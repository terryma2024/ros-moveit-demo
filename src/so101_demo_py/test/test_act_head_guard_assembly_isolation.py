"""The actual guard fixture must honor the shared live-admission assembly lease."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from test_act_head_paused_admission import admission_peer_cpu_slot

def test_other_worker_guard_assembly_waits_for_the_live_peer(tmp_path,tmp_path_factory):
    ready=tmp_path/'ready'; entered=tmp_path/'model_entered'
    script="""
import inspect,json,os,sys,time
from pathlib import Path
from types import SimpleNamespace
import mujoco
import test_act_head_trajectory_guard as module
ready,entered,scratch=map(Path,sys.argv[1:])
def probe(*args,**kwargs):
    entered.write_text('actual MjModel constructor boundary reached')
    raise RuntimeError('assembly boundary probe completed')
mujoco.MjModel.from_xml_path=probe
ready.write_text('imports complete; entering actual guard fixture')
fixture=module.guard.__wrapped__
try:
    if 'tmp_path_factory' in inspect.signature(fixture).parameters:
        value=fixture(tmp_path_factory=SimpleNamespace(getbasetemp=lambda:scratch))
    else:value=fixture()
    if inspect.isgenerator(value):next(value)
except RuntimeError as error:
    assert str(error)=='assembly boundary probe completed'
else:raise AssertionError('fixture skipped actual model constructor')
"""
    env=dict(os.environ)
    env['PYTHONPATH']=str(Path(__file__).resolve().parent)+os.pathsep+str(Path(os.environ['SO101_HFP_REPOSITORY'])/'src/so101_demo_py/test')+os.pathsep+env.get('PYTHONPATH','')
    child=None; blocked=False
    try:
        with admission_peer_cpu_slot(tmp_path_factory):
            child=subprocess.Popen([sys.executable,'-c',script,str(ready),str(entered),str(tmp_path_factory.getbasetemp())],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            deadline=time.monotonic()+10
            while not ready.exists() and child.poll() is None and time.monotonic()<deadline:time.sleep(.01)
            assert ready.exists(), 'child did not reach the actual assembly boundary'
            deadline=time.monotonic()+2
            while child.poll() is None and time.monotonic()<deadline:
                wchan=Path(f'/proc/{child.pid}/wchan').read_text().strip()
                if 'lock' in wchan:
                    blocked=True;break
                if entered.exists():break
                time.sleep(.01)
            assert blocked and not entered.exists(), 'real other-worker model construction overtook the admission lease'
        out,err=child.communicate(timeout=10)
        assert child.returncode==0,(out,err)
        assert entered.exists(), 'guard never assembled after the lease was released'
    finally:
        if child is not None and child.poll() is None:
            child.terminate();child.communicate(timeout=10)
