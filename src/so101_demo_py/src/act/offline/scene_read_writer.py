"""The planning-scene sidecar file, written off the read loop.

The read loop (about 20 Hz, and the Recorder's causal join needs every read) only `put`s finished lines. A single writer thread
appends them to the file in order, flushes and `fsync`s every `fsync_every` lines and once more at `close`. The file bytes are exactly
the bytes that were put, in the order they were put.

Nothing is dropped silently. A full queue and a write or fsync error both set `failure`, a code the recorder reports in its stats
(so the attempt's bag is judged invalid); a `put` after a failure raises. `close` returns only after everything queued has been
written and fsync'd, or sets `failure` when the writer could not finish within its time.
"""

from __future__ import annotations

from pathlib import Path
import os
import queue
import threading

from .delivery_diag import LOG as _DIAG_LOG, timed as _timed

QUEUE_CAPACITY = 1024          # about 50 s of reads at 20 Hz
FSYNC_EVERY = 20
CLOSE_TIMEOUT_S = 30.0


class SceneReadWriterError(RuntimeError):
    """The sidecar can no longer take lines; the message is the failure code."""


class SceneReadWriter:
    def __init__(self, path, *, capacity: int = QUEUE_CAPACITY, fsync_every: int = FSYNC_EVERY) -> None:
        self._path = Path(path)
        self._queue: queue.Queue = queue.Queue(maxsize=capacity)
        self._fsync_every = fsync_every
        self._closing = threading.Event()
        self._lock = threading.Lock()
        self._thread = None
        self._stream = None
        self._broken = False
        self.failure = None
        self.written = 0

    def _fail(self, code: str) -> None:
        with self._lock:
            if self.failure is None:
                self.failure = code

    def start(self) -> None:
        """Open the file for append and start the writer thread. Raises `SceneReadWriterError` when the file cannot be opened."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._stream = open(self._path, "ab")
        except OSError as error:
            code = f"RAW_SCENE_SIDECAR_WRITE_FAILED: {error!r}"[:300]
            self._fail(code)
            raise SceneReadWriterError(code) from error
        self._thread = threading.Thread(target=self._run, name="so101-raw-scene-reads-writer", daemon=True)
        self._thread.start()

    def put(self, record: bytes) -> None:
        """Queue one line (with its newline) behind the earlier ones. Never blocks; raises when the line cannot be kept."""
        if self.failure is not None:
            raise SceneReadWriterError(self.failure)
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            self._fail("RAW_SCENE_SIDECAR_QUEUE_FULL")
            raise SceneReadWriterError("RAW_SCENE_SIDECAR_QUEUE_FULL") from None

    def _write(self, record: bytes) -> None:
        self._stream.write(record)

    def _sync(self) -> None:
        self._stream.flush()
        os.fsync(self._stream.fileno())

    def _run(self) -> None:
        try:
            while True:
                try:
                    record = self._queue.get(timeout=0.05)
                except queue.Empty:
                    if self._closing.is_set():
                        break
                    continue
                if self._broken:
                    continue                      # the failure is recorded; nothing more can be written
                try:
                    _timed(_DIAG_LOG, "sidecar_write", lambda: self._write(record), written=self.written)
                    self.written += 1
                    if self.written % self._fsync_every == 0:
                        _timed(_DIAG_LOG, "sidecar_fsync", self._sync, written=self.written, queued=self._queue.qsize())
                except Exception as error:   # noqa: BLE001 - any write or fsync error is a recorder failure
                    self._broken = True
                    self._fail(f"RAW_SCENE_SIDECAR_WRITE_FAILED: {error!r}"[:300])
            if not self._broken:
                try:
                    _timed(_DIAG_LOG, "sidecar_final_fsync", self._sync, written=self.written)
                except Exception as error:   # noqa: BLE001
                    self._fail(f"RAW_SCENE_SIDECAR_WRITE_FAILED: {error!r}"[:300])
        finally:
            try:
                self._stream.close()
            except Exception:   # noqa: BLE001
                pass

    def close(self, timeout_s: float = CLOSE_TIMEOUT_S) -> None:
        """Wait until everything put so far is written and fsync'd; a writer that cannot finish in time is a failure."""
        self._closing.set()
        if self._thread is None:
            return
        self._thread.join(timeout_s)
        if self._thread.is_alive():
            self._fail("RAW_SCENE_SIDECAR_DRAIN_TIMEOUT")
