#!/usr/bin/env python3
"""Create visible, thermal, common-cell, and map overlays for pilot V/T pairs."""

from __future__ import annotations

import importlib.util
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

from table_io import read_table


GRID_XLSX_NAME = Path("data") / "processed" / "grids" / "pilot_luhk_aligned_10m_grid_cells.xlsx"
FOOTPRINTS_XLSX_NAME = Path("data") / "processed" / "footprints" / "image_footprints.xlsx"
OUTPUT_DIR_NAME = Path("outputs") / "figures" / "pilot_landuse_overlays"
OUTPUT_SUMMARY_NAME = Path("outputs") / "reports" / "05_assign_luhk_landuse_pilot_overlays_summary.txt"
OUTPUT_GEOJSON_NAME = Path("outputs") / "geodata" / "pilot_luhk_landuse_overlay_cells.geojson"

REQUIRED_PACKAGES = ["pandas", "matplotlib", "PIL", "pyproj"]

CATEGORY_COLORS = {
    0: "#1f77b4",
    1: "#ff7f0e",
    2: "#9467bd",
    3: "#d62728",
    4: "#8c564b",
    5: "#c49c94",
    6: "#f7b6d2",
    7: "#bdbdbd",
    8: "#7f7f7f",
    9: "#17becf",
}

CATEGORY_LABELS = {
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


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


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


def safe_stem(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(value).stem).strip("_") or "image"


def check_dependencies() -> bool:
    missing = [package for package in REQUIRED_PACKAGES if importlib.util.find_spec(package) is None]
    if not missing:
        return True
    print("Missing required Python packages: " + ", ".join(missing), file=sys.stderr)
    return False


def footprint_for_pair(footprints_df: Any, pair_id: str, image_type: str) -> Any:
    rows = footprints_df.loc[
        footprints_df["pair_id"].astype(str).eq(str(pair_id))
        & footprints_df["image_type"].astype(str).str.casefold().eq(image_type)
        & footprints_df["status"].astype(str).str.casefold().eq("ok")
    ]
    if rows.empty:
        raise ValueError(f"No valid {image_type} footprint for pair {pair_id}")
    return rows.iloc[0]


def category_color(value: Any) -> str:
    try:
        code = int(float(value))
    except (TypeError, ValueError):
        return "#eeeeee"
    return CATEGORY_COLORS.get(code, "#eeeeee")


def category_code(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def used_category_handles(rows: Any) -> list[Any]:
    import matplotlib.patches as mpatches

    codes = sorted(
        {
            code
            for code in (category_code(value) for value in rows.get("luhk_category_code", []))
            if code is not None
        }
    )
    return [
        mpatches.Patch(
            facecolor=CATEGORY_COLORS.get(code, "#eeeeee"),
            edgecolor="black",
            label=CATEGORY_LABELS.get(code, f"LUHK category {code}"),
            alpha=0.55,
        )
        for code in codes
    ]


def rect_from_footprint(footprint: Any) -> tuple[float, float, float, float]:
    return (
        float(footprint["min_x_2326"]),
        float(footprint["max_x_2326"]),
        float(footprint["min_y_2326"]),
        float(footprint["max_y_2326"]),
    )


def map_x_to_pixel(x: float, min_x: float, max_x: float, image_width: int) -> float:
    return (x - min_x) / (max_x - min_x) * image_width


def map_y_to_pixel(y: float, min_y: float, max_y: float, image_height: int) -> float:
    return (max_y - y) / (max_y - min_y) * image_height


def rows_for_overlay(grid_df: Any, pair_id: str, image_type: str, common_only: bool = False) -> Any:
    rows = grid_df.loc[grid_df["pair_id"].astype(str).eq(str(pair_id))].copy()
    if common_only:
        return rows.loc[rows["is_common_vt_cell"].astype(bool)]
    if image_type == "visible":
        return rows.loc[rows["is_visible_covered"].astype(bool)]
    if image_type == "thermal":
        return rows.loc[rows["is_thermal_covered"].astype(bool)]
    return rows


def plot_image_overlay(rows: Any, footprint: Any, image_path: Path, output_path: Path, title: str, common_only: bool = False) -> None:
    import matplotlib.patches as patches
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from PIL import Image, ImageOps

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = ImageOps.exif_transpose(Image.open(image_path))
    image_width, image_height = image.size
    min_x, max_x, min_y, max_y = rect_from_footprint(footprint)

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.imshow(image)
    for _, row in rows.iterrows():
        px_min = map_x_to_pixel(float(row["cell_min_x_2326"]), min_x, max_x, image_width)
        px_max = map_x_to_pixel(float(row["cell_max_x_2326"]), min_x, max_x, image_width)
        py_min = map_y_to_pixel(float(row["cell_max_y_2326"]), min_y, max_y, image_height)
        py_max = map_y_to_pixel(float(row["cell_min_y_2326"]), min_y, max_y, image_height)
        width = px_max - px_min
        height = py_max - py_min
        if width <= 0 or height <= 0:
            continue
        color = "#2ca02c" if common_only else category_color(row.get("luhk_category_code"))
        ax.add_patch(
            patches.Rectangle(
                (px_min, py_min),
                width,
                height,
                facecolor=color,
                edgecolor="black",
                linewidth=0.25,
                alpha=0.35,
            )
        )
    ax.set_xlim(0, image_width)
    ax.set_ylim(image_height, 0)
    ax.set_axis_off()
    ax.set_title(title)
    if common_only:
        handles = [
            mpatches.Patch(
                facecolor="#2ca02c",
                edgecolor="black",
                label="Common V/T LUHK cells",
                alpha=0.55,
            )
        ]
    else:
        handles = used_category_handles(rows)
    if handles:
        ax.legend(
            handles=handles,
            title="LUHK category",
            loc="center left",
            bbox_to_anchor=(1.01, 0.5),
            frameon=True,
        )
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_pair_map(rows: Any, visible_fp: Any, thermal_fp: Any, output_path: Path, pair_id: str) -> None:
    import matplotlib.patches as patches
    import matplotlib.pyplot as plt

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 7))
    for _, row in rows.iterrows():
        if bool(row["is_common_vt_cell"]):
            color = "#2ca02c"
        elif bool(row["is_visible_covered"]):
            color = "#1f77b4"
        else:
            color = "#d62728"
        ax.add_patch(
            patches.Rectangle(
                (row["cell_min_x_2326"], row["cell_min_y_2326"]),
                row["cell_max_x_2326"] - row["cell_min_x_2326"],
                row["cell_max_y_2326"] - row["cell_min_y_2326"],
                facecolor=color,
                edgecolor="black",
                linewidth=0.25,
                alpha=0.3,
            )
        )
    for footprint, color, label in ((visible_fp, "#1f77b4", "visible footprint"), (thermal_fp, "#d62728", "thermal footprint")):
        min_x, max_x, min_y, max_y = rect_from_footprint(footprint)
        ax.add_patch(
            patches.Rectangle(
                (min_x, min_y),
                max_x - min_x,
                max_y - min_y,
                fill=False,
                edgecolor=color,
                linewidth=1.6,
                label=label,
            )
        )
    ax.autoscale()
    ax.set_aspect("equal")
    ax.grid(True, linewidth=0.25, alpha=0.35)
    ax.legend(loc="best")
    ax.set_title(f"LUHK-Aligned V/T Cell Map\n{pair_id}")
    ax.set_xlabel("Easting (EPSG:2326)")
    ax.set_ylabel("Northing (EPSG:2326)")
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_pure_luhk_grid(rows: Any, footprint: Any, output_path: Path, title: str) -> None:
    import matplotlib.patches as patches
    import matplotlib.pyplot as plt

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 7))
    for _, row in rows.iterrows():
        ax.add_patch(
            patches.Rectangle(
                (row["cell_min_x_2326"], row["cell_min_y_2326"]),
                row["cell_max_x_2326"] - row["cell_min_x_2326"],
                row["cell_max_y_2326"] - row["cell_min_y_2326"],
                facecolor=category_color(row.get("luhk_category_code")),
                edgecolor="black",
                linewidth=0.25,
                alpha=0.7,
            )
        )
    min_x, max_x, min_y, max_y = rect_from_footprint(footprint)
    ax.add_patch(
        patches.Rectangle(
            (min_x, min_y),
            max_x - min_x,
            max_y - min_y,
            fill=False,
            edgecolor="black",
            linewidth=1.5,
            label="image footprint",
        )
    )
    ax.autoscale()
    ax.set_aspect("equal")
    ax.grid(True, linewidth=0.25, alpha=0.35)
    ax.set_title(title)
    ax.set_xlabel("Easting (EPSG:2326)")
    ax.set_ylabel("Northing (EPSG:2326)")
    ax.tick_params(axis="x", labelrotation=30)
    handles = used_category_handles(rows)
    handles.append(patches.Patch(facecolor="none", edgecolor="black", label="image footprint"))
    ax.legend(
        handles=handles,
        title="LUHK category",
        loc="center left",
        bbox_to_anchor=(1.01, 0.5),
        frameon=True,
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def polygon_lon_lat(row: Any, transformer_to_4326: Any) -> list[list[float]]:
    points = [
        (row["cell_min_x_2326"], row["cell_max_y_2326"]),
        (row["cell_max_x_2326"], row["cell_max_y_2326"]),
        (row["cell_max_x_2326"], row["cell_min_y_2326"]),
        (row["cell_min_x_2326"], row["cell_min_y_2326"]),
        (row["cell_min_x_2326"], row["cell_max_y_2326"]),
    ]
    return [list(transformer_to_4326.transform(float(x), float(y))) for x, y in points]


def json_ready(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    try:
        if value != value:
            return None
    except (TypeError, ValueError):
        pass
    return value


def write_geojson(grid_df: Any, output_geojson: Path) -> None:
    from pyproj import Transformer

    transformer_to_4326 = Transformer.from_crs("EPSG:2326", "EPSG:4326", always_xy=True)
    features = []
    for _, row in grid_df.iterrows():
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [polygon_lon_lat(row, transformer_to_4326)]},
                "properties": {key: json_ready(row[key]) for key in grid_df.columns},
            }
        )
    output_geojson.parent.mkdir(parents=True, exist_ok=True)
    output_geojson.write_text(json.dumps({"type": "FeatureCollection", "features": features}, indent=2), encoding="utf-8")


def main() -> int:
    if not check_dependencies():
        return 1
    root = project_root()
    grid_xlsx = root / GRID_XLSX_NAME
    footprints_xlsx = root / FOOTPRINTS_XLSX_NAME
    if not grid_xlsx.is_file():
        print(f"Error: grid XLSX not found: {relative_posix(grid_xlsx)}", file=sys.stderr)
        print("Run scripts/04_create_10m_grids_pilot.py first.", file=sys.stderr)
        return 1
    if not footprints_xlsx.is_file():
        print(f"Error: footprint XLSX not found: {relative_posix(footprints_xlsx)}", file=sys.stderr)
        return 1

    grid_df = read_table(grid_xlsx)
    footprints_df = read_table(footprints_xlsx)
    output_dir = root / OUTPUT_DIR_NAME
    generated: list[Path] = []
    summary_lines = [
        "Pilot LUHK land-use overlay summary",
        "",
        "Each pair has separate visible and thermal overlays. Visible overlays use visible geometry; thermal overlays use thermal geometry.",
        "Common-cell overlays use LUHK global_cell_id cells covered by both footprints.",
        "",
    ]

    for pair_id in sorted(grid_df["pair_id"].astype(str).unique()):
        pair_rows = grid_df.loc[grid_df["pair_id"].astype(str).eq(pair_id)]
        visible_fp = footprint_for_pair(footprints_df, pair_id, "visible")
        thermal_fp = footprint_for_pair(footprints_df, pair_id, "thermal")
        visible_path = resolve_project_path(str(visible_fp["image_path"]))
        thermal_path = resolve_project_path(str(thermal_fp["image_path"]))
        pair_dir = output_dir / safe_stem(pair_id)

        visible_overlay = pair_dir / f"{safe_stem(str(visible_fp['image_name']))}_visible_luhk_overlay.png"
        thermal_overlay = pair_dir / f"{safe_stem(str(thermal_fp['image_name']))}_thermal_luhk_overlay.png"
        common_visible_overlay = pair_dir / f"{safe_stem(str(visible_fp['image_name']))}_common_vt_cells_on_visible.png"
        common_thermal_overlay = pair_dir / f"{safe_stem(str(thermal_fp['image_name']))}_common_vt_cells_on_thermal.png"
        map_overlay = pair_dir / f"{safe_stem(pair_id)}_luhk_grid_map.png"
        visible_pure_grid = pair_dir / f"{safe_stem(str(visible_fp['image_name']))}_visible_coverage_pure_luhk_grid.png"
        thermal_pure_grid = pair_dir / f"{safe_stem(str(thermal_fp['image_name']))}_thermal_coverage_pure_luhk_grid.png"

        visible_rows = rows_for_overlay(grid_df, pair_id, "visible")
        thermal_rows = rows_for_overlay(grid_df, pair_id, "thermal")
        common_rows = rows_for_overlay(grid_df, pair_id, "visible", common_only=True)

        plot_image_overlay(
            visible_rows,
            visible_fp,
            visible_path,
            visible_overlay,
            f"Visible LUHK Overlay\n{visible_fp['image_name']}",
        )
        plot_image_overlay(
            thermal_rows,
            thermal_fp,
            thermal_path,
            thermal_overlay,
            f"Thermal LUHK Overlay\n{thermal_fp['image_name']}",
        )
        plot_image_overlay(
            common_rows,
            visible_fp,
            visible_path,
            common_visible_overlay,
            f"Common V/T LUHK Cells on Visible\n{visible_fp['image_name']}",
            common_only=True,
        )
        plot_image_overlay(
            common_rows,
            thermal_fp,
            thermal_path,
            common_thermal_overlay,
            f"Common V/T LUHK Cells on Thermal\n{thermal_fp['image_name']}",
            common_only=True,
        )
        plot_pair_map(pair_rows, visible_fp, thermal_fp, map_overlay, pair_id)
        plot_pure_luhk_grid(
            visible_rows,
            visible_fp,
            visible_pure_grid,
            f"Pure LUHK Grid in Visible Coverage\n{visible_fp['image_name']}",
        )
        plot_pure_luhk_grid(
            thermal_rows,
            thermal_fp,
            thermal_pure_grid,
            f"Pure LUHK Grid in Thermal Coverage\n{thermal_fp['image_name']}",
        )
        generated.extend(
            [
                visible_overlay,
                thermal_overlay,
                common_visible_overlay,
                common_thermal_overlay,
                map_overlay,
                visible_pure_grid,
                thermal_pure_grid,
            ]
        )
        summary_lines.append(
            f"- {pair_id}: visible cells={len(visible_rows)}, thermal cells={len(thermal_rows)}, "
            f"common cells={len(common_rows)}"
        )

    write_geojson(grid_df, root / OUTPUT_GEOJSON_NAME)
    summary_lines.extend(
        [
            "",
            f"output figure folder: {relative_posix(output_dir)}",
            f"output GeoJSON path: {relative_posix(root / OUTPUT_GEOJSON_NAME)}",
            "generated figures:",
        ]
    )
    summary_lines.extend(f"- {relative_posix(path)}" for path in generated)
    summary_path = root / OUTPUT_SUMMARY_NAME
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print(f"Pilot pairs overlaid: {grid_df['pair_id'].nunique()}")
    print(f"Generated figures: {len(generated)}")
    print(f"Output figure folder: {relative_posix(output_dir)}")
    print(f"Summary text path: {relative_posix(summary_path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
