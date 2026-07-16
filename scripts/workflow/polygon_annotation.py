"""Part C* polygon rasterization and minimal local Matplotlib drawing UI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageOps


Point = tuple[float, float]


@dataclass(slots=True)
class PolygonAnnotation:
    accepted: bool
    cancelled: bool
    coordinates: list[Point]
    surface_cover_category: str
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
    """Return labels and the authoritative known mask for Part C*.

    Outside values use a storage sentinel, but the boolean known mask is the
    authority. The sentinel is never a physical surface-cover class.
    """
    known = rasterize_polygon(vertices, shape)
    labels = np.full(shape, int(unknown_value), dtype=np.int16)
    labels[known] = int(surface_cover_class_id)
    return labels, known


class PolygonAnnotationUI:
    """Small blocking Matplotlib UI with Draw/Clear/Accept/Cancel behavior."""

    def __init__(
        self,
        thermal_image_path: Path,
        surface_cover_category: str,
        *,
        target_name: str = "",
        reviewer_confidence: str = "",
    ):
        if not surface_cover_category.strip():
            raise ValueError("A surface-cover category must be selected before drawing.")
        self.thermal_image_path = thermal_image_path
        self.surface_cover_category = surface_cover_category.strip()
        self.target_name = target_name.strip()
        self.reviewer_confidence = reviewer_confidence.strip()
        self.vertices: list[Point] = []
        self.accepted = False
        self.cancelled = False

    def run(self) -> PolygonAnnotation:
        import matplotlib.pyplot as plt
        from matplotlib.widgets import Button, PolygonSelector

        with Image.open(self.thermal_image_path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
        figure, axis = plt.subplots(figsize=(11, 8))
        figure.subplots_adjust(bottom=0.14)
        axis.imshow(image)
        axis.set_title(
            f"Part C* — {self.surface_cover_category}\nDraw polygon, then Accept; outside remains unknown"
        )
        axis.set_axis_off()

        def selected(vertices: list[Point]) -> None:
            self.vertices = [(float(x), float(y)) for x, y in vertices]

        selector = PolygonSelector(axis, selected, useblit=True)
        clear_axis = figure.add_axes((0.48, 0.03, 0.12, 0.055))
        accept_axis = figure.add_axes((0.62, 0.03, 0.12, 0.055))
        cancel_axis = figure.add_axes((0.76, 0.03, 0.12, 0.055))
        clear_button = Button(clear_axis, "Clear / Redraw")
        accept_button = Button(accept_axis, "Accept")
        cancel_button = Button(cancel_axis, "Cancel")

        def clear(_event: object) -> None:
            self.vertices = []
            selector.clear()
            figure.canvas.draw_idle()

        def accept(_event: object) -> None:
            try:
                validate_polygon(self.vertices, image.width, image.height)
            except ValueError as exc:
                axis.set_title(f"Cannot accept: {exc}\nDraw a valid polygon; outside remains unknown")
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
        if not self.accepted and not self.cancelled:
            self.cancelled = True
        return PolygonAnnotation(
            accepted=self.accepted,
            cancelled=self.cancelled,
            coordinates=self.vertices if self.accepted else [],
            surface_cover_category=self.surface_cover_category,
            target_name=self.target_name,
            reviewer_confidence=self.reviewer_confidence,
        )
