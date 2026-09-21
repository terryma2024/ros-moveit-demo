import hashlib
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin", reason="macOS install and dylib contracts are macOS-only")


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
INSTALLER = REPOSITORY_ROOT / "scripts" / "install-mujoco-ros2-control.zsh"
FUSION_CHECK = (
    REPOSITORY_ROOT / "src" / "so101_demo_py" / "scripts" / "check_fusion_contract.sh"
)
MACOS_VENDOR = REPOSITORY_ROOT / "tools" / "mujoco_vendor_macos"
MACOS_VENDOR_INSTALLER = REPOSITORY_ROOT / "scripts" / "install-mujoco-vendor-macos.zsh"
MUJOCO_GLFW_PATCH = (
    MACOS_VENDOR / "patches" / "mujoco-3.4.0-glfw-no-primary-monitor.patch"
)
DYLIB_FARM = REPOSITORY_ROOT / "scripts" / "setup-macos-ros-dylib-farm.zsh"
ENVRC_EXAMPLE = REPOSITORY_ROOT / ".envrc.example"
PATCH_SERIES_DIR = REPOSITORY_ROOT / "scripts" / "patches" / "mujoco_ros2_control"
SUBMODULE = REPOSITORY_ROOT / "third_party" / "mujoco_ros2_control"
DEMO_SETUP = REPOSITORY_ROOT / "src/so101_demo_py/setup.py"
LOCK = REPOSITORY_ROOT / "src/so101_demo_py/config/mujoco/dependency-lock.yaml"
RUNTIME_LOCK = REPOSITORY_ROOT / "src/so101_demo_py/config/dependency-lock.yaml"
INTEGRATION_GUIDE = (
    REPOSITORY_ROOT / "docs/guides/so101-mujoco-ros2-integration-guide.md"
)
UPSTREAM_010_COMMIT = "57fc6744844902d4532160b403fa95840c1d6f96"
LOCAL_R11_COMMIT = "f19a8cc3af61feccacb22a9f0d16cc972e3b2c08"
CANDIDATE_COMMIT = "85d2a5c42686a3d6b0d909a047a4188b24edd257"
CANDIDATE_LABEL = "main"
MUJOCO_340_COMMIT = "e55fff5dea6f1d5dd7963ca52eecc41d05ad0922"
MUJOCO_GLFW_PATCH_SHA256 = (
    "aa506e126cf8bec3bcc60a961fbe457e056d2aeb1838bb6c67c7584d7ac5264e"
)


def test_upgrade_candidate_provenance_is_identical_in_both_locks() -> None:
    lock = yaml.safe_load(LOCK.read_text(encoding="utf-8"))
    runtime_lock = yaml.safe_load(RUNTIME_LOCK.read_text(encoding="utf-8"))

    for candidate_lock in (lock, runtime_lock):
        assert candidate_lock["release"] == "0.1.0"
        assert candidate_lock["fork"]["tag"] == CANDIDATE_LABEL
        assert candidate_lock["fork"]["commit"] == CANDIDATE_COMMIT
        assert candidate_lock["fork"]["lineage_commit"] == LOCAL_R11_COMMIT
        assert candidate_lock["upstream"]["tag"] == "0.1.0"
        assert candidate_lock["upstream"]["commit"] == UPSTREAM_010_COMMIT
    assert runtime_lock["fork"] == lock["fork"]
    assert runtime_lock["upstream"] == lock["upstream"]
    assert not PATCH_SERIES_DIR.exists()
    attributes = (REPOSITORY_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "scripts/patches/mujoco_ros2_control" not in attributes


def test_upgrade_candidate_gitlink_is_clean_and_contains_both_ancestries() -> None:
    lock = yaml.safe_load(LOCK.read_text(encoding="utf-8"))
    locked_commit = lock["fork"]["commit"]
    gitlink = subprocess.run(
        ["git", "ls-files", "--stage", "--", "third_party/mujoco_ros2_control"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()[1]
    assert gitlink == locked_commit
    assert (
        subprocess.run(
            ["git", "-C", str(SUBMODULE), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == locked_commit
    )
    assert (
        subprocess.run(
            [
                "git",
                "-C",
                str(SUBMODULE),
                "status",
                "--porcelain",
                "--untracked-files=all",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        == ""
    )
    for ancestor in (UPSTREAM_010_COMMIT, LOCAL_R11_COMMIT):
        subprocess.run(
            [
                "git",
                "-C",
                str(SUBMODULE),
                "merge-base",
                "--is-ancestor",
                ancestor,
                locked_commit,
            ],
            check=True,
        )


def test_task_station_install_contract_and_fork_versions_are_complete() -> None:
    setup = DEMO_SETUP.read_text(encoding="utf-8")
    for executable in (
        "so101_mujoco_rgbd_batch",
        "task_reachability",
        "rgbd_sensor_capture",
    ):
        assert f'"{executable} =' in setup
    assert (REPOSITORY_ROOT / "src/so101_demo_py/launch/so101_mujoco_task_station.launch.py").is_file()
    assert (REPOSITORY_ROOT / "src/so101_demo_py/config/mujoco/rgbd_task_points.yaml").is_file()
    package_files = sorted(SUBMODULE.glob("**/package.xml"))
    assert package_files
    assert {ET.parse(path).getroot().findtext("version") for path in package_files} == {"0.1.0"}


def test_installer_builds_exact_upgrade_package_set_and_checks_new_artifacts() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")
    package_block = re.search(
        r"readonly -a fork_packages=\(\n(?P<body>.*?)\n\)", installer, re.DOTALL
    )
    assert package_block is not None
    assert package_block.group("body").split() == [
        "mujoco_3d_lidar",
        "mujoco_ros2_control_msgs",
        "mujoco_ros2_control_plugins",
        "mujoco_ros2_control",
    ]
    for required_interface in (
        "mujoco_ros2_control_msgs/srv/SetFreeJointState",
        "mujoco_ros2_control_msgs/srv/ResetWorld",
        "mujoco_ros2_control_msgs/srv/SetPause",
        "mujoco_ros2_control_msgs/msg/ViewerCamera",
        "mujoco_ros2_control_msgs/srv/SetViewerCamera",
        "mujoco_ros2_control_msgs/srv/GetViewerCamera",
    ):
        assert required_interface in installer
    assert "mujoco_ros2_control_plugins/CameraPlugin" in installer


def test_integration_guide_uses_the_optional_observer_abi_and_authoritative_order() -> None:
    guide = INTEGRATION_GUIDE.read_text(encoding="utf-8")
    evidence_section = guide.split("## 4.", maxsplit=1)[1].split("## 5.", maxsplit=1)[0]

    assert "plugin base 新增" not in evidence_section
    assert "MujocoSystemInterface::step_authoritative_physics()" not in evidence_section
    assert "MuJoCoROS2ControlPluginBase" in evidence_section
    assert "不属于 base" in evidence_section
    assert "MuJoCoROS2ControlSimulationObserver" in evidence_section
    assert "SimulationObserverDispatcher" in evidence_section

    authoritative_order = (
        "`apply_staged_control_inputs()`",
        "`pre_step_callback_(mj_data_)`",
        "`mj_step(mj_model_, mj_data_)`",
        "`Diverged(...)`",
        "`observer_dispatcher_.on_physics_step(...)`",
        "`publish_control_state()`",
        "`refresh_data_snapshot()`",
        "`publish_clock()`",
    )
    assert all(token in evidence_section for token in authoritative_order)
    positions = [evidence_section.index(token) for token in authoritative_order]
    assert positions == sorted(positions)


def test_integration_guide_reads_back_all_four_fork_package_prefixes() -> None:
    guide = INTEGRATION_GUIDE.read_text(encoding="utf-8")

    for package in (
        "mujoco_3d_lidar",
        "mujoco_ros2_control_msgs",
        "mujoco_ros2_control_plugins",
        "mujoco_ros2_control",
    ):
        assert f"ros2 pkg prefix {package}" in guide


def test_macos_environment_uses_the_fixed_runtime_contract() -> None:
    envrc = ENVRC_EXAMPLE.read_text(encoding="utf-8")
    dylib_farm = DYLIB_FARM.read_text(encoding="utf-8")

    assert "ros_root=/opt/ros2_jazzy" in envrc
    assert '"$ros_root/install/setup.bash"' in envrc
    assert 'dylib_farm="$ros_root/dylib_farm/current"' in envrc
    assert '${HOME}/ros2_jazzy' not in envrc
    assert '/opt/ros/jazzy' not in envrc
    assert 'SO101_ROS_ROOT:-/opt/ros2_jazzy' in dylib_farm
    assert '${ros_workspace}/dylib_farm' in dylib_farm


def test_macos_environment_sources_the_project_overlay_last() -> None:
    envrc = ENVRC_EXAMPLE.read_text(encoding="utf-8")
    setup_block = envrc.split("for setup in", maxsplit=1)[1].split("; do", maxsplit=1)[0]

    expected_order = (
        '"$ros_root/install/setup.bash"',
        '"$ros_root/extra_ws/install/setup.bash"',
        '"/opt/data/so101/runtime/fork/current/setup.bash"',
        '"/opt/data/so101/workspace/install/setup.bash"',
    )
    positions = [setup_block.index(item) for item in expected_order]
    assert positions == sorted(positions)


def test_macos_environment_replaces_inherited_dyld_paths_with_the_fixed_farm() -> None:
    envrc = ENVRC_EXAMPLE.read_text(encoding="utf-8")

    assert "unset DYLD_LIBRARY_PATH" in envrc
    assert 'export DYLD_LIBRARY_PATH="$dylib_farm"' in envrc
    assert '${DYLD_LIBRARY_PATH:+' not in envrc


def test_mujoco_installer_accepts_source_overlay_underlay() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")

    assert "SO101_ROS_UNDERLAY" in installer
    assert "SO101_ROS_DEPENDENCY_OVERLAY" in installer
    assert "readonly ros_underlay=/opt/ros/jazzy" not in installer
    assert 'source_setup "${ros_dependency_overlay}/setup.zsh"' in installer


def test_mujoco_installer_validates_platform_library_names() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")

    assert "platform.system()" in installer
    assert 'suffix = ".dylib" if platform.system() == "Darwin" else ".so"' in installer


def test_installer_builds_a_clean_locked_fork_without_patch_application() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")

    for forbidden in (
        "patch_series",
        "portable_patches",
        "apply_patch_series",
        "git apply",
        "if [[ $(uname -s) == Darwin ]]",
    ):
        assert forbidden not in installer
    assert '--base-paths "${build_source_dir}"' in installer
    assert "status --porcelain --untracked-files=all" in installer
    assert "build source must be clean" in installer


def test_installer_treats_main_as_a_branch_label_not_a_release_tag() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")

    assert 'if [[ ${fork_tag} == main ]]; then' in installer
    assert 'elif [[ ${fork_tag} == *-candidate ]]; then' in installer


def test_installer_accepts_a_validated_local_lodepng_source() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")

    assert "SO101_LODEPNG_SOURCE_DIR" in installer
    assert "FETCHCONTENT_SOURCE_DIR_LODEPNG" in installer
    assert "lodepng source must be clean" in installer
    assert "so101-locked-commit.txt" in installer
    assert "SO101_TEST_DYLIB_FARM" in installer
    assert 'export DYLD_LIBRARY_PATH="${test_dylib_farm}"' in installer
    assert 'export DYLD_FALLBACK_LIBRARY_PATH="${test_dylib_farm}"' in installer


def test_installer_crosses_macos_sip_boundaries_with_explicit_python() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")

    assert "SO101_PYTHON" in installer
    assert "SO101_COLCON" in installer
    assert "SO101_ROS2" in installer
    assert "SO101_CTEST" in installer
    assert '"${python_command}" "${colcon_command}" --log-base' in installer
    assert '"${python_command}" "${colcon_command}" test-result' in installer
    assert '"${python_command}" "${ros2_command}" pkg prefix' in installer
    assert '"${python_command}" "${ros2_command}" interface show' in installer
    assert '"${ctest_command}" --test-dir "${build_base}/${package_name}"' in installer


def test_macos_plugin_install_rpath_resolves_the_copied_vendor() -> None:
    cmake = (
        SUBMODULE / "mujoco_ros2_control" / "CMakeLists.txt"
    ).read_text(encoding="utf-8")

    assert (
        'INSTALL_RPATH "@loader_path;@loader_path/../opt/mujoco_vendor/lib"'
        in cmake
    )


def test_fusion_contract_uses_portable_sha256() -> None:
    fusion_check = FUSION_CHECK.read_text(encoding="utf-8")

    assert "sha256sum" not in fusion_check
    assert "hashlib.sha256" in fusion_check


def test_fusion_contract_avoids_ros2_shebang_dyld_filtering_on_macos() -> None:
    fusion_check = FUSION_CHECK.read_text(encoding="utf-8")

    assert 'export DYLD_LIBRARY_PATH="${dyld_library_path}"' in fusion_check
    assert 'ros2_command=(python3 "$(command -v ros2)")' in fusion_check
    assert '"${ros2_command[@]}" pkg prefix so101_demo_py' in fusion_check


def test_macos_mujoco_vendor_installs_source_build_with_linux_compatible_layout(
    tmp_path: Path,
) -> None:
    stage = tmp_path / "mujoco-stage"
    source = tmp_path / "mujoco-source"
    build = tmp_path / "build"
    install = tmp_path / "install"
    (stage / "include/mujoco").mkdir(parents=True)
    (stage / "lib").mkdir(parents=True)
    (source / "simulate").mkdir(parents=True)
    (stage / "include/mujoco/mujoco.h").write_text("/* fixture */\n", encoding="utf-8")
    (stage / "lib/libmujoco.dylib").write_bytes(b"fixture")
    (source / "simulate/simulate.h").write_text("/* fixture */\n", encoding="utf-8")

    subprocess.run(
        [
            "cmake",
            "-S",
            str(MACOS_VENDOR),
            "-B",
            str(build),
            f"-DMUJOCO_STAGE_ROOT={stage}",
            f"-DMUJOCO_SOURCE_ROOT={source}",
            f"-DCMAKE_INSTALL_PREFIX={install}",
            f"-DPython3_EXECUTABLE={sys.executable}",
        ],
        check=True,
    )
    subprocess.run(["cmake", "--install", str(build)], check=True)

    vendor_root = install / "opt/mujoco_vendor"
    assert (vendor_root / "include/mujoco/mujoco.h").read_text() == "/* fixture */\n"
    assert (vendor_root / "include/simulate/simulate.h").read_text() == "/* fixture */\n"
    assert (vendor_root / "lib/libmujoco.dylib").read_bytes() == b"fixture"
    assert (install / "share/mujoco_vendor/cmake/mujoco_vendorConfig.cmake").is_file()


def test_macos_mujoco_vendor_patch_is_pinned_and_auditable() -> None:
    assert MUJOCO_GLFW_PATCH.is_file()
    assert hashlib.sha256(MUJOCO_GLFW_PATCH.read_bytes()).hexdigest() == (
        MUJOCO_GLFW_PATCH_SHA256
    )
    patch = MUJOCO_GLFW_PATCH.read_text(encoding="utf-8")
    assert "primary_monitor ? Glfw().glfwGetVideoMode(primary_monitor) : nullptr" in patch
    assert "const bool core_video_available" in patch
    assert "if (primary_monitor)" in patch


def test_macos_mujoco_vendor_installer_replays_patch_from_clean_340_source() -> None:
    installer = MACOS_VENDOR_INSTALLER.read_text(encoding="utf-8")

    assert f"readonly mujoco_commit={MUJOCO_340_COMMIT}" in installer
    assert f"readonly patch_sha256={MUJOCO_GLFW_PATCH_SHA256}" in installer
    assert "SO101_MUJOCO_SOURCE_ROOT" in installer
    assert "SO101_MUJOCO_VENDOR_WORKSPACE" in installer
    assert "SO101_MUJOCO_VENDOR_INSTALL_PREFIX" in installer
    assert 'status --porcelain --untracked-files=all' in installer
    assert 'apply --unidiff-zero --check "${patch_file}"' in installer
    assert 'apply --unidiff-zero "${patch_file}"' in installer
    assert 'observed_patch_sha256' in installer
    assert '--prepare-only' in installer
    assert 'colcon_command=${SO101_COLCON:-${ros_workspace}/.venv/bin/colcon}' in installer
    assert '[[ -x ${colcon_command} ]]' in installer
    assert '"${colcon_command}" --log-base' in installer
    assert 'python_command=${SO101_PYTHON:-${ros_workspace}/.venv/bin/python}' in installer
    assert '[[ -x ${python_command} ]]' in installer
    assert '"${python_command}" -c "import catkin_pkg"' in installer
    assert 'PATH="${python_command:h}:${PATH}" "${colcon_command}"' in installer
    assert '-DPython3_EXECUTABLE="${python_command}"' in installer


def test_macos_dylib_farm_links_source_overlays_with_later_prefix_precedence(
    tmp_path: Path,
) -> None:
    zsh = shutil.which("zsh")
    if zsh is None:
        pytest.skip("zsh is required for the macOS dylib farm script")
    ros_root = tmp_path / "ros2_jazzy"
    first_prefix = ros_root / "first/install"
    second_prefix = ros_root / "second/install"
    (first_prefix / "alpha/lib").mkdir(parents=True)
    (second_prefix / "beta/lib").mkdir(parents=True)
    first_library = first_prefix / "alpha/lib/libalpha.dylib"
    second_library = second_prefix / "beta/lib/libbeta.dylib"
    first_library.write_bytes(b"alpha")
    second_library.write_bytes(b"beta")
    for library_name in (
        "libcontrol_toolbox.dylib",
        "libhardware_interface.dylib",
        "librosidl_typesupport_c.dylib",
    ):
        (first_prefix / "alpha/lib" / library_name).write_bytes(library_name.encode())

    environment = os.environ.copy()
    environment["SO101_ROS_ROOT"] = str(ros_root)
    environment["SO101_ROS_PREFIXES"] = os.pathsep.join(
        (str(first_prefix), str(second_prefix))
    )
    completed = subprocess.run(
        [zsh, str(DYLIB_FARM)],
        check=True,
        capture_output=True,
        env=environment,
        text=True,
    )
    farm = Path(completed.stdout.strip())

    assert (ros_root / "dylib_farm/current").resolve() == farm
    assert (farm / "libalpha.dylib").resolve() == first_library
    assert (farm / "libbeta.dylib").resolve() == second_library

    conflicting_library = second_prefix / "beta/lib/libalpha.dylib"
    conflicting_library.write_bytes(b"conflict")
    replaced = subprocess.run(
        [zsh, str(DYLIB_FARM)],
        check=True,
        capture_output=True,
        env=environment,
        text=True,
    )
    replaced_farm = Path(replaced.stdout.strip())

    assert replaced_farm != farm
    assert (ros_root / "dylib_farm/current").resolve() == replaced_farm
    assert (replaced_farm / "libalpha.dylib").resolve() == conflicting_library
    override_manifest = (replaced_farm / ".overrides.tsv").read_text(encoding="utf-8")
    assert str(first_library) in override_manifest
    assert str(conflicting_library) in override_manifest
