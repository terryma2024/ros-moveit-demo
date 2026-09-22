#!/usr/bin/env python3
"""Launch the installed unified service from a frozen launch document.

The service that a live acceptance window starts must be reproducible: the same install prefix, the
same farm target, the same interpreter and the same state roots, with nothing inherited from the
operator's shell. This launcher is the only entry that builds that environment.

It validates ``service-launch.json`` against a closed schema, re-resolves every frozen identity
against the live filesystem (farm logical path, farm resolved target, farm manifest bytes, install
inventory, Web bundle), writes the child receipt with the values the child really received, and then
``exec``s the installed console entry. It never sources a shell that would clear the service
parameters, and it refuses rather than falling back to an inherited environment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIRECTORY.parent
sys.path.insert(0, str(SCRIPT_DIRECTORY))

from so101_macos_runtime_contract import (  # noqa: E402 - the script directory is ours
    RuntimeContractError,
    RuntimePaths,
    build_runtime_environment,
)

LAUNCH_DOCUMENT_SCHEMA_VERSION = 1
RECEIPT_SCHEMA_VERSION = 1
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8013
CONSOLE_ENTRY_RELATIVE_PATH = "lib/so101_teleop/so101_unified_web_server.py"


class LaunchError(RuntimeError):
    """Fail-closed launcher error carrying a stable machine-readable code."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True, slots=True)
class ServiceLaunchDocument:
    schema_version: int
    case_id: str
    host: str
    port: int
    evidence_root: str
    socket_dir: str
    ros_domain_id: int
    install_prefix: str
    install_inventory_sha256: str
    web_bundle_sha256: str
    farm_logical: str
    farm_resolved: str
    farm_manifest_sha256: str
    python: str
    console_entry: str
    validation_parallel_config: str = ""


def _require(mapping: dict[str, Any], key: str, code: str = "LAUNCH_DOCUMENT_INVALID") -> Any:
    value = mapping.get(key)
    if value in (None, ""):
        raise LaunchError(code, key)
    return value


def load_launch_document(path: Path) -> ServiceLaunchDocument:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as error:
        raise LaunchError("LAUNCH_DOCUMENT_MISSING", str(path)) from error
    except json.JSONDecodeError as error:
        raise LaunchError("LAUNCH_DOCUMENT_INVALID", str(path)) from error
    if not isinstance(document, dict):
        raise LaunchError("LAUNCH_DOCUMENT_INVALID", "not an object")
    if document.get("schema_version") != LAUNCH_DOCUMENT_SCHEMA_VERSION:
        raise LaunchError("LAUNCH_DOCUMENT_SCHEMA", str(document.get("schema_version")))
    port = int(_require(document, "port"))
    if not 1 <= port <= 65535:
        raise LaunchError("LAUNCH_DOCUMENT_INVALID", "port")
    domain = int(document.get("ros_domain_id", 0))
    if not 0 <= domain <= 232:
        raise LaunchError("LAUNCH_DOCUMENT_INVALID", "ros_domain_id")
    return ServiceLaunchDocument(
        schema_version=LAUNCH_DOCUMENT_SCHEMA_VERSION,
        case_id=str(_require(document, "case_id")),
        host=str(document.get("host") or DEFAULT_HOST),
        port=port,
        evidence_root=str(_require(document, "evidence_root")),
        socket_dir=str(_require(document, "socket_dir")),
        ros_domain_id=domain,
        install_prefix=str(_require(document, "install_prefix")),
        install_inventory_sha256=str(_require(document, "install_inventory_sha256")),
        web_bundle_sha256=str(_require(document, "web_bundle_sha256")),
        farm_logical=str(_require(document, "farm_logical")),
        farm_resolved=str(_require(document, "farm_resolved")),
        farm_manifest_sha256=str(_require(document, "farm_manifest_sha256")),
        python=str(_require(document, "python")),
        console_entry=str(_require(document, "console_entry")),
        validation_parallel_config=str(document.get("validation_parallel_config") or ""),
    )


def _directory_inventory_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for entry in sorted(root.rglob("*")):
        relative = entry.relative_to(root).as_posix()
        if entry.is_symlink():
            digest.update(f"L{relative}\0{os.readlink(entry)}\n".encode())
        elif entry.is_dir():
            digest.update(f"D{relative}\n".encode())
        elif entry.is_file():
            digest.update(f"F{relative}\0{hashlib.sha256(entry.read_bytes()).hexdigest()}\n".encode())
    return digest.hexdigest()


def installed_web_bundle(prefix: Path) -> Path | None:
    """The bundle in either installed layout: merged `share/` or a package subdirectory."""

    for candidate in (
        Path(prefix) / "share/so101_teleop/web",
        Path(prefix) / "so101_teleop/share/so101_teleop/web",
    ):
        if candidate.is_dir():
            return candidate
    return None


def installed_console_entry(prefix: Path, relative_path: str) -> Path | None:
    """The console entry in either installed layout; `lib/...` is the merged one."""

    for candidate in (
        Path(prefix) / relative_path,
        Path(prefix) / "so101_teleop" / relative_path,
    ):
        if candidate.is_file():
            return candidate
    return None


def verify_frozen_identities(
    document: ServiceLaunchDocument, paths: RuntimePaths
) -> dict[str, object]:
    """Re-resolve every frozen identity; any drift refuses before a process exists."""

    if str(paths.project_install) != document.install_prefix:
        raise LaunchError("INSTALL_PREFIX_DRIFT", str(paths.project_install))
    if str(paths.dylib_farm) != document.farm_logical:
        raise LaunchError("FARM_LOGICAL_DRIFT", str(paths.dylib_farm))
    try:
        resolved = paths.dylib_farm.resolve(strict=True)
    except OSError as error:
        raise LaunchError("FARM_MISSING", str(paths.dylib_farm)) from error
    if str(resolved) != document.farm_resolved:
        raise LaunchError("FARM_RESOLVED_DRIFT", str(resolved))
    farm_entries = [
        {
            "name": entry.name,
            "resolved": str(entry.resolve(strict=True)),
            "size": entry.resolve(strict=True).stat().st_size,
        }
        for entry in sorted(paths.dylib_farm.iterdir(), key=lambda item: item.name)
        if entry.name.endswith(".dylib")
    ]
    farm_manifest_sha256 = hashlib.sha256(
        json.dumps(farm_entries, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if farm_manifest_sha256 != document.farm_manifest_sha256:
        raise LaunchError("FARM_MANIFEST_DRIFT", farm_manifest_sha256)
    inventory_sha256 = _directory_inventory_sha256(paths.project_install)
    if inventory_sha256 != document.install_inventory_sha256:
        raise LaunchError("INSTALL_INVENTORY_DRIFT", inventory_sha256)
    bundle = installed_web_bundle(paths.project_install)
    if bundle is None:
        raise LaunchError("WEB_BUNDLE_MISSING", str(paths.project_install))
    web_bundle_sha256 = _directory_inventory_sha256(bundle)
    if web_bundle_sha256 != document.web_bundle_sha256:
        raise LaunchError("WEB_BUNDLE_DRIFT", web_bundle_sha256)
    console_entry = installed_console_entry(paths.project_install, document.console_entry)
    if console_entry is None:
        raise LaunchError(
            "CONSOLE_ENTRY_MISSING",
            str(paths.project_install / document.console_entry),
        )
    if str(paths.python) != document.python:
        raise LaunchError("PYTHON_DRIFT", str(paths.python))
    for directory in (document.evidence_root, document.socket_dir):
        candidate = Path(directory)
        if not candidate.is_absolute() or not candidate.is_dir():
            raise LaunchError("LAUNCH_DOCUMENT_INVALID", directory)
    return {
        "farm_manifest_sha256": farm_manifest_sha256,
        "install_inventory_sha256": inventory_sha256,
        "web_bundle_sha256": web_bundle_sha256,
        "console_entry": str(console_entry),
        "console_entry_relative_path": document.console_entry,
    }


def child_environment(
    document: ServiceLaunchDocument, paths: RuntimePaths
) -> dict[str, str]:
    """The sourced ROS environment with the fixed baseline and the service parameters pinned.

    The runner sources the four validated setups first, so the child keeps exactly those prefixes;
    the fixed contract keys (HOME, PATH, TMPDIR/ROS_*, the farm-derived DYLD_LIBRARY_PATH) are then
    written *over* whatever the shell had, and the service parameters are added last. Nothing else
    is invented here and nothing is silently dropped.
    """

    environment: dict[str, str] = {
        key: value for key, value in os.environ.items() if isinstance(value, str)
    }
    environment.update(build_runtime_environment(paths, ros_domain_id=document.ros_domain_id))
    environment.update(
        {
            "SO101_UNIFIED_EVIDENCE_ROOT": document.evidence_root,
            "SO101_UNIFIED_SOCKET_DIR": document.socket_dir,
            "SO101_UNIFIED_ROS_PYTHON": document.python,
            "SO101_UNIFIED_INSTALL_PREFIX": document.install_prefix,
            "SO101_UNIFIED_HOST": document.host,
            "SO101_UNIFIED_PORT": str(document.port),
            "SO101_LIVE_CASE_ID": document.case_id,
        }
    )
    # The macOS capabilities document is only served when the service can read an execution profile:
    # `_execution_document()` reads `layout.parallel_config_path`, which comes from
    # SO101_VALIDATION_PARALLEL_CONFIG. Without it the default v1 document is used and the
    # capabilities answer has `platform: null`, which is what every W2 window saw.
    if getattr(document, "validation_parallel_config", ""):
        environment["SO101_VALIDATION_PARALLEL_CONFIG"] = document.validation_parallel_config
    # The perception weights are operator inputs, not repository content, and the layout reads them
    # from SO101_VALIDATION_YOLO_WEIGHTS / SO101_VALIDATION_GROUNDED_ROOT with no default. Whatever
    # the window exported is passed through rather than guessed; the declared profile still wins.
    for key, value in os.environ.items():
        if key.startswith("SO101_VALIDATION_") and key != "SO101_VALIDATION_PARALLEL_CONFIG":
            environment.setdefault(key, value)
    environment.pop("NODE_ENV", None)
    return environment


def _atomic_write_json(path: Path, document: dict[str, object]) -> str:
    encoded = json.dumps(document, indent=2, sort_keys=True).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    return hashlib.sha256(encoded).hexdigest()


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="so101_macos_unified_service")
    parser.add_argument("--launch-document", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    options = parse_arguments(argv)
    paths = RuntimePaths.production(REPOSITORY_ROOT)
    try:
        document = load_launch_document(options.launch_document)
        identities = verify_frozen_identities(document, paths)
        environment = child_environment(document, paths)
    except (LaunchError, RuntimeContractError) as error:
        print(json.dumps({"status": "REFUSED", "code": getattr(error, "code", "LAUNCH_FAILED"),
                          "detail": getattr(error, "detail", str(error))}, sort_keys=True))
        return 2
    # Every entry of AMENT_PREFIX_PATH is resolved before it is compared, and each root only has to
    # be *represented*: this host's ROS install is an isolated install, so its 692 entries name
    # `<root>/<package>` and never the bare root. Demanding the bare roots refused a correctly
    # sourced environment with OVERLAY_NOT_SOURCED.
    ament_entries = []
    for entry in environment.get("AMENT_PREFIX_PATH", "").split(os.pathsep):
        if not entry:
            continue
        try:
            ament_entries.append(Path(entry).resolve())
        except OSError:
            continue
    for required_prefix in (
        str(paths.ros_install),
        str(paths.ros_dependency_overlay),
        str(paths.ros_fork_overlay),
        str(paths.project_install),
    ):
        root = Path(required_prefix).resolve()
        if not any(entry == root or entry.is_relative_to(root) for entry in ament_entries):
            print(json.dumps({"status": "REFUSED", "code": "OVERLAY_NOT_SOURCED",
                              "detail": required_prefix}, sort_keys=True))
            return 2
    receipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "status": "EXEC",
        "case_id": document.case_id,
        "pid": os.getpid(),
        "argv": [document.python, str(identities["console_entry"])],
        "child_environment": {key: environment[key] for key in sorted(environment)},
        "identities": identities,
        "launch_document": str(options.launch_document),
    }
    _atomic_write_json(options.receipt, receipt)
    # The four overlays are sourced by the runner before this module is imported; this process
    # execs the verified console entry directly so no shell can drop the service parameters.
    os.execve(document.python, [document.python, str(identities["console_entry"])], environment)
    return 0  # pragma: no cover - execve never returns


if __name__ == "__main__":  # pragma: no cover - console entry
    raise SystemExit(main())
