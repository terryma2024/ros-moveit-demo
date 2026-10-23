"""One instance program, two layouts: the container's fixed mounts and a native single worker's own directories.

Real: `run_instance`, `serve_instance`, the spec loader, the task executor, the control server and its sockets, the durable
writers. Controlled doubles: the native stack, its probes and its retirement (no ROS, Docker or container), the CUDA driver
check and the installed prefix. Both layouts run the same driver against the same program; the only things that differ are the
`InstanceLayout` values.
"""

import ast
import asyncio
import importlib
import json
import os
from pathlib import Path
import sys
import threading
import time

import pytest

from so101_demo.runtime.act_instance import identity
from so101_demo.runtime.act_instance.layout import InstanceLayout
from test_campaign_shard import collection_fixture, fixture

PROGRAM = 'so101_demo.runtime.act_instance.program'


def program():
    return importlib.import_module(PROGRAM)


class StackDouble:
    stop_timeout_s = 15.0

    def __init__(self):
        self.timeouts = []

    async def start(self, *, timeout_s):
        self.timeouts.append(timeout_s)


class ReadyDouble:
    readiness_bytes = b'{"ready":true}\n'


class RetirementDouble:
    def __init__(self):
        self.calls = 0

    async def retire(self, *, fenced):
        assert fenced is True
        self.calls += 1
        return dict(goals_stopped=True, controllers_stopped=True, ros_children_exited=True, ros_graph_empty=True,
                    forced=False)


def container_like_layout(spec, tmp_path):
    """A layout whose output and control directories are not under the owned root, as a container's bind mounts are."""
    for name in ('mount-output', 'mount-control'):
        (tmp_path/name).mkdir(mode=0o700)
    return InstanceLayout(owned_root=Path(spec['owned_root']), output_root=tmp_path/'mount-output',
        control_root=tmp_path/'mount-control', teacher_socket=tmp_path/'mount-ipc/teacher/inference.sock',
        install_prefix=tmp_path/'mount-install', ros2_executable=tmp_path/'mount-install/bin/ros2')


def native_layout(spec, tmp_path):
    """A native layout: output and control are the owned root's own directories."""
    root = Path(spec['owned_root'])
    for name in ('output', 'control'):
        (root/name).mkdir(mode=0o700, exist_ok=True)
    return InstanceLayout(owned_root=root, output_root=root/'output', control_root=root/'control',
        teacher_socket=tmp_path/'run/ipc/teacher/inference.sock', install_prefix=tmp_path/'native-install',
        ros2_executable=tmp_path/'host-ros/bin/ros2')


LAYOUTS = pytest.mark.parametrize('make_layout', [container_like_layout, native_layout],
                                  ids=['container-like', 'native'])


def parts(tmp_path, make_layout):
    path, _document = fixture(tmp_path)
    spec_module = importlib.import_module('so101_demo.runtime.act_instance.spec')
    spec, runtime = spec_module.load_spec(path)
    (Path(spec['owned_root'])/'tmp').mkdir()
    layout = make_layout(spec, tmp_path)
    return spec, runtime, layout


async def control_call(layout, operation, payload):
    from so101_demo.runtime.inference.codec import open_socket_parent
    from so101_demo.runtime.parallel_ipc.frames import transport_address
    socket_path = layout.control_root/'normal.sock'
    fd = open_socket_parent(socket_path)
    try:
        reader, writer = await asyncio.open_unix_connection(transport_address(socket_path, fd))
        writer.write(json.dumps(dict(operation=operation, payload=payload,
            deadline_ns=time.monotonic_ns()+5_000_000_000)).encode()+b'\n')
        await writer.drain()
        reply = json.loads(await reader.readline())
        writer.close()
        await writer.wait_closed()
        return reply
    finally:
        os.close(fd)


async def wait_for(condition):
    async def poll():
        while not condition():
            await asyncio.sleep(.01)
    await asyncio.wait_for(poll(), 5)


@LAYOUTS
def test_the_same_program_serves_either_layout_on_the_layouts_own_directories(tmp_path, make_layout):
    from so101_demo.runtime.container_campaign.process_identity import read_process_owner
    spec, runtime, layout = parts(tmp_path, make_layout)
    root = Path(spec['owned_root'])
    stack, retirement = StackDouble(), RetirementDouble()

    async def run():
        serving = asyncio.create_task(program().serve_instance(spec, runtime, layout, install_signals=False,
            process=read_process_owner(os.getpid()), stack=stack, ready=ReadyDouble(), retirement=retirement))
        await wait_for(lambda: (root/'stack-readiness.json').exists())
        status = await control_call(layout, 'get_status', dict(task_id=None))
        assert status['accepted'] is True and status['result']['instance_id'] == 'wave-00-w00-g1'
        stopped = await control_call(layout, 'terminate', dict(reason='layout test'))
        assert stopped['accepted'] is True
        return await asyncio.wait_for(serving, 5)
    assert asyncio.run(run()) == 0

    ready = json.loads((layout.control_root/'child-ready.json').read_text())
    assert ready['normal_socket'] == str(layout.control_root/'normal.sock')
    assert ready['safety_socket'] == str(layout.control_root/'safety.sock')
    assert json.loads((root/'instance-exit.json').read_text())['cleanup_confirmed'] is True
    assert retirement.calls == 1 and stack.timeouts == [runtime.initializing_hard_timeout_s]
    # the readiness records and the exit record sit in the owned root under both layouts
    assert sorted(item.name for item in root.iterdir() if item.is_file()) == [
        'instance-exit.json', 'runtime-ready.json', 'stack-readiness.json']


@LAYOUTS
def test_the_collection_builder_gets_the_layouts_output_and_teacher_socket(tmp_path, make_layout):
    path, document = collection_fixture(tmp_path)
    spec_module = importlib.import_module('so101_demo.runtime.act_instance.spec')
    spec, _runtime = spec_module.load_spec(path)
    layout = make_layout(spec, tmp_path)
    stack, check = object(), (lambda: True)

    builder = program().shard_builder(spec, stack=stack, layout=layout, ready_check=check)

    assert builder.keywords == dict(stack=stack, shard_spec=spec, output_root=layout.output_root,
        teacher_socket=layout.teacher_socket, ready_check=check)


def test_a_layout_is_absolute_without_traversal_and_distinct_from_the_owned_root(tmp_path):
    good = dict(owned_root=tmp_path/'o', output_root=tmp_path/'o/output', control_root=tmp_path/'o/control',
        teacher_socket=tmp_path/'t.sock', install_prefix=tmp_path/'i', ros2_executable=tmp_path/'i/bin/ros2')
    assert InstanceLayout(**good).output_root == tmp_path/'o/output'
    for name, bad in (('output_root', 'relative'), ('control_root', tmp_path/'a/../b'), ('teacher_socket', None),
                      ('install_prefix', ''), ('ros2_executable', 'ros2'), ('owned_root', 'o'), ('output_root', tmp_path/'o'),
                      ('control_root', tmp_path/'o')):
        with pytest.raises(ValueError, match='^ACT_INSTANCE_LAYOUT_INVALID$'):
            InstanceLayout(**dict(good, **{name: bad}))
    with pytest.raises(Exception):
        InstanceLayout(**good).output_root = tmp_path       # frozen


@LAYOUTS
def test_a_layout_for_another_instance_is_refused(tmp_path, make_layout):
    from so101_demo.runtime.container_campaign.process_identity import read_process_owner
    spec, runtime, layout = parts(tmp_path, make_layout)
    other = InstanceLayout(owned_root=tmp_path/'elsewhere', output_root=layout.output_root,
        control_root=layout.control_root, teacher_socket=layout.teacher_socket, install_prefix=layout.install_prefix,
        ros2_executable=layout.ros2_executable)

    with pytest.raises(ValueError, match='^ACT_INSTANCE_LAYOUT_MISMATCH$'):
        asyncio.run(program().serve_instance(spec, runtime, other, process=read_process_owner(os.getpid()),
            stack=StackDouble(), ready=ReadyDouble(), retirement=RetirementDouble()))
    with pytest.raises(ValueError, match='^ACT_INSTANCE_LAYOUT_MISMATCH$'):
        asyncio.run(program().run_instance(spec, runtime, other))


def install_prefix(layout):
    for path in (layout.ros2_executable, layout.install_prefix/'lib/so101_demo_py/act_stack_ready'):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('#!/bin/sh\n')
        path.chmod(0o700)


def instance_process(monkeypatch, spec, prefix):
    """Everything `run_instance` reads from the process: the fixed environment and the installed prefix."""
    for name in (identity.INSTANCE_ROOT_ENV, identity.INSTANCE_OUTPUT_ENV):
        monkeypatch.setenv(name, 'restored-by-monkeypatch')
    for entry in identity.instance_environment(mujoco_session_id=spec['simulation_session_id']):
        name, value = entry.split('=', 1)
        monkeypatch.setenv(name, value)
    monkeypatch.delenv('ROS_NAMESPACE', raising=False)
    import ament_index_python.packages as packages
    monkeypatch.setattr(packages, 'get_package_prefix', lambda name: str(prefix))


@LAYOUTS
def test_run_instance_marks_the_layouts_directories_and_runs_the_stack_and_serve(tmp_path, monkeypatch, make_layout):
    from so101_demo.runtime.container_campaign import gpu_driver, retirement
    spec, runtime, layout = parts(tmp_path, make_layout)
    install_prefix(layout)
    instance_process(monkeypatch, spec, layout.install_prefix)
    seen = {}
    stack_double = StackDouble()
    retire = RetirementDouble()
    monkeypatch.setattr(gpu_driver, 'verify_selected_gpu',
        lambda gpu: dict(schema_version=1, kind='ACT_SHARD_CUDA_DRIVER', gpu_uuid=gpu, cuda_device_count=1))
    monkeypatch.setattr(retirement, 'NativeShardRetirement', lambda **arguments: retire)

    def compose(launch, observer):
        seen.update(launch=launch, observer=observer)
        return ReadyDouble(), (lambda: True), stack_double
    monkeypatch.setattr(program(), 'compose_stack', compose)
    root = Path(spec['owned_root'])

    async def stop_when_ready():
        await wait_for(lambda: (root/'stack-readiness.json').exists())
        return await control_call(layout, 'terminate', dict(reason='finished'))
    holder = {}
    thread = threading.Thread(target=lambda: holder.update(reply=asyncio.run(stop_when_ready())))
    thread.start()
    exit_code = asyncio.run(program().run_instance(spec, runtime, layout))
    thread.join(5)

    assert exit_code == 0 and holder['reply']['accepted'] is True
    # the marker names the layout's directories: it is what the recorder's bag-root decision reads in this process
    assert os.environ[identity.INSTANCE_ROOT_ENV] == str(root)
    assert os.environ[identity.INSTANCE_OUTPUT_ENV] == str(layout.output_root)
    launch = seen['launch']
    assert launch.ros2_executable == layout.ros2_executable and launch.ros_domain_id == 181
    assert seen['observer'] == layout.install_prefix/'lib/so101_demo_py/act_stack_ready'
    assert launch.evidence_root == root/'stack' and (root/'stack').is_dir()
    assert json.loads((root/'gpu-driver.json').read_text())['gpu_uuid'] == spec['gpu_uuid']
    assert retire.calls == 1


@LAYOUTS
def test_run_instance_refuses_drift_in_the_prefix_the_executables_and_the_environment(tmp_path, monkeypatch, make_layout):
    spec, runtime, layout = parts(tmp_path, make_layout)
    install_prefix(layout)
    instance_process(monkeypatch, spec, tmp_path/'another-prefix')
    with pytest.raises(ValueError, match='^CAMPAIGN_SHARD_INSTALLED_EXECUTABLE_MISSING$'):
        asyncio.run(program().run_instance(spec, runtime, layout))

    instance_process(monkeypatch, spec, layout.install_prefix)
    layout.ros2_executable.chmod(0o600)
    with pytest.raises(ValueError, match='^CAMPAIGN_SHARD_INSTALLED_EXECUTABLE_MISSING$'):
        asyncio.run(program().run_instance(spec, runtime, layout))
    layout.ros2_executable.chmod(0o700)

    monkeypatch.setenv('ROS_DOMAIN_ID', '182')
    with pytest.raises(ValueError, match='^CAMPAIGN_SHARD_ENVIRONMENT_DRIFT$'):
        asyncio.run(program().run_instance(spec, runtime, layout))
    monkeypatch.setenv('ROS_DOMAIN_ID', '181')
    monkeypatch.setenv('ROS_NAMESPACE', '/act/w00')
    with pytest.raises(ValueError, match='^CAMPAIGN_SHARD_ENVIRONMENT_DRIFT$'):
        asyncio.run(program().run_instance(spec, runtime, layout))
    assert not (Path(spec['owned_root'])/'stack').exists()


def test_the_instance_program_has_no_container_only_branch():
    """The program, layout and spec modules know no container path, interpreter or pid check; the shells own those."""
    for name in ('program', 'layout', 'spec'):
        module = importlib.import_module(f'so101_demo.runtime.act_instance.{name}')
        tree = ast.parse(Path(module.__file__).read_text())
        literals = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]
        assert not [value for value in literals if value.startswith('/act') or 'venv' in value or value == 'native'], name
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        assert not names & {'TASK_OUTPUT_MOUNT', 'CONTAINER_CONTROL_ROOT', 'CONTAINER_INSTALL_PREFIX',
            'CONTAINER_INTERPRETER', 'CONTAINER_TEACHER_SOCKET', 'CONTAINER_IPC_ROOT', 'CONTAINER_ROS2'}, name
        assert 'executable' not in attributes, name           # no `sys.executable` interpreter check
        imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        imported |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        assert not {item for item in imported if item and ('campaign_shard' in item or 'native' in item
            or item.endswith('shard_owner'))}, name
        # no comparison against the process id (the container shell's `pid == 1` fact)
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                assert not any(isinstance(sub, ast.Call) and getattr(sub.func, 'attr', '') == 'getpid'
                               for sub in ast.walk(node)), name


def test_there_is_one_implementation_of_the_instance_logic():
    """The shells hold neither the serve loop nor the stack composition."""
    shell = importlib.import_module('so101_demo.cli.campaign_shard')
    for name in ('serve_instance', 'serve_shard', 'compose_stack', 'instance_stack_launch', 'shard_builder',
                 'StackStartAwareRetirement', 'instance_id_for'):
        assert not hasattr(shell, name) or getattr(shell, name) is getattr(program(), name, None), name
    assert shell.run_instance is program().run_instance
    assert sys.modules[PROGRAM].run_instance.__module__ == PROGRAM
