"""Parity test: Particules regenerated from the new-format spec
(tests/fixtures/robotboy/particules.yaml) against the shipped RobotBoy
reference SVG (tests/fixtures/robotboy/reference/Particules.svg).

UNLIKE Löp/Loooop/MF-20 (test_parity_lop.py/test_parity_loooop.py/
test_parity_mf20.py), Particules' reference is the HAND-BUILT Inkscape
original, not a v1-pipeline-generated SVG:

  - Its components layer uses BARE ids (no `#WidgetClass` suffix) and its
    layer's `id` attribute is "layer_components" (only the
    inkscape:label is "components") -- parity.components_of already
    handles this dialect (see its module docstring), but the generated
    side's ids still carry `#WidgetClass`, so this file strips that suffix
    before comparing by name.
  - Its labels/title live in a separate "text" Inkscape layer (not baked
    as <path> inside "panel" like the panel_gen dialect), and it has NO
    <path> elements in "panel" at all -- so a panel_paths_of comparison
    against it would be comparing apples to nothing, which is exactly why
    component-CENTER parity is the mandatory contract here, not path
    parity (see particules.yaml's header comment and the task report).

One documented name discrepancy: the reference's components layer has a
circle named DENSITY_AR_PARAM at (29.6, 62.746) -- the exact position where
current Particules.cpp instead places GRAIN_LIGHT. GRAIN_LIGHT has occupied
this slot in Particules.cpp since the repo's first tracked commit;
DENSITY_AR_PARAM never appears in Particules.cpp history. The stale name
exists only in the hand-built SVG's invisible components layer, a leftover
from earlier design iterations. Since component-center parity must follow the
C++ mm2px coordinates (the MetaModule sync source of truth), _NAME_REMAP
below documents this one substitution explicitly rather than silently allowing
a set mismatch.

ROBOTBOY_THEME is a committed copy of ~/.config/vcv-panel-gen/theme.yaml (see
test_parity_mf20.py for the full rationale); Particules' spec overrides
screws to "none" (the module widget draws its own ScrewBlack corners).
"""
import html
import math
import os
import re
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import parity
import spec
from extract_reference import _path_bbox
from panelgen import generate

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "robotboy")
SPEC = os.path.join(FIXTURES, "particules.yaml")
REF = os.path.join(FIXTURES, "reference", "Particules.svg")
WORKTREE_REGEN = os.path.expanduser(
    "~/Dev/RobotBoy/.claude/worktrees/panel-refactor/res/Particules.svg")
ROBOTBOY_THEME = os.path.join(FIXTURES, "theme.yaml")


@pytest.fixture(autouse=True)
def _require_fonts():
    # Skip loudly on machines missing Futura / Shuttleblock Test Demi
    # instead of failing with an opaque wall of path-geometry diffs (see
    # parity.require_robotboy_fonts's docstring).
    parity.require_robotboy_fonts()

# The reference's one stale marker name -> the current cpp/spec name at the
# identical (29.6, 62.746) position. See module docstring.
_NAME_REMAP = {"DENSITY_AR_PARAM": "GRAIN_LIGHT"}


def test_component_centers_exact(tmp_path):
    """Mandatory: every component's center must match the hand-built
    reference to 1e-3mm, by NAME (bare in the reference, `NAME#Widget` in
    the generated output -- stripped before comparing), after applying the
    one documented DENSITY_AR_PARAM->GRAIN_LIGHT remap. Widget classes in
    the generated ids are asserted against Particules.cpp's actual widget
    types (collapsed to components.yaml's canonical shape classes, per
    Loooop.yaml's precedent -- see particules.yaml's header comment)."""
    out = tmp_path / "Particules.svg"
    report = generate(SPEC, str(out), theme_path=ROBOTBOY_THEME)
    assert not report.errors, report.errors

    got_raw = parity.components_of(str(out))
    want_raw = parity.components_of(REF)

    # Split generated ids into name -> (widget, shape-tuple).
    got = {}
    got_widgets = {}
    for eid, shape in got_raw.items():
        name, _, widget = eid.partition("#")
        got[name] = shape
        # Widget class names appear XML-escaped in the id attribute (e.g.
        # "MediumLight&lt;WhiteLight&gt;") since "<"/">" aren't legal
        # unescaped inside an XML attribute value; unescape before comparing.
        got_widgets[name] = html.unescape(widget) if widget else None

    want = {_NAME_REMAP.get(name, name): shape for name, shape in want_raw.items()}

    assert got.keys() == want.keys()
    for k in want:
        assert got[k][0] == want[k][0], k  # same shape kind (circle/rect)
        assert got[k][1:] == pytest.approx(want[k][1:], abs=1e-3), k

    # Widget classes from Particules.cpp's createXCentered<...> call sites,
    # collapsed to components.yaml's canonical shape class (matches
    # Loooop.yaml's VCVLightButton<...> -> VCVButton precedent).
    expected_widgets = {
        "FREEZE_PARAM": "VCVButton",
        "QUALITY_PARAM": "VCVBezel",
        "TIME_PARAM": "RoundBlackKnob",
        "DENSITY_PARAM": "RoundBlackKnob",
        "PITCH_PARAM": "RoundBlackKnob",
        "SIZE_PARAM": "RoundBlackKnob",
        "SHAPE_PARAM": "RoundBlackKnob",
        "FEEDBACK_PARAM": "RoundBlackKnob",
        "REVERB_PARAM": "RoundBlackKnob",
        "DRY_WET_PARAM": "RoundBlackKnob",
        "TIME_AR_PARAM": "Trimpot",
        "PITCH_AR_PARAM": "Trimpot",
        "SIZE_AR_PARAM": "Trimpot",
        "SHAPE_AR_PARAM": "Trimpot",
        "FEEDBACK_AMT_PARAM": "Trimpot",
        "REVERB_AMT_PARAM": "Trimpot",
        "DRY_WET_AMT_PARAM": "Trimpot",
        "GRAIN_LIGHT": "MediumLight<WhiteLight>",
    }
    for name, widget in expected_widgets.items():
        assert got_widgets[name] == widget, name


def test_zone_and_furniture(tmp_path):
    """Panel furnishings, asserted against literal expected values rather
    than the reference (comparing the generated output's own panel_shapes_of
    to itself would be vacuous, and the reference's dialect differs enough
    -- e.g. it has no connector-bar/screw concept at all -- that a set
    comparison isn't meaningful here): the translucent pink control-zone
    rect at its exact spec'd geometry/fill/opacity, no #808080 connector
    bars (bars: false / no `connectors:` in the spec), and no screw markers
    (theme: {screws: none})."""
    out = tmp_path / "Particules.svg"
    generate(SPEC, str(out), theme_path=ROBOTBOY_THEME)

    shapes = parity.panel_shapes_of(str(out))

    zone_shapes = [s for s in shapes if dict(s[1]).get("fill") == "#cf99a5"]
    assert len(zone_shapes) == 1, shapes
    tag, attrs = zone_shapes[0]
    assert tag == "rect"
    attrs = dict(attrs)
    assert attrs["x"] == pytest.approx(1.5, abs=1e-3)
    assert attrs["y"] == pytest.approx(28.0, abs=1e-3)
    assert attrs["width"] == pytest.approx(73.2, abs=1e-3)
    assert attrs["height"] == pytest.approx(79.6, abs=1e-3)
    assert attrs["rx"] == pytest.approx(2.0, abs=1e-3)
    assert attrs["fill-opacity"] == pytest.approx(0.5, abs=1e-3) if "fill-opacity" in attrs \
        else attrs.get("opacity") == pytest.approx(0.5, abs=1e-3)

    # No connector bars: v1's #808080 bar color never appears in the panel.
    bar_shapes = [s for s in shapes if dict(s[1]).get("fill") == "#808080"]
    assert bar_shapes == []

    # No screw markers: the module widget draws its own, so theme:
    # {screws: none} means zero screw circles in the generated panel
    # (screws are the only <circle> shapes panel_shapes_of would ever see
    # in this dialect -- connector bars and the background/zone tint are
    # both <rect>).
    circle_shapes = [s for s in shapes if s[0] == "circle"]
    assert circle_shapes == [], f"expected no circles (no screws) in panel layer, found {circle_shapes}"


def _element_bbox(tag, attrs):
    """(minx, miny, maxx, maxy) for one baked glyph element -- reuses
    tools/extract_reference's path-bbox math for <path>, and plain min/max
    for <line>/<polyline>/<polygon> (images.py never emits curves for those
    tags, only straight segments, so a simple min/max is exact, not just a
    containing box)."""
    if tag == "path":
        return _path_bbox(attrs["d"])
    if tag == "line":
        xs = [float(attrs["x1"]), float(attrs["x2"])]
        ys = [float(attrs["y1"]), float(attrs["y2"])]
        return min(xs), min(ys), max(xs), max(ys)
    # polyline / polygon
    coords = [float(n) for n in attrs["points"].replace(",", " ").split()]
    xs, ys = coords[0::2], coords[1::2]
    return min(xs), min(ys), max(xs), max(ys)


def test_glyphs_present(tmp_path):
    """The 12 decorative glyph placements (density tick scales x3, resize
    arrow, shape icons x4, noise->arrow attenuverter marks x4) must all be
    baked into the glyphs layer. Each source asset's element count is fixed
    (see tests/fixtures/robotboy/assets/particules/*.svg), so the total
    baked-element count is deterministic; this test asserts both the total
    count and, via each baked element's bounding-box center, that every
    declared glyph position has at least one baked element sitting there."""
    out = tmp_path / "Particules.svg"
    generate(SPEC, str(out), theme_path=ROBOTBOY_THEME)

    with open(out, encoding="utf-8") as f:
        svg_text = f.read()

    body = parity._layer_body(svg_text, "glyphs")
    assert body is not None, "no glyphs layer found"

    matches = list(re.finditer(r"<(path|line|polyline|polygon)\b([^>]*?)/>", body, re.DOTALL))
    # atten-random.svg: 1 polyline + 1 polygon = 2 elements, x4 placements = 8
    # ticks-uneven.svg / ticks-even.svg: 5 lines each = 10
    # tick-tiny.svg: 1 line = 1
    # resize-arrow.svg: 1 line + 2 polygons = 3
    # shape-curve.svg: 1 line + 1 path = 2
    # shape-wave.svg: 1 path = 1
    # shape-caret.svg: 2 lines = 2
    # shape-pulse.svg: 1 path = 1
    expected_total = 8 + 10 + 1 + 3 + 2 + 1 + 2 + 1
    assert len(matches) == expected_total, len(matches)

    centers = []
    for m in matches:
        tag, attrs = m.group(1), parity._attrs(m.group(2))
        bbox = _element_bbox(tag, attrs)
        assert bbox is not None, (tag, attrs)
        minx, miny, maxx, maxy = bbox
        centers.append(((minx + maxx) / 2.0, (miny + maxy) / 2.0))

    parsed = spec.load_spec(SPEC)
    assert len(parsed.glyphs) == 12
    for g in parsed.glyphs:
        # Every declared glyph position must have at least one baked
        # element whose bbox center sits within 5mm of it (generously
        # covers each asset's own viewBox half-extent, the largest of which
        # -- atten-random's combined polyline+arrow -- spans ~4mm).
        assert any(
            math.hypot(cx - g.x, cy - g.y) < 5.0 for cx, cy in centers
        ), f"no baked element found near glyph at ({g.x}, {g.y})"


def test_panel_paths_match_worktree():
    """Secondary reference: if the v1 worktree's own regenerated Particules
    SVG is available locally (it lives outside this repo, under RobotBoy's
    git worktree, so it isn't always present), compare panel-layer label/
    title paths against it by BOUNDING BOX, not exact `d` string equality.

    Exact string equality does not hold and isn't expected to: this spec's
    label baselines are rounded/shared-per-row values measured from the
    hand-built REF (see particules.yaml's header comment), while the
    worktree's own per-label baselines came from its (slightly different)
    v1 band-math computation -- so corresponding glyphs sit a fraction of a
    mm apart even though they're the same word rendered in the same font at
    the same size. What SHOULD hold: the same 14 label/title glyph outlines
    appear, each just translated by a small amount. This test verifies
    exactly that -- same count, and every generated path's bounding box has
    a corresponding worktree path within a small translation tolerance --
    which is the "bounding-box comparison against the WORKTREE regen SVG"
    the task brief calls for.
    """
    if not os.path.exists(WORKTREE_REGEN):
        pytest.skip(
            "worktree regen SVG not present locally "
            f"({WORKTREE_REGEN}) -- secondary reference only, skipping")

    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "Particules.svg")
        generate(SPEC, out, theme_path=ROBOTBOY_THEME)
        got = parity.panel_paths_of(out)

    want = parity.panel_paths_of(WORKTREE_REGEN)
    assert len(got) == len(want) == 14, (len(got), len(want))

    def bbox_center(d):
        minx, miny, maxx, maxy = _path_bbox(d)
        return (minx + maxx) / 2.0, (miny + maxy) / 2.0

    got_centers = [bbox_center(d) for d in got]
    want_centers = [bbox_center(d) for d in want]

    # Greedy nearest-neighbor pairing (14 items -- no need for a full
    # assignment solver): each generated glyph's bbox center is matched to
    # its closest not-yet-claimed worktree glyph.
    remaining = list(enumerate(want_centers))
    max_delta = 0.0
    for gx, gy in got_centers:
        best_i, best_pt, best_dist = None, None, None
        for i, (wx, wy) in remaining:
            dist = math.hypot(gx - wx, gy - wy)
            if best_dist is None or dist < best_dist:
                best_i, best_pt, best_dist = i, (wx, wy), dist
        assert best_dist < 1.0, (
            f"generated glyph at ({gx:.3f}, {gy:.3f}) has no worktree "
            f"glyph within 1mm (closest is {best_dist:.3f}mm away at "
            f"{best_pt})")
        max_delta = max(max_delta, best_dist)
        remaining = [(i, pt) for i, pt in remaining if i != best_i]

    assert not remaining, f"unmatched worktree glyphs: {remaining}"
