"""After acceptance, compare the controller_state reference with the sealed quintic (design section 2).

The guard checked the whole quintic before dispatch, and it sealed the proof. Once the goal is accepted
the stock controller samples that same quintic every 2 ms, so the ``reference`` of each
``/neck_controller/controller_state`` sample must lie on it. A foreign goal that reaches the controller
(admission authenticates the owner's dead-man connection, not individual action clients) moves the
reference off the curve; the divergence is *detected after the fact* and the owner stops (cancel, then the
stop path) with ``HEAD_REFERENCE_DIVERGED``.

Phases of one goal, in sim time:
  PREFIX   before the first point: the reference stays inside the sealed prefix envelope;
  MOVING   first point to last point: it lies on the quintic, tolerating a time misalignment of
           +/- two controller ticks (4 ms) and 1 microradian;
  HOLD     after the last point: it holds the final position within 1 microradian.
The reference velocity never exceeds the sealed velocity limit by more than 5 %.
"""

import math
import threading

from so101_demo.act import head_neck_limits as limits

CODE = 'HEAD_REFERENCE_DIVERGED'
_POSITION_TOLERANCE_RAD = 1e-6
_ALIGNMENT_NS = 2 * limits.STOP_WINDOW_STEP_NS
_VELOCITY_MARGIN = 1.05


def _quintic(q0, q1, duration_ns, tau_ns):
    s = min(max(tau_ns / duration_ns, 0.0), 1.0)
    return q0 + (q1 - q0) * (10 * s**3 - 15 * s**4 + 6 * s**5)


class HeadReferenceMonitor:
    def __init__(self, *, on_diverged=None):
        if on_diverged is not None and not callable(on_diverged):
            raise ValueError('REFERENCE_MONITOR_CALLBACK_INVALID')
        self._on_diverged = on_diverged
        self._lock = threading.Lock()
        self._goal = None
        self.diverged = None
        self.observed = 0

    def arm(self, proof):
        try:
            header = proof['header_stamp_ns']
            first_ns, last_ns = proof['typed_curve']['times_from_start_ns']
            q0, q1 = proof['typed_curve']['positions_rad']
            low, high = proof['collision']['prefix_envelope_rad']
            max_velocity = proof['max_velocity_rad_s']
            values = (header, first_ns, last_ns, q0, q1, low, high, max_velocity)
            if (any(type(value) not in (int, float) or not math.isfinite(value) for value in values)
                    or type(header) is not int or header < 0 or not 0 < first_ns < last_ns
                    or not low <= q0 <= high or max_velocity <= 0):
                raise ValueError
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError('REFERENCE_MONITOR_PROOF_INVALID') from error
        with self._lock:
            self._goal = dict(first=header + first_ns, last=header + last_ns, duration=last_ns - first_ns,
                              q0=q0, q1=q1, low=low, high=high, max_velocity=max_velocity)
            self.diverged = None
            self.observed = 0

    def disarm(self):
        with self._lock:
            self._goal = None

    def observe(self, sample):
        """Check one controller_state sample; returns the (first) divergence or None."""
        callback = None
        with self._lock:
            goal = self._goal
            if goal is None:
                return None
            if self.diverged is not None:
                return self.diverged
            self.observed += 1
            sim_ns = sample['sim_ns']
            position, velocity = sample['reference_position'], sample['reference_velocity']
            verdict = None
            if (not all(type(value) in (int, float) and math.isfinite(value)
                        for value in (position, velocity))):
                verdict = self._verdict('PREFIX', 'NON_FINITE', sim_ns, math.inf)
            elif abs(velocity) > goal['max_velocity'] * _VELOCITY_MARGIN:
                verdict = self._verdict(self._phase(goal, sim_ns), 'VELOCITY', sim_ns,
                                        abs(velocity) - goal['max_velocity'])
            elif sim_ns < goal['first']:
                outside = max(goal['low'] - position, position - goal['high'], 0.0)
                if outside > _POSITION_TOLERANCE_RAD:
                    verdict = self._verdict('PREFIX', 'POSITION', sim_ns, outside)
            elif sim_ns <= goal['last']:
                tau = sim_ns - goal['first']
                expected = [_quintic(goal['q0'], goal['q1'], goal['duration'], tau + shift)
                            for shift in (-_ALIGNMENT_NS, 0, _ALIGNMENT_NS)]
                outside = max(min(expected) - position, position - max(expected), 0.0)
                if outside > _POSITION_TOLERANCE_RAD:
                    verdict = self._verdict('MOVING', 'POSITION', sim_ns, outside)
            else:
                outside = abs(position - goal['q1'])
                if outside > _POSITION_TOLERANCE_RAD:
                    verdict = self._verdict('HOLD', 'POSITION', sim_ns, outside)
            if verdict is not None:
                self.diverged = verdict
                callback = self._on_diverged
        if verdict is not None and callback is not None:
            callback(verdict)
        return None if verdict is None else verdict

    @staticmethod
    def _phase(goal, sim_ns):
        return 'PREFIX' if sim_ns < goal['first'] else 'MOVING' if sim_ns <= goal['last'] else 'HOLD'

    @staticmethod
    def _verdict(phase, reason, sim_ns, deviation):
        return dict(code=CODE, phase=phase, reason=reason, sim_ns=sim_ns, deviation_rad=deviation)
