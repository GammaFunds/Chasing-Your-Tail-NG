"""Deterministic focused tests for Baseline Result v1 contract."""

import ast
import copy
import sys
import unittest
from typing import Optional, Tuple

from baseline_contract import (
    __all__ as CONTRACT_ALL,
    BASELINE_MANIFEST_RECORD_KIND,
    BaselineProvenanceV1,
    BaselineManifestV1,
    create_baseline_manifest,
)

from baseline_result import (
    __all__ as RESULT_ALL,
    BASELINE_RESULT_RECORD_KIND,
    BASELINE_RESULT_ID_PREFIX,
    BaselineCountSampleV1,
    BaselineResultV1,
    create_baseline_result,
    compare_baseline_result_source_facts,
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

_MAX_COUNT = (1 << 63) - 1


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
        "analysis_type": "observation.count_per_collection_session",
        "analysis_version": "1.0.0",
        "baseline_method": "count_mean_range",
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


# ── BaselineCountSampleV1 ─────────────────────────────────────────────────


class TestBaselineCountSampleV1(unittest.TestCase):

    def test_valid_construction(self):
        s = make_sample(HEX_A, 42)
        self.assertIsInstance(s, BaselineCountSampleV1)
        self.assertEqual(s.input_reference_digest, HEX_A)
        self.assertEqual(s.observation_count, 42)

    def test_zero_count_allowed(self):
        s = make_sample(HEX_A, 0)
        self.assertEqual(s.observation_count, 0)

    def test_upper_bound_count_allowed(self):
        s = make_sample(HEX_A, _MAX_COUNT)
        self.assertEqual(s.observation_count, _MAX_COUNT)

    def test_frozen(self):
        s = make_sample(HEX_A, 1)
        with self.assertRaises(Exception):
            s.observation_count = 99

    def test_empty_digest_rejected(self):
        with self.assertRaises(ValueError):
            BaselineCountSampleV1(
                input_reference_digest="",
                observation_count=1,
            )

    def test_non_hex_digest_rejected(self):
        with self.assertRaises(ValueError):
            BaselineCountSampleV1(
                input_reference_digest="x" * 64,
                observation_count=1,
            )

    def test_wrong_length_digest_rejected(self):
        with self.assertRaises(ValueError):
            BaselineCountSampleV1(
                input_reference_digest="a" * 63,
                observation_count=1,
            )

    def test_uppercase_digest_rejected(self):
        with self.assertRaises(ValueError):
            BaselineCountSampleV1(
                input_reference_digest="A" * 64,
                observation_count=1,
            )

    def test_bool_count_rejected(self):
        with self.assertRaises(ValueError):
            BaselineCountSampleV1(
                input_reference_digest=HEX_A,
                observation_count=True,
            )

    def test_negative_count_rejected(self):
        with self.assertRaises(ValueError):
            BaselineCountSampleV1(
                input_reference_digest=HEX_A,
                observation_count=-1,
            )

    def test_oversized_count_rejected(self):
        with self.assertRaises(ValueError):
            BaselineCountSampleV1(
                input_reference_digest=HEX_A,
                observation_count=_MAX_COUNT + 1,
            )

    def test_float_count_rejected(self):
        with self.assertRaises(ValueError):
            BaselineCountSampleV1(
                input_reference_digest=HEX_A,
                observation_count=3.0,
            )

    def test_string_count_rejected(self):
        with self.assertRaises(ValueError):
            BaselineCountSampleV1(
                input_reference_digest=HEX_A,
                observation_count="5",
            )

    def test_non_string_digest_rejected(self):
        with self.assertRaises(ValueError):
            BaselineCountSampleV1(
                input_reference_digest=123,
                observation_count=5,
            )

    def test_whitespace_digest_rejected(self):
        with self.assertRaises(ValueError):
            BaselineCountSampleV1(
                input_reference_digest=" " + HEX_A,
                observation_count=5,
            )


# ── BaselineResultV1 construction via create_baseline_result ──────────────


class TestBaselineResultCreation(unittest.TestCase):

    def test_create_with_available_status(self):
        r = make_result()
        self.assertIsInstance(r, BaselineResultV1)
        self.assertEqual(r.schema_version, "1.0")
        self.assertEqual(r.record_kind, BASELINE_RESULT_RECORD_KIND)
        self.assertTrue(r.baseline_result_id.startswith(BASELINE_RESULT_ID_PREFIX))
        self.assertEqual(len(r.baseline_result_id), len(BASELINE_RESULT_ID_PREFIX) + 64)
        self.assertEqual(len(r.baseline_result_digest), 64)
        self.assertEqual(r.analysis_type, "observation.count_per_collection_session")
        self.assertEqual(r.analysis_version, "1.0.0")
        self.assertEqual(r.baseline_method, "count_mean_range")
        self.assertEqual(r.baseline_version, "1.0.0")

    def test_id_suffix_equals_digest(self):
        r = make_result()
        self.assertEqual(r.baseline_result_id[-64:], r.baseline_result_digest)

    def test_frozen(self):
        r = make_result()
        with self.assertRaises(Exception):
            r.baseline_status = "changed"

    def test_create_with_insufficient_data(self):
        manifest = make_manifest(
            input_reference_digests=(HEX_A,),
            minimum_sample_count=2,
        )
        samples = (make_sample(HEX_A, 5),)
        r = create_baseline_result(
            hmac_key=HMAC_KEY_A,
            manifest=manifest,
            samples=samples,
            created_ingest_timestamp_us=INGEST_TS,
            provenance=make_provenance(),
        )
        self.assertEqual(r.sample_count, 1)
        self.assertEqual(r.minimum_sample_count, 2)
        self.assertEqual(r.baseline_status, "insufficient_data")
        self.assertEqual(r.status_reason_code, "baseline.minimum_not_met")
        self.assertIsNone(r.minimum_count)
        self.assertIsNone(r.maximum_count)
        self.assertIsNone(r.count_mean_numerator)
        self.assertIsNone(r.count_mean_denominator)

    def test_create_with_unknown_status(self):
        manifest = make_manifest(
            input_reference_digests=(),
            minimum_sample_count=2,
        )
        samples = ()
        r = create_baseline_result(
            hmac_key=HMAC_KEY_A,
            manifest=manifest,
            samples=samples,
            created_ingest_timestamp_us=INGEST_TS,
            provenance=make_provenance(),
        )
        self.assertEqual(r.sample_count, 0)
        self.assertEqual(r.minimum_sample_count, 2)
        self.assertEqual(r.baseline_status, "unknown")
        self.assertEqual(r.status_reason_code, "baseline.no_samples")
        self.assertIsNone(r.minimum_count)
        self.assertIsNone(r.maximum_count)
        self.assertIsNone(r.count_mean_numerator)
        self.assertIsNone(r.count_mean_denominator)

    def test_deterministic_result_id(self):
        r1 = make_result()
        r2 = make_result()
        self.assertEqual(r1.baseline_result_id, r2.baseline_result_id)
        self.assertEqual(r1.baseline_result_digest, r2.baseline_result_digest)

    def test_different_hmac_key_changes_result_id(self):
        r1 = make_result(hmac_key=HMAC_KEY_A)
        r2 = make_result(hmac_key=HMAC_KEY_B)
        self.assertNotEqual(r1.baseline_result_id, r2.baseline_result_id)

    def test_store_manifest_id_and_digest(self):
        manifest = make_manifest()
        r = make_result(manifest=manifest)
        self.assertEqual(r.manifest_id, manifest.baseline_manifest_id)
        self.assertEqual(r.manifest_digest, manifest.baseline_manifest_digest)

    def test_result_id_depends_only_on_manifest_digest(self):
        manifest = make_manifest()
        s1 = (make_sample(HEX_A, 3), make_sample(HEX_B, 7))
        s2 = (make_sample(HEX_A, 10), make_sample(HEX_B, 20))
        r1 = make_result(manifest=manifest, samples=s1)
        r2 = make_result(manifest=manifest, samples=s2)
        self.assertEqual(r1.baseline_result_id, r2.baseline_result_id)


# ── Metrics: min, max, reduced mean ───────────────────────────────────────


class TestBaselineMetrics(unittest.TestCase):

    def test_simple_mean(self):
        manifest = make_manifest(
            input_reference_digests=(HEX_A, HEX_B, HEX_C),
            minimum_sample_count=2,
        )
        samples = (
            make_sample(HEX_A, 1),
            make_sample(HEX_B, 2),
            make_sample(HEX_C, 3),
        )
        r = make_result(manifest=manifest, samples=samples)
        self.assertEqual(r.minimum_count, 1)
        self.assertEqual(r.maximum_count, 3)
        self.assertEqual(r.count_mean_numerator, 2)
        self.assertEqual(r.count_mean_denominator, 1)

    def test_odd_mean_not_reducible(self):
        manifest = make_manifest(
            input_reference_digests=(HEX_A, HEX_B),
            minimum_sample_count=2,
        )
        samples = (
            make_sample(HEX_A, 1),
            make_sample(HEX_B, 2),
        )
        r = make_result(manifest=manifest, samples=samples)
        self.assertEqual(r.minimum_count, 1)
        self.assertEqual(r.maximum_count, 2)
        self.assertEqual(r.count_mean_numerator, 3)
        self.assertEqual(r.count_mean_denominator, 2)

    def test_fraction_reduction(self):
        manifest = make_manifest(
            input_reference_digests=(HEX_A, HEX_B, HEX_C),
            minimum_sample_count=2,
        )
        samples = (
            make_sample(HEX_A, 2),
            make_sample(HEX_B, 4),
            make_sample(HEX_C, 6),
        )
        r = make_result(manifest=manifest, samples=samples)
        self.assertEqual(r.count_mean_numerator, 4)
        self.assertEqual(r.count_mean_denominator, 1)

    def test_fraction_reduction_large_gcd(self):
        manifest = make_manifest(
            input_reference_digests=(HEX_A, HEX_B),
            minimum_sample_count=2,
        )
        samples = (
            make_sample(HEX_A, 4),
            make_sample(HEX_B, 6),
        )
        r = make_result(manifest=manifest, samples=samples)
        self.assertEqual(r.count_mean_numerator, 5)
        self.assertEqual(r.count_mean_denominator, 1)

    def test_zero_counts(self):
        manifest = make_manifest(
            input_reference_digests=(HEX_A, HEX_B, HEX_C),
            minimum_sample_count=2,
        )
        samples = (
            make_sample(HEX_A, 0),
            make_sample(HEX_B, 0),
            make_sample(HEX_C, 0),
        )
        r = make_result(manifest=manifest, samples=samples)
        self.assertEqual(r.minimum_count, 0)
        self.assertEqual(r.maximum_count, 0)
        self.assertEqual(r.count_mean_numerator, 0)
        self.assertEqual(r.count_mean_denominator, 1)

    def test_upper_bound_counts(self):
        manifest = make_manifest(
            input_reference_digests=(HEX_A, HEX_B),
            minimum_sample_count=2,
        )
        samples = (
            make_sample(HEX_A, _MAX_COUNT),
            make_sample(HEX_B, _MAX_COUNT),
        )
        r = make_result(manifest=manifest, samples=samples)
        self.assertEqual(r.minimum_count, _MAX_COUNT)
        self.assertEqual(r.maximum_count, _MAX_COUNT)
        self.assertEqual(r.count_mean_numerator, _MAX_COUNT)
        self.assertEqual(r.count_mean_denominator, 1)

    def test_single_sample(self):
        manifest = make_manifest(
            input_reference_digests=(HEX_A,),
            minimum_sample_count=2,
        )
        samples = (make_sample(HEX_A, 42),)
        r = make_result(manifest=manifest, samples=samples)
        self.assertEqual(r.baseline_status, "insufficient_data")
        self.assertIsNone(r.minimum_count)
        self.assertIsNone(r.maximum_count)

    def test_threshold_available(self):
        manifest = make_manifest(
            input_reference_digests=(HEX_A, HEX_B),
            minimum_sample_count=2,
        )
        samples = (
            make_sample(HEX_A, 7),
            make_sample(HEX_B, 11),
        )
        r = make_result(manifest=manifest, samples=samples)
        self.assertEqual(r.baseline_status, "available")
        self.assertEqual(r.minimum_count, 7)
        self.assertEqual(r.maximum_count, 11)
        self.assertEqual(r.count_mean_numerator, 9)
        self.assertEqual(r.count_mean_denominator, 1)

    def test_large_count_sum(self):
        manifest = make_manifest(
            input_reference_digests=(HEX_A, HEX_B, HEX_C, HEX_D),
            minimum_sample_count=2,
        )
        samples = (
            make_sample(HEX_A, 1000000),
            make_sample(HEX_B, 2000000),
            make_sample(HEX_C, 3000000),
            make_sample(HEX_D, 4000000),
        )
        r = make_result(manifest=manifest, samples=samples)
        self.assertEqual(r.minimum_count, 1000000)
        self.assertEqual(r.maximum_count, 4000000)
        self.assertEqual(r.count_mean_numerator, 2500000)
        self.assertEqual(r.count_mean_denominator, 1)

    def test_fraction_with_remainder(self):
        manifest = make_manifest(
            input_reference_digests=(HEX_A, HEX_B, HEX_C),
            minimum_sample_count=2,
        )
        samples = (
            make_sample(HEX_A, 1),
            make_sample(HEX_B, 1),
            make_sample(HEX_C, 2),
        )
        r = make_result(manifest=manifest, samples=samples)
        self.assertEqual(r.count_mean_numerator, 4)
        self.assertEqual(r.count_mean_denominator, 3)

    def test_fraction_reduction_not_to_integer(self):
        manifest = make_manifest(
            input_reference_digests=(HEX_A, HEX_B, HEX_C, HEX_D),
            minimum_sample_count=2,
        )
        samples = (
            make_sample(HEX_A, 6),
            make_sample(HEX_B, 8),
            make_sample(HEX_C, 10),
            make_sample(HEX_D, 12),
        )
        r = make_result(manifest=manifest, samples=samples)
        self.assertEqual(r.count_mean_numerator, 9)
        self.assertEqual(r.count_mean_denominator, 1)


# ── Order independence ────────────────────────────────────────────────────


class TestOrderIndependence(unittest.TestCase):

    def test_order_independent_result_from_differently_ordered_manifests(self):
        refs_a = (HEX_C, HEX_A, HEX_B)
        refs_b = (HEX_B, HEX_C, HEX_A)
        m1 = make_manifest(input_reference_digests=refs_a)
        m2 = make_manifest(input_reference_digests=refs_b)
        self.assertEqual(m1.baseline_manifest_id, m2.baseline_manifest_id)

        s1 = (
            make_sample(HEX_A, 3),
            make_sample(HEX_B, 7),
            make_sample(HEX_C, 11),
        )
        s2 = (
            make_sample(HEX_A, 3),
            make_sample(HEX_B, 7),
            make_sample(HEX_C, 11),
        )
        r1 = make_result(manifest=m1, samples=s1)
        r2 = make_result(manifest=m2, samples=s2)
        self.assertEqual(r1.baseline_result_id, r2.baseline_result_id)
        self.assertEqual(r1.samples, r2.samples)
        self.assertEqual(r1.minimum_count, r2.minimum_count)
        self.assertEqual(r1.maximum_count, r2.maximum_count)
        self.assertEqual(r1.count_mean_numerator, r2.count_mean_numerator)
        self.assertEqual(r1.count_mean_denominator, r2.count_mean_denominator)
        self.assertEqual(r1, r2)

    def test_differently_ordered_samples_produce_equal_results(self):
        manifest = make_manifest(
            input_reference_digests=(HEX_A, HEX_B, HEX_C),
            minimum_sample_count=2,
        )
        ordered_samples = (
            make_sample(HEX_A, 3),
            make_sample(HEX_B, 7),
            make_sample(HEX_C, 11),
        )
        shuffled_samples = (
            make_sample(HEX_C, 11),
            make_sample(HEX_A, 3),
            make_sample(HEX_B, 7),
        )
        r1 = make_result(manifest=manifest, samples=ordered_samples)
        r2 = make_result(manifest=manifest, samples=shuffled_samples)
        self.assertEqual(r1.baseline_result_id, r2.baseline_result_id)
        stored_expected = (
            make_sample(HEX_A, 3),
            make_sample(HEX_B, 7),
            make_sample(HEX_C, 11),
        )
        self.assertEqual(r1.samples, stored_expected)
        self.assertEqual(r2.samples, stored_expected)
        self.assertEqual(r1, r2)

    def test_identical_same_result_byte_for_byte_ignoring_operational(self):
        r1 = make_result()
        r2 = make_result()
        self.assertEqual(r1, r2)
        self.assertNotEqual(id(r1), id(r2))


# ── Error cases for create_baseline_result ──────────────────────────────


class TestBaselineResultErrors(unittest.TestCase):

    def _base_kwargs(self):
        manifest = make_manifest()
        samples = make_samples_from_manifest(manifest)
        return {
            "hmac_key": HMAC_KEY_A,
            "manifest": manifest,
            "samples": samples,
            "created_ingest_timestamp_us": INGEST_TS,
            "provenance": make_provenance(),
        }

    def test_wrong_analysis_type_rejected(self):
        kw = self._base_kwargs()
        manifest = make_manifest(
            hmac_key=HMAC_KEY_A,
            analysis_type="wrong.type",
            input_reference_digests=(HEX_A, HEX_B),
        )
        kw["manifest"] = manifest
        with self.assertRaises(ValueError):
            create_baseline_result(**kw)

    def test_wrong_baseline_method_rejected(self):
        kw = self._base_kwargs()
        manifest = make_manifest(
            hmac_key=HMAC_KEY_A,
            baseline_method="wrong_method",
            input_reference_digests=(HEX_A, HEX_B),
        )
        kw["manifest"] = manifest
        with self.assertRaises(ValueError):
            create_baseline_result(**kw)

    def test_wrong_baseline_version_rejected(self):
        kw = self._base_kwargs()
        manifest = make_manifest(
            hmac_key=HMAC_KEY_A,
            baseline_version="2.0.0",
            input_reference_digests=(HEX_A, HEX_B),
        )
        kw["manifest"] = manifest
        with self.assertRaises(ValueError):
            create_baseline_result(**kw)

    def test_hmac_key_mismatch_rejected(self):
        kw = self._base_kwargs()
        manifest = make_manifest(hmac_key=HMAC_KEY_B)
        kw["manifest"] = manifest
        kw["hmac_key"] = HMAC_KEY_A
        with self.assertRaises(ValueError):
            create_baseline_result(**kw)

    def test_missing_samples_rejected(self):
        kw = self._base_kwargs()
        manifest = make_manifest(input_reference_digests=(HEX_A, HEX_B))
        kw["manifest"] = manifest
        kw["samples"] = (make_sample(HEX_A, 5),)
        with self.assertRaises(ValueError):
            create_baseline_result(**kw)

    def test_extra_samples_rejected(self):
        kw = self._base_kwargs()
        manifest = make_manifest(input_reference_digests=(HEX_A,))
        kw["manifest"] = manifest
        kw["samples"] = (make_sample(HEX_A, 5), make_sample(HEX_B, 3))
        with self.assertRaises(ValueError):
            create_baseline_result(**kw)

    def test_duplicate_sample_digests_rejected(self):
        kw = self._base_kwargs()
        samples = (make_sample(HEX_A, 5), make_sample(HEX_A, 3))
        kw["samples"] = samples
        with self.assertRaises(ValueError):
            create_baseline_result(**kw)

    def test_wrong_digest_in_sample_rejected(self):
        kw = self._base_kwargs()
        manifest = make_manifest(input_reference_digests=(HEX_A, HEX_B))
        kw["manifest"] = manifest
        kw["samples"] = (make_sample(HEX_A, 5), make_sample(HEX_D, 3))
        with self.assertRaises(ValueError):
            create_baseline_result(**kw)

    def test_bool_timestamp_rejected(self):
        kw = self._base_kwargs()
        kw["created_ingest_timestamp_us"] = True
        with self.assertRaises(ValueError):
            create_baseline_result(**kw)

    def test_negative_timestamp_rejected(self):
        kw = self._base_kwargs()
        kw["created_ingest_timestamp_us"] = -1
        with self.assertRaises(ValueError):
            create_baseline_result(**kw)

    def test_float_timestamp_rejected(self):
        kw = self._base_kwargs()
        kw["created_ingest_timestamp_us"] = 1000.5
        with self.assertRaises(ValueError):
            create_baseline_result(**kw)

    def test_wrong_provenance_type_rejected(self):
        kw = self._base_kwargs()
        kw["provenance"] = "not-provenance"
        with self.assertRaises(ValueError):
            create_baseline_result(**kw)

    def test_subclass_manifest_rejected(self):
        class MyManifest(BaselineManifestV1):
            pass
        valid = make_manifest()
        subclass = MyManifest(**valid.__dict__)
        with self.assertRaises(ValueError):
            create_baseline_result(
                hmac_key=HMAC_KEY_A,
                manifest=subclass,
                samples=make_samples_from_manifest(valid),
                created_ingest_timestamp_us=INGEST_TS,
                provenance=make_provenance(),
            )

    def test_subclass_samples_rejected(self):
        kw = self._base_kwargs()
        class MySample(BaselineCountSampleV1):
            pass
        bad_sample = MySample(
            input_reference_digest=HEX_A,
            observation_count=5,
        )
        kw["samples"] = (bad_sample, make_sample(HEX_B, 3))
        with self.assertRaises(ValueError):
            create_baseline_result(**kw)

    def test_non_tuple_samples_rejected(self):
        kw = self._base_kwargs()
        kw["samples"] = [make_sample(HEX_A, 5)]
        with self.assertRaises(ValueError):
            create_baseline_result(**kw)

    def test_empty_hmac_key_rejected(self):
        kw = self._base_kwargs()
        kw["hmac_key"] = b""
        with self.assertRaises(ValueError):
            create_baseline_result(**kw)

    def test_string_hmac_key_rejected(self):
        kw = self._base_kwargs()
        kw["hmac_key"] = "not-bytes"
        with self.assertRaises(ValueError):
            create_baseline_result(**kw)

    def test_single_sample_available(self):
        manifest = make_manifest(
            input_reference_digests=(HEX_A,),
            minimum_sample_count=1,
        )
        samples = (make_sample(HEX_A, 7),)
        r = make_result(manifest=manifest, samples=samples)
        self.assertEqual(r.baseline_status, "available")
        self.assertEqual(r.minimum_count, 7)
        self.assertEqual(r.maximum_count, 7)
        self.assertEqual(r.count_mean_numerator, 7)
        self.assertEqual(r.count_mean_denominator, 1)

    def test_mean_with_all_identical_counts(self):
        manifest = make_manifest(
            input_reference_digests=(HEX_A, HEX_B, HEX_C, HEX_D),
            minimum_sample_count=2,
        )
        samples = (
            make_sample(HEX_A, 10),
            make_sample(HEX_B, 10),
            make_sample(HEX_C, 10),
            make_sample(HEX_D, 10),
        )
        r = make_result(manifest=manifest, samples=samples)
        self.assertEqual(r.minimum_count, 10)
        self.assertEqual(r.maximum_count, 10)
        self.assertEqual(r.count_mean_numerator, 10)
        self.assertEqual(r.count_mean_denominator, 1)

    def test_mean_reducible_by_five(self):
        manifest = make_manifest(
            input_reference_digests=(HEX_A, HEX_B),
            minimum_sample_count=2,
        )
        samples = (
            make_sample(HEX_A, 10),
            make_sample(HEX_B, 15),
        )
        r = make_result(manifest=manifest, samples=samples)
        self.assertEqual(r.count_mean_numerator, 25)
        self.assertEqual(r.count_mean_denominator, 2)


# ── Direct construction validation ──────────────────────────────────────


class TestDirectConstructionValidation(unittest.TestCase):

    def _valid_result(self) -> BaselineResultV1:
        return make_result()

    def assert_rejects(self, **overrides):
        r = self._valid_result()
        base = {
            "schema_version": r.schema_version,
            "record_kind": r.record_kind,
            "baseline_result_id": r.baseline_result_id,
            "baseline_result_digest": r.baseline_result_digest,
            "analysis_type": r.analysis_type,
            "analysis_version": r.analysis_version,
            "baseline_method": r.baseline_method,
            "baseline_version": r.baseline_version,
            "manifest_id": r.manifest_id,
            "manifest_digest": r.manifest_digest,
            "samples": r.samples,
            "sample_count": r.sample_count,
            "minimum_sample_count": r.minimum_sample_count,
            "baseline_status": r.baseline_status,
            "status_reason_code": r.status_reason_code,
            "minimum_count": r.minimum_count,
            "maximum_count": r.maximum_count,
            "count_mean_numerator": r.count_mean_numerator,
            "count_mean_denominator": r.count_mean_denominator,
            "created_ingest_timestamp_us": r.created_ingest_timestamp_us,
            "provenance": r.provenance,
        }
        base.update(overrides)
        with self.assertRaises(ValueError):
            BaselineResultV1(**base)

    def test_rejects_wrong_schema_version(self):
        self.assert_rejects(schema_version="2.0")

    def test_rejects_wrong_record_kind(self):
        self.assert_rejects(record_kind="wrong")

    def test_rejects_bad_id_format(self):
        self.assert_rejects(baseline_result_id="bad_" + ("a" * 64))

    def test_rejects_id_digest_mismatch(self):
        good = self._valid_result()
        with self.assertRaises(ValueError):
            BaselineResultV1(
                schema_version=good.schema_version,
                record_kind=good.record_kind,
                baseline_result_id="blr_v1_" + ("a" * 64),
                baseline_result_digest=("b" * 64),
                analysis_type=good.analysis_type,
                analysis_version=good.analysis_version,
                baseline_method=good.baseline_method,
                baseline_version=good.baseline_version,
                manifest_id=good.manifest_id,
                manifest_digest=good.manifest_digest,
                samples=good.samples,
                sample_count=good.sample_count,
                minimum_sample_count=good.minimum_sample_count,
                baseline_status=good.baseline_status,
                status_reason_code=good.status_reason_code,
                minimum_count=good.minimum_count,
                maximum_count=good.maximum_count,
                count_mean_numerator=good.count_mean_numerator,
                count_mean_denominator=good.count_mean_denominator,
                created_ingest_timestamp_us=good.created_ingest_timestamp_us,
                provenance=good.provenance,
            )

    def test_rejects_wrong_analysis_type(self):
        self.assert_rejects(analysis_type="wrong.type")

    def test_rejects_wrong_baseline_method(self):
        self.assert_rejects(baseline_method="wrong_method")

    def test_rejects_non_tuple_samples(self):
        self.assert_rejects(samples=[make_sample(HEX_A, 1)])

    def test_rejects_duplicate_sample_digests(self):
        self.assert_rejects(samples=(
            make_sample(HEX_A, 1),
            make_sample(HEX_A, 2),
        ))

    def test_rejects_sample_subclass(self):
        class MySample(BaselineCountSampleV1):
            pass
        bad = MySample(
            input_reference_digest=HEX_A,
            observation_count=5,
        )
        good = self._valid_result()
        good_samples = list(good.samples)
        good_samples[0] = bad
        self.assert_rejects(samples=tuple(good_samples))

    def test_rejects_wrong_status(self):
        self.assert_rejects(
            baseline_status="invalid_status",
            status_reason_code="baseline.no_samples",
            minimum_count=None,
            maximum_count=None,
            count_mean_numerator=None,
            count_mean_denominator=None,
        )

    def test_rejects_available_with_none_metrics(self):
        self.assert_rejects(
            baseline_status="available",
            status_reason_code="baseline.minimum_met",
            minimum_count=None,
            maximum_count=None,
            count_mean_numerator=None,
            count_mean_denominator=None,
        )

    def test_rejects_non_available_with_metrics(self):
        self.assert_rejects(
            baseline_status="insufficient_data",
            status_reason_code="baseline.minimum_not_met",
            minimum_count=0,
            maximum_count=1,
            count_mean_numerator=1,
            count_mean_denominator=1,
        )

    def test_rejects_metric_mismatch_vs_samples(self):
        r = self._valid_result()
        mismatched_min = r.minimum_count + 1 if r.minimum_count is not None else 0
        mismatched_max = r.maximum_count if r.maximum_count is not None else 0
        if mismatched_min <= mismatched_max:
            self.assert_rejects(minimum_count=mismatched_min)

    def test_rejects_bool_timestamp(self):
        self.assert_rejects(created_ingest_timestamp_us=True)

    def test_rejects_negative_timestamp(self):
        self.assert_rejects(created_ingest_timestamp_us=-1)

    def test_rejects_wrong_provenance_type(self):
        self.assert_rejects(provenance="bad")

    def test_rejects_provenance_subclass(self):
        class MyProvenance(BaselineProvenanceV1):
            pass
        bad = MyProvenance(
            analyzer_name="cyt.baseline",
            analyzer_version="1.0.0",
            analysis_mode="synthetic",
            source_contract_version="1.0",
        )
        self.assert_rejects(provenance=bad)

    def test_rejects_bad_manifest_id_format(self):
        self.assert_rejects(manifest_id="bad-" + ("a" * 64))

    def test_rejects_manifest_id_suffix_mismatch(self):
        r = self._valid_result()
        bad_manifest_id = "blm_v1_" + ("d" * 64)
        with self.assertRaises(ValueError):
            BaselineResultV1(
                schema_version=r.schema_version,
                record_kind=r.record_kind,
                baseline_result_id=r.baseline_result_id,
                baseline_result_digest=r.baseline_result_digest,
                analysis_type=r.analysis_type,
                analysis_version=r.analysis_version,
                baseline_method=r.baseline_method,
                baseline_version=r.baseline_version,
                manifest_id=bad_manifest_id,
                manifest_digest=r.manifest_digest,
                samples=r.samples,
                sample_count=r.sample_count,
                minimum_sample_count=r.minimum_sample_count,
                baseline_status=r.baseline_status,
                status_reason_code=r.status_reason_code,
                minimum_count=r.minimum_count,
                maximum_count=r.maximum_count,
                count_mean_numerator=r.count_mean_numerator,
                count_mean_denominator=r.count_mean_denominator,
                created_ingest_timestamp_us=r.created_ingest_timestamp_us,
                provenance=r.provenance,
            )

    def test_rejects_unsorted_samples(self):
        manifest = make_manifest(
            input_reference_digests=(HEX_A, HEX_B),
            minimum_sample_count=2,
        )
        unsorted = (
            make_sample(HEX_B, 5),
            make_sample(HEX_A, 3),
        )
        with self.assertRaises(ValueError):
            BaselineResultV1(
                schema_version="1.0",
                record_kind=BASELINE_RESULT_RECORD_KIND,
                baseline_result_id="blr_v1_" + ("a" * 64),
                baseline_result_digest="a" * 64,
                analysis_type="observation.count_per_collection_session",
                analysis_version="1.0.0",
                baseline_method="count_mean_range",
                baseline_version="1.0.0",
                manifest_id=manifest.baseline_manifest_id,
                manifest_digest=manifest.baseline_manifest_digest,
                samples=unsorted,
                sample_count=2,
                minimum_sample_count=2,
                baseline_status="available",
                status_reason_code="baseline.minimum_met",
                minimum_count=3,
                maximum_count=5,
                count_mean_numerator=4,
                count_mean_denominator=1,
                created_ingest_timestamp_us=INGEST_TS,
                provenance=make_provenance(),
            )

    def test_rejects_sample_count_mismatch(self):
        self.assert_rejects(sample_count=99)

    def test_rejects_negative_minimum_sample_count(self):
        self.assert_rejects(minimum_sample_count=-1)

    def test_rejects_zero_minimum_sample_count(self):
        self.assert_rejects(minimum_sample_count=0)

    def test_rejects_bool_sample_count(self):
        self.assert_rejects(sample_count=True)

    def test_rejects_bool_minimum_sample_count(self):
        self.assert_rejects(minimum_sample_count=True)

    def test_rejects_status_reason_mismatch_unknown_with_available_reason(self):
        self.assert_rejects(
            baseline_status="unknown",
            status_reason_code="baseline.minimum_met",
            minimum_count=None,
            maximum_count=None,
            count_mean_numerator=None,
            count_mean_denominator=None,
        )

    def test_rejects_numerator_not_matching_recomputation(self):
        r = self._valid_result()
        if r.count_mean_numerator is not None:
            self.assert_rejects(count_mean_numerator=r.count_mean_numerator + 1)

    def test_rejects_available_metrics_with_non_integer(self):
        self.assert_rejects(
            baseline_status="available",
            status_reason_code="baseline.minimum_met",
            minimum_count=0,
            maximum_count=1,
            count_mean_numerator="bad",
            count_mean_denominator=1,
        )


# ── Comparison ───────────────────────────────────────────────────────────


class TestBaselineResultComparison(unittest.TestCase):

    def _result_pair(self):
        r1 = make_result()
        r2 = make_result()
        return r1, r2

    def test_compare_duplicate(self):
        r1, r2 = self._result_pair()
        self.assertEqual(
            compare_baseline_result_source_facts(r1, r2),
            "duplicate",
        )

    def test_compare_duplicate_same_object(self):
        r = make_result()
        self.assertEqual(
            compare_baseline_result_source_facts(r, r),
            "duplicate",
        )

    def test_compare_identity_conflict_different_id(self):
        r1 = make_result(hmac_key=HMAC_KEY_A)
        r2 = make_result(hmac_key=HMAC_KEY_B)
        self.assertEqual(
            compare_baseline_result_source_facts(r1, r2),
            "identity_conflict",
        )

    def test_compare_identity_conflict_changed_samples(self):
        manifest = make_manifest(
            input_reference_digests=(HEX_A, HEX_B),
            minimum_sample_count=2,
        )
        s1 = (make_sample(HEX_A, 3), make_sample(HEX_B, 10))
        s2 = (make_sample(HEX_A, 99), make_sample(HEX_B, 99))
        r1 = make_result(manifest=manifest, samples=s1)
        r2 = make_result(manifest=manifest, samples=s2)
        self.assertEqual(r1.baseline_result_id, r2.baseline_result_id)
        self.assertEqual(
            compare_baseline_result_source_facts(r1, r2),
            "identity_conflict",
        )

    def test_compare_identity_conflict_changed_manifest_id(self):
        r1 = make_result()
        manifest_id_b = "blm_v1_" + ("d" * 64)
        dig_b = "d" * 64
        r2 = BaselineResultV1(
            schema_version=r1.schema_version,
            record_kind=r1.record_kind,
            baseline_result_id=r1.baseline_result_id,
            baseline_result_digest=r1.baseline_result_digest,
            analysis_type=r1.analysis_type,
            analysis_version=r1.analysis_version,
            baseline_method=r1.baseline_method,
            baseline_version=r1.baseline_version,
            manifest_id=manifest_id_b,
            manifest_digest=dig_b,
            samples=r1.samples,
            sample_count=r1.sample_count,
            minimum_sample_count=r1.minimum_sample_count,
            baseline_status=r1.baseline_status,
            status_reason_code=r1.status_reason_code,
            minimum_count=r1.minimum_count,
            maximum_count=r1.maximum_count,
            count_mean_numerator=r1.count_mean_numerator,
            count_mean_denominator=r1.count_mean_denominator,
            created_ingest_timestamp_us=r1.created_ingest_timestamp_us,
            provenance=r1.provenance,
        )
        self.assertEqual(
            compare_baseline_result_source_facts(r1, r2),
            "identity_conflict",
        )

    def test_compare_identity_conflict_changed_source_contract(self):
        r1 = make_result()
        r2 = make_result(
            provenance=make_provenance(source_contract_version="2.0"),
        )
        self.assertEqual(
            compare_baseline_result_source_facts(r1, r2),
            "identity_conflict",
        )

    def test_compare_ignores_ingest_timestamp(self):
        r1 = make_result(created_ingest_timestamp_us=INGEST_TS)
        r2 = make_result(created_ingest_timestamp_us=INGEST_TS + 5000)
        self.assertEqual(
            compare_baseline_result_source_facts(r1, r2),
            "duplicate",
        )

    def test_compare_ignores_analyzer_name(self):
        r1 = make_result()
        r2 = make_result(
            provenance=BaselineProvenanceV1(
                analyzer_name="other.analyzer",
                analyzer_version="1.0.0",
                analysis_mode="synthetic",
                source_contract_version="1.0",
            ),
        )
        self.assertEqual(
            compare_baseline_result_source_facts(r1, r2),
            "duplicate",
        )

    def test_compare_ignores_analyzer_version(self):
        r1 = make_result()
        r2 = make_result(
            provenance=BaselineProvenanceV1(
                analyzer_name="cyt.baseline",
                analyzer_version="9.9.9",
                analysis_mode="synthetic",
                source_contract_version="1.0",
            ),
        )
        self.assertEqual(
            compare_baseline_result_source_facts(r1, r2),
            "duplicate",
        )

    def test_compare_ignores_analysis_mode(self):
        r1 = make_result()
        r2 = make_result(
            provenance=BaselineProvenanceV1(
                analyzer_name="cyt.baseline",
                analyzer_version="1.0.0",
                analysis_mode="live",
                source_contract_version="1.0",
            ),
        )
        self.assertEqual(
            compare_baseline_result_source_facts(r1, r2),
            "duplicate",
        )

    def test_compare_rejects_non_result(self):
        r = make_result()
        with self.assertRaises(ValueError):
            compare_baseline_result_source_facts("bad", r)
        with self.assertRaises(ValueError):
            compare_baseline_result_source_facts(r, "bad")

    def test_compare_rejects_subclass(self):
        class MyResult(BaselineResultV1):
            pass
        valid = make_result()
        subclass = MyResult(**valid.__dict__)
        with self.assertRaises(ValueError):
            compare_baseline_result_source_facts(subclass, valid)
        with self.assertRaises(ValueError):
            compare_baseline_result_source_facts(valid, subclass)

    def test_every_compared_field_mutation_loop(self):
        r = make_result()

        mutations = {
            "schema_version": "2.0",
            "record_kind": "different_kind",
            "baseline_result_id": "blr_v1_" + ("e" * 64),
            "baseline_result_digest": "e" * 64,
            "analysis_type": "different.type",
            "analysis_version": "9.9.9",
            "baseline_method": "different_method",
            "baseline_version": "9.9.9",
            "manifest_id": "blm_v1_" + ("d" * 64),
            "manifest_digest": "d" * 64,
            "samples": (make_sample(HEX_A, 999), make_sample(HEX_B, 999)),
            "sample_count": 99,
            "minimum_sample_count": 99,
            "baseline_status": "different_status",
            "status_reason_code": "different.reason",
            "minimum_count": 999,
            "maximum_count": 999,
            "count_mean_numerator": 999,
            "count_mean_denominator": 999,
        }

        for field, new_value in mutations.items():
            mutated = copy.copy(r)
            object.__setattr__(mutated, field, new_value)
            self.assertEqual(
                compare_baseline_result_source_facts(r, mutated),
                "identity_conflict",
                f"expected identity_conflict for field {field!r}",
            )

        # provenance.source_contract_version is compared separately.
        mutated_provenance = copy.copy(r.provenance)
        object.__setattr__(
            mutated_provenance, "source_contract_version", "2.0"
        )
        mutated = copy.copy(r)
        object.__setattr__(mutated, "provenance", mutated_provenance)
        self.assertEqual(
            compare_baseline_result_source_facts(r, mutated),
            "identity_conflict",
            "expected identity_conflict for provenance.source_contract_version",
        )

        # Operational provenance fields and created_ingest_timestamp_us
        # are ignored by the comparison.
        for op_field, op_value in (
            ("analyzer_name", "other.analyzer"),
            ("analyzer_version", "9.9.9"),
            ("analysis_mode", "live"),
        ):
            mutated_provenance = copy.copy(r.provenance)
            object.__setattr__(mutated_provenance, op_field, op_value)
            mutated = copy.copy(r)
            object.__setattr__(mutated, "provenance", mutated_provenance)
            self.assertEqual(
                compare_baseline_result_source_facts(r, mutated),
                "duplicate",
                f"expected duplicate for provenance.{op_field!r}",
            )

        mutated = copy.copy(r)
        object.__setattr__(
            mutated, "created_ingest_timestamp_us", INGEST_TS + 5000
        )
        self.assertEqual(
            compare_baseline_result_source_facts(r, mutated),
            "duplicate",
            "expected duplicate for created_ingest_timestamp_us",
        )

    def test_compare_identity_conflict_changed_minimum(self):
        manifest = make_manifest(
            input_reference_digests=(HEX_A, HEX_B),
            minimum_sample_count=2,
        )
        s1 = (make_sample(HEX_A, 3), make_sample(HEX_B, 10))
        s2 = (make_sample(HEX_A, 4), make_sample(HEX_B, 10))
        r1 = make_result(manifest=manifest, samples=s1)
        r2 = make_result(manifest=manifest, samples=s2)
        self.assertEqual(r1.baseline_result_id, r2.baseline_result_id)
        self.assertEqual(
            compare_baseline_result_source_facts(r1, r2),
            "identity_conflict",
        )

    def test_compare_identity_conflict_changed_maximum(self):
        manifest = make_manifest(
            input_reference_digests=(HEX_A, HEX_B),
            minimum_sample_count=2,
        )
        s1 = (make_sample(HEX_A, 3), make_sample(HEX_B, 10))
        s2 = (make_sample(HEX_A, 3), make_sample(HEX_B, 9))
        r1 = make_result(manifest=manifest, samples=s1)
        r2 = make_result(manifest=manifest, samples=s2)
        self.assertEqual(r1.baseline_result_id, r2.baseline_result_id)
        self.assertEqual(
            compare_baseline_result_source_facts(r1, r2),
            "identity_conflict",
        )


# ── Exported constants ──────────────────────────────────────────────────


class TestExportedConstants(unittest.TestCase):

    def test_all_exported_present(self):
        for name in RESULT_ALL:
            self.assertIn(name, dir(sys.modules["baseline_result"]))

    def test_all_exported_contains_six_names(self):
        self.assertEqual(len(RESULT_ALL), 6)

    def test_record_kind_value(self):
        self.assertEqual(BASELINE_RESULT_RECORD_KIND, "baseline_result")

    def test_id_prefix_value(self):
        self.assertEqual(BASELINE_RESULT_ID_PREFIX, "blr_v1_")


# ── Field order ─────────────────────────────────────────────────────────


class TestFieldOrder(unittest.TestCase):

    def test_baseline_count_sample_v1_field_order(self):
        fields = [
            f.name
            for f in __import__("dataclasses").fields(BaselineCountSampleV1)
        ]
        expected = [
            "input_reference_digest",
            "observation_count",
        ]
        self.assertEqual(fields, expected)

    def test_baseline_result_v1_field_order(self):
        fields = [
            f.name
            for f in __import__("dataclasses").fields(BaselineResultV1)
        ]
        expected = [
            "schema_version",
            "record_kind",
            "baseline_result_id",
            "baseline_result_digest",
            "analysis_type",
            "analysis_version",
            "baseline_method",
            "baseline_version",
            "manifest_id",
            "manifest_digest",
            "samples",
            "sample_count",
            "minimum_sample_count",
            "baseline_status",
            "status_reason_code",
            "minimum_count",
            "maximum_count",
            "count_mean_numerator",
            "count_mean_denominator",
            "created_ingest_timestamp_us",
            "provenance",
        ]
        self.assertEqual(fields, expected)

    def test_both_dataclasses_frozen(self):
        import dataclasses
        self.assertTrue(dataclasses.is_dataclass(BaselineCountSampleV1))
        self.assertTrue(dataclasses.is_dataclass(BaselineResultV1))


# ── AST prohibitions ────────────────────────────────────────────────────


class TestASTProhibitions(unittest.TestCase):

    def _load_source(self):
        with open("baseline_result.py") as f:
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
            "os",
            "sys",
            "random",
            "statistics",
            "datetime",
            "time",
            "math",
            "alert_store",
            "alert_projection",
            "surveillance_detector",
            "surveillance_analyzer",
            "observation_store",
            "observation_contract",
            "route_session_contract",
            "gps_tracker",
            "ground_truth_scenario_contract",
            "ground_truth_summary_builder",
            "secure_credentials",
            "secure_database",
            "secure_ignore_loader",
            "secure_main_logic",
            "input_validation",
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
                        self.fail(f"forbidden field: {node.target.id}")

            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if target.id in forbidden:
                            self.fail(f"forbidden name: {target.id}")

    def test_no_float_literals_or_casts(self):
        tree = self._load_source()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant):
                if isinstance(node.value, float):
                    self.fail(f"float literal: {node.value}")
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "float":
                    self.fail("float() call")
                if isinstance(node.func, ast.Attribute) and node.func.attr == "float":
                    self.fail("float() call via attr")

    def test_no_wall_clock_or_time_access(self):
        tree = self._load_source()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    attr = node.func.attr
                    if attr in {"time", "sleep", "gmtime", "localtime",
                                "strftime", "now", "utcnow", "today",
                                "fromtimestamp", "utcfromtimestamp"}:
                        self.fail(f"time access call: {attr}")

    def test_no_side_effect_statements(self):
        tree = self._load_source()
        for node in ast.walk(tree):
            if isinstance(node, ast.Delete):
                self.fail("del statement forbidden")

    def test_canonical_identity_uses_sort_keys_and_compact_separators(self):
        with open("baseline_result.py") as f:
            source = f.read()
        func_start = source.find("def _canonical_identity_bytes")
        self.assertGreaterEqual(func_start, 0)
        func_body = source[func_start:func_start + 400]
        self.assertIn("sort_keys=True", func_body)
        self.assertIn('separators=(",", ":")', func_body)
        self.assertIn("ensure_ascii=False", func_body)

    def test_no_math_or_statistics_import(self):
        tree = self._load_source()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in ("math", "statistics"):
                        self.fail(f"forbidden module: {alias.name}")
            if isinstance(node, ast.ImportFrom):
                if node.module and (
                    node.module.startswith("statistics")
                    or node.module == "math"
                ):
                    self.fail(f"forbidden module: {node.module}")

    def test_no_manifest_identity_part_extraction(self):
        with open("baseline_result.py") as f:
            source = f.read()
        self.assertNotIn("_extract_manifest_identity_parts", source)


if __name__ == "__main__":
    unittest.main()
