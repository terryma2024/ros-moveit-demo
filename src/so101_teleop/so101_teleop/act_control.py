"""Optional ACT-profile control port; the broker owns the real robot lease."""

import json
import os
from pathlib import Path
import time
import uuid


class ActControl:
    def __init__(self,connection):
        self.connection=connection;self.context=None;self.context_path=None

    def acquire(self,session_id,attempt_id):
        self.context=self.connection.acquire('teleop',session_id,attempt_id)
        return self.context

    def require(self,session_id):
        if self.context is None:raise PermissionError('LEASE_INVALID')
        if self.context['session_id']!=session_id:raise PermissionError('SESSION_MISMATCH')
        if self.context['owner'] not in ('teleop','teacher'):raise PermissionError('LEASE_OWNER_INVALID')
        self.connection.request('renew',self.context)

    def stop(self,session_id,*,timeout_s=5.):
        # Use a separate socket: the inherited teacher connection may be
        # waiting on reset/action acknowledgment while Stop must preempt it.
        from so101_demo.adapters.act.leased_action_client import BrokerConnection
        if self.context is None:raise PermissionError('LEASE_INVALID')
        context=dict(self.context)
        if context['session_id']!=session_id:raise PermissionError('SESSION_MISMATCH')
        if context['owner'] not in ('teleop','teacher'):raise PermissionError('LEASE_OWNER_INVALID')
        connection=BrokerConnection(context['broker_socket'],timeout_s=timeout_s)
        try:
            connection.request('revoke',context)
            deadline=time.monotonic()+timeout_s
            while True:
                status=connection.request('status',context)
                if status.get('state')=='IDLE' and status.get('stop_confirmed') is True:return True
                if time.monotonic()>=deadline:raise RuntimeError('STOP_NOT_CONFIRMED')
                time.sleep(.01)
        finally:connection.close()

    def publish_context(self):
        if self.context is None or 'connection_fd' not in self.context:
            raise PermissionError('INHERITED_CONTROL_CONNECTION_REQUIRED')
        path=Path(self.context['broker_socket']).parent/'contexts'/f'{uuid.uuid4().hex}.json'
        path.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as stream:json.dump(self.context,stream)
        self.context_path=path
        # Only this ACT server process's backend children inherit this machine
        # context. UI payloads/environment diagnostics never expose the token.
        os.environ['SO101_ACT_CONTROL_CONTEXT']=str(path)

    def begin_workflow(self,session_id,attempt_id):
        self.require(session_id)
        if self.context['owner']=='teacher':return
        self.connection.request('release',self.context)
        self.context=None
        self.context=self.connection.acquire('teacher',session_id,attempt_id)
        self.publish_context()

    def proxy(self,node,action_type,action_name):
        return ContextActionClient(self,node,action_type,action_name)

    def close(self):self.connection.close()


class ContextActionClient:
    def __init__(self,control,node,action_type,action_name):
        self.control,self.node,self.action_type,self.action_name=control,node,action_type,action_name

    def server_is_ready(self):
        from so101_demo.adapters.act.leased_action_client import ACTIONS
        scope=self.control.context or dict(owner='teleop',session_id='readiness',attempt_id='readiness')
        try:return self.control.connection.request('status',scope).get('action_servers',{}).get(ACTIONS[self.action_name]) is True
        except (OSError,RuntimeError,PermissionError):return False

    def wait_for_server(self,timeout_sec):
        until=time.monotonic()+timeout_sec
        while True:
            if self.server_is_ready():return True
            if time.monotonic()>=until:return False
            time.sleep(.01)

    def send_goal_async(self,goal,feedback_callback=None):
        from so101_demo.adapters.act.leased_action_client import make_action_client
        if self.control.context is None:raise PermissionError('LEASE_INVALID')
        self.control.require(self.control.context['session_id'])
        client=make_action_client(self.node,self.action_type,self.action_name,
                                 control_context=self.control.context,required_owner='teleop')
        return client.send_goal_async(goal,feedback_callback)
