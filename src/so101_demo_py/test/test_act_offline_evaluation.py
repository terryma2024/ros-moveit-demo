"""Task 12A: padded frames must not enter a joint metric, and bad rows must not vanish."""

import json
from pathlib import Path

import pytest


from so101_demo.act.offline_evaluation import masked_joint_mae, masked_joint_rmse


def test_padding_is_excluded_from_joint_metrics():
    predicted = [[1., 2., 3., 4., 5., 6.], [100., 100., 100., 100., 100., 100.]]
    target = [[0., 0., 0., 0., 0., 0.], [0., 0., 0., 0., 0., 0.]]
    assert masked_joint_mae(predicted, target, [True, False]) == [1., 2., 3., 4., 5., 6.]


def test_a_mask_that_keeps_nothing_is_refused_rather_than_reported_as_zero_error():
    with pytest.raises(ValueError, match="NO_VALID_TARGETS"):
        masked_joint_mae([[1.] * 6], [[0.] * 6], [False])
    with pytest.raises(ValueError, match="NO_VALID_TARGETS"):
        masked_joint_rmse([], [], [])


def test_shapes_values_and_mask_types_are_closed(tmp_path):
    for predicted, target, valid in (
            ([[1.] * 6], [[0.] * 6, [0.] * 6], [True]),          # length mismatch
            ([[1.] * 5], [[0.] * 5], [True]),                     # not six joints
            ([[1.] * 6], [[0.] * 6], [1]),                        # the mask is not a bool
            ([[float("nan")] * 6], [[0.] * 6], [True]),           # a non-finite prediction
            ([[True] * 6], [[0.] * 6], [True]),                   # a bool is not a joint angle
            ([[1.] * 6], [[float("inf")] * 6], [True]),           # nor is a non-finite target
    ):
        shape_fault = (len(predicted) != len(target) or len(predicted[0]) != 6
                       or type(valid[0]) is not bool)
        expected = "MASK_SHAPE_INVALID" if shape_fault else "(PREDICTED|TARGET)_INVALID"
        with pytest.raises(ValueError, match=expected):
            masked_joint_mae(predicted, target, valid)


def test_rmse_matches_the_same_masked_frames():
    predicted = [[3., 0., 0., 0., 0., 0.], [100.] * 6]
    target = [[0.] * 6, [0.] * 6]
    assert masked_joint_rmse(predicted, target, [True, False]) == [3., 0., 0., 0., 0., 0.]
    # the two metrics agree on a single frame, and the mask alone decides the denominator
    assert masked_joint_mae([[1.] * 6, [9.] * 6], [[0.] * 6, [0.] * 6], [True, True]) == [5.] * 6


def _frozen(tmp_path, *, episodes=10, cross_split=False, freeze_overrides=None, paths_overrides=None):
    import hashlib
    import json
    from pathlib import Path as _Path

    from so101_demo.act.bundle import BUNDLE_KEYS

    (tmp_path / "policy.bin").write_bytes(b"model")
    bundle = {"schema_version": 1, "kind": "act_bundle",
              "model_source": {"name": "act-v1", "sha256": "a" * 64},
              "dataset_sha256": "b" * 64, "config_sha256": "c" * 64, "policy_path": "policy.bin",
              "policy_sha256": hashlib.sha256(b"model").hexdigest(),
              "normalization": {"split": "train", "mean": [0.0] * 6},
              "action": {"chunk_size": 10, "execution_prefix": 1,
                         "temporal_ensembling": False, "tail_padding_mask": True}}
    assert set(bundle) == set(BUNDLE_KEYS)
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(bundle))
    frames = [{"observation": {"state": [0.0] * 8}, "action": [1.0] * 6, "valid": True}]
    manifest = {"episodes": [{"episode_id": f"ep-{index}", "split": "offline_test",
                              "status": "PASSED", "frames": frames,
                              "cross_split_chunk": cross_split}
                             for index in range(episodes)]}
    manifest_path = tmp_path / "dataset-manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    others = {}
    for name in ("campaign_index", "split_manifest", "calibration", "runtime_config"):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps({"name": name}))
        others[name] = path
    digests = {"bundle_sha256": hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
               "dataset_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
               "campaign_index_sha256": hashlib.sha256(others["campaign_index"].read_bytes()).hexdigest(),
               "split_manifest_sha256": hashlib.sha256(others["split_manifest"].read_bytes()).hexdigest(),
               "calibration_sha256": hashlib.sha256(others["calibration"].read_bytes()).hexdigest(),
               "runtime_config_sha256": hashlib.sha256(others["runtime_config"].read_bytes()).hexdigest()}
    digests.update(freeze_overrides or {})
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_text(json.dumps(digests))
    paths = {"bundle_sha256": str(bundle_path), "dataset_manifest_sha256": str(manifest_path),
             "campaign_index_sha256": str(others["campaign_index"]),
             "split_manifest_sha256": str(others["split_manifest"]),
             "calibration_sha256": str(others["calibration"]),
             "runtime_config_sha256": str(others["runtime_config"])}
    paths.update(paths_overrides or {})
    (tmp_path / "freeze-paths.json").write_text(json.dumps(paths))
    return manifest_path, bundle_path, freeze_path


class _FixedPolicy:
    def __init__(self, action=1.0):
        self._action, self.resets, self.infers = action, 0, 0

    def reset(self):
        self.resets += 1

    def infer(self, observation):
        self.infers += 1
        return ((self._action,) * 6,)


def test_evaluation_verifies_the_freeze_and_weighs_episodes_equally(tmp_path):
    import json

    from so101_demo.act.offline_evaluation import evaluate_offline

    manifest, bundle, freeze = _frozen(tmp_path)
    policy = _FixedPolicy(action=1.0)
    document = evaluate_offline(manifest, bundle, freeze, tmp_path / "report.json",
                                policy_loader=lambda _bundle: policy)
    assert document["episode_count"] == 10 and document["byte_weighted"] is False
    assert document["mean_mae_rad"] == [0.0] * 6      # a perfect model is a sane baseline
    assert policy.resets == 10 and policy.infers == 10   # one reset per episode, one infer per frame
    assert not (tmp_path / "report.json.partial").exists()
    with pytest.raises(ValueError, match="EVALUATION_OUTPUT_EXISTS"):
        evaluate_offline(manifest, bundle, freeze, tmp_path / "report.json",
                         policy_loader=lambda _bundle: _FixedPolicy())


def test_a_freeze_that_does_not_verify_stops_the_run(tmp_path):
    import json

    from so101_demo.act.offline_evaluation import evaluate_offline, load_freeze

    manifest, bundle, freeze = _frozen(tmp_path, freeze_overrides={"calibration_sha256": "d" * 64})
    with pytest.raises(ValueError, match="FREEZE_DIGEST_MISMATCH"):
        load_freeze(freeze)
    with pytest.raises(ValueError, match="FREEZE_DIGEST_MISMATCH"):
        evaluate_offline(manifest, bundle, freeze, tmp_path / "r.json",
                         policy_loader=lambda _bundle: _FixedPolicy())
    for overrides, code in (({"extra": "a" * 64}, "FREEZE_INVALID"),):
        bad = json.loads(Path(freeze).read_text())
        bad.update(overrides)
        Path(freeze).write_text(json.dumps(bad))
        with pytest.raises(ValueError, match=code):
            load_freeze(freeze)
    missing = json.loads(Path(freeze).read_text())
    missing.pop("bundle_sha256")
    Path(freeze).write_text(json.dumps(missing))
    with pytest.raises(ValueError, match="FREEZE_INVALID"):
        load_freeze(freeze)


def test_too_few_episodes_or_a_cross_split_chunk_refuses_evaluation(tmp_path):
    from so101_demo.act.offline_evaluation import evaluate_offline

    manifest, bundle, freeze = _frozen(tmp_path / "few", episodes=9) if (tmp_path / "few").mkdir(
        exist_ok=True) is None else (None, None, None)
    with pytest.raises(ValueError, match="OFFLINE_TEST_EPISODES_INSUFFICIENT"):
        evaluate_offline(manifest, bundle, freeze, tmp_path / "few" / "r.json",
                         policy_loader=lambda _bundle: _FixedPolicy())
    (tmp_path / "cross").mkdir(exist_ok=True)
    manifest, bundle, freeze = _frozen(tmp_path / "cross", cross_split=True)
    with pytest.raises(ValueError, match="CROSS_SPLIT_CHUNK_FORBIDDEN"):
        evaluate_offline(manifest, bundle, freeze, tmp_path / "cross" / "r.json",
                         policy_loader=lambda _bundle: _FixedPolicy())


def test_cli_evaluates_through_an_injected_loader_and_leaves_no_output_on_refusal(tmp_path, capsys):
    from so101_demo.cli.act_offline_evaluate import main

    manifest, bundle, freeze = _frozen(tmp_path)
    output = tmp_path / "report.json"
    argv = ["--manifest", str(manifest), "--bundle", str(bundle), "--freeze", str(freeze),
            "--output", str(output)]
    assert main(argv, policy_loader=lambda _bundle: _FixedPolicy()) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["episode_count"] == 10 and printed["byte_weighted"] is False
    assert output.is_file()

    # a refusal must not leave an output file behind
    refused = tmp_path / "refused.json"
    frozen_digest = json.loads(Path(freeze).read_text())
    frozen_digest["calibration_sha256"] = "d" * 64
    Path(freeze).write_text(json.dumps(frozen_digest))
    with pytest.raises(ValueError, match="FREEZE_DIGEST_MISMATCH"):
        main(["--manifest", str(manifest), "--bundle", str(bundle), "--freeze", str(freeze),
              "--output", str(refused)], policy_loader=lambda _bundle: _FixedPolicy())
    assert not refused.exists()


def test_the_production_loader_fails_closed_rather_than_reaching_for_a_model(tmp_path):
    from so101_demo.cli.act_offline_evaluate import _policy_loader

    # no torch in the test interpreter, so the production path must refuse precisely rather than guess
    with pytest.raises(ValueError,
                       match="OFFLINE_EVALUATION_(TRAINING_INTERPRETER_REQUIRED|LOADER_UNAVAILABLE)"):
        _policy_loader({})
