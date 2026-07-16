"""Versioned workflow models shared by the local version 0.1 entry points."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


CANONICAL_SCHEMA_VERSION = "0.1.0"
PROCESSING_VERSION = "heat-index-urop-0.1"


class StrEnum(str, Enum):
    """A JSON-friendly enum with stable string values."""


class ValidationStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    CACHE_HIT = "cache_hit"
    READY = "ready"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INCOMPLETE = "incomplete"


class SceneCorrespondence(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    INDETERMINATE = "indeterminate"


class CoverageClass(StrEnum):
    THERMAL_FULLY_SUPPORTED_BY_VISIBLE = "thermal_fully_supported_by_visible"
    OVERLAP_ONLY = "overlap_only"
    VISIBLE_INSIDE_THERMAL = "visible_inside_thermal"
    NO_USABLE_OVERLAP = "no_usable_overlap"
    INDETERMINATE = "indeterminate"


class AutoCandidateStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    NOT_RUN = "not_run"


class ManualReviewStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NOT_REVIEWED = "not_reviewed"
    CANCELLED = "cancelled"


class FinalAlignmentStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    INDETERMINATE = "indeterminate"


class ProcessingRoute(StrEnum):
    CACHE = "cached_result"
    NORMAL_VT = "normal_visible_thermal"
    THERMAL_POLYGON = "thermal_polygon"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INCOMPLETE = "incomplete"


class SourceMethod(StrEnum):
    VISIBLE_REVIEW = "visible_review"
    THERMAL_POLYGON_USER_ANNOTATION = "thermal_polygon_user_annotation"
    UNKNOWN = "unknown"


class QAStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass(slots=True)
class GroupInput:
    group_id: str
    visible_path: str
    thermal_path: str
    dataset_id: str = ""


@dataclass(slots=True)
class ValidationRecord:
    group_id: str
    pair_id: str
    image_id: str
    dataset_id: str
    visible_path: str
    thermal_path: str
    capture_time: str = ""
    session: str = ""
    altitude_m: float | None = None
    visible_camera_metadata: dict[str, Any] = field(default_factory=dict)
    thermal_camera_metadata: dict[str, Any] = field(default_factory=dict)
    validation_status: ValidationStatus = ValidationStatus.FAIL
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    processing_status: ProcessingStatus = ProcessingStatus.PENDING
    thermal_valid: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _enum_values(asdict(self))


@dataclass(slots=True)
class PartBDecision:
    group_id: str
    scene_correspondence: SceneCorrespondence = SceneCorrespondence.INDETERMINATE
    coverage_class: CoverageClass = CoverageClass.INDETERMINATE
    auto_candidate_status: AutoCandidateStatus = AutoCandidateStatus.NOT_RUN
    manual_review_status: ManualReviewStatus = ManualReviewStatus.NOT_REVIEWED
    final_alignment_status: FinalAlignmentStatus = FinalAlignmentStatus.INDETERMINATE
    candidate_transform_path: str = ""
    review_evidence_path: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _enum_values(asdict(self))


@dataclass(slots=True)
class ArtifactReference:
    path: str
    sha256: str = ""
    dtype: str = ""
    shape: list[int] = field(default_factory=list)


@dataclass(slots=True)
class CanonicalManifest:
    image_id: str
    group_id: str
    pair_id: str
    dataset_id: str
    visible_path: str
    thermal_path: str
    processing_route: ProcessingRoute
    source_method: SourceMethod
    image_height: int
    image_width: int
    processing_status: ProcessingStatus
    qa_status: QAStatus
    review_status: ManualReviewStatus
    schema_version: str = CANONICAL_SCHEMA_VERSION
    processing_version: str = PROCESSING_VERSION
    configuration_hash: str = ""
    source_file_hashes: dict[str, str] = field(default_factory=dict)
    validation_status: str = ""
    scene_correspondence: str = SceneCorrespondence.INDETERMINATE.value
    coverage_class: str = CoverageClass.INDETERMINATE.value
    label_provenance: str = SourceMethod.UNKNOWN.value
    surface_cover_class_id: int | None = None
    surface_cover_category: str | None = None
    target_name: str | None = None
    polygon_coordinates: list[list[float]] = field(default_factory=list)
    known_pixel_count: int = 0
    unknown_pixel_count: int = 0
    annotation_source: str = ""
    reviewer_confidence: str = ""
    temperature_metadata: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, ArtifactReference] = field(default_factory=dict)
    exclusions: list[str] = field(default_factory=list)
    notes: str = ""
    created_at_utc: str = ""

    def validate(self, *, require_artifacts: bool = True) -> None:
        if self.schema_version != CANONICAL_SCHEMA_VERSION:
            raise ValueError(f"Unsupported canonical schema version: {self.schema_version}")
        if self.image_height <= 0 or self.image_width <= 0:
            raise ValueError("Canonical image dimensions must be positive.")
        total = self.image_height * self.image_width
        if self.known_pixel_count < 0 or self.unknown_pixel_count < 0:
            raise ValueError("Known and unknown pixel counts cannot be negative.")
        if self.known_pixel_count + self.unknown_pixel_count != total:
            raise ValueError("Known and unknown pixel counts must cover the native thermal grid.")
        if require_artifacts and "temperature" not in self.artifacts:
            raise ValueError("A successful canonical result requires a temperature artifact.")
        if self.processing_status == ProcessingStatus.SUCCESS and self.qa_status == QAStatus.FAIL:
            raise ValueError("A failed-QA result cannot have processing_status=success.")
        if self.processing_route == ProcessingRoute.THERMAL_POLYGON:
            if self.review_status != ManualReviewStatus.ACCEPTED:
                raise ValueError("A successful polygon canonical result requires an accepted annotation.")
            if not self.surface_cover_category:
                raise ValueError("A polygon result requires a user-specified surface-cover category.")
            if self.known_pixel_count <= 0:
                raise ValueError("An accepted polygon must contain at least one known target pixel.")
            if len(self.polygon_coordinates) < 3:
                raise ValueError("An accepted polygon requires at least three coordinates.")
            if require_artifacts and not {"surface_cover_labels", "known_mask"}.issubset(self.artifacts):
                raise ValueError("A polygon result requires surface-cover labels and a known mask.")

    def to_dict(self) -> dict[str, Any]:
        return _enum_values(asdict(self))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CanonicalManifest":
        data = dict(payload)
        data["processing_route"] = ProcessingRoute(data["processing_route"])
        data["source_method"] = SourceMethod(data["source_method"])
        data["processing_status"] = ProcessingStatus(data["processing_status"])
        data["qa_status"] = QAStatus(data["qa_status"])
        data["review_status"] = ManualReviewStatus(data["review_status"])
        data["artifacts"] = {
            key: value if isinstance(value, ArtifactReference) else ArtifactReference(**value)
            for key, value in data.get("artifacts", {}).items()
        }
        return cls(**data)


@dataclass(slots=True)
class RouteDecision:
    route: ProcessingRoute
    status: ProcessingStatus
    reason: str


@dataclass(slots=True)
class GroupRunSummary:
    group_id: str
    image_id: str
    route: ProcessingRoute
    status: ProcessingStatus
    reason: str = ""
    canonical_manifest_path: str = ""
    cache_hit: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _enum_values(asdict(self))


def _enum_values(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {key: _enum_values(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_enum_values(item) for item in value]
    return value
