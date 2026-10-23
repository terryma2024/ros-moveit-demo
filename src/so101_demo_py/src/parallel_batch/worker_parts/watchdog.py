"""The heartbeat watchdog."""

from __future__ import annotations

import threading

from so101_demo.parallel_batch.contracts.identity import LeaseIdentity
from so101_demo.parallel_batch.worker_parts.contracts import _emit_diagnostic


class _HeartbeatWatchdog:
    """Send heartbeats outside the execution thread and latch the first fault."""

    def __init__(self, owner: "ParallelWorker", lease: LeaseIdentity):
        self._owner = owner
        self._lease = lease
        self._stop = threading.Event()
        self._fault = threading.Event()
        self._reason = None
        self._thread = threading.Thread(
            target=self._run,
            name=f"parallel-worker-heartbeat-{lease.worker_id}",
            daemon=True,
        )

    @property
    def faulted(self) -> bool:
        return self._fault.is_set()

    @property
    def reason(self) -> str | None:
        return self._reason

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=0.2)

    def _fail(self, reason: str) -> None:
        if not self._fault.is_set():
            self._reason = reason
            self._fault.set()
            self._owner._watchdog_revoked(self._lease, reason)

    def _diagnose(self, reason, started, error=None) -> None:
        try:
            try:
                now = self._owner._now()
            except Exception:
                now = None
            _emit_diagnostic("WORKER_WATCHDOG_EXCEPTION", {
                "reason": reason,
                "worker_id": self._lease.worker_id,
                "elapsed_s": None if started is None or now is None else now - started,
                "now_s": now,
            }, error)
        except Exception:
            pass

    def _run(self) -> None:
        while not self._stop.is_set():
            if self._owner._stop_requested.is_set():
                return
            started = None
            completed = threading.Event()
            response = {}

            def send_heartbeat():
                try:
                    response["ack"] = self._owner._heartbeat_transaction(
                        self._lease, started + self._owner._config.heartbeat_timeout_s)
                except Exception as error:
                    response["error"] = error
                finally:
                    completed.set()

            try:
                started = self._owner._now()
                threading.Thread(
                    target=send_heartbeat,
                    name=f"parallel-worker-heartbeat-rpc-{self._lease.worker_id}",
                    daemon=True,
                ).start()
                while not completed.wait(0.01):
                    if self._stop.is_set():
                        return
                    if self._owner._now() - started >= self._owner._config.heartbeat_timeout_s:
                        self._diagnose("HEARTBEAT_ACK_TIMEOUT", started)
                        self._fail("HEARTBEAT_ACK_TIMEOUT")
                        return
                if "error" in response:
                    raise response["error"]
                finished = self._owner._now()
                if finished - started >= self._owner._config.heartbeat_timeout_s:
                    self._diagnose("HEARTBEAT_ACK_TIMEOUT", started)
                    self._fail("HEARTBEAT_ACK_TIMEOUT")
                    return
                ack = response.get("ack")
                if not self._owner._ordered_receipts and not self._owner._accept_heartbeat(ack, self._lease):
                    self._diagnose("HEARTBEAT_ACK_INVALID", started)
                    self._fail("HEARTBEAT_ACK_INVALID")
                    return
                self._lease = ack
            except Exception as error:
                self._diagnose("COORDINATOR_LOST", started, error)
                self._fail("COORDINATOR_LOST")
                return
            if self._stop.wait(self._owner._config.heartbeat_interval_s):
                return
