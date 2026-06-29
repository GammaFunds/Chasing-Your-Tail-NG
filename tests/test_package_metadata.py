"""Tests for bounded package metadata and install layout."""

from __future__ import annotations

import ast
import base64
import csv
from email.parser import Parser
import hashlib
import importlib.metadata as importlib_metadata
import io
import os
import shutil
import subprocess
import stat
import sys
import tempfile
import tomllib
import unittest
import warnings
from pathlib import Path, PurePosixPath
import zipfile

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
PYPROJECT_TOML = REPO_ROOT / "pyproject.toml"

DECLARED_MODULES = [
    "kismet_eventbus_deployment",
    "kismet_eventbus_entrypoint",
    "kismet_eventbus_new_device_adapter",
    "kismet_eventbus_observation_handler",
    "kismet_eventbus_runtime",
    "kismet_eventbus_runtime_config",
    "kismet_eventbus_transport",
    "observation_contract",
    "observation_store",
]

DEPLOYMENT_ONLY_MODULES = [
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
DEPLOYMENT_ONLY_STEM = set(DEPLOYMENT_ONLY_MODULES)
WHEEL_FILENAME = "chasing_your_tail_ng-0.1.0-py3-none-any.whl"
DIST_INFO_DIR = "chasing_your_tail_ng-0.1.0.dist-info"
EXPECTED_ROOT_MODULE_FILES = {f"{module}.py" for module in DECLARED_MODULES}
REQUIRED_DIST_INFO_FILES = {"METADATA", "WHEEL", "RECORD"}
WHEEL_OPTIONAL_DIST_INFO_FILES = {"top_level.txt"}
INSTALLED_OPTIONAL_DIST_INFO_FILES = {
    "top_level.txt",
    "INSTALLER",
    "REQUESTED",
    "direct_url.json",
}
LICENSE_DIST_INFO_DIR = "licenses"
LICENSE_TEXT_BASENAMES = {
    "AUTHORS",
    "CONTRIBUTORS",
    "COPYING",
    "LICENSE",
    "NOTICE",
}
LICENSE_TEXT_SUFFIXES = {".md", ".rst", ".txt"}
ALLOWED_WHEEL_DIRECTORY_ENTRIES = {
    f"{DIST_INFO_DIR}/",
    f"{DIST_INFO_DIR}/{LICENSE_DIST_INFO_DIR}/",
}


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


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _copy_package_source(source_root: Path) -> None:
    shutil.copy2(PYPROJECT_TOML, source_root / "pyproject.toml")
    shutil.copy2(REPO_ROOT / "LICENSE", source_root / "LICENSE")
    for module in DECLARED_MODULES:
        shutil.copy2(REPO_ROOT / f"{module}.py", source_root / f"{module}.py")


def _subprocess_env(home: Path, cache: Path, tmpdir: Path) -> dict[str, str]:
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.upper().endswith("_PROXY")
        and not name.upper().startswith("PROXY_")
        and name.upper() != "PYTHONPATH"
    }
    env.update(
        {
            "HOME": str(home),
            "XDG_CACHE_HOME": str(cache),
            "TMPDIR": str(tmpdir),
            "PIP_NO_INDEX": "1",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INPUT": "1",
        }
    )
    return env


def _run_success(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {args!r}\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )
    return result


def _component_is_historical_payload(component: str) -> bool:
    if component in HISTORICAL_STEM:
        return True
    if component.endswith(".py") and component[:-3] in HISTORICAL_STEM:
        return True
    return False


def _assert_raw_archive_member_name(path: str) -> None:
    if path == "":
        raise AssertionError(f"empty archive member name: {path!r}")
    if "\x00" in path:
        raise AssertionError(f"NUL byte in archive member name: {path!r}")
    if "\\" in path:
        raise AssertionError(f"backslash in archive member name: {path!r}")
    if path.startswith("/"):
        raise AssertionError(f"absolute archive member name: {path!r}")
    if (
        len(path) >= 2
        and path[1] == ":"
        and ("A" <= path[0] <= "Z" or "a" <= path[0] <= "z")
    ):
        raise AssertionError(f"drive-like archive member name: {path!r}")

    body = path[:-1] if path.endswith("/") else path
    if body == "":
        raise AssertionError(f"empty archive member body: {path!r}")
    if "//" in body:
        raise AssertionError(f"repeated separator in archive member name: {path!r}")

    for component in body.split("/"):
        if component == "":
            raise AssertionError(f"empty component in archive member name: {path!r}")
        if component == ".":
            raise AssertionError(f"dot component in archive member name: {path!r}")
        if component == "..":
            raise AssertionError(
                f"parent traversal component in archive member name: {path!r}"
            )


def _archive_path_errors(path: str) -> list[str]:
    errors: list[str] = []
    posix_path = PurePosixPath(path)
    parts = posix_path.parts
    lowered_parts = tuple(part.lower() for part in parts)

    if posix_path.is_absolute() or path.startswith("/"):
        errors.append(f"absolute archive path: {path!r}")
    if "\\" in path:
        errors.append(f"backslash in archive path: {path!r}")
    if ".." in parts:
        errors.append(f"parent traversal in archive path: {path!r}")
    if "tests" in parts:
        errors.append(f"tests component in archive path: {path!r}")
    if "__pycache__" in parts:
        errors.append(f"__pycache__ component in archive path: {path!r}")
    if path.endswith(".pyc") or any(part.endswith(".pyc") for part in parts):
        errors.append(f"bytecode archive path: {path!r}")
    if any(part.endswith(".data") for part in parts):
        errors.append(f"data payload archive path: {path!r}")
    if "scripts" in lowered_parts:
        errors.append(f"scripts component in archive path: {path!r}")
    if "entry_points.txt" in parts:
        errors.append(f"entry points in archive path: {path!r}")
    if any(_component_is_historical_payload(part) for part in parts):
        errors.append(f"historical payload in archive path: {path!r}")

    return errors


def _assert_no_archive_path_violations(paths: list[str] | set[str]) -> None:
    errors = [
        error
        for path in sorted(paths)
        for error in _archive_path_errors(path)
    ]
    if errors:
        raise AssertionError("invalid wheel paths:\n" + "\n".join(errors))


def _is_permitted_license_dist_info_file(parts: tuple[str, ...]) -> bool:
    """Permit only direct, text-like license documents under licenses/.

    The license subtree is intentionally narrow: it accepts common license
    document names, optionally with a text-markup suffix, and does not allow
    nested directories, Python/code files, native payloads, or script names.
    """
    if len(parts) != 3 or parts[1] != LICENSE_DIST_INFO_DIR:
        return False

    name = parts[2]
    if not name or name.startswith("."):
        return False

    suffix = PurePosixPath(name).suffix.lower()
    stem = name[: -len(suffix)] if suffix else name
    if suffix and suffix not in LICENSE_TEXT_SUFFIXES:
        return False
    return stem.upper() in LICENSE_TEXT_BASENAMES


def _dist_info_policy_error(
    path: str,
    *,
    optional_direct_files: set[str],
    context: str,
) -> str | None:
    parts = PurePosixPath(path).parts
    if len(parts) < 2 or parts[0] != DIST_INFO_DIR:
        raise AssertionError(f"internal dist-info policy error for {path!r}")

    direct_files = REQUIRED_DIST_INFO_FILES | optional_direct_files
    if len(parts) == 2:
        if parts[1] in direct_files:
            return None
        return f"unexpected {context} dist-info file: {path}"

    if parts[1] == LICENSE_DIST_INFO_DIR:
        if _is_permitted_license_dist_info_file(parts):
            return None
        return f"unexpected {context} dist-info license file: {path}"

    return f"unexpected {context} dist-info directory: {path}"


def _assert_dist_info_file_policy(
    dist_info_files: set[str],
    *,
    optional_direct_files: set[str],
    context: str,
) -> None:
    required_paths = {f"{DIST_INFO_DIR}/{name}" for name in REQUIRED_DIST_INFO_FILES}
    missing = required_paths - dist_info_files
    if missing:
        raise AssertionError(f"missing {context} dist-info files: {sorted(missing)!r}")

    errors = [
        error
        for path in sorted(dist_info_files)
        for error in [
            _dist_info_policy_error(
                path,
                optional_direct_files=optional_direct_files,
                context=context,
            )
        ]
        if error is not None
    ]
    if errors:
        raise AssertionError(
            f"invalid {context} dist-info positive policy:\n" + "\n".join(errors)
        )


def _assert_wheel_directory_entry_policy(directory_paths: list[str]) -> None:
    errors = [
        f"unexpected wheel directory entry: {path!r}"
        for path in sorted(directory_paths)
        if path not in ALLOWED_WHEEL_DIRECTORY_ENTRIES
    ]
    if errors:
        raise AssertionError("\n".join(errors))


def _read_wheel_members(wheel_path: Path) -> tuple[set[str], dict[str, bytes]]:
    member_names: list[str] = []
    directory_paths: list[str] = []
    file_members: list[tuple[str, bytes]] = []
    seen: set[str] = set()

    with zipfile.ZipFile(wheel_path) as wheel:
        for info in wheel.infolist():
            name = info.filename
            _assert_raw_archive_member_name(name)
            if name in seen:
                raise AssertionError(f"duplicate wheel member: {name!r}")
            seen.add(name)

            member_names.append(name)
            if info.is_dir():
                directory_paths.append(name)
            else:
                file_members.append((name, wheel.read(info)))

    _assert_no_archive_path_violations(member_names)
    _assert_wheel_directory_entry_policy(directory_paths)
    return set(member_names), dict(file_members)


def _assert_wheel_layout(wheel_path: Path) -> dict[str, bytes]:
    all_paths, file_bytes = _read_wheel_members(wheel_path)
    file_paths = set(file_bytes)
    _assert_no_archive_path_violations(all_paths)

    dist_info_roots = {
        component
        for path in file_paths
        for component in PurePosixPath(path).parts
        if component.endswith(".dist-info")
    }
    if dist_info_roots != {DIST_INFO_DIR}:
        raise AssertionError(f"dist-info roots mismatch: {dist_info_roots!r}")

    outside_dist_info = {
        path
        for path in file_paths
        if PurePosixPath(path).parts[0] != DIST_INFO_DIR
    }
    if outside_dist_info != EXPECTED_ROOT_MODULE_FILES:
        raise AssertionError(
            "wheel payload mismatch:\n"
            f"expected={sorted(EXPECTED_ROOT_MODULE_FILES)!r}\n"
            f"actual={sorted(outside_dist_info)!r}"
        )

    dist_info_files = {
        path
        for path in file_paths
        if PurePosixPath(path).parts[0] == DIST_INFO_DIR
    }
    _assert_dist_info_file_policy(
        dist_info_files,
        optional_direct_files=WHEEL_OPTIONAL_DIST_INFO_FILES,
        context="wheel",
    )

    return file_bytes


def _assert_core_metadata(file_bytes: dict[str, bytes]) -> None:
    metadata = Parser().parsestr(
        file_bytes[f"{DIST_INFO_DIR}/METADATA"].decode("utf-8")
    )
    if metadata["Name"] != "chasing-your-tail-ng":
        raise AssertionError(f"metadata Name mismatch: {metadata['Name']!r}")
    if metadata["Version"] != "0.1.0":
        raise AssertionError(f"metadata Version mismatch: {metadata['Version']!r}")
    if metadata["Requires-Python"] != ">=3.10":
        raise AssertionError(
            f"metadata Requires-Python mismatch: {metadata['Requires-Python']!r}"
        )
    if metadata.get_all("Requires-Dist") != ["websocket-client>=1.8"]:
        raise AssertionError(
            "metadata Requires-Dist mismatch: "
            f"{metadata.get_all('Requires-Dist')!r}"
        )

    wheel = Parser().parsestr(file_bytes[f"{DIST_INFO_DIR}/WHEEL"].decode("utf-8"))
    if wheel["Wheel-Version"] != "1.0":
        raise AssertionError(f"Wheel-Version mismatch: {wheel['Wheel-Version']!r}")
    if wheel["Root-Is-Purelib"] != "true":
        raise AssertionError(
            f"Root-Is-Purelib mismatch: {wheel['Root-Is-Purelib']!r}"
        )
    if wheel.get_all("Tag") != ["py3-none-any"]:
        raise AssertionError(f"wheel Tag mismatch: {wheel.get_all('Tag')!r}")


def _assert_record_hashes(file_bytes: dict[str, bytes]) -> None:
    record_path = f"{DIST_INFO_DIR}/RECORD"
    rows = csv.reader(
        io.StringIO(file_bytes[record_path].decode("utf-8"), newline="")
    )
    seen: set[str] = set()
    for row in rows:
        if not row:
            continue
        if len(row) != 3:
            raise AssertionError(f"RECORD row field count mismatch: {row!r}")

        path, hash_spec, size = row
        if path in seen:
            raise AssertionError(f"duplicate RECORD path: {path!r}")
        seen.add(path)

        if path == record_path:
            if hash_spec != "" or size != "":
                raise AssertionError(f"RECORD self-row not empty: {row!r}")
            continue

        if not hash_spec.startswith("sha256="):
            raise AssertionError(f"RECORD hash is not sha256: {row!r}")
        if not size.isdecimal():
            raise AssertionError(f"RECORD size is not decimal: {row!r}")

        if path not in file_bytes:
            raise AssertionError(f"RECORD path missing from wheel: {path!r}")
        member_bytes = file_bytes[path]
        digest = base64.urlsafe_b64encode(
            hashlib.sha256(member_bytes).digest()
        ).decode("ascii").rstrip("=")
        if hash_spec != f"sha256={digest}":
            raise AssertionError(f"RECORD hash mismatch for {path!r}")
        if size != str(len(member_bytes)):
            raise AssertionError(f"RECORD size mismatch for {path!r}")

    if seen != set(file_bytes):
        raise AssertionError(
            "RECORD path set mismatch:\n"
            f"missing={sorted(set(file_bytes) - seen)!r}\n"
            f"extra={sorted(seen - set(file_bytes))!r}"
        )


def _assert_wheel_contract(wheel_path: Path) -> None:
    if wheel_path.name != WHEEL_FILENAME:
        raise AssertionError(f"wheel filename mismatch: {wheel_path.name!r}")
    file_bytes = _assert_wheel_layout(wheel_path)
    _assert_core_metadata(file_bytes)
    _assert_record_hashes(file_bytes)


def _installed_path_legacy_errors(relative: Path) -> list[str]:
    parts = relative.parts
    lowered_parts = tuple(part.lower() for part in parts)
    errors: list[str] = []

    if "tests" in parts:
        errors.append(f"tests component in installed path: {relative}")
    if "__pycache__" in parts:
        errors.append(f"__pycache__ component in installed path: {relative}")
    if relative.suffix == ".pyc" or any(part.endswith(".pyc") for part in parts):
        errors.append(f"bytecode installed path: {relative}")
    if any(part.endswith(".data") for part in parts):
        errors.append(f"data payload installed path: {relative}")
    if "bin" in lowered_parts or "scripts" in lowered_parts:
        errors.append(f"script installed path: {relative}")
    if "entry_points.txt" in parts:
        errors.append(f"entry points installed path: {relative}")
    if any(_component_is_historical_payload(part) for part in parts):
        errors.append(f"historical payload installed path: {relative}")

    return errors


def _installed_object_kind(mode: int) -> str:
    if stat.S_ISLNK(mode):
        return "symbolic link"
    if stat.S_ISREG(mode):
        return "regular file"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISFIFO(mode):
        return "FIFO"
    if stat.S_ISSOCK(mode):
        return "socket"
    if stat.S_ISCHR(mode):
        return "character device"
    if stat.S_ISBLK(mode):
        return "block device"
    return "non-regular file"


def _walk_installed_entries(install_target: Path) -> list[tuple[Path, os.stat_result]]:
    entries: list[tuple[Path, os.stat_result]] = []
    stack = [install_target]
    while stack:
        directory = stack.pop()
        with os.scandir(directory) as iterator:
            for entry in iterator:
                path = Path(entry.path)
                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError as exc:
                    raise AssertionError(f"cannot stat installed path: {path}") from exc
                entries.append((path, st))
                if stat.S_ISDIR(st.st_mode):
                    stack.append(path)
    return sorted(entries, key=lambda item: item[0].relative_to(install_target).parts)


def _assert_installed_tree(install_target: Path) -> None:
    try:
        target_st = install_target.lstat()
    except OSError as exc:
        raise AssertionError(f"cannot stat install target: {install_target}") from exc
    if not stat.S_ISDIR(target_st.st_mode) or stat.S_ISLNK(target_st.st_mode):
        kind = _installed_object_kind(target_st.st_mode)
        raise AssertionError(f"install target is not a genuine directory: {kind}")

    errors: list[str] = []
    root_regular_files: set[str] = set()
    root_dist_info_dirs: list[str] = []
    dist_info_files: set[str] = set()

    for path, st in _walk_installed_entries(install_target):
        relative = path.relative_to(install_target)
        parts = relative.parts
        mode = st.st_mode
        is_symlink = stat.S_ISLNK(mode)
        is_regular = stat.S_ISREG(mode)
        is_dir = stat.S_ISDIR(mode)
        kind = _installed_object_kind(mode)

        errors.extend(_installed_path_legacy_errors(relative))

        if len(parts) == 1 and path.name in EXPECTED_ROOT_MODULE_FILES:
            if is_symlink:
                errors.append(f"installed root module is a symbolic link: {relative}")
            elif not is_regular:
                errors.append(f"installed root module is not a regular file: {relative}")
            else:
                root_regular_files.add(path.name)
            continue

        if len(parts) == 1 and path.name.endswith(".dist-info"):
            if is_symlink:
                errors.append(f"installed dist-info is a symbolic link: {relative}")
            elif not is_dir:
                errors.append(f"installed dist-info is not a directory: {relative}")
            else:
                root_dist_info_dirs.append(path.name)
            continue

        if len(parts) == 1:
            if is_symlink:
                errors.append(f"unexpected installed root symbolic link: {relative}")
            elif is_dir:
                errors.append(f"unexpected installed root directory: {relative}")
            elif is_regular:
                errors.append(f"unexpected installed root file: {relative}")
            else:
                errors.append(f"unexpected installed root {kind}: {relative}")
            continue

        if parts[0] != DIST_INFO_DIR:
            if is_symlink:
                errors.append(f"unexpected installed symbolic link outside dist-info: {relative}")
            elif is_dir:
                errors.append(f"unexpected installed directory outside dist-info: {relative}")
            elif is_regular:
                errors.append(f"unexpected installed file outside dist-info: {relative}")
            else:
                errors.append(f"unexpected installed {kind} outside dist-info: {relative}")
            continue

        if is_symlink:
            errors.append(f"installed dist-info path is a symbolic link: {relative}")
            continue
        if is_dir:
            if parts != (DIST_INFO_DIR, LICENSE_DIST_INFO_DIR):
                errors.append(f"unexpected installed dist-info directory: {relative}")
            continue
        if not is_regular:
            errors.append(f"installed dist-info path is not regular: {relative} ({kind})")
            continue

        dist_info_file = relative.as_posix()
        policy_error = _dist_info_policy_error(
            dist_info_file,
            optional_direct_files=INSTALLED_OPTIONAL_DIST_INFO_FILES,
            context="installed",
        )
        if policy_error is not None:
            errors.append(policy_error)
        else:
            dist_info_files.add(dist_info_file)

    if root_dist_info_dirs != [DIST_INFO_DIR]:
        errors.append(f"installed dist-info mismatch: {root_dist_info_dirs!r}")

    missing_dist_info = {
        f"{DIST_INFO_DIR}/{name}" for name in REQUIRED_DIST_INFO_FILES
    } - dist_info_files
    if missing_dist_info:
        errors.append(
            f"missing installed dist-info files: {sorted(missing_dist_info)!r}"
        )

    if root_regular_files != EXPECTED_ROOT_MODULE_FILES:
        errors.append(
            "installed root module mismatch:\n"
            f"expected={sorted(EXPECTED_ROOT_MODULE_FILES)!r}\n"
            f"actual={sorted(root_regular_files)!r}"
        )

    if errors:
        raise AssertionError(
            "invalid installed tree:\n" + "\n".join(errors)
        )


def _assert_installed_metadata(install_target: Path) -> None:
    distributions = list(importlib_metadata.distributions(path=[str(install_target)]))
    if len(distributions) != 1:
        raise AssertionError(f"distribution count mismatch: {distributions!r}")

    distribution = distributions[0]
    metadata = distribution.metadata
    if metadata["Name"] != "chasing-your-tail-ng":
        raise AssertionError(f"installed Name mismatch: {metadata['Name']!r}")
    if distribution.version != "0.1.0":
        raise AssertionError(f"installed Version mismatch: {distribution.version!r}")
    if distribution.requires != ["websocket-client>=1.8"]:
        raise AssertionError(f"installed requires mismatch: {distribution.requires!r}")


def _import_probe_script() -> str:
    imports = repr(tuple(DECLARED_MODULES))
    return (
        "import importlib, io, sqlite3, socket, sys, threading\n"
        "from pathlib import Path\n"
        "install_target = Path(sys.argv[1]).resolve()\n"
        "repo_root = Path(sys.argv[2]).resolve()\n"
        "errors = []\n"
        "for entry in tuple(sys.path):\n"
        "    resolved = (Path.cwd() if entry == '' else Path(entry)).resolve()\n"
        "    try:\n"
        "        resolved.relative_to(repo_root)\n"
        "    except ValueError:\n"
        "        pass\n"
        "    else:\n"
        "        errors.append(f'repository sys.path entry: {resolved}')\n"
        "if errors:\n"
        "    raise AssertionError('; '.join(errors))\n"
        "sys.path.insert(0, str(install_target))\n"
        "threads_before = tuple(threading.enumerate())\n"
        "def guard(*args, **kwargs):\n"
        "    raise AssertionError('forbidden side effect')\n"
        "sqlite3.connect = guard\n"
        "socket.socket = guard\n"
        "socket.create_connection = guard\n"
        "threading.Thread.start = guard\n"
        "saved_stdout = sys.stdout\n"
        "saved_stderr = sys.stderr\n"
        "captured_stdout = io.StringIO()\n"
        "captured_stderr = io.StringIO()\n"
        "sys.stdout = captured_stdout\n"
        "sys.stderr = captured_stderr\n"
        "modules = []\n"
        "try:\n"
        f"    for name in {imports}:\n"
        "        modules.append(importlib.import_module(name))\n"
        "finally:\n"
        "    sys.stdout = saved_stdout\n"
        "    sys.stderr = saved_stderr\n"
        "for module in modules:\n"
        "    module_file = Path(module.__file__).resolve()\n"
        "    try:\n"
        "        module_file.relative_to(install_target)\n"
        "    except ValueError:\n"
        "        errors.append(f'{module.__name__} outside install target: {module_file}')\n"
        "if captured_stdout.getvalue():\n"
        "    errors.append(f'stdout: {captured_stdout.getvalue()!r}')\n"
        "if captured_stderr.getvalue():\n"
        "    errors.append(f'stderr: {captured_stderr.getvalue()!r}')\n"
        "if tuple(threading.enumerate()) != threads_before:\n"
        "    errors.append('threads changed')\n"
        "if 'websocket' in sys.modules:\n"
        "    errors.append('websocket imported')\n"
        "if errors:\n"
        "    raise AssertionError('; '.join(errors))\n"
    )


def _copy_wheel_with_extra_member(
    source_wheel: Path,
    target_wheel: Path,
    member_name: str,
    member_bytes: bytes,
) -> None:
    shutil.copy2(source_wheel, target_wheel)
    with zipfile.ZipFile(target_wheel, "a") as wheel:
        wheel.writestr(member_name, member_bytes)


def _copy_wheel_preserving_members(
    source_wheel: Path,
    target_wheel: Path,
    extra_info: zipfile.ZipInfo,
    extra_bytes: bytes,
) -> None:
    with zipfile.ZipFile(source_wheel) as source, zipfile.ZipFile(
        target_wheel, "w"
    ) as target:
        for info in source.infolist():
            member_bytes = b"" if info.is_dir() else source.read(info)
            target.writestr(info, member_bytes)
        target.writestr(extra_info, extra_bytes)


def _copy_wheel_with_duplicate_member(source_wheel: Path, target_dir: Path) -> Path:
    target_dir.mkdir()
    target_wheel = target_dir / WHEEL_FILENAME
    duplicate_name = f"{DECLARED_MODULES[0]}.py"
    duplicate_info = zipfile.ZipInfo(duplicate_name)
    duplicate_bytes = b"# duplicate member bytes must be rejected before RECORD\n"

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=f"Duplicate name: {duplicate_name!r}",
            category=UserWarning,
            module="zipfile",
        )
        _copy_wheel_preserving_members(
            source_wheel,
            target_wheel,
            duplicate_info,
            duplicate_bytes,
        )

    return target_wheel


def _copy_wheel_with_extra_directory(source_wheel: Path, target_dir: Path) -> Path:
    target_dir.mkdir()
    target_wheel = target_dir / WHEEL_FILENAME
    directory_info = zipfile.ZipInfo(f"{DIST_INFO_DIR}/unexpected/")
    directory_info.external_attr = (stat.S_IFDIR | 0o755) << 16

    _copy_wheel_preserving_members(source_wheel, target_wheel, directory_info, b"")
    return target_wheel


def _copy_wheel_with_malformed_member_name(
    source_wheel: Path,
    target_dir: Path,
) -> Path:
    target_dir.mkdir()
    target_wheel = target_dir / WHEEL_FILENAME
    malformed_info = zipfile.ZipInfo(f"{DIST_INFO_DIR}//evil.py")
    malformed_bytes = b"raise RuntimeError('malformed path must be rejected')\n"

    _copy_wheel_preserving_members(
        source_wheel,
        target_wheel,
        malformed_info,
        malformed_bytes,
    )
    return target_wheel


def _copy_wheel_with_missing_record_target(
    source_wheel: Path,
    target_dir: Path,
) -> Path:
    target_dir.mkdir()
    target_wheel = target_dir / WHEEL_FILENAME
    record_path = f"{DIST_INFO_DIR}/RECORD"
    missing_path = "missing_from_wheel.py"
    missing_digest = base64.urlsafe_b64encode(
        hashlib.sha256(b"").digest()
    ).decode("ascii").rstrip("=")
    missing_row = [missing_path, f"sha256={missing_digest}", "0"]

    with zipfile.ZipFile(source_wheel) as source, zipfile.ZipFile(
        target_wheel, "w"
    ) as target:
        record_rows = list(
            csv.reader(
                io.StringIO(source.read(record_path).decode("utf-8"), newline="")
            )
        )
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        writer.writerows(record_rows)
        writer.writerow(missing_row)
        replacement_record = output.getvalue().encode("utf-8")

        for info in source.infolist():
            if info.filename == record_path:
                target.writestr(info, replacement_record)
            else:
                member_bytes = b"" if info.is_dir() else source.read(info)
                target.writestr(info, member_bytes)

    return target_wheel


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

    def test_entrypoint_closure_equals_all_nine_modules(self) -> None:
        closure = self._closure("kismet_eventbus_entrypoint")
        self.assertEqual(closure, DECLARED_STEM)

    def test_deployment_closure_equals_original_eight_modules(self) -> None:
        closure = self._closure("kismet_eventbus_deployment")
        self.assertEqual(closure, DEPLOYMENT_ONLY_STEM)

    def test_deployment_does_not_import_entrypoint(self) -> None:
        imports = _all_import_names(REPO_ROOT / "kismet_eventbus_deployment.py")
        self.assertNotIn("kismet_eventbus_entrypoint", imports)

    def test_entrypoint_closures_no_extra_modules(self) -> None:
        closure = self._closure("kismet_eventbus_entrypoint")
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


# ======================================================================
# Wheel build, install, and import validation
# ======================================================================


class TestWheelBuildInstallValidation(unittest.TestCase):
    """Hermetic wheel build, install, and import contract test.

    Builds the eight-module flat package as a wheel from a temporary source
    copy, validates wheel contents, installs to a temporary target,
    and verifies that all modules import correctly from the installed
    location without side effects.
    """

    def test_wheel_build_install_import_contract(self) -> None:
        """Build, install, import and verify the eight-module package."""
        temporary_root = None
        with tempfile.TemporaryDirectory(prefix="cyt-ng-wheel-") as tmp:
            temporary_root = Path(tmp).resolve()
            self.assertFalse(_is_relative_to(temporary_root, REPO_ROOT))

            source_root = temporary_root / "source"
            wheel_output = temporary_root / "wheel-output"
            install_target = temporary_root / "install-target"
            run_dir = temporary_root / "run"
            home = temporary_root / "home"
            cache = temporary_root / "cache"
            tmpdir = temporary_root / "tmpdir"
            for directory in (
                source_root,
                wheel_output,
                install_target,
                run_dir,
                home,
                cache,
                tmpdir,
            ):
                directory.mkdir()

            _copy_package_source(source_root)
            env = _subprocess_env(home, cache, tmpdir)

            _run_success(
                [
                    sys.executable,
                    "-m",
                    "build",
                    "--wheel",
                    "--no-isolation",
                    "--outdir",
                    str(wheel_output),
                ],
                cwd=source_root,
                env=env,
                timeout=180,
            )

            wheels = sorted(wheel_output.glob("*.whl"))
            self.assertEqual([wheel.name for wheel in wheels], [WHEEL_FILENAME])
            wheel_path = wheels[0]
            _assert_wheel_contract(wheel_path)

            for raw_name, pattern in (
                ("", r"empty archive member name: ''"),
                ("./evil.py", r"dot component in archive member name: './evil\.py'"),
                (
                    "dir//evil.py",
                    r"repeated separator in archive member name: 'dir//evil\.py'",
                ),
                ("C:evil.py", r"drive-like archive member name: 'C:evil\.py'"),
            ):
                with self.assertRaisesRegex(AssertionError, pattern):
                    _assert_raw_archive_member_name(raw_name)

            malformed_name_wheel_path = _copy_wheel_with_malformed_member_name(
                wheel_path,
                temporary_root / "malformed-member-name",
            )
            with self.assertRaisesRegex(
                AssertionError,
                "repeated separator in archive member name: "
                "'chasing_your_tail_ng-0\\.1\\.0\\.dist-info//evil\\.py'",
            ):
                _assert_wheel_contract(malformed_name_wheel_path)

            missing_record_target_wheel_path = _copy_wheel_with_missing_record_target(
                wheel_path,
                temporary_root / "missing-record-target",
            )
            with self.assertRaisesRegex(
                AssertionError,
                "RECORD path missing from wheel: 'missing_from_wheel\\.py'",
            ):
                _assert_wheel_contract(missing_record_target_wheel_path)

            duplicate_wheel_path = _copy_wheel_with_duplicate_member(
                wheel_path,
                temporary_root / "duplicate-member",
            )
            with self.assertRaisesRegex(
                AssertionError,
                f"duplicate wheel member: '{DECLARED_MODULES[0]}\\.py'",
            ):
                _assert_wheel_contract(duplicate_wheel_path)

            extra_directory_wheel_path = _copy_wheel_with_extra_directory(
                wheel_path,
                temporary_root / "extra-directory",
            )
            with self.assertRaisesRegex(
                AssertionError,
                "unexpected wheel directory entry: "
                "'chasing_your_tail_ng-0\\.1\\.0\\.dist-info/unexpected/'",
            ):
                _assert_wheel_contract(extra_directory_wheel_path)

            mutated_wheel_path = temporary_root / WHEEL_FILENAME
            _copy_wheel_with_extra_member(
                wheel_path,
                mutated_wheel_path,
                f"{DIST_INFO_DIR}/evil.py",
                b"raise RuntimeError('dist-info payload must be rejected')\n",
            )
            with self.assertRaisesRegex(
                AssertionError,
                "invalid wheel dist-info positive policy:\nunexpected wheel "
                "dist-info file: chasing_your_tail_ng-0\\.1\\.0\\.dist-info/evil\\.py",
            ):
                _assert_wheel_contract(mutated_wheel_path)

            _run_success(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--no-index",
                    "--no-deps",
                    "--no-compile",
                    "--target",
                    str(install_target),
                    str(wheel_path),
                ],
                cwd=source_root,
                env=env,
                timeout=180,
            )

            _assert_installed_tree(install_target)
            _assert_installed_metadata(install_target)

            extra_dist_info_install = temporary_root / "install-extra-dist-info"
            shutil.copytree(install_target, extra_dist_info_install)
            (
                extra_dist_info_install / DIST_INFO_DIR / "evil.py"
            ).write_text("raise RuntimeError('installed payload')\n")
            with self.assertRaisesRegex(
                AssertionError,
                "invalid installed tree:\nunexpected installed dist-info file: "
                "chasing_your_tail_ng-0\\.1\\.0\\.dist-info/evil\\.py",
            ):
                _assert_installed_tree(extra_dist_info_install)

            symlink_install = temporary_root / "install-symlink-root"
            shutil.copytree(install_target, symlink_install)
            symlink_target = temporary_root / "replacement-root-module.py"
            symlink_target.write_text("# regular file behind rejected symlink\n")
            symlink_module = symlink_install / f"{DECLARED_MODULES[0]}.py"
            symlink_module.unlink()
            symlink_module.symlink_to(symlink_target)
            with self.assertRaisesRegex(
                AssertionError,
                "invalid installed tree:\ninstalled root module is a symbolic link: "
                f"{DECLARED_MODULES[0]}\\.py",
            ):
                _assert_installed_tree(symlink_install)

            import_result = _run_success(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    "-c",
                    _import_probe_script(),
                    str(install_target),
                    str(REPO_ROOT),
                ],
                cwd=run_dir,
                env={
                    "HOME": str(home),
                    "TMPDIR": str(tmpdir),
                    "PATH": os.environ.get("PATH", ""),
                },
                timeout=60,
            )
            self.assertEqual(import_result.stdout, "")
            self.assertEqual(import_result.stderr, "")

        self.assertIsNotNone(temporary_root)
        self.assertFalse(temporary_root.exists())
