#!/usr/bin/env python3
"""Estimate separate first-pass footprints for DJI visible and thermal images."""

from __future__ import annotations

import csv
import importlib.util
import json
import math
import sys
from pathlib import Path
from statistics import median
from typing import Any

from camera_profiles import resolve_camera_parameters


VT_PAIRS_CSV_NAME = Path("data") / "metadata" / "vt_pairs.csv"
METADATA_CSV_NAME = Path("data") / "metadata" / "dji_image_metadata.csv"
OUTPUT_CSV_NAME = Path("data") / "processed" / "footprints" / "image_footprints.csv"
OUTPUT_GEOJSON_NAME = Path("outputs") / "geodata" / "image_footprints.geojson"
SUMMARY_TXT_NAME = Path("outputs") / "reports" / "03_estimate_image_footprints_summary.txt"
PREVIEW_FIGURE_NAME = Path("outputs") / "figures" / "image_footprint_preview.png"

# Compatibility outputs for older thermal-only notebooks/scripts.
THERMAL_COMPAT_CSV_NAME = Path("data") / "processed" / "footprints" / "thermal_image_footprints.csv"
THERMAL_COMPAT_GEOJSON_NAME = Path("outputs") / "geodata" / "thermal_image_footprints.geojson"

REQUIRED_PACKAGES = ["pandas", "pyproj", "PIL", "matplotlib"]

CSV_COLUMNS = [
    "pair_id",
    "image_type",
    "image_path",
    "paired_image_path",
    "image_name",
    "paired_image_name",
    "pair_status",
    "metadata_source",
    "image_width",
    "image_height",
    "gps_latitude",
    "gps_longitude",
    "center_x_2326",
    "center_y_2326",
    "altitude_used_m",
    "altitude_source",
    "focal_length_mm",
    "focal_length_35mm",
    "sensor_width_mm",
    "sensor_height_mm",
    "sensor_source",
    "horizontal_fov_deg",
    "vertical_fov_deg",
    "fov_source",
    "camera_profile_used",
    "footprint_parameter_source",
    "fallback_used",
    "aperture_ignored",
    "gimbal_yaw_degree",
    "flight_yaw_degree",
    "yaw_source",
    "yaw_heading_assumption",
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
    "status",
    "warning_message",
]


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def check_dependencies() -> bool:
    missing = [package for package in REQUIRED_PACKAGES if importlib.util.find_spec(package) is None]
    if not missing:
        return True
    print("Missing required Python packages: " + ", ".join(missing), file=sys.stderr)
    print("Install dependencies with: python3 -m pip install -r requirements.txt", file=sys.stderr)
    return False


def relative_posix(path: Path) -> str:
    try:
        return path.relative_to(project_root()).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_project_path(path_text: str) -> Path:
    path = Path(str(path_text))
    if path.is_absolute():
        return path
    return project_root() / path


def normalize_path(value: Any) -> str:
    return str(value or "").replace("\\", "/").strip().casefold()


def is_garden_hill(value: Any) -> bool:
    return "gardenhill" in str(value or "").casefold() or "garden hill" in str(value or "").casefold()


def is_hkust_pair(row: Any) -> bool:
    text = " ".join(str(row.get(column, "")) for column in ("dataset_folder", "location", "v_path", "t_path"))
    lowered = text.casefold()
    return "hkust" in lowered and "gardenhill" not in lowered


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        if value != value:
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(value, str) and value.strip() == ""


def parse_float(value: Any) -> float | None:
    if is_missing(value) or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def read_actual_image_size(image_path_text: str) -> tuple[int, int] | None:
    path = resolve_project_path(image_path_text)
    if not path.is_file():
        return None
    from PIL import Image, ImageOps

    with Image.open(path) as image:
        displayed = ImageOps.exif_transpose(image)
        return displayed.size


def load_inputs(vt_pairs_csv: Path, metadata_csv: Path) -> tuple[Any, Any]:
    import pandas as pd

    if not vt_pairs_csv.is_file():
        raise FileNotFoundError(vt_pairs_csv)
    if not metadata_csv.is_file():
        raise FileNotFoundError(metadata_csv)
    return pd.read_csv(vt_pairs_csv), pd.read_csv(metadata_csv)


def metadata_index(metadata_df: Any) -> dict[tuple[str, str], Any]:
    index: dict[tuple[str, str], Any] = {}
    for _, row in metadata_df.iterrows():
        image_type = str(row.get("image_type", "")).casefold()
        for column in ("image_path", "source_file"):
            key = normalize_path(row.get(column, ""))
            if key:
                index[(image_type, key)] = row
        image_name = str(row.get("image_name", ""))
        if image_name:
            index[(image_type, image_name.casefold())] = row
    return index


def find_metadata_row(index: dict[tuple[str, str], Any], image_type: str, image_path: str) -> Any | None:
    path_key = normalize_path(image_path)
    if (image_type, path_key) in index:
        return index[(image_type, path_key)]
    name_key = Path(image_path).name.casefold()
    return index.get((image_type, name_key))


def pair_rows(vt_pairs_df: Any, metadata_df: Any) -> list[dict[str, Any]]:
    index = metadata_index(metadata_df)
    rows: list[dict[str, Any]] = []
    for _, pair in vt_pairs_df.iterrows():
        if str(pair.get("status", "")).casefold() != "paired":
            continue
        if not is_hkust_pair(pair):
            continue
        v_path = str(pair.get("v_path", "")).strip()
        t_path = str(pair.get("t_path", "")).strip()
        if not v_path or not t_path:
            continue
        for image_type, image_path, paired_path in (
            ("visible", v_path, t_path),
            ("thermal", t_path, v_path),
        ):
            metadata_row = find_metadata_row(index, image_type, image_path)
            rows.append(
                {
                    "pair": pair,
                    "metadata_row": metadata_row,
                    "image_type": image_type,
                    "image_path": image_path,
                    "paired_image_path": paired_path,
                }
            )
    return rows


def incomplete_row(
    pair: Any,
    image_type: str,
    image_path: str,
    paired_image_path: str,
    warning: str,
    metadata_row: Any | None = None,
) -> dict[str, Any]:
    image_name = Path(image_path).name
    paired_name = Path(paired_image_path).name
    row = {column: "" for column in CSV_COLUMNS}
    row.update(
        {
            "pair_id": str(pair.get("pair_id", "")),
            "image_type": image_type,
            "image_path": image_path,
            "paired_image_path": paired_image_path,
            "image_name": image_name,
            "paired_image_name": paired_name,
            "pair_status": str(pair.get("status", "")),
            "metadata_source": relative_posix(project_root() / METADATA_CSV_NAME),
            "camera_profile_used": f"{image_type}_profile",
            "fallback_used": False,
            "aperture_ignored": True,
            "yaw_heading_assumption": "not applied; approximate north-up rectangular footprint",
            "status": "incomplete",
            "warning_message": warning,
        }
    )
    if metadata_row is not None:
        row.update(
            {
                "image_width": parse_float(metadata_row.get("image_width")),
                "image_height": parse_float(metadata_row.get("image_height")),
                "gps_latitude": parse_float(metadata_row.get("gps_latitude")),
                "gps_longitude": parse_float(metadata_row.get("gps_longitude")),
                "altitude_used_m": parse_float(metadata_row.get("relative_altitude")),
                "focal_length_mm": parse_float(metadata_row.get("focal_length")),
                "focal_length_35mm": parse_float(metadata_row.get("focal_length_35mm")),
                "gimbal_yaw_degree": parse_float(metadata_row.get("gimbal_yaw_degree")),
                "flight_yaw_degree": parse_float(metadata_row.get("flight_yaw_degree")),
            }
        )
    return row


def estimate_one_footprint(
    pair: Any,
    metadata_row: Any,
    image_type: str,
    image_path: str,
    paired_image_path: str,
    transformer_to_2326: Any,
    transformer_to_4326: Any,
) -> dict[str, Any]:
    actual_size = read_actual_image_size(image_path)
    params = resolve_camera_parameters(metadata_row, image_type, actual_size)
    warnings = list(params.get("warnings") or [])

    required_missing: list[str] = []
    center_lat = params["center_lat"]
    center_lon = params["center_lon"]
    altitude = params["relative_altitude_m"]
    horizontal_fov = params["horizontal_fov_deg"]
    vertical_fov = params["vertical_fov_deg"]
    image_width = params["image_width_px"]
    image_height = params["image_height_px"]
    for name, value in (
        ("gps_latitude", center_lat),
        ("gps_longitude", center_lon),
        ("relative_altitude", altitude),
        ("horizontal_fov_deg", horizontal_fov),
        ("vertical_fov_deg", vertical_fov),
        ("image_width", image_width),
        ("image_height", image_height),
    ):
        if parse_float(value) is None:
            required_missing.append(name)
    if altitude is not None and altitude <= 0:
        required_missing.append("positive_relative_altitude")

    if required_missing:
        message = "missing or invalid required footprint metadata: " + ", ".join(required_missing)
        if warnings:
            message += "; " + "; ".join(warnings)
        return incomplete_row(pair, image_type, image_path, paired_image_path, message, metadata_row)

    ground_width = 2.0 * altitude * math.tan(math.radians(horizontal_fov) / 2.0)
    ground_height = 2.0 * altitude * math.tan(math.radians(vertical_fov) / 2.0)
    center_x, center_y = transformer_to_2326.transform(center_lon, center_lat)
    min_x = center_x - ground_width / 2.0
    max_x = center_x + ground_width / 2.0
    min_y = center_y - ground_height / 2.0
    max_y = center_y + ground_height / 2.0
    corners_2326 = {
        "nw": (min_x, max_y),
        "ne": (max_x, max_y),
        "se": (max_x, min_y),
        "sw": (min_x, min_y),
    }
    corners_4326 = {name: transformer_to_4326.transform(x, y) for name, (x, y) in corners_2326.items()}

    row = {column: "" for column in CSV_COLUMNS}
    row.update(
        {
            "pair_id": str(pair.get("pair_id", "")),
            "image_type": image_type,
            "image_path": image_path,
            "paired_image_path": paired_image_path,
            "image_name": str(metadata_row.get("image_name", Path(image_path).name)),
            "paired_image_name": Path(paired_image_path).name,
            "pair_status": str(pair.get("status", "")),
            "metadata_source": relative_posix(project_root() / METADATA_CSV_NAME),
            "image_width": image_width,
            "image_height": image_height,
            "gps_latitude": center_lat,
            "gps_longitude": center_lon,
            "center_x_2326": center_x,
            "center_y_2326": center_y,
            "altitude_used_m": altitude,
            "altitude_source": params["altitude_source"],
            "focal_length_mm": params["focal_length_mm"],
            "focal_length_35mm": params["focal_length_35mm"],
            "sensor_width_mm": params["sensor_width_mm"],
            "sensor_height_mm": params["sensor_height_mm"],
            "sensor_source": params["sensor_source"],
            "horizontal_fov_deg": horizontal_fov,
            "vertical_fov_deg": vertical_fov,
            "fov_source": params["fov_source"],
            "camera_profile_used": params["camera_profile_used"],
            "footprint_parameter_source": params["parameter_source"],
            "fallback_used": bool(params["fallback_used"]),
            "aperture_ignored": True,
            "gimbal_yaw_degree": params["gimbal_yaw_degree"],
            "flight_yaw_degree": params["flight_yaw_degree"],
            "yaw_source": params["yaw_source"],
            "yaw_heading_assumption": params["yaw_assumption"],
            "ground_width_m": ground_width,
            "ground_height_m": ground_height,
            "footprint_area_m2": ground_width * ground_height,
            "gsd_x_m_per_px": ground_width / image_width,
            "gsd_y_m_per_px": ground_height / image_height,
            "min_x_2326": min_x,
            "max_x_2326": max_x,
            "min_y_2326": min_y,
            "max_y_2326": max_y,
            "status": "ok",
            "warning_message": "; ".join(warnings),
        }
    )
    for name, (x, y) in corners_2326.items():
        row[f"{name}_x_2326"] = x
        row[f"{name}_y_2326"] = y
    for name, (lon, lat) in corners_4326.items():
        row[f"{name}_lat"] = lat
        row[f"{name}_lon"] = lon
    return row


def write_csv_rows(rows: list[dict[str, Any]], output_csv: Path) -> None:
    import pandas as pd

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    for column in CSV_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    df[CSV_COLUMNS].to_csv(output_csv, index=False)


def polygon_lon_lat(row: dict[str, Any]) -> list[list[float]]:
    return [
        [row["nw_lon"], row["nw_lat"]],
        [row["ne_lon"], row["ne_lat"]],
        [row["se_lon"], row["se_lat"]],
        [row["sw_lon"], row["sw_lat"]],
        [row["nw_lon"], row["nw_lat"]],
    ]


def json_ready(value: Any) -> Any:
    if value is None:
        return None
    try:
        if value != value:
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    return value


def write_geojson(rows: list[dict[str, Any]], output_geojson: Path) -> None:
    output_geojson.parent.mkdir(parents=True, exist_ok=True)
    features = []
    for row in rows:
        if row.get("status") != "ok":
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [polygon_lon_lat(row)]},
                "properties": {key: json_ready(value) for key, value in row.items() if key in CSV_COLUMNS},
            }
        )
    output_geojson.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, indent=2),
        encoding="utf-8",
    )


def write_preview(rows: list[dict[str, Any]], output_figure: Path) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    output_figure.parent.mkdir(parents=True, exist_ok=True)
    ok_rows = [row for row in rows if row.get("status") == "ok"]
    fig, ax = plt.subplots(figsize=(9, 7))
    if not ok_rows:
        ax.text(0.5, 0.5, "No valid image footprints", ha="center", va="center")
        ax.set_axis_off()
    else:
        colors = {"visible": "#1f77b4", "thermal": "#d62728"}
        for row in ok_rows:
            min_x = float(row["min_x_2326"])
            min_y = float(row["min_y_2326"])
            width = float(row["max_x_2326"]) - min_x
            height = float(row["max_y_2326"]) - min_y
            ax.add_patch(
                Rectangle(
                    (min_x, min_y),
                    width,
                    height,
                    fill=False,
                    edgecolor=colors.get(str(row["image_type"]), "black"),
                    linewidth=1.0,
                    alpha=0.7,
                )
            )
        ax.autoscale()
        ax.set_aspect("equal")
        ax.grid(True, linewidth=0.25, alpha=0.35)
        ax.set_xlabel("Easting (EPSG:2326)")
        ax.set_ylabel("Northing (EPSG:2326)")
        ax.set_title("Visible and Thermal Footprint Preview")
    fig.tight_layout()
    fig.savefig(output_figure, dpi=220, bbox_inches="tight")
    plt.close(fig)


def number_summary(values: list[float]) -> str:
    values = [value for value in values if value is not None and math.isfinite(value)]
    if not values:
        return "n/a"
    return f"min={min(values):.3f}, median={median(values):.3f}, max={max(values):.3f}"


def write_summary(rows: list[dict[str, Any]], summary_txt: Path) -> None:
    summary_txt.parent.mkdir(parents=True, exist_ok=True)
    ok_rows = [row for row in rows if row.get("status") == "ok"]
    visible_rows = [row for row in rows if row.get("image_type") == "visible"]
    thermal_rows = [row for row in rows if row.get("image_type") == "thermal"]
    lines = [
        "Image footprint estimation summary",
        "",
        f"total footprint rows written: {len(rows)}",
        f"valid footprints: {len(ok_rows)}",
        f"incomplete footprints: {len(rows) - len(ok_rows)}",
        f"visible rows: {len(visible_rows)}",
        f"thermal rows: {len(thermal_rows)}",
        f"visible rows using fallback: {sum(bool(row.get('fallback_used')) for row in visible_rows)}",
        f"thermal rows using fallback: {sum(bool(row.get('fallback_used')) for row in thermal_rows)}",
        "",
        "camera rule:",
        "- visible _V.JPG uses visible metadata only; no thermal fallback is allowed",
        "- thermal _T.JPG keeps the thermal profile fallback only when metadata cannot resolve FOV",
        "- yaw/heading is reported but not yet used; footprints are approximate north-up rectangles",
        "",
        f"valid ground_width_m: {number_summary([parse_float(row.get('ground_width_m')) for row in ok_rows])}",
        f"valid ground_height_m: {number_summary([parse_float(row.get('ground_height_m')) for row in ok_rows])}",
        "",
        f"output CSV path: {relative_posix(project_root() / OUTPUT_CSV_NAME)}",
        f"output GeoJSON path: {relative_posix(project_root() / OUTPUT_GEOJSON_NAME)}",
        f"preview figure path: {relative_posix(project_root() / PREVIEW_FIGURE_NAME)}",
    ]
    incomplete = [row for row in rows if row.get("status") != "ok"][:20]
    if incomplete:
        lines.extend(["", "first incomplete rows:"])
        for row in incomplete:
            lines.append(
                f"- {row.get('pair_id')} {row.get('image_type')} {row.get('image_name')}: "
                f"{row.get('warning_message')}"
            )
    summary_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    if not check_dependencies():
        return 1
    from pyproj import Transformer

    root = project_root()
    try:
        vt_pairs_df, metadata_df = load_inputs(root / VT_PAIRS_CSV_NAME, root / METADATA_CSV_NAME)
    except FileNotFoundError as exc:
        print(f"Error: required input not found: {exc}", file=sys.stderr)
        return 1

    transformer_to_2326 = Transformer.from_crs("EPSG:4326", "EPSG:2326", always_xy=True)
    transformer_to_4326 = Transformer.from_crs("EPSG:2326", "EPSG:4326", always_xy=True)

    rows: list[dict[str, Any]] = []
    for item in pair_rows(vt_pairs_df, metadata_df):
        metadata_row = item["metadata_row"]
        if metadata_row is None:
            rows.append(
                incomplete_row(
                    item["pair"],
                    item["image_type"],
                    item["image_path"],
                    item["paired_image_path"],
                    "no metadata row found for this paired image",
                )
            )
            continue
        rows.append(
            estimate_one_footprint(
                item["pair"],
                metadata_row,
                item["image_type"],
                item["image_path"],
                item["paired_image_path"],
                transformer_to_2326,
                transformer_to_4326,
            )
        )

    output_csv = root / OUTPUT_CSV_NAME
    output_geojson = root / OUTPUT_GEOJSON_NAME
    preview_figure = root / PREVIEW_FIGURE_NAME
    write_csv_rows(rows, output_csv)
    write_geojson(rows, output_geojson)
    write_preview(rows, preview_figure)
    write_summary(rows, root / SUMMARY_TXT_NAME)

    thermal_rows = [row for row in rows if row.get("image_type") == "thermal"]
    write_csv_rows(thermal_rows, root / THERMAL_COMPAT_CSV_NAME)
    write_geojson(thermal_rows, root / THERMAL_COMPAT_GEOJSON_NAME)

    print(f"Footprint rows written: {len(rows)}")
    print(f"Valid footprints: {sum(row.get('status') == 'ok' for row in rows)}")
    print(f"Output CSV path: {relative_posix(output_csv)}")
    print(f"Output GeoJSON path: {relative_posix(output_geojson)}")
    print(f"Summary text path: {relative_posix(root / SUMMARY_TXT_NAME)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
