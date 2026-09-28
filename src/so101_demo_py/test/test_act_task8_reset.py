"""Frozen Task 8 reset targets and authority transfer must fail closed."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import mujoco
import pytest

from so101_demo.act.ownership import Ownership
from so101_demo.act.task8_manifest import build_task8_live_manifest
from so101_demo.adapters.act.command_broker import CommandBroker, LocalBrokerConnection
from so101_demo.adapters.act.physics import model_sha256
from so101_demo.adapters.act.task8_reset import Task8ResetBoundary, task8_reset_targets


def installed_model():
    from pathlib import Path
    scene = Path(__file__).parents[1] / "assets/mujoco/act/scene.xml"
    return mujoco.MjModel.from_xml_path(str(scene))


def manifest():
    anchors = {
        "default": {"cup_start_m": [0.02, -0.28, 0.165], "neck_start_rad": 0.1},
        "left": {"cup_start_m": [-0.08, -0.28, 0.165], "neck_start_rad": 0.0},
        "forward": {"cup_start_m": [0.02, -0.36, 0.165], "neck_start_rad": 0.0},
    }
    return build_task8_live_manifest(
        anchors, source_sha256="a" * 64, runtime_config_sha256="b" * 64,
        collection_config_sha256="c" * 64, contact_policy_fingerprint="d" * 64,
        calibration_report_path="calibration-report.json",
        calibration_report_sha256="e" * 64,
    )


def request(**changes):
    result = {
        "mode": "phase_prefix", "stop_after": "SEARCH", "lifecycle": "FULL_RESTART",
        "scenario_id": "prefix-01", "session_id": "session-1", "attempt_id": "attempt-1",
        "deadline_ns": time.monotonic_ns() + 10_000_000_000,
    }
    result.update(changes)
    return result


def targets(model, frozen, case):
    return task8_reset_targets(
        model, frozen, case, expected_model_sha256=model_sha256(model),
        expected_mujoco_version=mujoco.mj_versionString(),
    )


def test_targets_use_named_compiled_keyframe_and_frozen_anchor():
    model = installed_model()
    frozen = manifest()
    first = targets(model, frozen, request())
    assert first.case_id == "prefix-01" and first.anchor == "default"
    assert first.joints_rad == (0.0,) * 6 + (0.1,)
    assert first.cup_start_m == (0.02, -0.28, 0.165)
    left = targets(model, frozen, request(
        mode="full", stop_after=None, scenario_id="full-02"))
    assert left.anchor == "left" and left.joints_rad == (0.0,) * 7
    assert left.cup_start_m == (-0.08, -0.28, 0.165)


def test_targets_reject_unfrozen_case_phase_and_model():
    model = installed_model()
    frozen = manifest()
    for case in (request(scenario_id="unknown"), request(stop_after="APPROACH"),
                 request(lifecycle="RESET_WORLD")):
        with pytest.raises(ValueError, match="TASK8_CASE"):
            targets(model, frozen, case)
    with pytest.raises(ValueError, match="TASK8_MODEL_HASH_MISMATCH"):
        task8_reset_targets(model, frozen, request(), expected_model_sha256="0" * 64,
                            expected_mujoco_version=mujoco.mj_versionString())


class Driver:
    def __init__(self):
        self.stops = []
        self.stationary = True

    def stopped(self): return self.stationary
    def refresh_stop(self): pass
    def refresh_idle(self): pass
    def stop_all(self, reason): self.stops.append(reason)


def boundary(monkeypatch, *, arm_error=False, stop_uncertain=False):
    from so101_demo.adapters.act import task8_reset

    model = installed_model()
    frozen = manifest()
    driver = Driver()
    broker = CommandBroker(driver, ownership=Ownership(), simulation_session_id="session-1")
    connection = LocalBrokerConnection(broker)
    nodes = []

    class ServiceNode:
        def destroy_node(self): nodes.append("destroyed")

    class Services:
        def __init__(self, service_node, joint_node, *, control_context,
                     broker_connection, service_timeout_s, operation_guard):
            assert broker_connection is connection
            assert control_context["owner"] == "recovery"
            operation_guard()
            nodes.append("created")

        def pause(self, paused):
            assert paused is False
            return True

    class Reset:
        def __init__(self, services, observer, *, on_reset_snapshot, **kwargs):
            self.arm = on_reset_snapshot
            assert kwargs["expected_joint_positions"] == (0.0,) * 6 + (0.1,)
            assert kwargs["expected_object_position"] == (0.02, -0.28, 0.165)
            self.last_reset_joint_snapshot = {"reset_epoch": 4}

        def reset(self, keyframe, free_joints, *, joint_overrides):
            assert keyframe == "task_start" and len(free_joints) == 1
            assert len(joint_overrides) == 7
            self.arm(SimpleNamespace(reset_epoch=4))
            return SimpleNamespace(new_epoch=4)

    class Sources:
        session_id = "session-1"
        contact_pairs = SimpleNamespace(model_sha256=model_sha256(model))
        reset_epoch = None
        world = SimpleNamespace(snapshot=lambda: SimpleNamespace(
            simulation_session_id="session-1", reset_epoch=4, simulation_step=1, paused=False))

        def arm(self, phase):
            assert phase == "SEARCH"
            if arm_error:
                if stop_uncertain:
                    driver.stationary = False
                raise RuntimeError("arm failed")
            self.reset_epoch = 4
            return 4

    monkeypatch.setattr(task8_reset, "MujocoRosClient", Services)
    monkeypatch.setattr(task8_reset, "MujocoResetClient", Reset)
    sources = Sources()
    instance = Task8ResetBoundary(
        node=object(), model=model, manifest=frozen, sources=sources,
        command_broker=broker, connection=connection, cancelled=threading.Event(),
        service_node_factory=ServiceNode, transition_timeout_s=0.02,
    )
    return instance, broker, driver, connection, nodes


def test_begin_transfers_only_after_reset_arm_running_epoch_and_stop(monkeypatch):
    instance, broker, driver, connection, nodes = boundary(monkeypatch)
    result = instance.begin(request())
    assert result == {"session_id": "session-1", "attempt_id": "attempt-1",
                      "reset_epoch": 4, "release_epoch": 0, "full_restart": False}
    assert instance.act_context["owner"] == "act"
    assert broker.ownership.state == "RUNNING" and not driver.stops
    assert nodes == ["created", "destroyed"]
    connection.close()


def test_begin_arm_failure_revokes_before_act_acquire(monkeypatch):
    instance, broker, driver, connection, nodes = boundary(monkeypatch, arm_error=True)
    with pytest.raises(RuntimeError, match="arm failed"):
        instance.begin(request())
    assert instance.act_context is None
    assert driver.stops == ["TASK8_RESET_ABORT"]
    assert nodes == ["created", "destroyed"]
    with pytest.raises(RuntimeError, match="TASK8_RESET_ALREADY_STARTED"):
        instance.begin(request())
    connection.close()


def test_begin_cancelled_before_acquire_leaves_broker_idle(monkeypatch):
    instance, broker, driver, connection, nodes = boundary(monkeypatch)
    instance.cancelled.set()
    with pytest.raises(RuntimeError, match="ACT_TASK8_CANCELLED"):
        instance.begin(request())
    assert broker.ownership.state == "IDLE" and nodes == [] and driver.stops == []
    connection.close()


def test_begin_preserves_uncertain_stop_as_failure(monkeypatch):
    instance, broker, driver, connection, nodes = boundary(
        monkeypatch, arm_error=True, stop_uncertain=True)
    with pytest.raises(RuntimeError, match="TASK8_RESET_STOP_NOT_CONFIRMED"):
        instance.begin(request())
    assert broker.ownership.state == "STOPPING"
    assert instance.act_context is None and driver.stops == ["TASK8_RESET_ABORT"]
    assert nodes == ["created", "destroyed"]
    connection.close()
