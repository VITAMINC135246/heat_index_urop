#!/usr/bin/env python3
"""Shared helpers for provisional Part E delta-T analysis.

Part E deliberately consumes existing Part C and Part D outputs. It does not
rerun DJI temperature extraction, change radiometric parameters, or train any
prediction model.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PILOT_PAIRS_XLSX = PROJECT_ROOT / "data" / "metadata" / "part_b_pilot_pairs.xlsx"
DJI_METADATA_XLSX = PROJECT_ROOT / "data" / "metadata" / "dji_image_metadata.xlsx"
FOOTPRINTS_XLSX = PROJECT_ROOT / "data" / "processed" / "footprints" / "image_footprints.xlsx"
GRID_XLSX = PROJECT_ROOT / "data" / "processed" / "grids" / "pilot_luhk_aligned_10m_grid_cells.xlsx"
MASK_MANIFEST_XLSX = PROJECT_ROOT / "outputs" / "part_c" / "summaries" / "part_c_final_mask_manifest.xlsx"
PART_C_COMBINED_XLSX = PROJECT_ROOT / "outputs" / "part_c" / "summaries" / "part_c_luhk_surface_cover_combined_summary.xlsx"
CLASS_MAPPING_XLSX = PROJECT_ROOT / "data" / "annotations" / "part_c" / "surface_cover_class_mapping.xlsx"
SHADOW_MAPPING_XLSX = PROJECT_ROOT / "data" / "annotations" / "part_c" / "shadow_flag_mapping.xlsx"
PART_D_SUMMARY_CSV = (
    PROJECT_ROOT
    / "outputs"
    / "part_d"
    / "summaries"
    / "part_d_tat3_parameter_temperature_extraction_summary.csv"
)
PART_D_SUBZERO_CSV = (
    PROJECT_ROOT
    / "outputs"
    / "part_d"
    / "qa"
    / "subzero_spatial_qa"
    / "summary"
    / "part_d_tat3_parameter_subzero_spatial_qa_summary.csv"
)
PART_D_TAT3_PILOT_PARAMS_CSV = (
    PROJECT_ROOT
    / "outputs"
    / "part_d"
    / "qa"
    / "tat3_parameter_audit"
    / "part_d_tat3_pilot_parameters.csv"
)

PART_E_ROOT = PROJECT_ROOT / "outputs" / "part_e"
PART_E_TABLE_DIR = PART_E_ROOT / "tables"
PART_E_FIGURE_DIR = PART_E_ROOT / "figures"
PART_E_SUMMARY_DIR = PART_E_ROOT / "summaries"

AMBIENT_MANIFEST = PROJECT_ROOT / "data" / "metadata" / "part_e_pilot_ambient_temperature_manifest.csv"
AMBIENT_TEMPLATE = PROJECT_ROOT / "data" / "metadata" / "part_e_pilot_ambient_temperature_manifest_template.csv"

PROVISIONAL_NOTICE = (
    "This is a provisional pilot delta-T analysis using temperature matrices "
    "extracted with per-image TAT3 parameters and reviewed with structural "
    "sub-zero QA. Apparent-temperature extrema still require physical "
    "plausibility review."
)

EXPECTED_THERMAL_SHAPE = (512, 640)
LUHK_GRID_SIZE_M = 10.0
LUHK_KEY_MULTIPLIER = 1_000_000

AMBIENT_COLUMNS = [
    "image_id",
    "acquisition_datetime",
    "ambient_temperature_c",
    "ambient_source",
    "ambient_source_id",
    "ambient_observation_datetime",
    "ambient_time_difference_minutes",
    "ambient_matching_method",
    "ambient_qa_status",
    "ambient_notes",
]

MISSING_AMBIENT_STATUSES = {
    "",
    "missing",
    "missing_external_record",
    "needs_input",
    "not_selected",
    "not_selected_missing_source",
    "ambiguous",
    "unmatched",
    "fail",
    "failed",
    "placeholder",
    "template",
}

NON_ANALYSIS_COVER_CLASS_NAMES = {
    "no_data_unreviewed",
    "unclear_ignore",
    "unknown",
    "unclassified",
    "invalid",
    "outside_roi",
}


class AmbientInputError(RuntimeError):
    """Raised when exactly one documented ambient value is unavailable."""


@dataclass(frozen=True)
class PixelCellMapping:
    cell_index: np.ndarray
    cells: pd.DataFrame
    mapped_pixel_count: int
    unmapped_pixel_count: int
    origin_x_2326: float
    origin_y_2326: float


def relative_posix(path: Path | str) -> str:
    work = Path(path)
    try:
        return work.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return work.as_posix()


def resolve_project_path(path_text: Any) -> Path:
    path = Path(str(path_text))
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def write_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def write_markdown(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def clean_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    return number


def round_float(value: Any, digits: int = 6) -> float | str:
    if value is None:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(number):
        return ""
    return round(number, digits)


def truthy(value: Any) -> bool:
    return str(value).strip().casefold() in {"1", "1.0", "true", "yes", "y"}


def safe_name(value: Any) -> str:
    text = str(value)
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_") or "value"


def image_id_from_name(image_name: Any) -> str:
    stem = Path(str(image_name)).stem
    if stem.endswith("_T") or stem.endswith("_V"):
        return stem[:-2]
    return stem


def flight_id_from_pair_id(pair_id: Any) -> str:
    left = str(pair_id).replace("\\", "/").split("::", 1)[0]
    return left.rstrip("/").split("/")[-1]


def read_required_excel(path: Path, label: str, dtype: Any = str) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Missing {label}: {relative_posix(path)}")
    return pd.read_excel(path, dtype=dtype).fillna("")


def read_required_csv(path: Path, label: str, dtype: Any = str) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Missing {label}: {relative_posix(path)}")
    return pd.read_csv(path, dtype=dtype, keep_default_na=False).fillna("")


def load_pilot_pairs() -> pd.DataFrame:
    df = read_required_excel(PILOT_PAIRS_XLSX, "Part B pilot pairs")
    required = {"pair_id", "image_id", "t_path", "t_image_width", "t_image_height"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Part B pilot pairs table is missing columns: {sorted(missing)}")
    return df.copy()


def load_thermal_metadata() -> pd.DataFrame:
    meta = read_required_excel(DJI_METADATA_XLSX, "DJI image metadata")
    required = {"image_name", "image_type", "pair_id", "capture_datetime"}
    missing = required - set(meta.columns)
    if missing:
        raise ValueError(f"DJI metadata table is missing columns: {sorted(missing)}")
    thermal = meta.loc[meta["image_type"].astype(str).str.casefold().eq("thermal")].copy()
    thermal["image_id"] = thermal["image_name"].map(image_id_from_name)
    keep = [
        "image_id",
        "pair_id",
        "capture_datetime",
        "gps_latitude",
        "gps_longitude",
        "camera_model",
        "image_width",
        "image_height",
        "atmospheric_temperature",
        "relative_humidity",
        "emissivity",
        "object_distance",
        "reflected_apparent_temperature",
    ]
    for column in keep:
        if column not in thermal.columns:
            thermal[column] = ""
    return thermal[keep]


def load_footprints() -> pd.DataFrame:
    df = read_required_excel(FOOTPRINTS_XLSX, "image footprints")
    required = {
        "pair_id",
        "image_type",
        "status",
        "image_width",
        "image_height",
        "min_x_2326",
        "max_x_2326",
        "min_y_2326",
        "max_y_2326",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Footprint table is missing columns: {sorted(missing)}")
    return df


def load_thermal_grid_cells() -> pd.DataFrame:
    df = read_required_excel(GRID_XLSX, "LUHK-aligned 10 m grid cells", dtype=None)
    required = {
        "pair_id",
        "global_cell_id",
        "luhk_row",
        "luhk_col",
        "cell_min_x_2326",
        "cell_max_x_2326",
        "cell_min_y_2326",
        "cell_max_y_2326",
        "cell_center_x_2326",
        "cell_center_y_2326",
        "luhk_raw_code",
        "luhk_category_name",
        "thermal_coverage_ratio",
        "is_thermal_covered",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Grid table is missing columns: {sorted(missing)}")
    df = df.copy()
    df["is_thermal_covered_bool"] = df["is_thermal_covered"].map(truthy)
    return df


def load_class_mapping() -> dict[int, str]:
    df = read_required_excel(CLASS_MAPPING_XLSX, "Part C physical surface-cover mapping")
    names: dict[int, str] = {}
    for _, row in df.iterrows():
        class_id = clean_float(row.get("class_id"))
        if class_id is None:
            continue
        names[int(class_id)] = str(row.get("class_name", "")).strip() or f"class_{int(class_id)}"
    return names


def load_shadow_mapping() -> dict[int, str]:
    df = read_required_excel(SHADOW_MAPPING_XLSX, "Part C shadow flag mapping")
    names: dict[int, str] = {}
    for _, row in df.iterrows():
        flag = clean_float(row.get("shadow_flag"))
        if flag is None:
            continue
        names[int(flag)] = str(row.get("shadow_name", "")).strip() or f"shadow_{int(flag)}"
    return names


def load_image_records() -> pd.DataFrame:
    pairs = load_pilot_pairs()
    metadata = load_thermal_metadata()
    mask_manifest = read_required_excel(MASK_MANIFEST_XLSX, "Part C final mask manifest")
    part_c = read_required_excel(PART_C_COMBINED_XLSX, "Part C combined summary")
    part_d = read_required_csv(PART_D_SUMMARY_CSV, "Part D TAT3-parameter temperature summary")
    subzero = read_required_csv(PART_D_SUBZERO_CSV, "Part D TAT3-parameter sub-zero summary")

    records = pairs.merge(metadata.drop(columns=["pair_id"]), on="image_id", how="left", validate="one_to_one")
    records = records.merge(mask_manifest, on=["pair_id", "image_id"], how="left", validate="one_to_one")
    part_c_status = part_c[
        [
            "pair_id",
            "image_id",
            "dominant_luhk_class",
            "alignment_quality",
            "manual_review_status",
            "usable_for_part_d",
        ]
    ].rename(columns={"usable_for_part_d": "part_c_usable_for_part_d"})
    records = records.merge(
        part_c_status,
        on=["pair_id", "image_id"],
        how="left",
        validate="one_to_one",
    )
    records = records.merge(
        part_d[
            [
                "image_id",
                "validation_status",
                "validation_flags",
                "ambient_temperature_c",
                "reflected_temperature_c",
                "emissivity",
                "relative_humidity_percent",
                "humidity_use_status",
                "tat3_report_capture_datetime",
                "tat3_parameter_source_report",
                "npy_path",
                "metadata_json_path",
                "temperature_shape",
                "aligns_with_part_c_masks",
            ]
        ],
        on="image_id",
        how="left",
        validate="one_to_one",
    )
    records = records.merge(
        subzero[["image_id", "qa_status", "qa_notes", "below_0_pixel_count", "below_minus_10_pixel_count"]],
        on="image_id",
        how="left",
        validate="one_to_one",
        suffixes=("", "_subzero"),
    )
    records["acquisition_datetime"] = records["capture_datetime"]
    records["flight_id"] = records["pair_id"].map(flight_id_from_pair_id)
    records["part_c_qa_status"] = records.apply(part_c_qa_status, axis=1)
    records["part_d_qa_status"] = records.apply(part_d_qa_status, axis=1)
    return records


def part_c_qa_status(row: pd.Series) -> str:
    usable = str(row.get("part_c_usable_for_part_d", "")).strip().casefold()
    alignment = str(row.get("alignment_quality", "")).strip().casefold()
    reviewed = str(row.get("manual_review_status", "")).strip().casefold()
    if usable == "yes" and alignment == "acceptable" and reviewed == "all_reviewed":
        return "pass"
    if usable:
        return "warn"
    return "missing"


def part_d_qa_status(row: pd.Series) -> str:
    statuses = [
        str(row.get("validation_status", "")).strip().casefold(),
        str(row.get("qa_status", "")).strip().casefold(),
    ]
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    if all(status == "pass" for status in statuses if status):
        return "pass"
    return "missing"


def load_ambient_manifest(path: Path = AMBIENT_MANIFEST) -> pd.DataFrame:
    if not path.is_file():
        raise AmbientInputError(
            "Ambient-temperature manifest is missing. Run "
            "`scripts/part_e/00_create_ambient_temperature_manifest_template.py` "
            "and fill one documented ambient_temperature_c per image."
        )
    df = pd.read_csv(path, dtype=str, keep_default_na=False).fillna("")
    missing_columns = [column for column in AMBIENT_COLUMNS if column not in df.columns]
    if missing_columns:
        raise AmbientInputError(
            f"Ambient manifest is missing required columns: {', '.join(missing_columns)}"
        )
    return df[AMBIENT_COLUMNS].copy()


def validate_ambient_manifest(pilot_image_ids: list[str], path: Path = AMBIENT_MANIFEST) -> pd.DataFrame:
    df = load_ambient_manifest(path)
    image_ids = set(pilot_image_ids)
    manifest_ids = set(df["image_id"].astype(str))
    missing_rows = sorted(image_ids - manifest_ids)
    extra_rows = sorted(manifest_ids - image_ids)
    duplicate_ids = sorted(df.loc[df["image_id"].duplicated(), "image_id"].astype(str).unique())
    problems: list[str] = []
    if missing_rows:
        problems.append("missing manifest rows for: " + ", ".join(missing_rows))
    if extra_rows:
        problems.append("manifest contains non-pilot image rows: " + ", ".join(extra_rows))
    if duplicate_ids:
        problems.append("duplicate image_id rows: " + ", ".join(duplicate_ids))

    checked_rows = []
    for _, row in df.iterrows():
        image_id = str(row["image_id"])
        if image_id not in image_ids:
            continue
        ambient = clean_float(row["ambient_temperature_c"])
        status = str(row["ambient_qa_status"]).strip().casefold()
        source = str(row["ambient_source"]).strip()
        method = str(row["ambient_matching_method"]).strip()
        if ambient is None:
            problems.append(f"{image_id} has no numeric ambient_temperature_c")
        if status in MISSING_AMBIENT_STATUSES:
            problems.append(f"{image_id} ambient_qa_status is `{row['ambient_qa_status']}`")
        if not source:
            problems.append(f"{image_id} has blank ambient_source")
        if not method:
            problems.append(f"{image_id} has blank ambient_matching_method")
        checked_rows.append(row)

    if problems:
        unique = []
        for problem in problems:
            if problem not in unique:
                unique.append(problem)
        raise AmbientInputError("Ambient-temperature input is not ready: " + "; ".join(unique))

    selected = pd.DataFrame(checked_rows).copy()
    selected["ambient_temperature_c"] = selected["ambient_temperature_c"].astype(float)
    return selected


def thermal_footprint_for_pair(footprints: pd.DataFrame, pair_id: str) -> pd.Series:
    rows = footprints.loc[
        footprints["pair_id"].astype(str).eq(str(pair_id))
        & footprints["image_type"].astype(str).str.casefold().eq("thermal")
        & footprints["status"].astype(str).str.casefold().eq("ok")
    ]
    if rows.empty:
        raise ValueError(f"No valid thermal footprint found for pair_id: {pair_id}")
    return rows.iloc[0]


def load_temperature_matrix(record: pd.Series) -> np.ndarray:
    path = resolve_project_path(record["npy_path"])
    if not path.is_file():
        raise FileNotFoundError(f"Missing temperature matrix: {relative_posix(path)}")
    matrix = np.load(path)
    if matrix.shape != EXPECTED_THERMAL_SHAPE:
        raise ValueError(f"{record['image_id']} temperature matrix shape {matrix.shape}, expected {EXPECTED_THERMAL_SHAPE}")
    return matrix


def load_part_c_masks(record: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    class_path = resolve_project_path(record["class_mask_thermal_grid_npy_path"])
    shadow_path = resolve_project_path(record["shadow_mask_thermal_grid_npy_path"])
    if not class_path.is_file():
        raise FileNotFoundError(f"Missing physical surface-cover mask: {relative_posix(class_path)}")
    if not shadow_path.is_file():
        raise FileNotFoundError(f"Missing shadow mask: {relative_posix(shadow_path)}")
    class_mask = np.load(class_path)
    shadow_mask = np.load(shadow_path)
    if class_mask.shape != EXPECTED_THERMAL_SHAPE:
        raise ValueError(f"{record['image_id']} class mask shape {class_mask.shape}, expected {EXPECTED_THERMAL_SHAPE}")
    if shadow_mask.shape != EXPECTED_THERMAL_SHAPE:
        raise ValueError(f"{record['image_id']} shadow mask shape {shadow_mask.shape}, expected {EXPECTED_THERMAL_SHAPE}")
    return class_mask, shadow_mask


def build_pixel_cell_mapping(
    grid: pd.DataFrame,
    footprints: pd.DataFrame,
    pair_id: str,
    image_shape: tuple[int, int] = EXPECTED_THERMAL_SHAPE,
) -> PixelCellMapping:
    cells = grid.loc[
        grid["pair_id"].astype(str).eq(str(pair_id)) & grid["is_thermal_covered_bool"]
    ].copy()
    if cells.empty:
        raise ValueError(f"No thermal-covered LUHK cells found for pair_id: {pair_id}")
    if cells.duplicated(["pair_id", "global_cell_id"]).any():
        duplicated = cells.loc[cells.duplicated(["pair_id", "global_cell_id"]), "global_cell_id"].tolist()
        raise ValueError(f"Duplicate pair_id + global_cell_id values found: {duplicated[:5]}")

    footprint = thermal_footprint_for_pair(footprints, pair_id)
    height, width = image_shape
    min_x = float(footprint["min_x_2326"])
    max_x = float(footprint["max_x_2326"])
    min_y = float(footprint["min_y_2326"])
    max_y = float(footprint["max_y_2326"])

    origin_x = np.median(cells["cell_min_x_2326"].astype(float) - cells["luhk_col"].astype(float) * LUHK_GRID_SIZE_M)
    origin_y = np.median(cells["cell_max_y_2326"].astype(float) + cells["luhk_row"].astype(float) * LUHK_GRID_SIZE_M)

    x_centers = min_x + (np.arange(width, dtype=np.float64) + 0.5) * (max_x - min_x) / width
    y_centers = max_y - (np.arange(height, dtype=np.float64) + 0.5) * (max_y - min_y) / height
    pixel_cols = np.floor((x_centers - origin_x) / LUHK_GRID_SIZE_M).astype(np.int64)
    pixel_rows = np.floor((origin_y - y_centers) / LUHK_GRID_SIZE_M).astype(np.int64)
    row_grid, col_grid = np.meshgrid(pixel_rows, pixel_cols, indexing="ij")
    keys = row_grid * LUHK_KEY_MULTIPLIER + col_grid

    cells = cells.reset_index(drop=True)
    cell_keys = (
        cells["luhk_row"].astype(np.int64).to_numpy() * LUHK_KEY_MULTIPLIER
        + cells["luhk_col"].astype(np.int64).to_numpy()
    )
    key_to_index = {int(key): index for index, key in enumerate(cell_keys.tolist())}
    unique_keys, inverse = np.unique(keys, return_inverse=True)
    unique_indices = np.array([key_to_index.get(int(key), -1) for key in unique_keys], dtype=np.int32)
    cell_index = unique_indices[inverse].reshape(image_shape)
    mapped = int((cell_index >= 0).sum())
    return PixelCellMapping(
        cell_index=cell_index,
        cells=cells,
        mapped_pixel_count=mapped,
        unmapped_pixel_count=int(cell_index.size - mapped),
        origin_x_2326=float(origin_x),
        origin_y_2326=float(origin_y),
    )


def values_stats(values: np.ndarray) -> dict[str, float | str]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {
            "mean": "",
            "median": "",
            "std": "",
            "min": "",
            "max": "",
            "p01": "",
            "p99": "",
        }
    std = float(np.std(finite, ddof=1)) if finite.size > 1 else 0.0
    return {
        "mean": round_float(np.mean(finite)),
        "median": round_float(np.median(finite)),
        "std": round_float(std),
        "min": round_float(np.min(finite)),
        "max": round_float(np.max(finite)),
        "p01": round_float(np.percentile(finite, 1)),
        "p99": round_float(np.percentile(finite, 99)),
    }


def class_name(class_id: int, class_names: dict[int, str]) -> str:
    return class_names.get(int(class_id), f"unknown_class_{int(class_id)}")


def is_analysis_cover_class(class_id: int, class_names: dict[int, str]) -> bool:
    name = class_name(class_id, class_names).strip().casefold()
    return name not in NON_ANALYSIS_COVER_CLASS_NAMES


def qa_warning_flag(*statuses: Any) -> int:
    texts = [str(status).strip().casefold() for status in statuses]
    return int(any(status in {"warn", "fail", "missing"} for status in texts))


def read_dataset(path: Path, label: str) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Missing {label}: {relative_posix(path)}")
    return pd.read_csv(path, keep_default_na=False)
