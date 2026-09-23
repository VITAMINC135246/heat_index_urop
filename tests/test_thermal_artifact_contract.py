"""Thermal provenance and cache lifecycle tests using deliberately synthetic pixels."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from heat_index.io.pilot import adapt_pilot_image
from heat_index.pipeline.workflow import temperature_for_group
from heat_index.thermal.artifact import load_thermal_artifact, sidecar_path, write_thermal_artifact
from heat_index.thermal.extraction import (
    TemperatureResult,
    legacy_summary_metadata,
    load_legacy_temperature,
    load_temperature_override,
    resolve_irp_exe,
)


PARAMETERS = {
    "distance_m": 5.0,
    "relative_humidity_percent": 50.0,
    "emissivity": 0.95,
    "ambient_temperature_c": 11.0,
    "reflected_temperature_c": 11.0,
}


def synthetic_result(*, source_hash: str | None = None) -> TemperatureResult:
    return TemperatureResult(
        matrix=np.arange(6, dtype=np.float32).reshape(2, 3),
        metadata={
            **PARAMETERS,
            "extraction_method": "synthetic_test_only",
            "temperature_definition": "per-pixel radiometric surface temperature",
            "temperature_unit": "degC",
            "parameter_source": "synthetic fixture",
            "source_image_sha256": source_hash,
        },
        qa_status="pass",
        qa_flags=[],
    )


@pytest.mark.unit
def test_standard_artifact_moves_as_a_pair_and_rejects_changed_pixels_or_inputs(tmp_path: Path) -> None:
    source = tmp_path / "original_T.JPG"
    source.write_bytes(b"synthetic source image")
    from heat_index.provenance.result_index import sha256_file

    original = synthetic_result(source_hash=sha256_file(source))
    matrix = tmp_path / "windows" / "image_temperature_celsius.npy"
    sidecar = write_thermal_artifact(matrix, original, image_id="image")
    written = json.loads(sidecar.read_text(encoding="utf-8"))
    assert written["cache_version"] == 1
    assert written["producer_version"]
    assert written["source_image_sha256"] == original.metadata["source_image_sha256"]
    destination = tmp_path / "mac"
    destination.mkdir()
    moved_matrix = destination / matrix.name
    shutil.copyfile(matrix, moved_matrix)
    shutil.copyfile(sidecar, destination / sidecar.name)

    loaded = load_thermal_artifact(
        moved_matrix,
        image_id="image",
        native_shape=(2, 3),
        expected_parameters=PARAMETERS,
        source_image_path=source,
    )
    np.testing.assert_array_equal(loaded.matrix, original.matrix)
    assert loaded.metadata["provenance_binding"] == "verified"
    assert loaded.metadata["parameter_source"] == "synthetic fixture"

    with pytest.raises(ValueError, match="incompatible radiometric parameters"):
        load_thermal_artifact(moved_matrix, expected_parameters={**PARAMETERS, "emissivity": 0.96})
    with pytest.raises(ValueError, match="image ID"):
        load_thermal_artifact(moved_matrix, image_id="other")
    other_source = tmp_path / "other_T.JPG"
    other_source.write_bytes(b"different source")
    with pytest.raises(ValueError, match="source image checksum"):
        load_thermal_artifact(moved_matrix, source_image_path=other_source)

    changed = original.matrix.copy()
    changed[0, 0] += 1
    np.save(moved_matrix, changed)
    with pytest.raises(ValueError, match="checksum"):
        load_thermal_artifact(moved_matrix)


@pytest.mark.unit
def test_sidecar_tampering_and_missing_sidecar_fail_closed(tmp_path: Path) -> None:
    matrix = tmp_path / "image_temperature_celsius.npy"
    sidecar = write_thermal_artifact(matrix, synthetic_result(), image_id="image")
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    payload["metadata"]["emissivity"] = 0.96
    sidecar.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint"):
        load_thermal_artifact(matrix)
    payload["metadata"]["emissivity"] = PARAMETERS["emissivity"]
    payload["metadata"]["image_id"] = "different"
    sidecar.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="image ID disagrees"):
        load_thermal_artifact(matrix)
    sidecar.unlink()
    with pytest.raises(FileNotFoundError, match="sidecar"):
        load_thermal_artifact(matrix)


@pytest.mark.unit
def test_historical_pilot_summary_recovers_parameters_but_marks_unbound_matrix(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    summary = pd.read_csv(
        repository / "outputs" / "part_d" / "summaries" / "part_d_tat3_parameter_temperature_extraction_summary.csv",
        keep_default_na=False,
    )
    row = summary.iloc[0]
    image_id = str(row["image_id"])
    matrix = tmp_path / f"{image_id}_temperature_celsius.npy"
    np.save(matrix, np.arange(6, dtype=np.float32).reshape(2, 3))
    loaded = load_legacy_temperature(matrix, row, image_id=image_id, native_shape=(2, 3))
    expected = legacy_summary_metadata(row)
    assert loaded.metadata["provenance_binding"] == "legacy_unverified"
    assert loaded.metadata["temperature_definition"] == "per-pixel radiometric surface temperature"
    assert loaded.metadata["temperature_unit"] == "Celsius interpreted from SDK measure output"
    assert loaded.metadata["source_report"] == row["tat3_parameter_source_report"]
    for key in PARAMETERS:
        assert float(loaded.metadata[key]) == float(expected[key])

    # The recovered summary is useful provenance, but a standard sidecar with
    # different parameters must never be relabeled as the accepted pilot run.
    changed = synthetic_result()
    changed.metadata["temperature_unit"] = expected["temperature_unit"]
    changed.metadata["emissivity"] = 0.96
    write_thermal_artifact(matrix, changed, image_id=image_id)
    with pytest.raises(ValueError, match="incompatible radiometric parameters"):
        load_legacy_temperature(matrix, row, image_id=image_id)


@pytest.mark.integration
def test_pilot_adapter_preserves_historical_temperature_and_ambient_definitions(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    row = pd.read_csv(
        repository / "outputs" / "part_d" / "summaries" / "part_d_tat3_parameter_temperature_extraction_summary.csv",
        keep_default_na=False,
    ).iloc[0].copy()
    image_id = str(row["image_id"])
    matrix_path = tmp_path / "data" / "processed" / "part_d" / "temperature_matrices" / f"{image_id}_temperature_celsius.npy"
    matrix_path.parent.mkdir(parents=True)
    np.save(matrix_path, np.arange(6, dtype=np.float32).reshape(2, 3))
    row["npy_path"] = str(matrix_path.relative_to(tmp_path))
    labels_path = tmp_path / "labels.npy"
    np.save(labels_path, np.ones((2, 3), dtype=np.int16))
    pairs = pd.DataFrame([{"image_id": image_id, "pair_id": "synthetic_pair", "v_path": "v.jpg", "t_path": "t.jpg"}])
    masks = pd.DataFrame([{
        "image_id": image_id,
        "usable_for_part_d": "yes",
        "class_mask_thermal_grid_npy_path": str(labels_path),
        "shadow_mask_thermal_grid_npy_path": "missing_shadow.npy",
    }])
    mapping = pd.DataFrame([{"class_id": 1, "class_name": "synthetic_cover"}])
    thermal_summary = pd.DataFrame([row])
    luhk = SimpleNamespace(
        labels=np.zeros((2, 3), dtype=np.int16), known_mask=np.zeros((2, 3), dtype=bool),
        category_names={}, cell_ids=np.zeros((2, 3), dtype=np.int16),
        raw_codes=np.zeros((2, 3), dtype=np.int16), provenance=SimpleNamespace(value="unknown"),
        metadata={}, status="unavailable", unavailable_reason="synthetic", spatial_uncertainty="unknown",
        source_paths=[],
    )
    with (
        patch("heat_index.io.pilot.pd.read_excel", side_effect=[pairs, masks, mapping]),
        patch("heat_index.io.pilot.pd.read_csv", return_value=thermal_summary),
        patch("heat_index.io.pilot.pilot_source_paths", return_value=[]),
        patch("heat_index.io.pilot.load_native_luhk_result", return_value=luhk),
        patch("heat_index.io.pilot.resolve_pilot_capture_time", return_value={}),
        patch("heat_index.io.pilot.write_canonical_result", return_value=(None, tmp_path / "manifest.json")) as write,
    ):
        adapt_pilot_image(tmp_path, image_id)
    temperature_metadata = write.call_args.kwargs["temperature_metadata"]
    ambient_metadata = write.call_args.kwargs["ambient_metadata"]
    assert temperature_metadata["temperature_definition"] == "per-pixel radiometric surface temperature"
    assert temperature_metadata["temperature_unit"] == "Celsius interpreted from SDK measure output"
    assert temperature_metadata["provenance_binding"] == "legacy_unverified"
    assert ambient_metadata["source"] == "TAT3 exported ambient parameter"
    assert ambient_metadata["source_record"] == row["tat3_parameter_source_report"]


@pytest.mark.integration
def test_explicit_tat3_parameters_bypass_old_pilot_cache_and_write_bound_artifact(tmp_path: Path) -> None:
    image_id = "synthetic_image"
    artifact = tmp_path / "thermal" / f"{image_id}_temperature_celsius.npy"
    args = SimpleNamespace(
        tat3_report=[], tat3_params_csv="parameters.csv", irp_exe="", sdk_root="",
        sdk_config="", keep_sdk_raw=False,
    )
    result = synthetic_result()
    with (
        patch("heat_index.pipeline.workflow.legacy_temperature") as legacy,
        patch("heat_index.pipeline.workflow.load_parameter_row", return_value=PARAMETERS),
        patch("heat_index.pipeline.workflow.resolve_irp_exe", return_value=tmp_path / "dji_irp.exe"),
        patch("heat_index.pipeline.workflow.extract_temperature", return_value=result),
    ):
        actual = temperature_for_group(
            image_id=image_id,
            thermal_path=tmp_path / "image_T.JPG",
            native_shape=(2, 3),
            overrides={},
            ambient_payload={},
            args=args,
            artifact_path=artifact,
        )
    legacy.assert_not_called()
    assert actual is result
    assert sidecar_path(artifact).is_file()
    np.testing.assert_array_equal(load_thermal_artifact(artifact, image_id=image_id, expected_parameters=PARAMETERS).matrix, result.matrix)


@pytest.mark.unit
def test_windows_dji_boundary_does_not_block_precomputed_numpy(tmp_path: Path) -> None:
    if sys.platform == "win32":
        pytest.skip("This boundary is exercised on non-Windows hosts.")
    with pytest.raises(RuntimeError, match="requires Windows"):
        resolve_irp_exe(irp_exe=str(tmp_path / "dji_irp.exe"))
    path = tmp_path / "provided.npy"
    np.save(path, np.arange(6, dtype=np.float32).reshape(2, 3))
    loaded = load_temperature_override(path, native_shape=(2, 3))
    assert loaded.metadata["provenance_binding"] == "unverified_npy"
    assert loaded.metadata["temperature_definition"] == ""
