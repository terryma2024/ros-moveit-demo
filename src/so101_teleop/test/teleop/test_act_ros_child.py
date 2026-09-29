"""A ROS child routes only its own ACT work through registered methods."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid
from types import SimpleNamespace

import pytest

from so101_teleop.unified.child_runtime import ChildRuntime
from so101_teleop.unified.contracts import DispatchToken, MutationError, OwnerKey, PendingChildKey
from so101_teleop.unified.ipc import decode_request
from so101_teleop.unified.ros_child import RclpyActionDriver, act_identity_from_environment, local_owner
from so101_teleop.process_identity import read_identity
from so101_teleop.unified.bridge import BridgeLaunch, BridgeProcessOwner
from so101_teleop.unified.act_artifacts import ActArtifactBinding


class ActDriver:
    def __init__(self):
        self.seen = []
        self.fail = False

    async def pick_place_phase(self, request):
        if self.fail:
            raise RuntimeError("child crashed")
        self.seen.append((request.worker_id, request.payload["scenario_id"]))
        return {"status": "PASSED", "scenario_id": request.payload["scenario_id"]}

    async def cancel_act(self, request):
        return {"stopped_confirmed": True, "reason": request.payload["reason"]}


def request(*, worker_id="w00", generation=3, operation="task8_phase"):
    deadline = time.monotonic_ns() + 10**9
    payload = (
        {"reason": "operator"} if operation == "cancel" else
        {"scenario_id": "scene-1", "stop_after": "MICRO_LIFT", "manifest_sha256": "a" * 64,
        "support_distance_max_m": 0.02,   # the admitted support distance (P1-3)
         "runtime_config_sha256": "b" * 64, "contact_policy_fingerprint": "c" * 64,
         "stack_owner": {"pid": 12345, "pgid": 12345, "started_ticks": 101,
                         "argv_sha256": "1" * 64, "environment_sha256": "2" * 64}}
    )
    document = {
        "version": 1, "operation": operation, "command_id": "command-1",
        "deadline_ns": deadline, "service_epoch": "epoch-1", "runtime_id": "runtime-w00",
        "service_token": "private", "campaign_id": "campaign-1", "worker_id": worker_id,
        "session_id": "session-0", "attempt_id": "attempt-0", "execution_generation": generation,
        "token": {"operation_id": "operation-1", "child_id": worker_id,
                  "runtime_id": "runtime-w00", "execution_generation": generation,
                  "deadline_ns": deadline, "revocation_revision": 0},
        "payload": payload,
    }
    return decode_request(json.dumps(document).encode(), now_ns=time.monotonic_ns())


def runtime(driver):
    return ChildRuntime(
        driver, owner=OwnerKey(1, 1, 1, "a" * 64, "b" * 64),
        service_epoch="epoch-1", runtime_id="runtime-w00", normal_queue_limit=2,
        act_campaign_id="campaign-1", act_worker_id="w00", act_generation=3,
    )


def test_act_child_reads_calibration_from_one_hash_bound_no_follow_open(tmp_path):
    path = tmp_path / "calibration.json"
    path.write_text('{"status":"TASK8_READY"}')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    binding = ActArtifactBinding(
        tmp_path, (("calibration_report", path),),
        (("calibration_report", digest),), "a" * 64,
    )
    assert binding.read_hashed_json("calibration_report") == {"status": "TASK8_READY"}
    path.write_text('{"status":"CALIBRATION_REQUIRED"}')
    with pytest.raises(ValueError, match="ACT_ARTIFACT_HASH_MISMATCH"):
        binding.read_hashed_json("calibration_report")
    path.unlink()
    path.symlink_to(tmp_path / "elsewhere.json")
    with pytest.raises(ValueError, match="ACT_ARTIFACT_UNAVAILABLE"):
        binding.read_hashed_json("calibration_report")


def qualified_report(tmp_path):
    from so101_demo.act.calibration import REQUIRED_MEASUREMENTS

    sample = tmp_path / "sample.json"
    sample.write_text("measured\n")
    digest = hashlib.sha256(sample.read_bytes()).hexdigest()
    measurements = {}
    for name, (unit, size) in REQUIRED_MEASUREMENTS.items():
        value = [1.0] * size if size > 1 else 1.0
        if name == "max_fine_corrections":
            value = 3
        measurements[name] = {
            "value": value, "unit": unit, "sample_path": str(sample),
            "sample_sha256": digest,
        }
    measurements["max_age_s"]["value"] = 0.1
    measurements["max_skew_s"]["value"] = 0.005
    measurements["stop_velocity_rad_s"]["value"] = 0.01
    return {
        "schema_version": 1, "status": "QUALIFIED", "source_commit": "a" * 40,
        "config_sha256": "b" * 64, "measurements": measurements,
        # mandatory since 8P1/8P2, and a QUALIFIED report must trace to its live campaign (8P4)
        "source_provenance_sha256": "c" * 64,
        "live_campaign": {"case_root": str(tmp_path / "task8-live"),
                          "campaign_result_sha256": "d" * 64,
                          "preparation_receipt_sha256": "e" * 64,
                          "journal_sha256": ["f" * 64] * 14},
        "checks": {name: "PASS" for name in
                   ("fov", "collision", "search", "synchronization", "execution", "release", "retreat")},
    }


def test_act_child_source_limits_require_measured_calibration(tmp_path):
    from so101_teleop.unified.ros_child import bound_act_source_settings

    report = qualified_report(tmp_path)
    settings = bound_act_source_settings(report, timestep_s=0.002)
    assert settings["stop_velocity_rad_s"] == 0.01
    assert settings["max_wall_age_s"] == 0.1
    assert settings["max_source_skew_s"] == 0.005
    assert settings["max_sim_gap_s"] == pytest.approx(0.003)
    report["status"] = "CALIBRATION_REQUIRED"
    with pytest.raises(ValueError, match="CALIBRATION_REQUIRED"):
        bound_act_source_settings(report, timestep_s=0.002)


def test_non_task8_manifest_does_not_construct_a_physical_port():
    from so101_teleop.unified.ros_child import maybe_provision_pick_place_port

    class Artifacts:
        def read_hashed_json(self, name):
            assert name == "manifest"
            return {"kind": "ACT_FORMAL_COLLECTION"}

    driver = SimpleNamespace(_act_artifacts=Artifacts())
    assert maybe_provision_pick_place_port(driver) is None


def test_admitted_child_provisions_bound_sources_and_dispatcher_before_task8(tmp_path, monkeypatch):
    import rclpy
    from rclpy import executors
    from so101_demo.adapters.act import ros_broker, pick_place_sources
    from so101_teleop.unified import ros_child
    from so101_teleop.unified.controller_reservation_paths import controller_reservation_directory

    report = qualified_report(tmp_path)
    path = tmp_path / "calibration.json"
    path.write_text(json.dumps(report))
    binding = ActArtifactBinding(
        tmp_path, (("calibration_report", path),),
        (("calibration_report", hashlib.sha256(path.read_bytes()).hexdigest()),), "a" * 64,
    )
    seen = []

    class Node:
        def destroy_node(self):
            seen.append("destroy")

    class Executor:
        def add_node(self, node):
            seen.append("add_node")

        def spin(self):
            seen.append("spin")

        def shutdown(self, timeout_sec):
            seen.append("shutdown")

    class Broker:
        def __init__(self, node, *, stop_velocity_rad_s, max_age_s):
            seen.append(("broker", stop_velocity_rad_s, max_age_s))

        def submit(self, kind, goal):
            seen.append(("submit", kind))
            return "goal"

        def prepare_goal(self, kind, goal):
            raise AssertionError("goal preparation is outside this startup test")

        def send_prepared(self, goal_id, kind, goal, goal_uuid):
            raise AssertionError("goal send is outside this startup test")

        def discard_prepared(self, goal_id):
            raise AssertionError("goal discard is outside this startup test")

    class Sources:
        def __init__(self, node, broker, **kwargs):
            seen.append(("sources", kwargs))

    class Dispatcher:
        def __init__(self, sources, broker, cancelled, *, command_broker):
            assert command_broker.driver is broker
            seen.append("dispatcher")

        def start(self):
            seen.append("start_dispatcher")

        def close(self):
            seen.append("close_dispatcher")

    monkeypatch.delenv("SO101_ACT_STOP_VELOCITY_RAD_S", raising=False)
    monkeypatch.delenv("SO101_ACT_EVIDENCE_MAX_AGE_S", raising=False)
    monkeypatch.setenv("SO101_ACT_WORKER_ID", "w00")
    monkeypatch.setenv("SO101_ACT_GENERATION", "1")
    monkeypatch.setenv("SO101_SIMULATION_SESSION_ID", "session-1")
    reservation_root = Path(os.environ["TMPDIR"]).parents[2] / f"p{uuid.uuid4().hex[:8]}"
    reservation_root.mkdir(mode=0o700)
    reservation_dir = controller_reservation_directory(reservation_root, "session-1")
    monkeypatch.setenv("SO101_ACT_RESERVATION_ROOT", str(reservation_root))
    monkeypatch.setenv("SO101_ACT_CONTROLLER_RESERVATION_DIR", str(reservation_dir))
    monkeypatch.setattr(rclpy, "init", lambda: seen.append("init"))
    monkeypatch.setattr(rclpy, "create_node", lambda *args, **kwargs: Node())
    monkeypatch.setattr(rclpy, "ok", lambda: True)
    monkeypatch.setattr(rclpy, "shutdown", lambda: seen.append("rclpy_shutdown"))
    monkeypatch.setattr(executors, "SingleThreadedExecutor", Executor)
    monkeypatch.setattr(ros_broker, "RosBrokerDriver", Broker)
    monkeypatch.setattr(pick_place_sources, "PickPlaceRosEvidence", Sources)
    monkeypatch.setattr(pick_place_sources, "PickPlaceHazardDispatcher", Dispatcher)
    port = object()
    def provision_port(driver):
        seen.append("provision_port")
        assert driver._act_sources is not None
        return port
    monkeypatch.setattr(ros_child, "maybe_provision_pick_place_port", provision_port, raising=False)
    driver = object.__new__(RclpyActionDriver)
    driver._node = driver._executor = driver._thread = None
    driver._act_artifacts = binding
    driver._act_model = SimpleNamespace(opt=SimpleNamespace(timestep=0.002))
    driver._act_contact_pairs = object()
    driver._act_cancelled = threading.Event()
    driver._act_sources = driver._act_hazard_dispatcher = None
    driver._task8_port = None
    broker = driver._start_ros_broker()
    assert isinstance(broker, Broker)
    authority = driver._act_command_broker
    assert authority.driver is broker
    assert driver._act_reset_connection.broker is authority
    assert authority.simulation_session_id == "session-1"
    from so101_demo.adapters.act.trusted_visible_approach_source import (
        TrustedVisibleApproachSourcePort,
    )
    from so101_demo.act.prefix_source import PrefixSourceAuthority
    assert isinstance(driver._act_visible_source, TrustedVisibleApproachSourcePort)
    assert authority._prefix_source_port is driver._act_visible_source
    assert isinstance(authority._prefix_sources, PrefixSourceAuthority)
    assert authority._prefix_sources.max_observation_age_s == 0.1
    assert authority._prefix_sources.max_prefix_age_s == 0.1
    assert authority.ownership.state == "IDLE"
    foreign = {"protocol_version": 1, "request_id": "r", "owner": "act",
               "session_id": "foreign", "attempt_id": "a", "lease_token": "",
               "operation": "acquire"}
    assert authority.handle(foreign, "child")["error"] == "SESSION_MISMATCH"
    token = authority.ownership.acquire("act", "session-1", "a")
    old_ticket = authority.ownership.ticket(token, "act", "session-1", "a")
    authority.ownership.revoke("TEST_REVOKE")
    with pytest.raises(PermissionError):
        authority.dispatch(old_ticket, "neck", object())
    assert not any(isinstance(item, tuple) and item[0] == "submit" for item in seen)
    assert ("broker", 0.01, 0.1) in seen
    source = next(item for item in seen if isinstance(item, tuple) and item[0] == "sources")[1]
    assert source["session_id"] == "session-1"
    assert source["max_source_skew_s"] == 0.005
    assert seen.index("dispatcher") < seen.index("start_dispatcher")
    assert driver._task8_port is port
    assert seen.index("start_dispatcher") < seen.index("provision_port")
    assert sorted(path.name for path in reservation_dir.iterdir()) == [
        "arm.provision", "gripper.provision", "neck.provision"]
    assert driver._act_reservation_provisions.capabilities["arm"] != (
        driver._act_reservation_provisions.capabilities["gripper"])
    assert set(authority.reservation_port._paths) == {"arm", "gripper", "neck"}
    for role in ("arm", "gripper", "neck"):
        assert authority.reservation_port._paths[role] == reservation_dir / f"{role}.sock"
        assert authority.reservation_port._capabilities[role] == (
            reservation_dir / f"{role}.provision").read_bytes()[24:56]
    driver.close()
    assert seen.index("close_dispatcher") < seen.index("shutdown")
    assert list(reservation_dir.iterdir()) == []


def test_child_routes_only_its_own_worker_and_generation():
    driver = ActDriver()
    child = runtime(driver)
    assert asyncio.run(child.dispatch_act(request()))["scenario_id"] == "scene-1"
    assert driver.seen == [("w00", "scene-1")]
    with pytest.raises(MutationError, match="ACT_WORKER_MISMATCH"):
        asyncio.run(child.dispatch_act(request(worker_id="w01")))
    with pytest.raises(MutationError, match="ACT_GENERATION_STALE"):
        asyncio.run(child.dispatch_act(request(generation=4)))
    assert driver.seen == [("w00", "scene-1")]


def test_child_crash_fences_following_work_but_cancel_remains_available():
    driver = ActDriver()
    child = runtime(driver)
    driver.fail = True
    with pytest.raises(MutationError, match="ACT_CHILD_FAILED"):
        asyncio.run(child.dispatch_act(request()))
    driver.fail = False
    with pytest.raises(MutationError, match="ACT_CHILD_FENCED"):
        asyncio.run(child.dispatch_act(request()))
    stopped = asyncio.run(child.dispatch_act(request(operation="cancel")))
    assert stopped == {"stopped_confirmed": True, "reason": "operator"}
    assert driver.seen == []


def test_child_cancel_fences_new_work_before_stop_ack_and_after_success():
    entered = asyncio.Event()
    release = asyncio.Event()

    class SlowStopDriver(ActDriver):
        async def cancel_act(self, request):
            entered.set()
            await release.wait()
            return await super().cancel_act(request)

    driver = SlowStopDriver()
    child = runtime(driver)

    async def exercise():
        stopping = asyncio.create_task(child.dispatch_act(request(operation="cancel")))
        await entered.wait()
        with pytest.raises(MutationError, match="ACT_CHILD_FENCED"):
            await child.dispatch_act(request())
        release.set()
        assert (await stopping)["stopped_confirmed"] is True
        with pytest.raises(MutationError, match="ACT_CHILD_FENCED"):
            await child.dispatch_act(request())
        assert (await child.dispatch_act(request(operation="cancel")))["stopped_confirmed"] is True

    asyncio.run(exercise())
    assert driver.seen == []


def test_child_cancel_cannot_publish_success_from_an_inflight_phase():
    entered = asyncio.Event()
    release = asyncio.Event()

    class SlowPhaseDriver(ActDriver):
        async def pick_place_phase(self, item):
            entered.set()
            await release.wait()
            return await super().pick_place_phase(item)

    driver = SlowPhaseDriver()
    child = runtime(driver)

    async def exercise():
        running = asyncio.create_task(child.dispatch_act(request()))
        await entered.wait()
        assert (await child.dispatch_act(request(operation="cancel")))["stopped_confirmed"] is True
        release.set()
        with pytest.raises(MutationError, match="ACT_CHILD_FENCED"):
            await running

    asyncio.run(exercise())


def test_child_fences_action_uncertainty_even_when_driver_raises_mutation_error():
    class UncertainDriver(ActDriver):
        async def pick_place_phase(self, request):
            raise MutationError("ROS_GOAL_RESPONSE_UNKNOWN")

    child = runtime(UncertainDriver())
    with pytest.raises(MutationError, match="ROS_GOAL_RESPONSE_UNKNOWN"):
        asyncio.run(child.dispatch_act(request()))
    with pytest.raises(MutationError, match="ACT_CHILD_FENCED"):
        asyncio.run(child.dispatch_act(request()))


def test_web_death_asks_act_driver_to_stop_all_owned_goals():
    class StopDriver(ActDriver):
        def __init__(self):
            super().__init__()
            self.stop_reasons = []

        async def stop_act(self, reason):
            self.stop_reasons.append(reason)
            return True

    driver = StopDriver()
    child = runtime(driver)
    asyncio.run(child.mark_web_dead("web owner lost"))
    assert driver.stop_reasons == ["web owner lost"]
    with pytest.raises(MutationError, match="ACT_CHILD_FENCED"):
        asyncio.run(child.dispatch_act(request()))


def test_ros_child_requires_complete_admitted_act_identity():
    environment = {
        "SO101_ACT_CAMPAIGN_ID": "campaign-1",
        "SO101_ACT_WORKER_ID": "w00",
        "SO101_ACT_GENERATION": "3",
    }
    assert act_identity_from_environment(environment) == ("campaign-1", "w00", 3)
    assert act_identity_from_environment({}) == (None, None, None)
    with pytest.raises(MutationError, match="ACT_CHILD_IDENTITY_INCOMPLETE"):
        act_identity_from_environment({"SO101_ACT_WORKER_ID": "w00"})
    with pytest.raises(MutationError, match="ACT_CHILD_GENERATION_INVALID"):
        act_identity_from_environment(dict(environment, SO101_ACT_GENERATION="-1"))


def test_ros_child_reports_exact_kernel_owner_for_safety_channel():
    observed = read_identity(os.getpid())
    owner = local_owner("runtime-test")
    assert owner.pid == observed.pid
    assert owner.pgid == observed.pgid
    assert owner.started_ticks == observed.start_marker
    assert owner.argv_sha256 == observed.command_sha256


def test_act_bridge_ready_rejects_wrong_epoch_and_worker_identity(tmp_path):
    launch = BridgeLaunch(
        Path(sys.executable), tmp_path, "runtime-w00",
        {"SO101_CHILD_SERVICE_EPOCH": "epoch-1", "SO101_ACT_CAMPAIGN_ID": "campaign-1",
         "SO101_ACT_WORKER_ID": "w00", "SO101_ACT_GENERATION": "3"},
        tmp_path / "socket",
    )
    owner = BridgeProcessOwner(launch, object(), object())
    owner.process = SimpleNamespace(poll=lambda: None)
    owner._ready_document = {"service_epoch": "epoch-old", "runtime_id": "runtime-w00",
                             "campaign_id": "campaign-1", "worker_id": "w00",
                             "execution_generation": 3}
    assert not owner.ready()
    owner._ready_document["service_epoch"] = "epoch-1"
    owner._ready_document["worker_id"] = "w01"
    assert not owner.ready()


def test_ros_action_driver_preserves_real_acceptance_terminal_and_stop():
    owner = OwnerKey(1, 1, 1, "a" * 64, "b" * 64)
    deadline = time.monotonic_ns() + 10**9
    token = DispatchToken("operation-1", "w00", "runtime-w00", 3, deadline, 0)

    class Broker:
        def __init__(self):
            self.goal_uuid = None
            self.cancelled = []

        def submit(self, kind, goal, *, goal_uuid):
            assert kind == "arm" and goal == {"trajectory": "test-goal"}
            self.goal_uuid = goal_uuid
            return "internal-1"

        def goal_state(self, gid):
            assert gid == "internal-1"
            return {"accepted": True, "status": 4, "result": {"error_code": 0},
                    "driver_error": None, "ros_goal_uuid": self.goal_uuid.replace("-", "")}

        def refresh_idle(self):
            pass

        def stopped(self):
            return True

        def cancel(self, gid):
            self.cancelled.append(gid)

        def refresh_stop(self):
            pass

    broker = Broker()
    driver = RclpyActionDriver(broker=broker, owner=owner, stop_timeout_s=0.05)
    goal_uuid = driver.allocate_goal_uuid(PendingChildKey("operation-1", "w00", "runtime-w00", 3))
    driver.register_action(token, goal_uuid, "arm", {"trajectory": "test-goal"})
    ack = asyncio.run(driver.submit(token, goal_uuid))
    assert ack.accepted and ack.key.goal_uuid == goal_uuid
    terminal = asyncio.run(driver.terminal(goal_uuid))
    assert terminal.succeeded and terminal.stopped_confirmed and terminal.cleanup_confirmed
    assert asyncio.run(driver.cancel(goal_uuid)) is True
    assert broker.cancelled == ["internal-1"]


def test_ros_action_driver_requests_physical_stop_on_unknown_acceptance():
    owner = OwnerKey(1, 1, 1, "a" * 64, "b" * 64)
    token = DispatchToken("operation-1", "w00", "runtime-w00", 3,
                          time.monotonic_ns() + 10**9, 0)

    class Broker:
        def __init__(self):
            self.stop_reasons = []

        def submit(self, kind, goal, *, goal_uuid):
            return "internal-1"

        def goal_state(self, gid):
            return {"accepted": None, "driver_error": "GOAL_RESPONSE_LOST"}

        def stop_all(self, reason):
            self.stop_reasons.append(reason)

    broker = Broker()
    driver = RclpyActionDriver(broker=broker, owner=owner)
    goal_uuid = driver.allocate_goal_uuid(PendingChildKey("operation-1", "w00", "runtime-w00", 3))
    driver.register_action(token, goal_uuid, "arm", object())
    with pytest.raises(MutationError, match="ROS_GOAL_RESPONSE_UNKNOWN"):
        asyncio.run(driver.submit(token, goal_uuid))
    assert broker.stop_reasons == ["ROS_GOAL_RESPONSE_UNKNOWN"]


def test_ros_action_driver_requests_stop_when_send_result_is_unknown():
    owner = OwnerKey(1, 1, 1, "a" * 64, "b" * 64)
    token = DispatchToken("operation-1", "w00", "runtime-w00", 3,
                          time.monotonic_ns() + 10**9, 0)

    class Broker:
        def __init__(self):
            self.stop_reasons = []

        def submit(self, kind, goal, *, goal_uuid):
            raise RuntimeError("goal send uncertain")

        def stop_all(self, reason):
            self.stop_reasons.append(reason)

    broker = Broker()
    driver = RclpyActionDriver(broker=broker, owner=owner)
    goal_uuid = driver.allocate_goal_uuid(PendingChildKey("operation-1", "w00", "runtime-w00", 3))
    driver.register_action(token, goal_uuid, "arm", object())
    with pytest.raises(MutationError, match="ROS_GOAL_SEND_UNKNOWN"):
        asyncio.run(driver.submit(token, goal_uuid))
    assert broker.stop_reasons == ["ROS_GOAL_SEND_UNKNOWN"]


def test_act_task8_child_refuses_missing_phase_port_before_motion():
    driver = RclpyActionDriver(broker=object())
    with pytest.raises(MutationError, match="ACT_TASK8_PORT_NOT_PROVISIONED"):
        asyncio.run(driver.pick_place_phase(request()))


def test_act_task8_child_rejects_failed_startup_proof_before_reset_and_replay():
    class Port:
        def __init__(self):
            self.begins = 0

        def begin(self, _request):
            self.begins += 1
            raise AssertionError("reset must not begin")

    port = Port()
    attempts = []

    def reject(_request):
        attempts.append("consumed")
        raise MutationError("TASK8_STARTUP_PROOF_INVALID")

    driver = RclpyActionDriver(
        broker=object(), task8_port=port, startup_proof_consumer=reject,
        act_hashes={"manifest_sha256": "a" * 64, "runtime_config_sha256": "b" * 64,
                    "contact_policy_fingerprint": "c" * 64},
    )
    child_request = request()
    with pytest.raises(MutationError, match="TASK8_STARTUP_PROOF_INVALID"):
        asyncio.run(driver.pick_place_phase(child_request))
    assert port.begins == 0 and attempts == ["consumed"]
    with pytest.raises(MutationError, match="TASK8_STARTUP_PROOF_ALREADY_CONSUMED"):
        asyncio.run(driver.pick_place_phase(child_request))
    assert port.begins == 0 and attempts == ["consumed"]


def test_act_task8_child_refuses_port_without_receipt_binding_before_reset():
    class Port:
        def __init__(self):
            self.begins = 0

        def begin(self, _request):
            self.begins += 1
            raise AssertionError("reset must not begin")

    port = Port()
    driver = RclpyActionDriver(
        broker=object(), task8_port=port,
        startup_proof_consumer=lambda _request: {"schema_version": 1},
        act_hashes={"manifest_sha256": "a" * 64, "runtime_config_sha256": "b" * 64,
                    "contact_policy_fingerprint": "c" * 64},
    )
    with pytest.raises(MutationError, match="ACT_TASK8_PORT_INVALID"):
        asyncio.run(driver.pick_place_phase(request()))
    assert port.begins == 0


def test_act_task8_child_routes_closed_hashes_to_runner_and_confirms_stop():
    class Broker:
        def __init__(self):
            self.reasons = []

        def stop_all(self, reason):
            self.reasons.append(reason)

        def refresh_stop(self):
            pass

        def stopped(self):
            return True

    class Port:
        def __init__(self):
            self.phases = []
            self.stops = []
            self.startup_receipt = None
            self.physics_step = 0

        def bind_startup_receipt(self, receipt):
            self.startup_receipt = receipt

        def begin(self, req):
            assert self.startup_receipt == {"schema_version": 1}
            return {"session_id": req["session_id"], "attempt_id": req["attempt_id"],
                    "reset_epoch": 1, "release_epoch": 0, "full_restart": True}

        def run_phase(self, phase, req):
            self.phases.append(phase)
            self.physics_step += 1
            return {
                "phase": phase, "session_id": req["session_id"], "attempt_id": req["attempt_id"],
                "reset_epoch": 1, "release_epoch": 0,
                "physics_step": self.physics_step,
                "planning_ok": True, "controller_reference_ok": True,
                "joint_feedback_ok": True, "contact_ok": True, "mujoco_ok": True,
                "planning_scene_ok": True, "head_rgb_ok": True, "wrist_rgb_ok": True,
                "manual_intervention": False, "moveit_recovery": False,
                "holding_state": "EMPTY", "bilateral_contact": phase == "CLOSE",
                "micro_lift_confirmed": False, "cup_off_table": False,
                "cup_supported": True, "released": False,
                "no_fingertip_contact": True, "placement_stable": False, "retreat_stable": False,
            }

        def safe_stop(self, reason, req):
            self.stops.append(reason)
            return True

    broker, port = Broker(), Port()
    driver = RclpyActionDriver(
        broker=broker, task8_port=port,
        startup_proof_consumer=lambda _request: {"schema_version": 1},
        act_hashes={"manifest_sha256": "a" * 64, "runtime_config_sha256": "b" * 64,
                    "contact_policy_fingerprint": "c" * 64},
    )
    child_request = request()
    with pytest.raises(MutationError, match="ACT_TASK8_HASH_MISMATCH"):
        bad = child_request.model_copy(update={"payload": {**child_request.payload,
            "contact_policy_fingerprint": "d" * 64}})
        asyncio.run(driver.pick_place_phase(bad))
    assert port.phases == []
    # Prefix through CLOSE needs only three phases, then a physical stop.
    close_request = child_request.model_copy(update={"payload": {**child_request.payload,
        "stop_after": "CLOSE"}})
    result = asyncio.run(driver.pick_place_phase(close_request))
    assert result["completed_phases"] == ["SEARCH", "APPROACH", "CLOSE"]
    assert result["formal_episode_eligible"] is False
    assert port.stops == ["PHASE_PREFIX_COMPLETE"]
    assert broker.reasons == ["TASK8_COMPLETED"]
    assert asyncio.run(driver.cancel_act(request(operation="cancel"))) == {
        "stopped_confirmed": True, "reason": "operator"}


def test_act_cancel_interrupts_next_phase_while_runner_thread_is_busy():
    entered, release = threading.Event(), threading.Event()

    class Broker:
        def __init__(self):
            self.reasons = []

        def stop_all(self, reason):
            self.reasons.append(reason)

        def refresh_stop(self):
            pass

        def stopped(self):
            return True

    class BlockingPort:
        def __init__(self):
            self.phases = []
            self.stops = []
            self.startup_receipt = None

        def bind_startup_receipt(self, receipt):
            self.startup_receipt = receipt

        def begin(self, req):
            assert self.startup_receipt == {"schema_version": 1}
            return {"session_id": req["session_id"], "attempt_id": req["attempt_id"],
                    "reset_epoch": 1, "release_epoch": 0, "full_restart": True}

        def run_phase(self, phase, req):
            self.phases.append(phase)
            entered.set()
            assert release.wait(2)
            return {}

        def safe_stop(self, reason, req):
            self.stops.append(reason)
            return True

    broker, port = Broker(), BlockingPort()
    driver = RclpyActionDriver(
        broker=broker, task8_port=port,
        startup_proof_consumer=lambda _request: {"schema_version": 1},
        act_hashes={"manifest_sha256": "a" * 64, "runtime_config_sha256": "b" * 64,
                    "contact_policy_fingerprint": "c" * 64},
    )

    async def run():
        pending = asyncio.create_task(driver.pick_place_phase(request()))
        assert await asyncio.to_thread(entered.wait, 1)
        canceled = await driver.cancel_act(request(operation="cancel"))
        release.set()
        with pytest.raises(MutationError, match="ACT_TASK8_FAILED"):
            await pending
        return canceled

    assert asyncio.run(run())["stopped_confirmed"] is True
    assert port.phases == ["SEARCH"]
    assert port.stops == ["TASK8_ABORT"]
    assert broker.reasons == ["operator", "TASK8_FAILED"]


def test_act_cancel_revokes_current_broker_ticket_before_driver_stop():
    from so101_demo.act.ownership import Ownership
    from so101_demo.adapters.act.command_broker import CommandBroker

    class BrokerDriver:
        hazard_reason = None

        def __init__(self):
            self.authority = None
            self.stop_states = []
            self.submissions = []

        def stopped(self): return True
        def refresh_stop(self): pass
        def refresh_idle(self): pass
        def stop_all(self, reason):
            self.stop_states.append((reason, self.authority.ownership.state))
        def submit(self, kind, goal):
            self.submissions.append(kind)
            return "neck-goal"

    physical = BrokerDriver()
    authority = CommandBroker(physical, ownership=Ownership(),
                              simulation_session_id="session-0")
    physical.authority = authority
    token = authority.ownership.acquire("act", "session-0", "attempt-0")
    old_ticket = authority.ownership.ticket(token, "act", "session-0", "attempt-0")
    driver = RclpyActionDriver(broker=physical, stop_timeout_s=0.02)
    driver._act_command_broker = authority

    assert asyncio.run(driver.cancel_act(request(operation="cancel"))) == {
        "stopped_confirmed": True, "reason": "operator",
    }
    assert physical.stop_states == [("operator", "STOPPING")]
    assert authority.ownership.state == "IDLE"
    with pytest.raises(PermissionError, match="LEASE"):
        authority.dispatch(old_ticket, "neck", object())
    assert not physical.submissions
