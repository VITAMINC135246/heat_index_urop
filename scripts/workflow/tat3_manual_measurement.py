"""Parse and analyze temporary TAT3 point/region measurement reports."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .extreme_temperature import extreme_summary
from .legacy_loader import load_numbered_script
from .models import MeasurementType
from .result_index import sha256_file


POINT_RE = re.compile(
    r"(?i)\bpoint\s+(?P<id>[A-Za-z0-9_.-]+)(?:\s*[:;,])?.*?"
    r"(?:x\s*=\s*(?P<x>-?\d+(?:\.\d+)?)[,; ]+y\s*=\s*(?P<y>-?\d+(?:\.\d+)?).*?)?"
    r"(?:temperature|temp|value)\s*=\s*(?P<value>-?\d+(?:\.\d+)?)\s*(?P<unit>°?\s*[CFK])?"
)
REGION_RE = re.compile(
    r"(?i)\bregion\s+(?P<id>[A-Za-z0-9_.-]+)(?:\s*[:;,])?.*?"
    r"min\s*=\s*(?P<min>-?\d+(?:\.\d+)?).*?max\s*=\s*(?P<max>-?\d+(?:\.\d+)?).*?"
    r"mean\s*=\s*(?P<mean>-?\d+(?:\.\d+)?)\s*(?P<unit>°?\s*[CFK])?"
)
GEOMETRY_RE = re.compile(r"(?i)(?:geometry|polygon|rectangle|ellipse)\s*=\s*(?P<geometry>.+?)(?:;\s*(?:min|max|mean)\s*=|$)")
AMBIENT_RE = re.compile(r"(?i)ambient(?:\s+temperature|\s+temp)?\s*[:=]\s*(-?\d+(?:\.\d+)?)\s*°?\s*C")
IMAGE_RE = re.compile(r"(?i)\b(DJI_\d{14}_\d+)(?:_T)?(?:\.JPE?G)?\b")


@dataclass(slots=True)
class TAT3ReportResult:
    manifest: dict[str, Any]
    measurements: pd.DataFrame
    report_entries: list[dict[str, Any]]


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _text_lines(path: Path) -> list[str]:
    if path.suffix.lower() == ".txt":
        return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    legacy = load_numbered_script(
        "scripts/part_d/03_parse_tat3_ambient_temperature_reports.py",
        "heat_index_tat3_ambient_parser_v02",
    )
    return legacy.extract_docx_paragraphs(path)


def _ambient_entries(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() != ".docx":
        return []
    legacy = load_numbered_script(
        "scripts/part_d/03_parse_tat3_ambient_temperature_reports.py",
        "heat_index_tat3_ambient_parser_v02",
    )
    return [legacy.parse_report_entry(entry) for entry in legacy.split_report_entries(path)]


def _validate_unit(unit: str | None, line: str) -> None:
    resolved = (unit or "C").replace("°", "").strip().upper()
    if resolved != "C" or re.search(r"(?i)fahrenheit|kelvin", line):
        raise ValueError(f"TAT3 measurement units must be Celsius; received {unit or line!r}.")


def parse_tat3_report(
    report_path: Path,
    *,
    expected_image_id: str | None = None,
    target_name: str,
    luhk_code: str,
    luhk_category: str,
    luhk_provenance: str,
    surface_cover_category: str,
    screenshot_path: Path | None = None,
    notes: str = "",
) -> TAT3ReportResult:
    if not report_path.is_file():
        raise FileNotFoundError(report_path)
    lines = _text_lines(report_path)
    entries = _ambient_entries(report_path)
    text_image_ids = {match.group(1).upper() for line in lines for match in IMAGE_RE.finditer(line)}
    if expected_image_id and text_image_ids and expected_image_id.upper() not in text_image_ids:
        raise ValueError(f"TAT3 report image IDs {sorted(text_image_ids)} do not include {expected_image_id}.")
    selected_entry: dict[str, Any] = {}
    if expected_image_id:
        matching = [entry for entry in entries if str(entry.get("image_id", "")) == expected_image_id]
        if entries and len(matching) != 1:
            raise ValueError(f"Expected exactly one TAT3 report entry for {expected_image_id}; found {len(matching)}.")
        selected_entry = matching[0] if matching else {}
    elif len(entries) == 1:
        selected_entry = entries[0]
        expected_image_id = str(selected_entry.get("image_id", ""))
    image_id = expected_image_id or ""
    ambient = selected_entry.get("ambient_temperature_c")
    if ambient in (None, ""):
        ambient_match = next((AMBIENT_RE.search(line) for line in lines if AMBIENT_RE.search(line)), None)
        ambient = float(ambient_match.group(1)) if ambient_match else None
    capture_time = str(selected_entry.get("report_capture_datetime", ""))
    measurements: list[dict[str, Any]] = []
    for line in lines:
        point = POINT_RE.search(line)
        if point:
            _validate_unit(point.group("unit"), line)
            x = float(point.group("x")) if point.group("x") is not None else np.nan
            y = float(point.group("y")) if point.group("y") is not None else np.nan
            value = float(point.group("value"))
            measurements.append(
                {
                    "measurement_id": point.group("id"),
                    "measurement_name": point.group("id"),
                    "measurement_type": MeasurementType.MANUAL_TAT3_POINT.value,
                    "temperature_statistic": "point_value",
                    "temperature_c": value,
                    "point_x": x,
                    "point_y": y,
                    "region_type": "",
                    "region_geometry": "",
                    "region_min_c": np.nan,
                    "region_max_c": np.nan,
                    "region_mean_c": np.nan,
                }
            )
            continue
        region = REGION_RE.search(line)
        if region:
            _validate_unit(region.group("unit"), line)
            geometry_match = GEOMETRY_RE.search(line)
            geometry = geometry_match.group("geometry").strip() if geometry_match else ""
            region_type = "polygon" if "polygon" in line.casefold() else "region"
            for statistic in ("min", "max", "mean"):
                measurements.append(
                    {
                        "measurement_id": f"{region.group('id')}:{statistic}",
                        "measurement_name": region.group("id"),
                        "measurement_type": MeasurementType.MANUAL_TAT3_REGION.value,
                        "temperature_statistic": statistic,
                        "temperature_c": float(region.group(statistic)),
                        "point_x": np.nan,
                        "point_y": np.nan,
                        "region_type": region_type,
                        "region_geometry": geometry,
                        "region_min_c": float(region.group("min")),
                        "region_max_c": float(region.group("max")),
                        "region_mean_c": float(region.group("mean")),
                    }
                )
    identifiers = [row["measurement_id"] for row in measurements]
    duplicates = sorted({value for value in identifiers if identifiers.count(value) > 1})
    if duplicates:
        raise ValueError(f"Duplicate TAT3 measurement IDs: {duplicates}")
    screenshot_hash = sha256_file(screenshot_path) if screenshot_path and screenshot_path.is_file() else ""
    frame = pd.DataFrame(measurements)
    if not frame.empty:
        frame.insert(0, "report_id", report_path.stem)
        frame.insert(1, "image_id", image_id)
        frame.insert(2, "capture_time", capture_time)
        frame["ambient_temperature_c"] = pd.to_numeric(ambient, errors="coerce")
        frame["delta_t_c"] = frame["temperature_c"] - frame["ambient_temperature_c"]
        frame["target_name"] = target_name
        frame["luhk_code"] = luhk_code
        frame["luhk_category"] = luhk_category
        frame["luhk_provenance"] = luhk_provenance
        frame["surface_cover_category"] = surface_cover_category
        frame["surface_cover_provenance"] = "tat3_report_user_context"
        frame["source_report"] = report_path.resolve().as_posix()
        frame["source_report_sha256"] = sha256_file(report_path)
        frame["screenshot_evidence"] = screenshot_path.resolve().as_posix() if screenshot_path else ""
        frame["screenshot_sha256"] = screenshot_hash
        frame["validation_status"] = "valid" if image_id else "image_id_unresolved"
        frame["spatial_location_available"] = (
            np.isfinite(frame["point_x"]) & np.isfinite(frame["point_y"])
        ) | frame["region_geometry"].astype(str).str.strip().ne("")
        frame["notes"] = notes
    manifest = {
        "schema_version": "temporary-tat3-0.2.0",
        "persistence_scope": "temporary_session",
        "report_id": report_path.stem,
        "source_report": report_path.resolve().as_posix(),
        "source_report_sha256": sha256_file(report_path),
        "image_id": image_id,
        "capture_time": capture_time,
        "ambient_temperature_c": ambient,
        "report_parameters": {key: _json_value(value) for key, value in selected_entry.items()},
        "report_entry_count": len(entries),
        "measurement_record_count": len(frame),
        "measurement_layout_status": "manual_measurements" if not frame.empty else "ambient_metadata_only",
        "target_name": target_name,
        "luhk_code": luhk_code,
        "luhk_category": luhk_category,
        "luhk_provenance": luhk_provenance,
        "surface_cover_category": surface_cover_category,
        "surface_cover_provenance": "tat3_report_user_context",
        "screenshot_evidence": screenshot_path.resolve().as_posix() if screenshot_path else "",
        "screenshot_sha256": screenshot_hash,
        "temporal_observation_policy": "one image/capture time is one temporal observation; points and regions are within-image spatial measurements",
        "notes": notes,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    return TAT3ReportResult(manifest, frame, entries)


def plot_manual_tat3_measurements(
    frame: pd.DataFrame,
    output_path: Path,
    *,
    screenshot_evidence: str = "",
) -> dict[str, Any]:
    """Plot real report coordinates when present, otherwise a labelled value chart."""
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    if frame.empty:
        raise ValueError("Manual TAT3 plotting requires at least one measurement record.")
    points = frame.loc[
        frame["measurement_type"].eq(MeasurementType.MANUAL_TAT3_POINT.value)
        & np.isfinite(frame["point_x"]) & np.isfinite(frame["point_y"])
    ].copy()
    regions = frame.loc[
        frame["measurement_type"].eq(MeasurementType.MANUAL_TAT3_REGION.value)
        & frame["region_geometry"].astype(str).str.strip().ne("")
    ].drop_duplicates("measurement_name")
    spatial = not points.empty or not regions.empty
    figure, axis = plt.subplots(figsize=(10, 6.8), facecolor="white")
    if spatial:
        if not points.empty:
            scatter = axis.scatter(
                points["point_x"], points["point_y"], c=points["temperature_c"],
                cmap="inferno", s=85, edgecolor="black", label="TAT3 point",
            )
            figure.colorbar(scatter, ax=axis, label="Temperature (°C)")
            for row in points.itertuples(index=False):
                axis.annotate(
                    f"{row.measurement_name}: {row.temperature_c:.2f}°C",
                    (row.point_x, row.point_y), xytext=(5, 5), textcoords="offset points", fontsize=8,
                )
        for row in regions.itertuples(index=False):
            numbers = [float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", str(row.region_geometry))]
            if len(numbers) >= 4 and len(numbers) % 2 == 0:
                coordinates = np.asarray(numbers, dtype=float).reshape(-1, 2)
                coordinates = np.vstack([coordinates, coordinates[0]])
                axis.plot(coordinates[:, 0], coordinates[:, 1], linewidth=1.8, label=f"Region {row.measurement_name}")
        axis.invert_yaxis()
        axis.set_xlabel("Report x coordinate")
        axis.set_ylabel("Report y coordinate")
        axis.set_title("Manual TAT3 measurements at report-supplied locations")
        axis.legend(loc="best", fontsize=8)
    else:
        labels = frame["measurement_name"].astype(str) + ":" + frame["temperature_statistic"].astype(str)
        positions = np.arange(len(frame))
        axis.bar(positions, frame["temperature_c"].astype(float), color="#D55E00")
        axis.set_xticks(positions, labels, rotation=30, ha="right")
        axis.set_ylabel("Temperature (°C)")
        axis.set_title("Manual TAT3 values — spatial location unavailable")
        axis.text(
            0.5, 0.96, "The report supplied no usable point coordinates or region geometry; no location was invented.",
            transform=axis.transAxes, ha="center", va="top", fontsize=9, color="#9C2F2F",
        )
    source = f"Screenshot evidence: {screenshot_evidence}" if screenshot_evidence else "No annotated screenshot supplied."
    figure.text(0.01, 0.01, source, fontsize=8)
    figure.tight_layout(rect=[0, 0.04, 1, 1])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180)
    figure.savefig(output_path.with_suffix(".pdf"))
    plt.close(figure)
    return {
        "spatial_location_available": spatial,
        "point_location_count": int(len(points)),
        "region_geometry_count": int(len(regions)),
        "screenshot_evidence": screenshot_evidence,
    }


def write_temporary_tat3_bundle(result: TAT3ReportResult, output_directory: Path) -> dict[str, Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    manifest_path = output_directory / "temporary_manifest.json"
    measurements_path = output_directory / "manual_measurements.parquet"
    summary_path = output_directory / "extreme_summary.csv"
    coordinates_path = output_directory / "extreme_coordinates.csv"
    plot_path = output_directory / "manual_measurement_extremes.png"
    analysis_path = output_directory / "temporary_analysis.md"
    if not result.measurements.empty:
        result.measurements.to_parquet(measurements_path, index=False, compression="zstd")
        summary, coordinates = extreme_summary(
            result.measurements.rename(columns={"point_y": "thermal_row", "point_x": "thermal_col"}),
            group_columns=("image_id", "measurement_type", "target_name", "surface_cover_category", "luhk_category"),
        )
        region_geometry = result.measurements.loc[
            result.measurements["measurement_type"].eq(MeasurementType.MANUAL_TAT3_REGION.value)
            & result.measurements["region_geometry"].astype(str).str.strip().ne("")
        ].drop_duplicates("measurement_name")
        if not region_geometry.empty:
            summary.loc[
                summary["measurement_type"].eq(MeasurementType.MANUAL_TAT3_REGION.value),
                "spatial_location_available",
            ] = True
            geometry_rows = pd.DataFrame([
                {
                    "image_id": row.image_id,
                    "measurement_type": row.measurement_type,
                    "target_name": row.target_name,
                    "surface_cover_category": row.surface_cover_category,
                    "luhk_category": row.luhk_category,
                    "location_type": "region_geometry",
                    "thermal_row": np.nan,
                    "thermal_col": np.nan,
                    "temperature_c": row.region_mean_c,
                    "region_geometry": row.region_geometry,
                    "selection_rule": "report-supplied region geometry; within-region extreme coordinates unavailable",
                }
                for row in region_geometry.itertuples(index=False)
            ])
            coordinates = pd.concat([coordinates, geometry_rows], ignore_index=True)
        summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
        coordinates.to_csv(coordinates_path, index=False, encoding="utf-8-sig")
        plot_info = plot_manual_tat3_measurements(
            result.measurements, plot_path,
            screenshot_evidence=str(result.manifest.get("screenshot_evidence", "")),
        )
        result.manifest["plot_spatial_location_available"] = plot_info["spatial_location_available"]
        result.manifest["plot_location_policy"] = "report coordinates/geometry only; no inferred locations"
        analysis_lines = [
            "# Temporary TAT3 manual-measurement analysis", "",
            f"- Measurement records: {len(result.measurements)}",
            f"- Spatial locations available: {plot_info['spatial_location_available']}",
            "- Temporal unit: one image/capture time.",
            "- Points and region statistics are within-image spatial observations, not temporal replicates.",
            "- No temporal/generalizable significance test was performed.",
        ]
        if not plot_info["spatial_location_available"]:
            analysis_lines.append("- The report supplied no usable spatial coordinates; no location was invented.")
    else:
        analysis_lines = [
            "# Temporary TAT3 report inspection", "",
            "- Layout: ambient/parameter metadata only.",
            "- Manual point/region records: 0.",
            "- No measurement locations or values were manufactured.",
        ]
    analysis_path.write_text("\n".join(analysis_lines) + "\n", encoding="utf-8")
    artifact_paths = [measurements_path, summary_path, coordinates_path, plot_path, plot_path.with_suffix(".pdf"), analysis_path]
    result.manifest["artifacts"] = {
        path.name: {"path": path.resolve().as_posix(), "sha256": sha256_file(path)}
        for path in artifact_paths if path.is_file()
    }
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result.manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(manifest_path)
    return {
        "manifest": manifest_path,
        "measurements": measurements_path,
        "extreme_summary": summary_path,
        "extreme_coordinates": coordinates_path,
        "plot": plot_path,
        "analysis": analysis_path,
    }
