from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.workflow.temporal_analysis import (
    TemporalAnalysisPlan,
    TemporalGroupDefinition,
    build_capture_summary,
    build_stratum_summary,
    parse_temporal_plan,
    run_temporal_analysis,
    validate_temporal_outputs,
)


def capture_rows(
    image_id: str,
    capture_time: str,
    temperatures: list[float],
    *,
    shape: tuple[int, int] = (2, 2),
    ambient: float | None = 5.0,
    target_id: str = "field-target",
    location_id: str = "field-location",
    measurement_type: str = "polygon_selected_thermal_pixel",
    source_method: str = "thermal_polygon_user_annotation",
    temperature_source: str = "dji_radiometric_sdk",
    temperature_definition: str = "apparent radiometric surface temperature",
    temperature_unit: str = "degC",
    capture_timezone: str = "Asia/Hong_Kong",
    capture_time_source: str = "exif_datetime_original",
    capture_time_valid: bool | None = None,
    ambient_source: str = "weather_station_a",
    ambient_definition: str = "screen-height air temperature",
    ambient_unit: str = "degC",
    ambient_data_qa_status: str | None = None,
    ambient_provenance: str | None = None,
    ambient_source_record: str | None = None,
    qa_status: str = "pass",
    roi_definition: str = "accepted target polygon",
    roi_method: str = "manual_polygon_per_capture",
    spatial_processing_method: str = "accepted_target_roi_summary",
    target_mask: list[bool] | None = None,
    gps_latitude: float | None = None,
    gps_longitude: float | None = None,
    roi_mask_sha256: str = "",
    roi_polygon_area_px2: float | None = None,
    roi_comparability_evidence: str = "",
    target_name: str = "Field target",
    spatial_registration_id: str = "",
    roi_boundary_overlap_fraction: float | None = None,
) -> pd.DataFrame:
    values = np.asarray(temperatures, dtype=float)
    if values.size != shape[0] * shape[1]:
        raise ValueError("Fixture values must fill the requested grid.")
    rows = np.repeat(np.arange(shape[0]), shape[1])
    cols = np.tile(np.arange(shape[1]), shape[0])
    selected = np.ones(values.size, dtype=bool) if target_mask is None else np.asarray(target_mask, dtype=bool)
    delta = values - ambient if ambient is not None else np.full(values.shape, np.nan)
    payload = {
            "image_id": image_id,
            "pixel_uid": [f"{image_id}__r{row}_c{col}" for row, col in zip(rows, cols)],
            "thermal_row": rows,
            "thermal_col": cols,
            "temperature_c": values,
            "delta_t_c": delta,
            "ambient_temperature_c": np.nan if ambient is None else ambient,
            "capture_datetime": capture_time,
            "capture_timezone": capture_timezone,
            "capture_time_source": capture_time_source,
            "measurement_type": measurement_type,
            "temperature_source": temperature_source,
            "temperature_definition": temperature_definition,
            "temperature_unit": temperature_unit,
            "source_method": source_method,
            "selection_scope": "accepted_target_roi",
            "surface_cover_provenance": source_method,
            "luhk_provenance": "user_supplied_luhk",
            "target_id": target_id,
            "target_name": target_name,
            "location_id": location_id,
            "location_name": "Field location",
            "roi_id": "field-roi",
            "roi_definition": roi_definition,
            "roi_method": roi_method,
            "spatial_processing_method": spatial_processing_method,
            "qa_status": qa_status,
            "ambient_source": ambient_source if ambient is not None else "",
            "ambient_definition": ambient_definition if ambient is not None else "",
            "ambient_unit": ambient_unit,
            "analysis_eligible": selected,
            "temperature_is_finite": np.isfinite(values),
            "label_known": selected,
            "target_mask": selected,
            "gps_latitude": np.nan if gps_latitude is None else gps_latitude,
            "gps_longitude": np.nan if gps_longitude is None else gps_longitude,
            "roi_mask_sha256": roi_mask_sha256,
            "roi_polygon_area_px2": np.nan if roi_polygon_area_px2 is None else roi_polygon_area_px2,
            "roi_target_pixel_count": int(selected.sum()),
            "roi_target_coverage_fraction": float(selected.mean()),
            "roi_comparability_evidence": roi_comparability_evidence,
            "spatial_registration_id": spatial_registration_id,
            "roi_boundary_overlap_fraction": (
                np.nan if roi_boundary_overlap_fraction is None else roi_boundary_overlap_fraction
            ),
        }
    if capture_time_valid is not None:
        payload["capture_time_valid"] = capture_time_valid
    for column, value in (
        ("ambient_data_qa_status", ambient_data_qa_status),
        ("ambient_provenance", ambient_provenance),
        ("ambient_source_record", ambient_source_record),
    ):
        if value is not None:
            payload[column] = value
    return pd.DataFrame(payload)


def confirmed_group(
    image_ids: list[str],
    *,
    group_id: str = "field-series",
    same_location: bool = True,
    roi_comparable: bool = True,
    override: bool = False,
    override_reason: str = "",
    registration: bool = False,
    windows: list[dict[str, str]] | None = None,
    full_day_sampling: bool = False,
) -> TemporalGroupDefinition:
    return TemporalGroupDefinition(
        temporal_group_id=group_id,
        image_ids=image_ids,
        location_id="field-location",
        target_id="field-target",
        location_name="Field location",
        target_name="Field target",
        same_location_confirmed=same_location,
        confirmation_provenance="ordinary_user_cli_confirmation",
        roi_comparable_confirmed=roi_comparable,
        spatial_override_confirmed=override,
        spatial_override_reason=override_reason,
        registration_confirmed=registration,
        registration_method="validated_fixture_registration" if registration else "",
        registration_id="registration-v1" if registration else "",
        observation_windows=windows or [],
        full_day_sampling_confirmed=full_day_sampling,
    )


class V03TemporalAnalysisTests(unittest.TestCase):
    def write_input(self, root: Path, frames: list[pd.DataFrame]) -> Path:
        path = root / "canonical.parquet"
        pd.concat(frames, ignore_index=True).to_parquet(path, index=False)
        return path

    def run_plan(
        self,
        root: Path,
        frames: list[pd.DataFrame],
        groups: list[TemporalGroupDefinition],
        *,
        requested: bool = True,
        output_name: str = "temporal",
        resume: bool = False,
    ):
        canonical = self.write_input(root, frames)
        plan = TemporalAnalysisPlan(temporal_requested=requested, groups=groups)
        return run_temporal_analysis(
            canonical,
            output_root=root / output_name,
            default_timezone="Asia/Hong_Kong",
            plan=plan,
            resume=resume,
        )

    def test_plan_is_json_serializable_and_never_infers_groups(self) -> None:
        group = confirmed_group(["a", "b"])
        plan = TemporalAnalysisPlan(temporal_requested=True, groups=[group])
        encoded = json.dumps(plan.to_dict())
        parsed = parse_temporal_plan(json.loads(encoded))
        self.assertTrue(parsed.temporal_requested)
        self.assertEqual(parsed.groups[0].image_ids, ["a", "b"])
        self.assertEqual(parsed.groups[0].gps_conflict_threshold_m, 100.0)
        self.assertFalse(parse_temporal_plan().temporal_requested)
        self.assertEqual(parse_temporal_plan().groups, [])

        with self.assertRaisesRegex(ValueError, "only one temporal group"):
            TemporalAnalysisPlan(
                temporal_requested=True,
                groups=[confirmed_group(["a"], group_id="one"), confirmed_group(["a"], group_id="two")],
            )
        with self.assertRaisesRegex(ValueError, "non-empty reason"):
            confirmed_group(["a", "b"], override=True)
        with self.assertRaisesRegex(ValueError, "confirmation_provenance"):
            TemporalGroupDefinition(
                temporal_group_id="g",
                image_ids=["a", "b"],
                location_id="l",
                target_id="t",
                same_location_confirmed=True,
            )
        with self.assertRaisesRegex(ValueError, "registration_method"):
            TemporalGroupDefinition(
                temporal_group_id="g",
                image_ids=["a", "b"],
                location_id="l",
                target_id="t",
                registration_confirmed=True,
            )

    def test_standalone_cli_defaults_to_no_and_accepts_only_explicit_temporal_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            canonical = self.write_input(
                root,
                [
                    capture_rows("a", "2026-02-02T09:00:00", [10, 12, 14, 16]),
                    capture_rows("b", "2026-02-02T10:00:00", [20, 22, 24, 26]),
                ],
            )
            script = Path(__file__).resolve().parents[1] / "scripts" / "run_temporal_analysis.py"
            common = [
                sys.executable,
                str(script),
                "--canonical-parquet",
                str(canonical),
                "--timezone",
                "Asia/Hong_Kong",
                "--dry-run",
            ]
            default = subprocess.run(
                [*common, "--output-root", str(root / "default")],
                cwd=script.parents[1],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(default.returncode, 0, default.stdout + default.stderr)
            self.assertIn("temporal_requested: False", default.stdout)
            self.assertIn("temporal_group_count: 0", default.stdout)

            plan_path = root / "reviewed_temporal_plan.json"
            plan_path.write_text(
                json.dumps(
                    TemporalAnalysisPlan(
                        temporal_requested=True,
                        groups=[confirmed_group(["a", "b"])],
                    ).to_dict()
                ),
                encoding="utf-8",
            )
            explicit = subprocess.run(
                [
                    *common,
                    "--output-root",
                    str(root / "explicit"),
                    "--temporal-plan",
                    str(plan_path),
                ],
                cwd=script.parents[1],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(explicit.returncode, 0, explicit.stdout + explicit.stderr)
            self.assertIn("temporal_requested: True", explicit.stdout)
            self.assertIn("temporal_group_count: 1", explicit.stdout)

            unsupported_interactive = subprocess.run(
                [
                    *common,
                    "--output-root",
                    str(root / "interactive"),
                    "--temporal",
                    "ask",
                ],
                cwd=script.parents[1],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(unsupported_interactive.returncode, 0)
            self.assertIn("requires --manifest or --run-summary", unsupported_interactive.stderr)

    def test_temporal_not_requested_is_clean_complete_skip_with_zero_figures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            canonical = self.write_input(
                root,
                [
                    capture_rows("one", "2026-02-02T09:00:00", [1, 2, 3, 4]),
                    capture_rows("two", "2026-02-02T10:00:00", [5, 6, 7, 8]),
                ],
            )
            output = root / "output"
            result = run_temporal_analysis(
                canonical,
                output_root=output,
                default_timezone="Asia/Hong_Kong",
                temporal_requested=False,
                resume=True,
            )
            self.assertEqual(result.status, "complete")
            manifest = json.loads(result.run_manifest.read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "complete")
            self.assertFalse(manifest["temporal_requested"])
            self.assertFalse(manifest["temporal_series_available"])
            self.assertIn("Temporal analysis was not requested", result.run_summary.read_text(encoding="utf-8"))
            self.assertEqual(list(output.rglob("*.png")), [])
            self.assertEqual(list(output.rglob("*.pdf")), [])
            validation = validate_temporal_outputs(output, canonical_hash=manifest["canonical_sha256"])
            self.assertEqual(validation["figure_files"], [])

            cached = run_temporal_analysis(
                canonical,
                output_root=output,
                default_timezone="Asia/Hong_Kong",
                temporal_requested=False,
                resume=True,
            )
            self.assertEqual(cached.status, "cache_hit")

            legacy = output / "figures" / "temporal_source_stratified_comparison.png"
            legacy.parent.mkdir(parents=True)
            legacy.write_bytes(b"superseded")
            cleaned = run_temporal_analysis(
                canonical,
                output_root=output,
                default_timezone="Asia/Hong_Kong",
                temporal_requested=False,
                resume=True,
            )
            self.assertEqual(cleaned.status, "complete")
            self.assertFalse(legacy.exists())
            self.assertEqual(list(output.rglob("*.png")), [])

            generated = run_temporal_analysis(
                canonical,
                output_root=output,
                default_timezone="Asia/Hong_Kong",
                plan=TemporalAnalysisPlan(
                    temporal_requested=True,
                    groups=[confirmed_group(["one", "two"])],
                ),
                resume=True,
            )
            self.assertTrue(generated.temporal_series_available)
            self.assertTrue(list(output.rglob("*.png")))
            skipped_again = run_temporal_analysis(
                canonical,
                output_root=output,
                default_timezone="Asia/Hong_Kong",
                temporal_requested=False,
                resume=True,
            )
            self.assertFalse(skipped_again.temporal_series_available)
            self.assertEqual(list(output.rglob("*.png")), [])
            self.assertEqual(list(output.rglob("*.pdf")), [])

    def test_same_location_and_roi_confirmation_are_hard_gates(self) -> None:
        frames = [
            capture_rows("a", "2026-02-02T09:00:00", [10, 12, 14, 16]),
            capture_rows("b", "2026-02-02T10:00:00", [20, 22, 24, 26]),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_plan(root, frames, [confirmed_group(["a", "b"], same_location=False)])
            manifest = json.loads(result.group_manifests[0].read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(manifest["trend_status"], "same_location_not_confirmed")
            self.assertFalse(manifest["temporal_series_available"])
            self.assertEqual(list(result.group_manifests[0].parent.rglob("*.png")), [])
            exclusions = pd.read_csv(result.group_manifests[0].parent / "qa" / "exclusions.csv")
            self.assertTrue(exclusions["exact_exclusion_reasons"].str.contains("same_physical_location_not_confirmed").all())

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_plan(root, frames, [confirmed_group(["a", "b"], roi_comparable=False)])
            manifest = json.loads(result.group_manifests[0].read_text(encoding="utf-8"))
            self.assertEqual(manifest["trend_status"], "roi_comparability_not_confirmed")
            self.assertFalse(manifest["peak_to_trough_available"])

    def test_primary_robust_and_absolute_peak_to_trough_results_are_correct(self) -> None:
        frames = [
            capture_rows("cool", "2026-02-02T02:00:00", [10, 12, 14, 16]),
            capture_rows("hot", "2026-02-02T12:00:00", [20, 22, 24, 26]),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_plan(root, frames, [confirmed_group(["cool", "hot"])])
            group_root = result.group_manifests[0].parent
            manifest = json.loads(result.group_manifests[0].read_text(encoding="utf-8"))
            self.assertTrue(manifest["temporal_series_available"])
            self.assertTrue(manifest["peak_to_trough_available"])
            self.assertEqual(manifest["trend_status"], "multi_capture_observed_series")
            captures = pd.read_csv(group_root / "tables" / "per_capture_statistics.csv")
            self.assertIn("temperature_q05_c", captures.columns)
            peaks = pd.read_csv(group_root / "tables" / "peak_to_trough_statistics.csv")
            mean = peaks.loc[peaks["statistic"].eq("mean")].iloc[0]
            median = peaks.loc[peaks["statistic"].eq("median")].iloc[0]
            q95 = peaks.loc[peaks["statistic"].eq("q95")].iloc[0]
            maximum = peaks.loc[peaks["statistic"].eq("max")].iloc[0]
            absolute = peaks.loc[peaks["statistic"].eq("absolute_pixel")].iloc[0]
            for row in (mean, median, q95, maximum):
                self.assertAlmostEqual(float(row["observed_peak_to_trough_range_c"]), 10.0)
            self.assertTrue(bool(mean["primary_representative"]))
            self.assertEqual(mean["observed_max_image_id"], "hot")
            self.assertEqual(mean["observed_min_image_id"], "cool")
            self.assertAlmostEqual(float(mean["observed_max_c"]), 23.0)
            self.assertAlmostEqual(float(mean["observed_min_c"]), 13.0)
            self.assertAlmostEqual(float(mean["max_min_time_interval_hours"]), 10.0)
            self.assertAlmostEqual(float(absolute["observed_peak_to_trough_range_c"]), 16.0)
            self.assertEqual((absolute["observed_max_row"], absolute["observed_max_col"]), (1, 1))
            self.assertEqual((absolute["observed_min_row"], absolute["observed_min_col"]), (0, 0))
            report = (group_root / "temporal_summary.md").read_text(encoding="utf-8")
            self.assertIn("Observed maximum ROI mean: 23.000°C", report)
            self.assertIn("Observed minimum ROI mean: 13.000°C", report)
            self.assertIn("Observed peak-to-trough difference: 10.000°C", report)
            self.assertIn("Absolute observed pixel maximum: 26.000°C", report)
            self.assertIn("Absolute observed pixel minimum: 10.000°C", report)
            run_summary = result.run_summary.read_text(encoding="utf-8")
            self.assertIn("observed maximum ROI mean: 23.000°C", run_summary)
            self.assertIn("Observed peak-to-trough difference: 10.000°C", run_summary)
            self.assertTrue((group_root / "figures" / "target_temperature_vs_local_time.png").is_file())
            self.assertTrue((group_root / "figures" / "observed_peak_to_trough_summary.png").is_file())
            self.assertTrue((group_root / "figures" / "sampling_coverage_timeline.png").is_file())
            self.assertFalse(any("source_stratified" in path.name for path in group_root.rglob("*")))

    def test_delta_t_requires_compatible_ambient_source_and_definition(self) -> None:
        compatible = [
            capture_rows(
                "a", "2026-02-02T09:00:00", [10, 12, 14, 16], ambient=5,
                ambient_data_qa_status="reviewed-pass",
                ambient_provenance="TAT3 report entry 56",
                ambient_source_record="combined_report.docx#entry-56",
            ),
            capture_rows(
                "b", "2026-02-02T10:00:00", [20, 22, 24, 26], ambient=6,
                ambient_data_qa_status="reviewed-pass",
                ambient_provenance="TAT3 report entry 56",
                ambient_source_record="combined_report.docx#entry-56",
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_plan(root, compatible, [confirmed_group(["a", "b"])])
            group_root = result.group_manifests[0].parent
            manifest = json.loads(result.group_manifests[0].read_text(encoding="utf-8"))
            self.assertTrue(manifest["delta_t_peak_to_trough_available"])
            delta = pd.read_csv(group_root / "tables" / "delta_t_peak_to_trough_statistics.csv")
            mean = delta.loc[delta["statistic"].eq("mean")].iloc[0]
            self.assertAlmostEqual(float(mean["observed_peak_to_trough_range_c"]), 9.0)
            self.assertEqual(mean["ambient_source"], "weather_station_a")
            self.assertEqual(mean["ambient_definition"], "screen-height air temperature")
            self.assertEqual(mean["ambient_data_qa_statuses"], "reviewed-pass")
            self.assertEqual(mean["ambient_provenance"], "TAT3 report entry 56")
            self.assertEqual(mean["ambient_source_records"], "combined_report.docx#entry-56")
            self.assertFalse(bool(mean["ambient_metadata_legacy_fallback"]))
            first_record = manifest["capture_records"][0]
            self.assertEqual(first_record["ambient_data_qa_status"], "reviewed-pass")
            self.assertEqual(first_record["ambient_provenance"], "TAT3 report entry 56")
            self.assertEqual(first_record["ambient_source_record"], "combined_report.docx#entry-56")
            report = (group_root / "temporal_summary.md").read_text(encoding="utf-8")
            self.assertIn("Observed maximum ROI-mean ΔT", report)
            self.assertIn("Ambient-data QA status: reviewed-pass", report)
            self.assertIn("Ambient provenance: TAT3 report entry 56", report)
            self.assertIn("Ambient source record: combined_report.docx#entry-56", report)
            self.assertTrue((group_root / "figures" / "target_delta_t_vs_local_time.png").is_file())

        incompatible = [
            compatible[0],
            capture_rows(
                "b", "2026-02-02T10:00:00", [20, 22, 24, 26], ambient=6,
                ambient_source="weather_station_b",
                ambient_definition="rooftop sensor temperature",
                ambient_unit="kelvin",
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_plan(root, incompatible, [confirmed_group(["a", "b"])])
            group_root = result.group_manifests[0].parent
            manifest = json.loads(result.group_manifests[0].read_text(encoding="utf-8"))
            self.assertTrue(manifest["temporal_series_available"])
            self.assertFalse(manifest["delta_t_peak_to_trough_available"])
            self.assertFalse((group_root / "figures" / "target_delta_t_vs_local_time.png").exists())
            report = (group_root / "temporal_summary.md").read_text(encoding="utf-8")
            self.assertIn("ΔT temporal range unavailable", report)
            self.assertIn("Ambient-temperature definitions are incompatible", report)
            self.assertEqual(
                set(manifest["delta_t_unavailability"]["exact_reasons"]),
                {
                    "incompatible_ambient_source_across_captures",
                    "incompatible_ambient_definition_across_captures",
                    "incompatible_ambient_unit_across_captures",
                },
            )
            self.assertIn("incompatible_ambient_source_across_captures", report)

        missing_metadata = [
            capture_rows(
                "a", "2026-02-02T09:00:00", [10, 12, 14, 16], ambient=5,
                ambient_source="", ambient_definition="", ambient_unit="",
            ),
            compatible[1],
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_plan(root, missing_metadata, [confirmed_group(["a", "b"])])
            group_root = result.group_manifests[0].parent
            manifest = json.loads(result.group_manifests[0].read_text(encoding="utf-8"))
            self.assertFalse(manifest["delta_t_peak_to_trough_available"])
            reasons = manifest["delta_t_exclusion_reasons"]["a"]
            self.assertIn("ambient_source_missing", reasons)
            self.assertIn("ambient_definition_missing", reasons)
            self.assertIn("ambient_unit_missing", reasons)
            compatibility = pd.read_csv(group_root / "tables" / "capture_compatibility.csv")
            self.assertIn("delta_t_exclusion_reasons", compatibility.columns)
            explanation = compatibility.loc[
                compatibility["image_id"].eq("a"), "delta_t_exclusion_explanation"
            ].iloc[0]
            self.assertIn("ΔT is unavailable", explanation)
            report = (group_root / "temporal_summary.md").read_text(encoding="utf-8")
            self.assertIn("ambient_source_missing", report)

    def test_duplicate_timestamps_and_missing_timestamp_are_explicit_exclusions(self) -> None:
        duplicate = [
            capture_rows("a", "2026-02-02T09:00:00", [10, 12, 14, 16]),
            capture_rows("b", "2026-02-02T09:00:00", [20, 22, 24, 26]),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_plan(root, duplicate, [confirmed_group(["a", "b"])])
            group_root = result.group_manifests[0].parent
            manifest = json.loads(result.group_manifests[0].read_text(encoding="utf-8"))
            self.assertFalse(manifest["temporal_series_available"])
            compatibility = pd.read_csv(group_root / "tables" / "capture_compatibility.csv")
            self.assertTrue(
                compatibility["group_gate_reasons"].str.contains(
                    "duplicate_capture_timestamp_within_compatibility_stratum"
                ).all()
            )
            self.assertEqual(list((group_root / "figures").glob("*")), [])

        missing = [
            capture_rows("a", "", [10, 12, 14, 16]),
            capture_rows("b", "2026-02-02T10:00:00", [20, 22, 24, 26]),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_plan(root, missing, [confirmed_group(["a", "b"])])
            exclusions = pd.read_csv(result.group_manifests[0].parent / "qa" / "exclusions.csv")
            reason = exclusions.loc[exclusions["image_id"].eq("a"), "exact_exclusion_reasons"].iloc[0]
            self.assertIn("capture_timestamp_missing", reason)

    def test_incompatible_ambient_strata_are_reported_separately_never_pooled(self) -> None:
        frames = [
            capture_rows("a1", "2026-02-02T09:00:00", [10, 12, 14, 16], ambient_source="station-a"),
            capture_rows("a2", "2026-02-02T10:00:00", [11, 13, 15, 17], ambient_source="station-a"),
            capture_rows("b1", "2026-02-02T11:00:00", [20, 22, 24, 26], ambient_source="station-b"),
            capture_rows("b2", "2026-02-02T12:00:00", [21, 23, 25, 27], ambient_source="station-b"),
        ]
        ids = ["a1", "a2", "b1", "b2"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_plan(root, frames, [confirmed_group(ids)])
            group_root = result.group_manifests[0].parent
            manifest = json.loads(result.group_manifests[0].read_text(encoding="utf-8"))
            self.assertTrue(manifest["delta_t_peak_to_trough_available"])
            findings = [
                value for value in manifest["compatibility_findings"]
                if value["analysis_family"] == "delta_t" and value["field"] == "ambient_source"
            ]
            self.assertEqual(findings[0]["code"], "incompatible_ambient_source_across_captures")
            delta = pd.read_csv(group_root / "tables" / "delta_t_peak_to_trough_statistics.csv")
            means = delta.loc[delta["statistic"].eq("mean") & delta["available"].astype(bool)]
            self.assertEqual(means["stratum_id"].nunique(), 2)
            self.assertTrue(means["eligible_capture_count"].eq(2).all())
            self.assertFalse(means["eligible_capture_count"].eq(4).any())
            report = (group_root / "temporal_summary.md").read_text(encoding="utf-8")
            self.assertIn("incompatible ambient references were never pooled", report)

    def test_explicit_invalid_capture_time_and_missing_source_are_hard_exclusions(self) -> None:
        frames = [
            capture_rows(
                "marked-invalid",
                "2026-02-02T09:00:00",
                [10, 12, 14, 16],
                capture_time_valid=False,
            ),
            capture_rows(
                "valid-a",
                "2026-02-02T10:00:00",
                [20, 22, 24, 26],
                capture_time_valid=True,
            ),
            capture_rows(
                "valid-b",
                "2026-02-02T11:00:00",
                [21, 23, 25, 27],
                capture_time_valid=True,
            ),
            capture_rows(
                "source-missing",
                "2026-02-02T12:00:00",
                [22, 24, 26, 28],
                capture_time_valid=True,
                capture_time_source="missing",
            ),
        ]
        ids = ["marked-invalid", "valid-a", "valid-b", "source-missing"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_plan(root, frames, [confirmed_group(ids)])
            group_root = result.group_manifests[0].parent
            manifest = json.loads(result.group_manifests[0].read_text(encoding="utf-8"))
            self.assertEqual(manifest["included_capture_list"], ["valid-a", "valid-b"])
            self.assertTrue(manifest["temporal_series_available"])
            exclusions = pd.read_csv(group_root / "qa" / "exclusions.csv").set_index("image_id")
            self.assertIn("capture_time_marked_invalid", exclusions.loc["marked-invalid", "exact_exclusion_reasons"])
            self.assertIn("capture_time_source_missing", exclusions.loc["source-missing", "exact_exclusion_reasons"])
            compatibility = pd.read_csv(group_root / "tables" / "capture_compatibility.csv").set_index("image_id")
            self.assertFalse(bool(compatibility.loc["marked-invalid", "capture_time_valid"]))
            self.assertEqual(compatibility.loc["valid-a", "capture_timezone_source"], "Asia/Hong_Kong")
            self.assertEqual(compatibility.loc["valid-a", "capture_timezone_output"], "Asia/Hong_Kong")
            valid_record = next(value for value in manifest["capture_records"] if value["image_id"] == "valid-a")
            self.assertEqual(valid_record["capture_timezone_source"], "Asia/Hong_Kong")
            self.assertEqual(valid_record["capture_timezone_output"], "Asia/Hong_Kong")
            self.assertIn("explicitly marks", exclusions.loc["marked-invalid", "exclusion_explanation"])

    def test_temperature_source_definition_unit_roi_and_qa_form_compatibility_gates(self) -> None:
        modifications = {
            "temperature source": {"temperature_source": "other_sensor"},
            "temperature definition": {"temperature_definition": "brightness temperature"},
            "temperature unit": {"temperature_unit": "kelvin"},
            "ROI method": {"roi_method": "different_roi_method"},
            "spatial processing method": {"spatial_processing_method": "different_spatial_method"},
        }
        for label, kwargs in modifications.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                frames = [
                    capture_rows("a", "2026-02-02T09:00:00", [10, 12, 14, 16]),
                    capture_rows("b", "2026-02-02T10:00:00", [20, 22, 24, 26], **kwargs),
                ]
                result = self.run_plan(root, frames, [confirmed_group(["a", "b"])])
                manifest = json.loads(result.group_manifests[0].read_text(encoding="utf-8"))
                self.assertFalse(manifest["temporal_series_available"])
                self.assertTrue(manifest["compatibility_findings"])
                report = (result.group_manifests[0].parent / "temporal_summary.md").read_text(encoding="utf-8")
                self.assertIn("Recorded values:", report)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frames = [
                capture_rows("a", "2026-02-02T09:00:00", [10, 12, 14, 16]),
                capture_rows("b", "2026-02-02T10:00:00", [20, 22, 24, 26], qa_status="fail"),
            ]
            result = self.run_plan(root, frames, [confirmed_group(["a", "b"])])
            manifest = json.loads(result.group_manifests[0].read_text(encoding="utf-8"))
            self.assertFalse(manifest["temporal_series_available"])
            exclusions = pd.read_csv(result.group_manifests[0].parent / "qa" / "exclusions.csv")
            self.assertIn(
                "qa_status_not_accepted",
                exclusions.loc[exclusions["image_id"].eq("b"), "exact_exclusion_reasons"].iloc[0],
            )

    def test_varying_roi_boundaries_are_explicitly_target_level_only(self) -> None:
        frames = [
            capture_rows(
                "a", "2026-02-02T09:00:00", [10, 12, 14, 16],
                roi_mask_sha256="mask-a", roi_polygon_area_px2=100.0,
                roi_comparability_evidence="accepted polygon drawn for capture a",
            ),
            capture_rows(
                "b", "2026-02-02T10:00:00", [20, 22, 24, 26],
                roi_mask_sha256="mask-b", roi_polygon_area_px2=112.0,
                roi_comparability_evidence="accepted polygon drawn for capture b",
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_plan(root, frames, [confirmed_group(["a", "b"])])
            group_root = result.group_manifests[0].parent
            manifest = json.loads(result.group_manifests[0].read_text(encoding="utf-8"))
            roi = manifest["roi_comparability"]
            self.assertEqual(roi["status"], "user_confirmed_varying_roi_target_level_only")
            self.assertTrue(roi["target_level_statistics_valid"])
            self.assertTrue(roi["target_level_only"])
            self.assertEqual(roi["boundary_fingerprints"], ["mask-a", "mask-b"])
            self.assertEqual(len(roi["capture_evidence"]), 2)
            report = (group_root / "temporal_summary.md").read_text(encoding="utf-8")
            self.assertIn("user_confirmed_varying_roi_target_level_only", report)
            self.assertIn("only capture-level ROI summaries are compared", report)

    def test_identity_conflict_requires_confirmed_override_and_reason(self) -> None:
        frames = [
            capture_rows("a", "2026-02-02T09:00:00", [10, 12, 14, 16], target_id="recorded-a"),
            capture_rows("b", "2026-02-02T10:00:00", [20, 22, 24, 26], target_id="recorded-b"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_plan(root, frames, [confirmed_group(["a", "b"])])
            manifest = json.loads(result.group_manifests[0].read_text(encoding="utf-8"))
            self.assertEqual(manifest["trend_status"], "spatial_identity_conflict")
            self.assertFalse(manifest["temporal_series_available"])
            self.assertTrue(manifest["recorded_identity_conflicts"])

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            group = confirmed_group(
                ["a", "b"],
                override=True,
                override_reason="Reviewer verified both captures show the same field despite legacy target IDs.",
            )
            result = self.run_plan(root, frames, [group])
            manifest = json.loads(result.group_manifests[0].read_text(encoding="utf-8"))
            self.assertTrue(manifest["temporal_series_available"])
            spatial = json.loads(
                (result.group_manifests[0].parent / "qa" / "spatial_identity_confirmation.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(spatial["override_applied"])
            self.assertIn("Reviewer verified", spatial["spatial_override_reason"])

    def test_target_name_registration_and_explicit_roi_non_overlap_are_identity_conflicts(self) -> None:
        frames = [
            capture_rows(
                "a", "2026-02-02T09:00:00", [10, 12, 14, 16],
                target_name="North pitch", spatial_registration_id="registration-old",
                roi_boundary_overlap_fraction=1.0,
            ),
            capture_rows(
                "b", "2026-02-02T10:00:00", [20, 22, 24, 26],
                target_name="South pitch", spatial_registration_id="registration-other",
                roi_boundary_overlap_fraction=0.0,
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_plan(Path(directory), frames, [confirmed_group(["a", "b"], registration=True)])
            manifest = json.loads(result.group_manifests[0].read_text(encoding="utf-8"))
            conflicts = manifest["recorded_identity_conflicts"]
            self.assertTrue(any(value.startswith("conflicting_target_names:") for value in conflicts))
            self.assertTrue(any(value.startswith("conflicting_spatial_registration_ids:") for value in conflicts))
            self.assertIn("accepted_roi_non_overlap:b", conflicts)
            self.assertFalse(manifest["temporal_series_available"])

    def test_gps_conflict_is_a_core_gate_and_requires_a_reasoned_override(self) -> None:
        frames = [
            capture_rows(
                "near",
                "2026-02-02T09:00:00",
                [10, 12, 14, 16],
                gps_latitude=22.3400,
                gps_longitude=114.2600,
            ),
            capture_rows(
                "far",
                "2026-02-02T10:00:00",
                [20, 22, 24, 26],
                # About 150 m away: this specifically guards the former 100-250 m policy gap.
                gps_latitude=22.34135,
                gps_longitude=114.2600,
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_plan(root, frames, [confirmed_group(["near", "far"])])
            manifest = json.loads(result.group_manifests[0].read_text(encoding="utf-8"))
            self.assertFalse(manifest["temporal_series_available"])
            self.assertTrue(
                any(value.startswith("gps_distance_conflict:") for value in manifest["recorded_identity_conflicts"])
            )
            self.assertTrue(any(">100.0m" in value for value in manifest["recorded_identity_conflicts"]))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_plan(
                root,
                frames,
                [
                    confirmed_group(
                        ["near", "far"],
                        override=True,
                        override_reason="Visible landmarks and surveyed target boundary confirm one site.",
                    )
                ],
            )
            manifest = json.loads(result.group_manifests[0].read_text(encoding="utf-8"))
            self.assertTrue(manifest["temporal_series_available"])
            self.assertEqual(manifest["capture_records"][0]["gps_longitude"], 114.26)

    def test_multiple_temporal_groups_are_stored_and_analyzed_separately(self) -> None:
        frames = [
            capture_rows("a1", "2026-02-02T09:00:00", [10, 10, 10, 10]),
            capture_rows("a2", "2026-02-02T10:00:00", [20, 20, 20, 20]),
            capture_rows(
                "b1", "2026-02-02T09:30:00", [100, 100, 100, 100],
                target_id="target-b", location_id="location-b",
            ),
            capture_rows(
                "b2", "2026-02-02T10:30:00", [104, 104, 104, 104],
                target_id="target-b", location_id="location-b",
            ),
        ]
        group_a = confirmed_group(["a1", "a2"], group_id="location-a-series")
        group_b = TemporalGroupDefinition(
            temporal_group_id="location-b-series",
            image_ids=["b1", "b2"],
            location_id="location-b",
            target_id="target-b",
            same_location_confirmed=True,
            confirmation_provenance="fixture_confirmation",
            roi_comparable_confirmed=True,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_plan(root, frames, [group_a, group_b])
            self.assertEqual(len(result.group_manifests), 2)
            ranges: dict[str, float] = {}
            for manifest_path in result.group_manifests:
                peak = pd.read_csv(manifest_path.parent / "tables" / "peak_to_trough_statistics.csv")
                ranges[manifest_path.parent.name] = float(
                    peak.loc[peak["statistic"].eq("mean"), "observed_peak_to_trough_range_c"].iloc[0]
                )
            self.assertEqual(ranges, {"location-a-series": 10.0, "location-b-series": 4.0})

    def test_one_capture_is_descriptive_without_range_trend_or_figure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_plan(
                root,
                [capture_rows("single", "2026-02-02T12:00:00", [40, 41, 42, 43])],
                [confirmed_group(["single"])],
            )
            group_root = result.group_manifests[0].parent
            manifest = json.loads(result.group_manifests[0].read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(manifest["analysis_completion_status"], "complete")
            self.assertEqual(manifest["temporal_result_availability"], "unavailable")
            self.assertEqual(manifest["eligible_capture_count"], 1)
            self.assertEqual(manifest["trend_status"], "single_capture_descriptive_no_trend")
            self.assertFalse(manifest["temporal_series_available"])
            self.assertFalse(manifest["peak_to_trough_available"])
            self.assertEqual(list(group_root.rglob("*.png")), [])
            self.assertEqual(list(group_root.rglob("*.pdf")), [])
            report = (group_root / "temporal_summary.md").read_text(encoding="utf-8")
            self.assertIn("Only one eligible capture is available", report)
            self.assertIn("Capture time (local): 2026-02-02T12:00:00+08:00", report)
            self.assertIn("Capture-time source: exif_datetime_original", report)
            self.assertIn("Capture timezone (source): Asia/Hong_Kong", report)
            for expected in (
                "ROI minimum: 40.000°C",
                "ROI maximum: 43.000°C",
                "ROI mean: 41.500°C",
                "ROI median: 41.500°C",
                "ROI q01: 40.030°C",
                "ROI q05: 40.150°C",
                "ROI q95: 42.850°C",
                "ROI q99: 42.970°C",
            ):
                self.assertIn(expected, report)

    def test_sampling_coverage_reports_gaps_and_does_not_claim_true_daily_range(self) -> None:
        frames = [
            capture_rows("night", "2026-02-02T01:00:00", [10, 12, 14, 16]),
            capture_rows("day", "2026-02-02T17:00:00", [20, 22, 24, 26]),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_plan(root, frames, [confirmed_group(["night", "day"])])
            coverage = pd.read_csv(result.group_manifests[0].parent / "tables" / "sampling_coverage.csv")
            row = coverage.iloc[0]
            self.assertAlmostEqual(float(row["largest_interval_hours"]), 16.0)
            self.assertTrue(bool(row["daytime_present"]))
            self.assertTrue(bool(row["nighttime_present"]))
            self.assertFalse(bool(row["true_daily_extrema_supported"]))
            self.assertIn("true daily maximum or minimum may be unobserved", row["coverage_statement"])

    def test_full_day_claim_requires_confirmed_dense_day_and_night_sampling(self) -> None:
        times = [
            "2026-02-02T00:00:00",
            "2026-02-02T04:00:00",
            "2026-02-02T08:00:00",
            "2026-02-02T12:00:00",
            "2026-02-02T16:00:00",
            "2026-02-02T20:00:00",
            "2026-02-03T00:00:00",
        ]
        ids = [f"capture-{index}" for index in range(len(times))]
        frames = [
            capture_rows(image_id, capture_time, [10 + index] * 4)
            for index, (image_id, capture_time) in enumerate(zip(ids, times))
        ]
        windows = [
            {
                "observation_window_id": "confirmed-full-day",
                "start_local": "2026-02-02T00:00:00",
                "end_local": "2026-02-03T00:00:00",
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_plan(
                root,
                frames,
                [confirmed_group(ids, windows=windows, full_day_sampling=True)],
            )
            coverage = pd.read_csv(result.group_manifests[0].parent / "tables" / "sampling_coverage.csv")
            row = coverage.iloc[0]
            self.assertEqual(int(row["eligible_capture_count"]), 7)
            self.assertAlmostEqual(float(row["observation_span_hours"]), 24.0)
            self.assertAlmostEqual(float(row["largest_interval_hours"]), 4.0)
            self.assertTrue(bool(row["true_daily_extrema_supported"]))
            self.assertEqual(row["sampling_coverage_status"], "full_day_sampling_design_confirmed")

        sparse_times = times.copy()
        sparse_times[1] = "2026-02-02T05:00:00"
        sparse_frames = [
            capture_rows(image_id, capture_time, [10 + index] * 4)
            for index, (image_id, capture_time) in enumerate(zip(ids, sparse_times))
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_plan(
                root,
                sparse_frames,
                [confirmed_group(ids, windows=windows, full_day_sampling=True)],
            )
            coverage = pd.read_csv(result.group_manifests[0].parent / "tables" / "sampling_coverage.csv")
            row = coverage.iloc[0]
            self.assertFalse(bool(row["true_daily_extrema_supported"]))
            self.assertIn("maximum_sampling_gap_exceeds_four_hours", row["full_day_gate_failures"])

    def test_default_local_dates_do_not_pool_across_dates_but_explicit_window_can(self) -> None:
        frames = [
            capture_rows("late", "2026-02-02T23:00:00", [10, 12, 14, 16]),
            capture_rows("early", "2026-02-03T01:00:00", [20, 22, 24, 26]),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_plan(root, frames, [confirmed_group(["late", "early"])])
            manifest = json.loads(result.group_manifests[0].read_text(encoding="utf-8"))
            self.assertFalse(manifest["temporal_series_available"])

        windows = [
            {
                "observation_window_id": "overnight-window",
                "start_local": "2026-02-02T22:00:00",
                "end_local": "2026-02-03T02:00:00",
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_plan(root, frames, [confirmed_group(["late", "early"], windows=windows)])
            manifest = json.loads(result.group_manifests[0].read_text(encoding="utf-8"))
            self.assertTrue(manifest["temporal_series_available"])
            peaks = pd.read_csv(result.group_manifests[0].parent / "tables" / "peak_to_trough_statistics.csv")
            self.assertTrue(peaks["observation_window_id"].eq("overnight-window").all())

    def test_pixelwise_maps_require_explicit_registration_and_comparable_grid_intersection(self) -> None:
        frames = [
            capture_rows("a", "2026-02-02T09:00:00", [10, 12, 14, 16]),
            capture_rows("b", "2026-02-02T10:00:00", [11, 15, 13, 20]),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_plan(root, frames, [confirmed_group(["a", "b"])])
            manifest = json.loads(result.group_manifests[0].read_text(encoding="utf-8"))
            self.assertFalse(manifest["pixelwise_temporal_analysis_available"])
            self.assertEqual(manifest["pixelwise_unavailable_reason"], "cross_capture_registration_not_confirmed")
            self.assertFalse(any("pixelwise" in path.name for path in result.group_manifests[0].parent.rglob("*")))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_plan(root, frames, [confirmed_group(["a", "b"], registration=True)])
            group_root = result.group_manifests[0].parent
            manifest = json.loads(result.group_manifests[0].read_text(encoding="utf-8"))
            self.assertTrue(manifest["pixelwise_temporal_analysis_available"])
            observed_range = np.load(group_root / "figures" / "pixelwise_observed_temperature_range.npy")
            np.testing.assert_allclose(observed_range, np.array([[1, 3], [1, 4]], dtype=np.float32))
            changes = pd.read_csv(group_root / "figures" / "pixelwise_largest_observed_changes.csv")
            self.assertEqual((int(changes.iloc[0]["thermal_row"]), int(changes.iloc[0]["thermal_col"])), (1, 1))

        mismatched = [
            frames[0],
            capture_rows("b", "2026-02-02T10:00:00", [11, 12, 13, 14, 15, 16], shape=(2, 3)),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_plan(root, mismatched, [confirmed_group(["a", "b"], registration=True)])
            manifest = json.loads(result.group_manifests[0].read_text(encoding="utf-8"))
            self.assertFalse(manifest["pixelwise_temporal_analysis_available"])
            self.assertEqual(manifest["pixelwise_unavailable_reason"], "registered_capture_shapes_differ")

    def test_pixelwise_maps_reject_multiple_eligible_strata_or_windows(self) -> None:
        frames = [
            capture_rows("morning-a", "2026-02-02T08:00:00", [10, 12, 14, 16]),
            capture_rows("morning-b", "2026-02-02T09:00:00", [11, 13, 15, 17]),
            capture_rows("evening-a", "2026-02-02T18:00:00", [20, 22, 24, 26]),
            capture_rows("evening-b", "2026-02-02T19:00:00", [21, 23, 25, 27]),
        ]
        windows = [
            {
                "observation_window_id": "morning",
                "start_local": "2026-02-02T07:00:00",
                "end_local": "2026-02-02T10:00:00",
            },
            {
                "observation_window_id": "evening",
                "start_local": "2026-02-02T17:00:00",
                "end_local": "2026-02-02T20:00:00",
            },
        ]
        ids = ["morning-a", "morning-b", "evening-a", "evening-b"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_plan(
                root,
                frames,
                [confirmed_group(ids, registration=True, windows=windows)],
            )
            group_root = result.group_manifests[0].parent
            manifest = json.loads(result.group_manifests[0].read_text(encoding="utf-8"))
            self.assertTrue(manifest["temporal_series_available"])
            self.assertFalse(manifest["pixelwise_temporal_analysis_available"])
            self.assertEqual(
                manifest["pixelwise_unavailable_reason"],
                "multiple_compatibility_strata_or_observation_windows",
            )
            self.assertFalse(any("pixelwise" in path.name for path in group_root.rglob("*")))

    def test_compatibility_helpers_do_not_claim_a_series_without_explicit_plan(self) -> None:
        frame = pd.concat(
            [
                capture_rows("a", "2026-02-02T09:00:00", [10, 12, 14, 16]),
                capture_rows("b", "2026-02-02T10:00:00", [20, 22, 24, 26]),
            ],
            ignore_index=True,
        )
        captures, inclusion, diagnostics = build_capture_summary(frame, default_timezone="Asia/Hong_Kong")
        self.assertEqual(len(captures), 2)
        self.assertTrue(inclusion["temperature_trend_eligible"].all())
        self.assertTrue(diagnostics.empty)
        strata = build_stratum_summary(captures)
        temperature = strata.loc[strata["metric_family"].eq("temperature")].iloc[0]
        self.assertEqual(temperature["trend_status"], "explicit_plan_required_before_temporal_series")


if __name__ == "__main__":
    unittest.main()
