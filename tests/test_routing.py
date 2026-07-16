from __future__ import annotations

import unittest

import pandas as pd

from scripts.workflow.models import (
    CoverageClass,
    ManualReviewStatus,
    PartBDecision,
    ProcessingRoute,
    ProcessingStatus,
    SceneCorrespondence,
)
from scripts.workflow.routing import finalize_part_b, route_group
from scripts.workflow.part_b_review import accepted_alignment_rows


class RoutingTests(unittest.TestCase):
    def test_auto_candidate_never_implies_acceptance(self) -> None:
        decision = PartBDecision(
            group_id="g1",
            scene_correspondence=SceneCorrespondence.ACCEPTED,
            coverage_class=CoverageClass.THERMAL_FULLY_SUPPORTED_BY_VISIBLE,
        )
        finalized = finalize_part_b(decision)
        self.assertEqual(finalized.final_alignment_status.value, "indeterminate")
        route = route_group(decision, thermal_valid=True)
        self.assertEqual(route.route, ProcessingRoute.THERMAL_POLYGON)

    def test_manual_full_coverage_acceptance_enters_normal_route(self) -> None:
        decision = PartBDecision(
            group_id="g1",
            scene_correspondence=SceneCorrespondence.ACCEPTED,
            coverage_class=CoverageClass.THERMAL_FULLY_SUPPORTED_BY_VISIBLE,
            manual_review_status=ManualReviewStatus.ACCEPTED,
        )
        route = route_group(decision, thermal_valid=True)
        self.assertEqual(route.route, ProcessingRoute.NORMAL_VT)
        self.assertEqual(route.status, ProcessingStatus.READY)

    def test_unusable_visible_with_valid_thermal_enters_polygon(self) -> None:
        decision = PartBDecision(
            group_id="g1",
            scene_correspondence=SceneCorrespondence.REJECTED,
            coverage_class=CoverageClass.NO_USABLE_OVERLAP,
            manual_review_status=ManualReviewStatus.REJECTED,
        )
        self.assertEqual(route_group(decision, thermal_valid=True).route, ProcessingRoute.THERMAL_POLYGON)

    def test_missing_thermal_fails(self) -> None:
        route = route_group(PartBDecision(group_id="g1"), thermal_valid=False)
        self.assertEqual(route.route, ProcessingRoute.FAILED)
        self.assertEqual(route.reason, "missing_or_invalid_thermal_image")

    def test_cancelled_part_b_does_not_enter_polygon(self) -> None:
        decision = PartBDecision(group_id="g1", manual_review_status=ManualReviewStatus.CANCELLED)
        route = route_group(decision, thermal_valid=True)
        self.assertEqual(route.route, ProcessingRoute.CANCELLED)

    def test_final_status_takes_precedence_over_candidate_quality(self) -> None:
        rows = pd.DataFrame(
            [
                {"image_id": "rejected", "alignment_quality": "acceptable", "final_alignment_status": "rejected"},
                {"image_id": "accepted", "alignment_quality": "poor", "final_alignment_status": "accepted"},
            ]
        )
        accepted = accepted_alignment_rows(rows)
        self.assertEqual(accepted["image_id"].tolist(), ["accepted"])


if __name__ == "__main__":
    unittest.main()
