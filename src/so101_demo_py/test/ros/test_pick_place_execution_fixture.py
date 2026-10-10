"""A full collection-off pick-place through ExecuteTrajectory + JTC fakes, and the seams it needs.

`pick_place_driver.py` builds the real execution adapter over fake action servers. The sys.modules assertion runs
in a clean interpreter so that no other test's imports can mask a broker import.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import pick_place_driver as driver
from so101_demo.core.domain import State
from paths import PACKAGE_ROOT, SOURCE_ROOT, TEST_IMPORT_PATH

SRC = PACKAGE_ROOT / "src"
TELEOP_SRC = SOURCE_ROOT / "so101_teleop" / "so101_teleop"
FORWARD_MOTION_STATES = (State.MOVE_ABOVE_OBJECT, State.DESCEND, State.MICRO_LIFT, State.LIFT,
                         State.MOVE_ABOVE_PLACE, State.DESCEND_TO_PLACE, State.RETREAT)


def test_full_pick_place_runs_through_execute_trajectory_and_the_jtc_gripper_action(tmp_path):
    out = driver.run(tmp_path)
    assert out.result.status.value == "DONE", (out.result.failure, out.result.state_trace)
    assert out.result.state_trace[-1] is State.DONE
    assert not any(state.name.startswith("RECOVER_") for state in out.result.state_trace)
    # every arm motion is one MoveIt ExecuteTrajectory goal; the gripper uses its own JTC action
    assert len(out.world.execute_goals) == len(FORWARD_MOTION_STATES)
    assert out.world.gripper_goals == [0.465038, -0.0485, 0.75]
    assert not out.world.cancels
    execution = out.execution
    assert type(execution._trajectory).__name__ == "MoveItExecutionClient"
    assert type(execution._gripper).__name__ == "GripperClient"
    for name in ("_collection_port", "_teacher_phase_port"):
        assert not hasattr(execution, name)
    manifest = json.loads((tmp_path / "dynamic-execute-manifest.json").read_text())
    assert manifest["status"] == "DONE"
    assert manifest["teacher_execution_status"] == "COMPLETED"
    assert "monitor_violation" not in manifest


def test_release_published_a_normal_stop_event_built_from_the_joint_state_proof(tmp_path, monkeypatch):
    from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution
    monkeypatch.setattr(RosDynamicMujocoExecution, "final_stop_proof_enabled", True)
    out = driver.run(tmp_path)
    stops = [payload for kind, payload in out.events if kind == "normal_stop"]
    assert len(stops) == 1, "the final boundary publishes the one normal stop"
    proof = stops[0]["proof"]
    assert set(proof["joint_positions"]) == {*driver.ARM, "6"}
    assert proof["trajectory_result"] == "SUCCEEDED" and proof["stop_confirmed_wall_s"] > 0
    assert "stop_evidence" not in proof and "references" not in proof


def test_teacher_path_imports_no_broker_module_in_a_clean_interpreter(tmp_path):
    script = (
        "import json, sys, pathlib\n"
        f"sys.path[:0] = {[*map(str, TEST_IMPORT_PATH)]!r}\n"
        "import pick_place_driver as d\n"
        "import so101_demo.ros.dynamic_runtime, so101_demo.ros.dynamic_mujoco_execution\n"
        "import so101_demo.backends.mujoco.reset, so101_demo.backends.mujoco.client\n"
        "before = d.broker_modules_loaded()\n"
        f"out = d.run(pathlib.Path({str(tmp_path)!r}))\n"
        "print('B1JSON ' + json.dumps({'status': out.result.status.value, 'before': before, 'after': d.broker_modules_loaded()}))\n")
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=300,
                               env={**os.environ, "SO101_ACT_PROFILE": ""}, check=False)
    line = next((item for item in completed.stdout.splitlines() if item.startswith("B1JSON ")), None)
    assert line is not None, completed.stdout[-2000:] + completed.stderr[-3000:]
    document = json.loads(line[len("B1JSON "):])
    assert document["status"] == "DONE"
    assert document["before"] == [] and document["after"] == [], document


# ---- seams -------------------------------------------------------------------------------------------------------

def test_execution_builds_plain_rclpy_action_clients_for_the_arm_and_the_gripper(tmp_path):
    import rclpy.action

    created = []

    class Recorder:
        def __init__(self, node, action_type, action_name):
            created.append((action_type.__name__ if hasattr(action_type, "__name__") else str(action_type), action_name))

    original = rclpy.action.ActionClient
    rclpy.action.ActionClient = Recorder
    try:
        out_world = driver.World()
        from so101_demo.core.dynamic_pick import resolve_motion_targets
        from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution
        from test_dynamic_pick import _sample, _template
        template = _template()
        execution = RosDynamicMujocoExecution(
            driver.FakeNode(), template, resolve_motion_targets(_sample(), template), session_id="s",
            expected_reset_epoch=1, evidence_file=tmp_path / "m.json",
            urdf_path=driver.PACKAGE / "assets/mujoco/so101.urdf", policy_path=Path("p.yaml"), policy_sha256="a" * 64,
            event_stream=driver.FakeStream())
    finally:
        rclpy.action.ActionClient = original
    assert [name for _kind, name in created] == ["/execute_trajectory", "/gripper_controller/follow_joint_trajectory"]
    assert type(execution._trajectory._client) is Recorder and type(execution._gripper._client) is Recorder


def test_teacher_native_binding_helpers_are_gone_from_the_runtime():
    import so101_demo.ros.dynamic_runtime as runtime
    assert not hasattr(runtime, "_bind_teacher_native_arm") and not hasattr(runtime, "_bind_teacher_native_gripper")
    source = Path(runtime.__file__).read_text()
    for forbidden in ("leased_action_client", "LeasedTeacherPhasePort", "teacher_trajectory", "preselected_target_diagnostic"):
        assert forbidden not in source, forbidden


def test_mujoco_ros_client_ignores_the_act_profile_and_control_context_environment(monkeypatch):
    from so101_demo.backends.mujoco.client import MujocoRosClient

    class Node:
        def create_client(self, *_args, **_kwargs):
            return SimpleNamespace(wait_for_service=lambda **_kw: True)

        def create_subscription(self, *_args, **_kwargs):
            return object()

    monkeypatch.setenv("SO101_ACT_PROFILE", "1")
    monkeypatch.setenv("SO101_ACT_CONTROL_CONTEXT", "/nonexistent/context.json")
    client = MujocoRosClient(Node(), Node(), service_timeout_s=1.0)
    assert not hasattr(client, "control_context")
    assert client._pause is not None and client._reset is not None and client._switch is not None


SOURCE_FILES_WITHOUT_LEASED_CLIENT = (
    "backends/mujoco/qualified_phases/transport.py", "backends/mujoco/qualified_phases/remaining_lift.py",
    "backends/mujoco/qualified_phases/contact_hold.py", "backends/mujoco/qualified_phases/policy_lift_waypoint1.py",
    "backends/mujoco/qualified_phases/release_retreat.py", "backends/mujoco/qualified_phases/descend.py",
    "backends/mujoco/qualified_phases/staged_approach.py", "backends/mujoco/qualified_phases/place_alignment.py",
    "backends/mujoco/qualified_phases/micro_lift.py", "ros/dynamic_mujoco_execution.py", "ros/dynamic_runtime.py",
    "control/gripper/client.py")


@pytest.mark.parametrize("relative", SOURCE_FILES_WITHOUT_LEASED_CLIENT)
def test_main_execution_files_use_the_plain_action_client_as_in_main(relative):
    text = (SRC / relative).read_text()
    assert "leased_action_client" not in text and "make_action_client" not in text


def test_make_action_client_has_no_call_site_left():
    allowed = set()
    found = set()
    for root in (SRC, TELEOP_SRC):
        for path in root.rglob("*.py"):
            if "make_action_client" in path.read_text(encoding="utf-8"):
                found.add(path)
    assert found == allowed, sorted(str(item) for item in found - allowed)


def test_teleop_server_has_no_leased_client_swap():
    text = (TELEOP_SRC / "server.py").read_text()
    for forbidden in ("BrokerConnection", "from .act_control import", "SO101_ACT_BROKER_SOCKET", "action_client = "):
        assert forbidden not in text, forbidden
