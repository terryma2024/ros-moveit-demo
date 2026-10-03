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


class HeadInferenceOwner:
    def __init__(self,*,factory,fault_callback):
        if not callable(factory) or not callable(fault_callback):
            raise ValueError('HEAD_INFERENCE_OWNER_CONFIG_INVALID')
        self._factory=factory;self._fault_callback=fault_callback
        self._entry_caller=threading.get_ident();self._lock=threading.Lock()
        self._jobs=queue.Queue(maxsize=1);self._ready=Future();self._retiring=threading.Event()
        self._stage='STARTING';self._error=None;self._closed=False;self._retired=None
        self._detector=None;self._live=None;self._factory_count=0;self._calibration_calls=0
        self._live_retirement=None;self._owner=None;self._metadata=None;self._operation_error=None
        self._quiescence=None
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
                        self._quiescence['quiesced_wall_s']=time.monotonic()
                        self._quiescence['inference_owner']=deepcopy(self._owner)
                        self._stage='QUIESCED'
                    continue
                if stage=='LIVE':
                    if not self._live.primary.ready:
                        if self._live.primary.failed:break
                        raise PermissionError('HEAD_INFERENCE_LIVE_PRIMARY_NOT_READY')
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
                    if (not callable(self._live.infer) or not callable(self._live.close)
                            or not callable(self._live.records_snapshot) or not callable(self._live.activate)):
                        raise ValueError('HEAD_INFERENCE_LIVE_BINDING_INVALID')
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
                try:self._live_retirement=self._live.close()
                except BaseException as error:self._fail('HEAD_INFERENCE_LIVE_RETIRE_FAILED',error)
            while True:
                try:queued=self._jobs.get_nowait()
                except queue.Empty:break
                queued[2].set_exception(PermissionError('HEAD_INFERENCE_OWNER_CLOSED'));self._jobs.task_done()
            with self._lock:self._stage='EXITED'

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
        if self._live is not None and (self._live_retirement is None
                or self._live_retirement.get('retired') is not True):
            raise PermissionError('HEAD_INFERENCE_LIVE_RETIRE_UNCONFIRMED')
        self._retired=dict(retired=True,factory_count=self._factory_count,
            calibration_detect_calls=self._calibration_calls,inference_owner=deepcopy(self._owner),
            live=self._live_retirement,error=self._error,thread_alive=False,
            operation_error=self._operation_error,
            quiescence=deepcopy(self._quiescence),
            retired_wall_s=time.monotonic())
        return deepcopy(self._retired)
