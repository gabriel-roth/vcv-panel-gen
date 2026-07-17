"""Tests for mm_sync.py, ported from v1's tests/test_mm_sync.py.

v1's version built its fixture SVGs through the v1 spec/layout pipeline
(PanelSpec/Row/Item/layout_panel/build_svg), which v2 replaced wholesale.
mm_sync.py itself has zero v1-specific imports (argparse, re, sys,
xml.etree.ElementTree, dataclasses, yaml only), so it was ported verbatim;
only the *fixtures* needed rework here.

Fixture strategy:
  - `_svg()` below drives the real v2 pipeline end-to-end
    (spec.parse_spec -> resolve.resolve -> svgdoc.build_svg) to prove
    mm_sync's contract — the `NAME#Widget` id convention and KIND_BY_FILL
    colors in the hidden "components" layer — still matches what v2
    actually emits.
  - `_hand_authored_svg()` builds a minimal SVG string by hand, mirroring
    svgdoc.py's exact components-layer markup, to prove mm_sync only
    depends on that hidden layer's contract (not on the rest of the
    document v2 happens to emit around it).
  - The `_info.hh` HEADER text is copied verbatim from v1's test file: it's
    plain text with no v1 API involved.

Behavior -> test mapping (old v1 test name -> new test name):
  test_derive_enum_name_by_kind_and_widget       -> test_derive_enum_name_by_kind_and_widget (verbatim body)
  test_derive_enum_name_unknown_param_widget_raises -> test_derive_enum_name_unknown_param_widget_raises (verbatim body)
  test_derive_enum_name_snap_knobs               -> test_derive_enum_name_snap_knobs (verbatim body)
  test_sync_updates_circle_and_rect_coords       -> test_sync_updates_circle_and_rect_coords
  test_sync_map_overrides_and_null               -> test_sync_map_overrides_and_null
  test_mm_aspect_narrows_and_recenters           -> test_mm_aspect_narrows_and_recenters
  test_mm_aspect_numeric_form                    -> test_mm_aspect_numeric_form
  test_mm_aspect_on_circle_raises                -> test_mm_aspect_on_circle_raises
  test_mm_aspect_unknown_key_raises               -> test_mm_aspect_unknown_key_raises
  test_mm_aspect_missing_id_raises                -> test_mm_aspect_missing_id_raises
  test_mm_aspect_bad_ratio_raises                 -> test_mm_aspect_bad_ratio_raises
  test_mm_aspect_null_id_raises                   -> test_mm_aspect_null_id_raises
  test_sync_unmatched_svg_component_raises        -> test_sync_unmatched_svg_component_raises
  test_sync_count_mismatch_raises                 -> test_sync_count_mismatch_raises
  test_sync_map_unknown_enum_raises                -> test_sync_map_unknown_enum_raises
  test_cli_writes_header_in_place                 -> test_cli_writes_header_in_place
  test_cli_failure_leaves_header_untouched        -> test_cli_failure_leaves_header_untouched
  test_cli_map_file                               -> test_cli_map_file
  test_cli_map_file_with_aspect                    -> test_cli_map_file_with_aspect
  test_strict_requires_null_declarations           -> test_strict_requires_null_declarations
  test_cli_strict_flag                             -> test_cli_strict_flag
  _svg_with_vcv_only_knob / test_ignore_lets_vcv_only_control_pass -> test_ignore_lets_vcv_only_control_pass
  test_ignore_unknown_svg_id_raises                -> test_ignore_unknown_svg_id_raises

Plus one new test (test_sync_against_hand_authored_svg) using the
hand-authored SVG string, added for extra confidence that mm_sync's
contract is the hidden-layer markup itself, not incidental v2 pipeline
output shape.
"""
import os
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mm_sync as M
from components import load_component_db
from glyphs import TextRenderer
from spec import parse_spec
from theme import resolve_theme, theme_from_mapping
from resolve import resolve
from svgdoc import build_svg
import constants as c

_DB = load_component_db()
_RENDERER = TextRenderer(c.FONT_PATH)


# --- enum-name derivation (the generator's old naming convention) ---
# Pure unit tests of M.derive_enum_name: no pipeline involved, ported
# verbatim from v1.

def test_derive_enum_name_by_kind_and_widget():
    cases = [
        ("SPEED1_PARAM", "#ff0000", "RoundBlackKnob", "Speed1Knob"),
        ("TIME_TRIM_PARAM", "#ff0000", "Trimpot", "TimeTrimKnob"),
        ("RECORD_PARAM", "#ff0000", "VCVButton", "RecordButton"),
        ("MODE_PARAM", "#ff0000", "CKSS", "ModeSwitch"),
        ("SPEED1_CV_INPUT", "#00ff00", "PJ301MPort", "Speed1CvIn"),
        ("MIX_L_OUTPUT", "#0000ff", "PJ301MPort", "MixLOut"),
        ("CLIP_LIGHT", "#ff00ff", "MediumLight<RedLight>", "ClipLight"),
        ("SCREEN", "#ffff00", "Widget", "Screen"),
    ]
    for name, fill, widget, want in cases:
        assert M.derive_enum_name(name, fill, widget) == want


def test_derive_enum_name_unknown_param_widget_raises():
    with pytest.raises(M.MMSyncError, match="MysteryFader"):
        M.derive_enum_name("X_PARAM", "#ff0000", "MysteryFader")


def test_derive_enum_name_snap_knobs():
    assert M.derive_enum_name("GRID_PARAM", "#ff0000", "RoundBlackSnapKnob") == "GridKnob"
    assert M.derive_enum_name("TRIM_PARAM", "#ff0000", "RoundSmallBlackKnob") == "TrimKnob"


# --- fixtures: a real v2-generated SVG + a hand-written header ---
#
# Explicit x/y (not grid/col) positions pass straight through
# resolve._resolve_position unchanged (x + dx, dx defaults to 0), and a
# `rect:` element's x/y/w/h are used as-is by resolve/svgdoc, so the values
# below are exactly what will land in the SVG's components layer -- no need
# to reverse-engineer them from the returned Layout.

SCREEN_RECT = {"x": 5.0, "y": 6.0, "w": 50.0, "h": 20.0}
SPEED_XY = (20.0, 40.0)
SPEED_CV_XY = (35.0, 40.0)
AUDIO_IN_XY = (10.0, 100.0)
AUDIO_OUT_XY = (30.0, 100.0)


def _spec_elements(extra=None):
    elements = [
        {"name": "SCREEN", "kind": "widget", "rect": dict(SCREEN_RECT)},
        {"name": "SPEED_PARAM", "x": SPEED_XY[0], "y": SPEED_XY[1]},
        {"name": "SPEED_CV_INPUT", "x": SPEED_CV_XY[0], "y": SPEED_CV_XY[1]},
        {"name": "AUDIO_INPUT", "x": AUDIO_IN_XY[0], "y": AUDIO_IN_XY[1]},
        {"name": "AUDIO_OUTPUT", "x": AUDIO_OUT_XY[0], "y": AUDIO_OUT_XY[1]},
    ]
    if extra:
        elements.extend(extra)
    return elements


def _svg(tmp_path, extra_elements=None, hp=12, name="T"):
    """Build a real panel SVG end-to-end through the v2 pipeline:
    spec.parse_spec -> resolve.resolve -> svgdoc.build_svg."""
    data = {"slug": name, "name": name, "hp": hp,
            "elements": _spec_elements(extra_elements)}
    spec = parse_spec(data, ".")
    theme = resolve_theme(None, theme_from_mapping({"screws": "none"}, "test"))
    lay = resolve(spec, theme, _DB, _RENDERER, _RENDERER)
    svg = build_svg(lay, theme, _RENDERER, _RENDERER)
    p = tmp_path / f"{name}.svg"
    p.write_text(svg)
    return str(p)


def _hand_authored_svg(tmp_path):
    """A minimal SVG string authored by hand, mirroring svgdoc.py's exact
    components-layer markup (NAME#Widget ids, KIND_BY_FILL colors, circle
    cx/cy vs rect x/y/width/height) without running the v2 pipeline."""
    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="60.96mm" height="128.5mm" viewBox="0 0 60.96 128.5">
  <g inkscape:label="panel" inkscape:groupmode="layer" id="panel" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape">
    <rect x="0" y="0" width="60.96" height="128.5" fill="#222222"/>
  </g>
  <g inkscape:label="components" inkscape:groupmode="layer" id="components" style="display:none" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape">
    <rect id="SCREEN#Widget" x="{SCREEN_RECT['x']}" y="{SCREEN_RECT['y']}" width="{SCREEN_RECT['w']}" height="{SCREEN_RECT['h']}" fill="#ffff00"/>
    <circle id="SPEED_PARAM#RoundBlackKnob" cx="{SPEED_XY[0]}" cy="{SPEED_XY[1]}" r="2" fill="#ff0000"/>
    <circle id="SPEED_CV_INPUT#PJ301MPort" cx="{SPEED_CV_XY[0]}" cy="{SPEED_CV_XY[1]}" r="2" fill="#00ff00"/>
    <circle id="AUDIO_INPUT#PJ301MPort" cx="{AUDIO_IN_XY[0]}" cy="{AUDIO_IN_XY[1]}" r="2" fill="#00ff00"/>
    <circle id="AUDIO_OUTPUT#PJ301MPort" cx="{AUDIO_OUT_XY[0]}" cy="{AUDIO_OUT_XY[1]}" r="2" fill="#0000ff"/>
  </g>
</svg>
"""
    p = tmp_path / "T_hand.svg"
    p.write_text(svg)
    return str(p)


HEADER = textwrap.dedent("""\
    #pragma once
    #include "CoreModules/elements/element_info.hh"
    #include <array>

    namespace MetaModule
    {

    struct TInfo : ModuleInfoBase {
        static constexpr std::string_view slug{"T"};
        using enum Coords;

        static constexpr std::array<Element, 6> Elements{{
            Knob{{{1.000f, 2.000f, Center, "Speed", "", 12.f, 12.f}, 0.5f}},
            AltParamChoice{{{0.f, 0.f, Center, "Mode", "", 0.f, 0.f}, 2, 0}},
            JackInput{{3.000f, 4.000f, Center, "Speed CV", "", 8.f, 8.f}},
            JackInput{{5.000f, 6.000f, Center, "In", "", 8.f, 8.f}},
            JackOutput{{7.000f, 8.000f, Center, "Out", "", 8.f, 8.f}},
            DynamicGraphicDisplay{{{{{9.f, 10.f, TopLeft, "Screen", "", 50.f, 20.f}}}}},
        }};

        enum class Elem {
            SpeedKnob, ModeAlt,
            SpeedCvIn, AudioIn,
            AudioOut,
            Screen,
        };
    };

    } // namespace MetaModule
    """)


def test_sync_updates_circle_and_rect_coords(tmp_path):
    svg_path = _svg(tmp_path)
    new_text, report = M.sync_text(HEADER, M.read_svg_components(svg_path))
    assert (f"Knob{{{{{{{SPEED_XY[0]:.3f}f, {SPEED_XY[1]:.3f}f, Center"
            in new_text)
    assert (f"{SPEED_CV_XY[0]:.3f}f, {SPEED_CV_XY[1]:.3f}f, Center, "
            f"\"Speed CV\"" in new_text)
    assert (f"{SCREEN_RECT['x']:.3f}f, {SCREEN_RECT['y']:.3f}f, TopLeft, "
            f"\"Screen\", \"\", {SCREEN_RECT['w']:.3f}f, "
            f"{SCREEN_RECT['h']:.3f}f") in new_text
    # the menu-only alt-param line is untouched, byte for byte
    assert 'AltParamChoice{{{0.f, 0.f, Center, "Mode", "", 0.f, 0.f}, 2, 0}}' \
        in new_text
    assert report.updated == 5
    assert report.untouched == ["ModeAlt"]


def test_sync_against_hand_authored_svg(tmp_path):
    """Confirms mm_sync only cares about the hidden components layer's
    markup contract, not the rest of the SVG document v2 happens to emit
    around it (no panel background rect matching, no theme, etc.)."""
    svg_path = _hand_authored_svg(tmp_path)
    new_text, report = M.sync_text(HEADER, M.read_svg_components(svg_path))
    assert (f"Knob{{{{{{{SPEED_XY[0]:.3f}f, {SPEED_XY[1]:.3f}f, Center"
            in new_text)
    assert (f"{SCREEN_RECT['x']:.3f}f, {SCREEN_RECT['y']:.3f}f, TopLeft, "
            f"\"Screen\", \"\", {SCREEN_RECT['w']:.3f}f, "
            f"{SCREEN_RECT['h']:.3f}f") in new_text
    assert report.updated == 5
    assert report.untouched == ["ModeAlt"]


def test_sync_map_overrides_and_null(tmp_path):
    svg_path = _svg(tmp_path)
    header = HEADER.replace("SpeedCvIn", "CvInSpeed")   # hand-named enum
    mapping = {"CvInSpeed": "SPEED_CV_INPUT", "ModeAlt": None}
    new_text, report = M.sync_text(header, M.read_svg_components(svg_path),
                                   mapping)
    assert f"{SPEED_CV_XY[0]:.3f}f, {SPEED_CV_XY[1]:.3f}f" in new_text
    assert report.updated == 5


def test_mm_aspect_narrows_and_recenters(tmp_path):
    svg_path = _svg(tmp_path)
    mapping = {"Screen": {"id": "SCREEN", "mm_aspect": "16:9"}}
    new_text, report = M.sync_text(HEADER, M.read_svg_components(svg_path),
                                   mapping)
    new_w = 16 / 9 * SCREEN_RECT["h"]
    new_x = SCREEN_RECT["x"] + (SCREEN_RECT["w"] - new_w) / 2.0
    assert (f"{new_x:.3f}f, {SCREEN_RECT['y']:.3f}f, TopLeft, \"Screen\", "
            f"\"\", {new_w:.3f}f, {SCREEN_RECT['h']:.3f}f") in new_text
    assert report.updated == 5


def test_mm_aspect_numeric_form(tmp_path):
    svg_path = _svg(tmp_path)
    mapping = {"Screen": {"id": "SCREEN", "mm_aspect": 2.0}}
    new_text, _ = M.sync_text(HEADER, M.read_svg_components(svg_path), mapping)
    new_w = 2.0 * SCREEN_RECT["h"]
    new_x = SCREEN_RECT["x"] + (SCREEN_RECT["w"] - new_w) / 2.0
    assert f"{new_x:.3f}f, {SCREEN_RECT['y']:.3f}f, TopLeft" in new_text
    assert f"{new_w:.3f}f, {SCREEN_RECT['h']:.3f}f" in new_text


def test_mm_aspect_on_circle_raises(tmp_path):
    svg_path = _svg(tmp_path)
    mapping = {"SpeedKnob": {"id": "SPEED_PARAM", "mm_aspect": 2}}
    with pytest.raises(M.MMSyncError, match="circle"):
        M.sync_text(HEADER, M.read_svg_components(svg_path), mapping)


def test_mm_aspect_unknown_key_raises(tmp_path):
    svg_path = _svg(tmp_path)
    mapping = {"Screen": {"id": "SCREEN", "bogus": 1}}
    with pytest.raises(M.MMSyncError, match="unknown map key"):
        M.sync_text(HEADER, M.read_svg_components(svg_path), mapping)


def test_mm_aspect_missing_id_raises(tmp_path):
    svg_path = _svg(tmp_path)
    mapping = {"Screen": {"mm_aspect": "16:9"}}
    with pytest.raises(M.MMSyncError, match="needs an 'id'"):
        M.sync_text(HEADER, M.read_svg_components(svg_path), mapping)


def test_mm_aspect_bad_ratio_raises(tmp_path):
    svg_path = _svg(tmp_path)
    for bad in ("0:1", "abc", "1:0"):
        mapping = {"Screen": {"id": "SCREEN", "mm_aspect": bad}}
        with pytest.raises(M.MMSyncError, match="mm_aspect"):
            M.sync_text(HEADER, M.read_svg_components(svg_path), mapping)


def test_mm_aspect_null_id_raises(tmp_path):
    svg_path = _svg(tmp_path)
    mapping = {"Screen": {"id": None, "mm_aspect": "16:9"}}
    with pytest.raises(M.MMSyncError, match="non-null id"):
        M.sync_text(HEADER, M.read_svg_components(svg_path), mapping)


def test_sync_unmatched_svg_component_raises(tmp_path):
    svg_path = _svg(tmp_path)
    header = HEADER.replace("SpeedCvIn", "CvInSpeed")   # no map this time
    with pytest.raises(M.MMSyncError, match="SPEED_CV_INPUT"):
        M.sync_text(header, M.read_svg_components(svg_path))


def test_sync_count_mismatch_raises(tmp_path):
    svg_path = _svg(tmp_path)
    header = HEADER.replace("SpeedCvIn, AudioIn,", "AudioIn,")
    assert header != HEADER          # guard against silent no-op replacement
    with pytest.raises(M.MMSyncError, match="enum"):
        M.sync_text(header, M.read_svg_components(svg_path))


def test_sync_map_unknown_enum_raises(tmp_path):
    svg_path = _svg(tmp_path)
    with pytest.raises(M.MMSyncError, match="NoSuchElem"):
        M.sync_text(HEADER, M.read_svg_components(svg_path),
                    {"NoSuchElem": "SPEED_CV_INPUT"})


def test_cli_writes_header_in_place(tmp_path):
    svg_path = _svg(tmp_path)
    hp = tmp_path / "T_info.hh"
    hp.write_text(HEADER)
    rc = M.main(["--header", str(hp), "--svg", svg_path])
    assert rc == 0
    assert f"{SPEED_XY[0]:.3f}f, {SPEED_XY[1]:.3f}f" in hp.read_text()


def test_cli_failure_leaves_header_untouched(tmp_path):
    svg_path = _svg(tmp_path)
    hp = tmp_path / "T_info.hh"
    broken = HEADER.replace("SpeedCvIn", "CvInSpeed")
    hp.write_text(broken)
    rc = M.main(["--header", str(hp), "--svg", svg_path])
    assert rc == 1
    assert hp.read_text() == broken     # nothing written on failure


def test_cli_map_file(tmp_path):
    svg_path = _svg(tmp_path)
    hp = tmp_path / "T_info.hh"
    hp.write_text(HEADER.replace("SpeedCvIn", "CvInSpeed"))
    mp = tmp_path / "map.yaml"
    mp.write_text("CvInSpeed: SPEED_CV_INPUT\nModeAlt: null\n")
    rc = M.main(["--header", str(hp), "--svg", svg_path, "--map", str(mp)])
    assert rc == 0
    assert f"{SPEED_CV_XY[0]:.3f}f, {SPEED_CV_XY[1]:.3f}f" in hp.read_text()


def test_cli_map_file_with_aspect(tmp_path):
    svg_path = _svg(tmp_path)
    hp = tmp_path / "T_info.hh"
    hp.write_text(HEADER)
    mp = tmp_path / "map.yaml"
    mp.write_text('Screen: {id: SCREEN, mm_aspect: "16:9"}\nModeAlt: null\n')
    rc = M.main(["--header", str(hp), "--svg", svg_path, "--map", str(mp),
                 "--strict"])
    assert rc == 0
    new_w = 16 / 9 * SCREEN_RECT["h"]
    assert f"{new_w:.3f}f, {SCREEN_RECT['h']:.3f}f" in hp.read_text()


def test_strict_requires_null_declarations(tmp_path):
    svg_path = _svg(tmp_path)
    comps = M.read_svg_components(svg_path)
    # ModeAlt has no SVG match and no null declaration -> strict error
    with pytest.raises(M.MMSyncError, match="ModeAlt"):
        M.sync_text(HEADER, comps, strict=True)
    # declaring it null satisfies strict mode
    new_text, report = M.sync_text(HEADER, comps, {"ModeAlt": None},
                                   strict=True)
    assert report.updated == 5
    assert report.untouched == ["ModeAlt"]


def test_cli_strict_flag(tmp_path):
    svg_path = _svg(tmp_path)
    hp = tmp_path / "T_info.hh"
    hp.write_text(HEADER)
    rc = M.main(["--header", str(hp), "--svg", svg_path, "--strict"])
    assert rc == 1                       # ModeAlt undeclared
    assert hp.read_text() == HEADER      # nothing written
    mp = tmp_path / "map.yaml"
    mp.write_text("ModeAlt: null\n")
    rc = M.main(["--header", str(hp), "--svg", svg_path, "--strict",
                 "--map", str(mp)])
    assert rc == 0


GRID_XY = (15.0, 100.0)


def _svg_with_vcv_only_knob(tmp_path):
    # The T module plus a Grid knob that exists only on the VCV panel
    # (menu-only alt-param on MetaModule), with a custom widget class.
    extra = [{"name": "GRID_PARAM", "widget": "RoundSmallBlackSnapKnob",
              "x": GRID_XY[0], "y": GRID_XY[1]}]
    return _svg(tmp_path, extra_elements=extra, hp=16)


def test_ignore_lets_vcv_only_control_pass(tmp_path):
    svg_path = _svg_with_vcv_only_knob(tmp_path)
    comps = M.read_svg_components(svg_path)
    # Without ignore: the unmatched Grid knob is an error.
    with pytest.raises(M.MMSyncError, match="GRID_PARAM"):
        M.sync_text(HEADER, comps, {"ModeAlt": None})
    # With ignore: sync succeeds and strict still passes.
    mapping = {"ModeAlt": None, "ignore": ["GRID_PARAM"]}
    new_text, report = M.sync_text(HEADER, comps, mapping, strict=True)
    assert report.updated == 5
    assert report.untouched == ["ModeAlt"]


def test_ignore_unknown_svg_id_raises(tmp_path):
    svg_path = _svg_with_vcv_only_knob(tmp_path)
    comps = M.read_svg_components(svg_path)
    with pytest.raises(M.MMSyncError, match="NOPE"):
        M.sync_text(HEADER, comps,
                    {"ModeAlt": None, "ignore": ["GRID_PARAM", "NOPE"]})
