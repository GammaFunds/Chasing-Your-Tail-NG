"""Baseline Result v1 — pure immutable count-baseline calculator."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import re
from typing import Optional, Tuple

from baseline_contract import (
    BASELINE_STATUSES,
    BaselineManifestV1,
    BaselineProvenanceV1,
    compare_baseline_manifest_source_facts,
    create_baseline_manifest,
)

BASELINE_RESULT_RECORD_KIND = "baseline_result"
BASELINE_RESULT_ID_PREFIX = "blr_v1_"

_SCHEMA_VERSION = "1.0"
_SUPPORTED_ANALYSIS_TYPE = "observation.count_per_collection_session"
_SUPPORTED_ANALYSIS_VERSION = "1.0.0"
_SUPPORTED_BASELINE_METHOD = "count_mean_range"
_SUPPORTED_BASELINE_VERSION = "1.0.0"
_MAX_COUNT = (1 << 63) - 1

_BLR_ID_RE = re.compile(r"^blr_v1_[0-9a-f]{64}$")
_BLM_ID_RE = re.compile(r"^blm_v1_[0-9a-f]{64}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")

_DUPLICATE = "duplicate"
_IDENTITY_CONFLICT = "identity_conflict"


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a


def _reduce_fraction(numerator: int, denominator: int) -> Tuple[int, int]:
    if denominator < 0:
        numerator = -numerator
        denominator = -denominator
    if numerator == 0:
        return (0, 1)
    g = _gcd(abs(numerator), abs(denominator))
    return (numerator // g, denominator // g)


def _canonical_identity_bytes(parts: Tuple[str, ...]) -> bytes:
    return json.dumps(
        list(parts),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _derive_hmac_digest(hmac_key: bytes, parts: Tuple[str, ...]) -> str:
    if not isinstance(hmac_key, bytes) or not hmac_key:
        raise ValueError()
    return hmac.new(
        hmac_key,
        _canonical_identity_bytes(parts),
        hashlib.sha256,
    ).hexdigest()


@dataclass(frozen=True)
class BaselineCountSampleV1:
    input_reference_digest: str
    observation_count: int

    def __post_init__(self) -> None:
        v = self.input_reference_digest
        if not isinstance(v, str) or not v or v != v.strip():
            raise ValueError()
        if _DIGEST_RE.fullmatch(v) is None:
            raise ValueError()

        c = self.observation_count
        if isinstance(c, bool) or not isinstance(c, int) or c < 0 or c > _MAX_COUNT:
            raise ValueError()


@dataclass(frozen=True)
class BaselineResultV1:
    schema_version: str
    record_kind: str
    baseline_result_id: str
    baseline_result_digest: str
    analysis_type: str
    analysis_version: str
    baseline_method: str
    baseline_version: str
    manifest_id: str
    manifest_digest: str
    samples: Tuple[BaselineCountSampleV1, ...]
    sample_count: int
    minimum_sample_count: int
    baseline_status: str
    status_reason_code: str
    minimum_count: Optional[int]
    maximum_count: Optional[int]
    count_mean_numerator: Optional[int]
    count_mean_denominator: Optional[int]
    created_ingest_timestamp_us: int
    provenance: BaselineProvenanceV1

    def __post_init__(self) -> None:
        if self.schema_version != _SCHEMA_VERSION:
            raise ValueError()

        if self.record_kind != BASELINE_RESULT_RECORD_KIND:
            raise ValueError()

        if _BLR_ID_RE.fullmatch(self.baseline_result_id) is None:
            raise ValueError()

        if self.baseline_result_id[-64:] != self.baseline_result_digest:
            raise ValueError()

        if _DIGEST_RE.fullmatch(self.baseline_result_digest) is None:
            raise ValueError()

        if self.analysis_type != _SUPPORTED_ANALYSIS_TYPE:
            raise ValueError()

        if self.analysis_version != _SUPPORTED_ANALYSIS_VERSION:
            raise ValueError()

        if self.baseline_method != _SUPPORTED_BASELINE_METHOD:
            raise ValueError()

        if self.baseline_version != _SUPPORTED_BASELINE_VERSION:
            raise ValueError()

        if _BLM_ID_RE.fullmatch(self.manifest_id) is None:
            raise ValueError()

        if self.manifest_id[-64:] != self.manifest_digest:
            raise ValueError()

        if _DIGEST_RE.fullmatch(self.manifest_digest) is None:
            raise ValueError()

        if type(self.samples) is not tuple:
            raise ValueError()

        prev_digest = ""
        for s in self.samples:
            if type(s) is not BaselineCountSampleV1:
                raise ValueError()
            d = s.input_reference_digest
            if d <= prev_digest:
                raise ValueError()
            prev_digest = d

        sc = self.sample_count
        if isinstance(sc, bool) or not isinstance(sc, int) or sc < 0:
            raise ValueError()
        if sc != len(self.samples):
            raise ValueError()

        msc = self.minimum_sample_count
        if isinstance(msc, bool) or not isinstance(msc, int) or msc <= 0:
            raise ValueError()

        if self.baseline_status not in BASELINE_STATUSES:
            raise ValueError()

        v = self.status_reason_code
        if not isinstance(v, str) or not v or v != v.strip():
            raise ValueError()

        expected_status, expected_reason = _compute_baseline_status(
            self.sample_count, self.minimum_sample_count
        )
        if self.baseline_status != expected_status:
            raise ValueError()
        if self.status_reason_code != expected_reason:
            raise ValueError()

        if self.baseline_status == "available":
            for val in (
                self.minimum_count,
                self.maximum_count,
                self.count_mean_numerator,
                self.count_mean_denominator,
            ):
                if isinstance(val, bool) or not isinstance(val, int):
                    raise ValueError()

            counts = tuple(s.observation_count for s in self.samples)
            calc_min = min(counts)
            calc_max = max(counts)
            total = sum(counts)
            n = len(counts)
            calc_num, calc_den = _reduce_fraction(total, n)

            if self.minimum_count != calc_min:
                raise ValueError()
            if self.maximum_count != calc_max:
                raise ValueError()
            if self.count_mean_numerator != calc_num:
                raise ValueError()
            if self.count_mean_denominator != calc_den:
                raise ValueError()
        else:
            if self.minimum_count is not None:
                raise ValueError()
            if self.maximum_count is not None:
                raise ValueError()
            if self.count_mean_numerator is not None:
                raise ValueError()
            if self.count_mean_denominator is not None:
                raise ValueError()

        ts = self.created_ingest_timestamp_us
        if isinstance(ts, bool) or not isinstance(ts, int) or ts < 0:
            raise ValueError()

        if type(self.provenance) is not BaselineProvenanceV1:
            raise ValueError()


def _compute_baseline_status(
    sample_count: int, minimum_sample_count: int
) -> Tuple[str, str]:
    if sample_count == 0:
        return ("unknown", "baseline.no_samples")
    if sample_count < minimum_sample_count:
        return ("insufficient_data", "baseline.minimum_not_met")
    return ("available", "baseline.minimum_met")


def create_baseline_result(
    *,
    hmac_key: bytes,
    manifest: BaselineManifestV1,
    samples: Tuple[BaselineCountSampleV1, ...],
    created_ingest_timestamp_us: int,
    provenance: BaselineProvenanceV1,
) -> BaselineResultV1:
    if not isinstance(hmac_key, bytes) or not hmac_key:
        raise ValueError()

    if type(manifest) is not BaselineManifestV1:
        raise ValueError()

    if manifest.analysis_type != _SUPPORTED_ANALYSIS_TYPE:
        raise ValueError()

    if manifest.analysis_version != _SUPPORTED_ANALYSIS_VERSION:
        raise ValueError()

    if manifest.baseline_method != _SUPPORTED_BASELINE_METHOD:
        raise ValueError()

    if manifest.baseline_version != _SUPPORTED_BASELINE_VERSION:
        raise ValueError()

    if type(samples) is not tuple:
        raise ValueError()

    seen = set()
    for s in samples:
        if type(s) is not BaselineCountSampleV1:
            raise ValueError()
        if s.input_reference_digest in seen:
            raise ValueError()
        seen.add(s.input_reference_digest)

    canonical_samples = tuple(
        sorted(samples, key=lambda x: x.input_reference_digest)
    )
    sample_digests = tuple(s.input_reference_digest for s in canonical_samples)
    if sample_digests != manifest.input_reference_digests:
        raise ValueError()

    reconstructed = create_baseline_manifest(
        hmac_key=hmac_key,
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
        input_reference_digests=manifest.input_reference_digests,
        minimum_sample_count=manifest.minimum_sample_count,
        created_ingest_timestamp_us=manifest.created_ingest_timestamp_us,
        provenance=manifest.provenance,
    )
    cmp_result = compare_baseline_manifest_source_facts(
        reconstructed, manifest
    )
    if cmp_result != _DUPLICATE:
        raise ValueError()

    if type(provenance) is not BaselineProvenanceV1:
        raise ValueError()

    ts = created_ingest_timestamp_us
    if isinstance(ts, bool) or not isinstance(ts, int) or ts < 0:
        raise ValueError()

    result_identity_parts = ("blr_v1", manifest.baseline_manifest_digest)
    result_digest = _derive_hmac_digest(hmac_key, result_identity_parts)
    result_id = f"{BASELINE_RESULT_ID_PREFIX}{result_digest}"

    sample_count = len(canonical_samples)
    minimum_sample_count = manifest.minimum_sample_count
    status, reason = manifest.baseline_status, manifest.status_reason_code

    if status == "available":
        counts = tuple(s.observation_count for s in canonical_samples)
        min_count = min(counts)
        max_count = max(counts)
        total = sum(counts)
        n = len(counts)
        num, den = _reduce_fraction(total, n)
    else:
        min_count = None
        max_count = None
        num = None
        den = None

    return BaselineResultV1(
        schema_version=_SCHEMA_VERSION,
        record_kind=BASELINE_RESULT_RECORD_KIND,
        baseline_result_id=result_id,
        baseline_result_digest=result_digest,
        analysis_type=_SUPPORTED_ANALYSIS_TYPE,
        analysis_version=_SUPPORTED_ANALYSIS_VERSION,
        baseline_method=_SUPPORTED_BASELINE_METHOD,
        baseline_version=_SUPPORTED_BASELINE_VERSION,
        manifest_id=manifest.baseline_manifest_id,
        manifest_digest=manifest.baseline_manifest_digest,
        samples=canonical_samples,
        sample_count=sample_count,
        minimum_sample_count=minimum_sample_count,
        baseline_status=status,
        status_reason_code=reason,
        minimum_count=min_count,
        maximum_count=max_count,
        count_mean_numerator=num,
        count_mean_denominator=den,
        created_ingest_timestamp_us=ts,
        provenance=provenance,
    )


def compare_baseline_result_source_facts(
    existing: BaselineResultV1,
    incoming: BaselineResultV1,
) -> str:
    if type(existing) is not BaselineResultV1:
        raise ValueError()

    if type(incoming) is not BaselineResultV1:
        raise ValueError()

    if existing.baseline_result_id != incoming.baseline_result_id:
        return _IDENTITY_CONFLICT

    fields = (
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
    )

    existing_facts = tuple(getattr(existing, f) for f in fields)
    incoming_facts = tuple(getattr(incoming, f) for f in fields)

    if existing_facts != incoming_facts:
        return _IDENTITY_CONFLICT

    if (
        existing.provenance.source_contract_version
        != incoming.provenance.source_contract_version
    ):
        return _IDENTITY_CONFLICT

    return _DUPLICATE


__all__ = [
    "BASELINE_RESULT_RECORD_KIND",
    "BASELINE_RESULT_ID_PREFIX",
    "BaselineCountSampleV1",
    "BaselineResultV1",
    "create_baseline_result",
    "compare_baseline_result_source_facts",
]
