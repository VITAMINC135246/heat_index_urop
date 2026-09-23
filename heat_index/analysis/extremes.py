"""Per-image Min/Max/q99 summaries and source-aware location figures."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parents[2] / ".matplotlib-cache"))


def _representative(group: pd.DataFrame, value: float, column: str) -> pd.Series | None:
    tied = group.loc[np.isclose(pd.to_numeric(group[column], errors="coerce"), value, rtol=0.0, atol=1e-7)].copy()
    if {"thermal_row", "thermal_col"}.issubset(tied.columns):
        coordinate_columns = ["thermal_row", "thermal_col"]
    elif {"pixel_y", "pixel_x"}.issubset(tied.columns):
        coordinate_columns = ["pixel_y", "pixel_x"]
    else:
        coordinate_columns = []
    if tied.empty or not coordinate_columns:
        return None
    finite_coordinates = np.logical_and.reduce([
        np.isfinite(pd.to_numeric(tied[column_name], errors="coerce").to_numpy(float))
        for column_name in coordinate_columns
    ])
    tied = tied.loc[finite_coordinates]
    if tied.empty:
        return None
    return tied.sort_values(coordinate_columns, kind="mergesort").iloc[0]


def extreme_summary(
    frame: pd.DataFrame,
    *,
    group_columns: Iterable[str] = (
        "image_id", "measurement_type", "temperature_source", "source_method", "target_name",
        "surface_cover_class", "luhk_label", "analysis_eligible",
    ),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    available_groups = [column for column in group_columns if column in frame.columns]
    rows: list[dict[str, Any]] = []
    coordinates: list[dict[str, Any]] = []
    for keys, group in frame.groupby(available_groups, dropna=False, observed=True, sort=True):
        keys = keys if isinstance(keys, tuple) else (keys,)
        base = dict(zip(available_groups, keys))
        values = pd.to_numeric(group["temperature_c"], errors="coerce")
        finite = np.isfinite(values)
        clean = values.loc[finite]
        eligible = group.get("analysis_eligible", pd.Series(True, index=group.index)).astype(bool) & finite
        coordinate_pair = (
            ("thermal_row", "thermal_col") if {"thermal_row", "thermal_col"}.issubset(group.columns)
            else (("pixel_y", "pixel_x") if {"pixel_y", "pixel_x"}.issubset(group.columns) else None)
        )
        spatial_available = bool(
            coordinate_pair
            and np.logical_and.reduce([
                np.isfinite(pd.to_numeric(group[column], errors="coerce").to_numpy(float))
                for column in coordinate_pair
            ]).any()
        )
        row: dict[str, Any] = {
            **base,
            "finite_pixel_count": int(finite.sum()),
            "eligible_pixel_count": int(eligible.sum()),
            "spatial_location_available": spatial_available,
        }
        if clean.empty:
            row.update({key: np.nan for key in ("min_temperature_c", "max_temperature_c", "q01_temperature_c", "median_temperature_c", "q95_temperature_c", "q99_temperature_c")})
            row.update({"tied_min_count": 0, "tied_max_count": 0, "qa_flags": "no_finite_temperature"})
            rows.append(row)
            continue
        minimum, maximum = float(clean.min()), float(clean.max())
        q99 = float(clean.quantile(0.99))
        tied_min = group.loc[finite & np.isclose(values, minimum, atol=1e-7, rtol=0.0)]
        tied_max = group.loc[finite & np.isclose(values, maximum, atol=1e-7, rtol=0.0)]
        row.update(
            {
                "min_temperature_c": minimum,
                "max_temperature_c": maximum,
                "q01_temperature_c": float(clean.quantile(0.01)),
                "median_temperature_c": float(clean.median()),
                "q95_temperature_c": float(clean.quantile(0.95)),
                "q99_temperature_c": q99,
                "tied_min_count": int(len(tied_min)),
                "tied_max_count": int(len(tied_max)),
                "q99_exceedance_count": int((clean >= q99).sum()),
                "qa_flags": ";".join(
                    flag for condition, flag in ((minimum < -100, "implausible_min_below_-100c"), (maximum > 300, "implausible_max_above_300c")) if condition
                ),
            }
        )
        ambient = pd.to_numeric(group.get("ambient_temperature_c", pd.Series(np.nan, index=group.index)), errors="coerce")
        delta = values - ambient
        finite_delta = delta[np.isfinite(delta)]
        row.update(
            {
                "min_delta_temperature_c": float(finite_delta.min()) if not finite_delta.empty else np.nan,
                "max_delta_temperature_c": float(finite_delta.max()) if not finite_delta.empty else np.nan,
                "q99_delta_temperature_c": float(finite_delta.quantile(0.99)) if not finite_delta.empty else np.nan,
            }
        )
        if row["spatial_location_available"]:
            for kind, selected in (("minimum", tied_min), ("maximum", tied_max), ("q99_exceedance", group.loc[finite & (values >= q99)])):
                for item in selected.itertuples(index=False):
                    payload = item._asdict()
                    coordinate_row = payload.get("thermal_row", payload.get("pixel_y", np.nan))
                    coordinate_col = payload.get("thermal_col", payload.get("pixel_x", np.nan))
                    if not np.isfinite(float(coordinate_row)) or not np.isfinite(float(coordinate_col)):
                        continue
                    coordinates.append(
                        {
                            **base,
                            "location_type": kind,
                            "thermal_row": coordinate_row,
                            "thermal_col": coordinate_col,
                            "temperature_c": payload.get("temperature_c", np.nan),
                            "selection_rule": "row-major first is representative" if kind in {"minimum", "maximum"} else "all finite pixels at or above q99",
                        }
                    )
        for kind, value in (("min", minimum), ("max", maximum)):
            representative = _representative(group.loc[finite], value, "temperature_c")
            row[f"representative_{kind}_row"] = np.nan if representative is None else int(representative.get("thermal_row", representative.get("pixel_y")))
            row[f"representative_{kind}_col"] = np.nan if representative is None else int(representative.get("thermal_col", representative.get("pixel_x")))
        rows.append(row)
    coordinate_columns = [
        *available_groups, "location_type", "thermal_row", "thermal_col",
        "temperature_c", "selection_rule",
    ]
    return pd.DataFrame(rows), pd.DataFrame(coordinates).reindex(columns=coordinate_columns)


def plot_pixel_extremes(
    *,
    matrix: np.ndarray,
    eligible_mask: np.ndarray,
    output_path: Path,
    image_id: str,
    source_annotation: str,
    polygon_coordinates: list[list[float]] | None = None,
) -> dict[str, Any]:
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    values = np.asarray(matrix, dtype=float)
    eligible = np.asarray(eligible_mask, dtype=bool) & np.isfinite(values)
    if values.shape != eligible.shape or not eligible.any():
        raise ValueError("Extreme-temperature plotting requires at least one eligible finite pixel.")
    selected = np.where(eligible, values, np.nan)
    minimum, maximum = float(np.nanmin(selected)), float(np.nanmax(selected))
    q99 = float(np.nanquantile(selected, 0.99))
    min_rows, min_cols = np.where(eligible & np.isclose(values, minimum, atol=1e-7, rtol=0.0))
    max_rows, max_cols = np.where(eligible & np.isclose(values, maximum, atol=1e-7, rtol=0.0))
    min_row, min_col = sorted(zip(min_rows.tolist(), min_cols.tolist()))[0]
    max_row, max_col = sorted(zip(max_rows.tolist(), max_cols.tolist()))[0]
    exceed = eligible & (values >= q99)
    figure, axis = plt.subplots(figsize=(10, 7))
    image = axis.imshow(values, cmap="inferno")
    figure.colorbar(image, ax=axis, label="Temperature (°C)")
    axis.scatter([min_col], [min_row], marker="v", s=90, facecolor="cyan", edgecolor="black", label=f"Min ({min_col}, {min_row}) {minimum:.2f}°C")
    axis.scatter([max_col], [max_row], marker="^", s=90, facecolor="lime", edgecolor="black", label=f"Max ({max_col}, {max_row}) {maximum:.2f}°C")
    axis.contour(exceed.astype(float), levels=[0.5], colors=["white"], linewidths=0.8)
    axis.plot([], [], color="white", label=f"q99 exceedance (q99={q99:.2f}°C)")
    if polygon_coordinates:
        polygon = np.asarray(polygon_coordinates, dtype=float)
        polygon = np.vstack([polygon, polygon[0]])
        axis.plot(polygon[:, 0], polygon[:, 1], color="deepskyblue", linewidth=1.5, label="Accepted target boundary")
    axis.set_title(f"{image_id} extreme-temperature locations\n{source_annotation}")
    axis.set_xlabel("Thermal column / x")
    axis.set_ylabel("Thermal row / y")
    axis.legend(loc="best", fontsize=8)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.tight_layout()
    figure.savefig(output_path, dpi=180)
    figure.savefig(output_path.with_suffix(".pdf"))
    plt.close(figure)
    return {
        "minimum_temperature_c": minimum,
        "maximum_temperature_c": maximum,
        "q99_temperature_c": q99,
        "representative_min": [min_row, min_col],
        "representative_max": [max_row, max_col],
        "tied_min_count": int(len(min_rows)),
        "tied_max_count": int(len(max_rows)),
        "q99_exceedance_count": int(exceed.sum()),
        "q99_location_rule": "q99 is a threshold; every eligible pixel at or above it is contoured",
    }


def write_extreme_outputs(frame: pd.DataFrame, output_directory: Path) -> tuple[Path, Path]:
    summary, coordinates = extreme_summary(frame)
    output_directory.mkdir(parents=True, exist_ok=True)
    summary_path = output_directory / "extreme_temperature_summary.csv"
    coordinates_path = output_directory / "extreme_temperature_coordinates.csv"
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    coordinates.to_csv(coordinates_path, index=False, encoding="utf-8-sig")
    return summary_path, coordinates_path
