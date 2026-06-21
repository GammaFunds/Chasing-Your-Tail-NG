"""Strict synthetic JSONL replay adapter for Observation Contract v1."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Iterable

from observation_contract import (
    ObservationEventV1,
    ObservationProvenanceV1,
    create_observation_event,
)
from observation_store import ObservationStore


_SOURCE_TYPE = "synthetic.jsonl"
_COLLECTOR_NAME = "cyt.synthetic_jsonl_adapter"
_COLLECTOR_VERSION = "1.0"
_INGEST_MODE = "replay"
_SOURCE_SCHEMA_VERSION = "cyt.synthetic-jsonl.v1"

_REQUIRED_KEYS = frozenset(
    {
        "source_record_reference",
        "source_timestamp_us",
    }
)

_OPTIONAL_KEYS = frozenset(
    {
        "device_identifier",
        "device_identifier_kind",
        "signal_strength",
        "signal_strength_unit",
    }
)

_ALLOWED_KEYS = _REQUIRED_KEYS | _OPTIONAL_KEYS

_STORE_RESULTS = frozenset(
    {
        "inserted",
        "duplicate",
        "identity_conflict",
    }
)


class SyntheticJsonlDecodeError(ValueError):
    """Raised when a synthetic JSONL record is invalid."""


@dataclass(frozen=True)
class ReplaySummaryV1:
    """Content-free counts for one completed replay."""

    total_records: int
    inserted: int
    duplicate: int
    identity_conflict: int

    def __post_init__(self) -> None:
        for name in (
            "total_records",
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

        if self.total_records != (
            self.inserted
            + self.duplicate
            + self.identity_conflict
        ):
            raise ValueError(
                "total_records must equal the result-count sum"
            )


def decode_synthetic_jsonl(
    lines: Iterable[str],
    *,
    hmac_key: bytes,
    collection_session_id: str,
    sensor_id: str,
    ingest_timestamp_us: int,
) -> tuple[ObservationEventV1, ...]:
    """Decode and validate an entire synthetic JSONL input."""

    if isinstance(lines, (str, bytes)):
        raise SyntheticJsonlDecodeError(
            "input must be an iterable of text lines"
        )

    try:
        iterator = iter(lines)
    except TypeError:
        raise SyntheticJsonlDecodeError(
            "input must be an iterable of text lines"
        ) from None

    provenance = ObservationProvenanceV1(
        collector_name=_COLLECTOR_NAME,
        collector_version=_COLLECTOR_VERSION,
        ingest_mode=_INGEST_MODE,
        source_schema_version=_SOURCE_SCHEMA_VERSION,
    )

    events: list[ObservationEventV1] = []

    for line_number, line in enumerate(iterator, 1):
        if not isinstance(line, str):
            raise SyntheticJsonlDecodeError(
                f"line {line_number}: line must be text"
            )

        if not line.strip():
            raise SyntheticJsonlDecodeError(
                f"line {line_number}: blank lines are not allowed"
            )

        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            raise SyntheticJsonlDecodeError(
                f"line {line_number}: malformed JSON"
            ) from None

        if type(record) is not dict:
            raise SyntheticJsonlDecodeError(
                f"line {line_number}: JSON value must be an object"
            )

        record_keys = set(record)

        unknown_keys = record_keys - _ALLOWED_KEYS
        if unknown_keys:
            raise SyntheticJsonlDecodeError(
                f"line {line_number}: unknown fields are not allowed"
            )

        missing_keys = _REQUIRED_KEYS - record_keys
        if missing_keys:
            names = ", ".join(sorted(missing_keys))
            raise SyntheticJsonlDecodeError(
                f"line {line_number}: missing fields: {names}"
            )

        try:
            event = create_observation_event(
                hmac_key=hmac_key,
                collection_session_id=collection_session_id,
                source_type=_SOURCE_TYPE,
                sensor_id=sensor_id,
                source_timestamp_us=record[
                    "source_timestamp_us"
                ],
                ingest_timestamp_us=ingest_timestamp_us,
                source_record_reference=record[
                    "source_record_reference"
                ],
                provenance=provenance,
                device_identifier=record.get(
                    "device_identifier"
                ),
                device_identifier_kind=record.get(
                    "device_identifier_kind"
                ),
                signal_strength=record.get(
                    "signal_strength"
                ),
                signal_strength_unit=record.get(
                    "signal_strength_unit"
                ),
            )
        except (TypeError, ValueError):
            raise SyntheticJsonlDecodeError(
                f"line {line_number}: invalid record fields"
            ) from None

        events.append(event)

    return tuple(events)


def replay_synthetic_jsonl(
    lines: Iterable[str],
    *,
    store: ObservationStore,
    hmac_key: bytes,
    collection_session_id: str,
    sensor_id: str,
    ingest_timestamp_us: int,
) -> ReplaySummaryV1:
    """Decode all records before inserting them into the store."""

    if type(store) is not ObservationStore:
        raise ValueError("store must be ObservationStore")

    events = decode_synthetic_jsonl(
        lines,
        hmac_key=hmac_key,
        collection_session_id=collection_session_id,
        sensor_id=sensor_id,
        ingest_timestamp_us=ingest_timestamp_us,
    )

    counts = {
        "inserted": 0,
        "duplicate": 0,
        "identity_conflict": 0,
    }

    for event in events:
        result = store.insert_observation_event(event)

        if result not in _STORE_RESULTS:
            raise RuntimeError(
                "unexpected observation store result"
            )

        counts[result] += 1

    return ReplaySummaryV1(
        total_records=len(events),
        inserted=counts["inserted"],
        duplicate=counts["duplicate"],
        identity_conflict=counts["identity_conflict"],
    )


__all__ = [
    "ReplaySummaryV1",
    "SyntheticJsonlDecodeError",
    "decode_synthetic_jsonl",
    "replay_synthetic_jsonl",
]
