"""Deterministic focused tests for the Alert Lifecycle v1 contract."""

import ast
import sys
import unittest
from typing import Optional, Tuple

from alert_contract import (
    __all__ as EXPORTED_ALL,
    SCHEMA_VERSION_V1,
    ALERT_RECORD_KIND,
    ALERT_EVIDENCE_RECORD_KIND,
    ALERT_TRANSITION_RECORD_KIND,
    ALERT_STATES,
    TERMINAL_STATES,
    NON_TERMINAL_STATES,
    ANALYSIS_MODES,
    EVIDENCE_LEVELS,
    ACTOR_KINDS,
    ID_PREFIX_DEDUP_KEY,
    ID_PREFIX_ALERT_ID,
    ID_PREFIX_EVIDENCE_ID,
    ID_PREFIX_TRANSITION_ID,
    AlertProvenanceV1,
    AlertV1,
    AlertEvidenceV1,
    AlertTransitionV1,
    create_alert,
    create_alert_evidence,
    create_alert_transition,
    compare_alert_source_facts,
    compare_alert_evidence_source_facts,
    compare_alert_transition_source_facts,
    is_allowed_alert_transition,
    validate_alert_transition_predecessor,
    cooldown_expires_at_us,
    is_within_alert_cooldown,
)


HMAC_KEY_A = b"test-key-alpha"
HMAC_KEY_B = b"test-key-beta"

TS_A = 1_000_000_000_000
TS_B = 1_000_000_001_000
TS_C = 1_000_000_002_000

HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64
HEX_D = "d" * 64
HEX_E = "e" * 64


# ── Helpers ──────────────────────────────────────────────────────────────

def make_provenance(
    analysis_mode: str = "synthetic",
) -> AlertProvenanceV1:
    return AlertProvenanceV1(
        analyzer_name="cyt.alert",
        analyzer_version="1.0.0",
        analysis_mode=analysis_mode,
        source_contract_version=SCHEMA_VERSION_V1,
    )


def make_alert(hmac_key: bytes = HMAC_KEY_A, **overrides) -> AlertV1:
    kwargs = {
        "hmac_key": hmac_key,
        "analysis_type": "pattern.persistence",
        "analysis_version": "1.0.0",
        "rule_id": "rule.multi_source",
        "rule_version": "1.0.0",
        "subject_kind": "device.aggregate",
        "subject_reference": HEX_A,
        "input_manifest_digest": HEX_C,
        "opening_evidence_reference": HEX_B,
        "first_observed_source_timestamp_us": TS_A,
        "created_ingest_timestamp_us": TS_B,
        "cooldown_us": 300_000_000,
        "provenance": make_provenance(),
    }
    kwargs.update(overrides)
    return create_alert(**kwargs)


def make_evidence(
    hmac_key: bytes = HMAC_KEY_A,
    alert: Optional[AlertV1] = None,
    **overrides,
) -> AlertEvidenceV1:
    if alert is None:
        alert = make_alert(hmac_key)
    kwargs = {
        "hmac_key": hmac_key,
        "alert": alert,
        "evidence_type": "observation.probe",
        "evidence_reference": HEX_D,
        "evidence_level": "observed",
        "observed_source_timestamp_us": TS_A,
        "recorded_ingest_timestamp_us": TS_B,
        "provenance": make_provenance(),
        "indicator_codes": ("indicator.probe_seen",),
        "data_quality_codes": ("quality.high",),
        "limitation_codes": (),
        "alternative_explanation_codes": (),
    }
    kwargs.update(overrides)
    return create_alert_evidence(**kwargs)


def make_transition(
    hmac_key: bytes = HMAC_KEY_A,
    alert: Optional[AlertV1] = None,
    **overrides,
) -> AlertTransitionV1:
    if alert is None:
        alert = make_alert(hmac_key)
    kwargs = {
        "hmac_key": hmac_key,
        "alert": alert,
        "transition_reference": HEX_E,
        "previous_transition_id": None,
        "from_state": "new",
        "to_state": "acknowledged",
        "transitioned_at_us": TS_A,
        "recorded_ingest_timestamp_us": TS_B,
        "reason_code": "transition.operator_review",
        "actor_kind": "operator",
        "provenance": make_provenance(),
    }
    kwargs.update(overrides)
    return create_alert_transition(**kwargs)


# ── Provenance ───────────────────────────────────────────────────────────

class TestAlertProvenanceV1(unittest.TestCase):

    def test_valid_construction(self):
        p = make_provenance()
        self.assertIsInstance(p, AlertProvenanceV1)

    def test_invalid_analysis_mode(self):
        with self.assertRaises(ValueError):
            make_provenance(analysis_mode="invalid")

    def test_empty_analyzer_name(self):
        with self.assertRaises(ValueError):
            AlertProvenanceV1(
                analyzer_name="",
                analyzer_version="1.0.0",
                analysis_mode="synthetic",
                source_contract_version=SCHEMA_VERSION_V1,
            )


# ── AlertV1 ──────────────────────────────────────────────────────────────

class TestAlertV1(unittest.TestCase):

    def test_create_minimal(self):
        a = make_alert()
        self.assertIsInstance(a, AlertV1)
        self.assertEqual(a.schema_version, SCHEMA_VERSION_V1)
        self.assertEqual(a.record_kind, ALERT_RECORD_KIND)
        self.assertEqual(a.initial_state, "new")
        self.assertTrue(a.alert_id.startswith(ID_PREFIX_ALERT_ID))
        self.assertTrue(a.deduplication_key.startswith(ID_PREFIX_DEDUP_KEY))

    def test_deterministic_identity(self):
        a1 = make_alert(HMAC_KEY_A)
        a2 = make_alert(HMAC_KEY_A)
        self.assertEqual(a1.alert_id, a2.alert_id)
        self.assertEqual(a1.deduplication_key, a2.deduplication_key)

    def test_different_hmac_key_changes_identity(self):
        a1 = make_alert(HMAC_KEY_A)
        a2 = make_alert(HMAC_KEY_B)
        self.assertNotEqual(a1.alert_id, a2.alert_id)

    def test_identity_changes_with_analysis_type(self):
        a1 = make_alert(analysis_type="pattern.persistence")
        a2 = make_alert(analysis_type="pattern.anomaly")
        self.assertNotEqual(a1.deduplication_key, a2.deduplication_key)
        self.assertNotEqual(a1.alert_id, a2.alert_id)

    def test_identity_changes_with_analysis_version(self):
        a1 = make_alert(analysis_version="1.0.0")
        a2 = make_alert(analysis_version="1.0.1")
        self.assertNotEqual(a1.deduplication_key, a2.deduplication_key)

    def test_identity_changes_with_rule_id(self):
        a1 = make_alert(rule_id="rule.multi_source")
        a2 = make_alert(rule_id="rule.single_source")
        self.assertNotEqual(a1.deduplication_key, a2.deduplication_key)

    def test_identity_changes_with_rule_version(self):
        a1 = make_alert(rule_version="1.0.0")
        a2 = make_alert(rule_version="2.0.0")
        self.assertNotEqual(a1.deduplication_key, a2.deduplication_key)

    def test_identity_changes_with_subject_kind(self):
        a1 = make_alert(subject_kind="device.aggregate")
        a2 = make_alert(subject_kind="device.singleton")
        self.assertNotEqual(a1.deduplication_key, a2.deduplication_key)

    def test_identity_changes_with_subject_reference(self):
        a1 = make_alert(subject_reference=HEX_A)
        a2 = make_alert(subject_reference=HEX_B)
        self.assertNotEqual(a1.deduplication_key, a2.deduplication_key)

    def test_identity_changes_with_baseline_manifest_digest(self):
        a1 = make_alert(baseline_manifest_digest=None)
        a2 = make_alert(baseline_manifest_digest=HEX_D)
        self.assertNotEqual(a1.deduplication_key, a2.deduplication_key)

    def test_identity_changes_with_opening_evidence_reference(self):
        a1 = make_alert(opening_evidence_reference=HEX_B)
        a2 = make_alert(opening_evidence_reference=HEX_C)
        self.assertNotEqual(a1.alert_id, a2.alert_id)
        self.assertEqual(a1.deduplication_key, a2.deduplication_key)

    def test_non_identity_ingest_timestamp_stable(self):
        a1 = make_alert(created_ingest_timestamp_us=TS_A)
        a2 = make_alert(created_ingest_timestamp_us=TS_C)
        self.assertEqual(a1.alert_id, a2.alert_id)

    def test_non_identity_provenance_stable(self):
        a1 = make_alert()
        a2 = create_alert(
            hmac_key=HMAC_KEY_A,
            analysis_type="pattern.persistence",
            analysis_version="1.0.0",
            rule_id="rule.multi_source",
            rule_version="1.0.0",
            subject_kind="device.aggregate",
            subject_reference=HEX_A,
            input_manifest_digest=HEX_C,
            opening_evidence_reference=HEX_B,
            first_observed_source_timestamp_us=TS_A,
            created_ingest_timestamp_us=TS_B,
            cooldown_us=300_000_000,
            provenance=AlertProvenanceV1(
                analyzer_name="other.analyzer",
                analyzer_version="2.0.0",
                analysis_mode="live",
                source_contract_version="2.0",
            ),
        )
        self.assertEqual(a1.alert_id, a2.alert_id)

    def test_frozen(self):
        a = make_alert()
        with self.assertRaises(Exception):
            a.analysis_type = "changed"

    def test_compare_duplicate(self):
        a1 = make_alert(HMAC_KEY_A)
        a2 = make_alert(HMAC_KEY_A)
        self.assertEqual(
            compare_alert_source_facts(a1, a2), "duplicate"
        )

    def test_compare_identity_conflict_different_id(self):
        a1 = make_alert(HMAC_KEY_A)
        a2 = make_alert(HMAC_KEY_B)
        self.assertEqual(
            compare_alert_source_facts(a1, a2), "identity_conflict"
        )

    def test_compare_identity_conflict_same_id_changed_facts(self):
        a1 = make_alert(HMAC_KEY_A)
        a2 = AlertV1(
            schema_version=a1.schema_version,
            record_kind=a1.record_kind,
            alert_id=a1.alert_id,
            deduplication_key=a1.deduplication_key,
            analysis_type=a1.analysis_type,
            analysis_version=a1.analysis_version,
            rule_id=a1.rule_id,
            rule_version=a1.rule_version,
            subject_kind=a1.subject_kind,
            subject_reference=HEX_E,
            input_manifest_digest=a1.input_manifest_digest,
            baseline_manifest_digest=a1.baseline_manifest_digest,
            opening_evidence_reference=a1.opening_evidence_reference,
            first_observed_source_timestamp_us=a1.first_observed_source_timestamp_us,
            created_ingest_timestamp_us=a1.created_ingest_timestamp_us,
            cooldown_us=a1.cooldown_us,
            initial_state=a1.initial_state,
            provenance=a1.provenance,
        )
        self.assertEqual(
            compare_alert_source_facts(a1, a2), "identity_conflict"
        )

    def test_compare_ignores_non_identity_fields(self):
        a1 = make_alert(created_ingest_timestamp_us=TS_A)
        a2 = make_alert(created_ingest_timestamp_us=TS_C)
        self.assertEqual(
            compare_alert_source_facts(a1, a2), "duplicate"
        )

    def test_compare_rejects_changed_deduplication_key(self):
        a1 = make_alert(HMAC_KEY_A)
        a2 = AlertV1(
            schema_version=a1.schema_version,
            record_kind=a1.record_kind,
            alert_id=a1.alert_id,
            deduplication_key=ID_PREFIX_DEDUP_KEY + HEX_E,
            analysis_type=a1.analysis_type,
            analysis_version=a1.analysis_version,
            rule_id=a1.rule_id,
            rule_version=a1.rule_version,
            subject_kind=a1.subject_kind,
            subject_reference=a1.subject_reference,
            input_manifest_digest=a1.input_manifest_digest,
            baseline_manifest_digest=a1.baseline_manifest_digest,
            opening_evidence_reference=a1.opening_evidence_reference,
            first_observed_source_timestamp_us=a1.first_observed_source_timestamp_us,
            created_ingest_timestamp_us=a1.created_ingest_timestamp_us,
            cooldown_us=a1.cooldown_us,
            initial_state=a1.initial_state,
            provenance=a1.provenance,
        )
        self.assertEqual(
            compare_alert_source_facts(a1, a2), "identity_conflict"
        )


# ── AlertEvidenceV1 ──────────────────────────────────────────────────────

class TestAlertEvidenceV1(unittest.TestCase):

    def test_create_minimal(self):
        e = make_evidence()
        self.assertIsInstance(e, AlertEvidenceV1)
        self.assertEqual(e.schema_version, SCHEMA_VERSION_V1)
        self.assertEqual(e.record_kind, ALERT_EVIDENCE_RECORD_KIND)
        self.assertTrue(e.evidence_id.startswith(ID_PREFIX_EVIDENCE_ID))

    def test_deterministic_identity(self):
        e1 = make_evidence(HMAC_KEY_A)
        e2 = make_evidence(HMAC_KEY_A)
        self.assertEqual(e1.evidence_id, e2.evidence_id)

    def test_different_key_changes_identity(self):
        e1 = make_evidence(HMAC_KEY_A)
        e2 = make_evidence(HMAC_KEY_B)
        self.assertNotEqual(e1.evidence_id, e2.evidence_id)

    def test_identity_changes_with_alert_id(self):
        a1 = make_alert(HMAC_KEY_A)
        a2 = make_alert(HMAC_KEY_B)
        e1 = make_evidence(HMAC_KEY_A, alert=a1)
        e2 = make_evidence(HMAC_KEY_A, alert=a2)
        self.assertNotEqual(e1.evidence_id, e2.evidence_id)

    def test_identity_changes_with_evidence_type(self):
        alert = make_alert(HMAC_KEY_A)
        e1 = make_evidence(HMAC_KEY_A, alert=alert, evidence_type="observation.probe")
        e2 = make_evidence(HMAC_KEY_A, alert=alert, evidence_type="observation.association")
        self.assertNotEqual(e1.evidence_id, e2.evidence_id)

    def test_identity_changes_with_evidence_reference(self):
        alert = make_alert(HMAC_KEY_A)
        e1 = make_evidence(HMAC_KEY_A, alert=alert, evidence_reference=HEX_D)
        e2 = make_evidence(HMAC_KEY_A, alert=alert, evidence_reference=HEX_E)
        self.assertNotEqual(e1.evidence_id, e2.evidence_id)

    def test_non_identity_evidence_level_stable(self):
        alert = make_alert(HMAC_KEY_A)
        e1 = make_evidence(HMAC_KEY_A, alert=alert, evidence_level="observed")
        e2 = make_evidence(HMAC_KEY_A, alert=alert, evidence_level="correlated")
        self.assertEqual(e1.evidence_id, e2.evidence_id)

    def test_non_identity_code_tuples_stable(self):
        alert = make_alert(HMAC_KEY_A)
        e1 = make_evidence(
            HMAC_KEY_A,
            alert=alert,
            indicator_codes=("indicator.probe_seen",),
        )
        e2 = make_evidence(
            HMAC_KEY_A,
            alert=alert,
            indicator_codes=("indicator.probe_seen", "indicator.second_probe"),
        )
        self.assertEqual(e1.evidence_id, e2.evidence_id)

    def test_frozen(self):
        e = make_evidence()
        with self.assertRaises(Exception):
            e.evidence_level = "derived"

    def test_compare_duplicate(self):
        e1 = make_evidence(HMAC_KEY_A)
        e2 = make_evidence(HMAC_KEY_A)
        self.assertEqual(
            compare_alert_evidence_source_facts(e1, e2), "duplicate"
        )

    def test_compare_identity_conflict_different_id(self):
        e1 = make_evidence(HMAC_KEY_A)
        e2 = make_evidence(HMAC_KEY_B)
        self.assertEqual(
            compare_alert_evidence_source_facts(e1, e2), "identity_conflict"
        )

    def test_compare_identity_conflict_same_id_changed_facts(self):
        e1 = make_evidence(HMAC_KEY_A)
        e2 = AlertEvidenceV1(
            schema_version=e1.schema_version,
            record_kind=e1.record_kind,
            evidence_id=e1.evidence_id,
            alert_id=e1.alert_id,
            evidence_type="observation.changed",
            evidence_reference=e1.evidence_reference,
            evidence_level=e1.evidence_level,
            observed_source_timestamp_us=e1.observed_source_timestamp_us,
            recorded_ingest_timestamp_us=e1.recorded_ingest_timestamp_us,
            indicator_codes=e1.indicator_codes,
            data_quality_codes=e1.data_quality_codes,
            limitation_codes=e1.limitation_codes,
            alternative_explanation_codes=e1.alternative_explanation_codes,
            provenance=e1.provenance,
        )
        self.assertEqual(
            compare_alert_evidence_source_facts(e1, e2), "identity_conflict"
        )


# ── AlertTransitionV1 ────────────────────────────────────────────────────

class TestAlertTransitionV1(unittest.TestCase):

    def test_create_minimal(self):
        t = make_transition()
        self.assertIsInstance(t, AlertTransitionV1)
        self.assertEqual(t.schema_version, SCHEMA_VERSION_V1)
        self.assertEqual(t.record_kind, ALERT_TRANSITION_RECORD_KIND)
        self.assertTrue(t.transition_id.startswith(ID_PREFIX_TRANSITION_ID))

    def test_deterministic_identity(self):
        t1 = make_transition(HMAC_KEY_A)
        t2 = make_transition(HMAC_KEY_A)
        self.assertEqual(t1.transition_id, t2.transition_id)

    def test_different_key_changes_identity(self):
        t1 = make_transition(HMAC_KEY_A)
        t2 = make_transition(HMAC_KEY_B)
        self.assertNotEqual(t1.transition_id, t2.transition_id)

    def test_identity_changes_with_alert_id(self):
        a1 = make_alert(HMAC_KEY_A)
        a2 = make_alert(HMAC_KEY_B)
        t1 = make_transition(HMAC_KEY_A, alert=a1)
        t2 = make_transition(HMAC_KEY_A, alert=a2)
        self.assertNotEqual(t1.transition_id, t2.transition_id)

    def test_identity_changes_with_transition_reference(self):
        alert = make_alert(HMAC_KEY_A)
        t1 = make_transition(HMAC_KEY_A, alert=alert, transition_reference=HEX_E)
        t2 = make_transition(HMAC_KEY_A, alert=alert, transition_reference=HEX_D)
        self.assertNotEqual(t1.transition_id, t2.transition_id)

    def test_non_identity_previous_transition_id_stable(self):
        alert = make_alert(HMAC_KEY_A)
        tid_a = ID_PREFIX_TRANSITION_ID + HEX_C
        tid_b = ID_PREFIX_TRANSITION_ID + HEX_D
        t1 = make_transition(
            HMAC_KEY_A,
            alert=alert,
            from_state="acknowledged",
            to_state="resolved",
            previous_transition_id=tid_a,
        )
        t2 = make_transition(
            HMAC_KEY_A,
            alert=alert,
            from_state="acknowledged",
            to_state="resolved",
            previous_transition_id=tid_b,
        )
        self.assertEqual(t1.transition_id, t2.transition_id)

    def test_non_identity_states_stable(self):
        alert = make_alert(HMAC_KEY_A)
        prev_id = ID_PREFIX_TRANSITION_ID + HEX_C
        t1 = make_transition(
            HMAC_KEY_A,
            alert=alert,
            from_state="new",
            to_state="acknowledged",
            previous_transition_id=None,
        )
        t2 = make_transition(
            HMAC_KEY_A,
            alert=alert,
            from_state="acknowledged",
            to_state="resolved",
            previous_transition_id=prev_id,
        )
        self.assertEqual(t1.transition_id, t2.transition_id)

    def test_frozen(self):
        t = make_transition()
        with self.assertRaises(Exception):
            t.to_state = "resolved"

    def test_compare_duplicate(self):
        t1 = make_transition(HMAC_KEY_A)
        t2 = make_transition(HMAC_KEY_A)
        self.assertEqual(
            compare_alert_transition_source_facts(t1, t2), "duplicate"
        )

    def test_compare_identity_conflict_different_id(self):
        t1 = make_transition(HMAC_KEY_A)
        t2 = make_transition(HMAC_KEY_B)
        self.assertEqual(
            compare_alert_transition_source_facts(t1, t2), "identity_conflict"
        )

    def test_compare_identity_conflict_same_id_changed_facts(self):
        t1 = make_transition(HMAC_KEY_A)
        t2 = AlertTransitionV1(
            schema_version=t1.schema_version,
            record_kind=t1.record_kind,
            transition_id=t1.transition_id,
            alert_id=t1.alert_id,
            transition_reference=t1.transition_reference,
            previous_transition_id=ID_PREFIX_TRANSITION_ID + HEX_C,
            from_state="acknowledged",
            to_state="resolved",
            transitioned_at_us=t1.transitioned_at_us,
            recorded_ingest_timestamp_us=t1.recorded_ingest_timestamp_us,
            reason_code=t1.reason_code,
            actor_kind=t1.actor_kind,
            provenance=t1.provenance,
        )
        self.assertEqual(
            compare_alert_transition_source_facts(t1, t2), "identity_conflict"
        )


# ── Transition validation ────────────────────────────────────────────────

class TestTransitionValidation(unittest.TestCase):

    def test_full_6x6_transition_matrix(self):
        expected = {
            ("new", "acknowledged"): True,
            ("new", "observing"): True,
            ("new", "dismissed"): True,
            ("new", "escalated"): True,
            ("new", "resolved"): False,
            ("new", "new"): False,
            ("acknowledged", "observing"): True,
            ("acknowledged", "dismissed"): True,
            ("acknowledged", "escalated"): True,
            ("acknowledged", "resolved"): True,
            ("acknowledged", "acknowledged"): False,
            ("acknowledged", "new"): False,
            ("observing", "dismissed"): True,
            ("observing", "escalated"): True,
            ("observing", "resolved"): True,
            ("observing", "acknowledged"): False,
            ("observing", "observing"): False,
            ("observing", "new"): False,
            ("escalated", "observing"): True,
            ("escalated", "dismissed"): True,
            ("escalated", "resolved"): True,
            ("escalated", "acknowledged"): False,
            ("escalated", "escalated"): False,
            ("escalated", "new"): False,
            ("dismissed", "acknowledged"): False,
            ("dismissed", "observing"): False,
            ("dismissed", "dismissed"): False,
            ("dismissed", "escalated"): False,
            ("dismissed", "resolved"): False,
            ("dismissed", "new"): False,
            ("resolved", "acknowledged"): False,
            ("resolved", "observing"): False,
            ("resolved", "dismissed"): False,
            ("resolved", "escalated"): False,
            ("resolved", "resolved"): False,
            ("resolved", "new"): False,
        }

        for from_state in ALERT_STATES:
            for to_state in ALERT_STATES:
                expected_value = expected[(from_state, to_state)]
                self.assertEqual(
                    is_allowed_alert_transition(from_state, to_state),
                    expected_value,
                    f"{from_state} -> {to_state}",
                )

    def test_invalid_state_raises(self):
        with self.assertRaises(ValueError):
            is_allowed_alert_transition("invalid", "new")
        with self.assertRaises(ValueError):
            is_allowed_alert_transition("new", "invalid")

    def test_first_transition_valid(self):
        t = make_transition(from_state="new", to_state="acknowledged")
        validate_alert_transition_predecessor(t, None)

    def test_first_transition_with_predecessor_fails(self):
        first = make_transition(
            from_state="new",
            to_state="acknowledged",
            transition_reference=HEX_D,
        )
        t = make_transition(
            from_state="new",
            to_state="observing",
            transition_reference=HEX_E,
        )
        with self.assertRaises(ValueError):
            validate_alert_transition_predecessor(t, first)

    def test_first_transition_with_previous_id_fails(self):
        with self.assertRaises(ValueError):
            make_transition(
                from_state="new",
                to_state="acknowledged",
                previous_transition_id=ID_PREFIX_TRANSITION_ID + HEX_C,
            )

    def test_non_first_transition_without_predecessor_fails(self):
        with self.assertRaises(ValueError):
            make_transition(from_state="acknowledged", to_state="observing")

    def test_valid_chain(self):
        alert = make_alert()
        first = make_transition(
            alert=alert,
            from_state="new",
            to_state="acknowledged",
            transition_reference=HEX_D,
            transitioned_at_us=TS_A,
        )
        second = make_transition(
            alert=alert,
            from_state="acknowledged",
            to_state="observing",
            transition_reference=HEX_E,
            transitioned_at_us=TS_B,
            previous_transition_id=first.transition_id,
        )
        validate_alert_transition_predecessor(first, None)
        validate_alert_transition_predecessor(second, first)

    def test_predecessor_id_equality(self):
        alert = make_alert()
        first = make_transition(
            alert=alert,
            from_state="new",
            to_state="acknowledged",
            transition_reference=HEX_D,
            transitioned_at_us=TS_A,
        )
        second = make_transition(
            alert=alert,
            from_state="acknowledged",
            to_state="observing",
            transition_reference=HEX_E,
            transitioned_at_us=TS_B,
            previous_transition_id=ID_PREFIX_TRANSITION_ID + HEX_C,
        )
        with self.assertRaises(ValueError):
            validate_alert_transition_predecessor(second, first)

    def test_chain_alert_id_mismatch(self):
        a1 = make_alert()
        a2 = make_alert(subject_reference=HEX_E)
        first = make_transition(
            alert=a1,
            from_state="new",
            to_state="acknowledged",
            transition_reference=HEX_D,
            transitioned_at_us=TS_A,
        )
        second = make_transition(
            alert=a2,
            from_state="acknowledged",
            to_state="observing",
            transition_reference=HEX_E,
            transitioned_at_us=TS_B,
            previous_transition_id=first.transition_id,
        )
        with self.assertRaises(ValueError):
            validate_alert_transition_predecessor(second, first)

    def test_chain_from_state_mismatch(self):
        alert = make_alert()
        first = make_transition(
            alert=alert,
            from_state="new",
            to_state="acknowledged",
            transition_reference=HEX_D,
            transitioned_at_us=TS_A,
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
            validate_alert_transition_predecessor(second, first)

    def test_chain_time_reversal(self):
        alert = make_alert()
        first = make_transition(
            alert=alert,
            from_state="new",
            to_state="acknowledged",
            transition_reference=HEX_D,
            transitioned_at_us=TS_C,
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
            validate_alert_transition_predecessor(second, first)

    def test_terminal_state_no_outgoing(self):
        for terminal in TERMINAL_STATES:
            for to_state in ALERT_STATES:
                self.assertFalse(
                    is_allowed_alert_transition(terminal, to_state)
                )


# ── Direct transition validation ─────────────────────────────────────────

class TestDirectTransitionValidation(unittest.TestCase):

    def _valid_first_transition(self) -> AlertTransitionV1:
        return make_transition(from_state="new", to_state="acknowledged")

    def _valid_non_first_transition(self) -> AlertTransitionV1:
        return make_transition(
            from_state="acknowledged",
            to_state="resolved",
            previous_transition_id=ID_PREFIX_TRANSITION_ID + HEX_C,
        )

    def test_direct_construction_self_transition_rejected(self):
        t = self._valid_first_transition()
        with self.assertRaises(ValueError):
            AlertTransitionV1(
                schema_version=t.schema_version,
                record_kind=t.record_kind,
                transition_id=t.transition_id,
                alert_id=t.alert_id,
                transition_reference=t.transition_reference,
                previous_transition_id=None,
                from_state="acknowledged",
                to_state="acknowledged",
                transitioned_at_us=t.transitioned_at_us,
                recorded_ingest_timestamp_us=t.recorded_ingest_timestamp_us,
                reason_code=t.reason_code,
                actor_kind=t.actor_kind,
                provenance=t.provenance,
            )

    def test_direct_construction_transition_to_new_rejected(self):
        t = self._valid_first_transition()
        with self.assertRaises(ValueError):
            AlertTransitionV1(
                schema_version=t.schema_version,
                record_kind=t.record_kind,
                transition_id=t.transition_id,
                alert_id=t.alert_id,
                transition_reference=t.transition_reference,
                previous_transition_id=None,
                from_state="acknowledged",
                to_state="new",
                transitioned_at_us=t.transitioned_at_us,
                recorded_ingest_timestamp_us=t.recorded_ingest_timestamp_us,
                reason_code=t.reason_code,
                actor_kind=t.actor_kind,
                provenance=t.provenance,
            )

    def test_direct_construction_additional_absent_pair_rejected(self):
        t = self._valid_first_transition()
        for from_state, to_state in (
            ("new", "resolved"),
            ("observing", "acknowledged"),
            ("escalated", "acknowledged"),
            ("dismissed", "resolved"),
            ("resolved", "dismissed"),
        ):
            with self.subTest(from_state=from_state, to_state=to_state):
                previous_id = (
                    ID_PREFIX_TRANSITION_ID + HEX_C
                    if from_state != "new"
                    else None
                )
                with self.assertRaises(ValueError):
                    AlertTransitionV1(
                        schema_version=t.schema_version,
                        record_kind=t.record_kind,
                        transition_id=t.transition_id,
                        alert_id=t.alert_id,
                        transition_reference=t.transition_reference,
                        previous_transition_id=previous_id,
                        from_state=from_state,
                        to_state=to_state,
                        transitioned_at_us=t.transitioned_at_us,
                        recorded_ingest_timestamp_us=t.recorded_ingest_timestamp_us,
                        reason_code=t.reason_code,
                        actor_kind=t.actor_kind,
                        provenance=t.provenance,
                    )

    def test_direct_construction_first_transition_with_previous_id_rejected(self):
        t = self._valid_first_transition()
        with self.assertRaises(ValueError):
            AlertTransitionV1(
                schema_version=t.schema_version,
                record_kind=t.record_kind,
                transition_id=t.transition_id,
                alert_id=t.alert_id,
                transition_reference=t.transition_reference,
                previous_transition_id=ID_PREFIX_TRANSITION_ID + HEX_C,
                from_state="new",
                to_state="acknowledged",
                transitioned_at_us=t.transitioned_at_us,
                recorded_ingest_timestamp_us=t.recorded_ingest_timestamp_us,
                reason_code=t.reason_code,
                actor_kind=t.actor_kind,
                provenance=t.provenance,
            )

    def test_direct_construction_non_first_without_previous_id_rejected(self):
        t = self._valid_first_transition()
        with self.assertRaises(ValueError):
            AlertTransitionV1(
                schema_version=t.schema_version,
                record_kind=t.record_kind,
                transition_id=t.transition_id,
                alert_id=t.alert_id,
                transition_reference=t.transition_reference,
                previous_transition_id=None,
                from_state="acknowledged",
                to_state="resolved",
                transitioned_at_us=t.transitioned_at_us,
                recorded_ingest_timestamp_us=t.recorded_ingest_timestamp_us,
                reason_code=t.reason_code,
                actor_kind=t.actor_kind,
                provenance=t.provenance,
            )

    def test_direct_construction_valid_first_transition_accepted(self):
        t = self._valid_first_transition()
        self.assertIsInstance(t, AlertTransitionV1)
        self.assertIsNone(t.previous_transition_id)

    def test_direct_construction_valid_non_first_transition_accepted(self):
        t = self._valid_non_first_transition()
        self.assertIsInstance(t, AlertTransitionV1)
        self.assertIsNotNone(t.previous_transition_id)

    def test_create_transition_rejects_locally_invalid_pair(self):
        alert = make_alert()
        with self.assertRaises(ValueError):
            create_alert_transition(
                hmac_key=HMAC_KEY_A,
                alert=alert,
                transition_reference=HEX_E,
                from_state="new",
                to_state="resolved",
                transitioned_at_us=TS_A,
                recorded_ingest_timestamp_us=TS_B,
                reason_code="transition.operator_review",
                actor_kind="operator",
                provenance=make_provenance(),
            )


# ── Cooldown ─────────────────────────────────────────────────────────────

class TestCooldown(unittest.TestCase):

    def test_cooldown_expiry_for_terminal(self):
        alert = make_alert(cooldown_us=1_000_000)
        terminal = make_transition(
            alert=alert,
            from_state="new",
            to_state="dismissed",
            transitioned_at_us=TS_B,
        )
        self.assertEqual(
            cooldown_expires_at_us(alert, terminal),
            TS_B + 1_000_000,
        )

    def test_cooldown_rejects_non_terminal(self):
        alert = make_alert()
        non_terminal = make_transition(
            alert=alert,
            from_state="new",
            to_state="acknowledged",
            transitioned_at_us=TS_B,
        )
        with self.assertRaises(ValueError):
            cooldown_expires_at_us(alert, non_terminal)

    def test_cooldown_rejects_wrong_alert(self):
        alert = make_alert()
        other_alert = make_alert(subject_reference=HEX_E)
        terminal = make_transition(
            alert=other_alert,
            from_state="new",
            to_state="dismissed",
            transitioned_at_us=TS_B,
        )
        with self.assertRaises(ValueError):
            cooldown_expires_at_us(alert, terminal)

    def test_within_cooldown_before_terminal_fails(self):
        alert = make_alert(cooldown_us=1_000_000)
        terminal = make_transition(
            alert=alert,
            from_state="new",
            to_state="dismissed",
            transitioned_at_us=TS_B,
        )
        with self.assertRaises(ValueError):
            is_within_alert_cooldown(alert, terminal, TS_A)

    def test_within_cooldown_inside(self):
        alert = make_alert(cooldown_us=1_000_000)
        terminal = make_transition(
            alert=alert,
            from_state="new",
            to_state="dismissed",
            transitioned_at_us=TS_B,
        )
        self.assertTrue(
            is_within_alert_cooldown(alert, terminal, TS_B + 500_000)
        )

    def test_within_cooldown_exact_boundary_outside(self):
        alert = make_alert(cooldown_us=1_000_000)
        terminal = make_transition(
            alert=alert,
            from_state="new",
            to_state="dismissed",
            transitioned_at_us=TS_B,
        )
        self.assertFalse(
            is_within_alert_cooldown(alert, terminal, TS_B + 1_000_000)
        )

    def test_within_cooldown_after(self):
        alert = make_alert(cooldown_us=1_000_000)
        terminal = make_transition(
            alert=alert,
            from_state="new",
            to_state="dismissed",
            transitioned_at_us=TS_B,
        )
        self.assertFalse(
            is_within_alert_cooldown(alert, terminal, TS_B + 1_500_000)
        )


# ── Malformed inputs ─────────────────────────────────────────────────────

class TestMalformedInputs(unittest.TestCase):

    def _base_alert_kwargs(self):
        return {
            "hmac_key": HMAC_KEY_A,
            "analysis_type": "pattern.persistence",
            "analysis_version": "1.0.0",
            "rule_id": "rule.multi_source",
            "rule_version": "1.0.0",
            "subject_kind": "device.aggregate",
            "subject_reference": HEX_A,
            "input_manifest_digest": HEX_C,
            "opening_evidence_reference": HEX_B,
            "first_observed_source_timestamp_us": TS_A,
            "created_ingest_timestamp_us": TS_B,
            "cooldown_us": 300_000_000,
            "provenance": make_provenance(),
        }

    def test_timestamp_us_bool_rejected(self):
        kw = self._base_alert_kwargs()
        kw["first_observed_source_timestamp_us"] = True
        with self.assertRaises(ValueError):
            create_alert(**kw)

    def test_timestamp_us_float_rejected(self):
        kw = self._base_alert_kwargs()
        kw["first_observed_source_timestamp_us"] = 1_000_000.5
        with self.assertRaises(ValueError):
            create_alert(**kw)

    def test_timestamp_us_negative_rejected(self):
        kw = self._base_alert_kwargs()
        kw["first_observed_source_timestamp_us"] = -1
        with self.assertRaises(ValueError):
            create_alert(**kw)

    def test_timestamp_us_string_rejected(self):
        kw = self._base_alert_kwargs()
        kw["first_observed_source_timestamp_us"] = "1000"
        with self.assertRaises(ValueError):
            create_alert(**kw)

    def test_digest_uppercase_rejected(self):
        kw = self._base_alert_kwargs()
        kw["subject_reference"] = "A" * 64
        with self.assertRaises(ValueError):
            create_alert(**kw)

    def test_digest_wrong_length_rejected(self):
        kw = self._base_alert_kwargs()
        kw["subject_reference"] = "a" * 63
        with self.assertRaises(ValueError):
            create_alert(**kw)

    def test_digest_non_hex_rejected(self):
        kw = self._base_alert_kwargs()
        kw["subject_reference"] = "x" * 64
        with self.assertRaises(ValueError):
            create_alert(**kw)

    def test_id_wrong_prefix_rejected(self):
        alert = make_alert()
        with self.assertRaises(ValueError):
            AlertV1(
                schema_version=alert.schema_version,
                record_kind=alert.record_kind,
                alert_id=alert.alert_id,
                deduplication_key="wrong_" + HEX_A,
                analysis_type=alert.analysis_type,
                analysis_version=alert.analysis_version,
                rule_id=alert.rule_id,
                rule_version=alert.rule_version,
                subject_kind=alert.subject_kind,
                subject_reference=alert.subject_reference,
                input_manifest_digest=alert.input_manifest_digest,
                opening_evidence_reference=alert.opening_evidence_reference,
                first_observed_source_timestamp_us=alert.first_observed_source_timestamp_us,
                created_ingest_timestamp_us=alert.created_ingest_timestamp_us,
                cooldown_us=alert.cooldown_us,
                initial_state=alert.initial_state,
                provenance=alert.provenance,
            )

    def test_invalid_initial_state_rejected(self):
        alert = make_alert()
        with self.assertRaises(ValueError):
            AlertV1(
                schema_version=alert.schema_version,
                record_kind=alert.record_kind,
                alert_id=alert.alert_id,
                deduplication_key=alert.deduplication_key,
                analysis_type=alert.analysis_type,
                analysis_version=alert.analysis_version,
                rule_id=alert.rule_id,
                rule_version=alert.rule_version,
                subject_kind=alert.subject_kind,
                subject_reference=alert.subject_reference,
                input_manifest_digest=alert.input_manifest_digest,
                opening_evidence_reference=alert.opening_evidence_reference,
                first_observed_source_timestamp_us=alert.first_observed_source_timestamp_us,
                created_ingest_timestamp_us=alert.created_ingest_timestamp_us,
                cooldown_us=alert.cooldown_us,
                initial_state="acknowledged",
                provenance=alert.provenance,
            )

    def test_invalid_evidence_level_rejected(self):
        alert = make_alert()
        with self.assertRaises(ValueError):
            create_alert_evidence(
                hmac_key=HMAC_KEY_A,
                alert=alert,
                evidence_type="observation.probe",
                evidence_reference=HEX_D,
                evidence_level="invalid",
                observed_source_timestamp_us=TS_A,
                recorded_ingest_timestamp_us=TS_B,
                provenance=make_provenance(),
            )

    def test_invalid_actor_kind_rejected(self):
        alert = make_alert()
        with self.assertRaises(ValueError):
            create_alert_transition(
                hmac_key=HMAC_KEY_A,
                alert=alert,
                transition_reference=HEX_E,
                from_state="new",
                to_state="acknowledged",
                transitioned_at_us=TS_A,
                recorded_ingest_timestamp_us=TS_B,
                reason_code="transition.operator_review",
                actor_kind="automation",
                provenance=make_provenance(),
            )

    def test_empty_hmac_key_rejected(self):
        kw = self._base_alert_kwargs()
        kw["hmac_key"] = b""
        with self.assertRaises(ValueError):
            create_alert(**kw)

    def test_hmac_key_string_rejected(self):
        kw = self._base_alert_kwargs()
        kw["hmac_key"] = "not-bytes"
        with self.assertRaises(ValueError):
            create_alert(**kw)

    def test_code_tuple_not_tuple_rejected(self):
        alert = make_alert()
        with self.assertRaises(ValueError):
            create_alert_evidence(
                hmac_key=HMAC_KEY_A,
                alert=alert,
                evidence_type="observation.probe",
                evidence_reference=HEX_D,
                evidence_level="observed",
                observed_source_timestamp_us=TS_A,
                recorded_ingest_timestamp_us=TS_B,
                provenance=make_provenance(),
                indicator_codes=["indicator.probe_seen"],
            )

    def test_code_tuple_not_sorted_rejected(self):
        alert = make_alert()
        with self.assertRaises(ValueError):
            create_alert_evidence(
                hmac_key=HMAC_KEY_A,
                alert=alert,
                evidence_type="observation.probe",
                evidence_reference=HEX_D,
                evidence_level="observed",
                observed_source_timestamp_us=TS_A,
                recorded_ingest_timestamp_us=TS_B,
                provenance=make_provenance(),
                indicator_codes=("indicator.second", "indicator.first"),
            )

    def test_code_tuple_duplicate_rejected(self):
        alert = make_alert()
        with self.assertRaises(ValueError):
            create_alert_evidence(
                hmac_key=HMAC_KEY_A,
                alert=alert,
                evidence_type="observation.probe",
                evidence_reference=HEX_D,
                evidence_level="observed",
                observed_source_timestamp_us=TS_A,
                recorded_ingest_timestamp_us=TS_B,
                provenance=make_provenance(),
                indicator_codes=("indicator.probe_seen", "indicator.probe_seen"),
            )

    def test_code_tuple_not_namespaced_rejected(self):
        alert = make_alert()
        with self.assertRaises(ValueError):
            create_alert_evidence(
                hmac_key=HMAC_KEY_A,
                alert=alert,
                evidence_type="observation.probe",
                evidence_reference=HEX_D,
                evidence_level="observed",
                observed_source_timestamp_us=TS_A,
                recorded_ingest_timestamp_us=TS_B,
                provenance=make_provenance(),
                indicator_codes=("probe_seen",),
            )

    def test_code_tuple_uppercase_rejected(self):
        alert = make_alert()
        with self.assertRaises(ValueError):
            create_alert_evidence(
                hmac_key=HMAC_KEY_A,
                alert=alert,
                evidence_type="observation.probe",
                evidence_reference=HEX_D,
                evidence_level="observed",
                observed_source_timestamp_us=TS_A,
                recorded_ingest_timestamp_us=TS_B,
                provenance=make_provenance(),
                indicator_codes=("Indicator.Probe_Seen",),
            )

    def test_transition_to_new_rejected(self):
        alert = make_alert()
        with self.assertRaises(ValueError):
            make_transition(alert=alert, from_state="acknowledged", to_state="new")

    def test_self_transition_rejected(self):
        alert = make_alert()
        with self.assertRaises(ValueError):
            make_transition(alert=alert, from_state="acknowledged", to_state="acknowledged")


# ── Exported constants ───────────────────────────────────────────────────

class TestExportedConstants(unittest.TestCase):

    def test_all_exported_present(self):
        for name in EXPORTED_ALL:
            self.assertIn(name, dir(sys.modules["alert_contract"]))

    def test_states_sorted_unique_lowercase(self):
        self.assertEqual(ALERT_STATES, set(ALERT_STATES))
        for state in ALERT_STATES:
            self.assertEqual(state, state.lower())

    def test_terminal_states_subset(self):
        for state in TERMINAL_STATES:
            self.assertIn(state, ALERT_STATES)

    def test_evidence_levels_sorted_unique_lowercase(self):
        self.assertEqual(EVIDENCE_LEVELS, {"observed", "correlated", "derived"})

    def test_actor_kinds(self):
        self.assertEqual(ACTOR_KINDS, {"operator", "system"})

    def test_analysis_modes(self):
        self.assertEqual(ANALYSIS_MODES, {"live", "replay", "synthetic"})


# ── AST prohibitions ─────────────────────────────────────────────────────

class TestASTProhibitions(unittest.TestCase):

    def _load_source(self):
        with open("alert_contract.py") as f:
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
        source = self._load_source_text()
        func_start = source.find("def _canonical_identity_bytes")
        self.assertGreaterEqual(func_start, 0)

        func_body = source[func_start:func_start + 400]
        self.assertIn("sort_keys=True", func_body)
        self.assertIn('separators=(",", ":")', func_body)
        self.assertIn("ensure_ascii=False", func_body)

    def _load_source_text(self) -> str:
        with open("alert_contract.py") as f:
            return f.read()

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
            "title",
            "location_label",
            "probability",
            "confidence",
            "accuracy",
            "threat",
            "stalking",
            "surveillance",
            "following",
            "intent",
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
