"""Stable wire models shared by the teleop service and its API."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ServerMode(str, Enum):
    STARTING = "STARTING"
    READ_ONLY = "READ_ONLY"
    READY = "READY"
    BUSY = "BUSY"
    DEGRADED = "DEGRADED"


class StepFrame(str, Enum):
    WORLD = "WORLD"
    TOOL = "TOOL"


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
    override_audit: List[OverrideAudit] = Field(default_factory=list)


class TelemetrySnapshot(BaseModel):
    sequence: int = 0
    server_timestamp: float = 0.0
    simulation_session_id: str = ""
    revision: int = 0
    mode: ServerMode = ServerMode.STARTING
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
