"""CLI: refuse before writing anything, then train one owned job."""

import hashlib
import importlib.util
import json

import pytest
import yaml

from so101_demo.act.training_requirements import require_resolved_requirements
from so101_demo.cli.act_train import main
from paths import PACKAGE_ROOT

SOURCE_LOCK = PACKAGE_ROOT / "config/act/requirements.lock"


def _workspace(tmp_path,monkeypatch, *, episodes=2):
    from act_export_fixture import complete_export_entries
    manifest = {"episodes": [{"scene_id": f"act-{index}", "status": "PASSED", "split": "train"}
                             for index in range(episodes)]}
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    entries=[{key:value for key,value in entry.items() if key!='content'} for entry in
        complete_export_entries(tmp_path,monkeypatch,tuple(f'act-{index}' for index in range(episodes)))]
    index = {"schema_version":2,"committed_episodes": entries}
    index_path = tmp_path / "campaign-index.json"
    index_path.write_text(json.dumps(index))
    binding = tmp_path / "gpu-binding.json"
    binding.write_text("{}")
    config = tmp_path / "training.yaml"
    config.write_text(yaml.safe_dump(yaml.safe_load(
        (PACKAGE_ROOT / "config/act/training.yaml").read_text())))
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
    manifest, index, binding, config = _workspace(tmp_path,monkeypatch)
    output = tmp_path / "bundle.json"
    # an unresolved lock is what blocks a training run. The shipped lock used to be that blocker; now that a
    # training interpreter has resolved it, the refusal is exercised with a synthetic unresolved lock and the
    # shipped one is asserted to pass the gate.
    unresolved = tmp_path / "requirements-unresolved.lock"
    unresolved.write_text(yaml.safe_dump({"schema_version": 1, "kind": "act_training_requirements",
                                          "status": "UNRESOLVED", "resolver": None, "packages": []},
                                         sort_keys=False))
    with pytest.raises(ValueError, match="TRAINING_REQUIREMENTS_UNRESOLVED"):
        main(_argv(manifest, index, binding, config, output),
             trainer=lambda *_a: {"kind": "act_bundle"}, owner_factory=lambda **_: {},
             requirements_path=unresolved)
    assert not output.exists() and not (tmp_path / "bundle.json.dataset").exists()
    assert require_resolved_requirements(SOURCE_LOCK)["status"] == "RESOLVED"
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


def test_the_production_trainer_fails_closed_and_never_overwrites_an_output(tmp_path,monkeypatch):
    from so101_demo.cli.act_train import _trainer

    if importlib.util.find_spec("torch") is not None:
        pytest.skip("this asserts the torch-free refusal; the training interpreter has torch")
    with pytest.raises(ValueError, match="TRAINING_(INTERPRETER_REQUIRED|ADAPTER_UNAVAILABLE)"):
        _trainer({}, tmp_path, tmp_path / "out")
    manifest, index, binding, config = _workspace(tmp_path,monkeypatch)
    output = tmp_path / "bundle.json"
    output.write_text("{}")
    with pytest.raises(ValueError, match="TRAINING_OUTPUT_EXISTS"):
        main(_argv(manifest, index, binding, config, output),
             trainer=lambda *_a: {"kind": "act_bundle"},
             owner_factory=lambda **_: {"device": "cuda", "run_root": str(tmp_path)},
             requirements_path=_resolved_lock(tmp_path))


# ---- design 2026-10-10 section 3.0 items 2-3: the requirements digest and the CUDA owner lease factory -----------------------------


def test_the_production_trainer_receives_the_requirements_lock_digest(tmp_path, monkeypatch):
    import so101_demo.cli.act_train as cli
    manifest, index, binding, config = _workspace(tmp_path, monkeypatch)
    lock = _resolved_lock(tmp_path)
    seen = {}

    def recorder(config_, dataset, output, *, requirements_sha256=None, backbone_weights=None):
        seen.update(requirements_sha256=requirements_sha256, dataset=dataset, output=output)
        return {"schema_version": 1, "kind": "act_bundle"}
    monkeypatch.setattr(cli, "_trainer", recorder)
    owner = {"device": "cuda", "run_root": str(tmp_path)}
    assert cli.main(_argv(manifest, index, binding, config, tmp_path / "bundle"), owner_factory=lambda **_: owner,
                    requirements_path=lock) == 0
    assert seen["requirements_sha256"] == hashlib.sha256(lock.read_bytes()).hexdigest()
    assert seen["output"] == tmp_path / "bundle"


def test_the_production_trainer_refuses_to_run_without_the_requirements_digest(tmp_path):
    from so101_demo.cli.act_train import _trainer

    pytest.importorskip("torch")
    from so101_demo.act.training_config import load_training_config
    shipped = load_training_config(PACKAGE_ROOT / "config/act/training.yaml")
    with pytest.raises(ValueError, match="TRAINING_REQUIREMENTS_SHA256_INVALID"):
        _trainer(shipped, tmp_path, tmp_path / "out")


class _Binding:
    DOCUMENT = {"device": "cuda", "binding_id": "train-binding-1", "leases": []}


def _binding_file(tmp_path, document=None):
    path = tmp_path / "train-gpu-binding.json"
    path.write_text(json.dumps(document or _Binding.DOCUMENT))
    return path


def test_the_cuda_owner_factory_claims_the_run_root_through_the_training_owner(tmp_path):
    from so101_demo.cli.act_train import local_owner_factory

    class Idle:
        def state(self):
            return "IDLE"
    run_root = tmp_path / "bundle.run"
    factory = local_owner_factory(_binding_file(tmp_path), run_root, arbiter=Idle(), identity=lambda: {"pid": 4242, "started_ticks": 99})
    owner = factory(dataset_sha256="a" * 64, config_sha256="b" * 64)
    assert owner["device"] == "cuda" and owner["run_root"] == str(run_root) and owner["gpu_binding_id"] == "train-binding-1"
    receipt = json.loads((run_root / "training-owner.json").read_text())
    assert receipt["dataset_sha256"] == "a" * 64 and receipt["config_sha256"] == "b" * 64 and receipt["owner_pid"] == 4242


def test_the_cuda_owner_factory_refuses_a_busy_gpu_a_bad_binding_and_an_unreadable_arbiter(tmp_path):
    from so101_demo.cli.act_train import local_owner_factory

    class Busy:
        def state(self):
            return "BUSY"
    ident = lambda: {"pid": 1, "started_ticks": 1}  # noqa: E731
    with pytest.raises(ValueError, match="TRAINING_ARBITER_BUSY"):
        local_owner_factory(_binding_file(tmp_path), tmp_path / "a.run", arbiter=Busy(), identity=ident)(
            dataset_sha256="a" * 64, config_sha256="b" * 64)
    with pytest.raises(ValueError, match="TRAINING_GPU_BUSY"):
        local_owner_factory(_binding_file(tmp_path, {**_Binding.DOCUMENT, "leases": [{"kind": "collection"}]}), tmp_path / "b.run",
                            arbiter=type("I", (), {"state": lambda self: "IDLE"})(), identity=ident)(
            dataset_sha256="a" * 64, config_sha256="b" * 64)
    with pytest.raises(ValueError, match="TRAINING_GPU_LEASE_INVALID"):
        local_owner_factory(tmp_path / "absent.json", tmp_path / "c.run", arbiter=Busy(), identity=ident)(
            dataset_sha256="a" * 64, config_sha256="b" * 64)
    assert not (tmp_path / "bundle.run" / "training-owner.json").exists()


def test_the_process_table_arbiter_is_idle_only_when_no_process_holds_a_compute_context():
    from so101_demo.cli.act_train import ProcessTableArbiter

    assert ProcessTableArbiter(runner=lambda: "").state() == "IDLE"
    assert ProcessTableArbiter(runner=lambda: "\n").state() == "IDLE"
    assert ProcessTableArbiter(runner=lambda: "4242\n").state() == "BUSY"

    def broken():
        raise OSError("nvidia-smi missing")
    with pytest.raises(ValueError, match="TRAINING_ARBITER_UNAVAILABLE"):
        ProcessTableArbiter(runner=broken).state()


def test_main_builds_its_owner_from_the_gpu_binding_when_no_factory_is_injected(tmp_path, monkeypatch):
    import so101_demo.cli.act_train as cli
    manifest, index, binding, config = _workspace(tmp_path, monkeypatch)
    seen = {}

    def factory_builder(gpu_binding, run_root):
        seen.update(binding=gpu_binding, run_root=run_root)
        return lambda **_: {"device": "cuda", "run_root": str(tmp_path)}
    monkeypatch.setattr(cli, "local_owner_factory", factory_builder)
    assert cli.main(_argv(manifest, index, binding, config, tmp_path / "bundle"), trainer=lambda *_a: {"kind": "act_bundle"},
                    requirements_path=_resolved_lock(tmp_path)) == 0
    assert seen == {"binding": binding, "run_root": tmp_path / "bundle.run"}


def test_the_default_requirements_lock_exists_and_is_a_resolved_lock():
    from so101_demo.cli.act_train import REQUIREMENTS_LOCK, default_requirements_lock

    assert REQUIREMENTS_LOCK.is_file() and default_requirements_lock() == REQUIREMENTS_LOCK
    assert require_resolved_requirements(REQUIREMENTS_LOCK)["status"] == "RESOLVED"
    assert REQUIREMENTS_LOCK.read_bytes() == SOURCE_LOCK.read_bytes()


def test_the_default_lock_falls_back_to_the_installed_share_layout(tmp_path, monkeypatch):
    import sys
    import types

    from so101_demo.cli import act_train

    share = tmp_path / "share"
    (share / "config/act").mkdir(parents=True)
    (share / "config/act/requirements.lock").write_text("x")
    module = types.ModuleType("ament_index_python.packages")
    module.get_package_share_directory = lambda name: str(share)
    monkeypatch.setitem(sys.modules, "ament_index_python", types.ModuleType("ament_index_python"))
    monkeypatch.setitem(sys.modules, "ament_index_python.packages", module)
    monkeypatch.setattr(act_train, "_SOURCE_ROOT", tmp_path / "absent")          # not a source tree
    assert act_train.default_requirements_lock() == share / "config/act/requirements.lock"


def test_the_cli_hands_the_backbone_weights_path_to_the_trainer(tmp_path, monkeypatch):
    import so101_demo.cli.act_train as cli
    manifest, index, binding, config = _workspace(tmp_path, monkeypatch)
    seen = {}

    def recorder(config_, dataset, output, *, requirements_sha256=None, backbone_weights=None):
        seen["weights"] = backbone_weights
        return {"schema_version": 1, "kind": "act_bundle"}
    monkeypatch.setattr(cli, "_trainer", recorder)
    owner = {"device": "cuda", "run_root": str(tmp_path)}
    weights = tmp_path / "resnet18.pth"
    assert cli.main([*_argv(manifest, index, binding, config, tmp_path / "bundle"), "--backbone-weights", str(weights)],
                    owner_factory=lambda **_: owner, requirements_path=_resolved_lock(tmp_path)) == 0
    assert seen["weights"] == weights


# ---- evidence-partition layout (2026-10-18): dataset and policy live outside the evidence root, the run directory in evidence records them ----


def _sha256_of(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_dataset_output_and_evidence_dir_place_the_export_apart_and_record_it(tmp_path, monkeypatch):
    import so101_demo.cli.act_train as cli
    manifest, index, binding, config = _workspace(tmp_path, monkeypatch)
    datasets = tmp_path / "datasets" / "merged-v2"
    policies = tmp_path / "policies" / "run-1"
    policies.mkdir(parents=True)
    evidence = tmp_path / "evidence" / "run-1"
    seen = {}

    def factory_builder(gpu_binding, run_root):
        seen["run_root"] = run_root
        return lambda **_: {"device": "cuda", "run_root": str(run_root)}

    def trainer(config_, dataset, out):
        out.mkdir()
        (out / "bundle.json").write_text('{"kind": "act_bundle"}')
        (out / "policy.safetensors").write_bytes(b"weights")
        return {"schema_version": 1, "kind": "act_bundle"}
    monkeypatch.setattr(cli, "local_owner_factory", factory_builder)
    bundle = policies / "bundle"
    assert cli.main([*_argv(manifest, index, binding, config, bundle), "--dataset-output", str(datasets),
                     "--evidence-dir", str(evidence)], trainer=trainer, requirements_path=_resolved_lock(tmp_path)) == 0
    assert (datasets / "export-manifest.json").is_file()
    assert not (policies / "bundle.dataset").exists()
    assert seen["run_root"] == evidence / "owner"
    record = json.loads((evidence / "training-outputs.json").read_text())
    assert record["kind"] == "act_training_outputs"
    assert record["dataset"] == {"path": str(datasets), "export_manifest_sha256": _sha256_of(datasets / "export-manifest.json")}
    assert (evidence / "export-manifest.json").read_bytes() == (datasets / "export-manifest.json").read_bytes()
    assert record["bundle"]["path"] == str(bundle)
    assert record["bundle"]["files"] == {"bundle.json": _sha256_of(bundle / "bundle.json"),
                                         "policy.safetensors": _sha256_of(bundle / "policy.safetensors")}
    assert record["state"]["status"] == "COMPLETED"
    assert json.loads((policies / "bundle.state.json").read_text())["status"] == "COMPLETED"


def test_a_failed_training_still_records_where_the_dataset_went(tmp_path, monkeypatch):
    import so101_demo.cli.act_train as cli
    manifest, index, binding, config = _workspace(tmp_path, monkeypatch)
    datasets = tmp_path / "datasets" / "d"
    evidence = tmp_path / "evidence"

    def trainer(*_a):
        raise ValueError("TRAINER_BOOM")
    monkeypatch.setattr(cli, "local_owner_factory", lambda gpu_binding, run_root: (lambda **_: {"device": "cuda", "run_root": str(run_root)}))
    with pytest.raises(ValueError, match="TRAINER_BOOM"):
        cli.main([*_argv(manifest, index, binding, config, tmp_path / "bundle"), "--dataset-output", str(datasets),
                  "--evidence-dir", str(evidence)], trainer=trainer, requirements_path=_resolved_lock(tmp_path))
    record = json.loads((evidence / "training-outputs.json").read_text())
    assert record["dataset"]["path"] == str(datasets) and record["bundle"] is None
    assert record["state"]["status"] == "FAILED" and "TRAINER_BOOM" in record["state"]["error"]


def test_dataset_output_and_evidence_record_refuse_to_overwrite(tmp_path, monkeypatch):
    import so101_demo.cli.act_train as cli
    manifest, index, binding, config = _workspace(tmp_path, monkeypatch)
    datasets = tmp_path / "ds"
    datasets.mkdir()
    with pytest.raises(ValueError, match="TRAINING_OUTPUT_EXISTS"):
        cli.main([*_argv(manifest, index, binding, config, tmp_path / "bundle"), "--dataset-output", str(datasets)],
                 trainer=lambda *_a: {"kind": "act_bundle"}, owner_factory=lambda **_: {"device": "cuda", "run_root": str(tmp_path)},
                 requirements_path=_resolved_lock(tmp_path))
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "training-outputs.json").write_text("{}")
    with pytest.raises(ValueError, match="TRAINING_EVIDENCE_EXISTS"):
        cli.main([*_argv(manifest, index, binding, config, tmp_path / "bundle2"), "--evidence-dir", str(evidence)],
                 trainer=lambda *_a: {"kind": "act_bundle"}, owner_factory=lambda **_: {"device": "cuda", "run_root": str(tmp_path)},
                 requirements_path=_resolved_lock(tmp_path))
    assert not (tmp_path / "bundle2.dataset").exists()          # refused before the export wrote anything


def test_reuse_dataset_trains_on_the_existing_export_without_exporting_again(tmp_path, capsys, monkeypatch):
    manifest, index, binding, config = _workspace(tmp_path, monkeypatch)
    requirements_path = _resolved_lock(tmp_path)
    owner = {"device": "cuda", "run_root": str(tmp_path)}
    trainer = lambda config, dataset, out: {"schema_version": 1, "kind": "act_bundle"}      # noqa: E731
    dataset = tmp_path / "export"
    first = _argv(manifest, index, binding, config, tmp_path / "first.json") + ["--dataset-output", str(dataset)]
    assert main(first, trainer=trainer, owner_factory=lambda **_: owner, requirements_path=requirements_path) == 0
    before = {path.relative_to(dataset).as_posix(): path.read_bytes() for path in dataset.rglob("*") if path.is_file()}
    capsys.readouterr()

    # the same export serves a second run: nothing in it is rewritten, and it is not exported again (the exporter must not be called)
    import so101_demo.cli.act_train as module
    monkeypatch.setattr(module, "export_dataset", lambda *a, **k: pytest.fail("the export must be reused"))
    second = _argv(manifest, index, binding, config, tmp_path / "second.json") + ["--dataset-output", str(dataset), "--reuse-dataset"]
    assert main(second, trainer=trainer, owner_factory=lambda **_: owner, requirements_path=requirements_path) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "COMPLETED"
    assert before == {path.relative_to(dataset).as_posix(): path.read_bytes() for path in dataset.rglob("*") if path.is_file()}

    # without --reuse-dataset an existing export is still refused
    with pytest.raises(ValueError, match="TRAINING_OUTPUT_EXISTS"):
        main(_argv(manifest, index, binding, config, tmp_path / "third.json") + ["--dataset-output", str(dataset)],
             trainer=trainer, owner_factory=lambda **_: owner, requirements_path=requirements_path)


def test_reuse_dataset_refuses_a_missing_export_and_one_made_from_other_inputs(tmp_path, monkeypatch):
    manifest, index, binding, config = _workspace(tmp_path, monkeypatch)
    requirements_path = _resolved_lock(tmp_path)
    owner = {"device": "cuda", "run_root": str(tmp_path)}
    kwargs = {"trainer": lambda *_a: {"kind": "act_bundle"}, "owner_factory": lambda **_: owner, "requirements_path": requirements_path}
    dataset = tmp_path / "export"
    output = tmp_path / "bundle.json"
    argv = _argv(manifest, index, binding, config, output) + ["--dataset-output", str(dataset), "--reuse-dataset"]
    with pytest.raises(ValueError, match="TRAINING_REUSED_DATASET_MISSING"):
        main(argv, **kwargs)
    with pytest.raises(ValueError, match="TRAINING_REUSED_DATASET_MISSING"):                 # no --dataset-output at all
        main(_argv(manifest, index, binding, config, output) + ["--reuse-dataset"], **kwargs)
    assert main(_argv(manifest, index, binding, config, tmp_path / "made.json") + ["--dataset-output", str(dataset)], **kwargs) == 0
    manifest.write_text(manifest.read_text() + " ")                                           # other bytes: a different input
    with pytest.raises(ValueError, match="TRAINING_REUSED_DATASET_MISMATCH"):
        main(argv, **kwargs)
    assert not output.exists()
