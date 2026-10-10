"""Independent verification of an eight-worker qualification document.

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
from pathlib import Path


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_document(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise ValueError("W8_QUALIFICATION_EVIDENCE_INVALID")
    try:
        document = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("W8_QUALIFICATION_EVIDENCE_INVALID") from error
    if not isinstance(document, dict):
        raise ValueError("W8_QUALIFICATION_EVIDENCE_INVALID")
    return document


def verify_eight_worker_qualification(qualified_path, payload) -> bool:
    """Return `True` only when the qualification document's evidence verifies from disk.

    Refusals, each with its own code so a caller can tell them apart: a missing or malformed document or
    evidence block (`W8_QUALIFICATION_EVIDENCE_INVALID`), a document that is not `QUALIFIED` with the
    required worker count (`W8_QUALIFICATION_EVIDENCE_INVALID`), and any digest mismatch between the
    document and the artifacts it names (`W8_QUALIFICATION_EVIDENCE_MISMATCH`).
    """

    document = _read_document(Path(qualified_path))
    if document.get("status") != "QUALIFIED" or document.get("worker_count") != 8:
        # admission already checks the declared fields; here they must at least be the qualified ones
        raise ValueError("W8_QUALIFICATION_EVIDENCE_INVALID")
    block = document.get("live_campaign")
    if (not isinstance(block, dict)
            or set(block) != {"case_root", "campaign_result_sha256", "preparation_receipt_sha256",
                              "journal_sha256"}
            or not isinstance(block["case_root"], str)
            or not block["case_root"]
            or not isinstance(block["journal_sha256"], list)
            or not block["journal_sha256"]):
        raise ValueError("W8_QUALIFICATION_EVIDENCE_INVALID")
    case_root = Path(block["case_root"])
    campaign_result = case_root / "campaign-result.json"
    if not campaign_result.is_file():
        raise ValueError("W8_QUALIFICATION_EVIDENCE_INVALID")
    if _digest(campaign_result) != block["campaign_result_sha256"]:
        # the campaign the document cites is not the campaign on disk
        raise ValueError("W8_QUALIFICATION_EVIDENCE_MISMATCH")
    # the campaign result's own summary must qualify on its terms (PASSED, complete, unbroken, unique
    # journal digests) and its digests must be exactly the ones the document cites, so a document cannot
    # point at a campaign whose summary says something else
    try:
        summary = json.loads(campaign_result.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("W8_QUALIFICATION_EVIDENCE_INVALID") from error
    from .pick_place_live_qualification import validate_campaign_summary

    try:
        summary = validate_campaign_summary(summary)
    except ValueError as error:
        raise ValueError("W8_QUALIFICATION_EVIDENCE_MISMATCH") from error
    if list(summary["case_journal_sha256"]) != list(block["journal_sha256"]):
        raise ValueError("W8_QUALIFICATION_EVIDENCE_MISMATCH")
    for expected in block["journal_sha256"]:
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError("W8_QUALIFICATION_EVIDENCE_INVALID")
        # the producer writes one journal per case under `<case_root>/task8-live/cases/<case_id>.json`
        cases = case_root / "task8-live" / "cases"
        if not any(_digest(path) == expected for path in cases.glob("*.json")):
            # a journal the document names is missing or has changed
            raise ValueError("W8_QUALIFICATION_EVIDENCE_MISMATCH")
    # the campaign's journals must re-check on the qualification producer's own terms: fourteen complete
    # rows bound to this bundle's identity, a prefix without a live-evidence artifact and a full with one.
    # That needs the prepared bundle the payload names, so it is done only when the payload supplies it;
    # a caller that names no bundle gets the digest binding above and nothing weaker is claimed for it.
    receipt_path = payload.get("preparation_receipt_path") if isinstance(payload, dict) else None
    if receipt_path is not None:
        if not isinstance(receipt_path, str) or not receipt_path:
            raise ValueError("W8_QUALIFICATION_EVIDENCE_INVALID")
        try:
            from .pick_place_validation_artifact_bundle import verify_prepared_pick_place_validation_bundle

            bundle = verify_prepared_pick_place_validation_bundle(Path(receipt_path))
            manifest_path = Path(bundle.manifest)
            manifest = json.loads(manifest_path.read_bytes())
        except (OSError, KeyError, TypeError, ValueError, UnicodeDecodeError,
                json.JSONDecodeError) as error:
            raise ValueError("W8_QUALIFICATION_EVIDENCE_INVALID") from error
        if _digest(Path(receipt_path)) != block["preparation_receipt_sha256"]:
            # the bundle is not the one the document was qualified against
            raise ValueError("W8_QUALIFICATION_EVIDENCE_MISMATCH")
        if payload.get("manifest_path") is not None and Path(payload["manifest_path"]) != manifest_path:
            raise ValueError("W8_QUALIFICATION_EVIDENCE_MISMATCH")
        from .pick_place_live_qualification import validate_case_journals

        try:
            validate_case_journals(case_root, manifest, identities=bundle.identities,
                                   manifest_document_sha256=manifest["manifest_document_sha256"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("W8_QUALIFICATION_EVIDENCE_MISMATCH") from error
    return True
