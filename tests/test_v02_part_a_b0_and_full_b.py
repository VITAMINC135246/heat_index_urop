from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

from scripts.workflow.input_validation import validate_group
from scripts.workflow.models import (
    ContentTriageState,
    CoverageClass,
    GroupInput,
    ManualReviewStatus,
    PartB0Result,
    PartBDecision,
    ProcessingRoute,
    ProcessingStatus,
    SceneCorrespondence,
)
from scripts.workflow.part_b_adapter import run_full_part_b
from scripts.workflow.part_b_correspondence import (
    apply_part_b0_review,
    triage_content_correspondence,
    write_part_b0_result,
)
from scripts.workflow.routing import route_after_part_a, route_after_part_b0, route_group


class PartAAndB0Tests(unittest.TestCase):
    def make_pair(self, root: Path) -> tuple[Path, Path]:
        visible = root / "DJI_20260717120000_0001_V.JPG"
        thermal = root / "DJI_20260717120000_0001_T.JPG"
        Image.new("RGB", (12, 9), "green").save(visible)
        Image.new("RGB", (7, 5), "gray").save(thermal)
        return visible, thermal

    def test_part_a_metadata_and_native_shape_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            visible, thermal = self.make_pair(Path(directory))
            group = GroupInput(
                "g", str(visible), str(thermal), "d",
                metadata_record={
                    "relative_altitude": "42.5",
                    "gps_latitude": "22.33",
                    "gps_longitude": "114.26",
                    "camera_model": "Matrice 4T",
                    "focal_length": "24",
                    "metadata_source": "synthetic_exiftool",
                },
            )
            record = validate_group(group, temperature_shape=(5, 7))
            self.assertTrue(record.thermal_valid)
            self.assertAlmostEqual(record.altitude_m or 0, 42.5)
            self.assertEqual(record.metadata_source, "synthetic_exiftool")
            mismatch = validate_group(group, temperature_shape=(6, 7))
            self.assertFalse(mismatch.thermal_valid)
            self.assertTrue(any(value.startswith("temperature_native_dimension_mismatch") for value in mismatch.fatal_errors))

    def test_visible_only_failure_routes_to_polygon_and_identifier_mismatch_needs_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            thermal = root / "DJI_20260717120000_0001_T.JPG"
            Image.new("RGB", (7, 5), "gray").save(thermal)
            record = validate_group(GroupInput("g", str(root / "missing_V.JPG"), str(thermal)))
            self.assertTrue(record.thermal_valid)
            self.assertEqual(route_after_part_a(record).route, ProcessingRoute.THERMAL_POLYGON)
            visible = root / "DJI_20260717120000_9999_V.JPG"
            Image.new("RGB", (7, 5), "green").save(visible)
            uncertain = validate_group(GroupInput("g", str(visible), str(thermal)))
            self.assertTrue(uncertain.pairing_uncertain)
            fatal = validate_group(GroupInput("fatal", str(visible), str(root / "missing_T.JPG")))
            self.assertFalse(fatal.thermal_valid)
            self.assertEqual(route_after_part_a(fatal).status, ProcessingStatus.FAILED)

    def test_b0_match_mismatch_ambiguous_and_manual_routes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            visible = Image.new("RGB", (300, 220), "black")
            draw = ImageDraw.Draw(visible)
            draw.rectangle((20, 30, 150, 170), outline="white", width=8)
            draw.ellipse((50, 60, 120, 130), fill="gray")
            draw.line((10, 200, 280, 10), fill="white", width=5)
            visible_path = root / "visible.png"
            visible.save(visible_path)
            match_path = root / "match.png"
            visible.crop((0, 20, 180, 180)).resize((90, 80)).save(match_path)
            match = triage_content_correspondence(
                group_id="g", image_id="i", visible_path=visible_path, thermal_path=match_path,
                output_directory=root / "match",
            )
            self.assertEqual(match.triage_state, ContentTriageState.CONTENT_MATCH_CANDIDATE)
            self.assertNotEqual(match.candidate_crop[0:2], [60, 30])  # no fixed center prior
            rng = np.random.default_rng(7)
            mismatch_path = root / "mismatch.png"
            Image.fromarray(rng.integers(0, 256, (80, 90, 3), dtype=np.uint8)).save(mismatch_path)
            mismatch = triage_content_correspondence(
                group_id="g", image_id="i", visible_path=visible_path, thermal_path=mismatch_path,
                output_directory=root / "mismatch",
            )
            self.assertEqual(mismatch.triage_state, ContentTriageState.CONTENT_MISMATCH_CANDIDATE)
            accepted_mismatch = apply_part_b0_review(mismatch, ManualReviewStatus.ACCEPTED)
            self.assertIn("run_full_part_b", route_after_part_b0(accepted_mismatch).reason)
            accepted_record = write_part_b0_result(accepted_mismatch, root / "accepted_mismatch.json")
            self.assertEqual(json.loads(accepted_record.read_text(encoding="utf-8"))["manual_review_status"], "accepted")
            flat_path = root / "flat.png"
            Image.new("RGB", (90, 80), "gray").save(flat_path)
            ambiguous = triage_content_correspondence(
                group_id="g", image_id="i", visible_path=visible_path, thermal_path=flat_path,
                output_directory=root / "ambiguous",
            )
            self.assertEqual(ambiguous.triage_state, ContentTriageState.NEEDS_MANUAL_REVIEW)
            self.assertEqual(route_after_part_b0(ambiguous).status, ProcessingStatus.AWAITING_PART_B0_REVIEW)
            self.assertEqual(
                route_after_part_b0(apply_part_b0_review(ambiguous, ManualReviewStatus.REJECTED)).route,
                ProcessingRoute.THERMAL_POLYGON,
            )
            accepted_ambiguous = apply_part_b0_review(ambiguous, ManualReviewStatus.ACCEPTED)
            accepted_route = route_after_part_b0(accepted_ambiguous)
            self.assertEqual(accepted_route.status, ProcessingStatus.READY)
            self.assertIn("run_full_part_b", accepted_route.reason)
            self.assertEqual(
                route_after_part_b0(apply_part_b0_review(ambiguous, ManualReviewStatus.CANCELLED)).status,
                ProcessingStatus.CANCELLED,
            )


class FullPartBAdapterTests(unittest.TestCase):
    def test_existing_candidate_evidence_is_retained_but_review_controls_route(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            visible = root / "v.png"
            thermal = root / "t.png"
            Image.new("RGB", (40, 30), "green").save(visible)
            Image.new("RGB", (20, 15), "gray").save(thermal)
            b0 = PartB0Result(
                group_id="g", image_id="i", triage_state=ContentTriageState.CONTENT_MATCH_CANDIDATE,
                candidate_crop=[0, 0, 40, 30], overall_score=0.9,
            )
            best = {
                "bbox": (1, 1, 39, 29), "rotation_deg": 0.0, "method": "preserved_test_candidate",
                "stage": "fine_grid", "score": 0.8, "old_score": 0.7, "score_delta": 0.1,
                "sobel_ncc": 0.6, "gray_ncc": 0.5, "edge_overlap": 0.4,
            }

            def fake_review(row: object) -> dict[str, object]:
                Path(str(row["contact_sheet_path"])).write_bytes(b"review")  # type: ignore[index]
                return {}

            accepted_review = PartBDecision(
                group_id="g", scene_correspondence=SceneCorrespondence.ACCEPTED,
                coverage_class=CoverageClass.THERMAL_FULLY_SUPPORTED_BY_VISIBLE,
                manual_review_status=ManualReviewStatus.ACCEPTED,
            )
            with patch("scripts.workflow.part_b_adapter.search_alignment", return_value=(best, [best], [], True)), patch(
                "scripts.workflow.part_b_adapter.generate_pair_review", side_effect=fake_review
            ):
                accepted = run_full_part_b(
                    group_id="g", image_id="i", visible_path=visible, thermal_path=thermal,
                    part_b0=b0, output_directory=root / "accepted", review_decision=accepted_review,
                )
                unreviewed = run_full_part_b(
                    group_id="g", image_id="i", visible_path=visible, thermal_path=thermal,
                    part_b0=b0, output_directory=root / "unreviewed",
                )
            self.assertEqual(accepted.candidate_scores["selected"]["method"], "preserved_test_candidate")
            self.assertTrue(Path(accepted.candidate_transform_path).is_file())
            self.assertTrue(Path(accepted.review_evidence_path).is_file())
            self.assertEqual(accepted.gcp_evidence["status"], "not_supplied")
            self.assertEqual(route_group(accepted, thermal_valid=True).route, ProcessingRoute.NORMAL_VT)
            self.assertEqual(route_group(unreviewed, thermal_valid=True).status, ProcessingStatus.AWAITING_PART_B_REVIEW)


if __name__ == "__main__":
    unittest.main()
