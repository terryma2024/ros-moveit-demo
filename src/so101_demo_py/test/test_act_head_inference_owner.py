"""One declared worker owns model construction, calibration and live inference."""
import threading
import time

import pytest

from so101_demo.cli import head_feedback_bootstrap as bootstrap


def start(factory,faults,simulation_policy=None):
    return bootstrap._start_owned_detector(factory=factory,
        fault_callback=lambda reason:faults.append(reason),
        **({'simulation_policy':simulation_policy} if simulation_policy is not None else {}))


class Detector:
    def __init__(self):self.calls=[];self.block=None;self.entered=threading.Event()
    def reset(self):self.calls.append(('reset',threading.get_native_id()))
    def detect(self,pixels,**kwargs):
        self.calls.append(('detect',threading.get_native_id(),pixels,kwargs))
        self.entered.set()
        if self.block is not None:assert self.block.wait(1.)
        return ['real return from controlled detector boundary']


def factory(detector,construction):
    def build():
        construction.append(threading.get_native_id())
        return dict(runtime=detector,runtime_device='cuda',weights_sha256='a'*64,model_id='c2a')
    return build


def test_factory_calibration_and_reset_run_on_one_eager_owned_thread():
    detector=Detector();construction=[];faults=[]
    worker=start(factory(detector,construction),faults)
    try:
        built=worker.configuration(timeout_s=1.)
        assert built['runtime'] is worker and built['runtime_device']=='cuda'
        receipt=built['inference_owner'];assert receipt['daemon'] is False
        assert construction==[receipt['native_id']] and receipt['native_id']!=threading.get_native_id()
        worker.reset();assert worker.detect(b'pixels',source_stamp_ns=7)==['real return from controlled detector boundary']
        assert {row[1] for row in detector.calls}==set(construction) and not faults
    finally:
        retired=worker.close(timeout_s=1.)
        assert retired['retired'] and retired['factory_count']==1


def test_repeated_readiness_does_not_construct_another_model_or_thread():
    detector=Detector();construction=[];faults=[]
    worker=start(factory(detector,construction),faults)
    try:
        first=worker.configuration(timeout_s=1.);second=worker.configuration(timeout_s=1.)
        assert first['inference_owner']==second['inference_owner'] and len(construction)==1
    finally:worker.close(timeout_s=1.)


class Live:
    def __init__(self,detector):
        self.detector=detector;self.primary=type('Primary',(),{'ready':True,'failed':False})()
        self.entered=threading.Event();self.release=threading.Event();self.count=0;self.records=[]
        self.owner=threading.get_native_id();self.closed=False;self.activated=False
    def activate(self):
        assert self.primary.ready and not self.activated
        self.activated=True
    def infer(self):
        assert self.activated
        assert threading.get_native_id()==self.owner
        if self.count:return None
        self.count+=1;self.entered.set()
        assert self.release.wait(1.)
        value=self.detector.detect(b'live',source_stamp_ns=8)
        self.records.append(dict(value=value,owner=threading.get_native_id()))
    def records_snapshot(self):return [dict(row) for row in self.records]
    def next_completed_exposure(self,after_sequence):
        from copy import deepcopy
        return None if after_sequence>=len(self.records) else deepcopy(self.records[after_sequence])
    def close(self):
        self.closed=True
        return dict(retired=True,inference_calls=self.count,completed_exposures=len(self.records),
            sequence=self.count,source_floor_ns=8)
    def freeze_retirement(self):
        assert threading.get_native_id()==self.owner
        self.closed=True
        return dict(retired=True,inference_calls=self.count,completed_exposures=len(self.records),
            sequence=self.count,source_floor_ns=8)
    def retirement_snapshot(self):
        assert self.closed
        return dict(retired=True,inference_calls=self.count,completed_exposures=len(self.records),
            sequence=self.count,source_floor_ns=8)


class StoppedLive(Live):
    """Controlled stopped-demand boundary; no real CUDA or simulator claims."""
    def __init__(self,detector,policy):
        from types import SimpleNamespace
        super().__init__(detector)
        self._simulation_policy=policy;self.monotonic=time.monotonic
        self.primary._simulation_policy=policy
        self.primary.epoch=SimpleNamespace(epoch='attempt',generation=5,session_id='session',policy_hash='a'*64)
        self.requests=[];self.queried=threading.Event();self.pixels_ready=threading.Event()
    def infer(self,*,observation_request):
        from copy import deepcopy
        assert self.activated and threading.get_native_id()==self.owner
        self.requests.append(deepcopy(observation_request));self.queried.set()
        if not self.pixels_ready.is_set():return None
        self.count+=1
        value=self.detector.detect(b'stopped',source_stamp_ns=9)
        row=dict(sequence=self.count,value=value,request=deepcopy(observation_request))
        self.records.append(row)
        return row


def stopped_worker():
    from so101_demo.act.head_simulation_policy import HeadSimulationPolicy
    policy=HeadSimulationPolicy.parse(HeadSimulationPolicy.default_document())
    detector=Detector();construction=[];faults=[];lives=[]
    worker=start(factory(detector,construction),faults,policy)
    worker.configuration(timeout_s=1.)
    def build(d):
        live=StoppedLive(d,policy);lives.append(live);return live
    worker.bind_live(build,timeout_s=1.);worker.activate_live()
    return worker,lives[0],detector,construction,faults


def stopped_request(live,*,sequence=1,motion_epoch=0):
    from so101_demo.act.head_monitor import digest
    now=time.monotonic()
    return dict(schema_version=1,epoch='attempt',generation=5,session_id='session',policy_sha256='a'*64,
        simulation_policy_sha256=digest(live._simulation_policy.readback()),motion_epoch=motion_epoch,
        observation_sequence=sequence,settled_source_floor_ns=1_000_000_000,
        settled_wall_s=now-.01,requested_wall_s=now,search_deadline_ns=round((now+29.)*1e9))


def wait_completed(worker):
    deadline=time.monotonic()+1.
    while (not worker.results or worker.observation_pending) and time.monotonic()<deadline:time.sleep(.001)
    assert worker.results and not worker.observation_pending


def test_simulation_owned_thread_never_starts_yolo_without_one_stopped_request():
    worker,live,detector,construction,faults=stopped_worker()
    try:
        assert not live.queried.wait(.05) and detector.calls==[]
        request=stopped_request(live);original=dict(request)
        worker.request_observation(request);request['generation']=99
        assert live.queried.wait(.5) and worker.observation_pending
        assert detector.calls==[]
        live.pixels_ready.set();wait_completed(worker)
        assert len(detector.calls)==1 and detector.calls[0][1]==construction[0]
        assert all(row==original for row in live.requests)
        before=len(live.requests);time.sleep(.05)
        assert len(live.requests)==before and live.count==1 and not faults
    finally:worker.close(timeout_s=1.)


def test_simulation_pending_original_request_survives_short_primary_progress_wait():
    worker,live,detector,_,faults=stopped_worker()
    try:
        request=stopped_request(live);worker.request_observation(request)
        assert live.queried.wait(.5)
        live.primary.ready=False;time.sleep(.06)
        assert worker.observation_pending and detector.calls==[] and not faults
        live.primary.ready=True;live.pixels_ready.set();wait_completed(worker)
        assert worker.results[0]['request']==request and live.count==1 and not faults
    finally:worker.close(timeout_s=1.)


def test_simulation_second_request_cannot_replace_pending_original_or_run_another_detector():
    worker,live,detector,construction,faults=stopped_worker()
    try:
        worker.request_observation(stopped_request(live));assert live.queried.wait(.5)
        with pytest.raises(PermissionError):worker.request_observation(stopped_request(live,sequence=2))
        assert faults and detector.calls==[] and len(construction)==1
    finally:worker.close(timeout_s=1.)


@pytest.mark.parametrize('damage',['sequence','motion','settled_floor','settled_wall','search_deadline'])
def test_simulation_next_request_cannot_replay_or_renew_motion_and_whole_deadline(damage):
    worker,live,detector,_,faults=stopped_worker()
    try:
        request=stopped_request(live,motion_epoch=1);live.pixels_ready.set()
        worker.request_observation(request);wait_completed(worker)
        next_request=dict(request,observation_sequence=2,requested_wall_s=time.monotonic())
        if damage=='sequence':next_request['observation_sequence']=1
        elif damage=='motion':next_request['motion_epoch']=0
        elif damage=='settled_floor':next_request['settled_source_floor_ns']+=1
        elif damage=='settled_wall':next_request['settled_wall_s']+=.001
        else:next_request['search_deadline_ns']+=1
        with pytest.raises(PermissionError):worker.request_observation(next_request)
        assert faults and len(detector.calls)==1
    finally:worker.close(timeout_s=1.)


def test_simulation_live_binding_cannot_hide_a_different_policy_document_in_numeric_equality():
    from so101_demo.act.head_simulation_policy import HeadSimulationPolicy
    document=HeadSimulationPolicy.default_document();policy=HeadSimulationPolicy.parse(document)
    document['stop_confirmation_timeout_s']=1
    different=HeadSimulationPolicy.parse(document)
    detector=Detector();construction=[];faults=[]
    worker=start(factory(detector,construction),faults,policy)
    try:
        worker.configuration(timeout_s=1.)
        with pytest.raises(PermissionError):worker.bind_live(lambda d:StoppedLive(d,different),timeout_s=1.)
        assert faults and detector.calls==[] and len(construction)==1
    finally:worker.close(timeout_s=1.)


def test_simulation_new_motion_can_request_one_new_observation_after_prior_completion():
    worker,live,detector,construction,faults=stopped_worker()
    try:
        request=stopped_request(live);live.pixels_ready.set()
        worker.request_observation(request);wait_completed(worker)
        now=time.monotonic()
        following=dict(request,observation_sequence=2,motion_epoch=1,
            settled_source_floor_ns=1_100_000_000,settled_wall_s=now-.001,requested_wall_s=now)
        worker.request_observation(following);wait_completed(worker)
        assert len(detector.calls)==2 and live.count==2 and len(construction)==1 and not faults
        assert worker.results[1]['request']==following
    finally:worker.close(timeout_s=1.)


def test_simulation_primary_wait_has_a_finite_original_supervision_cap_without_new_work():
    worker,live,detector,_,faults=stopped_worker()
    try:
        worker.request_observation(stopped_request(live));assert live.queried.wait(.5)
        wall=[time.monotonic()];live.monotonic=lambda:wall[0];live.primary.ready=False
        time.sleep(.05);wall[0]+=.5
        deadline=time.monotonic()+.5
        while not faults and time.monotonic()<deadline:time.sleep(.001)
        assert faults and detector.calls==[]
        with pytest.raises(PermissionError):worker.infer()
    finally:worker.close(timeout_s=1.)


def test_simulation_quiescence_retains_unstarted_request_without_starting_yolo():
    worker,live,detector,_,faults=stopped_worker()
    try:
        request=stopped_request(live);worker.request_observation(request)
        assert live.queried.wait(.5);worker.quiesce_live()
        deadline=time.monotonic()+.5
        while worker.live_quiescence() is None and time.monotonic()<deadline:time.sleep(.001)
        assert worker.live_quiescence()['unstarted_observation']==request
        assert not worker.observation_pending and detector.calls==[] and not faults
    finally:worker.close(timeout_s=1.)


def bind(worker,constructed):
    def build(detector):
        live=Live(detector);constructed.append(live);return live
    return worker.bind_live(build,timeout_s=1.)


def test_live_construction_and_inference_keep_same_actual_owner_and_main_responsive():
    detector=Detector();construction=[];faults=[];lives=[]
    worker=start(factory(detector,construction),faults)
    try:
        worker.configuration(timeout_s=1.);bind(worker,lives);live=lives[0]
        assert live.owner==construction[0] and not live.entered.is_set()
        worker.activate_live();assert live.entered.wait(.5)
        # A blocked inference does not own the controller's caller thread.
        before=time.monotonic();worker.infer();snapshot=worker.results
        assert time.monotonic()-before<.1 and snapshot==[]
        before=time.monotonic();assert worker.next_completed_exposure(0) is None
        assert time.monotonic()-before<.1
        assert live.count==1 and construction==[live.owner]
        live.release.set()
        deadline=time.monotonic()+.5
        while not worker.results and time.monotonic()<deadline:time.sleep(.001)
        assert worker.results[0]['owner']==construction[0]
        completed=worker.next_completed_exposure(0);completed['value'].append('changed caller copy')
        assert 'changed caller copy' not in worker.next_completed_exposure(0)['value']
        live.primary.failed=True;live.primary.ready=False
        retired=worker.close(timeout_s=1.)
        assert retired['retired'] and retired['live']['retired'] and live.closed
        assert not faults
    finally:
        for live in lives:live.release.set()
        worker.close(timeout_s=1.)


def test_quiescence_waits_for_actual_inflight_completion_without_blocking_main():
    detector=Detector();construction=[];faults=[];lives=[]
    worker=start(factory(detector,construction),faults)
    try:
        worker.configuration(timeout_s=1.);bind(worker,lives);live=lives[0]
        worker.activate_live();assert live.entered.wait(.5)
        before=time.monotonic();worker.quiesce_live()
        assert time.monotonic()-before<.1
        assert worker.live_quiescence() is None and worker.next_completed_exposure(0) is None
        live.release.set();deadline=time.monotonic()+.5
        while worker.live_quiescence() is None and time.monotonic()<deadline:time.sleep(.001)
        receipt=worker.live_quiescence()
        assert receipt['inference_owner']['native_id']==construction[0]
        assert worker.next_completed_exposure(0)['owner']==construction[0]
        assert receipt['quiesced_wall_s']>=receipt['requested_wall_s']
        changed=worker.live_quiescence();changed['inference_owner']['native_id']=0
        assert worker.live_quiescence()==receipt
        assert live.count==1 and len(construction)==1 and not faults
        retired=worker.close(timeout_s=1.)
        assert retired['quiescence']==receipt and retired['retired']
    finally:
        for live in lives:live.release.set()
        worker.close(timeout_s=1.)


def test_quiescence_cannot_be_requested_before_live_activation():
    detector=Detector();construction=[];faults=[]
    worker=start(factory(detector,construction),faults)
    try:
        worker.configuration(timeout_s=1.)
        with pytest.raises(PermissionError):worker.quiesce_live()
        assert faults
    finally:worker.close(timeout_s=1.)


@pytest.mark.parametrize('requester',['repeat','foreign_thread'])
def test_quiescence_rejects_reuse_and_another_caller(requester):
    detector=Detector();construction=[];faults=[];lives=[];errors=[]
    worker=start(factory(detector,construction),faults)
    try:
        worker.configuration(timeout_s=1.);bind(worker,lives)
        worker.activate_live();assert lives[0].entered.wait(.5)
        if requester=='repeat':
            worker.quiesce_live()
            with pytest.raises(PermissionError,match='QUIESCENCE_REFUSED'):worker.quiesce_live()
        else:
            def request():
                try:worker.quiesce_live()
                except PermissionError as error:errors.append(error)
            caller=threading.Thread(target=request);caller.start();caller.join(1.)
            assert not caller.is_alive() and len(errors)==1
            assert 'QUIESCENCE_REFUSED' in str(errors[0])
        assert faults and len(construction)==1 and lives[0].count==1
        with pytest.raises(PermissionError):worker.infer()
    finally:
        for live in lives:live.release.set()
        worker.close(timeout_s=1.)


@pytest.mark.parametrize('operation',['reset','detect','bind_again','activate_again'])
def test_bound_or_running_worker_cannot_reset_model_or_bind_a_second_live_reader(operation):
    detector=Detector();construction=[];faults=[];lives=[]
    worker=start(factory(detector,construction),faults)
    try:
        worker.configuration(timeout_s=1.);bind(worker,lives)
        if operation=='activate_again':worker.activate_live();assert lives[0].entered.wait(.5)
        with pytest.raises(PermissionError):
            if operation=='reset':worker.reset()
            elif operation=='detect':worker.detect(b'pixels')
            elif operation=='bind_again':bind(worker,lives)
            else:worker.activate_live()
        assert len(lives)==1 and len(construction)==1
        assert faults
    finally:
        for live in lives:live.release.set()
        worker.close(timeout_s=1.)


def test_factory_failure_faults_before_custom_exception_formatter_and_cannot_rebuild():
    faults=[];formats=[];builds=[]
    class Failure(RuntimeError):
        def __str__(self):formats.append(True);return 'custom formatter must not execute'
    def broken():builds.append(threading.get_native_id());raise Failure('factory failed')
    worker=start(broken,faults)
    try:
        with pytest.raises(PermissionError):worker.configuration(timeout_s=1.)
        with pytest.raises(PermissionError):worker.reset()
        assert faults and not formats and len(builds)==1
    finally:assert worker.close(timeout_s=1.)['retired']


def test_unconfirmed_retirement_closes_submission_and_never_claims_worker_exit():
    detector=Detector();construction=[];faults=[];lives=[]
    worker=start(factory(detector,construction),faults)
    try:
        worker.configuration(timeout_s=1.);bind(worker,lives);worker.activate_live()
        assert lives[0].entered.wait(.5)
        with pytest.raises(PermissionError,match='RETIRE_UNCONFIRMED'):worker.close(timeout_s=.001)
        with pytest.raises(PermissionError):worker.detect(b'late')
        lives[0].release.set()
        retired=worker.close(timeout_s=1.)
        assert retired['retired'] and len(construction)==1 and faults
    finally:
        for live in lives:live.release.set()
        worker.close(timeout_s=1.)


def test_live_failure_closes_owner_and_never_produces_a_result():
    detector=Detector();construction=[];faults=[]
    class BrokenLive(Live):
        def infer(self):raise ValueError('real live operation failed')
    worker=start(factory(detector,construction),faults)
    try:
        worker.configuration(timeout_s=1.);worker.bind_live(lambda d:BrokenLive(d),timeout_s=1.)
        worker.activate_live()
        deadline=time.monotonic()+.5
        while not faults and time.monotonic()<deadline:time.sleep(.001)
        with pytest.raises(PermissionError):worker.infer()
        assert worker.results==[] and faults
    finally:assert worker.close(timeout_s=1.)['retired']


def test_readiness_and_live_snapshots_cannot_mutate_owned_records():
    detector=Detector();construction=[];faults=[];lives=[]
    worker=start(factory(detector,construction),faults)
    try:
        first=worker.configuration(timeout_s=1.);owner=first['inference_owner']['native_id']
        first['inference_owner']['native_id']=0
        assert worker.configuration(timeout_s=1.)['inference_owner']['native_id']==owner
        bind(worker,lives);lives[0].records.append(dict(value=['original']))
        snapshot=worker.results;snapshot[0]['value'][0]='caller changed it'
        assert worker.results==[dict(value=['original'])]
    finally:worker.close(timeout_s=1.)


def test_actual_owner_exits_without_bulk_readback_then_caller_retains_originals():
    detector=Detector();construction=[];faults=[];lives=[];snapshots=[];frozen=[]
    class AuditLive(Live):
        def close(self):
            raise RuntimeError('bulk retirement cannot run on the CUDA owner')
        def freeze_retirement(self):
            frozen.append(threading.get_native_id())
            return super().freeze_retirement()
        def retirement_snapshot(self):
            assert not worker._thread.is_alive()
            snapshots.append(threading.get_native_id())
            return dict(super().retirement_snapshot(),original_attempts=[dict(sequence=68,outcome='REFUSED')])
    worker=start(factory(detector,construction),faults)
    try:
        worker.configuration(timeout_s=1.)
        def build(d):
            live=AuditLive(d);lives.append(live);return live
        worker.bind_live(build,timeout_s=1.)
        receipt=worker.close(timeout_s=1.)
        assert receipt['retired'] and not receipt['thread_alive']
        assert frozen==construction and snapshots==[threading.get_native_id()]
        assert receipt['live']['original_attempts']==[dict(sequence=68,outcome='REFUSED')]
        receipt['live']['original_attempts'][0]['outcome']='caller changed it'
        assert worker.close()['live']['original_attempts'][0]['outcome']=='REFUSED'
        assert not faults
    finally:
        for live in lives:live.release.set()
        if worker._thread.is_alive():worker.close(timeout_s=1.)


def test_root_execution_trace_detaches_after_primary_and_model_retirement():
    import gc
    from so101_demo.adapters.act.head_monitor_process import MonitorExecutionTrace
    before=(gc.isenabled(),gc.get_threshold(),tuple(gc.callbacks))
    trace=MonitorExecutionTrace()
    class Primary:
        def close(self):
            assert trace._result is None
            trace.mark('primary_closed')
            return dict(stage='RETIRED',motion_authority=False)
    class Owner:
        def close(self):
            assert trace._result is None
            trace.mark('model_retired')
            return dict(error=None,retired=True)
    result=dict(status='REFUSED')
    try:
        assert bootstrap._retire_entry_inference(primary=Primary(),inference_owner=Owner(),
            live=None,result=result,execution_trace=trace)
    finally:trace.finish()
    retained=result['root_execution_trace']
    assert [r[1] for r in retained['server_phases']]==['primary_closed','model_retired']
    assert retained['qualification'] is False and retained['motion_authority'] is False
    assert (gc.isenabled(),gc.get_threshold(),tuple(gc.callbacks))==before


@pytest.mark.parametrize('primary_failure',[False,True])
def test_entry_closes_reactive_primary_before_joined_owner_bulk_snapshot(primary_failure):
    detector=Detector();construction=[];faults=[];lives=[];snapshots=[]
    class ReactivePrimary:
        ready=True;failed=False;_finished=False
        def close(self):
            self.ready=False;self.failed=True
            if primary_failure:raise PermissionError('original Stop worker still alive')
            self._finished=True
            return dict(stage='RETIRED',motion_authority=False)
    primary=ReactivePrimary()
    class GuardedLive(Live):
        def retirement_snapshot(self):
            if not primary._finished:raise PermissionError('HEAD_LIVE_PRIMARY_RETIRE_UNCONFIRMED')
            assert not worker._thread.is_alive()
            snapshots.append(threading.get_native_id())
            return super().retirement_snapshot()
    worker=start(factory(detector,construction),faults)
    result=dict(status='REFUSED',live_exposure_diagnostic={})
    try:
        worker.configuration(timeout_s=1.)
        def build(d):
            live=GuardedLive(d);live.primary=primary;lives.append(live);return live
        worker.bind_live(build,timeout_s=1.)
        retired=bootstrap._retire_entry_inference(primary=primary,inference_owner=worker,live=worker,result=result)
        assert retired is (not primary_failure) and not worker._thread.is_alive()
        if primary_failure:
            assert result['producer_seals_withheld'] and not snapshots
            assert 'primary_teardown_error' in result and 'inference_owner_teardown_error' in result
        else:
            assert result['inference_owner_teardown']['retired'] and snapshots==[threading.get_native_id()]
            assert result['live_exposure_diagnostic']['records']==[]
    finally:
        primary._finished=True
        for live in lives:live.release.set()
        worker.close(timeout_s=1.)


def test_changed_frozen_retirement_never_becomes_a_valid_joined_receipt():
    detector=Detector();construction=[];faults=[]
    class ChangedLive(Live):
        def retirement_snapshot(self):return dict(super().retirement_snapshot(),sequence=999)
    worker=start(factory(detector,construction),faults)
    worker.configuration(timeout_s=1.)
    worker.bind_live(lambda d:ChangedLive(d),timeout_s=1.)
    with pytest.raises(PermissionError,match='RETIRE_CHANGED'):worker.close(timeout_s=1.)
    assert not worker._thread.is_alive() and worker._retired is None
