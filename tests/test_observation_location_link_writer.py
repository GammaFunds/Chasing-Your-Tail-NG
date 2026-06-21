from __future__ import annotations

from contextlib import closing
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from observation_contract import (
    ObservationProvenanceV1,
    create_observation_event,
    create_observation_location_link,
)
from observation_location_link_writer import (
    LocationLinkWriteSummaryV1,
    write_observation_location_link_candidates,
)
from observation_store import ObservationStore


class ObservationLocationLinkWriterTests(unittest.TestCase):
    KEY = b"synthetic-location-link-writer-key"

    def open_store(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)

        path = Path(tempdir.name) / "observations.sqlite"
        store = ObservationStore(path)
        self.addCleanup(store.close)

        return store, path

    @staticmethod
    def provenance():
        return ObservationProvenanceV1(
            collector_name="cyt.location_link_writer_test",
            collector_version="1.0",
            ingest_mode="replay",
            source_schema_version="synthetic-v1",
        )

    def event(self, *, reference="parent", timestamp_us=100):
        return create_observation_event(
            hmac_key=self.KEY,
            collection_session_id="session_alpha",
            source_type="synthetic.writer_event",
            sensor_id="event_sensor",
            source_timestamp_us=timestamp_us,
            ingest_timestamp_us=9_000_000,
            source_record_reference=reference,
            provenance=self.provenance(),
        )

    def link(
        self,
        event,
        *,
        fix_id="fix_alpha",
        fix_timestamp_us=110,
        latitude=51.5,
        longitude=7.4,
    ):
        return create_observation_location_link(
            hmac_key=self.KEY,
            observation=event,
            operator_fix_id=fix_id,
            operator_latitude=latitude,
            operator_longitude=longitude,
            operator_fix_timestamp_us=fix_timestamp_us,
            correlation_method="nearest_fix_bounded",
            correlation_version="1.0",
            operator_location_accuracy_m=4.0,
        )

    @staticmethod
    def snapshot(path):
        with closing(sqlite3.connect(path)) as connection:
            return tuple(connection.iterdump())

    @staticmethod
    def write(store, candidates):
        return write_observation_location_link_candidates(
            store=store,
            candidates=candidates,
        )

    def test_empty_batch_returns_zero_summary(self):
        store, _ = self.open_store()

        summary = self.write(store, ())

        self.assertEqual(
            summary,
            LocationLinkWriteSummaryV1(
                total_candidates=0,
                inserted=0,
                duplicate=0,
                identity_conflict=0,
            ),
        )
        self.assertEqual(
            store.list_observation_location_links(),
            (),
        )

    def test_single_candidate_is_inserted(self):
        store, _ = self.open_store()
        event = self.event()
        link = self.link(event)

        store.insert_observation_event(event)

        summary = self.write(store, (link,))

        self.assertEqual(summary.total_candidates, 1)
        self.assertEqual(summary.inserted, 1)
        self.assertEqual(summary.duplicate, 0)
        self.assertEqual(summary.identity_conflict, 0)
        self.assertEqual(
            store.list_observation_location_links(),
            (link,),
        )

    def test_replay_counts_duplicate(self):
        store, _ = self.open_store()
        event = self.event()
        link = self.link(event)

        store.insert_observation_event(event)

        first = self.write(store, (link,))
        second = self.write(store, (link,))

        self.assertEqual(first.inserted, 1)
        self.assertEqual(
            second,
            LocationLinkWriteSummaryV1(
                total_candidates=1,
                inserted=0,
                duplicate=1,
                identity_conflict=0,
            ),
        )

    def test_changed_link_facts_count_identity_conflict(self):
        store, _ = self.open_store()
        event = self.event()

        original = self.link(
            event,
            fix_id="shared_fix",
            latitude=51.5,
        )
        changed = self.link(
            event,
            fix_id="shared_fix",
            latitude=52.0,
        )

        self.assertEqual(
            original.location_link_id,
            changed.location_link_id,
        )
        self.assertNotEqual(original, changed)

        store.insert_observation_event(event)
        self.write(store, (original,))

        summary = self.write(store, (changed,))

        self.assertEqual(
            summary,
            LocationLinkWriteSummaryV1(
                total_candidates=1,
                inserted=0,
                duplicate=0,
                identity_conflict=1,
            ),
        )
        self.assertEqual(
            store.list_observation_location_links(),
            (original,),
        )

    def test_mixed_batch_counts_all_store_results(self):
        store, _ = self.open_store()

        first_event = self.event(reference="first_parent")
        second_event = self.event(reference="second_parent")

        first = self.link(
            first_event,
            fix_id="first_fix",
        )
        first_conflict = self.link(
            first_event,
            fix_id="first_fix",
            latitude=52.0,
        )
        second = self.link(
            second_event,
            fix_id="second_fix",
        )

        store.insert_observation_event(first_event)
        store.insert_observation_event(second_event)
        self.write(store, (first,))

        summary = self.write(
            store,
            (
                first,
                second,
                first_conflict,
            ),
        )

        self.assertEqual(
            summary,
            LocationLinkWriteSummaryV1(
                total_candidates=3,
                inserted=1,
                duplicate=1,
                identity_conflict=1,
            ),
        )

    def test_summary_is_frozen_and_validated(self):
        summary = LocationLinkWriteSummaryV1(
            total_candidates=3,
            inserted=1,
            duplicate=1,
            identity_conflict=1,
        )

        self.assertEqual(
            tuple(field.name for field in fields(summary)),
            (
                "total_candidates",
                "inserted",
                "duplicate",
                "identity_conflict",
            ),
        )

        with self.assertRaises(FrozenInstanceError):
            summary.inserted = 2

        invalid_values = (-1, True, 1.5)

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    LocationLinkWriteSummaryV1(
                        total_candidates=value,
                        inserted=0,
                        duplicate=0,
                        identity_conflict=0,
                    )

        with self.assertRaises(ValueError):
            LocationLinkWriteSummaryV1(
                total_candidates=2,
                inserted=1,
                duplicate=0,
                identity_conflict=0,
            )

    def test_invalid_store_is_rejected(self):
        with self.assertRaises(ValueError):
            self.write(object(), ())

    def test_invalid_candidate_batch_fails_before_writes(self):
        store, path = self.open_store()
        event = self.event()
        valid = self.link(event)

        store.insert_observation_event(event)
        before = self.snapshot(path)

        invalid_batches = (
            [valid],
            (valid, object()),
        )

        for candidates in invalid_batches:
            with self.subTest(candidates_type=type(candidates)):
                with self.assertRaises(ValueError):
                    self.write(store, candidates)

        after = self.snapshot(path)

        self.assertEqual(after, before)
        self.assertEqual(
            store.list_observation_location_links(),
            (),
        )

    def test_closed_store_fails(self):
        store, _ = self.open_store()
        event = self.event()
        link = self.link(event)

        store.close()

        with self.assertRaises(RuntimeError):
            self.write(store, (link,))

    def test_unexpected_store_result_fails_closed(self):
        store, _ = self.open_store()
        event = self.event()
        link = self.link(event)

        store.insert_observation_event(event)

        with patch.object(
            store,
            "insert_observation_location_link",
            return_value="unexpected",
        ):
            with self.assertRaises(RuntimeError):
                self.write(store, (link,))


if __name__ == "__main__":
    unittest.main()
