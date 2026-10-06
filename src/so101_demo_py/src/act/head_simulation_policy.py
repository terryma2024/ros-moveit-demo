"""Explicit finite MuJoCo Head policy; parsing never grants motion authority."""

from dataclasses import asdict, dataclass
import math
import re

from .head_feedback import nanoseconds


@dataclass(frozen=True)
class HeadSimulationPolicy:
    schema_version: int
    mode: str
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
        if (type(self.schema_version) is not int or self.schema_version != 2
                or type(self.mode) is not str or self.mode != 'mujoco_bounded_stop_search_file_v1'):
            raise ValueError('HEAD_SIMULATION_POLICY_SCOPE_INVALID')
        ceilings = dict(watchdog_period_s=.1, fault_reaction_limit_s=.5, native_close_timeout_s=.25,
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
            self.watchdog_period_s < self.fault_reaction_limit_s
            and self.fault_reaction_limit_s + self.native_close_timeout_s < self.stop_confirmation_timeout_s
            and self.feedback_receipt_timeout_s <= self.stop_confirmation_timeout_s
            and self.camera_loss_timeout_s <= self.stop_confirmation_timeout_s
            and self.perception_max_age_s <= self.perception_job_timeout_s
            and self.perception_job_timeout_s <= self.stop_confirmation_timeout_s
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
        return dict(schema_version=2, mode='mujoco_bounded_stop_search_file_v1',
            watchdog_period_s=.02,
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
            # Shared feedback ABI name: in file policy this is the local native-close budget.
            revoker_connection_deadline_s=self.native_close_timeout_s)

    def validate_search_values(self, values):
        expected = dict(max_age_s=self.perception_max_age_s, search_timeout_s=self.search_timeout_s,
            stop_latency_s=self.stop_confirmation_timeout_s)
        if not isinstance(values, dict) or any(
            type(values.get(name)) not in (int, float) or values[name] != value
            for name, value in expected.items()
        ):
            raise ValueError('HEAD_SIMULATION_POLICY_EFFECTIVE_VALUE_MISMATCH')


def validate_stopped_observation_request(request, *, policy, expected_scope, now_wall_s):
    """Freeze a stopped acquisition request; this proves no physical settlement."""
    from .head_evidence_identity import canonical_bytes, digest
    scope={'epoch','generation','session_id','policy_sha256'}
    keys=scope|{'schema_version','simulation_policy_sha256','motion_epoch','observation_sequence',
        'settled_source_floor_ns','settled_wall_s','requested_wall_s','search_deadline_ns'}
    if (type(policy) is not HeadSimulationPolicy or type(request) is not dict or set(request)!=keys
            or type(expected_scope) is not dict or set(expected_scope)!=scope
            or type(request['schema_version']) is not int or request['schema_version']!=1):
        raise ValueError('HEAD_STOPPED_OBSERVATION_REQUEST_INVALID')
    owned=dict(request)
    for key in ('epoch','session_id'):
        if type(owned[key]) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',owned[key]) is None:
            raise ValueError('HEAD_STOPPED_OBSERVATION_SCOPE_INVALID')
    for key in ('policy_sha256','simulation_policy_sha256'):
        if type(owned[key]) is not str or re.fullmatch(r'[0-9a-f]{64}',owned[key]) is None:
            raise ValueError('HEAD_STOPPED_OBSERVATION_SCOPE_INVALID')
    for key in ('generation','observation_sequence','settled_source_floor_ns','search_deadline_ns'):
        if type(owned[key]) is not int or not 0<owned[key]<2**64:
            raise ValueError('HEAD_STOPPED_OBSERVATION_SCOPE_INVALID')
    if (type(owned['motion_epoch']) is not int or not 0<=owned['motion_epoch']<2**64
            or canonical_bytes({key:owned[key] for key in scope})!=canonical_bytes(expected_scope)
            or owned['simulation_policy_sha256']!=digest(policy.readback())):
        raise ValueError('HEAD_STOPPED_OBSERVATION_SCOPE_INVALID')
    settled=nanoseconds(owned['settled_wall_s']);requested=nanoseconds(owned['requested_wall_s'])
    now=nanoseconds(now_wall_s);deadline=owned['search_deadline_ns']
    if not settled<=requested<=now<deadline<=requested+nanoseconds(policy.search_timeout_s):
        raise ValueError('HEAD_STOPPED_OBSERVATION_CLOCK_INVALID')
    return owned


class BoundedObservationBudget:
    """Finite recoverable observations share one original monotonic search cap."""
    def __init__(self,policy,*,started_wall_s):
        if type(policy) is not HeadSimulationPolicy:
            raise ValueError('HEAD_REOBSERVATION_POLICY_INVALID')
        started=nanoseconds(started_wall_s)
        self.policy=policy;self._started_ns=started;self._last_ns=started
        self._deadline_ns=started+nanoseconds(policy.search_timeout_s)
        self._total=0;self._per_stop={}

    def reobserve(self,stop_id,reason,now_wall_s):
        if (type(stop_id) is not int or not 0<=stop_id<2**64
                or type(reason) is not str or reason not in ('MISS','EXPIRED','SHORT_DROP')):
            raise ValueError('HEAD_REOBSERVATION_EVENT_INVALID')
        now=nanoseconds(now_wall_s)
        if now<self._last_ns:raise ValueError('HEAD_REOBSERVATION_CLOCK_INVALID')
        self._last_ns=now
        count=self._per_stop.get(stop_id,0)
        if (now>=self._deadline_ns or count>=self.policy.max_reobservations_per_stop
                or self._total>=self.policy.max_reobservations_total):return False
        self._total+=1;self._per_stop[stop_id]=count+1
        return True

    def readback(self):
        return dict(started_wall_ns=self._started_ns,search_deadline_ns=self._deadline_ns,
            reobservations_total=self._total,per_stop=dict(self._per_stop))
