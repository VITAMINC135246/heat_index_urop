from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from scripts.workflow.canonical_result import write_canonical_result
from scripts.workflow.capture_time import resolve_capture_time, select_capture_time_bundle
from scripts.workflow.models import ManualReviewStatus, ProcessingRoute, QAStatus, SourceMethod
from scripts.workflow.part_e_adapter import _compatible_frame
from scripts.workflow.pilot_adapter import resolve_pilot_capture_time


class CaptureTimeV032Tests(unittest.TestCase):
    def _image(self, path: Path, *, original: str = "", subsecond: str = "") -> None:
        image = Image.new("RGB", (5, 4), "gray")
        exif = Image.Exif()
        if original:
            exif[36867] = original  # DateTimeOriginal
        if subsecond:
            exif[37521] = subsecond  # SubsecTimeOriginal
        image.save(path, exif=exif)

    def test_exif_subsecond_precedes_dji_user_and_filename(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            thermal = Path(directory) / "DJI_20260717120000_0001_T.JPG"
            self._image(thermal, original="2026:07:17 11:22:33", subsecond="456")
            result = resolve_capture_time(
                thermal_path=thermal,
                dji_metadata_records=[{"capture_datetime": "2026-07-17 10:00:00"}],
                user_metadata={"capture_datetime": "2026-07-17 09:00:00"},
                default_timezone="Asia/Hong_Kong",
            )
            self.assertTrue(result.capture_time_valid)
            self.assertEqual(result.capture_time_source, "exif_subsec_datetime_original")
            self.assertIn("11:22:33.456", result.capture_time_local)
            self.assertIn("03:22:33.456", result.capture_time_utc)

    def test_pilot_adapter_does_not_overwrite_exif_with_part_a(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            thermal = Path(directory) / "thermal.jpg"
            visible = Path(directory) / "visible.jpg"
            self._image(thermal, original="2026:07:17 11:22:33", subsecond="456")
            self._image(visible)
            result = resolve_pilot_capture_time(
                thermal,
                visible,
                {
                    "capture_datetime": "2026-07-17T09:00:00+08:00",
                    "capture_time_local": "2026-07-17T09:00:00+08:00",
                    "capture_time_utc": "2026-07-17T01:00:00+00:00",
                    "capture_timezone": "Asia/Hong_Kong",
                    "capture_time_source": "part_a_capture_time_fallback",
                    "capture_time_valid": True,
                },
            )
            self.assertEqual(result["capture_time_source"], "exif_subsec_datetime_original")
            self.assertIn("11:22:33.456", result["capture_time_local"])
            self.assertIn("03:22:33.456", result["capture_time_utc"])

    def test_dji_metadata_precedes_user_and_filename_and_filename_is_last_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            thermal = Path(directory) / "DJI_20260717120000_0001_T.JPG"
            self._image(thermal)
            dji = resolve_capture_time(
                thermal_path=thermal,
                dji_metadata_records=[{"capture_datetime": "2026-07-17 10:00:00"}],
                user_metadata={"capture_datetime": "2026-07-17 09:00:00"},
            )
            self.assertEqual(dji.capture_time_source, "dji_metadata_record")
            self.assertIn("10:00:00", dji.capture_time_local)
            fallback = resolve_capture_time(thermal_path=thermal)
            self.assertEqual(fallback.capture_time_source, "dji_filename_timestamp")
            self.assertIn("12:00:00", fallback.capture_time_local)

    def test_explicitly_invalid_metadata_falls_through_to_next_priority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            thermal = Path(directory) / "DJI_20260717120000_0001_T.JPG"
            self._image(thermal)
            result = resolve_capture_time(
                thermal_path=thermal,
                dji_metadata_records=[
                    {
                        "capture_datetime": "2026-07-17 10:00:00",
                        "capture_time_source": "missing",
                        "capture_time_valid": False,
                    }
                ],
                user_metadata={
                    "capture_datetime": "2026-07-17 09:00:00",
                    "capture_timezone": "Asia/Hong_Kong",
                },
            )
            self.assertEqual(result.capture_time_source, "user_supplied_metadata")
            self.assertIn("09:00:00", result.capture_time_local)

    def test_aware_source_time_is_not_converted_to_analysis_default_timezone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            thermal = Path(directory) / "not-a-dji-name.jpg"
            self._image(thermal)
            result = resolve_capture_time(
                thermal_path=thermal,
                user_metadata={"capture_datetime": "2026-07-17T10:00:00+10:00"},
                default_timezone="Asia/Hong_Kong",
            )
            self.assertEqual(result.capture_time_source, "user_supplied_metadata")
            self.assertIn("T10:00:00+10:00", result.capture_time_local)
            self.assertIn("T00:00:00+00:00", result.capture_time_utc)
            self.assertNotEqual(result.capture_timezone, "Asia/Hong_Kong")

    def test_atomic_bundle_rejects_explicit_invalid_source_and_does_not_mix_fields(self) -> None:
        selected = select_capture_time_bundle(
            (
                {
                    "capture_datetime": "2026-07-17T01:00:00+00:00",
                    "capture_time_local": "2026-07-17T09:00:00+08:00",
                    "capture_timezone": "Asia/Hong_Kong",
                    "capture_time_source": "missing",
                    "capture_time_valid": False,
                },
                "",
            ),
            (
                {
                    "capture_datetime": "2026-07-17T12:00:00+10:00",
                    "capture_time_local": "2026-07-17T12:00:00+10:00",
                    "capture_time_utc": "2026-07-17T02:00:00+00:00",
                    "capture_timezone": "Australia/Sydney",
                    "capture_time_source": "exif_datetime_original",
                    "capture_time_valid": True,
                },
                "part_a_capture_time_fallback",
            ),
        )
        self.assertEqual(selected["capture_datetime"], "2026-07-17T12:00:00+10:00")
        self.assertEqual(selected["capture_time_utc"], "2026-07-17T02:00:00+00:00")
        self.assertEqual(selected["capture_timezone"], "Australia/Sydney")
        self.assertEqual(selected["capture_time_source"], "part_a_capture_time_fallback")

    def test_atomic_bundle_rejects_contradictory_local_and_utc_instants(self) -> None:
        selected = select_capture_time_bundle(
            (
                {
                    "capture_datetime": "2026-07-17T12:00:00+08:00",
                    "capture_time_local": "2026-07-17T12:00:00+08:00",
                    "capture_time_utc": "2026-07-17T12:00:00+00:00",
                    "capture_timezone": "Asia/Hong_Kong",
                    "capture_time_source": "dji_metadata_record",
                    "capture_time_valid": True,
                },
                "",
            ),
            (
                {
                    "capture_time": "2026-07-17T13:00:00",
                    "capture_timezone": "Asia/Hong_Kong",
                },
                "part_a_capture_time_fallback",
            ),
        )
        self.assertEqual(selected["capture_time_source"], "part_a_capture_time_fallback")
        self.assertEqual(selected["capture_time_local"], "2026-07-17T13:00:00+08:00")
        self.assertEqual(selected["capture_time_utc"], "2026-07-17T05:00:00+00:00")
        self.assertTrue(selected["timezone_assumption"])

    def test_canonical_capture_bundle_falls_back_atomically_to_part_a(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temperature = np.arange(6, dtype=np.float32).reshape(2, 3)
            labels = np.ones((2, 3), dtype=np.int16)
            known = np.ones((2, 3), dtype=bool)
            manifest, _ = write_canonical_result(
                output_root=Path(directory),
                image_id="atomic-time",
                group_id="g",
                pair_id="p",
                dataset_id="fixture",
                visible_path="v.jpg",
                thermal_path="t.jpg",
                temperature=temperature,
                labels=labels,
                known_mask=known,
                processing_route=ProcessingRoute.NORMAL_VT,
                source_method=SourceMethod.VISIBLE_REVIEW,
                review_status=ManualReviewStatus.ACCEPTED,
                qa_status=QAStatus.PASS,
                configuration_hash="fixture",
                source_file_hashes={},
                surface_cover_names={1: "roof"},
                temperature_metadata={
                    "capture_datetime": "2026-07-17T01:00:00+00:00",
                    "capture_time_local": "stale-temperature-local-time",
                    "capture_timezone": "UTC",
                    "capture_time_source": "missing",
                    "capture_time_valid": False,
                },
                part_a={
                    "capture_datetime": "2026-07-17T12:00:00+10:00",
                    "capture_time_local": "2026-07-17T12:00:00+10:00",
                    "capture_time_utc": "2026-07-17T02:00:00+00:00",
                    "capture_timezone": "Australia/Sydney",
                    "capture_time_source": "exif_datetime_original",
                    "capture_time_valid": True,
                },
            )
            self.assertEqual(manifest.capture_datetime, "2026-07-17T12:00:00+10:00")
            self.assertEqual(manifest.capture_time_local, "2026-07-17T12:00:00+10:00")
            self.assertEqual(manifest.capture_time_utc, "2026-07-17T02:00:00+00:00")
            self.assertEqual(manifest.capture_timezone, "Australia/Sydney")
            self.assertEqual(manifest.capture_time_source, "part_a_capture_time_fallback")

    def test_legacy_part_a_capture_time_fallback_is_explicit_in_part_e(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            temperature = np.arange(6, dtype=np.float32).reshape(2, 3)
            labels = np.ones((2, 3), dtype=np.int16)
            known = np.ones((2, 3), dtype=bool)
            manifest, path = write_canonical_result(
                output_root=root,
                image_id="legacy-time",
                group_id="g",
                pair_id="p",
                dataset_id="fixture",
                visible_path="v.jpg",
                thermal_path="t.jpg",
                temperature=temperature,
                labels=labels,
                known_mask=known,
                processing_route=ProcessingRoute.NORMAL_VT,
                source_method=SourceMethod.VISIBLE_REVIEW,
                review_status=ManualReviewStatus.ACCEPTED,
                qa_status=QAStatus.PASS,
                configuration_hash="fixture",
                source_file_hashes={},
                surface_cover_names={1: "roof"},
                part_a={"capture_time": "2026-07-17T12:00:00", "capture_timezone": "Asia/Hong_Kong"},
                ambient_metadata={
                    "ambient_temperature_c": 26.0,
                    "source": "TAT3 exported ambient parameter",
                    "definition": "provisional exported parameter",
                    "source_record": "report.docx",
                    "validation_status": "provisional_user_supplied_report_parameter",
                    "timezone": "Asia/Hong_Kong",
                },
            )
            # Simulate a pre-v0.3.2 manifest whose time existed only under Part A.
            manifest.capture_datetime = ""
            manifest.capture_time_local = ""
            manifest.capture_time_utc = ""
            manifest.capture_time_source = ""
            manifest.capture_time_valid = False
            manifest.temperature_metadata = {}
            frame = pd.read_parquet(path.parent / "pixels.parquet")
            frame["capture_datetime"] = "1999-01-01T00:00:00"
            frame["capture_time_local"] = "stale-local"
            frame["capture_time_utc"] = "stale-utc"
            frame["capture_timezone"] = "stale-zone"
            frame["capture_time_source"] = "stale-source"
            frame["timezone_assumption"] = "stale-assumption"
            frame["capture_time_valid"] = False
            compatible = _compatible_frame(frame, manifest)
            self.assertEqual(compatible["capture_datetime"].iloc[0], "2026-07-17T12:00:00+08:00")
            self.assertEqual(compatible["capture_time_local"].iloc[0], "2026-07-17T12:00:00+08:00")
            self.assertEqual(compatible["capture_time_utc"].iloc[0], "2026-07-17T04:00:00+00:00")
            self.assertEqual(compatible["capture_timezone"].iloc[0], "Asia/Hong_Kong")
            self.assertEqual(compatible["capture_time_source"].iloc[0], "part_a_capture_time_fallback")
            self.assertTrue(str(compatible["timezone_assumption"].iloc[0]))
            self.assertEqual(
                compatible["ambient_data_qa_status"].iloc[0],
                "provisional_user_supplied_report_parameter",
            )
            self.assertEqual(compatible["ambient_source_record"].iloc[0], "report.docx")
            self.assertEqual(compatible["ambient_provenance"].iloc[0], "canonical_manifest_ambient_metadata")
            self.assertTrue(bool(compatible["capture_time_valid"].iloc[0]))
            self.assertEqual(compatible["roi_target_pixel_count"].iloc[0], 6)
            self.assertEqual(compatible["roi_target_coverage_fraction"].iloc[0], 1.0)
            self.assertEqual(
                compatible["roi_mask_sha256"].iloc[0],
                manifest.artifacts["target_mask"].sha256,
            )


if __name__ == "__main__":
    unittest.main()
