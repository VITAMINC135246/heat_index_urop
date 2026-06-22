#!/usr/bin/env python3
"""Estimate first-pass ground footprints for DJI thermal images."""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path
from statistics import median
from typing import Any


INPUT_CSV_NAME = Path("data") / "metadata" / "dji_image_metadata.csv"
OUTPUT_CSV_NAME = Path("data") / "processed" / "footprints" / "thermal_image_footprints.csv"
OUTPUT_GEOJSON_NAME = Path("outputs") / "geodata" / "thermal_image_footprints.geojson"
SUMMARY_TXT_NAME = Path("outputs") / "reports" / "03_estimate_thermal_footprints_summary.txt"
PREVIEW_FIGURE_NAME = Path("outputs") / "figures" / "thermal_footprint_preview.png"

ASSUMED_HORIZONTAL_FOV_DEG = 61.0
ASSUMED_VERTICAL_FOV_DEG = 48.0
ASSUMED_NADIR_VIEW = True
ASSUMED_IMAGE_TOP_IS_NORTH = True
ASSUMED_GPS_AS_IMAGE_CENTER = True
TERRAIN_ELEVATION_KNOWN = False
UNUSUAL_ALTITUDE_LIMIT_M = 500.0

REQUIRED_PACKAGES = ["pandas", "pyproj", "matplotlib"]
OPTIONAL_GIS_PACKAGES = ["geopandas", "shapely"]

CSV_COLUMNS = [
    "image_path",
    "image_name",
    "image_type",
    "pair_id",
    "pair_status",
    "parent_folder",
    "center_lat",
    "center_lon",
    "center_x_2326",
    "center_y_2326",
    "relative_altitude_m",
    "absolute_altitude_m",
    "gps_altitude_m",
    "image_width_px",
    "image_height_px",
    "focal_length_mm",
    "f_number",
    "horizontal_fov_deg",
    "vertical_fov_deg",
    "fov_source",
    "ground_width_m",
    "ground_height_m",
    "footprint_area_m2",
    "gsd_x_m_per_px",
    "gsd_y_m_per_px",
    "min_x_2326",
    "max_x_2326",
    "min_y_2326",
    "max_y_2326",
    "nw_x_2326",
    "nw_y_2326",
    "ne_x_2326",
    "ne_y_2326",
    "se_x_2326",
    "se_y_2326",
    "sw_x_2326",
    "sw_y_2326",
    "nw_lat",
    "nw_lon",
    "ne_lat",
    "ne_lon",
    "se_lat",
    "se_lon",
    "sw_lat",
    "sw_lon",
    "min_lat",
    "max_lat",
    "min_lon",
    "max_lon",
    "assumed_nadir_view",
    "assumed_image_top_is_north",
    "assumed_gps_as_image_center",
    "terrain_elevation_known",
    "footprint_method",
    "quality_flag",
    "notes",
]

FOOTPRINT_METHOD = (
    "First-pass nadir footprint: GPS metadata is treated as image center; "
    "EPSG:4326 center is transformed to EPSG:2326; an axis-aligned rectangle "
    "is built from altitude and FOV; corners are transformed back to EPSG:4326."
)

NOTES = (
    "Approximate thermal footprint for HKUST-focused first-pass workflow. "
    "Garden Hill images are excluded. Terrain elevation is unknown, so "
    "relative_altitude is used as flight height above ground. This is not "
    "precise photogrammetric georeferencing."
)


def project_root() -> Path:
    """Return the repository root based on this script location."""
    return Path(__file__).resolve().parents[1]


def check_dependencies() -> bool:
    """Check required third-party GIS/data packages before importing them."""
    missing = [
        package
        for package in REQUIRED_PACKAGES
        if importlib.util.find_spec(package) is None
    ]
    if not missing:
        optional_missing = [
            package
            for package in OPTIONAL_GIS_PACKAGES
            if importlib.util.find_spec(package) is None
        ]
        if optional_missing:
            print(
                "Optional GIS dependency not available: "
                + ", ".join(optional_missing)
                + ". GeoJSON will be written directly without GeoPandas/Shapely."
            )
        return True

    for package in missing:
        print(
            f"Missing dependency: {package}. Please install it with: pip install {package}",
            file=sys.stderr,
        )
    print(
        "Install the missing packages, then rerun: "
        r"python scripts\03_estimate_thermal_footprints.py",
        file=sys.stderr,
    )
    return False


def relative_posix(path: Path) -> str:
    """Return a project-relative POSIX path when possible."""
    root = project_root()
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def load_metadata(input_csv: Path) -> Any:
    """Load Step 1 image metadata."""
    import pandas as pd

    if not input_csv.is_file():
        raise FileNotFoundError(f"Input metadata file does not exist: {input_csv}")
    return pd.read_csv(input_csv)


def is_missing(value: Any) -> bool:
    """Return True when a value should be treated as missing."""
    try:
        import pandas as pd

        if pd.isna(value):
            return True
    except (ImportError, TypeError, ValueError):
        pass
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def parse_float(value: Any) -> float | None:
    """Parse a float from a CSV value, preserving blanks as None."""
    if is_missing(value):
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        text = str(value).strip()
        try:
            return float(text)
        except ValueError:
            return None


def row_text(row: Any, column: str) -> str:
    """Return a clean string from a DataFrame row column."""
    if column not in row.index or is_missing(row[column]):
        return ""
    return str(row[column]).strip()


def normalized_name(name: str) -> str:
    """Normalize a column name for tolerant lookup."""
    return "".join(char for char in name.lower() if char.isalnum())


def first_existing_value(row: Any, candidates: list[str]) -> Any:
    """Return the first non-empty row value for a list of possible columns."""
    direct_columns = set(row.index)
    for candidate in candidates:
        if candidate in direct_columns and not is_missing(row[candidate]):
            return row[candidate]

    normalized_to_column = {
        normalized_name(column): column
        for column in row.index
    }
    for candidate in candidates:
        column = normalized_to_column.get(normalized_name(candidate))
        if column is not None and not is_missing(row[column]):
            return row[column]

    return None


def is_thermal_record(row: Any) -> bool:
    """Return True for thermal image metadata rows."""
    image_type = row_text(row, "image_type").lower()
    if image_type in {"t", "thermal"}:
        return True

    combined = " ".join(
        row_text(row, column).lower()
        for column in ("source_file", "image_path", "image_name")
    )
    return any(marker in combined for marker in ("_t.jpg", "_t.jpeg"))


def is_garden_hill_record(row: Any) -> bool:
    """Return True when a row should be excluded as Garden Hill imagery."""
    combined = " ".join(
        row_text(row, column).lower()
        for column in ("source_file", "image_path", "image_name", "parent_folder")
    )
    return any(marker in combined for marker in ("garden", "gardenhill", "garden hill"))


def filter_thermal_hkust_records(df: Any) -> tuple[Any, int, int]:
    """Keep thermal records and exclude Garden Hill records."""
    thermal_mask = df.apply(is_thermal_record, axis=1)
    thermal_df = df.loc[thermal_mask].copy()
    garden_mask = thermal_df.apply(is_garden_hill_record, axis=1)
    hkust_df = thermal_df.loc[~garden_mask].copy()
    return hkust_df, int(thermal_mask.sum()), int(garden_mask.sum())


def get_fov_values(row: Any) -> tuple[float, float, str]:
    """Determine horizontal/vertical FOV using metadata, sensor size, or fallback."""
    horizontal_fov = parse_float(
        first_existing_value(
            row,
            [
                "horizontal_fov_deg",
                "horizontal_fov",
                "HorizontalFOV",
                "Horizontal Field Of View",
                "FOVHorizontal",
            ],
        )
    )
    vertical_fov = parse_float(
        first_existing_value(
            row,
            [
                "vertical_fov_deg",
                "vertical_fov",
                "VerticalFOV",
                "Vertical Field Of View",
                "FOVVertical",
            ],
        )
    )
    if valid_positive(horizontal_fov) and valid_positive(vertical_fov):
        return horizontal_fov, vertical_fov, "metadata_fov"

    focal_length = parse_float(
        first_existing_value(row, ["focal_length", "focal_length_mm", "FocalLength"])
    )
    sensor_width = parse_float(
        first_existing_value(
            row,
            [
                "sensor_width",
                "sensor_width_mm",
                "SensorWidth",
                "Sensor Width",
                "SensorWidthMM",
            ],
        )
    )
    sensor_height = parse_float(
        first_existing_value(
            row,
            [
                "sensor_height",
                "sensor_height_mm",
                "SensorHeight",
                "Sensor Height",
                "SensorHeightMM",
            ],
        )
    )
    if (
        valid_positive(focal_length)
        and valid_positive(sensor_width)
        and valid_positive(sensor_height)
    ):
        horizontal = math.degrees(2.0 * math.atan(sensor_width / (2.0 * focal_length)))
        vertical = math.degrees(2.0 * math.atan(sensor_height / (2.0 * focal_length)))
        return horizontal, vertical, "estimated_from_sensor_and_focal_length"

    return ASSUMED_HORIZONTAL_FOV_DEG, ASSUMED_VERTICAL_FOV_DEG, "assumed_fallback"


def valid_positive(value: float | None) -> bool:
    """Return True for positive finite numeric values."""
    return value is not None and math.isfinite(value) and value > 0


def required_metadata_status(row: Any) -> tuple[bool, list[str]]:
    """Return whether a row has the fields required for footprint estimation."""
    flags: list[str] = []
    lat = parse_float(row.get("gps_latitude"))
    lon = parse_float(row.get("gps_longitude"))
    relative_altitude = parse_float(row.get("relative_altitude"))
    image_width = parse_float(row.get("image_width"))
    image_height = parse_float(row.get("image_height"))

    if lat is None or lon is None:
        flags.append("missing_gps")
    if relative_altitude is None:
        flags.append("missing_relative_altitude")
    if image_width is None or image_height is None:
        flags.append("missing_image_size")

    return not flags, flags


def make_quality_flag(flags: list[str]) -> str:
    """Build a semicolon-separated quality flag string."""
    if "ok" not in flags:
        flags.insert(0, "ok")
    return ";".join(dict.fromkeys(flags))


def estimate_footprint_for_row(row: Any, transformer_to_2326: Any, transformer_to_4326: Any) -> dict[str, Any]:
    """Estimate one thermal image footprint in EPSG:2326 and EPSG:4326."""
    center_lat = parse_float(row["gps_latitude"])
    center_lon = parse_float(row["gps_longitude"])
    relative_altitude_m = parse_float(row["relative_altitude"])
    image_width_px = parse_float(row["image_width"])
    image_height_px = parse_float(row["image_height"])

    if (
        center_lat is None
        or center_lon is None
        or relative_altitude_m is None
        or image_width_px is None
        or image_height_px is None
    ):
        raise ValueError("Missing required metadata for footprint estimation.")

    horizontal_fov_deg, vertical_fov_deg, fov_source = get_fov_values(row)
    ground_width_m = 2.0 * relative_altitude_m * math.tan(
        math.radians(horizontal_fov_deg) / 2.0
    )
    ground_height_m = 2.0 * relative_altitude_m * math.tan(
        math.radians(vertical_fov_deg) / 2.0
    )
    footprint_area_m2 = ground_width_m * ground_height_m
    gsd_x_m_per_px = ground_width_m / image_width_px if image_width_px else None
    gsd_y_m_per_px = ground_height_m / image_height_px if image_height_px else None

    center_x_2326, center_y_2326 = transformer_to_2326.transform(center_lon, center_lat)
    half_width = ground_width_m / 2.0
    half_height = ground_height_m / 2.0
    min_x_2326 = center_x_2326 - half_width
    max_x_2326 = center_x_2326 + half_width
    min_y_2326 = center_y_2326 - half_height
    max_y_2326 = center_y_2326 + half_height

    corners_2326 = {
        "nw": (min_x_2326, max_y_2326),
        "ne": (max_x_2326, max_y_2326),
        "se": (max_x_2326, min_y_2326),
        "sw": (min_x_2326, min_y_2326),
    }
    corners_4326 = {
        name: transformer_to_4326.transform(x, y)
        for name, (x, y) in corners_2326.items()
    }
    corner_lons = [lon for lon, lat in corners_4326.values()]
    corner_lats = [lat for lon, lat in corners_4326.values()]

    quality_flags: list[str] = []
    if relative_altitude_m <= 0 or relative_altitude_m > UNUSUAL_ALTITUDE_LIMIT_M:
        quality_flags.append("unusual_altitude")
    if fov_source == "assumed_fallback":
        quality_flags.append("missing_fov_using_assumption")

    output = {
        "image_path": row_text(row, "image_path"),
        "image_name": row_text(row, "image_name"),
        "image_type": row_text(row, "image_type"),
        "pair_id": row_text(row, "pair_id"),
        "pair_status": row_text(row, "pair_status"),
        "parent_folder": row_text(row, "parent_folder"),
        "center_lat": center_lat,
        "center_lon": center_lon,
        "center_x_2326": center_x_2326,
        "center_y_2326": center_y_2326,
        "relative_altitude_m": relative_altitude_m,
        "absolute_altitude_m": parse_float(row.get("absolute_altitude")),
        "gps_altitude_m": parse_float(row.get("gps_altitude")),
        "image_width_px": image_width_px,
        "image_height_px": image_height_px,
        "focal_length_mm": parse_float(
            first_existing_value(row, ["focal_length", "focal_length_mm", "FocalLength"])
        ),
        "f_number": parse_float(row.get("f_number")),
        "horizontal_fov_deg": horizontal_fov_deg,
        "vertical_fov_deg": vertical_fov_deg,
        "fov_source": fov_source,
        "ground_width_m": ground_width_m,
        "ground_height_m": ground_height_m,
        "footprint_area_m2": footprint_area_m2,
        "gsd_x_m_per_px": gsd_x_m_per_px,
        "gsd_y_m_per_px": gsd_y_m_per_px,
        "min_x_2326": min_x_2326,
        "max_x_2326": max_x_2326,
        "min_y_2326": min_y_2326,
        "max_y_2326": max_y_2326,
        "assumed_nadir_view": ASSUMED_NADIR_VIEW,
        "assumed_image_top_is_north": ASSUMED_IMAGE_TOP_IS_NORTH,
        "assumed_gps_as_image_center": ASSUMED_GPS_AS_IMAGE_CENTER,
        "terrain_elevation_known": TERRAIN_ELEVATION_KNOWN,
        "footprint_method": FOOTPRINT_METHOD,
        "quality_flag": make_quality_flag(quality_flags),
        "notes": NOTES,
    }

    for name, (x, y) in corners_2326.items():
        output[f"{name}_x_2326"] = x
        output[f"{name}_y_2326"] = y
    for name, (lon, lat) in corners_4326.items():
        output[f"{name}_lat"] = lat
        output[f"{name}_lon"] = lon

    output["min_lat"] = min(corner_lats)
    output["max_lat"] = max(corner_lats)
    output["min_lon"] = min(corner_lons)
    output["max_lon"] = max(corner_lons)
    return output


def build_geodataframe(footprint_rows: list[dict[str, Any]]) -> Any:
    """Build a GeoDataFrame with EPSG:4326 footprint polygons when available."""
    if (
        importlib.util.find_spec("geopandas") is None
        or importlib.util.find_spec("shapely") is None
    ):
        return None

    import geopandas as gpd
    from shapely.geometry import Polygon

    polygons = []
    for row in footprint_rows:
        polygons.append(
            Polygon(
                [
                    (row["nw_lon"], row["nw_lat"]),
                    (row["ne_lon"], row["ne_lat"]),
                    (row["se_lon"], row["se_lat"]),
                    (row["sw_lon"], row["sw_lat"]),
                    (row["nw_lon"], row["nw_lat"]),
                ]
            )
        )

    return gpd.GeoDataFrame(footprint_rows, geometry=polygons, crs="EPSG:4326")


def write_csv(footprint_rows: list[dict[str, Any]], output_csv: Path) -> None:
    """Write the footprint table without geometry."""
    import pandas as pd

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(footprint_rows)
    for column in CSV_COLUMNS:
        if column not in df.columns:
            df[column] = None
    df = df[CSV_COLUMNS]
    df.to_csv(output_csv, index=False, encoding="utf-8-sig")


def write_geojson(gdf: Any, footprint_rows: list[dict[str, Any]], output_geojson: Path) -> None:
    """Write GeoJSON in EPSG:4326."""
    output_geojson.parent.mkdir(parents=True, exist_ok=True)
    if gdf is not None:
        gdf.to_file(output_geojson, driver="GeoJSON")
        return

    features = []
    for row in footprint_rows:
        properties = {
            key: json_ready_value(value)
            for key, value in row.items()
            if key in CSV_COLUMNS
        }
        geometry = {
            "type": "Polygon",
            "coordinates": [
                [
                    [row["nw_lon"], row["nw_lat"]],
                    [row["ne_lon"], row["ne_lat"]],
                    [row["se_lon"], row["se_lat"]],
                    [row["sw_lon"], row["sw_lat"]],
                    [row["nw_lon"], row["nw_lat"]],
                ]
            ],
        }
        features.append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": geometry,
            }
        )

    feature_collection = {
        "type": "FeatureCollection",
        "name": "thermal_image_footprints",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
        },
        "features": features,
    }
    output_geojson.write_text(
        json.dumps(feature_collection, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_preview_figure(footprint_rows: list[dict[str, Any]], output_figure: Path) -> None:
    """Write a simple map-coordinate preview of footprint polygons."""
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as PlotPolygon

    output_figure.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(14, 7))

    if not footprint_rows:
        ax = axes[0]
        ax.text(0.5, 0.5, "No thermal footprints created", ha="center", va="center")
        ax.set_axis_off()
        axes[1].set_axis_off()
    else:
        all_x: list[float] = []
        all_y: list[float] = []

        center_x = [row["center_x_2326"] for row in footprint_rows]
        center_y = [row["center_y_2326"] for row in footprint_rows]
        altitude = [row["relative_altitude_m"] for row in footprint_rows]
        axes[0].scatter(
            center_x,
            center_y,
            c=altitude,
            cmap="viridis",
            s=10,
            alpha=0.85,
            linewidths=0,
        )
        colorbar = fig.colorbar(axes[0].collections[0], ax=axes[0], shrink=0.82)
        colorbar.set_label("Relative altitude (m)")
        axes[0].set_title("Thermal Image Centers")
        axes[0].set_xlabel("HK1980 Grid Easting (m, EPSG:2326)")
        axes[0].set_ylabel("HK1980 Grid Northing (m, EPSG:2326)")
        axes[0].set_aspect("equal", adjustable="box")
        axes[0].grid(True, linewidth=0.3, alpha=0.35)

        sample_step = max(1, len(footprint_rows) // 80)
        sampled_rows = footprint_rows[::sample_step]
        for row in footprint_rows:
            xy = [
                (row["nw_x_2326"], row["nw_y_2326"]),
                (row["ne_x_2326"], row["ne_y_2326"]),
                (row["se_x_2326"], row["se_y_2326"]),
                (row["sw_x_2326"], row["sw_y_2326"]),
            ]
            all_x.extend(point[0] for point in xy)
            all_y.extend(point[1] for point in xy)

        for row in sampled_rows:
            xy = [
                (row["nw_x_2326"], row["nw_y_2326"]),
                (row["ne_x_2326"], row["ne_y_2326"]),
                (row["se_x_2326"], row["se_y_2326"]),
                (row["sw_x_2326"], row["sw_y_2326"]),
            ]
            patch = PlotPolygon(
                xy,
                closed=True,
                facecolor="none",
                edgecolor="#1f77b4",
                linewidth=0.75,
                alpha=0.45,
            )
            axes[1].add_patch(patch)

        axes[1].scatter(center_x, center_y, s=4, color="#d62728", alpha=0.55)
        axes[1].set_title(f"Sampled Footprint Outlines ({len(sampled_rows)} of {len(footprint_rows)})")
        axes[1].set_xlabel("HK1980 Grid Easting (m, EPSG:2326)")
        axes[1].set_ylabel("HK1980 Grid Northing (m, EPSG:2326)")
        axes[1].set_aspect("equal", adjustable="box")
        axes[1].grid(True, linewidth=0.3, alpha=0.35)

        if all_x and all_y:
            x_margin = max((max(all_x) - min(all_x)) * 0.05, 1.0)
            y_margin = max((max(all_y) - min(all_y)) * 0.05, 1.0)
            for ax in axes:
                ax.set_xlim(min(all_x) - x_margin, max(all_x) + x_margin)
                ax.set_ylim(min(all_y) - y_margin, max(all_y) + y_margin)

    fig.tight_layout()
    fig.savefig(output_figure, dpi=200)
    plt.close(fig)


def json_ready_value(value: Any) -> Any:
    """Convert values to JSON-safe scalars."""
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def number_summary(values: list[float]) -> str:
    """Return min/median/max text for a numeric list."""
    clean_values = [
        float(value)
        for value in values
        if value is not None and math.isfinite(float(value))
    ]
    if not clean_values:
        return "n/a"
    return (
        f"min={min(clean_values):.6g}, "
        f"median={median(clean_values):.6g}, "
        f"max={max(clean_values):.6g}"
    )


def write_summary(
    summary_path: Path,
    total_metadata_rows: int,
    thermal_rows_found: int,
    garden_rows_excluded: int,
    thermal_rows_after_exclusion: int,
    rows_with_required_metadata: int,
    skipped_missing_gps: int,
    skipped_missing_relative_altitude: int,
    skipped_missing_image_size: int,
    footprint_rows: list[dict[str, Any]],
    output_csv: Path,
    output_geojson: Path,
    output_figure: Path,
) -> None:
    """Write a plain-text processing summary."""
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    fov_counts = {
        "metadata_fov": 0,
        "estimated_from_sensor_and_focal_length": 0,
        "assumed_fallback": 0,
    }
    for row in footprint_rows:
        fov_counts[row["fov_source"]] = fov_counts.get(row["fov_source"], 0) + 1

    lines = [
        "Thermal image footprint estimation summary",
        "",
        f"total metadata rows read: {total_metadata_rows}",
        f"thermal image rows found: {thermal_rows_found}",
        f"Garden Hill rows excluded: {garden_rows_excluded}",
        f"thermal rows after Garden Hill exclusion: {thermal_rows_after_exclusion}",
        f"rows with required metadata: {rows_with_required_metadata}",
        f"rows skipped due to missing GPS: {skipped_missing_gps}",
        f"rows skipped due to missing relative_altitude: {skipped_missing_relative_altitude}",
        f"rows skipped due to missing image size: {skipped_missing_image_size}",
        f"number of footprints created: {len(footprint_rows)}",
        "",
        f"number using metadata_fov: {fov_counts.get('metadata_fov', 0)}",
        (
            "number using estimated_from_sensor_and_focal_length: "
            f"{fov_counts.get('estimated_from_sensor_and_focal_length', 0)}"
        ),
        f"number using assumed_fallback FOV: {fov_counts.get('assumed_fallback', 0)}",
        "",
        (
            "min / median / max relative_altitude_m: "
            f"{number_summary([row['relative_altitude_m'] for row in footprint_rows])}"
        ),
        (
            "min / median / max ground_width_m: "
            f"{number_summary([row['ground_width_m'] for row in footprint_rows])}"
        ),
        (
            "min / median / max ground_height_m: "
            f"{number_summary([row['ground_height_m'] for row in footprint_rows])}"
        ),
        (
            "min / median / max footprint_area_m2: "
            f"{number_summary([row['footprint_area_m2'] for row in footprint_rows])}"
        ),
        (
            "min / median / max gsd_x_m_per_px: "
            f"{number_summary([row['gsd_x_m_per_px'] for row in footprint_rows])}"
        ),
        (
            "min / median / max gsd_y_m_per_px: "
            f"{number_summary([row['gsd_y_m_per_px'] for row in footprint_rows])}"
        ),
        "",
        f"output CSV path: {relative_posix(output_csv)}",
        f"output GeoJSON path: {relative_posix(output_geojson)}",
        f"output preview figure path: {relative_posix(output_figure)}",
    ]
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    if not check_dependencies():
        return 1

    from pyproj import Transformer

    root = project_root()
    input_csv = root / INPUT_CSV_NAME
    output_csv = root / OUTPUT_CSV_NAME
    output_geojson = root / OUTPUT_GEOJSON_NAME
    summary_txt = root / SUMMARY_TXT_NAME
    preview_figure = root / PREVIEW_FIGURE_NAME

    print(f"Input metadata CSV: {relative_posix(input_csv)}")
    try:
        metadata_df = load_metadata(input_csv)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    hkust_thermal_df, thermal_rows_found, garden_rows_excluded = (
        filter_thermal_hkust_records(metadata_df)
    )
    print(f"Total metadata rows read: {len(metadata_df)}")
    print(f"Thermal image rows found: {thermal_rows_found}")
    print(f"Garden Hill rows excluded: {garden_rows_excluded}")
    print(f"Thermal rows after Garden Hill exclusion: {len(hkust_thermal_df)}")

    transformer_to_2326 = Transformer.from_crs("EPSG:4326", "EPSG:2326", always_xy=True)
    transformer_to_4326 = Transformer.from_crs("EPSG:2326", "EPSG:4326", always_xy=True)

    footprint_rows: list[dict[str, Any]] = []
    rows_with_required_metadata = 0
    skipped_missing_gps = 0
    skipped_missing_relative_altitude = 0
    skipped_missing_image_size = 0

    for _, row in hkust_thermal_df.iterrows():
        has_required, missing_flags = required_metadata_status(row)
        if not has_required:
            if "missing_gps" in missing_flags:
                skipped_missing_gps += 1
            if "missing_relative_altitude" in missing_flags:
                skipped_missing_relative_altitude += 1
            if "missing_image_size" in missing_flags:
                skipped_missing_image_size += 1
            continue

        rows_with_required_metadata += 1
        footprint_rows.append(
            estimate_footprint_for_row(row, transformer_to_2326, transformer_to_4326)
        )

    print(f"Rows with required metadata: {rows_with_required_metadata}")
    print(f"Number of footprints created: {len(footprint_rows)}")

    write_csv(footprint_rows, output_csv)
    gdf = build_geodataframe(footprint_rows)
    write_geojson(gdf, footprint_rows, output_geojson)
    write_preview_figure(footprint_rows, preview_figure)
    write_summary(
        summary_path=summary_txt,
        total_metadata_rows=len(metadata_df),
        thermal_rows_found=thermal_rows_found,
        garden_rows_excluded=garden_rows_excluded,
        thermal_rows_after_exclusion=len(hkust_thermal_df),
        rows_with_required_metadata=rows_with_required_metadata,
        skipped_missing_gps=skipped_missing_gps,
        skipped_missing_relative_altitude=skipped_missing_relative_altitude,
        skipped_missing_image_size=skipped_missing_image_size,
        footprint_rows=footprint_rows,
        output_csv=output_csv,
        output_geojson=output_geojson,
        output_figure=preview_figure,
    )

    print(f"Output CSV path: {relative_posix(output_csv)}")
    print(f"Output GeoJSON path: {relative_posix(output_geojson)}")
    print(f"Output preview figure path: {relative_posix(preview_figure)}")
    print(f"Summary text path: {relative_posix(summary_txt)}")
    print()
    print("Next suggested command:")
    print(r"python scripts\03_estimate_thermal_footprints.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
