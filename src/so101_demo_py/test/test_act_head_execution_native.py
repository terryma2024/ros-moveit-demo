"""Fresh Head credentials bind the owned live child and an independent fault peer."""

import importlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import uuid

import pytest

from test_act_head_execution_composition import build_inputs
from so101_teleop.unified.controller_reservation_paths import controller_reservation_directory


def native_module():
    return importlib.import_module('so101_demo.adapters.act.head_execution_native')


@pytest.fixture
def child():
    # This owned sleeper supplies OS identity only; no ROS, model or hardware.
    processes = []
    def start(environment):
        process = subprocess.Popen([sys.executable, '-c', "import time; print('READY',flush=True); time.sleep(60)"],
                                   env=dict(os.environ, **environment),stdout=subprocess.PIPE,text=True)
        processes.append(process)
        import selectors
        with selectors.DefaultSelector() as ready:
            ready.register(process.stdout,selectors.EVENT_READ)
            assert ready.select(2.),'owned identity fixture did not finish exec'
        assert process.stdout.readline()=='READY\n'
        return process
    try:
        yield start
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=2.)


def scoped_inputs(tmp_path):
    inputs, policy = build_inputs(tmp_path)
    session = 'native-' + uuid.uuid4().hex
    inputs.document['run']['session_id'] = session
    # AF_UNIX paths cap at 107 bytes, so the reservation root is a short private directory outside the (long) test scratch.
    root = Path(tempfile.mkdtemp(prefix='so101-hrn-', dir='/tmp'))
    directory = controller_reservation_directory(root, session)
    inputs.document['ros']['environment'].update(
        SO101_ACT_RESERVATION_ROOT=str(root),
        SO101_ACT_CONTROLLER_RESERVATION_DIR=str(directory),
        SO101_SIMULATION_SESSION_ID=session)
    return inputs, policy, directory


def test_head_credentials_use_actual_child_and_distinct_main_fault_capabilities(tmp_path, child):
    inputs, policy, directory = scoped_inputs(tmp_path)
    child = child(inputs.document['ros']['environment'])
    stack = SimpleNamespace(processes=[child], environment=inputs.document['ros']['environment'])
    pair = native_module().provision_owned_native(inputs, stack, policy)
    main, fault = pair['native_keywords'], pair['revoker_keywords']
    assert main['native_owner']['pid'] == child.pid != os.getpid()
    assert main['native_owner'] == fault['native_owner']
    assert main['capability'] != fault['capability']
    assert len(main['capability']) == len(fault['capability']) == 32
    assert main['directory'] == str(directory)
    assert fault['path'] == str(directory / 'neck-primary-revoke.sock')
    assert fault['timeout_s'] == policy.native_close_timeout_s
    assert fault['simulation_policy'] is policy
    assert main['session_id'] == inputs.run['session_id']
    assert directory.stat().st_mode & 0o777 == 0o700
    for name in ('neck.provision', 'neck-primary-revoke.provision'):
        path = directory / name
        assert path.stat().st_mode & 0o777 == 0o600
        body = path.read_bytes()
        assert int.from_bytes(body[12:16], 'big') == os.getpid()
        assert pair['provision_receipts'][name]['bytes'] == len(body)
    primary = (directory / 'neck-primary-revoke.provision').read_bytes()
    assert int.from_bytes(primary[60:64], 'big') == child.pid
    assert not (directory / 'arm.provision').exists()
    assert not (directory / 'gripper.provision').exists()


@pytest.mark.parametrize('damage', ['missing', 'foreign_directory', 'session', 'ambient',
                                    'exited', 'child_environment'])
def test_native_credentials_refuse_incomplete_scope_or_dead_child(tmp_path, child, monkeypatch, damage):
    inputs, policy, directory = scoped_inputs(tmp_path)
    environment = inputs.document['ros']['environment']
    child = child(dict(environment, **({'SO101_SIMULATION_SESSION_ID': 'foreign'}
                                      if damage == 'child_environment' else {})))
    stack = SimpleNamespace(processes=[child], environment=dict(environment))
    if damage == 'missing':
        environment.pop('SO101_ACT_RESERVATION_ROOT')
    elif damage == 'foreign_directory':
        environment['SO101_ACT_CONTROLLER_RESERVATION_DIR'] = str(directory.parent / 'foreign')
        stack.environment = dict(environment)
    elif damage == 'session':
        environment['SO101_SIMULATION_SESSION_ID'] = 'other'
        stack.environment = dict(environment)
    elif damage == 'ambient':
        stack.environment['SO101_SIMULATION_SESSION_ID'] = 'ambient'
    elif damage == 'exited':
        child.terminate()
        child.wait(timeout=2.)
    with pytest.raises((PermissionError, ValueError)):
        native_module().provision_owned_native(inputs, stack, policy)
    assert not (directory / 'neck.provision').exists()
    assert not (directory / 'neck-primary-revoke.provision').exists()
