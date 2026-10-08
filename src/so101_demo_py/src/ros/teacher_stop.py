"""Teacher stop flags: user stop, parent death and the attempt deadline.

Nothing here touches ROS or a goal. A signal handler, the parent-pid check and the deadline watchdog thread only set
flags. The flags are read on the executing thread by the trajectory monitor, the gripper hook, the wait loops that have
no active goal and the state-machine entry, which raise `TeacherStop`. `MoveItExecutionClient` turns a monitor raise
into a cancel and `GripperClient` does the same for its own goal, so no thread other than the executing one ever calls
`cancel_goal_async`.
"""

from __future__ import annotations

import os
import signal
import threading
import time
from typing import Callable

USER_STOP = "TEACHER_USER_STOP"
PARENT_DIED = "TEACHER_PARENT_DIED"
DEADLINE = "TEACHER_DEADLINE"


class TeacherStop(RuntimeError):
    """A stop that ends the run. `code` is a `core.workflow.TERMINAL_STOP_CODES` member."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


class StopFlags:
    """User, parent-death and deadline flags with the first reason winning."""

    def __init__(
        self,
        *,
        parent_pid: int | None = None,
        getppid: Callable[[], int] = os.getppid,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._lock = threading.Lock()
        self._reason: str | None = None
        self._getppid = getppid
        self._parent_pid = getppid() if parent_pid is None else parent_pid
        self._clock = clock
        self._deadline_at: float | None = None
        self._deadline_flag = False

    # -- setters: safe from a signal handler or a watchdog thread (a flag write, nothing else) ---------------------

    def request_user_stop(self, reason: str = USER_STOP) -> None:
        with self._lock:
            if self._reason is None:
                self._reason = reason

    def arm_deadline(self, deadline_s: float) -> None:
        """Freeze the attempt deadline at `clock() + deadline_s`. A second call changes nothing."""
        with self._lock:
            if self._deadline_at is None:
                self._deadline_at = self._clock() + float(deadline_s)

    def set_deadline_flag(self) -> None:
        with self._lock:
            self._deadline_flag = True

    @property
    def deadline_flag_set(self) -> bool:
        with self._lock:
            return self._deadline_flag

    def check_deadline_clock(self) -> None:
        """Set the deadline flag when the frozen deadline has passed (the watchdog thread's only action)."""
        with self._lock:
            if self._deadline_at is not None and self._clock() >= self._deadline_at:
                self._deadline_flag = True

    # -- readers ----------------------------------------------------------------------------------------------------

    def reason(self) -> str | None:
        """The stop reason, or None. Compares the parent pid and the frozen deadline with the clock."""
        try:
            if self._getppid() != self._parent_pid:
                self.request_user_stop(PARENT_DIED)
        except OSError:
            pass
        self.check_deadline_clock()
        with self._lock:
            if self._reason is not None:
                return self._reason
            if self._deadline_flag:
                return DEADLINE
            return None

    def raise_if_stopped(self) -> None:
        reason = self.reason()
        if reason is not None:
            raise TeacherStop(reason)

    # -- signals ----------------------------------------------------------------------------------------------------

    def install_signal_handlers(self, signals=(signal.SIGINT, signal.SIGTERM)) -> Callable[[], None]:
        """Install handlers that only set the user-stop flag. Returns a function that restores the old ones."""
        previous = {}

        def handler(_signum, _frame):
            self.request_user_stop(USER_STOP)

        for signum in signals:
            previous[signum] = signal.signal(signum, handler)

        def restore() -> None:
            for signum, old in previous.items():
                signal.signal(signum, old)

        return restore


class DeadlineWatchdog:
    """A thread that sets the deadline flag once the frozen deadline passed. It holds no reference to any goal."""

    def __init__(self, flags: StopFlags, *, poll_s: float = 0.05) -> None:
        self._flags = flags
        self._poll_s = poll_s
        self._stopped = threading.Event()
        self.thread = threading.Thread(target=self._run, name="teacher-deadline-watchdog", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def _run(self) -> None:
        while not self._stopped.wait(self._poll_s):
            self._flags.check_deadline_clock()
            if self._flags.deadline_flag_set:
                return

    def stop(self) -> None:
        self._stopped.set()
        if self.thread.is_alive() and self.thread is not threading.current_thread():
            self.thread.join(1.0)
