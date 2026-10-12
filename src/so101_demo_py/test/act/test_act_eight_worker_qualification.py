"""The pick-place live qualification documents are not collection qualification evidence.

The old eight-worker verifier (`verify_eight_worker_qualification`) is gone: a `QUALIFIED` document with a `live_campaign` block
is the pick-place live shape, and the collection verifier (`verify_collection_qualification`) refuses it at its closed form check
before it reads anything else. The tests that only exercise the pick-place bundle and journal helpers are unchanged.
"""

import hashlib
import json
from pathlib import Path

import pytest

from so101_demo.act import parallel_qualification_verifier as verifier
from so101_demo.act.parallel_qualification_verifier import verify_collection_qualification
from so101_demo.runtime.container_campaign.paths import make_campaign_paths

REFUSED = "COLLECTION_QUALIFICATION_"


def _document(tmp_path, **overrides):
    """A pick-place live document whose campaign summary and journals really exist on disk, placed at a registered run's report path."""

    registered = tmp_path / "registered"
    registered.mkdir(exist_ok=True)
    run = make_campaign_paths(registered, "run-1")["run"]
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
    path = run / "host" / "qualification-report.json"
    path.write_text(json.dumps(document))
    return path, registered, case_root


def _refused(path, registered, code=REFUSED + "REPORT_INVALID"):
    with pytest.raises(ValueError, match=code):
        verify_collection_qualification(path, registered_root=registered, expected_identity=None)


def test_the_old_verifier_is_gone():
    assert not hasattr(verifier, "verify_eight_worker_qualification")


def test_a_pick_place_document_whose_evidence_re_derives_is_still_refused(tmp_path):
    """Before: the old verifier returned True for this document. After: it is not a collection report."""
    path, registered, _root = _document(tmp_path)
    _refused(path, registered)


@pytest.mark.parametrize("mutation", [
    lambda doc, root: doc.update({"status": "PASSED"}),
    lambda doc, root: doc.update({"worker_count": 4}),
    lambda doc, root: doc.pop("live_campaign"),
    lambda doc, root: doc["live_campaign"].update({"journal_sha256": []}),
    lambda doc, root: doc["live_campaign"].update({"campaign_result_sha256": "f" * 64}),
    lambda doc, root: doc["live_campaign"].update({"journal_sha256": ["a" * 64]}),
    lambda doc, root: doc["live_campaign"].update({"case_root": str(root / "gone")}),
], ids=["passed_word", "four_workers", "no_live_block", "no_journals", "result_digest", "journal_digest", "case_root"])
def test_every_mutation_of_a_pick_place_document_stays_refused(tmp_path, mutation):
    """Before: each mutation selected one old verifier code. After: the closed form check refuses all of them alike."""
    path, registered, root = _document(tmp_path)
    document = json.loads(path.read_text())
    mutation(document, root)
    path.write_text(json.dumps(document))
    _refused(path, registered)


def test_a_missing_document_refuses(tmp_path):
    registered = tmp_path / "registered"
    registered.mkdir()
    _refused(registered / "run-1" / "host" / "qualification-report.json", registered, REFUSED + "PATH_INVALID")


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


def test_a_complete_pick_place_document_over_a_prepared_bundle_is_refused(tmp_path):
    """Before: a fully valid pick-place document over a prepared bundle verified. After: the collection verifier refuses it."""

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
    registered = tmp_path / "registered"
    registered.mkdir()
    path = make_campaign_paths(registered, "run-1")["run"] / "host" / "qualification-report.json"
    path.write_text(json.dumps(document))
    _refused(path, registered)
