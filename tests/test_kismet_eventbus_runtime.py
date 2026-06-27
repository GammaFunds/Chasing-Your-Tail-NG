from __future__ import annotations

import ast
import builtins
import contextlib
import inspect
import io
import os
import socket
import sqlite3
import ssl
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import kismet_eventbus_runtime as runtime_module
from kismet_eventbus_runtime import (
    KismetEventbusRuntime,
    KismetEventbusRuntimeHealthV1,
    KismetEventbusRuntimeStatusV1,
)
from kismet_eventbus_runtime_config import (
    KismetEventbusTransportConfigV1,
    create_kismet_eventbus_transport_config,
)
from kismet_eventbus_transport import KismetEventbusTransportStatusV1


_SYNTHETIC_AUTH = b"Basic c3ludGhldGljOnRlc3Q="
_SYNTHETIC_HMAC = b"runtime-test-hmac-key-32-bytes!!"
_SYNTHETIC_PATH = "synthetic/runtime-observations.sqlite"
_SYNTHETIC_SESSION = "session_runtime_test"
_SYNTHETIC_SENSOR = "sensor_runtime_test"


def _config() -> KismetEventbusTransportConfigV1:
    return create_kismet_eventbus_transport_config(
        base_url="https://kismet.example.test",
        topics=("NEW_DEVICE",),
        authorization_header_value=_SYNTHETIC_AUTH,
        tls_mode="verify_required",
        connect_timeout_s=10.0,
        reconnect_delay_s=5.0,
        stop_join_timeout_s=1.0,
    )


class _RecordingTransport:
    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0
        self.start_error: BaseException | None = None
        self.stop_error: BaseException | None = None
        self._status = KismetEventbusTransportStatusV1(
            worker_lifecycle="stopped",
            stop_requested=False,
        )

    @property
    def status(self) -> KismetEventbusTransportStatusV1:
        return self._status

    def set_status(
        self,
        worker_lifecycle: str,
        *,
        stop_requested: bool = False,
    ) -> None:
        self._status = KismetEventbusTransportStatusV1(
            worker_lifecycle=worker_lifecycle,
            stop_requested=stop_requested,
        )

    def start(self) -> None:
        self.start_calls += 1
        if self.start_error is not None:
            raise self.start_error
        self.set_status("running")

    def stop(self) -> None:
        self.stop_calls += 1
        if self.stop_error is not None:
            raise self.stop_error
        self.set_status("stopped")


class _BlockingStartTransport(_RecordingTransport):
    def __init__(self) -> None:
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    def start(self) -> None:
        self.start_calls += 1
        self.entered.set()
        self.release.wait()


class _BlockingStopTransport(_RecordingTransport):
    def __init__(self) -> None:
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    def stop(self) -> None:
        self.stop_calls += 1
        self.entered.set()
        self.release.wait()


class KismetEventbusRuntimeTests(unittest.TestCase):
    maxDiff = None

    @staticmethod
    def _provider() -> int:
        return 1

    def _runtime_with_transport(
        self,
        transport: _RecordingTransport,
    ) -> KismetEventbusRuntime:
        with patch.object(
            runtime_module.KismetEventbusTransport,
            "from_config",
            return_value=transport,
        ):
            return KismetEventbusRuntime(
                _config(),
                _SYNTHETIC_PATH,
                hmac_key=_SYNTHETIC_HMAC,
                collection_session_id=_SYNTHETIC_SESSION,
                sensor_id=_SYNTHETIC_SENSOR,
                ingest_timestamp_us_provider=self._provider,
            )

    @staticmethod
    def _join(thread: threading.Thread) -> None:
        thread.join(timeout=5)
        assert not thread.is_alive(), "helper thread did not terminate"

    def test_public_surface_and_signature(self) -> None:
        self.assertEqual(
            runtime_module.__all__,
            [
                "KismetEventbusRuntime",
                "KismetEventbusRuntimeError",
                "KismetEventbusRuntimeHealthV1",
                "KismetEventbusRuntimeStatusV1",
            ],
        )
        self.assertEqual(
            tuple(inspect.signature(KismetEventbusRuntime.__init__).parameters),
            (
                "self",
                "config",
                "db_path",
                "hmac_key",
                "collection_session_id",
                "sensor_id",
                "ingest_timestamp_us_provider",
            ),
        )
        self.assertIsInstance(
            KismetEventbusRuntime.status,
            property,
        )
        self.assertIsInstance(
            KismetEventbusRuntime.health,
            property,
        )
        self.assertEqual(
            tuple(inspect.signature(KismetEventbusRuntime.recover).parameters),
            ("self",),
        )

    def test_health_dataclass_contract(self) -> None:
        self.assertEqual(
            tuple(KismetEventbusRuntimeHealthV1.__dataclass_fields__),
            (
                "runtime_lifecycle",
                "transport_worker_lifecycle",
                "control_state",
                "recovery_action",
            ),
        )

        health = KismetEventbusRuntimeHealthV1(
            runtime_lifecycle="stopped",
            transport_worker_lifecycle="stopped",
            control_state="inactive",
            recovery_action="none",
        )
        runtime = self._runtime_with_transport(_RecordingTransport())
        self.assertEqual(
            health,
            KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="stopped",
                transport_worker_lifecycle="stopped",
                control_state="inactive",
                recovery_action="none",
            ),
        )
        self.assertIsNot(health, runtime.health)
        self.assertFalse(hasattr(health, "__dict__"))
        self.assertEqual(repr(health), "KismetEventbusRuntimeHealthV1()")
        self.assertEqual(str(health), "KismetEventbusRuntimeHealthV1()")

        with self.assertRaises(Exception):
            health.runtime_lifecycle = "active"  # type: ignore[misc]

        for kwargs in (
            {
                "runtime_lifecycle": "invalid",
                "transport_worker_lifecycle": "stopped",
                "control_state": "inactive",
                "recovery_action": "none",
            },
            {
                "runtime_lifecycle": "stopped",
                "transport_worker_lifecycle": "invalid",
                "control_state": "inactive",
                "recovery_action": "none",
            },
            {
                "runtime_lifecycle": "stopped",
                "transport_worker_lifecycle": "stopped",
                "control_state": "invalid",
                "recovery_action": "none",
            },
            {
                "runtime_lifecycle": "stopped",
                "transport_worker_lifecycle": "stopped",
                "control_state": "inactive",
                "recovery_action": "invalid",
            },
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError) as ctx:
                    KismetEventbusRuntimeHealthV1(**kwargs)
                expected_field = next(
                    field
                    for field, value in kwargs.items()
                    if value == "invalid"
                )

                self.assertEqual(
                    str(ctx.exception),
                    expected_field,
                )

    def test_constructs_exactly_one_handler_and_transport(self) -> None:
        config = _config()
        handler = object()
        transport = object()

        with patch.object(
            runtime_module,
            "KismetEventbusObservationHandler",
            return_value=handler,
        ) as handler_factory, patch.object(
            runtime_module.KismetEventbusTransport,
            "from_config",
            return_value=transport,
        ) as transport_factory:
            runtime = KismetEventbusRuntime(
                config,
                _SYNTHETIC_PATH,
                hmac_key=_SYNTHETIC_HMAC,
                collection_session_id=_SYNTHETIC_SESSION,
                sensor_id=_SYNTHETIC_SENSOR,
                ingest_timestamp_us_provider=self._provider,
            )

        handler_factory.assert_called_once_with(
            _SYNTHETIC_PATH,
            hmac_key=_SYNTHETIC_HMAC,
            collection_session_id=_SYNTHETIC_SESSION,
            sensor_id=_SYNTHETIC_SENSOR,
            ingest_timestamp_us_provider=self._provider,
        )
        transport_factory.assert_called_once_with(config, handler)
        self.assertIs(runtime._handler, handler)
        self.assertIs(runtime._transport, transport)

    def test_rejects_non_config_before_component_construction(self) -> None:
        with patch.object(
            runtime_module,
            "KismetEventbusObservationHandler",
        ) as handler_factory, patch.object(
            runtime_module.KismetEventbusTransport,
            "from_config",
        ) as transport_factory:
            with self.assertRaises(runtime_module.KismetEventbusRuntimeError):
                KismetEventbusRuntime(
                    object(),  # type: ignore[arg-type]
                    _SYNTHETIC_PATH,
                    hmac_key=_SYNTHETIC_HMAC,
                    collection_session_id=_SYNTHETIC_SESSION,
                    sensor_id=_SYNTHETIC_SENSOR,
                    ingest_timestamp_us_provider=self._provider,
                )

        handler_factory.assert_not_called()
        transport_factory.assert_not_called()

    def test_construction_is_side_effect_free(self) -> None:
        real_import = builtins.__import__

        def forbidden(name: str):
            def fail(*args: object, **kwargs: object) -> object:
                raise AssertionError(f"forbidden {name}")
            return fail

        def guarded_import(
            name: str,
            globals: object = None,
            locals: object = None,
            fromlist: object = (),
            level: int = 0,
        ) -> object:
            if name.split(".")[0] == "websocket":
                raise AssertionError("websocket imported")
            return real_import(name, globals, locals, fromlist, level)

        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "observations.sqlite"

            with patch.object(
                builtins,
                "__import__",
                side_effect=guarded_import,
            ), patch.object(
                builtins,
                "open",
                forbidden("open"),
            ), patch.object(
                sqlite3,
                "connect",
                forbidden("sqlite3.connect"),
            ), patch.object(
                socket,
                "socket",
                forbidden("socket.socket"),
            ), patch.object(
                threading.Thread,
                "start",
                forbidden("thread.start"),
            ), patch.object(
                Path,
                "open",
                forbidden("Path.open"),
            ), patch.object(
                Path,
                "mkdir",
                forbidden("Path.mkdir"),
            ), patch.dict(
                os.environ,
                {},
                clear=True,
            ):
                runtime = KismetEventbusRuntime(
                    _config(),
                    db_path,
                    hmac_key=_SYNTHETIC_HMAC,
                    collection_session_id=_SYNTHETIC_SESSION,
                    sensor_id=_SYNTHETIC_SENSOR,
                    ingest_timestamp_us_provider=self._provider,
                )

            self.assertFalse(db_path.exists())
            self.assertEqual(runtime.status.lifecycle, "stopped")

    def test_runtime_module_has_no_forbidden_imports_or_calls(self) -> None:
        source = Path("kismet_eventbus_runtime.py").read_text(encoding="utf-8")
        tree = ast.parse(source)

        forbidden_imports = {
            "logging",
            "netrc",
            "keyring",
            "os",
            "socket",
            "sqlite3",
            "subprocess",
            "websocket",
        }
        imported: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])

        self.assertEqual(imported & forbidden_imports, set())

        forbidden_calls = {
            "open",
            "connect",
            "getenv",
            "expanduser",
            "get_password",
            "mkdir",
            "run",
            "Popen",
            "socket",
            "write_bytes",
            "write_text",
        }

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, forbidden_calls)
            elif isinstance(node.func, ast.Attribute):
                self.assertNotIn(node.func.attr, forbidden_calls)

    def test_initial_status_is_immutable_and_read_only(self) -> None:
        runtime = self._runtime_with_transport(_RecordingTransport())
        status = runtime.status

        self.assertEqual(
            status,
            KismetEventbusRuntimeStatusV1(
                lifecycle="stopped",
                generation=0,
                start_attempt_count=0,
                stop_attempt_count=0,
            ),
        )
        self.assertFalse(hasattr(status, "__dict__"))
        with self.assertRaises(Exception):
            status.lifecycle = "active"  # type: ignore[misc]

        self.assertFalse(hasattr(runtime, "transport"))
        self.assertFalse(hasattr(runtime, "handler"))
        self.assertFalse(hasattr(runtime, "config"))
        self.assertFalse(hasattr(runtime, "db_path"))

    def test_status_validation_rejects_invalid_values(self) -> None:
        invalid = (
            {
                "lifecycle": "invalid",
                "generation": 0,
                "start_attempt_count": 0,
                "stop_attempt_count": 0,
            },
            {
                "lifecycle": "stopped",
                "generation": True,
                "start_attempt_count": 0,
                "stop_attempt_count": 0,
            },
            {
                "lifecycle": "stopped",
                "generation": 0,
                "start_attempt_count": -1,
                "stop_attempt_count": 0,
            },
        )

        for kwargs in invalid:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    KismetEventbusRuntimeStatusV1(**kwargs)

    def test_start_stop_idempotency_and_generation_count(self) -> None:
        transport = _RecordingTransport()
        runtime = self._runtime_with_transport(transport)

        runtime.start()
        self.assertEqual(
            runtime.status,
            KismetEventbusRuntimeStatusV1(
                lifecycle="active",
                generation=1,
                start_attempt_count=1,
                stop_attempt_count=0,
            ),
        )

        runtime.start()
        self.assertEqual(transport.start_calls, 1)
        self.assertEqual(runtime.status.generation, 1)
        self.assertEqual(runtime.status.start_attempt_count, 2)

        runtime.stop()
        self.assertEqual(transport.stop_calls, 1)
        self.assertEqual(runtime.status.lifecycle, "stopped")

        runtime.stop()
        self.assertEqual(transport.stop_calls, 1)
        self.assertEqual(runtime.status.stop_attempt_count, 2)

        runtime.start()
        self.assertEqual(transport.start_calls, 2)
        self.assertEqual(runtime.status.generation, 2)
        runtime.stop()

    def test_starting_status_is_observable(self) -> None:
        transport = _BlockingStartTransport()
        runtime = self._runtime_with_transport(transport)
        errors: list[BaseException] = []

        def start() -> None:
            try:
                runtime.start()
            except BaseException as exc:
                errors.append(exc)

        thread = threading.Thread(target=start)
        thread.start()
        self.assertTrue(transport.entered.wait(timeout=5))
        self.assertEqual(runtime.status.lifecycle, "starting")
        self.assertEqual(runtime.status.generation, 0)

        transport.release.set()
        self._join(thread)
        self.assertEqual(errors, [])
        self.assertEqual(runtime.status.lifecycle, "active")
        self.assertEqual(runtime.status.generation, 1)
        runtime.stop()

    def test_stopping_status_is_observable(self) -> None:
        transport = _BlockingStopTransport()
        runtime = self._runtime_with_transport(transport)
        runtime.start()
        errors: list[BaseException] = []

        def stop() -> None:
            try:
                runtime.stop()
            except BaseException as exc:
                errors.append(exc)

        thread = threading.Thread(target=stop)
        thread.start()
        self.assertTrue(transport.entered.wait(timeout=5))
        self.assertEqual(runtime.status.lifecycle, "stopping")
        self.assertEqual(runtime.status.generation, 1)

        transport.release.set()
        self._join(thread)
        self.assertEqual(errors, [])
        self.assertEqual(runtime.status.lifecycle, "stopped")

    def test_start_failure_is_content_free_and_restartable(self) -> None:
        transport = _RecordingTransport()
        sensitive = "secret path identifier payload authorization"
        transport.start_error = RuntimeError(sensitive)
        runtime = self._runtime_with_transport(transport)

        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with self.assertRaises(RuntimeError):
                runtime.start()

        self.assertEqual(runtime.status.lifecycle, "start_failed")
        self.assertEqual(runtime.status.generation, 0)
        self.assertNotIn(sensitive, repr(runtime))
        self.assertNotIn(sensitive, str(runtime))
        self.assertNotIn(sensitive, repr(runtime.status))
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")

        transport.start_error = None
        runtime.start()
        self.assertEqual(runtime.status.lifecycle, "active")
        self.assertEqual(runtime.status.generation, 1)
        runtime.stop()

    def test_stop_failure_blocks_new_generation_until_retry_succeeds(self) -> None:
        transport = _RecordingTransport()
        runtime = self._runtime_with_transport(transport)
        runtime.start()

        sensitive = "secret path identifier payload authorization"
        transport.stop_error = RuntimeError(sensitive)

        with self.assertRaises(RuntimeError):
            runtime.stop()

        self.assertEqual(runtime.status.lifecycle, "stop_failed")
        self.assertEqual(runtime.status.generation, 1)
        self.assertNotIn(sensitive, repr(runtime))
        self.assertNotIn(sensitive, repr(runtime.status))

        with self.assertRaises(runtime_module.KismetEventbusRuntimeError) as ctx:
            runtime.start()

        self.assertEqual(str(ctx.exception), "stop_failed")
        self.assertEqual(transport.start_calls, 1)
        self.assertEqual(runtime.status.lifecycle, "stop_failed")

        transport.stop_error = None
        runtime.stop()
        self.assertEqual(transport.stop_calls, 2)
        self.assertEqual(runtime.status.lifecycle, "stopped")

    def test_initial_health_is_inactive_and_none(self) -> None:
        runtime = self._runtime_with_transport(_RecordingTransport())
        self.assertEqual(
            runtime.health,
            KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="stopped",
                transport_worker_lifecycle="stopped",
                control_state="inactive",
                recovery_action="none",
            ),
        )
        self.assertIsNot(runtime.health, runtime.health)

    def test_active_running_health_classification(self) -> None:
        transport = _RecordingTransport()
        runtime = self._runtime_with_transport(transport)
        runtime.start()

        self.assertEqual(
            runtime.health,
            KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="active",
                transport_worker_lifecycle="running",
                control_state="worker_running",
                recovery_action="none",
            ),
        )
        runtime.stop()

    def test_active_stopped_health_requires_restart(self) -> None:
        transport = _RecordingTransport()
        runtime = self._runtime_with_transport(transport)
        runtime.start()
        transport.set_status("stopped")

        health = runtime.health
        self.assertEqual(
            health,
            KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="active",
                transport_worker_lifecycle="stopped",
                control_state="recovery_required",
                recovery_action="restart",
            ),
        )

    def test_restart_recovery_stops_then_starts(self) -> None:
        transport = _RecordingTransport()
        events: list[str] = []

        original_start = transport.start
        original_stop = transport.stop

        def wrapped_start() -> None:
            events.append("start")
            original_start()

        def wrapped_stop() -> None:
            events.append("stop")
            original_stop()

        transport.start = wrapped_start  # type: ignore[assignment]
        transport.stop = wrapped_stop  # type: ignore[assignment]
        runtime = self._runtime_with_transport(transport)
        runtime.start()
        transport.set_status("stopped")

        runtime.recover()

        self.assertEqual(events, ["start", "stop", "start"])
        self.assertEqual(transport.start_calls, 2)
        self.assertEqual(transport.stop_calls, 1)
        self.assertEqual(runtime.status.generation, 2)
        self.assertEqual(runtime.status.lifecycle, "active")

    def test_restart_stop_failure_prevents_start(self) -> None:
        transport = _RecordingTransport()
        runtime = self._runtime_with_transport(transport)
        runtime.start()
        transport.set_status("stopped")
        transport.stop_error = RuntimeError("stop failed")

        with self.assertRaises(RuntimeError):
            runtime.recover()

        self.assertEqual(transport.start_calls, 1)
        self.assertEqual(transport.stop_calls, 1)
        self.assertEqual(runtime.status.lifecycle, "stop_failed")

    def test_start_failed_recovers_through_one_start(self) -> None:
        transport = _RecordingTransport()
        runtime = self._runtime_with_transport(transport)
        transport.start_error = RuntimeError("start failed")

        with self.assertRaises(RuntimeError):
            runtime.start()

        self.assertEqual(runtime.status.lifecycle, "start_failed")
        self.assertEqual(runtime.status.generation, 0)

        transport.start_error = None
        runtime.recover()

        self.assertEqual(transport.start_calls, 2)
        self.assertEqual(runtime.status.lifecycle, "active")
        self.assertEqual(runtime.status.generation, 1)

    def test_stop_failed_recovers_through_one_stop(self) -> None:
        transport = _RecordingTransport()
        runtime = self._runtime_with_transport(transport)
        runtime.start()
        transport.stop_error = RuntimeError("stop failed")

        with self.assertRaises(RuntimeError):
            runtime.stop()

        self.assertEqual(runtime.status.lifecycle, "stop_failed")
        self.assertEqual(transport.start_calls, 1)

        transport.stop_error = None
        runtime.recover()

        self.assertEqual(transport.stop_calls, 2)
        self.assertEqual(transport.start_calls, 1)
        self.assertEqual(runtime.status.lifecycle, "stopped")

    def test_stopped_running_recovers_through_one_stop(self) -> None:
        transport = _RecordingTransport()
        transport.set_status("running")
        runtime = self._runtime_with_transport(transport)

        runtime.recover()

        self.assertEqual(transport.stop_calls, 1)
        self.assertEqual(transport.start_calls, 0)
        self.assertEqual(runtime.status.lifecycle, "stopped")

    def test_starting_and_stopping_health_snapshots_transitioning(self) -> None:
        start_transport = _BlockingStartTransport()
        start_runtime = self._runtime_with_transport(start_transport)

        start_errors: list[BaseException] = []

        def do_start() -> None:
            try:
                start_runtime.start()
            except BaseException as exc:
                start_errors.append(exc)

        starter = threading.Thread(target=do_start, daemon=True)
        starter.start()
        self.assertTrue(start_transport.entered.wait(timeout=5))
        self.assertEqual(
            start_runtime.health,
            KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="starting",
                transport_worker_lifecycle="stopped",
                control_state="transitioning",
                recovery_action="wait",
            ),
        )
        start_transport.release.set()
        self._join(starter)
        self.assertEqual(start_errors, [])
        start_runtime.stop()

        stop_transport = _BlockingStopTransport()
        stop_runtime = self._runtime_with_transport(stop_transport)
        stop_runtime.start()

        stop_errors: list[BaseException] = []

        def do_stop() -> None:
            try:
                stop_runtime.stop()
            except BaseException as exc:
                stop_errors.append(exc)

        stopper = threading.Thread(target=do_stop, daemon=True)
        stopper.start()
        self.assertTrue(stop_transport.entered.wait(timeout=5))
        self.assertEqual(
            stop_runtime.health,
            KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="stopping",
                transport_worker_lifecycle="running",
                control_state="transitioning",
                recovery_action="wait",
            ),
        )
        stop_transport.release.set()
        self._join(stopper)
        self.assertEqual(stop_errors, [])
        self.assertEqual(stop_runtime.status.lifecycle, "stopped")

    def test_recover_none_is_noop(self) -> None:
        transport = _RecordingTransport()
        runtime = self._runtime_with_transport(transport)

        runtime.recover()

        self.assertEqual(transport.start_calls, 0)
        self.assertEqual(transport.stop_calls, 0)
        self.assertEqual(
            runtime.health,
            KismetEventbusRuntimeHealthV1(
                runtime_lifecycle="stopped",
                transport_worker_lifecycle="stopped",
                control_state="inactive",
                recovery_action="none",
            ),
        )

    def test_recover_reports_concurrent_transitions_without_waiting(
        self,
    ) -> None:
        def assert_transition_error(
            runtime: KismetEventbusRuntime,
            entered: threading.Event,
            release: threading.Event,
            operation: object,
        ) -> None:
            operation_errors: list[BaseException] = []
            recovery_errors: list[BaseException] = []
            recovery_done = threading.Event()

            def run_operation() -> None:
                try:
                    operation()  # type: ignore[operator]
                except BaseException as exc:
                    operation_errors.append(exc)

            def run_recovery() -> None:
                try:
                    runtime.recover()
                except BaseException as exc:
                    recovery_errors.append(exc)
                finally:
                    recovery_done.set()

            operation_thread = threading.Thread(
                target=run_operation,
                daemon=True,
            )
            recovery_thread = threading.Thread(
                target=run_recovery,
                daemon=True,
            )

            operation_thread.start()
            self.assertTrue(entered.wait(timeout=5))
            recovery_thread.start()

            try:
                self.assertTrue(
                    recovery_done.wait(timeout=1),
                    "recover waited behind an active transition",
                )
            finally:
                release.set()
                self._join(operation_thread)
                self._join(recovery_thread)

            self.assertEqual(operation_errors, [])
            self.assertEqual(len(recovery_errors), 1)
            self.assertIsInstance(
                recovery_errors[0],
                runtime_module.KismetEventbusRuntimeError,
            )
            self.assertEqual(
                str(recovery_errors[0]),
                "transition_in_progress",
            )

        start_transport = _BlockingStartTransport()
        start_runtime = self._runtime_with_transport(
            start_transport
        )

        assert_transition_error(
            start_runtime,
            start_transport.entered,
            start_transport.release,
            start_runtime.start,
        )

        self.assertEqual(
            start_runtime.status.start_attempt_count,
            1,
        )
        self.assertEqual(
            start_runtime.status.lifecycle,
            "active",
        )
        start_runtime.stop()

        stop_transport = _BlockingStopTransport()
        stop_runtime = self._runtime_with_transport(
            stop_transport
        )
        stop_runtime.start()

        assert_transition_error(
            stop_runtime,
            stop_transport.entered,
            stop_transport.release,
            stop_runtime.stop,
        )

        self.assertEqual(
            stop_runtime.status.stop_attempt_count,
            1,
        )
        self.assertEqual(
            stop_runtime.status.lifecycle,
            "stopped",
        )

    def test_recover_propagates_delegated_exceptions_unchanged(self) -> None:
        transport = _RecordingTransport()
        runtime = self._runtime_with_transport(transport)
        runtime.start()
        transport.set_status("stopped")
        exc = RuntimeError("delegated stop")
        transport.stop_error = exc

        with self.assertRaises(RuntimeError) as ctx:
            runtime.recover()

        self.assertIs(ctx.exception, exc)
        self.assertEqual(runtime.status.lifecycle, "stop_failed")

    def test_runtime_module_does_not_access_private_transport_fields(
        self,
    ) -> None:
        source = Path("kismet_eventbus_runtime.py").read_text(encoding="utf-8")
        for forbidden in (
            "._thread",
            "._retiring_thread",
            "._stop_event",
            "._retiring_stop_event",
            "._ws",
            "._ws_owner",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_same_handler_and_transport_are_reused_across_generations(self) -> None:
        config = _config()
        handler = object()
        transport = _RecordingTransport()

        with patch.object(
            runtime_module,
            "KismetEventbusObservationHandler",
            return_value=handler,
        ) as handler_factory, patch.object(
            runtime_module.KismetEventbusTransport,
            "from_config",
            return_value=transport,
        ) as transport_factory:
            runtime = KismetEventbusRuntime(
                config,
                _SYNTHETIC_PATH,
                hmac_key=_SYNTHETIC_HMAC,
                collection_session_id=_SYNTHETIC_SESSION,
                sensor_id=_SYNTHETIC_SENSOR,
                ingest_timestamp_us_provider=self._provider,
            )

            runtime.start()
            runtime.stop()
            runtime.start()
            runtime.stop()

        handler_factory.assert_called_once()
        transport_factory.assert_called_once_with(config, handler)
        self.assertIs(runtime._handler, handler)
        self.assertIs(runtime._transport, transport)
        self.assertEqual(transport.start_calls, 2)
        self.assertEqual(transport.stop_calls, 2)
        self.assertEqual(runtime.status.generation, 2)

    def test_repr_str_and_status_do_not_expose_configuration(self) -> None:
        runtime = self._runtime_with_transport(_RecordingTransport())
        output = "\n".join(
            (
                repr(runtime),
                str(runtime),
                repr(runtime.status),
                str(runtime.status),
            )
        )

        forbidden = (
            _SYNTHETIC_AUTH.decode("ascii"),
            str(_SYNTHETIC_AUTH),
            _SYNTHETIC_HMAC.decode("ascii"),
            str(_SYNTHETIC_HMAC),
            _SYNTHETIC_PATH,
            _SYNTHETIC_SESSION,
            _SYNTHETIC_SENSOR,
            "kismet.example.test",
            "NEW_DEVICE",
        )

        for value in forbidden:
            with self.subTest(value=value):
                self.assertNotIn(value, output)


if __name__ == "__main__":
    unittest.main()
