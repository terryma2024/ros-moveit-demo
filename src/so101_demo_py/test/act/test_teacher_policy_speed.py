"""Teacher execution policy schema 4: the speed keys (plan 2026-10-20 teacher speed tiers 1 and 2, items 18d/18e/18f).

Schema 3 stays the closed document it was and hashes byte-identically; schema 4 adds exactly five keys, each of which defaults (in the
default-valued document) to today's behaviour."""

import pytest
import yaml

from so101_demo.act.teacher_endpoint import load_teacher_execution_policy
from paths import PACKAGE_ROOT

CONFIG = PACKAGE_ROOT / "config/act"
TEACHER_POLICY_PATH = CONFIG / "teacher_execution_policy.yaml"
FAST_POLICY_PATH = CONFIG / "teacher_execution_policy_side_wrist_fast.yaml"
SPEED_KEYS = ("move_above_object_velocity_scaling", "move_above_object_acceleration_scaling", "retreat_velocity_scaling",
              "retreat_acceleration_scaling", "prepare_open_gripper_duration_s")
#: the policy_sha256 the schema 3 file had before schema 4 existed: a schema 3 freeze must load and hash byte-identically
SCHEMA_3_POLICY_SHA256 = "c9a1a2a0937b88ae61227e217205702abd0e9ed519b342b2f5ab4b53b2e0d9d8"
INVALID = "TEACHER_EXECUTION_POLICY_INVALID"


@pytest.fixture()
def document():
    return yaml.safe_load(TEACHER_POLICY_PATH.read_bytes())


@pytest.fixture()
def document4(document):
    return {**document, "schema_version": 4, "move_above_object_velocity_scaling": 0.03,
            "move_above_object_acceleration_scaling": 0.03, "retreat_velocity_scaling": 0.03,
            "retreat_acceleration_scaling": 0.03, "prepare_open_gripper_duration_s": 2.0}


def load_document(value):
    return load_teacher_execution_policy(yaml.safe_dump(value).encode())


def test_schema_3_loads_and_hashes_byte_identically_with_no_speed_keys():
    policy = load_teacher_execution_policy(TEACHER_POLICY_PATH)
    assert policy["schema_version"] == 3 and policy["policy_sha256"] == SCHEMA_3_POLICY_SHA256
    assert not set(SPEED_KEYS) & set(policy)


def test_schema_4_carries_the_speed_keys_and_hashes_differently(document4):
    policy = load_document(document4)
    assert policy["schema_version"] == 4
    assert [policy[key] for key in SPEED_KEYS] == [0.03, 0.03, 0.03, 0.03, 2.0]
    assert policy["policy_sha256"] != SCHEMA_3_POLICY_SHA256


def test_schema_4_with_the_default_values_changes_nothing_but_the_version(document, document4):
    old, new = load_document(document), load_document(document4)
    for key in set(old) - {"schema_version", "policy_sha256"}:
        assert old[key] == new[key], key


def test_the_speed_keys_belong_to_schema_4_only(document, document4):
    for key in SPEED_KEYS:
        with pytest.raises(ValueError, match=INVALID):
            load_document({**document, key: document4[key]})             # schema 3 is closed without them
        missing = dict(document4)
        del missing[key]
        with pytest.raises(ValueError, match=INVALID):
            load_document(missing)                                       # schema 4 requires every one
    with pytest.raises(ValueError, match=INVALID):
        load_document({**document4, "invented": 1})
    with pytest.raises(ValueError, match=INVALID):
        load_document({**document4, "schema_version": 6})
    with pytest.raises(ValueError, match=INVALID):
        load_document({**document4, "schema_version": True})


@pytest.mark.parametrize("key", SPEED_KEYS[:4])
@pytest.mark.parametrize("value", [0, 0.0, -0.1, 1.0001, float("nan"), float("inf"), True, "0.1", None, [0.1]])
def test_the_speed_scalings_are_limited_to_the_open_unit_interval(document4, key, value):
    with pytest.raises(ValueError, match=INVALID):
        load_document({**document4, key: value})


@pytest.mark.parametrize("value", [0, 0.0, 0.49, -1.0, 5.01, 60.0, float("nan"), float("inf"), True, "1.0", None])
def test_the_prepare_open_duration_is_limited_to_half_a_second_through_five_seconds(document4, value):
    with pytest.raises(ValueError, match=INVALID):
        load_document({**document4, "prepare_open_gripper_duration_s": value})


@pytest.mark.parametrize("key,value", [("move_above_object_velocity_scaling", 1.0), ("retreat_acceleration_scaling", 0.001),
                                       ("prepare_open_gripper_duration_s", 0.5), ("prepare_open_gripper_duration_s", 5.0)])
def test_the_speed_keys_accept_their_closed_range_ends(document4, key, value):
    assert load_document({**document4, key: value})[key] == value


def test_the_fast_policy_changes_exactly_the_five_speed_keys_and_the_version():
    default = yaml.safe_load(TEACHER_POLICY_PATH.read_bytes())
    fast = yaml.safe_load(FAST_POLICY_PATH.read_bytes())
    assert fast["schema_version"] == 4
    assert {key: fast[key] for key in SPEED_KEYS} == {
        "move_above_object_velocity_scaling": 0.10, "move_above_object_acceleration_scaling": 0.10,
        "retreat_velocity_scaling": 0.10, "retreat_acceleration_scaling": 0.10, "prepare_open_gripper_duration_s": 1.0}
    assert {key: value for key, value in fast.items() if key not in (*SPEED_KEYS, "schema_version")} == {
        key: value for key, value in default.items() if key != "schema_version"}
    loaded = load_teacher_execution_policy(FAST_POLICY_PATH)
    assert loaded["carry_max_velocity_scaling"] == 0.03 and loaded["carry_max_acceleration_scaling"] == 0.0075
    assert (loaded["grasp_stable_dwell_s"], loaded["release_settle_dwell_s"]) == (0.25, 0.5)


@pytest.mark.parametrize("name,accel", [("011", 0.011), ("015", 0.015)])
def test_a_carry_doe_policy_differs_from_the_fast_policy_only_in_the_carry_acceleration(name, accel):
    """R3 of the plan: each DOE level is a copy of the FAST file whose only difference is carry_max_acceleration_scaling."""
    fast = yaml.safe_load(FAST_POLICY_PATH.read_bytes())
    level_path = CONFIG / f"teacher_execution_policy_side_wrist_fast_carry{name}.yaml"
    level = yaml.safe_load(level_path.read_bytes())
    assert level == {**fast, "carry_max_acceleration_scaling": accel}
    assert fast["carry_max_acceleration_scaling"] == 0.0075
    loaded = load_teacher_execution_policy(level_path)
    assert loaded["schema_version"] == 4 and loaded["carry_max_acceleration_scaling"] == accel
    assert loaded["policy_sha256"] != load_teacher_execution_policy(FAST_POLICY_PATH)["policy_sha256"]
