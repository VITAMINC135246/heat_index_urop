#!/usr/bin/env python3
"""Helpers for invoking the supported artifact-tool workbook authoring stage."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from part_e_pixel_common import PROJECT_ROOT


BUILDER = PROJECT_ROOT / "scripts" / "part_e" / "build_part_e_workbooks.mjs"


def find_node() -> str:
    configured = os.environ.get("PART_E_NODE_EXE", "").strip()
    if configured and Path(configured).is_file():
        return configured
    detected = shutil.which("node")
    if detected:
        return detected
    raise RuntimeError("Node.js is required for artifact-tool workbook authoring.")


def ensure_artifact_tool() -> None:
    marker = PROJECT_ROOT / "scripts" / "part_e" / "node_modules" / "@oai" / "artifact-tool"
    if not marker.exists():
        raise RuntimeError(
            "The supported @oai/artifact-tool runtime is unavailable. Create an ignored "
            "scripts/part_e/node_modules junction to the workspace dependency runtime before running Excel stages."
        )


def run_builder(payload: dict[str, Any], payload_path: Path) -> None:
    ensure_artifact_tool()
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    command = [find_node(), "--max-old-space-size=8192", str(BUILDER), str(payload_path)]
    subprocess.run(command, cwd=BUILDER.parent, check=True)
