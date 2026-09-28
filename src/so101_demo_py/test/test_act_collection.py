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


def test_one_reset_per_attempt_and_a_terminal_state_nothing_overwrites():
    from so101_demo.act.collection import (
        AttemptLedger, collect_authorized_scenario, prepare_scenario,
    )

    ledger = AttemptLedger()
    reset, joints = _ResetPort(), _JointsPort()
    prepared = prepare_scenario(_scenario(), reset_port=reset, joints_port=joints, ledger=ledger,
                                attempt_id="attempt-1")
    with pytest.raises(ValueError, match="SCENARIO_RESET_ALREADY_PERFORMED"):
        prepare_scenario(_scenario(), reset_port=reset, joints_port=joints, ledger=ledger,
                         attempt_id="attempt-1")
    assert reset.calls == 1                                   # one reset per attempt, never two

    record = collect_authorized_scenario(prepared, _scenario(), phase_port=_PhasePort(),
                                         recorder=_Recorder(), qc_port=_QCPort("PASS"),
                                         ledger=ledger)
    sealed = ledger.terminal("act-abc")
    assert sealed == record and sealed["status"] == "PASSED"
    with pytest.raises(ValueError, match="SCENE_TERMINAL_STATE_IMMUTABLE"):
        collect_authorized_scenario(prepared, _scenario(), phase_port=_PhasePort(),
                                    recorder=_Recorder(), qc_port=_QCPort("FAIL"), ledger=ledger)
    assert ledger.terminal("act-abc") == record                # the terminal state did not change
    with pytest.raises(ValueError, match="SCENE_TERMINAL_STATE_IMMUTABLE"):
        prepare_scenario(_scenario(), reset_port=reset, joints_port=joints, ledger=ledger,
                         attempt_id="attempt-2")


def test_a_persistence_failure_surfaces_as_infra_and_seals_nothing():
    from so101_demo.act.collection import (
        AttemptLedger, collect_authorized_scenario, prepare_scenario, training_eligible,
    )

    class FailingRecorder:
        def append(self, row):
            raise OSError("recorder queue full")

    ledger = AttemptLedger()
    prepared = prepare_scenario(_scenario(), reset_port=_ResetPort(), joints_port=_JointsPort(),
                                ledger=ledger)
    with pytest.raises(OSError, match="recorder queue full"):
        collect_authorized_scenario(prepared, _scenario(), phase_port=_PhasePort(),
                                    recorder=FailingRecorder(), qc_port=_QCPort("PASS"),
                                    ledger=ledger)
    # a recorder fault must not become a business FAILED, and must not seal a terminal state
    assert ledger.terminal("act-abc") is None
    assert not training_eligible({"status": "FAILED", "qc": "PASS", "done": True,
                                  "interventions": 0, "coordinator_committed": True})
