"""Isolated SQLite store for observation contract v1.0."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator, Optional

from observation_contract import (
    ObservationEventV1,
    ObservationLocationLinkV1,
    ObservationProvenanceV1,
    compare_observation_source_facts,
)


_STORE_SCHEMA_VERSION = 1
_CONTRACT_SCHEMA_VERSION = "1.0"

_METADATA_TABLE = "store_metadata"
_EVENTS_TABLE = "observation_events"
_LINKS_TABLE = "observation_location_links"

_EVENT_UPDATE_TRIGGER = "observation_events_no_update"
_LINK_UPDATE_TRIGGER = "observation_location_links_no_update"

_METADATA_TABLE_DDL = f"""
CREATE TABLE {_METADATA_TABLE} (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    store_schema_version INTEGER NOT NULL CHECK (
        store_schema_version = {_STORE_SCHEMA_VERSION}
    ),
    contract_schema_version TEXT NOT NULL CHECK (
        contract_schema_version = '{_CONTRACT_SCHEMA_VERSION}'
    ),
    initialized_at_us INTEGER NOT NULL
)
"""

_EVENTS_TABLE_DDL = f"""
CREATE TABLE {_EVENTS_TABLE} (
    observation_id TEXT NOT NULL PRIMARY KEY,
    schema_version TEXT NOT NULL,
    record_kind TEXT NOT NULL,
    collection_session_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    sensor_id TEXT NOT NULL,
    source_timestamp_us INTEGER NOT NULL,
    ingest_timestamp_us INTEGER NOT NULL,
    source_record_reference TEXT NOT NULL,
    collector_name TEXT NOT NULL,
    collector_version TEXT NOT NULL,
    ingest_mode TEXT NOT NULL,
    source_schema_version TEXT,
    device_identifier TEXT,
    device_identifier_kind TEXT,
    signal_strength REAL,
    signal_strength_unit TEXT
)
"""

_LINKS_TABLE_DDL = f"""
CREATE TABLE {_LINKS_TABLE} (
    location_link_id TEXT NOT NULL PRIMARY KEY,
    schema_version TEXT NOT NULL,
    record_kind TEXT NOT NULL,
    observation_id TEXT NOT NULL REFERENCES {_EVENTS_TABLE} (
        observation_id
    ) ON DELETE CASCADE,
    operator_fix_id TEXT NOT NULL,
    operator_latitude REAL NOT NULL,
    operator_longitude REAL NOT NULL,
    operator_fix_timestamp_us INTEGER NOT NULL,
    source_to_fix_delta_us INTEGER NOT NULL,
    correlation_method TEXT NOT NULL,
    correlation_version TEXT NOT NULL,
    operator_location_accuracy_m REAL
)
"""

_EVENT_UPDATE_TRIGGER_DDL = f"""
CREATE TRIGGER {_EVENT_UPDATE_TRIGGER}
BEFORE UPDATE ON {_EVENTS_TABLE}
BEGIN
    SELECT RAISE(ABORT, 'observation_events is immutable');
END
"""

_LINK_UPDATE_TRIGGER_DDL = f"""
CREATE TRIGGER {_LINK_UPDATE_TRIGGER}
BEFORE UPDATE ON {_LINKS_TABLE}
BEGIN
    SELECT RAISE(ABORT, 'observation_location_links is immutable');
END
"""


class ObservationStore:
    """SQLite-backed immutable store for accepted observation records."""

    def __init__(self, db_path: str | Path):
        self._db_path = Path(db_path)
        self._connection: Optional[sqlite3.Connection] = None
        self._closed = False
        self._open()

    def __enter__(self) -> "ObservationStore":
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
        self._closed = True

    def insert_observation_event(self, event: ObservationEventV1) -> str:
        self._ensure_open()
        if type(event) is not ObservationEventV1:
            raise ValueError("event must be ObservationEventV1")

        with self._write_transaction():
            existing = self._fetch_event_row(event.observation_id)
            if existing is None:
                self._connection.execute(
                    """
                    INSERT INTO observation_events (
                        observation_id,
                        schema_version,
                        record_kind,
                        collection_session_id,
                        source_type,
                        sensor_id,
                        source_timestamp_us,
                        ingest_timestamp_us,
                        source_record_reference,
                        collector_name,
                        collector_version,
                        ingest_mode,
                        source_schema_version,
                        device_identifier,
                        device_identifier_kind,
                        signal_strength,
                        signal_strength_unit
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._event_insert_values(event),
                )
                return "inserted"

            existing_event = self._event_from_row(existing)
            return compare_observation_source_facts(
                existing_event,
                event,
            )

    def get_observation_event(
        self,
        observation_id: str,
    ) -> Optional[ObservationEventV1]:
        self._ensure_open()
        row = self._fetch_event_row(observation_id)
        if row is None:
            return None
        return self._event_from_row(row)

    def insert_observation_location_link(
        self,
        link: ObservationLocationLinkV1,
    ) -> str:
        self._ensure_open()
        if type(link) is not ObservationLocationLinkV1:
            raise ValueError(
                "link must be ObservationLocationLinkV1"
            )

        with self._write_transaction():
            parent = self._fetch_event_row(link.observation_id)
            if parent is None:
                raise ValueError("parent observation does not exist")

            parent_source_timestamp_us = parent["source_timestamp_us"]
            expected_delta = (
                link.operator_fix_timestamp_us
                - parent_source_timestamp_us
            )
            if link.source_to_fix_delta_us != expected_delta:
                raise ValueError(
                    "source_to_fix_delta_us must match the stored parent observation"
                )

            existing = self._fetch_link_row(link.location_link_id)
            if existing is None:
                self._connection.execute(
                    """
                    INSERT INTO observation_location_links (
                        location_link_id,
                        schema_version,
                        record_kind,
                        observation_id,
                        operator_fix_id,
                        operator_latitude,
                        operator_longitude,
                        operator_fix_timestamp_us,
                        source_to_fix_delta_us,
                        correlation_method,
                        correlation_version,
                        operator_location_accuracy_m
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._link_insert_values(link),
                )
                return "inserted"

            existing_link = self._link_from_row(existing)
            if existing_link == link:
                return "duplicate"
            return "identity_conflict"

    def get_observation_location_link(
        self,
        location_link_id: str,
    ) -> Optional[ObservationLocationLinkV1]:
        self._ensure_open()
        row = self._fetch_link_row(location_link_id)
        if row is None:
            return None
        return self._link_from_row(row)

    def _open(self) -> None:
        if self._connection is not None:
            return

        connection = sqlite3.connect(
            str(self._db_path),
            timeout=30.0,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")

        self._connection = connection
        try:
            if self._is_empty_database():
                self._bootstrap()
            else:
                self._validate_existing_schema()
        except Exception:
            self.close()
            raise

    def _ensure_open(self) -> None:
        if self._connection is None or self._closed:
            raise RuntimeError("ObservationStore is closed")

    @contextmanager
    def _write_transaction(self) -> Iterator[None]:
        self._ensure_open()
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except Exception:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()

    def _bootstrap(self) -> None:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            self._bootstrap_execute(_METADATA_TABLE_DDL)
            self._bootstrap_execute(_EVENTS_TABLE_DDL)
            self._bootstrap_execute(_LINKS_TABLE_DDL)
            self._bootstrap_execute(_EVENT_UPDATE_TRIGGER_DDL)
            self._bootstrap_execute(_LINK_UPDATE_TRIGGER_DDL)
            self._bootstrap_execute(
                f"""
                INSERT INTO {_METADATA_TABLE} (
                    singleton,
                    store_schema_version,
                    contract_schema_version,
                    initialized_at_us
                ) VALUES (1, ?, ?, ?)
                """,
                (
                    _STORE_SCHEMA_VERSION,
                    _CONTRACT_SCHEMA_VERSION,
                    0,
                ),
            )
            self._bootstrap_execute(
                f"PRAGMA user_version = {_STORE_SCHEMA_VERSION}"
            )
            self._connection.commit()
            self._validate_existing_schema()
        except Exception:
            self._connection.rollback()
            raise

    def _bootstrap_execute(
        self,
        sql: str,
        params: tuple[object, ...] = (),
    ) -> sqlite3.Cursor:
        return self._connection.execute(sql, params)

    def _is_empty_database(self) -> bool:
        user_version = self._connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]
        if user_version != 0:
            return False

        rows = self._connection.execute(
            """
            SELECT type, name
            FROM sqlite_master
            WHERE name NOT LIKE 'sqlite_%'
            """
        ).fetchall()
        return not rows

    def _validate_existing_schema(self) -> None:
        self._ensure_open()

        user_version = self._connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]
        if user_version != _STORE_SCHEMA_VERSION:
            raise ValueError("unsupported store schema version")

        table_names = self._fetch_object_names("table")
        if table_names != {
            _METADATA_TABLE,
            _EVENTS_TABLE,
            _LINKS_TABLE,
        }:
            raise ValueError("unexpected store tables")

        trigger_names = self._fetch_object_names("trigger")
        if trigger_names != {
            _EVENT_UPDATE_TRIGGER,
            _LINK_UPDATE_TRIGGER,
        }:
            raise ValueError("unexpected store triggers")

        self._validate_trigger_sql(
            _EVENT_UPDATE_TRIGGER,
            _EVENTS_TABLE,
            "observation_events is immutable",
        )
        self._validate_trigger_sql(
            _LINK_UPDATE_TRIGGER,
            _LINKS_TABLE,
            "observation_location_links is immutable",
        )

        self._validate_table_ddl(
            _METADATA_TABLE,
            _METADATA_TABLE_DDL,
        )
        self._validate_table_ddl(
            _EVENTS_TABLE,
            _EVENTS_TABLE_DDL,
        )
        self._validate_table_ddl(
            _LINKS_TABLE,
            _LINKS_TABLE_DDL,
        )

        metadata_rows = self._connection.execute(
            f"""
            SELECT
                singleton,
                store_schema_version,
                contract_schema_version,
                initialized_at_us
            FROM {_METADATA_TABLE}
            """
        ).fetchall()
        if len(metadata_rows) != 1:
            raise ValueError("unexpected metadata rows")

        metadata_row = metadata_rows[0]
        if (
            metadata_row["singleton"] != 1
            or metadata_row["store_schema_version"] != _STORE_SCHEMA_VERSION
            or metadata_row["contract_schema_version"]
            != _CONTRACT_SCHEMA_VERSION
            or metadata_row["initialized_at_us"] != 0
        ):
            raise ValueError("unexpected metadata values")

        orphan_check = self._connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
        if orphan_check:
            raise ValueError("foreign key violations detected")

    def _fetch_object_names(self, object_type: str) -> set[str]:
        rows = self._connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = ? AND name NOT LIKE 'sqlite_%'
            """,
            (object_type,),
        ).fetchall()
        return {row["name"] for row in rows}

    def _validate_table_ddl(
        self,
        table_name: str,
        expected_sql: str,
    ) -> None:
        row = self._connection.execute(
            """
            SELECT sql
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()
        if row is None or row["sql"] is None:
            raise ValueError(f"unexpected DDL for {table_name}")

        if self._normalize_sql(row["sql"]) != self._normalize_sql(expected_sql):
            raise ValueError(f"unexpected DDL for {table_name}")

    def _validate_trigger_sql(
        self,
        trigger_name: str,
        table_name: str,
        abort_message: str,
    ) -> None:
        row = self._connection.execute(
            """
            SELECT sql
            FROM sqlite_master
            WHERE type = 'trigger' AND name = ?
            """,
            (trigger_name,),
        ).fetchone()
        if row is None or row["sql"] is None:
            raise ValueError("unexpected trigger definition")

        expected_sql = (
            _EVENT_UPDATE_TRIGGER_DDL
            if trigger_name == _EVENT_UPDATE_TRIGGER
            else _LINK_UPDATE_TRIGGER_DDL
        )
        if self._normalize_sql(row["sql"]) != self._normalize_sql(expected_sql):
            raise ValueError("unexpected trigger body")

    @staticmethod
    def _normalize_sql(sql: str) -> str:
        return " ".join(sql.strip().split()).rstrip(";").lower()

    def _fetch_event_row(
        self,
        observation_id: str,
    ) -> Optional[sqlite3.Row]:
        return self._connection.execute(
            f"""
            SELECT *
            FROM {_EVENTS_TABLE}
            WHERE observation_id = ?
            """,
            (observation_id,),
        ).fetchone()

    def _fetch_link_row(
        self,
        location_link_id: str,
    ) -> Optional[sqlite3.Row]:
        return self._connection.execute(
            f"""
            SELECT *
            FROM {_LINKS_TABLE}
            WHERE location_link_id = ?
            """,
            (location_link_id,),
        ).fetchone()

    def _event_insert_values(
        self,
        event: ObservationEventV1,
    ) -> tuple[object, ...]:
        provenance = event.provenance
        return (
            event.observation_id,
            event.schema_version,
            event.record_kind,
            event.collection_session_id,
            event.source_type,
            event.sensor_id,
            event.source_timestamp_us,
            event.ingest_timestamp_us,
            event.source_record_reference,
            provenance.collector_name,
            provenance.collector_version,
            provenance.ingest_mode,
            provenance.source_schema_version,
            event.device_identifier,
            event.device_identifier_kind,
            event.signal_strength,
            event.signal_strength_unit,
        )

    def _link_insert_values(
        self,
        link: ObservationLocationLinkV1,
    ) -> tuple[object, ...]:
        return (
            link.location_link_id,
            link.schema_version,
            link.record_kind,
            link.observation_id,
            link.operator_fix_id,
            link.operator_latitude,
            link.operator_longitude,
            link.operator_fix_timestamp_us,
            link.source_to_fix_delta_us,
            link.correlation_method,
            link.correlation_version,
            link.operator_location_accuracy_m,
        )

    def _event_from_row(
        self,
        row: sqlite3.Row,
    ) -> ObservationEventV1:
        return ObservationEventV1(
            schema_version=row["schema_version"],
            record_kind=row["record_kind"],
            observation_id=row["observation_id"],
            collection_session_id=row["collection_session_id"],
            source_type=row["source_type"],
            sensor_id=row["sensor_id"],
            source_timestamp_us=row["source_timestamp_us"],
            ingest_timestamp_us=row["ingest_timestamp_us"],
            source_record_reference=row["source_record_reference"],
            provenance=ObservationProvenanceV1(
                collector_name=row["collector_name"],
                collector_version=row["collector_version"],
                ingest_mode=row["ingest_mode"],
                source_schema_version=row["source_schema_version"],
            ),
            device_identifier=row["device_identifier"],
            device_identifier_kind=row["device_identifier_kind"],
            signal_strength=row["signal_strength"],
            signal_strength_unit=row["signal_strength_unit"],
        )

    def _link_from_row(
        self,
        row: sqlite3.Row,
    ) -> ObservationLocationLinkV1:
        return ObservationLocationLinkV1(
            schema_version=row["schema_version"],
            record_kind=row["record_kind"],
            location_link_id=row["location_link_id"],
            observation_id=row["observation_id"],
            operator_fix_id=row["operator_fix_id"],
            operator_latitude=row["operator_latitude"],
            operator_longitude=row["operator_longitude"],
            operator_fix_timestamp_us=row["operator_fix_timestamp_us"],
            source_to_fix_delta_us=row["source_to_fix_delta_us"],
            correlation_method=row["correlation_method"],
            correlation_version=row["correlation_version"],
            operator_location_accuracy_m=row[
                "operator_location_accuracy_m"
            ],
        )


__all__ = ["ObservationStore"]
