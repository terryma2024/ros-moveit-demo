"""Diagnostic only (not part of any gate): time each revocation stage; log lines to $REVOKE_TIMING_LOG."""
import os
import time
import threading


def pytest_configure(config):
    from so101_demo.runtime.container_campaign import task_builder as tb
    log = os.environ["REVOKE_TIMING_LOG"]

    def write(text):
        with open(log, "a") as stream:
            stream.write(f"{os.getpid()} {time.monotonic():.3f} {text}\n")

    original_start = tb.CollectionTaskExecution._start_revocation
    original_revoke = tb.CollectionTaskExecution._revoke

    def start(self, reason=None):
        started = time.monotonic()
        record = original_start(self, reason)
        if not record.get("_timed"):
            record["_timed"] = True

            def watch():
                record["event"].wait(60)
                t1 = time.monotonic()
                record["audit_event"].wait(60)
                t2 = time.monotonic()
                write(f"REVOKE event_after={t1 - started:.3f}s audit_after={t2 - started:.3f}s reason={reason}")

            threading.Thread(target=watch, daemon=True).start()
        return record

    def revoke(self):
        t0 = time.monotonic()
        try:
            return original_revoke(self)
        finally:
            write(f"_revoke wall={time.monotonic() - t0:.3f}s")

    tb.CollectionTaskExecution._start_revocation = start
    tb.CollectionTaskExecution._revoke = revoke
