"""Exercise the exec server dispatch loop with controlled transport and runtime.

This guards server routing, not crypto, real ROS freshness, or qualification.
"""
import os
import sys
import pytest

from test_act_head_monitor_process import config
from so101_demo.adapters.act import head_monitor_process as server


@pytest.mark.parametrize('operation',['PREARM_INPUTS','PREARM_READY','EXPOSURE_ADMIT','EXPOSURE_FINISH'])
@pytest.mark.parametrize('parent_module',[None,'torch','mujoco'])
def test_exec_server_routes_prearm_to_runtime_after_presence_and_configuration(config,monkeypatch,operation,parent_module):
    if parent_module is not None:monkeypatch.setitem(sys.modules,parent_module,object())
    identity=server._peer(os.getpid());handled=[];replies=[]
    field={'EXPOSURE_ADMIT':'exposure','EXPOSURE_FINISH':'completion'}.get(operation,'policy')
    requests=iter([dict(operation='PRESENCE'),dict(operation='CONFIGURE',configuration={}),
        dict(operation=operation,**{field:dict(policy_sha256='a'*64)}),dict(operation='RETIRE_STATUS')])
    class Socket:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def bind(self,*args):pass
        def listen(self,*args):pass
        def setblocking(self,*args):pass
        def accept(self):return Socket(),None
        def recv(self,*args):return b''
    class Channel:
        def __init__(self,*args,**kw):pass
        def receive(self):return next(requests)
        def send(self,reply):replies.append(reply)
    class Runtime:
        def __init__(self,*args):self._future=None
        def handle(self,request):
            handled.append(request['operation']);self._future=object()
            return dict(request=request['operation'],stage='RETIRED' if request['operation']=='RETIRE_STATUS' else 'POLICY_READY')
        def after_send(self):pass
        def disconnected(self):pass
    monkeypatch.setattr(sys,'argv',['exec-routing','--bootstrap-fd','0','--socket',str(config['ipc_directory']/'monitor.socket')])
    monkeypatch.setattr(server,'_bootstrap',lambda fd:dict(secret='a'*64,epoch='routing',generation=5,session_id='session',primary=identity))
    monkeypatch.setattr(server,'_peer',lambda pid:identity.copy())
    monkeypatch.setattr(server.socket,'socket',lambda *args:Socket())
    monkeypatch.setattr(server.select,'select',lambda readers,*args:(readers,[],[]))
    monkeypatch.setattr(server,'HeadMonitorChannel',Channel)
    monkeypatch.setattr(server,'MonitorRuntimeProtocol',Runtime)
    monkeypatch.setenv('CUDA_VISIBLE_DEVICES','')
    # This controlled loop represents a fresh CPU-only exec. Other tests may
    # already have loaded these modules in the parent pytest worker. Actual
    # child-process CPU isolation remains covered by the exec tests.
    for module in ('torch','mujoco'):monkeypatch.delitem(sys.modules,module,raising=False)
    assert server.main()==0
    assert handled==['CONFIGURE',operation,'RETIRE_STATUS']
    assert [reply['request'] for reply in replies]==['PRESENCE','CONFIGURE',operation,'RETIRE_STATUS']
