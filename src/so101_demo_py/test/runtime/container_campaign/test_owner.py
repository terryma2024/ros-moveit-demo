"""Campaign ownership uses real service/launch state with external model I/O controlled."""

import asyncio
from dataclasses import asdict,replace
import hashlib
import importlib
import json
from types import SimpleNamespace

import pytest

from test_service_owner import fixture as service_fixture
from so101_teleop.unified.worker_slots import ActWorkerSlot


def fixture(tmp_path,**kwargs):
    service,registry,calls,containers = service_fixture(tmp_path,**kwargs)
    slot = ActWorkerSlot('campaign','w00',1,181,'/act/campaign/w00','/act/campaign/w00/arm_controller')
    sha = hashlib.sha256(json.dumps([asdict(slot)],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    path = service.paths['run']/'functional.json'
    scenes = service.paths['run']/'scenes.json'
    scenes.write_text(json.dumps({'scenarios':[dict(scene_id=f'functional-{i}',split='validation') for i in range(8)]}))
    context = replace(service.context,worker_count=1,domain_session_map_sha256=sha)
    identity={name:getattr(context,name) for name in ('source_sha256','runtime_config_sha256',
        'collection_config_sha256','contact_policy_fingerprint')}
    identity.update(gpu_uuid=context.physical_gpu_uuid,image_source_install=dict(
        inference=service.config['head_service']['image'],shard=service.config['shard_image']))
    manifest=dict(schema_version=1,kind='ACT_COLLECTION_FUNCTIONAL_RUN',run_id='functional',worker_count=1,
        controlled_identity=identity,scene_manifest=dict(path=str(scenes),sha256=hashlib.sha256(scenes.read_bytes()).hexdigest()))
    path.write_text(json.dumps(manifest))
    context=replace(context,manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    service.context=context
    stopped=[]
    coordinator=SimpleNamespace(stop_dispatch=lambda reason:stopped.append(reason))
    def launcher(**values):
        pytest.fail('partial service failure must precede any shard preparation')
    owner=importlib.import_module('so101_demo.runtime.container_campaign.owner').ContainerCampaignOwner(
        admitted_context=context,config=service.config,root=service.paths['run'],service_owner=service,
        slots=(slot,),manifest_path=path,qualification=True,launcher=launcher,coordinator=coordinator,
        verifier=SimpleNamespace(),monotonic_ns=service.clock,approved_disk_floor_bytes=0)
    return owner,service,registry,calls,containers,manifest,stopped


def test_partial_service_start_has_single_cleanup_and_keeps_unknown_launch_fenced(tmp_path):
    owner,service,registry,calls,containers,manifest,stopped=fixture(tmp_path,fail_teacher=True)
    async def run():
        with pytest.raises(ValueError,match='SERVICE_OWNER_START_FAILED'):
            await owner.run(manifest)
        first,second=await asyncio.gather(owner.close(),owner.close())
        assert first==second and first['terminated'] is False
        assert len([v for v in calls if v[:2]==['docker','run']])==2
        assert not containers['1'*64]['State']['Running']
        assert stopped and registry.records()[1]['owner'] is None
        with pytest.raises(ValueError,match='CAMPAIGN_OWNER_ALREADY_STARTED'):
            await owner.run(manifest)
    try:
        asyncio.run(run())
    finally:
        registry.close()


def test_changed_manifest_refuses_before_services_or_index(tmp_path):
    owner,service,registry,calls,containers,manifest,stopped=fixture(tmp_path)
    owner.manifest_path.write_text('{}')
    async def run():
        with pytest.raises(ValueError,match='CAMPAIGN_MANIFEST_CHANGED'):
            await owner.run(manifest)
        assert calls==[] and registry.records()==()
        assert not (owner.root/'campaign-index.json').exists()
        assert (await owner.close())['terminated'] is False
    try:
        asyncio.run(run())
    finally:
        registry.close()


def test_disk_floor_fences_dispatch_before_services_without_lowering_floor(tmp_path):
    owner,service,registry,calls,containers,manifest,stopped=fixture(tmp_path)
    owner.disk_reader=lambda root:0
    async def run():
        with pytest.raises(ValueError,match='CAMPAIGN_DISK_FLOOR_REACHED'):
            await owner.run(manifest)
        assert owner.dispatch_stopped and stopped==['CAMPAIGN_DISK_FLOOR_REACHED']
        assert calls==[] and registry.records()==()
        assert owner.approved_disk_floor_bytes==0
        await owner.close()
    try:
        asyncio.run(run())
    finally:
        registry.close()
