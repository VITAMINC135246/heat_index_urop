from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_MASK_HASHES = {
    "DJI_20260107143259_0005": "a705740d6a79e86b1eb91af4bb71212580b5292296f1f5d25870bb17fb1e0e06",
    "DJI_20260107143320_0007": "cb5643443fb5c098e0d510b7852f92b9cfb5205d7ee89b4d786dafa2eea3eeb1",
    "DJI_20260107143328_0008": "31d01ba27f6393aafda5895a92f83d9c63059ce6d03730e4705ddab6b6f59b0f",
    "DJI_20260107143344_0009": "e67e6a5f1b2a1055e4f85c1ba50bdcc8274ec5fd59c6af9f9e3fa95e54593759",
    "DJI_20260107143401_0011": "17f5a62bcbb3dd4f370a633541b793b8ef2b62ffff9dd3289a70533ea193c49c",
}

EXPECTED_TEMPERATURE = {
    "DJI_20260107143259_0005": (-17.5691280365, 45.5172042847, 14.2802686691, 28.7086124420, 11.0),
    "DJI_20260107143320_0007": (-22.2980251312, 47.6762008667, 16.3118457794, 31.5133304596, 10.6),
    "DJI_20260107143328_0008": (-24.2570247650, 47.7721481323, 16.0528450012, 31.9110965729, 10.5),
    "DJI_20260107143344_0009": (-23.7851772308, 48.8896408081, 16.1059436798, 31.7968692780, 9.9),
    "DJI_20260107143401_0011": (-29.1531429291, 40.5692062378, 16.0390987396, 30.4305057526, 9.9),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class PilotNumericBaselineTests(unittest.TestCase):
    def test_reviewed_part_c_mask_bytes_are_frozen(self) -> None:
        for image_id, expected in EXPECTED_MASK_HASHES.items():
            path = (
                PROJECT_ROOT
                / "outputs"
                / "part_c"
                / "masks"
                / image_id
                / f"{image_id}_physical_surface_cover_class_id_thermal_grid.npy"
            )
            self.assertTrue(path.is_file(), path)
            self.assertEqual(sha256(path), expected)

    def test_part_d_temperature_numeric_baseline(self) -> None:
        summary = pd.read_csv(
            PROJECT_ROOT
            / "outputs"
            / "part_d"
            / "summaries"
            / "part_d_tat3_parameter_temperature_extraction_summary.csv",
            keep_default_na=False,
        ).set_index("image_id")
        self.assertEqual(set(summary.index), set(EXPECTED_TEMPERATURE))
        for image_id, expected in EXPECTED_TEMPERATURE.items():
            matrix = np.load(PROJECT_ROOT / str(summary.loc[image_id, "npy_path"]))
            actual = (
                float(np.nanmin(matrix)),
                float(np.nanmax(matrix)),
                float(np.nanmean(matrix)),
                float(np.nanquantile(matrix, 0.99)),
                float(summary.loc[image_id, "ambient_temperature_c"]),
            )
            self.assertEqual(matrix.shape, (512, 640))
            np.testing.assert_allclose(actual, expected, rtol=0.0, atol=2e-6)
            self.assertEqual(matrix.size, 512 * 640)


if __name__ == "__main__":
    unittest.main()
