"""Write the restart measurements."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
import sys
import time

from so101_demo.act.head_search.qualification import _require_new_root
from so101_demo.act.head_search.restarts.contracts import (
    ABORT_CODES,
    AGGREGATE_ARTIFACT,
    ANCHORS,
    ARTIFACT_BY_ANCHOR,
    FIT_WARNING,
    OPERATION,
    PHASE,
    RECEIPT_ARTIFACT,
    RECEIPTS_KIND,
    RESTART_ANCHOR_UNDECLARED,
    RESTART_RUN_ROOT_EXISTS,
    SCHEMA_VERSION,
    _refuse,
    _write,
)
from so101_demo.act.head_search.restarts.observation import (
    anchor_declarations,
    read_ownership_receipt,
    require_runtime_of_record,
)
from so101_demo.act.head_search.restarts.restart_run import receipt_document


def write_head_search_restarts(
    *,
    run_root,
    ownership_receipt,
    runtime: Mapping,
    approved_bundle_sha256: str,
    seal: Mapping,
    workdir,
    run_anchor,
    producer: Mapping,
    values: Mapping | None = None,
    anchors: Sequence[str] = ANCHORS,
    now=time.gmtime,
) -> dict:
    """Claim a brand-new run root and run exactly one restart per declared anchor, in order.

    A refusal at any anchor stops the run: the anchors after it are never started, and the receipts
    already written stay on disk as the evidence of how far the run got.
    """

    started = time.time()
    root = Path(run_root)
    if root.exists():
        raise _refuse(
            RESTART_RUN_ROOT_EXISTS,
            f"{root} exists; a qualification run is never resumed, continued or overwritten",
        )
    runtime = require_runtime_of_record(runtime)
    ownership = read_ownership_receipt(ownership_receipt, run_root=root)
    declared = anchor_declarations(seal, anchors)
    if [item["anchor"] for item in declared] != list(ANCHORS):
        raise _refuse(
            RESTART_ANCHOR_UNDECLARED,
            f"the restart phases must be exactly {', '.join(ANCHORS)}, once each",
        )
    _require_new_root(root)
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    receipts: dict[str, str] = {}
    documents: dict[str, dict] = {}
    for item in declared:
        anchor = item["anchor"]
        anchor_root = root / anchor
        anchor_root.mkdir()
        stdout = (anchor_root / "stdout.log").open("a", encoding="utf-8")
        stderr = (anchor_root / "stderr.log").open("a", encoding="utf-8")
        try:
            evidence = run_anchor(
                anchor=anchor,
                anchor_root=anchor_root,
                declared=item,
                runtime=runtime,
                run_root=root,
                ownership=ownership,
                approved_bundle_sha256=approved_bundle_sha256,
                producer=producer,
                anchors=declared,
                stdout=stdout,
                stderr=stderr,
            )
        finally:
            stdout.close()
            stderr.close()
        document = receipt_document(
            anchor_run=evidence,
            runtime=runtime,
            approved_bundle_sha256=approved_bundle_sha256,
            run_root=root,
            anchor_root=anchor_root,
            ownership=ownership,
            producer=producer,
            values=values,
            elapsed_s=evidence.get("elapsed_s"),
            started_at_utc=evidence.get("started_at_utc"),
            finished_at_utc=evidence.get("finished_at_utc"),
        )
        _write(anchor_root, ARTIFACT_BY_ANCHOR[anchor], document)
        receipts[anchor] = str(anchor_root / ARTIFACT_BY_ANCHOR[anchor])
        documents[anchor] = document
        if document["refusals"]:
            first = document["refusals"][0]
            if first["code"] in ABORT_CODES:
                # a stack that may still be alive, or a second owner, is never followed by another anchor
                raise _refuse(
                    first["code"],
                    f"the {anchor} restart refused and the run stops here: {first['detail']}",
                )
            print(
                f"restart_{anchor}: REFUSED {first['code']}: {first['detail']}",
                file=sys.stderr,
            )
    aggregate = {
        "schema_version": SCHEMA_VERSION,
        "kind": RECEIPTS_KIND,
        "operation": OPERATION,
        "phase": PHASE,
        "run_root": str(root),
        "anchors": [item["anchor"] for item in declared],
        "receipts": receipts,
        "receipt_sha256": {anchor: documents[anchor]["sha256"] for anchor in receipts},
        "receipt_status": {anchor: documents[anchor]["status"] for anchor in receipts},
        "runtime": dict(runtime),
        "ownership_receipt": dict(ownership),
        "approved_bundle_sha256": approved_bundle_sha256,
        "producer": {**dict(producer), "stack_owned": True},
        "elapsed_s": time.time() - started,
        "status": "PASS" if all(d["status"] == "PASS" for d in documents.values()) else "REFUSED",
        "fit_warning": FIT_WARNING,
    }
    _write(root, AGGREGATE_ARTIFACT, aggregate)
    _write(root, RECEIPT_ARTIFACT, {**aggregate, "kind": f"{RECEIPTS_KIND}_receipt"})
    refused = [anchor for anchor, document in documents.items() if document["status"] != "PASS"]
    if refused:
        raise _refuse(
            documents[refused[0]]["refusals"][0]["code"],
            f"the restarts for {', '.join(sorted(refused))} refused; every receipt is on disk in {root}",
        )
    return {
        "receipts": receipts,
        "documents": documents,
        "aggregate": aggregate,
        "run_root": str(root),
    }
