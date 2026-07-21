"""Part C* polygon rasterization and isolated desktop drawing UI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from .gui_backend import interactive_pyplot


Point = tuple[float, float]


@dataclass(slots=True)
class PolygonAnnotation:
    accepted: bool
    cancelled: bool
    coordinates: list[Point]
    surface_cover_category: str
    luhk_category: str
    luhk_code: str = ""
    luhk_provenance: str = "unknown"
    surface_cover_provenance: str = "thermal_polygon_user_annotation"
    target_name: str = ""
    reviewer_confidence: str = ""
    notes: str = ""


def validate_polygon(vertices: Sequence[Sequence[float]], width: int, height: int) -> list[Point]:
    if width <= 0 or height <= 0:
        raise ValueError("Thermal-grid dimensions must be positive.")
    points: list[Point] = []
    for vertex in vertices:
        if len(vertex) != 2:
            raise ValueError("Every polygon vertex must contain x and y coordinates.")
        x, y = float(vertex[0]), float(vertex[1])
        if not np.isfinite(x) or not np.isfinite(y):
            raise ValueError("Polygon coordinates must be finite.")
        points.append((x, y))
    if len(points) < 3:
        raise ValueError("A polygon requires at least three vertices.")
    area = 0.0
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        area += (x1 * y2) - (x2 * y1)
    if abs(area) < 1e-6:
        raise ValueError("Polygon area must be greater than zero.")
    return points


def rasterize_polygon(vertices: Sequence[Sequence[float]], shape: tuple[int, int]) -> np.ndarray:
    """Rasterize native thermal pixel coordinates to an inside=True mask."""
    height, width = shape
    points = validate_polygon(vertices, width, height)
    canvas = Image.new("1", (width, height), 0)
    ImageDraw.Draw(canvas).polygon(points, outline=1, fill=1)
    mask = np.asarray(canvas, dtype=bool)
    if not mask.any():
        raise ValueError("Polygon does not select any thermal-grid pixels.")
    return mask


def labelled_polygon_arrays(
    vertices: Sequence[Sequence[float]],
    shape: tuple[int, int],
    surface_cover_class_id: int,
    *,
    unknown_value: int = -1,
) -> tuple[np.ndarray, np.ndarray]:
    """Return labels and the authoritative known mask for Part C*."""
    known = rasterize_polygon(vertices, shape)
    labels = np.full(shape, int(unknown_value), dtype=np.int16)
    labels[known] = int(surface_cover_class_id)
    return labels, known


def polygon_context_arrays(
    vertices: Sequence[Sequence[float]],
    shape: tuple[int, int],
    surface_cover_class_id: int,
    luhk_value: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build target-scoped cover and LUHK layers without exterior extrapolation."""
    labels, surface_known = labelled_polygon_arrays(vertices, shape, surface_cover_class_id)
    target = surface_known.copy()
    luhk_known = target.copy()
    luhk_labels = np.full(shape, "", dtype="<U96")
    luhk_labels[target] = str(luhk_value)
    return labels, surface_known, luhk_labels, luhk_known, target


class PolygonAnnotationUI:
    """Blocking desktop UI with visible context and thermal-grid polygon drawing."""

    def __init__(
        self,
        thermal_image_path: Path,
        surface_cover_category: str,
        *,
        visible_image_path: Path | None = None,
        target_name: str = "",
        luhk_category: str,
        luhk_code: str = "",
        luhk_provenance: str = "user_supplied_luhk",
        reviewer_confidence: str = "",
    ):
        if not surface_cover_category.strip():
            raise ValueError("A surface-cover category must be selected before drawing.")
        if not luhk_category.strip():
            raise ValueError("A LUHK category must be selected before drawing.")
        if luhk_provenance not in {"official_luhk_lookup", "user_supplied_luhk"}:
            raise ValueError("Accepted polygon LUHK provenance must be official lookup or user supplied.")
        self.thermal_image_path = thermal_image_path
        self.visible_image_path = visible_image_path
        self.surface_cover_category = surface_cover_category.strip()
        self.target_name = target_name.strip()
        self.luhk_category = luhk_category.strip()
        self.luhk_code = luhk_code.strip()
        self.luhk_provenance = luhk_provenance
        self.reviewer_confidence = reviewer_confidence.strip()
        self.vertices: list[Point] = []
        self.accepted = False
        self.cancelled = False
        self._widgets: list[object] = []

    def run(self) -> PolygonAnnotation:
        plt = interactive_pyplot("Part C* polygon GUI")
        from matplotlib.widgets import Button, PolygonSelector

        with Image.open(self.thermal_image_path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
        if self.visible_image_path:
            with Image.open(self.visible_image_path) as source:
                visible = ImageOps.exif_transpose(source).convert("RGB")
            figure, axes = plt.subplots(1, 2, figsize=(13, 7))
            axes[0].imshow(visible)
            axes[0].set_title("Visible reference (context only)")
            axes[0].set_axis_off()
            axis = axes[1]
        else:
            figure, axis = plt.subplots(figsize=(9, 7))
        figure.subplots_adjust(bottom=0.16)
        axis.imshow(image)
        axis.set_title(
            f"Part C* — {self.target_name or 'target'} / {self.surface_cover_category}\n"
            "Draw on this thermal image; outside remains unknown"
        )
        axis.set_axis_off()
        status = figure.text(
            0.04,
            0.105,
            f"LUHK: {self.luhk_category} | Click around the target; Accept closes the polygon automatically.",
            fontsize=10,
        )

        def selected(vertices: list[Point]) -> None:
            self.vertices = [(float(x), float(y)) for x, y in vertices]
            status.set_text(f"Polygon updated: {len(self.vertices)} vertices. Click Accept to validate.")
            figure.canvas.draw_idle()

        selector = PolygonSelector(axis, selected, useblit=True)
        clear_button = Button(figure.add_axes((0.48, 0.03, 0.12, 0.055)), "Clear / Redraw")
        accept_button = Button(figure.add_axes((0.62, 0.03, 0.12, 0.055)), "Accept")
        cancel_button = Button(figure.add_axes((0.76, 0.03, 0.12, 0.055)), "Cancel")
        self._widgets.extend([selector, clear_button, accept_button, cancel_button])

        def clear(_event: object) -> None:
            self.vertices = []
            selector.clear()
            status.set_text("Polygon cleared. Draw a new boundary on the thermal image.")
            figure.canvas.draw_idle()

        def accept(_event: object) -> None:
            try:
                current = self.vertices or [
                    (float(x), float(y)) for x, y in getattr(selector, "verts", [])
                ]
                self.vertices = validate_polygon(current, image.width, image.height)
            except ValueError as exc:
                status.set_text(f"Cannot accept: {exc}")
                figure.canvas.draw_idle()
                return
            self.accepted = True
            plt.close(figure)

        def cancel(_event: object) -> None:
            self.cancelled = True
            plt.close(figure)

        clear_button.on_clicked(clear)
        accept_button.on_clicked(accept)
        cancel_button.on_clicked(cancel)
        plt.show()
        return PolygonAnnotation(
            accepted=self.accepted,
            cancelled=self.cancelled,
            coordinates=self.vertices if self.accepted else [],
            surface_cover_category=self.surface_cover_category,
            luhk_category=self.luhk_category,
            luhk_code=self.luhk_code,
            luhk_provenance=self.luhk_provenance,
            target_name=self.target_name,
            reviewer_confidence=self.reviewer_confidence,
        )


def run_polygon_gui_subprocess(
    *,
    request_path: Path,
    result_path: Path,
    thermal_image_path: Path,
    visible_image_path: Path | None,
    surface_cover_category: str,
    target_name: str,
    luhk_category: str,
    luhk_code: str,
    luhk_provenance: str,
    reviewer_confidence: str,
) -> PolygonAnnotation:
    """Launch review in a clean process isolated from headless report plots."""
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(
        json.dumps(
            {
                "thermal_image_path": thermal_image_path.resolve().as_posix(),
                "visible_image_path": visible_image_path.resolve().as_posix() if visible_image_path else "",
                "surface_cover_category": surface_cover_category,
                "target_name": target_name,
                "luhk_category": luhk_category,
                "luhk_code": luhk_code,
                "luhk_provenance": luhk_provenance,
                "reviewer_confidence": reviewer_confidence,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    environment = os.environ.copy()
    if os.name == "nt":
        # Applied before process startup; unlike a late Tk call this prevents
        # Windows 150% scaling from placing controls outside the window.
        environment["__COMPAT_LAYER"] = "HIGHDPIAWARE"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.workflow.polygon_annotation",
            "--request",
            str(request_path),
            "--result",
            str(result_path),
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"Part C* polygon GUI exited with code {completed.returncode}.")
    if not result_path.is_file():
        return PolygonAnnotation(False, False, [], surface_cover_category, luhk_category)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    return PolygonAnnotation(
        accepted=bool(payload.get("accepted")),
        cancelled=bool(payload.get("cancelled")),
        coordinates=[(float(x), float(y)) for x, y in payload.get("coordinates", [])],
        surface_cover_category=str(payload.get("surface_cover_category", surface_cover_category)),
        luhk_category=str(payload.get("luhk_category", luhk_category)),
        luhk_code=str(payload.get("luhk_code", luhk_code)),
        luhk_provenance=str(payload.get("luhk_provenance", luhk_provenance)),
        target_name=str(payload.get("target_name", target_name)),
        reviewer_confidence=str(payload.get("reviewer_confidence", reviewer_confidence)),
    )


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Launch the Part C* polygon GUI.")
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    payload = json.loads(Path(args.request).read_text(encoding="utf-8"))
    annotation = PolygonAnnotationUI(
        Path(payload["thermal_image_path"]),
        str(payload["surface_cover_category"]),
        visible_image_path=Path(payload["visible_image_path"]) if payload.get("visible_image_path") else None,
        target_name=str(payload.get("target_name", "")),
        luhk_category=str(payload["luhk_category"]),
        luhk_code=str(payload.get("luhk_code", "")),
        luhk_provenance=str(payload.get("luhk_provenance", "user_supplied_luhk")),
        reviewer_confidence=str(payload.get("reviewer_confidence", "")),
    ).run()
    result_path = Path(args.result)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(asdict(annotation), indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
