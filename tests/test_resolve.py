import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import constants as c
from components import load_component_db
from glyphs import TextRenderer
from spec import parse_spec
from theme import resolve_theme, theme_from_mapping
from resolve import (
    resolve, ResolveError, Layout, PlacedComponent, PlacedText, PlacedBar,
    PlacedScrew, PlacedLogo,
)

_DB = load_component_db()
_RENDERER = TextRenderer(c.FONT_PATH)


def resolve_min(grids=None, elements=None, zones=None, glyphs=None,
                 connectors=None, title=None, hp=15, side_margin=None,
                 theme_over=None, base_dir="."):
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
    return resolve(spec, theme, _DB, _RENDERER, _RENDERER)


# ---------------------------------------------------------------------------
# Grid column math
# ---------------------------------------------------------------------------

def test_even_columns():
    lay = resolve_min(grids={"g": {"cols": {"count": 4, "from": 12.6, "to": 63.6},
                                   "rows": {"r": 40.0}}},
                      elements=[{"name": f"K{i}_PARAM", "grid": "g", "col": i, "row": "r"}
                                for i in (1, 2, 3, 4)])
    assert [round(comp.x, 3) for comp in lay.components] == [12.6, 29.6, 46.6, 63.6]


def test_count_only_span_uses_side_margin():
    # hp=15 -> width = 15 * 5.08 = 76.2; default side_margin = 8.0
    lay = resolve_min(grids={"g": {"cols": {"count": 3},
                                   "rows": {"r": 40.0}}},
                      elements=[{"name": f"K{i}_PARAM", "grid": "g", "col": i, "row": "r"}
                                for i in (1, 2, 3)],
                      hp=15)
    width = 15 * c.HP_MM
    expected = [8.0, width / 2.0, width - 8.0]
    assert [round(comp.x, 3) for comp in lay.components] == [round(v, 3) for v in expected]


def test_explicit_cols_verbatim():
    lay = resolve_min(grids={"g": {"cols": [11.9, 38.1, 59.845],
                                   "rows": {"r": 40.0}}},
                      elements=[{"name": f"K{i}_PARAM", "grid": "g", "col": i, "row": "r"}
                                for i in (1, 2, 3)])
    assert [comp.x for comp in lay.components] == [11.9, 38.1, 59.845]


def test_mixed_grid_x_absolute_y():
    lay = resolve_min(
        grids={"g": {"cols": {"count": 2, "from": 10.0, "to": 20.0},
                     "rows": {"r": 40.0}}},
        elements=[{"name": "A_PARAM", "grid": "g", "col": 1, "y": 99.0}])
    comp = lay.components[0]
    assert comp.x == 10.0
    assert comp.y == 99.0


def test_dx_dy_applied():
    lay = resolve_min(elements=[{"name": "A_PARAM", "x": 10.0, "y": 20.0,
                                 "dx": 1.5, "dy": -2.0}])
    comp = lay.components[0]
    assert comp.x == 11.5
    assert comp.y == 18.0


# ---------------------------------------------------------------------------
# Widget default / component passthrough
# ---------------------------------------------------------------------------

def test_default_widget_per_kind():
    lay = resolve_min(elements=[
        {"name": "A_PARAM", "x": 10.0, "y": 10.0},
        {"name": "B_INPUT", "x": 20.0, "y": 10.0},
        {"name": "C_OUTPUT", "x": 30.0, "y": 10.0},
        {"name": "D_LIGHT", "x": 40.0, "y": 10.0},
    ])
    widgets = {comp.name: comp.widget for comp in lay.components}
    assert widgets["A_PARAM"] == "RoundBlackKnob"
    assert widgets["B_INPUT"] == "PJ301MPort"
    assert widgets["C_OUTPUT"] == "PJ301MPort"
    assert widgets["D_LIGHT"] == "MediumLight<RedLight>"


def test_rect_widget_center_and_rect_passthrough():
    lay = resolve_min(elements=[
        {"name": "SCREEN", "kind": "widget",
         "rect": {"x": 1.5, "y": 10.4, "w": 57.96, "h": 22.35}},
    ])
    comp = lay.components[0]
    assert comp.rect.x == 1.5 and comp.rect.w == 57.96
    assert round(comp.x, 3) == round(1.5 + 57.96 / 2.0, 3)
    assert round(comp.y, 3) == round(10.4 + 22.35 / 2.0, 3)


# ---------------------------------------------------------------------------
# Attached label sugar / text elements
# ---------------------------------------------------------------------------

def test_attached_label_placement():
    lay = resolve_min(elements=[
        {"name": "A_PARAM", "x": 10.0, "y": 20.0,
         "label": {"text": "Drive", "dy": 8.2}},
    ])
    labels = [t for t in lay.texts if t.text == "Drive"]
    assert len(labels) == 1
    lb = labels[0]
    assert lb.x == 10.0
    assert lb.y == 28.2
    assert lb.size == c.LABEL_FONT_MM
    assert lb.layer == "panel"


def test_text_element_defaults_and_casing():
    lay = resolve_min(theme_over={"casing": "upper", "screws": "none"},
                       elements=[
        {"name": "A_PARAM", "x": 10.0, "y": 20.0},
        {"text": "time", "x": 25.0, "y": 30.0},
    ])
    texts = [t for t in lay.texts if t.x == 25.0]
    assert len(texts) == 1
    t = texts[0]
    assert t.text == "TIME"
    assert t.size == c.LABEL_FONT_MM
    assert t.tracking == 0.0
    assert t.layer == "panel"


# ---------------------------------------------------------------------------
# Value rings
# ---------------------------------------------------------------------------

def test_ring_labels_count_symmetry_and_layer():
    lay = resolve_min(elements=[
        {"name": "GRID_PARAM", "widget": "RoundBlackKnob", "x": 40.0, "y": 50.0},
        {"ring": ["0", "4", "8"], "around": "GRID_PARAM", "gap": 0.65},
    ])
    ring_texts = [t for t in lay.texts if t.layer == "values"]
    assert len(ring_texts) == 3
    assert {t.text for t in ring_texts} == {"0", "4", "8"}
    by_text = {t.text: t for t in ring_texts}
    # middle label (theta = 0, straight up) sits on the knob's x axis
    assert abs(by_text["4"].x - 40.0) < 1e-6
    assert by_text["4"].y < 50.0
    # side labels are symmetric about cx and share the same y
    left, right = by_text["0"], by_text["8"]
    assert abs((left.x - 40.0) + (right.x - 40.0)) < 1e-6
    assert abs(left.y - right.y) < 1e-6
    assert left.size == c.VALUE_FONT_MM


def test_ring_unknown_widget_raises():
    with pytest.raises(ResolveError):
        resolve_min(elements=[
            {"name": "GRID_PARAM", "kind": "widget", "x": 40.0, "y": 50.0},
            {"ring": ["0", "4", "8"], "around": "GRID_PARAM", "gap": 0.65},
        ])


# ---------------------------------------------------------------------------
# Connectors
# ---------------------------------------------------------------------------

def test_connector_bar_trimmed_by_radii():
    lay = resolve_min(elements=[
        {"name": "A_PARAM", "widget": "RoundBlackKnob", "x": 20.0, "y": 20.0},
        {"name": "B_PARAM", "widget": "RoundBlackKnob", "x": 20.0, "y": 40.0},
    ], connectors=[["A_PARAM", "B_PARAM"]])
    assert len(lay.bars) == 1
    bar = lay.bars[0]
    r = 9.6 / 2.0
    assert bar.x == 20.0
    assert round(bar.y1, 3) == round(20.0 + r, 3)
    assert round(bar.y2, 3) == round(40.0 - r, 3)
    assert bar.width == c.CONNECT_LINE_WIDTH
    assert bar.color == c.CONNECT_LINE_COLOR


def test_connector_requires_same_x():
    with pytest.raises(ResolveError):
        resolve_min(elements=[
            {"name": "A_PARAM", "widget": "RoundBlackKnob", "x": 20.0, "y": 20.0},
            {"name": "B_PARAM", "widget": "RoundBlackKnob", "x": 25.0, "y": 40.0},
        ], connectors=[["A_PARAM", "B_PARAM"]])


# ---------------------------------------------------------------------------
# Screws
# ---------------------------------------------------------------------------

def test_screws_none():
    lay = resolve_min(theme_over={"screws": "none"})
    assert lay.screws == []


def test_screws_dark_positions():
    lay = resolve_min(theme_over={"screws": "dark"}, hp=15)
    width = 15 * c.HP_MM
    assert len(lay.screws) == 4
    xs = sorted({round(s.x, 3) for s in lay.screws})
    ys = sorted({round(s.y, 3) for s in lay.screws})
    assert xs == [round(c.MOUNT_INSET_X, 3), round(width - c.MOUNT_INSET_X, 3)]
    assert ys == [round(c.MOUNT_Y_TOP, 3), round(c.MOUNT_Y_BOTTOM, 3)]


# ---------------------------------------------------------------------------
# Title
# ---------------------------------------------------------------------------

def test_title_default_centering():
    lay = resolve_min(hp=15)
    width = 15 * c.HP_MM
    assert isinstance(lay.title, PlacedText)
    assert lay.title.x == width / 2.0
    cap = _RENDERER.cap_height(c.TITLE_FONT_MM)
    expected_baseline = (c.TITLE_BAND_MM + cap) / 2.0
    assert abs(lay.title.y - expected_baseline) < 1e-6
    assert lay.title.text == "Test Panel"


def test_title_valign_baseline():
    lay = resolve_min(hp=15, title={"valign": "baseline"})
    assert abs(lay.title.y - (c.TITLE_FONT_MM + 1.0)) < 1e-6


def test_title_xy_and_dxdy_overrides():
    lay = resolve_min(hp=15, title={"x": 5.0, "y": 6.0, "dx": 1.0, "dy": 2.0})
    assert lay.title.x == 6.0
    assert lay.title.y == 8.0


# ---------------------------------------------------------------------------
# Zones / glyphs passthrough
# ---------------------------------------------------------------------------

def test_zones_pass_through():
    lay = resolve_min(zones=[{"x": 0, "y": 0, "w": 20, "h": 20}])
    assert len(lay.zones) == 1
    assert lay.zones[0].w == 20


def test_zones_default_empty_list():
    lay = resolve_min()
    assert lay.zones == []
    assert lay.glyphs == []
