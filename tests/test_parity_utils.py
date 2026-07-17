"""Tests for tests/parity.py against the copied RobotBoy reference fixtures.

These fixtures (tests/fixtures/robotboy/reference/*.svg) are read-only copies
of the hardware-accurate panels from ~/Dev/RobotBoy/res/ -- Tasks 11-14 will
compare newly generated panels against them for exact component-center and
panel-artwork parity. This file just proves the parsing helpers themselves
are correct against both authoring dialects present in those fixtures (see
tests/parity.py's module docstring for the dialect differences).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import parity

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "fixtures", "robotboy", "reference")


def _fixture(name):
    return os.path.join(FIXTURES, name)


def test_components_of_mf20filter_knob():
    components = parity.components_of(_fixture("MF20Filter.svg"))
    assert components["CUTOFF_PARAM#RoundBigBlackKnob"] == ("circle", 11.8, 30.997)
    assert components["HP_CUTOFF_PARAM#RoundBigBlackKnob"] == ("circle", 39.0, 30.997)
    assert components["LP_CUTOFF_CV_PARAM#Trimpot"] == ("circle", 11.8, 46.997)
    assert components["LP_CUTOFF_INPUT#PJ301MPort"] == ("circle", 11.8, 59.347)


def test_components_of_mf20filter_is_nonempty_and_keyed_on_full_id():
    components = parity.components_of(_fixture("MF20Filter.svg"))
    assert len(components) == 15
    # ids carry the panel_gen "NAME#Widget" convention verbatim.
    assert all("#" in eid for eid in components)


def test_components_of_reads_rect_screen_widget():
    components = parity.components_of(_fixture("Lop.svg"))
    assert components["SCREEN#Widget"] == ("rect", 1.5, 10.4, 57.96, 22.35)


def test_components_of_particules_hand_built_dialect():
    # Particules.svg is hand-authored: the components layer is tagged via
    # inkscape:label (id="layer_components", not id="components"), ids have
    # no "#Widget" suffix, and circles carry a *true* radius rather than the
    # generator's fixed r="2" marker. components_of must still parse cx/cy
    # correctly and must not depend on r at all.
    components = parity.components_of(_fixture("Particules.svg"))
    assert components["TIME_PARAM"] == ("circle", 12.6, 42.088)
    assert components["DENSITY_PARAM"] == ("circle", 29.6, 42.088)
    assert components["OUT_L_OUTPUT"] == ("circle", 51.25, 114.3)


def test_panel_paths_of_mf20filter_is_nonempty_and_normalized():
    paths = parity.panel_paths_of(_fixture("MF20Filter.svg"))
    assert len(paths) > 0
    for d in paths:
        # normalized: no run of 2+ spaces, no leading/trailing whitespace.
        assert "  " not in d
        assert d == d.strip()
        # every number token rounded to at most 3 decimal places.
        for tok in __import__("re").findall(r"-?\d+\.\d+", d):
            assert len(tok.split(".")[1]) <= 3


def test_panel_paths_of_particules_panel_has_no_paths():
    # Particules' panel layer (layer_panel) only holds background/tint
    # rects; its engraved text lives in a separate "text" layer. Proves
    # panel_paths_of doesn't accidentally spill into sibling layers.
    paths = parity.panel_paths_of(_fixture("Particules.svg"))
    assert paths == []


_NO_LAYERS_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="50mm" height="50mm" '
    'viewBox="0 0 50 50">\n'
    '  <g inkscape:label="values" id="values"><path d="M1 1 L2 2"/></g>\n'
    '</svg>\n'
)


def test_panel_paths_of_missing_layer_returns_empty_list(tmp_path):
    svg_path = tmp_path / "no_panel.svg"
    svg_path.write_text(_NO_LAYERS_SVG)
    assert parity.panel_paths_of(str(svg_path)) == []


def test_components_of_missing_layer_returns_empty_dict(tmp_path):
    svg_path = tmp_path / "no_components.svg"
    svg_path.write_text(_NO_LAYERS_SVG)
    assert parity.components_of(str(svg_path)) == {}


def test_normalized_d_rounds_and_collapses_whitespace(tmp_path):
    svg_path = tmp_path / "panel_only.svg"
    svg_path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm" '
        'viewBox="0 0 10 10">\n'
        '  <g inkscape:label="panel" id="panel">\n'
        '    <path d="M1.123456   2.0000  L3.4999 4"/>\n'
        '  </g>\n'
        '</svg>\n'
    )
    paths = parity.panel_paths_of(str(svg_path))
    assert paths == ["M1.123 2 L3.5 4"]
