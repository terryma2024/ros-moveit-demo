"""Original stopped capture boundaries; these controls do not execute CUDA."""
from collections import deque
from types import SimpleNamespace
import threading
import json

import pytest
from sensor_msgs.msg import Image, CameraInfo
from rosgraph_msgs.msg import Clock

from so101_demo.adapters.act.head_stopped_capture import StoppedHeadCapture


def test_real_entry_health_starts_after_warmup_before_stable_capture():
    from so101_demo.adapters.act.head_stopped_capture import measure_stopped_workload
    events=[]
    def begin():
        events.append('begin_capture')
        raise RuntimeError('controlled before stable window')
    capture=SimpleNamespace(check=lambda:None,infer=lambda *a,**k:events.append('warm') or {},
        begin_capture=begin)
    detector=SimpleNamespace(reset=lambda:events.append('reset'))
    with pytest.raises(RuntimeError,match='controlled before stable window'):
        measure_stopped_workload(capture,detector,None,session_id='s',stop_velocity_rad_s=.01,
            stop_latency_s=.07,before_stable=lambda:events.append('real_root_start'))
    assert events==['warm','reset','real_root_start','begin_capture']

try:
    from so101_demo.adapters.act.head_stopped_capture import stopped_window_boundary
except ImportError:
    def stopped_window_boundary(receipts,*,now_ns):
        from so101_demo.act.head_feedback import nanoseconds
        gaps=sorted(right-left for left,right in zip(receipts,receipts[1:]))
        midpoint=nanoseconds(receipts[-1])+nanoseconds(gaps[len(gaps)//2]/2)
        if midpoint<=now_ns:raise ValueError('HEAD_STOPPED_WINDOW_DECLARATION_LATE')
        return midpoint


@pytest.fixture
def capture():
    port=SimpleNamespace(_lock=threading.RLock(),_head_samples=deque(),
        _head_feedback=dict(source_ns=1_000_000_000,wall_s=10.,valid=True,
                            positions=(0.,),velocities=(0.,)))
    class Node:
        def __init__(self):
            update=lambda message:None
            self._time_source=SimpleNamespace(ros_time_is_active=True,clock_callback=update,
                _clock_sub=SimpleNamespace(callback=update,topic_name='/clock'))
        def create_subscription(self,kind,topic,callback,qos):return (kind,topic,callback,qos)
        def get_clock(self):
            assert not port._lock._is_owned()
            return SimpleNamespace(now=lambda:SimpleNamespace(nanoseconds=1_010_000_000))
    return StoppedHeadCapture(Node(),port,frame_id='head_camera_frame',monotonic=lambda:10.001)


def image(source=1_000_000_000):
    msg=Image();msg.header.stamp.sec=source//1_000_000_000
    msg.header.stamp.nanosec=source%1_000_000_000;msg.header.frame_id='head_camera_frame'
    msg.width=640;msg.height=480;msg.encoding='rgb8';msg.step=1920;msg.data=bytes(640*480*3)
    return msg


def info(source=1_000_000_000):
    msg=CameraInfo();msg.header.stamp.sec=source//1_000_000_000
    msg.header.stamp.nanosec=source%1_000_000_000;msg.header.frame_id='head_camera_frame'
    msg.width=640;msg.height=480;msg.k=[415.,0.,320.,0.,415.,240.,0.,0.,1.]
    return msg


def test_camera_and_joint_snapshot_precedes_decision_clock(capture):
    capture._image(image());capture._info(info())
    snapshot=capture.snapshot()
    assert snapshot['camera']==capture.camera_messages[-1]
    assert snapshot['joint']['wall_s']==10.
    assert snapshot['clocks']['sim_ns']==1_010_000_000
    capture.port._head_feedback['wall_s']=11.
    assert snapshot['joint']['wall_s']==10.
    assert all((entry.topic_name if hasattr(entry,'topic_name') else entry[1])!='/joint_states' for entry in capture.subscriptions)


def test_stopped_decision_consumes_copied_causal_joint_and_image_keeps_all_future_raw(capture):
    capture._image(image());first_image=dict(capture.camera_messages[-1])
    assert capture.take_image()[0]==first_image  # No unrelated capacity-one drop.
    first_joint=dict(capture.port._head_feedback);capture.port._head_samples.append(first_joint)
    future_joint=dict(first_joint,source_ns=1_012_000_000,wall_s=10.001)
    capture.port._head_samples.append(future_joint);capture.port._head_feedback=future_joint
    capture._image(image(1_100_000_000));pending_image=dict(capture.camera_messages[-1])
    snapshot=capture.snapshot()
    assert snapshot['joint']==first_joint and snapshot['camera']==first_image
    assert snapshot['clocks']['sim_ns']==1_010_000_000
    assert capture.port._head_feedback==future_joint
    assert list(capture.port._head_samples)==[first_joint,future_joint]
    assert list(capture.camera_messages)==[first_image,pending_image]
    assert snapshot['current_original_selection']['joint_candidate_sources_ns']==[1_012_000_000,1_000_000_000]
    assert snapshot['current_original_selection']['camera_candidate_sources_ns']==[1_100_000_000,1_000_000_000]


def test_stopped_snapshot_cannot_consume_any_candidate_before_actual_clock(capture):
    capture.port._head_feedback['source_ns']=1_020_000_000
    capture._image(image(1_100_000_000))
    with pytest.raises(ValueError):capture.snapshot()


def test_original_info_before_warm_boundary_pairs_image_after_boundary(capture):
    capture._info(info());original=dict(capture.info_messages[-1])
    capture.begin_capture();capture._image(image())
    capture.port._head_samples.append(capture.port._head_feedback.copy())
    transform=SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(sec=1,nanosec=0)),
        transform=SimpleNamespace(rotation=SimpleNamespace(x=0.,y=0.,z=0.,w=1.),
            translation=SimpleNamespace(x=0.,y=0.,z=0.)))
    class Buffer:
        def can_transform(self,*args):return True
        def lookup_transform(self,*args):return transform
    class Detector:
        calls=0
        def detect(self,pixels,**identity):
            assert not capture.port._lock._is_owned()
            self.calls+=1;return []
    detector=Detector()
    result=capture.infer(detector,Buffer(),session_id='test',attempt_id='test',stop_velocity_rad_s=.05)
    assert result is not None and detector.calls==1
    assert result['info_received_wall_s']==original['wall_s'] and result['info_source_ns']==original['source_ns']
    assert capture.info_messages[-1]==original and capture._pending is None


@pytest.mark.parametrize('scheduled',[False,True])
def test_cpu_pending_preserves_root_original_and_cuda_waits_then_main_reads_after_reply(capture,scheduled,monkeypatch):
    if not scheduled:capture._image(image());capture._info(info())
    capture.port._head_samples.append(capture.port._head_feedback.copy())
    original=capture._pending;requests=[];wall=[10.001]
    capture.monotonic=lambda:wall[0]
    transform=SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(sec=1,nanosec=0)),
        transform=SimpleNamespace(rotation=SimpleNamespace(x=0.,y=0.,z=0.,w=1.),
            translation=SimpleNamespace(x=0.,y=0.,z=0.)))
    class Buffer:
        def can_transform(self,*args):return True
        def lookup_transform(self,*args):return transform
    class Monitor:
        identity=dict(uid=1,pid=2,start_ticks=3)
        ready=False
        def request_runtime(self,request,*,trace=None):
            from copy import deepcopy
            requests.append(deepcopy(request));operation=request['operation']
            claim=request['exposure'] if operation=='CALIBRATION_FRAME_INPUTS' else request['completion']['claim']
            value=dict(request=operation,stage='CONFIGURED',purpose='calibration',calibration_measurement=True,
                motion_authority=False,epoch='entry',generation=7,session_id='test',monitor_peer=self.identity,
                root_claim=claim,inputs_ready=self.ready,ack_wall_s=wall[0],original_snapshot=dict(
                    image=dict(original[0],wall_s=10.000),info=dict(capture.info_messages[-1],wall_s=10.000),
                    decision=dict(wall_before_s=wall[0],wall_after_s=wall[0],sim_ns=1_010_000_000)))
            if operation=='CALIBRATION_FRAME_COMPLETION':
                value.update(measurement_complete=True,completion=request['completion'])
                # Completion transport/consumer work consumes real elapsed
                # time before Main can read its own decision clocks.
                wall[0]=10.015
            return value
    monitor=Monitor();detector_calls=[]
    class Detector:
        def detect(self,pixels,**identity):
            detector_calls.append(identity);wall[0]=10.010;return []
    capture.bind_measurement_monitor(monitor,epoch='entry',generation=7,session_id='test')
    if scheduled:
        capture.begin_capture();capture._image(image());capture._info(info());original=capture._pending
    with pytest.raises(PermissionError):
        capture.bind_measurement_monitor(monitor,epoch='entry',generation=7,session_id='test')
    assert capture.infer(Detector(),Buffer(),session_id='test',attempt_id='test',stop_velocity_rad_s=.05) is None
    assert capture._pending is original and not detector_calls
    monitor.ready=True
    done=threading.Event();snapshots=[];failures=[]
    original_snapshot=capture.snapshot
    def consumer_snapshot(**kwargs):
        if scheduled:
            assert threading.current_thread().name=='controlled-main-consumer', 'infer reads immediate Main clocks'
        return original_snapshot(**kwargs)
    monkeypatch.setattr(capture,'snapshot',consumer_snapshot)
    def consume():
        try:
            while not done.wait(.001):
                if getattr(capture,'_measurement_pending',None) is not None:
                    snapshots.append(capture.snapshot(consume_measurement=True))
        except BaseException as error:failures.append(error)
    worker=threading.Thread(target=consume,name='controlled-main-consumer')
    if scheduled:worker.start()
    try:
        row=capture.infer(Detector(),Buffer(),session_id='test',attempt_id='test',stop_velocity_rad_s=.05)
    finally:
        done.set()
        if scheduled:worker.join(timeout=1.)
    assert not failures
    assert len(detector_calls)==1 and capture._pending is None
    assert [r['operation'] for r in requests]==['CALIBRATION_FRAME_INPUTS']*2+['CALIBRATION_FRAME_COMPLETION']
    assert all((r.get('exposure') or r['completion']['claim'])['image_received_wall_s']==10.001 for r in requests)
    assert row['image_received_wall_s']==10.001 and row['completion_wall_s']==10.010
    proof=row['matched_consumer_measurement']
    assert proof['cpu_image_received_wall_s']==proof['cpu_info_received_wall_s']==10.000
    assert proof['root_handoff_decision_wall_s']==10.015
    assert row['cpu_measurement_completion']['completion']['completion_wall_s']==10.010
    if scheduled:
        assert row['root_handoff'] in snapshots
        assert row['root_handoff']['calibration_consumed_source_ns']==10**9
        assert row['root_handoff']['calibration_completion_ack_wall_s']==10.010
        assert row['root_handoff']['consumer_thread_native_id']==worker.native_id
    assert [a['outcome'] for a in capture._measurement_attempts]==['ACK']*3
    assert [a['inputs_ready'] for a in capture._measurement_attempts]==[False,True,True]


@pytest.mark.parametrize('damage',['foreign_peer','generation_bool','authority','claimed_original','late',
    'decision_future','missing_completion','completion_changed','original_hash'])
def test_capture_measurement_rejects_bad_ack_before_granting_any_new_work(capture,damage):
    wall=[10.001];capture.monotonic=lambda:wall[0]
    capture._image(image());capture._info(info())
    claim=dict(epoch='entry',generation=7,session_id='test',image_source_ns=10**9,
        info_source_ns=10**9,joint_source_ns=10**9,tf_source_ns=10**9,image_frame_id=capture.frame_id,
        payload_sha256=capture._pending[0]['payload_sha256'],image_received_wall_s=10.001,info_received_wall_s=10.001)
    completion=dict(claim=claim,completion_wall_s=10.001,result_sha256='b'*64)
    class Monitor:
        identity=dict(uid=1,pid=2,start_ticks=3)
        def request_runtime(self,request,*,trace=None):
            value=dict(request=request['operation'],stage='CONFIGURED',purpose='calibration',
                calibration_measurement=True,motion_authority=False,epoch='entry',generation=7,session_id='test',
                monitor_peer=self.identity,root_claim=dict(claim),inputs_ready=True,ack_wall_s=10.001,
                original_snapshot=dict(image=dict(capture._pending[0]),info=dict(capture.info_messages[-1]),
                    decision=dict(wall_before_s=10.001,wall_after_s=10.001,sim_ns=1_010_000_000)),
                measurement_complete=True,completion=dict(completion))
            if damage=='foreign_peer':value['monitor_peer']=dict(self.identity,pid=99)
            elif damage=='generation_bool':value['generation']=True
            elif damage=='authority':value['motion_authority']=True
            elif damage=='claimed_original':value['root_claim']['image_received_wall_s']=10.000
            elif damage=='late':wall[0]=10.012
            elif damage=='decision_future':value['original_snapshot']['decision']['wall_after_s']=10.002
            elif damage=='missing_completion':value.pop('measurement_complete')
            elif damage=='completion_changed':value['completion']['completion_wall_s']=10.000
            elif damage=='original_hash':value['original_snapshot']['image']['payload_sha256']='c'*64
            return value
    capture.bind_measurement_monitor(Monitor(),epoch='entry',generation=7,session_id='test')
    with pytest.raises(PermissionError):
        capture._measurement_request('CALIBRATION_FRAME_COMPLETION',completion)
    assert capture._pending is not None
    with pytest.raises(ValueError):capture.check()
    assert capture._measurement_attempts[-1]['outcome']=='REFUSED'
    assert capture._measurement_attempts[-1]['ack_wall_s'] is None


def test_failed_measurement_retains_original_request_before_fault_callback(capture):
    wall=[10.001];capture.monotonic=lambda:wall[0]
    capture._image(image());capture._info(info());pending=capture._pending
    claim=dict(epoch='entry',generation=7,session_id='test',image_source_ns=10**9,
        info_source_ns=10**9,joint_source_ns=10**9,tf_source_ns=10**9,image_frame_id=capture.frame_id,
        payload_sha256=pending[0]['payload_sha256'],image_received_wall_s=10.001,info_received_wall_s=10.001)
    class Monitor:
        identity=dict(uid=1,pid=2,start_ticks=3)
        def request_runtime(self,request,**kwargs):
            wall[0]=10.012
            raise TimeoutError('timed out')
    observed=[]
    capture.port._head_fault_callback=lambda reason:observed.append(
        (reason,list(getattr(capture,'_measurement_attempts',[]))))
    capture.bind_measurement_monitor(Monitor(),epoch='entry',generation=7,session_id='test')
    with pytest.raises(TimeoutError,match='timed out'):
        capture._measurement_request('CALIBRATION_FRAME_INPUTS',claim)
    assert capture._pending is pending and capture.port._head_policy_binding_failed
    with pytest.raises(ValueError,match='HEAD_STOPPED_MEASUREMENT_REFUSED'):capture.check()
    attempts=getattr(capture,'_measurement_attempts',[])
    assert len(attempts)==1, 'failed RPC loses original operation/claim/clock context'
    attempt=attempts[0]
    assert attempt['operation']=='CALIBRATION_FRAME_INPUTS' and attempt['root_claim']==claim
    assert attempt['started_wall_s']==10.001 and attempt['ended_wall_s']==10.012
    assert attempt['outcome']=='REFUSED' and attempt['error_type']=='TimeoutError'
    assert attempt['ack_wall_s'] is None and attempt['inputs_ready'] is None
    assert observed==[('HEAD_STOPPED_MEASUREMENT_REFUSED',attempts)]
    claim['image_source_ns']=99
    assert attempt['root_claim']['image_source_ns']==10**9


@pytest.mark.parametrize('failure',['missing','late'])
def test_scheduled_main_progress_refusal_keeps_completed_original_without_refresh(capture,failure):
    wall=[10.001];capture.monotonic=lambda:wall[0]
    capture._image(image());capture._info(info());capture._started=True
    completion=dict(root_claim=dict(image_source_ns=10**9),ack_wall_s=10.001)
    def wait(timeout):
        assert timeout==.010 and not capture.port._lock._is_owned()
        # Ordinary observations do not consume the completion mailbox.
        capture.snapshot();assert capture._measurement_pending is completion
        if failure=='missing':return False
        wall[0]=10.012;capture.snapshot(consume_measurement=True);return True
    capture._measurement_consumed=SimpleNamespace(clear=lambda:None,set=lambda:None,wait=wait)
    with pytest.raises(ValueError,match='HEAD_STOPPED_MAIN_PROGRESS_DEADLINE'):
        capture._main_measurement_handoff(completion)
    assert capture.port._head_policy_binding_failed
    assert capture._measurement_pending is completion if failure=='missing' else capture._measurement_handoff is not None
    with pytest.raises(ValueError):capture.check()


def test_warm_boundary_carries_only_last32_original_infos(capture):
    for sequence in range(40):capture._info(info(1_000_000_000+sequence*100_000_000))
    expected=list(capture.info_messages)[-32:]
    capture.begin_capture()
    assert list(capture.info_messages)==expected
    capture._info(info(5_000_000_000))
    assert len(capture.info_messages)==33


@pytest.mark.parametrize('damage',['frame','size','encoding','step','bytes','source'])
def test_invalid_payload_is_retained_and_consumes_capture(capture,damage):
    msg=image()
    if damage=='frame':msg.header.frame_id='foreign_camera'
    elif damage=='size':msg.width=639
    elif damage=='encoding':msg.encoding='bgr8'
    elif damage=='step':msg.step=1919
    elif damage=='bytes':msg.data=b'bad'
    else:msg.header.stamp.sec=0
    capture._image(msg)
    assert capture.camera_messages[-1]['valid'] is False
    with pytest.raises(ValueError):capture.snapshot()


def test_capacity_one_drop_remains_an_original_failure(capture):
    capture._image(image());capture._image(image(1_100_000_000))
    assert len(capture.camera_messages)==2
    assert capture.events[-1]['event']=='IMAGE_DROPPED'
    with pytest.raises(ValueError,match='DROPPED'):capture.check()


def test_duplicate_source_never_refreshes_original_receipt(capture):
    capture._image(image());first=capture.camera_messages[-1].copy()
    capture.take_image();capture._image(image())
    assert capture.camera_messages[0]==first
    assert capture.camera_messages[-1]['valid'] is False
    with pytest.raises(ValueError):capture.check()


def test_clock_original_callback_time_is_not_decision_time(capture):
    msg=Clock();msg.clock.sec=1
    capture._clock(msg)
    assert capture.clock_messages[-1]['source_ns']==1_000_000_000
    assert capture.clock_messages[-1]['wall_s']==10.001
    capture._clock(msg)
    assert capture.clock_messages[-1]['valid'] is False


def test_invalid_camera_info_is_retained(capture):
    msg=info();msg.k[0]=float('nan')
    capture._info(msg)
    assert capture.info_messages[-1]['valid'] is False
    with pytest.raises(ValueError):capture.check()


def test_valid_ros_info_keeps_builtin_boolean_for_lossless_json(capture):
    capture._info(info())
    assert type(capture.info_messages[-1]['valid']) is bool
    assert json.loads(json.dumps(capture.info_messages[-1]))['valid'] is True


def test_pending_original_waits_for_exact_tf_before_admission(capture):
    capture._image(image());capture._info(info())
    capture.port._head_samples.append(capture.port._head_feedback.copy())
    original=capture._pending
    class Buffer:
        def can_transform(self,*args):return False
        def lookup_transform(self,*args):raise AssertionError('SDK_LOOKUP_BEFORE_TF_READY')
    class Detector:
        def detect(self,*args,**kwargs):raise AssertionError('CUDA_BEFORE_TF_READY')
    assert capture.infer(Detector(),Buffer(),session_id='test',attempt_id='test',stop_velocity_rad_s=.05) is None
    assert capture._pending is original
    assert capture._pending[0]['wall_s']==10.001


def declare(capture):
    capture.begin_capture()
    getattr(capture,'declare_window',lambda **kw:None)(start_ns=11_000_000_000,end_ns=31_000_000_000)


def test_export_after_predeclared_end_does_not_admit_or_drop_new_presence(capture):
    declare(capture)
    capture.monotonic=lambda:31.001
    capture._image(image());capture._image(image(1_100_000_000))
    capture.check()
    assert capture.take_image() is None
    assert [row['event'] for row in capture.events]==['IMAGE_UNADMITTED_PRESENCE']*2
    assert len(capture.camera_messages)==2


def test_post_end_presence_cannot_hide_unconsumed_in_window_exposure(capture):
    declare(capture)
    capture.monotonic=lambda:30.999;capture._image(image())
    capture.monotonic=lambda:31.001;capture._image(image(1_100_000_000))
    assert capture._pending[0]['source_ns']==1_000_000_000
    with pytest.raises(ValueError,match='UNCONSUMED'):
        getattr(capture,'finish_window',lambda:None)()


def test_camera_info_and_clock_forward_original_metadata_after_cache_release(capture):
    records=[]
    def sink(kind,record):
        assert not capture.port._lock._is_owned()
        records.append((kind,record.copy()))
        if kind=='INFO':record['k'][0]=-1.
    getattr(capture,'bind_original_sink',lambda sink:None)(sink)
    capture._image(image());capture._info(info())
    msg=Clock();msg.clock.sec=1;capture._clock(msg)
    assert [kind for kind,_ in records]==['IMAGE','INFO','CLOCK']
    assert all(record['wall_s']==10.001 and record['source_ns']==1_000_000_000 for _,record in records)
    assert capture.info_messages[-1]['k'][0]==415.


def test_original_sink_failure_consumes_capture_before_return(capture):
    def sink(kind,record):raise RuntimeError('writer unavailable')
    getattr(capture,'bind_original_sink',lambda sink:None)(sink)
    capture._info(info())
    with pytest.raises(ValueError,match='ORIGINAL_SINK_FAILED'):capture.check()


def test_failure_before_capture_boundary_cannot_be_cleared(capture):
    capture._image(image(0))
    with pytest.raises(ValueError):capture.begin_capture()


def test_declared_window_and_original_sink_cannot_be_rebound(capture):
    declare(capture)
    with pytest.raises(PermissionError):capture.declare_window(start_ns=12_000_000_000,end_ns=32_000_000_000)
    capture.bind_original_sink(lambda *a:None)
    with pytest.raises(PermissionError):capture.bind_original_sink(lambda *a:None)


def test_in_window_drop_and_post_window_invalidity_still_fail(capture):
    declare(capture);capture.monotonic=lambda:30.
    capture._image(image());capture._image(image(1_100_000_000))
    capture.monotonic=lambda:32.;capture._image(image(1_200_000_000))
    with pytest.raises(ValueError,match='DROPPED'):capture.finish_window()


def test_finished_window_cannot_replay_exposure_or_reopen(capture):
    declare(capture);capture.monotonic=lambda:32.;capture.finish_window()
    capture._image(image())
    assert capture.infer(None,None,session_id='test',attempt_id='test',stop_velocity_rad_s=.05) is None
    with pytest.raises(PermissionError):capture.finish_window()
    invalid=image(1_100_000_000);invalid.header.frame_id='foreign';capture._image(invalid)
    with pytest.raises(ValueError,match='INVALID'):capture.check()


def test_late_original_waits_for_next_exposure_before_window_is_declared():
    receipts=[10.,10.1,10.2]
    assert stopped_window_boundary(receipts,now_ns=10_270_000_000) is None
    receipts.append(10.3)
    assert stopped_window_boundary(receipts,now_ns=10_310_000_000)==10_350_000_000


def test_equal_midpoint_is_not_a_future_window_and_cannot_start_in_past():
    assert stopped_window_boundary([10.,10.1,10.2],now_ns=10_250_000_000) is None


def test_predeclared_window_phase_leaves_measured_stable_processing_margin():
    assert stopped_window_boundary([10.,10.1,10.2],now_ns=10_240_000_000,
        processing_margin_s=.06)==10_260_000_000
    assert stopped_window_boundary([10.,10.1,10.2],now_ns=10_270_000_000,
        processing_margin_s=.06) is None


@pytest.mark.parametrize('margin',[float('nan'),-.001,.1001])
def test_window_phase_cannot_hide_invalid_processing_or_extend_one_source_period(margin):
    with pytest.raises(ValueError,match='WINDOW_PHASE'):
        stopped_window_boundary([10.,10.1,10.2],now_ns=10_210_000_000,processing_margin_s=margin)



def finished_live_capture(capture):
    declare(capture);capture.monotonic=lambda:32.;capture.finish_window()
    originals=[];capture.bind_original_sink(lambda kind,record:originals.append((kind,record)))
    return originals


def test_live_handoff_preserves_sealed_history_and_original_clock_receipts(capture):
    originals=finished_live_capture(capture)
    capture.clock_messages=deque(maxlen=1)
    first=Clock();first.clock.sec=1;capture._clock(first)
    sealed=tuple(dict(x) for x in capture.clock_messages);received=[]
    capture.bind_live_sink(lambda kind,record,**kw:received.append((kind,record,kw)))
    for second in (2,3):
        msg=Clock();msg.clock.sec=second;capture._clock(msg)
    capture.check()
    assert tuple(capture.clock_messages)==sealed
    assert [row[1]['source_ns'] for row in received]==[2_000_000_000,3_000_000_000]
    assert all(row[1]['wall_s']==32. for row in received)
    assert len(originals)==3 and capture.strict is True
    assert capture._window==(11_000_000_000,31_000_000_000) and capture._window_finished


def test_live_handoff_delivers_new_rgb_info_without_replay_or_second_subscriber(capture):
    originals=finished_live_capture(capture)
    capture._image(image());capture._info(info())
    frozen=json.dumps(dict(camera=list(capture.camera_messages),info=list(capture.info_messages),
        events=list(capture.events)),sort_keys=True)
    received=[];subscriptions=tuple(capture.subscriptions)
    def sink(kind,record,*,payload=None):
        assert not capture.port._lock._is_owned()
        received.append((kind,record,payload))
        record['source_ns']=0
    capture.bind_live_sink(sink)
    assert received==[]
    msg=image(1_100_000_000);capture._image(msg);capture._info(info(1_100_000_000))
    assert [kind for kind,_,_ in received]==['IMAGE','INFO']
    assert received[0][2]==bytes(msg.data) and received[1][2] is None
    assert originals[-2][1]['source_ns']==1_100_000_000
    assert capture._last_camera['source_ns']==1_100_000_000
    assert frozen==json.dumps(dict(camera=list(capture.camera_messages),info=list(capture.info_messages),
        events=list(capture.events)),sort_keys=True)
    assert tuple(capture.subscriptions)==subscriptions
    assert capture.infer(None,None,session_id='test',attempt_id='test',stop_velocity_rad_s=.05) is None


@pytest.mark.parametrize('damage',['early','no_journal','failed','pending'])
def test_live_handoff_cannot_bypass_unfinished_or_failed_capture(capture,damage):
    if damage=='early':declare(capture)
    else:finished_live_capture(capture)
    if damage=='no_journal':capture._original_sink=None
    elif damage=='failed':capture._failure='HEAD_STOPPED_IMAGE_DROPPED'
    elif damage=='pending':capture._pending=({'source_ns':1},b'pending')
    with pytest.raises((PermissionError,ValueError)):capture.bind_live_sink(lambda *a,**k:None)


def test_live_handoff_cannot_rebind_or_clear_failure(capture):
    finished_live_capture(capture);capture.bind_live_sink(lambda *a,**k:None)
    with pytest.raises(PermissionError):capture.bind_live_sink(lambda *a,**k:None)
    invalid=image();invalid.encoding='bgr8';capture._image(invalid)
    with pytest.raises(ValueError):capture.bind_live_sink(lambda *a,**k:None)
    with pytest.raises(ValueError):capture.check()


@pytest.mark.parametrize('damage',['invalid_rgb','nonadvancing_clock','sink_failure'])
def test_live_invalidity_retains_original_and_faults_before_more_delivery(capture,damage):
    originals=finished_live_capture(capture);faults=[];received=[]
    capture.port._head_fault_callback=lambda reason:faults.append(reason)
    def sink(kind,record,**kw):
        if damage=='sink_failure':raise RuntimeError('live reader failed')
        received.append(kind)
    capture.bind_live_sink(sink)
    if damage=='invalid_rgb':
        msg=image();msg.encoding='bgr8';capture._image(msg)
    else:
        msg=Clock();msg.clock.sec=1;capture._clock(msg)
        if damage=='nonadvancing_clock':capture._clock(msg)
    assert faults and capture.port._head_policy_binding_failed
    assert originals[-1][1]['valid'] is (damage=='sink_failure')
    prior=len(received);capture._info(info())
    assert len(received)==prior
    with pytest.raises(ValueError):capture.check()


def test_callback_copied_before_live_binding_cannot_be_replayed_after_handoff(capture):
    declare(capture);capture.monotonic=lambda:32.;capture.finish_window()
    copied=threading.Event();release=threading.Event();originals=[]
    def journal(kind,record):
        originals.append((kind,record))
        if record['source_ns']==1_000_000_000:
            copied.set();assert release.wait(1.)
    capture.bind_original_sink(journal)
    msg=Clock();msg.clock.sec=1
    thread=threading.Thread(target=capture._clock,args=(msg,));thread.start()
    try:
        assert copied.wait(1.)
        delivered=[];capture.bind_live_sink(lambda kind,record,**kw:delivered.append(record))
    finally:release.set();thread.join(1.)
    assert not thread.is_alive() and delivered==[]
    msg.clock.sec=2;capture._clock(msg)
    assert len(delivered)==1 and delivered[0]['source_ns']==2_000_000_000
    assert len(originals)==2


def test_live_reader_failure_before_pixel_evidence_does_not_grant_inference(capture):
    finished_live_capture(capture);received=[];faults=[]
    capture.port._head_fault_callback=lambda reason:faults.append(reason)
    capture.bind_live_sink(lambda kind,record,**kw:received.append(record))
    def writer(*a,**kw):raise RuntimeError('owned pixel writer failed')
    capture.emit=writer;capture._image(image())
    assert received==[] and faults==['HEAD_STOPPED_EVIDENCE_FAILED']
    with pytest.raises(ValueError):capture.check()
