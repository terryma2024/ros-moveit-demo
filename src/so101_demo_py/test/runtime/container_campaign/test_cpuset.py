"""Opt-in CPU partition of the campaign's containers (`shard_cpuset`, default off): each recording shard gets its own `docker --cpuset-cpus`
range and the other roles (Teacher, Head, processors) the CPUs below the first shard's. Pure functions and argv: no Docker."""

import json

import pytest

from so101_demo.runtime.container_campaign import cpuset
from so101_demo.runtime.inference import config as config_module
from test_config_identity import campaign_fixture, write_config
from test_launch import build, fixture


def test_the_key_is_absent_by_default_and_names_a_cpu_count_per_shard_and_the_first_shard_cpu():
    assert cpuset.cpuset_from_config({}) is None
    plan = cpuset.cpuset_from_config({"shard_cpuset": {"shard_cpus": 3, "first_shard_cpu": 6}})
    assert plan == cpuset.CpuPlan(shard_cpus=3, first_shard_cpu=6) and plan.document() == {"shard_cpus": 3, "first_shard_cpu": 6}
    for bad in ({"shard_cpus": 0, "first_shard_cpu": 6}, {"shard_cpus": 3, "first_shard_cpu": 0}, {"shard_cpus": True, "first_shard_cpu": 6},
                {"shard_cpus": 3.0, "first_shard_cpu": 6}, {"shard_cpus": 3}, {"shard_cpus": 3, "first_shard_cpu": 6, "extra": 1}, [], None):
        with pytest.raises(ValueError, match="CPUSET_PLAN_INVALID"):
            cpuset.cpuset_from_config({"shard_cpuset": bad})


def test_each_shard_gets_its_own_range_and_every_other_role_the_cpus_below_the_first_shard():
    plan = cpuset.CpuPlan(shard_cpus=3, first_shard_cpu=6)
    assert [plan.cpus("shard", index, worker_count=6, host_cpus=24) for index in range(6)] == [
        "6-8", "9-11", "12-14", "15-17", "18-20", "21-23"]
    for role in ("head", "teacher", "processor"):
        assert plan.cpus(role, None, worker_count=6, host_cpus=24) == "0-5"
    assert cpuset.CpuPlan(shard_cpus=1, first_shard_cpu=1).cpus("shard", 2, worker_count=3, host_cpus=4) == "3"
    assert cpuset.CpuPlan(shard_cpus=1, first_shard_cpu=1).cpus("teacher", None, worker_count=3, host_cpus=4) == "0"


def test_a_plan_that_does_not_fit_the_host_or_the_worker_count_is_refused():
    plan = cpuset.CpuPlan(shard_cpus=3, first_shard_cpu=6)
    with pytest.raises(ValueError, match="CPUSET_PLAN_EXCEEDS_HOST"):
        plan.cpus("shard", 0, worker_count=7, host_cpus=24)       # 6 + 7*3 = 27 > 24
    with pytest.raises(ValueError, match="CPUSET_PLAN_WORKER_INVALID"):
        plan.cpus("shard", 6, worker_count=6, host_cpus=24)
    with pytest.raises(ValueError, match="CPUSET_PLAN_WORKER_INVALID"):
        plan.cpus("shard", None, worker_count=6, host_cpus=24)
    with pytest.raises(ValueError, match="CPUSET_PLAN_ROLE_INVALID"):
        plan.cpus("gpu", None, worker_count=6, host_cpus=24)


def test_the_worker_index_is_the_slot_number_of_the_worker_id():
    assert cpuset.worker_index("w00") == 0 and cpuset.worker_index("w05") == 5
    for bad in ("w5", "x01", None, "w-1"):
        with pytest.raises(ValueError, match="CPUSET_PLAN_WORKER_INVALID"):
            cpuset.worker_index(bad)


@pytest.mark.parametrize("role", ["head", "teacher", "shard"])
def test_the_argv_has_no_cpu_option_by_default_and_one_docker_option_when_given(tmp_path, role):
    module, images, paths = fixture(tmp_path, role)
    assert "--cpuset-cpus" not in build(module, images, paths, role)
    argv = build(module, images, paths, role, cpuset_cpus="6-8")
    assert argv.count("--cpuset-cpus") == 1 and argv[argv.index("--cpuset-cpus")+1] == "6-8"
    assert argv.index("--cpuset-cpus") < argv.index(images["shard" if role == "processor" else role]["digest"])   # a docker option
    assert [value for value in argv if value != "--cpuset-cpus" and value != "6-8"] == build(module, images, paths, role)


@pytest.mark.parametrize("bad", ["", "a", "6-", "8-6", "6,", " 6", "6-8;x", 6])
def test_a_malformed_cpu_list_is_refused(tmp_path, bad):
    module, images, paths = fixture(tmp_path, "shard")
    with pytest.raises(ValueError, match="CONTAINER_LAUNCH_INVALID"):
        build(module, images, paths, "shard", cpuset_cpus=bad)


def test_the_campaign_config_accepts_the_key_and_refuses_a_malformed_one(tmp_path):
    document = campaign_fixture(tmp_path)
    path = write_config(tmp_path, document | {"shard_cpuset": {"shard_cpus": 3, "first_shard_cpu": 6}})
    assert config_module.load_campaign_config(path)["shard_cpuset"] == {"shard_cpus": 3, "first_shard_cpu": 6}
    assert "shard_cpuset" not in config_module.load_campaign_config(write_config(tmp_path, document))
    with pytest.raises(ValueError, match="CAMPAIGN_CONFIG_INVALID"):
        config_module.load_campaign_config(write_config(tmp_path, document | {"shard_cpuset": {"shard_cpus": 0, "first_shard_cpu": 6}}))
