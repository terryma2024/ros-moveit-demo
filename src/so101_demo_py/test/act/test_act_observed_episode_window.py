"""Actual PointEpisode sealing keeps source, label and physical clocks distinct."""

import json
import hashlib
import shutil

import pytest

from so101_demo.act.episode_assembly import PointEpisode, assemble_episode_capture, ProductionProducer
from so101_demo.act.episode_audit import verify_audit_manifest
from test_act_continuous_capture import AcquisitionGuard, AcquisitionMinter, feed, reference
from test_act_recorder import PROVENANCE
from test_act_seal_and_downgrade import IDENTITY, SCOPE, recorder_physical_audit


def point(tmp_path, *, commanded):
    root = tmp_path / "episode"
    capture = assemble_episode_capture(sampler=ProductionProducer(),
        physical_audit=recorder_physical_audit, guard=AcquisitionGuard(),
        identity=IDENTITY, provenance=PROVENANCE, inputs={"inputs_sha256": "a" * 64},
        episode_root=root, scope=SCOPE, scope_path=str(root / "audit" / "source.json"),
        deadline_s=120., monotonic=lambda: 0.)
    episode = PointEpisode.__new__(PointEpisode)
    episode.capture, episode._start_s = capture, 1.
    capture.start("session-1", "attempt-1", 2, 1.)
    if commanded:
        capture.on_event({"kind": "first_command", "sim_time_s": 1.})
    minter = AcquisitionMinter()
    for stamp in (1., 1.1, 1.2, 1.3):
        for camera in ("head", "wrist"):
            feed(capture, minter, camera=camera, stamp_s=stamp,
                 session="session-1", reset_epoch=2)
        if commanded:
            capture.on_reference(reference(stamp + .1))
        capture.drain()
    return episode, root


def test_point_seal_window_uses_actual_acquisitions_and_last_label(tmp_path):
    episode, root = point(tmp_path, commanded=True)
    summary = episode.finish(1.3, outcome={"status": "FAILED", "reason": "fixture_stop",
        "pick_place_validation_success": False, "stopped_confirmed": True})
    # Acceptance at t+0.1 must have passed, not merely reached the terminal clock.
    assert summary.sample_count == 2
    window = verify_audit_manifest(root / "audit" / "audit-manifest.json")["window"]
    assert window == {"source_schedule": {camera: [1., 1.1, 1.2, 1.3]
                                            for camera in ("head", "wrist")},
        "streams_required": ["head", "wrist"], "cadence_s": .1, "permitted_gaps_s": [],
        "collection_start_s": 1., "collection_end_s": 1.3, "first_command_s": 1.,
        "physics_end_s": 1.3, "label_cutoff_s": 1.1, "outcome": "complete"}
    assert json.loads((root / "seal.json").read_bytes())["status"] == "FAILED"


def test_no_command_window_never_invents_command_or_label(tmp_path):
    episode, root = point(tmp_path, commanded=False)
    episode.finish(1.3, outcome={"status": "FAILED", "reason": "before_dispatch",
        "pick_place_validation_success": False, "stopped_confirmed": True})
    window = verify_audit_manifest(root / "audit" / "audit-manifest.json")["window"]
    assert window["outcome"] == "no_command"
    assert window["first_command_s"] is None and window["label_cutoff_s"] is None
    assert window["collection_end_s"] == window["physics_end_s"] == 1.3


def test_physical_end_without_actual_rgb_coverage_cannot_seal(tmp_path):
    episode, root = point(tmp_path, commanded=True)
    with pytest.raises(ValueError, match="AUDIT_WINDOW_INVALID"):
        episode.finish(1.4, outcome={"status": "FAILED", "reason": "missing_tail",
            "pick_place_validation_success": False, "stopped_confirmed": True})
    assert not (root / "seal.json").exists()


def test_original_unselected_camera_tail_is_retained_in_the_window(tmp_path):
    episode, root = point(tmp_path, commanded=True)
    # Explicit source fixture: the next original publisher sequence is five.
    from so101_demo.act.acquisition import Acquisition
    from test_act_continuous_capture import ZERO
    from so101_demo.act.acquisition import pixel_digest
    for camera in ("head", "wrist"):
        frame = Acquisition(camera, "session-1", 2, 5, f"session-1/2/{camera}/5",
            1.35, 1_350_000_001, (480, 640, 3), "uint8", pixel_digest(ZERO))
        episode.capture.on_acquisition(frame, ZERO)
        episode.capture.sampler.stamps[camera].append(1.35)
    episode.finish(1.3, outcome={"status": "FAILED", "reason": "fixture_stop",
        "pick_place_validation_success": False, "stopped_confirmed": True})
    window = verify_audit_manifest(root / "audit" / "audit-manifest.json")["window"]
    assert window["collection_end_s"] == 1.35
    assert window["physics_end_s"] == 1.3
    assert window["source_schedule"] == {camera: [1., 1.1, 1.2, 1.3, 1.35]
                                           for camera in ("head", "wrist")}


@pytest.mark.parametrize("change", ["missing_interior", "foreign_camera", "duplicate_required",
    "missing_required", "label_cutoff", "collection_start", "collection_end", "cadence", "permitted_gap"])
def test_diagnostic_window_recomputes_original_camera_inventory_and_labels(tmp_path, change):
    episode, root = point(tmp_path, commanded=True)
    episode.finish(1.3, outcome={"status": "FAILED", "reason": "fixture_stop",
        "pick_place_validation_success": False, "stopped_confirmed": True})
    path = root / "audit" / "audit-manifest.json"
    original = path.read_bytes()
    assert verify_audit_manifest(path)["window"]["label_cutoff_s"] == 1.1
    document = json.loads(original)
    window = document["window"]
    if change == "missing_interior":
        window["source_schedule"]["head"].remove(1.1)
    elif change == "foreign_camera":
        window["source_schedule"]["imagined"] = window["source_schedule"]["head"][:]
    elif change == "duplicate_required":
        window["streams_required"] = ["head", "head", "wrist"]
    elif change == "missing_required":
        window["streams_required"] = ["head"]
    elif change == "label_cutoff":
        window["label_cutoff_s"] = 1.2
    elif change == "collection_start":
        window["collection_start_s"] = .9
    elif change == "collection_end":
        window["collection_end_s"] = 1.4
    elif change == "cadence":
        window["cadence_s"] = .2
    elif change == "permitted_gap":
        window["permitted_gaps_s"] = [[1., 1.3]]
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="AUDIT_WINDOW_INVALID"):
        verify_audit_manifest(path)
    path.write_bytes(original)
    assert verify_audit_manifest(path)["window"]["label_cutoff_s"] == 1.1


@pytest.mark.parametrize("change", ["sequence_hole", "foreign_session", "foreign_reset"])
def test_unused_original_camera_tail_cannot_escape_episode_identity_or_sequence(tmp_path, change):
    episode, root = point(tmp_path, commanded=True)
    episode.finish(1.3, outcome={"status": "FAILED", "reason": "fixture_stop",
        "pick_place_validation_success": False, "stopped_confirmed": True})
    original_manifest = root / "audit/audit-manifest.json"
    original_sha = hashlib.sha256(original_manifest.read_bytes()).hexdigest()
    assert verify_audit_manifest(original_manifest)["window"]["collection_end_s"] == 1.3
    isolated = tmp_path / "isolated-tail"
    shutil.copytree(root, isolated)
    target = isolated / "audit/acquisitions.jsonl"
    rows = [json.loads(line) for line in target.read_text().splitlines()]
    tail = next(row for row in rows if row["camera"] == "head" and row["sequence"] == 4)
    # Only unlabelled tail identity changes, so all recorded row bindings still resolve.
    if change == "sequence_hole":
        tail["sequence"] = 6
    elif change == "foreign_session":
        tail["session_id"] = "foreign"
    else:
        tail["reset_epoch"] += 1
    tail["acquisition_id"] = f'{tail["session_id"]}/{tail["reset_epoch"]}/{tail["camera"]}/{tail["sequence"]}'
    payload = ("\n".join(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows) + "\n").encode()
    target.write_bytes(payload)
    path = isolated / "audit/audit-manifest.json"
    document = json.loads(path.read_bytes())
    document["files"][target.name].update(size=len(payload), sha256=hashlib.sha256(payload).hexdigest())
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="AUDIT_ACQUISITION_INVALID"):
        verify_audit_manifest(path)
    assert hashlib.sha256(original_manifest.read_bytes()).hexdigest() == original_sha
    assert verify_audit_manifest(original_manifest)["window"]["collection_end_s"] == 1.3
