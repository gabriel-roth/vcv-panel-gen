"""Rack-free tests for screenshot.py's pure helpers and non-GUI paths.

Nothing here launches Rack, opens a window, or captures the screen. The GUI
paths (default/patch/live orchestration) are exercised by hand with the user's
consent, not in the automated suite.
"""
import json
import os

import numpy as np
import pytest
from PIL import Image

import screenshot
import shotmatch


# --- environment discovery ------------------------------------------------

def test_plugins_dirname_is_per_arch(monkeypatch):
    monkeypatch.setattr(screenshot.platform, "machine", lambda: "arm64")
    assert screenshot.plugins_dirname() == "plugins-mac-arm64"
    monkeypatch.setattr(screenshot.platform, "machine", lambda: "x86_64")
    assert screenshot.plugins_dirname() == "plugins-mac-x64"


def test_rack_binary_explicit_missing():
    with pytest.raises(screenshot.ScreenshotError, match="not found"):
        screenshot.rack_binary("/nope/Rack")


def test_rack_binary_explicit_present(tmp_path):
    b = tmp_path / "Rack"
    b.write_text("")
    assert screenshot.rack_binary(str(b)) == str(b)


def test_user_dir_prefers_explicit(monkeypatch):
    monkeypatch.delenv("RACK_USER_DIR", raising=False)
    assert screenshot.user_dir("/x/y") == "/x/y"
    monkeypatch.setenv("RACK_USER_DIR", "/from/env")
    assert screenshot.user_dir(None) == "/from/env"


def test_installed_plugin_dir_missing_lists_hint(tmp_path, monkeypatch):
    monkeypatch.setattr(screenshot, "plugins_dirname", lambda: "plugins-mac-arm64")
    with pytest.raises(screenshot.ScreenshotError, match="not installed"):
        screenshot.installed_plugin_dir("Ghost", str(tmp_path))


# --- scale candidates -----------------------------------------------------

def test_scale_candidates_centre_on_hint():
    cands = screenshot._scale_candidates(2.0)
    assert 2.0 in cands           # the hint itself
    assert any(abs(c - 1.8) < 1e-9 for c in cands)  # +/- around it
    assert 1.0 in cands and 2.0 in cands            # backing-scale fallbacks


# --- matched_crop over a synthetic window (no Rack) -----------------------

def _write_gray(path, arr):
    Image.fromarray((np.clip(arr, 0, 1) * 255).astype("uint8"), "L").save(path)


def test_matched_crop_finds_and_writes(tmp_path):
    rng = np.random.default_rng(0)
    tpl = np.zeros((380, 90), dtype=np.float32)
    yy, xx = np.mgrid[0:380, 0:90]
    tpl[(yy - 100) ** 2 + (xx - 45) ** 2 <= 400] = 0.9
    tpl[300:320, 10:80] = 0.7
    tpl += rng.normal(0, 0.01, tpl.shape).astype(np.float32)
    tpl = np.clip(tpl, 0, 1)

    window = rng.uniform(0.15, 0.25, (900, 700)).astype(np.float32)
    window[120:500, 200:290] = tpl  # place at (x=200, y=120), scale 1
    window += rng.normal(0, 0.01, window.shape).astype(np.float32)
    window = np.clip(window, 0, 1)

    tpl_png = tmp_path / "tpl.png"
    win_png = tmp_path / "win.png"
    out_png = tmp_path / "out.png"
    _write_gray(tpl_png, tpl)
    _write_gray(win_png, window)

    match = screenshot.matched_crop(str(win_png), str(tpl_png), str(out_png),
                                    scale_hint=1.0, min_score=0.5)
    assert abs(match.x - 200) <= 2 and abs(match.y - 120) <= 2
    assert Image.open(out_png).size == (90, 380)


def test_matched_crop_raises_below_min_score(tmp_path):
    rng = np.random.default_rng(1)
    tpl = np.clip(rng.normal(0.5, 0.2, (200, 60)), 0, 1).astype(np.float32)
    window = rng.uniform(0, 0.3, (600, 400)).astype(np.float32)  # template absent
    tpl_png, win_png, out_png = (tmp_path / n for n in ("t.png", "w.png", "o.png"))
    _write_gray(tpl_png, tpl)
    _write_gray(win_png, window)
    with pytest.raises(screenshot.ScreenshotError, match="confidently locate"):
        screenshot.matched_crop(str(win_png), str(tpl_png), str(out_png),
                                scale_hint=1.0, min_score=0.5)
    assert not out_png.exists()


# --- live zoom hint -------------------------------------------------------

def test_live_zoom_hint_reads_autosave(tmp_path):
    os.makedirs(tmp_path / "autosave")
    (tmp_path / "autosave" / "patch.json").write_text(json.dumps({"zoom": 1.75}))
    assert screenshot.live_zoom_hint(str(tmp_path)) == 1.75


def test_live_zoom_hint_defaults_when_absent(tmp_path):
    assert screenshot.live_zoom_hint(str(tmp_path)) == 1.0


# --- GUI user-dir prep (filesystem only, no launch) -----------------------

def test_prepare_gui_user_dir_links_plugins_and_sets_window(tmp_path, monkeypatch):
    monkeypatch.setattr(screenshot, "plugins_dirname", lambda: "plugins-mac-arm64")
    real = tmp_path / "real"
    os.makedirs(real / "plugins-mac-arm64" / "SomePlugin")
    (real / "settings.json").write_text(json.dumps({"zoom": 9, "windowSize": [1, 1]}))

    gui = screenshot._prepare_gui_user_dir(str(real))
    try:
        link = os.path.join(gui, "plugins-mac-arm64")
        assert os.path.islink(link)
        assert os.path.isdir(os.path.join(link, "SomePlugin"))
        s = json.load(open(os.path.join(gui, "settings.json")))
        assert s["windowMaximized"] is True
        assert s["checkVersion"] is False
        assert s["zoom"] == 9  # preserved from the real settings
    finally:
        import shutil
        shutil.rmtree(gui, ignore_errors=True)


# --- CLI error handling ---------------------------------------------------

def test_cli_reports_patch_error_without_launching(tmp_path, capsys, monkeypatch):
    # a .vcv whose module isn't present -> PatchError before any Rack launch
    import io, tarfile, zstandard
    patch = {"modules": [{"plugin": "A", "model": "B", "pos": [0, 0]}]}
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        data = json.dumps(patch).encode()
        info = tarfile.TarInfo("./patch.json")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    vcv = tmp_path / "p.vcv"
    vcv.write_bytes(zstandard.ZstdCompressor().compress(buf.getvalue()))

    fake_rack = tmp_path / "Rack"
    fake_rack.write_text("")
    # guard: fail loudly if anything tries to launch a process
    monkeypatch.setattr(screenshot.subprocess, "Popen",
                        lambda *a, **k: pytest.fail("must not launch Rack"))

    rc = screenshot.main(["patch", "--file", str(vcv), "--plugin", "X",
                          "--module", "Y", "--out", str(tmp_path / "o.png"),
                          "--rack", str(fake_rack), "--user-dir", str(tmp_path)])
    assert rc == 1
    assert "no module X:Y" in capsys.readouterr().err
