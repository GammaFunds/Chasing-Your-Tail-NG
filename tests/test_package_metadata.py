"""Tests for bounded package metadata and install layout."""

from __future__ import annotations

import ast
import subprocess
import stat
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
PYPROJECT_TOML = REPO_ROOT / "pyproject.toml"

DECLARED_MODULES = [
    "kismet_eventbus_deployment",
    "kismet_eventbus_new_device_adapter",
    "kismet_eventbus_observation_handler",
    "kismet_eventbus_runtime",
    "kismet_eventbus_runtime_config",
    "kismet_eventbus_transport",
    "observation_contract",
    "observation_store",
]

HISTORICAL_MODULES = [
    "chasing_your_tail",
    "cyt_gui",
    "probe_analyzer",
    "surveillance_analyzer",
    "surveillance_detector",
    "secure_credentials",
    "migrate_credentials",
]

HISTORICAL_STEM = set(HISTORICAL_MODULES)
DECLARED_STEM = set(DECLARED_MODULES)


def _parse() -> dict:
    with open(PYPROJECT_TOML, "rb") as f:
        return tomllib.load(f)


def _all_import_names(filepath: Path) -> set[str]:
    with open(filepath) as f:
        tree = ast.parse(f.read())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None and node.level == 0:
                names.add(node.module.split(".")[0])
    return names


def _validate_module_names(modules: list[str]) -> list[str]:
    """Return a list of validation errors for module names.
    An empty list means all names are valid.
    """
    errors: list[str] = []
    seen: set[str] = set()
    for name in modules:
        if type(name) is not str:
            errors.append(f"module name is not a built-in str: {type(name).__name__}")
            continue
        if not name:
            errors.append("module name is empty")
            continue
        if "." in name:
            errors.append(f"module name contains dot: {name!r}")
            continue
        if "/" in name or "\\" in name:
            errors.append(f"module name contains path separator: {name!r}")
            continue
        if not name.isidentifier():
            errors.append(f"module name is not a valid Python identifier: {name!r}")
            continue
        if name in seen:
            errors.append(f"duplicate module name: {name!r}")
        seen.add(name)
    return errors


def _validate_declared_sources(root: Path, modules: list[str]) -> list[str]:
    """Validate flat py-modules source layout under *root*.
    Returns a list of error messages (empty = valid).
    """
    errors: list[str] = []
    for name in modules:
        if type(name) is not str:
            continue  # caught by name validation
        source = root / f"{name}.py"
        try:
            st = source.lstat()
        except FileNotFoundError:
            errors.append(f"missing module source: {name}.py")
            continue
        except OSError:
            errors.append(f"cannot access {name}.py")
            continue

        if stat.S_ISLNK(st.st_mode):
            errors.append(f"{name}.py is a symbolic link")
        elif not stat.S_ISREG(st.st_mode):
            errors.append(f"{name}.py is not a regular file")

        dir_path = root / name
        if dir_path.is_dir():
            errors.append(f"directory {name}/ exists beside module file {name}.py")
    return errors


# ======================================================================
# Build system
# ======================================================================


class TestBuildSystem(unittest.TestCase):
    def test_build_backend(self) -> None:
        data = _parse()
        self.assertEqual(
            data["build-system"]["build-backend"],
            "setuptools.build_meta",
        )

    def test_requires(self) -> None:
        data = _parse()
        self.assertEqual(
            data["build-system"]["requires"],
            ["setuptools>=68"],
        )

    def test_build_system_only_keys(self) -> None:
        data = _parse()
        keys = set(data["build-system"])
        self.assertEqual(keys, {"build-backend", "requires"})


# ======================================================================
# Project metadata
# ======================================================================


class TestProjectMetadata(unittest.TestCase):
    def setUp(self) -> None:
        self.project = _parse()["project"]

    def test_name(self) -> None:
        self.assertEqual(self.project["name"], "chasing-your-tail-ng")

    def test_version(self) -> None:
        self.assertEqual(self.project["version"], "0.1.0")

    def test_description(self) -> None:
        self.assertEqual(
            self.project["description"],
            "Bounded Kismet eventbus runtime for Chasing Your Tail NG",
        )

    def test_requires_python(self) -> None:
        self.assertEqual(self.project["requires-python"], ">=3.10")

    def test_license(self) -> None:
        self.assertEqual(self.project["license"], {"file": "LICENSE"})

    def test_dependencies(self) -> None:
        self.assertEqual(
            self.project["dependencies"],
            ["websocket-client>=1.8"],
        )

    def test_no_dynamic(self) -> None:
        self.assertNotIn("dynamic", self.project)

    def test_no_scripts(self) -> None:
        self.assertNotIn("scripts", self.project)

    def test_no_gui_scripts(self) -> None:
        self.assertNotIn("gui-scripts", self.project)

    def test_no_entry_points(self) -> None:
        self.assertNotIn("entry-points", self.project)

    def test_no_optional_dependencies(self) -> None:
        self.assertNotIn("optional-dependencies", self.project)

    def test_no_readme(self) -> None:
        self.assertNotIn("readme", self.project)

    def test_no_data_files(self) -> None:
        self.assertNotIn("data-files", self.project)


# ======================================================================
# py-modules
# ======================================================================


class TestPyModules(unittest.TestCase):
    def test_exact_ordered_py_modules(self) -> None:
        data = _parse()
        py_modules = data["tool"]["setuptools"]["py-modules"]
        self.assertEqual(py_modules, DECLARED_MODULES)

    def test_no_packages_key(self) -> None:
        data = _parse()
        self.assertNotIn("packages", data["tool"]["setuptools"])

    def test_no_find(self) -> None:
        data = _parse()
        self.assertNotIn("find", data["tool"]["setuptools"])

    def test_no_package_data(self) -> None:
        data = _parse()
        cfg = data["tool"]["setuptools"]
        self.assertNotIn("package-data", cfg)
        self.assertNotIn("include-package-data", cfg)

    def test_no_cmdclass(self) -> None:
        data = _parse()
        cfg = data["tool"]["setuptools"]
        self.assertNotIn("cmdclass", cfg)


# ======================================================================
# SCM / environment-derived metadata
# ======================================================================


class TestForbiddenExtensions(unittest.TestCase):
    def test_no_setuptools_scm_section(self) -> None:
        data = _parse()
        tool = data.get("tool", {})
        self.assertNotIn("setuptools_scm", tool)

    def test_no_dynamic_version(self) -> None:
        """No SCM-derived versioning or environment-derived metadata."""
        data = _parse()
        project = data.get("project", {})
        self.assertNotIn("dynamic", project)

    def test_no_env_metadata(self) -> None:
        """Check no environment markers in dependencies."""
        data = _parse()
        for dep in data["project"].get("dependencies", []):
            self.assertNotIn(";", dep, f"Environment marker in dependency: {dep}")


# ======================================================================
# Historical modules absent
# ======================================================================


class TestHistoricalModulesAbsent(unittest.TestCase):
    def test_py_modules_excludes_historical(self) -> None:
        data = _parse()
        actual = set(data["tool"]["setuptools"]["py-modules"])
        overlap = actual & HISTORICAL_STEM
        self.assertFalse(overlap, f"Historical modules in py-modules: {overlap}")

    def test_no_historical_imports_in_declared_modules(self) -> None:
        for mod in DECLARED_MODULES:
            filepath = REPO_ROOT / f"{mod}.py"
            imports = _all_import_names(filepath)
            overlap = imports & HISTORICAL_STEM
            self.assertFalse(
                overlap,
                f"{mod}.py imports historical modules: {overlap}",
            )


# ======================================================================
# AST import closure
# ======================================================================


class TestImportClosure(unittest.TestCase):
    def test_closure_equals_declared_modules(self) -> None:
        closure = self._closure("kismet_eventbus_deployment")
        self.assertEqual(closure, DECLARED_STEM)

    def _closure(self, start: str) -> set[str]:
        visited: set[str] = set()
        queue = [start]
        while queue:
            mod = queue.pop(0)
            if mod in visited:
                continue
            visited.add(mod)
            filepath = REPO_ROOT / f"{mod}.py"
            for name in _all_import_names(filepath):
                if (REPO_ROOT / f"{name}.py").exists() and name not in visited:
                    queue.append(name)
        return visited

    def test_closure_no_extra_modules(self) -> None:
        closure = self._closure("kismet_eventbus_deployment")
        self.assertEqual(closure, DECLARED_STEM)
        unexpected = closure - DECLARED_STEM
        self.assertFalse(
            unexpected,
            f"Closure includes unexpected modules: {unexpected}",
        )
        missing = DECLARED_STEM - closure
        self.assertFalse(
            missing,
            f"Declared modules missing from closure: {missing}",
        )


# ======================================================================
# External dependency
# ======================================================================


class TestExternalDependency(unittest.TestCase):
    def test_only_websocket_is_external(self) -> None:
        external: set[str] = set()
        for mod in DECLARED_MODULES:
            filepath = REPO_ROOT / f"{mod}.py"
            for name in _all_import_names(filepath):
                if name in DECLARED_STEM:
                    continue
                if name == "__future__":
                    continue
                if name in sys.stdlib_module_names:
                    continue
                external.add(name)
        self.assertEqual(external, {"websocket"})


# ======================================================================
# Import probe (fresh subprocess, no side effects)
# ======================================================================


class TestImportProbe(unittest.TestCase):
    def test_import_produces_no_side_effects(self) -> None:
        imports = "\n".join(f"import {m}" for m in DECLARED_MODULES)
        script = (
            "import io, sqlite3, socket, sys, threading\n"
            "_threads_before = tuple(threading.enumerate())\n"
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
            f"{imports}\n"
            "_cap_out = sys.stdout.getvalue()\n"
            "_cap_err = sys.stderr.getvalue()\n"
            "sys.stdout = _saved_out\n"
            "sys.stderr = _saved_err\n"
            "_errs = []\n"
            "if _cap_out:\n"
            "    _errs.append('stdout: ' + repr(_cap_out))\n"
            "if _cap_err:\n"
            "    _errs.append('stderr: ' + repr(_cap_err))\n"
            "if tuple(threading.enumerate()) != _threads_before:\n"
            "    _errs.append('threads changed')\n"
            "if 'websocket' in sys.modules:\n"
            "    _errs.append('websocket imported')\n"
            "if _errs:\n"
            "    print('; '.join(_errs))\n"
            "    sys.exit(1)\n"
        )
        result = subprocess.run(
            [sys.executable, "-B", "-c", script],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        if result.returncode != 0:
            self.fail(
                f"Import probe failed (exit={result.returncode}): "
                f"stdout={result.stdout!r} stderr={result.stderr!r}"
            )
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")


# ======================================================================
# Source install layout
# ======================================================================


class TestSourceLayout(unittest.TestCase):
    """Validates that every declared module maps to a regular file at the
    repository root with no symlinks, missing files, directory collisions,
    or same-name directory conflicts."""

    def test_declared_module_names_are_unique_valid_flat_identifiers(self) -> None:
        # Positive: actual declared modules must be valid
        errors = _validate_module_names(DECLARED_MODULES)
        self.assertFalse(
            errors,
            f"Invalid module names:\n" + "\n".join(errors),
        )

        # Negative: prove rejection of invalid module names
        self.assertTrue(
            _validate_module_names([""]),
            "Expected rejection of empty module name",
        )
        self.assertTrue(
            _validate_module_names(["a.b"]),
            "Expected rejection of dotted module name",
        )
        self.assertTrue(
            _validate_module_names(["a/b"]),
            "Expected rejection of forward-slash path in module name",
        )
        self.assertTrue(
            _validate_module_names(["a\\b"]),
            "Expected rejection of backslash path in module name",
        )
        self.assertTrue(
            _validate_module_names(["123abc"]),
            "Expected rejection of invalid Python identifier",
        )
        self.assertTrue(
            _validate_module_names([42]),
            "Expected rejection of non-string module name",
        )

        class _StrSub(str):
            pass

        self.assertTrue(
            _validate_module_names([_StrSub("x")]),
            "Expected rejection of str subclass module name",
        )
        self.assertTrue(
            _validate_module_names(["mod", "mod"]),
            "Expected rejection of duplicate module name",
        )

    def test_declared_module_sources_are_regular_root_files(self) -> None:
        errors = _validate_declared_sources(REPO_ROOT, DECLARED_MODULES)
        self.assertFalse(
            errors,
            f"Source layout invalid:\n" + "\n".join(errors),
        )

    def test_missing_declared_module_source_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "present.py").write_text("")
            errors = _validate_declared_sources(root, ["present", "absent"])
            self.assertTrue(errors)
            self.assertTrue(
                any("absent" in e for e in errors),
                f"No error for missing module 'absent': {errors}",
            )

    def test_directory_in_place_of_module_source_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "mymod.py").mkdir()
            errors = _validate_declared_sources(root, ["mymod"])
            self.assertTrue(errors)
            self.assertTrue(
                any("not a regular file" in e for e in errors),
                f"No error for directory in place of file: {errors}",
            )

    def test_symlink_module_source_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "real.py").write_text("")
            (root / "mymod.py").symlink_to("real.py")
            errors = _validate_declared_sources(root, ["mymod"])
            self.assertTrue(errors)
            self.assertTrue(
                any("symbolic link" in e for e in errors),
                f"No error for symlink module source: {errors}",
            )

    def test_same_name_directory_collision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "mymod.py").write_text("")
            (root / "mymod").mkdir()
            errors = _validate_declared_sources(root, ["mymod"])
            self.assertTrue(errors)
            self.assertTrue(
                any("directory" in e and "mymod" in e for e in errors),
                f"No error for same-name directory collision: {errors}",
            )
