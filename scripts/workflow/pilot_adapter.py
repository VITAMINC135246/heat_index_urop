"""Adapter from the verified five-image pilot artifacts to schema 0.1."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .canonical_result import UNKNOWN_LABEL_ID, write_canonical_result
from .models import CoverageClass, ManualReviewStatus, ProcessingRoute, QAStatus, SceneCorrespondence, SourceMethod
from .result_index import configuration_hash, source_hashes


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
    ]
    shadow_path = _project_path(project_root, mask_row["shadow_mask_thermal_grid_npy_path"])
    if shadow_path.is_file():
        paths.append(shadow_path)
    return paths


def adapt_pilot_image(
    project_root: Path,
    image_id: str,
    *,
    output_root: Path | None = None,
    write_pixels_parquet: bool = True,
    configuration_hash_value: str | None = None,
    source_file_hashes_value: dict[str, str] | None = None,
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
    temperature = np.load(_project_path(project_root, temperature_row["npy_path"]))
    labels = np.load(_project_path(project_root, mask_row["class_mask_thermal_grid_npy_path"])).astype(np.int16)
    known = ~np.isin(labels, [0, 9])
    canonical_labels = labels.copy()
    canonical_labels[~known] = UNKNOWN_LABEL_ID
    shadow_path = _project_path(project_root, mask_row["shadow_mask_thermal_grid_npy_path"])
    shadow = np.load(shadow_path) if shadow_path.is_file() else None
    names = {int(row.class_id): str(row.class_name) for row in mapping.itertuples(index=False)}
    visible_path = _project_path(project_root, pair["v_path"])
    thermal_path = _project_path(project_root, pair["t_path"])
    hashes = source_hashes([visible_path, thermal_path])
    config = {
        "adapter": "verified_five_image_pilot",
        "source_method": SourceMethod.VISIBLE_REVIEW.value,
        "unknown_class_ids": [0, 9],
    }
    qa = QAStatus.WARN if str(temperature_row.get("validation_status", "")).casefold() == "warn" else QAStatus.PASS
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
        qa_status=qa,
        configuration_hash=configuration_hash_value or configuration_hash(config),
        source_file_hashes=source_file_hashes_value or hashes,
        surface_cover_names=names,
        shadow_mask=shadow,
        temperature_metadata={
            "legacy_extraction_method": temperature_row.get("extraction_method", ""),
            "ambient_temperature_c": temperature_row.get("ambient_temperature_c", ""),
            "legacy_validation_status": temperature_row.get("validation_status", ""),
        },
        validation_status="verified_pilot_adapter",
        scene_correspondence=SceneCorrespondence.ACCEPTED.value,
        coverage_class=CoverageClass.THERMAL_FULLY_SUPPORTED_BY_VISIBLE.value,
        notes="Adapted from the preserved and manually used five-image pilot outputs.",
        write_pixels_parquet=write_pixels_parquet,
    )
