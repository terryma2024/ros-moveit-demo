"""The browser session never substitutes for the broker's real control lease."""
from types import SimpleNamespace
import pytest
from so101_teleop.act_control import ActControl


def test_busy_act_owner_rejects_teleop_without_extra_commands():
    calls=[]
    class Connection:
        def acquire(self,*args):raise PermissionError('CONTROL_BUSY')
        def request(self,*args,**kwargs):calls.append(args);raise PermissionError('LEASE_INVALID')
    control=ActControl(Connection())
    with pytest.raises(PermissionError,match='CONTROL_BUSY'):control.acquire('s','a')
    with pytest.raises(PermissionError):control.require('s')
    assert calls==[]


def test_teleop_proxy_role_and_session_are_bound():
    calls=[]
    context=dict(broker_socket='/tmp/no-connect',owner='teleop',session_id='s',attempt_id='a',lease_token='token')
    class Connection:
        def acquire(self,*args):return context
        def request(self,operation,scope,**kwargs):calls.append(operation);return {'accepted':True}
    control=ActControl(Connection());control.acquire('s','a');control.require('s')
    assert calls==['renew']
    with pytest.raises(PermissionError,match='SESSION_MISMATCH'):control.require('old')
    assert control.context==context


def test_act_workflow_runner_cannot_start_without_common_authority(monkeypatch):
    from so101_teleop.workflow_gateway import WorkflowGateway
    monkeypatch.setenv('SO101_ACT_PROFILE','1')
    with pytest.raises(PermissionError,match='CONTROL_CONTEXT_REQUIRED'):
        WorkflowGateway(SimpleNamespace())


def test_stop_uses_independent_connection_and_original_scoped_token(monkeypatch):
    from so101_demo.adapters.act import leased_action_client as remote
    calls=[]
    context=dict(broker_socket='/tmp/no-connect',owner='teacher',session_id='s',attempt_id='a',lease_token='token',connection_fd=7,rpc_lock_path='/tmp/lock')
    class Primary:
        def request(self,*args,**kwargs):raise AssertionError('Stop must not wait on primary RPC')
    class Independent:
        def __init__(self,path,**kwargs):calls.append(('connect',path,kwargs))
        def request(self,op,scope):
            calls.append((op,dict(scope)))
            return {'state':'IDLE','stop_confirmed':True}
        def close(self):calls.append(('close',))
    monkeypatch.setattr(remote,'BrokerConnection',Independent)
    control=ActControl(Primary());control.context=context
    assert control.stop('s') is True
    assert [item[0] for item in calls]==['connect','revoke','status','close']
    assert calls[0][2].get('connection_fd') is None
    assert calls[1][1]==context
    with pytest.raises(PermissionError,match='SESSION_MISMATCH'):control.stop('old')
    assert len(calls)==4
