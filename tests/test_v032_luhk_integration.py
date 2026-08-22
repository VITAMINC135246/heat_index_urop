from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from PIL import Image

from scripts.workflow.part_c_review_gui import ReviewState, SuperpixelReviewController, SuperpixelReviewGUI
from scripts.workflow.pilot_adapter import adapt_pilot_image
from scripts.workflow.luhk_context import (
    LUHK_LOOKUP_VERSION,
    LUHK_SPATIAL_UNCERTAINTY,
    build_native_luhk_result,
    load_native_luhk_result,
)
from scripts.workflow.models import LUHKProvenance
from scripts.workflow.result_index import ResultIndex


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PART_E_DIR = PROJECT_ROOT / "scripts" / "part_e"
if str(PART_E_DIR) not in sys.path:
    sys.path.insert(0, str(PART_E_DIR))

from part_e_pixel_common import build_luhk_pixel_labels


EXPECTED_RAW_COUNTS = {
    "DJI_20260107143259_0005": {31: 222_592, 51: 200, 71: 66_827, 72: 31_408, 73: 6_653},
    "DJI_20260107143320_0007": {31: 319_447, 71: 7_633, 73: 600},
    "DJI_20260107143328_0008": {31: 326_558, 71: 1_122},
    "DJI_20260107143344_0009": {31: 327_680},
    "DJI_20260107143401_0011": {31: 327_188, 71: 492},
}

PILOT_CACHE_DEPENDENCIES = {
    "normal_luhk_lookup_version": LUHK_LOOKUP_VERSION,
    "normal_luhk_input:pilot_luhk_aligned_10m_grid_cells.xlsx": "grid-hash-v1",
    "normal_luhk_input:image_footprints.xlsx": "footprint-hash-v1",
    "normal_luhk_input:LUMHK_RasterGrid_2024.tif": "raster-hash-v1",
}
PILOT_SOURCE_HASHES = {
    "pilot-visible": "visible-hash-v1",
    "pilot-thermal": "thermal-hash-v1",
    "official-luhk-grid": "grid-hash-v1",
}


class V032NativeLUHKIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.grid = pd.read_excel(
            PROJECT_ROOT / "data" / "processed" / "grids" / "pilot_luhk_aligned_10m_grid_cells.xlsx"
        )
        cls.footprints = pd.read_excel(
            PROJECT_ROOT / "data" / "processed" / "footprints" / "image_footprints.xlsx"
        )
        cls.pairs = pd.read_excel(PROJECT_ROOT / "data" / "metadata" / "part_b_pilot_pairs.xlsx")

    def result_for(self, image_id: str):
        pair_id = str(self.pairs.loc[self.pairs["image_id"].astype(str).eq(image_id), "pair_id"].iloc[0])
        return build_native_luhk_result(
            image_id=image_id,
            pair_id=pair_id,
            shape=(512, 640),
            grid=self.grid,
            footprints=self.footprints,
            source_paths={"fixture": "preserved_official_mapping"},
        )

    def test_all_five_pilots_have_complete_native_grid_official_luhk(self) -> None:
        for image_id, expected_counts in EXPECTED_RAW_COUNTS.items():
            with self.subTest(image_id=image_id):
                result = self.result_for(image_id)
                self.assertTrue(result.available, result.unavailable_reason)
                self.assertEqual(result.status, "available")
                self.assertEqual(result.provenance, LUHKProvenance.OFFICIAL_LOOKUP)
                self.assertEqual(result.labels.shape, (512, 640))
                self.assertEqual(result.known_mask.shape, (512, 640))
                self.assertEqual(result.known_mask.dtype, np.bool_)
                self.assertEqual(result.known_pixel_count, 327_680)
                self.assertTrue(result.known_mask.all())
                values, counts = np.unique(result.raw_codes[result.known_mask], return_counts=True)
                self.assertEqual(dict(zip(values.tolist(), counts.tolist())), expected_counts)
                self.assertEqual(result.metadata["lookup_version"], LUHK_LOOKUP_VERSION)
                self.assertEqual(result.spatial_uncertainty, LUHK_SPATIAL_UNCERTAINTY)

    def test_one_native_image_preserves_multiple_official_categories(self) -> None:
        result = self.result_for("DJI_20260107143259_0005")
        self.assertEqual(
            set(np.unique(result.labels[result.known_mask])),
            {
                "gic_open_space",
                "other_urban_built_up",
                "woodland_shrubland_grassland_wetland",
            },
        )
        self.assertEqual(
            set(np.unique(result.category_names[result.known_mask])),
            {
                "GIC / open space",
                "Other urban / built-up land",
                "Woodland / shrubland / grassland / wetland",
            },
        )
        self.assertGreater(len(np.unique(result.cell_ids[result.known_mask])), 1)

    def test_missing_geospatial_context_is_explicitly_unavailable(self) -> None:
        result = build_native_luhk_result(
            image_id="future_normal_image",
            pair_id="pair-not-present",
            shape=(17, 23),
            grid=self.grid,
            footprints=self.footprints,
        )
        self.assertFalse(result.available)
        self.assertEqual(result.status, "unavailable")
        self.assertEqual(result.provenance, LUHKProvenance.UNKNOWN)
        self.assertEqual(result.unavailable_reason, "thermal_luhk_cells_missing")
        self.assertEqual(result.known_mask.shape, (17, 23))
        self.assertFalse(result.known_mask.any())
        self.assertTrue(np.all(result.labels == ""))
        self.assertTrue(np.all(result.raw_codes == -1))

    def test_unique_image_id_safely_resolves_a_stale_pair_identifier(self) -> None:
        image_id = "DJI_20260107143320_0007"
        expected_pair = str(self.pairs.loc[self.pairs["image_id"].astype(str).eq(image_id), "pair_id"].iloc[0])
        result = build_native_luhk_result(
            image_id=image_id,
            pair_id="stale-or-renamed-pair-id",
            shape=(512, 640),
            grid=self.grid,
            footprints=self.footprints,
        )
        self.assertTrue(result.available, result.unavailable_reason)
        self.assertEqual(result.pair_id, expected_pair)
        self.assertEqual(result.metadata["requested_pair_id"], "stale-or-renamed-pair-id")
        self.assertEqual(result.metadata["resolved_pair_id"], expected_pair)
        self.assertEqual(result.metadata["pair_resolution"], "unique_image_id")

    def test_project_loader_records_official_sources_and_uncertainty(self) -> None:
        image_id = "DJI_20260107143344_0009"
        pair_id = str(self.pairs.loc[self.pairs["image_id"].astype(str).eq(image_id), "pair_id"].iloc[0])
        result = load_native_luhk_result(
            PROJECT_ROOT,
            image_id=image_id,
            pair_id=pair_id,
            shape=(512, 640),
        )
        self.assertTrue(result.available)
        self.assertTrue({"luhk_cell_mapping", "thermal_footprints"}.issubset(result.source_paths))
        if (PROJECT_ROOT / "data" / "luhk" / "LUMHK_RasterGrid_2024.tif").is_file():
            self.assertIn("official_luhk_raster", result.source_paths)
        self.assertEqual(result.metadata["thermal_footprint_model"], "metadata_derived_north_up_rectangle")
        self.assertIn("yaw is not applied", result.spatial_uncertainty)

    def test_legacy_part_e_helper_delegates_without_numeric_change(self) -> None:
        image_id = "DJI_20260107143259_0005"
        record = self.pairs.loc[self.pairs["image_id"].astype(str).eq(image_id)].iloc[0]
        legacy = build_luhk_pixel_labels(
            record,
            {"grid": self.grid, "footprints": self.footprints},
            (512, 640),
        )
        self.assertEqual(set(legacy), {
            "cell_index", "mapped", "cell_id", "class_code", "class_name",
            "luhk_row", "luhk_col", "origin_x", "origin_y",
        })
        self.assertTrue(np.asarray(legacy["mapped"], dtype=bool).all())
        values, counts = np.unique(np.asarray(legacy["class_code"]), return_counts=True)
        self.assertEqual(dict(zip(values.tolist(), counts.tolist())), EXPECTED_RAW_COUNTS[image_id])
        self.assertEqual(float(legacy["origin_x"]), 800_000.0)
        self.assertEqual(float(legacy["origin_y"]), 848_000.0)

    def test_part_c_luhk_reference_has_no_annotation_entry_point(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            import matplotlib.pyplot as plt

            plt.switch_backend("Agg")
            root = Path(directory)
            visible = root / "visible.png"
            thermal = root / "thermal.png"
            reference = root / "official_luhk_read_only_context.png"
            Image.new("RGB", (3, 2), "green").save(visible)
            Image.new("RGB", (3, 2), "gray").save(thermal)
            Image.new("RGB", (3, 2), "blue").save(reference)
            metadata = {
                "status": "available",
                "provenance": "official_luhk_lookup",
                "spatial_uncertainty": LUHK_SPATIAL_UNCERTAINTY,
            }
            controller = SuperpixelReviewController(
                image_id="read-only-luhk",
                segment_labels=np.array([[1, 1, 2], [1, 2, 2]], dtype=np.int32),
                class_mapping={0: "no_data_unreviewed", 1: "roof", 5: "grass_low_vegetation", 9: "unclear_ignore"},
                suggestions={1: "roof", 2: "grass_low_vegetation"},
                visible_roi_path=visible.as_posix(),
                thermal_path=thermal.as_posix(),
                luhk_reference_path=reference.as_posix(),
                luhk_metadata=metadata,
            )
            controller.select(1)
            with self.assertRaisesRegex(ValueError, "surface-cover category"):
                controller.assign("gic_open_space")
            gui = SuperpixelReviewGUI(controller, root / "review.json")
            with (
                patch("scripts.workflow.part_c_review_gui.interactive_pyplot", return_value=plt),
                patch.object(plt, "show"),
            ):
                self.assertEqual(gui.run(), "draft")
            radio_labels = [label.get_text() for label in gui._widgets[0].labels]
            button_labels = {
                widget.label.get_text()
                for widget in gui._widgets
                if hasattr(widget, "label") and hasattr(widget.label, "get_text")
            }
            self.assertNotIn("gic_open_space", radio_labels)
            self.assertNotIn("GIC / open space", radio_labels)
            self.assertFalse(any("luhk" in label.casefold() for label in button_labels))
            self.assertFalse(any("luhk" in name.casefold() for name in ReviewState.__dataclass_fields__))
            payload = pd.read_json(root / "review.json", typ="series")
            self.assertEqual(payload["luhk_metadata"], metadata)
            self.assertEqual(payload["luhk_reference_path"], reference.as_posix())
            plt.close("all")


@pytest.mark.local_integration
class V032PilotLUHKWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.TemporaryDirectory()
        cls.output_root = Path(cls._temporary.name) / "canonical"
        cls.image_id = "DJI_20260107143259_0005"
        cls.manifest, cls.manifest_path = adapt_pilot_image(
            PROJECT_ROOT,
            cls.image_id,
            output_root=cls.output_root,
            write_pixels_parquet=True,
            configuration_hash_value="v032-luhk-wiring",
            source_file_hashes_value=PILOT_SOURCE_HASHES,
            dependency_fingerprints_value=PILOT_CACHE_DEPENDENCIES,
            part_a={
                "capture_datetime": "2026-01-07T14:32:59+08:00",
                "capture_time_local": "2026-01-07T14:32:59+08:00",
                "capture_timezone": "Asia/Hong_Kong",
                "capture_time_source": "test_preserved_part_a",
                "capture_time_valid": True,
            },
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary.cleanup()

    def test_pilot_canonical_manifest_and_pixels_preserve_official_luhk(self) -> None:
        manifest = self.manifest
        self.assertEqual(manifest.luhk_provenance, "official_luhk_lookup")
        self.assertEqual(manifest.luhk_known_pixel_count, 327_680)
        self.assertEqual(manifest.luhk_unknown_pixel_count, 0)
        self.assertEqual(manifest.luhk_metadata["status"], "available")
        self.assertEqual(manifest.luhk_metadata["lookup_version"], LUHK_LOOKUP_VERSION)
        self.assertEqual(manifest.luhk_metadata["known_pixel_count"], 327_680)
        self.assertIn("north-up", manifest.luhk_metadata["spatial_uncertainty"])
        self.assertTrue({"luhk_labels", "luhk_known_mask", "pixels"}.issubset(manifest.artifacts))

        directory = self.manifest_path.parent
        labels = np.load(directory / manifest.artifacts["luhk_labels"].path, mmap_mode="r", allow_pickle=False)
        known = np.load(directory / manifest.artifacts["luhk_known_mask"].path, mmap_mode="r", allow_pickle=False)
        self.assertEqual(labels.shape, (512, 640))
        self.assertEqual(known.shape, (512, 640))
        self.assertTrue(known.all())
        self.assertEqual(
            set(np.unique(labels[known])),
            {"gic_open_space", "other_urban_built_up", "woodland_shrubland_grassland_wetland"},
        )

        pixels = pd.read_parquet(
            directory / manifest.artifacts["pixels"].path,
            columns=[
                "luhk_class_code", "luhk_class_name", "luhk_cell_id", "luhk_raw_code",
                "luhk_label_valid", "luhk_provenance",
            ],
        )
        self.assertEqual(len(pixels), 327_680)
        self.assertTrue(pixels["luhk_label_valid"].astype(bool).all())
        self.assertEqual(set(pixels["luhk_provenance"]), {"official_luhk_lookup"})
        self.assertTrue(pixels["luhk_cell_id"].astype(str).str.startswith("LUHK_r").all())
        raw_counts = pixels["luhk_raw_code"].value_counts().sort_index().to_dict()
        self.assertEqual(raw_counts, EXPECTED_RAW_COUNTS[self.image_id])
        broad_counts = pixels["luhk_class_code"].value_counts().to_dict()
        self.assertEqual(broad_counts["gic_open_space"], 222_592)
        self.assertEqual(broad_counts["other_urban_built_up"], 200)
        self.assertEqual(broad_counts["woodland_shrubland_grassland_wetland"], 104_888)

    def test_luhk_source_or_dependency_change_invalidates_cache(self) -> None:
        index = ResultIndex(Path(self._temporary.name) / "result_index.json")
        index.register(self.manifest_path, self.manifest)
        compatible = index.check(
            self.image_id,
            source_file_hashes=PILOT_SOURCE_HASHES,
            configuration_hash_value="v032-luhk-wiring",
            dependency_fingerprints=PILOT_CACHE_DEPENDENCIES,
        )
        self.assertTrue(compatible.compatible, compatible.reason)
        for key in PILOT_CACHE_DEPENDENCIES:
            with self.subTest(dependency=key):
                changed = dict(PILOT_CACHE_DEPENDENCIES)
                changed[key] += "-changed"
                check = index.check(
                    self.image_id,
                    source_file_hashes=PILOT_SOURCE_HASHES,
                    configuration_hash_value="v032-luhk-wiring",
                    dependency_fingerprints=changed,
                )
                self.assertFalse(check.compatible)
                self.assertEqual(check.reason, "dependency_fingerprint_mismatch")
        changed_sources = dict(PILOT_SOURCE_HASHES)
        changed_sources["official-luhk-grid"] = "grid-hash-v2"
        check = index.check(
            self.image_id,
            source_file_hashes=changed_sources,
            configuration_hash_value="v032-luhk-wiring",
            dependency_fingerprints=PILOT_CACHE_DEPENDENCIES,
        )
        self.assertFalse(check.compatible)
        self.assertEqual(check.reason, "source_file_hash_mismatch")


if __name__ == "__main__":
    unittest.main()
