import importlib.util
import json
import subprocess
import sys
import threading
import textwrap
import time
from pathlib import Path
import sys

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / 'scripts'
    / 'gazebo_window_recorder.py'
)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(SCRIPT_PATH.parent))
SPEC = importlib.util.spec_from_file_location('gazebo_window_recorder', SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

Rect = MODULE.Rect
WindowInfo = MODULE.WindowInfo

GAZEBO = WindowInfo(0x32, 'Gazebo Sim', ('gz-sim-gui', 'Gazebo GUI'))
CLIENT = Rect(66, 32, 1920, 1080)
SUPERVISOR_CMDLINE = (
    f'python3 {SCRIPT_PATH} {MODULE.SUPERVISOR_MARKER} --state state.json'
)


class FakeProc:
    def __init__(self):
        self.ticks = {}
        self.cmdlines = {}
        self.alive = set()

    def set_start_ticks(self, pid, ticks):
        self.ticks[pid] = ticks

    def set_cmdline(self, pid, cmdline):
        self.cmdlines[pid] = cmdline

    def start_ticks(self, pid):
        if pid not in self.ticks:
            raise FileNotFoundError(f'no such process: {pid}')
        return self.ticks[pid]

    def cmdline(self, pid):
        if pid not in self.cmdlines:
            raise FileNotFoundError(f'no such process: {pid}')
        return self.cmdlines[pid]

    def is_alive(self, pid):
        return pid in self.alive


def matching_proc():
    proc = FakeProc()
    proc.set_start_ticks(42, 100)
    proc.set_cmdline(42, SUPERVISOR_CMDLINE)
    proc.alive.add(4242)
    return proc


def recorder_state(directory, **overrides):
    state = {
        'version': MODULE.STATE_VERSION,
        'phase': 'recording',
        'output': str(directory / 'run.mkv'),
        'supervisor_pid': 42,
        'supervisor_start_ticks': 100,
        'window_id': '0x32',
        'geometry': {'x': 66, 'y': 32, 'width': 1920, 'height': 1080},
        'display': ':1',
        'codec': 'libx264',
        'encoder_fallback_reason': None,
        'fps': 30,
        'started_at': '2026-07-29T00:00:00+00:00',
        'ended_at': None,
        'ffmpeg_log': str(directory / 'run.ffmpeg.log'),
        'ffmpeg_pid': 4242,
        'ffmpeg_exit_code': None,
        'duration_sec': None,
        'resolution': None,
        'avg_frame_rate': None,
    }
    state.update(overrides)
    path = directory / 'state.json'
    path.write_text(json.dumps(state))
    return path


def test_build_ffmpeg_command_records_only_client_region():
    command = MODULE.build_ffmpeg_command(
        display=':1', rect=Rect(66, 32, 1920, 1080), fps=30,
        encoder='libx264', output=Path('/tmp/run.mkv'),
    )
    assert command[:8] == [
        'ffmpeg', '-nostdin', '-f', 'x11grab', '-framerate', '30',
        '-video_size', '1920x1080',
    ]
    assert ':1+66,32' in command
    assert '-an' in command


def test_build_ffmpeg_command_forces_yuv420p_and_never_overwrites():
    command = MODULE.build_ffmpeg_command(
        display=':1', rect=CLIENT, fps=30,
        encoder='libx264', output=Path('/tmp/run.mkv'),
    )
    assert command[command.index('-pix_fmt') + 1] == 'yuv420p'
    assert '-y' not in command
    assert command[-1] == '/tmp/run.mkv'


def test_build_ffmpeg_command_uses_low_overhead_preset_for_libx264():
    command = MODULE.build_ffmpeg_command(
        display=':1', rect=Rect(66, 32, 1920, 1080), fps=30,
        encoder='libx264', output=Path('/tmp/run.mkv'),
    )
    assert command[command.index('-preset') + 1] == 'veryfast'


def test_build_ffmpeg_command_omits_libx264_preset_for_nvenc():
    command = MODULE.build_ffmpeg_command(
        display=':1', rect=Rect(66, 32, 1920, 1080), fps=30,
        encoder='h264_nvenc', output=Path('/tmp/run.mkv'),
    )
    assert '-preset' not in command


def test_even_geometry_crops_odd_dimensions_for_h264():
    assert MODULE.even_geometry(Rect(66, 32, 1919, 1079)) == Rect(66, 32, 1918, 1078)
    assert MODULE.even_geometry(CLIENT) == CLIENT
    with pytest.raises(ValueError, match='too small'):
        MODULE.even_geometry(Rect(0, 0, 1, 1080))


def test_select_encoder_prefers_nvenc_when_the_probe_succeeds():
    codec, reason = MODULE.select_encoder('auto', prober=lambda encoder: (True, None))
    assert codec == 'h264_nvenc'
    assert reason is None


def test_select_encoder_falls_back_to_libx264_and_records_reason():
    def failing_prober(encoder):
        assert encoder == 'h264_nvenc'
        return False, 'h264_nvenc probe failed: no NVENC capable device found'

    codec, reason = MODULE.select_encoder('auto', prober=failing_prober)
    assert codec == 'libx264'
    assert 'no NVENC capable device' in reason


def test_select_encoder_honors_an_explicit_choice_without_probing():
    def unexpected_probe(encoder):
        raise AssertionError('probe must not run for explicit encoders')

    codec, reason = MODULE.select_encoder('libx264', prober=unexpected_probe)
    assert codec == 'libx264'
    assert reason is None


def test_probe_encoder_accepts_real_libx264_with_lavfi_input():
    ok, reason = MODULE.probe_encoder('libx264')
    assert ok is True
    assert reason is None


def test_probe_encoder_rejects_an_unknown_encoder_with_reason():
    ok, reason = MODULE.probe_encoder('definitely_not_an_encoder')
    assert ok is False
    assert reason


def test_start_rejects_an_existing_output(tmp_path):
    output = tmp_path / 'run.mkv'
    output.write_bytes(b'evidence')
    with pytest.raises(RuntimeError, match='refusing to overwrite existing output'):
        MODULE.start_recorder(
            output, tmp_path / 'state.json',
            resolver=lambda: (GAZEBO, CLIENT),
            popen=lambda *args, **kwargs: None,
            environ={'DISPLAY': ':1'},
        )
    assert output.read_bytes() == b'evidence'


def test_start_rejects_an_existing_state(tmp_path):
    state_path = tmp_path / 'state.json'
    state_path.write_text('{}')
    with pytest.raises(RuntimeError, match='refusing to overwrite existing state'):
        MODULE.start_recorder(
            tmp_path / 'run.mkv', state_path,
            resolver=lambda: (GAZEBO, CLIENT),
            popen=lambda *args, **kwargs: None,
            environ={'DISPLAY': ':1'},
        )
    assert state_path.read_text() == '{}'


def test_start_requires_display_from_the_environment(tmp_path):
    with pytest.raises(RuntimeError, match='DISPLAY is not set'):
        MODULE.start_recorder(
            tmp_path / 'run.mkv', tmp_path / 'state.json',
            resolver=lambda: (GAZEBO, CLIENT),
            popen=lambda *args, **kwargs: None,
            environ={},
        )


def test_start_launches_detached_supervisor_and_waits_for_recording(tmp_path):
    output = tmp_path / 'run.mkv'
    state_path = tmp_path / 'state.json'
    launched = []

    class FakeProcess:
        pid = 777

    def fake_popen(argv, **kwargs):
        launched.append((list(argv), kwargs))
        MODULE.atomic_write_json(state_path, {'phase': 'recording'})
        return FakeProcess()

    probed = []
    state = MODULE.start_recorder(
        output, state_path,
        resolver=lambda: (GAZEBO, Rect(66, 32, 1919, 1079)),
        prober=lambda encoder: probed.append(encoder) or (True, None),
        popen=fake_popen,
        environ={'DISPLAY': ':1'},
        sleep=lambda _: None,
    )
    assert state['phase'] == 'recording'
    argv, kwargs = launched[0]
    assert argv[0] == sys.executable
    assert str(SCRIPT_PATH) in argv[1]
    assert MODULE.SUPERVISOR_MARKER in argv
    assert kwargs.get('start_new_session') is True
    assert probed == ['h264_nvenc']
    geometry = argv[argv.index('--geometry') + 1]
    assert geometry == '66,32,1918,1078'
    assert argv[argv.index('--display') + 1] == ':1'


def test_stop_rejects_reused_supervisor_pid(tmp_path):
    state_path = recorder_state(
        tmp_path, supervisor_pid=42, supervisor_start_ticks=100,
    )
    fake_proc = FakeProc()
    fake_proc.set_start_ticks(42, 101)
    fake_proc.set_cmdline(42, SUPERVISOR_CMDLINE)
    signals = []
    with pytest.raises(RuntimeError, match='PID identity mismatch'):
        MODULE.stop_recorder(
            state_path, proc=fake_proc,
            send_signal=lambda pid, sig: signals.append((pid, sig)),
            sleep=lambda _: None,
        )
    assert signals == []


def test_stop_rejects_a_recycled_pid_with_a_foreign_cmdline(tmp_path):
    state_path = recorder_state(tmp_path)
    fake_proc = FakeProc()
    fake_proc.set_start_ticks(42, 100)
    fake_proc.set_cmdline(42, '/usr/bin/python3 unrelated.py')
    signals = []
    with pytest.raises(RuntimeError, match='PID identity mismatch'):
        MODULE.stop_recorder(
            state_path, proc=fake_proc,
            send_signal=lambda pid, sig: signals.append((pid, sig)),
            sleep=lambda _: None,
        )
    assert signals == []


def test_stop_signals_matching_supervisor_and_returns_final_metadata(tmp_path):
    state_path = recorder_state(tmp_path)
    signals = []

    def finalize(pid, sig):
        signals.append((pid, sig))
        final = json.loads(state_path.read_text())
        final.update({
            'phase': 'stopped',
            'ffmpeg_exit_code': 0,
            'duration_sec': 1.5,
            'resolution': '1920x1080',
            'avg_frame_rate': 30.0,
            'ended_at': '2026-07-29T00:00:02+00:00',
        })
        MODULE.atomic_write_json(state_path, final)

    state = MODULE.stop_recorder(
        state_path, proc=matching_proc(), send_signal=finalize,
        sleep=lambda _: None,
    )
    assert signals == [(42, MODULE.signal.SIGTERM)]
    assert state['phase'] == 'stopped'
    assert state['ffmpeg_exit_code'] == 0
    assert state['duration_sec'] == 1.5
    assert state['resolution'] == '1920x1080'
    assert state['avg_frame_rate'] == 30.0
    assert state['ended_at'] is not None


def test_second_stop_is_idempotent(tmp_path):
    state_path = recorder_state(
        tmp_path, phase='stopped', ffmpeg_exit_code=0, duration_sec=2.0,
    )
    signals = []
    state = MODULE.stop_recorder(
        state_path, proc=FakeProc(),
        send_signal=lambda pid, sig: signals.append((pid, sig)),
        sleep=lambda _: None,
    )
    assert state['phase'] == 'stopped'
    assert state['duration_sec'] == 2.0
    assert signals == []


def test_status_reports_dead_supervisor_without_raising(tmp_path):
    state_path = recorder_state(tmp_path)
    report = MODULE.status_recorder(
        state_path, proc=FakeProc(), sleep=lambda _: None,
    )
    assert report['phase'] == 'recording'
    assert report['supervisor_alive'] is False
    assert report['ffmpeg_alive'] is False


def test_status_checks_identity_ffmpeg_liveness_and_output_growth(tmp_path):
    output = tmp_path / 'run.mkv'
    output.write_bytes(b'x')
    state_path = recorder_state(tmp_path)

    def grow(_seconds):
        output.write_bytes(b'x' * 2048)

    report = MODULE.status_recorder(
        state_path, proc=matching_proc(), sleep=grow,
    )
    assert report['supervisor_alive'] is True
    assert report['ffmpeg_alive'] is True
    assert report['output_bytes'] == 2048
    assert report['output_growing'] is True


def test_status_on_a_stopped_recording_needs_no_process_checks(tmp_path):
    output = tmp_path / 'run.mkv'
    output.write_bytes(b'x' * 10)
    state_path = recorder_state(
        tmp_path, phase='stopped', ffmpeg_exit_code=0, duration_sec=2.0,
    )
    report = MODULE.status_recorder(
        state_path, proc=FakeProc(), sleep=lambda _: None,
    )
    assert report['phase'] == 'stopped'
    assert report['supervisor_alive'] is False
    assert report['ffmpeg_alive'] is False
    assert report['output_growing'] is False
    assert report['output_bytes'] == 10


SYNTHETIC_FFMPEG = textwrap.dedent(
    '''
    import signal
    import sys
    import time

    output = sys.argv[1]
    stopped = False

    def handle_sigint(signum, frame):
        global stopped
        stopped = True

    signal.signal(signal.SIGINT, handle_sigint)
    with open(output, 'wb') as stream:
        while not stopped:
            stream.write(b'\\0' * 1024)
            stream.flush()
            time.sleep(0.01)
    sys.exit(0)
    '''
)


def wait_for_phase(state_path, phase, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if state_path.exists():
            state = json.loads(state_path.read_text())
            if state.get('phase') == phase:
                return state
        time.sleep(0.02)
    raise AssertionError(f'state never reached phase {phase!r}')


def run_supervisor_in_thread(state_path, output, log_path, event, ffprobe,
                             ffmpeg_command):
    result = {}

    def target():
        result['state'] = MODULE.run_supervisor(
            state_path=state_path,
            output=output,
            display=':1',
            geometry=Rect(0, 0, 64, 64),
            window_id='0x32',
            encoder='libx264',
            fps=30,
            log_path=log_path,
            ffmpeg_command=ffmpeg_command,
            ffprobe=ffprobe,
            terminate_event=event,
        )

    thread = threading.Thread(target=target)
    thread.start()
    return thread, result


def test_supervisor_forwards_sigint_and_writes_final_metadata(tmp_path):
    state_path = tmp_path / 'state.json'
    output = tmp_path / 'run.mkv'
    log_path = tmp_path / 'run.ffmpeg.log'
    event = threading.Event()
    thread, result = run_supervisor_in_thread(
        state_path, output, log_path, event,
        ffprobe=lambda path: {
            'duration_sec': 1.5,
            'resolution': '64x64',
            'avg_frame_rate': 30.0,
        },
        ffmpeg_command=[sys.executable, '-c', SYNTHETIC_FFMPEG, str(output)],
    )
    recording = wait_for_phase(state_path, 'recording')
    assert recording['supervisor_pid'] > 0
    assert recording['supervisor_start_ticks'] > 0
    assert recording['display'] == ':1'
    assert recording['codec'] == 'libx264'
    assert recording['fps'] == 30
    event.set()
    thread.join(timeout=30.0)
    assert not thread.is_alive()
    final = result['state']
    assert final['phase'] == 'stopped'
    assert final['ffmpeg_exit_code'] == 0
    assert final['duration_sec'] == 1.5
    assert final['resolution'] == '64x64'
    assert final['avg_frame_rate'] == 30.0
    assert final['ended_at'] is not None
    on_disk = json.loads(state_path.read_text())
    assert on_disk == final
    assert output.stat().st_size > 0


def test_supervisor_records_ffmpeg_failure_without_faking_success(tmp_path):
    state_path = tmp_path / 'state.json'
    output = tmp_path / 'run.mkv'
    log_path = tmp_path / 'run.ffmpeg.log'
    thread, result = run_supervisor_in_thread(
        state_path, output, log_path, threading.Event(),
        ffprobe=lambda path: (_ for _ in ()).throw(
            RuntimeError('ffprobe cannot read the file')
        ),
        ffmpeg_command=[
            sys.executable, '-c',
            'import sys; open(sys.argv[1], "wb").write(b"x"); sys.exit(3)',
            str(output),
        ],
    )
    thread.join(timeout=30.0)
    assert not thread.is_alive()
    final = result['state']
    assert final['phase'] == 'stopped'
    assert final['ffmpeg_exit_code'] == 3
    assert final['duration_sec'] is None
    assert final['resolution'] is None
    assert 'ffprobe_error' in final
    assert output.exists()
    assert log_path.exists()


def test_help_lists_the_three_user_subcommands(capsys):
    with pytest.raises(SystemExit) as excinfo:
        MODULE.main(['--help'])
    assert excinfo.value.code == 0
    help_text = capsys.readouterr().out
    for name in ('start', 'status', 'stop'):
        assert name in help_text
