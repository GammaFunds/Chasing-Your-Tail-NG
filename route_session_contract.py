"""Immutable, source-neutral route/session contract version 1.0."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import re
from typing import Optional, Sequence

from observation_contract import OperatorFixV1


SCHEMA_VERSION_V1 = "1.0"

COLLECTION_SESSION_RECORD_KIND = "collection_session"
COLLECTION_SOURCE_MEMBERSHIP_RECORD_KIND = "collection_source_membership"
COLLECTION_SOURCE_MEMBERSHIP_CLOSE_RECORD_KIND = "collection_source_membership_close"
COLLECTION_SESSION_CLOSE_RECORD_KIND = "collection_session_close"
ROUTE_RECORD_KIND = "route"
ANALYSIS_SESSION_RECORD_KIND = "analysis_session"

TIME_BASIS = "source_timestamp_us"
BOUNDARY_POLICY = "explicit_half_open_v1"
ROUTE_METHOD = "operator_fix_gap_partition"
ROUTE_VERSION_V1 = "1.0"

MEMBERSHIP_CLOSE_REASONS = frozenset({"normal", "source_restart", "source_failure", "session_closed", "aborted"})
SESSION_CLOSE_REASONS = frozenset({"completed", "operator_closed", "aborted", "clock_invalid"})

_SOURCE_TYPE_RE = re.compile(
    r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+$"
)
_CSN_ID_RE = re.compile(r"^csn_v1_[0-9a-f]{64}$")
_CSM_ID_RE = re.compile(r"^csm_v1_[0-9a-f]{64}$")
_CMC_ID_RE = re.compile(r"^cmc_v1_[0-9a-f]{64}$")
_CSC_ID_RE = re.compile(r"^csc_v1_[0-9a-f]{64}$")
_RTE_ID_RE = re.compile(r"^rte_v1_[0-9a-f]{64}$")
_ASN_ID_RE = re.compile(r"^asn_v1_[0-9a-f]{64}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")

_DUPLICATE = "duplicate"
_IDENTITY_CONFLICT = "identity_conflict"


def _require_text(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")

    if not value or value != value.strip():
        raise ValueError(
            f"{name} must be a non-empty canonical string"
        )

    return value


def _require_source_type(value: object) -> str:
    source_type = _require_text("source_type", value)

    if _SOURCE_TYPE_RE.fullmatch(source_type) is None:
        raise ValueError(
            "source_type must be a lowercase namespaced value"
        )

    return source_type


def _require_timestamp_us(name: str, value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        raise ValueError(
            f"{name} must be a non-negative integer Unix timestamp "
            "in microseconds"
        )

    return value


def _require_non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")

    return value


def _require_hmac_key(hmac_key: object) -> bytes:
    if not isinstance(hmac_key, bytes) or not hmac_key:
        raise ValueError("hmac_key must be non-empty bytes")

    return hmac_key


def _canonical_identity_bytes(parts: tuple[str, ...]) -> bytes:
    return json.dumps(
        list(parts),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _derive_hmac_identifier(
    prefix: str,
    hmac_key: bytes,
    parts: tuple[str, ...],
) -> str:
    digest = hmac.new(
        _require_hmac_key(hmac_key),
        _canonical_identity_bytes(parts),
        hashlib.sha256,
    ).hexdigest()

    return f"{prefix}{digest}"


def _require_digest(name: str, value: object) -> str:
    text = _require_text(name, value)

    if _DIGEST_RE.fullmatch(text) is None:
        raise ValueError(f"{name} must be a 64-character hex digest")

    return text


@dataclass(frozen=True)
class RouteSessionProvenanceV1:
    """Non-secret provenance for route/session records."""

    controller_name: str
    controller_version: str
    operation_mode: str

    def __post_init__(self) -> None:
        _require_text("controller_name", self.controller_name)
        _require_text("controller_version", self.controller_version)

        if self.operation_mode not in {"session_control", "route_snapshot", "analysis"}:
            raise ValueError(
                "operation_mode must be session_control, route_snapshot, or analysis"
            )


@dataclass(frozen=True)
class CollectionSessionV1:
    """Immutable collection session record."""

    schema_version: str
    record_kind: str
    collection_session_id: str
    session_controller_id: str
    collection_session_reference: str
    opened_source_timestamp_us: int
    time_basis: str
    boundary_policy: str
    ingest_timestamp_us: int
    provenance: RouteSessionProvenanceV1

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION_V1:
            raise ValueError('schema_version must be exactly "1.0"')

        if self.record_kind != COLLECTION_SESSION_RECORD_KIND:
            raise ValueError(
                'record_kind must be exactly "collection_session"'
            )

        if _CSN_ID_RE.fullmatch(self.collection_session_id) is None:
            raise ValueError("invalid collection_session_id")

        _require_text("session_controller_id", self.session_controller_id)
        _require_text("collection_session_reference", self.collection_session_reference)
        _require_timestamp_us("opened_source_timestamp_us", self.opened_source_timestamp_us)

        if self.time_basis != TIME_BASIS:
            raise ValueError(f'time_basis must be exactly "{TIME_BASIS}"')

        if self.boundary_policy != BOUNDARY_POLICY:
            raise ValueError(f'boundary_policy must be exactly "{BOUNDARY_POLICY}"')

        _require_timestamp_us("ingest_timestamp_us", self.ingest_timestamp_us)

        if not isinstance(self.provenance, RouteSessionProvenanceV1):
            raise ValueError("provenance must be RouteSessionProvenanceV1")


@dataclass(frozen=True)
class CollectionSourceMembershipV1:
    """Immutable collection source membership record."""

    schema_version: str
    record_kind: str
    membership_id: str
    collection_session_id: str
    source_type: str
    sensor_id: str
    source_instance_reference: str
    joined_source_timestamp_us: int
    ingest_timestamp_us: int
    provenance: RouteSessionProvenanceV1

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION_V1:
            raise ValueError('schema_version must be exactly "1.0"')

        if self.record_kind != COLLECTION_SOURCE_MEMBERSHIP_RECORD_KIND:
            raise ValueError(
                'record_kind must be exactly "collection_source_membership"'
            )

        if _CSM_ID_RE.fullmatch(self.membership_id) is None:
            raise ValueError("invalid membership_id")

        _require_text("collection_session_id", self.collection_session_id)
        _require_source_type(self.source_type)
        _require_text("sensor_id", self.sensor_id)
        _require_text("source_instance_reference", self.source_instance_reference)
        _require_timestamp_us("joined_source_timestamp_us", self.joined_source_timestamp_us)
        _require_timestamp_us("ingest_timestamp_us", self.ingest_timestamp_us)

        if not isinstance(self.provenance, RouteSessionProvenanceV1):
            raise ValueError("provenance must be RouteSessionProvenanceV1")


@dataclass(frozen=True)
class CollectionSourceMembershipCloseV1:
    """Immutable collection source membership close record."""

    schema_version: str
    record_kind: str
    membership_close_id: str
    membership_id: str
    left_source_timestamp_us: int
    close_reason: str
    ingest_timestamp_us: int
    provenance: RouteSessionProvenanceV1

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION_V1:
            raise ValueError('schema_version must be exactly "1.0"')

        if self.record_kind != COLLECTION_SOURCE_MEMBERSHIP_CLOSE_RECORD_KIND:
            raise ValueError(
                'record_kind must be exactly "collection_source_membership_close"'
            )

        if _CMC_ID_RE.fullmatch(self.membership_close_id) is None:
            raise ValueError("invalid membership_close_id")

        _require_text("membership_id", self.membership_id)
        _require_timestamp_us("left_source_timestamp_us", self.left_source_timestamp_us)

        if self.close_reason not in MEMBERSHIP_CLOSE_REASONS:
            raise ValueError(
                f"close_reason must be one of {sorted(MEMBERSHIP_CLOSE_REASONS)}"
            )

        _require_timestamp_us("ingest_timestamp_us", self.ingest_timestamp_us)

        if not isinstance(self.provenance, RouteSessionProvenanceV1):
            raise ValueError("provenance must be RouteSessionProvenanceV1")


@dataclass(frozen=True)
class CollectionSessionCloseV1:
    """Immutable collection session close record."""

    schema_version: str
    record_kind: str
    session_close_id: str
    collection_session_id: str
    closed_source_timestamp_us: int
    close_reason: str
    ingest_timestamp_us: int
    provenance: RouteSessionProvenanceV1

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION_V1:
            raise ValueError('schema_version must be exactly "1.0"')

        if self.record_kind != COLLECTION_SESSION_CLOSE_RECORD_KIND:
            raise ValueError(
                'record_kind must be exactly "collection_session_close"'
            )

        if _CSC_ID_RE.fullmatch(self.session_close_id) is None:
            raise ValueError("invalid session_close_id")

        _require_text("collection_session_id", self.collection_session_id)
        _require_timestamp_us("closed_source_timestamp_us", self.closed_source_timestamp_us)

        if self.close_reason not in SESSION_CLOSE_REASONS:
            raise ValueError(
                f"close_reason must be one of {sorted(SESSION_CLOSE_REASONS)}"
            )

        _require_timestamp_us("ingest_timestamp_us", self.ingest_timestamp_us)

        if not isinstance(self.provenance, RouteSessionProvenanceV1):
            raise ValueError("provenance must be RouteSessionProvenanceV1")


@dataclass(frozen=True)
class RouteV1:
    """Immutable route record derived from ordered operator fixes."""

    schema_version: str
    record_kind: str
    route_id: str
    collection_session_id: str
    route_method: str
    route_version: str
    max_internal_gap_us: int
    ordered_operator_fix_ids: tuple[str, ...]
    started_source_timestamp_us: int
    ended_source_timestamp_us: int
    point_count: int
    created_ingest_timestamp_us: int
    provenance: RouteSessionProvenanceV1

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION_V1:
            raise ValueError('schema_version must be exactly "1.0"')

        if self.record_kind != ROUTE_RECORD_KIND:
            raise ValueError('record_kind must be exactly "route"')

        if _RTE_ID_RE.fullmatch(self.route_id) is None:
            raise ValueError("invalid route_id")

        _require_text("collection_session_id", self.collection_session_id)
        _require_text("route_method", self.route_method)
        _require_text("route_version", self.route_version)
        _require_non_negative_int("max_internal_gap_us", self.max_internal_gap_us)

        if not isinstance(self.ordered_operator_fix_ids, tuple):
            raise ValueError("ordered_operator_fix_ids must be a tuple")

        if not self.ordered_operator_fix_ids:
            raise ValueError("ordered_operator_fix_ids must be non-empty")

        if len(self.ordered_operator_fix_ids) != len(set(self.ordered_operator_fix_ids)):
            raise ValueError("ordered_operator_fix_ids must not contain duplicates")

        for fix_id in self.ordered_operator_fix_ids:
            _require_text("ordered_operator_fix_id", fix_id)

        _require_timestamp_us("started_source_timestamp_us", self.started_source_timestamp_us)
        _require_timestamp_us("ended_source_timestamp_us", self.ended_source_timestamp_us)

        if self.started_source_timestamp_us > self.ended_source_timestamp_us:
            raise ValueError(
                "started_source_timestamp_us must be <= ended_source_timestamp_us"
            )

        if self.point_count != len(self.ordered_operator_fix_ids):
            raise ValueError(
                "point_count must equal len(ordered_operator_fix_ids)"
            )

        _require_timestamp_us("created_ingest_timestamp_us", self.created_ingest_timestamp_us)

        if not isinstance(self.provenance, RouteSessionProvenanceV1):
            raise ValueError("provenance must be RouteSessionProvenanceV1")


@dataclass(frozen=True)
class AnalysisSessionV1:
    """Immutable analysis session record."""

    schema_version: str
    record_kind: str
    analysis_session_id: str
    analysis_type: str
    analysis_version: str
    ordered_collection_session_ids: tuple[str, ...]
    ordered_route_ids: tuple[str, ...]
    input_manifest_digest: str
    created_ingest_timestamp_us: int
    provenance: RouteSessionProvenanceV1

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION_V1:
            raise ValueError('schema_version must be exactly "1.0"')

        if self.record_kind != ANALYSIS_SESSION_RECORD_KIND:
            raise ValueError(
                'record_kind must be exactly "analysis_session"'
            )

        if _ASN_ID_RE.fullmatch(self.analysis_session_id) is None:
            raise ValueError("invalid analysis_session_id")

        _require_text("analysis_type", self.analysis_type)
        _require_text("analysis_version", self.analysis_version)

        if not isinstance(self.ordered_collection_session_ids, tuple):
            raise ValueError("ordered_collection_session_ids must be a tuple")

        if not self.ordered_collection_session_ids:
            raise ValueError("ordered_collection_session_ids must be non-empty")

        if len(self.ordered_collection_session_ids) != len(set(self.ordered_collection_session_ids)):
            raise ValueError("ordered_collection_session_ids must not contain duplicates")

        for sid in self.ordered_collection_session_ids:
            _require_text("ordered_collection_session_id", sid)

        if not isinstance(self.ordered_route_ids, tuple):
            raise ValueError("ordered_route_ids must be a tuple")

        if len(self.ordered_route_ids) != len(set(self.ordered_route_ids)):
            raise ValueError("ordered_route_ids must not contain duplicates")

        for rid in self.ordered_route_ids:
            _require_text("ordered_route_id", rid)

        _require_digest("input_manifest_digest", self.input_manifest_digest)
        _require_timestamp_us("created_ingest_timestamp_us", self.created_ingest_timestamp_us)

        if not isinstance(self.provenance, RouteSessionProvenanceV1):
            raise ValueError("provenance must be RouteSessionProvenanceV1")


def create_collection_session(
    *,
    hmac_key: bytes,
    session_controller_id: str,
    collection_session_reference: str,
    opened_source_timestamp_us: int,
    ingest_timestamp_us: int,
    provenance: RouteSessionProvenanceV1,
) -> CollectionSessionV1:
    """Create a collection session with a deterministic local HMAC identity."""

    normalized_controller_id = _require_text(
        "session_controller_id",
        session_controller_id,
    )
    normalized_reference = _require_text(
        "collection_session_reference",
        collection_session_reference,
    )

    collection_session_id = _derive_hmac_identifier(
        "csn_v1_",
        hmac_key,
        (
            normalized_controller_id,
            normalized_reference,
        ),
    )

    return CollectionSessionV1(
        schema_version=SCHEMA_VERSION_V1,
        record_kind=COLLECTION_SESSION_RECORD_KIND,
        collection_session_id=collection_session_id,
        session_controller_id=normalized_controller_id,
        collection_session_reference=normalized_reference,
        opened_source_timestamp_us=opened_source_timestamp_us,
        time_basis=TIME_BASIS,
        boundary_policy=BOUNDARY_POLICY,
        ingest_timestamp_us=ingest_timestamp_us,
        provenance=provenance,
    )


def create_source_membership(
    *,
    hmac_key: bytes,
    collection_session: CollectionSessionV1,
    source_type: str,
    sensor_id: str,
    source_instance_reference: str,
    joined_source_timestamp_us: int,
    ingest_timestamp_us: int,
    provenance: RouteSessionProvenanceV1,
) -> CollectionSourceMembershipV1:
    """Create a source membership with a deterministic local HMAC identity."""

    if not isinstance(collection_session, CollectionSessionV1):
        raise ValueError("collection_session must be CollectionSessionV1")

    normalized_source_type = _require_source_type(source_type)
    normalized_sensor_id = _require_text("sensor_id", sensor_id)
    normalized_reference = _require_text(
        "source_instance_reference",
        source_instance_reference,
    )

    membership_id = _derive_hmac_identifier(
        "csm_v1_",
        hmac_key,
        (
            collection_session.collection_session_id,
            normalized_source_type,
            normalized_sensor_id,
            normalized_reference,
        ),
    )

    return CollectionSourceMembershipV1(
        schema_version=SCHEMA_VERSION_V1,
        record_kind=COLLECTION_SOURCE_MEMBERSHIP_RECORD_KIND,
        membership_id=membership_id,
        collection_session_id=collection_session.collection_session_id,
        source_type=normalized_source_type,
        sensor_id=normalized_sensor_id,
        source_instance_reference=normalized_reference,
        joined_source_timestamp_us=joined_source_timestamp_us,
        ingest_timestamp_us=ingest_timestamp_us,
        provenance=provenance,
    )


def create_membership_close(
    *,
    hmac_key: bytes,
    membership: CollectionSourceMembershipV1,
    left_source_timestamp_us: int,
    close_reason: str,
    ingest_timestamp_us: int,
    provenance: RouteSessionProvenanceV1,
) -> CollectionSourceMembershipCloseV1:
    """Create a membership close with a deterministic local HMAC identity."""

    if not isinstance(membership, CollectionSourceMembershipV1):
        raise ValueError("membership must be CollectionSourceMembershipV1")

    if close_reason not in MEMBERSHIP_CLOSE_REASONS:
        raise ValueError(
            f"close_reason must be one of {sorted(MEMBERSHIP_CLOSE_REASONS)}"
        )

    membership_close_id = _derive_hmac_identifier(
        "cmc_v1_",
        hmac_key,
        (
            membership.membership_id,
        ),
    )

    return CollectionSourceMembershipCloseV1(
        schema_version=SCHEMA_VERSION_V1,
        record_kind=COLLECTION_SOURCE_MEMBERSHIP_CLOSE_RECORD_KIND,
        membership_close_id=membership_close_id,
        membership_id=membership.membership_id,
        left_source_timestamp_us=left_source_timestamp_us,
        close_reason=close_reason,
        ingest_timestamp_us=ingest_timestamp_us,
        provenance=provenance,
    )


def create_session_close(
    *,
    hmac_key: bytes,
    collection_session: CollectionSessionV1,
    closed_source_timestamp_us: int,
    close_reason: str,
    ingest_timestamp_us: int,
    provenance: RouteSessionProvenanceV1,
) -> CollectionSessionCloseV1:
    """Create a session close with a deterministic local HMAC identity."""

    if not isinstance(collection_session, CollectionSessionV1):
        raise ValueError("collection_session must be CollectionSessionV1")

    if close_reason not in SESSION_CLOSE_REASONS:
        raise ValueError(
            f"close_reason must be one of {sorted(SESSION_CLOSE_REASONS)}"
        )

    session_close_id = _derive_hmac_identifier(
        "csc_v1_",
        hmac_key,
        (
            collection_session.collection_session_id,
        ),
    )

    return CollectionSessionCloseV1(
        schema_version=SCHEMA_VERSION_V1,
        record_kind=COLLECTION_SESSION_CLOSE_RECORD_KIND,
        session_close_id=session_close_id,
        collection_session_id=collection_session.collection_session_id,
        closed_source_timestamp_us=closed_source_timestamp_us,
        close_reason=close_reason,
        ingest_timestamp_us=ingest_timestamp_us,
        provenance=provenance,
    )


def create_route(
    *,
    hmac_key: bytes,
    collection_session_id: str,
    route_method: str = ROUTE_METHOD,
    route_version: str = ROUTE_VERSION_V1,
    max_internal_gap_us: int = 0,
    operator_fixes: Sequence[OperatorFixV1],
    provenance: RouteSessionProvenanceV1,
    created_ingest_timestamp_us: int,
) -> RouteV1:
    """Create a route from ordered operator fixes with deterministic HMAC identity."""

    normalized_session_id = _require_text(
        "collection_session_id",
        collection_session_id,
    )

    if not operator_fixes:
        raise ValueError("operator_fixes must be non-empty")

    if not all(isinstance(fix, OperatorFixV1) for fix in operator_fixes):
        raise ValueError("all operator_fixes must be OperatorFixV1 instances")

    for fix in operator_fixes:
        if fix.collection_session_id != normalized_session_id:
            raise ValueError(
                "all operator_fixes must have collection_session_id "
                "matching route's collection_session_id"
            )

    fix_ids = [fix.operator_fix_id for fix in operator_fixes]

    if len(fix_ids) != len(set(fix_ids)):
        raise ValueError("operator_fixes must not contain duplicate fix IDs")

    sorted_fixes = sorted(
        operator_fixes,
        key=lambda fix: (fix.operator_fix_timestamp_us, fix.operator_fix_id),
    )

    for i in range(len(sorted_fixes) - 1):
        gap = abs(
            sorted_fixes[i + 1].operator_fix_timestamp_us
            - sorted_fixes[i].operator_fix_timestamp_us
        )
        if gap > max_internal_gap_us:
            raise ValueError(
                "adjacent operator_fix timestamp gap exceeds max_internal_gap_us"
            )

    started_source_timestamp_us = sorted_fixes[0].operator_fix_timestamp_us
    ended_source_timestamp_us = sorted_fixes[-1].operator_fix_timestamp_us
    point_count = len(sorted_fixes)
    ordered_operator_fix_ids = tuple(fix.operator_fix_id for fix in sorted_fixes)

    route_id = _derive_hmac_identifier(
        "rte_v1_",
        hmac_key,
        (
            normalized_session_id,
            route_method,
            route_version,
            str(max_internal_gap_us),
            str(ordered_operator_fix_ids),
        ),
    )

    return RouteV1(
        schema_version=SCHEMA_VERSION_V1,
        record_kind=ROUTE_RECORD_KIND,
        route_id=route_id,
        collection_session_id=normalized_session_id,
        route_method=route_method,
        route_version=route_version,
        max_internal_gap_us=max_internal_gap_us,
        ordered_operator_fix_ids=ordered_operator_fix_ids,
        started_source_timestamp_us=started_source_timestamp_us,
        ended_source_timestamp_us=ended_source_timestamp_us,
        point_count=point_count,
        created_ingest_timestamp_us=created_ingest_timestamp_us,
        provenance=provenance,
    )


def create_analysis_session(
    *,
    hmac_key: bytes,
    analysis_type: str,
    analysis_version: str,
    collection_session_ids: Sequence[str],
    route_ids: Sequence[str],
    input_manifest_digest: str,
    provenance: RouteSessionProvenanceV1,
    created_ingest_timestamp_us: int,
) -> AnalysisSessionV1:
    """Create an analysis session with a deterministic local HMAC identity."""

    normalized_type = _require_text("analysis_type", analysis_type)
    normalized_version = _require_text("analysis_version", analysis_version)

    if not collection_session_ids:
        raise ValueError("collection_session_ids must be non-empty")

    for sid in collection_session_ids:
        _require_text("collection_session_id", sid)

    for rid in route_ids:
        _require_text("route_id", rid)

    sorted_session_ids = tuple(sorted(collection_session_ids))

    if len(sorted_session_ids) != len(set(sorted_session_ids)):
        raise ValueError("collection_session_ids must not contain duplicates")

    sorted_route_ids = tuple(sorted(route_ids))

    if len(sorted_route_ids) != len(set(sorted_route_ids)):
        raise ValueError("route_ids must not contain duplicates")

    normalized_digest = _require_digest(
        "input_manifest_digest",
        input_manifest_digest,
    )

    analysis_session_id = _derive_hmac_identifier(
        "asn_v1_",
        hmac_key,
        (
            normalized_type,
            normalized_version,
            str(sorted_session_ids),
            str(sorted_route_ids),
            normalized_digest,
        ),
    )

    return AnalysisSessionV1(
        schema_version=SCHEMA_VERSION_V1,
        record_kind=ANALYSIS_SESSION_RECORD_KIND,
        analysis_session_id=analysis_session_id,
        analysis_type=normalized_type,
        analysis_version=normalized_version,
        ordered_collection_session_ids=sorted_session_ids,
        ordered_route_ids=sorted_route_ids,
        input_manifest_digest=normalized_digest,
        created_ingest_timestamp_us=created_ingest_timestamp_us,
        provenance=provenance,
    )


def compare_collection_session_source_facts(
    existing: CollectionSessionV1,
    incoming: CollectionSessionV1,
) -> str:
    """Return duplicate or identity_conflict for two collection session records."""

    if not isinstance(existing, CollectionSessionV1):
        raise ValueError("existing must be CollectionSessionV1")

    if not isinstance(incoming, CollectionSessionV1):
        raise ValueError("incoming must be CollectionSessionV1")

    if existing.collection_session_id != incoming.collection_session_id:
        return _IDENTITY_CONFLICT

    fields = (
        "session_controller_id",
        "collection_session_reference",
        "opened_source_timestamp_us",
        "time_basis",
        "boundary_policy",
    )

    existing_facts = tuple(getattr(existing, field) for field in fields)
    incoming_facts = tuple(getattr(incoming, field) for field in fields)

    if existing_facts == incoming_facts:
        return _DUPLICATE

    return _IDENTITY_CONFLICT


def compare_source_membership_source_facts(
    existing: CollectionSourceMembershipV1,
    incoming: CollectionSourceMembershipV1,
) -> str:
    """Return duplicate or identity_conflict for two source membership records."""

    if not isinstance(existing, CollectionSourceMembershipV1):
        raise ValueError("existing must be CollectionSourceMembershipV1")

    if not isinstance(incoming, CollectionSourceMembershipV1):
        raise ValueError("incoming must be CollectionSourceMembershipV1")

    if existing.membership_id != incoming.membership_id:
        return _IDENTITY_CONFLICT

    fields = (
        "collection_session_id",
        "source_type",
        "sensor_id",
        "source_instance_reference",
        "joined_source_timestamp_us",
    )

    existing_facts = tuple(getattr(existing, field) for field in fields)
    incoming_facts = tuple(getattr(incoming, field) for field in fields)

    if existing_facts == incoming_facts:
        return _DUPLICATE

    return _IDENTITY_CONFLICT


def compare_membership_close_source_facts(
    existing: CollectionSourceMembershipCloseV1,
    incoming: CollectionSourceMembershipCloseV1,
) -> str:
    """Return duplicate or identity_conflict for two membership close records."""

    if not isinstance(existing, CollectionSourceMembershipCloseV1):
        raise ValueError("existing must be CollectionSourceMembershipCloseV1")

    if not isinstance(incoming, CollectionSourceMembershipCloseV1):
        raise ValueError("incoming must be CollectionSourceMembershipCloseV1")

    if existing.membership_close_id != incoming.membership_close_id:
        return _IDENTITY_CONFLICT

    fields = (
        "membership_id",
        "left_source_timestamp_us",
        "close_reason",
    )

    existing_facts = tuple(getattr(existing, field) for field in fields)
    incoming_facts = tuple(getattr(incoming, field) for field in fields)

    if existing_facts == incoming_facts:
        return _DUPLICATE

    return _IDENTITY_CONFLICT


def compare_session_close_source_facts(
    existing: CollectionSessionCloseV1,
    incoming: CollectionSessionCloseV1,
) -> str:
    """Return duplicate or identity_conflict for two session close records."""

    if not isinstance(existing, CollectionSessionCloseV1):
        raise ValueError("existing must be CollectionSessionCloseV1")

    if not isinstance(incoming, CollectionSessionCloseV1):
        raise ValueError("incoming must be CollectionSessionCloseV1")

    if existing.session_close_id != incoming.session_close_id:
        return _IDENTITY_CONFLICT

    fields = (
        "collection_session_id",
        "closed_source_timestamp_us",
        "close_reason",
    )

    existing_facts = tuple(getattr(existing, field) for field in fields)
    incoming_facts = tuple(getattr(incoming, field) for field in fields)

    if existing_facts == incoming_facts:
        return _DUPLICATE

    return _IDENTITY_CONFLICT


def compare_route_source_facts(
    existing: RouteV1,
    incoming: RouteV1,
) -> str:
    """Return duplicate or identity_conflict for two route records."""

    if not isinstance(existing, RouteV1):
        raise ValueError("existing must be RouteV1")

    if not isinstance(incoming, RouteV1):
        raise ValueError("incoming must be RouteV1")

    if existing.route_id != incoming.route_id:
        return _IDENTITY_CONFLICT

    fields = (
        "collection_session_id",
        "route_method",
        "route_version",
        "max_internal_gap_us",
        "ordered_operator_fix_ids",
        "started_source_timestamp_us",
        "ended_source_timestamp_us",
        "point_count",
    )

    existing_facts = tuple(getattr(existing, field) for field in fields)
    incoming_facts = tuple(getattr(incoming, field) for field in fields)

    if existing_facts == incoming_facts:
        return _DUPLICATE

    return _IDENTITY_CONFLICT


def compare_analysis_session_source_facts(
    existing: AnalysisSessionV1,
    incoming: AnalysisSessionV1,
) -> str:
    """Return duplicate or identity_conflict for two analysis session records."""

    if not isinstance(existing, AnalysisSessionV1):
        raise ValueError("existing must be AnalysisSessionV1")

    if not isinstance(incoming, AnalysisSessionV1):
        raise ValueError("incoming must be AnalysisSessionV1")

    if existing.analysis_session_id != incoming.analysis_session_id:
        return _IDENTITY_CONFLICT

    fields = (
        "analysis_type",
        "analysis_version",
        "ordered_collection_session_ids",
        "ordered_route_ids",
        "input_manifest_digest",
    )

    existing_facts = tuple(getattr(existing, field) for field in fields)
    incoming_facts = tuple(getattr(incoming, field) for field in fields)

    if existing_facts == incoming_facts:
        return _DUPLICATE

    return _IDENTITY_CONFLICT


def validate_collection_session_boundaries(
    session: CollectionSessionV1,
    session_close: Optional[CollectionSessionCloseV1] = None,
) -> None:
    """Validate collection session open/close temporal boundaries."""

    if not isinstance(session, CollectionSessionV1):
        raise ValueError("session must be CollectionSessionV1")

    if session_close is not None:
        if not isinstance(session_close, CollectionSessionCloseV1):
            raise ValueError("session_close must be CollectionSessionCloseV1")

        if session_close.collection_session_id != session.collection_session_id:
            raise ValueError(
                "session_close.collection_session_id must match "
                "session.collection_session_id"
            )

        if session.opened_source_timestamp_us > session_close.closed_source_timestamp_us:
            raise ValueError(
                "session.open must be <= session_close.close timestamp"
            )


def validate_source_membership_boundaries(
    membership: CollectionSourceMembershipV1,
    membership_close: Optional[CollectionSourceMembershipCloseV1] = None,
    session_collection_session_id: Optional[str] = None,
) -> None:
    """Validate source membership open/close temporal boundaries."""

    if not isinstance(membership, CollectionSourceMembershipV1):
        raise ValueError("membership must be CollectionSourceMembershipV1")

    if membership_close is not None:
        if not isinstance(membership_close, CollectionSourceMembershipCloseV1):
            raise ValueError("membership_close must be CollectionSourceMembershipCloseV1")

        if membership_close.membership_id != membership.membership_id:
            raise ValueError(
                "membership_close.membership_id must match "
                "membership.membership_id"
            )

        if membership.joined_source_timestamp_us > membership_close.left_source_timestamp_us:
            raise ValueError(
                "membership.join must be <= membership_close.left timestamp"
            )

    if session_collection_session_id is not None:
        if membership.collection_session_id != session_collection_session_id:
            raise ValueError(
                "membership.collection_session_id must match "
                "session_collection_session_id"
            )


def validate_source_record_admission(
    session: CollectionSessionV1,
    membership: CollectionSourceMembershipV1,
    source_timestamp_us: int,
    session_close: Optional[CollectionSessionCloseV1] = None,
    membership_close: Optional[CollectionSourceMembershipCloseV1] = None,
) -> None:
    """Validate whether a source record timestamp falls within admission boundaries."""

    if not isinstance(session, CollectionSessionV1):
        raise ValueError("session must be CollectionSessionV1")

    if not isinstance(membership, CollectionSourceMembershipV1):
        raise ValueError("membership must be CollectionSourceMembershipV1")

    if membership.collection_session_id != session.collection_session_id:
        raise ValueError(
            "membership.collection_session_id must match "
            "session.collection_session_id"
        )

    source_timestamp_us = _require_timestamp_us("source_timestamp_us", source_timestamp_us)

    if source_timestamp_us < session.opened_source_timestamp_us:
        raise ValueError(
            "source_timestamp_us must be >= session.opened_source_timestamp_us"
        )

    if session_close is not None:
        if not isinstance(session_close, CollectionSessionCloseV1):
            raise ValueError("session_close must be CollectionSessionCloseV1")

        if session_close.collection_session_id != session.collection_session_id:
            raise ValueError(
                "session_close.collection_session_id must match "
                "session.collection_session_id"
            )

        if source_timestamp_us >= session_close.closed_source_timestamp_us:
            raise ValueError(
                "source_timestamp_us must be < session_close.closed_source_timestamp_us"
            )

    if source_timestamp_us < membership.joined_source_timestamp_us:
        raise ValueError(
            "source_timestamp_us must be >= membership.joined_source_timestamp_us"
        )

    if membership_close is not None:
        if not isinstance(membership_close, CollectionSourceMembershipCloseV1):
            raise ValueError("membership_close must be CollectionSourceMembershipCloseV1")

        if membership_close.membership_id != membership.membership_id:
            raise ValueError(
                "membership_close.membership_id must match "
                "membership.membership_id"
            )

        if source_timestamp_us >= membership_close.left_source_timestamp_us:
            raise ValueError(
                "source_timestamp_us must be < membership_close.left_source_timestamp_us"
            )

    if membership.joined_source_timestamp_us < session.opened_source_timestamp_us:
        raise ValueError(
            "membership.joined_source_timestamp_us must be >= "
            "session.opened_source_timestamp_us"
        )

    if session_close is not None and membership_close is not None:
        if membership_close.left_source_timestamp_us > session_close.closed_source_timestamp_us:
            raise ValueError(
                "membership_close.left_source_timestamp_us must be <= "
                "session_close.closed_source_timestamp_us"
            )


def _intervals_overlap(
    a_join: int, a_end: Optional[int],
    b_join: int, b_end: Optional[int],
) -> bool:
    """Check if two half-open intervals [join, end) overlap.

    None end represents infinity (no close yet).
    """
    a_effect_end = a_end if a_end is not None else float("inf")
    b_effect_end = b_end if b_end is not None else float("inf")

    return a_join < b_effect_end and b_join < a_effect_end


def validate_no_membership_overlap(
    pairs: Sequence[tuple[CollectionSourceMembershipV1, Optional[CollectionSourceMembershipCloseV1]]],
) -> None:
    """Validate that source memberships within the same session/source/sensor don't overlap."""

    for membership, membership_close in pairs:
        if not isinstance(membership, CollectionSourceMembershipV1):
            raise ValueError("each pair first element must be CollectionSourceMembershipV1")

        if membership_close is not None:
            if not isinstance(membership_close, CollectionSourceMembershipCloseV1):
                raise ValueError(
                    "each pair second element must be "
                    "CollectionSourceMembershipCloseV1 or None"
                )
            if membership_close.membership_id != membership.membership_id:
                raise ValueError(
                    "membership_close.membership_id must match "
                    "membership.membership_id"
                )

    grouped: dict[tuple[str, str, str], list[tuple[int, Optional[int]]]] = {}

    for membership, membership_close in pairs:
        key = (
            membership.collection_session_id,
            membership.source_type,
            membership.sensor_id,
        )
        join_ts = membership.joined_source_timestamp_us
        end_ts = (
            membership_close.left_source_timestamp_us
            if membership_close is not None
            else None
        )
        grouped.setdefault(key, []).append((join_ts, end_ts))

    for key, intervals in grouped.items():
        if len(intervals) < 2:
            continue

        sorted_intervals = sorted(intervals, key=lambda x: x[0])

        for i in range(len(sorted_intervals) - 1):
            a_join, a_end = sorted_intervals[i]
            b_join, b_end = sorted_intervals[i + 1]

            if _intervals_overlap(a_join, a_end, b_join, b_end):
                session_id, source_type, sensor_id = key
                raise ValueError(
                    f"overlapping membership intervals for "
                    f"session={session_id} source_type={source_type} "
                    f"sensor_id={sensor_id}"
                )


def validate_route_fix_inputs(
    operator_fixes: Sequence[OperatorFixV1],
    expected_collection_session_id: str,
) -> None:
    """Validate that operator fixes are consistent inputs for route construction."""

    if not operator_fixes:
        raise ValueError("operator_fixes must be non-empty")

    if not all(isinstance(fix, OperatorFixV1) for fix in operator_fixes):
        raise ValueError("all operator_fixes must be OperatorFixV1 instances")

    normalized_expected = _require_text(
        "expected_collection_session_id",
        expected_collection_session_id,
    )

    for fix in operator_fixes:
        if fix.collection_session_id != normalized_expected:
            raise ValueError(
                "all operator_fixes must have collection_session_id "
                "matching expected_collection_session_id"
            )
        _require_text("operator_fix_id", fix.operator_fix_id)

    fix_ids = [fix.operator_fix_id for fix in operator_fixes]

    if len(fix_ids) != len(set(fix_ids)):
        raise ValueError("operator_fixes must not contain duplicate fix IDs")


__all__ = [
    "AnalysisSessionV1",
    "BOUNDARY_POLICY",
    "COLLECTION_SESSION_CLOSE_RECORD_KIND",
    "COLLECTION_SESSION_RECORD_KIND",
    "COLLECTION_SOURCE_MEMBERSHIP_CLOSE_RECORD_KIND",
    "COLLECTION_SOURCE_MEMBERSHIP_RECORD_KIND",
    "CollectionSessionCloseV1",
    "CollectionSessionV1",
    "CollectionSourceMembershipCloseV1",
    "CollectionSourceMembershipV1",
    "MEMBERSHIP_CLOSE_REASONS",
    "ROUTE_METHOD",
    "ROUTE_RECORD_KIND",
    "ROUTE_VERSION_V1",
    "RouteSessionProvenanceV1",
    "RouteV1",
    "SCHEMA_VERSION_V1",
    "SESSION_CLOSE_REASONS",
    "TIME_BASIS",
    "AnalysisSessionV1",
    "compare_analysis_session_source_facts",
    "compare_collection_session_source_facts",
    "compare_membership_close_source_facts",
    "compare_route_source_facts",
    "compare_session_close_source_facts",
    "compare_source_membership_source_facts",
    "create_analysis_session",
    "create_collection_session",
    "create_membership_close",
    "create_route",
    "create_session_close",
    "create_source_membership",
    "validate_collection_session_boundaries",
    "validate_no_membership_overlap",
    "validate_route_fix_inputs",
    "validate_source_membership_boundaries",
    "validate_source_record_admission",
]
