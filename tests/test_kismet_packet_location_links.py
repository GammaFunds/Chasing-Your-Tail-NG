from contextlib import closing
from dataclasses import FrozenInstanceError
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from kismet_packet_adapter import (
    KismetPacketAdapterError,
    KismetPacketLocationReplaySummaryV1,
    decode_kismet_packet_snapshot,
    decode_kismet_packet_snapshot_with_locations,
    replay_kismet_packet_snapshot_with_locations,
)
from observation_store import ObservationStore


class KismetPacketLocationLinkTests(unittest.TestCase):
    KEY = b"synthetic-kismet-location-test-key"

    def make_source(
        self,
        *,
        include_locations=True,
        rows=None,
    ):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)

        path = Path(tempdir.name) / "synthetic.kismet"

        location_columns = (
            ", lat REAL, lon REAL"
            if include_locations
            else ""
        )

        with closing(sqlite3.connect(path)) as connection:
            connection.execute(
                "CREATE TABLE KISMET (db_version INT)"
            )
            connection.execute(
                "INSERT INTO KISMET (db_version) VALUES (10)"
            )
            connection.execute(
                f"""
                CREATE TABLE packets (
                    ts_sec INT,
                    ts_usec INT,
                    sourcemac TEXT,
                    datasource TEXT,
                    error INT,
                    hash INT,
                    packetid INT
                    {location_columns}
                )
                """
            )

            for row in rows or []:
                if include_locations:
                    connection.execute(
                        """
                        INSERT INTO packets (
                            ts_sec,
                            ts_usec,
                            sourcemac,
                            datasource,
                            error,
                            hash,
                            packetid,
                            lat,
                            lon
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                            hash,
                            packetid
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
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

        return decode_kismet_packet_snapshot_with_locations(
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

        return replay_kismet_packet_snapshot_with_locations(
            path,
            **values,
        )

    @staticmethod
    def counts(path):
        with closing(sqlite3.connect(path)) as connection:
            events = connection.execute(
                "SELECT COUNT(*) FROM observation_events"
            ).fetchone()[0]
            links = connection.execute(
                "SELECT COUNT(*) "
                "FROM observation_location_links"
            ).fetchone()[0]

        return events, links

    def standard_row(
        self,
        *,
        ts_usec=1,
        error=0,
        latitude=51.5,
        longitude=7.4,
    ):
        return (
            100,
            ts_usec,
            "02:11:22:33:44:55",
            "11111111-2222-3333-4444-555555555555",
            error,
            10,
            1,
            latitude,
            longitude,
        )

    def test_decode_creates_same_packet_location_link(self):
        path = self.make_source(
            rows=[self.standard_row()]
        )

        record = self.decode(path)[0]
        event = record.event
        link = record.location_link

        self.assertIsNotNone(link)
        self.assertEqual(
            link.observation_id,
            event.observation_id,
        )
        self.assertEqual(
            link.operator_fix_timestamp_us,
            event.source_timestamp_us,
        )
        self.assertEqual(link.source_to_fix_delta_us, 0)
        self.assertEqual(
            link.correlation_method,
            "same_source_record",
        )
        self.assertEqual(link.correlation_version, "1.0")
        self.assertEqual(link.operator_latitude, 51.5)
        self.assertEqual(link.operator_longitude, 7.4)
        self.assertIsNone(
            link.operator_location_accuracy_m
        )
        self.assertTrue(
            link.operator_fix_id.startswith(
                event.observation_id
            )
        )
        self.assertNotIn(
            event.device_identifier,
            link.operator_fix_id,
        )
        self.assertNotIn(
            event.sensor_id,
            link.operator_fix_id,
        )

    def test_missing_and_zero_coordinates_create_no_link(self):
        path = self.make_source(
            rows=[
                self.standard_row(
                    latitude=None,
                    longitude=None,
                ),
                self.standard_row(
                    ts_usec=2,
                    latitude=0.0,
                    longitude=7.4,
                ),
                self.standard_row(
                    ts_usec=3,
                    latitude=51.5,
                    longitude=0.0,
                ),
            ]
        )

        records = self.decode(path)

        self.assertEqual(len(records), 3)
        self.assertTrue(
            all(
                record.location_link is None
                for record in records
            )
        )

    def test_missing_location_schema_fails_only_located_api(self):
        path = self.make_source(
            include_locations=False,
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

        events = decode_kismet_packet_snapshot(
            path,
            hmac_key=self.KEY,
            collection_session_id="collection_alpha",
            ingest_timestamp_us=9_000_000,
        )

        self.assertEqual(len(events), 1)

        with self.assertRaises(KismetPacketAdapterError):
            self.decode(path)

    def test_invalid_later_location_fails_before_writes(self):
        source = self.make_source(
            rows=[
                self.standard_row(),
                self.standard_row(
                    ts_usec=2,
                    latitude=91.0,
                ),
            ]
        )
        store, store_path = self.open_store()

        with self.assertRaises(KismetPacketAdapterError):
            self.replay(source, store)

        self.assertEqual(
            self.counts(store_path),
            (0, 0),
        )

    def test_replay_insert_then_duplicate_counts(self):
        source = self.make_source(
            rows=[self.standard_row()]
        )
        store, store_path = self.open_store()

        first = self.replay(source, store)
        second = self.replay(source, store)

        self.assertEqual(
            first,
            KismetPacketLocationReplaySummaryV1(
                total_rows=1,
                events_inserted=1,
                events_duplicate=0,
                events_identity_conflict=0,
                location_rows=1,
                links_inserted=1,
                links_duplicate=0,
                links_identity_conflict=0,
                links_skipped_event_conflict=0,
            ),
        )
        self.assertEqual(
            second,
            KismetPacketLocationReplaySummaryV1(
                total_rows=1,
                events_inserted=0,
                events_duplicate=1,
                events_identity_conflict=0,
                location_rows=1,
                links_inserted=0,
                links_duplicate=1,
                links_identity_conflict=0,
                links_skipped_event_conflict=0,
            ),
        )
        self.assertEqual(
            self.counts(store_path),
            (1, 1),
        )

    def test_changed_location_conflicts_with_duplicate_event(self):
        first_source = self.make_source(
            rows=[self.standard_row(latitude=51.5)]
        )
        changed_source = self.make_source(
            rows=[self.standard_row(latitude=51.6)]
        )
        store, _ = self.open_store()

        first = self.replay(first_source, store)
        changed = self.replay(changed_source, store)

        self.assertEqual(first.events_inserted, 1)
        self.assertEqual(first.links_inserted, 1)
        self.assertEqual(changed.events_duplicate, 1)
        self.assertEqual(
            changed.links_identity_conflict,
            1,
        )

    def test_event_conflict_skips_location_link(self):
        first_source = self.make_source(
            rows=[self.standard_row(ts_usec=1)]
        )
        changed_source = self.make_source(
            rows=[self.standard_row(ts_usec=2)]
        )
        store, store_path = self.open_store()

        first = self.replay(first_source, store)
        changed = self.replay(changed_source, store)

        self.assertEqual(first.events_inserted, 1)
        self.assertEqual(first.links_inserted, 1)
        self.assertEqual(
            changed.events_identity_conflict,
            1,
        )
        self.assertEqual(
            changed.links_skipped_event_conflict,
            1,
        )
        self.assertEqual(
            self.counts(store_path),
            (1, 1),
        )

    def test_error_rows_are_excluded(self):
        source = self.make_source(
            rows=[
                self.standard_row(error=1),
                self.standard_row(
                    ts_usec=2,
                    error=0,
                ),
            ]
        )

        records = self.decode(source)

        self.assertEqual(len(records), 1)
        self.assertEqual(
            records[0].event.source_timestamp_us,
            100_000_002,
        )

    def test_located_decode_uses_readonly_uri(self):
        source = self.make_source(
            rows=[self.standard_row()]
        )
        real_connect = sqlite3.connect

        with patch(
            "kismet_packet_adapter.sqlite3.connect",
            wraps=real_connect,
        ) as mocked:
            self.decode(source)

        args, kwargs = mocked.call_args

        self.assertIn("?mode=ro", args[0])
        self.assertTrue(kwargs["uri"])

    def test_summary_is_frozen_and_validated(self):
        summary = KismetPacketLocationReplaySummaryV1(
            total_rows=1,
            events_inserted=1,
            events_duplicate=0,
            events_identity_conflict=0,
            location_rows=1,
            links_inserted=1,
            links_duplicate=0,
            links_identity_conflict=0,
            links_skipped_event_conflict=0,
        )

        with self.assertRaises(FrozenInstanceError):
            summary.links_inserted = 2

        with self.assertRaises(ValueError):
            KismetPacketLocationReplaySummaryV1(
                total_rows=1,
                events_inserted=1,
                events_duplicate=1,
                events_identity_conflict=0,
                location_rows=0,
                links_inserted=0,
                links_duplicate=0,
                links_identity_conflict=0,
                links_skipped_event_conflict=0,
            )

        with self.assertRaises(ValueError):
            KismetPacketLocationReplaySummaryV1(
                total_rows=1,
                events_inserted=1,
                events_duplicate=0,
                events_identity_conflict=0,
                location_rows=1,
                links_inserted=0,
                links_duplicate=0,
                links_identity_conflict=0,
                links_skipped_event_conflict=0,
            )

    def test_errors_do_not_expose_identifiers_or_paths(self):
        private_identifier = "private-device-identifier"
        private_source = "private-source-identifier"

        row = (
            100,
            1,
            private_identifier,
            private_source,
            0,
            10,
            1,
            "invalid-latitude",
            7.4,
        )
        path = self.make_source(rows=[row])

        with self.assertRaises(
            KismetPacketAdapterError
        ) as context:
            self.decode(path)

        message = str(context.exception)

        self.assertNotIn(private_identifier, message)
        self.assertNotIn(private_source, message)
        self.assertNotIn(str(path), message)

    def test_unexpected_event_store_result_fails_closed(self):
        source = self.make_source(
            rows=[self.standard_row()]
        )
        store, store_path = self.open_store()

        with patch.object(
            store,
            "insert_observation_event",
            return_value="unexpected",
        ):
            with self.assertRaises(RuntimeError):
                self.replay(source, store)

        self.assertEqual(
            self.counts(store_path),
            (0, 0),
        )


if __name__ == "__main__":
    unittest.main()
