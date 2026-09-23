"""Replay a Windows-recovered, main-accepted pilot snapshot when it is supplied.

The absent active manifest is an explicit certification blocker, not a reason
to manufacture reference outputs from this branch. This replay compares
accepted numerical and scientific metadata outputs; thermal sidecar binding is
tested separately in the thermal artifact tests.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.workflow.pilot_adapter import adapt_pilot_image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "accepted_real"
ACTIVE_MANIFEST = FIXTURE_ROOT / "manifest.json"
FLOAT_ATOL_C = 2e-6  # Existing accepted pilot matrix assertion uses this float32 bound.


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fixture_path(relative: str) -> Path:
    candidate = (FIXTURE_ROOT / relative).resolve()
    if not candidate.is_relative_to(FIXTURE_ROOT.resolve()):
        raise AssertionError(f"Fixture path leaves accepted_real/: {relative}")
    return candidate


def _basename(value: str) -> str:
    return str(value).replace("\\", "/").rsplit("/", 1)[-1]


def _read_active_manifest() -> dict:
    if not ACTIVE_MANIFEST.is_file():
        pytest.skip(
            "Accepted real fixture is unavailable: recover the Windows/main snapshot "
            "and create tests/fixtures/accepted_real/manifest.json."
        )
    spec = json.loads(ACTIVE_MANIFEST.read_text(encoding="utf-8"))
    assert spec.get("schema_version") == 1
    assert spec.get("reference_branch") == "main"
    assert len(str(spec.get("reference_commit", ""))) == 40
    assert str(spec.get("reference_run_id", "")).strip()
    assert not str(spec["reference_run_id"]).startswith("REPLACE_")
    assert spec.get("cases"), "An active accepted-real manifest must contain cases."
    return spec


def _check_snapshot_hashes(case: dict, accepted_dir: Path) -> None:
    expected = case.get("accepted_sha256") or {}
    required = {
        "manifest.json",
        "temperature.npy",
        "surface_cover_labels.npy",
        "surface_cover_known_mask.npy",
        "target_mask.npy",
        "luhk_labels.npy",
        "luhk_known_mask.npy",
        "pixels.parquet",
    }
    assert required <= expected.keys(), f"Missing accepted SHA-256 entries: {sorted(required - expected.keys())}"
    for name, digest in expected.items():
        path = accepted_dir / name
        assert path.is_file(), f"Accepted main artifact missing: {path}"
        assert len(digest) == 64 and _sha256(path) == digest, f"Accepted artifact hash changed: {path}"


def _compare_array(accepted_dir: Path, actual_dir: Path, name: str) -> None:
    accepted = np.load(accepted_dir / name, allow_pickle=False)
    actual = np.load(actual_dir / name, allow_pickle=False)
    assert actual.shape == accepted.shape, name
    if name == "temperature.npy":
        np.testing.assert_allclose(actual, accepted, rtol=0, atol=FLOAT_ATOL_C, equal_nan=True)
    else:
        np.testing.assert_array_equal(actual, accepted, err_msg=name)


def _compare_pixels(accepted_dir: Path, actual_dir: Path, image_id: str) -> None:
    accepted = pd.read_parquet(accepted_dir / "pixels.parquet").sort_values(
        ["thermal_row", "thermal_col"]
    ).reset_index(drop=True)
    actual = pd.read_parquet(actual_dir / "pixels.parquet").sort_values(
        ["thermal_row", "thermal_col"]
    ).reset_index(drop=True)
    assert len(actual) == len(accepted)
    assert set(accepted.columns) <= set(actual.columns), sorted(set(accepted.columns) - set(actual.columns))
    assert accepted["image_id"].eq(image_id).all() and actual["image_id"].eq(image_id).all()
    numeric_science = {"temperature_c", "ambient_temperature_c", "delta_t_c"}
    assert numeric_science <= set(accepted.columns)
    for column in accepted.columns:
        if column in numeric_science:
            np.testing.assert_allclose(
                actual[column].to_numpy(dtype=float),
                accepted[column].to_numpy(dtype=float),
                rtol=0,
                atol=FLOAT_ATOL_C,
                equal_nan=True,
                err_msg=column,
            )
        else:
            pd.testing.assert_series_equal(actual[column], accepted[column], check_dtype=False, obj=column)

    # Grouped ΔT is checked independently of row-wise agreement. Summing
    # float32 pixel values in float64 may vary slightly by platform.
    def cover_summary(frame: pd.DataFrame) -> pd.DataFrame:
        selected = frame.loc[frame["analysis_eligible"].astype(bool)]
        return selected.groupby("surface_cover_class_id", sort=True)["delta_t_c"].agg(
            ["count", "mean"]
        )

    expected_summary = cover_summary(accepted)
    actual_summary = cover_summary(actual)
    pd.testing.assert_index_equal(actual_summary.index, expected_summary.index)
    pd.testing.assert_series_equal(actual_summary["count"], expected_summary["count"])
    np.testing.assert_allclose(
        actual_summary["mean"].to_numpy(float),
        expected_summary["mean"].to_numpy(float),
        rtol=0,
        atol=1e-6,
        equal_nan=True,
    )


@pytest.mark.scientific_regression
def test_main_accepted_pilot_snapshot_replays_on_phase2(tmp_path: Path) -> None:
    spec = _read_active_manifest()
    for case in spec["cases"]:
        image_id = str(case["image_id"])
        accepted_dir = _fixture_path(str(case["accepted_dir"]))
        _check_snapshot_hashes(case, accepted_dir)
        accepted_manifest = json.loads((accepted_dir / "manifest.json").read_text(encoding="utf-8"))
        assert accepted_manifest["image_id"] == image_id
        expected_shape = tuple(case["expected_shape"])
        assert expected_shape == (accepted_manifest["image_height"], accepted_manifest["image_width"])

        _actual, actual_manifest_path = adapt_pilot_image(
            PROJECT_ROOT, image_id, output_root=tmp_path, write_pixels_parquet=True
        )
        actual_dir = actual_manifest_path.parent
        actual_manifest = json.loads(actual_manifest_path.read_text(encoding="utf-8"))
        for field in (
            "image_id", "pair_id", "image_height", "image_width", "processing_route",
            "source_method", "review_status", "qa_status", "temperature_source",
            "scene_correspondence", "coverage_class", "known_pixel_count",
            "unknown_pixel_count", "target_pixel_count",
        ):
            assert actual_manifest[field] == accepted_manifest[field], f"{image_id}: {field}"
        for field in ("visible_path", "thermal_path"):
            assert _basename(actual_manifest[field]) == _basename(accepted_manifest[field]), f"{image_id}: {field}"
        for section, key_name in (
            ("temperature_metadata", "protected_temperature_metadata"),
            ("ambient_metadata", "protected_ambient_metadata"),
        ):
            keys = case.get(key_name)
            assert keys, f"{image_id}: specify the accepted scientific provenance keys in {key_name}"
            source_keys = {
                "source_report", "parameter_source", "measurement_parameter_source",
                "parameters", "thermal_parameters", "radiometric_parameters",
                "source_image", "source_image_sha256", "matrix_sha256", "cache_version",
            }
            keys = set(keys) | (source_keys & accepted_manifest[section].keys())
            for key in keys:
                assert key in accepted_manifest[section], f"{image_id}: main reference lacks {section}.{key}"
                assert actual_manifest[section].get(key) == accepted_manifest[section][key], (
                    f"{image_id}: {section}.{key}"
                )
        assert actual_manifest["part_b"] == accepted_manifest["part_b"], f"{image_id}: Part B alignment"

        for name in (
            "temperature.npy", "surface_cover_labels.npy", "surface_cover_known_mask.npy",
            "target_mask.npy", "luhk_labels.npy", "luhk_known_mask.npy",
        ):
            _compare_array(accepted_dir, actual_dir, name)
        if (accepted_dir / "shadow_mask.npy").is_file():
            assert "shadow_mask.npy" in case["accepted_sha256"]
            _compare_array(accepted_dir, actual_dir, "shadow_mask.npy")
        _compare_pixels(accepted_dir, actual_dir, image_id)
