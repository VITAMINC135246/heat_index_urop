from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

import pandas as pd

from scripts.run_analysis import temporal_user_summary_lines
from scripts.run_user_workflow import build_command, workflow_python
from scripts.workflow_gui import WorkflowGUI
from scripts.workflow.polygon_annotation import run_polygon_gui_subprocess
from scripts.workflow.temporal_interactive import _capture_cards, collect_temporal_plan


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class UserWorkflowTests(unittest.TestCase):
    def test_gui_pythonw_launcher_uses_console_python_for_child_logs(self) -> None:
        with patch("scripts.run_user_workflow.os.name", "nt"), patch(
            "scripts.run_user_workflow.sys.executable", str(PROJECT_ROOT / ".venv" / "Scripts" / "pythonw.exe")
        ):
            self.assertEqual(
                workflow_python(),
                str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"),
            )

    @staticmethod
    def _temporal_card(
        image_id: str,
        *,
        latitude: float,
        longitude: float,
        location_id: str = "field",
        target_id: str = "pitch",
    ) -> dict[str, object]:
        return {
            "manifest": object(),
            "image_id": image_id,
            "visible_path": f"{image_id}_V.JPG",
            "thermal_path": f"{image_id}_T.JPG",
            "capture_datetime": f"2026-02-02T0{image_id[-1]}:00:00+08:00",
            "capture_time_source": "dji_filename_timestamp",
            "gps_latitude": latitude,
            "gps_longitude": longitude,
            "target_id": target_id,
            "location_id": location_id,
            "target_name": "Football field",
            "dataset_id": "football-test",
            "measurement_source": "dji_sdk_radiometric_temperature",
            "measurement_type": "polygon_selected_thermal_pixel",
        }

    def test_capture_cards_select_one_valid_time_bundle_without_mixing_sources(self) -> None:
        common = {
            "image_id": "capture-1",
            "visible_path": "visible.jpg",
            "thermal_path": "thermal.jpg",
            "gps_latitude": 22.3,
            "gps_longitude": 114.2,
            "target_id": "pitch",
            "location_id": "field",
            "target_name": "Football field",
            "dataset_id": "football-test",
            "temperature_source": "dji_sdk_radiometric_temperature",
            "measurement_type": SimpleNamespace(value="polygon_selected_thermal_pixel"),
        }
        temperature_bundle = {
            "capture_datetime": "2026-02-02T14:08:15+08:00",
            "capture_time_local": "2026-02-02T14:08:15+08:00",
            "capture_time_utc": "2026-02-02T06:08:15+00:00",
            "capture_timezone": "Asia/Hong_Kong",
            "capture_time_source": "dji_metadata_record",
            "timezone_assumption": "metadata_timezone",
            "capture_time_valid": True,
        }
        invalid_manifest = dict(
            common,
            capture_datetime="",
            capture_time_local="",
            capture_time_utc="stale-utc-must-not-leak",
            capture_timezone="stale-zone-must-not-leak",
            capture_time_source="missing",
            timezone_assumption="stale-assumption-must-not-leak",
            capture_time_valid=False,
            temperature_metadata=temperature_bundle,
            part_a={"capture_time": "2026-02-02T09:00:00+08:00"},
        )
        with patch(
            "scripts.workflow.temporal_interactive.load_manifest",
            return_value=SimpleNamespace(**invalid_manifest),
        ):
            card = _capture_cards([Path("manifest.json")])[0]
        self.assertEqual(card["capture_datetime"], temperature_bundle["capture_time_local"])
        self.assertEqual(card["capture_time_utc"], temperature_bundle["capture_time_utc"])
        self.assertEqual(card["capture_timezone"], temperature_bundle["capture_timezone"])
        self.assertEqual(card["capture_time_source"], temperature_bundle["capture_time_source"])
        self.assertEqual(card["timezone_assumption"], temperature_bundle["timezone_assumption"])

        part_a_bundle = {
            "capture_time": "2026-02-02T09:11:28+08:00",
            "capture_time_local": "2026-02-02T09:11:28+08:00",
            "capture_time_utc": "2026-02-02T01:11:28+00:00",
            "capture_timezone": "Asia/Hong_Kong",
            "timezone_assumption": "legacy_part_a_metadata",
            "capture_time_valid": True,
        }
        invalid_temperature = {
            "capture_time": "",
            "capture_time_source": "missing",
            "capture_time_valid": False,
        }
        part_a_manifest = dict(
            invalid_manifest,
            temperature_metadata=invalid_temperature,
            part_a=part_a_bundle,
        )
        with patch(
            "scripts.workflow.temporal_interactive.load_manifest",
            return_value=SimpleNamespace(**part_a_manifest),
        ):
            fallback_card = _capture_cards([Path("manifest.json")])[0]
        self.assertEqual(fallback_card["capture_datetime"], part_a_bundle["capture_time_local"])
        self.assertEqual(fallback_card["capture_time_utc"], part_a_bundle["capture_time_utc"])
        self.assertEqual(fallback_card["capture_timezone"], part_a_bundle["capture_timezone"])
        self.assertEqual(fallback_card["capture_time_source"], "part_a_capture_time_fallback")
        self.assertEqual(fallback_card["timezone_assumption"], part_a_bundle["timezone_assumption"])

    def test_declining_spatial_conflict_override_rejects_group(self) -> None:
        cards = [
            self._temporal_card("capture-1", latitude=22.3, longitude=114.2),
            self._temporal_card("capture-2", latitude=23.3, longitude=114.2),
        ]
        answers = iter(
            [
                "1,2",
                "Football field",
                "field",
                "pitch",
                "field-series",
                "y",
                "y",
                "n",
                "",
            ]
        )
        prompts: list[str] = []
        messages: list[str] = []

        def answer(prompt: str) -> str:
            prompts.append(prompt)
            return next(answers)

        with patch("scripts.workflow.temporal_interactive._capture_cards", return_value=cards):
            plan = collect_temporal_plan(
                [Path("one.json"), Path("two.json")],
                requested=True,
                input_func=answer,
                output_func=messages.append,
            )
        self.assertTrue(plan.temporal_requested)
        self.assertEqual(plan.groups, [])
        self.assertTrue(any("not accepted because the spatial conflicts were not overridden" in line for line in messages))
        self.assertFalse(any("pixel-level spatial registration" in prompt for prompt in prompts))

    def test_accepted_spatial_override_records_confirmation_and_reason(self) -> None:
        cards = [
            self._temporal_card("capture-1", latitude=22.3, longitude=114.2),
            self._temporal_card("capture-2", latitude=23.3, longitude=114.2),
        ]
        answers = iter(
            [
                "1,2",
                "Football field",
                "field",
                "pitch",
                "field-series",
                "y",
                "y",
                "y",
                "Reviewed both accepted pitch polygons against the stadium boundary.",
                "n",
                "n",
            ]
        )
        with patch("scripts.workflow.temporal_interactive._capture_cards", return_value=cards):
            plan = collect_temporal_plan(
                [Path("one.json"), Path("two.json")],
                requested=True,
                input_func=lambda _prompt: next(answers),
                output_func=lambda _message: None,
            )
        self.assertEqual(len(plan.groups), 1)
        self.assertTrue(plan.groups[0].spatial_override_confirmed)
        self.assertEqual(
            plan.groups[0].spatial_override_reason,
            "Reviewed both accepted pitch polygons against the stadium boundary.",
        )

    def test_all_command_needs_real_inputs_but_no_user_json_or_config_authoring(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            visible = root / "DJI_20260202091127_0058_V.JPG"
            thermal = root / "DJI_20260202091128_0058_T.JPG"
            report = root / "report.docx"
            Image.new("RGB", (4, 3), "green").save(visible)
            Image.new("RGB", (4, 3), "gray").save(thermal)
            report.write_bytes(b"report")
            args = Namespace(
                production=False,
                open_results=False,
                workflow="all",
                visible=str(visible),
                thermal=str(thermal),
                tat3_report=str(report),
                target_name="HKUST football field",
                target_id="hkust-football-field-natural-turf",
                surface_cover="grass_low_vegetation",
                luhk="GIC / open space",
                confidence="medium",
                redraw_polygon=True,
            )
            command = build_command(args)
            self.assertEqual(command.count("--group"), 6)
            self.assertIn("--tat3-report", command)
            self.assertIn("--polygon-image-id", command)
            self.assertEqual(
                command[command.index("--reprocess-image-id") + 1],
                "DJI_20260202091128_0058",
            )
            self.assertIn("--require-all-success", command)
            self.assertEqual(command[command.index("--temporal") + 1], "ask")
            self.assertNotIn("--polygon-json", command)
            self.assertNotIn("--ambient-json", command)
            self.assertNotIn("--part-b0-review", command)

    def test_user_report_states_clean_temporal_skip_without_json_inspection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "temporal_run_manifest.json"
            manifest.write_text(
                json.dumps({"status": "complete", "temporal_requested": False, "groups": []}),
                encoding="utf-8",
            )
            lines = temporal_user_summary_lines({"temporal_run_manifest": str(manifest)}, root.parent)
            self.assertIn("Temporal analysis was not requested.", lines)

    def test_temporal_prompt_defaults_to_no_when_standard_input_is_closed(self) -> None:
        from scripts.workflow.temporal_interactive import collect_temporal_plan

        def closed_input(_prompt: str) -> str:
            raise EOFError

        messages: list[str] = []
        plan = collect_temporal_plan([], input_func=closed_input, output_func=messages.append)
        self.assertFalse(plan.temporal_requested)
        self.assertIn("Temporal analysis was not requested", messages[0])

    def test_several_groups_and_reports_are_supported_without_user_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pairs = []
            for index in (1, 2):
                visible = root / f"DJI_20260202090{index}00_000{index}_V.JPG"
                thermal = root / f"DJI_20260202090{index}01_000{index}_T.JPG"
                Image.new("RGB", (4, 3), "green").save(visible)
                Image.new("RGB", (4, 3), "gray").save(thermal)
                pairs.append((str(visible), str(thermal)))
            reports = [root / "morning.docx", root / "afternoon.docx"]
            for report in reports:
                report.write_bytes(b"report")
            command = build_command(
                Namespace(
                    production=False,
                    open_results=False,
                    workflow="groups",
                    group=pairs,
                    tat3_report=[str(path) for path in reports],
                    polygon_all=True,
                    target_name="HKUST football field",
                    target_id="hkust-football-field-natural-turf",
                    surface_cover="grass_low_vegetation",
                    luhk="GIC / open space",
                    confidence="medium",
                    redraw_review=True,
                )
            )
            self.assertEqual(command.count("--group"), 2)
            self.assertEqual(command.count("--tat3-report"), 2)
            self.assertIn("--launch-part-c-gui", command)
            self.assertEqual(command.count("--polygon-image-id"), 2)
            self.assertEqual(command.count("--reprocess-image-id"), 2)
            self.assertEqual(command[command.index("--temporal") + 1], "ask")

    def test_one_group_can_resume_a_saved_part_c_draft(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            visible = root / "DJI_20260202091127_0058_V.JPG"
            thermal = root / "DJI_20260202091128_0058_T.JPG"
            draft = root / "superpixel_review.json"
            Image.new("RGB", (4, 3), "green").save(visible)
            Image.new("RGB", (4, 3), "gray").save(thermal)
            draft.write_text("{}", encoding="utf-8")
            command = build_command(
                Namespace(
                    production=False,
                    open_results=False,
                    workflow="group",
                    visible=str(visible),
                    thermal=str(thermal),
                    tat3_report=[],
                    resume_part_c=str(draft),
                    redraw_review=False,
                )
            )
            value = command[command.index("--part-c-review") + 1]
            self.assertEqual(value, f"DJI_20260202091128_0058={draft.resolve()}")

    def test_desktop_gui_builds_a_several_group_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pairs: list[tuple[str, str]] = []
            for index in (1, 2):
                visible = root / f"group_{index}_V.JPG"
                thermal = root / f"group_{index}_T.JPG"
                visible.write_bytes(b"visible")
                thermal.write_bytes(b"thermal")
                pairs.append((str(visible), str(thermal)))
            value = lambda result: SimpleNamespace(get=lambda: result)
            gui = WorkflowGUI.__new__(WorkflowGUI)
            gui.mode = value("多组 V/T 图片")
            gui.production = value(False)
            gui.group_pairs = pairs
            gui.tat3 = value("")
            gui.redraw = value(True)
            gui.polygon_all = value(True)
            gui.target_name = value("HKUST football field")
            gui.target_id = value("hkust-football-field-natural-turf")
            gui.surface_cover = value("grass_low_vegetation")
            gui.luhk = value("GIC / open space")
            gui.confidence = value("medium")
            command = gui._command()
            self.assertEqual(command.count("--group"), 2)
            self.assertIn("groups", command)
            self.assertIn("--redraw-review", command)
            self.assertIn("--polygon-all", command)
            self.assertIn("hkust-football-field-natural-turf", command)

    def test_user_report_surfaces_primary_and_absolute_temporal_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            group_id = "field-series"
            tables = root / group_id / "tables"
            tables.mkdir(parents=True)
            pd.DataFrame(
                [
                    {
                        "statistic": "mean", "available": True, "primary_representative": True,
                        "observed_max_c": 42.0, "observed_max_time_local": "2026-02-02T12:03:00+08:00",
                        "observed_max_image_id": "noon", "observed_min_c": 18.0,
                        "observed_min_time_local": "2026-02-02T02:07:00+08:00",
                        "observed_min_image_id": "night", "observed_peak_to_trough_range_c": 24.0,
                    },
                    {
                        "statistic": "absolute_pixel", "available": True, "primary_representative": False,
                        "observed_max_c": 50.0, "observed_max_time_local": "2026-02-02T12:03:00+08:00",
                        "observed_max_image_id": "noon", "observed_min_c": 10.0,
                        "observed_min_time_local": "2026-02-02T02:07:00+08:00",
                        "observed_min_image_id": "night", "observed_peak_to_trough_range_c": 40.0,
                    },
                ]
            ).to_csv(tables / "peak_to_trough_statistics.csv", index=False)
            manifest = root / "temporal_run_manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "status": "complete", "temporal_requested": True,
                        "groups": [{
                            "temporal_group_id": group_id, "location_id": "field", "target_id": "pitch",
                            "submitted_capture_count": 2, "eligible_capture_count": 2,
                            "temporal_series_available": True, "trend_status": "multi_capture_observed_series",
                            "sampling_coverage_status": "partial_day",
                        }],
                    }
                ),
                encoding="utf-8",
            )
            rendered = "\n".join(temporal_user_summary_lines({"temporal_run_manifest": str(manifest)}, None))
            self.assertIn("Observed representative maximum: 42.000 °C", rendered)
            self.assertIn("Observed representative minimum: 18.000 °C", rendered)
            self.assertIn("peak-to-trough difference: 24.000 °C", rendered)
            self.assertIn("Absolute observed pixel max–min difference: 40.000 °C", rendered)

    def test_polygon_subprocess_distinguishes_window_close_from_cancel(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            thermal = root / "thermal.jpg"
            Image.new("RGB", (4, 3), "gray").save(thermal)
            from unittest.mock import patch

            with patch("scripts.workflow.polygon_annotation.subprocess.run") as run:
                run.return_value.returncode = 0
                result = run_polygon_gui_subprocess(
                    request_path=root / "request.json",
                    result_path=root / "missing-result.json",
                    thermal_image_path=thermal,
                    visible_image_path=None,
                    surface_cover_category="grass_low_vegetation",
                    target_name="field",
                    luhk_category="GIC / open space",
                    luhk_code="gic_open_space",
                    luhk_provenance="user_supplied_luhk",
                    reviewer_confidence="medium",
                )
            self.assertFalse(result.accepted)
            self.assertFalse(result.cancelled)


if __name__ == "__main__":
    unittest.main()
