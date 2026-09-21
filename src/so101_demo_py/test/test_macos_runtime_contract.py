from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_TOOL = REPOSITORY_ROOT / "scripts" / "so101_macos_runtime_contract.py"


def _load_contract_module():
    spec = importlib.util.spec_from_file_location("so101_macos_runtime_contract", CONTRACT_TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def contract_fixture(tmp_path: Path):
    module = _load_contract_module()
    filesystem_root = tmp_path / "host"
    physical_ros_root = tmp_path / "ros-source"
    logical_ros_root = filesystem_root / "opt/ros2_jazzy"
    data_root = filesystem_root / "opt/data"
    temp_root = data_root / "tmp"
    repository_root = tmp_path / "checkout"

    logical_ros_root.parent.mkdir(parents=True)
    physical_ros_root.mkdir()
    logical_ros_root.symlink_to(physical_ros_root, target_is_directory=True)
    data_root.mkdir()
    temp_root.mkdir()
    for runtime_directory in (
        data_root / "so101/home",
        data_root / "so101/ros-home",
        data_root / "so101/ros-logs",
    ):
        runtime_directory.mkdir(parents=True)

    required_files = (
        "install/setup.zsh",
        "install/ros2cli/bin/ros2",
        "extra_ws/install/setup.zsh",
        ".venv/bin/python",
        ".venv/bin/colcon",
    )
    for relative_path in required_files:
        path = physical_ros_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/zsh\n", encoding="utf-8")
        if path.parent.name == "bin":
            path.chmod(0o755)

    fork_install = data_root / "so101/runtime/fork/runs/fixture/install"
    fork_install.mkdir(parents=True)
    (fork_install / "setup.zsh").write_text("#!/bin/zsh\n", encoding="utf-8")
    (data_root / "so101/runtime/fork/current").symlink_to(fork_install)

    project_setup = data_root / "so101/workspace/install/setup.zsh"
    project_setup.parent.mkdir(parents=True)
    project_setup.write_text("#!/bin/zsh\n", encoding="utf-8")
    for project_package in (
        "so101_demo_py",
        "so101_mujoco_support",
        "so101_teleop",
    ):
        package_marker = (
            data_root
            / "so101/workspace/install"
            / project_package
            / "share/ament_index/resource_index/packages"
            / project_package
        )
        package_marker.parent.mkdir(parents=True)
        package_marker.write_text("", encoding="utf-8")

    farm_run = physical_ros_root / "dylib_farm/runs/fixture"
    farm_run.mkdir(parents=True)
    for library_name in module.REQUIRED_DYLIBS:
        (farm_run / library_name).write_bytes(b"fixture")
    (physical_ros_root / "dylib_farm/current").symlink_to(farm_run)

    paths = module.RuntimePaths.from_filesystem_root(
        filesystem_root=filesystem_root,
        repository_root=repository_root,
    )
    return module, paths, physical_ros_root


def _python_probe(_python: Path) -> dict[str, object]:
    return {
        "executable": str(_python.resolve()),
        "implementation": "CPython",
        "version": "3.11.15",
        "version_info": [3, 11],
    }


def test_production_contract_has_no_required_external_environment() -> None:
    module = _load_contract_module()
    paths = module.RuntimePaths.production(REPOSITORY_ROOT)

    assert module.REQUIRED_EXTERNAL_ENVIRONMENT == ()
    assert paths.ros_root == Path("/opt/ros2_jazzy")
    assert paths.ros_install == Path("/opt/ros2_jazzy/install")
    assert paths.python == Path("/opt/ros2_jazzy/.venv/bin/python")
    assert paths.data_root == Path("/opt/data")
    assert paths.temp_root == Path("/opt/data/tmp")
    assert paths.dylib_farm == Path("/opt/ros2_jazzy/dylib_farm/current")


def test_base_contract_accepts_a_valid_logical_symlink(contract_fixture) -> None:
    module, paths, physical_ros_root = contract_fixture

    report = module.validate_base_contract(
        paths,
        system_name="Darwin",
        machine="arm64",
        python_probe=_python_probe,
    )

    assert report["status"] == "PASS"
    assert report["paths"]["ros_root"]["logical"] == str(paths.ros_root)
    assert report["paths"]["ros_root"]["resolved"] == str(physical_ros_root)
    assert report["python"]["version_info"] == [3, 11]


@pytest.mark.parametrize(
    ("system_name", "machine", "error_code"),
    (
        ("Linux", "x86_64", "UNSUPPORTED_SYSTEM"),
        ("Darwin", "x86_64", "UNSUPPORTED_ARCHITECTURE"),
    ),
)
def test_base_contract_rejects_non_apple_silicon_hosts(
    contract_fixture, system_name: str, machine: str, error_code: str
) -> None:
    module, paths, _physical_ros_root = contract_fixture

    with pytest.raises(module.RuntimeContractError, match=error_code):
        module.validate_base_contract(
            paths,
            system_name=system_name,
            machine=machine,
            python_probe=_python_probe,
        )


def test_base_contract_rejects_a_broken_ros_root_symlink(contract_fixture) -> None:
    module, paths, physical_ros_root = contract_fixture
    physical_ros_root.rename(physical_ros_root.with_name("moved"))

    with pytest.raises(module.RuntimeContractError, match="ROS_ROOT_MISSING"):
        module.validate_base_contract(
            paths,
            system_name="Darwin",
            machine="arm64",
            python_probe=_python_probe,
        )


def test_base_contract_requires_python_311(contract_fixture) -> None:
    module, paths, _physical_ros_root = contract_fixture

    with pytest.raises(module.RuntimeContractError, match="PYTHON_ABI_MISMATCH"):
        module.validate_base_contract(
            paths,
            system_name="Darwin",
            machine="arm64",
            python_probe=lambda _path: {
                "executable": str(paths.python),
                "implementation": "CPython",
                "version": "3.12.0",
                "version_info": [3, 12],
            },
        )


def test_complete_contract_requires_project_overlay_and_loader_dependencies(
    contract_fixture,
) -> None:
    module, paths, _physical_ros_root = contract_fixture
    (paths.dylib_farm / "libhardware_interface.dylib").unlink()

    with pytest.raises(module.RuntimeContractError, match="DYLIB_MISSING"):
        module.validate_complete_contract(
            paths,
            system_name="Darwin",
            machine="arm64",
            python_probe=_python_probe,
            run_load_probe=False,
        )


def test_environment_is_rebuilt_from_the_contract_not_the_calling_shell(
    contract_fixture,
) -> None:
    module, paths, _physical_ros_root = contract_fixture
    first = module.build_runtime_environment(
        paths,
        inherited={
            "HOME": "/Users/first",
            "PATH": "/unexpected/first",
            "PYTHONHOME": "/poison/python-home",
            "PYTHONPATH": "/poison/python-path",
            "AMENT_PREFIX_PATH": "/poison/ament",
            "CMAKE_PREFIX_PATH": "/poison/cmake",
            "COLCON_PREFIX_PATH": "/poison/colcon",
            "DYLD_LIBRARY_PATH": "/poison/dyld",
            "DYLD_INSERT_LIBRARIES": "/poison/insert",
        },
        ros_domain_id=31,
    )
    second = module.build_runtime_environment(
        paths,
        inherited={"HOME": "/Users/second", "PATH": "/unexpected/second"},
        ros_domain_id=31,
    )

    assert first == second
    assert first["HOME"] == str(paths.runtime_home)
    assert first["PATH"].split(os.pathsep)[0] == str(paths.python.parent)
    assert first["DYLD_LIBRARY_PATH"] == str(paths.dylib_farm)
    assert first["TMPDIR"] == first["TMP"] == first["TEMP"] == str(paths.temp_root)
    assert first["ROS_HOME"] == str(paths.ros_home)
    assert first["ROS_LOG_DIR"] == str(paths.ros_log_dir)
    assert first["ROS_DOMAIN_ID"] == "31"
    assert "PYTHONHOME" not in first
    assert "PYTHONPATH" not in first
    assert "DYLD_INSERT_LIBRARIES" not in first


@pytest.mark.parametrize("domain_id", (-1, 233, "not-a-number"))
def test_environment_rejects_invalid_ros_domain_ids(
    contract_fixture, domain_id: object
) -> None:
    module, paths, _physical_ros_root = contract_fixture

    with pytest.raises(module.RuntimeContractError, match="ROS_DOMAIN_ID_INVALID"):
        module.build_runtime_environment(paths, inherited={}, ros_domain_id=domain_id)


def test_ros_command_uses_the_fixed_python_and_ros2_script(contract_fixture) -> None:
    module, paths, _physical_ros_root = contract_fixture

    command = module.build_ros_command(
        paths,
        ("launch", "so101_demo_py", "so101_mujoco_task_station.launch.py"),
    )

    assert command == [
        str(paths.python),
        str(paths.ros2_script),
        "launch",
        "so101_demo_py",
        "so101_mujoco_task_station.launch.py",
    ]


def test_ros_command_only_accepts_run_and_launch(contract_fixture) -> None:
    module, paths, _physical_ros_root = contract_fixture

    with pytest.raises(module.RuntimeContractError, match="ROS_COMMAND_INVALID"):
        module.build_ros_command(paths, ("daemon", "start"))
