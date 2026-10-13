"""The native shell of the instance program: native-only facts, the native layout, and the exit codes.

The program itself is `test_program.py`; here only what the shell adds. Real: the spec loader, the layout rules and a real
subprocess of the entry module. Controlled: `run_instance`, whose own behavior is the program's test.
"""

import asyncio
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from test_campaign_shard import fixture
from so101_demo.runtime.act_instance import program
from so101_demo.runtime.container_campaign.paths import make_campaign_paths


def shell():
    return importlib.import_module('so101_demo.cli.act_instance_native')


def native_spec(tmp_path):
    """A readiness spec whose owned root lives in a real campaign run (the layout marker the shell needs)."""
    paths = make_campaign_paths(tmp_path, 'campaign')
    root = paths['measurement']/'w00'/'g1'
    root.mkdir(parents=True)
    path, document = fixture(tmp_path)
    document = dict(document, owned_root=str(root))
    path.write_text(json.dumps(document))
    return path, document, paths


def leader(monkeypatch):
    monkeypatch.setattr(os, 'getpgrp', lambda: os.getpid())
    monkeypatch.setattr(os, 'getsid', lambda _pid: os.getpid())


def environment(monkeypatch, document):
    monkeypatch.setenv('SO101_ACT_INSTANCE_ROOT', document['owned_root'])
    monkeypatch.setenv('SO101_ACT_INSTANCE_OUTPUT', document['owned_root']+'/output')


def test_the_native_layout_is_the_owned_roots_own_directories_and_the_hosts_teacher_socket(tmp_path):
    path, document, paths = native_spec(tmp_path)
    layout = shell().native_layout(document, tmp_path/'install', tmp_path/'ros/bin/ros2')
    root = Path(document['owned_root'])
    assert (layout.owned_root, layout.output_root, layout.control_root) == (root, root/'output', root/'control')
    assert layout.teacher_socket == paths['run']/'ipc/teacher/inference.sock'
    assert layout.install_prefix == tmp_path/'install' and layout.ros2_executable == tmp_path/'ros/bin/ros2'


def test_a_long_run_root_is_no_problem_for_the_control_and_teacher_sockets(tmp_path):
    """Both are reached through the pinned parent directory, so the AF_UNIX path limit never applies to them."""
    deep = tmp_path/('d'*60)/('e'*60)
    deep.mkdir(parents=True)
    path, document, paths = native_spec(deep)
    layout = shell().native_layout(document, deep/'install', deep/'ros2')
    assert len(str(layout.control_root/'normal.sock')) > 110 and len(str(layout.teacher_socket)) > 110
    from so101_demo.runtime.inference.codec import open_socket_parent
    from so101_demo.runtime.parallel_ipc.frames import transport_address
    for directory in (layout.control_root, layout.teacher_socket.parent):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = open_socket_parent(layout.control_root/'normal.sock')
    try:
        assert len(transport_address(layout.control_root/'normal.sock', fd)) < 100
    finally:
        os.close(fd)


def test_the_shell_calls_the_one_instance_program_with_the_native_layout(tmp_path, monkeypatch):
    assert shell().run_instance is program.run_instance
    path, document, paths = native_spec(tmp_path)
    spec, runtime = shell().load_spec(path)
    seen = {}
    async def fake(loaded_spec, loaded_runtime, layout):
        seen.update(spec=loaded_spec, runtime=loaded_runtime, layout=layout)
        return 7
    monkeypatch.setattr(shell(), 'run_instance', fake)
    leader(monkeypatch)
    environment(monkeypatch, document)
    monkeypatch.setattr(shell(), 'running_installed_code', lambda prefix: True)
    ros2 = tmp_path/'ros/bin/ros2'
    assert shell().main(['--spec', str(path), '--install-prefix', str(tmp_path/'install'), '--ros2', str(ros2)]) == 7
    assert seen['spec'] == spec and seen['layout'] == shell().native_layout(spec, tmp_path/'install', ros2)


@pytest.mark.parametrize('damage', ['not_a_group_leader', 'marker_missing', 'marker_other_root', 'output_missing',
                                    'code_not_installed', 'relative_prefix'])
def test_a_native_instance_refuses_to_run_without_its_native_facts(tmp_path, monkeypatch, damage):
    path, document, paths = native_spec(tmp_path)
    spec, runtime = shell().load_spec(path)
    monkeypatch.setattr(shell(), 'run_instance', lambda *args: pytest.fail('ran the program without the native facts'))
    environment(monkeypatch, document)
    monkeypatch.setattr(shell(), 'running_installed_code', lambda prefix: True)
    prefix = tmp_path/'install'
    expected = 'CAMPAIGN_NATIVE_ENVIRONMENT_DRIFT'
    if damage != 'not_a_group_leader':
        leader(monkeypatch)
    if damage == 'not_a_group_leader':
        monkeypatch.setattr(os, 'getpgrp', lambda: os.getpid()+1)
        expected = 'CAMPAIGN_NATIVE_GROUP_REQUIRED'
    elif damage == 'marker_missing': monkeypatch.delenv('SO101_ACT_INSTANCE_ROOT')
    elif damage == 'marker_other_root': monkeypatch.setenv('SO101_ACT_INSTANCE_ROOT', document['owned_root']+'-other')
    elif damage == 'output_missing': monkeypatch.delenv('SO101_ACT_INSTANCE_OUTPUT')
    elif damage == 'code_not_installed':
        monkeypatch.setattr(shell(), 'running_installed_code', lambda prefix: False)
        expected = 'CAMPAIGN_NATIVE_CODE_NOT_INSTALLED'
    else:
        prefix, expected = Path('install'), 'CAMPAIGN_NATIVE_CODE_NOT_INSTALLED'
    with pytest.raises(ValueError, match=expected):
        asyncio.run(shell().run_native(spec, runtime, prefix, tmp_path/'ros2'))
    assert shell().main(['--spec', str(path), '--install-prefix', str(prefix), '--ros2', str(tmp_path/'ros2')]) == 1


def test_a_bad_spec_is_refused_before_anything_runs(tmp_path, monkeypatch):
    path, document, paths = native_spec(tmp_path)
    path.write_text(json.dumps(dict(document, worker_id='w01')))
    monkeypatch.setattr(shell(), 'run_native', lambda *args: pytest.fail('invalid spec started an instance'))
    assert shell().main(['--spec', str(path), '--install-prefix', str(tmp_path), '--ros2', str(tmp_path/'ros2')]) == 2


def test_the_installed_code_check_is_about_where_so101_demo_was_imported_from():
    import so101_demo
    package_root = Path(os.path.abspath(so101_demo.__file__)).parent
    assert shell().running_installed_code(package_root.parent) is True
    assert shell().running_installed_code(package_root/'nowhere') is False
    assert shell().running_installed_code(Path('/definitely/not/the/prefix')) is False


def test_the_entry_module_runs_as_a_real_process_and_refuses_source_trees(tmp_path):
    """A real subprocess in a session of its own, with the Host's instance environment: it stops at the installed-code fact."""
    path, document, paths = native_spec(tmp_path)
    environment = dict(os.environ, SO101_ACT_INSTANCE_ROOT=document['owned_root'],
                       SO101_ACT_INSTANCE_OUTPUT=document['owned_root']+'/output')
    result = subprocess.run([sys.executable, '-m', 'so101_demo.cli.act_instance_native', '--spec', str(path),
        '--install-prefix', str(tmp_path/'not-the-source-tree'), '--ros2', '/usr/bin/true'], env=environment, start_new_session=True,
        capture_output=True, text=True, timeout=120)
    assert result.returncode == 1 and 'CAMPAIGN_NATIVE_CODE_NOT_INSTALLED' in result.stderr
    missing = subprocess.run([sys.executable, '-m', 'so101_demo.cli.act_instance_native', '--spec', str(path)],
        env=environment, capture_output=True, text=True, timeout=120)
    assert missing.returncode == 2 and 'install-prefix' in missing.stderr and '--ros2' in missing.stderr
