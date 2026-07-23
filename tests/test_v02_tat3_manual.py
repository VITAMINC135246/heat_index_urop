from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.workflow.legacy_loader import load_numbered_script
from scripts.workflow.tat3_manual_measurement import parse_tat3_report, write_temporary_tat3_bundle


PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGE_ID = "DJI_20260717120000_0001"


class TAT3ManualParserTests(unittest.TestCase):
    def parse(self, root: Path, text: str):
        report = root / "report.txt"
        report.write_text(f"{IMAGE_ID}_T.JPG\n{text}\n", encoding="utf-8")
        return parse_tat3_report(
            report,
            expected_image_id=IMAGE_ID,
            target_name="HKUST soccer field",
            luhk_code="gic_open_space",
            luhk_category="GIC / open space",
            luhk_provenance="user_supplied_luhk",
            surface_cover_category="grass_low_vegetation",
        )

    def test_point_multiple_points_region_and_mixed_fixtures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            point = self.parse(root, "Ambient Temperature: 20 C\nPoint P1: x=12, y=34; temperature=25.5 C")
            self.assertEqual(point.measurements["measurement_type"].tolist(), ["manual_tat3_point"])
            self.assertAlmostEqual(float(point.measurements.iloc[0]["delta_t_c"]), 5.5)
            multiple = self.parse(
                root, "Ambient Temperature: 20 C\nPoint P1: x=1, y=2; temperature=21 C\nPoint P2: x=3, y=4; temperature=22 C"
            )
            self.assertEqual(len(multiple.measurements), 2)
            region = self.parse(
                root, "Ambient Temperature: 20 C\nRegion R1: geometry=polygon[(1,2),(3,4)]; min=21 max=30 mean=25 C"
            )
            self.assertEqual(len(region.measurements), 3)
            self.assertEqual(set(region.measurements["temperature_statistic"]), {"min", "max", "mean"})
            mixed = self.parse(
                root,
                "Ambient Temperature: 20 C\nPoint P1: temperature=24 C\n"
                "Region R1: geometry=rectangle(1,2,3,4); min=21 max=30 mean=25 C",
            )
            self.assertEqual(set(mixed.measurements["measurement_type"]), {"manual_tat3_point", "manual_tat3_region"})
            point_without_coordinates = mixed.measurements.loc[mixed.measurements["measurement_type"].eq("manual_tat3_point")].iloc[0]
            self.assertTrue(np.isnan(point_without_coordinates["point_x"]))

    def test_missing_ambient_mismatch_units_and_duplicate_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = self.parse(root, "Point P1: x=1, y=2; temperature=21 C")
            self.assertTrue(np.isnan(missing.measurements.iloc[0]["delta_t_c"]))
            with self.assertRaisesRegex(ValueError, "Celsius"):
                self.parse(root, "Point P1: x=1, y=2; temperature=72 F")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                self.parse(
                    root, "Point P1: x=1, y=2; temperature=21 C\nPoint P1: x=2, y=3; temperature=22 C"
                )
            report = root / "mismatch.txt"
            report.write_text("DJI_20260717120000_9999_T.JPG\nPoint P1: temperature=21 C", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "do not include"):
                parse_tat3_report(
                    report, expected_image_id=IMAGE_ID, target_name="t", luhk_code="gic_open_space",
                    luhk_category="GIC / open space", luhk_provenance="user_supplied_luhk",
                    surface_cover_category="grass_low_vegetation",
                )

    def test_temporary_bundle_does_not_touch_persistent_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index = root / "canonical_result_index.json"
            index.write_text(json.dumps({"results": {"existing": {"keep": True}}}), encoding="utf-8")
            before = index.read_bytes()
            result = self.parse(root, "Ambient Temperature: 20 C\nPoint P1: x=1, y=2; temperature=21 C")
            paths = write_temporary_tat3_bundle(result, root / "temporary_tat3")
            manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
            self.assertEqual(manifest["persistence_scope"], "temporary_session")
            self.assertTrue(paths["measurements"].is_file())
            self.assertTrue(paths["plot"].is_file())
            self.assertTrue(paths["plot"].with_suffix(".pdf").is_file())
            self.assertTrue(paths["analysis"].is_file())
            self.assertTrue(manifest["plot_spatial_location_available"])
            self.assertIn("manual_measurement_extremes.png", manifest["artifacts"])
            self.assertEqual(index.read_bytes(), before)
            self.assertIn("within-image spatial measurements", manifest["temporal_observation_policy"])

    def test_missing_coordinates_are_reported_without_invented_locations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.parse(root, "Ambient Temperature: 20 C\nPoint P1: temperature=21 C")
            paths = write_temporary_tat3_bundle(result, root / "temporary_tat3")
            manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
            summary = pd.read_csv(paths["extreme_summary"])
            coordinates = pd.read_csv(paths["extreme_coordinates"])
            self.assertFalse(bool(manifest["plot_spatial_location_available"]))
            self.assertFalse(bool(summary.iloc[0]["spatial_location_available"]))
            self.assertTrue(coordinates.empty)
            self.assertIn("no location was invented", paths["analysis"].read_text(encoding="utf-8").casefold())


@pytest.mark.local_integration
def test_named_local_ambient_reports_have_185_entries_and_no_manual_measurements() -> None:
    root = PROJECT_ROOT / "data" / "local_external" / "tat3_reports" / "raw"
    expected = {
        "combined_report__2026_07_15_22_43_23.docx": 144,
        "combined_report__2026_07_16_20_19_15.docx": 19,
        "combined_report__2026_07_17_01_05_05.docx": 22,
    }
    if not all((root / name).is_file() for name in expected):
        pytest.skip("Named local TAT3 ambient reports are not available.")
    legacy = load_numbered_script(
        "scripts/part_d/03_parse_tat3_ambient_temperature_reports.py",
        "heat_index_tat3_local_regression",
    )
    total = 0
    for name, count in expected.items():
        path = root / name
        entries = legacy.split_report_entries(path)
        assert len(entries) == count
        total += len(entries)
        first = legacy.parse_report_entry(entries[0])
        result = parse_tat3_report(
            path, expected_image_id=str(first["image_id"]), target_name="local parser regression",
            luhk_code="gic_open_space", luhk_category="GIC / open space",
            luhk_provenance="user_supplied_luhk", surface_cover_category="grass_low_vegetation",
        )
        assert result.manifest["measurement_layout_status"] == "ambient_metadata_only"
        assert result.measurements.empty
    assert total == 185
