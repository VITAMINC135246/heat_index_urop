from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from scripts.workflow.part_c_adapter import prepare_part_c_review


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "run_analysis.py"


class RunAnalysisV02Routes(unittest.TestCase):
    def config(self, root: Path) -> Path:
        path = root / "config.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "0.2.0", "processing_version": "heat-index-urop-0.2",
                    "dataset_root": str(root), "canonical_output_root": str(root / "images"),
                    "result_index": str(root / "index.json"), "run_output_root": str(root / "runs"),
                    "part_b0": {"thresholds": {}},
                    "part_e": {
                        "canonical_parquet": str(root / "part_e.parquet"),
                        "summary_csv": str(root / "part_e_summary.csv"),
                        "dashboard_directory": str(root / "dashboard"), "formal_enabled": False,
                        "write_full_pixel_csv": False,
                    },
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_needs_part_b0_review_cannot_silently_enter_part_c(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            visible = root / "DJI_20260717120000_0001_V.JPG"
            thermal = root / "DJI_20260717120000_0001_T.JPG"
            Image.new("RGB", (40, 30), "gray").save(visible)
            Image.new("RGB", (40, 30), "gray").save(thermal)
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--config", str(self.config(root)), "selected", "--group", str(visible), str(thermal)],
                cwd=PROJECT_ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertIn("awaiting_part_b0_review", completed.stdout)
            self.assertFalse((root / "images" / "DJI_20260717120000_0001" / "manifest.json").exists())

    def test_verified_normal_route_runs_a_to_e_on_cache_miss_then_hits_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_id = "DJI_20260717120000_0002"
            visible = root / f"{image_id}_V.PNG"
            thermal = root / f"{image_id}_T.PNG"
            image = Image.new("RGB", (80, 60), "black")
            draw = ImageDraw.Draw(image)
            draw.rectangle((8, 8, 70, 50), outline="white", width=4)
            draw.ellipse((20, 15, 45, 40), fill="gray")
            image.save(visible)
            image.save(thermal)
            temperature = root / "temperature.npy"
            np.save(temperature, np.linspace(20, 35, 80 * 60, dtype=np.float32).reshape(60, 80))
            ambient = root / "ambient.json"
            ambient.write_text(json.dumps({image_id: {"ambient_temperature_c": 22.0, "source": "synthetic"}}), encoding="utf-8")
            part_b_review = root / "part_b_review.json"
            part_b_review.write_text(
                json.dumps(
                    {
                        image_id: {
                            "scene_correspondence": "accepted",
                            "coverage_class": "thermal_fully_supported_by_visible",
                            "manual_review_status": "accepted",
                            "notes": "synthetic explicit final review",
                        }
                    }
                ),
                encoding="utf-8",
            )
            review_controller = prepare_part_c_review(
                image_id=image_id, pair_id=f"selected::{image_id}", visible_path=visible, thermal_path=thermal,
                accepted_crop=[0, 0, 80, 60], output_directory=root / "review_prep",
                class_mapping={0: "no_data_unreviewed", 1: "roof", 2: "asphalt_road", 3: "concrete_pavement", 4: "vegetation_tree", 5: "grass_low_vegetation", 6: "water", 7: "bare_soil", 8: "other_surface", 9: "unclear_ignore"},
            )
            review_controller.select(review_controller.segment_ids)
            review_controller.assign("roof")
            review_controller.set_review_metadata(reviewer="integration-test", reviewer_confidence="high")
            part_c_review = root / "part_c_review.json"
            review_controller.accept(part_c_review)
            command = [
                sys.executable, str(SCRIPT), "--config", str(self.config(root)),
                "--part-b-review", str(part_b_review), "--part-c-review", f"{image_id}={part_c_review}",
                "--temperature-npy", f"{image_id}={temperature}", "--ambient-json", str(ambient),
                "selected", "--group", str(visible), str(thermal),
            ]
            first = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False, timeout=90)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            manifest_path = root / "images" / image_id / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], "0.2.0")
            self.assertEqual(manifest["processing_route"], "normal_visible_thermal")
            self.assertEqual(manifest["measurement_type"], "full_thermal_pixel")
            self.assertEqual(manifest["surface_cover_provenance"], "visible_review")
            self.assertEqual(manifest["part_b"]["final_alignment_status"], "accepted")
            self.assertTrue((root / "part_e.parquet").is_file())
            self.assertTrue((manifest_path.parent / "extreme_temperature_locations.png").is_file())
            second = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False, timeout=90)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertIn("cache_hit", second.stdout)


if __name__ == "__main__":
    unittest.main()
