"""Task 12 CLI: refuse before writing anything, then train one owned job."""

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from so101_demo.cli.act_train import main

SOURCE_LOCK = Path(__file__).resolve().parents[1] / "config/act/requirements.lock"


def _workspace(tmp_path, *, episodes=2):
    manifest = {"episodes": [{"scene_id": f"act-{index}", "status": "PASSED", "split": "train"}
                             for index in range(episodes)]}
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    entries = []
    for index in range(episodes):
        content = tmp_path / f"episode-{index}.json"
        content.write_text(json.dumps({"frames": 2, "state": [0.0] * 8}))
        entries.append({"scene_id": f"act-{index}", "journal_sha256": "a" * 64,
                        "verifier_sha256": "a" * 64, "content_path": content.name,
                        "content_sha256": hashlib.sha256(content.read_bytes()).hexdigest()})
    index = {"committed_episodes": entries}
    index_path = tmp_path / "campaign-index.json"
    index_path.write_text(json.dumps(index))
    binding = tmp_path / "gpu-binding.json"
    binding.write_text("{}")
    config = tmp_path / "training.yaml"
    config.write_text(yaml.safe_dump(yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "config/act/training.yaml").read_text())))
    return manifest_path, index_path, binding, config


def _argv(manifest, index, binding, config, output):
    return ["--manifest", str(manifest), "--campaign-index", str(index),
            "--gpu-binding", str(binding), "--config", str(config),
            "--output", str(output), "--device", "cuda"]


def _resolved_lock(tmp_path):
    path = tmp_path / "requirements.lock"
    path.write_text(yaml.safe_dump({"schema_version": 1, "kind": "act_training_requirements",
                                    "status": "RESOLVED",
                                    "resolver": {"python": "3.12.3", "resolved_at": "2026-09-24T00:00:00Z",
                                                 "index_sha256": "a" * 64},
                                    "packages": [{"name": "torch", "version": "2.7.0",
                                                  "sha256": "b" * 64}]}))
    return path


def test_the_cli_exports_trains_and_records_the_run(tmp_path, capsys, monkeypatch):
    manifest, index, binding, config = _workspace(tmp_path)
    output = tmp_path / "bundle.json"
    # the shipped lock is deliberately unresolved: a training run cannot start against it
    with pytest.raises(ValueError, match="TRAINING_REQUIREMENTS_UNRESOLVED"):
        main(_argv(manifest, index, binding, config, output),
             trainer=lambda *_a: {"kind": "act_bundle"}, owner_factory=lambda **_: {},
             requirements_path=SOURCE_LOCK)
    assert not output.exists() and not (tmp_path / "bundle.json.dataset").exists()
    with pytest.raises(ValueError, match="TRAINING_DEVICE_INVALID"):
        main([*_argv(manifest, index, binding, config, output)[:-1], "cpu"],
             trainer=lambda *_a: {"kind": "act_bundle"}, owner_factory=lambda **_: {})

    # with a resolved lock and an owner, the whole path runs and leaves a terminal state
    requirements_path = _resolved_lock(tmp_path)
    owner = {"device": "cuda", "run_root": str(tmp_path)}
    assert main(_argv(manifest, index, binding, config, output),
                trainer=lambda config, dataset, out: {"schema_version": 1, "kind": "act_bundle"},
                owner_factory=lambda **_: owner, requirements_path=requirements_path) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == "COMPLETED" and printed["episode_count"] == 2
    assert (tmp_path / "bundle.json.dataset" / "export-manifest.json").is_file()
    assert json.loads((tmp_path / "bundle.json.state.json").read_text())["status"] == "COMPLETED"


def test_the_production_trainer_fails_closed_and_never_overwrites_an_output(tmp_path):
    from so101_demo.cli.act_train import _trainer

    with pytest.raises(ValueError, match="TRAINING_(INTERPRETER_REQUIRED|ADAPTER_UNAVAILABLE)"):
        _trainer({}, tmp_path, tmp_path / "out")
    manifest, index, binding, config = _workspace(tmp_path)
    output = tmp_path / "bundle.json"
    output.write_text("{}")
    with pytest.raises(ValueError, match="TRAINING_OUTPUT_EXISTS"):
        main(_argv(manifest, index, binding, config, output),
             trainer=lambda *_a: {"kind": "act_bundle"},
             owner_factory=lambda **_: {"device": "cuda", "run_root": str(tmp_path)},
             requirements_path=_resolved_lock(tmp_path))
