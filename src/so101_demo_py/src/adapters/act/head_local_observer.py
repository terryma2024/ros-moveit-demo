"""Shared-original local ROS observer for the file-protocol Head runtime.

It observes the existing original metadata (CLOCK/IMAGE/INFO/JOINT) delivered by
the one shared node/controller port, keeps bounded latest/history copies without
manufacturing receipt, source or sequence clocks, and issues real GetResult and
CancelGoal service calls for exact original UUIDs -- including UUIDs whose
acceptance is still UNKNOWN and that therefore have no goal handle.

This module has no monitor process, monitor epoch, monitor RPC/socket, heartbeat
or per-action ACK lifecycle. It never creates a SendGoal client and never grants
motion. The physical-stop predicate remains the controller port's own.
"""

import copy
from collections import deque
import math
import threading
import uuid

from action_msgs.msg import GoalStatusArray
from action_msgs.srv import CancelGoal
from control_msgs.action import FollowJointTrajectory
from unique_identifier_msgs.msg import UUID
from rclpy.qos import qos_profile_sensor_data

from so101_demo.act.head_evidence_identity import digest
from so101_demo.act.head_feedback import decision_clocks
from so101_demo.act.head_local_state import HeadLocalState
from so101_demo.act.head_simulation_policy import HeadSimulationPolicy
from .ros_execution import RosControllerPort, _copy_current_original_candidates


_ACTION = '/neck_controller/follow_joint_trajectory/_action/'
_KINDS = ('CLOCK', 'IMAGE', 'INFO', 'JOINT')
_HISTORY = 32
_TERMINAL = (4, 5, 6)


class HeadLocalObserver:
    """Retain originals and own the actual action status/cancel/result boundary."""

    def __init__(self, node, port, local_state, *, policy, camera_frame, fault_callback=None,
                 sink=None, emit=None, monotonic=None, bind_port_sink=True):
        import time

        if (type(port) is not RosControllerPort or port.node is not node
                or port.names != ('neck_yaw_joint',)
                or type(local_state) is not HeadLocalState
                or type(policy) is not HeadSimulationPolicy
                or type(camera_frame) is not str or not camera_frame):
            raise ValueError('HEAD_LOCAL_OBSERVER_CONFIG_INVALID')
        bound = port.feedback_policy
        if (bound is None or port._head_policy_binding_failed
                or bound._bound_simulation_policy is not policy
                or local_state.scope['policy_sha256'] != digest(policy.readback())):
            raise PermissionError('HEAD_LOCAL_OBSERVER_POLICY_MISMATCH')
        if fault_callback is not None and not callable(fault_callback):
            raise ValueError('HEAD_LOCAL_OBSERVER_FAULT_CALLBACK_INVALID')
        if sink is not None and not callable(sink):
            raise ValueError('HEAD_LOCAL_OBSERVER_SINK_INVALID')
        if emit is not None and not callable(emit):
            raise ValueError('HEAD_LOCAL_OBSERVER_EMIT_INVALID')
        if monotonic is not None and not callable(monotonic):
            raise ValueError('HEAD_LOCAL_OBSERVER_CLOCK_INVALID')
        if type(bind_port_sink) is not bool:
            raise ValueError('HEAD_LOCAL_OBSERVER_PORT_SINK_INVALID')
        self.node = node
        self.port = port
        self.local_state = local_state
        self.policy = policy
        self.camera_frame = camera_frame
        self.monotonic = time.monotonic if monotonic is None else monotonic
        self._sink = sink
        self._emit = emit
        self._fault_callback = fault_callback
        self._fault_callback_error = None
        self.failed = False
        self._fault_reason = None
        self._lock = threading.Lock()
        self._closed = False
        self._close_lock = threading.Lock()
        self._close_receipt = None
        self._clock = None
        self._clock_source_ns = None
        self._image = None
        self._info = None
        self._image_source_ns = None
        self._info_source_ns = None
        self._image_source_wall_s = None
        self._images = {}
        self._infos = {}
        self._joint = None
        self._joint_history = deque(maxlen=2)
        self._joint_count = 0
        self._action_status = {}
        self._outstanding = {}
        self.service_names = (_ACTION + 'get_result', _ACTION + 'cancel_goal')
        self._result_client = node.create_client(
            FollowJointTrajectory.Impl.GetResultService, self.service_names[0])
        self._cancel_client = node.create_client(CancelGoal, self.service_names[1])
        self.subscriptions = [node.create_subscription(
            GoalStatusArray, _ACTION + 'status', self._status, qos_profile_sensor_data)]
        # The shared port already owns the JOINT subscription and its receipt
        # clock; this observer only receives the original it routed after the
        # cache lock, exactly as the frozen original callbacks do.
        if bind_port_sink:
            # A composing router may own the single port sink instead; then it
            # forwards the same originals to this observer.
            port.bind_head_original_sink(self.observe_original)

    # ---- ownership and lifecycle -------------------------------------------

    @property
    def closed(self):
        return self._closed

    @property
    def camera_age(self):
        """Frozen camera admission age; the exposure entry must agree with it."""
        return self.policy.perception_max_age_s

    @property
    def _simulation_policy(self):
        """The one frozen local policy object; there is no monitor-owned copy."""
        return self.policy

    def bind_fault_callback(self, callback):
        if not callable(callback):
            raise ValueError('HEAD_LOCAL_OBSERVER_FAULT_CALLBACK_INVALID')
        with self._lock:
            if self._closed:
                raise PermissionError('HEAD_LOCAL_OBSERVER_CLOSED')
            if self._fault_callback is not None and self._fault_callback != callback:
                raise PermissionError('HEAD_LOCAL_OBSERVER_FAULT_CALLBACK_REBOUND')
            self._fault_callback = callback

    def fault(self, reason):
        """Request admission closure from this observer (router retirement path)."""
        if type(reason) is not str or not reason:
            raise ValueError('HEAD_LOCAL_OBSERVER_FAULT_INVALID')
        return self._invalidate(reason)

    def _invalidate(self, reason, *, token=None):
        """Latch the first immutable fault before diagnostics, sink or native work."""
        if token is None:
            token = self.local_state.latch_fault(reason)
        self.failed = True
        self._fault_reason = reason
        with self._lock:
            self._closed_admission = True
        if token is not None:
            try:
                self.local_state.finish_fault(token, {'reason': reason})
            except Exception:
                pass
        if self._fault_callback is not None:
            try:
                self._fault_callback(reason)
            except Exception as error:
                self._fault_callback_error = type(error).__name__
        try:
            if self._sink is not None:
                self._record(reason, {'reason': reason, 'kind': 'OBSERVER_INVALID'})
        except Exception:
            pass
        return reason

    def _record(self, kind, record):
        if self._sink is None:
            return None
        return self._sink(kind, record, None)

    def _emit_event(self, event, fields):
        if self._emit is None:
            return
        try:
            self._emit(event, **fields)
        except Exception:
            pass

    # ---- originals ---------------------------------------------------------

    @staticmethod
    def _original_clock(record):
        wall_s = record.get('wall_s')
        source_ns = record.get('source_ns')
        if (type(source_ns) is not int or source_ns < 0
                or type(wall_s) not in (int, float) or not math.isfinite(wall_s) or wall_s < 0
                or type(record.get('valid')) is not bool):
            return None
        return wall_s, source_ns

    def observe_original(self, kind, record):
        """Consume one routed original without creating a new clock or receipt."""
        if self._closed:
            raise PermissionError('HEAD_LOCAL_OBSERVER_CLOSED')
        if kind not in _KINDS or type(record) is not dict:
            self._invalidate('HEAD_LOCAL_OBSERVER_ORIGINAL_INVALID')
            raise ValueError('HEAD_LOCAL_OBSERVER_ORIGINAL_INVALID')
        clock = self._original_clock(record)
        if clock is None:
            self._invalidate('HEAD_LOCAL_OBSERVER_ORIGINAL_INVALID')
            raise ValueError('HEAD_LOCAL_OBSERVER_ORIGINAL_INVALID')
        wall_s, source_ns = clock
        if kind == 'JOINT':
            return self._joint_original(record, source_ns)
        if kind == 'CLOCK':
            return self._clock_original(record, source_ns)
        return self._camera_original(kind, record, source_ns)

    def _joint_original(self, record, source_ns):
        sequence = record.get('sequence')
        if type(sequence) is not int or sequence <= 0:
            self._invalidate('HEAD_LOCAL_OBSERVER_ORIGINAL_INVALID')
            raise ValueError('HEAD_LOCAL_OBSERVER_ORIGINAL_INVALID')
        fault_token = None
        invalid = record['valid'] is not True
        with self._lock:
            if self._closed:
                raise PermissionError('HEAD_LOCAL_OBSERVER_CLOSED')
            self._joint = dict(record)
            self._joint_history.append(self._joint)
            self._joint_count += 1
            if invalid:
                fault_token = self.local_state.latch_fault('HEAD_LOCAL_OBSERVER_JOINT_INVALID')
                self.failed = True
                self._fault_reason = 'HEAD_LOCAL_OBSERVER_JOINT_INVALID'
                self._closed_admission = True
        if invalid:
            self._invalidate('HEAD_LOCAL_OBSERVER_JOINT_INVALID', token=fault_token)
        if self._emit is not None:
            self._emit_event('JOINT_ORIGINAL', {'source_ns': source_ns, 'sequence': sequence})
        return True

    def _clock_original(self, record, source_ns):
        with self._lock:
            previous = self._clock_source_ns
            advancing = previous is None or source_ns > previous
            stored = dict(record)
            if not advancing or stored.get('valid') is not True or source_ns <= 0:
                stored['valid'] = False
                stored.setdefault('error', 'HEAD_LOCAL_OBSERVER_CLOCK_NONADVANCING')
            else:
                self._clock_source_ns = source_ns
            self._clock = stored
        if stored['valid'] is not True:
            self._invalidate('HEAD_LOCAL_OBSERVER_CLOCK_NONADVANCING')
        else:
            if self._sink is not None:
                self._record('CLOCK_ORIGINAL', stored)
        return stored['valid']

    def _camera_original(self, kind, record, source_ns):
        image = kind == 'IMAGE'
        reason = None
        fault_token = None
        if record.get('valid') is not True:
            reason = 'HEAD_LOCAL_OBSERVER_CAMERA_INVALID'
        elif source_ns <= 0 or record.get('frame_id') != self.camera_frame:
            reason = 'HEAD_LOCAL_OBSERVER_CAMERA_INVALID'
        else:
            for name in ('width', 'height'):
                if name in record and (type(record[name]) is not int or record[name] <= 0):
                    reason = 'HEAD_LOCAL_OBSERVER_CAMERA_INVALID'
        with self._lock:
            watermark = self._image_source_ns if image else self._info_source_ns
            advancing = watermark is None or source_ns > watermark
            stored = dict(record)
            if reason is None and not advancing:
                reason = 'HEAD_LOCAL_OBSERVER_CAMERA_INVALID'
            if reason is not None:
                stored['valid'] = False
                stored.setdefault('error', reason)
                # Close local admission before a reader can select an older
                # complete pair. Latching invokes no diagnostics or callbacks;
                # those operations remain outside the observer cache lock.
                fault_token = self.local_state.latch_fault(reason)
                self.failed = True
                self._fault_reason = reason
                self._closed_admission = True
            else:
                history = self._images if image else self._infos
                history[source_ns] = dict(stored)
                while len(history) > _HISTORY:
                    history.pop(next(iter(history)))
                if image:
                    self._image_source_ns = source_ns
                    self._image_source_wall_s = stored['wall_s']
                else:
                    self._info_source_ns = source_ns
            if image:
                self._image = stored
            else:
                self._info = stored
        if reason is not None:
            self._invalidate(reason, token=fault_token)
            return False
        if self._sink is not None:
            self._record('IMAGE_ORIGINAL' if image else 'INFO_ORIGINAL', stored)
        return True

    # ---- read-only views ---------------------------------------------------

    def snapshot(self):
        with self._lock:
            view = dict(
                clock=None if self._clock is None else dict(self._clock),
                clock_source_ns=self._clock_source_ns,
                image=None if self._image is None else dict(self._image),
                info=None if self._info is None else dict(self._info),
                image_source_ns=self._image_source_ns, info_source_ns=self._info_source_ns,
                image_source_wall_s=self._image_source_wall_s,
                joint=None if self._joint is None else dict(self._joint),
                joint_count=self._joint_count, action_status=dict(self._action_status),
                outstanding=sorted('%s:%s' % key for key in self._outstanding),
                failed=self.failed, fault_reason=self._fault_reason, closed=self._closed)
        view['fault'] = self.local_state.snapshot['fault']
        return view

    def camera_pair(self):
        """Return the newest complete original Image/CameraInfo pair or refuse."""
        with self._lock:
            # A pair is published only after both independently delivered
            # originals arrive. Invalid fragments still latch a fault in
            # _camera_original before entering either bounded history.
            if self.failed or self._closed:
                raise PermissionError('HEAD_LOCAL_OBSERVER_CURRENT_INVALID')
            paired_sources = self._images.keys() & self._infos.keys()
            source_ns = max(paired_sources) if paired_sources else None
            image = self._images.get(source_ns)
            info = self._infos.get(source_ns)
        if (image is None or info is None or image.get('valid') is not True
                or info.get('valid') is not True or image['source_ns'] != info['source_ns']
                or image.get('frame_id') != info.get('frame_id')
                or image.get('width') != info.get('width')
                or image.get('height') != info.get('height')):
            raise PermissionError('HEAD_LOCAL_OBSERVER_CAMERA_PAIR_INVALID')
        return dict(source_ns=image['source_ns'], frame_id=image['frame_id'],
                    width=image.get('width'), height=image.get('height'),
                    image=dict(image), info=dict(info))

    def current_inputs(self, now_wall_s):
        """Validate current originals and the newest complete original camera pair."""
        if (type(now_wall_s) not in (int, float) or not math.isfinite(now_wall_s)
                or now_wall_s < 0 or self.failed or self._closed):
            raise PermissionError('HEAD_LOCAL_OBSERVER_CURRENT_INVALID')
        with self._lock:
            clock, image, info, joint = self._clock, self._image, self._info, self._joint
            image_wall = self._image_source_wall_s
        if clock is None or clock.get('valid') is not True or clock['source_ns'] <= 0:
            raise PermissionError('HEAD_LOCAL_OBSERVER_CLOCK_INVALID')
        if joint is None or type(joint.get('sequence')) is not int:
            raise PermissionError('HEAD_LOCAL_OBSERVER_JOINT_INVALID')
        pair = self.camera_pair()
        return dict(clock=clock, joint=joint, camera_pair=pair,
                    image=pair['image'], info=pair['info'],
                    image_source_wall_s=pair['image']['wall_s'], now_wall_s=now_wall_s)

    def admission_joint_candidates(self):
        """Copy the same bounded causal candidates from received admission originals."""
        with self._lock:
            if self.failed or self._closed:
                raise PermissionError('HEAD_LOCAL_OBSERVER_CURRENT_INVALID')
            return _copy_current_original_candidates(self._joint, self._joint_history)

    # ---- action status, result and cancellation ----------------------------

    def _status(self, message):
        """StatusArray 1..6 proves acceptance; a terminal status is not a result."""
        callback_wall = self.monotonic()
        observed = []
        for status in message.status_list:
            gid = str(uuid.UUID(bytes=bytes(status.goal_info.goal_id.uuid)))
            value = int(status.status)
            if not 1 <= value <= 6:
                with self.port._lock:
                    known = gid in self.port._goals
                if known:
                    if self.port._head_action_sink is not None:
                        self.port.record_head_action('HEAD_ACTION_STATUS',gid,status,
                                                     callback_wall_s=callback_wall)
                continue
            contradiction = False
            with self.port._lock:
                record = self.port._goals.get(gid)
                if record is None:
                    continue
                if record['accepted'] is False:
                    contradiction = True
                else:
                    record['accepted'] = True
            with self._lock:
                self._action_status[gid] = value
            observed.append(dict(goal_uuid=gid, status=value))
            if contradiction:
                self._invalidate('HEAD_LOCAL_OBSERVER_ACCEPTANCE_CONTRADICTION')
            if self.port._head_action_sink is not None:
                self.port.record_head_action('HEAD_ACTION_STATUS',gid,status,
                                             callback_wall_s=callback_wall)
        return tuple(observed)

    def _pending_ids(self):
        with self.port._lock:
            return tuple(gid for gid, record in self.port._goals.items()
                         if record['accepted'] is not False
                         and getattr(record.get('result'), 'status', None) not in _TERMINAL)

    def _request(self, gid, kind):
        if kind not in ('result', 'cancel'):
            raise ValueError('HEAD_LOCAL_OBSERVER_REQUEST_KIND_INVALID')
        try:
            parsed = uuid.UUID(gid)
        except (AttributeError, TypeError, ValueError):
            self._invalidate('HEAD_LOCAL_OBSERVER_UUID_INVALID')
            raise ValueError('HEAD_LOCAL_OBSERVER_UUID_INVALID') from None
        if str(parsed) != gid or parsed.version != 4:
            self._invalidate('HEAD_LOCAL_OBSERVER_UUID_INVALID')
            raise ValueError('HEAD_LOCAL_OBSERVER_UUID_INVALID')
        with self._lock:
            if self._closed:
                raise PermissionError('HEAD_LOCAL_OBSERVER_CLOSED')
            if (gid, kind) in self._outstanding:
                return False
            self._outstanding[(gid, kind)] = None
        try:
            self.port._head_dispatch_io(gid, kind, lambda: self._call(gid, kind))
        except Exception as error:
            with self._lock:
                self._outstanding.pop((gid, kind), None)
            self.port._head_io_failed(gid, error)
            raise
        return True

    def _call(self, gid, kind):
        if kind == 'cancel':
            request = CancelGoal.Request()
            request.goal_info.goal_id = UUID(uuid=list(uuid.UUID(gid).bytes))
            client = self._cancel_client
        else:
            request = FollowJointTrajectory.Impl.GetResultService.Request()
            request.goal_id = UUID(uuid=list(uuid.UUID(gid).bytes))
            client = self._result_client
        requested_wall = self.monotonic()
        future = client.call_async(request)
        with self._lock:
            if (gid, kind) in self._outstanding:
                self._outstanding[(gid, kind)] = future
        future.add_done_callback(lambda done: self._response(gid, kind, done))
        if self.port._head_action_sink is not None:
            self.port.record_head_action('HEAD_ACTION_SERVICE_REQUEST',gid,request,
                                          callback_wall_s=requested_wall)

    def _response(self, gid, kind, future):
        callback_wall = self.monotonic()
        try:
            response = future.result()
            clocks = (decision_clocks(self.node, self.monotonic)
                      if kind == 'result' and response.status in _TERMINAL else None)
            contradiction = None
            with self.port._lock:
                record = self.port._goals[gid]
                if kind == 'cancel':
                    record['cancel_ack'] = response.return_code == 0
                elif response.status in (1, 2, 3, 4, 5, 6):
                    if record['accepted'] is False:
                        contradiction = 'HEAD_LOCAL_OBSERVER_ACCEPTANCE_CONTRADICTION'
                    else:
                        terminal = record['result']
                        if terminal is not None and (response.status != terminal.status
                                                     or response != terminal):
                            contradiction = 'HEAD_LOCAL_OBSERVER_TERMINAL_CONTRADICTION'
                        else:
                            record['accepted'] = True
                            if response.status in _TERMINAL:
                                record['result'] = response
                                if terminal is None and clocks is not None:
                                    record['terminal_wall_s'] = clocks['wall_after_s']
                                    record['terminal_source_floor_ns'] = clocks['sim_ns']
                elif response.status != 0:
                    contradiction = 'HEAD_LOCAL_OBSERVER_RESULT_STATUS_INVALID'
            if contradiction is not None:
                self._invalidate(contradiction)
            if self.port._head_action_sink is not None:
                self.port.record_head_action(
                    'HEAD_ACTION_CANCEL' if kind == 'cancel' else 'HEAD_ACTION_GET_RESULT',gid,
                    lambda: (self.port._head_cancel_reply(response) if kind == 'cancel'
                             else self.port._head_result_reply(response)),
                    callback_wall_s=callback_wall)
        except Exception as error:
            self.port._head_io_failed(gid, error)
        finally:
            with self._lock:
                self._outstanding.pop((gid, kind), None)

    def request_result(self, gid):
        return self._request(gid, 'result')

    def request_cancel(self, gid):
        with self.port._lock:
            record = self.port._goals.get(gid)
            if record is not None:
                record['cancel_requested'] = True
        return self._request(gid, 'cancel')

    def request_results(self):
        return tuple(gid for gid in self._pending_ids() if self._request(gid, 'result'))

    def request_cancel_all(self):
        """Cancel every non-terminal inventory UUID, accepted, UNKNOWN or handle-less."""
        requested = []
        for gid in self._pending_ids():
            try:
                if self.request_cancel(gid):
                    requested.append(gid)
            except Exception:
                continue
        return tuple(requested)

    # ---- retirement --------------------------------------------------------

    def close(self):
        with self._close_lock:
            if self._close_receipt is not None:
                return dict(copy.deepcopy(self._close_receipt), already_closed=True)
            with self._lock:
                self._closed = True
                outstanding = sorted('%s:%s' % key for key in self._outstanding)
            clients_retired = True
            for client in (self._result_client, self._cancel_client):
                try:
                    if self.node.destroy_client(client) is not True:
                        clients_retired = False
                except Exception:
                    clients_retired = False
            subscriptions_retired = True
            for subscription in self.subscriptions:
                try:
                    if self.node.destroy_subscription(subscription) is not True:
                        subscriptions_retired = False
                except Exception:
                    subscriptions_retired = False
            self._close_receipt = dict(clients_retired=clients_retired,
                subscriptions_retired=subscriptions_retired,
                outstanding=outstanding, already_closed=False)
            return copy.deepcopy(self._close_receipt)
