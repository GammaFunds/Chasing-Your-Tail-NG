"""Bounded composition of Kismet eventbus config, transport, and handler."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from kismet_eventbus_observation_handler import (
    KismetEventbusObservationHandler,
)
from kismet_eventbus_runtime_config import (
    KismetEventbusTransportConfigV1,
)
from kismet_eventbus_transport import (
    KismetEventbusTransport,
)


_LIFECYCLES = frozenset(
    {
        "stopped",
        "starting",
        "active",
        "stopping",
        "start_failed",
        "stop_failed",
    }
)

_CONTROL_STATES = frozenset(
    {
        "inactive",
        "transitioning",
        "worker_running",
        "recovery_required",
    }
)

_RECOVERY_ACTIONS = frozenset(
    {
        "none",
        "wait",
        "start",
        "stop",
        "restart",
    }
)


class KismetEventbusRuntimeError(RuntimeError):
    """Raised for a content-free runtime lifecycle violation."""


@dataclass(frozen=True, slots=True)
class KismetEventbusRuntimeStatusV1:
    """Immutable content-free snapshot of runtime-owned lifecycle state."""

    lifecycle: str
    generation: int
    start_attempt_count: int
    stop_attempt_count: int

    def __post_init__(self) -> None:
        if type(self.lifecycle) is not str or self.lifecycle not in _LIFECYCLES:
            raise ValueError("lifecycle")

        for name in (
            "generation",
            "start_attempt_count",
            "stop_attempt_count",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(name)


@dataclass(frozen=True, slots=True)
class KismetEventbusRuntimeHealthV1:
    """Content-free runtime and transport control-health snapshot.

    ``worker_running`` means only that the transport worker thread is
    alive.  It does not prove connection, subscription, recent-event,
    persistence, payload, freshness, sensor, or Kismet health.
    """

    runtime_lifecycle: str
    transport_worker_lifecycle: str
    control_state: str
    recovery_action: str

    def __post_init__(self) -> None:
        if (
            type(self.runtime_lifecycle) is not str
            or self.runtime_lifecycle not in _LIFECYCLES
        ):
            raise ValueError("runtime_lifecycle")

        if (
            type(self.transport_worker_lifecycle) is not str
            or self.transport_worker_lifecycle
            not in {"stopped", "running", "retiring"}
        ):
            raise ValueError("transport_worker_lifecycle")

        if (
            type(self.control_state) is not str
            or self.control_state not in _CONTROL_STATES
        ):
            raise ValueError("control_state")

        if (
            type(self.recovery_action) is not str
            or self.recovery_action not in _RECOVERY_ACTIONS
        ):
            raise ValueError("recovery_action")

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"

    def __str__(self) -> str:
        return repr(self)


class KismetEventbusRuntime:
    """Own one transport-plus-handler composition and its lifecycle.

    ``active`` means the latest runtime-owned ``start()`` transition
    completed successfully and no later runtime-owned ``stop()`` completed.
    It is deliberately not private transport-thread introspection.

    ``stop_failed`` is conservative: the worker may still be active.
    Another ``start()`` is rejected until ``stop()`` succeeds.
    """

    __slots__ = (
        "_handler",
        "_transport",
        "_state_lock",
        "_operation_lock",
        "_lifecycle",
        "_generation",
        "_start_attempt_count",
        "_stop_attempt_count",
    )

    def __init__(
        self,
        config: KismetEventbusTransportConfigV1,
        db_path: str | Path,
        *,
        hmac_key: bytes,
        collection_session_id: str,
        sensor_id: str,
        ingest_timestamp_us_provider: Callable[[], int],
    ) -> None:
        if not isinstance(config, KismetEventbusTransportConfigV1):
            raise KismetEventbusRuntimeError("invalid_config")

        handler = KismetEventbusObservationHandler(
            db_path,
            hmac_key=hmac_key,
            collection_session_id=collection_session_id,
            sensor_id=sensor_id,
            ingest_timestamp_us_provider=ingest_timestamp_us_provider,
        )
        transport = KismetEventbusTransport.from_config(config, handler)

        self._handler = handler
        self._transport = transport
        self._state_lock = threading.Lock()
        self._operation_lock = threading.Lock()
        self._lifecycle = "stopped"
        self._generation = 0
        self._start_attempt_count = 0
        self._stop_attempt_count = 0

    @property
    def status(self) -> KismetEventbusRuntimeStatusV1:
        """Return a new immutable, content-free lifecycle snapshot."""
        with self._state_lock:
            return KismetEventbusRuntimeStatusV1(
                lifecycle=self._lifecycle,
                generation=self._generation,
                start_attempt_count=self._start_attempt_count,
                stop_attempt_count=self._stop_attempt_count,
            )

    @property
    def health(self) -> KismetEventbusRuntimeHealthV1:
        """Return a content-free runtime control-health snapshot.

        ``worker_running`` means only that the transport worker thread
        is alive.  It does not prove connection, subscription,
        recent-event, persistence, payload, freshness, sensor, or
        Kismet health.
        """
        runtime_status = self.status
        transport_status = self._transport.status
        control_state, recovery_action = self._classify_health_locked(
            runtime_status.lifecycle,
            transport_status.worker_lifecycle,
        )
        return KismetEventbusRuntimeHealthV1(
            runtime_lifecycle=runtime_status.lifecycle,
            transport_worker_lifecycle=transport_status.worker_lifecycle,
            control_state=control_state,
            recovery_action=recovery_action,
        )

    def __repr__(self) -> str:
        return f"{type(self).__name__}(status={self.status!r})"

    def __str__(self) -> str:
        return repr(self)

    def start(self) -> None:
        """Start one runtime-owned transport generation.

        Repeated calls while active are no-ops at the transport boundary.
        A successful transition increments ``generation`` exactly once.
        """
        with self._operation_lock:
            self._start_locked()

    def stop(self) -> None:
        """Stop the current runtime-owned transport generation.

        Repeated calls while stopped are no-ops at the transport boundary.
        A failed bounded stop is represented conservatively as
        ``stop_failed`` and may be retried.
        """
        with self._operation_lock:
            self._stop_locked()

    def recover(self) -> None:
        """Apply one caller-invoked recovery transition, if needed.

        Recovery never waits behind another runtime lifecycle operation.
        A concurrent start, stop, or recovery operation is reported as
        ``transition_in_progress``.
        """
        if not self._operation_lock.acquire(blocking=False):
            raise KismetEventbusRuntimeError(
                "transition_in_progress"
            )

        try:
            action = self._recovery_action_locked()

            if action == "none":
                return

            if action == "wait":
                raise KismetEventbusRuntimeError(
                    "transition_in_progress"
                )

            if action == "start":
                self._start_locked()
                return

            if action == "stop":
                self._stop_locked()
                return

            if action == "restart":
                self._stop_locked()
                self._start_locked()
                return

            raise AssertionError(action)
        finally:
            self._operation_lock.release()

    def _start_locked(self) -> None:
        with self._state_lock:
            self._start_attempt_count += 1

            if self._lifecycle == "active":
                return

            if self._lifecycle == "stop_failed":
                raise KismetEventbusRuntimeError("stop_failed")

            self._lifecycle = "starting"

        try:
            self._transport.start()
        except BaseException:
            with self._state_lock:
                self._lifecycle = "start_failed"
            raise

        with self._state_lock:
            self._generation += 1
            self._lifecycle = "active"

    def _stop_locked(self) -> None:
        transport_status = self._transport.status

        with self._state_lock:
            self._stop_attempt_count += 1

            if (
                self._lifecycle in {"stopped", "start_failed"}
                and transport_status.worker_lifecycle == "stopped"
            ):
                self._lifecycle = "stopped"
                return

            self._lifecycle = "stopping"

        try:
            self._transport.stop()
        except BaseException:
            with self._state_lock:
                self._lifecycle = "stop_failed"
            raise

        with self._state_lock:
            self._lifecycle = "stopped"

    def _recovery_action_locked(self) -> str:
        runtime_status = self.status
        transport_status = self._transport.status
        _, recovery_action = self._classify_health_locked(
            runtime_status.lifecycle,
            transport_status.worker_lifecycle,
        )
        return recovery_action

    @staticmethod
    def _classify_health_locked(
        runtime_lifecycle: str,
        transport_worker_lifecycle: str,
    ) -> tuple[str, str]:
        if runtime_lifecycle in {"starting", "stopping"}:
            return "transitioning", "wait"

        if runtime_lifecycle == "active":
            if transport_worker_lifecycle == "running":
                return "worker_running", "none"
            return "recovery_required", "restart"

        if runtime_lifecycle == "stopped":
            if transport_worker_lifecycle == "stopped":
                return "inactive", "none"
            return "recovery_required", "stop"

        if runtime_lifecycle == "start_failed":
            if transport_worker_lifecycle == "stopped":
                return "recovery_required", "start"
            return "recovery_required", "stop"

        if runtime_lifecycle == "stop_failed":
            return "recovery_required", "stop"

        raise AssertionError(runtime_lifecycle)


__all__ = [
    "KismetEventbusRuntime",
    "KismetEventbusRuntimeError",
    "KismetEventbusRuntimeHealthV1",
    "KismetEventbusRuntimeStatusV1",
]
