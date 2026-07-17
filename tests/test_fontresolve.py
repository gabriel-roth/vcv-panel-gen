import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fontresolve as fr

FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")


def test_bundled_font_path_exists():
    assert os.path.exists(fr.BUNDLED_FONT)
    assert fr.BUNDLED_FONT.endswith("DejaVuSans.ttf")


def test_index_finds_dejavu_by_family_name():
    index = fr.build_font_index([FONTS_DIR])
    assert "dejavu sans" in index
    path, num = index["dejavu sans"]
    assert path.endswith("DejaVuSans.ttf") and num == 0


def test_resolve_matches_named_family():
    path, num = fr.resolve_font_stack(["DejaVu Sans"], dirs=[FONTS_DIR])
    assert path.endswith("DejaVuSans.ttf") and num == 0


def test_resolve_is_case_insensitive():
    path, _ = fr.resolve_font_stack(["dejavu sans"], dirs=[FONTS_DIR])
    assert path.endswith("DejaVuSans.ttf")


def test_resolve_falls_through_to_dejavu_in_dir():
    # Unknown family, but DejaVu is in the scanned dir → appended fallback wins.
    path, _ = fr.resolve_font_stack(["No Such Font"], dirs=[FONTS_DIR])
    assert path.endswith("DejaVuSans.ttf")


def test_resolve_ultimate_bundled_fallback_when_nothing_found():
    # Empty dir list: no index hits at all → bundled file returned directly.
    path, num = fr.resolve_font_stack(["No Such Font"], dirs=[])
    assert path == fr.BUNDLED_FONT and num == 0


def test_resolve_accepts_prebuilt_index():
    # A caller resolving several stacks (base font + title font) builds the
    # index once and passes it in; no directory scan happens on this path.
    index = {"futura": ("/fake/Futura.ttc", 1)}
    path, num = fr.resolve_font_stack(["Futura"], index=index)
    assert (path, num) == ("/fake/Futura.ttc", 1)
    # miss in the prebuilt index falls back to bundled, not to a fresh scan
    path, num = fr.resolve_font_stack(["No Such Font"], index={})
    assert path == fr.BUNDLED_FONT and num == 0
