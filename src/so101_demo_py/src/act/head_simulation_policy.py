"""Explicit finite MuJoCo Head policy; parsing never grants motion authority."""

from dataclasses import asdict, dataclass
import math


@dataclass(frozen=True)
class HeadSimulationPolicy:
    schema_version: int
    mode: str
    heartbeat_rpc_timeout_s: float
    supervision_stale_s: float
    watchdog_period_s: float
    fault_reaction_limit_s: float
    native_close_timeout_s: float
    stop_confirmation_timeout_s: float
    perception_max_age_s: float
    perception_job_timeout_s: float
    camera_loss_timeout_s: float
    feedback_receipt_timeout_s: float
    joint_source_age_s: float
    camera_source_age_s: float
    search_timeout_s: float
    max_reobservations_per_stop: int
    max_reobservations_total: int

    def __post_init__(self):
        if (type(self.schema_version) is not int or self.schema_version != 1
                or type(self.mode) is not str or self.mode != 'mujoco_bounded_stop_search'):
            raise ValueError('HEAD_SIMULATION_POLICY_SCOPE_INVALID')
        ceilings = dict(heartbeat_rpc_timeout_s=1., supervision_stale_s=2.,
            watchdog_period_s=.1, fault_reaction_limit_s=.5, native_close_timeout_s=.25,
            stop_confirmation_timeout_s=3., perception_max_age_s=.15,
            perception_job_timeout_s=3., camera_loss_timeout_s=2.,
            feedback_receipt_timeout_s=1., joint_source_age_s=.1,
            camera_source_age_s=.3, search_timeout_s=120.)
        for name, ceiling in ceilings.items():
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= ceiling:
                raise ValueError('HEAD_SIMULATION_POLICY_BUDGET_INVALID')
        for name, ceiling in (('max_reobservations_per_stop', 10), ('max_reobservations_total', 40)):
            value = getattr(self, name)
            if type(value) is not int or not 0 < value <= ceiling:
                raise ValueError('HEAD_SIMULATION_POLICY_REOBSERVATION_INVALID')
        if not (
            self.watchdog_period_s < self.heartbeat_rpc_timeout_s < self.supervision_stale_s
            and self.fault_reaction_limit_s + self.native_close_timeout_s < self.stop_confirmation_timeout_s
            and self.feedback_receipt_timeout_s <= self.supervision_stale_s
            and self.camera_loss_timeout_s <= self.supervision_stale_s
            and self.perception_max_age_s <= self.perception_job_timeout_s
            and self.stop_confirmation_timeout_s < self.search_timeout_s
            and self.max_reobservations_per_stop <= self.max_reobservations_total
        ):
            raise ValueError('HEAD_SIMULATION_POLICY_RELATION_INVALID')

    @classmethod
    def parse(cls, document):
        if type(document) is not dict or set(document) != set(cls.__dataclass_fields__):
            raise ValueError('HEAD_SIMULATION_POLICY_DOCUMENT_INVALID')
        return cls(**document)

    @staticmethod
    def default_document():
        """An explicit candidate for calibration, never an approved fallback."""
        return dict(schema_version=1, mode='mujoco_bounded_stop_search',
            heartbeat_rpc_timeout_s=.25, supervision_stale_s=.5, watchdog_period_s=.02,
            fault_reaction_limit_s=.25, native_close_timeout_s=.05,
            stop_confirmation_timeout_s=1., perception_max_age_s=.15,
            perception_job_timeout_s=1., camera_loss_timeout_s=.5,
            feedback_receipt_timeout_s=.25, joint_source_age_s=.05,
            camera_source_age_s=.2, search_timeout_s=30.,
            max_reobservations_per_stop=3, max_reobservations_total=12)

    def readback(self):
        return asdict(self)

    def feedback_values(self):
        return dict(joint_max_receipt_age_s=self.feedback_receipt_timeout_s,
            joint_max_source_age_s=self.joint_source_age_s,
            camera_interarrival_deadline_s=self.camera_loss_timeout_s,
            camera_max_source_age_s=self.camera_source_age_s,
            clock_interarrival_deadline_s=self.feedback_receipt_timeout_s,
            watchdog_period_s=self.watchdog_period_s,
            watchdog_reaction_limit_s=self.fault_reaction_limit_s,
            revoker_connection_deadline_s=self.native_close_timeout_s)

    def validate_search_values(self, values):
        expected = dict(max_age_s=self.perception_max_age_s, search_timeout_s=self.search_timeout_s,
            stop_latency_s=self.stop_confirmation_timeout_s)
        if not isinstance(values, dict) or any(
            type(values.get(name)) not in (int, float) or values[name] != value
            for name, value in expected.items()
        ):
            raise ValueError('HEAD_SIMULATION_POLICY_EFFECTIVE_VALUE_MISMATCH')
