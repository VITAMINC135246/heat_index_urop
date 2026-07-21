"""Versioned workflow contracts shared by the persistent v0.3 entry points."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


CANONICAL_SCHEMA_VERSION = "0.2.0"
LEGACY_CANONICAL_SCHEMA_VERSION = "0.1.0"
PROCESSING_VERSION = "heat-index-urop-0.3.1"


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
    AWAITING_PART_B0_REVIEW = "awaiting_part_b0_review"
    AWAITING_PART_B_REVIEW = "awaiting_part_b_review"
    AWAITING_PART_C_REVIEW = "awaiting_part_c_review"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXCLUDED = "excluded"
    INCOMPLETE = "incomplete"


class ContentTriageState(StrEnum):
    CONTENT_MATCH_CANDIDATE = "content_match_candidate"
    CONTENT_MISMATCH_CANDIDATE = "content_mismatch_candidate"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"
    NOT_RUN = "not_run"


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
    AWAITING_REVIEW = "awaiting_review"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXCLUDED = "excluded"
    INCOMPLETE = "incomplete"


class SourceMethod(StrEnum):
    VISIBLE_REVIEW = "visible_review"
    THERMAL_POLYGON_USER_ANNOTATION = "thermal_polygon_user_annotation"
    TAT3_MANUAL_MEASUREMENT = "tat3_manual_measurement"
    UNKNOWN = "unknown"


class MeasurementType(StrEnum):
    MANUAL_TAT3_POINT = "manual_tat3_point"
    MANUAL_TAT3_REGION = "manual_tat3_region"
    FULL_THERMAL_PIXEL = "full_thermal_pixel"
    POLYGON_SELECTED_THERMAL_PIXEL = "polygon_selected_thermal_pixel"


class LUHKProvenance(StrEnum):
    OFFICIAL_LOOKUP = "official_luhk_lookup"
    USER_SUPPLIED = "user_supplied_luhk"
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
    metadata_record: dict[str, Any] = field(default_factory=dict)


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
    gps_latitude: float | None = None
    gps_longitude: float | None = None
    camera_model: str = ""
    focal_length_mm: float | None = None
    camera_profile: dict[str, Any] = field(default_factory=dict)
    metadata_source: str = ""
    visible_camera_metadata: dict[str, Any] = field(default_factory=dict)
    thermal_camera_metadata: dict[str, Any] = field(default_factory=dict)
    validation_status: ValidationStatus = ValidationStatus.FAIL
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    fatal_errors: list[str] = field(default_factory=list)
    visible_errors: list[str] = field(default_factory=list)
    pairing_uncertain: bool = False
    visible_valid: bool = False
    thermal_valid: bool = False
    temperature_grid_compatible: bool | None = None
    processing_status: ProcessingStatus = ProcessingStatus.PENDING

    def to_dict(self) -> dict[str, Any]:
        return _enum_values(asdict(self))


@dataclass(slots=True)
class PartB0Result:
    group_id: str
    image_id: str
    triage_state: ContentTriageState
    algorithm_version: str = "part-b0-structural-ensemble-0.2.0"
    candidate_crop: list[int] = field(default_factory=list)
    candidate_transform: list[list[float]] = field(default_factory=list)
    feature_scores: dict[str, float] = field(default_factory=dict)
    overall_score: float = 0.0
    thresholds: dict[str, float] = field(default_factory=dict)
    confidence: str = "low"
    diagnostic_paths: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    manual_review_status: ManualReviewStatus = ManualReviewStatus.NOT_REVIEWED

    def to_dict(self) -> dict[str, Any]:
        return _enum_values(asdict(self))


@dataclass(slots=True)
class PartBDecision:
    group_id: str
    filename_time_pairing: str = "indeterminate"
    part_b0_state: ContentTriageState = ContentTriageState.NOT_RUN
    scene_correspondence: SceneCorrespondence = SceneCorrespondence.INDETERMINATE
    coverage_class: CoverageClass = CoverageClass.INDETERMINATE
    auto_candidate_status: AutoCandidateStatus = AutoCandidateStatus.NOT_RUN
    gcp_status: str = "not_run"
    manual_review_status: ManualReviewStatus = ManualReviewStatus.NOT_REVIEWED
    final_alignment_status: FinalAlignmentStatus = FinalAlignmentStatus.INDETERMINATE
    routing_status: str = "awaiting_review"
    candidate_transform_path: str = ""
    review_evidence_path: str = ""
    candidate_transform: list[list[float]] = field(default_factory=list)
    candidate_crop: list[int] = field(default_factory=list)
    candidate_scores: dict[str, Any] = field(default_factory=dict)
    gcp_evidence: dict[str, Any] = field(default_factory=dict)
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
    measurement_type: MeasurementType = MeasurementType.FULL_THERMAL_PIXEL
    selection_scope: str = "full_native_thermal_grid"
    configuration_hash: str = ""
    dependency_fingerprints: dict[str, str] = field(default_factory=dict)
    source_file_hashes: dict[str, str] = field(default_factory=dict)
    derived_input_hashes: dict[str, str] = field(default_factory=dict)
    tool_identity: dict[str, str] = field(default_factory=dict)
    part_a: dict[str, Any] = field(default_factory=dict)
    part_b0: dict[str, Any] = field(default_factory=dict)
    part_b: dict[str, Any] = field(default_factory=dict)
    validation_status: str = ""
    scene_correspondence: str = SceneCorrespondence.INDETERMINATE.value
    coverage_class: str = CoverageClass.INDETERMINATE.value
    label_provenance: str = SourceMethod.UNKNOWN.value
    surface_cover_provenance: str = SourceMethod.UNKNOWN.value
    luhk_provenance: str = LUHKProvenance.UNKNOWN.value
    luhk_category: str | None = None
    luhk_code: str | None = None
    surface_cover_class_id: int | None = None
    surface_cover_category: str | None = None
    target_id: str | None = None
    target_name: str | None = None
    capture_timezone: str = ""
    polygon_coordinates: list[list[float]] = field(default_factory=list)
    known_pixel_count: int = 0
    unknown_pixel_count: int = 0
    target_pixel_count: int = 0
    annotation_source: str = ""
    annotation_review: dict[str, Any] = field(default_factory=dict)
    reviewer_confidence: str = ""
    temperature_source: str = ""
    temperature_metadata: dict[str, Any] = field(default_factory=dict)
    ambient_metadata: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, ArtifactReference] = field(default_factory=dict)
    exclusions: list[str] = field(default_factory=list)
    notes: str = ""
    created_at_utc: str = ""

    def validate(self, *, require_artifacts: bool = True, allow_legacy: bool = False) -> None:
        supported = {CANONICAL_SCHEMA_VERSION}
        if allow_legacy:
            supported.add(LEGACY_CANONICAL_SCHEMA_VERSION)
        if self.schema_version not in supported:
            raise ValueError(f"Unsupported canonical schema version: {self.schema_version}")
        if self.image_height <= 0 or self.image_width <= 0:
            raise ValueError("Canonical image dimensions must be positive.")
        total = self.image_height * self.image_width
        if self.known_pixel_count < 0 or self.unknown_pixel_count < 0:
            raise ValueError("Known and unknown pixel counts cannot be negative.")
        if self.known_pixel_count + self.unknown_pixel_count != total:
            raise ValueError("Known and unknown pixel counts must cover the native thermal grid.")
        if require_artifacts and "temperature" not in self.artifacts:
            raise ValueError("A canonical result requires a temperature artifact.")
        if self.processing_status == ProcessingStatus.SUCCESS and self.qa_status == QAStatus.FAIL:
            raise ValueError("A failed-QA result cannot have processing_status=success.")
        if self.processing_route == ProcessingRoute.NORMAL_VT:
            if self.measurement_type != MeasurementType.FULL_THERMAL_PIXEL:
                raise ValueError("The normal route requires measurement_type=full_thermal_pixel.")
            if self.surface_cover_provenance != SourceMethod.VISIBLE_REVIEW.value:
                raise ValueError("The normal route requires visible_review surface-cover provenance.")
        if self.processing_route == ProcessingRoute.THERMAL_POLYGON:
            if self.measurement_type != MeasurementType.POLYGON_SELECTED_THERMAL_PIXEL:
                raise ValueError("The polygon route requires polygon_selected_thermal_pixel measurements.")
            if self.review_status != ManualReviewStatus.ACCEPTED:
                raise ValueError("A successful polygon canonical result requires an accepted annotation.")
            if not self.surface_cover_category or not self.luhk_category:
                raise ValueError("A polygon result requires surface-cover and LUHK context.")
            if self.luhk_provenance not in {item.value for item in LUHKProvenance}:
                raise ValueError("Polygon LUHK provenance is invalid.")
            if self.known_pixel_count <= 0 or self.target_pixel_count <= 0:
                raise ValueError("An accepted polygon must contain target pixels.")
            if len(self.polygon_coordinates) < 3:
                raise ValueError("An accepted polygon requires at least three coordinates.")
            required = {"surface_cover_labels", "surface_cover_known_mask", "target_mask", "luhk_labels", "luhk_known_mask"}
            if require_artifacts and not required.issubset(self.artifacts):
                raise ValueError(f"A polygon result requires artifacts: {sorted(required)}")

    def to_dict(self) -> dict[str, Any]:
        return _enum_values(asdict(self))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CanonicalManifest":
        data = dict(payload)
        legacy = str(data.get("schema_version", "")) == LEGACY_CANONICAL_SCHEMA_VERSION
        route = ProcessingRoute(data["processing_route"])
        data["processing_route"] = route
        data["source_method"] = SourceMethod(data["source_method"])
        data["processing_status"] = ProcessingStatus(data["processing_status"])
        data["qa_status"] = QAStatus(data["qa_status"])
        data["review_status"] = ManualReviewStatus(data["review_status"])
        if "measurement_type" in data:
            data["measurement_type"] = MeasurementType(data["measurement_type"])
        else:
            data["measurement_type"] = (
                MeasurementType.POLYGON_SELECTED_THERMAL_PIXEL
                if route == ProcessingRoute.THERMAL_POLYGON
                else MeasurementType.FULL_THERMAL_PIXEL
            )
        if legacy:
            data.setdefault("processing_version", "heat-index-urop-0.1")
            data.setdefault("surface_cover_provenance", str(data.get("label_provenance", "unknown")))
            data.setdefault("selection_scope", "polygon_target" if route == ProcessingRoute.THERMAL_POLYGON else "full_native_thermal_grid")
            data.setdefault("target_pixel_count", int(data.get("known_pixel_count", 0)))
        data["artifacts"] = {
            key: value if isinstance(value, ArtifactReference) else ArtifactReference(**value)
            for key, value in data.get("artifacts", {}).items()
        }
        allowed = set(cls.__dataclass_fields__)
        return cls(**{key: value for key, value in data.items() if key in allowed})


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
    part_a_record_path: str = ""
    part_b0_record_path: str = ""
    part_b_record_path: str = ""
    exclusions: list[str] = field(default_factory=list)

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
