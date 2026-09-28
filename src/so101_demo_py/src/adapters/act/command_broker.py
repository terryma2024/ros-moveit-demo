"""Single ownership authority with generation-fenced forwarding and Unix RPC."""

import fcntl
import json
import os
from pathlib import Path
import socket
import threading
import time
import uuid

from so101_demo.act.contracts import fields, identifier
from so101_demo.act.control_event_timeline import ControlEventTimeline
from so101_demo.act.ownership import OWNERS
from so101_demo.act.prefix_source import PrefixSourceAuthority

BASE=frozenset(('protocol_version','request_id','owner','session_id','attempt_id','lease_token','operation'))
EXTRA={'acquire':set(),'release':set(),'revoke':set(),'status':set(),'renew':set(),
       'submit':{'action_kind','goal'},'approve_prefix':{'prefix'},'submit_prefix':{'prefix','permit'},'prepare_reset':set(),'reset_world':{'reset_request'},'pause':{'paused'},'switch_controllers':{'activate','deactivate'},'finish_reset':set(),'cancel':{'goal_id'},'goal_status':{'goal_id'}}
MAX_REQUEST_BYTES=4*1024*1024


def endpoint_bytes(path):
    if not isinstance(path,str) or not Path(path).is_absolute() or '\x00' in path:
        raise ValueError('SOCKET_PATH_INVALID')
    count=len(os.fsencode(path))
    if count>107:raise ValueError('SOCKET_PATH_TOO_LONG')
    return count


class CommandBroker:
    def __init__(self,driver,*,ownership,simulation_session_id=None,prefix_executor=None,
                 prefix_source_authority=None,prefix_source_port=None,control_events=None,
                 reservation_port=None,authority=None):
        if (prefix_source_authority is None) != (prefix_source_port is None):
            raise ValueError('PREFIX_SOURCE_CONFIG_INVALID')
        if prefix_source_authority is not None and (
                not isinstance(prefix_source_authority,PrefixSourceAuthority)
                or not callable(prefix_source_port)):
            raise ValueError('PREFIX_SOURCE_CONFIG_INVALID')
        self.driver,self.ownership=driver,ownership
        if authority is not None:
            from so101_demo.adapters.act.broker_authority_composition import (
                BrokerAuthorityComposition,
            )
            if type(authority) is not BrokerAuthorityComposition:
                raise TypeError('BROKER_AUTHORITY_INVALID')
        self.authority=authority
        if reservation_port is not None and (
                not all(callable(getattr(reservation_port, name, None))
                        for name in ('arm_generation', 'reserve', 'close_generation'))
                or not all(callable(getattr(driver, name, None))
                           for name in ('prepare_goal', 'send_prepared', 'discard_prepared'))):
            raise TypeError('CONTROLLER_RESERVATION_PORT_INVALID')
        self.reservation_port=reservation_port
        self.prefix_executor=prefix_executor;self._pair_goals=set()
        self._prefix_sources=prefix_source_authority
        self._prefix_source_port=prefix_source_port
        self.simulation_session_id=simulation_session_id
        self.control_events=control_events if control_events is not None else ControlEventTimeline()
        if not isinstance(self.control_events,ControlEventTimeline):
            raise TypeError('CONTROL_EVENTS_INVALID')
        self.ownership.bind_control_events(self.control_events)
        if hasattr(self.driver,'bind_control_events'):
            self.driver.bind_control_events(self.control_events)
        self._lock=threading.RLock();self._participants={};self._goal_tickets={}
        self._stopping_generation=None;self.audit=[];self._fault_reason=None
        self._armed_generation=None
        self._acquire_pending=None
        self._release_pending=None        # exact (ticket, generation) release in flight
        self._cleanup_pending=None        # exact (generation, armed, reason) cleanup in flight
        self._reset_ticket=None;self._reset_applied=False;self._post_reset_ticket=None;self._writes=[]

    def issue_prefix_source(self,*,ticket,prefix,source,source_kind,
                            source_artifact_sha256,contact_policy_fingerprint,
                            output_received_wall_s=None):
        """Register a trusted in-process producer's exact source and prefix."""
        if self._prefix_sources is None:
            raise PermissionError('PREFIX_SOURCE_UNAVAILABLE')
        self.ownership.require_ticket(ticket)
        if ticket[2]!='act':raise PermissionError('PREFIX_OWNER_INVALID')
        receipt=self._prefix_sources.issue(
            ticket=ticket,prefix=prefix,source=source,source_kind=source_kind,
            source_artifact_sha256=source_artifact_sha256,
            contact_policy_fingerprint=contact_policy_fingerprint,
            output_received_wall_s=output_received_wall_s)
        try:self.ownership.require_ticket(ticket)
        except PermissionError:
            self._prefix_sources.revoke()
            raise
        return receipt

    def dispatch(self,ticket,kind,goal,*,trusted_search_neck=False):
        with self._lock,self.ownership.authorized(*ticket[1:]):
            self.ownership.require_ticket(ticket)
            self._post_reset_ticket=None
            self.control_events.record('submit_begin',generation=ticket[0],owner=ticket[2],
                                       session_id=ticket[3],attempt_id=ticket[4],detail=kind)
            try:
                if self.reservation_port is None:
                    gid=identifier(self.driver.submit(kind,goal))
                else:
                    gid=self._dispatch_reserved(ticket,kind,goal,
                                                trusted_search_neck=trusted_search_neck)
            except Exception:
                self.control_events.record('submit_uncertain',generation=ticket[0],
                                           owner=ticket[2],session_id=ticket[3],
                                           attempt_id=ticket[4],detail=kind)
                raise
            self._goal_tickets[gid]=ticket
            self.control_events.record('submit_registered',generation=ticket[0],
                                       owner=ticket[2],session_id=ticket[3],
                                       attempt_id=ticket[4],goal_id=gid,detail=kind)
            self.audit.append(dict(operation='submit',generation=ticket[0],owner=ticket[2],
                                   session_id=ticket[3],attempt_id=ticket[4],goal_id=gid))
            return gid

    def _dispatch_reserved(self,ticket,kind,goal,*,trusted_search_neck=False):
        gid=None
        registered=False
        try:
            if self._armed_generation!=ticket[0]:
                raise PermissionError('CONTROLLER_GENERATION_NOT_ARMED')
            if kind not in ('arm','gripper','neck'):
                raise PermissionError('CONTROLLER_RESERVATION_ROUTE_UNAVAILABLE')
            if kind=='neck' and (trusted_search_neck is not True or ticket[2]!='act'):
                raise PermissionError('NECK_SEARCH_PORT_REQUIRED')
            gid,goal_uuid=self.driver.prepare_goal(kind,goal)
            gid=identifier(gid)
            if not isinstance(goal_uuid,str) or str(uuid.UUID(goal_uuid))!=goal_uuid:
                raise ValueError('GOAL_UUID_INVALID')
            if gid in self._goal_tickets:raise RuntimeError('GOAL_ID_REUSED')
            self._goal_tickets[gid]=ticket
            registered=True
            # Gate 6 Batch 2 correction: when this broker owns a sealed resolver
            # and the ticket already carries an opaque permit handle, reserve
            # through the broker-owned binding. No caller-supplied identity,
            # snapshot, instant, deadline or receipt value exists on this path.
            if self.authority is not None:
                # Task 8 bound mode: derive the permit for *this* prepared goal.
                # There is no pre-existing handle lookup and no legacy fallback.
                try:
                    handle = self.authority.claim_prepared_goal(
                        ticket=ticket, role=kind, goal_uuid=goal_uuid, goal=goal)
                    reserved = self.reservation_port.reserve_bound(
                        ticket, kind, goal, goal_uuid, handle=handle)
                except Exception as error:
                    self.authority.revoke('BROKER_BOUND_CLAIM_FAILED')
                    raise PermissionError('CONTROLLER_RESERVATION_BOUND_FAILED') from error
            else:
                reserved = self.reservation_port.reserve(ticket, kind, goal, goal_uuid)
            if reserved is not True:
                raise PermissionError('CONTROLLER_RESERVATION_REJECTED')
            self.ownership.require_ticket(ticket)
            if identifier(self.driver.send_prepared(gid,kind,goal,goal_uuid))!=gid:
                raise RuntimeError('PREPARED_GOAL_ID_MISMATCH')
            return gid
        except Exception:
            if registered:self._goal_tickets.pop(gid,None)
            try:
                if gid is not None:self.driver.discard_prepared(gid)
            finally:
                self.ownership.revoke('CONTROLLER_RESERVATION_FAILED')
                self._stop_if_revoked()
            raise

    def _close_controller_generation(self,generation):
        if self.reservation_port is None:return
        try:
            if self.reservation_port.close_generation(generation) is False:
                raise RuntimeError('CONTROLLER_RESERVATION_CLOSE_UNCONFIRMED')
        except Exception as error:
            self._fault_reason='CONTROLLER_RESERVATION_CLOSE_UNCONFIRMED'
            self.audit.append(dict(operation='reservation_close_error',generation=generation,
                                   error=repr(error)))
            raise RuntimeError('CONTROLLER_RESERVATION_CLOSE_UNCONFIRMED') from error
        if self._armed_generation==generation:self._armed_generation=None

    def stop_attempt(self, reason, *, cancelled_event=None):
        """Close dispatch and signal cancellation under the same broker lock."""
        identifier(reason)
        if cancelled_event is not None and not isinstance(cancelled_event, threading.Event):
            raise TypeError('CANCEL_EVENT_INVALID')
        cleanup=None
        with self._lock:
            if cancelled_event is not None:cancelled_event.set()
            self.ownership.revoke(reason)
            if self.ownership.state=='STOPPING':
                generation=self.ownership.generation
                if generation!=self._stopping_generation:
                    # locked logical terminalization only: record the exact generation
                    # and clear dispatch state, but perform no controller/ROS I/O
                    self._stopping_generation=generation
                    self._reset_ticket=None;self._reset_applied=False;self._post_reset_ticket=None
                    if self._prefix_sources is not None:self._prefix_sources.revoke()
                    cleanup=(generation,self._armed_generation,
                             self.ownership.reason or 'REVOKED')
                    self._cleanup_pending=cleanup        # exact token for finalization
            # the in-lock call sees the generation already terminalized, so it only
            # refreshes/confirms the stop state and never repeats the I/O
            self._stop_if_revoked()
        if cleanup is not None:
            try:
                self._cleanup_unlocked_io(cleanup, propagate=True)   # caller sees the stop error
            except Exception:
                with self._lock:
                    if self._cleanup_pending==cleanup:
                        self._cleanup_pending=None
                raise                                    # no probe after a failed stop
            with self._lock:
                if self._cleanup_pending==cleanup:
                    self._cleanup_pending=None          # only this exact token finalizes
                self._stop_if_revoked()

    def _cleanup_unlocked_io(self,cleanup,*,propagate=False):
        """Unlocked terminalization I/O: controller close, prefix invalidate, ROS stop.

        ``propagate=True`` (the explicit stop_attempt entry point) surfaces a driver
        stop failure to the caller so a hazard dispatcher sees it. Background and
        connection-lifecycle paths (tick, disconnect) record and fence instead, so a
        failing stop can never raise out of a server loop as an unhandled exception.
        """

        generation,armed,reason_text=cleanup
        if armed is not None:
            try:self._close_controller_generation(armed)
            except RuntimeError:pass
        try:
            if self.prefix_executor is not None:
                self.prefix_executor.invalidate(reason_text)
        except Exception as error:
            with self._lock:
                if self._fault_reason is None:self._fault_reason='PAIR_CANCEL_LOST'
                self.audit.append(dict(operation='invalidate_error',error=repr(error)))
        try:
            self.driver.stop_all(reason_text)
        except Exception as error:
            with self._lock:
                if self._fault_reason is None:self._fault_reason='CONTROL_STOP_LOST'
                self.audit.append(dict(operation='stop_all_error',error=repr(error)))
            if propagate:
                raise                # explicit stop_attempt: the caller must see this

    def _driver_stopped(self):
        """Driver stopped proof, fail-closed.

        Production drivers always expose ``stopped()``. A driver that does not (a narrow
        test double, or an incompletely constructed driver) cannot prove the stopped
        state, so the broker treats it as NOT stopped rather than raising AttributeError
        from deep inside a reporting or authorization path.
        """

        probe=getattr(self.driver,'stopped',None)
        return bool(probe()) if callable(probe) else False

    def _stop_if_revoked(self):
        if self.ownership.state=='STOPPING':
            generation=self.ownership.generation
            if generation!=self._stopping_generation:
                self._stopping_generation=generation
                self._reset_ticket=None;self._reset_applied=False;self._post_reset_ticket=None
                if self._prefix_sources is not None:self._prefix_sources.revoke()
                if self._armed_generation is not None:
                    try:self._close_controller_generation(self._armed_generation)
                    except RuntimeError:pass
                try:
                    if self.prefix_executor is not None:self.prefix_executor.invalidate(self.ownership.reason or 'REVOKED')
                except Exception as error:
                    if self._fault_reason is None:self._fault_reason='PAIR_CANCEL_LOST'
                    self.audit.append(dict(operation='invalidate_error',error=repr(error)))
                finally:self.driver.stop_all(self.ownership.reason or 'REVOKED')
            if hasattr(self.driver,'refresh_stop'):self.driver.refresh_stop()
            # probe only when the driver exposes the state: the phased cleanup runs the
            # stop first, so a double without stopped() must not surface an AttributeError
            probe=getattr(self.driver,'stopped',None)
            if (callable(probe) and not any(not future.done() for future in self._writes)
                    and probe()):
                self.ownership.confirm_stopped(True)

    def tick(self):
        cleanup=None
        with self._lock:
            hazard=getattr(self.driver,'hazard_reason',None)
            if hazard and self._fault_reason is None:
                self._fault_reason=hazard;self.ownership.revoke(hazard)
            elif self._fault_reason and self.ownership.state=='RUNNING':self.ownership.revoke(self._fault_reason)
            if self.ownership.state=='STOPPING':
                generation=self.ownership.generation
                if generation!=self._stopping_generation:
                    # locked logical terminalization only: no controller/ROS I/O here
                    self._stopping_generation=generation
                    self._reset_ticket=None;self._reset_applied=False;self._post_reset_ticket=None
                    if self._prefix_sources is not None:self._prefix_sources.revoke()
                    cleanup=(generation,self._armed_generation,
                             self.ownership.reason or 'REVOKED')
                    self._cleanup_pending=cleanup
            # with the generation terminalized this only refreshes/confirms stop state
            self._stop_if_revoked()
        if cleanup is not None:
            self._cleanup_unlocked_io(cleanup, propagate=True)          # socket + ROS calls, lock free
            with self._lock:
                if self._cleanup_pending==cleanup:self._cleanup_pending=None
                self._stop_if_revoked()
        with self._lock:
            if self.ownership.state=='IDLE' and hasattr(self.driver,'refresh_idle'):self.driver.refresh_idle()
            elif self._post_reset_ticket is not None:
                try:self.ownership.require_ticket(self._post_reset_ticket)
                except PermissionError:self._post_reset_ticket=None
                else:
                    if not self.driver.pause_idempotent(True):self._post_reset_ticket=None
                    elif not self.driver.refresh_post_reset():self._post_reset_ticket=None

    def disconnect(self,connection_id):
        cleanup=None
        with self._lock:
            ticket=self._participants.pop(connection_id,None)
            if ticket is not None and ticket[0]==self.ownership.generation:
                self.ownership.revoke('CLIENT_DISCONNECTED')
                generation=self.ownership.generation
                if generation!=self._stopping_generation:
                    # locked logical terminalization only: no controller/ROS I/O here
                    self._stopping_generation=generation
                    self._reset_ticket=None;self._reset_applied=False;self._post_reset_ticket=None
                    if self._prefix_sources is not None:self._prefix_sources.revoke()
                    cleanup=(generation,self._armed_generation,
                             self.ownership.reason or 'REVOKED')
                    self._cleanup_pending=cleanup
                self._stop_if_revoked()
        if cleanup is not None:
            self._cleanup_unlocked_io(cleanup)          # socket + ROS calls, lock free
            with self._lock:
                if self._cleanup_pending==cleanup:self._cleanup_pending=None
                self._stop_if_revoked()

    def _prepare_reset(self,scope,connection_id):
        with self._lock,self.ownership.authorized(*scope) as ticket:
            if scope[1]=='act':raise PermissionError('RESET_OWNER_INVALID')
            if self._reset_ticket is not None:raise PermissionError('RESET_IN_PROGRESS')
            self._reset_ticket=ticket;self._reset_applied=False;self._post_reset_ticket=None
            self._participants[connection_id]=ticket
        try:
            deadline=time.monotonic()+5.
            while True:
                with self._lock:
                    self.tick()
                    with self.ownership.authorized(*scope):
                        self.ownership.require_ticket(ticket)
                        # Refresh real negative CancelGoal confirmations only
                        # through the owning driver. No reset or motion is sent.
                        refresh=getattr(self.driver,'refresh_idle',None)
                        if refresh is not None:refresh()
                        if self._driver_stopped():
                            if hasattr(self.driver,'prepare_reset'):self.driver.prepare_reset()
                            return
                        if refresh is None or time.monotonic()>=deadline:
                            raise PermissionError('CONTROL_NOT_STOPPED')
                time.sleep(.01)
        except Exception:
            with self._lock:
                if self._reset_ticket==ticket and ticket[0]==self.ownership.generation:
                    self.ownership.revoke('RESET_PREPARATION_FAILED');self._stop_if_revoked()
            raise




    def _release_phased(self,scope,connection_id,response):
        """Release in three phases with an exact pending token.

        The controller generation is closed with no lock held; ownership is released
        only after that close is authoritatively confirmed. A close failure latches a
        fault and leaves control unavailable rather than silently freeing the lease.
        """

        generation=None
        with self._lock:
            self.tick()
            if self._fault_reason:raise PermissionError(self._fault_reason)
            if self._release_pending is not None:
                raise PermissionError('CONTROLLER_RELEASE_PENDING')
            with self.ownership.authorized(*scope) as ticket:
                if self._reset_ticket is not None:raise PermissionError('RESET_IN_PROGRESS')
                if not self._driver_stopped():raise PermissionError('CONTROL_NOT_STOPPED')
                if self._armed_generation==ticket[0]:
                    generation=self._armed_generation
                self._release_pending=(ticket,generation)
        close_error=None
        if generation is not None:
            try:
                self._close_controller_generation(generation)   # unlocked socket exchange
            except Exception as error:
                close_error=error
        with self._lock:
            pending=self._release_pending
            if pending is None or pending[0]!=ticket:
                raise PermissionError('CONTROLLER_RELEASE_STALE')
            self._release_pending=None
            if close_error is not None:
                # close unconfirmed: latch fault/fencing, keep the lease unavailable
                if self._fault_reason is None:
                    self._fault_reason='CONTROLLER_RESERVATION_CLOSE_UNCONFIRMED'
                self.ownership.revoke('CONTROLLER_RESERVATION_CLOSE_UNCONFIRMED')
                self._stop_if_revoked()
                raise PermissionError('CONTROLLER_RESERVATION_CLOSE_UNCONFIRMED')
            self.ownership.require_ticket(ticket)
            if not self._driver_stopped():raise PermissionError('CONTROL_NOT_STOPPED')
            self.ownership.release(scope[0],True)
            if self._prefix_sources is not None:self._prefix_sources.revoke()
            self._post_reset_ticket=None
            if generation is not None and self._armed_generation==generation:
                self._armed_generation=None                 # the generation is closed
            self._participants.pop(connection_id,None)      # no participant survives
            response['accepted']=True


    def _acquire_restricted(self,scope,connection_id,response):
        """Logical-only acquire for non-ACT owners when a bound session is installed.

        Grants the ownership ticket needed for reset/recovery dispatch without touching
        the controller, the composition or the one-shot session.
        """

        with self._lock:
            self.tick()
            if self._fault_reason:raise PermissionError(self._fault_reason)
            if self._release_pending is not None:raise PermissionError('CONTROLLER_RELEASE_PENDING')
            if self._cleanup_pending is not None:raise PermissionError('CONTROLLER_CLEANUP_PENDING')
            if self._acquire_pending is not None:
                raise PermissionError('CONTROLLER_RESERVATION_ACQUIRE_PENDING')
            if self.ownership.state!='IDLE':raise PermissionError('CONTROL_BUSY')
            if not self._driver_stopped():
                self.ownership.revoke('CONTROL_NOT_STOPPED');self._stop_if_revoked()
                raise PermissionError('CONTROL_NOT_STOPPED')
            token=self.ownership.acquire(*scope[1:])
            ticket=self.ownership.ticket(token,*scope[1:])
            response['lease_token']=token
            response['accepted']=True
            self._participants[connection_id]=ticket
            return ticket

    def _acquire_legacy(self,scope,connection_id,response):
        """Legacy controller acquire in three phases (mirrors _acquire_bound).

        Phase 1 (locked): validate, exact ticket, mark the pending attempt.
        Phase 2 (unlocked): the controller arm socket exchange.
        Phase 3 (locked): revalidate the exact ticket and commit, or clean up.
        """

        with self._lock:
            self.tick()
            if self._fault_reason:raise PermissionError(self._fault_reason)
            if self._release_pending is not None:
                raise PermissionError('CONTROLLER_RELEASE_PENDING')
            if self._acquire_pending is not None:
                raise PermissionError('CONTROLLER_RESERVATION_ACQUIRE_PENDING')
            if self.ownership.state!='IDLE':raise PermissionError('CONTROL_BUSY')
            if not self._driver_stopped():
                self.ownership.revoke('CONTROL_NOT_STOPPED');self._stop_if_revoked()
                raise PermissionError('CONTROL_NOT_STOPPED')
            token=self.ownership.acquire(*scope[1:])
            ticket=self.ownership.ticket(token,*scope[1:])
            self._acquire_pending=ticket
        failure=None
        try:
            if not self._driver_stopped():raise PermissionError('CONTROL_NOT_STOPPED')
            if self.reservation_port.arm_generation(ticket) is not True:
                raise PermissionError('CONTROLLER_RESERVATION_ARM_REJECTED')
        except Exception as error:
            failure=error
        committed=False
        with self._lock:
            if self._acquire_pending==ticket:
                self._acquire_pending=None
            if failure is None:
                try:
                    self.tick()
                    if self.ownership.reason is not None or self.ownership.state!='RUNNING':
                        failure=PermissionError('CONTROLLER_RESERVATION_CONCURRENT_REVOKE')
                    elif not self._driver_stopped():
                        failure=PermissionError('CONTROL_NOT_STOPPED')
                    else:
                        with self.ownership.authorized(*ticket[1:]):
                            self.ownership.require_ticket(ticket)
                            self._armed_generation=ticket[0]
                            response['lease_token']=token
                            response['accepted']=True
                            self._participants[connection_id]=ticket
                            committed=True
                except Exception as error:
                    failure=error
            if failure is not None and self.ownership.reason is None:
                self.ownership.revoke('CONTROLLER_RESERVATION_ARM_FAILED')
            if failure is not None:
                self._stop_if_revoked()
        if failure is not None:
            if not committed:
                close_error=None
                try:self._close_controller_generation(ticket[0])
                except RuntimeError as error:close_error=error
                if close_error is not None:raise close_error
            raise failure

    def _acquire_bound(self,scope,connection_id,response):
        """Bound acquire in three phases.

        Phase 1 (locked): validate, take the exact ticket, mark _acquire_pending.
        Phase 2 (unlocked): session.arm -> session.confirm, i.e. all socket I/O.
        Phase 3 (locked): revalidate the ticket/ownership/stopped state and only then
        commit _armed_generation, the participant and the lease response.
        """

        with self._lock:
            self.tick()
            if self._fault_reason:raise PermissionError(self._fault_reason)
            if self._acquire_pending is not None:
                raise PermissionError('BOUND_AUTHORITY_ACQUIRE_PENDING')
            if self.ownership.state!='IDLE':raise PermissionError('CONTROL_BUSY')
            if not self._driver_stopped():
                self.ownership.revoke('CONTROL_NOT_STOPPED');self._stop_if_revoked()
                raise PermissionError('CONTROL_NOT_STOPPED')
            token=self.ownership.acquire(*scope[1:])
            ticket=self.ownership.ticket(token,*scope[1:])
            self._acquire_pending=ticket            # the exact provisional ticket
        armed=False
        failure=None
        try:
            # phase 2 holds no broker lock and no ownership lock, so a concurrent
            # stop_attempt/revoke proceeds; phase 3 revalidates atomically
            if not self._driver_stopped():raise PermissionError('CONTROL_NOT_STOPPED')
            self._bound_authority_session.arm(ticket)
            armed=True
            self.ownership.require_ticket(ticket)     # exact ticket, not just state
            self._bound_authority_session.confirm(self.ownership)
        except Exception as error:                      # phase 2 failure: no commit
            failure=error
        committed=False
        with self._lock:
            if self._acquire_pending==ticket:
                self._acquire_pending=None           # only this exact attempt's marker
            if failure is None:
                try:
                    self.tick()
                    if self.ownership.reason is not None or self.ownership.state!='RUNNING':
                        failure=PermissionError('BOUND_AUTHORITY_CONCURRENT_REVOKE')
                    elif not self._driver_stopped():
                        failure=PermissionError('CONTROL_NOT_STOPPED')
                    else:
                        # no I/O here: the ownership guard keeps an interleaved
                        # Ownership.revoke out between revalidation and commit
                        with self.ownership.authorized(*ticket[1:]):
                            self.ownership.require_ticket(ticket)
                            self._armed_generation=ticket[0]
                            response['lease_token']=token
                            response['accepted']=True
                            self._participants[connection_id]=ticket
                            committed=True
                except Exception as error:
                    failure=error
            if failure is not None and self.ownership.reason is None:
                self.ownership.revoke('BOUND_AUTHORITY_ACQUIRE_FAILED')  # first reason wins
            if failure is not None:
                self._stop_if_revoked()                 # only ever under the broker lock
        if failure is not None:
            if armed and not committed:
                # the controller side may already be armed: fence it so no live
                # generation survives a failed commit
                self._bound_authority_session.abort('BOUND_AUTHORITY_COMMIT_FAILED')
            raise failure

    def handle(self,request,connection_id):
        response=dict(request_id=request.get('request_id','') if isinstance(request,dict) else '',
                      accepted=False,error=None,goal_id=None)
        try:
            operation=request['operation']
            if operation not in EXTRA:raise ValueError('OPERATION_INVALID')
            fields(request,BASE|EXTRA[operation])
            if type(request['protocol_version']) is not int or request['protocol_version']!=1:
                raise ValueError('PROTOCOL_VERSION_INVALID')
            if request['owner'] not in OWNERS:raise ValueError('OWNER_INVALID')
            for key in ('request_id','session_id','attempt_id'):identifier(request[key])
            if (self.simulation_session_id is not None and operation!='status'
                    and request['session_id']!=self.simulation_session_id):raise PermissionError('SESSION_MISMATCH')
            scope=tuple(request[key] for key in ('lease_token','owner','session_id','attempt_id'))
            if self._release_pending is not None and operation not in ('status','release','revoke'):
                raise PermissionError('CONTROLLER_RELEASE_PENDING')
            if self._cleanup_pending is not None and operation not in ('status','revoke'):
                raise PermissionError('CONTROLLER_CLEANUP_PENDING')
            if operation=='prepare_reset':
                self._prepare_reset(scope,connection_id)
                response['accepted']=True
                return response
            if operation=='acquire' and self._bound_authority_session is not None:
                if request['owner']=='act':
                    # A-prime: only the exact ACT execution acquire may consume the
                    # one-shot bound session
                    self._acquire_bound(scope,connection_id,response)
                else:
                    # recovery/teacher/teleop get a restricted logical-only acquire:
                    # no controller arm, no composition access, no session consumption.
                    # This is an explicit owner-scoped route, not a generic fallback.
                    self._acquire_restricted(scope,connection_id,response)
                return response
            if operation=='acquire' and self.reservation_port is not None:
                # legacy controller arm: same phasing, no broker lock across the socket
                self._acquire_legacy(scope,connection_id,response)
                return response
            if operation=='release':
                # phased release: logical invalidation, unlocked controller close,
                # locked exact-token finalization
                self._release_phased(scope,connection_id,response)
                return response
            if operation in ('reset_world','pause','switch_controllers','finish_reset'):
                with self._lock:
                    self.tick()
                    with self.ownership.authorized(*scope) as ticket:
                        if request['owner']=='act':raise PermissionError('RESET_OWNER_INVALID')
                        if operation!='pause' and self._reset_ticket!=ticket:
                            raise PermissionError('RESET_PREPARATION_REQUIRED')
                        if operation=='pause' and self._reset_ticket is None:
                            if not self.driver.stopped() and not getattr(self.driver,'pause_idempotent',lambda value:False)(request['paused']):
                                raise PermissionError('CONTROL_NOT_STOPPED')
                        if operation=='reset_world' and self._reset_applied:raise PermissionError('RESET_ALREADY_APPLIED')
                        if operation=='finish_reset' and not self._reset_applied:raise PermissionError('RESET_NOT_APPLIED')
                        values={key:request[key] for key in EXTRA[operation]}
                        prepared=self.driver.validate_write(operation,values)
                        future=self.driver.begin_write(operation,prepared)
                        self._writes.append(future);self._participants[connection_id]=ticket
                        if operation=='reset_world':self._reset_applied=True
                # Every actual service enqueue is generation fenced above. The
                # bounded response wait leaves Stop/revoke free to preempt it.
                result=self.driver.await_write(future)
                with self._lock:
                    self.ownership.require_ticket(ticket)
                    if operation=='finish_reset':
                        if self.driver.finish_reset(result) is not True:raise RuntimeError('RESET_FINAL_EVIDENCE_INVALID')
                        self._reset_ticket=None;self._reset_applied=False;self._post_reset_ticket=ticket
                    elif operation=='pause' and request['paused'] is False:
                        self._post_reset_ticket=None
                    response[{'reset_world':'reset_result','pause':'pause_result',
                              'switch_controllers':'switch_result','finish_reset':'finish_result'}[operation]]=result
                response['accepted']=True
                return response
            if operation in ('approve_prefix','submit_prefix'):
                with self._lock:
                    self.tick()
                    with self.ownership.authorized(*scope) as ticket:
                        if request['owner']!='act':raise PermissionError('PREFIX_OWNER_INVALID')
                        if self.prefix_executor is None:raise PermissionError('PREFIX_EXECUTOR_UNAVAILABLE')
                        self._participants[connection_id]=ticket
                # Acceptance waiting never holds the broker forwarding lock.
                # Each actual controller send separately rechecks this ticket
                # inside dispatch's authorization/queue critical section.
                if operation=='approve_prefix':
                    if self._prefix_sources is None:
                        response['permit']=self.prefix_executor.approve(ticket,request['prefix'])
                    else:
                        approve=getattr(self.prefix_executor,'approve_with_source',None)
                        if not callable(approve):
                            raise PermissionError('PREFIX_SOURCE_PROOF_UNWIRED')
                        source=self._prefix_source_port(ticket)
                        receipt=self._prefix_sources.consume(
                            ticket=ticket,prefix=request['prefix'],source=source)
                        self.ownership.require_ticket(ticket)
                        response['permit']=approve(ticket,request['prefix'],receipt)
                else:
                    gid=self.prefix_executor.submit(ticket,request['prefix'],request['permit'])
                    with self._lock:
                        self.ownership.require_ticket(ticket)
                        self._goal_tickets[gid]=ticket;self._pair_goals.add(gid)
                    response['goal_id']=gid
                response['accepted']=True
                return response
            with self._lock:
                self.tick()
                if operation=='acquire':
                    if self._fault_reason:raise PermissionError(self._fault_reason)
                    if self.ownership.state!='IDLE':raise PermissionError('CONTROL_BUSY')
                    if not self._driver_stopped():
                        self.ownership.revoke('CONTROL_NOT_STOPPED');self._stop_if_revoked()
                        raise PermissionError('CONTROL_NOT_STOPPED')
                    token=self.ownership.acquire(*scope[1:])
                    ticket=self.ownership.ticket(token,*scope[1:])
                    response['lease_token']=token
                    self._participants[connection_id]=ticket
                elif operation=='status':
                    self._stop_if_revoked();response['state']=self.ownership.state
                    response['generation']=self.ownership.generation
                    response['stop_confirmed']=self._driver_stopped() and not any(not future.done() for future in self._writes)
                    response['reset_in_progress']=self._reset_ticket is not None
                    response['hazard_reason']=self._fault_reason
                    if hasattr(self.driver,'ready'):
                        response['action_servers']={kind:self.driver.ready(kind)
                                                    for kind in ('arm','gripper','neck','execute_trajectory')}
                elif operation=='goal_status':
                    gid=identifier(request['goal_id'])
                    ticket=self._goal_tickets.get(gid)
                    if ticket is None or ticket[1:]!=scope:raise PermissionError('GOAL_SCOPE_INVALID')
                    state=dict(self.prefix_executor.goal_state(gid) if gid in self._pair_goals else self.driver.goal_state(gid));response['action_accepted']=state.pop('accepted',None)
                    response.update(state);response['goal_id']=gid
                else:
                    with self.ownership.authorized(*scope) as ticket:
                        self._participants[connection_id]=ticket
                        if operation=='renew':self.ownership.renew(*scope)
                        elif operation=='submit':
                            if self._reset_ticket is not None:raise PermissionError('RESET_IN_PROGRESS')
                            if request['owner']=='act':raise PermissionError('ACT_PREFIX_REQUIRED')
                            goal=self.driver.validate(request['action_kind'],request['goal'])
                            response['goal_id']=self.dispatch(ticket,request['action_kind'],goal)
                        elif operation in ('cancel','goal_status'):
                            gid=identifier(request['goal_id'])
                            if self._goal_tickets.get(gid)!=ticket:raise PermissionError('GOAL_SCOPE_INVALID')
                            if operation=='cancel':self.driver.cancel(gid)
                            else:response.update(self.driver.goal_state(gid));response['goal_id']=gid
                        elif operation=='release':
                            if self._reset_ticket is not None:raise PermissionError('RESET_IN_PROGRESS')
                            if not self.driver.stopped():raise PermissionError('CONTROL_NOT_STOPPED')
                            if self._armed_generation==ticket[0]:
                                self._close_controller_generation(ticket[0])
                            self.ownership.release(scope[0],True)
                            if self._prefix_sources is not None:self._prefix_sources.revoke()
                            self._post_reset_ticket=None
                        elif operation=='revoke':self.ownership.revoke('CLIENT_REVOKED')
                    self._stop_if_revoked()
                # RPC acceptance is permission/forwarding success. Actual action
                # acceptance/result fields are reported separately by goal_status.
                response['accepted']=True
        except (KeyError,TypeError,ValueError,PermissionError,RuntimeError,OSError) as error:
            response['error']=str(error) or type(error).__name__
            try:self.tick()
            except Exception:pass
        return response


class LocalBrokerConnection:
    """Use the child-owned broker without creating another writer or socket."""

    def __init__(self, broker: CommandBroker):
        if not isinstance(broker, CommandBroker):
            raise TypeError('COMMAND_BROKER_REQUIRED')
        self.broker = broker
        self._connection_id = f'local-{uuid.uuid4()}'
        self._lock = threading.RLock()
        self._closed = False

    def request(self, operation, context, **extra):
        with self._lock:
            if self._closed:
                raise RuntimeError('BROKER_DISCONNECTED')
            request = dict(protocol_version=1, request_id=str(uuid.uuid4()),
                           operation=operation, owner=context['owner'],
                           session_id=context['session_id'], attempt_id=context['attempt_id'],
                           lease_token=context.get('lease_token', ''), **extra)
            result = self.broker.handle(request, self._connection_id)
            if result.get('request_id') != request['request_id']:
                raise RuntimeError('BROKER_RESPONSE_ID_INVALID')
            if result.get('accepted') is not True:
                raise PermissionError(result.get('error') or 'BROKER_REJECTED')
            return result

    def acquire(self, owner, session_id, attempt_id):
        context = dict(owner=owner, session_id=session_id, attempt_id=attempt_id)
        context['lease_token'] = self.request('acquire', context)['lease_token']
        return context

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self.broker.disconnect(self._connection_id)


class UnixBrokerServer:
    """Exclusive authority; preserved socket/lock files require a new run on restart."""
    def __init__(self,broker,path,*,parent_pid=None):
        endpoint_bytes(path)  # before creating/spawning anything
        self.broker,self.path=broker,Path(path);self.parent_pid=parent_pid
        self._listener=None;self._lock_file=None;self._stop=threading.Event()
        self._threads=[];self._peers=set();self._peers_lock=threading.Lock()

    def start(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        if self.path.is_symlink():raise RuntimeError('SOCKET_PATH_UNSAFE')
        self._lock_file=open(str(self.path)+'.lock','a+b')
        try:
            fcntl.flock(self._lock_file,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if self.path.exists():raise RuntimeError('BROKER_ENDPOINT_ALREADY_EXISTS')
            self._listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
            self._listener.bind(str(self.path));os.chmod(self.path,0o600)
            self._listener.listen(16);self._listener.settimeout(.1)
        except Exception:
            self._lock_file.close();self._lock_file=None
            if self._listener is not None:self._listener.close()
            raise
        thread=threading.Thread(target=self._serve,daemon=True);self._threads.append(thread);thread.start()
        return self

    def _serve(self):
        while not self._stop.is_set():
            if self.parent_pid is not None:
                try:os.kill(self.parent_pid,0)
                except ProcessLookupError:
                    self.broker.ownership.revoke('PARENT_DIED');self.broker.tick();self._stop.set();break
            try:
                self.broker.tick()
            except Exception as error:
                # a failing driver stop is fenced and recorded; the loop keeps serving
                self.broker.audit.append(dict(operation='tick_error',error=repr(error)))
            try:peer,_=self._listener.accept()
            except socket.timeout:continue
            except OSError:break
            with self._peers_lock:self._peers.add(peer)
            thread=threading.Thread(target=self._peer,args=(peer,),daemon=True)
            self._threads.append(thread);thread.start()

    def _peer(self,peer):
        connection=f'fd-{peer.fileno()}';pending=b''
        try:
            while not self._stop.is_set():
                block=peer.recv(65536)
                if not block:break
                pending+=block
                if len(pending)>MAX_REQUEST_BYTES:break
                while b'\n' in pending:
                    line,pending=pending.split(b'\n',1)
                    try:request=json.loads(line)
                    except (ValueError,UnicodeError):request={}
                    response=self.broker.handle(request,connection)
                    peer.sendall(json.dumps(response,allow_nan=False,separators=(',',':')).encode()+b'\n')
        except OSError:pass
        finally:
            self.broker.disconnect(connection)
            with self._peers_lock:self._peers.discard(peer)
            peer.close()

    def close(self):
        self.broker.ownership.revoke('BROKER_SHUTDOWN');self.broker.tick();self._stop.set()
        if self._listener:self._listener.close()
        with self._peers_lock:peers=list(self._peers)
        for peer in peers:
            try:peer.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        for thread in self._threads:thread.join(timeout=1)
        if self._lock_file:self._lock_file.close()
