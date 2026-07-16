"""Explicit Part B finalization and per-group routing rules."""

from __future__ import annotations

from .models import (
    CoverageClass,
    FinalAlignmentStatus,
    ManualReviewStatus,
    PartBDecision,
    ProcessingRoute,
    ProcessingStatus,
    RouteDecision,
    SceneCorrespondence,
)


def finalize_part_b(decision: PartBDecision) -> PartBDecision:
    """Derive a final state without ever auto-accepting a score candidate."""
    if decision.manual_review_status == ManualReviewStatus.CANCELLED:
        decision.final_alignment_status = FinalAlignmentStatus.INDETERMINATE
    elif decision.manual_review_status == ManualReviewStatus.REJECTED:
        decision.final_alignment_status = FinalAlignmentStatus.REJECTED
    elif (
        decision.manual_review_status == ManualReviewStatus.ACCEPTED
        and decision.scene_correspondence == SceneCorrespondence.ACCEPTED
        and decision.coverage_class == CoverageClass.THERMAL_FULLY_SUPPORTED_BY_VISIBLE
    ):
        decision.final_alignment_status = FinalAlignmentStatus.ACCEPTED
    elif decision.scene_correspondence == SceneCorrespondence.REJECTED or decision.coverage_class in {
        CoverageClass.NO_USABLE_OVERLAP,
        CoverageClass.VISIBLE_INSIDE_THERMAL,
    }:
        decision.final_alignment_status = FinalAlignmentStatus.REJECTED
    else:
        decision.final_alignment_status = FinalAlignmentStatus.INDETERMINATE
    return decision


def route_group(decision: PartBDecision, *, thermal_valid: bool) -> RouteDecision:
    finalized = finalize_part_b(decision)
    if not thermal_valid:
        return RouteDecision(
            ProcessingRoute.FAILED,
            ProcessingStatus.FAILED,
            "missing_or_invalid_thermal_image",
        )
    if finalized.manual_review_status == ManualReviewStatus.CANCELLED:
        return RouteDecision(ProcessingRoute.CANCELLED, ProcessingStatus.CANCELLED, "part_b_review_cancelled")
    if finalized.final_alignment_status == FinalAlignmentStatus.ACCEPTED:
        return RouteDecision(ProcessingRoute.NORMAL_VT, ProcessingStatus.READY, "final_vt_alignment_accepted")
    return RouteDecision(
        ProcessingRoute.THERMAL_POLYGON,
        ProcessingStatus.READY,
        "vt_correspondence_not_accepted_valid_thermal_available",
    )
