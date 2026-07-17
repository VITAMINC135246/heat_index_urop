"""Connect schema-0.2 result sets to the preserved formal Part E stages."""

from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .canonical_result import load_manifest
from .part_e_adapter import (
    aggregate_canonical_results,
    manifest_paths_from_run_summary,
    write_source_dashboard,
)
from .result_index import sha256_file


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_COLUMNS = [
    "measurement_type", "temperature_source", "source_method",
    "surface_cover_provenance", "luhk_provenance", "target_name", "qa_status",
]


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def build_v02_part_e_config(
    *,
    image_ids: Iterable[str],
    canonical_parquet: Path,
    output_root: Path,
    base_config_path: Path | None = None,
) -> Path:
    base = base_config_path or PROJECT_ROOT / "config" / "part_e_delta_t_analysis.json"
    config = deepcopy(json.loads(base.read_text(encoding="utf-8")))
    config["analysis_scope"] = "schema-0.2 canonical result set"
    # Retain the legacy key because the numbered stages use it as the dynamic
    # list of image IDs, not as a five-image whitelist.
    config["pilot_image_ids"] = list(dict.fromkeys(map(str, image_ids)))
    config["canonical_schema_version"] = "0.2.0"
    config["multi_source_policy"] = "source-stratified primary; equal-image dashboard; no default pooling"
    outputs = config["outputs"]
    outputs.update(
        {
            "canonical_parquet": canonical_parquet.resolve().as_posix(),
            "sample_directory": (output_root / "samples").resolve().as_posix(),
            "excel_source_directory": (output_root / "excel_source").resolve().as_posix(),
            "part_e_root": output_root.resolve().as_posix(),
            "tables": (output_root / "tables").resolve().as_posix(),
            "qa": (output_root / "qa").resolve().as_posix(),
            "summaries": (output_root / "summaries").resolve().as_posix(),
            "excel": (output_root / "excel").resolve().as_posix(),
            "pixel_workbooks": (output_root / "excel" / "pixel_workbooks").resolve().as_posix(),
            "excel_figures": (output_root / "figures" / "supporting").resolve().as_posix(),
            "spectrum_figures": (output_root / "figures" / "spectrum").resolve().as_posix(),
            "spatial_maps": (output_root / "figures" / "spatial").resolve().as_posix(),
        }
    )
    config_path = output_root / "part_e_schema_0_2_config.json"
    _atomic_text(config_path, json.dumps(config, indent=2, ensure_ascii=False))
    return config_path


def _summary_from_combined(canonical: Path, summary_path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(canonical)
    required = {"image_id", "temperature_c", "delta_t_c", "analysis_eligible", *SOURCE_COLUMNS}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Schema-0.2 combined Parquet is missing: {missing}")
    rows: list[dict[str, object]] = []
    for keys, group in frame.groupby(["image_id", *SOURCE_COLUMNS], dropna=False, observed=True, sort=True):
        image_id, *source_values = keys
        finite = np.isfinite(pd.to_numeric(group["temperature_c"], errors="coerce").to_numpy(float))
        delta = pd.to_numeric(group["delta_t_c"], errors="coerce").to_numpy(float)
        eligible = group["analysis_eligible"].astype(bool).to_numpy() & finite
        row = dict(zip(SOURCE_COLUMNS, source_values))
        eligible_delta = delta[eligible & np.isfinite(delta)]
        rows.append({
            "image_id": str(image_id), "group_id": str(group.get("group_id", pd.Series([""])).iloc[0]),
            **row, "total_pixel_count": len(group), "finite_pixel_count": int(finite.sum()),
            "label_known_pixel_count": int(group.get("label_known", pd.Series(False, index=group.index)).astype(bool).sum()),
            "analysis_eligible_pixel_count": int(eligible.sum()), "excluded_pixel_count": int((~eligible).sum()),
            "unknown_label_pixel_count": int((~group.get("label_known", pd.Series(False, index=group.index)).astype(bool)).sum()),
            "eligible_temperature_mean_c": float(pd.to_numeric(group.loc[eligible, "temperature_c"], errors="coerce").mean()),
            "eligible_delta_t_mean_c": float(np.mean(eligible_delta)) if eligible_delta.size else np.nan,
            "missing_ambient": bool(not np.isfinite(delta).any()),
        })
    summary = pd.DataFrame(rows)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    return summary


def write_inclusion_exclusion_report(
    *,
    output_root: Path,
    canonical: Path,
    source_summary: pd.DataFrame,
    run_summary_path: Path | None,
) -> tuple[Path, Path]:
    pixels = pd.read_parquet(canonical)
    required = {"image_id", "label_known", "analysis_eligible", *SOURCE_COLUMNS}
    missing = sorted(required.difference(pixels.columns))
    if missing:
        raise ValueError(f"Part E inclusion report is missing canonical fields: {missing}")
    pixels = pixels[["image_id", "label_known", "analysis_eligible", *SOURCE_COLUMNS]].copy()
    pixel_counts = (
        pixels.groupby("image_id", sort=True)
        .agg(
            unknown_label_pixels=("label_known", lambda values: int((~values.astype(bool)).sum())),
            excluded_pixels=("analysis_eligible", lambda values: int((~values.astype(bool)).sum())),
        )
        .reset_index()
    )
    if run_summary_path is not None:
        payload = json.loads(run_summary_path.read_text(encoding="utf-8"))
        rows = pd.DataFrame(payload.get("groups", []))
    else:
        rows = pd.DataFrame({
            "image_id": source_summary["image_id"].astype(str).drop_duplicates(),
            "status": "success", "reason": "included_manifest",
        })
    if rows.empty:
        rows = pd.DataFrame(columns=["image_id", "status", "reason"])
    for column in ("image_id", "status", "reason"):
        if column not in rows:
            rows[column] = ""
    ambient = source_summary.groupby("image_id", sort=True)["missing_ambient"].all().rename("missing_ambient").reset_index()
    report = rows.merge(pixel_counts, on="image_id", how="left").merge(ambient, on="image_id", how="left")
    ambient_missing = report["missing_ambient"].fillna(True).astype(bool)
    report["included_in_formal_part_e"] = report["status"].isin({"success", "cache_hit"}) & ~ambient_missing
    csv_path = output_root / "tables" / "part_e_inclusion_exclusion.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(csv_path, index=False, encoding="utf-8-sig")

    status_counts = report["status"].astype(str).value_counts().to_dict()
    source_counts = pixels.groupby(SOURCE_COLUMNS, dropna=False, observed=True).size().reset_index(name="pixel_count")
    lines = [
        "# Part E schema-0.2 inclusion/exclusion report", "",
        f"- Result groups represented: {len(report)}",
        f"- Included images with finite ambient/delta temperature: {int(report['included_in_formal_part_e'].sum())}",
        f"- Missing-ambient images: {int(report['missing_ambient'].fillna(False).sum())}",
        f"- Unknown-label pixels: {int(report['unknown_label_pixels'].fillna(0).sum())}",
        f"- Excluded pixels: {int(report['excluded_pixels'].fillna(0).sum())}",
        f"- Group states: {json.dumps(status_counts, sort_keys=True)}", "",
        "## Source/provenance strata", "",
    ]
    for row in source_counts.itertuples(index=False):
        label = ", ".join(f"{column}={getattr(row, column)}" for column in SOURCE_COLUMNS)
        lines.append(f"- {label}: {int(row.pixel_count)} pixels")
    markdown_path = output_root / "qa" / "part_e_inclusion_exclusion.md"
    _atomic_text(markdown_path, "\n".join(lines) + "\n")
    return csv_path, markdown_path


def run_formal_part_e(
    manifest_paths: Iterable[Path] | None = None,
    *,
    output_root: Path,
    run_summary_path: Path | None = None,
    combined_parquet: Path | None = None,
    resume: bool = True,
    dry_run: bool = False,
) -> dict[str, str]:
    paths = list(manifest_paths or [])
    if run_summary_path is not None and not paths:
        paths = manifest_paths_from_run_summary(run_summary_path)
    if combined_parquet is not None and paths:
        raise ValueError("Supply manifests/run summary or a combined Parquet, not both.")
    if combined_parquet is None and not paths:
        raise ValueError("Formal Part E requires manifests, a run summary, or a schema-0.2 combined Parquet.")

    output_root.mkdir(parents=True, exist_ok=True)
    summary_path = output_root / "tables" / "part_e_schema_0_2_source_summary.csv"
    if combined_parquet is not None:
        canonical = combined_parquet.resolve()
        source_summary = _summary_from_combined(canonical, summary_path)
        image_ids = source_summary["image_id"].astype(str).unique().tolist()
    else:
        canonical = output_root / "part_e_schema_0_2_pixels.parquet"
        source_summary = aggregate_canonical_results(
            paths,
            output_parquet=canonical,
            summary_csv=summary_path,
            dashboard_directory=output_root / "source_dashboard",
        )
        image_ids = [load_manifest(path).image_id for path in paths]
    write_source_dashboard(source_summary, output_root / "source_dashboard")
    config = build_v02_part_e_config(
        image_ids=image_ids, canonical_parquet=canonical, output_root=output_root,
    )
    canonical_hash = sha256_file(canonical)
    state_path = output_root / "qa" / "part_e_stage_state.json"
    prior_state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    effective_resume = resume and prior_state.get("canonical_sha256") == canonical_hash
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "part_e" / "run_part_e_pipeline.py"),
        "--config", str(config), "--from-stage", "sample", "--to-stage", "spectrum", "--skip-excel",
    ]
    if effective_resume:
        command.append("--resume")
    if dry_run:
        command.append("--dry-run")
    completed = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
    if completed.returncode:
        raise RuntimeError(f"Formal Part E stages failed ({completed.returncode}):\n{completed.stdout}\n{completed.stderr}")

    inclusion_csv, inclusion_md = write_inclusion_exclusion_report(
        output_root=output_root, canonical=canonical, source_summary=source_summary,
        run_summary_path=run_summary_path,
    )
    qa_path = output_root / "qa" / "schema_0_2_part_e_handoff.md"
    formal_state = "planned (dry run)" if dry_run else "completed"
    _atomic_text(qa_path, "\n".join([
        "# Schema 0.2 Part E handoff QA", "",
        f"- Formal stage state: {formal_state}",
        f"- Canonical manifests: {len(paths)}",
        f"- Images: {source_summary['image_id'].nunique()}",
        f"- Source methods: {', '.join(sorted(source_summary['source_method'].astype(str).unique()))}",
        f"- Measurement types: {', '.join(sorted(source_summary['measurement_type'].astype(str).unique()))}",
        f"- Missing ambient strata: {int(source_summary['missing_ambient'].astype(bool).sum())}",
        "- Primary comparisons are source-stratified; no pooled inferential result is generated by default.",
        "- Pixels/points/regions are within-image spatial observations; image/time is the temporal unit.",
    ]) + "\n")
    report_path = output_root / "summaries" / "schema_0_2_part_e_summary.md"
    _atomic_text(
        report_path,
        "# Formal Part E schema-0.2 run\n\n"
        f"Stage state: {formal_state}. The preserved spatial thinning, exploratory statistics, effect sizes, "
        "and KDE stages consume the shared schema-0.2 canonical pixels. Source-stratified dashboards are primary; "
        "unavailable LUHK, shadow, or ambient strata are reported rather than imputed.\n",
    )
    if not dry_run:
        _atomic_text(state_path, json.dumps({"canonical_sha256": canonical_hash, "status": "complete"}, indent=2))
    return {
        "canonical_parquet": canonical.resolve().as_posix(),
        "source_summary": summary_path.resolve().as_posix(),
        "config": config.resolve().as_posix(),
        "qa": qa_path.resolve().as_posix(),
        "inclusion_csv": inclusion_csv.resolve().as_posix(),
        "inclusion_report": inclusion_md.resolve().as_posix(),
        "report": report_path.resolve().as_posix(),
        "stage_stdout": completed.stdout,
    }
