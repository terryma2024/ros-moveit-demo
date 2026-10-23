"""Worker leases, the campaign journal and the per-slot pick-place summary."""

from __future__ import annotations

import glob
import json
from pathlib import Path

from so101_demo.parallel_batch import point_drain
from so101_demo.parallel_batch.macos_two_worker_campaign import (
    MacosTwoWorkerCampaignError,
)

#: The v4 exact two-worker profile this module is the entry point for.
MPS_TWO_WORKER_FIRST_PASS = "MPS_TWO_WORKER_FIRST_PASS"


TWO_WORKER_FIRST_PASS_BATCH_KIND = "FIRST_PASS"


#: The worker child module, spawned as `python -m so101_demo.cli.macos_two_worker_process`.
_WORKER_MODULE = "so101_demo.cli.macos_two_worker_process"


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
    Worker refuses (`POINTS_PATH_MISSING`), which is exactly the gap the live gate found. The
    frame is created once; a later run reuses it rather than rewriting evidence.
    """

    if binding is None or queue is None:
        raise MacosTwoWorkerCampaignError("SELECTION_QUEUE_REQUIRED", "a binding and a queue are required")
    # One Worker per capacity slot: exact two-worker creates two, each single-worker profile exactly one.
    if worker_ids is None:
        worker_ids = tuple(f"worker-{index + 1:02d}" for index in range(len(plan.slots.slot_ids)))
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

    The macOS single-worker/two-worker compositions reuse the existing `CoordinatorJournal`: the coordinator is the
    single writer, every returned event is already fsynced *and* covered by a published committed
    watermark, and the projection side reads that prefix instead of polling terminal files.
    """

    from so101_demo.parallel_batch.journal import CoordinatorJournal

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


def summarize_per_slot_pick_place(*, evidence_root: Path, workers=("worker-01", "worker-02")) -> dict:
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
