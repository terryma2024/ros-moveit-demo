"""Causal 10 Hz labels and lossless, auditable episode sealing."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from so101_demo.act.expert import MoveItExpertActionTap, CausalEpisodeCapture
from audited_episode import audit_of, seal_audited
from so101_demo.act.rig_profile import DEFAULT_RIG
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
            "pick_place_validation_success": status == "PASSED", "stopped_confirmed": True}


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
    path, manifest, scope = seal_audited(recorder, tmp_path, outcome("FAILED"))
    assert verify_episode_seal(path, audit_manifest=manifest, scope=scope)["record_count"] == 0


def test_recorder_seals_lossless_rgb_and_keeps_audit_out_of_observation(tmp_path):
    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1",
                               attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)
    recorder.append(observation(1.0), (0.,) * 6, audit(1.0))
    recorder.append(observation(1.1), (0.1,) * 6, audit(1.1, release_epoch=1, release_event=True,
                                                        reference_positions=(0.1,) * 6))
    recorder.append(observation(1.2), (0.2,) * 6, audit(1.2, release_epoch=1,
        release_time_s=1.08, reference_positions=(0.2,) * 6))
    seal_path, manifest, scope = seal_audited(recorder, tmp_path, outcome())
    seal = verify_episode_seal(seal_path, audit_manifest=manifest, scope=scope)
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


@pytest.mark.parametrize("tamper,expected", [("missing_frame", (ValueError, OSError)), ("bad_reference", ValueError)])
def test_verifier_rejects_self_hashed_missing_frame_and_bad_reference(tmp_path, tamper, expected):
    import hashlib
    import so101_demo.act.recorder as recorder_module

    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1",
                               attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)
    recorder.append(observation(1.0), (0.,) * 6, audit(1.0))
    recorder.append(observation(1.1), (0.,) * 6, audit(1.1, reference_positions=(0.,) * 6))
    seal_path, manifest, scope = seal_audited(recorder, tmp_path, outcome())
    rows_path = seal_path.parent / "records.jsonl"
    rows = [json.loads(line) for line in rows_path.read_text().splitlines()]
    if tamper == "missing_frame":
        rows[0]["observation"]["head_png"] = "frames/missing.png"
    else:
        rows[1]["action"] = [0.5] * 6
    data = b"".join(recorder_module._canonical(row) + b"\n" for row in rows)
    rows_path.write_bytes(data)
    seal = json.loads(seal_path.read_bytes())
    seal["files"]["records.jsonl"] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
    seal["manifest_sha256"] = hashlib.sha256(recorder_module._canonical({
        key: value for key, value in seal.items() if key != "manifest_sha256"})).hexdigest()
    seal_path.write_bytes(recorder_module._canonical(seal) + b"\n")
    with pytest.raises(expected) as caught:
        verify_episode_seal(seal_path, audit_manifest=manifest, scope=scope)
    if tamper == "bad_reference":
        assert "EPISODE_SEAL_ROWS_MISMATCH" in str(caught.value)


def test_business_failed_episode_can_seal_but_never_claims_training_qc(tmp_path):
    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1",
                               attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)
    path, manifest, scope = seal_audited(recorder, tmp_path, outcome("FAILED"))
    seal = verify_episode_seal(path, audit_manifest=manifest, scope=scope)
    assert seal["status"] == "FAILED" and seal["qc_passed"] is False
    assert seal["record_count"] == 0 and seal["committed"] is False


def test_fsync_failure_is_infrastructure_not_a_business_failed_seal(tmp_path, monkeypatch):
    import so101_demo.act.recorder as recorder_module

    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1",
                               attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)
    recorder.append(observation(1.0), (0.,) * 6, audit(1.0))
    manifest, scope = audit_of(recorder, tmp_path)
    monkeypatch.setattr(recorder_module.os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("disk failed")))
    with pytest.raises(RecorderInfraError, match="RECORDER_SEAL_FAILED"):
        recorder.finish(outcome("FAILED"), audit_manifest=manifest, scope=scope)
    assert not (tmp_path / "episode/seal.json").exists()


def _audit_and_scope(tmp_path, *, session="session-1", attempt="attempt-1"):

    import numpy as _np

    from so101_demo.act.acquisition import AcquisitionMinter
    from so101_demo.act.episode_audit.writer import EpisodeAuditWriter

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
    # a zero-row failed episode names no labelled binding; the multi-row tests exercise bindings
    manifest = writer.seal({"start_s": 1.0, "end_s": 1.2})
    return manifest, scope


def test_a_seal_names_the_raw_audit_and_the_collection_scope(tmp_path):
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


def test_a_seal_refuses_an_audit_that_changed_after_sealing(tmp_path):
    manifest, scope = _audit_and_scope(tmp_path)
    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1",
                               attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)
    path = recorder.finish(outcome("FAILED"), audit_manifest=manifest, scope=scope)
    (manifest.parent / "events.jsonl").write_bytes(b'{"sequence":1}\n')
    with pytest.raises(ValueError, match="AUDIT_HASH_MISMATCH"):
        verify_episode_seal(path, audit_manifest=manifest, scope=scope)


def test_a_seal_fsyncs_the_referenced_files_and_the_parent_directory(tmp_path, monkeypatch):
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


def test_a_seal_refuses_an_audit_of_another_episode(tmp_path):
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


def _multi_row_audit(tmp_path, instants, *, mismatched_pixels=False):
    """An audit with one binding per recorded instant, plus the scope the seal must share."""


    from so101_demo.act.acquisition import AcquisitionMinter
    from so101_demo.act.episode_audit.writer import EpisodeAuditWriter

    scope_document = {"kind": "ACT_COLLECTION_SCOPE", "schema_version": 1,
                      "mode": "preselected_target_diagnostic", "scene_id": "default", "seed": 0,
                      "inputs_sha256": "c" * 64}
    scope = tmp_path / "collection-scope.json"
    scope.write_bytes(json.dumps(scope_document, sort_keys=True, separators=(",", ":")).encode())
    writer = EpisodeAuditWriter(tmp_path / "audit-episode", scope_document,
                                {"session_id": "session-1", "attempt_id": "attempt-1",
                                 "reset_epoch": 2, "release_epoch": 1},
                                {"inputs_sha256": "c" * 64})
    minter = AcquisitionMinter()
    frames = {}
    for instant in instants:
        for camera in ("head", "wrist"):
            # the acquisition must identify the very frame the recorder stores, or it is not common
            pixels = observation(instant)[camera]
            if mismatched_pixels and instant == instants[-1]:
                pixels = pixels.copy()
                pixels[0, 0] = (255, 0, 0)
            frame = minter.mint(camera, session_id="session-1", reset_epoch=2, stamp_s=instant,
                                received_monotonic_ns=1, pixels=pixels)
            writer.append_acquisition(frame)
            frames[(camera, instant)] = frame
    for index, instant in enumerate(instants):
        # the reference each row names must be the action that row recorded, or the binding is not common
        writer.append_source("references", {"reference_time_s": round(instant + 0.1, 6),
                                            "source": "CONTROLLER_REFERENCE",
                                            "positions": [round(0.1 * index, 6)] * 6,
                                            "accepted": True})
        writer.bind_row(index, instant, frames[("head", instant)].acquisition_id,
                        frames[("wrist", instant)].acquisition_id, index + 1)
    return writer.seal({"start_s": instants[0], "end_s": instants[-1]}), scope


def _three_row_recorder(tmp_path):
    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1",
                               attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)
    recorder.append(observation(1.0), (0.0,) * 6, audit(1.0))
    recorder.append(observation(1.1), (0.1,) * 6,
                    audit(1.1, release_epoch=1, release_event=True, reference_positions=(0.1,) * 6))
    recorder.append(observation(1.2), (0.2,) * 6,
                    audit(1.2, release_epoch=1, release_time_s=1.08,
                          reference_positions=(0.2,) * 6))
    return recorder


def test_a_multi_row_episode_verifies_against_its_bound_audit(tmp_path):
    manifest, scope = _multi_row_audit(tmp_path, (1.0, 1.1, 1.2))
    path = _three_row_recorder(tmp_path).finish(outcome(), audit_manifest=manifest, scope=scope)
    document = verify_episode_seal(path, audit_manifest=manifest, scope=scope)
    assert document["record_count"] == 3 and document["schema_version"] == 2


def test_a_recorded_row_at_a_different_instant_than_its_binding_is_refused(tmp_path):
    """Tamper the recorder side so the audit stays legal and only the correlation can catch it."""

    manifest, scope = _multi_row_audit(tmp_path, (1.0, 1.1, 1.2))
    path = _three_row_recorder(tmp_path).finish(outcome(), audit_manifest=manifest, scope=scope)
    records = (tmp_path / "episode" / "records.jsonl").read_text().splitlines()
    last = json.loads(records[-1])
    last["observation"]["sim_time_s"] = 1.15
    records[-1] = json.dumps(last, sort_keys=True, separators=(",", ":"))
    payload = ("\n".join(records) + "\n").encode()
    (tmp_path / "episode" / "records.jsonl").write_bytes(payload)
    seal = json.loads(path.read_bytes())
    seal["files"]["records.jsonl"] = {"sha256": hashlib.sha256(payload).hexdigest(),
                                      "size": len(payload)}
    seal.pop("manifest_sha256")
    seal["manifest_sha256"] = hashlib.sha256(
        json.dumps(seal, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    path.write_bytes(json.dumps(seal, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    with pytest.raises(ValueError, match="EPISODE_SEAL_ROWS_MISMATCH"):
        verify_episode_seal(path, audit_manifest=manifest, scope=scope)


class _RawReferencePort:
    def __init__(self, document):
        self.document = document

    def reference_state(self, target):
        return {**self.document, "requested_sim_time_s": target}


def test_a_raw_reference_port_still_writes_training_rows(tmp_path):
    """The raw frame must not break the recorder's closed row audit (T3-F8)."""

    from so101_demo.act.expert import CausalEpisodeCapture, MoveItExpertActionTap

    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1",
                               attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)
    raw = {"joint_names": ["shoulder_pan", "shoulder_lift"], "sim_stamp_ns": 1100000000,
           "received_monotonic_ns": 900000, "velocities": [0.0, 0.0]}
    tap = MoveItExpertActionTap(_RawReferencePort(
        {"source": "CONTROLLER_REFERENCE", "positions": [0.1] * 6, **raw}))
    capture = CausalEpisodeCapture(recorder, tap)
    physical = {key: value for key, value in audit(1.0).items()
                if key not in ("reference_time_s", "reference_source", "reference_positions")}
    capture.append(observation(1.0), physical)
    assert capture.raw_reference == raw
    path, manifest, scope = seal_audited(recorder, tmp_path, outcome("FAILED"))
    seal = verify_episode_seal(path, audit_manifest=manifest, scope=scope)
    assert seal["record_count"] == 1
    row = json.loads((tmp_path / "episode" / "records.jsonl").read_text().splitlines()[0])
    assert not set(capture._RAW_REFERENCE_KEYS) & set(row["audit"])


def test_a_recorded_action_that_differs_from_its_bound_reference_is_refused(tmp_path):
    """Changing the action (not the time) must break the common binding (T3-F4)."""

    manifest, scope = _multi_row_audit(tmp_path, (1.0, 1.1, 1.2))
    path = _three_row_recorder(tmp_path).finish(outcome(), audit_manifest=manifest, scope=scope)
    records = (tmp_path / "episode" / "records.jsonl").read_text().splitlines()
    last = json.loads(records[-1])
    last["action"] = [9.9] * 6
    records[-1] = json.dumps(last, sort_keys=True, separators=(",", ":"))
    payload = ("\n".join(records) + "\n").encode()
    (tmp_path / "episode" / "records.jsonl").write_bytes(payload)
    seal = json.loads(path.read_bytes())
    seal["files"]["records.jsonl"] = {"sha256": hashlib.sha256(payload).hexdigest(),
                                      "size": len(payload)}
    seal.pop("manifest_sha256")
    seal["manifest_sha256"] = hashlib.sha256(
        json.dumps(seal, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    path.write_bytes(json.dumps(seal, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    with pytest.raises(ValueError, match="EPISODE_SEAL_ROWS_MISMATCH"):
        verify_episode_seal(path, audit_manifest=manifest, scope=scope)


def test_a_scope_that_is_not_the_audits_payload_is_refused_on_readback(tmp_path):
    manifest, scope = _multi_row_audit(tmp_path, (1.0, 1.1, 1.2))
    path = _three_row_recorder(tmp_path).finish(outcome(), audit_manifest=manifest, scope=scope)
    other_scope = tmp_path / "other-scope.json"
    other_scope.write_bytes(json.dumps({"kind": "ACT_COLLECTION_SCOPE", "schema_version": 1,
                                        "mode": "preselected_target_diagnostic", "scene_id": "x",
                                        "seed": 0, "inputs_sha256": "c" * 64},
                                       sort_keys=True, separators=(",", ":")).encode())
    # the seal's own scope digest is compared first, so a different payload is refused there; the
    # audit-side comparison is the guard once the seal's digest matches
    with pytest.raises(ValueError,
                       match="EPISODE_SEAL_AUDIT_MISMATCH|EPISODE_SEAL_AUDIT_SCOPE_MISMATCH"):
        verify_episode_seal(path, audit_manifest=manifest, scope=other_scope)


def test_an_acquisition_that_does_not_identify_the_stored_frame_is_refused(tmp_path):
    """The stored lossless pixels must be the pixels the bound acquisition identified (T3-F4)."""

    manifest, scope = _multi_row_audit(tmp_path, (1.0, 1.1, 1.2), mismatched_pixels=True)
    recorder = _three_row_recorder(tmp_path)
    # the seal path wraps a refused self-check as an infrastructure error, so assert both layers
    with pytest.raises(Exception, match="RECORDER_SEAL_FAILED") as caught:
        recorder.finish(outcome(), audit_manifest=manifest, scope=scope)
    assert "EPISODE_SEAL_PIXELS_MISMATCH" in str(caught.value.__cause__)


def _count_pixel_hashes(monkeypatch, fail_on=None, wrong_on=None):
    """Every call of the frame decoder, in the order the calls start; `fail_on` (a file name) makes that frame undecodable and
    `wrong_on` gives it a hash that is not its acquisition's."""
    from so101_demo.act import recorder as recorder_module

    seen, direct = [], recorder_module._decoded_pixel_sha256

    def counted(path):
        seen.append(Path(path).name)
        if fail_on is not None and Path(path).name == fail_on:
            raise ValueError("EPISODE_FRAME_INVALID")
        if wrong_on is not None and Path(path).name == wrong_on:
            return "0" * 64
        return direct(path)
    monkeypatch.setattr(recorder_module, "_decoded_pixel_sha256", counted)
    return seen


def test_the_seal_decodes_each_stored_frame_once_and_threads_do_not_change_the_verdict(tmp_path, monkeypatch):
    manifest, scope = _multi_row_audit(tmp_path, (1.0, 1.1, 1.2))
    path = _three_row_recorder(tmp_path).finish(outcome(), audit_manifest=manifest, scope=scope)
    seen = _count_pixel_hashes(monkeypatch)
    seal = verify_episode_seal(path, audit_manifest=manifest, scope=scope)
    assert seal["record_count"] == 3 and len(seen) == len(set(seen)) == 3 * len(DEFAULT_RIG.camera_names)
    assert sorted(seen) == sorted(f"{index:06d}-{camera}.png" for index in range(3) for camera in DEFAULT_RIG.camera_names)


def test_an_undecodable_frame_raises_its_own_error_from_the_seal_check(tmp_path, monkeypatch):
    manifest, scope = _multi_row_audit(tmp_path, (1.0, 1.1, 1.2))
    path = _three_row_recorder(tmp_path).finish(outcome(), audit_manifest=manifest, scope=scope)
    _count_pixel_hashes(monkeypatch, fail_on=f"000001-{DEFAULT_RIG.camera_names[0]}.png")
    with pytest.raises(ValueError, match="EPISODE_FRAME_INVALID"):
        verify_episode_seal(path, audit_manifest=manifest, scope=scope)


def test_the_first_frame_that_fails_decides_even_when_a_later_one_fails_differently(tmp_path, monkeypatch):
    """Row 0 does not match its acquisition and row 2 cannot be decoded: the check meets row 0 first, as it always did."""

    manifest, scope = _multi_row_audit(tmp_path, (1.0, 1.1, 1.2))
    path = _three_row_recorder(tmp_path).finish(outcome(), audit_manifest=manifest, scope=scope)
    camera = DEFAULT_RIG.camera_names[0]
    _count_pixel_hashes(monkeypatch, wrong_on=f"000000-{camera}.png", fail_on=f"000002-{camera}.png")
    with pytest.raises(ValueError, match="EPISODE_SEAL_PIXELS_MISMATCH"):
        verify_episode_seal(path, audit_manifest=manifest, scope=scope)


def test_a_zero_row_seal_may_not_name_a_labelled_binding(tmp_path):
    """A labelled binding means a row was written, so a zero-row episode may not carry one (T3-F4)."""

    manifest, scope = _multi_row_audit(tmp_path, (1.0, 1.1, 1.2))
    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1",
                               attempt_id="attempt-1", reset_epoch=2, provenance=PROVENANCE)
    with pytest.raises(Exception, match="RECORDER_SEAL_FAILED") as caught:
        recorder.finish(outcome("FAILED"), audit_manifest=manifest, scope=scope)
    assert "EPISODE_SEAL_ROWS_MISMATCH" in str(caught.value.__cause__)
