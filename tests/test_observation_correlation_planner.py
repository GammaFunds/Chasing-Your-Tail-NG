from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from observation_contract import (
    ObservationProvenanceV1,
    create_observation_event,
    create_observation_location_link,
    create_operator_fix,
)
from observation_correlation_planner import (
    plan_bounded_observation_location_links,
)
from observation_store import ObservationStore


class ObservationCorrelationPlannerTests(unittest.TestCase):
    KEY = b"synthetic-correlation-planner-key"

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
            collector_name="cyt.correlation_planner_test",
            collector_version="1.0",
            ingest_mode="replay",
            source_schema_version="synthetic-v1",
        )

    def event(
        self,
        *,
        reference,
        timestamp_us,
        session_id="session_alpha",
    ):
        return create_observation_event(
            hmac_key=self.KEY,
            collection_session_id=session_id,
            source_type="synthetic.planner_event",
            sensor_id="event_sensor",
            source_timestamp_us=timestamp_us,
            ingest_timestamp_us=9_000_000,
            source_record_reference=reference,
            provenance=self.provenance(),
        )

    def fix(
        self,
        *,
        reference,
        timestamp_us,
        session_id="session_alpha",
        latitude=51.5,
        longitude=7.4,
    ):
        return create_operator_fix(
            hmac_key=self.KEY,
            collection_session_id=session_id,
            source_type="synthetic.planner_fix",
            sensor_id="gps_sensor",
            operator_fix_timestamp_us=timestamp_us,
            ingest_timestamp_us=9_000_100,
            source_record_reference=reference,
            provenance=self.provenance(),
            operator_latitude=latitude,
            operator_longitude=longitude,
            operator_location_accuracy_m=4.0,
        )

    def plan(
        self,
        *,
        store,
        fixes,
        max_delta_us=1_000,
        collection_session_id=None,
    ):
        return plan_bounded_observation_location_links(
            store=store,
            hmac_key=self.KEY,
            operator_fixes=tuple(fixes),
            max_delta_us=max_delta_us,
            collection_session_id=collection_session_id,
        )

    @staticmethod
    def snapshot(path):
        with closing(sqlite3.connect(path)) as connection:
            return tuple(connection.iterdump())

    def test_empty_store_returns_empty_tuple(self):
        store, _ = self.open_store()

        result = self.plan(
            store=store,
            fixes=(
                self.fix(
                    reference="unused_fix",
                    timestamp_us=100,
                ),
            ),
        )

        self.assertEqual(result, ())
        self.assertIsInstance(result, tuple)

    def test_reads_events_and_returns_bounded_candidates(self):
        store, _ = self.open_store()

        earlier = self.event(
            reference="event_earlier",
            timestamp_us=100,
        )
        later = self.event(
            reference="event_later",
            timestamp_us=300,
        )

        store.insert_observation_event(later)
        store.insert_observation_event(earlier)

        first_fix = self.fix(
            reference="fix_first",
            timestamp_us=110,
        )
        second_fix = self.fix(
            reference="fix_second",
            timestamp_us=290,
        )

        links = self.plan(
            store=store,
            fixes=(second_fix, first_fix),
            max_delta_us=20,
        )

        self.assertEqual(
            tuple(link.observation_id for link in links),
            (
                earlier.observation_id,
                later.observation_id,
            ),
        )
        self.assertEqual(
            tuple(link.source_to_fix_delta_us for link in links),
            (10, -10),
        )
        self.assertTrue(
            all(
                link.correlation_method
                == "nearest_fix_bounded"
                for link in links
            )
        )
        self.assertTrue(
            all(
                link.correlation_version == "1.0"
                for link in links
            )
        )

    def test_collection_session_filter_limits_candidates(self):
        store, _ = self.open_store()

        alpha = self.event(
            reference="alpha_event",
            timestamp_us=100,
            session_id="session_alpha",
        )
        beta = self.event(
            reference="beta_event",
            timestamp_us=100,
            session_id="session_beta",
        )

        store.insert_observation_event(alpha)
        store.insert_observation_event(beta)

        fixes = (
            self.fix(
                reference="alpha_fix",
                timestamp_us=100,
                session_id="session_alpha",
            ),
            self.fix(
                reference="beta_fix",
                timestamp_us=100,
                session_id="session_beta",
            ),
        )

        links = self.plan(
            store=store,
            fixes=fixes,
            collection_session_id="session_beta",
        )

        self.assertEqual(len(links), 1)
        self.assertEqual(
            links[0].observation_id,
            beta.observation_id,
        )

    def test_stored_same_source_record_link_suppresses_parent(self):
        store, _ = self.open_store()

        event = self.event(
            reference="same_source_parent",
            timestamp_us=100,
        )
        fix = self.fix(
            reference="bounded_fix",
            timestamp_us=100,
        )

        store.insert_observation_event(event)

        same_source_link = create_observation_location_link(
            hmac_key=self.KEY,
            observation=event,
            operator_fix_id=(
                event.observation_id + ".same_packet_fix_v1"
            ),
            operator_latitude=51.5,
            operator_longitude=7.4,
            operator_fix_timestamp_us=100,
            correlation_method="same_source_record",
            correlation_version="1.0",
        )
        store.insert_observation_location_link(
            same_source_link
        )

        self.assertEqual(
            self.plan(store=store, fixes=(fix,)),
            (),
        )

    def test_other_stored_method_does_not_suppress_candidate(self):
        store, _ = self.open_store()

        event = self.event(
            reference="legacy_parent",
            timestamp_us=100,
        )
        old_fix = self.fix(
            reference="old_fix",
            timestamp_us=100,
        )
        new_fix = self.fix(
            reference="new_fix",
            timestamp_us=101,
        )

        store.insert_observation_event(event)

        legacy_link = create_observation_location_link(
            hmac_key=self.KEY,
            observation=event,
            operator_fix_id=old_fix.operator_fix_id,
            operator_latitude=old_fix.operator_latitude,
            operator_longitude=old_fix.operator_longitude,
            operator_fix_timestamp_us=(
                old_fix.operator_fix_timestamp_us
            ),
            correlation_method="legacy_nearest",
            correlation_version="1.0",
        )
        store.insert_observation_location_link(legacy_link)

        links = self.plan(
            store=store,
            fixes=(new_fix,),
        )

        self.assertEqual(len(links), 1)
        self.assertEqual(
            links[0].operator_fix_id,
            new_fix.operator_fix_id,
        )

    def test_existing_identical_bounded_link_remains_candidate(self):
        store, _ = self.open_store()

        event = self.event(
            reference="bounded_parent",
            timestamp_us=100,
        )
        fix = self.fix(
            reference="bounded_fix",
            timestamp_us=105,
        )

        store.insert_observation_event(event)

        existing = create_observation_location_link(
            hmac_key=self.KEY,
            observation=event,
            operator_fix_id=fix.operator_fix_id,
            operator_latitude=fix.operator_latitude,
            operator_longitude=fix.operator_longitude,
            operator_fix_timestamp_us=(
                fix.operator_fix_timestamp_us
            ),
            correlation_method="nearest_fix_bounded",
            correlation_version="1.0",
            operator_location_accuracy_m=(
                fix.operator_location_accuracy_m
            ),
        )
        store.insert_observation_location_link(existing)

        self.assertEqual(
            self.plan(store=store, fixes=(fix,)),
            (existing,),
        )

    def test_planning_is_read_only_and_repeatable(self):
        store, path = self.open_store()

        event = self.event(
            reference="immutable_parent",
            timestamp_us=100,
        )
        fix = self.fix(
            reference="immutable_fix",
            timestamp_us=110,
        )
        store.insert_observation_event(event)

        before = self.snapshot(path)

        first = self.plan(
            store=store,
            fixes=(fix,),
        )
        second = self.plan(
            store=store,
            fixes=(fix,),
        )

        after = self.snapshot(path)

        self.assertEqual(first, second)
        self.assertEqual(after, before)
        self.assertEqual(
            store.list_observation_location_links(),
            (),
        )

    def test_invalid_session_filter_fails_closed(self):
        store, _ = self.open_store()

        for value in ("", "   ", 123, True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.plan(
                        store=store,
                        fixes=(),
                        collection_session_id=value,
                    )

    def test_closed_store_fails(self):
        store, _ = self.open_store()
        store.close()

        with self.assertRaises(RuntimeError):
            self.plan(
                store=store,
                fixes=(),
            )

    def test_invalid_max_delta_fails_closed(self):
        store, _ = self.open_store()

        for value in (-1, True, 1.5):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.plan(
                        store=store,
                        fixes=(),
                        max_delta_us=value,
                    )


if __name__ == "__main__":
    unittest.main()
