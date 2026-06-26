"""Isolated SQLite store for Baseline Manifest v1 and Baseline Result v1 records."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Iterator, Optional

from baseline_contract import (
    BaselineManifestV1,
    BaselineProvenanceV1,
    compare_baseline_manifest_source_facts,
)
from baseline_result import (
    BaselineCountSampleV1,
    BaselineResultV1,
    compare_baseline_result_source_facts,
)


_STORE_SCHEMA_VERSION = 1
_CONTRACT_SCHEMA_VERSION = "1.0"

_METADATA_TABLE = "store_metadata"
_MANIFESTS_TABLE = "baseline_manifests"
_RESULTS_TABLE = "baseline_results"

_MANIFEST_UPDATE_TRIGGER = "baseline_manifests_no_update"
_MANIFEST_DELETE_TRIGGER = "baseline_manifests_no_delete"
_RESULT_UPDATE_TRIGGER = "baseline_results_no_update"
_RESULT_DELETE_TRIGGER = "baseline_results_no_delete"

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

_MANIFESTS_TABLE_DDL = f"""
CREATE TABLE {_MANIFESTS_TABLE} (
    baseline_manifest_id TEXT NOT NULL PRIMARY KEY,
    schema_version TEXT NOT NULL,
    record_kind TEXT NOT NULL,
    baseline_manifest_digest TEXT NOT NULL,
    analysis_type TEXT NOT NULL,
    analysis_version TEXT NOT NULL,
    baseline_method TEXT NOT NULL,
    baseline_version TEXT NOT NULL,
    subject_kind TEXT NOT NULL,
    subject_reference TEXT NOT NULL,
    window_start_source_timestamp_us TEXT NOT NULL,
    window_end_source_timestamp_us TEXT NOT NULL,
    time_basis TEXT NOT NULL,
    boundary_policy TEXT NOT NULL,
    input_reference_digests TEXT NOT NULL,
    sample_count TEXT NOT NULL,
    minimum_sample_count TEXT NOT NULL,
    baseline_status TEXT NOT NULL,
    status_reason_code TEXT NOT NULL,
    created_ingest_timestamp_us TEXT NOT NULL,
    analyzer_name TEXT NOT NULL,
    analyzer_version TEXT NOT NULL,
    analysis_mode TEXT NOT NULL,
    source_contract_version TEXT NOT NULL
)
"""

_RESULTS_TABLE_DDL = f"""
CREATE TABLE {_RESULTS_TABLE} (
    baseline_result_id TEXT NOT NULL PRIMARY KEY,
    schema_version TEXT NOT NULL,
    record_kind TEXT NOT NULL,
    baseline_result_digest TEXT NOT NULL,
    analysis_type TEXT NOT NULL,
    analysis_version TEXT NOT NULL,
    baseline_method TEXT NOT NULL,
    baseline_version TEXT NOT NULL,
    manifest_id TEXT NOT NULL REFERENCES {_MANIFESTS_TABLE} (
        baseline_manifest_id
    ),
    manifest_digest TEXT NOT NULL,
    samples TEXT NOT NULL,
    sample_count TEXT NOT NULL,
    minimum_sample_count TEXT NOT NULL,
    baseline_status TEXT NOT NULL,
    status_reason_code TEXT NOT NULL,
    minimum_count TEXT,
    maximum_count TEXT,
    count_mean_numerator TEXT,
    count_mean_denominator TEXT,
    created_ingest_timestamp_us TEXT NOT NULL,
    analyzer_name TEXT NOT NULL,
    analyzer_version TEXT NOT NULL,
    analysis_mode TEXT NOT NULL,
    source_contract_version TEXT NOT NULL,
    UNIQUE (manifest_id)
)
"""

_MANIFEST_UPDATE_TRIGGER_DDL = f"""
CREATE TRIGGER {_MANIFEST_UPDATE_TRIGGER}
BEFORE UPDATE ON {_MANIFESTS_TABLE}
BEGIN
    SELECT RAISE(ABORT, 'baseline_manifests is immutable');
END
"""

_MANIFEST_DELETE_TRIGGER_DDL = f"""
CREATE TRIGGER {_MANIFEST_DELETE_TRIGGER}
BEFORE DELETE ON {_MANIFESTS_TABLE}
BEGIN
    SELECT RAISE(ABORT, 'baseline_manifests is immutable');
END
"""

_RESULT_UPDATE_TRIGGER_DDL = f"""
CREATE TRIGGER {_RESULT_UPDATE_TRIGGER}
BEFORE UPDATE ON {_RESULTS_TABLE}
BEGIN
    SELECT RAISE(ABORT, 'baseline_results is immutable');
END
"""

_RESULT_DELETE_TRIGGER_DDL = f"""
CREATE TRIGGER {_RESULT_DELETE_TRIGGER}
BEFORE DELETE ON {_RESULTS_TABLE}
BEGIN
    SELECT RAISE(ABORT, 'baseline_results is immutable');
END
"""

_TRIGGER_DDLS = {
    _MANIFEST_UPDATE_TRIGGER: _MANIFEST_UPDATE_TRIGGER_DDL,
    _MANIFEST_DELETE_TRIGGER: _MANIFEST_DELETE_TRIGGER_DDL,
    _RESULT_UPDATE_TRIGGER: _RESULT_UPDATE_TRIGGER_DDL,
    _RESULT_DELETE_TRIGGER: _RESULT_DELETE_TRIGGER_DDL,
}


def _serialize_digests(digests: tuple[str, ...]) -> str:
    return json.dumps(list(digests), separators=(",", ":"))


def _deserialize_digests(text: str) -> tuple[str, ...]:
    return tuple(json.loads(text))


def _serialize_int(value: int) -> str:
    return str(value)


def _serialize_optional_int(value: Optional[int]) -> Optional[str]:
    if value is None:
        return None
    return _serialize_int(value)


def _deserialize_int(text: object) -> int:
    if not isinstance(text, str):
        raise ValueError("integer value must be canonical decimal text")
    if not text:
        raise ValueError("integer value must not be empty")

    if text == "0":
        return 0

    if text[0] == "-":
        digits = text[1:]
        if not digits:
            raise ValueError("integer value must have digits")
    else:
        digits = text

    if digits[0] == "0":
        raise ValueError("non-canonical integer value")

    if not digits.isascii() or not digits.isdigit():
        raise ValueError("integer value must contain only ASCII decimal digits")

    value = int(text)
    if str(value) != text:
        raise ValueError("non-canonical integer value")

    return value


def _deserialize_optional_int(text: object) -> Optional[int]:
    if text is None:
        return None
    return _deserialize_int(text)


def _serialize_samples(
    samples: tuple[BaselineCountSampleV1, ...],
) -> str:
    return json.dumps(
        [
            [s.input_reference_digest, s.observation_count]
            for s in samples
        ],
        separators=(",", ":"),
    )


def _deserialize_samples(
    text: str,
) -> tuple[BaselineCountSampleV1, ...]:
    pairs = json.loads(text)
    return tuple(
        BaselineCountSampleV1(
            input_reference_digest=pair[0],
            observation_count=pair[1],
        )
        for pair in pairs
    )


def _validate_id(identifier: object) -> None:
    if type(identifier) is not str or not identifier.strip():
        raise ValueError("identifier must be a non-empty string")


class BaselineStore:
    """SQLite-backed append-only store for accepted baseline records."""

    def __init__(self, db_path: str | Path):
        self._db_path = Path(db_path)
        self._connection: Optional[sqlite3.Connection] = None
        self._closed = False
        self._open()

    def __enter__(self) -> "BaselineStore":
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

    # ── Manifest methods ─────────────────────────────────────────────────

    def insert_baseline_manifest(
        self,
        manifest: BaselineManifestV1,
    ) -> str:
        self._ensure_open()
        if type(manifest) is not BaselineManifestV1:
            raise ValueError("manifest must be BaselineManifestV1")

        with self._write_transaction():
            existing = self._fetch_manifest_row(
                manifest.baseline_manifest_id
            )
            if existing is None:
                self._connection.execute(
                    f"""
                    INSERT INTO {_MANIFESTS_TABLE} (
                        baseline_manifest_id,
                        schema_version,
                        record_kind,
                        baseline_manifest_digest,
                        analysis_type,
                        analysis_version,
                        baseline_method,
                        baseline_version,
                        subject_kind,
                        subject_reference,
                        window_start_source_timestamp_us,
                        window_end_source_timestamp_us,
                        time_basis,
                        boundary_policy,
                        input_reference_digests,
                        sample_count,
                        minimum_sample_count,
                        baseline_status,
                        status_reason_code,
                        created_ingest_timestamp_us,
                        analyzer_name,
                        analyzer_version,
                        analysis_mode,
                        source_contract_version
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    self._manifest_insert_values(manifest),
                )
                return "inserted"

            existing_manifest = self._manifest_from_row(existing)
            return compare_baseline_manifest_source_facts(
                existing_manifest,
                manifest,
            )

    def get_baseline_manifest(
        self,
        baseline_manifest_id: str,
    ) -> Optional[BaselineManifestV1]:
        self._ensure_open()
        _validate_id(baseline_manifest_id)
        row = self._fetch_manifest_row(baseline_manifest_id)
        if row is None:
            return None
        return self._manifest_from_row(row)

    def list_baseline_manifests(
        self,
    ) -> tuple[BaselineManifestV1, ...]:
        """Return manifests in deterministic source-window order."""
        self._ensure_open()
        rows = self._connection.execute(
            f"""
            SELECT *
            FROM {_MANIFESTS_TABLE}
            """
        ).fetchall()
        records = tuple(
            self._manifest_from_row(row) for row in rows
        )
        return tuple(
            sorted(
                records,
                key=lambda m: (
                    m.window_start_source_timestamp_us,
                    m.window_end_source_timestamp_us,
                    m.baseline_manifest_id,
                ),
            )
        )

    # ── Result methods ───────────────────────────────────────────────────

    def insert_baseline_result(
        self,
        result: BaselineResultV1,
    ) -> str:
        self._ensure_open()
        if type(result) is not BaselineResultV1:
            raise ValueError("result must be BaselineResultV1")

        with self._write_transaction():
            existing = self._fetch_result_row(result.baseline_result_id)
            if existing is not None:
                existing_result = self._result_from_row(existing)
                return compare_baseline_result_source_facts(
                    existing_result,
                    result,
                )

            parent_row = self._fetch_manifest_row(result.manifest_id)
            if parent_row is None:
                raise ValueError("parent manifest does not exist")

            parent = self._manifest_from_row(parent_row)
            self._validate_result_against_manifest(result, parent)

            existing_for_manifest = (
                self._fetch_result_row_for_manifest(result.manifest_id)
            )
            if existing_for_manifest is not None:
                return "identity_conflict"

            self._connection.execute(
                f"""
                INSERT INTO {_RESULTS_TABLE} (
                    baseline_result_id,
                    schema_version,
                    record_kind,
                    baseline_result_digest,
                    analysis_type,
                    analysis_version,
                    baseline_method,
                    baseline_version,
                    manifest_id,
                    manifest_digest,
                    samples,
                    sample_count,
                    minimum_sample_count,
                    baseline_status,
                    status_reason_code,
                    minimum_count,
                    maximum_count,
                    count_mean_numerator,
                    count_mean_denominator,
                    created_ingest_timestamp_us,
                    analyzer_name,
                    analyzer_version,
                    analysis_mode,
                    source_contract_version
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                self._result_insert_values(result),
            )
            return "inserted"

    def get_baseline_result(
        self,
        baseline_result_id: str,
    ) -> Optional[BaselineResultV1]:
        self._ensure_open()
        _validate_id(baseline_result_id)
        row = self._fetch_result_row(baseline_result_id)
        if row is None:
            return None
        return self._result_from_row(row)

    def get_baseline_result_for_manifest(
        self,
        baseline_manifest_id: str,
    ) -> Optional[BaselineResultV1]:
        self._ensure_open()
        _validate_id(baseline_manifest_id)
        row = self._fetch_result_row_for_manifest(
            baseline_manifest_id
        )
        if row is None:
            return None
        return self._result_from_row(row)

    def list_baseline_results(
        self,
    ) -> tuple[BaselineResultV1, ...]:
        """Return results ordered by parent manifest window then result id."""
        self._ensure_open()
        rows = self._connection.execute(
            f"""
            SELECT r.*,
                   m.window_start_source_timestamp_us
                       AS parent_window_start,
                   m.window_end_source_timestamp_us
                       AS parent_window_end
            FROM {_RESULTS_TABLE} r
            JOIN {_MANIFESTS_TABLE} m
                ON r.manifest_id = m.baseline_manifest_id
            """
        ).fetchall()
        records_with_keys = []
        for row in rows:
            result = self._result_from_row(row)
            key = (
                _deserialize_int(row["parent_window_start"]),
                _deserialize_int(row["parent_window_end"]),
                result.baseline_result_id,
            )
            records_with_keys.append((key, result))
        return tuple(
            result
            for _, result in sorted(
                records_with_keys,
                key=lambda item: item[0],
            )
        )

    # ── Bundle method ─────────────────────────────────────────────────────

    def insert_baseline_bundle(
        self,
        manifest: BaselineManifestV1,
        result: BaselineResultV1,
    ) -> str:
        self._ensure_open()
        if type(manifest) is not BaselineManifestV1:
            raise ValueError("manifest must be BaselineManifestV1")
        if type(result) is not BaselineResultV1:
            raise ValueError("result must be BaselineResultV1")

        with self._write_transaction():
            existing_manifest_row = self._fetch_manifest_row(
                manifest.baseline_manifest_id
            )

            manifest_present = existing_manifest_row is not None
            if manifest_present:
                existing_manifest = self._manifest_from_row(
                    existing_manifest_row
                )
                manifest_result = compare_baseline_manifest_source_facts(
                    existing_manifest,
                    manifest,
                )
                if manifest_result == "identity_conflict":
                    return "identity_conflict"
                authoritative_manifest = existing_manifest
            else:
                authoritative_manifest = manifest

            self._validate_result_against_manifest(
                result,
                authoritative_manifest,
            )

            existing_result_row = self._fetch_result_row(
                result.baseline_result_id
            )
            if existing_result_row is not None:
                existing_result = self._result_from_row(
                    existing_result_row
                )
                result_comparison = compare_baseline_result_source_facts(
                    existing_result,
                    result,
                )
                if result_comparison == "identity_conflict":
                    return "identity_conflict"
                existing_for_manifest = (
                    self._fetch_result_row_for_manifest(
                        result.manifest_id
                    )
                )
                if (
                    existing_for_manifest is not None
                    and existing_for_manifest["baseline_result_id"]
                    != result.baseline_result_id
                ):
                    return "identity_conflict"
                return "duplicate"

            existing_for_manifest = (
                self._fetch_result_row_for_manifest(
                    result.manifest_id
                )
            )
            if existing_for_manifest is not None:
                return "identity_conflict"

            if not manifest_present:
                self._connection.execute(
                    f"""
                    INSERT INTO {_MANIFESTS_TABLE} (
                        baseline_manifest_id,
                        schema_version,
                        record_kind,
                        baseline_manifest_digest,
                        analysis_type,
                        analysis_version,
                        baseline_method,
                        baseline_version,
                        subject_kind,
                        subject_reference,
                        window_start_source_timestamp_us,
                        window_end_source_timestamp_us,
                        time_basis,
                        boundary_policy,
                        input_reference_digests,
                        sample_count,
                        minimum_sample_count,
                        baseline_status,
                        status_reason_code,
                        created_ingest_timestamp_us,
                        analyzer_name,
                        analyzer_version,
                        analysis_mode,
                        source_contract_version
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    self._manifest_insert_values(manifest),
                )

            self._connection.execute(
                f"""
                INSERT INTO {_RESULTS_TABLE} (
                    baseline_result_id,
                    schema_version,
                    record_kind,
                    baseline_result_digest,
                    analysis_type,
                    analysis_version,
                    baseline_method,
                    baseline_version,
                    manifest_id,
                    manifest_digest,
                    samples,
                    sample_count,
                    minimum_sample_count,
                    baseline_status,
                    status_reason_code,
                    minimum_count,
                    maximum_count,
                    count_mean_numerator,
                    count_mean_denominator,
                    created_ingest_timestamp_us,
                    analyzer_name,
                    analyzer_version,
                    analysis_mode,
                    source_contract_version
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                self._result_insert_values(result),
            )

            return "inserted"

    # ── Internal: connection management ───────────────────────────────────

    def _open(self) -> None:
        if self._connection is not None:
            return

        connection = sqlite3.connect(
            str(self._db_path),
            timeout=30,
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
            raise RuntimeError("BaselineStore is closed")

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
            self._bootstrap_execute(_MANIFESTS_TABLE_DDL)
            self._bootstrap_execute(_RESULTS_TABLE_DDL)
            self._bootstrap_execute(_MANIFEST_UPDATE_TRIGGER_DDL)
            self._bootstrap_execute(_MANIFEST_DELETE_TRIGGER_DDL)
            self._bootstrap_execute(_RESULT_UPDATE_TRIGGER_DDL)
            self._bootstrap_execute(_RESULT_DELETE_TRIGGER_DDL)
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
            _MANIFESTS_TABLE,
            _RESULTS_TABLE,
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
            _MANIFESTS_TABLE,
            _MANIFESTS_TABLE_DDL,
        )
        self._validate_table_ddl(
            _RESULTS_TABLE,
            _RESULTS_TABLE_DDL,
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
            or metadata_row["store_schema_version"]
            != _STORE_SCHEMA_VERSION
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

        if (
            self._normalize_sql(row["sql"])
            != self._normalize_sql(expected_sql)
        ):
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

        if (
            self._normalize_sql(row["sql"])
            != self._normalize_sql(expected_sql)
        ):
            raise ValueError("unexpected trigger body")

    @staticmethod
    def _normalize_sql(sql: str) -> str:
        return " ".join(sql.strip().split()).rstrip(";").lower()

    # ── Internal: row fetchers ────────────────────────────────────────────

    def _fetch_manifest_row(
        self,
        baseline_manifest_id: str,
    ) -> Optional[sqlite3.Row]:
        return self._connection.execute(
            f"""
            SELECT *
            FROM {_MANIFESTS_TABLE}
            WHERE baseline_manifest_id = ?
            """,
            (baseline_manifest_id,),
        ).fetchone()

    def _fetch_result_row(
        self,
        baseline_result_id: str,
    ) -> Optional[sqlite3.Row]:
        return self._connection.execute(
            f"""
            SELECT *
            FROM {_RESULTS_TABLE}
            WHERE baseline_result_id = ?
            """,
            (baseline_result_id,),
        ).fetchone()

    def _fetch_result_row_for_manifest(
        self,
        baseline_manifest_id: str,
    ) -> Optional[sqlite3.Row]:
        return self._connection.execute(
            f"""
            SELECT *
            FROM {_RESULTS_TABLE}
            WHERE manifest_id = ?
            """,
            (baseline_manifest_id,),
        ).fetchone()

    # ── Internal: parent consistency validation ───────────────────────────

    @staticmethod
    def _validate_result_against_manifest(
        result: BaselineResultV1,
        manifest: BaselineManifestV1,
    ) -> None:
        if result.manifest_id != manifest.baseline_manifest_id:
            raise ValueError("manifest_id mismatch")
        if result.manifest_digest != manifest.baseline_manifest_digest:
            raise ValueError("manifest_digest mismatch")
        if result.analysis_type != manifest.analysis_type:
            raise ValueError("analysis_type mismatch")
        if result.analysis_version != manifest.analysis_version:
            raise ValueError("analysis_version mismatch")
        if result.baseline_method != manifest.baseline_method:
            raise ValueError("baseline_method mismatch")
        if result.baseline_version != manifest.baseline_version:
            raise ValueError("baseline_version mismatch")
        if result.sample_count != manifest.sample_count:
            raise ValueError("sample_count mismatch")
        if (
            result.minimum_sample_count
            != manifest.minimum_sample_count
        ):
            raise ValueError("minimum_sample_count mismatch")
        if result.baseline_status != manifest.baseline_status:
            raise ValueError("baseline_status mismatch")
        if result.status_reason_code != manifest.status_reason_code:
            raise ValueError("status_reason_code mismatch")

        result_digests = tuple(
            s.input_reference_digest for s in result.samples
        )
        if result_digests != manifest.input_reference_digests:
            raise ValueError(
                "sample digests do not match manifest "
                "input_reference_digests"
            )

    # ── Internal: insert values ───────────────────────────────────────────

    @staticmethod
    def _manifest_insert_values(
        manifest: BaselineManifestV1,
    ) -> tuple[object, ...]:
        provenance = manifest.provenance
        return (
            manifest.baseline_manifest_id,
            manifest.schema_version,
            manifest.record_kind,
            manifest.baseline_manifest_digest,
            manifest.analysis_type,
            manifest.analysis_version,
            manifest.baseline_method,
            manifest.baseline_version,
            manifest.subject_kind,
            manifest.subject_reference,
            _serialize_int(manifest.window_start_source_timestamp_us),
            _serialize_int(manifest.window_end_source_timestamp_us),
            manifest.time_basis,
            manifest.boundary_policy,
            _serialize_digests(manifest.input_reference_digests),
            _serialize_int(manifest.sample_count),
            _serialize_int(manifest.minimum_sample_count),
            manifest.baseline_status,
            manifest.status_reason_code,
            _serialize_int(manifest.created_ingest_timestamp_us),
            provenance.analyzer_name,
            provenance.analyzer_version,
            provenance.analysis_mode,
            provenance.source_contract_version,
        )

    @staticmethod
    def _result_insert_values(
        result: BaselineResultV1,
    ) -> tuple[object, ...]:
        provenance = result.provenance
        return (
            result.baseline_result_id,
            result.schema_version,
            result.record_kind,
            result.baseline_result_digest,
            result.analysis_type,
            result.analysis_version,
            result.baseline_method,
            result.baseline_version,
            result.manifest_id,
            result.manifest_digest,
            _serialize_samples(result.samples),
            _serialize_int(result.sample_count),
            _serialize_int(result.minimum_sample_count),
            result.baseline_status,
            result.status_reason_code,
            _serialize_optional_int(result.minimum_count),
            _serialize_optional_int(result.maximum_count),
            _serialize_optional_int(result.count_mean_numerator),
            _serialize_optional_int(result.count_mean_denominator),
            _serialize_int(result.created_ingest_timestamp_us),
            provenance.analyzer_name,
            provenance.analyzer_version,
            provenance.analysis_mode,
            provenance.source_contract_version,
        )

    # ── Internal: row deserializers ───────────────────────────────────────

    @staticmethod
    def _manifest_from_row(
        row: sqlite3.Row,
    ) -> BaselineManifestV1:
        return BaselineManifestV1(
            schema_version=row["schema_version"],
            record_kind=row["record_kind"],
            baseline_manifest_id=row["baseline_manifest_id"],
            baseline_manifest_digest=row[
                "baseline_manifest_digest"
            ],
            analysis_type=row["analysis_type"],
            analysis_version=row["analysis_version"],
            baseline_method=row["baseline_method"],
            baseline_version=row["baseline_version"],
            subject_kind=row["subject_kind"],
            subject_reference=row["subject_reference"],
            window_start_source_timestamp_us=_deserialize_int(
                row["window_start_source_timestamp_us"]
            ),
            window_end_source_timestamp_us=_deserialize_int(
                row["window_end_source_timestamp_us"]
            ),
            time_basis=row["time_basis"],
            boundary_policy=row["boundary_policy"],
            input_reference_digests=_deserialize_digests(
                row["input_reference_digests"]
            ),
            sample_count=_deserialize_int(row["sample_count"]),
            minimum_sample_count=_deserialize_int(
                row["minimum_sample_count"]
            ),
            baseline_status=row["baseline_status"],
            status_reason_code=row["status_reason_code"],
            created_ingest_timestamp_us=_deserialize_int(
                row["created_ingest_timestamp_us"]
            ),
            provenance=BaselineProvenanceV1(
                analyzer_name=row["analyzer_name"],
                analyzer_version=row["analyzer_version"],
                analysis_mode=row["analysis_mode"],
                source_contract_version=row[
                    "source_contract_version"
                ],
            ),
        )

    @staticmethod
    def _result_from_row(
        row: sqlite3.Row,
    ) -> BaselineResultV1:
        return BaselineResultV1(
            schema_version=row["schema_version"],
            record_kind=row["record_kind"],
            baseline_result_id=row["baseline_result_id"],
            baseline_result_digest=row[
                "baseline_result_digest"
            ],
            analysis_type=row["analysis_type"],
            analysis_version=row["analysis_version"],
            baseline_method=row["baseline_method"],
            baseline_version=row["baseline_version"],
            manifest_id=row["manifest_id"],
            manifest_digest=row["manifest_digest"],
            samples=_deserialize_samples(row["samples"]),
            sample_count=_deserialize_int(row["sample_count"]),
            minimum_sample_count=_deserialize_int(
                row["minimum_sample_count"]
            ),
            baseline_status=row["baseline_status"],
            status_reason_code=row["status_reason_code"],
            minimum_count=_deserialize_optional_int(
                row["minimum_count"]
            ),
            maximum_count=_deserialize_optional_int(
                row["maximum_count"]
            ),
            count_mean_numerator=_deserialize_optional_int(
                row["count_mean_numerator"]
            ),
            count_mean_denominator=_deserialize_optional_int(
                row["count_mean_denominator"]
            ),
            created_ingest_timestamp_us=_deserialize_int(
                row["created_ingest_timestamp_us"]
            ),
            provenance=BaselineProvenanceV1(
                analyzer_name=row["analyzer_name"],
                analyzer_version=row["analyzer_version"],
                analysis_mode=row["analysis_mode"],
                source_contract_version=row[
                    "source_contract_version"
                ],
            ),
        )


__all__ = ["BaselineStore"]
