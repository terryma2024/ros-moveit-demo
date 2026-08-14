import os
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
INSTALLER = REPOSITORY_ROOT / "scripts" / "install-mujoco-ros2-control.zsh"
FUSION_CHECK = (
    REPOSITORY_ROOT / "src" / "so101_demo_py" / "scripts" / "check_fusion_contract.sh"
)
MACOS_VENDOR = REPOSITORY_ROOT / "tools" / "mujoco_vendor_macos"
DYLIB_FARM = REPOSITORY_ROOT / "scripts" / "setup-macos-ros-dylib-farm.zsh"
ENVRC_EXAMPLE = REPOSITORY_ROOT / ".envrc.example"
PATCH_SERIES_DIR = REPOSITORY_ROOT / "scripts" / "patches" / "mujoco_ros2_control"
PATCH_SERIES_FILE = PATCH_SERIES_DIR / "series"
SUBMODULE = REPOSITORY_ROOT / "third_party" / "mujoco_ros2_control"
LOCKED_FORK_COMMIT = "738e304551b4ea6db020b466086a13db71b65607"


def _patch_series_entries() -> list[str]:
    return [
        line.strip()
        for line in PATCH_SERIES_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_cross_platform_patch_series_is_the_only_authority() -> None:
    entries = _patch_series_entries()

    assert entries
    assert len(entries) == len(set(entries))
    assert all(Path(entry).name == entry and ".." not in entry for entry in entries)
    assert {path.name for path in PATCH_SERIES_DIR.glob("*.patch")} == set(entries)
    assert not (
        REPOSITORY_ROOT / "patches/mujoco_ros2_control/macos-format-uint64.patch"
    ).exists()
    attributes = (REPOSITORY_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "scripts/patches/mujoco_ros2_control/*.patch -whitespace" in attributes

    tracked = subprocess.run(
        ["git", "ls-files", "scripts/patches/mujoco_ros2_control"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert {str(PATCH_SERIES_FILE.relative_to(REPOSITORY_ROOT))} | {
        str((PATCH_SERIES_DIR / entry).relative_to(REPOSITORY_ROOT))
        for entry in entries
    } <= set(tracked)


def test_cross_platform_patch_series_round_trips_locked_commit(
    tmp_path: Path,
) -> None:
    checkout = tmp_path / "fork"
    subprocess.run(
        ["git", "clone", "--shared", "--no-checkout", str(SUBMODULE), str(checkout)],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(checkout), "checkout", "--detach", LOCKED_FORK_COMMIT],
        check=True,
    )
    entries = _patch_series_entries()
    for entry in entries:
        patch = PATCH_SERIES_DIR / entry
        subprocess.run(
            ["git", "-C", str(checkout), "apply", "--check", str(patch)],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(checkout), "apply", str(patch)], check=True
        )

    heartbeat = (
        checkout
        / "mujoco_ros2_control_plugins/src/heartbeat_publisher_plugin.cpp"
    ).read_text(encoding="utf-8")
    assert "PRIu64" in heartbeat
    assert "Published heartbeat #%llu" not in heartbeat

    for entry in reversed(entries):
        subprocess.run(
            [
                "git",
                "-C",
                str(checkout),
                "apply",
                "--reverse",
                str(PATCH_SERIES_DIR / entry),
            ],
            check=True,
        )
    status = subprocess.run(
        [
            "git",
            "-C",
            str(checkout),
            "status",
            "--porcelain",
            "--untracked-files=all",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert status.stdout == ""


def test_installer_applies_the_same_series_on_every_platform() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")

    assert "patch_series_file=" in installer
    assert "load_patch_series" in installer
    assert 'apply_patch_series "${build_source_dir}"' in installer
    assert "if [[ $(uname -s) == Darwin ]]" not in installer


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


def test_mujoco_installer_applies_portable_series_to_build_copy() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")

    assert "patch_series_file=" in installer
    assert "load_patch_series" in installer
    assert 'apply_patch_series "${build_source_dir}"' in installer
    assert "if [[ $(uname -s) == Darwin ]]" not in installer
    assert '--base-paths "${build_source_dir}"' in installer
    assert 'for (( patch_index=${#portable_patches}; patch_index >= 1; --patch_index ))' in installer
    assert 'apply --reverse "${portable_patch}"' in installer
    assert 'for portable_patch in "${portable_patches[@]}"' in installer


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
