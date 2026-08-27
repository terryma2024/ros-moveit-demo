"""Stable wire models shared by the teleop service and its API."""

from __future__ import annotations

from enum import Enum
import math
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ServerMode(str, Enum):
    STARTING = "STARTING"
    READ_ONLY = "READ_ONLY"
    READY = "READY"
    BUSY = "BUSY"
    DEGRADED = "DEGRADED"


class StepFrame(str, Enum):
    WORLD = "WORLD"
    TOOL = "TOOL"


class BackendCapabilityMap(BaseModel):
    backend_probe: bool
    workflow_execute: bool
    workflow_start: bool
    workflow_run: bool
    workflow_resume: bool
    workflow_stop: bool
    reset_world: bool
    scene_operations: bool
    physical_observation: bool
    manual_joint_execute: bool
    manual_tcp_execute: bool
    camera_presets: bool
    task_batch: bool
    task_reachability: bool
    sensor_capture: bool
    task_environment_shutdown: bool


class BackendCapabilitiesResponse(BaseModel):
    simulation_only: bool
    bind_policy: str
    backend: Literal["gazebo_cpp", "gazebo_py", "mujoco_py"]
    owner_package: str
    owner_executable: str
    capabilities: BackendCapabilityMap


class Pose6D(BaseModel):
    frame_id: str
    tcp_frame: str
    x_m: float
    y_m: float
    z_m: float
    roll_rad: float
    pitch_rad: float
    yaw_rad: float


class JointSample(BaseModel):
    name: str
    position_rad: float
    velocity_rad_s: float = 0.0
    lower_limit_rad: Optional[float] = None
    upper_limit_rad: Optional[float] = None
    age_s: float = 0.0


class CollisionPair(BaseModel):
    source: str
    object_a: str
    object_b: str
    allowed: bool = False
    waypoint_index: Optional[int] = None
    depth_m: Optional[float] = None
    first_seen_at: Optional[float] = None
    last_seen_at: Optional[float] = None


class ValidationEvidence(BaseModel):
    passed: bool = False
    failure_code: Optional[str] = None
    measured: Dict[str, float] = Field(default_factory=dict)
    thresholds: Dict[str, float] = Field(default_factory=dict)
    contacts: List[CollisionPair] = Field(default_factory=list)
    sample_ages_s: Dict[str, float] = Field(default_factory=dict)


class PhysicalOutcomeEvidence(BaseModel):
    release_epoch_id: Optional[str] = None
    first_sequence: Optional[int] = None
    last_sequence: Optional[int] = None
    sample_count: int = 0
    duration_s: float = 0.0
    metrics: Dict[str, float] = Field(default_factory=dict)
    final_pose: Optional[Pose6D] = None
    intended_support_contact: Optional[bool] = None
    gripper_contact: Optional[bool] = None
    gazebo_attached: Optional[bool] = None
    moveit_attached: Optional[bool] = None
    world_object_synchronized: Optional[bool] = None
    primary_failure: Optional[str] = None


class OverrideAudit(BaseModel):
    command_id: str
    workflow_run_id: str
    state: str
    snapshot_revision: int
    failure_code: str
    evidence: ValidationEvidence
    operator_confirmation: str
    confirmed_at: float


class WorkflowSnapshot(BaseModel):
    run_id: Optional[str] = None
    current_state: str = "IDLE"
    last_completed_state: Optional[str] = None
    next_state: Optional[str] = None
    trace: List[str] = Field(default_factory=list)
    checkpoint_session_id: Optional[str] = None
    checkpoint_fresh: bool = False
    validation: Optional[ValidationEvidence] = None
    physical_outcome: Optional[PhysicalOutcomeEvidence] = None
    override_audit: List[OverrideAudit] = Field(default_factory=list)


class TelemetrySnapshot(BaseModel):
    sequence: int = 0
    server_timestamp: float = 0.0
    simulation_session_id: str = ""
    revision: int = 0
    mode: ServerMode = ServerMode.STARTING
    environment: Dict[str, str] = Field(default_factory=dict)
    source_ages_s: Dict[str, float] = Field(default_factory=dict)
    joints: Dict[str, JointSample] = Field(default_factory=dict)
    tcp: Optional[Pose6D] = None
    object_pose: Optional[Pose6D] = None
    controllers: Dict[str, str] = Field(default_factory=dict)
    gazebo_attached: Optional[bool] = None
    moveit_attached: Optional[bool] = None
    scene_revision: int = 0
    moveit_collisions: List[CollisionPair] = Field(default_factory=list)
    gazebo_contacts: List[CollisionPair] = Field(default_factory=list)
    real_time_factor: Optional[float] = None
    physical_outcome: Optional[PhysicalOutcomeEvidence] = None


class JointPlanRequest(BaseModel):
    target_joints_rad: Dict[str, float]
    command_id: str


class TcpPlanRequest(BaseModel):
    target: Pose6D
    command_id: str


class PlanSummary(BaseModel):
    plan_id: str
    start_fingerprint: str
    target_fingerprint: str
    scene_revision: int
    expires_at_monotonic: float
    trajectory_points: int = 0
    estimated_duration_s: float = 0.0
    max_joint_delta_rad: float = 0.0
    collisions: List[CollisionPair] = Field(default_factory=list)
    ik_solution_rad: Dict[str, float] = Field(default_factory=dict)


class CommandResult(BaseModel):
    command_id: str
    accepted: bool
    succeeded: bool
    code: str
    message: str
    layers: Dict[str, str] = Field(default_factory=dict)
    data: Dict[str, Any] = Field(default_factory=dict)
    snapshot_revision: Optional[int] = None
    validation: Optional[ValidationEvidence] = None


_SAFE_TASK_ID = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$"


class _StrictTaskModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaskPointModel(_StrictTaskModel):
    id: str = Field(pattern=_SAFE_TASK_ID)
    label: str = Field(min_length=1, max_length=120)
    cup_position_world_m: tuple[float, float, float]

    @field_validator("cup_position_world_m")
    @classmethod
    def finite_position(cls, value):
        if not all(math.isfinite(item) for item in value):
            raise ValueError("task point XYZ must be finite")
        return value


class TaskRunRequest(_StrictTaskModel):
    schema_version: Literal[1]
    points: List[TaskPointModel] = Field(min_length=1, max_length=100)
    session_id: str = Field(pattern=_SAFE_TASK_ID)
    lease_id: str = Field(min_length=1, max_length=120)
    command_id: str = Field(pattern=_SAFE_TASK_ID)

    @field_validator("points")
    @classmethod
    def unique_points(cls, value):
        if len({point.id for point in value}) != len(value):
            raise ValueError("task point IDs must be unique")
        return value


class TaskMutationRequest(_StrictTaskModel):
    session_id: str = Field(pattern=_SAFE_TASK_ID)
    lease_id: str = Field(min_length=1, max_length=120)
    command_id: str = Field(pattern=_SAFE_TASK_ID)


class TaskRecoveryRequest(TaskMutationRequest):
    action: Literal["stop", "reset-and-continue"]
    confirmation: str


class TaskShutdownRequest(TaskMutationRequest):
    confirmation: str


class TaskCaptureRequest(TaskMutationRequest):
    pass


class TaskPointSummary(_StrictTaskModel):
    id: str
    status: str
    failure_code: Optional[str] = None
    reachability_status: Optional[str] = None
    reset_epoch: Optional[int] = None
    artifact_ids: List[str] = Field(default_factory=list)


class TaskRunSummary(_StrictTaskModel):
    run_id: str
    status: str
    simulation_session_id: str
    points: List[TaskPointSummary] = Field(default_factory=list)
    first_shared_failure: Optional[str] = None


class ReachabilityResponse(_StrictTaskModel):
    status: str
    reports: List[Dict[str, Any]] = Field(default_factory=list)
    simulation_session_id: str


class TaskArtifactSummary(_StrictTaskModel):
    artifact_id: str = Field(pattern=r"^[a-f0-9]{24}$")
    name: str = Field(min_length=1, max_length=160)
    media_type: str = Field(min_length=1, max_length=100)
    byte_size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class CaptureResponse(_StrictTaskModel):
    capture_id: str
    status: str
    artifact_ids: List[str] = Field(default_factory=list)
    source_stamp_ns: Optional[int] = Field(default=None, ge=0)
    summary: Dict[str, Any] = Field(default_factory=dict)
    artifacts: List[TaskArtifactSummary] = Field(default_factory=list)


class RenderedImageRequest(TaskMutationRequest):
    source_artifact_id: str = Field(pattern=r"^[a-f0-9]{24}$")
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    png_base64: str = Field(min_length=1, max_length=14_000_000)
    view_matrix: tuple[float, ...]
    projection_matrix: tuple[float, ...]
    point_size: float = Field(gt=0, le=100)
    color_mode: Literal["rgb", "uniform"]
    background_rgb: tuple[float, float, float]
    viewport_px: tuple[int, int]
    original_point_count: int = Field(gt=0)
    displayed_point_count: int = Field(gt=0, le=400_000)
    sampling_rule: Literal["all", "fixed-stride"]
    sampling_stride: int = Field(ge=1)
    captured_at: str = Field(min_length=1, max_length=80)

    @field_validator("view_matrix", "projection_matrix")
    @classmethod
    def finite_matrix(cls, value):
        if len(value) != 16 or not all(math.isfinite(item) for item in value):
            raise ValueError("render matrices must contain 16 finite values")
        return value

    @field_validator("background_rgb")
    @classmethod
    def valid_background(cls, value):
        if not all(math.isfinite(item) and 0.0 <= item <= 1.0 for item in value):
            raise ValueError("background RGB values must be finite and within [0, 1]")
        return value

    @field_validator("viewport_px")
    @classmethod
    def valid_viewport(cls, value):
        if not all(0 < item <= 16384 for item in value):
            raise ValueError("viewport dimensions must be within [1, 16384]")
        return value


class TaskEvent(_StrictTaskModel):
    sequence: int = Field(ge=1)
    kind: str
    run_id: Optional[str] = None
    point_id: Optional[str] = None
    status: str
    failure_code: Optional[str] = None
