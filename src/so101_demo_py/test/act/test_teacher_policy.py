"""The Teacher execution policy (design 2026-10-10-so101-teacher-minimal-runtime-gates): the closed loader, the freeze binding and
the general runtime policy that carries the three shared bounds."""

import hashlib

import pytest
import yaml

from so101_demo.act.frozen_runtime_inputs import load_teacher_frozen_inputs
from so101_demo.act.diagnostic_episode_inputs import (
    EXECUTION_POLICY_BINDING, POLICY_BINDINGS, policy_binding, read_inputs_manifest, verify_frozen_inputs)
from so101_demo.act.general_runtime_policy import load_general_runtime_policy
from so101_demo.act.teacher_endpoint import EXECUTION_VALUES, load_teacher_execution_policy
from paths import PACKAGE_ROOT

CONFIG = PACKAGE_ROOT / "config/act"
TEACHER_POLICY_FILE = "teacher_execution_policy.yaml"
TEACHER_POLICY_PATH = CONFIG / TEACHER_POLICY_FILE
GENERAL_POLICY_PATH = CONFIG / "general_runtime_policy.yaml"


def test_the_teacher_policy_loads_with_the_motion_place_and_gate_values():
    policy = load_teacher_execution_policy(TEACHER_POLICY_PATH)
    assert policy["schema_version"] == 3
    assert (policy["state_max_age_s"], policy["state_unavailable_stop_s"], policy["execution_deadline_s"]) == (0.5, 1.0, 180.0)
    assert (policy["grasp_stable_dwell_s"], policy["release_settle_dwell_s"]) == (0.25, 0.5)
    assert (policy["arm_stop_wait_s"], policy["arm_stop_velocity_rad_s"]) == (1.0, 0.002)
    assert (policy["cup_pose_source"], policy["verdict_source"]) == ("broker_rgbd", "sim_truth")
    assert policy["place_reference_offset_m"] == -0.01325 and "place_descend_offset_m" not in policy


def test_the_general_runtime_policy_carries_exactly_the_three_shared_bounds_the_teacher_policy_agrees_with():
    general = load_general_runtime_policy(GENERAL_POLICY_PATH)
    teacher = load_teacher_execution_policy(TEACHER_POLICY_PATH)
    assert set(general) == {"kind", "schema_version", "policy_sha256", *EXECUTION_VALUES}
    for key in EXECUTION_VALUES:
        assert general[key] == teacher[key], key
    assert general["kind"] != teacher["kind"] and general["policy_sha256"] != teacher["policy_sha256"]


@pytest.mark.parametrize("change", [
    {"state_max_age_s": 0}, {"state_unavailable_stop_s": -1.0}, {"execution_deadline_s": float("nan")},
    {"state_max_age_s": True}, {"kind": "ACT_TEACHER_EXECUTION_POLICY"}, {"schema_version": 2}, {"invented": 1}])
def test_the_general_runtime_loader_is_a_closed_schema(change):
    document = {**yaml.safe_load(GENERAL_POLICY_PATH.read_bytes()), **change}
    with pytest.raises(ValueError, match="GENERAL_RUNTIME_POLICY_INVALID"):
        load_general_runtime_policy(yaml.safe_dump(document).encode())
    document = yaml.safe_load(GENERAL_POLICY_PATH.read_bytes())
    del document["execution_deadline_s"]
    with pytest.raises(ValueError, match="GENERAL_RUNTIME_POLICY_INVALID"):
        load_general_runtime_policy(yaml.safe_dump(document).encode())


@pytest.fixture()
def document():
    return yaml.safe_load(TEACHER_POLICY_PATH.read_bytes())


def load_document(value):
    return load_teacher_execution_policy(yaml.safe_dump(value).encode())


@pytest.mark.parametrize("change", [
    {"grasp_stable_dwell_s": 0.0}, {"grasp_stable_dwell_s": -1.0}, {"grasp_stable_dwell_s": 6.0}, {"release_settle_dwell_s": 6.0},
    {"release_settle_dwell_s": float("nan")}, {"arm_stop_wait_s": 0.0}, {"arm_stop_wait_s": 6.0}, {"arm_stop_velocity_rad_s": 0.0},
    {"arm_stop_velocity_rad_s": 0.5}, {"cup_pose_source": "sim_truth"}, {"cup_pose_source": "wrist_estimator"},
    {"verdict_source": "broker_rgbd"}, {"grasp_stable_dwell_s": "0.25"}, {"grasp_stable_dwell_s": True},
    {"place_height_mode": "constant"}, {"place_touchdown_guard_m": 0.0003}, {"schema_version": 4}, {"schema_version": 2}])
def test_the_teacher_loader_refuses_out_of_range_and_foreign_values(document, change):
    document.update(change)
    with pytest.raises(ValueError, match="TEACHER_EXECUTION_POLICY_INVALID"):
        load_document(document)


def test_the_teacher_loader_is_a_closed_schema(document):
    for key in set(document) - {"kind", "schema_version"}:
        missing = dict(document)
        del missing[key]
        with pytest.raises(ValueError, match="TEACHER_EXECUTION_POLICY_INVALID"):
            load_document(missing)
    with pytest.raises(ValueError, match="TEACHER_EXECUTION_POLICY_INVALID"):
        load_document({**document, "place_descend_offset_m": -0.01325})            # the policy cannot express a constant offset
    with pytest.raises(ValueError, match="TEACHER_EXECUTION_POLICY_INVALID"):
        load_document({**document, "invented": 1})


def test_the_policy_binding_names_the_teacher_policy_file():
    assert EXECUTION_POLICY_BINDING == "teacher_execution_policy"
    assert POLICY_BINDINGS[EXECUTION_POLICY_BINDING] == (TEACHER_POLICY_FILE, "config/act/" + TEACHER_POLICY_FILE)
    binding = policy_binding(EXECUTION_POLICY_BINDING, TEACHER_POLICY_PATH.read_bytes())
    assert binding["path"] == "policies/" + TEACHER_POLICY_FILE and binding["values"]["schema_version"] == 3
    with pytest.raises(ValueError, match="TEACHER_EXECUTION_POLICY_INVALID"):
        policy_binding(EXECUTION_POLICY_BINDING, GENERAL_POLICY_PATH.read_bytes())    # the general policy is not a Teacher policy


def test_a_freeze_binds_the_teacher_policy_and_the_teacher_names_it(tmp_path):
    from test_act_child_recorder_binding import frozen_child_inputs

    manifest_path, document, _ = frozen_child_inputs(tmp_path)
    assert EXECUTION_POLICY_BINDING in document
    assert document[EXECUTION_POLICY_BINDING]["file_sha256"] == hashlib.sha256(TEACHER_POLICY_PATH.read_bytes()).hexdigest()
    frozen, snapshot, _ = load_teacher_frozen_inputs(manifest_path)
    assert snapshot["files"]["config/act/" + TEACHER_POLICY_FILE]["sha256"] == document[EXECUTION_POLICY_BINDING]["file_sha256"]
    assert frozen[EXECUTION_POLICY_BINDING]["values"]["schema_version"] == 3


def test_a_manifest_binding_a_foreign_execution_policy_name_is_refused(tmp_path):
    from test_act_child_recorder_binding import frozen_child_inputs
    from test_act_policy_freeze import rehash

    manifest_path, document, _ = frozen_child_inputs(tmp_path)
    document["teacher_execution_policy_v1"] = document[EXECUTION_POLICY_BINDING]
    rehash(manifest_path, document)
    for call in (read_inputs_manifest, verify_frozen_inputs, load_teacher_frozen_inputs):
        with pytest.raises(ValueError, match="INPUTS_MANIFEST_INVALID"):
            call(manifest_path)


def test_the_execution_snapshot_carries_the_teacher_policy_file_like_the_others(tmp_path):
    from test_act_child_recorder_binding import frozen_child_inputs

    _, _, snapshot = frozen_child_inputs(tmp_path)
    assert "config/act/" + TEACHER_POLICY_FILE in snapshot["files"]
    assert "config/act/general_runtime_policy.yaml" in snapshot["files"]
