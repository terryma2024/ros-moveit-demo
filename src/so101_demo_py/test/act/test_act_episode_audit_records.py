"""Camera rows, binding and the readback of a re-signed audit."""

from __future__ import annotations

import hashlib
import json

from act_episode_audit_support import (
    ZERO,
    _ratified_reference,
    _resign,
    complete_audit,
    identity,
    scope,
)
import pytest

from so101_demo.act.acquisition import AcquisitionMinter
from so101_demo.act.episode_audit.checks import (
    MANIFEST_KIND,
    SOURCE_KINDS,
)
from so101_demo.act.episode_audit.verification import verify_audit_manifest
from so101_demo.act.episode_audit.writer import EpisodeAuditWriter


def test_an_episode_that_starts_after_the_first_camera_frames_seals_and_verifies(tmp_path):
    """The window starts after the worker's last pause, so frames the camera adapter numbered before the capture started
    (sequence 1 ...) are not in the episode: the retained sequence of a camera begins wherever the capture began and must then be
    contiguous. (Pilot bag 031b82c6: the first audited head frame was sequence 2 and the seal failed AUDIT_ACQUISITION_INVALID.)"""

    writer = EpisodeAuditWriter(tmp_path / "episode", scope(), identity(), {"inputs_sha256": "a" * 64})
    minter = AcquisitionMinter()
    frames = {}
    for camera in ("head", "wrist"):
        minter.mint(camera, session_id="s", reset_epoch=1, stamp_s=0.9, received_monotonic_ns=900_000_001, pixels=ZERO)  # not audited
        for stamp in (1.0, 1.1):
            frame = minter.mint(camera, session_id="s", reset_epoch=1, stamp_s=stamp,
                                received_monotonic_ns=int(stamp * 1e9) + 1, pixels=ZERO)
            writer.append_acquisition(frame)
            frames[(camera, stamp)] = frame
    assert frames[("head", 1.0)].sequence == 2
    writer.append_source("references", {"reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE",
                                        "positions": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6], "accepted": True})
    writer.bind_row(0, 1.0, frames[("head", 1.0)].acquisition_id, frames[("wrist", 1.0)].acquisition_id, 1)
    path = writer.seal({"start_s": 1.0, "end_s": 1.1, "label_cutoff_s": 1.0})
    assert verify_audit_manifest(path)["window"]["start_s"] == 1.0


def test_a_gap_inside_the_retained_camera_sequence_is_still_refused(tmp_path):
    writer = EpisodeAuditWriter(tmp_path / "episode", scope(), identity(), {"inputs_sha256": "a" * 64})
    minter = AcquisitionMinter()
    frames = {}
    for camera in ("head", "wrist"):
        for stamp in (1.0, 1.1, 1.2):
            frame = minter.mint(camera, session_id="s", reset_epoch=1, stamp_s=stamp,
                                received_monotonic_ns=int(stamp * 1e9) + 1, pixels=ZERO)
            if not (camera == "head" and stamp == 1.1):          # the audit never saw the middle head frame
                writer.append_acquisition(frame)
            frames[(camera, stamp)] = frame
    writer.append_source("references", {"reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE",
                                        "positions": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6], "accepted": True})
    writer.bind_row(0, 1.0, frames[("head", 1.0)].acquisition_id, frames[("wrist", 1.0)].acquisition_id, 1)
    path = writer.seal({"start_s": 1.0, "end_s": 1.2, "label_cutoff_s": 1.0})
    with pytest.raises(ValueError, match="AUDIT_ACQUISITION_INVALID"):
        verify_audit_manifest(path)


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


def test_a_camera_stamp_one_nanosecond_off_the_microsecond_grid_still_binds_its_exact_reference(tmp_path):
    """Pilot bag 031b82c6: the head/wrist frames carried 4.803999999 s (sec=4, nanosec=803999999). The capture's reference target is
    the nanosecond sum (4.903999999); the binding check rounded the target to microseconds (4.904) and refused the capture's own row
    (AUDIT_BINDING_REFERENCE_INVALID). The rule is unchanged: the reference must be for exactly stamp + 0.1 s, in nanoseconds."""

    from so101_demo.act.acquisition import AcquisitionMinter

    writer = EpisodeAuditWriter(tmp_path / "episode", scope(), {"session_id": "s", "attempt_id": "a", "reset_epoch": 1,
                                                                 "release_epoch": 1}, {"inputs_sha256": "a" * 64})
    minter, ids = AcquisitionMinter(), {}
    for camera in ("head", "wrist"):
        frame = minter.mint(camera, session_id="s", reset_epoch=1, stamp_s=4.803999999, received_monotonic_ns=1, pixels=ZERO)
        writer.append_acquisition(frame)
        ids[camera] = frame.acquisition_id
    target = (round(4.803999999 * 1e9) + round(0.1 * 1e9)) / 1e9
    writer.append_source("references", {"reference_time_s": target, "source": "CONTROLLER_REFERENCE",
                                        "positions": [0.1] * 6, "accepted": True})
    writer.bind_row(0, 4.803999999, ids["head"], ids["wrist"], 1)
    off = (round(4.803999999 * 1e9) + round(0.1 * 1e9) + 1) / 1e9      # one more nanosecond is still a different instant
    writer.append_source("references", {"reference_time_s": off, "source": "CONTROLLER_REFERENCE",
                                        "positions": [0.1] * 6, "accepted": True})
    other, other_ids = _staging(tmp_path / "second")
    other.append_source("references", {"reference_time_s": 1.1 + 1e-9, "source": "CONTROLLER_REFERENCE",
                                       "positions": [0.1] * 6, "accepted": True})
    with pytest.raises(ValueError, match="AUDIT_BINDING_REFERENCE_INVALID"):
        other.bind_row(0, 1.0, other_ids["head"], other_ids["wrist"], 2)


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
    # a re-signed row that genuinely carries both raw reference groups is refused on readback (T3-F3);
    # one legacy key beside the packed group is what makes it a mixture rather than a valid alternative
    ("references.jsonl", lambda row: row.update(_ratified_reference()) or row.update({"joint_names": ["a"]}),
     "AUDIT_REFERENCE_INVALID"),
    # checks the readback already implements, each now with a re-signed counterexample
    ("acquisitions.jsonl", lambda row: row.update({"camera": "neck"}), "AUDIT_ACQUISITION_INVALID"),
    ("acquisitions.jsonl", lambda row: row.update({"acquisition_id": "s/1/head/9"}),
     "AUDIT_ACQUISITION_INVALID"),
    ("acquisitions.jsonl", lambda row: row.update({"shape": [480, 640]}), "AUDIT_ACQUISITION_INVALID"),
    ("events.jsonl", lambda row: row.update({"identity": {**row["identity"], "reset_epoch": 9}}),
     "AUDIT_EVENT_INVALID"),
    ("physics.jsonl", lambda row: row.update({"kind": "hold"}), "AUDIT_PHYSICS_INVALID"),
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
