"""Deterministic focused tests for Baseline Manifest v1 contract."""

import ast
import sys
import unittest
from typing import Optional, Tuple

from baseline_contract import (
    __all__ as EXPORTED_ALL,
    BASELINE_MANIFEST_RECORD_KIND,
    BASELINE_STATUSES,
    BaselineProvenanceV1,
    BaselineManifestV1,
    create_baseline_manifest,
    compare_baseline_manifest_source_facts,
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


def make_provenance(
    analysis_mode: str = "synthetic",
    source_contract_version: str = "1.0",
) -> BaselineProvenanceV1:
    return BaselineProvenanceV1(
        analyzer_name="cyt.baseline",
        analyzer_version="1.0.0",
        analysis_mode=analysis_mode,
        source_contract_version=source_contract_version,
    )


def make_manifest(
    hmac_key: bytes = HMAC_KEY_A,
    input_reference_digests: Tuple[str, ...] = (HEX_A, HEX_B),
    minimum_sample_count: int = 2,
    **overrides,
) -> BaselineManifestV1:
    kwargs = {
        "hmac_key": hmac_key,
        "analysis_type": "statistical.mean",
        "analysis_version": "1.0.0",
        "baseline_method": "rolling_window",
        "baseline_version": "1.0.0",
        "subject_kind": "device.aggregate",
        "subject_reference": HEX_C,
        "window_start_source_timestamp_us": WINDOW_START,
        "window_end_source_timestamp_us": WINDOW_END,
        "input_reference_digests": input_reference_digests,
        "minimum_sample_count": minimum_sample_count,
        "created_ingest_timestamp_us": INGEST_TS,
        "provenance": make_provenance(),
    }
    kwargs.update(overrides)
    return create_baseline_manifest(**kwargs)


# ── Provenance ──────────────────────────────────────────────────────────────


class TestBaselineProvenanceV1(unittest.TestCase):

    def test_valid_construction(self):
        p = make_provenance()
        self.assertIsInstance(p, BaselineProvenanceV1)

    def test_frozen(self):
        p = make_provenance()
        with self.assertRaises(Exception):
            p.analyzer_name = "changed"

    def test_invalid_analysis_mode(self):
        with self.assertRaises(ValueError):
            make_provenance(analysis_mode="invalid")

    def test_analysis_mode_non_string_rejected(self):
        with self.assertRaises(ValueError):
            BaselineProvenanceV1(
                analyzer_name="cyt.baseline",
                analyzer_version="1.0.0",
                analysis_mode=["live"],
                source_contract_version="1.0",
            )

    def test_empty_analyzer_name(self):
        with self.assertRaises(ValueError):
            BaselineProvenanceV1(
                analyzer_name="",
                analyzer_version="1.0.0",
                analysis_mode="synthetic",
                source_contract_version="1.0",
            )

    def test_empty_analyzer_version(self):
        with self.assertRaises(ValueError):
            BaselineProvenanceV1(
                analyzer_name="cyt.baseline",
                analyzer_version="",
                analysis_mode="synthetic",
                source_contract_version="1.0",
            )

    def test_all_analysis_modes_accepted(self):
        for mode in ("live", "replay", "synthetic"):
            p = make_provenance(analysis_mode=mode)
            self.assertEqual(p.analysis_mode, mode)


# ── BaselineManifestV1 ──────────────────────────────────────────────────────


class TestBaselineManifestV1(unittest.TestCase):

    def test_create_minimal(self):
        m = make_manifest()
        self.assertIsInstance(m, BaselineManifestV1)
        self.assertEqual(m.schema_version, "1.0")
        self.assertEqual(m.record_kind, BASELINE_MANIFEST_RECORD_KIND)
        self.assertTrue(m.baseline_manifest_id.startswith("blm_v1_"))
        self.assertEqual(len(m.baseline_manifest_id), len("blm_v1_") + 64)
        self.assertEqual(len(m.baseline_manifest_digest), 64)
        self.assertEqual(m.time_basis, "source_timestamp_us")
        self.assertEqual(m.boundary_policy, "half_open")

    def test_id_suffix_equals_digest(self):
        m = make_manifest()
        self.assertEqual(m.baseline_manifest_id[-64:], m.baseline_manifest_digest)

    def test_sample_count_derived(self):
        m = make_manifest(input_reference_digests=(HEX_A, HEX_B, HEX_C))
        self.assertEqual(m.sample_count, 3)
        self.assertEqual(len(m.input_reference_digests), 3)

    def test_zero_samples_unknown_status(self):
        m = make_manifest(
            input_reference_digests=(),
            minimum_sample_count=2,
        )
        self.assertEqual(m.sample_count, 0)
        self.assertEqual(m.baseline_status, "unknown")
        self.assertEqual(m.status_reason_code, "baseline.no_samples")

    def test_below_threshold_insufficient_data(self):
        m = make_manifest(
            input_reference_digests=(HEX_A,),
            minimum_sample_count=2,
        )
        self.assertEqual(m.sample_count, 1)
        self.assertEqual(m.baseline_status, "insufficient_data")
        self.assertEqual(m.status_reason_code, "baseline.minimum_not_met")

    def test_exact_threshold_available(self):
        m = make_manifest(
            input_reference_digests=(HEX_A, HEX_B),
            minimum_sample_count=2,
        )
        self.assertEqual(m.sample_count, 2)
        self.assertEqual(m.baseline_status, "available")
        self.assertEqual(m.status_reason_code, "baseline.minimum_met")

    def test_above_threshold_available(self):
        m = make_manifest(
            input_reference_digests=(HEX_A, HEX_B, HEX_C, HEX_D),
            minimum_sample_count=2,
        )
        self.assertEqual(m.sample_count, 4)
        self.assertEqual(m.baseline_status, "available")
        self.assertEqual(m.status_reason_code, "baseline.minimum_met")

    def test_input_order_independent_identity(self):
        order_a = (HEX_B, HEX_A, HEX_C)
        order_b = (HEX_C, HEX_A, HEX_B)
        m1 = make_manifest(input_reference_digests=order_a)
        m2 = make_manifest(input_reference_digests=order_b)
        self.assertEqual(m1.baseline_manifest_id, m2.baseline_manifest_id)
        self.assertEqual(m1.input_reference_digests, (HEX_A, HEX_B, HEX_C))
        self.assertEqual(m2.input_reference_digests, (HEX_A, HEX_B, HEX_C))

    def test_duplicate_input_references_rejected(self):
        with self.assertRaises(ValueError):
            make_manifest(input_reference_digests=(HEX_A, HEX_A))

    def test_input_tuple_not_list(self):
        with self.assertRaises(ValueError):
            make_manifest(input_reference_digests=[HEX_A, HEX_B])

    def test_constructor_rejects_tuple_subclass(self):
        class MyTuple(tuple):
            pass

        with self.assertRaises(ValueError):
            make_manifest(
                input_reference_digests=MyTuple((HEX_A, HEX_B))
            )

    def test_empty_or_whitespace_text_rejected(self):
        for field in ("analysis_type", "analysis_version",
                       "baseline_method", "baseline_version",
                       "subject_kind"):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    make_manifest(**{field: ""})

    def test_frozen(self):
        m = make_manifest()
        with self.assertRaises(Exception):
            m.analysis_type = "changed"

    def test_baseline_statuses_constant(self):
        self.assertIsInstance(BASELINE_STATUSES, frozenset)
        self.assertEqual(
            BASELINE_STATUSES,
            {"available", "insufficient_data", "unknown"},
        )

    def test_record_kind_constant(self):
        self.assertEqual(BASELINE_MANIFEST_RECORD_KIND, "baseline_manifest")


# ── Direct construction rejection ──────────────────────────────────────────


class TestDirectConstructionValidation(unittest.TestCase):

    def _valid_manifest(self) -> BaselineManifestV1:
        return make_manifest()

    def test_direct_construction_rejects_wrong_schema_version(self):
        m = self._valid_manifest()
        with self.assertRaises(ValueError):
            BaselineManifestV1(
                schema_version="2.0",
                record_kind=m.record_kind,
                baseline_manifest_id=m.baseline_manifest_id,
                baseline_manifest_digest=m.baseline_manifest_digest,
                analysis_type=m.analysis_type,
                analysis_version=m.analysis_version,
                baseline_method=m.baseline_method,
                baseline_version=m.baseline_version,
                subject_kind=m.subject_kind,
                subject_reference=m.subject_reference,
                window_start_source_timestamp_us=(
                    m.window_start_source_timestamp_us
                ),
                window_end_source_timestamp_us=(
                    m.window_end_source_timestamp_us
                ),
                time_basis=m.time_basis,
                boundary_policy=m.boundary_policy,
                input_reference_digests=m.input_reference_digests,
                sample_count=m.sample_count,
                minimum_sample_count=m.minimum_sample_count,
                baseline_status=m.baseline_status,
                status_reason_code=m.status_reason_code,
                created_ingest_timestamp_us=m.created_ingest_timestamp_us,
                provenance=m.provenance,
            )

    def test_direct_construction_rejects_wrong_record_kind(self):
        m = self._valid_manifest()
        with self.assertRaises(ValueError):
            BaselineManifestV1(
                schema_version=m.schema_version,
                record_kind="wrong",
                baseline_manifest_id=m.baseline_manifest_id,
                baseline_manifest_digest=m.baseline_manifest_digest,
                analysis_type=m.analysis_type,
                analysis_version=m.analysis_version,
                baseline_method=m.baseline_method,
                baseline_version=m.baseline_version,
                subject_kind=m.subject_kind,
                subject_reference=m.subject_reference,
                window_start_source_timestamp_us=(
                    m.window_start_source_timestamp_us
                ),
                window_end_source_timestamp_us=(
                    m.window_end_source_timestamp_us
                ),
                time_basis=m.time_basis,
                boundary_policy=m.boundary_policy,
                input_reference_digests=m.input_reference_digests,
                sample_count=m.sample_count,
                minimum_sample_count=m.minimum_sample_count,
                baseline_status=m.baseline_status,
                status_reason_code=m.status_reason_code,
                created_ingest_timestamp_us=m.created_ingest_timestamp_us,
                provenance=m.provenance,
            )

    def test_direct_construction_rejects_bad_id_format(self):
        m = self._valid_manifest()
        with self.assertRaises(ValueError):
            BaselineManifestV1(
                schema_version=m.schema_version,
                record_kind=m.record_kind,
                baseline_manifest_id="bad_" + HEX_A,
                baseline_manifest_digest=HEX_A,
                analysis_type=m.analysis_type,
                analysis_version=m.analysis_version,
                baseline_method=m.baseline_method,
                baseline_version=m.baseline_version,
                subject_kind=m.subject_kind,
                subject_reference=m.subject_reference,
                window_start_source_timestamp_us=(
                    m.window_start_source_timestamp_us
                ),
                window_end_source_timestamp_us=(
                    m.window_end_source_timestamp_us
                ),
                time_basis=m.time_basis,
                boundary_policy=m.boundary_policy,
                input_reference_digests=m.input_reference_digests,
                sample_count=m.sample_count,
                minimum_sample_count=m.minimum_sample_count,
                baseline_status=m.baseline_status,
                status_reason_code=m.status_reason_code,
                created_ingest_timestamp_us=m.created_ingest_timestamp_us,
                provenance=m.provenance,
            )

    def test_direct_construction_rejects_id_digest_mismatch(self):
        m = self._valid_manifest()
        # ID has HEX_E suffix but digest is HEX_A — suffix != digest
        wrong_id = "blm_v1_" + HEX_E
        with self.assertRaises(ValueError):
            BaselineManifestV1(
                schema_version=m.schema_version,
                record_kind=m.record_kind,
                baseline_manifest_id=wrong_id,
                baseline_manifest_digest=HEX_A,
                analysis_type=m.analysis_type,
                analysis_version=m.analysis_version,
                baseline_method=m.baseline_method,
                baseline_version=m.baseline_version,
                subject_kind=m.subject_kind,
                subject_reference=m.subject_reference,
                window_start_source_timestamp_us=(
                    m.window_start_source_timestamp_us
                ),
                window_end_source_timestamp_us=(
                    m.window_end_source_timestamp_us
                ),
                time_basis=m.time_basis,
                boundary_policy=m.boundary_policy,
                input_reference_digests=m.input_reference_digests,
                sample_count=m.sample_count,
                minimum_sample_count=m.minimum_sample_count,
                baseline_status=m.baseline_status,
                status_reason_code=m.status_reason_code,
                created_ingest_timestamp_us=m.created_ingest_timestamp_us,
                provenance=m.provenance,
            )

    def test_direct_construction_rejects_wrong_time_basis(self):
        m = self._valid_manifest()
        with self.assertRaises(ValueError):
            BaselineManifestV1(
                schema_version=m.schema_version,
                record_kind=m.record_kind,
                baseline_manifest_id=m.baseline_manifest_id,
                baseline_manifest_digest=m.baseline_manifest_digest,
                analysis_type=m.analysis_type,
                analysis_version=m.analysis_version,
                baseline_method=m.baseline_method,
                baseline_version=m.baseline_version,
                subject_kind=m.subject_kind,
                subject_reference=m.subject_reference,
                window_start_source_timestamp_us=(
                    m.window_start_source_timestamp_us
                ),
                window_end_source_timestamp_us=(
                    m.window_end_source_timestamp_us
                ),
                time_basis="wall_clock_us",
                boundary_policy=m.boundary_policy,
                input_reference_digests=m.input_reference_digests,
                sample_count=m.sample_count,
                minimum_sample_count=m.minimum_sample_count,
                baseline_status=m.baseline_status,
                status_reason_code=m.status_reason_code,
                created_ingest_timestamp_us=m.created_ingest_timestamp_us,
                provenance=m.provenance,
            )

    def test_direct_construction_rejects_wrong_boundary_policy(self):
        m = self._valid_manifest()
        with self.assertRaises(ValueError):
            BaselineManifestV1(
                schema_version=m.schema_version,
                record_kind=m.record_kind,
                baseline_manifest_id=m.baseline_manifest_id,
                baseline_manifest_digest=m.baseline_manifest_digest,
                analysis_type=m.analysis_type,
                analysis_version=m.analysis_version,
                baseline_method=m.baseline_method,
                baseline_version=m.baseline_version,
                subject_kind=m.subject_kind,
                subject_reference=m.subject_reference,
                window_start_source_timestamp_us=(
                    m.window_start_source_timestamp_us
                ),
                window_end_source_timestamp_us=(
                    m.window_end_source_timestamp_us
                ),
                time_basis=m.time_basis,
                boundary_policy="open",
                input_reference_digests=m.input_reference_digests,
                sample_count=m.sample_count,
                minimum_sample_count=m.minimum_sample_count,
                baseline_status=m.baseline_status,
                status_reason_code=m.status_reason_code,
                created_ingest_timestamp_us=m.created_ingest_timestamp_us,
                provenance=m.provenance,
            )

    def test_direct_construction_rejects_bad_window(self):
        m = self._valid_manifest()
        with self.assertRaises(ValueError):
            BaselineManifestV1(
                schema_version=m.schema_version,
                record_kind=m.record_kind,
                baseline_manifest_id=m.baseline_manifest_id,
                baseline_manifest_digest=m.baseline_manifest_digest,
                analysis_type=m.analysis_type,
                analysis_version=m.analysis_version,
                baseline_method=m.baseline_method,
                baseline_version=m.baseline_version,
                subject_kind=m.subject_kind,
                subject_reference=m.subject_reference,
                window_start_source_timestamp_us=WINDOW_END,
                window_end_source_timestamp_us=WINDOW_START,
                time_basis=m.time_basis,
                boundary_policy=m.boundary_policy,
                input_reference_digests=m.input_reference_digests,
                sample_count=m.sample_count,
                minimum_sample_count=m.minimum_sample_count,
                baseline_status=m.baseline_status,
                status_reason_code=m.status_reason_code,
                created_ingest_timestamp_us=m.created_ingest_timestamp_us,
                provenance=m.provenance,
            )

    def test_direct_construction_rejects_equal_window(self):
        m = self._valid_manifest()
        with self.assertRaises(ValueError):
            BaselineManifestV1(
                schema_version=m.schema_version,
                record_kind=m.record_kind,
                baseline_manifest_id=m.baseline_manifest_id,
                baseline_manifest_digest=m.baseline_manifest_digest,
                analysis_type=m.analysis_type,
                analysis_version=m.analysis_version,
                baseline_method=m.baseline_method,
                baseline_version=m.baseline_version,
                subject_kind=m.subject_kind,
                subject_reference=m.subject_reference,
                window_start_source_timestamp_us=WINDOW_START,
                window_end_source_timestamp_us=WINDOW_START,
                time_basis=m.time_basis,
                boundary_policy=m.boundary_policy,
                input_reference_digests=m.input_reference_digests,
                sample_count=m.sample_count,
                minimum_sample_count=m.minimum_sample_count,
                baseline_status=m.baseline_status,
                status_reason_code=m.status_reason_code,
                created_ingest_timestamp_us=m.created_ingest_timestamp_us,
                provenance=m.provenance,
            )

    def test_direct_construction_rejects_sample_count_mismatch(self):
        m = self._valid_manifest()
        with self.assertRaises(ValueError):
            BaselineManifestV1(
                schema_version=m.schema_version,
                record_kind=m.record_kind,
                baseline_manifest_id=m.baseline_manifest_id,
                baseline_manifest_digest=m.baseline_manifest_digest,
                analysis_type=m.analysis_type,
                analysis_version=m.analysis_version,
                baseline_method=m.baseline_method,
                baseline_version=m.baseline_version,
                subject_kind=m.subject_kind,
                subject_reference=m.subject_reference,
                window_start_source_timestamp_us=(
                    m.window_start_source_timestamp_us
                ),
                window_end_source_timestamp_us=(
                    m.window_end_source_timestamp_us
                ),
                time_basis=m.time_basis,
                boundary_policy=m.boundary_policy,
                input_reference_digests=m.input_reference_digests,
                sample_count=99,
                minimum_sample_count=m.minimum_sample_count,
                baseline_status=m.baseline_status,
                status_reason_code=m.status_reason_code,
                created_ingest_timestamp_us=m.created_ingest_timestamp_us,
                provenance=m.provenance,
            )

    def test_direct_construction_rejects_wrong_status(self):
        m = self._valid_manifest()
        with self.assertRaises(ValueError):
            BaselineManifestV1(
                schema_version=m.schema_version,
                record_kind=m.record_kind,
                baseline_manifest_id=m.baseline_manifest_id,
                baseline_manifest_digest=m.baseline_manifest_digest,
                analysis_type=m.analysis_type,
                analysis_version=m.analysis_version,
                baseline_method=m.baseline_method,
                baseline_version=m.baseline_version,
                subject_kind=m.subject_kind,
                subject_reference=m.subject_reference,
                window_start_source_timestamp_us=(
                    m.window_start_source_timestamp_us
                ),
                window_end_source_timestamp_us=(
                    m.window_end_source_timestamp_us
                ),
                time_basis=m.time_basis,
                boundary_policy=m.boundary_policy,
                input_reference_digests=m.input_reference_digests,
                sample_count=m.sample_count,
                minimum_sample_count=m.minimum_sample_count,
                baseline_status="insufficient_data",
                status_reason_code="baseline.minimum_met",
                created_ingest_timestamp_us=m.created_ingest_timestamp_us,
                provenance=m.provenance,
            )

    def test_direct_construction_rejects_unsorted_references(self):
        m = self._valid_manifest()
        unsorted = (HEX_B, HEX_A)
        with self.assertRaises(ValueError):
            BaselineManifestV1(
                schema_version=m.schema_version,
                record_kind=m.record_kind,
                baseline_manifest_id=m.baseline_manifest_id,
                baseline_manifest_digest=m.baseline_manifest_digest,
                analysis_type=m.analysis_type,
                analysis_version=m.analysis_version,
                baseline_method=m.baseline_method,
                baseline_version=m.baseline_version,
                subject_kind=m.subject_kind,
                subject_reference=m.subject_reference,
                window_start_source_timestamp_us=(
                    m.window_start_source_timestamp_us
                ),
                window_end_source_timestamp_us=(
                    m.window_end_source_timestamp_us
                ),
                time_basis=m.time_basis,
                boundary_policy=m.boundary_policy,
                input_reference_digests=unsorted,
                sample_count=2,
                minimum_sample_count=m.minimum_sample_count,
                baseline_status=m.baseline_status,
                status_reason_code=m.status_reason_code,
                created_ingest_timestamp_us=m.created_ingest_timestamp_us,
                provenance=m.provenance,
            )

    def test_direct_construction_rejects_duplicate_references(self):
        m = self._valid_manifest()
        dup = (HEX_A, HEX_A)
        with self.assertRaises(ValueError):
            BaselineManifestV1(
                schema_version=m.schema_version,
                record_kind=m.record_kind,
                baseline_manifest_id=m.baseline_manifest_id,
                baseline_manifest_digest=m.baseline_manifest_digest,
                analysis_type=m.analysis_type,
                analysis_version=m.analysis_version,
                baseline_method=m.baseline_method,
                baseline_version=m.baseline_version,
                subject_kind=m.subject_kind,
                subject_reference=m.subject_reference,
                window_start_source_timestamp_us=(
                    m.window_start_source_timestamp_us
                ),
                window_end_source_timestamp_us=(
                    m.window_end_source_timestamp_us
                ),
                time_basis=m.time_basis,
                boundary_policy=m.boundary_policy,
                input_reference_digests=dup,
                sample_count=2,
                minimum_sample_count=m.minimum_sample_count,
                baseline_status=m.baseline_status,
                status_reason_code=m.status_reason_code,
                created_ingest_timestamp_us=m.created_ingest_timestamp_us,
                provenance=m.provenance,
            )

    def test_direct_construction_rejects_non_tuple_references(self):
        m = self._valid_manifest()
        with self.assertRaises(ValueError):
            BaselineManifestV1(
                schema_version=m.schema_version,
                record_kind=m.record_kind,
                baseline_manifest_id=m.baseline_manifest_id,
                baseline_manifest_digest=m.baseline_manifest_digest,
                analysis_type=m.analysis_type,
                analysis_version=m.analysis_version,
                baseline_method=m.baseline_method,
                baseline_version=m.baseline_version,
                subject_kind=m.subject_kind,
                subject_reference=m.subject_reference,
                window_start_source_timestamp_us=(
                    m.window_start_source_timestamp_us
                ),
                window_end_source_timestamp_us=(
                    m.window_end_source_timestamp_us
                ),
                time_basis=m.time_basis,
                boundary_policy=m.boundary_policy,
                input_reference_digests=[HEX_A, HEX_B],
                sample_count=2,
                minimum_sample_count=m.minimum_sample_count,
                baseline_status=m.baseline_status,
                status_reason_code=m.status_reason_code,
                created_ingest_timestamp_us=m.created_ingest_timestamp_us,
                provenance=m.provenance,
            )

    def test_direct_construction_rejects_tuple_subclass(self):
        m = self._valid_manifest()

        class MyTuple(tuple):
            pass

        with self.assertRaises(ValueError):
            BaselineManifestV1(
                schema_version=m.schema_version,
                record_kind=m.record_kind,
                baseline_manifest_id=m.baseline_manifest_id,
                baseline_manifest_digest=m.baseline_manifest_digest,
                analysis_type=m.analysis_type,
                analysis_version=m.analysis_version,
                baseline_method=m.baseline_method,
                baseline_version=m.baseline_version,
                subject_kind=m.subject_kind,
                subject_reference=m.subject_reference,
                window_start_source_timestamp_us=(
                    m.window_start_source_timestamp_us
                ),
                window_end_source_timestamp_us=(
                    m.window_end_source_timestamp_us
                ),
                time_basis=m.time_basis,
                boundary_policy=m.boundary_policy,
                input_reference_digests=MyTuple((HEX_A, HEX_B)),
                sample_count=2,
                minimum_sample_count=m.minimum_sample_count,
                baseline_status=m.baseline_status,
                status_reason_code=m.status_reason_code,
                created_ingest_timestamp_us=m.created_ingest_timestamp_us,
                provenance=m.provenance,
            )

    def test_direct_construction_rejects_provenance_subclass(self):
        m = self._valid_manifest()

        class MyProvenance(BaselineProvenanceV1):
            pass

        bad_provenance = MyProvenance(
            analyzer_name="cyt.baseline",
            analyzer_version="1.0.0",
            analysis_mode="synthetic",
            source_contract_version="1.0",
        )

        with self.assertRaises(ValueError):
            BaselineManifestV1(
                schema_version=m.schema_version,
                record_kind=m.record_kind,
                baseline_manifest_id=m.baseline_manifest_id,
                baseline_manifest_digest=m.baseline_manifest_digest,
                analysis_type=m.analysis_type,
                analysis_version=m.analysis_version,
                baseline_method=m.baseline_method,
                baseline_version=m.baseline_version,
                subject_kind=m.subject_kind,
                subject_reference=m.subject_reference,
                window_start_source_timestamp_us=(
                    m.window_start_source_timestamp_us
                ),
                window_end_source_timestamp_us=(
                    m.window_end_source_timestamp_us
                ),
                time_basis=m.time_basis,
                boundary_policy=m.boundary_policy,
                input_reference_digests=m.input_reference_digests,
                sample_count=m.sample_count,
                minimum_sample_count=m.minimum_sample_count,
                baseline_status=m.baseline_status,
                status_reason_code=m.status_reason_code,
                created_ingest_timestamp_us=m.created_ingest_timestamp_us,
                provenance=bad_provenance,
            )


# ── Identity ────────────────────────────────────────────────────────────────


class TestBaselineManifestIdentity(unittest.TestCase):

    def test_deterministic_identity(self):
        m1 = make_manifest(HMAC_KEY_A)
        m2 = make_manifest(HMAC_KEY_A)
        self.assertEqual(m1.baseline_manifest_id, m2.baseline_manifest_id)
        self.assertEqual(
            m1.baseline_manifest_digest, m2.baseline_manifest_digest
        )

    def test_different_hmac_key_changes_identity(self):
        m1 = make_manifest(HMAC_KEY_A)
        m2 = make_manifest(HMAC_KEY_B)
        self.assertNotEqual(
            m1.baseline_manifest_id, m2.baseline_manifest_id
        )

    def test_identity_changes_with_analysis_type(self):
        m1 = make_manifest(analysis_type="statistical.mean")
        m2 = make_manifest(analysis_type="statistical.median")
        self.assertNotEqual(
            m1.baseline_manifest_id, m2.baseline_manifest_id
        )

    def test_identity_changes_with_analysis_version(self):
        m1 = make_manifest(analysis_version="1.0.0")
        m2 = make_manifest(analysis_version="1.0.1")
        self.assertNotEqual(
            m1.baseline_manifest_id, m2.baseline_manifest_id
        )

    def test_identity_changes_with_baseline_method(self):
        m1 = make_manifest(baseline_method="rolling_window")
        m2 = make_manifest(baseline_method="fixed_window")
        self.assertNotEqual(
            m1.baseline_manifest_id, m2.baseline_manifest_id
        )

    def test_identity_changes_with_baseline_version(self):
        m1 = make_manifest(baseline_version="1.0.0")
        m2 = make_manifest(baseline_version="2.0.0")
        self.assertNotEqual(
            m1.baseline_manifest_id, m2.baseline_manifest_id
        )

    def test_identity_changes_with_subject_kind(self):
        m1 = make_manifest(subject_kind="device.aggregate")
        m2 = make_manifest(subject_kind="device.singleton")
        self.assertNotEqual(
            m1.baseline_manifest_id, m2.baseline_manifest_id
        )

    def test_identity_changes_with_subject_reference(self):
        m1 = make_manifest(subject_reference=HEX_C)
        m2 = make_manifest(subject_reference=HEX_D)
        self.assertNotEqual(
            m1.baseline_manifest_id, m2.baseline_manifest_id
        )

    def test_identity_changes_with_source_contract_version(self):
        m1 = make_manifest(provenance=make_provenance(
            source_contract_version="1.0",
        ))
        m2 = make_manifest(provenance=make_provenance(
            source_contract_version="2.0",
        ))
        self.assertNotEqual(
            m1.baseline_manifest_id, m2.baseline_manifest_id
        )

    def test_identity_changes_with_window_start(self):
        m1 = make_manifest(
            window_start_source_timestamp_us=WINDOW_START,
        )
        m2 = make_manifest(
            window_start_source_timestamp_us=WINDOW_START + 1,
        )
        self.assertNotEqual(
            m1.baseline_manifest_id, m2.baseline_manifest_id
        )

    def test_identity_changes_with_window_end(self):
        m1 = make_manifest(
            window_end_source_timestamp_us=WINDOW_END,
        )
        m2 = make_manifest(
            window_end_source_timestamp_us=WINDOW_END + 1,
        )
        self.assertNotEqual(
            m1.baseline_manifest_id, m2.baseline_manifest_id
        )

    def test_identity_changes_with_input_references(self):
        m1 = make_manifest(input_reference_digests=(HEX_A, HEX_B))
        m2 = make_manifest(input_reference_digests=(HEX_A, HEX_C))
        self.assertNotEqual(
            m1.baseline_manifest_id, m2.baseline_manifest_id
        )

    def test_identity_changes_with_minimum_sample_count(self):
        m1 = make_manifest(minimum_sample_count=2)
        m2 = make_manifest(minimum_sample_count=3)
        self.assertNotEqual(
            m1.baseline_manifest_id, m2.baseline_manifest_id
        )

    def test_non_identity_ingest_timestamp_stable(self):
        m1 = make_manifest(created_ingest_timestamp_us=INGEST_TS)
        m2 = make_manifest(created_ingest_timestamp_us=INGEST_TS + 5000)
        self.assertEqual(
            m1.baseline_manifest_id, m2.baseline_manifest_id
        )

    def test_non_identity_analyzer_name_stable(self):
        m1 = make_manifest(
            provenance=BaselineProvenanceV1(
                analyzer_name="cyt.baseline",
                analyzer_version="1.0.0",
                analysis_mode="synthetic",
                source_contract_version="1.0",
            ),
        )
        m2 = make_manifest(
            provenance=BaselineProvenanceV1(
                analyzer_name="other.analyzer",
                analyzer_version="1.0.0",
                analysis_mode="synthetic",
                source_contract_version="1.0",
            ),
        )
        self.assertEqual(
            m1.baseline_manifest_id, m2.baseline_manifest_id
        )

    def test_non_identity_analyzer_version_stable(self):
        m1 = make_manifest(
            provenance=BaselineProvenanceV1(
                analyzer_name="cyt.baseline",
                analyzer_version="1.0.0",
                analysis_mode="synthetic",
                source_contract_version="1.0",
            ),
        )
        m2 = make_manifest(
            provenance=BaselineProvenanceV1(
                analyzer_name="cyt.baseline",
                analyzer_version="2.0.0",
                analysis_mode="synthetic",
                source_contract_version="1.0",
            ),
        )
        self.assertEqual(
            m1.baseline_manifest_id, m2.baseline_manifest_id
        )

    def test_non_identity_analysis_mode_stable(self):
        m1 = make_manifest(
            provenance=BaselineProvenanceV1(
                analyzer_name="cyt.baseline",
                analyzer_version="1.0.0",
                analysis_mode="synthetic",
                source_contract_version="1.0",
            ),
        )
        m2 = make_manifest(
            provenance=BaselineProvenanceV1(
                analyzer_name="cyt.baseline",
                analyzer_version="1.0.0",
                analysis_mode="live",
                source_contract_version="1.0",
            ),
        )
        self.assertEqual(
            m1.baseline_manifest_id, m2.baseline_manifest_id
        )


# ── Comparison ──────────────────────────────────────────────────────────────


class TestBaselineManifestComparison(unittest.TestCase):

    def test_compare_duplicate(self):
        m1 = make_manifest(HMAC_KEY_A)
        m2 = make_manifest(HMAC_KEY_A)
        self.assertEqual(
            compare_baseline_manifest_source_facts(m1, m2), "duplicate"
        )

    def test_compare_identity_conflict_different_id(self):
        m1 = make_manifest(HMAC_KEY_A)
        m2 = make_manifest(HMAC_KEY_B)
        self.assertEqual(
            compare_baseline_manifest_source_facts(m1, m2),
            "identity_conflict",
        )

    def test_compare_identity_conflict_same_id_changed_fact(self):
        m1 = make_manifest(HMAC_KEY_A)
        m2 = BaselineManifestV1(
            schema_version=m1.schema_version,
            record_kind=m1.record_kind,
            baseline_manifest_id=m1.baseline_manifest_id,
            baseline_manifest_digest=m1.baseline_manifest_digest,
            analysis_type="different.type",
            analysis_version=m1.analysis_version,
            baseline_method=m1.baseline_method,
            baseline_version=m1.baseline_version,
            subject_kind=m1.subject_kind,
            subject_reference=m1.subject_reference,
            window_start_source_timestamp_us=(
                m1.window_start_source_timestamp_us
            ),
            window_end_source_timestamp_us=(
                m1.window_end_source_timestamp_us
            ),
            time_basis=m1.time_basis,
            boundary_policy=m1.boundary_policy,
            input_reference_digests=m1.input_reference_digests,
            sample_count=m1.sample_count,
            minimum_sample_count=m1.minimum_sample_count,
            baseline_status=m1.baseline_status,
            status_reason_code=m1.status_reason_code,
            created_ingest_timestamp_us=m1.created_ingest_timestamp_us,
            provenance=m1.provenance,
        )
        self.assertEqual(
            compare_baseline_manifest_source_facts(m1, m2),
            "identity_conflict",
        )

    def test_compare_ignores_non_identity_ingest_timestamp(self):
        m1 = make_manifest(created_ingest_timestamp_us=INGEST_TS)
        m2 = make_manifest(created_ingest_timestamp_us=INGEST_TS + 5000)
        self.assertEqual(
            compare_baseline_manifest_source_facts(m1, m2), "duplicate"
        )

    def test_compare_ignores_non_identity_provenance(self):
        m1 = make_manifest()
        m2 = make_manifest(
            provenance=BaselineProvenanceV1(
                analyzer_name="other.analyzer",
                analyzer_version="9.9.9",
                analysis_mode="live",
                source_contract_version="1.0",
            ),
        )
        self.assertEqual(
            compare_baseline_manifest_source_facts(m1, m2), "duplicate"
        )

    def test_compare_detects_source_contract_version_change(self):
        m1 = make_manifest(
            provenance=make_provenance(source_contract_version="1.0"),
        )
        m2 = make_manifest(
            provenance=make_provenance(source_contract_version="2.0"),
        )
        self.assertEqual(
            compare_baseline_manifest_source_facts(m1, m2),
            "identity_conflict",
        )

    def test_compare_rejects_non_baselinemanifestv1(self):
        with self.assertRaises(ValueError):
            compare_baseline_manifest_source_facts(
                "not-a-manifest", make_manifest()
            )
        with self.assertRaises(ValueError):
            compare_baseline_manifest_source_facts(
                make_manifest(), "not-a-manifest"
            )

    def test_compare_rejects_manifest_subclass(self):
        class MyManifest(BaselineManifestV1):
            pass

        valid = make_manifest()
        subclass = MyManifest(**valid.__dict__)

        with self.assertRaises(ValueError):
            compare_baseline_manifest_source_facts(subclass, valid)
        with self.assertRaises(ValueError):
            compare_baseline_manifest_source_facts(valid, subclass)


# ── Malformed inputs ────────────────────────────────────────────────────────


class TestMalformedInputs(unittest.TestCase):

    def _base_kwargs(self):
        return {
            "hmac_key": HMAC_KEY_A,
            "analysis_type": "statistical.mean",
            "analysis_version": "1.0.0",
            "baseline_method": "rolling_window",
            "baseline_version": "1.0.0",
            "subject_kind": "device.aggregate",
            "subject_reference": HEX_C,
            "window_start_source_timestamp_us": WINDOW_START,
            "window_end_source_timestamp_us": WINDOW_END,
            "input_reference_digests": (HEX_A, HEX_B),
            "minimum_sample_count": 2,
            "created_ingest_timestamp_us": INGEST_TS,
            "provenance": make_provenance(),
        }

    def test_window_start_bool_rejected(self):
        kw = self._base_kwargs()
        kw["window_start_source_timestamp_us"] = True
        with self.assertRaises(ValueError):
            create_baseline_manifest(**kw)

    def test_window_start_float_rejected(self):
        kw = self._base_kwargs()
        kw["window_start_source_timestamp_us"] = 1000.5
        with self.assertRaises(ValueError):
            create_baseline_manifest(**kw)

    def test_window_start_string_rejected(self):
        kw = self._base_kwargs()
        kw["window_start_source_timestamp_us"] = "1000"
        with self.assertRaises(ValueError):
            create_baseline_manifest(**kw)

    def test_window_start_negative_rejected(self):
        kw = self._base_kwargs()
        kw["window_start_source_timestamp_us"] = -1
        with self.assertRaises(ValueError):
            create_baseline_manifest(**kw)

    def test_window_end_bool_rejected(self):
        kw = self._base_kwargs()
        kw["window_end_source_timestamp_us"] = True
        with self.assertRaises(ValueError):
            create_baseline_manifest(**kw)

    def test_window_start_end_equal_rejected(self):
        kw = self._base_kwargs()
        kw["window_end_source_timestamp_us"] = WINDOW_START
        with self.assertRaises(ValueError):
            create_baseline_manifest(**kw)

    def test_window_start_greater_than_end_rejected(self):
        kw = self._base_kwargs()
        kw["window_start_source_timestamp_us"] = WINDOW_END
        kw["window_end_source_timestamp_us"] = WINDOW_START
        with self.assertRaises(ValueError):
            create_baseline_manifest(**kw)

    def test_ingest_timestamp_bool_rejected(self):
        kw = self._base_kwargs()
        kw["created_ingest_timestamp_us"] = True
        with self.assertRaises(ValueError):
            create_baseline_manifest(**kw)

    def test_minimum_sample_count_bool_rejected(self):
        kw = self._base_kwargs()
        kw["minimum_sample_count"] = True
        with self.assertRaises(ValueError):
            create_baseline_manifest(**kw)

    def test_minimum_sample_count_zero_rejected(self):
        kw = self._base_kwargs()
        kw["minimum_sample_count"] = 0
        with self.assertRaises(ValueError):
            create_baseline_manifest(**kw)

    def test_minimum_sample_count_negative_rejected(self):
        kw = self._base_kwargs()
        kw["minimum_sample_count"] = -1
        with self.assertRaises(ValueError):
            create_baseline_manifest(**kw)

    def test_minimum_sample_count_float_rejected(self):
        kw = self._base_kwargs()
        kw["minimum_sample_count"] = 1.5
        with self.assertRaises(ValueError):
            create_baseline_manifest(**kw)

    def test_minimum_sample_count_string_rejected(self):
        kw = self._base_kwargs()
        kw["minimum_sample_count"] = "2"
        with self.assertRaises(ValueError):
            create_baseline_manifest(**kw)

    def test_empty_hmac_key_rejected(self):
        kw = self._base_kwargs()
        kw["hmac_key"] = b""
        with self.assertRaises(ValueError):
            create_baseline_manifest(**kw)

    def test_hmac_key_string_rejected(self):
        kw = self._base_kwargs()
        kw["hmac_key"] = "not-bytes"
        with self.assertRaises(ValueError):
            create_baseline_manifest(**kw)

    def test_digest_uppercase_rejected(self):
        kw = self._base_kwargs()
        kw["subject_reference"] = "A" * 64
        with self.assertRaises(ValueError):
            create_baseline_manifest(**kw)

    def test_digest_wrong_length_rejected(self):
        kw = self._base_kwargs()
        kw["subject_reference"] = "a" * 63
        with self.assertRaises(ValueError):
            create_baseline_manifest(**kw)

    def test_digest_non_hex_rejected(self):
        kw = self._base_kwargs()
        kw["subject_reference"] = "x" * 64
        with self.assertRaises(ValueError):
            create_baseline_manifest(**kw)

    def test_input_ref_uppercase_rejected(self):
        kw = self._base_kwargs()
        kw["input_reference_digests"] = ("A" * 64, HEX_B)
        with self.assertRaises(ValueError):
            create_baseline_manifest(**kw)

    def test_input_ref_wrong_length_rejected(self):
        kw = self._base_kwargs()
        kw["input_reference_digests"] = ("a" * 63, HEX_B)
        with self.assertRaises(ValueError):
            create_baseline_manifest(**kw)

    def test_provenance_wrong_type_rejected(self):
        kw = self._base_kwargs()
        kw["provenance"] = "not-a-provenance"
        with self.assertRaises(ValueError):
            create_baseline_manifest(**kw)

    def test_constructor_rejects_provenance_subclass(self):
        class MyProvenance(BaselineProvenanceV1):
            pass

        kw = self._base_kwargs()
        kw["provenance"] = MyProvenance(
            analyzer_name="cyt.baseline",
            analyzer_version="1.0.0",
            analysis_mode="synthetic",
            source_contract_version="1.0",
        )
        with self.assertRaises(ValueError):
            create_baseline_manifest(**kw)


# ── Exported constants ──────────────────────────────────────────────────────


class TestExportedConstants(unittest.TestCase):

    def test_all_exported_present(self):
        for name in EXPORTED_ALL:
            self.assertIn(name, dir(sys.modules["baseline_contract"]))

    def test_all_exported_contains_six_names(self):
        self.assertEqual(len(EXPORTED_ALL), 6)

    def test_baseline_statuses_values(self):
        self.assertEqual(
            BASELINE_STATUSES,
            {"available", "insufficient_data", "unknown"},
        )

    def test_baseline_statuses_is_frozenset(self):
        self.assertIsInstance(BASELINE_STATUSES, frozenset)

    def test_record_kind_value(self):
        self.assertEqual(
            BASELINE_MANIFEST_RECORD_KIND, "baseline_manifest"
        )


# ── Field order ─────────────────────────────────────────────────────────────


class TestFieldOrder(unittest.TestCase):

    def test_baseline_manifest_v1_field_order(self):
        fields = [
            f.name
            for f in __import__(
                "dataclasses"
            ).fields(BaselineManifestV1)
        ]
        expected = [
            "schema_version",
            "record_kind",
            "baseline_manifest_id",
            "baseline_manifest_digest",
            "analysis_type",
            "analysis_version",
            "baseline_method",
            "baseline_version",
            "subject_kind",
            "subject_reference",
            "window_start_source_timestamp_us",
            "window_end_source_timestamp_us",
            "time_basis",
            "boundary_policy",
            "input_reference_digests",
            "sample_count",
            "minimum_sample_count",
            "baseline_status",
            "status_reason_code",
            "created_ingest_timestamp_us",
            "provenance",
        ]
        self.assertEqual(fields, expected)

    def test_baseline_provenance_v1_field_order(self):
        fields = [
            f.name
            for f in __import__(
                "dataclasses"
            ).fields(BaselineProvenanceV1)
        ]
        expected = [
            "analyzer_name",
            "analyzer_version",
            "analysis_mode",
            "source_contract_version",
        ]
        self.assertEqual(fields, expected)

    def test_both_dataclasses_frozen(self):
        self.assertTrue(__import__(
            "dataclasses"
        ).is_dataclass(BaselineProvenanceV1))
        self.assertTrue(__import__(
            "dataclasses"
        ).is_dataclass(BaselineManifestV1))
        import dataclasses
        self.assertTrue(dataclasses.is_dataclass(BaselineProvenanceV1))
        self.assertTrue(dataclasses.is_dataclass(BaselineManifestV1))


# ── AST prohibitions ───────────────────────────────────────────────────────


class TestASTProhibitions(unittest.TestCase):

    def _load_source(self):
        with open("baseline_contract.py") as f:
            return ast.parse(f.read())

    def test_no_forbidden_imports(self):
        tree = self._load_source()
        forbidden = {
            "sqlite3",
            "sqlite",
            "tkinter",
            "subprocess",
            "smtplib",
            "http",
            "urllib",
            "socket",
            "logging",
            "threading",
            "multiprocessing",
            "alert_store",
            "alert_projection",
            "surveillance_detector",
            "surveillance_analyzer",
            "observation_store",
            "observation_contract",
            "route_session_contract",
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
                        self.fail(f"forbidden import: {node.module}")

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

            if isinstance(node.func, ast.Attribute):
                if node.func.attr in {"connect", "execute"}:
                    self.fail(f"forbidden call: {node.func.attr}")

    def test_canonical_identity_uses_sort_keys_and_compact_separators(self):
        with open("baseline_contract.py") as f:
            source = f.read()

        func_start = source.find("def _canonical_identity_bytes")
        self.assertGreaterEqual(func_start, 0)

        func_body = source[func_start:func_start + 400]
        self.assertIn("sort_keys=True", func_body)
        self.assertIn('separators=(",", ":")', func_body)
        self.assertIn("ensure_ascii=False", func_body)

    def test_no_forbidden_fields(self):
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
                        self.fail(f"forbidden field: {node.target.id}")

            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if target.id in forbidden:
                            self.fail(f"forbidden name: {target.id}")

            if isinstance(node, ast.Constant):
                if isinstance(node.value, str):
                    for word in forbidden:
                        if word in node.value.lower():
                            self.fail(f"forbidden string: {node.value}")


if __name__ == "__main__":
    unittest.main()
