"""Task 14: a retry needs a known-empty cup, an unspent budget and a wall-clock allowance."""

import pytest

from so101_demo.act.session import retry_allowed


def test_no_retry_with_unknown_or_held_cup():
    assert not retry_allowed(0, "UNKNOWN", True)
    assert not retry_allowed(0, "HOLDING", True)
    assert retry_allowed(0, "EMPTY", True)
    assert not retry_allowed(1, "EMPTY", True)


def test_the_budget_and_the_inputs_are_closed():
    assert retry_allowed(0, "EMPTY", True) is True
    assert retry_allowed(0, "EMPTY", False) is False        # no budget left in the wall clock
    assert retry_allowed(2, "EMPTY", True) is False          # two spent retries is simply not a retry
    for attempts in (-1, True, 1.0, "0"):                    # malformed counts are refused
        with pytest.raises(ValueError, match="RETRY_ATTEMPTS_INVALID"):
            retry_allowed(attempts, "EMPTY", True)
    for state in ("empty", "HELD", "", None):
        with pytest.raises(ValueError, match="RETRY_CUP_STATE_INVALID"):
            retry_allowed(0, state, True)
    for budget in (1, None, "yes"):
        with pytest.raises(ValueError, match="RETRY_BUDGET_INVALID"):
            retry_allowed(0, "EMPTY", budget)


class _Worker:
    def __init__(self):
        self.calls = []

    def request(self, name, payload):
        self.calls.append((name, payload))
        return {"ok": True}


class _Inference:
    def __init__(self, *, reply=None):
        self.pending = None
        self._reply = reply

    def submit(self, observation, *, sequence):
        self.pending = sequence

    def poll(self):
        reply, self._reply = self._reply, None
        if reply:
            self.pending = None
        return reply or {}


def _session(*, commander="operator-1", reply=None, attempts=0):
    from types import SimpleNamespace

    from so101_demo.act.session import ActSession

    return ActSession(context=SimpleNamespace(commander_id=commander), worker_port=_Worker(),
                      inference=_Inference(reply=reply), attempts=attempts)


def test_only_the_session_commander_may_command_it():
    session = _session()
    assert session.command(commander_id="operator-1", name="START")["name"] == "START"
    with pytest.raises(ValueError, match="COMMAND_NOT_OWNED"):
        session.command(commander_id="operator-2", name="START")
    assert session.worker_port.calls == [("START", {})]      # the refused command never reached the port
    with pytest.raises(ValueError, match="SESSION_COMMAND_INVALID"):
        session.command(commander_id="operator-1", name="")
    session.close()
    with pytest.raises(ValueError, match="SESSION_CLOSED"):
        session.command(commander_id="operator-1", name="START")


def test_a_tick_never_waits_on_the_model_and_a_reply_advances_the_phase():
    idle = _session()
    assert idle.tick() == {"phase": "SEARCH", "waiting": False, "sequence": None, "actions": ()}
    waiting = _session()
    waiting.inference.submit({}, sequence=3)
    assert waiting.tick()["waiting"] is True                # reported, not blocked on
    answered = _session(reply={"sequence": 3, "actions": ((0.1,) * 6,), "age_s": 0.0})
    answered.inference.submit({}, sequence=3)
    tick = answered.tick()
    assert tick["phase"] == "ACT" and tick["sequence"] == 3 and tick["actions"] == ((0.1,) * 6,)


def test_the_retry_budget_is_spent_once_and_a_new_attempt_forgets_the_cup():
    session = _session()
    with pytest.raises(ValueError, match="RETRY_CUP_STATE_INVALID"):
        session.observe_cup("EMPTYISH")
    session.observe_cup("EMPTY")
    assert session.request_retry(budget_available=True) is True
    assert session.attempts == 1 and session.cup_state == "UNKNOWN"
    assert session.request_retry(budget_available=True) is False      # the budget is one
    holding = _session()
    holding.observe_cup("HOLDING")
    assert holding.request_retry(budget_available=True) is False      # never re-drive a held cup
    assert holding.attempts == 0
