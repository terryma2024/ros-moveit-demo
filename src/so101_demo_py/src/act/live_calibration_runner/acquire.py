"""Bounded broker acquisition for one diagnostic attempt."""

import time


def acquire_after_stop(connection, *, owner, session, attempt, status_context,
                       status_records, attempts=5, timeout_s=3.,
                       monotonic=time.monotonic, sleep=time.sleep):
    if type(attempts) is not int or attempts < 1 or timeout_s <= 0:
        raise ValueError("ACQUIRE_BOUND_INVALID")
    for index in range(attempts):
        try:
            return connection.acquire(owner, session, attempt)
        except PermissionError as error:
            if str(error) != "CONTROL_NOT_STOPPED":
                raise
            if index + 1 == attempts:
                raise RuntimeError("BOUNDED_ACQUIRE_EXHAUSTED") from error
        deadline = monotonic() + timeout_s
        while monotonic() < deadline:
            state = connection.request("status", status_context)
            status_records.append(state)
            if state["hazard_reason"] is not None:
                raise RuntimeError("BROKER_HAZARD:" + str(state["hazard_reason"]))
            if state["state"] == "IDLE" and state["stop_confirmed"] is True:
                break
            sleep(.05)
        else:
            raise RuntimeError("BROKER_STOP_BARRIER_MISSING")
    raise AssertionError("unreachable acquisition bound")
