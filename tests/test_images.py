import os
import sys
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from images import load_image, place_image, ImageError


def _write(tmp_path, body, viewbox="-1 -1 2 2"):
    p = tmp_path / "g.svg"
    p.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}">{body}</svg>')
    return str(p)


def test_requires_viewbox(tmp_path):
    p = tmp_path / "n.svg"
    p.write_text('<svg xmlns="http://www.w3.org/2000/svg"><line x1="0" y1="0" x2="1" y2="1"/></svg>')
    with pytest.raises(ImageError):
        load_image(str(p))


def test_line_baked_centered(tmp_path):
    # viewBox center is (0,0); a horizontal line across it, placed at (10,20).
    src = _write(tmp_path, '<line x1="-0.5" y1="0" x2="0.5" y2="0" stroke="#fff" stroke-width="0.1"/>')
    out = place_image(load_image(src), cx=10.0, cy=20.0, sx=1.0, sy=1.0)
    assert "transform" not in out
    assert 'stroke="#fff"' in out
    assert 'x1="9.5"' in out and 'x2="10.5"' in out
    assert 'y1="20"' in out and 'y2="20"' in out


def test_scale_scales_coords_and_stroke(tmp_path):
    src = _write(tmp_path, '<line x1="-0.5" y1="0" x2="0.5" y2="0" stroke="#fff" stroke-width="0.1"/>')
    out = place_image(load_image(src), cx=10.0, cy=20.0, sx=2.0, sy=2.0)
    assert 'x1="9"' in out and 'x2="11"' in out
    assert 'stroke-width="0.2"' in out          # 0.1 * scale


def test_polygon_and_polyline_and_path(tmp_path):
    body = ('<polyline points="-0.5,0 0,0.25 0.5,0" fill="none" stroke="#fff" stroke-width="0.1"/>'
            '<polygon points="-0.5,-0.5 0.5,-0.5 0,0.5" fill="#fff"/>'
            '<path d="M -0.5,0 L 0.5,0" stroke="#fff" stroke-width="0.1" fill="none"/>')
    out = place_image(load_image(_write(tmp_path, body)), cx=0.0, cy=0.0, sx=1.0, sy=1.0)
    assert "<polyline" in out and "<polygon" in out and "<path" in out
    assert "transform" not in out


def test_group_transform_is_baked(tmp_path):
    # A translate on a wrapping group must be folded into coordinates.
    body = '<g transform="translate(0.25,0)"><line x1="0" y1="0" x2="0" y2="0" stroke="#fff" stroke-width="0.1"/></g>'
    out = place_image(load_image(_write(tmp_path, body)), cx=0.0, cy=0.0, sx=1.0, sy=1.0)
    assert "transform" not in out
    assert 'x1="0.25"' in out


def test_rejects_circle(tmp_path):
    with pytest.raises(ImageError):
        load_image(_write(tmp_path, '<circle cx="0" cy="0" r="1"/>'))
