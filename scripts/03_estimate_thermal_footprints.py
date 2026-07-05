#!/usr/bin/env python3
"""Compatibility entry point for the revised V/T image footprint workflow."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def main() -> int:
    script_path = Path(__file__).with_name("03_estimate_image_footprints.py")
    spec = importlib.util.spec_from_file_location("estimate_image_footprints", script_path)
    if spec is None or spec.loader is None:
        print(f"Error: could not load {script_path}", file=sys.stderr)
        return 1
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    print(
        "Note: scripts/03_estimate_thermal_footprints.py is now a compatibility "
        "wrapper. The active workflow is scripts/03_estimate_image_footprints.py."
    )
    return int(module.main())


if __name__ == "__main__":
    sys.exit(main())
