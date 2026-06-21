import gc
from contextlib import closing
import sqlite3
import tempfile
import types
import unittest
import warnings
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from observation_contract import (
    ObservationProvenanceV1,
    create_observation_event,
    create_observation_location_link,
)
from observation_store import ObservationStore


class ObservationStoreTests(unittest.TestCase):
    KEY = b"synthetic-store-test-key"

    @staticmethod
    def provenance(
        *,
        collector_name="synthetic_collector",
        collector_version="1.2.3",
        ingest_mode="live",
        source_schema_version="synthetic-v1",
    ):
        return ObservationProvenanceV1(
            collector_name=collector_name,
            collector_version=collector_version,
            ingest_mode=ingest_mode,
            source_schema_version=source_schema_version,
        )

    def event(self, **overrides):
        values = {
            "hmac_key": self.KEY,
            "collection_session_id": "collection_alpha",
            "source_type": "synthetic.event",
            "sensor_id": "sensor_alpha",
            "source_timestamp_us": 1_000_000,
            "ingest_timestamp_us": 1_000_250,
            "source_record_reference": "record_alpha",
            "provenance": self.provenance(),
            "device_identifier": None,
            "device_identifier_kind": None,
            "signal_strength": None,
            "signal_strength_unit": None,
        }
        values.update(overrides)
        return create_observation_event(**values)

    def location_link(self, observation=None, **overrides):
        values = {
            "hmac_key": self.KEY,
            "observation": observation or self.event(),
            "operator_fix_id": "fix_alpha",
            "operator_latitude": 10.25,
            "operator_longitude": -20.5,
            "operator_fix_timestamp_us": 1_000_750,
            "correlation_method": "nearest_fix_bounded",
            "correlation_version": "1.0",
            "operator_location_accuracy_m": 4.5,
        }
        values.update(overrides)
        return create_observation_location_link(**values)

    def open_store(self):
        tempdir = tempfile.TemporaryDirectory()
        path = Path(tempdir.name) / "observations.sqlite"
        store = ObservationStore(path)
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)
        return store, path

    @staticmethod
    def table_names(path):
        with closing(sqlite3.connect(path)) as connection:
            return {
                row[0]
                for row in connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                    AND name NOT LIKE 'sqlite_%'
                    """
                )
            }

    @staticmethod
    def trigger_sql(path, trigger_name):
        with closing(sqlite3.connect(path)) as connection:
            row = connection.execute(
                """
                SELECT sql
                FROM sqlite_master
                WHERE type = 'trigger' AND name = ?
                """,
                (trigger_name,),
            ).fetchone()
            return None if row is None else row[0]

    @staticmethod
    def table_info(path, table_name):
        with closing(sqlite3.connect(path)) as connection:
            return tuple(
                (
                    row[1],
                    row[2].upper(),
                    row[3],
                    row[5],
                    row[4],
                )
                for row in connection.execute(
                    f"PRAGMA table_info({table_name})"
                )
            )

    def create_valid_schema(self, path):
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                """
                CREATE TABLE store_metadata (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    store_schema_version INTEGER NOT NULL CHECK (
                        store_schema_version = 1
                    ),
                    contract_schema_version TEXT NOT NULL CHECK (
                        contract_schema_version = '1.0'
                    ),
                    initialized_at_us INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE observation_events (
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
            )
            connection.execute(
                """
                CREATE TABLE observation_location_links (
                    location_link_id TEXT NOT NULL PRIMARY KEY,
                    schema_version TEXT NOT NULL,
                    record_kind TEXT NOT NULL,
                    observation_id TEXT NOT NULL REFERENCES observation_events (
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
            )
            connection.execute(
                """
                CREATE TRIGGER observation_events_no_update
                BEFORE UPDATE ON observation_events
                BEGIN
                    SELECT RAISE(ABORT, 'observation_events is immutable');
                END
                """
            )
            connection.execute(
                """
                CREATE TRIGGER observation_location_links_no_update
                BEFORE UPDATE ON observation_location_links
                BEGIN
                    SELECT RAISE(ABORT, 'observation_location_links is immutable');
                END
                """
            )
            connection.execute(
                """
                INSERT INTO store_metadata (
                    singleton,
                    store_schema_version,
                    contract_schema_version,
                    initialized_at_us
                ) VALUES (1, 1, '1.0', 0)
                """
            )
            connection.execute("PRAGMA user_version = 1")
            connection.commit()

    @staticmethod
    def file_bytes(path):
        return Path(path).read_bytes()

    @staticmethod
    def schema_snapshot(path):
        with closing(sqlite3.connect(path)) as connection:
            user_version = connection.execute(
                "PRAGMA user_version"
            ).fetchone()[0]
            rows = connection.execute(
                """
                SELECT type, name, sql
                FROM sqlite_master
                WHERE name NOT LIKE 'sqlite_%'
                ORDER BY type, name
                """
            ).fetchall()
            return (
                user_version,
                tuple((row[0], row[1], row[2]) for row in rows),
            )

    def test_new_store_bootstraps_metadata_and_version(self):
        store, path = self.open_store()

        self.assertEqual(
            store._connection.execute("PRAGMA foreign_keys").fetchone()[0],
            1,
        )
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                1,
            )
            metadata = connection.execute(
                """
                SELECT store_schema_version, contract_schema_version
                FROM store_metadata
                """
            ).fetchone()
            self.assertEqual(metadata[0], 1)
            self.assertEqual(metadata[1], "1.0")

        self.assertEqual(
            self.table_names(path),
            {
                "store_metadata",
                "observation_events",
                "observation_location_links",
            },
        )
        self.assertEqual(
            self.table_info(
                path,
                "observation_events",
            )[0],
            ("observation_id", "TEXT", 1, 1, None),
        )

    def test_event_insert_roundtrip_and_immutable(self):
        store, path = self.open_store()
        event = self.event(
            device_identifier="device_alpha",
            device_identifier_kind="synthetic_id",
            signal_strength=-37.5,
            signal_strength_unit="synthetic_unit",
        )

        self.assertEqual(store.insert_observation_event(event), "inserted")
        self.assertEqual(store.get_observation_event(event.observation_id), event)

        store.close()
        with closing(sqlite3.connect(path)) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    UPDATE observation_events
                    SET sensor_id = ?
                    WHERE observation_id = ?
                    """,
                    ("changed", event.observation_id),
                )
            stored = connection.execute(
                """
                SELECT observation_id, sensor_id
                FROM observation_events
                WHERE observation_id = ?
                """,
                (event.observation_id,),
            ).fetchone()
            self.assertEqual(stored[0], event.observation_id)
            self.assertEqual(stored[1], event.sensor_id)

    def test_duplicate_event_after_close_reopen(self):
        store, path = self.open_store()
        event = self.event(
            device_identifier="device_alpha",
            device_identifier_kind="synthetic_id",
            signal_strength=-42,
            signal_strength_unit="synthetic_unit",
        )
        self.assertEqual(store.insert_observation_event(event), "inserted")
        store.close()

        reopened = ObservationStore(path)
        self.addCleanup(reopened.close)

        duplicate = self.event(
            ingest_timestamp_us=9_000_000,
            provenance=self.provenance(
                collector_version="9.9.9",
                ingest_mode="replay",
            ),
            device_identifier="device_alpha",
            device_identifier_kind="synthetic_id",
            signal_strength=-42,
            signal_strength_unit="synthetic_unit",
        )
        self.assertEqual(
            reopened.insert_observation_event(duplicate),
            "duplicate",
        )
        self.assertEqual(
            reopened.get_observation_event(event.observation_id),
            event,
        )

    def test_event_identity_conflict_preserves_original_row(self):
        store, _ = self.open_store()
        event = self.event(
            device_identifier="device_alpha",
            device_identifier_kind="synthetic_id",
            signal_strength=-42,
            signal_strength_unit="synthetic_unit",
        )
        self.assertEqual(store.insert_observation_event(event), "inserted")

        conflict = self.event(
            source_timestamp_us=1_000_001,
            device_identifier="device_alpha",
            device_identifier_kind="synthetic_id",
            signal_strength=-42,
            signal_strength_unit="synthetic_unit",
        )
        self.assertEqual(
            store.insert_observation_event(conflict),
            "identity_conflict",
        )
        self.assertEqual(store.get_observation_event(event.observation_id), event)

    def test_location_link_insert_roundtrip_and_immutable(self):
        store, path = self.open_store()
        event = self.event()
        self.assertEqual(store.insert_observation_event(event), "inserted")
        link = self.location_link(observation=event)

        self.assertEqual(
            store.insert_observation_location_link(link),
            "inserted",
        )
        self.assertEqual(
            store.get_observation_location_link(link.location_link_id),
            link,
        )

        store.close()
        with closing(sqlite3.connect(path)) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    UPDATE observation_location_links
                    SET operator_fix_id = ?
                    WHERE location_link_id = ?
                    """,
                    ("changed", link.location_link_id),
                )
            stored = connection.execute(
                """
                SELECT location_link_id, operator_fix_id
                FROM observation_location_links
                WHERE location_link_id = ?
                """,
                (link.location_link_id,),
            ).fetchone()
            self.assertEqual(stored[0], link.location_link_id)
            self.assertEqual(stored[1], link.operator_fix_id)

    def test_location_link_duplicate_and_identity_conflict(self):
        store, _ = self.open_store()
        event = self.event()
        self.assertEqual(store.insert_observation_event(event), "inserted")
        link = self.location_link(observation=event)

        self.assertEqual(
            store.insert_observation_location_link(link),
            "inserted",
        )
        self.assertEqual(
            store.insert_observation_location_link(link),
            "duplicate",
        )

        conflict = replace(link, operator_latitude=11.0)
        self.assertEqual(
            store.insert_observation_location_link(conflict),
            "identity_conflict",
        )
        self.assertEqual(
            store.get_observation_location_link(link.location_link_id),
            link,
        )

    def test_missing_parent_and_invalid_delta_leave_no_partial_rows(self):
        store, path = self.open_store()
        orphan_event = self.event()
        orphan_link = self.location_link(observation=orphan_event)

        with self.assertRaises(ValueError):
            store.insert_observation_location_link(orphan_link)
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM observation_location_links"
                ).fetchone()[0],
                0,
            )

        stored_event = self.event()
        self.assertEqual(
            store.insert_observation_event(stored_event),
            "inserted",
        )
        invalid_delta_link = replace(
            self.location_link(observation=stored_event),
            source_to_fix_delta_us=999_999,
        )

        with self.assertRaises(ValueError):
            store.insert_observation_location_link(invalid_delta_link)
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM observation_location_links"
                ).fetchone()[0],
                0,
            )

    def test_bootstrap_failure_rolls_back_completely(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "bootstrap_fail.sqlite"
            call_count = {"value": 0}

            def failing_bootstrap_execute(store, sql, params=()):
                call_count["value"] += 1
                if call_count["value"] == 3:
                    raise RuntimeError("bootstrap boom")
                return store._connection.execute(sql, params)

            with patch.object(
                ObservationStore,
                "_bootstrap_execute",
                new=failing_bootstrap_execute,
            ):
                with self.assertRaises(RuntimeError):
                    ObservationStore(path)

            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(
                    connection.execute("PRAGMA user_version").fetchone()[0],
                    0,
                )
                self.assertEqual(
                    self.table_names(path),
                    set(),
                )

    def test_noop_trigger_same_name_is_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "noop_trigger.sqlite"
            self.create_valid_schema(path)

            with closing(sqlite3.connect(path)) as connection:
                connection.execute("DROP TRIGGER observation_events_no_update")
                connection.execute(
                    """
                    CREATE TRIGGER observation_events_no_update
                    BEFORE UPDATE ON observation_events
                    WHEN 0
                    BEGIN
                        SELECT RAISE(ABORT, 'observation_events is immutable');
                    END
                    """
                )
                connection.commit()

            before = self.schema_snapshot(path)

            with self.assertRaises(ValueError):
                ObservationStore(path)

            self.assertEqual(self.schema_snapshot(path), before)
            self.assertEqual(
                self.table_names(path),
                {
                    "store_metadata",
                    "observation_events",
                    "observation_location_links",
                },
            )
            self.assertIn("WHEN 0", self.trigger_sql(path, "observation_events_no_update"))

    def test_missing_metadata_checks_are_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "missing_checks.sqlite"
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute(
                    """
                    CREATE TABLE store_metadata (
                        singleton INTEGER PRIMARY KEY,
                        store_schema_version INTEGER NOT NULL,
                        contract_schema_version TEXT NOT NULL,
                        initialized_at_us INTEGER NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE observation_events (
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
                )
                connection.execute(
                    """
                    CREATE TABLE observation_location_links (
                        location_link_id TEXT NOT NULL PRIMARY KEY,
                        schema_version TEXT NOT NULL,
                        record_kind TEXT NOT NULL,
                        observation_id TEXT NOT NULL REFERENCES observation_events (
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
                )
                connection.execute(
                    """
                    CREATE TRIGGER observation_events_no_update
                    BEFORE UPDATE ON observation_events
                    BEGIN
                        SELECT RAISE(ABORT, 'observation_events is immutable');
                    END
                    """
                )
                connection.execute(
                    """
                    CREATE TRIGGER observation_location_links_no_update
                    BEFORE UPDATE ON observation_location_links
                    BEGIN
                        SELECT RAISE(ABORT, 'observation_location_links is immutable');
                    END
                    """
                )
                connection.execute(
                    """
                    INSERT INTO store_metadata (
                        singleton,
                        store_schema_version,
                        contract_schema_version,
                        initialized_at_us
                    ) VALUES (1, 1, '1.0', 0)
                    """
                )
                connection.execute("PRAGMA user_version = 1")
                connection.commit()

            before = self.schema_snapshot(path)

            with self.assertRaises(ValueError):
                ObservationStore(path)

            self.assertEqual(self.schema_snapshot(path), before)
            self.assertEqual(
                self.table_names(path),
                {
                    "store_metadata",
                    "observation_events",
                    "observation_location_links",
                },
            )

    def test_altered_table_constraint_or_type_is_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "altered_table.sqlite"
            self.create_valid_schema(path)

            with closing(sqlite3.connect(path)) as connection:
                connection.execute("DROP TABLE observation_events")
                connection.execute(
                    """
                    CREATE TABLE observation_events (
                        observation_id TEXT NOT NULL PRIMARY KEY,
                        schema_version TEXT NOT NULL,
                        record_kind TEXT NOT NULL,
                        collection_session_id TEXT NOT NULL,
                        source_type TEXT NOT NULL,
                        sensor_id INTEGER NOT NULL,
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
                )
                connection.commit()

            before = self.schema_snapshot(path)

            with self.assertRaises(ValueError):
                ObservationStore(path)

            self.assertEqual(self.schema_snapshot(path), before)
            self.assertEqual(
                self.table_names(path),
                {
                    "store_metadata",
                    "observation_events",
                    "observation_location_links",
                },
            )
            self.assertEqual(
                self.table_info(path, "observation_events")[5],
                ("sensor_id", "INTEGER", 1, 0, None),
            )

    def test_absence_of_public_raw_connection_api(self):
        store, _ = self.open_store()
        with self.assertRaises(AttributeError):
            _ = store.connection

    def test_fake_aggregate_state_object_is_rejected(self):
        store, _ = self.open_store()
        fake_event = types.SimpleNamespace(
            observation_id="obs_v1_" + "0" * 64,
        )
        fake_link = types.SimpleNamespace(
            location_link_id="loc_v1_" + "0" * 64,
        )

        with self.assertRaises(ValueError):
            store.insert_observation_event(fake_event)
        with self.assertRaises(ValueError):
            store.insert_observation_location_link(fake_link)

    def test_connections_close_cleanly_without_resourcewarning(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", ResourceWarning)
            with tempfile.TemporaryDirectory() as tempdir:
                path = Path(tempdir) / "observations.sqlite"
                with ObservationStore(path) as store:
                    self.assertIsInstance(store, ObservationStore)
                del store
                gc.collect()


if __name__ == "__main__":
    unittest.main()
