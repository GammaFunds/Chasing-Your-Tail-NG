"""Persistence of preplanned observation location-link candidates."""

from __future__ import annotations

from dataclasses import dataclass

from observation_contract import ObservationLocationLinkV1
from observation_store import ObservationStore


_STORE_RESULTS = frozenset(
    {
        "inserted",
        "duplicate",
        "identity_conflict",
    }
)


@dataclass(frozen=True)
class LocationLinkWriteSummaryV1:
    """Content-free result counts for one candidate write batch."""

    total_candidates: int
    inserted: int
    duplicate: int
    identity_conflict: int

    def __post_init__(self) -> None:
        for name in (
            "total_candidates",
            "inserted",
            "duplicate",
            "identity_conflict",
        ):
            value = getattr(self, name)

            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    f"{name} must be a non-negative integer"
                )

        if self.total_candidates != (
            self.inserted
            + self.duplicate
            + self.identity_conflict
        ):
            raise ValueError(
                "total_candidates must equal the result-count sum"
            )


def write_observation_location_link_candidates(
    *,
    store: ObservationStore,
    candidates: tuple[ObservationLocationLinkV1, ...],
) -> LocationLinkWriteSummaryV1:
    """Persist validated candidates and return content-free counts."""

    if type(store) is not ObservationStore:
        raise ValueError("store must be ObservationStore")

    if type(candidates) is not tuple:
        raise ValueError(
            "candidates must be a tuple of ObservationLocationLinkV1"
        )

    for candidate in candidates:
        if type(candidate) is not ObservationLocationLinkV1:
            raise ValueError(
                "every candidate must be ObservationLocationLinkV1"
            )

    counts = {
        "inserted": 0,
        "duplicate": 0,
        "identity_conflict": 0,
    }

    for candidate in candidates:
        result = store.insert_observation_location_link(candidate)

        if result not in _STORE_RESULTS:
            raise RuntimeError(
                "unexpected observation location-link store result"
            )

        counts[result] += 1

    return LocationLinkWriteSummaryV1(
        total_candidates=len(candidates),
        inserted=counts["inserted"],
        duplicate=counts["duplicate"],
        identity_conflict=counts["identity_conflict"],
    )


__all__ = [
    "LocationLinkWriteSummaryV1",
    "write_observation_location_link_candidates",
]
