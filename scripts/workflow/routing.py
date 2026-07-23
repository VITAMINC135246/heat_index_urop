"""Version 0.2 route-state transitions with explicit review boundaries."""

from __future__ import annotations

from .models import (
    ContentTriageState,
    CoverageClass,
    FinalAlignmentStatus,
    ManualReviewStatus,
    PartB0Result,
    PartBDecision,
    ProcessingRoute,
    ProcessingStatus,
    RouteDecision,
    SceneCorrespondence,
    ValidationRecord,
)


def finalize_part_b(decision: PartBDecision) -> PartBDecision:
    """Derive the final state without accepting automatic or GCP evidence."""
    if decision.manual_review_status == ManualReviewStatus.CANCELLED:
        decision.final_alignment_status = FinalAlignmentStatus.INDETERMINATE
        decision.routing_status = "cancelled"
    elif decision.manual_review_status == ManualReviewStatus.REJECTED:
        decision.final_alignment_status = FinalAlignmentStatus.REJECTED
        decision.routing_status = "thermal_polygon"
    elif (
        decision.manual_review_status == ManualReviewStatus.ACCEPTED
        and decision.scene_correspondence == SceneCorrespondence.ACCEPTED
        and decision.coverage_class == CoverageClass.THERMAL_FULLY_SUPPORTED_BY_VISIBLE
    ):
        decision.final_alignment_status = FinalAlignmentStatus.ACCEPTED
        decision.routing_status = "normal_visible_thermal"
    elif decision.scene_correspondence == SceneCorrespondence.REJECTED or decision.coverage_class in {
        CoverageClass.NO_USABLE_OVERLAP,
        CoverageClass.VISIBLE_INSIDE_THERMAL,
    }:
        decision.final_alignment_status = FinalAlignmentStatus.REJECTED
        decision.routing_status = "thermal_polygon"
    else:
        decision.final_alignment_status = FinalAlignmentStatus.INDETERMINATE
        decision.routing_status = "awaiting_part_b_review"
    return decision


def route_after_part_a(record: ValidationRecord) -> RouteDecision:
    if not record.thermal_valid or record.fatal_errors:
        return RouteDecision(ProcessingRoute.FAILED, ProcessingStatus.FAILED, "fatal_part_a_thermal_validation")
    if not record.visible_valid or record.visible_errors:
        return RouteDecision(ProcessingRoute.THERMAL_POLYGON, ProcessingStatus.READY, "visible_unusable_thermal_valid")
    return RouteDecision(ProcessingRoute.INCOMPLETE, ProcessingStatus.READY, "run_part_b0")


def route_after_part_b0(result: PartB0Result) -> RouteDecision:
    if result.manual_review_status == ManualReviewStatus.CANCELLED:
        return RouteDecision(ProcessingRoute.CANCELLED, ProcessingStatus.CANCELLED, "part_b0_review_cancelled")
    if result.manual_review_status == ManualReviewStatus.REJECTED:
        return RouteDecision(ProcessingRoute.THERMAL_POLYGON, ProcessingStatus.READY, "part_b0_match_rejected")
    if result.manual_review_status == ManualReviewStatus.ACCEPTED:
        return RouteDecision(ProcessingRoute.INCOMPLETE, ProcessingStatus.READY, "part_b0_match_manually_accepted_run_full_part_b")
    if result.triage_state == ContentTriageState.CONTENT_MISMATCH_CANDIDATE:
        return RouteDecision(ProcessingRoute.THERMAL_POLYGON, ProcessingStatus.READY, "part_b0_content_mismatch_candidate")
    if result.triage_state == ContentTriageState.NEEDS_MANUAL_REVIEW:
        return RouteDecision(
            ProcessingRoute.AWAITING_REVIEW,
            ProcessingStatus.AWAITING_PART_B0_REVIEW,
            "part_b0_manual_review_required",
        )
    return RouteDecision(ProcessingRoute.INCOMPLETE, ProcessingStatus.READY, "part_b0_match_candidate_run_full_part_b")


def route_group(decision: PartBDecision, *, thermal_valid: bool) -> RouteDecision:
    finalized = finalize_part_b(decision)
    if not thermal_valid:
        return RouteDecision(ProcessingRoute.FAILED, ProcessingStatus.FAILED, "missing_or_invalid_thermal_image")
    if finalized.manual_review_status == ManualReviewStatus.CANCELLED:
        return RouteDecision(ProcessingRoute.CANCELLED, ProcessingStatus.CANCELLED, "part_b_review_cancelled")
    if finalized.final_alignment_status == FinalAlignmentStatus.ACCEPTED:
        return RouteDecision(ProcessingRoute.NORMAL_VT, ProcessingStatus.READY, "final_vt_alignment_accepted")
    if finalized.final_alignment_status == FinalAlignmentStatus.REJECTED:
        return RouteDecision(ProcessingRoute.THERMAL_POLYGON, ProcessingStatus.READY, "final_vt_alignment_rejected")
    return RouteDecision(
        ProcessingRoute.AWAITING_REVIEW,
        ProcessingStatus.AWAITING_PART_B_REVIEW,
        "final_vt_alignment_not_reviewed_or_indeterminate",
    )
