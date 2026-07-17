"""Capture-level temporal analysis for canonical and compatible measurements.

Pixels, polygon pixels, TAT3 points, and TAT3 regions are within-image spatial
observations.  This module first reduces them to one descriptive row per
capture/source/target stratum; it never treats them as temporal replicates.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import matplotlib
import numpy as np
import pandas as pd

from .result_index import sha256_file


PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".matplotlib-cache"))
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


SOURCE_COLUMNS = [
    "measurement_type",
    "temperature_source",
    "temperature_definition",
    "source_method",
    "surface_cover_provenance",
    "luhk_provenance",
    "target_id",
    "target_name",
    "qa_status",
]
TEMPERATURE_STRATUM_COLUMNS = [
    "measurement_type",
    "temperature_source",
    "temperature_definition",
    "source_method",
    "surface_cover_provenance",
    "luhk_provenance",
    "target_linkage_key",
    "qa_status",
]
DELTA_STRATUM_COLUMNS = [*TEMPERATURE_STRATUM_COLUMNS, "ambient_source", "ambient_definition"]
STAT_NAMES = ("min", "max", "mean", "median", "q01", "q95", "q99")


@dataclass(slots=True)
class TemporalRunResult:
    status: str
    output_root: Path
    capture_summary: Path
    stratum_summary: Path
    inclusion_exclusion: Path
    diagnostics: Path
    qa_report: Path
    report: Path
    validation: Path

    def to_dict(self) -> dict[str, str]:
        return {
            "status": self.status,
            "output_root": self.output_root.resolve().as_posix(),
            "capture_summary": self.capture_summary.resolve().as_posix(),
            "stratum_summary": self.stratum_summary.resolve().as_posix(),
            "inclusion_exclusion": self.inclusion_exclusion.resolve().as_posix(),
            "diagnostics": self.diagnostics.resolve().as_posix(),
            "qa_report": self.qa_report.resolve().as_posix(),
            "report": self.report.resolve().as_posix(),
            "validation": self.validation.resolve().as_posix(),
        }


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _config_hash(default_timezone: str) -> str:
    payload = {
        "processing_version": "heat-index-urop-0.3",
        "default_timezone": default_timezone,
        "interpolation": "disabled",
        "temporal_unit": "one image/capture time",
        "aggregation": "equal-image",
        "statistics": list(STAT_NAMES),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _ensure_columns(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    aliases = {
        "capture_datetime": ("capture_datetime", "capture_time"),
        "thermal_row": ("thermal_row", "pixel_y"),
        "thermal_col": ("thermal_col", "pixel_x"),
    }
    for target, candidates in aliases.items():
        if target in work:
            continue
        for candidate in candidates:
            if candidate in work:
                work[target] = work[candidate]
                break
    required = {"image_id", "temperature_c", "measurement_type"}
    missing = sorted(required.difference(work.columns))
    if missing:
        raise ValueError(f"Temporal input is missing required fields: {missing}")
    defaults: dict[str, Any] = {
        "capture_datetime": "",
        "capture_timezone": "",
        "temperature_source": "",
        "temperature_definition": "",
        "source_method": "unknown",
        "surface_cover_provenance": "unknown",
        "luhk_provenance": "unknown",
        "target_id": "",
        "target_name": "",
        "qa_status": "unknown",
        "ambient_source": "",
        "ambient_definition": "",
        "ambient_temperature_c": np.nan,
        "delta_t_c": np.nan,
        "analysis_eligible": True,
        "temperature_is_finite": True,
        "label_known": True,
        "target_mask": True,
        "exclusion_reason": "",
        "dataset_id": "",
        "group_id": "",
    }
    for column, value in defaults.items():
        if column not in work:
            work[column] = value
    for column in (
        "image_id", "capture_datetime", "capture_timezone", "measurement_type", "temperature_source", "temperature_definition",
        "source_method", "surface_cover_provenance", "luhk_provenance", "target_id", "target_name",
        "qa_status", "ambient_source", "ambient_definition", "dataset_id", "group_id",
    ):
        work[column] = work[column].fillna("").astype(str)
    work["temperature_c"] = pd.to_numeric(work["temperature_c"], errors="coerce")
    work["delta_t_c"] = pd.to_numeric(work["delta_t_c"], errors="coerce")
    work["ambient_temperature_c"] = pd.to_numeric(work["ambient_temperature_c"], errors="coerce")
    for column in ("analysis_eligible", "temperature_is_finite", "label_known", "target_mask"):
        work[column] = work[column].fillna(False).astype(bool)
    work["temperature_is_finite"] &= np.isfinite(work["temperature_c"])
    return work


def _parse_capture_time(
    raw_values: pd.Series,
    timezone_values: pd.Series,
    default_timezone: str,
) -> tuple[pd.Timestamp | pd.NaT, pd.Timestamp | pd.NaT, str, str]:
    raw = sorted({value.strip() for value in raw_values.astype(str) if value.strip()})
    zones = sorted({value.strip() for value in timezone_values.astype(str) if value.strip()})
    if len(raw) != 1:
        reason = "capture_timestamp_missing" if not raw else "ambiguous_capture_timestamps"
        return pd.NaT, pd.NaT, reason, reason
    if len(zones) > 1:
        return pd.NaT, pd.NaT, "ambiguous_capture_timezones", "ambiguous_capture_timezones"
    try:
        stamp = pd.Timestamp(raw[0])
    except (TypeError, ValueError):
        return pd.NaT, pd.NaT, "invalid_capture_timestamp", "invalid_capture_timestamp"
    try:
        if stamp.tzinfo is None:
            zone_name = zones[0] if zones else default_timezone
            ZoneInfo(zone_name)
            stamp = stamp.tz_localize(zone_name, ambiguous="raise", nonexistent="raise")
            assumption = "capture_timezone_metadata" if zones else "default_timezone_assumed"
        else:
            assumption = "embedded_offset_or_timezone"
        local = stamp.tz_convert(default_timezone)
        utc = stamp.tz_convert("UTC")
    except (TypeError, ValueError, KeyError):
        return pd.NaT, pd.NaT, "invalid_or_ambiguous_timezone", "invalid_or_ambiguous_timezone"
    return local, utc, assumption, ""


def _stats(values: pd.Series, prefix: str) -> dict[str, float]:
    array = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    array = array[np.isfinite(array)]
    if not array.size:
        return {f"{prefix}_{name}_c": np.nan for name in STAT_NAMES}
    return {
        f"{prefix}_min_c": float(np.min(array)),
        f"{prefix}_max_c": float(np.max(array)),
        f"{prefix}_mean_c": float(np.mean(array)),
        f"{prefix}_median_c": float(np.median(array)),
        f"{prefix}_q01_c": float(np.quantile(array, 0.01)),
        f"{prefix}_q95_c": float(np.quantile(array, 0.95)),
        f"{prefix}_q99_c": float(np.quantile(array, 0.99)),
    }


def _stratum_id(row: pd.Series | dict[str, Any], columns: list[str]) -> str:
    return "|".join(f"{column}={str(row[column])}" for column in columns)


def _duplicate_image_ids(frame: pd.DataFrame) -> set[str]:
    if "pixel_uid" not in frame:
        return set()
    identifiers = frame["pixel_uid"].fillna("").astype(str)
    usable = identifiers.ne("")
    duplicated = frame.loc[usable].assign(_pixel_uid=identifiers[usable]).duplicated(
        subset=["image_id", "_pixel_uid"], keep=False
    )
    return set(frame.loc[usable].loc[duplicated, "image_id"].astype(str))


def build_capture_summary(
    frame: pd.DataFrame,
    *,
    default_timezone: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    work = _ensure_columns(frame)
    duplicate_ids = _duplicate_image_ids(work)
    diagnostics: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    group_columns = ["image_id", *SOURCE_COLUMNS]
    for keys, group in work.groupby(group_columns, sort=True, dropna=False, observed=True):
        values = dict(zip(group_columns, keys))
        image_id = str(values["image_id"])
        local, utc, timezone_assumption, time_error = _parse_capture_time(
            group["capture_datetime"], group["capture_timezone"], default_timezone
        )
        target_id = str(values["target_id"]).strip()
        target_name = str(values["target_name"]).strip()
        target_linkage_key = target_id if target_id else f"unlinked:{image_id}"
        if not target_id:
            diagnostics.append(
                {
                    "image_id": image_id,
                    "diagnostic": "missing_target_id_for_cross_capture_linkage",
                    "severity": "warning",
                    "detail": "Single-capture description is allowed; target-specific temporal pooling is disabled.",
                }
            )
        if time_error:
            diagnostics.append(
                {"image_id": image_id, "diagnostic": time_error, "severity": "error", "detail": "Capture excluded from chronological series."}
            )
        duplicate_image = image_id in duplicate_ids
        if duplicate_image:
            diagnostics.append(
                {
                    "image_id": image_id,
                    "diagnostic": "duplicate_image_id_or_measurement_grid",
                    "severity": "error",
                    "detail": "Repeated pixel/measurement identifiers would otherwise double-weight the capture.",
                }
            )
        ambient_values = pd.to_numeric(group["ambient_temperature_c"], errors="coerce")
        ambient_unique = np.unique(np.round(ambient_values[np.isfinite(ambient_values)], 7))
        ambiguous_ambient = len(ambient_unique) > 1
        ambient_sources = sorted({value.strip() for value in group["ambient_source"].astype(str) if value.strip()})
        ambient_definitions = sorted({value.strip() for value in group["ambient_definition"].astype(str) if value.strip()})
        ambiguous_ambient_metadata = len(ambient_sources) > 1 or len(ambient_definitions) > 1
        if ambiguous_ambient:
            diagnostics.append(
                {
                    "image_id": image_id,
                    "diagnostic": "ambiguous_ambient_values_within_capture",
                    "severity": "error",
                    "detail": json.dumps(ambient_unique.tolist()),
                }
            )
        if ambiguous_ambient_metadata:
            diagnostics.append(
                {
                    "image_id": image_id,
                    "diagnostic": "ambiguous_ambient_definition_within_capture",
                    "severity": "error",
                    "detail": json.dumps({"sources": ambient_sources, "definitions": ambient_definitions}, sort_keys=True),
                }
            )
        finite = group["temperature_is_finite"].astype(bool) & np.isfinite(group["temperature_c"])
        eligible = group["analysis_eligible"].astype(bool) & finite
        delta_finite = eligible & np.isfinite(group["delta_t_c"])
        known = group["label_known"].astype(bool)
        target = group["target_mask"].astype(bool)
        row: dict[str, Any] = {
            **values,
            "target_linkage_key": target_linkage_key,
            "capture_time_local": local.isoformat() if pd.notna(local) else "",
            "capture_time_utc": utc.isoformat() if pd.notna(utc) else "",
            "capture_timezone_output": default_timezone,
            "timezone_assumption": timezone_assumption,
            "capture_time_valid": bool(pd.notna(utc)),
            "duplicate_image_id": duplicate_image,
            "ambient_temperature_c": float(ambient_unique[0]) if len(ambient_unique) == 1 else np.nan,
            "ambient_source": ambient_sources[0] if len(ambient_sources) == 1 else "",
            "ambient_definition": ambient_definitions[0] if len(ambient_definitions) == 1 else "",
            "ambient_available": bool(delta_finite.any()),
            "ambient_ambiguous": ambiguous_ambient or ambiguous_ambient_metadata,
            "total_measurement_count": int(len(group)),
            "finite_temperature_count": int(finite.sum()),
            "analysis_eligible_count": int(eligible.sum()),
            "finite_delta_t_count": int(delta_finite.sum()),
            "target_measurement_count": int(target.sum()),
            "target_coverage_fraction": float(target.mean()) if len(target) else np.nan,
            "known_label_count": int(known.sum()),
            "unknown_label_count": int((~known).sum()),
            "temperature_trend_eligible": bool(
                pd.notna(utc)
                and not duplicate_image
                and str(values["temperature_source"]).strip()
                and str(values["temperature_definition"]).strip()
            ),
            "delta_t_trend_eligible": bool(
                pd.notna(utc)
                and not duplicate_image
                and not ambiguous_ambient
                and not ambiguous_ambient_metadata
                and delta_finite.any()
                and str(values["temperature_source"]).strip()
                and str(values["temperature_definition"]).strip()
                and len(ambient_sources) == 1
                and len(ambient_definitions) == 1
            ),
            "temporal_unit": "one image/capture time",
            "spatial_observation_policy": "within-image measurements summarized before cross-time analysis",
        }
        row.update(_stats(group.loc[eligible, "temperature_c"], "temperature"))
        row.update(_stats(group.loc[delta_finite, "delta_t_c"], "delta_t"))
        row["temperature_stratum_id"] = _stratum_id(row, TEMPERATURE_STRATUM_COLUMNS)
        row["delta_t_stratum_id"] = _stratum_id(row, DELTA_STRATUM_COLUMNS)
        rows.append(row)
    summary = pd.DataFrame(rows)
    if summary.empty:
        summary = pd.DataFrame(
            columns=[
                *group_columns, "target_linkage_key", "capture_time_local", "capture_time_utc",
                "capture_time_valid", "temperature_stratum_id", "delta_t_stratum_id",
            ]
        )
    else:
        summary = summary.sort_values(
            ["capture_time_utc", "image_id", "source_method", "measurement_type", "target_linkage_key"],
            kind="mergesort",
        ).reset_index(drop=True)

        explicit = summary.loc[summary["target_id"].astype(str).str.strip().ne("")]
        inconsistent_targets = {
            target_id
            for target_id, group in explicit.groupby("target_id", sort=True)
            if group["target_name"].astype(str).nunique(dropna=False) > 1
        }
        if inconsistent_targets:
            mask = summary["target_id"].isin(inconsistent_targets)
            summary.loc[mask, ["temperature_trend_eligible", "delta_t_trend_eligible"]] = False
            for target_id in sorted(inconsistent_targets):
                diagnostics.append(
                    {
                        "image_id": "",
                        "diagnostic": "inconsistent_target_names_for_target_id",
                        "severity": "error",
                        "detail": target_id,
                    }
                )

        for stratum_column, eligible_column in (
            ("temperature_stratum_id", "temperature_trend_eligible"),
            ("delta_t_stratum_id", "delta_t_trend_eligible"),
        ):
            candidates = summary.loc[summary[eligible_column].astype(bool)].copy()
            duplicates = candidates.duplicated(subset=[stratum_column, "capture_time_utc"], keep=False)
            duplicate_rows = candidates.loc[duplicates]
            if not duplicate_rows.empty:
                affected = duplicate_rows.index
                summary.loc[affected, eligible_column] = False
                for row in duplicate_rows.itertuples(index=False):
                    diagnostics.append(
                        {
                            "image_id": row.image_id,
                            "diagnostic": "duplicate_timestamp_within_compatible_stratum",
                            "severity": "error",
                            "detail": f"{getattr(row, stratum_column)} @ {row.capture_time_utc}",
                        }
                    )

    inclusion_rows: list[dict[str, Any]] = []
    for row in summary.itertuples(index=False):
        reasons: list[str] = []
        if not row.capture_time_valid:
            reasons.append("invalid_or_missing_capture_time")
        if row.duplicate_image_id:
            reasons.append("duplicate_image_id")
        if not str(row.target_id).strip():
            reasons.append("missing_target_id_cross_capture_linkage_disabled")
        if not str(row.temperature_source).strip():
            reasons.append("temperature_source_definition_missing")
        elif not str(row.temperature_definition).strip():
            reasons.append("temperature_measurement_definition_missing")
        if not row.ambient_available:
            reasons.append("ambient_missing_delta_t_unavailable")
        if row.ambient_available and (not str(row.ambient_source).strip() or not str(row.ambient_definition).strip()):
            reasons.append("ambient_source_or_definition_missing")
        inclusion_rows.append(
            {
                "image_id": row.image_id,
                "measurement_type": row.measurement_type,
                "source_method": row.source_method,
                "target_id": row.target_id,
                "capture_time_utc": row.capture_time_utc,
                "temperature_descriptive_included": row.analysis_eligible_count > 0,
                "temperature_trend_eligible": row.temperature_trend_eligible,
                "delta_t_descriptive_included": row.finite_delta_t_count > 0,
                "delta_t_trend_eligible": row.delta_t_trend_eligible,
                "reasons": ";".join(reasons),
            }
        )
    inclusion = pd.DataFrame(inclusion_rows).reindex(
        columns=[
            "image_id", "measurement_type", "source_method", "target_id", "capture_time_utc",
            "temperature_descriptive_included", "temperature_trend_eligible",
            "delta_t_descriptive_included", "delta_t_trend_eligible", "reasons",
        ]
    )
    diagnostics_frame = pd.DataFrame(diagnostics, columns=["image_id", "diagnostic", "severity", "detail"])
    diagnostics_frame = diagnostics_frame.sort_values(["severity", "diagnostic", "image_id"], kind="mergesort").reset_index(drop=True)
    return summary, inclusion, diagnostics_frame


def build_stratum_summary(captures: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for kind, stratum_column, eligible_column, metric in (
        ("temperature", "temperature_stratum_id", "temperature_trend_eligible", "temperature_mean_c"),
        ("delta_t", "delta_t_stratum_id", "delta_t_trend_eligible", "delta_t_mean_c"),
    ):
        if captures.empty:
            continue
        for stratum_id, group in captures.groupby(stratum_column, sort=True, dropna=False, observed=True):
            valid = group.loc[group[eligible_column].astype(bool)].copy()
            valid["_time"] = pd.to_datetime(valid["capture_time_utc"], utc=True, errors="coerce")
            valid = valid.loc[valid["_time"].notna()].sort_values(["_time", "image_id"], kind="mergesort")
            intervals = valid["_time"].diff().dt.total_seconds().dropna().to_numpy(float)
            irregular = bool(len(intervals) > 1 and not np.allclose(intervals, intervals[0], rtol=0, atol=1.0))
            capture_count = len(valid)
            if capture_count == 0:
                trend_status = "no_compatible_capture"
            elif capture_count == 1:
                trend_status = "single_capture_descriptive_no_trend"
            else:
                trend_status = "multi_capture_descriptive_exploratory"
            values = pd.to_numeric(valid[metric], errors="coerce") if metric in valid else pd.Series(dtype=float)
            rows.append(
                {
                    "metric_family": kind,
                    "stratum_id": str(stratum_id),
                    "compatible_capture_count": capture_count,
                    "trend_status": trend_status,
                    "irregular_intervals": irregular,
                    "interval_seconds_json": json.dumps(intervals.tolist()),
                    "first_capture_utc": valid["capture_time_utc"].iloc[0] if capture_count else "",
                    "last_capture_utc": valid["capture_time_utc"].iloc[-1] if capture_count else "",
                    "equal_image_mean_of_capture_means_c": float(values.mean()) if values.notna().any() else np.nan,
                    "aggregation_policy": "equal image/capture weighting",
                    "interpolation": "disabled",
                    "inference": "exploratory; descriptive within-image quantiles are not confidence intervals",
                }
            )
    return pd.DataFrame(rows).sort_values(["metric_family", "stratum_id"], kind="mergesort").reset_index(drop=True) if rows else pd.DataFrame(
        columns=[
            "metric_family", "stratum_id", "compatible_capture_count", "trend_status",
            "irregular_intervals", "interval_seconds_json", "first_capture_utc", "last_capture_utc",
            "equal_image_mean_of_capture_means_c", "aggregation_policy", "interpolation", "inference",
        ]
    )


def _save_figure(fig: plt.Figure, directory: Path, stem: str) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = [directory / f"{stem}.png", directory / f"{stem}.pdf"]
    fig.savefig(paths[0], dpi=180, bbox_inches="tight", facecolor="white")
    fig.savefig(paths[1], bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return paths


def _plot_time_series(captures: pd.DataFrame, *, family: str, directory: Path) -> list[Path]:
    if family == "temperature":
        stratum_column = "temperature_stratum_id"
        eligible_column = "temperature_trend_eligible"
        columns = ("temperature_mean_c", "temperature_median_c", "temperature_q01_c", "temperature_q99_c")
        ylabel = "Temperature (°C)"
        stem = "temporal_temperature_series"
    else:
        stratum_column = "delta_t_stratum_id"
        eligible_column = "delta_t_trend_eligible"
        columns = ("delta_t_mean_c", "delta_t_median_c", "delta_t_q01_c", "delta_t_q99_c")
        ylabel = "ΔT (°C)"
        stem = "temporal_delta_t_series"
    fig, axis = plt.subplots(figsize=(12, 6), facecolor="white")
    plotted = 0
    for index, (stratum, group) in enumerate(captures.groupby(stratum_column, sort=True, dropna=False, observed=True)):
        valid = group.loc[group[eligible_column].astype(bool)].copy()
        valid["_time"] = pd.to_datetime(valid["capture_time_utc"], utc=True, errors="coerce")
        valid = valid.loc[valid["_time"].notna()].sort_values(["_time", "image_id"], kind="mergesort")
        if valid.empty:
            continue
        color = plt.get_cmap("tab10")(index % 10)
        first = valid.iloc[0]
        label = (
            f"{first['source_method']} / {first['measurement_type']} / "
            f"{first['target_id'] or 'target-id unavailable'} / {first['temperature_source'] or 'temperature-source unavailable'}"
        )
        axis.plot(valid["_time"], valid[columns[0]], marker="o", color=color, label=f"mean — {label}")
        axis.plot(valid["_time"], valid[columns[1]], marker=".", linestyle="--", color=color, alpha=0.75, label=f"median — {label}")
        if len(valid) >= 2:
            axis.fill_between(
                valid["_time"],
                pd.to_numeric(valid[columns[2]], errors="coerce"),
                pd.to_numeric(valid[columns[3]], errors="coerce"),
                color=color,
                alpha=0.12,
            )
        plotted += 1
    if not plotted:
        axis.axis("off")
        axis.text(0.5, 0.55, "NO COMPATIBLE TEMPORAL SERIES", ha="center", va="center", fontsize=18, weight="bold")
        axis.text(0.5, 0.42, "See temporal inclusion/exclusion and diagnostics tables.", ha="center", va="center")
    else:
        axis.set_xlabel("Capture time (UTC; chronological; no interpolation)")
        axis.set_ylabel(ylabel)
        axis.grid(alpha=0.2)
        axis.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), fontsize=7, frameon=False, ncol=1)
    axis.set_title(f"Capture-level {family} series — mean/median with descriptive q01–q99 bands")
    fig.text(0.01, 0.01, "Bands describe within-image variation; they are not confidence intervals. Images/captures are weighted equally.", fontsize=9)
    fig.subplots_adjust(bottom=0.32, left=0.09, right=0.98, top=0.90)
    return _save_figure(fig, directory, stem)


def _plot_source_panel(captures: pd.DataFrame, directory: Path) -> list[Path]:
    figure, axes = plt.subplots(1, 2, figsize=(16, 6), facecolor="white")
    for axis, metric, title in (
        (axes[0], "temperature_mean_c", "Equal-capture mean temperature"),
        (axes[1], "delta_t_mean_c", "Equal-capture mean ΔT"),
    ):
        available = captures.loc[pd.to_numeric(captures.get(metric), errors="coerce").notna()].copy() if not captures.empty else pd.DataFrame()
        if available.empty:
            axis.axis("off")
            axis.text(0.5, 0.5, f"{title}\nUNAVAILABLE", ha="center", va="center")
            continue
        available["source_label"] = (
            available["source_method"].astype(str)
            + "\n"
            + available["measurement_type"].astype(str)
            + "\n"
            + available["target_id"].replace("", "target-id unavailable").astype(str)
        )
        grouped = available.groupby("source_label", sort=True, observed=True)[metric].mean()
        axis.bar(np.arange(len(grouped)), grouped.to_numpy(float), color="#0072B2")
        axis.set_xticks(np.arange(len(grouped)), grouped.index, rotation=25, ha="right", fontsize=8)
        axis.set_ylabel("°C")
        axis.set_title(title)
    figure.suptitle("Source-stratified capture-level comparison (each capture weighted once; exploratory)")
    figure.tight_layout(rect=[0, 0, 1, 0.95])
    return _save_figure(figure, directory, "temporal_source_stratified_comparison")


def _expected_paths(output_root: Path) -> list[Path]:
    return [
        output_root / "tables" / "temporal_capture_summary.csv",
        output_root / "tables" / "temporal_stratum_summary.csv",
        output_root / "tables" / "temporal_inclusion_exclusion.csv",
        output_root / "qa" / "temporal_diagnostics.csv",
        output_root / "qa" / "temporal_qa_report.md",
        output_root / "summaries" / "temporal_analysis_report.md",
        *[
            output_root / "figures" / f"{stem}.{suffix}"
            for stem in (
                "temporal_temperature_series",
                "temporal_delta_t_series",
                "temporal_source_stratified_comparison",
            )
            for suffix in ("png", "pdf")
        ],
    ]


def validate_temporal_outputs(output_root: Path, *, canonical_hash: str | None = None) -> dict[str, Any]:
    validation_path = output_root / "qa" / "temporal_output_validation.json"
    if not validation_path.is_file():
        raise ValueError("Temporal output validation record is missing.")
    payload = json.loads(validation_path.read_text(encoding="utf-8"))
    if canonical_hash and payload.get("canonical_sha256") != canonical_hash:
        raise ValueError("Temporal outputs do not match the current canonical input.")
    missing = [path.resolve().as_posix() for path in _expected_paths(output_root) if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise ValueError(f"Temporal output is incomplete: {missing[:10]}")
    return payload


def run_temporal_analysis(
    canonical_parquet: Path,
    *,
    output_root: Path,
    default_timezone: str,
    resume: bool = True,
    dry_run: bool = False,
) -> TemporalRunResult | dict[str, str]:
    ZoneInfo(default_timezone)
    canonical_parquet = canonical_parquet.resolve()
    if not canonical_parquet.is_file():
        raise FileNotFoundError(canonical_parquet)
    canonical_hash = sha256_file(canonical_parquet)
    config_hash = _config_hash(default_timezone)
    state_path = output_root / "qa" / "temporal_stage_state.json"
    validation_path = output_root / "qa" / "temporal_output_validation.json"
    if dry_run:
        return {
            "status": "planned_dry_run",
            "canonical_parquet": canonical_parquet.as_posix(),
            "canonical_sha256": canonical_hash,
            "default_timezone": default_timezone,
            "temporal_unit": "one image/capture time",
        }
    if resume and state_path.is_file() and validation_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("canonical_sha256") == canonical_hash and state.get("config_sha256") == config_hash:
            try:
                validate_temporal_outputs(output_root, canonical_hash=canonical_hash)
            except (OSError, ValueError, json.JSONDecodeError):
                pass
            else:
                paths = _expected_paths(output_root)
                return TemporalRunResult(
                    "cache_hit", output_root, paths[0], paths[1], paths[2], paths[3], paths[4], paths[5], validation_path
                )

    frame = pd.read_parquet(canonical_parquet)
    captures, inclusion, diagnostics = build_capture_summary(frame, default_timezone=default_timezone)
    strata = build_stratum_summary(captures)
    tables = output_root / "tables"
    qa = output_root / "qa"
    summaries = output_root / "summaries"
    figures = output_root / "figures"
    for directory in (tables, qa, summaries, figures):
        directory.mkdir(parents=True, exist_ok=True)
    capture_path = tables / "temporal_capture_summary.csv"
    stratum_path = tables / "temporal_stratum_summary.csv"
    inclusion_path = tables / "temporal_inclusion_exclusion.csv"
    diagnostics_path = qa / "temporal_diagnostics.csv"
    captures.to_csv(capture_path, index=False, encoding="utf-8-sig", float_format="%.8g")
    strata.to_csv(stratum_path, index=False, encoding="utf-8-sig", float_format="%.8g")
    inclusion.to_csv(inclusion_path, index=False, encoding="utf-8-sig")
    diagnostics.to_csv(diagnostics_path, index=False, encoding="utf-8-sig")
    figure_paths = [
        *_plot_time_series(captures, family="temperature", directory=figures),
        *_plot_time_series(captures, family="delta_t", directory=figures),
        *_plot_source_panel(captures, figures),
    ]
    del figure_paths
    valid_times = int(captures.get("capture_time_valid", pd.Series(dtype=bool)).astype(bool).sum()) if not captures.empty else 0
    multi = int(strata["trend_status"].eq("multi_capture_descriptive_exploratory").sum()) if not strata.empty else 0
    single = int(strata["trend_status"].eq("single_capture_descriptive_no_trend").sum()) if not strata.empty else 0
    qa_report = qa / "temporal_qa_report.md"
    _atomic_text(
        qa_report,
        "\n".join(
            [
                "# Temporal analysis QA", "",
                f"- Canonical SHA-256: `{canonical_hash}`",
                f"- Output timezone: `{default_timezone}`",
                "- Naive timestamps use the recorded capture timezone; if absent, the output timezone is an explicit assumption.",
                f"- Capture/source/target rows: {len(captures)}",
                f"- Valid chronological rows: {valid_times}",
                f"- Diagnostic rows: {len(diagnostics)}",
                f"- Multi-capture compatible strata: {multi}",
                f"- Single-capture descriptive strata: {single}",
                "- Pixels, polygon pixels, TAT3 points, and regions are within-image spatial observations, not temporal replicates.",
                "- Cross-time summaries use one row per capture and equal-capture weighting.",
                "- Measurement types, source methods, temperature definitions, ambient definitions, provenance, and target IDs are not silently pooled.",
                "- Missing ambient values are not fabricated; temperature remains descriptive while ΔT is unavailable.",
                "- No interpolation is performed. Irregular intervals are retained and reported.",
                "- q01/q95/q99 bands describe within-image variation; they are not confidence intervals.",
                "- Any multi-capture interpretation is exploratory; a single capture is not a temporal trend.",
            ]
        )
        + "\n",
    )
    report_path = summaries / "temporal_analysis_report.md"
    _atomic_text(
        report_path,
        "\n".join(
            [
                "# Capture-level temporal analysis", "",
                f"The run produced {len(captures)} capture/source/target summaries and {len(strata)} compatibility-stratum summaries.",
                "Time series are chronological, use equal image/capture weighting, and do not interpolate missing times.",
                "Within-image quantiles show descriptive spatial variation rather than across-time uncertainty.",
                "Inferential interpretation is exploratory. One capture is reported as descriptive and never called a trend.",
                "The software does not contain or fabricate a 26°C result; a real soccer-field result requires accepted per-capture polygons, real compatible temperature matrices, and the correct ambient records.",
            ]
        )
        + "\n",
    )
    validation = {
        "status": "complete",
        "canonical_parquet": canonical_parquet.as_posix(),
        "canonical_sha256": canonical_hash,
        "config_sha256": config_hash,
        "default_timezone": default_timezone,
        "capture_summary_rows": len(captures),
        "stratum_summary_rows": len(strata),
        "diagnostic_rows": len(diagnostics),
        "expected_files": [path.resolve().as_posix() for path in _expected_paths(output_root)],
    }
    _atomic_text(validation_path, json.dumps(validation, indent=2, ensure_ascii=False))
    _atomic_text(
        state_path,
        json.dumps(
            {"status": "complete", "canonical_sha256": canonical_hash, "config_sha256": config_hash},
            indent=2,
        ),
    )
    validate_temporal_outputs(output_root, canonical_hash=canonical_hash)
    return TemporalRunResult(
        "complete", output_root, capture_path, stratum_path, inclusion_path,
        diagnostics_path, qa_report, report_path, validation_path,
    )
