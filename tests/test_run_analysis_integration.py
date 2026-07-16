from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "run_analysis.py"


class RunAnalysisIntegrationTests(unittest.TestCase):
    def test_unreviewed_vt_uses_polygon_then_cache_and_part_e(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            visible = root / "DJI_20260717120000_0001_V.JPG"
            thermal = root / "DJI_20260717120000_0001_T.JPG"
            Image.new("RGB", (7, 5), "green").save(visible)
            Image.new("RGB", (7, 5), "gray").save(thermal)
            image_id = "DJI_20260717120000_0001"
            matrix = root / "temperature.npy"
            np.save(matrix, np.arange(35, dtype=np.float32).reshape(5, 7))
            polygon = root / "polygon.json"
            polygon.write_text(
                json.dumps({image_id: {"review_status": "accepted", "coordinates": [[1, 1], [5, 1], [5, 3], [1, 3]]}}),
                encoding="utf-8",
            )
            config = root / "config.json"
            config.write_text(
                json.dumps(
                    {
                        "dataset_root": str(root),
                        "canonical_output_root": str(root / "images"),
                        "result_index": str(root / "index.json"),
                        "run_output_root": str(root / "runs"),
                        "part_e": {
                            "canonical_parquet": str(root / "part_e.parquet"),
                            "summary_csv": str(root / "part_e_summary.csv"),
                            "write_full_pixel_csv": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            command = [
                sys.executable, str(SCRIPT), "--config", str(config), "--polygon-json", str(polygon),
                "--surface-cover", "grass_low_vegetation", "--target-name", "synthetic field",
                "--temperature-npy", f"{image_id}={matrix}", "selected", "--group", str(visible), str(thermal),
            ]
            first = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            manifest = json.loads((root / "images" / image_id / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["processing_route"], "thermal_polygon")
            self.assertGreater(manifest["known_pixel_count"], 0)
            self.assertGreater(manifest["unknown_pixel_count"], 0)
            part_e = pd.read_parquet(root / "part_e.parquet")
            outside = part_e.loc[~part_e["label_known"]]
            self.assertFalse(outside["analysis_eligible"].any())
            second = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertIn("cache_hit", second.stdout)


if __name__ == "__main__":
    unittest.main()
