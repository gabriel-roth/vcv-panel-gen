import os
import re
import sys
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import constants as c
from glyphs import TextRenderer

_FUTURA = "/System/Library/Fonts/Supplemental/Futura.ttc"


def test_width_positive_and_scales():
    tr = TextRenderer(c.FONT_PATH)
    w1 = tr.text_width("FREQ", 3.0)
    w2 = tr.text_width("FREQ", 6.0)
    assert w1 > 0
    assert abs(w2 - 2 * w1) < 1e-6


def test_path_d_is_nonempty_and_has_no_transform():
    tr = TextRenderer(c.FONT_PATH)
    d = tr.text_to_path_d("A", x=10.0, y=20.0, size_mm=3.0, anchor="start")
    assert d.strip().startswith(("M", "m"))
    assert "transform" not in d


def test_empty_text_returns_empty():
    tr = TextRenderer(c.FONT_PATH)
    assert tr.text_to_path_d("   ", 0, 0, 3.0) == ""


def _path_ys(d):
    nums = [float(n) for n in re.findall(r"-?\d+\.?\d*", d)]
    return nums[1::2]  # SVGPathPen emits coordinate pairs; odd indices are y


def test_baseline_placement_and_yflip():
    tr = TextRenderer(c.FONT_PATH)
    d = tr.text_to_path_d("A", x=0.0, y=20.0, size_mm=5.0, anchor="start")
    ys = _path_ys(d)
    assert ys, "expected path coordinates"
    assert max(ys) <= 20.0 + 1e-6   # glyph sits at/above the baseline (SVG y grows downward)
    assert min(ys) < 20.0           # 'A' ascends above the baseline


def test_middle_anchor_matches_start_with_offset():
    tr = TextRenderer(c.FONT_PATH)
    w = tr.text_width("FREQ", 3.0)
    mid = tr.text_to_path_d("FREQ", x=50.0, y=10.0, size_mm=3.0, anchor="middle")
    start = tr.text_to_path_d("FREQ", x=50.0 - w / 2.0, y=10.0, size_mm=3.0, anchor="start")
    assert mid == start


def test_bundled_dejavu_fallback_loads():
    # The bundled font must always load — it's the portable fallback.
    import fontresolve as fr
    tr = TextRenderer(fr.BUNDLED_FONT, 0)
    assert tr.text_width("A", 3.0) > 0


@pytest.mark.skipif(not os.path.exists(_FUTURA), reason="Futura.ttc not installed")
def test_futura_ttc_face_loads():
    # Opening a .ttc requires a font number; face 0 is Futura Medium.
    tr = TextRenderer(_FUTURA, 0)
    assert tr.text_width("A", 3.0) > 0
    d = tr.text_to_path_d("A", 0.0, 10.0, 5.0, anchor="start")
    assert d and "transform" not in d


def test_tracking_widens_run_by_tracking_times_len():
    import fontresolve as fr
    tr = TextRenderer(fr.BUNDLED_FONT, 0)
    base = tr.text_width("ABCD", 5.0)
    trk = tr.text_width("ABCD", 5.0, tracking_mm=0.5)
    assert abs((trk - base) - 0.5 * 4) < 1e-9


def test_tracking_shifts_later_glyphs_right():
    import fontresolve as fr
    tr = TextRenderer(fr.BUNDLED_FONT, 0)
    plain = tr.text_to_path_d("AV", 0.0, 10.0, 5.0, anchor="start")
    spaced = tr.text_to_path_d("AV", 0.0, 10.0, 5.0, anchor="start", tracking_mm=1.0)
    # Same first glyph, wider run -> spaced string is longer/different, no transform.
    assert plain != spaced
    assert "transform" not in spaced


def test_kern_changes_width_by_sum_of_offsets():
    import fontresolve as fr
    tr = TextRenderer(fr.BUNDLED_FONT, 0)
    base = tr.text_width("ABCD", 5.0)
    kern = [0.0, -0.4, 0.0, 0.25]  # per-glyph leading offsets in mm
    assert abs((tr.text_width("ABCD", 5.0, kern_mm=kern) - base) - sum(kern)) < 1e-9


def test_kern_none_matches_no_kern():
    import fontresolve as fr
    tr = TextRenderer(fr.BUNDLED_FONT, 0)
    assert (tr.text_to_path_d("ABCD", 0.0, 10.0, 5.0, anchor="start")
            == tr.text_to_path_d("ABCD", 0.0, 10.0, 5.0, anchor="start", kern_mm=None))


def test_kern_tightens_only_the_targeted_gap():
    import fontresolve as fr
    tr = TextRenderer(fr.BUNDLED_FONT, 0)
    plain = tr.text_to_path_d("AVB", 0.0, 10.0, 5.0, anchor="start")
    # pull V toward A (offset before index 1); B keeps its own advance after V
    kerned = tr.text_to_path_d("AVB", 0.0, 10.0, 5.0, anchor="start",
                               kern_mm=[0.0, -0.5, 0.0])
    assert plain != kerned
    assert "transform" not in kerned
