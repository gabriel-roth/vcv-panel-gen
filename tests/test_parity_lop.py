"""Parity test: Löp regenerated from the new-format spec
(tests/fixtures/robotboy/lop.yaml) must exactly match the shipped RobotBoy
reference SVG (tests/fixtures/robotboy/reference/Lop.svg) -- component
centers (the panel_gen->helper.py->C++ contract), the panel-layer label/
logo-title path geometry (proves identical font, size, casing, tracking, and
baseline placement, and an identical baked logo), the panel-layer non-path
shapes (zone tint, screws, connector bars -- see parity.panel_shapes_of), and
the values-layer ring-label paths around the Grid snap knob.

ROBOTBOY_THEME is a committed copy of ~/.config/vcv-panel-gen/theme.yaml (see
test_parity_mf20.py for the full rationale); Löp's spec has no theme overrides
(it ships the theme's default dark screws, unlike MF-20's silver ones).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import parity
from panelgen import generate

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "robotboy")
SPEC = os.path.join(FIXTURES, "lop.yaml")
REF = os.path.join(FIXTURES, "reference", "Lop.svg")
ROBOTBOY_THEME = os.path.join(FIXTURES, "theme.yaml")


@pytest.fixture(autouse=True)
def _require_fonts():
    # Skip loudly on machines missing Futura / Shuttleblock Test Demi
    # instead of failing with an opaque wall of path-geometry diffs (see
    # parity.require_robotboy_fonts's docstring).
    parity.require_robotboy_fonts()


def test_component_centers_exact(tmp_path):
    out = tmp_path / "Lop.svg"
    report = generate(SPEC, str(out), theme_path=ROBOTBOY_THEME)
    assert not report.errors, report.errors

    got = parity.components_of(str(out))
    want = parity.components_of(REF)

    assert got.keys() == want.keys()
    for k in want:
        assert got[k][0] == want[k][0], k  # same shape kind (circle/rect)
        assert got[k][1:] == pytest.approx(want[k][1:], abs=1e-3), k


def test_panel_paths_match(tmp_path):
    out = tmp_path / "Lop.svg"
    generate(SPEC, str(out), theme_path=ROBOTBOY_THEME)

    got = sorted(parity.panel_paths_of(str(out)))
    want = sorted(parity.panel_paths_of(REF))
    assert got == want


def test_panel_shapes_match(tmp_path):
    """Zone tint, screw markers, and connector bars -- the panel-layer
    <rect>/<circle> geometry that panel_paths_of (paths only) can't see."""
    out = tmp_path / "Lop.svg"
    generate(SPEC, str(out), theme_path=ROBOTBOY_THEME)

    got = sorted(parity.panel_shapes_of(str(out)))
    want = sorted(parity.panel_shapes_of(REF))
    assert got == want


def test_ring_values_match(tmp_path):
    """The Grid snap knob's value-ring labels (Ø/4/8/16/32/64) live in the
    `values` layer, not `panel` -- panel_paths_of never sees them. Compare
    them the same way panel_paths_of compares panel paths: normalized `d`
    string equality. (The generic ring math in resolve.py is a direct port of
    v1's, minus dodge logic that Löp's ring doesn't need -- exact `d` strings
    matched on the first try, so no bbox fallback was needed here.)"""
    out = tmp_path / "Lop.svg"
    generate(SPEC, str(out), theme_path=ROBOTBOY_THEME)

    got = sorted(parity.values_paths_of(str(out)))
    want = sorted(parity.values_paths_of(REF))
    assert got == want
