"""The shadow stop window beside the broker stack (design section 3, step 1 of section 7).

It records what a topic-based stop window would have concluded, in its own log, and changes
nothing in the run: it grants no authority, never gates stop confirmation and swallows its own
failures into the log. ``so101_demo.act.head_stop_window_shadow`` compares the log with the
sealed native events. This module and its switch are removed when the thin JTC subclass lands.

Lifecycle, in order: ``start`` (before arm), ``note_first_goal`` (before the first goal is
sent: the startup window must have completed before it), ``on_raw_stop_confirmed`` (the
CANCEL_STOP worker calls it with the sim stamp of the raw-stop confirmation; the end window
then counts only samples stamped after it) and ``finish`` (after the runtime retired).
"""

import json
import os
import re
import threading
import time
from pathlib import Path

from so101_demo.act import head_neck_limits as limits
from .head_stop_window_subscriber import TOPIC, StopWindowSubscriber

ENVIRONMENT_VARIABLE = 'SO101_HEAD_SHADOW_STOP_WINDOW_DIR'
_RUN_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z')


class ShadowStopWindow:
    def __init__(self, *, context, directory, run_id, monotonic_ns=time.monotonic_ns):
        if type(run_id) is not str or _RUN_ID.fullmatch(run_id) is None or '..' in run_id:
            raise ValueError('SHADOW_RUN_ID_INVALID')
        directory = Path(directory)
        if not directory.is_absolute() or not directory.is_dir():
            raise ValueError('SHADOW_DIRECTORY_INVALID')
        self.run_id = run_id
        self.path = directory / f'shadow-stop-window-{run_id}.jsonl'
        self._monotonic_ns = monotonic_ns
        self._lock = threading.Lock()
        self._file = None
        self._phase = 'startup'
        self._startup_window = self._end_window = None
        self._end_recorded = threading.Event()
        self._final = None
        self.errors = []
        self.subscriber = StopWindowSubscriber(context=context, node_name='head_shadow_stop_window',
                                               monotonic_ns=monotonic_ns, on_complete=self._complete)

    # ---- log -----------------------------------------------------------------------------

    def _write(self, row):
        row = dict(row, mono_ns=self._monotonic_ns())
        try:
            with self._lock:
                if self._file is not None:
                    self._file.write(json.dumps(row, sort_keys=True) + '\n')
                    self._file.flush()
        except Exception as error:  # the shadow never breaks a run
            self.errors.append(f'{type(error).__name__}: {error}'[:200])

    def _complete(self, window):
        with self._lock:
            phase = self._phase
            if phase == 'startup':
                self._startup_window = dict(window)
            else:
                self._end_window = dict(window)
        self._write(dict(kind='SHADOW_WINDOW', phase=phase, window=window))
        if phase == 'end':
            self._end_recorded.set()

    # ---- lifecycle ---------------------------------------------------------------------------

    def start(self):
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
        self._file = os.fdopen(descriptor, 'w', encoding='utf-8')
        self.subscriber.start()
        self._write(dict(kind='SHADOW_STARTED', run_id=self.run_id, topic=TOPIC,
                         node_name=self.subscriber.node_name, qos_depth=self.subscriber.qos_profile.depth,
                         reliable=True, samples=limits.STOP_WINDOW_SAMPLES,
                         deadline_s=limits.STOP_WINDOW_DEADLINE_S))

    def _log_runs(self):
        with self._lock:
            phase = self._phase
        for run in self.subscriber.take_runs():
            self._write(dict(kind='SHADOW_QUIET_RUN', phase=phase, **run))

    def note_first_goal(self):
        """The owner is about to send its first goal: the startup phase ends, the window is void."""
        self.subscriber.void('FIRST_GOAL')
        self._log_runs()
        self._write(dict(kind='SHADOW_FIRST_GOAL', startup_completed=self._startup_window is not None))

    def on_raw_stop_confirmed(self, sim_ns):
        self.subscriber.flush_run()
        self._log_runs()
        with self._lock:
            self._phase = 'end'
        self.subscriber.rearm(floor_sim_ns=sim_ns)
        self._write(dict(kind='SHADOW_END_PHASE', raw_stop_sim_ns=sim_ns))

    def snapshot(self):
        return self.subscriber.snapshot()

    def finish(self, *, timeout_s):
        """Wait (bounded) for the end window when an end phase began, then close the log."""
        with self._lock:
            if self._final is not None:
                return dict(self._final)
            waiting = self._phase == 'end'
        if waiting:
            self._end_recorded.wait(timeout_s)
        self.subscriber.flush_run()
        self._log_runs()
        snapshot = self.subscriber.snapshot()
        receipt = self.subscriber.stop()
        final = dict(startup_window=self._startup_window, end_window=self._end_window,
                     resets=snapshot['resets'], voids=snapshot['voids'], received=snapshot['received'],
                     below_floor=snapshot['below_floor'])
        self._write(dict(kind='SHADOW_FINAL', stop_receipt=receipt, errors=list(self.errors), **final))
        with self._lock:
            self._final = final
            if self._file is not None:
                self._file.close()
                self._file = None
        return dict(final)


def shadow_from_environment(*, context, run_id, environ=None):
    """The one switch: a directory named by the environment turns the shadow on."""
    environ = os.environ if environ is None else environ
    value = environ.get(ENVIRONMENT_VARIABLE)
    if value is None:
        return None
    return ShadowStopWindow(context=context, directory=value, run_id=run_id)
