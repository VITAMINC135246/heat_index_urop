"""Load numbered compatibility scripts without renaming their entry points."""

from __future__ import annotations

import importlib.util
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=None)
def load_numbered_script(relative_path: str, module_name: str) -> ModuleType:
    path = PROJECT_ROOT / relative_path
    if not path.is_file():
        raise FileNotFoundError(path)
    scripts_dir = str(PROJECT_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load compatibility script: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
