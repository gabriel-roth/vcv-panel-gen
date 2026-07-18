"""Spec parsing and validation for the v2 grid-based panel format.

This module is pure parsing/validation: it turns a YAML mapping into a
PanelSpec tree of dataclasses, checking every rule the schema defines
(design doc section 4). It does NOT compute element positions — grid
columns/rows are normalized (explicit lists, {count,from,to} forms, evenly
spaced rows) but a column-only grid ({count} with no from/to) is left
unresolved on purpose: its span depends on side_margin, which is only a
default and is applied by the resolver (Task 4), not here.

Unknown keys are rejected everywhere, using the same _reject_unknown
technique as v1's spec.py: it names the offending key(s) and the context
(its "path") in the error message, so a typo reads as a clear SpecError
instead of being silently ignored.
"""
import os
import re
from dataclasses import dataclass, field

import yaml

from components import load_component_db
from constants import VALUE_RING_GAP_MM
from theme import CASING_MODES


class SpecError(Exception):
    pass


# Zone defaults: v1's constants.py ZONE_FILL/ZONE_OPACITY/ZONE_RX values,
# copied here because Task 1 dropped them from the trimmed constants.py (they
# are spec-schema defaults, not shared geometry constants).
ZONE_FILL = "#ffffff"
ZONE_OPACITY = 0.14
ZONE_RX = 2.0

# All spec-level colors (zone fill, label/text color) use this exact form:
# 6 or 8 hex digits, no 3-digit shorthand.
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")

_ALLOWED_KINDS = {"param", "input", "output", "light", "widget"}
_SUFFIX_KIND = [
    ("_PARAM", "param"),
    ("_INPUT", "input"),
    ("_OUTPUT", "output"),
    ("_LIGHT", "light"),
]

_COMPONENT_DB = load_component_db()


def _reject_unknown(mapping, allowed, context):
    unknown = set(mapping) - allowed
    if unknown:
        raise SpecError(
            f"{context}: unknown key(s) {sorted(unknown)}; "
            f"valid: {sorted(allowed)}")


def _is_number(v):
    return not isinstance(v, bool) and isinstance(v, (int, float))


def _parse_number(v, field_name, ctx):
    if not _is_number(v):
        raise SpecError(f"{ctx}: {field_name!r} must be a number (mm), got {v!r}")
    return float(v)


def _parse_positive_number(v, field_name, ctx):
    if not _is_number(v) or v <= 0:
        raise SpecError(f"{ctx}: {field_name!r} must be a positive number, got {v!r}")
    return float(v)


def _parse_nonneg_number(v, field_name, ctx):
    if not _is_number(v) or v < 0:
        raise SpecError(f"{ctx}: {field_name!r} must be a non-negative number, got {v!r}")
    return float(v)


def _parse_color(v, ctx, field_name="color"):
    if not isinstance(v, str) or not COLOR_RE.match(v):
        raise SpecError(
            f"{ctx}: {field_name!r} must be a hex color like #rrggbb or "
            f"#rrggbbaa, got {v!r}")
    return v


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ColsSpec:
    count: int
    x_from: float | None
    x_to: float | None
    explicit: list | None


@dataclass(frozen=True)
class GridSpec:
    cols: ColsSpec
    rows: dict


@dataclass(frozen=True)
class Position:
    grid: str | None
    col: int | None
    row: str | None
    x: float | None
    y: float | None
    dx: float = 0.0
    dy: float = 0.0


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class LabelSpec:
    text: str
    dx: float
    dy: float
    size: float | None = None
    color: str | None = None
    casing: str | None = None


@dataclass
class ComponentEl:
    name: str
    kind: str
    widget: str | None
    pos: Position | None
    rect: Rect | None
    label: LabelSpec | None = None


@dataclass
class TextEl:
    text: str
    pos: Position
    size: float | None = None
    color: str | None = None
    casing: str | None = None
    tracking: float | None = None


@dataclass
class RingEl:
    labels: list
    around: str
    gap: float


@dataclass
class Zone:
    x: float
    y: float
    w: float
    h: float
    rx: float
    fill: str
    opacity: float


@dataclass
class GlyphEl:
    src: str
    x: float
    y: float
    scale: float


@dataclass
class TitleSpec:
    text: str | None
    logo: str | None = None
    size: float | None = None
    tracking: float | None = None
    valign: str | None = None
    x: float | None = None
    y: float | None = None
    dx: float | None = None
    dy: float | None = None
    kern: list | None = None   # per-pair kerning: list of (pair, em) tuples


@dataclass
class PanelSpec:
    slug: str
    name: str
    hp: int
    theme_mapping: dict | None
    title: TitleSpec
    grids: dict = field(default_factory=dict)
    elements: list = field(default_factory=list)
    zones: list | None = None
    glyphs: list | None = None
    connectors: list | None = None
    overlaps_ok: list | None = None
    side_margin: float | None = None


# ---------------------------------------------------------------------------
# Grids
# ---------------------------------------------------------------------------

_GRID_KEYS = {"cols", "rows"}
_COLS_DICT_KEYS = {"count", "from", "to"}
_ROWS_EVEN_KEYS = {"from", "to", "count", "names"}


def _parse_cols(raw, ctx):
    if raw is None:
        raise SpecError(f"{ctx}: 'cols' is required")
    if isinstance(raw, list):
        if not raw or any(not _is_number(v) for v in raw):
            raise SpecError(f"{ctx}: 'cols' list must be a non-empty list of numbers")
        return ColsSpec(count=len(raw), x_from=None, x_to=None,
                         explicit=[float(v) for v in raw])
    if isinstance(raw, dict):
        _reject_unknown(raw, _COLS_DICT_KEYS, f"{ctx} cols")
        count = raw.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise SpecError(f"{ctx} cols: 'count' must be a positive integer, got {count!r}")
        has_from, has_to = "from" in raw, "to" in raw
        if has_from != has_to:
            raise SpecError(f"{ctx} cols: 'from' and 'to' must be given together")
        x_from = x_to = None
        if has_from:
            x_from = _parse_number(raw["from"], "from", f"{ctx} cols")
            x_to = _parse_number(raw["to"], "to", f"{ctx} cols")
            if x_to <= x_from:
                raise SpecError(f"{ctx} cols: 'to' must be greater than 'from'")
        return ColsSpec(count=count, x_from=x_from, x_to=x_to, explicit=None)
    raise SpecError(
        f"{ctx}: 'cols' must be a list of numbers or a mapping {{count, from?, to?}}, "
        f"got {raw!r}")


def _parse_rows_even(raw, ctx):
    count = raw["count"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise SpecError(f"{ctx} rows: 'count' must be a positive integer, got {count!r}")
    x_from = _parse_number(raw["from"], "from", f"{ctx} rows")
    x_to = _parse_number(raw["to"], "to", f"{ctx} rows")
    if count > 1 and x_to <= x_from:
        raise SpecError(f"{ctx} rows: 'to' must be greater than 'from'")
    names = raw["names"]
    if (not isinstance(names, list)
            or any(not isinstance(n, str) or not n.strip() for n in names)):
        raise SpecError(f"{ctx} rows: 'names' must be a list of non-empty strings")
    if len(names) != count:
        raise SpecError(
            f"{ctx} rows: 'names' length ({len(names)}) must equal 'count' ({count})")
    if len(set(names)) != len(names):
        raise SpecError(f"{ctx} rows: 'names' must be unique")
    if count == 1:
        values = [x_from]
    else:
        step = (x_to - x_from) / (count - 1)
        values = [x_from + i * step for i in range(count)]
    return dict(zip(names, values))


_ROWS_EVEN_TRIGGER_KEYS = {"count", "names"}


def _parse_rows(raw, ctx):
    if raw is None:
        raise SpecError(f"{ctx}: 'rows' is required")
    if not isinstance(raw, dict):
        raise SpecError(f"{ctx}: 'rows' must be a mapping")
    if any(k in raw for k in _ROWS_EVEN_TRIGGER_KEYS):
        # Evenly-spaced form: {from, to, count, names}. Dispatch on 'count'
        # or 'names' being present (rather than requiring an exact key-set
        # match) so a spec that's missing one of the four required keys
        # still gets a clear "evenly-spaced form requires X" error instead
        # of silently falling through to the literal name->value form.
        _reject_unknown(raw, _ROWS_EVEN_KEYS, f"{ctx} rows")
        for k in ("from", "to", "count", "names"):
            if k not in raw:
                raise SpecError(
                    f"{ctx} rows: evenly-spaced form requires {k!r} "
                    f"(rows are always referenced by name)")
        return _parse_rows_even(raw, ctx)
    if not raw:
        raise SpecError(f"{ctx}: 'rows' must be non-empty")
    rows = {}
    for name, v in raw.items():
        if not isinstance(name, str) or not name.strip():
            raise SpecError(f"{ctx}: row name must be a non-empty string, got {name!r}")
        rows[name] = _parse_number(v, name, f"{ctx} rows")
    return rows


def _parse_grids(raw):
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise SpecError("'grids' must be a mapping of grid name -> grid def")
    grids = {}
    for name, gdef in raw.items():
        ctx = f"grid {name!r}"
        if not isinstance(gdef, dict):
            raise SpecError(f"{ctx}: must be a mapping")
        _reject_unknown(gdef, _GRID_KEYS, ctx)
        cols = _parse_cols(gdef.get("cols"), ctx)
        rows = _parse_rows(gdef.get("rows"), ctx)
        grids[name] = GridSpec(cols=cols, rows=rows)
    return grids


# ---------------------------------------------------------------------------
# Element position
# ---------------------------------------------------------------------------

def _parse_position(raw, grids, ctx):
    grid = raw.get("grid")
    col = raw.get("col")
    row = raw.get("row")
    x = raw.get("x")
    y = raw.get("y")

    if grid is not None:
        if not isinstance(grid, str):
            raise SpecError(f"{ctx}: 'grid' must be a string, got {grid!r}")
        if grid not in grids:
            raise SpecError(f"{ctx}: unknown grid {grid!r}")

    has_col, has_x = col is not None, x is not None
    if has_col == has_x:
        raise SpecError(
            f"{ctx}: exactly one x-source is required per element (grid+col or x)")
    if has_col:
        if grid is None:
            raise SpecError(f"{ctx}: 'col' requires 'grid'")
        if isinstance(col, bool) or not isinstance(col, int) or col < 1:
            raise SpecError(f"{ctx}: 'col' must be a positive 1-based integer, got {col!r}")
        gspec = grids[grid]
        if col > gspec.cols.count:
            raise SpecError(
                f"{ctx}: col {col} is out of range for grid {grid!r} "
                f"({gspec.cols.count} columns)")
    else:
        x = _parse_number(x, "x", ctx)

    has_row, has_y = row is not None, y is not None
    if has_row == has_y:
        raise SpecError(
            f"{ctx}: exactly one y-source is required per element (row or y)")
    if has_row:
        if grid is None:
            raise SpecError(f"{ctx}: 'row' requires 'grid'")
        if not isinstance(row, str):
            raise SpecError(f"{ctx}: 'row' must be a string, got {row!r}")
        gspec = grids[grid]
        if row not in gspec.rows:
            raise SpecError(f"{ctx}: unknown row {row!r} in grid {grid!r}")
    else:
        y = _parse_number(y, "y", ctx)

    dx = _parse_number(raw.get("dx", 0.0), "dx", ctx)
    dy = _parse_number(raw.get("dy", 0.0), "dy", ctx)

    return Position(grid=grid, col=col, row=row, x=x, y=y, dx=dx, dy=dy)


# ---------------------------------------------------------------------------
# kind inference
# ---------------------------------------------------------------------------

def _infer_or_validate_kind(name, explicit, ctx):
    inferred = None
    for suffix, k in _SUFFIX_KIND:
        if name.endswith(suffix):
            inferred = k
            break
    if explicit is not None:
        if explicit not in _ALLOWED_KINDS:
            raise SpecError(
                f"{ctx}: 'kind' must be one of {sorted(_ALLOWED_KINDS)}, got {explicit!r}")
        return explicit
    if inferred is not None:
        return inferred
    raise SpecError(
        f"{ctx}: 'kind' is required (name {name!r} has no recognized "
        f"_PARAM/_INPUT/_OUTPUT/_LIGHT suffix)")


# ---------------------------------------------------------------------------
# Label sugar
# ---------------------------------------------------------------------------

_LABEL_KEYS = {"text", "dx", "dy", "size", "color", "casing"}


def _parse_label(raw, ctx):
    if isinstance(raw, str):
        raise SpecError(
            f"{ctx}: 'label' must be a mapping {{text, dx?, dy, size?, color?, casing?}} "
            f"with an explicit 'dy' offset, not a bare string like {raw!r}")
    if not isinstance(raw, dict):
        raise SpecError(f"{ctx}: 'label' must be a mapping, got {raw!r}")
    _reject_unknown(raw, _LABEL_KEYS, f"{ctx} label")
    text = raw.get("text")
    if not isinstance(text, str) or not text.strip():
        raise SpecError(f"{ctx} label: 'text' must be a non-empty string")
    if "dy" not in raw:
        raise SpecError(
            f"{ctx} label: 'dy' is required (an explicit offset — there is no default)")
    dy = _parse_number(raw["dy"], "dy", f"{ctx} label")
    dx = _parse_number(raw.get("dx", 0.0), "dx", f"{ctx} label")
    size = _parse_positive_number(raw["size"], "size", f"{ctx} label") if "size" in raw else None
    color = _parse_color(raw["color"], f"{ctx} label") if "color" in raw else None
    casing = raw.get("casing")
    if casing is not None and casing not in CASING_MODES:
        raise SpecError(f"{ctx} label: 'casing' must be one of {CASING_MODES}, got {casing!r}")
    return LabelSpec(text=text, dx=dx, dy=dy, size=size, color=color, casing=casing)


# ---------------------------------------------------------------------------
# Component / text / ring elements
# ---------------------------------------------------------------------------

_COMPONENT_KEYS = {"name", "kind", "widget", "grid", "col", "row", "x", "y",
                    "dx", "dy", "rect", "label"}
_RECT_KEYS = {"x", "y", "w", "h"}
_TEXT_KEYS = {"text", "grid", "col", "row", "x", "y", "dx", "dy",
              "size", "color", "casing", "tracking"}
_RING_KEYS = {"ring", "around", "gap"}


def _parse_rect(raw, ctx):
    if not isinstance(raw, dict):
        raise SpecError(f"{ctx}: 'rect' must be a mapping {{x, y, w, h}}, got {raw!r}")
    _reject_unknown(raw, _RECT_KEYS, f"{ctx} rect")
    for k in _RECT_KEYS:
        if k not in raw:
            raise SpecError(f"{ctx} rect: missing required key {k!r}")
    x = _parse_number(raw["x"], "x", f"{ctx} rect")
    y = _parse_number(raw["y"], "y", f"{ctx} rect")
    w = _parse_positive_number(raw["w"], "w", f"{ctx} rect")
    h = _parse_positive_number(raw["h"], "h", f"{ctx} rect")
    return Rect(x=x, y=y, w=w, h=h)


def _parse_component_el(raw, grids, ctx):
    _reject_unknown(raw, _COMPONENT_KEYS, ctx)
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise SpecError(f"{ctx}: 'name' must be a non-empty string, got {name!r}")
    name = name.strip()
    kind = _infer_or_validate_kind(name, raw.get("kind"), ctx)

    if "rect" in raw:
        for k in ("grid", "col", "row", "x", "y", "dx", "dy"):
            if k in raw:
                raise SpecError(f"{ctx}: 'rect' is mutually exclusive with {k!r}")
        if kind != "widget":
            raise SpecError(
                f"{ctx}: 'rect' is only valid with kind: widget, got kind {kind!r}")
        rect = _parse_rect(raw["rect"], ctx)
        pos = None
        widget = raw.get("widget")
        if widget is not None and (not isinstance(widget, str) or not widget.strip()):
            raise SpecError(f"{ctx}: 'widget' must be a non-empty string, got {widget!r}")
    else:
        rect = None
        pos = _parse_position(raw, grids, ctx)
        if "widget" in raw:
            widget = raw["widget"]
            if not isinstance(widget, str) or not widget.strip():
                raise SpecError(f"{ctx}: 'widget' must be a non-empty string, got {widget!r}")
        else:
            widget = _COMPONENT_DB.default_widget(kind)

    label = _parse_label(raw["label"], ctx) if "label" in raw else None
    return ComponentEl(name=name, kind=kind, widget=widget, pos=pos, rect=rect, label=label)


def _parse_text_el(raw, grids, ctx):
    _reject_unknown(raw, _TEXT_KEYS, ctx)
    text = raw.get("text")
    if not isinstance(text, str) or not text.strip():
        raise SpecError(f"{ctx}: 'text' must be a non-empty string, got {text!r}")
    pos = _parse_position(raw, grids, ctx)
    size = _parse_positive_number(raw["size"], "size", ctx) if "size" in raw else None
    color = _parse_color(raw["color"], ctx) if "color" in raw else None
    casing = raw.get("casing")
    if casing is not None and casing not in CASING_MODES:
        raise SpecError(f"{ctx}: 'casing' must be one of {CASING_MODES}, got {casing!r}")
    tracking = _parse_nonneg_number(raw["tracking"], "tracking", ctx) if "tracking" in raw else None
    return TextEl(text=text, pos=pos, size=size, color=color, casing=casing, tracking=tracking)


def _parse_ring(raw, ctx):
    _reject_unknown(raw, _RING_KEYS, ctx)
    labels = raw.get("ring")
    if (not isinstance(labels, list) or not labels
            or any(not isinstance(v, str) for v in labels)):
        raise SpecError(f"{ctx}: 'ring' must be a non-empty list of label strings")
    around = raw.get("around")
    if not isinstance(around, str) or not around.strip():
        raise SpecError(f"{ctx}: 'around' must name a declared component, got {around!r}")
    gap = _parse_nonneg_number(raw.get("gap", VALUE_RING_GAP_MM), "gap", ctx)
    return RingEl(labels=list(labels), around=around, gap=gap)


# ---------------------------------------------------------------------------
# row: / place: shorthand
# ---------------------------------------------------------------------------

_ROW_SHARED_KEYS = {"widget", "kind", "size", "color", "casing", "dx", "dy", "label"}
_ROW_BLOCK_KEYS = {"grid", "at"} | _ROW_SHARED_KEYS
_ROW_PLACE_KEYS = {"row", "place"}


def _expand_row_place(raw, ctx):
    """Expand a `row:`/`place:` shorthand entry into a list of
    ("component"|"text", merged_dict) pairs ready for the ordinary
    element parsers. `~` (YAML null) in `place` skips that column."""
    _reject_unknown(raw, _ROW_PLACE_KEYS, ctx)
    row_block = raw["row"]
    if not isinstance(row_block, dict):
        raise SpecError(f"{ctx}: 'row' shorthand block must be a mapping")
    _reject_unknown(row_block, _ROW_BLOCK_KEYS, f"{ctx} row")
    grid = row_block.get("grid")
    if not isinstance(grid, str) or not grid.strip():
        raise SpecError(f"{ctx} row: 'grid' is required")
    at = row_block.get("at")
    if not isinstance(at, str) or not at.strip():
        raise SpecError(f"{ctx} row: 'at' is required (row name)")
    shared = {k: v for k, v in row_block.items() if k in _ROW_SHARED_KEYS}

    place = raw["place"]
    if not isinstance(place, list) or not place:
        raise SpecError(f"{ctx}: 'place' must be a non-empty list")

    expanded = []
    for i, item in enumerate(place, start=1):
        if item is None:
            continue
        if isinstance(item, str):
            merged = dict(shared)
            merged.pop("widget", None)
            merged.pop("kind", None)
            merged["text"] = item
            merged["grid"] = grid
            merged["col"] = i
            merged["row"] = at
            expanded.append(("text", merged))
        elif isinstance(item, dict):
            if "name" in item:
                merged = dict(shared)
                merged.update(item)
                merged["grid"] = grid
                merged["col"] = i
                merged["row"] = at
                expanded.append(("component", merged))
            elif "text" in item:
                merged = dict(shared)
                merged.pop("widget", None)
                merged.pop("kind", None)
                merged.update(item)
                merged["grid"] = grid
                merged["col"] = i
                merged["row"] = at
                expanded.append(("text", merged))
            else:
                raise SpecError(f"{ctx}: place[{i}] must have 'name' or 'text', got {item!r}")
        else:
            raise SpecError(
                f"{ctx}: place[{i}] must be a mapping, string, or null, got {item!r}")
    return expanded


# ---------------------------------------------------------------------------
# elements list
# ---------------------------------------------------------------------------

def _parse_elements(raw_list, grids):
    elements = []
    names_seen = set()
    pending_rings = []

    def _add_component(merged, ctx):
        el = _parse_component_el(merged, grids, ctx)
        if el.name in names_seen:
            raise SpecError(f"{ctx}: duplicate component name {el.name!r}")
        names_seen.add(el.name)
        elements.append(el)

    for i, raw in enumerate(raw_list):
        ctx = f"element {i}"
        if not isinstance(raw, dict):
            raise SpecError(f"{ctx}: must be a mapping, got {raw!r}")
        if "ring" in raw:
            ring = _parse_ring(raw, ctx)
            elements.append(ring)
            pending_rings.append((ring, ctx))
        elif "row" in raw and "place" in raw:
            for kind_, merged in _expand_row_place(raw, ctx):
                sub_ctx = f"{ctx} place"
                if kind_ == "component":
                    _add_component(merged, sub_ctx)
                else:
                    elements.append(_parse_text_el(merged, grids, sub_ctx))
        elif "name" in raw:
            _add_component(raw, ctx)
        elif "text" in raw:
            elements.append(_parse_text_el(raw, grids, ctx))
        else:
            raise SpecError(
                f"{ctx}: must have 'name', 'text', 'ring', or 'row'+'place', got {raw!r}")

    for ring, ctx in pending_rings:
        if ring.around not in names_seen:
            raise SpecError(
                f"{ctx}: 'around' references unknown component {ring.around!r}")

    return elements, names_seen


# ---------------------------------------------------------------------------
# zones / glyphs / title / connectors / overlaps_ok
# ---------------------------------------------------------------------------

_ZONE_KEYS = {"x", "y", "w", "h", "rx", "fill", "opacity"}


def _parse_zones(raw):
    if raw is None:
        return None
    if not isinstance(raw, list) or not raw:
        raise SpecError("'zones' must be a non-empty list of rect mappings")
    zones = []
    for i, z in enumerate(raw):
        ctx = f"zone {i}"
        if not isinstance(z, dict):
            raise SpecError(f"{ctx}: must be a mapping, got {z!r}")
        _reject_unknown(z, _ZONE_KEYS, ctx)
        for k in ("x", "y", "w", "h"):
            if k not in z:
                raise SpecError(f"{ctx}: missing required key {k!r}")
        x = _parse_number(z["x"], "x", ctx)
        y = _parse_number(z["y"], "y", ctx)
        w = _parse_positive_number(z["w"], "w", ctx)
        h = _parse_positive_number(z["h"], "h", ctx)
        fill = _parse_color(z.get("fill", ZONE_FILL), ctx, "fill")
        opacity = z.get("opacity", ZONE_OPACITY)
        if not _is_number(opacity) or not 0 < float(opacity) <= 1:
            raise SpecError(f"{ctx}: 'opacity' must be in (0, 1], got {opacity!r}")
        rx = _parse_nonneg_number(z.get("rx", ZONE_RX), "rx", ctx)
        zones.append(Zone(x=x, y=y, w=w, h=h, rx=rx, fill=fill, opacity=float(opacity)))
    return zones


_GLYPH_KEYS = {"src", "at", "scale"}


def _parse_glyphs(raw, base_dir):
    if raw is None:
        return None
    if not isinstance(raw, list) or not raw:
        raise SpecError("'glyphs' must be a non-empty list of {src, at, scale} mappings")
    glyphs = []
    for i, g in enumerate(raw):
        ctx = f"glyph {i}"
        if not isinstance(g, dict):
            raise SpecError(f"{ctx}: must be a mapping, got {g!r}")
        _reject_unknown(g, _GLYPH_KEYS, ctx)
        src = g.get("src")
        if not isinstance(src, str) or not src.strip():
            raise SpecError(f"{ctx}: 'src' must be a path to an SVG asset, got {src!r}")
        resolved = os.path.normpath(os.path.join(base_dir, src))
        if not os.path.isfile(resolved):
            raise SpecError(f"{ctx}: src file not found: {src!r} (resolved to {resolved})")
        at = g.get("at")
        if (not isinstance(at, (list, tuple)) or len(at) != 2
                or any(not _is_number(v) for v in at)):
            raise SpecError(f"{ctx}: 'at' must be [x, y] in mm, got {at!r}")
        scale = g.get("scale", 1.0)
        if not _is_number(scale):
            raise SpecError(f"{ctx}: 'scale' must be a number, got {scale!r}")
        if scale == 0:
            raise SpecError(f"{ctx}: 'scale' must be non-zero, got {scale!r}")
        glyphs.append(GlyphEl(src=resolved, x=float(at[0]), y=float(at[1]), scale=float(scale)))
    return glyphs


_TITLE_KEYS = {"text", "logo", "size", "tracking", "valign", "x", "y", "dx", "dy", "kern"}


def _parse_title_kern(raw):
    """Parse a title `kern:` list into [(pair, em), ...]. Each entry is a
    mapping {pair: <2 chars>, em: <number>}; em is the adjustment in em units
    (fraction of the title size, negative = tighter) applied to the gap after
    the pair's first letter. Order is preserved so repeated pairs bind to
    successive occurrences (see resolve._resolve_kern)."""
    if not isinstance(raw, list):
        raise SpecError("title: 'kern' must be a list of {pair, em} mappings")
    out = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise SpecError(f"title: kern[{i}] must be a mapping with 'pair' and 'em'")
        _reject_unknown(item, {"pair", "em"}, f"title kern[{i}]")
        pair = item.get("pair")
        if isinstance(pair, bool):
            raise SpecError(
                f"title: kern[{i}] 'pair' came through as a boolean ({pair!r}); "
                f"YAML reads bare ON/OFF/YES/NO/TRUE as booleans — quote it, e.g. "
                f'pair: "ON"')
        if not isinstance(pair, str) or len(pair) != 2:
            raise SpecError(
                f"title: kern[{i}] 'pair' must be a 2-character string, got {pair!r}")
        if "em" not in item:
            raise SpecError(f"title: kern[{i}] requires 'em'")
        em = _parse_number(item["em"], "em", f"title kern[{i}]")
        out.append((pair, em))
    return out


def _parse_title(raw, base_dir, default_text):
    if raw is None:
        return TitleSpec(text=default_text)
    if not isinstance(raw, dict):
        raise SpecError("'title' must be a mapping")
    _reject_unknown(raw, _TITLE_KEYS, "title")
    text = raw.get("text")
    logo = raw.get("logo")
    if text is not None and logo is not None:
        raise SpecError("title: 'text' and 'logo' are mutually exclusive")
    if text is not None and (not isinstance(text, str) or not text.strip()):
        raise SpecError(f"title: 'text' must be a non-empty string, got {text!r}")
    if logo is not None:
        if not isinstance(logo, str) or not logo.strip():
            raise SpecError(f"title: 'logo' must be a path to a logo SVG, got {logo!r}")
        resolved = os.path.normpath(os.path.join(base_dir, logo))
        if not os.path.isfile(resolved):
            raise SpecError(f"title: logo file not found: {logo!r} (resolved to {resolved})")
        logo = resolved
    if text is None and logo is None:
        text = default_text

    size = _parse_positive_number(raw["size"], "size", "title") if "size" in raw else None
    tracking = (_parse_nonneg_number(raw["tracking"], "tracking", "title")
                if "tracking" in raw else None)
    valign = raw.get("valign")
    if valign is not None and valign not in ("baseline", "center"):
        raise SpecError(f"title: 'valign' must be 'baseline' or 'center', got {valign!r}")
    x = _parse_number(raw["x"], "x", "title") if "x" in raw else None
    y = _parse_number(raw["y"], "y", "title") if "y" in raw else None
    dx = _parse_number(raw["dx"], "dx", "title") if "dx" in raw else None
    dy = _parse_number(raw["dy"], "dy", "title") if "dy" in raw else None
    kern = _parse_title_kern(raw["kern"]) if "kern" in raw else None
    if kern is not None and logo is not None:
        raise SpecError("title: 'kern' applies to live text, not a 'logo'")

    return TitleSpec(text=text, logo=logo, size=size, tracking=tracking,
                      valign=valign, x=x, y=y, dx=dx, dy=dy, kern=kern)


def _parse_connectors(raw, names_seen):
    if raw is None:
        return None
    if not isinstance(raw, list) or not raw:
        raise SpecError("'connectors' must be a non-empty list of [A, B] name pairs")
    parsed = []
    for i, c in enumerate(raw):
        ctx = f"connector {i}"
        if (not isinstance(c, list) or len(c) != 2
                or any(not isinstance(x, str) or not x.strip() for x in c)):
            raise SpecError(f"{ctx}: must be a [from, to] pair of component names, got {c!r}")
        for nm in c:
            if nm not in names_seen:
                raise SpecError(f"{ctx}: unknown component name {nm!r}")
        parsed.append([c[0], c[1]])
    return parsed


def _validate_overlaps_ok_name(nm, names_seen, ctx):
    """A name in an overlaps_ok entry is either a declared component name
    (validated against names_seen, as before) or one of four special forms
    matching the non-component labels checks.py's warning formatter produces
    (see checks.py _screw_label/_text_label and the literal "title" label):
      - "title" -- the panel title.
      - "text:<content>" -- a text label, matched by exact content after the
        prefix, e.g. "text:OUT" matches checks.py's `f"text:{t.text}"`.
      - "screw" -- any screw (wildcard).
      - "screw@<x>,<y>" -- a specific screw, matched (in checks.py) after
        rounding x,y to 2 decimals exactly as `f"screw@{s.x:.2f},{s.y:.2f}"`
        formats them.
    Unknown non-prefixed names still error.
    """
    if nm == "title" or nm == "screw":
        return
    if nm.startswith("text:"):
        if nm == "text:":
            raise SpecError(
                f"{ctx}: 'text:' entry must have content after the prefix, got {nm!r}")
        return
    if nm.startswith("screw@"):
        coords = nm[len("screw@"):]
        parts = coords.split(",")
        if len(parts) != 2:
            raise SpecError(
                f"{ctx}: 'screw@x,y' entry must have exactly one comma, got {nm!r}")
        for part in parts:
            try:
                float(part)
            except ValueError:
                raise SpecError(
                    f"{ctx}: 'screw@x,y' coordinates must be numeric, got {nm!r}")
        return
    if nm not in names_seen:
        raise SpecError(f"{ctx}: unknown component name {nm!r}")


def _parse_overlaps_ok(raw, names_seen):
    if raw is None:
        return None
    if not isinstance(raw, list) or not raw:
        raise SpecError("'overlaps_ok' must be a non-empty list of name lists")
    parsed = []
    for i, entry in enumerate(raw):
        ctx = f"overlaps_ok {i}"
        if (not isinstance(entry, list) or len(entry) not in (1, 2)
                or any(not isinstance(x, str) or not x.strip() for x in entry)):
            raise SpecError(
                f"{ctx}: must be a list of 1 or 2 names, got {entry!r}")
        for nm in entry:
            _validate_overlaps_ok_name(nm, names_seen, ctx)
        parsed.append(list(entry))
    return parsed


# ---------------------------------------------------------------------------
# Top level
# ---------------------------------------------------------------------------

TOP_KEYS = {"slug", "name", "hp", "theme", "title", "grids", "elements",
            "zones", "glyphs", "connectors", "overlaps_ok", "side_margin"}


def parse_spec(data, base_dir):
    if not isinstance(data, dict):
        raise SpecError("Spec must be a YAML mapping")
    for key in ("slug", "name", "hp", "elements"):
        if key not in data:
            raise SpecError(f"Spec missing required key: {key}")
    _reject_unknown(data, TOP_KEYS, "Spec")

    slug = data["slug"]
    if not isinstance(slug, str) or not slug.strip():
        raise SpecError(f"'slug' must be a non-empty string, got {slug!r}")
    name = data["name"]
    if not isinstance(name, str) or not name.strip():
        raise SpecError(f"'name' must be a non-empty string, got {name!r}")
    hp = data["hp"]
    if isinstance(hp, bool) or not isinstance(hp, int) or hp <= 0:
        raise SpecError(f"'hp' must be a positive integer, got {hp!r}")

    theme_mapping = data.get("theme")
    if theme_mapping is not None and not isinstance(theme_mapping, dict):
        raise SpecError(f"'theme' must be a mapping, got {theme_mapping!r}")

    grids = _parse_grids(data.get("grids"))

    raw_elements = data["elements"]
    if not isinstance(raw_elements, list) or not raw_elements:
        raise SpecError("'elements' must be a non-empty list")
    elements, names_seen = _parse_elements(raw_elements, grids)

    zones = _parse_zones(data.get("zones"))
    glyphs = _parse_glyphs(data.get("glyphs"), base_dir)
    title = _parse_title(data.get("title"), base_dir, default_text=name)
    connectors = _parse_connectors(data.get("connectors"), names_seen)
    overlaps_ok = _parse_overlaps_ok(data.get("overlaps_ok"), names_seen)

    side_margin = data.get("side_margin")
    if side_margin is not None:
        side_margin = _parse_positive_number(side_margin, "side_margin", "Spec")

    return PanelSpec(slug=slug, name=name, hp=hp, theme_mapping=theme_mapping,
                      title=title, grids=grids, elements=elements, zones=zones,
                      glyphs=glyphs, connectors=connectors, overlaps_ok=overlaps_ok,
                      side_margin=side_margin)


def load_spec(path):
    with open(path) as f:
        data = yaml.safe_load(f)
    base_dir = os.path.dirname(os.path.abspath(path))
    return parse_spec(data, base_dir)
