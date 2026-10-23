"""Coordinated timed arm/gripper submission with a latched physical-stop gate."""

import copy
import hashlib
import json
import threading
import time

from .contracts import finite, identifier, validate_action, validate_action_prefix, vector
from .goal_pair_telemetry import CONTROLLERS, LoadSampler, late_controllers, summarize_goal_pairs
from .joints import ARM_JOINTS, joint_limits_for


def split_positions(rows):
    checked=tuple(validate_action(row) for row in rows)
    if not checked: raise ValueError('PREFIX_EMPTY')
    return tuple(row[:5] for row in checked), tuple((row[5],) for row in checked)


def prefix_sha256(prefix):
    checked=validate_action_prefix(prefix)
    return hashlib.sha256(json.dumps(checked,sort_keys=True,separators=(',',':'),
                                     allow_nan=False).encode()).hexdigest()


def bounded_positions(row, profile="act"):
    checked=validate_action(row)
    limits=joint_limits_for(profile)
    if any(not limits[name][0]<=value<=limits[name][1]
           for name,value in zip(ARM_JOINTS,checked,strict=True)):
        raise ValueError('JOINT_LIMIT_INVALID')
    return checked


class ActExecutionAdapter:
    """The broker owns this driver; ports must report actual action/velocity state.

    accepted returns None while the actual goal response is pending. stopped is
    true only after cancellation/terminal acknowledgement and fresh zero-speed
    feedback, including pending requests. The reference port evaluates the actual
    controller interpolation at the requested future simulation time.
    """

    def __init__(self, arm, gripper, *, permit_port, sim_clock, monotonic=time.monotonic,
                 progress, submit_lead_s, accept_timeout_s, stop_timeout_s, reference_port,
                 path_port=None, proof_reference_port=None, proof_clock_port=None,
                 proof_goal_port=None, proof_timing=None, load_sampler=None):
        self.arm,self.gripper=arm,gripper
        self.permit_port,self.sim_clock=permit_port,sim_clock
        self.monotonic,self.progress=monotonic,progress
        self.reference_port=reference_port
        if path_port is not None and not callable(path_port):raise ValueError('EXECUTION_PATH_PORT_INVALID')
        self.path_port=path_port
        self.proof_reference_port=proof_reference_port
        self.proof_clock_port=proof_clock_port
        self.proof_goal_port=proof_goal_port
        self.proof_timing=None if proof_timing is None else dict(proof_timing)
        if any(port is not None and not callable(port) for port in (
                proof_reference_port,proof_clock_port,proof_goal_port)):
            raise ValueError('PROOF_COMMIT_PORT_INVALID')
        self.submit_lead_s=finite(submit_lead_s)
        self.accept_timeout_s=finite(accept_timeout_s)
        self.stop_timeout_s=finite(stop_timeout_s)
        if not (0<self.accept_timeout_s<self.submit_lead_s and self.stop_timeout_s>0):
            raise ValueError('EXECUTION_TIMING_INVALID')
        self._lock=threading.RLock()
        self.state='STOPPED'; self.current_goal_ids=(None,None)
        self._all_goals=[]; self._identity=None; self._sequence=-1; self._generation=0
        self.audit=[]; self._submitting=False
        # Diagnostics only (see goal_pair_telemetry): never read by the control path.
        self.pair_log=[]; self.last_pair=None; self._load_sampler=load_sampler or LoadSampler()

    def _safely(self,function,*args):
        try: return function(*args)
        except Exception: return None

    def _port_timing(self,port,gid):
        timing=getattr(port,'goal_timing',None)
        return {} if timing is None else (timing(gid) or {})

    def _in_flight(self,port):
        count=getattr(port,'unfinished_goals',None)
        return None if count is None else count()

    def _open_pair(self,sequence,start,send_sim_s):
        # Plain values only: nothing here may take time on the send path (no port call, no /proc read); the in-flight counts and the
        # load sample are taken when the pair is closed.
        pair=dict(sequence=sequence,target_start_sim_s=start,send_sim_s=send_sim_s,goal_ids=dict.fromkeys(CONTROLLERS),
            send_wall_s=dict.fromkeys(CONTROLLERS),accept_wall_s=dict.fromkeys(CONTROLLERS),
            accept_latency_s=dict.fromkeys(CONTROLLERS),accept_thread=dict.fromkeys(CONTROLLERS),
            in_flight_at_check=None,decision_thread=threading.current_thread().name,load=None,
            outcome=None,late_controller=None,check_wall_s=None,check_sim_s=None,accept_sim_s=None,
            late_arrival_latency_s={})
        self.pair_log.append(pair); self.last_pair=pair
        return pair

    def _refresh_pair(self,pair):
        """Re-read the ports' own send/accept times (the accept callback may run after the decision)."""
        for name,port in zip(CONTROLLERS,(self.arm,self.gripper),strict=True):
            gid=pair['goal_ids'].get(name)
            if gid is None: continue
            timing=self._safely(self._port_timing,port,gid) or {}
            sent,accepted=timing.get('send_wall_s'),timing.get('accept_wall_s')
            pair['send_wall_s'][name]=sent; pair['accept_wall_s'][name]=accepted
            pair['accept_thread'][name]=timing.get('accept_thread')
            latency=None if sent is None or accepted is None else accepted-sent
            pair['accept_latency_s'][name]=latency
            if pair['outcome']=='timeout' and name in late_controllers(pair) and latency is not None:
                pair['late_arrival_latency_s'][name]=latency

    def _note_sent(self,pair,sent,sent_done_wall_s):
        pair['sent_done_wall_s']=sent_done_wall_s
        pair['goal_ids']=dict(zip(CONTROLLERS,sent,strict=True))
        self._refresh_pair(pair)

    def _close_pair(self,pair,outcome,responses,check_wall_s,check_sim_s):
        if pair is None: return
        pair.update(outcome=outcome,check_wall_s=check_wall_s,check_sim_s=check_sim_s)
        if outcome=='accepted': pair['accept_sim_s']=check_sim_s
        else:
            late=[name for name,result in zip(CONTROLLERS,responses,strict=True) if result is not True]
            pair['late_controller']=None if not late else ('both' if len(late)==2 else late[0])
        # sampled here, after the decision, so that nothing is added between the goals being sent and their acceptance being read;
        # the counts include this pair's own two goals while they are unfinished
        pair['in_flight_at_check']={name:self._safely(self._in_flight,port)
                                    for name,port in zip(CONTROLLERS,(self.arm,self.gripper),strict=True)}
        pair['load']=self._safely(self._load_sampler.sample)
        self._refresh_pair(pair)

    def goal_response_summary(self):
        """Diagnostics only: acceptance latency statistics over the pairs of this attempt (see `summarize_goal_pairs`)."""
        for pair in self.pair_log: self._safely(self._refresh_pair,pair)
        return summarize_goal_pairs(self.pair_log,accept_timeout_s=self.accept_timeout_s)

    def begin_attempt(self,session_id,attempt_id):
        identity=(identifier(session_id),identifier(attempt_id))
        with self._lock:
            if self.state!='STOPPED' or self._submitting:
                raise RuntimeError('CONTROL_NOT_STOPPED')
            if self._all_goals and not all(port.stopped() for port in (self.arm,self.gripper)):
                raise RuntimeError('CONTROL_NOT_STOPPED')
            self._identity=identity; self._sequence=-1; self._generation+=1
            self.pair_log=[]; self.last_pair=None
            self.state='READY'; self.current_goal_ids=(None,None); self._all_goals=[]

    def _send(self,port,goal,generation):
        goal_id=identifier(port.send(goal))
        with self._lock:
            self._all_goals.append((port,goal_id))
            if generation!=self._generation or self.state in ('STOPPING','STOPPED'):
                port.cancel(goal_id)
                raise RuntimeError('CONTROLLER_PAIR_FAILED: revoked during send')
        return goal_id

    def _proof_time_check(self,proof,readback,start):
        from .path_proof import require_commit_window
        sample=readback['dual_clock']
        current=self.proof_clock_port()
        if (sample['continuous'] is not True
                or current['continuous'] is not True
                or finite(current['wall_s'],nonnegative=True)
                   < finite(sample['wall_s'],nonnegative=True)
                or finite(current['sim_s'],nonnegative=True)
                   < finite(sample['sim_s'],nonnegative=True)):
            raise ValueError('PROOF_CLOCK_INVALID')
        return require_commit_window(
            proof,state_received_wall_s=sample['wall_s'],
            accepted_wall_s=current['wall_s'],accepted_sim_s=current['sim_s'],
            start_sim_s=start,clock_error_s=max(
                finite(sample['error_s'],nonnegative=True),
                finite(current['error_s'],nonnegative=True)),
            clock_continuous=True,**self.proof_timing)

    def _prepare_proof_goals(self,proof,checked):
        from .path_proof import goal_pair_from_proof, require_proven_goals
        if (self.proof_reference_port is None or self.proof_clock_port is None
                or self.proof_goal_port is None or self.proof_timing is None
                or not callable(getattr(self.permit_port,'current_proof_state',None))
                or not callable(getattr(self.permit_port,'close_proof',None))):
            raise PermissionError('PROOF_COMMIT_PORT_REQUIRED')
        readback=self.permit_port.current_proof_state(proof)
        if readback['controller_stop_confirmed'] is not True:
            raise PermissionError('PROOF_STOP_UNCONFIRMED')
        sample=readback['dual_clock']
        start=round((finite(sample['sim_s'],nonnegative=True)
                     + self.submit_lead_s)*1_000_000_000)/1_000_000_000
        reference=self.proof_reference_port(start)
        if (reference['requested_sim_time_s']!=start
                or vector(reference['positions'],6)!=proof.controller_start_positions
                or vector(reference['velocities'],6)!=proof.controller_start_velocities):
            raise PermissionError('PROOF_REFERENCE_CHANGED')
        bridge=readback['snapshot']['controller_bridge']['time_s']
        goals=goal_pair_from_proof(
            proof,start_time_s=start,bridge_time_s=bridge,
            reference_positions=reference['positions'])
        require_proven_goals(
            proof,goals,bridge_time_s=bridge,
            reference_positions=reference['positions'])
        self._proof_time_check(proof,readback,start)
        if self.proof_goal_port(goals,proof,copy.deepcopy(readback)) is not True:
            raise PermissionError('PATH_REJECTED')
        require_proven_goals(
            proof,goals,bridge_time_s=bridge,
            reference_positions=reference['positions'])
        if self.permit_port.current_proof_state(proof)['controller_stop_confirmed'] is not True:
            raise PermissionError('PROOF_STOP_UNCONFIRMED')
        self._proof_time_check(proof,readback,start)
        return goals,start,readback

    def submit(self,prefix,permit):
        checked=validate_action_prefix(prefix)
        for row in checked['positions']: bounded_positions(row)
        with self._lock:
            if self.state not in ('READY','EXECUTING') or self._submitting:
                raise RuntimeError('SUBMISSION_DISABLED')
            if (checked['session_id'],checked['attempt_id'])!=self._identity:
                raise ValueError('ATTEMPT_INVALID')
            if checked['sequence']<=self._sequence: raise ValueError('SEQUENCE_INVALID')
            self._submitting=True
            generation=self._generation
            previous=self.current_goal_ids
        sent=[]
        proof=None; pair=None; send_sim_s=None; self.last_pair=None
        try:
            consumed=self.permit_port.require(permit,checked)
            from .path_proof import PathProof
            if isinstance(consumed,PathProof):
                proof=consumed
                if previous!=(None,None):
                    raise PermissionError('PROOF_REPLACEMENT_FORBIDDEN')
                goals,start,proof_readback=self._prepare_proof_goals(proof,checked)
                send_sim_s=proof_readback['dual_clock']['sim_s']
            else:
                now=finite(self.sim_clock(),nonnegative=True)
                start=now+self.submit_lead_s; send_sim_s=now
                if start>=checked['target_times_s'][0]-1e-6:
                    raise ValueError('PREFIX_LATE')
                held=bounded_positions(self.reference_port(start))
                arm,grip=split_positions((held,)+checked['positions'])
                offsets=(0.,)+tuple(target-start for target in checked['target_times_s'])
                goals=tuple(dict(joint_names=names,header_stamp_s=start,time_from_start_s=offsets,
                                positions=rows,session_id=checked['session_id'],
                                attempt_id=checked['attempt_id'],sequence=checked['sequence'],
                                prefix_sha256=prefix_sha256(checked))
                    for names,rows in ((ARM_JOINTS[:5],arm),(ARM_JOINTS[5:],grip)))
                if self.path_port is not None and self.path_port(goals,checked) is not True:
                    raise PermissionError('PATH_REJECTED')
            with self._lock:
                if generation!=self._generation:raise RuntimeError('revoked during preparation')
                self._sequence=checked['sequence']
            pair=self._safely(self._open_pair,checked['sequence'],start,send_sim_s)
            # No inference lock, and stop may invalidate this operation at any point.
            for port,old in zip((self.arm,self.gripper),previous,strict=True):
                if old is not None: port.cancel(old)
            for port,goal in zip((self.arm,self.gripper),goals,strict=True):
                with self._lock:
                    if generation!=self._generation: raise RuntimeError('revoked before send')
                if proof is not None:
                    from .path_proof import require_proven_goals
                    require_proven_goals(
                        proof,goals,
                        bridge_time_s=proof_readback['snapshot']['controller_bridge']['time_s'],
                        reference_positions=proof.controller_start_positions)
                    fresh=self.permit_port.current_proof_state(proof)
                    if not sent and fresh['controller_stop_confirmed'] is not True:
                        raise PermissionError('PROOF_STOP_UNCONFIRMED')
                    self._proof_time_check(proof,proof_readback,start)
                sent.append(self._send(port,goal,generation))
            wait_start=self.monotonic(); deadline=wait_start+self.accept_timeout_s
            if pair is not None: self._safely(self._note_sent,pair,tuple(sent),wait_start)
            sim_now=None
            while True:
                with self._lock:
                    if generation!=self._generation: raise RuntimeError('revoked before acceptance')
                responses=tuple(port.accepted(gid) for port,gid in zip(
                    (self.arm,self.gripper),sent,strict=True))
                if proof is not None:
                    self._proof_time_check(proof,proof_readback,start)
                elif (sim_now:=self.sim_clock())>=start:
                    self._safely(self._close_pair,pair,'after_common_start',responses,self.monotonic(),sim_now)
                    raise RuntimeError('acceptance after common start')
                if any(result is False for result in responses):
                    self._safely(self._close_pair,pair,'rejected',responses,self.monotonic(),sim_now)
                    raise RuntimeError('goal rejected')
                if all(result is True for result in responses): break
                check_wall=self.monotonic()
                if check_wall>=deadline:
                    self._safely(self._close_pair,pair,'timeout',responses,check_wall,sim_now)
                    raise RuntimeError('goal response timeout')
                self.progress()
            if proof is not None:
                self.permit_port.current_proof_state(proof)
                self._proof_time_check(proof,proof_readback,start)
            with self._lock:
                if generation!=self._generation: raise RuntimeError('revoked after acceptance')
                self.current_goal_ids=tuple(sent); self.state='EXECUTING'
                audit=dict(prefix_sha256=prefix_sha256(checked),goals=goals,
                    goal_ids=tuple(sent),accepted_wall_s=self.monotonic(),accepted_sim_s=self.sim_clock())
                self.audit.append(audit)
                self._safely(self._close_pair,pair,'accepted',responses,audit['accepted_wall_s'],audit['accepted_sim_s'])
            return ':'.join(sent)
        except Exception as error:
            if pair is not None and pair['outcome'] is None: pair['outcome']='error: '+type(error).__name__
            if sent or self._all_goals or not isinstance(error,(ValueError,PermissionError)):
                self.stop('CONTROLLER_PAIR_FAILED')
            if not sent and isinstance(error,(ValueError,PermissionError)):raise
            raise RuntimeError(f'CONTROLLER_PAIR_FAILED: {error}') from error
        finally:
            if proof is not None and callable(getattr(self.permit_port,'close_proof',None)):
                self.permit_port.close_proof(proof)
            with self._lock: self._submitting=False

    def invalidate(self,reason):
        identifier(reason)
        with self._lock:
            self.state='STOPPING'; self._generation+=1
            self.permit_port.revoke(reason)
            goals=tuple(self._all_goals)
        for port,gid in goals:
            port.cancel(gid)

    def stop(self,reason):
        identifier(reason)
        with self._lock:
            self.state='STOPPING'; self._generation+=1
            self.permit_port.revoke(reason)
            goals=tuple(self._all_goals)
        errors=[]
        for port,gid in goals:
            try: port.cancel(gid)
            except Exception as error: errors.append(repr(error))
        self.audit.append(dict(stop_reason=reason,requested_wall_s=self.monotonic(),
                               cancel_errors=errors))
        deadline=self.monotonic()+self.stop_timeout_s
        while self.poll_stop()!='STOPPED' and self.monotonic()<deadline:
            self.progress()
        return self.state

    def poll_stop(self):
        with self._lock:
            if self.state=='STOPPING':
                # During a failed submit, every already sent/pending port must
                # acknowledge and stop. Late sends are cancelled by _send.
                if not self._all_goals or all(port.stopped() for port in (self.arm,self.gripper)):
                    self.state='STOPPED'
            return self.state
