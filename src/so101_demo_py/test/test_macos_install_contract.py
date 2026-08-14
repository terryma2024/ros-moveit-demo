from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
INSTALLER = REPOSITORY_ROOT / "scripts" / "install-mujoco-ros2-control.zsh"
FUSION_CHECK = (
    REPOSITORY_ROOT / "src" / "so101_demo_py" / "scripts" / "check_fusion_contract.sh"
)


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


def test_mujoco_installer_applies_macos_patch_to_build_copy() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")

    assert "mujoco-ros2-control-macos.patch" in installer
    assert "mujoco-ros2-control-macos-platform.patch" in installer
    assert "mujoco-ros2-control-macos-headless.patch" in installer
    assert "mujoco-ros2-control-macos-main-thread-ui.patch" in installer
    assert "mujoco-ros2-control-macos-frameworks.patch" in installer
    assert "mujoco-ros2-control-macos-test-runtime.patch" in installer
    assert "mujoco-ros2-control-macos-test-rmw.patch" in installer
    assert '--base-paths "${build_source_dir}"' in installer
    assert 'for (( patch_index=${#macos_patches}; patch_index >= 1; --patch_index ))' in installer
    assert 'apply --reverse "${macos_patches[patch_index]}"' in installer
    assert 'for macos_patch in "${macos_patches[@]}"' in installer


def test_fusion_contract_uses_portable_sha256() -> None:
    fusion_check = FUSION_CHECK.read_text(encoding="utf-8")

    assert "sha256sum" not in fusion_check
    assert "hashlib.sha256" in fusion_check


def test_fusion_contract_avoids_ros2_shebang_dyld_filtering_on_macos() -> None:
    fusion_check = FUSION_CHECK.read_text(encoding="utf-8")

    assert 'export DYLD_LIBRARY_PATH="${dyld_library_path}"' in fusion_check
    assert 'ros2_command=(python3 "$(command -v ros2)")' in fusion_check
    assert '"${ros2_command[@]}" pkg prefix so101_demo_py' in fusion_check
