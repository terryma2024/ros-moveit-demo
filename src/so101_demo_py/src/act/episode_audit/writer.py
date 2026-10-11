"""The episode audit writer."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

from so101_demo.act.episode_audit.checks import (
    _ACQUISITION_FIELDS,
    _EVENT_FIELDS,
    _EVENT_PAYLOADS,
    _GRID_S,
    _MAX_SKEW_S,
    _MAX_SOURCE_AGE_S,
    _PHYSICS_FIELDS,
    _PHYSICS_KINDS,
    _REFERENCE_FIELDS,
    _REFERENCE_FRAME_FIELDS,
    _REFERENCE_RAW_FIELDS,
    _ROW_FIELDS,
    _TOLERANCE_S,
    _WINDOW_FIELDS,
    MANIFEST_KIND,
    SOURCE_KINDS,
    _canonical,
    _capture_window_matches_observed,
    _closed,
    _event_identity_ok,
    _Files,
    _finite,
    _formal_coverage_ok,
    _hex64,
    _identity_ok,
    _integer,
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


class EpisodeAuditWriter:
    """The single writer of one episode's raw audit."""

    def __init__(self, root: Path, scope: dict, identity: dict, inputs: dict) -> None:
        self.root = Path(root)
        if (not self.root.is_absolute() or ".." in self.root.parts
                or not isinstance(scope, dict) or not isinstance(identity, dict)
                or not isinstance(inputs, dict)):
            raise ValueError("AUDIT_ROOT_INVALID")
        digest = inputs.get("inputs_sha256") if isinstance(inputs, dict) else None
        if not _scope_ok(scope):
            # a scope the frozen contract does not recognise may not open an episode audit
            raise ValueError("AUDIT_SCOPE_INVALID")
        if not _identity_ok(identity, formal=scope["mode"] == "formal"):
            # a formal episode must name the lease it ran under, using the registered contract
            raise ValueError("AUDIT_IDENTITY_INVALID")
        if not inputs:
            raise ValueError("AUDIT_SCOPE_INVALID")
        if not _hex64(digest):
            # the audit always names the frozen inputs it belongs to
            raise ValueError("AUDIT_INPUTS_INVALID")
        from so101_demo.act.diagnostic_episode_inputs import audit_execution_model_identity
        self._execution_model = audit_execution_model_identity(inputs)
        self._execution_chunks = (inputs["execution_snapshot"]["physics_chunks"]
                                  if self._execution_model is not None else None)
        # the episode's directory is owned by the recorder, which creates it and refuses to reuse one; the audit
        # writer roots at that same directory so its manifest sits where verification resolves it, and accepts an
        # existing root for exactly that reason - it still refuses anything that is not a directory
        if self.root.exists():
            if not self.root.is_dir():
                raise ValueError("AUDIT_ROOT_INVALID")
        else:
            self.root.mkdir(parents=False, exist_ok=False)
        audit = self.root / "audit"
        audit.mkdir()
        self.files = _Files(audit / "source.json", audit / "inputs.json", audit / "episode.json",
                            audit / "acquisitions.jsonl", audit / "row-bindings.jsonl",
                            audit / "events.jsonl", audit / "references.jsonl",
                            audit / "physics.jsonl")
        self.scope = dict(scope)
        self.identity = dict(identity)
        self.inputs = dict(inputs)
        self._write_new(self.files.source, _canonical(self.scope))
        self._write_new(self.files.inputs, _canonical(self.inputs))
        self._write_new(self.files.episode, _canonical(self.identity))
        self._streams = {name: self._open(path) for name, path in self.files.streams().items()}
        self._sequence = {name: 0 for name in self._streams}
        self._task_sequence = 0
        self._acquisitions: dict = {}
        self._references: dict = {}
        self._bound: set = set()
        self._last_row_time_s: float | None = None
        self._bound_references: set = set()
        self._revoked_targets: set = set()
        self._event_release_epoch: int | None = None
        self._world_source_previous = None
        self._world_source_hashes = {}
        self._teacher_event_last_seq = 0
        self._collection_boundaries = set()
        self._native_first_dispatch_clock = None
        self._native_normal_end_clock = None
        self._event_kinds: set = set()
        # F3: which release epochs a `release` event actually named, so seal() can require that every step the
        # stream takes is named by one rather than only that some release happened somewhere
        self._release_named: dict = {}
        self._reference_history: dict = {}
        self._row_indexes: set = set()
        self._row_times: list = []
        self._release_epoch: int | None = None
        self._observed_epochs: dict = {}
        self._sealed: Path | None = None
        self._raw_physics_previous = None
        self._scene_records = {}

    # -- the only writer ---------------------------------------------------

    def append_acquisition(self, frame) -> None:
        self._require_open()
        record = {field: getattr(frame, field) for field in _ACQUISITION_FIELDS - {"task_sequence"}}
        record["shape"] = list(record["shape"])
        record["task_sequence"] = self._next_task()
        _closed(record, _ACQUISITION_FIELDS, "AUDIT_SCHEMA_INVALID")
        if record["acquisition_id"] in self._acquisitions:
            raise ValueError("AUDIT_ACQUISITION_DUPLICATE")
        self._acquisitions[record["acquisition_id"]] = record
        self._append("acquisitions", record)

    def bind_row(self, row_index, sim_time_s, head_id, wrist_id, reference_sequence) -> None:
        self._require_open()
        record = {"row_index": _integer(row_index, "AUDIT_ROW_INVALID"),
                  "sim_time_s": _finite(sim_time_s, "AUDIT_ROW_INVALID", nonnegative=True),
                  "head_acquisition_id": head_id, "wrist_acquisition_id": wrist_id,
                  "reference_sequence": _integer(reference_sequence, "AUDIT_ROW_INVALID")}
        _closed(record, _ROW_FIELDS, "AUDIT_ROW_INVALID")
        if head_id == wrist_id:
            # the same acquisition in both slots is never a real stereo pair
            raise ValueError("AUDIT_BINDING_INVALID")
        for value, camera in ((head_id, "head"), (wrist_id, "wrist")):
            if not isinstance(value, str) or not value or value not in self._acquisitions:
                # a row may not be bound to an acquisition the audit never saw
                raise ValueError("AUDIT_BINDING_UNKNOWN")
            frame = self._acquisitions[value]
            if frame["camera"] != camera:
                # the head slot takes a head acquisition and the wrist slot a wrist one
                raise ValueError("AUDIT_BINDING_INVALID")
            if (frame["session_id"] != self.identity.get("session_id")
                    or frame["reset_epoch"] != self.identity.get("reset_epoch")):
                # a frame from another session or reset epoch does not belong to this episode
                raise ValueError("AUDIT_BINDING_INVALID")
            if value in self._bound:
                # one acquisition fills one row, the same rule the capture enforces
                raise ValueError("AUDIT_BINDING_REUSED")
        if record["row_index"] in self._row_indexes:
            raise ValueError("AUDIT_ROW_INVALID")
        if record["row_index"] != len(self._row_indexes):
            # rows are a contiguous schedule: no gaps, no reordering
            raise ValueError("AUDIT_ROW_ORDER_INVALID")
        stamps = []
        for value in (head_id, wrist_id):
            frame = self._acquisitions[value]
            age = record["sim_time_s"] - frame["stamp_s"]
            if age < -_TOLERANCE_S or age > _MAX_SOURCE_AGE_S + _TOLERANCE_S:
                # a frame from the future, or one too old, is not causal for this instant
                raise ValueError("AUDIT_BINDING_CAUSALITY_INVALID")
            stamps.append(frame["stamp_s"])
        if abs(stamps[0] - stamps[1]) > _MAX_SKEW_S + _TOLERANCE_S:
            raise ValueError("AUDIT_BINDING_CAUSALITY_INVALID")
        if self._last_row_time_s is not None and abs(
                record["sim_time_s"] - (self._last_row_time_s + _GRID_S)) > _TOLERANCE_S:
            # rows are a contiguous 10 Hz schedule, not merely consecutive integers
            raise ValueError("AUDIT_ROW_SCHEDULE_INVALID")
        entry = self._references.get(record["reference_sequence"])
        target = _reference_target_s(record["sim_time_s"])
        if (entry is None or entry["reference_time_s"] != target
                or entry["accepted"] is not True
                or entry["reference_time_s"] in self._revoked_targets):
            # the binding must name a reference this episode accepted for exactly that instant and
            # whose acceptance still stands
            raise ValueError("AUDIT_BINDING_REFERENCE_INVALID")
        self._row_indexes.add(record["row_index"])
        self._row_times.append(record["sim_time_s"])
        self._last_row_time_s = record["sim_time_s"]
        self._bound.update((head_id, wrist_id))
        self._bound_references.add(record["reference_sequence"])
        self._append("row-bindings", record)

    def append_recorder_queue(self, document, *, sim_time_s):
        import time

        from so101_demo.act.lossless_recorder import verify_queue_evidence
        verify_queue_evidence(document)
        identity = dict(self.identity)
        if self._event_release_epoch is not None:
            identity["release_epoch"] = self._event_release_epoch
        self.append_source("events", {"kind": "recorder_queue", "identity": identity,
            "sim_time_s": sim_time_s, "monotonic_ns": time.monotonic_ns(),
            "payload": {"queue_evidence": document}})

    def append_raw_physics(self, document):
        """Retain the complete native chunk under this episode's actual identity."""
        import time
        identity = dict(self.identity)
        if self._event_release_epoch is not None:
            identity["release_epoch"] = self._event_release_epoch
        self.append_source("events", {"kind": "physics_chunk", "identity": identity,
            "sim_time_s": document["chunk"]["last_simulation_time_s"],
            "monotonic_ns": time.monotonic_ns(), "payload": {"raw_chunk": document}})

    def append_scene_association(self, document):
        """Retain actual source alignment records; native references are mandatory at sealed readback."""
        import time
        identity = dict(self.identity)
        if self._event_release_epoch is not None:
            identity["release_epoch"] = self._event_release_epoch
        self.append_source("events", {"kind": "source_alignment", "identity": identity,
            "sim_time_s": document["source"]["physics"]["simulation_time_s"],
            "monotonic_ns": time.monotonic_ns(), "payload": {"association": document}})

    def append_world_source(self, document):
        """Retain a published original candidate, without applying endpoint quality selection."""
        import time
        identity = dict(self.identity)
        if self._event_release_epoch is not None:
            identity["release_epoch"] = self._event_release_epoch
        self.append_source("events", {"kind": "world_source", "identity": identity,
            "sim_time_s": document["physics"]["simulation_time_s"], "monotonic_ns": time.monotonic_ns(),
            "payload": {"world_source": document}})

    def append_teacher_event(self, document):
        """Retain one accepted `SO101_TEACHER_EVENT` event verbatim, in strictly increasing `seq` order.

        Scene operations take sequence numbers without being retained here, so a skip is allowed; the sealed summary
        (`append_teacher_event_summary`) is what proves that nothing else was lost.
        """
        import time
        identity = dict(self.identity)
        if self._event_release_epoch is not None:
            identity['release_epoch'] = self._event_release_epoch
        self.append_source('events', dict(kind='teacher_event', identity=identity,
            sim_time_s=document['sim_time_ns'] / 1e9, monotonic_ns=time.monotonic_ns(),
            payload={'teacher_event': document}))

    def append_teacher_event_summary(self, summary):
        """Seal the Recorder's own count of every V2 event it accepted (retained or not)."""
        import time
        identity = dict(self.identity)
        if self._event_release_epoch is not None:
            identity['release_epoch'] = self._event_release_epoch
        self.append_source('events', dict(kind='teacher_event_summary', identity=identity, sim_time_s=None,
            monotonic_ns=time.monotonic_ns(), payload={'event_summary': summary}))

    def append_reference_continuity(self, report):
        """Seal the per-controller `controller_state` gap report (the label stream's continuity)."""
        import time
        identity = dict(self.identity)
        if self._event_release_epoch is not None:
            identity['release_epoch'] = self._event_release_epoch
        self.append_source('events', dict(kind='controller_reference', identity=identity, sim_time_s=None,
            monotonic_ns=time.monotonic_ns(), payload={'reference_continuity': report}))

    def append_collection_boundary(self, stage, value):
        """Preserve one original boundary without observing a replacement source clock."""
        import time

        from so101_demo.act.collection_boundaries import boundary_clock, validate_collection_boundary
        document = dict(kind='ACT_COLLECTION_BOUNDARY', schema_version=2, stage=stage, value=value)
        validate_collection_boundary(document, identity=self.identity)
        identity = dict(self.identity)
        if self._event_release_epoch is not None:
            identity['release_epoch'] = self._event_release_epoch
        self.append_source('events', dict(kind='collection_boundary', identity=identity,
            sim_time_s=boundary_clock(document)['sim_time_ns'] / 1e9, monotonic_ns=time.monotonic_ns(),
            payload={'collection_boundary': document}))

    def append_source(self, kind, record) -> None:
        self._require_open()
        if kind not in SOURCE_KINDS:
            raise ValueError("AUDIT_SOURCE_KIND_INVALID")
        if kind == "events":
            item = _closed(record, _EVENT_FIELDS - {"sequence", "task_sequence"}, "AUDIT_SCHEMA_INVALID").copy()
            if (not isinstance(item["kind"], str) or item["kind"] not in _EVENT_PAYLOADS
                    or not isinstance(item["identity"], dict) or not item["identity"]
                    or not _event_identity_ok(item["identity"], self.identity,
                                              release_epoch=self._event_release_epoch)
                    or not isinstance(item["payload"], dict)
                    or set(item["payload"]) != _EVENT_PAYLOADS[item["kind"]]):
                # an unknown kind, an empty identity or a payload outside its kind's schema is refused
                raise ValueError("AUDIT_SCHEMA_INVALID")
            _integer(item["monotonic_ns"], "AUDIT_SCHEMA_INVALID", minimum=1)
            # a sim time is recorded only when the source actually supplies one, never invented
            if item["sim_time_s"] is not None:
                _finite(item["sim_time_s"], "AUDIT_SCHEMA_INVALID", nonnegative=True)
            if item["kind"] in ("run_complete", "run_aborted"):
                _integer(item["payload"]["physics_step"], "AUDIT_SCHEMA_INVALID")
            if not _payload_typed(item["payload"]):
                # every value must be the type its key declares, per kind
                raise ValueError("AUDIT_SCHEMA_INVALID")
            if item['kind']=='teacher_event':
                from so101_demo.act.teacher_collection import first_command_clock, validate_teacher_event
                document=item['payload']['teacher_event']
                validate_teacher_event(document, identity=self.identity)
                if (document['seq'] <= self._teacher_event_last_seq
                        or item['monotonic_ns'] < document['monotonic_ns']
                        or item['sim_time_s'] != document['sim_time_ns'] / 1e9):
                    raise ValueError('AUDIT_TEACHER_EVENT_INVALID')
                self._teacher_event_last_seq = document['seq']
                clock = first_command_clock(document)
                if clock is not None and self._native_first_dispatch_clock is None:
                    self._native_first_dispatch_clock = dict(clock)
            if item['kind'] == 'collection_boundary':
                from so101_demo.act.collection_boundaries import claim_collection_boundary
                boundary=claim_collection_boundary(item, identity=self.identity, seen=self._collection_boundaries,
                    world_hashes=self._world_source_hashes)
                if boundary['stage']=='normal_stop':
                    self._native_normal_end_clock=dict(boundary['value']['source_clock'])
            if item["kind"] == "physics_chunk":
                from so101_demo.act.raw_physics_chunks import verify_raw_chunk
                raw = item["payload"]["raw_chunk"]
                verify_raw_chunk(raw, previous=self._raw_physics_previous,
                    session_id=self.identity["session_id"], reset_epoch=self.identity["reset_epoch"],
                    **({} if self._execution_model is None else {
                        "nq": self._execution_model["nq"], "nv": self._execution_model["nv"],
                        "max_samples": self._execution_chunks["max_samples"],
                        "max_contacts": self._execution_chunks["max_contacts"]}))
                if (item["monotonic_ns"] < raw["received_monotonic_ns"]
                        or item["sim_time_s"] != raw["chunk"]["last_simulation_time_s"]):
                    raise ValueError("AUDIT_PHYSICS_RAW_EVENT_INVALID")
                self._raw_physics_previous = json.loads(_canonical(raw))
            if item["kind"] == "source_alignment":
                association = item["payload"]["association"]
                source = association["source"]["physics"]
                if (source["simulation_session_id"] != self.identity["session_id"]
                        or source["reset_epoch"] != self.identity["reset_epoch"]
                        or source["simulation_time_s"] != item["sim_time_s"]
                        or association["query"]["record"]["response_ros_clock"]["end_monotonic_ns"]
                        > item["monotonic_ns"]):
                    raise ValueError("AUDIT_SOURCE_ALIGNMENT_INVALID")
                from so101_demo.act.scene_association import claim_scene_records
                claim_scene_records(association, self._scene_records)
            if item["kind"] == "world_source":
                from so101_demo.act.native_endpoints import validate_world_source
                source = item["payload"]["world_source"]
                validate_world_source(source, identity=self.identity, previous=self._world_source_previous)
                if (source["physics"]["simulation_time_s"] != item["sim_time_s"]
                        or item["monotonic_ns"] < max(source["received_monotonic_ns"], source["scene_received_monotonic_ns"])):
                    raise ValueError("AUDIT_WORLD_SOURCE_INVALID")
                self._world_source_previous = json.loads(_canonical(source))
                from so101_demo.act.collection_boundaries import world_source_digest
                self._world_source_hashes[source['physics']['publisher_sequence']]=world_source_digest(source)
            if item["kind"] == "phase_complete":
                _integer(item["payload"]["physics_step"], "AUDIT_SCHEMA_INVALID")
                if not isinstance(item["payload"]["phase"], str) or not item["payload"]["phase"]:
                    raise ValueError("AUDIT_SCHEMA_INVALID")
            if item["kind"] == "release":
                if item["payload"]["release_epoch"] != item["identity"]["release_epoch"]:
                    raise ValueError("AUDIT_SCHEMA_INVALID")
            self._event_release_epoch = item["identity"]["release_epoch"]
            self._event_kinds.add(item["kind"])
            _epoch = item["identity"].get("release_epoch")
            if type(_epoch) is int:
                self._release_named[_epoch] = (self._release_named.get(_epoch, False)
                                               or item["kind"] == "release")
            item["sequence"] = self._next("events")
            item["task_sequence"] = self._task_sequence
        elif kind == "references":
            keys = set(record) if isinstance(record, dict) else set()
            packed = _REFERENCE_FRAME_FIELDS & keys
            raw_present = _REFERENCE_RAW_FIELDS & keys
            if packed and packed != _REFERENCE_FRAME_FIELDS:
                raise ValueError("AUDIT_SCHEMA_INVALID")
            if packed and raw_present:
                # the ratified per-frame shape and the legacy flat group are alternatives
                raise ValueError("AUDIT_SCHEMA_INVALID")
            if raw_present and raw_present != _REFERENCE_RAW_FIELDS:
                raise ValueError("AUDIT_SCHEMA_INVALID")
            if packed:
                _reference_frames_ok(record, history=self._reference_history)
            elif raw_present:
                _reference_raw_ok(record, "AUDIT_SCHEMA_INVALID")
            item = _closed(record, (_REFERENCE_FIELDS | packed | raw_present) - {"sequence", "task_sequence"},
                           "AUDIT_SCHEMA_INVALID").copy()
            _finite(item["reference_time_s"], "AUDIT_SCHEMA_INVALID", nonnegative=True)
            positions = item["positions"]
            if (not isinstance(positions, (list, tuple)) or len(positions) != 6
                    or any(isinstance(value, bool) or not isinstance(value, (int, float))
                           or not math.isfinite(value) for value in positions)):
                raise ValueError("AUDIT_SCHEMA_INVALID")
            item["positions"] = [float(value) for value in positions]
            if item["source"] != "CONTROLLER_REFERENCE" or type(item["accepted"]) is not bool:
                raise ValueError("AUDIT_SCHEMA_INVALID")
            item["sequence"] = self._next("references")
            item["task_sequence"] = self._task_sequence
            # the recorded row keeps the declared closed fields; the revocation state lives beside it
            self._references[item["sequence"]] = item
            if item["accepted"] is not True:
                # a revocation voids the acceptance for that target instant, so no row may keep
                # binding an acceptance the controller has since withdrawn
                self._revoked_targets.add(item["reference_time_s"])
        else:
            item = _closed(record, _PHYSICS_FIELDS - {"sequence", "task_sequence"}, "AUDIT_SCHEMA_INVALID").copy()
            if item["kind"] not in _PHYSICS_KINDS or not isinstance(item["observation"], dict):
                raise ValueError("AUDIT_SCHEMA_INVALID")
            _finite(item["sim_time_s"], "AUDIT_SCHEMA_INVALID", nonnegative=True)
            epoch = _integer(item["release_epoch"], "AUDIT_SCHEMA_INVALID")
            item["sim_time_s"] = _finite(item["sim_time_s"], "AUDIT_SCHEMA_INVALID",
                                         nonnegative=True)
            if not _physics_observation_typed(item["observation"], kind=item["kind"]):
                raise ValueError("AUDIT_SCHEMA_INVALID")
            if item["observation"]["simulation_time_s"] != item["sim_time_s"]:
                raise ValueError("AUDIT_SCHEMA_INVALID")
            self._apply_epoch(epoch, item["kind"], item["observation"])
            item["sequence"] = self._next("physics")
            item["task_sequence"] = self._task_sequence
        self._append(kind, item)

    def observed_collection_window(self, facts: dict, *, cadence_s: float) -> dict:
        """Build the collection claim from original acquired frames and capture clocks."""
        self._require_open()
        schedule = {camera: sorted(row["stamp_s"] for row in self._acquisitions.values()
                                  if row["camera"] == camera)
                    for camera in ("head", "wrist")}
        if any(not stamps or stamps != sorted(set(stamps)) for stamps in schedule.values()):
            raise ValueError("AUDIT_WINDOW_INVALID")
        stamps = [stamp for values in schedule.values() for stamp in values]
        first, cutoff = facts["first_command_s"], facts["label_cutoff_s"]
        window = {"source_schedule": schedule, "streams_required": ["head", "wrist"],
            "cadence_s": cadence_s, "permitted_gaps_s": [],
            "collection_start_s": min(stamps), "collection_end_s": max(stamps),
            "first_command_s": first, "physics_end_s": facts["physics_end_s"],
            "label_cutoff_s": cutoff,
            "outcome": "complete" if cutoff is not None else
                       "no_command" if first is None else "no_label"}
        if not _window_ok(window, mode=self.scope["mode"]):
            raise ValueError("AUDIT_WINDOW_INVALID")
        # A collection claim cannot permit a camera hole or omit an acquired instant.
        if any(later - earlier > cadence_s * 1.5 + _TOLERANCE_S
               for values in schedule.values() for earlier, later in zip(values, values[1:])):
            raise ValueError("AUDIT_WINDOW_INVALID")
        return window

    def seal(self, window: dict) -> Path:
        self._require_open()
        if self.scope.get("mode") == "formal":
            # F5: one shared predicate governs both sides - the writer's coverage is the same requirement the
            # readback re-checks (which also names the accepted reference an inline check used to miss) - and
            # the F3 tie stays beside it
            # the episode's declared initial epoch is not a transition, so the writer's own
            # tie exempts it exactly as the readback's does - the two must agree, or a stream the readback
            # accepts cannot be sealed at all
            _initial = self.identity.get("release_epoch")
            if type(_initial) is not int:
                _initial = 0
            if (not _formal_coverage_ok(self.root / "audit")
                    # F3: every release step the stream takes must be named by a release event, not just one
                    or any(epoch > _initial and not named for epoch, named in self._release_named.items())):
                raise ValueError("AUDIT_FORMAL_COVERAGE_INCOMPLETE")
        for sequence in sorted(self._bound_references):
            entry = self._references.get(sequence)
            if (entry is None or entry["accepted"] is not True
                    or entry["reference_time_s"] in self._revoked_targets):
                # an already-bound row whose acceptance was revoked before sealing cannot be sealed
                raise ValueError("AUDIT_BINDING_REVOKED")
        if not isinstance(window, dict) or not window:
            raise ValueError("AUDIT_WINDOW_INVALID")
        from so101_demo.act.teacher_collection import validate_first_command_window, validate_normal_end_window
        validate_first_command_window(self._native_first_dispatch_clock,window)
        validate_normal_end_window(self._native_normal_end_clock,window)
        if (self.scope.get("mode") == "formal" or set(window) == _WINDOW_FIELDS) and not _window_ok(
                window, mode=self.scope.get("mode")):
            # a formal audit states the ratified window; a diagnostic audit may record a legacy one
            raise ValueError("AUDIT_WINDOW_INVALID")
        if set(window) == _WINDOW_FIELDS and not _capture_window_matches_observed(
                window, self._row_times, self._acquisitions, mode=self.scope["mode"]):
            raise ValueError("AUDIT_WINDOW_INVALID")
        if self.scope.get("mode") == "formal" and not self._window_matches_rows(window):
            # and it must describe the rows and acquisitions this audit actually holds
            raise ValueError("AUDIT_WINDOW_INVALID")
        for name, stream in self._streams.items():
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
        files = {}
        for target in (*self.files.streams().values(), self.files.source, self.files.inputs,
                       self.files.episode):
            files[target.name] = {"path": target.name, "size": target.stat().st_size,
                                  "sha256": _sha256(target)}
        manifest = {"kind": MANIFEST_KIND, "schema_version": 2,
                    # the digest of the scope payload this audit was collected under
                    "scope_sha256": _sha256(self.files.source),
                    "identity": dict(self.identity), "window": dict(window), "files": files}
        target = self.root / "audit" / "audit-manifest.json"
        self._write_new(target, _canonical(manifest))
        self._fsync_dir(target.parent)
        self._sealed = target
        return target

    # -- helpers -----------------------------------------------------------

    def _window_matches_rows(self, window: dict) -> bool:
        # the readback passed the physics history and the seal did not, so the endpoint
        # comparison was inert exactly where it mattered; both boundaries now supply the same arguments
        return _window_matches_observed(
            window, self._row_times, self._acquisitions,
            [row["sim_time_s"] for row in _records(self.root / "audit" / "physics.jsonl",
                                                   _PHYSICS_FIELDS, "AUDIT_PHYSICS_INVALID")])

    def _apply_epoch(self, epoch: int, kind: str, observation: dict) -> None:
        if self._release_epoch is None:
            self._release_epoch = epoch
        elif epoch < self._release_epoch:
            raise ValueError("AUDIT_RELEASE_EPOCH_STALE")
        elif epoch > self._release_epoch:
            self._release_epoch = epoch
        if kind == "support":
            supported = observation.get("supported")
            if type(supported) is not bool:
                raise ValueError("AUDIT_SCHEMA_INVALID")
            self._observed_epochs[epoch] = supported

    def _next_task(self) -> int:
        """The one counter every record draws from, so any two records can be ordered from the records alone (source alignment)."""

        self._task_sequence += 1
        return self._task_sequence

    def _next(self, kind: str) -> int:
        self._sequence[kind] += 1
        self._next_task()
        return self._sequence[kind]

    def _require_open(self) -> None:
        if self._sealed is not None:
            raise ValueError("AUDIT_ALREADY_SEALED")

    def _append(self, name: str, record: dict) -> None:
        stream = self._streams[name]
        stream.write(_canonical(record) + b"\n")
        stream.flush()

    def _open(self, path: Path):
        return path.open("xb")

    def _write_new(self, path: Path, payload: bytes) -> None:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())

    def _fsync_dir(self, directory: Path) -> None:
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
