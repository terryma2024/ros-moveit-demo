"""The macOS MPS W2 campaign entry point.

`mujoco_parallel_batch` is the Linux container path: it requires a broker image, a CUDA device and
`proc_fd_unix`. This is its macOS counterpart, and it exists because the v4 contract had no
executable entry point at all — the schema, the broker, the IPC, the supervisor, the registry and
the recovery were each tested but never driven together outside a test.

What it does, in the design's order:

1. read-only inventory, so a duplicate claim, endpoint or campaign directory stops the run before
   anything is spawned;
2. the real start guard, in its own process, because the accelerator probe imports torch;
3. the supervisor claim and the private campaign root;
4. one broker bootstrap that loads the real model set on MPS through the detector factory, on a
   single execution lane, and publishes a ready receipt;
5. two workers spawned by the supervisor, each writing a registered ACK before it runs;
6. the composed campaign's one-time admission for every response;
7. exact cleanup, with the durable receipt cleared only when cleanup is proven complete.

The command emits one JSON document on stdout so the ledger can quote it directly, and it exits
non-zero when the run is not a pass.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from dataclasses import dataclass
from typing import Callable

from ..parallel_batch.campaign_supervisor import ACTIVE, CampaignSupervisor
from ..parallel_batch.contracts import (
    ContractError,
    ParallelRuntimeConfigV4,
    ParallelRuntimeConfigV5,
    ParallelRuntimeConfigV6,
    resolve_execution_route,
)
from ..parallel_batch import point_drain
from ..parallel_batch.inference_registry import InferenceRegistry
from ..parallel_batch.macos_w2_campaign import (
    CampaignPorts,
    MacosW2Campaign,
    MacosW2CampaignError,
    read_inventory,
)
from ..parallel_batch.queue import DurablePointQueue
from ..parallel_batch.start_guard import CAMPAIGN_GUARD_EPOCH, FAIL
from ..parallel_batch.start_guard_probe import (
    GUARD_RESULT_FD_VARIABLE,
    UNSET_PROBE,
    GuardHandoverRefused,
    compose_darwin_start_guard,
    consume_guard_handover,
    darwin_guard_scope,
    publish_guard_handover,
    run_campaign_start_guard,
)
from ..parallel_batch.w1_composition import (
    MPS_W1_FIRST_PASS,
    MPS_W1_FULL_RESTART_RETRY,
    W1_FIRST_PASS_BATCH_KIND,
    W1_RETRY_BATCH_KIND,
    compose_w1_first_pass,
    compose_w1_retry,
)
from ..parallel_batch.w2_composition import (
    CompositionError,
    compose_w2_campaign,
    load_execution_config_for_schema,
)
from ..runtime.unix_address import PRIVATE_TMP, DarwinPrivatePathUnixAddress

#: The v4 exact-W2 profile this module is the entry point for.
MPS_W2_FIRST_PASS = "MPS_W2_FIRST_PASS"
W2_FIRST_PASS_BATCH_KIND = "FIRST_PASS"


#: The worker child module, spawned as `python -m so101_demo.cli.macos_w2_worker`.
_WORKER_MODULE = "so101_demo.cli.macos_w2_worker"


def lease_worker_execution(*, queue, binding, worker_id: str, slot_id: str,
                           evidence_root: Path, input_sha256: str,
                           deadline_s: float = 240.0, generation: int = 1,
                           model_id: str = "yolo", attempt_count: int = 3,
                           tamper_input_sha256: bool = False,
                           duplicate_probe: bool = False,
                           execution_profile: str | None = None,
                           batch_kind: str | None = None,
                           schema_version: int | None = None,
                           lease_name: str | None = None,
                           point_id: str | None = None,
                           journal=None) -> dict:
    """Turn one queue lease into the single point file a Worker is allowed to execute.

    The Worker receives a lease document that carries the *single-point* input path and digest
    instead of the installed catalog, so "one lease executes one point" is a fact of the document
    the Worker reads rather than a convention its argv has to respect. The queue is the only issuer
    of the point: `point_id` can confirm the queue's choice but never select a different one.
    """

    return point_drain.write_lease_document(
        queue=queue, binding=binding, worker_id=worker_id, slot_id=slot_id,
        evidence_root=evidence_root, input_sha256=input_sha256, deadline_s=deadline_s,
        generation=generation, model_id=model_id, attempt_count=attempt_count,
        tamper_input_sha256=tamper_input_sha256, duplicate_probe=duplicate_probe,
        execution_profile=execution_profile, batch_kind=batch_kind,
        schema_version=schema_version, lease_name=lease_name, point_id=point_id, journal=journal)


def build_worker_leases(*, plan, batch_id: str, evidence_root: Path,
                         input_sha256: str, deadline_s: float = 240.0,
                         tamper_input_sha256: bool = False,
                         duplicate_probe: bool = False,
                         worker_ids: tuple[str, ...] | None = None,
                         binding=None, queue=None, generation: int = 1) -> dict[str, dict]:
    """Write each Worker's lease document from the durable queue, one point per Worker.

    There is no capacity-only form left: a lease that carries no single-point input is a lease the
    Worker refuses (`POINTS_PATH_MISSING`), which is exactly the gap Task 11's live gate found. The
    frame is created once; a later run reuses it rather than rewriting evidence.
    """

    if binding is None or queue is None:
        raise MacosW2CampaignError("SELECTION_QUEUE_REQUIRED", "a binding and a queue are required")
    # One Worker per capacity slot: exact W2 creates two, each W1 profile exactly one.
    if worker_ids is None:
        worker_ids = tuple(f"w{index + 1}" for index in range(len(plan.slots.slot_ids)))
    leases: dict[str, dict] = {}
    for index, worker_id in enumerate(worker_ids):
        slot_id = plan.slots.slot_ids[index] if index < len(plan.slots.slot_ids) else (
            f"slot-{index}")
        leases[worker_id] = lease_worker_execution(
            queue=queue, binding=binding, worker_id=worker_id, slot_id=slot_id,
            evidence_root=evidence_root, input_sha256=input_sha256, deadline_s=deadline_s,
            generation=generation, tamper_input_sha256=tamper_input_sha256,
            duplicate_probe=duplicate_probe,
            execution_profile=getattr(plan, "execution_profile", None),
            batch_kind=getattr(plan, "batch_kind", None),
            schema_version=getattr(plan, "schema_version", None),
            lease_name=f"{worker_id}-lease-{int(generation):02d}.json")
    return leases


def open_campaign_journal(*, evidence_root: Path, campaign_id: str, batch_id: str):
    """Open the batch's standard journal and commit CAMPAIGN_STARTED before anything runs.

    The macOS W1/W2 compositions reuse the existing `CoordinatorJournal`: the coordinator is the
    single writer, every returned event is already fsynced *and* covered by a published committed
    watermark, and the projection side reads that prefix instead of polling terminal files.
    """

    from ..parallel_batch.journal import CoordinatorJournal

    journal = CoordinatorJournal.create(Path(evidence_root) / "journal", batch_id)
    try:
        journal.append_committed(
            "CAMPAIGN_STARTED",
            f"{campaign_id}/CAMPAIGN_STARTED",
            {
                "campaign_id": campaign_id,
                "batch_id": batch_id,
                "schema_version": journal.schema_version,
            },
        )
    except BaseException:
        journal.close()
        raise
    return journal


def commit_campaign_terminal(journal, *, outcome: str, cleanup_complete: bool) -> None:
    """Commit BATCH_TERMINAL, and CLEANUP_COMMITTED only when cleanup is proven complete."""

    journal.append_committed(
        "BATCH_TERMINAL", f"{journal.batch_id}/BATCH_TERMINAL", {"outcome": str(outcome)}
    )
    if cleanup_complete:
        journal.append_committed(
            "CLEANUP_COMMITTED",
            f"{journal.batch_id}/CLEANUP_COMMITTED",
            {"cleanup_complete": True},
        )



def bind_worker_requests(campaign, leases: dict[str, dict], *, ready,
                         deadline_s: float = 300.0,
                         progress_probe_count: int = 3) -> None:
    """Bind every id the Workers will use *before* any of them is served.

    An id that was never bound is refused by the one-time table, so this is the admission gate - and
    it binds the `{attempt_id}-{model_id}` ids the Worker derives, not a parallel set. The Worker's
    IPC round trips are bound per generation too: a Worker spawned again for the next point must not
    replay an id the table already consumed.
    """

    for worker_id, document in sorted(leases.items()):
        for attempt_id in document["attempt_ids"]:
            campaign.request_binding(
                request_id=f"{attempt_id}-{document['model_id']}", slot_id=document["slot_id"],
                point_id=document["point_id"], attempt=1,
                input_sha256=document["input_sha256"], deadline_s=deadline_s,
                broker_pid=ready.broker_pid, broker_birth_identity=ready.broker_birth_identity)
        for index in range(int(progress_probe_count)):
            campaign.request_binding(
                request_id=point_drain.worker_progress_request_id(
                    worker_id=worker_id, generation=int(document["worker_generation"]),
                    index=index),
                slot_id=document["slot_id"], point_id=document["point_id"], attempt=1,
                input_sha256=document["input_sha256"], deadline_s=deadline_s,
                broker_pid=ready.broker_pid, broker_birth_identity=ready.broker_birth_identity)


def campaign_status(*, cleanup_complete: bool, results, workers, served, refused,
                    points) -> str:
    """The exact-W2 verdict: the same rule `campaign_verdict` applies to every route.

    It requires the whole happy path *and* the executed point set: cleanup complete, one result
    document per Worker spawn, every spawn `ACTIVE`, at least six served requests whose devices are
    exactly `["mps"]`, no refused request at all, and `points["complete"]` - every selected point
    executed exactly once, with its evidence, and no unselected point attempted. A verdict that
    asserted nothing about the point set is what let Task 11's empty campaigns report PASS.
    """

    spec = CampaignRouteSpec(
        execution_profile=MPS_W2_FIRST_PASS, batch_kind=W2_FIRST_PASS_BATCH_KIND,
        config_class=ParallelRuntimeConfigV4, module="so101_demo.cli.macos_w2_campaign",
        worker_ids=("w1", "w2"), default_point_ids=("p1", "p2"), minimum_served=6,
        composer=compose_w2_campaign)
    return campaign_verdict(spec=spec, cleanup_complete=cleanup_complete, results=results,
                            workers=workers, served=served, refused=refused, points=points)


def summarize_per_slot_pick_place(*, evidence_root: Path, workers=("w1", "w2")) -> dict:
    """Read each slot's pick-place evidence back out of its own directory tree, defensively.

    A reader should not have to walk the tree to learn whether a slot executed its points, so the
    campaign document carries this summary. Missing directories are reported as zeros rather than
    raising: a slot that produced nothing is a fact worth recording, not a reason to lose the run.

    An executed point is one the batch runner left its terminal `point-result.json` behind for - the
    document the campaign's own committed point result names as the attempt's evidence manifest -
    or, for a partial tree, one whose dynamic-execution manifest reached `DONE` without a failure.
    A `contacts` entry still requires the latter: only a completed pick-place carries those items.
    """

    summary: dict[str, dict] = {}
    for worker_id in workers:
        # One station root per lease, so the slot's evidence is everything under its own station
        # directory - the `pick` root of each attempt included, never a single fixed one.
        station_root = Path(evidence_root) / f"{worker_id}-station"
        manifests = sorted(glob.glob(
            f"{station_root}/**/dynamic-execute-manifest.json", recursive=True))
        points = sorted(glob.glob(f"{station_root}/**/point-result.json", recursive=True))
        executed: set[str] = set()
        contacts = []
        for manifest in manifests:
            try:
                entry = json.loads(Path(manifest).read_text())
            except (OSError, ValueError):
                continue
            if entry.get("current_state") == "DONE" and entry.get("failure") is None:
                point = Path(manifest).parent.parent.name
                executed.add(point)
                sample = (entry.get("final_samples") or [{}])[0]
                contacts.append({"point": point,
                                 # the catalog id, without the batch runner's ordinal prefix
                                 "point_id": point.split("-", 1)[1] if "-" in point else point,
                                 "simulation_step": sample.get("simulation_step"),
                                 "table_contact": sample.get("table_contact"),
                                 "max_normal_force_n": sample.get("maximum_normal_force_n"),
                                 # The items the plan names for each batch, taken from the manifest so a
                                 # reader sees them in the campaign document rather than by walking
                                 # directories: the planning-scene shadow, the release marker sequence,
                                 # the detach/transition count and where the cup ended up.
                                 "planning_scene_readback": entry.get("planning_scene_readback"),
                                 "release_marker_sequence": entry.get("release_marker_sequence"),
                                 "transition_count": entry.get("transition_count"),
                                 # The point's state sequence, which is where the approach, grasp,
                                 # lift, place and release phases are itemised for this point.
                                 "state_trace": list(entry.get("state_trace") or ()),
                                 "planned_states": sorted((entry.get("resolved_targets") or {}).keys()),
                                 "final_cup_position_world_m": sample.get("cup_position_world_m"),
                                 "final_cup_orientation_world_xyzw": sample.get("cup_orientation_world_xyzw"),
                                 "left_right_contacts": [sample.get("left_contact_count"),
                                                         sample.get("right_contact_count")]})
        # A point that ran - passed or failed - leaves the batch runner's terminal per-point
        # document in its own point directory, and the drain commits an attempt on exactly such a
        # document (see `point_drain.read_point_evidence`). The dynamic manifest above exists only
        # for the points that reached the pick-place stages, so counting executions from it alone
        # made a retry batch whose single point died at RGBD perception - `retry-001` of
        # campaign-e94a4b74 - read as having executed nothing, while its committed
        # `point-results/sample_05_near_center.json` named that very point. A point directory with
        # neither document was never executed and is not listed: a batch that ran nothing still
        # reports nothing.
        executed.update(Path(result).parent.name for result in points)
        failure_codes = set()
        for result in points:
            try:
                failure_codes.add(json.loads(Path(result).read_text()).get("failure_code"))
            except (OSError, ValueError):
                failure_codes.add("UNREADABLE_POINT_RESULT")
        summary[worker_id] = {
            "executed_points": sorted(executed),
            "manifests": len(manifests),
            "point_results": len(points),
            "failure_codes": sorted(code for code in failure_codes if code is not None),
            "contacts": contacts,
            "evidence_root": str(station_root),
            "point_result_paths": points,
        }
    return summary


#: The operations this composition implements; anything else is refused rather than served.
IMPLEMENTED_OPERATIONS = frozenset({"broker.infer", "worker.progress", "worker.result"})


def _declared_digest(serialized: object) -> str | None:
    """Read the digest a Worker declared, defensively: anything unreadable is *not* a match."""

    try:
        document = serialized
        if isinstance(document, (bytes, bytearray, str)):
            document = json.loads(document)
        return (document or {}).get("input_sha256")
    except Exception:  # noqa: BLE001 - an unreadable digest must not become a pass
        return None


def admission_decision(*, operation: str, request_id: str, serialized_request: object,
                       consumed_ids, bound_digest: str, cancelled_ids=()) -> dict | None:
    """The campaign's admission rule, as a pure function so it can be tested without a socket.

    Returns a refusal mapping the v4 server turns into a non-OK response, or `None` to serve. The
    order matters: an unimplemented operation is refused before anything else, and a repeated id is
    refused before it can consume the table a second time.
    """

    if operation not in IMPLEMENTED_OPERATIONS:
        return {"error": {"code": "UNKNOWN_OPERATION", "detail": operation}}
    if request_id in cancelled_ids:
        # A cancelled request's result is forfeit: it is refused whether or not it was ever consumed,
        # which is the safety-cancel property the Coordinator owns in the design.
        return {"error": {"code": "CANCELLED", "detail": request_id}}
    if request_id in consumed_ids:
        return {"error": {"code": "DUPLICATE_REQUEST", "detail": request_id}}
    if operation == "broker.infer":
        declared = _declared_digest(serialized_request)
        if declared != bound_digest:
            return {"error": {"code": "SNAPSHOT_MISMATCH", "detail": f"{request_id}: {declared!r}"}}
    return None


def serve_and_admit(campaign, *, request_id: str, candidates: int, device: str,
                    served: list, broker_pid: int, broker_birth_identity: int) -> dict | None:
    """Record one served response and consult the one-time table for it *now*.

    The table is the admission gate for every response, and it is also a bounded table of
    *outstanding* requests. Deferring every admission to the end of a campaign drains that bound:
    the drain issues one lease per point, and the registry refuses a new binding once its pending
    set is full (`REGISTRY_CAPACITY`), which is how the first seven-point drain stopped after five
    spawns. Admitting each response as it is served keeps the table's semantics exactly - nothing is
    served that the table will not admit - while keeping its pending set bounded.
    """

    decision = campaign.admit_response(
        request_id, broker_pid=broker_pid, broker_birth_identity=broker_birth_identity)
    entry = {"request_id": request_id, "candidates": candidates, "device": device,
             "admitted": bool(decision.accepted), "admission_reason": decision.reason}
    served.append(entry)
    if not decision.accepted:
        return {"error": {"code": "RESULT_NOT_ADMITTED", "detail": decision.reason}}
    return None


def served_admission_split(served) -> tuple[list[dict], list[dict]]:
    """The admitted and refused responses of one campaign, from the decisions made while serving."""

    admitted = [{"request_id": entry["request_id"], "reason": entry.get("admission_reason")}
                for entry in served if entry.get("admitted")]
    refused = [{"request_id": entry["request_id"], "reason": entry.get("admission_reason")}
               for entry in served if not entry.get("admitted")]
    return admitted, refused


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="so101_macos_w2_campaign",
        description="Run one exact-W2 macOS MPS campaign with the published model set.",
    )
    parser.add_argument("--config", type=Path, required=True,
                        help="the schema-v4 macOS MPS document")
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--point-id", action="append", default=[],
                        help="repeatable; exact W2 keeps two slots regardless")
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=None,
                        help="the immutable point catalog the selection is frozen from; the "
                             "installed document is used when this is omitted")
    parser.add_argument("--catalog-sha256", default=None,
                        help="the catalog digest the selection must match; drift is refused")
    parser.add_argument("--retry-root", type=Path, default=None,
                        help="v5 only: the prior campaign evidence root whose committed business "
                             "FAILED point this retry is bound to")
    parser.add_argument("--yolo-weights", type=Path, required=True)
    parser.add_argument("--grounded-root", type=Path, required=True)
    parser.add_argument("--duplicate-probe", action="store_true",
                        help="have each Worker repeat one request id, so the one-time table's refusal "
                             "is exercised; off by default, because a refused request makes the "
                             "campaign verdict INCOMPLETE by construction")
    parser.add_argument("--cancel-second-worker-after-served", type=int, default=0,
                        help="fault injection: after this many served requests, cancel every "
                             "remaining request of the second Worker, whose results are then forfeit")
    parser.add_argument("--tamper-snapshot-sha", action="store_true",
                        help="fault injection: tell the Workers to declare a wrong snapshot digest, "
                             "so the bound-digest check must refuse them")
    parser.add_argument("--stall-serve-after", type=int, default=0,
                        help="fault injection: delay this request's answer beyond the Worker's "
                             "deadline, so a timeout must be refused rather than admitted")
    parser.add_argument("--worker-deadline-s", type=float, default=240.0)
    parser.add_argument("--crash-broker-after-served", type=int, default=0,
                        help="fault injection: signal the owned Broker child exactly once, after "
                             "this many served requests (0 disables it)")
    parser.add_argument("--skip-models", action="store_true",
                        help="compose and pre-flight only; never a pass")
    return parser


def _as_rgb8(value):
    """Coerce a warm-up input into the (H, W, 3) uint8 array a DetectionFrame requires.

    The bootstrap builds its default warm-up input as a torch tensor in (N, C, H, W); the frame
    type owns a stricter contract, and adapting here keeps either shape usable without loosening
    that contract.
    """

    import numpy as np

    if hasattr(value, "detach"):  # a torch tensor
        value = value.detach().to("cpu").numpy()
    array = np.asarray(value)
    if array.ndim == 4:
        array = array[0]
    if array.ndim == 3 and array.shape[0] in (1, 3, 4) and array.shape[2] not in (1, 3, 4):
        array = np.transpose(array, (1, 2, 0))
    if array.ndim == 3 and array.shape[2] == 4:
        array = array[:, :, :3]
    if array.dtype != np.uint8:
        array = np.clip(array * 255 if array.max() <= 1.0 else array, 0, 255).astype(np.uint8)
    return np.ascontiguousarray(array)


def _inventory(campaign_id: str, evidence_root: Path) -> dict:
    supervisor_root = evidence_root / "supervisor"
    inventory = read_inventory(
        claim_path=supervisor_root / "campaign-claim.lock",
        ipc_base=PRIVATE_TMP / f"so101-ipc-{os.getuid()}",
    )
    return {
        "campaign_id": campaign_id,
        "claim_held": inventory.claim_held,
        "live_endpoints": list(inventory.live_endpoints),
        "owned_processes": list(inventory.owned_processes),
        "existing_campaign_dirs": list(inventory.existing_campaign_dirs),
        "clean": inventory.clean,
    }


def _model_factories(*, yolo_weights: Path, grounded_root: Path):
    """The real published models, built on MPS through the production detector factory."""

    from ..adapters.perception.detector_factory import (
        DetectorFactoryOptions,
        build_detector,
    )
    from ..adapters.perception.grounded_sam import GroundedSamThresholds
    from ..core.detection import DetectionQuery
    from ..parallel_batch.contracts import ParallelRuntimeConfigV4

    def build(model_id: str):
        def factory():
            if model_id == "yolo":
                options = DetectorFactoryOptions(
                    backend="yolo_seg", requested_device="mps", allow_cpu_fallback=False,
                    yolo_weights_path=yolo_weights,
                    yolo_weights_sha256=ParallelRuntimeConfigV4.FROZEN_YOLO_WEIGHTS_SHA256,
                    yolo_model_id="plastic-cup-yolo11n-seg-v1", yolo_imgsz=640)
            else:
                options = DetectorFactoryOptions(
                    backend="grounded_sam", requested_device="mps", allow_cpu_fallback=False,
                    grounded_model_root=grounded_root,
                    grounded_manifest_sha256=(
                        ParallelRuntimeConfigV4.FROZEN_GROUNDED_SAM_MANIFEST_SHA256),
                    grounded_thresholds=GroundedSamThresholds.defaults())
            detector = build_detector(options=options).detector

            class Warmable:
                """The detector plus the call shape a broker warm-up uses."""

                weights_sha256 = f"real-{model_id}"
                config_sha256 = "real-config"
                runtime_device = detector.runtime_device

                def _modules(self):
                    found = []
                    for attribute in ("_model", "_grounding_model", "_sam_model"):
                        candidate = getattr(detector, attribute, None)
                        if candidate is not None and hasattr(candidate, "parameters"):
                            found.append(candidate)
                    return found

                def parameters(self):
                    collected = []
                    for module in self._modules():
                        collected.extend(module.parameters())
                    return collected

                def query(self):
                    return DetectionQuery(class_id="cup")

                def __call__(self, frame):
                    # The broker bootstrap hands the warm-up value straight back to the model, so
                    # this must accept whatever the caller's warm-up input is: a DetectionFrame or
                    # a bare RGB array.
                    if not hasattr(frame, "rgb8"):
                        from ..core.detection import DetectionFrame as _Frame

                        frame = _Frame(rgb8=_as_rgb8(frame), source_stamp_ns=1,
                                       source_frame_id="warmup")
                    detector.detect(frame, self.query())
                    modules = self._modules()
                    if not modules:
                        raise RuntimeError(f"no torch modules on {model_id}")
                    return next(iter(modules[0].parameters())).detach().sum().reshape(1)

                def detect(self, frame, _query=None):
                    return detector.detect(frame, self.query())

            return Warmable()

        return factory

    return {"yolo": build("yolo"), "grounded-sam": build("grounded-sam")}


# --------------------------------------------------------------------------------------
# the guard phase: one fresh observation, handed over through this process's own pipe
# --------------------------------------------------------------------------------------

#: Which phase this process is in. The guard phase runs before the campaign child exists and is
#: the only phase allowed to import the accelerator probe; the broker phase is entered through
#: this process's own inherited pipe, or it is refused.
GUARD_PHASE_VARIABLE = "SO101_CAMPAIGN_PHASE"
GUARD_PHASE = "guard"
BROKER_PHASE = "broker"


def campaign_guard_scope(*, batch_id: str, worker_count: int,
                         epoch: int = CAMPAIGN_GUARD_EPOCH):
    """The campaign-level scope: epoch 0, the real owner identity, the approved MPS selector.

    Per-spawn epochs start at 1, so a campaign preflight can never be mistaken for a spawn
    admission. The owner facts (PID and birth identity) are the same on both sides of the `exec`,
    which is what makes them checkable after it rather than assumed.
    """

    return darwin_guard_scope(batch_id=batch_id, worker_count=worker_count, epoch=epoch)


def guard_document(result) -> dict:
    """The audit projection of one guard result. It is written down, never read back as input."""

    checks = dict(result.checks)
    head = checks.get("mps_headroom")
    reason = None
    for name in ("mps_accelerator", "probe", "ram", "cpu_capacity", "mps_headroom"):
        check = checks.get(name)
        if check is not None and check.status == FAIL:
            reason = check.reason
            break
    if reason is None:
        reason = head.reason if head is not None else "START_GUARD_OK"
    return {
        "status": result.status,
        "reason": reason,
        "epoch": result.scope.epoch,
        "scope": {
            "batch_id": result.scope.batch_id,
            "epoch": result.scope.epoch,
            "owner_pid": result.scope.owner_pid,
            "owner_starttime_ticks": result.scope.owner_starttime_ticks,
            "gpu_selector": result.scope.gpu_selector,
            "worker_count": result.scope.worker_count,
        },
        "cleanup_state": result.cleanup_state,
        "available_bytes": None if head is None else head.observed,
        "cutoff": None if head is None else head.cutoff,
        "admission_kind": "unified-memory-proxy" if head is not None else None,
        "checks": {
            name: {"status": check.status, "reason": check.reason, "observed": check.observed,
                   "cutoff": check.cutoff, "unit": check.unit}
            for name, check in checks.items()
        },
    }


def run_guard_phase(arguments, *, policy, batch_id, worker_count, probe=UNSET_PROBE, state_root=None):
    """Take one fresh campaign observation and record it for audit.

    The on-disk copy is written on every attempt - PASS, WARN or FAIL - and it is never an input:
    a `start-guard.json` left by an earlier epoch, a different owner or a tampered run cannot
    admit anything, and it cannot block a healthy fresh probe either.
    """

    result = run_campaign_start_guard(policy=policy, batch_id=batch_id, worker_count=worker_count,
                                      probe=probe, state_root=state_root)
    document = guard_document(result)
    root = Path(arguments.evidence_root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "start-guard.json").write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    return document, result


def broker_phase_guard(environment, *, scope, max_age_s, forbidden_modules=("torch",),
                       clock=time.monotonic):
    """Read the one-shot admission from the inherited pipe this process created, or refuse.

    Nothing is read from disk here, whatever a `start-guard.json` says. A missing descriptor, a
    scope/owner/epoch mismatch, an expired result, a refusal or a guard-phase import that survived
    the `exec` are all refusals by name.
    """

    raw = environment.get(GUARD_RESULT_FD_VARIABLE)
    if raw is None or not str(raw).strip().isdigit():
        raise GuardHandoverRefused(
            "GUARD_HANDOVER_MISSING",
            "the admission must arrive through the inherited pipe this process created")
    return consume_guard_handover(int(raw), scope=scope, max_age_s=max_age_s, clock=clock,
                                  forbidden_modules=forbidden_modules)


def _audit_guard(arguments) -> dict | None:
    """The on-disk guard record, read defensively and only for the evidence document."""

    path = Path(arguments.evidence_root) / "start-guard.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


# --------------------------------------------------------------------------------------
# the closed route table: one entry point per approved profile
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CampaignRouteSpec:
    """One row of the support matrix, wired to the entry point that executes it."""

    execution_profile: str
    batch_kind: str
    config_class: type
    module: str
    worker_ids: tuple[str, ...]
    default_point_ids: tuple[str, ...]
    minimum_served: int
    composer: Callable[..., object]

    @property
    def worker_count(self) -> int:
        return len(self.worker_ids)

    @property
    def pass_label(self) -> str:
        return "W2_CAMPAIGN_PASS" if self.worker_count == 2 else "N1_CAMPAIGN_PASS"

    @property
    def incomplete_label(self) -> str:
        return "W2_CAMPAIGN_INCOMPLETE" if self.worker_count == 2 else "N1_CAMPAIGN_INCOMPLETE"


ROUTE_SPECS: tuple[CampaignRouteSpec, ...] = (
    CampaignRouteSpec(
        execution_profile=MPS_W2_FIRST_PASS, batch_kind=W2_FIRST_PASS_BATCH_KIND,
        config_class=ParallelRuntimeConfigV4, module="so101_demo.cli.macos_w2_campaign",
        worker_ids=("w1", "w2"), default_point_ids=("p1", "p2"), minimum_served=6,
        composer=compose_w2_campaign),
    CampaignRouteSpec(
        execution_profile=MPS_W1_FULL_RESTART_RETRY, batch_kind=W1_RETRY_BATCH_KIND,
        config_class=ParallelRuntimeConfigV5, module="so101_demo.cli.macos_n1_retry",
        worker_ids=("w1",), default_point_ids=("p1",), minimum_served=3,
        composer=compose_w1_retry),
    CampaignRouteSpec(
        execution_profile=MPS_W1_FIRST_PASS, batch_kind=W1_FIRST_PASS_BATCH_KIND,
        config_class=ParallelRuntimeConfigV6, module="so101_demo.cli.macos_n1_first_pass",
        worker_ids=("w1",), default_point_ids=("p1",), minimum_served=3,
        composer=compose_w1_first_pass),
)


def route_spec(execution_profile: str) -> CampaignRouteSpec:
    """The one entry point that executes a profile. There is no generic fallback."""

    for spec in ROUTE_SPECS:
        if spec.execution_profile == execution_profile:
            return spec
    raise ContractError(f"EXECUTION_PROFILE_UNKNOWN: {execution_profile}")


class RefusedRun(Exception):
    """A refusal before anything was spawned. It is reported as evidence, not as a traceback."""

    def __init__(self, stage: str, detail: str, exit_code: int = 1) -> None:
        super().__init__(f"{stage}: {detail}")
        self.stage = stage
        self.detail = detail
        self.exit_code = exit_code


def run_routed(*, argv, arguments, execution_profile: str) -> int:
    """Load the document, resolve the closed route, compose the plan and drive the campaign.

    The routing key is `(schema_version, execution_profile, batch_kind, worker_count)`. The profile
    comes from the entry point, the batch kind from the profile it names, the schema and the
    worker count from the document - and a profile is never inferred from how many points were
    selected.
    """

    spec = route_spec(execution_profile)
    document: dict = {"status": "PENDING", "execution_profile": spec.execution_profile}
    try:
        config = load_execution_config_for_schema(arguments.config)
        if not isinstance(config, spec.config_class):
            raise RefusedRun(
                "config",
                "CONFIG_SCHEMA_MISMATCH: "
                f"{execution_profile} requires {spec.config_class.__name__}, "
                f"not {type(config).__name__}")
        route = resolve_execution_route(
            schema_version=config.schema_version, execution_profile=spec.execution_profile,
            batch_kind=spec.batch_kind, worker_count=config.worker_count)
        plan = spec.composer(
            config=config, config_path=arguments.config, campaign_id=arguments.campaign_id,
            batch_id=arguments.batch_id,
            selected_point_ids=tuple(arguments.point_id) or spec.default_point_ids,
            evidence_root=arguments.evidence_root)
    except RefusedRun:
        raise
    except (ContractError, CompositionError) as error:
        raise RefusedRun("config", str(error)) from error

    document["route"] = {
        "schema_version": route.schema_version,
        "execution_profile": str(route.execution_profile),
        "batch_kind": str(route.batch_kind),
        "worker_count": route.worker_count,
        "module": spec.module,
        "config_path": str(arguments.config),
        "config_sha256": plan.config_sha256,
    }
    inventory = _inventory(arguments.campaign_id, arguments.evidence_root)
    document["inventory"] = inventory
    if not inventory["clean"]:
        raise RefusedRun(
            "inventory",
            "a claim, endpoint or campaign directory is already present; "
            "this run will not clean up someone else's resources",
            exit_code=2)
    document["plan"] = plan.to_document()
    if arguments.skip_models:
        document.update(status="COMPOSED_ONLY", stage="compose",
                        detail="--skip-models was set, so this is never a pass")
        print(json.dumps(document, indent=2, sort_keys=True))
        return 3
    return _drive_campaign(arguments, argv, plan, spec, document)


def _guard_admission(arguments, argv, plan, spec, document):
    """The fresh campaign admission, handed over through this process's own pipe.

    Returns the admitted result in the broker phase; in the guard phase it either refuses (and
    returns ``None`` after writing the refusal document) or replaces this process with the broker
    phase. The on-disk record is written for audit either way and is never read as input.
    """

    scope = campaign_guard_scope(batch_id=arguments.batch_id, worker_count=plan.worker_count)
    if os.environ.get(GUARD_PHASE_VARIABLE) != BROKER_PHASE:
        read_fd, write_fd = os.pipe()
        audit, result = run_guard_phase(
            arguments, policy=plan.config.start_guard, batch_id=arguments.batch_id,
            worker_count=plan.worker_count,
            state_root=arguments.evidence_root / "start-guard-state")
        print(json.dumps({"phase": "start-guard", **audit}, indent=2, sort_keys=True), flush=True)
        if result.status == FAIL or result.cleanup_state != "CLEAR":
            for descriptor in (read_fd, write_fd):
                try:
                    os.close(descriptor)
                except OSError:  # pragma: no cover - already closed
                    pass
            document.update(status="REFUSED", stage="start_guard", start_guard=audit)
            print(json.dumps(document, indent=2, sort_keys=True))
            return None
        publish_guard_handover(write_fd, result)
        # The admission travels through this pipe and nowhere else: the descriptor is made
        # inheritable and the process is replaced, so the guard phase's interpreter - including
        # its torch import - does not survive into the broker phase.
        os.set_inheritable(read_fd, True)
        child_environment = dict(os.environ)
        child_environment[GUARD_RESULT_FD_VARIABLE] = str(read_fd)
        child_environment[GUARD_PHASE_VARIABLE] = BROKER_PHASE
        child_environment["PYTORCH_ENABLE_MPS_FALLBACK"] = "0"
        os.execve(sys.executable, [sys.executable, "-m", spec.module, *argv], child_environment)
        raise AssertionError("unreachable")  # pragma: no cover - execve never returns

    document["start_guard"] = _audit_guard(arguments)
    admitted = broker_phase_guard(os.environ, scope=scope,
                                  max_age_s=plan.start_guard_timeout_s)
    document["start_guard_admission"] = {"status": admitted.status,
                                         "epoch": admitted.scope.epoch,
                                         "source": "inherited-pipe"}
    return admitted


# --------------------------------------------------------------------------------------
# the immutable selection and the durable queue: bound before anything is spawned
# --------------------------------------------------------------------------------------


def installed_catalog_path() -> Path:
    """The installed point catalog, which is what a service-resolved selection uses."""

    try:
        from ament_index_python.packages import get_package_share_directory

        return Path(get_package_share_directory("so101_demo_py")) \
            / point_drain.INSTALLED_CATALOG_RELATIVE
    except Exception as error:  # noqa: BLE001 - a missing catalog is a refusal, not a traceback
        raise RefusedRun("config", f"CATALOG_MISSING: {type(error).__name__}: {error}") from error


def selection_document(selection, *, catalog_path: Path, extras=None) -> dict:
    """The audit projection of the one selection this campaign executes.

    It is produced by the same function that writes `selection-binding.json`, so a first pass and a
    retry project the identical shape - including the retry's original selection/result chain and
    how it was verified - instead of the retry path crashing on a first-pass-only field.
    """

    return point_drain.selection_document_for(selection, catalog_path=catalog_path, extras=extras)


def bind_campaign_selection(*, arguments, plan, spec):
    """Freeze the selection binding and open the durable queue it drains.

    A first pass takes the ordered `--point-id` list (the four anchors are required by the binding
    contract, so a selection that omits them is refused by name rather than silently extended). A
    v5 retry takes exactly one point and must reference the prior campaign's committed business
    `FAILED` result; anything else - an unrun point, an infrastructure failure, an indeterminate
    point - is refused before a process exists. Returns the binding, its durable queue and the
    catalog path the binding was frozen from, which is what the selection document records.
    """

    from ..parallel_batch.selection import SelectionError, load_point_catalog

    retry = spec.batch_kind == W1_RETRY_BATCH_KIND
    point_ids = tuple(arguments.point_id)
    catalog_argument = getattr(arguments, "catalog", None)
    expected_catalog_sha256 = getattr(arguments, "catalog_sha256", None)
    try:
        if retry:
            # A retry binding is named one of two ways, and both must name an *original result*:
            # the prior campaign root (`--retry-root`, whose committed result document is re-read
            # and hashed) or the service's already-admitted chain (`--original-selection-sha256`
            # with `--original-result-sha256`, optionally with the original result document so its
            # bytes decide). There is no form that starts a retry without a named original result.
            retry_root = getattr(arguments, "retry_root", None)
            selection_sha = getattr(arguments, "original_selection_sha256", None)
            result_sha = getattr(arguments, "original_result_sha256", None)
            catalog_sha = getattr(arguments, "original_catalog_sha256", None)
            original_result = getattr(arguments, "original_result", None)
            original_batch_id = getattr(arguments, "original_batch_id", None)
            if len(point_ids) != 1:
                raise RefusedRun("selection", "RETRY_POINT_REQUIRED", exit_code=2)
            if retry_root is None and selection_sha is None and result_sha is None:
                raise RefusedRun(
                    "selection",
                    "RETRY_ROOT_REQUIRED: name the original chain with --retry-root or with "
                    "--original-selection-sha256 and --original-result-sha256",
                    exit_code=2)
            if retry_root is None and (selection_sha is None or result_sha is None):
                raise RefusedRun(
                    "selection",
                    "RETRY_ROOT_REQUIRED: --original-selection-sha256 and "
                    "--original-result-sha256 are both required without --retry-root",
                    exit_code=2)
            if original_batch_id is not None and original_batch_id == arguments.batch_id:
                raise RefusedRun("selection", "RETRY_BATCH_EXISTS", exit_code=2)
            extras = {"original_batch_id": original_batch_id}
            if retry_root is not None:
                source = point_drain.read_retry_source(prior_root=Path(retry_root),
                                                       point_id=point_ids[0])
                prior = point_drain.read_selection_document(
                    Path(retry_root) / point_drain.SELECTION_DOCUMENT_BASENAME)
                if str(prior["campaign_id"]) != arguments.campaign_id:
                    raise RefusedRun(
                        "selection",
                        f"RETRY_CAMPAIGN_MISMATCH: {prior['campaign_id']} != "
                        f"{arguments.campaign_id}", exit_code=2)
                if str(prior["batch_id"]) == arguments.batch_id:
                    raise RefusedRun("selection", "RETRY_BATCH_EXISTS", exit_code=2)
                # A digest named beside the root may only *confirm* what the root's own bytes say.
                for name, declared, recorded in (
                        ("original_selection_sha256", selection_sha,
                         str(prior["selection_sha256"])),
                        ("original_result_sha256", result_sha,
                         str(source["original_result_sha256"])),
                        ("original_catalog_sha256", catalog_sha,
                         str(prior["catalog_sha256"]))):
                    if declared is not None and declared != recorded:
                        raise RefusedRun(
                            "selection",
                            f"RETRY_SOURCE_MISMATCH: {name} {declared} != {recorded}",
                            exit_code=2)
                extras["original_batch_id"] = original_batch_id or str(prior["batch_id"])
                catalog_path = (Path(catalog_argument) if catalog_argument is not None
                                else Path(str(source["catalog_path"])))
                if (catalog_argument is not None and catalog_path.resolve()
                        != Path(str(source["catalog_path"])).resolve()):
                    raise RefusedRun("selection", "RETRY_CATALOG_MISMATCH", exit_code=2)
            else:
                catalog_path = (Path(catalog_argument) if catalog_argument is not None
                                else installed_catalog_path())
                source = point_drain.retry_source_from_hashes(
                    point_id=point_ids[0], original_selection_sha256=selection_sha,
                    original_result_sha256=result_sha,
                    original_catalog_sha256=(
                        catalog_sha if catalog_sha is not None
                        else load_point_catalog(catalog_path).sha256),
                    original_result_path=original_result,
                    original_batch_id=original_batch_id)
            extras["original_result_source"] = source.get("original_result_source")
            catalog = load_point_catalog(catalog_path)
            closure = point_drain.runtime_closure_sha256(
                catalog_path=catalog_path, catalog_sha256=catalog.sha256,
                config_sha256=plan.config_sha256)
            selection = point_drain.retry_binding(
                source=source, catalog_path=catalog_path, campaign_id=arguments.campaign_id,
                batch_id=arguments.batch_id, config_sha256=plan.config_sha256,
                runtime_closure_sha256=closure,
                expected_catalog_sha256=expected_catalog_sha256)
        else:
            extras = {}
            if not point_ids:
                raise RefusedRun("selection", "SELECTED_POINTS_REQUIRED", exit_code=2)
            catalog_path = (Path(catalog_argument) if catalog_argument is not None
                            else installed_catalog_path())
            catalog = load_point_catalog(catalog_path)
            closure = point_drain.runtime_closure_sha256(
                catalog_path=catalog_path, catalog_sha256=catalog.sha256,
                config_sha256=plan.config_sha256)
            selection = point_drain.first_pass_binding(
                catalog_path=catalog_path, point_ids=point_ids,
                campaign_id=arguments.campaign_id, batch_id=arguments.batch_id,
                config_sha256=plan.config_sha256, runtime_closure_sha256=closure,
                expected_catalog_sha256=expected_catalog_sha256)
    except (SelectionError, point_drain.PointDrainError) as error:
        raise RefusedRun("selection", str(error), exit_code=2) from error
    queue = DurablePointQueue(root=Path(arguments.evidence_root) / "queue", binding=selection)
    point_drain.write_selection_document(
        evidence_root=arguments.evidence_root, binding=selection, catalog_path=catalog_path,
        extras=extras)
    return selection, queue, catalog_path


def station_processes(station_root: str, *, ps_runner=None) -> list[dict]:
    """Processes whose own argv declares exactly this attempt's station root.

    The station launcher is passed `task_evidence_root:=<station root>`, and the root is unique to
    one lease under this campaign's evidence root, so a match is this campaign's process and not a
    stranger's. Nothing is signalled here.
    """

    import subprocess

    runner = _default_ps_runner if ps_runner is None else ps_runner
    token = f"task_evidence_root:={station_root}"
    try:
        completed = runner(["ps", "-axo", "pid=,pgid=,command="])
    except (OSError, subprocess.SubprocessError):
        return []
    matches: list[dict] = []
    for line in (getattr(completed, "stdout", "") or "").splitlines():
        if token not in line or "so101_mujoco_task_station.launch.py" not in line:
            continue
        fields = line.split(None, 2)
        if len(fields) != 3 or not fields[0].isdigit() or not fields[1].isdigit():
            continue
        matches.append({"pid": int(fields[0]), "pgid": int(fields[1]), "command": fields[2]})
    return matches


def _default_ps_runner(command):
    import subprocess

    return subprocess.run(command, capture_output=True, text=True, timeout=30.0)


def stop_station_residue(station_root: str, *, ps_runner=None, signal_sender=None,
                         sleep=None, wait_s: float = 6.0) -> dict:
    """Stop a station that outlived the Worker that owned it, by exact identity, and report.

    A Worker killed by a signal never runs its own `finally`, so its station can survive it. The
    station is still this campaign's process - its argv names this attempt's station root - so it
    is stopped the way the station stack stops it: SIGINT to the launch's own process group, then
    SIGTERM, then SIGKILL, and never a group this campaign cannot name.
    """

    import signal as _signal
    import time as _time

    sender = (lambda pid, number: os.kill(pid, number)) if signal_sender is None else signal_sender
    sleeper = _time.sleep if sleep is None else sleep
    matches = station_processes(station_root, ps_runner=ps_runner)
    stopped, refused = [], []
    for entry in matches:
        leader = entry["pid"] == entry["pgid"]
        target = -entry["pgid"] if leader else entry["pid"]
        for number, grace in ((_signal.SIGINT, wait_s), (_signal.SIGTERM, wait_s / 2.0),
                              (_signal.SIGKILL, wait_s / 2.0)):
            try:
                sender(target, number)
            except ProcessLookupError:
                break
            except (PermissionError, OSError) as error:
                refused.append({"pid": entry["pid"], "error": f"{type(error).__name__}: {error}"})
                break
            sleeper(grace / 4.0)
            if not station_processes(station_root, ps_runner=ps_runner):
                break
        stopped.append(entry["pid"])
    remaining = station_processes(station_root, ps_runner=ps_runner)
    return {"station_root": station_root, "clear": not remaining, "stopped": stopped,
            "refused": refused, "remaining": [entry["pid"] for entry in remaining]}


def reconcile_station(station_root: str, *, ps_runner=None, signal_sender=None, sleep=None) -> dict:
    """Read this attempt's station back, and stop it if the Worker that owned it is gone."""

    readback = station_readback(station_root, ps_runner=ps_runner)
    if readback["clear"]:
        return readback
    stopped = stop_station_residue(station_root, ps_runner=ps_runner, signal_sender=signal_sender,
                                   sleep=sleep)
    after = station_readback(station_root, ps_runner=ps_runner)
    return {**after, "reconciled": stopped}


def station_readback(station_root: str, *, attempts: int = 6, sleep_s: float = 0.5,
                     ps_runner=None) -> dict:
    """Report whether anything still carries this attempt's station root.

    The Worker shuts its own station down; this is the campaign's independent readback of that
    claim. It signals nothing: a survivor is reported, and the drain stops rather than starting the
    next point on top of a station that is still alive.
    """

    matches: list[dict] = []
    for _attempt in range(int(attempts)):
        matches = station_processes(station_root, ps_runner=ps_runner)
        if not matches:
            break
        time.sleep(sleep_s)
    return {"station_root": station_root, "clear": not matches,
            "matches": [entry["pid"] for entry in matches[:8]]}


def _drive_campaign(arguments, argv, plan, spec, document) -> int:
    """Run one composed campaign: guard, broker, Workers, admission, exact cleanup."""

    supervisor = CampaignSupervisor(
        arguments.campaign_id, state_root=arguments.evidence_root / "supervisor",
        ack_timeout_s=120.0,
        # Every Worker takes its own fresh admission once its spawn intent is durable and before
        # `Popen`; the scope binds this process's real owner identity and the plan's worker count.
        spawn_guard=compose_darwin_start_guard(
            plan.config.start_guard,
            state_root=arguments.evidence_root / "start-guard-state"),
        guard_worker_count=plan.worker_count)
    address = DarwinPrivatePathUnixAddress()
    ports = CampaignPorts(model_factories=_model_factories(
        yolo_weights=arguments.yolo_weights.resolve(),
        grounded_root=arguments.grounded_root.resolve()))
    registry = InferenceRegistry(campaign_id=arguments.campaign_id)
    campaign = MacosW2Campaign(plan=plan, address=address, supervisor=supervisor, ports=ports,
                               registry=registry)
    # The immutable selection and the durable queue exist before the first process does. A
    # selection the binding contract refuses - fewer than four points, a missing anchor, an unknown
    # id, a retry of a point that is not a committed business FAILED - stops the campaign here.
    selection, queue, catalog_path = bind_campaign_selection(
        arguments=arguments, plan=plan, spec=spec)
    campaign.bind_selection(binding=selection, queue=queue)
    selection_path = (Path(arguments.evidence_root)
                      / point_drain.SELECTION_DOCUMENT_BASENAME)
    # The campaign document states the same selection the immutable document on disk holds, from
    # that document rather than from a second projection: a retry's original chain and how it was
    # verified (`original_result_source`) therefore read the same in both places.
    written_selection = point_drain.read_selection_document(selection_path)
    document["selection"] = {
        **{key: written_selection[key] for key in (
            "kind", "selection_sha256", "catalog_sha256", "config_sha256",
            "runtime_closure_sha256", "selected_point_ids", "original_selection_sha256",
            "original_result_sha256", "original_outcome", "original_result_source",
            "original_batch_id") if key in written_selection},
        "document_path": str(selection_path),
    }
    document["queue"] = {"root": str(queue.state_path.parent),
                         "state_path": str(queue.state_path),
                         "selected_point_ids": list(selection.selected_point_ids)}

    try:
        admitted = _guard_admission(arguments, argv, plan, spec, document)
    except GuardHandoverRefused as refusal:
        document.update(status="REFUSED", stage="start_guard_handover",
                        refusal=refusal.reason, detail=refusal.detail)
        print(json.dumps(document, indent=2, sort_keys=True))
        return 4
    if admitted is None:
        return 4

    # The broker phase proper. The guard phase ran in a previous interpreter state, so torch is
    # still unimported here, which is what the bootstrap checks.
    from ..runtime.mps_broker_bootstrap import MpsBrokerBootstrap
    from ..core.detection import DetectionFrame, DetectionQuery
    from ..runtime.parallel_ipc_v4 import V4PermissionOnlyServer

    import numpy as np

    journal = None
    supervisor.acquire_claim()
    supervisor.note_heartbeat(owner_pid=os.getpid())
    bootstrap = None
    campaign_root = None
    campaign_root_cleaned = False
    try:
        bootstrap = MpsBrokerBootstrap(
            models=tuple(ports.model_factories.items()),
            memory_fraction=plan.mps_process_memory_fraction,
            lane_capacity=8)
        _torch, ready = bootstrap.prepare()
        document["broker"] = {
            "pid": ready.broker_pid, "birth_identity": ready.broker_birth_identity,
            "ready": ready.ready, "device": ready.runtime_device,
            "fallback_env": ready.fallback_env,
            "models": [model.model_id for model in ready.models],
            "model_devices": [model.device for model in ready.models],
            "model_parameter_devices": [list(model.parameter_devices) for model in ready.models],
            "lane_stats": dict(ready.lane_stats),
            "warmup_total_latency_s": ready.warmup_total_latency_s,
            "receipt_path": str(ready.write(arguments.evidence_root / "broker-ready.json")),
        }
        # --- the composed campaign runs: endpoint, Workers, one-time admission -------------
        campaign_root = address.create_campaign_root()
        document["campaign_root"] = str(campaign_root.campaign_path)
        journal = open_campaign_journal(
            evidence_root=arguments.evidence_root,
            campaign_id=plan.campaign_id, batch_id=arguments.batch_id)
        document["journal"] = {
            "batch_id": arguments.batch_id,
            "segment": str(journal.segment_path),
            "watermark": journal.read_watermark().as_document(arguments.batch_id)
            if journal.read_watermark() else None,
        }
        models = bootstrap.loaded_models
        served: list[dict] = []

        def warm_frame() -> DetectionFrame:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            frame[200:280, 260:380] = 200
            return DetectionFrame(rgb8=np.ascontiguousarray(frame),
                                  source_stamp_ns=time.monotonic_ns(),
                                  source_frame_id="campaign-frame")

        # The Coordinator's table is the admission gate, so every request a Worker will make is
        # bound here *before* it is served. An id that was never bound is refused. Each lease binds
        # the single point that Worker may execute, so the table itself carries the selected-only
        # property: a point the queue never leased has no bound request either.
        import hashlib

        input_digest = hashlib.sha256(b"campaign-warm-frame").hexdigest()
        admission_deadline_s = float(getattr(plan.config, "batch_hard_timeout_s", 5400.0))
        leases: dict[str, dict] = {}

        consumed_ids: set[str] = set()
        cancelled_ids: set[str] = set()
        infer_served = 0
        handler_errors: list[dict] = []
        fault_trace: list[dict] = []

        def handler(request):
            """Serve one request: a real forward pass, admitted through the one-time table."""

            serialized_request = None
            try:
                payload = request.payload
                if isinstance(payload, (bytes, bytearray, str)):
                    payload = json.loads(payload)
                serialized_request = (payload or {}).get("request")
            except Exception:  # noqa: BLE001 - an unreadable payload is a mismatch, not a pass
                serialized_request = None
            if (arguments.cancel_second_worker_after_served
                    and len(served) == arguments.cancel_second_worker_after_served
                    and len(spec.worker_ids) > 1):
                leases_last = leases.get(spec.worker_ids[-1]) or {}
                cancelled_ids.update(f"{attempt}-{leases_last.get('model_id', 'yolo')}"
                                     for attempt in leases_last.get("attempt_ids", []))
            refusal = admission_decision(
                operation=request.operation, request_id=request.request_id,
                serialized_request=serialized_request, consumed_ids=consumed_ids,
                bound_digest=input_digest, cancelled_ids=cancelled_ids)
            if refusal is not None:
                if refusal["error"]["code"] == "DUPLICATE_REQUEST":
                    served.append({"request_id": request.request_id,
                                   "operation": request.operation, "duplicate": True})
                return refusal
            consumed_ids.add(request.request_id)

            detector = models["yolo"]
            batch = bootstrap.lane.submit(
                lambda: detector.detect(warm_frame(), DetectionQuery(class_id="cup")),
                label=f"serve:{request.operation}")
            candidates = len(getattr(batch, "candidates", ()))
            device = detector.runtime_device
            refusal = serve_and_admit(
                campaign, request_id=request.request_id, candidates=candidates, device=device,
                served=served, broker_pid=ready.broker_pid,
                broker_birth_identity=ready.broker_birth_identity)
            if refusal is not None:
                return refusal
            # Fault injection, explicit and one-shot: the Broker child is signalled by exact PID
            # only after the requested number of requests has been served, and what the campaign
            # does next is the evidence - never an automatic kill and never a silent retry.
            if (arguments.crash_broker_after_served
                    and len(served) == arguments.crash_broker_after_served
                    and not document.get("broker_crash")):
                killed = False
                if int(ready.broker_pid) == os.getpid():
                    # Fail closed rather than commit suicide: in this composition the MPS Broker is
                    # in-process, so signalling ourselves would destroy the evidence.
                    document["broker_crash"] = {"pid": ready.broker_pid,
                                                "refused": "BROKER_IS_THIS_PROCESS"}
                    return {"error": {"code": "BROKER_IS_THIS_PROCESS",
                                      "detail": request.request_id}}
                try:
                    os.kill(ready.broker_pid, signal.SIGKILL)
                    killed = True
                except OSError as error:
                    document["broker_crash"] = {"pid": ready.broker_pid, "error": str(error)}
                else:
                    document["broker_crash"] = {"pid": ready.broker_pid, "signal": "SIGKILL"}
                document["broker_crash"]["killed"] = killed
            if request.operation == "broker.infer":
                payload = request.payload or {}
                serialized = payload.get("request")
                if not isinstance(serialized, (str, bytes, dict)):
                    return {"error": {"code": "INVALID_REQUEST",
                                      "detail": request.request_id}}
                return {"ok": True, "request_id": request.request_id, "device": device,
                        "candidates": candidates}
            return {"request_id": request.request_id, "device": device,
                    "candidates": candidates}

        server = V4PermissionOnlyServer(
            endpoint_path=address.endpoint_path(campaign_root, "broker"), handler=handler)
        endpoint = server.start(
            address=address, root=campaign_root, role="broker", owner_pid=os.getpid(),
            owner_birth_identity=ready.broker_birth_identity)
        document["endpoint"] = {"path": str(endpoint.path),
                                "mode": oct(os.stat(endpoint.path).st_mode & 0o777)}
        document["campaign_root"] = str(getattr(campaign_root, "campaign_path", campaign_root))
        broker_pid = getattr(ready, "broker_pid", None)
        document["broker_identity"] = {
            "pid": broker_pid,
            "birth_identity": getattr(ready, "broker_birth_identity", None),
            "in_campaign_process": broker_pid == os.getpid(),
        }

        # --- the drain: one lease, one point, one commit; then the next lease ---------------
        slot_index = {slot_id: index for index, slot_id in enumerate(plan.slots.slot_ids)}

        def lease_point(worker_id: str, slot_id: str, generation: int) -> dict:
            """Lease the queue's next point and write the document this Worker executes from."""

            lease_document = lease_worker_execution(
                queue=queue, binding=selection, worker_id=worker_id, slot_id=slot_id,
                evidence_root=arguments.evidence_root, input_sha256=input_digest,
                deadline_s=arguments.worker_deadline_s, generation=generation,
                execution_profile=spec.execution_profile, batch_kind=spec.batch_kind,
                schema_version=getattr(plan, "schema_version", None),
                tamper_input_sha256=arguments.tamper_snapshot_sha,
                duplicate_probe=arguments.duplicate_probe,
                lease_name=f"{worker_id}-lease-{int(generation):02d}.json", journal=journal)
            leases[worker_id] = lease_document
            bind_worker_requests(campaign, {worker_id: lease_document}, ready=ready,
                                 deadline_s=admission_deadline_s)
            return lease_document

        def spawn_worker(worker_id: str, slot_id: str, generation: int,
                         lease_document: dict) -> point_drain.WorkerRun:
            """Spawn one Worker for exactly this lease, with its own fresh start-guard admission."""

            slot = slot_index[slot_id]
            attempt_id = str(lease_document["attempt_id"])
            # Every lease gets its own ack, result and station root: a later point can never
            # overwrite the evidence of an earlier one, and a station is never reused.
            ack = arguments.evidence_root / f"{worker_id}-ack-{attempt_id}.json"
            result_path = arguments.evidence_root / f"{worker_id}-result-{attempt_id}.json"
            station_root = point_drain.station_root_for(
                evidence_root=arguments.evidence_root, worker_id=worker_id, attempt_id=attempt_id)
            station_root.mkdir(parents=True, exist_ok=True)
            record = supervisor.spawn(
                role="worker", slot=slot,
                argv=[sys.executable, "-m", _WORKER_MODULE, str(ack), str(endpoint.path),
                      worker_id, str(result_path),
                      f"{arguments.campaign_id}-{worker_id}-{attempt_id}",
                      str(station_root), str(plan.ros_domain_ids[slot]),
                      str(lease_document["lease_path"])],
                nonce=f"{arguments.campaign_id}-{worker_id}-{attempt_id}", ack_path=ack,
                ack_timeout_s=120.0)
            journal.append_committed(
                "WORKER_REGISTERED", f"{arguments.batch_id}/WORKER_REGISTERED/{attempt_id}",
                {"worker_id": worker_id, "slot_id": slot_id, "generation": generation,
                 "point_id": lease_document["point_id"], "attempt_id": attempt_id,
                 "pid": record.pid, "birth_identity": record.birth_identity,
                 "status": record.status})
            return point_drain.WorkerRun(
                worker_id=worker_id, slot_id=slot_id, generation=generation, pid=record.pid,
                status=record.status, result_path=result_path, station_root=str(station_root))

        def release_worker(worker_id: str, slot_id: str) -> str:
            """Wait for this attempt's Worker to exit, then free its slot for the next lease.

            The bound is the station-teardown scale, not the batch budget: a Worker whose result is
            already durable must not hold the slot for the whole campaign while it shuts its
            station down. One that outlives this bound is stopped by its exact identity.
            """

            return supervisor.release_child(
                role="worker", slot=slot_index[slot_id],
                wait_s=float(getattr(plan.config, "executing_hard_timeout_s", 180.0)))

        report = point_drain.drain_point_queue(
            queue=queue, binding=selection, worker_ids=spec.worker_ids,
            slot_ids=plan.slots.slot_ids, evidence_root=arguments.evidence_root,
            lease_point=lease_point, spawn_worker=spawn_worker, release_worker=release_worker,
            station_readback=lambda station_root: reconcile_station(station_root),
            # A Worker that exits without a result document is an infrastructure failure, not a
            # reason for the campaign to wait out its whole budget.
            worker_alive=lambda run: not supervisor.is_gone(run.pid) if run.pid else True,
            journal=journal,
            wait_timeout_s=float(getattr(plan.config, "batch_hard_timeout_s", 5400.0)) + 600.0)
        workers = [dict(spawn) for spawn in report.spawns]
        document["workers"] = workers
        document["drain"] = {"stop_reason": report.stop_reason,
                             "stop_detail": report.stop_detail,
                             "stopped_at_cap": report.stopped_at_cap,
                             "releases": [dict(release) for release in report.releases]}
        points_summary = report.summary(selected_point_ids=selection.selected_point_ids)
        document["points"] = points_summary
        # The result documents are re-read from disk as evidence rather than restated from memory.
        results: list[dict] = []
        for spawn in workers:
            path = Path(str(spawn["result_path"]))
            try:
                results.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                results.append({"worker_id": spawn["worker_id"], "unreadable": str(path)})
        document["worker_results"] = results

        # Evidence must not be sealed while handlers are still in flight.
        server.join_workers(timeout_s=30.0)   # returns None; the wait itself is the guarantee
        document["handlers_joined"] = True
        document["server_rejections"] = list(getattr(server, "rejections", ()) or ())
        document["fault_trace"] = fault_trace
        document["cancelled_ids"] = sorted(cancelled_ids)

        per_slot = summarize_per_slot_pick_place(evidence_root=arguments.evidence_root,
                                                 workers=spec.worker_ids)
        document["per_slot_pick_place"] = per_slot
        document["handler_errors"] = handler_errors

        # Every response was admitted through the one-time table when it was served.
        admitted_responses, refused = served_admission_split(served)
        document["admission"] = {"admitted": admitted_responses, "refused": refused}
        document["served"] = {
            "count": len(served),
            "devices": sorted({item["device"] for item in served if "device" in item}),
            "duplicates_refused": sum(1 for item in served if item.get("duplicate")),
            "lane_stats": {"executed": bootstrap.lane.stats.executed,
                           "max_concurrent": bootstrap.lane.stats.max_concurrent,
                           "rejected": bootstrap.lane.stats.rejected},
        }

        server.stop()
        cleanup = address.cleanup_campaign(campaign_root)
        campaign_root_cleaned = bool(cleanup.complete)
        document["cleanup"] = {
            "complete": cleanup.complete, "directory_removed": cleanup.directory_removed,
            "registry_empty": address.registry == (),
        }
        supervisor.terminate_all()
        document["cleanup"]["workers_reaped"] = [supervisor.is_gone(w["pid"]) for w in workers]
        # Every station this campaign started, read back and - if a killed Worker left one behind -
        # stopped by exact identity. A station that outlives the campaign is residue, and residue is
        # never a pass.
        station_roots = sorted({str(spawn["station_root"]) for spawn in workers
                                if spawn.get("station_root")})
        stations = [reconcile_station(root) for root in station_roots]
        document["cleanup"]["stations"] = stations
        document["cleanup"]["stations_clear"] = all(item["clear"] for item in stations)
        document["cleanup"]["complete"] = bool(
            document["cleanup"]["complete"] and document["cleanup"]["stations_clear"])

        document["status"] = campaign_verdict(
            spec=spec, cleanup_complete=bool(document["cleanup"]["complete"]), results=results,
            workers=workers, served=document["served"], refused=refused,
            points=points_summary)
        # The terminal events are committed before the document is sealed, so the recorded
        # watermark covers every canonical event of the run. The `finally` block repeats them
        # defensively; a repeated idempotency key returns the original event and cannot move the
        # watermark backwards.
        commit_campaign_terminal(
            journal, outcome=str(document["status"]),
            cleanup_complete=bool(document["cleanup"]["complete"]))
        document["journal"] = {**document["journal"], "terminal_watermark": (
            journal.read_watermark().as_document(arguments.batch_id)
            if journal.read_watermark() else None)}
        document["journal_terminal"] = True
        print(json.dumps(document, indent=2, sort_keys=True))
        (arguments.evidence_root / "campaign-result.json").write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n")
        return 0 if document["status"] == spec.pass_label else 7
    finally:
        supervisor.terminate_all()
        if campaign_root is not None and not campaign_root_cleaned:
            # A campaign that aborts before its cleanup phase must not leave a registered endpoint
            # behind: `read_inventory` treats a live campaign directory as someone else's resource
            # and would refuse the next campaign on this host. Best effort, reported by the caller.
            try:
                address.cleanup_campaign(campaign_root)
            except Exception:  # noqa: BLE001 - the residue readback is what reports this
                pass
        if journal is not None:
            try:
                commit_campaign_terminal(
                    journal, outcome=str(document.get("status", "UNKNOWN")),
                    cleanup_complete=bool(document.get("cleanup", {}).get("complete")))
                document["journal_terminal"] = True
                (arguments.evidence_root / "campaign-result.json").write_text(
                    json.dumps(document, indent=2, sort_keys=True) + "\n")
            finally:
                journal.close()
        supervisor.release_claim()
        if bootstrap is not None:
            bootstrap.lane.shutdown()


def campaign_verdict(*, spec, cleanup_complete, results, workers, served, refused,
                     points) -> str:
    """The campaign's own verdict for one route, as a pure function.

    PASS is the happy path only, and the happy path now includes the point set: cleanup proven
    complete, one result document per Worker spawn, **every** spawn recorded `ACTIVE`, at least the
    route's minimum number of served requests whose devices are exactly ``["mps"]``, no refused
    request at all, and `points["complete"]` - every selected point executed exactly once with its
    durable evidence, every `PASSED` point with its physical manifest, no duplicate attempt and no
    unselected point ever attempted.

    The point clause is the one Task 11's live gate was missing: without it a campaign that executed
    nothing at all reported `W2_CAMPAIGN_PASS`. A refused request - even a deliberate probe - still
    reads INCOMPLETE by construction.
    """

    if (cleanup_complete and workers and len(results) == len(workers)
            and all(worker["status"] == "ACTIVE" for worker in workers)
            and {worker["worker_id"] for worker in workers} >= set(spec.worker_ids)
            and served["count"] >= spec.minimum_served
            and served["devices"] == ["mps"]
            and not refused
            and bool(points.get("complete"))):
        return spec.pass_label
    return spec.incomplete_label


def run(argv: list[str] | None = None) -> int:
    """The v4 exact-W2 entry point. The profile is this module's; it is not a flag."""

    arguments = build_parser().parse_args(argv)
    arguments_argv = list(sys.argv[1:] if argv is None else argv)
    try:
        return run_routed(argv=arguments_argv, arguments=arguments,
                          execution_profile=MPS_W2_FIRST_PASS)
    except RefusedRun as refusal:
        print(json.dumps({"status": "REFUSED", "stage": refusal.stage, "detail": refusal.detail},
                         indent=2, sort_keys=True))
        return refusal.exit_code


def build_w1_parser(execution_profile: str) -> argparse.ArgumentParser:
    """The W1 parser. One entry point per profile: there is no `--batch-kind` switch."""

    spec = route_spec(execution_profile)
    retry = spec.batch_kind == W1_RETRY_BATCH_KIND
    parser = argparse.ArgumentParser(
        prog="so101_macos_n1_retry" if retry else "so101_macos_n1_first_pass",
        description=f"Run one macOS MPS W1 campaign ({spec.execution_profile}) with one Worker.")
    parser.add_argument("--config", type=Path, required=True,
                        help=f"the schema-v{5 if retry else 6} macOS MPS W1 document")
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--point-id", action="append", default=[],
                        help="repeatable; exact W1 keeps one slot regardless")
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=None,
                        help="the immutable point catalog the selection is frozen from")
    parser.add_argument("--catalog-sha256", default=None)
    parser.add_argument("--retry-root", type=Path, default=None,
                        help="v5 only: the prior campaign root holding the committed business "
                             "FAILED point this retry is bound to")
    parser.add_argument("--original-selection-sha256", default=None,
                        help="v5 only: the original first-pass selection digest the retry "
                             "references (required without --retry-root)")
    parser.add_argument("--original-result-sha256", default=None,
                        help="v5 only: the digest of the original committed business FAILED "
                             "point result (required without --retry-root)")
    parser.add_argument("--original-catalog-sha256", default=None,
                        help="v5 only: the catalog digest the original selection was frozen from; "
                             "the resolved catalog is used when this is omitted")
    parser.add_argument("--original-result", type=Path, default=None,
                        help="v5 only: the original committed result document; when given, its "
                             "bytes must match --original-result-sha256 and it decides the outcome")
    parser.add_argument("--original-batch-id", default=None,
                        help="v5 only: the original batch the failed point came from; it must "
                             "differ from --batch-id")
    parser.add_argument("--yolo-weights", type=Path, required=True)
    parser.add_argument("--grounded-root", type=Path, required=True)
    parser.add_argument("--duplicate-probe", action="store_true")
    parser.add_argument("--cancel-second-worker-after-served", type=int, default=0)
    parser.add_argument("--tamper-snapshot-sha", action="store_true")
    parser.add_argument("--stall-serve-after", type=int, default=0)
    parser.add_argument("--worker-deadline-s", type=float, default=240.0)
    parser.add_argument("--crash-broker-after-served", type=int, default=0)
    parser.add_argument("--skip-models", action="store_true",
                        help="compose and pre-flight only; never a pass")
    return parser


def run_w1(argv: list[str] | None = None, *, execution_profile: str) -> int:
    """The W1 entry point for one named profile. A different profile's document is refused."""

    spec = route_spec(execution_profile)
    if spec.worker_count != 1:
        raise ContractError(f"NOT_A_W1_PROFILE: {execution_profile}")
    arguments = build_w1_parser(execution_profile).parse_args(argv)
    arguments_argv = list(sys.argv[1:] if argv is None else argv)
    try:
        return run_routed(argv=arguments_argv, arguments=arguments,
                          execution_profile=execution_profile)
    except RefusedRun as refusal:
        print(json.dumps({"status": "REFUSED", "stage": refusal.stage, "detail": refusal.detail},
                         indent=2, sort_keys=True))
        return refusal.exit_code


def main(argv: list[str] | None = None) -> int:
    # The launcher's first job is the fallback pin and the process handover, and it happens before
    # anything that could import torch. The accelerator probe needs torch.mps, while the broker
    # bootstrap requires torch to still be unimported when it reads the pin, so the two must not
    # share an interpreter. Pinning and re-executing here is what keeps that true; the guard phase
    # re-executes once more to hand the admission over.
    arguments = list(sys.argv[1:] if argv is None else argv)
    if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") != "0":
        environment = dict(os.environ)
        environment["PYTORCH_ENABLE_MPS_FALLBACK"] = "0"
        os.execve(sys.executable, [sys.executable, "-m",
                                   "so101_demo.cli.macos_w2_campaign", *arguments], environment)
    try:
        return run(arguments)
    except Exception as error:  # noqa: BLE001 - a refusal is reported, never a traceback alone
        print(json.dumps({"status": "ERROR", "error": f"{type(error).__name__}: {error}"},
                         indent=2, sort_keys=True))
        return 1


def main_w1(execution_profile: str, argv: list[str] | None = None) -> int:
    """The W1 launcher: same fallback pin, then the profile's own entry point."""

    spec = route_spec(execution_profile)
    arguments = list(sys.argv[1:] if argv is None else argv)
    if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") != "0":
        environment = dict(os.environ)
        environment["PYTORCH_ENABLE_MPS_FALLBACK"] = "0"
        os.execve(sys.executable, [sys.executable, "-m", spec.module, *arguments], environment)
    try:
        return run_w1(arguments, execution_profile=execution_profile)
    except Exception as error:  # noqa: BLE001 - a refusal is reported, never a traceback alone
        print(json.dumps({"status": "ERROR", "error": f"{type(error).__name__}: {error}"},
                         indent=2, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
