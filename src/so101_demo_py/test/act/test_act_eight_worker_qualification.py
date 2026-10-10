"""The independent W8 verifier refuses anything it cannot re-derive from disk."""

import hashlib
import json
from pathlib import Path

import pytest

from so101_demo.act.parallel_qualification_verifier import verify_eight_worker_qualification


def _document(tmp_path, **overrides):
    """A qualified document whose campaign summary and journals really exist on disk."""

    case_root = tmp_path / "campaign"
    case_root.mkdir(parents=True, exist_ok=True)
    digests = []
    cases = case_root / "pick-place-live" / "cases"
    cases.mkdir(parents=True, exist_ok=True)
    for index in range(14):                      # nine prefix cases and five fulls, all distinct
        journal = cases / f"{'prefix' if index < 9 else 'full'}-{index % 9 + 1:02d}.json"
        journal.write_bytes(json.dumps({"case": index}).encode())
        digests.append(hashlib.sha256(journal.read_bytes()).hexdigest())
    campaign = case_root / "campaign-result.json"
    campaign.write_bytes(json.dumps({"status": "PASSED", "prefix_count": 9,
                                     "consecutive_full_count": 5,
                                     "case_journal_sha256": digests}).encode())
    document = {"status": "QUALIFIED", "worker_count": 8,
                "live_campaign": {
                    "case_root": str(case_root),
                    "campaign_result_sha256": hashlib.sha256(campaign.read_bytes()).hexdigest(),
                    "preparation_receipt_sha256": "0" * 64,
                    "journal_sha256": digests}}
    document.update(overrides)
    path = tmp_path / "qualified.json"
    path.write_text(json.dumps(document))
    return path, case_root


def test_a_document_whose_evidence_re_derives_verifies(tmp_path):
    path, _root = _document(tmp_path)
    assert verify_eight_worker_qualification(path, {}) is True


@pytest.mark.parametrize("mutation,code", [
    (lambda doc, root: doc.update({"status": "PASSED"}), "W8_QUALIFICATION_EVIDENCE_INVALID"),
    (lambda doc, root: doc.update({"worker_count": 4}), "W8_QUALIFICATION_EVIDENCE_INVALID"),
    (lambda doc, root: doc.pop("live_campaign"), "W8_QUALIFICATION_EVIDENCE_INVALID"),
    (lambda doc, root: doc["live_campaign"].update({"journal_sha256": []}),
     "W8_QUALIFICATION_EVIDENCE_INVALID"),
    (lambda doc, root: doc["live_campaign"].update({"campaign_result_sha256": "f" * 64}),
     "W8_QUALIFICATION_EVIDENCE_MISMATCH"),
    (lambda doc, root: doc["live_campaign"].update({"journal_sha256": ["a" * 64]}),
     "W8_QUALIFICATION_EVIDENCE_MISMATCH"),
    (lambda doc, root: doc["live_campaign"].update({"case_root": str(root / "gone")}),
     "W8_QUALIFICATION_EVIDENCE_INVALID"),
])
def test_the_verifier_refuses_what_it_cannot_re_derive(tmp_path, mutation, code):
    path, root = _document(tmp_path)
    document = json.loads(path.read_text())
    mutation(document, root)
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match=code):
        verify_eight_worker_qualification(path, {})


def test_a_missing_document_refuses(tmp_path):
    with pytest.raises(ValueError, match="W8_QUALIFICATION_EVIDENCE_INVALID"):
        verify_eight_worker_qualification(tmp_path / "absent.json", {})


@pytest.mark.parametrize("payload,code", [
    ({"preparation_receipt_path": ""}, "W8_QUALIFICATION_EVIDENCE_INVALID"),
    ({"preparation_receipt_path": "/nonexistent/receipt.json"}, "W8_QUALIFICATION_EVIDENCE_INVALID"),
])
def test_a_named_bundle_that_cannot_be_opened_refuses(tmp_path, payload, code):
    """When the payload names a bundle it must open, and its evidence must agree.

    The positive path needs a committed prepared bundle; `test_act_pick_place_validation_artifact_bundle.py`'s `ValidInputs`
    fixture (lines 34-86) is the model for it, and that test belongs with the next increment.
    """

    path, _root = _document(tmp_path)
    with pytest.raises(ValueError, match=code):
        verify_eight_worker_qualification(path, payload)


def test_a_prepared_bundle_yields_the_identities_and_manifest_the_verifier_consumes(tmp_path):
    """First half: the bundle route the verifier's journal delegation depends on."""

    from test_act_pick_place_validation_artifact_bundle import _inputs

    from so101_demo.act.pick_place_validation_artifact_bundle import (
        prepare_pick_place_validation_bundle, verify_prepared_pick_place_validation_bundle,
    )

    receipt = prepare_pick_place_validation_bundle(_inputs(tmp_path), tmp_path / "bundle")
    assert receipt.is_file()
    bundle = verify_prepared_pick_place_validation_bundle(receipt)
    assert Path(bundle.manifest).is_file()
    assert set(bundle.identities) == {"source_provenance_sha256", "runtime_config_sha256",
                                      "anchors_sha256", "contact_policy_fingerprint",
                                      "act_profile_sha256"}


def test_journal_rows_for_a_prepared_bundle_can_be_built_and_match_it(tmp_path):
    """Second half, one step at a time: a prefix and a full row for real identities."""

    from test_act_pick_place_validation_artifact_bundle import _inputs

    from so101_demo.act.pick_place_validation_artifact_bundle import (
        prepare_pick_place_validation_bundle, verify_prepared_pick_place_validation_bundle,
    )
    from so101_demo.act.pick_place_live_evidence import (
        case_row_to_journal_row, require_case_row_matches_bundle,
    )

    receipt = prepare_pick_place_validation_bundle(_inputs(tmp_path), tmp_path / "bundle")
    bundle = verify_prepared_pick_place_validation_bundle(receipt)
    manifest = json.loads(Path(bundle.manifest).read_bytes())
    document_sha = manifest["manifest_document_sha256"]
    evidence = tmp_path / "full-01.json"
    evidence.write_bytes(b'{"case": "full-01"}')
    child = tmp_path / "child-receipt.json"
    stack = tmp_path / "stack-receipt.json"
    for path in (child, stack):
        path.write_bytes(b'{"retired": true}')

    def published(case_id, mode, live_path):
        return {"case_id": case_id, "mode": mode, "status": "PASSED",
                "live_evidence_path": live_path,
                "live_evidence_sha256": (hashlib.sha256(Path(live_path).read_bytes()).hexdigest()
                                         if live_path else "0" * 64),
                "child_retirement_receipt_path": str(child),
                "child_receipt_sha256": hashlib.sha256(child.read_bytes()).hexdigest(),
                "stack_retirement_receipt_path": str(stack),
                "stack_receipt_sha256": hashlib.sha256(stack.read_bytes()).hexdigest()}

    # the journal vocabulary is `phase_prefix` for a case without a live artifact and `full` for one with it
    for mode, live in (("phase_prefix", ""), ("full", str(evidence))):
        case_id = f"{'prefix' if mode == 'phase_prefix' else 'full'}-01"
        row = case_row_to_journal_row(published(case_id, mode, live),
                                      identities=bundle.identities,
                                      manifest_document_sha256=document_sha)
        require_case_row_matches_bundle(row, identities=bundle.identities,
                                        manifest_document_sha256=document_sha)


def test_a_qualified_document_over_a_prepared_bundle_and_fourteen_journals_verifies(tmp_path):
    """The verifier's positive path, end to end."""

    from test_act_pick_place_validation_artifact_bundle import _inputs

    from so101_demo.act.pick_place_validation_artifact_bundle import (
        prepare_pick_place_validation_bundle, verify_prepared_pick_place_validation_bundle,
    )
    from so101_demo.act.pick_place_live_evidence import (
        case_row_to_journal_row, require_case_row_matches_bundle,
    )

    prefixes = [f"prefix-{index:02d}" for index in range(1, 10)]
    fulls = [f"full-{index:02d}" for index in range(1, 6)]
    inputs = _inputs(tmp_path)
    # the frozen manifest lists cases as objects with a `case_id` whose shape is `[a-z]+-NN`
    inputs.manifest.write_text(json.dumps({
        "schema_version": 2, "kind": "ACT_PICK_PLACE_VALIDATION", "manifest_sha256": "f" * 64,
        "prefix_cases": [{"case_id": case_id} for case_id in prefixes],
        "full_cases": [{"case_id": case_id} for case_id in fulls]}))
    receipt = prepare_pick_place_validation_bundle(inputs, tmp_path / "bundle")
    bundle = verify_prepared_pick_place_validation_bundle(receipt)
    manifest = json.loads(Path(bundle.manifest).read_bytes())
    document_sha = manifest["manifest_document_sha256"]
    case_root = tmp_path / "campaign"
    child = tmp_path / "child.json"
    stack = tmp_path / "stack.json"
    child.write_bytes(b'{"retired": "child"}')
    stack.write_bytes(b'{"retired": "stack"}')
    digests = []
    cases = case_root / "pick-place-live" / "cases"
    cases.mkdir(parents=True, exist_ok=True)
    for case_id in prefixes + fulls:
        directory = cases
        evidence = tmp_path / f"{case_id}-live.json"
        mode = "full" if case_id in fulls else "phase_prefix"
        if mode == "full":
            evidence.write_bytes(json.dumps({"case": case_id}).encode())
            live_path, live_digest = str(evidence), hashlib.sha256(evidence.read_bytes()).hexdigest()
        else:
            live_path, live_digest = "", "0" * 64
        row = case_row_to_journal_row(
            {"case_id": case_id, "mode": mode, "status": "PASSED",
             "live_evidence_path": live_path, "live_evidence_sha256": live_digest,
             "child_retirement_receipt_path": str(child),
             "child_receipt_sha256": hashlib.sha256(child.read_bytes()).hexdigest(),
             "stack_retirement_receipt_path": str(stack),
             "stack_receipt_sha256": hashlib.sha256(stack.read_bytes()).hexdigest()},
            identities=bundle.identities, manifest_document_sha256=document_sha)
        require_case_row_matches_bundle(row, identities=bundle.identities,
                                        manifest_document_sha256=document_sha)
        journal = cases / f"{case_id}.json"
        journal.write_bytes(json.dumps(row).encode())
        digests.append(hashlib.sha256(journal.read_bytes()).hexdigest())
    campaign = case_root / "campaign-result.json"
    campaign.write_bytes(json.dumps({"status": "PASSED", "prefix_count": len(prefixes),
                                     "consecutive_full_count": len(fulls),
                                     "case_journal_sha256": digests}).encode())
    document = {"status": "QUALIFIED", "worker_count": 8,
                "live_campaign": {"case_root": str(case_root),
                                  "campaign_result_sha256": hashlib.sha256(campaign.read_bytes()).hexdigest(),
                                  "preparation_receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
                                  "journal_sha256": digests}}
    path = tmp_path / "qualified.json"
    path.write_text(json.dumps(document))
    payload = {"preparation_receipt_path": str(receipt), "manifest_path": str(bundle.manifest)}
    assert verify_eight_worker_qualification(path, payload) is True
    # one variable: a journal edited after sealing is no longer the one the document cites
    sealed = cases / f"{fulls[0]}.json"
    sealed.write_bytes(sealed.read_bytes().replace(b'"PASSED"', b'"FAILED"'))
    with pytest.raises(ValueError, match="W8_QUALIFICATION_EVIDENCE_MISMATCH"):
        verify_eight_worker_qualification(path, payload)
