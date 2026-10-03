"""Inference claims must match CPU-owned originals and their absolute deadline."""
import hashlib
from concurrent.futures import Future

import pytest
from builtin_interfaces.msg import Time
from rosgraph_msgs.msg import Clock

from test_act_head_feedback_freshness import sample
from test_act_head_monitor_prearm import prepared, completed
from so101_demo.act.head_feedback import nanoseconds
from so101_demo.act.head_monitor_ipc import HeadMonitorCodec
from so101_demo.adapters.act.head_monitor_process import MonitorRuntimeProtocol


def ready():
    node,runtime,observer=prepared()
    observer._active=True;observer.camera_skew=.01
    observer.fault_callback=runtime.fault
    identity=dict(generation=5,incarnation='native',boot='boot')
    runtime.epoch.armed_ready(identity,identity)
    record=dict(epoch='attempt',generation=5,session_id='session',policy_sha256='a'*64,
        sequence=1,image_source_ns=10**9,info_source_ns=10**9,joint_source_ns=10**9,
        tf_source_ns=10**9,image_frame_id=observer.camera_frame,
        payload_sha256=hashlib.sha256(bytes(640*480*3)).hexdigest(),
        image_received_wall_s=10.,info_received_wall_s=10.,deadline_ns=10_050_000_000)
    return node,runtime,observer,record


def refresh(node,runtime,observer,wall):
    node.wall=wall;node.sim=1.+wall-10.
    observer.port._feedback(sample(node.sim))
    source=nanoseconds(node.sim)
    observer._on_clock(Clock(clock=Time(sec=source//10**9,nanosec=source%10**9)))
    observer.executor_progress()
    observer.heartbeat(dict(wall_s=wall,executor_wall_s=wall,inference_deadline_wall_s=None))
    runtime._watchdog_wall=wall


def delayed_original():
    node,runtime,observer,record=ready()
    refresh(node,runtime,observer,10.001)
    record.update(image_source_ns=1_001_000_000,info_source_ns=1_001_000_000,
        joint_source_ns=1_001_000_000,tf_source_ns=1_001_000_000,
        image_received_wall_s=10.001,info_received_wall_s=10.001,deadline_ns=10_051_000_000)
    return node,runtime,observer,record


def receive_original(observer,record,kind):
    from sensor_msgs.msg import Image,CameraInfo
    from std_msgs.msg import Header
    source=record['image_source_ns']
    header=Header(frame_id=observer.camera_frame,
        stamp=Time(sec=source//10**9,nanosec=source%10**9))
    if kind=='IMAGE':
        observer._on_image(Image(header=header,width=640,height=480,encoding='rgb8',step=1920,
            data=bytes(640*480*3)))
    else:
        observer._on_info(CameraInfo(header=header,width=640,height=480,
            k=[200.,0.,320.,0.,200.,240.,0.,0.,1.]))


@pytest.mark.parametrize('first',['IMAGE','INFO'])
def test_authenticated_inputs_wait_for_each_cpu_original_without_consuming_admission(tmp_path,first):
    node,runtime,observer,record=delayed_original()
    protocol=MonitorRuntimeProtocol(dict(epoch='attempt',generation=5,session_id='session',
        primary=runtime.primary),tmp_path)
    protocol._future=completed(runtime);protocol._policy_future=completed(True)
    scope=dict(secret=b'x'*32,epoch='attempt',generation=5,session_id='session')
    sender=HeadMonitorCodec(**scope,role='monitor');receiver=HeadMonitorCodec(**scope,role='primary')
    before=runtime._exposures.summary();polls=list(observer.watchdog_polls)
    def inputs():
        return receiver.decode(sender.encode(protocol.handle(dict(operation='EXPOSURE_INPUTS',exposure=record))))
    try:
        for received in (None,first,'INFO' if first=='IMAGE' else 'IMAGE'):
            if received:receive_original(observer,record,received)
            ack=inputs()
            assert ack['inputs_ready'] is (received is not None and received!=first)
            assert ack['motion_authority'] is False and ack['root_claim']==record
            assert ack['request']=='EXPOSURE_INPUTS' and ack['stage']=='ARMED_READY'
            assert runtime._exposures.summary()==before and not runtime.epoch.inventory
            assert list(observer.watchdog_polls)==polls and runtime._watchdog_wall==10.001
            assert not runtime.revoked
        admitted=runtime.exposure_admit(record)
        assert admitted['sequence']==1 and admitted['exposure_admitted']
        assert runtime.exposure_finish(completion(admitted,10.001))['exposure_finished']
    finally:observer.close(timeout_s=1.)


def test_original_arriving_after_inputs_snapshot_waits_for_next_original_decision(monkeypatch):
    node,runtime,observer,record=delayed_original()
    snapshot=observer.port.original_feedback_snapshot;calls=[]
    def arriving():
        original=snapshot();calls.append(True)
        if len(calls)==2:
            # The callback happens after the query copied its decision. Its
            # later original receipt must belong to a subsequent query.
            node.wall=10.002
            receive_original(observer,record,'INFO');receive_original(observer,record,'IMAGE')
        return original
    monkeypatch.setattr(observer.port,'original_feedback_snapshot',arriving)
    try:
        reply=runtime.exposure_inputs(record)
        assert reply['inputs_ready'] is False and not runtime.revoked
        assert observer._image_source==record['image_source_ns']
        monkeypatch.setattr(observer.port,'original_feedback_snapshot',snapshot)
        refresh(node,runtime,observer,10.002)
        reply=runtime.exposure_inputs(record)
        assert reply['inputs_ready'] is True
        assert runtime._exposures.summary()['sequence']==0
        assert runtime.exposure_admit(record)['deadline_ns']==10_051_000_000
    finally:observer.close(timeout_s=1.)


@pytest.mark.parametrize('damage',['future','payload','frame','receipt','deadline','extra','sequence',
    'received_missing','received_invalid','received_hash','info_missing','expired','stage','watchdog',
    'heartbeat','executor','clock','joint','revoked','overlap','old_source'])
def test_inputs_wait_never_hides_invalid_or_previously_received_original(damage):
    node,runtime,observer,record=delayed_original()
    if damage=='future':record['image_source_ns']+=1
    elif damage=='payload':record['payload_sha256']='bad'
    elif damage=='frame':record['image_frame_id']='other'
    elif damage=='receipt':record['image_received_wall_s']=10.002
    elif damage=='deadline':record['deadline_ns']+=1
    elif damage=='extra':record['extra']=True
    elif damage=='sequence':record['sequence']=True
    elif damage.startswith('received_'):
        receive_original(observer,record,'IMAGE')
        if damage=='received_missing':observer._images.clear()
        elif damage=='received_invalid':observer._images[record['image_source_ns']]['valid']=False
        else:observer._images[record['image_source_ns']]['payload_sha256']='b'*64
    elif damage=='info_missing':
        receive_original(observer,record,'INFO');observer._infos.pop(record['image_source_ns'])
    elif damage=='expired':refresh(node,runtime,observer,10.051)
    elif damage=='stage':runtime.epoch._stage='POLICY_READY'
    elif damage=='watchdog':runtime._watchdog_wall=9.99
    elif damage=='heartbeat':observer._primary['wall_s']=9.99
    elif damage=='executor':observer._executor_wall=9.99
    elif damage=='clock':observer._clock=None
    elif damage=='joint':observer.port._head_feedback['valid']=False
    elif damage=='revoked':runtime.fault('test',node.wall)
    elif damage=='overlap':
        receive_original(observer,record,'IMAGE');receive_original(observer,record,'INFO')
        runtime.exposure_admit(record)
    elif damage=='old_source':runtime._exposures._source_floor=record['image_source_ns']
    try:
        before=runtime._exposures.summary()
        with pytest.raises(PermissionError):runtime.exposure_inputs(record)
        assert runtime.revoked and runtime._exposures.summary()==before
    finally:observer.close(timeout_s=1.)


def completion(ack,wall=10.):
    return dict(exposure_sha256=ack['exposure_sha256'],sequence=ack['sequence'],
        image_source_ns=ack['image_source_ns'],completion_wall_s=wall,result_sha256='b'*64)


@pytest.mark.parametrize('root_receipt',[10.,10.002])
def test_authenticated_finished_exposure_discharges_only_its_exact_old_heartbeat_deadlines(root_receipt):
    node,runtime,observer,record=ready()
    record.update(image_received_wall_s=root_receipt,info_received_wall_s=root_receipt,
        deadline_ns=nanoseconds(root_receipt)+50_000_000)
    try:
        refresh(node,runtime,observer,10.003)
        ack=runtime.exposure_admit(record)
        refresh(node,runtime,observer,10.048)
        heartbeat=dict(wall_s=10.048,executor_wall_s=10.048,
            inference_deadline_wall_s=record['deadline_ns']*1e-9)
        # Preserve a real advancing heartbeat that already copied the deadline.
        heartbeat['wall_s']=10.0481;node.wall=10.0481
        observer.heartbeat(heartbeat)
        finished=runtime.exposure_finish(completion(ack,10.048))
        assert finished['deadline_discharge']['deadlines_ns']==sorted(set([ack['deadline_ns'],record['deadline_ns']]))
        for wall in [10.0501,10.0521]:
            node.wall=wall;node.sim=1.+wall-10.
            observer.port._feedback(sample(node.sim))
            source=nanoseconds(node.sim)
            observer._on_clock(Clock(clock=Time(sec=source//10**9,nanosec=source%10**9)))
            observer.executor_progress();observer.watchdog_polls.append(wall-.001)
            observer.poll()
            assert not runtime.revoked and not observer.failed
            assert observer._primary==heartbeat
        # A different uncompleted deadline still expires at its original time.
        node.wall=10.053
        observer.heartbeat(dict(wall_s=node.wall,executor_wall_s=node.wall,
            inference_deadline_wall_s=10.0525))
        observer.poll()
        assert runtime.revoked and observer._fault_wall==10.0525
    finally:observer.close(timeout_s=1.)


def test_polled_original_is_admitted_once_without_motion_or_new_watchdog_tick():
    _,runtime,observer,record=ready()
    try:
        assert not observer._images  # Existing observer consumed the pending pair.
        polls=list(observer.watchdog_polls)
        ack=runtime.exposure_admit(record)
        assert ack['exposure_admitted'] and ack['motion_authority'] is False
        assert ack['stage']=='ARMED_READY' and ack['deadline_ns']==record['deadline_ns']
        assert ack['original_snapshot']['image']['payload_sha256']==record['payload_sha256']
        assert ack['original_snapshot']['joint']['source_ns']==record['joint_source_ns']
        assert runtime._watchdog_wall==10. and list(observer.watchdog_polls)==polls
        result=runtime.exposure_finish(completion(ack))
        assert result['exposure_finished'] and result['result_sha256']=='b'*64
        assert not runtime.revoked and not runtime.epoch.inventory
        with pytest.raises(PermissionError):runtime.exposure_admit(dict(record,sequence=2))
        assert runtime.revoked
    finally:observer.close(timeout_s=1.)


@pytest.mark.parametrize('field,value',[
    ('epoch','other'),('generation',6),('generation',True),('session_id','other'),
    ('policy_sha256','c'*64),('sequence',2),('sequence',True),
    ('image_source_ns',10**9+1),('info_source_ns',10**9-1),
    ('joint_source_ns',10**9-1),('tf_source_ns',10**9+1),
    ('tf_source_ns',10**9-10_000_001),('image_frame_id','wrong'),
    ('payload_sha256','c'*64),('payload_sha256','A'*64),
    ('image_received_wall_s',10.001),('info_received_wall_s',float('nan')),
    ('deadline_ns',10_050_000_001),('deadline_ns',True),
])
def test_foreign_or_extended_claim_irreversibly_revokes(field,value):
    _,runtime,observer,record=ready()
    try:
        with pytest.raises(PermissionError):runtime.exposure_admit(dict(record,**{field:value}))
        assert runtime.revoked and observer.port._head_policy_binding_failed
    finally:observer.close(timeout_s=1.)


@pytest.mark.parametrize('damage',['prearm','policy','watchdog','clock','clock_future',
    'camera','info','joint','skew_missing','extra','overlap'])
def test_no_claim_can_replace_missing_or_stale_cpu_inputs(damage):
    node,runtime,observer,record=ready()
    if damage=='prearm':runtime.epoch._stage='POLICY_READY'
    elif damage=='policy':runtime._policy=None
    elif damage=='watchdog':runtime._watchdog_wall=9.989
    elif damage=='clock':observer._clock=None
    elif damage=='clock_future':observer._clock['source_ns']=10**9+1
    elif damage=='camera':observer._camera=None
    elif damage=='info':observer._infos.clear()
    elif damage=='joint':observer.port._head_samples.clear()
    elif damage=='skew_missing':observer.camera_skew=None
    elif damage=='extra':record['unexpected']=False
    try:
        if damage=='overlap':runtime.exposure_admit(record)
        with pytest.raises(PermissionError):runtime.exposure_admit(record)
        assert runtime.revoked
        if damage=='watchdog':assert runtime._fault['fault_wall_s']==pytest.approx(9.999)
    finally:observer.close(timeout_s=1.)


def test_independent_original_receipt_can_only_tighten_root_deadline():
    _,runtime,observer,record=ready()
    observer._camera['wall_s']=9.99
    try:
        ack=runtime.exposure_admit(record)
        assert ack['deadline_ns']==10_040_000_000
        assert ack['original_snapshot']['image']['wall_s']==9.99
        assert ack['root_claim']==record
    finally:observer.close(timeout_s=1.)


@pytest.mark.parametrize('field,value',[
    ('exposure_sha256','c'*64),('sequence',2),('sequence',True),
    ('image_source_ns',10**9+1),('completion_wall_s',9.999),
    ('completion_wall_s',10.051),('result_sha256','bad'),
])
def test_completion_is_bound_to_exact_claim_original_time_and_result(field,value):
    _,runtime,observer,record=ready()
    try:
        ack=runtime.exposure_admit(record)
        with pytest.raises(PermissionError):
            runtime.exposure_finish(dict(completion(ack),**{field:value}))
        assert runtime.revoked
    finally:observer.close(timeout_s=1.)


def test_fresh_current_joint_does_not_substitute_for_causal_exposure_joint():
    node,runtime,observer,record=ready()
    refresh(node,runtime,observer,10.02)
    try:
        ack=runtime.exposure_admit(record)
        assert ack['original_snapshot']['joint']['source_ns']==10**9
        assert ack['original_snapshot']['current_joint']['source_ns']==1_020_000_000
        assert runtime.exposure_finish(completion(ack,10.02))['exposure_finished']
    finally:observer.close(timeout_s=1.)


def test_irrelevant_history_copy_work_cannot_exhaust_original_admission_deadline():
    from collections.abc import Mapping
    import json
    node,runtime,observer,record=ready()
    causal=dict(observer.port._head_samples[-1])
    class HistoricalOriginal(Mapping):
        def __init__(self,value):self.value=value
        def __getitem__(self,key):return self.value[key]
        def __len__(self):return len(self.value)
        def __iter__(self):
            # Charge elapsed copy work to the original monotonic clock.
            # This is controlled latency, not an actual-host timing claim.
            node.wall+=.00002
            return iter(self.value)
    history=[HistoricalOriginal(dict(causal,source_ns=100_000_000+i*100_000,
        wall_s=9.0+i*.0001)) for i in range(3500)]
    observer.port._head_samples.clear();observer.port._head_samples.extend(history+[causal])
    try:
        ack=runtime.exposure_admit(record)
        assert ack['original_snapshot']['joint']==json.loads(json.dumps(causal))
        assert ack['ack_wall_s']<10.05 and not runtime.revoked
        assert len(observer.port._head_samples)==3501
    finally:observer.close(timeout_s=1.)


@pytest.mark.parametrize('expire_in_watchdog',[False,True])
def test_late_receipt_and_deadline_free_heartbeat_cannot_release_expired_claim(expire_in_watchdog):
    node,runtime,observer,record=ready()
    try:
        ack=runtime.exposure_admit(record)
        refresh(node,runtime,observer,10.051)
        if expire_in_watchdog:runtime._exposures.poll(node.wall)
        with pytest.raises(PermissionError):runtime.exposure_finish(completion(ack,10.04))
        assert runtime.revoked
        assert runtime._fault['fault_wall_s']==pytest.approx(10.05,abs=1e-12)
    finally:observer.close(timeout_s=1.)


def test_completion_cannot_be_reused_or_clear_new_claim():
    _,runtime,observer,record=ready()
    try:
        ack=runtime.exposure_admit(record);runtime.exposure_finish(completion(ack))
        with pytest.raises(PermissionError):runtime.exposure_finish(completion(ack))
        assert runtime.revoked
    finally:observer.close(timeout_s=1.)


def test_returned_ack_and_caller_claim_cannot_mutate_cpu_lease():
    _,runtime,observer,record=ready()
    try:
        ack=runtime.exposure_admit(record);done=completion(ack)
        record['deadline_ns']+=10**9;ack['deadline_ns']+=10**9
        ack['original_snapshot']['image']['wall_s']=20.
        ack['root_claim']['payload_sha256']='c'*64
        result=runtime.exposure_finish(done)
        assert result['deadline_ns']==10_050_000_000
    finally:observer.close(timeout_s=1.)


def test_owned_watchdog_expires_exposure_even_after_deadline_free_heartbeat(monkeypatch):
    from so101_demo.adapters.act import head_monitor_runtime as module
    node,runtime,observer,record=ready()
    try:
        runtime.exposure_admit(record);refresh(node,runtime,observer,10.051)
        original_poll=observer.poll
        def one_poll():
            original_poll();runtime._shutdown.set()
        monkeypatch.setattr(observer,'poll',one_poll)
        monkeypatch.setattr(module.time,'monotonic',lambda:node.wall)
        runtime._watchdog()
        assert runtime.revoked
        assert runtime._fault['reason']=='HEAD_MONITOR_EXPOSURE_DEADLINE'
        assert runtime._fault['fault_wall_s']==pytest.approx(10.05,abs=1e-12)
        runtime._exposures.poll(10.06)
        records=list(runtime._records.queue)
        assert sum(row['event']=='EXPOSURE_EXPIRED' for row in records)==1
        assert runtime._exposures.summary()['active']['deadline_ns']==10_050_000_000
    finally:observer.close(timeout_s=1.)


@pytest.mark.parametrize('damage',['hash','endian'])
def test_cpu_hash_comes_from_actual_original_image_bytes(damage):
    from sensor_msgs.msg import Image
    from std_msgs.msg import Header
    node,runtime,observer,record=ready()
    refresh(node,runtime,observer,10.001)
    header=Header(frame_id=observer.camera_frame,stamp=Time(sec=1,nanosec=1_000_000))
    data=bytearray(640*480*3);data[0]=1
    record.update(image_source_ns=1_001_000_000,info_source_ns=1_001_000_000,
        joint_source_ns=1_001_000_000,tf_source_ns=1_001_000_000,
        image_received_wall_s=node.wall,info_received_wall_s=node.wall,deadline_ns=10_051_000_000)
    from sensor_msgs.msg import CameraInfo
    try:
        observer._on_info(CameraInfo(header=header,width=640,height=480,k=[200.,0.,320.,0.,200.,240.,0.,0.,1.]))
        observer._on_image(Image(header=header,width=640,height=480,encoding='rgb8',step=1920,
            is_bigendian=1 if damage=='endian' else 0,data=bytes(data)))
        with pytest.raises(PermissionError):runtime.exposure_admit(record)
        assert runtime.revoked
    finally:observer.close(timeout_s=1.)


@pytest.mark.parametrize('pending',[False,True])
@pytest.mark.parametrize('operation',['EXPOSURE_INPUTS','EXPOSURE_ADMIT'])
def test_actual_protocol_and_authenticated_codec_route_admission_and_completion(tmp_path,pending,operation):
    _,runtime,observer,record=ready()
    config=dict(epoch='attempt',generation=5,session_id='session',primary=runtime.primary)
    protocol=MonitorRuntimeProtocol(config,tmp_path)
    protocol._future=completed(runtime);protocol._policy_future=Future() if pending else completed(True)
    scope=dict(secret=b'x'*32,epoch='attempt',generation=5,session_id='session')
    sender=HeadMonitorCodec(**scope,role='monitor');receiver=HeadMonitorCodec(**scope,role='primary')
    try:
        request=dict(operation=operation,exposure=record)
        if pending:
            with pytest.raises(PermissionError,match='POLICY_ACK_REQUIRED'):protocol.handle(request)
            return
        ack=receiver.decode(sender.encode(protocol.handle(request)))
        if operation=='EXPOSURE_INPUTS':
            assert ack['request']==operation and ack['inputs_ready'] is True
            assert runtime._exposures.summary()['active'] is None
            ack=protocol.handle(dict(operation='EXPOSURE_ADMIT',exposure=record))
        assert ack['request']=='EXPOSURE_ADMIT' and ack['exposure_admitted']
        result=protocol.handle(dict(operation='EXPOSURE_FINISH',completion=completion(ack)))
        reply=receiver.decode(sender.encode(result))
        assert reply['request']=='EXPOSURE_FINISH' and reply['exposure_finished']
        assert reply['motion_authority'] is False
    finally:observer.close(timeout_s=1.)
