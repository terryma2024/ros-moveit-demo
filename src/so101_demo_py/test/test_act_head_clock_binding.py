"""Actual rclpy Clock ownership and receipt ordering; no simulator or motion."""
from types import SimpleNamespace
import pytest
import rclpy
from rclpy.context import Context
from rclpy.node import Node
from rclpy.parameter import Parameter
from rosgraph_msgs.msg import Clock
from rclpy.qos import qos_profile_sensor_data

try:
    from so101_demo.adapters.act.head_clock_binding import bind_head_clock
except ModuleNotFoundError:
    def bind_head_clock(node,observe,*,monotonic):
        # The pre-fix production boundary is an independent subscription.
        return node.create_subscription(Clock,'/clock',lambda msg:observe(msg,received_wall_s=monotonic()),qos_profile_sensor_data)


@pytest.fixture
def node():
    ctx=Context();rclpy.init(context=ctx)
    value=Node('controlled_head_clock',context=ctx,parameter_overrides=[Parameter('use_sim_time',value=True)])
    try:yield value
    finally:value.destroy_node();ctx.shutdown()


def test_single_actual_timesource_clock_updates_before_original_visibility(node):
    original=node._time_source._clock_sub;before_qos=original.qos_profile;seen=[]
    def observe(msg,*,received_wall_s):
        seen.append((msg,node.get_clock().now().nanoseconds,received_wall_s))
    sub=bind_head_clock(node,observe,monotonic=lambda:17.)
    msg=Clock();msg.clock.sec=3;msg.clock.nanosec=2
    sub.callback(msg)
    assert seen==[(msg,3_000_000_002,17.)]
    assert sub is original and sub.qos_profile==before_qos
    assert len([s for s in node.subscriptions if s.topic_name=='/clock'])==1


def test_existing_subscription_cannot_be_rebound_or_hide_originals(node):
    seen=[]
    sub=bind_head_clock(node,lambda msg,**kw:seen.append((msg,kw)),monotonic=lambda:18.)
    with pytest.raises(PermissionError,match='HEAD_CLOCK_BINDING'):
        bind_head_clock(node,lambda *args,**kw:None,monotonic=lambda:19.)
    msg=Clock();msg.clock.sec=4;sub.callback(msg)
    assert seen==[(msg,dict(received_wall_s=18.))]


def test_inactive_timesource_cannot_invent_a_clock_subscription(node):
    node.set_parameters([Parameter('use_sim_time',value=False)])
    with pytest.raises(PermissionError,match='HEAD_CLOCK_BINDING'):
        bind_head_clock(node,lambda *args,**kw:None,monotonic=lambda:1.)
    assert not [s for s in node.subscriptions if s.topic_name=='/clock']

@pytest.mark.parametrize('component',['stopped','local'])
def test_component_reuses_timesource_callback_with_one_clock_subscription(node,component):
    import threading
    from collections import deque
    if component=='stopped':
        from so101_demo.adapters.act.head_stopped_capture import StoppedHeadCapture
        port=SimpleNamespace(_lock=threading.RLock(),_head_samples=deque(),_head_feedback=None)
        observer=StoppedHeadCapture(node,port,frame_id='head_camera_frame',monotonic=lambda:20.)
        read=lambda:observer.clock_messages[-1]
    else:
        from rclpy.action import ActionClient
        from control_msgs.action import FollowJointTrajectory
        from so101_demo.adapters.act.ros_execution import RosControllerPort
        from so101_demo.adapters.act.head_local_observer import HeadLocalObserver
        from so101_demo.adapters.act.head_stopped_capture import StoppedHeadCapture
        from so101_demo.act.head_feedback import FeedbackPolicy
        from test_act_head_local_observer import simulation_policy, local_state
        policy = simulation_policy()
        client = ActionClient(node, FollowJointTrajectory,
                              '/neck_controller/follow_joint_trajectory')
        port = RosControllerPort(node, client, ('neck_yaw_joint',), max_age_s=.05,
            stop_velocity_rad_s=.002, monotonic=lambda:20.,
            feedback_policy=FeedbackPolicy.parse(policy.feedback_values(), simulation_policy=policy))
        observer = HeadLocalObserver(node, port, local_state(policy), policy=policy,
            camera_frame='head_camera_frame', monotonic=lambda:20., bind_port_sink=False)
        capture = StoppedHeadCapture(node, port, frame_id='head_camera_frame', monotonic=lambda:20.)
        capture.bind_original_sink(observer.observe_original)
        read = lambda:observer._clock
    try:
        assert len([s for s in node.subscriptions if s.topic_name=='/clock'])==1
        msg=Clock();msg.clock.sec=5;node._time_source._clock_sub.callback(msg)
        assert read()['source_ns']==node.get_clock().now().nanoseconds==5_000_000_000
        assert read()['wall_s']==20.
    finally:
        if component=='local':
            observer.close();port.close_head_io(timeout_s=1.)


def test_binding_after_executor_attachment_is_refused(node):
    from rclpy.executors import SingleThreadedExecutor
    executor=SingleThreadedExecutor(context=node.context);executor.add_node(node)
    original=node._time_source._clock_sub.callback
    try:
        with pytest.raises(PermissionError,match='HEAD_CLOCK_BINDING'):
            bind_head_clock(node,lambda *args,**kw:None,monotonic=lambda:1.)
        assert node._time_source._clock_sub.callback==original
    finally:executor.remove_node(node);executor.shutdown()


@pytest.mark.parametrize('receipt',[float('nan'),float('inf'),-1.,True])
def test_invalid_original_receipt_cannot_update_clock_or_forward(node,receipt):
    seen=[]
    sub=bind_head_clock(node,lambda *args,**kw:seen.append((args,kw)),monotonic=lambda:receipt)
    msg=Clock();msg.clock.sec=5
    with pytest.raises(ValueError,match='HEAD_CLOCK_BINDING_RECEIPT_INVALID'):sub.callback(msg)
    assert node.get_clock().now().nanoseconds==0 and seen==[]
