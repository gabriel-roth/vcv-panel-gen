"""Doc-example test: the worked example printed in AGENTS.md (section 9)
must actually build clean (no errors, no warnings) and produce the component
ids that section quotes verbatim. If this spec ever needs to change, update
AGENTS.md's copy in the same commit.
"""
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import panelgen

_AGENTS_MD_EXAMPLE = """\
slug: Example
name: DEMO
hp: 10

elements:
  - {text: Level, x: 25.4, y: 40}
  - {name: LEVEL_PARAM, x: 25.4, y: 50}
  - {name: LEVEL_CV_INPUT, x: 25.4, y: 65}
  - {text: CV, x: 25.4, y: 73.5}

connectors:
  - [LEVEL_PARAM, LEVEL_CV_INPUT]
"""


@pytest.fixture(autouse=True)
def _isolate_conventional_theme(tmp_path, monkeypatch):
    fake_conventional = str(tmp_path / "no-such-conventional-theme.yaml")
    monkeypatch.setattr(panelgen, "CONVENTIONAL_THEME", fake_conventional)


def test_agents_md_worked_example_builds_clean(tmp_path):
    spec_path = tmp_path / "example.yaml"
    spec_path.write_text(_AGENTS_MD_EXAMPLE)
    out_path = tmp_path / "out" / "Demo.svg"

    report = panelgen.generate(str(spec_path), str(out_path))

    assert report.errors == []
    assert report.warnings == []
    svg = out_path.read_text()
    assert 'id="LEVEL_PARAM#RoundBlackKnob"' in svg
    assert 'id="LEVEL_CV_INPUT#PJ301MPort"' in svg
