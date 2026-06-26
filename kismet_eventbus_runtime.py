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
from kismet_eventbus_transport import KismetEventbusTransport


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

    def stop(self) -> None:
        """Stop the current runtime-owned transport generation.

        Repeated calls while stopped are no-ops at the transport boundary.
        A failed bounded stop is represented conservatively as
        ``stop_failed`` and may be retried.
        """
        with self._operation_lock:
            with self._state_lock:
                self._stop_attempt_count += 1

                if self._lifecycle in {"stopped", "start_failed"}:
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


__all__ = [
    "KismetEventbusRuntime",
    "KismetEventbusRuntimeError",
    "KismetEventbusRuntimeStatusV1",
]
