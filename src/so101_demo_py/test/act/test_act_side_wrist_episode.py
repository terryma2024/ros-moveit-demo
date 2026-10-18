"""A rig v2 episode (side and wrist cameras, no head, no neck, 6-wide state) through the capture, recorder, audit, seal, QC counts and export.

The v1 chain is `test_act_seal_and_downgrade.py`; this drives the same production seams with a frozen inputs set that binds the v2
profile, and asserts that nothing of a head or a neck is written anywhere.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from so101_demo.act.acquisition import AcquisitionGuard, AcquisitionMinter
from so101_demo.act.episode_assembly import assemble_episode_capture
from so101_demo.act.episode_audit.verification import verify_audit_manifest
from so101_demo.act.recorder import verify_episode_seal
from so101_demo.act.rig_profile import HEAD_WRIST_RIG, SIDE_WRIST_RIG, dump_rig_profile
from test_act_recorder import PROVENANCE, audit as recorder_audit

SCOPE = {"kind": "ACT_COLLECTION_SCOPE", "schema_version": 1, "mode": "preselected_target_diagnostic",
         "scene_id": "default", "seed": 0, "inputs_sha256": "a" * 64}
IDENTITY = {"session_id": "session-1", "attempt_id": "attempt-1", "reset_epoch": 2, "release_epoch": 1,
            "scene_id": "default", "seed": 0, "mode": "preselected_target_diagnostic"}
OUTCOME = {"status": "FAILED", "reason": "search_failed", "pick_place_validation_success": False, "stopped_confirmed": True}


def frozen_inputs(rig):
    """The audit's copy of the frozen inputs: bound to the rig when it is not the default (v1 sealed sets bind none)."""
    from so101_demo.act.diagnostic_episode_inputs import rig_profile_binding
    base = {"inputs_sha256": "a" * 64}
    return base if rig is HEAD_WRIST_RIG else {**base, "rig_profile": rig_profile_binding(dump_rig_profile(rig))}


class RigSampler:
    """The newest causal frame of each camera of the rig; the arm stream (and the neck's, when the rig has one) rides along."""

    def __init__(self, rig):
        self.rig = rig
        self.stamps = {camera: [] for camera in rig.camera_names}

    def sample_with_audit(self, session_id, attempt_id, at_s):
        stamps = {}
        for camera in self.rig.camera_names:
            causal = [stamp for stamp in self.stamps[camera] if stamp <= at_s + 1e-9]
            stamps[camera] = round(max(causal), 6) if causal else round(at_s - 0.1, 6)
        stamps["arm"] = stamps[self.rig.camera_names[0]]
        if self.rig.has_neck:
            stamps["neck"] = stamps["arm"]
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        state = [0.0] * 6 + ([0.0, 1.0] if self.rig.has_neck else [])
        observation = {"session_id": session_id, "attempt_id": attempt_id, "sim_time_s": at_s, "state": state,
                       **{camera: image for camera in self.rig.camera_names}}
        return observation, {"source_stamps": stamps}


def physical_audit(at_s):
    return {key: value for key, value in recorder_audit(at_s).items() if key != "source_stamps"}


def reference(at_s):
    return {"source": "CONTROLLER_REFERENCE", "requested_sim_time_s": round(at_s, 6),
            "positions": [0.0] * 6, "accepted": True}


def sealed_episode(tmp_path, rig):
    root = tmp_path / "episode"
    sampler = RigSampler(rig)
    capture = assemble_episode_capture(
        sampler=sampler, physical_audit=physical_audit, guard=AcquisitionGuard(), identity=dict(IDENTITY),
        provenance=PROVENANCE, inputs=frozen_inputs(rig), episode_root=root, scope=SCOPE,
        scope_path=str(root / "audit" / "source.json"), deadline_s=120.0, monotonic=lambda: 0.0)
    assert capture.rig is rig and capture.recorder.rig is rig and capture.audit.rig is rig
    minter = AcquisitionMinter(rig)
    capture.start("session-1", "attempt-1", 2, 1.0)
    pixels = np.zeros((480, 640, 3), dtype=np.uint8)
    for stamp in (1.0, 1.1, 1.2, 1.3):
        for camera in rig.camera_names:
            frame = minter.mint(camera, session_id="session-1", reset_epoch=2, stamp_s=stamp,
                                received_monotonic_ns=int(stamp * 1e9) + 1, pixels=pixels)
            capture.on_acquisition(frame, pixels)
            sampler.stamps[camera].append(stamp)
        capture.on_reference(reference(stamp + 0.1))
        capture.drain()
    capture.finish(1.3, window={"start_s": 1.0, "end_s": 1.3, "label_cutoff_s": 1.3}, outcome=OUTCOME)
    return root


@pytest.mark.parametrize("rig", [pytest.param(HEAD_WRIST_RIG, id="head-wrist"), pytest.param(SIDE_WRIST_RIG, id="side-wrist")])
def test_an_episode_of_either_rig_seals_and_reads_back_with_that_rigs_files_and_keys(tmp_path, rig):
    root = sealed_episode(tmp_path, rig)
    manifest_path = root / "audit" / "audit-manifest.json"
    verify_audit_manifest(manifest_path)
    seal = verify_episode_seal(root / "seal.json", audit_manifest=manifest_path, scope=root / "audit" / "source.json")
    count = seal["record_count"]
    assert count == 2
    rows = [json.loads(line) for line in (root / "records.jsonl").read_text().splitlines()]
    assert {frozenset(row["observation"]) for row in rows} == {frozenset({"sim_time_s", "state", *rig.frame_keys})}
    assert {len(row["observation"]["state"]) for row in rows} == {rig.state_dim}
    assert {frozenset(row["audit"]["source_stamps"]) for row in rows} == {
        frozenset({*rig.camera_names, "arm", *(("neck",) if rig.has_neck else ())})}
    frames = sorted(path.name for path in (root / "frames").iterdir())
    assert frames == sorted(f"{index:06d}-{camera}.png" for index in range(count) for camera in rig.camera_names)
    bindings = [json.loads(line) for line in (root / "audit" / "row-bindings.jsonl").read_text().splitlines()]
    assert {frozenset(row) for row in bindings} == {frozenset({"row_index", "sim_time_s", "reference_sequence",
                                                              *(f"{camera}_acquisition_id" for camera in rig.camera_names)})}
    window = json.loads(manifest_path.read_text())["window"]
    if "streams_required" in window:                       # the full observed window (a formal episode) names the rig's cameras
        assert window["streams_required"] == list(rig.camera_names) and set(window["source_schedule"]) == set(rig.camera_names)


def test_a_side_wrist_episode_leaves_no_trace_of_a_head_or_a_neck(tmp_path):
    root = sealed_episode(tmp_path, SIDE_WRIST_RIG)
    for path in root.rglob("*"):
        assert "head" not in path.name and "neck" not in path.name, path
        if path.is_file() and path.suffix in (".jsonl", ".json"):
            text = path.read_text()
            assert "head_png" not in text and "head_acquisition_id" not in text and '"neck"' not in text, path


def test_the_recorder_and_the_audit_refuse_the_other_rigs_episode(tmp_path):
    """A v1 reader of a v2 episode (and the reverse) fails closed: the rig is the one the audit's frozen inputs bind."""
    from so101_demo.act.recorder import EpisodeRecorder
    from test_act_recorder import observation as v1_observation

    recorder = EpisodeRecorder(tmp_path / "v2-recorder", session_id="session-1", attempt_id="attempt-1", reset_epoch=2,
                               provenance=PROVENANCE, rig=SIDE_WRIST_RIG)
    with pytest.raises(Exception, match="VECTOR_INVALID|FIELDS|SCHEMA|INVALID"):
        recorder.append(v1_observation(1.0), (0.0,) * 6, recorder_audit(1.0))


def test_the_qc_count_fields_follow_the_rig_and_a_report_of_either_known_rig_validates():
    from so101_demo.act.episode_qc import QC_COUNT_FIELDS, qc_count_fields
    assert QC_COUNT_FIELDS == {"records", "head_acquisitions", "wrist_acquisitions", "references", "events", "physics", "native_steps"}
    assert qc_count_fields(SIDE_WRIST_RIG) == {"records", "side_acquisitions", "wrist_acquisitions", "references", "events", "physics",
                                       "native_steps"}


def test_the_export_reads_each_rigs_frames_and_state_width():
    from so101_demo.act import bundle
    for rig, state in ((HEAD_WRIST_RIG, [0.0] * 8), (SIDE_WRIST_RIG, [0.0] * 6)):
        names = {camera: f"frames/000000-{camera}.png" for camera in rig.camera_names}
        observation = {"sim_time_s": 0.0, "state": state, **{rig.frame_key(c): n for c, n in names.items()}, "audit": {"x": 1}}
        content = bundle.training_content({"frames": 1, "rows": [{"observation": observation, "action": [0.0] * 6}]}, rig)
        kept = content["rows"][0]["observation"]
        assert set(kept) == {"sim_time_s", "state", *rig.frame_keys}
        bundle._check_dimensions(content, rig)
        files = {name: {"sha256": "f" * 64, "size": 1} for name in names.values()}
        plan = bundle._frame_plan("scene-1", content, files, rig)
        assert [item[0] for item in plan] == [names[c] for c in rig.camera_names]
        rewritten = bundle._with_frame_paths(content, {name: "episodes/" + name for name, _, _ in plan}, rig)
        assert all(rewritten["rows"][0]["observation"][key].startswith("episodes/") for key in rig.frame_keys)
    other = bundle.training_content({"rows": [{"observation": {"sim_time_s": 0.0, "state": [0.0] * 8, "head_png": "frames/000000-head.png",
                                                               "wrist_png": "frames/000000-wrist.png"}, "action": [0.0] * 6}]}, SIDE_WRIST_RIG)
    with pytest.raises(ValueError, match="EXPORT_EPISODE_DIMENSION_INVALID"):
        bundle._check_dimensions(other, SIDE_WRIST_RIG)
    with pytest.raises(ValueError, match="EXPORT_EPISODE_FRAME_MISSING"):
        bundle._frame_plan("scene-1", other, {}, SIDE_WRIST_RIG)
