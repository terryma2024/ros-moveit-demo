"""Concurrent container waves reuse the existing durable lease/commit engine."""

import asyncio
from dataclasses import replace
import time

from so101_demo.act.parallel_collection import reserve_qualification_scenes
from so101_demo.act.result_store import ActCollectionResultVerifier
from so101_demo.parallel_batch.contracts.common import RunMode
from so101_demo.parallel_batch.contracts.linux_cuda import BatchKind,BatchRequest,ParallelRuntimeConfigLinuxCuda
from so101_demo.parallel_batch.coordinator import BatchCoordinator
from so101_demo.parallel_batch.journal import CoordinatorJournal
from so101_demo.runtime.inference.config import validate_file_ref
from so101_demo.runtime.parallel_ipc.frames import canonical_json
from so101_teleop.unified.contracts import AdmittedCampaignContext


class QualificationPointSelector:
    def __init__(self,*,scene_ids,worker_ids):
        self.assignment=reserve_qualification_scenes(scene_ids,worker_ids)
        self.coordinator=None

    def bind(self,coordinator):
        if self.coordinator is not None or type(coordinator) is not BatchCoordinator:
            raise ValueError('QUALIFICATION_COORDINATOR_BINDING_INVALID')
        self.coordinator=coordinator

    def choose(self,worker_id,eligible):
        if self.coordinator is None or worker_id not in self.assignment['reserved_by_worker']:
            raise ValueError('QUALIFICATION_COORDINATOR_BINDING_INVALID')
        points=self.coordinator.snapshot().points
        for scene in self.assignment['reserved_by_worker'][worker_id]:
            if not points[scene].terminal:
                return scene if scene in eligible else None
        return next((scene for scene in self.assignment['surplus'] if scene in eligible),None)


class ContainerCaseResultVerifier(ActCollectionResultVerifier):
    """Route each lease to its own original scope/input bindings, without mutation races."""
    def __init__(self,worker_roots,*,case_inputs):
        if type(case_inputs) is not dict or not case_inputs:
            raise ValueError('CONTAINER_CASE_INPUTS_INVALID')
        self.readers={}
        self.references={}
        for scene,refs in case_inputs.items():
            if type(refs) is not dict or set(refs)!={'scope','inputs_manifest'}:
                raise ValueError('CONTAINER_CASE_INPUTS_INVALID')
            paths={name:validate_file_ref(ref) for name,ref in refs.items()}
            self.references[scene]={name:dict(ref) for name,ref in refs.items()}
            self.readers[scene]=ActCollectionResultVerifier(worker_roots,scope=paths['scope'],
                inputs_manifest=paths['inputs_manifest'],trust_independent_qc_memo=True)
        first=next(iter(self.readers.values()))
        super().__init__(worker_roots,scope=first.scope,inputs_manifest=first.inputs_manifest)

    def bind_execution_journal(self,journal):
        super().bind_execution_journal(journal)
        for reader in self.readers.values():
            reader.bind_execution_journal(journal)

    def bind_read_only_execution_journal(self,root,batch_id,coordinator_epoch):
        super().bind_read_only_execution_journal(root,batch_id,coordinator_epoch)
        for reader in self.readers.values():
            reader.bind_read_only_execution_journal(root,batch_id,coordinator_epoch)

    def _reader(self,lease):
        for ref in self.references[lease.point_id].values():
            validate_file_ref(ref)
        return self.readers[lease.point_id]

    def verify(self,lease,location,run_mode):
        return self._reader(lease).verify(lease,location,run_mode)

    def discover(self,lease,workspace):
        return self._reader(lease).discover(lease,workspace)


class ConcurrentCollectionCoordinator:
    def __init__(self,*,context,config,case_inputs,run_worker,clock=time.monotonic):
        if (type(context) is not AdmittedCampaignContext or context.workload_kind!='act_collection_start'
                or type(config) is not ParallelRuntimeConfigLinuxCuda or not callable(run_worker)
                or type(case_inputs) is not dict or not case_inputs):
            raise ValueError('CONTAINER_COORDINATOR_CONFIG_INVALID')
        self.context,self.config,self.case_inputs=context,config,case_inputs
        self.run_worker,self.clock=run_worker,clock
        self.active=None
        self.stop_reason=None
        self.waves={}

    def stop_dispatch(self,reason):
        if type(reason) is not str or not reason:
            raise ValueError('CONTAINER_DISPATCH_STOP_REASON_INVALID')
        if self.stop_reason is None:
            self.stop_reason=reason
            if self.active is not None:
                self.active.request_stop(reason=reason)

    async def run_wave(self,*,plan,shards,endpoints,dispatch_allowed):
        if self.stop_reason is not None or self.active is not None or not dispatch_allowed():
            raise ValueError('CONTAINER_WAVE_DISPATCH_FENCED')
        if type(shards) is not tuple or len(shards)!=self.context.worker_count:
            raise ValueError('CONTAINER_WAVE_SHARD_COUNT_INVALID')
        wave=plan['wave_index']
        root=shards[0].root.parents[2]/'host'/('wave-'+str(wave))
        if str(root.parents[1])!=self.context.evidence_root or wave in self.waves:
            raise ValueError('CONTAINER_WAVE_ROOT_INVALID')
        await asyncio.gather(*(shard.check_health() for shard in shards))
        scene_order=tuple(plan['scene_ids'])
        roots={shard.launch.worker_id:shard.root for shard in shards}
        inputs={scene:self.case_inputs[scene] for scene in scene_order}
        verifier=ContainerCaseResultVerifier(roots,case_inputs=inputs)
        remaining=self.context.deadline_monotonic_s-self.clock()
        if remaining<=0:
            raise ValueError('CONTAINER_CAMPAIGN_DEADLINE_EXPIRED')
        config=replace(self.config,batch_hard_timeout_s=min(self.config.batch_hard_timeout_s,remaining))
        request=BatchRequest(self.context.campaign_id+'-wave-'+str(wave),RunMode.EXECUTE,
            scene_order,len(shards),root,BatchKind.FIRST_PASS)
        if (root/'coordinator').exists():
            raise ValueError('CONTAINER_WAVE_NEW_JOURNAL_REQUIRED')
        journal=CoordinatorJournal.create(root/'coordinator',request.batch_id)
        try:
            verifier.bind_execution_journal(journal)
            selector=(QualificationPointSelector(scene_ids=scene_order,worker_ids=tuple(roots))
                      if plan['assignment'] is not None else None)
            if selector is not None and canonical_json(selector.assignment)!=canonical_json(plan['assignment']):
                raise ValueError('CONTAINER_WAVE_ASSIGNMENT_CHANGED')
            coordinator=BatchCoordinator(journal,request,config=config,result_port=verifier,
                clock=self.clock,point_selector=None if selector is None else selector.choose)
            if selector is not None:
                selector.bind(coordinator)
            self.active=coordinator
            self.waves[wave]=(coordinator,journal)
            for shard in shards:
                coordinator.register_worker(shard.launch.worker_id,generation=shard.launch.launch_generation)
            # The real transport runner uses each registered shard and borrows
            # campaign endpoints. It owns neither inference service shutdown.
            runs=await asyncio.gather(*(self.run_worker(coordinator=coordinator,journal=journal,
                shard=shard,endpoints=endpoints,config=config,dispatch_allowed=dispatch_allowed)
                for shard in shards),return_exceptions=True)
            errors=[dict(type=type(value).__name__,reason=str(value)) for value in runs
                    if isinstance(value,BaseException)]
            if errors:
                self.stop_dispatch('CONTAINER_WORKER_INFRA_FAILURE')
            commits=[event for event in journal.replay().events if event.type=='RESULT_COMMITTED']
            rows=[dict(scene_id=event.payload['identity']['point_id'],
                worker_id=event.payload['identity']['worker_id'],location=event.payload['identity']['location'])
                for event in commits]
            return dict(wave_index=wave,coordinator_root=str(root/'coordinator'),
                        case_results=rows,infra_errors=errors)
        except BaseException:
            journal.close()
            raise
        finally:
            self.active=None

    def complete_wave_cleanup(self,plan,shards):
        coordinator,journal=self.waves[plan['wave_index']]
        try:
            if any(shard._close_task is None or not shard._close_task.done()
                   or shard._close_task.result()['terminated'] is not True for shard in shards):
                raise ValueError('CONTAINER_WAVE_CLEANUP_UNCONFIRMED')
            for shard in shards:
                shard.registry.prove_terminated(shard.launch.launch_id,shard.inspect(shard.owner.container_id))
            coordinator.complete_cleanup(owned_processes_stopped=True,controllers_stopped=True)
        finally:
            journal.close()

    def close(self):
        for coordinator,journal in self.waves.values():
            journal.close()
