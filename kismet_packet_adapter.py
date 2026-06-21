"""Read-only Kismet packet snapshot adapter for Observation Contract v1."""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from typing import Union

from observation_contract import (
    ObservationEventV1,
    ObservationProvenanceV1,
    create_observation_event,
)
from observation_store import ObservationStore


_SUPPORTED_DB_VERSIONS = frozenset({8, 9, 10})

_REQUIRED_PACKET_COLUMNS = {
    "ts_sec": {"INT", "INTEGER"},
    "ts_usec": {"INT", "INTEGER"},
    "sourcemac": {"TEXT"},
    "datasource": {"TEXT"},
    "error": {"INT", "INTEGER"},
    "hash": {"INT", "INTEGER"},
    "packetid": {"INT", "INTEGER"},
}

_SOURCE_TYPE = "kismet.packet"
_COLLECTOR_NAME = "cyt.kismet_packet_adapter"
_COLLECTOR_VERSION = "1.0"
_INGEST_MODE = "import"
_SOURCE_SCHEMA_VERSION = "kismetdb.packet.v1"

_ZERO_MAC = "00:00:00:00:00:00"
_ZERO_UUID = "00000000-0000-0000-0000-000000000000"

_STORE_RESULTS = frozenset(
    {
        "inserted",
        "duplicate",
        "identity_conflict",
    }
)


class KismetPacketAdapterError(ValueError):
    """Raised when a Kismet packet snapshot is not admissible."""


@dataclass(frozen=True)
class KismetPacketReplaySummaryV1:
    """Content-free result counts for one bounded snapshot replay."""

    total_rows: int
    inserted: int
    duplicate: int
    identity_conflict: int

    def __post_init__(self) -> None:
        for name in (
            "total_rows",
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

        if self.total_rows != (
            self.inserted
            + self.duplicate
            + self.identity_conflict
        ):
            raise ValueError(
                "total_rows must equal the result-count sum"
            )


def _require_integer(
    name: str,
    value: object,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise KismetPacketAdapterError(
            f"{name} must be an integer"
        )

    if minimum is not None and value < minimum:
        raise KismetPacketAdapterError(
            f"{name} is outside the supported range"
        )

    if maximum is not None and value > maximum:
        raise KismetPacketAdapterError(
            f"{name} is outside the supported range"
        )

    return value


def _read_db_version(
    connection: sqlite3.Connection,
) -> int:
    try:
        rows = connection.execute(
            "SELECT db_version FROM KISMET"
        ).fetchall()
    except sqlite3.Error:
        raise KismetPacketAdapterError(
            "Kismet database metadata is unavailable"
        ) from None

    if len(rows) != 1:
        raise KismetPacketAdapterError(
            "Kismet database metadata is invalid"
        )

    version = _require_integer(
        "db_version",
        rows[0]["db_version"],
        minimum=1,
    )

    if version not in _SUPPORTED_DB_VERSIONS:
        raise KismetPacketAdapterError(
            "unsupported Kismet database version"
        )

    return version


def _validate_packet_schema(
    connection: sqlite3.Connection,
) -> None:
    try:
        rows = connection.execute(
            "PRAGMA table_info(packets)"
        ).fetchall()
    except sqlite3.Error:
        raise KismetPacketAdapterError(
            "Kismet packet schema is unavailable"
        ) from None

    if not rows:
        raise KismetPacketAdapterError(
            "Kismet packet schema is unavailable"
        )

    actual = {
        row["name"]: row["type"].upper()
        for row in rows
    }

    for column, accepted_types in _REQUIRED_PACKET_COLUMNS.items():
        if column not in actual:
            raise KismetPacketAdapterError(
                "Kismet packet schema is missing required columns"
            )

        if actual[column] not in accepted_types:
            raise KismetPacketAdapterError(
                "Kismet packet schema has incompatible column types"
            )


def _normalize_datasource(value: object) -> str:
    if not isinstance(value, str):
        raise KismetPacketAdapterError(
            "packet datasource is invalid"
        )

    normalized = value.strip()

    if not normalized or normalized == _ZERO_UUID:
        raise KismetPacketAdapterError(
            "packet datasource is unavailable"
        )

    return normalized


def _normalize_source_mac(
    value: object,
) -> tuple[str | None, str | None]:
    if value is None:
        return None, None

    if not isinstance(value, str):
        raise KismetPacketAdapterError(
            "packet source identifier is invalid"
        )

    normalized = value.strip()

    if not normalized or normalized == _ZERO_MAC:
        return None, None

    return normalized, "mac"


def _source_reference(
    *,
    db_version: int,
    source_rowid: int,
    packet_hash: int,
    packet_id: int,
) -> str:
    return json.dumps(
        [
            "kismet.packet.v1",
            db_version,
            source_rowid,
            packet_hash,
            packet_id,
        ],
        ensure_ascii=True,
        separators=(",", ":"),
    )


def decode_kismet_packet_snapshot(
    db_path: Union[str, Path],
    *,
    hmac_key: bytes,
    collection_session_id: str,
    ingest_timestamp_us: int,
) -> tuple[ObservationEventV1, ...]:
    """Decode every admissible packet row before any store write."""

    path = Path(db_path)

    if not path.is_file():
        raise KismetPacketAdapterError(
            "Kismet packet source is unavailable"
        )

    database_uri = path.resolve().as_uri() + "?mode=ro"

    provenance = ObservationProvenanceV1(
        collector_name=_COLLECTOR_NAME,
        collector_version=_COLLECTOR_VERSION,
        ingest_mode=_INGEST_MODE,
        source_schema_version=_SOURCE_SCHEMA_VERSION,
    )

    try:
        with closing(
            sqlite3.connect(database_uri, uri=True)
        ) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")

            db_version = _read_db_version(connection)
            _validate_packet_schema(connection)

            rows = connection.execute(
                """
                SELECT
                    rowid AS source_rowid,
                    ts_sec,
                    ts_usec,
                    sourcemac,
                    datasource,
                    hash AS packet_hash,
                    packetid AS packet_id
                FROM packets
                WHERE error = 0
                ORDER BY rowid
                """
            ).fetchall()
    except KismetPacketAdapterError:
        raise
    except sqlite3.Error:
        raise KismetPacketAdapterError(
            "unable to read Kismet packet source"
        ) from None

    events: list[ObservationEventV1] = []

    for row_number, row in enumerate(rows, 1):
        try:
            source_rowid = _require_integer(
                "source_rowid",
                row["source_rowid"],
                minimum=1,
            )
            ts_sec = _require_integer(
                "ts_sec",
                row["ts_sec"],
                minimum=0,
            )
            ts_usec = _require_integer(
                "ts_usec",
                row["ts_usec"],
                minimum=0,
                maximum=999_999,
            )
            packet_hash = _require_integer(
                "packet_hash",
                row["packet_hash"],
            )
            packet_id = _require_integer(
                "packet_id",
                row["packet_id"],
                minimum=0,
            )
            datasource = _normalize_datasource(
                row["datasource"]
            )
            (
                device_identifier,
                device_identifier_kind,
            ) = _normalize_source_mac(
                row["sourcemac"]
            )

            source_timestamp_us = (
                ts_sec * 1_000_000 + ts_usec
            )

            event = create_observation_event(
                hmac_key=hmac_key,
                collection_session_id=collection_session_id,
                source_type=_SOURCE_TYPE,
                sensor_id=datasource,
                source_timestamp_us=source_timestamp_us,
                ingest_timestamp_us=ingest_timestamp_us,
                source_record_reference=_source_reference(
                    db_version=db_version,
                    source_rowid=source_rowid,
                    packet_hash=packet_hash,
                    packet_id=packet_id,
                ),
                provenance=provenance,
                device_identifier=device_identifier,
                device_identifier_kind=device_identifier_kind,
            )
        except (KismetPacketAdapterError, TypeError, ValueError):
            raise KismetPacketAdapterError(
                f"packet row {row_number}: invalid source fields"
            ) from None

        events.append(event)

    return tuple(events)


def replay_kismet_packet_snapshot(
    db_path: Union[str, Path],
    *,
    store: ObservationStore,
    hmac_key: bytes,
    collection_session_id: str,
    ingest_timestamp_us: int,
) -> KismetPacketReplaySummaryV1:
    """Decode the complete bounded snapshot, then write events."""

    if type(store) is not ObservationStore:
        raise ValueError("store must be ObservationStore")

    events = decode_kismet_packet_snapshot(
        db_path,
        hmac_key=hmac_key,
        collection_session_id=collection_session_id,
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

    return KismetPacketReplaySummaryV1(
        total_rows=len(events),
        inserted=counts["inserted"],
        duplicate=counts["duplicate"],
        identity_conflict=counts["identity_conflict"],
    )


__all__ = [
    "KismetPacketAdapterError",
    "KismetPacketReplaySummaryV1",
    "decode_kismet_packet_snapshot",
    "replay_kismet_packet_snapshot",
]
