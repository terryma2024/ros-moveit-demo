"""Task 12: training runs only past the gates, and always leaves a terminal state."""

import hashlib
import json
from pathlib import Path

import pytest

from so101_demo.act.bundle import export_dataset
from so101_demo.act.training import require_exported_dataset, train_act


def _export(tmp_path):
    committed = tuple({"scene_id": f"act-{index}", "split": "train", "status": "PASSED",
                       "content": {"frames": 2, "state": [0.0] * 8}}
                      for index in range(2))
    output = tmp_path / "dataset"
    export_dataset(committed, output, source_manifest_sha256="a" * 64,
                   campaign_index_sha256="b" * 64)
    return output


def _config():
    return {"schema_version": 1, "kind": "act_training",
            "action": {"chunk_size": 10, "execution_prefix": 1, "temporal_ensembling": False,
                       "tail_padding_mask": True}}


def _owner(tmp_path, *, device="cuda"):
    return {"device": device, "run_root": str(tmp_path)}


def _bundle(_config, _dataset, _output):
    return {"schema_version": 1, "kind": "act_bundle"}


def test_a_run_passes_the_gates_trains_and_records_completion(tmp_path):
    dataset = _export(tmp_path)
    seen = {}

    def trainer(config, path, output):
        seen["dataset"] = path
        return _bundle(config, path, output)

    outcome = train_act(config=_config(), requirements={"status": "RESOLVED"}, dataset=dataset,
                        owner=_owner(tmp_path), output=tmp_path / "bundle.json", trainer=trainer)
    assert outcome["status"] == "COMPLETED" and outcome["episode_count"] == 2
    state = json.loads((tmp_path / "bundle.json.state.json").read_text())
    assert state["status"] == "COMPLETED" and state["error"] is None
    assert seen["dataset"] == dataset
    assert not list(tmp_path.glob("*.partial"))


def test_a_failed_run_leaves_a_failed_state_with_the_error(tmp_path):
    dataset = _export(tmp_path)

    def exploding(_config, _dataset, _output):
        raise RuntimeError("CUDA out of memory")

    with pytest.raises(RuntimeError, match="CUDA out of memory"):
        train_act(config=_config(), requirements={"status": "RESOLVED"}, dataset=dataset,
                  owner=_owner(tmp_path), output=tmp_path / "bundle.json", trainer=exploding)
    state = json.loads((tmp_path / "bundle.json.state.json").read_text())
    assert state["status"] == "FAILED" and "CUDA out of memory" in state["error"]


def test_training_is_refused_before_the_trainer_when_a_gate_fails(tmp_path):
    dataset = _export(tmp_path)
    calls = []

    def trainer(*_args):
        calls.append(True)
        return _bundle(*_args)

    with pytest.raises(ValueError, match="TRAINING_REQUIREMENTS_UNRESOLVED"):
        train_act(config=_config(), requirements={"status": "UNRESOLVED"}, dataset=dataset,
                  owner=_owner(tmp_path), output=tmp_path / "b.json", trainer=trainer)
    with pytest.raises(ValueError, match="TRAINING_OWNER_NOT_CUDA"):
        train_act(config=_config(), requirements={"status": "RESOLVED"}, dataset=dataset,
                  owner=_owner(tmp_path, device="cpu"), output=tmp_path / "b.json", trainer=trainer)
    assert calls == []                                    # no trainer ever ran

    # a tampered episode is caught before training, not during it
    victim = dataset / "episodes" / "act-0.json"
    victim.write_text(json.dumps({"tampered": True}))
    with pytest.raises(ValueError, match="TRAINING_EPISODE_DIGEST_MISMATCH"):
        require_exported_dataset(dataset)
    with pytest.raises(ValueError, match="TRAINING_EPISODE_DIGEST_MISMATCH"):
        train_act(config=_config(), requirements={"status": "RESOLVED"}, dataset=dataset,
                  owner=_owner(tmp_path), output=tmp_path / "b.json", trainer=trainer)
    assert calls == []
    with pytest.raises(ValueError, match="TRAINING_DATASET_NOT_EXPORTED"):
        require_exported_dataset(tmp_path / "absent")
