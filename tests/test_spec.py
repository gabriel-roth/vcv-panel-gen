import os
import sys
import textwrap

import pytest
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spec import (SpecError, GridSpec, ColsSpec, Position, ComponentEl,
                   LabelSpec, Rect, TextEl, RingEl, Zone, GlyphEl, TitleSpec,
                   PanelSpec, load_spec, parse_spec)


HAPPY_YAML = textwrap.dedent("""\
    slug: test_panel
    name: Test Panel
    hp: 15
    theme:
      background: "#222222"
    title:
      text: Test Panel
      size: 5.0
      valign: center
    grids:
      main:
        cols: {count: 4, from: 12.6, to: 63.6}
        rows:
          knobs_a: 42.088
          cv_a: 53.746
      labels:
        cols: [11.9, 38.1, 59.845, 70.0]
        rows: {from: 31.5, to: 101.7, count: 3, names: [labels_a, labels_b, labels_c]}
    elements:
      - {name: TIME_PARAM, widget: RoundBlackKnob, grid: main, col: 1, row: cv_a, dy: 0.5}
      - {name: FREEZE_INPUT, x: 11.9, y: 15.875}
      - {name: SCREEN, kind: widget, rect: {x: 1.5, y: 10.4, w: 57.96, h: 22.35}}
      - {text: TIME, grid: labels, col: 1, row: labels_a}
      - {ring: ["0", "4", "8", "16", "32", "64"], around: TIME_PARAM, gap: 0.65}
      - row: {grid: main, at: knobs_a, widget: RoundBlackKnob}
        place:
          - {name: DENSITY_PARAM}
          - {name: PITCH_PARAM}
          - ~
          - {name: SIZE_PARAM}
      - row: {grid: labels, at: labels_a}
        place: [DENSITY, PITCH, ~, SIZE]
      - {name: DRIVE_PARAM, grid: main, col: 2, row: cv_a, label: {text: Drive, dy: 8.2}}
    zones:
      - {x: 0, y: 0, w: 63.6, h: 128.5}
      - {x: 0, y: 0, w: 20, h: 20, fill: "#112233", opacity: 0.5, rx: 1.0}
    glyphs:
      - {src: glyph.svg, at: [5.0, 5.0], scale: 1.0}
    connectors:
      - [TIME_PARAM, FREEZE_INPUT]
    overlaps_ok:
      - [TIME_PARAM]
      - [FREEZE_INPUT, SCREEN]
    side_margin: 8.0
    """)

_GLYPH_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'


def _write_spec(tmp_path, text, glyph=True):
    if glyph:
        (tmp_path / "glyph.svg").write_text(_GLYPH_SVG)
    p = tmp_path / "spec.yaml"
    p.write_text(text)
    return p


def load(tmp_path, text, glyph=True):
    return load_spec(str(_write_spec(tmp_path, text, glyph=glyph)))


@pytest.fixture(autouse=True)
def _glyph_asset(tmp_path):
    # Tests that call parse_spec(data, str(tmp_path)) directly (bypassing the
    # load() helper) still need glyph.svg on disk, since HAPPY_YAML's glyphs:
    # entry resolves 'src' relative to base_dir.
    (tmp_path / "glyph.svg").write_text(_GLYPH_SVG)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_happy_path_full_spec(tmp_path):
    p = load(tmp_path, HAPPY_YAML)
    assert isinstance(p, PanelSpec)
    assert p.slug == "test_panel"
    assert p.name == "Test Panel"
    assert p.hp == 15
    assert p.theme_mapping == {"background": "#222222"}
    assert p.side_margin == 8.0

    # title
    assert p.title.text == "Test Panel"
    assert p.title.size == 5.0
    assert p.title.valign == "center"

    # grids: both cols forms
    main = p.grids["main"]
    assert isinstance(main, GridSpec)
    assert main.cols == ColsSpec(count=4, x_from=12.6, x_to=63.6, explicit=None)
    assert main.rows == {"knobs_a": 42.088, "cv_a": 53.746}

    labels = p.grids["labels"]
    assert labels.cols == ColsSpec(count=4, x_from=None, x_to=None,
                                    explicit=[11.9, 38.1, 59.845, 70.0])
    # both rows forms: evenly-spaced form resolved to a name->y dict
    assert labels.rows["labels_a"] == 31.5
    assert labels.rows["labels_c"] == 101.7
    assert labels.rows["labels_b"] == pytest.approx((31.5 + 101.7) / 2)

    # component with grid pos + dy
    time_param = next(e for e in p.elements if getattr(e, "name", None) == "TIME_PARAM")
    assert isinstance(time_param, ComponentEl)
    assert time_param.kind == "param"  # inferred from suffix
    assert time_param.widget == "RoundBlackKnob"
    assert time_param.pos == Position(grid="main", col=1, row="cv_a", x=None, y=None,
                                       dx=0.0, dy=0.5)
    assert time_param.rect is None

    # component with absolute pos, kind inferred, widget defaulted
    freeze = next(e for e in p.elements if getattr(e, "name", None) == "FREEZE_INPUT")
    assert freeze.kind == "input"
    assert freeze.widget == "PJ301MPort"  # default for "input" from components.yaml
    assert freeze.pos == Position(grid=None, col=None, row=None, x=11.9, y=15.875,
                                   dx=0.0, dy=0.0)

    # rect widget
    screen = next(e for e in p.elements if getattr(e, "name", None) == "SCREEN")
    assert screen.kind == "widget"
    assert screen.pos is None
    assert screen.rect == Rect(x=1.5, y=10.4, w=57.96, h=22.35)

    # text element
    text_els = [e for e in p.elements if isinstance(e, TextEl)]
    time_text = next(e for e in text_els if e.text == "TIME")
    assert time_text.pos.grid == "labels" and time_text.pos.col == 1
    assert time_text.pos.row == "labels_a"

    # ring
    ring = next(e for e in p.elements if isinstance(e, RingEl))
    assert ring.labels == ["0", "4", "8", "16", "32", "64"]
    assert ring.around == "TIME_PARAM"
    assert ring.gap == 0.65

    # row/place shorthand: '~' skips a column, cols are 1-based positions
    knobs = [e for e in p.elements if isinstance(e, ComponentEl) and e.pos and e.pos.row == "knobs_a"]
    assert [k.pos.col for k in knobs] == [1, 2, 4]
    assert [k.name for k in knobs] == ["DENSITY_PARAM", "PITCH_PARAM", "SIZE_PARAM"]
    assert all(k.widget == "RoundBlackKnob" for k in knobs)  # shared key applied

    # row/place shorthand with bare-string place items -> text elements
    label_texts = [e for e in text_els if e.pos and e.pos.row == "labels_a" and e.text != "TIME"]
    assert sorted((e.text, e.pos.col) for e in label_texts) == [
        ("DENSITY", 1), ("PITCH", 2), ("SIZE", 4)]

    # attached label sugar
    drive = next(e for e in p.elements if getattr(e, "name", None) == "DRIVE_PARAM")
    assert drive.label == LabelSpec(text="Drive", dx=0.0, dy=8.2, size=None, color=None, casing=None)

    # zones: defaults + explicit override
    assert len(p.zones) == 2
    z0 = p.zones[0]
    assert z0.fill == "#ffffff" and z0.opacity == 0.14 and z0.rx == 2.0
    z1 = p.zones[1]
    assert z1.fill == "#112233" and z1.opacity == 0.5 and z1.rx == 1.0

    # glyphs
    assert len(p.glyphs) == 1
    g = p.glyphs[0]
    assert g.src.endswith("glyph.svg") and os.path.isfile(g.src)
    assert g.x == 5.0 and g.y == 5.0 and g.scale == 1.0

    # connectors / overlaps_ok
    assert p.connectors == [["TIME_PARAM", "FREEZE_INPUT"]]
    assert p.overlaps_ok == [["TIME_PARAM"], ["FREEZE_INPUT", "SCREEN"]]


def test_kind_inferred_from_suffix(tmp_path):
    p = load(tmp_path, HAPPY_YAML)
    assert next(e for e in p.elements if getattr(e, "name", "") == "TIME_PARAM").kind == "param"


def test_row_place_shorthand_expands(tmp_path):
    p = load(tmp_path, HAPPY_YAML)
    knobs = [e for e in p.elements if isinstance(e, ComponentEl) and e.pos and e.pos.row == "knobs_a"]
    assert [k.pos.col for k in knobs] == [1, 2, 4]


# ---------------------------------------------------------------------------
# Rule-by-rule validation tests
# ---------------------------------------------------------------------------

def test_unknown_key_rejected(tmp_path):
    with pytest.raises(SpecError, match="wobble"):
        load(tmp_path, HAPPY_YAML.replace("hp: 15", "hp: 15\nwobble: 3"))


def test_unknown_key_rejected_nested(tmp_path):
    with pytest.raises(SpecError, match="wobble"):
        load(tmp_path, HAPPY_YAML.replace(
            "cols: {count: 4, from: 12.6, to: 63.6}",
            "cols: {count: 4, from: 12.6, to: 63.6, wobble: 1}"))


@pytest.mark.parametrize("key", ["slug", "name", "hp", "elements"])
def test_required_top_level_keys(tmp_path, key):
    data = yaml.safe_load(HAPPY_YAML)
    del data[key]
    with pytest.raises(SpecError, match=key):
        parse_spec(data, str(tmp_path))


@pytest.mark.parametrize("bad_hp", [0, -1, 1.5, True, "15"])
def test_hp_must_be_positive_int(tmp_path, bad_hp):
    data = yaml.safe_load(HAPPY_YAML)
    data["hp"] = bad_hp
    with pytest.raises(SpecError, match="hp"):
        parse_spec(data, str(tmp_path))


def test_element_requires_exactly_one_x_source_none(tmp_path):
    data = yaml.safe_load(HAPPY_YAML)
    data["elements"].append({"name": "BAD_PARAM", "row": "cv_a", "grid": "main"})
    with pytest.raises(SpecError, match="x-source"):
        parse_spec(data, str(tmp_path))


def test_element_requires_exactly_one_x_source_both(tmp_path):
    data = yaml.safe_load(HAPPY_YAML)
    data["elements"].append({"name": "BAD_PARAM", "grid": "main", "col": 1, "x": 5,
                              "row": "cv_a"})
    with pytest.raises(SpecError, match="x-source"):
        parse_spec(data, str(tmp_path))


def test_element_requires_exactly_one_y_source_none(tmp_path):
    data = yaml.safe_load(HAPPY_YAML)
    data["elements"].append({"name": "BAD_PARAM", "grid": "main", "col": 1})
    with pytest.raises(SpecError, match="y-source"):
        parse_spec(data, str(tmp_path))


def test_element_requires_exactly_one_y_source_both(tmp_path):
    data = yaml.safe_load(HAPPY_YAML)
    data["elements"].append({"name": "BAD_PARAM", "grid": "main", "col": 1,
                              "row": "cv_a", "y": 5})
    with pytest.raises(SpecError, match="y-source"):
        parse_spec(data, str(tmp_path))


def test_row_without_grid_is_error(tmp_path):
    data = yaml.safe_load(HAPPY_YAML)
    data["elements"].append({"name": "BAD_PARAM", "x": 5, "row": "cv_a"})
    with pytest.raises(SpecError, match="grid"):
        parse_spec(data, str(tmp_path))


@pytest.mark.parametrize("bad_col", [0, -1, 5, 1.5])
def test_col_must_be_1_based_int_within_grid_count(tmp_path, bad_col):
    data = yaml.safe_load(HAPPY_YAML)
    data["elements"].append({"name": "BAD_PARAM", "grid": "main", "col": bad_col,
                              "row": "cv_a"})
    with pytest.raises(SpecError, match="col"):
        parse_spec(data, str(tmp_path))


def test_row_must_name_a_row_in_the_grid(tmp_path):
    data = yaml.safe_load(HAPPY_YAML)
    data["elements"].append({"name": "BAD_PARAM", "grid": "main", "col": 1,
                              "row": "no_such_row"})
    with pytest.raises(SpecError, match="no_such_row"):
        parse_spec(data, str(tmp_path))


def test_duplicate_component_name_rejected(tmp_path):
    data = yaml.safe_load(HAPPY_YAML)
    data["elements"].append({"name": "TIME_PARAM", "x": 1, "y": 1})
    with pytest.raises(SpecError, match="duplicate"):
        parse_spec(data, str(tmp_path))


def test_empty_component_name_rejected(tmp_path):
    data = yaml.safe_load(HAPPY_YAML)
    data["elements"].append({"name": "", "x": 1, "y": 1})
    with pytest.raises(SpecError, match="name"):
        parse_spec(data, str(tmp_path))


def test_kind_required_when_no_suffix_match(tmp_path):
    data = yaml.safe_load(HAPPY_YAML)
    data["elements"].append({"name": "GADGET", "x": 1, "y": 1})
    with pytest.raises(SpecError, match="kind"):
        parse_spec(data, str(tmp_path))


def test_kind_must_be_allowed_value(tmp_path):
    data = yaml.safe_load(HAPPY_YAML)
    data["elements"].append({"name": "GADGET", "kind": "bogus", "x": 1, "y": 1})
    with pytest.raises(SpecError, match="kind"):
        parse_spec(data, str(tmp_path))


def test_kind_suffix_match_is_case_sensitive(tmp_path):
    data = yaml.safe_load(HAPPY_YAML)
    data["elements"].append({"name": "gadget_param", "x": 1, "y": 1})
    with pytest.raises(SpecError, match="kind"):
        parse_spec(data, str(tmp_path))


def test_rect_requires_kind_widget(tmp_path):
    data = yaml.safe_load(HAPPY_YAML)
    data["elements"].append({"name": "BAD_PARAM", "rect": {"x": 0, "y": 0, "w": 5, "h": 5}})
    with pytest.raises(SpecError, match="rect"):
        parse_spec(data, str(tmp_path))


def test_rect_mutually_exclusive_with_grid_position(tmp_path):
    data = yaml.safe_load(HAPPY_YAML)
    data["elements"].append({"name": "BAD_SCREEN", "kind": "widget", "grid": "main",
                              "col": 1, "row": "cv_a",
                              "rect": {"x": 0, "y": 0, "w": 5, "h": 5}})
    with pytest.raises(SpecError, match="rect"):
        parse_spec(data, str(tmp_path))


def test_rect_mutually_exclusive_with_absolute_position(tmp_path):
    data = yaml.safe_load(HAPPY_YAML)
    data["elements"].append({"name": "BAD_SCREEN", "kind": "widget", "x": 1, "y": 1,
                              "rect": {"x": 0, "y": 0, "w": 5, "h": 5}})
    with pytest.raises(SpecError, match="rect"):
        parse_spec(data, str(tmp_path))


def test_ring_around_must_reference_declared_component(tmp_path):
    data = yaml.safe_load(HAPPY_YAML)
    data["elements"].append({"ring": ["a", "b"], "around": "NO_SUCH_NAME"})
    with pytest.raises(SpecError, match="NO_SUCH_NAME"):
        parse_spec(data, str(tmp_path))


def test_connectors_must_be_2_lists(tmp_path):
    data = yaml.safe_load(HAPPY_YAML)
    data["connectors"] = [["TIME_PARAM"]]
    with pytest.raises(SpecError, match="connector"):
        parse_spec(data, str(tmp_path))


def test_connectors_must_reference_declared_names(tmp_path):
    data = yaml.safe_load(HAPPY_YAML)
    data["connectors"] = [["TIME_PARAM", "NO_SUCH_NAME"]]
    with pytest.raises(SpecError, match="NO_SUCH_NAME"):
        parse_spec(data, str(tmp_path))


def test_overlaps_ok_must_be_1_or_2_lists(tmp_path):
    data = yaml.safe_load(HAPPY_YAML)
    data["overlaps_ok"] = [["TIME_PARAM", "FREEZE_INPUT", "SCREEN"]]
    with pytest.raises(SpecError, match="overlaps_ok"):
        parse_spec(data, str(tmp_path))


def test_overlaps_ok_must_reference_declared_names(tmp_path):
    data = yaml.safe_load(HAPPY_YAML)
    data["overlaps_ok"] = [["NO_SUCH_NAME"]]
    with pytest.raises(SpecError, match="NO_SUCH_NAME"):
        parse_spec(data, str(tmp_path))


def test_grid_rows_evenly_spaced_requires_names(tmp_path):
    data = yaml.safe_load(HAPPY_YAML)
    data["grids"]["labels"]["rows"] = {"from": 31.5, "to": 101.7, "count": 3}
    with pytest.raises(SpecError, match="names"):
        parse_spec(data, str(tmp_path))


def test_grid_rows_evenly_spaced_names_length_must_match_count(tmp_path):
    data = yaml.safe_load(HAPPY_YAML)
    data["grids"]["labels"]["rows"] = {"from": 31.5, "to": 101.7, "count": 3,
                                        "names": ["a", "b"]}
    with pytest.raises(SpecError, match="names"):
        parse_spec(data, str(tmp_path))


def test_zone_color_must_match_regex(tmp_path):
    data = yaml.safe_load(HAPPY_YAML)
    data["zones"][0]["fill"] = "#zzz"
    with pytest.raises(SpecError, match="fill"):
        parse_spec(data, str(tmp_path))


def test_zone_color_rejects_3digit_shorthand(tmp_path):
    data = yaml.safe_load(HAPPY_YAML)
    data["zones"][0]["fill"] = "#fff"
    with pytest.raises(SpecError, match="fill"):
        parse_spec(data, str(tmp_path))


def test_label_color_must_match_regex(tmp_path):
    data = yaml.safe_load(HAPPY_YAML)
    for el in data["elements"]:
        if el.get("name") == "DRIVE_PARAM":
            el["label"]["color"] = "not-a-color"
    with pytest.raises(SpecError, match="color"):
        parse_spec(data, str(tmp_path))


def test_bare_string_label_is_rejected(tmp_path):
    data = yaml.safe_load(HAPPY_YAML)
    for el in data["elements"]:
        if el.get("name") == "DRIVE_PARAM":
            el["label"] = "Drive"
    with pytest.raises(SpecError, match="dy"):
        parse_spec(data, str(tmp_path))


def test_label_requires_dy(tmp_path):
    data = yaml.safe_load(HAPPY_YAML)
    for el in data["elements"]:
        if el.get("name") == "DRIVE_PARAM":
            el["label"] = {"text": "Drive"}
    with pytest.raises(SpecError, match="dy"):
        parse_spec(data, str(tmp_path))
