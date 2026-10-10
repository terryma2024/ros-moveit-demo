"""The frozen policy set (A4c): `teacher_endpoint` + `teacher_execution_policy` + `episode_recorder_v1`, each frozen with its
full effective values and its sha256.

The Teacher and the Recorder load their policies from the frozen manifest at runtime and refuse a mismatch: the Teacher
before any motion, the Recorder before it listens, `act_first_episode run` before it creates its run root.
"""

import hashlib
import inspect
import json
from types import SimpleNamespace

import pytest
import yaml

from so101_demo.act.first_episode_inputs import (
    POLICY_BINDINGS, freeze_inputs, policy_binding, verify_frozen_inputs, verify_policy_bindings)
from test_act_first_episode_scope import _registry, _write_registry
from paths import PACKAGE_ROOT

CONFIG = PACKAGE_ROOT / "config/act"
POLICY_FILES = {"teacher_endpoint": CONFIG / "teacher_endpoint.yaml",
                "teacher_execution_policy": CONFIG / "teacher_execution_policy.yaml",
                "episode_recorder_policy": CONFIG / "episode_recorder_v1.yaml"}


def freeze(tmp_path, **overrides):
    files = {**POLICY_FILES, **overrides}
    return freeze_inputs(_write_registry(tmp_path, _registry(tmp_path)), tmp_path / "inputs",
                         mode="preselected_target_diagnostic", **files,
                         runtime_policy=CONFIG / "endpoint_pose_development_runtime_v1.yaml")


def rehash(manifest_path, document):
    """Rewrite a manifest with its hash chain recomputed, as a self-consistent forger would."""
    from so101_demo.act.first_episode_inputs import _MANIFEST_OPTIONAL, _canonical
    extra = {key: document[key] for key in _MANIFEST_OPTIONAL if key in document}
    document["inputs_sha256"] = hashlib.sha256(_canonical({**document["roles"], **extra})).hexdigest()
    manifest_path.write_bytes(_canonical(document))


def test_the_freezer_binds_the_three_policies_with_full_values_and_both_digests(tmp_path):
    from so101_demo.act.offline.policy import load_recorder_policy
    from so101_demo.act.teacher_endpoint import load_teacher_endpoint_policy, load_teacher_execution_policy

    manifest_path = freeze(tmp_path)
    document = json.loads(manifest_path.read_bytes())
    assert "endpoint_policy" not in document, "the retired endpoint pose binding is not carried"
    loaders = {"teacher_endpoint": load_teacher_endpoint_policy, "teacher_execution_policy": load_teacher_execution_policy,
               "episode_recorder_v1": load_recorder_policy}
    sources = {"teacher_endpoint": POLICY_FILES["teacher_endpoint"],
               "teacher_execution_policy": POLICY_FILES["teacher_execution_policy"],
               "episode_recorder_v1": POLICY_FILES["episode_recorder_policy"]}
    assert set(POLICY_BINDINGS) == set(loaders)
    for name, loader in loaders.items():
        binding, payload = document[name], sources[name].read_bytes()
        effective = loader(payload)
        assert set(binding) == {"path", "file_sha256", "bytes", "policy_sha256", "values"}
        assert binding["path"] == "policies/" + POLICY_BINDINGS[name][0]
        assert (manifest_path.parent / binding["path"]).read_bytes() == payload
        assert binding["file_sha256"] == hashlib.sha256(payload).hexdigest() and binding["bytes"] == len(payload)
        assert binding["policy_sha256"] == effective["policy_sha256"]
        assert binding["values"] == {key: value for key, value in effective.items() if key != "policy_sha256"}
    # the full effective values are readable without the YAML: the tolerances, the deadlines and the Recorder bounds
    assert document["teacher_endpoint"]["values"]["tolerances"]["final_xy_m"] == 0.020
    assert document["teacher_execution_policy"]["values"]["execution_deadline_s"] == 180.0
    assert document["episode_recorder_v1"]["values"]["ready_timeout_s"] > 0


def test_each_policy_value_enters_the_inputs_hash_chain(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    baseline = json.loads(freeze(tmp_path / "a").read_bytes())["inputs_sha256"]
    changed = tmp_path / "recorder.yaml"
    document = yaml.safe_load(POLICY_FILES["episode_recorder_policy"].read_text())
    document["ready_timeout_s"] = 7.0
    changed.write_text(yaml.safe_dump(document))
    other = json.loads(freeze(tmp_path / "b", episode_recorder_policy=changed).read_bytes())
    assert other["inputs_sha256"] != baseline and other["episode_recorder_v1"]["values"]["ready_timeout_s"] == 7.0


def test_the_freezer_and_prepare_no_longer_take_the_retired_endpoint_policy():
    from so101_demo.cli import act_first_episode
    assert "endpoint_policy" not in inspect.signature(freeze_inputs).parameters
    for name in ("teacher_endpoint", "teacher_execution_policy", "episode_recorder_policy"):
        assert inspect.signature(freeze_inputs).parameters[name].default is None
    parser = act_first_episode.build_parser()
    base = ["prepare", "--candidates", "c", "--runtime-policy", "r", "--output", "o"]
    options = parser.parse_args(base + ["--teacher-endpoint", "e", "--teacher-execution-policy", "x",
                                        "--episode-recorder-policy", "p"])
    assert (options.teacher_endpoint, options.teacher_execution_policy, options.episode_recorder_policy) == ("e", "x", "p")
    # the broker stop policy and the bound timing are gone with the broker (inputs manifest schema 2)
    for refused in (base + ["--endpoint-policy", "old"], base + ["--teacher-endpoint", "e"],
                    base + ["--broker-stop-policy", "b"], base + ["--teacher-bound-timing", "t"]):
        with pytest.raises(SystemExit) as caught:
            parser.parse_args(refused)
        assert caught.value.code == 2
    run = parser.parse_args(["run", "--inputs", "i", "--root", "r"])
    assert (run.collection, run.collection_fault) == ("on", "none")


@pytest.mark.parametrize("which, mutate", [
    ("teacher_endpoint", lambda doc: doc.update(tolerances={**doc["tolerances"], "final_xy_m": -1})),
    ("teacher_execution_policy", lambda doc: doc.update(state_max_age_s=0)),
    ("episode_recorder_policy", lambda doc: doc.update(max_duration_s=10_000)),
    ("episode_recorder_policy", lambda doc: doc.update(unknown_key=1))])
def test_a_policy_that_fails_its_closed_loader_is_refused_before_anything_is_written(tmp_path, which, mutate):
    bad = tmp_path / "bad.yaml"
    document = yaml.safe_load(POLICY_FILES[which].read_text())
    mutate(document)
    bad.write_text(yaml.safe_dump(document))
    with pytest.raises(ValueError):
        freeze(tmp_path, **{which: bad})
    assert not (tmp_path / "inputs").exists()


@pytest.mark.parametrize("fault", ["file_bytes", "values", "policy_sha", "extra_field", "path", "missing_file", "symlink"])
def test_a_changed_or_inconsistent_policy_binding_is_refused(tmp_path, fault):
    manifest_path = freeze(tmp_path)
    document = json.loads(manifest_path.read_bytes())
    binding = document["teacher_endpoint"]
    policy_file = manifest_path.parent / binding["path"]
    if fault == "file_bytes":
        policy_file.write_bytes(policy_file.read_bytes() + b"# edited after the freeze\n")
    elif fault == "values":
        binding["values"] = {**binding["values"], "tolerances": {**binding["values"]["tolerances"], "final_xy_m": 0.5}}
        rehash(manifest_path, document)
    elif fault == "policy_sha":
        binding["policy_sha256"] = "0" * 64
        rehash(manifest_path, document)
    elif fault == "extra_field":
        binding["unreviewed"] = True
        rehash(manifest_path, document)
    elif fault == "path":
        binding["path"] = "policies/other.yaml"
        rehash(manifest_path, document)
    elif fault == "missing_file":
        policy_file.unlink()
    else:
        original = policy_file.read_bytes()
        policy_file.unlink()
        elsewhere = tmp_path / "elsewhere.yaml"
        elsewhere.write_bytes(original)
        policy_file.symlink_to(elsewhere)
    with pytest.raises(ValueError, match="INPUTS_POLICY_BINDING_INVALID: teacher_endpoint"):
        verify_frozen_inputs(manifest_path)


# ---- the snapshot cross-check: the Teacher reads the snapshot's copy, so the bound bytes must be the same bytes --------

def forge_a_consistent_policy(manifest_path, name, change):
    """A self-consistent replacement: new file bytes, new binding values and a recomputed hash chain."""
    document = json.loads(manifest_path.read_bytes())
    path = manifest_path.parent / document[name]["path"]
    values = yaml.safe_load(path.read_text())
    change(values)
    payload = yaml.safe_dump(values).encode()
    path.write_bytes(payload)
    document[name] = policy_binding(name, payload)
    rehash(manifest_path, document)


def test_the_teacher_loads_its_snapshot_and_policies_from_the_frozen_manifest(tmp_path):
    from so101_demo.act.frozen_runtime_inputs import load_teacher_frozen_inputs
    from test_act_child_recorder_binding import frozen_child_inputs
    manifest_path, document, snapshot = frozen_child_inputs(tmp_path)
    frozen, loaded, root = load_teacher_frozen_inputs(manifest_path)
    assert frozen == document and loaded == snapshot and root == manifest_path.parent / "execution"
    policies = verify_policy_bindings(frozen, manifest_path, loaded)
    assert set(policies) == set(POLICY_BINDINGS)
    # the policy file the Teacher's own loader reads is the snapshot's copy of exactly the bound bytes
    for name, (_, config_path) in POLICY_BINDINGS.items():
        if name not in frozen:
            continue
        assert snapshot["files"][config_path]["sha256"] == frozen[name]["file_sha256"]


@pytest.mark.parametrize("name, change", [
    ("teacher_endpoint", lambda values: values["tolerances"].update(final_xy_m=0.5)),
    ("teacher_execution_policy", lambda values: values.update(execution_deadline_s=999.0)),
    ("episode_recorder_v1", lambda values: values.update(ready_timeout_s=3.0))])
def test_a_consistently_forged_policy_that_differs_from_the_execution_snapshot_is_refused_everywhere(
        tmp_path, name, change):
    from so101_demo.act.offline.policy import RecorderConfigRefused
    from so101_demo.act.frozen_runtime_inputs import load_recorder_frozen_policy, load_teacher_frozen_inputs
    from test_act_child_recorder_binding import frozen_child_inputs
    manifest_path, _, _ = frozen_child_inputs(tmp_path)
    forge_a_consistent_policy(manifest_path, name, change)
    expected = "execution snapshot copy differs"
    with pytest.raises(ValueError, match=expected):
        verify_frozen_inputs(manifest_path)
    with pytest.raises(ValueError, match=expected):
        load_teacher_frozen_inputs(manifest_path)
    with pytest.raises(RecorderConfigRefused, match="RECORDER_FROZEN_INPUTS_INVALID"):
        load_recorder_frozen_policy(manifest_path)


def test_a_frozen_set_without_the_teacher_policies_is_refused_by_the_teacher_loader(tmp_path):
    from so101_demo.act.frozen_runtime_inputs import load_teacher_frozen_inputs
    from test_act_child_recorder_binding import frozen_child_inputs
    manifest_path, _, _ = frozen_child_inputs(tmp_path)
    document = json.loads(manifest_path.read_bytes())
    document.pop("teacher_endpoint")
    rehash(manifest_path, document)
    with pytest.raises(ValueError, match="INPUTS_TEACHER_POLICY_REQUIRED: teacher_endpoint"):
        load_teacher_frozen_inputs(manifest_path)


def test_the_recorder_loads_its_policy_only_from_the_frozen_manifest(tmp_path):
    from so101_demo.act.frozen_runtime_inputs import load_recorder_frozen_policy
    from so101_demo.act.offline.policy import RecorderConfigRefused
    manifest_path = freeze(tmp_path)
    policy = load_recorder_frozen_policy(manifest_path)
    bound = json.loads(manifest_path.read_bytes())["episode_recorder_v1"]
    assert policy["policy_sha256"] == bound["policy_sha256"] and policy["ready_timeout_s"] == bound["values"]["ready_timeout_s"]
    document = json.loads(manifest_path.read_bytes())
    document.pop("episode_recorder_v1")
    rehash(manifest_path, document)
    with pytest.raises(RecorderConfigRefused, match="RECORDER_POLICY_NOT_FROZEN"):
        load_recorder_frozen_policy(manifest_path)
    with pytest.raises(RecorderConfigRefused, match="RECORDER_FROZEN_INPUTS_INVALID"):
        load_recorder_frozen_policy(tmp_path / "does-not-exist.json")


def test_act_first_episode_run_refuses_a_forged_policy_before_creating_its_run_root(tmp_path):
    from so101_demo.cli import act_first_episode
    from test_act_child_recorder_binding import frozen_child_inputs
    manifest_path, document, _ = frozen_child_inputs(tmp_path)
    forge_a_consistent_policy(manifest_path, "teacher_endpoint",
                              lambda values: values["tolerances"].update(final_xy_m=0.5))
    root = tmp_path / "live"
    assert act_first_episode.main(["run", "--inputs", str(manifest_path.parent), "--root", str(root),
                                   "--mode", document["mode"], "--lifecycle", "FULL_RESTART"]) == 2
    assert not root.exists()


def test_the_teacher_refuses_a_forged_policy_before_any_motion_or_runtime_load(tmp_path, capsys):
    """`run_dynamic_execute` loads the frozen set first: a mismatch returns 1 before the runtime or ROS is touched."""
    from so101_demo.ros.dynamic_runtime import run_dynamic_execute
    from test_act_child_recorder_binding import frozen_child_inputs
    manifest_path, _, _ = frozen_child_inputs(tmp_path)
    forge_a_consistent_policy(manifest_path, "teacher_execution_policy",
                              lambda values: values.update(execution_deadline_s=999.0))

    def never(*args, **kwargs):
        raise AssertionError("the runtime was touched with a forged policy set")

    runtime = SimpleNamespace(get_package_share_directory=lambda *a, **k: str(tmp_path), load_policy=never,
                              load_geometry=never, rclpy=SimpleNamespace(init=never))
    options = SimpleNamespace(session_id="s", expected_reset_epoch=1, evidence_root=tmp_path / "dynamic",
                              frozen_inputs_manifest=manifest_path)
    assert run_dynamic_execute(options, _runtime=runtime) == 1
    output = capsys.readouterr().out
    assert "status=ERROR" in output and "execution snapshot copy differs" in output


# ---- the Teacher execution policy is the one binding the Teacher needs --------------------------------------------------------------

def test_a_frozen_set_without_the_teacher_execution_policy_is_refused_by_the_teacher_loader(tmp_path):
    from so101_demo.act.frozen_runtime_inputs import load_teacher_frozen_inputs
    from test_act_child_recorder_binding import frozen_child_inputs
    manifest_path, document, _ = frozen_child_inputs(tmp_path)
    document.pop("teacher_execution_policy")
    rehash(manifest_path, document)
    with pytest.raises(ValueError, match="INPUTS_TEACHER_POLICY_REQUIRED: teacher_execution_policy"):
        load_teacher_frozen_inputs(manifest_path)
