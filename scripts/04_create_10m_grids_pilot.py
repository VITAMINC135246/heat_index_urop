#!/usr/bin/env python3
"""Create LUHK-aligned 10m grid cells for selected pilot V/T pairs."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
import warnings
import zipfile
from pathlib import Path
from statistics import median
from typing import Any

from table_io import read_table, write_table


IMAGE_FOOTPRINTS_XLSX_NAME = Path("data") / "processed" / "footprints" / "image_footprints.xlsx"
LUHK_EXTRACT_DIR_NAME = Path("data") / "LUHK2024_extracted"
OUTPUT_GRID_XLSX_NAME = Path("data") / "processed" / "grids" / "pilot_luhk_aligned_10m_grid_cells.xlsx"
OUTPUT_GEOJSON_NAME = Path("outputs") / "geodata" / "pilot_luhk_aligned_10m_grid_cells.geojson"
OUTPUT_FIGURE_DIR_NAME = Path("outputs") / "figures" / "pilot_grid_overlays"
SUMMARY_TXT_NAME = Path("outputs") / "reports" / "04_create_10m_grids_pilot_summary.txt"

# Compatibility path used by older follow-up scripts.
COMPAT_GRID_XLSX_NAME = Path("data") / "processed" / "grids" / "pilot_10m_grid_cells.xlsx"
COMPAT_GEOJSON_NAME = Path("outputs") / "geodata" / "pilot_10m_grid_cells.geojson"

REQUIRED_PACKAGES = ["pandas", "rasterio", "numpy", "matplotlib", "pyproj"]
GRID_SIZE_M = 10.0

CATEGORY_GROUPS = {
    0: "Residential",
    1: "Commercial",
    2: "Industrial",
    3: "GIC / open space",
    4: "Transport",
    5: "Other urban / built-up land",
    6: "Agriculture",
    7: "Woodland / shrubland / grassland / wetland",
    8: "Barren land",
    9: "Water bodies",
}

CODE_TO_GROUP = {
    1: 0,
    2: 0,
    3: 0,
    11: 1,
    21: 2,
    22: 2,
    23: 2,
    31: 3,
    32: 3,
    41: 4,
    42: 4,
    43: 4,
    44: 4,
    51: 5,
    52: 5,
    53: 5,
    54: 5,
    61: 6,
    62: 6,
    71: 7,
    72: 7,
    73: 7,
    74: 7,
    81: 8,
    83: 8,
    91: 9,
    92: 9,
}

GRID_COLUMNS = [
    "pair_id",
    "global_cell_id",
    "luhk_row",
    "luhk_col",
    "cell_min_x_2326",
    "cell_max_x_2326",
    "cell_min_y_2326",
    "cell_max_y_2326",
    "cell_area_m2",
    "cell_center_x_2326",
    "cell_center_y_2326",
    "cell_center_lat",
    "cell_center_lon",
    "luhk_raw_code",
    "luhk_category_code",
    "luhk_category_name",
    "dominant_luhk_category",
    "visible_image_name",
    "thermal_image_name",
    "visible_image_path",
    "thermal_image_path",
    "visible_coverage_ratio",
    "thermal_coverage_ratio",
    "is_visible_covered",
    "is_thermal_covered",
    "is_common_vt_cell",
    "visible_footprint_width_m",
    "visible_footprint_height_m",
    "thermal_footprint_width_m",
    "thermal_footprint_height_m",
]


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def relative_posix(path: Path) -> str:
    try:
        return path.relative_to(project_root()).as_posix()
    except ValueError:
        return path.as_posix()


def check_dependencies() -> bool:
    missing = [package for package in REQUIRED_PACKAGES if importlib.util.find_spec(package) is None]
    if not missing:
        return True
    print("Missing required Python packages: " + ", ".join(missing), file=sys.stderr)
    return False


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create LUHK-raster-aligned 10m grid cells for five pilot V/T pairs."
    )
    parser.add_argument("--source-folder", help="Optional raw folder filter for pilot pair selection.")
    parser.add_argument("--max-pairs", type=int, default=5, help="Number of valid V/T pilot pairs to select.")
    parser.add_argument("--pair-ids", help="Optional comma-separated explicit pair_id list.")
    return parser.parse_args(argv)


def find_luhk_raster() -> Path:
    root = project_root()
    extract_dir = root / LUHK_EXTRACT_DIR_NAME
    candidates = sorted(extract_dir.rglob("*.tif")) if extract_dir.is_dir() else []
    for path in candidates:
        if any(token in path.name.casefold() for token in ("blu", "luhk", "lumhk")):
            return path
    zip_candidates = sorted((root / "data").glob("*LUHK*GEOTIFF*.zip"))
    if not zip_candidates:
        raise FileNotFoundError("Could not find LUHK raster or LUHK GeoTIFF ZIP.")
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_candidates[0], "r") as zf:
        zf.extractall(extract_dir)
    candidates = sorted(extract_dir.rglob("*.tif"))
    if not candidates:
        raise FileNotFoundError("No .tif file found after extracting LUHK ZIP.")
    return candidates[0]


def rect(row: Any) -> tuple[float, float, float, float]:
    return (
        float(row["min_x_2326"]),
        float(row["max_x_2326"]),
        float(row["min_y_2326"]),
        float(row["max_y_2326"]),
    )


def overlap_area(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    min_x = max(a[0], b[0])
    max_x = min(a[1], b[1])
    min_y = max(a[2], b[2])
    max_y = min(a[3], b[3])
    if max_x <= min_x or max_y <= min_y:
        return 0.0
    return (max_x - min_x) * (max_y - min_y)


def select_pilot_pairs(footprints_df: Any, args: argparse.Namespace) -> list[str]:
    ok = footprints_df.loc[footprints_df["status"].astype(str).str.casefold().eq("ok")].copy()
    if args.source_folder:
        folder = args.source_folder.replace("\\", "/").casefold()
        ok = ok.loc[
            ok["image_path"].astype(str).str.replace("\\", "/", regex=False).str.casefold().str.contains(folder)
            | ok["paired_image_path"].astype(str).str.replace("\\", "/", regex=False).str.casefold().str.contains(folder)
        ]
    if args.pair_ids:
        requested = [item.strip() for item in args.pair_ids.split(",") if item.strip()]
        return requested

    selected: list[str] = []
    for pair_id, group in ok.groupby("pair_id", sort=True):
        types = {str(value).casefold() for value in group["image_type"].tolist()}
        if {"visible", "thermal"}.issubset(types):
            selected.append(str(pair_id))
        if len(selected) >= args.max_pairs:
            break
    return selected


def cell_bounds_from_transform(transform: Any, row: int, col: int) -> tuple[float, float, float, float]:
    left = transform.c + col * transform.a
    right = left + transform.a
    top = transform.f + row * transform.e
    bottom = top + transform.e
    return min(left, right), max(left, right), min(bottom, top), max(bottom, top)


def row_col_range(src: Any, bounds: tuple[float, float, float, float]) -> tuple[range, range]:
    min_x, max_x, min_y, max_y = bounds
    row_top, col_left = src.index(min_x, max_y)
    row_bottom, col_right = src.index(max_x, min_y)
    row_start = max(0, min(row_top, row_bottom) - 1)
    row_stop = min(src.height, max(row_top, row_bottom) + 2)
    col_start = max(0, min(col_left, col_right) - 1)
    col_stop = min(src.width, max(col_left, col_right) + 2)
    return range(row_start, row_stop), range(col_start, col_stop)


def polygon_lon_lat(row: dict[str, Any], transformer_to_4326: Any) -> list[list[float]]:
    points = [
        (row["cell_min_x_2326"], row["cell_max_y_2326"]),
        (row["cell_max_x_2326"], row["cell_max_y_2326"]),
        (row["cell_max_x_2326"], row["cell_min_y_2326"]),
        (row["cell_min_x_2326"], row["cell_min_y_2326"]),
        (row["cell_min_x_2326"], row["cell_max_y_2326"]),
    ]
    return [list(transformer_to_4326.transform(x, y)) for x, y in points]


def build_pair_grid_rows(pair_id: str, visible: Any, thermal: Any, src: Any, data: Any, transformer_to_4326: Any) -> list[dict[str, Any]]:
    visible_rect = rect(visible)
    thermal_rect = rect(thermal)
    union = (
        min(visible_rect[0], thermal_rect[0]),
        max(visible_rect[1], thermal_rect[1]),
        min(visible_rect[2], thermal_rect[2]),
        max(visible_rect[3], thermal_rect[3]),
    )
    rows_range, cols_range = row_col_range(src, union)
    grid_rows: list[dict[str, Any]] = []
    for raster_row in rows_range:
        for raster_col in cols_range:
            cell_rect = cell_bounds_from_transform(src.transform, raster_row, raster_col)
            cell_area = (cell_rect[1] - cell_rect[0]) * (cell_rect[3] - cell_rect[2])
            if cell_area <= 0:
                continue
            visible_ratio = overlap_area(cell_rect, visible_rect) / cell_area
            thermal_ratio = overlap_area(cell_rect, thermal_rect) / cell_area
            is_visible = visible_ratio > 0
            is_thermal = thermal_ratio > 0
            if not is_visible and not is_thermal:
                continue
            raw_code = int(data[raster_row, raster_col])
            category_code = CODE_TO_GROUP.get(raw_code, "")
            category_name = CATEGORY_GROUPS.get(category_code, "") if category_code != "" else ""
            center_x = (cell_rect[0] + cell_rect[1]) / 2.0
            center_y = (cell_rect[2] + cell_rect[3]) / 2.0
            center_lon, center_lat = transformer_to_4326.transform(center_x, center_y)
            grid_rows.append(
                {
                    "pair_id": pair_id,
                    "global_cell_id": f"LUHK_r{raster_row:05d}_c{raster_col:05d}",
                    "luhk_row": raster_row,
                    "luhk_col": raster_col,
                    "cell_min_x_2326": cell_rect[0],
                    "cell_max_x_2326": cell_rect[1],
                    "cell_min_y_2326": cell_rect[2],
                    "cell_max_y_2326": cell_rect[3],
                    "cell_area_m2": cell_area,
                    "cell_center_x_2326": center_x,
                    "cell_center_y_2326": center_y,
                    "cell_center_lat": center_lat,
                    "cell_center_lon": center_lon,
                    "luhk_raw_code": raw_code,
                    "luhk_category_code": category_code,
                    "luhk_category_name": category_name,
                    "dominant_luhk_category": category_name,
                    "visible_image_name": visible["image_name"],
                    "thermal_image_name": thermal["image_name"],
                    "visible_image_path": visible["image_path"],
                    "thermal_image_path": thermal["image_path"],
                    "visible_coverage_ratio": visible_ratio,
                    "thermal_coverage_ratio": thermal_ratio,
                    "is_visible_covered": is_visible,
                    "is_thermal_covered": is_thermal,
                    "is_common_vt_cell": is_visible and is_thermal,
                    "visible_footprint_width_m": visible["ground_width_m"],
                    "visible_footprint_height_m": visible["ground_height_m"],
                    "thermal_footprint_width_m": thermal["ground_width_m"],
                    "thermal_footprint_height_m": thermal["ground_height_m"],
                }
            )
    return grid_rows


def write_xlsx(rows: list[dict[str, Any]], output_xlsx: Path) -> None:
    import pandas as pd

    output_xlsx.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    for column in GRID_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    write_table(output_xlsx, df, GRID_COLUMNS)


def json_ready(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    try:
        if value != value:
            return None
    except (TypeError, ValueError):
        pass
    return value


def write_geojson(rows: list[dict[str, Any]], output_geojson: Path, transformer_to_4326: Any) -> None:
    output_geojson.parent.mkdir(parents=True, exist_ok=True)
    features = []
    for row in rows:
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [polygon_lon_lat(row, transformer_to_4326)]},
                "properties": {key: json_ready(value) for key, value in row.items() if key in GRID_COLUMNS},
            }
        )
    output_geojson.write_text(json.dumps({"type": "FeatureCollection", "features": features}, indent=2), encoding="utf-8")


def write_preview(rows: list[dict[str, Any]], output_path: Path) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 7))
    if not rows:
        ax.text(0.5, 0.5, "No pilot cells", ha="center", va="center")
        ax.set_axis_off()
    else:
        for row in rows:
            color = "#2ca02c" if row["is_common_vt_cell"] else ("#1f77b4" if row["is_visible_covered"] else "#d62728")
            ax.add_patch(
                Rectangle(
                    (row["cell_min_x_2326"], row["cell_min_y_2326"]),
                    row["cell_max_x_2326"] - row["cell_min_x_2326"],
                    row["cell_max_y_2326"] - row["cell_min_y_2326"],
                    facecolor=color,
                    edgecolor="black",
                    linewidth=0.2,
                    alpha=0.25,
                )
            )
        ax.autoscale()
        ax.set_aspect("equal")
        ax.grid(True, linewidth=0.25, alpha=0.35)
        ax.set_title("LUHK-Aligned Pilot Cells\nblue=visible only, red=thermal only, green=common")
        ax.set_xlabel("Easting (EPSG:2326)")
        ax.set_ylabel("Northing (EPSG:2326)")
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def summary_number(values: list[int]) -> str:
    if not values:
        return "n/a"
    return f"min={min(values)}, median={median(values)}, max={max(values)}"


def write_summary(selected_pair_ids: list[str], rows: list[dict[str, Any]], raster_path: Path, output_xlsx: Path, output_geojson: Path, preview: Path) -> None:
    SUMMARY_TXT_NAME.parent
    counts = []
    lines = [
        "Pilot LUHK-aligned 10m grid construction summary",
        "",
        f"selected V/T pilot pairs: {len(selected_pair_ids)}",
        f"selected pair_ids: {', '.join(selected_pair_ids)}",
        f"LUHK raster used: {relative_posix(raster_path)}",
        f"total LUHK grid rows written: {len(rows)}",
        f"visible-covered rows: {sum(row['is_visible_covered'] for row in rows)}",
        f"thermal-covered rows: {sum(row['is_thermal_covered'] for row in rows)}",
        f"common V/T rows: {sum(row['is_common_vt_cell'] for row in rows)}",
        "",
        "grid rule: cells are official LUHK raster cells identified by luhk_row/luhk_col/global_cell_id",
        "geometry rule: visible coverage uses visible footprint; thermal coverage uses thermal footprint",
        "",
        "per-pair summary:",
    ]
    for pair_id in selected_pair_ids:
        pair_rows = [row for row in rows if row["pair_id"] == pair_id]
        counts.append(len(pair_rows))
        lines.append(
            f"- {pair_id}: total={len(pair_rows)}, "
            f"visible={sum(row['is_visible_covered'] for row in pair_rows)}, "
            f"thermal={sum(row['is_thermal_covered'] for row in pair_rows)}, "
            f"common={sum(row['is_common_vt_cell'] for row in pair_rows)}"
        )
    lines.extend(
        [
            "",
            f"min / median / max cells per pair: {summary_number(counts)}",
            f"output XLSX path: {relative_posix(output_xlsx)}",
            f"output GeoJSON path: {relative_posix(output_geojson)}",
            f"preview figure path: {relative_posix(preview)}",
        ]
    )
    summary_path = project_root() / SUMMARY_TXT_NAME
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not check_dependencies():
        return 1
    import pandas as pd
    import rasterio
    from pyproj import Transformer

    root = project_root()
    footprints_xlsx = root / IMAGE_FOOTPRINTS_XLSX_NAME
    if not footprints_xlsx.is_file():
        print(f"Error: footprint XLSX not found: {relative_posix(footprints_xlsx)}", file=sys.stderr)
        print("Run scripts/03_estimate_image_footprints.py first.", file=sys.stderr)
        return 1
    footprints_df = read_table(footprints_xlsx)
    selected_pair_ids = select_pilot_pairs(footprints_df, args)
    if not selected_pair_ids:
        print("Error: no valid pilot V/T pairs selected.", file=sys.stderr)
        return 1

    raster_path = find_luhk_raster()
    transformer_to_4326 = Transformer.from_crs("EPSG:2326", "EPSG:4326", always_xy=True)
    all_rows: list[dict[str, Any]] = []
    with rasterio.open(raster_path) as src:
        crs_text = str(src.crs) if src.crs else ""
        if src.crs and src.crs.to_epsg() != 2326 and 'AUTHORITY["EPSG","2326"]' not in crs_text:
            print(f"Warning: LUHK raster CRS is {src.crs}; expected EPSG:2326.")
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            data = src.read(1)
        for pair_id in selected_pair_ids:
            group = footprints_df.loc[
                footprints_df["pair_id"].astype(str).eq(str(pair_id))
                & footprints_df["status"].astype(str).str.casefold().eq("ok")
            ]
            visible_rows = group.loc[group["image_type"].astype(str).str.casefold().eq("visible")]
            thermal_rows = group.loc[group["image_type"].astype(str).str.casefold().eq("thermal")]
            if visible_rows.empty or thermal_rows.empty:
                print(f"Warning: skipping pair without both valid footprints: {pair_id}")
                continue
            all_rows.extend(
                build_pair_grid_rows(
                    str(pair_id),
                    visible_rows.iloc[0],
                    thermal_rows.iloc[0],
                    src,
                    data,
                    transformer_to_4326,
                )
            )

    output_xlsx = root / OUTPUT_GRID_XLSX_NAME
    output_geojson = root / OUTPUT_GEOJSON_NAME
    preview = root / OUTPUT_FIGURE_DIR_NAME / "pilot_luhk_aligned_grid_preview.png"
    write_xlsx(all_rows, output_xlsx)
    write_geojson(all_rows, output_geojson, transformer_to_4326)
    write_xlsx(all_rows, root / COMPAT_GRID_XLSX_NAME)
    write_geojson(all_rows, root / COMPAT_GEOJSON_NAME, transformer_to_4326)
    write_preview(all_rows, preview)
    write_summary(selected_pair_ids, all_rows, raster_path, output_xlsx, output_geojson, preview)

    print(f"Selected V/T pairs: {len(selected_pair_ids)}")
    print(f"LUHK-aligned cells written: {len(all_rows)}")
    print(f"Output XLSX path: {relative_posix(output_xlsx)}")
    print(f"Output GeoJSON path: {relative_posix(output_geojson)}")
    print(f"Summary text path: {relative_posix(root / SUMMARY_TXT_NAME)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
