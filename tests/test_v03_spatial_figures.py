from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.workflow.canonical_result import write_canonical_result
from scripts.workflow.models import ManualReviewStatus, ProcessingRoute, QAStatus, SourceMethod
from scripts.workflow.part_e_adapter import aggregate_canonical_results


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "part_e" / "05_generate_pixel_spatial_figures.py"
SPEC = importlib.util.spec_from_file_location("v03_spatial_figures", SCRIPT)
assert SPEC and SPEC.loader
SPATIAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SPATIAL)


class V03CanonicalSpatialFigureTests(unittest.TestCase):
    def _results(self, root: Path) -> tuple[list[Path], Path]:
        normal_shape = (5, 7)
        normal_temperature = np.arange(np.prod(normal_shape), dtype=np.float32).reshape(normal_shape) + 20
        normal_temperature[0, 0] = np.nan
        normal_labels = np.ones(normal_shape, dtype=np.int16)
        normal_known = np.ones(normal_shape, dtype=bool)
        normal_known[0, 1] = False
        normal_labels[~normal_known] = -1
        _, normal = write_canonical_result(
            output_root=root / "canonical",
            image_id="normal_dynamic",
            group_id="g-normal",
            pair_id="p-normal",
            dataset_id="synthetic_non_scientific_fixture",
            visible_path="visible.png",
            thermal_path="thermal.png",
            temperature=normal_temperature,
            labels=normal_labels,
            known_mask=normal_known,
            processing_route=ProcessingRoute.NORMAL_VT,
            source_method=SourceMethod.VISIBLE_REVIEW,
            review_status=ManualReviewStatus.ACCEPTED,
            qa_status=QAStatus.WARN,
            configuration_hash="normal",
            source_file_hashes={"thermal": "normal"},
            surface_cover_names={1: "roof"},
            temperature_metadata={"capture_time": "2026-02-02T09:00:00", "capture_timezone": "Asia/Hong_Kong"},
            ambient_metadata={},
            temperature_source="mocked_temperature_matrix",
            luhk_provenance="unknown",
        )

        polygon_shape = (6, 8)
        polygon_temperature = np.arange(np.prod(polygon_shape), dtype=np.float32).reshape(polygon_shape) + 30
        target = np.zeros(polygon_shape, dtype=bool)
        target[1:5, 2:7] = True
        polygon_labels = np.full(polygon_shape, -1, dtype=np.int16)
        polygon_labels[target] = 5
        shadow = np.zeros(polygon_shape, dtype=bool)
        shadow[2:4, 3:5] = True
        _, polygon = write_canonical_result(
            output_root=root / "canonical",
            image_id="polygon_dynamic",
            group_id="g-polygon",
            pair_id="p-polygon",
            dataset_id="synthetic_non_scientific_fixture",
            visible_path="",
            thermal_path="thermal2.png",
            temperature=polygon_temperature,
            labels=polygon_labels,
            known_mask=target,
            target_mask=target,
            shadow_mask=shadow,
            processing_route=ProcessingRoute.THERMAL_POLYGON,
            source_method=SourceMethod.THERMAL_POLYGON_USER_ANNOTATION,
            review_status=ManualReviewStatus.ACCEPTED,
            qa_status=QAStatus.PASS,
            configuration_hash="polygon",
            source_file_hashes={"thermal": "polygon"},
            surface_cover_names={5: "grass_low_vegetation"},
            surface_cover_class_id=5,
            surface_cover_category="grass_low_vegetation",
            target_id="hkust-soccer-field",
            target_name="HKUST soccer field",
            polygon_coordinates=[[2, 1], [7, 1], [7, 5], [2, 5]],
            luhk_category="GIC / open space",
            luhk_code="gic_open_space",
            luhk_provenance="user_supplied_luhk",
            temperature_metadata={
                "ambient_temperature_c": 23.0,
                "capture_time": "2026-02-02T12:00:00",
                "capture_timezone": "Asia/Hong_Kong",
            },
            ambient_metadata={
                "ambient_temperature_c": 23.0,
                "source": "mocked_ambient_fixture",
                "definition": "near-surface air temperature",
            },
            temperature_source="mocked_temperature_matrix",
        )
        combined = root / "combined.parquet"
        aggregate_canonical_results(
            [normal, polygon], output_parquet=combined, summary_csv=root / "summary.csv"
        )
        return [normal, polygon], combined

    def test_normal_polygon_dynamic_missing_layers_and_boundary_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, combined = self._results(root)
            output = root / "spatial"
            result = SPATIAL.run(combined, output)
            self.assertEqual(result["generated_unit_count"], 2)
            self.assertEqual(len(result["expected_figure_files"]), 2 * 8 * 2)
            self.assertTrue(all((output / name).stat().st_size > 100 for name in result["expected_figure_files"]))
            manifest = pd.read_csv(output / "spatial_figure_manifest.csv", keep_default_na=False)
            normal = manifest.loc[manifest["image_id"].eq("normal_dynamic")].iloc[0]
            polygon = manifest.loc[manifest["image_id"].eq("polygon_dynamic")].iloc[0]
            self.assertEqual((int(normal["image_height"]), int(normal["image_width"])), (5, 7))
            self.assertFalse(bool(normal["ambient_available"]))
            self.assertFalse(bool(normal["luhk_available"]))
            self.assertFalse(bool(normal["shadow_available"]))
            self.assertTrue(bool(polygon["target_applicable"]))
            self.assertEqual(polygon["target_id"], "hkust-soccer-field")
            self.assertEqual(polygon["source_method"], "thermal_polygon_user_annotation")

            pixels = pd.read_parquet(combined)
            outside = pixels.loc[pixels["image_id"].eq("polygon_dynamic") & ~pixels["target_mask"].astype(bool)]
            self.assertFalse(outside["label_known"].astype(bool).any())
            self.assertFalse(outside["analysis_eligible"].astype(bool).any())
            self.assertTrue(outside["exclusion_reason"].eq("outside_target_selection").all())

    def test_completeness_validation_rejects_deleted_figure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, combined = self._results(root)
            output = root / "spatial"
            result = SPATIAL.run(combined, output)
            victim = output / result["expected_figure_files"][0]
            victim.unlink()
            with self.assertRaisesRegex(ValueError, "incomplete"):
                SPATIAL.validate_outputs(output, expected_hash=result["canonical_sha256"])

    def test_non_pixel_sources_are_recorded_not_silently_completed_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frame = pd.DataFrame(
                {
                    "image_id": ["tat3-point"],
                    "thermal_row": [0],
                    "thermal_col": [0],
                    "temperature_c": [31.0],
                    "measurement_type": ["manual_tat3_point"],
                    "source_method": ["tat3_manual_measurement"],
                    "analysis_eligible": [True],
                    "label_known": [True],
                    "target_mask": [True],
                }
            )
            canonical = root / "tat3.parquet"
            frame.to_parquet(canonical, index=False)
            output = root / "spatial"
            result = SPATIAL.run(canonical, output)
            self.assertEqual(result["generated_unit_count"], 0)
            self.assertEqual(result["status"], "complete_with_recorded_exclusions")
            self.assertTrue(result["recorded_exclusions"])
            self.assertTrue((output / "spatial_figure_validation.json").is_file())


if __name__ == "__main__":
    unittest.main()
