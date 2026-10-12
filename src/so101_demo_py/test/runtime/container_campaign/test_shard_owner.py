"""Production shard owner persists intents before external Docker effects."""

import asyncio
from dataclasses import asdict
import importlib
import json
import hashlib
from pathlib import Path
import time
from types import SimpleNamespace

import pytest

from so101_demo.runtime.container_campaign.launch import ShardLaunchArgs
from so101_demo.runtime.container_campaign.paths import make_campaign_paths
from so101_demo.runtime.container_campaign.registry import ContainerLaunch, ContainerLaunchRegistry
from so101_teleop.unified.contracts import AdmittedCampaignContext


def fixture(tmp_path, response, *, generation=1):
    module = importlib.import_module('so101_demo.runtime.container_campaign.shard_owner')
    paths = make_campaign_paths(tmp_path, 'campaign')
    root = paths['measurement']/'w00'/f'g{generation}'
    root.mkdir(parents=True)
    (root/'tmp').mkdir(); (root/'control').mkdir()
    spec = paths['run']/'spec.json'
    runtime = paths['run']/'runtime.yaml'
    runtime.write_bytes((Path(__file__).resolve().parents[3]/'config/mujoco/parallel_batch_linux_cuda.yaml').read_bytes())
    image = dict(digest='sha256:'+'a'*64,package_source_sha256='b'*64,install_sha256='c'*64)
    gpu = 'GPU-28221cec-9d21-7753-fd5a-da645740df19'
    context = AdmittedCampaignContext(campaign_id='campaign',operation_id='operation',
        workload_kind='act_collection_start',service_epoch='epoch',execution_generation=1,
        stable_host_id='host',physical_gpu_uuid=gpu,worker_count=1,source_sha256='d'*64,
        manifest_sha256='d'*64,runtime_config_sha256='d'*64,collection_config_sha256='d'*64,
        contact_policy_fingerprint='d'*64,domain_session_map_sha256='d'*64,resource_binding_id='binding',
        evidence_root=str(paths['run']),admitted_at_monotonic_s=1,deadline_monotonic_s=time.monotonic()+3600,
        registered_evidence_root=str(tmp_path),campaign_config_path=str(spec),campaign_config_sha256='d'*64)
    launch = ContainerLaunch(launch_id=f'measurement-w00-g{generation}',role='shard',worker_id='w00',
        wave_id='measurement',launch_generation=generation,container_name=f'so101-campaign-w00-g{generation}',
        image_digest=image['digest'],owned_root=str(root),ros_namespace='/act/campaign/w00',
        ros_domain_id=181,session_id=f'campaign-w00-g{generation}')
    spec.write_text(json.dumps(dict(schema_version=1,kind='ACT_CONTAINER_SHARD',
        workload_kind='no_motion_readiness',campaign_id='campaign',worker_id='w00',execution_generation=1,
        service_epoch='epoch',launch_generation=generation,owned_root=str(root),ros_namespace=launch.ros_namespace,
        ros_domain_id=181,simulation_session_id=launch.session_id,gpu_uuid=gpu,service_token='e'*64,
        runtime_id='runtime',controlled_runtime=dict(path=str(runtime),
            sha256=hashlib.sha256(runtime.read_bytes()).hexdigest()))))
    entry = ShardLaunchArgs(spec=spec,ros_domain_id=181,ros_namespace=launch.ros_namespace,
                            mujoco_session_id=launch.session_id)
    registry = ContainerLaunchRegistry(paths['host']/'launches.sqlite3')
    calls = []
    def docker(argv):
        calls.append(argv)
        if argv[:2] == ['docker','run']:
            assert registry.records()[0]['launch'] == asdict(launch)
            assert (root/'launch-argv.json').is_file()
            return SimpleNamespace(returncode=response[0],stdout=response[1],stderr='diagnostic')
        raise AssertionError(argv)
    owner = module.ContainerShardOwner(admitted_context=context,launch=launch,entry=entry,
        images={role:image for role in ('head','teacher','shard')},paths=paths,registry=registry,
        approved_inputs=(),config_paths=(spec,),service_token='e'*64,startup_timeout_s=.1,
        heartbeat_timeout_s=5.,max_frame_bytes=8388608,stop_timeout_s=.1,docker_runner=docker)
    return owner,registry,calls,root


@pytest.mark.parametrize('response',[(1,''),(0,'invalid-container-id')])
def test_failed_or_unknown_launch_keeps_intent_and_never_claims_cleanup(tmp_path,response):
    owner,registry,calls,root = fixture(tmp_path,response)
    async def run():
        with pytest.raises(ValueError,match='SHARD_CONTAINER_LAUNCH_FAILED'):
            await owner.start()
        first,second = await asyncio.gather(owner.close(),owner.close())
        assert first == second and first['terminated'] is False
        assert first['errors'][0]['reason'] == 'LAUNCH_OWNER_UNKNOWN'
        assert len(calls) == 1
        assert registry.records()[0]['owner'] is None
        assert (root/'launch-result.json').is_file()
        with pytest.raises(ValueError,match='SHARD_OWNER_ALREADY_STARTED'):
            await owner.start()
    try:
        asyncio.run(run())
    finally:
        registry.close()


def test_close_before_start_fences_future_launch_without_effects(tmp_path):
    owner,registry,calls,root = fixture(tmp_path,(0,'invalid'))
    async def run():
        assert (await owner.close())['terminated'] is True
        with pytest.raises(ValueError,match='SHARD_OWNER_ALREADY_STARTED'):
            await owner.start()
        assert registry.records() == () and calls == []
    try:
        asyncio.run(run())
    finally:
        registry.close()


def test_spec_drift_refused_before_durable_intent_or_docker(tmp_path):
    owner,registry,calls,root = fixture(tmp_path,(0,'invalid'))
    owner.entry.spec.write_text('{}')
    async def run():
        with pytest.raises(ValueError,match='SHARD_SPEC_CHANGED'):
            await owner.start()
        assert registry.records() == () and calls == []
    try:
        asyncio.run(run())
    finally:
        registry.close()


def test_actual_restart_of_settled_predecessor_prevents_next_intent_or_docker(tmp_path,monkeypatch):
    from test_shard_retirement import fixture as stop_fixture
    from so101_demo.runtime.container_campaign.process_identity import (
        ContainerOwnerKey,ContainerChildBinding,pid_namespace_inode,
    )
    owner,registry,calls,root=fixture(tmp_path,(0,'invalid'),generation=8)
    previous_root=tmp_path/'previous';previous_root.mkdir()
    _,old_root,process,_,retirement,_=stop_fixture(previous_root,monkeypatch)
    asyncio.run(retirement.retire(fenced=True))
    previous=ContainerLaunch(launch_id='previous-w00-g7',role='shard',worker_id='w00',wave_id='previous',
        launch_generation=7,container_name='so101-previous-g7',image_digest='sha256:'+'a'*64,
        owned_root=str(old_root),ros_namespace='/act/campaign/w00',ros_domain_id=181,session_id='session1')
    key=ContainerOwnerKey('f'*64,'2026-10-12T01:02:03.123Z','sha256:'+'a'*64,7)
    registry.register(previous);registry.bind_container(previous.launch_id,key)
    registry.bind_child(previous.launch_id,ContainerChildBinding(key,process,pid_namespace_inode(),
        str(old_root/'control/normal.sock')))
    observed=dict(Id=key.container_id,Image=key.image_digest,State=dict(StartedAt=key.docker_started_at,
        Running=False,Restarting=False,Pid=0,Status='exited',ExitCode=0))
    registry.prove_terminated(previous.launch_id,observed)
    observed['State'].update(Running=True,Pid=100,Status='running')
    inspected=[]
    def inspect_docker(argv):
        inspected.append(argv)
        assert argv==['docker','inspect',key.container_id]
        return SimpleNamespace(returncode=0,stdout=json.dumps([observed]),stderr='')
    owner.docker=inspect_docker
    async def run():
        with pytest.raises(ValueError,match='LAUNCH_STOP_UNCONFIRMED'):
            await owner.start()
        assert len(registry.records())==1 and inspected and calls==[]
    try:
        asyncio.run(run())
    finally:
        registry.close()
