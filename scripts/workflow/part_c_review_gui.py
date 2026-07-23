"""Headlessly testable Part C superpixel review controller and local GUI."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image

from .gui_backend import interactive_pyplot as _interactive_pyplot
from .legacy_loader import load_numbered_script


UNKNOWN_REGION = "__unknown__"


def interactive_pyplot() -> Any:
    """Compatibility wrapper used by Part C and its regression tests."""
    return _interactive_pyplot("Part C GUI")


def array_sha256(array: np.ndarray) -> str:
    digest = hashlib.sha256()
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(str(tuple(array.shape)).encode("ascii"))
    digest.update(np.ascontiguousarray(array).tobytes())
    return digest.hexdigest()


@dataclass
class ReviewState:
    labels: dict[int, str] = field(default_factory=dict)
    shadow: dict[int, bool] = field(default_factory=dict)
    selected: set[int] = field(default_factory=set)
    notes: str = ""
    reviewer_confidence: str = ""
    reviewer: str = ""
    review_status: str = "draft"


class SuperpixelReviewController:
    def __init__(
        self,
        *,
        image_id: str,
        segment_labels: np.ndarray,
        class_mapping: dict[int, str],
        suggestions: dict[int, str] | None = None,
        visible_roi_path: str = "",
        thermal_path: str = "",
        luhk_reference_path: str = "",
        luhk_metadata: dict[str, Any] | None = None,
    ):
        labels = np.asarray(segment_labels)
        if labels.ndim != 2:
            raise ValueError("Part C segment labels must be a two-dimensional array.")
        self.image_id = image_id
        self.segment_labels = labels.astype(np.int32, copy=False)
        self.class_mapping = {int(key): str(value) for key, value in class_mapping.items()}
        self.class_ids = {value: key for key, value in self.class_mapping.items()}
        self.allowed_classes = {value for key, value in self.class_mapping.items() if key not in {0, 9}}
        self.suggestions = {int(key): str(value) for key, value in (suggestions or {}).items()}
        self.visible_roi_path = visible_roi_path
        self.thermal_path = thermal_path
        self.luhk_reference_path = luhk_reference_path
        self.luhk_metadata = dict(luhk_metadata or {})
        self.segment_ids = {int(value) for value in np.unique(self.segment_labels)}
        self.state = ReviewState()
        self._undo: list[ReviewState] = []
        self._redo: list[ReviewState] = []

    def _checkpoint(self) -> None:
        self._undo.append(deepcopy(self.state))
        self._redo.clear()

    def begin_gui_session(self) -> None:
        """Require a fresh Accept action whenever the desktop review opens."""

        self.state.review_status = "draft"

    def select(self, segment_ids: int | list[int] | set[int], *, append: bool = False) -> None:
        values = {int(segment_ids)} if isinstance(segment_ids, (int, np.integer)) else {int(value) for value in segment_ids}
        unknown = values.difference(self.segment_ids)
        if unknown:
            raise ValueError(f"Unknown superpixel IDs: {sorted(unknown)}")
        self.state.selected = self.state.selected.union(values) if append else values

    def assign(self, category: str) -> None:
        if category not in self.allowed_classes:
            raise ValueError(f"Unknown physical surface-cover category: {category}")
        if not self.state.selected:
            raise ValueError("Select at least one superpixel before assigning a label.")
        self._checkpoint()
        for segment_id in self.state.selected:
            self.state.labels[segment_id] = category

    def mark_unknown(self) -> None:
        if not self.state.selected:
            raise ValueError("Select at least one superpixel before marking it unknown.")
        self._checkpoint()
        for segment_id in self.state.selected:
            self.state.labels[segment_id] = UNKNOWN_REGION

    def apply_suggestions_to_unreviewed(self) -> int:
        """Apply valid machine suggestions as a visible, undoable review starting point."""
        assignments = {
            segment_id: category if category in self.allowed_classes else UNKNOWN_REGION
            for segment_id, category in self.suggestions.items()
            if segment_id in self.unreviewed_segments
        }
        if not assignments:
            return 0
        self._checkpoint()
        self.state.labels.update(assignments)
        return len(assignments)

    def set_shadow(self, value: bool) -> None:
        if not self.state.selected:
            raise ValueError("Select at least one superpixel before changing shadow status.")
        self._checkpoint()
        for segment_id in self.state.selected:
            self.state.shadow[segment_id] = bool(value)

    def clear_selected_labels(self) -> None:
        if not self.state.selected:
            return
        self._checkpoint()
        for segment_id in self.state.selected:
            self.state.labels.pop(segment_id, None)
            self.state.shadow.pop(segment_id, None)

    def set_review_metadata(self, *, notes: str | None = None, reviewer_confidence: str | None = None, reviewer: str | None = None) -> None:
        self._checkpoint()
        if notes is not None:
            self.state.notes = notes
        if reviewer_confidence is not None:
            if reviewer_confidence not in {"", "low", "medium", "high"}:
                raise ValueError("Reviewer confidence must be low, medium, high, or blank.")
            self.state.reviewer_confidence = reviewer_confidence
        if reviewer is not None:
            self.state.reviewer = reviewer

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(deepcopy(self.state))
        self.state = self._undo.pop()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(deepcopy(self.state))
        self.state = self._redo.pop()
        return True

    @property
    def unreviewed_segments(self) -> set[int]:
        return self.segment_ids.difference(self.state.labels)

    @property
    def unknown_segments(self) -> set[int]:
        return {key for key, value in self.state.labels.items() if value == UNKNOWN_REGION}

    def validate_for_acceptance(self) -> list[str]:
        errors: list[str] = []
        if self.unreviewed_segments:
            errors.append(f"unreviewed_superpixels:{len(self.unreviewed_segments)}")
        invalid = {value for value in self.state.labels.values() if value not in self.allowed_classes | {UNKNOWN_REGION}}
        if invalid:
            errors.append(f"invalid_categories:{sorted(invalid)}")
        return errors

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": "part-c-superpixel-review-0.2.0",
            "image_id": self.image_id,
            "dimensions": [int(value) for value in self.segment_labels.shape],
            "segment_labels_sha256": array_sha256(self.segment_labels),
            "visible_roi_path": self.visible_roi_path,
            "thermal_path": self.thermal_path,
            "luhk_reference_path": self.luhk_reference_path,
            "luhk_metadata": self.luhk_metadata,
            "class_mapping": {str(key): value for key, value in self.class_mapping.items()},
            "suggestions": {str(key): value for key, value in self.suggestions.items()},
            "labels": {str(key): value for key, value in self.state.labels.items()},
            "shadow": {str(key): bool(value) for key, value in self.state.shadow.items()},
            "review_status": self.state.review_status,
            "reviewer": self.state.reviewer,
            "reviewer_confidence": self.state.reviewer_confidence,
            "notes": self.state.notes,
            "unreviewed_segment_count": len(self.unreviewed_segments),
            "unknown_segment_count": len(self.unknown_segments),
        }

    def save_draft(self, path: Path) -> Path:
        self.state.review_status = "draft"
        return self._write(path)

    def accept(self, path: Path) -> Path:
        errors = self.validate_for_acceptance()
        if errors:
            raise ValueError("Part C review cannot be accepted: " + ";".join(errors))
        self.state.review_status = "accepted"
        return self._write(path)

    def cancel(self, path: Path | None = None) -> Path | None:
        self.state.review_status = "cancelled"
        return self._write(path) if path else None

    def _write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(self._payload(), indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
        return path

    @classmethod
    def resume(
        cls,
        path: Path,
        *,
        segment_labels: np.ndarray,
        expected_image_id: str | None = None,
    ) -> "SuperpixelReviewController":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if expected_image_id and str(payload.get("image_id")) != expected_image_id:
            raise ValueError("Part C review image ID does not match the requested image.")
        if list(np.asarray(segment_labels).shape) != list(payload.get("dimensions", [])):
            raise ValueError("Part C review dimensions do not match the segment grid.")
        if array_sha256(np.asarray(segment_labels)) != payload.get("segment_labels_sha256"):
            raise ValueError("Part C review segment-grid hash does not match.")
        controller = cls(
            image_id=str(payload["image_id"]),
            segment_labels=segment_labels,
            class_mapping={int(key): value for key, value in payload["class_mapping"].items()},
            suggestions={int(key): value for key, value in payload.get("suggestions", {}).items()},
            visible_roi_path=str(payload.get("visible_roi_path", "")),
            thermal_path=str(payload.get("thermal_path", "")),
            luhk_reference_path=str(payload.get("luhk_reference_path", "")),
            luhk_metadata=dict(payload.get("luhk_metadata", {})),
        )
        controller.state = ReviewState(
            labels={int(key): value for key, value in payload.get("labels", {}).items()},
            shadow={int(key): bool(value) for key, value in payload.get("shadow", {}).items()},
            notes=str(payload.get("notes", "")),
            reviewer_confidence=str(payload.get("reviewer_confidence", "")),
            reviewer=str(payload.get("reviewer", "")),
            review_status=str(payload.get("review_status", "draft")),
        )
        return controller

    def generate_masks(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        if self.state.review_status != "accepted":
            raise ValueError("Final Part C masks require an accepted review artifact.")
        errors = self.validate_for_acceptance()
        if errors:
            raise ValueError("Part C review is invalid: " + ";".join(errors))
        rows = [
            {
                "segment_id": segment_id,
                "manual_class": "no_data_unreviewed" if label == UNKNOWN_REGION else label,
                "shadow_status": int(self.state.shadow.get(segment_id, False)),
                "confidence": self.state.reviewer_confidence,
            }
            for segment_id, label in sorted(self.state.labels.items())
        ]
        legacy = load_numbered_script(
            "scripts/part_c/03_generate_final_masks_and_summaries.py",
            "heat_index_part_c_final_masks_v02",
        )
        class_mask, shadow_mask, _low_conf = legacy.build_reviewed_label_layers(
            self.segment_labels,
            pd.DataFrame(rows),
            self.class_ids,
            "shadow_status",
        )
        known = ~np.isin(class_mask, [0, 9])
        canonical = class_mask.astype(np.int16)
        canonical[~known] = -1
        return canonical, known, shadow_mask.astype(bool)


class SuperpixelReviewGUI:
    """Lightweight Matplotlib renderer around ``SuperpixelReviewController``."""

    def __init__(self, controller: SuperpixelReviewController, draft_path: Path):
        self.controller = controller
        self.draft_path = draft_path
        self.current_category = next(iter(sorted(controller.allowed_classes)), UNKNOWN_REGION)
        self._widgets: list[Any] = []

    @staticmethod
    def _boundaries(labels: np.ndarray) -> np.ndarray:
        boundary = np.zeros(labels.shape, dtype=bool)
        boundary[1:, :] |= labels[1:, :] != labels[:-1, :]
        boundary[:-1, :] |= labels[:-1, :] != labels[1:, :]
        boundary[:, 1:] |= labels[:, 1:] != labels[:, :-1]
        boundary[:, :-1] |= labels[:, :-1] != labels[:, 1:]
        return boundary

    def _review_overlay(self) -> np.ndarray:
        labels = self.controller.segment_labels
        overlay = np.zeros((*labels.shape, 4), dtype=np.float32)
        palette = (
            (0.12, 0.47, 0.71), (1.00, 0.50, 0.05), (0.17, 0.63, 0.17),
            (0.84, 0.15, 0.16), (0.58, 0.40, 0.74), (0.55, 0.34, 0.29),
            (0.89, 0.47, 0.76), (0.50, 0.50, 0.50), (0.74, 0.74, 0.13),
            (0.09, 0.75, 0.81),
        )
        colors = {name: palette[index % len(palette)] for index, name in enumerate(sorted(self.controller.allowed_classes))}
        for segment_id in self.controller.segment_ids:
            mask = labels == segment_id
            category = self.controller.state.labels.get(segment_id)
            if category == UNKNOWN_REGION:
                overlay[mask] = (0.45, 0.45, 0.45, 0.58)
            elif category in colors:
                overlay[mask] = (*colors[category], 0.48)
            elif self.controller.suggestions.get(segment_id) in colors:
                overlay[mask] = (*colors[self.controller.suggestions[segment_id]], 0.12)
            if self.controller.state.shadow.get(segment_id, False):
                overlay[mask, :3] = (0.08, 0.15, 0.48)
                overlay[mask, 3] = 0.58
        for segment_id in self.controller.state.selected:
            mask = labels == segment_id
            overlay[mask, :3] = (1.0, 0.92, 0.05)
            overlay[mask, 3] = 0.62
        return overlay

    def run(self) -> str:
        # A resumed accepted artifact is useful as editable state, but merely
        # reopening and closing it must not count as acceptance in this run.
        self.controller.begin_gui_session()
        plt = interactive_pyplot()
        from matplotlib.widgets import Button, RadioButtons, TextBox

        class ResizeSafeTextBox(TextBox):
            """Work around Matplotlib 3.11 wrapping ResizeEvent as a location event."""

            def _resize(self, _event: Any) -> None:
                self.stop_typing()

        visible = np.asarray(Image.open(self.controller.visible_roi_path).convert("RGB"))
        if visible.shape[:2] != self.controller.segment_labels.shape:
            visible = np.asarray(Image.fromarray(visible).resize(
                (self.controller.segment_labels.shape[1], self.controller.segment_labels.shape[0]),
                Image.Resampling.LANCZOS,
            ))
        panel_count = 2 + int(bool(self.controller.thermal_path)) + int(bool(self.controller.luhk_reference_path))
        if panel_count >= 4:
            # Four readable 640×512 panels are more useful than four narrow
            # strips whose titles and image details overlap on a laptop.
            # Fit a 125%-scaled Windows laptop display without clipping the
            # action buttons below the canvas.  The two-by-two layout keeps
            # each contextual image readable at this smaller physical size.
            figure, axes_grid = plt.subplots(2, 2, figsize=(10.5, 5.8), squeeze=False)
            figure.subplots_adjust(
                left=0.035, right=0.79, bottom=0.21, top=0.93,
                hspace=0.22, wspace=0.08,
            )
        else:
            figure, axes_grid = plt.subplots(1, panel_count, figsize=(10.5, 5.8), squeeze=False)
            figure.subplots_adjust(left=0.035, right=0.79, bottom=0.20, top=0.91, wspace=0.08)
        panel_axes = list(axes_grid.flat)
        axis = panel_axes[0]
        review_axis = panel_axes[1]
        boundaries = self._boundaries(self.controller.segment_labels)
        boundary_rgba = np.zeros((*boundaries.shape, 4), dtype=np.float32)
        boundary_rgba[boundaries] = (1.0, 1.0, 1.0, 0.90)
        axis.imshow(visible)
        axis.imshow(boundary_rgba, interpolation="nearest")
        axis.set_title("Visible image + superpixel boundaries")
        axis.set_axis_off()
        review_axis.imshow(visible)
        review_artist = review_axis.imshow(self._review_overlay(), interpolation="nearest")
        review_axis.imshow(boundary_rgba, interpolation="nearest")
        review_axis.set_title("Live review mask (click here or visible image)")
        review_axis.set_axis_off()
        panel_index = 2
        if self.controller.thermal_path:
            panel_axes[panel_index].imshow(Image.open(self.controller.thermal_path))
            panel_axes[panel_index].set_title("Corresponding thermal image")
            panel_axes[panel_index].set_axis_off()
            panel_index += 1
        if self.controller.luhk_reference_path:
            panel_axes[panel_index].imshow(Image.open(self.controller.luhk_reference_path))
            panel_axes[panel_index].set_title("Official LUHK context (read-only)")
            panel_axes[panel_index].set_axis_off()
        status = figure.text(0.035, 0.100, "", fontsize=9.5)
        figure.text(
            0.035, 0.165,
            "1 Click region  2 Choose cover  3 Assign  |  Ctrl-click: multi-select  |  Pale colors: suggestions",
            fontsize=10,
        )
        luhk_status = str(self.controller.luhk_metadata.get("status", "unavailable"))
        luhk_provenance = str(self.controller.luhk_metadata.get("provenance", "unknown"))
        luhk_reason = str(self.controller.luhk_metadata.get("unavailable_reason", ""))
        luhk_uncertainty = str(self.controller.luhk_metadata.get("spatial_uncertainty", "")).strip()
        if not luhk_uncertainty:
            luhk_uncertainty = (
                "Approximate metadata-derived north-up footprint; yaw is not applied; "
                "Part B alignment does not improve map georegistration."
            )
        figure.text(
            0.035, 0.142,
            f"LUHK is read-only and separate from surface cover: status={luhk_status}; provenance={luhk_provenance}"
            + (f"; reason={luhk_reason}" if luhk_reason else ""),
            fontsize=8.5,
        )
        if not luhk_reason:
            figure.text(0.035, 0.121, f"Spatial precision: {luhk_uncertainty}", fontsize=8.2)
        radio_axis = figure.add_axes((0.805, 0.33, 0.19, 0.58))
        choices = [*sorted(self.controller.allowed_classes), "unknown/unclear"]
        radio = RadioButtons(radio_axis, choices)
        radio.on_clicked(lambda value: setattr(self, "current_category", UNKNOWN_REGION if value == "unknown/unclear" else value))
        self._widgets.append(radio)

        def refresh(message: str = "") -> None:
            review_artist.set_data(self._review_overlay())
            selected = sorted(self.controller.state.selected)
            status.set_text(
                f"{message}  Selected={selected or 'none'}  "
                f"Unreviewed={len(self.controller.unreviewed_segments)}  "
                f"Unknown={len(self.controller.unknown_segments)}  "
                f"Undo={len(self.controller._undo)}  Redo={len(self.controller._redo)}"
            )
            figure.canvas.draw_idle()

        def action(operation: Any, success: str) -> Any:
            def callback(_event: Any) -> None:
                try:
                    result = operation()
                    if isinstance(result, bool) and not result:
                        refresh("No matching history entry; state unchanged.")
                    else:
                        suffix = f" ({result})" if isinstance(result, int) and not isinstance(result, bool) else ""
                        refresh(success + suffix)
                except (OSError, ValueError, RuntimeError) as exc:
                    refresh(f"Cannot complete action: {exc}")
            return callback

        def click(event: Any) -> None:
            if event.inaxes not in {axis, review_axis} or event.xdata is None or event.ydata is None:
                return
            row, col = int(event.ydata), int(event.xdata)
            if 0 <= row < self.controller.segment_labels.shape[0] and 0 <= col < self.controller.segment_labels.shape[1]:
                append = bool(event.key and "control" in str(event.key).casefold())
                self.controller.select(int(self.controller.segment_labels[row, col]), append=append)
                refresh("Selection changed.")

        figure.canvas.mpl_connect("button_press_event", click)

        def button(x: float, y: float, width: float, label: str, callback: Any) -> None:
            item = Button(figure.add_axes((x, y, width, 0.042)), label)
            item.on_clicked(callback)
            self._widgets.append(item)

        button(0.035, 0.055, 0.085, "Assign", action(
            lambda: self.controller.mark_unknown() if self.current_category == UNKNOWN_REGION else self.controller.assign(self.current_category),
            "Assignment applied.",
        ))
        button(0.125, 0.055, 0.095, "Mark unknown", action(self.controller.mark_unknown, "Marked unknown."))
        button(0.225, 0.055, 0.075, "Shadow", action(lambda: self.controller.set_shadow(True), "Shadow applied."))
        button(0.305, 0.055, 0.085, "No shadow", action(lambda: self.controller.set_shadow(False), "Shadow cleared."))
        button(0.395, 0.055, 0.065, "Clear", action(self.controller.clear_selected_labels, "Selection cleared."))
        button(0.465, 0.055, 0.06, "Undo", action(self.controller.undo, "Undo."))
        button(0.530, 0.055, 0.06, "Redo", action(self.controller.redo, "Redo."))
        button(0.595, 0.055, 0.12, "Fill suggestions", action(
            self.controller.apply_suggestions_to_unreviewed, "Suggestions applied to unreviewed regions"
        ))
        button(0.720, 0.055, 0.07, "Save", action(lambda: self.controller.save_draft(self.draft_path), "Draft saved."))
        notes_box = ResizeSafeTextBox(
            figure.add_axes((0.11, 0.005, 0.51, 0.033)), "Notes", initial=self.controller.state.notes
        )
        notes_box.on_submit(lambda value: self.controller.set_review_metadata(notes=value))
        self._widgets.append(notes_box)

        def accept(_event: Any) -> None:
            try:
                self.controller.accept(self.draft_path)
            except ValueError as exc:
                refresh(str(exc) + " Use Fill suggestions or review remaining regions.")
                return
            plt.close(figure)

        def cancel(_event: Any) -> None:
            self.controller.cancel(self.draft_path)
            plt.close(figure)

        button(0.805, 0.20, 0.09, "Accept", accept)
        button(0.900, 0.20, 0.09, "Cancel", cancel)
        refresh("Ready.")
        plt.show()
        if self.controller.state.review_status not in {"accepted", "cancelled"}:
            self.controller.save_draft(self.draft_path)
        return self.controller.state.review_status


def run_review_gui_subprocess(controller: SuperpixelReviewController, draft_path: Path, segment_path: Path) -> str:
    """Run the GUI in a clean process so prior headless Part A/B plots cannot break Tk events."""
    session_path = draft_path.parent / "superpixel_review_session.json"
    session_path.write_text(
        json.dumps(
            {
                "image_id": controller.image_id,
                "segment_path": segment_path.resolve().as_posix(),
                "class_mapping": {str(key): value for key, value in controller.class_mapping.items()},
                "suggestions": {str(key): value for key, value in controller.suggestions.items()},
                "visible_roi_path": controller.visible_roi_path,
                "thermal_path": controller.thermal_path,
                "luhk_reference_path": controller.luhk_reference_path,
                "luhk_metadata": controller.luhk_metadata,
                "draft_path": draft_path.resolve().as_posix(),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    environment = os.environ.copy()
    if os.name == "nt":
        environment["__COMPAT_LAYER"] = "HIGHDPIAWARE"
    completed = subprocess.run(
        [sys.executable, "-m", "scripts.workflow.part_c_review_gui", "--session", str(session_path)],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"Part C review GUI exited with code {completed.returncode}.")
    if not draft_path.is_file():
        return "draft"
    return str(json.loads(draft_path.read_text(encoding="utf-8")).get("review_status", "draft"))


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Launch the Part C desktop review GUI.")
    parser.add_argument("--session", required=True)
    args = parser.parse_args()
    payload = json.loads(Path(args.session).read_text(encoding="utf-8"))
    segment_labels = np.load(payload["segment_path"], allow_pickle=False)
    artifact = Path(payload["draft_path"])
    if artifact.is_file():
        controller = SuperpixelReviewController.resume(
            artifact, segment_labels=segment_labels, expected_image_id=str(payload["image_id"])
        )
        # Session inputs are freshly prepared for the current run.  Older
        # drafts predate the real-image/LUHK panels, so do not let an otherwise
        # valid draft hide the current contextual imagery when it is resumed.
        controller.visible_roi_path = str(payload.get("visible_roi_path", controller.visible_roi_path))
        controller.thermal_path = str(payload.get("thermal_path", controller.thermal_path))
        controller.luhk_reference_path = str(
            payload.get("luhk_reference_path", controller.luhk_reference_path)
        )
        controller.luhk_metadata = dict(payload.get("luhk_metadata", controller.luhk_metadata))
    else:
        controller = SuperpixelReviewController(
            image_id=str(payload["image_id"]),
            segment_labels=segment_labels,
            class_mapping={int(key): value for key, value in payload["class_mapping"].items()},
            suggestions={int(key): value for key, value in payload.get("suggestions", {}).items()},
            visible_roi_path=str(payload["visible_roi_path"]),
            thermal_path=str(payload.get("thermal_path", "")),
            luhk_reference_path=str(payload.get("luhk_reference_path", "")),
            luhk_metadata=dict(payload.get("luhk_metadata", {})),
        )
    SuperpixelReviewGUI(controller, artifact).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
