"""Stream and manifest verification of a sealed episode audit."""

from __future__ import annotations

import json
import math
from pathlib import Path

from so101_demo.act.acquisition import CAMERAS, canonical_acquisition_id
from so101_demo.act.episode_audit.checks import (
    _ACQUISITION_FIELDS,
    _EVENT_FIELDS,
    _EVENT_PAYLOADS,
    _GRID_S,
    _MANIFEST_FIELDS,
    _MAX_SKEW_S,
    _MAX_SOURCE_AGE_S,
    _METADATA_FILES,
    _PHYSICS_FIELDS,
    _PHYSICS_KINDS,
    _REFERENCE_FIELDS,
    _REFERENCE_FRAME_FIELDS,
    _REFERENCE_RAW_FIELDS,
    _ROW_FIELDS,
    _STREAM_NAMES,
    _TOLERANCE_S,
    _WINDOW_FIELDS,
    MANIFEST_KIND,
    _audit_manifest_key,
    _capture_window_matches_observed,
    _event_identity_ok,
    _formal_coverage_ok,
    _hex64,
    _identity_ok,
    _payload_typed,
    _physics_observation_typed,
    _records,
    _reference_frames_ok,
    _reference_raw_ok,
    _reference_target_s,
    _scope_ok,
    _sha256,
    _window_matches_observed,
    _window_ok,
)
from so101_demo.act.qc_session import load_model, session_memo


@session_memo(_audit_manifest_key)
def verify_audit_manifest(path: Path) -> dict:
    """Re-read a sealed audit and recompute it.

    The inventory is **required**, not trusted: every expected stream and metadata file must be listed
    with a safe relative path, its size and its digest, so a manifest that omits a stream cannot leave
    that stream unchecked. Each stream is then re-validated semantically with the same closed schemas
    and relationships the writer enforced, because a checksum only proves the bytes did not change.
    """

    path = Path(path)
    try:
        manifest = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("AUDIT_MANIFEST_INVALID") from error
    if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_FIELDS:
        raise ValueError("AUDIT_MANIFEST_INVALID")
    if manifest["kind"] != MANIFEST_KIND or manifest["schema_version"] != 2:
        raise ValueError("AUDIT_MANIFEST_INVALID")
    audit = path.parent
    expected = set(_METADATA_FILES) | set(_STREAM_NAMES)
    files = manifest["files"]
    if not isinstance(files, dict) or set(files) != expected:
        # an inventory that omits a stream, or invents one, is refused rather than partially checked
        raise ValueError("AUDIT_MANIFEST_INVENTORY_INVALID")
    for name, entry in files.items():
        target = audit / name
        if (not isinstance(entry, dict) or set(entry) != {"path", "size", "sha256"}
                or entry["path"] != name or not target.is_file() or target.is_symlink()):
            raise ValueError("AUDIT_MANIFEST_INVENTORY_INVALID")
        payload = target.read_bytes()
        if len(payload) != entry["size"] or _sha256(target) != entry["sha256"]:
            # a changed raw reference, a rewritten stream or a deleted file lands here
            raise ValueError("AUDIT_HASH_MISMATCH")
    formal_window = json.loads((audit / "source.json").read_bytes()).get("mode") == "formal"
    if (not isinstance(manifest["identity"], dict) or not isinstance(manifest["window"], dict)
            or (formal_window and not _window_ok(manifest["window"], mode="formal"))
            or manifest["scope_sha256"] != _sha256(audit / "source.json")):
        # the manifest names the scope it was collected under, and the payload must agree with it
        raise ValueError("AUDIT_MANIFEST_INVALID")
    _verify_streams(audit, manifest["identity"])
    from so101_demo.act.teacher_collection import (
        first_command_clock,
        validate_first_command_window,
        validate_normal_end_window,
    )
    first_commands=[clock for clock in (first_command_clock(row['payload']['teacher_event'])
                    for row in _records(audit/'events.jsonl',_EVENT_FIELDS,'AUDIT_EVENT_INVALID')
                    if row['kind']=='teacher_event') if clock is not None]
    validate_first_command_window(None if not first_commands else first_commands[0], manifest['window'])
    normal_ends=[row['payload']['collection_boundary']['value']['source_clock']
        for row in _records(audit/'events.jsonl',_EVENT_FIELDS,'AUDIT_EVENT_INVALID')
        if row['kind']=='collection_boundary' and row['payload']['collection_boundary']['stage']=='normal_stop']
    validate_normal_end_window(None if not normal_ends else normal_ends[0],manifest['window'])
    if set(manifest["window"]) == _WINDOW_FIELDS:
        bound = _records(audit / "row-bindings.jsonl", _ROW_FIELDS, "AUDIT_ROW_INVALID")
        acquired = _records(audit / "acquisitions.jsonl", _ACQUISITION_FIELDS,
                            "AUDIT_ACQUISITION_INVALID")
        if not _capture_window_matches_observed(manifest["window"],
                [row["sim_time_s"] for row in bound],
                {row["acquisition_id"]: row for row in acquired},
                mode=json.loads((audit / "source.json").read_bytes())["mode"]):
            raise ValueError("AUDIT_WINDOW_INVALID")
    if formal_window:
        # the seal's window-to-observed predicate is repeated here, from the rows this readback holds,
        # so an invented in-range instant cannot pass by satisfying `_window_ok` and the coverage gate alone
        _bound_rows = _records(audit / "row-bindings.jsonl", _ROW_FIELDS, "AUDIT_ROW_INVALID")
        _acquisition_rows = _records(audit / "acquisitions.jsonl", _ACQUISITION_FIELDS,
                                     "AUDIT_ACQUISITION_INVALID")
        if not _window_matches_observed(manifest["window"],
                                        [row["sim_time_s"] for row in _bound_rows],
                                        {row["acquisition_id"]: row for row in _acquisition_rows},
                                        [row["sim_time_s"] for row in _records(
                                            audit / "physics.jsonl", _PHYSICS_FIELDS,
                                            "AUDIT_PHYSICS_INVALID")]):
            raise ValueError("AUDIT_WINDOW_INVALID")
    if formal_window and not _formal_coverage_ok(audit):
        # the seal gate's coverage requirement holds when the audit is read back, not only when sealed
        raise ValueError("AUDIT_FORMAL_COVERAGE_INCOMPLETE")
    return manifest


def _verify_streams(audit: Path, identity: dict) -> None:
    """Re-apply admission semantics to every stream, not just its checksum."""

    acquisitions = {}
    per_camera: dict = {}
    for row in _records(audit / "acquisitions.jsonl", _ACQUISITION_FIELDS,
                        "AUDIT_ACQUISITION_INVALID"):
        if (row["camera"] not in CAMERAS or list(row["shape"]) != [480, 640, 3]
                or row["session_id"] != identity.get("session_id")
                or row["reset_epoch"] != identity.get("reset_epoch")
                or row["dtype"] != "uint8" or not _hex64(row["pixel_sha256"])
                or type(row["sequence"]) is not int or row["sequence"] < 1
                or type(row["reset_epoch"]) is not int or row["reset_epoch"] < 0
                or type(row["received_monotonic_ns"]) is not int or row["received_monotonic_ns"] < 1
                or not isinstance(row["stamp_s"], (int, float)) or isinstance(row["stamp_s"], bool)
                or not math.isfinite(row["stamp_s"]) or row["stamp_s"] < 0
                or not math.isfinite(row["received_monotonic_ns"])):
            raise ValueError("AUDIT_ACQUISITION_INVALID")
        if row["acquisition_id"] != canonical_acquisition_id(
                row["session_id"], row["reset_epoch"], row["camera"], row["sequence"]):
            raise ValueError("AUDIT_ACQUISITION_INVALID")
        key = (row["camera"], row["session_id"], row["reset_epoch"])
        # The retained sequence of a camera begins wherever the capture began (frames the adapter numbered before the capture
        # started, or before the episode window, are not in the episode) and is contiguous from there: a gap is still refused.
        previous_sequence, previous_stamp = per_camera.get(key, (row["sequence"] - 1, -1.0))
        if (row["acquisition_id"] in acquisitions or row["sequence"] != previous_sequence + 1
                or row["stamp_s"] <= previous_stamp):
            # a new sequence must also be a new source instant: ordering alone is not monotonic time
            raise ValueError("AUDIT_ACQUISITION_INVALID")
        per_camera[key] = (row["sequence"], row["stamp_s"])
        acquisitions[row["acquisition_id"]] = row
    revoked = set()
    references = {}
    sequence = 0
    frame_history: dict = {}
    for row in _records(audit / "references.jsonl",
                        _REFERENCE_FIELDS | _REFERENCE_RAW_FIELDS | _REFERENCE_FRAME_FIELDS,
                        "AUDIT_REFERENCE_INVALID",
                        optional_any=(_REFERENCE_RAW_FIELDS, _REFERENCE_FRAME_FIELDS)):
        if (type(row["sequence"]) is not int or row["sequence"] != sequence + 1
                or row["source"] != "CONTROLLER_REFERENCE"
                or type(row["accepted"]) is not bool
                or not isinstance(row["positions"], list) or len(row["positions"]) != 6
                or not isinstance(row["reference_time_s"], (int, float))
                or isinstance(row["reference_time_s"], bool)
                or not math.isfinite(row["reference_time_s"]) or row["reference_time_s"] < 0
                or any(isinstance(value, bool) or not isinstance(value, (int, float))
                       or not math.isfinite(value) for value in row["positions"])):
            raise ValueError("AUDIT_REFERENCE_INVALID")
        sequence = row["sequence"]
        packed_keys = _REFERENCE_FRAME_FIELDS & set(row)
        raw_keys = _REFERENCE_RAW_FIELDS & set(row)
        if packed_keys and raw_keys:
            # the two groups are alternatives at admission, so readback refuses them together too
            raise ValueError("AUDIT_REFERENCE_INVALID")
        if packed_keys:
            _reference_frames_ok(row, history=frame_history)
        elif raw_keys:
            _reference_raw_ok(row, "AUDIT_REFERENCE_INVALID")
        references[row["sequence"]] = row
        if row["accepted"] is not True:
            revoked.add(row["reference_time_s"])
    bound: set = set()
    indexes: set = set()
    last_time: float | None = None
    for row in _records(audit / "row-bindings.jsonl", _ROW_FIELDS, "AUDIT_ROW_INVALID"):
        if (type(row["row_index"]) is not int or row["row_index"] < 0
                or row["row_index"] in indexes or row["row_index"] != len(indexes)
                or row["head_acquisition_id"] == row["wrist_acquisition_id"]
                or not isinstance(row["sim_time_s"], (int, float))
                or isinstance(row["sim_time_s"], bool)
                or not math.isfinite(row["sim_time_s"]) or row["sim_time_s"] < 0):
            raise ValueError("AUDIT_ROW_INVALID")
        indexes.add(row["row_index"])
        stamps = []
        for value, camera in ((row["head_acquisition_id"], "head"),
                              (row["wrist_acquisition_id"], "wrist")):
            frame = acquisitions.get(value)
            if frame is None or value in bound or frame["camera"] != camera:
                raise ValueError("AUDIT_BINDING_UNKNOWN")
            if (frame["session_id"] != identity.get("session_id")
                    or frame["reset_epoch"] != identity.get("reset_epoch")):
                raise ValueError("AUDIT_BINDING_INVALID")
            age = row["sim_time_s"] - frame["stamp_s"]
            if age < -_TOLERANCE_S or age > _MAX_SOURCE_AGE_S + _TOLERANCE_S:
                raise ValueError("AUDIT_BINDING_CAUSALITY_INVALID")
            stamps.append(frame["stamp_s"])
            bound.add(value)
        if abs(stamps[0] - stamps[1]) > _MAX_SKEW_S + _TOLERANCE_S:
            raise ValueError("AUDIT_BINDING_CAUSALITY_INVALID")
        if last_time is not None and abs(row["sim_time_s"] - (last_time + _GRID_S)) > _TOLERANCE_S:
            raise ValueError("AUDIT_ROW_SCHEDULE_INVALID")
        last_time = row["sim_time_s"]
        target = _reference_target_s(row["sim_time_s"])
        if type(row["reference_sequence"]) is not int:
            # residual case: the writer admits an exact integer for this binding, and Python's key equality
            # would let `true` or `1.0` resolve integer key 1 on readback, so the type is required on both sides
            raise ValueError("AUDIT_ROW_INVALID")
        named = references.get(row["reference_sequence"])
        if named is None or named["reference_time_s"] != target or named["accepted"] is not True:
            # the binding must resolve to a reference this episode accepted for exactly that instant
            raise ValueError("AUDIT_BINDING_REFERENCE_INVALID")
        if target in revoked:
            raise ValueError("AUDIT_BINDING_REVOKED")
    sequence = 0
    event_epoch: int | None = None
    queues = []
    raw_physics_previous = None
    inputs = json.loads((audit / "inputs.json").read_bytes())
    from so101_demo.act.diagnostic_episode_inputs import audit_execution_model_identity
    execution_model = audit_execution_model_identity(inputs)
    execution_chunks = inputs["execution_snapshot"]["physics_chunks"] if execution_model is not None else None
    associations = []
    world_sources = []
    world_hashes = {}
    teacher_event_last_seq = 0
    collection_boundaries = set()
    native_steps = {}
    for row in _records(audit / "events.jsonl", _EVENT_FIELDS, "AUDIT_EVENT_INVALID"):
        payload = row["payload"]
        if (type(row["sequence"]) is not int or row["sequence"] != sequence + 1
                or row["kind"] not in _EVENT_PAYLOADS
                or not isinstance(row["identity"], dict) or not row["identity"]
                or type(row["monotonic_ns"]) is not int or row["monotonic_ns"] < 1
                or not isinstance(payload, dict)
                or set(payload) != _EVENT_PAYLOADS[row["kind"]]):
            raise ValueError("AUDIT_EVENT_INVALID")
        if row["sim_time_s"] is not None and (
                isinstance(row["sim_time_s"], bool) or not isinstance(row["sim_time_s"], (int, float))
                or not math.isfinite(row["sim_time_s"]) or row["sim_time_s"] < 0):
            raise ValueError("AUDIT_EVENT_INVALID")
        if row["kind"] == "release" and (
                payload.get("release_epoch") != (row["identity"].get("release_epoch"))):
            # F3: the writer correlates a release payload's epoch with its identity, so the readback does
            # too; a re-signed event may not claim one epoch in its payload and another in its identity
            raise ValueError("AUDIT_EVENT_INVALID")
        if not _event_identity_ok(row["identity"], identity, release_epoch=event_epoch):
            raise ValueError("AUDIT_EVENT_INVALID")
        event_epoch = row["identity"]["release_epoch"]
        if row["kind"] in ("phase_complete", "run_complete", "run_aborted"):
            if type(payload["physics_step"]) is not int or payload["physics_step"] < 0:
                raise ValueError("AUDIT_EVENT_INVALID")
        if row["kind"] == "phase_complete" and (not isinstance(payload["phase"], str)
                                                or not payload["phase"]):
            raise ValueError("AUDIT_EVENT_INVALID")
        if not _payload_typed(payload):
            raise ValueError("AUDIT_EVENT_INVALID")
        if row['kind']=='teacher_event':
            from so101_demo.act.teacher_collection import validate_teacher_event
            document = payload['teacher_event']
            validate_teacher_event(document, identity=identity)
            if (document['seq'] <= teacher_event_last_seq or row['monotonic_ns'] < document['monotonic_ns']
                    or row['sim_time_s'] != document['sim_time_ns'] / 1e9):
                raise ValueError('AUDIT_EVENT_INVALID')
            teacher_event_last_seq = document['seq']
        if row['kind'] == 'collection_boundary':
            from so101_demo.act.collection_boundaries import claim_collection_boundary
            claim_collection_boundary(row, identity=identity, seen=collection_boundaries,world_hashes=world_hashes)
        if row["kind"] == "recorder_queue":
            queues.append(payload["queue_evidence"])
        if row["kind"] == "physics_chunk":
            from so101_demo.act.raw_physics_chunks import verify_raw_chunk
            raw = payload["raw_chunk"]
            verify_raw_chunk(raw, previous=raw_physics_previous, previous_verified=True,
                session_id=identity["session_id"], reset_epoch=identity["reset_epoch"],
                **({} if execution_model is None else {"nq": execution_model["nq"], "nv": execution_model["nv"],
                    "max_samples": execution_chunks["max_samples"], "max_contacts": execution_chunks["max_contacts"]}))
            if (row["monotonic_ns"] < raw["received_monotonic_ns"]
                    or row["sim_time_s"] != raw["chunk"]["last_simulation_time_s"]):
                raise ValueError("AUDIT_PHYSICS_RAW_EVENT_INVALID")
            raw_physics_previous = raw
            for sample in raw["chunk"]["samples"]:
                native_steps[sample["physics_step"]] = sample
        if row["kind"] == "source_alignment":
            association = payload["association"]
            if (association["source"]["physics"]["simulation_time_s"] != row["sim_time_s"]
                    or association["query"]["record"]["response_ros_clock"]["end_monotonic_ns"]
                    > row["monotonic_ns"]):
                raise ValueError("AUDIT_SOURCE_ALIGNMENT_INVALID")
            associations.append(association)
        if row["kind"] == "world_source":
            source = payload["world_source"]
            if (source["physics"]["simulation_time_s"] != row["sim_time_s"]
                    or row["monotonic_ns"] < max(source["received_monotonic_ns"], source["scene_received_monotonic_ns"])):
                raise ValueError("AUDIT_WORLD_SOURCE_INVALID")
            world_sources.append(source)
            from so101_demo.act.collection_boundaries import world_source_digest
            world_hashes[source['physics']['publisher_sequence']]=world_source_digest(source)
        sequence = row["sequence"]
    if associations:
        from so101_demo.act.scene_association import claim_scene_records, verify_scene_association
        scene_records = {}
        for association in associations:
            claim_scene_records(association, scene_records)
            step = association["source"]["physics"]["simulation_step"]
            verify_scene_association(association, inputs=inputs, identity=identity,
                raw_steps=[] if step not in native_steps else [native_steps[step]])
    if world_sources:
        from so101_demo.act.execution_snapshot import verify_execution_snapshot
        from so101_demo.act.native_endpoints import verify_world_source
        if execution_model is None:
            raise ValueError("WORLD_SOURCE_FROZEN_INPUTS_REQUIRED")
        models = {}
        previous = None
        for source in world_sources:
            root = source["execution_root"]
            if root not in models:
                snapshot = verify_execution_snapshot(root, expected_sha256=inputs["execution_snapshot"]["sha256"])
                models[root] = load_model(Path(root) / snapshot["scene_path"], root=root)
            step = source["physics"]["simulation_step"]
            verify_world_source(source, identity=identity, model=models[root], model_identity=execution_model,
                raw_steps=[] if step not in native_steps else [native_steps[step]], previous=previous)
            previous = source
    inputs = json.loads((audit / "inputs.json").read_bytes())
    if "execution_snapshot" in inputs:
        bound_rows = _records(audit / "row-bindings.jsonl", _ROW_FIELDS, "AUDIT_ROW_INVALID")
        if (len(queues) != 1 or queues[0]["accepted_samples"] != len(bound_rows)
                or queues[0]["written_samples"] != len(bound_rows)):
            raise ValueError("AUDIT_RECORDER_QUEUE_INCOMPLETE")
        if raw_physics_previous is None:
            raise ValueError("AUDIT_PHYSICS_RAW_INCOMPLETE")
    # F3: on a formal audit every release step the stream takes must be named by a release event - the
    # writer's own tie restated here, because a re-signed stream never passes through the writer.
    # A diagnostic audit is out of scope, exactly as it is for that gate.
    _source = audit / "source.json"
    _formal_mode = False
    if _source.is_file():
        try:
            _formal_mode = json.loads(_source.read_bytes()).get("mode") == "formal"
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            _formal_mode = False
    if _formal_mode and (audit / "events.jsonl").is_file():
        _named: dict = {}
        for _row in _records(audit / "events.jsonl", _EVENT_FIELDS, "AUDIT_EVENT_INVALID"):
            _step = _row["identity"].get("release_epoch")
            if type(_step) is int:
                _named[_step] = _named.get(_step, False) or _row["kind"] == "release"
        # the episode's declared initial epoch is not a transition and is not required to
        # be named by a release event; every later epoch still is, which is what a re-signed stream must not skip
        try:
            _initial = json.loads((audit / "audit-manifest.json").read_bytes())["identity"]["release_epoch"]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
            _initial = 0
        if type(_initial) is not int:
            _initial = 0
        if any(step > _initial and not seen for step, seen in _named.items()):
            raise ValueError("AUDIT_EVENT_INVALID")

    epoch: int | None = None
    sequence = 0
    for row in _records(audit / "physics.jsonl", _PHYSICS_FIELDS, "AUDIT_PHYSICS_INVALID"):
        if (type(row["sequence"]) is not int or row["sequence"] != sequence + 1
                or row["kind"] not in _PHYSICS_KINDS
                or isinstance(row["sim_time_s"], bool)
                or not isinstance(row["sim_time_s"], (int, float))
                or not math.isfinite(row["sim_time_s"]) or row["sim_time_s"] < 0
                or row["observation"].get("simulation_time_s") != row["sim_time_s"]
                or type(row["release_epoch"]) is not int or row["release_epoch"] < 0
                ):
            raise ValueError("AUDIT_PHYSICS_INVALID")
        sequence = row["sequence"]
        if epoch is None or row["release_epoch"] > epoch:
            epoch = row["release_epoch"]
        elif row["release_epoch"] < epoch:
            raise ValueError("AUDIT_RELEASE_EPOCH_STALE")
        if not _physics_observation_typed(row["observation"], kind=row["kind"]):
            # readback applies the same source contract the writer admitted
            raise ValueError("AUDIT_PHYSICS_INVALID")
    declared = json.loads((audit / "episode.json").read_bytes())
    scope = json.loads((audit / "source.json").read_bytes())
    inputs = json.loads((audit / "inputs.json").read_bytes())
    if (declared != identity or not _scope_ok(scope) or not _identity_ok(declared)
            or not isinstance(inputs, dict) or not _hex64(inputs.get("inputs_sha256"))
            or inputs["inputs_sha256"] != scope["inputs_sha256"]
            or not _identity_ok(declared, formal=scope["mode"] == "formal")):
        # the manifest identity must be the identity the episode actually recorded, and the scope and
        # inputs payloads must be the closed documents they claim to be
        raise ValueError("AUDIT_METADATA_INVALID")
