"""Parity test: Loooop regenerated from the new-format spec
(tests/fixtures/robotboy/loooop.yaml) must exactly match the shipped
RobotBoy reference SVG (tests/fixtures/robotboy/reference/Loooop.svg) --
component centers (the panel_gen->helper.py->C++ contract), the panel-layer
label/title path geometry (proves identical font, size, casing, tracking,
and baseline placement), the panel-layer non-path shapes (four head-tint
zones, screws, 24 knob->CV connector bars -- see parity.panel_shapes_of),
and the values-layer ring-label paths around the Grid snap knob.

ROBOTBOY_THEME is a committed copy of ~/.config/vcv-panel-gen/theme.yaml (see
test_parity_mf20.py for the full rationale); Loooop's spec has no theme
overrides (it ships the theme's default dark screws, like Löp).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import parity
from panelgen import generate

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "robotboy")
SPEC = os.path.join(FIXTURES, "loooop.yaml")
REF = os.path.join(FIXTURES, "reference", "Loooop.svg")
ROBOTBOY_THEME = os.path.join(FIXTURES, "theme.yaml")


def test_component_centers_exact(tmp_path):
    out = tmp_path / "Loooop.svg"
    report = generate(SPEC, str(out), theme_path=ROBOTBOY_THEME)
    assert not report.errors, report.errors

    got = parity.components_of(str(out))
    want = parity.components_of(REF)

    assert got.keys() == want.keys()
    for k in want:
        assert got[k][0] == want[k][0], k  # same shape kind (circle/rect)
        assert got[k][1:] == pytest.approx(want[k][1:], abs=1e-3), k


def test_panel_paths_match(tmp_path):
    out = tmp_path / "Loooop.svg"
    generate(SPEC, str(out), theme_path=ROBOTBOY_THEME)

    got = sorted(parity.panel_paths_of(str(out)))
    want = sorted(parity.panel_paths_of(REF))
    assert got == want


def test_panel_shapes_match(tmp_path):
    """Four head-tint zones, screw markers, and 24 knob->CV connector bars --
    the panel-layer <rect>/<circle> geometry that panel_paths_of (paths only)
    can't see."""
    out = tmp_path / "Loooop.svg"
    generate(SPEC, str(out), theme_path=ROBOTBOY_THEME)

    got = sorted(parity.panel_shapes_of(str(out)))
    want = sorted(parity.panel_shapes_of(REF))
    assert got == want


def test_ring_values_match(tmp_path):
    """The Grid snap knob's value-ring labels (Ø/4/8/16/32/64) live in the
    `values` layer, not `panel` -- panel_paths_of never sees them. Compare
    them the same way panel_paths_of compares panel paths: normalized `d`
    string equality (same mechanism verified for Löp's identical ring)."""
    out = tmp_path / "Loooop.svg"
    generate(SPEC, str(out), theme_path=ROBOTBOY_THEME)

    got = sorted(parity.values_paths_of(str(out)))
    want = sorted(parity.values_paths_of(REF))
    assert got == want
