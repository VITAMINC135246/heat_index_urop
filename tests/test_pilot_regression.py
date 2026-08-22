from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd
import pytest

from scripts.workflow.models import SourceMethod
from scripts.workflow.pilot_adapter import adapt_pilot_image


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class PilotRegressionTests(unittest.TestCase):
    def test_five_pilot_artifact_contracts_remain_compatible(self) -> None:
        pairs = pd.read_excel(PROJECT_ROOT / "data" / "metadata" / "part_b_pilot_pairs.xlsx")
        masks = pd.read_excel(PROJECT_ROOT / "outputs" / "part_c" / "summaries" / "part_c_final_mask_manifest.xlsx")
        temperatures = pd.read_csv(
            PROJECT_ROOT / "outputs" / "part_d" / "summaries" / "part_d_tat3_parameter_temperature_extraction_summary.csv"
        )
        self.assertEqual(pairs["image_id"].nunique(), 5)
        self.assertEqual(masks["image_id"].nunique(), 5)
        self.assertTrue(masks["usable_for_part_d"].astype(str).str.casefold().eq("yes").all())
        self.assertEqual(temperatures["image_id"].nunique(), 5)
        self.assertTrue(temperatures["extraction_status"].eq("success").all())
        self.assertTrue(temperatures["temperature_shape"].eq("512x640").all())

    @pytest.mark.local_integration
    def test_existing_part_e_row_count_when_local_parquet_is_available(self) -> None:
        path = PROJECT_ROOT / "data" / "processed" / "part_e" / "part_e_pixel_delta_t.parquet"
        if not path.is_file():
            self.skipTest("Local reproducible Part E Parquet is not present.")
        import pyarrow.parquet as pq

        self.assertEqual(pq.ParquetFile(path).metadata.num_rows, 5 * 512 * 640)

    @pytest.mark.local_integration
    def test_normal_part_c_pilot_adapter_builds_versioned_manifest(self) -> None:
        import tempfile

        image_id = pd.read_excel(PROJECT_ROOT / "data" / "metadata" / "part_b_pilot_pairs.xlsx").iloc[0]["image_id"]
        with tempfile.TemporaryDirectory() as directory:
            manifest, path = adapt_pilot_image(
                PROJECT_ROOT, str(image_id), output_root=Path(directory), write_pixels_parquet=False
            )
            self.assertTrue(path.is_file())
            self.assertEqual(manifest.source_method, SourceMethod.VISIBLE_REVIEW)
            self.assertEqual((manifest.image_height, manifest.image_width), (512, 640))
            self.assertEqual(manifest.known_pixel_count + manifest.unknown_pixel_count, 512 * 640)


if __name__ == "__main__":
    unittest.main()
