"""Portable physical data locations retain stable repository-relative identities."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from heat_index.config.paths import project_paths


@pytest.mark.unit
def test_default_data_root_and_non_data_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HEAT_INDEX_DATA_ROOT", raising=False)
    monkeypatch.delenv("HEAT_INDEX_LOCAL_CONFIG", raising=False)
    paths = project_paths(tmp_path)
    assert paths.data_root == tmp_path / "data"
    assert paths.resolve("data/raw/pilot.jpg") == tmp_path / "data/raw/pilot.jpg"
    assert paths.logical("data/raw/pilot.jpg") == Path("data/raw/pilot.jpg")
    assert paths.resolve("outputs/qa.json") == tmp_path / "outputs/qa.json"


@pytest.mark.integration
def test_local_override_and_environment_priority_preserve_logical_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_config = tmp_path / "config" / "paths.local.json"
    local_config.parent.mkdir()
    local_config.write_text(json.dumps({"data_root": "../local-pilot-data"}), encoding="utf-8")
    monkeypatch.delenv("HEAT_INDEX_DATA_ROOT", raising=False)
    monkeypatch.delenv("HEAT_INDEX_LOCAL_CONFIG", raising=False)
    local_paths = project_paths(tmp_path)
    assert local_paths.resolve("data/raw/pilot.jpg") == tmp_path.parent / "local-pilot-data/raw/pilot.jpg"
    assert local_paths.logical(local_paths.resolve("data/raw/pilot.jpg")) == Path("data/raw/pilot.jpg")

    external = tmp_path / "external-data"
    monkeypatch.setenv("HEAT_INDEX_DATA_ROOT", str(external))
    env_paths = project_paths(tmp_path)
    assert env_paths.resolve("data/raw/pilot.jpg") == external / "raw/pilot.jpg"
    assert env_paths.logical(external / "raw/pilot.jpg") == Path("data/raw/pilot.jpg")
    assert env_paths.resolve("outputs/qa.json") == tmp_path / "outputs/qa.json"


@pytest.mark.unit
@pytest.mark.skipif(os.name == "nt", reason="Windows drive paths are valid on Windows")
def test_windows_path_on_mac_or_linux_fails_intentionally(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Windows-only path"):
        project_paths(tmp_path).resolve(r"D:\raw\pilot.jpg")
