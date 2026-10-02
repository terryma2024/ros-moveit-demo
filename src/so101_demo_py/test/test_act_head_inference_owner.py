"""One declared worker owns model construction, calibration and live inference."""
import threading
import time

import pytest

from so101_demo.cli import head_feedback_bootstrap as bootstrap


def start(factory,faults):
    return bootstrap._start_owned_detector(factory=factory,
        fault_callback=lambda reason:faults.append(reason))


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
        self.owner=threading.get_native_id();self.closed=False
    def infer(self):
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
