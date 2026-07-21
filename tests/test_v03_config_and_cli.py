from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

from scripts.workflow.canonical_result import write_canonical_result
from scripts.workflow.models import ManualReviewStatus, ProcessingRoute, QAStatus, SourceMethod


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class V03ConfigAndCliTests(unittest.TestCase):
    def test_v03_configs_and_scientific_templates_are_isolated(self) -> None:
        production = json.loads((PROJECT_ROOT / "config" / "workflow_v0_3.json").read_text(encoding="utf-8"))
        acceptance = json.loads((PROJECT_ROOT / "config" / "workflow_v0_3_acceptance.json").read_text(encoding="utf-8"))
        polygon = json.loads((PROJECT_ROOT / "config" / "acceptance" / "v0_3_soccer_polygon_template.json").read_text(encoding="utf-8"))
        ambient = json.loads((PROJECT_ROOT / "config" / "acceptance" / "v0_3_soccer_ambient_template.json").read_text(encoding="utf-8"))
        self.assertEqual(production["schema_version"], "0.2.0")
        self.assertEqual(production["processing_version"], "heat-index-urop-0.3.1")
        self.assertEqual(production["part_e"]["temporal_timezone"], "Asia/Hong_Kong")
        self.assertIn("outputs/runs/v0_3_user_acceptance", acceptance["canonical_output_root"].replace("\\", "/"))
        polygon_entry = next(iter(polygon.values()))
        ambient_entry = next(iter(ambient.values()))
        self.assertEqual(polygon_entry["review_status"], "draft")
        self.assertEqual(polygon_entry["coordinates"], [])
        self.assertIsNone(ambient_entry["ambient_temperature_c"])
        self.assertIn("Never copy", ambient_entry["notes"])

    def test_temporal_cli_accepts_manifests_and_run_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifests = []
            for index, hour in enumerate((9, 11), start=1):
                image_id = f"capture-{index}"
                _, path = write_canonical_result(
                    output_root=root / "canonical", image_id=image_id, group_id=image_id, pair_id=image_id,
                    dataset_id="non_scientific_fixture", visible_path="v", thermal_path="t",
                    temperature=np.arange(12, dtype=np.float32).reshape(3, 4) + 20,
                    labels=np.ones((3, 4), dtype=np.int16), known_mask=np.ones((3, 4), dtype=bool),
                    processing_route=ProcessingRoute.NORMAL_VT, source_method=SourceMethod.VISIBLE_REVIEW,
                    review_status=ManualReviewStatus.ACCEPTED, qa_status=QAStatus.PASS,
                    configuration_hash=image_id, source_file_hashes={"fixture": image_id},
                    surface_cover_names={1: "roof"}, target_id="stable-target", target_name="fixture target",
                    temperature_source="mocked_temperature_matrix",
                    temperature_metadata={
                        "capture_time": f"2026-02-02T{hour:02d}:00:00",
                        "capture_timezone": "Asia/Hong_Kong",
                        "ambient_temperature_c": 20.0,
                        "definition": "synthetic per-pixel surface temperature",
                    },
                    ambient_metadata={
                        "ambient_temperature_c": 20.0,
                        "source": "synthetic ambient fixture",
                        "definition": "synthetic air temperature",
                    },
                )
                manifests.append(path)
            script = PROJECT_ROOT / "scripts" / "run_temporal_analysis.py"
            output = root / "manifest-input"
            command = [
                sys.executable, str(script),
                "--manifest", str(manifests[0]), "--manifest", str(manifests[1]),
                "--output-root", str(output), "--timezone", "Asia/Hong_Kong", "--dry-run",
            ]
            completed = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertIn("planned_dry_run", completed.stdout)
            self.assertTrue((output / "input" / "temporal_canonical_pixels.parquet").is_file())

            run_summary = root / "run_summary.json"
            run_summary.write_text(
                json.dumps(
                    {
                        "groups": [
                            {"image_id": f"capture-{index}", "status": "success", "canonical_manifest_path": str(path)}
                            for index, path in enumerate(manifests, start=1)
                        ]
                    }
                ),
                encoding="utf-8",
            )
            output2 = root / "summary-input"
            completed2 = subprocess.run(
                [
                    sys.executable, str(script), "--run-summary", str(run_summary),
                    "--output-root", str(output2), "--timezone", "Asia/Hong_Kong", "--dry-run",
                ],
                cwd=PROJECT_ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed2.returncode, 0, completed2.stdout + completed2.stderr)
            self.assertTrue((output2 / "input" / "temporal_canonical_pixels.parquet").is_file())


if __name__ == "__main__":
    unittest.main()
