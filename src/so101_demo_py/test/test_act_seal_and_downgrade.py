"""E2 corrections 2 and 3: a capture seals its audit, and a failing verdict changes the terminal status.

Both tests are marked xfail for a measured integration defect rather than a harness one (CP-2726): the capture adds
`head_acquisition_id` and `wrist_acquisition_id` to the audit it hands the recorder, and the recorder's closed
`_AUDIT_KEYS` - sixteen keys - does not admit them, so every row is refused with EPISODE_AUDIT_SCHEMA. Nothing drived
the capture and the recorder together before this file, which is why the defect survived.
"""

import pytest

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from so101_demo.act.continuous_capture import ContinuousEpisodeCapture
from so101_demo.act.endpoint_pose_acceptance import load_endpoint_policy
from so101_demo.act.episode_audit import EpisodeAuditWriter, verify_audit_manifest
from so101_demo.act.episode_qc import endpoint_qc_document
from so101_demo.act.recorder import EpisodeRecorder
from so101_demo.act.result_store import ActCollectionResultStore, ActCollectionResultVerifier
from so101_demo.parallel_batch.contracts import LeaseIdentity, RunMode
from test_act_continuous_capture import (AcquisitionGuard, AcquisitionMinter, FakeSampler, feed,
                                         reference)
from test_act_recorder import PROVENANCE

POLICY = Path(__file__).resolve().parents[1] / "config/act/endpoint_pose_acceptance_v1.yaml"
SCOPE = {"kind": "ACT_COLLECTION_SCOPE", "schema_version": 1, "mode": "preselected_target_diagnostic",
         "scene_id": "default", "seed": 0, "inputs_sha256": "a" * 64}
IDENTITY = {"session_id": "session-1", "attempt_id": "attempt-1", "reset_epoch": 2, "release_epoch": 1,
            "scene_id": "default", "seed": 0, "mode": "preselected_target_diagnostic"}


class RecorderSampler(FakeSampler):
    """The same sampler, minus the one key the recorder's closed audit set does not admit (CP-2723)."""

    def sample_with_audit(self, session_id, attempt_id, at_s):
        observation, source = super().sample_with_audit(session_id, attempt_id, at_s)
        return observation, {"source_stamps": source["source_stamps"]}


def recorder_physical_audit(at_s):
    """The physical half only: the recorder suite's audit minus what the sampler supplies."""

    from test_act_recorder import audit as recorder_audit

    return {key: value for key, value in recorder_audit(at_s).items() if key != "source_stamps"}


def lease():
    return LeaseIdentity(batch_id="batch-1", coordinator_epoch=1, worker_id="w00", worker_generation=1,
                         point_id="point-1", attempt_id="attempt-1", lease_generation=1,
                         lease_issued_monotonic_s=10.0, lease_deadline_monotonic_s=20.0)


def store_for(tmp_path):
    """The store owns the episode root: <workspace>/working/episode, and refuses any other seal (CP-2762)."""

    workspace = tmp_path / "w00" / "attempts" / "point-1" / "attempt-1"
    return ActCollectionResultStore(workspace, lease(), clock=lambda: 15.0)


def sealed_episode(tmp_path, *, outcome, end_s=1.3, episode_root=None):
    """Drive one real capture to its seal, with references one instant ahead of each row (CP-2725)."""

    # the audit lives where the verifier resolves it by convention: <workspace>/sealed/episode/audit-manifest.json,
    # which is the writer's own root with its streams in <root>/audit/ (CP-2768)
    audit_root = episode_root or (tmp_path / "episode")

    # the coordinates the physical half carries: the recorder suite's audit() hardcodes session-1 and defaults to
    # reset_epoch 2, and the recorder requires the audit to agree with it (CP-2734)
    # the recorder creates its own root and refuses one that exists, so it must not be pointed at the writer's: the
    # recorder reaches the audit through audit_manifest.parent, which is the writer's root (CP-2769)
    recorder = EpisodeRecorder(audit_root, session_id="session-1", attempt_id="attempt-1",
                               reset_epoch=2, provenance=PROVENANCE)
    audit = EpisodeAuditWriter(audit_root, SCOPE, IDENTITY, {"inputs_sha256": "a" * 64})

    capture = ContinuousEpisodeCapture(
        recorder=recorder, sampler=RecorderSampler(), guard=AcquisitionGuard(),
        physical_audit=recorder_physical_audit, audit=audit,
        scope=str(audit_root / "audit" / "source.json"), deadline_s=120.0, monotonic=lambda: 0.0)
    minter = AcquisitionMinter()
    capture.start("session-1", "attempt-1", 2, 1.0)
    # N rows need N+1 instants of frames: a row is released only once the observed sim clock has passed its target
    # instant, because an early acceptance could still be revoked (CP-2741)
    for stamp in (1.0, 1.1, 1.2, 1.3):
        for camera in ("head", "wrist"):                 # the frames carry the episode's reset epoch too
            feed(capture, minter, camera=camera, stamp_s=stamp, session="session-1", reset_epoch=2)
        capture.on_reference(reference(stamp + 0.1))     # a row targets at_s + dt_s, not at_s
        capture.drain()
    capture.finish(end_s, window={"start_s": 1.0, "end_s": end_s, "label_cutoff_s": end_s},
                   outcome=outcome)
    return audit_root / "audit" / "audit-manifest.json", recorder.root / "seal.json"


def test_a_capture_driven_to_its_seal_binds_the_audit_the_endpoint_qc_reads(tmp_path):
    """Correction 2: the episode carries the audit, and a fresh process can read it back."""

    store = store_for(tmp_path)
    manifest_path, _ = sealed_episode(tmp_path, episode_root=store.episode_root,
                                      outcome={"status": "FAILED", "reason": "search_failed",
                                               "task8_success": False, "stopped_confirmed": True})
    manifest = verify_audit_manifest(manifest_path)
    assert manifest["kind"] == "ACT_EPISODE_AUDIT"
    document = endpoint_qc_document(manifest_path.parent, {
        "initial_target": [0.0] * 7, "final_target": [0.0] * 7,
        "endpoint_policy": load_endpoint_policy(POLICY)})
    print("EPISODE QC:", document["status"], "| checks:", sorted(document["checks"]))
    assert document["rule_version"] == "endpoint_pose_v1" and "endpoint_pose" in document["checks"]


def test_a_run_claiming_success_cannot_survive_a_failing_endpoint_verdict(tmp_path):
    """Correction 3: the coordinator reads result['status'], so a failing verdict must change it."""

    store = store_for(tmp_path)
    current = lease()
    manifest_path, episode_seal = sealed_episode(
        tmp_path, episode_root=store.episode_root,
        outcome={"status": "PASSED", "reason": "completed",
                 "task8_success": True, "stopped_confirmed": True})
    # a v2 seal is verified only when both artifacts are supplied, so the store is told where they are (CP-2765)
    # the store verifies before it publishes, so it is handed the pre-publish pair; the verifier is handed the
    # published one, because the publish renames working -> sealed (CP-2777)
    store.audit_manifest = manifest_path
    store.scope = manifest_path.parent / "source.json"
    sealed = store.seal(episode_seal)
    verifier = ActCollectionResultVerifier(
        {"w00": tmp_path / "w00"},
        audit_manifest=sealed / "episode" / "audit" / "audit-manifest.json",
        scope=sealed / "episode" / "audit" / "source.json",
        endpoint_inputs={"initial_target": [0.0] * 7, "final_target": [0.0] * 7,
                         "endpoint_policy": load_endpoint_policy(POLICY)})
    result = verifier.verify(current, str(sealed), RunMode.EXECUTE)
    print("DOWNGRADE status:", result["status"], "| endpoint:", result["endpoint"]["status"])
    assert result["endpoint"]["status"] != "PASS"
    assert result["status"] == "FAILED"


def test_discover_finds_a_seal_only_at_the_location_the_lease_reserves(tmp_path):
    """The ACT port's discover, which the composition drives exactly as it drives the generic adapter (CP-2801).

    Two directions, because both matter: the reserved location yields a verified seal, and anything else yields None
    rather than a scan of the filesystem.
    """
    store = store_for(tmp_path)
    manifest_path, episode_seal = sealed_episode(
        tmp_path, episode_root=store.episode_root,
        outcome={"status": "FAILED", "reason": "search_failed",
                 "task8_success": False, "stopped_confirmed": True})
    # the store verifies before it publishes, so it is handed the pre-publish pair; the verifier the published one
    store.audit_manifest = manifest_path
    store.scope = manifest_path.parent / "source.json"
    sealed = store.seal(episode_seal)

    verifier = ActCollectionResultVerifier(
        {"w00": tmp_path / "w00"},
        audit_manifest=sealed / "episode" / "audit" / "audit-manifest.json",
        scope=sealed / "episode" / "audit" / "source.json",
        endpoint_inputs={"initial_target": [0.0] * 7,
                         "endpoint_policy": {"rule_version": "endpoint_pose_v1", "thresholds": {}},
                         "final_target": [0.0] * 7})

    reserved = tmp_path / "w00" / "attempts" / "point-1" / "attempt-1"
    assert verifier.discover(lease(), reserved) == str(reserved / "sealed")
    assert verifier.discover(lease(), tmp_path / "elsewhere") is None
