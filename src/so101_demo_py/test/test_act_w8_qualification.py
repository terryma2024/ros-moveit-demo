"""The independent W8 verifier refuses anything it cannot re-derive from disk."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

from so101_demo.act.w8_qualification import verify_w8_qualification


def _document(tmp_path, **overrides):
    """A qualified document whose campaign summary and journals really exist on disk."""

    case_root = tmp_path / "campaign"
    case_root.mkdir(parents=True, exist_ok=True)
    digests = []
    for index in range(14):                      # nine prefix cases and five fulls, all distinct
        journal = case_root / f"case-{index}" / "journal.json"
        journal.parent.mkdir(parents=True, exist_ok=True)
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
    assert verify_w8_qualification(path, {}) is True


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
        verify_w8_qualification(path, {})


def test_a_missing_document_refuses(tmp_path):
    with pytest.raises(ValueError, match="W8_QUALIFICATION_EVIDENCE_INVALID"):
        verify_w8_qualification(tmp_path / "absent.json", {})


@pytest.mark.parametrize("payload,code", [
    ({"preparation_receipt_path": ""}, "W8_QUALIFICATION_EVIDENCE_INVALID"),
    ({"preparation_receipt_path": "/nonexistent/receipt.json"}, "W8_QUALIFICATION_EVIDENCE_INVALID"),
])
def test_a_named_bundle_that_cannot_be_opened_refuses(tmp_path, payload, code):
    """CP-2093: when the payload names a bundle it must open, and its evidence must agree.

    The positive path needs a committed prepared bundle; `test_act_task8_artifact_bundle.py`'s `ValidInputs`
    fixture (lines 34-86) is the model for it, and that test belongs with the next increment.
    """

    path, _root = _document(tmp_path)
    with pytest.raises(ValueError, match=code):
        verify_w8_qualification(path, payload)


def test_a_prepared_bundle_yields_the_identities_and_manifest_the_verifier_consumes(tmp_path):
    """CP-2103's first half: the bundle route the verifier's journal delegation depends on."""

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_act_task8_artifact_bundle import _inputs

    from so101_demo.act.task8_artifact_bundle import (
        prepare_task8_bundle, verify_prepared_task8_bundle,
    )

    receipt = prepare_task8_bundle(_inputs(tmp_path), tmp_path / "bundle")
    assert receipt.is_file()
    bundle = verify_prepared_task8_bundle(receipt)
    assert Path(bundle.manifest).is_file()
    assert set(bundle.identities) == {"source_provenance_sha256", "runtime_config_sha256",
                                      "anchors_sha256", "contact_policy_fingerprint",
                                      "act_profile_sha256"}
