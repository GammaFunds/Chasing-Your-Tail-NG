from contextlib import closing
from dataclasses import FrozenInstanceError
from pathlib import Path
import sqlite3
import tempfile
import unittest

from alert_contract import (
    AlertEvidenceV1,
    AlertTransitionV1,
    AlertV1,
)

from alert_store import AlertStore

from tests.test_alert_contract import (
    HMAC_KEY_A,
    TS_A,
    TS_B,
    TS_C,
    HEX_A,
    HEX_B,
    HEX_C,
    HEX_D,
    HEX_E,
    make_provenance,
    make_alert,
    make_evidence,
    make_transition,
)


class AlertStoreReadTests(unittest.TestCase):

    @staticmethod
    def open_store():
        tempdir = tempfile.TemporaryDirectory()
        path = Path(tempdir.name) / "alerts_read.sqlite"
        store = AlertStore(path)
        return store, path, tempdir

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

            alert_count = connection.execute(
                "SELECT COUNT(*) FROM alerts"
            ).fetchone()[0]
            evidence_count = connection.execute(
                "SELECT COUNT(*) FROM evidence"
            ).fetchone()[0]
            transition_count = connection.execute(
                "SELECT COUNT(*) FROM transitions"
            ).fetchone()[0]

        return schema, alert_count, evidence_count, transition_count

    # ── Alerts listing ──────────────────────────────────────────────────

    def test_list_alerts_empty_and_deterministically_ordered(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        self.assertEqual(store.list_alerts(), ())

        alerts = (
            make_alert(
                subject_reference=HEX_A,
                first_observed_source_timestamp_us=300,
            ),
            make_alert(
                subject_reference=HEX_B,
                first_observed_source_timestamp_us=100,
            ),
        )

        for a in (alerts[0], alerts[1]):
            self.assertEqual(store.insert_alert(a), "inserted")

        expected = tuple(
            sorted(
                alerts,
                key=lambda a: (
                    a.first_observed_source_timestamp_us,
                    a.alert_id,
                ),
            )
        )
        self.assertEqual(store.list_alerts(), expected)

    def test_list_alerts_filtered_by_dedup_key(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert_a = make_alert()
        alert_b = make_alert(
            analysis_type="pattern.anomaly",
        )

        self.assertEqual(store.insert_alert(alert_a), "inserted")
        self.assertEqual(store.insert_alert(alert_b), "inserted")

        filtered = store.list_alerts(
            deduplication_key=alert_a.deduplication_key,
        )
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].alert_id, alert_a.alert_id)

        self.assertEqual(
            store.list_alerts(
                deduplication_key=ID_PREFIX_DEDUP_KEY + "f" * 64,
            ),
            (),
        )

    # ── Evidence listing ────────────────────────────────────────────────

    def test_list_evidence_empty_and_deterministically_ordered(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        self.assertEqual(store.list_alert_evidence(), ())

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")

        evidence_items = (
            make_evidence(
                alert=alert,
                evidence_reference=HEX_C,
                observed_source_timestamp_us=300,
            ),
            make_evidence(
                alert=alert,
                evidence_reference=HEX_D,
                observed_source_timestamp_us=100,
            ),
        )

        for e in (evidence_items[0], evidence_items[1]):
            self.assertEqual(
                store.insert_alert_evidence(e),
                "inserted",
            )

        expected = tuple(
            sorted(
                evidence_items,
                key=lambda e: (
                    e.observed_source_timestamp_us,
                    e.evidence_id,
                ),
            )
        )
        self.assertEqual(
            store.list_alert_evidence(),
            expected,
        )

    def test_list_evidence_filtered_by_alert_id(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert_a = make_alert(subject_reference=HEX_A)
        alert_b = make_alert(
            HMAC_KEY_A,
            subject_reference=HEX_E,
        )
        self.assertEqual(store.insert_alert(alert_a), "inserted")
        self.assertEqual(store.insert_alert(alert_b), "inserted")

        evidence_a = make_evidence(
            alert=alert_a,
            evidence_reference=HEX_C,
        )
        evidence_b = make_evidence(
            alert=alert_b,
            evidence_reference=HEX_D,
        )

        for e in (evidence_a, evidence_b):
            self.assertEqual(
                store.insert_alert_evidence(e),
                "inserted",
            )

        self.assertEqual(
            store.list_alert_evidence(alert_id=alert_a.alert_id),
            (evidence_a,),
        )
        self.assertEqual(
            store.list_alert_evidence(
                alert_id=ID_PREFIX_ALERT_ID + "f" * 64,
            ),
            (),
        )

    # ── Transitions listing ─────────────────────────────────────────────

    def test_list_transitions_empty_and_deterministically_ordered(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        self.assertEqual(store.list_alert_transitions(), ())

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")

        first = make_transition(
            alert=alert,
            from_state="new",
            to_state="acknowledged",
            transition_reference=HEX_D,
            transitioned_at_us=TS_A,
        )
        second = make_transition(
            alert=alert,
            from_state="acknowledged",
            to_state="observing",
            transition_reference=HEX_E,
            transitioned_at_us=TS_C,
            previous_transition_id=first.transition_id,
        )

        # Insert out of expected order
        store.insert_alert_transition(first)
        store.insert_alert_transition(second)

        transitions = (first, second)
        expected = tuple(
            sorted(
                transitions,
                key=lambda t: (
                    t.transitioned_at_us,
                    t.transition_id,
                ),
            )
        )
        self.assertEqual(
            store.list_alert_transitions(),
            expected,
        )

    def test_list_transitions_filtered_by_alert_id(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert_a = make_alert(subject_reference=HEX_A)
        alert_b = make_alert(
            HMAC_KEY_A,
            subject_reference=HEX_E,
        )
        self.assertEqual(store.insert_alert(alert_a), "inserted")
        self.assertEqual(store.insert_alert(alert_b), "inserted")

        t_a = make_transition(
            alert=alert_a,
            transition_reference=HEX_D,
        )
        t_b = make_transition(
            alert=alert_b,
            transition_reference=HEX_E,
        )

        self.assertEqual(
            store.insert_alert_transition(t_a),
            "inserted",
        )
        self.assertEqual(
            store.insert_alert_transition(t_b),
            "inserted",
        )

        self.assertEqual(
            store.list_alert_transitions(alert_id=alert_a.alert_id),
            (t_a,),
        )
        self.assertEqual(
            store.list_alert_transitions(
                alert_id=ID_PREFIX_ALERT_ID + "f" * 64,
            ),
            (),
        )

    # ── Read results are frozen contract objects ────────────────────────

    def test_read_results_are_tuples_of_frozen_contract_objects(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        evidence = make_evidence(alert=alert)
        t = make_transition(alert=alert)

        self.assertEqual(store.insert_alert(alert), "inserted")
        self.assertEqual(
            store.insert_alert_evidence(evidence),
            "inserted",
        )
        self.assertEqual(
            store.insert_alert_transition(t),
            "inserted",
        )

        alerts = store.list_alerts()
        evidence_list = store.list_alert_evidence()
        transitions = store.list_alert_transitions()

        self.assertIsInstance(alerts, tuple)
        self.assertIsInstance(evidence_list, tuple)
        self.assertIsInstance(transitions, tuple)

        self.assertIsInstance(alerts[0], AlertV1)
        self.assertIsInstance(evidence_list[0], AlertEvidenceV1)
        self.assertIsInstance(transitions[0], AlertTransitionV1)

        with self.assertRaises(FrozenInstanceError):
            alerts[0].analysis_type = "changed"
        with self.assertRaises(FrozenInstanceError):
            evidence_list[0].evidence_level = "derived"
        with self.assertRaises(FrozenInstanceError):
            transitions[0].to_state = "resolved"

    # ── Invalid filters fail closed ─────────────────────────────────────

    def test_invalid_filters_fail_closed(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        invalid_values = (
            "",
            "   ",
            123,
            True,
        )

        for value in invalid_values:
            with self.subTest(method="list_alerts", value=value):
                with self.assertRaises(ValueError):
                    store.list_alerts(
                        deduplication_key=value,
                    )

            with self.subTest(method="list_evidence", value=value):
                with self.assertRaises(ValueError):
                    store.list_alert_evidence(alert_id=value)

            with self.subTest(method="list_transitions", value=value):
                with self.assertRaises(ValueError):
                    store.list_alert_transitions(alert_id=value)

    # ── Reads do not mutate the database ────────────────────────────────

    def test_reads_do_not_mutate(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        evidence = make_evidence(alert=alert)
        t = make_transition(alert=alert)

        self.assertEqual(store.insert_alert(alert), "inserted")
        self.assertEqual(
            store.insert_alert_evidence(evidence),
            "inserted",
        )
        self.assertEqual(
            store.insert_alert_transition(t),
            "inserted",
        )

        before = self.snapshot(path)

        for _ in range(3):
            self.assertEqual(store.list_alerts(), (alert,))
            self.assertEqual(
                store.list_alert_evidence(),
                (evidence,),
            )
            self.assertEqual(
                store.list_alert_transitions(),
                (t,),
            )

        after = self.snapshot(path)
        self.assertEqual(after, before)

    # ── Closed store operations fail ────────────────────────────────────

    def test_closed_store_operations_fail(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        store.close()

        with self.assertRaises(RuntimeError):
            store.list_alerts()

        with self.assertRaises(RuntimeError):
            store.list_alert_evidence()

        with self.assertRaises(RuntimeError):
            store.list_alert_transitions()

        with self.assertRaises(RuntimeError):
            store.get_alert("any")

        with self.assertRaises(RuntimeError):
            store.get_alert_evidence("any")

        with self.assertRaises(RuntimeError):
            store.get_alert_transition("any")

        with self.assertRaises(RuntimeError):
            alert = make_alert()
            store.insert_alert(alert)

        with self.assertRaises(RuntimeError):
            evidence = make_evidence(alert=make_alert())
            store.insert_alert_evidence(evidence)

        with self.assertRaises(RuntimeError):
            transition = make_transition(alert=make_alert())
            store.insert_alert_transition(transition)


from alert_contract import ID_PREFIX_DEDUP_KEY, ID_PREFIX_ALERT_ID


if __name__ == "__main__":
    unittest.main()
