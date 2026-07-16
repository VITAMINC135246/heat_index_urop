"""Load explicit Part B review decisions and verified-pilot evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .models import (
    AutoCandidateStatus,
    CoverageClass,
    ManualReviewStatus,
    PartBDecision,
    SceneCorrespondence,
)
from .routing import finalize_part_b


def decision_from_dict(group_id: str, payload: dict[str, Any]) -> PartBDecision:
    decision = PartBDecision(
        group_id=group_id,
        scene_correspondence=SceneCorrespondence(payload.get("scene_correspondence", "indeterminate")),
        coverage_class=CoverageClass(payload.get("coverage_class", "indeterminate")),
        auto_candidate_status=AutoCandidateStatus(payload.get("auto_candidate_status", "not_run")),
        manual_review_status=ManualReviewStatus(payload.get("manual_review_status", "not_reviewed")),
        candidate_transform_path=str(payload.get("candidate_transform_path", "")),
        review_evidence_path=str(payload.get("review_evidence_path", "")),
        notes=str(payload.get("notes", "")),
    )
    return finalize_part_b(decision)


def load_review_decisions(path: Path | None) -> dict[str, PartBDecision]:
    if path is None:
        return {}
    if not path.is_file():
        raise FileNotFoundError(f"Part B review decision file does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("decisions", payload)
    if not isinstance(rows, dict):
        raise ValueError("Part B review file must contain an object keyed by group_id or image_id.")
    return {str(key): decision_from_dict(str(key), value) for key, value in rows.items()}


def verified_pilot_decisions(project_root: Path) -> dict[str, PartBDecision]:
    """Use downstream reviewed artifacts—not an auto score—as pilot evidence."""
    pairs_path = project_root / "data" / "metadata" / "part_b_pilot_pairs.xlsx"
    masks_path = project_root / "outputs" / "part_c" / "summaries" / "part_c_final_mask_manifest.xlsx"
    temperatures_path = (
        project_root / "outputs" / "part_d" / "summaries" / "part_d_tat3_parameter_temperature_extraction_summary.csv"
    )
    if not all(path.is_file() for path in (pairs_path, masks_path, temperatures_path)):
        return {}
    pairs = pd.read_excel(pairs_path)
    masks = pd.read_excel(masks_path)
    temperatures = pd.read_csv(temperatures_path, keep_default_na=False)
    usable_masks = set(
        masks.loc[masks["usable_for_part_d"].astype(str).str.casefold().eq("yes"), "image_id"].astype(str)
    )
    successful_temperatures = set(
        temperatures.loc[temperatures["extraction_status"].astype(str).str.casefold().eq("success"), "image_id"].astype(str)
    )
    decisions: dict[str, PartBDecision] = {}
    for row in pairs.itertuples(index=False):
        image_id = str(row.image_id)
        if image_id not in usable_masks or image_id not in successful_temperatures:
            continue
        decision = PartBDecision(
            group_id=str(row.pair_id),
            scene_correspondence=SceneCorrespondence.ACCEPTED,
            coverage_class=CoverageClass.THERMAL_FULLY_SUPPORTED_BY_VISIBLE,
            auto_candidate_status=AutoCandidateStatus.AVAILABLE,
            manual_review_status=ManualReviewStatus.ACCEPTED,
            review_evidence_path="outputs/part_c/summaries/part_c_final_mask_manifest.xlsx",
            notes=(
                "Verified legacy pilot: acceptance derives from the downstream manually reviewed Part C mask "
                "and successful Part D grid compatibility, not from the cross-modal score alone."
            ),
        )
        decisions[image_id] = finalize_part_b(decision)
        decisions[str(row.pair_id)] = decisions[image_id]
    return decisions


def resolve_decision(
    *,
    group_id: str,
    image_id: str,
    explicit: dict[str, PartBDecision],
    verified_pilot: dict[str, PartBDecision],
) -> PartBDecision:
    source = explicit.get(group_id) or explicit.get(image_id) or verified_pilot.get(group_id) or verified_pilot.get(image_id)
    if source is None:
        return PartBDecision(group_id=group_id)
    return PartBDecision(
        group_id=group_id,
        scene_correspondence=source.scene_correspondence,
        coverage_class=source.coverage_class,
        auto_candidate_status=source.auto_candidate_status,
        manual_review_status=source.manual_review_status,
        final_alignment_status=source.final_alignment_status,
        candidate_transform_path=source.candidate_transform_path,
        review_evidence_path=source.review_evidence_path,
        notes=source.notes,
    )


def accepted_alignment_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Return final-accepted rows while reading frozen legacy pilot summaries."""
    if "final_alignment_status" in frame.columns:
        return frame.loc[
            frame["final_alignment_status"].astype(str).str.casefold().eq("accepted")
        ].copy()
    if "alignment_quality" in frame.columns:
        return frame.loc[
            frame["alignment_quality"].astype(str).str.casefold().eq("acceptable")
        ].copy()
    return frame.iloc[0:0].copy()
