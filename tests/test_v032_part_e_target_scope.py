from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


PART_E_DIR = Path(__file__).resolve().parents[1] / "scripts" / "part_e"
if str(PART_E_DIR) not in sys.path:
    sys.path.insert(0, str(PART_E_DIR))

from part_e_pixel_common import (  # noqa: E402
    formal_target_eligible_mask,
    family_eligible_and_group,
    gic_open_space_mask,
    grouped_summary,
    spatially_thinned_sample,
)


class PartETargetScopeTests(unittest.TestCase):
    def test_gic_filter_accepts_canonical_string_and_legacy_numeric_codes(self) -> None:
        frame = pd.DataFrame(
            {
                "luhk_class_code": ["gic_open_space", "31", "residential", "not-a-number"],
                "luhk_class_name": ["GIC / open space", "Government land", "Residential", "Unknown"],
            }
        )
        self.assertEqual(gic_open_space_mask(frame).tolist(), [True, True, False, False])

    def test_formal_groups_do_not_pool_incompatible_ambient_definitions(self) -> None:
        frame = self._image_frame("same-image", [1.0, 2.0], [True, True])
        frame["ambient_source"] = "station-a"
        frame["ambient_definition"] = ["screen-level air temperature", "exported camera parameter"]
        frame["ambient_unit"] = "degC"
        frame["ambient_data_qa_status"] = "pass"
        frame["ambient_provenance"] = "fixture"
        eligible, groups = family_eligible_and_group(frame, "surface_cover")
        self.assertTrue(eligible.all())
        self.assertEqual(groups[eligible].nunique(), 2)

    @staticmethod
    def _image_frame(
        image_id: str,
        delta_t: list[float],
        target_mask: list[bool],
    ) -> pd.DataFrame:
        count = len(delta_t)
        rows = np.repeat(np.arange(2), 3)[:count]
        cols = np.tile(np.arange(3), 2)[:count]
        return pd.DataFrame(
            {
                "pixel_uid": [f"{image_id}-{row}-{col}" for row, col in zip(rows, cols)],
                "image_id": image_id,
                "thermal_row": rows,
                "thermal_col": cols,
                "delta_t_c": delta_t,
                "pixel_accepted": True,
                "analysis_eligible": target_mask,
                "target_mask": target_mask,
                # Leave these valid outside the polygon so the test proves that
                # target scope, rather than an incidental class mask, excludes it.
                "surface_cover_valid": True,
                "surface_cover_class": "grass",
                "luhk_label_valid": True,
                "luhk_class_code": "gic_open_space",
                "luhk_class_name": "GIC / open space",
                "shadow_valid": True,
                "shadow_flag": 0,
            }
        )

    @staticmethod
    def _sampling_config() -> dict[str, object]:
        return {
            "sampling": {
                "spatial_tile_size_px": 1,
                "max_pixels_per_group": 100,
                "max_pixels_per_image_per_group": 100,
                "method": "synthetic_target_scope_test",
            }
        }

    def test_polygon_outside_pixels_do_not_enter_overall_or_image_statistics(self) -> None:
        normal = self._image_frame(
            "normal", [1.0, 2.0, 3.0, 4.0, 5.0, 6.0], [True] * 6
        )
        polygon = self._image_frame(
            "polygon", [10.0, 20.0, 100.0, 100.0, 100.0, 100.0],
            [True, True, False, False, False, False],
        )
        frame = pd.concat([normal, polygon], ignore_index=True)

        formal_mask = formal_target_eligible_mask(frame)
        self.assertEqual(int(formal_mask.sum()), 8)

        sample, manifest = spatially_thinned_sample(
            frame, "image_comparison", self._sampling_config(), seed=42
        )
        eligible_by_image = manifest.groupby("image_id")["eligible_pixel_count"].sum().to_dict()
        sampled_by_image = sample.groupby("image_id").size().to_dict()
        self.assertEqual(eligible_by_image, {"normal": 6, "polygon": 2})
        self.assertEqual(sampled_by_image, {"normal": 6, "polygon": 2})
        self.assertTrue(sample.loc[sample["image_id"].eq("polygon"), "target_mask"].all())

        summary = grouped_summary(frame, sample, ["image_id"], formal_mask).set_index("image_id")
        self.assertEqual(int(summary.loc["normal", "n_pixels_full"]), 6)
        self.assertEqual(int(summary.loc["polygon", "n_pixels_full"]), 2)
        self.assertAlmostEqual(float(summary.loc["polygon", "mean_full"]), 15.0)
        self.assertAlmostEqual(float(summary.loc["polygon", "max_full"]), 20.0)

        for family in (
            "luhk",
            "surface_cover",
            "luhk_surface_cover",
            "surface_cover_shadow",
        ):
            with self.subTest(family=family):
                _, family_manifest = spatially_thinned_sample(
                    frame, family, self._sampling_config(), seed=42
                )
                polygon_count = family_manifest.loc[
                    family_manifest["image_id"].eq("polygon"), "eligible_pixel_count"
                ].sum()
                self.assertEqual(int(polygon_count), 2)

    def test_normal_result_without_legacy_target_mask_keeps_full_image_behavior(self) -> None:
        normal = self._image_frame(
            "normal", [1.0, 2.0, 3.0, 4.0, 5.0, 6.0], [True] * 6
        ).drop(columns="target_mask")

        formal_mask = formal_target_eligible_mask(normal)
        sample, manifest = spatially_thinned_sample(
            normal, "image_comparison", self._sampling_config(), seed=42
        )
        self.assertEqual(int(formal_mask.sum()), 6)
        self.assertEqual(int(manifest["eligible_pixel_count"].sum()), 6)
        self.assertEqual(len(sample), 6)


if __name__ == "__main__":
    unittest.main()
