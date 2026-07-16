#!/usr/bin/env python3
"""Finalize workbooks with Excel COM, create PivotTables, and export native charts."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from part_e_pixel_common import PROJECT_ROOT, project_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/part_e_delta_t_analysis.json")
    parser.add_argument("--main-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = project_path(args.config)
    script = PROJECT_ROOT / "scripts" / "part_e" / "06_finalize_excel_workbooks.ps1"
    command = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
        "-ProjectRoot", str(PROJECT_ROOT), "-ConfigPath", str(config_path),
    ]
    if args.main_only:
        command.extend(["-SkipPixelWorkbooks", "-SkipPixelValidation"])
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
