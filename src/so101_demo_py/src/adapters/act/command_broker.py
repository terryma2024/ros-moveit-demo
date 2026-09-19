"""Single ownership authority with generation-fenced forwarding and Unix RPC."""

import fcntl
import json
import os
from pathlib import Path
import socket
import threading
import time

from so101_demo.act.contracts import fields, identifier
from so101_demo.act.ownership import OWNERS

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
    def __init__(self,driver,*,ownership,simulation_session_id=None,prefix_executor=None):
        self.driver,self.ownership=driver,ownership
        self.prefix_executor=prefix_executor;self._pair_goals=set()
        self.simulation_session_id=simulation_session_id
        self._lock=threading.RLock();self._participants={};self._goal_tickets={}
        self._stopping_generation=None;self.audit=[];self._fault_reason=None
        self._reset_ticket=None;self._reset_applied=False;self._writes=[]

    def dispatch(self,ticket,kind,goal):
        with self._lock,self.ownership.authorized(*ticket[1:]):
            self.ownership.require_ticket(ticket)
            gid=identifier(self.driver.submit(kind,goal))
            self._goal_tickets[gid]=ticket
            self.audit.append(dict(operation='submit',generation=ticket[0],owner=ticket[2],
                                   session_id=ticket[3],attempt_id=ticket[4],goal_id=gid))
            return gid

    def _stop_if_revoked(self):
        if self.ownership.state=='STOPPING':
            generation=self.ownership.generation
            if generation!=self._stopping_generation:
                self._stopping_generation=generation
                self._reset_ticket=None;self._reset_applied=False
                try:
                    if self.prefix_executor is not None:self.prefix_executor.invalidate(self.ownership.reason or 'REVOKED')
                except Exception as error:
                    self._fault_reason=self._fault_reason or 'PAIR_CANCEL_LOST'
                    self.audit.append(dict(operation='invalidate_error',error=repr(error)))
                finally:self.driver.stop_all(self.ownership.reason or 'REVOKED')
            if hasattr(self.driver,'refresh_stop'):self.driver.refresh_stop()
            if not any(not future.done() for future in self._writes) and self.driver.stopped():self.ownership.confirm_stopped(True)

    def tick(self):
        with self._lock:
            hazard=getattr(self.driver,'hazard_reason',None)
            if hazard and self._fault_reason is None:
                self._fault_reason=hazard;self.ownership.revoke(hazard)
            elif self._fault_reason and self.ownership.state=='RUNNING':self.ownership.revoke(self._fault_reason)
            self._stop_if_revoked()
            if self.ownership.state=='IDLE' and hasattr(self.driver,'refresh_idle'):self.driver.refresh_idle()

    def disconnect(self,connection_id):
        with self._lock:
            ticket=self._participants.pop(connection_id,None)
            if ticket is not None and ticket[0]==self.ownership.generation:
                self.ownership.revoke('CLIENT_DISCONNECTED');self._stop_if_revoked()

    def _prepare_reset(self,scope,connection_id):
        with self._lock,self.ownership.authorized(*scope) as ticket:
            if scope[1]=='act':raise PermissionError('RESET_OWNER_INVALID')
            if self._reset_ticket is not None:raise PermissionError('RESET_IN_PROGRESS')
            self._reset_ticket=ticket;self._reset_applied=False
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
                        if self.driver.stopped():
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
            if operation=='prepare_reset':
                self._prepare_reset(scope,connection_id)
                response['accepted']=True
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
                        self._reset_ticket=None;self._reset_applied=False
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
                    response['permit']=self.prefix_executor.approve(ticket,request['prefix'])
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
                    if not self.driver.stopped():
                        self.ownership.revoke('CONTROL_NOT_STOPPED');self._stop_if_revoked()
                        raise PermissionError('CONTROL_NOT_STOPPED')
                    token=self.ownership.acquire(*scope[1:]);response['lease_token']=token
                    self._participants[connection_id]=self.ownership.ticket(token,*scope[1:])
                elif operation=='status':
                    self._stop_if_revoked();response['state']=self.ownership.state
                    response['generation']=self.ownership.generation
                    response['stop_confirmed']=self.driver.stopped() and not any(not future.done() for future in self._writes)
                    response['reset_in_progress']=self._reset_ticket is not None
                    response['hazard_reason']=self._fault_reason
                    if hasattr(self.driver,'ready'):
                        response['action_servers']={kind:self.driver.ready(kind) for kind in ('arm','gripper','execute_trajectory')}
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
                            self.ownership.release(scope[0],self.driver.stopped())
                        elif operation=='revoke':self.ownership.revoke('CLIENT_REVOKED')
                    self._stop_if_revoked()
                # RPC acceptance is permission/forwarding success. Actual action
                # acceptance/result fields are reported separately by goal_status.
                response['accepted']=True
        except (KeyError,TypeError,ValueError,PermissionError,RuntimeError) as error:
            response['error']=str(error) or type(error).__name__
            try:self.tick()
            except Exception:pass
        return response


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
            self.broker.tick()
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
