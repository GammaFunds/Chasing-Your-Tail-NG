"""Immutable ground-truth scenario manifest and expected summary v1."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional

from observation_location_link_writer import LocationLinkWriteSummaryV1
from synthetic_jsonl_adapter import ReplaySummaryV1


SCHEMA_VERSION_V1 = "1.0"
RECORD_KIND = "ground_truth_scenario"

REJECTION_STAGES = frozenset({
    "observation_decode",
    "observation_write",
    "operator_fix_decode",
    "correlation_plan",
    "location_link_write",
    "lifecycle_validation",
    "route_construction",
    "result_validation",
})

_SCENARIO_ID_RE = re.compile(
    r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+$"
)
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_TAG_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
_VALID_OUTCOMES = frozenset({"completed", "rejected"})


def _require_text(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")

    if not value or value != value.strip():
        raise ValueError(
            f"{name} must be a non-empty canonical string"
        )

    return value


def _require_non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")

    return value


def _validate_tags(tags: object) -> tuple[str, ...]:
    if not isinstance(tags, tuple):
        raise ValueError("tags must be a tuple")

    for i, tag in enumerate(tags):
        if not isinstance(tag, str):
            raise ValueError(f"tags[{i}] must be a string")

        if not tag:
            raise ValueError(f"tags[{i}] must be non-empty")

        if tag != tag.strip().lower():
            raise ValueError(f"tags[{i}] must be lowercase")

        if _TAG_RE.fullmatch(tag) is None:
            raise ValueError(f"tags[{i}] contains invalid characters")

    if len(tags) != len(set(tags)):
        raise ValueError("tags must not contain duplicates")

    if list(tags) != sorted(tags):
        raise ValueError("tags must be sorted")

    return tags


def _validate_route_source_time_bounds(
    bounds: tuple,
) -> None:
    if not isinstance(bounds, tuple):
        raise ValueError(
            "route_source_time_bounds_us must be a tuple"
        )

    for i, bound in enumerate(bounds):
        if not isinstance(bound, tuple) or len(bound) != 2:
            raise ValueError(
                f"route_source_time_bounds_us[{i}] must be a 2-tuple"
            )

        start, end = bound
        _require_non_negative_int(
            f"route_source_time_bounds_us[{i}][0]", start
        )
        _require_non_negative_int(
            f"route_source_time_bounds_us[{i}][1]", end
        )

        if start > end:
            raise ValueError(
                f"route_source_time_bounds_us[{i}][0] must be "
                f"<= route_source_time_bounds_us[{i}][1]"
            )


@dataclass(frozen=True)
class GroundTruthExpectedSummaryV1:
    """Content-free expected summary for a ground-truth scenario."""

    outcome: str
    rejection_stage: Optional[str]
    replay_summary: ReplaySummaryV1
    location_link_write_summary: LocationLinkWriteSummaryV1
    observation_event_count: int
    observation_location_link_count: int
    collection_session_count: int
    source_membership_count: int
    membership_close_count: int
    session_close_count: int
    route_count: int
    analysis_session_count: int
    unlinked_observation_count: int
    route_point_counts: tuple[int, ...]
    route_source_time_bounds_us: tuple[tuple[int, int], ...]
    source_to_fix_deltas_us: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.outcome not in _VALID_OUTCOMES:
            raise ValueError(
                'outcome must be "completed" or "rejected"'
            )

        if self.outcome == "completed":
            if self.rejection_stage is not None:
                raise ValueError(
                    "completed outcome must not have a rejection_stage"
                )
        else:
            if self.rejection_stage not in REJECTION_STAGES:
                raise ValueError(
                    f"rejection_stage must be one of "
                    f"{sorted(REJECTION_STAGES)}"
                )

        if not isinstance(self.replay_summary, ReplaySummaryV1):
            raise ValueError("replay_summary must be ReplaySummaryV1")

        if not isinstance(
            self.location_link_write_summary,
            LocationLinkWriteSummaryV1,
        ):
            raise ValueError(
                "location_link_write_summary must be "
                "LocationLinkWriteSummaryV1"
            )

        for count_name in (
            "observation_event_count",
            "observation_location_link_count",
            "collection_session_count",
            "source_membership_count",
            "membership_close_count",
            "session_close_count",
            "route_count",
            "analysis_session_count",
            "unlinked_observation_count",
        ):
            _require_non_negative_int(
                count_name, getattr(self, count_name)
            )

        if self.unlinked_observation_count > self.observation_event_count:
            raise ValueError(
                "unlinked_observation_count must not exceed "
                "observation_event_count"
            )

        if not isinstance(self.route_point_counts, tuple):
            raise ValueError("route_point_counts must be a tuple")

        for i, count in enumerate(self.route_point_counts):
            if (
                isinstance(count, bool)
                or not isinstance(count, int)
                or count < 1
            ):
                raise ValueError(
                    f"route_point_counts[{i}] must be a positive integer"
                )

        _validate_route_source_time_bounds(
            self.route_source_time_bounds_us
        )

        if len(self.route_point_counts) != self.route_count:
            raise ValueError(
                "len(route_point_counts) must equal route_count"
            )

        if len(self.route_source_time_bounds_us) != self.route_count:
            raise ValueError(
                "len(route_source_time_bounds_us) must equal route_count"
            )

        if not isinstance(self.source_to_fix_deltas_us, tuple):
            raise ValueError(
                "source_to_fix_deltas_us must be a tuple"
            )

        for i, delta in enumerate(self.source_to_fix_deltas_us):
            if isinstance(delta, bool) or not isinstance(delta, int):
                raise ValueError(
                    f"source_to_fix_deltas_us[{i}] must be an integer"
                )

        if (
            len(self.source_to_fix_deltas_us)
            != self.observation_location_link_count
        ):
            raise ValueError(
                "len(source_to_fix_deltas_us) must equal "
                "observation_location_link_count"
            )


@dataclass(frozen=True)
class GroundTruthScenarioManifestV1:
    """Immutable ground-truth scenario manifest version 1.0."""

    schema_version: str
    record_kind: str
    scenario_id: str
    scenario_version: str
    scenario_label: str
    tags: tuple[str, ...]
    input_manifest_digest: str
    expected_summary: GroundTruthExpectedSummaryV1

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION_V1:
            raise ValueError('schema_version must be exactly "1.0"')

        if self.record_kind != RECORD_KIND:
            raise ValueError(
                'record_kind must be exactly '
                '"ground_truth_scenario"'
            )

        if _SCENARIO_ID_RE.fullmatch(self.scenario_id) is None:
            raise ValueError(
                "scenario_id must be a lowercase namespaced value"
            )

        _require_text("scenario_version", self.scenario_version)
        _require_text("scenario_label", self.scenario_label)

        _validate_tags(self.tags)

        if _DIGEST_RE.fullmatch(self.input_manifest_digest) is None:
            raise ValueError(
                "input_manifest_digest must be a "
                "64-character hex digest"
            )

        if not isinstance(
            self.expected_summary, GroundTruthExpectedSummaryV1
        ):
            raise ValueError(
                "expected_summary must be "
                "GroundTruthExpectedSummaryV1"
            )


__all__ = [
    "GroundTruthExpectedSummaryV1",
    "GroundTruthScenarioManifestV1",
    "REJECTION_STAGES",
    "RECORD_KIND",
    "SCHEMA_VERSION_V1",
]
