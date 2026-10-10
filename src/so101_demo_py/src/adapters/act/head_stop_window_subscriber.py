"""The stop-window subscriber: its own node, its own executor thread, reliable depth-64 QoS.

It subscribes ``/neck_controller/controller_state`` and feeds every sample to a
:class:`so101_demo.act.head_stop_window.StopWindow`. It shares nothing with the Head runtime's
executor, so a stalled runtime callback cannot delay the samples and a stalled subscriber cannot
delay the runtime. The owner calls :meth:`void` when it sends a goal.
"""

import threading
import time

from so101_demo.act import head_neck_limits as limits
from so101_demo.act.head_stop_window import StopWindow

TOPIC = '/neck_controller/controller_state'
NECK_JOINT = 'neck_yaw_joint'


def _first(values):
    try:
        return values[0]
    except (IndexError, TypeError):
        return None


class StopWindowSubscriber:
    def __init__(self, *, context, node_name='head_stop_window', topic=TOPIC, window=None,
                 monotonic_ns=time.monotonic_ns, on_complete=None):
        if not callable(monotonic_ns) or (on_complete is not None and not callable(on_complete)):
            raise ValueError('STOP_WINDOW_SUBSCRIBER_CONFIG_INVALID')
        self.context, self.node_name, self.topic = context, node_name, topic
        self._window = StopWindow() if window is None else window
        self._monotonic_ns = monotonic_ns
        self._on_complete = on_complete
        self._lock = threading.Lock()
        self._started = False
        self._stop = threading.Event()
        self._receipt = None
        self.node = self.executor = self.thread = self._subscription = None
        self.callback_thread_names = set()
        self._floor_sim_ns = None
        self._runs_taken = 0
        self.below_floor = 0
        self.received = 0
        self.callback_errors = []

    # ---- lifecycle -----------------------------------------------------------------------

    def start(self):
        with self._lock:
            if self._started:
                raise PermissionError('STOP_WINDOW_ALREADY_STARTED')
            self._started = True
        from control_msgs.msg import JointTrajectoryControllerState
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.node import Node
        from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
        self.node = Node(self.node_name, context=self.context)
        qos = QoSProfile(depth=limits.STOP_WINDOW_QOS_DEPTH, history=HistoryPolicy.KEEP_LAST,
                         reliability=ReliabilityPolicy.RELIABLE)
        self._subscription = self.node.create_subscription(
            JointTrajectoryControllerState, self.topic, self._callback, qos)
        self.executor = SingleThreadedExecutor(context=self.context)
        self.executor.add_node(self.node)
        self.thread = threading.Thread(target=self._spin, name='head-stop-window', daemon=True)
        self.thread.start()

    def _spin(self):
        try:
            while self.context.ok() and not self._stop.is_set():
                self.executor.spin_once(timeout_sec=.05)
        except Exception as error:  # a dead subscriber is visible through the snapshot
            self.callback_errors.append(f'{type(error).__name__}: {error}'[:200])

    def stop(self, timeout_s=1.):
        with self._lock:
            if self._receipt is not None:
                return dict(self._receipt)
        self._stop.set()
        if self.thread is not None:
            self.thread.join(timeout_s)
        alive = self.thread is not None and self.thread.is_alive()
        destroyed = False
        if not alive and self.node is not None:
            try:
                self.executor.remove_node(self.node)
            except Exception:
                pass
            self.node.destroy_node()
            self.executor.shutdown(timeout_sec=0.)
            destroyed = True
        receipt = dict(thread_alive=alive, node_destroyed=destroyed or self.node is None,
                       received=self.received, callback_errors=list(self.callback_errors))
        with self._lock:
            self._receipt = receipt
        return dict(receipt)

    # ---- samples -------------------------------------------------------------------------

    def _callback(self, message):
        received_ns = self._monotonic_ns()
        self.callback_thread_names.add(threading.current_thread().name)
        try:
            stamp = message.header.stamp
            sim_ns = int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)
            valid = list(message.joint_names) == [NECK_JOINT]
            sample = dict(
                sim_ns=sim_ns, receive_mono_ns=received_ns,
                feedback_velocity=_first(message.feedback.velocities),
                reference_velocity=_first(message.reference.velocities),
                reference_position=_first(message.reference.positions))
            if not valid:
                sample['sim_ns'] = None
            with self._lock:
                self.received += 1
                if (self._floor_sim_ns is not None and valid and type(sim_ns) is int
                        and sim_ns <= self._floor_sim_ns):
                    self.below_floor += 1
                    return
                done = self._window.observe(now_mono_ns=self._monotonic_ns(), **sample)
            if done is not None and self._on_complete is not None:
                self._on_complete(done)
        except Exception as error:
            self.callback_errors.append(f'{type(error).__name__}: {error}'[:200])

    # ---- owner interface -----------------------------------------------------------------

    @property
    def qos_profile(self):
        return self._subscription.qos_profile

    @property
    def completed(self):
        with self._lock:
            return self._window.completed

    def wait_completed(self, timeout_s):
        deadline = time.monotonic() + timeout_s
        while True:
            done = self.completed
            if done is not None or time.monotonic() >= deadline:
                return done
            time.sleep(.005)

    def void(self, reason):
        with self._lock:
            self._window.void(reason)

    def flush_run(self):
        """Close the quiet run in progress so that :meth:`take_runs` reports it."""
        with self._lock:
            self._window.flush_run()

    def take_runs(self):
        """The closed quiet runs (>= 51 samples) not handed out before."""
        with self._lock:
            runs = self._window.runs[self._runs_taken:]
            self._runs_taken = len(self._window.runs)
            return [dict(run) for run in runs]

    def rearm(self, floor_sim_ns=None):
        """Forget the latched window; samples stamped <= ``floor_sim_ns`` no longer count."""
        with self._lock:
            self._window.rearm()
            self._floor_sim_ns = floor_sim_ns

    def snapshot(self):
        with self._lock:
            return dict(resets=dict(self._window.resets), voids=list(self._window.voids),
                        pending=self._window.pending_count, observed=self._window.observed,
                        received=self.received, below_floor=self.below_floor,
                        completed=self._window.completed,
                        callback_errors=list(self.callback_errors))
