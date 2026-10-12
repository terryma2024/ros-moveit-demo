"""One collection Worker run in one native shard, with single-flight owned retirement."""

import asyncio
from pathlib import Path

from so101_demo.act.parallel_collection_contracts import read_document
from so101_demo.runtime.inference.config import validate_file_ref
from so101_demo.cli.mujoco_batch.common import _jsonable


class CollectionShardDriver:
    def __init__(self,*,spec,stack,retirement,worker_builder):
        if (spec.get('workload_kind')!='act_collection' or type(spec.get('business_identity')) is not dict
                or set(spec['business_identity'])!={'manifest_sha256','runtime_config_sha256',
                    'collection_config_sha256','contact_policy_fingerprint'} or not callable(worker_builder)):
            raise ValueError('COLLECTION_SHARD_DRIVER_INVALID')
        self.spec,self.stack,self.retirement,self.worker_builder=spec,stack,retirement,worker_builder
        self.start_task=self._build_task=self._run_task=self._stop_task=None
        self.worker=self.runtime=None
        self._run_claimed=self._closing=False
        self.cleanup_errors=[]

    async def act_collection_start(self,request):
        if self._run_claimed or self._closing:
            raise ValueError('COLLECTION_SHARD_ALREADY_RUN')
        payload=request.payload
        if (request.session_id!=self.spec['simulation_session_id']
                or payload['launch_generation']!=self.spec['launch_generation']
                or any(payload[name]!=value for name,value in self.spec['business_identity'].items())):
            raise ValueError('COLLECTION_SHARD_CONTEXT_MISMATCH')
        expected=Path(self.spec['owned_root'])/'control/worker-spec.json'
        if payload['worker_spec']['path']!=str(expected):
            raise ValueError('COLLECTION_WORKER_SPEC_OUTSIDE_INSTANCE')
        path=validate_file_ref(payload['worker_spec'])
        document=read_document(path)
        validate_file_ref(payload['worker_spec'])
        self._run_claimed=True
        self._run_task=asyncio.create_task(self._run(document))
        return await asyncio.shield(self._run_task)

    async def _run(self,document):
        if self.start_task is None:
            raise ValueError('COLLECTION_NATIVE_START_NOT_BOUND')
        await asyncio.shield(self.start_task)
        if self._closing:
            raise ValueError('COLLECTION_SHARD_FENCED')
        self._build_task=asyncio.create_task(asyncio.to_thread(self.worker_builder,document,
            stack=self.stack,shard_spec=self.spec))
        self.worker,self.runtime=await asyncio.shield(self._build_task)
        if self._closing:
            raise ValueError('COLLECTION_SHARD_FENCED')
        results=await asyncio.to_thread(self.worker.run)
        return dict(worker_id=self.spec['worker_id'],launch_generation=self.spec['launch_generation'],
                    results=_jsonable(results))

    async def act_collection_resume(self,request):
        raise ValueError('ACT_CONTAINER_RESUME_FORBIDDEN')

    async def cancel_act(self,request):
        return dict(stopped_confirmed=await self.stop_act('collection-cancel'))

    async def submit(self,*args):
        raise ValueError('COLLECTION_SHARD_GENERIC_MOTION_REFUSED')

    async def cancel(self,*args):
        raise ValueError('COLLECTION_SHARD_GENERIC_MOTION_REFUSED')

    async def terminal(self,*args):
        raise ValueError('COLLECTION_SHARD_GENERIC_MOTION_REFUSED')

    async def stop_act(self,reason):
        self._closing=True
        if self._stop_task is None:
            self._stop_task=asyncio.create_task(self._stop())
        return await asyncio.shield(self._stop_task)

    async def _stop(self):
        helpers_stopped=True
        if self.start_task is not None:
            try:await asyncio.shield(self.start_task)
            except Exception:pass
        if self._build_task is not None:
            try:self.worker,self.runtime=await asyncio.shield(self._build_task)
            except Exception as error:
                helpers_stopped=False
                self._cleanup_error('worker-build',error)
        if self.worker is not None:
            try:await asyncio.to_thread(self.worker.request_stop)
            except Exception as error:
                helpers_stopped=False
                self._cleanup_error('worker-stop',error)
        if self.runtime is not None:
            event=getattr(self.runtime,'_stop_requested',None)
            if event is not None:event.set()
            try:await asyncio.to_thread(self.runtime.shutdown_owned)
            except Exception as error:
                helpers_stopped=False
                self._cleanup_error('helper-stop',error)
        receipt=await self.retirement.retire(fenced=True)
        if self._run_task is not None:
            try:await asyncio.shield(self._run_task)
            except Exception:pass
        return helpers_stopped and all(receipt[name] for name in (
            'goals_stopped','controllers_stopped','ros_children_exited','ros_graph_empty')) and not receipt['forced']

    def _cleanup_error(self,stage,error):
        self.cleanup_errors.append(dict(stage=stage,type=type(error).__name__,reason=str(error)))
