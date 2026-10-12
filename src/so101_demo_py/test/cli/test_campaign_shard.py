"""A private shard validates its immutable spec before creating ROS or processes."""

import importlib
import json
from pathlib import Path
import shutil
import hashlib
import time

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


def collection_fixture(tmp_path):
    from test_config_identity import campaign_fixture,write_config
    path,document=fixture(tmp_path)
    campaign=campaign_fixture(tmp_path)
    campaign['gpu_uuid']=document['gpu_uuid']
    campaign_path=write_config(tmp_path,campaign)
    original_runtime=dict(document['controlled_runtime'])
    identity=dict(manifest_sha256='a'*64,runtime_config_sha256=campaign['controlled_runtime']['sha256'],
        collection_config_sha256='c'*64,contact_policy_fingerprint='d'*64)
    document.update(workload_kind='act_collection',controlled_runtime=campaign['controlled_runtime'],
        parallel_runtime=original_runtime,business_identity=identity,
        campaign_config=dict(path=str(campaign_path),sha256=hashlib.sha256(campaign_path.read_bytes()).hexdigest()),
        wave_id='wave-00',deadline_monotonic_s=time.monotonic()+3600)
    path.write_text(json.dumps(document))
    return path,document


def test_collection_spec_uses_original_controlled_json_and_builds_the_task_builder(tmp_path):
    """Real spec loader and real builder selection; the native stack is an opaque object."""
    import functools
    mod=importlib.import_module('so101_demo.cli.campaign_shard')
    path,document=collection_fixture(tmp_path)
    actual,runtime=mod.load_spec(path)
    assert actual==document and runtime.heartbeat_timeout_s==5.
    stack=object()
    builder=mod.shard_builder(actual,stack=stack,output_root=Path('/act/output'))
    from so101_demo.runtime.container_campaign.task_builder import build_collection_task
    assert type(builder) is functools.partial and builder.func is build_collection_task
    assert builder.args==() and builder.keywords==dict(stack=stack,shard_spec=actual,output_root=Path('/act/output'))
    assert not hasattr(mod,'build_shard_driver') and not hasattr(mod,'ChildRuntime')


def test_readiness_workload_builder_refuses_every_task(tmp_path):
    mod=importlib.import_module('so101_demo.cli.campaign_shard')
    path,_document=fixture(tmp_path)
    spec,_runtime=mod.load_spec(path)
    builder=mod.shard_builder(spec,stack=object(),output_root=tmp_path)
    with pytest.raises(ValueError,match='SHARD_READINESS_HAS_NO_MOTION_PORT'):
        builder(object())
    with pytest.raises(ValueError,match='CAMPAIGN_SHARD_WORKLOAD_UNKNOWN'):
        mod.shard_builder(dict(spec,workload_kind='hardware'),stack=object(),output_root=tmp_path)


@pytest.mark.parametrize('damage',['extra','missing','hash','identity','wave','expired','bool_deadline'])
def test_bad_collection_spec_refuses_before_any_native_runtime(tmp_path,monkeypatch,damage):
    mod=importlib.import_module('so101_demo.cli.campaign_shard')
    path,document=collection_fixture(tmp_path)
    if damage=='extra':document['allow_legacy']=True
    elif damage=='missing':document.pop('campaign_config')
    elif damage=='hash':document['parallel_runtime']['sha256']='f'*64
    elif damage=='identity':document['business_identity']['runtime_config_sha256']='f'*64
    elif damage=='wave':document['wave_id']='wave-1'
    elif damage=='expired':document['deadline_monotonic_s']=time.monotonic()-1
    else:document['deadline_monotonic_s']=True
    path.write_text(json.dumps(document))
    monkeypatch.setattr(mod,'run_shard',lambda *args:pytest.fail('bad collection spec started native runtime'))
    assert mod.main(['--spec',str(path)])==2
