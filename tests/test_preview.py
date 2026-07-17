import os
import sys
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import preview


def _asset_svg(fill):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="30px" '
            f'height="30px" viewBox="0 0 30 30"><circle cx="15" cy="15" '
            f'r="10" fill="{fill}"/></svg>')

_PANEL_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" '
    'xmlns:xlink="http://www.w3.org/1999/xlink" '
    'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
    'width="50mm" height="50mm" viewBox="0 0 50 50">\n'
    '  <g inkscape:label="components" id="components" style="display:none">\n'
    '    <circle id="A_PARAM#RoundBlackKnob" cx="10" cy="10" r="2" fill="#ff0000"/>\n'
    '    <circle id="B_PARAM#RoundBlackKnob" cx="30" cy="10" r="2" fill="#ff0000"/>\n'
    '    <circle id="C_PARAM#RoundBlackKnob" cx="20" cy="30" r="2" fill="#ff0000"/>\n'
    '  </g>\n'
    '</svg>\n'
)


def _fake_library(tmp_path):
    lib = tmp_path / "ComponentLibrary"
    lib.mkdir()
    (lib / "RoundBlackKnob_bg.svg").write_text(_asset_svg("#111"))
    (lib / "RoundBlackKnob.svg").write_text(_asset_svg("#333"))
    return lib


def test_preview_dedupes_repeated_assets_into_defs(tmp_path):
    # Three identical knobs share two assets (bg + body). Each asset's base64
    # payload must be embedded exactly once (in <defs>), referenced by <use>.
    preview._px_size.cache_clear()
    preview._data_uri.cache_clear()
    lib = _fake_library(tmp_path)
    src = tmp_path / "Panel.svg"
    src.write_text(_PANEL_SVG)
    out, missing = preview.build_preview(str(src), str(lib))

    assert missing == []
    ET.fromstring(out)  # well-formed XML

    # Two unique assets -> two <image> defs, regardless of the 3 placements.
    assert out.count("<image ") == 2
    # 3 knobs x 2 assets each = 6 placements, all lightweight <use> refs.
    assert out.count("<use ") == 6
    # The (identical) asset payload is embedded once per asset, not per use.
    b64 = preview._data_uri(str(lib / "RoundBlackKnob.svg")).split(",", 1)[1]
    assert out.count(b64) == 1


def test_conventional_libraries_nonempty():
    assert preview.CONVENTIONAL_LIBRARIES
    assert all(isinstance(p, str) for p in preview.CONVENTIONAL_LIBRARIES)


def test_default_library_prefers_existing(tmp_path):
    existing = str(tmp_path)
    missing = str(tmp_path / "does-not-exist")
    assert preview.default_library([missing, existing]) == existing


def test_default_library_falls_back_to_first_when_none_exist(tmp_path):
    a = str(tmp_path / "nope-a")
    b = str(tmp_path / "nope-b")
    assert preview.default_library([a, b]) == a
