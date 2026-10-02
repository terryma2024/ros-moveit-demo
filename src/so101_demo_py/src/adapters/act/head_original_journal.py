"""Bounded owned writer for original Head metadata, with no motion authority."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import queue
import threading
import time


class HeadOriginalJournal:
    def __init__(self,path,*,fault_callback):
        if not callable(fault_callback):raise ValueError('HEAD_ORIGINAL_JOURNAL_CALLBACK_INVALID')
        self.path=Path(path);self._fault_callback=fault_callback
        self._records=queue.Queue(maxsize=20000);self._lock=threading.Lock()
        self._closed=False;self._failed=False;self._count=0
        self._handle=self.path.open('x',encoding='ascii')
        self._thread=threading.Thread(target=self._run,name='head-original-journal')
        try:self._thread.start()
        except BaseException:self._handle.close();raise

    def _fail(self):
        with self._lock:
            first=not self._failed;self._failed=True
        if first:
            try:self._fault_callback('HEAD_ORIGINAL_JOURNAL_FAILED')
            except Exception:pass

    def __call__(self,kind,record):
        owned=dict(kind=kind,record=deepcopy(record))
        try:
            with self._lock:
                if self._closed or self._failed:raise PermissionError('HEAD_ORIGINAL_JOURNAL_CLOSED')
                self._records.put_nowait(owned)
        except queue.Full:
            self._fail();raise PermissionError('HEAD_ORIGINAL_JOURNAL_OVERFLOW') from None

    def _run(self):
        try:
            while True:
                item=self._records.get()
                try:
                    if item is None:break
                    self._handle.write(json.dumps(item,sort_keys=True,allow_nan=False)+'\n')
                    self._count+=1
                finally:self._records.task_done()
            self._handle.flush();os.fsync(self._handle.fileno())
        except BaseException:self._fail()
        finally:
            try:self._handle.close()
            except BaseException:self._fail()

    def close(self,*,timeout_s):
        deadline=time.monotonic()+timeout_s
        with self._lock:
            if self._closed:raise PermissionError('HEAD_ORIGINAL_JOURNAL_ALREADY_CLOSED')
            self._closed=True
        if self._thread.is_alive():
            try:self._records.put(None,timeout=max(0.,deadline-time.monotonic()))
            except queue.Full:self._fail()
        self._thread.join(timeout=max(0.,deadline-time.monotonic()))
        if self._thread.is_alive() or self._failed:
            self._fail();raise RuntimeError('HEAD_ORIGINAL_JOURNAL_SEAL_FAILED')
        return dict(path=str(self.path),count=self._count,thread_exited=True,
            sha256=hashlib.sha256(self.path.read_bytes()).hexdigest())
