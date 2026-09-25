"""Lossless, fail-closed live contact chunk ingestion without a ROS process."""

import json
from types import SimpleNamespace as NS

import pytest

from so101_demo.act.contact_live import (
    LivePhysicsStream, LiveContactObserver, RosLiveContactAdapter, chunk_from_ros,
)


LIMITS = {"maximum_force_n": 11.6, "maximum_displacement_m": .03,
          "maximum_ros_skew_s": .02, "maximum_receipt_age_s": .2}


def _step(number, *, force=0.0):
    left = [{"robot_geom": "fixed_fingertip_pad_collision_006",
             "object_body": "plastic_cup", "normal_force_n": force,
             "signed_distance_m": -.0001}] if force else []
    return {
        "simulation_session_id": "session-live-a", "reset_epoch": 1,
        "physics_step": number, "simulation_time_s": number * .002,
        "model_qpos": [.02, -.28, .165], "model_qvel": [0., 0., 0.],
        "cup_position_m": [.02, -.28, .165], "cup_velocity_m_s": [0., 0., 0.],
        "left_contacts": left, "right_contacts": [], "other_contacts": [],
        "truncated": False, "diagnostic_hazard_breached": False,
    }


def _chunk(sequence, *steps):
    return {
        "chunk_sequence": sequence, "simulation_session_id": "session-live-a",
        "reset_epoch": 1, "first_physics_step": steps[0]["physics_step"],
        "last_physics_step": steps[-1]["physics_step"],
        "first_simulation_time_s": steps[0]["simulation_time_s"],
        "last_simulation_time_s": steps[-1]["simulation_time_s"],
        "failed_publish_attempts": 0, "evidence_loss": False,
        "samples": list(steps),
    }


def _stream(tmp_path):
    ticks = iter((1000.0 + index * .001 for index in range(100)))
    return LivePhysicsStream(
        session_id="session-live-a", reset_epoch=1, model_sha256="a" * 64,
        model_nq=3, model_nv=3, cup_qpos_address=0, cup_qvel_address=0,
        diagnostic_limits=LIMITS, output_path=tmp_path / "physics.ndjson",
        monotonic=lambda: next(ticks),
    )


def test_live_chunk_stream_persists_contiguous_raw_state(tmp_path):
    recorder = _stream(tmp_path)
    recorder.accept_chunk(_chunk(1, _step(1), _step(2)), ros_time_s=.004)
    recorder.accept_chunk(_chunk(2, _step(3)), ros_time_s=.006)
    recorder.close()
    rows = [json.loads(line) for line in (tmp_path / "physics.ndjson").read_text().splitlines()]
    assert [row["physics_step"] for row in rows] == [1, 2, 3]
    assert all(row["model_qpos"] == [.02, -.28, .165] for row in rows)
    assert all(row["simulation_session_id"] == "session-live-a" and
               row["reset_epoch"] == 1 and row["model_sha256"] == "a" * 64
               for row in rows)
    assert recorder.recorded_steps == 3


def test_live_release_requires_prior_bilateral_contact_and_measured_open_stop(tmp_path):
    ticks = iter((1000.0 + index * .001 for index in range(100)))
    recorder = LivePhysicsStream(
        session_id="session-live-a", reset_epoch=1, model_sha256="a" * 64,
        model_nq=4, model_nv=4, cup_qpos_address=0, cup_qvel_address=0,
        release_qpos_address=3, release_qvel_address=3, release_open_q6=.465,
        diagnostic_limits=LIMITS, output_path=tmp_path / "release.ndjson",
        monotonic=lambda: next(ticks),
    )
    first = _step(1)
    first["model_qpos"].append(.1)
    first["model_qvel"].append(0.)
    first["other_contacts"] = [{"robot_geom": "table_collision", "object_body": "plastic_cup",
                                "normal_force_n": .1, "signed_distance_m": -.0001}]
    second = _step(2, force=.4)
    second["model_qpos"].append(.1)
    second["model_qvel"].append(0.)
    second["right_contacts"] = [{"robot_geom": "moving_fingertip_pad_collision_000",
                                 "object_body": "plastic_cup", "normal_force_n": .4,
                                 "signed_distance_m": -.0001}]
    third = _step(3)
    third["model_qpos"].append(.465)
    third["model_qvel"].append(.01)
    third["other_contacts"] = first["other_contacts"]
    fourth = _step(4)
    fourth["model_qpos"].append(.465)
    fourth["model_qvel"].append(0.)
    fourth["other_contacts"] = first["other_contacts"]
    recorder.accept_chunk(_chunk(1, first, second, third, fourth), ros_time_s=.008)
    recorder.close()
    rows = [json.loads(line) for line in (tmp_path / "release.ndjson").read_text().splitlines()]
    assert [row["released"] for row in rows] == [False, False, False, True]


@pytest.mark.parametrize("damage", ["gap", "session", "loss", "truncated", "force", "state"])
def test_live_chunk_stream_latches_damage_and_retains_prefix(tmp_path, damage):
    recorder = _stream(tmp_path)
    recorder.accept_chunk(_chunk(1, _step(1)), ros_time_s=.002)
    bad = _chunk(2, _step(2))
    if damage == "gap":
        bad["samples"][0]["physics_step"] = 3
        bad["first_physics_step"] = bad["last_physics_step"] = 3
    elif damage == "session":
        bad["samples"][0]["simulation_session_id"] = "other-session"
    elif damage == "loss":
        bad["evidence_loss"] = True
    elif damage == "truncated":
        bad["samples"][0]["truncated"] = True
    elif damage == "force":
        bad["samples"][0]["left_contacts"] = [
            {"robot_geom": "fixed_fingertip_pad_collision_006", "object_body": "plastic_cup",
             "normal_force_n": 12.0, "signed_distance_m": -.001}]
    else:
        bad["samples"][0]["model_qpos"][0] = .04
    with pytest.raises(ValueError):
        recorder.accept_chunk(bad, ros_time_s=.004)
    assert recorder.hazard is not None
    with pytest.raises(ValueError):
        recorder.accept_chunk(_chunk(2, _step(2)), ros_time_s=.004)
    recorder.close()
    rows = [json.loads(line) for line in (tmp_path / "physics.ndjson").read_text().splitlines()]
    assert [row["physics_step"] for row in rows] == [1]


def test_live_chunk_checks_displacement_from_first_step_within_same_chunk(tmp_path):
    recorder = _stream(tmp_path)
    moved = _step(2)
    moved["cup_position_m"][0] = .051
    moved["model_qpos"][0] = .051
    with pytest.raises(ValueError, match="displacement"):
        recorder.accept_chunk(_chunk(1, _step(1), moved), ros_time_s=.004)
    assert recorder.recorded_steps == 0
    recorder.close()


def test_live_chunk_requires_current_ros_clock(tmp_path):
    recorder = _stream(tmp_path)
    with pytest.raises(ValueError, match="ROS"):
        recorder.accept_chunk(_chunk(1, _step(1)))
    assert recorder.hazard is not None
    recorder.close()


def _ros_contact(geom):
    return NS(body1="plastic_cup", geom1="cup_collision", body2="gripper",
              geom2=geom, normal_force_n=.5, signed_distance_m=-.0001)


def _ros_chunk():
    step = NS(simulation_session_id="session-live-a", reset_epoch=1,
              physics_step=1, simulation_time_s=.002,
              model_qpos=[.02, -.28, .165], model_qvel=[0., 0., 0.],
              object_pose_world=NS(position=NS(x=.02, y=-.28, z=.165)),
              left_fingertip_contacts=[_ros_contact("fixed_fingertip_pad_collision_006")],
              right_fingertip_contacts=[], other_object_contacts=[],
              maximum_normal_force_n=.5, global_max_single_contact_force_n=.5,
              total_normal_force_n=.5,
              truncated=False, diagnostic_hazard_breached=False)
    return NS(chunk_sequence=0, simulation_session_id="session-live-a", reset_epoch=1,
              first_physics_step=1, last_physics_step=1,
              first_simulation_time_s=.002, last_simulation_time_s=.002,
              failed_publish_attempts=0, evidence_loss=False, samples=[step])


def test_ros_chunk_converter_checks_same_step_state_and_contact_identity(tmp_path):
    message = _ros_chunk()
    chunk = chunk_from_ros(message, cup_qpos_address=0, cup_qvel_address=0)
    recorder = _stream(tmp_path)
    recorder.accept_chunk(chunk, ros_time_s=.002)
    recorder.close()
    row = json.loads((tmp_path / "physics.ndjson").read_text())
    assert row["left_contacts"][0]["robot_geom"] == "fixed_fingertip_pad_collision_006"


def test_ros_chunk_converter_accepts_post_step_pose_and_rejects_stale_derived_pose():
    message = _ros_chunk()
    sample = message.samples[0]
    sample.model_qpos[2] = .165 - .00000981
    with pytest.raises(ValueError, match="live object pose disagrees with MuJoCo state"):
        chunk_from_ros(message, cup_qpos_address=0, cup_qvel_address=0)
    sample.object_pose_world.position.z = sample.model_qpos[2]
    converted = chunk_from_ros(message, cup_qpos_address=0, cup_qvel_address=0)
    assert converted["samples"][0]["cup_position_m"][2] == sample.model_qpos[2]


@pytest.mark.parametrize("damage", ["body", "category", "force", "total", "pose", "state"])
def test_ros_chunk_converter_rejects_misbound_evidence(damage):
    message = _ros_chunk()
    sample = message.samples[0]
    if damage == "body":
        sample.left_fingertip_contacts[0].body1 = "wrong"
    elif damage == "category":
        sample.left_fingertip_contacts[0].geom2 = "table_collision"
    elif damage == "force":
        sample.maximum_normal_force_n = .1
    elif damage == "total":
        sample.total_normal_force_n = .1
    elif damage == "pose":
        sample.object_pose_world.position.x = .03
    else:
        sample.model_qpos = []
    with pytest.raises(ValueError):
        chunk_from_ros(message, cup_qpos_address=0, cup_qvel_address=0)


def _observer(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    now = [1000.0]
    aborts = []
    recorder = LivePhysicsStream(
        session_id="session-live-a", reset_epoch=1, model_sha256="a" * 64,
        model_nq=3, model_nv=3, cup_qpos_address=0, cup_qvel_address=0,
        diagnostic_limits=LIMITS, output_path=tmp_path / "observer.ndjson",
        monotonic=lambda: now[0],
    )
    observer = LiveContactObserver(
        recorder, ros_clock=lambda: .002, monotonic=lambda: now[0],
        on_abort=aborts.append,
    )
    return observer, now, aborts


def test_live_observer_aborts_and_preserves_recorded_prefix(tmp_path):
    observer, now, aborts = _observer(tmp_path)
    observer.accept_chunk(_ros_chunk())
    now[0] += .001
    bad = _ros_chunk()
    bad.chunk_sequence = 1
    bad.samples[0].physics_step = 2
    bad.first_physics_step = bad.last_physics_step = 2
    bad.evidence_loss = True
    observer.accept_chunk(bad)
    assert len(aborts) == 1 and observer.hazard is not None
    observer.accept_chunk(_ros_chunk())
    assert len(aborts) == 1
    observer.close()
    assert len((tmp_path / "observer.ndjson").read_text().splitlines()) == 1


def test_live_observer_hazard_latch_and_stale_stream_abort(tmp_path):
    observer, now, aborts = _observer(tmp_path)
    observer.accept_hazard(NS(simulation_session_id="session-live-a", reset_epoch=1,
                              physics_step=1, force_n=12.0, threshold_n=11.6,
                              evidence_loss=False))
    assert len(aborts) == 1
    observer.close()

    stale, now, aborts = _observer(tmp_path / "stale")
    now[0] += .201
    stale.poll()
    assert aborts == []
    stale.start()
    now[0] += .201
    stale.poll()
    assert aborts == ["LIVE_CONTACT_EVIDENCE_STALE"]
    stale.close()


def test_live_observer_rearms_receipt_deadline_after_authoritative_pause(tmp_path):
    observer, now, aborts = _observer(tmp_path)
    observer.accept_chunk(_ros_chunk())
    observer.suspend()
    now[0] += 5.
    observer.poll()
    assert aborts == []
    observer.start()
    now[0] += .199
    observer.poll()
    assert aborts == []
    now[0] += .002
    observer.poll()
    assert aborts == ["LIVE_CONTACT_EVIDENCE_STALE"]
    observer.close()


def test_live_observer_accepts_first_contiguous_chunk_after_paused_gap(tmp_path):
    observer, now, aborts = _observer(tmp_path)
    observer.accept_chunk(_ros_chunk())
    observer.suspend()
    now[0] += 5.
    observer.start()
    now[0] += .01
    next_chunk = _ros_chunk()
    next_chunk.chunk_sequence = 1
    next_chunk.samples[0].physics_step = 2
    next_chunk.samples[0].simulation_time_s = .004
    next_chunk.first_physics_step = next_chunk.last_physics_step = 2
    next_chunk.first_simulation_time_s = next_chunk.last_simulation_time_s = .004
    observer.accept_chunk(next_chunk)
    assert aborts == []
    assert observer.recorder.recorded_steps == 2
    observer.close()


def test_live_observer_keeps_running_receipt_gap_fail_closed(tmp_path):
    observer, now, aborts = _observer(tmp_path)
    observer.accept_chunk(_ros_chunk())
    now[0] += .201
    next_chunk = _ros_chunk()
    next_chunk.chunk_sequence = 1
    next_chunk.samples[0].physics_step = 2
    next_chunk.samples[0].simulation_time_s = .004
    next_chunk.first_physics_step = next_chunk.last_physics_step = 2
    next_chunk.first_simulation_time_s = next_chunk.last_simulation_time_s = .004
    observer.accept_chunk(next_chunk)
    assert aborts == ["LIVE_CONTACT_EVIDENCE_INVALID:live physics evidence is stale"]
    assert observer.recorder.recorded_steps == 1
    observer.close()


def test_ros_adapter_subscribes_once_and_closes_owned_handles(tmp_path):
    observer, _, aborts = _observer(tmp_path)

    class Node:
        def __init__(self):
            self.subscriptions = []
            self.destroyed = []
            self.timer = None

        def create_subscription(self, kind, topic, callback, qos):
            handle = (kind, topic, callback, qos)
            self.subscriptions.append(handle)
            return handle

        def create_timer(self, period, callback):
            self.timer = (period, callback)
            return self.timer

        def destroy_subscription(self, handle):
            self.destroyed.append(handle)

        def destroy_timer(self, handle):
            self.destroyed.append(handle)

    node = Node()
    adapter = RosLiveContactAdapter(node, observer)
    assert [part[1] for part in node.subscriptions] == [
        "/so101/simulation/physics_step_chunks", "/so101/simulation/physics_hazard"
    ]
    assert node.timer is None
    node.subscriptions[0][2](_ros_chunk())
    node.subscriptions[1][2](NS(simulation_session_id="session-live-a", reset_epoch=1,
                                physics_step=1, force_n=12.0, threshold_n=11.6,
                                evidence_loss=False))
    assert len(aborts) == 1
    adapter.close()
    assert len(node.destroyed) == 2
