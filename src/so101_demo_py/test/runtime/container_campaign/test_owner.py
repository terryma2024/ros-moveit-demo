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
        inference=service.config['teacher_service']['image'],shard=service.config['shard_image']))
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
        assert len([v for v in calls if v[:2]==['docker','run']])==1
        assert containers=={}
        assert stopped and registry.records()[0]['owner'] is None
        with pytest.raises(ValueError,match='CAMPAIGN_OWNER_ALREADY_STARTED'):
            await owner.run(manifest)
    try:
        asyncio.run(run())
    finally:
        registry.close()


def test_owner_refuses_head_role_for_collection(tmp_path):
    owner,service,registry,calls,containers,manifest,stopped=fixture(tmp_path)
    module=importlib.import_module('so101_demo.runtime.container_campaign.owner')
    arguments=dict(admitted_context=owner.context,config=owner.config,root=owner.root,service_owner=service,
        slots=owner.slots,manifest_path=owner.manifest_path,qualification=True,launcher=owner.launcher,
        coordinator=owner.coordinator,verifier=owner.verifier)
    try:
        assert service.roles==('teacher',)
        assert module.ContainerCampaignOwner(**arguments).services.roles==('teacher',)
        for roles in (('head','teacher'),('head',),()):
            service.roles=roles
            with pytest.raises(ValueError,match='CAMPAIGN_OWNER_CONFIG_INVALID'):
                module.ContainerCampaignOwner(**arguments)
        assert calls==[] and registry.records()==()
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


# ---- waves: instance faults, release fences and the frozen index ---------------------------------------------------
# Controlled doubles: the shard owner (`FakeShard`, substituted for `ContainerShardOwner` in the owner module), the wave
# coordinator and the wave verifier. The service owner, registry, Docker double and campaign owner are the real ones.


class FakeShard:
    def __init__(self, owner, wave, *, release=True):
        slot = owner.slots[0]
        self.context, self.registry, self.release = owner.context, owner.registry, release
        self.launch = SimpleNamespace(worker_id=slot.worker_id, ros_domain_id=slot.ros_domain_id,
            ros_namespace=slot.namespace, wave_id='wave-'+str(wave), launch_id=f'wave-{wave}-w00-g1')
        self.closes = self.health_checks = 0

    async def check_health(self):
        self.health_checks += 1
        raise AssertionError('instance health is polled by the wave coordinator, not by the campaign monitor')

    async def close(self):
        self.closes += 1
        return dict(terminated=self.release, launch_id=self.launch.launch_id, errors=[])


def wave_owner(tmp_path, monkeypatch, *, scene_count, releases=(True, True), verify=None):
    owner, service, registry, calls, containers, manifest, stopped = fixture(tmp_path)
    module = importlib.import_module('so101_demo.runtime.container_campaign.owner')
    monkeypatch.setattr(module, 'ContainerShardOwner', FakeShard)
    manifest = {'scenarios': [dict(scene_id=f'scene-{i:02d}', split='validation') for i in range(scene_count)]}
    owner.manifest_path.write_text(json.dumps(manifest))
    context = replace(owner.context, manifest_sha256=hashlib.sha256(owner.manifest_path.read_bytes()).hexdigest())
    owner.context = service.context = context
    owner.qualification = False
    made, waves = [], []

    def launcher(*, plan, endpoints, slots):
        shard = FakeShard(owner, plan['wave_index'], release=releases[min(plan['wave_index'], len(releases)-1)])
        made.append(shard)
        return (shard,)

    async def run_wave(*, plan, shards, endpoints, dispatch_allowed):
        waves.append(plan['wave_index'])
        await asyncio.sleep(.05)    # lets the campaign monitor run its first pass during the wave
        return dict(wave_index=plan['wave_index'], coordinator_root='x', case_results=[], infra_errors=[])

    owner.launcher = launcher
    owner.coordinator = SimpleNamespace(stop_dispatch=lambda reason: stopped.append(reason), run_wave=run_wave,
        complete_wave_cleanup=lambda plan, shards: None)
    owner.verifier = SimpleNamespace(verify_wave=verify or (lambda plan, outcome, shards: dict(wave_index=plan['wave_index'],
        scene_count=len(plan['scene_ids']), coordinator_root='x', case_results=[])))
    return SimpleNamespace(owner=owner, service=service, registry=registry, calls=calls, containers=containers,
        manifest=manifest, stopped=stopped, made=made, waves=waves)


def test_shard_fault_preserves_shared_service(tmp_path, monkeypatch):
    def refuse(plan, outcome, shards):
        raise ValueError('CONTAINER_WAVE_COMMIT_READBACK_INVALID')
    world = wave_owner(tmp_path, monkeypatch, scene_count=8, verify=refuse)
    owner = world.owner

    async def run():
        with pytest.raises(ValueError, match='CONTAINER_WAVE_COMMIT_READBACK_INVALID'):
            await owner.run(world.manifest)
        # the wave failed, but neither the campaign nor the shared services were stopped by it
        assert owner.stop_reason == 'CAMPAIGN_RUN_INTERRUPTED'
        assert owner.stop_reason != 'CAMPAIGN_RESOURCE_OR_SERVICE_FAULT'
        assert [c for c in world.calls if c[:2] == ['docker', 'kill']] == []
        assert all(item['State']['Running'] for item in world.containers.values())
        assert world.made[0].closes == 1 and world.made[0].health_checks == 0
        result = await owner.close()
        assert result['terminated'] is True and not any(item['State']['Running'] for item in world.containers.values())
    try:
        asyncio.run(run())
    finally:
        world.registry.close()


def test_unreleased_instance_blocks_next_wave(tmp_path, monkeypatch):
    world = wave_owner(tmp_path, monkeypatch, scene_count=21, releases=(False,))
    owner = world.owner

    async def run():
        with pytest.raises(ValueError, match='CAMPAIGN_SHARD_STOP_UNCONFIRMED'):
            await owner.run(world.manifest)
        assert world.waves == [0] and len(world.made) == 1 and owner.stop_reason == 'CAMPAIGN_SHARD_STOP_UNCONFIRMED'
        assert not (owner.root/'collection-index.json').exists()
        assert (await owner.close())['terminated'] is False
    try:
        asyncio.run(run())
    finally:
        world.registry.close()


def test_frozen_index_is_written_once_after_the_last_wave(tmp_path, monkeypatch):
    def verified(plan, outcome, shards):
        rows = []
        for scene in plan['scene_ids']:
            task = 'wave-'+str(plan['wave_index'])+'-w00-'+scene
            proof = dict(result_status='PASSED', teacher_execution_status='COMPLETED', teacher_task_result='PASS',
                act_data_status='VALID', act_data_reason=None, act_data_qc='PASS', export_eligible=scene.endswith('0'),
                result_sha256='a'*64, task_result_sha256='b'*64, location='/loc/'+task)
            rows.append(dict(scene_id=scene, worker_id='w00', task_id=task, launch_id='l', location='/out/'+task, proof=proof,
                registration='/host/'+task+'/collected.json', owner_root='/owner', scope_path='/scope', inputs_manifest='/inputs'))
        return dict(wave_index=plan['wave_index'], scene_count=len(rows), coordinator_root='x', case_results=rows)
    world = wave_owner(tmp_path, monkeypatch, scene_count=21, verify=verified)
    owner = world.owner

    async def run():
        result = await owner.run(world.manifest)
        assert world.waves == [0, 1] and len(result['waves']) == 2
        index = json.loads((owner.root/'collection-index.json').read_text())
        assert index['kind'] == 'act_collection_frozen_index' and index['qualification'] is False and index['scene_count'] == 21
        assert len(index['collected_tasks']) == 21
        assert [item['scene_id'] for item in index['committed_episodes']] == ['scene-00', 'scene-10', 'scene-20']
        assert all(item['schema_version'] == 3 for item in index['committed_episodes'])
        await owner.close()
    try:
        asyncio.run(run())
    finally:
        world.registry.close()
