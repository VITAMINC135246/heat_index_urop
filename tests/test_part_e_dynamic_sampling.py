from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


PART_E_DIR = Path(__file__).resolve().parents[1] / "scripts" / "part_e"
if str(PART_E_DIR) not in sys.path:
    sys.path.insert(0, str(PART_E_DIR))

from part_e_pixel_common import spatially_thinned_sample


class DynamicSamplingTests(unittest.TestCase):
    def image_frame(self, image_id: str, shape: tuple[int, int], source: str) -> pd.DataFrame:
        height, width = shape
        rows = np.repeat(np.arange(height), width)
        cols = np.tile(np.arange(width), height)
        count = height * width
        return pd.DataFrame(
            {
                "pixel_uid": [f"{image_id}-{row}-{col}" for row, col in zip(rows, cols)],
                "image_id": image_id,
                "thermal_row": rows,
                "thermal_col": cols,
                "pixel_accepted": True,
                "surface_cover_valid": True,
                "surface_cover_class": "grass",
                "analysis_eligible": True,
                "source_method": source,
                "luhk_label_valid": False,
                "luhk_class_code": -1,
                "luhk_class_name": "",
                "shadow_valid": False,
                "shadow_flag": pd.array([pd.NA] * count, dtype="Int8"),
            }
        )

    def test_variable_native_shapes_are_sampled_deterministically(self) -> None:
        frame = pd.concat(
            [
                self.image_frame("small", (5, 7), "thermal_polygon_user_annotation"),
                self.image_frame("wide", (3, 11), "visible_review"),
            ],
            ignore_index=True,
        )
        config = {
            "sampling": {
                "spatial_tile_size_px": 2,
                "max_pixels_per_group": 100,
                "max_pixels_per_image_per_group": 100,
                "method": "test",
            }
        }
        first, manifest = spatially_thinned_sample(frame, "surface_cover", config, 42)
        second, _ = spatially_thinned_sample(frame, "surface_cover", config, 42)
        self.assertEqual(first["pixel_uid"].tolist(), second["pixel_uid"].tolist())
        self.assertEqual(set(manifest["image_id"]), {"small", "wide"})
        self.assertTrue(first["group_name"].str.contains("visible_review|thermal_polygon_user_annotation").all())


if __name__ == "__main__":
    unittest.main()
