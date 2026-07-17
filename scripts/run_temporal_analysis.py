#!/usr/bin/env python3
"""Run the supported v0.3 capture-level temporal analysis."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.workflow.part_e_adapter import aggregate_canonical_results, manifest_paths_from_run_summary
from scripts.workflow.temporal_analysis import run_temporal_analysis


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--canonical-parquet")
    inputs.add_argument("--run-summary")
    inputs.add_argument("--manifest", action="append")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--timezone", required=True, help="IANA timezone, for example Asia/Hong_Kong.")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def main() -> int:
    args = parse_args()
    output_root = resolve(args.output_root)
    if args.canonical_parquet:
        canonical = resolve(args.canonical_parquet)
    else:
        manifests = [resolve(value) for value in (args.manifest or [])]
        if args.run_summary:
            manifests = manifest_paths_from_run_summary(resolve(args.run_summary))
        if not manifests:
            raise ValueError("No successful canonical manifests were found for temporal analysis.")
        canonical = output_root / "input" / "temporal_canonical_pixels.parquet"
        aggregate_canonical_results(
            manifests,
            output_parquet=canonical,
            summary_csv=output_root / "input" / "temporal_source_summary.csv",
        )
    result = run_temporal_analysis(
        canonical,
        output_root=output_root,
        default_timezone=args.timezone,
        resume=args.resume,
        dry_run=args.dry_run,
    )
    payload = result.to_dict() if hasattr(result, "to_dict") else result
    for key, value in payload.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
