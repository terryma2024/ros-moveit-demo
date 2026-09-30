"""Task 3: one raw audit per episode, sealed once and verified by recomputation.

The writer is the only writer. A row cannot be bound to an acquisition the audit never saw, one
acquisition cannot fill two rows, a physics observation from a stale release epoch is refused, an
unknown schema field is refused, and the manifest is written last and never rewritten. Verification
re-reads the files and recomputes their digests, so a changed raw reference is detected rather than
trusted.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from so101_demo.act.acquisition import AcquisitionMinter
from so101_demo.act.episode_audit import (
    MANIFEST_KIND,
    SOURCE_KINDS,
    EpisodeAuditWriter,
    verify_audit_manifest,
)

ZERO = np.zeros((480, 640, 3), dtype=np.uint8)


def identity():
    return {"session_id": "s", "attempt_id": "attempt-1", "reset_epoch": 1, "release_epoch": 1,
            "scene_id": "default", "seed": 0, "mode": "preselected_target_diagnostic"}


def scope():
    return {"kind": "ACT_COLLECTION_SCOPE", "schema_version": 1,
            "mode": "preselected_target_diagnostic", "scene_id": "default", "seed": 0,
            "inputs_sha256": "a" * 64}


def complete_audit(tmp_path):
    """Every closed field and file this task writes, with real files and real hashes."""

    writer = EpisodeAuditWriter(tmp_path / "episode", scope(), identity(),
                                {"inputs_sha256": "a" * 64})
    minter = AcquisitionMinter()
    # one frame per camera per instant: a row binds the head frame to the head slot and the wrist frame
    # to the wrist slot, which is exactly the relationship the review's counterexample violated
    frames = {}
    for camera in ("head", "wrist"):
        for stamp in (1.0, 1.1):
            frame = minter.mint(camera, session_id="s", reset_epoch=1, stamp_s=stamp,
                                received_monotonic_ns=int(stamp * 1e9) + 1, pixels=ZERO)
            writer.append_acquisition(frame)
            frames[(camera, stamp)] = frame
    writer.append_source("references", {"reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE",
                                        "positions": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
                                        "accepted": True})
    writer.append_source("events", {"kind": "phase_complete", "identity": identity(),
                                    "sim_time_s": 1.0, "monotonic_ns": 1000,
                                    "payload": {"phase": "SEARCH", "physics_step": 1}})
    # the raw block follows what the MuJoCo source actually publishes, plus the verified support flag
    writer.append_source("physics", {
        "kind": "support", "sim_time_s": 1.1, "release_epoch": 1,
        "observation": {"simulation_time_s": 1.1, "simulation_step": 11, "left_contact_count": 2,
                        "right_contact_count": 2, "table_contact": True, "supported": True,
                        "maximum_normal_force_n": 0.4, "cup_position_world_m": [0.02, -0.28, 0.165]}})
    writer.append_source("physics", {
        "kind": "retract", "sim_time_s": 1.2, "release_epoch": 1,
        "observation": {"simulation_time_s": 1.2, "simulation_step": 12, "left_contact_count": 0,
                        "right_contact_count": 0, "table_contact": True,
                        "maximum_normal_force_n": 0.0, "cup_position_world_m": [0.02, -0.28, 0.165]}})
    writer.bind_row(0, 1.0, frames[("head", 1.0)].acquisition_id,
                    frames[("wrist", 1.0)].acquisition_id, 1)
    window = {"start_s": 1.0, "end_s": 1.2, "label_cutoff_s": 1.0}
    return writer, window


def test_sealed_audit_is_not_overwritten(tmp_path):
    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    original = path.read_bytes()
    with pytest.raises(ValueError, match="AUDIT_ALREADY_SEALED"):
        writer.seal(window)
    assert path.read_bytes() == original


def test_a_sealed_audit_verifies_by_recomputation(tmp_path):
    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    manifest = verify_audit_manifest(path)
    assert manifest["kind"] == MANIFEST_KIND
    assert set(manifest["files"]) == {"acquisitions.jsonl", "row-bindings.jsonl",
                                      "events.jsonl", "references.jsonl", "physics.jsonl",
                                      "source.json", "inputs.json", "episode.json"}
    assert manifest["window"] == window
    assert manifest["schema_version"] == 2 and manifest["identity"] == identity()
    assert manifest["scope_sha256"] == hashlib.sha256((path.parent / "source.json").read_bytes()).hexdigest()


def test_a_changed_raw_reference_is_detected(tmp_path):
    """The sealed audit is verified by recomputing the bytes, not by trusting the manifest."""

    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    references = writer.files.references
    document = json.loads(references.read_text().splitlines()[0])
    document["positions"][0] = 0.9
    references.write_bytes((json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode())
    with pytest.raises(ValueError, match="AUDIT_HASH_MISMATCH"):
        verify_audit_manifest(path)


def test_a_missing_acquisition_binding_is_refused(tmp_path):
    writer = EpisodeAuditWriter(tmp_path / "episode", scope(), identity(),
                                {"inputs_sha256": "a" * 64})
    minter = AcquisitionMinter()
    frame = minter.mint("head", session_id="s", reset_epoch=1, stamp_s=1.0,
                        received_monotonic_ns=1, pixels=ZERO)
    writer.append_acquisition(frame)
    with pytest.raises(ValueError, match="AUDIT_BINDING_UNKNOWN"):
        writer.bind_row(0, 1.0, frame.acquisition_id, "s/1/wrist/1", 1)


def test_one_acquisition_cannot_fill_two_rows(tmp_path):
    writer = EpisodeAuditWriter(tmp_path / "episode", scope(), identity(),
                                {"inputs_sha256": "a" * 64})
    minter = AcquisitionMinter()
    head = minter.mint("head", session_id="s", reset_epoch=1, stamp_s=1.0,
                       received_monotonic_ns=1, pixels=ZERO)
    wrist = minter.mint("wrist", session_id="s", reset_epoch=1, stamp_s=1.0,
                        received_monotonic_ns=1, pixels=ZERO)
    writer.append_acquisition(head)
    writer.append_acquisition(wrist)
    writer.append_source("references", {"reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE",
                                        "positions": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
                                        "accepted": True})
    writer.bind_row(0, 1.0, head.acquisition_id, wrist.acquisition_id, 1)
    with pytest.raises(ValueError, match="AUDIT_BINDING_REUSED"):
        writer.bind_row(1, 1.1, head.acquisition_id, wrist.acquisition_id, 1)


def test_an_unknown_schema_field_is_refused(tmp_path):
    writer, _ = complete_audit(tmp_path)
    with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
        writer.append_source("events", {"kind": "phase_complete", "identity": identity(),
                                        "sim_time_s": 1.0, "monotonic_ns": 1,
                                        "payload": {"phase": "SEARCH", "physics_step": 1},
                                        "success": True})
    with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
        writer.append_source("references", {"reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE",
                                            "positions": [0.1] * 6, "accepted": True, "extra": 1})
    with pytest.raises(ValueError, match="AUDIT_SOURCE_KIND_INVALID"):
        writer.append_source("planning_scene", {"sim_time_s": 1.0})
    with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
        writer.append_source("physics", {"kind": "unknown_kind", "sim_time_s": 1.0,
                                         "release_epoch": 1, "observation": {}})


def test_stale_support_across_a_release_epoch_is_refused(tmp_path):
    """A support observation from an older release epoch may not justify a later release."""

    writer, _ = complete_audit(tmp_path)
    writer.append_source("physics", {"kind": "support", "sim_time_s": 1.3, "release_epoch": 2,
                                     "observation": {"simulation_time_s": 1.3, "simulation_step": 13,
                                                     "table_contact": True, "supported": True}})
    with pytest.raises(ValueError, match="AUDIT_RELEASE_EPOCH_STALE"):
        writer.append_source("physics", {"kind": "support", "sim_time_s": 1.4, "release_epoch": 1,
                                         "observation": {"simulation_time_s": 1.4,
                                                         "simulation_step": 14, "table_contact": True,
                                                         "supported": True}})


def test_a_stale_epoch_in_a_sealed_audit_is_detected_on_readback(tmp_path):
    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    physics = writer.files.physics
    lines = physics.read_bytes().splitlines()
    lines.insert(1, json.dumps({"sequence": 9, "kind": "support", "sim_time_s": 1.15,
                                "release_epoch": 0,
                                "observation": {"simulation_time_s": 1.15, "simulation_step": 1,
                                                "table_contact": True, "supported": True}},
                               sort_keys=True, separators=(",", ":")).encode())
    physics.write_bytes(b"\n".join(lines) + b"\n")
    with pytest.raises(ValueError, match="AUDIT_HASH_MISMATCH"):
        verify_audit_manifest(path)


def test_a_missing_inputs_digest_is_refused(tmp_path):
    with pytest.raises(ValueError, match="AUDIT_SCOPE_INVALID"):
        EpisodeAuditWriter(tmp_path / "episode", scope(), identity(), {})
    with pytest.raises(ValueError, match="AUDIT_INPUTS_INVALID"):
        EpisodeAuditWriter(tmp_path / "episode", scope(), identity(), {"candidate": "x"})
    with pytest.raises(ValueError, match="AUDIT_INPUTS_INVALID"):
        EpisodeAuditWriter(tmp_path / "episode", scope(), identity(),
                           {"inputs_sha256": "not-a-digest"})


def test_every_source_kind_is_closed_and_the_writer_is_exclusive(tmp_path):
    assert SOURCE_KINDS == ("events", "references", "physics")
    writer, window = complete_audit(tmp_path)
    writer.seal(window)
    with pytest.raises(ValueError, match="AUDIT_ALREADY_SEALED"):
        writer.append_acquisition(None)
    with pytest.raises(ValueError, match="AUDIT_ALREADY_SEALED"):
        writer.append_source("events", {"kind": "phase_complete", "identity": identity(),
                                        "sim_time_s": 2.0, "monotonic_ns": 5,
                                        "payload": {"phase": "SEARCH", "physics_step": 2}})
    with pytest.raises(FileExistsError):
        EpisodeAuditWriter(tmp_path / "episode", scope(), identity(),
                           {"inputs_sha256": "a" * 64})


def _resign(writer, manifest_path, name, payload):
    """Rewrite one stream and make the manifest agree, so only semantics can catch it."""

    (manifest_path.parent / name).write_bytes(payload)
    document = json.loads(manifest_path.read_bytes())
    document["files"][name] = {"path": name, "size": len(payload),
                               "sha256": hashlib.sha256(payload).hexdigest()}
    manifest_path.write_bytes(json.dumps(document, sort_keys=True, separators=(",", ":")).encode())
    return manifest_path


def test_an_inventory_that_omits_a_stream_is_refused(tmp_path):
    """A manifest may not leave a stream unchecked by leaving it out (T3-F3)."""

    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    document = json.loads(path.read_bytes())
    del document["files"]["references.jsonl"]
    path.write_bytes(json.dumps(document, sort_keys=True, separators=(",", ":")).encode())
    with pytest.raises(ValueError, match="AUDIT_MANIFEST_INVENTORY_INVALID"):
        verify_audit_manifest(path)


def test_an_inventory_entry_with_an_unsafe_path_is_refused(tmp_path):
    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    document = json.loads(path.read_bytes())
    document["files"]["events.jsonl"] = {"path": "../events.jsonl", "size": 0, "sha256": "a" * 64}
    path.write_bytes(json.dumps(document, sort_keys=True, separators=(",", ":")).encode())
    with pytest.raises(ValueError, match="AUDIT_MANIFEST_INVENTORY_INVALID"):
        verify_audit_manifest(path)


def test_a_checksum_consistent_reference_with_an_extra_field_is_refused(tmp_path):
    """Re-validating semantics is what catches a self-consistent but schema-breaking stream."""

    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    row = json.loads((path.parent / "references.jsonl").read_text().splitlines()[0])
    row["extra"] = True
    payload = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
    _resign(writer, path, "references.jsonl", payload)
    with pytest.raises(ValueError, match="AUDIT_REFERENCE_INVALID"):
        verify_audit_manifest(path)


def test_a_checksum_consistent_duplicate_row_index_is_refused(tmp_path):
    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    lines = (path.parent / "row-bindings.jsonl").read_text().splitlines()
    duplicated = json.loads(lines[0])
    duplicated["head_acquisition_id"] = "s/1/wrist/1"
    duplicated["wrist_acquisition_id"] = "s/1/head/1"
    payload = ("\n".join([*lines, json.dumps(duplicated, sort_keys=True,
                                              separators=(",", ":"))]) + "\n").encode()
    _resign(writer, path, "row-bindings.jsonl", payload)
    with pytest.raises(ValueError, match="AUDIT_ROW_INVALID"):
        verify_audit_manifest(path)


def _staging(tmp_path, *, reset_epoch=1, identity_reset=1):
    """A writer with one real head/wrist pair at 1.0 and one accepted reference at 1.1."""

    from so101_demo.act.acquisition import AcquisitionMinter

    tmp_path.mkdir(parents=True, exist_ok=True)
    writer = EpisodeAuditWriter(tmp_path / "episode",
                                scope(),
                                {"session_id": "s", "attempt_id": "a",
                                 "reset_epoch": identity_reset, "release_epoch": 1},
                                {"inputs_sha256": "a" * 64})
    minter = AcquisitionMinter()
    frames = {}
    for camera in ("head", "wrist"):
        frame = minter.mint(camera, session_id="s", reset_epoch=reset_epoch, stamp_s=1.0,
                            received_monotonic_ns=1, pixels=ZERO)
        writer.append_acquisition(frame)
        frames[camera] = frame.acquisition_id
    writer.append_source("references", {"reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE",
                                        "positions": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
                                        "accepted": True})
    return writer, frames


def test_a_row_may_not_bind_the_wrong_camera(tmp_path):
    """The head slot takes a head acquisition and the wrist slot a wrist one (T3-F2)."""

    writer, frames = _staging(tmp_path)
    with pytest.raises(ValueError, match="AUDIT_BINDING_INVALID"):
        writer.bind_row(0, 1.0, frames["wrist"], frames["head"], 1)


def test_the_same_acquisition_may_not_fill_both_slots(tmp_path):
    writer, frames = _staging(tmp_path)
    with pytest.raises(ValueError, match="AUDIT_BINDING_INVALID"):
        writer.bind_row(0, 1.0, frames["head"], frames["head"], 1)


def test_a_cross_reset_acquisition_is_refused(tmp_path):
    writer, frames = _staging(tmp_path, reset_epoch=7, identity_reset=1)
    with pytest.raises(ValueError, match="AUDIT_BINDING_INVALID"):
        writer.bind_row(0, 1.0, frames["head"], frames["wrist"], 1)


def test_a_binding_must_name_an_accepted_reference_for_that_instant(tmp_path):
    writer, frames = _staging(tmp_path)
    with pytest.raises(ValueError, match="AUDIT_BINDING_REFERENCE_INVALID"):
        writer.bind_row(0, 1.0, frames["head"], frames["wrist"], 2)      # no such sequence
    writer.append_source("references", {"reference_time_s": 1.3, "source": "CONTROLLER_REFERENCE",
                                        "positions": [0.1] * 6, "accepted": True})
    with pytest.raises(ValueError, match="AUDIT_BINDING_REFERENCE_INVALID"):
        writer.bind_row(0, 1.0, frames["head"], frames["wrist"], 2)      # that reference is for 1.3
    other, other_frames = _staging(tmp_path / "second")
    other.append_source("references", {"reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE",
                                       "positions": [0.1] * 6, "accepted": False})
    with pytest.raises(ValueError, match="AUDIT_BINDING_REFERENCE_INVALID"):
        # the revocation voids the earlier acceptance for the same instant (T3-F2 residual)
        other.bind_row(0, 1.0, other_frames["head"], other_frames["wrist"], 1)


def test_rows_must_be_a_contiguous_schedule(tmp_path):
    writer, frames = _staging(tmp_path)
    writer.append_source("references", {"reference_time_s": 1.2, "source": "CONTROLLER_REFERENCE",
                                        "positions": [0.1] * 6, "accepted": True})
    with pytest.raises(ValueError, match="AUDIT_ROW_ORDER_INVALID"):
        writer.bind_row(1, 1.1, frames["head"], frames["wrist"], 2)


def test_a_future_or_stale_frame_is_not_causal_for_a_row(tmp_path):
    from so101_demo.act.acquisition import AcquisitionMinter

    for stamp, code in ((2.0, "AUDIT_BINDING_CAUSALITY_INVALID"),
                        (0.5, "AUDIT_BINDING_CAUSALITY_INVALID")):
        base = tmp_path / f"case-{stamp}"
        base.mkdir(parents=True)
        writer = EpisodeAuditWriter(base / "episode", scope(),
                                    {"session_id": "s", "attempt_id": "a", "reset_epoch": 1,
                                     "release_epoch": 1}, {"inputs_sha256": "a" * 64})
        minter = AcquisitionMinter()
        frames = {}
        for camera in ("head", "wrist"):
            frame = minter.mint(camera, session_id="s", reset_epoch=1, stamp_s=stamp,
                                received_monotonic_ns=1, pixels=ZERO)
            writer.append_acquisition(frame)
            frames[camera] = frame.acquisition_id
        writer.append_source("references", {"reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE",
                                            "positions": [0.1] * 6, "accepted": True})
        with pytest.raises(ValueError, match=code):
            writer.bind_row(0, 1.0, frames["head"], frames["wrist"], 1)


def test_rows_must_sit_on_the_10hz_grid(tmp_path):
    from so101_demo.act.acquisition import AcquisitionMinter

    writer = EpisodeAuditWriter(tmp_path / "episode", scope(),
                                {"session_id": "s", "attempt_id": "a", "reset_epoch": 1,
                                 "release_epoch": 1}, {"inputs_sha256": "a" * 64})
    minter = AcquisitionMinter()
    ids = {}
    for stamp in (1.0, 1.3):
        for camera in ("head", "wrist"):
            frame = minter.mint(camera, session_id="s", reset_epoch=1, stamp_s=stamp,
                                received_monotonic_ns=1, pixels=ZERO)
            writer.append_acquisition(frame)
            ids[(camera, stamp)] = frame.acquisition_id
    for target in (1.1, 1.4):
        writer.append_source("references", {"reference_time_s": target,
                                            "source": "CONTROLLER_REFERENCE",
                                            "positions": [0.1] * 6, "accepted": True})
    writer.bind_row(0, 1.0, ids[("head", 1.0)], ids[("wrist", 1.0)], 1)
    with pytest.raises(ValueError, match="AUDIT_ROW_SCHEDULE_INVALID"):
        writer.bind_row(1, 1.3, ids[("head", 1.3)], ids[("wrist", 1.3)], 2)


def test_a_late_revocation_prevents_sealing_a_bound_row(tmp_path):
    writer, frames = _staging(tmp_path)
    writer.bind_row(0, 1.0, frames["head"], frames["wrist"], 1)
    writer.append_source("references", {"reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE",
                                        "positions": [0.1] * 6, "accepted": False})
    with pytest.raises(ValueError, match="AUDIT_BINDING_REVOKED"):
        writer.seal({"start_s": 1.0})


def test_readback_refuses_a_resigned_swapped_binding(tmp_path):
    """The reviewer's checksum-consistent counterexample: swap the camera slots and re-sign."""

    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    row = json.loads((path.parent / "row-bindings.jsonl").read_text().splitlines()[0])
    row["head_acquisition_id"], row["wrist_acquisition_id"] = (row["wrist_acquisition_id"],
                                                               row["head_acquisition_id"])
    payload = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
    _resign(writer, path, "row-bindings.jsonl", payload)
    with pytest.raises(ValueError, match="AUDIT_BINDING_UNKNOWN"):
        verify_audit_manifest(path)


def test_readback_refuses_a_resigned_unresolvable_reference_sequence(tmp_path):
    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    row = json.loads((path.parent / "row-bindings.jsonl").read_text().splitlines()[0])
    row["reference_sequence"] = 99
    payload = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
    _resign(writer, path, "row-bindings.jsonl", payload)
    with pytest.raises(ValueError, match="AUDIT_BINDING_REFERENCE_INVALID"):
        verify_audit_manifest(path)


def test_readback_refuses_a_resigned_unknown_event(tmp_path):
    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    lines = (path.parent / "events.jsonl").read_text().splitlines()
    payload = ("\n".join([*lines, json.dumps({"sequence": len(lines) + 1, "kind": "claim",
                                              "identity": identity(), "sim_time_s": None,
                                              "monotonic_ns": 5, "payload": {}},
                                             sort_keys=True, separators=(",", ":"))]) + "\n").encode()
    _resign(writer, path, "events.jsonl", payload)
    with pytest.raises(ValueError, match="AUDIT_EVENT_INVALID"):
        verify_audit_manifest(path)


def test_the_scope_and_identity_must_be_the_frozen_contracts(tmp_path):
    for bad_scope, code in (
            ({"kind": "ACT_EPISODE_AUDIT", "schema_version": 1,
              "mode": "preselected_target_diagnostic", "scene_id": "default", "seed": 0,
              "inputs_sha256": "a" * 64}, "AUDIT_SCOPE_INVALID"),
            ({"kind": "ACT_COLLECTION_SCOPE", "schema_version": 2, "mode": "formal",
              "scene_id": "default", "seed": 0, "inputs_sha256": "a" * 64},
             "AUDIT_SCOPE_INVALID"),
            ({"kind": "ACT_COLLECTION_SCOPE", "schema_version": 1, "mode": "live",
              "scene_id": "default", "seed": 0, "inputs_sha256": "a" * 64},
             "AUDIT_SCOPE_INVALID"),
            ({"kind": "ACT_COLLECTION_SCOPE", "schema_version": 1, "mode": "formal",
              "scene_id": "default", "seed": 0, "inputs_sha256": "a" * 64, "extra": 1},
             "AUDIT_SCOPE_INVALID")):
        with pytest.raises(ValueError, match=code):
            EpisodeAuditWriter(tmp_path / "episode", bad_scope, identity(),
                               {"inputs_sha256": "a" * 64})
    for bad_identity in ({"session_id": "s", "attempt_id": "a", "reset_epoch": 1},
                         {"session_id": "s", "attempt_id": "a", "release_epoch": 1},
                         {"attempt_id": "a", "reset_epoch": 1, "release_epoch": 1}):
        with pytest.raises(ValueError, match="AUDIT_IDENTITY_INVALID"):
            EpisodeAuditWriter(tmp_path / "episode", scope(), bad_identity,
                               {"inputs_sha256": "a" * 64})


def test_readback_refuses_a_resigned_scope_document(tmp_path):
    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    document = json.loads((path.parent / "source.json").read_bytes())
    document["mode"] = "live"
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    (path.parent / "source.json").write_bytes(payload)
    manifest = json.loads(path.read_bytes())
    manifest["files"]["source.json"] = {"path": "source.json", "size": len(payload),
                                        "sha256": hashlib.sha256(payload).hexdigest()}
    manifest["scope_sha256"] = hashlib.sha256(payload).hexdigest()
    path.write_bytes(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode())
    with pytest.raises(ValueError, match="AUDIT_METADATA_INVALID"):
        verify_audit_manifest(path)


@pytest.mark.parametrize("stream, mutate, code", [
    ("row-bindings.jsonl", lambda row: row.update({"row_index": 7}), "AUDIT_ROW_INVALID"),
    ("events.jsonl", lambda row: row["payload"].update({"physics_step": -1}), "AUDIT_EVENT_INVALID"),
    ("physics.jsonl", lambda row: row.update({"release_epoch": -1}), "AUDIT_PHYSICS_INVALID"),
    ("references.jsonl", lambda row: row.update({"sequence": 1.0}), "AUDIT_REFERENCE_INVALID"),
])
def test_readback_refuses_resigned_records_that_admission_would_reject(tmp_path, stream, mutate,
                                                                      code):
    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    row = json.loads((path.parent / stream).read_text().splitlines()[0])
    mutate(row)
    payload = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
    _resign(writer, path, stream, payload)
    with pytest.raises(ValueError, match=code):
        verify_audit_manifest(path)


def test_readback_refuses_a_nonfinite_reference_position(tmp_path):
    """`1e309` decodes to infinity in JSON, which admission rejects and readback must too."""

    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    lines = (path.parent / "references.jsonl").read_bytes().splitlines()
    payload = lines[0].replace(b"0.1", b"1e309", 1) + b"\n"
    _resign(writer, path, "references.jsonl", payload)
    with pytest.raises(ValueError, match="AUDIT_REFERENCE_INVALID"):
        verify_audit_manifest(path)


def test_readback_compares_the_scope_and_inputs_digests(tmp_path):
    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    document = json.loads((path.parent / "inputs.json").read_bytes())
    document["inputs_sha256"] = "b" * 64
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    _resign(writer, path, "inputs.json", payload)
    with pytest.raises(ValueError, match="AUDIT_METADATA_INVALID"):
        verify_audit_manifest(path)


def _lease(**overrides):
    lease = {"batch_id": "batch-1", "coordinator_epoch": 1, "worker_id": "worker-1",
             "worker_generation": 1, "point_id": "point-1", "attempt_id": "attempt-1",
             "lease_generation": 1, "lease_issued_monotonic_s": 100.0,
             "lease_deadline_monotonic_s": 200.0}
    lease.update(overrides)
    return lease


def test_a_formal_audit_requires_the_registered_lease_contract(tmp_path):
    """The plan's formal scope needs the full lease; the contract already exists, so reuse it."""

    formal = dict(scope(), mode="formal")
    formal_identity = {**identity(), "lease": _lease()}
    writer = EpisodeAuditWriter(tmp_path / "ok", formal, formal_identity, {"inputs_sha256": "a" * 64})
    assert writer.identity["lease"]["batch_id"] == "batch-1"

    with pytest.raises(ValueError, match="AUDIT_IDENTITY_INVALID"):
        EpisodeAuditWriter(tmp_path / "no-lease", formal, identity(), {"inputs_sha256": "a" * 64})
    for broken in (_lease(lease_deadline_monotonic_s=100.0), _lease(worker_generation=0),
                   _lease(attempt_id="other-attempt"), _lease(batch_id="")):
        with pytest.raises(ValueError, match="AUDIT_IDENTITY_INVALID"):
            EpisodeAuditWriter(tmp_path / "broken", formal, {**identity(), "lease": broken},
                               {"inputs_sha256": "a" * 64})
    # a diagnostic audit stays admissible without a lease, keeping the modes distinct
    EpisodeAuditWriter(tmp_path / "diagnostic", scope(), identity(), {"inputs_sha256": "a" * 64})


@pytest.mark.parametrize("kind, payload", [
    ("dispatch", {"owner": "worker-1", "permit_id": "permit-1"}),
    ("accept", {"permit_id": "permit-1"}),
    ("revoke", {"permit_id": "permit-1", "reason": "deadline"}),
    ("stop", {"reason": "TASK8_ABORT", "stopped_confirmed": True}),
    ("contact", {"left_contacts": 2, "right_contacts": 2, "table_contact": True}),
    # a release event describes the epoch its own identity claims
    ("release", {"release_epoch": 1, "supported": True, "no_fingertip_contact": True}),
    ("final_check", {"placement_stable": True, "retreat_stable": True}),
])
def test_the_required_event_kinds_are_accepted_and_refuse_a_wrong_payload(tmp_path, kind, payload):
    writer = EpisodeAuditWriter(tmp_path / "episode", scope(), identity(),
                                {"inputs_sha256": "a" * 64})
    writer.append_source("events", {"kind": kind, "identity": identity(), "sim_time_s": 1.0,
                                    "monotonic_ns": 1000, "payload": payload})
    # a boolean where a count belongs and an extra key are both refused for a declared kind
    for broken in ({**payload, "extra": 1},
                   {**payload, **({"left_contacts": True} if kind == "contact"
                                  else {"reason": True} if "reason" in payload
                                  else {"permit_id": 1} if "permit_id" in payload
                                  else {"stopped_confirmed": 1} if kind == "stop"
                                  else {"release_epoch": True} if kind == "release"
                                  else {"placement_stable": "yes"} if kind == "final_check"
                                  else {"owner": 1})}):
        other = EpisodeAuditWriter(tmp_path / f"bad-{len(broken)}", scope(), identity(),
                                   {"inputs_sha256": "a" * 64})
        with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
            other.append_source("events", {"kind": kind, "identity": identity(), "sim_time_s": 1.0,
                                           "monotonic_ns": 1000, "payload": broken})


def test_the_physics_observation_must_follow_the_source_contract(tmp_path):
    """The raw block is typed against what the MuJoCo source actually publishes (T3-F1)."""

    good = {"simulation_time_s": 1.1, "simulation_step": 11, "left_contact_count": 2,
            "right_contact_count": 2, "table_contact": True, "maximum_normal_force_n": 0.5,
            "cup_position_world_m": [0.02, -0.28, 0.165], "other_contact_geoms": ["table_collision"]}
    writer = EpisodeAuditWriter(tmp_path / "ok", scope(), identity(), {"inputs_sha256": "a" * 64})
    writer.append_source("physics", {"kind": "contact", "sim_time_s": 1.1, "release_epoch": 1,
                                     "observation": good})
    for broken in ({**good, "extra": 1}, {**good, "left_contact_count": True},
                   {**good, "table_contact": 1}, {**good, "maximum_normal_force_n": -0.1},
                   {**good, "cup_position_world_m": [0.0, 0.0]},
                   {**good, "cup_position_world_m": [0.0, 0.0, float("inf")]},
                   {key: value for key, value in good.items() if key != "simulation_time_s"}):
        other = EpisodeAuditWriter(tmp_path / f"bad-{len(str(broken))}-{id(broken) % 97}", scope(),
                                   identity(), {"inputs_sha256": "a" * 64})
        with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
            other.append_source("physics", {"kind": "contact", "sim_time_s": 1.1,
                                            "release_epoch": 1, "observation": broken})


def test_a_reference_record_may_preserve_the_observer_raw_frame(tmp_path):
    """The audit must be able to hold the raw history the observer keeps (T3-F1)."""

    raw = {"joint_names": ["shoulder_pan", "shoulder_lift"], "sim_stamp_ns": 1100000000,
           "received_monotonic_ns": 900000, "velocities": [0.0, 0.0]}
    writer = EpisodeAuditWriter(tmp_path / "ok", scope(), identity(), {"inputs_sha256": "a" * 64})
    writer.append_source("references", {"reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE",
                                        "positions": [0.1] * 6, "accepted": True, **raw})
    for broken in ({"joint_names": []}, {"sim_stamp_ns": 0}, {"received_monotonic_ns": -1},
                   {"velocities": [0.0]}, {"velocities": ["x", "y"]}):
        other = EpisodeAuditWriter(tmp_path / f"bad-{sorted(broken)[0]}-{len(str(broken))}", scope(),
                                   identity(), {"inputs_sha256": "a" * 64})
        with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
            other.append_source("references", {"reference_time_s": 1.1,
                                               "source": "CONTROLLER_REFERENCE",
                                               "positions": [0.1] * 6, "accepted": True, **broken})
    # a partial raw group is refused: all four fields or none
    third = EpisodeAuditWriter(tmp_path / "partial", scope(), identity(), {"inputs_sha256": "a" * 64})
    with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
        third.append_source("references", {"reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE",
                                           "positions": [0.1] * 6, "accepted": True,
                                           "joint_names": ["a", "b"]})


def test_readback_refuses_a_resigned_partial_raw_reference(tmp_path):
    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    lines = (path.parent / "references.jsonl").read_text().splitlines()
    row = json.loads(lines[0])
    row["joint_names"] = ["a", "b"]
    payload = ("\n".join([json.dumps(row, sort_keys=True, separators=(",", ":"))]) + "\n").encode()
    _resign(writer, path, "references.jsonl", payload)
    with pytest.raises(ValueError, match="AUDIT_REFERENCE_INVALID"):
        verify_audit_manifest(path)


def test_a_registered_source_document_is_admitted_and_a_time_only_block_is_not(tmp_path):
    """The real evidence_dict document must pass; a timestamp alone must not (T3-F1)."""

    document = {"publisher_sequence": 7, "simulation_time_s": 1.1, "simulation_step": 11,
                "reset_epoch": 1, "paused": False, "left_contact_count": 2, "right_contact_count": 2,
                "table_contact": True, "other_contact_geoms": ["table_collision"],
                "maximum_normal_force_n": 0.5, "cup_position_world_m": [0.02, -0.28, 0.165],
                "cup_orientation_world_xyzw": [0.0, 0.0, 0.0, 1.0],
                "cup_linear_velocity_world_m_s": [0.0, 0.0, 0.0],
                "cup_angular_velocity_world_rad_s": [0.0, 0.0, 0.0]}
    writer = EpisodeAuditWriter(tmp_path / "ok", scope(), identity(), {"inputs_sha256": "a" * 64})
    writer.append_source("physics", {"kind": "contact", "sim_time_s": 1.1, "release_epoch": 1,
                                     "observation": document})
    for kind, observation in (
            ("contact", {"simulation_time_s": 1.1, "simulation_step": 11}),
            ("pose", {"simulation_time_s": 1.1, "simulation_step": 11}),
            ("retract", {"simulation_time_s": 1.1, "simulation_step": 11, "table_contact": True}),
            ("support", {"simulation_time_s": 1.1, "simulation_step": 11, "supported": True}),
            ("contact", {**document, "other_contact_geoms": [1, 2]})):
        other = EpisodeAuditWriter(tmp_path / f"bad-{kind}-{len(observation)}", scope(), identity(),
                                   {"inputs_sha256": "a" * 64})
        with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
            other.append_source("physics", {"kind": kind, "sim_time_s": 1.1, "release_epoch": 1,
                                            "observation": observation})


def test_readback_requires_exact_types_and_correlated_clocks(tmp_path):
    """Sequences are integers, clocks agree, and an event identity is the episode's (T3-F3)."""

    # a boolean or float sequence is refused at admission, so the writer cannot record one
    writer = EpisodeAuditWriter(tmp_path / "seq", scope(), identity(), {"inputs_sha256": "a" * 64})
    with pytest.raises(ValueError, match="AUDIT_ROW_INVALID"):
        writer.bind_row(0, 1.0, "a", "b", True)
    # a physics envelope clock must be finite and equal the observation clock
    with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
        writer.append_source("physics", {"kind": "pose", "sim_time_s": 1.1, "release_epoch": 1,
                                         "observation": {"simulation_time_s": 1.2,
                                                         "simulation_step": 1,
                                                         "cup_position_world_m": [0.0, 0.0, 0.0]}})
    # an event identity must be the episode's, and its release epoch cannot go backwards
    with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
        writer.append_source("events", {"kind": "phase_start",
                                        "identity": {**identity(), "reset_epoch": 9},
                                        "sim_time_s": 1.0, "monotonic_ns": 1,
                                        "payload": {"phase": "SEARCH"}})
    writer.append_source("events", {"kind": "phase_start",
                                    "identity": {**identity(), "release_epoch": 2},
                                    "sim_time_s": 1.0, "monotonic_ns": 1,
                                    "payload": {"phase": "SEARCH"}})
    with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
        writer.append_source("events", {"kind": "phase_start", "identity": identity(),
                                        "sim_time_s": 1.0, "monotonic_ns": 2,
                                        "payload": {"phase": "SEARCH"}})
    # readback repeats the clock correlation on a re-signed stream of its own
    case = tmp_path / "sealed"
    case.mkdir(parents=True, exist_ok=True)
    sealed, window = complete_audit(case)
    path = sealed.seal(window)
    row = json.loads((path.parent / "physics.jsonl").read_text().splitlines()[0])
    row["sim_time_s"] = None
    payload = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
    _resign(sealed, path, "physics.jsonl", payload)
    with pytest.raises(ValueError, match="AUDIT_PHYSICS_INVALID"):
        verify_audit_manifest(path)


def _window(**overrides):
    window = {"source_schedule": {"head": [1.0, 1.1], "wrist": [1.0, 1.1]},
              "streams_required": ["head", "wrist"], "cadence_s": 0.1, "permitted_gaps_s": [],
              "collection_start_s": 1.0, "collection_end_s": 1.2, "first_command_s": 1.0,
              "physics_end_s": 1.1, "label_cutoff_s": 1.0, "outcome": "complete"}
    window.update(overrides)
    return window


def test_the_ratified_window_schema_is_enforced_for_a_formal_audit(tmp_path):
    """Proposal B: the window's fields and per-outcome ordering are ratified and enforced."""

    # the writer carries full source coverage first, so each attempt below fails on the window alone
    writer = _formal_writer(tmp_path / "window")
    writer.append_source("references", {"reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE",
                                        "positions": [0.1] * 6, "accepted": True})
    writer.append_source("physics", {"kind": "pose", "sim_time_s": 1.1, "release_epoch": 1,
                                     "observation": {"simulation_time_s": 1.1, "simulation_step": 1,
                                                     "cup_position_world_m": [0.0, 0.0, 0.0]}})
    for kind, payload in (("phase_complete", {"phase": "SEARCH", "physics_step": 1}),
                          ("release", {"release_epoch": 1, "supported": True,
                                       "no_fingertip_contact": True})):
        writer.append_source("events", {"kind": kind, "identity": identity(), "sim_time_s": 1.1,
                                        "monotonic_ns": 1, "payload": payload})
    with pytest.raises(ValueError, match="AUDIT_WINDOW_INVALID"):
        writer.seal(_window() | {"extra": 1})
    with pytest.raises(ValueError, match="AUDIT_WINDOW_INVALID"):
        writer.seal(_window(label_cutoff_s=1.5))                    # outside the physics window
    with pytest.raises(ValueError, match="AUDIT_WINDOW_INVALID"):
        writer.seal(_window(first_command_s=1.5))                   # after the physics end
    with pytest.raises(ValueError, match="AUDIT_WINDOW_INVALID"):
        writer.seal(_window(outcome="no_command"))                  # must null both instants
    with pytest.raises(ValueError, match="AUDIT_WINDOW_INVALID"):
        writer.seal(_window(outcome="interrupted_diagnostic"))      # never formal evidence
    # the writer creates its own root, so only its parent must exist
    diagnostic = EpisodeAuditWriter(tmp_path / "legacy", scope(), identity(),
                                    {"inputs_sha256": "a" * 64})
    assert diagnostic.seal({"start_s": 1.0}).is_file()               # the diagnostic path is unchanged


def _formal_writer(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    return EpisodeAuditWriter(tmp_path / "formal", dict(scope(), mode="formal"),
                               {**identity(), "lease": _lease()}, {"inputs_sha256": "a" * 64})


def test_a_formal_audit_may_not_seal_without_source_coverage(tmp_path):
    """A formal seal must carry physics, references, events and a release (T3-F5)."""

    empty = _formal_writer(tmp_path / "empty")
    with pytest.raises(ValueError, match="AUDIT_FORMAL_COVERAGE_INCOMPLETE"):
        empty.seal(_window())

    partial = _formal_writer(tmp_path / "partial")
    partial.append_source("physics", {"kind": "pose", "sim_time_s": 1.1, "release_epoch": 1,
                                      "observation": {"simulation_time_s": 1.1,
                                                      "simulation_step": 1,
                                                      "cup_position_world_m": [0.0, 0.0, 0.0]}})
    with pytest.raises(ValueError, match="AUDIT_FORMAL_COVERAGE_INCOMPLETE"):
        partial.seal(_window())

    complete = _formal_writer(tmp_path / "complete")
    complete.append_source("references", {"reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE",
                                          "positions": [0.1] * 6, "accepted": True})
    complete.append_source("physics", {"kind": "pose", "sim_time_s": 1.1, "release_epoch": 1,
                                       "observation": {"simulation_time_s": 1.1,
                                                       "simulation_step": 1,
                                                       "cup_position_world_m": [0.0, 0.0, 0.0]}})
    for kind, payload in (("phase_complete", {"phase": "SEARCH", "physics_step": 1}),
                          ("release", {"release_epoch": 1, "supported": True,
                                       "no_fingertip_contact": True})):
        complete.append_source("events", {"kind": kind, "identity": identity(),
                                          "sim_time_s": 1.1, "monotonic_ns": 1, "payload": payload})
    assert complete.seal(_window()).is_file()
    # the diagnostic mode keeps its previous behaviour, which is what the plan separates
    diagnostic = EpisodeAuditWriter(tmp_path / "diagnostic", scope(), identity(),
                                    {"inputs_sha256": "a" * 64})
    assert diagnostic.seal({"start_s": 1.0}).is_file()


def _ratified_reference():
    return {"frames": {
        "arm": {"joint_names": ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex",
                                "wrist_roll"],
                "positions": [0.1, 0.2, 0.3, 0.4, 0.5], "velocities": [0.0] * 5,
                "sim_stamp_ns": 1100000000, "received_monotonic_ns": 900000, "observer_sequence": 7},
        "gripper": {"joint_names": ["gripper"], "positions": [0.6], "velocities": [0.0],
                    "sim_stamp_ns": 1100000000, "received_monotonic_ns": 900100,
                    "observer_sequence": 7}},
        "evaluation": {"requested_sim_time_s": 1.1, "basis": "interval", "goal_id": "goal-1",
                       "accepted_sim_s": 1.0, "revoked_sim_s": None},
        "projected_positions": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
        "projection_map": [["arm", 0], ["arm", 1], ["arm", 2], ["arm", 3], ["arm", 4],
                           ["gripper", 0]]}


def test_the_ratified_reference_frames_are_accepted_and_validated(tmp_path):
    """Proposal A: per-kind frames with their clocks, an evaluation and a checked map."""

    base = {"reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE",
            "positions": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6], "accepted": True}
    writer = EpisodeAuditWriter(tmp_path / "ok", scope(), identity(), {"inputs_sha256": "a" * 64})
    writer.append_source("references", {**base, **_ratified_reference()})

    def broken(**changes):
        document = json.loads(json.dumps(_ratified_reference()))
        for key, value in changes.items():
            if value is None:
                document.pop(key, None)
            else:
                document[key] = value
        return document

    frames = _ratified_reference()["frames"]
    cases = [broken(evaluation={"requested_sim_time_s": 1.1, "basis": "published", "goal_id": "g",
                                "accepted_sim_s": 1.0, "revoked_sim_s": None}),
             broken(evaluation={**_ratified_reference()["evaluation"], "goal_id": None,
                                "accepted_sim_s": None}),
             broken(projection_map=[["arm", 0], ["arm", 1], ["arm", 2], ["arm", 3], ["arm", 4],
                                    ["gripper", 3]]),
             broken(projected_positions=[0.9, 0.2, 0.3, 0.4, 0.5, 0.6]),
             broken(frames={**frames, "arm": {**frames["arm"], "velocities": [0.0] * 4}}),
             broken(frames={"arm": frames["arm"]}),
             broken(frames={**frames, "base": frames["gripper"]}),
             # the provenance checks the fifth verdict named as independent of A.1
             broken(evaluation={**_ratified_reference()["evaluation"],
                                "requested_sim_time_s": 1.3}),
             broken(evaluation={**_ratified_reference()["evaluation"], "accepted_sim_s": 1.2}),
             broken(evaluation={**_ratified_reference()["evaluation"], "revoked_sim_s": 1.0}),
             broken(projection_map=[["arm", 0]] * 6),
             broken(frames={**frames, "arm": {**frames["arm"], "joint_names": ["a"] * 4,
                                              "positions": [0.1] * 4, "velocities": [0.0] * 4}}),
             broken(frames={**frames, "gripper": {**frames["gripper"],
                                                  "joint_names": ["g", "h"],
                                                  "positions": [0.6, 0.7],
                                                  "velocities": [0.0, 0.0]}})]
    for index, document in enumerate(cases):
        other = EpisodeAuditWriter(tmp_path / f"bad-{index}", scope(), identity(),
                                   {"inputs_sha256": "a" * 64})
        with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
            other.append_source("references", {**base, **document})
    mixed = EpisodeAuditWriter(tmp_path / "mixed", scope(), identity(), {"inputs_sha256": "a" * 64})
    with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
        mixed.append_source("references", {**base, **_ratified_reference(),
                                           "joint_names": ["a"], "sim_stamp_ns": 1,
                                           "received_monotonic_ns": 1, "velocities": [0.0]})


def test_the_planning_scene_and_feedback_records_are_validated(tmp_path):
    """Proposal C's two records: accepted and typified, so a gate can be derived from them."""

    scene = {"scene_revision": 3, "attached_objects": ["plastic_cup"],
             "world_object_ids": ["plastic_cup", "table"], "is_diff": False, "sim_time_s": 1.1,
             "source": "search_boundary"}
    feedback = [{"controller": "arm", "joint_names": ["shoulder_pan", "shoulder_lift"],
                 "commanded_positions": [0.1, 0.2], "measured_positions": [0.1, 0.2],
                 "measured_velocities": [0.0, 0.0], "status_sequence": 4, "sim_time_s": 1.1},
                {"controller": "gripper", "joint_names": ["gripper"],
                 "commanded_positions": [0.6], "measured_positions": [0.6],
                 "measured_velocities": [0.0], "status_sequence": 4, "sim_time_s": 1.1}]
    pose = {"simulation_time_s": 1.1, "simulation_step": 11, "cup_position_world_m": [0.0, 0.0, 0.0]}
    writer = EpisodeAuditWriter(tmp_path / "ok", scope(), identity(), {"inputs_sha256": "a" * 64})
    writer.append_source("physics", {"kind": "pose", "sim_time_s": 1.1, "release_epoch": 1,
                                     "observation": {**pose, "planning_scene_observation": scene,
                                                     "controller_feedback": feedback}})
    for index, broken in enumerate(({**scene, "sim_time_s": 1.2},
                                    {**scene, "attached_objects": ["b", "a"]},
                                    {**scene, "scene_revision": -1},
                                    {**scene, "extra": 1},
                                    {**scene, "source": ""})):
        other = EpisodeAuditWriter(tmp_path / f"bad-scene-{index}", scope(), identity(),
                                   {"inputs_sha256": "a" * 64})
        with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
            other.append_source("physics", {"kind": "pose", "sim_time_s": 1.1, "release_epoch": 1,
                                            "observation": {**pose,
                                                            "planning_scene_observation": broken}})
    for index, broken_feedback in enumerate(([{**feedback[0], "sim_time_s": 1.2}],
                                             [{**feedback[0], "measured_positions": [0.1]}],
                                             [{**feedback[0], "controller": "neck"}],
                                             [{**feedback[0], "status_sequence": 0}],
                                             [{**feedback[0], "joint_names": []}])):
        other = EpisodeAuditWriter(tmp_path / f"bad-fb-{index}", scope(), identity(),
                                   {"inputs_sha256": "a" * 64})
        with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
            other.append_source("physics", {"kind": "pose", "sim_time_s": 1.1, "release_epoch": 1,
                                            "observation": {**pose,
                                                            "controller_feedback": broken_feedback}})


def test_the_per_kind_history_must_keep_its_ordering_across_the_stream(tmp_path):
    """A second packed reference may not rewind its kind's stamps, receipts or sequence (T3-F1)."""

    base = {"reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE",
            "positions": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6], "accepted": True}
    writer = EpisodeAuditWriter(tmp_path / "ordered", scope(), identity(), {"inputs_sha256": "a" * 64})
    writer.append_source("references", {**base, **_ratified_reference()})
    later = json.loads(json.dumps(_ratified_reference()))
    later["evaluation"]["requested_sim_time_s"] = 1.2
    later["frames"]["arm"]["sim_stamp_ns"] = 1200000000
    later["frames"]["arm"]["received_monotonic_ns"] = 901000
    later["frames"]["arm"]["observer_sequence"] = 8
    later["frames"]["gripper"] = {**later["frames"]["gripper"], "sim_stamp_ns": 1200000000,
                                  "received_monotonic_ns": 901100, "observer_sequence": 8}
    writer.append_source("references", {**base, "reference_time_s": 1.2, **later})
    rewind = json.loads(json.dumps(later))
    rewind["evaluation"]["requested_sim_time_s"] = 1.3
    rewind["frames"]["arm"]["sim_stamp_ns"] = 1100000000
    with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
        writer.append_source("references", {**base, "reference_time_s": 1.3, **rewind})
