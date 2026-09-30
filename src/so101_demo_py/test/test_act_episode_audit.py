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
    return {"session_id": "s", "attempt_id": "attempt-1", "reset_epoch": 1, "scene_id": "default",
            "seed": 0, "mode": "preselected_target_diagnostic"}


def complete_audit(tmp_path):
    """Every closed field and file this task writes, with real files and real hashes."""

    writer = EpisodeAuditWriter(tmp_path / "episode", {"mode": "preselected_target_diagnostic",
                                                       "scene_id": "default", "seed": 0},
                                identity(), {"inputs_sha256": "a" * 64})
    minter = AcquisitionMinter()
    frames = []
    for camera in ("head", "wrist"):
        for stamp in (1.0, 1.1):
            frame = minter.mint(camera, session_id="s", reset_epoch=1, stamp_s=stamp,
                                received_monotonic_ns=int(stamp * 1e9) + 1, pixels=ZERO)
            writer.append_acquisition(frame)
            frames.append(frame)
    writer.append_source("references", {"reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE",
                                        "positions": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
                                        "accepted": True})
    writer.append_source("events", {"kind": "first_command", "sim_time_s": 1.0, "physics_step": 0,
                                    "detail": "dispatch"})
    writer.append_source("physics", {"kind": "support", "sim_time_s": 1.1, "release_epoch": 1,
                                     "observation": {"supported": True, "contacts": 2}})
    writer.append_source("physics", {"kind": "retract", "sim_time_s": 1.2, "release_epoch": 1,
                                     "observation": {"distance_m": 0.05}})
    writer.bind_row(0, 1.0, frames[0].acquisition_id, frames[1].acquisition_id, 1)
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
    writer = EpisodeAuditWriter(tmp_path / "episode", {"mode": "diagnostic"}, identity(),
                                {"inputs_sha256": "a" * 64})
    minter = AcquisitionMinter()
    frame = minter.mint("head", session_id="s", reset_epoch=1, stamp_s=1.0,
                        received_monotonic_ns=1, pixels=ZERO)
    writer.append_acquisition(frame)
    with pytest.raises(ValueError, match="AUDIT_BINDING_UNKNOWN"):
        writer.bind_row(0, 1.0, frame.acquisition_id, "s/1/wrist/1", 1)


def test_one_acquisition_cannot_fill_two_rows(tmp_path):
    writer = EpisodeAuditWriter(tmp_path / "episode", {"mode": "diagnostic"}, identity(),
                                {"inputs_sha256": "a" * 64})
    minter = AcquisitionMinter()
    head = minter.mint("head", session_id="s", reset_epoch=1, stamp_s=1.0,
                       received_monotonic_ns=1, pixels=ZERO)
    wrist = minter.mint("wrist", session_id="s", reset_epoch=1, stamp_s=1.0,
                        received_monotonic_ns=1, pixels=ZERO)
    writer.append_acquisition(head)
    writer.append_acquisition(wrist)
    writer.bind_row(0, 1.0, head.acquisition_id, wrist.acquisition_id, 1)
    with pytest.raises(ValueError, match="AUDIT_BINDING_REUSED"):
        writer.bind_row(1, 1.1, head.acquisition_id, wrist.acquisition_id, 1)


def test_an_unknown_schema_field_is_refused(tmp_path):
    writer, _ = complete_audit(tmp_path)
    with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
        writer.append_source("events", {"kind": "phase", "sim_time_s": 1.0, "physics_step": 0,
                                        "detail": "x", "success": True})
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
                                     "observation": {"supported": True}})
    with pytest.raises(ValueError, match="AUDIT_RELEASE_EPOCH_STALE"):
        writer.append_source("physics", {"kind": "support", "sim_time_s": 1.4, "release_epoch": 1,
                                         "observation": {"supported": True}})


def test_a_stale_epoch_in_a_sealed_audit_is_detected_on_readback(tmp_path):
    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    physics = writer.files.physics
    lines = physics.read_bytes().splitlines()
    lines.insert(1, json.dumps({"sequence": 9, "kind": "support", "sim_time_s": 1.15,
                                "release_epoch": 0, "observation": {"supported": True}},
                               sort_keys=True, separators=(",", ":")).encode())
    physics.write_bytes(b"\n".join(lines) + b"\n")
    with pytest.raises(ValueError, match="AUDIT_HASH_MISMATCH"):
        verify_audit_manifest(path)


def test_a_missing_inputs_digest_is_refused(tmp_path):
    with pytest.raises(ValueError, match="AUDIT_SCOPE_INVALID"):
        EpisodeAuditWriter(tmp_path / "episode", {"mode": "diagnostic"}, identity(), {})
    with pytest.raises(ValueError, match="AUDIT_INPUTS_INVALID"):
        EpisodeAuditWriter(tmp_path / "episode", {"mode": "diagnostic"}, identity(),
                           {"candidate": "x"})
    with pytest.raises(ValueError, match="AUDIT_INPUTS_INVALID"):
        EpisodeAuditWriter(tmp_path / "episode", {"mode": "diagnostic"}, identity(),
                           {"inputs_sha256": "not-a-digest"})


def test_every_source_kind_is_closed_and_the_writer_is_exclusive(tmp_path):
    assert SOURCE_KINDS == ("events", "references", "physics")
    writer, window = complete_audit(tmp_path)
    writer.seal(window)
    with pytest.raises(ValueError, match="AUDIT_ALREADY_SEALED"):
        writer.append_acquisition(None)
    with pytest.raises(ValueError, match="AUDIT_ALREADY_SEALED"):
        writer.append_source("events", {"kind": "phase", "sim_time_s": 2.0, "physics_step": 5,
                                        "detail": "late"})
    with pytest.raises(FileExistsError):
        EpisodeAuditWriter(tmp_path / "episode", {"mode": "diagnostic"}, identity(),
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
