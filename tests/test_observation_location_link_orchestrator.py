from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from observation_contract import (
    ObservationProvenanceV1,
    create_observation_event,
    create_observation_location_link,
    create_operator_fix,
)
from observation_location_link_orchestrator import (
    run_bounded_observation_location_link_correlation,
)
from observation_location_link_writer import (
    LocationLinkWriteSummaryV1,
)
from observation_store import ObservationStore


class ObservationLocationLinkOrchestratorTests(unittest.TestCase):
    KEY = b"synthetic-location-link-orchestrator-key"

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
            collector_name="cyt.location_link_orchestrator_test",
            collector_version="1.0",
            ingest_mode="replay",
            source_schema_version="synthetic-v1",
        )

    def event(
        self,
        *,
        reference="event_alpha",
        timestamp_us=100,
        session_id="session_alpha",
    ):
        return create_observation_event(
            hmac_key=self.KEY,
            collection_session_id=session_id,
            source_type="synthetic.orchestrator_event",
            sensor_id="event_sensor",
            source_timestamp_us=timestamp_us,
            ingest_timestamp_us=9_000_000,
            source_record_reference=reference,
            provenance=self.provenance(),
        )

    def fix(
        self,
        *,
        reference="fix_alpha",
        timestamp_us=110,
        session_id="session_alpha",
        latitude=51.5,
        longitude=7.4,
    ):
        return create_operator_fix(
            hmac_key=self.KEY,
            collection_session_id=session_id,
            source_type="synthetic.orchestrator_fix",
            sensor_id="gps_sensor",
            operator_fix_timestamp_us=timestamp_us,
            ingest_timestamp_us=9_000_100,
            source_record_reference=reference,
            provenance=self.provenance(),
            operator_latitude=latitude,
            operator_longitude=longitude,
            operator_location_accuracy_m=4.0,
        )

    def link(self, event, fix):
        return create_observation_location_link(
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

    def orchestrate(
        self,
        *,
        store,
        fixes,
        max_delta_us=1_000,
        collection_session_id=None,
    ):
        return run_bounded_observation_location_link_correlation(
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

    def test_empty_store_returns_zero_summary(self):
        store, _ = self.open_store()

        summary = self.orchestrate(
            store=store,
            fixes=(),
        )

        self.assertEqual(
            summary,
            LocationLinkWriteSummaryV1(
                total_candidates=0,
                inserted=0,
                duplicate=0,
                identity_conflict=0,
            ),
        )

    def test_plans_and_writes_bounded_candidate(self):
        store, _ = self.open_store()
        event = self.event(timestamp_us=100)
        fix = self.fix(timestamp_us=110)

        store.insert_observation_event(event)

        summary = self.orchestrate(
            store=store,
            fixes=(fix,),
            max_delta_us=10,
        )

        self.assertEqual(summary.total_candidates, 1)
        self.assertEqual(summary.inserted, 1)
        self.assertEqual(summary.duplicate, 0)
        self.assertEqual(summary.identity_conflict, 0)

        links = store.list_observation_location_links()

        self.assertEqual(len(links), 1)
        self.assertEqual(
            links[0].observation_id,
            event.observation_id,
        )
        self.assertEqual(
            links[0].operator_fix_id,
            fix.operator_fix_id,
        )
        self.assertEqual(
            links[0].source_to_fix_delta_us,
            10,
        )

    def test_replay_counts_existing_candidate_as_duplicate(self):
        store, _ = self.open_store()
        event = self.event()
        fix = self.fix()

        store.insert_observation_event(event)

        first = self.orchestrate(store=store, fixes=(fix,))
        second = self.orchestrate(store=store, fixes=(fix,))

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

    def test_collection_session_filter_limits_writes(self):
        store, _ = self.open_store()

        alpha = self.event(
            reference="alpha_event",
            timestamp_us=100,
            session_id="session_alpha",
        )
        beta = self.event(
            reference="beta_event",
            timestamp_us=200,
            session_id="session_beta",
        )

        alpha_fix = self.fix(
            reference="alpha_fix",
            timestamp_us=100,
            session_id="session_alpha",
        )
        beta_fix = self.fix(
            reference="beta_fix",
            timestamp_us=200,
            session_id="session_beta",
        )

        store.insert_observation_event(alpha)
        store.insert_observation_event(beta)

        summary = self.orchestrate(
            store=store,
            fixes=(alpha_fix, beta_fix),
            collection_session_id="session_beta",
        )

        self.assertEqual(summary.inserted, 1)

        links = store.list_observation_location_links()

        self.assertEqual(len(links), 1)
        self.assertEqual(
            links[0].observation_id,
            beta.observation_id,
        )

    def test_same_source_record_suppresses_bounded_write(self):
        store, _ = self.open_store()
        event = self.event()
        fix = self.fix(timestamp_us=100)

        store.insert_observation_event(event)

        same_source = create_observation_location_link(
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
        store.insert_observation_location_link(same_source)

        summary = self.orchestrate(
            store=store,
            fixes=(fix,),
        )

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
            (same_source,),
        )

    def test_out_of_window_produces_no_write(self):
        store, _ = self.open_store()
        event = self.event(timestamp_us=100)
        fix = self.fix(timestamp_us=201)

        store.insert_observation_event(event)

        summary = self.orchestrate(
            store=store,
            fixes=(fix,),
            max_delta_us=100,
        )

        self.assertEqual(summary.total_candidates, 0)
        self.assertEqual(
            store.list_observation_location_links(),
            (),
        )

    def test_invalid_max_delta_fails_before_write(self):
        store, path = self.open_store()
        event = self.event()
        fix = self.fix()

        store.insert_observation_event(event)
        before = self.snapshot(path)

        for value in (-1, True, 1.5):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.orchestrate(
                        store=store,
                        fixes=(fix,),
                        max_delta_us=value,
                    )

        after = self.snapshot(path)

        self.assertEqual(after, before)
        self.assertEqual(
            store.list_observation_location_links(),
            (),
        )

    def test_closed_store_fails(self):
        store, _ = self.open_store()
        store.close()

        with self.assertRaises(RuntimeError):
            self.orchestrate(
                store=store,
                fixes=(),
            )

    def test_delegates_planner_output_unchanged_to_writer(self):
        store, _ = self.open_store()
        event = self.event()
        fix = self.fix()
        candidate = self.link(event, fix)

        expected = LocationLinkWriteSummaryV1(
            total_candidates=1,
            inserted=1,
            duplicate=0,
            identity_conflict=0,
        )

        with patch(
            "observation_location_link_orchestrator."
            "plan_bounded_observation_location_links",
            return_value=(candidate,),
        ) as planner:
            with patch(
                "observation_location_link_orchestrator."
                "write_observation_location_link_candidates",
                return_value=expected,
            ) as writer:
                result = self.orchestrate(
                    store=store,
                    fixes=(fix,),
                    max_delta_us=25,
                    collection_session_id="session_alpha",
                )

        self.assertIs(result, expected)

        planner.assert_called_once_with(
            store=store,
            hmac_key=self.KEY,
            operator_fixes=(fix,),
            max_delta_us=25,
            collection_session_id="session_alpha",
        )
        writer.assert_called_once_with(
            store=store,
            candidates=(candidate,),
        )


if __name__ == "__main__":
    unittest.main()
