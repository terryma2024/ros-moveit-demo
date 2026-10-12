"""Private Worker-local lease RPC; campaign admission remains at the unified entry."""

from pathlib import Path
import threading

from so101_demo.cli.mujoco_batch.common import _jsonable,_lease_wire
from so101_demo.cli.mujoco_batch.rpc_proxies import _CoordinatorRpcProxy,_validate_rpc_payload
from so101_demo.parallel_batch.contracts.common import RunMode
from so101_demo.parallel_batch.coordinator import BatchCoordinator
from so101_demo.runtime.parallel_ipc.authority import AuthenticatedUnixServer,WorkerTokenAuthority


_OPERATIONS={'register_worker','grant_lease','record_recovery','heartbeat','heartbeat_teacher',
             'ack_lease','ack_attempt_started','begin_finalizing','commit_result'}


class CollectionCoordinatorProxy(_CoordinatorRpcProxy):
    def __init__(self,*args,**kwargs):
        if kwargs.get('mode') is not RunMode.EXECUTE:
            raise ValueError('COLLECTION_EXECUTE_REQUIRED')
        super().__init__(*args,**kwargs)
        self._sequence_lock=threading.Lock()

    def _call(self,operation,*,lease=None,request_key=None,**values):
        with self._sequence_lock:
            self._sequence+=1
            sequence=self._sequence
        message=dict(schema_version=1,kind='coordinator_call',
            coordinator_epoch=values.pop('coordinator_epoch',None) or (
                lease.coordinator_epoch if lease is not None else self.coordinator_epoch),
            worker_id=self.worker_id,worker_generation=self.generation,lease=_lease_wire(lease),
            request_id=f'rpc-{self.worker_id}-{sequence}',
            idempotency_key=request_key or f'{operation}-{self.worker_id}-{self.generation}-{sequence}',
            token=self.token,payload={'operation':operation,**_jsonable(values)})
        # One exchange only. ACK loss preserves the original durable history
        # and fences this run; it never resends a qualification operation.
        return self.client.call(message)['payload']


class CollectionCoordinatorTransport:
    def __init__(self,*,coordinator,worker_id,generation,control_root,config):
        root=Path(control_root)
        if (type(coordinator) is not BatchCoordinator or coordinator.request.run_mode is not RunMode.EXECUTE
                or root.resolve(strict=True)!=root or not root.is_dir()
                or worker_id not in coordinator.snapshot().workers
                or coordinator.snapshot().workers[worker_id].generation!=generation):
            raise ValueError('COLLECTION_RPC_BINDING_INVALID')
        self.coordinator,self.worker_id,self.generation=coordinator,worker_id,generation
        self.authority=WorkerTokenAuthority(root,coordinator_epoch=coordinator.journal.coordinator_epoch,
                                           ipc_root=root)
        self.token_path=self.authority.issue(worker_id,generation)
        self.socket_path=root/'coordinator.sock'
        self.server=AuthenticatedUnixServer(self.socket_path,self.authority,self._handle,
            deadline_s=config.heartbeat_timeout_s,max_frame_bytes=config.broker_max_frame_bytes,
            max_concurrent_connections=4)
        self._thread=None
        self._closed=False

    def _handle(self,message):
        payload=message['payload']
        operation=payload.get('operation')
        if operation not in _OPERATIONS:
            raise ValueError('COLLECTION_RPC_OPERATION_REFUSED')
        _validate_rpc_payload(payload)
        if (message['worker_id']!=self.worker_id or message['worker_generation']!=self.generation
                or message['coordinator_epoch']!=self.coordinator.journal.coordinator_epoch):
            raise ValueError('COLLECTION_RPC_WORKER_MISMATCH')
        if operation in {'register_worker','grant_lease','record_recovery'}:
            if payload['generation']!=self.generation:
                raise ValueError('COLLECTION_RPC_GENERATION_CHANGE_REFUSED')
        c=self.coordinator
        if operation=='register_worker':
            result=c.register_worker(self.worker_id,generation=self.generation,
                recovery_deadline_monotonic_s=payload['recovery_deadline_monotonic_s'])
        elif operation=='grant_lease':
            result=c.grant_lease_outcome(self.worker_id,generation=self.generation,
                                       request_key=message['idempotency_key'])
            if result['lease'] is not None:
                self.authority.bind_lease(self.worker_id,self.generation,_lease_wire(result['lease']))
        elif operation=='record_recovery':
            result=c.record_recovery(self.worker_id,**{name:value for name,value in payload.items()
                                                      if name!='operation'})
        else:
            worker=c.snapshot().workers[self.worker_id]
            if worker.lease is None or _lease_wire(worker.lease)!=message['lease']:
                raise ValueError('COLLECTION_RPC_ACTIVE_LEASE_REQUIRED')
            lease=worker.lease
            if operation=='heartbeat':result=c.heartbeat(lease)
            elif operation=='heartbeat_teacher':result=c.heartbeat_projection(lease)
            elif operation=='commit_result':
                result=c.commit_result(lease,payload['location'],request_key=message['idempotency_key'])
            elif operation=='ack_attempt_started':
                result=c.ack_attempt_started(lease,request_key=message['idempotency_key'],
                                            gate_summary=payload['gate_summary'])
            else:
                result=getattr(c,operation)(lease,request_key=message['idempotency_key'])
        return _jsonable(result)

    def start(self):
        if self._thread is not None or self._closed:
            raise ValueError('COLLECTION_RPC_ALREADY_STARTED')
        self._thread=threading.Thread(target=self.server.serve_forever,daemon=True,
                                      name='act-collection-rpc-'+self.worker_id)
        self._thread.start()

    def close(self):
        if self._closed:return
        self._closed=True
        self.server.close(preserve_socket=True)
        if self.server._executor is not None:
            self.server._executor.shutdown(wait=True)
        if self._thread is not None:
            self._thread.join(timeout=1.)
            if self._thread.is_alive():
                raise ValueError('COLLECTION_RPC_THREAD_EXIT_UNCONFIRMED')
