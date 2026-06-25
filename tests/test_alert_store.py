import gc
from contextlib import closing
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sqlite3
import tempfile
import types
import unittest
import warnings

from alert_contract import (
    ALERT_TRANSITION_RECORD_KIND,
    AlertEvidenceV1,
    AlertProvenanceV1,
    AlertTransitionV1,
    AlertV1,
    SCHEMA_VERSION_V1,
    ID_PREFIX_ALERT_ID,
    ID_PREFIX_EVIDENCE_ID,
    ID_PREFIX_TRANSITION_ID,
    create_alert,
    create_alert_evidence,
    create_alert_transition,
)
from alert_store import AlertStore

from tests.test_alert_contract import (
    HMAC_KEY_A,
    HMAC_KEY_B,
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


class AlertStoreTests(unittest.TestCase):

    @staticmethod
    def open_store():
        tempdir = tempfile.TemporaryDirectory()
        path = Path(tempdir.name) / "alerts.sqlite"
        store = AlertStore(path)
        return store, path, tempdir

    @staticmethod
    def add_cleanup(store, tempdir):
        # Helper to schedule cleanup on a test instance
        pass

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
                (row[1], row[2].upper(), row[3], row[5], row[4])
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
                CREATE TABLE alerts (
                    alert_id TEXT NOT NULL PRIMARY KEY,
                    schema_version TEXT NOT NULL,
                    record_kind TEXT NOT NULL,
                    deduplication_key TEXT NOT NULL,
                    analysis_type TEXT NOT NULL,
                    analysis_version TEXT NOT NULL,
                    rule_id TEXT NOT NULL,
                    rule_version TEXT NOT NULL,
                    subject_kind TEXT NOT NULL,
                    subject_reference TEXT NOT NULL,
                    input_manifest_digest TEXT NOT NULL,
                    opening_evidence_reference TEXT NOT NULL,
                    first_observed_source_timestamp_us INTEGER NOT NULL,
                    created_ingest_timestamp_us INTEGER NOT NULL,
                    cooldown_us INTEGER NOT NULL,
                    initial_state TEXT NOT NULL,
                    baseline_manifest_digest TEXT,
                    analyzer_name TEXT NOT NULL,
                    analyzer_version TEXT NOT NULL,
                    analysis_mode TEXT NOT NULL,
                    source_contract_version TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE evidence (
                    evidence_id TEXT NOT NULL PRIMARY KEY,
                    schema_version TEXT NOT NULL,
                    record_kind TEXT NOT NULL,
                    alert_id TEXT NOT NULL REFERENCES alerts (alert_id),
                    evidence_type TEXT NOT NULL,
                    evidence_reference TEXT NOT NULL,
                    evidence_level TEXT NOT NULL,
                    observed_source_timestamp_us INTEGER NOT NULL,
                    recorded_ingest_timestamp_us INTEGER NOT NULL,
                    indicator_codes TEXT NOT NULL,
                    data_quality_codes TEXT NOT NULL,
                    limitation_codes TEXT NOT NULL,
                    alternative_explanation_codes TEXT NOT NULL,
                    analyzer_name TEXT NOT NULL,
                    analyzer_version TEXT NOT NULL,
                    analysis_mode TEXT NOT NULL,
                    source_contract_version TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE transitions (
                    transition_id TEXT NOT NULL PRIMARY KEY,
                    schema_version TEXT NOT NULL,
                    record_kind TEXT NOT NULL,
                    alert_id TEXT NOT NULL REFERENCES alerts (alert_id),
                    transition_reference TEXT NOT NULL,
                    previous_transition_id TEXT REFERENCES transitions (transition_id),
                    from_state TEXT NOT NULL,
                    to_state TEXT NOT NULL,
                    transitioned_at_us INTEGER NOT NULL,
                    recorded_ingest_timestamp_us INTEGER NOT NULL,
                    reason_code TEXT NOT NULL,
                    actor_kind TEXT NOT NULL,
                    analyzer_name TEXT NOT NULL,
                    analyzer_version TEXT NOT NULL,
                    analysis_mode TEXT NOT NULL,
                    source_contract_version TEXT NOT NULL
                )
                """
            )
            for name, table, msg in (
                ("alerts_no_update", "alerts", "alerts is immutable"),
                ("alerts_no_delete", "alerts", "alerts is immutable"),
                ("evidence_no_update", "evidence", "evidence is immutable"),
                ("evidence_no_delete", "evidence", "evidence is immutable"),
                ("transitions_no_update", "transitions", "transitions is immutable"),
                ("transitions_no_delete", "transitions", "transitions is immutable"),
            ):
                kind = "UPDATE" if "update" in name else "DELETE"
                connection.execute(
                    f"""
                    CREATE TRIGGER {name}
                    BEFORE {kind} ON {table}
                    BEGIN
                        SELECT RAISE(ABORT, '{msg}');
                    END
                    """,
                )
            connection.execute(
                """
                INSERT INTO store_metadata (
                    singleton, store_schema_version,
                    contract_schema_version, initialized_at_us
                ) VALUES (1, 1, '1.0', 0)
                """
            )
            connection.execute("PRAGMA user_version = 1")
            connection.commit()

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

    # ── Bootstrap and schema metadata ────────────────────────────────────

    def test_new_store_bootstraps_metadata_and_version(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        self.assertEqual(
            store._connection.execute(
                "PRAGMA foreign_keys"
            ).fetchone()[0],
            1,
        )
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(
                connection.execute(
                    "PRAGMA user_version"
                ).fetchone()[0],
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
                "alerts",
                "evidence",
                "transitions",
            },
        )
        self.assertEqual(
            self.table_info(path, "alerts")[0],
            ("alert_id", "TEXT", 1, 1, None),
        )

    # ── Alert roundtrip ──────────────────────────────────────────────────

    def test_alert_insert_roundtrip(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")
        self.assertEqual(store.get_alert(alert.alert_id), alert)

    def test_alert_duplicate(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")
        self.assertEqual(store.insert_alert(alert), "duplicate")

    def test_alert_identity_conflict(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")

        conflict = make_alert(
            first_observed_source_timestamp_us=TS_C,
        )
        self.assertEqual(
            store.insert_alert(conflict),
            "identity_conflict",
        )

    def test_alert_duplicate_after_close_reopen(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")
        store.close()

        reopened = AlertStore(path)
        self.addCleanup(reopened.close)

        dup = make_alert(
            created_ingest_timestamp_us=TS_C,
            provenance=make_provenance(analysis_mode="live"),
        )
        self.assertEqual(
            reopened.insert_alert(dup),
            "duplicate",
        )
        self.assertEqual(
            reopened.get_alert(alert.alert_id),
            alert,
        )

    def test_alert_identity_conflict_preserves_original_row(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")

        conflict = make_alert(
            first_observed_source_timestamp_us=TS_C,
        )
        self.assertEqual(
            store.insert_alert(conflict),
            "identity_conflict",
        )
        self.assertEqual(
            store.get_alert(alert.alert_id),
            alert,
        )

    # ── Evidence roundtrip ───────────────────────────────────────────────

    def test_evidence_insert_roundtrip(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")

        evidence = make_evidence(alert=alert)
        self.assertEqual(
            store.insert_alert_evidence(evidence),
            "inserted",
        )
        self.assertEqual(
            store.get_alert_evidence(evidence.evidence_id),
            evidence,
        )

    def test_evidence_duplicate(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")

        evidence = make_evidence(alert=alert)
        self.assertEqual(
            store.insert_alert_evidence(evidence),
            "inserted",
        )
        self.assertEqual(
            store.insert_alert_evidence(evidence),
            "duplicate",
        )

    def test_evidence_identity_conflict(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")

        evidence = make_evidence(alert=alert)
        self.assertEqual(
            store.insert_alert_evidence(evidence),
            "inserted",
        )

        conflict = make_evidence(
            alert=alert,
            evidence_level="correlated",
        )
        self.assertEqual(
            store.insert_alert_evidence(conflict),
            "identity_conflict",
        )

    def test_evidence_duplicate_after_close_reopen(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")
        evidence = make_evidence(alert=alert)
        self.assertEqual(
            store.insert_alert_evidence(evidence),
            "inserted",
        )
        store.close()

        reopened = AlertStore(path)
        self.addCleanup(reopened.close)

        dup = make_evidence(
            alert=alert,
            recorded_ingest_timestamp_us=TS_C,
            provenance=make_provenance(analysis_mode="live"),
        )
        self.assertEqual(
            reopened.insert_alert_evidence(dup),
            "duplicate",
        )
        self.assertEqual(
            reopened.get_alert_evidence(evidence.evidence_id),
            evidence,
        )

    def test_evidence_missing_parent_rejected(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        orphan_alert = make_alert()
        orphan_evidence = make_evidence(alert=orphan_alert)

        with self.assertRaises(ValueError):
            store.insert_alert_evidence(orphan_evidence)

    # ── Transition roundtrip ─────────────────────────────────────────────

    def test_transition_insert_roundtrip_first(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")

        t = make_transition(alert=alert)
        self.assertEqual(
            store.insert_alert_transition(t),
            "inserted",
        )
        self.assertEqual(
            store.get_alert_transition(t.transition_id),
            t,
        )

    def test_transition_insert_roundtrip_non_first(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")

        first = make_transition(
            alert=alert,
            from_state="new",
            to_state="acknowledged",
            transition_reference=HEX_D,
            transitioned_at_us=TS_A,
        )
        self.assertEqual(
            store.insert_alert_transition(first),
            "inserted",
        )

        second = make_transition(
            alert=alert,
            from_state="acknowledged",
            to_state="observing",
            transition_reference=HEX_E,
            transitioned_at_us=TS_B,
            previous_transition_id=first.transition_id,
        )
        self.assertEqual(
            store.insert_alert_transition(second),
            "inserted",
        )
        self.assertEqual(
            store.get_alert_transition(second.transition_id),
            second,
        )

    def test_transition_duplicate(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")

        t = make_transition(alert=alert)
        self.assertEqual(
            store.insert_alert_transition(t),
            "inserted",
        )
        self.assertEqual(
            store.insert_alert_transition(t),
            "duplicate",
        )

    def test_transition_identity_conflict(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")

        t = make_transition(alert=alert)
        self.assertEqual(
            store.insert_alert_transition(t),
            "inserted",
        )

        conflict = make_transition(
            alert=alert,
            transitioned_at_us=TS_C,
        )
        self.assertEqual(
            store.insert_alert_transition(conflict),
            "identity_conflict",
        )

    def test_transition_duplicate_after_close_reopen(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")
        t = make_transition(alert=alert)
        self.assertEqual(
            store.insert_alert_transition(t),
            "inserted",
        )
        store.close()

        reopened = AlertStore(path)
        self.addCleanup(reopened.close)

        dup = make_transition(
            alert=alert,
            recorded_ingest_timestamp_us=TS_C,
            provenance=make_provenance(analysis_mode="live"),
        )
        self.assertEqual(
            reopened.insert_alert_transition(dup),
            "duplicate",
        )
        self.assertEqual(
            reopened.get_alert_transition(t.transition_id),
            t,
        )

    def test_transition_missing_parent_rejected(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        orphan_alert = make_alert()
        orphan_transition = make_transition(alert=orphan_alert)

        with self.assertRaises(ValueError):
            store.insert_alert_transition(orphan_transition)

    def test_transition_missing_predecessor_rejected(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")

        first = make_transition(
            alert=alert,
            from_state="new",
            to_state="acknowledged",
            transition_reference=HEX_D,
            transitioned_at_us=TS_A,
        )
        self.assertEqual(
            store.insert_alert_transition(first),
            "inserted",
        )

        bogus_prev_id = ID_PREFIX_TRANSITION_ID + HEX_C
        orphan = make_transition(
            alert=alert,
            from_state="acknowledged",
            to_state="observing",
            transition_reference=HEX_E,
            transitioned_at_us=TS_B,
            previous_transition_id=bogus_prev_id,
        )
        with self.assertRaises(ValueError):
            store.insert_alert_transition(orphan)

    def test_transition_multiple_first_rejected(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")

        t1 = make_transition(
            alert=alert,
            from_state="new",
            to_state="acknowledged",
            transition_reference=HEX_D,
            transitioned_at_us=TS_A,
        )
        self.assertEqual(
            store.insert_alert_transition(t1),
            "inserted",
        )

        t2 = make_transition(
            alert=alert,
            from_state="new",
            to_state="observing",
            transition_reference=HEX_E,
            transitioned_at_us=TS_B,
        )
        with self.assertRaises(ValueError):
            store.insert_alert_transition(t2)

    def test_transition_predecessor_alert_mismatch_rejected(self):
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

        first = make_transition(
            alert=alert_a,
            from_state="new",
            to_state="acknowledged",
            transition_reference=HEX_D,
            transitioned_at_us=TS_A,
        )
        self.assertEqual(
            store.insert_alert_transition(first),
            "inserted",
        )

        second = make_transition(
            alert=alert_b,
            from_state="acknowledged",
            to_state="observing",
            transition_reference=HEX_E,
            transitioned_at_us=TS_B,
            previous_transition_id=first.transition_id,
        )
        with self.assertRaises(ValueError):
            store.insert_alert_transition(second)

    def test_transition_predecessor_state_mismatch_rejected(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")

        first = make_transition(
            alert=alert,
            from_state="new",
            to_state="acknowledged",
            transition_reference=HEX_D,
            transitioned_at_us=TS_A,
        )
        self.assertEqual(
            store.insert_alert_transition(first),
            "inserted",
        )

        second = make_transition(
            alert=alert,
            from_state="observing",
            to_state="escalated",
            transition_reference=HEX_E,
            transitioned_at_us=TS_B,
            previous_transition_id=first.transition_id,
        )
        with self.assertRaises(ValueError):
            store.insert_alert_transition(second)

    def test_transition_predecessor_time_mismatch_rejected(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")

        first = make_transition(
            alert=alert,
            from_state="new",
            to_state="acknowledged",
            transition_reference=HEX_D,
            transitioned_at_us=TS_C,
        )
        self.assertEqual(
            store.insert_alert_transition(first),
            "inserted",
        )

        second = make_transition(
            alert=alert,
            from_state="acknowledged",
            to_state="observing",
            transition_reference=HEX_E,
            transitioned_at_us=TS_A,
            previous_transition_id=first.transition_id,
        )
        with self.assertRaises(ValueError):
            store.insert_alert_transition(second)

    def test_transition_fork_rejected(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")

        first = make_transition(
            alert=alert,
            from_state="new",
            to_state="acknowledged",
            transition_reference=HEX_D,
            transitioned_at_us=TS_A,
        )
        self.assertEqual(
            store.insert_alert_transition(first),
            "inserted",
        )

        second = make_transition(
            alert=alert,
            from_state="acknowledged",
            to_state="observing",
            transition_reference=HEX_E,
            transitioned_at_us=TS_B,
            previous_transition_id=first.transition_id,
        )
        self.assertEqual(
            store.insert_alert_transition(second),
            "inserted",
        )

        fork = make_transition(
            alert=alert,
            from_state="acknowledged",
            to_state="escalated",
            transition_reference=HEX_A,
            transitioned_at_us=TS_C,
            previous_transition_id=first.transition_id,
        )
        with self.assertRaises(ValueError):
            store.insert_alert_transition(fork)

    def test_transition_old_replay_after_child_returns_duplicate(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")

        first = make_transition(
            alert=alert,
            from_state="new",
            to_state="acknowledged",
            transition_reference=HEX_D,
            transitioned_at_us=TS_A,
        )
        self.assertEqual(
            store.insert_alert_transition(first),
            "inserted",
        )

        second = make_transition(
            alert=alert,
            from_state="acknowledged",
            to_state="observing",
            transition_reference=HEX_E,
            transitioned_at_us=TS_B,
            previous_transition_id=first.transition_id,
        )
        self.assertEqual(
            store.insert_alert_transition(second),
            "inserted",
        )

        self.assertEqual(
            store.insert_alert_transition(first),
            "duplicate",
        )

    def test_transition_terminal_chain_append_rejected(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")

        terminal = make_transition(
            alert=alert,
            from_state="new",
            to_state="dismissed",
            transition_reference=HEX_D,
            transitioned_at_us=TS_A,
        )
        self.assertEqual(
            store.insert_alert_transition(terminal),
            "inserted",
        )

        # Contract allows acknowledged -> resolved, but predecessor (dismissed)
        # state mismatch should be caught by validate_alert_transition_predecessor.
        after = make_transition(
            alert=alert,
            from_state="acknowledged",
            to_state="resolved",
            transition_reference=HEX_E,
            transitioned_at_us=TS_B,
            previous_transition_id=terminal.transition_id,
        )
        with self.assertRaises(ValueError):
            store.insert_alert_transition(after)

    def test_equal_timestamp_parent_id_after_child_regression(self):
        """Structural tail must be used, not max(timestamp, id)."""
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")

        provenance = make_provenance()

        # Parent transition_id lexicographically after child, both at the
        # same timestamp. Old tail detection (timestamp DESC, id DESC) would
        # wrongly pick parent as the tail once child is stored.
        parent_id = ID_PREFIX_TRANSITION_ID + "f" * 64
        child_id = ID_PREFIX_TRANSITION_ID + "e" * 64
        grandchild_id = ID_PREFIX_TRANSITION_ID + "d" * 64
        fork_id = ID_PREFIX_TRANSITION_ID + "c" * 64

        parent = AlertTransitionV1(
            schema_version=SCHEMA_VERSION_V1,
            record_kind=ALERT_TRANSITION_RECORD_KIND,
            transition_id=parent_id,
            alert_id=alert.alert_id,
            transition_reference=HEX_D,
            previous_transition_id=None,
            from_state="new",
            to_state="acknowledged",
            transitioned_at_us=TS_A,
            recorded_ingest_timestamp_us=TS_B,
            reason_code="transition.operator_review",
            actor_kind="operator",
            provenance=provenance,
        )
        child = AlertTransitionV1(
            schema_version=SCHEMA_VERSION_V1,
            record_kind=ALERT_TRANSITION_RECORD_KIND,
            transition_id=child_id,
            alert_id=alert.alert_id,
            transition_reference=HEX_E,
            previous_transition_id=parent_id,
            from_state="acknowledged",
            to_state="observing",
            transitioned_at_us=TS_A,
            recorded_ingest_timestamp_us=TS_B,
            reason_code="transition.operator_review",
            actor_kind="operator",
            provenance=provenance,
        )
        grandchild = AlertTransitionV1(
            schema_version=SCHEMA_VERSION_V1,
            record_kind=ALERT_TRANSITION_RECORD_KIND,
            transition_id=grandchild_id,
            alert_id=alert.alert_id,
            transition_reference=HEX_A,
            previous_transition_id=child_id,
            from_state="observing",
            to_state="resolved",
            transitioned_at_us=TS_A,
            recorded_ingest_timestamp_us=TS_B,
            reason_code="transition.operator_review",
            actor_kind="operator",
            provenance=provenance,
        )
        fork = AlertTransitionV1(
            schema_version=SCHEMA_VERSION_V1,
            record_kind=ALERT_TRANSITION_RECORD_KIND,
            transition_id=fork_id,
            alert_id=alert.alert_id,
            transition_reference=HEX_C,
            previous_transition_id=parent_id,
            from_state="acknowledged",
            to_state="escalated",
            transitioned_at_us=TS_A,
            recorded_ingest_timestamp_us=TS_B,
            reason_code="transition.operator_review",
            actor_kind="operator",
            provenance=provenance,
        )

        self.assertEqual(
            store.insert_alert_transition(parent),
            "inserted",
        )
        self.assertEqual(
            store.insert_alert_transition(child),
            "inserted",
        )
        self.assertEqual(
            store.insert_alert_transition(grandchild),
            "inserted",
        )

        with self.assertRaises(ValueError):
            store.insert_alert_transition(fork)

        # Identical replay of parent and child remains duplicate.
        self.assertEqual(
            store.insert_alert_transition(parent),
            "duplicate",
        )
        self.assertEqual(
            store.insert_alert_transition(child),
            "duplicate",
        )

        # No partial row is written on rejection.
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM transitions"
                ).fetchone()[0],
                3,
            )

    # ── Frozen returned records ─────────────────────────────────────────

    def test_frozen_returned_records(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")
        evidence = make_evidence(alert=alert)
        self.assertEqual(
            store.insert_alert_evidence(evidence),
            "inserted",
        )
        t = make_transition(alert=alert)
        self.assertEqual(
            store.insert_alert_transition(t),
            "inserted",
        )

        stored_alert = store.get_alert(alert.alert_id)
        stored_evidence = store.get_alert_evidence(evidence.evidence_id)
        stored_transition = store.get_alert_transition(t.transition_id)

        with self.assertRaises(FrozenInstanceError):
            stored_alert.analysis_type = "changed"
        with self.assertRaises(FrozenInstanceError):
            stored_evidence.evidence_level = "derived"
        with self.assertRaises(FrozenInstanceError):
            stored_transition.to_state = "resolved"

    # ── Transaction rollback ─────────────────────────────────────────────

    def test_transaction_rollback_no_partial_rows_evidence(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        orphan_alert = make_alert()
        orphan_evidence = make_evidence(alert=orphan_alert)

        with self.assertRaises(ValueError):
            store.insert_alert_evidence(orphan_evidence)

        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM evidence"
                ).fetchone()[0],
                0,
            )

    def test_transaction_rollback_no_partial_rows_transition(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")

        first = make_transition(
            alert=alert,
            from_state="new",
            to_state="acknowledged",
            transition_reference=HEX_D,
            transitioned_at_us=TS_A,
        )
        self.assertEqual(
            store.insert_alert_transition(first),
            "inserted",
        )

        second = make_transition(
            alert=alert,
            from_state="observing",
            to_state="escalated",
            transition_reference=HEX_E,
            transitioned_at_us=TS_B,
            previous_transition_id=first.transition_id,
        )
        with self.assertRaises(ValueError):
            store.insert_alert_transition(second)

        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM transitions"
                ).fetchone()[0],
                1,
            )

    # ── UPDATE trigger enforcement ──────────────────────────────────────

    def test_update_trigger_enforcement(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")
        evidence = make_evidence(alert=alert)
        self.assertEqual(
            store.insert_alert_evidence(evidence),
            "inserted",
        )
        t = make_transition(alert=alert)
        self.assertEqual(
            store.insert_alert_transition(t),
            "inserted",
        )
        store.close()

        with closing(sqlite3.connect(path)) as connection:
            for table, id_col, id_val, col in (
                ("alerts", "alert_id", alert.alert_id, "analysis_type"),
                ("evidence", "evidence_id", evidence.evidence_id, "evidence_level"),
                ("transitions", "transition_id", t.transition_id, "from_state"),
            ):
                with self.subTest(table=table):
                    with self.assertRaises(sqlite3.IntegrityError):
                        connection.execute(
                            f"""
                            UPDATE {table}
                            SET {col} = 'changed'
                            WHERE {id_col} = ?
                            """,
                            (id_val,),
                        )

    # ── DELETE trigger enforcement ──────────────────────────────────────

    def test_delete_trigger_enforcement(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        alert = make_alert()
        self.assertEqual(store.insert_alert(alert), "inserted")
        evidence = make_evidence(alert=alert)
        self.assertEqual(
            store.insert_alert_evidence(evidence),
            "inserted",
        )
        t = make_transition(alert=alert)
        self.assertEqual(
            store.insert_alert_transition(t),
            "inserted",
        )
        store.close()

        with closing(sqlite3.connect(path)) as connection:
            for table, id_col, id_val in (
                ("alerts", "alert_id", alert.alert_id),
                ("evidence", "evidence_id", evidence.evidence_id),
                ("transitions", "transition_id", t.transition_id),
            ):
                with self.subTest(table=table):
                    with self.assertRaises(sqlite3.IntegrityError):
                        connection.execute(
                            f"""
                            DELETE FROM {table}
                            WHERE {id_col} = ?
                            """,
                            (id_val,),
                        )

    # ── Schema rejection without mutation ────────────────────────────────

    def test_altered_table_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "altered.sqlite"
            self.create_valid_schema(path)

            with closing(sqlite3.connect(path)) as connection:
                connection.execute("DROP TABLE evidence")
                connection.execute(
                    """
                    CREATE TABLE evidence (
                        evidence_id TEXT NOT NULL PRIMARY KEY,
                        schema_version TEXT NOT NULL,
                        record_kind TEXT NOT NULL,
                        alert_id TEXT NOT NULL REFERENCES alerts (alert_id),
                        evidence_type TEXT NOT NULL,
                        evidence_reference TEXT NOT NULL,
                        evidence_level TEXT NOT NULL,
                        observed_source_timestamp_us INTEGER NOT NULL,
                        recorded_ingest_timestamp_us INTEGER NOT NULL,
                        indicator_codes TEXT NOT NULL,
                        data_quality_codes TEXT NOT NULL,
                        limitation_codes TEXT NOT NULL,
                        alternative_explanation_codes TEXT NOT NULL,
                        analyzer_name TEXT NOT NULL,
                        analyzer_version TEXT NOT NULL,
                        analysis_mode TEXT NOT NULL,
                        source_contract_version TEXT NOT NULL,
                        extra_column TEXT
                    )
                    """
                )
                connection.commit()

            before = self.schema_snapshot(path)

            with self.assertRaises(ValueError):
                AlertStore(path)

            self.assertEqual(self.schema_snapshot(path), before)

    def test_altered_trigger_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "altered_trigger.sqlite"
            self.create_valid_schema(path)

            with closing(sqlite3.connect(path)) as connection:
                connection.execute(
                    "DROP TRIGGER evidence_no_update"
                )
                connection.execute(
                    """
                    CREATE TRIGGER evidence_no_update
                    BEFORE UPDATE ON evidence
                    WHEN 0
                    BEGIN
                        SELECT RAISE(ABORT, 'evidence is immutable');
                    END
                    """
                )
                connection.commit()

            before = self.schema_snapshot(path)

            with self.assertRaises(ValueError):
                AlertStore(path)

            self.assertEqual(self.schema_snapshot(path), before)
            self.assertIn(
                "WHEN 0",
                self.trigger_sql(path, "evidence_no_update"),
            )

    def test_missing_metadata_checks_rejected_without_mutation(self):
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
                    CREATE TABLE alerts (
                        alert_id TEXT NOT NULL PRIMARY KEY,
                        schema_version TEXT NOT NULL,
                        record_kind TEXT NOT NULL,
                        deduplication_key TEXT NOT NULL,
                        analysis_type TEXT NOT NULL,
                        analysis_version TEXT NOT NULL,
                        rule_id TEXT NOT NULL,
                        rule_version TEXT NOT NULL,
                        subject_kind TEXT NOT NULL,
                        subject_reference TEXT NOT NULL,
                        input_manifest_digest TEXT NOT NULL,
                        opening_evidence_reference TEXT NOT NULL,
                        first_observed_source_timestamp_us INTEGER NOT NULL,
                        created_ingest_timestamp_us INTEGER NOT NULL,
                        cooldown_us INTEGER NOT NULL,
                        initial_state TEXT NOT NULL,
                        baseline_manifest_digest TEXT,
                        analyzer_name TEXT NOT NULL,
                        analyzer_version TEXT NOT NULL,
                        analysis_mode TEXT NOT NULL,
                        source_contract_version TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE evidence (
                        evidence_id TEXT NOT NULL PRIMARY KEY,
                        schema_version TEXT NOT NULL,
                        record_kind TEXT NOT NULL,
                        alert_id TEXT NOT NULL REFERENCES alerts (alert_id),
                        evidence_type TEXT NOT NULL,
                        evidence_reference TEXT NOT NULL,
                        evidence_level TEXT NOT NULL,
                        observed_source_timestamp_us INTEGER NOT NULL,
                        recorded_ingest_timestamp_us INTEGER NOT NULL,
                        indicator_codes TEXT NOT NULL,
                        data_quality_codes TEXT NOT NULL,
                        limitation_codes TEXT NOT NULL,
                        alternative_explanation_codes TEXT NOT NULL,
                        analyzer_name TEXT NOT NULL,
                        analyzer_version TEXT NOT NULL,
                        analysis_mode TEXT NOT NULL,
                        source_contract_version TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE transitions (
                        transition_id TEXT NOT NULL PRIMARY KEY,
                        schema_version TEXT NOT NULL,
                        record_kind TEXT NOT NULL,
                        alert_id TEXT NOT NULL REFERENCES alerts (alert_id),
                        transition_reference TEXT NOT NULL,
                        previous_transition_id TEXT REFERENCES transitions (transition_id),
                        from_state TEXT NOT NULL,
                        to_state TEXT NOT NULL,
                        transitioned_at_us INTEGER NOT NULL,
                        recorded_ingest_timestamp_us INTEGER NOT NULL,
                        reason_code TEXT NOT NULL,
                        actor_kind TEXT NOT NULL,
                        analyzer_name TEXT NOT NULL,
                        analyzer_version TEXT NOT NULL,
                        analysis_mode TEXT NOT NULL,
                        source_contract_version TEXT NOT NULL
                    )
                    """
                )
                for name, table, msg in (
                    ("alerts_no_update", "alerts", "alerts is immutable"),
                    ("alerts_no_delete", "alerts", "alerts is immutable"),
                    ("evidence_no_update", "evidence", "evidence is immutable"),
                    ("evidence_no_delete", "evidence", "evidence is immutable"),
                    ("transitions_no_update", "transitions", "transitions is immutable"),
                    ("transitions_no_delete", "transitions", "transitions is immutable"),
                ):
                    kind = "UPDATE" if "update" in name else "DELETE"
                    connection.execute(
                        f"""
                        CREATE TRIGGER {name}
                        BEFORE {kind} ON {table}
                        BEGIN
                            SELECT RAISE(ABORT, '{msg}');
                        END
                        """,
                    )
                connection.execute(
                    """
                    INSERT INTO store_metadata (
                        singleton, store_schema_version,
                        contract_schema_version, initialized_at_us
                    ) VALUES (1, 1, '1.0', 0)
                    """
                )
                connection.execute("PRAGMA user_version = 1")
                connection.commit()

            before = self.schema_snapshot(path)

            with self.assertRaises(ValueError):
                AlertStore(path)

            self.assertEqual(self.schema_snapshot(path), before)

    # ── No aggregate-state / current-state table or column ──────────────

    def test_no_aggregate_state_table_or_column(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        with closing(sqlite3.connect(path)) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                    """
                )
            }
            self.assertEqual(
                tables,
                {"store_metadata", "alerts", "evidence", "transitions"},
            )

            for table in tables:
                cols = connection.execute(
                    f"PRAGMA table_info({table})"
                ).fetchall()
                for col in cols:
                    self.assertNotIn(
                        "current_state",
                        col[1].lower(),
                        f"{table} has current_state column",
                    )

    # ── No public raw connection API ────────────────────────────────────

    def test_no_public_raw_connection_api(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        with self.assertRaises(AttributeError):
            _ = store.connection

    # ── Fake object rejection ───────────────────────────────────────────

    def test_fake_object_rejected(self):
        store, path, tempdir = self.open_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        fake_alert = types.SimpleNamespace(
            alert_id=ID_PREFIX_ALERT_ID + "0" * 64,
        )
        fake_evidence = types.SimpleNamespace(
            evidence_id=ID_PREFIX_EVIDENCE_ID + "0" * 64,
        )
        fake_transition = types.SimpleNamespace(
            transition_id=ID_PREFIX_TRANSITION_ID + "0" * 64,
        )

        with self.assertRaises(ValueError):
            store.insert_alert(fake_alert)
        with self.assertRaises(ValueError):
            store.insert_alert_evidence(fake_evidence)
        with self.assertRaises(ValueError):
            store.insert_alert_transition(fake_transition)

    # ── Clean shutdown without ResourceWarning ─────────────────────────

    def test_clean_shutdown_no_resourcewarning(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", ResourceWarning)
            with tempfile.TemporaryDirectory() as tempdir:
                path = Path(tempdir) / "clean.sqlite"
                with AlertStore(path) as store:
                    self.assertIsInstance(store, AlertStore)
                del store
                gc.collect()


if __name__ == "__main__":
    unittest.main()
