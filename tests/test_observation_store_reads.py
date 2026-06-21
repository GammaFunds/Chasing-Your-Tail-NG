from contextlib import closing
from dataclasses import FrozenInstanceError
from pathlib import Path
import sqlite3
import tempfile
import unittest

from observation_contract import (
    ObservationEventV1,
    ObservationLocationLinkV1,
    ObservationProvenanceV1,
    create_observation_event,
    create_observation_location_link,
)
from observation_store import ObservationStore


class ObservationStoreReadTests(unittest.TestCase):
    KEY = b"synthetic-observation-store-read-key"

    def open_store(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)

        path = Path(tempdir.name) / "observations.sqlite"
        store = ObservationStore(path)
        self.addCleanup(store.close)

        return store, path

    def event(
        self,
        reference,
        source_timestamp_us,
        *,
        collection_session_id="session_alpha",
    ):
        return create_observation_event(
            hmac_key=self.KEY,
            collection_session_id=collection_session_id,
            source_type="synthetic.read",
            sensor_id="sensor_alpha",
            source_timestamp_us=source_timestamp_us,
            ingest_timestamp_us=9_000_000,
            source_record_reference=reference,
            provenance=ObservationProvenanceV1(
                collector_name="cyt.store_read_test",
                collector_version="1.0",
                ingest_mode="replay",
                source_schema_version=(
                    "cyt.store-read-test.v1"
                ),
            ),
        )

    def link(
        self,
        event,
        fix_id,
        fix_timestamp_us,
    ):
        return create_observation_location_link(
            hmac_key=self.KEY,
            observation=event,
            operator_fix_id=fix_id,
            operator_latitude=51.5,
            operator_longitude=7.4,
            operator_fix_timestamp_us=fix_timestamp_us,
            correlation_method="nearest_fix_bounded",
            correlation_version="1.0",
            operator_location_accuracy_m=4.0,
        )

    @staticmethod
    def snapshot(path):
        with closing(sqlite3.connect(path)) as connection:
            schema = connection.execute(
                """
                SELECT type, name, sql
                FROM sqlite_master
                WHERE name NOT LIKE 'sqlite_%'
                ORDER BY type, name
                """
            ).fetchall()

            event_count = connection.execute(
                "SELECT COUNT(*) FROM observation_events"
            ).fetchone()[0]

            link_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM observation_location_links
                """
            ).fetchone()[0]

        return schema, event_count, link_count

    def test_list_events_empty_and_deterministically_ordered(self):
        store, _ = self.open_store()

        self.assertEqual(
            store.list_observation_events(),
            (),
        )

        events = (
            self.event("record_c", 300),
            self.event("record_a", 100),
            self.event("record_b", 100),
        )

        for event in (
            events[0],
            events[2],
            events[1],
        ):
            self.assertEqual(
                store.insert_observation_event(event),
                "inserted",
            )

        expected = tuple(
            sorted(
                events,
                key=lambda event: (
                    event.source_timestamp_us,
                    event.observation_id,
                ),
            )
        )

        self.assertEqual(
            store.list_observation_events(),
            expected,
        )

    def test_list_events_filters_collection_session(self):
        store, _ = self.open_store()

        alpha_events = (
            self.event(
                "alpha_two",
                200,
                collection_session_id="session_alpha",
            ),
            self.event(
                "alpha_one",
                100,
                collection_session_id="session_alpha",
            ),
        )
        beta_event = self.event(
            "beta_one",
            50,
            collection_session_id="session_beta",
        )

        for event in (*alpha_events, beta_event):
            store.insert_observation_event(event)

        expected = tuple(
            sorted(
                alpha_events,
                key=lambda event: (
                    event.source_timestamp_us,
                    event.observation_id,
                ),
            )
        )

        self.assertEqual(
            store.list_observation_events(
                collection_session_id="session_alpha"
            ),
            expected,
        )

        self.assertEqual(
            store.list_observation_events(
                collection_session_id="missing_session"
            ),
            (),
        )

    def test_list_links_empty_and_deterministically_ordered(self):
        store, _ = self.open_store()
        event = self.event("parent", 50)

        store.insert_observation_event(event)

        self.assertEqual(
            store.list_observation_location_links(),
            (),
        )

        links = (
            self.link(event, "fix_c", 300),
            self.link(event, "fix_a", 100),
            self.link(event, "fix_b", 100),
        )

        for link in (
            links[0],
            links[2],
            links[1],
        ):
            self.assertEqual(
                store.insert_observation_location_link(link),
                "inserted",
            )

        expected = tuple(
            sorted(
                links,
                key=lambda link: (
                    link.operator_fix_timestamp_us,
                    link.location_link_id,
                ),
            )
        )

        self.assertEqual(
            store.list_observation_location_links(),
            expected,
        )

    def test_list_links_filters_parent_observation(self):
        store, _ = self.open_store()

        first_event = self.event("first_parent", 100)
        second_event = self.event("second_parent", 200)

        first_link = self.link(
            first_event,
            "first_fix",
            110,
        )
        second_link = self.link(
            second_event,
            "second_fix",
            210,
        )

        for event in (first_event, second_event):
            store.insert_observation_event(event)

        for link in (second_link, first_link):
            store.insert_observation_location_link(link)

        self.assertEqual(
            store.list_observation_location_links(
                observation_id=first_event.observation_id
            ),
            (first_link,),
        )

        self.assertEqual(
            store.list_observation_location_links(
                observation_id=second_event.observation_id
            ),
            (second_link,),
        )

        self.assertEqual(
            store.list_observation_location_links(
                observation_id="obs_v1_"
                + ("0" * 64)
            ),
            (),
        )

    def test_read_results_are_tuples_of_frozen_contract_objects(self):
        store, _ = self.open_store()
        event = self.event("frozen_parent", 100)
        link = self.link(event, "frozen_fix", 110)

        store.insert_observation_event(event)
        store.insert_observation_location_link(link)

        events = store.list_observation_events()
        links = store.list_observation_location_links()

        self.assertIsInstance(events, tuple)
        self.assertIsInstance(links, tuple)
        self.assertIsInstance(events[0], ObservationEventV1)
        self.assertIsInstance(
            links[0],
            ObservationLocationLinkV1,
        )

        with self.assertRaises(FrozenInstanceError):
            events[0].sensor_id = "changed"

        with self.assertRaises(FrozenInstanceError):
            links[0].operator_fix_id = "changed"

    def test_invalid_filters_fail_closed(self):
        store, _ = self.open_store()

        invalid_values = (
            "",
            "   ",
            123,
            True,
        )

        for value in invalid_values:
            with self.subTest(
                method="events",
                value=value,
            ):
                with self.assertRaises(ValueError):
                    store.list_observation_events(
                        collection_session_id=value
                    )

            with self.subTest(
                method="links",
                value=value,
            ):
                with self.assertRaises(ValueError):
                    store.list_observation_location_links(
                        observation_id=value
                    )

    def test_read_methods_require_an_open_store(self):
        store, _ = self.open_store()
        store.close()

        with self.assertRaises(RuntimeError):
            store.list_observation_events()

        with self.assertRaises(RuntimeError):
            store.list_observation_location_links()

    def test_read_methods_do_not_mutate_store(self):
        store, path = self.open_store()
        event = self.event("immutable_read", 100)
        link = self.link(event, "immutable_fix", 110)

        store.insert_observation_event(event)
        store.insert_observation_location_link(link)

        before = self.snapshot(path)

        for _ in range(3):
            self.assertEqual(
                store.list_observation_events(),
                (event,),
            )
            self.assertEqual(
                store.list_observation_location_links(),
                (link,),
            )

        after = self.snapshot(path)

        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
