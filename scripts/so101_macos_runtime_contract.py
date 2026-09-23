#!/usr/bin/env python3
"""Validate the fixed Apple Silicon ROS 2 runtime used by SO-101."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence


REQUIRED_EXTERNAL_ENVIRONMENT: tuple[str, ...] = ()
#: The authorized fixed dylib farm contract (design section 17): the five prefixes every
#: runtime artifact has to be attributable to, and the two images an A2 round attests.
FIXED_CLOSURE_PREFIXES = (
    "/opt/ros/jazzy/install",
    "/opt/ros/jazzy/extra_ws/install",
    "/opt/data/so101/runtime/fork/current",
    "/opt/data/so101/workspace/install",
    "/opt/ros/jazzy/dylib_farm/current",
)
FIXED_DYLIB_FARM_CONTRACT_SCHEMA_VERSION = 1
CONTROLLER_RUNTIME_RELATIVE_PATH = "lib/mujoco_ros2_control/ros2_control_node"
PLUGIN_BASENAME = "libmujoco_ros2_control.dylib"
VENDOR_BASENAME = "libmujoco.3.4.0.dylib"

REQUIRED_DYLIBS = (
    "libcontrol_toolbox.dylib",
    "libhardware_interface.dylib",
    "librosidl_typesupport_c.dylib",
)
REQUIRED_PACKAGES = (
    "control_toolbox",
    "controller_manager",
    "hardware_interface",
    "mujoco_ros2_control",
    "mujoco_vendor",
    "so101_demo_py",
    "so101_mujoco_support",
    "so101_teleop",
    "transmission_interface",
)


class RuntimeContractError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    repository_root: Path
    ros_root: Path
    ros_install: Path
    ros_dependency_overlay: Path
    ros_fork_overlay: Path
    python: Path
    colcon: Path
    ros2_script: Path
    data_root: Path
    temp_root: Path
    dylib_farm: Path
    project_install: Path
    runtime_home: Path
    ros_home: Path
    ros_log_dir: Path

    @classmethod
    def production(cls, repository_root: Path) -> "RuntimePaths":
        return cls.from_filesystem_root(
            filesystem_root=Path("/"), repository_root=repository_root
        )

    @classmethod
    def from_filesystem_root(
        cls, *, filesystem_root: Path, repository_root: Path
    ) -> "RuntimePaths":
        root = Path(filesystem_root)
        repository = Path(repository_root).resolve()
        ros_root = root / "opt/ros/jazzy"
        data_root = root / "opt/data"
        temp_root = data_root / "tmp"
        runtime_root = data_root / "so101"
        project_install = runtime_root / "workspace/install"
        return cls(
            repository_root=repository,
            ros_root=ros_root,
            ros_install=ros_root / "install",
            ros_dependency_overlay=ros_root / "extra_ws/install",
            ros_fork_overlay=runtime_root / "runtime/fork/current",
            python=ros_root / ".venv/bin/python",
            colcon=ros_root / ".venv/bin/colcon",
            ros2_script=ros_root / "install/ros2cli/bin/ros2",
            data_root=data_root,
            temp_root=temp_root,
            dylib_farm=ros_root / "dylib_farm/current",
            project_install=project_install,
            runtime_home=runtime_root / "home",
            ros_home=runtime_root / "ros-home",
            ros_log_dir=runtime_root / "ros-logs",
        )

    @property
    def setup_files(self) -> tuple[Path, ...]:
        return (
            self.ros_install / "setup.zsh",
            self.ros_dependency_overlay / "setup.zsh",
            self.ros_fork_overlay / "local_setup.zsh",
            self.project_install / "local_setup.zsh",
        )


def _path_identity(path: Path) -> dict[str, str]:
    return {"logical": str(path), "resolved": str(path.resolve(strict=True))}


def _require_directory(path: Path, code: str) -> None:
    if not path.is_dir():
        raise RuntimeContractError(code, str(path))


def _require_file(path: Path, code: str) -> None:
    if not path.is_file():
        raise RuntimeContractError(code, str(path))


def _require_executable(path: Path, code: str) -> None:
    _require_file(path, code)
    if not os.access(path, os.X_OK):
        raise RuntimeContractError(code, f"not executable: {path}")


def _default_python_probe(python: Path) -> dict[str, object]:
    probe = (
        "import json,platform,sys; "
        "print(json.dumps({'executable':sys.executable,"
        "'implementation':platform.python_implementation(),"
        "'version':platform.python_version(),"
        "'version_info':list(sys.version_info[:2])},sort_keys=True))"
    )
    completed = subprocess.run(
        [str(python), "-I", "-c", probe],
        check=False,
        capture_output=True,
        text=True,
        env={
            "PATH": f"{python.parent}:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "PYTHONNOUSERSITE": "1",
        },
    )
    if completed.returncode != 0:
        raise RuntimeContractError(
            "PYTHON_PROBE_FAILED", completed.stderr.strip() or str(python)
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeContractError(
            "PYTHON_PROBE_FAILED", completed.stdout.strip()
        ) from error


def validate_base_contract(
    paths: RuntimePaths,
    *,
    system_name: str | None = None,
    machine: str | None = None,
    python_probe: Callable[[Path], dict[str, object]] = _default_python_probe,
) -> dict[str, object]:
    observed_system = system_name or platform.system()
    observed_machine = machine or platform.machine()
    if observed_system != "Darwin":
        raise RuntimeContractError("UNSUPPORTED_SYSTEM", observed_system)
    if observed_machine != "arm64":
        raise RuntimeContractError("UNSUPPORTED_ARCHITECTURE", observed_machine)

    if not paths.ros_root.exists():
        raise RuntimeContractError("ROS_ROOT_MISSING", str(paths.ros_root))
    _require_directory(paths.ros_root, "ROS_ROOT_MISSING")
    _require_directory(paths.ros_install, "ROS_INSTALL_MISSING")
    _require_directory(paths.ros_dependency_overlay, "ROS_DEPENDENCY_OVERLAY_MISSING")
    for setup_file in paths.setup_files[:2]:
        _require_file(setup_file, "ROS_SETUP_MISSING")
    _require_executable(paths.python, "ROS_PYTHON_INVALID")
    _require_executable(paths.colcon, "COLCON_INVALID")
    _require_file(paths.ros2_script, "ROS2_CLI_MISSING")
    _require_directory(paths.data_root, "DATA_ROOT_MISSING")
    _require_directory(paths.temp_root, "TEMP_ROOT_MISSING")
    for writable_path, code in (
        (paths.data_root, "DATA_ROOT_NOT_WRITABLE"),
        (paths.temp_root, "TEMP_ROOT_NOT_WRITABLE"),
    ):
        if not os.access(writable_path, os.W_OK | os.X_OK):
            raise RuntimeContractError(code, str(writable_path))

    python_identity = python_probe(paths.python)
    if python_identity.get("implementation") != "CPython" or python_identity.get(
        "version_info"
    ) != [3, 11]:
        raise RuntimeContractError(
            "PYTHON_ABI_MISMATCH", json.dumps(python_identity, sort_keys=True)
        )

    return {
        "status": "PASS",
        "level": "base",
        "platform": {"system": observed_system, "machine": observed_machine},
        "paths": {
            "ros_root": _path_identity(paths.ros_root),
            "ros_install": _path_identity(paths.ros_install),
            "data_root": _path_identity(paths.data_root),
            "temp_root": _path_identity(paths.temp_root),
        },
        "python": python_identity,
        "required_external_environment": list(REQUIRED_EXTERNAL_ENVIRONMENT),
    }


def build_runtime_environment(
    paths: RuntimePaths,
    *,
    inherited: Mapping[str, str] | None = None,
    ros_domain_id: object = 0,
) -> dict[str, str]:
    del inherited
    try:
        domain_id = int(ros_domain_id)
    except (TypeError, ValueError) as error:
        raise RuntimeContractError(
            "ROS_DOMAIN_ID_INVALID", str(ros_domain_id)
        ) from error
    if str(domain_id) != str(ros_domain_id) or not 0 <= domain_id <= 232:
        raise RuntimeContractError("ROS_DOMAIN_ID_INVALID", str(ros_domain_id))

    return {
        "HOME": str(paths.runtime_home),
        "PATH": os.pathsep.join(
            (
                str(paths.python.parent),
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
        "VIRTUAL_ENV": str(paths.python.parents[1]),
        "GZ_CONFIG_PATH": os.pathsep.join(
            f"/opt/homebrew/opt/{package}/share/gz"
            for package in (
                "gz-sim8", "gz-transport13", "gz-msgs10", "gz-plugin2", "sdformat14"
            )
        ),
        "PYTHONNOUSERSITE": "1",
        "TMPDIR": str(paths.temp_root),
        "TMP": str(paths.temp_root),
        "TEMP": str(paths.temp_root),
        "ROS_HOME": str(paths.ros_home),
        "ROS_LOG_DIR": str(paths.ros_log_dir),
        "ROS_DOMAIN_ID": str(domain_id),
        "DYLD_LIBRARY_PATH": str(paths.dylib_farm),
        "GZ_SIM_SYSTEM_PLUGIN_PATH": os.pathsep.join(
            (
                str(paths.ros_dependency_overlay / "lib"),
                str(paths.project_install / "so101_gazebo_demo_cpp/lib"),
            )
        ),
    }


def build_ros_command(paths: RuntimePaths, arguments: Sequence[str]) -> list[str]:
    if len(arguments) < 2 or arguments[0] not in {"launch", "run"}:
        raise RuntimeContractError(
            "ROS_COMMAND_INVALID", "expected: launch|run PACKAGE ..."
        )
    return [str(paths.python), str(paths.ros2_script), *arguments]


def _farm_manifest(paths: RuntimePaths) -> dict[str, object]:
    _require_directory(paths.dylib_farm, "DYLIB_FARM_MISSING")
    entries: list[dict[str, object]] = []
    for library in sorted(paths.dylib_farm.iterdir(), key=lambda item: item.name):
        if not library.name.endswith(".dylib"):
            continue
        try:
            resolved = library.resolve(strict=True)
        except OSError as error:
            raise RuntimeContractError("DYLIB_FARM_BROKEN_LINK", str(library)) from error
        if not resolved.is_file():
            raise RuntimeContractError("DYLIB_FARM_ENTRY_INVALID", str(library))
        entries.append(
            {
                "name": library.name,
                "resolved": str(resolved),
                "size": resolved.stat().st_size,
            }
        )
    names = {entry["name"] for entry in entries}
    for required in REQUIRED_DYLIBS:
        if required not in names:
            raise RuntimeContractError("DYLIB_MISSING", required)
    encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    return {
        "logical": str(paths.dylib_farm),
        "resolved": str(paths.dylib_farm.resolve(strict=True)),
        "library_count": len(entries),
        "manifest_sha256": hashlib.sha256(encoded).hexdigest(),
        "required": list(REQUIRED_DYLIBS),
        # The receipt carries the sanctioned prefixes itself, so a round can freeze the
        # contract it was validated against instead of re-deriving it later.
        "closure_prefixes": list(FIXED_CLOSURE_PREFIXES),
    }


def _run_complete_probe(paths: RuntimePaths, domain_id: int) -> dict[str, object]:
    environment = build_runtime_environment(
        paths, inherited=os.environ, ros_domain_id=domain_id
    )
    probe_code = "\n".join(
        (
            "import ctypes,json,os,rclpy",
            f"libraries={json.dumps([str(paths.dylib_farm / name) for name in REQUIRED_DYLIBS])}",
            "loaded=[lib for lib in libraries if ctypes.CDLL(lib, mode=os.RTLD_LOCAL|os.RTLD_NOW)]",
            "print(json.dumps({'rclpy':rclpy.__file__,'loaded':loaded},sort_keys=True))",
        )
    )
    setup_arguments = [str(path) for path in paths.setup_files]
    shell_program = r'''
set -eo pipefail
python_path="$1"
ros2_script="$2"
probe_code="$3"
shift 3
set +u
for setup_file in "$@"; do
  source "$setup_file"
done
set -u
export DYLD_LIBRARY_PATH="${SO101_FIXED_DYLIB_FARM}"
"$python_path" -c "$probe_code"
for package_name in ${=SO101_REQUIRED_PACKAGES}; do
  package_prefix="$("$python_path" "$ros2_script" pkg prefix "$package_name")"
  print -- "PACKAGE_PREFIX\t${package_name}\t${package_prefix}"
done
'''
    environment["SO101_FIXED_DYLIB_FARM"] = str(paths.dylib_farm)
    environment["SO101_REQUIRED_PACKAGES"] = " ".join(REQUIRED_PACKAGES)
    completed = subprocess.run(
        [
            "/bin/zsh",
            "-f",
            "-c",
            shell_program,
            "zsh",
            str(paths.python),
            str(paths.ros2_script),
            probe_code,
            *setup_arguments,
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if completed.returncode != 0:
        raise RuntimeContractError(
            "RUNTIME_LOAD_PROBE_FAILED", completed.stderr.strip() or completed.stdout.strip()
        )
    lines = completed.stdout.splitlines()
    try:
        load_result = json.loads(lines[0])
    except (IndexError, json.JSONDecodeError) as error:
        raise RuntimeContractError(
            "RUNTIME_LOAD_PROBE_FAILED", completed.stdout.strip()
        ) from error
    package_prefixes: dict[str, str] = {}
    for line in lines[1:]:
        fields = line.split("\t", maxsplit=2)
        if len(fields) == 3 and fields[0] == "PACKAGE_PREFIX":
            package_prefixes[fields[1]] = fields[2]
    if set(package_prefixes) != set(REQUIRED_PACKAGES):
        raise RuntimeContractError(
            "PACKAGE_PREFIX_PROBE_FAILED", json.dumps(package_prefixes, sort_keys=True)
        )
    for project_package in (
        "so101_demo_py",
        "so101_mujoco_support",
        "so101_teleop",
    ):
        expected_project_prefix = paths.project_install / project_package
        if (
            Path(package_prefixes[project_package]).resolve()
            != expected_project_prefix.resolve()
        ):
            raise RuntimeContractError(
                "PROJECT_OVERLAY_NOT_AUTHORITATIVE",
                f"{project_package}: {package_prefixes[project_package]}",
            )
    return {"load": load_result, "package_prefixes": package_prefixes}


def validate_complete_contract(
    paths: RuntimePaths,
    *,
    system_name: str | None = None,
    machine: str | None = None,
    python_probe: Callable[[Path], dict[str, object]] = _default_python_probe,
    run_load_probe: bool = True,
    ros_domain_id: int = 0,
) -> dict[str, object]:
    report = validate_base_contract(
        paths,
        system_name=system_name,
        machine=machine,
        python_probe=python_probe,
    )
    _require_directory(paths.ros_fork_overlay, "ROS_FORK_OVERLAY_MISSING")
    _require_file(paths.ros_fork_overlay / "local_setup.zsh", "ROS_SETUP_MISSING")
    _require_file(paths.project_install / "local_setup.zsh", "PROJECT_SETUP_MISSING")
    for project_package in (
        "so101_demo_py",
        "so101_mujoco_support",
        "so101_teleop",
    ):
        package_marker = (
            paths.project_install
            / project_package
            / "share/ament_index/resource_index/packages"
            / project_package
        )
        _require_file(package_marker, "PROJECT_PACKAGE_MISSING")
    for runtime_directory in (paths.runtime_home, paths.ros_home, paths.ros_log_dir):
        _require_directory(runtime_directory, "RUNTIME_DATA_DIRECTORY_MISSING")
        if not os.access(runtime_directory, os.W_OK | os.X_OK):
            raise RuntimeContractError(
                "RUNTIME_DATA_DIRECTORY_NOT_WRITABLE", str(runtime_directory)
            )
    report["level"] = "complete"
    report["dylib_farm"] = _farm_manifest(paths)
    report["fixed_dylib_farm_contract"] = {
        "schema_version": FIXED_DYLIB_FARM_CONTRACT_SCHEMA_VERSION,
        "dylib_farm_root": str(paths.dylib_farm),
        "closure_prefixes": list(FIXED_CLOSURE_PREFIXES),
        "controller_relative_path": CONTROLLER_RUNTIME_RELATIVE_PATH,
        "plugin_basename": PLUGIN_BASENAME,
        "vendor_basename": VENDOR_BASENAME,
    }
    report["project_install"] = _path_identity(paths.project_install)
    if run_load_probe:
        report["runtime_probe"] = _run_complete_probe(paths, ros_domain_id)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the fixed /opt SO-101 macOS runtime contract."
    )
    parser.add_argument("doctor", nargs="?", default="doctor", choices=("doctor",))
    parser.add_argument("--base", action="store_true", help="check prerequisites only")
    parser.add_argument("--json", action="store_true", help="emit a JSON receipt")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--domain-id", type=int, default=0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    paths = RuntimePaths.production(arguments.repo_root)
    try:
        if arguments.base:
            report = validate_base_contract(paths)
        else:
            report = validate_complete_contract(
                paths, ros_domain_id=arguments.domain_id
            )
    except RuntimeContractError as error:
        document = {"status": "FAIL", "code": error.code, "detail": error.detail}
        if arguments.json:
            print(json.dumps(document, indent=2, sort_keys=True))
        else:
            print(str(error), file=sys.stderr)
        return 2
    if arguments.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"SO101_MACOS_RUNTIME_{str(report['level']).upper()}_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
