"""Alert Lifecycle v1 — isolated immutable contract."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import re
from typing import Optional, Tuple


SCHEMA_VERSION_V1 = "1.0"

ALERT_RECORD_KIND = "alert"
ALERT_EVIDENCE_RECORD_KIND = "alert_evidence"
ALERT_TRANSITION_RECORD_KIND = "alert_transition"

ALERT_STATES = frozenset(
    {"acknowledged", "dismissed", "escalated", "new", "observing", "resolved"}
)
TERMINAL_STATES = frozenset({"dismissed", "resolved"})
NON_TERMINAL_STATES = frozenset({"new", "acknowledged", "observing", "escalated"})

ANALYSIS_MODES = frozenset({"live", "replay", "synthetic"})
EVIDENCE_LEVELS = frozenset({"correlated", "derived", "observed"})
ACTOR_KINDS = frozenset({"operator", "system"})

ID_PREFIX_DEDUP_KEY = "adk_v1_"
ID_PREFIX_ALERT_ID = "alr_v1_"
ID_PREFIX_EVIDENCE_ID = "aev_v1_"
ID_PREFIX_TRANSITION_ID = "atr_v1_"

_DEDUP_KEY_RE = re.compile(rf"^{ID_PREFIX_DEDUP_KEY}[0-9a-f]{{64}}$")
_ALERT_ID_RE = re.compile(rf"^{ID_PREFIX_ALERT_ID}[0-9a-f]{{64}}$")
_EVIDENCE_ID_RE = re.compile(rf"^{ID_PREFIX_EVIDENCE_ID}[0-9a-f]{{64}}$")
_TRANSITION_ID_RE = re.compile(rf"^{ID_PREFIX_TRANSITION_ID}[0-9a-f]{{64}}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_NAMESPACE_RE = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+$")

_DUPLICATE = "duplicate"
_IDENTITY_CONFLICT = "identity_conflict"

_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "new": frozenset({"acknowledged", "observing", "dismissed", "escalated"}),
    "acknowledged": frozenset({"observing", "dismissed", "escalated", "resolved"}),
    "observing": frozenset({"dismissed", "escalated", "resolved"}),
    "escalated": frozenset({"observing", "dismissed", "resolved"}),
    "dismissed": frozenset(),
    "resolved": frozenset(),
}


def _require_text(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")

    if not value or value != value.strip():
        raise ValueError(f"{name} must be a non-empty canonical string")

    return value


def _require_timestamp_us(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(
            f"{name} must be a non-negative integer Unix timestamp in microseconds"
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


def _require_digest(name: str, value: object) -> str:
    text = _require_text(name, value)

    if _DIGEST_RE.fullmatch(text) is None:
        raise ValueError(f"{name} must be a 64-character hex digest")

    return text


def _require_optional_digest(name: str, value: object) -> Optional[str]:
    if value is None:
        return None

    return _require_digest(name, value)


def _require_id(name: str, value: object, prefix: str) -> str:
    text = _require_text(name, value)

    pattern = re.compile(rf"^{re.escape(prefix)}[0-9a-f]{{64}}$")
    if pattern.fullmatch(text) is None:
        raise ValueError(f"{name} must be a valid identifier")

    return text


def _require_namespaced(name: str, value: object) -> str:
    text = _require_text(name, value)

    if _NAMESPACE_RE.fullmatch(text) is None:
        raise ValueError(f"{name} must be a lowercase namespaced value")

    return text


def _require_canonical_tuple(name: str, value: object) -> Tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{name} must be a tuple")

    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{name} must contain only strings")
        _require_namespaced(f"{name} element", item)

    if tuple(sorted(value)) != value:
        raise ValueError(f"{name} must be sorted")

    if len(set(value)) != len(value):
        raise ValueError(f"{name} must not contain duplicates")

    return value


def _canonical_identity_bytes(parts: tuple[str, ...]) -> bytes:
    return json.dumps(
        list(parts),
        ensure_ascii=False,
        sort_keys=True,
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


@dataclass(frozen=True)
class AlertProvenanceV1:
    """Non-secret provenance for one alert-family record."""

    analyzer_name: str
    analyzer_version: str
    analysis_mode: str
    source_contract_version: str

    def __post_init__(self) -> None:
        _require_text("analyzer_name", self.analyzer_name)
        _require_text("analyzer_version", self.analyzer_version)

        if self.analysis_mode not in ANALYSIS_MODES:
            raise ValueError("analysis_mode must be live, replay, or synthetic")

        _require_text("source_contract_version", self.source_contract_version)


@dataclass(frozen=True)
class AlertV1:
    """Immutable alert record."""

    schema_version: str
    record_kind: str
    alert_id: str
    deduplication_key: str
    analysis_type: str
    analysis_version: str
    rule_id: str
    rule_version: str
    subject_kind: str
    subject_reference: str
    input_manifest_digest: str
    opening_evidence_reference: str
    first_observed_source_timestamp_us: int
    created_ingest_timestamp_us: int
    cooldown_us: int
    initial_state: str
    provenance: AlertProvenanceV1
    baseline_manifest_digest: Optional[str] = None

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION_V1:
            raise ValueError('schema_version must be exactly "1.0"')

        if self.record_kind != ALERT_RECORD_KIND:
            raise ValueError('record_kind must be exactly "alert"')

        if _ALERT_ID_RE.fullmatch(self.alert_id) is None:
            raise ValueError("invalid alert_id")

        if _DEDUP_KEY_RE.fullmatch(self.deduplication_key) is None:
            raise ValueError("invalid deduplication_key")

        _require_text("analysis_type", self.analysis_type)
        _require_text("analysis_version", self.analysis_version)
        _require_text("rule_id", self.rule_id)
        _require_text("rule_version", self.rule_version)
        _require_text("subject_kind", self.subject_kind)
        _require_digest("subject_reference", self.subject_reference)
        _require_digest("input_manifest_digest", self.input_manifest_digest)
        _require_digest(
            "opening_evidence_reference",
            self.opening_evidence_reference,
        )
        _require_timestamp_us(
            "first_observed_source_timestamp_us",
            self.first_observed_source_timestamp_us,
        )
        _require_timestamp_us(
            "created_ingest_timestamp_us",
            self.created_ingest_timestamp_us,
        )
        _require_non_negative_int("cooldown_us", self.cooldown_us)

        if self.initial_state != "new":
            raise ValueError('initial_state must be exactly "new"')

        _require_optional_digest(
            "baseline_manifest_digest",
            self.baseline_manifest_digest,
        )

        if not isinstance(self.provenance, AlertProvenanceV1):
            raise ValueError("provenance must be AlertProvenanceV1")


@dataclass(frozen=True)
class AlertEvidenceV1:
    """Immutable alert evidence record."""

    schema_version: str
    record_kind: str
    evidence_id: str
    alert_id: str
    evidence_type: str
    evidence_reference: str
    evidence_level: str
    observed_source_timestamp_us: int
    recorded_ingest_timestamp_us: int
    indicator_codes: Tuple[str, ...]
    data_quality_codes: Tuple[str, ...]
    limitation_codes: Tuple[str, ...]
    alternative_explanation_codes: Tuple[str, ...]
    provenance: AlertProvenanceV1

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION_V1:
            raise ValueError('schema_version must be exactly "1.0"')

        if self.record_kind != ALERT_EVIDENCE_RECORD_KIND:
            raise ValueError('record_kind must be exactly "alert_evidence"')

        if _EVIDENCE_ID_RE.fullmatch(self.evidence_id) is None:
            raise ValueError("invalid evidence_id")

        if _ALERT_ID_RE.fullmatch(self.alert_id) is None:
            raise ValueError("invalid alert_id")

        _require_text("evidence_type", self.evidence_type)
        _require_digest("evidence_reference", self.evidence_reference)

        if self.evidence_level not in EVIDENCE_LEVELS:
            raise ValueError(
                "evidence_level must be observed, correlated, or derived"
            )

        _require_timestamp_us(
            "observed_source_timestamp_us",
            self.observed_source_timestamp_us,
        )
        _require_timestamp_us(
            "recorded_ingest_timestamp_us",
            self.recorded_ingest_timestamp_us,
        )

        _require_canonical_tuple("indicator_codes", self.indicator_codes)
        _require_canonical_tuple("data_quality_codes", self.data_quality_codes)
        _require_canonical_tuple("limitation_codes", self.limitation_codes)
        _require_canonical_tuple(
            "alternative_explanation_codes",
            self.alternative_explanation_codes,
        )

        if not isinstance(self.provenance, AlertProvenanceV1):
            raise ValueError("provenance must be AlertProvenanceV1")


@dataclass(frozen=True)
class AlertTransitionV1:
    """Immutable alert state transition record."""

    schema_version: str
    record_kind: str
    transition_id: str
    alert_id: str
    transition_reference: str
    previous_transition_id: Optional[str]
    from_state: str
    to_state: str
    transitioned_at_us: int
    recorded_ingest_timestamp_us: int
    reason_code: str
    actor_kind: str
    provenance: AlertProvenanceV1

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION_V1:
            raise ValueError('schema_version must be exactly "1.0"')

        if self.record_kind != ALERT_TRANSITION_RECORD_KIND:
            raise ValueError(
                'record_kind must be exactly "alert_transition"'
            )

        if _TRANSITION_ID_RE.fullmatch(self.transition_id) is None:
            raise ValueError("invalid transition_id")

        if _ALERT_ID_RE.fullmatch(self.alert_id) is None:
            raise ValueError("invalid alert_id")

        _require_digest("transition_reference", self.transition_reference)

        if self.previous_transition_id is not None:
            if _TRANSITION_ID_RE.fullmatch(self.previous_transition_id) is None:
                raise ValueError("invalid previous_transition_id")

        if self.from_state not in ALERT_STATES:
            raise ValueError("invalid from_state")

        if self.to_state not in ALERT_STATES:
            raise ValueError("invalid to_state")

        if not is_allowed_alert_transition(self.from_state, self.to_state):
            raise ValueError("disallowed transition")

        if self.from_state == "new":
            if self.previous_transition_id is not None:
                raise ValueError(
                    "first transition must not reference a previous transition"
                )
        else:
            if self.previous_transition_id is None:
                raise ValueError(
                    "non-first transition must reference a previous transition"
                )

        _require_timestamp_us(
            "transitioned_at_us",
            self.transitioned_at_us,
        )
        _require_timestamp_us(
            "recorded_ingest_timestamp_us",
            self.recorded_ingest_timestamp_us,
        )

        _require_text("reason_code", self.reason_code)

        if self.actor_kind not in ACTOR_KINDS:
            raise ValueError("actor_kind must be operator or system")

        if not isinstance(self.provenance, AlertProvenanceV1):
            raise ValueError("provenance must be AlertProvenanceV1")


def create_alert(
    *,
    hmac_key: bytes,
    analysis_type: str,
    analysis_version: str,
    rule_id: str,
    rule_version: str,
    subject_kind: str,
    subject_reference: str,
    input_manifest_digest: str,
    opening_evidence_reference: str,
    first_observed_source_timestamp_us: int,
    created_ingest_timestamp_us: int,
    cooldown_us: int,
    provenance: AlertProvenanceV1,
    baseline_manifest_digest: Optional[str] = None,
) -> AlertV1:
    """Create an alert with a deterministic local HMAC identity."""

    normalized_analysis_type = _require_text("analysis_type", analysis_type)
    normalized_analysis_version = _require_text(
        "analysis_version", analysis_version
    )
    normalized_rule_id = _require_text("rule_id", rule_id)
    normalized_rule_version = _require_text("rule_version", rule_version)
    normalized_subject_kind = _require_text("subject_kind", subject_kind)
    normalized_subject_reference = _require_digest(
        "subject_reference", subject_reference
    )
    normalized_input_manifest_digest = _require_digest(
        "input_manifest_digest", input_manifest_digest
    )
    normalized_opening_reference = _require_digest(
        "opening_evidence_reference", opening_evidence_reference
    )
    normalized_baseline = (
        _require_digest("baseline_manifest_digest", baseline_manifest_digest)
        if baseline_manifest_digest is not None
        else ""
    )

    deduplication_key = _derive_hmac_identifier(
        ID_PREFIX_DEDUP_KEY,
        hmac_key,
        (
            normalized_analysis_type,
            normalized_analysis_version,
            normalized_rule_id,
            normalized_rule_version,
            normalized_subject_kind,
            normalized_subject_reference,
            normalized_baseline,
        ),
    )

    alert_id = _derive_hmac_identifier(
        ID_PREFIX_ALERT_ID,
        hmac_key,
        (
            deduplication_key,
            normalized_opening_reference,
        ),
    )

    return AlertV1(
        schema_version=SCHEMA_VERSION_V1,
        record_kind=ALERT_RECORD_KIND,
        alert_id=alert_id,
        deduplication_key=deduplication_key,
        analysis_type=normalized_analysis_type,
        analysis_version=normalized_analysis_version,
        rule_id=normalized_rule_id,
        rule_version=normalized_rule_version,
        subject_kind=normalized_subject_kind,
        subject_reference=normalized_subject_reference,
        input_manifest_digest=normalized_input_manifest_digest,
        baseline_manifest_digest=baseline_manifest_digest,
        opening_evidence_reference=normalized_opening_reference,
        first_observed_source_timestamp_us=first_observed_source_timestamp_us,
        created_ingest_timestamp_us=created_ingest_timestamp_us,
        cooldown_us=cooldown_us,
        initial_state="new",
        provenance=provenance,
    )


def create_alert_evidence(
    *,
    hmac_key: bytes,
    alert: AlertV1,
    evidence_type: str,
    evidence_reference: str,
    evidence_level: str,
    observed_source_timestamp_us: int,
    recorded_ingest_timestamp_us: int,
    provenance: AlertProvenanceV1,
    indicator_codes: Tuple[str, ...] = (),
    data_quality_codes: Tuple[str, ...] = (),
    limitation_codes: Tuple[str, ...] = (),
    alternative_explanation_codes: Tuple[str, ...] = (),
) -> AlertEvidenceV1:
    """Create an alert evidence record with a deterministic HMAC identity."""

    if not isinstance(alert, AlertV1):
        raise ValueError("alert must be AlertV1")

    normalized_evidence_type = _require_text("evidence_type", evidence_type)
    normalized_evidence_reference = _require_digest(
        "evidence_reference", evidence_reference
    )

    if evidence_level not in EVIDENCE_LEVELS:
        raise ValueError(
            "evidence_level must be observed, correlated, or derived"
        )

    normalized_indicator_codes = _require_canonical_tuple(
        "indicator_codes", indicator_codes
    )
    normalized_data_quality_codes = _require_canonical_tuple(
        "data_quality_codes", data_quality_codes
    )
    normalized_limitation_codes = _require_canonical_tuple(
        "limitation_codes", limitation_codes
    )
    normalized_alternative_codes = _require_canonical_tuple(
        "alternative_explanation_codes", alternative_explanation_codes
    )

    evidence_id = _derive_hmac_identifier(
        ID_PREFIX_EVIDENCE_ID,
        hmac_key,
        (
            alert.alert_id,
            normalized_evidence_type,
            normalized_evidence_reference,
        ),
    )

    return AlertEvidenceV1(
        schema_version=SCHEMA_VERSION_V1,
        record_kind=ALERT_EVIDENCE_RECORD_KIND,
        evidence_id=evidence_id,
        alert_id=alert.alert_id,
        evidence_type=normalized_evidence_type,
        evidence_reference=normalized_evidence_reference,
        evidence_level=evidence_level,
        observed_source_timestamp_us=observed_source_timestamp_us,
        recorded_ingest_timestamp_us=recorded_ingest_timestamp_us,
        indicator_codes=normalized_indicator_codes,
        data_quality_codes=normalized_data_quality_codes,
        limitation_codes=normalized_limitation_codes,
        alternative_explanation_codes=normalized_alternative_codes,
        provenance=provenance,
    )


def create_alert_transition(
    *,
    hmac_key: bytes,
    alert: AlertV1,
    transition_reference: str,
    from_state: str,
    to_state: str,
    transitioned_at_us: int,
    recorded_ingest_timestamp_us: int,
    reason_code: str,
    actor_kind: str,
    provenance: AlertProvenanceV1,
    previous_transition_id: Optional[str] = None,
) -> AlertTransitionV1:
    """Create an alert transition with a deterministic HMAC identity."""

    if not isinstance(alert, AlertV1):
        raise ValueError("alert must be AlertV1")

    normalized_reference = _require_digest(
        "transition_reference", transition_reference
    )
    normalized_reason_code = _require_text("reason_code", reason_code)

    if from_state not in ALERT_STATES:
        raise ValueError("invalid from_state")

    if to_state not in ALERT_STATES:
        raise ValueError("invalid to_state")

    if actor_kind not in ACTOR_KINDS:
        raise ValueError("actor_kind must be operator or system")

    if previous_transition_id is not None:
        if _TRANSITION_ID_RE.fullmatch(previous_transition_id) is None:
            raise ValueError("invalid previous_transition_id")

    transition_id = _derive_hmac_identifier(
        ID_PREFIX_TRANSITION_ID,
        hmac_key,
        (
            alert.alert_id,
            normalized_reference,
        ),
    )

    return AlertTransitionV1(
        schema_version=SCHEMA_VERSION_V1,
        record_kind=ALERT_TRANSITION_RECORD_KIND,
        transition_id=transition_id,
        alert_id=alert.alert_id,
        transition_reference=normalized_reference,
        previous_transition_id=previous_transition_id,
        from_state=from_state,
        to_state=to_state,
        transitioned_at_us=transitioned_at_us,
        recorded_ingest_timestamp_us=recorded_ingest_timestamp_us,
        reason_code=normalized_reason_code,
        actor_kind=actor_kind,
        provenance=provenance,
    )


def compare_alert_source_facts(existing: AlertV1, incoming: AlertV1) -> str:
    """Return duplicate or identity_conflict for two alert records."""

    if not isinstance(existing, AlertV1):
        raise ValueError("existing must be AlertV1")

    if not isinstance(incoming, AlertV1):
        raise ValueError("incoming must be AlertV1")

    if existing.alert_id != incoming.alert_id:
        return _IDENTITY_CONFLICT

    fields = (
        "deduplication_key",
        "analysis_type",
        "analysis_version",
        "rule_id",
        "rule_version",
        "subject_kind",
        "subject_reference",
        "input_manifest_digest",
        "baseline_manifest_digest",
        "opening_evidence_reference",
        "first_observed_source_timestamp_us",
        "cooldown_us",
        "initial_state",
    )

    existing_facts = tuple(getattr(existing, field) for field in fields)
    incoming_facts = tuple(getattr(incoming, field) for field in fields)

    if existing_facts == incoming_facts:
        return _DUPLICATE

    return _IDENTITY_CONFLICT


def compare_alert_evidence_source_facts(
    existing: AlertEvidenceV1,
    incoming: AlertEvidenceV1,
) -> str:
    """Return duplicate or identity_conflict for two evidence records."""

    if not isinstance(existing, AlertEvidenceV1):
        raise ValueError("existing must be AlertEvidenceV1")

    if not isinstance(incoming, AlertEvidenceV1):
        raise ValueError("incoming must be AlertEvidenceV1")

    if existing.evidence_id != incoming.evidence_id:
        return _IDENTITY_CONFLICT

    fields = (
        "alert_id",
        "evidence_type",
        "evidence_reference",
        "evidence_level",
        "observed_source_timestamp_us",
        "indicator_codes",
        "data_quality_codes",
        "limitation_codes",
        "alternative_explanation_codes",
    )

    existing_facts = tuple(getattr(existing, field) for field in fields)
    incoming_facts = tuple(getattr(incoming, field) for field in fields)

    if existing_facts == incoming_facts:
        return _DUPLICATE

    return _IDENTITY_CONFLICT


def compare_alert_transition_source_facts(
    existing: AlertTransitionV1,
    incoming: AlertTransitionV1,
) -> str:
    """Return duplicate or identity_conflict for two transition records."""

    if not isinstance(existing, AlertTransitionV1):
        raise ValueError("existing must be AlertTransitionV1")

    if not isinstance(incoming, AlertTransitionV1):
        raise ValueError("incoming must be AlertTransitionV1")

    if existing.transition_id != incoming.transition_id:
        return _IDENTITY_CONFLICT

    fields = (
        "alert_id",
        "transition_reference",
        "previous_transition_id",
        "from_state",
        "to_state",
        "transitioned_at_us",
        "reason_code",
        "actor_kind",
    )

    existing_facts = tuple(getattr(existing, field) for field in fields)
    incoming_facts = tuple(getattr(incoming, field) for field in fields)

    if existing_facts == incoming_facts:
        return _DUPLICATE

    return _IDENTITY_CONFLICT


def is_allowed_alert_transition(from_state: str, to_state: str) -> bool:
    """Return True if from_state -> to_state is allowed."""

    if from_state not in ALERT_STATES:
        raise ValueError("invalid from_state")

    if to_state not in ALERT_STATES:
        raise ValueError("invalid to_state")

    return to_state in _ALLOWED_TRANSITIONS.get(from_state, frozenset())


def validate_alert_transition_predecessor(
    transition: AlertTransitionV1,
    predecessor: Optional[AlertTransitionV1] = None,
) -> None:
    """Validate a transition against its predecessor."""

    if not isinstance(transition, AlertTransitionV1):
        raise ValueError("transition must be AlertTransitionV1")

    if predecessor is not None:
        if not isinstance(predecessor, AlertTransitionV1):
            raise ValueError("predecessor must be AlertTransitionV1")

    if not is_allowed_alert_transition(transition.from_state, transition.to_state):
        raise ValueError("disallowed transition")

    if transition.from_state == transition.to_state:
        raise ValueError("self-transition is not allowed")

    if transition.to_state == "new":
        raise ValueError("transition to new is not allowed")

    if transition.from_state == "new":
        if predecessor is not None:
            raise ValueError(
                "first transition must not have a predecessor"
            )

        if transition.previous_transition_id is not None:
            raise ValueError(
                "first transition must not reference a previous transition"
            )
    else:
        if predecessor is None:
            raise ValueError("non-first transition requires a predecessor")

        if transition.previous_transition_id != predecessor.transition_id:
            raise ValueError("previous_transition_id must match predecessor")

        if transition.alert_id != predecessor.alert_id:
            raise ValueError("alert_id must match predecessor")

        if transition.from_state != predecessor.to_state:
            raise ValueError("from_state must continue from predecessor")

        if transition.transitioned_at_us < predecessor.transitioned_at_us:
            raise ValueError(
                "transitioned_at_us must not move backward in time"
            )

    if transition.to_state in TERMINAL_STATES:
        return


def cooldown_expires_at_us(
    alert: AlertV1,
    terminal_transition: AlertTransitionV1,
) -> int:
    """Return the cooldown expiry timestamp for a terminal transition."""

    if not isinstance(alert, AlertV1):
        raise ValueError("alert must be AlertV1")

    if not isinstance(terminal_transition, AlertTransitionV1):
        raise ValueError("terminal_transition must be AlertTransitionV1")

    if terminal_transition.alert_id != alert.alert_id:
        raise ValueError("terminal_transition must belong to alert")

    if terminal_transition.to_state not in TERMINAL_STATES:
        raise ValueError("terminal_transition must end in a terminal state")

    return terminal_transition.transitioned_at_us + alert.cooldown_us


def is_within_alert_cooldown(
    alert: AlertV1,
    terminal_transition: AlertTransitionV1,
    candidate_source_timestamp_us: int,
) -> bool:
    """Return True if candidate falls inside the alert cooldown window."""

    if not isinstance(alert, AlertV1):
        raise ValueError("alert must be AlertV1")

    if not isinstance(terminal_transition, AlertTransitionV1):
        raise ValueError("terminal_transition must be AlertTransitionV1")

    candidate_source_timestamp_us = _require_timestamp_us(
        "candidate_source_timestamp_us", candidate_source_timestamp_us
    )

    expiry = cooldown_expires_at_us(alert, terminal_transition)

    if candidate_source_timestamp_us < terminal_transition.transitioned_at_us:
        raise ValueError(
            "candidate_source_timestamp_us must not precede terminal transition"
        )

    return candidate_source_timestamp_us < expiry


__all__ = [
    "ALERT_EVIDENCE_RECORD_KIND",
    "ALERT_RECORD_KIND",
    "ALERT_TRANSITION_RECORD_KIND",
    "ALERT_STATES",
    "ANALYSIS_MODES",
    "ACTOR_KINDS",
    "AlertEvidenceV1",
    "AlertProvenanceV1",
    "AlertTransitionV1",
    "AlertV1",
    "EVIDENCE_LEVELS",
    "ID_PREFIX_ALERT_ID",
    "ID_PREFIX_DEDUP_KEY",
    "ID_PREFIX_EVIDENCE_ID",
    "ID_PREFIX_TRANSITION_ID",
    "NON_TERMINAL_STATES",
    "SCHEMA_VERSION_V1",
    "TERMINAL_STATES",
    "compare_alert_evidence_source_facts",
    "compare_alert_source_facts",
    "compare_alert_transition_source_facts",
    "cooldown_expires_at_us",
    "create_alert",
    "create_alert_evidence",
    "create_alert_transition",
    "is_allowed_alert_transition",
    "is_within_alert_cooldown",
    "validate_alert_transition_predecessor",
]
