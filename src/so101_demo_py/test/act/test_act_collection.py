"""Only a committed, clean, complete success may enter training."""

import pytest

from so101_demo.act.collection import training_eligible


def _record(**overrides):
    record = {"status": "PASSED", "qc": "PASS", "done": True, "interventions": 0,
              "coordinator_committed": True}
    record.update(overrides)
    return record


def test_failure_is_retained_but_not_exported():
    assert not training_eligible({"qc": "PASS", "done": False, "interventions": 0})
    assert not training_eligible({"qc": "FAIL", "done": True, "interventions": 0})
    assert not training_eligible({"qc": "PASS", "done": True, "interventions": 0,
                                  "status": "PASSED", "coordinator_committed": False})


def test_only_a_committed_clean_success_is_eligible():
    assert training_eligible(_record())
    for key, value in (("status", "FAILED"), ("qc", "FAIL"), ("done", False),
                       ("interventions", 1), ("coordinator_committed", False)):
        assert not training_eligible(_record(**{key: value})), key
    # an incomplete record is refused, not raised out of: the plan's Step-1 case has exactly this
    # shape and expects False
    assert not training_eligible({"qc": "PASS", "done": True, "interventions": 0})


def test_payload_digests_every_artifact_and_closes_its_keys(tmp_path):
    from so101_demo.act.collection import (
        COLLECTION_PAYLOAD_KEYS, build_collection_payload,
    )

    files = {}
    for name in ("manifest", "calibration", "policy", "receipt"):
        path = tmp_path / f"{name}.json"
        path.write_text("{}")
        files[name] = path
    payload = build_collection_payload(
        campaign_id="campaign-1", manifest_path=files["manifest"],
        calibration_report=files["calibration"], policy=files["policy"],
        activation_receipt=files["receipt"], evidence_root=tmp_path,
        qualification_mode=False, limit=5)
    assert set(payload) == COLLECTION_PAYLOAD_KEYS and payload["backend"] == "mujoco"
    assert payload["manifest_sha256"] and payload["policy_sha256"]
    for bad in ({"limit": 0}, {"qualification_mode": "yes"}):
        with pytest.raises(ValueError):
            build_collection_payload(
                campaign_id="campaign-1", manifest_path=files["manifest"],
                calibration_report=files["calibration"], policy=files["policy"],
                activation_receipt=files["receipt"], evidence_root=tmp_path,
                **{"qualification_mode": False, "limit": 5, **bad})
    with pytest.raises(ValueError, match="COLLECTION_INPUT_UNREADABLE"):
        build_collection_payload(
            campaign_id="campaign-1", manifest_path=tmp_path / "absent.json",
            calibration_report=files["calibration"], policy=files["policy"],
            activation_receipt=files["receipt"], evidence_root=tmp_path,
            qualification_mode=False, limit=5)
    with pytest.raises(ValueError, match="COLLECTION_EVIDENCE_ROOT_INVALID"):
        build_collection_payload(
            campaign_id="campaign-1", manifest_path=files["manifest"],
            calibration_report=files["calibration"], policy=files["policy"],
            activation_receipt=files["receipt"], evidence_root=tmp_path / "absent",
            qualification_mode=False, limit=5)


def test_selection_excludes_rollout_sets_and_separates_qualification():
    from so101_demo.act.collection import require_collection_selection

    scenarios = [{"scene_id": f"act-{name}", "split": name}
                 for name in ("train", "validation", "offline_test", "rollout_validation",
                              "rollout_test")]
    formal = require_collection_selection({"scenarios": scenarios}, qualification_mode=False)
    assert formal == ["act-train", "act-validation", "act-offline_test"]
    # a Rollout row in the manifest is excluded from the selection, not a reason to refuse it
    assert require_collection_selection(
        {"scenarios": scenarios + [{"scene_id": "act-x", "split": "rollout_test"}]},
        qualification_mode=False) == formal
    qualification = {"scenarios": [{"scene_id": "act-functional-1", "split": "functional"},
                                   {"scene_id": "act-load-1", "split": "load"}]}
    assert require_collection_selection(qualification, qualification_mode=True) == [
        "act-functional-1", "act-load-1"]
    # formal mode never collects a qualification scene, and vice versa: each answers with nothing left
    with pytest.raises(ValueError, match="COLLECTION_SELECTION_EMPTY"):
        require_collection_selection(qualification, qualification_mode=False)
    with pytest.raises(ValueError, match="COLLECTION_SELECTION_EMPTY"):
        require_collection_selection({"scenarios": [{"scene_id": "act-t", "split": "train"}]},
                                     qualification_mode=True)
