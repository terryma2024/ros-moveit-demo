"""The Teacher's cup pose from the simulator on a randomised indoor episode, and the camera-versus-truth check (indoor P3, T2, decision D2)."""

from __future__ import annotations

import json
import math
from types import SimpleNamespace

import pytest

from so101_demo.act import appearance_plan as ap
from so101_demo.core.task_geometry import Pose7
from so101_demo.runtime.container_campaign import privileged_pose as module
from so101_demo.runtime.parallel_ros_ports.observations import AdmittedPose

SESSION = "act-session-1"
LEASE = SimpleNamespace(attempt_id="p3-007-lease-1", point_id="p3-007")
CAMERA = (0.02011, -0.22044, 0.165)
TRUTH = (0.02007, -0.21994, 0.16485)


def chain(camera=CAMERA, epoch="reset-3"):
    return AdmittedPose("world", 123_000_000_000, 5.0, Pose7((*camera, 0.0, 0.0, 0.0, 1.0)), epoch, object())


def evidence(truth=TRUTH, *, epoch=3, session=SESSION, paused=True):
    calls = []

    def read(session_id):
        calls.append(session_id)
        return SimpleNamespace(simulation_session_id=session, reset_epoch=epoch, paused=paused, simulation_time_s=1.25,
                               object_state=SimpleNamespace(position_world=truth))

    read.calls = calls
    return read


def source(kind, teacher_source, tmp_path=None, **kwargs):
    return module.PoseSource(source=teacher_source, kind=kind, rig="side-wrist-indoor", evidence=kwargs.pop("evidence", evidence()),
                             session_id=SESSION, tolerance_m=0.010, **({} if tmp_path is None else dict(record_directory=tmp_path, task_id="task-7")),
                             **kwargs)


def test_a_privileged_episode_is_given_the_simulator_position_and_the_orientation_the_camera_pose_always_has(tmp_path):
    read = evidence()
    item = source(ap.KIND_RANDOMISED, ap.TEACHER_SOURCE_PRIVILEGED, tmp_path, evidence=read)
    original = chain()
    given = item(LEASE, original)
    assert given.pose_world.values == (*TRUTH, 0.0, 0.0, 0.0, 1.0)
    assert (given.frame_id, given.source_stamp_ns, given.reset_epoch, given.localized) == (
        original.frame_id, original.source_stamp_ns, original.reset_epoch, original.localized)
    assert original.pose_world.values[:3] == CAMERA and read.calls == [SESSION]
    record = json.loads((tmp_path / "task-7.teacher-source.json").read_text())
    assert record["teacher_source"] == "privileged_pose" and record["applied"] is True and record["episode_kind"] == "randomised"
    assert record["camera_position_m"] == list(CAMERA) and record["truth_position_m"] == list(TRUTH)
    assert record["published_position_m"] == list(TRUTH) and record["scene_id"] == "p3-007" and record["reset_epoch"] == 3
    assert record["xy_error_m"] == pytest.approx(math.hypot(CAMERA[0] - TRUTH[0], CAMERA[1] - TRUTH[1])) and record["within_tolerance"] is True


def test_a_camera_episode_keeps_its_pose_and_records_the_check_against_the_simulator(tmp_path):
    item = source(ap.KIND_NOMINAL, ap.TEACHER_SOURCE_CAMERA, tmp_path)
    original = chain()
    assert item(LEASE, original) is original
    record = json.loads((tmp_path / "task-7.teacher-source.json").read_text())
    assert record["teacher_source"] == "camera_rgbd" and record["applied"] is False and "published_position_m" not in record
    assert record["within_tolerance"] is True and record["tolerance_m"] == 0.010


def test_a_camera_pose_off_by_more_than_the_start_tolerance_is_recorded_not_replaced_on_a_nominal_episode(tmp_path):
    item = source(ap.KIND_NOMINAL, ap.TEACHER_SOURCE_CAMERA, tmp_path)
    off = chain((CAMERA[0] + 0.02, CAMERA[1], CAMERA[2]))
    assert item(LEASE, off) is off
    assert item.record["within_tolerance"] is False and item.record["xy_error_m"] > 0.010


def test_the_camera_pose_off_the_truth_is_recorded_on_a_privileged_episode_and_the_truth_is_still_what_is_published(tmp_path):
    item = source(ap.KIND_RANDOMISED, ap.TEACHER_SOURCE_PRIVILEGED, tmp_path)
    given = item(LEASE, chain((CAMERA[0] + 0.05, CAMERA[1], CAMERA[2])))
    assert given.pose_world.values[:3] == TRUTH and item.record["within_tolerance"] is False


def test_the_privileged_pose_is_allowed_only_on_a_randomised_episode_of_the_indoor_rig():
    ok = dict(evidence=evidence(), session_id=SESSION, tolerance_m=0.01)
    module.PoseSource(source=ap.TEACHER_SOURCE_PRIVILEGED, kind=ap.KIND_RANDOMISED, rig="side-wrist-indoor", **ok)
    for rig, kind, teacher_source in (("side-wrist-indoor", ap.KIND_NOMINAL, ap.TEACHER_SOURCE_PRIVILEGED),
                                      ("side-wrist", ap.KIND_RANDOMISED, ap.TEACHER_SOURCE_PRIVILEGED),
                                      ("head-wrist", ap.KIND_RANDOMISED, ap.TEACHER_SOURCE_PRIVILEGED),
                                      ("side-wrist-indoor", ap.KIND_RANDOMISED, ap.TEACHER_SOURCE_CAMERA),
                                      ("side-wrist-indoor", ap.KIND_RANDOMISED, "other")):
        with pytest.raises(module.PrivilegedPoseRefused, match="TEACHER_SOURCE_NOT_ALLOWED"):
            module.PoseSource(source=teacher_source, kind=kind, rig=rig, **ok)


def test_evidence_of_another_session_epoch_or_an_unpaused_state_is_refused(tmp_path):
    for read in (evidence(session="other"), evidence(epoch=4), evidence(paused=False)):
        item = source(ap.KIND_RANDOMISED, ap.TEACHER_SOURCE_PRIVILEGED, None, evidence=read)
        with pytest.raises(module.PrivilegedPoseRefused, match="PRIVILEGED_POSE_EVIDENCE_NOT_THIS_EPISODE"):
            item(LEASE, chain())
        assert item.record is None


def test_the_record_is_written_once_and_a_non_finite_pose_is_refused(tmp_path):
    item = source(ap.KIND_RANDOMISED, ap.TEACHER_SOURCE_PRIVILEGED, tmp_path)
    item(LEASE, chain())
    with pytest.raises(FileExistsError):
        item(LEASE, chain())
    bad = source(ap.KIND_RANDOMISED, ap.TEACHER_SOURCE_PRIVILEGED, evidence=evidence((math.nan, 0.0, 0.1)))
    with pytest.raises(ValueError, match="PRIVILEGED_POSE_NON_FINITE"):
        bad(LEASE, chain())


def test_the_agreement_is_a_pure_xy_distance_against_the_tolerance():
    near = module.agreement((0.0, 0.0, 0.165), (0.003, 0.004, 0.16), 0.010)
    assert near["xy_error_m"] == pytest.approx(0.005) and near["within_tolerance"] is True and near["z_error_m"] == pytest.approx(0.005)
    assert module.agreement((0.0, 0.0, 0.165), (0.010, 0.0, 0.165), 0.010)["within_tolerance"] is True
    assert module.agreement((0.0, 0.0, 0.165), (0.0101, 0.0, 0.165), 0.010)["within_tolerance"] is False
    for bad in (((0, 0), (0, 0, 0), 0.01), ((0, 0, 0), (0, 0, 0), 0.0)):
        with pytest.raises(ValueError, match="PRIVILEGED_POSE_AGREEMENT_INVALID"):
            module.agreement(*bad)


def test_the_source_needs_both_or_neither_of_the_record_arguments():
    with pytest.raises(ValueError, match="PRIVILEGED_POSE_CONFIG_INVALID"):
        module.PoseSource(source=ap.TEACHER_SOURCE_CAMERA, kind=ap.KIND_NOMINAL, rig="side-wrist-indoor", evidence=evidence(),
                          session_id=SESSION, tolerance_m=0.01, record_directory="x")
