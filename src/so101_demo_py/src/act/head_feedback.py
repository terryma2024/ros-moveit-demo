"""Original Head feedback clocks and ordered post-request stop confirmation.

These value objects carry explicit policy inputs. Loading a calibration policy or
an approved bundle is the entrypoint's responsibility; no defaults grant motion.
"""

from dataclasses import dataclass, asdict, InitVar, field
import math


def nanoseconds(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('HEAD_FEEDBACK_CLOCK_INVALID')
    return round(value * 1_000_000_000)


@dataclass(frozen=True)
class FeedbackPolicy:
    joint_max_receipt_age_s: float
    joint_max_source_age_s: float
    camera_interarrival_deadline_s: float
    camera_max_source_age_s: float
    clock_interarrival_deadline_s: float
    watchdog_period_s: float
    watchdog_reaction_limit_s: float
    revoker_connection_deadline_s: float
    simulation_policy: InitVar[object] = field(default=None, kw_only=True)

    def __post_init__(self, simulation_policy):
        if any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0
               for value in asdict(self).values()):
            raise ValueError('HEAD_FEEDBACK_POLICY_INVALID')
        bound = self._simulation(simulation_policy)
        if bound is None:
            if (self.watchdog_period_s != .002 or self.watchdog_reaction_limit_s != .010
                    or self.revoker_connection_deadline_s != .002):
                raise ValueError('HEAD_FEEDBACK_POLICY_SCHEDULING_INVALID')
        elif asdict(self) != bound.feedback_values():
            raise ValueError('HEAD_FEEDBACK_SIMULATION_BINDING_INVALID')
        object.__setattr__(self, '_bound_simulation_policy', bound)

    @staticmethod
    def _simulation(document):
        if document is None:
            return None
        from .head_simulation_policy import HeadSimulationPolicy
        return document if isinstance(document, HeadSimulationPolicy) else HeadSimulationPolicy.parse(document)

    @classmethod
    def parse(cls, values, *, simulation_policy=None):
        if isinstance(values, cls):
            if (simulation_policy is not None
                    and values._bound_simulation_policy != cls._simulation(simulation_policy)):
                raise ValueError('HEAD_FEEDBACK_SIMULATION_REBIND_REFUSED')
            return values
        names = set(cls.__dataclass_fields__) - {'simulation_policy'}
        if not isinstance(values, dict) or set(values) != names:
            raise ValueError('HEAD_FEEDBACK_POLICY_INVALID')
        return cls(**values, simulation_policy=simulation_policy)

    def check_joint(self, sample, decision):
        if sample is None or sample.get('valid') is not True:
            raise ValueError('HEAD_FEEDBACK_INVALID')
        receipt_age = nanoseconds(decision['wall_after_s']) - nanoseconds(sample['wall_s'])
        source_age = decision['sim_ns'] - sample['source_ns']
        # Compare integer clock ticks. Decimal seconds converted from original
        # ROS stamps must not introduce a float rounding allowance to the bound.
        if not 0 <= receipt_age <= math.floor(self.joint_max_receipt_age_s * 1e9):
            raise ValueError('HEAD_FEEDBACK_RECEIPT_STALE')
        if not 0 <= source_age <= math.floor(self.joint_max_source_age_s * 1e9):
            raise ValueError('HEAD_FEEDBACK_SOURCE_STALE')
        return dict(receipt_age_s=receipt_age*1e-9, source_age_s=source_age*1e-9)


def decision_clocks(node, monotonic):
    """Call after copying the original sample and releasing its cache lock."""
    before = monotonic()
    sim_ns = node.get_clock().now().nanoseconds
    after = monotonic()
    if (nanoseconds(after) < nanoseconds(before) or type(sim_ns) is not int or sim_ns <= 0):
        raise ValueError('HEAD_FEEDBACK_CLOCK_INVALID')
    return dict(wall_before_s=before, sim_ns=sim_ns, sim_s=sim_ns*1e-9, wall_after_s=after)


class OrderedStopConfirmation:
    """Consume originals in callback order; polling never adds a quiet sample."""

    def __init__(self, epoch):
        required = {'epoch', 'generation', 'request_wall_s', 'request_sim_s',
                    'fault_wall_s', 'stop_latency_s'}
        if not isinstance(epoch, dict) or set(epoch) != required:
            raise ValueError('HEAD_STOP_EPOCH_INVALID')
        if (type(epoch['epoch']) is not str or not epoch['epoch']
                or type(epoch['generation']) is not int or epoch['generation'] <= 0
                or epoch['stop_latency_s'] <= 0
                or nanoseconds(epoch['fault_wall_s']) > nanoseconds(epoch['request_wall_s'])):
            raise ValueError('HEAD_STOP_EPOCH_INVALID')
        for key in ('request_sim_s', 'request_wall_s', 'fault_wall_s', 'stop_latency_s'):
            nanoseconds(epoch[key])
        self.epoch = dict(epoch)
        self.count = 0
        self.last_sequence = 0
        self.last_source_ns = self.last_receipt_ns = None
        self.confirming_samples = []
        self.confirmed_at = None
        self.confirmation_inventory = None
        self.inventory_changed = False

    def observe(self, sample, decision, policy, velocity_limit):
        sequence = sample['sequence']
        if sequence <= self.last_sequence:
            return
        self.last_sequence = sequence
        try:
            policy.check_joint(sample, decision)
            source, receipt = sample['source_ns'], nanoseconds(sample['wall_s'])
            if (source <= nanoseconds(self.epoch['request_sim_s'])
                    or receipt <= nanoseconds(self.epoch['request_wall_s'])
                    or (self.last_source_ns is not None and source <= self.last_source_ns)
                    or (self.last_receipt_ns is not None and receipt <= self.last_receipt_ns)
                    or any(abs(value) > velocity_limit for value in sample['velocities'])):
                raise ValueError('HEAD_STOP_SAMPLE_INVALID')
        except (KeyError, TypeError, ValueError):
            self.count = 0
            self.confirming_samples.clear()
        else:
            self.count += 1
            self.confirming_samples.append(dict(sample, decision=dict(decision)))
            self.confirming_samples = self.confirming_samples[-3:]
        if sample.get('valid') is True:
            self.last_source_ns = sample['source_ns']
            self.last_receipt_ns = nanoseconds(sample['wall_s'])

    def within_deadline(self, decision):
        elapsed = nanoseconds(decision['wall_after_s']) - nanoseconds(self.epoch['fault_wall_s'])
        return 0 <= elapsed <= math.floor(self.epoch['stop_latency_s'] * 1e9)
