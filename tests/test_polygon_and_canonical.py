from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.workflow.canonical_result import (
    UNKNOWN_LABEL_ID,
    eligible_target_pixels,
    load_manifest,
    validate_label_layers,
    write_canonical_result,
)
from scripts.workflow.models import (
    ManualReviewStatus,
    ProcessingRoute,
    QAStatus,
    SourceMethod,
)
from scripts.workflow.polygon_annotation import labelled_polygon_arrays, rasterize_polygon


class PolygonCanonicalTests(unittest.TestCase):
    def test_polygon_inside_known_outside_unknown(self) -> None:
        labels, known = labelled_polygon_arrays([(1, 1), (5, 1), (5, 4), (1, 4)], (6, 8), 5)
        self.assertGreater(int(known.sum()), 0)
        self.assertLess(int(known.sum()), known.size)
        self.assertTrue(np.all(labels[known] == 5))
        self.assertTrue(np.all(labels[~known] == UNKNOWN_LABEL_ID))

    def test_dynamic_dimensions_and_optional_shadow(self) -> None:
        shape = (5, 7)
        labels, known = labelled_polygon_arrays([(1, 1), (5, 1), (5, 3), (1, 3)], shape, 5)
        temperature = np.arange(shape[0] * shape[1], dtype=np.float32).reshape(shape)
        with tempfile.TemporaryDirectory() as directory:
            manifest, path = write_canonical_result(
                output_root=Path(directory),
                image_id="synthetic_T",
                group_id="g1",
                pair_id="p1",
                dataset_id="d1",
                visible_path="synthetic_V.JPG",
                thermal_path="synthetic_T.JPG",
                temperature=temperature,
                labels=labels,
                known_mask=known,
                processing_route=ProcessingRoute.THERMAL_POLYGON,
                source_method=SourceMethod.THERMAL_POLYGON_USER_ANNOTATION,
                review_status=ManualReviewStatus.ACCEPTED,
                qa_status=QAStatus.PASS,
                configuration_hash="config-hash",
                source_file_hashes={"synthetic_T.JPG": "source-hash"},
                surface_cover_names={5: "grass_low_vegetation"},
                surface_cover_class_id=5,
                surface_cover_category="grass_low_vegetation",
                target_name="field",
                polygon_coordinates=[[1, 1], [5, 1], [5, 3], [1, 3]],
            )
            self.assertEqual((manifest.image_height, manifest.image_width), shape)
            self.assertNotIn("shadow_mask", manifest.artifacts)
            loaded = load_manifest(path)
            self.assertEqual(loaded.known_pixel_count, int(known.sum()))
            pixels = pd.read_parquet(Path(directory) / "synthetic_T" / "pixels.parquet")
            eligible = eligible_target_pixels(pixels)
            self.assertEqual(len(eligible), int(known.sum()))
            self.assertTrue(pixels.loc[~pixels["label_known"], "exclusion_reason"].eq("label_unknown").all())
            self.assertFalse(pixels.loc[~pixels["label_known"], "analysis_eligible"].any())

    def test_cancelled_annotation_cannot_be_successful_canonical_result(self) -> None:
        shape = (4, 4)
        labels, known = labelled_polygon_arrays([(0, 0), (3, 0), (3, 3)], shape, 1)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "accepted annotation"):
                write_canonical_result(
                    output_root=Path(directory), image_id="i", group_id="g", pair_id="p", dataset_id="d",
                    visible_path="v", thermal_path="t", temperature=np.ones(shape), labels=labels, known_mask=known,
                    processing_route=ProcessingRoute.THERMAL_POLYGON,
                    source_method=SourceMethod.THERMAL_POLYGON_USER_ANNOTATION,
                    review_status=ManualReviewStatus.CANCELLED, qa_status=QAStatus.PASS,
                    configuration_hash="x", source_file_hashes={}, surface_cover_class_id=1,
                    surface_cover_category="roof", polygon_coordinates=[[0, 0], [3, 0], [3, 3]],
                )

    def test_unknown_storage_sentinel_is_enforced(self) -> None:
        temperature = np.ones((2, 2), dtype=np.float32)
        known = np.array([[True, False], [False, False]])
        labels = np.array([[1, 0], [-1, -1]], dtype=np.int16)
        with self.assertRaisesRegex(ValueError, "Unknown pixels"):
            validate_label_layers(temperature, labels, known)


if __name__ == "__main__":
    unittest.main()
