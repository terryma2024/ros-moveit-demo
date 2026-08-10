#!/usr/bin/env python3
"""Supervised recorder for the unique Gazebo client window on ai-station.

``start`` resolves the unique Gazebo window through the shared X11 module,
launches a detached supervisor that owns the ffmpeg child, and returns once
the state file reports ``phase=recording``. ``status`` cross-checks the
state file, the supervisor PID identity (/proc start ticks and cmdline),
ffmpeg liveness and output growth. ``stop`` signals only a supervisor whose
identity still matches the recorded one, then waits for the finalized
metadata. Only the client region is recorded: never the full display and
never audio. Evidence files are never overwritten.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from ai_station_x11 import (  # noqa: E402
    Rect,
    WindowInfo,
    X11EwmhBackend,
    parse_xwininfo_geometry,
    select_unique_window,
)
from so101_stack_inventory import parse_start_ticks  # noqa: E402


SCRIPT_PATH = Path(__file__).resolve()
STATE_VERSION = 1
DEFAULT_FPS = 30
SUPERVISOR_MARKER = '_supervise'
COMMAND_TIMEOUT_SEC = 10.0
PROBE_TIMEOUT_SEC = 20.0
START_TIMEOUT_SEC = 30.0
STOP_TIMEOUT_SEC = 60.0
FINALIZE_GRACE_SEC = 30.0
POLL_INTERVAL_SEC = 0.1


class ProcReader:
    """Minimal /proc reader used to pin supervisor and ffmpeg identity."""

    def __init__(self, proc_root='/proc'):
        self.proc_root = Path(proc_root)

    def start_ticks(self, pid):
        return parse_start_ticks(
            (self.proc_root / str(pid) / 'stat').read_text()
        )

    def cmdline(self, pid):
        raw = (self.proc_root / str(pid) / 'cmdline').read_bytes()
        return ' '.join(
            part
            for part in raw.decode('utf-8', 'replace').split('\0')
            if part
        )

    def is_alive(self, pid):
        return (self.proc_root / str(pid)).is_dir()


def default_runner(arguments, env=None, timeout=COMMAND_TIMEOUT_SEC):
    """Run one read-only command and return stdout; raise on any failure."""
    return subprocess.run(
        arguments,
        check=True,
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    ).stdout


def resolve_gazebo_client(backend_factory=X11EwmhBackend, runner=None):
    """Return (WindowInfo, client Rect) of the one Gazebo window.

    Reuses the shared X11 module for window classification and geometry
    parsing so the identification rules never drift between tools.
    """
    if runner is None:
        runner = default_runner
    backend = backend_factory()
    window = select_unique_window(backend.windows(), 'gazebo')
    text = runner(
        ['xwininfo', '-id', hex(window.window_id)],
        env=backend.environment,
    )
    return window, parse_xwininfo_geometry(text)


def even_geometry(rect):
    """Crop odd dimensions; H.264 yuv420p requires even width/height."""
    width = rect.width - rect.width % 2
    height = rect.height - rect.height % 2
    if width <= 0 or height <= 0:
        raise ValueError(
            f'Gazebo client region too small to record: {rect!r}'
        )
    return Rect(rect.x, rect.y, width, height)


def build_ffmpeg_command(display, rect, fps, encoder, output):
    """Record only the client region: no full display, no audio, no -y."""
    command = [
        'ffmpeg', '-nostdin',
        '-f', 'x11grab',
        '-framerate', str(fps),
        '-video_size', f'{rect.width}x{rect.height}',
        '-i', f'{display}+{rect.x},{rect.y}',
        '-an',
        '-c:v', encoder,
    ]
    if encoder == 'libx264':
        # Low-overhead preset so software encoding keeps up with live capture.
        command += ['-preset', 'veryfast']
    command += [
        '-pix_fmt', 'yuv420p',
        str(output),
    ]
    return command


def probe_encoder(encoder, timeout=PROBE_TIMEOUT_SEC):
    """Encode one lavfi frame to the null muxer; return (ok, reason)."""
    command = [
        'ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
        '-f', 'lavfi', '-i', 'testsrc=size=64x64:rate=1:duration=1',
        '-frames:v', '1',
        '-an', '-c:v', encoder, '-pix_fmt', 'yuv420p',
        '-f', 'null', '-',
    ]
    try:
        subprocess.run(
            command, check=True, capture_output=True, text=True,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or '').strip().splitlines()
        reason = detail[-1] if detail else str(error)
        return False, f'{encoder} probe failed: {reason}'
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, f'{encoder} probe failed: {error}'
    return True, None


def select_encoder(preference, prober=probe_encoder):
    """Return (codec, fallback_reason); auto prefers a proven NVENC."""
    if preference != 'auto':
        return preference, None
    ok, reason = prober('h264_nvenc')
    if ok:
        return 'h264_nvenc', None
    return 'libx264', reason


def probe_video(output, timeout=COMMAND_TIMEOUT_SEC):
    """Read duration, resolution and average frame rate with ffprobe."""
    text = subprocess.run(
        [
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,avg_frame_rate',
            '-show_entries', 'format=duration',
            '-of', 'json', str(output),
        ],
        check=True, capture_output=True, text=True, timeout=timeout,
    ).stdout
    payload = json.loads(text)
    stream = payload['streams'][0]
    numerator, _, denominator = stream['avg_frame_rate'].partition('/')
    rate = None
    if float(denominator or 0):
        rate = float(numerator) / float(denominator)
    return {
        'duration_sec': float(payload['format']['duration']),
        'resolution': f"{stream['width']}x{stream['height']}",
        'avg_frame_rate': rate,
    }


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def atomic_write_json(path, payload):
    """Write JSON through a sibling temp file so readers see all or nothing."""
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(payload, indent=2) + '\n')
    os.replace(temporary, path)


def load_state(state_path):
    return json.loads(Path(state_path).read_text())


def verify_supervisor_identity(state, proc):
    """Pin the recorded PID to its start ticks and supervisor cmdline."""
    pid = state['supervisor_pid']
    try:
        ticks = proc.start_ticks(pid)
        cmdline = proc.cmdline(pid)
    except (OSError, ValueError, IndexError) as error:
        raise RuntimeError(
            f'PID identity mismatch: supervisor pid {pid} is not readable '
            f'({error}); the recorded supervisor is gone'
        )
    if ticks != state['supervisor_start_ticks']:
        raise RuntimeError(
            f'PID identity mismatch: pid {pid} start ticks {ticks} != '
            f"recorded {state['supervisor_start_ticks']}; the PID was reused"
        )
    if SUPERVISOR_MARKER not in cmdline or SCRIPT_PATH.name not in cmdline:
        raise RuntimeError(
            f'PID identity mismatch: pid {pid} cmdline {cmdline!r} is not '
            'the recorder supervisor; the PID was reused'
        )


def start_recorder(output, state_path, encoder='auto', fps=DEFAULT_FPS,
                   resolver=None, prober=probe_encoder, popen=None,
                   environ=None, monotonic=time.monotonic, sleep=time.sleep,
                   timeout_sec=START_TIMEOUT_SEC):
    """Launch the detached supervisor and wait for phase=recording."""
    output = Path(output)
    state_path = Path(state_path)
    if output.exists():
        raise RuntimeError(f'refusing to overwrite existing output: {output}')
    if state_path.exists():
        raise RuntimeError(f'refusing to overwrite existing state: {state_path}')
    if resolver is None:
        resolver = resolve_gazebo_client
    if popen is None:
        popen = subprocess.Popen
    if environ is None:
        environ = os.environ
    display = environ.get('DISPLAY')
    if not display:
        raise RuntimeError('DISPLAY is not set; source ~/gui-env.zsh first')
    window, client = resolver()
    geometry = even_geometry(client)
    codec, fallback_reason = select_encoder(encoder, prober)
    log_path = state_path.with_suffix('.ffmpeg.log')
    argv = [
        sys.executable, str(SCRIPT_PATH), SUPERVISOR_MARKER,
        '--state', str(state_path),
        '--output', str(output),
        '--display', display,
        '--geometry',
        f'{geometry.x},{geometry.y},{geometry.width},{geometry.height}',
        '--window-id', hex(window.window_id),
        '--encoder', codec,
        '--fps', str(fps),
        '--log', str(log_path),
    ]
    if fallback_reason:
        argv += ['--encoder-fallback-reason', fallback_reason]
    popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    deadline = monotonic() + timeout_sec
    while monotonic() < deadline:
        if state_path.exists():
            state = load_state(state_path)
            if state.get('phase') == 'recording':
                return state
            if state.get('phase') == 'stopped':
                raise RuntimeError(
                    'recorder stopped before recording became active: '
                    f"ffmpeg_exit_code={state.get('ffmpeg_exit_code')}; "
                    f'see {log_path}'
                )
        sleep(POLL_INTERVAL_SEC)
    raise RuntimeError(
        f'timed out waiting for recorder state {state_path} to reach '
        'phase=recording'
    )


def status_recorder(state_path, proc=None, sleep=time.sleep,
                    growth_interval_sec=0.5):
    """Cross-check state, supervisor identity, ffmpeg and output growth."""
    if proc is None:
        proc = ProcReader()
    state = load_state(state_path)
    report = {
        'phase': state['phase'],
        'output': state['output'],
        'supervisor_alive': False,
        'ffmpeg_alive': False,
        'output_bytes': None,
        'output_growing': False,
    }
    output = Path(state['output'])
    if state['phase'] == 'stopped':
        if output.exists():
            report['output_bytes'] = output.stat().st_size
        return report
    try:
        verify_supervisor_identity(state, proc)
        report['supervisor_alive'] = True
    except RuntimeError as error:
        report['supervisor_error'] = str(error)
    ffmpeg_pid = state.get('ffmpeg_pid')
    if ffmpeg_pid is not None:
        report['ffmpeg_alive'] = proc.is_alive(ffmpeg_pid)
    if not output.exists():
        return report
    before = output.stat().st_size
    sleep(growth_interval_sec)
    after = output.stat().st_size
    report['output_bytes'] = after
    report['output_growing'] = after > before
    return report


def stop_recorder(state_path, proc=None, send_signal=None,
                  monotonic=time.monotonic, sleep=time.sleep,
                  timeout_sec=STOP_TIMEOUT_SEC):
    """Signal only a verified supervisor; wait for atomic final metadata."""
    if proc is None:
        proc = ProcReader()
    if send_signal is None:
        send_signal = os.kill
    state = load_state(state_path)
    if state['phase'] == 'stopped':
        return state
    verify_supervisor_identity(state, proc)
    send_signal(state['supervisor_pid'], signal.SIGTERM)
    deadline = monotonic() + timeout_sec
    while monotonic() < deadline:
        updated = load_state(state_path)
        if updated['phase'] == 'stopped':
            return updated
        sleep(POLL_INTERVAL_SEC)
    raise RuntimeError(
        f'timed out waiting for finalized recorder state {state_path}'
    )


def parse_geometry(text):
    values = tuple(int(value) for value in text.split(','))
    if len(values) != 4:
        raise ValueError(f'invalid geometry: {text!r}')
    rect = Rect(*values)
    if rect.width <= 0 or rect.height <= 0:
        raise ValueError(f'invalid geometry: {text!r}')
    return rect


def run_supervisor(state_path, output, display, geometry, window_id, encoder,
                   fps, log_path, fallback_reason=None, ffmpeg_command=None,
                   popen_factory=subprocess.Popen, ffprobe=probe_video,
                   proc=None, terminate_event=None,
                   monotonic=time.monotonic, sleep=time.sleep,
                   finalize_grace_sec=FINALIZE_GRACE_SEC):
    """Own ffmpeg; on SIGTERM forward SIGINT and finalize metadata atomically.

    The MKV and the ffmpeg log are always preserved; an abnormal ffmpeg
    exit is recorded honestly instead of being rewritten as success.
    """
    if proc is None:
        proc = ProcReader()
    if terminate_event is None:
        terminate_event = threading.Event()

        def handle_sigterm(signum, frame):
            terminate_event.set()

        signal.signal(signal.SIGTERM, handle_sigterm)
    output = Path(output)
    state_path = Path(state_path)
    if ffmpeg_command is None:
        ffmpeg_command = build_ffmpeg_command(
            display, geometry, fps, encoder, output,
        )
    state = {
        'version': STATE_VERSION,
        'phase': 'launching',
        'output': str(output),
        'supervisor_pid': os.getpid(),
        'supervisor_start_ticks': proc.start_ticks(os.getpid()),
        'window_id': window_id,
        'geometry': {
            'x': geometry.x,
            'y': geometry.y,
            'width': geometry.width,
            'height': geometry.height,
        },
        'display': display,
        'codec': encoder,
        'encoder_fallback_reason': fallback_reason,
        'fps': fps,
        'started_at': utc_now(),
        'ended_at': None,
        'ffmpeg_log': str(log_path),
        'ffmpeg_command': list(ffmpeg_command),
        'ffmpeg_pid': None,
        'ffmpeg_exit_code': None,
        'duration_sec': None,
        'resolution': None,
        'avg_frame_rate': None,
    }
    atomic_write_json(state_path, state)
    with open(log_path, 'ab') as log_file:
        log_file.write(
            ('recorder command: ' + ' '.join(ffmpeg_command) + '\n').encode()
        )
        log_file.flush()
        process = popen_factory(
            ffmpeg_command,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        state['ffmpeg_pid'] = process.pid
        state['phase'] = 'recording'
        atomic_write_json(state_path, state)
        signaled_at = None
        while process.poll() is None:
            if terminate_event.is_set() and signaled_at is None:
                process.send_signal(signal.SIGINT)
                signaled_at = monotonic()
            if (
                signaled_at is not None
                and monotonic() - signaled_at > finalize_grace_sec
            ):
                state['finalize_warning'] = (
                    'ffmpeg ignored SIGINT; killed after grace period'
                )
                process.kill()
                break
            sleep(0.05)
        state['ffmpeg_exit_code'] = process.wait()
    state['ended_at'] = utc_now()
    try:
        probe = ffprobe(output)
        state['duration_sec'] = probe['duration_sec']
        state['resolution'] = probe['resolution']
        state['avg_frame_rate'] = probe['avg_frame_rate']
    except Exception as error:
        state['ffprobe_error'] = str(error)
    state['phase'] = 'stopped'
    atomic_write_json(state_path, state)
    return state


def _build_parser():
    parser = argparse.ArgumentParser(
        description='Record the unique Gazebo client window (MKV/H.264).',
    )
    subparsers = parser.add_subparsers(
        dest='command', required=True, metavar='{start,status,stop}',
    )
    start = subparsers.add_parser(
        'start', help='start recording the Gazebo client region',
    )
    start.add_argument('--output', required=True,
                       help='MKV output path; must not exist yet')
    start.add_argument('--state', required=True,
                       help='recorder state JSON path; must not exist yet')
    start.add_argument('--encoder', default='auto',
                       help='auto, h264_nvenc or libx264 (default: auto)')
    start.add_argument('--fps', type=int, default=DEFAULT_FPS,
                       help=f'fixed capture rate (default: {DEFAULT_FPS})')
    status = subparsers.add_parser(
        'status', help='cross-check state, processes and output growth',
    )
    status.add_argument('--state', required=True)
    stop = subparsers.add_parser(
        'stop', help='stop the verified supervisor and finalize metadata',
    )
    stop.add_argument('--state', required=True)
    # Internal supervisor mode: intentionally not listed in --help.
    supervise = subparsers.add_parser(SUPERVISOR_MARKER)
    supervise.add_argument('--state', required=True)
    supervise.add_argument('--output', required=True)
    supervise.add_argument('--display', required=True)
    supervise.add_argument('--geometry', required=True)
    supervise.add_argument('--window-id', required=True)
    supervise.add_argument('--encoder', required=True)
    supervise.add_argument('--fps', type=int, required=True)
    supervise.add_argument('--log', required=True)
    supervise.add_argument('--encoder-fallback-reason', default=None)
    return parser


def main(argv=None):
    arguments = _build_parser().parse_args(argv)
    try:
        if arguments.command == 'start':
            payload = start_recorder(
                arguments.output, arguments.state,
                encoder=arguments.encoder, fps=arguments.fps,
            )
        elif arguments.command == 'status':
            payload = status_recorder(arguments.state)
        elif arguments.command == 'stop':
            payload = stop_recorder(arguments.state)
        else:
            payload = run_supervisor(
                state_path=arguments.state,
                output=arguments.output,
                display=arguments.display,
                geometry=parse_geometry(arguments.geometry),
                window_id=arguments.window_id,
                encoder=arguments.encoder,
                fps=arguments.fps,
                log_path=arguments.log,
                fallback_reason=arguments.encoder_fallback_reason,
            )
    except (RuntimeError, OSError, ValueError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 1
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
