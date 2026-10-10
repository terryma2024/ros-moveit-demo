"""The 51-sample ``controller_state`` stop window (design section 3), as a pure evaluator.

A window is 51 consecutive ``/neck_controller/controller_state`` samples on the 2 ms sim-stamp
grid in which every sample has |feedback velocity| <= 0.002, |reference velocity| <= 0.002,
the same reference position as the first sample, and a monotonic receive age <= 200 ms
measured at the moment the window completes. ``controller_state`` carries neither "holding"
nor "no active goal"; the unchanged reference position stands in for both, and the owner voids
the window with :meth:`void` whenever it sends a goal.

The evaluator owns no clock and no ROS object. The caller passes the sim stamp, the monotonic
receive time and the monotonic evaluation time of every sample.
"""

from collections import Counter, deque
import math

from . import head_neck_limits as limits

RESET_REASONS = ('INVALID_SAMPLE', 'VELOCITY', 'SIM_TIME_GAP', 'RECEIVED_TIME_REGRESSION',
                 'REFERENCE_CHANGED')


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


class StopWindow:
    """Evaluate one stream of controller_state samples; the first completion is latched."""

    def __init__(self):
        self._samples = deque(maxlen=limits.STOP_WINDOW_SAMPLES)
        self._completed = None
        self.resets = Counter()
        self.voids = []
        self.observed = 0

    @property
    def completed(self):
        return None if self._completed is None else dict(self._completed)

    @property
    def pending_count(self):
        return len(self._samples)

    def rearm(self):
        """Forget the latched window and the buffer; counters keep running."""
        self._samples.clear()
        self._completed = None

    def void(self, reason):
        """A goal (or any other owner event) voids the samples collected so far."""
        self.voids.append(reason)
        self._samples.clear()

    def _reset(self, reason):
        self.resets[reason] += 1
        self._samples.clear()

    def observe(self, *, sim_ns, receive_mono_ns, feedback_velocity, reference_velocity,
                reference_position, now_mono_ns=None):
        """Feed one sample; returns the window dict on the call that completes it, else None."""
        self.observed += 1
        if (type(sim_ns) is not int or sim_ns <= 0 or type(receive_mono_ns) is not int
                or not all(_number(value) for value in
                           (feedback_velocity, reference_velocity, reference_position))):
            self._reset('INVALID_SAMPLE')
            return None
        if (abs(feedback_velocity) > limits.STOP_WINDOW_MAX_VELOCITY_RAD_S
                or abs(reference_velocity) > limits.STOP_WINDOW_MAX_VELOCITY_RAD_S):
            self._reset('VELOCITY')
            return None
        if self._samples:
            previous = self._samples[-1]
            if sim_ns - previous['sim_ns'] != limits.STOP_WINDOW_STEP_NS:
                self._reset('SIM_TIME_GAP')
            elif receive_mono_ns < previous['mono_ns']:
                self._reset('RECEIVED_TIME_REGRESSION')
            elif reference_position != self._samples[0]['reference_position']:
                self._reset('REFERENCE_CHANGED')
        self._samples.append(dict(sim_ns=sim_ns, mono_ns=receive_mono_ns,
                                  feedback_velocity=abs(feedback_velocity),
                                  reference_velocity=abs(reference_velocity),
                                  reference_position=reference_position))
        if self._completed is not None or len(self._samples) < limits.STOP_WINDOW_SAMPLES:
            return None
        now = receive_mono_ns if now_mono_ns is None else now_mono_ns
        oldest_age = now - self._samples[0]['mono_ns']
        if oldest_age > limits.STOP_WINDOW_MAX_AGE_NS:
            self._samples.popleft()
            return None
        # receive times are monotonic within the window, so the oldest sample is the oldest age
        self._completed = dict(
            n=len(self._samples), first_sim_ns=self._samples[0]['sim_ns'],
            last_sim_ns=self._samples[-1]['sim_ns'],
            max_abs_feedback_velocity=max(s['feedback_velocity'] for s in self._samples),
            max_abs_reference_velocity=max(s['reference_velocity'] for s in self._samples),
            reference_position=self._samples[0]['reference_position'],
            max_age_ns=oldest_age, completed_mono_ns=now)
        return dict(self._completed)
