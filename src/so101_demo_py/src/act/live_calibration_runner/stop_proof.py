"""Three authoritative stop readbacks within a broker refresh window."""

import time


def stable_stop(connection, context, records, *, expected, seconds=5., poll_s=.02,
                monotonic=time.monotonic, sleep=time.sleep):
    if expected not in ("IDLE", "RUNNING") or seconds <= 0 or poll_s <= 0:
        raise ValueError("STOP_PROOF_PARAMETERS_INVALID")
    deadline = monotonic() + seconds
    consecutive = 0
    while monotonic() < deadline:
        state = connection.request("status", context)
        records.append(state)
        if state["hazard_reason"] is not None:
            raise RuntimeError("BROKER_HAZARD:" + str(state["hazard_reason"]))
        consecutive = consecutive + 1 if (state["state"] == expected and
                                            state["stop_confirmed"] is True) else 0
        if consecutive >= 3:
            return True
        sleep(poll_s)
    return False


def require_stop_proof(connection, context, records, *, timeout_s=5., poll_s=.02,
                       monotonic=time.monotonic, sleep=time.sleep):
    if not stable_stop(connection, context, records, expected="RUNNING",
                       seconds=timeout_s, poll_s=poll_s, monotonic=monotonic, sleep=sleep):
        raise AssertionError("POST_RESET_STOP_PROOF_MISSING")
