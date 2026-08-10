import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / 'scripts'
    / 'so101_stack_inventory.py'
)
SPEC = importlib.util.spec_from_file_location('so101_stack_inventory', SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

classify_process = MODULE.classify_process
parse_ros_nodes = MODULE.parse_ros_nodes
parse_start_ticks = MODULE.parse_start_ticks
parse_tmux_panes = MODULE.parse_tmux_panes
read_process = MODULE.read_process


@pytest.mark.parametrize(
    ('cmdline', 'role'),
    [
        ('/usr/bin/gz sim -v 3 so101_pick_place.sdf', 'gazebo'),
        ('ruby /usr/bin/gz sim -g --render-engine ogre2', 'gazebo'),
        ('gz-sim-gui --render-engine ogre2', 'gazebo'),
        ('/opt/ros/jazzy/lib/moveit_ros_move_group/move_group', 'moveit'),
        ('pick_place_state_machine --ros-args', 'pick_place'),
        (
            'python3 /home/user/ws/install/so101_gazebo_demo_cpp/lib/'
            'so101_gazebo_demo_cpp/pick_place_state_machine --ros-args',
            'pick_place',
        ),
        ('/opt/ros/jazzy/lib/rviz2/rviz2 -d moveit.rviz', 'rviz'),
        ('python unrelated_training.py', None),
        ('/usr/bin/bash', None),
    ],
)
def test_classify_process(cmdline, role):
    assert classify_process(cmdline) == role


def test_source_never_signals_and_runs_commands_through_one_runner():
    source = SCRIPT_PATH.read_text()
    forbidden = (
        'os.kill',
        'SIGTERM',
        'SIGKILL',
        'SIGINT',
        'signal.',
        'send_signal',
        'terminate(',
        '.kill(',
        'pkill',
        'killall',
        'tmux kill',
    )
    for token in forbidden:
        assert token not in source, f'forbidden token in source: {token}'
    assert source.count('subprocess.run') == 1
    assert 'def default_runner' in source


def test_parse_start_ticks_reads_field_after_comm():
    stat = '4242 (gz sim) S 1 4242 4242 0 -1 4194304 100 0 0 0 5 2 0 0 20 0 1 0 987654 1000 100'
    assert parse_start_ticks(stat) == 987654


def test_parse_ros_nodes_drops_blank_lines():
    assert parse_ros_nodes('/move_group\n\n/rviz2\n') == ['/move_group', '/rviz2']


def test_parse_tmux_panes_splits_tab_separated_fields():
    text = 'sim\t0\t1\t4242\tgz\nsim\t0\t2\t4243\tzsh\n'
    assert parse_tmux_panes(text) == [
        {
            'session': 'sim',
            'window_index': 0,
            'pane_index': 1,
            'pane_pid': 4242,
            'command': 'gz',
        },
        {
            'session': 'sim',
            'window_index': 0,
            'pane_index': 2,
            'pane_pid': 4243,
            'command': 'zsh',
        },
    ]


def _write_process(proc_root, pid, cmdline, stat, environ=None, cwd_target=None):
    proc_dir = proc_root / str(pid)
    proc_dir.mkdir(parents=True)
    proc_dir.joinpath('cmdline').write_bytes(cmdline)
    proc_dir.joinpath('stat').write_text(stat)
    if environ is not None:
        proc_dir.joinpath('environ').write_bytes(environ)
    if cwd_target is not None:
        proc_dir.joinpath('cwd').symlink_to(cwd_target)
    return proc_dir


STAT = '100 (move_group) S 1 100 100 0 -1 4194304 100 0 0 0 5 2 0 0 20 0 1 0 555 1000 100'


def test_read_process_extracts_filtered_fields(tmp_path):
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    proc_dir = _write_process(
        tmp_path,
        100,
        b'/opt/ros/jazzy/lib/moveit_ros_move_group/move_group\0--ros-args\0',
        STAT,
        environ=b'ROS_DOMAIN_ID=42\0GZ_PARTITION=so101\0SECRET_TOKEN=abc\0',
        cwd_target=workspace,
    )
    info = read_process(proc_dir)
    assert info.pid == 100
    assert info.role == 'moveit'
    assert info.start_ticks == 555
    assert 'move_group' in info.cmdline
    assert info.cwd == str(workspace)
    assert info.environment == {
        'ROS_DOMAIN_ID': '42',
        'GZ_PARTITION': 'so101',
    }


def test_read_process_omits_unreadable_details(tmp_path):
    proc_dir = _write_process(
        tmp_path,
        101,
        b'pick_place_state_machine\0--ros-args\0',
        '101 (pick_place_state_machine) S 1 101 101 0 -1 4194304 100 0 0 0 '
        '5 2 0 0 20 0 1 0 777 1000 100',
    )
    info = read_process(proc_dir)
    assert info.role == 'pick_place'
    assert info.start_ticks == 777
    assert info.cwd is None
    assert info.environment == {}


def test_read_process_returns_none_for_unrelated_processes(tmp_path):
    proc_dir = _write_process(
        tmp_path, 102, b'python\0unrelated_training.py\0',
        '102 (python) S 1 102 102 0 -1 4194304 100 0 0 0 '
        '5 2 0 0 20 0 1 0 888 1000 100',
    )
    assert read_process(proc_dir) is None


def _empty_runner(arguments, timeout):
    raise RuntimeError(f'command unavailable: {arguments[0]}')


def _failing_backend_factory():
    raise RuntimeError('DISPLAY is not set; source ~/gui-env.zsh first')


def test_main_uses_only_injected_read_commands(tmp_path, capsys):
    commands = []

    def fake_runner(arguments, timeout):
        commands.append(list(arguments))
        if arguments[:3] == ['ros2', 'node', 'list']:
            return '/move_group\n/rviz2\n'
        if arguments[:2] == ['tmux', 'list-panes']:
            return 'sim\t0\t0\t4242\tzsh\n'
        raise AssertionError(f'unexpected command: {arguments!r}')

    proc_root = tmp_path / 'proc'
    proc_root.mkdir()
    output = tmp_path / 'inventory.json'
    exit_code = MODULE.main(
        ['--json', str(output)],
        runner=fake_runner,
        backend_factory=_failing_backend_factory,
        proc_root=proc_root,
        environ={'ROS_DOMAIN_ID': '42', 'SECRET_TOKEN': 'abc'},
    )
    assert exit_code == 0
    assert commands == [
        ['ros2', 'node', 'list'],
        ['tmux', 'list-panes', '-a', '-F', MODULE.TMUX_PANE_FORMAT],
    ]
    payload = json.loads(output.read_text())
    assert set(payload) == {
        'captured_at',
        'environment',
        'processes',
        'ros_nodes',
        'tmux_panes',
        'windows',
        'warnings',
    }
    assert payload['environment'] == {'ROS_DOMAIN_ID': '42'}
    assert payload['processes'] == []
    assert payload['ros_nodes'] == ['/move_group', '/rviz2']
    assert payload['tmux_panes'][0]['session'] == 'sim'
    assert payload['windows'] == []
    assert any('windows' in warning for warning in payload['warnings'])
    stdout_payload = json.loads(capsys.readouterr().out)
    assert stdout_payload == payload


def test_main_warns_and_empties_sections_when_commands_fail(tmp_path, capsys):
    proc_root = tmp_path / 'proc'
    proc_root.mkdir()
    output = tmp_path / 'inventory.json'
    exit_code = MODULE.main(
        ['--json', str(output)],
        runner=_empty_runner,
        backend_factory=_failing_backend_factory,
        proc_root=proc_root,
        environ={},
    )
    assert exit_code == 0
    payload = json.loads(output.read_text())
    assert payload['ros_nodes'] == []
    assert payload['tmux_panes'] == []
    assert payload['windows'] == []
    assert payload['environment'] == {}
    assert len(payload['warnings']) == 3
    capsys.readouterr()


def test_main_refuses_to_overwrite_existing_json(tmp_path, capsys):
    output = tmp_path / 'inventory.json'
    output.write_text('original')
    proc_root = tmp_path / 'proc'
    proc_root.mkdir()
    exit_code = MODULE.main(
        ['--json', str(output)],
        runner=_empty_runner,
        backend_factory=_failing_backend_factory,
        proc_root=proc_root,
        environ={},
    )
    assert exit_code == 1
    assert output.read_text() == 'original'
    capsys.readouterr()
