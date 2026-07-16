#!/usr/bin/env python3
"""Validate reusable Part E artifacts without regenerating them."""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from PIL import Image

from part_e_pixel_common import SAMPLE_FILES, load_config, project_path, write_csv, write_markdown


EXPECTED_SHAPE = (512, 640)
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/part_e_delta_t_analysis.json")
    parser.add_argument("--scope", choices=["inputs", "pixels", "all"], default="all")
    return parser.parse_args()


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(
        self, area: str, check: str, passed: bool, detail: str, *, required: bool = True
    ) -> None:
        self.rows.append({
            "area": area,
            "check": check,
            "status": "PASS" if passed else ("FAIL" if required else "WARN"),
            "detail": detail,
        })

    @property
    def passed(self) -> bool:
        return all(row["status"] != "FAIL" for row in self.rows)


def validate_inputs(config: dict[str, Any], checks: Checks) -> None:
    inputs = config["inputs"]
    for name, value in inputs.items():
        if name == "temperature_matrix_format":
            continue
        path = project_path(value)
        checks.add("inputs", name, path.exists(), str(path))
    pilot_ids = list(map(str, config["pilot_image_ids"]))
    checks.add(
        "inputs", "pilot_image_ids", len(pilot_ids) == 5 and len(set(pilot_ids)) == 5,
        f"{len(pilot_ids)} unique pilot IDs",
    )


def validate_canonical(config: dict[str, Any], checks: Checks) -> None:
    path = project_path(config["outputs"]["canonical_parquet"])
    if not path.is_file():
        checks.add("canonical", "file_exists", False, str(path))
        return
    parquet = pq.ParquetFile(path)
    expected_rows = len(config["pilot_image_ids"]) * EXPECTED_SHAPE[0] * EXPECTED_SHAPE[1]
    checks.add(
        "canonical", "row_count", parquet.metadata.num_rows == expected_rows,
        f"{parquet.metadata.num_rows:,} rows; expected {expected_rows:,}",
    )
    required = {
        "pixel_uid", "image_id", "thermal_row", "thermal_col", "temperature_c",
        "ambient_temperature_c", "delta_t_c", "pixel_accepted", "luhk_label_valid",
        "surface_cover_valid", "shadow_flag", "shadow_valid",
    }
    missing = sorted(required.difference(parquet.schema_arrow.names))
    checks.add("canonical", "required_schema", not missing, f"missing={missing}")
    if missing:
        return
    table = pq.read_table(
        path,
        columns=[
            "image_id", "temperature_c", "ambient_temperature_c", "delta_t_c",
            "pixel_accepted", "shadow_flag", "shadow_valid",
        ],
    ).to_pandas()
    accepted = table["pixel_accepted"].astype(bool).to_numpy()
    temperature = table["temperature_c"].to_numpy(float)
    ambient = table["ambient_temperature_c"].to_numpy(float)
    delta = table["delta_t_c"].to_numpy(float)
    finite = np.isfinite(temperature) & np.isfinite(ambient) & np.isfinite(delta)
    checks.add(
        "canonical", "accepted_pixels_finite", bool(finite[accepted].all()),
        f"accepted={int(accepted.sum()):,}; finite accepted={int((finite & accepted).sum()):,}",
    )
    error = np.abs(delta[accepted] - (temperature[accepted] - ambient[accepted]))
    maximum_error = float(error.max()) if error.size else np.inf
    checks.add(
        "canonical", "pixel_delta_t_formula", maximum_error <= 1e-5,
        f"max abs error={maximum_error:.3g} °C",
    )
    counts = table.groupby("image_id", observed=True).size().to_dict()
    expected_per_image = EXPECTED_SHAPE[0] * EXPECTED_SHAPE[1]
    image_ok = set(map(str, counts)) == set(map(str, config["pilot_image_ids"])) and all(
        int(value) == expected_per_image for value in counts.values()
    )
    checks.add("canonical", "complete_image_grids", image_ok, json.dumps({str(k): int(v) for k, v in counts.items()}))
    shadow_present = int(((table["shadow_flag"] == 1) & table["shadow_valid"].astype(bool)).sum())
    checks.add("canonical", "shadow_status", shadow_present == 0, f"valid shadow_flag=1 pixels={shadow_present:,}")


def validate_samples(config: dict[str, Any], checks: Checks) -> None:
    directory = project_path(config["outputs"]["sample_directory"])
    coverage_path = project_path(config["outputs"]["tables"]) / "part_e_pixel_sample_coverage.csv"
    manifest_path = project_path(config["outputs"]["tables"]) / "part_e_pixel_sampling_manifest.csv"
    reproducibility_path = project_path(config["outputs"]["qa"]) / "part_e_sampling_reproducibility.csv"
    if not coverage_path.is_file() or not manifest_path.is_file() or not reproducibility_path.is_file():
        checks.add("samples", "control_tables_exist", False, "coverage, manifest, or reproducibility table missing")
        return
    coverage = pd.read_csv(coverage_path)
    manifest = pd.read_csv(manifest_path)
    reproducibility = pd.read_csv(reproducibility_path)
    checks.add(
        "samples", "reproducibility", bool(reproducibility["status"].eq("PASS").all()),
        reproducibility["status"].value_counts().to_dict().__str__(),
    )
    primary_seed = int(config["sampling"]["primary_seed"])
    for family, base in SAMPLE_FILES.items():
        path = directory / f"{base}.parquet"
        if not path.is_file():
            checks.add("samples", family, False, f"missing {path}")
            continue
        sample = pd.read_parquet(path)
        family_coverage = coverage.loc[coverage["analysis_family"].eq(family)]
        expected_count = int(family_coverage["sampled_pixel_count"].sum())
        valid = (
            len(sample) == expected_count
            and sample["pixel_uid"].nunique() == len(sample)
            and np.isfinite(sample["delta_t_c"].to_numpy(float)).all()
            and set(sample["sampling_seed"].astype(int).unique()) == {primary_seed}
            and set(sample["sampling_method"].astype(str).unique()) == {config["sampling"]["method"]}
        )
        manifest_count = int(manifest.loc[manifest["analysis_family"].eq(family), "sampled_pixel_count"].sum())
        valid = valid and manifest_count == len(sample)
        checks.add(
            "samples", family, bool(valid),
            f"sampled={len(sample):,}; coverage={expected_count:,}; manifest={manifest_count:,}; unique pixels={sample['pixel_uid'].nunique():,}",
        )


def validate_analysis(config: dict[str, Any], checks: Checks) -> None:
    tables = project_path(config["outputs"]["tables"])
    required = [
        "part_e_delta_t_by_luhk_pixels.csv",
        "part_e_delta_t_by_surface_cover_pixels.csv",
        "part_e_delta_t_by_luhk_surface_cover_pixels.csv",
        "part_e_delta_t_by_surface_cover_shadow_pixels.csv",
        "part_e_delta_t_by_image_pixels.csv",
        "part_e_pixel_statistical_tests.csv",
        "part_e_pixel_effect_sizes.csv",
        "part_e_sampling_stability.csv",
    ]
    missing = [name for name in required if not (tables / name).is_file()]
    checks.add("analysis", "required_tables", not missing, f"missing={missing}")
    stability_path = tables / "part_e_sampling_stability.csv"
    if stability_path.is_file():
        stability = pd.read_csv(stability_path)
        expected = 1 + len(config["sampling"]["secondary_seeds"])
        checks.add(
            "analysis", "sampling_stability_seeds",
            stability["sampling_seed"].nunique() == expected,
            f"{stability['sampling_seed'].nunique()} seeds; expected {expected}",
        )


def validate_png(path: Path) -> tuple[bool, str]:
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
            corner = np.asarray(image.convert("RGB"))[0, 0].mean()
        ok = width >= 1000 and height >= 550 and corner >= 180
        return ok, f"{width}×{height}; top-left luminance={corner:.0f}"
    except Exception as exc:  # pragma: no cover - diagnostic path
        return False, str(exc)


def validate_spectra(config: dict[str, Any], checks: Checks) -> None:
    directory = project_path(config["outputs"]["spectrum_figures"])
    for stem in SPECTRUM_STEMS:
        png = directory / f"{stem}.png"
        pdf = directory / f"{stem}.pdf"
        png_ok, detail = validate_png(png) if png.is_file() else (False, "missing PNG")
        pdf_ok = pdf.is_file() and pdf.read_bytes()[:4] == b"%PDF"
        checks.add("spectrum", stem, png_ok and pdf_ok, f"PNG {detail}; PDF={'valid' if pdf_ok else 'missing/invalid'}")
    shadow_files = list(directory.glob("fig06*"))
    checks.add(
        "spectrum", "shadow_not_estimable", not shadow_files,
        "no fig06 files, as required" if not shadow_files else f"unexpected files={shadow_files}",
    )
    caption = directory / "part_e_spectrum_figure_captions.md"
    summary_path = project_path(config["outputs"]["tables"]) / "part_e_pixel_delta_t_spectrum_summary.csv"
    required_columns = {
        "analysis_family", "group_name", "n_pixels_full", "n_pixels_sampled", "n_images",
        "mean_sampled", "median_sampled", "std_sampled", "min_sampled", "q05_sampled",
        "q25_sampled", "q75_sampled", "q95_sampled", "max_sampled", "sampling_seed",
        "sampling_method", "kde_status", "kde_bandwidth_method", "eligibility_or_skipped_reason",
    }
    if summary_path.is_file():
        summary = pd.read_csv(summary_path)
        missing = sorted(required_columns.difference(summary.columns))
        shadow = summary.loc[summary["analysis_family"].eq("surface_cover_shadow")]
        summary_ok = not missing and not shadow.empty and shadow["kde_status"].eq("not_estimable_as_contrast").all()
        checks.add("spectrum", "source_summary", summary_ok, f"rows={len(summary)}; missing columns={missing}")
    else:
        checks.add("spectrum", "source_summary", False, f"missing {summary_path}")
    caption_text = caption.read_text(encoding="utf-8") if caption.is_file() else ""
    caption_terms = ["one accepted finite thermal pixel", "Density is normalized", "spatial autocorrelation", "not estimable"]
    checks.add(
        "spectrum", "captions", caption.is_file() and all(term in caption_text for term in caption_terms),
        f"caption file={caption}; required statements present={all(term in caption_text for term in caption_terms)}",
    )


def validate_supporting_outputs(config: dict[str, Any], checks: Checks) -> None:
    root = project_path(config["outputs"]["part_e_root"])
    supporting = project_path(config["outputs"]["excel_figures"])
    supporting_stems = [
        "fig01_delta_t_by_luhk_boxplot", "fig02_delta_t_by_surface_cover_boxplot",
        "fig03_delta_t_within_gic_by_cover", "fig04_delta_t_by_cover_shadow",
        "fig05_pixel_sample_coverage", "fig06_delta_t_by_image",
        "fig07_sampling_stability", "fig08_cover_mean_delta_t_95ci",
    ]
    missing_supporting = [
        f"{stem}.{suffix}" for stem in supporting_stems for suffix in ("png", "pdf")
        if not (supporting / f"{stem}.{suffix}").is_file()
    ]
    checks.add(
        "supporting", "supporting_figures", not missing_supporting,
        f"missing={missing_supporting}", required=False,
    )
    spatial = project_path(config["outputs"]["spatial_maps"])
    spatial_stems = [
        "temperature_map", "delta_t_map", "luhk_overlay", "surface_cover_overlay",
        "shadow_overlay", "combined_qa_panel",
    ]
    missing_spatial = [
        f"{image_id}_{stem}.{suffix}"
        for image_id in config["pilot_image_ids"] for stem in spatial_stems for suffix in ("png", "pdf")
        if not (spatial / f"{image_id}_{stem}.{suffix}").is_file()
    ]
    checks.add(
        "supporting", "spatial_figures", not missing_spatial,
        f"missing count={len(missing_spatial)}", required=False,
    )
    workbooks = [
        project_path(config["outputs"]["excel"]) / "part_e_pixel_statistical_analysis.xlsx",
        *[
            project_path(config["outputs"]["pixel_workbooks"]) / f"{image_id}_pixel_delta_t.xlsx"
            for image_id in config["pilot_image_ids"]
        ],
    ]
    workbook_details: list[str] = []
    valid = True
    for path in workbooks:
        ok = path.is_file() and zipfile.is_zipfile(path)
        if ok:
            with zipfile.ZipFile(path) as archive:
                ok = "[Content_Types].xml" in archive.namelist() and "xl/workbook.xml" in archive.namelist()
        valid = valid and ok
        workbook_details.append(f"{path.name}={'valid' if ok else 'invalid/missing'}")
    checks.add(
        "supporting", "excel_workbooks", valid, "; ".join(workbook_details), required=False,
    )
    script_dir = project_path("scripts/part_e")
    legacy_names = {
        "00_create_ambient_temperature_manifest_template.py",
        "01_build_cell_delta_t_dataset.py",
        "02_build_surface_cover_delta_t_dataset.py",
        "03_generate_summary_tables.py",
        "04_run_exploratory_statistics.py",
        "05_create_figures.py",
        "06_create_clear_spectrum_figures.py",
        "part_e_common.py",
    }
    legacy_present = sorted(path.name for path in script_dir.iterdir() if path.name in legacy_names)
    numbered_scripts = sorted(
        path.name
        for path in script_dir.iterdir()
        if path.is_file() and len(path.name) > 3 and path.name[:2].isdigit() and path.name[2] == "_"
    )
    prefix_counts: dict[str, int] = {}
    for name in numbered_scripts:
        prefix_counts[name[:2]] = prefix_counts.get(name[:2], 0) + 1
    duplicate_prefixes = sorted(prefix for prefix, count in prefix_counts.items() if count > 1)
    pipeline = project_path("scripts/part_e/run_part_e_pipeline.py")
    pipeline_text = pipeline.read_text(encoding="utf-8") if pipeline.is_file() else ""
    checks.add(
        "methodology", "formal_script_namespace_clean",
        not legacy_present and not duplicate_prefixes and not any(name in pipeline_text for name in legacy_names),
        f"active numbered scripts={numbered_scripts}; legacy present={legacy_present}; duplicate prefixes={duplicate_prefixes}",
    )
    checks.add("supporting", "part_e_root", root.is_dir(), str(root))


def validate_documentation(config: dict[str, Any], checks: Checks) -> None:
    documents = {
        "README": (
            project_path("README.md"),
            ["Part E formal pixel-spectrum workflow", "statistical distribution", "spatial autocorrelation"],
        ),
        "methodology": (
            project_path("docs/part_e_delta_t_statistical_analysis.md"),
            ["formal observation is one original thermal pixel", "Scott's bandwidth rule", "not estimable"],
        ),
        "overview": (
            project_path("docs/revised_project_overview.md"),
            ["primary scientific", "visual result", "canonical 1,638,400-row pixel dataset", "does not generalize"],
        ),
        "change_log": (
            project_path("docs/method_change_log.md"),
            ["Part E pixel-level spectrum priority", "earlier cell-level spectrum workflow", "P-values remain exploratory"],
        ),
        "formal_report": (
            project_path(config["outputs"]["summaries"]) / "part_e_round1_delta_t_analysis_summary.md",
            ["Overall pixel ΔT spectrum", "sampling stability", "do not generalize"],
        ),
    }
    for name, (path, terms) in documents.items():
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        missing = [term for term in terms if term.casefold() not in text.casefold()]
        checks.add("documentation", name, path.is_file() and not missing, f"missing statements={missing}")


def write_report(config: dict[str, Any], checks: Checks, scope: str) -> Path:
    qa = project_path(config["outputs"]["qa"])
    qa.mkdir(parents=True, exist_ok=True)
    stem = {
        "inputs": "part_e_discovery_validation",
        "pixels": "part_e_pixel_artifact_validation",
        "all": "part_e_final_qa",
    }[scope]
    frame = pd.DataFrame(checks.rows)
    write_csv(qa / f"{stem}.csv", frame)
    lines = [
        f"# Part E {scope} validation",
        "",
        f"Overall status: **{'PASS' if checks.passed else 'FAIL'}**.",
        "",
        "Validation reads existing artifacts and does not regenerate extraction, sampling, statistics, workbooks, or maps.",
        "",
        "| Area | Check | Status | Detail |",
        "|---|---|---:|---|",
    ]
    for row in checks.rows:
        detail = str(row["detail"]).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {row['area']} | {row['check']} | {row['status']} | {detail} |")
    path = qa / f"{stem}.md"
    write_markdown(path, lines)
    return path


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    checks = Checks()
    validate_inputs(config, checks)
    if args.scope in {"pixels", "all"}:
        validate_canonical(config, checks)
    if args.scope == "all":
        validate_samples(config, checks)
        validate_analysis(config, checks)
        validate_spectra(config, checks)
        validate_supporting_outputs(config, checks)
        validate_documentation(config, checks)
    report = write_report(config, checks, args.scope)
    print(f"Part E {args.scope} validation: {'PASS' if checks.passed else 'FAIL'} ({report})")
    return 0 if checks.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
