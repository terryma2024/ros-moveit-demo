"""Prepare immutable native collection instances in the admitted stable slots."""

import hashlib
from pathlib import Path
import secrets

from so101_demo.runtime.act_instance.program import instance_id_for
from so101_demo.runtime.act_instance.spec import SPEC_SCHEMA_VERSION,load_spec
from so101_demo.cli.mujoco_batch.request import _load_runtime_config
from so101_demo.runtime.container_campaign.launch import ShardLaunchArgs
from so101_demo.runtime.container_campaign.registry import ContainerLaunch,ContainerLaunchRegistry
from so101_demo.runtime.container_campaign.service_owner import _docker,_write
from so101_demo.runtime.container_campaign.shard_owner import ContainerShardOwner,read_container_namespace
from so101_demo.runtime.inference.config import load_campaign_config,validate_file_ref
from so101_teleop.unified.contracts import AdmittedCampaignContext
from so101_teleop.unified.worker_slots import ActWorkerSlot


class ContainerShardLauncher:
    def __init__(self,*,context,config,paths,registry,parallel_runtime,approved_inputs,config_paths,
                 docker_runner=_docker,namespace_reader=read_container_namespace):
        # `docker_runner` and `namespace_reader` are the owners' external edges; the defaults are the production ones.
        if (type(context) is not AdmittedCampaignContext or context.workload_kind!='act_collection_start'
                or type(registry) is not ContainerLaunchRegistry or str(paths['run'])!=context.evidence_root
                or type(approved_inputs) is not tuple or type(config_paths) is not tuple
                or load_campaign_config(context.campaign_config_path,roles=('teacher',),
                    expected_sha256=context.campaign_config_sha256)!=config):
            raise ValueError('COLLECTION_SHARD_LAUNCHER_INVALID')
        self.context,self.config,self.paths,self.registry=context,config,paths,registry
        self.parallel_runtime=dict(parallel_runtime)
        self.runtime=_load_runtime_config(validate_file_ref(parallel_runtime))
        self.approved_inputs,self.config_paths=approved_inputs,config_paths
        self.docker_runner,self.namespace_reader=docker_runner,namespace_reader
        self._next_wave=0
        self._prepared={}

    def _launch(self,*,slot,wave_id,generation,short,root,session):
        return ContainerLaunch(launch_id=wave_id+'-'+slot.worker_id+'-g'+str(generation),role='shard',
            worker_id=slot.worker_id,wave_id=wave_id,launch_generation=generation,
            container_name='so101-act-'+short+'-'+slot.worker_id+'-g'+str(generation),
            image_digest=self.config['shard_image']['digest'],owned_root=str(root),session_id=session)

    def _owner(self,*,launch,entry,spec_path,token,images,endpoints):
        return ContainerShardOwner(admitted_context=self.context,launch=launch,entry=entry,
            images=images,paths=self.paths,registry=self.registry,approved_inputs=self.approved_inputs,
            config_paths=tuple(dict.fromkeys((*self.config_paths,spec_path))),service_token=token,
            startup_timeout_s=self.runtime.initializing_hard_timeout_s,
            status_timeout_s=self.runtime.heartbeat_timeout_s,max_frame_bytes=self.runtime.broker_max_frame_bytes,
            stop_timeout_s=self.runtime.worker_recovery_timeout_s,
            docker_runner=self.docker_runner,namespace_reader=self.namespace_reader)

    def __call__(self,*,plan,endpoints,slots):
        wave=plan['wave_index']
        if (type(wave) is not int or wave!=self._next_wave or type(slots) is not tuple
                or len(slots)!=self.context.worker_count
                or any(type(slot) is not ActWorkerSlot or slot.campaign_id!=self.context.campaign_id
                    or slot.execution_generation!=self.context.execution_generation
                    or slot.worker_id!=f'w{index:02d}' for index,slot in enumerate(slots))):
            raise ValueError('COLLECTION_SHARD_WAVE_INVALID')
        validate_file_ref(self.parallel_runtime)
        config=load_campaign_config(self.context.campaign_config_path,roles=('teacher',),
            expected_sha256=self.context.campaign_config_sha256)
        if config!=self.config:raise ValueError('COLLECTION_SHARD_CONFIG_DRIFT')
        identity={name:getattr(self.context,name) for name in (
            'manifest_sha256','runtime_config_sha256','collection_config_sha256','contact_policy_fingerprint')}
        short=hashlib.sha256((self.context.campaign_id+':'+self.context.operation_id).encode()).hexdigest()[:16]
        wave_id='wave-'+str(wave)
        generation=wave+1
        images=dict(head=config['head_service']['image'],teacher=config['teacher_service']['image'],
                    shard=config['shard_image'])
        owners=[]
        for slot in slots:
            root=self.paths['run']/wave_id/slot.worker_id/('g'+str(generation))
            root.mkdir(parents=True,mode=0o700)
            (root/'tmp').mkdir(mode=0o700)
            for name in ('control','output','task-inputs'):
                (root/name).mkdir(mode=0o700)
            session='act-'+short+'-'+slot.worker_id+'-g'+str(generation)
            runtime_id='runtime-'+short+'-'+slot.worker_id+'-g'+str(generation)
            token=secrets.token_hex(32)
            spec=dict(schema_version=SPEC_SCHEMA_VERSION,kind='ACT_CONTAINER_SHARD',workload_kind='act_collection',
                campaign_id=self.context.campaign_id,worker_id=slot.worker_id,
                launch_generation=generation,execution_generation=self.context.execution_generation,
                runtime_id=runtime_id,service_epoch=self.context.service_epoch,service_token=token,
                owned_root=str(root),
                simulation_session_id=session,gpu_uuid=self.context.physical_gpu_uuid,
                controlled_runtime=config['controlled_runtime'],business_identity=identity,
                parallel_runtime=self.parallel_runtime,campaign_config=dict(path=self.context.campaign_config_path,
                    sha256=self.context.campaign_config_sha256),wave_id=wave_id,
                deadline_monotonic_s=self.context.deadline_monotonic_s)
            spec_path=self.paths['run']/('shard-'+wave_id+'-'+slot.worker_id+'-g'+str(generation)+'.json')
            _write(spec_path,spec)
            if load_spec(spec_path)[0]!=spec:raise ValueError('COLLECTION_SHARD_SPEC_DRIFT')
            launch=self._launch(slot=slot,wave_id=wave_id,generation=generation,short=short,root=root,session=session)
            if launch.launch_id!=instance_id_for(spec):raise ValueError('COLLECTION_SHARD_INSTANCE_ID_DRIFT')
            entry=ShardLaunchArgs(spec=spec_path,mujoco_session_id=session)
            owners.append(self._owner(launch=launch,entry=entry,spec_path=spec_path,token=token,images=images,
                endpoints=endpoints))
        self._prepared[wave]=tuple(owners)
        self._next_wave+=1
        return tuple(owners)
