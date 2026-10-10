"""CP-3504 (design 2026-10-10-so101-teacher-minimal-runtime-gates): Teacher execution policy v3 - the loader, the freeze binding
(exactly one of v1/v2/v3) and the guarantee that v1 and v2 stay byte-identical."""

import hashlib
import json

import pytest
import yaml

from so101_demo.act.frozen_runtime_inputs import frozen_execution_policy_name, load_teacher_frozen_inputs
from so101_demo.act.first_episode_inputs import (
    EXECUTION_POLICY_BINDINGS, POLICY_BINDINGS, policy_binding, read_inputs_manifest, verify_frozen_inputs)
from so101_demo.act.teacher_endpoint import load_teacher_execution_policy
from paths import PACKAGE_ROOT

CONFIG = PACKAGE_ROOT / "config/act"
V1, V2, V3 = (CONFIG / f"teacher_execution_policy_v{n}.yaml" for n in (1, 2, 3))
V3_NAME = "teacher_execution_policy_v3.yaml"
#: v1 and v2 are frozen artifacts of earlier rounds: a change of one byte is a new policy, never an edit
V1_SHA256 = "af0a56995b211bf6008a938e5437a1246a54cdabfc81623004f6493591cd96b9"
V2_SHA256 = "eb9ea49282c2fd558f331da97f1b7425345233c1d4534a7452e89cef5420ad67"


def test_v1_and_v2_stay_byte_identical():
    assert hashlib.sha256(V1.read_bytes()).hexdigest() == V1_SHA256
    assert hashlib.sha256(V2.read_bytes()).hexdigest() == V2_SHA256


def test_v3_loads_with_the_v2_motion_and_place_values_and_its_own_fields():
    two, three = load_teacher_execution_policy(V2), load_teacher_execution_policy(V3)
    assert three["schema_version"] == 3 and two["schema_version"] == 2
    for key in set(two) - {"schema_version", "policy_sha256"}:
        assert three[key] == two[key], key          # the motion, the carry scaling and the place strategy are v2's
    assert (three["grasp_stable_dwell_s"], three["release_settle_dwell_s"]) == (0.25, 0.5)
    assert (three["arm_stop_wait_s"], three["arm_stop_velocity_rad_s"]) == (1.0, 0.002)
    assert (three["cup_pose_source"], three["verdict_source"]) == ("broker_rgbd", "sim_truth")
    assert three["place_reference_offset_m"] == -0.01325 and "place_descend_offset_m" not in three
    assert three["policy_sha256"] not in (two["policy_sha256"], load_teacher_execution_policy(V1)["policy_sha256"])


@pytest.fixture()
def document():
    return yaml.safe_load(V3.read_bytes())


def load_document(value):
    return load_teacher_execution_policy(yaml.safe_dump(value).encode())


@pytest.mark.parametrize("change", [
    {"grasp_stable_dwell_s": 0.0}, {"grasp_stable_dwell_s": -1.0}, {"grasp_stable_dwell_s": 6.0}, {"release_settle_dwell_s": 6.0},
    {"release_settle_dwell_s": float("nan")}, {"arm_stop_wait_s": 0.0}, {"arm_stop_wait_s": 6.0}, {"arm_stop_velocity_rad_s": 0.0},
    {"arm_stop_velocity_rad_s": 0.5}, {"cup_pose_source": "sim_truth"}, {"cup_pose_source": "wrist_estimator"},
    {"verdict_source": "broker_rgbd"}, {"grasp_stable_dwell_s": "0.25"}, {"grasp_stable_dwell_s": True},
    {"place_height_mode": "constant"}, {"place_touchdown_guard_m": 0.0003}, {"schema_version": 4}])
def test_the_v3_loader_refuses_out_of_range_and_foreign_values(document, change):
    document.update(change)
    with pytest.raises(ValueError, match="TEACHER_EXECUTION_POLICY_INVALID"):
        load_document(document)


def test_the_v3_loader_is_a_closed_schema(document):
    for key in set(document) - {"kind", "schema_version"}:
        missing = dict(document)
        del missing[key]
        with pytest.raises(ValueError, match="TEACHER_EXECUTION_POLICY_INVALID"):
            load_document(missing)
    with pytest.raises(ValueError, match="TEACHER_EXECUTION_POLICY_INVALID"):
        load_document({**document, "place_descend_offset_m": -0.01325})            # v3 cannot express the v1 constant
    with pytest.raises(ValueError, match="TEACHER_EXECUTION_POLICY_INVALID"):
        load_document({**document, "invented": 1})
    v2 = yaml.safe_load(V2.read_bytes())
    for extra in ("grasp_stable_dwell_s", "cup_pose_source"):                      # and v2 cannot carry v3 fields
        with pytest.raises(ValueError, match="TEACHER_EXECUTION_POLICY_INVALID"):
            load_document({**v2, extra: document[extra]})


def test_the_policy_binding_follows_the_schema():
    assert EXECUTION_POLICY_BINDINGS == {"teacher_execution_policy_v1": 1, "teacher_execution_policy_v2": 2,
                                         "teacher_execution_policy_v3": 3}
    assert POLICY_BINDINGS["teacher_execution_policy_v3"] == (V3_NAME, "config/act/" + V3_NAME)
    for name, other in (("teacher_execution_policy_v3", V2), ("teacher_execution_policy_v3", V1),
                        ("teacher_execution_policy_v2", V3), ("teacher_execution_policy_v1", V3)):
        with pytest.raises(ValueError, match="TEACHER_EXECUTION_POLICY_INVALID: binding " + name):
            policy_binding(name, other.read_bytes())
    binding = policy_binding("teacher_execution_policy_v3", V3.read_bytes())
    assert binding["path"] == "policies/" + V3_NAME and binding["values"]["schema_version"] == 3


def test_a_freeze_binds_v3_alone_and_the_teacher_names_it(tmp_path):
    from test_act_child_recorder_binding import frozen_child_inputs

    manifest_path, document, _ = frozen_child_inputs(tmp_path, execution_policy=V3_NAME)
    assert "teacher_execution_policy_v3" in document
    assert "teacher_execution_policy_v1" not in document and "teacher_execution_policy_v2" not in document
    assert document["teacher_execution_policy_v3"]["file_sha256"] == hashlib.sha256(V3.read_bytes()).hexdigest()
    frozen, snapshot, _ = load_teacher_frozen_inputs(manifest_path)
    assert frozen_execution_policy_name(frozen) == "teacher_execution_policy_v3"
    assert snapshot["files"]["config/act/" + V3_NAME]["sha256"] == document["teacher_execution_policy_v3"]["file_sha256"]
    assert frozen["teacher_execution_policy_v3"]["values"]["schema_version"] == 3


@pytest.mark.parametrize("second,source", [("teacher_execution_policy_v1", V1), ("teacher_execution_policy_v2", V2)])
def test_a_manifest_naming_v3_and_another_execution_policy_is_refused(tmp_path, second, source):
    from test_act_child_recorder_binding import frozen_child_inputs
    from test_act_policy_freeze import rehash

    manifest_path, document, _ = frozen_child_inputs(tmp_path, execution_policy=V3_NAME)
    (manifest_path.parent / "policies" / source.name).write_bytes(source.read_bytes())
    document[second] = policy_binding(second, source.read_bytes())
    rehash(manifest_path, document)
    for call in (read_inputs_manifest, verify_frozen_inputs, load_teacher_frozen_inputs):
        with pytest.raises(ValueError, match="INPUTS_MANIFEST_INVALID"):
            call(manifest_path)
    with pytest.raises(ValueError, match="INPUTS_TEACHER_POLICY_REQUIRED"):
        frozen_execution_policy_name({"teacher_execution_policy_v3": {}, second: {}})


def test_the_execution_snapshot_carries_the_v3_file_like_the_others(tmp_path):
    from test_act_child_recorder_binding import frozen_child_inputs

    _, _, snapshot = frozen_child_inputs(tmp_path, execution_policy=V3_NAME)
    for name in ("teacher_execution_policy_v1.yaml", "teacher_execution_policy_v2.yaml", V3_NAME):
        assert "config/act/" + name in snapshot["files"], name
