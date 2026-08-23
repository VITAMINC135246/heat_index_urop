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
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.workflow.input_validation import discover_dataset_groups  # noqa: E402

PILOT_TABLE = PROJECT_ROOT / "data" / "metadata" / "part_b_pilot_pairs.xlsx"


def resolve(value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def workflow_python() -> str:
    """Use console Python for the child so GUI launchers receive its live stdout."""
    executable = Path(sys.executable)
    if os.name == "nt" and executable.name.casefold() == "pythonw.exe":
        console = executable.with_name("python.exe")
        if console.is_file():
            return str(console)
    return str(executable)


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
        child.add_argument(
            "--redraw-polygon",
            action="store_true",
            help="Reopen Part C* even when a compatible accepted football-field result exists.",
        )
    group = subparsers.add_parser("group", help="Explore one visible/thermal input group interactively.")
    group.add_argument("visible")
    group.add_argument("thermal")
    group.add_argument("--tat3-report", action="append", default=[])
    group.add_argument(
        "--resume-part-c",
        default="",
        help="Resume a saved Part C superpixel_review.json draft for this thermal image.",
    )
    group.add_argument("--redraw-review", action="store_true", help="Reopen Part C/Part C* even if an accepted cache exists.")
    dataset = subparsers.add_parser("dataset", help="Explore every image group in a dataset directory interactively.")
    dataset.add_argument("dataset")
    dataset.add_argument("--tat3-report", action="append", default=[])
    dataset.add_argument("--redraw-review", action="store_true", help="Reopen accepted reviews for every selected group.")
    groups = subparsers.add_parser("groups", help="Explore several specific visible/thermal groups in one run.")
    groups.add_argument("--group", nargs=2, metavar=("VISIBLE", "THERMAL"), action="append", required=True)
    groups.add_argument("--tat3-report", action="append", default=[])
    groups.add_argument("--polygon-all", action="store_true", help="Use target-polygon Part C* for every selected group.")
    groups.add_argument("--target-name", default="")
    groups.add_argument("--target-id", default="")
    groups.add_argument("--surface-cover", default="grass_low_vegetation")
    groups.add_argument("--luhk", default="GIC / open space")
    groups.add_argument("--confidence", choices=["low", "medium", "high"], default="medium")
    groups.add_argument("--redraw-review", action="store_true", help="Reopen accepted reviews for all selected groups.")
    return result


def ask(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


def ask_yes_no(label: str, default: bool = False) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    while True:
        value = input(f"{label}{suffix}: ").strip().casefold()
        if not value:
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False


def interactive_session() -> argparse.Namespace:
    print("What do you want to explore this time?", flush=True)
    print("  1) Five accepted pilot images", flush=True)
    print("  2) Football field", flush=True)
    print("  3) Five pilots + football field", flush=True)
    print("  4) One visible/thermal group", flush=True)
    print("  5) A dataset directory", flush=True)
    print("  6) Several specific visible/thermal groups", flush=True)
    choices = {
        "1": "five-pilots", "2": "soccer", "3": "all", "4": "group", "5": "dataset", "6": "groups"
    }
    selection = ""
    while selection not in choices:
        selection = input("Choose 1-6: ").strip()
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
                "redraw_polygon": ask_yes_no(
                    "Redraw the football-field polygon even if an accepted result already exists?"
                ),
            }
        )
    elif workflow == "group":
        common.update(
            {
                "visible": ask("Visible image path"),
                "thermal": ask("Thermal image path"),
                "tat3_report": ask("TAT3 DOCX report path(s), separated by ; (optional)"),
                "resume_part_c": ask("Saved Part C superpixel_review.json (optional)"),
                "redraw_review": ask_yes_no("Reopen Part C even if this image already has an accepted result?"),
            }
        )
    elif workflow == "dataset":
        common.update(
            {
                "dataset": ask("Dataset directory"),
                "tat3_report": ask("TAT3 DOCX report path(s), separated by ; (optional)"),
                "redraw_review": ask_yes_no("Reopen accepted Part C/Part C* reviews for this dataset?"),
            }
        )
    elif workflow == "groups":
        selected_groups: list[tuple[str, str]] = []
        while True:
            visible = ask("Visible image path (press Enter when finished)")
            if not visible:
                break
            thermal = ask("Matching thermal image path")
            if not thermal:
                print("A thermal image is required for that visible image; the pair was not added.", flush=True)
                continue
            selected_groups.append((visible, thermal))
        if not selected_groups:
            raise ValueError("At least one visible/thermal group is required.")
        polygon_all = ask_yes_no("Do all selected groups require target-polygon extraction (Part C*)?")
        common.update(
            {
                "group": selected_groups,
                "tat3_report": ask("TAT3 DOCX report path(s), separated by ; (optional)"),
                "polygon_all": polygon_all,
                "target_name": ask("Shared target name", "HKUST football field") if polygon_all else "",
                "target_id": ask("Shared stable target ID", "hkust-football-field-natural-turf") if polygon_all else "",
                "surface_cover": ask("Shared surface cover", "grass_low_vegetation") if polygon_all else "",
                "luhk": ask("Shared LUHK category", "GIC / open space") if polygon_all else "",
                "confidence": ask("Reviewer confidence (low/medium/high)", "medium") if polygon_all else "medium",
                "redraw_review": ask_yes_no(
                    "Reopen Part C/Part C* even if these images already have accepted results?"
                ),
            }
        )
    return argparse.Namespace(**common)


def report_values(value: object) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return [
        item.strip()
        for raw in values
        for item in str(raw or "").split(";")
        if item.strip()
    ]


def build_command(args: argparse.Namespace) -> list[str]:
    config = "config/workflow_v0_3.json" if args.production else "config/workflow_v0_3_acceptance.json"
    command = [
        workflow_python(),
        str(PROJECT_ROOT / "scripts" / "run_analysis.py"),
        "--config",
        config,
        "--require-all-success",
        "--interactive",
        "--temporal",
        "ask",
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
        if bool(getattr(args, "redraw_polygon", False)):
            command.extend(["--reprocess-image-id", image_id(thermal)])
        groups.append((visible, thermal))
    if args.workflow == "group":
        visible = resolve(args.visible)
        thermal = resolve(args.thermal)
        for path, label in ((visible, "visible image"), (thermal, "thermal image")):
            if not path.is_file():
                raise FileNotFoundError(f"Group {label} does not exist: {path}")
        for report in report_values(args.tat3_report):
            command.extend(["--tat3-report", str(resolve(report))])
        resume_part_c = str(getattr(args, "resume_part_c", "") or "").strip()
        if resume_part_c:
            review_path = resolve(resume_part_c)
            if not review_path.is_file():
                raise FileNotFoundError(f"Saved Part C review does not exist: {review_path}")
            command.extend(["--part-c-review", f"{image_id(thermal)}={review_path}"])
        command.append("--launch-part-c-gui")
        groups.append((visible, thermal))
        if bool(getattr(args, "redraw_review", False)):
            command.extend(["--reprocess-image-id", image_id(thermal)])
    if args.workflow == "dataset":
        for report in report_values(args.tat3_report):
            command.extend(["--tat3-report", str(resolve(report))])
        dataset_path = resolve(args.dataset)
        if not dataset_path.is_dir():
            raise FileNotFoundError(f"Dataset directory does not exist: {dataset_path}")
        if bool(getattr(args, "redraw_review", False)):
            for selected in discover_dataset_groups(dataset_path):
                command.extend(["--reprocess-image-id", image_id(Path(selected.thermal_path))])
        command.extend(["--launch-part-c-gui", "dataset", "--dataset", str(dataset_path)])
        return command
    if args.workflow == "groups":
        for report in report_values(args.tat3_report):
            command.extend(["--tat3-report", str(resolve(report))])
        command.append("--launch-part-c-gui")
        for visible_value, thermal_value in args.group:
            visible = resolve(visible_value)
            thermal = resolve(thermal_value)
            for path, label in ((visible, "visible image"), (thermal, "thermal image")):
                if not path.is_file():
                    raise FileNotFoundError(f"Group {label} does not exist: {path}")
            groups.append((visible, thermal))
            if bool(getattr(args, "redraw_review", False)):
                command.extend(["--reprocess-image-id", image_id(thermal)])
            if bool(getattr(args, "polygon_all", False)):
                command.extend(["--polygon-image-id", image_id(thermal)])
        if bool(getattr(args, "polygon_all", False)):
            command.extend(
                [
                    "--surface-cover", str(getattr(args, "surface_cover", "grass_low_vegetation")),
                    "--target-name", str(getattr(args, "target_name", "")),
                    "--target-id", str(getattr(args, "target_id", "")),
                    "--luhk", str(getattr(args, "luhk", "GIC / open space")),
                    "--luhk-provenance", "user_supplied_luhk",
                    "--reviewer-confidence", str(getattr(args, "confidence", "medium")),
                ]
            )
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
