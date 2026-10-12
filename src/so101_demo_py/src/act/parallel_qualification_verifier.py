"""Independent verification of an eight-worker qualification document, and the container-collection qualification report.

The two collection entry points are `build_collection_qualification_report` and `verify_collection_qualification` at the end of
this module; the recomputation they share is `collection_qualification_recompute`. Everything between is the earlier pick-place
verifier, which admission still calls until the container path replaces it.

`so101_teleop`'s admission refuses a self-declared `PASSED` qualification: it requires an independent
verifier of the frozen contract, of the committed campaign waves and of the actual per-Worker terminal
leases (`unified/admission.py:492-502`). This module is that verifier.

It trusts nothing the document claims about its own evidence. The document's `live_campaign` block names a
case root and the digests of the campaign result, the preparation receipt and every case journal; this
verifier recomputes those digests **from disk** and refuses on any mismatch, then delegates the campaign and
journal rules to the same functions the producer uses, so a document cannot cite evidence that does not
exist, has changed, or was never validated.
"""

import hashlib
import json
import os
from pathlib import Path


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_document(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise ValueError("EIGHT_WORKER_QUALIFICATION_EVIDENCE_INVALID")
    try:
        document = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("EIGHT_WORKER_QUALIFICATION_EVIDENCE_INVALID") from error
    if not isinstance(document, dict):
        raise ValueError("EIGHT_WORKER_QUALIFICATION_EVIDENCE_INVALID")
    return document


def verify_eight_worker_qualification(qualified_path, payload) -> bool:
    """Return `True` only when the qualification document's evidence verifies from disk.

    Refusals, each with its own code so a caller can tell them apart: a missing or malformed document or
    evidence block (`EIGHT_WORKER_QUALIFICATION_EVIDENCE_INVALID`), a document that is not `QUALIFIED` with the
    required worker count (`EIGHT_WORKER_QUALIFICATION_EVIDENCE_INVALID`), and any digest mismatch between the
    document and the artifacts it names (`EIGHT_WORKER_QUALIFICATION_EVIDENCE_MISMATCH`).
    """

    document = _read_document(Path(qualified_path))
    if document.get("status") != "QUALIFIED" or document.get("worker_count") != 8:
        # admission already checks the declared fields; here they must at least be the qualified ones
        raise ValueError("EIGHT_WORKER_QUALIFICATION_EVIDENCE_INVALID")
    block = document.get("live_campaign")
    if (not isinstance(block, dict)
            or set(block) != {"case_root", "campaign_result_sha256", "preparation_receipt_sha256",
                              "journal_sha256"}
            or not isinstance(block["case_root"], str)
            or not block["case_root"]
            or not isinstance(block["journal_sha256"], list)
            or not block["journal_sha256"]):
        raise ValueError("EIGHT_WORKER_QUALIFICATION_EVIDENCE_INVALID")
    case_root = Path(block["case_root"])
    campaign_result = case_root / "campaign-result.json"
    if not campaign_result.is_file():
        raise ValueError("EIGHT_WORKER_QUALIFICATION_EVIDENCE_INVALID")
    if _digest(campaign_result) != block["campaign_result_sha256"]:
        # the campaign the document cites is not the campaign on disk
        raise ValueError("EIGHT_WORKER_QUALIFICATION_EVIDENCE_MISMATCH")
    # the campaign result's own summary must qualify on its terms (PASSED, complete, unbroken, unique
    # journal digests) and its digests must be exactly the ones the document cites, so a document cannot
    # point at a campaign whose summary says something else
    try:
        summary = json.loads(campaign_result.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("EIGHT_WORKER_QUALIFICATION_EVIDENCE_INVALID") from error
    from .pick_place_live_qualification import validate_campaign_summary

    try:
        summary = validate_campaign_summary(summary)
    except ValueError as error:
        raise ValueError("EIGHT_WORKER_QUALIFICATION_EVIDENCE_MISMATCH") from error
    if list(summary["case_journal_sha256"]) != list(block["journal_sha256"]):
        raise ValueError("EIGHT_WORKER_QUALIFICATION_EVIDENCE_MISMATCH")
    for expected in block["journal_sha256"]:
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError("EIGHT_WORKER_QUALIFICATION_EVIDENCE_INVALID")
        # the producer writes one journal per case under `<case_root>/pick-place-live/cases/<case_id>.json`
        cases = case_root / "pick-place-live" / "cases"
        if not any(_digest(path) == expected for path in cases.glob("*.json")):
            # a journal the document names is missing or has changed
            raise ValueError("EIGHT_WORKER_QUALIFICATION_EVIDENCE_MISMATCH")
    # the campaign's journals must re-check on the qualification producer's own terms: fourteen complete
    # rows bound to this bundle's identity, a prefix without a live-evidence artifact and a full with one.
    # That needs the prepared bundle the payload names, so it is done only when the payload supplies it;
    # a caller that names no bundle gets the digest binding above and nothing weaker is claimed for it.
    receipt_path = payload.get("preparation_receipt_path") if isinstance(payload, dict) else None
    if receipt_path is not None:
        if not isinstance(receipt_path, str) or not receipt_path:
            raise ValueError("EIGHT_WORKER_QUALIFICATION_EVIDENCE_INVALID")
        try:
            from .pick_place_validation_artifact_bundle import verify_prepared_pick_place_validation_bundle

            bundle = verify_prepared_pick_place_validation_bundle(Path(receipt_path))
            manifest_path = Path(bundle.manifest)
            manifest = json.loads(manifest_path.read_bytes())
        except (OSError, KeyError, TypeError, ValueError, UnicodeDecodeError,
                json.JSONDecodeError) as error:
            raise ValueError("EIGHT_WORKER_QUALIFICATION_EVIDENCE_INVALID") from error
        if _digest(Path(receipt_path)) != block["preparation_receipt_sha256"]:
            # the bundle is not the one the document was qualified against
            raise ValueError("EIGHT_WORKER_QUALIFICATION_EVIDENCE_MISMATCH")
        if payload.get("manifest_path") is not None and Path(payload["manifest_path"]) != manifest_path:
            raise ValueError("EIGHT_WORKER_QUALIFICATION_EVIDENCE_MISMATCH")
        from .pick_place_live_qualification import validate_case_journals

        try:
            validate_case_journals(case_root, manifest, identities=bundle.identities,
                                   manifest_document_sha256=manifest["manifest_document_sha256"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("EIGHT_WORKER_QUALIFICATION_EVIDENCE_MISMATCH") from error
    return True


# ---- the container-collection qualification report ---------------------------------------------------------------------

REPORT_RELATIVE = Path("host") / "qualification-report.json"
_REPORT_KEYS = frozenset({"schema_version", "kind", "status", "qualification_run_id", "worker_count", "controlled_identity",
                          "contract", "campaign_index", "waves", "quality", "resource_logs", "reasons"})
_QUALITY_NAMES = frozenset({"recorder_lossless", "frame_continuity", "qc_valid_rate", "teacher_physical_success_rate"})


def build_collection_qualification_report(run_root, *, contract) -> Path:
    """Recompute the run from its originals and write `<run>/host/qualification-report.json`, once and never over an old one.

    `contract` is the gate contract file the campaign config names. A run that does not qualify still gets a report: status
    `NOT_QUALIFIED` and a sorted list of closed reason codes. A run or contract that cannot be read raises and writes nothing.
    """

    from .collection_qualification_recompute import canonical, recompute, run_layout

    run, _ = run_layout(run_root)
    target = run / REPORT_RELATIVE
    if target.exists() or target.is_symlink():
        raise ValueError("QUALIFICATION_REPORT_EXISTS")
    payload = canonical(recompute(run, contract))
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError as error:
        raise ValueError("QUALIFICATION_REPORT_EXISTS") from error
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return target


def _qualification_run(report_path, registered_root) -> Path:
    """The run directory a report belongs to: the registered root's direct child, with its own layout file and the fixed report path.

    Composes `_open_regular` (no symlink in any component), the canonical-path rule of the campaign paths and the run layout
    document. Whether the run is the current one is the caller's question: admission knows the current root."""

    from .collection_qualification_recompute import run_layout

    report, registered = Path(report_path), Path(registered_root)
    try:
        for path in (report, registered):
            if not path.is_absolute() or ".." in path.parts or path.resolve(strict=True) != path:
                raise ValueError("path is not canonical")
        run = report.parent.parent
        if not registered.is_dir() or run.parent != registered or report != run / REPORT_RELATIVE:
            raise ValueError("report is not at the fixed location of a run of the registered root")
        _, layout = run_layout(run)
        if layout["root"] != str(registered) or layout["run_id"] != run.name:
            raise ValueError("layout names another root")
    except (OSError, ValueError) as error:
        raise ValueError("COLLECTION_QUALIFICATION_PATH_INVALID") from error
    return run


def _closed_report(document):
    from .collection_qualification_recompute import KIND

    if (type(document) is not dict or set(document) != _REPORT_KEYS or document["kind"] != KIND
            or type(document["schema_version"]) is not int or document["schema_version"] != 1
            or document["status"] not in ("QUALIFIED", "NOT_QUALIFIED")
            or type(document["worker_count"]) is not int or document["worker_count"] != 8
            or type(document["qualification_run_id"]) is not str or type(document["reasons"]) is not list
            or type(document["quality"]) is not dict or set(document["quality"]) != _QUALITY_NAMES):
        raise ValueError("COLLECTION_QUALIFICATION_REPORT_INVALID")


def verify_collection_qualification(report_path, *, registered_root, expected_identity) -> dict:
    """Recompute the whole run behind a report and return the in-memory proof; nothing is written, nothing the report says is used.

    A legacy `PASSED` receipt or a pick-place live document fails the closed kind and field check before anything else is read.
    The recomputed document must equal the report byte for byte and be `QUALIFIED`. `expected_identity=None` skips only the
    comparison with an externally supplied controlled identity.
    """

    from .collection_qualification_recompute import (
        _bytes, _parse, campaign_contract_path, canonical, contract_documents, recompute,
    )

    report = Path(report_path)
    try:
        run = _qualification_run(report, registered_root)
        raw = _bytes(report)
        document = _parse(raw)
        _closed_report(document)
    except ValueError as error:
        if str(error).startswith("COLLECTION_QUALIFICATION_"):
            raise
        raise ValueError("COLLECTION_QUALIFICATION_REPORT_INVALID") from error
    except OSError as error:
        raise ValueError("COLLECTION_QUALIFICATION_REPORT_INVALID") from error
    if document["status"] != "QUALIFIED":
        raise ValueError("COLLECTION_QUALIFICATION_NOT_QUALIFIED")
    try:
        contract_path = campaign_contract_path(run)
        recomputed = recompute(run, contract_path)
        _, contract = contract_documents(contract_path)
    except ValueError as error:
        raise ValueError("COLLECTION_QUALIFICATION_RECOMPUTE_INVALID") from error
    if recomputed["status"] != "QUALIFIED" or canonical(recomputed) != raw:
        raise ValueError("COLLECTION_QUALIFICATION_RECOMPUTE_MISMATCH")
    if expected_identity is not None and recomputed["controlled_identity"] != expected_identity:
        raise ValueError("COLLECTION_QUALIFICATION_IDENTITY_MISMATCH")
    return dict(kind="ACT_COLLECTION_QUALIFICATION_READBACK", schema_version=1, status="PASS",
                report_sha256=hashlib.sha256(raw).hexdigest(), qualification_run_id=recomputed["qualification_run_id"],
                run_root=str(run), controlled_identity=recomputed["controlled_identity"],
                contract_sha256=recomputed["contract"]["sha256"],
                scene_manifest_sha256=contract["scene_manifest"]["sha256"],
                functional_manifest_sha256=contract["functional_manifest"]["sha256"],
                formal_split_manifest_sha256=contract["formal_split_manifest"]["sha256"], task_count=40)
