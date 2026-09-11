"""
Worker-local perception policy and durable pose admission.

The Broker supplies QUALIFIED candidates, never permission to move. The runtime
supplies frozen geometry/quality gates and a current lease/start authorization
check; these ports must return the literal True only after verification. Source
times and clock use the same simulation clock. No new thresholds are invented
here. One owning Worker creates one latch per execution workspace; recovery of
an existing POSE_ACCEPTED file requires coordinator adjudication, not replaying
motion through a new latch.
"""

from dataclasses import asdict, dataclass
import json
import math
from numbers import Real
import threading

from .artifacts import AttemptWorkspace, ValidationWorkspace
from .contracts import (
    _require_finite, _require_id, _require_positive_int, _require_sha256,
    AttemptStatus, ExecutionKind, InferenceRequest, ModelOutcome,
)


class PerceptionError(ValueError):
    """A perception sequencing or admission contract was violated."""


class PoseAdmissionCommitError(PerceptionError):
    """Visible acceptance evidence needs recovery adjudication, not motion."""


def _frame(name, value):
    if not isinstance(value, str) or not value.strip() or any(c.isspace() for c in value):
        raise PerceptionError(f'FRAME_ID: {name}')


def _vector(name, value, size):
    if (not isinstance(value, (tuple, list)) or len(value) != size
            or any(isinstance(v, bool) or not isinstance(v, Real)
                   or not math.isfinite(v) for v in value)):
        raise PerceptionError(f'FINITE_VECTOR: {name}')
    return tuple(float(v) for v in value)


@dataclass(frozen=True)
class AdmissionContext:
    """Trusted local reset/session/TF context and externally frozen tolerances."""

    session_id: str
    reset_completed_timestamp_s: float
    source_frame: str
    target_frame: str
    max_frame_age_s: float
    max_rgbd_skew_s: float
    max_tf_skew_s: float

    def __post_init__(self):
        _require_id('session_id', self.session_id)
        for name in ('source_frame', 'target_frame'):
            _frame(name, getattr(self, name))
        for name in ('reset_completed_timestamp_s', 'max_frame_age_s',
                     'max_rgbd_skew_s', 'max_tf_skew_s'):
            object.__setattr__(self, name, _require_finite(name, getattr(self, name)))


@dataclass(frozen=True)
class LocalizedPose:
    """Localized candidate with the complete echoed request and RGB-D/TF provenance."""

    request: InferenceRequest
    broker_generation: int
    session_id: str
    depth_timestamp_s: float
    depth_sha256: str
    tf_timestamp_s: float
    source_frame: str
    target_frame: str
    position_xyz: tuple
    orientation_xyzw: tuple

    def __post_init__(self):
        if type(self.request) is not InferenceRequest:
            raise PerceptionError('REQUEST_IDENTITY_REQUIRED')
        _require_positive_int('broker_generation', self.broker_generation)
        _require_id('session_id', self.session_id)
        _require_sha256('depth_sha256', self.depth_sha256)
        for name in ('depth_timestamp_s', 'tf_timestamp_s'):
            object.__setattr__(self, name, _require_finite(name, getattr(self, name)))
        for name in ('source_frame', 'target_frame'):
            _frame(name, getattr(self, name))
        object.__setattr__(self, 'position_xyz', _vector('position_xyz', self.position_xyz, 3))
        orientation = _vector('orientation_xyzw', self.orientation_xyzw, 4)
        if not any(orientation):
            raise PerceptionError('ZERO_QUATERNION')
        object.__setattr__(self, 'orientation_xyzw', orientation)


@dataclass(frozen=True)
class PerceptionDecision:
    """Next model or disposition; CANCELLED is audit-only, not a point outcome."""

    disposition: str
    next_model: str | None = None
    reason: str | None = None
    attempt_status: AttemptStatus | None = None


class PoseAdmissionLatch:
    """Only a successful local evidence write can open this latch."""

    def __init__(self, workspace, context, *, broker_generation, clock,
                 authorize, geometry_gate, quality_gate):
        """Bind an unopened latch to the current Worker execution workspace."""
        if type(workspace) not in (AttemptWorkspace, ValidationWorkspace):
            raise PerceptionError('WORKER_WORKSPACE_REQUIRED')
        if not isinstance(context, AdmissionContext):
            raise PerceptionError('ADMISSION_CONTEXT_REQUIRED')
        self.workspace, self.context = workspace, context
        self.broker_generation = _require_positive_int('broker_generation', broker_generation)
        self._clock, self._authorize = clock, authorize
        self._geometry_gate, self._quality_gate = geometry_gate, quality_gate
        self._lock = threading.RLock()
        self._expected = None
        self._accepted_document = None
        self._adjudication_required = False
        self._last_source_clock = None
        self._cancelled = set()
        self._fenced = False
        self.rejection_reason = None
        if (workspace.path / 'pose_accepted.json').exists():
            raise PerceptionError('POSE_ACCEPTED_REQUIRES_ADJUDICATION')

    @property
    def accepted(self):
        """Report historical durable acceptance, independent of topic publication."""
        with self._lock:
            return self._accepted_document is not None

    def _current(self, request):
        authorized = self._authorize(request)
        return (authorized is True and not self._fenced
                and request.request_id not in self._cancelled)

    @property
    def requires_adjudication(self):
        """Report whether a visible but unadmitted event blocks this latch."""
        with self._lock:
            return self._adjudication_required

    def check_result(self, request, broker_generation):
        """Check all echoed fields before interpreting even a MODEL_ERROR."""
        with self._lock:
            if type(request) is not InferenceRequest or request != self._expected:
                raise PerceptionError('REQUEST_IDENTITY_MISMATCH')
            current = self._current(request)
            # Authorization can block or observe a new Broker/request epoch.
            # Compare the complete identity again after the callback returns.
            if request != self._expected:
                raise PerceptionError('REQUEST_IDENTITY_MISMATCH')
            if (type(broker_generation) is not int
                    or broker_generation != self.broker_generation
                    or not current):
                self._cancelled.add(request.request_id)
                return False
            return True

    def expect(self, request, *, depth_timestamp_s, depth_sha256):
        """Register locally captured input identity before sending its model request."""
        with self._lock:
            if type(request) is not InferenceRequest:
                raise PerceptionError('REQUEST_IDENTITY_REQUIRED')
            identity = asdict(self.workspace.identity)
            kind = (ExecutionKind.ATTEMPT if type(self.workspace) is AttemptWorkspace
                    else ExecutionKind.VALIDATION)
            if (request.execution_kind is not kind
                    or any(getattr(request, key) != value for key, value in identity.items())
                    or request.reset_epoch != self.workspace._metadata['reset_epoch']):
                raise PerceptionError('WORKSPACE_IDENTITY_MISMATCH')
            suffix = self.workspace.path.parts[-4:]
            expected_path = '/'.join((request.worker_id, *suffix, 'perception/input/rgb.npy'))
            if request.input_relative_path != expected_path:
                raise PerceptionError('INPUT_PATH_IDENTITY_MISMATCH')
            if self.accepted or not self._current(request):
                raise PerceptionError('REQUEST_NOT_AUTHORIZED')
            _require_finite('depth_timestamp_s', depth_timestamp_s)
            _require_sha256('depth_sha256', depth_sha256)
            if not self._fresh(request.image_timestamp_s, depth_timestamp_s):
                raise PerceptionError('STALE_RGBD')
            self._expected = request
            self._depth_timestamp_s, self._depth_sha256 = depth_timestamp_s, depth_sha256

    def _fresh(self, rgb_stamp, depth_stamp, tf_stamp=None):
        context = self.context
        now = _require_finite('source_clock', self._clock())
        if self._last_source_clock is not None and now < self._last_source_clock:
            self._fenced = True
            return False
        self._last_source_clock = now
        stamps = (rgb_stamp, depth_stamp)
        if (any(stamp <= context.reset_completed_timestamp_s or stamp > now
                or now - stamp > context.max_frame_age_s for stamp in stamps)
                or abs(rgb_stamp - depth_stamp) > context.max_rgbd_skew_s):
            return False
        return (tf_stamp is None or (
            context.reset_completed_timestamp_s < tf_stamp <= now
            and all(abs(tf_stamp - stamp) <= context.max_tf_skew_s for stamp in stamps)))

    def _candidate_current(self, request, value, context):
        if not self.check_result(request, value.broker_generation):
            return self._reject('REQUEST_CANCELLED_OR_FENCED')
        fresh = self._fresh(request.image_timestamp_s, value.depth_timestamp_s,
                            value.tf_timestamp_s)
        identity = asdict(self.workspace.identity)
        kind = (ExecutionKind.ATTEMPT if type(self.workspace) is AttemptWorkspace
                else ExecutionKind.VALIDATION)
        # Read identity/context after both callbacks, including the source clock.
        if (request != self._expected or value.request != request
                or request.execution_kind is not kind
                or any(getattr(request, key) != item for key, item in identity.items())
                or request.reset_epoch != self.workspace._metadata['reset_epoch']
                or value.broker_generation != self.broker_generation
                or self._fenced or request.request_id in self._cancelled):
            return self._reject('REQUEST_CANCELLED_OR_FENCED')
        if (self.context != context or value.session_id != context.session_id
                or value.depth_timestamp_s != self._depth_timestamp_s
                or value.depth_sha256 != self._depth_sha256
                or value.source_frame != context.source_frame
                or value.target_frame != context.target_frame):
            return self._reject('SOURCE_OR_TF_IDENTITY_MISMATCH')
        return fresh or self._reject('STALE_RGBD_OR_TF')

    def _require_adjudication(self):
        self._adjudication_required = True
        self._fenced = True
        return PoseAdmissionCommitError('POSE_ACCEPTED_REQUIRES_ADJUDICATION')

    def accept(self, request, localized_pose):
        """
        Validate a candidate, persist POSE_ACCEPTED, then open the latch once.

        Filesystem or validator exceptions propagate without opening the latch;
        the Worker must stop and classify infrastructure failures separately.
        If an event is visible when commit verification fails, this latch is
        permanently fenced and the event requires recovery adjudication.
        A False return is an ordinary admission rejection. The immutable event
        is stored directly in working/ so its directory entry is synced by the
        artifact writer without introducing unsynced intermediate directories.
        """
        with self._lock:
            if self.requires_adjudication:
                raise self._require_adjudication()
            self.rejection_reason = None
            if (type(localized_pose) is not LocalizedPose
                    or type(request) is not InferenceRequest
                    or request != self._expected or localized_pose.request != request):
                return self._reject('POSE_REQUEST_IDENTITY_MISMATCH')
            if not self.check_result(request, localized_pose.broker_generation):
                return self._reject('REQUEST_CANCELLED_OR_FENCED')
            document = {'type': 'POSE_ACCEPTED', 'request': asdict(request),
                        'admission_context': asdict(self.context),
                        'localized_pose': asdict(localized_pose)}
            if self.accepted:
                return document == self._accepted_document
            context, value = self.context, localized_pose
            if not self._candidate_current(request, value, context):
                return False
            if (self._geometry_gate(request, value) is not True
                    or self._quality_gate(request, value) is not True):
                return self._reject('GEOMETRY_OR_QUALITY_REJECTED')
            # Validators, file writes and readback can all block. The same full
            # guard runs on both sides of the durable write. Motion separately
            # checks its current lease after successful admission.
            if not self._candidate_current(request, value, context):
                return False
            path = self.workspace.path / 'pose_accepted.json'
            if path.exists():
                raise self._require_adjudication()
            try:
                self.workspace.write_json('pose_accepted.json', document)
            except Exception:
                if path.exists():
                    self._require_adjudication()
                raise
            try:
                observed = json.loads(path.read_text())
                if (observed != json.loads(json.dumps(document))
                        or not self._candidate_current(request, value, context)):
                    raise self._require_adjudication()
            except Exception as error:
                raise self._require_adjudication() from error
            self._accepted_document = document
            return True

    def _reject(self, reason):
        self.rejection_reason = reason
        return False

    def fence(self):
        """Irreversibly prevent further admission for this Worker generation."""
        with self._lock:
            self._fenced = True

    def cancel(self, request):
        """Exclude a cancelled request from any later pose admission."""
        with self._lock:
            if request != self._expected:
                raise PerceptionError('REQUEST_IDENTITY_MISMATCH')
            self._cancelled.add(request.request_id)


class PerceptionPolicy:
    """Enforce one YOLO stage followed by at most one permitted fallback."""

    def __init__(self, latch, *, yolo_model_id, grounded_model_id):
        """Start with YOLO only; model names come from the frozen runtime profile."""
        _require_id('yolo_model_id', yolo_model_id)
        _require_id('grounded_model_id', grounded_model_id)
        if yolo_model_id == grounded_model_id:
            raise PerceptionError('DISTINCT_MODEL_IDS_REQUIRED')
        self.latch = latch
        self._models = {'yolo': yolo_model_id, 'grounded': grounded_model_id}
        self._outcomes = {'yolo': None, 'grounded': None}
        self._pending = None
        self._awaiting_admission = False
        self._lock = threading.RLock()

    @property
    def decision(self):
        """Return the current externally observable next step."""
        with self._lock:
            value = decide(self._outcomes['yolo'], self._outcomes['grounded'], latch=self.latch)
            if self._pending is not None and not self._awaiting_admission:
                return PerceptionDecision('WAIT_RESULT')
            if value.next_model:
                return PerceptionDecision(value.disposition, self._models[value.next_model])
            return value

    def start_request(self, request, *, depth_timestamp_s, depth_sha256):
        """Permit exactly one request for the next eligible model stage."""
        with self._lock:
            if self._pending is not None or self.decision.next_model != request.model_id:
                raise PerceptionError('MODEL_SEQUENCE')
            self.latch.expect(request, depth_timestamp_s=depth_timestamp_s,
                              depth_sha256=depth_sha256)
            self._pending = request

    def record_result(self, request, outcome, *, broker_generation, localized_pose=None):
        """Attribute a model result before classification or local admission."""
        with self._lock:
            if not isinstance(outcome, ModelOutcome):
                raise PerceptionError('MODEL_OUTCOME_REQUIRED')
            if request != self._pending or self._awaiting_admission:
                raise PerceptionError('REQUEST_IDENTITY_OR_SEQUENCE_MISMATCH')
            if not self.latch.check_result(request, broker_generation):
                outcome = ModelOutcome.CANCELLED
            if outcome is ModelOutcome.CANCELLED:
                self.latch.cancel(request)
            stage = self._stage(request)
            self._outcomes[stage] = outcome
            if outcome is ModelOutcome.QUALIFIED:
                self._awaiting_admission = True
                if localized_pose is not None:
                    return self.admit_pose(request, localized_pose)
            else:
                self._pending = None
            return self.decision

    def _stage(self, request):
        return 'yolo' if request.model_id == self._models['yolo'] else 'grounded'

    def admit_pose(self, request, localized_pose):
        """Treat local admission rejection as this model's NORMAL_REJECTION."""
        with self._lock:
            if self.latch.requires_adjudication:
                raise PoseAdmissionCommitError('POSE_ACCEPTED_REQUIRES_ADJUDICATION')
            if request != self._pending or not self._awaiting_admission:
                raise PerceptionError('POSE_ADMISSION_SEQUENCE')
            if not self.latch.check_result(request, localized_pose.broker_generation):
                outcome = ModelOutcome.CANCELLED
            else:
                try:
                    accepted = self.latch.accept(request, localized_pose)
                except Exception:
                    if self.latch.requires_adjudication:
                        self._outcomes[self._stage(request)] = ModelOutcome.INFRA_ERROR
                        self._pending = None
                        self._awaiting_admission = False
                    raise
                if accepted:
                    outcome = ModelOutcome.QUALIFIED
                elif not self.latch.check_result(request, localized_pose.broker_generation):
                    outcome = ModelOutcome.CANCELLED
                else:
                    outcome = ModelOutcome.NORMAL_REJECTION
            self._outcomes[self._stage(request)] = outcome
            self._pending = None
            self._awaiting_admission = False
            return self.decision


def decide(yolo=None, grounded=None, *, latch):
    """Classify effective model outcomes using the local admission latch."""
    if not isinstance(latch, PoseAdmissionLatch):
        raise PerceptionError('LOCAL_ADMISSION_LATCH_REQUIRED')
    for outcome in (yolo, grounded):
        if outcome is not None and not isinstance(outcome, ModelOutcome):
            raise PerceptionError('MODEL_OUTCOME_REQUIRED')
    if latch.requires_adjudication:
        return PerceptionDecision('INVALID', reason='PERCEPTION_INFRA_ERROR',
                                  attempt_status=AttemptStatus.INVALID)
    if latch.accepted:
        return PerceptionDecision('CONTINUE')
    for outcome in (yolo, grounded):
        if outcome in (ModelOutcome.INFRA_ERROR, ModelOutcome.QUEUE_TIMEOUT,
                       ModelOutcome.INFERENCE_TIMEOUT):
            return PerceptionDecision('INVALID', reason=f'PERCEPTION_{outcome.value}',
                                      attempt_status=AttemptStatus.INVALID)
    if ModelOutcome.CANCELLED in (yolo, grounded):
        return PerceptionDecision('CANCELLED', reason='PERCEPTION_CANCELLED')
    fallback = (ModelOutcome.NORMAL_REJECTION, ModelOutcome.MODEL_ERROR)
    if grounded is not None and yolo not in fallback:
        raise PerceptionError('MODEL_SEQUENCE')
    if yolo is None:
        return PerceptionDecision('REQUEST_MODEL', 'yolo')
    if ModelOutcome.QUALIFIED in (yolo, grounded):
        return PerceptionDecision('ADMIT_POSE')
    if grounded is None:
        return PerceptionDecision('REQUEST_MODEL', 'grounded')
    reason = ('PERCEPTION_MODEL_ERROR' if ModelOutcome.MODEL_ERROR in (yolo, grounded)
              else 'PERCEPTION_NO_POSE')
    return PerceptionDecision('FAILED', reason=reason, attempt_status=AttemptStatus.FAILED)
