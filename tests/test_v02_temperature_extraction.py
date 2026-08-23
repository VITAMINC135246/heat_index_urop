from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image

from scripts.run_analysis import PILOT_TAT3_PARAMETERS, temperature_for_group

from scripts.workflow.temperature_extraction import (
    build_sdk_command,
    extract_temperature,
    load_temperature_override,
    load_report_parameter_row,
    TemperatureResult,
    temperature_qa,
)


PARAMETERS = {
    "distance_m": 10.0,
    "relative_humidity_percent": 70.0,
    "emissivity": 0.95,
    "ambient_temperature_c": 25.0,
    "reflected_temperature_c": 25.0,
}


class TemperatureExtractionTests(unittest.TestCase):
    def test_shared_sdk_command_and_mocked_float32_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            thermal = root / "image_T.JPG"
            Image.new("RGB", (3, 2), "gray").save(thermal)
            exe = root / "dji_irp.exe"
            exe.write_bytes(b"fake-sdk")
            raw = root / "out.raw"
            command = build_sdk_command(irp_exe=exe, thermal_path=thermal, raw_path=raw, parameters=PARAMETERS)
            self.assertEqual(command[command.index("--distance") + 1], "10.0")
            self.assertEqual(command[command.index("--ambient") + 1], "25.0")

            def runner(argv: list[str], **_kwargs: object) -> SimpleNamespace:
                output = Path(argv[argv.index("-o") + 1])
                np.arange(6, dtype=np.float32).tofile(output)
                return SimpleNamespace(returncode=0, stdout="ok", stderr="")

            result = extract_temperature(
                thermal_path=thermal, image_id="image", parameters=PARAMETERS,
                work_directory=root / "work", irp_exe=exe, runner=runner,
            )
            self.assertEqual(result.matrix.shape, (2, 3))
            self.assertEqual(result.metadata["ambient_temperature_c"], 25.0)
            self.assertTrue(result.metadata["sdk_tool_sha256"])

    def test_override_missing_ambient_and_failed_qa_are_retained(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "temperature.npy"
            np.save(path, np.arange(6, dtype=np.float32).reshape(2, 3))
            result = load_temperature_override(path, native_shape=(2, 3))
            self.assertFalse(result.metadata["delta_temperature_available"])
            self.assertIsNone(result.metadata["ambient_temperature_c"])
            with self.assertRaisesRegex(ValueError, "native thermal grid"):
                load_temperature_override(path, native_shape=(3, 2))
        status, flags = temperature_qa(np.ones((3, 3), dtype=np.float32))
        self.assertEqual(status, "fail")
        self.assertIn("all_constant", flags)

    def test_report_parameters_are_selected_by_image_without_intermediate_csv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.docx"
            report.write_bytes(b"fixture")
            row = {
                "image_id": "DJI_20260202091128_0058",
                "ambient_parse_status": "ok",
                "ambient_temperature_c": 10.8,
                "reflected_temperature_c": 10.8,
                "distance_m": 5,
                "emissivity": 0.95,
                "humidity_percent": 50,
                "humidity_use_status": "not_used_unreliable_tat3_export",
                "report_capture_datetime": "2026-02-02 09:11:28",
            }
            with patch("scripts.workflow.tat3_manual_measurement._ambient_entries", return_value=[row]):
                result = load_report_parameter_row(report, row["image_id"])
            self.assertEqual(result["ambient_temperature_c"], 10.8)
            self.assertEqual(result["relative_humidity_percent"], 50.0)
            self.assertEqual(result["distance_m"], 5.0)

    def test_missing_pilot_matrix_falls_back_to_pilot_tat3_parameters_and_sdk(self) -> None:
        image_id = "DJI_20260107143259_0005"
        expected = TemperatureResult(
            matrix=np.arange(6, dtype=np.float32).reshape(2, 3),
            metadata={"extraction_method": "DJI Thermal SDK"},
            qa_status="pass",
            qa_flags=[],
        )
        args = SimpleNamespace(
            tat3_report=[], tat3_params_csv="", irp_exe="", sdk_root="",
            sdk_config="config/part_d_sdk.local.json", keep_sdk_raw=False,
        )
        with (
            patch("scripts.run_analysis.legacy_temperature", return_value=None),
            patch("scripts.run_analysis.pilot_image_ids", return_value=[image_id]),
            patch("scripts.run_analysis.load_parameter_row", return_value=PARAMETERS) as load_parameters,
            patch("scripts.run_analysis.resolve_irp_exe", return_value=Path("dji_irp.exe")),
            patch("scripts.run_analysis.extract_temperature", return_value=expected) as extract,
        ):
            result = temperature_for_group(
                image_id=image_id,
                thermal_path=Path("pilot_T.JPG"),
                native_shape=(2, 3),
                overrides={},
                ambient_payload={},
                args=args,
            )
        load_parameters.assert_called_once_with(PILOT_TAT3_PARAMETERS, image_id)
        extract.assert_called_once()
        self.assertIs(result, expected)


if __name__ == "__main__":
    unittest.main()
