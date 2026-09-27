"""Immutable relative path input for a later broker-owned path proof."""

from dataclasses import dataclass

from .contracts import finite, validate_action_prefix
from .execution import prefix_sha256


def _nanoseconds(value):
    return round(finite(value, nonnegative=True) * 1_000_000_000)


@dataclass(frozen=True)
class RelativePathRequest:
    session_id: str
    attempt_id: str
    sequence: int
    policy_observation_time_s: float
    policy_received_wall_s: float
    source_prefix_sha256: str
    bridge_offset_ns: int
    target_offsets_ns: tuple[int, ...]
    positions: tuple[tuple[float, ...], ...]

    def require_policy_freshness(self, *, now_wall_s, max_age_s, jitter_s):
        age = finite(now_wall_s, nonnegative=True) - self.policy_received_wall_s
        limit = finite(max_age_s)
        jitter = finite(jitter_s, nonnegative=True)
        if limit <= 0 or not 0 <= age or not age + jitter < limit:
            raise ValueError('POLICY_OBSERVATION_STALE')

    @classmethod
    def from_prefix(cls, prefix, *, bridge_time_s, start_time_s,
                    policy_received_wall_s):
        checked = validate_action_prefix(prefix)
        observation_ns = _nanoseconds(checked['observation_time_s'])
        bridge_ns = _nanoseconds(bridge_time_s)
        start_ns = _nanoseconds(start_time_s)
        targets_ns = tuple(_nanoseconds(value) for value in checked['target_times_s'])
        if not bridge_ns <= observation_ns < start_ns < targets_ns[0]:
            raise ValueError('PATH_TIME_AXIS_INVALID')
        return cls(
            session_id=checked['session_id'], attempt_id=checked['attempt_id'],
            sequence=checked['sequence'],
            policy_observation_time_s=checked['observation_time_s'],
            policy_received_wall_s=finite(policy_received_wall_s, nonnegative=True),
            source_prefix_sha256=prefix_sha256(checked),
            bridge_offset_ns=bridge_ns - start_ns,
            target_offsets_ns=tuple(value - start_ns for value in targets_ns),
            positions=checked['positions'],
        )

    def materialize(self, *, start_time_s, bridge_time_s):
        start_ns = _nanoseconds(start_time_s)
        bridge_ns = _nanoseconds(bridge_time_s)
        if bridge_ns - start_ns != self.bridge_offset_ns:
            raise ValueError('BRIDGE_INTERVAL_CHANGED')
        return {
            'session_id': self.session_id, 'attempt_id': self.attempt_id,
            'sequence': self.sequence,
            'policy_observation_time_s': self.policy_observation_time_s,
            'policy_received_wall_s': self.policy_received_wall_s,
            'source_prefix_sha256': self.source_prefix_sha256,
            'bridge_time_s': bridge_ns / 1_000_000_000,
            'start_time_s': start_ns / 1_000_000_000,
            'target_times_s': tuple((start_ns + offset) / 1_000_000_000
                                    for offset in self.target_offsets_ns),
            'positions': self.positions,
        }
