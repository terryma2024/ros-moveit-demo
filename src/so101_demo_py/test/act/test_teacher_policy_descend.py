"""Teacher execution policy schema 5: the DESCEND two-stage keys and the OPEN_GRIPPER duration (round-2 plan S2).

Schema 3 and 4 stay the closed documents they were and hash byte-identically; schema 5 is schema 4 plus exactly four required keys."""

import hashlib

import pytest
import yaml

from so101_demo.act.teacher_endpoint import load_teacher_execution_policy
from paths import PACKAGE_ROOT

CONFIG = PACKAGE_ROOT / "config/act"
TEACHER_POLICY_PATH = CONFIG / "teacher_execution_policy.yaml"
FAST_POLICY_PATH = CONFIG / "teacher_execution_policy_side_wrist_fast.yaml"
CARRY015_PATH = CONFIG / "teacher_execution_policy_side_wrist_fast_carry015.yaml"
CARRY_B_PATH = CONFIG / "teacher_execution_policy_side_wrist_fast_carry_b.yaml"
DESCEND_KEYS = ("descend_approach_velocity_scaling", "descend_approach_acceleration_scaling", "descend_final_distance_m",
                "open_gripper_duration_s")
INVALID = "TEACHER_EXECUTION_POLICY_INVALID"
#: the policy_sha256 values the schema 3 and schema 4 files had before schema 5 existed (computed on the base commit 5531ab078)
SCHEMA_3_POLICY_SHA256 = "c9a1a2a0937b88ae61227e217205702abd0e9ed519b342b2f5ab4b53b2e0d9d8"


@pytest.fixture()
def document4():
    return yaml.safe_load(CARRY015_PATH.read_bytes())


@pytest.fixture()
def document5(document4):
    return {**document4, "schema_version": 5, "descend_approach_velocity_scaling": 0.10,
            "descend_approach_acceleration_scaling": 0.10, "descend_final_distance_m": 0.02, "open_gripper_duration_s": 1.0}


def load_document(value):
    return load_teacher_execution_policy(yaml.safe_dump(value).encode())


def test_schema_5_carries_the_four_keys(document5):
    policy = load_document(document5)
    assert policy["schema_version"] == 5
    assert [policy[key] for key in DESCEND_KEYS] == [0.10, 0.10, 0.02, 1.0]
    assert policy["move_above_object_velocity_scaling"] == 0.10 and policy["prepare_open_gripper_duration_s"] == 1.0


def test_schema_5_with_the_default_values_changes_nothing_but_the_version_and_the_new_keys(document4, document5):
    old, new = load_document(document4), load_document(document5)
    for key in set(old) - {"schema_version", "policy_sha256"}:
        assert old[key] == new[key], key
    assert old["policy_sha256"] != new["policy_sha256"]


@pytest.mark.parametrize("key", DESCEND_KEYS)
def test_schema_5_requires_every_new_key_and_older_schemas_refuse_them(document4, document5, key):
    missing = dict(document5)
    del missing[key]
    with pytest.raises(ValueError, match=INVALID):
        load_document(missing)
    with pytest.raises(ValueError, match=INVALID):
        load_document({**document4, key: document5[key]})                          # schema 4 is closed without them
    with pytest.raises(ValueError, match=INVALID):
        load_document({**yaml.safe_load(TEACHER_POLICY_PATH.read_bytes()), key: document5[key]})   # and so is schema 3


def test_schema_5_is_closed_and_an_unknown_schema_is_refused(document5):
    with pytest.raises(ValueError, match=INVALID):
        load_document({**document5, "invented": 1})
    for version in (7, True, "5", 5.0):
        with pytest.raises(ValueError, match=INVALID):
            load_document({**document5, "schema_version": version})


@pytest.mark.parametrize("key", DESCEND_KEYS[:2])
@pytest.mark.parametrize("value", [0, 0.0, -0.1, 1.0001, float("nan"), float("inf"), True, "0.1", None, [0.1]])
def test_the_descend_approach_scalings_are_limited_to_the_open_unit_interval(document5, key, value):
    with pytest.raises(ValueError, match=INVALID):
        load_document({**document5, key: value})


@pytest.mark.parametrize("value", [0, 0.0, 0.005, 0.0049, -0.02, 0.0501, 0.1, float("nan"), float("inf"), True, "0.02", None])
def test_the_final_distance_is_limited_to_above_five_millimetres_through_fifty(document5, value):
    with pytest.raises(ValueError, match=INVALID):
        load_document({**document5, "descend_final_distance_m": value})


@pytest.mark.parametrize("value", [0.0051, 0.02, 0.05])
def test_the_final_distance_accepts_the_range_inside_and_its_upper_end(document5, value):
    assert load_document({**document5, "descend_final_distance_m": value})["descend_final_distance_m"] == value


@pytest.mark.parametrize("value", [0, 0.0, 0.49, -1.0, 5.01, 60.0, float("nan"), float("inf"), True, "1.0", None])
def test_the_open_gripper_duration_is_limited_to_half_a_second_through_five_seconds(document5, value):
    with pytest.raises(ValueError, match=INVALID):
        load_document({**document5, "open_gripper_duration_s": value})


@pytest.mark.parametrize("value", [0.5, 5.0])
def test_the_open_gripper_duration_accepts_its_closed_range_ends(document5, value):
    assert load_document({**document5, "open_gripper_duration_s": value})["open_gripper_duration_s"] == value


def test_schema_3_and_4_files_load_and_hash_as_before():
    three = load_teacher_execution_policy(TEACHER_POLICY_PATH)
    assert three["schema_version"] == 3 and three["policy_sha256"] == SCHEMA_3_POLICY_SHA256
    for path in (FAST_POLICY_PATH, CARRY015_PATH, CONFIG / "teacher_execution_policy_side_wrist_fast_carry011.yaml"):
        four = load_teacher_execution_policy(path)
        assert four["schema_version"] == 4 and not set(DESCEND_KEYS) & set(four)
        # the hash is the sha256 of the canonical JSON of the loaded fields, so it depends on nothing the new keys add
        fields = {key: value for key, value in four.items() if key != "policy_sha256"}
        import json

        assert four["policy_sha256"] == hashlib.sha256(
            json.dumps(fields, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@pytest.mark.parametrize("name,approach", [("descend010", 0.10), ("descend020", 0.20), ("two_leg_open_1s", 0.03)])
def test_the_descend_policy_files_are_carry_b_at_schema_5_with_only_the_new_keys(name, approach):
    document4 = yaml.safe_load(CARRY_B_PATH.read_bytes())
    path = CONFIG / f"teacher_execution_policy_side_wrist_fast_{name}.yaml"
    document = yaml.safe_load(path.read_bytes())
    assert document == {**document4, "schema_version": 5, "descend_approach_velocity_scaling": approach,
                        "descend_approach_acceleration_scaling": approach, "descend_final_distance_m": 0.02,
                        "open_gripper_duration_s": 1.0}
    loaded = load_teacher_execution_policy(path)
    assert loaded["schema_version"] == 5 and loaded["carry_max_velocity_scaling"] == 0.08 \
        and loaded["carry_max_acceleration_scaling"] == 0.03
