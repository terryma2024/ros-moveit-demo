"""A freeze may bind a schema 4 variant of the Teacher execution policy (`config/act/teacher_execution_policy_*.yaml`).

The execution snapshot carries every `config/act` file; the Teacher loads the one whose bytes the freeze bound. The default file keeps
its path, and a bound file that no snapshot file carries is still refused."""

import hashlib

import pytest

from so101_demo.act.diagnostic_episode_inputs import (
    EXECUTION_POLICY_BINDING, snapshot_policy_path, verify_frozen_inputs)
from so101_demo.act.frozen_runtime_inputs import load_teacher_frozen_inputs
from paths import PACKAGE_ROOT

DEFAULT_FILE = "teacher_execution_policy.yaml"
FAST_FILE = "teacher_execution_policy_side_wrist_fast.yaml"


def freeze(tmp_path, policy_file):
    from test_act_child_recorder_binding import frozen_child_inputs

    manifest_path, document, snapshot = frozen_child_inputs(tmp_path, teacher_policy_file=policy_file)
    return manifest_path, document, snapshot


def test_a_freeze_of_the_fast_policy_verifies_and_loads_with_schema_4(tmp_path):
    manifest_path, document, snapshot = freeze(tmp_path, FAST_FILE)
    assert document[EXECUTION_POLICY_BINDING]["file_sha256"] == hashlib.sha256(
        (PACKAGE_ROOT / "config/act" / FAST_FILE).read_bytes()).hexdigest()
    assert verify_frozen_inputs(manifest_path)[EXECUTION_POLICY_BINDING]["values"]["schema_version"] == 4
    frozen, loaded, _ = load_teacher_frozen_inputs(manifest_path)
    assert frozen[EXECUTION_POLICY_BINDING]["values"]["prepare_open_gripper_duration_s"] == 1.0
    assert snapshot_policy_path(loaded["files"], EXECUTION_POLICY_BINDING,
                                frozen[EXECUTION_POLICY_BINDING]["file_sha256"]) == "config/act/" + FAST_FILE


def test_a_freeze_of_the_default_policy_keeps_the_default_path(tmp_path):
    manifest_path, _, _ = freeze(tmp_path, DEFAULT_FILE)
    frozen, loaded, _ = load_teacher_frozen_inputs(manifest_path)
    assert frozen[EXECUTION_POLICY_BINDING]["values"]["schema_version"] == 3
    assert snapshot_policy_path(loaded["files"], EXECUTION_POLICY_BINDING,
                                frozen[EXECUTION_POLICY_BINDING]["file_sha256"]) == "config/act/" + DEFAULT_FILE


def test_a_bound_policy_that_no_snapshot_file_carries_is_refused(tmp_path):
    from test_act_policy_freeze import rehash

    manifest_path, document, _ = freeze(tmp_path, FAST_FILE)
    policy = manifest_path.parent / document[EXECUTION_POLICY_BINDING]["path"]
    payload = policy.read_bytes().replace(b"retreat_velocity_scaling: 0.1", b"retreat_velocity_scaling: 0.2")
    assert payload != policy.read_bytes()
    policy.write_bytes(payload)
    document[EXECUTION_POLICY_BINDING].update(file_sha256=hashlib.sha256(payload).hexdigest(), bytes=len(payload))
    rehash(manifest_path, document)
    with pytest.raises(ValueError):
        load_teacher_frozen_inputs(manifest_path)
    with pytest.raises(ValueError):
        verify_frozen_inputs(manifest_path)


def test_only_teacher_execution_policy_variants_are_looked_up():
    files = {"config/act/" + DEFAULT_FILE: {"sha256": "a" * 64}, "config/act/" + FAST_FILE: {"sha256": "b" * 64},
             "config/act/teacher_endpoint_other.yaml": {"sha256": "c" * 64},
             "config/act/nested/teacher_execution_policy_x.yaml": {"sha256": "d" * 64},
             "config/other/teacher_execution_policy_y.yaml": {"sha256": "e" * 64}}
    assert snapshot_policy_path(files, EXECUTION_POLICY_BINDING, "a" * 64) == "config/act/" + DEFAULT_FILE
    assert snapshot_policy_path(files, EXECUTION_POLICY_BINDING, "b" * 64) == "config/act/" + FAST_FILE
    for sha in ("c", "d", "e", "f"):
        assert snapshot_policy_path(files, EXECUTION_POLICY_BINDING, sha * 64) is None
    assert snapshot_policy_path(files, "teacher_endpoint", "c" * 64) is None        # no variants for the other policies
