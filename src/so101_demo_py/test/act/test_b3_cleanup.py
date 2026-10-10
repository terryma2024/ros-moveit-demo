"""B3: the broker chain is gone and the Teacher's controllers are the stock JointTrajectoryController.

Names are built from fragments so the repository-wide absence gate (`rg -w` over the deleted stems) stays meaningful.
"""
import importlib.util
import inspect

import pytest
import yaml
from paths import PACKAGE_ROOT, REPOSITORY

CONFIG = PACKAGE_ROOT / "config/mujoco"
SRC = PACKAGE_ROOT / "src"
STOCK = "joint_trajectory_controller/JointTrajectoryController"


def _controllers(name):
    return yaml.safe_load((CONFIG / name).read_text())


def test_the_act_controller_yaml_is_the_original_stock_config_plus_the_stock_neck_block():
    original, act = _controllers("ros2_controllers.yaml"), _controllers("act/ros2_controllers.yaml")
    manager = act["controller_manager"]["ros__parameters"]
    for name in ("arm_controller", "gripper_controller", "neck_controller"):
        assert manager[name]["type"] == STOCK, name
    # arm and gripper are byte-for-byte the original parameters, so the ACT profile cannot drift from the original
    for name in ("arm_controller", "gripper_controller", "joint_state_broadcaster"):
        assert act[name] == original[name], name
    assert act["neck_controller"]["ros__parameters"]["joints"] == ["neck_yaw_joint"]
    assert act["controller_manager"]["ros__parameters"]["update_rate"] == original["controller_manager"]["ros__parameters"]["update_rate"] == 500
    text = (CONFIG / "act/ros2_controllers.yaml").read_text()
    assert "so101_mujoco_support/" not in text and "enable_topic_command" not in text


# The Head neck is the stock joint trajectory controller plus a thin subclass (design 2026-10-10): the broker, the
# ROS broker driver, the leased action client, the reservation client/provision stack, the native close and the
# broker execution port are all gone, and so is the console script.
DELETED_MODULES = [
    ("adapters/act", "_".join(parts)) for parts in (
        ("command", "broker"), ("ros", "broker"), ("leased", "action", "client"),
        ("dispatch", "transaction"), ("teacher", "native", "runtime"),
        ("teacher", "bound", "authority"), ("teacher", "cup", "safety"), ("teacher", "physics", "source"),
        ("pick", "place", "child", "port"), ("pick", "place", "sources"),
        ("controller", "reservation", "client"), ("controller", "reservation", "provision"),
        ("head", "execution", "native"), ("head", "reservation", "authority"), ("head", "revocation"),
        ("head", "native", "policy", "readback"), ("broker", "execution"), ("head", "control", "protocol"))
] + [("act", "_".join(parts)) for parts in (
    ("native", "dispatch"), ("native", "stop"), ("broker", "stop", "policy"), ("teacher", "bound", "timing"),
    ("contact", "live", "session"))] + [("cli", "act_command_" + "broker"), ("runtime", "teacher_worker_" + "lifecycle")]


@pytest.mark.parametrize("package, module", DELETED_MODULES)
def test_a_deleted_module_is_not_importable_and_has_no_file(package, module):
    assert not (SRC / package / f"{module}.py").exists()
    assert importlib.util.find_spec(f"so101_demo.{package.replace('/', '.')}.{module}") is None


def test_the_c_plus_plus_broker_chain_is_gone_and_the_evidence_plugin_stays():
    # The reservation protocol/socket/provision, the bound reservation, the stop and ingress witnesses and the
    # broker-owned controller are deleted; the Head neck controller is the thin subclass of the stock one.
    support = REPOSITORY / "src/so101_mujoco_support"
    gone = ["src/native_sampler" + "_c_api.cpp", "src/broker_owned_trajectory_controller.cpp",
            "src/controller_reservation_protocol.cpp", "src/head_revocation_transport.cpp",
            "include/so101_mujoco_support/controller_stop_witness.hpp"]
    assert not any((support / name).exists() for name in gone)
    cmake = (support / "CMakeLists.txt").read_text()
    assert "so101_simulation_evidence_plugin" in cmake and "test_physics_step_fence" in cmake
    assert "native_trajectory" + "_sampler" not in cmake
    assert "broker_owned" not in cmake and "controller_reservation" not in cmake
    assert "so101_head_neck_trajectory_controller" in cmake


def test_the_vendored_jtc_is_not_in_the_worktree_and_the_snapshot_does_not_read_it():
    assert not (REPOSITORY / "src/third_party").exists()
    from so101_demo.act import execution_snapshot
    assert "third_party/ros2_controllers" not in inspect.getsource(execution_snapshot)


def test_the_console_script_and_the_receipt_plumbing_are_gone():
    assert "act_command_" + "broker" not in (REPOSITORY / "src/so101_demo_py/setup.py").read_text()
    from so101_demo.runtime import parallel_ipc
    assert not hasattr(parallel_ipc, "Rpc" + "WireReceipt")
    assert not hasattr(parallel_ipc.UnixRpcClient, "call_with_" + "receipt")
    from so101_demo.adapters.act.physics import MujocoPathChecker
    assert not hasattr(MujocoPathChecker, "check_native" + "_path")
    from so101_demo.act import episode_assembly
    assert not hasattr(episode_assembly, "readback_from_" + "frozen")


def test_the_old_inputs_manifest_schema_is_refused():
    from so101_demo.act.diagnostic_episode_inputs import MANIFEST_SCHEMA_VERSION, freeze_inputs
    assert MANIFEST_SCHEMA_VERSION == 2
    parameters = inspect.signature(freeze_inputs).parameters
    assert "broker" + "_stop_policy" not in parameters and "teacher_bound" + "_timing" not in parameters
