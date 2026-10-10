"""Bounded lazy CPU workers for Head observation and cancellation RPC calls."""

import math
import queue
import threading
import time


def exception_metadata(error):
    """Bounded built-in metadata, without an exception's custom formatter."""
    name=type(error).__name__
    args=BaseException.args.__get__(error)
    detail=args[0][:256] if args and type(args[0]) is str else ''
    return name+(': '+detail if detail else '')


class HeadCallbackIO:
    def __init__(self, name, *, capacity=32):
        if type(capacity) is not int or not 0 < capacity <= 128:
            raise ValueError('HEAD_CALLBACK_IO_CAPACITY_INVALID')
        self._queue = queue.Queue(maxsize=capacity)
        self._lock = threading.Lock()
        self._closed = False
        self._thread = None
        self._name = name
        self._error = None
        self._report_error = None

    def submit(self, operation, on_error):
        """Queue without waiting; no SDK work runs on the submitting callback."""
        with self._lock:
            if self._closed:
                raise PermissionError('HEAD_CALLBACK_IO_CLOSED')
            try:
                self._queue.put_nowait((operation, on_error))
            except queue.Full:
                self._closed = True
                raise PermissionError('HEAD_CALLBACK_IO_QUEUE_FULL') from None
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, daemon=True, name=self._name)
                try:self._thread.start()
                except BaseException:
                    self._closed = True
                    raise

    def _run(self):
        while True:
            item = self._queue.get()
            if item is None:return
            operation, on_error = item
            with self._lock:closed = self._closed
            try:
                if closed:raise PermissionError('HEAD_CALLBACK_IO_CLOSED')
                operation()
            except Exception as error:
                # Close before calling external reporting code. A failed SDK
                # operation or reporter must never leave a dead queue open.
                with self._lock:self._closed = True
                report_failure=None
                try:on_error(error)
                except Exception as report_error:report_failure=report_error
                # The owned fault callback runs before even bounded diagnostic
                # metadata; neither formatter nor reporter owns the queue lock.
                diagnostic=exception_metadata(error)
                reporting=None if report_failure is None else exception_metadata(report_failure)
                with self._lock:
                    self._error=diagnostic;self._report_error=reporting
            finally:self._queue.task_done()
            with self._lock:
                if self._closed:return

    def close(self, *, timeout_s):
        """Owned teardown only; thread retirement is never a robot stop proof."""
        if type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or timeout_s < 0:
            raise ValueError('HEAD_CALLBACK_IO_CLOSE_DEADLINE_INVALID')
        started = time.monotonic()
        with self._lock:
            self._closed = True
            thread = self._thread
            if thread is not None:
                try:self._queue.put_nowait(None)
                except queue.Full:pass
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout_s)
        return dict(retired=thread is None or not thread.is_alive(),
                    pending=self._queue.qsize(),elapsed_s=time.monotonic()-started)
