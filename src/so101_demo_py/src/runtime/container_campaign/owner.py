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
from so101_demo.runtime.container_campaign.resource_log import (
    append_resource_log,check_disk_dispatch_guard,read_disk_free_bytes,
)
from so101_demo.runtime.container_campaign.result_verifier import build_frozen_index
from so101_demo.runtime.container_campaign.service_owner import ContainerServiceOwner,_write
from so101_demo.runtime.container_campaign.native_owner import NativeInstanceOwner
from so101_demo.runtime.container_campaign.shard_owner import ContainerShardOwner
from so101_demo.runtime.inference.config import load_campaign_config
from so101_teleop.unified.contracts import AdmittedCampaignContext
from so101_teleop.unified.worker_slots import ActWorkerSlot


class ContainerCampaignOwner:
    def __init__(self,*,admitted_context,config,root,service_owner,slots,manifest_path,
                 qualification,launcher,coordinator,verifier,monotonic_ns=time.monotonic_ns,
                 approved_disk_floor_bytes=0,disk_reader=read_disk_free_bytes):
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
                or type(approved_disk_floor_bytes) is not int or approved_disk_floor_bytes<0):
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
        self.dispatch_stopped=False
        self.stop_reason=None
        self.shards=[]
        self._started=self._closing=False
        self._run_done=asyncio.Event()
        self._run_task=self._close_task=None

    def stop_dispatch(self,reason):
        if type(reason) is not str or not reason:
            raise ValueError('CAMPAIGN_STOP_REASON_INVALID')
        if not self.dispatch_stopped:
            self.dispatch_stopped=True
            self.stop_reason=reason
            self.coordinator.stop_dispatch(reason)

    def dispatch_allowed(self):
        return not self.dispatch_stopped and not self._closing and self.clock()<int(self.context.deadline_monotonic_s*1e9)

    def _disk_guard(self):
        free=self.disk_reader(self.root)
        append_resource_log(self.root/'host/resources.jsonl',monotonic_ns=self.clock(),
                            observed={'disk_free_bytes':free},missing={})
        if not check_disk_dispatch_guard(free,approved_floor_bytes=self.approved_disk_floor_bytes):
            self.stop_dispatch('CAMPAIGN_DISK_FLOOR_REACHED')
            raise ValueError('CAMPAIGN_DISK_FLOOR_REACHED')

    async def _monitor(self):
        try:
            while self.dispatch_allowed():
                self._disk_guard()
                await self.services.check_health()
                await asyncio.sleep(1.)
            if not self.dispatch_stopped and not self._closing:
                self.stop_dispatch('CAMPAIGN_DEADLINE_EXPIRED')
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
            worker_ids=tuple(slot.worker_id for slot in self.slots)
            plans=plan_campaign_waves(ids,worker_ids,plane=plane,max_wave_size=20)
            self._disk_guard()
            _write(self.root/'campaign-index.json',dict(schema_version=1,kind='act_collection_campaign_index',
                qualification=self.qualification,scene_count=len(ids),waves=plans))
            endpoints=await self.services.start()
            monitor=asyncio.create_task(self._monitor())
            completed=[]
            for plan in plans:
                if not self.dispatch_allowed():
                    raise ValueError(self.stop_reason or 'CAMPAIGN_DISPATCH_FENCED')
                self._disk_guard()
                await self.services.check_health()
                # All commands are prepared before the first shard effect.
                prepared=self.launcher(plan=plan,endpoints=endpoints,slots=self.slots)
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
                    raise ValueError(self.stop_reason or 'CAMPAIGN_DISPATCH_FENCED')
                # The wave coordinator starts every instance and holds the ready barrier.
                outcome=await self.coordinator.run_wave(plan=plan,shards=prepared,endpoints=endpoints,
                    dispatch_allowed=self.dispatch_allowed)
                cleanup=await asyncio.gather(*(shard.close() for shard in prepared))
                if any(value['terminated'] is not True for value in cleanup):
                    self.stop_dispatch('CAMPAIGN_SHARD_STOP_UNCONFIRMED')
                    raise ValueError('CAMPAIGN_SHARD_STOP_UNCONFIRMED')
                self.coordinator.complete_wave_cleanup(plan,prepared)
                verified=await asyncio.to_thread(self.verifier.verify_wave,plan,outcome,prepared)
                _write(self.root/'host'/('wave-'+str(plan['wave_index'])+'-verified.json'),verified)
                completed.append(verified)
            result=dict(campaign_id=self.context.campaign_id,scene_count=len(ids),waves=completed)
            _write(self.root/'host/campaign-result.json',result)
            _write(self.root/'collection-index.json',build_frozen_index(campaign_id=self.context.campaign_id,
                qualification=self.qualification,scene_count=len(ids),waves=completed))
            return result
        finally:
            if monitor is not None:
                monitor.cancel()
                await asyncio.gather(monitor,return_exceptions=True)
            self._run_done.set()

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
        services=await self.services.close()
        independently_clear=await asyncio.to_thread(self.registry.all_terminated,self.services.inspect_container)
        clear=independently_clear and services['terminated'] is True and all(
            type(value) is dict and value.get('terminated') is True for value in shards)
        result=dict(terminated=clear,services=services,
            shards=[value if type(value) is dict else dict(error_type=type(value).__name__,reason=str(value))
                    for value in shards],stop_reason=self.stop_reason)
        _write(self.root/'host/campaign-cleanup.json',result)
        return result
