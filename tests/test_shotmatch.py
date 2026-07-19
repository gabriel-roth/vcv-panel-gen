"""Template-match core, tested Rack-free by embedding a known template.

We synthesize a distinctive template, paste it into a larger canvas at a known
scale and offset, add mild noise, and assert locate() recovers the box.
"""
import numpy as np
import pytest
from PIL import Image

import shotmatch


def _make_template(seed=0, w=90, h=380):
    """A distinctive panel-like grayscale array in [0, 1]."""
    rng = np.random.default_rng(seed)
    arr = np.zeros((h, w), dtype=np.float32)
    # a few bright discs (knobs) and bars (labels) so the image has structure
    yy, xx = np.mgrid[0:h, 0:w]
    for cy, cx, r in [(70, 45, 20), (180, 30, 14), (180, 60, 14), (300, 45, 24)]:
        arr[(yy - cy) ** 2 + (xx - cx) ** 2 <= r * r] = 0.9
    arr[20:30, 10:80] = 0.6
    arr += rng.normal(0, 0.01, arr.shape).astype(np.float32)
    return np.clip(arr, 0, 1)


def _paste(canvas_wh, template, scale, offset, noise=0.02, seed=1):
    """Render template scaled + placed into a gray canvas; return the array."""
    cw, ch = canvas_wh
    ox, oy = offset
    tpl = shotmatch._resize_gray(template, scale)
    th, tw = tpl.shape
    rng = np.random.default_rng(seed)
    canvas = rng.uniform(0.15, 0.25, (ch, cw)).astype(np.float32)  # rack-ish bg
    canvas[oy:oy + th, ox:ox + tw] = tpl
    canvas += rng.normal(0, noise, canvas.shape).astype(np.float32)
    return np.clip(canvas, 0, 1)


def test_locate_exact_scale_and_offset():
    tpl = _make_template()
    window = _paste((600, 800), tpl, scale=1.0, offset=(140, 90))
    m = shotmatch.locate(window, tpl, scales=[1.0])
    assert m is not None
    assert abs(m.x - 140) <= 2
    assert abs(m.y - 90) <= 2
    assert m.w == tpl.shape[1]
    assert m.h == tpl.shape[0]
    assert m.score > 0.9


def test_locate_recovers_scaled_module():
    """On a Retina capture the module is the template times backingScale."""
    tpl = _make_template(seed=3)
    window = _paste((900, 1200), tpl, scale=2.0, offset=(120, 200))
    # caller offers the right hint plus fallbacks; best scale should win
    m = shotmatch.locate(window, tpl, scales=[1.0, 1.5, 2.0])
    assert m is not None
    assert m.scale == 2.0
    assert abs(m.x - 120) <= 3
    assert abs(m.y - 200) <= 3
    assert m.score > 0.85


def test_locate_is_theme_invariant():
    """A light template must still match a dark (contrast-inverted) panel.

    Rack's --screenshot always renders the light panel, but a running Rack may
    show the dark one; matching on gradient magnitude makes polarity irrelevant.
    """
    tpl = _make_template(seed=7)          # the light-panel template
    dark = 1.0 - tpl                      # same edges, inverted fill (dark panel)
    window = _paste((900, 1100), dark, scale=2.0, offset=(160, 140))
    m = shotmatch.locate(window, tpl, scales=[1.5, 2.0, 2.5])
    assert m is not None
    assert m.scale == 2.0
    assert abs(m.x - 160) <= 3 and abs(m.y - 140) <= 3
    assert m.score > 0.5


def test_low_score_when_template_absent():
    tpl = _make_template(seed=5)
    rng = np.random.default_rng(9)
    window = rng.uniform(0.1, 0.3, (700, 500)).astype(np.float32)  # no template
    m = shotmatch.locate(window, tpl, scales=[1.0])
    assert m is not None  # locate still returns its best guess...
    assert m.score < 0.5   # ...but the score is low, so the caller rejects it


def test_template_larger_than_window_returns_none():
    tpl = _make_template()
    small = np.zeros((50, 50), dtype=np.float32)
    assert shotmatch.locate(small, tpl, scales=[1.0]) is None


def test_to_gray_from_pil():
    img = Image.new("RGB", (4, 3), (255, 255, 255))
    arr = shotmatch.to_gray(img)
    assert arr.shape == (3, 4)
    assert pytest.approx(arr.max(), abs=1e-6) == 1.0


def test_flat_template_rejected():
    flat = np.full((10, 10), 0.5, dtype=np.float32)
    window = np.zeros((40, 40), dtype=np.float32)
    with pytest.raises(ValueError):
        shotmatch.ncc_map(window, flat)
