"""Fresh callbacks arriving during a read must not acquire a negative age.

The seams deliver real typed originals at a controlled call boundary. No
receipt, policy deadline, fault, Stop acknowledgement or goal is synthesized.
"""
import time

import pytest

from test_act_head_local_runtime import armed_runtime, prime_current_inputs, runtime_setup


@pytest.mark.parametrize('boundary',['executor','camera','feedback'])
def test_dispatch_clock_follows_the_snapshot_it_validates(monkeypatch,boundary):
    row=runtime_setup(monkeypatch)
    runtime=armed_runtime(row)
    policy=runtime.policy.readback()
    delivered=[]
    def deliver_once():
        if not delivered:
            delivered.append(True)
            prime_current_inputs(row)
    if boundary=='executor':
        def clock():
            captured=time.monotonic()
            deliver_once()
            return captured
        monkeypatch.setattr(runtime,'monotonic',clock)
    elif boundary=='camera':
        current=row.observer.current_inputs
        def snapshot(now):
            deliver_once()
            return current(now)
        monkeypatch.setattr(row.observer,'current_inputs',snapshot)
    else:
        feedback=row.port.feedback_snapshot
        def snapshot():
            deliver_once()
            return feedback()
        monkeypatch.setattr(row.port,'feedback_snapshot',snapshot)
    try:
        assert runtime.dispatch_guard() is True
        assert delivered and not runtime.faulted
        assert runtime.policy.readback()==policy
    finally:runtime.close(timeout_s=1.)


def test_new_feedback_cannot_renew_an_observation_deadline_that_expires_during_snapshot(monkeypatch):
    row=runtime_setup(monkeypatch)
    runtime=armed_runtime(row)
    feedback=row.port.feedback_snapshot
    runtime.dispatch_observation_deadline(time.monotonic()+.02)
    def delayed_snapshot():
        time.sleep(.03)
        prime_current_inputs(row)
        return feedback()
    monkeypatch.setattr(row.port,'feedback_snapshot',delayed_snapshot)
    try:
        with pytest.raises(PermissionError,match='OBSERVATION_EXPIRED'):
            runtime.dispatch_guard()
        assert runtime.faulted
    finally:runtime.close(timeout_s=1.)
