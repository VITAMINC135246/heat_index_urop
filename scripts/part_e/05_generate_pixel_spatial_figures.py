#!/usr/bin/env python3
"""Generate schema-aware spatial figures from the shared canonical Parquet."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import pandas as pd
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".matplotlib-cache"))
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


PIXEL_MEASUREMENTS = {"full_thermal_pixel", "polygon_selected_thermal_pixel"}
STEMS = (
    "temperature_map",
    "delta_t_map",
    "surface_cover_overlay",
    "luhk_overlay",
    "target_overlay",
    "shadow_overlay",
    "analysis_eligibility_mask",
    "combined_qa_panel",
)
COLORS = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#D55E00", "#56B4E9", "#999999", "#332288"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--canonical-parquet", default="")
    parser.add_argument("--output-directory", default="")
    parser.add_argument("--image-id", default="")
    return parser.parse_args()


def project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-._")
    return cleaned or "unknown"


def save(fig: plt.Figure, directory: Path, stem: str) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = [directory / f"{stem}.png", directory / f"{stem}.pdf"]
    fig.savefig(paths[0], dpi=180, bbox_inches="tight", facecolor="white")
    fig.savefig(paths[1], bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return paths


def finite_limits(matrix: np.ndarray) -> tuple[float, float] | None:
    values = matrix[np.isfinite(matrix)]
    if not values.size:
        return None
    low, high = np.quantile(values, [0.01, 0.99])
    if not np.isfinite(low) or not np.isfinite(high):
        return None
    if low == high:
        pad = max(0.5, abs(float(low)) * 0.01)
        low, high = low - pad, high + pad
    return float(low), float(high)


def unavailable(title: str, reason: str, source: str, directory: Path, stem: str) -> list[Path]:
    fig, axis = plt.subplots(figsize=(9, 5.5), facecolor="white")
    axis.axis("off")
    axis.text(0.5, 0.60, "UNAVAILABLE", ha="center", va="center", fontsize=24, weight="bold", color="#777777")
    axis.text(0.5, 0.44, reason, ha="center", va="center", fontsize=12, wrap=True)
    axis.text(0.5, 0.10, source, ha="center", va="center", fontsize=9, color="#555555", wrap=True)
    axis.set_title(title, fontsize=14)
    return save(fig, directory, stem)


def scalar_map(
    matrix: np.ndarray,
    *,
    title: str,
    label: str,
    cmap: str,
    source: str,
    directory: Path,
    stem: str,
) -> list[Path]:
    limits = finite_limits(matrix)
    if limits is None:
        return unavailable(title, f"No finite {label} values are available; no values were imputed.", source, directory, stem)
    fig, axis = plt.subplots(figsize=(10, 6), facecolor="white")
    image = axis.imshow(matrix, origin="upper", cmap=cmap, vmin=limits[0], vmax=limits[1], interpolation="nearest")
    colorbar = fig.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
    colorbar.set_label(label)
    axis.set_title(title)
    axis.set_xlabel("Thermal column / pixel_x")
    axis.set_ylabel("Thermal row / pixel_y")
    axis.text(0, -0.13, source, transform=axis.transAxes, fontsize=9, wrap=True)
    fig.tight_layout()
    return save(fig, directory, stem)


def categorical_overlay(
    base: np.ndarray,
    values: np.ndarray,
    known: np.ndarray,
    *,
    title: str,
    unavailable_reason: str,
    source: str,
    directory: Path,
    stem: str,
) -> list[Path]:
    categories = sorted({str(value) for value in values[known] if str(value).strip()})
    if not categories:
        return unavailable(title, unavailable_reason, source, directory, stem)
    mapped = np.full(values.shape, np.nan, dtype=float)
    for index, value in enumerate(categories):
        mapped[known & (values.astype(str) == value)] = index
    cmap = ListedColormap([COLORS[index % len(COLORS)] for index in range(max(1, len(categories)))])
    fig, axis = plt.subplots(figsize=(11, 6.5), facecolor="white")
    axis.imshow(base, origin="upper", cmap="gray", interpolation="nearest")
    axis.imshow(mapped, origin="upper", cmap=cmap, alpha=0.55, interpolation="nearest", vmin=0, vmax=max(1, len(categories) - 1))
    handles = [Patch(facecolor=COLORS[index % len(COLORS)], label=value) for index, value in enumerate(categories)]
    handles.append(Patch(facecolor="#BBBBBB", alpha=0.35, label="unknown / unavailable context"))
    axis.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.01, 1), frameon=False, fontsize=9)
    axis.set_title(title)
    axis.set_xlabel("Thermal column / pixel_x")
    axis.set_ylabel("Thermal row / pixel_y")
    axis.text(0, -0.13, source, transform=axis.transAxes, fontsize=9, wrap=True)
    fig.tight_layout()
    return save(fig, directory, stem)


def target_overlay(
    base: np.ndarray,
    target: np.ndarray,
    *,
    applicable: bool,
    source: str,
    directory: Path,
    stem: str,
    title: str,
) -> list[Path]:
    if not applicable:
        return unavailable(title, "No target/polygon restriction applies to this full-image result.", source, directory, stem)
    if not target.any():
        return unavailable(title, "The canonical target mask contains no accepted target pixels.", source, directory, stem)
    fig, axis = plt.subplots(figsize=(10, 6), facecolor="white")
    axis.imshow(base, origin="upper", cmap="gray", interpolation="nearest")
    rgba = np.zeros((*target.shape, 4), dtype=float)
    rgba[target] = [0.0, 0.62, 0.45, 0.48]
    axis.imshow(rgba, origin="upper", interpolation="nearest")
    axis.contour(target.astype(float), levels=[0.5], colors=["#D55E00"], linewidths=1.8, origin="upper")
    axis.set_title(title)
    axis.set_xlabel("Thermal column / pixel_x")
    axis.set_ylabel("Thermal row / pixel_y")
    axis.text(
        0,
        -0.15,
        "Accepted boundary in orange; green is inside target. Outside context remains unknown and is not extrapolated.\n" + source,
        transform=axis.transAxes,
        fontsize=9,
        wrap=True,
    )
    fig.tight_layout()
    return save(fig, directory, stem)


def shadow_overlay(
    base: np.ndarray,
    shadow: np.ndarray,
    shadow_known: np.ndarray,
    *,
    source: str,
    directory: Path,
    stem: str,
    title: str,
) -> list[Path]:
    if not shadow_known.any():
        return unavailable(title, "Shadow is unavailable; missing values were not converted to zero.", source, directory, stem)
    fig, axis = plt.subplots(figsize=(10, 6), facecolor="white")
    axis.imshow(base, origin="upper", cmap="gray", interpolation="nearest")
    rgba = np.zeros((*shadow.shape, 4), dtype=float)
    rgba[shadow_known & shadow] = [0.84, 0.15, 0.16, 0.65]
    rgba[shadow_known & ~shadow] = [0.2, 0.55, 0.9, 0.16]
    axis.imshow(rgba, origin="upper", interpolation="nearest")
    axis.set_title(title)
    axis.set_xlabel("Thermal column / pixel_x")
    axis.set_ylabel("Thermal row / pixel_y")
    axis.text(
        0,
        -0.13,
        f"Known shadow pixels: {int(shadow_known.sum()):,}; shadow_flag=1: {int((shadow_known & shadow).sum()):,}. {source}",
        transform=axis.transAxes,
        fontsize=9,
        wrap=True,
    )
    fig.tight_layout()
    return save(fig, directory, stem)


def eligibility_map(
    base: np.ndarray,
    eligible: np.ndarray,
    known: np.ndarray,
    *,
    source: str,
    directory: Path,
    stem: str,
    title: str,
) -> list[Path]:
    state = np.zeros(base.shape, dtype=np.int8)
    state[known & ~eligible] = 1
    state[eligible] = 2
    fig, axis = plt.subplots(figsize=(10, 6), facecolor="white")
    axis.imshow(base, origin="upper", cmap="gray", interpolation="nearest")
    axis.imshow(state, origin="upper", cmap=ListedColormap(["#AAAAAA", "#D55E00", "#009E73"]), alpha=0.58, vmin=0, vmax=2)
    axis.legend(
        handles=[
            Patch(facecolor="#009E73", label="analysis eligible"),
            Patch(facecolor="#D55E00", label="known but excluded"),
            Patch(facecolor="#AAAAAA", label="unknown / outside target"),
        ],
        loc="upper left",
        bbox_to_anchor=(1.01, 1),
        frameon=False,
    )
    axis.set_title(title)
    axis.set_xlabel("Thermal column / pixel_x")
    axis.set_ylabel("Thermal row / pixel_y")
    axis.text(0, -0.13, source, transform=axis.transAxes, fontsize=9, wrap=True)
    fig.tight_layout()
    return save(fig, directory, stem)


def _draw_panel_scalar(axis: plt.Axes, matrix: np.ndarray, title: str, cmap: str) -> None:
    limits = finite_limits(matrix)
    if limits is None:
        axis.axis("off")
        axis.text(0.5, 0.5, f"{title}\nUNAVAILABLE", ha="center", va="center")
        return
    axis.imshow(matrix, origin="upper", cmap=cmap, vmin=limits[0], vmax=limits[1], interpolation="nearest")
    axis.set_title(title)


def combined_panel(unit: dict[str, Any], *, source: str, directory: Path, stem: str, title: str) -> list[Path]:
    fig, axes = plt.subplots(2, 4, figsize=(20, 10), facecolor="white")
    _draw_panel_scalar(axes[0, 0], unit["temperature"], "Temperature (°C)", "cividis")
    _draw_panel_scalar(axes[0, 1], unit["delta_t"], "ΔT (°C)", "coolwarm")
    for axis, values, known, panel_title in (
        (axes[0, 2], unit["cover"], unit["cover_known"], "Surface cover"),
        (axes[0, 3], unit["luhk"], unit["luhk_known"], "LUHK context"),
    ):
        categories = sorted({str(value) for value in values[known] if str(value).strip()})
        if not categories:
            axis.axis("off")
            axis.text(0.5, 0.5, f"{panel_title}\nUNAVAILABLE", ha="center", va="center")
        else:
            mapped = np.full(values.shape, np.nan)
            for index, value in enumerate(categories):
                mapped[known & (values.astype(str) == value)] = index
            axis.imshow(mapped, origin="upper", cmap=ListedColormap(COLORS), interpolation="nearest")
            axis.set_title(panel_title)
    axes[1, 0].imshow(unit["temperature"], origin="upper", cmap="gray")
    if unit["target_applicable"] and unit["target"].any():
        axes[1, 0].contour(unit["target"].astype(float), levels=[0.5], colors=["#D55E00"], origin="upper")
        axes[1, 0].set_title("Accepted target boundary")
    else:
        axes[1, 0].set_title("Target: not applicable")
    axes[1, 1].imshow(unit["temperature"], origin="upper", cmap="gray")
    if unit["shadow_known"].any():
        rgba = np.zeros((*unit["shadow"].shape, 4))
        rgba[unit["shadow_known"] & unit["shadow"]] = [0.84, 0.15, 0.16, 0.65]
        axes[1, 1].imshow(rgba, origin="upper")
        axes[1, 1].set_title("Shadow")
    else:
        axes[1, 1].axis("off")
        axes[1, 1].text(0.5, 0.5, "Shadow\nUNAVAILABLE", ha="center", va="center")
    state = np.zeros(unit["temperature"].shape, dtype=np.int8)
    state[unit["known"] & ~unit["eligible"]] = 1
    state[unit["eligible"]] = 2
    axes[1, 2].imshow(state, origin="upper", cmap=ListedColormap(["#AAAAAA", "#D55E00", "#009E73"]), vmin=0, vmax=2)
    axes[1, 2].set_title("Eligibility / unknown")
    axes[1, 3].axis("off")
    axes[1, 3].text(
        0.02,
        0.98,
        "\n".join(
            [
                f"Grid: {unit['height']} × {unit['width']}",
                f"Finite temperature: {int(np.isfinite(unit['temperature']).sum()):,}",
                f"Eligible: {int(unit['eligible'].sum()):,}",
                f"Known cover: {int(unit['cover_known'].sum()):,}",
                f"Known LUHK: {int(unit['luhk_known'].sum()):,}",
                f"Target pixels: {int(unit['target'].sum()):,}",
                "Quantile bands are descriptive within-image variation, not confidence intervals.",
                source,
            ]
        ),
        va="top",
        fontsize=10,
        wrap=True,
    )
    for axis in axes.flat[:7]:
        if axis.axison:
            axis.set_xlabel("thermal_col", fontsize=9)
            axis.set_ylabel("thermal_row", fontsize=9)
    fig.suptitle(title, fontsize=16)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    return save(fig, directory, stem)


def matrix(group: pd.DataFrame, column: str, height: int, width: int, default: Any) -> np.ndarray:
    result = np.full((height, width), default, dtype=object if isinstance(default, str) else None)
    rows = group["thermal_row"].astype(int).to_numpy()
    cols = group["thermal_col"].astype(int).to_numpy()
    result[rows, cols] = group[column].to_numpy()
    return result


def build_unit(group: pd.DataFrame) -> dict[str, Any]:
    rows = pd.to_numeric(group["thermal_row"], errors="coerce")
    cols = pd.to_numeric(group["thermal_col"], errors="coerce")
    if rows.isna().any() or cols.isna().any() or (rows < 0).any() or (cols < 0).any():
        raise ValueError("invalid_thermal_coordinates")
    coordinate_pairs = pd.DataFrame({"row": rows.astype(int), "col": cols.astype(int)})
    if coordinate_pairs.duplicated().any():
        raise ValueError("duplicate_thermal_coordinates")
    height_values = pd.to_numeric(group.get("image_height", pd.Series(dtype=float)), errors="coerce").dropna().unique()
    width_values = pd.to_numeric(group.get("image_width", pd.Series(dtype=float)), errors="coerce").dropna().unique()
    height = int(height_values[0]) if len(height_values) == 1 else int(rows.max()) + 1
    width = int(width_values[0]) if len(width_values) == 1 else int(cols.max()) + 1
    if len(group) != height * width or int(rows.max()) >= height or int(cols.max()) >= width:
        raise ValueError(f"incomplete_native_grid:{len(group)}_rows_for_{height}x{width}")
    temperature = matrix(group.assign(temperature_c=pd.to_numeric(group["temperature_c"], errors="coerce")), "temperature_c", height, width, np.nan).astype(float)
    delta_t = matrix(group.assign(delta_t_c=pd.to_numeric(group.get("delta_t_c"), errors="coerce")), "delta_t_c", height, width, np.nan).astype(float)
    cover = matrix(group.fillna({"surface_cover_class": ""}), "surface_cover_class", height, width, "").astype(str)
    luhk = matrix(group.fillna({"luhk_class_name": ""}), "luhk_class_name", height, width, "").astype(str)
    cover_known = matrix(group, "surface_cover_known" if "surface_cover_known" in group else "label_known", height, width, False).astype(bool)
    luhk_known = matrix(group, "luhk_label_valid" if "luhk_label_valid" in group else "luhk_known", height, width, False).astype(bool)
    target = matrix(group, "target_mask", height, width, False).astype(bool)
    eligible = matrix(group, "analysis_eligible", height, width, False).astype(bool)
    known = matrix(group, "label_known", height, width, False).astype(bool)
    shadow_known = matrix(group, "shadow_valid", height, width, False).astype(bool)
    shadow_values = group["shadow_flag"].fillna(0).astype(int) if "shadow_flag" in group else pd.Series(0, index=group.index)
    shadow = matrix(group.assign(_shadow=shadow_values), "_shadow", height, width, 0).astype(bool)
    measurement = str(group["measurement_type"].iloc[0])
    return {
        "height": height,
        "width": width,
        "temperature": temperature,
        "delta_t": delta_t,
        "cover": cover,
        "luhk": luhk,
        "cover_known": cover_known,
        "luhk_known": luhk_known,
        "target": target,
        "eligible": eligible,
        "known": known,
        "shadow_known": shadow_known,
        "shadow": shadow,
        "target_applicable": measurement == "polygon_selected_thermal_pixel" or not target.all(),
    }


def render_unit(group: pd.DataFrame, unit_key: str, directory: Path) -> tuple[dict[str, Any], list[Path]]:
    unit = build_unit(group)
    image_id = str(group["image_id"].iloc[0])
    source_method = str(group["source_method"].iloc[0])
    measurement_type = str(group["measurement_type"].iloc[0])
    temperature_source = str(group.get("temperature_source", pd.Series([""])).iloc[0])
    temperature_definition = str(group.get("temperature_definition", pd.Series([""])).iloc[0])
    surface_provenance = str(group.get("surface_cover_provenance", pd.Series([""])).iloc[0])
    luhk_provenance = str(group.get("luhk_provenance", pd.Series([""])).iloc[0])
    target_id = str(group.get("target_id", pd.Series([""])).iloc[0])
    target_name = str(group.get("target_name", pd.Series([""])).iloc[0])
    source = (
        f"source_method={source_method}; measurement_type={measurement_type}; temperature_source={temperature_source or 'unspecified'}; "
        f"temperature_definition={temperature_definition or 'unspecified'}; "
        f"surface_cover_provenance={surface_provenance or 'unknown'}; luhk_provenance={luhk_provenance or 'unknown'}; "
        f"target_id={target_id or 'unavailable'}; target_name={target_name or 'unavailable'}"
    )
    prefix = unit_key
    files: list[Path] = []
    files += scalar_map(unit["temperature"], title=f"{image_id} — temperature", label="Temperature (°C)", cmap="cividis", source=source, directory=directory, stem=f"{prefix}_temperature_map")
    files += scalar_map(unit["delta_t"], title=f"{image_id} — ΔT", label="ΔT (°C)", cmap="coolwarm", source=source, directory=directory, stem=f"{prefix}_delta_t_map")
    files += categorical_overlay(
        unit["temperature"], unit["cover"], unit["cover_known"], title=f"{image_id} — surface-cover overlay",
        unavailable_reason="Surface-cover labels are unavailable; unknown pixels were not assigned a class.", source=source,
        directory=directory, stem=f"{prefix}_surface_cover_overlay",
    )
    files += categorical_overlay(
        unit["temperature"], unit["luhk"], unit["luhk_known"], title=f"{image_id} — LUHK overlay",
        unavailable_reason="LUHK context is unavailable; no official or user-supplied category was invented.", source=source,
        directory=directory, stem=f"{prefix}_luhk_overlay",
    )
    files += target_overlay(unit["temperature"], unit["target"], applicable=unit["target_applicable"], source=source, directory=directory, stem=f"{prefix}_target_overlay", title=f"{image_id} — target/polygon overlay")
    files += shadow_overlay(unit["temperature"], unit["shadow"], unit["shadow_known"], source=source, directory=directory, stem=f"{prefix}_shadow_overlay", title=f"{image_id} — shadow overlay")
    files += eligibility_map(unit["temperature"], unit["eligible"], unit["known"], source=source, directory=directory, stem=f"{prefix}_analysis_eligibility_mask", title=f"{image_id} — analysis eligibility / unknown mask")
    files += combined_panel(unit, source=source, directory=directory, stem=f"{prefix}_combined_qa_panel", title=f"{image_id} — canonical spatial QA")
    row = {
        "unit_key": unit_key,
        "image_id": image_id,
        "source_method": source_method,
        "measurement_type": measurement_type,
        "temperature_source": temperature_source,
        "temperature_definition": temperature_definition,
        "surface_cover_provenance": surface_provenance,
        "luhk_provenance": luhk_provenance,
        "target_id": target_id,
        "target_name": target_name,
        "image_height": unit["height"],
        "image_width": unit["width"],
        "ambient_available": bool(np.isfinite(unit["delta_t"]).any()),
        "surface_cover_available": bool(unit["cover_known"].any()),
        "luhk_available": bool(unit["luhk_known"].any()),
        "target_applicable": bool(unit["target_applicable"]),
        "shadow_available": bool(unit["shadow_known"].any()),
        "analysis_eligible_pixel_count": int(unit["eligible"].sum()),
        "status": "generated",
        "exclusion_reason": "",
    }
    return row, files


def validate_outputs(directory: Path, *, expected_hash: str | None = None) -> dict[str, Any]:
    path = directory / "spatial_figure_validation.json"
    if not path.is_file():
        raise ValueError("Spatial validation record is missing.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if expected_hash and payload.get("canonical_sha256") != expected_hash:
        raise ValueError("Spatial validation record does not match the canonical Parquet.")
    if payload.get("method_sha256") != sha256_file(Path(__file__).resolve()):
        raise ValueError("Spatial validation record was generated by a different method version.")
    expected = [directory / value for value in payload.get("expected_figure_files", [])]
    missing = [item.name for item in expected if not item.is_file() or item.stat().st_size < 100]
    if missing:
        raise ValueError(f"Spatial figure output is incomplete: {missing[:10]}")
    if payload.get("status") not in {"complete", "complete_with_recorded_exclusions"}:
        raise ValueError(f"Spatial stage status is not complete: {payload.get('status')}")
    if not expected and not payload.get("recorded_exclusions"):
        raise ValueError("An empty spatial stage cannot be reported as complete.")
    return payload


def run(canonical: Path, directory: Path, image_id: str = "") -> dict[str, Any]:
    if not canonical.is_file():
        raise FileNotFoundError(canonical)
    frame = pd.read_parquet(canonical)
    required = {
        "image_id", "thermal_row", "thermal_col", "temperature_c", "measurement_type",
        "source_method", "analysis_eligible", "label_known", "target_mask",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Canonical Parquet is missing spatial fields: {missing}")
    if image_id:
        frame = frame.loc[frame["image_id"].astype(str).eq(image_id)].copy()
    directory.mkdir(parents=True, exist_ok=True)
    pixel_frame = frame.loc[frame["measurement_type"].astype(str).isin(PIXEL_MEASUREMENTS)].copy()
    rows: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    files: list[Path] = []
    if pixel_frame.empty:
        exclusions.append({"image_id": image_id, "reason": "no_full_or_polygon_pixel_measurements", "status": "not_applicable"})
    else:
        group_columns = ["image_id", "source_method", "measurement_type"]
        source_units = pixel_frame.groupby(group_columns, sort=True, dropna=False, observed=True)
        units_per_image = source_units.size().reset_index().groupby("image_id").size().to_dict()
        for keys, group in source_units:
            selected_image, source_method, measurement_type = map(str, keys)
            unit_key = slug(selected_image)
            if int(units_per_image.get(keys[0], 1)) > 1:
                unit_key += f"__{slug(source_method)}__{slug(measurement_type)}"
            try:
                row, generated = render_unit(group, unit_key, directory)
            except (ValueError, KeyError, TypeError) as exc:
                exclusions.append(
                    {
                        "image_id": selected_image,
                        "source_method": source_method,
                        "measurement_type": measurement_type,
                        "reason": str(exc),
                        "status": "excluded",
                    }
                )
                continue
            rows.append(row)
            files.extend(generated)
    manifest_path = directory / "spatial_figure_manifest.csv"
    pd.DataFrame(rows).to_csv(manifest_path, index=False, encoding="utf-8-sig")
    exclusions_path = directory / "spatial_figure_exclusions.csv"
    exclusion_columns = ["image_id", "source_method", "measurement_type", "reason", "status"]
    pd.DataFrame(exclusions).reindex(columns=exclusion_columns).to_csv(exclusions_path, index=False, encoding="utf-8-sig")
    relative_files = [path.relative_to(directory).as_posix() for path in files]
    status = "complete" if rows and not exclusions else "complete_with_recorded_exclusions"
    validation = {
        "status": status,
        "canonical_parquet": canonical.resolve().as_posix(),
        "canonical_sha256": sha256_file(canonical),
        "method_sha256": sha256_file(Path(__file__).resolve()),
        "generated_unit_count": len(rows),
        "recorded_exclusions": exclusions,
        "expected_stems_per_generated_unit": list(STEMS),
        "expected_figure_files": relative_files,
        "manifest": manifest_path.name,
        "exclusions": exclusions_path.name,
        "source_stratification": "image_id + source_method + measurement_type",
    }
    validation_path = directory / "spatial_figure_validation.json"
    validation_path.write_text(json.dumps(validation, indent=2, ensure_ascii=False), encoding="utf-8")
    validate_outputs(directory, expected_hash=validation["canonical_sha256"])
    return validation


def main() -> int:
    args = parse_args()
    config = json.loads(project_path(args.config).read_text(encoding="utf-8"))
    canonical = project_path(args.canonical_parquet or config["outputs"]["canonical_parquet"])
    directory = project_path(args.output_directory or config["outputs"]["spatial_maps"])
    result = run(canonical, directory, args.image_id)
    print(
        f"Spatial figures complete: units={result['generated_unit_count']}; "
        f"exclusions={len(result['recorded_exclusions'])}; status={result['status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
