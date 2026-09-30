"""Causal 10 Hz labels and lossless, auditable episode sealing."""

from __future__ import annotations

import hashlib
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


def _audit_and_scope(tmp_path, *, session="session-1", attempt="attempt-1"):
    import hashlib as _hashlib

    import numpy as _np

    from so101_demo.act.acquisition import AcquisitionMinter
    from so101_demo.act.episode_audit import EpisodeAuditWriter

    def canonical(document):
        # byte-for-byte the payload the audit writes, so the seal and the audit name one scope
        return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()

    # the scope exists first: the audit records the digest of the scope this episode ran under
    scope = tmp_path / "collection-scope.json"
    scope.write_bytes(canonical({"kind": "ACT_COLLECTION_SCOPE", "schema_version": 1,
                                 "mode": "preselected_target_diagnostic", "scene_id": "default",
                                 "seed": 0, "inputs_sha256": "c" * 64}))


    scope_document = json.loads(scope.read_bytes())
    writer = EpisodeAuditWriter(tmp_path / "audit-episode", scope_document,
                                {"session_id": session, "attempt_id": attempt,
                                 "reset_epoch": 2, "release_epoch": 1, "scene_id": "default",
                                 "seed": 0},
                                {"inputs_sha256": "c" * 64})
    minter = AcquisitionMinter()
    frames = {}
    for camera in ("head", "wrist"):
        frame = minter.mint(camera, session_id=session, reset_epoch=2, stamp_s=1.0,
                            received_monotonic_ns=1, pixels=_np.zeros((480, 640, 3), dtype=_np.uint8))
        writer.append_acquisition(frame)
        frames[camera] = frame
    writer.append_source("references", {"reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE",
                                        "positions": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
                                        "accepted": True})
    writer.bind_row(0, 1.0, frames["head"].acquisition_id, frames["wrist"].acquisition_id, 1)
    manifest = writer.seal({"start_s": 1.0, "end_s": 1.2})
    return manifest, scope


def test_a_v2_seal_names_the_raw_audit_and_the_collection_scope(tmp_path):
    manifest, scope = _audit_and_scope(tmp_path)
    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1",
                               attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)
    path = recorder.finish(outcome("FAILED"), audit_manifest=manifest, scope=scope)
    document = verify_episode_seal(path, audit_manifest=manifest, scope=scope)
    assert document["schema_version"] == 2
    assert (document["audit_manifest_sha256"]
            == hashlib.sha256(manifest.read_bytes()).hexdigest())
    manifest_document = json.loads(manifest.read_bytes())
    assert document["scope_sha256"] == manifest_document["scope_sha256"]
    assert document["scope_sha256"] == hashlib.sha256(scope.read_bytes()).hexdigest()
    for incomplete in ({}, {"audit_manifest": manifest}, {"scope": scope}):
        with pytest.raises(ValueError, match="EPISODE_SEAL_AUDIT_INCOMPLETE"):
            verify_episode_seal(path, **incomplete)
    rechecked = verify_episode_seal(path, audit_manifest=manifest, scope=scope)
    assert rechecked == document


def test_a_seal_without_the_audit_stays_v1_and_readable(tmp_path):
    """The old schema stays readable for audit; only the new closure is v2."""

    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1",
                               attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)
    document = verify_episode_seal(recorder.finish(outcome("FAILED")))
    assert document["schema_version"] == 1
    assert "audit_manifest_sha256" not in document and "scope_sha256" not in document


def test_a_half_referenced_audit_is_refused(tmp_path):
    manifest, _ = _audit_and_scope(tmp_path)
    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1",
                               attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)
    with pytest.raises(ValueError, match="EPISODE_SEAL_AUDIT_INCOMPLETE"):
        recorder.finish(outcome("FAILED"), audit_manifest=manifest)


def test_a_tampered_audit_cannot_be_sealed(tmp_path):
    manifest, scope = _audit_and_scope(tmp_path)
    references = manifest.parent / "references.jsonl"
    original = references.read_bytes()
    tampered = original.replace(b"0.1", b"0.9", 1)
    assert tampered != original, "the fixture must actually change a raw reference"
    references.write_bytes(tampered)
    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1",
                               attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)
    with pytest.raises(ValueError, match="AUDIT_HASH_MISMATCH"):
        recorder.finish(outcome("FAILED"), audit_manifest=manifest, scope=scope)


def test_a_v2_seal_refuses_an_audit_that_changed_after_sealing(tmp_path):
    manifest, scope = _audit_and_scope(tmp_path)
    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1",
                               attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)
    path = recorder.finish(outcome("FAILED"), audit_manifest=manifest, scope=scope)
    (manifest.parent / "events.jsonl").write_bytes(b'{"sequence":1}\n')
    with pytest.raises(ValueError, match="AUDIT_HASH_MISMATCH"):
        verify_episode_seal(path, audit_manifest=manifest, scope=scope)


def test_a_v2_seal_fsyncs_the_referenced_files_and_the_parent_directory(tmp_path, monkeypatch):
    import os as os_module
    import stat

    manifest, scope = _audit_and_scope(tmp_path)
    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1",
                               attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)
    synced = []
    real_fsync = os_module.fsync

    def recording_fsync(fd):
        info = os_module.fstat(fd)
        synced.append((info.st_ino, stat.S_ISDIR(info.st_mode)))
        return real_fsync(fd)

    monkeypatch.setattr(os_module, "fsync", recording_fsync)
    recorder.finish(outcome("FAILED"), audit_manifest=manifest, scope=scope)
    inodes = {inode for inode, _ in synced}
    assert manifest.stat().st_ino in inodes and scope.stat().st_ino in inodes
    assert (recorder.root.parent.stat().st_ino, True) in synced


def test_a_v2_seal_refuses_an_audit_of_another_episode(tmp_path):
    """A checksum-consistent seal naming a valid but unrelated audit is not evidence (T3-F4)."""

    manifest, scope = _audit_and_scope(tmp_path)
    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1",
                               attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)
    path = recorder.finish(outcome("FAILED"), audit_manifest=manifest, scope=scope)
    (tmp_path / "other").mkdir(parents=True, exist_ok=True)
    other, other_scope = _audit_and_scope(tmp_path / "other", session="session-2")
    # a valid audit of another episode is refused; its digest cannot match the sealed one, and the
    # identity comparison behind that digest is exercised by the positive case above
    with pytest.raises(ValueError, match="EPISODE_SEAL_AUDIT_MISMATCH"):
        verify_episode_seal(path, audit_manifest=other, scope=other_scope)


def test_a_rehashed_v1_seal_may_not_carry_v2_fields(tmp_path):
    """The seal field set is version-specific, so v2 digests cannot ride on a v1 document (T3-F4)."""

    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1",
                               attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)
    path = recorder.finish(outcome("FAILED"))
    document = json.loads(path.read_bytes())
    assert document["schema_version"] == 1
    document["audit_manifest_sha256"] = "a" * 64
    document["scope_sha256"] = "b" * 64
    document.pop("manifest_sha256")
    document["manifest_sha256"] = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    path.write_bytes(json.dumps(document, sort_keys=True, separators=(",", ":")).encode())
    with pytest.raises(ValueError, match="EPISODE_SEAL_SCHEMA"):
        verify_episode_seal(path)


def test_a_rehashed_v1_seal_may_not_carry_v2_fields(tmp_path):
    """The seal field set is version-specific, so v2 digests cannot ride on a v1 document (T3-F4)."""

    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1",
                               attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)
    path = recorder.finish(outcome("FAILED"))
    document = json.loads(path.read_bytes())
    assert document["schema_version"] == 1
    document["audit_manifest_sha256"] = "a" * 64
    document["scope_sha256"] = "b" * 64
    document.pop("manifest_sha256")
    document["manifest_sha256"] = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    path.write_bytes(json.dumps(document, sort_keys=True, separators=(",", ":")).encode())
    with pytest.raises(ValueError, match="EPISODE_SEAL_SCHEMA"):
        verify_episode_seal(path)
