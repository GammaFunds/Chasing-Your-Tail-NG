"""Deterministic tests for KismetEventbusTransport.

No real network sockets or wall-clock sleeps are used.  Every helper
thread that is started is bounded-joined and explicitly asserted to
have terminated.
"""

from __future__ import annotations

import ast
import json
import logging
import threading
import unittest

from kismet_eventbus_transport import (
    KismetEventbusError,
    KismetEventbusTransport,
)


# ------------------------------------------------------------------
# Fake WebSocket for deterministic testing
# ------------------------------------------------------------------

class FakeWebSocket:
    """Simulates a WebSocket with controllable receive data."""

    def __init__(
        self,
        recv_data: list[str] | None = None,
        *,
        close_immediately: bool = False,
        expected_sends: int = 0,
    ) -> None:
        self.sent: list[str] = []
        self._recv_data: list[str] = list(recv_data or [])
        self._closed: bool = close_immediately
        self._recv_blocker = threading.Event()
        self.all_sent: threading.Event = threading.Event()
        self._expected_sends = expected_sends
        if close_immediately:
            self._recv_blocker.set()

    def send(self, data: str) -> None:
        self.sent.append(data)
        if self._expected_sends and len(self.sent) >= self._expected_sends:
            self.all_sent.set()

    def recv(self) -> str | None:
        if self._closed:
            return None
        if self._recv_data:
            return self._recv_data.pop(0)
        self._recv_blocker.wait()
        if self._closed:
            return None
        if self._recv_data:
            return self._recv_data.pop(0)
        return None

    def close(self) -> None:
        self._closed = True
        self._recv_blocker.set()

    @property
    def closed(self) -> bool:
        return self._closed


# ------------------------------------------------------------------
# Controlled thread seams for deterministic lifecycle boundaries
# ------------------------------------------------------------------

class _FailStartThread(threading.Thread):
    """Thread whose ``start()`` always raises without starting."""

    def start(self) -> None:
        raise RuntimeError("injected start failure")


class _TailBlockingThread(threading.Thread):
    """Thread that holds the run tail open after its target returns."""

    def __init__(
        self,
        *args: object,
        target_returned: threading.Event,
        release_thread_tail: threading.Event,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._target_returned = target_returned
        self._release_thread_tail = release_thread_tail

    def run(self) -> None:
        super().run()
        self._target_returned.set()
        self._release_thread_tail.wait()


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------

class KismetEventbusTransportTests(unittest.TestCase):
    """KismetEventbusTransport — deterministic lifecycle tests."""

    maxDiff = None

    # --------------------------------------------------------------
    # Convenience helpers
    # --------------------------------------------------------------

    @staticmethod
    def _assertJoined(
        t: threading.Thread,
        timeout: float = 5.0,
    ) -> None:
        t.join(timeout=timeout)
        assert not t.is_alive(), (
            f"helper thread {t.name} did not terminate within {timeout}s"
        )

    @staticmethod
    def _fake_connect(url: str) -> FakeWebSocket:
        return FakeWebSocket()

    @staticmethod
    def _noop_waiter(se: threading.Event) -> None:
        return

    # --------------------------------------------------------------
    # 1. Importing the module performs no connection
    # --------------------------------------------------------------
    def test_import_performs_no_connection(self) -> None:
        with open("kismet_eventbus_transport.py") as f:
            tree = ast.parse(f.read())

        for stmt in tree.body:
            if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                names = (
                    [alias.name for alias in stmt.names]
                    if isinstance(stmt, ast.Import)
                    else []
                )
                module = (
                    stmt.module if isinstance(stmt, ast.ImportFrom) else ""
                )
                if "websocket" in module or any(
                    "websocket" in n for n in names
                ):
                    self.fail("websocket imported at module level")

        found_lazy = False
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [alias.name for alias in node.names]
                    if isinstance(node, ast.Import)
                    else []
                )
                module = (
                    node.module if isinstance(node, ast.ImportFrom) else ""
                )
                if "websocket" in module or any(
                    "websocket" in n for n in names
                ):
                    found_lazy = True
                    break

        self.assertTrue(found_lazy, "no lazy websocket import found")

    # --------------------------------------------------------------
    # 2. HTTP and HTTPS URL conversion
    # --------------------------------------------------------------
    def test_http_url_conversion(self) -> None:
        transport = KismetEventbusTransport(
            "http://kismet.example.com",
            ("t",),
            lambda _: None,
            _create_connection=self._fake_connect,
            _reconnect_waiter=self._noop_waiter,
        )
        self.assertEqual(
            transport._ws_url,
            "ws://kismet.example.com/eventbus/events.ws",
        )

    def test_https_url_conversion(self) -> None:
        transport = KismetEventbusTransport(
            "https://kismet.example.com",
            ("t",),
            lambda _: None,
            _create_connection=self._fake_connect,
            _reconnect_waiter=self._noop_waiter,
        )
        self.assertEqual(
            transport._ws_url,
            "wss://kismet.example.com/eventbus/events.ws",
        )

    def test_url_conversion_preserves_port(self) -> None:
        transport = KismetEventbusTransport(
            "http://kismet.example.com:8080",
            ("t",),
            lambda _: None,
            _create_connection=self._fake_connect,
            _reconnect_waiter=self._noop_waiter,
        )
        self.assertEqual(
            transport._ws_url,
            "ws://kismet.example.com:8080/eventbus/events.ws",
        )

    # --------------------------------------------------------------
    # 3. Rejection of unsupported schemes, missing host,
    #    and embedded credentials
    # --------------------------------------------------------------
    def test_rejects_unsupported_scheme(self) -> None:
        with self.assertRaises(KismetEventbusError):
            KismetEventbusTransport(
                "ftp://kismet.example.com",
                ("t",),
                lambda _: None,
            )

    def test_rejects_missing_host(self) -> None:
        with self.assertRaises(KismetEventbusError):
            KismetEventbusTransport(
                "http:///path",
                ("t",),
                lambda _: None,
            )

    def test_rejects_embedded_credentials(self) -> None:
        with self.assertRaises(KismetEventbusError):
            KismetEventbusTransport(
                "http://user:pass@kismet.example.com",
                ("t",),
                lambda _: None,
            )

    # --------------------------------------------------------------
    # 4. Deterministic subscription frames and order
    # --------------------------------------------------------------
    def test_subscription_frames_in_order(self) -> None:
        ws = FakeWebSocket(expected_sends=3)
        transport = KismetEventbusTransport(
            "http://example.com",
            ("gamma", "alpha", "beta"),
            lambda _: None,
            _create_connection=lambda url: ws,
            _reconnect_waiter=self._noop_waiter,
        )
        transport.start()
        self.assertTrue(ws.all_sent.wait(timeout=5))
        self.assertEqual(
            ws.sent,
            [
                json.dumps(
                    ["SUBSCRIBE", "gamma"],
                    separators=(",", ":"),
                ),
                json.dumps(
                    ["SUBSCRIBE", "alpha"],
                    separators=(",", ":"),
                ),
                json.dumps(
                    ["SUBSCRIBE", "beta"],
                    separators=(",", ":"),
                ),
            ],
        )
        transport.stop()
        self.assertIsNone(transport._thread)

    def test_subscription_deduplicates(self) -> None:
        ws = FakeWebSocket(expected_sends=2)
        transport = KismetEventbusTransport(
            "http://example.com",
            ("topic", "topic", "other"),
            lambda _: None,
            _create_connection=lambda url: ws,
            _reconnect_waiter=self._noop_waiter,
        )
        transport.start()
        self.assertTrue(ws.all_sent.wait(timeout=5))
        self.assertEqual(len(ws.sent), 2)
        self.assertIn(
            json.dumps(["SUBSCRIBE", "topic"], separators=(",", ":")),
            ws.sent,
        )
        transport.stop()
        self.assertIsNone(transport._thread)

    def test_rejects_empty_topic(self) -> None:
        with self.assertRaises(KismetEventbusError):
            KismetEventbusTransport(
                "http://example.com",
                ("",),
                lambda _: None,
            )

    def test_rejects_all_empty_topics(self) -> None:
        with self.assertRaises(KismetEventbusError):
            KismetEventbusTransport(
                "http://example.com",
                ("", ""),
                lambda _: None,
            )

    # --------------------------------------------------------------
    # 5. Structured topic payload dispatch
    # --------------------------------------------------------------
    def test_dispatches_structured_payload(self) -> None:
        received: list[dict] = []
        event = threading.Event()

        def handler(msg: dict) -> None:
            received.append(msg)
            event.set()

        ws = FakeWebSocket(
            recv_data=[
                '{"kismet":{"topic":"test","data":123}}',
            ],
        )
        transport = KismetEventbusTransport(
            "http://example.com",
            ("t",),
            handler,
            _create_connection=lambda url: ws,
            _reconnect_waiter=self._noop_waiter,
        )
        transport.start()
        event.wait(timeout=5)
        transport.stop()
        self.assertEqual(
            received,
            [{"kismet": {"topic": "test", "data": 123}}],
        )

    # --------------------------------------------------------------
    # 6. Malformed JSON is dropped
    # --------------------------------------------------------------
    def test_malformed_json_is_dropped(self) -> None:
        received: list[dict] = []
        event = threading.Event()

        def handler(msg: dict) -> None:
            received.append(msg)
            event.set()

        ws = FakeWebSocket(
            recv_data=[
                "not json",
                '{"valid":true}',
            ],
        )
        transport = KismetEventbusTransport(
            "http://example.com",
            ("t",),
            handler,
            _create_connection=lambda url: ws,
            _reconnect_waiter=self._noop_waiter,
        )
        transport.start()
        event.wait(timeout=5)
        transport.stop()
        self.assertEqual(received, [{"valid": True}])

    # --------------------------------------------------------------
    # 7. JSON arrays/scalars are dropped
    # --------------------------------------------------------------
    def test_non_object_frames_are_dropped(self) -> None:
        received: list[dict] = []
        event = threading.Event()

        def handler(msg: dict) -> None:
            received.append(msg)
            event.set()

        ws = FakeWebSocket(
            recv_data=[
                '["array"]',
                "42",
                '"string"',
                "true",
                "null",
                '{"valid":true}',
            ],
        )
        transport = KismetEventbusTransport(
            "http://example.com",
            ("t",),
            handler,
            _create_connection=lambda url: ws,
            _reconnect_waiter=self._noop_waiter,
        )
        transport.start()
        event.wait(timeout=5)
        transport.stop()
        self.assertEqual(received, [{"valid": True}])

    # --------------------------------------------------------------
    # 8. One handler exception does not block the next event
    # --------------------------------------------------------------
    def test_handler_exception_isolation(self) -> None:
        received: list[dict] = []
        event = threading.Event()

        def handler(msg: dict) -> None:
            if msg.get("fail"):
                raise ValueError("handler error")
            received.append(msg)
            event.set()

        ws = FakeWebSocket(
            recv_data=[
                '{"fail":true}',
                '{"ok":true}',
            ],
        )
        transport = KismetEventbusTransport(
            "http://example.com",
            ("t",),
            handler,
            _create_connection=lambda url: ws,
            _reconnect_waiter=self._noop_waiter,
        )
        transport.start()
        event.wait(timeout=5)
        transport.stop()
        self.assertEqual(received, [{"ok": True}])

    # --------------------------------------------------------------
    # 9. Connection closure causes one controlled reconnect,
    #    signalled by connector-created Events for first and
    #    second connection creation.
    # --------------------------------------------------------------
    def test_connection_closure_triggers_reconnect(self) -> None:
        connections: list[FakeWebSocket] = []
        connect_events: list[threading.Event] = [
            threading.Event(),
            threading.Event(),
        ]
        connect_index: list[int] = [0]

        def create_conn(url: str) -> FakeWebSocket:
            is_first = len(connections) == 0
            ws = FakeWebSocket(close_immediately=is_first)
            connections.append(ws)
            i = connect_index[0]
            connect_index[0] += 1
            connect_events[i].set()
            return ws

        def waiter(se: threading.Event) -> None:
            return

        transport = KismetEventbusTransport(
            "http://example.com",
            ("t",),
            lambda _: None,
            _create_connection=create_conn,
            _reconnect_waiter=waiter,
        )
        transport.start()
        self.assertTrue(connect_events[0].wait(timeout=5))
        self.assertTrue(connect_events[1].wait(timeout=5))
        transport.stop()
        self.assertEqual(len(connections), 2)
        self.assertIsNone(transport._thread)

    # --------------------------------------------------------------
    # 10. Reconnect waiting is interrupted by stop()
    # --------------------------------------------------------------
    def test_stop_interrupts_reconnect_wait(self) -> None:
        waiter_entered = threading.Event()
        waiter_exited = threading.Event()

        def waiter(se: threading.Event) -> None:
            waiter_entered.set()
            se.wait()  # blocks until stop() sets the generation event
            waiter_exited.set()

        transport = KismetEventbusTransport(
            "http://example.com",
            ("t",),
            lambda _: None,
            _create_connection=lambda url: FakeWebSocket(
                close_immediately=True,
            ),
            _reconnect_waiter=waiter,
        )
        transport.start()
        self.assertTrue(waiter_entered.wait(timeout=5))
        transport.stop()
        self.assertTrue(waiter_exited.wait(timeout=5))
        self.assertIsNone(transport._thread)

    # --------------------------------------------------------------
    # 11. Double start creates only one worker
    # --------------------------------------------------------------
    def test_double_start_creates_one_worker(self) -> None:
        ws = FakeWebSocket(expected_sends=1)
        create_count: list[int] = [0]

        def create_conn(url: str) -> FakeWebSocket:
            create_count[0] += 1
            return ws

        transport = KismetEventbusTransport(
            "http://example.com",
            ("t",),
            lambda _: None,
            _create_connection=create_conn,
            _reconnect_waiter=self._noop_waiter,
        )
        transport.start()
        transport.start()  # second start — must be no-op
        self.assertTrue(ws.all_sent.wait(timeout=5))
        transport.stop()
        self.assertEqual(create_count[0], 1)
        self.assertIsNone(transport._thread)

    # --------------------------------------------------------------
    # 12. stop() before start() is safe
    # --------------------------------------------------------------
    def test_stop_before_start_is_safe(self) -> None:
        transport = KismetEventbusTransport(
            "http://example.com",
            ("t",),
            lambda _: None,
            _create_connection=self._fake_connect,
            _reconnect_waiter=self._noop_waiter,
        )
        # Should not raise
        transport.stop()
        transport.stop()  # second call also safe

    # --------------------------------------------------------------
    # 13. stop() closes the current socket and leaves the client
    #     stopped
    # --------------------------------------------------------------
    def test_stop_closes_socket_and_leaves_stopped(self) -> None:
        ws = FakeWebSocket(expected_sends=1)
        transport = KismetEventbusTransport(
            "http://example.com",
            ("t",),
            lambda _: None,
            _create_connection=lambda url: ws,
            _reconnect_waiter=self._noop_waiter,
        )
        transport.start()
        self.assertTrue(ws.all_sent.wait(timeout=5))
        thread = transport._thread
        transport.stop()
        self.assertTrue(ws.closed)
        self.assertFalse(thread.is_alive())
        self.assertIsNone(transport._thread)

    # --------------------------------------------------------------
    # 14. No reconnect occurs after stop()
    # --------------------------------------------------------------
    def test_no_reconnect_after_stop(self) -> None:
        waiter_called = threading.Event()

        def waiter(se: threading.Event) -> None:
            waiter_called.set()
            se.wait()

        transport = KismetEventbusTransport(
            "http://example.com",
            ("t",),
            lambda _: None,
            _create_connection=lambda url: FakeWebSocket(),
            _reconnect_waiter=waiter,
        )
        transport.start()
        transport.stop()
        # Worker should have exited before any reconnect wait
        self.assertFalse(waiter_called.is_set())
        self.assertIsNone(transport._thread)

    # --------------------------------------------------------------
    # 15. Captured logs contain no password, Authorization value,
    #     payload contents, or injected exception text
    # --------------------------------------------------------------
    def test_logs_contain_no_sensitive_data(self) -> None:
        import io

        received: list[dict] = []
        event = threading.Event()

        def handler(msg: dict) -> None:
            received.append(msg)
            event.set()

        ws = FakeWebSocket(
            recv_data=[
                '{"sensitive":"payload-data"}',
            ],
        )

        transport = KismetEventbusTransport(
            "http://example.com",
            ("t",),
            handler,
            _create_connection=lambda url: ws,
            _reconnect_waiter=self._noop_waiter,
        )

        logger = logging.getLogger("kismet_eventbus_transport")
        previous_level = logger.level
        stream = io.StringIO()
        handler_cap = logging.StreamHandler(stream)
        handler_cap.setLevel(logging.DEBUG)
        logger.addHandler(handler_cap)
        logger.setLevel(logging.DEBUG)

        try:
            transport.start()
            event.wait(timeout=5)
            transport.stop()
        finally:
            logger.removeHandler(handler_cap)
            logger.setLevel(previous_level)

        all_output = stream.getvalue()
        self.assertNotIn("password", all_output)
        self.assertNotIn("Authorization", all_output)
        self.assertNotIn("payload-data", all_output)
        self.assertNotIn("handler error", all_output)

    # --------------------------------------------------------------
    # 16. Static import checks prove no forbidden
    #     application-layer imports
    # --------------------------------------------------------------
    def test_no_forbidden_imports(self) -> None:
        forbidden_prefixes = (
            "observation",
            "route_session",
            "bounded_gps",
            "chasing_your_tail",
            "cyt_gui",
            "probe_analyzer",
            "surveillance",
            "gps_tracker",
            "flask",
            "socketio",
        )

        with open("kismet_eventbus_transport.py") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for prefix in forbidden_prefixes:
                        self.assertNotIn(
                            prefix,
                            alias.name,
                            (
                                f"forbidden import '{alias.name}' "
                                f"matches prefix '{prefix}'"
                            ),
                        )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for prefix in forbidden_prefixes:
                    self.assertNotIn(
                        prefix,
                        module,
                        (
                            f"forbidden import from '{module}' "
                            f"matches prefix '{prefix}'"
                        ),
                    )

    # --------------------------------------------------------------
    # 17. Immediate stop followed by start creates a new worker
    # --------------------------------------------------------------
    def test_stop_then_start_creates_new_worker(self) -> None:
        wss: list[FakeWebSocket] = []

        def create(url: str) -> FakeWebSocket:
            ws = FakeWebSocket(expected_sends=1)
            wss.append(ws)
            return ws

        transport = KismetEventbusTransport(
            "http://example.com",
            ("t",),
            lambda _: None,
            _create_connection=create,
            _reconnect_waiter=self._noop_waiter,
        )
        transport.start()
        self.assertEqual(len(wss), 1)
        self.assertTrue(wss[0].all_sent.wait(timeout=5))
        thread_1 = transport._thread
        transport.stop()
        self.assertFalse(thread_1.is_alive())

        transport.start()
        self.assertEqual(len(wss), 2)
        thread_2 = transport._thread
        self.assertIsNotNone(thread_2)
        self.assertIsNot(thread_2, thread_1)
        transport.stop()
        self.assertFalse(thread_2.is_alive())

    # --------------------------------------------------------------
    # 18. Subscription send failure enters reconnect path;
    #     reconnect is awaited via an explicit second-connection
    #     Event, not inferred from waiter entry.
    # --------------------------------------------------------------
    def test_send_failure_triggers_reconnect(self) -> None:
        connections: list[FakeWebSocket] = []
        connect_events: list[threading.Event] = [
            threading.Event(),
            threading.Event(),
        ]
        connect_index: list[int] = [0]

        def create_conn(url: str) -> FakeWebSocket:
            is_first = len(connections) == 0
            if is_first:
                ws = FakeWebSocket(expected_sends=1)

                def fail_send(data: str) -> None:
                    raise ConnectionError("send failed")

                ws.send = fail_send  # type: ignore[assignment]
            else:
                ws = FakeWebSocket(expected_sends=1)
            connections.append(ws)
            i = connect_index[0]
            connect_index[0] += 1
            connect_events[i].set()
            return ws

        def waiter(se: threading.Event) -> None:
            return

        transport = KismetEventbusTransport(
            "http://example.com",
            ("t",),
            lambda _: None,
            _create_connection=create_conn,
            _reconnect_waiter=waiter,
        )
        transport.start()
        self.assertTrue(connect_events[0].wait(timeout=5))
        self.assertTrue(connect_events[1].wait(timeout=5))
        transport.stop()
        self.assertEqual(len(connections), 2)
        self.assertIsNone(transport._thread)

    # --------------------------------------------------------------
    # 19. Bounded stop failure preserves live thread reference
    # --------------------------------------------------------------
    def test_bounded_stop_failure_preserves_thread(self) -> None:
        waiter_entered = threading.Event()
        release_worker = threading.Event()

        def waiter(se: threading.Event) -> None:
            waiter_entered.set()
            release_worker.wait()

        transport = KismetEventbusTransport(
            "http://example.com",
            ("t",),
            lambda _: None,
            _create_connection=lambda url: FakeWebSocket(
                close_immediately=True,
            ),
            _reconnect_waiter=waiter,
        )
        transport._STOP_JOIN_TIMEOUT_S = 0.2

        transport.start()
        self.assertTrue(waiter_entered.wait(timeout=5))

        thread_before = transport._thread
        stop_event_before = transport._stop_event
        self.assertIsNotNone(thread_before)
        self.assertIsNotNone(stop_event_before)
        self.assertTrue(thread_before.is_alive())

        with self.assertRaises(KismetEventbusError):
            transport.stop()

        # Bounded-stop failure must retain the live worker reference
        # and that worker's generation stop event.
        self.assertIs(transport._thread, thread_before)
        self.assertIs(transport._stop_event, stop_event_before)
        self.assertTrue(thread_before.is_alive())
        self.assertTrue(stop_event_before.is_set())

        # After releasing the bounded-stop blocker, call stop() again
        # and prove clean termination and cleared worker state.
        release_worker.set()
        transport.stop()
        self.assertFalse(thread_before.is_alive())
        self.assertIsNone(transport._thread)
        self.assertIsNone(transport._stop_event)

    # --------------------------------------------------------------
    # 20. Concurrent start/stop never exposes a not-yet-started
    #     thread to join(), forced with an injected thread-creation
    #     seam rather than repeated scheduling luck.
    # --------------------------------------------------------------
    def test_concurrent_start_stop_no_unstarted_join(self) -> None:
        published = threading.Event()
        allow_start = threading.Event()
        started_real = threading.Event()

        ws = FakeWebSocket(expected_sends=1)

        class _WatchingThread(threading.Thread):
            def start(self) -> None:
                published.set()
                allow_start.wait()
                super().start()
                started_real.set()

        def factory(**kwargs: object) -> threading.Thread:
            return _WatchingThread(**kwargs)

        transport = KismetEventbusTransport(
            "http://example.com",
            ("t",),
            lambda _: None,
            _create_connection=lambda url: ws,
            _reconnect_waiter=self._noop_waiter,
            _thread_factory=factory,
        )

        start_errors: list[BaseException] = []
        start_done = threading.Event()

        def do_start() -> None:
            try:
                transport.start()
            except BaseException as exc:  # noqa: BLE001
                start_errors.append(exc)
            finally:
                start_done.set()

        stop_done = threading.Event()
        stop_errors: list[BaseException] = []

        def do_stop() -> None:
            try:
                transport.stop()
            except BaseException as exc:  # noqa: BLE001
                stop_errors.append(exc)
            finally:
                stop_done.set()

        starter = threading.Thread(
            target=do_start, daemon=True, name="start-helper"
        )
        stopper = threading.Thread(
            target=do_stop, daemon=True, name="stop-helper"
        )
        worker_ref: list[threading.Thread | None] = [None]

        try:
            starter.start()
            # Forced boundary: start() has published ``_thread`` and is
            # now blocked inside the thread-creation seam, still holding
            # the instance lock.
            self.assertTrue(published.wait(timeout=5))
            worker_ref[0] = transport._thread
            self.assertIsNotNone(worker_ref[0])
            self.assertFalse(started_real.is_set())

            # Launch stop() while the boundary exists.  It must block on
            # the lock start() still holds, so it can never join() the
            # unstarted thread.
            stopper.start()

            # Release the real start; start() returns the lock, the
            # worker actually starts, then stopper acquires the lock and
            # captures an already-started worker to join.
            allow_start.set()
            self.assertTrue(started_real.wait(timeout=5))
            self.assertTrue(start_done.wait(timeout=5))
            self.assertEqual(start_errors, [])
            self.assertTrue(stop_done.wait(timeout=5))
            self.assertEqual(stop_errors, [])
        finally:
            allow_start.set()
            self._assertJoined(starter)
            self._assertJoined(stopper)

        # The captured worker was actually started (not an unstarted
        # shell) and was driven to a clean stop by the concurrent stop.
        self.assertIsNotNone(worker_ref[0])
        self._assertJoined(worker_ref[0])
        self.assertIsNone(transport._thread)
        self.assertIsNone(transport._stop_event)

    # --------------------------------------------------------------
    # 21. Self-stop from a handler preserves _thread until the
    #     worker actually exits
    # --------------------------------------------------------------
    def test_self_stop_preserves_thread_until_exit(self) -> None:
        handler_done = threading.Event()
        worker_exited = threading.Event()
        observations: list[threading.Thread | None] = []

        def handler(msg: dict) -> None:
            observations.append(transport._thread)
            transport.stop()  # self-stop from a handler
            observations.append(transport._thread)
            handler_done.set()

        transport = KismetEventbusTransport(
            "http://example.com",
            ("t",),
            handler,
            _create_connection=lambda url: FakeWebSocket(
                recv_data=['{"x":1}'],
            ),
            _reconnect_waiter=self._noop_waiter,
        )
        original_worker = transport._worker

        def wrapped(se: threading.Event) -> None:
            try:
                original_worker(se)
            finally:
                worker_exited.set()

        transport._worker = wrapped  # type: ignore[method-assign]
        transport.start()
        thread_ref = transport._thread
        stop_event_ref = transport._stop_event
        self.assertIsNotNone(thread_ref)
        self.assertIsNotNone(stop_event_ref)
        self.assertTrue(handler_done.wait(timeout=5))
        # During the handler (before and after self-stop), _thread is
        # still the live worker; self-stop does not join or clear it.
        self.assertIs(observations[0], thread_ref)
        self.assertIs(observations[1], thread_ref)
        self.assertTrue(worker_exited.wait(timeout=5))
        # After actual worker exit, the outer finally clears _thread and
        # the generation stop event.
        self.assertIsNone(transport._thread)
        self.assertIsNone(transport._stop_event)
        # Bounded join on the captured worker before asserting death.
        self._assertJoined(thread_ref)
        self.assertFalse(thread_ref.is_alive())

    # --------------------------------------------------------------
    # 22. A start request during self-stop cannot overlap a
    #     second worker, and proves no new worker is created while
    #     a retiring earlier thread is still actually alive.
    # --------------------------------------------------------------
    def test_start_during_self_stop_cannot_overlap(self) -> None:
        in_handler = threading.Event()
        release_handler = threading.Event()
        worker_exited = threading.Event()
        create_count: list[int] = [0]

        def handler(msg: dict) -> None:
            in_handler.set()
            transport.stop()  # self-stop
            release_handler.wait()

        def create(url: str) -> FakeWebSocket:
            create_count[0] += 1
            return FakeWebSocket(recv_data=['{"x":1}'])

        def wrapped(se: threading.Event) -> None:
            try:
                original_worker(se)
            finally:
                worker_exited.set()

        transport = KismetEventbusTransport(
            "http://example.com",
            ("t",),
            handler,
            _create_connection=create,
            _reconnect_waiter=self._noop_waiter,
        )
        original_worker = transport._worker
        transport._worker = wrapped  # type: ignore[method-assign]
        transport.start()
        orig_thread = transport._thread
        orig_stop_event = transport._stop_event
        self.assertIsNotNone(orig_thread)
        self.assertIsNotNone(orig_stop_event)
        self.assertTrue(in_handler.wait(timeout=5))

        # Worker is alive inside the handler (self-stopped). A
        # concurrent start request from another thread must NOT spawn
        # a 2nd worker while the retiring earlier thread is alive.
        starter_done = threading.Event()

        def attempt_start() -> None:
            transport.start()
            starter_done.set()

        t = threading.Thread(target=attempt_start)
        t.start()
        self._assertJoined(t)
        self.assertTrue(starter_done.is_set())
        self.assertIs(transport._thread, orig_thread)
        self.assertIs(transport._stop_event, orig_stop_event)
        self.assertTrue(orig_thread.is_alive())
        # No second connection was ever created while A was alive.
        self.assertEqual(create_count[0], 1)

        release_handler.set()
        self.assertTrue(worker_exited.wait(timeout=5))
        self.assertIsNone(transport._thread)
        self.assertIsNone(transport._stop_event)
        self._assertJoined(orig_thread)
        self.assertFalse(orig_thread.is_alive())

    # --------------------------------------------------------------
    # 23. Worker generation regression: a worker tail that has
    #     returned from its target but has not yet exited the Python
    #     Thread bootstrap tail still blocks new generations and
    #     remains stoppable.
    # --------------------------------------------------------------
    def test_thread_run_tail_blocks_start_and_stop(self) -> None:
        target_returned = threading.Event()
        release_thread_tail = threading.Event()
        stop_entered = threading.Event()
        stop_finished = threading.Event()
        create_count: list[int] = [0]
        created_threads: list[threading.Thread] = []
        self_stop_enabled = threading.Event()
        self_stop_enabled.set()

        def handler(msg: dict) -> None:
            if self_stop_enabled.is_set():
                transport.stop()

        def create(url: str) -> FakeWebSocket:
            create_count[0] += 1
            return FakeWebSocket(recv_data=['{"x":1}'])

        def factory(**kwargs: object) -> threading.Thread:
            if len(created_threads) == 0:
                thread: threading.Thread = _TailBlockingThread(
                    target_returned=target_returned,
                    release_thread_tail=release_thread_tail,
                    **kwargs,
                )
            else:
                thread = threading.Thread(**kwargs)
            created_threads.append(thread)
            return thread

        transport = KismetEventbusTransport(
            "http://example.com",
            ("t",),
            handler,
            _create_connection=create,
            _reconnect_waiter=self._noop_waiter,
            _thread_factory=factory,
        )

        transport.start()
        a_thread = transport._thread
        a_stop_event = transport._stop_event
        self.assertIsNotNone(a_thread)
        self.assertIsNotNone(a_stop_event)
        self.assertTrue(target_returned.wait(timeout=5))
        self.assertIsNone(transport._thread)
        self.assertIs(transport._retiring_thread, a_thread)
        self.assertIs(transport._retiring_stop_event, a_stop_event)
        self.assertTrue(a_thread.is_alive())
        self.assertEqual(create_count[0], 1)

        # While A is in the thread tail, a new start must not create B.
        transport.start()
        self.assertEqual(create_count[0], 1)
        self.assertIs(transport._retiring_thread, a_thread)
        self.assertTrue(a_thread.is_alive())

        def do_stop() -> None:
            stop_entered.set()
            try:
                transport.stop()
            finally:
                stop_finished.set()

        stop_thread = threading.Thread(
            target=do_stop,
            daemon=True,
            name="tail-stop",
        )
        stop_thread.start()
        self.assertTrue(stop_entered.wait(timeout=5))
        self.assertFalse(stop_finished.is_set())

        release_thread_tail.set()
        self._assertJoined(a_thread)
        self.assertTrue(stop_finished.wait(timeout=5))
        self._assertJoined(stop_thread)

        self_stop_enabled.clear()
        self.assertIsNone(transport._thread)
        self.assertIsNone(transport._stop_event)
        self.assertIsNone(transport._retiring_thread)
        self.assertIsNone(transport._retiring_stop_event)

        transport.start()
        self.assertEqual(create_count[0], 2)
        b_thread = transport._thread
        self.assertIsNotNone(b_thread)
        transport.stop()
        self._assertJoined(b_thread)
        self.assertIsNone(transport._thread)
        self.assertIsNone(transport._stop_event)
        self.assertIsNone(transport._retiring_thread)
        self.assertIsNone(transport._retiring_stop_event)

    # --------------------------------------------------------------
    # 24. Worker generation regression: an injected
    #     ``Thread.start()`` failure leaves no unstarted thread
    #     published, stop() remains safe, and a later valid
    #     ``start()`` succeeds.
    # --------------------------------------------------------------
    def test_thread_start_failure_rolls_back_state(self) -> None:
        ws = FakeWebSocket(expected_sends=1)

        def factory(**kwargs: object) -> threading.Thread:
            return _FailStartThread(**kwargs)

        transport = KismetEventbusTransport(
            "http://example.com",
            ("t",),
            lambda _: None,
            _create_connection=lambda url: ws,
            _reconnect_waiter=self._noop_waiter,
            _thread_factory=factory,
        )

        with self.assertRaises(RuntimeError):
            transport.start()

        # No unstarted thread remains published; worker state is clean.
        self.assertIsNone(transport._thread)
        self.assertIsNone(transport._stop_event)

        # stop() remains safe (idempotent after failed start).
        transport.stop()
        self.assertIsNone(transport._thread)
        self.assertIsNone(transport._stop_event)

        # A later valid start() can succeed with a real factory.
        transport._thread_factory = threading.Thread  # type: ignore[assignment]
        transport.start()
        self.assertTrue(ws.all_sent.wait(timeout=5))
        thread_ref = transport._thread
        self.assertIsNotNone(thread_ref)
        transport.stop()
        self._assertJoined(thread_ref)
        self.assertIsNone(transport._thread)
        self.assertIsNone(transport._stop_event)

    # --------------------------------------------------------------
    # 24. Worker generation regression: a delayed stop that
    #     captured worker A can never signal, close, clear, or
    #     terminate a later worker B.
    # --------------------------------------------------------------
    def test_delayed_stop_cannot_touch_newer_generation(self) -> None:
        # A: blocks in the reconnect waiter until released, then exits
        # because its own (captured) stop event was set.
        a_in_waiter = threading.Event()
        release_a = threading.Event()

        def a_waiter(se: threading.Event) -> None:
            a_in_waiter.set()
            release_a.wait()
            # Wait until the delayed stop has set A's stop event.
            se.wait()

        transport = KismetEventbusTransport(
            "http://example.com",
            ("t",),
            lambda _: None,
            _create_connection=lambda url: FakeWebSocket(
                close_immediately=True,
            ),
            _reconnect_waiter=a_waiter,
        )
        transport.start()
        self.assertTrue(a_in_waiter.wait(timeout=5))

        a_thread = transport._thread
        a_stop_event = transport._stop_event
        self.assertIsNotNone(a_thread)
        self.assertIsNotNone(a_stop_event)
        self.assertIs(a_thread, transport._thread)

        # Gate the delayed stop after it bounded-joins A but before it
        # runs its identity-safe clear block, so B can start in between.
        after_join_a = threading.Event()
        proceed_stop = threading.Event()

        def stop_after_join(
            worked: threading.Thread, sev: threading.Event
        ) -> None:
            after_join_a.set()
            proceed_stop.wait()

        transport._stop_after_join = stop_after_join  # type: ignore[assignment]

        old_stop_done = threading.Event()

        def do_old_stop() -> None:
            transport.stop()
            old_stop_done.set()

        old_stop_thread = threading.Thread(
            target=do_old_stop, daemon=True, name="old-stop"
        )
        old_stop_thread.start()

        try:
            # Release A so it can retire once the delayed stop set A's
            # stop event and the bounded join returns.
            release_a.set()
            self.assertTrue(after_join_a.wait(timeout=5))
            self._assertJoined(a_thread)
            # After A finalized, _thread is None and old stop is paused.
            self.assertIsNone(transport._thread)
            self.assertFalse(old_stop_done.is_set())

            # Now start a second generation worker B with its own
            # socket and its own stop event, blocked in its recv loop.
            b_ws = FakeWebSocket(expected_sends=1)

            def b_create(url: str) -> FakeWebSocket:
                return b_ws

            transport._create_connection = b_create  # type: ignore[assignment]
            transport.start()
            self.assertTrue(b_ws.all_sent.wait(timeout=5))

            b_thread = transport._thread
            b_stop_event = transport._stop_event
            b_ws_ref = transport._ws
            b_ws_owner = transport._ws_owner
            self.assertIsNotNone(b_thread)
            self.assertIsNotNone(b_stop_event)
            self.assertIsNot(b_stop_event, a_stop_event)
            self.assertIs(b_ws_ref, b_ws)
            self.assertIs(b_ws_owner, b_thread)

            # B is untouched by the still-paused delayed stop.
            self.assertFalse(b_stop_event.is_set())
            self.assertFalse(b_ws.closed)
            self.assertTrue(b_thread.is_alive())

            # Resume the delayed stop: it must not clear B's state.
            proceed_stop.set()
            self.assertTrue(old_stop_done.wait(timeout=5))
            self._assertJoined(old_stop_thread)

            # B remains fully intact and published.
            self.assertIs(transport._thread, b_thread)
            self.assertIs(transport._stop_event, b_stop_event)
            self.assertIs(transport._ws, b_ws)
            self.assertIs(transport._ws_owner, b_thread)
            self.assertFalse(b_stop_event.is_set())
            self.assertFalse(b_ws.closed)
            self.assertTrue(b_thread.is_alive())

            # Cleanly stop B.
            transport.stop()
            self._assertJoined(b_thread)
            self.assertIsNone(transport._thread)
            self.assertIsNone(transport._stop_event)
        finally:
            proceed_stop.set()
            release_a.set()
            self._assertJoined(old_stop_thread)

    # --------------------------------------------------------------
    # 25. Old worker finalizer cannot clear a newer worker
    #     reference, exercised through a live older worker that
    #     is superseded by a live newer published reference.
    # --------------------------------------------------------------
    def test_old_finalizer_cannot_clear_newer_thread(self) -> None:
        transport = KismetEventbusTransport(
            "http://example.com",
            ("t",),
            lambda _: None,
            _create_connection=lambda url: FakeWebSocket(),
            _reconnect_waiter=self._noop_waiter,
        )

        # Live older and newer worker threads (actually alive, not
        # already-finished dummies), each with their own stop event.
        old_block = threading.Event()
        new_block = threading.Event()
        old_stop = threading.Event()
        new_stop = threading.Event()

        def old_target() -> None:
            old_block.wait()

        def new_target() -> None:
            new_block.wait()

        old_thread = threading.Thread(target=old_target)
        newer_thread = threading.Thread(target=new_target)
        old_thread.start()
        newer_thread.start()

        try:
            transport._thread = newer_thread
            transport._stop_event = new_stop

            # The old worker's outer finally runs after a newer worker
            # has been published: it must clear only its own state.
            transport._finalize_worker(old_thread, old_stop)
            self.assertIs(transport._thread, newer_thread)
            self.assertIs(transport._stop_event, new_stop)
        finally:
            old_block.set()
            new_block.set()
            self._assertJoined(old_thread)
            self._assertJoined(newer_thread)

    # --------------------------------------------------------------
    # 26. Stale socket cleanup cannot clear or close a newer
    #     worker's socket, exercised through a live older worker
    #     and a live newer published socket.
    # --------------------------------------------------------------
    def test_stale_socket_cleanup_cannot_touch_newer_socket(self) -> None:
        transport = KismetEventbusTransport(
            "http://example.com",
            ("t",),
            lambda _: None,
            _create_connection=lambda url: FakeWebSocket(),
            _reconnect_waiter=self._noop_waiter,
        )

        old_block = threading.Event()
        new_block = threading.Event()
        old_thread = threading.Thread(target=lambda: old_block.wait())
        newer_thread = threading.Thread(target=lambda: new_block.wait())
        ws_new = FakeWebSocket()
        old_thread.start()
        newer_thread.start()

        try:
            transport._ws = ws_new
            transport._ws_owner = newer_thread

            # Retire-via-clear path: identity-safe, leaves B untouched.
            transport._clear_ws_if_owner(old_thread)
            self.assertIs(transport._ws, ws_new)
            self.assertIs(transport._ws_owner, newer_thread)

            # Close path: identity-safe, leaves B's socket open.
            transport._close_ws_if_owner(old_thread)
            self.assertIs(transport._ws, ws_new)
            self.assertIs(transport._ws_owner, newer_thread)
            self.assertFalse(ws_new.closed)
        finally:
            old_block.set()
            new_block.set()
            self._assertJoined(old_thread)
            self._assertJoined(newer_thread)

    # --------------------------------------------------------------
    # 27. Real worker supersede path: a worker that finds itself
    #     no longer the current worker closes only its own socket
    #     and returns without touching the newer publication.
    # --------------------------------------------------------------
    def test_superseded_worker_closes_only_own_socket(self) -> None:
        released = threading.Event()
        first_ws: list[FakeWebSocket] = []

        def create(url: str) -> FakeWebSocket:
            ws = FakeWebSocket()
            first_ws.append(ws)
            return ws

        transport = KismetEventbusTransport(
            "http://example.com",
            ("t",),
            lambda _: None,
            _create_connection=create,
            _reconnect_waiter=self._noop_waiter,
        )

        # Block the first worker between create and publish so the
        # test can publish a newer worker reference underneath it.
        original_worker = transport._worker

        def slow_worker(se: threading.Event) -> None:
            released.wait()
            original_worker(se)

        transport._worker = slow_worker  # type: ignore[method-assign]
        transport.start()
        a_thread = transport._thread
        a_stop = transport._stop_event
        self.assertIsNotNone(a_thread)

        # Publish a newer live worker + socket underneath the still-
        # running (blocked) older worker.
        new_block = threading.Event()
        newer_thread = threading.Thread(
            target=lambda: new_block.wait(),
            daemon=True,
            name="newer-worker",
        )
        newer_thread.start()
        newer_ws = FakeWebSocket()
        transport._thread = newer_thread
        transport._stop_event = threading.Event()
        transport._ws = newer_ws
        transport._ws_owner = newer_thread

        try:
            # Release A so it reaches _publish_ws, which must detect
            # the supersession, return False, close its own fresh
            # socket, and leave the newer publication intact.
            released.set()
            self._assertJoined(a_thread)
            self.assertIs(transport._thread, newer_thread)
            self.assertIs(transport._ws, newer_ws)
            self.assertIs(transport._ws_owner, newer_thread)
            self.assertFalse(newer_ws.closed)

            # The orphaned socket A created was closed once; the newer
            # socket A would have tried to publish was closed on detect.
            if first_ws:
                self.assertTrue(first_ws[0].closed)
        finally:
            new_block.set()
            released.set()
            self._assertJoined(newer_thread)


if __name__ == "__main__":
    unittest.main()
