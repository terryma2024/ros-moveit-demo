"""Bounded immutable derivative-rich Head trajectory preparation and collision gate.

This is deliberately separate from the shared ACT position-only converter.  A
guard is bound once to one local dispatcher, simulation reset, model, geometry
document and controller feedback port.  Prepared values are capabilities only
for that exact guard and exact original CDR byte string.
"""

from __future__ import annotations

from dataclasses import dataclass
import copy
import hashlib
import json
import math
import threading
import time
from types import MappingProxyType
import uuid

import mujoco
import numpy as np
from control_msgs.action import FollowJointTrajectory
from rclpy.serialization import deserialize_message, serialize_message
from rosidl_runtime_py.convert import message_to_ordereddict
from trajectory_msgs.msg import JointTrajectoryPoint

from so101_demo.act.head_evidence_identity import canonical_bytes
from so101_demo.act import head_neck_limits as limits
from so101_demo.act.head_feedback import nanoseconds
from .physics import model_sha256
from .pick_place_neck_sweep import MujocoNeckSweepChecker


_QUIET_VELOCITY = limits.QUIET_VELOCITY_RAD_S
_MAX_VELOCITY = limits.MAX_VELOCITY_RAD_S
_MAX_ACCELERATION = limits.MAX_ACCELERATION_RAD_S2
_MIN_DURATION_NS = limits.MIN_DURATION_NS
_MAX_DURATION_NS = limits.MAX_DURATION_NS
_LEAD_NS = limits.HEADER_LEAD_NS
_MIN_FIRST_OFFSET_NS = limits.MIN_FIRST_OFFSET_NS
_MAX_FIRST_OFFSET_NS = limits.MAX_FIRST_OFFSET_NS
_PATH_STEP_S = limits.PATH_STEP_S
_CLEARANCE_M = limits.CLEARANCE_M
_MAX_SAMPLES = limits.MAX_SAMPLES
# Retain the original angular collision resolution as motion limits increase.
_PATH_MAX_SPACING_MOTION_RAD = limits.PATH_MAX_SPACING_MOTION_RAD
_PREFIX_MAX_SPACING_MOTION_RAD = limits.PREFIX_MAX_SPACING_MOTION_RAD


def check_dispatch_against_controller_state(proof, sample, *, current_ros_ns, now_mono_ns):
    """Approximate, before dispatch, what the broker checked at the consuming tick (design section 2).

    The broker refused a goal whose first point had already passed, whose header led the first point by
    more than 14 ms, or whose measured first-update state (|v| <= 0.04136, |dq| <= 0.002) was not close
    to the first point. The stock controller does none of that, so the owner checks the latest
    ``controller_state`` sample here instead. A sample is at most 200 ms old and finite.
    """
    if sample is None:
        raise PermissionError("HEAD_TRAJECTORY_CONTROLLER_STATE_MISSING")
    position, velocity = sample.get("feedback_position"), sample.get("feedback_velocity")
    if not all(type(value) in (int, float) and math.isfinite(value) for value in (position, velocity)):
        raise PermissionError("HEAD_TRAJECTORY_CONTROLLER_STATE_NON_FINITE")
    age_ns = now_mono_ns - sample["receive_mono_ns"]
    if not 0 <= age_ns <= limits.STOP_WINDOW_MAX_AGE_NS:
        raise PermissionError("HEAD_TRAJECTORY_CONTROLLER_STATE_STALE")
    if abs(velocity) > limits.QUIET_VELOCITY_RAD_S:
        raise PermissionError("HEAD_TRAJECTORY_CONTROLLER_PREFIX_VELOCITY")
    first_position = proof["typed_curve"]["positions_rad"][0]
    if abs(position - first_position) > limits.MEASURED_POSITION_MISMATCH_RAD:
        raise PermissionError("HEAD_TRAJECTORY_CONTROLLER_PREFIX_MISMATCH")
    first_offset = proof["first_point_offset_ns"]
    remaining_ns = proof["header_stamp_ns"] + first_offset - current_ros_ns
    if remaining_ns <= limits.STOP_WINDOW_STEP_NS:
        raise PermissionError("HEAD_TRAJECTORY_GOAL_LATE")
    if remaining_ns > first_offset + limits.CONSUMING_TICK_ALLOWANCE_NS:
        raise PermissionError("HEAD_TRAJECTORY_HEADER_LEAD")


@dataclass(frozen=True, slots=True)
class PreparedHeadTrajectory:
    """Immutable CDR and canonical provenance issued by one guard instance."""

    _owner: object
    _nonce: str
    original_cdr: bytes
    proof_bytes: bytes

    @property
    def proof(self) -> dict:
        return json.loads(self.proof_bytes)


def _finite(value: object, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"HEAD_TRAJECTORY_{name}_INVALID")
    return float(value)


def _stamp_ns(message) -> int:
    stamp = message.trajectory.header.stamp
    return int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)


def _set_time(message, ns: int) -> None:
    message.sec, message.nanosec = divmod(ns, 1_000_000_000)


def _point_ns(point) -> int:
    return int(point.time_from_start.sec) * 1_000_000_000 + int(point.time_from_start.nanosec)


def _freeze_json(value):
    if type(value) is dict:
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze_json(item) for item in value)
    return value


def _quintic_coefficients(q0: float, v0: float, a0: float,
                          q1: float, v1: float, a1: float, duration_s: float):
    """Return power coefficients in normalized time for quintic Hermite data."""
    t = _finite(duration_s, "DURATION")
    if t <= 0:
        raise ValueError("HEAD_TRAJECTORY_DURATION_INVALID")
    q0, v0, a0, q1, v1, a1 = (_finite(x, "POINT") for x in (q0, v0, a0, q1, v1, a1))
    c0, c1, c2 = q0, v0 * t, 0.5 * a0 * t * t
    d = q1 - (c0 + c1 + c2)
    e = v1 * t - (c1 + 2 * c2)
    f = a1 * t * t - 2 * c2
    c3 = 10 * d - 4 * e + 0.5 * f
    c4 = -15 * d + 7 * e - f
    c5 = 6 * d - 3 * e + 0.5 * f
    return np.asarray((c0, c1, c2, c3, c4, c5), dtype=np.float64)


def _real_roots_inside(coefficients, low=0.0, high=1.0):
    coefficients = np.asarray(coefficients, dtype=np.float64)
    last = len(coefficients) - 1
    while last > 0 and coefficients[last] == 0:
        last -= 1
    if last == 0:
        return ()
    roots = np.roots(coefficients[:last + 1][::-1])
    return tuple(float(root.real) for root in roots
                 if abs(float(root.imag)) <= 1e-10 and low < root.real < high)


def quintic_extrema(q0: float, v0: float, a0: float,
                    q1: float, v1: float, a1: float, duration_s: float) -> dict:
    """Exact polynomial candidates for position, velocity and acceleration extrema."""
    t = _finite(duration_s, "DURATION")
    coefficients = _quintic_coefficients(q0, v0, a0, q1, v1, a1, t)
    d1 = np.arange(1, 6, dtype=np.float64) * coefficients[1:] / t
    d2 = np.arange(1, 5, dtype=np.float64) * d1[1:] / t
    d3 = np.arange(1, 4, dtype=np.float64) * d2[1:] / t

    def values(poly, points):
        return tuple(float(np.polynomial.polynomial.polyval(x, poly)) for x in points)

    p_candidates = (0.0, 1.0, *_real_roots_inside(d1))
    v_candidates = (0.0, 1.0, *_real_roots_inside(d2))
    a_candidates = (0.0, 1.0, *_real_roots_inside(d3))
    return {
        "position": values(coefficients, p_candidates),
        "velocity": values(d1, v_candidates),
        "acceleration": values(d2, a_candidates),
        "candidate_s": {"position": p_candidates, "velocity": v_candidates,
                         "acceleration": a_candidates},
    }


@dataclass(frozen=True, slots=True)
class _Snapshot:
    scope: bytes
    scene_session: str
    reset_epoch: int
    model_sha256: str
    qpos: tuple[float, ...]
    qvel: tuple[float, ...]
    neck_position: float
    neck_velocity: float
    scene_received_wall_ns: int
    scene_source_time_ns: int
    feedback_source_ns: int
    feedback_wall_ns: int
    decision_sim_ns: int
    decision_wall_ns: int


class HeadTrajectoryGuard:
    """Prepare one safe quintic against current full-state and immutable bounds.

    Constructor inputs are explicit: an already-warmed independent MuJoCo
    checker, the same feedback-aware port used for dispatch, a live
    SceneStateObserver, the active reset identity, and the original sealed
    head-camera geometry document. ``prepare(target_rad)`` selects a safe
    duration, checks the measured-prefix envelope and quintic at 2 ms, then
    seals one ROS goal. The fixed .004 s header lead and original local search
    deadline are never refreshed.
    """

    def __init__(self, *, checker: MujocoNeckSweepChecker, feedback_port,
                 scene_observer, node, model_xml_path, geometry_path,
                 geometry_sha256: str,
                 simulation_session_id: str, reset_epoch: int,
                 monotonic=time.monotonic, expected_mujoco_version="3.12.0",
                 controller_state_source=None):
        if controller_state_source is not None and not callable(controller_state_source):
            raise ValueError("HEAD_TRAJECTORY_SOURCE_INVALID")
        self.controller_state_source = controller_state_source
        if type(checker) is not MujocoNeckSweepChecker:
            raise ValueError("HEAD_TRAJECTORY_CHECKER_INVALID")
        if (mujoco.mj_versionString() != expected_mujoco_version
                or checker.model.opt.timestep != 0.002
                or checker.model_sha256 != scene_observer.model_sha256
                or checker.step_s != _PATH_STEP_S or checker.clearance_m != _CLEARANCE_M
                or checker.max_samples != _MAX_SAMPLES or checker.allowed
                or checker.names.count(None)):
            raise ValueError("HEAD_TRAJECTORY_MODEL_OR_POLICY_INVALID")
        if (not callable(monotonic) or not callable(getattr(feedback_port, "feedback_snapshot", None))
                or not callable(getattr(scene_observer, "snapshot_with_receipt", None))
                or not callable(getattr(node, "get_clock", None))):
            raise ValueError("HEAD_TRAJECTORY_SOURCE_INVALID")
        if type(simulation_session_id) is not str or not simulation_session_id:
            raise ValueError("HEAD_TRAJECTORY_RESET_INVALID")
        if type(reset_epoch) is not int or reset_epoch <= 0:
            raise ValueError("HEAD_TRAJECTORY_RESET_INVALID")
        from pathlib import Path
        xml_path = Path(model_xml_path)
        if not xml_path.is_absolute() or not xml_path.is_file():
            raise ValueError("HEAD_TRAJECTORY_MODEL_XML_INVALID")
        xml_sha = hashlib.sha256(xml_path.read_bytes()).hexdigest()
        # The shared sweep checker inflates geom_margin after recording its
        # pristine semantic hash. Compare the unmodified XML load to that
        # original hash; never rehash or relabel its private inflated model.
        pristine_model = mujoco.MjModel.from_xml_path(str(xml_path))
        if model_sha256(pristine_model) != checker.model_sha256:
            raise ValueError("HEAD_TRAJECTORY_MODEL_SEMANTIC_SHA_INVALID")
        base_body = mujoco.mj_name2id(pristine_model, mujoco.mjtObj.mjOBJ_BODY, "base")
        if base_body < 1:
            raise ValueError("HEAD_TRAJECTORY_PROTECTED_MASK_INVALID")
        expected_names = tuple(mujoco.mj_id2name(
            pristine_model, mujoco.mjtObj.mjOBJ_GEOM, index)
            for index in range(pristine_model.ngeom))
        expected_protected = set()
        for geom in range(pristine_model.ngeom):
            body = int(pristine_model.geom_bodyid[geom])
            while body > 0 and body != base_body:
                body = int(pristine_model.body_parentid[body])
            if body == base_body:
                expected_protected.add(geom)
        if (checker.names != expected_names
                or checker.protected != frozenset(expected_protected)
                or checker.allowed != set()
                or not np.all(np.isfinite(checker.model.geom_margin))
                or np.any(checker.model.geom_margin < _CLEARANCE_M)):
            raise ValueError("HEAD_TRAJECTORY_PROTECTED_MASK_INVALID")
        self._bound_protected = frozenset(expected_protected)
        self._bound_geom_names = expected_names
        self._bound_allowed_pairs = frozenset()
        self._bound_geom_margins = tuple(float(value) for value in checker.model.geom_margin)
        self._bound_checker_limits = (checker.step_s, checker.clearance_m,
                                      checker.max_samples, int(checker.neck_qpos))
        path = Path(geometry_path)
        if not path.is_absolute() or not path.is_file():
            raise ValueError("HEAD_TRAJECTORY_GEOMETRY_INVALID")
        raw = path.read_bytes()
        actual_geometry_sha = hashlib.sha256(raw).hexdigest()
        if actual_geometry_sha != geometry_sha256:
            raise ValueError("HEAD_TRAJECTORY_GEOMETRY_DIGEST_INVALID")
        document = json.loads(raw)
        if (document.get("schema_version") != 1
                or document.get("camera_name") != "head_camera"
                or document.get("source_digests", {}).get("scene_sha256") is None):
            raise ValueError("HEAD_TRAJECTORY_GEOMETRY_INVALID")
        interval = document.get("lock_valid_neck_rad")
        search = document.get("required_search_domain_rad")
        if (type(interval) is not list or len(interval) != 2
                or type(search) is not list or len(search) != 2):
            raise ValueError("HEAD_TRAJECTORY_GEOMETRY_INVALID")
        self.safe_interval = tuple(_finite(x, "GEOMETRY_BOUND") for x in interval)
        self.search_domain = tuple(_finite(x, "SEARCH_BOUND") for x in search)
        if not (self.safe_interval[0] < self.safe_interval[1]
                and self.safe_interval[0] <= self.search_domain[0] < self.search_domain[1]
                <= self.safe_interval[1]):
            raise ValueError("HEAD_TRAJECTORY_GEOMETRY_INVALID")
        self.geometry_sha256 = actual_geometry_sha
        self.geometry_scene_sha256 = document["source_digests"]["scene_sha256"]
        if self.geometry_scene_sha256 != xml_sha:
            raise ValueError("HEAD_TRAJECTORY_GEOMETRY_SCENE_SHA_INVALID")
        self.model_xml_sha256 = xml_sha
        self.model_semantic_sha256 = checker.model_sha256
        self.checker, self.feedback_port = checker, feedback_port
        self.scene_observer, self.node = scene_observer, node
        self.simulation_session_id, self.reset_epoch = simulation_session_id, reset_epoch
        self.monotonic = monotonic
        self._neck_qpos = int(checker.neck_qpos)
        self._model = checker.model
        self._data = mujoco.MjData(self._model)
        self._owner = object()
        self._lock = threading.Lock()
        self._issued: dict[str, tuple] = {}
        self._dispatcher = None
        self._local_state = None
        self._stopped = False
        self._admission_scene = None
        self._admission_required = False

    def bind_dispatcher(self, dispatcher, local_state) -> None:
        """Bind once to the actual Head inventory owner; arbitrary callables refuse."""
        from .head_inventory_dispatch import HeadInventoryDispatcher
        from so101_demo.act.head_local_state import HeadLocalState
        if type(dispatcher) is not HeadInventoryDispatcher or type(local_state) is not HeadLocalState:
            raise ValueError("HEAD_TRAJECTORY_DISPATCH_BINDING_INVALID")
        bound_guard = getattr(dispatcher, "_guard", None)
        if (dispatcher.local_state is not local_state or dispatcher.port is not self.feedback_port
                or getattr(bound_guard, "__self__", None) is not self
                or getattr(bound_guard, "__func__", None) is not type(self).is_current):
            raise ValueError("HEAD_TRAJECTORY_DISPATCH_BINDING_INVALID")
        with self._lock:
            if self._dispatcher is not None or self._stopped:
                raise PermissionError("HEAD_TRAJECTORY_GUARD_ALREADY_BOUND")
            self._dispatcher, self._local_state = dispatcher, local_state
        from .head_local_runtime import HeadLocalRuntime
        self._admission_required = type(getattr(dispatcher._own, '__self__', None)) is HeadLocalRuntime

    def _require_admission(self, *, check_scene=False):
        if self._admission_scene is None:
            if self._admission_required:
                raise PermissionError('HEAD_ADMISSION_LEASE_REQUIRED')
            return None
        return self._admission_scene._require_lease(self, check_scene=check_scene)

    def stop(self) -> None:
        """Revoke future admissions without taking ROS, cache or MuJoCo locks."""
        with self._lock:
            self._stopped = True

    def _scope_bytes(self) -> bytes:
        if self._local_state is None:
            raise PermissionError("HEAD_TRAJECTORY_GUARD_UNBOUND")
        if not self._local_state.controller_bound:
            raise PermissionError('HEAD_LOCAL_CONTROLLER_UNBOUND')
        # HeadLocalState seals this canonical document at construction. Read
        # those owner-held bytes directly so claim-boundary revalidation does
        # not decode/re-encode JSON merely to compare the same scope.
        scope = getattr(self._local_state, "_scope_json", None)
        if type(scope) is not bytes:
            raise PermissionError("HEAD_TRAJECTORY_SCOPE_INVALID")
        return scope

    def _capture(self) -> tuple[_Snapshot, dict, dict]:
        self._require_admission(check_scene=True)
        if self._stopped or self._dispatcher is None:
            raise PermissionError("HEAD_TRAJECTORY_GUARD_REVOKED")
        scope = self._scope_bytes()
        feedback = copy.deepcopy(self.feedback_port.feedback_snapshot())
        scene, received = self.scene_observer.snapshot_with_receipt()
        scene = copy.deepcopy(scene)
        decision = dict(feedback.get("decision", {}))
        sample = feedback
        policy = getattr(self.feedback_port, "feedback_policy", None)
        if (policy is None or policy.joint_max_source_age_s != 0.05
                or policy.joint_max_receipt_age_s != 0.25
                or sample.get("valid") is not True):
            raise PermissionError("HEAD_TRAJECTORY_FEEDBACK_POLICY_INVALID")
        qpos = tuple(float(value) for value in scene["qpos"])
        qvel = tuple(float(value) for value in scene["qvel"])
        if (len(qpos) != self._model.nq or len(qvel) != self._model.nv
                or not all(math.isfinite(value) for value in (*qpos, *qvel))
                or scene["model_sha256"] != self.checker.model_sha256
                or scene["simulation_session_id"] != self.simulation_session_id
                or scene["reset_epoch"] != self.reset_epoch):
            raise PermissionError("HEAD_TRAJECTORY_SCENE_IDENTITY_INVALID")
        sim_ns = decision.get("sim_ns")
        source_ns = sample.get("source_ns")
        receipt_s = sample.get("wall_s")
        if (type(sim_ns) is not int or sim_ns <= 0 or type(source_ns) is not int
                or source_ns <= 0 or receipt_s is None):
            raise PermissionError("HEAD_TRAJECTORY_FEEDBACK_CLOCK_INVALID")
        neck_position = _finite(sample["positions"][0], "FEEDBACK_POSITION")
        neck_velocity = _finite(sample["velocities"][0], "FEEDBACK_VELOCITY")
        if (abs(neck_velocity) > _QUIET_VELOCITY
                or abs(qpos[self._neck_qpos] - neck_position) > limits.MEASURED_POSITION_MISMATCH_RAD):
            raise PermissionError("HEAD_TRAJECTORY_MEASURED_ANCHOR_INVALID")
        now_wall_ns = nanoseconds(self.monotonic())
        scene_received_ns = nanoseconds(received)
        scene_end = scene["clock_interval_end_monotonic_ns"]
        scene_begin = scene["clock_interval_begin_monotonic_ns"]
        scene_source_ns = nanoseconds(scene["simulation_time_s"])
        scene_max_ns = math.floor(self.scene_observer.max_age * 1e9)
        if (not type(scene_begin) is int or not type(scene_end) is int
                or not 0 < scene_begin <= scene_end <= now_wall_ns
                or not 0 <= now_wall_ns - scene_received_ns <= scene_max_ns
                or not 0 <= now_wall_ns - scene_end <= scene_max_ns
                or not 0 <= sim_ns - scene_source_ns <= math.floor(self.scene_observer.max_age * 1e9)):
            raise PermissionError("HEAD_TRAJECTORY_SCENE_CLOCK_INVALID")
        local = self._local_state
        if now_wall_ns >= local.search_deadline_ns:
            raise PermissionError("HEAD_TRAJECTORY_SEARCH_DEADLINE_EXPIRED")
        state = _Snapshot(scope=scope, scene_session=scene["simulation_session_id"],
            reset_epoch=scene["reset_epoch"], model_sha256=scene["model_sha256"],
            qpos=qpos, qvel=qvel, neck_position=neck_position,
            neck_velocity=neck_velocity, scene_received_wall_ns=scene_received_ns,
            scene_source_time_ns=scene_source_ns, feedback_source_ns=source_ns,
            feedback_wall_ns=nanoseconds(receipt_s), decision_sim_ns=sim_ns,
            decision_wall_ns=nanoseconds(decision["wall_after_s"]))
        return state, sample, scene

    def _check_physical_path(self, snapshot: _Snapshot, target: float,
                             duration_ns: int, *, first_offset_ns=None) -> dict:
        if first_offset_ns is None:
            first_offset_ns = self._prefix_offset_ns(
                snapshot.qpos[self._neck_qpos] - snapshot.neck_position,
                snapshot.neck_velocity)
        offset_s = first_offset_ns * 1e-9
        duration_s = duration_ns * 1e-9
        first = snapshot.neck_position
        delta = target - first
        envelope_radius = (limits.MEASURED_POSITION_MISMATCH_RAD
                           + limits.PREFIX_ENVELOPE_VELOCITY_FACTOR * _QUIET_VELOCITY
                           * (offset_s + limits.CONSUMING_TICK_ALLOWANCE_S))
        low, high = first - envelope_radius, first + envelope_radius
        if low < self.safe_interval[0] or high > self.safe_interval[1]:
            raise PermissionError("HEAD_TRAJECTORY_PREFIX_OUTSIDE_GEOMETRY")
        envelope_intervals = max(1, math.ceil(
            (high - low) / _PREFIX_MAX_SPACING_MOTION_RAD))
        main_intervals = max(1, math.ceil(duration_s / _PATH_STEP_S),
                             math.ceil(1.875 * abs(delta) / _PATH_MAX_SPACING_MOTION_RAD))
        sample_count = envelope_intervals + 1 + main_intervals + 1
        if sample_count > _MAX_SAMPLES:
            raise PermissionError("HEAD_TRAJECTORY_SAMPLE_BUDGET")
        main = quintic_extrema(first, 0.0, 0.0, target, 0.0, 0.0, duration_s)
        if (min(main["position"]) < self.safe_interval[0]
                or max(main["position"]) > self.safe_interval[1]
                or max(abs(value) for value in main["velocity"]) > _MAX_VELOCITY
                or max(abs(value) for value in main["acceleration"]) > _MAX_ACCELERATION):
            raise PermissionError("HEAD_TRAJECTORY_CONTINUOUS_LIMIT")
        intervals = np.linspace(low, high, envelope_intervals + 1, dtype=np.float64)
        envelope_checks = 0
        main_checks = 0

        for value in intervals:
            self._check_collision_pose(snapshot.qpos, float(value)); envelope_checks += 1
        for index in range(main_intervals + 1):
            s = index / main_intervals
            position = first + delta * (10*s**3 - 15*s**4 + 6*s**5)
            self._check_collision_pose(snapshot.qpos, position); main_checks += 1
        return {"safe": True, "model_sha256": self.checker.model_sha256,
                "scene_xml_sha256": self.geometry_scene_sha256,
                "path_step_s": _PATH_STEP_S, "clearance_m": _CLEARANCE_M,
                "prefix_envelope_rad": [low, high],
                "prefix_time_step_s": _PATH_STEP_S,
                "prefix_max_velocity_rad_s": _MAX_VELOCITY,
                "prefix_max_sample_spacing_rad": _PREFIX_MAX_SPACING_MOTION_RAD,
                "prefix_sample_spacing_rad": (high - low) / envelope_intervals,
                "prefix_envelope_samples": envelope_checks,
                "main_samples": main_checks, "sample_count": sample_count,
                "main_extrema": main}

    def _check_collision_pose(self, qpos, neck_position: float) -> None:
        """Replay one full observed qpos in the private, margin-inflated model."""
        self._require_admission()
        self._require_collision_policy()
        if len(qpos) != self._model.nq or not all(math.isfinite(float(value)) for value in qpos):
            raise PermissionError("HEAD_TRAJECTORY_FULL_STATE_INVALID")
        self._data.qpos[:] = qpos
        self._data.qpos[self._neck_qpos] = _finite(neck_position, "COLLISION_POSITION")
        mujoco.mj_fwdPosition(self._model, self._data)
        # Native views avoid constructing one Python contact wrapper per row.
        # Keep unknown geometry and protected contacts in their original order
        # so the first refusal remains the same as the scalar traversal.
        geometry = self._data.contact.geom
        invalid = np.any((geometry < 0) | (geometry >= self._model.ngeom), axis=1)
        selected = invalid.copy()
        valid = ~invalid
        protected = np.zeros(self._model.ngeom, dtype=np.bool_)
        protected[list(self._bound_protected)] = True
        selected[valid] = (protected[geometry[valid, 0]] |
                           protected[geometry[valid, 1]])
        distances = self._data.contact.dist
        for index in np.flatnonzero(selected):
            if invalid[index]:
                raise PermissionError("HEAD_TRAJECTORY_CONTACT_GEOMETRY_UNKNOWN")
            a, b = (int(value) for value in geometry[index])
            pair = tuple(sorted((self._bound_geom_names[a], self._bound_geom_names[b])))
            distance = float(distances[index])
            if (not math.isfinite(distance) or distance <= _CLEARANCE_M
                    and pair not in self._bound_allowed_pairs):
                raise PermissionError("HEAD_TRAJECTORY_PROTECTED_CONTACT")

    def _require_collision_policy(self) -> None:
        if (self.checker.model is not self._model
                or self.checker.names != self._bound_geom_names
                or self.checker.protected != self._bound_protected
                or frozenset(self.checker.allowed) != self._bound_allowed_pairs
                or (self.checker.step_s, self.checker.clearance_m,
                    self.checker.max_samples, int(self.checker.neck_qpos))
                    != self._bound_checker_limits
                or not np.array_equal(self._model.geom_margin, self._bound_geom_margins)):
            raise PermissionError("HEAD_TRAJECTORY_COLLISION_POLICY_MUTATED")

    @staticmethod
    def _prefix_offset_ns(position_mismatch_rad: float, velocity_rad_s: float) -> int:
        mismatch = _finite(position_mismatch_rad, "PREFIX_POSITION")
        velocity = _finite(velocity_rad_s, "PREFIX_VELOCITY")
        if abs(mismatch) > limits.MEASURED_POSITION_MISMATCH_RAD or abs(velocity) > _QUIET_VELOCITY:
            raise PermissionError("HEAD_TRAJECTORY_MEASURED_ANCHOR_INVALID")
        # Reserve the native first-update timing allowance and a small pose
        # margin. The native guard independently checks its actual measured
        # prefix; this estimate never grants permission to bypass that check.
        drift = abs(velocity) * limits.CONSUMING_TICK_ALLOWANCE_S + 0.000002
        for offset_ns in range(_MIN_FIRST_OFFSET_NS, _MAX_FIRST_OFFSET_NS + 1, 10_000_000):
            remaining = offset_ns * 1e-9 - limits.CONSUMING_TICK_ALLOWANCE_S
            bounded = True
            for position in (mismatch - drift, mismatch + drift):
                extrema = quintic_extrema(position, velocity, 0., 0., 0., 0., remaining)
                bounded &= (max(abs(v) for v in extrema["velocity"]) <= 0.9 * _MAX_VELOCITY
                            and max(abs(a) for a in extrema["acceleration"]) <= 0.9 * _MAX_ACCELERATION)
            if bounded:
                return offset_ns
        raise PermissionError("HEAD_TRAJECTORY_PREFIX_DURATION_LIMIT")

    @staticmethod
    def _duration_ns(delta: float) -> int:
        distance = abs(delta)
        required = max(_MIN_DURATION_NS,
            math.ceil((1.875 * distance / _MAX_VELOCITY) * 1e9),
            math.ceil(math.sqrt(5.773502691896258 * distance / _MAX_ACCELERATION) * 1e9))
        duration_ns = required
        while duration_ns <= _MAX_DURATION_NS:
            t = duration_ns * 1e-9
            if (1.875 * distance / t <= _MAX_VELOCITY
                    and 5.773502691896258 * distance / (t*t) <= _MAX_ACCELERATION):
                return duration_ns
            duration_ns += 1
        raise PermissionError("HEAD_TRAJECTORY_DURATION_LIMIT")

    def _validate_goal_curve(self, goal: FollowJointTrajectory.Goal) -> dict:
        trajectory = goal.trajectory
        if (tuple(trajectory.joint_names) != ("neck_yaw_joint",)
                or len(trajectory.points) != 2):
            raise PermissionError("HEAD_TRAJECTORY_TYPED_SHAPE_INVALID")
        points = tuple(trajectory.points)
        rows = []
        times = []
        for point in points:
            if (len(point.positions) != 1 or len(point.velocities) != 1
                    or len(point.accelerations) != 1):
                raise PermissionError("HEAD_TRAJECTORY_TYPED_DERIVATIVES_REQUIRED")
            if len(point.effort) != 0:
                raise PermissionError("HEAD_TRAJECTORY_TYPED_DERIVATIVES_REQUIRED")
            rows.append(tuple(_finite(values[0], "TYPED_POINT") for values in
                              (point.positions, point.velocities, point.accelerations)))
            times.append(_point_ns(point))
        q0, v0, a0 = rows[0]
        q1, v1, a1 = rows[1]
        if (not _MIN_FIRST_OFFSET_NS <= times[0] <= _MAX_FIRST_OFFSET_NS or times[1] <= times[0]
                or times[1] > _MAX_DURATION_NS
                or times[1] - times[0] < _MIN_DURATION_NS
                or (v0, a0, v1, a1) != (0.0, 0.0, 0.0, 0.0)
                or not self.safe_interval[0] <= q0 <= self.safe_interval[1]
                or not self.safe_interval[0] <= q1 <= self.safe_interval[1]):
            raise PermissionError("HEAD_TRAJECTORY_TYPED_TIMING_OR_BOUNDS_INVALID")
        extrema = quintic_extrema(q0, v0, a0, q1, v1, a1,
                                  (times[1] - times[0]) * 1e-9)
        velocities, accelerations = extrema["velocity"], extrema["acceleration"]
        delta = q1 - q0
        if (min(extrema["position"]) < self.safe_interval[0]
                or max(extrema["position"]) > self.safe_interval[1]
                or max(abs(value) for value in velocities) > _MAX_VELOCITY
                or max(abs(value) for value in accelerations) > _MAX_ACCELERATION
                or (delta > 0 and min(velocities) < -1e-12)
                or (delta < 0 and max(velocities) > 1e-12)):
            raise PermissionError("HEAD_TRAJECTORY_CONTINUOUS_LIMIT")
        return {"positions_rad": [q0, q1], "velocities_rad_s": [v0, v1],
                "accelerations_rad_s2": [a0, a1], "times_from_start_ns": times,
                "extrema": extrema}

    def prepare(self, target_rad: float) -> PreparedHeadTrajectory:
        """Prepare one sealed rich two-point neck goal from fresh measured state."""
        admission = self._require_admission(check_scene=True)
        target = _finite(target_rad, "TARGET")
        if not self.safe_interval[0] <= target <= self.safe_interval[1]:
            raise PermissionError("HEAD_TRAJECTORY_TARGET_OUTSIDE_GEOMETRY")
        before, _, _ = self._capture()
        first_offset_ns = self._prefix_offset_ns(
            before.qpos[self._neck_qpos] - before.neck_position, before.neck_velocity)
        duration_ns = self._duration_ns(target - before.neck_position)
        if first_offset_ns + duration_ns > _MAX_DURATION_NS:
            raise PermissionError("HEAD_TRAJECTORY_TOTAL_DURATION_LIMIT")
        wall_now_ns = nanoseconds(self.monotonic())
        endpoint_offset_ns = first_offset_ns + duration_ns
        if (wall_now_ns + _LEAD_NS + endpoint_offset_ns
                > self._local_state.search_deadline_ns):
            raise PermissionError("HEAD_TRAJECTORY_SEARCH_DEADLINE_TOO_SHORT")
        collision = self._check_physical_path(before, target, duration_ns,
                                              first_offset_ns=first_offset_ns)
        after, _, _ = self._capture()
        if (after.scope != before.scope or after.scene_session != before.scene_session
                or after.reset_epoch != before.reset_epoch
                or after.model_sha256 != before.model_sha256
                or after.qpos != before.qpos or after.qvel != before.qvel
                or after.neck_position != before.neck_position
                or after.neck_velocity != before.neck_velocity):
            raise PermissionError("HEAD_TRAJECTORY_STATE_CHANGED_DURING_CHECK")
        # Final source clock/stamp is chosen only after all model work. The
        # serialized header is never refreshed if later admission expires.
        decision = self.node.get_clock().now().nanoseconds
        if type(decision) is not int or decision <= 0:
            raise PermissionError("HEAD_TRAJECTORY_ROS_CLOCK_INVALID")
        header_ns = decision + _LEAD_NS
        goal = FollowJointTrajectory.Goal()
        trajectory = goal.trajectory
        trajectory.joint_names = ["neck_yaw_joint"]
        _set_time(trajectory.header.stamp, header_ns)
        first = JointTrajectoryPoint()
        first.positions = [before.neck_position]
        first.velocities = [0.0]
        first.accelerations = [0.0]
        _set_time(first.time_from_start, first_offset_ns)
        trajectory.points.append(first)
        terminal = JointTrajectoryPoint()
        terminal.positions = [target]
        terminal.velocities = [0.0]
        terminal.accelerations = [0.0]
        _set_time(terminal.time_from_start, first_offset_ns + duration_ns)
        trajectory.points.append(terminal)
        typed_curve = self._validate_goal_curve(goal)
        serialized = serialize_message(goal)
        typed = message_to_ordereddict(goal)
        typed_bytes = canonical_bytes(typed)
        now_after_ns = nanoseconds(self.monotonic())
        current_ros_ns = self.node.get_clock().now().nanoseconds
        if (type(current_ros_ns) is not int or current_ros_ns <= 0
                or not self._deadline_fits(
                    self._local_state.search_deadline_ns, header_ns, endpoint_offset_ns,
                    current_ros_ns, now_after_ns)):
            raise PermissionError("HEAD_TRAJECTORY_SEARCH_DEADLINE_TOO_SHORT")
        if (now_after_ns >= self._local_state.search_deadline_ns
                or header_ns - decision != _LEAD_NS
                or _stamp_ns(goal) != header_ns
                or _point_ns(trajectory.points[0]) != first_offset_ns
                or _point_ns(trajectory.points[-1]) > _MAX_DURATION_NS):
            raise PermissionError("HEAD_TRAJECTORY_FINAL_CLOCK_INVALID")
        proof = {
            "schema_version": 1, "kind": "PREPARED_HEAD_QUINTIC",
            "scope": json.loads(before.scope),
            "simulation_session_id": before.scene_session,
            "reset_epoch": before.reset_epoch,
            "model_sha256": before.model_sha256,
            "scene_xml_sha256": self.geometry_scene_sha256,
            "geometry_sha256": self.geometry_sha256,
            "scene_qpos": list(before.qpos), "scene_qvel": list(before.qvel),
            "scene_source_time_ns": before.scene_source_time_ns,
            "scene_receipt_wall_ns": before.scene_received_wall_ns,
            "feedback_source_ns": before.feedback_source_ns,
            "feedback_receipt_wall_ns": before.feedback_wall_ns,
            "feedback_decision_sim_ns": before.decision_sim_ns,
            "feedback_decision_wall_ns": before.decision_wall_ns,
            "measured_neck_position_rad": before.neck_position,
            "measured_neck_velocity_rad_s": before.neck_velocity,
            "requested_target_rad": target,
            "header_stamp_ns": header_ns,
            "first_point_offset_ns": first_offset_ns,
            "last_point_offset_ns": first_offset_ns + duration_ns,
            "search_deadline_ns": self._local_state.search_deadline_ns,
            "lead_ns": _LEAD_NS,
            "main_duration_ns": duration_ns,
            "safe_interval_rad": list(self.safe_interval),
            "search_domain_rad": list(self.search_domain),
            "max_velocity_rad_s": _MAX_VELOCITY,
            "max_acceleration_rad_s2": _MAX_ACCELERATION,
            "quiet_velocity_rad_s": _QUIET_VELOCITY,
            "collision": collision,
            "typed_curve": typed_curve,
            "typed_goal_sha256": hashlib.sha256(typed_bytes).hexdigest(),
            "original_cdr_sha256": hashlib.sha256(serialized).hexdigest(),
        }
        proof_bytes = canonical_bytes(proof)
        nonce = uuid.uuid4().hex
        prepared = PreparedHeadTrajectory(self._owner, nonce, bytes(serialized), proof_bytes)
        with self._lock:
            if self._stopped:
                raise PermissionError("HEAD_TRAJECTORY_GUARD_REVOKED")
            if len(self._issued) >= 128:
                self._issued.pop(next(iter(self._issued)))
            self._issued[nonce] = (prepared, prepared.original_cdr, proof_bytes,
                                   _freeze_json(proof), goal, typed_bytes, before, admission)
        return prepared

    @staticmethod
    def _deadline_fits(deadline_ns: int, header_ns: int, final_offset_ns: int,
                       current_ros_ns: int, now_wall_ns: int) -> bool:
        """Check the original header and complete endpoint against one wall deadline."""
        return (type(deadline_ns) is int and type(header_ns) is int
                and type(final_offset_ns) is int and type(current_ros_ns) is int
                and type(now_wall_ns) is int and header_ns > current_ros_ns
                and now_wall_ns + (header_ns - current_ros_ns) + final_offset_ns
                <= deadline_ns)

    def _validate_seal(self, prepared: PreparedHeadTrajectory):
        admission = self._require_admission(check_scene=True)
        if type(prepared) is not PreparedHeadTrajectory or prepared._owner is not self._owner:
            raise PermissionError("HEAD_TRAJECTORY_PREPARED_OWNER_INVALID")
        with self._lock:
            item = self._issued.get(prepared._nonce)
            stopped = self._stopped
        if stopped or item is None or item[0] is not prepared:
            raise PermissionError("HEAD_TRAJECTORY_PREPARED_REVOKED")
        if prepared.original_cdr != item[1] or prepared.proof_bytes != item[2]:
            raise PermissionError("HEAD_TRAJECTORY_PREPARED_MUTATED")
        if item[7] is not admission:
            raise PermissionError('HEAD_ADMISSION_PREPARED_LEASE_INVALID')
        return item[3], item[4], item[6]

    def revalidate(self, prepared: PreparedHeadTrajectory) -> dict:
        """Fast proof/scope/freshness check before reserve and SDK boundaries."""
        proof, _, issued_snapshot = self._validate_seal(prepared)
        current, _, _ = self._capture()
        if (current.scope != issued_snapshot.scope
                or current.scene_session != issued_snapshot.scene_session
                or current.reset_epoch != proof["reset_epoch"]
                or current.model_sha256 != issued_snapshot.model_sha256
                or current.qpos != issued_snapshot.qpos
                or current.qvel != issued_snapshot.qvel
                or current.neck_position != issued_snapshot.neck_position
                or abs(current.neck_velocity) > _QUIET_VELOCITY
                or current.decision_wall_ns >= proof["search_deadline_ns"]
                or nanoseconds(self.monotonic()) >= proof["search_deadline_ns"]):
            raise PermissionError("HEAD_TRAJECTORY_PREPARED_STALE")
        current_ros_ns = self.node.get_clock().now().nanoseconds
        now_wall_ns = nanoseconds(self.monotonic())
        if (type(current_ros_ns) is not int or current_ros_ns <= 0
                or not current_ros_ns < proof["header_stamp_ns"]
                <= current_ros_ns + _LEAD_NS
                or not self._deadline_fits(
                    proof["search_deadline_ns"], proof["header_stamp_ns"],
                    proof["last_point_offset_ns"], current_ros_ns, now_wall_ns)):
            raise PermissionError("HEAD_TRAJECTORY_PREPARED_HEADER_EXPIRED")
        if self.controller_state_source is not None:
            check_dispatch_against_controller_state(
                proof, self.controller_state_source(), current_ros_ns=current_ros_ns,
                now_mono_ns=time.monotonic_ns())
        return proof

    def is_current(self) -> bool:
        if self._stopped or self._dispatcher is None:
            return False
        try:
            self._require_admission(check_scene=True)
            self._dispatcher._check_scope()
            return True
        except Exception:
            return False
