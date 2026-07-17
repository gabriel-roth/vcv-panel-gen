import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import theme as T

import pytest


def test_default_theme_values():
    d = T.DEFAULT_THEME
    assert d.background == "#e8e8e8"
    assert d.font == ["DejaVu Sans"]  # bundled font → reproducible by default
    assert d.casing == "preserve"
    assert d.text_color is None
    assert d.screws == "light"  # silver screws unless a spec opts into dark


def test_merge_override_wins_field_by_field():
    base = T.Theme(background="#111111", font=["A"], casing="upper", text_color="#fff")
    override = T.Theme(casing="lower")  # only casing set
    merged = T.merge(base, override)
    assert merged.casing == "lower"          # overridden
    assert merged.background == "#111111"    # inherited
    assert merged.font == ["A"]              # inherited
    assert merged.text_color == "#fff"       # inherited


def test_resolve_layers_default_then_file_then_inline():
    file_partial = T.Theme(background="#222222", casing="upper")
    inline_partial = T.Theme(casing="title")  # spec overrides file's casing
    r = T.resolve_theme(file_partial, inline_partial)
    assert r.background == "#222222"          # from file
    assert r.casing == "title"                # inline beats file
    assert r.font == ["DejaVu Sans"]          # from default
    assert r.text_color is None               # from default


def test_resolve_with_no_partials_is_default():
    assert T.resolve_theme() == T.DEFAULT_THEME


def test_from_mapping_parses_all_fields():
    t = T.theme_from_mapping(
        {"background": "#1a1a1a", "font": ["Futura"], "casing": "upper",
         "text_color": "#eee"}, "test")
    assert t.background == "#1a1a1a" and t.font == ["Futura"]
    assert t.casing == "upper" and t.text_color == "#eee"


def test_from_mapping_none_is_empty_theme():
    assert T.theme_from_mapping(None, "test") == T.Theme()


def test_from_mapping_rejects_bad_hex():
    with pytest.raises(T.ThemeError, match="background"):
        T.theme_from_mapping({"background": "grey"}, "myfile")


def test_from_mapping_rejects_bad_casing():
    with pytest.raises(T.ThemeError, match="casing"):
        T.theme_from_mapping({"casing": "sentence"}, "myfile")


def test_from_mapping_rejects_non_list_font():
    with pytest.raises(T.ThemeError, match="font"):
        T.theme_from_mapping({"font": "Futura"}, "myfile")


def test_from_mapping_rejects_empty_font_list():
    with pytest.raises(T.ThemeError, match="font"):
        T.theme_from_mapping({"font": []}, "myfile")


def test_from_mapping_rejects_unknown_field():
    with pytest.raises(T.ThemeError, match="unknown"):
        T.theme_from_mapping({"colour": "#fff"}, "myfile")


def test_error_names_the_source_layer():
    with pytest.raises(T.ThemeError, match="myfile"):
        T.theme_from_mapping({"casing": "bogus"}, "myfile")


def test_load_theme_file_reads_yaml(tmp_path):
    p = tmp_path / "theme.yaml"
    p.write_text("background: \"#123456\"\ncasing: title\n")
    t = T.load_theme_file(str(p))
    assert t.background == "#123456" and t.casing == "title"
    assert t.font is None  # unset → inherits later


def test_apply_casing_upper():
    assert T.apply_casing("Freq", "upper") == "FREQ"


def test_apply_casing_lower():
    assert T.apply_casing("Freq", "lower") == "freq"


def test_apply_casing_title():
    assert T.apply_casing("out left", "title") == "Out Left"


def test_apply_casing_preserve():
    assert T.apply_casing("V/OCT", "preserve") == "V/OCT"


def test_text_color_explicit_override_wins():
    t = T.Theme(background="#000000", text_color="#abcdef")
    assert T.resolve_text_color(t) == "#abcdef"


def test_text_color_auto_black_on_light_bg():
    t = T.Theme(background="#e8e8e8")
    assert T.resolve_text_color(t) == "#000000"


def test_text_color_auto_white_on_dark_bg():
    t = T.Theme(background="#1a1a1a")
    assert T.resolve_text_color(t) == "#ffffff"


def test_text_color_auto_handles_short_hex():
    t = T.Theme(background="#111")  # near-black
    assert T.resolve_text_color(t) == "#ffffff"


def test_default_theme_title_font_is_none():
    assert T.DEFAULT_THEME.title_font is None


def test_merge_inherits_and_overrides_title_font():
    base = T.Theme(title_font=["A"])
    assert T.merge(base, T.Theme()).title_font == ["A"]                  # inherit
    assert T.merge(base, T.Theme(title_font=["B"])).title_font == ["B"]  # override


def test_resolve_title_font_precedence():
    file_p = T.Theme(title_font=["FileFont"])
    inline_p = T.Theme(title_font=["InlineFont"])
    assert T.resolve_theme(file_p, inline_p).title_font == ["InlineFont"]  # inline wins
    assert T.resolve_theme(file_p, None).title_font == ["FileFont"]        # from file
    assert T.resolve_theme().title_font is None                           # default


def test_from_mapping_parses_title_font():
    t = T.theme_from_mapping({"title_font": ["Shuttleblock Test Demi"]}, "test")
    assert t.title_font == ["Shuttleblock Test Demi"]


def test_from_mapping_title_font_absent_is_none():
    assert T.theme_from_mapping({"font": ["X"]}, "test").title_font is None


def test_from_mapping_rejects_non_list_title_font():
    with pytest.raises(T.ThemeError, match="title_font"):
        T.theme_from_mapping({"title_font": "NotAList"}, "myfile")


def test_from_mapping_rejects_empty_title_font():
    with pytest.raises(T.ThemeError, match="title_font"):
        T.theme_from_mapping({"title_font": []}, "myfile")


def test_title_font_is_an_allowed_field():
    # Must not be rejected as an unknown field.
    T.theme_from_mapping({"title_font": ["X"]}, "test")  # no raise


def test_from_mapping_parses_screws():
    assert T.theme_from_mapping({"screws": "dark"}, "test").screws == "dark"
    assert T.theme_from_mapping({"screws": "light"}, "test").screws == "light"


def test_from_mapping_screws_absent_is_none():
    assert T.theme_from_mapping({"font": ["X"]}, "test").screws is None


def test_from_mapping_rejects_bad_screws():
    with pytest.raises(T.ThemeError, match="screws"):
        T.theme_from_mapping({"screws": "brass"}, "myfile")


def test_merge_inherits_and_overrides_screws():
    base = T.Theme(screws="dark")
    assert T.merge(base, T.Theme()).screws == "dark"                # inherit
    assert T.merge(base, T.Theme(screws="light")).screws == "light"  # override


def test_resolve_screw_color_light_and_dark():
    assert T.resolve_screw_color(T.Theme(screws="light")) == "#c0c0c0"
    assert T.resolve_screw_color(T.Theme(screws="dark")) == "#333333"


def test_resolve_screw_color_defaults_to_light():
    # An unset screws field (None) resolves to the light/silver screw.
    assert T.resolve_screw_color(T.Theme()) == "#c0c0c0"


def test_from_mapping_value_color_and_rejects_bad():
    t = T.theme_from_mapping({"value_color": "#a8a8a8"}, "src")
    assert t.value_color == "#a8a8a8"
    with pytest.raises(T.ThemeError, match="value_color"):
        T.theme_from_mapping({"value_color": "grey"}, "src")


def test_resolve_value_color_blends_text_toward_background():
    # 0.55 * 255 + 0.45 * 0x3d(61) = 167.7 -> 168 = 0xa8 per channel
    t = T.Theme(background="#3d3d3d", text_color="#ffffff")
    assert T.resolve_value_color(t) == "#a8a8a8"


def test_resolve_value_color_explicit_override_wins():
    t = T.Theme(background="#3d3d3d", text_color="#ffffff", value_color="#808080")
    assert T.resolve_value_color(t) == "#808080"


def test_resolve_value_color_default_theme():
    # Auto text on the default light background resolves black -> dim grey:
    # 0.45 * 0xe8(232) = 104.4 -> 104 = 0x68 per channel.
    assert T.resolve_value_color(T.DEFAULT_THEME) == "#686868"


def test_merge_inherits_and_overrides_value_color():
    base = T.Theme(value_color="#aaaaaa")
    assert T.merge(base, T.Theme()).value_color == "#aaaaaa"
    assert T.merge(base, T.Theme(value_color="#bbbbbb")).value_color == "#bbbbbb"
