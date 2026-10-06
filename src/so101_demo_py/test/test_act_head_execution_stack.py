"""Owned transport retirement honors the declared Head budget and retains failure."""

import importlib
import signal
import sys
import time

import pytest


def stack_for_test(tmp_path):
    from so101_demo.adapters.act.head_execution_provider import RESOURCE_MODULES
    module_name, name = RESOURCE_MODULES['stack']
    constructor = getattr(importlib.import_module(module_name), name)
    stack = constructor(controller_config_path=tmp_path/'controllers.yaml',
        environment={},urdf_path=tmp_path/'robot.urdf',scene_path=tmp_path/'scene.xml',
        plugin_config_path=tmp_path/'plugins.yaml',workspace=tmp_path,session_id='stack-test')
    stack.teardown_timeout_s = .15
    stack.log_path = tmp_path/'stack.log'
    return stack


def wait_ready(stack, child):
    deadline=time.monotonic()+2.
    while time.monotonic()<deadline:
        assert child.poll() is None
        if 'READY' in stack.log_path.read_text():return
        time.sleep(.005)
    raise TimeoutError('owned child did not become ready')


def test_provider_transport_has_no_qualification_restart_import():
    from so101_demo.adapters.act.head_execution_provider import RESOURCE_MODULES
    assert RESOURCE_MODULES['stack'][0] == 'so101_demo.act.head_execution_stack'


def test_head_stack_bounds_stubborn_child_and_replays_failed_retirement(tmp_path):
    stack=stack_for_test(tmp_path)
    child=stack._spawn([sys.executable,'-c',
        'import signal,time;signal.signal(signal.SIGINT,signal.SIG_IGN);print("READY",flush=True);time.sleep(3.)'],
        'owned-test-child')
    stack.processes.append(child)
    try:
        wait_ready(stack,child)
        started=time.monotonic();receipt=stack.stop();elapsed=time.monotonic()-started
        assert elapsed < .5,elapsed
        assert receipt['retired'] is True and receipt['closed'] is False
        assert receipt['forced_kill'] == [child.pid]
        assert receipt['children'][0]['rc'] == -signal.SIGKILL
        assert stack.stop() == receipt
        assert all(handle.closed for handle in stack.handles)
    finally:
        if child.poll() is None:child.kill();child.wait(timeout=1.)
        for handle in stack.handles:handle.close()


def test_head_stack_graceful_exit_is_truthful_and_idempotent(tmp_path):
    stack=stack_for_test(tmp_path)
    child=stack._spawn([sys.executable,'-c',
        'import signal,sys,time;signal.signal(signal.SIGINT,lambda *args:sys.exit(0));print("READY",flush=True);time.sleep(3.)'],
        'owned-test-child')
    stack.processes.append(child)
    try:
        wait_ready(stack,child)
        receipt=stack.stop()
        assert receipt['retired'] is True and receipt['closed'] is True
        assert receipt['forced_kill'] == []
        assert receipt['children'][0]['rc'] == 0
        assert stack.stop() == receipt
    finally:
        if child.poll() is None:child.kill();child.wait(timeout=1.)
        for handle in stack.handles:handle.close()


@pytest.mark.parametrize('exit_code', [0, 7])
def test_startup_reaps_all_owned_spawners_and_refuses_failed_child(tmp_path, exit_code):
    stack = stack_for_test(tmp_path)
    children = []
    try:
        for controller in ('joint_state_broadcaster', 'arm_controller',
                           'gripper_controller', 'neck_controller'):
            child = stack._spawn([sys.executable, '-c',
                f'import time,sys;time.sleep(.02);sys.exit({exit_code})'],
                'spawner '+controller)
            children.append(child)
            stack.processes.append(child)
        if exit_code:
            with pytest.raises(PermissionError, match='HEAD_STACK_SPAWNER_FAILED'):
                stack.wait_startup(deadline=time.monotonic()+1.)
        else:
            receipt = stack.wait_startup(deadline=time.monotonic()+1.)
            assert receipt['ready'] is True
            assert len(receipt['children']) == 4
            assert all(row['rc'] == 0 for row in receipt['children'])
            assert all(child.poll() == 0 for child in children)
    finally:
        stack.stop()


def test_startup_wait_uses_declared_absolute_deadline(tmp_path):
    stack = stack_for_test(tmp_path)
    try:
        for controller in ('joint_state_broadcaster', 'arm_controller',
                           'gripper_controller', 'neck_controller'):
            child = stack._spawn([sys.executable, '-c', 'import time;time.sleep(3.)'],
                'spawner '+controller)
            stack.processes.append(child)
        started = time.monotonic()
        with pytest.raises(TimeoutError, match='HEAD_STACK_SPAWNER_TIMEOUT'):
            stack.wait_startup(deadline=started+.025)
        assert time.monotonic()-started < .2
    finally:
        stack.stop()
