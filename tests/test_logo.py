import os
import re
import sys
import textwrap
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import logo as L


def write_logo(tmp_path, text, name="logo.svg"):
    p = tmp_path / name
    p.write_text(textwrap.dedent(text))
    return str(p)


# A minimal square logo in a clean 0..10 viewBox, no internal transform.
SQUARE = """
    <?xml version="1.0"?>
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">
      <path d="M0 0 L10 0 L10 10 L0 10 Z"/>
    </svg>
"""


def bbox(svg_fragment):
    xs, ys = [], []
    for d in re.findall(r'd="([^"]*)"', svg_fragment):
        nums = [float(x) for x in re.findall(r'[-+]?(?:\d*\.\d+|\d+\.?)', d)]
        xs += nums[0::2]; ys += nums[1::2]
    return min(xs), min(ys), max(xs), max(ys)


# --- transform parsing -------------------------------------------------------

def test_parse_translate_scale_compose():
    # translate then scale: point (1,1) -> scale to (2,2) -> translate (+5,+5)
    aff = L._parse_transform("translate(5 5) scale(2)")
    a, b, c, d, e, f = aff
    assert (a * 1 + c * 1 + e, b * 1 + d * 1 + f) == (7.0, 7.0)


def test_parse_matrix_and_negative_scale():
    aff = L._parse_transform("matrix(0.1 0 0 -0.1 -73 216)")
    assert aff == (0.1, 0.0, 0.0, -0.1, -73.0, 216.0)


def test_parse_rejects_unknown_function():
    with pytest.raises(L.LogoError):
        L._parse_transform("skewX(10)")


# --- load_logo ---------------------------------------------------------------

def test_load_reads_viewbox_and_paths(tmp_path):
    lg = L.load_logo(write_logo(tmp_path, SQUARE))
    assert (lg.minx, lg.miny, lg.width, lg.height) == (0.0, 0.0, 10.0, 10.0)
    assert len(lg.paths) == 1
    assert lg.transform == L.IDENTITY


def test_load_composes_group_transform(tmp_path):
    lg = L.load_logo(write_logo(tmp_path, """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 366 154">
          <g transform="translate(-73,216) scale(0.1,-0.1)" fill="#000000">
            <path d="M2070 2015 l0 -145 z"/>
          </g>
        </svg>
    """))
    assert lg.transform == (0.1, 0.0, 0.0, -0.1, -73.0, 216.0)
    assert len(lg.paths) == 1


def test_load_missing_viewbox_errors(tmp_path):
    with pytest.raises(L.LogoError, match="viewBox"):
        L.load_logo(write_logo(tmp_path, """
            <svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0 L1 1"/></svg>
        """))


def test_load_no_path_errors(tmp_path):
    with pytest.raises(L.LogoError, match="drawable"):
        L.load_logo(write_logo(tmp_path, """
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>
        """))


def test_load_rejects_non_path_shapes(tmp_path):
    with pytest.raises(L.LogoError, match="rect"):
        L.load_logo(write_logo(tmp_path, """
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">
              <rect x="0" y="0" width="5" height="5"/>
            </svg>
        """))


# --- baking ------------------------------------------------------------------

def test_bake_identity_absolute():
    assert L._bake_path("M0 0 L10 0 L10 10 Z", L.IDENTITY) == \
        "M 0 0 L 10 0 L 10 10 Z"


def test_bake_relative_lineto_resolved_to_absolute():
    # M then relative 'l' deltas become absolute L points.
    assert L._bake_path("M5 5 l5 0 l0 5 z", L.IDENTITY) == \
        "M 5 5 L 10 5 L 10 10 Z"


def test_bake_implicit_moveto_linetos():
    # extra pairs after M are implicit linetos
    assert L._bake_path("M0 0 10 0 10 10", L.IDENTITY) == \
        "M 0 0 L 10 0 L 10 10"


def test_bake_h_and_v_become_line_endpoints():
    assert L._bake_path("M0 0 H10 V10", L.IDENTITY) == \
        "M 0 0 L 10 0 L 10 10"


def test_bake_cubic_scaled_and_translated():
    aff = (2.0, 0.0, 0.0, 2.0, 1.0, 1.0)
    assert L._bake_path("M0 0 C1 1 2 2 3 3", aff) == \
        "M 1 1 C 3 3 5 5 7 7"


def test_bake_rejects_arc():
    with pytest.raises(L.LogoError, match="A"):
        L._bake_path("M0 0 A5 5 0 0 1 10 10", L.IDENTITY)


def test_bake_negative_scale_flips_y():
    # potrace's scale(0.1,-0.1) translate(0,10): y flips about origin then shifts
    aff = L._parse_transform("translate(0,10) scale(1,-1)")
    assert L._bake_path("M0 0 L0 5", aff) == "M 0 10 L 0 5"


# --- place_logo --------------------------------------------------------------

def test_place_centers_scales_and_positions(tmp_path):
    lg = L.load_logo(write_logo(tmp_path, SQUARE))
    frag = L.place_logo(lg, cx=30.0, top=2.0, target_h=6.0, fill="#ffffff")
    minx, miny, maxx, maxy = bbox(frag)
    assert (maxy - miny) == pytest.approx(6.0)       # scaled to target height
    assert (maxx - minx) == pytest.approx(6.0)       # square stays square
    assert (minx + maxx) / 2 == pytest.approx(30.0)  # centered on cx
    assert miny == pytest.approx(2.0)                # top edge at `top`


def test_place_emits_fill_and_no_transform(tmp_path):
    lg = L.load_logo(write_logo(tmp_path, SQUARE))
    frag = L.place_logo(lg, cx=30.0, top=2.0, target_h=6.0, fill="#abcdef")
    assert 'fill="#abcdef"' in frag
    assert "transform=" not in frag
    assert frag.count("<path") == 1
