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


@pytest.mark.parametrize('exit_code', [0, 7])
def test_batched_spawner_submits_all_roles_and_reaps_one_actual_child(tmp_path, exit_code):
    from so101_demo.act.head_execution_stack import RestartStack
    stack = RestartStack(controller_config_path=tmp_path/'controllers.yaml',
        environment={}, urdf_path=tmp_path/'robot.urdf', scene_path=tmp_path/'scene.xml',
        plugin_config_path=tmp_path/'plugins.yaml', workspace=tmp_path,
        session_id='batch-test', batch_spawners=True, teardown_timeout_s=.15)
    stack.log_path = tmp_path/'stack.log'
    script = tmp_path/'spawner'
    script.write_text(f'#!{sys.executable}\nimport sys,json\n'
        f'print(json.dumps(sys.argv[1:]),flush=True)\nsys.exit({exit_code})\n')
    script.chmod(0o700)
    child = stack._spawn([str(script), 'joint_state_broadcaster', '--param-file',
        str(tmp_path/'controllers.yaml')], 'spawner joint_state_broadcaster')
    neck = stack._spawn([str(script), 'neck_controller', '--inactive'], 'spawner neck_controller')
    stack.processes.extend((child, neck))
    try:
        if exit_code:
            with pytest.raises(PermissionError, match='HEAD_STACK_SPAWNER_FAILED'):
                stack.wait_startup(deadline=time.monotonic()+1.)
        else:
            result = stack.wait_startup(deadline=time.monotonic()+1.)
            assert result['ready'] and len(result['children']) == 2
            assert [row['pid'] for row in result['children']] == [child.pid, neck.pid]
            assert result['children'][0]['rc'] == 0 and child.poll() == 0
            import json
            lines = [json.loads(line) for line in stack.log_path.read_text().splitlines()]
            assert ['joint_state_broadcaster', 'arm_controller', 'gripper_controller',
                    '--param-file', str(tmp_path/'controllers.yaml')] in lines
            assert ['neck_controller', '--inactive'] in lines
    finally:
        stack.stop()


def test_batched_spawner_cannot_extend_original_startup_deadline(tmp_path):
    from so101_demo.act.head_execution_stack import RestartStack
    stack = RestartStack(controller_config_path=tmp_path/'controllers.yaml',
        environment={}, urdf_path=tmp_path/'robot.urdf', scene_path=tmp_path/'scene.xml',
        plugin_config_path=tmp_path/'plugins.yaml', workspace=tmp_path,
        session_id='batch-timeout-test', batch_spawners=True, teardown_timeout_s=.15)
    stack.log_path = tmp_path/'stack.log'
    script = tmp_path/'spawner'
    script.write_text(f'#!{sys.executable}\nimport time\ntime.sleep(3.)\n')
    script.chmod(0o700)
    child = stack._spawn([str(script), 'joint_state_broadcaster'],
                         'spawner joint_state_broadcaster')
    neck = stack._spawn([str(script), 'neck_controller'], 'spawner neck_controller')
    stack.processes.extend((child, neck))
    try:
        started = time.monotonic()
        with pytest.raises(TimeoutError, match='HEAD_STACK_SPAWNER_TIMEOUT'):
            stack.wait_startup(deadline=started+.025)
        assert time.monotonic()-started < .2
    finally:
        stack.stop()


@pytest.mark.parametrize('batched, expected_children', [(False, 6), (True, 4)])
def test_start_keeps_four_controllers_and_truthful_child_count(
        tmp_path, monkeypatch, batched, expected_children):
    from so101_demo.act.head_execution_stack import RestartStack
    from so101_demo.act.head_search import transport_measurement as transport
    script = tmp_path/'installed-child'
    script.write_text(f'#!{sys.executable}\nimport sys,json\n'
                      'print(json.dumps(sys.argv[1:]),flush=True)\n')
    script.chmod(0o700)
    monkeypatch.setattr(transport, '_package_executable', lambda *args: str(script))
    robot = tmp_path/'robot.urdf'; robot.write_text('<robot name="owned-test"/>')
    stack = RestartStack(controller_config_path=tmp_path/'controllers.yaml',
        environment={}, urdf_path=robot, scene_path=tmp_path/'scene.xml',
        plugin_config_path=tmp_path/'plugins.yaml', workspace=tmp_path,
        session_id='start-test', batch_spawners=batched, teardown_timeout_s=.15)
    try:
        stack.start()
        startup = stack.wait_startup(deadline=time.monotonic()+1.)
        assert len(stack.processes) == expected_children
        for child in stack.processes:
            assert child.wait(timeout=1.) == 0
        if batched:
            assert stack.processes[2].args[1:4] == [
                'joint_state_broadcaster', 'arm_controller', 'gripper_controller']
            assert '--inactive' not in stack.processes[2].args
            assert stack.processes[3].args[1] == 'neck_controller'
            assert len(startup['children']) == 2
        else:
            assert [child.args[1] for child in stack.processes[2:]] == [
                'joint_state_broadcaster', 'arm_controller', 'gripper_controller',
                'neck_controller']
        # only the neck waits for the owner: it is configured and left inactive by its spawner
        neck_spawners = [child for child in stack.processes[2:] if child.args[1] == 'neck_controller']
        assert len(neck_spawners) == 1 and '--inactive' in neck_spawners[0].args
        assert not any('--inactive' in child.args for child in stack.processes[2:]
                       if child.args[1] != 'neck_controller')
        retirement = stack.stop()
        assert retirement['closed'] and len(retirement['children']) == expected_children
        assert len({child['pid'] for child in retirement['children']}) == expected_children
    finally:
        stack.stop()
