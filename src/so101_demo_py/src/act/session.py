"""Task 14: what may be retried, and under whose command.

A retry re-drives the arm toward a cup. That is only defensible when the cup's state is actually known and
empty: a held cup would be crushed or dropped, and an unknown state might be either. The attempt budget is
deliberately one — the plan's baseline does not retry a failed placement on hope.
"""

from __future__ import annotations

CUP_STATES = ("EMPTY", "HOLDING", "UNKNOWN")
_SAFE_TO_RETRY = "EMPTY"


def retry_allowed(attempts: int, cup_state: str, budget_available: bool) -> bool:
    """Whether one more attempt may be started, given what is known about the cup.

    `attempts` counts retries already used: 0 means the single retry is still unspent, 1 means it is gone.
    """

    if type(attempts) is not int or attempts < 0:
        raise ValueError("RETRY_ATTEMPTS_INVALID")
    if cup_state not in CUP_STATES:
        raise ValueError("RETRY_CUP_STATE_INVALID")
    if type(budget_available) is not bool:
        raise ValueError("RETRY_BUDGET_INVALID")
    if cup_state != _SAFE_TO_RETRY:
        # holding or unknown: evidence first, and never a blind re-approach
        return False
    return attempts == 0 and budget_available


class ActSession:
    """One session with one commander, a non-blocking inference boundary and a retry budget.

    Command ownership is structural: the session is created with a single commander identity, and a command
    from anyone else is refused rather than queued. `tick` never waits on the model — it polls the
    one-in-flight boundary and reports whether it is still waiting, so the control loop stays in charge.
    """

    def __init__(self, *, context, worker_port, inference, attempts: int = 0) -> None:
        if not callable(getattr(worker_port, "request", None)):
            raise ValueError("SESSION_WORKER_PORT_REQUIRED")
        if not callable(getattr(inference, "submit", None)) or \
                not callable(getattr(inference, "poll", None)):
            raise ValueError("SESSION_INFERENCE_REQUIRED")
        commander_id = getattr(context, "commander_id", None)
        if not isinstance(commander_id, str) or not commander_id:
            raise ValueError("SESSION_COMMANDER_REQUIRED")
        if type(attempts) is not int or attempts < 0:
            raise ValueError("RETRY_ATTEMPTS_INVALID")
        self.context = context
        self.worker_port = worker_port
        self.inference = inference
        self.commander_id = commander_id
        self.attempts = attempts
        self.cup_state = "UNKNOWN"
        self.phase = "SEARCH"
        self.closed = False
        self.commands = []

    def observe_cup(self, state: str) -> None:
        if state not in CUP_STATES:
            raise ValueError("RETRY_CUP_STATE_INVALID")
        self.cup_state = state

    def command(self, *, commander_id: str, name: str, payload: dict | None = None) -> dict:
        if self.closed:
            raise ValueError("SESSION_CLOSED")
        if commander_id != self.commander_id:
            # one commander per session: a second writer would make the arm's owner ambiguous
            raise ValueError("COMMAND_NOT_OWNED")
        if not isinstance(name, str) or not name:
            raise ValueError("SESSION_COMMAND_INVALID")
        outcome = self.worker_port.request(name, payload or {})
        self.commands.append(name)
        return {"name": name, "outcome": outcome, "phase": self.phase}

    def request_retry(self, *, budget_available: bool) -> bool:
        if self.closed:
            raise ValueError("SESSION_CLOSED")
        allowed = retry_allowed(self.attempts, self.cup_state, budget_available)
        if allowed:
            self.attempts += 1
            self.cup_state = "UNKNOWN"          # the new attempt must re-establish what it holds
        return allowed

    def tick(self) -> dict:
        """Advance one step without ever waiting on the model."""

        if self.closed:
            raise ValueError("SESSION_CLOSED")
        waiting = getattr(self.inference, "pending", None) is not None
        if waiting:
            reply = self.inference.poll()        # refusals for stale or misordered replies propagate
            if reply:
                self.phase = "ACT"
                return {"phase": self.phase, "waiting": False, "sequence": reply["sequence"],
                        "actions": reply["actions"]}
            return {"phase": self.phase, "waiting": True, "sequence": None, "actions": ()}
        return {"phase": self.phase, "waiting": False, "sequence": None, "actions": ()}

    def close(self) -> None:
        self.closed = True
