"""Task 8 SEARCH commands stay inside the measured, current ACT lease."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest
from sensor_msgs.msg import JointState

from so101_demo.act.head_search_binding import HeadSearchBinding
from so101_demo.act.ownership import Ownership
from so101_demo.act.task8_manifest import build_task8_live_manifest
from so101_demo.adapters.act.command_broker import CommandBroker, LocalBrokerConnection
from so101_demo.adapters.act.physics import model_sha256
from so101_demo.adapters.act.task8_search_binding import build_task8_search_adapter


def _binding():
    measured = {
        "horizontal_fov_rad": 1.0, "coarse_step_rad": 0.4,
        "search_timeout_s": 5.0, "max_age_s": 0.2, "max_skew_s": 0.02,
        "center_deadband_px": 10.0, "vertical_bounds_px": [100.0, 380.0],
        "min_area_px2": 100.0, "min_confidence": 0.6,
        "max_fine_corrections": 3, "max_fine_total_rad": 0.5,
        "lock_valid_neck_rad": [-0.2, 0.3], "submit_lead_s": 0.04,
        "stop_velocity_rad_s": 0.002, "stop_latency_s": 0.2,
    }
    motion = {"settle_velocity_rad_s": 0.01, "goal_tolerance_rad": 0.02,
              "neck_goal_duration_s": 0.5}
    camera = {"frame_id": "head_camera_frame",
              "ray_origin_frame_id": "head_camera_frame"}
    return HeadSearchBinding({}, camera, motion, measured)


def _sweep(boundary, check=None):
    return SimpleNamespace(
        model_sha256=model_sha256(boundary.model),
        check=check or (lambda *_args, **_kwargs: True),
    )


def _fixture(monkeypatch, *, epoch=1):
    import mujoco
    from pathlib import Path
    from so101_demo.adapters.act import task8_search_binding

    scene = Path(__file__).parents[1] / "assets/mujoco/act/scene.xml"
    model = mujoco.MjModel.from_xml_path(str(scene))
    manifest = build_task8_live_manifest(
        {"default": {"cup_start_m": [0.02, -0.28, 0.165], "neck_start_rad": 0.1},
         "left": {"cup_start_m": [-0.08, -0.28, 0.165], "neck_start_rad": 0.0},
         "forward": {"cup_start_m": [0.02, -0.36, 0.165], "neck_start_rad": 0.0}},
        source_sha256="a" * 64, runtime_config_sha256="b" * 64,
        collection_config_sha256="c" * 64, contact_policy_fingerprint="d" * 64,
        calibration_report_path="calibration-report.json",
        calibration_report_sha256="e" * 64,
    )
    request = {"mode": "phase_prefix", "stop_after": "SEARCH",
               "lifecycle": "FULL_RESTART", "scenario_id": "prefix-01",
               "session_id": "session-1", "attempt_id": "attempt-1",
               "deadline_ns": time.monotonic_ns() + 10_000_000_000}
    sent = []
    class Driver:
        clients = {"neck": SimpleNamespace(server_is_ready=lambda: True)}
        hazard_reason = None
        def stopped(self): return True
        def refresh_idle(self): pass
        def refresh_stop(self): pass
        def stop_all(self, _reason): pass
        def cancel(self, _goal_id): pass
        def submit(self, kind, goal):
            sent.append((kind, goal))
            return f"neck-{len(sent)}"
    broker = CommandBroker(Driver(), ownership=Ownership(), simulation_session_id="session-1")
    connection = LocalBrokerConnection(broker)
    context = connection.acquire("act", "session-1", "attempt-1")
    cancelled = threading.Event()
    world = SimpleNamespace(snapshot=lambda: SimpleNamespace(
        simulation_session_id="session-1", reset_epoch=epoch,
        simulation_step=1, paused=False,
    ))
    sources = SimpleNamespace(
        session_id="session-1", reset_epoch=1, phase="SEARCH",
        scene=SimpleNamespace(floor=1.0), world=world,
        contact_pairs=SimpleNamespace(model_sha256=model_sha256(model)),
        capture=lambda _attempt_id: {
            "world": SimpleNamespace(simulation_session_id="session-1",
                                     reset_epoch=1, simulation_step=2, paused=False),
            "scene": {"simulation_session_id": "session-1", "reset_epoch": 1,
                      "simulation_step": 2, "paused": False,
                      "qpos": tuple(model.key_qpos[0])},
        },
    )
    class Boundary:
        def __init__(self):
            self.model, self.manifest, self.sources = model, manifest, sources
            self.broker, self.act_context, self.receipt = broker, context, SimpleNamespace(new_epoch=1)
            self.cancelled = cancelled
        def _guard(self, item):
            if item != request or cancelled.is_set():
                raise RuntimeError("ACT_TASK8_CANCELLED")
            if time.monotonic_ns() >= item["deadline_ns"]:
                raise TimeoutError("ACT_DEADLINE_EXPIRED")
    boundary = Boundary()
    built = []
    class Detector:
        def reset(self): pass
    def build_detector(binding, *, snapshot_root):
        built.append((binding, snapshot_root))
        return SimpleNamespace(runtime=Detector(), snapshot_path=snapshot_root / "best.pt")
    monkeypatch.setattr(task8_search_binding, "build_bound_head_detector", build_detector)
    node = SimpleNamespace(
        create_subscription=lambda *_args: None,
        get_clock=lambda: SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=1_100_000_000)),
    )
    return node, boundary, request, sent, built, connection


def test_search_neck_uses_current_broker_ticket_and_measured_interval(monkeypatch, tmp_path):
    node, boundary, request, sent, built, connection = _fixture(monkeypatch)
    adapter = build_task8_search_adapter(
        node, boundary=boundary, binding=_binding(), request=request,
        snapshot_root=tmp_path, tf_buffer=object(),
        neck_sweep_checker=_sweep(boundary),
    )
    assert built and adapter.source_floor_s == 1.0
    joint = JointState(name=["neck_yaw_joint"], position=[0.1], velocity=[0.0])
    joint.header.stamp.sec = 1
    adapter.neck_port._joint(joint)
    assert adapter.neck_port.command_neck(
        0.2, session_id="session-1", attempt_id="attempt-1", observation_time_s=1.0,
    ) == "neck-1"
    assert len(sent) == 1 and sent[0][0] == "neck"
    with pytest.raises(PermissionError, match="SEARCH_UNSAFE_MOTION"):
        adapter.neck_port.command_neck(
            0.4, session_id="session-1", attempt_id="attempt-1", observation_time_s=1.0,
        )
    assert len(sent) == 1
    broker = boundary.broker
    broker.ownership.revoke("TEST_CANCEL")
    with pytest.raises(PermissionError, match="LEASE"):
        adapter.neck_port.command_neck(
            0.2, session_id="session-1", attempt_id="attempt-1", observation_time_s=1.0,
        )
    assert len(sent) == 1
    connection.close()


def test_search_neck_refuses_colliding_same_step_sweep_before_goal(monkeypatch, tmp_path):
    node, boundary, request, sent, _, connection = _fixture(monkeypatch)
    checks = []

    def reject(qpos, **kwargs):
        checks.append((qpos, kwargs))
        return False

    adapter = build_task8_search_adapter(
        node, boundary=boundary, binding=_binding(), request=request,
        snapshot_root=tmp_path, tf_buffer=object(),
        neck_sweep_checker=_sweep(boundary, reject),
    )
    joint = JointState(name=["neck_yaw_joint"], position=[0.1], velocity=[0.0])
    joint.header.stamp.sec = 1
    adapter.neck_port._joint(joint)
    with pytest.raises(PermissionError, match="SEARCH_UNSAFE_MOTION"):
        adapter.neck_port.command_neck(
            0.2, session_id="session-1", attempt_id="attempt-1",
            observation_time_s=1.0,
        )
    assert len(checks) == 1 and checks[0][1]["target_rad"] == 0.2
    assert checks[0][0] == tuple(boundary.model.key_qpos[0])
    assert sent == []
    connection.close()


@pytest.mark.parametrize("source_failure", ["stale_step", "unavailable"])
def test_search_neck_refuses_missing_same_step_qpos(monkeypatch, tmp_path, source_failure):
    node, boundary, request, sent, _, connection = _fixture(monkeypatch)
    original_capture = boundary.sources.capture
    if source_failure == "stale_step":
        def capture(attempt_id):
            raw = original_capture(attempt_id)
            raw["scene"]["simulation_step"] -= 1
            return raw
    else:
        def capture(_attempt_id):
            raise RuntimeError("SOURCE_STEP_MISMATCH")
    boundary.sources.capture = capture
    checks = []
    adapter = build_task8_search_adapter(
        node, boundary=boundary, binding=_binding(), request=request,
        snapshot_root=tmp_path, tf_buffer=object(),
        neck_sweep_checker=_sweep(boundary, lambda *_a, **_k: checks.append(True)),
    )
    joint = JointState(name=["neck_yaw_joint"], position=[0.1], velocity=[0.0])
    joint.header.stamp.sec = 1
    adapter.neck_port._joint(joint)
    with pytest.raises(PermissionError, match="SEARCH_UNSAFE_MOTION"):
        adapter.neck_port.command_neck(
            0.2, session_id="session-1", attempt_id="attempt-1",
            observation_time_s=1.0,
        )
    assert sent == [] and checks == []
    connection.close()


def test_search_binding_rejects_wrong_running_epoch_before_detector_load(monkeypatch, tmp_path):
    node, boundary, request, sent, built, connection = _fixture(monkeypatch, epoch=2)
    with pytest.raises(RuntimeError, match="TASK8_SEARCH_EPOCH_MISMATCH"):
        build_task8_search_adapter(node, boundary=boundary, binding=_binding(),
                                   request=request, snapshot_root=tmp_path, tf_buffer=object(),
                                   neck_sweep_checker=_sweep(boundary))
    assert not built and not sent
    connection.close()


def test_search_binding_refuses_wrong_sweep_model_before_detector_load(monkeypatch, tmp_path):
    node, boundary, request, sent, built, connection = _fixture(monkeypatch)
    sweep = _sweep(boundary)
    sweep.model_sha256 = "0" * 64
    with pytest.raises(ValueError, match="TASK8_SEARCH_BINDING_INVALID"):
        build_task8_search_adapter(
            node, boundary=boundary, binding=_binding(), request=request,
            snapshot_root=tmp_path, tf_buffer=object(), neck_sweep_checker=sweep,
        )
    assert not built and not sent
    connection.close()


def test_search_binding_rejects_nonfinite_reset_floor_before_detector_load(monkeypatch, tmp_path):
    node, boundary, request, sent, built, connection = _fixture(monkeypatch)
    boundary.sources.scene.floor = float("nan")
    with pytest.raises(RuntimeError, match="TASK8_SEARCH_RESET_FLOOR_INVALID"):
        build_task8_search_adapter(node, boundary=boundary, binding=_binding(),
                                   request=request, snapshot_root=tmp_path, tf_buffer=object(),
                                   neck_sweep_checker=_sweep(boundary))
    assert not built and not sent
    connection.close()


def test_search_tick_cancellation_stops_before_new_neck_goal(monkeypatch, tmp_path):
    node, boundary, request, sent, _, connection = _fixture(monkeypatch)
    adapter = build_task8_search_adapter(
        node, boundary=boundary, binding=_binding(), request=request,
        snapshot_root=tmp_path, tf_buffer=object(),
        neck_sweep_checker=_sweep(boundary),
    )
    boundary.cancelled.set()
    with pytest.raises(RuntimeError, match="ACT_TASK8_CANCELLED"):
        adapter.tick(safe_observe=True)
    assert not sent
    connection.close()
