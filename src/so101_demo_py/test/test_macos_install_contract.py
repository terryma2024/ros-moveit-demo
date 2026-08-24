import hashlib
import os
import subprocess
import sys
from pathlib import Path

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
LOCK = REPOSITORY_ROOT / "src/so101_demo_py/config/mujoco/dependency-lock.yaml"
RUNTIME_LOCK = REPOSITORY_ROOT / "src/so101_demo_py/config/dependency-lock.yaml"
R6_FORK_COMMIT = "738e304551b4ea6db020b466086a13db71b65607"
EXPECTED_PORTABLE_DIFF_SHA256 = (
    "f57e9dea368a15edd881887f24ac56c5bbdb4d57194233d7faea79ca87c9358c"
)
MUJOCO_340_COMMIT = "e55fff5dea6f1d5dd7963ca52eecc41d05ad0922"
MUJOCO_GLFW_PATCH_SHA256 = (
    "aa506e126cf8bec3bcc60a961fbe457e056d2aeb1838bb6c67c7584d7ac5264e"
)


def test_r8_fork_is_the_only_portable_source_authority() -> None:
    lock = yaml.safe_load(LOCK.read_text(encoding="utf-8"))
    runtime_lock = yaml.safe_load(RUNTIME_LOCK.read_text(encoding="utf-8"))

    assert lock["fork"]["tag"] == "so101-0.0.3-r8"
    assert runtime_lock["fork"]["tag"] == "so101-0.0.3-r8"
    assert runtime_lock["fork"]["commit"] == lock["fork"]["commit"]
    assert (
        runtime_lock["fork"]["policy_behavior_commit"]
        == lock["fork"]["policy_behavior_commit"]
    )
    assert not PATCH_SERIES_DIR.exists()
    attributes = (REPOSITORY_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "scripts/patches/mujoco_ros2_control" not in attributes


def test_r8_gitlink_history_and_portable_bytes_are_exact() -> None:
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
    subprocess.run(
        [
            "git",
            "-C",
            str(SUBMODULE),
            "merge-base",
            "--is-ancestor",
            R6_FORK_COMMIT,
            locked_commit,
        ],
        check=True,
    )
    subjects = subprocess.run(
        [
            "git",
            "-C",
            str(SUBMODULE),
            "log",
            "--format=%s",
            "--reverse",
            f"{R6_FORK_COMMIT}..{locked_commit}",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert subjects == [
        "portable heartbeat format",
        "platform build and rpath",
        "headless rendering control",
        "Apple main thread UI",
        "Apple framework linkage",
        "Apple test logging runtime",
        "Apple test RMW runtime",
        "platform C++17 requirements",
        "Apple conversion warnings",
        "Apple test backward runtime",
        "guard Apple test runtime dependencies",
        "fix: guard unavailable GLFW primary monitor",
    ]
    portable_diff = subprocess.run(
        [
            "git",
            "-C",
            str(SUBMODULE),
            "diff",
            "--binary",
            f"{R6_FORK_COMMIT}..{locked_commit}",
        ],
        check=True,
        capture_output=True,
    ).stdout
    assert hashlib.sha256(portable_diff).hexdigest() == EXPECTED_PORTABLE_DIFF_SHA256


def test_macos_environment_defaults_to_ubuntu_ros_prefix() -> None:
    envrc = ENVRC_EXAMPLE.read_text(encoding="utf-8")
    dylib_farm = DYLIB_FARM.read_text(encoding="utf-8")

    assert 'ros_underlay="${SO101_ROS_UNDERLAY:-/opt/ros/jazzy}"' in envrc
    assert '"$ros_underlay/setup.bash"' in envrc
    assert 'ros_underlay="${SO101_ROS_UNDERLAY:-/opt/ros/jazzy}"' in dylib_farm
    assert 'default_prefixes="${ros_underlay}:' in dylib_farm


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
