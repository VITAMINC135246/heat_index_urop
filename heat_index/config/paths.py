"""One logical data-root boundary for research inputs and generated data."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

DATA_ROOT_ENV = "HEAT_INDEX_DATA_ROOT"
LOCAL_PATHS_ENV = "HEAT_INDEX_LOCAL_CONFIG"


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _absolute(value: str | Path, root: Path) -> Path:
    raw = str(value)
    if os.name != "nt" and PureWindowsPath(raw).drive:
        raise ValueError(f"Windows-only path on this host: {raw}. Configure a local {DATA_ROOT_ENV} instead.")
    path = Path(raw).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


@dataclass(frozen=True)
class ProjectPaths:
    project_root: Path
    data_root: Path

    def resolve(self, value: str | Path) -> Path:
        """Resolve a repository-relative path, redirecting only its data/ prefix."""
        path = Path(value)
        if path.is_absolute():
            return path
        if os.name != "nt" and PureWindowsPath(str(value)).drive:
            raise ValueError(f"Windows-only path on this host: {value}")
        if path.parts and path.parts[0] == "data":
            return self.data_root.joinpath(*path.parts[1:])
        return self.project_root / path

    def logical(self, value: str | Path) -> Path:
        """Return a stable repository-relative identity for a physical path."""
        path = self.resolve(value).resolve()
        try:
            return Path("data") / path.relative_to(self.data_root)
        except ValueError:
            try:
                return path.relative_to(self.project_root)
            except ValueError:
                return path


def project_paths(project_root: Path | None = None) -> ProjectPaths:
    root = (project_root or repository_root()).resolve()
    configured = os.environ.get(DATA_ROOT_ENV, "").strip()
    if not configured:
        config_path = _absolute(os.environ.get(LOCAL_PATHS_ENV, "config/paths.local.json"), root)
        if config_path.is_file():
            config = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(config, dict):
                raise ValueError(f"Local paths config must be a JSON object: {config_path}")
            configured = str(config.get("data_root", "")).strip()
    data = _absolute(configured, root) if configured else root / "data"
    return ProjectPaths(root, data)


def data_root(project_root: Path | None = None) -> Path:
    return project_paths(project_root).data_root


def resolve_path(value: str | Path, project_root: Path | None = None) -> Path:
    return project_paths(project_root).resolve(value)


def logical_path(value: str | Path, project_root: Path | None = None) -> Path:
    return project_paths(project_root).logical(value)
