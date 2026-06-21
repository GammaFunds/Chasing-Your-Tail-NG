from __future__ import annotations

from observation_contract import (
    ObservationEventV1,
    ObservationLocationLinkV1,
    OperatorFixV1,
    create_observation_location_link,
)


def correlate_observations_to_operator_fixes(
    *,
    hmac_key: bytes,
    observations: tuple[ObservationEventV1, ...],
    operator_fixes: tuple[OperatorFixV1, ...],
    max_delta_us: int,
    existing_location_links: tuple[
        ObservationLocationLinkV1, ...
    ] = (),
) -> tuple[ObservationLocationLinkV1, ...]:
    if isinstance(max_delta_us, bool) or not isinstance(
        max_delta_us, int
    ) or max_delta_us < 0:
        raise ValueError(
            "max_delta_us must be a non-negative integer"
        )

    suppressed_ids = {
        link.observation_id
        for link in existing_location_links
        if link.correlation_method == "same_source_record"
    }

    obs_by_id = {obs.observation_id: obs for obs in observations}

    results: list[ObservationLocationLinkV1] = []

    for obs in observations:
        if obs.observation_id in suppressed_ids:
            continue

        best_fix: OperatorFixV1 | None = None
        best_abs_delta: int | None = None

        for fix in operator_fixes:
            if fix.collection_session_id != obs.collection_session_id:
                continue

            delta = (
                fix.operator_fix_timestamp_us
                - obs.source_timestamp_us
            )
            abs_delta = abs(delta)

            if abs_delta > max_delta_us:
                continue

            if best_fix is None:
                best_fix = fix
                best_abs_delta = abs_delta
            elif abs_delta < best_abs_delta:
                best_fix = fix
                best_abs_delta = abs_delta
            elif abs_delta == best_abs_delta:
                if (
                    fix.operator_fix_timestamp_us
                    < best_fix.operator_fix_timestamp_us
                ):
                    best_fix = fix
                elif (
                    fix.operator_fix_timestamp_us
                    == best_fix.operator_fix_timestamp_us
                    and fix.operator_fix_id
                    < best_fix.operator_fix_id
                ):
                    best_fix = fix

        if best_fix is not None:
            link = create_observation_location_link(
                hmac_key=hmac_key,
                observation=obs,
                operator_fix_id=best_fix.operator_fix_id,
                operator_latitude=best_fix.operator_latitude,
                operator_longitude=best_fix.operator_longitude,
                operator_fix_timestamp_us=best_fix.operator_fix_timestamp_us,
                correlation_method="nearest_fix_bounded",
                correlation_version="1.0",
                operator_location_accuracy_m=best_fix.operator_location_accuracy_m,
            )
            results.append(link)

    results.sort(
        key=lambda link: (
            obs_by_id[link.observation_id].source_timestamp_us,
            link.observation_id,
        )
    )

    return tuple(results)


__all__ = ["correlate_observations_to_operator_fixes"]
