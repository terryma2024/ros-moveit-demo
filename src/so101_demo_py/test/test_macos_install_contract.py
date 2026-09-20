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
CANDIDATE_COMMIT = "f89033c548591c9b4e7c2c5f76653562b22ff600"
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


def test_macos_environment_defaults_to_ubuntu_ros_prefix() -> None:
    envrc = ENVRC_EXAMPLE.read_text(encoding="utf-8")
    dylib_farm = DYLIB_FARM.read_text(encoding="utf-8")

    assert 'ros_underlay="${SO101_ROS_UNDERLAY:-/opt/ros/jazzy}"' in envrc
    assert '"$ros_underlay/setup.bash"' in envrc
    assert 'ros_underlay="${SO101_ROS_UNDERLAY:-/opt/ros/jazzy}"' in dylib_farm
    assert 'default_prefixes="${ros_underlay}:' in dylib_farm


def test_macos_environment_keeps_project_install_authoritative(tmp_path: Path) -> None:
    project_root = tmp_path / "moveit-demo"
    ros_workspace = tmp_path / "ros2_jazzy"
    ros_underlay = tmp_path / "ros_underlay"
    stale_fork = ros_workspace / "ws_mujoco_ros2_control_fork" / "install"
    project_root.mkdir()
    (project_root / ".envrc").write_text(
        ENVRC_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8"
    )

    prefixes = [
        ros_underlay,
        ros_workspace / "extra_ws" / "install",
        stale_fork,
        ros_workspace / "so101_isolated_ws" / "install",
        project_root / "install",
    ]
    for prefix in prefixes:
        prefix.mkdir(parents=True)
        setup = (
            f'export AMENT_PREFIX_PATH="{prefix}'
            '${AMENT_PREFIX_PATH:+:$AMENT_PREFIX_PATH}"\n'
        )
        if prefix == project_root / "install":
            setup = (
                f'export AMENT_PREFIX_PATH="{stale_fork}'
                '${AMENT_PREFIX_PATH:+:$AMENT_PREFIX_PATH}"\n' + setup
            )
        (prefix / "setup.bash").write_text(setup, encoding="utf-8")

    result = subprocess.run(
        [
            "bash",
            "-c",
            'watch_file() { :; }; source_env() { source "$1"; }; '
            'source "$1"; printf "%s" "$AMENT_PREFIX_PATH"',
            "bash",
            str(project_root / ".envrc"),
        ],
        check=True,
        capture_output=True,
        text=True,
        env={
            "HOME": str(tmp_path),
            "PATH": "/usr/bin:/bin",
            "SO101_ROS_UNDERLAY": str(ros_underlay),
            "SO101_ROS_WORKSPACE": str(ros_workspace),
        },
    )
    resolved_prefixes = result.stdout.split(":")

    assert resolved_prefixes[0] == str(project_root / "install")
    assert str(stale_fork) not in resolved_prefixes


def test_macos_environment_keeps_dylib_farm_as_fallback(tmp_path: Path) -> None:
    project_root = tmp_path / "moveit-demo"
    ros_workspace = tmp_path / "ros2_jazzy"
    project_install = project_root / "install"
    dylib_farm = ros_workspace / "macos_dylib_farm" / "current"
    project_install.mkdir(parents=True)
    dylib_farm.mkdir(parents=True)
    (project_root / ".envrc").write_text(
        ENVRC_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (project_install / "setup.bash").write_text(
        f'export DYLD_LIBRARY_PATH="{project_install / "lib"}'
        '${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"\n',
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "bash",
            "-c",
            'watch_file() { :; }; source_env() { source "$1"; }; '
            'source "$1"; printf "%s" "$DYLD_LIBRARY_PATH"',
            "bash",
            str(project_root / ".envrc"),
        ],
        check=True,
        capture_output=True,
        text=True,
        env={
            "HOME": str(tmp_path),
            "PATH": "/usr/bin:/bin",
            "SO101_ROS_WORKSPACE": str(ros_workspace),
        },
    )
    resolved_paths = result.stdout.split(":")

    assert resolved_paths[0] == str(project_install / "lib")
    assert resolved_paths[-1] == str(dylib_farm)


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


def test_macos_dylib_farm_links_source_overlays_and_rejects_ambiguous_names(
    tmp_path: Path,
) -> None:
    ros_root = tmp_path / "ros2_jazzy"
    first_prefix = ros_root / "first/install"
    second_prefix = ros_root / "second/install"
    (first_prefix / "alpha/lib").mkdir(parents=True)
    (second_prefix / "beta/lib").mkdir(parents=True)
    first_library = first_prefix / "alpha/lib/libalpha.dylib"
    second_library = second_prefix / "beta/lib/libbeta.dylib"
    first_library.write_bytes(b"alpha")
    second_library.write_bytes(b"beta")

    environment = os.environ.copy()
    environment["SO101_ROS_ROOT"] = str(ros_root)
    environment["SO101_ROS_PREFIXES"] = os.pathsep.join(
        (str(first_prefix), str(second_prefix))
    )
    completed = subprocess.run(
        [str(DYLIB_FARM)],
        check=True,
        capture_output=True,
        env=environment,
        text=True,
    )
    farm = Path(completed.stdout.strip())

    assert (farm / "libalpha.dylib").resolve() == first_library
    assert (farm / "libbeta.dylib").resolve() == second_library

    conflicting_library = second_prefix / "beta/lib/libalpha.dylib"
    conflicting_library.write_bytes(b"conflict")
    rejected = subprocess.run(
        [str(DYLIB_FARM)],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert rejected.returncode != 0
    assert "ambiguous dylib basename: libalpha.dylib" in rejected.stderr



MUJOCO_HEADER_INCLUDE = re.compile(r"#include\s*<(mujoco/[A-Za-z0-9_./]+\.h)>")
FORK_SOURCE_SUFFIXES = {".h", ".hpp", ".hh", ".cpp", ".cc", ".cxx"}
LIDAR_ROOT = SUBMODULE / "mujoco_extensions" / "mujoco_3d_lidar"
LIDAR_NUMERIC_TYPES = (
    LIDAR_ROOT / "include" / "mujoco_3d_lidar" / "mujoco_numeric_types.hpp"
)
# MuJoCo keeps mjtNum/mjMINVAL/mjtByte in mjtnum.h up to 3.8.0 and in mjtype.h
# from 3.9.0. The numeric type header is the one sanctioned place for the
# version-dependent include.
MUJOCO_NUMERIC_HEADER_SWITCH = "mujoco_numeric_types.hpp"
GUARDED_MUJOCO_HEADER = "mujoco/mjtnum.h"


def _mujoco_vendor_include_dir() -> Path | None:
    """Return the include directory of the installed MuJoCo vendor package."""
    try:
        from ament_index_python.packages import get_package_prefix
    except ImportError:
        return None
    try:
        prefix = Path(get_package_prefix("mujoco_vendor"))
    except Exception:
        return None
    include_dir = prefix / "opt" / "mujoco_vendor" / "include"
    return include_dir if include_dir.is_dir() else None


def _fork_sources() -> list[Path]:
    if not (SUBMODULE / ".git").exists():
        return []
    return sorted(
        path
        for path in SUBMODULE.rglob("*")
        if path.is_file()
        and path.suffix in FORK_SOURCE_SUFFIXES
        and ".git" not in path.parts
    )


def test_lidar_extension_selects_the_mujoco_numeric_header_by_availability() -> None:
    header = LIDAR_NUMERIC_TYPES.read_text(encoding="utf-8")
    assert "__has_include(<mujoco/mjtype.h>)" in header
    assert "#include <mujoco/mjtype.h>" in header
    assert "#include <mujoco/mjtnum.h>" in header

    for source in (
        LIDAR_ROOT / "include" / "mujoco_3d_lidar" / "3dlidar.h",
        LIDAR_ROOT / "src" / "3dlidar.cpp",
    ):
        text = source.read_text(encoding="utf-8")
        assert f"#include <mujoco_3d_lidar/{MUJOCO_NUMERIC_HEADER_SWITCH}>" in text, source
        assert f"#include <{GUARDED_MUJOCO_HEADER}>" not in text, source


def test_fork_sources_only_include_mujoco_headers_the_vendor_can_supply() -> None:
    include_dir = _mujoco_vendor_include_dir()
    if include_dir is None:
        pytest.skip("the installed mujoco_vendor ships no include directory here")
    sources = _fork_sources()
    if not sources:
        pytest.skip("the mujoco_ros2_control submodule is not initialized here")

    available = {
        path.relative_to(include_dir).as_posix() for path in include_dir.rglob("*.h")
    }
    assert available, "the vendored MuJoCo ships no headers"

    missing: dict[str, list[str]] = {}
    for source in sources:
        for header in MUJOCO_HEADER_INCLUDE.findall(
            source.read_text(encoding="utf-8", errors="ignore")
        ):
            if header not in available and not (
                header == GUARDED_MUJOCO_HEADER and source == LIDAR_NUMERIC_TYPES
            ):
                missing.setdefault(header, []).append(
                    source.relative_to(REPOSITORY_ROOT).as_posix()
                )
    assert not missing, (
        "fork sources include MuJoCo headers that the pinned vendor version does "
        f"not ship: {missing}"
    )


def test_lidar_extension_headers_compile_against_the_vendored_mujoco(
    tmp_path: Path,
) -> None:
    include_dir = _mujoco_vendor_include_dir()
    if include_dir is None:
        pytest.skip("the installed mujoco_vendor ships no include directory here")
    compiler = shutil.which("g++") or shutil.which("c++")
    if compiler is None:
        pytest.skip("no C++ compiler is available here")

    translation_unit = tmp_path / "lidar_include_check.cpp"
    translation_unit.write_text(
        "#include <mujoco_3d_lidar/3dlidar.h>\nint main() { return 0; }\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            compiler,
            "-std=c++17",
            "-fsyntax-only",
            f"-I{LIDAR_ROOT / 'include'}",
            f"-I{include_dir}",
            str(translation_unit),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_locked_fork_commit_is_contained_in_the_named_release_ref() -> None:
    """The lock names a release ref and an exact commit.

    The fork advances its pin along integration branches while the release ref
    stays where it is, so the contract the installer must enforce is containment
    of the release ref in the pinned commit, not pointer equality.
    """
    lock = yaml.safe_load(LOCK.read_text(encoding="utf-8"))
    release_ref = lock["fork"]["tag"]
    locked_commit = lock["fork"]["commit"]

    resolved = subprocess.run(
        ["git", "-C", str(SUBMODULE), "rev-list", "-n", "1", release_ref],
        check=False,
        capture_output=True,
        text=True,
    )
    if resolved.returncode != 0:
        pytest.skip(f"fork release ref {release_ref} is unavailable in this checkout")

    contained = subprocess.run(
        [
            "git",
            "-C",
            str(SUBMODULE),
            "merge-base",
            "--is-ancestor",
            resolved.stdout.strip(),
            locked_commit,
        ],
        check=False,
    )
    assert contained.returncode == 0, (
        f"locked fork commit {locked_commit} is not contained in release ref "
        f"{release_ref} ({resolved.stdout.strip()})"
    )


def test_installer_reports_a_pin_that_is_ahead_of_the_release_ref() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")

    assert "FORK_PIN_AHEAD_OF_RELEASE_REF" in installer
    assert "commits_ahead=" in installer
    assert "is not contained in fork ref" in installer
    assert "fork release tag does not resolve to locked commit" not in installer


def test_installer_repoints_a_stale_build_source_to_the_locked_commit() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")

    assert "BUILD_SOURCE_REPOINTED" in installer
    assert "cannot be re-pointed" in installer
    # A dirty build source stays a hard failure.
    assert "build source must be clean at locked fork commit" in installer
