"""Deterministic focused tests for BaselineStore (P3)."""

import ast
import copy
import gc
from contextlib import closing
from dataclasses import FrozenInstanceError
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest
import warnings
from typing import Optional, Tuple

from baseline_contract import (
    BaselineManifestV1,
    BaselineProvenanceV1,
)
from baseline_result import (
    BaselineCountSampleV1,
    BaselineResultV1,
    create_baseline_result,
)
from baseline_store import (
    __all__ as STORE_ALL,
    BaselineStore,
)


HMAC_KEY_A = b"test-key-alpha"
HMAC_KEY_B = b"test-key-beta"

WINDOW_START = 1_000_000_000_000
WINDOW_END = 1_000_000_360_000
INGEST_TS = WINDOW_END + 1000

HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64
HEX_D = "d" * 64
HEX_E = "e" * 64


# ── Helpers ───────────────────────────────────────────────────────────────


def make_provenance(
    analysis_mode: str = "synthetic",
    source_contract_version: str = "1.0",
    analyzer_name: str = "cyt.baseline",
    analyzer_version: str = "1.0.0",
) -> BaselineProvenanceV1:
    return BaselineProvenanceV1(
        analyzer_name=analyzer_name,
        analyzer_version=analyzer_version,
        analysis_mode=analysis_mode,
        source_contract_version=source_contract_version,
    )


def make_manifest(
    hmac_key: bytes = HMAC_KEY_A,
    input_reference_digests: Tuple[str, ...] = (HEX_A, HEX_B),
    minimum_sample_count: int = 2,
    window_start: int = WINDOW_START,
    window_end: int = WINDOW_END,
    **overrides,
) -> BaselineManifestV1:
    from baseline_contract import create_baseline_manifest

    kwargs = {
        "hmac_key": hmac_key,
        "analysis_type": "observation.count_per_collection_session",
        "analysis_version": "1.0.0",
        "baseline_method": "count_mean_range",
        "baseline_version": "1.0.0",
        "subject_kind": "device.aggregate",
        "subject_reference": HEX_C,
        "window_start_source_timestamp_us": window_start,
        "window_end_source_timestamp_us": window_end,
        "input_reference_digests": input_reference_digests,
        "minimum_sample_count": minimum_sample_count,
        "created_ingest_timestamp_us": INGEST_TS,
        "provenance": make_provenance(),
    }
    kwargs.update(overrides)
    return create_baseline_manifest(**kwargs)


def make_sample(
    input_reference_digest: str,
    observation_count: int = 5,
) -> BaselineCountSampleV1:
    return BaselineCountSampleV1(
        input_reference_digest=input_reference_digest,
        observation_count=observation_count,
    )


def make_samples_from_manifest(
    manifest: BaselineManifestV1,
    count: int = 5,
) -> Tuple[BaselineCountSampleV1, ...]:
    return tuple(
        make_sample(d, observation_count=count)
        for d in manifest.input_reference_digests
    )


def make_result(
    hmac_key: bytes = HMAC_KEY_A,
    manifest: Optional[BaselineManifestV1] = None,
    samples: Optional[Tuple[BaselineCountSampleV1, ...]] = None,
    created_ingest_timestamp_us: int = INGEST_TS,
    provenance: Optional[BaselineProvenanceV1] = None,
    **overrides,
) -> BaselineResultV1:
    if manifest is None:
        m = make_manifest(hmac_key=hmac_key)
    else:
        m = manifest
    if samples is None:
        samples_input = make_samples_from_manifest(m)
    else:
        samples_input = samples
    if provenance is None:
        prov = make_provenance()
    else:
        prov = provenance
    kwargs = {
        "hmac_key": hmac_key,
        "manifest": m,
        "samples": samples_input,
        "created_ingest_timestamp_us": created_ingest_timestamp_us,
        "provenance": prov,
    }
    kwargs.update(overrides)
    return create_baseline_result(**kwargs)


# ── Test class ────────────────────────────────────────────────────────────


class BaselineStoreTests(unittest.TestCase):

    # ── Setup helpers ─────────────────────────────────────────────────

    def open_store(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        path = Path(tempdir.name) / "baseline.sqlite"
        store = BaselineStore(path)
        self.addCleanup(store.close)
        return store, path

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
    def trigger_names(path):
        with closing(sqlite3.connect(path)) as connection:
            return {
                row[0]
                for row in connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'trigger'
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
                CREATE TABLE baseline_manifests (
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
            )
            connection.execute(
                """
                CREATE TABLE baseline_results (
                    baseline_result_id TEXT NOT NULL PRIMARY KEY,
                    schema_version TEXT NOT NULL,
                    record_kind TEXT NOT NULL,
                    baseline_result_digest TEXT NOT NULL,
                    analysis_type TEXT NOT NULL,
                    analysis_version TEXT NOT NULL,
                    baseline_method TEXT NOT NULL,
                    baseline_version TEXT NOT NULL,
                    manifest_id TEXT NOT NULL REFERENCES baseline_manifests (
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
            )
            for name, table, msg in (
                ("baseline_manifests_no_update", "baseline_manifests",
                 "baseline_manifests is immutable"),
                ("baseline_manifests_no_delete", "baseline_manifests",
                 "baseline_manifests is immutable"),
                ("baseline_results_no_update", "baseline_results",
                 "baseline_results is immutable"),
                ("baseline_results_no_delete", "baseline_results",
                 "baseline_results is immutable"),
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

    # ── Bootstrap and schema metadata ─────────────────────────────────

    def test_new_store_bootstraps_exact_schema_and_metadata(self):
        store, path = self.open_store()

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
                SELECT singleton, store_schema_version,
                       contract_schema_version, initialized_at_us
                FROM store_metadata
                """
            ).fetchone()
            self.assertEqual(metadata[0], 1)
            self.assertEqual(metadata[1], 1)
            self.assertEqual(metadata[2], "1.0")
            self.assertEqual(metadata[3], 0)

        self.assertEqual(
            self.table_names(path),
            {
                "store_metadata",
                "baseline_manifests",
                "baseline_results",
            },
        )
        self.assertEqual(
            self.trigger_names(path),
            {
                "baseline_manifests_no_update",
                "baseline_manifests_no_delete",
                "baseline_results_no_update",
                "baseline_results_no_delete",
            },
        )
        self.assertEqual(
            self.table_info(path, "baseline_manifests")[0],
            ("baseline_manifest_id", "TEXT", 1, 1, None),
        )
        self.assertEqual(
            self.table_info(path, "baseline_manifests")[10],
            ("window_start_source_timestamp_us", "TEXT", 1, 0, None),
        )
        self.assertEqual(
            self.table_info(path, "baseline_manifests")[15],
            ("sample_count", "TEXT", 1, 0, None),
        )
        self.assertEqual(
            self.table_info(path, "baseline_results")[8],
            ("manifest_id", "TEXT", 1, 0, None),
        )
        self.assertEqual(
            self.table_info(path, "baseline_results")[11],
            ("sample_count", "TEXT", 1, 0, None),
        )
        self.assertEqual(
            self.table_info(path, "baseline_results")[15],
            ("minimum_count", "TEXT", 0, 0, None),
        )
        self.assertEqual(
            self.table_info(path, "baseline_results")[19],
            ("created_ingest_timestamp_us", "TEXT", 1, 0, None),
        )

    def test_valid_database_reopens_successfully(self):
        store, path = self.open_store()
        manifest = make_manifest()
        self.assertEqual(
            store.insert_baseline_manifest(manifest),
            "inserted",
        )
        store.close()

        reopened = BaselineStore(path)
        self.addCleanup(reopened.close)
        self.assertEqual(
            reopened.get_baseline_manifest(
                manifest.baseline_manifest_id
            ),
            manifest,
        )

    # ── Manifest roundtrip ────────────────────────────────────────────

    def test_manifest_insert_fetch_list_reopen_reconstruct(self):
        store, path = self.open_store()
        manifest = make_manifest()

        self.assertEqual(
            store.insert_baseline_manifest(manifest),
            "inserted",
        )
        self.assertEqual(
            store.get_baseline_manifest(
                manifest.baseline_manifest_id
            ),
            manifest,
        )
        self.assertEqual(
            store.list_baseline_manifests(),
            (manifest,),
        )

        store.close()
        reopened = BaselineStore(path)
        self.addCleanup(reopened.close)
        self.assertEqual(
            reopened.get_baseline_manifest(
                manifest.baseline_manifest_id
            ),
            manifest,
        )
        self.assertEqual(
            reopened.list_baseline_manifests(),
            (manifest,),
        )

    def test_manifest_frozen_returned_record(self):
        store, _ = self.open_store()
        manifest = make_manifest()
        self.assertEqual(
            store.insert_baseline_manifest(manifest),
            "inserted",
        )
        stored = store.get_baseline_manifest(
            manifest.baseline_manifest_id
        )
        with self.assertRaises(FrozenInstanceError):
            stored.analysis_type = "changed"

    # ── Manifest duplicate and conflict ───────────────────────────────

    def test_manifest_duplicate_returns_duplicate(self):
        store, _ = self.open_store()
        manifest = make_manifest()
        self.assertEqual(
            store.insert_baseline_manifest(manifest),
            "inserted",
        )
        self.assertEqual(
            store.insert_baseline_manifest(manifest),
            "duplicate",
        )

    def test_manifest_identity_conflict_preserves_first_row(self):
        store, _ = self.open_store()
        manifest = make_manifest()
        self.assertEqual(
            store.insert_baseline_manifest(manifest),
            "inserted",
        )

        conflict = BaselineManifestV1(
            schema_version=manifest.schema_version,
            record_kind=manifest.record_kind,
            baseline_manifest_id=manifest.baseline_manifest_id,
            baseline_manifest_digest=(
                manifest.baseline_manifest_digest
            ),
            analysis_type="different.type",
            analysis_version=manifest.analysis_version,
            baseline_method=manifest.baseline_method,
            baseline_version=manifest.baseline_version,
            subject_kind=manifest.subject_kind,
            subject_reference=manifest.subject_reference,
            window_start_source_timestamp_us=(
                manifest.window_start_source_timestamp_us
            ),
            window_end_source_timestamp_us=(
                manifest.window_end_source_timestamp_us
            ),
            time_basis=manifest.time_basis,
            boundary_policy=manifest.boundary_policy,
            input_reference_digests=(
                manifest.input_reference_digests
            ),
            sample_count=manifest.sample_count,
            minimum_sample_count=manifest.minimum_sample_count,
            baseline_status=manifest.baseline_status,
            status_reason_code=manifest.status_reason_code,
            created_ingest_timestamp_us=(
                manifest.created_ingest_timestamp_us
            ),
            provenance=manifest.provenance,
        )
        self.assertEqual(
            store.insert_baseline_manifest(conflict),
            "identity_conflict",
        )
        self.assertEqual(
            store.get_baseline_manifest(
                manifest.baseline_manifest_id
            ),
            manifest,
        )

    def test_manifest_operational_differences_return_duplicate(self):
        store, _ = self.open_store()
        manifest = make_manifest(
            created_ingest_timestamp_us=INGEST_TS,
            provenance=make_provenance(
                analyzer_name="cyt.baseline",
                analysis_mode="synthetic",
            ),
        )
        self.assertEqual(
            store.insert_baseline_manifest(manifest),
            "inserted",
        )

        operational_dup = make_manifest(
            created_ingest_timestamp_us=INGEST_TS + 5000,
            provenance=make_provenance(
                analyzer_name="other.analyzer",
                analyzer_version="9.9.9",
                analysis_mode="live",
            ),
        )
        self.assertEqual(
            operational_dup.baseline_manifest_id,
            manifest.baseline_manifest_id,
        )
        self.assertEqual(
            store.insert_baseline_manifest(operational_dup),
            "duplicate",
        )
        self.assertEqual(
            store.get_baseline_manifest(
                manifest.baseline_manifest_id
            ),
            manifest,
        )

    def test_manifest_source_contract_version_conflict(self):
        store, _ = self.open_store()
        manifest = make_manifest(
            provenance=make_provenance(source_contract_version="1.0"),
        )
        self.assertEqual(
            store.insert_baseline_manifest(manifest),
            "inserted",
        )

        conflict = BaselineManifestV1(
            schema_version=manifest.schema_version,
            record_kind=manifest.record_kind,
            baseline_manifest_id=manifest.baseline_manifest_id,
            baseline_manifest_digest=(
                manifest.baseline_manifest_digest
            ),
            analysis_type=manifest.analysis_type,
            analysis_version=manifest.analysis_version,
            baseline_method=manifest.baseline_method,
            baseline_version=manifest.baseline_version,
            subject_kind=manifest.subject_kind,
            subject_reference=manifest.subject_reference,
            window_start_source_timestamp_us=(
                manifest.window_start_source_timestamp_us
            ),
            window_end_source_timestamp_us=(
                manifest.window_end_source_timestamp_us
            ),
            time_basis=manifest.time_basis,
            boundary_policy=manifest.boundary_policy,
            input_reference_digests=(
                manifest.input_reference_digests
            ),
            sample_count=manifest.sample_count,
            minimum_sample_count=manifest.minimum_sample_count,
            baseline_status=manifest.baseline_status,
            status_reason_code=manifest.status_reason_code,
            created_ingest_timestamp_us=(
                manifest.created_ingest_timestamp_us
            ),
            provenance=BaselineProvenanceV1(
                analyzer_name=manifest.provenance.analyzer_name,
                analyzer_version=manifest.provenance.analyzer_version,
                analysis_mode=manifest.provenance.analysis_mode,
                source_contract_version="2.0",
            ),
        )
        self.assertEqual(
            store.insert_baseline_manifest(conflict),
            "identity_conflict",
        )
        self.assertEqual(
            store.get_baseline_manifest(
                manifest.baseline_manifest_id
            ),
            manifest,
        )

    # ── Result roundtrip ──────────────────────────────────────────────

    def test_available_result_roundtrip(self):
        store, path = self.open_store()
        manifest = make_manifest(
            input_reference_digests=(HEX_A, HEX_B),
            minimum_sample_count=2,
        )
        self.assertEqual(
            store.insert_baseline_manifest(manifest),
            "inserted",
        )
        samples = (
            make_sample(HEX_A, 7),
            make_sample(HEX_B, 11),
        )
        result = make_result(
            manifest=manifest,
            samples=samples,
        )
        self.assertEqual(
            store.insert_baseline_result(result),
            "inserted",
        )
        self.assertEqual(
            store.get_baseline_result(result.baseline_result_id),
            result,
        )
        self.assertEqual(
            store.get_baseline_result_for_manifest(
                manifest.baseline_manifest_id
            ),
            result,
        )

        store.close()
        reopened = BaselineStore(path)
        self.addCleanup(reopened.close)
        self.assertEqual(
            reopened.get_baseline_result(result.baseline_result_id),
            result,
        )

    def test_insufficient_data_result_roundtrip(self):
        store, _ = self.open_store()
        manifest = make_manifest(
            input_reference_digests=(HEX_A,),
            minimum_sample_count=2,
        )
        self.assertEqual(
            store.insert_baseline_manifest(manifest),
            "inserted",
        )
        samples = (make_sample(HEX_A, 5),)
        result = make_result(manifest=manifest, samples=samples)
        self.assertEqual(result.baseline_status, "insufficient_data")
        self.assertEqual(
            store.insert_baseline_result(result),
            "inserted",
        )
        self.assertEqual(
            store.get_baseline_result(result.baseline_result_id),
            result,
        )
        stored = store.get_baseline_result(result.baseline_result_id)
        self.assertIsNone(stored.minimum_count)
        self.assertIsNone(stored.maximum_count)
        self.assertIsNone(stored.count_mean_numerator)
        self.assertIsNone(stored.count_mean_denominator)

    def test_unknown_result_roundtrip(self):
        store, _ = self.open_store()
        manifest = make_manifest(
            input_reference_digests=(),
            minimum_sample_count=2,
        )
        self.assertEqual(
            store.insert_baseline_manifest(manifest),
            "inserted",
        )
        result = make_result(
            manifest=manifest,
            samples=(),
        )
        self.assertEqual(result.baseline_status, "unknown")
        self.assertEqual(
            store.insert_baseline_result(result),
            "inserted",
        )
        self.assertEqual(
            store.get_baseline_result(result.baseline_result_id),
            result,
        )

    def test_result_sample_counts_and_mean_components_remain_integers(self):
        store, _ = self.open_store()
        manifest = make_manifest(
            input_reference_digests=(HEX_A, HEX_B, HEX_C),
            minimum_sample_count=2,
        )
        self.assertEqual(
            store.insert_baseline_manifest(manifest),
            "inserted",
        )
        samples = (
            make_sample(HEX_A, 1),
            make_sample(HEX_B, 1),
            make_sample(HEX_C, 2),
        )
        result = make_result(manifest=manifest, samples=samples)
        self.assertEqual(
            store.insert_baseline_result(result),
            "inserted",
        )
        stored = store.get_baseline_result(
            result.baseline_result_id
        )
        self.assertIs(type(stored.minimum_count), int)
        self.assertIs(type(stored.maximum_count), int)
        self.assertIs(type(stored.count_mean_numerator), int)
        self.assertIs(type(stored.count_mean_denominator), int)
        for s in stored.samples:
            self.assertIs(type(s.observation_count), int)
        self.assertEqual(stored.count_mean_numerator, 4)
        self.assertEqual(stored.count_mean_denominator, 3)

    def test_result_frozen_returned_record(self):
        store, _ = self.open_store()
        manifest = make_manifest()
        self.assertEqual(
            store.insert_baseline_manifest(manifest),
            "inserted",
        )
        result = make_result(manifest=manifest)
        self.assertEqual(
            store.insert_baseline_result(result),
            "inserted",
        )
        stored = store.get_baseline_result(
            result.baseline_result_id
        )
        with self.assertRaises(FrozenInstanceError):
            stored.baseline_status = "changed"

    # ── Result duplicate and conflict ─────────────────────────────────

    def test_result_duplicate_returns_duplicate(self):
        store, _ = self.open_store()
        manifest = make_manifest()
        self.assertEqual(
            store.insert_baseline_manifest(manifest),
            "inserted",
        )
        result = make_result(manifest=manifest)
        self.assertEqual(
            store.insert_baseline_result(result),
            "inserted",
        )
        self.assertEqual(
            store.insert_baseline_result(result),
            "duplicate",
        )

    def test_result_identity_conflict_preserves_first_row(self):
        store, _ = self.open_store()
        manifest = make_manifest(
            input_reference_digests=(HEX_A, HEX_B),
            minimum_sample_count=2,
        )
        self.assertEqual(
            store.insert_baseline_manifest(manifest),
            "inserted",
        )
        s1 = (make_sample(HEX_A, 3), make_sample(HEX_B, 10))
        result = make_result(manifest=manifest, samples=s1)
        self.assertEqual(
            store.insert_baseline_result(result),
            "inserted",
        )

        s2 = (make_sample(HEX_A, 99), make_sample(HEX_B, 99))
        conflict = make_result(manifest=manifest, samples=s2)
        self.assertEqual(
            conflict.baseline_result_id,
            result.baseline_result_id,
        )
        self.assertEqual(
            store.insert_baseline_result(conflict),
            "identity_conflict",
        )
        self.assertEqual(
            store.get_baseline_result(result.baseline_result_id),
            result,
        )

    def test_result_operational_differences_return_duplicate(self):
        store, _ = self.open_store()
        manifest = make_manifest()
        self.assertEqual(
            store.insert_baseline_manifest(manifest),
            "inserted",
        )
        result = make_result(
            manifest=manifest,
            created_ingest_timestamp_us=INGEST_TS,
            provenance=make_provenance(
                analyzer_name="cyt.baseline",
                analysis_mode="synthetic",
            ),
        )
        self.assertEqual(
            store.insert_baseline_result(result),
            "inserted",
        )

        operational_dup = make_result(
            manifest=manifest,
            created_ingest_timestamp_us=INGEST_TS + 5000,
            provenance=make_provenance(
                analyzer_name="other.analyzer",
                analyzer_version="9.9.9",
                analysis_mode="live",
            ),
        )
        self.assertEqual(
            operational_dup.baseline_result_id,
            result.baseline_result_id,
        )
        self.assertEqual(
            store.insert_baseline_result(operational_dup),
            "duplicate",
        )
        self.assertEqual(
            store.get_baseline_result(result.baseline_result_id),
            result,
        )

    def test_result_source_contract_version_conflict(self):
        store, _ = self.open_store()
        manifest = make_manifest()
        self.assertEqual(
            store.insert_baseline_manifest(manifest),
            "inserted",
        )
        result = make_result(
            provenance=make_provenance(source_contract_version="1.0"),
        )
        self.assertEqual(
            store.insert_baseline_result(result),
            "inserted",
        )

        conflict_prov = BaselineProvenanceV1(
            analyzer_name=result.provenance.analyzer_name,
            analyzer_version=result.provenance.analyzer_version,
            analysis_mode=result.provenance.analysis_mode,
            source_contract_version="2.0",
        )
        conflict = copy.copy(result)
        object.__setattr__(conflict, "provenance", conflict_prov)
        self.assertEqual(
            store.insert_baseline_result(conflict),
            "identity_conflict",
        )
        self.assertEqual(
            store.get_baseline_result(result.baseline_result_id),
            result,
        )

    # ── Missing parent manifest ───────────────────────────────────────

    def test_missing_parent_manifest_rejects_result_no_partial_write(self):
        store, path = self.open_store()
        orphan_manifest = make_manifest()
        orphan_result = make_result(manifest=orphan_manifest)

        with self.assertRaises(ValueError):
            store.insert_baseline_result(orphan_result)

        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM baseline_results"
                ).fetchone()[0],
                0,
            )

    # ── Large integer and canonical regressions ───────────────────────

    def test_large_manifest_integer_roundtrip(self):
        large = 2**63 + 1000
        store, path = self.open_store()
        manifest = make_manifest(
            window_start=large,
            window_end=large + 1_000_000,
            minimum_sample_count=large,
            input_reference_digests=(HEX_A,),
            created_ingest_timestamp_us=large,
        )
        self.assertEqual(
            store.insert_baseline_manifest(manifest),
            "inserted",
        )
        self.assertEqual(
            store.get_baseline_manifest(
                manifest.baseline_manifest_id
            ),
            manifest,
        )
        self.assertEqual(
            store.list_baseline_manifests(),
            (manifest,),
        )

        store.close()
        reopened = BaselineStore(path)
        self.addCleanup(reopened.close)
        stored = reopened.get_baseline_manifest(
            manifest.baseline_manifest_id
        )
        self.assertEqual(stored, manifest)
        self.assertIs(
            type(stored.window_start_source_timestamp_us),
            int,
        )
        self.assertIs(
            type(stored.window_end_source_timestamp_us),
            int,
        )
        self.assertIs(type(stored.sample_count), int)
        self.assertIs(type(stored.minimum_sample_count), int)
        self.assertIs(
            type(stored.created_ingest_timestamp_us),
            int,
        )

    def test_large_exact_mean_numerator_roundtrip(self):
        store, path = self.open_store()
        manifest = make_manifest(
            input_reference_digests=(HEX_A, HEX_B),
            minimum_sample_count=2,
        )
        samples = (
            make_sample(HEX_A, 2**63 - 1),
            make_sample(HEX_B, 2**63 - 2),
        )
        result = make_result(manifest=manifest, samples=samples)
        self.assertEqual(result.count_mean_numerator, 2**64 - 3)
        self.assertEqual(result.count_mean_denominator, 2)

        self.assertEqual(
            store.insert_baseline_manifest(manifest),
            "inserted",
        )
        self.assertEqual(
            store.insert_baseline_result(result),
            "inserted",
        )

        store.close()
        reopened = BaselineStore(path)
        self.addCleanup(reopened.close)
        stored = reopened.get_baseline_result(
            result.baseline_result_id
        )
        self.assertEqual(stored, result)
        self.assertIs(type(stored.count_mean_numerator), int)
        self.assertIs(type(stored.count_mean_denominator), int)
        self.assertEqual(
            stored.count_mean_numerator,
            2**64 - 3,
        )
        self.assertEqual(stored.count_mean_denominator, 2)

    def test_large_result_operational_timestamp_roundtrip(self):
        large_ts = 2**63 + 5000
        store, path = self.open_store()
        manifest = make_manifest()
        result = make_result(
            manifest=manifest,
            created_ingest_timestamp_us=large_ts,
        )
        self.assertEqual(
            store.insert_baseline_manifest(manifest),
            "inserted",
        )
        self.assertEqual(
            store.insert_baseline_result(result),
            "inserted",
        )

        store.close()
        reopened = BaselineStore(path)
        self.addCleanup(reopened.close)
        stored = reopened.get_baseline_result(
            result.baseline_result_id
        )
        self.assertEqual(stored, result)
        self.assertIs(type(stored.created_ingest_timestamp_us), int)
        self.assertEqual(
            stored.created_ingest_timestamp_us,
            large_ts,
        )

    def test_numeric_ordering_across_decimal_widths(self):
        store, _ = self.open_store()
        large = 2**63 + 1

        m_small = make_manifest(
            window_start=9,
            window_end=10,
            input_reference_digests=(HEX_A,),
            minimum_sample_count=1,
        )
        m_ten = make_manifest(
            window_start=10,
            window_end=11,
            input_reference_digests=(HEX_B,),
            minimum_sample_count=1,
        )
        m_large = make_manifest(
            window_start=large,
            window_end=large + 1,
            input_reference_digests=(HEX_C,),
            minimum_sample_count=1,
        )

        for m in (m_large, m_ten, m_small):
            self.assertEqual(
                store.insert_baseline_manifest(m),
                "inserted",
            )

        expected_manifests = (m_small, m_ten, m_large)
        self.assertEqual(
            store.list_baseline_manifests(),
            expected_manifests,
        )

        r_small = make_result(manifest=m_small)
        r_ten = make_result(manifest=m_ten)
        r_large = make_result(manifest=m_large)
        for r in (r_large, r_ten, r_small):
            self.assertEqual(
                store.insert_baseline_result(r),
                "inserted",
            )

        expected_results = (r_small, r_ten, r_large)
        self.assertEqual(
            store.list_baseline_results(),
            expected_results,
        )

    def test_canonical_stored_integer_rejection(self):
        for malformed in (
            "01", "+1", " 1", "1.0",
            "١", "１２", "𝟙", "-١",
        ):
            with self.subTest(malformed=malformed):
                store, path = self.open_store()
                manifest = make_manifest()
                self.assertEqual(
                    store.insert_baseline_manifest(manifest),
                    "inserted",
                )
                store.close()

                with closing(sqlite3.connect(path)) as connection:
                    row = connection.execute(
                        """
                        SELECT *
                        FROM baseline_manifests
                        WHERE baseline_manifest_id = ?
                        """,
                        (manifest.baseline_manifest_id,),
                    ).fetchone()
                    columns = [
                        d[0]
                        for d in connection.execute(
                            "SELECT * FROM baseline_manifests"
                        ).description
                    ]
                    values = list(row)
                    idx = columns.index(
                        "created_ingest_timestamp_us"
                    )
                    values[idx] = malformed
                    id_idx = columns.index(
                        "baseline_manifest_id"
                    )
                    digest_idx = columns.index(
                        "baseline_manifest_digest"
                    )
                    values[id_idx] = "blm_v1_" + ("f" * 64)
                    values[digest_idx] = "f" * 64
                    placeholders = ", ".join(
                        "?" for _ in columns
                    )
                    connection.execute(
                        f"""
                        INSERT INTO baseline_manifests (
                            {', '.join(columns)}
                        ) VALUES ({placeholders})
                        """,
                        values,
                    )
                    connection.commit()

                reopened = BaselineStore(path)
                self.addCleanup(reopened.close)
                self.assertEqual(
                    reopened.get_baseline_manifest(
                        manifest.baseline_manifest_id
                    ),
                    manifest,
                )
                with self.assertRaises(ValueError):
                    reopened.get_baseline_manifest(
                        "blm_v1_" + ("f" * 64)
                    )
                with self.assertRaises(ValueError):
                    reopened.list_baseline_manifests()

    def test_str_subclass_id_rejected(self):
        store, _ = self.open_store()

        class MyStr(str):
            pass

        subclass_id = MyStr("blm_v1_" + ("0" * 64))
        with self.assertRaises(ValueError):
            store.get_baseline_manifest(subclass_id)
        with self.assertRaises(ValueError):
            store.get_baseline_result(subclass_id)
        with self.assertRaises(ValueError):
            store.get_baseline_result_for_manifest(subclass_id)

    # ── Parent-consistency rules ──────────────────────────────────────

    def _store_manifest_and_result(self):
        store, path = self.open_store()
        manifest = make_manifest(
            input_reference_digests=(HEX_A, HEX_B),
            minimum_sample_count=2,
        )
        self.assertEqual(
            store.insert_baseline_manifest(manifest),
            "inserted",
        )
        result = make_result(manifest=manifest)
        return store, path, manifest, result

    def test_result_manifest_id_mismatch_rejected(self):
        store, path, manifest, result = (
            self._store_manifest_and_result()
        )
        modified = copy.copy(result)
        object.__setattr__(
            modified,
            "manifest_id",
            "blm_v1_" + ("0" * 64),
        )
        object.__setattr__(
            modified,
            "manifest_digest",
            "0" * 64,
        )
        with self.assertRaises(ValueError):
            store.insert_baseline_result(modified)
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM baseline_results"
                ).fetchone()[0],
                0,
            )

    def test_result_manifest_digest_mismatch_rejected(self):
        store, path, manifest, result = (
            self._store_manifest_and_result()
        )
        modified = copy.copy(result)
        object.__setattr__(
            modified,
            "manifest_digest",
            "f" * 64,
        )
        with self.assertRaises(ValueError):
            store.insert_baseline_result(modified)
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM baseline_results"
                ).fetchone()[0],
                0,
            )

    def test_result_analysis_type_mismatch_rejected(self):
        store, path, manifest, result = (
            self._store_manifest_and_result()
        )
        modified = copy.copy(result)
        object.__setattr__(
            modified,
            "analysis_type",
            "different.type",
        )
        with self.assertRaises(ValueError):
            store.insert_baseline_result(modified)

    def test_result_analysis_version_mismatch_rejected(self):
        store, path, manifest, result = (
            self._store_manifest_and_result()
        )
        modified = copy.copy(result)
        object.__setattr__(
            modified,
            "analysis_version",
            "9.9.9",
        )
        with self.assertRaises(ValueError):
            store.insert_baseline_result(modified)

    def test_result_baseline_method_mismatch_rejected(self):
        store, path, manifest, result = (
            self._store_manifest_and_result()
        )
        modified = copy.copy(result)
        object.__setattr__(
            modified,
            "baseline_method",
            "different.method",
        )
        with self.assertRaises(ValueError):
            store.insert_baseline_result(modified)

    def test_result_baseline_version_mismatch_rejected(self):
        store, path, manifest, result = (
            self._store_manifest_and_result()
        )
        modified = copy.copy(result)
        object.__setattr__(
            modified,
            "baseline_version",
            "9.9.9",
        )
        with self.assertRaises(ValueError):
            store.insert_baseline_result(modified)

    def test_result_sample_count_mismatch_rejected(self):
        store, path, manifest, result = (
            self._store_manifest_and_result()
        )
        modified = copy.copy(result)
        object.__setattr__(modified, "sample_count", 99)
        with self.assertRaises(ValueError):
            store.insert_baseline_result(modified)

    def test_result_minimum_sample_count_mismatch_rejected(self):
        store, path, manifest, result = (
            self._store_manifest_and_result()
        )
        modified = copy.copy(result)
        object.__setattr__(
            modified,
            "minimum_sample_count",
            99,
        )
        with self.assertRaises(ValueError):
            store.insert_baseline_result(modified)

    def test_result_baseline_status_mismatch_rejected(self):
        store, path, manifest, result = (
            self._store_manifest_and_result()
        )
        modified = copy.copy(result)
        object.__setattr__(
            modified,
            "baseline_status",
            "unknown",
        )
        object.__setattr__(
            modified,
            "status_reason_code",
            "baseline.no_samples",
        )
        object.__setattr__(modified, "minimum_count", None)
        object.__setattr__(modified, "maximum_count", None)
        object.__setattr__(
            modified,
            "count_mean_numerator",
            None,
        )
        object.__setattr__(
            modified,
            "count_mean_denominator",
            None,
        )
        with self.assertRaises(ValueError):
            store.insert_baseline_result(modified)

    def test_result_status_reason_code_mismatch_rejected(self):
        store, path, manifest, result = (
            self._store_manifest_and_result()
        )
        modified = copy.copy(result)
        object.__setattr__(
            modified,
            "status_reason_code",
            "different.reason",
        )
        with self.assertRaises(ValueError):
            store.insert_baseline_result(modified)

    def test_result_sample_digest_sequence_mismatch_rejected(self):
        store, path, manifest, result = (
            self._store_manifest_and_result()
        )
        modified = copy.copy(result)
        object.__setattr__(
            modified,
            "samples",
            (
                make_sample(HEX_C, 5),
                make_sample(HEX_D, 10),
            ),
        )
        with self.assertRaises(ValueError):
            store.insert_baseline_result(modified)

    # ── Second different result identity for one manifest ─────────────

    def test_second_different_result_identity_for_manifest_conflict(self):
        store, path, manifest, result = (
            self._store_manifest_and_result()
        )
        self.assertEqual(
            store.insert_baseline_result(result),
            "inserted",
        )

        # Construct a result with a different result_id/digest
        # but same manifest_id.
        different = copy.copy(result)
        object.__setattr__(
            different,
            "baseline_result_id",
            "blr_v1_" + ("f" * 64),
        )
        object.__setattr__(
            different,
            "baseline_result_digest",
            "f" * 64,
        )
        self.assertEqual(
            store.insert_baseline_result(different),
            "identity_conflict",
        )
        self.assertEqual(
            store.get_baseline_result(result.baseline_result_id),
            result,
        )
        self.assertIsNone(
            store.get_baseline_result("blr_v1_" + ("f" * 64)),
        )
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM baseline_results"
                ).fetchone()[0],
                1,
            )

    # ── UPDATE and DELETE trigger enforcement ─────────────────────────

    def test_update_trigger_enforcement(self):
        store, path = self.open_store()
        manifest = make_manifest()
        self.assertEqual(
            store.insert_baseline_manifest(manifest),
            "inserted",
        )
        result = make_result(manifest=manifest)
        self.assertEqual(
            store.insert_baseline_result(result),
            "inserted",
        )
        store.close()

        with closing(sqlite3.connect(path)) as connection:
            for table, id_col, id_val, col in (
                ("baseline_manifests", "baseline_manifest_id",
                 manifest.baseline_manifest_id, "analysis_type"),
                ("baseline_results", "baseline_result_id",
                 result.baseline_result_id, "baseline_status"),
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

    def test_delete_trigger_enforcement(self):
        store, path = self.open_store()
        manifest = make_manifest()
        self.assertEqual(
            store.insert_baseline_manifest(manifest),
            "inserted",
        )
        result = make_result(manifest=manifest)
        self.assertEqual(
            store.insert_baseline_result(result),
            "inserted",
        )
        store.close()

        with closing(sqlite3.connect(path)) as connection:
            for table, id_col, id_val in (
                ("baseline_manifests", "baseline_manifest_id",
                 manifest.baseline_manifest_id),
                ("baseline_results", "baseline_result_id",
                 result.baseline_result_id),
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

    # ── Failed insert rollback ────────────────────────────────────────

    def test_failed_result_insert_rolls_back_completely(self):
        store, path = self.open_store()
        manifest = make_manifest()
        self.assertEqual(
            store.insert_baseline_manifest(manifest),
            "inserted",
        )
        orphan_manifest = make_manifest(
            hmac_key=HMAC_KEY_B,
            subject_reference=HEX_D,
        )
        orphan_result = make_result(
            hmac_key=HMAC_KEY_B,
            manifest=orphan_manifest,
        )
        with self.assertRaises(ValueError):
            store.insert_baseline_result(orphan_result)

        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM baseline_results"
                ).fetchone()[0],
                0,
            )

    # ── Wrong object types and subclasses ─────────────────────────────

    def test_wrong_object_types_rejected(self):
        store, _ = self.open_store()
        fake_manifest = types.SimpleNamespace(
            baseline_manifest_id="blm_v1_" + ("0" * 64),
        )
        fake_result = types.SimpleNamespace(
            baseline_result_id="blr_v1_" + ("0" * 64),
        )
        with self.assertRaises(ValueError):
            store.insert_baseline_manifest(fake_manifest)
        with self.assertRaises(ValueError):
            store.insert_baseline_result(fake_result)

    def test_manifest_subclass_rejected(self):
        store, _ = self.open_store()

        class MyManifest(BaselineManifestV1):
            pass

        valid = make_manifest()
        subclass = MyManifest(**valid.__dict__)
        with self.assertRaises(ValueError):
            store.insert_baseline_manifest(subclass)

    def test_result_subclass_rejected(self):
        store, _ = self.open_store()

        class MyResult(BaselineResultV1):
            pass

        manifest = make_manifest()
        store.insert_baseline_manifest(manifest)
        valid = make_result(manifest=manifest)
        subclass = MyResult(**valid.__dict__)
        with self.assertRaises(ValueError):
            store.insert_baseline_result(subclass)

    # ── Invalid IDs ───────────────────────────────────────────────────

    def test_invalid_ids_rejected(self):
        store, _ = self.open_store()

        class MyStr(str):
            pass

        invalid_values = ("", "   ", 123, True, None, MyStr("valid_id"))

        for value in invalid_values:
            with self.subTest(method="get_manifest", value=value):
                with self.assertRaises(ValueError):
                    store.get_baseline_manifest(value)
            with self.subTest(method="get_result", value=value):
                with self.assertRaises(ValueError):
                    store.get_baseline_result(value)
            with self.subTest(
                method="get_result_for_manifest", value=value
            ):
                with self.assertRaises(ValueError):
                    store.get_baseline_result_for_manifest(value)

    # ── Missing IDs return None ───────────────────────────────────────

    def test_missing_ids_return_none(self):
        store, _ = self.open_store()
        missing_manifest_id = "blm_v1_" + ("0" * 64)
        missing_result_id = "blr_v1_" + ("0" * 64)

        self.assertIsNone(
            store.get_baseline_manifest(missing_manifest_id)
        )
        self.assertIsNone(
            store.get_baseline_result(missing_result_id)
        )
        self.assertIsNone(
            store.get_baseline_result_for_manifest(
                missing_manifest_id
            )
        )

    # ── Deterministic ordering ────────────────────────────────────────

    def test_manifest_list_deterministic_order_reverse_insertion(self):
        store, _ = self.open_store()
        m1 = make_manifest(
            window_start=1_000_000,
            window_end=2_000_000,
            input_reference_digests=(HEX_A,),
            minimum_sample_count=1,
        )
        m2 = make_manifest(
            window_start=1_000_000,
            window_end=2_000_000,
            input_reference_digests=(HEX_B,),
            minimum_sample_count=1,
        )
        m3 = make_manifest(
            window_start=500_000,
            window_end=600_000,
            input_reference_digests=(HEX_C,),
            minimum_sample_count=1,
        )

        for m in (m3, m2, m1):
            self.assertEqual(
                store.insert_baseline_manifest(m),
                "inserted",
            )

        expected = tuple(
            sorted(
                (m1, m2, m3),
                key=lambda m: (
                    m.window_start_source_timestamp_us,
                    m.window_end_source_timestamp_us,
                    m.baseline_manifest_id,
                ),
            )
        )
        self.assertEqual(
            store.list_baseline_manifests(),
            expected,
        )

    def test_result_list_deterministic_order_reverse_insertion(self):
        store, _ = self.open_store()

        m_early = make_manifest(
            window_start=500_000,
            window_end=600_000,
            input_reference_digests=(HEX_C,),
            minimum_sample_count=1,
        )
        m_late = make_manifest(
            window_start=1_000_000,
            window_end=2_000_000,
            input_reference_digests=(HEX_A,),
            minimum_sample_count=1,
        )

        r_early = make_result(manifest=m_early)
        r_late = make_result(manifest=m_late)

        for m in (m_late, m_early):
            self.assertEqual(
                store.insert_baseline_manifest(m),
                "inserted",
            )
        for r in (r_late, r_early):
            self.assertEqual(
                store.insert_baseline_result(r),
                "inserted",
            )

        expected = (r_early, r_late)
        self.assertEqual(
            store.list_baseline_results(),
            expected,
        )

    def test_list_empty_returns_empty_tuple(self):
        store, _ = self.open_store()
        self.assertEqual(store.list_baseline_manifests(), ())
        self.assertEqual(store.list_baseline_results(), ())

    # ── Closing and use-after-close ───────────────────────────────────

    def test_close_is_idempotent(self):
        store, _ = self.open_store()
        store.close()
        store.close()

    def test_use_after_close_raises_runtime_error(self):
        store, _ = self.open_store()
        manifest = make_manifest()
        store.insert_baseline_manifest(manifest)
        store.close()

        with self.assertRaises(RuntimeError):
            store.insert_baseline_manifest(manifest)
        with self.assertRaises(RuntimeError):
            store.get_baseline_manifest(manifest.baseline_manifest_id)
        with self.assertRaises(RuntimeError):
            store.list_baseline_manifests()
        with self.assertRaises(RuntimeError):
            store.insert_baseline_result(make_result(manifest=manifest))
        with self.assertRaises(RuntimeError):
            store.get_baseline_result("blr_v1_" + ("0" * 64))
        with self.assertRaises(RuntimeError):
            store.get_baseline_result_for_manifest(
                manifest.baseline_manifest_id
            )
        with self.assertRaises(RuntimeError):
            store.list_baseline_results()

    def test_context_manager_closes_connection(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "ctx.sqlite"
            with BaselineStore(path) as store:
                self.assertIsInstance(store, BaselineStore)
                store.insert_baseline_manifest(make_manifest())
            with self.assertRaises(RuntimeError):
                store.list_baseline_manifests()

    def test_construction_failure_closes_connection(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "bad.sqlite"
            self.create_valid_schema(path)

            with closing(sqlite3.connect(path)) as connection:
                connection.execute("PRAGMA user_version = 99")
                connection.commit()

            with self.assertRaises(ValueError):
                BaselineStore(path)

    # ── Schema rejection without mutation ─────────────────────────────

    def test_unexpected_user_version_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "bad_version.sqlite"
            self.create_valid_schema(path)

            with closing(sqlite3.connect(path)) as connection:
                connection.execute("PRAGMA user_version = 2")
                connection.commit()

            before = self.schema_snapshot(path)
            with self.assertRaises(ValueError):
                BaselineStore(path)
            self.assertEqual(self.schema_snapshot(path), before)

    def test_unexpected_metadata_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "bad_meta.sqlite"
            self.create_valid_schema(path)

            with closing(sqlite3.connect(path)) as connection:
                connection.execute(
                    """
                    UPDATE store_metadata
                    SET initialized_at_us = 123
                    WHERE singleton = 1
                    """
                )
                connection.commit()

            before = self.schema_snapshot(path)
            with self.assertRaises(ValueError):
                BaselineStore(path)
            self.assertEqual(self.schema_snapshot(path), before)

    def test_extra_table_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "extra_table.sqlite"
            self.create_valid_schema(path)

            with closing(sqlite3.connect(path)) as connection:
                connection.execute(
                    "CREATE TABLE extra_table (id INTEGER)"
                )
                connection.commit()

            before = self.schema_snapshot(path)
            with self.assertRaises(ValueError):
                BaselineStore(path)
            self.assertEqual(self.schema_snapshot(path), before)

    def test_missing_table_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "missing_table.sqlite"
            self.create_valid_schema(path)

            with closing(sqlite3.connect(path)) as connection:
                connection.execute(
                    "DROP TRIGGER baseline_results_no_update"
                )
                connection.execute(
                    "DROP TRIGGER baseline_results_no_delete"
                )
                connection.execute("DROP TABLE baseline_results")
                connection.commit()

            before = self.schema_snapshot(path)
            with self.assertRaises(ValueError):
                BaselineStore(path)
            self.assertEqual(self.schema_snapshot(path), before)

    def test_changed_table_ddl_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "changed_ddl.sqlite"
            self.create_valid_schema(path)

            with closing(sqlite3.connect(path)) as connection:
                connection.execute("DROP TABLE baseline_manifests")
                connection.execute(
                    """
                    CREATE TABLE baseline_manifests (
                        baseline_manifest_id TEXT NOT NULL PRIMARY KEY,
                        schema_version TEXT NOT NULL,
                        record_kind TEXT NOT NULL,
                        baseline_manifest_digest TEXT NOT NULL,
                        analysis_type TEXT NOT NULL,
                        analysis_version TEXT NOT NULL,
                        baseline_method TEXT NOT NULL,
                        baseline_version TEXT NOT NULL,
                        subject_kind TEXT NOT NULL,
                        subject_reference INTEGER NOT NULL,
                        window_start_source_timestamp_us INTEGER NOT NULL,
                        window_end_source_timestamp_us INTEGER NOT NULL,
                        time_basis TEXT NOT NULL,
                        boundary_policy TEXT NOT NULL,
                        input_reference_digests TEXT NOT NULL,
                        sample_count INTEGER NOT NULL,
                        minimum_sample_count INTEGER NOT NULL,
                        baseline_status TEXT NOT NULL,
                        status_reason_code TEXT NOT NULL,
                        created_ingest_timestamp_us INTEGER NOT NULL,
                        analyzer_name TEXT NOT NULL,
                        analyzer_version TEXT NOT NULL,
                        analysis_mode TEXT NOT NULL,
                        source_contract_version TEXT NOT NULL
                    )
                    """
                )
                connection.commit()

            before = self.schema_snapshot(path)
            with self.assertRaises(ValueError):
                BaselineStore(path)
            self.assertEqual(self.schema_snapshot(path), before)

    def test_extra_trigger_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "extra_trigger.sqlite"
            self.create_valid_schema(path)

            with closing(sqlite3.connect(path)) as connection:
                connection.execute(
                    """
                    CREATE TRIGGER extra_trigger
                    BEFORE INSERT ON baseline_manifests
                    BEGIN
                        SELECT RAISE(ABORT, 'extra');
                    END
                    """
                )
                connection.commit()

            before = self.schema_snapshot(path)
            with self.assertRaises(ValueError):
                BaselineStore(path)
            self.assertEqual(self.schema_snapshot(path), before)

    def test_missing_trigger_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "missing_trigger.sqlite"
            self.create_valid_schema(path)

            with closing(sqlite3.connect(path)) as connection:
                connection.execute(
                    "DROP TRIGGER baseline_manifests_no_update"
                )
                connection.commit()

            before = self.schema_snapshot(path)
            with self.assertRaises(ValueError):
                BaselineStore(path)
            self.assertEqual(self.schema_snapshot(path), before)

    def test_changed_trigger_body_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "changed_trigger.sqlite"
            self.create_valid_schema(path)

            with closing(sqlite3.connect(path)) as connection:
                connection.execute(
                    "DROP TRIGGER baseline_manifests_no_update"
                )
                connection.execute(
                    """
                    CREATE TRIGGER baseline_manifests_no_update
                    BEFORE UPDATE ON baseline_manifests
                    WHEN 0
                    BEGIN
                        SELECT RAISE(ABORT, 'baseline_manifests is immutable');
                    END
                    """
                )
                connection.commit()

            before = self.schema_snapshot(path)
            with self.assertRaises(ValueError):
                BaselineStore(path)
            self.assertEqual(self.schema_snapshot(path), before)
            self.assertIn(
                "WHEN 0",
                self.trigger_sql(
                    path, "baseline_manifests_no_update"
                ),
            )

    def test_foreign_key_violation_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "fk_violation.sqlite"
            self.create_valid_schema(path)

            zero = "0" * 64
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("PRAGMA foreign_keys = OFF")
                connection.execute(
                    """
                    INSERT INTO baseline_results (
                        baseline_result_id, schema_version,
                        record_kind, baseline_result_digest,
                        analysis_type, analysis_version,
                        baseline_method, baseline_version,
                        manifest_id, manifest_digest,
                        samples, sample_count,
                        minimum_sample_count,
                        baseline_status, status_reason_code,
                        minimum_count, maximum_count,
                        count_mean_numerator,
                        count_mean_denominator,
                        created_ingest_timestamp_us,
                        analyzer_name, analyzer_version,
                        analysis_mode, source_contract_version
                    ) VALUES (
                        ?, '1.0', 'baseline_result', ?,
                        'observation.count_per_collection_session',
                        '1.0.0',
                        'count_mean_range', '1.0.0',
                        ?, ?,
                        '[]', '0', '1',
                        'unknown', 'baseline.no_samples',
                        NULL, NULL, NULL, NULL,
                        '0',
                        'a', '1.0.0', 'synthetic', '1.0'
                    )
                    """,
                    (
                        "blr_v1_" + zero,
                        zero,
                        "blm_v1_" + zero,
                        zero,
                    ),
                )
                connection.commit()

            before = self.schema_snapshot(path)
            with self.assertRaises(ValueError):
                BaselineStore(path)
            self.assertEqual(self.schema_snapshot(path), before)

    # ── Clean shutdown without ResourceWarning ────────────────────────

    def test_clean_shutdown_no_resourcewarning(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", ResourceWarning)
            with tempfile.TemporaryDirectory() as tempdir:
                path = Path(tempdir) / "clean.sqlite"
                with BaselineStore(path) as store:
                    self.assertIsInstance(store, BaselineStore)
                del store
                gc.collect()

    # ── No public raw connection API ──────────────────────────────────

    def test_no_public_raw_connection_api(self):
        store, _ = self.open_store()
        with self.assertRaises(AttributeError):
            _ = store.connection

    # ── Exported API ──────────────────────────────────────────────────

    def test_all_contains_exactly_baseline_store(self):
        self.assertEqual(STORE_ALL, ["BaselineStore"])

    def test_all_entries_present(self):
        for name in STORE_ALL:
            self.assertIn(
                name,
                dir(sys.modules["baseline_store"]),
            )


# ── AST prohibitions ─────────────────────────────────────────────────────


class TestASTProhibitions(unittest.TestCase):

    def _load_source(self):
        with open("baseline_store.py") as f:
            return ast.parse(f.read())

    def test_no_forbidden_imports(self):
        tree = self._load_source()
        forbidden = {
            "tkinter",
            "subprocess",
            "smtplib",
            "http",
            "urllib",
            "socket",
            "logging",
            "threading",
            "multiprocessing",
            "os",
            "sys",
            "random",
            "statistics",
            "datetime",
            "time",
            "math",
            "alert_store",
            "alert_contract",
            "alert_projection",
            "surveillance_detector",
            "surveillance_analyzer",
            "observation_store",
            "observation_contract",
            "observation_location_link_orchestrator",
            "observation_location_link_writer",
            "observation_correlation_planner",
            "route_session_contract",
            "gps_tracker",
            "bounded_gps_correlator",
            "kismet_eventbus_new_device_adapter",
            "kismet_eventbus_transport",
            "kismet_packet_adapter",
            "kismet_db_selection",
            "ground_truth_scenario_contract",
            "ground_truth_summary_builder",
            "synthetic_jsonl_adapter",
            "synthetic_operator_fix_jsonl_adapter",
            "secure_credentials",
            "secure_database",
            "secure_ignore_loader",
            "secure_main_logic",
            "input_validation",
            "chasing_your_tail",
            "cyt_gui",
            "probe_analyzer",
            "ignore_list",
            "ignore_list_ssid",
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in forbidden:
                        self.fail(f"forbidden import: {alias.name}")

            if isinstance(node, ast.ImportFrom):
                if node.module:
                    top = node.module.split(".")[0]
                    if top in forbidden:
                        self.fail(
                            f"forbidden import: {node.module}"
                        )

    def test_no_forbidden_calls(self):
        tree = self._load_source()

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            if isinstance(node.func, ast.Name):
                name = node.func.id
                if name in {"print", "eval", "exec"}:
                    self.fail(f"forbidden call: {name}")

                if name == "open":
                    for kw in node.keywords:
                        if kw.arg == "mode":
                            try:
                                mode = ast.literal_eval(kw.value)
                            except Exception:
                                continue
                            if isinstance(mode, str) and "w" in mode:
                                self.fail("forbidden open for write")

    def test_no_wall_clock_or_time_access(self):
        tree = self._load_source()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    attr = node.func.attr
                    if attr in {
                        "time", "sleep", "gmtime", "localtime",
                        "strftime", "now", "utcnow", "today",
                        "fromtimestamp", "utcfromtimestamp",
                    }:
                        self.fail(f"time access call: {attr}")

    def test_no_forbidden_field_or_variable_names(self):
        tree = self._load_source()
        forbidden = {
            "raw_mac",
            "ssid",
            "latitude",
            "longitude",
            "coordinates",
            "packets",
            "signal",
            "channel",
            "payload",
            "device_name",
            "description",
            "narrative",
            "location_label",
            "probability",
            "confidence",
            "accuracy",
            "threat",
            "stalking",
            "surveillance",
            "following",
            "intent",
            "score",
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name):
                    if node.target.id in forbidden:
                        self.fail(
                            f"forbidden field: {node.target.id}"
                        )

            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if target.id in forbidden:
                            self.fail(
                                f"forbidden name: {target.id}"
                            )

    def test_no_float_literals_or_casts(self):
        tree = self._load_source()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant):
                if isinstance(node.value, float):
                    self.fail(f"float literal: {node.value}")
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and (
                    node.func.id == "float"
                ):
                    self.fail("float() call")
                if isinstance(node.func, ast.Attribute) and (
                    node.func.attr == "float"
                ):
                    self.fail("float() call via attr")

    def test_no_side_effect_statements(self):
        tree = self._load_source()
        for node in ast.walk(tree):
            if isinstance(node, ast.Delete):
                self.fail("del statement forbidden")


if __name__ == "__main__":
    unittest.main()
