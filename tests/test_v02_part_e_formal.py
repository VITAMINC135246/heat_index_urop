from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.workflow.canonical_result import write_canonical_result
from scripts.workflow.models import (
    ManualReviewStatus,
    ProcessingRoute,
    QAStatus,
    SourceMethod,
)
from scripts.workflow.part_e_runner import run_formal_part_e


class FormalPartEV02IntegrationTests(unittest.TestCase):
    def _write_results(self, root: Path) -> list[Path]:
        shape = (96, 96)
        temperature = np.linspace(20.0, 40.0, shape[0] * shape[1], dtype=np.float32).reshape(shape)
        normal_luhk = np.full(shape, "gic_open_space", dtype="<U96")
        normal_luhk[:, 48:] = "woodland_shrubland_grassland_wetland"
        normal_luhk_names = np.full(shape, "GIC / open space", dtype="<U96")
        normal_luhk_names[:, 48:] = "Woodland / shrubland / grassland / wetland"
        _, normal_path = write_canonical_result(
            output_root=root / "canonical", image_id="normal_001", group_id="g1", pair_id="p1",
            dataset_id="d", visible_path="visible.jpg", thermal_path="thermal.jpg",
            temperature=temperature, labels=np.ones(shape, dtype=np.int16),
            known_mask=np.ones(shape, dtype=bool), processing_route=ProcessingRoute.NORMAL_VT,
            source_method=SourceMethod.VISIBLE_REVIEW, review_status=ManualReviewStatus.ACCEPTED,
            qa_status=QAStatus.PASS, configuration_hash="normal", source_file_hashes={"thermal": "a"},
            surface_cover_names={1: "roof"}, temperature_metadata={"ambient_temperature_c": 20.0},
            temperature_source="override_npy", luhk_labels=normal_luhk,
            luhk_known_mask=np.ones(shape, dtype=bool), luhk_class_names=normal_luhk_names,
            luhk_provenance="official_luhk_lookup",
        )

        target = np.zeros(shape, dtype=bool)
        target[2:94, 2:94] = True
        labels = np.full(shape, -1, dtype=np.int16)
        labels[target] = 5
        _, polygon_path = write_canonical_result(
            output_root=root / "canonical", image_id="polygon_001", group_id="g2", pair_id="p2",
            dataset_id="d", visible_path="", thermal_path="thermal2.jpg",
            temperature=temperature + 2.0, labels=labels, known_mask=target,
            processing_route=ProcessingRoute.THERMAL_POLYGON,
            source_method=SourceMethod.THERMAL_POLYGON_USER_ANNOTATION,
            review_status=ManualReviewStatus.ACCEPTED, qa_status=QAStatus.PASS,
            configuration_hash="polygon", source_file_hashes={"thermal": "b"},
            surface_cover_names={5: "grass_low_vegetation"}, surface_cover_class_id=5,
            surface_cover_category="grass_low_vegetation", target_name="field", target_mask=target,
            polygon_coordinates=[[2, 2], [94, 2], [94, 94], [2, 94]],
            luhk_category="GIC / open space", luhk_code="gic_open_space",
            luhk_provenance="user_supplied_luhk",
            temperature_metadata={"ambient_temperature_c": 21.0}, temperature_source="override_npy",
        )

        _, missing_ambient_path = write_canonical_result(
            output_root=root / "canonical", image_id="missing_ambient_001", group_id="g3", pair_id="p3",
            dataset_id="d", visible_path="visible3.jpg", thermal_path="thermal3.jpg",
            temperature=temperature, labels=np.ones(shape, dtype=np.int16),
            known_mask=np.ones(shape, dtype=bool), processing_route=ProcessingRoute.NORMAL_VT,
            source_method=SourceMethod.VISIBLE_REVIEW, review_status=ManualReviewStatus.ACCEPTED,
            qa_status=QAStatus.PASS, configuration_hash="missing", source_file_hashes={"thermal": "c"},
            surface_cover_names={1: "roof"}, temperature_metadata={},
            temperature_source="override_npy", luhk_provenance="unknown",
        )
        _, zero_eligible_path = write_canonical_result(
            output_root=root / "canonical", image_id="zero_eligible_001", group_id="g4", pair_id="p4",
            dataset_id="d", visible_path="visible4.jpg", thermal_path="thermal4.jpg",
            temperature=temperature, labels=np.full(shape, -1, dtype=np.int16),
            known_mask=np.zeros(shape, dtype=bool), processing_route=ProcessingRoute.NORMAL_VT,
            source_method=SourceMethod.VISIBLE_REVIEW, review_status=ManualReviewStatus.ACCEPTED,
            qa_status=QAStatus.PASS, configuration_hash="zero", source_file_hashes={"thermal": "d"},
            surface_cover_names={1: "roof"}, temperature_metadata={"ambient_temperature_c": 20.0},
            temperature_source="override_npy", luhk_provenance="unknown",
        )
        return [normal_path, polygon_path, missing_ambient_path, zero_eligible_path]

    def test_schema_02_sampling_statistics_kde_qa_report_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifests = self._write_results(root)
            run_summary = root / "run_summary.json"
            run_summary.write_text(json.dumps({"groups": [
                {"image_id": "normal_001", "status": "success", "reason": "ready"},
                {"image_id": "polygon_001", "status": "cache_hit", "reason": "cached"},
                {"image_id": "missing_ambient_001", "status": "success", "reason": "temperature_only"},
                {"image_id": "zero_eligible_001", "status": "success", "reason": "no_reviewed_pixels"},
                {"image_id": "failed_001", "status": "failed", "reason": "thermal_invalid"},
                {"image_id": "cancelled_001", "status": "cancelled", "reason": "user_cancelled"},
                {"image_id": "review_001", "status": "awaiting_part_b0_review", "reason": "ambiguous"},
            ]}), encoding="utf-8")
            output = root / "formal"
            result = run_formal_part_e(
                manifests, output_root=output, run_summary_path=run_summary, resume=False,
            )
            self.assertTrue((output / "tables" / "part_e_pixel_sample_coverage.csv").is_file())
            self.assertTrue((output / "tables" / "part_e_pixel_statistical_tests.csv").is_file())
            self.assertTrue((output / "tables" / "part_e_pixel_effect_sizes.csv").is_file())
            self.assertTrue((output / "tables" / "part_e_pixel_delta_t_spectrum_summary.csv").is_file())
            self.assertTrue((output / "qa" / "part_e_sampling_reproducibility.csv").is_file())
            self.assertTrue((output / "figures" / "spectrum" / "fig00_pixel_delta_t_spectrum_overall.png").is_file())
            self.assertTrue((output / "figures" / "spectrum" / "fig01_pixel_delta_t_spectrum_by_luhk_facets.png").is_file())
            self.assertTrue((output / "figures" / "spatial" / "spatial_figure_validation.json").is_file())
            temporal_manifest_path = output / "temporal" / "temporal_run_manifest.json"
            self.assertTrue(temporal_manifest_path.is_file())
            self.assertTrue((output / "temporal" / "temporal_run_summary.md").is_file())
            self.assertTrue((output / "temporal" / "temporal_output_validation.json").is_file())
            temporal_manifest = json.loads(temporal_manifest_path.read_text(encoding="utf-8"))
            self.assertFalse(temporal_manifest["temporal_requested"])
            self.assertFalse(temporal_manifest["temporal_series_available"])
            self.assertFalse(any((output / "temporal").rglob("*.png")))
            self.assertTrue(Path(result["report"]).is_file())

            report_stage = Path(__file__).resolve().parents[1] / "scripts" / "part_e" / "11_generate_part_e_report.py"
            generated_config = output / "part_e_schema_0_2_config.json"
            completed_report = subprocess.run(
                [sys.executable, str(report_stage), "--config", str(generated_config)],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed_report.returncode, 0, completed_report.stderr)
            dynamic_report = (output / "summaries" / "part_e_round1_delta_t_analysis_summary.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("analysis of 4 accepted capture(s)", dynamic_report)
            self.assertNotIn("five-image HKUST pilot", dynamic_report)
            self.assertIn("heterogeneous measurement/ROI/provenance", dynamic_report)

            tests = pd.read_csv(output / "tables" / "part_e_pixel_statistical_tests.csv")
            self.assertTrue(tests["groups_compared"].fillna("").str.contains("measurement_type=").any())
            spectrum = pd.read_csv(output / "tables" / "part_e_pixel_delta_t_spectrum_summary.csv")
            overall = spectrum.loc[spectrum["analysis_family"].eq("overall")].iloc[0]
            self.assertEqual(overall["kde_status"], "not_pooled_heterogeneous_sources")
            self.assertIn("were not pooled", overall["eligibility_or_skipped_reason"])
            coverage = pd.read_csv(output / "tables" / "part_e_pixel_sample_coverage.csv")
            self.assertEqual(int(coverage.loc[coverage["analysis_family"].eq("surface_cover_shadow"), "sampled_pixel_count"].sum()), 0)
            luhk_groups = coverage.loc[coverage["analysis_family"].eq("luhk"), "group_name"].astype(str)
            self.assertTrue(luhk_groups.str.contains("luhk_provenance=official_luhk_lookup", regex=False).any())
            self.assertTrue(luhk_groups.str.contains("luhk_provenance=user_supplied_luhk", regex=False).any())
            sampling_manifest = pd.read_csv(output / "tables" / "part_e_pixel_sampling_manifest.csv")
            luhk_manifest = sampling_manifest.loc[sampling_manifest["analysis_family"].eq("luhk")]
            official_eligible = luhk_manifest.loc[
                luhk_manifest["group_name"].str.contains("luhk_provenance=official_luhk_lookup", regex=False),
                "eligible_pixel_count",
            ].sum()
            polygon_eligible = luhk_manifest.loc[
                luhk_manifest["group_name"].str.contains("luhk_provenance=user_supplied_luhk", regex=False),
                "eligible_pixel_count",
            ].sum()
            self.assertEqual(int(official_eligible), int(np.prod((96, 96))))
            self.assertEqual(int(polygon_eligible), int((92 * 92)))
            inclusion = pd.read_csv(output / "tables" / "part_e_inclusion_exclusion.csv")
            self.assertEqual(set(inclusion["status"]), {
                "success", "cache_hit", "failed", "cancelled", "awaiting_part_b0_review",
            })
            missing = inclusion.loc[inclusion["image_id"].eq("missing_ambient_001")].iloc[0]
            self.assertTrue(bool(missing["missing_ambient"]))
            self.assertFalse(bool(missing["included_in_formal_part_e"]))
            zero_eligible = inclusion.loc[inclusion["image_id"].eq("zero_eligible_001")].iloc[0]
            self.assertEqual(int(zero_eligible["eligible_pixels"]), 0)
            self.assertFalse(bool(zero_eligible["included_in_formal_part_e"]))

            resumed = run_formal_part_e(
                manifests, output_root=output, run_summary_path=run_summary, resume=True,
            )
            self.assertIn("SKIP sample", resumed["stage_stdout"])
            self.assertIn("SKIP spectrum", resumed["stage_stdout"])
            self.assertIn("SKIP spatial-figures", resumed["stage_stdout"])
            self.assertEqual(resumed["temporal_status"], "cache_hit")
            state = json.loads((output / "qa" / "part_e_stage_state.json").read_text(encoding="utf-8"))
            self.assertRegex(state["dependency_sha256"], r"^[0-9a-f]{64}$")

            dry = run_formal_part_e(
                output_root=root / "dry_run", combined_parquet=Path(result["canonical_parquet"]), dry_run=True,
            )
            self.assertIn("DRY-RUN sample", dry["stage_stdout"])
            self.assertIn("planned (dry run)", Path(dry["qa"]).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
