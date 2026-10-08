"""A spooler dies with the Recorder that started it (CP-3405: test runs left spoolers re-parented to PID 1 for hours).

Two independent guards, both in the child: the kernel's parent-death signal (PR_SET_PDEATHSIG, SIGKILL: nothing the child holds
needs a graceful end) and a watchdog thread that notices a changed parent pid, which also covers a parent that died before the
signal was armed and kernels without prctl. In the parent every spool process object closes itself at interpreter exit.
"""

from __future__ import annotations

import atexit
import ctypes
import os
import signal
import threading
import time

_PR_SET_PDEATHSIG = 1


def die_with_parent(parent_pid: int, *, on_orphan=None, period_s: float = 0.25) -> None:
    try:
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(_PR_SET_PDEATHSIG, int(signal.SIGKILL), 0, 0, 0)
    except Exception:
        pass
    if os.getppid() != parent_pid:               # the parent died before the signal was armed
        os.kill(os.getpid(), signal.SIGKILL)

    def watch() -> None:
        while True:
            time.sleep(period_s)
            if os.getppid() != parent_pid:
                if on_orphan is not None:
                    on_orphan()
                os.kill(os.getpid(), signal.SIGKILL)

    threading.Thread(target=watch, name="so101-spool-parent-watchdog", daemon=True).start()


def register_exit_close(owner) -> None:
    """Close `owner` (a spool process object) when the interpreter exits, however the owner's user forgot to."""
    atexit.register(lambda: owner.close())
