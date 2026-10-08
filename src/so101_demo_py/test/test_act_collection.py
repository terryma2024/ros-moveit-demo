"""Task 11: only a committed, clean, complete success may enter training."""

import json

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


class _Service:
    """A service double: it records what the CLI asked for and nothing else."""

    def __init__(self, *, refuse=False):
        self.calls = []
        self.resets = 0
        self.children = 0
        self._refuse = refuse

    def start(self, payload, scenes):
        self.calls.append({"payload": dict(payload), "scenes": list(scenes)})
        if self._refuse:
            raise ValueError("CAMPAIGN_START_SCHEMA")
        self.resets += len(scenes)
        return {"status": "PASSED", "scenes": len(scenes)}


def _cli_inputs(tmp_path, *, qualification_only=False):
    from so101_demo.act.sampling import SPLITS
    from so101_demo.act.candidate_source import candidate_identity
    from so101_demo.act.sampling import REACHABILITY_GATES

    splits = ("functional", "load") if qualification_only else ("train", "validation", "offline_test")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"scenarios": [{"scene_id": f"act-{name}-{index}",
                                                   "split": name}
                                                  for name in splits for index in range(2)]}))
    files = {}
    for name in ("calibration", "policy", "receipt"):
        path = tmp_path / f"{name}.json"
        path.write_text("{}")
        files[name] = path
    return manifest, files


def test_cli_refuses_before_any_service_exists(tmp_path):
    from so101_demo.cli.act_collect import main

    manifest, files = _cli_inputs(tmp_path)
    built = []

    def factory(payload):
        built.append(payload)
        return _Service()

    argv = ["--manifest", str(manifest), "--calibration", str(files["calibration"]),
            "--policy", str(files["policy"]), "--activation-receipt", str(files["receipt"]),
            "--root", str(tmp_path), "--limit", "2"]
    assert main(argv, service_factory=factory) == 0
    assert len(built) == 1                                   # one payload, one service

    # an absent input refuses with zero side effects: no service was ever constructed
    built.clear()
    with pytest.raises(ValueError, match="COLLECTION_INPUT_UNREADABLE"):
        main([*argv[:1], str(tmp_path / "absent.json"), *argv[2:]], service_factory=factory)
    assert built == []
    # a Rollout-only manifest selects nothing for formal mode, again with no service
    built.clear()
    manifest.write_text(json.dumps({"scenarios": [{"scene_id": "act-r", "split": "rollout_test"}]}))
    with pytest.raises(ValueError, match="COLLECTION_SELECTION_EMPTY"):
        main(argv, service_factory=factory)
    assert built == []


def test_cli_truncates_to_the_limit_and_admission_refusal_leaves_no_side_effects(tmp_path):
    from so101_demo.cli.act_collect import main

    manifest, files = _cli_inputs(tmp_path)
    service = _Service()
    argv = ["--manifest", str(manifest), "--calibration", str(files["calibration"]),
            "--policy", str(files["policy"]), "--activation-receipt", str(files["receipt"]),
            "--root", str(tmp_path), "--limit", "2"]
    assert main(argv, service_factory=lambda payload: service) == 0
    assert service.calls[0]["scenes"] == ["act-train-0", "act-train-1"]   # limit truncates selection
    assert service.calls[0]["payload"]["qualification_mode"] is False

    refusing = _Service(refuse=True)
    with pytest.raises(ValueError, match="CAMPAIGN_START_SCHEMA"):
        main(argv, service_factory=lambda payload: refusing)
    assert refusing.resets == 0 and refusing.children == 0                # zero resets, zero children


def test_cli_qualification_mode_only_takes_qualification_scenes(tmp_path):
    from so101_demo.cli.act_collect import main

    manifest, files = _cli_inputs(tmp_path, qualification_only=True)
    service = _Service()
    argv = ["--manifest", str(manifest), "--calibration", str(files["calibration"]),
            "--policy", str(files["policy"]), "--activation-receipt", str(files["receipt"]),
            "--root", str(tmp_path), "--limit", "3", "--qualification"]
    assert main(argv, service_factory=lambda payload: service) == 0
    call = service.calls[0]
    assert call["payload"]["qualification_mode"] is True
    assert all(scene.split("-")[1] in ("functional", "load") for scene in call["scenes"])
    # a formal-only manifest cannot be collected in qualification mode
    (tmp_path / "formal").mkdir(exist_ok=True)      # the directory must exist before it is written to
    formal_manifest, _ = _cli_inputs(tmp_path / "formal")
    with pytest.raises(ValueError, match="COLLECTION_SELECTION_EMPTY"):
        main([*argv[:1], str(formal_manifest), *argv[2:]],
             service_factory=lambda payload: _Service())
