"""Fixed monotonic expert/policy attempt budget, independent of simulation time."""

from dataclasses import dataclass, field

from .contracts import ContractError, finite

ACT_TIMEOUT_S = 120.0


@dataclass(frozen=True)
class Deadline:
    started_wall_s: float
    _last_wall_s: float = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        start = finite(self.started_wall_s, nonnegative=True)
        object.__setattr__(self, "_last_wall_s", start)

    def expired(self, now_wall_s):
        now = finite(now_wall_s, nonnegative=True)
        if now < self._last_wall_s:
            raise ContractError("MONOTONIC_TIME_REVERSED")
        object.__setattr__(self, "_last_wall_s", now)
        return now - self.started_wall_s >= ACT_TIMEOUT_S
