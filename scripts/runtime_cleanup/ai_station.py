#!/usr/bin/env python3
"""Preview or stop ai-station ROS/Teleop processes without removing environments."""

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import select
import shutil
import signal
import socket
import subprocess
import sys


HOST = 'AI-STATION-001'
SESSIONS = frozenset(('so101-expert-validation', 'so101-mujoco', 'so101-teleop'))
ENTRIES = frozenset((
    'so101_teleop_server.py', 'so101_expert_validation_server.py',
    'run_so101_adaptive_batch.zsh', 'run_so101_adaptive_worker_scaling.zsh',
))
ROS_LIBRARIES = re.compile(r'/(?:librcl|librmw|libroscpp|libmoveit|libgazebo|libgz-sim)[^ /]*\.so')
PACKAGE_ENTRY = re.compile(r'/(?:so101_[^/]+|mujoco_[^/]+)/lib/[^/]+/')


@dataclass(frozen=True)
class Process:
    pid: int
    ppid: int
    started_ticks: int
    uid: int
    argv: tuple
    exe: str
    state: str
    maps: str

    def receipt(self):
        return {
            'pid': self.pid, 'ppid': self.ppid, 'started_ticks': self.started_ticks,
            'uid': self.uid, 'exe': self.exe,
            'argv_sha256': hashlib.sha256('\0'.join(self.argv).encode()).hexdigest(),
            'reason': runtime_reason(self),
        }


def read_process(pid):
    root = Path('/proc') / str(pid)
    raw = (root / 'stat').read_text()
    fields = raw[raw.rfind(')') + 2:].split()
    argv = tuple((root / 'cmdline').read_bytes().decode(errors='replace').split('\0')[:-1])
    uid = root.stat().st_uid
    try:
        exe = os.readlink(root / 'exe')
    except PermissionError:
        exe = argv[0] if argv else ''
    except FileNotFoundError:
        # Zombies have no executable link and cannot execute further work.
        if fields[0] != 'Z':
            raise
        exe = ''
    try:
        maps = (root / 'maps').read_text() if uid == os.getuid() else ''
    except PermissionError:
        maps = 'METADATA_DENIED'
    return Process(pid, int(fields[1]), int(fields[19]), uid, argv, exe, fields[0], maps)


def interpreter_entry(argv):
    index = 1
    while index < len(argv):
        arg = argv[index]
        if arg in ('-c', '-lc', '-ic'):
            return '', ''
        if arg == '-m':
            return 'module', argv[index + 1] if index + 1 < len(argv) else ''
        if arg in ('-X', '-W'):
            index += 2
            continue
        if not arg.startswith('-'):
            return 'script', arg
        index += 1
    return '', ''


def runtime_reason(process):
    if not process.argv or process.state == 'Z':
        return ''
    executable = Path(process.argv[0]).name
    # Prompt text, inherited ROS variables and a so101 training filename are not identity.
    if executable in ('codex', 'codex-code-mode-host', 'cua-driver'):
        return ''
    if process.exe.startswith('/opt/ros/') or PACKAGE_ENTRY.search(process.exe):
        return 'ROS or SO-101 package executable'
    if executable in ('ros2', 'roscore', 'roslaunch', 'rosmaster', 'rosout', 'move_group', 'rviz2', 'gzserver', 'gzclient'):
        return 'ROS or simulator command'
    if executable == 'gz' and 'sim' in process.argv[1:3]:
        return 'Gazebo simulation'
    if executable.startswith(('python', 'bash', 'zsh', 'sh', 'ruby')):
        kind, entry = interpreter_entry(process.argv)
        if kind == 'module' and (entry.startswith('ros2cli.') or entry in ('launch', 'launch_ros')):
            return 'ROS module'
        if kind == 'script' and (Path(entry).name in ENTRIES or entry.startswith('/opt/ros/') or PACKAGE_ENTRY.search(entry)):
            return 'ROS or Teleop entry script'
        if kind == 'script' and Path(entry).name == 'gz' and 'sim' in process.argv[2:4]:
            return 'Gazebo simulation wrapper'
    if '/opt/ros/' in process.maps or ROS_LIBRARIES.search(process.maps):
        return 'loaded ROS or simulator libraries'
    return ''


def run(args, empty_codes=()):
    executable = shutil.which(args[0])
    if executable is None:
        raise RuntimeError(f'required command is unavailable: {args[0]}')
    result = subprocess.run([executable, *args[1:]], capture_output=True, text=True, timeout=15)
    if result.returncode in empty_codes and ('no server running' in result.stderr or 'No such file or directory' in result.stderr):
        return ''
    if result.returncode:
        raise RuntimeError(f'{args[0]} inspection failed: {result.stderr.strip()}')
    return result.stdout


def list_panes():
    text = run(['tmux', 'list-panes', '-a', '-F', '#{session_name}|#{pane_id}|#{pane_pid}|#{pane_current_command}'], empty_codes=(1,))
    return [dict(zip(('session', 'pane', 'pid', 'command'), line.split('|'))) for line in text.splitlines()]


def snapshot():
    processes = []
    denials = []
    for root in Path('/proc').iterdir():
        if not root.name.isdigit() or int(root.name) == os.getpid():
            continue
        try:
            process = read_process(int(root.name))
        except (FileNotFoundError, ProcessLookupError):
            continue
        if process.maps == 'METADATA_DENIED':
            denials.append({'pid': process.pid, 'exe': process.exe})
        processes.append(process)
    targets = [process for process in processes if runtime_reason(process)]
    blockers = [f'ROS/Teleop PID {process.pid} belongs to another UID ({process.uid})' for process in targets if process.uid != os.getuid()]
    # Stop managed launchers through their lifecycle, not by killing a child that respawns.
    containers = run(['docker', 'ps', '--format', '{{.ID}} {{.Names}} {{.Image}}']).splitlines()
    if containers:
        blockers.append('running containers require ownership/lifecycle handling: ' + '; '.join(containers))
    service_text = run(['systemctl', '--user', 'list-units', '--type=service', '--state=active,activating', '--no-legend', '--no-pager', '--plain'])
    for line in service_text.splitlines():
        name = line.split()[0]
        if re.match(r'^(?:so101|ros|teleop|mujoco|gazebo)[-.@]', name):
            blockers.append('active managed runtime service: ' + name)
    for process in targets:
        try:
            cgroup = (Path('/proc') / str(process.pid) / 'cgroup').read_text()
        except FileNotFoundError:
            continue
        services = re.findall(r'/([^/]+\.service)(?:/|$)', cgroup, flags=re.MULTILINE)
        for service in services:
            if not service.startswith('session-') and not re.fullmatch(r'user@\d+\.service', service):
                blockers.append(f'PID {process.pid} has service owner {service}; stop its launcher first')
    return {'processes': processes, 'targets': targets, 'panes': list_panes(), 'blockers': sorted(set(blockers)), 'metadata_denials': denials, 'containers': containers}


def stop_process(expected, timeout):
    """Bind the signal to a pidfd, then recheck PID/start/argv/executable identity."""
    try:
        fd = os.pidfd_open(expected.pid)
    except ProcessLookupError:
        return 'already exited'
    try:
        try:
            current = read_process(expected.pid)
        except (FileNotFoundError, ProcessLookupError):
            return 'already exited'
        if current.state == 'Z':
            return 'not executing (zombie)'
        if (current.pid, current.started_ticks, current.uid, current.argv, current.exe) != (expected.pid, expected.started_ticks, expected.uid, expected.argv, expected.exe):
            raise RuntimeError(f'PID {expected.pid} identity changed; no signal sent')
        if not runtime_reason(current):
            raise RuntimeError(f'PID {expected.pid} no longer has runtime identity')
        signal.pidfd_send_signal(fd, signal.SIGINT)
        if not select.select([fd], [], [], timeout)[0]:
            raise RuntimeError(f'PID {expected.pid} did not exit after SIGINT; no automatic escalation')
        return 'exited after SIGINT'
    finally:
        os.close(fd)


def close_sessions(before, evidence):
    closed = []
    for session in sorted(SESSIONS):
        original = [pane for pane in before['panes'] if pane['session'] == session]
        if not original:
            continue
        current = [pane for pane in list_panes() if pane['session'] == session]
        if [(p['pane'], p['pid']) for p in current] != [(p['pane'], p['pid']) for p in original]:
            raise RuntimeError(f'{session} pane identity changed; session retained')
        for pane in current:
            pid = int(pane['pid'])
            initial_shell = next(process for process in before['processes'] if process.pid == pid)
            shell = read_process(pid)
            if shell.started_ticks != initial_shell.started_ticks or pane['command'] not in ('zsh', 'bash'):
                raise RuntimeError(f'{session} is not the original idle shell; retained')
            for root in Path('/proc').iterdir():
                if not root.name.isdigit():
                    continue
                try:
                    child = read_process(int(root.name))
                except FileNotFoundError:
                    continue
                if child.ppid == pid:
                    raise RuntimeError(f'{session} still has child PID {child.pid}; retained')
            capture = run(['tmux', 'capture-pane', '-p', '-J', '-t', pane['pane'], '-S', '-2000'])
            (evidence / f'{session}-{pane["pane"].lstrip("%")}.txt').write_text(capture)
        run(['tmux', 'kill-session', '-t', '=' + session])
        closed.append(session)
    return closed


def public_snapshot(value):
    return {key: [process.receipt() for process in items] if key in ('processes', 'targets') else items for key, items in value.items()}


def display_snapshot(value):
    public = public_snapshot(value)
    public['inspected_process_count'] = len(public.pop('processes'))
    return public


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='stop verified processes; default is preview only')
    parser.add_argument('--evidence-dir', type=Path, help='new, nonexistent directory under the task registered evidence root')
    parser.add_argument('--timeout', type=float, default=15, help='SIGINT exit timeout per PID in seconds (default: 15)')
    args = parser.parse_args(argv)
    evidence = None
    actions = []
    try:
        if sys.platform != 'linux' or socket.gethostname() != HOST:
            raise RuntimeError(f'this entry point is only for Linux host {HOST}')
        if not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
            raise RuntimeError('Python/Linux pidfd support is required')
        if not math.isfinite(args.timeout) or args.timeout <= 0 or args.timeout > 60:
            raise RuntimeError('--timeout must be greater than 0 and at most 60 seconds')
        if args.apply and args.evidence_dir is None:
            raise RuntimeError('--apply requires a new --evidence-dir')
        if args.evidence_dir is not None:
            args.evidence_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
            evidence = args.evidence_dir
        before = snapshot()
        if evidence:
            (evidence / 'before.json').write_text(json.dumps(public_snapshot(before), indent=2) + '\n')
        if not args.apply:
            print(json.dumps({'mode': 'PREVIEW', **display_snapshot(before)}, indent=2))
            return 2 if before['blockers'] else 0
        if before['blockers']:
            raise RuntimeError('; '.join(before['blockers']))
        for target in before['targets']:
            actions.append({**target.receipt(), 'result': stop_process(target, args.timeout)})
        closed = close_sessions(before, evidence)
        after = snapshot()
        result = {'mode': 'APPLY', 'result': 'PASS' if not after['targets'] and not after['blockers'] else 'INCOMPLETE', 'actions': actions, 'closed_sessions': closed, 'after': public_snapshot(after)}
        (evidence / 'after.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({**result, 'after': display_snapshot(after)}, indent=2))
        return 0 if result['result'] == 'PASS' else 2
    except (RuntimeError, OSError, subprocess.SubprocessError, StopIteration) as error:
        result = {'result': 'BLOCKED', 'error': str(error), 'actions_completed': actions}
        if evidence:
            (evidence / 'blocked.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
