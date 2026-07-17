#!/usr/bin/env python3
"""Measure representative schema-0.2 stage timings without raw DJI data or SDK."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, TypeVar

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.workflow.canonical_result import write_canonical_result
from scripts.workflow.input_validation import validate_group
from scripts.workflow.models import (
    CoverageClass,
    GroupInput,
    ManualReviewStatus,
    PartBDecision,
    ProcessingRoute,
    QAStatus,
    SceneCorrespondence,
    SourceMethod,
)
from scripts.workflow.part_b_adapter import run_full_part_b
from scripts.workflow.part_b_correspondence import triage_content_correspondence
from scripts.workflow.part_c_adapter import prepare_part_c_review
from scripts.workflow.part_e_runner import run_formal_part_e
from scripts.workflow.temperature_extraction import extract_temperature
from scripts.part_b.b06_generate_alignment_refinement_review import generate_pair_review


T = TypeVar("T")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="Benchmark JSON path; defaults under ignored outputs/runs/.")
    parser.add_argument("--skip-formal-part-e", action="store_true", help="Skip the slower sampling/statistics/KDE/plot stage.")
    return parser.parse_args()


def measure(name: str, function: Callable[[], T], rows: list[dict[str, object]]) -> T:
    tracemalloc.start()
    started = time.perf_counter()
    result = function()
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    rows.append({
        "stage": name,
        "elapsed_seconds": round(elapsed, 6),
        "python_tracemalloc_peak_mib": round(peak / (1024 * 1024), 3),
    })
    return result


def directory_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def main() -> int:
    args = parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else PROJECT_ROOT / "outputs" / "runs" / f"benchmark_v0_2_{stamp}" / "benchmark.json"
    )
    work = output_path.parent / "payload"
    work.mkdir(parents=True, exist_ok=True)
    image_id = "DJI_20260717120000_0001"
    visible_path = work / f"{image_id}_V.PNG"
    thermal_path = work / f"{image_id}_T.PNG"
    visible = Image.new("RGB", (160, 120), "black")
    draw = ImageDraw.Draw(visible)
    draw.rectangle((12, 10, 145, 108), outline="white", width=5)
    draw.ellipse((35, 25, 90, 80), fill="gray")
    draw.line((5, 110, 150, 5), fill="white", width=3)
    visible.save(visible_path)
    visible.save(thermal_path)

    rows: list[dict[str, object]] = []
    group = GroupInput(
        "benchmark-group", str(visible_path), str(thermal_path), "benchmark",
        metadata_record={"relative_altitude": "50", "camera_model": "Matrice 4T", "focal_length": "24"},
    )
    measure("part_a_metadata_validation", lambda: validate_group(group, temperature_shape=(120, 160)), rows)
    b0 = measure(
        "part_b0_content_triage",
        lambda: triage_content_correspondence(
            group_id=group.group_id, image_id=image_id, visible_path=visible_path,
            thermal_path=thermal_path, output_directory=work / "part_b0",
        ),
        rows,
    )
    accepted_review = PartBDecision(
        group_id=group.group_id, scene_correspondence=SceneCorrespondence.ACCEPTED,
        coverage_class=CoverageClass.THERMAL_FULLY_SUPPORTED_BY_VISIBLE,
        manual_review_status=ManualReviewStatus.ACCEPTED,
    )
    part_b = measure(
        "full_part_b_end_to_end_candidates_gcp_and_review",
        lambda: run_full_part_b(
            group_id=group.group_id, image_id=image_id, visible_path=visible_path,
            thermal_path=thermal_path, part_b0=b0, output_directory=work / "part_b",
            review_decision=accepted_review,
        ),
        rows,
    )

    def standalone_review_package() -> dict[str, object]:
        directory = work / "part_b_review_only"
        old = b0.candidate_crop
        refined = part_b.candidate_crop
        values: dict[str, object] = {
            "image_id": image_id, "v_path": visible_path.as_posix(), "t_path": thermal_path.as_posix(),
            "rotation_deg": 0.0, "alignment_quality": "candidate_only", "needs_manual_gcp": "yes",
            "score_delta": 0.0,
        }
        for prefix, box in (("old", old), ("refined", refined)):
            values.update({
                f"{prefix}_roi_x_min_px": box[0], f"{prefix}_roi_y_min_px": box[1],
                f"{prefix}_roi_x_max_px": box[2], f"{prefix}_roi_y_max_px": box[3],
            })
        for name in (
            "old_roi_box", "refined_roi_box", "old_blend", "refined_blend", "old_side_by_side",
            "refined_side_by_side", "old_edges", "refined_edges", "gcp_reference",
        ):
            key = {
                "old_blend": "old_blend_overlay_path", "refined_blend": "refined_blend_overlay_path",
                "old_edges": "old_edge_overlay_path", "refined_edges": "refined_edge_overlay_path",
                "gcp_reference": "manual_gcp_side_by_side_path",
            }.get(name, f"{name}_path")
            values[key] = (directory / f"{name}.png").as_posix()
        values["contact_sheet_path"] = (directory / "contact_sheet.png").as_posix()
        return generate_pair_review(pd.Series(values))

    measure("part_b_review_package_generation_only", standalone_review_package, rows)
    controller = measure(
        "part_c_superpixel_preparation",
        lambda: prepare_part_c_review(
            image_id=image_id, pair_id="benchmark-pair", visible_path=visible_path,
            thermal_path=thermal_path, accepted_crop=part_b.candidate_crop,
            output_directory=work / "part_c",
            class_mapping={
                0: "no_data_unreviewed", 1: "roof", 2: "asphalt_road", 3: "concrete_pavement",
                4: "vegetation_tree", 5: "grass_low_vegetation", 6: "water", 7: "bare_soil",
                8: "other_surface", 9: "unclear_ignore",
            },
        ),
        rows,
    )

    fake_irp = work / "dji_irp_fake.exe"
    fake_irp.write_bytes(b"benchmark fake SDK identity")
    sdk_matrix = np.linspace(20.0, 40.0, 120 * 160, dtype=np.float32).reshape(120, 160)

    def fake_runner(command: list[str], **_kwargs: object) -> SimpleNamespace:
        raw_path = Path(command[command.index("-o") + 1])
        sdk_matrix.tofile(raw_path)
        return SimpleNamespace(returncode=0, stdout="benchmark mocked SDK", stderr="")

    temperature = measure(
        "part_d_mocked_native_sdk_extraction",
        lambda: extract_temperature(
            thermal_path=thermal_path, image_id=image_id,
            parameters={
                "distance_m": 50.0, "relative_humidity_percent": 70.0, "emissivity": 0.95,
                "ambient_temperature_c": 20.0, "reflected_temperature_c": 20.0,
            },
            work_directory=work / "part_d", irp_exe=fake_irp, runner=fake_runner,
        ),
        rows,
    )
    labels = np.ones(temperature.matrix.shape, dtype=np.int16)
    known = np.ones(temperature.matrix.shape, dtype=bool)
    manifest, manifest_path = measure(
        "canonical_schema_02_write",
        lambda: write_canonical_result(
            output_root=work / "canonical", image_id=image_id, group_id=group.group_id,
            pair_id="benchmark-pair", dataset_id="benchmark", visible_path=str(visible_path),
            thermal_path=str(thermal_path), temperature=temperature.matrix, labels=labels,
            known_mask=known, processing_route=ProcessingRoute.NORMAL_VT,
            source_method=SourceMethod.VISIBLE_REVIEW, review_status=ManualReviewStatus.ACCEPTED,
            qa_status=QAStatus.PASS, configuration_hash="benchmark", source_file_hashes={"thermal": "benchmark"},
            surface_cover_names={1: "roof"}, temperature_metadata=temperature.metadata,
            temperature_source="mocked_dji_sdk", part_b0=b0.to_dict(), part_b=part_b.to_dict(),
            annotation_review={"benchmark_segment_count": len(controller.segment_ids)},
        ),
        rows,
    )
    if not args.skip_formal_part_e:
        measure(
            "formal_part_e_sampling_statistics_kde_plots",
            lambda: run_formal_part_e([manifest_path], output_root=work / "formal_part_e", resume=False),
            rows,
        )

    canonical_bytes = directory_bytes(manifest_path.parent)
    disk = shutil.disk_usage(output_path.parent)
    retention_y = int((disk.free * 0.8) // max(canonical_bytes, 1))
    payload = {
        "benchmark_version": "v0.2-stage-benchmark-1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {"python": sys.version, "platform": sys.platform},
        "representative_input": {
            "image_shape": [120, 160], "synthetic_images": 1,
            "sdk_mode": "mocked runner writing native float32 matrix",
            "interactive_review_time": "not measured; user-dependent and excluded from compute timings",
        },
        "stages": rows,
        "storage": {
            "measured_canonical_bytes_per_image": canonical_bytes,
            "measured_canonical_mib_per_image": round(canonical_bytes / (1024 * 1024), 3),
            "retention_limit_y_formula": "floor(0.8 * free_storage_bytes / measured_canonical_bytes_per_image)",
            "current_machine_free_storage_bytes": disk.free,
            "current_machine_storage_based_y": retention_y,
        },
        "request_group_guidance": {
            "interactive_recommended_x": 1,
            "unattended_recommended_x": 25,
            "status": "provisional operational guidance, not a proven production-capacity limit",
            "note": "X is request scheduling; Y is storage retention. They are intentionally separate.",
        },
        "limitations": [
            "Synthetic cross-modal content is easier than arbitrary field imagery.",
            "Part D used the real command/parser path with a fake SDK runner; external DJI SDK latency was not measured.",
            "tracemalloc reports Python allocations and can undercount native NumPy/OpenCV buffers.",
            "Interactive annotation time is user-dependent and was not included in compute timing.",
            "Pilot-scale measurements do not prove production capacity.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(output_path)
    print(output_path)
    for row in rows:
        print(f"{row['stage']}: {row['elapsed_seconds']} s, peak {row['python_tracemalloc_peak_mib']} MiB")
    print(f"Canonical storage: {canonical_bytes} bytes/image")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
