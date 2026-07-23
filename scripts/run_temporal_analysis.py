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
from scripts.workflow.temporal_analysis import (
    TemporalAnalysisPlan,
    parse_temporal_plan,
    run_temporal_analysis,
)
from scripts.workflow.temporal_interactive import collect_temporal_plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--canonical-parquet")
    inputs.add_argument("--run-summary")
    inputs.add_argument("--manifest", action="append")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--timezone", required=True, help="IANA timezone, for example Asia/Hong_Kong.")
    parser.add_argument(
        "--temporal",
        choices=("no", "yes", "ask"),
        default="no",
        help=(
            "Temporal analysis is opt-in. 'no' is the safe default; 'ask' prompts the user; "
            "'yes' starts the same confirmation workflow without the initial yes/no question."
        ),
    )
    parser.add_argument(
        "--interactive-temporal",
        action="store_true",
        help="Alias for --temporal ask. Requires --manifest or --run-summary so source evidence can be shown.",
    )
    parser.add_argument(
        "--temporal-plan",
        help="Programmatic JSON plan containing explicit same-location groups; never inferred from the input data.",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def select_temporal_plan(
    args: argparse.Namespace,
    manifest_paths: list[Path],
) -> TemporalAnalysisPlan:
    """Resolve the explicit opt-in; never create groups from canonical metadata."""

    if args.temporal_plan:
        if args.interactive_temporal or args.temporal != "no":
            raise ValueError("Use either --temporal-plan or interactive temporal confirmation, not both.")
        return parse_temporal_plan(resolve(args.temporal_plan))
    if args.interactive_temporal and args.temporal != "no":
        raise ValueError("--interactive-temporal is an alias for --temporal ask; use only one of them.")

    mode = "ask" if args.interactive_temporal else args.temporal
    if mode == "no":
        print("Temporal analysis was not requested. No temporal groups or figures will be created.", flush=True)
        return TemporalAnalysisPlan(temporal_requested=False)
    if not manifest_paths:
        raise ValueError(
            "Interactive temporal confirmation requires --manifest or --run-summary so visible/thermal paths, "
            "capture metadata, and spatial evidence can be shown. With --canonical-parquet, use a reviewed "
            "--temporal-plan or keep the default --temporal no."
        )
    return collect_temporal_plan(
        manifest_paths,
        requested=True if mode == "yes" else None,
    )


def main() -> int:
    args = parse_args()
    output_root = resolve(args.output_root)
    manifests: list[Path] = []
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
    temporal_plan = select_temporal_plan(args, manifests)
    result = run_temporal_analysis(
        canonical,
        output_root=output_root,
        default_timezone=args.timezone,
        plan=temporal_plan,
        resume=args.resume,
        dry_run=args.dry_run,
    )
    payload = result.to_dict() if hasattr(result, "to_dict") else result
    for key, value in payload.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        exit_code = 2
    raise SystemExit(exit_code)
