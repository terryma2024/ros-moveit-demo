"""The one writer of the campaign batch layout every test that needs those bytes shares.

The batch root a campaign writes is ``<evidence_root>/campaigns/<campaign>/<batch>`` with its
journal under ``journal/`` and its durable per-point documents under ``point-results/``. Two test
modules need exactly that layout - the projection tests drive the installed projection over it, and
the retry fixture composes the production service over it - so the writer lives here once. A second
copy would be a second source of truth for a byte-level vocabulary: the event names, the payload
field names and the document fields are what the installed readers verify, and a copy that drifts
would make one module's tests pass against bytes the other module never produces.

Only the fields the installed readers actually verify are written. ``CampaignLayoutReader`` and
``_point_result_document`` are the authority for the per-point document; everything else the live
campaign happens to record is not read by the projection or the retry admission and is deliberately
absent here, so a reader that starts depending on one of those fields shows up as a failing test
rather than as a fixture that quietly anticipated it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from so101_demo.parallel_batch.journal import CoordinatorJournal

#: The campaign's own binding hashes. They are fixture constants, not hashes of anything outside
#: the test's ``tmp_path``: the readers require a digest, never a particular one.
CATALOG_SHA256 = "c" * 64
SELECTION_SHA256 = "5" * 64
CONFIG_SHA256 = "2" * 64
RUNTIME_CLOSURE_SHA256 = "7" * 64
EVIDENCE_MANIFEST_SHA256 = "e" * 64
DYNAMIC_MANIFEST_SHA256 = "d" * 64

#: The bindings a batch document may name, and the verdicts the campaign's own result may carry.
CAMPAIGN_PASS_VERDICTS = ("W2_CAMPAIGN_PASS", "N1_CAMPAIGN_PASS")
CAMPAIGN_INCOMPLETE = "CAMPAIGN_INCOMPLETE"

#: The two binding vocabularies one campaign writes: the first pass names its catalog and lists its
#: selection, a retry names the catalog it was selected from and the one point it executes.
FIRST_PASS_KIND = "FIRST_PASS"
RETRY_KIND = "FULL_RESTART_RETRY"


def result_sha256(point_id: str, attempt_id: str, outcome: str) -> str:
    """The result hash the batch's own ``POINT_TERMINAL`` commits for one attempt."""

    return hashlib.sha256(f"{point_id}:{attempt_id}:{outcome}".encode()).hexdigest()


def point_result_document(
    *, campaign_id: str, batch_id: str, point_id: str, attempt_id: str, outcome: str,
    evidence_manifest_sha256: str = EVIDENCE_MANIFEST_SHA256,
    dynamic_manifest_sha256: str = DYNAMIC_MANIFEST_SHA256,
    worker_id: str = "w1", generation: int = 1,
) -> dict:
    """The campaign's durable per-point committed document, with only the verified fields.

    ``committed``/``point_id``/``attempt_id``/``outcome`` are what ``_point_result_document``
    requires - the projection refuses without any one of them. The lease identity ties the document
    to the campaign's own lease and the two manifest digests are cross-checked against the committed
    event that references them; both were measured the same way: dropping one keeps the projection
    green, while a *wrong* value refuses it, so they are verification, not decoration. Every other
    field a live campaign records (worker/slot/generation, the points and worker-result digests, the
    physical-evidence flags, the station readback) is read by nothing in this path and is therefore
    not written: a reader that starts depending on one of them must fail here, not silently find a
    fixture that anticipated it.
    """

    return {
        "committed": True,
        "point_id": point_id,
        "attempt_id": attempt_id,
        "outcome": outcome,
        "lease_identity": [campaign_id, batch_id, point_id, attempt_id, generation, worker_id],
        "evidence_manifest_sha256": evidence_manifest_sha256,
        "dynamic_manifest_sha256": dynamic_manifest_sha256,
    }


def append_campaign_stream(
    journal, *, campaign_id: str, batch_id: str, outcomes, verdict: str,
    cleanup_complete=True, evidence_manifest_sha256: str = EVIDENCE_MANIFEST_SHA256,
    dynamic_manifest_sha256: str = DYNAMIC_MANIFEST_SHA256, worker_id: str = "w1",
    slot_id: str = "slot-0", selection_sha256: str = SELECTION_SHA256,
) -> None:
    """Commit the campaign's own event stream, exactly as the composition writes it.

    ``cleanup_complete=None`` omits the ``CLEANUP_COMMITTED`` frame altogether, which is how a batch
    whose own bytes never claim cleanup is written - the negative a receipt must never be invented
    from.
    """

    journal.append_committed(
        "CAMPAIGN_STARTED",
        f"{campaign_id}/CAMPAIGN_STARTED",
        {"campaign_id": campaign_id, "batch_id": batch_id,
         "schema_version": journal.schema_version},
    )
    for point_id, outcome in outcomes.items():
        attempt_id = f"{point_id}-attempt-1"
        lease_sha256 = hashlib.sha256(f"{point_id}-lease".encode()).hexdigest()
        points_sha256 = hashlib.sha256(f"{point_id}-points".encode()).hexdigest()
        journal.append_committed(
            "POINT_LEASED", f"{batch_id}/POINT_LEASED/{attempt_id}",
            {
                "point_id": point_id, "attempt_id": attempt_id, "worker_id": worker_id,
                "slot_id": slot_id, "generation": 1,
                "lease": {"batch_id": batch_id, "campaign_id": campaign_id, "point_id": point_id,
                          "attempt_id": attempt_id, "worker_id": worker_id, "slot_id": slot_id,
                          "generation": 1},
                "lease_sha256": lease_sha256,
                "points_path": f"points/{point_id}.yaml",
                "points_sha256": points_sha256,
                "selection_sha256": selection_sha256,
            },
        )
        journal.append_committed(
            "WORKER_REGISTERED", f"{batch_id}/WORKER_REGISTERED/{attempt_id}",
            {"point_id": point_id, "attempt_id": attempt_id, "worker_id": worker_id,
             "slot_id": slot_id, "generation": 1, "pid": 4242, "birth_identity": 9001,
             "status": "ACTIVE"},
        )
        journal.append_committed(
            "ATTEMPT_STARTED", f"{batch_id}/ATTEMPT_STARTED/{attempt_id}",
            {"point_id": point_id, "attempt_id": attempt_id, "worker_id": worker_id,
             "slot_id": slot_id, "generation": 1, "pid": 4242,
             "lease_sha256": lease_sha256, "points_sha256": points_sha256},
        )
        journal.append_committed(
            "RESULT_COMMITTED", f"{batch_id}/RESULT_COMMITTED/{attempt_id}",
            {"point_id": point_id, "attempt_id": attempt_id, "worker_id": worker_id,
             "slot_id": slot_id, "generation": 1, "outcome": outcome,
             "failure_code": None if outcome == "PASSED" else "ANCHOR_UNREACHABLE",
             "moveit_executed": True, "station_ready": True, "cleanup_owned": True,
             "evidence_manifest_sha256": evidence_manifest_sha256,
             "dynamic_manifest_sha256": dynamic_manifest_sha256,
             "lease_identity": [campaign_id, batch_id, point_id, attempt_id, 1, worker_id]},
        )
        journal.append_committed(
            "POINT_TERMINAL", f"{batch_id}/POINT_TERMINAL/{point_id}",
            {"point_id": point_id, "attempt_id": attempt_id, "outcome": outcome,
             "state": "COMMITTED",
             "result_sha256": result_sha256(point_id, attempt_id, outcome)},
        )
    journal.append_committed("BATCH_TERMINAL", f"{batch_id}/BATCH_TERMINAL", {"outcome": verdict})
    if cleanup_complete is not None:
        journal.append_committed(
            "CLEANUP_COMMITTED", f"{batch_id}/CLEANUP_COMMITTED",
            {"cleanup_complete": cleanup_complete},
        )


def _selection_binding(*, campaign_id, batch_id, kind, point_ids, catalog_sha256, selection_sha256,
                       config_sha256, runtime_closure_sha256):
    """The batch's own binding document, in the vocabulary its kind writes.

    The journal's leases reference this document's ``selection_sha256``, so one of the two is what
    the reader verifies the other against. A ``FULL_RESTART_RETRY`` binding names the catalog its
    one point was selected from (``original_catalog_sha256``) and that point (``point``); it
    deliberately
    carries none of the first pass's names, which is exactly the vocabulary the reader must accept
    on that kind and refuse anywhere else.
    """

    binding = {
        "batch_id": batch_id,
        "campaign_id": campaign_id,
        "kind": kind,
        "catalog_schema_version": 1,
        "coordinate_frame": "world",
        "selection_sha256": selection_sha256,
        "config_sha256": config_sha256,
        "runtime_closure_sha256": runtime_closure_sha256,
    }
    if kind == RETRY_KIND:
        binding["original_catalog_sha256"] = catalog_sha256
        binding["point"] = {"point_id": point_ids[0], "point_sha256": "9" * 64}
    else:
        binding["catalog_sha256"] = catalog_sha256
        binding["selected_point_ids"] = list(point_ids)
        binding["points"] = [
            {"point_id": point_id, "point_sha256": "9" * 64} for point_id in point_ids
        ]
    return binding


def write_campaign_batch(
    root, outcomes, *, campaign_id: str, batch_id: str, verdict: str, kind: str = FIRST_PASS_KIND,
    point_ids=None, cleanup_complete=True, catalog_sha256: str = CATALOG_SHA256,
    selection_sha256: str = SELECTION_SHA256, config_sha256: str = CONFIG_SHA256,
    runtime_closure_sha256: str = RUNTIME_CLOSURE_SHA256,
    evidence_manifest_sha256: str = EVIDENCE_MANIFEST_SHA256,
    dynamic_manifest_sha256: str = DYNAMIC_MANIFEST_SHA256, worker_id: str = "w1",
) -> Path:
    """Write one campaign batch root: journal, binding, per-point results, result doc."""

    selected = tuple(outcomes) if point_ids is None else tuple(point_ids)
    if kind == RETRY_KIND and len(selected) != 1:
        raise ValueError("a retry batch executes exactly one point")
    batch_root = (Path(root) / "campaigns" / campaign_id / batch_id).resolve()
    batch_root.mkdir(parents=True)
    (batch_root / "points").mkdir()
    (batch_root / "point-results").mkdir()
    for point_id in selected:
        attempt_id = f"{point_id}-attempt-1"
        (batch_root / "points" / f"{point_id}.yaml").write_text(f"point_id: {point_id}\n")
        (batch_root / "point-results" / f"{point_id}.json").write_text(
            json.dumps(
                point_result_document(
                    campaign_id=campaign_id, batch_id=batch_id, point_id=point_id,
                    attempt_id=attempt_id, outcome=outcomes[point_id],
                    evidence_manifest_sha256=evidence_manifest_sha256,
                    dynamic_manifest_sha256=dynamic_manifest_sha256,
                    worker_id=worker_id,
                ),
                sort_keys=True,
            )
        )
    document = {
        "batch_id": batch_id,
        "campaign_id": campaign_id,
        "catalog_sha256": catalog_sha256,
        "binding": _selection_binding(
            campaign_id=campaign_id, batch_id=batch_id, kind=kind, point_ids=selected,
            catalog_sha256=catalog_sha256, selection_sha256=selection_sha256,
            config_sha256=config_sha256, runtime_closure_sha256=runtime_closure_sha256,
        ),
    }
    if kind == RETRY_KIND:
        # The retry document's own summary names the one point its binding names, so a binding whose
        # point was rewritten disagrees with the summary it was written from and is refused.
        document["selected_point_ids"] = list(selected)
    (batch_root / "selection-binding.json").write_text(json.dumps(document, sort_keys=True))
    (batch_root / "campaign-result.json").write_text(json.dumps({
        "status": verdict,
        "points": {point_id: {"committed": outcomes[point_id]} for point_id in selected},
    }, sort_keys=True))
    with CoordinatorJournal.create(batch_root / "journal", batch_id) as journal:
        append_campaign_stream(
            journal, campaign_id=campaign_id, batch_id=batch_id, outcomes=outcomes,
            verdict=verdict, cleanup_complete=cleanup_complete,
            evidence_manifest_sha256=evidence_manifest_sha256,
            dynamic_manifest_sha256=dynamic_manifest_sha256, worker_id=worker_id,
            selection_sha256=selection_sha256,
        )
    return batch_root
