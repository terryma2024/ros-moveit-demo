"""The Head neck dead-man heartbeat helper (design section 1.4, review 3 issue 1).

A separate process, stdlib only, started as ``python -I head_deadman_helper.py ...`` by the runtime
that owns the Head neck. It connects to the controller's per-activation socket and sends one byte
every period, so the Python GIL of the runtime can never stall the heartbeat itself. It is tied to
the runtime in three ways:

* ``PR_SET_PDEATHSIG(SIGKILL)``, then a re-check of the parent pid (a parent that died before the
  call has already re-parented the helper);
* a liveness pipe: heartbeats are sent only while liveness ticks keep arriving from the runtime. If no
  tick arrived for the liveness bound (150 ms) the heartbeat stops at once; ticks resuming resume it;
* the end of the pipe (the runtime closed it) ends the helper, which closes the socket.

A ``C`` byte on the liveness pipe is the planned close: the helper closes the socket and exits 0.

Exit codes: 0 closed or pipe ended, 3 wrong parent, 4 connect timeout, 5 socket error. Status lines on
the status pipe: STARTED, CONNECTED, CLOSED, LIVENESS_EOF, CONNECT_TIMEOUT, PARENT_MISMATCH, SOCKET_ERROR.
"""

import argparse
import ctypes
import os
import select
import signal
import socket
import sys
import time

PR_SET_PDEATHSIG = 1


def _status(fd, text):
    try:
        os.write(fd, (text + '\n').encode('ascii'))
    except OSError:
        pass


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', required=True)
    parser.add_argument('--activation-id', type=int, required=True)
    parser.add_argument('--parent-pid', type=int, required=True)
    parser.add_argument('--liveness-fd', type=int, required=True)
    parser.add_argument('--status-fd', type=int, required=True)
    parser.add_argument('--period', type=float, default=0.02)
    parser.add_argument('--liveness', type=float, default=0.15)
    parser.add_argument('--connect-timeout', type=float, default=5.0)
    args = parser.parse_args(argv)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_PDEATHSIG, int(signal.SIGKILL), 0, 0, 0) != 0:
        _status(args.status_fd, 'PDEATHSIG_FAILED')
        return 6
    if os.getppid() != args.parent_pid:
        _status(args.status_fd, 'PARENT_MISMATCH')
        return 3
    _status(args.status_fd, 'STARTED')
    path = os.path.join(args.directory, 'neck-%d.sock' % args.activation_id)
    deadline = time.monotonic() + args.connect_timeout
    connection = None
    while connection is None:
        if time.monotonic() >= deadline:
            _status(args.status_fd, 'CONNECT_TIMEOUT')
            return 4
        attempt = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            attempt.connect(path)
            connection = attempt
        except OSError:
            attempt.close()
            time.sleep(0.005)
    _status(args.status_fd, 'CONNECTED')
    last_tick = time.monotonic()
    next_beat = time.monotonic()
    while True:
        now = time.monotonic()
        ready, _, _ = select.select([args.liveness_fd], [], [], max(0.0, next_beat - now))
        if ready:
            data = os.read(args.liveness_fd, 256)
            if not data:
                connection.close()
                _status(args.status_fd, 'LIVENESS_EOF')
                return 0
            if b'C' in data:
                connection.close()
                _status(args.status_fd, 'CLOSED')
                return 0
            if b't' in data:
                last_tick = time.monotonic()
        now = time.monotonic()
        if now >= next_beat:
            next_beat += args.period
            if next_beat < now:
                next_beat = now + args.period
            if now - last_tick <= args.liveness:
                try:
                    connection.send(b'h', socket.MSG_NOSIGNAL)
                except OSError:
                    _status(args.status_fd, 'SOCKET_ERROR')
                    return 5


if __name__ == '__main__':
    sys.exit(main())
