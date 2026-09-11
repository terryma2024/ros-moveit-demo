"""Deterministic multistart IK and sampled Cartesian-path validation."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Protocol, Sequence

from ...core.domain import State
from ...ports.evidence import PoseEvidence


class PoseIk(Protocol):
    def solve(
        self,
        target: PoseEvidence,
        seed: tuple[float, ...],
        *,
        position_tolerance_m: float,
        orientation_tolerance_rad: float,
    ) -> tuple[float, ...]: ...

    def forward(self, positions: Sequence[float]) -> PoseEvidence: ...

    def orientation_error_rad(self, actual: PoseEvidence, target: PoseEvidence) -> float: ...


@dataclass(frozen=True, slots=True)
class SeedCandidate:
    source: str
    source_index: int
    positions_rad: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class HorizonWaypoint:
    state: State
    segment_index: int
    target: PoseEvidence


@dataclass(frozen=True, slots=True)
class CandidateReceipt:
    state: str
    segment_index: int
    seed_source: str
    seed_index: int
    seed_positions_rad: tuple[float, ...]
    accepted: bool
    joint_positions_rad: tuple[float, ...] | None
    position_error_m: float | None
    orientation_error_rad: float | None
    joint_margin_rad: float | None
    continuity_rad: float | None
    minimum_clearance_z_m: float | None
    maximum_corridor_deviation_m: float | None
    score: float | None
    failure_code: str | None

    def to_document(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HorizonStep:
    waypoint: HorizonWaypoint
    receipt: CandidateReceipt


@dataclass(frozen=True, slots=True)
class HorizonPath:
    steps: tuple[HorizonStep, ...]
    cumulative_score: float


@dataclass(frozen=True, slots=True)
class HorizonResult:
    paths: tuple[HorizonPath, ...]
    candidate_receipts: tuple[CandidateReceipt, ...]

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "algorithm": "deterministic_bounded_multistart_beam_search",
            "candidate_receipts": [item.to_document() for item in self.candidate_receipts],
            "selected_paths": [
                {
                    "cumulative_score": path.cumulative_score,
                    "steps": [step.receipt.to_document() for step in path.steps],
                }
                for path in self.paths
            ],
        }


@dataclass(frozen=True, slots=True)
class CartesianCorridorReceipt:
    accepted: bool
    sample_count: int
    maximum_deviation_m: float
    maximum_orientation_error_rad: float
    minimum_clearance_z_m: float
    failure_code: str | None

    def to_document(self) -> dict[str, object]:
        return asdict(self)


_STRUCTURED_BASE_YAW_OFFSETS = (-0.30, -0.15, 0.15, 0.30)
MOVE_ABOVE_PLAN_CANDIDATE_COUNT = 4
MOVE_ABOVE_CARTESIAN_SEGMENT_COUNT = 6
_FROZEN_SEED_BANK = (
    (-0.45, 0.0, 0.0, 0.0, -0.45),
    (-0.30, 0.30, 0.0, 1.20, -0.30),
    (-0.20, 0.30, 0.0, 1.20, -0.20),
    (-0.10, 0.30, 0.0, 1.20, -0.10),
    (0.00, 0.30, 0.0, 1.20, 0.00),
    (0.10, 0.30, 0.0, 1.20, 0.10),
    (0.20, 0.30, 0.0, 1.20, 0.20),
    (0.30, 0.30, 0.0, 1.20, 0.30),
    (0.45, 0.0, 0.0, 0.0, 0.45),
)


def _finite_positions(values: Sequence[float]) -> tuple[float, ...]:
    result = tuple(float(value) for value in values)
    if len(result) != 5 or any(not math.isfinite(value) for value in result):
        raise ValueError("DETERMINISTIC_HORIZON_SEED_INVALID")
    return result


def deterministic_seed_candidates(
    current_state: Sequence[float], prior_stage: Sequence[float]
) -> tuple[SeedCandidate, ...]:
    """Build the fixed, bounded seed sequence used by every planning surface."""

    current = _finite_positions(current_state)
    prior = _finite_positions(prior_stage)
    raw: list[tuple[str, tuple[float, ...]]] = [
        ("current_state", current),
        ("prior_stage", prior),
    ]
    for offset in _STRUCTURED_BASE_YAW_OFFSETS:
        structured = list(prior)
        structured[0] += offset
        structured[4] += offset
        raw.append(("structured_base_yaw", tuple(structured)))
    raw.extend(("frozen_seed_bank", seed) for seed in _FROZEN_SEED_BANK)

    seen: set[tuple[float, ...]] = set()
    candidates: list[SeedCandidate] = []
    source_indexes: dict[str, int] = {}
    for source, positions in raw:
        positions = _finite_positions(positions)
        index = source_indexes.get(source, 0)
        source_indexes[source] = index + 1
        key = tuple(round(value, 12) for value in positions)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(SeedCandidate(source, index, positions))
    return tuple(candidates)


def _point_to_segment_distance(
    point: Sequence[float], start: Sequence[float], end: Sequence[float]
) -> float:
    delta = tuple(b - a for a, b in zip(start, end, strict=True))
    length_squared = sum(value * value for value in delta)
    if length_squared <= 1e-18:
        return math.dist(point, start)
    progress = (
        sum(
            (value - origin) * direction
            for value, origin, direction in zip(point, start, delta, strict=True)
        )
        / length_squared
    )
    progress = min(1.0, max(0.0, progress))
    projected = tuple(origin + progress * direction for origin, direction in zip(start, delta))
    return math.dist(point, projected)


def _segment_progress(
    point: Sequence[float], start: Sequence[float], end: Sequence[float]
) -> float:
    delta = tuple(b - a for a, b in zip(start, end, strict=True))
    length_squared = sum(value * value for value in delta)
    if length_squared <= 1e-18:
        return 1.0
    return min(
        1.0,
        max(
            0.0,
            sum(
                (value - origin) * direction
                for value, origin, direction in zip(point, start, delta, strict=True)
            )
            / length_squared,
        ),
    )


def _interpolate_orientation(
    start: tuple[float, ...], target: tuple[float, ...], fraction: float
) -> tuple[float, ...]:
    target_values = target
    if sum(a * b for a, b in zip(start, target, strict=True)) < 0.0:
        target_values = tuple(-value for value in target)
    values = tuple(a + fraction * (b - a) for a, b in zip(start, target_values, strict=True))
    norm = math.sqrt(sum(value * value for value in values))
    return tuple(value / norm for value in values)


def interpolated_move_above_waypoints(
    ik: PoseIk,
    start_joint_positions: Sequence[float],
    target: PoseEvidence,
    *,
    segment_count: int = MOVE_ABOVE_CARTESIAN_SEGMENT_COUNT,
) -> tuple[HorizonWaypoint, ...]:
    """Bound the long approach with deterministic Cartesian pose waypoints."""

    if segment_count < 1:
        raise ValueError("MOVE_ABOVE_SEGMENT_COUNT_INVALID")
    start_pose = ik.forward(_finite_positions(start_joint_positions))
    waypoints = []
    for index in range(1, segment_count + 1):
        fraction = index / segment_count
        position = tuple(
            start + fraction * (end - start)
            for start, end in zip(
                start_pose.position_m, target.position_m, strict=True
            )
        )
        orientation = _interpolate_orientation(
            start_pose.orientation_xyzw,
            target.orientation_xyzw,
            fraction,
        )
        waypoints.append(
            HorizonWaypoint(
                State.MOVE_ABOVE_OBJECT,
                index,
                PoseEvidence(position, orientation),
            )
        )
    return tuple(waypoints)


def _joint_margin(ik: PoseIk, joints: tuple[float, ...]) -> float:
    limits = getattr(ik, "joint_limits", ())
    if not limits:
        return 1.0
    return min(
        min(value - lower, upper - value)
        for value, (lower, upper) in zip(joints, limits, strict=True)
    )


def _kinematic_segment_metrics(
    ik: PoseIk, start_joints: tuple[float, ...], end_joints: tuple[float, ...]
) -> tuple[float, float]:
    start_pose = ik.forward(start_joints)
    end_pose = ik.forward(end_joints)
    maximum_deviation = 0.0
    minimum_clearance = math.inf
    for index in range(9):
        fraction = index / 8.0
        joints = tuple(
            start + fraction * (end - start)
            for start, end in zip(start_joints, end_joints, strict=True)
        )
        pose = ik.forward(joints)
        maximum_deviation = max(
            maximum_deviation,
            _point_to_segment_distance(pose.position_m, start_pose.position_m, end_pose.position_m),
        )
        minimum_clearance = min(minimum_clearance, pose.position_m[2])
    return maximum_deviation, minimum_clearance


def solve_horizon(
    ik: PoseIk,
    waypoints: tuple[HorizonWaypoint, ...],
    current_state: Sequence[float],
    *,
    position_tolerance_m: float,
    orientation_tolerance_rad: float,
    beam_width: int = 3,
) -> HorizonResult:
    """Solve and score a complete waypoint prefix before admitting its first move."""

    if not waypoints or beam_width < 1:
        raise ValueError("DETERMINISTIC_HORIZON_ARGUMENT_INVALID")
    initial = _finite_positions(current_state)
    beam: list[tuple[float, tuple[HorizonStep, ...], tuple[float, ...]]] = [(0.0, (), initial)]
    all_receipts: list[CandidateReceipt] = []

    for waypoint in waypoints:
        expanded: list[tuple[float, tuple[HorizonStep, ...], tuple[float, ...]]] = []
        solution_keys: set[tuple[float, ...]] = set()
        for prior_score, prior_steps, prior_joints in beam:
            candidates = deterministic_seed_candidates(initial, prior_joints)
            for candidate in candidates:
                try:
                    joints = tuple(
                        float(value)
                        for value in ik.solve(
                            waypoint.target,
                            candidate.positions_rad,
                            position_tolerance_m=position_tolerance_m,
                            orientation_tolerance_rad=orientation_tolerance_rad,
                        )
                    )
                    actual = ik.forward(joints)
                    position_error = math.dist(actual.position_m, waypoint.target.position_m)
                    orientation_error = ik.orientation_error_rad(actual, waypoint.target)
                    margin = _joint_margin(ik, joints)
                    continuity = math.dist(joints, prior_joints)
                    corridor, clearance = _kinematic_segment_metrics(ik, prior_joints, joints)
                    local_score = (
                        position_error / position_tolerance_m
                        + orientation_error / orientation_tolerance_rad
                        + 0.08 * continuity
                        + 0.02 / max(0.01, margin + 0.01)
                        + 2.0 * corridor
                    )
                    score = prior_score + local_score
                    receipt = CandidateReceipt(
                        waypoint.state.value,
                        waypoint.segment_index,
                        candidate.source,
                        candidate.source_index,
                        candidate.positions_rad,
                        True,
                        joints,
                        position_error,
                        orientation_error,
                        margin,
                        continuity,
                        clearance,
                        corridor,
                        score,
                        None,
                    )
                except Exception as error:  # each bounded seed produces an auditable rejection
                    code = str(error).split(":", 1)[0] or type(error).__name__
                    receipt = CandidateReceipt(
                        waypoint.state.value,
                        waypoint.segment_index,
                        candidate.source,
                        candidate.source_index,
                        candidate.positions_rad,
                        False,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        code,
                    )
                    all_receipts.append(receipt)
                    continue
                all_receipts.append(receipt)
                key = tuple(round(value, 7) for value in joints)
                if key in solution_keys:
                    continue
                solution_keys.add(key)
                expanded.append((score, prior_steps + (HorizonStep(waypoint, receipt),), joints))

        expanded.sort(
            key=lambda item: (
                item[0],
                item[1][-1].receipt.seed_source,
                item[1][-1].receipt.seed_index,
                item[2],
            )
        )
        beam = expanded[:beam_width]
        if not beam:
            break

    paths = tuple(
        HorizonPath(steps, score) for score, steps, _joints in beam if len(steps) == len(waypoints)
    )
    return HorizonResult(paths, tuple(all_receipts))


def validate_cartesian_corridor(
    ik: PoseIk,
    trajectory: object,
    planning_joint_names: Sequence[str],
    start_joint_positions: Sequence[float],
    target: PoseEvidence,
    *,
    maximum_deviation_m: float,
    orientation_tolerance_rad: float,
    minimum_clearance_z_m: float,
) -> CartesianCorridorReceipt:
    """Validate actual MoveIt trajectory samples in TCP space, never endpoints alone."""

    start_joints = _finite_positions(start_joint_positions)
    joint_trajectory = trajectory.joint_trajectory
    names = tuple(joint_trajectory.joint_names)
    indexes = tuple(names.index(name) for name in planning_joint_names)
    samples = [
        tuple(float(point.positions[index]) for index in indexes)
        for point in joint_trajectory.points
    ]
    if not samples or math.dist(samples[0], start_joints) > 1e-9:
        samples.insert(0, start_joints)
    start_pose = ik.forward(start_joints)
    poses = [ik.forward(sample) for sample in samples]
    maximum_deviation = max(
        _point_to_segment_distance(pose.position_m, start_pose.position_m, target.position_m)
        for pose in poses
    )
    maximum_orientation_error = max(
        ik.orientation_error_rad(
            pose,
            PoseEvidence(
                tuple(
                    start + progress * (end - start)
                    for start, end in zip(start_pose.position_m, target.position_m, strict=True)
                ),
                _interpolate_orientation(
                    start_pose.orientation_xyzw,
                    target.orientation_xyzw,
                    progress,
                ),
            ),
        )
        for pose in poses
        for progress in (
            _segment_progress(pose.position_m, start_pose.position_m, target.position_m),
        )
    )
    minimum_clearance = min(pose.position_m[2] for pose in poses)

    failure_code = None
    if maximum_deviation > maximum_deviation_m:
        failure_code = "CARTESIAN_CORRIDOR_DEVIATION"
    elif maximum_orientation_error > orientation_tolerance_rad:
        failure_code = "CARTESIAN_CORRIDOR_ORIENTATION"
    elif minimum_clearance < minimum_clearance_z_m:
        failure_code = "CARTESIAN_CORRIDOR_CLEARANCE"
    return CartesianCorridorReceipt(
        failure_code is None,
        len(samples),
        maximum_deviation,
        maximum_orientation_error,
        minimum_clearance,
        failure_code,
    )


def cartesian_candidate_score(
    receipt: CartesianCorridorReceipt,
    *,
    candidate_index: int,
) -> tuple[float, float, int, int]:
    """Rank accepted MoveIt candidates without changing corridor tolerances."""

    if not receipt.accepted:
        raise ValueError("only accepted Cartesian corridors can be scored")
    return (
        receipt.maximum_orientation_error_rad,
        receipt.maximum_deviation_m,
        receipt.sample_count,
        candidate_index,
    )
