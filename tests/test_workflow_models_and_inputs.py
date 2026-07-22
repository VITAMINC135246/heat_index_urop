from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scripts.workflow.input_validation import discover_dataset_groups, validate_group
from scripts.workflow.models import GroupInput, ProcessingStatus, ValidationStatus


class InputValidationTests(unittest.TestCase):
    def make_image(self, path: Path, size: tuple[int, int] = (8, 6)) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, (100, 80, 60)).save(path)

    def test_valid_vt_group_returns_structured_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "DJI_20260717_session"
            visible = root / "DJI_20260717120000_0001_V.JPG"
            thermal = root / "DJI_20260717120000_0001_T.JPG"
            self.make_image(visible)
            self.make_image(thermal, (7, 5))
            record = validate_group(GroupInput("g1", str(visible), str(thermal), "synthetic"))
            self.assertIn(record.validation_status, {ValidationStatus.PASS, ValidationStatus.WARN})
            self.assertEqual(record.processing_status, ProcessingStatus.READY)
            self.assertTrue(record.thermal_valid)
            self.assertEqual(record.image_id, "DJI_20260717120000_0001")
            self.assertEqual(record.thermal_camera_metadata["width"], 7)
            self.assertEqual(record.thermal_camera_metadata["height"], 5)

    def test_missing_thermal_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            visible = root / "DJI_20260717120000_0001_V.JPG"
            thermal = root / "DJI_20260717120000_0001_T.JPG"
            self.make_image(visible)
            record = validate_group(GroupInput("g1", str(visible), str(thermal)))
            self.assertEqual(record.validation_status, ValidationStatus.FAIL)
            self.assertEqual(record.processing_status, ProcessingStatus.FAILED)
            self.assertFalse(record.thermal_valid)
            self.assertIn("missing_thermal_image", record.errors)

    def test_invalid_thermal_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            visible = root / "DJI_20260717120000_0001_V.JPG"
            thermal = root / "DJI_20260717120000_0001_T.JPG"
            self.make_image(visible)
            thermal.write_text("not an image", encoding="utf-8")
            record = validate_group(GroupInput("g1", str(visible), str(thermal)))
            self.assertEqual(record.validation_status, ValidationStatus.FAIL)
            self.assertTrue(any(value.startswith("invalid_thermal_image") for value in record.errors))
            self.assertFalse(record.thermal_valid)

    def test_dataset_discovery_retains_thermal_only_fallback_groups(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_image(root / "DJI_20260717120000_0001_V.JPG")
            self.make_image(root / "DJI_20260717120000_0001_T.JPG")
            self.make_image(root / "DJI_20260717120100_0002_T.JPG")
            groups = discover_dataset_groups(root, "dataset-a")
            self.assertEqual(len(groups), 2)
            self.assertEqual(groups[0].dataset_id, "dataset-a")
            self.assertEqual(groups[1].visible_path, "")

    def test_dataset_discovery_pairs_unique_adjacent_dji_timestamps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "DJI_202602020853_001"
            visible = root / "DJI_20260202091127_0058_V.JPG"
            thermal = root / "DJI_20260202091128_0058_T.JPG"
            self.make_image(visible)
            self.make_image(thermal)
            groups = discover_dataset_groups(root, "real-pattern")
            self.assertEqual(len(groups), 1)
            self.assertEqual(Path(groups[0].visible_path), visible)
            self.assertEqual(Path(groups[0].thermal_path), thermal)
            self.assertEqual(
                groups[0].metadata_record["discovery_pairing_method"],
                "session_sample_unique_timestamp_tolerance",
            )
            record = validate_group(groups[0])
            self.assertTrue(record.visible_valid)
            self.assertTrue(record.pairing_uncertain)

    def test_dataset_discovery_does_not_guess_between_ambiguous_visible_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_image(root / "DJI_20260202091127_0058_V.JPG")
            self.make_image(root / "DJI_20260202091129_0058_V.JPG")
            self.make_image(root / "DJI_20260202091128_0058_T.JPG")
            groups = discover_dataset_groups(root, "ambiguous")
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0].visible_path, "")
            self.assertEqual(groups[0].metadata_record["discovery_pairing_method"], "ambiguous_unpaired")
            self.assertEqual(groups[0].metadata_record["discovery_visible_candidate_count"], 2)


if __name__ == "__main__":
    unittest.main()
