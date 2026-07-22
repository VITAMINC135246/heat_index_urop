"""Controlled LUHK vocabulary and native thermal-grid lookup utilities.

The official LUHK product is broad land-use context.  It is deliberately kept
separate from the visible-image physical surface-cover review.  Native-grid
assignment uses the centre of each thermal pixel and the preserved approximate
north-up thermal footprint; it does not imply surveyed pixel georegistration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .models import LUHKProvenance


LUHK_GRID_SIZE_M = 10.0
LUHK_KEY_MULTIPLIER = 1_000_000
LUHK_LOOKUP_VERSION = "official-luhk-10m-pixel-centre-v1"
LUHK_SPATIAL_UNCERTAINTY = (
    "Approximate context only: LUHK is assigned through a metadata-derived, "
    "north-up rectangular thermal footprint; yaw is not applied and Part B "
    "image-space alignment does not improve map georegistration."
)

DEFAULT_GRID_RELATIVE_PATH = Path("data/processed/grids/pilot_luhk_aligned_10m_grid_cells.xlsx")
DEFAULT_FOOTPRINTS_RELATIVE_PATH = Path("data/processed/footprints/image_footprints.xlsx")
DEFAULT_RASTER_RELATIVE_PATH = Path("data/luhk/LUMHK_RasterGrid_2024.tif")


LUHK_CATEGORIES = {
    "residential": "Residential",
    "commercial": "Commercial",
    "industrial": "Industrial",
    "gic_open_space": "GIC / open space",
    "transport": "Transport",
    "other_urban_built_up": "Other urban / built-up land",
    "agriculture": "Agriculture",
    "woodland_shrubland_grassland_wetland": "Woodland / shrubland / grassland / wetland",
    "barren_land": "Barren land",
    "water_bodies": "Water bodies",
}

LUHK_GROUP_CODES = {
    0: "residential",
    1: "commercial",
    2: "industrial",
    3: "gic_open_space",
    4: "transport",
    5: "other_urban_built_up",
    6: "agriculture",
    7: "woodland_shrubland_grassland_wetland",
    8: "barren_land",
    9: "water_bodies",
}


@dataclass(frozen=True, slots=True)
class LUHKContext:
    code: str
    category: str
    provenance: LUHKProvenance


@dataclass(frozen=True, slots=True)
class NativeLUHKResult:
    """Official LUHK context represented on one native thermal grid.

    ``labels`` contains stable broad codes such as ``gic_open_space``.
    ``known_mask`` is the only validity authority.  Raw official raster codes,
    cell identifiers, and human-readable category names are retained as
    separate provenance layers rather than being inferred from surface cover.
    """

    image_id: str
    pair_id: str
    labels: np.ndarray
    known_mask: np.ndarray
    cell_ids: np.ndarray
    raw_codes: np.ndarray
    category_names: np.ndarray
    luhk_rows: np.ndarray
    luhk_cols: np.ndarray
    cell_indices: np.ndarray
    mapped_mask: np.ndarray
    provenance: LUHKProvenance
    status: str
    unavailable_reason: str = ""
    spatial_uncertainty: str = LUHK_SPATIAL_UNCERTAINTY
    source_paths: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    _legacy_arrays: dict[str, np.ndarray] = field(default_factory=dict, repr=False, compare=False)

    @property
    def available(self) -> bool:
        return self.status == "available" and bool(self.known_mask.any())

    @property
    def known_pixel_count(self) -> int:
        return int(self.known_mask.sum())

    def as_legacy_part_e_dict(self) -> dict[str, np.ndarray | float]:
        """Return the historical ``build_luhk_pixel_labels`` payload."""

        legacy = self._legacy_arrays
        return {
            "cell_index": self.cell_indices,
            "mapped": self.mapped_mask,
            "cell_id": legacy.get("cell_id", self.cell_ids),
            "class_code": legacy.get("class_code", self.raw_codes),
            "class_name": legacy.get("class_name", self.category_names),
            "luhk_row": legacy.get("luhk_row", self.luhk_rows),
            "luhk_col": legacy.get("luhk_col", self.luhk_cols),
            "origin_x": float(self.metadata.get("grid_origin_x_2326", np.nan)),
            "origin_y": float(self.metadata.get("grid_origin_y_2326", np.nan)),
        }


def resolve_luhk_context(value: str, provenance: str) -> LUHKContext:
    text = value.strip()
    if not text:
        raise ValueError("Part C* requires a LUHK category.")
    normalized = text.casefold().replace("/", " ").replace("-", " ")
    normalized = "_".join(normalized.split())
    by_name = {name.casefold(): code for code, name in LUHK_CATEGORIES.items()}
    code = text if text in LUHK_CATEGORIES else by_name.get(text.casefold(), normalized)
    if code not in LUHK_CATEGORIES:
        raise ValueError(f"Unknown LUHK category: {value!r}")
    resolved_provenance = LUHKProvenance(provenance)
    if resolved_provenance == LUHKProvenance.UNKNOWN:
        raise ValueError("An accepted Part C* target requires official or user-supplied LUHK provenance.")
    return LUHKContext(code=code, category=LUHK_CATEGORIES[code], provenance=resolved_provenance)


def _empty_array(shape: tuple[int, int], value: Any, dtype: str | np.dtype[Any]) -> np.ndarray:
    return np.full(shape, value, dtype=dtype)


def unavailable_native_luhk_result(
    *,
    image_id: str,
    pair_id: str,
    shape: tuple[int, int],
    reason: str,
    source_paths: dict[str, str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> NativeLUHKResult:
    """Build an explicit unavailable result without inventing a LUHK label."""

    if len(shape) != 2 or any(int(value) <= 0 for value in shape):
        raise ValueError("Native LUHK shape must contain two positive dimensions.")
    resolved_shape = (int(shape[0]), int(shape[1]))
    return NativeLUHKResult(
        image_id=str(image_id),
        pair_id=str(pair_id),
        labels=_empty_array(resolved_shape, "", "<U48"),
        known_mask=np.zeros(resolved_shape, dtype=bool),
        cell_ids=_empty_array(resolved_shape, "", "<U40"),
        raw_codes=_empty_array(resolved_shape, -1, np.int16),
        category_names=_empty_array(resolved_shape, "", "<U96"),
        luhk_rows=_empty_array(resolved_shape, -1, np.int32),
        luhk_cols=_empty_array(resolved_shape, -1, np.int32),
        cell_indices=_empty_array(resolved_shape, -1, np.int32),
        mapped_mask=np.zeros(resolved_shape, dtype=bool),
        provenance=LUHKProvenance.UNKNOWN,
        status="unavailable",
        unavailable_reason=str(reason),
        source_paths=dict(source_paths or {}),
        metadata={
            "lookup_version": LUHK_LOOKUP_VERSION,
            "native_shape": list(resolved_shape),
            **(metadata or {}),
        },
    )


def _truthy(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.casefold().isin({"1", "true", "yes", "y", "ok"})


def _image_matches(rows: pd.DataFrame, image_id: str) -> bool:
    if not image_id:
        return True
    for column in ("thermal_image_name", "image_name", "thermal_image_path", "image_path", "pair_id"):
        if column in rows and rows[column].astype(str).str.contains(image_id, regex=False).any():
            return True
    return False


def _rows_for_image_id(rows: pd.DataFrame, image_id: str) -> pd.DataFrame:
    """Return rows tied to one image identifier without guessing by time/order."""

    if not image_id:
        return rows.iloc[0:0].copy()
    mask = pd.Series(False, index=rows.index, dtype=bool)
    for column in ("thermal_image_name", "image_name", "thermal_image_path", "image_path", "pair_id"):
        if column in rows:
            mask |= rows[column].astype(str).str.contains(image_id, case=False, regex=False)
    return rows.loc[mask].copy()


def build_native_luhk_result(
    *,
    image_id: str,
    pair_id: str,
    shape: tuple[int, int],
    grid: pd.DataFrame,
    footprints: pd.DataFrame,
    source_paths: dict[str, str] | None = None,
) -> NativeLUHKResult:
    """Map preserved official LUHK cells to native thermal-pixel centres.

    The method is the validated five-pilot method formerly local to Part E.
    Missing, ambiguous, or spatially inconsistent inputs produce an explicit
    unavailable result instead of a fabricated dominant category.
    """

    if len(shape) != 2 or any(int(value) <= 0 for value in shape):
        raise ValueError("Native LUHK shape must contain two positive dimensions.")
    resolved_shape = (int(shape[0]), int(shape[1]))
    sources = dict(source_paths or {})
    required_grid = {
        "pair_id", "global_cell_id", "luhk_row", "luhk_col",
        "cell_min_x_2326", "cell_max_y_2326", "luhk_raw_code",
        "luhk_category_code", "luhk_category_name", "is_thermal_covered",
    }
    missing_grid = sorted(required_grid.difference(grid.columns))
    if missing_grid:
        return unavailable_native_luhk_result(
            image_id=image_id, pair_id=pair_id, shape=resolved_shape,
            reason="luhk_grid_columns_missing:" + ",".join(missing_grid), source_paths=sources,
        )
    required_footprint = {
        "pair_id", "image_type", "status", "min_x_2326", "max_x_2326",
        "min_y_2326", "max_y_2326",
    }
    missing_footprint = sorted(required_footprint.difference(footprints.columns))
    if missing_footprint:
        return unavailable_native_luhk_result(
            image_id=image_id, pair_id=pair_id, shape=resolved_shape,
            reason="footprint_columns_missing:" + ",".join(missing_footprint), source_paths=sources,
        )

    resolved_pair_id = str(pair_id)
    pair_resolution = "pair_id"
    thermal_grid = grid.loc[_truthy(grid["is_thermal_covered"])].copy()
    pair_grid = thermal_grid.loc[
        thermal_grid["pair_id"].astype(str).eq(resolved_pair_id)
    ].copy()
    if pair_grid.empty or not _image_matches(pair_grid, image_id):
        image_grid = _rows_for_image_id(thermal_grid, image_id)
        candidate_pairs = sorted(image_grid["pair_id"].astype(str).unique())
        if len(candidate_pairs) == 1:
            resolved_pair_id = candidate_pairs[0]
            pair_resolution = "unique_image_id"
            pair_grid = image_grid.loc[image_grid["pair_id"].astype(str).eq(resolved_pair_id)].copy()
        elif len(candidate_pairs) > 1:
            return unavailable_native_luhk_result(
                image_id=image_id, pair_id=pair_id, shape=resolved_shape,
                reason=f"image_id_luhk_mapping_ambiguous:{len(candidate_pairs)}", source_paths=sources,
            )
    if pair_grid.empty:
        return unavailable_native_luhk_result(
            image_id=image_id, pair_id=pair_id, shape=resolved_shape,
            reason="thermal_luhk_cells_missing", source_paths=sources,
        )
    if not _image_matches(pair_grid, image_id):
        return unavailable_native_luhk_result(
            image_id=image_id, pair_id=pair_id, shape=resolved_shape,
            reason="image_id_pair_mismatch", source_paths=sources,
        )
    if pair_grid.duplicated(["global_cell_id"]).any() or pair_grid.duplicated(["luhk_row", "luhk_col"]).any():
        return unavailable_native_luhk_result(
            image_id=image_id, pair_id=pair_id, shape=resolved_shape,
            reason="thermal_luhk_cells_duplicate", source_paths=sources,
        )

    footprint_rows = footprints.loc[
        footprints["pair_id"].astype(str).eq(resolved_pair_id)
        & footprints["image_type"].astype(str).str.casefold().eq("thermal")
        & footprints["status"].astype(str).str.casefold().eq("ok")
    ].copy()
    if len(footprint_rows) != 1:
        return unavailable_native_luhk_result(
            image_id=image_id, pair_id=pair_id, shape=resolved_shape,
            reason=f"valid_thermal_footprint_count:{len(footprint_rows)}", source_paths=sources,
        )
    if not _image_matches(footprint_rows, image_id):
        return unavailable_native_luhk_result(
            image_id=image_id, pair_id=pair_id, shape=resolved_shape,
            reason="thermal_footprint_image_id_mismatch", source_paths=sources,
        )
    footprint = footprint_rows.iloc[0]
    bounds = np.array(
        [
            footprint["min_x_2326"], footprint["max_x_2326"],
            footprint["min_y_2326"], footprint["max_y_2326"],
        ],
        dtype=float,
    )
    if not np.isfinite(bounds).all() or bounds[1] <= bounds[0] or bounds[3] <= bounds[2]:
        return unavailable_native_luhk_result(
            image_id=image_id, pair_id=pair_id, shape=resolved_shape,
            reason="thermal_footprint_bounds_invalid", source_paths=sources,
        )

    pair_grid = pair_grid.reset_index(drop=True)
    origin_x_values = (
        pd.to_numeric(pair_grid["cell_min_x_2326"], errors="coerce").to_numpy(float)
        - pd.to_numeric(pair_grid["luhk_col"], errors="coerce").to_numpy(float) * LUHK_GRID_SIZE_M
    )
    origin_y_values = (
        pd.to_numeric(pair_grid["cell_max_y_2326"], errors="coerce").to_numpy(float)
        + pd.to_numeric(pair_grid["luhk_row"], errors="coerce").to_numpy(float) * LUHK_GRID_SIZE_M
    )
    if not np.isfinite(origin_x_values).all() or not np.isfinite(origin_y_values).all():
        return unavailable_native_luhk_result(
            image_id=image_id, pair_id=pair_id, shape=resolved_shape,
            reason="luhk_grid_transform_non_finite", source_paths=sources,
        )
    origin_x = float(np.median(origin_x_values))
    origin_y = float(np.median(origin_y_values))
    transform_residual = max(
        float(np.max(np.abs(origin_x_values - origin_x))),
        float(np.max(np.abs(origin_y_values - origin_y))),
    )
    if transform_residual > 1e-6:
        return unavailable_native_luhk_result(
            image_id=image_id, pair_id=pair_id, shape=resolved_shape,
            reason=f"luhk_grid_transform_inconsistent:{transform_residual:.9g}", source_paths=sources,
        )

    height, width = resolved_shape
    x_centers = bounds[0] + (np.arange(width, dtype=np.float64) + 0.5) * (bounds[1] - bounds[0]) / width
    y_centers = bounds[3] - (np.arange(height, dtype=np.float64) + 0.5) * (bounds[3] - bounds[2]) / height
    pixel_cols = np.floor((x_centers - origin_x) / LUHK_GRID_SIZE_M).astype(np.int32)
    pixel_rows = np.floor((origin_y - y_centers) / LUHK_GRID_SIZE_M).astype(np.int32)
    row_grid, col_grid = np.meshgrid(pixel_rows, pixel_cols, indexing="ij")
    keys = row_grid.astype(np.int64) * LUHK_KEY_MULTIPLIER + col_grid.astype(np.int64)

    cell_keys = (
        pd.to_numeric(pair_grid["luhk_row"], errors="coerce").astype(np.int64).to_numpy()
        * LUHK_KEY_MULTIPLIER
        + pd.to_numeric(pair_grid["luhk_col"], errors="coerce").astype(np.int64).to_numpy()
    )
    key_to_index = {int(key): index for index, key in enumerate(cell_keys)}
    unique_keys, inverse = np.unique(keys, return_inverse=True)
    unique_indices = np.array([key_to_index.get(int(key), -1) for key in unique_keys], dtype=np.int32)
    cell_index = unique_indices[inverse].reshape(resolved_shape)
    mapped = cell_index >= 0
    safe = np.where(mapped, cell_index, 0)

    legacy_cell_id = pair_grid["global_cell_id"].astype(str).to_numpy()[safe]
    legacy_raw_code = (
        pd.to_numeric(pair_grid["luhk_raw_code"], errors="coerce").fillna(-1).astype(np.int16).to_numpy()[safe]
    )
    legacy_category_name = pair_grid["luhk_category_name"].astype(str).to_numpy()[safe]
    legacy_row = pd.to_numeric(pair_grid["luhk_row"], errors="coerce").astype(np.int32).to_numpy()[safe]
    legacy_col = pd.to_numeric(pair_grid["luhk_col"], errors="coerce").astype(np.int32).to_numpy()[safe]
    group_ids = (
        pd.to_numeric(pair_grid["luhk_category_code"], errors="coerce").fillna(-1).astype(np.int16).to_numpy()[safe]
    )
    stable_by_group = np.array([LUHK_GROUP_CODES.get(index, "") for index in range(10)], dtype="<U48")
    labels = _empty_array(resolved_shape, "", "<U48")
    group_known = (group_ids >= 0) & (group_ids < len(stable_by_group))
    known = mapped & group_known
    labels[known] = stable_by_group[group_ids[known]]
    known &= labels != ""

    cell_ids = _empty_array(resolved_shape, "", "<U40")
    raw_codes = _empty_array(resolved_shape, -1, np.int16)
    category_names = _empty_array(resolved_shape, "", "<U96")
    luhk_rows = _empty_array(resolved_shape, -1, np.int32)
    luhk_cols = _empty_array(resolved_shape, -1, np.int32)
    cell_ids[known] = legacy_cell_id[known]
    raw_codes[known] = legacy_raw_code[known]
    category_names[known] = np.array([LUHK_CATEGORIES[value] for value in labels[known]], dtype="<U96")
    luhk_rows[known] = legacy_row[known]
    luhk_cols[known] = legacy_col[known]

    metadata = {
        "lookup_version": LUHK_LOOKUP_VERSION,
        "lookup_method": "approximate_north_up_thermal_pixel_center_to_official_10m_luhk_cell",
        "crs": "EPSG:2326",
        "grid_size_m": LUHK_GRID_SIZE_M,
        "native_shape": [height, width],
        "requested_pair_id": str(pair_id),
        "resolved_pair_id": resolved_pair_id,
        "pair_resolution": pair_resolution,
        "grid_origin_x_2326": origin_x,
        "grid_origin_y_2326": origin_y,
        "grid_transform_max_residual_m": transform_residual,
        "thermal_footprint_bounds_2326": {
            "min_x": float(bounds[0]), "max_x": float(bounds[1]),
            "min_y": float(bounds[2]), "max_y": float(bounds[3]),
        },
        "thermal_footprint_model": "metadata_derived_north_up_rectangle",
        "known_pixel_count": int(known.sum()),
        "unknown_pixel_count": int(known.size - known.sum()),
        "mapped_cell_pixel_count": int(mapped.sum()),
        "official_raw_codes": sorted({int(value) for value in raw_codes[known]}),
        "broad_codes": sorted({str(value) for value in labels[known]}),
        "temperature_aggregation_by_luhk_cell": False,
    }
    status = "available" if known.any() else "unavailable"
    reason = "" if known.any() else "no_recognized_official_luhk_pixels"
    return NativeLUHKResult(
        image_id=str(image_id),
        pair_id=resolved_pair_id,
        labels=labels,
        known_mask=known,
        cell_ids=cell_ids,
        raw_codes=raw_codes,
        category_names=category_names,
        luhk_rows=luhk_rows,
        luhk_cols=luhk_cols,
        cell_indices=cell_index,
        mapped_mask=mapped,
        provenance=LUHKProvenance.OFFICIAL_LOOKUP if known.any() else LUHKProvenance.UNKNOWN,
        status=status,
        unavailable_reason=reason,
        source_paths=sources,
        metadata=metadata,
        _legacy_arrays={
            "cell_id": legacy_cell_id,
            "class_code": legacy_raw_code,
            "class_name": legacy_category_name,
            "luhk_row": legacy_row,
            "luhk_col": legacy_col,
        },
    )


def load_native_luhk_result(
    project_root: Path,
    *,
    image_id: str,
    pair_id: str,
    shape: tuple[int, int],
    grid_path: Path | None = None,
    footprints_path: Path | None = None,
    raster_path: Path | None = None,
) -> NativeLUHKResult:
    """Load preserved official spatial inputs and build a native LUHK layer."""

    root = Path(project_root)
    grid_file = grid_path or root / DEFAULT_GRID_RELATIVE_PATH
    footprints_file = footprints_path or root / DEFAULT_FOOTPRINTS_RELATIVE_PATH
    raster_file = raster_path or root / DEFAULT_RASTER_RELATIVE_PATH
    sources = {
        "luhk_cell_mapping": grid_file.resolve().as_posix(),
        "thermal_footprints": footprints_file.resolve().as_posix(),
    }
    if raster_file.is_file():
        sources["official_luhk_raster"] = raster_file.resolve().as_posix()
    missing = [name for name, path in (("luhk_cell_mapping", grid_file), ("thermal_footprints", footprints_file)) if not path.is_file()]
    if missing:
        return unavailable_native_luhk_result(
            image_id=image_id, pair_id=pair_id, shape=shape,
            reason="source_files_missing:" + ",".join(missing), source_paths=sources,
        )
    try:
        grid = pd.read_excel(grid_file)
        footprints = pd.read_excel(footprints_file)
    except (OSError, ValueError, ImportError) as exc:
        return unavailable_native_luhk_result(
            image_id=image_id, pair_id=pair_id, shape=shape,
            reason=f"source_tables_unreadable:{type(exc).__name__}", source_paths=sources,
        )
    return build_native_luhk_result(
        image_id=image_id,
        pair_id=pair_id,
        shape=shape,
        grid=grid,
        footprints=footprints,
        source_paths=sources,
    )
