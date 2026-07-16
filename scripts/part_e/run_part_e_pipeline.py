#!/usr/bin/env python3
"""Run the formal, resumable Part E sampled-pixel workflow."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from part_e_pixel_common import SAMPLE_FILES, load_config, project_path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STAGE_NAMES = [
    "discover",
    "audit",
    "extract",
    "validate-pixels",
    "sample",
    "analyse",
    "spectrum",
    "supporting-figures",
    "spatial-figures",
    "excel",
    "final-qa",
    "report",
]
SPECTRUM_STEMS = [
    "fig00_pixel_delta_t_spectrum_overall",
    "fig01_pixel_delta_t_spectrum_by_luhk_facets",
    "fig02_pixel_delta_t_spectrum_by_surface_cover_facets",
    "fig03_pixel_delta_t_spectrum_within_gic_by_cover_facets",
    "fig04_pixel_delta_t_spectrum_within_gic_overlay",
    "fig05_pixel_delta_t_spectrum_by_image_facets",
    "fig07_pixel_delta_t_sampling_stability",
    "fig08_pixel_delta_t_surface_cover_bootstrap_ci",
]


@dataclass
class Command:
    argv: list[str]
    optional: bool = False


@dataclass
class Stage:
    name: str
    commands: Callable[[argparse.Namespace], list[Command]]
    outputs: Callable[[argparse.Namespace, dict], list[Path]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/part_e_delta_t_analysis.json")
    parser.add_argument("--from-stage", choices=STAGE_NAMES)
    parser.add_argument("--to-stage", choices=STAGE_NAMES)
    parser.add_argument("--spectrum-only", action="store_true", help="Run only the formal spectrum stage.")
    parser.add_argument("--skip-supporting-figures", action="store_true")
    parser.add_argument("--skip-excel", action="store_true")
    parser.add_argument("--include-excel", action="store_true", help="Explicitly build the optional main Excel workbook.")
    parser.add_argument(
        "--include-per-image-excel",
        action="store_true",
        help="Explicitly build large per-image workbooks; also enables full pixel CSV export.",
    )
    parser.add_argument(
        "--write-full-pixel-csv",
        action="store_true",
        help="Explicitly export large per-image pixel CSV files during extraction.",
    )
    parser.add_argument("--image-id", help="Limit stages that support targeted per-image output.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Skip stages whose required outputs already exist.")
    parser.add_argument(
        "--workers", type=int, default=1,
        help="Reserved worker budget for parallel-safe stages; current formal stages remain deterministic and single-process.",
    )
    return parser.parse_args()


def py(script: str, args: argparse.Namespace, *extra: str) -> Command:
    return Command([sys.executable, str(PROJECT_ROOT / "scripts" / "part_e" / script), "--config", args.config, *extra])


def output(config: dict, key: str, name: str = "") -> Path:
    base = project_path(config["outputs"][key])
    return base / name if name else base


def stage_definitions() -> list[Stage]:
    def discover_commands(args: argparse.Namespace) -> list[Command]:
        return [py("10_validate_part_e_outputs.py", args, "--scope", "inputs")]

    def audit_commands(args: argparse.Namespace) -> list[Command]:
        return [py("00_audit_part_e_inputs.py", args)]

    def extract_commands(args: argparse.Namespace) -> list[Command]:
        extra = ("--write-full-pixel-csv",) if (args.write_full_pixel_csv or args.include_per_image_excel) else ()
        return [py("01_build_pixel_delta_t_dataset.py", args, "--overwrite", *extra)]

    def pixel_validation_commands(args: argparse.Namespace) -> list[Command]:
        return [py("10_validate_part_e_outputs.py", args, "--scope", "pixels")]

    def sample_commands(args: argparse.Namespace) -> list[Command]:
        return [py("02_build_pixel_analysis_samples.py", args)]

    def analysis_commands(args: argparse.Namespace) -> list[Command]:
        return [py("03_run_pixel_statistical_analysis.py", args, "--skip-supporting-figures")]

    def spectrum_commands(args: argparse.Namespace) -> list[Command]:
        return [py("04_generate_pixel_delta_t_spectra.py", args)]

    def supporting_commands(args: argparse.Namespace) -> list[Command]:
        return [py("03_run_pixel_statistical_analysis.py", args, "--supporting-figures-only")]

    def spatial_commands(args: argparse.Namespace) -> list[Command]:
        extra = ("--image-id", args.image_id) if args.image_id else ()
        return [py("05_generate_pixel_spatial_figures.py", args, *extra)]

    def excel_commands(args: argparse.Namespace) -> list[Command]:
        image_extra = ("--image-id", args.image_id) if args.image_id else ()
        commands: list[Command] = []
        if args.include_per_image_excel:
            first = py("06_build_per_image_pixel_workbooks.py", args, *image_extra)
            first.optional = True
            commands.append(first)
        if args.include_excel and not args.image_id:
            main_workbook = py("07_build_main_excel_workbook.py", args)
            main_workbook.optional = True
            export_charts = py("09_export_excel_charts.py", args)
            export_charts.optional = True
            commands.append(main_workbook)
        if commands:
            commands.extend([
                Command([
                    "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(PROJECT_ROOT / "scripts" / "part_e" / "08_finalize_excel_workbooks.ps1"),
                    "-ProjectRoot", str(PROJECT_ROOT), "-ConfigPath", str(project_path(args.config)),
                ], optional=True),
                *([export_charts] if args.include_excel and not args.image_id else []),
            ])
        return commands

    def final_qa_commands(args: argparse.Namespace) -> list[Command]:
        return [py("10_validate_part_e_outputs.py", args, "--scope", "all")]

    def report_commands(args: argparse.Namespace) -> list[Command]:
        return [py("11_generate_part_e_report.py", args)]

    def spatial_outputs(args: argparse.Namespace, config: dict) -> list[Path]:
        ids = [args.image_id] if args.image_id else list(config["pilot_image_ids"])
        stems = [
            "temperature_map", "delta_t_map", "luhk_overlay", "surface_cover_overlay",
            "shadow_overlay", "combined_qa_panel",
        ]
        return [
            output(config, "spatial_maps", f"{image_id}_{stem}.{suffix}")
            for image_id in ids for stem in stems for suffix in ("png", "pdf")
        ]

    def excel_outputs(args: argparse.Namespace, config: dict) -> list[Path]:
        ids = [args.image_id] if args.image_id else list(config["pilot_image_ids"])
        paths = (
            [output(config, "pixel_workbooks", f"{image_id}_pixel_delta_t.xlsx") for image_id in ids]
            if args.include_per_image_excel else []
        )
        if args.include_excel and not args.image_id:
            paths.append(output(config, "excel", "part_e_pixel_statistical_analysis.xlsx"))
        return paths

    return [
        Stage("discover", discover_commands, lambda a, c: [output(c, "qa", "part_e_discovery_validation.md")]),
        Stage("audit", audit_commands, lambda a, c: [output(c, "qa", "part_e_pipeline_audit.md")]),
        Stage("extract", extract_commands, lambda a, c: [output(c, "canonical_parquet"), output(c, "tables", "part_e_full_pixel_summary_by_image.csv")]),
        Stage("validate-pixels", pixel_validation_commands, lambda a, c: [output(c, "qa", "part_e_pixel_artifact_validation.md")]),
        Stage(
            "sample", sample_commands,
            lambda a, c: [
                *[output(c, "sample_directory", f"{base}.parquet") for base in SAMPLE_FILES.values()],
                output(c, "tables", "part_e_pixel_sampling_manifest.csv"),
                output(c, "tables", "part_e_pixel_sample_coverage.csv"),
                output(c, "qa", "part_e_sampling_reproducibility.csv"),
            ],
        ),
        Stage(
            "analyse", analysis_commands,
            lambda a, c: [
                output(c, "tables", "part_e_pixel_statistical_tests.csv"),
                output(c, "tables", "part_e_pixel_effect_sizes.csv"),
                output(c, "tables", "part_e_sampling_stability.csv"),
                output(c, "tables", "part_e_delta_t_by_luhk_pixels.csv"),
                output(c, "tables", "part_e_delta_t_by_surface_cover_pixels.csv"),
            ],
        ),
        Stage(
            "spectrum", spectrum_commands,
            lambda a, c: [
                *[
                    output(c, "spectrum_figures", f"{stem}.{suffix}")
                    for stem in SPECTRUM_STEMS for suffix in ("png", "pdf")
                ],
                output(c, "spectrum_figures", "part_e_spectrum_figure_captions.md"),
                output(c, "tables", "part_e_pixel_delta_t_spectrum_summary.csv"),
            ],
        ),
        Stage(
            "supporting-figures", supporting_commands,
            lambda a, c: [
                output(c, "excel_figures", f"{stem}.{suffix}")
                for stem in [
                    "fig01_delta_t_by_luhk_boxplot", "fig02_delta_t_by_surface_cover_boxplot",
                    "fig03_delta_t_within_gic_by_cover", "fig04_delta_t_by_cover_shadow",
                    "fig05_pixel_sample_coverage", "fig06_delta_t_by_image",
                    "fig07_sampling_stability", "fig08_cover_mean_delta_t_95ci",
                ]
                for suffix in ("png", "pdf")
            ],
        ),
        Stage("spatial-figures", spatial_commands, spatial_outputs),
        Stage("excel", excel_commands, excel_outputs),
        Stage("final-qa", final_qa_commands, lambda a, c: [output(c, "qa", "part_e_final_qa.md")]),
        Stage("report", report_commands, lambda a, c: [output(c, "summaries", "part_e_round1_delta_t_analysis_summary.md")]),
    ]


def selected_stages(args: argparse.Namespace, stages: list[Stage]) -> list[Stage]:
    if args.spectrum_only:
        if args.from_stage or args.to_stage:
            raise ValueError("--spectrum-only cannot be combined with --from-stage or --to-stage")
        selected = [stage for stage in stages if stage.name == "spectrum"]
    else:
        start = STAGE_NAMES.index(args.from_stage) if args.from_stage else 0
        stop = STAGE_NAMES.index(args.to_stage) if args.to_stage else len(STAGE_NAMES) - 1
        if start > stop:
            raise ValueError("--from-stage must not occur after --to-stage")
        selected = stages[start : stop + 1]
    if args.skip_supporting_figures:
        selected = [stage for stage in selected if stage.name != "supporting-figures"]
    if args.skip_excel or not (args.include_excel or args.include_per_image_excel):
        selected = [stage for stage in selected if stage.name != "excel"]
    return selected


def main() -> int:
    args = parse_args()
    if args.workers < 1:
        raise ValueError("--workers must be at least 1")
    config = load_config(args.config)
    if args.image_id and args.image_id not in set(map(str, config["pilot_image_ids"])):
        raise ValueError(f"Unknown selected image ID: {args.image_id}")
    stages = selected_stages(args, stage_definitions())
    print(f"Part E stages: {', '.join(stage.name for stage in stages) or 'none'}")
    print(f"Worker budget: {args.workers}; deterministic single-process execution is used by current stages")
    for stage in stages:
        expected = stage.outputs(args, config)
        complete = bool(expected) and all(path.is_file() for path in expected)
        if args.resume and complete:
            print(f"SKIP {stage.name}: required outputs already exist")
            continue
        commands = stage.commands(args)
        for command in commands:
            print(f"{'DRY-RUN' if args.dry_run else 'RUN'} {stage.name}: {subprocess.list2cmdline(command.argv)}")
            if args.dry_run:
                continue
            completed = subprocess.run(command.argv, cwd=PROJECT_ROOT, check=False)
            if completed.returncode and command.optional:
                print(f"WARNING {stage.name}: optional Excel command returned {completed.returncode}; formal non-Excel stages remain valid")
                continue
            if completed.returncode:
                raise subprocess.CalledProcessError(completed.returncode, command.argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
