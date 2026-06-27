"""Deterministic tests for kismet_eventbus_deployment assembly.

No real network, environment, file, home-directory, credential discovery,
or I/O is used.  Only synthetic test credentials are supplied.
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
from unittest.mock import ANY, Mock, call, patch

import kismet_eventbus_deployment as deployment_module
import kismet_eventbus_runtime
import kismet_eventbus_runtime_config
from kismet_eventbus_deployment import (
    KismetEventbusDeploymentManifestV1,
    create_kismet_eventbus_runtime,
    create_kismet_eventbus_runtime_from_manifest,
)

# ======================================================================
# Synthetic secrets for testing — never real credentials
# ======================================================================

_SYNTHETIC_AUTH = b"Basic c3ludGhldGljLWRlcGxveW1lbnQ6dGVzdA=="
_SYNTHETIC_HMAC = b"deployment-test-hmac-key-32-bytes!!"
_SYNTHETIC_SESSION = "deployment_test_session"
_SYNTHETIC_SENSOR = "deployment_test_sensor"
_SYNTHETIC_PATH = "synthetic/deployment-observations.sqlite"


def _provider() -> int:
    return 1_000_000


def _valid_manifest_kwargs(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "base_url": "https://test.example",
        "topics": ("NEW_DEVICE",),
        "tls_mode": "verify_required",
        "connect_timeout_s": 10.0,
        "reconnect_delay_s": 5.0,
        "stop_join_timeout_s": 5.0,
        "db_path": "/tmp/test.sqlite",
        "collection_session_id": "test_session",
        "sensor_id": "test_sensor",
    }
    kwargs.update(overrides)
    return kwargs


def _valid_kwargs(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "base_url": "https://kismet.deployment.test",
        "topics": ("NEW_DEVICE",),
        "authorization_header_value": _SYNTHETIC_AUTH,
        "tls_mode": "verify_required",
        "connect_timeout_s": 10.0,
        "reconnect_delay_s": 5.0,
        "stop_join_timeout_s": 5.0,
        "db_path": _SYNTHETIC_PATH,
        "hmac_key": _SYNTHETIC_HMAC,
        "collection_session_id": _SYNTHETIC_SESSION,
        "sensor_id": _SYNTHETIC_SENSOR,
        "ingest_timestamp_us_provider": _provider,
    }
    kwargs.update(overrides)
    return kwargs


# ======================================================================
# 1. Public surface
# ======================================================================


class DeploymentSurfaceTests(unittest.TestCase):
    """Exact __all__, signature, and public surface."""

    def test_module_all_contains_exactly_three_names(self) -> None:
        self.assertEqual(
            deployment_module.__all__,
            (
                "KismetEventbusDeploymentManifestV1",
                "create_kismet_eventbus_runtime",
                "create_kismet_eventbus_runtime_from_manifest",
            ),
        )

    def test_exact_keyword_only_signature_and_annotations(self) -> None:
        sig = inspect.signature(
            create_kismet_eventbus_runtime,
            eval_str=True,
        )

        for param in sig.parameters.values():
            self.assertEqual(
                param.kind,
                inspect.Parameter.KEYWORD_ONLY,
                f"parameter {param.name} is not keyword-only",
            )

        expected_names = (
            "base_url",
            "topics",
            "authorization_header_value",
            "tls_mode",
            "connect_timeout_s",
            "reconnect_delay_s",
            "stop_join_timeout_s",
            "db_path",
            "hmac_key",
            "collection_session_id",
            "sensor_id",
            "ingest_timestamp_us_provider",
        )

        self.assertEqual(
            tuple(sig.parameters.keys()),
            expected_names,
        )

        expected_annotations = {
            "base_url": str,
            "topics": tuple[str, ...],
            "authorization_header_value": bytes,
            "tls_mode": str,
            "connect_timeout_s": float,
            "reconnect_delay_s": float,
            "stop_join_timeout_s": float,
            "db_path": str | Path,
            "hmac_key": bytes,
            "collection_session_id": str,
            "sensor_id": str,
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

    def test_no_public_class_in_module(self) -> None:
        module_defined_public_functions = {
            name
            for name, obj in vars(deployment_module).items()
            if (
                not name.startswith("_")
                and inspect.isfunction(obj)
                and getattr(obj, "__module__", None)
                == deployment_module.__name__
            )
        }

        self.assertEqual(
            module_defined_public_functions,
            {
                "create_kismet_eventbus_runtime",
                "create_kismet_eventbus_runtime_from_manifest",
            },
        )

        module_defined_public_classes = {
            name
            for name, obj in vars(deployment_module).items()
            if (
                not name.startswith("_")
                and isinstance(obj, type)
                and getattr(obj, "__module__", None)
                == deployment_module.__name__
            )
        }

        self.assertEqual(
            module_defined_public_classes,
            {"KismetEventbusDeploymentManifestV1"},
        )


# ======================================================================
# 2. Config factory forwarding
# ======================================================================


class DeploymentConfigFactoryForwardingTests(unittest.TestCase):
    """Config factory call count and keyword forwarding."""

    def test_config_factory_called_once_with_exact_kwargs(self) -> None:
        fake_config = object()

        with patch.object(
            kismet_eventbus_runtime_config,
            "create_kismet_eventbus_transport_config",
            return_value=fake_config,
        ) as mock_factory, patch.object(
            kismet_eventbus_runtime,
            "KismetEventbusRuntime",
        ) as mock_runtime:
            create_kismet_eventbus_runtime(**_valid_kwargs())

        mock_factory.assert_called_once_with(
            base_url="https://kismet.deployment.test",
            topics=("NEW_DEVICE",),
            authorization_header_value=_SYNTHETIC_AUTH,
            tls_mode="verify_required",
            connect_timeout_s=10.0,
            reconnect_delay_s=5.0,
            stop_join_timeout_s=5.0,
        )

        # Verify runtime was constructed
        mock_runtime.assert_called_once()

    def test_config_failure_propagates_and_runtime_not_constructed(self) -> None:
        config_error = ValueError("invalid config sentinel")

        with patch.object(
            kismet_eventbus_runtime_config,
            "create_kismet_eventbus_transport_config",
            side_effect=config_error,
        ) as mock_factory, patch.object(
            kismet_eventbus_runtime,
            "KismetEventbusRuntime",
        ) as mock_runtime:
            with self.assertRaises(ValueError) as ctx:
                create_kismet_eventbus_runtime(**_valid_kwargs())

        self.assertIs(ctx.exception, config_error)
        mock_factory.assert_called_once()
        mock_runtime.assert_not_called()


# ======================================================================
# 3. Runtime constructor forwarding
# ======================================================================


class DeploymentRuntimeConstructorForwardingTests(unittest.TestCase):
    """Runtime-constructor call count and argument forwarding."""

    def setUp(self) -> None:
        self.fake_config = object()
        self.config_patcher = patch.object(
            kismet_eventbus_runtime_config,
            "create_kismet_eventbus_transport_config",
            return_value=self.fake_config,
        )
        self.mock_config_factory = self.config_patcher.start()

    def tearDown(self) -> None:
        self.config_patcher.stop()

    def test_runtime_constructor_called_once_with_exact_args(self) -> None:
        with patch.object(
            kismet_eventbus_runtime,
            "KismetEventbusRuntime",
        ) as mock_runtime:
            runtime = create_kismet_eventbus_runtime(**_valid_kwargs())

        mock_runtime.assert_called_once_with(
            self.fake_config,
            _SYNTHETIC_PATH,
            hmac_key=_SYNTHETIC_HMAC,
            collection_session_id=_SYNTHETIC_SESSION,
            sensor_id=_SYNTHETIC_SENSOR,
            ingest_timestamp_us_provider=_provider,
        )

    def test_config_object_forwarded_by_identity(self) -> None:
        with patch.object(
            kismet_eventbus_runtime,
            "KismetEventbusRuntime",
        ) as mock_runtime:
            create_kismet_eventbus_runtime(**_valid_kwargs())

        args, _ = mock_runtime.call_args
        self.assertIs(args[0], self.fake_config)

    def test_returned_runtime_preserved_by_identity(self) -> None:
        fake_runtime = object()

        with patch.object(
            kismet_eventbus_runtime,
            "KismetEventbusRuntime",
            return_value=fake_runtime,
        ) as mock_runtime:
            result = create_kismet_eventbus_runtime(**_valid_kwargs())

        self.assertIs(result, fake_runtime)

    def test_authorization_bytes_forwarded_by_identity(self) -> None:
        specific_auth = (
            b"Basic c3ludGhldGljLWlkZW50aXR5LXRlc3Q6eA=="
        )

        with patch.object(
            kismet_eventbus_runtime,
            "KismetEventbusRuntime",
        ) as mock_runtime:
            create_kismet_eventbus_runtime(
                **_valid_kwargs(
                    authorization_header_value=specific_auth,
                )
            )

        self.assertEqual(mock_runtime.call_count, 1)

        args, kwargs = self.mock_config_factory.call_args

        self.assertEqual(args, ())
        self.assertIs(
            kwargs["authorization_header_value"],
            specific_auth,
        )

    def test_hmac_bytes_forwarded_by_identity(self) -> None:
        specific_hmac = b"exact-hmac-identity-bytes-test-!!"
        fake_runtime = object()

        with patch.object(
            kismet_eventbus_runtime,
            "KismetEventbusRuntime",
            return_value=fake_runtime,
        ) as mock_runtime:
            create_kismet_eventbus_runtime(
                **_valid_kwargs(hmac_key=specific_hmac)
            )

        _, kwargs = mock_runtime.call_args
        self.assertIs(kwargs["hmac_key"], specific_hmac)

    def test_runtime_constructor_failure_propagates(self) -> None:
        runtime_error = TypeError("runtime constructor sentinel")

        with patch.object(
            kismet_eventbus_runtime,
            "KismetEventbusRuntime",
            side_effect=runtime_error,
        ):
            with self.assertRaises(TypeError) as ctx:
                create_kismet_eventbus_runtime(**_valid_kwargs())

        self.assertIs(ctx.exception, runtime_error)


# ======================================================================
# 4. Inactive construction
# ======================================================================


class DeploymentInactiveConstructionTests(unittest.TestCase):
    """No start, no stop, runtime remains inactive."""

    def test_no_start_or_stop_called(self) -> None:
        fake_config = object()
        mock_runtime = Mock(spec=["start", "stop", "status"])

        with patch.object(
            kismet_eventbus_runtime_config,
            "create_kismet_eventbus_transport_config",
            return_value=fake_config,
        ), patch.object(
            kismet_eventbus_runtime,
            "KismetEventbusRuntime",
            return_value=mock_runtime,
        ):
            result = create_kismet_eventbus_runtime(**_valid_kwargs())

        result.start.assert_not_called()  # type: ignore[attr-defined]
        result.stop.assert_not_called()  # type: ignore[attr-defined]

    def test_constructor_wiring_remains_inactive(self) -> None:
        fake_config = object()
        runtime_double = Mock(
            spec=[
                "start",
                "stop",
                "status",
            ]
        )
        kwargs = _valid_kwargs()

        with patch.object(
            kismet_eventbus_runtime_config,
            "create_kismet_eventbus_transport_config",
            return_value=fake_config,
        ) as mock_config_factory, patch.object(
            kismet_eventbus_runtime,
            "KismetEventbusRuntime",
            return_value=runtime_double,
        ) as mock_runtime_constructor:
            runtime = create_kismet_eventbus_runtime(
                **kwargs
            )

        mock_config_factory.assert_called_once()

        mock_runtime_constructor.assert_called_once_with(
            fake_config,
            kwargs["db_path"],
            hmac_key=kwargs["hmac_key"],
            collection_session_id=(
                kwargs["collection_session_id"]
            ),
            sensor_id=kwargs["sensor_id"],
            ingest_timestamp_us_provider=(
                kwargs["ingest_timestamp_us_provider"]
            ),
        )

        self.assertIs(
            runtime,
            runtime_double,
        )
        runtime_double.start.assert_not_called()
        runtime_double.stop.assert_not_called()


# ======================================================================
# 5. AST prohibition of forbidden imports and calls
# ======================================================================


class DeploymentASTProhibitionTests(unittest.TestCase):
    """AST-level prohibition of legacy credential, environment, filesystem,
    network, process, logging, threading, and wall-clock dependencies."""

    def _source_tree(self) -> ast.AST:
        source_path = Path(deployment_module.__file__)

        return ast.parse(
            source_path.read_text(encoding="utf-8"),
            filename=str(source_path),
        )

    def test_ast_no_forbidden_legacy_imports(self) -> None:
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

    def test_ast_no_websocket_import(self) -> None:
        tree = self._source_tree()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(
                        alias.name.split(".")[0],
                        "websocket",
                        "websocket must not be imported by the deployment module",
                    )
            elif isinstance(node, ast.ImportFrom) and node.module:
                self.assertNotEqual(
                    node.module.split(".")[0],
                    "websocket",
                    "websocket must not be imported by the deployment module",
                )

    def test_ast_imports_only_annotations_callable_path_and_contracts(self) -> None:
        allowed_import_roots = {
            "__future__",
            "collections",
            "dataclasses",
            "pathlib",
            "kismet_eventbus_runtime",
            "kismet_eventbus_runtime_config",
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
# 6. Import side-effect prohibition
# ======================================================================


class DeploymentImportSideEffectTests(unittest.TestCase):
    """Module-level import triggers no I/O, env, or network access."""

    def test_import_has_no_forbidden_side_effects(self) -> None:
        import builtins
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

        module_path = Path(deployment_module.__file__)
        module_source = module_path.read_text(
            encoding="utf-8",
        )
        module_code = compile(
            module_source,
            str(module_path),
            "exec",
        )

        module_name = "_kismet_eventbus_deployment_import_probe"
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
            "dataclasses",
            "pathlib",
            "kismet_eventbus_runtime",
            "kismet_eventbus_runtime_config",
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
            "create_kismet_eventbus_runtime",
            fresh_globals,
        )


# ======================================================================
# 7. Do not duplicate validation already owned by accepted contracts
# ======================================================================


class DeploymentNoRedundantValidationTests(unittest.TestCase):
    """The deployment function does not re-validate values already checked
    by the config factory or runtime constructor."""

    def test_invalid_base_url_reaches_config_factory(self) -> None:
        with patch.object(
            kismet_eventbus_runtime_config,
            "create_kismet_eventbus_transport_config",
            side_effect=ValueError("bad url"),
        ) as mock_factory:
            with self.assertRaises(ValueError):
                create_kismet_eventbus_runtime(
                    **_valid_kwargs(base_url="not-a-valid-url")
                )
        mock_factory.assert_called_once()

    def test_invalid_topics_reaches_config_factory(self) -> None:
        with patch.object(
            kismet_eventbus_runtime_config,
            "create_kismet_eventbus_transport_config",
            side_effect=ValueError("bad topics"),
        ) as mock_factory:
            with self.assertRaises(ValueError):
                create_kismet_eventbus_runtime(
                    **_valid_kwargs(topics=())
                )
        mock_factory.assert_called_once()


# ======================================================================
# 8. Manifest structure — frozen, slotted, fields, no secrets
# ======================================================================


class ManifestStructureTests(unittest.TestCase):
    """KismetEventbusDeploymentManifestV1 structural contract."""

    def _valid_kwargs(self, **overrides: object) -> dict[str, object]:
        kwargs: dict[str, object] = {
            "base_url": "https://test.example",
            "topics": ("NEW_DEVICE",),
            "tls_mode": "verify_required",
            "connect_timeout_s": 10.0,
            "reconnect_delay_s": 5.0,
            "stop_join_timeout_s": 5.0,
            "db_path": "/tmp/test.sqlite",
            "collection_session_id": "test_session",
            "sensor_id": "test_sensor",
        }
        kwargs.update(overrides)
        return kwargs

    def test_manifest_is_frozen_dataclass(self) -> None:
        obj = KismetEventbusDeploymentManifestV1(
            **_valid_manifest_kwargs(),
        )
        with self.assertRaises(AttributeError):
            obj.base_url = "https://other.example"

    def test_manifest_is_slotted(self) -> None:
        obj = KismetEventbusDeploymentManifestV1(
            **_valid_manifest_kwargs(),
        )
        with self.assertRaises(AttributeError):
            obj.__dict__

    def test_exact_ordered_field_tuple(self) -> None:
        import dataclasses
        expected = (
            "base_url",
            "topics",
            "tls_mode",
            "connect_timeout_s",
            "reconnect_delay_s",
            "stop_join_timeout_s",
            "db_path",
            "collection_session_id",
            "sensor_id",
        )
        actual = tuple(
            f.name for f in dataclasses.fields(KismetEventbusDeploymentManifestV1)
        )
        self.assertEqual(actual, expected)

    def test_manifest_has_no_authorization_header_value_field(self) -> None:
        import dataclasses
        names = {f.name for f in dataclasses.fields(KismetEventbusDeploymentManifestV1)}
        self.assertNotIn("authorization_header_value", names)

    def test_manifest_has_no_hmac_key_field(self) -> None:
        import dataclasses
        names = {f.name for f in dataclasses.fields(KismetEventbusDeploymentManifestV1)}
        self.assertNotIn("hmac_key", names)

    def test_manifest_topics_list_rejected(self) -> None:
        with self.assertRaises(TypeError):
            KismetEventbusDeploymentManifestV1(
                **_valid_manifest_kwargs(topics=["NEW_DEVICE"]),
            )

    def test_manifest_topics_tuple_non_str_rejected(self) -> None:
        with self.assertRaises(TypeError):
            KismetEventbusDeploymentManifestV1(
                **_valid_manifest_kwargs(topics=(42,)),
            )

    def test_manifest_wrong_type_base_url_rejected(self) -> None:
        with self.assertRaises(TypeError):
            KismetEventbusDeploymentManifestV1(
                **_valid_manifest_kwargs(base_url=42),
            )

    def test_manifest_wrong_type_tls_mode_rejected(self) -> None:
        with self.assertRaises(TypeError):
            KismetEventbusDeploymentManifestV1(
                **_valid_manifest_kwargs(tls_mode=42),
            )

    def test_manifest_wrong_type_connect_timeout_s_rejected(self) -> None:
        with self.assertRaises(TypeError):
            KismetEventbusDeploymentManifestV1(
                **_valid_manifest_kwargs(connect_timeout_s="10"),
            )

    def test_manifest_wrong_type_reconnect_delay_s_rejected(self) -> None:
        with self.assertRaises(TypeError):
            KismetEventbusDeploymentManifestV1(
                **_valid_manifest_kwargs(reconnect_delay_s="5"),
            )

    def test_manifest_wrong_type_stop_join_timeout_s_rejected(self) -> None:
        with self.assertRaises(TypeError):
            KismetEventbusDeploymentManifestV1(
                **_valid_manifest_kwargs(stop_join_timeout_s="5"),
            )

    def test_manifest_wrong_type_db_path_rejected(self) -> None:
        with self.assertRaises(TypeError):
            KismetEventbusDeploymentManifestV1(
                **_valid_manifest_kwargs(db_path=42),
            )

    def test_manifest_wrong_type_collection_session_id_rejected(self) -> None:
        with self.assertRaises(TypeError):
            KismetEventbusDeploymentManifestV1(
                **_valid_manifest_kwargs(collection_session_id=42),
            )

    def test_manifest_wrong_type_sensor_id_rejected(self) -> None:
        with self.assertRaises(TypeError):
            KismetEventbusDeploymentManifestV1(
                **_valid_manifest_kwargs(sensor_id=42),
            )

    def test_manifest_accepts_pathlib_db_path(self) -> None:
        obj = KismetEventbusDeploymentManifestV1(
            **_valid_manifest_kwargs(db_path=Path("/tmp/test.sqlite")),
        )
        self.assertIsInstance(obj.db_path, Path)

    def test_manifest_equality_is_value_based(self) -> None:
        kwargs = dict(
            base_url="https://test.example",
            topics=("NEW_DEVICE",),
            tls_mode="verify_required",
            connect_timeout_s=10.0,
            reconnect_delay_s=5.0,
            stop_join_timeout_s=5.0,
            db_path="/tmp/test.sqlite",
            collection_session_id="test_session",
            sensor_id="test_sensor",
        )
        a = KismetEventbusDeploymentManifestV1(**kwargs)
        b = KismetEventbusDeploymentManifestV1(**kwargs)
        self.assertEqual(a, b)
        self.assertEqual(hash(a), hash(b))

    def test_manifest_inequality_on_field_change(self) -> None:
        base = dict(
            base_url="https://test.example",
            topics=("NEW_DEVICE",),
            tls_mode="verify_required",
            connect_timeout_s=10.0,
            reconnect_delay_s=5.0,
            stop_join_timeout_s=5.0,
            db_path="/tmp/test.sqlite",
            collection_session_id="test_session",
            sensor_id="test_sensor",
        )
        a = KismetEventbusDeploymentManifestV1(**base)
        modified = dict(base, base_url="https://other.example")
        b = KismetEventbusDeploymentManifestV1(**modified)
        self.assertNotEqual(a, b)

    def test_manifest_mutation_fails(self) -> None:
        obj = KismetEventbusDeploymentManifestV1(
            **_valid_manifest_kwargs(),
        )
        with self.assertRaises(AttributeError):
            obj.base_url = "https://other.example"  # type: ignore[misc]


# ======================================================================
# 9. Manifest assembly — delegation, forwarding, identity, exceptions
# ======================================================================


class ManifestAssemblyTests(unittest.TestCase):
    """create_kismet_eventbus_runtime_from_manifest contract."""

    def _make_manifest(self, **overrides: object) -> KismetEventbusDeploymentManifestV1:
        kwargs = dict(
            base_url="https://kismet.deployment.test",
            topics=("NEW_DEVICE",),
            tls_mode="verify_required",
            connect_timeout_s=10.0,
            reconnect_delay_s=5.0,
            stop_join_timeout_s=5.0,
            db_path=_SYNTHETIC_PATH,
            collection_session_id=_SYNTHETIC_SESSION,
            sensor_id=_SYNTHETIC_SENSOR,
        )
        kwargs.update(overrides)
        return KismetEventbusDeploymentManifestV1(**kwargs)

    def test_assembly_delegates_exactly_once_to_existing_factory(self) -> None:
        manifest = self._make_manifest()

        with patch.object(
            deployment_module,
            "create_kismet_eventbus_runtime",
            return_value=Mock(spec=["start", "stop"]),
        ) as mock_factory:
            create_kismet_eventbus_runtime_from_manifest(
                manifest=manifest,
                authorization_header_value=_SYNTHETIC_AUTH,
                hmac_key=_SYNTHETIC_HMAC,
                ingest_timestamp_us_provider=_provider,
            )

        mock_factory.assert_called_once()

    def test_every_manifest_field_forwarded_exactly(self) -> None:
        manifest = self._make_manifest()

        with patch.object(
            deployment_module,
            "create_kismet_eventbus_runtime",
            return_value=Mock(spec=["start", "stop"]),
        ) as mock_factory:
            create_kismet_eventbus_runtime_from_manifest(
                manifest=manifest,
                authorization_header_value=_SYNTHETIC_AUTH,
                hmac_key=_SYNTHETIC_HMAC,
                ingest_timestamp_us_provider=_provider,
            )

        _, kwargs = mock_factory.call_args
        self.assertEqual(kwargs["base_url"], "https://kismet.deployment.test")
        self.assertEqual(kwargs["topics"], ("NEW_DEVICE",))
        self.assertEqual(kwargs["tls_mode"], "verify_required")
        self.assertEqual(kwargs["connect_timeout_s"], 10.0)
        self.assertEqual(kwargs["reconnect_delay_s"], 5.0)
        self.assertEqual(kwargs["stop_join_timeout_s"], 5.0)
        self.assertEqual(kwargs["db_path"], _SYNTHETIC_PATH)
        self.assertEqual(kwargs["collection_session_id"], _SYNTHETIC_SESSION)
        self.assertEqual(kwargs["sensor_id"], _SYNTHETIC_SENSOR)

    def test_authorization_header_value_identity_preserved(self) -> None:
        manifest = self._make_manifest()
        specific_auth = b"Basic aWRlbnRpdHktYXV0aC10ZXN0Og=="

        with patch.object(
            deployment_module,
            "create_kismet_eventbus_runtime",
            return_value=Mock(spec=["start", "stop"]),
        ) as mock_factory:
            create_kismet_eventbus_runtime_from_manifest(
                manifest=manifest,
                authorization_header_value=specific_auth,
                hmac_key=_SYNTHETIC_HMAC,
                ingest_timestamp_us_provider=_provider,
            )

        _, kwargs = mock_factory.call_args
        self.assertIs(kwargs["authorization_header_value"], specific_auth)

    def test_hmac_key_identity_preserved(self) -> None:
        manifest = self._make_manifest()
        specific_hmac = b"hmac-identity-preserved-test-0000"

        with patch.object(
            deployment_module,
            "create_kismet_eventbus_runtime",
            return_value=Mock(spec=["start", "stop"]),
        ) as mock_factory:
            create_kismet_eventbus_runtime_from_manifest(
                manifest=manifest,
                authorization_header_value=_SYNTHETIC_AUTH,
                hmac_key=specific_hmac,
                ingest_timestamp_us_provider=_provider,
            )

        _, kwargs = mock_factory.call_args
        self.assertIs(kwargs["hmac_key"], specific_hmac)

    def test_ingest_timestamp_us_provider_identity_preserved(self) -> None:
        manifest = self._make_manifest()

        def custom_provider() -> int:
            return 999_999

        with patch.object(
            deployment_module,
            "create_kismet_eventbus_runtime",
            return_value=Mock(spec=["start", "stop"]),
        ) as mock_factory:
            create_kismet_eventbus_runtime_from_manifest(
                manifest=manifest,
                authorization_header_value=_SYNTHETIC_AUTH,
                hmac_key=_SYNTHETIC_HMAC,
                ingest_timestamp_us_provider=custom_provider,
            )

        _, kwargs = mock_factory.call_args
        self.assertIs(kwargs["ingest_timestamp_us_provider"], custom_provider)

    def test_exact_runtime_object_returned(self) -> None:
        manifest = self._make_manifest()
        fake_runtime = object()

        with patch.object(
            deployment_module,
            "create_kismet_eventbus_runtime",
            return_value=fake_runtime,
        ) as mock_factory:
            result = create_kismet_eventbus_runtime_from_manifest(
                manifest=manifest,
                authorization_header_value=_SYNTHETIC_AUTH,
                hmac_key=_SYNTHETIC_HMAC,
                ingest_timestamp_us_provider=_provider,
            )

        self.assertIs(result, fake_runtime)

    def test_existing_factory_exceptions_propagate_unchanged(self) -> None:
        manifest = self._make_manifest()
        sentinel = ValueError("sentinel propagation")

        with patch.object(
            deployment_module,
            "create_kismet_eventbus_runtime",
            side_effect=sentinel,
        ):
            with self.assertRaises(ValueError) as ctx:
                create_kismet_eventbus_runtime_from_manifest(
                    manifest=manifest,
                    authorization_header_value=_SYNTHETIC_AUTH,
                    hmac_key=_SYNTHETIC_HMAC,
                    ingest_timestamp_us_provider=_provider,
                )

        self.assertIs(ctx.exception, sentinel)

    def test_manifest_assembly_signature_exact(self) -> None:
        sig = inspect.signature(
            create_kismet_eventbus_runtime_from_manifest,
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
            "authorization_header_value",
            "hmac_key",
            "ingest_timestamp_us_provider",
        )
        self.assertEqual(
            tuple(sig.parameters.keys()),
            expected_names,
        )

        expected_annotations = {
            "manifest": KismetEventbusDeploymentManifestV1,
            "authorization_header_value": bytes,
            "hmac_key": bytes,
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

    def test_non_manifest_rejected_before_delegation(self) -> None:
        with patch.object(
            deployment_module,
            "create_kismet_eventbus_runtime",
        ) as mock_factory:
            with self.assertRaises(TypeError) as ctx:
                create_kismet_eventbus_runtime_from_manifest(
                    manifest={"base_url": "https://evil.example"},  # type: ignore[arg-type]
                    authorization_header_value=_SYNTHETIC_AUTH,
                    hmac_key=_SYNTHETIC_HMAC,
                    ingest_timestamp_us_provider=_provider,
                )

        self.assertEqual(str(ctx.exception), "manifest invalid")
        mock_factory.assert_not_called()

    def test_assembly_no_redundant_credential_discovery(self) -> None:
        manifest = self._make_manifest()

        with patch.object(
            deployment_module,
            "create_kismet_eventbus_runtime",
            return_value=Mock(spec=["start", "stop"]),
        ) as mock_factory, patch(
            "kismet_eventbus_deployment.create_kismet_eventbus_runtime_from_manifest",
            wraps=create_kismet_eventbus_runtime_from_manifest,
        ):
            create_kismet_eventbus_runtime_from_manifest(
                manifest=manifest,
                authorization_header_value=_SYNTHETIC_AUTH,
                hmac_key=_SYNTHETIC_HMAC,
                ingest_timestamp_us_provider=_provider,
            )
            mock_factory.assert_called_once()


# ======================================================================
# 10. Manifest construction side-effect freedom
# ======================================================================


class ManifestConstructionSideEffectTests(unittest.TestCase):
    """Manifest construction performs no I/O, network, threading, subprocess,
    logging, printing, or wall-clock operations."""

    def test_manifest_construction_no_credential_discovery(self) -> None:
        import builtins
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

        forbidden = AssertionError(
            "manifest construction triggered forbidden side effect"
        )

        patch_targets = (
            (builtins, "open"),
            (builtins, "print"),
            (glob, "glob"),
            (glob, "iglob"),
            (importlib, "import_module"),
            (importlib.util, "spec_from_file_location"),
            (importlib.util, "module_from_spec"),
            (logging, "basicConfig"),
            (logging, "getLogger"),
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
            (pkgutil, "iter_modules"),
            (pkgutil, "walk_packages"),
            (runpy, "run_module"),
            (runpy, "run_path"),
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

        with ExitStack() as stack:
            for owner, attribute_name in patch_targets:
                stack.enter_context(
                    patch.object(
                        owner,
                        attribute_name,
                        side_effect=forbidden,
                    )
                )

            KismetEventbusDeploymentManifestV1(
                base_url="https://test.example",
                topics=("NEW_DEVICE",),
                tls_mode="verify_required",
                connect_timeout_s=10.0,
                reconnect_delay_s=5.0,
                stop_join_timeout_s=5.0,
                db_path="/tmp/test.sqlite",
                collection_session_id="test_session",
                sensor_id="test_sensor",
            )


if __name__ == "__main__":
    unittest.main()
