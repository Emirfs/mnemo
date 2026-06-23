"""Marker-based project resolution: .mnemo-project lets repos share a project."""

from __future__ import annotations

import subprocess
from pathlib import Path

from mnemo.vault import detect_project


def test_marker_overrides_folder(tmp_path: Path):
    repo = tmp_path / "some-repo-name"
    repo.mkdir()
    (repo / ".mnemo-project").write_text("stm32-rf-ota\n", encoding="utf-8")
    assert detect_project(repo) == "stm32-rf-ota"


def test_marker_found_walking_up(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / "src" / "deep").mkdir(parents=True)
    (repo / ".git").mkdir()  # git root boundary
    (repo / ".mnemo-project").write_text("shared\n", encoding="utf-8")
    assert detect_project(repo / "src" / "deep") == "shared"


def test_no_marker_falls_back_to_folder(tmp_path: Path):
    repo = tmp_path / "plainfolder"
    repo.mkdir()
    # no marker, no git remote -> folder name
    assert detect_project(repo) == "plainfolder"


def test_marker_stops_at_git_root(tmp_path: Path):
    # marker above the git root must NOT leak into the repo
    (tmp_path / ".mnemo-project").write_text("outer\n", encoding="utf-8")
    repo = tmp_path / "inner"
    repo.mkdir()
    (repo / ".git").mkdir()
    # inner has its own folder name (git remote absent) and should not see 'outer'
    assert detect_project(repo) != "outer"
