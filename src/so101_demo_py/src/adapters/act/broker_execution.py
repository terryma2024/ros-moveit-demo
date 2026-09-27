"""The common broker's paired driver; every send is generation fenced."""

import threading
import time

from control_msgs.action import FollowJointTrajectory

from so101_demo.act.execution import ActExecutionAdapter
from so101_demo.act.joints import ARM_JOINTS
from so101_demo.act.permits import PermitAuthority
from .ros_execution import trajectory_message


class BrokerControllerPort:
    def __init__(self,broker,kind,context_port):
        self.broker,self.kind,self.context_port=broker,kind,context_port

    def send(self,goal):
        message=FollowJointTrajectory.Goal();message.trajectory=trajectory_message(goal)
        return self.broker.dispatch(self.context_port(),self.kind,message)
        if self.kind=='neck':
            return self.broker.dispatch(self.context_port(),self.kind,message,
                                        trusted_search_neck=True)

    def accepted(self,gid):return self.broker.driver.goal_state(gid)['accepted']
    def cancel(self,gid):self.broker.driver.cancel(gid)
    def stopped(self):return self.broker.driver.stopped()


class BrokerPairedExecution:
    def __init__(self,broker,*,snapshot_port,check_port,reference_port,sim_clock,
                 submit_lead_s,accept_timeout_s,stop_timeout_s,permit_ttl_s,path_port=None,
                 proof_source_port=None,proof_state_port=None,
                 proof_reference_port=None,proof_clock_port=None,
                 proof_goal_port=None,proof_timing=None,
                 max_observation_age_s=None,max_prefix_age_s=None):
        proof_ports=(proof_source_port,proof_state_port,proof_reference_port,
                     proof_clock_port,proof_goal_port,proof_timing,
                     max_observation_age_s,max_prefix_age_s)
        if any(value is not None for value in proof_ports) and (
                any(value is None for value in proof_ports)
                or not all(callable(port) for port in proof_ports[:5])):
            raise ValueError('PATH_PROOF_PORT_INVALID')
        self.broker=broker;self._ticket=None;self._lock=threading.RLock();self._pairs={}
        self.permits=PermitAuthority(snapshot_port=lambda:snapshot_port(self._ticket),
            check_port=check_port,generation_port=lambda:broker.ownership.generation,
            ttl_s=permit_ttl_s,proof_source_port=proof_source_port,
            proof_state_port=proof_state_port,
            proof_ticket_port=(lambda:self._ticket) if proof_source_port is not None else None,
            max_observation_age_s=max_observation_age_s,
            max_prefix_age_s=max_prefix_age_s)
        self.adapter=ActExecutionAdapter(
            BrokerControllerPort(broker,'arm',lambda:self._ticket),
            BrokerControllerPort(broker,'gripper',lambda:self._ticket),
            permit_port=self.permits,sim_clock=sim_clock,progress=lambda:time.sleep(.001),
            submit_lead_s=submit_lead_s,accept_timeout_s=accept_timeout_s,
            stop_timeout_s=stop_timeout_s,reference_port=reference_port,path_port=path_port,
            proof_reference_port=proof_reference_port,
            proof_clock_port=proof_clock_port,proof_goal_port=proof_goal_port,
            proof_timing=proof_timing)

    def _require_source_proof(self):
        if (self.broker.reservation_port is not None
                and self.permits.proof_source_port is None):
            raise PermissionError('PATH_PROOF_SOURCE_UNWIRED')

    def _bind(self,ticket):
        self.broker.ownership.require_ticket(ticket)
        if ticket[2]!='act':raise PermissionError('PREFIX_OWNER_INVALID')
        with self._lock:
            if self._ticket!=ticket:
                # Baseline cancellation can invalidate even the never-bound
                # adapter. Refresh it only after the common driver confirms
                # all real controllers and fresh physical feedback stopped.
                if not self.broker.driver.stopped():
                    raise RuntimeError('CONTROL_NOT_STOPPED')
                self.adapter.poll_stop()
                self.adapter.begin_attempt(ticket[3],ticket[4]);self._ticket=ticket

    def approve(self,ticket,prefix):
        self._require_source_proof()
        self._bind(ticket)
        return self.permits.approve(prefix)

    def approve_with_source(self,ticket,prefix,receipt):
        self._require_source_proof()
        self._bind(ticket)
        return self.permits.approve_with_source(prefix,receipt)

    def submit(self,ticket,prefix,permit):
        self._require_source_proof()
        self._bind(ticket)
        try:
            gid=self.adapter.submit(prefix,permit)
            with self._lock:self._pairs[gid]=tuple(self.adapter.current_goal_ids)
            return gid
        except Exception:
            # Pair rejection or uncertain response closes the entire ownership
            # generation. No subsequent teacher/manual command can slip through.
            with self.broker._lock:
                self.broker.ownership.revoke('CONTROLLER_PAIR_FAILED');self.broker.tick()
            raise

    def invalidate(self,reason):self.adapter.invalidate(reason)

    def goal_state(self,gid):
        with self._lock:ids=self._pairs[gid]
        states=[self.broker.driver.goal_state(item) for item in ids]
        accepted=all(state['accepted'] is True for state in states)
        terminal=all(state['status'] in (4,5,6) for state in states)
        status=None;result=None;segment_stop_confirmed=False
        if terminal:
            success=all(state['status']==4 and state['result']['error_code']==0 for state in states)
            status=4 if success else 6
            result={'arm':states[0]['result'],'gripper':states[1]['result']}
            if success:
                # A successful action result can precede physical settling.
                # Keep refreshing the driver's negative cancellation baseline
                # while this ACT lease is RUNNING, then check fresh feedback.
                self.broker.driver.refresh_idle()
                segment_stop_confirmed=self.broker.driver.stopped()
        return dict(accepted=accepted,status=status,result=result,
                    goal_ids=ids,controllers=states,audit=self.adapter.audit,
                    segment_stop_confirmed=segment_stop_confirmed)
