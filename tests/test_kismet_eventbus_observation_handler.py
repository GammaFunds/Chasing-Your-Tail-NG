import ast
import contextlib
import io
import inspect
import sqlite3
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import kismet_eventbus_observation_handler as handler_module
from kismet_eventbus_new_device_adapter import (
    NEW_DEVICE,
    decode_kismet_new_device_envelope,
)
from kismet_eventbus_observation_handler import (
    KismetEventbusObservationHandler,
)
from observation_store import ObservationStore


class KismetEventbusObservationHandlerTests(unittest.TestCase):
    KEY = b"handler-test-key-32-bytes-long!!"

    @staticmethod
    def _payload(**overrides):
        payload = {
            "kismet.device.base.key": "AA:BB:CC:DD:EE:FF",
            "kismet.device.base.macaddr": "AA:BB:CC:DD:EE:FF",
            "kismet.device.base.first_time": 1234567890,
        }
        payload.update(overrides)
        return payload

    @classmethod
    def _envelope(cls, **overrides):
        return {NEW_DEVICE: cls._payload(**overrides)}

    def _handler(self, db_path, timestamps):
        iterator = iter(timestamps)

        def provider():
            return next(iterator)

        return KismetEventbusObservationHandler(
            db_path,
            hmac_key=self.KEY,
            collection_session_id="session_alpha",
            sensor_id="sensor_alpha",
            ingest_timestamp_us_provider=provider,
        ), provider

    @staticmethod
    def _db_path(tempdir):
        return Path(tempdir) / "observations.sqlite"

    def test_public_surface(self):
        self.assertEqual(
            handler_module.__all__,
            ["KismetEventbusObservationHandler"],
        )
        signature = inspect.signature(KismetEventbusObservationHandler.__init__)
        self.assertEqual(
            tuple(signature.parameters),
            (
                "self",
                "db_path",
                "hmac_key",
                "collection_session_id",
                "sensor_id",
                "ingest_timestamp_us_provider",
            ),
        )
        self.assertTrue(callable(KismetEventbusObservationHandler))

        handler = KismetEventbusObservationHandler(
            Path("/tmp/handler-surface.sqlite"),
            hmac_key=self.KEY,
            collection_session_id="session_alpha",
            sensor_id="sensor_alpha",
            ingest_timestamp_us_provider=lambda: 1,
        )

        self.assertFalse(hasattr(handler, "close"))
        self.assertFalse(hasattr(handler, "connection"))
        self.assertFalse(hasattr(handler, "store"))
        self.assertFalse(hasattr(handler, "__enter__"))
        self.assertFalse(hasattr(handler, "__exit__"))

    def test_constructor_is_side_effect_free(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = self._db_path(tempdir)
            calls = []

            def provider():
                calls.append("called")
                return 1

            handler = KismetEventbusObservationHandler(
                path,
                hmac_key=self.KEY,
                collection_session_id="session_alpha",
                sensor_id="sensor_alpha",
                ingest_timestamp_us_provider=provider,
            )

            self.assertFalse(path.exists())
            self.assertEqual(calls, [])
            self.assertFalse(hasattr(handler, "_store"))

    def test_valid_envelope_inserts_and_round_trips(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = self._db_path(tempdir)
            handler, _ = self._handler(path, [1_000_500])

            self.assertFalse(path.exists())
            expected = decode_kismet_new_device_envelope(
                self._envelope(),
                hmac_key=self.KEY,
                collection_session_id="session_alpha",
                sensor_id="sensor_alpha",
                ingest_timestamp_us=1_000_500,
            )
            self.assertEqual(handler(self._envelope()), "inserted")
            self.assertTrue(path.exists())

            with ObservationStore(path) as store:
                self.assertEqual(
                    store.get_observation_event(expected.observation_id),
                    expected,
                )

    def test_exact_replay_returns_duplicate_and_preserves_first_row(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = self._db_path(tempdir)
            calls = {"count": 0}
            timestamps = iter([1_000_500, 2_000_500])

            def provider():
                calls["count"] += 1
                return next(timestamps)

            handler = KismetEventbusObservationHandler(
                path,
                hmac_key=self.KEY,
                collection_session_id="session_alpha",
                sensor_id="sensor_alpha",
                ingest_timestamp_us_provider=provider,
            )

            first = handler(self._envelope())
            second = handler(self._envelope())

            self.assertEqual(first, "inserted")
            self.assertEqual(second, "duplicate")

            with ObservationStore(path) as store:
                stored = store.list_observation_events()
                self.assertEqual(len(stored), 1)
                self.assertEqual(stored[0].ingest_timestamp_us, 1_000_500)
            self.assertEqual(calls["count"], 2)

    def test_identity_conflict_preserves_original_row(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = self._db_path(tempdir)
            handler, _ = self._handler(path, [1_000_500, 2_000_500])
            baseline = decode_kismet_new_device_envelope(
                self._envelope(),
                hmac_key=self.KEY,
                collection_session_id="session_alpha",
                sensor_id="sensor_alpha",
                ingest_timestamp_us=1_000_500,
            )
            conflict = replace(
                baseline,
                source_timestamp_us=baseline.source_timestamp_us + 1,
            )

            self.assertEqual(handler(self._envelope()), "inserted")
            with patch(
                "kismet_eventbus_observation_handler.decode_kismet_new_device_envelope",
                return_value=conflict,
            ):
                self.assertEqual(handler(self._envelope()), "identity_conflict")

            with ObservationStore(path) as store:
                stored = store.list_observation_events()
                self.assertEqual(len(stored), 1)
                self.assertEqual(stored[0], baseline)

    def test_malformed_envelopes_are_rejected_before_store_open(self):
        malformed_envelopes = [
            {},
            {NEW_DEVICE: self._payload(), "EXTRA": 1},
            [],
            {NEW_DEVICE: []},
            {"OTHER": self._payload()},
            {NEW_DEVICE: {**self._payload(), "kismet.device.base.key": ""}},
        ]

        for index, envelope in enumerate(malformed_envelopes):
            with self.subTest(index=index):
                with tempfile.TemporaryDirectory() as tempdir:
                    path = self._db_path(tempdir)
                    calls = []
                    handler = KismetEventbusObservationHandler(
                        path,
                        hmac_key=self.KEY,
                        collection_session_id="session_alpha",
                        sensor_id="sensor_alpha",
                        ingest_timestamp_us_provider=lambda: calls.append("called") or 1,
                    )
                    with patch(
                        "kismet_eventbus_observation_handler.ObservationStore",
                        side_effect=AssertionError("store must not open"),
                    ):
                        self.assertEqual(handler(envelope), "malformed")
                    self.assertEqual(calls, ["called"])
                    self.assertFalse(path.exists())

    def test_invalid_timestamp_provider_results_raise_value_error(self):
        values = [True, -1, "1", None]
        for value in values:
            with self.subTest(value=value):
                with tempfile.TemporaryDirectory() as tempdir:
                    path = self._db_path(tempdir)

                    def provider(value=value):
                        return value

                    handler = KismetEventbusObservationHandler(
                        path,
                        hmac_key=self.KEY,
                        collection_session_id="session_alpha",
                        sensor_id="sensor_alpha",
                        ingest_timestamp_us_provider=provider,
                    )
                    with patch(
                        "kismet_eventbus_observation_handler.decode_kismet_new_device_envelope",
                        side_effect=AssertionError("decoder must not be called"),
                    ):
                        with self.assertRaises(ValueError) as ctx:
                            handler(self._envelope())
                    self.assertEqual(str(ctx.exception), "ingest_timestamp_us")
                    self.assertFalse(path.exists())

    def test_provider_exception_propagates_unchanged(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = self._db_path(tempdir)
            sentinel = RuntimeError("provider boom")

            def provider():
                raise sentinel

            handler = KismetEventbusObservationHandler(
                path,
                hmac_key=self.KEY,
                collection_session_id="session_alpha",
                sensor_id="sensor_alpha",
                ingest_timestamp_us_provider=provider,
            )
            with patch(
                "kismet_eventbus_observation_handler.decode_kismet_new_device_envelope",
                side_effect=AssertionError("decoder must not be called"),
            ):
                with self.assertRaises(RuntimeError) as ctx:
                    handler(self._envelope())
            self.assertIs(ctx.exception, sentinel)
            self.assertNotIn(self.KEY.decode("ascii", errors="ignore"), str(ctx.exception))
            self.assertFalse(path.exists())

    def test_construction_thread_differs_from_invocation_thread(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = self._db_path(tempdir)
            handler, _ = self._handler(path, [1_000_500])
            result = {}

            def worker():
                result["value"] = handler(self._envelope())

            thread = threading.Thread(target=worker)
            thread.start()
            thread.join()

            self.assertEqual(result["value"], "inserted")
            with ObservationStore(path) as store:
                self.assertEqual(len(store.list_observation_events()), 1)

    def test_sequential_worker_generation_simulation(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = self._db_path(tempdir)
            handler, _ = self._handler(path, [1_000_500, 2_000_500])
            results = []

            def run_once():
                results.append(handler(self._envelope()))

            first = threading.Thread(target=run_once)
            first.start()
            first.join()

            second = threading.Thread(target=run_once)
            second.start()
            second.join()

            self.assertEqual(results, ["inserted", "duplicate"])
            with ObservationStore(path) as store:
                stored = store.list_observation_events()
                self.assertEqual(len(stored), 1)
                self.assertEqual(stored[0].ingest_timestamp_us, 1_000_500)

    def test_store_failure_propagates_without_retry(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir)
            calls = []

            def provider():
                return 1_000_500

            handler = KismetEventbusObservationHandler(
                path,
                hmac_key=self.KEY,
                collection_session_id="session_alpha",
                sensor_id="sensor_alpha",
                ingest_timestamp_us_provider=provider,
            )

            def failing_store(*args, **kwargs):
                calls.append("called")
                raise sqlite3.OperationalError("unable to open database file")

            with patch(
                "kismet_eventbus_observation_handler.ObservationStore",
                side_effect=failing_store,
            ):
                with self.assertRaises(sqlite3.OperationalError):
                    handler(self._envelope())
            self.assertEqual(calls, ["called"])
            self.assertFalse((path / "observations.sqlite").exists())

    def test_secret_containment(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = self._db_path(tempdir)
            handler, _ = self._handler(path, [1_000_500, 2_000_500, 3_000_500])

            envelope = self._envelope()
            conflict_event = replace(
                decode_kismet_new_device_envelope(
                    envelope,
                    hmac_key=self.KEY,
                    collection_session_id="session_alpha",
                    sensor_id="sensor_alpha",
                    ingest_timestamp_us=2_000_500,
                ),
                source_timestamp_us=123,
            )

            outputs = io.StringIO()
            errors = io.StringIO()

            with contextlib.redirect_stdout(outputs), contextlib.redirect_stderr(errors):
                self.assertEqual(handler(envelope), "inserted")
                self.assertEqual(handler(envelope), "duplicate")
                with patch(
                    "kismet_eventbus_observation_handler.decode_kismet_new_device_envelope",
                    return_value=conflict_event,
                ):
                    self.assertEqual(handler(envelope), "identity_conflict")
                with patch(
                    "kismet_eventbus_observation_handler.ObservationStore",
                    side_effect=AssertionError("store must not open"),
                ):
                    self.assertEqual(
                        KismetEventbusObservationHandler(
                            path,
                            hmac_key=self.KEY,
                            collection_session_id="session_alpha",
                            sensor_id="sensor_alpha",
                            ingest_timestamp_us_provider=lambda: 1,
                        )(
                            {NEW_DEVICE: []}
                        ),
                        "malformed",
                    )
                with patch(
                    "kismet_eventbus_observation_handler.decode_kismet_new_device_envelope",
                    side_effect=AssertionError("decoder must not be called"),
                ):
                    with self.assertRaises(RuntimeError):
                        KismetEventbusObservationHandler(
                            path,
                            hmac_key=self.KEY,
                            collection_session_id="session_alpha",
                            sensor_id="sensor_alpha",
                            ingest_timestamp_us_provider=lambda: (_ for _ in ()).throw(
                                RuntimeError("provider boom")
                            ),
                        )(envelope)
                with patch(
                    "kismet_eventbus_observation_handler.decode_kismet_new_device_envelope",
                    side_effect=AssertionError("decoder must not be called"),
                ):
                    with self.assertRaises(ValueError):
                        KismetEventbusObservationHandler(
                            path,
                            hmac_key=self.KEY,
                            collection_session_id="session_alpha",
                            sensor_id="sensor_alpha",
                            ingest_timestamp_us_provider=lambda: "bad",
                        )(envelope)

            self.assertEqual(outputs.getvalue(), "")
            self.assertEqual(errors.getvalue(), "")
            self.assertNotIn(self.KEY.decode("ascii", errors="ignore"), repr(handler))

    def test_static_prohibitions(self):
        source_path = Path(__file__).resolve().parent.parent / "kismet_eventbus_observation_handler.py"
        tree = ast.parse(source_path.read_text())

        imported_modules = set()
        from_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_modules.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module is not None:
                    from_modules.add(node.module.split(".")[0])

        self.assertLessEqual(imported_modules | from_modules, {"collections", "pathlib", "kismet_eventbus_new_device_adapter", "observation_store"})

        call_nodes = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
        self.assertEqual(
            sum(
                1
                for node in call_nodes
                if isinstance(node.func, ast.Name) and node.func.id == "ObservationStore"
            ),
            1,
        )
        self.assertEqual(
            sum(
                1
                for node in call_nodes
                if isinstance(node.func, ast.Attribute)
                and node.func.attr == "insert_observation_event"
            ),
            1,
        )

        class_def = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "KismetEventbusObservationHandler"
        )
        call_method = next(
            node for node in class_def.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "__call__"
        )
        method_calls = [
            node for node in ast.walk(call_method)
            if isinstance(node, ast.Call)
        ]
        decode_lines = [
            node.lineno
            for node in method_calls
            if isinstance(node.func, ast.Name)
            and node.func.id == "decode_kismet_new_device_envelope"
        ]
        store_lines = [
            node.lineno
            for node in method_calls
            if isinstance(node.func, ast.Name)
            and node.func.id == "ObservationStore"
        ]
        self.assertEqual(len(decode_lines), 1)
        self.assertEqual(len(store_lines), 1)
        self.assertLess(decode_lines[0], store_lines[0])

        forbidden_names = {"print"}
        forbidden_bases = {
            "logging",
            "os",
            "time",
            "datetime",
            "threading",
            "requests",
            "websocket",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, forbidden_names)
                elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                    self.assertNotIn(node.func.value.id, forbidden_bases)

        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = []
                if isinstance(node, ast.Assign):
                    targets.extend(node.targets)
                    value = node.value
                else:
                    targets.append(node.target)
                    value = node.value
                if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "ObservationStore":
                    for target in targets:
                        self.assertFalse(
                            isinstance(target, ast.Attribute)
                            and isinstance(target.value, ast.Name)
                            and target.value.id == "self"
                        )

        forbidden_attr_names = {
            "getenv",
            "environ",
            "home",
            "cwd",
            "expanduser",
            "Thread",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                self.assertNotEqual(node.attr, "Thread")
                self.assertNotIn(node.attr, forbidden_attr_names - {"Thread"})


if __name__ == "__main__":
    unittest.main()
