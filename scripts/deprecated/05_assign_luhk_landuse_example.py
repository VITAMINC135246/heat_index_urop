#!/usr/bin/env python3
"""Compatibility entry point for the revised pilot V/T overlay workflow."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def main() -> int:
    script_path = Path(__file__).with_name("05_assign_luhk_landuse_pilot_overlays.py")
    spec = importlib.util.spec_from_file_location("assign_luhk_landuse_pilot_overlays", script_path)
    if spec is None or spec.loader is None:
        print(f"Error: could not load {script_path}", file=sys.stderr)
        return 1
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    print(
        "Note: scripts/05_assign_luhk_landuse_example.py is now a compatibility "
        "wrapper. The active workflow is scripts/05_assign_luhk_landuse_pilot_overlays.py."
    )
    return int(module.main())


if __name__ == "__main__":
    sys.exit(main())
