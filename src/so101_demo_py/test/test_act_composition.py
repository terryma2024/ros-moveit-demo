"""Task 14: planning needs a mode; executing needs everything, verified."""

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from so101_demo.runtime.act_composition import build_act_session_composition

PACKAGE = Path(__file__).resolve().parents[1]


class _Port:
    def request(self, name, payload):
        return {"ok": True}


class _Inference:
    def submit(self, observation, *, sequence):
        return sequence


def _context():
    from types import SimpleNamespace

    return SimpleNamespace(commander_id="operator-1")


def _artifacts(tmp_path):
    (tmp_path / "policy.bin").write_bytes(b"model")
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps({
        "schema_version": 1, "kind": "act_bundle",
        "model_source": {"name": "act-v1", "sha256": "a" * 64},
        "dataset_sha256": "b" * 64, "config_sha256": "c" * 64, "policy_path": "policy.bin",
        "policy_sha256": hashlib.sha256(b"model").hexdigest(),
        "normalization": {"split": "train", "mean": [0.0] * 6},
        "action": {"chunk_size": 10, "execution_prefix": 1,
                   "temporal_ensembling": False, "tail_padding_mask": True}}))
    calibration = tmp_path / "calibration.json"
    calibration.write_text("{}")
    policy = tmp_path / "policy.json"
    policy.write_text("{}")
    receipt = tmp_path / "receipt.json"
    receipt.write_text("{}")
    runtime = tmp_path / "runtime.yaml"
    runtime.write_text((PACKAGE / "config/act/runtime.yaml").read_text())
    return {"bundle_path": bundle, "calibration_path": calibration, "policy_path": policy,
            "activation_receipt": receipt, "runtime_config": runtime}


def test_planning_modes_need_only_a_mode_and_an_evidence_root(tmp_path):
    for mode in ("dry_run", "plan_only"):
        composition = build_act_session_composition(
            mode=mode, context=_context(), worker_port=_Port(), inference=_Inference(),
            evidence_root=tmp_path)
        assert composition["effects"] is False and composition["artifacts"] == {}
    with pytest.raises(ValueError, match="ACT_SESSION_MODE_INVALID"):
        build_act_session_composition(mode="maybe", context=_context(), worker_port=_Port(),
                                      inference=_Inference(), evidence_root=tmp_path)
    with pytest.raises(ValueError, match="ACT_SESSION_EVIDENCE_ROOT_INVALID"):
        build_act_session_composition(mode="dry_run", context=_context(), worker_port=_Port(),
                                      inference=_Inference(), evidence_root=tmp_path / "absent")


def test_execute_requires_every_artifact_it_will_lean_on(tmp_path):
    artifacts = _artifacts(tmp_path)
    for field, code in (("bundle_path", "ACT_EXECUTE_BUNDLE_REQUIRED"),
                        ("calibration_path", "ACT_EXECUTE_CALIBRATION_REQUIRED"),
                        ("policy_path", "ACT_EXECUTE_POLICY_REQUIRED"),
                        ("activation_receipt", "ACT_EXECUTE_ACTIVATION_REQUIRED"),
                        ("runtime_config", "ACT_EXECUTE_RUNTIME_CONFIG_REQUIRED")):
        missing = {**artifacts, field: None}
        with pytest.raises(ValueError, match=code):
            build_act_session_composition(mode="execute", context=_context(), worker_port=_Port(),
                                          inference=_Inference(), evidence_root=tmp_path, **missing)
    composition = build_act_session_composition(mode="execute", context=_context(),
                                                worker_port=_Port(), inference=_Inference(),
                                                evidence_root=tmp_path, **artifacts)
    assert composition["effects"] is True
    assert composition["bundle"]["kind"] == "act_bundle"
    assert composition["runtime_settings"]["inference"]["device"] == "cuda"

    # a tampered policy is caught here rather than at the first action
    (tmp_path / "policy.bin").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="BUNDLE_POLICY_DIGEST_MISMATCH"):
        build_act_session_composition(mode="execute", context=_context(), worker_port=_Port(),
                                      inference=_Inference(), evidence_root=tmp_path, **artifacts)
