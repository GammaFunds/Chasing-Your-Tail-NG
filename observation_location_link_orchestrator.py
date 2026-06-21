"""Orchestration of bounded observation location-link planning and writing."""

from __future__ import annotations

from typing import Optional

from observation_contract import OperatorFixV1
from observation_correlation_planner import (
    plan_bounded_observation_location_links,
)
from observation_location_link_writer import (
    LocationLinkWriteSummaryV1,
    write_observation_location_link_candidates,
)
from observation_store import ObservationStore


def run_bounded_observation_location_link_correlation(
    *,
    store: ObservationStore,
    hmac_key: bytes,
    operator_fixes: tuple[OperatorFixV1, ...],
    max_delta_us: int,
    collection_session_id: Optional[str] = None,
) -> LocationLinkWriteSummaryV1:
    """Plan bounded link candidates and persist them explicitly."""

    candidates = plan_bounded_observation_location_links(
        store=store,
        hmac_key=hmac_key,
        operator_fixes=operator_fixes,
        max_delta_us=max_delta_us,
        collection_session_id=collection_session_id,
    )

    return write_observation_location_link_candidates(
        store=store,
        candidates=candidates,
    )


__all__ = [
    "run_bounded_observation_location_link_correlation",
]
