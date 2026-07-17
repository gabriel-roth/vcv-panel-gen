import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import constants as c
from components import load_component_db
from glyphs import TextRenderer
from spec import parse_spec
from theme import resolve_theme, theme_from_mapping
from resolve import resolve
from checks import run_checks, Report

_DB = load_component_db()
_RENDERER = TextRenderer(c.FONT_PATH)


def run(grids=None, elements=None, zones=None, glyphs=None, connectors=None,
        overlaps_ok=None, title=None, hp=15, side_margin=None, theme_over=None,
        base_dir="."):
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
    if overlaps_ok is not None:
        data["overlaps_ok"] = overlaps_ok
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
    return run_checks(lay, spec, _DB, _RENDERER)


def has_overlap(warnings, a, b):
    return any(w.startswith("OVERLAP") and a in w and b in w for w in warnings)


# ---------------------------------------------------------------------------
# Bounds errors
# ---------------------------------------------------------------------------

def test_offpanel_circle_errors():
    # RoundBlackKnob (default for _PARAM) has true diameter 9.6mm (r=4.8);
    # centered at x=2.0 its left edge sits at -2.8mm, off the panel.
    report = run(elements=[{"name": "EDGE_PARAM", "x": 2.0, "y": 10.0}])
    assert any("EDGE_PARAM" in e and "mm" in e for e in report.errors)


def test_offpanel_text_errors():
    # cap_height(LABEL_FONT_MM) ~= 2.1mm; baseline at y=1.0 puts the box top
    # at -1.1mm, off the panel.
    report = run(elements=[
        {"name": "X_PARAM", "x": 40.0, "y": 60.0},
        {"text": "Hi", "x": 40.0, "y": 1.0},
    ])
    assert any("text:Hi" in e and "mm" in e for e in report.errors)


def test_offpanel_element_is_quiet_when_in_bounds():
    report = run(elements=[{"name": "MID_PARAM", "x": 40.0, "y": 60.0}])
    assert report.errors == []


# ---------------------------------------------------------------------------
# Overlap warnings
# ---------------------------------------------------------------------------

def test_two_overlapping_knobs_warn_with_depth():
    # Two RoundBlackKnobs (r=4.8 each) 5.0mm apart: depth = 4.8+4.8-5.0 = 4.6.
    report = run(elements=[
        {"name": "A_PARAM", "x": 30.0, "y": 60.0},
        {"name": "B_PARAM", "x": 35.0, "y": 60.0},
    ])
    assert has_overlap(report.warnings, "A_PARAM", "B_PARAM")
    match = [w for w in report.warnings if "A_PARAM" in w and "B_PARAM" in w][0]
    assert "depth 4.60mm" in match


def test_non_overlapping_knobs_are_quiet():
    report = run(elements=[
        {"name": "A_PARAM", "x": 20.0, "y": 60.0},
        {"name": "B_PARAM", "x": 50.0, "y": 60.0},
    ])
    assert report.warnings == []
    assert report.errors == []


def test_text_over_knob_warns():
    report = run(elements=[
        {"name": "A_PARAM", "x": 30.0, "y": 60.0},
        {"text": "X", "x": 30.0, "y": 60.0},
    ])
    assert has_overlap(report.warnings, "A_PARAM", "text:X")


def test_zones_never_warn():
    # A zone fully covering an isolated component produces no warnings --
    # zones have no extent and never participate in overlap checks.
    report = run(
        elements=[{"name": "A_PARAM", "x": 30.0, "y": 60.0}],
        zones=[{"x": 10.0, "y": 40.0, "w": 40.0, "h": 40.0}],
    )
    assert report.warnings == []


# ---------------------------------------------------------------------------
# Suppression via overlaps_ok
# ---------------------------------------------------------------------------

def test_suppression_by_pair_forward_order():
    report = run(elements=[
        {"name": "A_PARAM", "x": 30.0, "y": 60.0},
        {"name": "B_PARAM", "x": 35.0, "y": 60.0},
    ], overlaps_ok=[["A_PARAM", "B_PARAM"]])
    assert not has_overlap(report.warnings, "A_PARAM", "B_PARAM")


def test_suppression_by_pair_reverse_order():
    report = run(elements=[
        {"name": "A_PARAM", "x": 30.0, "y": 60.0},
        {"name": "B_PARAM", "x": 35.0, "y": 60.0},
    ], overlaps_ok=[["B_PARAM", "A_PARAM"]])
    assert not has_overlap(report.warnings, "A_PARAM", "B_PARAM")


def test_suppression_by_singleton():
    # A singleton suppresses every overlap involving that element, whatever
    # is on the other side (here: text over a knob).
    report = run(elements=[
        {"name": "A_PARAM", "x": 30.0, "y": 60.0},
        {"text": "X", "x": 30.0, "y": 60.0},
    ], overlaps_ok=[["A_PARAM"]])
    assert not has_overlap(report.warnings, "A_PARAM", "text:X")


def test_suppression_does_not_hide_unrelated_overlaps():
    report = run(elements=[
        {"name": "A_PARAM", "x": 30.0, "y": 60.0},
        {"name": "B_PARAM", "x": 35.0, "y": 60.0},
        {"name": "C_PARAM", "x": 30.0, "y": 60.0},
    ], overlaps_ok=[["A_PARAM", "B_PARAM"]])
    assert not has_overlap(report.warnings, "A_PARAM", "B_PARAM")
    # A_PARAM and C_PARAM sit on top of each other and are not suppressed.
    assert has_overlap(report.warnings, "A_PARAM", "C_PARAM")


# ---------------------------------------------------------------------------
# Unknown widget class
# ---------------------------------------------------------------------------

def test_title_logo_uses_real_width_not_height_as_both_dims(tmp_path):
    # A wide logo (viewBox 40x5, aspect 8): cap_height(5.0mm title size) is
    # 3.5mm, so the real drawn width is 3.5 * 8 = 28mm (half-width 14mm).
    # Centered at x=10 on a 76.2mm-wide panel, the real box's left edge sits
    # at -4mm -- off panel. Using height (3.5mm) as a stand-in for width
    # would wrongly report this title as in-bounds (half-width 1.75mm).
    logo_path = tmp_path / "wide-logo.svg"
    logo_path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 5">'
        '<path d="M0 0 L40 0 L40 5 L0 5 Z"/></svg>')
    report = run(
        elements=[{"name": "X_PARAM", "x": 40.0, "y": 60.0}],
        title={"logo": str(logo_path), "x": 10.0, "y": 3.5},
    )
    assert any("title" in e and "mm" in e for e in report.errors)


def test_unknown_widget_class_errors():
    report = run(elements=[
        {"name": "MYSTERY_WIDGET", "kind": "widget", "widget": "NoSuchWidget123",
         "x": 40.0, "y": 60.0},
    ])
    assert any("MYSTERY_WIDGET" in e and "NoSuchWidget123" in e
               for e in report.errors)
