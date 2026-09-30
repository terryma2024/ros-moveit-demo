"""The common raw audit for one episode.

One writer owns the episode's raw evidence: the acquisitions the cameras actually produced, the
controller references the run actually accepted or revoked, the physics observations the run actually
made, the run events, and the binding of each training row to the acquisitions and reference sequence
it consumed. The recorder writes its rows through the same boundary, so a row cannot exist without its
raw binding, and nothing may rewrite the audit after it is sealed.

Every append is a new line; there is no update path. Each source kind has a closed schema, so an
unknown field is refused rather than silently retained, and `seal()` writes the manifest of the raw
audit last, fsyncing every file and the directory before returning. `verify_audit_manifest()` re-reads
the files and recomputes their digests, so a rewritten reference or a missing binding is detected
instead of trusted.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path

MANIFEST_KIND = "ACT_EPISODE_AUDIT_MANIFEST"
SOURCE_KINDS = ("events", "references", "physics")
_ACQUISITION_FIELDS = frozenset({"camera", "session_id", "reset_epoch", "sequence", "acquisition_id",
                                 "stamp_s", "received_monotonic_ns", "pixel_sha256"})
_ROW_FIELDS = frozenset({"row_index", "sim_time_s", "head_id", "wrist_id", "reference_sequence"})
_REFERENCE_FIELDS = frozenset({"sequence", "reference_time_s", "source", "positions", "accepted"})
_EVENT_FIELDS = frozenset({"sequence", "kind", "sim_time_s", "physics_step", "detail"})
_PHYSICS_FIELDS = frozenset({"sequence", "kind", "sim_time_s", "release_epoch", "observation"})
_PHYSICS_KINDS = ("support", "contact", "pose", "retract")
_MANIFEST_FIELDS = frozenset({"kind", "schema_version", "window", "files", "inputs_sha256"})


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _closed(record, fields: frozenset, code: str) -> dict:
    if not isinstance(record, dict) or set(record) != fields:
        raise ValueError(code)
    return record


def _finite(value, code: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(code)
    if nonnegative and value < 0:
        raise ValueError(code)
    return float(value)


def _integer(value, code: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(code)
    return value


@dataclass(frozen=True)
class _Files:
    source: Path
    inputs: Path
    episode: Path
    acquisitions: Path
    rows: Path
    events: Path
    references: Path
    physics: Path

    def streams(self) -> dict:
        return {"acquisitions": self.acquisitions, "rows": self.rows, "events": self.events,
                "references": self.references, "physics": self.physics}


class EpisodeAuditWriter:
    """The single writer of one episode's raw audit."""

    def __init__(self, root: Path, scope: dict, identity: dict, inputs: dict) -> None:
        self.root = Path(root)
        if (not self.root.is_absolute() or ".." in self.root.parts
                or not isinstance(scope, dict) or not isinstance(identity, dict)
                or not isinstance(inputs, dict)):
            raise ValueError("AUDIT_ROOT_INVALID")
        digest = inputs.get("inputs_sha256") if isinstance(inputs, dict) else None
        if not scope or not identity or not inputs:
            raise ValueError("AUDIT_SCOPE_INVALID")
        if (not isinstance(digest, str) or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)):
            # the audit always names the frozen inputs it belongs to
            raise ValueError("AUDIT_INPUTS_INVALID")
        self.root.mkdir(parents=False, exist_ok=False)
        audit = self.root / "audit"
        audit.mkdir()
        self.files = _Files(audit / "source.json", audit / "inputs.json", audit / "episode.json",
                            audit / "acquisitions.jsonl", audit / "rows.jsonl",
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
        self._acquisitions: dict = {}
        self._bound: set = set()
        self._row_indexes: set = set()
        self._release_epoch: int | None = None
        self._observed_epochs: dict = {}
        self._sealed: Path | None = None

    # -- the only writer ---------------------------------------------------

    def append_acquisition(self, frame) -> None:
        self._require_open()
        record = {field: getattr(frame, field) for field in _ACQUISITION_FIELDS}
        _closed(record, _ACQUISITION_FIELDS, "AUDIT_SCHEMA_INVALID")
        if record["acquisition_id"] in self._acquisitions:
            raise ValueError("AUDIT_ACQUISITION_DUPLICATE")
        self._acquisitions[record["acquisition_id"]] = record
        self._append("acquisitions", record)

    def bind_row(self, row_index, sim_time_s, head_id, wrist_id, reference_sequence) -> None:
        self._require_open()
        record = {"row_index": _integer(row_index, "AUDIT_ROW_INVALID"),
                  "sim_time_s": _finite(sim_time_s, "AUDIT_ROW_INVALID", nonnegative=True),
                  "head_id": head_id, "wrist_id": wrist_id,
                  "reference_sequence": _integer(reference_sequence, "AUDIT_ROW_INVALID")}
        _closed(record, _ROW_FIELDS, "AUDIT_ROW_INVALID")
        for name, value in (("head_id", head_id), ("wrist_id", wrist_id)):
            if not isinstance(value, str) or not value or value not in self._acquisitions:
                # a row may not be bound to an acquisition the audit never saw
                raise ValueError("AUDIT_BINDING_UNKNOWN")
            if value in self._bound:
                # one acquisition fills one row, the same rule the capture enforces
                raise ValueError("AUDIT_BINDING_REUSED")
        if record["row_index"] in self._row_indexes:
            raise ValueError("AUDIT_ROW_INVALID")
        self._row_indexes.add(record["row_index"])
        self._bound.update((head_id, wrist_id))
        self._append("rows", record)

    def append_source(self, kind, record) -> None:
        self._require_open()
        if kind not in SOURCE_KINDS:
            raise ValueError("AUDIT_SOURCE_KIND_INVALID")
        if kind == "events":
            item = _closed(record, _EVENT_FIELDS - {"sequence"}, "AUDIT_SCHEMA_INVALID").copy()
            # a runner knows the verified physics step at the boundary; a sim time is recorded only
            # when the source actually supplies one, never invented from the step
            _integer(item["physics_step"], "AUDIT_SCHEMA_INVALID")
            if item["sim_time_s"] is not None:
                _finite(item["sim_time_s"], "AUDIT_SCHEMA_INVALID", nonnegative=True)
            if (not isinstance(item["kind"], str) or not item["kind"]
                    or not isinstance(item["detail"], str)):
                raise ValueError("AUDIT_SCHEMA_INVALID")
            item["sequence"] = self._next("events")
        elif kind == "references":
            item = _closed(record, _REFERENCE_FIELDS - {"sequence"}, "AUDIT_SCHEMA_INVALID").copy()
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
        else:
            item = _closed(record, _PHYSICS_FIELDS - {"sequence"}, "AUDIT_SCHEMA_INVALID").copy()
            if item["kind"] not in _PHYSICS_KINDS or not isinstance(item["observation"], dict):
                raise ValueError("AUDIT_SCHEMA_INVALID")
            _finite(item["sim_time_s"], "AUDIT_SCHEMA_INVALID", nonnegative=True)
            epoch = _integer(item["release_epoch"], "AUDIT_SCHEMA_INVALID")
            self._apply_epoch(epoch, item["kind"], item["observation"])
            item["sequence"] = self._next("physics")
        self._append(kind, item)

    def seal(self, window: dict) -> Path:
        self._require_open()
        if not isinstance(window, dict) or not window:
            raise ValueError("AUDIT_WINDOW_INVALID")
        for name, stream in self._streams.items():
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
        files = {path.name: _sha256(path) for path in self.files.streams().values()}
        files.update({path.name: _sha256(path) for path in (self.files.source, self.files.inputs,
                                                            self.files.episode)})
        manifest = {"kind": MANIFEST_KIND, "schema_version": 1, "window": dict(window),
                    "files": files, "inputs_sha256": self.inputs["inputs_sha256"]}
        target = self.root / "audit" / "audit-manifest.json"
        self._write_new(target, _canonical(manifest))
        self._fsync_dir(target.parent)
        self._sealed = target
        return target

    # -- helpers -----------------------------------------------------------

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

    def _next(self, kind: str) -> int:
        self._sequence[kind] += 1
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


def verify_audit_manifest(path: Path) -> dict:
    """Re-read a sealed audit and recompute it; a rewritten file or lost binding is refused."""

    path = Path(path)
    try:
        manifest = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("AUDIT_MANIFEST_INVALID") from error
    if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_FIELDS:
        raise ValueError("AUDIT_MANIFEST_INVALID")
    if manifest["kind"] != MANIFEST_KIND or manifest["schema_version"] != 1:
        raise ValueError("AUDIT_MANIFEST_INVALID")
    audit = path.parent
    for name, digest in manifest["files"].items():
        target = audit / name
        if not target.is_file() or _sha256(target) != digest:
            # a changed raw reference, a rewritten stream or a deleted file lands here
            raise ValueError("AUDIT_HASH_MISMATCH")
    acquisitions = {}
    for line in (audit / "acquisitions.jsonl").read_text().splitlines():
        record = json.loads(line)
        acquisitions[record["acquisition_id"]] = record
    bound: set = set()
    for line in (audit / "rows.jsonl").read_text().splitlines():
        record = json.loads(line)
        for name in ("head_id", "wrist_id"):
            value = record[name]
            if value not in acquisitions or value in bound:
                raise ValueError("AUDIT_BINDING_UNKNOWN")
            bound.add(value)
    epoch: int | None = None
    for line in (audit / "physics.jsonl").read_text().splitlines():
        record = json.loads(line)
        if epoch is None or record["release_epoch"] > epoch:
            epoch = record["release_epoch"]
        elif record["release_epoch"] < epoch:
            raise ValueError("AUDIT_RELEASE_EPOCH_STALE")
    return manifest
