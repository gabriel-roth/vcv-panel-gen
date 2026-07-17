import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import constants as c
from components import load_component_db
from glyphs import TextRenderer
from spec import parse_spec
from theme import resolve_theme, theme_from_mapping
from resolve import resolve
from validate import validate_svg
from svgdoc import build_svg

_DB = load_component_db()
_RENDERER = TextRenderer(c.FONT_PATH)


def _write_glyph(tmp_path, name="mark.svg"):
    p = tmp_path / name
    p.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-1 -1 2 2">'
        '<path d="M -0.5,0 L 0.5,0" stroke="#123456" stroke-width="0.1" fill="none"/>'
        '</svg>')
    return str(p)


def build(grids=None, elements=None, zones=None, glyphs=None, connectors=None,
          title=None, hp=15, side_margin=None, theme_over=None, base_dir="."):
    data = {
        "slug": "test_panel",
        "name": "Test Panel",
        "hp": hp,
        "elements": elements if elements is not None else
                    [{"name": "X_PARAM", "x": 10.0, "y": 10.0}],
    }
    if grids is not None:
        data["grids"] = grids
    if zones is not None:
        data["zones"] = zones
    if glyphs is not None:
        data["glyphs"] = glyphs
    if connectors is not None:
        data["connectors"] = connectors
    if title is not None:
        data["title"] = title
    if side_margin is not None:
        data["side_margin"] = side_margin
    spec = parse_spec(data, base_dir)
    over = {"screws": "none"}
    if theme_over:
        over.update(theme_over)
    theme = resolve_theme(None, theme_from_mapping(over, "test"))
    lay = resolve(spec, theme, _DB, _RENDERER, _RENDERER)
    svg = build_svg(lay, theme, _RENDERER, _RENDERER)
    return svg, lay, theme


# ---------------------------------------------------------------------------
# Root element
# ---------------------------------------------------------------------------

def test_root_attrs_mm_and_1to1_viewbox():
    svg, lay, _ = build(hp=15)
    w, h = lay.width, lay.height
    assert f'width="{w}mm"' in svg
    assert f'height="{h}mm"' in svg
    assert f'viewBox="0 0 {w} {h}"' in svg


# ---------------------------------------------------------------------------
# Layer presence / order
# ---------------------------------------------------------------------------

def test_layer_order_and_components_hidden():
    svg, lay, _ = build(elements=[
        {"name": "TIME_PARAM", "widget": "RoundBlackKnob", "x": 10.0, "y": 10.0},
        {"name": "IN_INPUT", "x": 20.0, "y": 10.0},
    ])
    panel_i = svg.index('id="panel"')
    components_i = svg.index('id="components"')
    assert panel_i < components_i
    # components layer must be hidden
    comp_open = svg[svg.index('inkscape:label="components"'):]
    assert 'style="display:none"' in comp_open.split(">")[0] + ">"


def test_values_layer_omitted_when_empty():
    svg, lay, _ = build(elements=[
        {"name": "TIME_PARAM", "widget": "RoundBlackKnob", "x": 10.0, "y": 10.0},
    ])
    assert 'id="values"' not in svg


def test_glyphs_layer_omitted_when_empty():
    svg, lay, _ = build(elements=[
        {"name": "TIME_PARAM", "widget": "RoundBlackKnob", "x": 10.0, "y": 10.0},
    ])
    assert 'id="glyphs"' not in svg


def test_glyphs_layer_present_and_ordered(tmp_path):
    src = _write_glyph(tmp_path)
    svg, lay, _ = build(
        elements=[{"name": "TIME_PARAM", "widget": "RoundBlackKnob", "x": 10.0, "y": 10.0}],
        glyphs=[{"src": os.path.basename(src), "at": [5.0, 5.0], "scale": 1.0}],
        base_dir=str(tmp_path))
    assert 'id="glyphs"' in svg
    panel_i = svg.index('id="panel"')
    glyphs_i = svg.index('id="glyphs"')
    components_i = svg.index('id="components"')
    assert panel_i < glyphs_i < components_i
    assert 'stroke="#123456"' in svg


# ---------------------------------------------------------------------------
# Components layer
# ---------------------------------------------------------------------------

def test_knob_component_id_and_fill():
    svg, lay, _ = build(elements=[
        {"name": "TIME_PARAM", "widget": "RoundBlackKnob", "x": 10.0, "y": 10.0},
    ])
    comp_section = svg[svg.index('id="components"'):]
    assert 'id="TIME_PARAM#RoundBlackKnob"' in comp_section
    m = re.search(r'<circle id="TIME_PARAM#RoundBlackKnob"[^/]*/>', comp_section)
    assert m is not None
    assert 'fill="#ff0000"' in m.group(0)
    assert 'r="2"' in m.group(0)


def test_input_component_fill():
    svg, lay, _ = build(elements=[
        {"name": "IN_INPUT", "x": 20.0, "y": 10.0},
    ])
    comp_section = svg[svg.index('id="components"'):]
    m = re.search(r'<circle id="IN_INPUT#PJ301MPort"[^/]*/>', comp_section)
    assert m is not None
    assert 'fill="#00ff00"' in m.group(0)


def test_rect_widget_uses_real_bounds_and_hash_widget_id():
    svg, lay, _ = build(elements=[
        {"name": "SCREEN", "kind": "widget",
         "rect": {"x": 1.5, "y": 10.4, "w": 57.96, "h": 22.35}},
    ])
    comp_section = svg[svg.index('id="components"'):]
    m = re.search(r'<rect id="SCREEN#Widget"[^/]*/>', comp_section)
    assert m is not None
    tag = m.group(0)
    assert 'x="1.5"' in tag
    assert 'y="10.4"' in tag
    assert 'width="57.96"' in tag
    assert 'height="22.35"' in tag
    assert 'fill="#ffff00"' in tag


# ---------------------------------------------------------------------------
# Text as paths, no <text>
# ---------------------------------------------------------------------------

def test_text_emitted_as_path_no_text_tag():
    svg, lay, _ = build(elements=[
        {"name": "A_PARAM", "x": 10.0, "y": 20.0,
         "label": {"text": "Drive", "dy": 8.2}},
    ])
    assert "<text" not in svg
    assert "<path" in svg


def test_label_fill_matches_resolved_text_color():
    svg, lay, theme = build(elements=[
        {"name": "A_PARAM", "x": 10.0, "y": 20.0,
         "label": {"text": "Drive", "dy": 8.2}},
    ])
    from theme import resolve_text_color
    color = resolve_text_color(theme)
    assert f'fill="{color}"' in svg


# ---------------------------------------------------------------------------
# Ring / values layer
# ---------------------------------------------------------------------------

def test_ring_text_lands_in_values_layer():
    svg, lay, _ = build(elements=[
        {"name": "GRID_PARAM", "widget": "RoundBlackKnob", "x": 40.0, "y": 50.0},
        {"ring": ["0", "4", "8"], "around": "GRID_PARAM", "gap": 0.65},
    ])
    values_start = svg.index('id="values"')
    next_layer = svg.index('id="components"')
    values_section = svg[values_start:next_layer]
    # 3 ring labels -> at least 3 path elements in the values layer
    assert values_section.count("<path") == 3


# ---------------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------------

def test_zone_rect_with_fill_opacity():
    svg, lay, _ = build(zones=[{"x": 1.0, "y": 2.0, "w": 20.0, "h": 15.0,
                                "fill": "#ffffff", "opacity": 0.14}])
    assert 'fill="#ffffff"' in svg
    assert 'fill-opacity="0.14"' in svg
    assert 'width="20.00"' in svg or 'width="20.0"' in svg


# ---------------------------------------------------------------------------
# Full validation
# ---------------------------------------------------------------------------

def test_validate_svg_passes():
    svg, lay, _ = build(elements=[
        {"name": "TIME_PARAM", "widget": "RoundBlackKnob", "x": 10.0, "y": 10.0,
         "label": {"text": "Time", "dy": -6.0}},
        {"name": "IN_INPUT", "x": 20.0, "y": 10.0},
        {"ring": ["0", "4", "8"], "around": "TIME_PARAM", "gap": 0.65},
    ], zones=[{"x": 0, "y": 0, "w": 20, "h": 20}])
    validate_svg(svg)  # must not raise


def test_no_forbidden_tags_or_transform():
    svg, lay, _ = build(elements=[
        {"name": "TIME_PARAM", "widget": "RoundBlackKnob", "x": 10.0, "y": 10.0},
    ])
    for tag in ("<text", "<style", "<image", "<filter", "<mask", "<clipPath"):
        assert tag not in svg
    assert "transform=" not in svg
