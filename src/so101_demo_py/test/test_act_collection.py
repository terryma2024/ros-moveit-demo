"""Task 11: only a committed, clean, complete success may enter training."""

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


class _ResetPort:
    def __init__(self, *, ready=True, proof=None, epoch=4):
        self.calls = 0
        # `proof or {...}` would turn the deliberately empty proof into a valid one, so the
        # "unproved reset" case would never reach the guard it is meant to exercise
        self._ready, self._epoch = ready, epoch
        self._proof = {"graph_clear": True} if proof is None else proof

    def reset(self, scenario):
        self.calls += 1
        return {"reset_epoch": self._epoch, "ready": self._ready, "proof": self._proof,
                "scene_sha256": "a" * 64}


class _JointsPort:
    def __init__(self, joints=None):
        self._joints = joints if joints is not None else [0.0] * 7
        self.calls = 0

    def read(self):
        self.calls += 1
        return self._joints


class _PhasePort:
    def __init__(self, *, infra_at=None):
        self.phases = []
        self._infra_at = infra_at

    def run(self, phase, prepared):
        self.phases.append(phase)
        return {"phase": phase, "infra_fault": phase == self._infra_at}


class _Recorder:
    def __init__(self):
        self.rows = []

    def append(self, row):
        self.rows.append(row)


class _QCPort:
    def __init__(self, verdict="PASS"):
        self._verdict = verdict

    def verdict(self, prepared, phases):
        return self._verdict


def _scenario():
    return {"scene_id": "act-abc", "split": "train", "xy": [0.1, 0.0], "arm_q": [0.0] * 6,
            "search_start_rad": 0.0, "seed": 1, "config_sha256": "a" * 64}


def test_prepare_resets_exactly_once_with_a_proved_readback():
    from so101_demo.act.collection import prepare_scenario

    reset, joints = _ResetPort(), _JointsPort()
    prepared = prepare_scenario(_scenario(), reset_port=reset, joints_port=joints)
    assert reset.calls == 1 and joints.calls == 1
    assert prepared["reset_epoch"] == 4 and len(prepared["joints"]) == 7
    with pytest.raises(ValueError, match="SCENARIO_RESET_UNPROVED"):
        prepare_scenario(_scenario(), reset_port=_ResetPort(ready=False), joints_port=joints)
    with pytest.raises(ValueError, match="SCENARIO_RESET_UNPROVED"):
        prepare_scenario(_scenario(), reset_port=_ResetPort(proof={}), joints_port=joints)
    with pytest.raises(ValueError, match="SEVEN_JOINT_READBACK_INVALID"):
        prepare_scenario(_scenario(), reset_port=_ResetPort(),
                         joints_port=_JointsPort(joints=[0.0] * 6))
    with pytest.raises(ValueError, match="SCENARIO_INVALID"):
        prepare_scenario({"scene_id": "act-abc"}, reset_port=reset, joints_port=joints)


def test_collection_runs_the_ordered_phases_without_a_second_reset():
    from so101_demo.act.collection import (
        COLLECTION_PHASES, collect_authorized_scenario, prepare_scenario, training_eligible,
    )

    reset, joints = _ResetPort(), _JointsPort()
    prepared = prepare_scenario(_scenario(), reset_port=reset, joints_port=joints)
    phases, recorder = _PhasePort(), _Recorder()
    record = collect_authorized_scenario(prepared, _scenario(), phase_port=phases,
                                         recorder=recorder, qc_port=_QCPort("PASS"))
    assert phases.phases == list(COLLECTION_PHASES[:-1])       # QC is the verdict, not a phase call
    assert reset.calls == 1                                    # no second reset anywhere
    assert len(recorder.rows) == len(phases.phases)
    assert training_eligible(record)
    failed = collect_authorized_scenario(prepared, _scenario(), phase_port=_PhasePort(),
                                         recorder=_Recorder(), qc_port=_QCPort("FAIL"))
    assert failed["status"] == "FAILED" and not training_eligible(failed)


def test_infrastructure_fault_is_raised_and_never_sealed_as_a_business_failure():
    from so101_demo.act.collection import collect_authorized_scenario, prepare_scenario

    prepared = prepare_scenario(_scenario(), reset_port=_ResetPort(), joints_port=_JointsPort())
    with pytest.raises(RuntimeError, match="COLLECTION_INFRA_FAULT"):
        collect_authorized_scenario(prepared, _scenario(), phase_port=_PhasePort(infra_at="RECORD"),
                                    recorder=_Recorder(), qc_port=_QCPort("PASS"))
    with pytest.raises(ValueError, match="SCENARIO_NOT_PREPARED"):
        collect_authorized_scenario({"scene_id": "other", "split": "train"}, _scenario(),
                                    phase_port=_PhasePort(), recorder=_Recorder(),
                                    qc_port=_QCPort("PASS"))


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
