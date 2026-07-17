"""Headlessly testable Part C superpixel review controller and local GUI."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image

from .legacy_loader import load_numbered_script


UNKNOWN_REGION = "__unknown__"


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
        self.segment_ids = {int(value) for value in np.unique(self.segment_labels)}
        self.state = ReviewState()
        self._undo: list[ReviewState] = []
        self._redo: list[ReviewState] = []

    def _checkpoint(self) -> None:
        self._undo.append(deepcopy(self.state))
        self._redo.clear()

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

    def run(self) -> str:
        import matplotlib.pyplot as plt
        from matplotlib.widgets import Button, RadioButtons, TextBox

        visible = np.asarray(Image.open(self.controller.visible_roi_path).convert("RGB"))
        if visible.shape[:2] != self.controller.segment_labels.shape:
            visible = np.asarray(Image.fromarray(visible).resize(
                (self.controller.segment_labels.shape[1], self.controller.segment_labels.shape[0]),
                Image.Resampling.LANCZOS,
            ))
        figure, axes = plt.subplots(1, 2 if self.controller.thermal_path else 1, figsize=(14, 8), squeeze=False)
        figure.subplots_adjust(left=0.05, right=0.78, bottom=0.17)
        axis = axes[0, 0]
        axis.imshow(visible)
        axis.contour(self.controller.segment_labels, levels=np.unique(self.controller.segment_labels), colors="white", linewidths=0.25)
        axis.set_title("Click superpixels; Ctrl-click selects several")
        axis.set_axis_off()
        if self.controller.thermal_path:
            axes[0, 1].imshow(Image.open(self.controller.thermal_path))
            axes[0, 1].set_title("Corresponding thermal image")
            axes[0, 1].set_axis_off()
        status = figure.text(0.05, 0.05, "Unreviewed regions are not labels.")
        radio_axis = figure.add_axes((0.80, 0.35, 0.19, 0.55))
        choices = [*sorted(self.controller.allowed_classes), "unknown/unclear"]
        radio = RadioButtons(radio_axis, choices)
        radio.on_clicked(lambda value: setattr(self, "current_category", UNKNOWN_REGION if value == "unknown/unclear" else value))

        def click(event: Any) -> None:
            if event.inaxes is not axis or event.xdata is None or event.ydata is None:
                return
            row, col = int(event.ydata), int(event.xdata)
            if 0 <= row < self.controller.segment_labels.shape[0] and 0 <= col < self.controller.segment_labels.shape[1]:
                append = bool(event.key and "control" in str(event.key).casefold())
                self.controller.select(int(self.controller.segment_labels[row, col]), append=append)
                status.set_text(f"Selected: {sorted(self.controller.state.selected)}")
                figure.canvas.draw_idle()

        figure.canvas.mpl_connect("button_press_event", click)

        def button(x: float, label: str, callback: Any) -> None:
            item = Button(figure.add_axes((x, 0.11, 0.095, 0.045)), label)
            item.on_clicked(callback)

        def assign(_event: Any) -> None:
            if self.current_category == UNKNOWN_REGION:
                self.controller.mark_unknown()
            else:
                self.controller.assign(self.current_category)
            status.set_text(f"Unreviewed: {len(self.controller.unreviewed_segments)}; unknown: {len(self.controller.unknown_segments)}")

        button(0.05, "Assign", assign)
        button(0.15, "Shadow", lambda event: self.controller.set_shadow(True))
        button(0.25, "No shadow", lambda event: self.controller.set_shadow(False))
        button(0.35, "Clear", lambda event: self.controller.clear_selected_labels())
        button(0.45, "Undo", lambda event: self.controller.undo())
        button(0.55, "Redo", lambda event: self.controller.redo())
        button(0.65, "Save draft", lambda event: self.controller.save_draft(self.draft_path))
        notes_box = TextBox(figure.add_axes((0.12, 0.01, 0.55, 0.035)), "Notes", initial=self.controller.state.notes)
        notes_box.on_submit(lambda value: self.controller.set_review_metadata(notes=value))

        def accept(_event: Any) -> None:
            try:
                self.controller.accept(self.draft_path)
            except ValueError as exc:
                status.set_text(str(exc))
                figure.canvas.draw_idle()
                return
            plt.close(figure)

        def cancel(_event: Any) -> None:
            self.controller.cancel(self.draft_path)
            plt.close(figure)

        button(0.80, "Accept", accept)
        button(0.90, "Cancel", cancel)
        plt.show()
        if self.controller.state.review_status not in {"accepted", "cancelled"}:
            self.controller.save_draft(self.draft_path)
        return self.controller.state.review_status
