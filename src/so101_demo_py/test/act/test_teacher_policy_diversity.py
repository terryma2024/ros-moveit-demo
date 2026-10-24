"""Teacher execution policy schema 6 (R3-a): schema 5 plus the closed `diversity` block.

Schema 3, 4 and 5 stay the closed documents they were: every shipped file below loads and hashes exactly as it did before schema 6 existed
(the pinned policy_sha256 values were computed on the base commit d949c33e3), and none of them may carry a `diversity` key."""

import copy

import pytest
import yaml

from so101_demo.act.teacher_endpoint import (
    EXECUTION_SCHEMA_DIVERSITY,
    load_teacher_execution_policy,
    speed_policy_value,
)
from paths import PACKAGE_ROOT

CONFIG = PACKAGE_ROOT / "config/act"
INVALID = "TEACHER_EXECUTION_POLICY_INVALID"
BASE5 = CONFIG / "teacher_execution_policy_side_wrist_fast_two_leg_open_1s.yaml"
DIVERSITY = {
    "campaign_seed": 20261024,
    "start_pose": {"distribution": "uniform", "half_range_rad": 0.15, "max_redraws": 8},
    "pregrasp_height": {"distribution": "uniform", "half_range_m": 0.015},
    "place_approach_height": {"distribution": "uniform", "half_range_m": 0.015},
    "carry_via": {"distribution": "uniform_box", "half_extent_m": [0.03, 0.03, 0.03]},
    "speed_scale": {"distribution": "uniform", "low": 0.7, "high": 1.3},
    "ompl": {"num_planning_attempts": 3},
}
#: file -> (schema, policy_sha256) on the base commit, before schema 6 existed
PINNED = {
    "teacher_execution_policy.yaml": (3, "c9a1a2a0937b88ae61227e217205702abd0e9ed519b342b2f5ab4b53b2e0d9d8"),
    "teacher_execution_policy_side_wrist_fast.yaml": (4, "530032042be1c1319fdb65015a318bcb567a7626c5730e6fcf5cadc48d6dc30a"),
    "teacher_execution_policy_side_wrist_fast_carry011.yaml": (4, "9aa09598451c6d70d607527a48c78ef2a3475ac9d06cc31c999216614b3ae217"),
    "teacher_execution_policy_side_wrist_fast_carry015.yaml": (4, "f153d2b638f559a86543f0e295864cd7cbc300dd7d841eee4a12f779c382cc84"),
    "teacher_execution_policy_side_wrist_fast_carry_a.yaml": (4, "a8bea1417bcbdab3745eb441b0faeca32529bd0d8f792939f1367afd6418f6db"),
    "teacher_execution_policy_side_wrist_fast_carry_b.yaml": (4, "e449c6fe23f5aa690662fc6f8e9048829fd1b1148532adbdf6e775b443640848"),
    "teacher_execution_policy_side_wrist_fast_descend010.yaml": (5, "60db53c0625cf9309e9b6b1ddb32020143cb99753d1452d34785812a6486fa1a"),
    "teacher_execution_policy_side_wrist_fast_descend020.yaml": (5, "fee330af3e7bec6a6cbbf37f923bd6de80eb6769e3f315c7e55a4dc9c189bcdf"),
    "teacher_execution_policy_side_wrist_fast_two_leg_open_1s.yaml": (5, "8ce2552bd52c5cb71e59d8239f50f5574663eccb2feafd24dea7440331aeb358"),
}


@pytest.fixture()
def document5():
    return yaml.safe_load(BASE5.read_bytes())


@pytest.fixture()
def document6(document5):
    return {**document5, "schema_version": 6, "diversity": copy.deepcopy(DIVERSITY)}


def load_document(value):
    return load_teacher_execution_policy(yaml.safe_dump(value).encode())


def test_the_schema_constant_is_6():
    assert EXECUTION_SCHEMA_DIVERSITY == 6


@pytest.mark.parametrize("name", sorted(PINNED))
def test_schema_3_4_and_5_files_load_and_hash_exactly_as_before(name):
    schema, sha = PINNED[name]
    policy = load_teacher_execution_policy(CONFIG / name)
    assert policy["schema_version"] == schema and policy["policy_sha256"] == sha
    assert "diversity" not in policy


def test_the_shipped_schema_6_file_is_the_schema_5_file_plus_the_diversity_block(document5):
    shipped = yaml.safe_load((CONFIG / "teacher_execution_policy_side_wrist_diversity.yaml").read_bytes())
    assert {key: value for key, value in shipped.items() if key not in ("schema_version", "diversity")} == {
        key: value for key, value in document5.items() if key != "schema_version"}
    assert shipped["schema_version"] == 6
    loaded = load_teacher_execution_policy(CONFIG / "teacher_execution_policy_side_wrist_diversity.yaml")
    assert loaded["diversity"]["start_pose"]["half_range_rad"] == 0.15 and loaded["diversity"]["ompl"]["num_planning_attempts"] >= 1


def test_the_shipped_policy_plans_with_one_attempt_and_a_one_sided_via_height():
    """MoveIt runs several attempts in parallel and keeps the shortest, which reduces the diversity: one attempt is the default."""
    loaded = load_teacher_execution_policy(CONFIG / "teacher_execution_policy_side_wrist_diversity.yaml")
    assert loaded["diversity"]["ompl"] == {"num_planning_attempts": 1}
    from so101_demo.act import teacher_diversity as td

    values = [td.values_for_policy(loaded, f"act-{n:04d}") for n in range(200)]
    assert all(v["ompl"]["num_planning_attempts"] == 1 and v["ompl"]["seed_applied"] is False for v in values)
    assert all(0.0 <= v["carry_via_offset_m"][2] <= 0.03 for v in values)


def test_schema_6_carries_the_diversity_block_and_every_schema_5_value(document5, document6):
    old, new = load_document(document5), load_document(document6)
    assert new["schema_version"] == 6 and new["diversity"] == DIVERSITY
    for key in set(old) - {"schema_version", "policy_sha256"}:
        assert old[key] == new[key], key
    assert old["policy_sha256"] != new["policy_sha256"]


def test_the_diversity_block_is_frozen_with_the_policy_hash(document6):
    base = load_document(document6)
    other_seed = copy.deepcopy(document6)
    other_seed["diversity"]["campaign_seed"] += 1
    other_range = copy.deepcopy(document6)
    other_range["diversity"]["start_pose"]["half_range_rad"] = 0.10
    assert len({base["policy_sha256"], load_document(other_seed)["policy_sha256"], load_document(other_range)["policy_sha256"]}) == 3
    assert load_document(copy.deepcopy(document6))["policy_sha256"] == base["policy_sha256"]


def test_schema_6_requires_the_block_and_older_schemas_refuse_it(document5, document6):
    missing = dict(document6)
    del missing["diversity"]
    with pytest.raises(ValueError, match=INVALID):
        load_document(missing)
    for version in (3, 4, 5):
        older = {**document6, "schema_version": version}
        with pytest.raises(ValueError, match=INVALID):
            load_document(older)
    with pytest.raises(ValueError, match=INVALID):
        load_document({**yaml.safe_load((CONFIG / "teacher_execution_policy.yaml").read_bytes()), "diversity": DIVERSITY})


def test_schema_6_is_closed_and_schema_7_is_unknown(document6):
    with pytest.raises(ValueError, match=INVALID):
        load_document({**document6, "invented": 1})
    for version in (7, True, "6", 6.0):
        with pytest.raises(ValueError, match=INVALID):
            load_document({**document6, "schema_version": version})


@pytest.mark.parametrize("path,value", [
    (("campaign_seed",), -1), (("start_pose", "half_range_rad"), 0.5), (("start_pose", "max_redraws"), 0),
    (("pregrasp_height", "half_range_m"), 0.05), (("carry_via", "half_extent_m"), [0.03, 0.03, 0.2]),
    (("speed_scale", "high"), 2.0), (("speed_scale", "low"), 0.1), (("ompl", "num_planning_attempts"), 0),
])
def test_out_of_range_diversity_values_are_refused_at_policy_load(document6, path, value):
    target = document6["diversity"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError, match=INVALID) as error:
        load_document(document6)
    assert "TEACHER_DIVERSITY_INVALID" in str(error.value)


def test_a_diversity_block_that_is_not_a_mapping_is_refused(document6):
    for bad in (None, [], "x", 5):
        with pytest.raises(ValueError, match=INVALID):
            load_document({**document6, "diversity": bad})


def test_the_speed_keys_resolve_for_a_schema_6_policy(document6):
    policy = load_document(document6)
    assert speed_policy_value(policy, "retreat_velocity_scaling", 9.0) == policy["retreat_velocity_scaling"]
    assert speed_policy_value(policy, "descend_final_distance_m", 9.0, since_schema=5) == policy["descend_final_distance_m"]
