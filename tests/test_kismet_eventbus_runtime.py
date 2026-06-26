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
    KismetEventbusRuntimeStatusV1,
)
from kismet_eventbus_runtime_config import (
    KismetEventbusTransportConfigV1,
    create_kismet_eventbus_transport_config,
)


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

    def start(self) -> None:
        self.start_calls += 1
        if self.start_error is not None:
            raise self.start_error

    def stop(self) -> None:
        self.stop_calls += 1
        if self.stop_error is not None:
            raise self.stop_error


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
