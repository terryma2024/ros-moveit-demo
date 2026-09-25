"""Causal 10 Hz labels and lossless, auditable episode sealing."""

from __future__ import annotations

import json

import numpy as np
import pytest
from PIL import Image

from so101_demo.act.expert import MoveItExpertActionTap, CausalEpisodeCapture
from so101_demo.act.recorder import EpisodeRecorder, RecorderInfraError, require_grid, verify_episode_seal


PROVENANCE = {"source_sha256": "a" * 64, "scene_sha256": "b" * 64,
              "config_sha256": "c" * 64, "policy_fingerprint": "d" * 64, "seed": 7}


def observation(at_s):
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[20:40, 30:50] = (5, 80, 250)
    return {"session_id": "session-1", "attempt_id": "attempt-1", "sim_time_s": at_s,
            "head": frame, "wrist": frame.copy(), "state": (0., 0., 0., 0., 0., 0., 0., 1.)}


def audit(at_s, *, release_epoch=0, release_event=False, reset_epoch=2,
          release_time_s=None, reference_positions=(0.,) * 6):
    return {"session_id": "session-1", "attempt_id": "attempt-1",
            "reset_epoch": reset_epoch, "release_epoch": release_epoch,
            "release_event": release_event, "release_time_s": at_s - 0.02 if release_event else release_time_s,
            "phase": "RELEASE" if release_event else "TRANSPORT",
            "reference_time_s": at_s + 0.1,
            "reference_source": "CONTROLLER_REFERENCE",
            "reference_positions": reference_positions,
            "source_stamps": {name: at_s for name in ("head", "wrist", "arm", "neck")},
            "physical_stamps": {name: at_s for name in ("cup", "contacts", "planning_scene")},
            "mujoco_truth": {"cup_z_m": 0.18}, "contacts": [],
            "planning_scene": {"attached": not release_event},
            "controller_state": {"stopped": False}}


def outcome(status="PASSED"):
    return {"status": status, "reason": "complete" if status == "PASSED" else "search_failed",
            "task8_success": status == "PASSED", "stopped_confirmed": True}


def test_grid_rejects_missing_or_repeated_ticks():
    require_grid([1., 1.1, 1.2])
    with pytest.raises(ValueError, match="EPISODE_TIME_GAP"):
        require_grid([1., 1.2])
    with pytest.raises(ValueError, match="EPISODE_TIME_GAP"):
        require_grid([1., 1., 1.1])


def test_expert_label_reads_future_controller_reference_not_measured_state():
    class Reference:
        def __init__(self):
            self.queried = []

        def reference_state(self, when):
            self.queried.append(when)
            return {"requested_sim_time_s": when, "positions": (1., 2., 3., 4., 5., 6.),
                    "source": "CONTROLLER_REFERENCE"}

    source = Reference()
    assert MoveItExpertActionTap(source).label(1.0) == (1., 2., 3., 4., 5., 6.)
    assert source.queried == [1.1]
    source.reference_state = lambda when: {"requested_sim_time_s": when,
        "positions": (1., 2., 3., 4., 5., 6.), "source": "MEASURED_JOINTS"}
    with pytest.raises(ValueError, match="EXPERT_REFERENCE_SOURCE_INVALID"):
        MoveItExpertActionTap(source).label(1.0)


def test_capture_binds_action_and_audit_to_one_verified_reference_query(tmp_path):
    class Reference:
        def __init__(self):
            self.calls = []

        def reference_state(self, at_s):
            self.calls.append(at_s)
            return {"requested_sim_time_s": at_s, "positions": (0.3,) * 6,
                    "source": "CONTROLLER_REFERENCE"}

    source = Reference()
    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1",
                               attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)
    capture = CausalEpisodeCapture(recorder, MoveItExpertActionTap(source))
    physical_audit = {key: value for key, value in audit(1.0).items()
                      if key not in {"reference_time_s", "reference_source", "reference_positions"}}
    assert capture.append(observation(1.0), physical_audit) == (0.3,) * 6
    assert source.calls == [1.1]
    row = json.loads((tmp_path / "episode/records.jsonl").read_text().splitlines()[0])
    assert row["action"] == [0.3] * 6
    assert row["audit"]["reference_positions"] == [0.3] * 6
    assert row["audit"]["reference_time_s"] == 1.1


def test_missing_reference_emits_no_training_row_or_image(tmp_path):
    class Missing:
        def reference_state(self, at_s):
            raise RuntimeError("cancelled interval")

    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1",
                               attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)
    capture = CausalEpisodeCapture(recorder, MoveItExpertActionTap(Missing()))
    physical_audit = {key: value for key, value in audit(1.0).items()
                      if key not in {"reference_time_s", "reference_source", "reference_positions"}}
    with pytest.raises(ValueError, match="EXPERT_REFERENCE_UNAVAILABLE"):
        capture.append(observation(1.0), physical_audit)
    assert list((tmp_path / "episode/frames").iterdir()) == []
    assert verify_episode_seal(recorder.finish(outcome("FAILED")))["record_count"] == 0


def test_recorder_seals_lossless_rgb_and_keeps_audit_out_of_observation(tmp_path):
    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1",
                               attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)
    recorder.append(observation(1.0), (0.,) * 6, audit(1.0))
    recorder.append(observation(1.1), (0.1,) * 6, audit(1.1, release_epoch=1, release_event=True,
                                                        reference_positions=(0.1,) * 6))
    recorder.append(observation(1.2), (0.2,) * 6, audit(1.2, release_epoch=1,
        release_time_s=1.08, reference_positions=(0.2,) * 6))
    seal_path = recorder.finish(outcome())
    seal = verify_episode_seal(seal_path)
    assert seal["status"] == "PASSED" and seal["qc_passed"] is True
    assert seal["record_count"] == 3 and seal["committed"] is False
    rows = [json.loads(line) for line in (tmp_path / "episode/records.jsonl").read_text().splitlines()]
    assert set(rows[0]["observation"]) == {"sim_time_s", "state", "head_png", "wrist_png"}
    assert "mujoco_truth" not in rows[0]["observation"]
    assert rows[1]["audit"]["release_event"] is True
    with Image.open(tmp_path / "episode" / rows[0]["observation"]["head_png"]) as image:
        assert np.array_equal(np.asarray(image), observation(1.0)["head"])


def test_recorder_rejects_reset_change_and_release_without_new_epoch(tmp_path):
    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1",
                               attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)
    recorder.append(observation(1.0), (0.,) * 6, audit(1.0))
    with pytest.raises(ValueError, match="EPISODE_SCOPE_INVALID"):
        recorder.append(observation(1.1), (0.,) * 6, audit(1.1, reset_epoch=3))
    with pytest.raises(ValueError, match="RELEASE_EPOCH_INVALID"):
        recorder.append(observation(1.1), (0.,) * 6, audit(1.1, release_epoch=1))
    with pytest.raises(ValueError, match="EPISODE_TIME_GAP"):
        recorder.append(observation(1.2), (0.,) * 6, audit(1.2))


def test_release_epoch_cannot_reuse_pre_release_physical_evidence(tmp_path):
    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1",
                               attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)
    recorder.append(observation(1.0), (0.,) * 6, audit(1.0))
    old = audit(1.1, release_epoch=1, release_event=True)
    old["physical_stamps"] = {name: 1.05 for name in old["physical_stamps"]}
    with pytest.raises(ValueError, match="RELEASE_EVIDENCE_STALE"):
        recorder.append(observation(1.1), (0.,) * 6, old)


def test_action_must_equal_audited_controller_reference(tmp_path):
    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1",
                               attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)
    with pytest.raises(ValueError, match="EPISODE_REFERENCE_INVALID"):
        recorder.append(observation(1.0), (0.5,) * 6, audit(1.0))


def test_verifier_rejects_self_hashed_missing_frame_and_bad_reference(tmp_path):
    import hashlib
    import so101_demo.act.recorder as recorder_module

    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1",
                               attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)
    recorder.append(observation(1.0), (0.,) * 6, audit(1.0))
    recorder.append(observation(1.1), (0.,) * 6, audit(1.1))
    seal_path = recorder.finish(outcome())
    rows_path = seal_path.parent / "records.jsonl"
    rows = [json.loads(line) for line in rows_path.read_text().splitlines()]
    rows[0]["observation"]["head_png"] = "frames/missing.png"
    rows[1]["action"] = [0.5] * 6
    data = b"".join(recorder_module._canonical(row) + b"\n" for row in rows)
    rows_path.write_bytes(data)
    seal = json.loads(seal_path.read_bytes())
    seal["files"]["records.jsonl"] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
    seal["manifest_sha256"] = hashlib.sha256(recorder_module._canonical({
        key: value for key, value in seal.items() if key != "manifest_sha256"})).hexdigest()
    seal_path.write_bytes(recorder_module._canonical(seal) + b"\n")
    with pytest.raises(ValueError, match="EPISODE_SEAL_FILES_INVALID"):
        verify_episode_seal(seal_path)


def test_business_failed_episode_can_seal_but_never_claims_training_qc(tmp_path):
    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1",
                               attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)
    seal = verify_episode_seal(recorder.finish(outcome("FAILED")))
    assert seal["status"] == "FAILED" and seal["qc_passed"] is False
    assert seal["record_count"] == 0 and seal["committed"] is False


def test_fsync_failure_is_infrastructure_not_a_business_failed_seal(tmp_path, monkeypatch):
    import so101_demo.act.recorder as recorder_module

    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1",
                               attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)
    recorder.append(observation(1.0), (0.,) * 6, audit(1.0))
    monkeypatch.setattr(recorder_module.os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("disk failed")))
    with pytest.raises(RecorderInfraError, match="RECORDER_SEAL_FAILED"):
        recorder.finish(outcome("FAILED"))
    assert not (tmp_path / "episode/seal.json").exists()
