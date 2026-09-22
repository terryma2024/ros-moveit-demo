"""The campaign body drains the durable shared queue: one lease, one point (design section 8).

Task 11's live gate found the gap this module closes. The campaign reported a pass while every
Worker refused to execute anything: the lease document the campaign wrote carried no
`points_path`/`points_sha256`, so `single_point_input.pick_place_request` answered
`{"requested": False, "error": "POINTS_PATH_MISSING"}` and the durable queue was never seeded from
`--point-id` at all. `lease_worker_execution` in the campaign CLI already knew how to turn a lease
into an executable single-point input; nothing called it.

The drain here is that wiring, and it is deliberately narrow:

* **one lease, one point.** `queue.lease_next()` is the only issuer, `write_single_point_input()`
  writes the point file the Worker reads back, and the lease document carries the path and digest.
  A point can never be leased twice for one generation, and an unselected point can never obtain a
  lease.
* **a result is committed only after the evidence is durable.** The Worker writes its result
  document and the batch runner's `point-result.json`/dynamic manifest first; the drain reads them
  back, hashes them, and only then commits the business outcome to the queue and to the journal.
  A point whose chain is incomplete is recorded as an *infrastructure* failure - it is never
  committed as a business result and never silently skipped.
* **the canonical committed events with the watermark.** POINT_LEASED, ATTEMPT_STARTED,
  RESULT_COMMITTED and POINT_TERMINAL are appended through `CoordinatorJournal.append_committed`,
  which fsyncs the frame, publishes the committed watermark and only then returns.
* **the verdict cannot pass over an unexecuted selection.** `point_execution_summary()` is the
  campaign's own statement about the selected point set, and it is what the verdict requires.

Business versus infrastructure, precisely:

* `SUCCEEDED` -> business `PASSED`; `FAILED` -> business `FAILED`; `SKIPPED_UNREACHABLE` -> business
  `INDETERMINATE` (a point declared unreachable is a terminal, honest non-execution).
* Anything else - a missing or unreadable `point-result.json`, a missing station, a refused
  pick-place request, an ambiguous evidence tree - is `INFRA_FAILED`: no business result, no queue
  terminal state, and the campaign stops rather than re-leasing the point into a second execution.
* `moveit_executed` means the point reached its terminal business decision (the batch's own
  `point-result.json`); `physical_evidence` means the dynamic execution manifest is on disk, and it
  is required for every `PASSED` point.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Mapping, Sequence

from ..runtime.task_artifacts import atomic_json, fsync_directory
from .queue import CommittedResult, DurablePointQueue, PointLease, WorkerIdentity
from .resource_identity import canonical_sha256
from .selection import (
    FirstPassSelectionBinding,
    RetrySelectionBinding,
    build_first_pass_selection,
    build_retry_selection,
)
from .single_point_input import (
    PointExecutionResult,
    SinglePointInputError,
    write_single_point_input,
)

SELECTION_DOCUMENT_SCHEMA_VERSION = 1
SELECTION_DOCUMENT_BASENAME = "selection-binding.json"
POINT_RESULTS_DIRNAME = "point-results"
POINT_RESULT_BASENAME = "point-result.json"
DYNAMIC_MANIFEST_RELATIVE = "dynamic/dynamic-execute-manifest.json"
INSTALLED_CATALOG_RELATIVE = "config/mujoco/moveit_expert_validation_points_v1.yaml"

COMMITTED = "COMMITTED"
INFRA_FAILED = "INFRA_FAILED"

#: The batch runner's terminal status vocabulary -> the queue's business outcome vocabulary.
BUSINESS_BY_STATUS: Mapping[str, str] = {
    "SUCCEEDED": "PASSED",
    "FAILED": "FAILED",
    "SKIPPED_UNREACHABLE": "INDETERMINATE",
}

#: The modules whose bytes define what "this selection executes here" means.
EXECUTION_MODULES = (
    "so101_demo.parallel_batch.point_drain",
    "so101_demo.parallel_batch.single_point_input",
    "so101_demo.parallel_batch.queue",
    "so101_demo.parallel_batch.selection",
)

#: The environment pins that belong to the runtime closure identity.
CLOSURE_VARIABLES = (
    "DYLD_LIBRARY_PATH",
    "LD_LIBRARY_PATH",
    "PYTORCH_ENABLE_MPS_FALLBACK",
    "SO101_OWNER_TREE_ROOT",
)


class PointDrainError(RuntimeError):
    """The drain refused an operation, or found a fact that forbids continuing."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(Path(path).read_bytes())


# --------------------------------------------------------------------------------------
# the runtime closure identity and the immutable selection document
# --------------------------------------------------------------------------------------


def runtime_closure_sha256(*, catalog_path: Path, catalog_sha256: str, config_sha256: str,
                           environment: Mapping[str, str] | None = None) -> str:
    """Digest the execution closure a selection binding is frozen against.

    The digest covers the catalog, the profile document and the bytes of the modules that turn a
    lease into an executed point, plus the environment pins that change what those modules load.
    It is recomputed from content rather than trusted, so "the same closure" is a checked fact.
    """

    values = dict(os.environ if environment is None else environment)
    modules = {}
    for name in EXECUTION_MODULES:
        module = importlib.import_module(name)
        path = Path(module.__file__).resolve()
        modules[name] = {"path": str(path), "sha256": _sha256_file(path)}
    return canonical_sha256({
        "catalog_path": str(Path(catalog_path).resolve()),
        "catalog_sha256": catalog_sha256,
        "config_sha256": config_sha256,
        "modules": modules,
        "python_executable": sys.executable,
        "platform": sys.platform,
        "environment": {name: values.get(name) for name in CLOSURE_VARIABLES},
    })


def first_pass_binding(*, catalog_path: Path, point_ids: Sequence[str], campaign_id: str,
                       batch_id: str, config_sha256: str, runtime_closure_sha256: str,
                       coordinate_frame: str = "world",
                       expected_catalog_sha256: str | None = None
                       ) -> FirstPassSelectionBinding:
    """Freeze the ordered first-pass selection the campaign must execute."""

    return build_first_pass_selection(
        catalog_path=Path(catalog_path), point_ids=tuple(point_ids),
        campaign_id=campaign_id, batch_id=batch_id, config_sha256=config_sha256,
        runtime_closure_sha256=runtime_closure_sha256, coordinate_frame=coordinate_frame,
        expected_catalog_sha256=expected_catalog_sha256)


def retry_binding(*, source: Mapping[str, object], catalog_path: Path, campaign_id: str,
                  batch_id: str, config_sha256: str, runtime_closure_sha256: str,
                  expected_catalog_sha256: str | None = None) -> RetrySelectionBinding:
    """Freeze the one business `FAILED` point one v5 retry batch may execute."""

    return build_retry_selection(
        catalog_path=Path(catalog_path), point_id=str(source["point_id"]),
        original_selection_sha256=str(source["original_selection_sha256"]),
        original_result_sha256=str(source["original_result_sha256"]),
        original_outcome=str(source["original_outcome"]), campaign_id=campaign_id,
        batch_id=batch_id, config_sha256=config_sha256,
        runtime_closure_sha256=runtime_closure_sha256,
        expected_catalog_sha256=expected_catalog_sha256)


def binding_catalog_sha256(binding) -> str:
    """The catalog digest of either binding: a retry names it as the *original* catalog."""

    return str(getattr(binding, "catalog_sha256", None)
               or getattr(binding, "original_catalog_sha256"))


def selection_document_for(binding, *, catalog_path: Path) -> dict:
    """The audit projection of the one selection a campaign executes, for either binding kind.

    A first-pass binding carries the catalog it was frozen from; a retry binding carries the
    *original* catalog, selection and result hashes of the committed business `FAILED` point it
    references. Both documents must carry a catalog digest, because the retry chain is read back
    from exactly this file.
    """

    document = {
        "schema_version": SELECTION_DOCUMENT_SCHEMA_VERSION,
        "catalog_path": str(Path(catalog_path).resolve()),
        "catalog_sha256": binding_catalog_sha256(binding),
        "config_sha256": binding.config_sha256,
        "runtime_closure_sha256": binding.runtime_closure_sha256,
        "selection_sha256": binding.selection_sha256,
        "selected_point_ids": list(binding.selected_point_ids),
        "campaign_id": binding.campaign_id,
        "batch_id": binding.batch_id,
        "kind": ("FULL_RESTART_RETRY" if isinstance(binding, RetrySelectionBinding)
                 else "FIRST_PASS"),
        "binding": binding.as_document(),
    }
    if isinstance(binding, RetrySelectionBinding):
        document["original_selection_sha256"] = binding.original_selection_sha256
        document["original_result_sha256"] = binding.original_result_sha256
        document["original_outcome"] = binding.original_outcome
    return document


def write_selection_document(*, evidence_root: Path, binding, catalog_path: Path) -> Path:
    """Write the immutable selection binding a retry chain can reference, once.

    Rewriting the same bytes is idempotent; a different document at the same path is refused,
    because a selection that changed after it was recorded is not the selection that ran.
    """

    document = selection_document_for(binding, catalog_path=catalog_path)
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path = Path(evidence_root) / SELECTION_DOCUMENT_BASENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise PointDrainError("SELECTION_DOCUMENT_CONFLICT", str(path))
        return path
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fsync_directory(path.parent)
    return path


def read_selection_document(path: Path) -> dict:
    """Read a recorded selection binding, refusing anything that is not one."""

    path = Path(path)
    try:
        document = json.loads(path.read_bytes())
    except (OSError, ValueError) as error:
        raise PointDrainError("SELECTION_DOCUMENT_UNREADABLE", f"{path}: {error}") from error
    if not isinstance(document, dict) or \
            document.get("schema_version") != SELECTION_DOCUMENT_SCHEMA_VERSION:
        raise PointDrainError("SELECTION_DOCUMENT_UNREADABLE", str(path))
    for name in ("selection_sha256", "catalog_sha256", "catalog_path", "selected_point_ids"):
        if name not in document:
            raise PointDrainError("SELECTION_DOCUMENT_UNREADABLE", f"{path}: {name}")
    return document


def read_retry_source(*, prior_root: Path, point_id: str,
                      selection_document_path: Path | None = None) -> dict:
    """The original selection/result chain one retry admission must reference.

    The original result has to be a *committed business* `FAILED` document: an infrastructure
    failure, an indeterminate point or a point that never ran cannot be retried, and the retry
    binding refuses it by name.
    """

    root = Path(prior_root)
    document = read_selection_document(
        root / SELECTION_DOCUMENT_BASENAME if selection_document_path is None
        else Path(selection_document_path))
    if point_id not in tuple(document["selected_point_ids"]):
        raise PointDrainError("RETRY_POINT_NOT_SELECTED", point_id)
    result_path = root / POINT_RESULTS_DIRNAME / f"{point_id}.json"
    try:
        payload = result_path.read_bytes()
    except OSError as error:
        raise PointDrainError("RETRY_POINT_NOT_COMMITTED", f"{result_path}: {error}") from error
    try:
        result = json.loads(payload)
    except ValueError as error:
        raise PointDrainError("RETRY_POINT_NOT_COMMITTED", str(result_path)) from error
    if not isinstance(result, dict) or result.get("committed") is not True:
        raise PointDrainError("RETRY_POINT_NOT_COMMITTED", str(result_path))
    if result.get("outcome") != "FAILED":
        raise PointDrainError("RETRY_POINT_NOT_FAILED", str(result.get("outcome")))
    return {
        "point_id": point_id,
        "original_catalog_sha256": str(document["catalog_sha256"]),
        "original_selection_sha256": str(document["selection_sha256"]),
        "original_result_sha256": _sha256_bytes(payload),
        "original_outcome": "FAILED",
        "original_result_path": str(result_path),
        "catalog_path": str(document["catalog_path"]),
        "prior_root": str(root),
    }


# --------------------------------------------------------------------------------------
# one lease: the single point file the Worker reads back
# --------------------------------------------------------------------------------------


def station_root_for(*, evidence_root: Path, worker_id: str, attempt_id: str) -> Path:
    """Where one attempt's station lives: a fresh root per lease, never a reused one."""

    return Path(evidence_root) / f"{worker_id}-station" / attempt_id


def worker_progress_request_id(*, worker_id: str, generation: int, index: int) -> str:
    """The request id one Worker generation uses for its IPC round trips.

    It is derived from the generation so a Worker that is spawned again for the next point cannot
    replay an id the one-time admission table already consumed.
    """

    return f"{worker_id}-req-g{int(generation):02d}-{int(index):02d}"


def worker_probe_attempt_id(*, worker_id: str, generation: int, index: int) -> str:
    """The extra inference attempt ids one lease carries beside its own point attempt.

    They are generation-scoped for the same reason the round-trip ids are: the campaign binds them
    in the one-time table before each spawn, and a repeated id is refused - so a second lease for
    the same slot must never re-derive the first lease's ids.
    """

    return f"{worker_id}-att-g{int(generation):02d}-{int(index):02d}"


def write_lease_document(*, queue: DurablePointQueue, binding, worker_id: str, slot_id: str,
                         evidence_root: Path, input_sha256: str, deadline_s: float = 240.0,
                         generation: int = 1, model_id: str = "yolo", attempt_count: int = 3,
                         tamper_input_sha256: bool = False, duplicate_probe: bool = False,
                         execution_profile: str | None = None, batch_kind: str | None = None,
                         schema_version: int | None = None,
                         lease_name: str | None = None, point_id: str | None = None,
                         journal=None) -> dict:
    """Lease the next unleased point and write the document the Worker executes from.

    This is the campaign body's only lease issuer: it takes the queue's next point, writes the
    single-point input through `write_single_point_input` (fsynced, atomic, hash-bound) and puts
    the path and digest into the lease document the Worker already reads. `point_id` may only
    *confirm* the queue's own choice; it can never select a different point.
    """

    from .queue import WorkerIdentity as _WorkerIdentity

    if not isinstance(queue, DurablePointQueue):
        raise PointDrainError("LEASE_QUEUE_TYPE", type(queue).__name__)
    if not isinstance(binding, (FirstPassSelectionBinding, RetrySelectionBinding)):
        raise PointDrainError("LEASE_BINDING_TYPE", type(binding).__name__)
    if queue.selection_sha256 != binding.selection_sha256:
        raise PointDrainError("LEASE_SELECTION_MISMATCH", queue.selection_sha256)
    identity = _WorkerIdentity(worker_id=worker_id, slot_id=slot_id, generation=int(generation))
    lease = queue.lease_next(identity)
    if lease is None:
        raise PointDrainError("QUEUE_NO_PENDING_POINT", worker_id)
    if point_id is not None and point_id != lease.point_id:
        raise PointDrainError("LEASE_POINT_MISMATCH", f"{point_id} != {lease.point_id}")
    execution_input = write_single_point_input(binding=binding, lease=lease, root=evidence_root)
    attempt_ids = [lease.attempt_id] + [
        worker_probe_attempt_id(worker_id=worker_id, generation=int(generation), index=attempt)
        for attempt in range(1, attempt_count)
    ]
    station_root = station_root_for(
        evidence_root=evidence_root, worker_id=worker_id, attempt_id=lease.attempt_id)
    document = {
        "worker_id": worker_id, "slot_id": slot_id, "batch_id": binding.batch_id,
        "campaign_id": binding.campaign_id,
        "execution_profile": execution_profile, "batch_kind": batch_kind,
        "schema_version": schema_version,
        "coordinator_epoch": 1, "worker_generation": int(generation), "lease_generation": 1,
        "reset_epoch": "epoch-1", "point_id": lease.point_id, "model_id": model_id,
        "attempt_id": lease.attempt_id, "attempt_ids": attempt_ids,
        "point_sha256": execution_input.point_sha256,
        "points_path": str(execution_input.absolute_path(evidence_root)),
        "points_sha256": execution_input.points_sha256,
        "selection_sha256": binding.selection_sha256,
        "station_root": str(station_root),
        "worker_root": str(evidence_root / f"{worker_id}-worker"),
        "snapshot_path": str(evidence_root / f"{worker_id}-frame.npy"),
        "input_sha256": input_sha256, "source_stamp_ns": 1_000_000_000,
        "source_frame_id": "task_camera_frame", "shape": [480, 640, 3],
        "deadline_s": float(deadline_s),
        "tamper_input_sha256": bool(tamper_input_sha256),
        "duplicate_probe": bool(duplicate_probe),
        "start_event_type": "attempt_started",
    }
    frame_path = Path(document["snapshot_path"])
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    if not frame_path.exists():
        frame_path.write_bytes(b"campaign-warm-frame")
    lease_path = Path(evidence_root) / (
        lease_name if lease_name is not None
        else f"{worker_id}-lease-{int(generation):02d}.json")
    lease_path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
    document["lease_path"] = str(lease_path)
    document["lease_sha256"] = canonical_sha256(lease.as_document())
    if journal is not None:
        journal.append_committed(
            "POINT_LEASED", f"{binding.batch_id}/POINT_LEASED/{lease.attempt_id}",
            {"point_id": lease.point_id, "attempt_id": lease.attempt_id,
             "worker_id": worker_id, "slot_id": slot_id, "generation": int(generation),
             "lease": lease.as_document(), "lease_sha256": document["lease_sha256"],
             "points_path": document["points_path"],
             "points_sha256": document["points_sha256"],
             "selection_sha256": binding.selection_sha256})
    return document


# --------------------------------------------------------------------------------------
# the evidence one attempt must have before a business result may be committed
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PointEvidence:
    """The durable evidence one executed point left behind."""

    point_id: str
    status: str
    failure_code: str | None
    manifest_relative_path: str
    manifest_sha256: str
    dynamic_manifest_relative_path: str | None
    dynamic_manifest_sha256: str | None

    @property
    def physical_evidence(self) -> bool:
        return self.dynamic_manifest_relative_path is not None


def read_point_evidence(*, pick_root: Path, point_id: str) -> PointEvidence:
    """Read one point's terminal manifest out of a Worker's pick-place evidence root.

    Exactly one `point-result.json` must exist under the root and it must name the leased point.
    Zero, several, unreadable or mismatched documents are refusals, not empty answers.
    """

    root = Path(pick_root)
    if not root.is_dir():
        raise PointDrainError("POINT_EVIDENCE_MISSING", str(root))
    matches = sorted(root.rglob(POINT_RESULT_BASENAME))
    if not matches:
        raise PointDrainError("POINT_EVIDENCE_MISSING", str(root))
    if len(matches) > 1:
        raise PointDrainError(
            "POINT_EVIDENCE_AMBIGUOUS", ", ".join(str(item) for item in matches))
    manifest = matches[0]
    try:
        payload = manifest.read_bytes()
        document = json.loads(payload)
    except (OSError, ValueError) as error:
        raise PointDrainError("POINT_EVIDENCE_UNREADABLE", f"{manifest}: {error}") from error
    if not isinstance(document, dict) or document.get("id") != point_id:
        raise PointDrainError(
            "POINT_EVIDENCE_MISMATCH",
            f"{document.get('id') if isinstance(document, dict) else document!r} != {point_id}")
    status = document.get("status")
    if not isinstance(status, str) or not status:
        raise PointDrainError("POINT_EVIDENCE_MISMATCH", f"status={status!r}")
    dynamic_relative = None
    dynamic_sha = None
    dynamic = manifest.parent / DYNAMIC_MANIFEST_RELATIVE
    if dynamic.is_file():
        dynamic_relative = dynamic.relative_to(root).as_posix()
        dynamic_sha = _sha256_file(dynamic)
    failure_code = document.get("failure_code")
    return PointEvidence(
        point_id=point_id, status=status,
        failure_code=failure_code if isinstance(failure_code, str) else None,
        manifest_relative_path=manifest.relative_to(root).as_posix(),
        manifest_sha256=_sha256_bytes(payload),
        dynamic_manifest_relative_path=dynamic_relative,
        dynamic_manifest_sha256=dynamic_sha)


# --------------------------------------------------------------------------------------
# one attempt: what the Worker reported, classified honestly
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PointAttempt:
    """One lease's outcome, as the campaign records it."""

    point_id: str
    attempt_id: str
    worker_id: str
    slot_id: str
    generation: int
    state: str
    outcome: str | None
    failure_code: str | None
    infrastructure_code: str | None
    lease_sha256: str
    points_path: str
    points_sha256: str
    evidence_manifest_relative_path: str | None
    evidence_manifest_sha256: str | None
    dynamic_manifest_relative_path: str | None
    dynamic_manifest_sha256: str | None
    physical_evidence: bool
    station_ready: bool
    moveit_executed: bool
    cleanup_owned: bool
    batch_exit_code: int | None
    worker_result_path: str
    worker_result_sha256: str
    worker_pid: int | None
    released: str | None = None
    station_readback: Mapping[str, object] = field(default_factory=dict)

    @property
    def committed(self) -> bool:
        return self.state == COMMITTED

    def as_document(self) -> dict:
        return {
            "point_id": self.point_id, "attempt_id": self.attempt_id,
            "worker_id": self.worker_id, "slot_id": self.slot_id,
            "generation": self.generation, "state": self.state, "outcome": self.outcome,
            "failure_code": self.failure_code,
            "infrastructure_code": self.infrastructure_code,
            "lease_sha256": self.lease_sha256,
            "points_path": self.points_path, "points_sha256": self.points_sha256,
            "evidence_manifest_relative_path": self.evidence_manifest_relative_path,
            "evidence_manifest_sha256": self.evidence_manifest_sha256,
            "dynamic_manifest_relative_path": self.dynamic_manifest_relative_path,
            "dynamic_manifest_sha256": self.dynamic_manifest_sha256,
            "physical_evidence": self.physical_evidence,
            "station_ready": self.station_ready,
            "moveit_executed": self.moveit_executed,
            "cleanup_owned": self.cleanup_owned,
            "batch_exit_code": self.batch_exit_code,
            "worker_result_path": self.worker_result_path,
            "worker_result_sha256": self.worker_result_sha256,
            "worker_pid": self.worker_pid,
            "released": self.released,
            "station_readback": dict(self.station_readback),
        }


def unfinished_attempt(*, lease_document: Mapping[str, object], run: "WorkerRun", code: str,
                       released: str | None = None,
                       station_readback: Mapping[str, object] | None = None) -> PointAttempt:
    """The attempt record for a Worker that produced no result document at all.

    A Worker that exited without writing its result cannot have committed anything, so this is an
    infrastructure failure with the reason attached - never a business outcome, and never a reason
    to wait for the campaign's whole budget.
    """

    return PointAttempt(
        point_id=str(lease_document["point_id"]), attempt_id=str(lease_document["attempt_id"]),
        worker_id=run.worker_id, slot_id=run.slot_id, generation=run.generation,
        state=INFRA_FAILED, outcome=None, failure_code=None, infrastructure_code=code,
        lease_sha256=str(lease_document.get("lease_sha256") or ""),
        points_path=str(lease_document.get("points_path") or ""),
        points_sha256=str(lease_document.get("points_sha256") or ""),
        evidence_manifest_relative_path=None, evidence_manifest_sha256=None,
        dynamic_manifest_relative_path=None, dynamic_manifest_sha256=None,
        physical_evidence=False, station_ready=False, moveit_executed=False,
        cleanup_owned=False, batch_exit_code=None, worker_result_path="",
        worker_result_sha256="", worker_pid=run.pid, released=released,
        station_readback=dict(station_readback or {}))


def read_worker_result(path: Path) -> tuple[dict, str]:
    """Read a Worker's atomically written result document and digest its bytes."""

    path = Path(path)
    try:
        payload = path.read_bytes()
        document = json.loads(payload)
    except (OSError, ValueError) as error:
        raise PointDrainError("WORKER_RESULT_UNREADABLE", f"{path}: {error}") from error
    if not isinstance(document, dict):
        raise PointDrainError("WORKER_RESULT_UNREADABLE", f"{path}: not an object")
    return document, _sha256_bytes(payload)


def _station_ready(worker_result: Mapping[str, object]) -> bool:
    record = worker_result.get("station_record")
    if not isinstance(record, Mapping):
        return False
    ready = record.get("ready")
    if not isinstance(ready, Mapping):
        return False
    return ready.get("ready") is True and ready.get("exit_code") == 0


def attempt_from_worker(*, lease_document: Mapping[str, object], worker_result: Mapping[str, object],
                        worker_result_sha256: str, worker_result_path: Path,
                        evidence_root: Path) -> PointAttempt:
    """Classify one lease's outcome from the Worker's own durable result document.

    The classification never guesses: a chain that cannot be completed is an infrastructure
    failure with the code that says which link is missing.
    """

    point_id = str(lease_document["point_id"])
    attempt_id = str(lease_document["attempt_id"])
    worker_id = str(lease_document["worker_id"])
    slot_id = str(lease_document["slot_id"])
    generation = int(lease_document["worker_generation"])
    lease_sha256 = str(lease_document.get("lease_sha256") or "")
    worker_pid = worker_result.get("pid")
    pick_place = worker_result.get("pick_place")
    pick_place = pick_place if isinstance(pick_place, Mapping) else {}

    def infrastructure(code: str, *, station_ready: bool,
                       exit_code: int | None = None) -> PointAttempt:
        return PointAttempt(
            point_id=point_id, attempt_id=attempt_id, worker_id=worker_id, slot_id=slot_id,
            generation=generation, state=INFRA_FAILED, outcome=None, failure_code=None,
            infrastructure_code=code, lease_sha256=lease_sha256,
            points_path=str(lease_document.get("points_path") or ""),
            points_sha256=str(lease_document.get("points_sha256") or ""),
            evidence_manifest_relative_path=None, evidence_manifest_sha256=None,
            dynamic_manifest_relative_path=None, dynamic_manifest_sha256=None,
            physical_evidence=False, station_ready=station_ready, moveit_executed=False,
            cleanup_owned=False, batch_exit_code=exit_code,
            worker_result_path=str(worker_result_path),
            worker_result_sha256=worker_result_sha256,
            worker_pid=worker_pid if isinstance(worker_pid, int) else None)

    station_ready = _station_ready(worker_result)
    exit_code = pick_place.get("exit_code")
    exit_code = exit_code if isinstance(exit_code, int) else None
    if not pick_place.get("requested"):
        return infrastructure(str(pick_place.get("error") or "PICK_PLACE_NOT_REQUESTED"),
                              station_ready=station_ready, exit_code=exit_code)
    if not station_ready:
        return infrastructure("STATION_NOT_READY", station_ready=False, exit_code=exit_code)
    expected_pick_root = station_root_for(
        evidence_root=evidence_root, worker_id=worker_id, attempt_id=attempt_id) / "pick"
    reported = pick_place.get("evidence_root")
    if not isinstance(reported, str) or Path(reported) != expected_pick_root:
        return infrastructure("PICK_ROOT_MISMATCH", station_ready=True, exit_code=exit_code)
    try:
        evidence = read_point_evidence(pick_root=expected_pick_root, point_id=point_id)
    except PointDrainError as error:
        return infrastructure(error.code, station_ready=True, exit_code=exit_code)
    outcome = BUSINESS_BY_STATUS.get(evidence.status)
    if outcome is None:
        return infrastructure("POINT_STATUS_UNKNOWN", station_ready=True, exit_code=exit_code)
    # The attempt records the evidence paths relative to the *campaign* evidence root, so a reader
    # of the campaign document can open them without knowing this attempt's pick root.
    def campaign_relative(relative: str | None) -> str | None:
        if relative is None:
            return None
        return (expected_pick_root / relative).relative_to(evidence_root).as_posix()

    return PointAttempt(
        point_id=point_id, attempt_id=attempt_id, worker_id=worker_id, slot_id=slot_id,
        generation=generation, state=COMMITTED, outcome=outcome,
        failure_code=evidence.failure_code, infrastructure_code=None,
        lease_sha256=lease_sha256,
        points_path=str(lease_document.get("points_path") or ""),
        points_sha256=str(lease_document.get("points_sha256") or ""),
        evidence_manifest_relative_path=campaign_relative(evidence.manifest_relative_path),
        evidence_manifest_sha256=evidence.manifest_sha256,
        dynamic_manifest_relative_path=campaign_relative(
            evidence.dynamic_manifest_relative_path),
        dynamic_manifest_sha256=evidence.dynamic_manifest_sha256,
        physical_evidence=evidence.physical_evidence,
        station_ready=True, moveit_executed=True, cleanup_owned=True,
        batch_exit_code=exit_code, worker_result_path=str(worker_result_path),
        worker_result_sha256=worker_result_sha256,
        worker_pid=worker_pid if isinstance(worker_pid, int) else None)


# --------------------------------------------------------------------------------------
# commit: journal first, then the queue, then the terminal event
# --------------------------------------------------------------------------------------


def _committed_document(*, attempt: PointAttempt, lease: PointLease,
                        execution_result: PointExecutionResult | None) -> dict:
    return {
        "schema_version": 1,
        "point_id": attempt.point_id,
        "attempt_id": attempt.attempt_id,
        "outcome": attempt.outcome,
        "committed": True,
        "lease_identity": list(lease.identity),
        "lease_sha256": attempt.lease_sha256,
        "worker_id": attempt.worker_id,
        "slot_id": attempt.slot_id,
        "generation": attempt.generation,
        "points_path": attempt.points_path,
        "points_sha256": attempt.points_sha256,
        "evidence_manifest_relative_path": attempt.evidence_manifest_relative_path,
        "evidence_manifest_sha256": attempt.evidence_manifest_sha256,
        "dynamic_manifest_relative_path": attempt.dynamic_manifest_relative_path,
        "dynamic_manifest_sha256": attempt.dynamic_manifest_sha256,
        "physical_evidence": attempt.physical_evidence,
        "station_ready": attempt.station_ready,
        "moveit_executed": attempt.moveit_executed,
        "cleanup_owned": attempt.cleanup_owned,
        "failure_code": attempt.failure_code,
        "batch_exit_code": attempt.batch_exit_code,
        "worker_result_path": attempt.worker_result_path,
        "worker_result_sha256": attempt.worker_result_sha256,
        "worker_pid": attempt.worker_pid,
        "released": attempt.released,
        "station_readback": dict(attempt.station_readback),
        "execution_result": None if execution_result is None else execution_result.as_document(),
    }


def commit_attempt(*, queue: DurablePointQueue, binding, attempt: PointAttempt,
                   lease: PointLease | None, journal=None) -> PointAttempt:
    """Commit one attempt: the durable business result, or the honest infrastructure record.

    A business outcome is committed only after the Task 3 durability object accepts the chain
    (station ready, MoveIt/physics decision, evidence manifest, cleanup ownership, matching lease
    identity). Everything else is journalled as an infrastructure failure and never reaches the
    queue, so it can never be mistaken for an executed point.
    """

    if not attempt.committed:
        if journal is not None:
            journal.append_committed(
                "ATTEMPT_FAILED",
                f"{binding.batch_id}/ATTEMPT_FAILED/{attempt.attempt_id}",
                {"point_id": attempt.point_id, "attempt_id": attempt.attempt_id,
                 "worker_id": attempt.worker_id, "slot_id": attempt.slot_id,
                 "generation": attempt.generation,
                 "infrastructure_code": attempt.infrastructure_code,
                 "outcome": None,
                 "worker_result_sha256": attempt.worker_result_sha256,
                 "pick_place_error": attempt.infrastructure_code})
        return attempt

    if lease is None:
        raise PointDrainError("LEASE_REQUIRED", f"{attempt.point_id}/{attempt.attempt_id}")
    execution_result = None
    if attempt.outcome != "INDETERMINATE":
        try:
            execution_result = PointExecutionResult(
                lease_identity=lease.identity, point_id=attempt.point_id,
                attempt_id=attempt.attempt_id, outcome=str(attempt.outcome),
                business_decision=str(attempt.outcome),
                evidence_manifest_relative_path=str(attempt.evidence_manifest_relative_path),
                evidence_manifest_sha256=str(attempt.evidence_manifest_sha256),
                station_ready=attempt.station_ready, moveit_executed=attempt.moveit_executed,
                cleanup_owned=attempt.cleanup_owned)
        except SinglePointInputError as error:
            failed = _as_infrastructure(attempt, error.code)
            if journal is not None:
                journal.append_committed(
                    "ATTEMPT_FAILED",
                    f"{binding.batch_id}/ATTEMPT_FAILED/{attempt.attempt_id}",
                    {"point_id": attempt.point_id, "attempt_id": attempt.attempt_id,
                     "worker_id": attempt.worker_id, "slot_id": attempt.slot_id,
                     "generation": attempt.generation,
                     "infrastructure_code": error.code, "outcome": None,
                     "worker_result_sha256": attempt.worker_result_sha256})
            return failed

    document = _committed_document(attempt=attempt, lease=lease,
                                   execution_result=execution_result)
    if journal is not None:
        journal.append_committed(
            "RESULT_COMMITTED", f"{binding.batch_id}/RESULT_COMMITTED/{attempt.attempt_id}",
            {"point_id": attempt.point_id, "attempt_id": attempt.attempt_id,
             "worker_id": attempt.worker_id, "slot_id": attempt.slot_id,
             "generation": attempt.generation, "outcome": attempt.outcome,
             "lease_identity": list(lease.identity),
             "evidence_manifest_sha256": attempt.evidence_manifest_sha256,
             "dynamic_manifest_sha256": attempt.dynamic_manifest_sha256,
             "failure_code": attempt.failure_code,
             "station_ready": attempt.station_ready,
             "moveit_executed": attempt.moveit_executed,
             "cleanup_owned": attempt.cleanup_owned})
    queue.commit_result(
        lease,
        CommittedResult(point_id=attempt.point_id, attempt_id=attempt.attempt_id,
                        outcome=str(attempt.outcome),
                        evidence_sha256=str(attempt.evidence_manifest_sha256),
                        result_sha256=canonical_sha256(document)),
        worker=WorkerIdentity(worker_id=attempt.worker_id, slot_id=attempt.slot_id,
                              generation=attempt.generation))
    if journal is not None:
        journal.append_committed(
            "POINT_TERMINAL", f"{binding.batch_id}/POINT_TERMINAL/{attempt.point_id}",
            {"point_id": attempt.point_id, "attempt_id": attempt.attempt_id,
             "outcome": attempt.outcome, "state": COMMITTED,
             "result_sha256": canonical_sha256(document)})
    return attempt


def _active_lease(queue: DurablePointQueue, attempt: PointAttempt) -> PointLease:
    for lease in queue.snapshot().active_leases:
        if lease.attempt_id == attempt.attempt_id and lease.point_id == attempt.point_id:
            return lease
    raise PointDrainError("LEASE_NOT_ACTIVE", f"{attempt.point_id}/{attempt.attempt_id}")


def _as_infrastructure(attempt: PointAttempt, code: str) -> PointAttempt:
    return PointAttempt(
        point_id=attempt.point_id, attempt_id=attempt.attempt_id, worker_id=attempt.worker_id,
        slot_id=attempt.slot_id, generation=attempt.generation, state=INFRA_FAILED, outcome=None,
        failure_code=attempt.failure_code, infrastructure_code=code,
        lease_sha256=attempt.lease_sha256, points_path=attempt.points_path,
        points_sha256=attempt.points_sha256,
        evidence_manifest_relative_path=attempt.evidence_manifest_relative_path,
        evidence_manifest_sha256=attempt.evidence_manifest_sha256,
        dynamic_manifest_relative_path=attempt.dynamic_manifest_relative_path,
        dynamic_manifest_sha256=attempt.dynamic_manifest_sha256,
        physical_evidence=attempt.physical_evidence, station_ready=attempt.station_ready,
        moveit_executed=attempt.moveit_executed, cleanup_owned=attempt.cleanup_owned,
        batch_exit_code=attempt.batch_exit_code, worker_result_path=attempt.worker_result_path,
        worker_result_sha256=attempt.worker_result_sha256, worker_pid=attempt.worker_pid,
        released=attempt.released, station_readback=attempt.station_readback)


def write_committed_point_document(*, evidence_root: Path, attempt: PointAttempt,
                                   lease: PointLease) -> Path:
    """Write the per-point committed document the retry chain reads back."""

    document = _committed_document(attempt=attempt, lease=lease, execution_result=None)
    path = Path(evidence_root) / POINT_RESULTS_DIRNAME / f"{attempt.point_id}.json"
    atomic_json(path, document)
    return path


# --------------------------------------------------------------------------------------
# the campaign's own statement about the selected point set
# --------------------------------------------------------------------------------------


def point_execution_summary(*, selected_point_ids: Sequence[str],
                            attempts: Sequence[PointAttempt],
                            spawns: Sequence[Mapping[str, object]] = ()) -> dict:
    """Derive the completeness facts the verdict is allowed to require.

    `complete` is true only when every selected point has exactly one committed business result
    with a durable evidence manifest, no point was executed twice, no unselected point was ever
    attempted, no attempt ended in infrastructure failure, and every `PASSED` point carries its
    physical execution manifest.
    """

    selected = tuple(selected_point_ids)
    selected_set = set(selected)
    by_point: dict[str, list[PointAttempt]] = {point_id: [] for point_id in selected}
    unselected: list[str] = []
    for attempt in attempts:
        if attempt.point_id in selected_set:
            by_point.setdefault(attempt.point_id, []).append(attempt)
        else:
            unselected.append(attempt.point_id)
    duplicates = sorted(point_id for point_id, items in by_point.items() if len(items) > 1)
    committed = {point_id: items[0].outcome for point_id, items in by_point.items()
                 if len(items) == 1 and items[0].state == COMMITTED}
    unexecuted = [point_id for point_id in selected if point_id not in committed]
    infrastructure = [item.as_document() for items in by_point.values() for item in items
                      if item.state != COMMITTED]
    missing_physical = [point_id for point_id, items in by_point.items()
                        if len(items) == 1 and items[0].state == COMMITTED
                        and items[0].outcome == "PASSED" and not items[0].physical_evidence]
    complete = (not duplicates and not unselected and not infrastructure and not unexecuted
                and not missing_physical and len(committed) == len(selected))
    return {
        "selected_point_ids": list(selected),
        "committed": committed,
        "attempts": [attempt.as_document() for attempt in attempts],
        "workers": sorted({attempt.worker_id for attempt in attempts}),
        "spawns": [dict(spawn) for spawn in spawns],
        "duplicate_attempts": duplicates,
        "unselected_attempts": sorted(unselected),
        "unexecuted_point_ids": unexecuted,
        "infrastructure_failures": infrastructure,
        "missing_physical_evidence": missing_physical,
        "complete": complete,
    }


# --------------------------------------------------------------------------------------
# the drain loop
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WorkerRun:
    """What one spawn of one Worker amounts to."""

    worker_id: str
    slot_id: str
    generation: int
    pid: int | None
    status: str
    result_path: Path
    station_root: str

    def as_document(self) -> dict:
        return {"worker_id": self.worker_id, "slot_id": self.slot_id,
                "generation": self.generation, "pid": self.pid, "status": self.status,
                "result_path": str(self.result_path), "station_root": self.station_root}


@dataclass(frozen=True, slots=True)
class DrainReport:
    """What one drain did, in the order it did it."""

    attempts: tuple[PointAttempt, ...]
    spawns: tuple[dict, ...]
    releases: tuple[dict, ...]
    stop_reason: str | None
    stopped_at_cap: bool
    stop_detail: str | None = None

    def summary(self, *, selected_point_ids: Sequence[str]) -> dict:
        return point_execution_summary(
            selected_point_ids=selected_point_ids, attempts=self.attempts, spawns=self.spawns)


def drain_point_queue(*, queue: DurablePointQueue, binding, worker_ids: Sequence[str],
                      slot_ids: Sequence[str], evidence_root: Path,
                      lease_point: Callable[[str, str, int], dict],
                      spawn_worker: Callable[[str, str, int, dict], WorkerRun],
                      release_worker: Callable[[str, str], str] | None = None,
                      station_readback: Callable[[str], Mapping[str, object]] | None = None,
                      worker_alive: Callable[["WorkerRun"], bool] | None = None,
                      journal=None, max_points: int | None = None,
                      wait_timeout_s: float = 1500.0, poll_s: float = 0.25,
                      sleep: Callable[[float], None] = time.sleep,
                      clock: Callable[[], float] = time.monotonic) -> DrainReport:
    """Drain the durable queue: lease one point, execute it, commit it, lease the next.

    One slot is one concurrent Worker. Every iteration leases the queue's next *unleased* point for
    a free slot, waits for that Worker's durable result document, commits the outcome, releases the
    Worker (its result is only committed once the Worker that produced it is proven stopped) and
    then leases again - so a point is executed at most once and only selected points can ever be
    leased. An infrastructure failure stops the drain instead of re-leasing the point.
    """

    worker_ids = tuple(worker_ids)
    slot_ids = tuple(slot_ids)
    if len(worker_ids) != len(slot_ids):
        raise PointDrainError("DRAIN_SLOTS_MISMATCH", f"{worker_ids} != {slot_ids}")
    if not worker_ids:
        raise PointDrainError("DRAIN_SLOTS_MISMATCH", "no slots")
    if not callable(lease_point) or not callable(spawn_worker):
        raise PointDrainError("DRAIN_SEAM_MISSING", "lease_point and spawn_worker are required")

    worker_by_slot = dict(zip(slot_ids, worker_ids))
    generations = {slot_id: 0 for slot_id in slot_ids}
    in_flight: dict[str, tuple[WorkerRun, dict]] = {}
    attempts: list[PointAttempt] = []
    spawns: list[dict] = []
    releases: list[dict] = []
    stop_reason: str | None = None
    stop_detail: str | None = None
    stopped_at_cap = False
    leased = 0
    deadline = clock() + float(wait_timeout_s)

    def at_cap() -> bool:
        return max_points is not None and leased >= int(max_points)

    while True:
        for slot_id in slot_ids:
            if stop_reason or at_cap():
                break
            if slot_id in in_flight:
                continue
            if not queue.snapshot().pending_point_ids:
                break
            generation = generations[slot_id] + 1
            try:
                lease_document = lease_point(worker_by_slot[slot_id], slot_id, generation)
            except PointDrainError as error:
                stop_reason = error.code
                stop_detail = error.detail or None
                break
            except Exception as error:  # noqa: BLE001 - a refused lease is a stop, not a crash
                stop_reason = f"LEASE_FAILED:{type(error).__name__}"
                stop_detail = str(error)
                break
            generations[slot_id] = generation
            leased += 1
            if journal is not None:
                journal.append_committed(
                    "POINT_LEASED",
                    f"{binding.batch_id}/POINT_LEASED/{lease_document['attempt_id']}",
                    {"point_id": lease_document["point_id"],
                     "attempt_id": lease_document["attempt_id"],
                     "worker_id": worker_by_slot[slot_id], "slot_id": slot_id,
                     "generation": generation,
                     "lease_sha256": lease_document.get("lease_sha256"),
                     "points_path": lease_document.get("points_path"),
                     "points_sha256": lease_document.get("points_sha256"),
                     "selection_sha256": binding.selection_sha256})
            try:
                run = spawn_worker(worker_by_slot[slot_id], slot_id, generation, lease_document)
            except Exception as error:  # noqa: BLE001 - a refused spawn is a stop, not a crash
                stop_reason = f"SPAWN_FAILED:{type(error).__name__}"
                stop_detail = str(error)
                break
            spawns.append({**run.as_document(), "point_id": lease_document["point_id"],
                           "attempt_id": lease_document["attempt_id"]})
            in_flight[slot_id] = (run, lease_document)
            if run.status != "ACTIVE":
                stop_reason = "SPAWN_NOT_ACTIVE"
                break
            if journal is not None:
                journal.append_committed(
                    "ATTEMPT_STARTED",
                    f"{binding.batch_id}/ATTEMPT_STARTED/{lease_document['attempt_id']}",
                    {"point_id": lease_document["point_id"],
                     "attempt_id": lease_document["attempt_id"],
                     "worker_id": worker_by_slot[slot_id], "slot_id": slot_id,
                     "generation": generation, "pid": run.pid,
                     "points_sha256": lease_document.get("points_sha256"),
                     "lease_sha256": lease_document.get("lease_sha256")})

        stopped_at_cap = at_cap() and not in_flight
        if stop_reason or stopped_at_cap or not in_flight:
            break

        progressed = False
        for slot_id in list(in_flight):
            run, lease_document = in_flight[slot_id]
            result_path = Path(run.result_path)
            if not result_path.exists():
                if worker_alive is not None and not worker_alive(run):
                    # The Worker is gone and left no result: record the attempt as the
                    # infrastructure failure it is, report the station readback and stop, rather
                    # than waiting out the campaign's whole budget for a document that cannot come.
                    readback = station_readback(run.station_root) if station_readback else {}
                    released = release_worker(run.worker_id, slot_id) if release_worker else None
                    attempt = unfinished_attempt(
                        lease_document=lease_document, run=run,
                        code="WORKER_EXITED_WITHOUT_RESULT", released=released,
                        station_readback=readback)
                    attempts.append(commit_attempt(queue=queue, binding=binding, attempt=attempt,
                                                   lease=None, journal=journal))
                    releases.append({"worker_id": run.worker_id, "slot_id": slot_id,
                                     "generation": run.generation, "outcome": released,
                                     "station_readback": dict(readback)})
                    del in_flight[slot_id]
                    stop_reason = "WORKER_EXITED_WITHOUT_RESULT"
                    break
                continue
            worker_result, result_sha256 = read_worker_result(result_path)
            released = None
            if release_worker is not None:
                try:
                    released = release_worker(run.worker_id, slot_id)
                except PointDrainError as error:
                    stop_reason = error.code
                    break
            readback: Mapping[str, object] = {}
            if station_readback is not None:
                readback = station_readback(run.station_root)
            attempt = attempt_from_worker(
                lease_document=lease_document, worker_result=worker_result,
                worker_result_sha256=result_sha256, worker_result_path=result_path,
                evidence_root=evidence_root)
            attempt = replace(attempt, released=released, station_readback=readback)
            lease = _active_lease(queue, attempt)
            attempt = commit_attempt(queue=queue, binding=binding, attempt=attempt, lease=lease,
                                     journal=journal)
            if attempt.committed:
                write_committed_point_document(
                    evidence_root=evidence_root, attempt=attempt, lease=lease)
            attempts.append(attempt)
            releases.append({"worker_id": run.worker_id, "slot_id": slot_id,
                             "generation": run.generation, "outcome": released,
                             "station_readback": dict(readback)})
            del in_flight[slot_id]
            progressed = True
            if readback and readback.get("clear") is False:
                stop_reason = "STATION_RESIDUE"
                break
            if attempt.infrastructure_code is not None:
                stop_reason = attempt.infrastructure_code
                break
        if stop_reason:
            break
        stopped_at_cap = at_cap() and not in_flight
        if stopped_at_cap:
            break
        if not progressed:
            if clock() >= deadline:
                stop_reason = "DRAIN_TIMEOUT"
                break
            sleep(poll_s)

    return DrainReport(attempts=tuple(attempts), spawns=tuple(spawns),
                       releases=tuple(releases), stop_reason=stop_reason,
                       stopped_at_cap=stopped_at_cap, stop_detail=stop_detail)
