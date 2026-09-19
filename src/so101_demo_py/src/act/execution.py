"""Coordinated timed arm/gripper submission with a latched physical-stop gate."""

import hashlib
import json
import threading
import time

from .contracts import finite, identifier, validate_action, validate_action_prefix
from .joints import ARM_JOINTS, JOINT_LIMITS


def split_positions(rows):
    checked=tuple(validate_action(row) for row in rows)
    if not checked: raise ValueError('PREFIX_EMPTY')
    return tuple(row[:5] for row in checked), tuple((row[5],) for row in checked)


def prefix_sha256(prefix):
    checked=validate_action_prefix(prefix)
    return hashlib.sha256(json.dumps(checked,sort_keys=True,separators=(',',':'),
                                     allow_nan=False).encode()).hexdigest()


def bounded_positions(row):
    checked=validate_action(row)
    if any(not JOINT_LIMITS[name][0]<=value<=JOINT_LIMITS[name][1]
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
                 progress, submit_lead_s, accept_timeout_s, stop_timeout_s, reference_port, path_port=None):
        self.arm,self.gripper=arm,gripper
        self.permit_port,self.sim_clock=permit_port,sim_clock
        self.monotonic,self.progress=monotonic,progress
        self.reference_port=reference_port
        if path_port is not None and not callable(path_port):raise ValueError('EXECUTION_PATH_PORT_INVALID')
        self.path_port=path_port
        self.submit_lead_s=finite(submit_lead_s)
        self.accept_timeout_s=finite(accept_timeout_s)
        self.stop_timeout_s=finite(stop_timeout_s)
        if not (0<self.accept_timeout_s<self.submit_lead_s and self.stop_timeout_s>0):
            raise ValueError('EXECUTION_TIMING_INVALID')
        self._lock=threading.RLock()
        self.state='STOPPED'; self.current_goal_ids=(None,None)
        self._all_goals=[]; self._identity=None; self._sequence=-1; self._generation=0
        self.audit=[]; self._submitting=False

    def begin_attempt(self,session_id,attempt_id):
        identity=(identifier(session_id),identifier(attempt_id))
        with self._lock:
            if self.state!='STOPPED' or self._submitting:
                raise RuntimeError('CONTROL_NOT_STOPPED')
            if self._all_goals and not all(port.stopped() for port in (self.arm,self.gripper)):
                raise RuntimeError('CONTROL_NOT_STOPPED')
            self._identity=identity; self._sequence=-1; self._generation+=1
            self.state='READY'; self.current_goal_ids=(None,None); self._all_goals=[]

    def _send(self,port,goal,generation):
        goal_id=identifier(port.send(goal))
        with self._lock:
            self._all_goals.append((port,goal_id))
            if generation!=self._generation or self.state in ('STOPPING','STOPPED'):
                port.cancel(goal_id)
                raise RuntimeError('CONTROLLER_PAIR_FAILED: revoked during send')
        return goal_id

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
        try:
            self.permit_port.require(permit,checked)
            now=finite(self.sim_clock(),nonnegative=True)
            start=now+self.submit_lead_s
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
            # No inference lock, and stop may invalidate this operation at any point.
            for port,old in zip((self.arm,self.gripper),previous,strict=True):
                if old is not None: port.cancel(old)
            for port,goal in zip((self.arm,self.gripper),goals,strict=True):
                with self._lock:
                    if generation!=self._generation: raise RuntimeError('revoked before send')
                sent.append(self._send(port,goal,generation))
            deadline=self.monotonic()+self.accept_timeout_s
            while True:
                with self._lock:
                    if generation!=self._generation: raise RuntimeError('revoked before acceptance')
                responses=tuple(port.accepted(gid) for port,gid in zip(
                    (self.arm,self.gripper),sent,strict=True))
                if self.sim_clock()>=start: raise RuntimeError('acceptance after common start')
                if any(result is False for result in responses): raise RuntimeError('goal rejected')
                if all(result is True for result in responses): break
                if self.monotonic()>=deadline: raise RuntimeError('goal response timeout')
                self.progress()
            with self._lock:
                if generation!=self._generation: raise RuntimeError('revoked after acceptance')
                self.current_goal_ids=tuple(sent); self.state='EXECUTING'
                self.audit.append(dict(prefix_sha256=prefix_sha256(checked),goals=goals,
                    goal_ids=tuple(sent),accepted_wall_s=self.monotonic(),accepted_sim_s=self.sim_clock()))
            return ':'.join(sent)
        except Exception as error:
            if sent or self._all_goals or not isinstance(error,(ValueError,PermissionError)):
                self.stop('CONTROLLER_PAIR_FAILED')
            if not sent and isinstance(error,(ValueError,PermissionError)):raise
            raise RuntimeError(f'CONTROLLER_PAIR_FAILED: {error}') from error
        finally:
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
