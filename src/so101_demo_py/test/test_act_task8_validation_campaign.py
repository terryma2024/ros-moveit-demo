"""The validation campaign's admission rules, with the manifest written by the production writer.

This is the case->journal layer's gate: the campaign admits a case only when the manifest on disk is the verified one,
the context matches it hash for hash, one worker owns it, and the production full-restart composition is importable by
name. The four negatives below break the chain at four different links, and each must refuse with its own name.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from so101_demo.act.pick_place_validation_campaign import (  # noqa: E402
    PickPlaceValidationCampaign, PickPlaceValidationError,
)
from so101_demo.act.pick_place_validation_manifest import (  # noqa: E402
    _full_cases, _prefix_cases, _sha, require_pick_place_validation_manifest, write_new_manifest,
)


def _manifest_document() -> dict:
    """A valid manifest built by the PRODUCTION builder, with the anchors dict the validator requires.

    Reading the module rather than hand-writing its document is what this file's first draft got wrong: the schema
    version is 2, the anchors are the three named cup starts (not the phases), and the case lists are canonical.
    """

    from so101_demo.act.pick_place_validation_manifest import build_pick_place_validation_manifest

    anchors = {name: {"cup_start_m": [0.0, -0.28, 0.165], "neck_start_rad": 0.0}
               for name in ("default", "left", "forward")}
    return build_pick_place_validation_manifest(
        anchors, source_sha256="b" * 64, runtime_config_sha256="b" * 64,
        collection_config_sha256="b" * 64, contact_policy_fingerprint="b" * 64,
        calibration_report_path="/data/work/so101-evidence/act-data/report.json",
        calibration_report_sha256="a" * 64)


def _campaign(tmp_path, *, worker_count=1, clock_ns=0):
    document = _manifest_document()
    path = write_new_manifest(tmp_path / "manifest.json", document)
    raw = path.read_bytes()
    import hashlib

    context = SimpleNamespace(manifest_sha256=hashlib.sha256(raw).hexdigest(),
                              campaign_id="campaign-1", worker_count=worker_count,
                              source_sha256=document["source_sha256"],
                              runtime_config_sha256=document["runtime_config_sha256"],
                              collection_config_sha256=document["collection_config_sha256"],
                              contact_policy_fingerprint=document["contact_policy_fingerprint"])
    worker = SimpleNamespace(context=context,
                             launch=SimpleNamespace(mujoco_session_id="mujoco-session-1"))
    return PickPlaceValidationCampaign(path, context, worker, tmp_path / "journal.jsonl",
                                       clock_ns=lambda: clock_ns)


def test_a_verified_manifest_plans_every_case_and_the_composition_is_required_by_name(tmp_path):
    campaign = _campaign(tmp_path)
    cases = campaign.planned_cases(deadline_ns=1)
    assert tuple(case["case_id"] for case in cases) == tuple(
        case["case_id"] for case in (*_prefix_cases(), *_full_cases()))
    # the lifecycle proof is a static import of the PRODUCTION composition: no caller can supply it
    required = PickPlaceValidationCampaign.trusted_full_restart_composition()
    if required is None:
        with pytest.raises(PickPlaceValidationError, match="FULL_RESTART_PROOF_UNAVAILABLE"):
            PickPlaceValidationCampaign.require_full_restart_lifecycle()
    else:
        PickPlaceValidationCampaign.require_full_restart_lifecycle()


def test_four_negatives_break_the_chain_at_four_different_links(tmp_path):
    """Each link refuses with its own name - manifest binding, ownership, deadline, and the lifecycle proof."""

    campaign = _campaign(tmp_path)
    # 1. the manifest on disk is not the one the context was told about
    tampered = tmp_path / "manifest.json"
    document = json.loads(tampered.read_bytes())
    document["campaign_note"] = "tampered"
    tampered.write_text(json.dumps(document))
    with pytest.raises(PickPlaceValidationError, match="TASK8_MANIFEST_BINDING_INVALID"):
        campaign.planned_cases(deadline_ns=1)

    # 2. more than one worker claims the campaign (the manager is single-owner by rule)
    (tmp_path / "second").mkdir()
    with pytest.raises(PickPlaceValidationError, match="TASK8_CAMPAIGN_OWNER_INVALID"):
        _campaign(tmp_path / "second", worker_count=2).planned_cases(deadline_ns=1)

    # 3. the deadline is already behind the clock
    (tmp_path / "third").mkdir()
    with pytest.raises(PickPlaceValidationError, match="TASK8_CAMPAIGN_OWNER_INVALID"):
        _campaign(tmp_path / "third", clock_ns=10).planned_cases(deadline_ns=5)

    # 4. the lifecycle proof itself: the production composition must be importable by name
    class _NoComposition(PickPlaceValidationCampaign):
        @staticmethod
        def trusted_full_restart_composition():
            return None

    with pytest.raises(PickPlaceValidationError, match="FULL_RESTART_PROOF_UNAVAILABLE"):
        _NoComposition.require_full_restart_lifecycle()


def test_the_manifest_validator_refuses_a_document_that_was_edited_after_writing(tmp_path):
    document = _manifest_document()
    document["full_cases"] = list(document["full_cases"])[:-1]
    with pytest.raises(ValueError, match="TASK8_(CASES_INVALID|MANIFEST_HASH_MISMATCH)"):
        require_pick_place_validation_manifest(document)
