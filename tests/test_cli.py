import os
import subprocess
import sys
import tempfile

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import panelgen
from checks import Report
from theme import ThemeError

PANELGEN_PY = os.path.join(REPO_ROOT, "panelgen.py")

# A path that is guaranteed not to exist, used to override the conventional
# theme lookup for subprocess-based tests below (see _run_cli). Never
# created by anything in this test module, so it stays absent for the life
# of the test run.
_NONEXISTENT_THEME_FILE = os.path.join(
    tempfile.gettempdir(), "vcv-panel-gen-test-isolation-nonexistent-theme.yaml")


# ---------------------------------------------------------------------------
# Isolation: no test in this module may read the real
# ~/.config/vcv-panel-gen/theme.yaml on the machine running the tests.
# In-process calls (generate()/check() called directly) go through this
# autouse fixture, which points panelgen.CONVENTIONAL_THEME at a nonexistent
# path under tmp_path. Subprocess calls (_run_cli) can't be reached by
# monkeypatch, so they get PANELGEN_THEME_FILE set in their environment
# instead (see _run_cli below).
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_conventional_theme(tmp_path, monkeypatch):
    fake_conventional = str(tmp_path / "no-such-conventional-theme.yaml")
    monkeypatch.setattr(panelgen, "CONVENTIONAL_THEME", fake_conventional)


# ---------------------------------------------------------------------------
# Spec fixtures — minimal YAML written to tmp_path for each scenario.
# ---------------------------------------------------------------------------

_GOOD_SPEC = """\
slug: test_cli_panel
name: Test CLI Panel
hp: 20
elements:
  - name: X_PARAM
    x: 40.0
    y: 60.0
"""

# RoundBlackKnob (default widget for a _PARAM) has true radius 4.8mm; at
# x=2.0 the knob's left edge (2.0 - 4.8 = -2.8) falls outside the panel,
# which run_checks reports as a bounds error (matches tests/test_checks.py).
_OFF_PANEL_SPEC = """\
slug: test_cli_off_panel
name: Test CLI Off Panel
hp: 20
elements:
  - name: X_PARAM
    x: 2.0
    y: 10.0
"""

# Two RoundBlackKnobs (r=4.8 each) 5.0mm apart overlap (depth 4.6mm) but both
# sit comfortably inside a 20 HP (101.6mm) panel — an OVERLAP warning with no
# bounds error.
_OVERLAP_SPEC = """\
slug: test_cli_overlap
name: Test CLI Overlap
hp: 20
elements:
  - name: A_PARAM
    x: 30.0
    y: 60.0
  - name: B_PARAM
    x: 35.0
    y: 60.0
"""

_THEME_YAML = """\
background: "#112233"
"""


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return str(p)


def _run_cli(*args):
    # PANELGEN_THEME_FILE points panelgen's conventional-theme lookup at a
    # path that doesn't exist, so a subprocess run never reads the real
    # ~/.config/vcv-panel-gen/theme.yaml on the machine running the tests
    # (monkeypatching panelgen.CONVENTIONAL_THEME in-process can't reach
    # across the process boundary, hence the env var).
    env = dict(os.environ, PANELGEN_THEME_FILE=_NONEXISTENT_THEME_FILE)
    result = subprocess.run(
        [sys.executable, PANELGEN_PY, *args],
        capture_output=True, text=True, env=env,
    )
    return result


# ---------------------------------------------------------------------------
# generate(): happy path
# ---------------------------------------------------------------------------

def test_generate_happy_path_writes_svg_and_returns_empty_errors(tmp_path):
    spec_path = _write(tmp_path, "panel.yaml", _GOOD_SPEC)
    out_path = str(tmp_path / "panel.svg")

    report = panelgen.generate(spec_path, out_path)

    assert isinstance(report, Report)
    assert report.errors == []
    assert os.path.exists(out_path)
    svg = open(out_path).read()
    assert "<svg" in svg
    # Isolation check: with no --theme and no conventional file present (the
    # autouse fixture points CONVENTIONAL_THEME at a nonexistent path), the
    # real user theme's background ("#3d3d3d" on this machine) must never
    # leak into output.
    assert "#3d3d3d" not in svg


# ---------------------------------------------------------------------------
# check(): validates without writing
# ---------------------------------------------------------------------------

def test_check_mode_writes_nothing(tmp_path):
    spec_path = _write(tmp_path, "panel.yaml", _GOOD_SPEC)
    before = set(os.listdir(tmp_path))

    report = panelgen.check(spec_path)

    assert isinstance(report, Report)
    assert report.errors == []
    after = set(os.listdir(tmp_path))
    assert before == after  # nothing new written


def test_check_cli_flag_exits_0_and_writes_nothing(tmp_path):
    spec_path = _write(tmp_path, "panel.yaml", _GOOD_SPEC)
    before = set(os.listdir(tmp_path))

    result = _run_cli(spec_path, "--check")

    assert result.returncode == 0, result.stderr
    after = set(os.listdir(tmp_path))
    assert before == after


# ---------------------------------------------------------------------------
# Off-panel spec: exit 1 via the real CLI subprocess
# ---------------------------------------------------------------------------

def test_off_panel_spec_exits_1_via_subprocess(tmp_path):
    spec_path = _write(tmp_path, "off_panel.yaml", _OFF_PANEL_SPEC)
    out_path = str(tmp_path / "off_panel.svg")

    result = _run_cli(spec_path, "--out", out_path)

    assert result.returncode == 1
    assert "ERROR" in result.stderr
    assert not os.path.exists(out_path)  # aborted before writing


# ---------------------------------------------------------------------------
# Overlap-only spec: exit 0, OVERLAP warning on stderr, file still written
# ---------------------------------------------------------------------------

def test_overlap_only_spec_exits_0_with_overlap_on_stderr(tmp_path):
    spec_path = _write(tmp_path, "overlap.yaml", _OVERLAP_SPEC)
    out_path = str(tmp_path / "overlap.svg")

    result = _run_cli(spec_path, "--out", out_path)

    assert result.returncode == 0, result.stderr
    assert "OVERLAP" in result.stderr
    assert "WARNING" in result.stderr
    assert os.path.exists(out_path)


# ---------------------------------------------------------------------------
# --theme: an explicit background is reflected in the output
# ---------------------------------------------------------------------------

def test_theme_background_reflected_in_output(tmp_path):
    spec_path = _write(tmp_path, "panel.yaml", _GOOD_SPEC)
    theme_path = _write(tmp_path, "theme.yaml", _THEME_YAML)
    out_path = str(tmp_path / "panel.svg")

    report = panelgen.generate(spec_path, out_path, theme_path=theme_path)

    assert report.errors == []
    svg = open(out_path).read()
    assert 'fill="#112233"' in svg


def test_conventional_theme_picked_up_when_theme_path_omitted(tmp_path, monkeypatch):
    # Covers the conventional-path branch of _load_theme_layer itself
    # (theme_path=None + CONVENTIONAL_THEME pointing at a real file) without
    # ever touching the actual ~/.config/vcv-panel-gen/theme.yaml: this test
    # points CONVENTIONAL_THEME at its own temp file with a background that
    # can't be confused with the real user theme's "#3d3d3d".
    conventional_theme = _write(tmp_path, "conventional-theme.yaml",
                                 'background: "#00ff99"\n')
    monkeypatch.setattr(panelgen, "CONVENTIONAL_THEME", conventional_theme)

    spec_path = _write(tmp_path, "panel.yaml", _GOOD_SPEC)
    out_path = str(tmp_path / "panel.svg")

    report = panelgen.generate(spec_path, out_path)

    assert report.errors == []
    svg = open(out_path).read()
    assert 'fill="#00ff99"' in svg


def test_theme_flag_via_cli(tmp_path):
    spec_path = _write(tmp_path, "panel.yaml", _GOOD_SPEC)
    theme_path = _write(tmp_path, "theme.yaml", _THEME_YAML)
    out_path = str(tmp_path / "panel.svg")

    result = _run_cli(spec_path, "--out", out_path, "--theme", theme_path)

    assert result.returncode == 0, result.stderr
    svg = open(out_path).read()
    assert 'fill="#112233"' in svg


# ---------------------------------------------------------------------------
# Output-location guard: refuses writing inside this repo checkout
# ---------------------------------------------------------------------------

def test_guard_refuses_output_inside_repo(tmp_path):
    spec_path = _write(tmp_path, "panel.yaml", _GOOD_SPEC)
    bad_out = os.path.join(REPO_ROOT, "cli_guard_test_output.svg")

    try:
        with pytest.raises(panelgen.OutputLocationError):
            panelgen.generate(spec_path, bad_out)
        assert not os.path.exists(bad_out)
    finally:
        if os.path.exists(bad_out):
            os.remove(bad_out)


def test_guard_refuses_output_inside_repo_via_cli(tmp_path):
    spec_path = _write(tmp_path, "panel.yaml", _GOOD_SPEC)
    bad_out = os.path.join(REPO_ROOT, "cli_guard_test_output2.svg")

    try:
        result = _run_cli(spec_path, "--out", bad_out)
        assert result.returncode == 1
        assert "ERROR" in result.stderr
        assert not os.path.exists(bad_out)
    finally:
        if os.path.exists(bad_out):
            os.remove(bad_out)


def test_guard_raises_even_when_tool_root_is_under_tempdir(tmp_path, monkeypatch):
    # Regression test for the guard-ordering bug: _check_output_location
    # used to check the tempdir exemption before the inside-tool check, so a
    # checkout that itself lives under the system temp dir (TOOL_ROOT ends
    # up under tempfile.gettempdir()) would short-circuit out via the
    # tempdir exemption before ever reaching the inside-tool check, silently
    # neutering the guard. tmp_path already resolves under
    # tempfile.gettempdir() (that's the whole reason the tempdir exemption
    # exists), so it doubles as a stand-in "checkout living under /tmp"
    # here.
    fake_tool_root = tmp_path / "fake_checkout"
    fake_tool_root.mkdir()
    monkeypatch.setattr(panelgen, "TOOL_ROOT", os.path.realpath(str(fake_tool_root)))

    spec_path = _write(tmp_path, "panel.yaml", _GOOD_SPEC)
    bad_out = str(fake_tool_root / "out.svg")

    with pytest.raises(panelgen.OutputLocationError):
        panelgen.generate(spec_path, bad_out)
    assert not os.path.exists(bad_out)


# ---------------------------------------------------------------------------
# generate() raises (rather than swallowing) real spec errors
# ---------------------------------------------------------------------------

def test_generate_raises_spec_error_for_bad_spec(tmp_path):
    from spec import SpecError
    spec_path = _write(tmp_path, "bad.yaml", "not: a: valid: spec\n")
    out_path = str(tmp_path / "bad.svg")
    with pytest.raises((SpecError, Exception)):
        panelgen.generate(spec_path, out_path)


def test_check_raises_theme_error_for_bad_theme(tmp_path):
    spec_path = _write(tmp_path, "panel.yaml", _GOOD_SPEC)
    theme_path = _write(tmp_path, "theme.yaml", "background: not-a-hex-color\n")
    with pytest.raises(ThemeError):
        panelgen.check(spec_path, theme_path=theme_path)
