"""One owned simulator reset with authoritative full-state pose readback."""

import copy
from contextlib import contextmanager
import math
import threading
import time
from types import SimpleNamespace

from .head_execution_scene import HeadSceneSafety
from .scene_state import SceneStateObserver, RosSceneStateAdapter


_CONTROLLERS = ('arm_controller', 'gripper_controller', 'neck_controller')


def rebase_startup_originals(capture, port, reset_proof):
    """Discard pre-reset diagnostic watermarks before any execution owner binds."""
    from .head_stopped_capture import StoppedHeadCapture
    from .ros_execution import RosControllerPort
    # The native reset preserves ROS clock continuity while advancing its epoch.
    reset_time_s = reset_proof.get('simulation_time_s')
    if (type(capture) is not StoppedHeadCapture or type(port) is not RosControllerPort
            or capture.port is not port or reset_proof.get('paused') is not True
            or reset_proof.get('simulation_step') != 0
            or type(reset_time_s) not in (int, float)
            or not math.isfinite(reset_time_s) or reset_time_s < 0
            or type(reset_proof.get('reset_epoch')) is not int or reset_proof['reset_epoch'] <= 0):
        raise ValueError('HEAD_RESET_ORIGINAL_BOUNDARY_INVALID')
    with port._lock:
        if (capture._started or capture.strict or capture._original_sink is not None
                or capture._live_sink is not None or capture._failure is not None
                or port._head_original_sink is not None or port._head_fault_callback is not None
                or port._head_policy_binding_failed or port._goals or port._head_inventory_scope is not None):
            raise PermissionError('HEAD_RESET_ORIGINAL_BOUNDARY_USED')
        capture._last.clear()
        capture._last_camera = capture._pending = None
        for rows in (capture.camera_messages,capture.info_messages,capture.clock_messages,capture.events):
            rows.clear()
        port._head_source_watermark = port._head_feedback = None
        port._head_samples.clear()
        port._head_sequence = 0


class HeadSceneServices:
    """Use bounded futures on the already-spinning owned ROS node."""

    def __init__(self, node):
        from controller_manager_msgs.srv import ListControllers, SwitchController
        from mujoco_ros2_control_msgs.srv import ResetWorld, SetPause
        self.node = node
        self.types = dict(pause=SetPause, reset=ResetWorld, switch=SwitchController,
                          controllers=ListControllers)
        self.clients = {}
        try:
            for name, endpoint in dict(pause='/mujoco_ros2_control_node/set_pause',
                    reset='/mujoco_ros2_control_node/reset_world',
                    switch='/controller_manager/switch_controller',
                    controllers='/controller_manager/list_controllers').items():
                self.clients[name] = node.create_client(self.types[name], endpoint)
        except Exception:
            self.close()
            raise

    def _call(self, name, request, *, deadline):
        client = self.clients[name]
        while not client.wait_for_service(timeout_sec=min(.01, max(0., deadline-time.monotonic()))):
            if time.monotonic() >= deadline:
                raise TimeoutError('HEAD_RESET_SERVICE_UNAVAILABLE:'+name)
        if time.monotonic() >= deadline:
            raise TimeoutError('HEAD_RESET_SERVICE_DEADLINE:'+name)
        future = client.call_async(request)
        while not future.done():
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                future.cancel()
                raise TimeoutError('HEAD_RESET_SERVICE_TIMEOUT:'+name)
            time.sleep(min(.005, remaining))
        result = future.result()
        if result is None:
            raise ValueError('HEAD_RESET_SERVICE_EMPTY:'+name)
        return result

    def pause(self, paused, *, deadline):
        request = self.types['pause'].Request(paused=paused)
        return self._call('pause', request, deadline=deadline).success is True

    def switch(self, *, activate, deactivate, deadline):
        request = self.types['switch'].Request()
        request.activate_controllers, request.deactivate_controllers = list(activate), list(deactivate)
        request.strictness = request.STRICT
        request.activate_asap = True
        remaining_ns = max(1, round((deadline-time.monotonic())*1e9))
        request.timeout.sec, request.timeout.nanosec = divmod(remaining_ns, 1_000_000_000)
        return self._call('switch', request, deadline=deadline).ok is True

    def active(self, names, *, deadline):
        response = self._call('controllers', self.types['controllers'].Request(), deadline=deadline)
        states = {row.name: row.state for row in response.controller}
        return all(states.get(name) == 'active' for name in names)

    def reset_pose(self, pose, *, deadline):
        from so101_demo.backends.mujoco.client import (
            JointResetOverride, FreeJointResetOverride, joint_override_message, _free_joint_message)
        request = self.types['reset'].Request()
        # Empty keyframe selects the native captured initial state, then applies
        # these validated overrides. The approved scene has no named keyframe.
        request.keyframe = ''
        joints = tuple(JointResetOverride(name, value) for name, value in zip(
            ('1','2','3','4','5','6','neck_yaw_joint'), (*pose['arm_rad'],pose['neck_rad']),strict=True))
        request.state_overrides.joint_states = joint_override_message(joints)
        request.state_overrides.free_joints = [
            _free_joint_message(FreeJointResetOverride('plastic_cup',tuple(pose['cup_xyz'])))]
        return self._call('reset', request, deadline=deadline).success is True

    def close(self):
        failures = []
        for name, client in tuple(self.clients.items()):
            try:
                if self.node.destroy_client(client) is not True: failures.append(name)
            except Exception as error: failures.append(name+':'+type(error).__name__)
            self.clients.pop(name)
        return dict(closed=not failures, failures=failures)


class OwnedHeadScene:
    """Keep the same full-state subscriber live through reset, dispatch and Stop."""

    def __init__(self, *, node, inputs, safety, max_age_s, services=None, startup_ready=None,
                 emit=lambda kind, record: None):
        if type(safety) is not HeadSceneSafety:
            raise ValueError('HEAD_RESET_SAFETY_INVALID')
        self.node, self.inputs, self.safety, self.emit = node, inputs, safety, emit
        self.startup_ready = startup_ready
        self._lock = threading.RLock()
        self._latest = self._expected_epoch = self.receipt = self.hazard = None
        self._latest_wall = None
        self._used = self._closed = False
        self._close_lock = threading.Lock()
        self._close_receipt = None
        self._fault = None
        self._admission_binding = None
        self._admission_gate = threading.Lock()
        self._admission_lease = None
        model = safety.checker.model
        self.observer = SceneStateObserver(model_sha256=safety.checker.model_sha256,
                                           nq=model.nq,nv=model.nv,max_age_s=max_age_s)
        self.services = services if services is not None else HeadSceneServices(node)
        try:
            self.adapter = RosSceneStateAdapter(node,self.observer,on_hazard=self._hazard,
                record_port=self._record,pending_reset_port=self._pending_reset)
        except Exception:
            self.services.close()
            raise

    def _hazard(self, reason):
        with self._lock:
            self.hazard = self.hazard or reason
            fault = self._fault
        if fault is not None: fault(reason)

    def bind_fault(self, callback):
        if not callable(callback): raise ValueError('HEAD_RESET_FAULT_BINDING_INVALID')
        with self._lock:
            if self._fault is not None or self._closed: raise PermissionError('HEAD_RESET_FAULT_REBOUND')
            self._fault = callback
            reason = self.hazard
        if reason is not None: callback(reason)

    def _record(self, frame):
        self.emit('SCENE_STATE',frame)
        with self._lock:
            self._latest, self._latest_wall = copy.deepcopy(frame), time.monotonic()

    def _pending_reset(self, frame):
        return (self._expected_epoch is not None
                and frame['simulation_session_id'] == self.inputs.run['session_id']
                and frame['reset_epoch'] == self._expected_epoch)

    def _current(self):
        with self._lock:
            if self.hazard or self.observer.hazard:
                raise PermissionError(self.hazard or self.observer.hazard)
            frame, wall = copy.deepcopy(self._latest), self._latest_wall
        if frame is None or wall is None or not 0 <= time.monotonic()-wall <= self.observer.max_age:
            return None
        self.observer.validate(frame)
        if frame['simulation_session_id'] != self.inputs.run['session_id']:
            raise PermissionError('HEAD_RESET_SESSION_INVALID')
        return frame

    def _wait(self, predicate, deadline):
        while time.monotonic() < deadline:
            frame = self._current()
            if frame is not None and predicate(frame): return frame
            time.sleep(min(.005,max(0.,deadline-time.monotonic())))
        raise TimeoutError('HEAD_RESET_EVIDENCE_TIMEOUT')

    def _verify_pose(self, frame):
        pose = self.inputs.document['development_pose']
        for name,value in zip(('1','2','3','4','5','6','neck_yaw_joint'),
                               (*pose['arm_rad'],pose['neck_rad']),strict=True):
            if abs(frame['qpos'][self.safety.joint_map[name]['qpos']]-value) > 1e-9:
                raise ValueError('HEAD_RESET_JOINT_POSE_INVALID')
        address = self.safety.free_body_map['plastic_cup']['qpos']
        expected = (*pose['cup_xyz'],1.,0.,0.,0.)
        if any(abs(a-b)>1e-9 for a,b in zip(frame['qpos'][address:address+7],expected,strict=True)):
            raise ValueError('HEAD_RESET_CUP_POSE_INVALID')
        if any(abs(value)>1e-9 for value in frame['qvel']):
            raise ValueError('HEAD_RESET_VELOCITY_INVALID')

    def reset(self, *, timeout_s=5.):
        if type(timeout_s) not in (float,int) or not 0 < timeout_s <= 5.:
            raise ValueError('HEAD_RESET_TIMEOUT_INVALID')
        with self._lock:
            if self._used or self._closed: raise PermissionError('HEAD_RESET_REUSED')
            self._used = True
        deadline = time.monotonic()+timeout_s
        def require(value, operation):
            if value is not True: raise PermissionError('HEAD_RESET_'+operation+'_REFUSED')
        try:
            if self.startup_ready is not None:
                startup = self.startup_ready(deadline=deadline)
                require(startup.get('ready'), 'STARTUP')
                self.emit('STACK_STARTUP_VERIFIED', startup)
            # Spawners are owned asynchronous children. Do not pause their
            # controller-manager cycle or strictly deactivate missing roles.
            while not self.services.active(_CONTROLLERS,deadline=deadline):
                if time.monotonic() >= deadline:
                    raise TimeoutError('HEAD_RESET_STARTUP_CONTROLLERS_TIMEOUT')
                time.sleep(min(.005,max(0.,deadline-time.monotonic())))
            require(self.services.pause(True,deadline=deadline),'INITIAL_PAUSE')
            old = self._wait(lambda row: row['paused'],deadline)
            self._expected_epoch = old['reset_epoch']+1
            require(self.services.pause(False,deadline=deadline),'PREPARE_RUNNING')
            require(self.services.switch(activate=(),deactivate=_CONTROLLERS,deadline=deadline),'DEACTIVATE')
            require(self.services.pause(True,deadline=deadline),'PAUSE')
            require(self.services.reset_pose(self.inputs.document['development_pose'],deadline=deadline),'RESET')
            frame = self._wait(lambda row: row['reset_epoch']==self._expected_epoch
                and row['paused'] and row['simulation_step']==0,deadline)
            self._verify_pose(frame)
            self.adapter.arm(SimpleNamespace(**frame))
            require(self.services.pause(False,deadline=deadline),'RESUME_FOR_ACTIVATE')
            require(self.services.switch(activate=_CONTROLLERS,deactivate=(),deadline=deadline),'ACTIVATE')
            while not self.services.active(_CONTROLLERS,deadline=deadline):
                if time.monotonic() >= deadline: raise TimeoutError('HEAD_RESET_CONTROLLERS_TIMEOUT')
                time.sleep(.005)
            require(self.services.pause(True,deadline=deadline),'FINAL_PAUSE')
            self._wait(lambda row: row['paused'] and row['reset_epoch']==self._expected_epoch,deadline)
            self.receipt = dict(frame,old_epoch=old['reset_epoch'],
                safety_sha256=self.safety.source_sha256,verified_pose=copy.deepcopy(self.inputs.document['development_pose']))
            self.emit('SCENE_RESET_VERIFIED',self.receipt)
            return copy.deepcopy(self.receipt)
        except Exception:
            # Failure does not reactivate controllers or invent successful proof.
            try: self.services.pause(True,deadline=time.monotonic()+min(.05,timeout_s))
            except Exception: pass
            raise

    def resume(self, *, timeout_s=1.):
        if self.receipt is None or self._closed or self.hazard:
            raise PermissionError('HEAD_RESET_UNVERIFIED')
        if self.services.pause(False,deadline=time.monotonic()+timeout_s) is not True:
            raise PermissionError('HEAD_RESET_RESUME_REFUSED')

    def bind_admission(self, *, runtime, guard):
        """Bind the exact existing scene, runtime and prepared dispatcher once."""
        from .head_local_runtime import HeadLocalRuntime
        from .head_trajectory_guard import HeadTrajectoryGuard
        if (type(runtime) is not HeadLocalRuntime or type(guard) is not HeadTrajectoryGuard
                or self.receipt is None or self._closed or self.hazard
                or runtime.node is not self.node or guard.node is not self.node
                or any(runtime.local_state.scope[key] != self.inputs.run.get(key)
                       for key in ('session_id', 'generation', 'epoch'))
                or guard.simulation_session_id != self.inputs.run['session_id']
                or guard.reset_epoch != self.receipt['reset_epoch']
                or guard.checker is not self.safety.checker
                or guard.scene_observer is not self.observer
                or guard.feedback_port is not runtime.port
                or guard._local_state is not runtime.local_state
                or guard._dispatcher is None
                or guard._dispatcher.port is not runtime.port):
            raise PermissionError('HEAD_ADMISSION_BINDING_INVALID')
        with self._lock:
            if self._admission_binding is not None or guard._admission_scene is not None:
                raise PermissionError('HEAD_ADMISSION_REBOUND')
            self._admission_binding = (runtime, guard)
            guard._admission_scene = self

    def _require_lease(self, guard, *, check_scene=False):
        """Cheap revocation/deadline check, including every collision sample."""
        lease = self._admission_lease
        if (self._admission_binding is None or self._admission_binding[1] is not guard
                or lease is None or lease['thread'] != threading.get_ident()):
            raise PermissionError('HEAD_ADMISSION_LEASE_REQUIRED')
        runtime = self._admission_binding[0]
        if (self._closed or self.hazard or guard._stopped or runtime.stop_requested
                or not runtime.ready or runtime.local_state.faulted):
            raise PermissionError('HEAD_ADMISSION_REVOKED')
        if time.monotonic_ns() >= lease['deadline_ns']:
            raise PermissionError('HEAD_ADMISSION_LEASE_EXPIRED')
        if check_scene:
            frame, _ = self.observer.snapshot_with_receipt()
            self._admission_identity(frame, guard)
            if frame['paused'] is not True:
                raise PermissionError('HEAD_ADMISSION_SCENE_RUNNING')
        return lease

    def _admission_identity(self, frame, guard):
        runtime = self._admission_binding[0]
        if any(runtime.local_state.scope[key] != self.inputs.run.get(key)
               for key in ('session_id', 'generation', 'epoch')):
            raise PermissionError('HEAD_ADMISSION_BINDING_INVALID')
        if (frame['simulation_session_id'] != self.inputs.run['session_id']
                or frame['reset_epoch'] != self.receipt['reset_epoch']
                or frame['model_sha256'] != guard.model_semantic_sha256):
            raise PermissionError('HEAD_ADMISSION_SCENE_IDENTITY_INVALID')

    def _await_admission_state(self, paused, *, request_ns, deadline_ns, guard,
                               allow_stop=False):
        runtime = self._admission_binding[0]
        while time.monotonic_ns() < deadline_ns:
            if not allow_stop and (runtime.stop_requested or not runtime.ready):
                raise PermissionError('HEAD_ADMISSION_REVOKED')
            try:
                frame, received = self.observer.snapshot_with_receipt()
            except ValueError as error:
                if self.observer.hazard:
                    raise PermissionError(str(error)) from error
            else:
                self._admission_identity(frame, guard)
                if (frame['paused'] is paused
                        and frame['clock_interval_begin_monotonic_ns'] >= request_ns):
                    return frame, received
            time.sleep(min(.001, max(0., (deadline_ns-time.monotonic_ns())*1e-9)))
        raise TimeoutError('HEAD_ADMISSION_STATE_TIMEOUT')

    def _admission_deadline(self, runtime, guard):
        """Capture immutable expirations of originals, never renew their receipts."""
        from so101_demo.act.head_feedback import nanoseconds
        from .ros_execution import _causal_current_original
        runtime.dispatch_guard()
        current = runtime.observer.current_inputs(runtime.monotonic())
        candidates = runtime.observer.admission_joint_candidates()
        feedback = runtime.port.feedback_snapshot()
        joint = _causal_current_original(candidates, feedback['decision']['sim_ns'])
        runtime.port.feedback_policy.check_joint(joint, feedback['decision'])
        frame, received = self.observer.snapshot_with_receipt()
        self._admission_identity(frame, guard)
        policy = runtime.policy
        def expires(receipt, duration):
            return nanoseconds(receipt) + math.floor(duration*1e9)
        deadline = min(runtime.local_state.search_deadline_ns,
            expires(current['clock']['wall_s'], runtime.port.feedback_policy.clock_interarrival_deadline_s),
            expires(joint['wall_s'], runtime.port.feedback_policy.joint_max_receipt_age_s),
            expires(feedback['wall_s'], policy.feedback_receipt_timeout_s),
            expires(current['image']['wall_s'], policy.camera_source_age_s),
            expires(current['info']['wall_s'], policy.camera_source_age_s),
            expires(current['image_source_wall_s'], policy.camera_loss_timeout_s),
            expires(received, self.observer.max_age),
            frame['clock_interval_end_monotonic_ns'] + math.floor(self.observer.max_age*1e9))
        if time.monotonic_ns() >= deadline:
            raise PermissionError('HEAD_ADMISSION_LEASE_EXPIRED')
        return deadline

    def _await_fresh_admission_pair(self, runtime, guard):
        """Freeze original expirations; initial motion first waits for a newer pair."""
        started_ns = time.monotonic_ns()
        wait_deadline_ns = self._admission_deadline(runtime, guard)
        current = runtime.observer.current_inputs(runtime.monotonic())
        source_floor_ns = current['image']['source_ns']
        with runtime._lock:
            observation_deadline = runtime._observation_deadline_wall_s
        if observation_deadline is not None:
            # The search has already selected a complete post-settlement
            # observation. Another camera-period wait consumes that unchanged
            # deadline without making the selected observation any fresher.
            # Capture the current complete originals before a lease exists;
            # neither their receipts nor the selected deadline are renewed.
            from so101_demo.act.head_feedback import nanoseconds
            deadline_ns = min(wait_deadline_ns, nanoseconds(observation_deadline))
            runtime.dispatch_guard()
            self.emit('HEAD_ADMISSION_INPUT_READY', dict(
                started_ns=started_ns, wait_deadline_ns=wait_deadline_ns,
                source_floor_ns=source_floor_ns, source_ns=current['image']['source_ns'],
                image_receipt_wall_s=current['image']['wall_s'],
                info_receipt_wall_s=current['info']['wall_s'], deadline_ns=deadline_ns,
                selection='selected_observation_current_complete_pair'))
            runtime.dispatch_guard()
            return deadline_ns
        while time.monotonic_ns() < wait_deadline_ns:
            # The world and original observers stay live here. Lost, invalid,
            # stopped or expired inputs still refuse under their original limits.
            runtime.dispatch_guard()
            current = runtime.observer.current_inputs(runtime.monotonic())
            image, info = current['image'], current['info']
            if (image['source_ns'] > source_floor_ns
                    and info['source_ns'] == image['source_ns']):
                if time.monotonic_ns() >= wait_deadline_ns:
                    break
                deadline_ns = self._admission_deadline(runtime, guard)
                self.emit('HEAD_ADMISSION_INPUT_READY', dict(
                    started_ns=started_ns, wait_deadline_ns=wait_deadline_ns,
                    source_floor_ns=source_floor_ns, source_ns=image['source_ns'],
                    image_receipt_wall_s=image['wall_s'], info_receipt_wall_s=info['wall_s'],
                    deadline_ns=deadline_ns))
                runtime.dispatch_guard()
                return deadline_ns
            time.sleep(min(.001, max(0., (wait_deadline_ns-time.monotonic_ns())*1e-9)))
        raise PermissionError('HEAD_ADMISSION_ORIGINAL_PAIR_TIMEOUT')

    @contextmanager
    def paused_admission(self, guard):
        """Pause through prepared SDK submission, then prove resume before return."""
        if self._admission_binding is None or self._admission_binding[1] is not guard:
            raise PermissionError('HEAD_ADMISSION_BINDING_INVALID')
        runtime = self._admission_binding[0]
        if not self._admission_gate.acquire(blocking=False):
            runtime.fault('HEAD_ADMISSION_BUSY')
            raise PermissionError('HEAD_ADMISSION_BUSY')
        pause_may_have_applied = False
        operation_error = resume_error = None
        deadline_ns = None
        try:
            deadline_ns = self._await_fresh_admission_pair(runtime, guard)
            request_ns = time.monotonic_ns()
            # Cancellation of a client future does not prove the server did
            # not pause. Always attempt bounded resume after this boundary.
            pause_may_have_applied = True
            if self.services.pause(True, deadline=deadline_ns*1e-9) is not True:
                raise PermissionError('HEAD_ADMISSION_PAUSE_REFUSED')
            frame, received = self._await_admission_state(True, request_ns=request_ns,
                deadline_ns=deadline_ns, guard=guard)
            self._admission_lease = dict(thread=threading.get_ident(), deadline_ns=deadline_ns)
            self.emit('HEAD_ADMISSION_PAUSED', dict(deadline_ns=deadline_ns,
                request_ns=request_ns, scene=frame, receipt_wall_s=received))
            self._require_lease(guard, check_scene=True)
            yield
            self._require_lease(guard, check_scene=True)
        except BaseException as error:
            operation_error = error
            runtime.fault('HEAD_ADMISSION_TRANSACTION_FAILED',
                          {'error': type(error).__name__, 'reason': str(error)})
        finally:
            self._admission_lease = None
            try:
                if pause_may_have_applied:
                    def resume_before(bound, *, service_deadline=None):
                        request = time.monotonic_ns()
                        if request >= bound:
                            raise TimeoutError('HEAD_ADMISSION_RESUME_DEADLINE')
                        deadline_s = bound/1e9 if service_deadline is None else service_deadline
                        if self.services.pause(False, deadline=deadline_s) is not True:
                            raise PermissionError('HEAD_ADMISSION_RESUME_REFUSED')
                        frame, received = self._await_admission_state(False,
                            request_ns=request, deadline_ns=bound, guard=guard, allow_stop=True)
                        self.emit('HEAD_ADMISSION_RESUMED', dict(request_ns=request,
                            deadline_ns=bound, scene=frame, receipt_wall_s=received))
                    if runtime.stop_requested:
                        stop_deadline = runtime.stop_receipt()['stop_deadline_wall_s']
                        bound = round(stop_deadline*1e9)
                    else:
                        stop_deadline = None
                        bound = deadline_ns
                    try:
                        resume_before(bound, service_deadline=stop_deadline)
                    except BaseException as error:
                        resume_error = error
                        runtime.fault('HEAD_ADMISSION_RESUME_FAILED',
                                      {'error': type(error).__name__, 'reason': str(error)})
                        # The first failure is still a failed execution even
                        # if cleanup succeeds. Its Stop deadline is immutable.
                        cleanup_deadline = runtime.stop_receipt()['stop_deadline_wall_s']
                        cleanup = round(cleanup_deadline*1e9)
                        if cleanup > bound:
                            try:
                                resume_before(cleanup, service_deadline=cleanup_deadline)
                            except BaseException as cleanup_error:
                                self.emit('HEAD_ADMISSION_RESUME_UNCONFIRMED',
                                    {'error': type(cleanup_error).__name__, 'reason': str(cleanup_error),
                                     'deadline_ns': cleanup})
            finally:
                self._admission_gate.release()
        if operation_error is None and resume_error is None and not runtime.ready:
            operation_error = PermissionError('HEAD_ADMISSION_REVOKED')
            runtime.fault('HEAD_ADMISSION_TRANSACTION_FAILED', {'reason': str(operation_error)})
        if operation_error is not None:
            raise operation_error from resume_error
        if resume_error is not None:
            raise resume_error

    def close(self):
        with self._close_lock:
            if self._close_receipt is not None:
                return copy.deepcopy(self._close_receipt)
            with self._lock:
                self._closed = True
            failures = []
            try:
                if self.node.destroy_subscription(self.adapter.subscription) is not True:
                    failures.append('scene_subscription')
            except Exception as error:
                failures.append(type(error).__name__)
            try:
                services = self.services.close()
            except Exception as error:
                services = dict(closed=False, error=type(error).__name__)
            self._close_receipt = dict(closed=not failures and services.get('closed') is True,
                                      failures=failures, services=services)
            return copy.deepcopy(self._close_receipt)
