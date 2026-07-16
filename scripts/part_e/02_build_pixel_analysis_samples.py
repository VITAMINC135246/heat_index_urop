#!/usr/bin/env python3
"""Build deterministic spatially thinned pixel samples with retained dependence."""

from __future__ import annotations

import argparse

import pandas as pd

from part_e_pixel_common import (
    SAMPLE_COLUMNS,
    SAMPLE_FILES,
    dataframe_sha256,
    ensure_output_directories,
    load_config,
    project_path,
    read_canonical,
    spatially_thinned_sample,
    write_csv,
    write_sample_outputs,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/part_e_delta_t_analysis.json")
    parser.add_argument("--seed", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    ensure_output_directories(config)
    seed = int(args.seed or config["sampling"]["primary_seed"])
    columns = list(dict.fromkeys(SAMPLE_COLUMNS + ["pixel_accepted"]))
    full = read_canonical(config, columns=columns)
    manifests: list[pd.DataFrame] = []
    reproducibility: list[dict[str, object]] = []
    for family in SAMPLE_FILES:
        sample, manifest = spatially_thinned_sample(full, family, config, seed)
        repeated, _ = spatially_thinned_sample(full, family, config, seed)
        checksum = dataframe_sha256(sample, ["pixel_uid"])
        repeated_checksum = dataframe_sha256(repeated, ["pixel_uid"])
        exact = checksum == repeated_checksum and len(sample) == len(repeated)
        if not exact:
            raise ValueError(f"Sampling reproducibility failed for {family}.")
        write_sample_outputs(config, family, sample)
        manifests.append(manifest)
        reproducibility.append({
            "analysis_family": family,
            "sampling_seed": seed,
            "first_sample_count": len(sample),
            "repeated_sample_count": len(repeated),
            "first_pixel_uid_checksum": checksum,
            "repeated_pixel_uid_checksum": repeated_checksum,
            "exact_pixel_uid_match": exact,
            "duplicate_pixel_uid_count": int(sample["pixel_uid"].duplicated().sum()),
            "status": "PASS" if exact and not sample["pixel_uid"].duplicated().any() else "FAIL",
        })
        print(f"{family}: {len(sample):,} sampled pixels")

    manifest_frame = pd.concat(manifests, ignore_index=True)
    write_csv(project_path(config["outputs"]["tables"]) / "part_e_pixel_sampling_manifest.csv", manifest_frame)
    coverage = (
        manifest_frame.groupby(["analysis_family", "group_name"], sort=True)
        .agg(
            full_eligible_pixel_count=("eligible_pixel_count", "sum"),
            sampled_pixel_count=("sampled_pixel_count", "sum"),
            full_image_count=("image_id", "nunique"),
            sampled_image_count=("image_id", lambda values: manifest_frame.loc[values.index].loc[manifest_frame.loc[values.index, "sampled_pixel_count"] > 0, "image_id"].nunique()),
        )
        .reset_index()
    )
    coverage["sampling_fraction"] = coverage["sampled_pixel_count"] / coverage["full_eligible_pixel_count"]
    coverage["sampling_seed"] = seed
    coverage["sampling_method"] = config["sampling"]["method"]
    write_csv(project_path(config["outputs"]["tables"]) / "part_e_pixel_sample_coverage.csv", coverage)
    write_csv(
        project_path(config["outputs"]["qa"]) / "part_e_sampling_reproducibility.csv",
        pd.DataFrame(reproducibility),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
