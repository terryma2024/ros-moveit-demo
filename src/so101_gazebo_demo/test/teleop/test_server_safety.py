import asyncio
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_teleop.models import PlanSummary, Pose6D, ServerMode, TelemetrySnapshot
from so101_teleop.server import (
    TELEOP_ENVIRONMENT_KEYS,
    RosTelemetryWorker,
    StoredTrajectory,
    TeleopService,
    _joint_fingerprint,
    read_teleop_environment,
)
from so101_teleop.control import PlanRejected, PlanStore
from so101_teleop.main import installed_web_assets


class Worker:
    def __init__(self):
        self._plans = {}; self.attaches = []; self.executed = []; self.fingerprint = "start-a"
        self._snapshot = TelemetrySnapshot(mode=ServerMode.READY, simulation_session_id="sim-a", revision=7)
    def snapshot(self): return self._snapshot
    def start_fingerprint(self): return self.fingerprint
    def attachment_transaction(self, attach): self.attaches.append(attach); return True
    def execute_plan(self, plan_id): self.executed.append(plan_id)
    def package_cli(self, executable, arguments): return "owner completed"
    def home(self): return None
    def invalidate_session(self):
        self._plans.clear(); self._snapshot.simulation_session_id = "sim-reset"; return "sim-reset"


class PlanningWorker(Worker):
    def __init__(self):
        super().__init__()
        self.planning_calls = []

    def plan_joints(self, target, velocity_scaling_factor=0.10,
                    acceleration_scaling_factor=0.10):
        self.planning_calls.append({
            "target": target,
            "velocity_scaling_factor": velocity_scaling_factor,
            "acceleration_scaling_factor": acceleration_scaling_factor,
        })
        summary = PlanSummary(
            plan_id="scaled-plan",
            start_fingerprint=self.fingerprint,
            target_fingerprint="target",
            scene_revision=0,
            expires_at_monotonic=time.monotonic() + 30,
        )
        stored = StoredTrajectory(summary, object(), "sim-a", 7)
        self._plans[summary.plan_id] = stored
        return stored


async def lease(service):
    return (await service.command("lease", {"command_id": "lease"})).layers["lease_id"]


def test_joint_plan_forwards_bounded_velocity_and_acceleration_scaling():
    """Loaded pick/place moves can run slower without weakening path tolerance."""
    async def scenario():
        worker = PlanningWorker()
        service = TeleopService(worker)
        token = await lease(service)

        result = await service.command("plan_joints", {
            "command_id": "slow-plan",
            "lease_id": token,
            "target_joints_rad": {str(index): 0.1 for index in range(1, 6)},
            "velocity_scaling_factor": 0.03,
            "acceleration_scaling_factor": 0.03,
        })

        assert result.succeeded
        assert worker.planning_calls == [{
            "target": {str(index): 0.1 for index in range(1, 6)},
            "velocity_scaling_factor": 0.03,
            "acceleration_scaling_factor": 0.03,
        }]

    asyncio.run(scenario())


def test_valid_web_root_override_is_authoritative(monkeypatch, tmp_path):
    root = tmp_path / "dist"
    assets = root / "assets"
    assets.mkdir(parents=True)
    (root / "index.html").write_text('<script src="/assets/app.js"></script>')
    (assets / "app.js").write_text("ok")
    monkeypatch.setenv("SO101_TELEOP_WEB_ROOT", str(root))
    assert installed_web_assets() == root


def test_invalid_web_root_override_is_rejected_without_fallback(monkeypatch, tmp_path):
    missing = tmp_path / "missing"
    monkeypatch.setenv("SO101_TELEOP_WEB_ROOT", str(missing))
    with pytest.raises(RuntimeError, match="SO101_TELEOP_WEB_ROOT"):
        installed_web_assets()


def test_telemetry_environment_exposes_only_the_operator_diagnostic_allowlist():
    allowed = [
        "ROS_DOMAIN_ID", "ROS_DISTRO", "ROS_VERSION", "ROS_PYTHON_VERSION",
        "ROS_AUTOMATIC_DISCOVERY_RANGE", "AMENT_PREFIX_PATH", "COLCON_PREFIX_PATH",
        "GZ_PARTITION", "GZ_CONFIG_PATH", "GZ_SIM_RESOURCE_PATH",
        "GZ_SIM_SYSTEM_PLUGIN_PATH", "PYTHONPATH", "LD_LIBRARY_PATH",
    ]
    environment = {key: f"value-{index}" for index, key in enumerate(allowed)}
    environment["SECRET_TOKEN"] = "must-not-leak"

    assert list(TELEOP_ENVIRONMENT_KEYS) == allowed
    assert read_teleop_environment(environment) == {
        key: f"value-{index}" for index, key in enumerate(allowed)
    }
    assert "SECRET_TOKEN" not in read_teleop_environment(environment)


def test_worker_snapshot_captures_runtime_ros_and_gazebo_environment(monkeypatch):
    monkeypatch.setenv("ROS_DOMAIN_ID", "55")
    monkeypatch.setenv("GZ_PARTITION", "partition-a")
    monkeypatch.setenv("SECRET_TOKEN", "must-not-leak")

    snapshot = RosTelemetryWorker().snapshot()

    assert snapshot.environment["ROS_DOMAIN_ID"] == "55"
    assert snapshot.environment["GZ_PARTITION"] == "partition-a"
    assert "SECRET_TOKEN" not in snapshot.environment


def test_second_client_cannot_silently_replace_an_unexpired_control_lease():
    """A diagnostic browser must not steal the operator's one-writer lease."""
    async def scenario():
        service = TeleopService(Worker())
        first = await service.command("lease", {"command_id": "lease-first"})
        second = await service.command("lease", {"command_id": "lease-second"})
        renewed = await service.command("lease_renew", {
            "command_id": "renew-first",
            "lease_id": first.layers["lease_id"],
        })

        assert second.succeeded is False
        assert second.code == "LEASE_BUSY"
        assert renewed.succeeded is True
    asyncio.run(scenario())


def test_valid_lease_renewal_is_not_rejected_while_workflow_owner_is_running():
    """A long workflow command must not make its own operator lose the lease."""
    async def scenario():
        worker = Worker()
        started = threading.Event()
        release = threading.Event()

        def blocking_owner(executable, arguments, timeout_s=45.0):
            started.set()
            assert release.wait(timeout=2.0)
            return "trace=WAIT_GRASP_STABLE"

        worker.package_cli = blocking_owner
        service = TeleopService(worker)
        acquired = await service.command("lease", {"command_id": "lease"})
        lease_id = acquired.layers["lease_id"]
        workflow = asyncio.create_task(service.command("workflow_start", {
            "command_id": "workflow-start",
            "lease_id": lease_id,
            "session_id": "sim-a",
        }))
        assert await asyncio.to_thread(started.wait, 1.0)

        renewed = await service.command("lease_renew", {
            "command_id": "renew-during-workflow",
            "lease_id": lease_id,
            "session_id": "sim-a",
        })
        release.set()
        completed = await workflow

        assert renewed.succeeded is True
        assert renewed.code == "OK"
        assert completed.succeeded is True

    asyncio.run(scenario())


def test_workflow_step_resumes_the_existing_cpp_checkpoint_before_single_step():
    """Next Step must advance the checkpoint instead of replaying the first step."""
    async def scenario():
        worker = Worker()
        calls = []

        def owner(executable, arguments, timeout_s=45.0):
            calls.append((executable, list(arguments), timeout_s))
            return "trace=IDLE -> PREPARE_OPEN_GRIPPER -> MOVE_ABOVE_OBJECT"

        worker.package_cli = owner
        service = TeleopService(worker)
        lease_id = await lease(service)
        started = await service.command("workflow_start", {
            "command_id": "workflow-start",
            "lease_id": lease_id,
            "session_id": "sim-a",
        })
        run_id = started.data["workflow"]["run_id"]
        stepped = await service.command("workflow_step", {
            "command_id": "workflow-step",
            "lease_id": lease_id,
            "session_id": "sim-a",
            "run_id": run_id,
            "snapshot_revision": started.snapshot_revision,
        })

        assert started.succeeded is True
        assert stepped.succeeded is True
        assert "--resume" not in calls[0][1]
        assert calls[0][1][-1] == "--step"
        assert calls[1][1][-3:] == ["--resume", "true", "--step"]

    asyncio.run(scenario())


def test_workflow_run_creates_a_fresh_run_without_step_or_resume_flags():
    """Run owns a new checkpoint and executes the workflow from the beginning."""
    async def scenario():
        worker = Worker()
        calls = []

        def owner(executable, arguments, timeout_s=45.0):
            calls.append((executable, list(arguments), timeout_s))
            return "trace=IDLE -> PREPARE_OPEN_GRIPPER -> DONE"

        worker.package_cli = owner
        service = TeleopService(worker)
        lease_id = await lease(service)
        result = await service.command("workflow_run", {
            "command_id": "workflow-run",
            "lease_id": lease_id,
            "session_id": "sim-a",
        })

        assert result.succeeded is True
        assert result.data["workflow"]["run_id"] in service._workflow
        assert calls[0][0] == "pick_place_state_machine"
        assert "--step" not in calls[0][1]
        assert "--resume" not in calls[0][1]

    asyncio.run(scenario())


def test_workflow_run_cannot_replace_an_existing_workflow():
    """Run must not silently overwrite a workflow checkpoint after Start."""
    async def scenario():
        worker = Worker()
        calls = []

        def owner(executable, arguments, timeout_s=45.0):
            calls.append((executable, list(arguments), timeout_s))
            return "trace=IDLE -> PREPARE_OPEN_GRIPPER"

        worker.package_cli = owner
        service = TeleopService(worker)
        lease_id = await lease(service)
        started = await service.command("workflow_start", {
            "command_id": "workflow-start",
            "lease_id": lease_id,
            "session_id": "sim-a",
        })
        original = dict(service._workflow)
        rejected = await service.command("workflow_run", {
            "command_id": "workflow-run",
            "lease_id": lease_id,
            "session_id": "sim-a",
        })

        assert started.succeeded is True
        assert rejected.succeeded is False
        assert rejected.code == "WORKFLOW_ALREADY_STARTED"
        assert service._workflow == original
        assert len(calls) == 1

    asyncio.run(scenario())


def test_workflow_resume_requires_an_existing_run_and_uses_resume_only():
    """Resume continues an existing checkpoint and never creates one implicitly."""
    async def scenario():
        worker = Worker()
        calls = []

        def owner(executable, arguments, timeout_s=45.0):
            calls.append((executable, list(arguments), timeout_s))
            return "trace=IDLE -> PREPARE_OPEN_GRIPPER"

        worker.package_cli = owner
        service = TeleopService(worker)
        lease_id = await lease(service)
        missing = await service.command("workflow_resume", {
            "command_id": "workflow-resume-missing",
            "lease_id": lease_id,
            "session_id": "sim-a",
        })
        assert missing.succeeded is False
        assert missing.code == "WORKFLOW_RUN_MISMATCH"
        assert service._workflow == {}
        assert calls == []

        started = await service.command("workflow_start", {
            "command_id": "workflow-start",
            "lease_id": lease_id,
            "session_id": "sim-a",
        })
        resumed = await service.command("workflow_resume", {
            "command_id": "workflow-resume",
            "lease_id": lease_id,
            "session_id": "sim-a",
            "run_id": started.data["workflow"]["run_id"],
        })
        assert resumed.succeeded is True
        assert calls[1][1][-2:] == ["--resume", "true"]
        assert "--step" not in calls[1][1]

    asyncio.run(scenario())


def test_detach_publishes_detach_and_waits_for_detached_convergence():
    """A suffix match made detach issue an attach event; exact operation identity is required."""
    async def scenario():
        worker = Worker(); service = TeleopService(worker); token = await lease(service)
        result = await service.command("attachment_detach", {"command_id": "detach", "lease_id": token})
        assert result.succeeded and worker.attaches == [False]
    asyncio.run(scenario())


def test_worker_generates_nonempty_startup_session_without_launch_environment(monkeypatch):
    """An omitted launch variable must not collapse the plan/session safety boundary."""
    monkeypatch.delenv("SO101_SIMULATION_SESSION_ID", raising=False)
    worker = RosTelemetryWorker()
    assert worker._session_id.startswith("startup-")


def test_joint_samples_publish_authoritative_so101_urdf_position_limits():
    worker = object.__new__(RosTelemetryWorker)
    message = SimpleNamespace(
        name=[str(index) for index in range(1, 7)],
        position=[0.0] * 6,
        velocity=[0.0] * 6,
    )

    worker._on_joints(message)

    expected = {
        "1": (-1.91986, 1.91986),
        "2": (-1.74533, 1.74533),
        "3": (-1.74533, 1.5708),
        "4": (-1.65806, 1.65806),
        "5": (-2.79253, 2.79253),
        "6": (-0.059303612618397, 1.74533),
    }
    assert {
        name: (sample.lower_limit_rad, sample.upper_limit_rad)
        for name, sample in worker._joints.items()
    } == expected


def test_tcp_ik_uses_one_minute_solver_timeout_and_larger_service_budget():
    worker = object.__new__(RosTelemetryWorker)
    worker._ik_client = object()
    worker._current_positions = lambda: {str(index): 0.0 for index in range(1, 7)}
    captured = {}
    def call(client, request, timeout_s):
        captured["solver"] = request.ik_request.timeout.sec
        captured["service"] = timeout_s
        return SimpleNamespace(error_code=SimpleNamespace(val=-31))
    worker._call = call
    with pytest.raises(RuntimeError, match="MOVEIT_IK_FAILED_-31"):
        worker.plan_tcp(Pose6D(frame_id="world", tcp_frame="so101_tcp", x_m=0, y_m=0,
                               z_m=0, roll_rad=0, pitch_rad=0, yaw_rad=0))
    assert captured == {"solver": 60, "service": 65.0}


def test_reset_session_is_visible_to_snapshot_without_waiting_for_timer():
    worker = object.__new__(RosTelemetryWorker)
    worker._plans = {}; worker._active_goal = object(); worker._attached = True
    worker._session_id = "before"; worker._lock = threading.Lock()
    worker._latest = TelemetrySnapshot(simulation_session_id="before")
    reset = worker.invalidate_session()
    assert worker.snapshot().simulation_session_id == reset


def test_execute_rejects_live_joint_drift_instead_of_using_stored_start():
    """A trajectory planned from A must not execute after feedback reports B."""
    async def scenario():
        worker = Worker(); service = TeleopService(worker); token = await lease(service)
        summary = PlanSummary(plan_id="plan", start_fingerprint="start-a", target_fingerprint="target", scene_revision=0, expires_at_monotonic=time.monotonic() + 30)
        worker._plans["plan"] = StoredTrajectory(summary, object(), "sim-a", 7); service._plans.put(summary)
        worker.fingerprint = "start-b"
        result = await service.command("execute", {"command_id": "execute", "lease_id": token, "plan_id": "plan"})
        assert result.succeeded is False and result.code == "PLAN_STALE_START" and worker.executed == []
    asyncio.run(scenario())


def test_execute_rejects_non_latest_plan_id():
    """The path requested by the client must be the same plan validated by PlanStore."""
    async def scenario():
        worker = Worker(); service = TeleopService(worker); token = await lease(service)
        first = PlanSummary(plan_id="first", start_fingerprint="start-a", target_fingerprint="first", scene_revision=0, expires_at_monotonic=time.monotonic() + 30)
        latest = PlanSummary(plan_id="latest", start_fingerprint="start-a", target_fingerprint="latest", scene_revision=0, expires_at_monotonic=time.monotonic() + 30)
        worker._plans["first"] = StoredTrajectory(first, object(), "sim-a", 7)
        worker._plans["latest"] = StoredTrajectory(latest, object(), "sim-a", 7); service._plans.put(latest)
        result = await service.command("execute", {"command_id": "execute-latest", "lease_id": token, "plan_id": "first"})
        assert result.succeeded is False and result.code == "PLAN_NOT_LATEST" and worker.executed == []
    asyncio.run(scenario())


def test_execute_rejects_plan_when_independently_observed_scene_revision_changes():
    """Attachment/scene changes invalidate a plan even when joints remain unchanged."""
    async def scenario():
        worker = Worker(); service = TeleopService(worker); token = await lease(service)
        summary = PlanSummary(plan_id="scene-plan", start_fingerprint="start-a", target_fingerprint="target", scene_revision=0, expires_at_monotonic=time.monotonic() + 30)
        worker._plans["scene-plan"] = StoredTrajectory(summary, object(), "sim-a", 7); service._plans.put(summary)
        worker._snapshot.scene_revision = 1
        result = await service.command("execute", {"command_id": "scene-execute", "lease_id": token, "plan_id": "scene-plan"})
        assert result.succeeded is False and result.code == "PLAN_STALE_SCENE" and worker.executed == []
    asyncio.run(scenario())


def test_scene_mutations_clear_worker_and_service_trajectory_stores():
    """A scene repair or home motion cannot leave a cached trajectory executable."""
    async def scenario():
        worker = Worker(); service = TeleopService(worker); token = await lease(service)
        summary = PlanSummary(plan_id="cached", start_fingerprint="start-a", target_fingerprint="target", scene_revision=0, expires_at_monotonic=time.monotonic() + 30)
        worker._plans["cached"] = StoredTrajectory(summary, object(), "sim-a", 7); service._plans.put(summary)
        repaired = await service.command("scene_repair", {"command_id": "repair", "lease_id": token, "confirmation": "CONFIRM SCENE_REPAIR"})
        assert repaired.succeeded and worker._plans == {} and service._plans._latest is None
        worker._plans["cached"] = StoredTrajectory(summary, object(), "sim-a", 7); service._plans.put(summary)
        homed = await service.command("robot_home", {"command_id": "home", "lease_id": token, "confirmation": "CONFIRM ROBOT_HOME"})
        assert homed.succeeded and worker._plans == {} and service._plans._latest is None
    asyncio.run(scenario())


def test_reset_revokes_old_lease_and_workflow_run():
    async def scenario():
        worker = Worker(); service = TeleopService(worker); lease_id = await lease(service)
        service._workflow["run"] = (Path("/tmp/checkpoint"), "sim-a")
        reset = await service.command("simulation_reset", {"command_id":"reset", "lease_id":lease_id, "confirmation":"CONFIRM SIMULATION_RESET"})
        assert reset.succeeded
        old = await service.command("workflow_step", {"command_id":"old", "lease_id":lease_id, "run_id":"run"})
        assert old.succeeded is False and old.code == "LEASE_REQUIRED"
        assert service._workflow == {} and worker._plans == {}
    asyncio.run(scenario())


def test_parameter_round_trip_returns_operator_targets_not_snapshot():
    """Save/load must preserve browser targets, not silently substitute live telemetry."""
    async def scenario():
        worker = Worker(); service = TeleopService(worker); token = await lease(service)
        service._parameters = Path("/tmp/so101-teleop-test-parameters.json")
        saved = await service.command("parameters_save", {"command_id": "save", "lease_id": token, "target_joints_rad": {"1": 0.1}, "target_tcp": {"x_m": 0.02}})
        loaded = await service.command("parameters_load", {"command_id": "load", "lease_id": token})
        assert saved.succeeded and loaded.succeeded
        assert loaded.data["parameters"]["target_joints_rad"] == {"1": 0.1}
        assert loaded.data["parameters"]["target_tcp"] == {"x_m": 0.02}
    asyncio.run(scenario())


def transaction_worker(*, gazebo: bool, moveit: bool, fail_owner: bool = False):
    """A narrow, synchronous ROS-worker boundary double for transaction tests."""
    worker = object.__new__(RosTelemetryWorker)
    state = {"gazebo": gazebo, "moveit": moveit, "events": []}
    worker._lock = threading.Lock(); worker._moveit_attached = None; worker._attached = gazebo
    worker._scene_revision = 0; worker._scene_tuple = None; worker._scene_stamp = 0.0
    worker.publish_attachment = lambda attach: (state["events"].append(attach), state.__setitem__("gazebo", attach))
    worker._wait_gazebo_attachment = lambda attach, timeout_s=4.0: state["gazebo"] is attach
    worker.snapshot = lambda: SimpleNamespace(gazebo_attached=state["gazebo"])
    def owner(executable, arguments, timeout_s=45.0):
        if executable == "so101_moveit_scene" and arguments[0] in ("attach", "detach") and fail_owner:
            raise RuntimeError("CPP_OWNER_FAILED_so101_moveit_scene")
        if executable == "so101_moveit_scene" and arguments[0] == "attach": state["moveit"] = True
        if executable == "so101_moveit_scene" and arguments[0] == "detach": state["moveit"] = False
        if executable == "so101_moveit_scene" and arguments[0] == "observe":
            return f"task_object_attached={'true' if state['moveit'] else 'false'}"
        return ""
    worker.package_cli = owner
    return worker, state


def test_attachment_owner_failure_rolls_back_gazebo_to_detached():
    """Attach cannot leave Gazebo attached if the separate MoveIt transaction fails."""
    worker, state = transaction_worker(gazebo=False, moveit=False, fail_owner=True)
    try:
        worker.attachment_transaction(True)
        assert False, "expected owner failure"
    except RuntimeError as error:
        assert str(error) == "MOVEIT_SCENE_OWNER_FAILED_GAZEBO_ROLLED_BACK"
    assert state["events"] == [True, False]
    assert state["gazebo"] is False
    assert worker._moveit_attached is False


def test_attachment_rejects_independent_planning_scene_mismatch():
    """A successful owner command is insufficient when its queried scene disagrees."""
    worker, state = transaction_worker(gazebo=False, moveit=False)
    original = worker.package_cli
    def mismatch(executable, arguments, timeout_s=45.0):
        if arguments == ["observe"]: return "task_object_attached=false"
        return original(executable, arguments, timeout_s)
    worker.package_cli = mismatch
    try:
        worker.attachment_transaction(True)
        assert False, "expected independent scene mismatch"
    except RuntimeError as error:
        assert str(error) == "MOVEIT_SCENE_STATE_MISMATCH_GAZEBO_ROLLED_BACK"
    assert state["events"] == [True, False]
    assert worker._moveit_attached is False


def test_detach_waits_for_both_gazebo_and_independent_moveit_scene():
    """Detach reports success only after the event and Planning Scene both say detached."""
    worker, state = transaction_worker(gazebo=True, moveit=True)
    assert worker.attachment_transaction(False) is True
    assert state["events"] == [False]
    assert state["gazebo"] is False and state["moveit"] is False
    assert worker._moveit_attached is False


def test_named_gazebo_pose_v_is_authoritative_when_ros_tf_bridge_has_no_identity():
    """Pose_V names, not an empty TF bridge frame, identify the physical cup."""
    worker = object.__new__(RosTelemetryWorker); worker._object_pose = None; worker._object_stamp = 0.0; worker._lock = threading.Lock()
    pose = SimpleNamespace(name="plastic_cup", position=SimpleNamespace(x=0.02, y=-0.28, z=0.181),
        orientation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0))
    other = SimpleNamespace(name="table", position=SimpleNamespace(x=9.0, y=9.0, z=9.0), orientation=pose.orientation)
    worker._on_gazebo_pose_v(SimpleNamespace(pose=[other, pose]))
    assert worker._object_pose is not None
    assert (worker._object_pose.x_m, worker._object_pose.y_m, worker._object_pose.z_m) == (0.02, -0.28, 0.181)


def test_durable_gazebo_attachment_relay_explicitly_observes_detached():
    worker = object.__new__(RosTelemetryWorker); worker._lock = threading.Lock(); worker._attached = None; worker._moveit_attached = None
    worker._scene_revision = 0; worker._scene_tuple = None; worker._scene_stamp = 0.0
    worker._on_gazebo_attachment_state(SimpleNamespace(data="detached"))
    assert worker._attached is False


def test_scene_revision_increments_only_after_a_new_independent_attachment_tuple():
    worker = object.__new__(RosTelemetryWorker); worker._lock = threading.Lock(); worker._scene_revision = 0; worker._scene_tuple = None; worker._scene_stamp = 0.0
    worker._record_scene_observation(False, False)
    baseline = worker._scene_revision
    worker._record_scene_observation(False, False)
    assert worker._scene_revision == baseline
    worker._record_scene_observation(True, True)
    assert worker._scene_revision == baseline + 1


def test_start_fingerprint_allows_five_urad_feedback_micro_jitter():
    baseline = _joint_fingerprint({str(index): 0.0 for index in range(1, 6)})
    jittered = _joint_fingerprint({str(index): 0.000005 for index in range(1, 6)})
    plan = PlanSummary(plan_id="jitter", start_fingerprint=baseline, target_fingerprint="t", scene_revision=0, expires_at_monotonic=time.monotonic() + 30)
    store = PlanStore(); store.put(plan)
    assert store.require_executable(jittered, 0, "jitter").plan_id == "jitter"


def test_start_fingerprint_allows_sub_milliradian_feedback_jitter_across_quantized_bins():
    baseline = _joint_fingerprint({str(index): 0.0 for index in range(1, 6)})
    jittered = _joint_fingerprint({"1": 0.0006, "2": 0.0, "3": 0.0, "4": 0.0, "5": 0.0})
    plan = PlanSummary(plan_id="sub-milliradian-jitter", start_fingerprint=baseline, target_fingerprint="t", scene_revision=0, expires_at_monotonic=time.monotonic() + 30)
    store = PlanStore(); store.put(plan)
    assert store.require_executable(jittered, 0, "sub-milliradian-jitter").plan_id == "sub-milliradian-jitter"


def test_start_fingerprint_rejects_one_milliradian_joint_drift():
    baseline = _joint_fingerprint({str(index): 0.0 for index in range(1, 6)})
    drifted = _joint_fingerprint({"1": 0.001, "2": 0.0, "3": 0.0, "4": 0.0, "5": 0.0})
    plan = PlanSummary(plan_id="drift", start_fingerprint=baseline, target_fingerprint="t", scene_revision=0, expires_at_monotonic=time.monotonic() + 30)
    store = PlanStore(); store.put(plan)
    try:
        store.require_executable(drifted, 0, "drift")
        assert False, "expected PLAN_STALE_START"
    except PlanRejected as error:
        assert str(error) == "PLAN_STALE_START"
