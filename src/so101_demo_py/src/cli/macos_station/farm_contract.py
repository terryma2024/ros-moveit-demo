"""The fixed dylib farm contract, its inventory and report."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path

from so101_demo.cli.macos_station.contracts import FARM_CLOSURE_PREFIXES, StationDiagnosticError
from so101_demo.cli.macos_station.diagnostic_run import _atomic_write_json


@dataclass(frozen=True, slots=True)
class FixedFarmRuntimePaths:
    """The fixed /opt runtime contract as the farm diagnostic sees it."""

    ros_root: Path
    ros_install: Path
    ros_dependency_overlay: Path
    ros_fork_overlay: Path
    python: Path
    ros2_script: Path
    data_root: Path
    temp_root: Path
    dylib_farm: Path
    project_install: Path
    runtime_home: Path
    ros_home: Path
    ros_log_dir: Path

    @classmethod
    def production(cls) -> "FixedFarmRuntimePaths":
        ros_root = Path("/opt/ros/jazzy")
        runtime_root = Path("/opt/data/so101")
        data_root = Path("/opt/data")
        return cls(
            ros_root=ros_root,
            ros_install=ros_root / "install",
            ros_dependency_overlay=ros_root / "extra_ws/install",
            ros_fork_overlay=runtime_root / "runtime/fork/current",
            python=ros_root / ".venv/bin/python",
            ros2_script=ros_root / "install/ros2cli/bin/ros2",
            data_root=data_root,
            temp_root=data_root / "tmp",
            dylib_farm=ros_root / "dylib_farm/current",
            project_install=runtime_root / "workspace/install",
            runtime_home=runtime_root / "home",
            ros_home=runtime_root / "ros-home",
            ros_log_dir=runtime_root / "ros-logs",
        )

    def environment(self, ros_domain_id: int) -> dict[str, str]:
        """The baseline child environment: every value is constructed here, none inherited."""

        return {
            "HOME": str(self.runtime_home),
            "PATH": os.pathsep.join(
                (
                    str(self.python.parent),
                    "/opt/homebrew/opt/ffmpeg-full/bin",
                    "/opt/homebrew/opt/llvm/bin",
                    "/opt/homebrew/opt/coreutils/libexec/gnubin",
                    "/opt/homebrew/opt/gnu-sed/libexec/gnubin",
                    "/opt/homebrew/bin",
                    "/usr/bin",
                    "/bin",
                    "/usr/sbin",
                    "/sbin",
                )
            ),
            "VIRTUAL_ENV": str(self.python.parents[1]),
            "GZ_CONFIG_PATH": os.pathsep.join(
                f"/opt/homebrew/opt/{package}/share/gz"
                for package in (
                    "gz-sim8", "gz-transport13", "gz-msgs10", "gz-plugin2", "sdformat14"
                )
            ),
            "PYTHONNOUSERSITE": "1",
            "TMPDIR": str(self.temp_root),
            "TMP": str(self.temp_root),
            "TEMP": str(self.temp_root),
            "ROS_HOME": str(self.ros_home),
            "ROS_LOG_DIR": str(self.ros_log_dir),
            "ROS_DOMAIN_ID": str(int(ros_domain_id)),
            "DYLD_LIBRARY_PATH": str(self.dylib_farm),
            "GZ_SIM_SYSTEM_PLUGIN_PATH": os.pathsep.join(
                (
                    str(self.ros_dependency_overlay / "lib"),
                    str(self.project_install / "so101_gazebo_demo_cpp/lib"),
                )
            ),
        }


@dataclass(frozen=True, slots=True)
class FixedDylibFarmContract:
    """The frozen farm identity a round has to stay inside."""

    receipt_path: Path
    receipt_sha256: str
    dylib_farm_logical: Path
    dylib_farm_resolved: Path
    dylib_farm_manifest_sha256: str
    project_install: Path
    closure_prefixes: tuple[str, ...]

    @property
    def dylib_farm_root(self) -> str:
        return str(self.dylib_farm_logical)

    def as_document(self) -> dict[str, object]:
        return {
            "receipt_path": str(self.receipt_path),
            "receipt_sha256": self.receipt_sha256,
            "dylib_farm_logical": str(self.dylib_farm_logical),
            "dylib_farm_resolved": str(self.dylib_farm_resolved),
            "dylib_farm_manifest_sha256": self.dylib_farm_manifest_sha256,
            "project_install": str(self.project_install),
            "closure_prefixes": list(self.closure_prefixes),
        }


def _farm_library_inventory(farm: Path) -> tuple[list[dict[str, object]], str]:
    entries: list[dict[str, object]] = []
    for library in sorted(farm.iterdir(), key=lambda item: item.name):
        if not library.name.endswith(".dylib"):
            continue
        resolved = library.resolve(strict=True)
        if not resolved.is_file():
            raise StationDiagnosticError("FARM_ENTRY_INVALID", str(library))
        entries.append(
            {
                "name": library.name,
                "resolved": str(resolved),
                "size": resolved.stat().st_size,
            }
        )
    encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    return entries, hashlib.sha256(encoded).hexdigest()


def load_fixed_dylib_farm_contract(receipt_path: Path) -> FixedDylibFarmContract:
    """Re-resolve the receipt against the live farm; any drift fails closed before a spawn."""

    path = Path(receipt_path)
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise StationDiagnosticError("FARM_RECEIPT_MISSING", str(path)) from error
    try:
        receipt = json.loads(raw)
    except json.JSONDecodeError as error:
        raise StationDiagnosticError("FARM_RECEIPT_INVALID", str(path)) from error
    if not isinstance(receipt, dict) or receipt.get("level") != "complete":
        raise StationDiagnosticError("FARM_RECEIPT_INVALID", "level")
    farm = receipt.get("dylib_farm")
    install = receipt.get("project_install")
    if not isinstance(farm, dict) or not isinstance(install, dict):
        raise StationDiagnosticError("FARM_RECEIPT_INVALID", "dylib_farm/project_install")
    logical = Path(str(farm.get("logical")))
    declared_prefixes = farm.get("closure_prefixes", receipt.get("closure_prefixes"))
    if declared_prefixes is None:
        prefixes = FARM_CLOSURE_PREFIXES
    elif isinstance(declared_prefixes, list) and all(
        isinstance(prefix, str) and Path(prefix).is_absolute()
        for prefix in declared_prefixes
    ):
        # A negative-control or fixture receipt may declare its own sanctioned prefixes.
        prefixes = tuple(str(prefix) for prefix in declared_prefixes)
    else:
        raise StationDiagnosticError("FARM_RECEIPT_INVALID", "closure_prefixes")
    if not any(logical.is_relative_to(Path(prefix)) for prefix in prefixes):
        raise StationDiagnosticError("FARM_LOGICAL_PATH_DRIFT", str(logical))
    try:
        resolved = logical.resolve(strict=True)
    except OSError as error:
        raise StationDiagnosticError("FARM_MISSING", str(logical)) from error
    if str(resolved) != str(farm.get("resolved")):
        raise StationDiagnosticError(
            "FARM_RESOLVED_TARGET_DRIFT", f"{resolved} != {farm.get('resolved')}"
        )
    _entries, manifest_sha256 = _farm_library_inventory(logical)
    if manifest_sha256 != str(farm.get("manifest_sha256")):
        raise StationDiagnosticError(
            "FARM_MANIFEST_DRIFT",
            f"{manifest_sha256} != {farm.get('manifest_sha256')}",
        )
    project_install = Path(str(install.get("resolved") or install.get("logical")))
    return FixedDylibFarmContract(
        receipt_path=path,
        receipt_sha256=hashlib.sha256(raw).hexdigest(),
        dylib_farm_logical=logical,
        dylib_farm_resolved=resolved,
        dylib_farm_manifest_sha256=manifest_sha256,
        project_install=project_install,
        closure_prefixes=prefixes,
    )


def _farm_round_binding(
    contract: FixedDylibFarmContract, binding_path: Path
) -> dict[str, object]:
    path = Path(binding_path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise StationDiagnosticError("FARM_RUN_BINDING_MISSING", str(path)) from error
    except json.JSONDecodeError as error:
        raise StationDiagnosticError("FARM_RUN_BINDING_INVALID", str(path)) from error
    if not isinstance(document, dict):
        raise StationDiagnosticError("FARM_RUN_BINDING_INVALID", "not an object")
    if document.get("farm_contract_sha256") != contract.receipt_sha256:
        raise StationDiagnosticError("FARM_RUN_BINDING_RECEIPT_MISMATCH", str(path))
    for key, expected in (
        ("farm_logical", str(contract.dylib_farm_logical)),
        ("farm_resolved", str(contract.dylib_farm_resolved)),
        ("farm_manifest_sha256", contract.dylib_farm_manifest_sha256),
    ):
        if document.get(key) != expected:
            raise StationDiagnosticError("FARM_RUN_BINDING_DRIFT", key)
    for key in ("round_id", "session_id", "ros_domain_id", "task_evidence_root", "scene_path"):
        if document.get(key) in (None, ""):
            raise StationDiagnosticError("FARM_RUN_BINDING_INVALID", key)
    domain_id = int(document["ros_domain_id"])  # type: ignore[arg-type]
    if not 0 <= domain_id <= 232:
        raise StationDiagnosticError("FARM_RUN_BINDING_INVALID", "ros_domain_id")
    return document


def _write_farm_report(output_path: Path, report: dict[str, object]) -> str:
    """Write the report with a body digest, then return that digest."""

    body = {key: value for key, value in report.items() if key != "report_sha256"}
    digest = hashlib.sha256(
        json.dumps(body, indent=2, sort_keys=True).encode("utf-8")
    ).hexdigest()
    document = {**body, "report_sha256": digest}
    _atomic_write_json(output_path, document)
    return digest


def _owner_ancestry(
    rows: Sequence[tuple[int, int, str]],
    *,
    root_pid: int,
    root_role: str,
    root_birth_identity: int,
    root_executable: str,
    target_pid: int,
    target_birth_identity: int,
    target_executable: str,
):
    """Reconstruct the owner chain from the launch root down to the controller child."""

    from so101_demo.runtime.runtime_closure.identities import ProcessIdentity

    parents = {row[0]: row[1] for row in rows}
    chain: list[int] = [target_pid]
    while chain[-1] != root_pid:
        parent = parents.get(chain[-1])
        if parent is None or parent in chain:
            raise StationDiagnosticError(
                "STATION_CONTROLLER_PROCESS_UNBOUND", f"{target_pid} is not a child of {root_pid}"
            )
        chain.append(parent)
    chain.reverse()
    identities = [
        ProcessIdentity(
            role=root_role,
            pid=root_pid,
            parent_pid=os.getppid(),
            birth_identity=root_birth_identity,
            executable=root_executable,
        )
    ]
    for pid in chain[1:-1]:
        identities.append(
            ProcessIdentity(
                role="task_station_launcher",
                pid=pid,
                parent_pid=parents[pid],
                birth_identity=-1,
                executable="unknown",
            )
        )
    identities.append(
        ProcessIdentity(
            role="controller_runtime",
            pid=target_pid,
            parent_pid=parents[target_pid],
            birth_identity=target_birth_identity,
            executable=target_executable,
        )
    )
    return tuple(identities)
