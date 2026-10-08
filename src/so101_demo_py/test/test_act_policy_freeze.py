"""The frozen policy set (A4c): `teacher_endpoint_v2` + `teacher_execution_policy_v1` + `episode_recorder_v1` replace the
endpoint_pose_v1 `endpoint_policy`, each frozen with its full effective values and its sha256.

The Teacher and the Recorder load their policies from the frozen manifest at runtime and refuse a mismatch: the Teacher
before any motion, the Recorder before it listens, `act_first_episode run` before it creates its run root.
"""

import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from so101_demo.act.first_episode_inputs import (
    POLICY_BINDINGS, freeze_inputs, policy_binding, verify_frozen_inputs, verify_policy_bindings)
from test_act_first_episode_scope import _registry, _write_registry

CONFIG = Path(__file__).parents[1] / "config/act"
POLICY_FILES = {"teacher_endpoint": CONFIG / "teacher_endpoint_v2.yaml",
                "teacher_execution_policy": CONFIG / "teacher_execution_policy_v1.yaml",
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
    assert "endpoint_policy" not in document, "the endpoint_pose_v1 binding is replaced, not carried"
    loaders = {"teacher_endpoint_v2": load_teacher_endpoint_policy, "teacher_execution_policy_v1": load_teacher_execution_policy,
               "episode_recorder_v1": load_recorder_policy}
    sources = {"teacher_endpoint_v2": POLICY_FILES["teacher_endpoint"],
               "teacher_execution_policy_v1": POLICY_FILES["teacher_execution_policy"],
               "episode_recorder_v1": POLICY_FILES["episode_recorder_policy"]}
    assert set(POLICY_BINDINGS) == set(loaders) | {"teacher_execution_policy_v2"}      # v2 is frozen instead of v1, never beside it
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
    assert document["teacher_endpoint_v2"]["values"]["tolerances"]["final_xy_m"] == 0.020
    assert document["teacher_execution_policy_v1"]["values"]["execution_deadline_s"] == 180.0
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


def test_the_freezer_and_prepare_no_longer_take_the_endpoint_policy_v1():
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
    binding = document["teacher_endpoint_v2"]
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
    with pytest.raises(ValueError, match="INPUTS_POLICY_BINDING_INVALID: teacher_endpoint_v2"):
        verify_frozen_inputs(manifest_path)


def test_a_manifest_from_before_the_replacement_still_reads_and_carries_no_new_binding(tmp_path):
    """An old frozen set (its `endpoint_policy` v1 binding, none of the three) stays readable for audit."""
    from so101_demo.act.endpoint_pose_acceptance import load_endpoint_policy
    from so101_demo.act.first_episode_inputs import _canonical
    manifest_path = freeze(tmp_path)
    document = json.loads(manifest_path.read_bytes())
    for name in POLICY_BINDINGS:
        document.pop(name, None)
    policy = load_endpoint_policy(CONFIG / "endpoint_pose_acceptance_v1.yaml")
    document["endpoint_policy"] = {"rule_version": policy["rule_version"], "thresholds": policy["thresholds"],
                                   "sha256": hashlib.sha256(_canonical(policy)).hexdigest()}
    rehash(manifest_path, document)
    legacy = verify_frozen_inputs(manifest_path)
    assert "endpoint_policy" in legacy and not set(POLICY_BINDINGS) & set(legacy)


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
    assert set(policies) == set(POLICY_BINDINGS) - {"teacher_execution_policy_v2"}
    # the policy file the Teacher's own loader reads is the snapshot's copy of exactly the bound bytes
    for name, (_, config_path) in POLICY_BINDINGS.items():
        if name not in frozen:
            continue
        assert snapshot["files"][config_path]["sha256"] == frozen[name]["file_sha256"]


@pytest.mark.parametrize("name, change", [
    ("teacher_endpoint_v2", lambda values: values["tolerances"].update(final_xy_m=0.5)),
    ("teacher_execution_policy_v1", lambda values: values.update(execution_deadline_s=999.0)),
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
    document.pop("teacher_endpoint_v2")
    rehash(manifest_path, document)
    with pytest.raises(ValueError, match="INPUTS_TEACHER_POLICY_REQUIRED: teacher_endpoint_v2"):
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
    forge_a_consistent_policy(manifest_path, "teacher_endpoint_v2",
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
    forge_a_consistent_policy(manifest_path, "teacher_execution_policy_v1",
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


# ---- CP-3480: policy v2 (tilt-compensated place height) is frozen instead of v1 ----------------------------------------------------

V2_NAME = "teacher_execution_policy_v2.yaml"


def test_a_freeze_binds_v2_instead_of_v1_and_the_teacher_names_it(tmp_path):
    from so101_demo.act.frozen_runtime_inputs import frozen_execution_policy_name, load_teacher_frozen_inputs
    from test_act_child_recorder_binding import frozen_child_inputs
    manifest_path, document, snapshot = frozen_child_inputs(tmp_path, execution_policy=V2_NAME)
    assert "teacher_execution_policy_v2" in document and "teacher_execution_policy_v1" not in document
    binding = document["teacher_execution_policy_v2"]
    assert binding["path"] == "policies/" + V2_NAME and binding["values"]["place_height_mode"] == "tilt_compensated"
    assert binding["file_sha256"] == hashlib.sha256((CONFIG / V2_NAME).read_bytes()).hexdigest()
    frozen, loaded, root = load_teacher_frozen_inputs(manifest_path)
    assert frozen_execution_policy_name(frozen) == "teacher_execution_policy_v2"
    assert loaded["files"]["config/act/" + V2_NAME]["sha256"] == binding["file_sha256"]
    assert set(verify_policy_bindings(frozen, manifest_path, loaded)) == {
        "teacher_endpoint_v2", "teacher_execution_policy_v2", "episode_recorder_v1"}


def test_a_schema_2_document_cannot_be_bound_as_v1_nor_a_schema_1_one_as_v2():
    with pytest.raises(ValueError, match="TEACHER_EXECUTION_POLICY_INVALID: binding teacher_execution_policy_v1"):
        policy_binding("teacher_execution_policy_v1", (CONFIG / V2_NAME).read_bytes())
    with pytest.raises(ValueError, match="TEACHER_EXECUTION_POLICY_INVALID: binding teacher_execution_policy_v2"):
        policy_binding("teacher_execution_policy_v2", (CONFIG / "teacher_execution_policy_v1.yaml").read_bytes())


def test_the_teacher_loader_wants_exactly_one_execution_policy(tmp_path):
    from so101_demo.act.frozen_runtime_inputs import frozen_execution_policy_name
    v1 = {"teacher_execution_policy_v1": {}}
    v2 = {"teacher_execution_policy_v2": {}}
    assert frozen_execution_policy_name(v1) == "teacher_execution_policy_v1" and frozen_execution_policy_name(v2) == "teacher_execution_policy_v2"
    for frozen in ({}, {**v1, **v2}):
        with pytest.raises(ValueError, match="INPUTS_TEACHER_POLICY_REQUIRED"):
            frozen_execution_policy_name(frozen)


def test_a_manifest_carrying_both_execution_bindings_is_rejected(tmp_path):
    """CP-3483: a freeze names exactly one execution policy; a self-consistent manifest with v1 and v2 is not admitted."""
    from so101_demo.act.first_episode_inputs import read_inputs_manifest
    from so101_demo.act.frozen_runtime_inputs import load_teacher_frozen_inputs
    from test_act_child_recorder_binding import frozen_child_inputs
    manifest_path, document, _ = frozen_child_inputs(tmp_path, execution_policy=V2_NAME)
    assert "teacher_execution_policy_v1" not in document
    (manifest_path.parent / "policies/teacher_execution_policy_v1.yaml").write_bytes(
        (CONFIG / "teacher_execution_policy_v1.yaml").read_bytes())
    document["teacher_execution_policy_v1"] = policy_binding(
        "teacher_execution_policy_v1", (CONFIG / "teacher_execution_policy_v1.yaml").read_bytes())
    rehash(manifest_path, document)
    for call in (read_inputs_manifest, verify_frozen_inputs, load_teacher_frozen_inputs):
        with pytest.raises(ValueError, match="INPUTS_MANIFEST_INVALID"):
            call(manifest_path)
