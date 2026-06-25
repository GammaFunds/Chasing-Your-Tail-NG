"""Isolated SQLite store for Alert Lifecycle v1 records."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Iterator, Optional

from alert_contract import (
    AlertEvidenceV1,
    AlertProvenanceV1,
    AlertTransitionV1,
    AlertV1,
    compare_alert_evidence_source_facts,
    compare_alert_source_facts,
    compare_alert_transition_source_facts,
    validate_alert_transition_predecessor,
)


_STORE_SCHEMA_VERSION = 1
_CONTRACT_SCHEMA_VERSION = "1.0"

_METADATA_TABLE = "store_metadata"
_ALERTS_TABLE = "alerts"
_EVIDENCE_TABLE = "evidence"
_TRANSITIONS_TABLE = "transitions"

_ALERT_UPDATE_TRIGGER = "alerts_no_update"
_ALERT_DELETE_TRIGGER = "alerts_no_delete"
_EVIDENCE_UPDATE_TRIGGER = "evidence_no_update"
_EVIDENCE_DELETE_TRIGGER = "evidence_no_delete"
_TRANSITION_UPDATE_TRIGGER = "transitions_no_update"
_TRANSITION_DELETE_TRIGGER = "transitions_no_delete"

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

_ALERTS_TABLE_DDL = f"""
CREATE TABLE {_ALERTS_TABLE} (
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

_EVIDENCE_TABLE_DDL = f"""
CREATE TABLE {_EVIDENCE_TABLE} (
    evidence_id TEXT NOT NULL PRIMARY KEY,
    schema_version TEXT NOT NULL,
    record_kind TEXT NOT NULL,
    alert_id TEXT NOT NULL REFERENCES {_ALERTS_TABLE} (alert_id),
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

_TRANSITIONS_TABLE_DDL = f"""
CREATE TABLE {_TRANSITIONS_TABLE} (
    transition_id TEXT NOT NULL PRIMARY KEY,
    schema_version TEXT NOT NULL,
    record_kind TEXT NOT NULL,
    alert_id TEXT NOT NULL REFERENCES {_ALERTS_TABLE} (alert_id),
    transition_reference TEXT NOT NULL,
    previous_transition_id TEXT REFERENCES {_TRANSITIONS_TABLE} (transition_id),
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

_ALERT_UPDATE_TRIGGER_DDL = f"""
CREATE TRIGGER {_ALERT_UPDATE_TRIGGER}
BEFORE UPDATE ON {_ALERTS_TABLE}
BEGIN
    SELECT RAISE(ABORT, 'alerts is immutable');
END
"""

_ALERT_DELETE_TRIGGER_DDL = f"""
CREATE TRIGGER {_ALERT_DELETE_TRIGGER}
BEFORE DELETE ON {_ALERTS_TABLE}
BEGIN
    SELECT RAISE(ABORT, 'alerts is immutable');
END
"""

_EVIDENCE_UPDATE_TRIGGER_DDL = f"""
CREATE TRIGGER {_EVIDENCE_UPDATE_TRIGGER}
BEFORE UPDATE ON {_EVIDENCE_TABLE}
BEGIN
    SELECT RAISE(ABORT, 'evidence is immutable');
END
"""

_EVIDENCE_DELETE_TRIGGER_DDL = f"""
CREATE TRIGGER {_EVIDENCE_DELETE_TRIGGER}
BEFORE DELETE ON {_EVIDENCE_TABLE}
BEGIN
    SELECT RAISE(ABORT, 'evidence is immutable');
END
"""

_TRANSITION_UPDATE_TRIGGER_DDL = f"""
CREATE TRIGGER {_TRANSITION_UPDATE_TRIGGER}
BEFORE UPDATE ON {_TRANSITIONS_TABLE}
BEGIN
    SELECT RAISE(ABORT, 'transitions is immutable');
END
"""

_TRANSITION_DELETE_TRIGGER_DDL = f"""
CREATE TRIGGER {_TRANSITION_DELETE_TRIGGER}
BEFORE DELETE ON {_TRANSITIONS_TABLE}
BEGIN
    SELECT RAISE(ABORT, 'transitions is immutable');
END
"""

_TRIGGER_DDLS = {
    _ALERT_UPDATE_TRIGGER: _ALERT_UPDATE_TRIGGER_DDL,
    _ALERT_DELETE_TRIGGER: _ALERT_DELETE_TRIGGER_DDL,
    _EVIDENCE_UPDATE_TRIGGER: _EVIDENCE_UPDATE_TRIGGER_DDL,
    _EVIDENCE_DELETE_TRIGGER: _EVIDENCE_DELETE_TRIGGER_DDL,
    _TRANSITION_UPDATE_TRIGGER: _TRANSITION_UPDATE_TRIGGER_DDL,
    _TRANSITION_DELETE_TRIGGER: _TRANSITION_DELETE_TRIGGER_DDL,
}


def _serialize_tuples(t: tuple[str, ...]) -> str:
    return json.dumps(t, separators=(",", ":"))


def _deserialize_tuples(s: str) -> tuple[str, ...]:
    return tuple(json.loads(s))


class AlertStore:
    """SQLite-backed immutable store for accepted Alert Lifecycle v1 records."""

    def __init__(self, db_path: str | Path):
        self._db_path = Path(db_path)
        self._connection: Optional[sqlite3.Connection] = None
        self._closed = False
        self._open()

    def __enter__(self) -> "AlertStore":
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

    # ── Alert methods ─────────────────────────────────────────────────────

    def insert_alert(self, alert: AlertV1) -> str:
        self._ensure_open()
        if type(alert) is not AlertV1:
            raise ValueError("alert must be AlertV1")

        with self._write_transaction():
            existing = self._fetch_alert_row(alert.alert_id)
            if existing is None:
                self._connection.execute(
                    f"""
                    INSERT INTO {_ALERTS_TABLE} (
                        alert_id, schema_version, record_kind,
                        deduplication_key, analysis_type, analysis_version,
                        rule_id, rule_version, subject_kind, subject_reference,
                        input_manifest_digest, opening_evidence_reference,
                        first_observed_source_timestamp_us,
                        created_ingest_timestamp_us,
                        cooldown_us, initial_state, baseline_manifest_digest,
                        analyzer_name, analyzer_version, analysis_mode,
                        source_contract_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._alert_insert_values(alert),
                )
                return "inserted"

            existing_alert = self._alert_from_row(existing)
            return compare_alert_source_facts(existing_alert, alert)

    def get_alert(self, alert_id: str) -> Optional[AlertV1]:
        self._ensure_open()
        row = self._fetch_alert_row(alert_id)
        if row is None:
            return None
        return self._alert_from_row(row)

    def list_alerts(
        self,
        *,
        deduplication_key: Optional[str] = None,
    ) -> tuple[AlertV1, ...]:
        self._ensure_open()

        if deduplication_key is not None:
            if (
                not isinstance(deduplication_key, str)
                or not deduplication_key.strip()
            ):
                raise ValueError("deduplication_key must be non-empty text")

            rows = self._connection.execute(
                f"""
                SELECT *
                FROM {_ALERTS_TABLE}
                WHERE deduplication_key = ?
                ORDER BY first_observed_source_timestamp_us, alert_id
                """,
                (deduplication_key,),
            ).fetchall()
        else:
            rows = self._connection.execute(
                f"""
                SELECT *
                FROM {_ALERTS_TABLE}
                ORDER BY first_observed_source_timestamp_us, alert_id
                """
            ).fetchall()

        return tuple(self._alert_from_row(row) for row in rows)

    # ── Evidence methods ──────────────────────────────────────────────────

    def insert_alert_evidence(self, evidence: AlertEvidenceV1) -> str:
        self._ensure_open()
        if type(evidence) is not AlertEvidenceV1:
            raise ValueError("evidence must be AlertEvidenceV1")

        with self._write_transaction():
            existing = self._fetch_evidence_row(evidence.evidence_id)
            if existing is None:
                parent = self._fetch_alert_row(evidence.alert_id)
                if parent is None:
                    raise ValueError("parent alert does not exist")

                self._connection.execute(
                    f"""
                    INSERT INTO {_EVIDENCE_TABLE} (
                        evidence_id, schema_version, record_kind,
                        alert_id, evidence_type, evidence_reference,
                        evidence_level, observed_source_timestamp_us,
                        recorded_ingest_timestamp_us,
                        indicator_codes, data_quality_codes,
                        limitation_codes, alternative_explanation_codes,
                        analyzer_name, analyzer_version, analysis_mode,
                        source_contract_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._evidence_insert_values(evidence),
                )
                return "inserted"

            existing_evidence = self._evidence_from_row(existing)
            return compare_alert_evidence_source_facts(existing_evidence, evidence)

    def get_alert_evidence(
        self,
        evidence_id: str,
    ) -> Optional[AlertEvidenceV1]:
        self._ensure_open()
        row = self._fetch_evidence_row(evidence_id)
        if row is None:
            return None
        return self._evidence_from_row(row)

    def list_alert_evidence(
        self,
        *,
        alert_id: Optional[str] = None,
    ) -> tuple[AlertEvidenceV1, ...]:
        self._ensure_open()

        if alert_id is not None:
            if not isinstance(alert_id, str) or not alert_id.strip():
                raise ValueError("alert_id must be non-empty text")

            rows = self._connection.execute(
                f"""
                SELECT *
                FROM {_EVIDENCE_TABLE}
                WHERE alert_id = ?
                ORDER BY observed_source_timestamp_us, evidence_id
                """,
                (alert_id,),
            ).fetchall()
        else:
            rows = self._connection.execute(
                f"""
                SELECT *
                FROM {_EVIDENCE_TABLE}
                ORDER BY observed_source_timestamp_us, evidence_id
                """
            ).fetchall()

        return tuple(self._evidence_from_row(row) for row in rows)

    # ── Transition methods ────────────────────────────────────────────────

    def insert_alert_transition(self, transition: AlertTransitionV1) -> str:
        self._ensure_open()
        if type(transition) is not AlertTransitionV1:
            raise ValueError("transition must be AlertTransitionV1")

        with self._write_transaction():
            existing = self._fetch_transition_row(transition.transition_id)
            if existing is not None:
                existing_transition = self._transition_from_row(existing)
                return compare_alert_transition_source_facts(
                    existing_transition, transition
                )

            parent = self._fetch_alert_row(transition.alert_id)
            if parent is None:
                raise ValueError("parent alert does not exist")

            tails = self._fetch_structural_tails(transition.alert_id)
            if transition.previous_transition_id is None:
                if tails:
                    raise ValueError(
                        "alert already has a first transition"
                    )
                validate_alert_transition_predecessor(transition, None)
            else:
                pred_row = self._fetch_transition_row(
                    transition.previous_transition_id
                )
                if pred_row is None:
                    raise ValueError(
                        "predecessor transition does not exist"
                    )
                predecessor = self._transition_from_row(pred_row)

                if len(tails) != 1:
                    raise ValueError(
                        "chain has no unique structural tail"
                    )
                if tails[0]["transition_id"] != predecessor.transition_id:
                    raise ValueError(
                        "predecessor is not the current chain tail"
                    )

                validate_alert_transition_predecessor(transition, predecessor)

            self._connection.execute(
                f"""
                INSERT INTO {_TRANSITIONS_TABLE} (
                    transition_id, schema_version, record_kind,
                    alert_id, transition_reference, previous_transition_id,
                    from_state, to_state, transitioned_at_us,
                    recorded_ingest_timestamp_us, reason_code, actor_kind,
                    analyzer_name, analyzer_version, analysis_mode,
                    source_contract_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._transition_insert_values(transition),
            )
            return "inserted"

    def get_alert_transition(
        self,
        transition_id: str,
    ) -> Optional[AlertTransitionV1]:
        self._ensure_open()
        row = self._fetch_transition_row(transition_id)
        if row is None:
            return None
        return self._transition_from_row(row)

    def list_alert_transitions(
        self,
        *,
        alert_id: Optional[str] = None,
    ) -> tuple[AlertTransitionV1, ...]:
        self._ensure_open()

        if alert_id is not None:
            if not isinstance(alert_id, str) or not alert_id.strip():
                raise ValueError("alert_id must be non-empty text")

            rows = self._connection.execute(
                f"""
                SELECT *
                FROM {_TRANSITIONS_TABLE}
                WHERE alert_id = ?
                ORDER BY transitioned_at_us, transition_id
                """,
                (alert_id,),
            ).fetchall()
        else:
            rows = self._connection.execute(
                f"""
                SELECT *
                FROM {_TRANSITIONS_TABLE}
                ORDER BY transitioned_at_us, transition_id
                """
            ).fetchall()

        return tuple(self._transition_from_row(row) for row in rows)

    # ── Internal: connection management ───────────────────────────────────

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
            raise RuntimeError("AlertStore is closed")

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

    # ── Internal: bootstrap ───────────────────────────────────────────────

    def _bootstrap(self) -> None:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            self._bootstrap_execute(_METADATA_TABLE_DDL)
            self._bootstrap_execute(_ALERTS_TABLE_DDL)
            self._bootstrap_execute(_EVIDENCE_TABLE_DDL)
            self._bootstrap_execute(_TRANSITIONS_TABLE_DDL)
            self._bootstrap_execute(_ALERT_UPDATE_TRIGGER_DDL)
            self._bootstrap_execute(_ALERT_DELETE_TRIGGER_DDL)
            self._bootstrap_execute(_EVIDENCE_UPDATE_TRIGGER_DDL)
            self._bootstrap_execute(_EVIDENCE_DELETE_TRIGGER_DDL)
            self._bootstrap_execute(_TRANSITION_UPDATE_TRIGGER_DDL)
            self._bootstrap_execute(_TRANSITION_DELETE_TRIGGER_DDL)
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

    # ── Internal: schema validation ───────────────────────────────────────

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
            _ALERTS_TABLE,
            _EVIDENCE_TABLE,
            _TRANSITIONS_TABLE,
        }:
            raise ValueError("unexpected store tables")

        trigger_names = self._fetch_object_names("trigger")
        if trigger_names != set(_TRIGGER_DDLS):
            raise ValueError("unexpected store triggers")

        for trigger_name in _TRIGGER_DDLS:
            self._validate_trigger_sql(trigger_name)

        self._validate_table_ddl(
            _METADATA_TABLE,
            _METADATA_TABLE_DDL,
        )
        self._validate_table_ddl(
            _ALERTS_TABLE,
            _ALERTS_TABLE_DDL,
        )
        self._validate_table_ddl(
            _EVIDENCE_TABLE,
            _EVIDENCE_TABLE_DDL,
        )
        self._validate_table_ddl(
            _TRANSITIONS_TABLE,
            _TRANSITIONS_TABLE_DDL,
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

        expected_sql = _TRIGGER_DDLS.get(trigger_name)
        if expected_sql is None:
            raise ValueError(f"unknown trigger: {trigger_name}")

        if self._normalize_sql(row["sql"]) != self._normalize_sql(expected_sql):
            raise ValueError("unexpected trigger body")

    @staticmethod
    def _normalize_sql(sql: str) -> str:
        return " ".join(sql.strip().split()).rstrip(";").lower()

    # ── Internal: row fetchers ────────────────────────────────────────────

    def _fetch_alert_row(
        self,
        alert_id: str,
    ) -> Optional[sqlite3.Row]:
        return self._connection.execute(
            f"""
            SELECT *
            FROM {_ALERTS_TABLE}
            WHERE alert_id = ?
            """,
            (alert_id,),
        ).fetchone()

    def _fetch_evidence_row(
        self,
        evidence_id: str,
    ) -> Optional[sqlite3.Row]:
        return self._connection.execute(
            f"""
            SELECT *
            FROM {_EVIDENCE_TABLE}
            WHERE evidence_id = ?
            """,
            (evidence_id,),
        ).fetchone()

    def _fetch_transition_row(
        self,
        transition_id: str,
    ) -> Optional[sqlite3.Row]:
        return self._connection.execute(
            f"""
            SELECT *
            FROM {_TRANSITIONS_TABLE}
            WHERE transition_id = ?
            """,
            (transition_id,),
        ).fetchone()

    def _fetch_structural_tails(
        self,
        alert_id: str,
    ) -> list[sqlite3.Row]:
        """Return transitions for the alert not referenced as a predecessor."""
        return self._connection.execute(
            f"""
            SELECT t1.*
            FROM {_TRANSITIONS_TABLE} t1
            LEFT JOIN {_TRANSITIONS_TABLE} t2
                ON t2.previous_transition_id = t1.transition_id
                AND t2.alert_id = t1.alert_id
            WHERE t1.alert_id = ?
                AND t2.transition_id IS NULL
            """,
            (alert_id,),
        ).fetchall()

    # ── Internal: insert values ───────────────────────────────────────────

    @staticmethod
    def _alert_insert_values(alert: AlertV1) -> tuple[object, ...]:
        provenance = alert.provenance
        return (
            alert.alert_id,
            alert.schema_version,
            alert.record_kind,
            alert.deduplication_key,
            alert.analysis_type,
            alert.analysis_version,
            alert.rule_id,
            alert.rule_version,
            alert.subject_kind,
            alert.subject_reference,
            alert.input_manifest_digest,
            alert.opening_evidence_reference,
            alert.first_observed_source_timestamp_us,
            alert.created_ingest_timestamp_us,
            alert.cooldown_us,
            alert.initial_state,
            alert.baseline_manifest_digest,
            provenance.analyzer_name,
            provenance.analyzer_version,
            provenance.analysis_mode,
            provenance.source_contract_version,
        )

    @staticmethod
    def _evidence_insert_values(
        evidence: AlertEvidenceV1,
    ) -> tuple[object, ...]:
        provenance = evidence.provenance
        return (
            evidence.evidence_id,
            evidence.schema_version,
            evidence.record_kind,
            evidence.alert_id,
            evidence.evidence_type,
            evidence.evidence_reference,
            evidence.evidence_level,
            evidence.observed_source_timestamp_us,
            evidence.recorded_ingest_timestamp_us,
            _serialize_tuples(evidence.indicator_codes),
            _serialize_tuples(evidence.data_quality_codes),
            _serialize_tuples(evidence.limitation_codes),
            _serialize_tuples(evidence.alternative_explanation_codes),
            provenance.analyzer_name,
            provenance.analyzer_version,
            provenance.analysis_mode,
            provenance.source_contract_version,
        )

    @staticmethod
    def _transition_insert_values(
        transition: AlertTransitionV1,
    ) -> tuple[object, ...]:
        provenance = transition.provenance
        return (
            transition.transition_id,
            transition.schema_version,
            transition.record_kind,
            transition.alert_id,
            transition.transition_reference,
            transition.previous_transition_id,
            transition.from_state,
            transition.to_state,
            transition.transitioned_at_us,
            transition.recorded_ingest_timestamp_us,
            transition.reason_code,
            transition.actor_kind,
            provenance.analyzer_name,
            provenance.analyzer_version,
            provenance.analysis_mode,
            provenance.source_contract_version,
        )

    # ── Internal: row deserializers ───────────────────────────────────────

    @staticmethod
    def _alert_from_row(row: sqlite3.Row) -> AlertV1:
        return AlertV1(
            schema_version=row["schema_version"],
            record_kind=row["record_kind"],
            alert_id=row["alert_id"],
            deduplication_key=row["deduplication_key"],
            analysis_type=row["analysis_type"],
            analysis_version=row["analysis_version"],
            rule_id=row["rule_id"],
            rule_version=row["rule_version"],
            subject_kind=row["subject_kind"],
            subject_reference=row["subject_reference"],
            input_manifest_digest=row["input_manifest_digest"],
            opening_evidence_reference=row["opening_evidence_reference"],
            first_observed_source_timestamp_us=row[
                "first_observed_source_timestamp_us"
            ],
            created_ingest_timestamp_us=row["created_ingest_timestamp_us"],
            cooldown_us=row["cooldown_us"],
            initial_state=row["initial_state"],
            baseline_manifest_digest=row["baseline_manifest_digest"],
            provenance=AlertProvenanceV1(
                analyzer_name=row["analyzer_name"],
                analyzer_version=row["analyzer_version"],
                analysis_mode=row["analysis_mode"],
                source_contract_version=row["source_contract_version"],
            ),
        )

    @staticmethod
    def _evidence_from_row(row: sqlite3.Row) -> AlertEvidenceV1:
        return AlertEvidenceV1(
            schema_version=row["schema_version"],
            record_kind=row["record_kind"],
            evidence_id=row["evidence_id"],
            alert_id=row["alert_id"],
            evidence_type=row["evidence_type"],
            evidence_reference=row["evidence_reference"],
            evidence_level=row["evidence_level"],
            observed_source_timestamp_us=row[
                "observed_source_timestamp_us"
            ],
            recorded_ingest_timestamp_us=row[
                "recorded_ingest_timestamp_us"
            ],
            indicator_codes=_deserialize_tuples(row["indicator_codes"]),
            data_quality_codes=_deserialize_tuples(
                row["data_quality_codes"]
            ),
            limitation_codes=_deserialize_tuples(
                row["limitation_codes"]
            ),
            alternative_explanation_codes=_deserialize_tuples(
                row["alternative_explanation_codes"]
            ),
            provenance=AlertProvenanceV1(
                analyzer_name=row["analyzer_name"],
                analyzer_version=row["analyzer_version"],
                analysis_mode=row["analysis_mode"],
                source_contract_version=row["source_contract_version"],
            ),
        )

    @staticmethod
    def _transition_from_row(row: sqlite3.Row) -> AlertTransitionV1:
        return AlertTransitionV1(
            schema_version=row["schema_version"],
            record_kind=row["record_kind"],
            transition_id=row["transition_id"],
            alert_id=row["alert_id"],
            transition_reference=row["transition_reference"],
            previous_transition_id=row["previous_transition_id"],
            from_state=row["from_state"],
            to_state=row["to_state"],
            transitioned_at_us=row["transitioned_at_us"],
            recorded_ingest_timestamp_us=row[
                "recorded_ingest_timestamp_us"
            ],
            reason_code=row["reason_code"],
            actor_kind=row["actor_kind"],
            provenance=AlertProvenanceV1(
                analyzer_name=row["analyzer_name"],
                analyzer_version=row["analyzer_version"],
                analysis_mode=row["analysis_mode"],
                source_contract_version=row["source_contract_version"],
            ),
        )


__all__ = ["AlertStore"]
