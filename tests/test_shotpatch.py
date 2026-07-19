"""Patch-viewport derivation, tested Rack-free on plain dicts."""
import pytest

import shotpatch


def _patch():
    return {
        "version": "2.6.6",
        "zoom": 1.4142,
        "gridOffset": [15.98, 0.85],
        "modules": [
            {"plugin": "Core", "model": "AudioInterface2", "pos": [59, 0]},
            {"plugin": "Acme", "model": "Widget", "pos": [12, 1]},
            {"plugin": "Acme", "model": "Widget", "pos": [30, 2]},
        ],
    }


def test_find_module():
    m = shotpatch.find_module(_patch(), "Core", "AudioInterface2")
    assert m["pos"] == [59, 0]


def test_find_module_index_selects_duplicate():
    m = shotpatch.find_module(_patch(), "Acme", "Widget", index=1)
    assert m["pos"] == [30, 2]


def test_find_module_missing_lists_contents():
    with pytest.raises(shotpatch.PatchError) as e:
        shotpatch.find_module(_patch(), "Nope", "Nope")
    assert "Acme:Widget" in str(e.value)
    assert "Core:AudioInterface2" in str(e.value)


def test_find_module_index_out_of_range():
    with pytest.raises(shotpatch.PatchError):
        shotpatch.find_module(_patch(), "Acme", "Widget", index=5)


def test_derive_pins_zoom_and_offset_to_module_pos():
    patch = _patch()
    out, pos = shotpatch.derive_patch(patch, "Acme", "Widget", index=1)
    assert pos == [30, 2]
    assert out["zoom"] == 1.0
    assert out["gridOffset"] == [30.0, 2.0]


def test_derive_respects_zoom_arg():
    out, _ = shotpatch.derive_patch(_patch(), "Core", "AudioInterface2", zoom=2.0)
    assert out["zoom"] == 2.0
    assert out["gridOffset"] == [59.0, 0.0]


def test_derive_does_not_mutate_input():
    patch = _patch()
    shotpatch.derive_patch(patch, "Core", "AudioInterface2")
    assert patch["zoom"] == 1.4142
    assert patch["gridOffset"] == [15.98, 0.85]
