"""Read-only planning of bounded observation location-link candidates."""

from __future__ import annotations

from typing import Optional

from bounded_gps_correlator import (
    correlate_observations_to_operator_fixes,
)
from observation_contract import (
    ObservationLocationLinkV1,
    OperatorFixV1,
)
from observation_store import ObservationStore


def plan_bounded_observation_location_links(
    *,
    store: ObservationStore,
    hmac_key: bytes,
    operator_fixes: tuple[OperatorFixV1, ...],
    max_delta_us: int,
    collection_session_id: Optional[str] = None,
) -> tuple[ObservationLocationLinkV1, ...]:
    """Return bounded link candidates without mutating the store."""

    if not isinstance(store, ObservationStore):
        raise ValueError("store must be ObservationStore")

    observations = store.list_observation_events(
        collection_session_id=collection_session_id,
    )
    existing_location_links = (
        store.list_observation_location_links()
    )

    return correlate_observations_to_operator_fixes(
        hmac_key=hmac_key,
        observations=observations,
        operator_fixes=operator_fixes,
        max_delta_us=max_delta_us,
        existing_location_links=existing_location_links,
    )


__all__ = ["plan_bounded_observation_location_links"]
