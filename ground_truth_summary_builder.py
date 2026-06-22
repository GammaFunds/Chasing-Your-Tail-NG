"""Pure deterministic builder for completed GroundTruthExpectedSummaryV1."""

from __future__ import annotations

from ground_truth_scenario_contract import GroundTruthExpectedSummaryV1
from observation_contract import (
    ObservationEventV1,
    ObservationLocationLinkV1,
)
from observation_location_link_writer import LocationLinkWriteSummaryV1
from route_session_contract import (
    AnalysisSessionV1,
    CollectionSessionCloseV1,
    CollectionSessionV1,
    CollectionSourceMembershipCloseV1,
    CollectionSourceMembershipV1,
    RouteV1,
)
from synthetic_jsonl_adapter import ReplaySummaryV1


def _require_tuple_of(
    name: str,
    value: object,
    expected_type: type,
    id_attr: str,
) -> None:
    if type(value) is not tuple:
        raise TypeError(f"{name} must be a tuple")

    ids_seen: set = set()
    for i, element in enumerate(value):
        if type(element) is not expected_type:
            raise TypeError(
                f"{name}[{i}] must be "
                f"{expected_type.__name__}, "
                f"got {type(element).__name__}"
            )

        record_id = getattr(element, id_attr)
        if record_id in ids_seen:
            raise ValueError(
                f"duplicate {id_attr} in {name}: {record_id}"
            )
        ids_seen.add(record_id)


def build_completed_ground_truth_summary_v1(
    *,
    replay_summary: ReplaySummaryV1,
    location_link_write_summary: LocationLinkWriteSummaryV1,
    observations: tuple[ObservationEventV1, ...],
    location_links: tuple[ObservationLocationLinkV1, ...],
    collection_sessions: tuple[CollectionSessionV1, ...],
    source_memberships: tuple[CollectionSourceMembershipV1, ...],
    membership_closes: tuple[CollectionSourceMembershipCloseV1, ...],
    session_closes: tuple[CollectionSessionCloseV1, ...],
    routes: tuple[RouteV1, ...],
    analysis_sessions: tuple[AnalysisSessionV1, ...],
) -> GroundTruthExpectedSummaryV1:
    """Build a completed GroundTruthExpectedSummaryV1 from produced records.

    Canonical ordering rules
    ------------------------
    - Routes are ordered by route_id (lexicographic).
    - Location links are ordered by location_link_id (lexicographic).
    """
    if type(replay_summary) is not ReplaySummaryV1:
        raise TypeError("replay_summary must be ReplaySummaryV1")

    if type(location_link_write_summary) is not LocationLinkWriteSummaryV1:
        raise TypeError(
            "location_link_write_summary must be "
            "LocationLinkWriteSummaryV1"
        )

    _require_tuple_of(
        "observations",
        observations,
        ObservationEventV1,
        "observation_id",
    )
    _require_tuple_of(
        "location_links",
        location_links,
        ObservationLocationLinkV1,
        "location_link_id",
    )
    _require_tuple_of(
        "collection_sessions",
        collection_sessions,
        CollectionSessionV1,
        "collection_session_id",
    )
    _require_tuple_of(
        "source_memberships",
        source_memberships,
        CollectionSourceMembershipV1,
        "membership_id",
    )
    _require_tuple_of(
        "membership_closes",
        membership_closes,
        CollectionSourceMembershipCloseV1,
        "membership_close_id",
    )
    _require_tuple_of(
        "session_closes",
        session_closes,
        CollectionSessionCloseV1,
        "session_close_id",
    )
    _require_tuple_of("routes", routes, RouteV1, "route_id")
    _require_tuple_of(
        "analysis_sessions",
        analysis_sessions,
        AnalysisSessionV1,
        "analysis_session_id",
    )

    obs_ids = {ev.observation_id for ev in observations}

    for link in location_links:
        if link.observation_id not in obs_ids:
            raise ValueError(
                f"location_link {link.location_link_id} references "
                f"unknown observation_id: {link.observation_id}"
            )

    linked_obs_ids = {link.observation_id for link in location_links}
    unlinked_observation_count = sum(
        1 for ev in observations if ev.observation_id not in linked_obs_ids
    )

    sorted_routes = tuple(
        sorted(routes, key=lambda r: r.route_id)
    )
    sorted_links = tuple(
        sorted(location_links, key=lambda l: l.location_link_id)
    )

    route_point_counts = tuple(r.point_count for r in sorted_routes)
    route_source_time_bounds_us = tuple(
        (r.started_source_timestamp_us, r.ended_source_timestamp_us)
        for r in sorted_routes
    )
    source_to_fix_deltas_us = tuple(
        link.source_to_fix_delta_us for link in sorted_links
    )

    return GroundTruthExpectedSummaryV1(
        outcome="completed",
        rejection_stage=None,
        replay_summary=replay_summary,
        location_link_write_summary=location_link_write_summary,
        observation_event_count=len(observations),
        observation_location_link_count=len(location_links),
        collection_session_count=len(collection_sessions),
        source_membership_count=len(source_memberships),
        membership_close_count=len(membership_closes),
        session_close_count=len(session_closes),
        route_count=len(routes),
        analysis_session_count=len(analysis_sessions),
        unlinked_observation_count=unlinked_observation_count,
        route_point_counts=route_point_counts,
        route_source_time_bounds_us=route_source_time_bounds_us,
        source_to_fix_deltas_us=source_to_fix_deltas_us,
    )


__all__ = [
    "build_completed_ground_truth_summary_v1",
]
