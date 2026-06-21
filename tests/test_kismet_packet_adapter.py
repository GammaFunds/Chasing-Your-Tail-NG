from contextlib import closing
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from kismet_packet_adapter import (
    KismetPacketAdapterError,
    KismetPacketReplaySummaryV1,
    decode_kismet_packet_snapshot,
    replay_kismet_packet_snapshot,
)
from observation_store import ObservationStore


class KismetPacketAdapterTests(unittest.TestCase):
    KEY = b"synthetic-kismet-packet-test-key"

    def make_source(
        self,
        *,
        db_version=10,
        include_packetid=True,
        rows=None,
    ):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)

        path = Path(tempdir.name) / "synthetic.kismet"

        packetid_column = (
            ", packetid INT"
            if include_packetid
            else ""
        )

        with closing(sqlite3.connect(path)) as connection:
            connection.execute(
                "CREATE TABLE KISMET (db_version INT)"
            )
            connection.execute(
                "INSERT INTO KISMET (db_version) VALUES (?)",
                (db_version,),
            )
            connection.execute(
                f"""
                CREATE TABLE packets (
                    ts_sec INT,
                    ts_usec INT,
                    sourcemac TEXT,
                    datasource TEXT,
                    error INT,
                    hash INT
                    {packetid_column}
                )
                """
            )

            for row in rows or []:
                if include_packetid:
                    connection.execute(
                        """
                        INSERT INTO packets (
                            ts_sec,
                            ts_usec,
                            sourcemac,
                            datasource,
                            error,
                            hash,
                            packetid
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        row,
                    )
                else:
                    connection.execute(
                        """
                        INSERT INTO packets (
                            ts_sec,
                            ts_usec,
                            sourcemac,
                            datasource,
                            error,
                            hash
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        row,
                    )

            connection.commit()

        return path

    def open_store(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)

        path = Path(tempdir.name) / "observations.sqlite"
        store = ObservationStore(path)
        self.addCleanup(store.close)

        return store, path

    def decode(self, path, **overrides):
        values = {
            "hmac_key": self.KEY,
            "collection_session_id": "collection_alpha",
            "ingest_timestamp_us": 9_000_000,
        }
        values.update(overrides)

        return decode_kismet_packet_snapshot(
            path,
            **values,
        )

    def replay(self, path, store, **overrides):
        values = {
            "store": store,
            "hmac_key": self.KEY,
            "collection_session_id": "collection_alpha",
            "ingest_timestamp_us": 9_000_000,
        }
        values.update(overrides)

        return replay_kismet_packet_snapshot(
            path,
            **values,
        )

    @staticmethod
    def event_count(path):
        with closing(sqlite3.connect(path)) as connection:
            return connection.execute(
                "SELECT COUNT(*) FROM observation_events"
            ).fetchone()[0]

    def test_decode_maps_packet_fields_and_timestamp(self):
        datasource = (
            "11111111-2222-3333-4444-555555555555"
        )
        mac = "02:11:22:33:44:55"

        path = self.make_source(
            rows=[
                (
                    1_700_000_000,
                    123_456,
                    mac,
                    datasource,
                    0,
                    1234,
                    7,
                )
            ]
        )

        event = self.decode(path)[0]

        self.assertEqual(
            event.source_timestamp_us,
            1_700_000_000_123_456,
        )
        self.assertEqual(event.source_type, "kismet.packet")
        self.assertEqual(event.sensor_id, datasource)
        self.assertEqual(event.device_identifier, mac)
        self.assertEqual(
            event.device_identifier_kind,
            "mac",
        )
        self.assertIsNone(event.signal_strength)
        self.assertEqual(
            json.loads(event.source_record_reference),
            ["kismet.packet.v1", 10, 1, 1234, 7],
        )
        self.assertNotIn(
            datasource,
            event.source_record_reference,
        )
        self.assertNotIn(
            mac,
            event.source_record_reference,
        )
        self.assertEqual(
            event.provenance.collector_name,
            "cyt.kismet_packet_adapter",
        )
        self.assertEqual(
            event.provenance.ingest_mode,
            "import",
        )

    def test_zero_source_mac_is_omitted(self):
        path = self.make_source(
            rows=[
                (
                    100,
                    1,
                    "00:00:00:00:00:00",
                    "11111111-2222-3333-4444-555555555555",
                    0,
                    10,
                    1,
                )
            ]
        )

        event = self.decode(path)[0]

        self.assertIsNone(event.device_identifier)
        self.assertIsNone(event.device_identifier_kind)

    def test_readonly_uri_is_used(self):
        path = self.make_source(
            rows=[
                (
                    100,
                    1,
                    "02:11:22:33:44:55",
                    "11111111-2222-3333-4444-555555555555",
                    0,
                    10,
                    1,
                )
            ]
        )

        real_connect = sqlite3.connect

        with patch(
            "kismet_packet_adapter.sqlite3.connect",
            wraps=real_connect,
        ) as mocked:
            self.decode(path)

        args, kwargs = mocked.call_args

        self.assertIn("?mode=ro", args[0])
        self.assertTrue(kwargs["uri"])

    def test_versions_8_through_10_are_supported(self):
        for version in (8, 9, 10):
            with self.subTest(version=version):
                path = self.make_source(
                    db_version=version,
                    rows=[
                        (
                            100,
                            1,
                            "02:11:22:33:44:55",
                            "11111111-2222-3333-4444-555555555555",
                            0,
                            10,
                            1,
                        )
                    ],
                )

                self.assertEqual(len(self.decode(path)), 1)

    def test_unsupported_versions_fail(self):
        for version in (7, 11):
            with self.subTest(version=version):
                path = self.make_source(
                    db_version=version
                )

                with self.assertRaises(
                    KismetPacketAdapterError
                ):
                    self.decode(path)

    def test_missing_required_schema_fails(self):
        path = self.make_source(
            include_packetid=False
        )

        with self.assertRaises(KismetPacketAdapterError):
            self.decode(path)

    def test_error_rows_are_out_of_scope(self):
        path = self.make_source(
            rows=[
                (
                    100,
                    1,
                    "02:11:22:33:44:55",
                    "11111111-2222-3333-4444-555555555555",
                    1,
                    10,
                    1,
                ),
                (
                    101,
                    2,
                    "02:11:22:33:44:56",
                    "11111111-2222-3333-4444-555555555555",
                    0,
                    11,
                    2,
                ),
            ]
        )

        events = self.decode(path)

        self.assertEqual(len(events), 1)
        self.assertEqual(
            events[0].source_timestamp_us,
            101_000_002,
        )

    def test_invalid_later_row_fails_before_writes(self):
        source = self.make_source(
            rows=[
                (
                    100,
                    1,
                    "02:11:22:33:44:55",
                    "11111111-2222-3333-4444-555555555555",
                    0,
                    10,
                    1,
                ),
                (
                    101,
                    1_000_000,
                    "02:11:22:33:44:56",
                    "11111111-2222-3333-4444-555555555555",
                    0,
                    11,
                    2,
                ),
            ]
        )
        store, store_path = self.open_store()

        with self.assertRaises(KismetPacketAdapterError):
            self.replay(source, store)

        self.assertEqual(self.event_count(store_path), 0)

    def test_replay_insert_then_duplicate(self):
        source = self.make_source(
            rows=[
                (
                    100,
                    1,
                    "02:11:22:33:44:55",
                    "11111111-2222-3333-4444-555555555555",
                    0,
                    10,
                    1,
                )
            ]
        )
        store, _ = self.open_store()

        first = self.replay(source, store)
        second = self.replay(source, store)

        self.assertEqual(
            first,
            KismetPacketReplaySummaryV1(
                total_rows=1,
                inserted=1,
                duplicate=0,
                identity_conflict=0,
            ),
        )
        self.assertEqual(
            second,
            KismetPacketReplaySummaryV1(
                total_rows=1,
                inserted=0,
                duplicate=1,
                identity_conflict=0,
            ),
        )

    def test_same_reference_changed_source_fact_conflicts(self):
        datasource = (
            "11111111-2222-3333-4444-555555555555"
        )

        first_source = self.make_source(
            rows=[
                (
                    100,
                    1,
                    "02:11:22:33:44:55",
                    datasource,
                    0,
                    10,
                    1,
                )
            ]
        )
        second_source = self.make_source(
            rows=[
                (
                    100,
                    2,
                    "02:11:22:33:44:55",
                    datasource,
                    0,
                    10,
                    1,
                )
            ]
        )
        store, _ = self.open_store()

        first = self.replay(first_source, store)
        second = self.replay(second_source, store)

        self.assertEqual(first.inserted, 1)
        self.assertEqual(second.identity_conflict, 1)

    def test_summary_is_frozen_and_validated(self):
        summary = KismetPacketReplaySummaryV1(
            total_rows=2,
            inserted=1,
            duplicate=1,
            identity_conflict=0,
        )

        with self.assertRaises(FrozenInstanceError):
            summary.inserted = 2

        with self.assertRaises(ValueError):
            KismetPacketReplaySummaryV1(
                total_rows=1,
                inserted=1,
                duplicate=1,
                identity_conflict=0,
            )

    def test_errors_do_not_expose_identifiers_or_paths(self):
        private_identifier = "private-device-identifier"
        private_source = (
            "private-source-identifier"
        )

        path = self.make_source(
            rows=[
                (
                    100,
                    1_000_000,
                    private_identifier,
                    private_source,
                    0,
                    10,
                    1,
                )
            ]
        )

        with self.assertRaises(
            KismetPacketAdapterError
        ) as context:
            self.decode(path)

        message = str(context.exception)

        self.assertNotIn(private_identifier, message)
        self.assertNotIn(private_source, message)
        self.assertNotIn(str(path), message)


if __name__ == "__main__":
    unittest.main()
