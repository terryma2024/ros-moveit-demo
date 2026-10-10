"""The stop-window subscriber: own node, own executor thread, reliable depth-64 controller_state."""

import threading
import time

import pytest
import rclpy
from builtin_interfaces.msg import Time
from control_msgs.msg import JointTrajectoryControllerState
from rclpy.context import Context
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from trajectory_msgs.msg import JointTrajectoryPoint

from so101_demo.act.head_neck_limits import STOP_WINDOW_QOS_DEPTH, STOP_WINDOW_STEP_NS
from so101_demo.adapters.act.head_stop_window_subscriber import StopWindowSubscriber

TOPIC = '/neck_controller/controller_state'
BASE_SIM = 7_000_000_000


class Rig:
    def __init__(self):
        self.context = Context()
        rclpy.init(context=self.context)
        self.node = rclpy.create_node('stop_window_test_publisher', context=self.context)
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        self.publisher = self.node.create_publisher(JointTrajectoryControllerState, TOPIC, qos)
        self.subscriber = None

    def message(self, sim_ns, *, fb=0.0, ref=0.0, position=0.3, velocities=True, joints=('neck_yaw_joint',)):
        message = JointTrajectoryControllerState()
        message.header.stamp = Time(sec=sim_ns // 10**9, nanosec=sim_ns % 10**9)
        message.joint_names = list(joints)
        for field, velocity in (('reference', ref), ('feedback', fb)):
            point = JointTrajectoryPoint(positions=[position])
            if velocities:
                point.velocities = [velocity]
            setattr(message, field, point)
        return message

    def publish(self, first, count, **keywords):
        # paced like the controller (a burst above the subscriber's depth would be lost by design)
        for index in range(first, first + count):
            self.publisher.publish(self.message(BASE_SIM + index * STOP_WINDOW_STEP_NS, **keywords))
            time.sleep(.001)

    def close(self):
        if self.subscriber is not None:
            self.subscriber.stop()
        self.node.destroy_node()
        self.context.shutdown()


@pytest.fixture
def rig(isolated_ros_domain):
    value = Rig()
    try:
        yield value
    finally:
        value.close()


def started(rig, **keywords):
    rig.subscriber = StopWindowSubscriber(context=rig.context, **keywords)
    rig.subscriber.start()
    deadline = time.monotonic() + 5.
    while rig.publisher.get_subscription_count() < 1:
        assert time.monotonic() < deadline, 'subscriber never matched'
        time.sleep(.01)
    return rig.subscriber


def wait_for(predicate, timeout=5.):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(.01)
    return False


def test_51_published_quiet_samples_complete_the_window_on_the_subscribers_own_thread(rig):
    subscriber = started(rig)
    rig.publish(0, 51)
    assert wait_for(lambda: subscriber.completed is not None)
    done = subscriber.completed
    assert done['n'] == 51 and done['first_sim_ns'] == BASE_SIM
    assert done['last_sim_ns'] == BASE_SIM + 50 * STOP_WINDOW_STEP_NS
    assert subscriber.thread.name == 'head-stop-window'
    assert subscriber.thread is not threading.current_thread()
    assert subscriber.callback_thread_names == {'head-stop-window'}


def test_the_subscription_is_reliable_with_depth_64_on_its_own_node(rig):
    subscriber = started(rig)
    info = rig.node.get_publishers_info_by_topic(TOPIC)
    assert info, 'publisher side sees its own endpoint'
    subs = rig.node.get_subscriptions_info_by_topic(TOPIC)
    assert len(subs) == 1
    assert subs[0].node_name == subscriber.node_name != 'stop_window_test_publisher'
    # the graph endpoint info does not carry depth (rmw reports 0); the subscription itself does
    assert subscriber.qos_profile.depth == STOP_WINDOW_QOS_DEPTH == 64
    assert subscriber.qos_profile.history == HistoryPolicy.KEEP_LAST
    assert subs[0].qos_profile.reliability == ReliabilityPolicy.RELIABLE


def test_a_gap_in_the_sim_stamps_restarts_the_window(rig):
    subscriber = started(rig)
    rig.publish(0, 30)
    rig.publish(32, 30)  # two samples missing: 4 ms jump after sample 29
    assert wait_for(lambda: subscriber.snapshot()['resets'].get('SIM_TIME_GAP') == 1)
    assert subscriber.completed is None
    rig.publish(62, 21)
    assert wait_for(lambda: subscriber.completed is not None)
    assert subscriber.completed['first_sim_ns'] == BASE_SIM + 32 * STOP_WINDOW_STEP_NS


def test_a_moving_sample_restarts_the_window(rig):
    subscriber = started(rig)
    rig.publish(0, 40)
    rig.publish(40, 1, fb=0.05)
    assert wait_for(lambda: subscriber.snapshot()['resets'].get('VELOCITY') == 1)
    assert subscriber.completed is None


def test_missing_velocity_arrays_or_a_foreign_joint_are_invalid_samples(rig):
    subscriber = started(rig)
    rig.publish(0, 3, velocities=False)
    rig.publish(3, 3, joints=('other_joint',))
    assert wait_for(lambda: subscriber.snapshot()['resets'].get('INVALID_SAMPLE') == 6)
    assert subscriber.completed is None


def test_void_restarts_collection_and_rearm_forgets_the_latched_window(rig):
    subscriber = started(rig)
    rig.publish(0, 51)
    assert wait_for(lambda: subscriber.completed is not None)
    subscriber.rearm()
    assert subscriber.completed is None
    rig.publish(51, 30)
    assert wait_for(lambda: subscriber.snapshot()['pending'] == 30)
    subscriber.void('GOAL_SENT')
    assert subscriber.snapshot()['pending'] == 0 and subscriber.snapshot()['voids'] == ['GOAL_SENT']
    rig.publish(81, 51)
    assert wait_for(lambda: subscriber.completed is not None)
    assert subscriber.completed['first_sim_ns'] == BASE_SIM + 81 * STOP_WINDOW_STEP_NS


def test_wait_completed_returns_the_window_or_none_at_the_deadline(rig):
    subscriber = started(rig)
    assert subscriber.wait_completed(.05) is None
    rig.publish(0, 51)
    assert subscriber.wait_completed(5.)['n'] == 51


def test_stop_joins_the_thread_destroys_the_node_and_is_idempotent(rig):
    subscriber = started(rig)
    receipt = subscriber.stop()
    assert receipt['thread_alive'] is False and receipt['node_destroyed'] is True
    assert not subscriber.thread.is_alive()
    assert rig.node.get_subscriptions_info_by_topic(TOPIC) == []
    assert subscriber.stop() == receipt


def test_start_twice_is_refused(rig):
    subscriber = started(rig)
    with pytest.raises(PermissionError, match='STOP_WINDOW_ALREADY_STARTED'):
        subscriber.start()


def test_rearm_with_a_floor_ignores_samples_stamped_at_or_below_it(rig):
    subscriber = started(rig)
    rig.publish(0, 51)
    assert wait_for(lambda: subscriber.completed is not None)
    floor = BASE_SIM + 60 * STOP_WINDOW_STEP_NS
    subscriber.rearm(floor_sim_ns=floor)
    rig.publish(51, 61)  # indices 51..111; index 60 is the floor itself
    assert wait_for(lambda: subscriber.completed is not None)
    assert subscriber.completed['first_sim_ns'] == floor + STOP_WINDOW_STEP_NS
    assert subscriber.snapshot()['below_floor'] == 10  # indices 51..60


def test_rearm_without_a_floor_clears_an_earlier_floor(rig):
    subscriber = started(rig)
    subscriber.rearm(floor_sim_ns=BASE_SIM + 1000 * STOP_WINDOW_STEP_NS)
    subscriber.rearm()
    rig.publish(0, 51)
    assert wait_for(lambda: subscriber.completed is not None)


def test_take_runs_hands_out_each_closed_run_once_and_flush_closes_the_open_one(rig):
    subscriber = started(rig)
    rig.publish(0, 60)
    rig.publish(60, 1, fb=0.5)  # ends the first run (60 samples)
    rig.publish(61, 70)
    assert wait_for(lambda: subscriber.snapshot()['observed'] == 131)
    first = subscriber.take_runs()
    assert [run['n'] for run in first] == [60]
    assert subscriber.take_runs() == []
    subscriber.flush_run()
    second = subscriber.take_runs()
    assert [run['n'] for run in second] == [70]
    assert second[0]['first_sim_ns'] == BASE_SIM + 61 * STOP_WINDOW_STEP_NS
