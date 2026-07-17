"""Parity test: MF-20 regenerated from the new-format spec
(tests/fixtures/robotboy/mf20filter.yaml) must exactly match the shipped
RobotBoy reference SVG (tests/fixtures/robotboy/reference/MF20Filter.svg) --
both in component centers (the panel_gen->helper.py->C++ contract) and in
the panel-layer label/title path geometry (proves identical font, size,
casing, tracking, and baseline placement).

ROBOTBOY_THEME is a committed copy of ~/.config/vcv-panel-gen/theme.yaml
(casing upper, background #3d3d3d, white text, dark screws, Futura +
Shuttleblock Test Demi) so these tests are deterministic regardless of the
machine's real user config; the spec itself overrides screws to "light" to
match this module's silver screws.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import parity
from panelgen import generate

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "robotboy")
SPEC = os.path.join(FIXTURES, "mf20filter.yaml")
REF = os.path.join(FIXTURES, "reference", "MF20Filter.svg")
ROBOTBOY_THEME = os.path.join(FIXTURES, "theme.yaml")


@pytest.fixture(autouse=True)
def _require_fonts():
    # Skip loudly on machines missing Futura / Shuttleblock Test Demi
    # instead of failing with an opaque wall of path-geometry diffs (see
    # parity.require_robotboy_fonts's docstring).
    parity.require_robotboy_fonts()


def test_component_centers_exact(tmp_path):
    out = tmp_path / "MF20Filter.svg"
    report = generate(SPEC, str(out), theme_path=ROBOTBOY_THEME)
    assert not report.errors, report.errors

    got = parity.components_of(str(out))
    want = parity.components_of(REF)

    assert got.keys() == want.keys()
    for k in want:
        assert got[k][0] == want[k][0], k  # same shape kind (circle/rect)
        assert got[k][1:] == pytest.approx(want[k][1:], abs=1e-3), k


def test_panel_paths_match(tmp_path):
    out = tmp_path / "MF20Filter.svg"
    generate(SPEC, str(out), theme_path=ROBOTBOY_THEME)

    got = sorted(parity.panel_paths_of(str(out)))
    want = sorted(parity.panel_paths_of(REF))
    assert got == want


def test_panel_shapes_match(tmp_path):
    """Zone tint, screw markers, and connector bars -- the panel-layer
    <rect>/<circle> geometry that panel_paths_of (paths only) can't see.
    MF-20's reference zone tint is hand-tuned and encodes fill via a
    `style="fill:#8a5a2c;fill-opacity:0.25;stroke:none"` attribute rather
    than discrete fill/fill-opacity attributes -- panel_shapes_of normalizes
    both encodings before comparing (see its docstring)."""
    out = tmp_path / "MF20Filter.svg"
    generate(SPEC, str(out), theme_path=ROBOTBOY_THEME)

    got = sorted(parity.panel_shapes_of(str(out)))
    want = sorted(parity.panel_shapes_of(REF))
    assert got == want
