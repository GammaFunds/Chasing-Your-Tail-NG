"""Baseline Manifest v1 — pure immutable contract."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import re
from typing import Tuple


BASELINE_MANIFEST_RECORD_KIND = "baseline_manifest"

BASELINE_STATUSES = frozenset({"available", "insufficient_data", "unknown"})

_ANALYSIS_MODES = frozenset({"live", "replay", "synthetic"})
_BASELINE_MANIFEST_ID_PREFIX = "blm_v1_"
_SCHEMA_VERSION_V1 = "1.0"
_TIME_BASIS = "source_timestamp_us"
_BOUNDARY_POLICY = "half_open"

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_MANIFEST_ID_RE = re.compile(
    rf"^{_BASELINE_MANIFEST_ID_PREFIX}[0-9a-f]{{64}}$"
)

_DUPLICATE = "duplicate"
_IDENTITY_CONFLICT = "identity_conflict"


def _require_text(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")

    if not value or value != value.strip():
        raise ValueError(f"{name} must be a non-empty canonical string")

    return value


def _require_timestamp_us(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(
            f"{name} must be a non-negative integer Unix timestamp "
            "in microseconds"
        )

    return value


def _require_digest(name: str, value: object) -> str:
    text = _require_text(name, value)

    if _DIGEST_RE.fullmatch(text) is None:
        raise ValueError(f"{name} must be a 64-character hex digest")

    return text


def _require_positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")

    return value


def _require_hmac_key(hmac_key: object) -> bytes:
    if not isinstance(hmac_key, bytes) or not hmac_key:
        raise ValueError("hmac_key must be non-empty bytes")

    return hmac_key


def _canonical_identity_bytes(parts: tuple[str, ...]) -> bytes:
    return json.dumps(
        list(parts),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _derive_hmac_digest(
    hmac_key: bytes,
    parts: tuple[str, ...],
) -> str:
    return hmac.new(
        _require_hmac_key(hmac_key),
        _canonical_identity_bytes(parts),
        hashlib.sha256,
    ).hexdigest()


def _compute_baseline_status(
    sample_count: int,
    minimum_sample_count: int,
) -> tuple[str, str]:
    if sample_count == 0:
        return ("unknown", "baseline.no_samples")

    if sample_count < minimum_sample_count:
        return ("insufficient_data", "baseline.minimum_not_met")

    return ("available", "baseline.minimum_met")


@dataclass(frozen=True)
class BaselineProvenanceV1:
    analyzer_name: str
    analyzer_version: str
    analysis_mode: str
    source_contract_version: str

    def __post_init__(self) -> None:
        _require_text("analyzer_name", self.analyzer_name)
        _require_text("analyzer_version", self.analyzer_version)

        _require_text("analysis_mode", self.analysis_mode)

        if self.analysis_mode not in _ANALYSIS_MODES:
            raise ValueError(
                "analysis_mode must be live, replay, or synthetic"
            )

        _require_text(
            "source_contract_version", self.source_contract_version
        )


@dataclass(frozen=True)
class BaselineManifestV1:
    schema_version: str
    record_kind: str
    baseline_manifest_id: str
    baseline_manifest_digest: str
    analysis_type: str
    analysis_version: str
    baseline_method: str
    baseline_version: str
    subject_kind: str
    subject_reference: str
    window_start_source_timestamp_us: int
    window_end_source_timestamp_us: int
    time_basis: str
    boundary_policy: str
    input_reference_digests: tuple[str, ...]
    sample_count: int
    minimum_sample_count: int
    baseline_status: str
    status_reason_code: str
    created_ingest_timestamp_us: int
    provenance: BaselineProvenanceV1

    def __post_init__(self) -> None:
        if self.schema_version != _SCHEMA_VERSION_V1:
            raise ValueError('schema_version must be exactly "1.0"')

        if self.record_kind != BASELINE_MANIFEST_RECORD_KIND:
            raise ValueError(
                'record_kind must be exactly "baseline_manifest"'
            )

        if _MANIFEST_ID_RE.fullmatch(self.baseline_manifest_id) is None:
            raise ValueError("invalid baseline_manifest_id")

        _require_digest(
            "baseline_manifest_digest", self.baseline_manifest_digest
        )

        if self.baseline_manifest_id[-64:] != self.baseline_manifest_digest:
            raise ValueError(
                "baseline_manifest_digest must equal ID suffix"
            )

        _require_text("analysis_type", self.analysis_type)
        _require_text("analysis_version", self.analysis_version)
        _require_text("baseline_method", self.baseline_method)
        _require_text("baseline_version", self.baseline_version)
        _require_text("subject_kind", self.subject_kind)
        _require_digest("subject_reference", self.subject_reference)

        _require_timestamp_us(
            "window_start_source_timestamp_us",
            self.window_start_source_timestamp_us,
        )
        _require_timestamp_us(
            "window_end_source_timestamp_us",
            self.window_end_source_timestamp_us,
        )

        if (
            self.window_start_source_timestamp_us
            >= self.window_end_source_timestamp_us
        ):
            raise ValueError(
                "window_start must be strictly less than window_end"
            )

        if self.time_basis != _TIME_BASIS:
            raise ValueError(
                'time_basis must be exactly "source_timestamp_us"'
            )

        if self.boundary_policy != _BOUNDARY_POLICY:
            raise ValueError(
                'boundary_policy must be exactly "half_open"'
            )

        if type(self.input_reference_digests) is not tuple:
            raise ValueError(
                "input_reference_digests must be exactly tuple"
            )

        for ref in self.input_reference_digests:
            _require_digest("input_reference_digest", ref)

        if (
            tuple(sorted(self.input_reference_digests))
            != self.input_reference_digests
        ):
            raise ValueError("input_reference_digests must be sorted")

        if (
            len(set(self.input_reference_digests))
            != len(self.input_reference_digests)
        ):
            raise ValueError(
                "input_reference_digests must not contain duplicates"
            )

        if (
            isinstance(self.sample_count, bool)
            or not isinstance(self.sample_count, int)
            or self.sample_count < 0
        ):
            raise ValueError("sample_count must be a non-negative integer")

        if self.sample_count != len(self.input_reference_digests):
            raise ValueError(
                "sample_count must equal len(input_reference_digests)"
            )

        _require_positive_int(
            "minimum_sample_count", self.minimum_sample_count
        )

        expected_status, expected_reason = _compute_baseline_status(
            self.sample_count,
            self.minimum_sample_count,
        )

        if self.baseline_status != expected_status:
            raise ValueError(
                f"baseline_status must be {expected_status!r}"
            )

        if self.status_reason_code != expected_reason:
            raise ValueError(
                f"status_reason_code must be {expected_reason!r}"
            )

        _require_timestamp_us(
            "created_ingest_timestamp_us",
            self.created_ingest_timestamp_us,
        )

        if type(self.provenance) is not BaselineProvenanceV1:
            raise ValueError(
                "provenance must be exactly BaselineProvenanceV1"
            )


def create_baseline_manifest(
    *,
    hmac_key: bytes,
    analysis_type: str,
    analysis_version: str,
    baseline_method: str,
    baseline_version: str,
    subject_kind: str,
    subject_reference: str,
    window_start_source_timestamp_us: int,
    window_end_source_timestamp_us: int,
    input_reference_digests: tuple[str, ...],
    minimum_sample_count: int,
    created_ingest_timestamp_us: int,
    provenance: BaselineProvenanceV1,
) -> BaselineManifestV1:
    _require_hmac_key(hmac_key)

    if type(input_reference_digests) is not tuple:
        raise ValueError(
            "input_reference_digests must be exactly tuple"
        )

    normalized_analysis_type = _require_text("analysis_type", analysis_type)
    normalized_analysis_version = _require_text(
        "analysis_version", analysis_version
    )
    normalized_baseline_method = _require_text(
        "baseline_method", baseline_method
    )
    normalized_baseline_version = _require_text(
        "baseline_version", baseline_version
    )
    normalized_subject_kind = _require_text("subject_kind", subject_kind)
    normalized_subject_reference = _require_digest(
        "subject_reference", subject_reference
    )

    _require_timestamp_us(
        "window_start_source_timestamp_us",
        window_start_source_timestamp_us,
    )
    _require_timestamp_us(
        "window_end_source_timestamp_us",
        window_end_source_timestamp_us,
    )

    if window_start_source_timestamp_us >= window_end_source_timestamp_us:
        raise ValueError(
            "window_start must be strictly less than window_end"
        )

    normalized_refs: list[str] = []
    for ref in input_reference_digests:
        normalized_ref = _require_digest("input_reference_digest", ref)
        normalized_refs.append(normalized_ref)

    if len(set(normalized_refs)) != len(normalized_refs):
        raise ValueError(
            "input_reference_digests must not contain duplicates"
        )

    canonical_refs = tuple(sorted(normalized_refs))
    sample_count = len(canonical_refs)

    normalized_minimum = _require_positive_int(
        "minimum_sample_count", minimum_sample_count
    )

    _require_timestamp_us(
        "created_ingest_timestamp_us", created_ingest_timestamp_us
    )

    if type(provenance) is not BaselineProvenanceV1:
        raise ValueError(
            "provenance must be exactly BaselineProvenanceV1"
        )

    baseline_status, status_reason_code = _compute_baseline_status(
        sample_count, normalized_minimum
    )

    identity_parts = (
        normalized_analysis_type,
        normalized_analysis_version,
        normalized_baseline_method,
        normalized_baseline_version,
        normalized_subject_kind,
        normalized_subject_reference,
        provenance.source_contract_version,
        str(window_start_source_timestamp_us),
        str(window_end_source_timestamp_us),
        _TIME_BASIS,
        _BOUNDARY_POLICY,
        *canonical_refs,
        str(normalized_minimum),
    )

    digest = _derive_hmac_digest(hmac_key, identity_parts)
    manifest_id = f"{_BASELINE_MANIFEST_ID_PREFIX}{digest}"

    return BaselineManifestV1(
        schema_version=_SCHEMA_VERSION_V1,
        record_kind=BASELINE_MANIFEST_RECORD_KIND,
        baseline_manifest_id=manifest_id,
        baseline_manifest_digest=digest,
        analysis_type=normalized_analysis_type,
        analysis_version=normalized_analysis_version,
        baseline_method=normalized_baseline_method,
        baseline_version=normalized_baseline_version,
        subject_kind=normalized_subject_kind,
        subject_reference=normalized_subject_reference,
        window_start_source_timestamp_us=window_start_source_timestamp_us,
        window_end_source_timestamp_us=window_end_source_timestamp_us,
        time_basis=_TIME_BASIS,
        boundary_policy=_BOUNDARY_POLICY,
        input_reference_digests=canonical_refs,
        sample_count=sample_count,
        minimum_sample_count=normalized_minimum,
        baseline_status=baseline_status,
        status_reason_code=status_reason_code,
        created_ingest_timestamp_us=created_ingest_timestamp_us,
        provenance=provenance,
    )


def compare_baseline_manifest_source_facts(
    existing: BaselineManifestV1,
    incoming: BaselineManifestV1,
) -> str:
    if type(existing) is not BaselineManifestV1:
        raise ValueError(
            "existing must be exactly BaselineManifestV1"
        )

    if type(incoming) is not BaselineManifestV1:
        raise ValueError(
            "incoming must be exactly BaselineManifestV1"
        )

    if existing.baseline_manifest_id != incoming.baseline_manifest_id:
        return _IDENTITY_CONFLICT

    fields = (
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
    "BASELINE_MANIFEST_RECORD_KIND",
    "BASELINE_STATUSES",
    "BaselineProvenanceV1",
    "BaselineManifestV1",
    "create_baseline_manifest",
    "compare_baseline_manifest_source_facts",
]
