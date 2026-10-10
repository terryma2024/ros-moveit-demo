"""Bind the owned local observer to existing original callbacks, without authority."""
from copy import deepcopy
import threading

from .ros_execution import RosControllerPort


def _local_observer(primary):
    from .head_local_observer import HeadLocalObserver
    return type(primary) is HeadLocalObserver


class HeadOriginalRouter:
    def __init__(self,port,sink,*,progress=None):
        if (not isinstance(port,RosControllerPort) or (sink is not None and not callable(sink))
                or (progress is not None and not callable(progress))
                or (not port._head_bootstrap and port.feedback_policy is None)):
            raise ValueError('HEAD_ORIGINAL_ROUTER_CONFIG_INVALID')
        self.port=port;self.sink=sink;self._primary=None;self._closed=False;self._retiring=False
        self.progress=progress
        self._bound=False;self._lock=threading.Lock()

    def _primary_valid(self,primary):
        if _local_observer(primary):
            return primary.port is self.port and not primary.failed and not primary.closed
        return False

    def bind_primary(self,primary):
        if not self._primary_valid(primary):
            raise ValueError('HEAD_ORIGINAL_ROUTER_PRIMARY_INVALID')
        with self._lock:
            if self._closed or self._retiring or self._bound:
                raise PermissionError('HEAD_ORIGINAL_ROUTER_REBOUND')
            self._bound=True;self._primary=primary

    def __call__(self,kind,record):
        with self._lock:primary=None if self._closed else self._primary
        # Invalidity latches on the owned primary before any journal callback.
        # The original is still retained, including rejected sensor payloads.
        try:
            if primary is not None:primary.observe_original(kind,deepcopy(record))
        finally:
            if self.progress is not None:self.progress()
            if self.sink is not None:self.sink(kind,deepcopy(record))

    def retire(self):
        with self._lock:
            primary=self._primary;self._retiring=True
        if primary is not None and not primary.failed:
            primary.fault('HEAD_PRIMARY_ORIGINAL_ROUTER_RETIRED')
        with self._lock:self._closed=True
