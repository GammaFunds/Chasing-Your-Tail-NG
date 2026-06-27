"""Inactive, transport-only Kismet eventbus WebSocket client.

This module provides a bounded WebSocket subscription and dispatch
transport for the Kismet eventbus.  It is deliberately isolated from
any observation store, analysis, alert, route/session, or reporting
path.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse

from kismet_eventbus_runtime_config import (
    KismetEventbusTransportConfigV1 as _KismetEventbusTransportConfigV1,
)

_logger = logging.getLogger(__name__)

__all__ = [
    "KismetEventbusError",
    "KismetEventbusTransport",
    "KismetEventbusTransportStatusV1",
]


class KismetEventbusError(Exception):
    """Raised on invalid configuration or connection errors."""


_SCHEME_MAP: dict[str, str] = {
    "http": "ws",
    "https": "wss",
}

_WORKER_LIFECYCLES = frozenset(
    {
        "stopped",
        "running",
        "retiring",
    }
)


@dataclass(frozen=True, slots=True)
class KismetEventbusTransportStatusV1:
    """Immutable content-free snapshot of transport worker state."""

    worker_lifecycle: str
    stop_requested: bool

    def __post_init__(self) -> None:
        if (
            type(self.worker_lifecycle) is not str
            or self.worker_lifecycle not in _WORKER_LIFECYCLES
        ):
            raise ValueError("worker_lifecycle")

        if type(self.stop_requested) is not bool:
            raise ValueError("stop_requested")

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"

    def __str__(self) -> str:
        return repr(self)


def _build_ws_url(base_url: str) -> str:
    """Convert *http(s)* base URL to a *ws(s)* eventbus WebSocket URL."""
    parsed = urlparse(base_url)
    scheme = parsed.scheme.lower()

    if scheme not in _SCHEME_MAP:
        raise KismetEventbusError(
            f"unsupported scheme: {scheme}"
        )

    host = parsed.hostname
    if not host:
        raise KismetEventbusError("missing host")

    if parsed.username is not None or parsed.password is not None:
        raise KismetEventbusError(
            "embedded credentials not allowed"
        )

    ws_scheme = _SCHEME_MAP[scheme]

    if ":" in host:
        netloc = f"[{host}]"
    else:
        netloc = host

    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"

    return f"{ws_scheme}://{netloc}/eventbus/events.ws"


def _deduplicate_topics(
    topics: tuple[str, ...],
) -> tuple[str, ...]:
    """Deduplicate topics while preserving caller-supplied order.

    Validates that each entry is a non-empty string and that at least
    one topic remains after deduplication.
    """
    seen: set[str] = set()
    result: list[str] = []

    for topic in topics:
        if not isinstance(topic, str) or not topic:
            raise KismetEventbusError(
                "topics must be non-empty strings"
            )

        if topic not in seen:
            seen.add(topic)
            result.append(topic)

    if not result:
        raise KismetEventbusError(
            "at least one topic is required"
        )

    return tuple(result)


class KismetEventbusTransport:
    """Bounded WebSocket subscription transport for Kismet eventbus events.

    This is a *transport-only* client.  It produces no observations,
    location links, routes, alerts, classifications, or persistence.

    Worker lifecycle is generation-specific and identity-safe:

    * Each ``start()`` creates a fresh per-generation stop event owned
      by that worker.  A worker captures and uses only its own stop
      event for its loop and reconnect waiter.
    * ``stop()`` captures the exact current worker thread and the stop
      event belonging to that same generation.  A delayed stop that
      captured worker A can never signal, close, clear, or terminate
      worker B, even if A retires and B starts before the delayed stop
      resumes.
    * ``start()`` publishes the worker thread, its stop event, and
      calls ``thread.start()`` atomically under the instance lock, so
      ``stop()`` can never observe a published-but-unstarted thread.
      If ``thread.start()`` raises, the published worker state is
      rolled back under the lock when it still belongs to that
      attempted worker.
    * A new worker is never created while a retiring earlier thread is
      still actually alive.  When a worker's target returns but its
      Python ``Thread`` object is still unwinding, that generation is
      tracked separately as retiring until a later lifecycle call can
      reap it.
    * Self-stop (a handler invoking ``stop()``) never joins the running
      thread and never clears ``_thread`` before the worker exits.
    * An outer worker ``finally`` clears ``_thread`` and the stop event
      only when the worker is still the published one, so a stale
      finalizer can never clear a later worker reference.
    * Socket publication and cleanup are identity-guarded by owner
      thread identity, so an old worker can never clear or close a
      newer worker's active socket.
    """

    _CONNECT_RETRY_DELAY_S: float = 5.0
    _STOP_JOIN_TIMEOUT_S: float = 5.0

    def __init__(
        self,
        base_url: str,
        topics: tuple[str, ...],
        handler: Callable[[dict[str, Any]], None],
        *,
        _create_connection: Callable[..., Any] | None = None,
        _reconnect_waiter: (
            Callable[[threading.Event], None] | None
        ) = None,
        _thread_factory: (
            Callable[..., threading.Thread] | None
        ) = None,
        _stop_after_join: (
            Callable[
                [threading.Thread, threading.Event], None
            ]
            | None
        ) = None,
    ) -> None:
        if not callable(handler):
            raise KismetEventbusError(
                "handler must be callable"
            )

        self._ws_url = _build_ws_url(base_url)
        self._topics = _deduplicate_topics(topics)
        self._handler = handler

        self._create_connection = (
            _create_connection
            if _create_connection is not None
            else self._default_create_connection
        )
        self._reconnect_waiter = (
            _reconnect_waiter
            if _reconnect_waiter is not None
            else self._default_reconnect_waiter
        )
        self._thread_factory = (
            _thread_factory
            if _thread_factory is not None
            else threading.Thread
        )
        self._stop_after_join = _stop_after_join

        self._lock = threading.Lock()
        # Current-generation worker state.  Each generation owns its
        # own stop event; the shared-single-event design is replaced so
        # a delayed stop targeting worker A can never act on worker B.
        self._stop_event: threading.Event | None = None
        self._ws: Any = None
        self._ws_owner: threading.Thread | None = None
        self._thread: threading.Thread | None = None
        self._retiring_thread: threading.Thread | None = None
        self._retiring_stop_event: threading.Event | None = None

    # ------------------------------------------------------------------
    # from_config  (config-based factory)
    # ------------------------------------------------------------------

    @classmethod
    def from_config(
        cls,
        config: _KismetEventbusTransportConfigV1,
        handler: Callable[[dict[str, Any]], object],
        *,
        _create_connection: Callable[..., Any] | None = None,
        _reconnect_waiter: (
            Callable[[threading.Event], None] | None
        ) = None,
        _thread_factory: (
            Callable[..., threading.Thread] | None
        ) = None,
        _stop_after_join: (
            Callable[
                [threading.Thread, threading.Event],
                None,
            ]
            | None
        ) = None,
    ) -> KismetEventbusTransport:
        if not isinstance(
            config, _KismetEventbusTransportConfigV1
        ):
            raise KismetEventbusError("invalid config type")

        if not callable(handler):
            raise KismetEventbusError("handler must be callable")

        connect_fn = cls._build_config_create_connection(
            config,
            _create_connection,
        )

        if _reconnect_waiter is not None:
            reconnect_fn = _reconnect_waiter
        else:
            reconnect_delay = config._reconnect_delay_s
            reconnect_fn = (
                lambda se: se.wait(
                    timeout=reconnect_delay,
                )
            )

        transport = cls.__new__(cls)
        KismetEventbusTransport.__init__(
            transport,
            config._base_url,
            config._topics,
            handler,
            _create_connection=connect_fn,
            _reconnect_waiter=reconnect_fn,
            _thread_factory=_thread_factory,
            _stop_after_join=_stop_after_join,
        )
        transport._STOP_JOIN_TIMEOUT_S = (
            config._stop_join_timeout_s
        )
        return transport

    @staticmethod
    def _build_config_create_connection(
        config: _KismetEventbusTransportConfigV1,
        connector: Callable[..., Any] | None,
    ) -> Callable[[str], Any]:
        import ssl

        auth_value = config._authorization_header_value.decode(
            "ascii"
        )
        timeout = config._connect_timeout_s
        tls_mode = config._tls_mode

        def connect(url: str) -> Any:
            low_level_connector = connector

            if low_level_connector is None:
                import websocket

                low_level_connector = (
                    websocket.create_connection
                )

            kwargs: dict[str, Any] = {
                "header": [
                    f"Authorization: {auth_value}",
                ],
                "timeout": timeout,
            }

            if tls_mode == "verify_required":
                kwargs["sslopt"] = {
                    "cert_reqs": ssl.CERT_REQUIRED,
                    "check_hostname": True,
                }

            return low_level_connector(
                url,
                **kwargs,
            )

        return connect

    # ------------------------------------------------------------------
    # Default factory / waiter  (lazy websocket-client import)
    # ------------------------------------------------------------------

    @staticmethod
    def _default_create_connection(url: str) -> Any:
        import websocket

        return websocket.create_connection(url)

    @staticmethod
    def _default_reconnect_waiter(
        stop_event: threading.Event,
    ) -> None:
        stop_event.wait(
            timeout=KismetEventbusTransport._CONNECT_RETRY_DELAY_S,
        )

    @property
    def status(self) -> KismetEventbusTransportStatusV1:
        """Return a fresh immutable snapshot of worker state only."""
        with self._lock:
            thread = self._thread
            stop_event = self._stop_event
            retiring_thread = self._retiring_thread
            retiring_stop_event = self._retiring_stop_event

            if thread is not None and thread.is_alive():
                return KismetEventbusTransportStatusV1(
                    worker_lifecycle="running",
                    stop_requested=(
                        stop_event.is_set()
                        if stop_event is not None
                        else False
                    ),
                )

            if retiring_thread is not None and retiring_thread.is_alive():
                return KismetEventbusTransportStatusV1(
                    worker_lifecycle="retiring",
                    stop_requested=(
                        retiring_stop_event.is_set()
                        if retiring_stop_event is not None
                        else False
                    ),
                )

            return KismetEventbusTransportStatusV1(
                worker_lifecycle="stopped",
                stop_requested=False,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the eventbus worker thread.

        Idempotent.  A second worker is never created while an earlier
        worker thread remains actually alive.  Worker publication and
        ``thread.start()`` are atomic with respect to ``stop()``; if
        ``thread.start()`` raises, the published worker state is
        rolled back under the lock when it still belongs to the
        attempted worker, leaving the transport safely stoppable and
        restartable.
        """
        with self._lock:
            self._reap_completed_worker_locked()
            if (
                (
                    self._thread is not None
                    and self._thread.is_alive()
                )
                or (
                    self._retiring_thread is not None
                    and self._retiring_thread.is_alive()
                )
            ):
                # A retiring earlier thread is still actually alive:
                # do not permit a new worker.
                return

            stop_event = threading.Event()
            thread = self._thread_factory(
                target=self._worker,
                args=(stop_event,),
                daemon=True,
            )
            # Publish worker state, then start, atomically under the
            # lock so stop() can never observe a published-but-unstarted
            # thread to join().
            self._thread = thread
            self._stop_event = stop_event
            try:
                thread.start()
            except BaseException:
                # Rollback only the state belonging to this attempted
                # worker; leave the transport safely stoppable and
                # restartable.
                if self._thread is thread:
                    self._thread = None
                if self._stop_event is stop_event:
                    self._stop_event = None
                raise

    def stop(self) -> None:
        """Stop the eventbus worker and close its socket.

        Idempotent: safe before ``start()`` and after the worker has
        fully terminated.  ``stop()`` captures the exact current worker
        thread and the stop event belonging to that same generation,
        so a delayed stop that captured worker A never signals, closes,
        clears, or terminates a later worker B.

        When invoked from outside the worker thread, performs a bounded
        join and raises a content-free :class:`KismetEventbusError` if
        the worker does not terminate in time, preserving the live
        worker reference.  When invoked from inside the worker
        (self-stop), sets the stop event and closes the socket but
        never joins the running thread and never clears ``_thread``;
        the worker's own outer ``finally`` clears it once it exits.
        """
        with self._lock:
            self._reap_completed_worker_locked()
            worker_thread = self._thread
            stop_event = self._stop_event
            if worker_thread is None:
                worker_thread = self._retiring_thread
                stop_event = self._retiring_stop_event

        if worker_thread is None:
            # Idempotent: nothing to stop (never started, or already
            # fully terminated and reaped).
            return

        if stop_event is not None:
            stop_event.set()
        self._close_ws_if_owner(worker_thread)

        if threading.current_thread() is worker_thread:
            # Self-stop: do not join, do not clear worker state.
            return

        worker_thread.join(timeout=self._STOP_JOIN_TIMEOUT_S)
        if worker_thread.is_alive():
            # Bounded termination failed: raise content-free error and
            # preserve the live worker reference (and its stop event).
            raise KismetEventbusError()

        if self._stop_after_join is not None:
            self._stop_after_join(worker_thread, stop_event)

        with self._lock:
            if self._thread is worker_thread:
                self._thread = None
            if self._stop_event is stop_event:
                self._stop_event = None
            if self._retiring_thread is worker_thread:
                self._retiring_thread = None
            if self._retiring_stop_event is stop_event:
                self._retiring_stop_event = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _publish_ws(
        self,
        owner_thread: threading.Thread,
        ws: Any,
    ) -> bool:
        """Publish *ws* as the active socket iff *owner_thread* is
        still the current worker.  Returns False if superseded."""
        with self._lock:
            if self._thread is not owner_thread:
                return False
            self._ws = ws
            self._ws_owner = owner_thread
            return True

    def _close_ws_if_owner(
        self,
        owner_thread: threading.Thread,
    ) -> None:
        """Close and clear the active socket iff it is owned by
        *owner_thread*.  Identity-safe: never touches a socket owned
        by a different (e.g. newer) worker."""
        ws: Any = None
        with self._lock:
            if (
                self._ws is not None
                and self._ws_owner is owner_thread
            ):
                ws = self._ws
                self._ws = None
                self._ws_owner = None

        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    def _clear_ws_if_owner(
        self,
        owner_thread: threading.Thread,
    ) -> None:
        """Clear the active socket publication iff it is owned by
        *owner_thread*.  Does not close; called by a worker after it
        has already closed its own local socket reference.
        Identity-safe: a stale worker cannot clear a newer worker's
        socket publication."""
        with self._lock:
            if self._ws_owner is owner_thread:
                self._ws = None
                self._ws_owner = None

    def _finalize_worker(
        self,
        worker_thread: threading.Thread,
        stop_event: threading.Event,
    ) -> None:
        """Outer worker finalizer: retire the exiting generation.

        The active worker reference is moved to the retiring slot only
        when the exiting worker is still the published one, so a stale
        worker can never clear a later worker reference.  The retiring
        slot remains generation-specific and identity-safe until a
        later lifecycle call reaps it after the thread is actually
        dead.
        """
        with self._lock:
            if self._thread is worker_thread:
                self._retiring_thread = worker_thread
                self._retiring_stop_event = stop_event
                self._thread = None
                self._stop_event = None

    def _reap_completed_worker_locked(self) -> None:
        """Clear stale worker state once the thread is actually dead."""
        if (
            self._retiring_thread is not None
            and not self._retiring_thread.is_alive()
        ):
            self._retiring_thread = None
            self._retiring_stop_event = None

        if self._thread is not None and not self._thread.is_alive():
            self._thread = None
            self._stop_event = None

    def _worker(
        self, stop_event: threading.Event
    ) -> None:
        my_thread = threading.current_thread()
        try:
            while not stop_event.is_set():
                ws: Any = None

                try:
                    ws = self._create_connection(self._ws_url)
                except Exception:
                    _logger.debug("connection attempt failed")

                if ws is not None:
                    if not self._publish_ws(my_thread, ws):
                        # Superseded by a newer worker before we could
                        # publish.  Do not use this socket.
                        try:
                            ws.close()
                        except Exception:
                            pass
                        return

                    try:
                        self._subscribe_and_dispatch(
                            ws, stop_event
                        )
                    finally:
                        try:
                            ws.close()
                        except Exception:
                            pass
                        self._clear_ws_if_owner(my_thread)

                if not stop_event.is_set():
                    self._reconnect_waiter(stop_event)
        finally:
            self._finalize_worker(my_thread, stop_event)

    def _subscribe_and_dispatch(
        self,
        ws: Any,
        stop_event: threading.Event,
    ) -> None:
        for topic in self._topics:
            if stop_event.is_set():
                return

            frame = json.dumps(
                {"SUBSCRIBE": topic},
                separators=(",", ":"),
            )
            try:
                ws.send(frame)
            except Exception:
                return

        while not stop_event.is_set():
            try:
                raw = ws.recv()
            except Exception:
                break

            if raw is None:
                break

            try:
                msg: Any = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if not isinstance(msg, dict):
                continue

            try:
                self._handler(msg)
            except Exception:
                pass
