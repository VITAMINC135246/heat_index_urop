from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from PIL import Image

from scripts.run_user_workflow import build_command
from scripts.workflow.polygon_annotation import run_polygon_gui_subprocess


class UserWorkflowTests(unittest.TestCase):
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
            )
            command = build_command(args)
            self.assertEqual(command.count("--group"), 6)
            self.assertIn("--tat3-report", command)
            self.assertIn("--polygon-image-id", command)
            self.assertIn("--require-all-success", command)
            self.assertNotIn("--polygon-json", command)
            self.assertNotIn("--ambient-json", command)
            self.assertNotIn("--part-b0-review", command)

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
