from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd


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

    def test_existing_part_e_row_count_when_local_parquet_is_available(self) -> None:
        path = PROJECT_ROOT / "data" / "processed" / "part_e" / "part_e_pixel_delta_t.parquet"
        if not path.is_file():
            self.skipTest("Local reproducible Part E Parquet is not present.")
        import pyarrow.parquet as pq

        self.assertEqual(pq.ParquetFile(path).metadata.num_rows, 5 * 512 * 640)


if __name__ == "__main__":
    unittest.main()
