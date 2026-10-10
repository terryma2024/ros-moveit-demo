"""The owner's side of the dead-man: spawn the helper, tick it, plan its close."""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from so101_demo.act import head_neck_limits as limits

HELPER_PATH = Path(__file__).with_name('head_deadman_helper.py')


class _Ticker:
    """Writes one liveness tick per period while it is running and the gate (if any) says alive."""

    def __init__(self, descriptor, period_s, alive=None):
        self._descriptor, self._period, self._alive = descriptor, period_s, alive
        self._run = threading.Event()
        self._run.set()
        self._stop = threading.Event()
        self.ticks = 0
        self._thread = threading.Thread(target=self._loop, name='head-deadman-ticker', daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop.wait(self._period):
            if not self._run.is_set() or (self._alive is not None and not self._alive()):
                continue
            try:
                os.write(self._descriptor, b't')
            except OSError:
                return
            self.ticks += 1

    def pause(self):
        self._run.clear()

    def resume(self):
        self._run.set()

    def stop(self):
        self._stop.set()
        self._thread.join(1.)


class DeadmanHelper:
    def __init__(self, *, directory, activation_id, connect_timeout_s=5.,
                 period_s=limits.DEADMAN_PERIOD_S, liveness_s=limits.DEADMAN_LIVENESS_S,
                 expected_parent_pid=None, python=None):
        self.directory, self.activation_id = str(directory), activation_id
        self.connect_timeout_s, self.period_s, self.liveness_s = connect_timeout_s, period_s, liveness_s
        self.expected_parent_pid = os.getpid() if expected_parent_pid is None else expected_parent_pid
        self.python = python or sys.executable
        self._process = None
        self._tick_write = None
        self._status_read = None
        self._status_lines = []
        self._status_event = threading.Event()
        self._lock = threading.Lock()
        self._ticker = None
        self._reader = None

    # ---- lifecycle ------------------------------------------------------------------------------

    def start(self):
        tick_read, self._tick_write = os.pipe()
        self._status_read, status_write = os.pipe()
        try:
            self._process = subprocess.Popen(
                [self.python, '-I', str(HELPER_PATH), '--directory', self.directory,
                 '--activation-id', str(self.activation_id), '--parent-pid', str(self.expected_parent_pid),
                 '--liveness-fd', str(tick_read), '--status-fd', str(status_write),
                 '--period', repr(self.period_s), '--liveness', repr(self.liveness_s),
                 '--connect-timeout', repr(self.connect_timeout_s)],
                pass_fds=(tick_read, status_write), stdin=subprocess.DEVNULL, close_fds=True)
        finally:
            os.close(tick_read)
            os.close(status_write)
        self._reader = threading.Thread(target=self._read_status, name='head-deadman-status', daemon=True)
        self._reader.start()
        return self._process.pid

    def _read_status(self):
        buffer = b''
        while True:
            try:
                data = os.read(self._status_read, 256)
            except OSError:
                return
            if not data:
                self._status_event.set()
                return
            buffer += data
            while b'\n' in buffer:
                line, buffer = buffer.split(b'\n', 1)
                with self._lock:
                    self._status_lines.append(line.decode('ascii', 'replace'))
                self._status_event.set()

    @property
    def pid(self):
        return None if self._process is None else self._process.pid

    @property
    def status(self):
        with self._lock:
            return self._status_lines[-1] if self._status_lines else None

    @property
    def status_lines(self):
        with self._lock:
            return list(self._status_lines)

    @property
    def returncode(self):
        return None if self._process is None else self._process.poll()

    def wait_connected(self, timeout_s):
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.status == 'CONNECTED':
                return True
            if self.returncode is not None and self.status != 'CONNECTED':
                return False
            time.sleep(.002)
        return self.status == 'CONNECTED'

    def wait_exit(self, timeout_s):
        try:
            self._process.wait(timeout_s)
        except subprocess.TimeoutExpired:
            return None
        return self._process.returncode

    # ---- liveness and close ------------------------------------------------------------------------

    def start_ticker(self, period_s=0.02, alive=None):
        """Tick the helper every period; ``alive`` gates the tick (the runtime's own liveness)."""
        if self._ticker is not None:
            raise PermissionError('DEADMAN_TICKER_ALREADY_STARTED')
        self._ticker = _Ticker(self._tick_write, period_s, alive)
        return self._ticker

    def tick(self):
        os.write(self._tick_write, b't')

    def close_planned(self, timeout_s=1.):
        """Ask the helper to close the socket and exit; True when it exited 0 reporting CLOSED."""
        if self._ticker is not None:
            self._ticker.stop()
            self._ticker = None
        try:
            os.write(self._tick_write, b'C')
        except OSError:
            pass
        code = self.wait_exit(timeout_s)
        deadline = time.monotonic() + .5
        while self.status != 'CLOSED' and time.monotonic() < deadline and code == 0:
            time.sleep(.002)
        return code == 0 and self.status == 'CLOSED'

    def drop_liveness_pipe(self):
        if self._ticker is not None:
            self._ticker.stop()
            self._ticker = None
        if self._tick_write is not None:
            os.close(self._tick_write)
            self._tick_write = None

    def kill(self):
        if self._ticker is not None:
            self._ticker.stop()
            self._ticker = None
        if self._process is not None and self._process.poll() is None:
            self._process.kill()
            self._process.wait()
        for name in ('_tick_write',):
            descriptor = getattr(self, name)
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                setattr(self, name, None)
