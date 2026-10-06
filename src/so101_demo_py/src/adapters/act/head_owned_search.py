"""Real Head Search on the entry's original exposures and existing transport.

This adapter creates no ROS, model, SDK or worker resources. The entry prepares
the controller before ARM, then binds its already-owned dispatch facade once.
"""
from copy import deepcopy
import math
import threading
import time
from types import SimpleNamespace

from so101_demo.act.head_evidence_identity import digest
from so101_demo.act.head_feedback import nanoseconds
from so101_demo.act.head_simulation_policy import BoundedObservationBudget, HeadSimulationPolicy
from so101_demo.act.bearing import optical_ray_base
from so101_demo.act.search import HeadSearchController
from .ros_search import rotation_matrix


def map_owned_search_exposure(row,config):
    """Decode original CameraInfo, Header TF and causal JointState without restamping."""
    try:
        source=row['source_ns'];info=row['original_info'];joint=row['causal_joint']
        skew=math.floor(config['max_skew_s']*1e9)
        if ((row['session_id'],row['epoch'])!=(config['session_id'],config['attempt_id'])
                or type(row['sequence']) is not int or row['sequence']<=0
                or any(type(value) is not int or value<=0 for value in
                    (source,info['source_ns'],joint['source_ns'],row['tf_source_ns']))
                or row['info_source_ns']!=source or info['source_ns']!=source
                or row['joint_source_ns']!=joint['source_ns']
                or info['frame_id']!=config['frame_id'] or joint['valid'] is not True
                or not 0<=source-joint['source_ns']<=skew
                or not 0<=source-row['tf_source_ns']<=skew
                or len(joint['positions'])!=1 or len(joint['velocities'])!=1
                or any(type(value) not in (int,float) or not math.isfinite(value) for value in
                    (joint['wall_s'],joint['positions'][0],joint['velocities'][0],
                     row['image_received_wall_s'],row['info_received_wall_s']))
                or info['wall_s']!=row['info_received_wall_s']):
            raise ValueError('HEAD_SEARCH_ORIGINAL_MAPPING_INVALID')
        quaternion=row['tf_rotation']
        if len(quaternion)!=4:raise ValueError('HEAD_SEARCH_ORIGINAL_ROTATION_INVALID')
        rotation=rotation_matrix(SimpleNamespace(**dict(zip(('x','y','z','w'),quaternion))))
        optical_ray_base((info['k'][2],info['k'][5]),info['k'],info['d'],rotation)
        identity=dict(session_id=row['session_id'],attempt_id=row['epoch'])
        frame=dict(identity,sim_time_s=source*1e-9,received_wall_s=row['image_received_wall_s'],
            frame_id=info['frame_id'],k=deepcopy(info['k']),distortion=deepcopy(info['d']),
            rotation_optical_to_base=rotation.tolist(),detections=deepcopy(row['detections']))
        feedback=dict(identity,sim_time_s=joint['source_ns']*1e-9,received_wall_s=joint['wall_s'],
            neck_yaw_rad=joint['positions'][0],neck_velocity_rad_s=joint['velocities'][0],safe_observe=True)
        return frame,feedback
    except (KeyError,TypeError,AttributeError,IndexError) as error:
        raise ValueError('HEAD_SEARCH_ORIGINAL_MAPPING_INVALID') from error


class OwnedHeadSearch:
    def __init__(self,*,config,primary,port,owner,settlement,stop_velocity_rad_s,
                 emit,monotonic=time.monotonic,local_state=None,policy=None,
                 initial_settled_source_floor_ns=1):
        self.controller=HeadSearchController(config)
        if (not callable(settlement) or not callable(emit) or not callable(monotonic)
                or type(stop_velocity_rad_s) not in (int,float)
                or not math.isfinite(stop_velocity_rad_s) or stop_velocity_rad_s<=0):
            raise ValueError('HEAD_OWNED_SEARCH_CONFIG_INVALID')
        if local_state is not None:
            from so101_demo.act.head_local_state import HeadLocalState
            if type(local_state) is not HeadLocalState:
                raise ValueError('HEAD_OWNED_SEARCH_LOCAL_STATE_INVALID')
        if policy is not None and type(policy) is not HeadSimulationPolicy:
            raise ValueError('HEAD_OWNED_SEARCH_POLICY_INVALID')
        if local_state is not None and policy is None:
            raise ValueError('HEAD_OWNED_SEARCH_POLICY_REQUIRED')
        if (type(initial_settled_source_floor_ns) is not int
                or initial_settled_source_floor_ns <= 0):
            raise ValueError('HEAD_OWNED_SEARCH_SETTLED_FLOOR_INVALID')
        self.primary=primary;self.port=port;self.owner=owner;self.settlement=settlement
        self.emit=emit;self.monotonic=monotonic;self.stop_velocity=stop_velocity_rad_s
        self._entry=threading.get_ident();self._neck=None;self._sequence=0
        # A request can complete without admitting an exposure. These counters
        # advance independently; rejected camera frames never acquire authority.
        self._observation_sequence=0
        self._local_state=local_state;self._motion_epoch=0
        start=float(config['search_start_rad'])
        if local_state is not None:
            # The authoritative target/lock lives in the shared local state, so
            # a fault can never interleave between a check and this commit.
            start=float(local_state.commit_search_state(motion_epoch=0,target_rad=start,
                lock_count=0,sequence=0,source_ns=None,decision_wall_s=None,reason='init')['target_rad'])
        self._target=start;self._active=None
        self._policy=policy;self._pending_request=None
        self._settled_floor=initial_settled_source_floor_ns
        self._settled_wall_s=self.monotonic()
        self._budget=None
        if local_state is not None:
            # The observation budget shares the original 30 s search cap and can
            # never be reset by a reobservation.
            self._budget=BoundedObservationBudget(policy,started_wall_s=(
                local_state.search_deadline_ns*1e-9-policy.search_timeout_s))
        self.commands=[];self.observations=[];self.result=None

    def bind_transport(self,neck):
        if self._neck is not None or not callable(getattr(neck,'command_neck',None)):
            self.primary.fault('HEAD_SEARCH_TRANSPORT_REBOUND')
            raise PermissionError('HEAD_SEARCH_TRANSPORT_REBOUND')
        self._neck=neck

    def begin_development_move(self, target_rad):
        """Admit the declared first nonzero MOVE before stopped-demand inference."""
        domain = self.controller.config.get('required_search_domain_rad')
        if (threading.get_ident() != self._entry or self._neck is None
                or self._local_state is None or not self._local_state.controller_bound
                or self._active is not None or self.commands or self.observations
                or self._pending_request is not None or self.result is not None
                or type(domain) not in (list,tuple) or len(domain) != 2
                or type(target_rad) not in (int,float) or target_rad != domain[0]):
            raise PermissionError('HEAD_INITIAL_MOVE_SCOPE_INVALID')
        self.primary.dispatch_guard()
        current = self.port.feedback_snapshot()
        now = self.monotonic()
        if (nanoseconds(now) >= self._local_state.search_deadline_ns
                or target_rad == current['positions'][0]):
            raise PermissionError('HEAD_INITIAL_MOVE_DEADLINE_OR_ZERO')
        committed = self._local_state.commit_search_state(motion_epoch=self._motion_epoch+1,
            target_rad=target_rad,lock_count=0,sequence=self._sequence,
            source_ns=current['source_ns'],decision_wall_s=now,reason='initial_development_move')
        self._motion_epoch, self._target = committed['motion_epoch'], committed['target_rad']
        command = dict(target_rad=self._target,sequence=self._sequence,source_ns=current['source_ns'],
            original_deadline_ns=self._local_state.search_deadline_ns,dispatch_wall_s=now,
            initial_development_move=True)
        self.commands.append(command)
        try:
            gid = self._neck.command_neck(self._target,session_id=self.controller.config['session_id'],
                attempt_id=self.controller.config['attempt_id'],
                observation_time_s=current['source_ns']*1e-9)
        except Exception:
            self.primary.fault('HEAD_INITIAL_MOVE_REFUSED')
            raise
        command['goal_uuid'], command['sdk_return_wall_s'] = gid, self.monotonic()
        self._active = command
        self.controller.target = self._target
        self.emit('SEARCH_OWNED_GOAL_DISPATCHED',command=deepcopy(command))
        return gid

    def _settle(self,current):
        if self._active is None:return True
        command=self._active;gid=command['goal_uuid']
        with self.port._lock:
            state=dict(self.port._goals[gid])
        response=state.get('result')
        command['accepted']=state.get('accepted');command['terminal_status']=getattr(response,'status',None)
        command['result_error_code']=getattr(getattr(response,'result',None),'error_code',None)
        if (state.get('accepted') is False or state.get('error') is not None
                or (response is not None and (response.status!=4 or response.result.error_code!=0))):
            raise PermissionError('HEAD_SEARCH_OWNED_GOAL_FAILED')
        if response is None:return False
        if 'terminal_observed_wall_s' not in command:
            command['terminal_observed_wall_s']=self.monotonic()
            command['terminal_source_floor_ns']=current['decision']['sim_ns']
            return False
        # Originals are append-only. The cache lock copies references only;
        # sealed bootstrap history is neither decoded nor copied by this loop.
        with self.port._lock:originals=tuple(self.port._head_samples)
        samples=tuple(row for row in originals if row['wall_s']>command['terminal_observed_wall_s'])
        proof=self.settlement(samples,state,target_rad=command['target_rad'],
            position_tolerance_rad=self.controller.config['goal_tolerance_rad'],
            velocity_tolerance_rad_s=min(self.stop_velocity,self.controller.config['settle_velocity_rad_s']),
            source_floor_ns=command['terminal_source_floor_ns'],dispatch_wall_s=command['dispatch_wall_s'],
            terminal_wall_s=command['terminal_observed_wall_s'])
        if proof is None:return False
        command['confirming_samples']=deepcopy(proof);command['settled_wall_s']=self.monotonic()
        self._settled_floor=proof[-1]['source_ns'];self._settled_wall_s=command['settled_wall_s']
        self._active=None
        self.emit('SEARCH_OWNED_GOAL_SETTLED',command=deepcopy(command))
        return True

    def _submit_observation_request(self):
        """Submit at most one frozen stopped-observation request to the owner."""
        if self._active is not None:
            raise PermissionError('HEAD_SEARCH_OBSERVATION_BEFORE_SETTLEMENT')
        if self._pending_request is not None:return None
        now=self.monotonic();deadline=self._local_state.search_deadline_ns
        if nanoseconds(now)>=deadline:
            raise PermissionError('HEAD_SEARCH_OBSERVATION_DEADLINE')
        scope=self._local_state.scope
        request=dict(epoch=scope['epoch'],generation=scope['generation'],
            session_id=scope['session_id'],policy_sha256=scope['policy_sha256'],schema_version=1,
            simulation_policy_sha256=digest(self._policy.readback()),
            motion_epoch=len(self._local_state.inventory),
            observation_sequence=self._observation_sequence+1,
            settled_source_floor_ns=self._settled_floor,settled_wall_s=self._settled_wall_s,
            requested_wall_s=now,search_deadline_ns=deadline)
        self._pending_request=self.owner.request_observation(request)
        self.emit('SEARCH_OBSERVATION_REQUESTED',request=dict(self._pending_request),
            budget=self._budget.readback())
        return self._pending_request

    @property
    def observation_budget(self):
        return None if self._budget is None else self._budget.readback()

    @property
    def pending_observation_request(self):
        return None if self._pending_request is None else dict(self._pending_request)

    @property
    def search_state(self):
        """Committed authoritative target/lock when a local state is bound."""
        if self._local_state is None:return None
        return self._local_state.search_state

    def _discard_observation(self, row, outcome):
        if not self._budget.reobserve(self._motion_epoch,outcome,self.monotonic()):
            return self._terminal(dict(status='SEARCH_OBSERVATION_BUDGET_EXHAUSTED',
                found=False,observation_outcome=outcome,budget=self._budget.readback()))
        self.emit('SEARCH_OBSERVATION_DISCARDED',sequence=row['sequence'],
            observation_sequence=self._observation_sequence,outcome=outcome,
            budget=self._budget.readback())
        self._submit_observation_request()
        return None

    def _exposure_expired(self, row, current):
        deadline=row['deadline_ns']
        if type(deadline) is not int or deadline<=0:
            raise PermissionError('HEAD_SEARCH_EXPOSURE_DEADLINE_INVALID')
        source_age=current['decision']['sim_ns']-row['source_ns']
        if source_age<0:
            raise PermissionError('HEAD_SEARCH_EXPOSURE_FUTURE_SOURCE')
        return (nanoseconds(self.monotonic())>=deadline or self._policy is not None
            and source_age>nanoseconds(self._policy.camera_source_age_s))

    def _terminal(self,result):
        if self._local_state is not None and result['status']=='TARGET_LOCKED':
            self._local_state.commit_search_state(motion_epoch=self._motion_epoch,
                target_rad=self._target,lock_count=self.controller.lock_count,
                sequence=self._sequence,source_ns=None,decision_wall_s=self.monotonic(),
                reason='lock')
        self.result=deepcopy(result)
        self.emit('SEARCH_CONTROLLER_TERMINAL',result=self.result,commands=deepcopy(self.commands))
        if result['status']!='TARGET_LOCKED':self.primary.fault('HEAD_SEARCH_'+result['status'])
        return deepcopy(self.result)

    def tick(self):
        try:
            if threading.get_ident()!=self._entry or self._neck is None:
                raise PermissionError('HEAD_SEARCH_CONTROL_OWNER_INVALID')
            if self.result is not None:return deepcopy(self.result)
            self.owner.infer();self.primary.dispatch_guard();current=self.port.feedback_snapshot()
            now=self.monotonic()
            self.emit('SEARCH_CONTROL_DECISION',decision=current['decision'],
                original_joint={key:value for key,value in current.items() if key!='decision'},
                controller_thread_native_id=threading.get_native_id())
            terminal=self.controller.advance_deadline(now)
            if terminal is not None:return self._terminal(terminal)
            settled=self._settle(current)
            if self._local_state is not None:
                row=self.owner.next_completed_observation(self._observation_sequence)
            else:
                row=self.owner.next_completed_exposure(self._sequence)
            if row is None:
                if self._local_state is not None and settled:self._submit_observation_request()
                return None
            if (self._local_state is not None
                    and row.get('motion_epoch')!=self._motion_epoch):
                raise PermissionError('HEAD_SEARCH_COMPLETED_EPOCH_INVALID')
            if self._local_state is not None:
                outcome=row.get('observation_outcome')
                if outcome not in ('VALID','EXPIRED','SHORT_DROP'):
                    raise PermissionError('HEAD_SEARCH_OBSERVATION_OUTCOME_INVALID')
                if (type(row.get('observation_sequence')) is not int
                        or row['observation_sequence']!=self._observation_sequence+1
                        or self._pending_request is None
                        or row['observation_sequence']!=self._pending_request['observation_sequence']
                        or (row['session_id'],row['epoch'])!=(
                            self.controller.config['session_id'],self.controller.config['attempt_id'])):
                    raise PermissionError('HEAD_SEARCH_COMPLETED_OBSERVATION_INVALID')
                if row['sequence'] is None:
                    if outcome=='VALID':
                        raise PermissionError('HEAD_SEARCH_COMPLETED_SEQUENCE_INVALID')
                elif type(row['sequence']) is not int or row['sequence']!=self._sequence+1:
                    raise PermissionError('HEAD_SEARCH_COMPLETED_SEQUENCE_INVALID')
                self._pending_request=None
                self._observation_sequence=row['observation_sequence']
                if row['sequence'] is not None:self._sequence=row['sequence']
                if outcome!='VALID':
                    # A legitimately discarded completion changes no target and
                    # no lock; it is charged to the one original retry budget.
                    return self._discard_observation(row,outcome)
            else:
                if type(row['sequence']) is not int or row['sequence']!=self._sequence+1:
                    raise PermissionError('HEAD_SEARCH_COMPLETED_SEQUENCE_INVALID')
                self._sequence=row['sequence']
            if not settled or row['source_ns']<=self._settled_floor:
                self.emit('SEARCH_EXPOSURE_BEFORE_OWNED_SETTLEMENT',sequence=self._sequence,
                    source_ns=row['source_ns'],settled_source_floor_ns=self._settled_floor)
                return None
            deadline=row['deadline_ns']
            frame,feedback=map_owned_search_exposure(row,self.controller.config)
            if self._exposure_expired(row,current):
                if self._local_state is not None:return self._discard_observation(row,'EXPIRED')
                raise PermissionError('HEAD_SEARCH_SELECTED_EXPOSURE_EXPIRED')
            core_wall=self.monotonic()
            context=dict(session_id=self.controller.config['session_id'],
                attempt_id=self.controller.config['attempt_id'],policy=self.port.feedback_policy,
                sample={key:value for key,value in current.items()
                    if key not in ('decision','receipt_age_s','source_age_s')},decision=current['decision'])
            candidate=deepcopy(self.controller) if self._local_state is not None else self.controller
            decision=candidate.tick(frame,feedback,core_wall,joint_context=context)
            self.primary.dispatch_guard()
            latest=self.port.feedback_snapshot()
            if self._exposure_expired(row,latest):
                if self._local_state is not None:return self._discard_observation(row,'EXPIRED')
                raise PermissionError('HEAD_SEARCH_SELECTED_EXPOSURE_EXPIRED')
            self.controller=candidate
            self.observations.append(dict(sequence=self._sequence,source_ns=row['source_ns'],
                track_id=self.controller.track,lock_count=self.controller.lock_count,
                core_tick_wall_s=core_wall,current_joint=context['sample'],
                current_joint_decision=context['decision'],decision=deepcopy(decision)))
            self.emit('SEARCH_EXPOSURE_DECISION',observation=deepcopy(self.observations[-1]))
            if 'found' in decision:return self._terminal(decision)
            if decision['stop']:
                raise PermissionError('HEAD_SEARCH_'+decision['status'])
            target=decision['neck_target_rad']
            if target==self._target:return None
            if self._local_state is not None:
                committed=self._local_state.commit_search_state(motion_epoch=self._motion_epoch+1,
                    target_rad=target,lock_count=0,sequence=self._sequence,
                    source_ns=row['source_ns'],decision_wall_s=self.monotonic(),reason='dispatch')
                self._motion_epoch=committed['motion_epoch']
                self._target=committed['target_rad']
            self.primary.dispatch_observation_deadline(deadline*1e-9)
            command=dict(target_rad=target,sequence=self._sequence,source_ns=row['source_ns'],
                original_deadline_ns=deadline,dispatch_wall_s=self.monotonic())
            # Preserve an incomplete command if the existing dispatcher sends
            # before a later boundary refuses. Its authoritative UUID inventory
            # still belongs to primary/CPU and must participate in owned stop.
            self.commands.append(command)
            gid=self._neck.command_neck(target,session_id=self.controller.config['session_id'],
                attempt_id=self.controller.config['attempt_id'],observation_time_s=frame['sim_time_s'])
            command['goal_uuid']=gid;command['sdk_return_wall_s']=self.monotonic()
            self.primary.dispatch_observation_deadline(None)
            if self._local_state is None:self._target=target
            self._active=command
            self.emit('SEARCH_OWNED_GOAL_DISPATCHED',command=deepcopy(command))
            return None
        except Exception:
            self.primary.fault('HEAD_OWNED_SEARCH_REFUSED')
            raise
