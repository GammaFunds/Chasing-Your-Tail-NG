"""Strict synthetic OperatorFixV1 JSONL replay adapter."""

from __future__ import annotations

import json
from typing import Iterable

from observation_contract import (
    ObservationProvenanceV1,
    OperatorFixV1,
    create_operator_fix,
)
from observation_location_link_orchestrator import (
    run_bounded_observation_location_link_correlation,
)
from observation_location_link_writer import (
    LocationLinkWriteSummaryV1,
)
from observation_store import ObservationStore


_SOURCE_TYPE = "synthetic.operator_fix_jsonl"
_COLLECTOR_NAME = "cyt.synthetic_operator_fix_jsonl_adapter"
_COLLECTOR_VERSION = "1.0"
_INGEST_MODE = "replay"
_SOURCE_SCHEMA_VERSION = "cyt.synthetic-operator-fix-jsonl.v1"

_REQUIRED_KEYS = frozenset(
    {
        "source_record_reference",
        "operator_fix_timestamp_us",
        "operator_latitude",
        "operator_longitude",
    }
)

_OPTIONAL_KEYS = frozenset(
    {
        "operator_location_accuracy_m",
    }
)

_ALLOWED_KEYS = _REQUIRED_KEYS | _OPTIONAL_KEYS


class SyntheticOperatorFixJsonlDecodeError(ValueError):
    """Raised when a synthetic operator-fix record is invalid."""


def decode_synthetic_operator_fix_jsonl(
    lines: Iterable[str],
    *,
    hmac_key: bytes,
    collection_session_id: str,
    sensor_id: str,
    ingest_timestamp_us: int,
) -> tuple[OperatorFixV1, ...]:
    """Decode and validate an entire synthetic fix JSONL input."""

    if isinstance(lines, (str, bytes)):
        raise SyntheticOperatorFixJsonlDecodeError(
            "input must be an iterable of text lines"
        )

    try:
        iterator = iter(lines)
    except TypeError:
        raise SyntheticOperatorFixJsonlDecodeError(
            "input must be an iterable of text lines"
        ) from None

    provenance = ObservationProvenanceV1(
        collector_name=_COLLECTOR_NAME,
        collector_version=_COLLECTOR_VERSION,
        ingest_mode=_INGEST_MODE,
        source_schema_version=_SOURCE_SCHEMA_VERSION,
    )

    fixes: list[OperatorFixV1] = []

    for line_number, line in enumerate(iterator, 1):
        if not isinstance(line, str):
            raise SyntheticOperatorFixJsonlDecodeError(
                f"line {line_number}: line must be text"
            )

        if not line.strip():
            raise SyntheticOperatorFixJsonlDecodeError(
                f"line {line_number}: blank lines are not allowed"
            )

        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            raise SyntheticOperatorFixJsonlDecodeError(
                f"line {line_number}: malformed JSON"
            ) from None

        if type(record) is not dict:
            raise SyntheticOperatorFixJsonlDecodeError(
                f"line {line_number}: JSON value must be an object"
            )

        record_keys = set(record)

        if record_keys - _ALLOWED_KEYS:
            raise SyntheticOperatorFixJsonlDecodeError(
                f"line {line_number}: unknown fields are not allowed"
            )

        missing_keys = _REQUIRED_KEYS - record_keys

        if missing_keys:
            names = ", ".join(sorted(missing_keys))
            raise SyntheticOperatorFixJsonlDecodeError(
                f"line {line_number}: missing fields: {names}"
            )

        try:
            fix = create_operator_fix(
                hmac_key=hmac_key,
                collection_session_id=collection_session_id,
                source_type=_SOURCE_TYPE,
                sensor_id=sensor_id,
                operator_fix_timestamp_us=record[
                    "operator_fix_timestamp_us"
                ],
                ingest_timestamp_us=ingest_timestamp_us,
                source_record_reference=record[
                    "source_record_reference"
                ],
                provenance=provenance,
                operator_latitude=record["operator_latitude"],
                operator_longitude=record["operator_longitude"],
                operator_location_accuracy_m=record.get(
                    "operator_location_accuracy_m"
                ),
            )
        except (TypeError, ValueError):
            raise SyntheticOperatorFixJsonlDecodeError(
                f"line {line_number}: invalid record fields"
            ) from None

        fixes.append(fix)

    return tuple(fixes)


def replay_synthetic_operator_fix_jsonl(
    lines: Iterable[str],
    *,
    store: ObservationStore,
    hmac_key: bytes,
    collection_session_id: str,
    sensor_id: str,
    ingest_timestamp_us: int,
    max_delta_us: int,
) -> LocationLinkWriteSummaryV1:
    """Decode all fixes, then run bounded correlation and writing."""

    if type(store) is not ObservationStore:
        raise ValueError("store must be ObservationStore")

    fixes = decode_synthetic_operator_fix_jsonl(
        lines,
        hmac_key=hmac_key,
        collection_session_id=collection_session_id,
        sensor_id=sensor_id,
        ingest_timestamp_us=ingest_timestamp_us,
    )

    return run_bounded_observation_location_link_correlation(
        store=store,
        hmac_key=hmac_key,
        operator_fixes=fixes,
        max_delta_us=max_delta_us,
        collection_session_id=collection_session_id,
    )


__all__ = [
    "SyntheticOperatorFixJsonlDecodeError",
    "decode_synthetic_operator_fix_jsonl",
    "replay_synthetic_operator_fix_jsonl",
]
