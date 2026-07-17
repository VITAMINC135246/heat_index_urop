#!/usr/bin/env python3
"""Benchmark v0.3 spatial/temporal stages with non-scientific fixtures."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.workflow.canonical_result import write_canonical_result
from scripts.workflow.models import ManualReviewStatus, ProcessingRoute, QAStatus, SourceMethod
from scripts.workflow.part_e_adapter import aggregate_canonical_results
from scripts.workflow.temporal_analysis import run_temporal_analysis


def directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def write_fixture(root: Path, image_id: str, hour: int, *, normal: bool, ambient: float | None) -> Path:
    shape = (32, 40)
    temperature = np.linspace(22.0 + hour / 10, 42.0 + hour / 10, np.prod(shape), dtype=np.float32).reshape(shape)
    metadata = {
        "capture_time": f"2026-02-02T{hour:02d}:00:00",
        "capture_timezone": "Asia/Hong_Kong",
        "ambient_temperature_c": ambient,
        "definition": "per-pixel radiometric surface temperature fixture",
    }
    ambient_metadata = (
        {
            "ambient_temperature_c": ambient,
            "source": "synthetic ambient fixture",
            "definition": "synthetic near-surface air temperature",
        }
        if ambient is not None
        else {}
    )
    if normal:
        labels = np.ones(shape, dtype=np.int16)
        known = np.ones(shape, dtype=bool)
        return write_canonical_result(
            output_root=root / "canonical", image_id=image_id, group_id=image_id, pair_id=image_id,
            dataset_id="non_scientific_benchmark_fixture", visible_path="fixture-visible", thermal_path="fixture-thermal",
            temperature=temperature, labels=labels, known_mask=known,
            processing_route=ProcessingRoute.NORMAL_VT, source_method=SourceMethod.VISIBLE_REVIEW,
            review_status=ManualReviewStatus.ACCEPTED, qa_status=QAStatus.PASS,
            configuration_hash=image_id, source_file_hashes={"fixture": image_id}, surface_cover_names={1: "roof"},
            temperature_metadata=metadata, ambient_metadata=ambient_metadata,
            temperature_source="mocked_temperature_matrix", luhk_provenance="unknown",
        )[1]
    target = np.zeros(shape, dtype=bool)
    target[4:28, 5:35] = True
    labels = np.full(shape, -1, dtype=np.int16)
    labels[target] = 5
    return write_canonical_result(
        output_root=root / "canonical", image_id=image_id, group_id=image_id, pair_id=image_id,
        dataset_id="non_scientific_benchmark_fixture", visible_path="", thermal_path="fixture-thermal",
        temperature=temperature, labels=labels, known_mask=target, target_mask=target,
        processing_route=ProcessingRoute.THERMAL_POLYGON,
        source_method=SourceMethod.THERMAL_POLYGON_USER_ANNOTATION,
        review_status=ManualReviewStatus.ACCEPTED, qa_status=QAStatus.PASS,
        configuration_hash=image_id, source_file_hashes={"fixture": image_id},
        surface_cover_names={5: "grass_low_vegetation"}, surface_cover_class_id=5,
        surface_cover_category="grass_low_vegetation", target_id="benchmark-soccer-target",
        target_name="NON-SCIENTIFIC benchmark target", polygon_coordinates=[[5, 4], [35, 4], [35, 28], [5, 28]],
        luhk_category="GIC / open space", luhk_code="gic_open_space", luhk_provenance="user_supplied_luhk",
        temperature_metadata=metadata, ambient_metadata=ambient_metadata,
        temperature_source="mocked_temperature_matrix",
    )[1]


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = PROJECT_ROOT / "outputs" / "runs" / f"benchmark_v0_3_{stamp}"
    root.mkdir(parents=True, exist_ok=True)
    manifests = [
        write_fixture(root, "benchmark_normal_0900", 9, normal=True, ambient=20.0),
        write_fixture(root, "benchmark_polygon_0900", 9, normal=False, ambient=20.0),
        write_fixture(root, "benchmark_polygon_1100", 11, normal=False, ambient=21.0),
        write_fixture(root, "benchmark_polygon_1400", 14, normal=False, ambient=None),
    ]
    canonical = root / "combined.parquet"
    aggregate_canonical_results(manifests, output_parquet=canonical, summary_csv=root / "source_summary.csv")
    config = {
        "outputs": {
            "canonical_parquet": canonical.resolve().as_posix(),
            "spatial_maps": (root / "spatial").resolve().as_posix(),
        }
    }
    config_path = root / "spatial_config.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    started = time.perf_counter()
    spatial = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "part_e" / "05_generate_pixel_spatial_figures.py"), "--config", str(config_path)],
        cwd=PROJECT_ROOT, capture_output=True, text=True, check=False,
    )
    spatial_seconds = time.perf_counter() - started
    if spatial.returncode:
        raise RuntimeError(spatial.stdout + "\n" + spatial.stderr)

    started = time.perf_counter()
    temporal = run_temporal_analysis(
        canonical, output_root=root / "temporal", default_timezone="Asia/Hong_Kong", resume=False
    )
    temporal_seconds = time.perf_counter() - started
    started = time.perf_counter()
    resumed = run_temporal_analysis(
        canonical, output_root=root / "temporal", default_timezone="Asia/Hong_Kong", resume=True
    )
    temporal_resume_seconds = time.perf_counter() - started
    payload = {
        "fixture_policy": "non-scientific synthetic temperature and ambient matrices; never use for a 26C claim",
        "processing_version": "heat-index-urop-0.3",
        "canonical_rows": 4 * 32 * 40,
        "spatial_seconds": spatial_seconds,
        "temporal_seconds": temporal_seconds,
        "temporal_resume_seconds": temporal_resume_seconds,
        "temporal_status": temporal.status,
        "temporal_resume_status": resumed.status,
        "output_bytes": directory_size(root),
        "root": root.resolve().as_posix(),
    }
    benchmark_path = root / "benchmark.json"
    benchmark_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"Benchmark: {benchmark_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
