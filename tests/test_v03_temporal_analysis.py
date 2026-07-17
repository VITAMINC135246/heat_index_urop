from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.workflow.temporal_analysis import (
    build_capture_summary,
    build_stratum_summary,
    run_temporal_analysis,
)


def capture_rows(
    image_id: str,
    capture_time: str,
    temperatures: list[float],
    *,
    ambient: float | None = 20.0,
    target_id: str = "hkust-soccer-field",
    target_name: str = "HKUST soccer field",
    measurement_type: str = "polygon_selected_thermal_pixel",
    source_method: str = "thermal_polygon_user_annotation",
    temperature_source: str = "mocked_temperature_matrix",
    capture_timezone: str = "Asia/Hong_Kong",
    ambient_source: str = "mocked_station_fixture",
    ambient_definition: str = "near-surface air temperature",
) -> pd.DataFrame:
    values = np.asarray(temperatures, dtype=float)
    delta = values - ambient if ambient is not None else np.full(values.shape, np.nan)
    return pd.DataFrame(
        {
            "image_id": image_id,
            "pixel_uid": [f"{image_id}__{index}" for index in range(len(values))],
            "temperature_c": values,
            "delta_t_c": delta,
            "ambient_temperature_c": np.nan if ambient is None else ambient,
            "capture_datetime": capture_time,
            "capture_timezone": capture_timezone,
            "measurement_type": measurement_type,
            "temperature_source": temperature_source,
            "temperature_definition": "per-pixel radiometric surface temperature",
            "source_method": source_method,
            "surface_cover_provenance": source_method,
            "luhk_provenance": "user_supplied_luhk",
            "target_id": target_id,
            "target_name": target_name,
            "qa_status": "pass",
            "ambient_source": ambient_source if ambient is not None else "",
            "ambient_definition": ambient_definition if ambient is not None else "",
            "analysis_eligible": True,
            "temperature_is_finite": True,
            "label_known": True,
            "target_mask": True,
        }
    )


class V03TemporalAnalysisTests(unittest.TestCase):
    def test_timestamp_order_timezone_and_irregular_intervals(self) -> None:
        frame = pd.concat(
            [
                capture_rows("c3", "2026-02-02T12:00:00", [30, 32]),
                capture_rows("c1", "2026-02-02T01:00:00+00:00", [20, 22], capture_timezone=""),
                capture_rows("c2", "2026-02-02T10:00:00", [25, 27]),
            ],
            ignore_index=True,
        )
        captures, _, diagnostics = build_capture_summary(frame, default_timezone="Asia/Hong_Kong")
        self.assertEqual(list(captures["image_id"]), ["c1", "c2", "c3"])
        self.assertEqual(captures.iloc[0]["capture_time_local"], "2026-02-02T09:00:00+08:00")
        self.assertEqual(captures.iloc[1]["timezone_assumption"], "capture_timezone_metadata")
        self.assertTrue(diagnostics.empty)
        strata = build_stratum_summary(captures)
        temperature = strata.loc[strata["metric_family"].eq("temperature")].iloc[0]
        self.assertEqual(int(temperature["compatible_capture_count"]), 3)
        self.assertTrue(bool(temperature["irregular_intervals"]))
        self.assertEqual(temperature["trend_status"], "multi_capture_descriptive_exploratory")

    def test_equal_image_aggregation_not_pixel_weighted(self) -> None:
        frame = pd.concat(
            [
                capture_rows("small", "2026-02-02T09:00:00", [10.0, 10.0], ambient=5.0),
                capture_rows("large", "2026-02-02T10:00:00", [30.0] * 100, ambient=5.0),
            ],
            ignore_index=True,
        )
        captures, _, _ = build_capture_summary(frame, default_timezone="Asia/Hong_Kong")
        strata = build_stratum_summary(captures)
        temperature = strata.loc[strata["metric_family"].eq("temperature")].iloc[0]
        self.assertAlmostEqual(float(temperature["equal_image_mean_of_capture_means_c"]), 20.0)
        self.assertNotAlmostEqual(float(temperature["equal_image_mean_of_capture_means_c"]), float(frame["temperature_c"].mean()))

    def test_duplicate_timestamp_missing_ambient_and_one_capture_behavior(self) -> None:
        duplicate = pd.concat(
            [
                capture_rows("a", "2026-02-02T09:00:00", [30, 31]),
                capture_rows("b", "2026-02-02T09:00:00", [32, 33], ambient=None),
            ],
            ignore_index=True,
        )
        captures, inclusion, diagnostics = build_capture_summary(duplicate, default_timezone="Asia/Hong_Kong")
        self.assertTrue(diagnostics["diagnostic"].eq("duplicate_timestamp_within_compatible_stratum").any())
        missing = captures.loc[captures["image_id"].eq("b")].iloc[0]
        self.assertTrue(np.isfinite(float(missing["temperature_mean_c"])))
        self.assertTrue(np.isnan(float(missing["delta_t_mean_c"])))
        self.assertFalse(bool(inclusion.loc[inclusion["image_id"].eq("b"), "delta_t_descriptive_included"].iloc[0]))

        single, _, _ = build_capture_summary(
            capture_rows("single", "2026-02-02T12:00:00", [40, 42]),
            default_timezone="Asia/Hong_Kong",
        )
        one = build_stratum_summary(single)
        self.assertTrue(one["trend_status"].eq("single_capture_descriptive_no_trend").all())

    def test_sources_measurements_and_targets_are_not_silently_pooled(self) -> None:
        frame = pd.concat(
            [
                capture_rows("p1", "2026-02-02T09:00:00", [30, 31], target_id="field-a"),
                capture_rows("p2", "2026-02-02T10:00:00", [32, 33], target_id="field-b"),
                capture_rows(
                    "tat3",
                    "2026-02-02T11:00:00",
                    [34],
                    target_id="field-a",
                    measurement_type="manual_tat3_point",
                    source_method="tat3_manual_measurement",
                    temperature_source="tat3_report_value",
                ),
                capture_rows("missing-id", "2026-02-02T12:00:00", [35, 36], target_id=""),
            ],
            ignore_index=True,
        )
        captures, _, diagnostics = build_capture_summary(frame, default_timezone="Asia/Hong_Kong")
        self.assertEqual(captures["temperature_stratum_id"].nunique(), 4)
        self.assertTrue(diagnostics["diagnostic"].eq("missing_target_id_for_cross_capture_linkage").any())
        missing = captures.loc[captures["image_id"].eq("missing-id")].iloc[0]
        self.assertTrue(str(missing["target_linkage_key"]).startswith("unlinked:"))

    def test_duplicate_image_grid_is_detected(self) -> None:
        original = capture_rows("duplicate", "2026-02-02T09:00:00", [30, 31])
        frame = pd.concat([original, original], ignore_index=True)
        captures, _, diagnostics = build_capture_summary(frame, default_timezone="Asia/Hong_Kong")
        self.assertTrue(bool(captures.iloc[0]["duplicate_image_id"]))
        self.assertFalse(bool(captures.iloc[0]["temperature_trend_eligible"]))
        self.assertTrue(diagnostics["diagnostic"].eq("duplicate_image_id_or_measurement_grid").any())

    def test_outputs_cache_invalidation_zero_case_and_no_fabricated_26(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            canonical = root / "temporal.parquet"
            frame = pd.concat(
                [
                    capture_rows("t1", "2026-02-02T09:00:00", [30, 31]),
                    capture_rows("t2", "2026-02-02T10:30:00", [35, 36]),
                ],
                ignore_index=True,
            )
            frame.to_parquet(canonical, index=False)
            output = root / "output"
            first = run_temporal_analysis(
                canonical, output_root=output, default_timezone="Asia/Hong_Kong", resume=True
            )
            self.assertEqual(first.status, "complete")
            capture_text = first.capture_summary.read_text(encoding="utf-8-sig")
            second = run_temporal_analysis(
                canonical, output_root=output, default_timezone="Asia/Hong_Kong", resume=True
            )
            self.assertEqual(second.status, "cache_hit")
            self.assertEqual(capture_text, second.capture_summary.read_text(encoding="utf-8-sig"))
            self.assertTrue((output / "figures" / "temporal_temperature_series.png").stat().st_size > 100)
            report = first.report.read_text(encoding="utf-8")
            self.assertIn("does not contain or fabricate a 26°C result", report)

            changed = pd.concat([frame, capture_rows("t3", "2026-02-02T12:00:00", [40, 41])], ignore_index=True)
            changed.to_parquet(canonical, index=False)
            third = run_temporal_analysis(
                canonical, output_root=output, default_timezone="Asia/Hong_Kong", resume=True
            )
            self.assertEqual(third.status, "complete")

            empty = root / "empty.parquet"
            frame.iloc[0:0].to_parquet(empty, index=False)
            empty_result = run_temporal_analysis(
                empty, output_root=root / "empty-output", default_timezone="Asia/Hong_Kong", resume=False
            )
            self.assertEqual(empty_result.status, "complete")
            empty_summary = pd.read_csv(empty_result.capture_summary)
            self.assertTrue(empty_summary.empty)


if __name__ == "__main__":
    unittest.main()
