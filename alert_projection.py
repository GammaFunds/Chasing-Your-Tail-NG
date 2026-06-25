"""Alert State Projection v1 — pure deterministic derived state."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Tuple

from alert_contract import (
    ID_PREFIX_ALERT_ID,
    ID_PREFIX_TRANSITION_ID,
    SCHEMA_VERSION_V1,
    ALERT_STATES,
    TERMINAL_STATES,
    AlertV1,
    AlertTransitionV1,
    validate_alert_transition_predecessor,
    cooldown_expires_at_us,
    is_within_alert_cooldown,
)


ALERT_STATE_PROJECTION_RECORD_KIND = "alert_state_projection"

_ALERT_ID_RE = re.compile(rf"^{ID_PREFIX_ALERT_ID}[0-9a-f]{{64}}$")
_TRANSITION_ID_RE = re.compile(rf"^{ID_PREFIX_TRANSITION_ID}[0-9a-f]{{64}}$")


def _check_non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be a non-negative integer")
    if value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


@dataclass(frozen=True)
class AlertStateProjectionV1:
    """Immutable alert state projection record."""

    schema_version: str
    record_kind: str
    alert_id: str
    as_of_source_timestamp_us: int
    current_state: str
    state_entered_at_us: int
    applied_transition_count: int
    applied_tail_transition_id: Optional[str]
    terminal: bool
    cooldown_expires_at_us: Optional[int]
    cooldown_active: bool

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION_V1:
            raise ValueError('schema_version must be exactly "1.0"')
        if self.record_kind != ALERT_STATE_PROJECTION_RECORD_KIND:
            raise ValueError(
                'record_kind must be exactly "alert_state_projection"'
            )
        if _ALERT_ID_RE.fullmatch(self.alert_id) is None:
            raise ValueError("invalid alert_id")
        if self.current_state not in ALERT_STATES:
            raise ValueError("invalid current_state")
        _check_non_negative_int(
            "as_of_source_timestamp_us", self.as_of_source_timestamp_us
        )
        _check_non_negative_int(
            "state_entered_at_us", self.state_entered_at_us
        )
        _check_non_negative_int(
            "applied_transition_count", self.applied_transition_count
        )
        if (
            self.applied_transition_count == 0
            and self.applied_tail_transition_id is not None
        ):
            raise ValueError(
                "zero applied transitions must have None tail"
            )
        if self.applied_transition_count > 0:
            if self.applied_tail_transition_id is None:
                raise ValueError(
                    "positive applied transitions must have a tail"
                )
            if _TRANSITION_ID_RE.fullmatch(
                self.applied_tail_transition_id
            ) is None:
                raise ValueError("invalid applied_tail_transition_id")
        if type(self.terminal) is not bool:
            raise ValueError("terminal must be a bool")
        if type(self.cooldown_active) is not bool:
            raise ValueError("cooldown_active must be a bool")
        if self.terminal != (self.current_state in TERMINAL_STATES):
            raise ValueError(
                "terminal must match current_state membership in "
                "TERMINAL_STATES"
            )
        if self.cooldown_expires_at_us is not None:
            _check_non_negative_int(
                "cooldown_expires_at_us", self.cooldown_expires_at_us
            )
        if self.terminal:
            if self.cooldown_expires_at_us is None:
                raise ValueError(
                    "terminal projection must have cooldown_expires_at_us"
                )
            if self.cooldown_expires_at_us < self.state_entered_at_us:
                raise ValueError(
                    "cooldown_expires_at_us must not be earlier than "
                    "state_entered_at_us"
                )
            if self.cooldown_active != (
                self.as_of_source_timestamp_us < self.cooldown_expires_at_us
            ):
                raise ValueError(
                    "cooldown_active must equal "
                    "as_of_source_timestamp_us < cooldown_expires_at_us"
                )
        else:
            if self.cooldown_expires_at_us is not None:
                raise ValueError(
                    "non-terminal must not have cooldown_expires_at_us"
                )
            if self.cooldown_active:
                raise ValueError(
                    "non-terminal must not have active cooldown"
                )
        if self.state_entered_at_us > self.as_of_source_timestamp_us:
            raise ValueError(
                "state_entered_at_us must not be later than "
                "as_of_source_timestamp_us"
            )


def build_alert_state_projection(
    *,
    alert: AlertV1,
    transitions: tuple[AlertTransitionV1, ...],
    as_of_source_timestamp_us: int,
) -> AlertStateProjectionV1:
    """Build an immutable alert state projection.

    Parameters
    ----------
    alert : AlertV1
        The source alert to project from.
    transitions : tuple[AlertTransitionV1, ...]
        Immutable supply of transition records that may or may not
        form a complete chain for the alert.
    as_of_source_timestamp_us : int
        Inclusive source timestamp for the projection.
        A transition is applied when its transitioned_at_us is
        less than or equal to this value.

    Returns
    -------
    AlertStateProjectionV1
    """

    if type(alert) is not AlertV1:
        raise ValueError("alert must be AlertV1")

    if type(transitions) is not tuple:
        raise ValueError("transitions must be a tuple")

    for t in transitions:
        if type(t) is not AlertTransitionV1:
            raise ValueError("each transition must be AlertTransitionV1")

    if (
        isinstance(as_of_source_timestamp_us, bool)
        or not isinstance(as_of_source_timestamp_us, int)
        or as_of_source_timestamp_us < 0
    ):
        raise ValueError(
            "as_of_source_timestamp_us must be a non-negative integer"
        )

    if as_of_source_timestamp_us < alert.first_observed_source_timestamp_us:
        raise ValueError(
            "as_of_source_timestamp_us must not precede alert "
            "first_observed_source_timestamp_us"
        )

    if len(transitions) == 0:
        return _initial_projection(alert, as_of_source_timestamp_us)

    by_id: dict[str, AlertTransitionV1] = {}
    for t in transitions:
        if t.transition_id in by_id:
            raise ValueError("duplicate transition_id")
        by_id[t.transition_id] = t

    for t in transitions:
        if t.alert_id != alert.alert_id:
            raise ValueError("transition alert_id does not match alert")

    children: dict[Optional[str], list[AlertTransitionV1]] = {}
    for t in transitions:
        pid = t.previous_transition_id
        if pid not in children:
            children[pid] = []
        children[pid].append(t)

    roots = children.get(None, [])
    if len(roots) != 1:
        raise ValueError("must have exactly one root transition")

    root = roots[0]

    validate_alert_transition_predecessor(root, None)

    if root.transitioned_at_us < alert.first_observed_source_timestamp_us:
        raise ValueError(
            "root transitioned_at_us must not precede alert "
            "first_observed_source_timestamp_us"
        )

    for t in transitions:
        if t.previous_transition_id is not None:
            if t.previous_transition_id not in by_id:
                raise ValueError("missing predecessor")

    ordered: list[AlertTransitionV1] = []
    visited: set[str] = set()
    current: Optional[AlertTransitionV1] = root
    while current is not None:
        if current.transition_id in visited:
            raise ValueError("cycle detected")
        visited.add(current.transition_id)
        ordered.append(current)
        cid = current.transition_id
        child_list = children.get(cid, [])
        if len(child_list) > 1:
            raise ValueError("fork detected")
        if len(child_list) == 1:
            child = child_list[0]
            validate_alert_transition_predecessor(child, current)
            current = child
        else:
            current = None

    if len(visited) != len(transitions):
        raise ValueError("disconnected chain")

    applied: list[AlertTransitionV1] = []
    for t in ordered:
        if t.transitioned_at_us <= as_of_source_timestamp_us:
            applied.append(t)

    if len(applied) == 0:
        return _initial_projection(alert, as_of_source_timestamp_us)

    last = applied[-1]
    current_state = last.to_state
    terminal = current_state in TERMINAL_STATES

    if terminal:
        cooldown_expiry = cooldown_expires_at_us(alert, last)
        cooldown_active_flag = is_within_alert_cooldown(
            alert, last, as_of_source_timestamp_us
        )
    else:
        cooldown_expiry = None
        cooldown_active_flag = False

    return AlertStateProjectionV1(
        schema_version=SCHEMA_VERSION_V1,
        record_kind=ALERT_STATE_PROJECTION_RECORD_KIND,
        alert_id=alert.alert_id,
        as_of_source_timestamp_us=as_of_source_timestamp_us,
        current_state=current_state,
        state_entered_at_us=last.transitioned_at_us,
        applied_transition_count=len(applied),
        applied_tail_transition_id=last.transition_id,
        terminal=terminal,
        cooldown_expires_at_us=cooldown_expiry,
        cooldown_active=cooldown_active_flag,
    )


def _initial_projection(
    alert: AlertV1,
    as_of_source_timestamp_us: int,
) -> AlertStateProjectionV1:
    return AlertStateProjectionV1(
        schema_version=SCHEMA_VERSION_V1,
        record_kind=ALERT_STATE_PROJECTION_RECORD_KIND,
        alert_id=alert.alert_id,
        as_of_source_timestamp_us=as_of_source_timestamp_us,
        current_state=alert.initial_state,
        state_entered_at_us=alert.first_observed_source_timestamp_us,
        applied_transition_count=0,
        applied_tail_transition_id=None,
        terminal=alert.initial_state in TERMINAL_STATES,
        cooldown_expires_at_us=None,
        cooldown_active=False,
    )


__all__ = [
    "ALERT_STATE_PROJECTION_RECORD_KIND",
    "AlertStateProjectionV1",
    "build_alert_state_projection",
]
