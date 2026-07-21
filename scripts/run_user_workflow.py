#!/usr/bin/env python3
"""Ordinary-user launcher for the five pilots and football-field workflow."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PILOT_TABLE = PROJECT_ROOT / "data" / "metadata" / "part_b_pilot_pairs.xlsx"


def resolve(value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def pilot_groups() -> list[tuple[Path, Path]]:
    table = pd.read_excel(PILOT_TABLE)
    groups: list[tuple[Path, Path]] = []
    for row in table.itertuples(index=False):
        groups.append((resolve(row.v_path), resolve(row.t_path)))
    if len(groups) != 5:
        raise ValueError(f"The accepted pilot table must contain exactly five images; found {len(groups)}.")
    return groups


def image_id(thermal_path: Path) -> str:
    name = thermal_path.stem
    return name[:-2] if name.casefold().endswith("_t") else name


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Run real inputs without writing workflow config, review JSON, or ambient JSON files."
    )
    result.add_argument("--production", action="store_true", help="Write normal production outputs instead of isolated acceptance outputs.")
    result.add_argument("--open-results", action="store_true", help="Open the newest run folder in Explorer after completion.")
    subparsers = result.add_subparsers(dest="workflow")
    subparsers.add_parser("five-pilots", help="Run the five accepted real pilot image pairs through canonical output and Part E.")
    for name in ("soccer", "all"):
        child = subparsers.add_parser(
            name,
            help="Run the football field only." if name == "soccer" else "Run five pilots plus the football field.",
        )
        child.add_argument("visible", help="Football-field visible JPG.")
        child.add_argument("thermal", help="Matching football-field thermal JPG.")
        child.add_argument("tat3_report", help="TAT3 DOCX containing this thermal image's extraction parameters.")
        child.add_argument("--target-name", default="HKUST football field")
        child.add_argument("--target-id", default="hkust-football-field-natural-turf")
        child.add_argument("--surface-cover", default="grass_low_vegetation")
        child.add_argument("--luhk", default="GIC / open space")
        child.add_argument("--confidence", choices=["low", "medium", "high"], default="medium")
    group = subparsers.add_parser("group", help="Explore one visible/thermal input group interactively.")
    group.add_argument("visible")
    group.add_argument("thermal")
    group.add_argument("--tat3-report", default="")
    dataset = subparsers.add_parser("dataset", help="Explore every image group in a dataset directory interactively.")
    dataset.add_argument("dataset")
    dataset.add_argument("--tat3-report", default="")
    return result


def ask(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


def interactive_session() -> argparse.Namespace:
    print("What do you want to explore this time?", flush=True)
    print("  1) Five accepted pilot images", flush=True)
    print("  2) Football field", flush=True)
    print("  3) Five pilots + football field", flush=True)
    print("  4) One visible/thermal group", flush=True)
    print("  5) A dataset directory", flush=True)
    choices = {"1": "five-pilots", "2": "soccer", "3": "all", "4": "group", "5": "dataset"}
    selection = ""
    while selection not in choices:
        selection = input("Choose 1-5: ").strip()
    workflow = choices[selection]
    common: dict[str, object] = {"workflow": workflow, "production": False, "open_results": True}
    if workflow in {"soccer", "all"}:
        base = PROJECT_ROOT / "data" / "raw" / "HKUST" / "20260202_Thermal_HKUST" / "DCIM" / "DJI_202602020853_001"
        common.update(
            {
                "visible": ask("Football-field visible JPG", str(base / "DJI_20260202091127_0058_V.JPG")),
                "thermal": ask("Football-field thermal JPG", str(base / "DJI_20260202091128_0058_T.JPG")),
                "tat3_report": ask(
                    "TAT3 DOCX report",
                    str(
                        PROJECT_ROOT
                        / "data"
                        / "local_external"
                        / "tat3_reports"
                        / "raw"
                        / "combined_report__2026_07_17_18_12_48.docx"
                    ),
                ),
                "target_name": ask("Target name", "HKUST football field"),
                "target_id": ask("Stable target ID", "hkust-football-field-natural-turf"),
                "surface_cover": ask("Surface cover", "grass_low_vegetation"),
                "luhk": ask("LUHK category", "GIC / open space"),
                "confidence": ask("Reviewer confidence (low/medium/high)", "medium"),
            }
        )
    elif workflow == "group":
        common.update(
            {
                "visible": ask("Visible image path"),
                "thermal": ask("Thermal image path"),
                "tat3_report": ask("TAT3 DOCX report (press Enter if a legacy matrix already exists)"),
            }
        )
    elif workflow == "dataset":
        common.update(
            {
                "dataset": ask("Dataset directory"),
                "tat3_report": ask("Combined TAT3 DOCX report (optional)"),
            }
        )
    return argparse.Namespace(**common)


def build_command(args: argparse.Namespace) -> list[str]:
    config = "config/workflow_v0_3.json" if args.production else "config/workflow_v0_3_acceptance.json"
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "run_analysis.py"),
        "--config",
        config,
        "--require-all-success",
        "--interactive",
    ]
    groups: list[tuple[Path, Path]] = []
    if args.workflow in {"five-pilots", "all"}:
        groups.extend(pilot_groups())
    if args.workflow in {"soccer", "all"}:
        visible = resolve(args.visible)
        thermal = resolve(args.thermal)
        report = resolve(args.tat3_report)
        for path, label in ((visible, "visible image"), (thermal, "thermal image"), (report, "TAT3 report")):
            if not path.is_file():
                raise FileNotFoundError(f"Football-field {label} does not exist: {path}")
        command.extend(
            [
                "--tat3-report",
                str(report),
                "--polygon-image-id",
                image_id(thermal),
                "--surface-cover",
                args.surface_cover,
                "--target-name",
                args.target_name,
                "--target-id",
                args.target_id,
                "--luhk",
                args.luhk,
                "--luhk-provenance",
                "user_supplied_luhk",
                "--reviewer-confidence",
                args.confidence,
            ]
        )
        groups.append((visible, thermal))
    if args.workflow == "group":
        visible = resolve(args.visible)
        thermal = resolve(args.thermal)
        for path, label in ((visible, "visible image"), (thermal, "thermal image")):
            if not path.is_file():
                raise FileNotFoundError(f"Group {label} does not exist: {path}")
        if args.tat3_report:
            command.extend(["--tat3-report", str(resolve(args.tat3_report))])
        command.append("--launch-part-c-gui")
        groups.append((visible, thermal))
    if args.workflow == "dataset":
        if args.tat3_report:
            command.extend(["--tat3-report", str(resolve(args.tat3_report))])
        command.extend(["--launch-part-c-gui", "dataset", "--dataset", str(resolve(args.dataset))])
        return command
    command.extend(["selected", "--dataset-id", f"user-{args.workflow}"])
    for visible, thermal in groups:
        command.extend(["--group", str(visible), str(thermal)])
    return command


def newest_run(production: bool) -> Path | None:
    root = PROJECT_ROOT / ("outputs/runs/v0_3" if production else "outputs/runs/v0_3_user_acceptance") / "workflow_runs"
    candidates = [path for path in root.glob("run_*") if path.is_dir()]
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


def main() -> int:
    args = interactive_session() if len(sys.argv) == 1 else parser().parse_args()
    if not args.workflow:
        args = interactive_session()
    command = build_command(args)
    print(f"Starting {args.workflow}: no user-authored JSON/config is required.", flush=True)
    completed = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    run = newest_run(args.production)
    if run:
        print(f"Run folder: {run}", flush=True)
        print(f"Open this guide first: {run / 'USER_RESULTS.md'}", flush=True)
        if args.open_results and os.name == "nt":
            os.startfile(run)  # type: ignore[attr-defined]
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
