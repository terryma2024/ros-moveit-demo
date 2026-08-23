import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from so101_demo.ports.reset import ResetStepReceipt


def _pose():
    from so101_demo.core.task_geometry import Pose7

    return Pose7((0.45, 0.25, 0.08, 0.0, 0.0, 0.0, 1.0))


def test_command_adapter_uses_exact_detach_topic_and_empty_message() -> None:
    from so101_demo.backends.gazebo.commands import GazeboCommandAdapter

    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, "", "")

    receipt = GazeboCommandAdapter(runner=run).request_detach()

    assert receipt.success
    argv, kwargs = calls[0]
    assert argv == [
        "gz",
        "topic",
        "-t",
        "/so101/detach_object",
        "-m",
        "gz.msgs.Empty",
        "-p",
        "",
    ]
    assert kwargs["shell"] is False


def test_command_adapter_sets_full_named_pose_and_requires_boolean_ack() -> None:
    from so101_demo.backends.gazebo.commands import GazeboCommandAdapter

    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, "data: true\n", "")

    receipt = GazeboCommandAdapter(runner=run).set_task_object_pose(_pose())

    assert receipt.success
    argv, _kwargs = calls[0]
    assert argv[:4] == [
        "gz",
        "service",
        "-s",
        "/world/so101_pick_place/set_pose",
    ]
    assert "gz.msgs.Pose" in argv
    assert "gz.msgs.Boolean" in argv
    assert 'name: "plastic_cup"' in argv[-1]
    assert "x: 0.45" in argv[-1]
    assert "w: 1.0" in argv[-1]


@pytest.mark.parametrize(
    ("world_state", "expected"),
    [
        ('component: "94 18 fixed"\n', True),
        ('component: "93 18 fixed"\n', False),
    ],
)
def test_command_adapter_reads_attachment_from_exact_ecs_joint(
    world_state: str, expected: bool
) -> None:
    from so101_demo.backends.gazebo.commands import GazeboCommandAdapter

    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, world_state, "")

    receipt = GazeboCommandAdapter(runner=run).observe_attachment(
        parent_entity_id=94,
        child_entity_id=18,
    )

    assert receipt.success
    assert receipt.evidence["attached"] is expected
    assert "stdout" not in receipt.evidence
    assert receipt.evidence["world_state_bytes"] == len(world_state.encode())
    assert len(receipt.evidence["world_state_sha256"]) == 64
    argv, kwargs = calls[0]
    assert argv[:4] == [
        "gz",
        "service",
        "-s",
        "/world/so101_pick_place/state",
    ]
    assert "gz.msgs.SerializedStepMap" in argv
    assert kwargs["shell"] is False


def test_gazebo_pose_vector_preserves_named_pose_and_entity_ids() -> None:
    from so101_demo.backends.gazebo.reset import GazeboResetState
    from so101_demo.control.trajectory.reset_control import record_gazebo_pose_vector

    state = GazeboResetState()
    vector = SimpleNamespace(
        pose=[
            SimpleNamespace(
                name="plastic_cup",
                id=17,
                position=SimpleNamespace(x=0.35, y=0.15, z=0.045),
                orientation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
            ),
            SimpleNamespace(name="body", id=18),
            SimpleNamespace(name="gripper", id=94),
        ]
    )

    record_gazebo_pose_vector(state, vector)

    snapshot = state.snapshot()
    assert snapshot["cup_pose"].values == (0.35, 0.15, 0.045, 0.0, 0.0, 0.0, 1.0)
    assert snapshot["entity_ids"] == {
        "plastic_cup": 17,
        "body": 18,
        "gripper": 94,
    }


def test_gazebo_parking_pose_is_stable_on_the_ground_plane() -> None:
    config = yaml.safe_load(
        Path("src/so101_demo_py/config/gazebo/reset.yaml").read_bytes()
    )

    assert config["parking_pose_xyz_xyzw"] == [
        0.45,
        0.25,
        0.045,
        0.0,
        0.0,
        0.0,
        1.0,
    ]


@pytest.mark.parametrize(
    ("result", "code"),
    [
        (subprocess.CompletedProcess([], 1, "", "failed"), "RESET_GAZEBO_COMMAND_FAILED"),
        (subprocess.CompletedProcess([], 0, "data: false\n", ""), "RESET_GAZEBO_ACK_REJECTED"),
        (subprocess.CompletedProcess([], 0, "not boolean\n", ""), "RESET_GAZEBO_ACK_INVALID"),
    ],
)
def test_pose_command_failures_are_stable(result, code: str) -> None:
    from so101_demo.backends.gazebo.commands import GazeboCommandAdapter

    adapter = GazeboCommandAdapter(runner=lambda *_args, **_kwargs: result)
    receipt = adapter.set_task_object_pose(_pose())
    assert not receipt.success
    assert receipt.failure_code == code


def test_physical_adapter_verifies_detach_and_pose_convergence() -> None:
    from so101_demo.backends.gazebo.reset import GazeboPhysicalResetPort
    from so101_demo.ports.reset import ResetStepReceipt

    attached = iter((True, True, False))
    poses = iter((None, _pose()))

    class Commands:
        def request_detach(self):
            return ResetStepReceipt(True, None, {"published": True})

        def set_task_object_pose(self, pose):
            return ResetStepReceipt(True, None, {"requested_pose": pose.values})

    port = GazeboPhysicalResetPort(
        Commands(),
        observe_attachment=lambda: next(attached),
        observe_pose=lambda: next(poses),
        timeout_s=0.1,
        wait=lambda _seconds: None,
    )

    assert port.detach_task_object().success
    assert port.park_task_object(_pose()).success


def test_physical_adapter_times_out_without_false_success() -> None:
    from so101_demo.backends.gazebo.reset import GazeboPhysicalResetPort
    from so101_demo.ports.reset import ResetStepReceipt

    class Commands:
        def request_detach(self):
            return ResetStepReceipt(True, None, {})

        def set_task_object_pose(self, pose):
            return ResetStepReceipt(True, None, {})

    ticks = iter((0.0, 0.0, 0.2, 0.2))
    port = GazeboPhysicalResetPort(
        Commands(),
        observe_attachment=lambda: True,
        observe_pose=lambda: None,
        timeout_s=0.1,
        clock=lambda: next(ticks),
        wait=lambda _seconds: None,
    )

    result = port.detach_task_object()
    assert not result.success
    assert result.failure_code == "RESET_GAZEBO_DETACH_VERIFY_FAILED"


def test_robot_adapter_executes_the_exact_planned_trajectory() -> None:
    from so101_demo.backends.gazebo.reset import GazeboRobotResetPort
    from so101_demo.core.domain import ActionResult, ActionStatus

    trajectory = object()

    class Planner:
        def plan_joint_path(self, request, timeout_s):
            self.request = request
            return type("Outcome", (), {"trajectory": trajectory, "failure": None})()

    class Executor:
        def execute(self, received, timeout_s):
            self.received = received
            return ActionResult(ActionStatus.SUCCEEDED)

    planner, executor = Planner(), Executor()
    port = GazeboRobotResetPort(
        planner=planner,
        executor=executor,
        command_gripper=lambda _target: ResetStepReceipt(True, None, {}),
        observe_joints=lambda: ({str(index): 0.0 for index in range(1, 7)}, {str(index): 0.0 for index in range(1, 7)}),
        home_positions=(0.0, 0.0, 0.0, 0.0, 0.0),
        gripper_open_position=-0.059600220867817,
        position_tolerance=0.002,
        velocity_tolerance=0.01,
        timeout_s=0.1,
    )

    plan = port.plan_home("home")
    assert plan.success and plan.plan is trajectory
    assert port.execute_home_and_verify(plan.plan).success
    assert executor.received is trajectory


def test_robot_adapter_waits_for_gripper_position_and_velocity_convergence() -> None:
    from so101_demo.backends.gazebo.reset import GazeboRobotResetPort

    observations = iter(
        (
            ({"6": -0.0567}, {"6": -0.0298}),
            ({"6": -0.059600220867817}, {"6": 0.0}),
        )
    )
    calls = []
    port = GazeboRobotResetPort(
        planner=object(),
        executor=object(),
        command_gripper=lambda _target: ResetStepReceipt(True, None, {}),
        observe_joints=lambda: calls.append(True) or next(observations),
        home_positions=(0.0, 0.0, 0.0, 0.0, 0.0),
        gripper_open_position=-0.059600220867817,
        position_tolerance=0.002,
        velocity_tolerance=0.01,
        timeout_s=0.1,
        wait=lambda _seconds: None,
    )

    assert port.open_gripper().success
    assert len(calls) == 2


def test_moveit_planning_client_converts_joint_domain_request_to_wire_request() -> None:
    from moveit_msgs.srv import GetMotionPlan
    from so101_demo.control.moveit.planning import JointPlanRequest, MoveItPlanningClient

    class Future:
        def done(self):
            return True

        def result(self):
            trajectory = SimpleNamespace(
                joint_trajectory=SimpleNamespace(points=[object()])
            )
            return SimpleNamespace(
                motion_plan_response=SimpleNamespace(
                    error_code=SimpleNamespace(val=1), trajectory=trajectory
                )
            )

    class Client:
        def wait_for_service(self, timeout_sec):
            return True

        def call_async(self, request):
            self.request = request
            if not isinstance(request, GetMotionPlan.Request):
                raise TypeError()
            return Future()

    client = Client()
    outcome = MoveItPlanningClient(client).plan_joint_path(
        JointPlanRequest(
            joint_names=("1", "2", "3", "4", "5"),
            current_positions=(0.2, -0.15, 0.25, -0.2, 0.15),
            target_positions=(0.0, 0.0, 0.0, 0.0, 0.0),
        )
    )

    assert outcome.failure is None
    assert isinstance(client.request, GetMotionPlan.Request)
