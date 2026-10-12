"""Dispatch one frozen Worker run through its registered private shard.

Replies are transport outcomes. Only the Coordinator's original durable commits
are collection results; this runner never manufactures a result row or retries.
"""

import asyncio
import copy
import hashlib
from dataclasses import fields
from pathlib import Path

from so101_demo.act.parallel_collection_contracts import read_document,scene_ids
from so101_demo.parallel_batch.coordinator import BatchCoordinator
from so101_demo.parallel_batch.contracts.common import AttemptStatus
from so101_demo.parallel_batch.worker_parts.contracts import WorkerRunResult,adaptive_result_is_infrastructure
from so101_demo.runtime.container_campaign.service_owner import ServiceEndpoint,_write
from so101_demo.runtime.container_campaign.shard_owner import ContainerShardOwner
from so101_demo.runtime.container_campaign.worker_transport import CollectionCoordinatorTransport
from so101_demo.runtime.inference.config import validate_file_ref,load_campaign_config
from so101_teleop.unified.contracts import AdmittedCampaignContext
from so101_teleop.unified.ipc import IpcRequest


BUSINESS_FIELDS=('manifest_sha256','runtime_config_sha256',
                 'collection_config_sha256','contact_policy_fingerprint')


def _verify_worker_outcomes(rows):
    if not rows:
        raise ValueError('COLLECTION_WORKER_INFRA_FAILURE')
    expected={field.name for field in fields(WorkerRunResult)}
    for row in rows:
        if (type(row) is not dict or set(row)!=expected or type(row['recovered']) is not bool
                or type(row['stopped_reason']) is not str or not row['stopped_reason']
                or any(value is not None and (type(value) is not str or not value)
                       for name,value in row.items() if name not in {'recovered','terminal_status','stopped_reason'})):
            raise ValueError('COLLECTION_WORKER_REPLY_REJECTED')
        value=dict(row)
        if value['terminal_status'] is not None:
            value['terminal_status']=AttemptStatus(value['terminal_status'])
        if adaptive_result_is_infrastructure(WorkerRunResult(**value)):
            raise ValueError('COLLECTION_WORKER_INFRA_FAILURE')


class ContainerWorkerRunner:
    def __init__(self,*,context,parallel_runtime,scene_manifest,case_inputs):
        if (type(context) is not AdmittedCampaignContext or context.workload_kind!='act_collection_start'
                or type(case_inputs) is not dict or not case_inputs):
            raise ValueError('COLLECTION_WORKER_RUNNER_INVALID')
        validate_file_ref(parallel_runtime)
        scenes=scene_ids(scene_manifest)
        if set(case_inputs)!=set(scenes):
            raise ValueError('COLLECTION_CASE_INPUTS_INVALID')
        for refs in case_inputs.values():
            if type(refs) is not dict or set(refs)!={'scope','inputs_manifest'}:
                raise ValueError('COLLECTION_CASE_INPUTS_INVALID')
            for ref in refs.values():validate_file_ref(ref)
        self.context=context
        self.campaign_config=dict(path=context.campaign_config_path,sha256=context.campaign_config_sha256)
        self.config=load_campaign_config(context.campaign_config_path,
            expected_sha256=context.campaign_config_sha256)
        if (self.config['gpu_uuid']!=context.physical_gpu_uuid
                or self.config['controlled_runtime']['sha256']!=context.runtime_config_sha256):
            raise ValueError('COLLECTION_WORKER_CONTEXT_MISMATCH')
        self.parallel_runtime=copy.deepcopy(parallel_runtime)
        self.scene_manifest=copy.deepcopy(scene_manifest)
        self.case_inputs=copy.deepcopy(case_inputs)
        self._claimed=set()
        self.transports={}

    async def __call__(self,*,coordinator,journal,shard,endpoints,config,dispatch_allowed):
        if (type(coordinator) is not BatchCoordinator or coordinator.journal is not journal
                or type(shard) is not ContainerShardOwner or shard.context!=self.context
                or shard.spec['workload_kind']!='act_collection'
                or type(endpoints) is not dict or set(endpoints)!={'head','teacher'}
                or any(type(endpoint) is not ServiceEndpoint or endpoint.role!=role
                       for role,endpoint in endpoints.items())):
            raise ValueError('COLLECTION_WORKER_DISPATCH_INVALID')
        launch=shard.launch
        if launch.launch_id in self._claimed:
            raise ValueError('COLLECTION_WORKER_ALREADY_DISPATCHED')
        if not dispatch_allowed():
            raise ValueError('COLLECTION_WORKER_DISPATCH_FENCED')
        if (load_campaign_config(self.context.campaign_config_path,
                expected_sha256=self.context.campaign_config_sha256)!=self.config
                or shard.image!=self.config['shard_image']
                or any(endpoint.max_frame_bytes!=self.config[role+'_service']['max_frame_bytes']
                       for role,endpoint in endpoints.items())):
            raise ValueError('COLLECTION_WORKER_CONTEXT_MISMATCH')
        identity={name:getattr(self.context,name) for name in BUSINESS_FIELDS}
        if shard.spec['business_identity']!=identity:
            raise ValueError('COLLECTION_WORKER_CONTEXT_MISMATCH')
        await shard.check_health()
        validate_file_ref(self.parallel_runtime)
        scene_path=validate_file_ref(self.scene_manifest)
        rows=read_document(scene_path)['scenarios']
        catalog={row['scene_id']:row for row in rows}
        validate_file_ref(self.scene_manifest)
        selected=tuple(coordinator.request.selected_point_ids)
        if not set(selected).issubset(catalog):
            raise ValueError('COLLECTION_WORKER_SCENES_INVALID')
        cases={scene:copy.deepcopy(self.case_inputs[scene]) for scene in selected}
        for refs in cases.values():
            for ref in refs.values():validate_file_ref(ref)
        # Claim before any token/socket/file effect. An interrupted or rejected
        # exchange is retained as an original failed dispatch, never replayed.
        self._claimed.add(launch.launch_id)
        control=shard.root/'control'
        transport=CollectionCoordinatorTransport(coordinator=coordinator,worker_id=launch.worker_id,
            generation=launch.launch_generation,control_root=control,config=config)
        self.transports[launch.launch_id]=transport
        try:
            transport.start()
            document=dict(schema_version=1,kind='ACT_CONTAINER_COLLECTION_WORKER',
                batch_id=coordinator.request.batch_id,coordinator_epoch=journal.coordinator_epoch,
                worker_id=launch.worker_id,launch_generation=launch.launch_generation,
                execution_generation=self.context.execution_generation,wave_id=launch.wave_id,
                session_id=launch.session_id,owned_root=str(shard.root),ros_namespace=launch.ros_namespace,
                ros_domain_id=launch.ros_domain_id,business_identity=identity,
                deadline_monotonic_s=self.context.deadline_monotonic_s,
                parallel_runtime=self.parallel_runtime,scene_manifest=self.scene_manifest,
                campaign_config=self.campaign_config,
                case_inputs=cases,catalog={scene:catalog[scene] for scene in selected},
                coordinator=dict(socket_path=str(transport.socket_path),token_path=str(transport.token_path)))
            for role,endpoint in endpoints.items():
                document[role]=dict(role=role,socket_path='/act/ipc/'+role+'/inference.sock',
                    service_generation=endpoint.service_generation,max_frame_bytes=endpoint.max_frame_bytes)
            spec_path=control/'worker-spec.json'
            _write(spec_path,document)
            deadline_ns=int(self.context.deadline_monotonic_s*1e9)
            packet=IpcRequest(version=1,operation='act_collection_start',
                command_id='collection-'+launch.launch_id,deadline_ns=deadline_ns,
                service_epoch=self.context.service_epoch,runtime_id=shard.spec['runtime_id'],
                service_token=shard.token,campaign_id=self.context.campaign_id,worker_id=launch.worker_id,
                session_id=launch.session_id,attempt_id=launch.wave_id,
                execution_generation=self.context.execution_generation,
                token=dict(operation_id=self.context.operation_id,child_id=launch.worker_id,
                    runtime_id=shard.spec['runtime_id'],execution_generation=self.context.execution_generation,
                    deadline_ns=deadline_ns,revocation_revision=0),
                payload=identity|dict(launch_generation=launch.launch_generation,
                    worker_spec=dict(path=str(spec_path),sha256=hashlib.sha256(spec_path.read_bytes()).hexdigest())))
            if not dispatch_allowed():
                raise ValueError('COLLECTION_WORKER_DISPATCH_FENCED')
            reply=await shard.control_client().call(packet)
            _write(control/'worker-run-reply.json',reply.model_dump(mode='json'))
            expected=dict(operation_id=self.context.operation_id,campaign_id=self.context.campaign_id,
                worker_id=launch.worker_id,execution_generation=self.context.execution_generation)
            if (not reply.accepted or reply.code!='OK' or type(reply.result) is not dict
                    or set(reply.result)!=set(expected)|{'body'}
                    or any(type(reply.result[name]) is not type(value) or reply.result[name]!=value
                           for name,value in expected.items())):
                raise ValueError('COLLECTION_WORKER_REPLY_REJECTED')
            body=reply.result['body']
            if (type(body) is not dict or set(body)!={'worker_id','launch_generation','results'}
                    or body['worker_id']!=launch.worker_id or type(body['launch_generation']) is not int
                    or body['launch_generation']!=launch.launch_generation or type(body['results']) is not list):
                raise ValueError('COLLECTION_WORKER_REPLY_REJECTED')
            _verify_worker_outcomes(body['results'])
            return body
        except BaseException as error:
            _write(control/'worker-run-failure.json',dict(type=type(error).__name__,reason=str(error)))
            raise
        finally:
            close=asyncio.create_task(asyncio.to_thread(transport.close))
            try:await asyncio.shield(close)
            except asyncio.CancelledError:
                await close
                raise
