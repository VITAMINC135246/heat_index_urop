#!/usr/bin/env python3
"""Create pilot 10m x 10m grid cells inside thermal image footprints."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any


GRID_SIZE_M = 10.0

VT_PAIRS_CSV_NAME = Path("data") / "metadata" / "vt_pairs.csv"
IMAGE_METADATA_CSV_NAME = Path("data") / "metadata" / "dji_image_metadata.csv"
THERMAL_FOOTPRINTS_CSV_NAME = (
    Path("data") / "processed" / "footprints" / "thermal_image_footprints.csv"
)

OUTPUT_GRID_CSV_NAME = (
    Path("data") / "processed" / "grids" / "pilot_10m_grid_cells.csv"
)
OUTPUT_GEOJSON_NAME = Path("outputs") / "geodata" / "pilot_10m_grid_cells.geojson"
OUTPUT_FIGURE_DIR_NAME = Path("outputs") / "figures" / "pilot_grid_overlays"
SUMMARY_TXT_NAME = (
    Path("outputs") / "reports" / "04_create_10m_grids_pilot_summary.txt"
)

REQUIRED_PACKAGES = ["pandas", "pyproj", "matplotlib"]
OPTIONAL_PACKAGES = ["geopandas", "shapely"]

GRID_COLUMNS = [
    "grid_id",
    "image_id",
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
    "cell_width_m",
    "cell_height_m",
    "cell_area_m2",
    "cell_center_x_2326",
    "cell_center_y_2326",
    "cell_center_lat",
    "cell_center_lon",
    "is_partial_edge_cell",
    "footprint_min_x_2326",
    "footprint_max_x_2326",
    "footprint_min_y_2326",
    "footprint_max_y_2326",
    "footprint_ground_width_m",
    "footprint_ground_height_m",
    "footprint_gsd_x_m_per_px",
    "footprint_gsd_y_m_per_px",
    "quality_flag",
    "notes",
]

NOTES = (
    "Pilot 10m x 10m grid cell created inside the paired thermal image "
    "footprint. LUHK land-use assignment, thermal matrix extraction, delta-T, "
    "and prediction are intentionally deferred to later workflow steps."
)


def project_root() -> Path:
    """Return the repository root based on this script location."""
    return Path(__file__).resolve().parents[1]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Create pilot 10m x 10m grid cells from paired thermal footprints. "
            "A source folder is required so the script never scans all raw data by default."
        )
    )
    parser.add_argument(
        "--source-folder",
        help="Folder to recursively search for pilot *_V.JPG / *_V.JPEG images.",
    )
    parser.add_argument(
        "--max-images",
        type=int,
        default=10,
        help="Maximum number of visible images to select after filtering. Default: 10.",
    )
    args = parser.parse_args(argv)

    if not args.source_folder:
        parser.print_usage(sys.stderr)
        print(
            "Error: --source-folder is required. This pilot script will not "
            "process the whole raw dataset by default.",
            file=sys.stderr,
        )
        print(
            r'Example: python scripts\04_create_10m_grids_pilot.py '
            r'--source-folder "F:\Projects\heat_index_urop\data\raw\YOUR_SELECTED_FOLDER" '
            r"--max-images 10",
            file=sys.stderr,
        )
        raise SystemExit(2)

    if args.max_images < 1:
        print("Error: --max-images must be at least 1.", file=sys.stderr)
        raise SystemExit(2)

    return args


def check_dependencies() -> bool:
    """Check required packages and report optional GIS package availability."""
    missing = [
        package
        for package in REQUIRED_PACKAGES
        if importlib.util.find_spec(package) is None
    ]
    if missing:
        for package in missing:
            print(
                f"Missing dependency: {package}. Please install it with: pip install {package}",
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


def relative_posix(path: Path) -> str:
    """Return a project-relative POSIX path when possible."""
    root = project_root()
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def normalize_path(path_value: Any) -> str:
    """Normalize paths for robust matching across slashes, case, and drive roots."""
    if path_value is None:
        return ""
    text = str(path_value).strip().strip('"').strip("'")
    if not text:
        return ""
    text = text.replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]

    path = Path(text)
    if path.is_absolute():
        try:
            text = path.resolve().relative_to(project_root()).as_posix()
        except ValueError:
            text = path.as_posix()

    text = re.sub(r"/+", "/", text)
    return text.casefold()


def normalized_base_name(path_value: Any) -> str:
    """Return a case-insensitive DJI base name without _V/_T suffix."""
    stem = Path(str(path_value).replace("\\", "/")).stem
    return re.sub(r"_[vt]$", "", stem, flags=re.IGNORECASE).casefold()


def is_garden_hill_path(path: Path | str) -> bool:
    """Return True when a path should be excluded as Garden Hill imagery."""
    text = str(path).replace("\\", "/").casefold()
    return any(marker in text for marker in ("garden", "gardenhill", "garden hill"))


def has_ignored_folder(path: Path) -> bool:
    """Return True for paths inside folders that should not be searched."""
    ignored = {"misc", "thm"}
    return any(part.casefold() in ignored for part in path.parts)


def is_visible_image(path: Path) -> bool:
    """Return True for visible DJI image names."""
    return (
        path.is_file()
        and path.suffix.casefold() in {".jpg", ".jpeg"}
        and path.stem.casefold().endswith("_v")
    )


def load_vt_pairs(path: Path) -> Any:
    """Load visible/thermal pair table."""
    import pandas as pd

    if not path.is_file():
        raise FileNotFoundError(f"Missing input file: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def load_image_metadata(path: Path) -> Any:
    """Load image metadata for optional contextual matching."""
    import pandas as pd

    if not path.is_file():
        raise FileNotFoundError(f"Missing input file: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def load_thermal_footprints(path: Path) -> Any:
    """Load thermal footprint table."""
    import pandas as pd

    if not path.is_file():
        raise FileNotFoundError(f"Missing input file: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def find_visible_images_in_source_folder(source_folder: Path) -> list[Path]:
    """Recursively find filtered visible images in a user-selected folder."""
    if not source_folder.is_dir():
        raise NotADirectoryError(f"Source folder does not exist: {source_folder}")

    visible_images: list[Path] = []
    for path in source_folder.rglob("*"):
        if not is_visible_image(path):
            continue
        if has_ignored_folder(path) or is_garden_hill_path(path):
            continue
        visible_images.append(path)

    return sorted(visible_images, key=lambda item: normalize_path(relative_posix(item)))


def select_pilot_visible_images(visible_images: list[Path], max_images: int) -> list[Path]:
    """Select the first N visible images after reproducible sorting."""
    return visible_images[:max_images]


def build_pair_indexes(vt_pairs_df: Any) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    """Build exact-path and base-name indexes from vt_pairs.csv."""
    by_visible_path: dict[str, dict[str, str]] = {}
    by_base_name: dict[str, dict[str, str]] = {}

    for _, row in vt_pairs_df.iterrows():
        v_path = str(row.get("v_path", "")).strip()
        t_path = str(row.get("t_path", "")).strip()
        if not v_path:
            continue

        record = {
            "pair_id": str(row.get("pair_id", "")).strip(),
            "pair_status": str(row.get("status", "")).strip(),
            "visible_image_path": v_path,
            "thermal_image_path": t_path,
            "thermal_image_name": Path(t_path.replace("\\", "/")).name if t_path else "",
        }
        by_visible_path.setdefault(normalize_path(v_path), record)
        by_base_name.setdefault(normalized_base_name(v_path), record)

    return by_visible_path, by_base_name


def match_visible_to_thermal(
    visible_path: Path,
    by_visible_path: dict[str, dict[str, str]],
    by_base_name: dict[str, dict[str, str]],
) -> tuple[dict[str, str] | None, str]:
    """Find the paired thermal image for one selected visible image."""
    visible_keys = [
        normalize_path(relative_posix(visible_path)),
        normalize_path(visible_path),
    ]
    for key in visible_keys:
        if key in by_visible_path:
            record = by_visible_path[key]
            if record.get("thermal_image_path"):
                return record, "matched_by_visible_path"
            return None, "pair_row_has_no_thermal_path"

    base_key = normalized_base_name(visible_path)
    record = by_base_name.get(base_key)
    if record and record.get("thermal_image_path"):
        return record, "matched_by_base_name"
    if record:
        return None, "pair_row_has_no_thermal_path"
    return None, "no_pair_in_vt_pairs"


def build_footprint_indexes(footprints_df: Any) -> dict[str, dict[str, dict[str, Any]]]:
    """Build multiple lookup indexes for thermal footprint rows."""
    indexes: dict[str, dict[str, dict[str, Any]]] = {
        "path": {},
        "name": {},
        "pair_id": {},
        "base": {},
    }

    for _, row in footprints_df.iterrows():
        record = row.to_dict()
        image_path = str(record.get("image_path", "")).strip()
        image_name = str(record.get("image_name", "")).strip()
        pair_id = str(record.get("pair_id", "")).strip()
        if image_path:
            indexes["path"].setdefault(normalize_path(image_path), record)
            indexes["base"].setdefault(normalized_base_name(image_path), record)
        if image_name:
            indexes["name"].setdefault(image_name.casefold(), record)
            indexes["base"].setdefault(normalized_base_name(image_name), record)
        if pair_id:
            indexes["pair_id"].setdefault(pair_id.casefold(), record)

    return indexes


def build_metadata_thermal_index(metadata_df: Any) -> dict[str, str]:
    """Build a best-effort index from thermal image names to metadata paths."""
    index: dict[str, str] = {}
    for _, row in metadata_df.iterrows():
        image_type = str(row.get("image_type", "")).strip().casefold()
        image_path = str(row.get("image_path", "")).strip()
        image_name = str(row.get("image_name", "")).strip()
        if image_type not in {"thermal", "t"} and "_t." not in image_name.casefold():
            continue
        if image_path:
            index.setdefault(normalized_base_name(image_path), image_path)
        if image_name and image_path:
            index.setdefault(image_name.casefold(), image_path)
    return index


def match_thermal_to_footprint(
    pair_record: dict[str, str],
    footprint_indexes: dict[str, dict[str, dict[str, Any]]],
    metadata_thermal_index: dict[str, str],
) -> tuple[dict[str, Any] | None, str]:
    """Find the thermal footprint row corresponding to a paired thermal image."""
    thermal_path = pair_record.get("thermal_image_path", "")
    thermal_name = pair_record.get("thermal_image_name", "")
    pair_id = pair_record.get("pair_id", "")

    path_key = normalize_path(thermal_path)
    if path_key in footprint_indexes["path"]:
        return footprint_indexes["path"][path_key], "matched_by_thermal_path"

    if thermal_name and thermal_name.casefold() in footprint_indexes["name"]:
        return footprint_indexes["name"][thermal_name.casefold()], "matched_by_thermal_name"

    if pair_id and pair_id.casefold() in footprint_indexes["pair_id"]:
        return footprint_indexes["pair_id"][pair_id.casefold()], "matched_by_pair_id"

    base_key = normalized_base_name(thermal_path or thermal_name)
    if base_key in footprint_indexes["base"]:
        return footprint_indexes["base"][base_key], "matched_by_base_name"

    metadata_path = metadata_thermal_index.get(base_key)
    if metadata_path and normalize_path(metadata_path) in footprint_indexes["path"]:
        return footprint_indexes["path"][normalize_path(metadata_path)], "matched_via_metadata_path"

    return None, "no_thermal_footprint"


def parse_float(value: Any) -> float | None:
    """Parse numeric table values."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    return number


def make_edges_ascending(min_value: float, max_value: float, step: float) -> list[float]:
    """Create ascending edges from min to max, keeping a final partial edge."""
    if max_value <= min_value:
        return []

    edges = [min_value]
    current = min_value
    while current + step < max_value:
        current += step
        edges.append(current)
    if not math.isclose(edges[-1], max_value, rel_tol=0.0, abs_tol=1e-9):
        edges.append(max_value)
    return edges


def create_grid_for_footprint(
    visible_path: Path,
    pair_record: dict[str, str],
    footprint: dict[str, Any],
    transformer_to_4326: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Create 10m grid cells for one thermal footprint."""
    min_x = parse_float(footprint.get("min_x_2326"))
    max_x = parse_float(footprint.get("max_x_2326"))
    min_y = parse_float(footprint.get("min_y_2326"))
    max_y = parse_float(footprint.get("max_y_2326"))
    ground_width = parse_float(footprint.get("ground_width_m"))
    ground_height = parse_float(footprint.get("ground_height_m"))

    image_id = Path(str(footprint.get("image_name") or pair_record["thermal_image_path"])).stem
    context = {
        "image_id": image_id,
        "pair_id": pair_record.get("pair_id", ""),
        "visible_image_path": relative_posix(visible_path),
        "visible_image_name": visible_path.name,
        "thermal_image_path": str(footprint.get("image_path") or pair_record.get("thermal_image_path", "")),
        "thermal_image_name": str(footprint.get("image_name") or pair_record.get("thermal_image_name", "")),
        "center_x_2326": parse_float(footprint.get("center_x_2326")),
        "center_y_2326": parse_float(footprint.get("center_y_2326")),
        "min_x_2326": min_x,
        "max_x_2326": max_x,
        "min_y_2326": min_y,
        "max_y_2326": max_y,
    }

    if (
        min_x is None
        or max_x is None
        or min_y is None
        or max_y is None
        or ground_width is None
        or ground_height is None
        or max_x <= min_x
        or max_y <= min_y
        or ground_width <= 0
        or ground_height <= 0
    ):
        return [], context

    x_edges = make_edges_ascending(min_x, max_x, GRID_SIZE_M)
    y_edges_ascending = make_edges_ascending(min_y, max_y, GRID_SIZE_M)
    y_edges_north_to_south = list(reversed(y_edges_ascending))
    rows: list[dict[str, Any]] = []

    for grid_row, (y_top, y_bottom) in enumerate(
        zip(y_edges_north_to_south, y_edges_north_to_south[1:])
    ):
        cell_min_y = min(y_bottom, y_top)
        cell_max_y = max(y_bottom, y_top)
        for grid_col, (cell_min_x, cell_max_x) in enumerate(zip(x_edges, x_edges[1:])):
            cell_width = cell_max_x - cell_min_x
            cell_height = cell_max_y - cell_min_y
            center_x = (cell_min_x + cell_max_x) / 2.0
            center_y = (cell_min_y + cell_max_y) / 2.0
            center_lon, center_lat = transformer_to_4326.transform(center_x, center_y)
            is_partial = (
                not math.isclose(cell_width, GRID_SIZE_M, rel_tol=0.0, abs_tol=1e-6)
                or not math.isclose(cell_height, GRID_SIZE_M, rel_tol=0.0, abs_tol=1e-6)
            )
            grid_id = f"{image_id}__r{grid_row:03d}_c{grid_col:03d}"
            rows.append(
                {
                    "grid_id": grid_id,
                    "image_id": image_id,
                    "pair_id": pair_record.get("pair_id", ""),
                    "visible_image_name": visible_path.name,
                    "thermal_image_name": context["thermal_image_name"],
                    "visible_image_path": relative_posix(visible_path),
                    "thermal_image_path": context["thermal_image_path"],
                    "grid_row": grid_row,
                    "grid_col": grid_col,
                    "cell_min_x_2326": cell_min_x,
                    "cell_max_x_2326": cell_max_x,
                    "cell_min_y_2326": cell_min_y,
                    "cell_max_y_2326": cell_max_y,
                    "cell_width_m": cell_width,
                    "cell_height_m": cell_height,
                    "cell_area_m2": cell_width * cell_height,
                    "cell_center_x_2326": center_x,
                    "cell_center_y_2326": center_y,
                    "cell_center_lat": center_lat,
                    "cell_center_lon": center_lon,
                    "is_partial_edge_cell": is_partial,
                    "footprint_min_x_2326": min_x,
                    "footprint_max_x_2326": max_x,
                    "footprint_min_y_2326": min_y,
                    "footprint_max_y_2326": max_y,
                    "footprint_ground_width_m": ground_width,
                    "footprint_ground_height_m": ground_height,
                    "footprint_gsd_x_m_per_px": parse_float(footprint.get("gsd_x_m_per_px")),
                    "footprint_gsd_y_m_per_px": parse_float(footprint.get("gsd_y_m_per_px")),
                    "quality_flag": "ok;partial_edge_cell" if is_partial else "ok",
                    "notes": NOTES,
                }
            )

    return rows, context


def build_grid_geodataframe(grid_rows: list[dict[str, Any]]) -> Any:
    """Build a GeoDataFrame if optional GIS packages are available."""
    if (
        importlib.util.find_spec("geopandas") is None
        or importlib.util.find_spec("shapely") is None
    ):
        return None

    import geopandas as gpd
    from shapely.geometry import Polygon

    geometries = [
        Polygon(cell_polygon_lon_lat(row))
        for row in grid_rows
    ]
    return gpd.GeoDataFrame(grid_rows, geometry=geometries, crs="EPSG:4326")


def cell_polygon_lon_lat(row: dict[str, Any]) -> list[tuple[float, float]]:
    """Return an EPSG:4326 polygon ring for a grid cell."""
    return [
        (row["nw_lon"], row["nw_lat"]),
        (row["ne_lon"], row["ne_lat"]),
        (row["se_lon"], row["se_lat"]),
        (row["sw_lon"], row["sw_lat"]),
        (row["nw_lon"], row["nw_lat"]),
    ]


def add_cell_corner_coordinates(grid_rows: list[dict[str, Any]], transformer_to_4326: Any) -> None:
    """Add WGS84 corner coordinates needed for GeoJSON output."""
    for row in grid_rows:
        corners = {
            "nw": (row["cell_min_x_2326"], row["cell_max_y_2326"]),
            "ne": (row["cell_max_x_2326"], row["cell_max_y_2326"]),
            "se": (row["cell_max_x_2326"], row["cell_min_y_2326"]),
            "sw": (row["cell_min_x_2326"], row["cell_min_y_2326"]),
        }
        for name, (x, y) in corners.items():
            lon, lat = transformer_to_4326.transform(x, y)
            row[f"{name}_lon"] = lon
            row[f"{name}_lat"] = lat


def write_grid_csv(grid_rows: list[dict[str, Any]], output_csv: Path) -> None:
    """Write one CSV row per grid cell."""
    import pandas as pd

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(grid_rows)
    for column in GRID_COLUMNS:
        if column not in df.columns:
            df[column] = None
    df = df[GRID_COLUMNS]
    df.to_csv(output_csv, index=False, encoding="utf-8-sig")


def json_ready_value(value: Any) -> Any:
    """Convert values to JSON-safe scalars."""
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def write_grid_geojson(grid_rows: list[dict[str, Any]], output_geojson: Path) -> None:
    """Write grid cells as EPSG:4326 GeoJSON polygons."""
    output_geojson.parent.mkdir(parents=True, exist_ok=True)
    gdf = build_grid_geodataframe(grid_rows)
    if gdf is not None:
        try:
            gdf.to_file(output_geojson, driver="GeoJSON")
            return
        except Exception as exc:
            print(
                "Warning: GeoPandas GeoJSON export failed; writing GeoJSON "
                f"directly instead. Details: {exc}"
            )

    features = []
    for row in grid_rows:
        properties = {
            key: json_ready_value(value)
            for key, value in row.items()
            if key in GRID_COLUMNS
        }
        features.append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[list(point) for point in cell_polygon_lon_lat(row)]],
                },
            }
        )

    geojson = {
        "type": "FeatureCollection",
        "name": "pilot_10m_grid_cells",
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


def safe_stem(value: str) -> str:
    """Return a filesystem-safe stem for figure names."""
    stem = Path(value).stem
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("_") or "image"


def group_rows_by_image(grid_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group grid rows by image id."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in grid_rows:
        grouped[str(row["image_id"])].append(row)
    return dict(grouped)


def grid_extents(rows: list[dict[str, Any]]) -> tuple[float, float, float, float]:
    """Return min/max x/y extents for a group of grid rows."""
    return (
        min(row["cell_min_x_2326"] for row in rows),
        max(row["cell_max_x_2326"] for row in rows),
        min(row["cell_min_y_2326"] for row in rows),
        max(row["cell_max_y_2326"] for row in rows),
    )


def draw_grid_overlay(ax: Any, rows: list[dict[str, Any]], title: str, center: tuple[float | None, float | None]) -> None:
    """Draw footprint rectangle and grid lines in EPSG:2326 coordinates."""
    min_x, max_x, min_y, max_y = grid_extents(rows)
    x_values = sorted(
        {
            row["cell_min_x_2326"]
            for row in rows
        }
        | {
            row["cell_max_x_2326"]
            for row in rows
        }
    )
    y_values = sorted(
        {
            row["cell_min_y_2326"]
            for row in rows
        }
        | {
            row["cell_max_y_2326"]
            for row in rows
        }
    )

    ax.plot(
        [min_x, max_x, max_x, min_x, min_x],
        [max_y, max_y, min_y, min_y, max_y],
        color="#111111",
        linewidth=1.3,
        label="thermal footprint",
    )
    for x in x_values:
        ax.plot([x, x], [min_y, max_y], color="#1f77b4", linewidth=0.35, alpha=0.55)
    for y in y_values:
        ax.plot([min_x, max_x], [y, y], color="#1f77b4", linewidth=0.35, alpha=0.55)

    center_x, center_y = center
    if center_x is not None and center_y is not None:
        ax.scatter([center_x], [center_y], marker="+", s=70, color="#d62728", label="image center")

    margin_x = max((max_x - min_x) * 0.05, 1.0)
    margin_y = max((max_y - min_y) * 0.05, 1.0)
    ax.set_xlim(min_x - margin_x, max_x + margin_x)
    ax.set_ylim(min_y - margin_y, max_y + margin_y)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(title, fontsize=9)
    ax.set_xlabel("HK1980 Grid Easting (m, EPSG:2326)")
    ax.set_ylabel("HK1980 Grid Northing (m, EPSG:2326)")
    ax.grid(True, linewidth=0.25, alpha=0.35)


def write_individual_overlay_figures(
    grid_rows: list[dict[str, Any]],
    footprint_contexts: dict[str, dict[str, Any]],
    output_dir: Path,
) -> list[Path]:
    """Create one grid overlay figure per valid pilot image."""
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)
    figure_paths: list[Path] = []
    for image_id, rows in group_rows_by_image(grid_rows).items():
        context = footprint_contexts.get(image_id, {})
        visible_name = str(rows[0].get("visible_image_name") or image_id)
        pair_id = str(rows[0].get("pair_id") or "")
        figure_path = output_dir / f"{safe_stem(visible_name)}_grid_overlay.png"

        fig, ax = plt.subplots(figsize=(8, 8))
        title = f"{visible_name}\n{pair_id}" if pair_id else visible_name
        draw_grid_overlay(
            ax,
            rows,
            title,
            (
                parse_float(context.get("center_x_2326")),
                parse_float(context.get("center_y_2326")),
            ),
        )
        fig.tight_layout()
        fig.savefig(figure_path, dpi=180)
        plt.close(fig)
        figure_paths.append(figure_path)

    return figure_paths


def write_combined_preview_figure(
    grid_rows: list[dict[str, Any]],
    footprint_contexts: dict[str, dict[str, Any]],
    output_path: Path,
) -> None:
    """Create one combined preview figure for all pilot grids."""
    import matplotlib.pyplot as plt

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 9))

    if not grid_rows:
        ax.text(0.5, 0.5, "No pilot grid cells created", ha="center", va="center")
        ax.set_axis_off()
    else:
        colors = plt.cm.tab10.colors
        grouped = group_rows_by_image(grid_rows)
        for index, (image_id, rows) in enumerate(grouped.items()):
            color = colors[index % len(colors)]
            min_x, max_x, min_y, max_y = grid_extents(rows)
            ax.plot(
                [min_x, max_x, max_x, min_x, min_x],
                [max_y, max_y, min_y, min_y, max_y],
                color=color,
                linewidth=1.2,
                label=image_id[:18],
            )
            x_values = sorted({row["cell_min_x_2326"] for row in rows} | {row["cell_max_x_2326"] for row in rows})
            y_values = sorted({row["cell_min_y_2326"] for row in rows} | {row["cell_max_y_2326"] for row in rows})
            for x in x_values:
                ax.plot([x, x], [min_y, max_y], color=color, linewidth=0.22, alpha=0.35)
            for y in y_values:
                ax.plot([min_x, max_x], [y, y], color=color, linewidth=0.22, alpha=0.35)

            context = footprint_contexts.get(image_id, {})
            center_x = parse_float(context.get("center_x_2326"))
            center_y = parse_float(context.get("center_y_2326"))
            if center_x is not None and center_y is not None:
                ax.scatter([center_x], [center_y], marker="+", s=45, color=color)

        min_x, max_x, min_y, max_y = grid_extents(grid_rows)
        margin_x = max((max_x - min_x) * 0.05, 1.0)
        margin_y = max((max_y - min_y) * 0.05, 1.0)
        ax.set_xlim(min_x - margin_x, max_x + margin_x)
        ax.set_ylim(min_y - margin_y, max_y + margin_y)
        ax.set_aspect("equal", adjustable="box")
        ax.set_title("Pilot 10m Grid Cells from Thermal Footprints")
        ax.set_xlabel("HK1980 Grid Easting (m, EPSG:2326)")
        ax.set_ylabel("HK1980 Grid Northing (m, EPSG:2326)")
        ax.grid(True, linewidth=0.25, alpha=0.35)
        if len(grouped) <= 10:
            ax.legend(fontsize=6, loc="best")

    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def number_summary(values: list[int]) -> str:
    """Return min / median / max text for integer counts."""
    if not values:
        return "n/a"
    return f"min={min(values)}, median={median(values):.0f}, max={max(values)}"


def write_summary(
    summary_path: Path,
    source_folder: Path,
    max_images: int,
    visible_images_found: int,
    selected_visible_images: list[Path],
    selected_records: list[dict[str, Any]],
    grid_rows: list[dict[str, Any]],
    output_csv: Path,
    output_geojson: Path,
    output_figure_dir: Path,
) -> None:
    """Write a plain-text pilot grid summary."""
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with_pair = sum(record["pair_record"] is not None for record in selected_records)
    with_footprint = sum(record["footprint"] is not None and record["grid_cell_count"] > 0 for record in selected_records)
    missing_pair = sum(record["pair_record"] is None for record in selected_records)
    missing_footprint = sum(
        record["pair_record"] is not None
        and (record["footprint"] is None or record["grid_cell_count"] == 0)
        for record in selected_records
    )
    full_cells = sum(not row["is_partial_edge_cell"] for row in grid_rows)
    partial_cells = sum(row["is_partial_edge_cell"] for row in grid_rows)
    cells_per_image = [
        record["grid_cell_count"]
        for record in selected_records
        if record["grid_cell_count"] > 0
    ]

    lines = [
        "Pilot 10m x 10m grid construction summary",
        "",
        f"source folder used: {source_folder}",
        f"max images requested: {max_images}",
        f"number of _V.JPG images found in source folder: {visible_images_found}",
        f"number of selected visible images: {len(selected_visible_images)}",
        f"number of selected visible images with paired thermal images: {with_pair}",
        f"number of selected images with available thermal footprints: {with_footprint}",
        f"number of images skipped due to missing pair: {missing_pair}",
        f"number of images skipped due to missing footprint: {missing_footprint}",
        f"total grid cells created: {len(grid_rows)}",
        f"number of full 10m x 10m cells: {full_cells}",
        f"number of partial edge cells: {partial_cells}",
        f"min / median / max cells per image: {number_summary(cells_per_image)}",
        "",
        f"output CSV path: {relative_posix(output_csv)}",
        f"output GeoJSON path: {relative_posix(output_geojson)}",
        f"output overlay figure folder: {relative_posix(output_figure_dir)}",
        "",
        "selected visible images:",
    ]
    for index, record in enumerate(selected_records, start=1):
        visible = record["visible_path"]
        lines.append(
            f"{index}. {relative_posix(visible)} | status={record['status']} | "
            f"pair_match={record['pair_match_method']} | "
            f"footprint_match={record['footprint_match_method']} | "
            f"grid_cells={record['grid_cell_count']}"
        )
        if record.get("skip_reason"):
            lines.append(f"   skip_reason={record['skip_reason']}")

    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def resolve_source_folder(source_folder_text: str) -> Path:
    """Resolve source-folder input relative to project root when needed."""
    source_folder = Path(source_folder_text)
    if source_folder.is_absolute():
        return source_folder
    return project_root() / source_folder


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not check_dependencies():
        return 1

    from pyproj import Transformer

    root = project_root()
    source_folder = resolve_source_folder(args.source_folder)
    vt_pairs_csv = root / VT_PAIRS_CSV_NAME
    image_metadata_csv = root / IMAGE_METADATA_CSV_NAME
    thermal_footprints_csv = root / THERMAL_FOOTPRINTS_CSV_NAME
    output_csv = root / OUTPUT_GRID_CSV_NAME
    output_geojson = root / OUTPUT_GEOJSON_NAME
    output_figure_dir = root / OUTPUT_FIGURE_DIR_NAME
    summary_txt = root / SUMMARY_TXT_NAME
    combined_preview = output_figure_dir / "pilot_grid_combined_preview.png"

    print(f"Source folder: {source_folder}")
    try:
        visible_images = find_visible_images_in_source_folder(source_folder)
        vt_pairs_df = load_vt_pairs(vt_pairs_csv)
        metadata_df = load_image_metadata(image_metadata_csv)
        footprints_df = load_thermal_footprints(thermal_footprints_csv)
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    selected_visible_images = select_pilot_visible_images(visible_images, args.max_images)
    print(f"Visible images found after filtering: {len(visible_images)}")
    print(f"Selected visible images: {len(selected_visible_images)}")

    pair_by_path, pair_by_base = build_pair_indexes(vt_pairs_df)
    footprint_indexes = build_footprint_indexes(footprints_df)
    metadata_thermal_index = build_metadata_thermal_index(metadata_df)
    transformer_to_4326 = Transformer.from_crs("EPSG:2326", "EPSG:4326", always_xy=True)

    all_grid_rows: list[dict[str, Any]] = []
    selected_records: list[dict[str, Any]] = []
    footprint_contexts: dict[str, dict[str, Any]] = {}

    for visible_path in selected_visible_images:
        pair_record, pair_match_method = match_visible_to_thermal(
            visible_path,
            pair_by_path,
            pair_by_base,
        )
        selected_record: dict[str, Any] = {
            "visible_path": visible_path,
            "pair_record": pair_record,
            "footprint": None,
            "status": "skipped",
            "pair_match_method": pair_match_method,
            "footprint_match_method": "",
            "grid_cell_count": 0,
            "skip_reason": "",
        }

        if pair_record is None:
            selected_record["skip_reason"] = pair_match_method
            selected_records.append(selected_record)
            continue

        footprint, footprint_match_method = match_thermal_to_footprint(
            pair_record,
            footprint_indexes,
            metadata_thermal_index,
        )
        selected_record["footprint"] = footprint
        selected_record["footprint_match_method"] = footprint_match_method
        if footprint is None:
            selected_record["skip_reason"] = footprint_match_method
            selected_records.append(selected_record)
            continue

        grid_rows, context = create_grid_for_footprint(
            visible_path,
            pair_record,
            footprint,
            transformer_to_4326,
        )
        if not grid_rows:
            selected_record["skip_reason"] = "thermal_footprint_has_zero_or_invalid_area"
            selected_records.append(selected_record)
            continue

        add_cell_corner_coordinates(grid_rows, transformer_to_4326)
        all_grid_rows.extend(grid_rows)
        footprint_contexts[context["image_id"]] = context
        selected_record["status"] = "grid_created"
        selected_record["grid_cell_count"] = len(grid_rows)
        selected_records.append(selected_record)

    write_grid_csv(all_grid_rows, output_csv)
    write_grid_geojson(all_grid_rows, output_geojson)
    write_individual_overlay_figures(all_grid_rows, footprint_contexts, output_figure_dir)
    write_combined_preview_figure(all_grid_rows, footprint_contexts, combined_preview)
    write_summary(
        summary_path=summary_txt,
        source_folder=source_folder,
        max_images=args.max_images,
        visible_images_found=len(visible_images),
        selected_visible_images=selected_visible_images,
        selected_records=selected_records,
        grid_rows=all_grid_rows,
        output_csv=output_csv,
        output_geojson=output_geojson,
        output_figure_dir=output_figure_dir,
    )

    print(f"Total grid cells created: {len(all_grid_rows)}")
    print(f"Output CSV path: {relative_posix(output_csv)}")
    print(f"Output GeoJSON path: {relative_posix(output_geojson)}")
    print(f"Output overlay figure folder: {relative_posix(output_figure_dir)}")
    print(f"Summary text path: {relative_posix(summary_txt)}")
    print()
    print("Next suggested command:")
    print(
        r'python scripts\04_create_10m_grids_pilot.py '
        r'--source-folder "F:\Projects\heat_index_urop\data\raw\YOUR_SELECTED_FOLDER" '
        r"--max-images 10"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
