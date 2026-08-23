"""Adapter from the verified five-image pilot artifacts to schema 0.1."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .canonical_result import UNKNOWN_LABEL_ID, write_canonical_result
from .capture_time import dji_metadata_for_paths, resolve_capture_time
from .luhk_context import LUHK_CATEGORIES, LUHK_LOOKUP_VERSION, load_native_luhk_result
from .models import CoverageClass, ManualReviewStatus, ProcessingRoute, QAStatus, SceneCorrespondence, SourceMethod
from .result_index import configuration_hash, source_hashes
from .temperature_extraction import TemperatureResult


def _project_path(root: Path, value: Any) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else root / path


def pilot_image_ids(project_root: Path) -> list[str]:
    pairs = pd.read_excel(project_root / "data" / "metadata" / "part_b_pilot_pairs.xlsx")
    return pairs["image_id"].astype(str).tolist()


def pilot_source_paths(project_root: Path, image_id: str) -> list[Path]:
    """Return every mutable reviewed artifact that determines one pilot result."""
    pairs_path = project_root / "data" / "metadata" / "part_b_pilot_pairs.xlsx"
    masks_path = project_root / "outputs" / "part_c" / "summaries" / "part_c_final_mask_manifest.xlsx"
    temperatures_path = (
        project_root / "outputs" / "part_d" / "summaries" / "part_d_tat3_parameter_temperature_extraction_summary.csv"
    )
    pairs = pd.read_excel(pairs_path)
    masks = pd.read_excel(masks_path)
    temperatures = pd.read_csv(temperatures_path, keep_default_na=False)
    pair_rows = pairs.loc[pairs["image_id"].astype(str).eq(image_id)]
    mask_rows = masks.loc[masks["image_id"].astype(str).eq(image_id)]
    temperature_rows = temperatures.loc[temperatures["image_id"].astype(str).eq(image_id)]
    if len(pair_rows) != 1 or len(mask_rows) != 1 or len(temperature_rows) != 1:
        raise ValueError(f"Pilot source artifacts do not map one-to-one for {image_id}.")
    mask_row = mask_rows.iloc[0]
    temperature_row = temperature_rows.iloc[0]
    paths = [
        pairs_path,
        masks_path,
        temperatures_path,
        _project_path(project_root, mask_row["class_mask_thermal_grid_npy_path"]),
        _project_path(project_root, temperature_row["npy_path"]),
        project_root / "data" / "processed" / "grids" / "pilot_luhk_aligned_10m_grid_cells.xlsx",
        project_root / "data" / "processed" / "footprints" / "image_footprints.xlsx",
        Path(__file__).with_name("luhk_context.py"),
    ]
    official_raster = project_root / "data" / "luhk" / "LUMHK_RasterGrid_2024.tif"
    if official_raster.is_file():
        paths.append(official_raster)
    shadow_path = _project_path(project_root, mask_row["shadow_mask_thermal_grid_npy_path"])
    if shadow_path.is_file():
        paths.append(shadow_path)
    return paths


def resolve_pilot_capture_time(
    thermal_path: Path,
    visible_path: Path,
    part_a: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve one immutable capture-time bundle using the shared priority chain.

    Part A is a lower-priority user-metadata fallback.  Keeping this helper
    separate prevents the adapter from overwriting higher-priority EXIF or DJI
    timestamps after resolution.
    """
    part_a_payload = dict(part_a or {})
    return resolve_capture_time(
        thermal_path=thermal_path,
        visible_path=visible_path,
        dji_metadata_records=dji_metadata_for_paths([thermal_path, visible_path]),
        user_metadata=part_a_payload,
        default_timezone=str(part_a_payload.get("capture_timezone") or "Asia/Hong_Kong"),
    ).to_dict()


def adapt_pilot_image(
    project_root: Path,
    image_id: str,
    *,
    output_root: Path | None = None,
    write_pixels_parquet: bool = True,
    configuration_hash_value: str | None = None,
    source_file_hashes_value: dict[str, str] | None = None,
    dependency_fingerprints_value: dict[str, str] | None = None,
    part_a: dict[str, Any] | None = None,
    temperature_result: TemperatureResult | None = None,
) -> tuple[object, Path]:
    pairs = pd.read_excel(project_root / "data" / "metadata" / "part_b_pilot_pairs.xlsx")
    masks = pd.read_excel(project_root / "outputs" / "part_c" / "summaries" / "part_c_final_mask_manifest.xlsx")
    temperatures = pd.read_csv(
        project_root / "outputs" / "part_d" / "summaries" / "part_d_tat3_parameter_temperature_extraction_summary.csv",
        keep_default_na=False,
    )
    mapping = pd.read_excel(project_root / "data" / "annotations" / "part_c" / "surface_cover_class_mapping.xlsx")
    pair_rows = pairs.loc[pairs["image_id"].astype(str).eq(image_id)]
    mask_rows = masks.loc[masks["image_id"].astype(str).eq(image_id)]
    temperature_rows = temperatures.loc[temperatures["image_id"].astype(str).eq(image_id)]
    if len(pair_rows) != 1 or len(mask_rows) != 1 or len(temperature_rows) != 1:
        raise ValueError(f"Pilot artifacts do not map one-to-one for {image_id}.")
    pair = pair_rows.iloc[0]
    mask_row = mask_rows.iloc[0]
    temperature_row = temperature_rows.iloc[0]
    if str(mask_row.get("usable_for_part_d", "")).casefold() != "yes":
        raise ValueError(f"Pilot Part C result is not accepted for Part D: {image_id}")
    if str(temperature_row.get("extraction_status", "")).casefold() != "success":
        raise ValueError(f"Pilot temperature extraction is not successful: {image_id}")
    if temperature_result is None:
        temperature = np.load(_project_path(project_root, temperature_row["npy_path"]))
        runtime_temperature_metadata = {
            "extraction_method": temperature_row.get("extraction_method", ""),
            "temperature_definition": "per-pixel radiometric surface temperature",
            "temperature_unit": temperature_row.get("temperature_unit", "degC"),
            "ambient_temperature_c": temperature_row.get("ambient_temperature_c", ""),
            "legacy_validation_status": temperature_row.get("validation_status", ""),
        }
        runtime_qa = (
            QAStatus.WARN
            if str(temperature_row.get("validation_status", "")).casefold() == "warn"
            else QAStatus.PASS
        )
    else:
        temperature = np.asarray(temperature_result.matrix, dtype=np.float32)
        runtime_temperature_metadata = dict(temperature_result.metadata)
        runtime_qa = (
            QAStatus(temperature_result.qa_status)
            if temperature_result.qa_status in {status.value for status in QAStatus}
            else QAStatus.WARN
        )
    labels = np.load(_project_path(project_root, mask_row["class_mask_thermal_grid_npy_path"])).astype(np.int16)
    known = ~np.isin(labels, [0, 9])
    canonical_labels = labels.copy()
    canonical_labels[~known] = UNKNOWN_LABEL_ID
    shadow_path = _project_path(project_root, mask_row["shadow_mask_thermal_grid_npy_path"])
    shadow = np.load(shadow_path) if shadow_path.is_file() else None
    names = {int(row.class_id): str(row.class_name) for row in mapping.itertuples(index=False)}
    visible_path = _project_path(project_root, pair["v_path"])
    thermal_path = _project_path(project_root, pair["t_path"])
    hashes = source_hashes(pilot_source_paths(project_root, image_id))
    luhk = load_native_luhk_result(
        project_root,
        image_id=image_id,
        pair_id=str(pair["pair_id"]),
        shape=temperature.shape,
    )
    part_a_payload = dict(part_a or {})
    capture_payload = resolve_pilot_capture_time(thermal_path, visible_path, part_a_payload)
    config = {
        "adapter": "verified_five_image_pilot",
        "source_method": SourceMethod.VISIBLE_REVIEW.value,
        "unknown_class_ids": [0, 9],
    }
    return write_canonical_result(
        output_root=output_root or project_root / "data" / "processed" / "images",
        image_id=image_id,
        group_id=str(pair["pair_id"]),
        pair_id=str(pair["pair_id"]),
        dataset_id=str(pair.get("dataset_folder", "HKUST_pilot")),
        visible_path=visible_path.as_posix(),
        thermal_path=thermal_path.as_posix(),
        temperature=temperature,
        labels=canonical_labels,
        known_mask=known,
        processing_route=ProcessingRoute.NORMAL_VT,
        source_method=SourceMethod.VISIBLE_REVIEW,
        review_status=ManualReviewStatus.ACCEPTED,
        qa_status=runtime_qa,
        configuration_hash=configuration_hash_value or configuration_hash(config),
        source_file_hashes=source_file_hashes_value or hashes,
        dependency_fingerprints=dependency_fingerprints_value or {
            "luhk_lookup_version": LUHK_LOOKUP_VERSION,
        },
        surface_cover_names=names,
        shadow_mask=shadow,
        luhk_labels=luhk.labels,
        luhk_known_mask=luhk.known_mask,
        luhk_class_names=luhk.category_names,
        luhk_cell_ids=luhk.cell_ids,
        luhk_raw_codes=luhk.raw_codes,
        luhk_provenance=luhk.provenance.value,
        luhk_metadata={
            **luhk.metadata,
            "status": luhk.status,
            "unavailable_reason": luhk.unavailable_reason,
            "spatial_uncertainty": luhk.spatial_uncertainty,
            "source_paths": luhk.source_paths,
            "category_names_by_code": LUHK_CATEGORIES,
        },
        temperature_metadata={
            **runtime_temperature_metadata,
            **capture_payload,
        },
        ambient_metadata={
            "ambient_temperature_c": runtime_temperature_metadata.get(
                "ambient_temperature_c", temperature_row.get("ambient_temperature_c", "")
            ),
            "source": "TAT3 exported ambient parameter",
            "definition": "TAT3 exported ambient parameter; not independently validated meteorological air temperature",
            "source_record": runtime_temperature_metadata.get(
                "source_report", temperature_row.get("tat3_parameter_source_report", "")
            ),
            "validation_status": "provisional_report_parameter",
        },
        temperature_source=str(
            runtime_temperature_metadata.get("extraction_method", temperature_row.get("extraction_method", ""))
        ),
        validation_status="verified_pilot_adapter",
        part_a=part_a_payload,
        scene_correspondence=SceneCorrespondence.ACCEPTED.value,
        coverage_class=CoverageClass.THERMAL_FULLY_SUPPORTED_BY_VISIBLE.value,
        notes=(
            "Adapted from preserved reviewed pilot outputs. LUHK uses the official 10 m lookup with "
            "a metadata-derived north-up approximate footprint; it is separate from surface-cover review."
        ),
        write_pixels_parquet=write_pixels_parquet,
    )
