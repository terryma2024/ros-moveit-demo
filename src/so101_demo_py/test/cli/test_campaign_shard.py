"""A private shard validates its immutable spec before creating ROS or processes."""

import importlib
import json
from pathlib import Path
import shutil

import pytest


def fixture(tmp_path):
    root = tmp_path / "wave-00/w00/g1"
    root.mkdir(parents=True)
    runtime = tmp_path / "runtime.yaml"
    source = Path(__file__).parents[2] / "config/mujoco/parallel_batch_linux_cuda.yaml"
    shutil.copyfile(source, runtime)
    import hashlib
    document = dict(schema_version=1, kind="ACT_CONTAINER_SHARD", workload_kind="no_motion_readiness",
        campaign_id="campaign", worker_id="w00", launch_generation=1, execution_generation=3,
        runtime_id="runtime1", service_epoch="epoch1", service_token="1"*64,
        owned_root=str(root), ros_namespace="/act/campaign/w00", ros_domain_id=181,
        simulation_session_id="campaign-wave00-w00-g1", gpu_uuid="GPU-28221cec-9d21-7753-fd5a-da645740df19",
        controlled_runtime=dict(path=str(runtime), sha256=hashlib.sha256(runtime.read_bytes()).hexdigest()))
    path = tmp_path / "shard.json"
    path.write_text(json.dumps(document,indent=2)+"\n")
    return path, document


def test_frozen_config_supplies_owner_and_startup_budgets(tmp_path):
    mod = importlib.import_module("so101_demo.cli.campaign_shard")
    path, document = fixture(tmp_path)
    spec, runtime = mod.load_spec(path)
    assert spec == document
    assert runtime.heartbeat_timeout_s == 5.0
    assert runtime.initializing_hard_timeout_s == 180.0


@pytest.mark.parametrize("problem", ["version", "extra", "root", "namespace", "domain", "generation", "backend", "scope", "hash"])
def test_bad_spec_refused_before_runtime_factory(tmp_path, monkeypatch, problem):
    mod = importlib.import_module("so101_demo.cli.campaign_shard")
    path, document = fixture(tmp_path)
    if problem == "version": document["schema_version"] = True
    elif problem == "extra": document["hardware"] = True
    elif problem == "root": document["owned_root"] = "relative"
    elif problem == "namespace": document["ros_namespace"] = "/"
    elif problem == "domain": document["ros_domain_id"] = True
    elif problem == "generation": document["launch_generation"] = True
    elif problem == "backend": document["workload_kind"] = "hardware"
    elif problem == "scope": document["worker_id"] = "w01"
    elif problem == "hash": document["controlled_runtime"]["sha256"] = "f"*64
    path.write_text(json.dumps(document))
    monkeypatch.setattr(mod, "run_shard", lambda *args: pytest.fail("invalid spec started a runtime"))
    assert mod.main(["--spec", str(path)]) == 2


def test_shard_entry_cannot_start_host_ros(tmp_path):
    import asyncio

    mod = importlib.import_module("so101_demo.cli.campaign_shard")
    path, _document = fixture(tmp_path)
    spec, runtime = mod.load_spec(path)
    with pytest.raises(ValueError, match="CAMPAIGN_SHARD_PRIVATE_CONTAINER_REQUIRED"):
        asyncio.run(mod.run_shard(spec,runtime))


def test_no_motion_image_gate_cannot_forward_a_goal():
    import asyncio

    mod = importlib.import_module("so101_demo.cli.campaign_shard")
    driver = mod.NoMotionReadinessDriver(None)
    for operation in (driver.submit,driver.cancel,driver.terminal):
        with pytest.raises(ValueError, match="SHARD_READINESS_HAS_NO_MOTION_PORT"):
            asyncio.run(operation(object()))
