from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from scripts.workflow.canonical_result import load_manifest, read_schema_01_manifest, write_canonical_result
from scripts.workflow.extreme_temperature import extreme_summary, plot_pixel_extremes
from scripts.workflow.models import ManualReviewStatus, ProcessingRoute, QAStatus, SourceMethod
from scripts.workflow.polygon_annotation import polygon_context_arrays
from scripts.workflow.result_index import ResultIndex


class CacheAndSchemaTests(unittest.TestCase):
    def make_result(self, root: Path, *, dependencies: dict[str, str] | None = None) -> tuple[object, Path]:
        labels, known, luhk, luhk_known, target = polygon_context_arrays(
            [(0, 0), (3, 0), (3, 3)], (4, 4), 1, "gic_open_space"
        )
        return write_canonical_result(
            output_root=root / "images", image_id="image", group_id="g", pair_id="p", dataset_id="d",
            visible_path="v", thermal_path="t", temperature=np.arange(16, dtype=np.float32).reshape(4, 4),
            labels=labels, known_mask=known, target_mask=target, luhk_labels=luhk, luhk_known_mask=luhk_known,
            processing_route=ProcessingRoute.THERMAL_POLYGON,
            source_method=SourceMethod.THERMAL_POLYGON_USER_ANNOTATION,
            review_status=ManualReviewStatus.ACCEPTED, qa_status=QAStatus.PASS,
            configuration_hash="config", source_file_hashes={"thermal": "raw"},
            dependency_fingerprints=dependencies or {"polygon": "one", "luhk": "gic", "tat3": "a", "sdk": "x", "part_c": "m1"},
            surface_cover_names={1: "roof"}, surface_cover_class_id=1, surface_cover_category="roof",
            target_name="target", polygon_coordinates=[[0, 0], [3, 0], [3, 3]],
            luhk_category="GIC / open space", luhk_code="gic_open_space", luhk_provenance="user_supplied_luhk",
        )

    def test_dependency_and_artifact_corruption_invalidate_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, path = self.make_result(root)
            index = ResultIndex(root / "index.json")
            index.register(path, manifest)  # type: ignore[arg-type]
            index.save()
            dependencies = manifest.dependency_fingerprints  # type: ignore[attr-defined]
            hit = index.check(
                "image", source_file_hashes={"thermal": "raw"}, configuration_hash_value="config",
                dependency_fingerprints=dependencies,
            )
            self.assertTrue(hit.compatible)
            for key in ("part_c", "luhk", "tat3", "sdk", "polygon"):
                changed = dict(dependencies)
                changed[key] += "-changed"
                check = index.check(
                    "image", source_file_hashes={"thermal": "raw"}, configuration_hash_value="config",
                    dependency_fingerprints=changed,
                )
                self.assertEqual(check.reason, "dependency_fingerprint_mismatch")
            temperature = path.parent / "temperature.npy"
            with temperature.open("ab") as handle:
                handle.write(b"damage")
            damaged = index.check(
                "image", source_file_hashes={"thermal": "raw"}, configuration_hash_value="config",
                dependency_fingerprints=dependencies,
            )
            self.assertIn("artifact_hash_mismatch", damaged.reason)

    def test_failed_qa_cannot_register_and_schema_01_is_read_only_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            labels, known, luhk, luhk_known, target = polygon_context_arrays(
                [(0, 0), (2, 0), (2, 2)], (3, 3), 1, "gic_open_space"
            )
            failed, failed_path = write_canonical_result(
                output_root=root / "failed", image_id="failed", group_id="g", pair_id="p", dataset_id="d",
                visible_path="v", thermal_path="t", temperature=np.ones((3, 3)), labels=labels, known_mask=known,
                target_mask=target, luhk_labels=luhk, luhk_known_mask=luhk_known,
                processing_route=ProcessingRoute.THERMAL_POLYGON,
                source_method=SourceMethod.THERMAL_POLYGON_USER_ANNOTATION,
                review_status=ManualReviewStatus.ACCEPTED, qa_status=QAStatus.FAIL,
                configuration_hash="c", source_file_hashes={}, surface_cover_class_id=1, surface_cover_category="roof",
                polygon_coordinates=[[0, 0], [2, 0], [2, 2]], luhk_category="GIC / open space",
                luhk_provenance="user_supplied_luhk",
            )
            with self.assertRaisesRegex(ValueError, "Only successful"):
                ResultIndex(root / "index.json").register(failed_path, failed)
            legacy = root / "legacy.json"
            legacy.write_text(
                json.dumps(
                    {
                        "schema_version": "0.1.0", "processing_version": "heat-index-urop-0.1",
                        "image_id": "old", "group_id": "g", "pair_id": "p", "dataset_id": "d",
                        "visible_path": "v", "thermal_path": "t", "processing_route": "normal_visible_thermal",
                        "source_method": "visible_review", "image_height": 2, "image_width": 2,
                        "processing_status": "success", "qa_status": "pass", "review_status": "accepted",
                        "known_pixel_count": 4, "unknown_pixel_count": 0, "label_provenance": "visible_review",
                        "artifacts": {"temperature": {"path": "temperature.npy", "sha256": ""}},
                    }
                ),
                encoding="utf-8",
            )
            old = read_schema_01_manifest(legacy)
            self.assertEqual(old.schema_version, "0.1.0")
            self.assertEqual(old.processing_version, "heat-index-urop-0.1")

    def test_missing_artifact_schema_mismatch_and_atomic_failure_are_not_reusable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, path = self.make_result(root)
            index = ResultIndex(root / "index.json")
            index.register(path, manifest)  # type: ignore[arg-type]
            index.payload["results"]["image"]["schema_version"] = "9.9.9"
            mismatch = index.check(
                "image", source_file_hashes={"thermal": "raw"}, configuration_hash_value="config",
                dependency_fingerprints=manifest.dependency_fingerprints,  # type: ignore[attr-defined]
            )
            self.assertEqual(mismatch.reason, "schema_version_mismatch")
            index.payload["results"]["image"]["schema_version"] = "0.2.0"
            (path.parent / "target_mask.npy").unlink()
            missing = index.check(
                "image", source_file_hashes={"thermal": "raw"}, configuration_hash_value="config",
                dependency_fingerprints=manifest.dependency_fingerprints,  # type: ignore[attr-defined]
            )
            self.assertTrue(missing.reason.startswith("artifact_missing:"))

            atomic_root = root / "atomic"
            labels, known, luhk, luhk_known, target = polygon_context_arrays(
                [(0, 0), (2, 0), (2, 2)], (3, 3), 1, "gic_open_space"
            )
            with patch("scripts.workflow.canonical_result._atomic_parquet", side_effect=OSError("simulated write failure")):
                with self.assertRaisesRegex(OSError, "simulated write failure"):
                    write_canonical_result(
                        output_root=atomic_root, image_id="atomic", group_id="g", pair_id="p", dataset_id="d",
                        visible_path="", thermal_path="t", temperature=np.ones((3, 3), dtype=np.float32),
                        labels=labels, known_mask=known, target_mask=target, luhk_labels=luhk,
                        luhk_known_mask=luhk_known, processing_route=ProcessingRoute.THERMAL_POLYGON,
                        source_method=SourceMethod.THERMAL_POLYGON_USER_ANNOTATION,
                        review_status=ManualReviewStatus.ACCEPTED, qa_status=QAStatus.PASS,
                        configuration_hash="c", source_file_hashes={"thermal": "raw"},
                        surface_cover_class_id=1, surface_cover_category="roof", target_name="target",
                        polygon_coordinates=[[0, 0], [2, 0], [2, 2]], luhk_category="GIC / open space",
                        luhk_code="gic_open_space", luhk_provenance="user_supplied_luhk",
                    )
            self.assertFalse((atomic_root / "atomic" / "manifest.json").exists())
            self.assertEqual(ResultIndex(root / "atomic_index.json").check(
                "atomic", source_file_hashes={"thermal": "raw"}, configuration_hash_value="c",
            ).reason, "not_indexed")


class ExtremeTemperatureTests(unittest.TestCase):
    def test_deterministic_ties_q99_delta_and_polygon_figure(self) -> None:
        matrix = np.array([[1.0, 1.0, 2.0], [3.0, 9.0, 9.0]], dtype=np.float32)
        rows, cols = np.indices(matrix.shape)
        frame = pd.DataFrame(
            {
                "image_id": "i", "measurement_type": "polygon_selected_thermal_pixel",
                "temperature_source": "npy", "source_method": "thermal_polygon_user_annotation",
                "target_name": "field", "surface_cover_class": "grass", "luhk_label": "gic",
                "analysis_eligible": True, "thermal_row": rows.ravel(), "thermal_col": cols.ravel(),
                "temperature_c": matrix.ravel(), "ambient_temperature_c": 1.0,
            }
        )
        summary, coordinates = extreme_summary(frame)
        self.assertEqual(int(summary.iloc[0]["tied_min_count"]), 2)
        self.assertEqual(int(summary.iloc[0]["tied_max_count"]), 2)
        self.assertEqual((int(summary.iloc[0]["representative_min_row"]), int(summary.iloc[0]["representative_min_col"])), (0, 0))
        self.assertEqual((int(summary.iloc[0]["representative_max_row"]), int(summary.iloc[0]["representative_max_col"])), (1, 1))
        self.assertGreaterEqual(len(coordinates.loc[coordinates["location_type"].eq("q99_exceedance")]), 2)
        self.assertAlmostEqual(float(summary.iloc[0]["max_delta_temperature_c"]), 8.0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "extremes.png"
            result = plot_pixel_extremes(
                matrix=matrix, eligible_mask=np.ones_like(matrix, dtype=bool), output_path=path,
                image_id="i", source_annotation="polygon source", polygon_coordinates=[[0, 0], [2, 0], [2, 1]],
            )
            self.assertTrue(path.is_file())
            self.assertTrue(path.with_suffix(".pdf").is_file())
            self.assertEqual(result["tied_max_count"], 2)
            self.assertIn("threshold", result["q99_location_rule"])

    def test_manual_measurement_without_coordinates_does_not_invent_location(self) -> None:
        frame = pd.DataFrame(
            {
                "image_id": ["i"], "measurement_type": ["manual_tat3_point"],
                "temperature_c": [25.0], "ambient_temperature_c": [20.0],
            }
        )
        summary, coordinates = extreme_summary(frame, group_columns=("image_id", "measurement_type"))
        self.assertFalse(bool(summary.iloc[0]["spatial_location_available"]))
        self.assertTrue(coordinates.empty)


if __name__ == "__main__":
    unittest.main()
