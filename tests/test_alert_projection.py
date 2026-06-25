"""Deterministic focused tests for Alert State Projection v1."""

import ast
import sys
import unittest
import re as stdlib_re
from typing import Optional, Tuple

from alert_contract import (
    SCHEMA_VERSION_V1,
    ALERT_STATES,
    TERMINAL_STATES,
    ID_PREFIX_ALERT_ID,
    ID_PREFIX_TRANSITION_ID,
    AlertProvenanceV1,
    AlertV1,
    AlertTransitionV1,
    create_alert,
    create_alert_transition,
    validate_alert_transition_predecessor,
    cooldown_expires_at_us,
    is_within_alert_cooldown,
)

from alert_projection import (
    __all__ as EXPORTED_ALL,
    ALERT_STATE_PROJECTION_RECORD_KIND,
    AlertStateProjectionV1,
    build_alert_state_projection,
)


HMAC_KEY_A = b"test-key-alpha"

TS_A = 1_000_000_000_000
TS_B = 1_000_000_001_000
TS_C = 1_000_000_002_000
TS_D = 1_000_000_003_000
TS_E = 1_000_000_004_000
TS_F = 1_000_000_005_000

HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64
HEX_D = "d" * 64
HEX_E = "e" * 64

_TRANSITION_ID_RE = stdlib_re.compile(
    rf"^{ID_PREFIX_TRANSITION_ID}[0-9a-f]{{64}}$"
)


def make_provenance(
    analysis_mode: str = "synthetic",
) -> AlertProvenanceV1:
    return AlertProvenanceV1(
        analyzer_name="cyt.alert",
        analyzer_version="1.0.0",
        analysis_mode=analysis_mode,
        source_contract_version=SCHEMA_VERSION_V1,
    )


def make_alert(**overrides) -> AlertV1:
    kwargs = {
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
    kwargs.update(overrides)
    return create_alert(**kwargs)


def make_transition(
    alert: Optional[AlertV1] = None,
    **overrides,
) -> AlertTransitionV1:
    if alert is None:
        alert = make_alert()
    kwargs = {
        "hmac_key": HMAC_KEY_A,
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


def make_stateful_transition(
    alert: AlertV1,
    from_state: str,
    to_state: str,
    transitioned_at_us: int,
    previous_transition_id: Optional[str] = None,
    transition_reference: Optional[str] = None,
) -> AlertTransitionV1:
    return create_alert_transition(
        hmac_key=HMAC_KEY_A,
        alert=alert,
        transition_reference=(
            transition_reference if transition_reference is not None else HEX_E
        ),
        previous_transition_id=previous_transition_id,
        from_state=from_state,
        to_state=to_state,
        transitioned_at_us=transitioned_at_us,
        recorded_ingest_timestamp_us=TS_B,
        reason_code="transition.operator_review",
        actor_kind="operator",
        provenance=make_provenance(),
    )


# ── Constants & Exports ───────────────────────────────────────────────

class TestConstants(unittest.TestCase):

    def test_record_kind_constant(self):
        self.assertEqual(ALERT_STATE_PROJECTION_RECORD_KIND, "alert_state_projection")

    def test_public_all(self):
        expected = frozenset({
            "ALERT_STATE_PROJECTION_RECORD_KIND",
            "AlertStateProjectionV1",
            "build_alert_state_projection",
        })
        self.assertEqual(frozenset(EXPORTED_ALL), expected)

    def test_all_exposes_no_private_names(self):
        for name in EXPORTED_ALL:
            self.assertFalse(name.startswith("_"))

    def test_builder_docstring_inclusive(self):
        doc = build_alert_state_projection.__doc__
        self.assertIsNotNone(doc)
        self.assertIn("inclusive", doc.lower())
        self.assertNotIn("exclusive", doc.lower())


# ── AlertStateProjectionV1 dataclass ──────────────────────────────────

class TestAlertStateProjectionV1(unittest.TestCase):

    def _make_params(self, **overrides) -> dict:
        params = {
            "schema_version": SCHEMA_VERSION_V1,
            "record_kind": ALERT_STATE_PROJECTION_RECORD_KIND,
            "alert_id": f"{ID_PREFIX_ALERT_ID}{'a' * 64}",
            "as_of_source_timestamp_us": 1000,
            "current_state": "new",
            "state_entered_at_us": 500,
            "applied_transition_count": 0,
            "applied_tail_transition_id": None,
            "terminal": False,
            "cooldown_expires_at_us": None,
            "cooldown_active": False,
        }
        params.update(overrides)
        return params

    def test_valid_defaults(self):
        p = AlertStateProjectionV1(**self._make_params())
        self.assertIsInstance(p, AlertStateProjectionV1)

    def test_frozen(self):
        p = AlertStateProjectionV1(**self._make_params())
        with self.assertRaises(AttributeError):
            p.current_state = "dismissed"

    def test_schema_version_validation(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(**self._make_params(schema_version="2.0"))

    def test_record_kind_validation(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(**self._make_params(record_kind="wrong"))

    def test_alert_id_validation(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(**self._make_params(alert_id="invalid"))

    def test_alert_id_wrong_prefix(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(
                **self._make_params(alert_id="xxx_v1_" + "a" * 64)
            )

    def test_current_state_in_alerts(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(
                **self._make_params(current_state="invalid_state")
            )

    def test_as_of_rejects_bool(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(
                **self._make_params(as_of_source_timestamp_us=True)
            )

    def test_as_of_rejects_float(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(
                **self._make_params(as_of_source_timestamp_us=1.5)
            )

    def test_as_of_rejects_string(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(
                **self._make_params(as_of_source_timestamp_us="1000")
            )

    def test_state_entered_rejects_bool(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(
                **self._make_params(state_entered_at_us=True)
            )

    def test_state_entered_rejects_float(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(
                **self._make_params(state_entered_at_us=1.5)
            )

    def test_applied_count_rejects_bool(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(
                **self._make_params(applied_transition_count=True)
            )

    def test_applied_count_rejects_float(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(
                **self._make_params(applied_transition_count=1.5)
            )

    def test_applied_count_negative(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(
                **self._make_params(applied_transition_count=-1)
            )

    def test_zero_applied_tail_none(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(
                **self._make_params(
                    applied_transition_count=0,
                    applied_tail_transition_id=(
                        f"{ID_PREFIX_TRANSITION_ID}{'b' * 64}"
                    ),
                )
            )

    def test_positive_applied_tail_not_none(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(
                **self._make_params(
                    applied_transition_count=1,
                    applied_tail_transition_id=None,
                )
            )

    def test_positive_applied_tail_valid_id(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(
                **self._make_params(
                    applied_transition_count=1,
                    applied_tail_transition_id="not_a_transition_id",
                )
            )

    def test_terminal_matches_state(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(
                **self._make_params(
                    current_state="dismissed",
                    terminal=False,
                )
            )

    def test_nonterminal_no_cooldown_expiry(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(
                **self._make_params(
                    current_state="new",
                    terminal=False,
                    cooldown_expires_at_us=2000,
                    cooldown_active=False,
                )
            )

    def test_nonterminal_no_active_cooldown(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(
                **self._make_params(
                    current_state="new",
                    terminal=False,
                    cooldown_expires_at_us=None,
                    cooldown_active=True,
                )
            )

    def test_cooldown_active_requires_terminal(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(
                **self._make_params(
                    current_state="new",
                    terminal=False,
                    cooldown_expires_at_us=2000,
                    cooldown_active=True,
                )
            )

    def test_cooldown_active_requires_as_of_before_expiry(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(
                **self._make_params(
                    current_state="dismissed",
                    terminal=True,
                    cooldown_expires_at_us=100,
                    as_of_source_timestamp_us=200,
                    cooldown_active=True,
                )
            )

    def test_state_entered_not_later_than_as_of(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(
                **self._make_params(
                    state_entered_at_us=2000,
                    as_of_source_timestamp_us=1000,
                )
            )

    def test_terminal_dismissed(self):
        p = AlertStateProjectionV1(**self._make_params(
            current_state="dismissed",
            terminal=True,
            cooldown_expires_at_us=5000,
            cooldown_active=True,
            as_of_source_timestamp_us=4000,
            state_entered_at_us=3000,
            applied_transition_count=1,
            applied_tail_transition_id=(
                f"{ID_PREFIX_TRANSITION_ID}{'c' * 64}"
            ),
        ))
        self.assertTrue(p.terminal)
        self.assertEqual(p.current_state, "dismissed")

    def test_terminal_resolved(self):
        p = AlertStateProjectionV1(**self._make_params(
            current_state="resolved",
            terminal=True,
            cooldown_expires_at_us=6000,
            cooldown_active=False,
            as_of_source_timestamp_us=7000,
            state_entered_at_us=5000,
            applied_transition_count=2,
            applied_tail_transition_id=(
                f"{ID_PREFIX_TRANSITION_ID}{'d' * 64}"
            ),
        ))
        self.assertTrue(p.terminal)
        self.assertEqual(p.current_state, "resolved")

    def test_cooldown_active_exact_boundary_rejected(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(**self._make_params(
                current_state="dismissed",
                terminal=True,
                cooldown_expires_at_us=1000,
                as_of_source_timestamp_us=1000,
                cooldown_active=True,
            ))

    def test_terminal_rejects_int_1(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(**self._make_params(
                current_state="dismissed",
                terminal=1,
                cooldown_expires_at_us=5000,
                cooldown_active=True,
                applied_transition_count=1,
                applied_tail_transition_id=(
                    f"{ID_PREFIX_TRANSITION_ID}{'c' * 64}"
                ),
            ))

    def test_terminal_rejects_int_0(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(**self._make_params(terminal=0))

    def test_cooldown_active_rejects_int_1(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(**self._make_params(
                current_state="dismissed",
                terminal=True,
                cooldown_expires_at_us=5000,
                cooldown_active=1,
                applied_transition_count=1,
                applied_tail_transition_id=(
                    f"{ID_PREFIX_TRANSITION_ID}{'c' * 64}"
                ),
            ))

    def test_cooldown_active_rejects_int_0(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(**self._make_params(
                current_state="dismissed",
                terminal=True,
                cooldown_expires_at_us=5000,
                cooldown_active=0,
                applied_transition_count=1,
                applied_tail_transition_id=(
                    f"{ID_PREFIX_TRANSITION_ID}{'c' * 64}"
                ),
            ))

    def test_terminal_requires_cooldown_expiry(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(**self._make_params(
                current_state="dismissed",
                terminal=True,
                cooldown_expires_at_us=None,
                cooldown_active=False,
                applied_transition_count=1,
                applied_tail_transition_id=(
                    f"{ID_PREFIX_TRANSITION_ID}{'c' * 64}"
                ),
            ))

    def test_cooldown_expiry_rejects_bool(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(**self._make_params(
                current_state="dismissed",
                terminal=True,
                cooldown_expires_at_us=True,
                cooldown_active=False,
                applied_transition_count=1,
                applied_tail_transition_id=(
                    f"{ID_PREFIX_TRANSITION_ID}{'c' * 64}"
                ),
            ))

    def test_cooldown_expiry_rejects_float(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(**self._make_params(
                current_state="dismissed",
                terminal=True,
                cooldown_expires_at_us=1.5,
                cooldown_active=False,
                applied_transition_count=1,
                applied_tail_transition_id=(
                    f"{ID_PREFIX_TRANSITION_ID}{'c' * 64}"
                ),
            ))

    def test_cooldown_expiry_rejects_string(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(**self._make_params(
                current_state="dismissed",
                terminal=True,
                cooldown_expires_at_us="5000",
                cooldown_active=False,
                applied_transition_count=1,
                applied_tail_transition_id=(
                    f"{ID_PREFIX_TRANSITION_ID}{'c' * 64}"
                ),
            ))

    def test_cooldown_expiry_rejects_negative(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(**self._make_params(
                current_state="dismissed",
                terminal=True,
                cooldown_expires_at_us=-1,
                cooldown_active=False,
                applied_transition_count=1,
                applied_tail_transition_id=(
                    f"{ID_PREFIX_TRANSITION_ID}{'c' * 64}"
                ),
            ))

    def test_cooldown_expiry_not_earlier_than_state_entered(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(**self._make_params(
                current_state="dismissed",
                terminal=True,
                state_entered_at_us=2000,
                cooldown_expires_at_us=1000,
                as_of_source_timestamp_us=500,
                cooldown_active=False,
                applied_transition_count=1,
                applied_tail_transition_id=(
                    f"{ID_PREFIX_TRANSITION_ID}{'c' * 64}"
                ),
            ))

    def test_cooldown_active_false_inside_window_rejected(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(**self._make_params(
                current_state="dismissed",
                terminal=True,
                state_entered_at_us=1000,
                cooldown_expires_at_us=2000,
                as_of_source_timestamp_us=1500,
                cooldown_active=False,
                applied_transition_count=1,
                applied_tail_transition_id=(
                    f"{ID_PREFIX_TRANSITION_ID}{'c' * 64}"
                ),
            ))

    def test_cooldown_active_true_at_boundary_rejected(self):
        with self.assertRaises(ValueError):
            AlertStateProjectionV1(**self._make_params(
                current_state="dismissed",
                terminal=True,
                state_entered_at_us=1000,
                cooldown_expires_at_us=2000,
                as_of_source_timestamp_us=2000,
                cooldown_active=True,
                applied_transition_count=1,
                applied_tail_transition_id=(
                    f"{ID_PREFIX_TRANSITION_ID}{'c' * 64}"
                ),
            ))


# ── build_alert_state_projection ─────────────────────────────────────

class TestBuildAlertStateProjection(unittest.TestCase):

    def test_no_transitions(self):
        alert = make_alert()
        projection = build_alert_state_projection(
            alert=alert,
            transitions=(),
            as_of_source_timestamp_us=TS_A,
        )
        self.assertEqual(projection.current_state, "new")
        self.assertEqual(
            projection.state_entered_at_us,
            alert.first_observed_source_timestamp_us,
        )
        self.assertEqual(projection.applied_transition_count, 0)
        self.assertIsNone(projection.applied_tail_transition_id)
        self.assertFalse(projection.terminal)
        self.assertIsNone(projection.cooldown_expires_at_us)
        self.assertFalse(projection.cooldown_active)
        self.assertEqual(projection.alert_id, alert.alert_id)
        self.assertEqual(projection.as_of_source_timestamp_us, TS_A)

    def test_single_transition_before_as_of(self):
        alert = make_alert()
        t1 = make_stateful_transition(
            alert, "new", "acknowledged",
            transitioned_at_us=TS_A + 1000,
        )
        projection = build_alert_state_projection(
            alert=alert,
            transitions=(t1,),
            as_of_source_timestamp_us=TS_A + 2000,
        )
        self.assertEqual(projection.current_state, "acknowledged")
        self.assertEqual(projection.state_entered_at_us, TS_A + 1000)
        self.assertEqual(projection.applied_transition_count, 1)
        self.assertEqual(projection.applied_tail_transition_id, t1.transition_id)
        self.assertFalse(projection.terminal)

    def test_single_transition_exactly_at_as_of(self):
        alert = make_alert()
        t1 = make_stateful_transition(
            alert, "new", "acknowledged",
            transitioned_at_us=TS_A + 1000,
        )
        projection = build_alert_state_projection(
            alert=alert,
            transitions=(t1,),
            as_of_source_timestamp_us=TS_A + 1000,
        )
        self.assertEqual(projection.current_state, "acknowledged")
        self.assertEqual(projection.applied_transition_count, 1)

    def test_single_transition_after_as_of(self):
        alert = make_alert()
        t1 = make_stateful_transition(
            alert, "new", "acknowledged",
            transitioned_at_us=TS_A + 2000,
        )
        projection = build_alert_state_projection(
            alert=alert,
            transitions=(t1,),
            as_of_source_timestamp_us=TS_A + 1000,
        )
        self.assertEqual(projection.current_state, "new")
        self.assertEqual(projection.applied_transition_count, 0)
        self.assertIsNone(projection.applied_tail_transition_id)

    def test_between_transitions(self):
        alert = make_alert()
        t1 = make_stateful_transition(
            alert, "new", "acknowledged",
            transitioned_at_us=TS_A + 1000,
        )
        t2 = make_stateful_transition(
            alert, "acknowledged", "observing",
            transitioned_at_us=TS_A + 3000,
            previous_transition_id=t1.transition_id,
            transition_reference=HEX_D,
        )
        projection = build_alert_state_projection(
            alert=alert,
            transitions=(t1, t2),
            as_of_source_timestamp_us=TS_A + 2000,
        )
        self.assertEqual(projection.current_state, "acknowledged")
        self.assertEqual(projection.applied_transition_count, 1)

    def test_after_all_transitions(self):
        alert = make_alert()
        t1 = make_stateful_transition(
            alert, "new", "acknowledged",
            transitioned_at_us=TS_A + 1000,
        )
        t2 = make_stateful_transition(
            alert, "acknowledged", "observing",
            transitioned_at_us=TS_A + 3000,
            previous_transition_id=t1.transition_id,
            transition_reference=HEX_D,
        )
        projection = build_alert_state_projection(
            alert=alert,
            transitions=(t1, t2),
            as_of_source_timestamp_us=TS_A + 5000,
        )
        self.assertEqual(projection.current_state, "observing")
        self.assertEqual(projection.applied_transition_count, 2)

    def test_multi_transition_chain(self):
        alert = make_alert()
        t1 = make_stateful_transition(
            alert, "new", "acknowledged",
            transitioned_at_us=TS_A + 1000,
        )
        t2 = make_stateful_transition(
            alert, "acknowledged", "observing",
            transitioned_at_us=TS_A + 2000,
            previous_transition_id=t1.transition_id,
            transition_reference=HEX_D,
        )
        t3 = make_stateful_transition(
            alert, "observing", "escalated",
            transitioned_at_us=TS_A + 3000,
            previous_transition_id=t2.transition_id,
            transition_reference=HEX_C,
        )
        projection = build_alert_state_projection(
            alert=alert,
            transitions=(t1, t2, t3),
            as_of_source_timestamp_us=TS_A + 5000,
        )
        self.assertEqual(projection.current_state, "escalated")
        self.assertEqual(projection.applied_transition_count, 3)
        self.assertEqual(
            projection.applied_tail_transition_id, t3.transition_id
        )

    def test_tuple_order_independence(self):
        alert = make_alert()
        t1 = make_stateful_transition(
            alert, "new", "acknowledged",
            transitioned_at_us=TS_A + 1000,
        )
        t2 = make_stateful_transition(
            alert, "acknowledged", "observing",
            transitioned_at_us=TS_A + 2000,
            previous_transition_id=t1.transition_id,
            transition_reference=HEX_D,
        )
        t3 = make_stateful_transition(
            alert, "observing", "escalated",
            transitioned_at_us=TS_A + 3000,
            previous_transition_id=t2.transition_id,
            transition_reference=HEX_C,
        )
        p1 = build_alert_state_projection(
            alert=alert,
            transitions=(t1, t2, t3),
            as_of_source_timestamp_us=TS_A + 5000,
        )
        p2 = build_alert_state_projection(
            alert=alert,
            transitions=(t3, t1, t2),
            as_of_source_timestamp_us=TS_A + 5000,
        )
        self.assertEqual(p1.current_state, p2.current_state)
        self.assertEqual(
            p1.applied_transition_count, p2.applied_transition_count
        )
        self.assertEqual(
            p1.applied_tail_transition_id, p2.applied_tail_transition_id
        )
        self.assertEqual(p1.state_entered_at_us, p2.state_entered_at_us)

    def test_equal_timestamp_structural_order(self):
        alert = make_alert()
        t1 = make_stateful_transition(
            alert, "new", "acknowledged",
            transitioned_at_us=TS_A + 1000,
        )
        t2 = make_stateful_transition(
            alert, "acknowledged", "observing",
            transitioned_at_us=TS_A + 1000,
            previous_transition_id=t1.transition_id,
            transition_reference=HEX_D,
        )
        t3 = make_stateful_transition(
            alert, "observing", "escalated",
            transitioned_at_us=TS_A + 1000,
            previous_transition_id=t2.transition_id,
            transition_reference=HEX_C,
        )
        projection = build_alert_state_projection(
            alert=alert,
            transitions=(t1, t2, t3),
            as_of_source_timestamp_us=TS_A + 1000,
        )
        self.assertEqual(projection.current_state, "escalated")
        self.assertEqual(projection.applied_transition_count, 3)
        self.assertEqual(
            projection.applied_tail_transition_id, t3.transition_id
        )
        self.assertEqual(projection.state_entered_at_us, TS_A + 1000)

    def test_equal_timestamp_partial_application(self):
        alert = make_alert()
        t1 = make_stateful_transition(
            alert, "new", "acknowledged",
            transitioned_at_us=TS_A + 1000,
        )
        t2 = make_stateful_transition(
            alert, "acknowledged", "observing",
            transitioned_at_us=TS_A + 1000,
            previous_transition_id=t1.transition_id,
            transition_reference=HEX_D,
        )
        t3 = make_stateful_transition(
            alert, "observing", "escalated",
            transitioned_at_us=TS_A + 2000,
            previous_transition_id=t2.transition_id,
            transition_reference=HEX_C,
        )
        projection = build_alert_state_projection(
            alert=alert,
            transitions=(t1, t2, t3),
            as_of_source_timestamp_us=TS_A + 1000,
        )
        self.assertEqual(projection.current_state, "observing")
        self.assertEqual(projection.applied_transition_count, 2)
        self.assertEqual(
            projection.applied_tail_transition_id, t2.transition_id
        )

    def test_ids_ordered_opposite_to_chain_order(self):
        alert = make_alert()
        provenance = make_provenance()
        t1 = AlertTransitionV1(
            schema_version=SCHEMA_VERSION_V1,
            record_kind="alert_transition",
            transition_id="atr_v1_" + "f" * 64,
            alert_id=alert.alert_id,
            transition_reference=HEX_A,
            previous_transition_id=None,
            from_state="new",
            to_state="acknowledged",
            transitioned_at_us=TS_A + 1000,
            recorded_ingest_timestamp_us=TS_B,
            reason_code="transition.operator_review",
            actor_kind="operator",
            provenance=provenance,
        )
        t2 = AlertTransitionV1(
            schema_version=SCHEMA_VERSION_V1,
            record_kind="alert_transition",
            transition_id="atr_v1_" + "a" * 64,
            alert_id=alert.alert_id,
            transition_reference=HEX_B,
            previous_transition_id=t1.transition_id,
            from_state="acknowledged",
            to_state="observing",
            transitioned_at_us=TS_A + 2000,
            recorded_ingest_timestamp_us=TS_B,
            reason_code="transition.operator_review",
            actor_kind="operator",
            provenance=provenance,
        )
        projection = build_alert_state_projection(
            alert=alert,
            transitions=(t2, t1),
            as_of_source_timestamp_us=TS_A + 5000,
        )
        self.assertEqual(projection.current_state, "observing")
        self.assertEqual(projection.applied_transition_count, 2)
        self.assertEqual(
            projection.applied_tail_transition_id, t2.transition_id
        )

    def test_historical_as_of_with_future_chain(self):
        alert = make_alert()
        t1 = make_stateful_transition(
            alert, "new", "acknowledged",
            transitioned_at_us=TS_A + 1000,
        )
        t2 = make_stateful_transition(
            alert, "acknowledged", "observing",
            transitioned_at_us=TS_A + 2000,
            previous_transition_id=t1.transition_id,
            transition_reference=HEX_D,
        )
        t3 = make_stateful_transition(
            alert, "observing", "escalated",
            transitioned_at_us=TS_A + 3000,
            previous_transition_id=t2.transition_id,
            transition_reference=HEX_C,
        )
        projection = build_alert_state_projection(
            alert=alert,
            transitions=(t1, t2, t3),
            as_of_source_timestamp_us=TS_A + 1500,
        )
        self.assertEqual(projection.current_state, "acknowledged")
        self.assertEqual(projection.applied_transition_count, 1)

    def test_terminal_dismissed(self):
        alert = make_alert()
        t1 = make_stateful_transition(
            alert, "new", "dismissed",
            transitioned_at_us=TS_A + 1000,
        )
        projection = build_alert_state_projection(
            alert=alert,
            transitions=(t1,),
            as_of_source_timestamp_us=TS_A + 2000,
        )
        self.assertEqual(projection.current_state, "dismissed")
        self.assertTrue(projection.terminal)
        expected_expiry = cooldown_expires_at_us(alert, t1)
        self.assertEqual(
            projection.cooldown_expires_at_us, expected_expiry
        )

    def test_terminal_resolved(self):
        alert = make_alert()
        t1 = make_stateful_transition(
            alert, "new", "acknowledged",
            transitioned_at_us=TS_A + 1000,
        )
        t2 = make_stateful_transition(
            alert, "acknowledged", "resolved",
            transitioned_at_us=TS_A + 2000,
            previous_transition_id=t1.transition_id,
            transition_reference=HEX_D,
        )
        projection = build_alert_state_projection(
            alert=alert,
            transitions=(t1, t2),
            as_of_source_timestamp_us=TS_A + 3000,
        )
        self.assertEqual(projection.current_state, "resolved")
        self.assertTrue(projection.terminal)
        expected_expiry = cooldown_expires_at_us(alert, t2)
        self.assertEqual(
            projection.cooldown_expires_at_us, expected_expiry
        )

    def test_cooldown_inside_window(self):
        alert = make_alert(cooldown_us=1_000_000)
        t1 = make_stateful_transition(
            alert, "new", "dismissed",
            transitioned_at_us=TS_A + 1000,
        )
        projection = build_alert_state_projection(
            alert=alert,
            transitions=(t1,),
            as_of_source_timestamp_us=TS_A + 1500,
        )
        self.assertTrue(projection.cooldown_active)
        self.assertEqual(
            projection.cooldown_expires_at_us, TS_A + 1000 + 1_000_000
        )

    def test_cooldown_exact_boundary(self):
        alert = make_alert(cooldown_us=1_000_000)
        t1 = make_stateful_transition(
            alert, "new", "dismissed",
            transitioned_at_us=TS_A + 1000,
        )
        projection = build_alert_state_projection(
            alert=alert,
            transitions=(t1,),
            as_of_source_timestamp_us=TS_A + 1000 + 1_000_000,
        )
        self.assertFalse(projection.cooldown_active)

    def test_cooldown_after_boundary(self):
        alert = make_alert(cooldown_us=1_000_000)
        t1 = make_stateful_transition(
            alert, "new", "dismissed",
            transitioned_at_us=TS_A + 1000,
        )
        projection = build_alert_state_projection(
            alert=alert,
            transitions=(t1,),
            as_of_source_timestamp_us=TS_A + 1000 + 1_000_000 + 1,
        )
        self.assertFalse(projection.cooldown_active)

    def test_cooldown_zero_duration(self):
        alert = make_alert(cooldown_us=0)
        t1 = make_stateful_transition(
            alert, "new", "dismissed",
            transitioned_at_us=TS_A + 1000,
        )
        projection = build_alert_state_projection(
            alert=alert,
            transitions=(t1,),
            as_of_source_timestamp_us=TS_A + 1000,
        )
        self.assertFalse(projection.cooldown_active)
        self.assertEqual(
            projection.cooldown_expires_at_us, TS_A + 1000
        )

    def test_source_objects_unchanged(self):
        alert = make_alert()
        t1 = make_stateful_transition(
            alert, "new", "acknowledged",
            transitioned_at_us=TS_A + 1000,
        )
        orig_alert_id = alert.alert_id
        orig_t1_id = t1.transition_id
        build_alert_state_projection(
            alert=alert,
            transitions=(t1,),
            as_of_source_timestamp_us=TS_A + 2000,
        )
        self.assertEqual(alert.alert_id, orig_alert_id)
        self.assertEqual(t1.transition_id, orig_t1_id)
        self.assertEqual(t1.from_state, "new")

    def test_frozen_projection_record(self):
        alert = make_alert()
        projection = build_alert_state_projection(
            alert=alert,
            transitions=(),
            as_of_source_timestamp_us=TS_A,
        )
        with self.assertRaises(AttributeError):
            projection.current_state = "dismissed"

    def test_bool_timestamp_rejected(self):
        alert = make_alert()
        with self.assertRaises(ValueError):
            build_alert_state_projection(
                alert=alert,
                transitions=(),
                as_of_source_timestamp_us=True,
            )

    def test_float_timestamp_rejected(self):
        alert = make_alert()
        with self.assertRaises(ValueError):
            build_alert_state_projection(
                alert=alert,
                transitions=(),
                as_of_source_timestamp_us=1.5,
            )

    def test_string_timestamp_rejected(self):
        alert = make_alert()
        with self.assertRaises(ValueError):
            build_alert_state_projection(
                alert=alert,
                transitions=(),
                as_of_source_timestamp_us="1000",
            )

    def test_negative_timestamp_rejected(self):
        alert = make_alert()
        with self.assertRaises(ValueError):
            build_alert_state_projection(
                alert=alert,
                transitions=(),
                as_of_source_timestamp_us=-1,
            )

    def test_as_of_before_first_observed_rejected(self):
        alert = make_alert(first_observed_source_timestamp_us=TS_A + 1000)
        with self.assertRaises(ValueError):
            build_alert_state_projection(
                alert=alert,
                transitions=(),
                as_of_source_timestamp_us=TS_A,
            )

    def test_list_instead_of_tuple_rejected(self):
        alert = make_alert()
        with self.assertRaises(ValueError):
            build_alert_state_projection(
                alert=alert,
                transitions=[],  # type: ignore
                as_of_source_timestamp_us=TS_A,
            )

    def test_wrong_element_type_rejected(self):
        alert = make_alert()
        with self.assertRaises(ValueError):
            build_alert_state_projection(
                alert=alert,
                transitions=("not_a_transition",),  # type: ignore
                as_of_source_timestamp_us=TS_A,
            )

    def test_wrong_alert_id_rejected(self):
        alert_a = make_alert()
        alert_b = make_alert(subject_reference=HEX_D)
        t = make_stateful_transition(
            alert_b, "new", "acknowledged",
            transitioned_at_us=TS_A + 1000,
        )
        with self.assertRaises(ValueError):
            build_alert_state_projection(
                alert=alert_a,
                transitions=(t,),
                as_of_source_timestamp_us=TS_A + 2000,
            )

    def test_duplicate_transition_id_rejected(self):
        alert = make_alert()
        t1 = make_stateful_transition(
            alert, "new", "acknowledged",
            transitioned_at_us=TS_A + 1000,
        )
        t2 = make_stateful_transition(
            alert, "new", "acknowledged",
            transitioned_at_us=TS_A + 2000,
            transition_reference=HEX_D,
        )
        t2_bad = AlertTransitionV1(
            schema_version=t2.schema_version,
            record_kind=t2.record_kind,
            transition_id=t1.transition_id,
            alert_id=t2.alert_id,
            transition_reference=t2.transition_reference,
            previous_transition_id=t2.previous_transition_id,
            from_state=t2.from_state,
            to_state=t2.to_state,
            transitioned_at_us=t2.transitioned_at_us,
            recorded_ingest_timestamp_us=t2.recorded_ingest_timestamp_us,
            reason_code=t2.reason_code,
            actor_kind=t2.actor_kind,
            provenance=t2.provenance,
        )
        with self.assertRaises(ValueError):
            build_alert_state_projection(
                alert=alert,
                transitions=(t1, t2_bad),
                as_of_source_timestamp_us=TS_A + 5000,
            )

    def test_missing_predecessor_rejected(self):
        alert = make_alert()
        t1 = make_stateful_transition(
            alert, "new", "acknowledged",
            transitioned_at_us=TS_A + 1000,
        )
        valid_hex = "0" * 64
        provenance = make_provenance()
        t2 = AlertTransitionV1(
            schema_version=SCHEMA_VERSION_V1,
            record_kind="alert_transition",
            transition_id="atr_v1_" + "1" * 64,
            alert_id=alert.alert_id,
            transition_reference=HEX_D,
            previous_transition_id="atr_v1_" + valid_hex,
            from_state="acknowledged",
            to_state="observing",
            transitioned_at_us=TS_A + 2000,
            recorded_ingest_timestamp_us=TS_B,
            reason_code="transition.operator_review",
            actor_kind="operator",
            provenance=provenance,
        )
        with self.assertRaises(ValueError):
            build_alert_state_projection(
                alert=alert,
                transitions=(t1, t2),
                as_of_source_timestamp_us=TS_A + 5000,
            )

    def test_multiple_roots_rejected(self):
        alert = make_alert()
        t1 = make_stateful_transition(
            alert, "new", "acknowledged",
            transitioned_at_us=TS_A + 1000,
        )
        t2 = make_stateful_transition(
            alert, "new", "acknowledged",
            transitioned_at_us=TS_A + 2000,
            transition_reference=HEX_D,
        )
        with self.assertRaises(ValueError):
            build_alert_state_projection(
                alert=alert,
                transitions=(t1, t2),
                as_of_source_timestamp_us=TS_A + 5000,
            )

    def test_fork_rejected(self):
        alert = make_alert()
        t1 = make_stateful_transition(
            alert, "new", "acknowledged",
            transitioned_at_us=TS_A + 1000,
        )
        t2 = make_stateful_transition(
            alert, "acknowledged", "observing",
            transitioned_at_us=TS_A + 2000,
            previous_transition_id=t1.transition_id,
            transition_reference=HEX_D,
        )
        t3 = make_stateful_transition(
            alert, "acknowledged", "escalated",
            transitioned_at_us=TS_A + 2000,
            previous_transition_id=t1.transition_id,
            transition_reference=HEX_C,
        )
        with self.assertRaises(ValueError):
            build_alert_state_projection(
                alert=alert,
                transitions=(t1, t2, t3),
                as_of_source_timestamp_us=TS_A + 5000,
            )

    def test_disconnected_component_rejected(self):
        alert = make_alert()
        provenance = make_provenance()
        root = AlertTransitionV1(
            schema_version=SCHEMA_VERSION_V1,
            record_kind="alert_transition",
            transition_id="atr_v1_" + "0" * 64,
            alert_id=alert.alert_id,
            transition_reference=HEX_A,
            previous_transition_id=None,
            from_state="new",
            to_state="acknowledged",
            transitioned_at_us=TS_A + 1000,
            recorded_ingest_timestamp_us=TS_B,
            reason_code="transition.operator_review",
            actor_kind="operator",
            provenance=provenance,
        )
        cycle_a = AlertTransitionV1(
            schema_version=SCHEMA_VERSION_V1,
            record_kind="alert_transition",
            transition_id="atr_v1_" + "a" * 64,
            alert_id=alert.alert_id,
            transition_reference=HEX_B,
            previous_transition_id="atr_v1_" + "b" * 64,
            from_state="observing",
            to_state="escalated",
            transitioned_at_us=TS_A + 2000,
            recorded_ingest_timestamp_us=TS_B,
            reason_code="transition.operator_review",
            actor_kind="operator",
            provenance=provenance,
        )
        cycle_b = AlertTransitionV1(
            schema_version=SCHEMA_VERSION_V1,
            record_kind="alert_transition",
            transition_id="atr_v1_" + "b" * 64,
            alert_id=alert.alert_id,
            transition_reference=HEX_C,
            previous_transition_id="atr_v1_" + "a" * 64,
            from_state="escalated",
            to_state="observing",
            transitioned_at_us=TS_A + 3000,
            recorded_ingest_timestamp_us=TS_B,
            reason_code="transition.operator_review",
            actor_kind="operator",
            provenance=provenance,
        )
        with self.assertRaises(ValueError):
            build_alert_state_projection(
                alert=alert,
                transitions=(root, cycle_a, cycle_b),
                as_of_source_timestamp_us=TS_A + 5000,
            )

    def test_zero_root_cycle_rejected(self):
        alert = make_alert()
        provenance = make_provenance()
        t1 = AlertTransitionV1(
            schema_version=SCHEMA_VERSION_V1,
            record_kind="alert_transition",
            transition_id="atr_v1_" + "a" * 64,
            alert_id=alert.alert_id,
            transition_reference=HEX_A,
            previous_transition_id="atr_v1_" + "c" * 64,
            from_state="acknowledged",
            to_state="observing",
            transitioned_at_us=TS_A + 1000,
            recorded_ingest_timestamp_us=TS_B,
            reason_code="transition.operator_review",
            actor_kind="operator",
            provenance=provenance,
        )
        t2 = AlertTransitionV1(
            schema_version=SCHEMA_VERSION_V1,
            record_kind="alert_transition",
            transition_id="atr_v1_" + "b" * 64,
            alert_id=alert.alert_id,
            transition_reference=HEX_B,
            previous_transition_id=t1.transition_id,
            from_state="observing",
            to_state="escalated",
            transitioned_at_us=TS_A + 2000,
            recorded_ingest_timestamp_us=TS_B,
            reason_code="transition.operator_review",
            actor_kind="operator",
            provenance=provenance,
        )
        t3 = AlertTransitionV1(
            schema_version=SCHEMA_VERSION_V1,
            record_kind="alert_transition",
            transition_id="atr_v1_" + "c" * 64,
            alert_id=alert.alert_id,
            transition_reference=HEX_C,
            previous_transition_id=t2.transition_id,
            from_state="escalated",
            to_state="observing",
            transitioned_at_us=TS_A + 3000,
            recorded_ingest_timestamp_us=TS_B,
            reason_code="transition.operator_review",
            actor_kind="operator",
            provenance=provenance,
        )
        with self.assertRaises(ValueError):
            build_alert_state_projection(
                alert=alert,
                transitions=(t1, t2, t3),
                as_of_source_timestamp_us=TS_A + 5000,
            )

    def test_transition_before_alert_first_observed_rejected(self):
        alert = make_alert(first_observed_source_timestamp_us=TS_A + 5000)
        t1 = make_stateful_transition(
            alert, "new", "acknowledged",
            transitioned_at_us=TS_A + 1000,
        )
        with self.assertRaises(ValueError):
            build_alert_state_projection(
                alert=alert,
                transitions=(t1,),
                as_of_source_timestamp_us=TS_A + 10000,
            )

    def test_alert_type_check(self):
        with self.assertRaises(ValueError):
            build_alert_state_projection(
                alert="not_an_alert",  # type: ignore
                transitions=(),
                as_of_source_timestamp_us=TS_A,
            )

    def test_transitions_type_check(self):
        alert = make_alert()
        with self.assertRaises(ValueError):
            build_alert_state_projection(
                alert=alert,
                transitions="not_a_tuple",  # type: ignore
                as_of_source_timestamp_us=TS_A,
            )

    def test_zero_roots_rejected(self):
        alert = make_alert()
        provenance = make_provenance()
        t1 = AlertTransitionV1(
            schema_version=SCHEMA_VERSION_V1,
            record_kind="alert_transition",
            transition_id="atr_v1_" + "1" * 64,
            alert_id=alert.alert_id,
            transition_reference=HEX_A,
            previous_transition_id="atr_v1_" + "2" * 64,
            from_state="acknowledged",
            to_state="observing",
            transitioned_at_us=TS_A + 2000,
            recorded_ingest_timestamp_us=TS_B,
            reason_code="transition.operator_review",
            actor_kind="operator",
            provenance=provenance,
        )
        with self.assertRaises(ValueError):
            build_alert_state_projection(
                alert=alert,
                transitions=(t1,),
                as_of_source_timestamp_us=TS_A + 5000,
            )


# ── AST purity checks ─────────────────────────────────────────────────

class TestModulePurity(unittest.TestCase):

    def test_no_forbidden_imports(self):
        with open("alert_projection.py") as f:
            tree = ast.parse(f.read())
        forbidden_imports = {
            "sqlite3",
            "time",
            "datetime",
            "os",
            "sys",
            "socket",
            "subprocess",
            "threading",
            "tkinter",
            "kismet",
            "eventbus",
            "requests",
            "http",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    self.assertNotIn(
                        top, forbidden_imports,
                        f"forbidden import: {alias.name}",
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module is not None:
                    top = node.module.split(".")[0]
                    self.assertNotIn(
                        top, forbidden_imports,
                        f"forbidden import: {node.module}",
                    )

    def test_no_print(self):
        with open("alert_projection.py") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "print":
                    self.fail("print call found in alert_projection.py")

    def test_no_eval_or_exec(self):
        with open("alert_projection.py") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    self.assertNotEqual(node.func.id, "eval")
                    self.assertNotEqual(node.func.id, "exec")

    def test_no_network_or_persistence_names(self):
        with open("alert_projection.py") as f:
            tree = ast.parse(f.read())
        bad = {"sqlite3", "SQLite", "kismet", "Kismet", "Eventbus",
               "threading", "Thread", "subprocess", "socket", "connect"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                self.assertNotIn(node.id, bad)
            if isinstance(node, ast.Attribute):
                self.assertNotIn(node.attr, bad)

    def test_no_mutable_module_state(self):
        with open("alert_projection.py") as f:
            tree = ast.parse(f.read())
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and not target.id.startswith("_"):
                        if target.id.isupper():
                            continue
                        self.fail(
                            f"non-private module-level assignment: {target.id}"
                        )

    def test_no_cached_or_notification_state(self):
        with open("alert_projection.py") as f:
            source = f.read()
        self.assertNotIn("_cached", source)
        self.assertNotIn("_notification", source)
        self.assertNotIn("_narrative", source)
        self.assertNotIn("_threat", source)
        self.assertNotIn("_intent", source)
        self.assertNotIn("_probability", source)
        self.assertNotIn("_confidence", source)

    def test_no_wall_clock_or_runtime(self):
        with open("alert_projection.py") as f:
            source = f.read()
        self.assertNotIn("time.time", source)
        self.assertNotIn("datetime.now", source)
        self.assertNotIn("datetime.utcnow", source)
        self.assertNotIn("perf_counter", source)
        self.assertNotIn("monotonic", source)

    def test_project_class_has_no_forbidden_fields(self):
        forbidden = {"_narrative", "_threat", "_intent",
                     "_probability", "_confidence", "_cached",
                     "_notification", "_mutable"}
        for attr in dir(AlertStateProjectionV1):
            for bad in forbidden:
                self.assertNotEqual(attr, bad)

    def test_no_eventbus_references(self):
        with open("alert_projection.py") as f:
            source = f.read()
        self.assertNotIn("eventbus", source.lower())
        self.assertNotIn("EventBus", source)
        self.assertNotIn("event_bus", source)


if __name__ == "__main__":
    unittest.main()
