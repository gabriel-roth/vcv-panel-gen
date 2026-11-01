import os
import sys

import pytest
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import panelgen
import variants
from variants import VariantError, apply_variant, roughen


@pytest.fixture(autouse=True)
def _isolate_conventional_theme(tmp_path, monkeypatch):
    monkeypatch.setattr(panelgen, "CONVENTIONAL_THEME", str(tmp_path / "no-theme.yaml"))


BASE = {
    "slug": "T", "name": "T", "hp": 12,
    "grids": {"main": {"cols": [15.0, 45.0], "rows": {"knobs": 40.0, "cv": 60.0}}},
    "zones": [{"x": 2, "y": 30, "w": 56, "h": 40, "arrows": [{"side": "right", "at": 50}]}],
    "elements": [
        {"row": {"grid": "main", "at": "knobs"}, "place": [{"name": "A_PARAM"}, {"name": "B_PARAM"}]},
        {"row": {"grid": "main", "at": "cv"}, "place": [{"name": "A_INPUT"}, {"name": "B_INPUT"}]},
        {"text": "IN", "x": 30, "y": 80},
        {"text": "IN", "x": 30, "y": 90},
        {"name": "OUT_OUTPUT", "x": 30, "y": 110},
    ],
    "connectors": [["A_PARAM", "A_INPUT"], ["B_PARAM", "B_INPUT"]],
    "overlaps_ok": [["B_INPUT", "OUT_OUTPUT"]],
}


def test_set_deep_merges_and_none_deletes():
    out = apply_variant(BASE, {"set": {"hp": 14, "grids": {"main": {"rows": {"cv": 62.0}}},
                                       "connectors": None}})
    assert out["hp"] == 14
    assert out["grids"]["main"]["rows"] == {"knobs": 40.0, "cv": 62.0}
    assert "connectors" not in out
    assert BASE["hp"] == 12   # base untouched


def test_edit_standalone_x_replaces_col():
    out = apply_variant(BASE, {"edit": {"OUT_OUTPUT": {"x": 20}}})
    assert out["elements"][4] == {"name": "OUT_OUTPUT", "x": 20, "y": 110}


def test_edit_row_item_without_position_stays_in_row():
    out = apply_variant(BASE, {"edit": {"B_PARAM": {"widget": "Trimpot"}}})
    assert out["elements"][0]["place"][1] == {"name": "B_PARAM", "widget": "Trimpot"}


def test_edit_row_item_position_pulls_it_out():
    out = apply_variant(BASE, {"edit": {"B_PARAM": {"y": 45}}})
    assert out["elements"][0]["place"] == [{"name": "A_PARAM"}, None]
    assert out["elements"][1] == {"name": "B_PARAM", "grid": "main", "col": 2, "y": 45}


def test_text_targets_need_disambiguation():
    with pytest.raises(VariantError, match="matches 2"):
        apply_variant(BASE, {"edit": {"text:IN": {"y": 85}}})
    out = apply_variant(BASE, {"edit": {"text:IN#2": {"y": 95}}})
    assert out["elements"][3]["y"] == 95


def test_remove_drops_references():
    out = apply_variant(BASE, {"remove": ["B_INPUT", "zone:0"]})
    assert out["elements"][1]["place"] == [{"name": "A_INPUT"}, None]
    assert out["connectors"] == [["A_PARAM", "A_INPUT"]]
    assert "overlaps_ok" not in out
    assert "zones" not in out


def test_remove_whole_row_drops_the_block():
    out = apply_variant(BASE, {"remove": ["A_INPUT", "B_INPUT"]})
    assert all("place" not in e or e["row"]["at"] != "cv" for e in out["elements"])


def test_add_appends():
    out = apply_variant(BASE, {"add": {"elements": [{"text": "NEW", "x": 10, "y": 20}]}})
    assert out["elements"][-1] == {"text": "NEW", "x": 10, "y": 20}
    with pytest.raises(VariantError):
        apply_variant(BASE, {"add": {"grids": {}}})


def test_unknown_target():
    with pytest.raises(VariantError, match="no such element"):
        apply_variant(BASE, {"edit": {"NOPE_PARAM": {"x": 1}}})


def test_roughen_strips_polish():
    out = roughen(apply_variant(BASE, {"add": {"glyphs": [{"src": "x.svg", "at": [1, 1]}]}}))
    assert "glyphs" not in out
    assert "arrows" not in out["zones"][0]


def test_page_builds_and_reports_bad_variant(tmp_path):
    (tmp_path / "base.yaml").write_text(yaml.safe_dump(BASE))
    (tmp_path / "overlay.py").write_text(
        "import variants\n"
        "def overlay(spec):\n"
        "    e = variants.find(spec, 'OUT_OUTPUT')\n"
        "    return f'<circle id=\"mock\" cx=\"{e[\"x\"]}\" cy=\"{e[\"y\"]}\" r=\"1\"/>'\n")
    (tmp_path / "v.yaml").write_text(yaml.safe_dump({
        "base": "base.yaml", "title": "Round 1", "overlay": "overlay.py",
        "later": ["title tracking"],
        "variants": [
            {"name": "Move out", "note": "OUT left", "edit": {"OUT_OUTPUT": {"x": 15}}},
            {"name": "Rough", "rough": True},
            {"name": "Bad", "edit": {"NOPE_PARAM": {"x": 1}}},
        ]}))
    page, failed = variants.build_page(str(tmp_path / "v.yaml"), library=None)
    assert page.count('class="card"') == 4          # Current + three variants
    assert page.count("<img src") == 3                 # the bad one has no image
    assert "title tracking" in page and "Round 1" in page
    assert [name for name, _ in failed] == ["Bad"]


def test_cli_writes_page(tmp_path):
    (tmp_path / "base.yaml").write_text(yaml.safe_dump(BASE))
    (tmp_path / "v.yaml").write_text(yaml.safe_dump({
        "base": "base.yaml", "variants": [{"name": "Wider", "set": {"hp": 14}, "crop": None}]}))
    assert variants.main([str(tmp_path / "v.yaml"), "--library", str(tmp_path / "none")]) == 0
    assert (tmp_path / "v.html").exists()
