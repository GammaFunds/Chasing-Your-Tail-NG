"""Caller-driven recovery-policy boundary for KismetEventbusRuntime.

This module defines a bounded recovery policy that controls when
KismetEventbusRuntime.recover() is invoked, enforcing a budget of
consecutive attempts with a cooldown period.

KismetEventbusRecoveryPolicyV1 does not directly create sockets, open
files, access environment variables, handle credentials, log, print,
create threads, timers, polling loops, signals, subprocesses, or
daemons.  Calling runtime.recover() may indirectly invoke transport
start, stop, or restart and may therefore cause worker-thread and
network activity in productive use.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from kismet_eventbus_runtime import (
    KismetEventbusRuntime,
    KismetEventbusRuntimeHealthV1,
)


__all__ = (
    "KismetEventbusRecoveryPolicyError",
    "KismetEventbusRecoveryPolicyResultV1",
    "KismetEventbusRecoveryPolicyV1",
)


class KismetEventbusRecoveryPolicyError(RuntimeError):
    """Raised for policy-operation contention or monotonic-time regression."""


_VALID_OUTCOMES = frozenset({
    "not_required",
    "transition_deferred",
    "budget_cooldown",
    "recover_invoked",
})


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class KismetEventbusRecoveryPolicyResultV1:
    """Frozen, slotted, content-free recovery-policy result.

    repr() and str() return KismetEventbusRecoveryPolicyResultV1() with no
    field values, runtime detail, path, credential, payload, identifier, or
    exception text.
    """

    outcome: str
    attempts_in_window: int
    pre_call_health: KismetEventbusRuntimeHealthV1
    post_call_health: KismetEventbusRuntimeHealthV1 | None

    def __post_init__(self) -> None:
        if type(self.outcome) is not str or self.outcome not in _VALID_OUTCOMES:
            raise ValueError("outcome")
        if type(self.attempts_in_window) is not int or self.attempts_in_window < 0:
            raise ValueError("attempts_in_window")
        if type(self.pre_call_health) is not KismetEventbusRuntimeHealthV1:
            raise ValueError("pre_call_health")
        if self.post_call_health is not None and type(self.post_call_health) is not KismetEventbusRuntimeHealthV1:
            raise ValueError("post_call_health")

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"

    def __str__(self) -> str:
        return repr(self)


class KismetEventbusRecoveryPolicyV1:
    """Bounded caller-driven recovery policy for KismetEventbusRuntime.

    Controls when runtime.recover() is invoked, enforcing an attempt budget
    over a sliding window with a cooldown period after the budget is
    exhausted.
    """

    __slots__ = (
        "_lock",
        "_max_attempts",
        "_cooldown_after_budget_s",
        "_monotonic_time_provider",
        "_attempts_in_window",
        "_blocked_until_s",
        "_last_sampled_time_s",
    )

    def __init__(
        self,
        *,
        max_attempts: int,
        cooldown_after_budget_s: float,
        monotonic_time_provider: Callable[[], float] = time.monotonic,
    ) -> None:
        if type(max_attempts) is not int:
            raise TypeError("max_attempts")
        if max_attempts <= 0:
            raise ValueError("max_attempts")

        if type(cooldown_after_budget_s) is not float:
            raise TypeError("cooldown_after_budget_s")
        if not math.isfinite(cooldown_after_budget_s) or cooldown_after_budget_s <= 0:
            raise ValueError("cooldown_after_budget_s")

        if not callable(monotonic_time_provider):
            raise TypeError("monotonic_time_provider")

        self._lock = threading.Lock()
        self._max_attempts = max_attempts
        self._cooldown_after_budget_s = cooldown_after_budget_s
        self._monotonic_time_provider = monotonic_time_provider
        self._attempts_in_window = 0
        self._blocked_until_s: float | None = None
        self._last_sampled_time_s: float | None = None

    def apply(
        self,
        *,
        runtime: KismetEventbusRuntime,
    ) -> KismetEventbusRecoveryPolicyResultV1:
        if type(runtime) is not KismetEventbusRuntime:
            raise TypeError("runtime")

        if not self._lock.acquire(blocking=False):
            raise KismetEventbusRecoveryPolicyError(
                "recovery policy transition in progress"
            )

        try:
            pre_call_health = runtime.health
            action = pre_call_health.recovery_action

            if action == "none":
                self._attempts_in_window = 0
                self._blocked_until_s = None
                return KismetEventbusRecoveryPolicyResultV1(
                    outcome="not_required",
                    attempts_in_window=0,
                    pre_call_health=pre_call_health,
                    post_call_health=pre_call_health,
                )

            if action == "wait":
                return KismetEventbusRecoveryPolicyResultV1(
                    outcome="transition_deferred",
                    attempts_in_window=self._attempts_in_window,
                    pre_call_health=pre_call_health,
                    post_call_health=None,
                )

            now = self._monotonic_time_provider()

            if type(now) is bool:
                raise TypeError("monotonic time bool")
            if type(now) is int:
                now = float(now)
            elif type(now) is not float:
                raise TypeError("monotonic time non-numeric")

            if math.isnan(now) or math.isinf(now):
                raise ValueError("monotonic time non-finite")
            if now < 0:
                raise ValueError("monotonic time negative")

            if self._last_sampled_time_s is not None and now < self._last_sampled_time_s:
                raise KismetEventbusRecoveryPolicyError(
                    "monotonic time regressed"
                )

            self._last_sampled_time_s = now

            blocked = self._blocked_until_s
            if blocked is not None and now >= blocked:
                self._attempts_in_window = 0
                self._blocked_until_s = None
                blocked = None

            if blocked is not None and now < blocked:
                return KismetEventbusRecoveryPolicyResultV1(
                    outcome="budget_cooldown",
                    attempts_in_window=self._attempts_in_window,
                    pre_call_health=pre_call_health,
                    post_call_health=None,
                )

            self._attempts_in_window += 1

            if self._attempts_in_window >= self._max_attempts:
                self._blocked_until_s = now + self._cooldown_after_budget_s

            runtime.recover()

            post_call_health = runtime.health

            if post_call_health.recovery_action == "none":
                self._attempts_in_window = 0
                self._blocked_until_s = None

            return KismetEventbusRecoveryPolicyResultV1(
                outcome="recover_invoked",
                attempts_in_window=self._attempts_in_window,
                pre_call_health=pre_call_health,
                post_call_health=post_call_health,
            )
        finally:
            self._lock.release()
