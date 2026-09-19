"""ROS-compatible remote action clients; the broker retains underlying clients."""

from concurrent.futures import Future
import copy
import fcntl
import json
import os
import socket
import threading
import time
from types import SimpleNamespace
import uuid

from .command_broker import endpoint_bytes, MAX_REQUEST_BYTES

ACTIONS={'/execute_trajectory':'execute_trajectory',
         '/arm_controller/follow_joint_trajectory':'arm',
         '/gripper_controller/follow_joint_trajectory':'gripper'}
_CONNECTIONS={};_POOL_LOCK=threading.RLock()


class BrokerConnection:
    def __init__(self,broker_socket,*,connection_fd=None,rpc_lock_path=None,timeout_s=5.):
        endpoint_bytes(broker_socket);self.path=broker_socket;self.timeout=timeout_s
        self._lock=threading.RLock();self._pending=b'';self._closed=False
        self._file_lock=None;self._file_lock_path=rpc_lock_path
        if rpc_lock_path is not None:
            if not os.path.isabs(rpc_lock_path):raise ValueError('RPC_LOCK_PATH_INVALID')
            fd=os.open(rpc_lock_path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
            self._file_lock=os.fdopen(fd,'a+b')
        if connection_fd is None:
            self.socket=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
            self.socket.settimeout(timeout_s);self.socket.connect(broker_socket)
        else:
            if type(connection_fd) is not int or connection_fd<0:raise ValueError('BROKER_FD_INVALID')
            self.socket=socket.socket(fileno=os.dup(connection_fd));self.socket.settimeout(timeout_s)

    def request(self,operation,context,**extra):
        request=dict(protocol_version=1,request_id=str(uuid.uuid4()),operation=operation,
            owner=context['owner'],session_id=context['session_id'],attempt_id=context['attempt_id'],
            lease_token=context.get('lease_token',''),**extra)
        line=json.dumps(request,allow_nan=False,separators=(',',':')).encode()+b'\n'
        if len(line)>MAX_REQUEST_BYTES:raise ValueError('REQUEST_TOO_LARGE')
        with self._lock:
            if self._closed:raise RuntimeError('BROKER_DISCONNECTED')
            if self._file_lock:fcntl.flock(self._file_lock,fcntl.LOCK_EX)
            try:
                self.socket.sendall(line)
                # Peek for this reply's newline and consume no bytes beyond it.
                # The per-request inherited-FD lock spans send/read. Bounded
                # chunks avoid thousands of GIL-releasing recv(1) calls while
                # preserving the next process's reply in the kernel buffer.
                response=bytearray()
                while True:
                    peek=self.socket.recv(65536,socket.MSG_PEEK)
                    if not peek:raise RuntimeError('BROKER_DISCONNECTED')
                    newline=peek.find(b'\n')
                    count=newline+1 if newline>=0 else len(peek)
                    block=self.socket.recv(count)
                    if not block:raise RuntimeError('BROKER_DISCONNECTED')
                    if block.endswith(b'\n'):
                        response.extend(block[:-1])
                        if len(response)>MAX_REQUEST_BYTES:raise ValueError('RESPONSE_TOO_LARGE')
                        break
                    response.extend(block)
                    if len(response)>MAX_REQUEST_BYTES:raise ValueError('RESPONSE_TOO_LARGE')
                result=json.loads(response)
                if result.get('request_id')!=request['request_id']:raise RuntimeError('BROKER_RESPONSE_ID_INVALID')
                if result.get('accepted') is not True:raise PermissionError(result.get('error') or 'BROKER_REJECTED')
                return result
            finally:
                if self._file_lock:fcntl.flock(self._file_lock,fcntl.LOCK_UN)

    def acquire(self,owner,session_id,attempt_id):
        context=dict(broker_socket=self.path,owner=owner,session_id=session_id,attempt_id=attempt_id)
        context['lease_token']=self.request('acquire',context)['lease_token']
        if self._file_lock:
            context['connection_fd']=self.socket.fileno()
            context['rpc_lock_path']=self._file_lock_path
        with _POOL_LOCK:_CONNECTIONS[(self.path,context['lease_token'])]=self
        return context

    def close(self):
        with self._lock:
            if self._closed:return
            self._closed=True;self.socket.close()
            if self._file_lock:self._file_lock.close()
        with _POOL_LOCK:
            for key,value in list(_CONNECTIONS.items()):
                if value is self:del _CONNECTIONS[key]


def context_from_environment():
    path=os.environ.get('SO101_ACT_CONTROL_CONTEXT')
    if path is None:return None
    with open(path,encoding='utf-8') as stream:context=json.load(stream)
    if not isinstance(context,dict):raise PermissionError('CONTROL_CONTEXT_INVALID')
    return context


def connection_for(context):
    key=(context['broker_socket'],context['lease_token'])
    with _POOL_LOCK:
        if key not in _CONNECTIONS:
            _CONNECTIONS[key]=BrokerConnection(context['broker_socket'],
                connection_fd=context.get('connection_fd'),rpc_lock_path=context.get('rpc_lock_path'))
        return _CONNECTIONS[key]


def message_dict(message):
    from rosidl_runtime_py.convert import message_to_ordereddict
    return dict(message_to_ordereddict(message))


def decoded(kind,values):
    from rosidl_runtime_py.set_message import set_message_fields
    message=kind();set_message_fields(message,copy.deepcopy(values));return message


def asynchronous(call):
    future=Future()
    def run():
        try:future.set_result(call())
        except Exception as error:future.set_exception(error)
    threading.Thread(target=run,daemon=True).start();return future


class LeasedGoalHandle:
    def __init__(self,client,gid,accepted,feedback_callback=None):
        self._client,self.goal_id,self.accepted=client,gid,accepted
        self.feedback_callback=feedback_callback
        self._result_future=Future();self._polling=False;self._lock=threading.Lock()

    def get_result_async(self):
        with self._lock:
            if not self._polling:
                self._polling=True
                threading.Thread(target=self._poll,daemon=True).start()
        return self._result_future

    def _poll(self):
        try:
            previous_feedback=None
            while True:
                state=self._client.connection.request('goal_status',self._client.context,goal_id=self.goal_id)
                feedback=state.get('feedback')
                if feedback is not None and feedback!=previous_feedback and self.feedback_callback:
                    self.feedback_callback(SimpleNamespace(
                        feedback=decoded(self._client.action_type.Feedback,feedback)))
                    previous_feedback=feedback
                if state.get('status') in (4,5,6) and state.get('result') is not None:
                    self._result_future.set_result(SimpleNamespace(status=state['status'],
                        result=decoded(self._client.action_type.Result,state['result'])))
                    return
                time.sleep(.01)
        except Exception as error:self._result_future.set_exception(error)

    def cancel_goal_async(self):
        def cancel():
            from action_msgs.srv import CancelGoal
            self._client.connection.request('cancel',self._client.context,goal_id=self.goal_id)
            while True:
                state=self._client.connection.request('goal_status',self._client.context,goal_id=self.goal_id)
                if state.get('cancel_response') is not None:
                    return decoded(CancelGoal.Response,state['cancel_response'])
                time.sleep(.01)
        return asynchronous(cancel)


class LeasedActionClient:
    def __init__(self,node,action_type,action_name,*,broker_socket,owner,session_id,attempt_id,
                 lease_token,connection_fd=None,rpc_lock_path=None):
        if action_name not in ACTIONS:raise PermissionError('ACTION_NOT_BROKERED')
        self.node,self.action_type,self.kind=node,action_type,ACTIONS[action_name]
        self.context=dict(broker_socket=broker_socket,owner=owner,session_id=session_id,
                          attempt_id=attempt_id,lease_token=lease_token)
        if connection_fd is not None:self.context['connection_fd']=connection_fd
        if rpc_lock_path is not None:self.context['rpc_lock_path']=rpc_lock_path
        self.connection=connection_for(self.context);self.feedback_callback=None

    def wait_for_server(self,timeout_sec):
        deadline=time.monotonic()+timeout_sec
        while True:
            try:
                status=self.connection.request('status',self.context)
                if status.get('action_servers',{}).get(self.kind) is True:return True
            except (OSError,RuntimeError,PermissionError):return False
            if time.monotonic()>=deadline:return False
            time.sleep(.01)

    def send_goal_async(self,goal,feedback_callback=None):
        self.feedback_callback=feedback_callback
        def submit():
            reply=self.connection.request('submit',self.context,action_kind=self.kind,goal=message_dict(goal))
            gid=reply['goal_id']
            while True:
                status=self.connection.request('goal_status',self.context,goal_id=gid)
                if status.get('action_accepted') is not None:
                    return LeasedGoalHandle(self,gid,status['action_accepted'] is True,feedback_callback)
                time.sleep(.005)
        return asynchronous(submit)


def make_action_client(node,action_type,action_name,*,control_context=None,required_owner="teacher"):
    context=control_context if control_context is not None else context_from_environment()
    if context is not None:
        if context.get("owner") != required_owner:raise PermissionError("LEASE_OWNER_INVALID")
        return LeasedActionClient(node,action_type,action_name,**context)
    if os.environ.get('SO101_ACT_PROFILE') in ('1','true'):
        raise PermissionError('CONTROL_CONTEXT_REQUIRED')
    from rclpy.action import ActionClient
    return ActionClient(node,action_type,action_name)
