#!/usr/bin/env python3
"""Assign dominant LUHK land-use classes to one example image's pilot grid cells."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any


DEFAULT_IMAGE_STEM = "DJI_20260107143259_0005_V"

GRID_CSV_NAME = Path("data") / "processed" / "grids" / "pilot_10m_grid_cells.csv"
VT_PAIRS_CSV_NAME = Path("data") / "metadata" / "vt_pairs.csv"
IMAGE_METADATA_CSV_NAME = Path("data") / "metadata" / "dji_image_metadata.csv"
LUHK_EXTRACT_DIR_NAME = Path("data") / "LUHK2024_extracted"

REQUIRED_PACKAGES = ["pandas", "rasterio", "numpy", "matplotlib", "PIL", "pyproj"]
OPTIONAL_PACKAGES = ["geopandas", "shapely"]

OUTPUT_COLUMNS = [
    "grid_id",
    "pair_id",
    "visible_image_name",
    "thermal_image_name",
    "visible_image_path",
    "thermal_image_path",
    "grid_row",
    "grid_col",
    "cell_min_x_2326",
    "cell_max_x_2326",
    "cell_min_y_2326",
    "cell_max_y_2326",
    "cell_center_x_2326",
    "cell_center_y_2326",
    "cell_center_lat",
    "cell_center_lon",
    "cell_width_m",
    "cell_height_m",
    "cell_area_m2",
    "is_partial_edge_cell",
    "dominant_luhk_code",
    "dominant_luhk_name",
    "dominant_ratio",
    "second_luhk_code",
    "second_luhk_name",
    "second_ratio",
    "landuse_quality_flag",
    "notes",
]

# Recreated from scripts/plot_hong_kong_land_use.py. The labels and grouping
# match the existing hong_kong_land_use_csdi_10_categories figure setup.
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

NOTES = (
    "Dominant LUHK land-use assigned by majority overlap between the pilot "
    "10m grid cell and the LUHK 2024 10m raster. This step does not extract "
    "thermal temperatures, calculate delta-T, or run prediction. Overlay on "
    "the visible image is an approximate first-pass visualization using the "
    "north-up rectangular footprint assumption."
)


def project_root() -> Path:
    """Return the repository root based on this script location."""
    return Path(__file__).resolve().parents[1]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Assign dominant LUHK land-use classes to one example image's "
            "existing pilot 10m grid cells."
        )
    )
    parser.add_argument(
        "--image-stem",
        default=DEFAULT_IMAGE_STEM,
        help=f"Visible image stem to process. Default: {DEFAULT_IMAGE_STEM}",
    )
    return parser.parse_args(argv)


def check_dependencies() -> bool:
    """Check required packages before running the LUHK overlay."""
    missing = [
        package
        for package in REQUIRED_PACKAGES
        if importlib.util.find_spec(package) is None
    ]
    if missing:
        for package in missing:
            install_name = "Pillow" if package == "PIL" else package
            print(
                f"Missing dependency: {package}. Please install it with: pip install {install_name}",
                file=sys.stderr,
            )
        return False

    optional_missing = [
        package
        for package in OPTIONAL_PACKAGES
        if importlib.util.find_spec(package) is None
    ]
    if optional_missing:
        print(
            "Optional GIS dependency not available: "
            + ", ".join(optional_missing)
            + ". GeoJSON will be written directly without GeoPandas/Shapely."
        )
    return True


def output_paths(image_stem: str) -> dict[str, Path]:
    """Return all output paths for an example image stem."""
    safe = safe_stem(image_stem)
    root = project_root()
    return {
        "csv": root / "data" / "processed" / "grids" / f"example_grid_landuse_{safe}.csv",
        "geojson": root / "outputs" / "geodata" / f"example_grid_landuse_{safe}.geojson",
        "map": root / "outputs" / "figures" / f"example_grid_landuse_{safe}_map.png",
        "overlay": root / "outputs" / "figures" / f"example_grid_landuse_{safe}_overlay_on_V.png",
        "summary": root / "outputs" / "reports" / "05_assign_luhk_landuse_example_summary.txt",
    }


def safe_stem(value: str) -> str:
    """Return a filename-safe stem."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(value).stem).strip("_") or "image"


def relative_posix(path: Path) -> str:
    """Return a project-relative POSIX path when possible."""
    root = project_root()
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def normalize_stem(value: Any) -> str:
    """Normalize a file path/name/stem for robust image matching."""
    text = str(value or "").replace("\\", "/").strip()
    stem = Path(text).stem if text else ""
    return stem.casefold()


def resolve_project_path(path_text: str) -> Path:
    """Resolve a path stored in CSV relative to the project root."""
    path = Path(str(path_text).strip())
    if path.is_absolute():
        return path
    return project_root() / path


def find_luhk_resources() -> tuple[Path, Path | None]:
    """Find or extract the LUHK GeoTIFF raster already present in the project."""
    root = project_root()
    likely_tifs = [
        path
        for path in root.rglob("*.tif")
        if ".venv" not in path.parts
        and any(token in path.name.casefold() for token in ("blu", "luhk", "lumhk"))
    ]
    if not likely_tifs:
        likely_tifs = [
            path
            for path in root.rglob("*.tif")
            if ".venv" not in path.parts
        ]
    if likely_tifs:
        return sorted(likely_tifs, key=lambda item: item.as_posix())[0], None

    zip_candidates = [
        path
        for path in (root / "data").rglob("*.zip")
        if any(token in path.name.casefold() for token in ("land", "util", "luhk", "raster"))
    ]
    if not zip_candidates:
        raise FileNotFoundError(
            "Could not find a LUHK GeoTIFF or LUHK raster ZIP under the project data folder."
        )

    zip_path = sorted(zip_candidates, key=lambda item: item.as_posix())[0]
    extract_dir = root / LUHK_EXTRACT_DIR_NAME
    extract_dir.mkdir(parents=True, exist_ok=True)
    print(f"Extracting LUHK raster ZIP: {relative_posix(zip_path)}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)

    extracted_tifs = sorted(extract_dir.rglob("*.tif"), key=lambda item: item.as_posix())
    if not extracted_tifs:
        raise FileNotFoundError(
            f"No .tif file found after extracting LUHK raster ZIP: {zip_path}"
        )
    return extracted_tifs[0], zip_path


def load_grid_cells_for_example(grid_csv: Path, image_stem: str) -> Any:
    """Load and filter Step 3 pilot grid cells to one visible image stem."""
    import pandas as pd

    if not grid_csv.is_file():
        raise FileNotFoundError(f"Grid CSV not found: {grid_csv}")

    df = pd.read_csv(grid_csv)
    target = normalize_stem(image_stem)
    mask = (
        df["visible_image_name"].map(normalize_stem).eq(target)
        | df["visible_image_path"].map(normalize_stem).eq(target)
    )
    if "image_id" in df.columns:
        mask = mask | df["image_id"].map(normalize_stem).eq(target)

    example_df = df.loc[mask].copy()
    if example_df.empty:
        raise ValueError(
            f"No pilot grid cells found for image stem '{image_stem}' in {grid_csv}"
        )
    example_df.sort_values(["grid_row", "grid_col"], inplace=True)
    return example_df


def load_visible_image_path(example_df: Any) -> Path:
    """Resolve the original visible image path from the grid table."""
    path_text = str(example_df.iloc[0]["visible_image_path"])
    visible_path = resolve_project_path(path_text)
    if not visible_path.is_file():
        raise FileNotFoundError(f"Original visible image not found: {visible_path}")
    return visible_path


def load_luhk_raster_and_category_mapping() -> tuple[Path, dict[int, str], dict[int, int]]:
    """Find the LUHK raster and return category labels/mapping."""
    raster_path, zip_path = find_luhk_resources()
    if zip_path:
        print(f"LUHK ZIP used: {relative_posix(zip_path)}")
    print(f"LUHK raster used: {relative_posix(raster_path)}")
    return raster_path, CATEGORY_GROUPS, CODE_TO_GROUP


def parse_float(value: Any) -> float | None:
    """Parse finite floats from table values."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def pixel_bounds(transform: Any, row: int, col: int) -> tuple[float, float, float, float]:
    """Return left, bottom, right, top bounds for a north-up raster pixel."""
    left = transform.c + col * transform.a
    right = left + transform.a
    top = transform.f + row * transform.e
    bottom = top + transform.e
    return min(left, right), min(bottom, top), max(left, right), max(bottom, top)


def overlap_area(
    a_min_x: float,
    a_min_y: float,
    a_max_x: float,
    a_max_y: float,
    b_min_x: float,
    b_min_y: float,
    b_max_x: float,
    b_max_y: float,
) -> float:
    """Return rectangle intersection area."""
    width = max(0.0, min(a_max_x, b_max_x) - max(a_min_x, b_min_x))
    height = max(0.0, min(a_max_y, b_max_y) - max(a_min_y, b_min_y))
    return width * height


def assign_one_cell(
    src: Any,
    row: Any,
    code_to_group: dict[int, int],
    category_groups: dict[int, str],
) -> dict[str, Any]:
    """Assign a dominant LUHK category to one grid cell by area majority."""
    import numpy as np
    from rasterio.windows import Window, from_bounds

    min_x = float(row["cell_min_x_2326"])
    max_x = float(row["cell_max_x_2326"])
    min_y = float(row["cell_min_y_2326"])
    max_y = float(row["cell_max_y_2326"])

    raw_window = from_bounds(min_x, min_y, max_x, max_y, transform=src.transform)
    row_start = max(int(math.floor(raw_window.row_off)), 0)
    col_start = max(int(math.floor(raw_window.col_off)), 0)
    row_stop = min(int(math.ceil(raw_window.row_off + raw_window.height)), src.height)
    col_stop = min(int(math.ceil(raw_window.col_off + raw_window.width)), src.width)

    if row_stop <= row_start or col_stop <= col_start:
        return no_luhk_assignment("no_luhk_overlap")

    window = Window(col_start, row_start, col_stop - col_start, row_stop - row_start)
    data = src.read(1, window=window, masked=True)

    group_areas: dict[int, float] = defaultdict(float)
    raw_code_areas: dict[int, float] = defaultdict(float)
    nodata = src.nodata

    for local_row in range(data.shape[0]):
        for local_col in range(data.shape[1]):
            value = data[local_row, local_col]
            if np.ma.is_masked(value):
                continue
            raw_code = int(value)
            if nodata is not None and raw_code == int(nodata):
                continue
            group_id = code_to_group.get(raw_code)
            if group_id is None:
                continue

            raster_row = row_start + local_row
            raster_col = col_start + local_col
            pix_min_x, pix_min_y, pix_max_x, pix_max_y = pixel_bounds(
                src.transform,
                raster_row,
                raster_col,
            )
            area = overlap_area(
                min_x,
                min_y,
                max_x,
                max_y,
                pix_min_x,
                pix_min_y,
                pix_max_x,
                pix_max_y,
            )
            if area <= 0:
                continue
            group_areas[group_id] += area
            raw_code_areas[raw_code] += area

    total_area = sum(group_areas.values())
    if total_area <= 0:
        return no_luhk_assignment("no_mapped_luhk_class")

    ranked = sorted(group_areas.items(), key=lambda item: (-item[1], item[0]))
    dominant_code, dominant_area = ranked[0]
    second_code = ranked[1][0] if len(ranked) > 1 else None
    second_area = ranked[1][1] if len(ranked) > 1 else 0.0
    dominant_ratio = dominant_area / total_area
    second_ratio = second_area / total_area if total_area else None

    return {
        "dominant_luhk_code": dominant_code,
        "dominant_luhk_name": category_groups[dominant_code],
        "dominant_ratio": dominant_ratio,
        "second_luhk_code": second_code,
        "second_luhk_name": category_groups.get(second_code, "") if second_code is not None else "",
        "second_ratio": second_ratio,
        "landuse_quality_flag": classify_landuse_quality(dominant_ratio),
        "luhk_overlap_area_m2": total_area,
        "luhk_raw_code_area_json": json.dumps(
            {str(code): area for code, area in sorted(raw_code_areas.items())},
            ensure_ascii=False,
        ),
    }


def no_luhk_assignment(flag: str) -> dict[str, Any]:
    """Return an empty LUHK assignment for cells without raster/category overlap."""
    return {
        "dominant_luhk_code": "",
        "dominant_luhk_name": "",
        "dominant_ratio": "",
        "second_luhk_code": "",
        "second_luhk_name": "",
        "second_ratio": "",
        "landuse_quality_flag": flag,
        "luhk_overlap_area_m2": 0.0,
        "luhk_raw_code_area_json": "{}",
    }


def assign_luhk_to_grid_cells(
    example_df: Any,
    raster_path: Path,
    category_groups: dict[int, str],
    code_to_group: dict[int, int],
) -> Any:
    """Assign dominant LUHK land-use classes to the example grid cells."""
    import pandas as pd
    import rasterio

    assignments: list[dict[str, Any]] = []
    with rasterio.open(raster_path) as src:
        raster_crs_text = str(src.crs) if src.crs else ""
        raster_epsg = src.crs.to_epsg() if src.crs else None
        if raster_epsg != 2326 and "EPSG\",\"2326" not in raster_crs_text:
            print(
                f"Warning: LUHK raster CRS is {src.crs}; expected EPSG:2326 for this workflow."
            )
        for _, row in example_df.iterrows():
            assignments.append(assign_one_cell(src, row, code_to_group, category_groups))

    assignment_df = pd.DataFrame(assignments)
    result = pd.concat([example_df.reset_index(drop=True), assignment_df], axis=1)
    result["notes"] = NOTES
    return result


def classify_landuse_quality(dominant_ratio: float | None) -> str:
    """Classify confidence from dominant LUHK ratio."""
    if dominant_ratio is None:
        return "no_luhk_overlap"
    if dominant_ratio >= 0.8:
        return "high_confidence"
    if dominant_ratio >= 0.6:
        return "medium_confidence"
    return "mixed_cell"


def write_example_csv(result_df: Any, output_csv: Path) -> None:
    """Write the example LUHK grid assignment CSV."""
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df = result_df.copy()
    for column in OUTPUT_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    extra_columns = [
        column
        for column in ("luhk_overlap_area_m2", "luhk_raw_code_area_json")
        if column in df.columns
    ]
    df = df[OUTPUT_COLUMNS + extra_columns]
    df.to_csv(output_csv, index=False, encoding="utf-8-sig")


def json_ready_value(value: Any) -> Any:
    """Convert values to JSON-safe scalars."""
    if value is None:
        return None
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return value
    if hasattr(value, "item"):
        return json_ready_value(value.item())
    if isinstance(value, (str, int, bool)):
        return value
    return str(value)


def cell_polygon_2326(row: Any) -> list[tuple[float, float]]:
    """Return one grid cell polygon ring in EPSG:2326."""
    return [
        (float(row["cell_min_x_2326"]), float(row["cell_max_y_2326"])),
        (float(row["cell_max_x_2326"]), float(row["cell_max_y_2326"])),
        (float(row["cell_max_x_2326"]), float(row["cell_min_y_2326"])),
        (float(row["cell_min_x_2326"]), float(row["cell_min_y_2326"])),
        (float(row["cell_min_x_2326"]), float(row["cell_max_y_2326"])),
    ]


def cell_polygon_lon_lat(row: Any, transformer_to_4326: Any) -> list[list[float]]:
    """Return one grid cell polygon ring in GeoJSON lon/lat order."""
    return [
        list(transformer_to_4326.transform(x, y))
        for x, y in cell_polygon_2326(row)
    ]


def write_example_geojson(result_df: Any, output_geojson: Path) -> None:
    """Write LUHK-assigned grid cells as EPSG:4326 GeoJSON."""
    from pyproj import Transformer

    transformer_to_4326 = Transformer.from_crs("EPSG:2326", "EPSG:4326", always_xy=True)
    output_geojson.parent.mkdir(parents=True, exist_ok=True)

    features = []
    property_columns = OUTPUT_COLUMNS + [
        "luhk_overlap_area_m2",
        "luhk_raw_code_area_json",
    ]
    for _, row in result_df.iterrows():
        properties = {
            column: json_ready_value(row[column])
            for column in property_columns
            if column in result_df.columns
        }
        features.append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [cell_polygon_lon_lat(row, transformer_to_4326)],
                },
            }
        )

    geojson = {
        "type": "FeatureCollection",
        "name": safe_stem(output_geojson.stem),
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
        },
        "features": features,
    }
    output_geojson.write_text(
        json.dumps(geojson, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def category_colors() -> dict[int, Any]:
    """Return the same tab20-derived colors used by the existing LUHK plot."""
    import matplotlib.pyplot as plt

    group_ids = sorted(CATEGORY_GROUPS.keys())
    base_cmap = plt.colormaps["tab20"].resampled(len(group_ids))
    return {group_id: base_cmap(i) for i, group_id in enumerate(group_ids)}


def used_category_handles(result_df: Any, colors: dict[int, Any]) -> list[Any]:
    """Build legend handles for categories present in the result."""
    import matplotlib.patches as mpatches

    codes = sorted(
        {
            int(code)
            for code in result_df["dominant_luhk_code"].tolist()
            if str(code).strip() != ""
        }
    )
    return [
        mpatches.Patch(color=colors[code], label=CATEGORY_GROUPS[code])
        for code in codes
    ]


def plot_grid_landuse_map(result_df: Any, output_map: Path, image_stem: str) -> None:
    """Plot LUHK-assigned grid cells in EPSG:2326 map coordinates."""
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    output_map.parent.mkdir(parents=True, exist_ok=True)
    colors = category_colors()

    fig, ax = plt.subplots(figsize=(10, 8))
    for _, row in result_df.iterrows():
        code_text = str(row["dominant_luhk_code"]).strip()
        facecolor = colors.get(int(code_text), "#f2f2f2") if code_text else "#f2f2f2"
        rect = mpatches.Rectangle(
            (float(row["cell_min_x_2326"]), float(row["cell_min_y_2326"])),
            float(row["cell_width_m"]),
            float(row["cell_height_m"]),
            facecolor=facecolor,
            edgecolor="#333333",
            linewidth=0.25,
            alpha=0.9,
        )
        ax.add_patch(rect)

    min_x = float(result_df["cell_min_x_2326"].min())
    max_x = float(result_df["cell_max_x_2326"].max())
    min_y = float(result_df["cell_min_y_2326"].min())
    max_y = float(result_df["cell_max_y_2326"].max())
    margin_x = max((max_x - min_x) * 0.04, 1.0)
    margin_y = max((max_y - min_y) * 0.04, 1.0)
    ax.set_xlim(min_x - margin_x, max_x + margin_x)
    ax.set_ylim(min_y - margin_y, max_y + margin_y)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(f"LUHK Dominant Land-use Grid\n{image_stem}")
    ax.set_xlabel("Easting (Hong Kong 1980 Grid, EPSG:2326)")
    ax.set_ylabel("Northing (Hong Kong 1980 Grid, EPSG:2326)")
    ax.grid(True, linewidth=0.25, alpha=0.35)
    handles = used_category_handles(result_df, colors)
    if handles:
        ax.legend(
            handles=handles,
            title="CSDI land-use category",
            loc="center left",
            bbox_to_anchor=(1.02, 0.5),
            borderaxespad=0,
            fontsize=8,
        )

    fig.tight_layout()
    fig.savefig(output_map, dpi=220, bbox_inches="tight")
    plt.close(fig)


def map_x_to_pixel(x: float, min_x: float, max_x: float, image_width: int) -> float:
    """Project EPSG:2326 x into visible-image pixel x."""
    return (x - min_x) / (max_x - min_x) * image_width


def map_y_to_pixel(y: float, min_y: float, max_y: float, image_height: int) -> float:
    """Project EPSG:2326 y into visible-image pixel y with north-up top edge."""
    return (max_y - y) / (max_y - min_y) * image_height


def plot_overlay_on_visible_image(
    result_df: Any,
    visible_image_path: Path,
    output_overlay: Path,
    image_stem: str,
) -> None:
    """Plot approximate LUHK grid overlay on the original visible image."""
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from PIL import Image, ImageOps

    output_overlay.parent.mkdir(parents=True, exist_ok=True)
    image = ImageOps.exif_transpose(Image.open(visible_image_path))
    image_width, image_height = image.size
    colors = category_colors()

    min_x = float(result_df["cell_min_x_2326"].min())
    max_x = float(result_df["cell_max_x_2326"].max())
    min_y = float(result_df["cell_min_y_2326"].min())
    max_y = float(result_df["cell_max_y_2326"].max())

    fig, ax = plt.subplots(figsize=(12, 9))
    ax.imshow(image)

    for _, row in result_df.iterrows():
        code_text = str(row["dominant_luhk_code"]).strip()
        facecolor = colors.get(int(code_text), "#f2f2f2") if code_text else "#f2f2f2"
        px_min = map_x_to_pixel(float(row["cell_min_x_2326"]), min_x, max_x, image_width)
        px_max = map_x_to_pixel(float(row["cell_max_x_2326"]), min_x, max_x, image_width)
        py_min = map_y_to_pixel(float(row["cell_max_y_2326"]), min_y, max_y, image_height)
        py_max = map_y_to_pixel(float(row["cell_min_y_2326"]), min_y, max_y, image_height)
        rect = mpatches.Rectangle(
            (px_min, py_min),
            px_max - px_min,
            py_max - py_min,
            facecolor=facecolor,
            edgecolor="#111111",
            linewidth=0.18,
            alpha=0.32,
        )
        ax.add_patch(rect)

    ax.set_title(
        f"Approximate LUHK Grid Overlay on Visible Image\n{image_stem}",
        fontsize=12,
    )
    ax.set_xlim(0, image_width)
    ax.set_ylim(image_height, 0)
    ax.set_axis_off()
    handles = used_category_handles(result_df, colors)
    if handles:
        ax.legend(
            handles=handles,
            title="CSDI land-use category",
            loc="center left",
            bbox_to_anchor=(1.02, 0.5),
            borderaxespad=0,
            fontsize=8,
        )

    fig.tight_layout()
    fig.savefig(output_overlay, dpi=220, bbox_inches="tight")
    plt.close(fig)


def numeric_summary(values: list[float]) -> str:
    """Return min / median / max summary text."""
    clean = [value for value in values if value is not None and math.isfinite(value)]
    if not clean:
        return "n/a"
    return f"min={min(clean):.4f}, median={median(clean):.4f}, max={max(clean):.4f}"


def write_summary(
    summary_path: Path,
    image_stem: str,
    result_df: Any,
    output_csv: Path,
    output_geojson: Path,
    output_map: Path,
    output_overlay: Path,
    raster_path: Path,
) -> None:
    """Write a plain-text summary report."""
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    partial_values = result_df["is_partial_edge_cell"].astype(str).str.casefold()
    partial_count = int(partial_values.isin(["true", "1", "yes"]).sum())
    full_count = int(len(result_df) - partial_count)
    ratios = [
        float(value)
        for value in result_df["dominant_ratio"].tolist()
        if str(value).strip() != ""
    ]
    unique_names = sorted(
        {
            str(name)
            for name in result_df["dominant_luhk_name"].tolist()
            if str(name).strip()
        }
    )
    quality_counts = result_df["landuse_quality_flag"].value_counts().to_dict()

    lines = [
        "LUHK land-use assignment example summary",
        "",
        f"example image processed: {image_stem}",
        f"LUHK raster used: {relative_posix(raster_path)}",
        f"number of grid cells in example image: {len(result_df)}",
        f"number of full cells: {full_count}",
        f"number of partial edge cells: {partial_count}",
        "",
        f"number of unique dominant land-use classes assigned: {len(unique_names)}",
        "list of unique dominant land-use names:",
        *[f"- {name}" for name in unique_names],
        "",
        f"min / median / max dominant_ratio: {numeric_summary(ratios)}",
        "",
        f"number of high_confidence cells: {quality_counts.get('high_confidence', 0)}",
        f"number of medium_confidence cells: {quality_counts.get('medium_confidence', 0)}",
        f"number of mixed_cell cells: {quality_counts.get('mixed_cell', 0)}",
        f"number of no_luhk_overlap cells: {quality_counts.get('no_luhk_overlap', 0)}",
        f"number of no_mapped_luhk_class cells: {quality_counts.get('no_mapped_luhk_class', 0)}",
        "",
        f"path to CSV: {relative_posix(output_csv)}",
        f"path to GeoJSON: {relative_posix(output_geojson)}",
        f"path to map figure: {relative_posix(output_map)}",
        f"path to overlay figure: {relative_posix(output_overlay)}",
    ]
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not check_dependencies():
        return 1

    root = project_root()
    paths = output_paths(args.image_stem)
    grid_csv = root / GRID_CSV_NAME
    vt_pairs_csv = root / VT_PAIRS_CSV_NAME
    image_metadata_csv = root / IMAGE_METADATA_CSV_NAME

    # These two metadata files are loaded only to confirm the expected project
    # context exists for this workflow step.
    for input_path in (vt_pairs_csv, image_metadata_csv):
        if not input_path.is_file():
            print(f"Error: required input file not found: {input_path}", file=sys.stderr)
            return 1

    try:
        example_df = load_grid_cells_for_example(grid_csv, args.image_stem)
        visible_image_path = load_visible_image_path(example_df)
        raster_path, category_groups, code_to_group = load_luhk_raster_and_category_mapping()
        result_df = assign_luhk_to_grid_cells(
            example_df,
            raster_path,
            category_groups,
            code_to_group,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    write_example_csv(result_df, paths["csv"])
    write_example_geojson(result_df, paths["geojson"])
    plot_grid_landuse_map(result_df, paths["map"], args.image_stem)
    plot_overlay_on_visible_image(
        result_df,
        visible_image_path,
        paths["overlay"],
        args.image_stem,
    )
    write_summary(
        paths["summary"],
        args.image_stem,
        result_df,
        paths["csv"],
        paths["geojson"],
        paths["map"],
        paths["overlay"],
        raster_path,
    )

    print(f"Example image processed: {args.image_stem}")
    print(f"Grid cells assigned: {len(result_df)}")
    print(f"Output CSV: {relative_posix(paths['csv'])}")
    print(f"Output GeoJSON: {relative_posix(paths['geojson'])}")
    print(f"Map figure: {relative_posix(paths['map'])}")
    print(f"Overlay figure: {relative_posix(paths['overlay'])}")
    print(f"Summary: {relative_posix(paths['summary'])}")
    print()
    print("Next suggested command:")
    print(
        r'python scripts\05_assign_luhk_landuse_example.py '
        r'--image-stem "DJI_20260107143259_0005_V"'
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
