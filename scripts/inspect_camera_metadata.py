#!/usr/bin/env python3
"""Summarize DJI Matrice 4T camera metadata for Part A validation."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from camera_profiles import classify_matrice_4t_camera


PROJECT_ROOT = Path(__file__).resolve().parents[1]
METADATA_CSV = PROJECT_ROOT / "data" / "metadata" / "dji_image_metadata.csv"
OUTPUT_CSV = PROJECT_ROOT / "data" / "metadata" / "camera_metadata_validation_summary.csv"


def main() -> int:
    if not METADATA_CSV.is_file():
        raise FileNotFoundError(f"Missing metadata CSV: {METADATA_CSV}")

    with METADATA_CSV.open("r", encoding="utf-8-sig", newline="") as csv_file:
        rows = list(csv.DictReader(csv_file))

    image_types = Counter(row.get("image_type", "") for row in rows)
    camera_keys = Counter()
    confidence = Counter()
    visible_35mm = Counter()
    thermal_35mm = Counter()
    focal_size_combos = Counter()

    for row in rows:
        classification = classify_matrice_4t_camera(row)
        image_type = row.get("image_type", "")
        camera_keys[classification["camera_key"]] += 1
        confidence[classification["confidence"]] += 1
        combo = (
            image_type,
            row.get("focal_length", ""),
            row.get("focal_length_35mm", ""),
            row.get("image_width", ""),
            row.get("image_height", ""),
        )
        focal_size_combos[combo] += 1
        if image_type == "visible":
            visible_35mm[row.get("focal_length_35mm", "")] += 1
        elif image_type == "thermal":
            thermal_35mm[row.get("focal_length_35mm", "")] += 1

    summary_rows: list[tuple[str, str]] = [
        ("validated_on", "2026-07-07"),
        ("metadata_csv", "data/metadata/dji_image_metadata.csv"),
        ("total_metadata_rows", str(len(rows))),
        ("visible_rows", str(image_types.get("visible", 0))),
        ("thermal_rows", str(image_types.get("thermal", 0))),
        (
            "preliminary_rule",
            "Use image_type plus per-image focal_length_35mm: 24=wide visible, 70=medium tele visible, 168=tele visible, 52-53=thermal.",
        ),
        (
            "important_warning",
            "This is a metadata validation rule only; later footprint, cover, and LUHK overlay outputs remain non-final until camera selection is validated per image.",
        ),
    ]

    for key, count in sorted(camera_keys.items()):
        summary_rows.append((f"classified_{key}", str(count)))
    for key, count in sorted(confidence.items()):
        summary_rows.append((f"classification_confidence_{key}", str(count)))
    for key, count in sorted(visible_35mm.items(), key=lambda item: float(item[0] or 0)):
        summary_rows.append((f"visible_focal_length_35mm_{key}", str(count)))
    for key, count in sorted(thermal_35mm.items(), key=lambda item: float(item[0] or 0)):
        summary_rows.append((f"thermal_focal_length_35mm_{key}", str(count)))
    for combo, count in focal_size_combos.most_common():
        image_type, focal, focal_35mm, width, height = combo
        summary_rows.append((f"combo_{image_type}_{focal}_{focal_35mm}_{width}x{height}", str(count)))

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file, lineterminator="\n")
        writer.writerow(["metric", "value"])
        writer.writerows(summary_rows)

    print(f"Wrote {OUTPUT_CSV.relative_to(PROJECT_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
