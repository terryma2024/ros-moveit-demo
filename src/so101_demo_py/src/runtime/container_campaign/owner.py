"""Campaign services survive waves; private shards retire before slot reuse.

The unified entry alone admits resources. This owner consumes that context and
the original slot hash, freezes dispatch inputs, and requires independent wave
readback and every original container stop before reporting cleanup complete.
"""

import asyncio
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time

from so101_demo.act.parallel_collection import plan_campaign_waves
from so101_demo.act.parallel_collection_contracts import (
    read_document,scene_ids,validate_run_contract,
)
from so101_demo.runtime.container_campaign.durability import sync_filesystem
from so101_demo.runtime.container_campaign.processing_limits import (
    check_phase_limits,phase1_deadline_s,phase2_deadline_s,retry_invalid_max_rounds,retry_round_plan,
)
from so101_demo.runtime.container_campaign.resource_log import (
    append_resource_log,check_disk_dispatch_guard,read_disk_free_bytes,
)
from so101_demo.runtime.container_campaign.processing_verifier import build_campaign_result,read_journal,retry_candidate
from so101_demo.runtime.container_campaign.result_verifier import build_frozen_index
from so101_demo.runtime.container_campaign.service_owner import ContainerServiceOwner,_write
from so101_demo.runtime.container_campaign.native_owner import NativeInstanceOwner
from so101_demo.runtime.container_campaign.shard_owner import ContainerShardOwner
from so101_demo.runtime.inference.config import load_campaign_config
from so101_teleop.unified.contracts import AdmittedCampaignContext
from so101_teleop.unified.worker_slots import ActWorkerSlot


PHASE1_DEADLINE_REASON='CAMPAIGN_PHASE1_DEADLINE_EXPIRED'


class ContainerCampaignOwner:
    def __init__(self,*,admitted_context,config,root,service_owner,slots,manifest_path,
                 qualification,launcher,coordinator,verifier,monotonic_ns=time.monotonic_ns,
                 approved_disk_floor_bytes=0,disk_reader=read_disk_free_bytes,syncfs=sync_filesystem,processing=None,
                 campaign_total_s=None):
        root=Path(root)
        if (type(admitted_context) is not AdmittedCampaignContext
                or admitted_context.workload_kind!='act_collection_start'
                or type(service_owner) is not ContainerServiceOwner or service_owner.context!=admitted_context
                or service_owner.roles!=('teacher',) or service_owner.registry.records()
                or root.resolve(strict=True)!=root or str(root)!=admitted_context.evidence_root
                or service_owner.paths['run']!=root or type(qualification) is not bool
                or type(slots) is not tuple or len(slots)!=admitted_context.worker_count
                or any(type(slot) is not ActWorkerSlot for slot in slots)
                or not callable(launcher) or not callable(monotonic_ns) or not callable(disk_reader)
                or type(approved_disk_floor_bytes) is not int or approved_disk_floor_bytes<0 or not callable(syncfs)):
            raise ValueError('CAMPAIGN_OWNER_CONFIG_INVALID')
        if (load_campaign_config(admitted_context.campaign_config_path,roles=('teacher',),
                expected_sha256=admitted_context.campaign_config_sha256)!=config or service_owner.config!=config):
            raise ValueError('CAMPAIGN_OWNER_CONFIG_CHANGED')
        for index,slot in enumerate(slots):
            if (slot.campaign_id!=admitted_context.campaign_id
                    or slot.execution_generation!=admitted_context.execution_generation
                    or slot.worker_id!=f'w{index:02d}'):
                raise ValueError('CAMPAIGN_OWNER_SLOT_MISMATCH')
        serialized=json.dumps([asdict(slot) for slot in slots],sort_keys=True,separators=(',',':')).encode()
        if hashlib.sha256(serialized).hexdigest()!=admitted_context.domain_session_map_sha256:
            raise ValueError('CAMPAIGN_OWNER_SLOT_MISMATCH')
        self.context,self.config,self.root=admitted_context,config,root
        self.services,self.registry,self.slots=service_owner,service_owner.registry,slots
        self.manifest_path=Path(manifest_path)
        self.qualification,self.launcher,self.coordinator,self.verifier=qualification,launcher,coordinator,verifier
        self.clock,self.approved_disk_floor_bytes,self.disk_reader=monotonic_ns,approved_disk_floor_bytes,disk_reader
        self.syncfs=syncfs
        #: the phase-2 scheduler (`ProcessingScheduler`) or None: without one a campaign ends after phase 1, as before
        self.processing=processing
        #: the effective campaign total as admitted (config or runtime yaml); None records the admitted deadline span instead
        self.campaign_total_s=campaign_total_s
        self.phase1_deadline_s=None
        self.phase2=None
        self.dispatch_stopped=False
        self.stop_reason=None
        self.shards=[]
        self._started=self._closing=False
        self._run_done=asyncio.Event()
        self._run_task=self._close_task=None
        self._recording=False
        self._wave_wall_s=[]
        self._sync_s=None
        self._next_wave_index=0

    def stop_dispatch(self,reason):
        if type(reason) is not str or not reason:
            raise ValueError('CAMPAIGN_STOP_REASON_INVALID')
        if not self.dispatch_stopped or self.stop_reason==PHASE1_DEADLINE_REASON:
            self.dispatch_stopped=True
            self.stop_reason=reason
            self.coordinator.stop_dispatch(reason)

    def dispatch_allowed(self):
        """Phase-1 dispatch gate: open until the earlier of the phase-1 deadline and the total deadline."""
        limit=self.context.deadline_monotonic_s
        if self.phase1_deadline_s is not None:
            limit=min(limit,self.phase1_deadline_s)
        return not self.dispatch_stopped and not self._closing and self.clock()<int(limit*1e9)

    def _phase1_limit_reached(self):
        """Phase 1 ended on its own deadline (not on the total, not on a fault): the campaign goes on to phase 2."""
        if self.stop_reason==PHASE1_DEADLINE_REASON:
            return True
        if self.dispatch_stopped or self._closing or self.phase1_deadline_s is None:
            return False
        now=self.clock()
        return self.phase1_deadline_s<self.context.deadline_monotonic_s and int(self.phase1_deadline_s*1e9)<=now<int(
            self.context.deadline_monotonic_s*1e9)

    def _disk_guard(self):
        free=self.disk_reader(self.root)
        append_resource_log(self.root/'host/resources.jsonl',monotonic_ns=self.clock(),
                            observed={'disk_free_bytes':free},missing={})
        if not check_disk_dispatch_guard(free,approved_floor_bytes=self.approved_disk_floor_bytes):
            self.stop_dispatch('CAMPAIGN_DISK_FLOOR_REACHED')
            raise ValueError('CAMPAIGN_DISK_FLOOR_REACHED')

    async def _monitor(self):
        """Disk and service health, once a second, until the run ends: through phase 2 and the readback too. The phase-1 deadline
        only closes dispatch; it does not end the observation."""
        try:
            while not self._closing and not self._run_done.is_set():
                if self.clock()>=int(self.context.deadline_monotonic_s*1e9):
                    self.stop_dispatch('CAMPAIGN_DEADLINE_EXPIRED')
                elif self._recording and not self.dispatch_allowed() and not self.dispatch_stopped:
                    self.stop_dispatch(PHASE1_DEADLINE_REASON if self._phase1_limit_reached() else 'CAMPAIGN_DEADLINE_EXPIRED')
                self._disk_guard()
                await self.services.check_health()
                await asyncio.sleep(1.)
        except Exception as error:
            self.stop_dispatch('CAMPAIGN_RESOURCE_OR_SERVICE_FAULT')
            _write(self.root/'host/dispatch-fault.json',dict(type=type(error).__name__,reason=str(error)))

    async def run(self,manifest):
        if self._started or self._closing:
            raise ValueError('CAMPAIGN_OWNER_ALREADY_STARTED')
        self._started=True
        self._run_task=asyncio.create_task(self._run(manifest))
        try:
            return await asyncio.shield(self._run_task)
        except BaseException:
            self.stop_dispatch('CAMPAIGN_RUN_INTERRUPTED')
            raise

    async def _run(self,manifest):
        monitor=None
        try:
            retry_max=retry_invalid_max_rounds(self.config)
            if retry_max and self.qualification:
                raise ValueError('CAMPAIGN_RETRY_QUALIFICATION_FORBIDDEN')
            if retry_max and self.processing is None:
                raise ValueError('CAMPAIGN_RETRY_REQUIRES_PROCESSING')
            actual=read_document(self.manifest_path)
            if (hashlib.sha256(self.manifest_path.read_bytes()).hexdigest()!=self.context.manifest_sha256
                    or actual!=manifest):
                raise ValueError('CAMPAIGN_MANIFEST_CHANGED')
            if self.qualification:
                plane,contract=validate_run_contract(actual)
                if contract['worker_count']!=self.context.worker_count:
                    raise ValueError('CAMPAIGN_MANIFEST_INVALID')
                # the gate plane is exactly 40 scenes; a functional contract was already closed to 8 or 16
                ids=scene_ids(contract['scene_manifest'],count=40 if plane=='gate' else None)
            else:
                plane=None
                rows=actual.get('scenarios')
                if type(rows) is not list or not rows or any(type(row) is not dict for row in rows):
                    raise ValueError('CAMPAIGN_MANIFEST_INVALID')
                ids=tuple(row['scene_id'] for row in rows)
            # the coordinator writes its collection mode into every task document: a spot check is a diagnostic-mode run, every other
            # plane a formal one
            expected_mode='preselected_target_diagnostic' if plane=='spot_check' else 'formal'
            if getattr(self.coordinator,'collection_mode','formal')!=expected_mode:
                raise ValueError('CAMPAIGN_COLLECTION_MODE_MISMATCH')
            worker_ids=tuple(slot.worker_id for slot in self.slots)
            # The time limits are checked before anything is launched. The 1 s tolerance covers the nanosecond rounding of the
            # admitted deadline.
            context=self.context
            check_phase_limits(self.config,context.deadline_monotonic_s-context.admitted_at_monotonic_s+1.)
            self.phase1_deadline_s=phase1_deadline_s(self.config,admitted_s=context.admitted_at_monotonic_s,
                total_deadline_s=context.deadline_monotonic_s)
            setter=getattr(self.coordinator,'set_phase1_deadline',None)
            if callable(setter):
                setter(self.phase1_deadline_s)
            plans=plan_campaign_waves(ids,worker_ids,plane=plane,max_wave_size=20)
            total=self.campaign_total_s
            if total is None:
                total=round(context.deadline_monotonic_s-context.admitted_at_monotonic_s,3)
            append_resource_log(self.root/'host/resources.jsonl',monotonic_ns=self.clock(),
                observed={'campaign_total_s':total,
                          'campaign_total_source':'campaign config' if 'batch_hard_timeout_s' in self.config else 'runtime yaml'},
                missing={})
            self._disk_guard()
            _write(self.root/'campaign-index.json',dict(schema_version=1,kind='act_collection_campaign_index',
                qualification=self.qualification,scene_count=len(ids),waves=plans))
            endpoints=await self.services.start()
            monitor=asyncio.create_task(self._monitor())
            completed=await self._record_waves(plans,endpoints)
            recorded={row['scene_id'] for wave in completed for row in wave['case_results']}
            # Only the phase-1 deadline can leave a scene unrecorded: every other path either verified a whole wave (the verifier
            # holds the denominator) or raised.
            missing=([scene for scene in ids if scene not in recorded]
                     if self.stop_reason==PHASE1_DEADLINE_REASON or self._phase1_limit_reached() else [])
            if missing:
                # Unrecorded scenes are missing evidence: this run can no longer be a complete (or qualified) collection.
                _write(self.root/'host/phase1-limit.json',dict(schema_version=1,kind='act_collection_phase1_limit',
                    campaign_id=self.context.campaign_id,stop_reason=self.stop_reason or PHASE1_DEADLINE_REASON,
                    phase1_deadline_s=self.phase1_deadline_s,recorded_scenes=len(recorded),missing_scenes=missing))
            await self._finish_phase1(ids,completed)
            phase2=await self.start_phase_two(completed)
            result=dict(campaign_id=self.context.campaign_id,scene_count=len(ids),waves=completed)
            task_faults=[item for wave in completed for item in wave.get('faults',())]
            if task_faults:
                # A task fault is isolated to its scene: the run goes on and holds complete results, and the CLI exits non-zero.
                result['task_faults']=[dict(scene_id=item['scene_id'],reason=item['reason']) for item in task_faults]
            if phase2 is not None:
                result['phase2']=phase2
            if missing:
                result['missing_evidence']=missing
            combine=getattr(self.verifier,'verify_processing',None)
            if missing or any(row['proof'].get('processing')=='PENDING' for wave in completed for row in wave['case_results']):
                # The Teacher half is proven (and not every scene was recorded): this is the phase-1 record.
                result['processing']='PENDING'
                _write(self.root/'host/phase1-result.json',result)
                if self.processing is None or not callable(combine):
                    return result
            if self.processing is not None and callable(combine):
                # Both phases are over: the campaign result and the frozen index come from the combined per-scene proof (the
                # Teacher half of phase 1, the data half of phase 2, every attempt; scenes without evidence are explicit entries).
                if retry_max:
                    combined,retry,rounds=await self._retry_rounds(ids,worker_ids,completed,endpoints,retry_max)
                    combined['retry']=retry
                    result['retry']=retry
                    result['waves']=[wave for recording in rounds for wave in recording['waves']]
                    result.pop('task_faults',None)
                else:
                    combined=await asyncio.to_thread(combine,completed,list(ids))
                # A scene that ended FAULT or MISSING in either phase is a fault of the run, so the CLI exits non-zero.
                known={item['scene_id'] for item in result.get('task_faults',())}
                unfinished=[dict(scene_id=item['scene_id'],reason=item.get('reason') or item['state'])
                            for item in combined['scenes'] if item['state'] in ('FAULT','MISSING') and item['scene_id'] not in known]
                if unfinished:
                    result['task_faults']=[*result.get('task_faults',()),*unfinished]
                _write(self.root/'host/campaign-result.json',build_campaign_result(self.context.campaign_id,len(ids),combined))
                _write(self.root/'collection-index.json',build_frozen_index(campaign_id=self.context.campaign_id,
                    qualification=self.qualification,scene_count=len(ids),combined=combined))
                result['processing']='COMPLETE'
                return result
            _write(self.root/'host/campaign-result.json',result)
            _write(self.root/'collection-index.json',build_frozen_index(campaign_id=self.context.campaign_id,
                qualification=self.qualification,scene_count=len(ids),waves=completed))
            return result
        finally:
            if monitor is not None:
                monitor.cancel()
                await asyncio.gather(monitor,return_exceptions=True)
            self._run_done.set()

    async def _record_waves(self,plans,endpoints):
        self._recorded_waves=[]
        self._recording=True
        try:
            for plan in plans:
                if self._phase1_limit_reached():
                    break
                if not self.dispatch_allowed():
                    raise ValueError(self.stop_reason or 'CAMPAIGN_DISPATCH_FENCED')
                started=self.clock()/1e9
                self._disk_guard()
                await self.services.check_health()
                prepared=self.launcher(plan=plan,endpoints=endpoints,slots=self.slots)
                self._next_wave_index=getattr(self.launcher,'_next_wave',plan['wave_index']+1)
                if (type(prepared) is not tuple or len(prepared)!=len(self.slots)
                        or any(type(shard) not in (ContainerShardOwner,NativeInstanceOwner) for shard in prepared)):
                    raise ValueError('CAMPAIGN_SHARD_PREPARATION_INVALID')
                for shard,slot in zip(prepared,self.slots,strict=True):
                    if (shard.context!=self.context or shard.registry is not self.registry
                            or shard.launch.worker_id!=slot.worker_id
                            or shard.launch.wave_id!='wave-'+str(plan['wave_index'])):
                        raise ValueError('CAMPAIGN_SHARD_SLOT_MISMATCH')
                self.shards.extend(prepared)
                if not self.dispatch_allowed():
                    if self._phase1_limit_reached():
                        await asyncio.gather(*(shard.close() for shard in prepared))
                        break
                    raise ValueError(self.stop_reason or 'CAMPAIGN_DISPATCH_FENCED')
                outcome=await self.coordinator.run_wave(plan=plan,shards=prepared,endpoints=endpoints,
                    dispatch_allowed=self.dispatch_allowed)
                cleanup=await asyncio.gather(*(shard.close() for shard in prepared))
                if any(value['terminated'] is not True for value in cleanup):
                    self.stop_dispatch('CAMPAIGN_SHARD_STOP_UNCONFIRMED')
                    raise ValueError('CAMPAIGN_SHARD_STOP_UNCONFIRMED')
                self.coordinator.complete_wave_cleanup(plan,prepared)
                collected={row['scene_id'] for row in outcome['case_results']}
                if len(collected)<len(plan['scene_ids']) and self._phase1_limit_reached() and not outcome['infra_errors']:
                    faulted={item['scene_id'] for item in outcome.get('scene_faults',())}
                    kept=dict(plan,scene_ids=[scene for scene in plan['scene_ids'] if scene in collected or scene in faulted],
                              assignment=None)
                    if not kept['scene_ids']:
                        break
                    verified=await asyncio.to_thread(self.verifier.verify_wave,kept,outcome,prepared,partial=True)
                else:
                    verified=await asyncio.to_thread(self.verifier.verify_wave,plan,outcome,prepared)
                _write(self.root/'host'/('wave-'+str(plan['wave_index'])+'-verified.json'),verified)
                self._recorded_waves.append(verified)
                self._wave_wall_s.append(self.clock()/1e9-started)
            return self._recorded_waves
        finally:
            self._recording=False

    def _reopen_recording(self,deadline):
        coordinator_reason=getattr(self.coordinator,'stop_reason',None)
        if (self.stop_reason not in (None,PHASE1_DEADLINE_REASON) or self._closing
                or coordinator_reason not in (None,PHASE1_DEADLINE_REASON)):
            raise ValueError('CAMPAIGN_RETRY_DISPATCH_FENCED')
        if self.stop_reason==PHASE1_DEADLINE_REASON or coordinator_reason==PHASE1_DEADLINE_REASON:
            self.coordinator.reopen_dispatch(PHASE1_DEADLINE_REASON)
        self.stop_reason=None
        self.dispatch_stopped=False
        self.phase1_deadline_s=deadline
        setter=getattr(self.coordinator,'set_phase1_deadline',None)
        if callable(setter):
            setter(deadline)

    def _retry_observations(self):
        events=read_journal(self.root/'host/processing-journal.jsonl') or []
        starts,task_times,start_times={},[],[]
        phase_start=None
        for event in events:
            instant=event['monotonic_s']
            if event['event']=='phase2_start':
                phase_start=instant
            elif event['event']=='processor_started' and phase_start is not None:
                start_times.append(instant-phase_start)
            elif event['event']=='dispatch':
                starts[event['task_id']]=instant
            elif event['event']=='result' and event['task_id'] in starts:
                task_times.append(instant-starts[event['task_id']])
        return dict(wave_wall_s=list(self._wave_wall_s),sync_s=self._sync_s,task_s=task_times,processor_start_s=start_times)

    async def _retry_rounds(self,ids,worker_ids,completed,endpoints,maximum):
        rounds=[dict(recording_round=0,scene_ids=list(ids),waves=completed)]
        combine=self.verifier.verify_rounds
        combined=await asyncio.to_thread(combine,rounds,list(ids))
        initially_invalid={item['scene_id'] for item in combined['scenes'] if retry_candidate(item)}
        observed=self._retry_observations()
        decisions=[]
        aborted=None
        for number in range(1,maximum+1):
            candidates=[item['scene_id'] for item in combined['scenes'] if retry_candidate(item['recording_attempts'][-1])]
            plans=plan_campaign_waves(candidates,worker_ids,plane=None,first_wave_index=self._next_wave_index,
                                      recording_round=number) if candidates else []
            reason=None
            estimate=None
            stop_reason=self.stop_reason or getattr(self.coordinator,'stop_reason',None)
            if not candidates:
                reason='NO_CANDIDATES'
            elif stop_reason not in (None,PHASE1_DEADLINE_REASON):
                reason='DISPATCH_STOPPED:'+stop_reason
            else:
                runtime=self.coordinator.config
                runtime={name:getattr(runtime,name) for name in ('initializing_hard_timeout_s','executing_hard_timeout_s',
                          'finalizing_hard_timeout_s','worker_recovery_timeout_s')}
                admitted=getattr(self.processing,'_admitted',None)
                processors=len(admitted) if admitted else self.phase2['processors']
                estimate=retry_round_plan(self.config,now_s=self.clock()/1e9,total_deadline_s=self.context.deadline_monotonic_s,
                    scene_count=len(candidates),worker_count=len(worker_ids),processor_count=processors,observed=observed,runtime=runtime)
                if not estimate['fits']:
                    reason=estimate['reason']
                largest=max((item['phase1'].get('recording_bytes',0) for item in combined['scenes'] if item['phase1']),default=0)
                if reason is None and self.disk_reader(self.root)<self.approved_disk_floor_bytes+len(candidates)*largest:
                    reason='RETRY_ROUND_DISK'
            decision=dict(recording_round=number,candidates=candidates,plans=plans,estimate=estimate,
                          status='RUN' if reason is None else 'SKIPPED',reason=reason)
            _write(self.root/'host'/f'retry-round-{number}.json',decision)
            decisions.append(decision)
            if reason is not None:
                break
            recording=dict(recording_round=number,scene_ids=candidates,waves=[])
            rounds.append(recording)
            self._recorded_waves=[]
            try:
                self._reopen_recording(estimate['recording_deadline_s'])
                recording['waves']=await self._record_waves(plans,endpoints)
                await self._finish_phase1(candidates,recording['waves'],round=number)
                await self.start_phase_two(recording['waves'],round=number)
            except Exception as error:
                cleanup=await asyncio.gather(*(shard.close() for shard in self.shards),return_exceptions=True)
                if (any(not isinstance(value,dict) or value.get('terminated') is not True for value in cleanup)
                        or 'STOP_UNCONFIRMED' in str(error) or 'STOP_UNPROVEN' in str(error)
                        or await asyncio.to_thread(self.registry.role_terminated,'shard',self.services.inspect_container) is not True):
                    raise ValueError('CAMPAIGN_RETRY_STOP_UNCONFIRMED') from error
                recording['waves']=getattr(self,'_recorded_waves',[])
                aborted=str(error)
            combined=await asyncio.to_thread(combine,rounds,list(ids))
            if aborted is not None:
                break
        recovered=sum(item['scene_id'] in initially_invalid and item['verdict']['export_eligible'] is True
                      for item in combined['scenes'])
        retry=dict(max_rounds=maximum,rounds_run=len(rounds)-1,recovered=recovered,
                   status='ABORTED' if aborted is not None else 'COMPLETE',reason=aborted,decisions=decisions)
        return combined,retry,rounds

    async def _finish_phase1(self,ids,completed,*,round=0):
        """After the last phase-1 wave is verified: prove every shard stopped, then make the run root durable with one syncfs.

        Phase 1 writes the raw bags without fsync; nothing that reads them (phase 2) may start before this record exists."""
        proven=await asyncio.to_thread(self.registry.role_terminated,'shard',self.services.inspect_container)
        if proven is not True:
            self.stop_dispatch('CAMPAIGN_PHASE1_STOP_UNPROVEN')
            raise ValueError('CAMPAIGN_PHASE1_STOP_UNPROVEN')
        host=self.root/'host' if round==0 else self.root/'host'/f'retry-{round}'
        if round:
            host.mkdir(mode=0o700,exist_ok=True)
        started=self.clock()/1e9
        try:
            synced=await asyncio.to_thread(self.syncfs,self.root)
        except Exception as error:
            self.stop_dispatch('CAMPAIGN_PHASE1_SYNC_FAILED')
            _write(host/'phase1-sync-fault.json',dict(type=type(error).__name__,reason=str(error)))
            raise ValueError('CAMPAIGN_PHASE1_SYNC_FAILED') from error
        if round==0:
            self._sync_s=self.clock()/1e9-started
        _write(host/'phase1-durability.json',dict(schema_version=1,kind='act_collection_phase1_durability',
            campaign_id=self.context.campaign_id,scene_count=len(ids),waves=len(completed),shards_proven_stopped=True,
            **synced))

    async def start_phase_two(self,waves,*,round=0):
        """Phase 2: every scene whose phase-1 record is PENDING_QC goes to the processor scheduler.

        Scenes whose data verdict is already final (a Teacher failure that recorded nothing, such as the pre-motion unreachable
        form) are not queued. Returns the scheduler's summary, or None when there is nothing to process or no scheduler."""
        if self.processing is None:
            return None
        rows=[row for wave in waves for row in wave['case_results'] if row['proof'].get('processing')=='PENDING']
        if not rows:
            return None
        started=self.clock()/1e9
        deadline=phase2_deadline_s(self.config,phase2_start_s=started,total_deadline_s=self.context.deadline_monotonic_s)
        host=self.root/'host' if round==0 else self.root/'host'/f'retry-{round}'
        options={} if round==0 else dict(round=round,host_dir=host)
        summary=await self.processing.run(rows,deadline_s=deadline,**options)
        _write(host/'processing-result.json',summary)
        if summary.get('processors_stopped') is not True:
            self.stop_dispatch('CAMPAIGN_PROCESSORS_STOP_UNCONFIRMED')
            raise ValueError('CAMPAIGN_PROCESSORS_STOP_UNCONFIRMED')
        self.phase2=summary
        return summary

    async def close(self):
        self._closing=True
        self.stop_dispatch('CAMPAIGN_CLOSING')
        if self._close_task is None:
            self._close_task=asyncio.create_task(self._close())
        return await asyncio.shield(self._close_task)

    async def _close(self):
        if self._run_task is not None:
            await self._run_done.wait()
        shards=await asyncio.gather(*(shard.close() for shard in self.shards),return_exceptions=True)
        if callable(getattr(self.coordinator,'close',None)):
            self.coordinator.close()
        processors=await asyncio.gather(*(owner.close() for owner in getattr(self.processing,'owners',())),
                                        return_exceptions=True)
        services=await self.services.close()
        independently_clear=await asyncio.to_thread(self.registry.all_terminated,self.services.inspect_container)
        clear=independently_clear and services['terminated'] is True and all(
            type(value) is dict and value.get('terminated') is True for value in (*shards,*processors))
        result=dict(terminated=clear,services=services,
            shards=[value if type(value) is dict else dict(error_type=type(value).__name__,reason=str(value))
                    for value in shards],stop_reason=self.stop_reason)
        if processors:
            result['processors']=[value if type(value) is dict else dict(error_type=type(value).__name__,reason=str(value))
                                  for value in processors]
        _write(self.root/'host/campaign-cleanup.json',result)
        return result
