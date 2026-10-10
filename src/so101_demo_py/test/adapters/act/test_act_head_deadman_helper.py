"""The heartbeat helper: a separate process tied to the runtime (design section 1.4, review 3 issue 1)."""

import os
import signal
import socket
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from so101_demo.adapters.act.head_deadman_client import DeadmanHelper


class FakeController:
    """Stands in for the controller's dead-man socket: records every byte's arrival time."""

    def __init__(self, directory, activation_id=1):
        self.path = Path(directory) / f'neck-{activation_id}.sock'
        self.beats, self.peer, self.eof = [], None, threading.Event()
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(str(self.path))
        self._server.listen(2)
        self.connected = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        connection, _ = self._server.accept()
        credentials = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        import struct
        self.peer = struct.unpack('3i', credentials)
        self.connected.set()
        while True:
            data = connection.recv(64)
            if not data:
                self.eof.set()
                return
            now = time.monotonic()
            self.beats.extend([now] * len(data))

    def gaps(self, since=0.0):
        beats = [beat for beat in self.beats if beat >= since]
        return [b - a for a, b in zip(beats, beats[1:])]

    def close(self):
        self._server.close()


def _short_directory():
    """AF_UNIX paths are short: SO101_IPC_SOCKET_BASE is the gate's short private base."""
    import tempfile
    base = os.environ.get('SO101_IPC_SOCKET_BASE') or None
    path = Path(tempfile.mkdtemp(prefix='dm', dir=base if base and len(base) < 60 else '/tmp'))
    path.chmod(0o700)
    return path


@pytest.fixture
def directory():
    path = _short_directory()
    yield path
    import shutil
    shutil.rmtree(path, ignore_errors=True)


def make(directory, **keywords):
    keywords.setdefault('connect_timeout_s', 5.)
    return DeadmanHelper(directory=directory, activation_id=1, **keywords)


def test_the_helper_connects_when_the_socket_appears_and_the_controller_sees_the_helpers_pid(directory):
    helper = make(directory)
    pid = helper.start()
    time.sleep(.2)  # the helper starts before the controller creates its socket
    controller = FakeController(directory)
    try:
        assert helper.wait_connected(5.) is True
        assert controller.connected.wait(2.)
        assert controller.peer[0] == pid == helper.pid and controller.peer[1] == os.geteuid()
        assert helper.status == 'CONNECTED'
    finally:
        helper.kill()
        controller.close()


def test_heartbeats_arrive_every_20ms_with_no_gap_over_40ms_while_ticks_flow(directory):
    controller = FakeController(directory)
    helper = make(directory)
    helper.start()
    try:
        assert helper.wait_connected(5.)
        helper.start_ticker(period_s=.02)
        time.sleep(.3)
        begin = time.monotonic()
        time.sleep(1.5)
        gaps = controller.gaps(begin)
        assert len(gaps) >= 60, len(gaps)
        assert max(gaps) < .045, max(gaps)
        assert .015 < sum(gaps) / len(gaps) < .028
    finally:
        helper.kill()
        controller.close()


def test_without_ticks_for_150ms_the_heartbeat_stops_and_it_resumes_with_the_ticks(directory):
    controller = FakeController(directory)
    helper = make(directory)
    helper.start()
    try:
        assert helper.wait_connected(5.)
        ticker = helper.start_ticker(period_s=.02)
        time.sleep(.3)
        ticker.pause()
        paused_at = time.monotonic()
        time.sleep(.6)
        last = max(beat for beat in controller.beats if beat < paused_at + .6)
        # the last heartbeat is at most the liveness bound plus one period after the last tick
        assert last - paused_at < .15 + .03, last - paused_at
        time.sleep(.05)
        count = len(controller.beats)
        time.sleep(.2)
        assert len(controller.beats) == count, 'no heartbeat while the runtime is silent'
        ticker.resume()
        time.sleep(.3)
        assert len(controller.beats) > count
    finally:
        helper.kill()
        controller.close()


def test_a_planned_close_closes_the_socket_and_the_helper_exits_zero(directory):
    controller = FakeController(directory)
    helper = make(directory)
    helper.start()
    try:
        assert helper.wait_connected(5.)
        assert helper.close_planned(timeout_s=2.) is True
        assert controller.eof.wait(1.)
        assert helper.returncode == 0 and helper.status == 'CLOSED'
    finally:
        helper.kill()
        controller.close()


def test_closing_the_liveness_pipe_ends_the_helper_and_closes_the_socket(directory):
    controller = FakeController(directory)
    helper = make(directory)
    helper.start()
    try:
        assert helper.wait_connected(5.)
        helper.drop_liveness_pipe()
        assert controller.eof.wait(2.)
        assert helper.wait_exit(2.) is not None
    finally:
        helper.kill()
        controller.close()


def test_a_helper_with_the_wrong_parent_pid_exits_before_it_connects(directory):
    controller = FakeController(directory)
    helper = make(directory, expected_parent_pid=os.getpid() + 7)
    helper.start()
    try:
        assert helper.wait_exit(3.) == 3
        assert not controller.connected.is_set()
    finally:
        controller.close()


def test_a_helper_that_finds_no_socket_exits_with_a_connect_timeout(directory):
    helper = make(directory, connect_timeout_s=.3)
    helper.start()
    assert helper.wait_exit(3.) == 4
    assert helper.status == 'CONNECT_TIMEOUT'


def test_killing_the_runtime_kills_the_helper_and_closes_the_socket(directory):
    controller = FakeController(directory)
    runtime = subprocess.Popen([sys.executable, '-c', textwrap.dedent(f'''
        import sys, time
        from so101_demo.adapters.act.head_deadman_client import DeadmanHelper
        helper = DeadmanHelper(directory={str(directory)!r}, activation_id=1, connect_timeout_s=5.)
        helper.start()
        assert helper.wait_connected(5.)
        helper.start_ticker(period_s=.02)
        print(helper.pid, flush=True)
        time.sleep(60)
    ''')], stdout=subprocess.PIPE, text=True)
    try:
        helper_pid = int(runtime.stdout.readline())
        assert controller.connected.wait(5.)
        killed_at = time.monotonic()
        runtime.kill()
        runtime.wait()
        assert controller.eof.wait(1.)
        assert time.monotonic() - killed_at < .5
        def gone():
            try:
                return Path(f'/proc/{helper_pid}/stat').read_text().rsplit(')', 1)[1].split()[0] == 'Z'
            except OSError:
                return True
        deadline = time.monotonic() + 1.
        while time.monotonic() < deadline and not gone():
            time.sleep(.01)
        assert gone(), 'the helper outlived its runtime'
    finally:
        runtime.kill()
        controller.close()


def _runtime_script(directory, body):
    return textwrap.dedent(f'''
        import sys, time
        from so101_demo.adapters.act.head_deadman_client import DeadmanHelper
        helper = DeadmanHelper(directory={str(directory)!r}, activation_id=1, connect_timeout_s=5.)
        helper.start()
        assert helper.wait_connected(5.)
        helper.start_ticker(period_s=.02)
        time.sleep(.3)
        print('READY', time.monotonic(), flush=True)
    ''') + textwrap.dedent(body)


def _run_runtime_with_load(directory, body):
    controller = FakeController(directory)
    script = _runtime_script(directory, 'begin = time.monotonic()\n' + body +
                             'print("DONE", time.monotonic() - begin, flush=True)\ntime.sleep(.3)\n')
    runtime = subprocess.Popen([sys.executable, '-c', script], stdout=subprocess.PIPE, text=True)
    try:
        output = runtime.stdout.read()
    finally:
        runtime.wait(20)
    controller.close()
    held = [float(line.split()[1]) for line in output.split('\n') if line.startswith('DONE')][0]
    steady = controller.beats[len(controller.beats) // 6]
    return held, controller.gaps(steady)


def test_a_runtime_that_holds_the_gil_silences_the_heartbeat_after_the_liveness_bound(directory):
    # a single C call that keeps the GIL (about 0.8 s) starves the runtime's ticker thread
    held, gaps = _run_runtime_with_load(directory, 'x = 3 ** 6_000_000\n')
    assert held > .4, f'the big-integer power must hold the GIL for a while ({held:.2f}s)'
    assert max(gaps) >= .15, f'a starved runtime must silence the heartbeat ({max(gaps):.3f}s)'


def test_a_busy_runtime_that_yields_the_gil_does_not_silence_the_heartbeat(directory):
    held, gaps = _run_runtime_with_load(directory, (
        'end = time.monotonic() + 0.8\nwhile time.monotonic() < end:\n    sum(range(1000))\n'))
    assert held > .7
    assert max(gaps) < .06, f'load that yields the GIL must not silence the heartbeat ({max(gaps):.3f}s)'
