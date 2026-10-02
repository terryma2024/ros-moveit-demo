"""The primary consumes original shared inputs without a second sensor stream."""
import pytest
from test_act_head_monitor_ros import Node
from test_act_head_feedback_freshness import policy,sample
from so101_demo.adapters.act.ros_execution import RosControllerPort
from so101_demo.adapters.act.head_monitor_ros import HeadROSMonitor,_NoMotion


def shared():
    node=Node();events=[];faults=[]
    port=RosControllerPort(node,_NoMotion(),('neck_yaw_joint',),stop_velocity_rad_s=.002,max_age_s=.05,
        feedback_policy=policy(),monotonic=lambda:node.wall)
    port._feedback(sample())
    primary=HeadROSMonitor(node,epoch='attempt',generation=5,stop_velocity_rad_s=.002,stop_latency_s=.07,
        camera_max_age_s=.05,camera_frame_id='head_camera_frame',controller_port=port,
        emit=lambda event,**kw:events.append((event,kw)),fault_callback=lambda reason,wall:faults.append((reason,wall)),
        monotonic=lambda:node.wall)
    return node,port,primary,events,faults


def test_shared_primary_keeps_original_port_policy_and_one_joint_subscription():
    node,port,primary,_,_=shared()
    try:
        assert primary.port is port and primary._policy is port.feedback_policy
        topics=[row[1] for row in node.subscriptions]
        assert topics.count('/joint_states')==1
        assert not set(topics)&{'/head_camera/color','/head_camera/camera_info','/clock'}
    finally:primary.close(timeout_s=1.);port.close_head_io(timeout_s=1.)


def test_shared_camera_info_clock_keep_original_receipts_at_watchdog_admission():
    node,port,primary,events,faults=shared()
    try:
        primary.observe_original('CLOCK',dict(source_ns=1_000_000_000,wall_s=9.99,valid=True))
        primary.observe_original('IMAGE',dict(source_ns=1_000_000_000,wall_s=9.995,frame_id='head_camera_frame',valid=True))
        primary.observe_original('INFO',dict(source_ns=1_000_000_000,wall_s=9.996,frame_id='head_camera_frame',valid=True))
        assert primary._clock['wall_s']==9.99
        primary.executor_progress();primary.heartbeat(dict(wall_s=10.,executor_wall_s=10.,inference_deadline_wall_s=None))
        primary.activate()
        assert not faults and primary._camera['wall_s']==9.995 and primary._camera_watermark==1_000_000_000
        assert primary.port.feedback_snapshot()['wall_s']==10.
        assert primary.port is port
    finally:primary.close(timeout_s=1.);port.close_head_io(timeout_s=1.)


def test_shared_primary_callbacks_run_outside_original_feedback_cache():
    node,port,primary,_,_=shared();latches=[]
    try:
        def closed(reason):
            assert port._head_policy_binding_failed
            assert not port._lock._is_owned()
            latches.append(reason)
        primary.fault_callback=lambda reason,wall:closed(reason)
        assert port._head_fault_callback is not None
        port._head_fault_callback('original port asynchronous failure')
        assert primary.failed and latches==['original port asynchronous failure']
    finally:primary.close(timeout_s=1.);port.close_head_io(timeout_s=1.)


@pytest.mark.parametrize('kind,damage',[('IMAGE','frame'),('CLOCK','source'),('INFO','valid')])
def test_shared_invalid_original_latches_before_prearm(kind,damage):
    node,port,primary,_,faults=shared()
    record=dict(source_ns=1_000_000_000,wall_s=9.999,frame_id='head_camera_frame',valid=True)
    if damage=='frame':record['frame_id']='foreign'
    elif damage=='source':record['source_ns']=0
    else:record['valid']=False
    try:
        with pytest.raises(ValueError):primary.observe_original(kind,record)
        assert primary.failed and port._head_policy_binding_failed and faults
        assert not primary._active
    finally:primary.close(timeout_s=1.);port.close_head_io(timeout_s=1.)


def test_shared_observer_cannot_be_rebound_or_replace_original_fault_callback():
    node,port,primary,_,_=shared();callback=port._head_fault_callback
    try:
        with pytest.raises(ValueError):HeadROSMonitor(node,epoch='foreign',generation=6,
            stop_velocity_rad_s=.002,stop_latency_s=.07,camera_max_age_s=.05,camera_frame_id='head_camera_frame',
            controller_port=port,emit=lambda *a,**kw:None,fault_callback=lambda *a:None,monotonic=lambda:node.wall)
        assert port._head_fault_callback is callback
        assert len([row for row in node.subscriptions if row[1]=='/joint_states'])==1
    finally:primary.close(timeout_s=1.);port.close_head_io(timeout_s=1.)


def test_independent_cpu_observer_never_accepts_primary_injected_originals():
    from test_act_head_monitor_ros import observer
    _,cpu,_,_=observer()
    try:
        with pytest.raises(PermissionError,match='EXTERNAL_INPUT_FORBIDDEN'):
            cpu.observe_original('CLOCK',dict(source_ns=1_000_000_000,wall_s=9.999,valid=True))
        assert cpu._clock is None
    finally:cpu.close(timeout_s=1.)


def test_original_joint_sink_keeps_receipt_and_never_runs_inside_port_cache():
    node,port,primary,_,_=shared();records=[]
    def sink(kind,record):
        assert not port._lock._is_owned()
        records.append((kind,record.copy()))
        record['positions']=(99.,)
    try:
        getattr(port,'bind_head_original_sink',lambda sink:None)(sink)
        message=sample();message.header.stamp.nanosec=10_000_000
        port._feedback(message)
        assert len(records)==1 and records[0][0]=='JOINT'
        assert records[0][1]['wall_s']==10. and records[0][1]['source_ns']==1_010_000_000
        assert port._head_feedback['positions']!=(99.,)
    finally:primary.close(timeout_s=1.);port.close_head_io(timeout_s=1.)


def test_original_joint_sink_failure_latches_owned_fault_before_return():
    node,port,primary,_,faults=shared()
    def sink(kind,record):raise RuntimeError('owned journal unavailable')
    try:
        getattr(port,'bind_head_original_sink',lambda sink:None)(sink)
        message=sample();message.header.stamp.nanosec=10_000_000;port._feedback(message)
        assert port._head_policy_binding_failed and primary.failed and faults
    finally:primary.close(timeout_s=1.);port.close_head_io(timeout_s=1.)
