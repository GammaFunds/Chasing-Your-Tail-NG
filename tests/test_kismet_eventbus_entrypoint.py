"""Deterministic tests for kismet_eventbus_entrypoint delegation.

No real network, environment, file, home-directory, credential discovery,
or I/O is used.  Only synthetic test credentials are supplied through the
deployment module's credential container.
"""

from __future__ import annotations

import ast
import builtins
import inspect
import os
import sys
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest.mock import Mock, patch

import kismet_eventbus_deployment as deployment_module
import kismet_eventbus_entrypoint as entrypoint_module
import kismet_eventbus_runtime
from kismet_eventbus_deployment import (
    KismetEventbusCredentialsV1,
    KismetEventbusDeploymentManifestV1,
)
from kismet_eventbus_entrypoint import (
    create_inactive_kismet_eventbus_runtime,
)

# ======================================================================
# Synthetic test data — never real credentials
# ======================================================================

_SYNTHETIC_AUTH = b"Basic c3ludGhldGljLWVudHJ5cG9pbnQ6dGVzdA=="
_SYNTHETIC_HMAC = b"entrypoint-test-hmac-key-32-bytes!!"
_SYNTHETIC_SESSION = "entrypoint_test_session"
_SYNTHETIC_SENSOR = "entrypoint_test_sensor"
_SYNTHETIC_PATH = "synthetic/entrypoint-observations.sqlite"


def _provider() -> int:
    return 1_000_000


def _make_manifest(**overrides: object) -> KismetEventbusDeploymentManifestV1:
    kwargs: dict[str, object] = {
        "base_url": "https://kismet.entrypoint.test",
        "topics": ("NEW_DEVICE",),
        "tls_mode": "verify_required",
        "connect_timeout_s": 10.0,
        "reconnect_delay_s": 5.0,
        "stop_join_timeout_s": 5.0,
        "db_path": _SYNTHETIC_PATH,
        "collection_session_id": _SYNTHETIC_SESSION,
        "sensor_id": _SYNTHETIC_SENSOR,
    }
    kwargs.update(overrides)
    return KismetEventbusDeploymentManifestV1(**kwargs)


def _make_credentials(**overrides: object) -> KismetEventbusCredentialsV1:
    kwargs: dict[str, object] = {
        "authorization_header_value": _SYNTHETIC_AUTH,
        "hmac_key": _SYNTHETIC_HMAC,
    }
    kwargs.update(overrides)
    return KismetEventbusCredentialsV1(**kwargs)


# ======================================================================
# 1. Public surface
# ======================================================================


class EntrypointSurfaceTests(unittest.TestCase):
    """Exact __all__, signature, and public surface."""

    def test_module_all_contains_exactly_one_name(self) -> None:
        self.assertEqual(
            entrypoint_module.__all__,
            ("create_inactive_kismet_eventbus_runtime",),
        )

    def test_exact_keyword_only_signature_and_annotations(self) -> None:
        sig = inspect.signature(
            create_inactive_kismet_eventbus_runtime,
            eval_str=True,
        )

        for param in sig.parameters.values():
            self.assertEqual(
                param.kind,
                inspect.Parameter.KEYWORD_ONLY,
                f"parameter {param.name} is not keyword-only",
            )

        expected_names = (
            "manifest",
            "credential_provider",
            "ingest_timestamp_us_provider",
        )

        self.assertEqual(
            tuple(sig.parameters.keys()),
            expected_names,
        )

        expected_annotations = {
            "manifest": KismetEventbusDeploymentManifestV1,
            "credential_provider": Callable[
                [], KismetEventbusCredentialsV1
            ],
            "ingest_timestamp_us_provider": Callable[[], int],
        }

        for name, expected_type in expected_annotations.items():
            with self.subTest(param=name):
                actual = sig.parameters[name].annotation
                self.assertEqual(actual, expected_type)

        self.assertEqual(
            sig.return_annotation,
            kismet_eventbus_runtime.KismetEventbusRuntime,
        )

    def test_no_public_class_defined_in_module(self) -> None:
        module_defined_public_classes = {
            name
            for name, obj in vars(entrypoint_module).items()
            if (
                not name.startswith("_")
                and isinstance(obj, type)
                and getattr(obj, "__module__", None)
                == entrypoint_module.__name__
            )
        }

        self.assertEqual(module_defined_public_classes, set())

    def test_no_other_public_function(self) -> None:
        module_defined_public_functions = {
            name
            for name, obj in vars(entrypoint_module).items()
            if (
                not name.startswith("_")
                and inspect.isfunction(obj)
                and getattr(obj, "__module__", None)
                == entrypoint_module.__name__
            )
        }

        self.assertEqual(
            module_defined_public_functions,
            {"create_inactive_kismet_eventbus_runtime"},
        )

    def test_no_main_guard_or_main_definition(self) -> None:
        source = Path(entrypoint_module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                if (
                    isinstance(node.test, ast.Compare)
                    and isinstance(node.test.left, ast.Name)
                    and node.test.left.id == "__name__"
                ):
                    self.fail("module defines __name__ guard")
            if isinstance(node, ast.FunctionDef):
                self.assertNotEqual(node.name, "main")


# ======================================================================
# 2. One-call delegation and identity forwarding
# ======================================================================


class EntrypointDelegationTests(unittest.TestCase):
    """Delegates exactly one call to the deployment module's provider
    factory, forwarding all arguments by identity."""

    def test_delegate_called_exactly_once_with_identity(self) -> None:
        manifest = _make_manifest()
        provider = Mock(return_value=_make_credentials())
        fake_runtime = object()

        with patch.object(
            deployment_module,
            "create_kismet_eventbus_runtime_from_credential_provider",
            return_value=fake_runtime,
        ) as mock_delegate:
            result = create_inactive_kismet_eventbus_runtime(
                manifest=manifest,
                credential_provider=provider,
                ingest_timestamp_us_provider=_provider,
            )

        self.assertIs(result, fake_runtime)
        mock_delegate.assert_called_once_with(
            manifest=manifest,
            credential_provider=provider,
            ingest_timestamp_us_provider=_provider,
        )

        _, kwargs = mock_delegate.call_args
        self.assertIs(kwargs["manifest"], manifest)
        self.assertIs(kwargs["credential_provider"], provider)
        self.assertIs(
            kwargs["ingest_timestamp_us_provider"],
            _provider,
        )

    def test_no_direct_provider_invocation_when_delegate_mocked(self) -> None:
        manifest = _make_manifest()
        provider = Mock()

        with patch.object(
            deployment_module,
            "create_kismet_eventbus_runtime_from_credential_provider",
            return_value=Mock(spec=["start", "stop", "recover"]),
        ):
            create_inactive_kismet_eventbus_runtime(
                manifest=manifest,
                credential_provider=provider,
                ingest_timestamp_us_provider=_provider,
            )

        provider.assert_not_called()

    def test_returned_object_identity(self) -> None:
        manifest = _make_manifest()
        provider = Mock(return_value=_make_credentials())
        fake_runtime = object()

        with patch.object(
            deployment_module,
            "create_kismet_eventbus_runtime_from_credential_provider",
            return_value=fake_runtime,
        ):
            result = create_inactive_kismet_eventbus_runtime(
                manifest=manifest,
                credential_provider=provider,
                ingest_timestamp_us_provider=_provider,
            )

        self.assertIs(result, fake_runtime)

    def test_exception_identity_propagates(self) -> None:
        manifest = _make_manifest()
        provider = Mock()
        sentinel = RuntimeError("delegate sentinel")

        with patch.object(
            deployment_module,
            "create_kismet_eventbus_runtime_from_credential_provider",
            side_effect=sentinel,
        ):
            with self.assertRaises(RuntimeError) as ctx:
                create_inactive_kismet_eventbus_runtime(
                    manifest=manifest,
                    credential_provider=provider,
                    ingest_timestamp_us_provider=_provider,
                )

        self.assertIs(ctx.exception, sentinel)

    def test_delegate_not_called_on_import(self) -> None:
        """Importing the module does NOT trigger the delegate."""
        import kismet_eventbus_entrypoint

        self.assertTrue(
            hasattr(
                kismet_eventbus_entrypoint,
                "create_inactive_kismet_eventbus_runtime",
            )
        )

    def test_timestamp_provider_not_called(self) -> None:
        manifest = _make_manifest()
        ts_provider = Mock()
        provider = Mock()

        with patch.object(
            deployment_module,
            "create_kismet_eventbus_runtime_from_credential_provider",
            return_value=Mock(spec=["start", "stop", "recover"]),
        ):
            create_inactive_kismet_eventbus_runtime(
                manifest=manifest,
                credential_provider=provider,
                ingest_timestamp_us_provider=ts_provider,
            )

        ts_provider.assert_not_called()
        provider.assert_not_called()


# ======================================================================
# 3. Existing provider validation behaviour
# ======================================================================


class EntrypointValidationDelegationTests(unittest.TestCase):
    """The entrypoint delegates to the deployment module's validation."""

    def test_invalid_manifest_type_rejected_provider_not_called(self) -> None:
        provider = Mock()

        with self.assertRaises(TypeError) as ctx:
            create_inactive_kismet_eventbus_runtime(
                manifest=object(),  # type: ignore[arg-type]
                credential_provider=provider,
                ingest_timestamp_us_provider=_provider,
            )

        self.assertEqual(str(ctx.exception), "manifest invalid")
        provider.assert_not_called()

    def test_non_callable_provider_rejected(self) -> None:
        manifest = _make_manifest()

        with self.assertRaises(TypeError) as ctx:
            create_inactive_kismet_eventbus_runtime(
                manifest=manifest,
                credential_provider=object(),  # type: ignore[arg-type]
                ingest_timestamp_us_provider=_provider,
            )

        self.assertEqual(str(ctx.exception), "credential_provider invalid")

    def test_invalid_credentials_rejected(self) -> None:
        manifest = _make_manifest()
        provider = Mock(return_value=object())

        with self.assertRaises(TypeError) as ctx:
            create_inactive_kismet_eventbus_runtime(
                manifest=manifest,
                credential_provider=provider,
                ingest_timestamp_us_provider=_provider,
            )

        self.assertEqual(str(ctx.exception), "credentials invalid")
        provider.assert_called_once_with()


# ======================================================================
# 4. Inactive construction — no lifecycle calls
# ======================================================================


class EntrypointInactiveConstructionTests(unittest.TestCase):
    """No start, stop, or recover called on the returned runtime."""

    def test_no_lifecycle_calls_on_returned_runtime(self) -> None:
        manifest = _make_manifest()
        provider = Mock(return_value=_make_credentials())
        runtime_double = Mock(spec=["start", "stop", "recover", "status"])

        with patch.object(
            deployment_module,
            "create_kismet_eventbus_runtime_from_credential_provider",
            return_value=runtime_double,
        ):
            result = create_inactive_kismet_eventbus_runtime(
                manifest=manifest,
                credential_provider=provider,
                ingest_timestamp_us_provider=_provider,
            )

        self.assertIs(result, runtime_double)
        runtime_double.start.assert_not_called()
        runtime_double.stop.assert_not_called()
        runtime_double.recover.assert_not_called()

    def test_stopped_runtime_status_with_zero_counts(self) -> None:
        manifest = _make_manifest()
        provider = Mock(return_value=_make_credentials())
        runtime_double = Mock(spec=["start", "stop", "recover", "status"])
        runtime_double.status = (
            kismet_eventbus_runtime.KismetEventbusRuntimeStatusV1(
                lifecycle="stopped",
                generation=0,
                start_attempt_count=0,
                stop_attempt_count=0,
            )
        )

        with patch.object(
            deployment_module,
            "create_kismet_eventbus_runtime_from_credential_provider",
            return_value=runtime_double,
        ):
            result = create_inactive_kismet_eventbus_runtime(
                manifest=manifest,
                credential_provider=provider,
                ingest_timestamp_us_provider=_provider,
            )

        self.assertEqual(result.status.lifecycle, "stopped")
        self.assertEqual(result.status.generation, 0)
        self.assertEqual(result.status.start_attempt_count, 0)
        self.assertEqual(result.status.stop_attempt_count, 0)


# ======================================================================
# 5. No database, socket, thread, or websocket
# ======================================================================


class EntrypointNoSideEffectTests(unittest.TestCase):
    """No SQLite, socket, thread start, or websocket import at module level."""

    def test_no_database_socket_or_thread_at_import(self) -> None:
        import io
        import sqlite3
        import socket
        import threading

        script = (
            "import io, sqlite3, socket, sys, threading\n"
            "def _guard(*a, **kw):\n"
            "    raise AssertionError('forbidden call')\n"
            "sqlite3.connect = _guard\n"
            "socket.socket = _guard\n"
            "socket.create_connection = _guard\n"
            "threading.Thread.start = _guard\n"
            "_saved_out = sys.stdout\n"
            "_saved_err = sys.stderr\n"
            "sys.stdout = io.StringIO()\n"
            "sys.stderr = io.StringIO()\n"
            "import kismet_eventbus_entrypoint\n"
            "_cap_out = sys.stdout.getvalue()\n"
            "_cap_err = sys.stderr.getvalue()\n"
            "sys.stdout = _saved_out\n"
            "sys.stderr = _saved_err\n"
            "_errs = []\n"
            "if _cap_out:\n"
            "    _errs.append('stdout: ' + repr(_cap_out))\n"
            "if _cap_err:\n"
            "    _errs.append('stderr: ' + repr(_cap_err))\n"
            "if _errs:\n"
            "    print('; '.join(_errs))\n"
            "    sys.exit(1)\n"
        )
        result = __import__("subprocess").run(
            [sys.executable, "-B", "-c", script],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent.parent,
        )
        if result.returncode != 0:
            self.fail(
                f"Import probe failed (exit={result.returncode}): "
                f"stdout={result.stdout!r} stderr={result.stderr!r}"
            )
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_no_stdout_or_stderr_on_normal_call(self) -> None:
        manifest = _make_manifest()
        provider = Mock(return_value=_make_credentials())

        import io
        saved_out = sys.stdout
        saved_err = sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        try:
            with patch.object(
                deployment_module,
                "create_kismet_eventbus_runtime_from_credential_provider",
                return_value=Mock(spec=["start", "stop", "recover"]),
            ):
                create_inactive_kismet_eventbus_runtime(
                    manifest=manifest,
                    credential_provider=provider,
                    ingest_timestamp_us_provider=_provider,
                )
            captured_out = sys.stdout.getvalue()
            captured_err = sys.stderr.getvalue()
        finally:
            sys.stdout = saved_out
            sys.stderr = saved_err

        self.assertEqual(captured_out, "")
        self.assertEqual(captured_err, "")


# ======================================================================
# 6. AST prohibition of forbidden imports and operations
# ======================================================================


class EntrypointASTProhibitionTests(unittest.TestCase):
    """AST-level prohibition of legacy credential, environment, filesystem,
    network, process, logging, threading, and wall-clock dependencies."""

    def _source_tree(self) -> ast.AST:
        source_path = Path(entrypoint_module.__file__)
        return ast.parse(
            source_path.read_text(encoding="utf-8"),
            filename=str(source_path),
        )

    def test_ast_no_forbidden_imports(self) -> None:
        forbidden_import_roots = {
            "secure_credentials",
            "migrate_credentials",
            "os",
            "netrc",
            "keyring",
            "keyczar",
            "dotenv",
            "socket",
            "subprocess",
            "logging",
            "threading",
            "time",
            "signal",
            "json",
            "sqlite3",
        }
        tree = self._source_tree()
        imported: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(
                    alias.name.split(".")[0] for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])

        found = imported & forbidden_import_roots
        self.assertEqual(found, set(), f"forbidden imports: {found}")

    def test_ast_no_websocket_import(self) -> None:
        tree = self._source_tree()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(
                        alias.name.split(".")[0],
                        "websocket",
                        "websocket must not be imported by the entrypoint module",
                    )
            elif isinstance(node, ast.ImportFrom) and node.module:
                self.assertNotEqual(
                    node.module.split(".")[0],
                    "websocket",
                    "websocket must not be imported by the entrypoint module",
                )

    def test_ast_no_forbidden_calls(self) -> None:
        tree = self._source_tree()

        forbidden_import_roots = {
            "dotenv",
            "glob",
            "httpx",
            "importlib",
            "keyring",
            "logging",
            "migrate_credentials",
            "netrc",
            "os",
            "pkgutil",
            "requests",
            "runpy",
            "secure_credentials",
            "signal",
            "socket",
            "subprocess",
            "threading",
            "time",
        }

        forbidden_calls = {
            "__import__",
            "builtins.__import__",
            "glob.glob",
            "glob.iglob",
            "importlib.import_module",
            "importlib.util.module_from_spec",
            "importlib.util.spec_from_file_location",
            "os.getcwd",
            "os.listdir",
            "os.scandir",
            "os.walk",
            "os.path.abspath",
            "os.path.realpath",
            "os.path.exists",
            "os.path.isfile",
            "os.path.isdir",
            "Path.cwd",
            "Path.resolve",
            "Path.absolute",
            "Path.expanduser",
            "Path.glob",
            "Path.rglob",
            "Path.iterdir",
            "Path.exists",
            "Path.is_file",
            "Path.is_dir",
            "Path.stat",
            "Path.lstat",
            "pathlib.Path.cwd",
            "pathlib.Path.resolve",
            "pathlib.Path.absolute",
            "pathlib.Path.expanduser",
            "pathlib.Path.glob",
            "pathlib.Path.rglob",
            "pathlib.Path.iterdir",
            "pathlib.Path.exists",
            "pathlib.Path.is_file",
            "pathlib.Path.is_dir",
            "pathlib.Path.stat",
            "pathlib.Path.lstat",
            "pkgutil.iter_modules",
            "pkgutil.walk_packages",
            "runpy.run_module",
            "runpy.run_path",
        }

        forbidden_terminal_calls = {
            "__import__",
            "absolute",
            "cwd",
            "exists",
            "expanduser",
            "getcwd",
            "glob",
            "iglob",
            "import_module",
            "is_dir",
            "is_file",
            "iter_modules",
            "iterdir",
            "listdir",
            "lstat",
            "module_from_spec",
            "realpath",
            "resolve",
            "rglob",
            "run_module",
            "run_path",
            "scandir",
            "spec_from_file_location",
            "stat",
            "walk",
            "walk_packages",
        }

        def node_name(node: ast.AST) -> str | None:
            if isinstance(node, ast.Name):
                return node.id

            if isinstance(node, ast.Call):
                return node_name(node.func)

            if isinstance(node, ast.Attribute):
                parent = node_name(node.value)

                if parent:
                    return f"{parent}.{node.attr}"

                return node.attr

            return None

        actual_import_roots: set[str] = set()
        actual_calls: set[str] = set()
        actual_terminal_calls: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    actual_import_roots.add(
                        alias.name.split(".", 1)[0]
                    )

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    actual_import_roots.add(
                        node.module.split(".", 1)[0]
                    )

            elif isinstance(node, ast.Call):
                name = node_name(node.func)

                if name:
                    actual_calls.add(name)
                    actual_terminal_calls.add(
                        name.rsplit(".", 1)[-1]
                    )

        self.assertEqual(
            actual_import_roots & forbidden_import_roots,
            set(),
        )

        self.assertEqual(
            actual_calls & forbidden_calls,
            set(),
        )

        self.assertEqual(
            actual_terminal_calls & forbidden_terminal_calls,
            set(),
        )

    def test_ast_no_authorization_or_hmac_access(self) -> None:
        """AST-level check that the module never accesses
        authorization_header_value or hmac_key."""
        tree = self._source_tree()

        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                self.assertNotEqual(
                    node.attr,
                    "authorization_header_value",
                    "module must not access authorization_header_value",
                )
                self.assertNotEqual(
                    node.attr,
                    "hmac_key",
                    "module must not access hmac_key",
                )

    def test_ast_no_credential_provider_direct_invocation(self) -> None:
        """AST-level check that the module never calls credential_provider
        directly — it always delegates."""
        tree = self._source_tree()

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    self.assertNotEqual(
                        node.func.id,
                        "credential_provider",
                        "module must not invoke credential_provider directly",
                    )

    def test_ast_allowed_imports_only(self) -> None:
        allowed_import_roots = {
            "__future__",
            "collections",
            "kismet_eventbus_deployment",
            "kismet_eventbus_runtime",
        }
        tree = self._source_tree()
        imported: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(
                    alias.name.split(".")[0] for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])

        unexpected = imported - allowed_import_roots
        self.assertEqual(
            unexpected, set(), f"unexpected imports: {unexpected}"
        )


# ======================================================================
# 7. Import side-effect prohibition
# ======================================================================


class EntrypointImportSideEffectTests(unittest.TestCase):
    """Module-level import triggers no I/O, env, or network access."""

    def test_import_has_no_forbidden_side_effects(self) -> None:
        import glob
        import importlib
        import importlib.util
        import logging
        import os
        import pkgutil
        import runpy
        import socket
        import subprocess
        import threading
        import time
        import urllib.request
        from contextlib import ExitStack
        from pathlib import Path
        from unittest.mock import patch

        module_path = Path(entrypoint_module.__file__)
        module_source = module_path.read_text(
            encoding="utf-8",
        )
        module_code = compile(
            module_source,
            str(module_path),
            "exec",
        )

        module_name = "_kismet_eventbus_entrypoint_import_probe"
        fresh_globals = {
            "__name__": module_name,
            "__file__": str(module_path),
            "__package__": "",
            "__builtins__": builtins.__dict__,
        }

        forbidden = AssertionError(
            "forbidden import-time side effect"
        )

        real_import = builtins.__import__

        allowed_imports = {
            "__future__",
            "collections.abc",
            "kismet_eventbus_deployment",
            "kismet_eventbus_runtime",
        }

        def guarded_import(
            name: str,
            globals: object = None,
            locals: object = None,
            fromlist: object = (),
            level: int = 0,
        ) -> object:
            if level != 0 or name not in allowed_imports:
                raise forbidden

            return real_import(
                name,
                globals,
                locals,
                fromlist,
                level,
            )

        patch_targets = (
            (builtins, "open"),
            (builtins, "print"),
            (importlib, "import_module"),
            (
                importlib.util,
                "spec_from_file_location",
            ),
            (
                importlib.util,
                "module_from_spec",
            ),
            (glob, "glob"),
            (glob, "iglob"),
            (os, "getenv"),
            (os, "getcwd"),
            (os, "listdir"),
            (os, "scandir"),
            (os, "walk"),
            (os.path, "abspath"),
            (os.path, "realpath"),
            (os.path, "exists"),
            (os.path, "isfile"),
            (os.path, "isdir"),
            (pkgutil, "iter_modules"),
            (pkgutil, "walk_packages"),
            (runpy, "run_module"),
            (runpy, "run_path"),
            (Path, "home"),
            (Path, "cwd"),
            (Path, "resolve"),
            (Path, "absolute"),
            (Path, "expanduser"),
            (Path, "glob"),
            (Path, "rglob"),
            (Path, "iterdir"),
            (Path, "exists"),
            (Path, "is_file"),
            (Path, "is_dir"),
            (Path, "stat"),
            (Path, "lstat"),
            (Path, "open"),
            (Path, "read_text"),
            (Path, "read_bytes"),
            (Path, "write_text"),
            (Path, "write_bytes"),
            (logging, "basicConfig"),
            (logging, "getLogger"),
            (socket, "create_connection"),
            (socket, "socket"),
            (subprocess, "run"),
            (subprocess, "Popen"),
            (threading, "Thread"),
            (time, "sleep"),
            (time, "time"),
            (time, "monotonic"),
            (urllib.request, "urlopen"),
        )

        # Register the probe module so Python 3.14+ dataclass internals
        # can resolve forward references via sys.modules.
        sys.modules[module_name] = type(sys)(module_name)

        try:
            with ExitStack() as stack:
                for owner, attribute_name in patch_targets:
                    stack.enter_context(
                        patch.object(
                            owner,
                            attribute_name,
                            side_effect=forbidden,
                        )
                    )

                stack.enter_context(
                    patch.object(
                        builtins,
                        "__import__",
                        side_effect=guarded_import,
                    )
                )

                sys.modules[module_name].__dict__.update(
                    fresh_globals
                )

                exec(
                    module_code,
                    fresh_globals,
                    fresh_globals,
                )
        finally:
            sys.modules.pop(module_name, None)

        self.assertIn(
            "create_inactive_kismet_eventbus_runtime",
            fresh_globals,
        )
