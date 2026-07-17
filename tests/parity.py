"""Parity helpers: pull component centers and panel-layer path data out of an
SVG for comparing a v2-generated panel against a hand-authored RobotBoy
reference (or vice versa).

Two authoring dialects show up in the reference fixtures under
`tests/fixtures/robotboy/`:

  - panel_gen output (Loooop.svg, Lop.svg, MF20Filter.svg): the components
    layer is `<g inkscape:label="components" ... id="components"
    style="display:none">` and every shape's `id` is `NAME#WidgetClass`
    (e.g. `CUTOFF_PARAM#RoundBigBlackKnob`), with a tiny fixed marker radius
    (r="2") that carries no size information.
  - hand-built Particules.svg: the layer is `<g id="layer_components"
    inkscape:label="components" ...>` (the *id* is not literally
    "components", only the inkscape:label is) and shape ids are the bare
    param/input/output name (`TIME_PARAM`, no `#Widget` suffix) with a *true*
    drawn radius (e.g. r="4.8" for a RoundBlackKnob) rather than a fixed
    marker size.

`components_of` is dialect-agnostic: it locates the components layer by
searching for either `inkscape:label="<name>"` or `id="<name>"` (so it finds
Particules' layer via its label, not its id), and reads only cx/cy (or
x/y/width/height for rects) -- never r -- so the differing radius
conventions don't matter. The dict key is always whatever the `id` attribute
literally contains, `#Widget` suffix or not, so callers must know which
dialect they're comparing against (this mirrors v1 preview.py's `_controls`,
which resolves the widget *class* the same way for its own purposes).

Same layer-lookup technique is used for the panel layer (`panel` /
`layer_panel`) to pull `<path>` elements for whole-shape comparison.
"""
import os
import re

import pytest
import yaml

import fontresolve

_NUM_RE = r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?'
_ATTR_RE = re.compile(r'(\w[\w:-]*)="([^"]*)"')

_ROBOTBOY_THEME = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "fixtures", "robotboy", "theme.yaml")

_font_index_cache = None


def _font_index():
    """Build (and cache for the session) the installed-font index used by
    require_robotboy_fonts -- the directory scan is the expensive part of
    fontresolve.resolve_font_stack, and every parity test file calls the
    guard once at collection time."""
    global _font_index_cache
    if _font_index_cache is None:
        _font_index_cache = fontresolve.build_font_index()
    return _font_index_cache


def require_robotboy_fonts():
    """Skip the calling test module unless the RobotBoy fixture theme's font
    stacks (Futura for body text, "Shuttleblock Test Demi" for the title)
    both resolve to a real installed face rather than fontresolve's bundled
    DejaVu Sans fallback.

    fontresolve silently falls back to bundled DejaVu when a requested
    family isn't installed, so on a machine missing these two fonts the
    parity suites would otherwise run to completion and fail with enormous,
    opaque path-geometry diffs (every glyph outline differs) instead of a
    clear, actionable reason. These fixtures are machine-specific acceptance
    tests captured against one real installation, so a loud skip elsewhere
    beats a red suite.
    """
    with open(_ROBOTBOY_THEME, "r", encoding="utf-8") as f:
        theme_data = yaml.safe_load(f)

    index = _font_index()
    base_stack = theme_data.get("font") or []
    title_stack = theme_data.get("title_font") or base_stack
    bundled = os.path.realpath(fontresolve.BUNDLED_FONT)

    for stack in (base_stack, title_stack):
        path, _num = fontresolve.resolve_font_stack(stack, index=index)
        if os.path.realpath(path) == bundled:
            pytest.skip(
                "RobotBoy parity fixtures require the Futura and "
                "Shuttleblock Test Demi fonts; skipping")


def _read(svg_path):
    with open(svg_path, "r", encoding="utf-8") as f:
        return f.read()


def _layer_body(svg_text, name):
    """Inner text of the first `<g>` layer tagged `inkscape:label="name"` or
    `id="name"`, or None if no such layer exists. Layers in all four
    reference fixtures are non-nested (no `<g>` opens again before the
    layer's own closing `</g>`), so the first `</g>` after the opening tag
    is reliably the layer's own close."""
    pattern = (
        r'<g\b[^>]*?(?:inkscape:label="%s"|id="%s")[^>]*?>(.*?)</g>'
        % (re.escape(name), re.escape(name))
    )
    m = re.search(pattern, svg_text, re.DOTALL)
    return m.group(1) if m else None


def _attrs(text):
    return dict(_ATTR_RE.findall(text))


def components_of(svg_path):
    """dict: full `id` attribute -> ("circle", cx, cy) or ("rect", x, y, w, h),
    for every <circle>/<rect> in the components layer. Coordinates rounded to
    3 decimals. Radius is never read (see module docstring: the two dialects
    disagree on what `r` means)."""
    body = _layer_body(_read(svg_path), "components")
    result = {}
    if body is None:
        return result
    for m in re.finditer(r'<(circle|rect)\b([^>]*?)/>', body, re.DOTALL):
        tag = m.group(1)
        attrs = _attrs(m.group(2))
        eid = attrs.get("id")
        if not eid:
            continue
        if tag == "circle":
            result[eid] = (
                "circle",
                round(float(attrs["cx"]), 3),
                round(float(attrs["cy"]), 3),
            )
        else:
            result[eid] = (
                "rect",
                round(float(attrs["x"]), 3),
                round(float(attrs["y"]), 3),
                round(float(attrs["width"]), 3),
                round(float(attrs["height"]), 3),
            )
    return result


def _normalize_d(d):
    """Collapse whitespace runs to single spaces and round every numeric
    token to 3 decimals, so cosmetically-different but numerically-equal
    path data (trailing float noise, inconsistent spacing) compares equal."""
    d = re.sub(r"\s+", " ", d.strip())

    def repl(m):
        val = round(float(m.group(0)), 3)
        if val == 0:
            val = 0.0  # normalize -0.0 to 0.0 before formatting
        s = f"{val:.3f}".rstrip("0").rstrip(".")
        return s if s else "0"

    return re.sub(_NUM_RE, repl, d)


def panel_paths_of(svg_path):
    """list[str]: normalized `d` strings of every <path> in the panel layer,
    in document order."""
    body = _layer_body(_read(svg_path), "panel")
    if body is None:
        return []
    paths = []
    for m in re.finditer(r"<path\b([^>]*?)/>", body, re.DOTALL):
        attrs = _attrs(m.group(1))
        d = attrs.get("d")
        if d is None:
            continue
        paths.append(_normalize_d(d))
    return paths


def values_paths_of(svg_path):
    """list[str]: normalized `d` strings of every <path> in the `values`
    layer (value-ring / position labels), in document order. Same
    normalization as panel_paths_of -- see its docstring -- just aimed at the
    other visible layer, since value-ring labels are deliberately excluded
    from the panel layer (kept out of the MetaModule faceplate PNG export)."""
    body = _layer_body(_read(svg_path), "values")
    if body is None:
        return []
    paths = []
    for m in re.finditer(r"<path\b([^>]*?)/>", body, re.DOTALL):
        attrs = _attrs(m.group(1))
        d = attrs.get("d")
        if d is None:
            continue
        paths.append(_normalize_d(d))
    return paths


def _parse_style(style):
    """Split a `style="prop:value;prop2:value2"` attribute into a dict.
    Hand-tuned reference rects (e.g. MF-20's zone tint) encode fill via
    `style=` instead of discrete `fill=`/`fill-opacity=` attributes; this
    lets panel_shapes_of normalize both encodings to the same comparable
    form."""
    props = {}
    for chunk in style.split(";"):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        k, v = chunk.split(":", 1)
        props[k.strip()] = v.strip()
    return props


def panel_shapes_of(svg_path):
    """list[tuple]: normalized geometry of every <rect>/<circle> in the panel
    layer that is NOT part of a `<path>` -- the zone tint, mounting screws,
    and connector bars that panel_paths_of can't see (it only reads <path>
    elements). Each entry is a tuple of the tag name followed by every
    remaining attribute as (key, value) pairs sorted by key, with numeric
    values rounded to 3 decimals and non-numeric values (colors, class,
    opacity strings) kept as-is.

    A `style="..."` attribute (if present) is parsed into individual
    properties and merged in -- per SVG semantics, style wins over any
    discrete attribute of the same name -- so a hand-tuned reference rect
    encoding `fill`/`fill-opacity` via `style=` compares equal to a
    generated rect using discrete attributes. `stroke:none` (from either
    encoding) is then dropped, since an absent `stroke` attribute means the
    same default. `id` and `class` are also excluded: these shapes are
    decorative and unidentified in both dialects (the components layer,
    which DOES carry ids, is `components_of`'s job), and `class` is purely
    an authoring artifact of one encoding.

    The full list is generic across the panel_gen dialect (Loooop.svg,
    Lop.svg, MF20Filter.svg all use the same `panel`-layer conventions), so
    Tasks 13-14 can reuse it unchanged.
    """
    body = _layer_body(_read(svg_path), "panel")
    shapes = []
    if body is None:
        return shapes
    for m in re.finditer(r"<(rect|circle)\b([^>]*?)/>", body, re.DOTALL):
        tag = m.group(1)
        attrs = _attrs(m.group(2))
        style = attrs.pop("style", None)
        if style:
            attrs.update(_parse_style(style))
        attrs.pop("id", None)
        attrs.pop("class", None)
        if attrs.get("stroke") == "none":
            attrs.pop("stroke", None)
        items = []
        for k, v in attrs.items():
            try:
                v_norm = round(float(v), 3)
                if v_norm == 0:
                    v_norm = 0.0
            except ValueError:
                v_norm = v
            items.append((k, v_norm))
        shapes.append((tag, tuple(sorted(items))))
    return shapes
