"""One eager, joined thread owns the entry's model and every CUDA call.

The pre-ARM proxy preserves calibration's original clocks. Live consumption is
bound once on that same thread and never blocks the controller's caller thread.
No ROS, SDK, model fallback, retry or replacement thread is constructed here.
"""
from concurrent.futures import Future
from copy import deepcopy
import math
import queue
import threading
import time

from .head_callback_io import exception_metadata
from so101_demo.act.head_feedback import nanoseconds
from so101_demo.act.head_evidence_identity import canonical_bytes
from so101_demo.act.head_simulation_policy import HeadSimulationPolicy, validate_stopped_observation_request


class HeadInferenceOwner:
    def __init__(self,*,factory,fault_callback,simulation_policy=None):
        if not callable(factory) or not callable(fault_callback):
            raise ValueError('HEAD_INFERENCE_OWNER_CONFIG_INVALID')
        self._simulation_policy=(None if simulation_policy is None else HeadSimulationPolicy.parse(
            simulation_policy.readback() if type(simulation_policy) is HeadSimulationPolicy else simulation_policy))
        self._factory=factory;self._fault_callback=fault_callback
        self._entry_caller=threading.get_ident();self._lock=threading.Lock()
        self._jobs=queue.Queue(maxsize=1);self._ready=Future();self._retiring=threading.Event()
        self._stage='STARTING';self._error=None;self._closed=False;self._retired=None
        self._detector=None;self._live=None;self._factory_count=0;self._calibration_calls=0
        self._live_retirement=None;self._owner=None;self._metadata=None;self._operation_error=None
        self._quiescence=None
        self._observation=None;self._last_observation=None;self._not_ready_since=None
        self._completed_observation_sequence=0
        self._thread=threading.Thread(target=self._run,name='head-owned-inference',daemon=False)
        try:self._thread.start()
        except BaseException:
            self._fail('HEAD_INFERENCE_OWNER_START_FAILED');raise

    def _fail(self,reason,error=None):
        # Close submissions and wake retirement before external reporting or
        # bounded metadata. A custom exception formatter never owns this path.
        with self._lock:
            self._closed=True
            if self._error is None:self._error=reason
        self._retiring.set()
        try:self._fault_callback(reason)
        except Exception:pass
        if error is not None:
            with self._lock:self._error=reason+': '+exception_metadata(error)

    def _run(self):
        pending=None
        try:
            self._owner=dict(name=threading.current_thread().name,ident=threading.get_ident(),
                native_id=threading.get_native_id(),daemon=threading.current_thread().daemon,
                started_wall_s=time.monotonic())
            self._factory_count+=1;built=self._factory()
            if (type(built) is not dict or 'runtime' not in built
                    or not callable(built['runtime'].detect) or not callable(built['runtime'].reset)):
                raise ValueError('HEAD_INFERENCE_FACTORY_INVALID')
            self._detector=built['runtime'];self._metadata=deepcopy({k:v for k,v in built.items() if k!='runtime'})
            with self._lock:
                if self._closed:raise PermissionError('HEAD_INFERENCE_ENTRY_REVOKED')
                self._stage='READY'
            self._ready.set_result(True)
            while not self._retiring.is_set():
                with self._lock:stage=self._stage
                if stage=='QUIESCING':
                    # This owner reaches here only after its current complete
                    # inference/admission/completion call has returned.
                    with self._lock:
                        if self._simulation_policy is not None:
                            self._quiescence['unstarted_observation']=deepcopy(self._observation)
                            self._observation=None
                        self._quiescence['quiesced_wall_s']=time.monotonic()
                        self._quiescence['inference_owner']=deepcopy(self._owner)
                        self._stage='QUIESCED'
                    continue
                if stage=='LIVE':
                    if not self._live.primary.ready:
                        if self._live.primary.failed:break
                        if self._simulation_policy is not None:
                            now=self._live.monotonic()
                            if self._not_ready_since is None:self._not_ready_since=now
                            if (nanoseconds(now)<nanoseconds(self._not_ready_since)
                                    or nanoseconds(now)-nanoseconds(self._not_ready_since)
                                        >=nanoseconds(self._simulation_policy.fault_reaction_limit_s)):
                                raise PermissionError('HEAD_INFERENCE_LIVE_PRIMARY_NOT_READY')
                            self._retiring.wait(self._simulation_policy.watchdog_period_s)
                            continue
                        raise PermissionError('HEAD_INFERENCE_LIVE_PRIMARY_NOT_READY')
                    self._not_ready_since=None
                    if self._simulation_policy is not None:
                        with self._lock:request=self._observation
                        if request is not None:
                            if nanoseconds(self._live.monotonic())>=request['search_deadline_ns']:
                                raise PermissionError('HEAD_INFERENCE_STOPPED_SEARCH_EXPIRED')
                            result=self._live.infer(observation_request=deepcopy(request))
                            if result is not None:
                                with self._lock:
                                    if self._observation is not request:
                                        raise PermissionError('HEAD_INFERENCE_STOPPED_REQUEST_CHANGED')
                                    self._observation=None
                                    # Publication by the live channel precedes
                                    # infer's return. Release this request and
                                    # expose its completion in one owner commit.
                                    self._completed_observation_sequence=request['observation_sequence']
                        self._retiring.wait(self._simulation_policy.watchdog_period_s)
                    else:
                        self._live.infer()
                        self._retiring.wait(.001)
                    continue
                try:pending=self._jobs.get(timeout=.002)
                except queue.Empty:continue
                operation,payload,future=pending
                with self._lock:closed=self._closed
                if closed:raise PermissionError('HEAD_INFERENCE_OWNER_CLOSED')
                if operation=='detect':
                    pixels,kwargs=payload;self._calibration_calls+=1
                    result=self._detector.detect(pixels,**kwargs)
                elif operation=='reset':result=self._detector.reset()
                elif operation=='bind':
                    self._live=payload(self._detector)
                    if (not callable(self._live.infer)
                            or not callable(getattr(self._live,'freeze_retirement',None))
                            or not callable(getattr(self._live,'retirement_snapshot',None))
                            or not callable(self._live.records_snapshot) or not callable(self._live.activate)):
                        raise ValueError('HEAD_INFERENCE_LIVE_BINDING_INVALID')
                    if self._simulation_policy is not None:
                        expected=canonical_bytes(self._simulation_policy.readback())
                        for actual in (self._live._simulation_policy,self._live.primary._simulation_policy):
                            if (type(actual) is not HeadSimulationPolicy
                                    or canonical_bytes(actual.readback())!=expected):
                                raise ValueError('HEAD_INFERENCE_LIVE_POLICY_MISMATCH')
                    with self._lock:self._stage='BOUND'
                    result=dict(bound=True,inference_owner=deepcopy(self._owner))
                else:raise PermissionError('HEAD_INFERENCE_OPERATION_INVALID')
                future.set_result(result);self._jobs.task_done();pending=None
        except BaseException as error:
            controlled=(self._live is not None and self._live.primary.failed)
            if not controlled:self._fail('HEAD_INFERENCE_OWNER_FAILED',error)
            self._operation_error=dict(controlled_primary_revoked=controlled,
                metadata=exception_metadata(error),observed_wall_s=time.monotonic())
            if not self._ready.done():self._ready.set_exception(PermissionError('HEAD_INFERENCE_OWNER_FAILED'))
            if pending is not None:
                if not pending[2].done():pending[2].set_exception(PermissionError('HEAD_INFERENCE_OWNER_FAILED'))
                self._jobs.task_done();pending=None
        finally:
            with self._lock:self._closed=True
            if self._live is not None:
                try:self._live_retirement=self._live.freeze_retirement()
                except BaseException as error:self._fail('HEAD_INFERENCE_LIVE_RETIRE_FAILED',error)
            while True:
                try:queued=self._jobs.get_nowait()
                except queue.Empty:break
                queued[2].set_exception(PermissionError('HEAD_INFERENCE_OWNER_CLOSED'));self._jobs.task_done()
            with self._lock:self._stage='EXITED'

    @property
    def runtime_device(self):
        with self._lock:
            return None if self._metadata is None else self._metadata.get('runtime_device')

    def configuration(self,*,timeout_s):
        if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=90:
            raise ValueError('HEAD_INFERENCE_READY_TIMEOUT_INVALID')
        try:self._ready.result(timeout_s)
        except Exception as error:
            self._fail('HEAD_INFERENCE_READY_REFUSED',error)
            raise PermissionError('HEAD_INFERENCE_READY_REFUSED') from error
        with self._lock:
            if self._closed or self._error is not None:raise PermissionError('HEAD_INFERENCE_OWNER_CLOSED')
        return dict(deepcopy(self._metadata),runtime=self,inference_owner=deepcopy(self._owner))

    def _call(self,operation,payload=None,*,timeout_s=90.):
        if threading.get_ident()!=self._entry_caller:
            self._fail('HEAD_INFERENCE_CALLER_INVALID');raise PermissionError('HEAD_INFERENCE_CALLER_INVALID')
        future=Future()
        refusal=None
        with self._lock:
            if self._closed or self._error is not None or self._stage!='READY':
                refusal='HEAD_INFERENCE_STAGE_INVALID'
            else:
                try:self._jobs.put_nowait((operation,payload,future))
                except queue.Full:refusal='HEAD_INFERENCE_QUEUE_FULL'
                if refusal is None and operation=='bind':self._stage='BINDING'
        if refusal is not None:
            self._fail(refusal);raise PermissionError(refusal)
        try:return future.result(timeout_s)
        except Exception as error:
            self._fail('HEAD_INFERENCE_CALL_REFUSED',error)
            raise PermissionError('HEAD_INFERENCE_CALL_REFUSED') from error

    def reset(self):return self._call('reset')

    def detect(self,pixels,**kwargs):return self._call('detect',(pixels,deepcopy(kwargs)))

    def bind_live(self,factory,*,timeout_s):
        if not callable(factory):raise ValueError('HEAD_INFERENCE_LIVE_FACTORY_INVALID')
        return self._call('bind',factory,timeout_s=timeout_s)

    def activate_live(self):
        refused=False
        with self._lock:
            if (self._closed or self._error is not None or self._stage!='BOUND'
                    or not self._live.primary.ready):
                refused=True
            else:self._stage='ACTIVATING'
        if refused:
            self._fail('HEAD_INFERENCE_ACTIVATION_REFUSED')
            raise PermissionError('HEAD_INFERENCE_ACTIVATION_REFUSED')
        try:self._live.activate()
        except BaseException as error:
            self._fail('HEAD_INFERENCE_ACTIVATION_REFUSED',error)
            raise PermissionError('HEAD_INFERENCE_ACTIVATION_REFUSED') from error
        with self._lock:
            if (self._closed or self._error is not None or self._stage!='ACTIVATING'
                    or not self._live.primary.ready):refused=True
            else:self._stage='LIVE'
        if refused:
            self._fail('HEAD_INFERENCE_ACTIVATION_REFUSED')
            raise PermissionError('HEAD_INFERENCE_ACTIVATION_REFUSED')

    def infer(self):
        """Main control polling performs no model or queue wait."""
        with self._lock:
            if self._error is not None or self._stage not in ('BOUND','LIVE','QUIESCING','QUIESCED'):
                raise PermissionError('HEAD_INFERENCE_LIVE_REFUSED')
        return None

    @property
    def observation_pending(self):
        with self._lock:return self._observation is not None

    def request_observation(self,request):
        """One original request occupies the existing owner until completed."""
        try:
            if threading.get_ident()!=self._entry_caller or self._simulation_policy is None:
                raise PermissionError('HEAD_INFERENCE_STOPPED_REQUEST_OWNER_INVALID')
            with self._lock:
                if (self._closed or self._error is not None or self._stage!='LIVE'
                        or self._observation is not None):
                    raise PermissionError('HEAD_INFERENCE_STOPPED_REQUEST_STAGE_INVALID')
            epoch=self._live.primary.epoch
            bound=validate_stopped_observation_request(request,policy=self._simulation_policy,
                expected_scope=dict(epoch=epoch.epoch,generation=epoch.generation,
                    session_id=epoch.session_id,policy_sha256=epoch.policy_hash),now_wall_s=self._live.monotonic())
            with self._lock:
                last=self._last_observation
                if (self._closed or self._error is not None or self._stage!='LIVE'
                        or self._observation is not None or self._live.primary.ready is not True
                        or bound['observation_sequence']!=(1 if last is None else last['observation_sequence']+1)):
                    raise PermissionError('HEAD_INFERENCE_STOPPED_REQUEST_STAGE_INVALID')
                if last is not None:
                    same_motion=bound['motion_epoch']==last['motion_epoch']
                    if (bound['motion_epoch']<last['motion_epoch']
                            or nanoseconds(bound['requested_wall_s'])<=nanoseconds(last['requested_wall_s'])
                            or bound['search_deadline_ns']!=last['search_deadline_ns']
                            or (same_motion and any(bound[key]!=last[key]
                                for key in ('settled_source_floor_ns','settled_wall_s')))
                            or (not same_motion and (bound['settled_source_floor_ns']<=last['settled_source_floor_ns']
                                or nanoseconds(bound['settled_wall_s'])<=nanoseconds(last['settled_wall_s'])))):
                        raise PermissionError('HEAD_INFERENCE_STOPPED_REQUEST_REUSED')
                self._observation=bound;self._last_observation=deepcopy(bound)
            return deepcopy(bound)
        except Exception as error:
            self._fail('HEAD_INFERENCE_STOPPED_REQUEST_REFUSED',error)
            raise PermissionError('HEAD_INFERENCE_STOPPED_REQUEST_REFUSED') from error

    def quiesce_live(self):
        refused=False
        with self._lock:
            if (threading.get_ident()!=self._entry_caller or self._closed or self._error is not None
                    or self._stage!='LIVE' or not self._live.primary.ready):refused=True
            else:
                self._quiescence=dict(requested_wall_s=time.monotonic())
                self._stage='QUIESCING'
        if refused:
            self._fail('HEAD_INFERENCE_QUIESCENCE_REFUSED')
            raise PermissionError('HEAD_INFERENCE_QUIESCENCE_REFUSED')

    def live_quiescence(self):
        self.infer()
        with self._lock:
            return deepcopy(self._quiescence) if self._stage=='QUIESCED' else None

    @property
    def results(self):
        live=self._live
        return [] if live is None else deepcopy(live.records_snapshot())

    def next_completed_exposure(self,after_sequence):
        self.infer()  # Status only; never wait for the CUDA worker.
        live=self._live
        if live is None:raise PermissionError('HEAD_INFERENCE_LIVE_NOT_BOUND')
        return live.next_completed_exposure(after_sequence)

    def next_completed_observation(self,after_sequence):
        """Completed stopped-observation row from the bound live channel.

        The local stopped-demand path uses this channel; a live object without
        it is refused rather than served a fabricated row.
        """
        self.infer()  # Status only; never wait for the CUDA worker.
        live=self._live
        if live is None:raise PermissionError('HEAD_INFERENCE_LIVE_NOT_BOUND')
        reader=getattr(live,'next_completed_observation',None)
        if not callable(reader):raise PermissionError('HEAD_INFERENCE_OBSERVATION_CHANNEL_ABSENT')
        with self._lock:completed_sequence=self._completed_observation_sequence
        row=reader(after_sequence)
        if row is not None and row['observation_sequence']>completed_sequence:
            return None
        return row

    def close(self,*,timeout_s=1.):
        if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<=timeout_s<=10:
            raise ValueError('HEAD_INFERENCE_RETIRE_TIMEOUT_INVALID')
        with self._lock:
            self._closed=True
            if self._retired is not None:return deepcopy(self._retired)
        self._retiring.set()
        if self._thread is not threading.current_thread():self._thread.join(timeout_s)
        if self._thread.is_alive():
            self._fail('HEAD_INFERENCE_RETIRE_UNCONFIRMED')
            raise PermissionError('HEAD_INFERENCE_RETIRE_UNCONFIRMED')
        if self._live is not None and (type(self._live_retirement) is not dict
                or self._live_retirement.get('retired') is not True):
            raise PermissionError('HEAD_INFERENCE_LIVE_RETIRE_UNCONFIRMED')
        live_receipt=None if self._live is None else self._live.retirement_snapshot()
        if (self._live is not None and (type(live_receipt) is not dict or live_receipt.get('retired') is not True
                or any(live_receipt.get(key)!=value for key,value in self._live_retirement.items()))):
            raise PermissionError('HEAD_INFERENCE_LIVE_RETIRE_CHANGED')
        self._retired=dict(retired=True,factory_count=self._factory_count,
            calibration_detect_calls=self._calibration_calls,inference_owner=deepcopy(self._owner),
            live=live_receipt,error=self._error,thread_alive=False,
            operation_error=self._operation_error,
            quiescence=deepcopy(self._quiescence),
            retired_wall_s=time.monotonic())
        return deepcopy(self._retired)
