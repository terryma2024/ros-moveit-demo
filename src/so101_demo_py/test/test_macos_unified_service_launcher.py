"""Contract tests for the frozen-identity service launcher (remediation Task 7B).

The launcher is the only thing that may build the service's environment. It validates a closed
launch document, re-resolves every frozen identity against the live filesystem and refuses before a
process exists when anything drifted. These tests never start the service: the `execve` boundary is
observed, not crossed.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
LAUNCHER = REPOSITORY_ROOT / "scripts" / "so101_macos_unified_service.py"


def _launcher_module():
    spec = importlib.util.spec_from_file_location("so101_macos_unified_service", LAUNCHER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _absolute_document(tmp_path: Path, module, overrides: dict | None = None) -> dict:
    document = {
        "schema_version": module.LAUNCH_DOCUMENT_SCHEMA_VERSION,
        "case_id": "macos-w2-20",
        "host": "127.0.0.1",
        "port": 8013,
        "evidence_root": str(tmp_path),
        "socket_dir": str(tmp_path / "sockets"),
        "ros_domain_id": 173,
        "install_prefix": "/opt/data/so101/workspace/install",
        "install_inventory_sha256": "a" * 64,
        "web_bundle_sha256": "b" * 64,
        "farm_logical": "/opt/ros2_jazzy/dylib_farm/current",
        "farm_resolved": "/opt/ros2_jazzy/dylib_farm/runs/x",
        "farm_manifest_sha256": "c" * 64,
        "python": "/opt/ros2_jazzy/.venv/bin/python",
        "console_entry": "lib/so101_teleop/so101_unified_web_server.py",
    }
    document.update(overrides or {})
    return document


def test_the_launch_document_is_closed_and_refuses_missing_fields(tmp_path: Path) -> None:
    module = _launcher_module()
    (tmp_path / "sockets").mkdir()

    for missing in ("case_id", "evidence_root", "socket_dir", "install_prefix",
                    "install_inventory_sha256", "web_bundle_sha256", "farm_logical",
                    "farm_resolved", "farm_manifest_sha256", "python", "console_entry"):
        document = _absolute_document(tmp_path, module)
        document.pop(missing)
        path = tmp_path / f"launch-{missing}.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        with pytest.raises(module.LaunchError) as error:
            module.load_launch_document(path)
        assert error.value.code == "LAUNCH_DOCUMENT_INVALID"
        assert error.value.detail == missing

    wrong_schema = _absolute_document(tmp_path, module, {"schema_version": 99})
    path = tmp_path / "launch-schema.json"
    path.write_text(json.dumps(wrong_schema), encoding="utf-8")
    with pytest.raises(module.LaunchError) as error:
        module.load_launch_document(path)
    assert error.value.code == "LAUNCH_DOCUMENT_SCHEMA"


def test_a_valid_document_loads_and_a_bad_port_is_refused(tmp_path: Path) -> None:
    module = _launcher_module()
    (tmp_path / "sockets").mkdir()
    path = tmp_path / "launch.json"
    path.write_text(json.dumps(_absolute_document(tmp_path, module)), encoding="utf-8")

    document = module.load_launch_document(path)

    assert document.case_id == "macos-w2-20"
    assert document.port == 8013
    assert document.host == "127.0.0.1"

    for bad in (0, 70000):
        broken = _absolute_document(tmp_path, module, {"port": bad})
        broken_path = tmp_path / f"launch-port-{bad}.json"
        broken_path.write_text(json.dumps(broken), encoding="utf-8")
        with pytest.raises(module.LaunchError) as error:
            module.load_launch_document(broken_path)
        assert error.value.code == "LAUNCH_DOCUMENT_INVALID"


def test_frozen_identity_drift_is_refused_before_any_process_exists(tmp_path: Path) -> None:
    module = _launcher_module()
    paths = module.RuntimePaths.production(REPOSITORY_ROOT)
    (tmp_path / "sockets").mkdir()
    base = _absolute_document(tmp_path, module)
    live_farm = paths.dylib_farm.resolve(strict=True)

    valid = {
        **base,
        "install_prefix": str(paths.project_install),
        "farm_logical": str(paths.dylib_farm),
        "farm_resolved": str(live_farm),
        "python": str(paths.python),
        "install_inventory_sha256": module._directory_inventory_sha256(paths.project_install),
        "web_bundle_sha256": module._directory_inventory_sha256(
            module.installed_web_bundle(paths.project_install)),
    }
    entries = [
        {"name": entry.name, "resolved": str(entry.resolve(strict=True)),
         "size": entry.resolve(strict=True).stat().st_size}
        for entry in sorted(paths.dylib_farm.iterdir(), key=lambda item: item.name)
        if entry.name.endswith(".dylib")
    ]
    import hashlib

    valid["farm_manifest_sha256"] = hashlib.sha256(
        json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    document = module.ServiceLaunchDocument(**valid)
    identities = module.verify_frozen_identities(document, paths)
    assert identities["console_entry"].endswith(module.CONSOLE_ENTRY_RELATIVE_PATH)

    for field, code in (
        ("farm_resolved", "FARM_RESOLVED_DRIFT"),
        ("farm_manifest_sha256", "FARM_MANIFEST_DRIFT"),
        ("install_inventory_sha256", "INSTALL_INVENTORY_DRIFT"),
        ("web_bundle_sha256", "WEB_BUNDLE_DRIFT"),
        ("python", "PYTHON_DRIFT"),
        ("install_prefix", "INSTALL_PREFIX_DRIFT"),
        ("farm_logical", "FARM_LOGICAL_DRIFT"),
    ):
        drifted = {**valid, field: "gone" if field.endswith("prefix") or field == "python"
                   else "0" * 64}
        with pytest.raises(module.LaunchError) as error:
            module.verify_frozen_identities(
                module.ServiceLaunchDocument(**drifted), paths)
        assert error.value.code == code, field


def test_the_child_environment_pins_the_contract_and_the_service_parameters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _launcher_module()
    paths = module.RuntimePaths.production(REPOSITORY_ROOT)
    (tmp_path / "sockets").mkdir()
    document = module.ServiceLaunchDocument(**_absolute_document(tmp_path, module))
    monkeypatch.setenv("AMENT_PREFIX_PATH", "/sourced/prefix")
    monkeypatch.setenv("SO101_UNIFIED_EVIDENCE_ROOT", "/somebody/elses/root")
    monkeypatch.setenv("NODE_ENV", "development")

    environment = module.child_environment(document, paths)

    assert environment["AMENT_PREFIX_PATH"] == "/sourced/prefix"
    assert environment["DYLD_LIBRARY_PATH"] == str(paths.dylib_farm)
    assert environment["ROS_DOMAIN_ID"] == "173"
    assert environment["TMPDIR"] == str(paths.temp_root)
    assert environment["SO101_UNIFIED_EVIDENCE_ROOT"] == str(tmp_path)
    assert environment["SO101_UNIFIED_SOCKET_DIR"] == str(tmp_path / "sockets")
    assert environment["SO101_UNIFIED_INSTALL_PREFIX"] == str(paths.project_install)
    assert environment["SO101_UNIFIED_HOST"] == "127.0.0.1"
    assert environment["SO101_UNIFIED_PORT"] == "8013"
    assert environment["SO101_LIVE_CASE_ID"] == "macos-w2-20"
    assert "NODE_ENV" not in environment
