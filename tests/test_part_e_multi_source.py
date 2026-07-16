from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.workflow.canonical_result import UNKNOWN_LABEL_ID, write_canonical_result
from scripts.workflow.models import ManualReviewStatus, ProcessingRoute, QAStatus, SourceMethod
from scripts.workflow.part_e_adapter import aggregate_canonical_results
from scripts.workflow.polygon_annotation import labelled_polygon_arrays


class PartEMultiSourceTests(unittest.TestCase):
    def make_result(
        self,
        root: Path,
        image_id: str,
        route: ProcessingRoute,
        method: SourceMethod,
        labels: np.ndarray,
        known: np.ndarray,
        *,
        category: str | None = None,
        class_id: int | None = None,
    ) -> Path:
        _, path = write_canonical_result(
            output_root=root / "images", image_id=image_id, group_id=f"g-{image_id}", pair_id=f"p-{image_id}",
            dataset_id="d", visible_path="v", thermal_path="t",
            temperature=np.arange(labels.size, dtype=np.float32).reshape(labels.shape),
            labels=labels, known_mask=known, processing_route=route, source_method=method,
            review_status=ManualReviewStatus.ACCEPTED, qa_status=QAStatus.PASS,
            configuration_hash="c", source_file_hashes={"t": image_id}, surface_cover_names={1: "roof", 5: "grass"},
            surface_cover_class_id=class_id, surface_cover_category=category,
            polygon_coordinates=[[0, 0], [2, 0], [2, 2]] if route == ProcessingRoute.THERMAL_POLYGON else [],
            temperature_metadata={"ambient_temperature_c": 20.0},
        )
        return path

    def test_normal_and_polygon_results_keep_separate_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            normal_labels = np.array([[1, 1, UNKNOWN_LABEL_ID], [1, 1, UNKNOWN_LABEL_ID]], dtype=np.int16)
            normal_known = normal_labels != UNKNOWN_LABEL_ID
            normal = self.make_result(
                root, "normal", ProcessingRoute.NORMAL_VT, SourceMethod.VISIBLE_REVIEW,
                normal_labels, normal_known,
            )
            polygon_labels, polygon_known = labelled_polygon_arrays([(0, 0), (2, 0), (2, 1)], (2, 3), 5)
            polygon = self.make_result(
                root, "polygon", ProcessingRoute.THERMAL_POLYGON,
                SourceMethod.THERMAL_POLYGON_USER_ANNOTATION, polygon_labels, polygon_known,
                category="grass", class_id=5,
            )
            output = root / "part_e.parquet"
            summary = aggregate_canonical_results(
                [normal, polygon], output_parquet=output, summary_csv=root / "summary.csv"
            )
            self.assertEqual(set(summary["source_method"]), {"visible_review", "thermal_polygon_user_annotation"})
            combined = pd.read_parquet(output)
            self.assertEqual(set(combined["source_method"]), {"visible_review", "thermal_polygon_user_annotation"})
            polygon_rows = combined.loc[combined["source_method"].eq("thermal_polygon_user_annotation")]
            self.assertFalse(polygon_rows.loc[~polygon_rows["label_known"], "surface_cover_valid"].any())
            self.assertTrue(polygon_rows.loc[~polygon_rows["label_known"], "exclusion_reason"].eq("label_unknown").all())


if __name__ == "__main__":
    unittest.main()
