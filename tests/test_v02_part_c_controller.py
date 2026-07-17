from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from scripts.workflow.part_c_adapter import load_reviewed_label_override
from scripts.workflow.part_c_review_gui import SuperpixelReviewController
from scripts.workflow.result_index import sha256_file


class PartCControllerTests(unittest.TestCase):
    def controller(self) -> SuperpixelReviewController:
        return SuperpixelReviewController(
            image_id="image-1",
            segment_labels=np.array([[1, 1, 2], [3, 3, 2]], dtype=np.int32),
            class_mapping={0: "no_data_unreviewed", 1: "roof", 5: "grass_low_vegetation", 9: "unclear_ignore"},
            suggestions={1: "roof", 2: "grass_low_vegetation", 3: "roof"},
        )

    def test_multi_assignment_unknown_shadow_undo_redo_and_masks(self) -> None:
        controller = self.controller()
        self.assertEqual(controller.unreviewed_segments, {1, 2, 3})  # suggestions are not reviewed labels
        controller.select([1, 2])
        controller.assign("roof")
        controller.set_shadow(True)
        controller.select(3)
        controller.mark_unknown()
        self.assertFalse(controller.validate_for_acceptance())
        self.assertTrue(controller.undo())
        self.assertIn(3, controller.unreviewed_segments)
        self.assertTrue(controller.redo())
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "review.json"
            controller.set_review_metadata(notes="audited", reviewer="tester", reviewer_confidence="high")
            controller.accept(artifact)
            resumed = SuperpixelReviewController.resume(
                artifact, segment_labels=controller.segment_labels, expected_image_id="image-1"
            )
            labels, known, shadow = resumed.generate_masks()
            self.assertTrue(np.all(labels[known] == 1))
            self.assertTrue(np.all(labels[~known] == -1))
            self.assertTrue(shadow[controller.segment_labels == 1].all())
            self.assertTrue(shadow[controller.segment_labels == 2].all())
            self.assertFalse(shadow[controller.segment_labels == 3].any())

    def test_draft_resume_cancel_and_bare_override_rejection(self) -> None:
        controller = self.controller()
        controller.select(1)
        controller.assign("roof")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            draft = root / "draft.json"
            controller.save_draft(draft)
            resumed = SuperpixelReviewController.resume(draft, segment_labels=controller.segment_labels)
            self.assertEqual(resumed.state.labels, {1: "roof"})
            resumed.cancel(draft)
            self.assertEqual(json.loads(draft.read_text(encoding="utf-8"))["review_status"], "cancelled")
            labels = root / "labels.npy"
            np.save(labels, np.ones((2, 3), dtype=np.int16))
            with self.assertRaisesRegex(ValueError, "companion review manifest"):
                load_reviewed_label_override(
                    labels_path=labels, manifest_path=root / "missing.json", image_id="image-1", expected_shape=(2, 3)
                )
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "image_id": "image-1", "dimensions": [2, 3], "class_mapping": {"1": "roof"},
                        "review_status": "accepted", "reviewer": "tester", "artifact_sha256": sha256_file(labels),
                    }
                ),
                encoding="utf-8",
            )
            loaded, known, payload = load_reviewed_label_override(
                labels_path=labels, manifest_path=manifest, image_id="image-1", expected_shape=(2, 3)
            )
            self.assertTrue(known.all())
            self.assertEqual(payload["reviewer"], "tester")
            self.assertTrue(np.all(loaded == 1))


if __name__ == "__main__":
    unittest.main()
