from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from scripts.workflow.part_c_adapter import load_reviewed_label_override
from scripts.workflow.part_c_review_gui import SuperpixelReviewController, SuperpixelReviewGUI, interactive_pyplot
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

    def test_gui_switches_from_headless_agg_to_tk_backend(self) -> None:
        with (
            patch("matplotlib.pyplot.get_backend", return_value="Agg"),
            patch("matplotlib.pyplot.switch_backend") as switch_backend,
        ):
            interactive_pyplot()
        switch_backend.assert_called_once_with("TkAgg")

    def test_gui_keeps_an_existing_interactive_backend(self) -> None:
        with (
            patch("matplotlib.pyplot.get_backend", return_value="TkAgg"),
            patch("matplotlib.pyplot.switch_backend") as switch_backend,
        ):
            interactive_pyplot()
        switch_backend.assert_not_called()

    def test_suggestion_prefill_is_visible_undoable_and_gui_retains_widgets(self) -> None:
        controller = self.controller()
        controller.suggestions[3] = "unclear_ignore"
        self.assertEqual(controller.apply_suggestions_to_unreviewed(), 3)
        self.assertFalse(controller.unreviewed_segments)
        self.assertEqual(controller.state.labels[3], "__unknown__")
        self.assertTrue(controller.undo())
        self.assertEqual(controller.unreviewed_segments, {1, 2, 3})
        with tempfile.TemporaryDirectory() as directory:
            from PIL import Image
            import matplotlib.pyplot as plt

            plt.switch_backend("Agg")
            root = Path(directory)
            visible = root / "visible.png"
            thermal = root / "thermal.png"
            Image.new("RGB", (3, 2), "green").save(visible)
            Image.new("RGB", (3, 2), "gray").save(thermal)
            controller.visible_roi_path = str(visible)
            controller.thermal_path = str(thermal)
            gui = SuperpixelReviewGUI(controller, root / "review.json")
            with (
                patch("scripts.workflow.part_c_review_gui.interactive_pyplot", return_value=plt),
                patch.object(plt, "show"),
            ):
                self.assertEqual(gui.run(), "draft")
            from matplotlib.backend_bases import ResizeEvent

            canvas = gui._widgets[-1].ax.figure.canvas
            canvas.callbacks.process("resize_event", ResizeEvent("resize_event", canvas))
            self.assertGreaterEqual(len(gui._widgets), 10)
            self.assertTrue(gui._boundaries(controller.segment_labels).any())
            self.assertEqual(gui._review_overlay().shape, (2, 3, 4))
            buttons = {
                widget.label.get_text(): widget
                for widget in gui._widgets
                if hasattr(widget, "label") and hasattr(widget.label, "get_text")
            }
            controller.select(1)
            buttons["Assign"]._observers.process("clicked", None)
            self.assertIn(controller.state.labels[1], controller.allowed_classes)
            buttons["Mark unknown"]._observers.process("clicked", None)
            self.assertEqual(controller.state.labels[1], "__unknown__")
            buttons["Shadow"]._observers.process("clicked", None)
            self.assertTrue(controller.state.shadow[1])
            buttons["No shadow"]._observers.process("clicked", None)
            self.assertFalse(controller.state.shadow[1])
            buttons["Undo"]._observers.process("clicked", None)
            self.assertTrue(controller.state.shadow[1])
            buttons["Redo"]._observers.process("clicked", None)
            self.assertFalse(controller.state.shadow[1])


if __name__ == "__main__":
    unittest.main()
