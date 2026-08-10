#!/usr/bin/env python3
"""Read-only inventory of the SO101 simulation stack on ai-station.

Lists related processes from /proc, ROS nodes, tmux panes, and RViz/Gazebo
windows so an operator can select exact PIDs before stopping a stack. The
tool never sends signals and never mutates tmux or ROS state; every external
command goes through the injectable read-only ``default_runner``.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from ai_station_x11 import X11EwmhBackend, classify_window  # noqa: E402


COMMAND_TIMEOUT_SEC = 10.0
SAFE_ENVIRONMENT_KEYS = ('ROS_DOMAIN_ID', 'GZ_PARTITION', 'DISPLAY')
PROCESS_ENVIRONMENT_KEYS = ('ROS_DOMAIN_ID', 'GZ_PARTITION')
TMUX_PANE_FORMAT = (
    '#{session_name}\t#{window_index}\t#{pane_index}'
    '\t#{pane_pid}\t#{pane_current_command}'
)
GZ_SIM_RE = re.compile(r'(?:^|/)gz\s+sim\b')
RVIZ_RE = re.compile(r'(?:^|/)rviz2?\b')


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    role: str
    start_ticks: int
    cmdline: str
    cwd: str | None = None
    environment: dict = field(default_factory=dict)


def classify_process(cmdline):
    """Return the SO101 stack role for a cmdline, or None when unrelated."""
    if GZ_SIM_RE.search(cmdline) or 'gz-sim' in cmdline:
        return 'gazebo'
    if 'move_group' in cmdline or 'moveit_ros' in cmdline:
        return 'moveit'
    if 'pick_place' in cmdline:
        return 'pick_place'
    if RVIZ_RE.search(cmdline):
        return 'rviz'
    return None


def parse_start_ticks(stat_text):
    """Extract the starttime field (22) from /proc/<pid>/stat text."""
    close = stat_text.rfind(')')
    if close < 0:
        raise ValueError(f'invalid proc stat: {stat_text!r}')
    fields = stat_text[close + 1:].split()
    return int(fields[19])


def parse_ros_nodes(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_tmux_panes(text):
    panes = []
    for line in text.splitlines():
        if not line.strip():
            continue
        session, window_index, pane_index, pane_pid, command = line.split('\t')
        panes.append({
            'session': session,
            'window_index': int(window_index),
            'pane_index': int(pane_index),
            'pane_pid': int(pane_pid),
            'command': command,
        })
    return panes


def default_runner(arguments, timeout=COMMAND_TIMEOUT_SEC):
    """Run one read-only command and return stdout; raise on any failure."""
    return subprocess.run(
        arguments,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    ).stdout


def read_process(proc_dir):
    """Build a ProcessInfo from one /proc directory; None when unrelated."""
    try:
        raw_cmdline = (proc_dir / 'cmdline').read_bytes()
    except OSError:
        return None
    cmdline = ' '.join(
        part
        for part in raw_cmdline.decode('utf-8', 'replace').split('\0')
        if part
    )
    if not cmdline:
        return None
    role = classify_process(cmdline)
    if role is None:
        return None
    try:
        start_ticks = parse_start_ticks((proc_dir / 'stat').read_text())
    except (OSError, ValueError, IndexError):
        start_ticks = 0
    try:
        cwd = os.readlink(proc_dir / 'cwd')
    except OSError:
        cwd = None
    return ProcessInfo(
        pid=int(proc_dir.name),
        role=role,
        start_ticks=start_ticks,
        cmdline=cmdline,
        cwd=cwd,
        environment=read_process_environment(proc_dir),
    )


def read_process_environment(proc_dir):
    """Return only the safe GZ/ROS keys from /proc/<pid>/environ."""
    try:
        raw = (proc_dir / 'environ').read_bytes()
    except OSError:
        return {}
    result = {}
    for pair in raw.decode('utf-8', 'replace').split('\0'):
        name, separator, value = pair.partition('=')
        if separator and name in PROCESS_ENVIRONMENT_KEYS:
            result[name] = value
    return result


def list_processes(proc_root):
    processes = []
    for entry in sorted(Path(proc_root).iterdir(), key=lambda path: path.name):
        if not entry.name.isdigit():
            continue
        info = read_process(entry)
        if info is not None:
            processes.append(info)
    return processes


def _process_payload(info):
    payload = {
        'pid': info.pid,
        'role': info.role,
        'start_ticks': info.start_ticks,
        'cmdline': info.cmdline,
        'cwd': info.cwd,
    }
    if info.environment:
        payload['environment'] = dict(info.environment)
    return payload


def collect_ros_nodes(runner, warnings):
    try:
        return parse_ros_nodes(runner(['ros2', 'node', 'list'], COMMAND_TIMEOUT_SEC))
    except Exception as error:
        warnings.append(f'ros2 node list unavailable: {error}')
        return []


def collect_tmux_panes(runner, warnings):
    try:
        return parse_tmux_panes(
            runner(['tmux', 'list-panes', '-a', '-F', TMUX_PANE_FORMAT],
                   COMMAND_TIMEOUT_SEC)
        )
    except Exception as error:
        warnings.append(f'tmux list-panes unavailable: {error}')
        return []


def collect_windows(backend_factory, warnings):
    """List RViz/Gazebo windows through the shared X11 discovery module."""
    try:
        backend = backend_factory()
        observed = backend.windows()
    except Exception as error:
        warnings.append(f'windows unavailable: {error}')
        return []
    windows = []
    for window in observed:
        role = classify_window(window.title, window.wm_class)
        if role is None:
            continue
        entry = {
            'window_id': f'0x{window.window_id:x}',
            'role': role,
            'title': window.title,
            'wm_class': list(window.wm_class),
        }
        try:
            geometry = backend.geometry(window.window_id)
            entry['geometry'] = {
                'x': geometry.x,
                'y': geometry.y,
                'width': geometry.width,
                'height': geometry.height,
            }
        except Exception as error:
            warnings.append(
                f'geometry unavailable for window 0x{window.window_id:x}: {error}'
            )
            entry['geometry'] = None
        windows.append(entry)
    return windows


def safe_environment(environ):
    return {
        key: environ[key] for key in SAFE_ENVIRONMENT_KEYS if key in environ
    }


def build_inventory(runner, backend_factory, proc_root, environ):
    return {
        'captured_at': datetime.now(timezone.utc).isoformat(),
        'environment': safe_environment(environ),
        'processes': [
            _process_payload(info) for info in list_processes(proc_root)
        ],
        'ros_nodes': [],
        'tmux_panes': [],
        'windows': [],
        'warnings': [],
    }


def _build_parser():
    parser = argparse.ArgumentParser(
        description='Read-only inventory of the SO101 simulation stack.'
    )
    parser.add_argument(
        '--json',
        help='also write the inventory to this path; must not exist yet',
    )
    return parser


def main(argv=None, runner=None, backend_factory=None, proc_root=Path('/proc'),
         environ=None):
    arguments = _build_parser().parse_args(argv)
    if runner is None:
        runner = default_runner
    if backend_factory is None:
        backend_factory = X11EwmhBackend
    if environ is None:
        environ = os.environ
    output = Path(arguments.json) if arguments.json else None
    if output is not None and output.exists():
        print(f'error: refusing to overwrite existing file: {output}',
              file=sys.stderr)
        return 1
    inventory = build_inventory(runner, backend_factory, proc_root, environ)
    warnings = inventory['warnings']
    inventory['ros_nodes'] = collect_ros_nodes(runner, warnings)
    inventory['tmux_panes'] = collect_tmux_panes(runner, warnings)
    inventory['windows'] = collect_windows(backend_factory, warnings)
    text = json.dumps(inventory, indent=2) + '\n'
    if output is not None:
        output.write_text(text)
    print(text, end='')
    return 0


if __name__ == '__main__':
    sys.exit(main())
