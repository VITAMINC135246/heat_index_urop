from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from scripts.workflow.canonical_result import write_canonical_result
from scripts.workflow.models import ManualReviewStatus, ProcessingRoute, QAStatus, SourceMethod
from scripts.workflow.polygon_annotation import labelled_polygon_arrays
from scripts.workflow.result_index import ResultIndex


class ResultIndexTests(unittest.TestCase):
    def test_compatible_cache_hit_and_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            labels, known = labelled_polygon_arrays([(0, 0), (3, 0), (3, 3)], (4, 4), 1)
            hashes = {"thermal": "source-hash"}
            manifest, manifest_path = write_canonical_result(
                output_root=root / "images", image_id="image-1", group_id="g", pair_id="p", dataset_id="d",
                visible_path="v", thermal_path="t", temperature=np.ones((4, 4)), labels=labels, known_mask=known,
                processing_route=ProcessingRoute.THERMAL_POLYGON,
                source_method=SourceMethod.THERMAL_POLYGON_USER_ANNOTATION,
                review_status=ManualReviewStatus.ACCEPTED, qa_status=QAStatus.PASS,
                configuration_hash="config-hash", source_file_hashes=hashes,
                surface_cover_class_id=1, surface_cover_category="roof",
                polygon_coordinates=[[0, 0], [3, 0], [3, 3]],
                luhk_category="GIC / open space", luhk_provenance="user_supplied_luhk",
            )
            index = ResultIndex(root / "index.json")
            index.register(manifest_path, manifest)
            index.save()
            hit = ResultIndex(root / "index.json").check(
                "image-1", source_file_hashes=hashes, configuration_hash_value="config-hash"
            )
            self.assertTrue(hit.compatible)
            mismatch = index.check(
                "image-1", source_file_hashes={"thermal": "changed"}, configuration_hash_value="config-hash"
            )
            self.assertFalse(mismatch.compatible)
            self.assertEqual(mismatch.reason, "source_file_hash_mismatch")


if __name__ == "__main__":
    unittest.main()
