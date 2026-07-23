#!/usr/bin/env python3
"""Shared utilities for the formal Part E thermal-pixel workflow.

The statistical observation is one original thermal pixel. LUHK 10 m cells and
8 px sampling tiles are retained only as label provenance or sampling strata;
no temperature value is averaged by either spatial unit.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.workflow.luhk_context import (  # noqa: E402
    LUHK_GRID_SIZE_M,
    LUHK_KEY_MULTIPLIER,
    build_native_luhk_result,
)

SAMPLE_FILES = {
    "luhk": "part_e_sample_luhk",
    "surface_cover": "part_e_sample_surface_cover",
    "luhk_surface_cover": "part_e_sample_luhk_surface_cover",
    "surface_cover_shadow": "part_e_sample_surface_cover_shadow",
    "image_comparison": "part_e_sample_image_comparison",
}

SAMPLE_COLUMNS = [
    "pixel_uid",
    "image_id",
    "flight_id",
    "capture_datetime",
    "thermal_row",
    "thermal_col",
    "pixel_x",
    "pixel_y",
    "temperature_c",
    "ambient_temperature_c",
    "delta_t_c",
    "luhk_cell_id",
    "luhk_class_code",
    "luhk_class_name",
    "luhk_label_valid",
    "surface_cover_class",
    "surface_cover_valid",
    "surface_cover_review_status",
    "shadow_flag",
    "shadow_valid",
    "measurement_type",
    "temperature_source",
    "temperature_definition",
    "temperature_unit",
    "ambient_source",
    "ambient_definition",
    "ambient_unit",
    "ambient_data_qa_status",
    "ambient_provenance",
    "ambient_source_record",
    "source_method",
    "label_provenance",
    "surface_cover_provenance",
    "luhk_provenance",
    "label_known",
    "analysis_eligible",
    "target_mask",
    "exclusion_reason",
    "target_name",
    "target_id",
    "qa_status",
    "annotation_review_status",
]


def load_config(path: Path | str) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["_config_path"] = config_path.as_posix()
    return config


def project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def relative(path: str | Path) -> str:
    target = Path(path).resolve()
    try:
        return target.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return target.as_posix()


def ensure_output_directories(config: dict[str, Any]) -> None:
    for value in config["outputs"].values():
        path = project_path(value)
        if path.suffix:
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            path.mkdir(parents=True, exist_ok=True)


def write_csv(path: str | Path, frame: pd.DataFrame) -> None:
    target = project_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False, encoding="utf-8-sig")


def write_markdown(path: str | Path, lines: Iterable[str]) -> None:
    target = project_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with project_path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_info() -> dict[str, str]:
    def run(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=PROJECT_ROOT, text=True).strip()

    return {
        "branch": run("branch", "--show-current"),
        "commit": run("rev-parse", "HEAD"),
        "commit_short": run("rev-parse", "--short", "HEAD"),
    }


def truthy(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.casefold().isin({"1", "true", "yes", "y", "ok"})


def load_source_tables(config: dict[str, Any]) -> dict[str, pd.DataFrame]:
    inputs = config["inputs"]
    tables = {
        "pairs": pd.read_excel(project_path(inputs["pilot_pairs"])),
        "metadata": pd.read_excel(project_path(inputs["image_metadata"])),
        "temperature": pd.read_csv(project_path(inputs["temperature_summary"]), keep_default_na=False),
        "ambient": pd.read_csv(project_path(inputs["ambient_manifest"]), keep_default_na=False),
        "masks": pd.read_excel(project_path(inputs["mask_manifest"])),
        "part_c_summary": pd.read_excel(project_path(inputs["part_c_combined_summary"])),
        "cover_mapping": pd.read_excel(project_path(inputs["surface_cover_mapping"])),
        "shadow_mapping": pd.read_excel(project_path(inputs["shadow_mapping"])),
        "grid": pd.read_excel(project_path(inputs["luhk_grid"])),
        "footprints": pd.read_excel(project_path(inputs["image_footprints"])),
    }
    return tables


def build_image_records(config: dict[str, Any], tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    pilot_ids = list(map(str, config["pilot_image_ids"]))
    pairs = tables["pairs"].copy()
    pairs["image_id"] = pairs["image_id"].astype(str)
    pairs = pairs.loc[pairs["image_id"].isin(pilot_ids)].copy()
    if set(pairs["image_id"]) != set(pilot_ids) or len(pairs) != len(pilot_ids):
        raise ValueError("Pilot image IDs do not map one-to-one in the Part B pilot-pairs table.")
    garden_text = pairs.astype(str).agg(" ".join, axis=1).str.contains("GardenHill", case=False, regex=False)
    if garden_text.any():
        raise ValueError("Garden Hill record found inside the formal pilot selection.")

    temperature = tables["temperature"].copy()
    temperature["image_id"] = temperature["image_id"].astype(str)
    ambient = tables["ambient"].copy()
    ambient["image_id"] = ambient["image_id"].astype(str)
    masks = tables["masks"].copy()
    masks["image_id"] = masks["image_id"].astype(str)

    for name, frame in (("temperature", temperature), ("ambient", ambient), ("mask", masks)):
        selected = frame.loc[frame["image_id"].isin(pilot_ids)]
        if len(selected) != len(pilot_ids) or selected["image_id"].nunique() != len(pilot_ids):
            raise ValueError(f"{name} records do not map one-to-one to all pilot image IDs.")

    records = pairs.merge(
        temperature[
            [
                "image_id",
                "npy_path",
                "metadata_json_path",
                "tat3_parameter_source_report",
                "ambient_temperature_c",
                "temperature_shape",
                "validation_status",
                "aligns_with_part_c_masks",
            ]
        ].rename(
            columns={
                "ambient_temperature_c": "part_d_ambient_temperature_c",
                "validation_status": "part_d_validation_status",
            }
        ),
        on="image_id",
        how="left",
        validate="one_to_one",
    )
    records = records.merge(ambient, on="image_id", how="left", validate="one_to_one")
    records = records.merge(
        masks[
            [
                "image_id",
                "pair_id",
                "class_mask_thermal_grid_npy_path",
                "shadow_mask_thermal_grid_npy_path",
                "thermal_grid_shape",
                "usable_for_part_d",
            ]
        ],
        on=["image_id", "pair_id"],
        how="left",
        validate="one_to_one",
    )
    part_c_summary = tables["part_c_summary"].copy()
    records = records.merge(
        part_c_summary[
            [
                "image_id",
                "pair_id",
                "alignment_quality",
                "manual_review_status",
                "spatial_uncertainty_notes",
            ]
        ],
        on=["image_id", "pair_id"],
        how="left",
        validate="one_to_one",
    )
    records["ambient_temperature_c"] = pd.to_numeric(records["ambient_temperature_c"], errors="coerce")
    records["part_d_ambient_temperature_c"] = pd.to_numeric(
        records["part_d_ambient_temperature_c"], errors="coerce"
    )
    if not np.isfinite(records["ambient_temperature_c"]).all():
        raise ValueError("Every pilot image must have one finite ambient temperature.")
    if not np.allclose(
        records["ambient_temperature_c"], records["part_d_ambient_temperature_c"], atol=1e-9
    ):
        raise ValueError("Formal ambient manifest does not match the Part D TAT3 parameters.")
    if not records["ambient_source"].astype(str).eq(config["ambient_source"]).all():
        raise ValueError("Formal ambient_source must be TAT3 for every image.")
    if not records["validation_status"].astype(str).eq(config["ambient_validation_status"]).all():
        raise ValueError("Formal ambient validation status must be provisional for every image.")

    records["flight_id"] = records["pair_id"].astype(str).str.split("::").str[0]
    records["capture_datetime"] = records["capture_datetime"].astype(str)
    order = {image_id: index for index, image_id in enumerate(pilot_ids)}
    records["_order"] = records["image_id"].map(order)
    return records.sort_values("_order").reset_index(drop=True)


def class_mapping(tables: dict[str, pd.DataFrame]) -> dict[int, str]:
    return {
        int(row.class_id): str(row.class_name)
        for row in tables["cover_mapping"].itertuples(index=False)
    }


def load_temperature(record: pd.Series) -> np.ndarray:
    matrix = np.load(project_path(str(record["npy_path"])))
    if matrix.ndim != 2 or not all(int(value) > 0 for value in matrix.shape):
        raise ValueError(f"{record['image_id']} temperature matrix must be a non-empty two-dimensional grid.")
    return matrix.astype(np.float32, copy=False)


def load_masks(record: pd.Series, expected_shape: tuple[int, int] | None = None) -> tuple[np.ndarray, np.ndarray | None]:
    class_mask = np.load(project_path(str(record["class_mask_thermal_grid_npy_path"])))
    if class_mask.ndim != 2:
        raise ValueError(f"{record['image_id']} cover mask must be two-dimensional.")
    if expected_shape is not None and class_mask.shape != expected_shape:
        raise ValueError(f"{record['image_id']} cover-mask shape {class_mask.shape}, expected {expected_shape}.")
    shadow_path = project_path(str(record["shadow_mask_thermal_grid_npy_path"]))
    shadow_mask = np.load(shadow_path) if shadow_path.is_file() else None
    if shadow_mask is not None and expected_shape is not None and shadow_mask.shape != expected_shape:
        raise ValueError(f"{record['image_id']} shadow-mask shape {shadow_mask.shape}, expected {expected_shape}.")
    return class_mask, shadow_mask


def build_luhk_pixel_labels(
    record: pd.Series, tables: dict[str, pd.DataFrame], shape: tuple[int, int]
) -> dict[str, np.ndarray | float]:
    result = build_native_luhk_result(
        image_id=str(record["image_id"]),
        pair_id=str(record["pair_id"]),
        shape=shape,
        grid=tables["grid"],
        footprints=tables["footprints"],
    )
    if result.unavailable_reason == "thermal_luhk_cells_missing":
        raise ValueError(f"Missing or duplicate thermal-covered LUHK cells for {record['image_id']}.")
    if result.unavailable_reason == "thermal_luhk_cells_duplicate":
        raise ValueError(f"Missing or duplicate thermal-covered LUHK cells for {record['image_id']}.")
    if result.unavailable_reason.startswith("valid_thermal_footprint_count:"):
        raise ValueError(f"Expected one valid thermal footprint for {record['image_id']}.")
    if not result.available:
        raise ValueError(f"LUHK lookup unavailable for {record['image_id']}: {result.unavailable_reason}")
    return result.as_legacy_part_e_dict()


def describe_values(values: pd.Series | np.ndarray) -> dict[str, float | int]:
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    if not array.size:
        return {key: np.nan for key in ("mean", "median", "std", "min", "q05", "q25", "q75", "q95", "max")} | {"n": 0}
    return {
        "n": int(array.size),
        "mean": float(np.mean(array)),
        "median": float(np.median(array)),
        "std": float(np.std(array, ddof=1)) if array.size > 1 else 0.0,
        "min": float(np.min(array)),
        "q05": float(np.quantile(array, 0.05)),
        "q25": float(np.quantile(array, 0.25)),
        "q75": float(np.quantile(array, 0.75)),
        "q95": float(np.quantile(array, 0.95)),
        "max": float(np.max(array)),
    }


def splitmix64(values: np.ndarray, seed: int) -> np.ndarray:
    x = values.astype(np.uint64, copy=False) + np.uint64(seed) + np.uint64(0x9E3779B97F4A7C15)
    x = (x ^ (x >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
    x = (x ^ (x >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    return x ^ (x >> np.uint64(31))


def formal_target_eligible_mask(frame: pd.DataFrame) -> np.ndarray:
    """Return the formal Part E target population mask.

    A formal observation must be accepted, have finite delta-T, be marked
    analysis-eligible, and fall inside the image's target mask.  Older normal
    visible/thermal results did not persist ``target_mask``; for those results
    the analysis-eligible mask is the backwards-compatible target definition.
    """
    delta_finite = (
        np.isfinite(pd.to_numeric(frame["delta_t_c"], errors="coerce").to_numpy(float))
        if "delta_t_c" in frame.columns
        else np.ones(len(frame), dtype=bool)
    )
    accepted = truthy(frame["pixel_accepted"]).to_numpy()
    analysis_eligible = truthy(
        frame["analysis_eligible"]
        if "analysis_eligible" in frame.columns
        else frame["surface_cover_valid"]
    ).to_numpy()
    target_mask = truthy(
        frame["target_mask"]
        if "target_mask" in frame.columns
        else pd.Series(analysis_eligible, index=frame.index)
    ).to_numpy()
    return accepted & delta_finite & analysis_eligible & target_mask


def gic_open_space_mask(frame: pd.DataFrame) -> pd.Series:
    """Recognize GIC/open-space in legacy numeric and canonical vocabularies."""

    if frame.empty:
        return pd.Series(False, index=frame.index, dtype=bool)
    codes = frame.get("luhk_class_code", pd.Series("", index=frame.index)).astype(str).str.casefold()
    names = frame.get("luhk_class_name", pd.Series("", index=frame.index)).astype(str).str.casefold()
    return (
        codes.isin({"31", "gic_open_space"})
        | names.str.contains("gic", regex=False)
        | names.str.contains("open space", regex=False)
    )


def family_eligible_and_group(frame: pd.DataFrame, family: str) -> tuple[np.ndarray, pd.Series]:
    # Formal Part E is a delta-temperature analysis. Retain temperature-only
    # rows in the canonical dataset, but do not fabricate an ambient value or
    # admit a non-finite delta-T row into sampling.
    accepted = formal_target_eligible_mask(frame)
    source_fields = [
        ("measurement_type", "full_thermal_pixel"),
        ("temperature_source", "unknown"),
        ("temperature_definition", "unknown"),
        ("temperature_unit", "degC"),
        ("ambient_source", "unavailable"),
        ("ambient_definition", "unavailable"),
        ("ambient_unit", "degC"),
        ("ambient_data_qa_status", "unavailable"),
        ("ambient_provenance", "unavailable"),
        ("source_method", "visible_review"),
        ("surface_cover_provenance", "visible_review"),
        ("luhk_provenance", "unknown"),
        ("target_name", ""),
        ("target_id", ""),
        ("qa_status", "pass"),
    ]
    source = pd.Series("", index=frame.index, dtype=object)
    for column, default in source_fields:
        value = frame[column].astype(str) if column in frame else pd.Series(default, index=frame.index)
        source = source + column + "=" + value + " | "
    prefix = source
    if family == "luhk":
        eligible = accepted & frame["luhk_label_valid"].astype(bool).to_numpy()
        group = prefix + frame["luhk_class_code"].astype(str) + " | " + frame["luhk_class_name"].astype(str)
    elif family == "surface_cover":
        eligible = accepted & frame["surface_cover_valid"].astype(bool).to_numpy()
        group = prefix + frame["surface_cover_class"].astype(str)
    elif family == "luhk_surface_cover":
        eligible = accepted & frame["luhk_label_valid"].astype(bool).to_numpy() & frame["surface_cover_valid"].astype(bool).to_numpy()
        group = (
            prefix
            + frame["luhk_class_code"].astype(str)
            + " | "
            + frame["luhk_class_name"].astype(str)
            + " | "
            + frame["surface_cover_class"].astype(str)
        )
    elif family == "surface_cover_shadow":
        eligible = accepted & frame["surface_cover_valid"].astype(bool).to_numpy() & frame["shadow_valid"].astype(bool).to_numpy()
        group = prefix + frame["surface_cover_class"].astype(str) + " | shadow=" + frame["shadow_flag"].astype("Int64").astype(str)
    elif family == "image_comparison":
        eligible = accepted
        group = prefix + frame["image_id"].astype(str)
    else:
        raise KeyError(f"Unknown analysis family: {family}")
    return eligible, group


def _allocate_quotas(counts: pd.Series, capacity: pd.Series, total: int) -> dict[str, int]:
    counts = counts.astype(float)
    capacity = capacity.astype(int)
    if int(capacity.sum()) <= total:
        return capacity.to_dict()
    raw = counts / counts.sum() * total
    quotas = np.floor(raw).astype(int).clip(lower=1)
    quotas = pd.Series(np.minimum(quotas, capacity), index=counts.index, dtype=int)
    while int(quotas.sum()) > total:
        candidates = quotas[quotas > 1]
        key = min(candidates.index, key=lambda item: (raw[item] - quotas[item], str(item)))
        quotas[key] -= 1
    fractions = raw - np.floor(raw)
    while int(quotas.sum()) < total:
        candidates = [item for item in counts.index if quotas[item] < capacity[item]]
        if not candidates:
            break
        key = max(candidates, key=lambda item: (fractions[item], counts[item], str(item)))
        quotas[key] += 1
        fractions[key] = -1
    return quotas.to_dict()


def prepare_spatial_sampling_plan(
    frame: pd.DataFrame,
    family: str,
    config: dict[str, Any],
    *,
    eligible_groups: tuple[np.ndarray, pd.Series] | None = None,
) -> dict[str, Any]:
    """Prepare seed-invariant state for repeated spatially-thinned samples.

    Stability analysis evaluates the same population with many deterministic
    seeds.  Eligibility, spatial strata, per-image capacities, and allocation
    quotas are identical for every seed, so rebuilding and factorizing those
    million-row structures for each seed is pure overhead.  The returned plan
    keeps the original pixel-level sampling design: each seed still hashes
    every eligible original pixel, chooses one pixel per spatial tile, and then
    applies the configured image/group quotas.

    This is intentionally an opt-in fast path.  One-off sampling continues to
    use :func:`spatially_thinned_sample`'s established implementation.
    """

    sampling = config["sampling"]
    eligible, groups = eligible_groups or family_eligible_and_group(frame, family)
    positions = np.flatnonzero(eligible)
    plan: dict[str, Any] = {
        "family": family,
        "frame_length": len(frame),
        "positions": positions,
        "tile_size": int(sampling["spatial_tile_size_px"]),
        "group_limit": int(sampling["max_pixels_per_group"]),
        "image_group_limit": int(sampling["max_pixels_per_image_per_group"]),
        "method": sampling["method"],
    }
    if not positions.size:
        plan["empty"] = True
        return plan

    image_id = frame.iloc[positions]["image_id"].astype(str).to_numpy()
    group_name = groups.iloc[positions].astype(str).to_numpy()
    thermal_row = frame.iloc[positions]["thermal_row"].to_numpy(dtype=np.int32)
    thermal_col = frame.iloc[positions]["thermal_col"].to_numpy(dtype=np.int32)
    tile_row = thermal_row // plan["tile_size"]
    tile_col = thermal_col // plan["tile_size"]

    strata_key, strata_values = pd.factorize(
        pd.MultiIndex.from_arrays([image_id, group_name, tile_row, tile_col]),
        sort=True,
    )
    pixel_key, _ = pd.factorize(
        pd.MultiIndex.from_arrays([image_id, thermal_row, thermal_col]),
        sort=True,
    )
    image_group_key, image_group_values = pd.factorize(
        pd.MultiIndex.from_arrays([image_id, group_name]),
        sort=True,
    )
    group_key, _ = pd.factorize(group_name, sort=True)
    image_key, _ = pd.factorize(image_id, sort=True)

    # Every stratum belongs to exactly one image/group.  Counts of strata and
    # eligible pixels therefore determine the seed-independent allocation
    # capacity without selecting a pixel for any particular seed.
    first_for_stratum = np.full(len(strata_values), len(positions), dtype=np.int64)
    np.minimum.at(first_for_stratum, strata_key, np.arange(len(positions), dtype=np.int64))
    stratum_image_group = image_group_key[first_for_stratum]
    image_group_count = len(image_group_values)
    eligible_counts = np.bincount(image_group_key, minlength=image_group_count).astype(np.int64)
    capacities = np.minimum(
        np.bincount(stratum_image_group, minlength=image_group_count),
        plan["image_group_limit"],
    ).astype(np.int64)

    pair_rows = pd.DataFrame(
        {
            "image_group_key": np.arange(image_group_count, dtype=np.int64),
            "image_id": [str(value[0]) for value in image_group_values],
            "group_name": [str(value[1]) for value in image_group_values],
            "eligible_pixel_count": eligible_counts,
            "capacity": capacities,
        }
    )
    quotas = np.zeros(image_group_count, dtype=np.int64)
    for _, group_pairs in pair_rows.groupby("group_name", sort=True):
        indexed = group_pairs.set_index("image_id")
        allocated = _allocate_quotas(
            indexed["eligible_pixel_count"],
            indexed["capacity"],
            plan["group_limit"],
        )
        for row in group_pairs.itertuples(index=False):
            quotas[int(row.image_group_key)] = int(allocated.get(str(row.image_id), 0))

    manifest_base = pair_rows[
        ["group_name", "image_id", "eligible_pixel_count", "image_group_key"]
    ].copy()
    manifest_base["sampled_pixel_count"] = manifest_base["image_group_key"].map(
        dict(enumerate(quotas.tolist()))
    ).astype(int)
    manifest_base = manifest_base.drop(columns="image_group_key").sort_values(
        ["group_name", "image_id"], kind="mergesort"
    ).reset_index(drop=True)
    manifest_base["sampling_fraction"] = (
        manifest_base["sampled_pixel_count"] / manifest_base["eligible_pixel_count"]
    )

    plan.update(
        {
            "empty": False,
            "image_id": image_id,
            "group_name": group_name,
            "thermal_row": thermal_row,
            "thermal_col": thermal_col,
            "tile_row": tile_row,
            "tile_col": tile_col,
            "strata_key": strata_key.astype(np.int64, copy=False),
            "strata_count": len(strata_values),
            "base_id": pixel_key.astype(np.uint64, copy=False),
            "image_group_key": image_group_key.astype(np.int64, copy=False),
            "group_key": group_key.astype(np.int64, copy=False),
            "image_key": image_key.astype(np.int64, copy=False),
            "quota_by_image_group": quotas,
            "group_population": np.bincount(group_key).astype(np.int64),
            "manifest_base": manifest_base,
        }
    )
    return plan


def _sample_from_spatial_sampling_plan(
    frame: pd.DataFrame,
    family: str,
    config: dict[str, Any],
    seed: int,
    plan: dict[str, Any],
    *,
    build_manifest: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    sampling = config["sampling"]
    expected = (
        family,
        len(frame),
        int(sampling["spatial_tile_size_px"]),
        int(sampling["max_pixels_per_group"]),
        int(sampling["max_pixels_per_image_per_group"]),
        sampling["method"],
    )
    actual = (
        plan.get("family"),
        plan.get("frame_length"),
        plan.get("tile_size"),
        plan.get("group_limit"),
        plan.get("image_group_limit"),
        plan.get("method"),
    )
    if actual != expected:
        raise ValueError("Spatial sampling plan does not match the frame, family, or sampling configuration")

    manifest_columns = [
        "analysis_family", "group_name", "image_id", "eligible_pixel_count",
        "sampled_pixel_count", "sampling_fraction", "sampling_seed", "sampling_method",
        "spatial_tile_size_px", "max_pixels_per_group", "max_pixels_per_image_per_group",
    ]
    if plan["empty"]:
        sample_columns = SAMPLE_COLUMNS + [
            "analysis_family", "group_name", "sampling_seed", "tile_row", "tile_col",
            "sampling_method", "source_population_count",
        ]
        return pd.DataFrame(columns=sample_columns), pd.DataFrame(columns=manifest_columns)

    base_id = plan["base_id"]
    strata_key = plan["strata_key"]
    score = splitmix64(base_id, seed)

    # O(N) segmented minimum replaces an O(N log N) global lexicographic sort.
    # In the vanishingly rare event of a 64-bit score tie, choose the earliest
    # stratum position, matching the stable order used by the established path.
    minimum_score = np.full(plan["strata_count"], np.iinfo(np.uint64).max, dtype=np.uint64)
    np.minimum.at(minimum_score, strata_key, score)
    tied = np.flatnonzero(score == minimum_score[strata_key])
    representatives = np.full(plan["strata_count"], len(base_id), dtype=np.int64)
    np.minimum.at(representatives, strata_key[tied], tied)

    second_score = splitmix64(base_id[representatives], seed ^ 0xA5A5A5A5)
    image_group = plan["image_group_key"][representatives]
    representative_order = np.lexsort(
        (np.arange(len(representatives), dtype=np.int64), second_score, image_group)
    )
    ordered_representatives = representatives[representative_order]
    ordered_image_group = image_group[representative_order]
    group_starts = np.r_[0, np.flatnonzero(ordered_image_group[1:] != ordered_image_group[:-1]) + 1]
    group_lengths = np.diff(np.r_[group_starts, len(ordered_image_group)])
    within_group_rank = np.arange(len(ordered_image_group)) - np.repeat(group_starts, group_lengths)
    keep = within_group_rank < plan["quota_by_image_group"][ordered_image_group]
    selected = ordered_representatives[keep]

    # Restore the public sample ordering of the established implementation.
    selected = selected[
        np.lexsort(
            (
                plan["thermal_col"][selected],
                plan["thermal_row"][selected],
                plan["image_key"][selected],
                plan["group_key"][selected],
            )
        )
    ]
    sample = frame.iloc[plan["positions"][selected]].copy().reset_index(drop=True)
    sample["analysis_family"] = family
    sample["group_name"] = plan["group_name"][selected]
    sample["sampling_seed"] = int(seed)
    sample["tile_row"] = plan["tile_row"][selected].astype(np.int16, copy=False)
    sample["tile_col"] = plan["tile_col"][selected].astype(np.int16, copy=False)
    sample["sampling_method"] = sampling["method"]
    sample["source_population_count"] = plan["group_population"][
        plan["group_key"][selected]
    ].astype(np.int64, copy=False)

    if not build_manifest:
        return sample, pd.DataFrame(columns=manifest_columns)
    manifest = plan["manifest_base"].copy()
    manifest.insert(0, "analysis_family", family)
    manifest["sampling_seed"] = int(seed)
    manifest["sampling_method"] = sampling["method"]
    manifest["spatial_tile_size_px"] = int(sampling["spatial_tile_size_px"])
    manifest["max_pixels_per_group"] = int(sampling["max_pixels_per_group"])
    manifest["max_pixels_per_image_per_group"] = int(
        sampling["max_pixels_per_image_per_group"]
    )
    return sample, manifest


def spatially_thinned_sample(
    frame: pd.DataFrame,
    family: str,
    config: dict[str, Any],
    seed: int,
    *,
    eligible_groups: tuple[np.ndarray, pd.Series] | None = None,
    sampling_plan: dict[str, Any] | None = None,
    build_manifest: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if sampling_plan is not None:
        return _sample_from_spatial_sampling_plan(
            frame,
            family,
            config,
            seed,
            sampling_plan,
            build_manifest=build_manifest,
        )
    sampling = config["sampling"]
    eligible, groups = eligible_groups or family_eligible_and_group(frame, family)
    positions = np.flatnonzero(eligible)
    if not positions.size:
        sample_columns = SAMPLE_COLUMNS + [
            "analysis_family", "group_name", "sampling_seed", "tile_row", "tile_col",
            "sampling_method", "source_population_count",
        ]
        manifest_columns = [
            "analysis_family", "group_name", "image_id", "eligible_pixel_count",
            "sampled_pixel_count", "sampling_fraction", "sampling_seed", "sampling_method",
            "spatial_tile_size_px", "max_pixels_per_group", "max_pixels_per_image_per_group",
        ]
        return pd.DataFrame(columns=sample_columns), pd.DataFrame(columns=manifest_columns)
    work = pd.DataFrame(
        {
            "position": positions,
            "image_id": frame.iloc[positions]["image_id"].astype(str).to_numpy(),
            "group_name": groups.iloc[positions].astype(str).to_numpy(),
            "thermal_row": frame.iloc[positions]["thermal_row"].to_numpy(dtype=np.int32),
            "thermal_col": frame.iloc[positions]["thermal_col"].to_numpy(dtype=np.int32),
        }
    )
    tile_size = int(sampling["spatial_tile_size_px"])
    work["tile_row"] = work["thermal_row"] // tile_size
    work["tile_col"] = work["thermal_col"] // tile_size
    strata_key, _ = pd.factorize(
        pd.MultiIndex.from_frame(work[["image_id", "group_name", "tile_row", "tile_col"]]),
        sort=True,
    )
    pixel_key, _ = pd.factorize(
        pd.MultiIndex.from_frame(work[["image_id", "thermal_row", "thermal_col"]]),
        sort=True,
    )
    base_id = pixel_key.astype(np.uint64)
    score = splitmix64(base_id, seed)
    order = np.lexsort((score, strata_key))
    sorted_keys = strata_key[order]
    first = np.r_[True, sorted_keys[1:] != sorted_keys[:-1]]
    thinned = work.iloc[order[first]].copy()
    thinned["score"] = splitmix64(base_id[order[first]], seed ^ 0xA5A5A5A5)
    thinned = thinned.sort_values(["image_id", "group_name", "score"], kind="mergesort")
    thinned = thinned.groupby(["image_id", "group_name"], sort=False, group_keys=False).head(
        int(sampling["max_pixels_per_image_per_group"])
    )

    population = work.groupby(["group_name", "image_id"], sort=True).size().rename("eligible_pixel_count")
    selected_parts: list[pd.DataFrame] = []
    group_limit = int(sampling["max_pixels_per_group"])
    for group_name, group_candidates in thinned.groupby("group_name", sort=True):
        candidate_counts = group_candidates.groupby("image_id").size()
        eligible_counts = population.loc[group_name]
        quotas = _allocate_quotas(eligible_counts, candidate_counts, group_limit)
        for image_id, image_candidates in group_candidates.groupby("image_id", sort=True):
            selected_parts.append(image_candidates.nsmallest(quotas.get(image_id, 0), "score"))
    selected = pd.concat(selected_parts, ignore_index=True) if selected_parts else thinned.iloc[0:0].copy()
    selected = selected.sort_values(["group_name", "image_id", "thermal_row", "thermal_col"]).reset_index(drop=True)
    sample = frame.iloc[selected["position"].to_numpy()].copy().reset_index(drop=True)
    sample["analysis_family"] = family
    sample["group_name"] = selected["group_name"].to_numpy()
    sample["sampling_seed"] = int(seed)
    sample["tile_row"] = selected["tile_row"].to_numpy(dtype=np.int16)
    sample["tile_col"] = selected["tile_col"].to_numpy(dtype=np.int16)
    sample["sampling_method"] = sampling["method"]
    group_population = work.groupby("group_name").size().to_dict()
    sample["source_population_count"] = sample["group_name"].map(group_population).astype(np.int64)

    manifest = (
        work.groupby(["group_name", "image_id"], sort=True)
        .size()
        .rename("eligible_pixel_count")
        .reset_index()
        .merge(
            sample.groupby(["group_name", "image_id"], sort=True).size().rename("sampled_pixel_count").reset_index(),
            on=["group_name", "image_id"],
            how="left",
        )
    )
    manifest["sampled_pixel_count"] = manifest["sampled_pixel_count"].fillna(0).astype(int)
    manifest["sampling_fraction"] = manifest["sampled_pixel_count"] / manifest["eligible_pixel_count"]
    manifest.insert(0, "analysis_family", family)
    manifest["sampling_seed"] = int(seed)
    manifest["sampling_method"] = sampling["method"]
    manifest["spatial_tile_size_px"] = tile_size
    manifest["max_pixels_per_group"] = group_limit
    manifest["max_pixels_per_image_per_group"] = int(sampling["max_pixels_per_image_per_group"])
    return sample, manifest


def read_canonical(config: dict[str, Any], columns: list[str] | None = None) -> pd.DataFrame:
    path = project_path(config["outputs"]["canonical_parquet"])
    available = set(pq.ParquetFile(path).schema_arrow.names)
    selected = None if columns is None else [column for column in columns if column in available]
    frame = pq.read_table(path, columns=selected).to_pandas(strings_to_categorical=True)
    defaults: dict[str, Any] = {
        "source_method": "visible_review",
        "measurement_type": "full_thermal_pixel",
        "temperature_source": "legacy_part_d",
        "temperature_definition": "legacy definition unavailable",
        "temperature_unit": "degC",
        "ambient_source": "legacy unavailable",
        "ambient_definition": "legacy unavailable",
        "ambient_unit": "degC",
        "ambient_data_qa_status": "legacy unavailable",
        "ambient_provenance": "legacy unavailable",
        "ambient_source_record": "",
        "label_provenance": "visible_review",
        "surface_cover_provenance": "visible_review",
        "luhk_provenance": "unknown",
        "label_known": frame.get("surface_cover_valid", pd.Series(False, index=frame.index)),
        "analysis_eligible": frame.get("surface_cover_valid", pd.Series(False, index=frame.index)),
        "target_mask": frame.get(
            "analysis_eligible",
            frame.get("surface_cover_valid", pd.Series(False, index=frame.index)),
        ),
        "exclusion_reason": "",
        "target_name": "",
        "target_id": "",
        "qa_status": "pass",
        "annotation_review_status": frame.get("surface_cover_review_status", pd.Series("", index=frame.index)),
    }
    for column, value in defaults.items():
        if column not in frame.columns:
            frame[column] = value
    if columns is not None:
        missing = [column for column in columns if column not in frame.columns]
        if missing:
            raise ValueError(f"Canonical dataset is missing required columns: {missing}")
        return frame[columns]
    return frame


def write_sample_outputs(config: dict[str, Any], family: str, sample: pd.DataFrame) -> None:
    base = SAMPLE_FILES[family]
    directory = project_path(config["outputs"]["sample_directory"])
    directory.mkdir(parents=True, exist_ok=True)
    ordered = SAMPLE_COLUMNS + [
        "analysis_family",
        "group_name",
        "sampling_seed",
        "tile_row",
        "tile_col",
        "sampling_method",
        "source_population_count",
    ]
    output = sample.reindex(columns=ordered).copy()
    for column in output.select_dtypes(include="category").columns:
        output[column] = output[column].astype(str)
    output.to_parquet(directory / f"{base}.parquet", index=False, compression="zstd")
    output.to_csv(directory / f"{base}.csv", index=False, encoding="utf-8-sig")


def grouped_summary(
    full: pd.DataFrame,
    sample: pd.DataFrame,
    group_columns: list[str],
    valid_mask: pd.Series | np.ndarray,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    eligible = full.loc[np.asarray(valid_mask, dtype=bool)].copy()
    for keys, group in eligible.groupby(group_columns, observed=True, sort=True, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        stats = describe_values(group["delta_t_c"])
        row = {column: key for column, key in zip(group_columns, keys)}
        row.update({
            "n_pixels_full": stats.pop("n"),
            "n_images": int(group["image_id"].nunique()),
            **{f"{key}_full": value for key, value in stats.items()},
        })
        matching = sample.copy()
        for column, key in zip(group_columns, keys):
            matching = matching.loc[matching[column].astype(str).eq(str(key))]
        sampled_stats = describe_values(matching["delta_t_c"] if not matching.empty else np.array([]))
        row["n_pixels_sampled"] = sampled_stats["n"]
        row["mean_sampled"] = sampled_stats["mean"]
        row["median_sampled"] = sampled_stats["median"]
        rows.append(row)
    return pd.DataFrame(rows)


def dataframe_sha256(frame: pd.DataFrame, columns: list[str]) -> str:
    ordered = frame.sort_values(columns).reset_index(drop=True)
    values = pd.util.hash_pandas_object(ordered[columns], index=False).to_numpy(dtype=np.uint64)
    return hashlib.sha256(values.tobytes()).hexdigest()
