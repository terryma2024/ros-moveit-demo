from types import SimpleNamespace

from so101_demo.core.domain import State
from so101_demo.ports.evidence import PoseEvidence
from so101_demo.ports.robot_control import JointStateEvidence, PlanResult


class FakeProvider:
    def target_for(self, state: State) -> PoseEvidence:
        assert state is State.MOVE_ABOVE_OBJECT
        return PoseEvidence((0.02, -0.28, 0.28), (0.0, 0.0, 0.0, 1.0))


class FakeControl:
    def __init__(self) -> None:
        self.requests = []
        self.execute_calls = 0

    def plan_tcp_motion(self, request):
        self.requests.append(request)
        start = JointStateEvidence(("1", "2"), (0.0, 0.0), 1.0)
        terminal = JointStateEvidence(("1", "2"), (0.1, 0.2), 2.0)
        return PlanResult(True, start_state=start, terminal_state=terminal, trajectory=object())

    def execute(self, _plan):
        self.execute_calls += 1
        raise AssertionError("plan-only must never execute")


def test_plans_exactly_one_shared_workflow_state_without_execution() -> None:
    from so101_demo.application.dynamic_plan_only import DynamicPlanningOptions, plan_dynamic_state

    control = FakeControl()
    result = plan_dynamic_state(
        state=State.MOVE_ABOVE_OBJECT,
        provider=FakeProvider(),
        control=control,
        options=DynamicPlanningOptions(
            planning_frame="world",
            planning_group="arm",
            tcp_link="so101_tcp",
            position_tolerance_m=0.002,
            orientation_tolerance_rad=(0.1, 0.1, 0.1),
            planning_timeout_s=5.0,
            velocity_scaling=0.03,
            acceleration_scaling=0.03,
        ),
    )

    assert result.accepted
    assert len(control.requests) == 1
    request = control.requests[0]
    assert request.target_pose.position_m == (0.02, -0.28, 0.28)
    assert request.planning_frame == "world"
    assert request.planning_group == "arm"
    assert request.tcp_link == "so101_tcp"
    assert request.position_tolerance_m == 0.002
    assert request.velocity_scaling == 0.03
    assert control.execute_calls == 0


def test_rejects_a_non_motion_state_before_calling_planner() -> None:
    import pytest

    from so101_demo.application.dynamic_plan_only import (
        DynamicPlanOnlyError,
        DynamicPlanningOptions,
        plan_dynamic_state,
    )

    control = FakeControl()
    with pytest.raises(DynamicPlanOnlyError, match="PLAN_ONLY_STATE_UNSUPPORTED"):
        plan_dynamic_state(
            state=State.OPEN_GRIPPER,
            provider=FakeProvider(),
            control=control,
            options=DynamicPlanningOptions(
                "world", "arm", "so101_tcp", 0.002, (0.1, 0.1, 0.1), 5.0, 0.03, 0.03
            ),
        )
    assert control.requests == []


def test_run_dynamic_plan_only_arms_ready_boundary_before_pose_wait(
    tmp_path, monkeypatch
) -> None:
    import ament_index_python.packages as ament_packages
    import rclpy

    from so101_demo.ros import dynamic_runtime

    events: list[str] = []
    node = SimpleNamespace(destroy_node=lambda: events.append("node.close"))
    template = SimpleNamespace(
        planning_frame="world",
        planning_group="arm",
        tcp_link="so101_tcp",
        arm_joint_names=("shoulder", "elbow"),
        position_tolerance_m=0.002,
        orientation_tolerance_rad=(0.1, 0.1, 0.1),
        planning_timeout_s=5.0,
        velocity_scaling=0.03,
        acceleration_scaling=0.03,
    )
    loaded = SimpleNamespace(
        template=template,
        path=tmp_path / "policy.yaml",
        sha256="policy-sha",
        qualification_status="CALIBRATION_REQUIRED",
    )
    sample = object()

    class Source:
        def __init__(self, _node, _template) -> None:
            self.armed = False
            events.append("source.create")

        def arm(self, timeout_s: float) -> None:
            assert timeout_s == 5.0
            self.armed = True
            events.append("source.arm")

        def get_one(self, timeout_s: float):
            assert timeout_s == 8.0
            events.append("sample.acquire")
            if not self.armed:
                raise AssertionError("pose read before READY boundary")
            return sample

    class Scene:
        def __init__(self, _node) -> None:
            events.append("scene.create")

        def close(self) -> None:
            events.append("scene.close")

    class Planner:
        control = object()

        def __init__(self, _node, _joint_names) -> None:
            events.append("planner.create")

        def close(self) -> None:
            events.append("planner.close")

    monkeypatch.setattr(rclpy, "init", lambda: events.append("ros.init"))
    monkeypatch.setattr(
        rclpy,
        "create_node",
        lambda *_args, **_kwargs: events.append("node.create") or node,
    )
    monkeypatch.setattr(rclpy, "ok", lambda: False)
    monkeypatch.setattr(
        ament_packages,
        "get_package_share_directory",
        lambda _package: str(tmp_path / "share" / "so101_demo_py"),
    )
    monkeypatch.setattr(dynamic_runtime, "_load_policy", lambda *_args: loaded)
    monkeypatch.setattr(dynamic_runtime, "RosCupPoseSource", Source)
    monkeypatch.setattr(dynamic_runtime, "RosCupSceneObserver", Scene)
    monkeypatch.setattr(dynamic_runtime, "RosDynamicPlanner", Planner)
    monkeypatch.setattr(
        dynamic_runtime, "resolve_motion_targets", lambda *_args: object()
    )
    monkeypatch.setattr(
        dynamic_runtime,
        "plan_dynamic_state_with_scene_gates",
        lambda **_kwargs: (
            SimpleNamespace(accepted=True, error_code=None),
            object(),
            object(),
        ),
    )
    evidence_file = tmp_path / "plan.json"
    monkeypatch.setattr(
        dynamic_runtime,
        "write_dynamic_plan_manifest",
        lambda *_args, **_kwargs: evidence_file,
    )
    options = SimpleNamespace(
        plan_only_state="MOVE_ABOVE_OBJECT",
        evidence_file=str(evidence_file),
        dynamic_policy=None,
        backend="mujoco",
        installed_prefix=None,
        cup_pose_timeout_s=8.0,
        source_commit="source-sha",
    )

    assert dynamic_runtime.run_dynamic_plan_only(options) == 0
    assert events == [
        "ros.init",
        "node.create",
        "source.create",
        "source.arm",
        "sample.acquire",
        "scene.create",
        "planner.create",
        "planner.close",
        "scene.close",
        "node.close",
    ]
