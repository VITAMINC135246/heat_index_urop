#!/usr/bin/env python3
"""Run exploratory Part E statistical comparisons on aggregated observations."""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from part_e.part_e_common import (  # noqa: E402
    PART_E_SUMMARY_DIR,
    PART_E_TABLE_DIR,
    PROVISIONAL_NOTICE,
    read_dataset,
    relative_posix,
    round_float,
    write_csv,
    write_markdown,
)


CELL_DATA = PART_E_TABLE_DIR / "part_e_cell_delta_t_observations_all_finite.csv"
COVER_DATA = PART_E_TABLE_DIR / "part_e_surface_cover_delta_t_observations_all_finite.csv"
STATS_CSV = PART_E_TABLE_DIR / "part_e_exploratory_statistical_tests.csv"
STATS_MD = PART_E_SUMMARY_DIR / "part_e_exploratory_statistical_tests.md"


def valid_numeric(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    work = df.loc[pd.to_numeric(df.get("analysis_valid", 0), errors="coerce").fillna(0).astype(int).eq(1)].copy()
    work[value_col] = pd.to_numeric(work[value_col], errors="coerce")
    return work.dropna(subset=[value_col])


def welch_anova(groups: list[np.ndarray]) -> tuple[float, float, float, float] | None:
    try:
        from scipy import stats
    except Exception:
        return None
    arrays = [np.asarray(group, dtype=float) for group in groups if len(group) > 1]
    if len(arrays) < 2:
        return None
    n = np.array([len(group) for group in arrays], dtype=float)
    means = np.array([group.mean() for group in arrays], dtype=float)
    variances = np.array([group.var(ddof=1) for group in arrays], dtype=float)
    if np.any(variances <= 0):
        return None
    weights = n / variances
    weighted_mean = np.sum(weights * means) / np.sum(weights)
    k = len(arrays)
    numerator = np.sum(weights * (means - weighted_mean) ** 2) / (k - 1)
    correction = 1 + (2 * (k - 2) / (k**2 - 1)) * np.sum((1 / (n - 1)) * (1 - weights / np.sum(weights)) ** 2)
    f_stat = numerator / correction
    df1 = k - 1
    df2 = (k**2 - 1) / (3 * np.sum((1 / (n - 1)) * (1 - weights / np.sum(weights)) ** 2))
    p_value = stats.f.sf(f_stat, df1, df2)
    return float(f_stat), float(df1), float(df2), float(p_value)


def group_test(df: pd.DataFrame, group_col: str, value_col: str, analysis_unit: str) -> list[dict[str, object]]:
    try:
        from scipy import stats
    except Exception as exc:
        return [
            {
                "analysis_unit": analysis_unit,
                "comparison": group_col,
                "test": "not_run",
                "status": "scipy_unavailable",
                "notes": str(exc),
            }
        ]

    work = valid_numeric(df, value_col)
    groups = []
    labels = []
    for label, group in work.groupby(group_col, dropna=False, sort=True):
        values = group[value_col].to_numpy(dtype=float)
        if len(values) >= 2:
            labels.append(str(label))
            groups.append(values)
    rows: list[dict[str, object]] = []
    image_count = work["image_id"].nunique() if "image_id" in work.columns else ""
    if len(groups) < 2:
        return [
            {
                "analysis_unit": analysis_unit,
                "comparison": group_col,
                "test": "not_run",
                "status": "insufficient_groups",
                "group_count": len(groups),
                "image_count": image_count,
                "notes": "At least two groups with two observations each are required.",
            }
        ]

    f_stat, anova_p = stats.f_oneway(*groups)
    rows.append(
        {
            "analysis_unit": analysis_unit,
            "comparison": group_col,
            "test": "one_way_anova",
            "status": "exploratory",
            "group_count": len(groups),
            "image_count": image_count,
            "statistic": round_float(f_stat),
            "p_value": round_float(anova_p),
            "effect_size": "group mean differences reported in descriptive summary tables",
            "notes": "Exploratory only; observations are aggregated cells/cell-covers, with only five pilot images.",
        }
    )

    welch = welch_anova(groups)
    if welch is not None:
        f_welch, df1, df2, p_welch = welch
        rows.append(
            {
                "analysis_unit": analysis_unit,
                "comparison": group_col,
                "test": "welch_anova",
                "status": "exploratory",
                "group_count": len(groups),
                "image_count": image_count,
                "statistic": round_float(f_welch),
                "df1": round_float(df1),
                "df2": round_float(df2),
                "p_value": round_float(p_welch),
                "notes": "Exploratory variance-robust comparison; no claim of final inference.",
            }
        )

    kw_stat, kw_p = stats.kruskal(*groups)
    rows.append(
        {
            "analysis_unit": analysis_unit,
            "comparison": group_col,
            "test": "kruskal_wallis",
            "status": "exploratory",
            "group_count": len(groups),
            "image_count": image_count,
            "statistic": round_float(kw_stat),
            "p_value": round_float(kw_p),
            "notes": "Non-parametric exploratory comparison on aggregated observations.",
        }
    )

    pair_count = 0
    for (label_a, values_a), (label_b, values_b) in itertools.combinations(zip(labels, groups), 2):
        if len(values_a) < 2 or len(values_b) < 2:
            continue
        stat, p_value = stats.mannwhitneyu(values_a, values_b, alternative="two-sided")
        median_diff = float(np.median(values_a) - np.median(values_b))
        pair_count += 1
        rows.append(
            {
                "analysis_unit": analysis_unit,
                "comparison": group_col,
                "test": "pairwise_mann_whitney_bonferroni",
                "status": "exploratory",
                "group_a": label_a,
                "group_b": label_b,
                "group_count": len(groups),
                "image_count": image_count,
                "statistic": round_float(stat),
                "p_value": round_float(min(p_value * max(1, pair_count), 1.0)),
                "effect_size": round_float(median_diff),
                "effect_size_units": "median delta-T difference, group_a minus group_b, deg C",
                "notes": "Bonferroni-adjusted sequential exploratory pairwise comparison.",
            }
        )

    if image_count != "" and int(image_count) <= 5:
        rows.append(
            {
                "analysis_unit": analysis_unit,
                "comparison": group_col,
                "test": "cluster_or_fixed_effect_model",
                "status": "not_run",
                "image_count": image_count,
                "notes": "Only five independent pilot images are available; cluster-robust or image fixed-effect model estimates would be fragile and are deferred.",
            }
        )
    return rows


def main() -> int:
    cell = read_dataset(CELL_DATA, "cell-level Part E dataset")
    cover = read_dataset(COVER_DATA, "cell-by-cover Part E dataset")
    rows: list[dict[str, object]] = []
    rows.extend(group_test(cell, "luhk_aggregated_class", "delta_t_mean_c", "cell"))
    rows.extend(group_test(cell, "image_id", "delta_t_mean_c", "cell"))
    rows.extend(group_test(cover, "physical_surface_cover_class", "class_delta_t_mean_c", "cell_by_surface_cover"))
    rows.extend(group_test(cover, "luhk_aggregated_class", "class_delta_t_mean_c", "cell_by_surface_cover"))
    rows.extend(group_test(cover, "physical_surface_cover_class", "class_delta_t_mean_c", "within_luhk_surface_cover"))
    result = pd.DataFrame(rows)
    write_csv(STATS_CSV, result)

    lines = [
        "# Part E Exploratory Statistical Tests",
        "",
        f"**Provisional-result rule:** {PROVISIONAL_NOTICE}",
        "",
        "These tests use LUHK-cell or cell-by-surface-cover observations, not individual thermal pixels. All inferential results are exploratory because only five pilot images are included.",
        "",
        f"- Results table: `{relative_posix(STATS_CSV)}`",
        "- Image fixed-effect or cluster-robust models are deferred when the five-image pilot size makes them unreliable.",
    ]
    write_markdown(STATS_MD, lines)
    print(f"Statistical-test rows: {len(result)}")
    print(f"Output: {relative_posix(STATS_CSV)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
