#!/usr/bin/env python3
"""Run separate temporary TAT3 manual point/region analysis."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.workflow.input_validation import image_identifier
from scripts.workflow.luhk_context import resolve_luhk_context
from scripts.workflow.tat3_manual_measurement import parse_tat3_report, write_temporary_tat3_bundle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, help="TAT3 DOCX or textual measurement report.")
    parser.add_argument("--thermal-image", help="Optional thermal image evidence path.")
    parser.add_argument("--image-id", default="", help="Expected image ID when a thermal path is unavailable.")
    parser.add_argument("--target-name", required=True)
    parser.add_argument("--luhk", required=True, help="Controlled LUHK category code or name.")
    parser.add_argument(
        "--luhk-provenance",
        required=True,
        choices=["official_luhk_lookup", "user_supplied_luhk"],
    )
    parser.add_argument("--surface-cover", required=True)
    parser.add_argument("--screenshot", help="Optional annotated TAT3 screenshot evidence.")
    parser.add_argument("--notes", default="")
    parser.add_argument("--output-dir", help="Explicit temporary/export bundle directory.")
    return parser.parse_args()


def validate_surface_cover(value: str) -> str:
    mapping_path = PROJECT_ROOT / "data" / "annotations" / "part_c" / "surface_cover_class_mapping.xlsx"
    table = pd.read_excel(mapping_path)
    allowed = {
        str(row.class_name).casefold(): str(row.class_name)
        for row in table.itertuples(index=False)
        if int(row.class_id) not in {0, 9}
    }
    if value.casefold() not in allowed:
        raise ValueError(f"Unknown physical surface-cover category: {value}")
    return allowed[value.casefold()]


def main() -> int:
    args = parse_args()
    thermal_path = Path(args.thermal_image).expanduser().resolve() if args.thermal_image else None
    image_id = args.image_id.strip()
    if thermal_path:
        if not thermal_path.is_file():
            raise FileNotFoundError(thermal_path)
        path_id = image_identifier(thermal_path)
        if image_id and image_id != path_id:
            raise ValueError(f"Thermal image ID {path_id} does not match --image-id {image_id}.")
        image_id = path_id
    if not image_id:
        raise ValueError("Provide --thermal-image or --image-id.")
    luhk = resolve_luhk_context(args.luhk, args.luhk_provenance)
    surface_cover = validate_surface_cover(args.surface_cover)
    report = Path(args.report).expanduser().resolve()
    screenshot = Path(args.screenshot).expanduser().resolve() if args.screenshot else None
    if screenshot and not screenshot.is_file():
        raise FileNotFoundError(screenshot)
    result = parse_tat3_report(
        report,
        expected_image_id=image_id,
        target_name=args.target_name,
        luhk_code=luhk.code,
        luhk_category=luhk.category,
        luhk_provenance=luhk.provenance.value,
        surface_cover_category=surface_cover,
        screenshot_path=screenshot,
        notes=args.notes,
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else PROJECT_ROOT / "outputs" / "runs" / f"tat3_{stamp}" / "temporary_tat3"
    )
    paths = write_temporary_tat3_bundle(result, output)
    print(f"TAT3 layout: {result.manifest['measurement_layout_status']}")
    print(f"Measurement records: {len(result.measurements)}")
    print(f"Persistence scope: temporary_session")
    print(f"Temporary manifest: {paths['manifest']}")
    print(f"Temporary analysis: {paths['analysis']}")
    if paths["plot"].is_file():
        print(f"Measurement plot: {paths['plot']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
