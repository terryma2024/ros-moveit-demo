"""Cup force/compression and collision rules the Teacher monitor enforces.

These are the cup-safety and contact protections the retired command broker enforced, ported without any broker,
reservation or `TeacherPhysicsSelection` type. The numbers are the activated contact policy's thresholds, unchanged. The
rules read the Teacher observer's `SimulationEvidence` contact lists and the `/so101/simulation/robot_contacts` frames.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

CUP_FORCE_CODE = "DYNAMIC_CUP_FORCE_EXCEEDED"
CUP_COMPRESSION_CODE = "DYNAMIC_CUP_COMPRESSION_EXCEEDED"
COLLISION_CODE = "DYNAMIC_COLLISION_STOP"


@dataclass(frozen=True, slots=True)
class CupSafetyLimits:
    maximum_safe_force_n: float
    maximum_compression_distance_m: float


def _positive_finite(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def limits_from_thresholds(thresholds: Mapping[str, Any]) -> CupSafetyLimits:
    """The two stop limits from an activated contact policy `thresholds` mapping; a missing or bad value refuses."""
    try:
        force = thresholds["maximum_safe_force_n"]
        compression = thresholds["maximum_compression_distance_m"]
    except (KeyError, TypeError) as error:
        raise ValueError("TEACHER_SAFETY_LIMITS_INVALID") from error
    if not _positive_finite(force) or not _positive_finite(compression):
        raise ValueError("TEACHER_SAFETY_LIMITS_INVALID")
    return CupSafetyLimits(float(force), float(compression))


@dataclass(frozen=True, slots=True)
class CupVerdict:
    code: str | None
    unavailable: bool
    summed_force_n: float
    compression_m: float


def evaluate_cup_contacts(sample: Any, limits: CupSafetyLimits) -> CupVerdict:
    """Summed normal force (left + right + other) and fingertip compression against the limits.

    `truncated=True` means the contact list is incomplete, so the force bound cannot be evaluated: it is reported as
    unavailable and never as zero force. Both comparisons are strict, as in the broker.
    """
    if getattr(sample, "truncated", False) is True:
        return CupVerdict(None, True, math.nan, math.nan)
    left = tuple(sample.left_fingertip_contacts)
    right = tuple(sample.right_fingertip_contacts)
    other = tuple(sample.other_object_contacts)
    summed = sum(float(item.normal_force_n) for item in (*left, *right, *other))
    compression = max((max(0.0, -float(item.signed_distance_m)) for item in (*left, *right)), default=0.0)
    if summed > limits.maximum_safe_force_n:
        return CupVerdict(CUP_FORCE_CODE, False, summed, compression)
    if compression > limits.maximum_compression_distance_m:
        return CupVerdict(CUP_COMPRESSION_CODE, False, summed, compression)
    return CupVerdict(None, False, summed, compression)


_CONTACT_KEYS = frozenset(("geom_a", "geom_b", "signed_distance_m", "normal_force_n", "truncated", "evidence_loss"))
_FRAME_KEYS = _CONTACT_KEYS | frozenset(("simulation_session_id", "reset_epoch", "physics_step", "simulation_time_s"))


class CollisionWatch:
    """Latches the first robot contact pair outside `process_pairs` (a collision), or a frame that cannot be evaluated.

    `process_pairs` are the cup process-expectation pairs (cup support and fingertip contact, the union over all
    phases): they are audit-only. Any other pair (robot against table or robot, a non-finger part against the cup) is a
    collision. A truncated or lossy frame means the collision list is not evaluable and also stops. Frames of an earlier
    reset epoch are ignored; a frame of another session or a later epoch is invalid evidence and stops.
    """

    def __init__(self, *, process_pairs, known_geoms, session_id: str, reset_epoch: int, record_only: bool = False,
                 tap=None, clock=time.monotonic) -> None:
        self._clock = clock
        #: Teacher policy v3: nothing latches. A pair outside the process pairs is offered to `tap.offer_collision`
        #: and an unreadable frame to `tap.note_incomplete` (the facts become process telemetry, never a stop).
        self._record_only, self._tap = record_only, tap
        self._process_pairs = frozenset(tuple(sorted(pair)) for pair in process_pairs)
        self._known = frozenset(known_geoms)
        self._session_id = session_id
        self._reset_epoch = reset_epoch
        self.hazard: str | None = None
        self.detail = ""
        self.hazard_step: int | None = None
        self.frames_seen = 0
        self._subscription = None

    def _latch(self, detail: str, step) -> None:
        if self._record_only:
            if self._tap is not None:
                self._tap.note_incomplete("CONTACT_FRAME_UNREADABLE: " + detail[:80])
            return None
        if self.hazard is None:
            self.hazard, self.detail, self.hazard_step = COLLISION_CODE, detail, step

    def accept(self, frame: Mapping[str, Any]) -> None:
        try:
            if set(frame) != _FRAME_KEYS:
                return self._latch("frame fields invalid", None)
            step = frame["physics_step"]
            if frame["simulation_session_id"] != self._session_id or frame["reset_epoch"] > self._reset_epoch:
                return self._latch("frame identity invalid", step)
            if frame["reset_epoch"] < self._reset_epoch:
                return None  # a frame from before the reset boundary
            self.frames_seen += 1
            if self._record_only and self._tap is not None:
                self._tap.note_receipt("collision", self._clock())
            if frame["truncated"] is not False or frame["evidence_loss"] is not False:
                if self._record_only:
                    self._latch("contact frame truncated or lossy", step)
                else:
                    return self._latch("contact frame truncated or lossy", step)
            arrays = [list(frame[key]) for key in ("geom_a", "geom_b", "signed_distance_m", "normal_force_n")]
            if len({len(item) for item in arrays}) != 1:
                return self._latch("contact arrays differ in length", step)
            for index, (first, second) in enumerate(zip(arrays[0], arrays[1], strict=True)):
                if self._known and (first not in self._known or second not in self._known):
                    if self._record_only:
                        self._latch(f"unknown geometry {first}/{second}", step)
                        continue
                    return self._latch(f"unknown geometry {first}/{second}", step)
                if tuple(sorted((first, second))) not in self._process_pairs:
                    if self._record_only:
                        if self._tap is not None:
                            self._tap.offer_collision(step, frame["simulation_time_s"], first, second,
                                                      arrays[2][index], arrays[3][index])
                        continue
                    return self._latch(f"pair {first} / {second}", step)
        except (KeyError, TypeError, ValueError):
            self._latch("frame invalid", None)

    def attach(self, node) -> None:
        """Subscribe to the plugin's robot contact frames (reliable, deep queue as the broker adapter did)."""
        from rclpy.qos import QoSProfile, ReliabilityPolicy
        from so101_mujoco_support.msg import RobotContactEvidence

        def callback(message) -> None:
            self.accept({key: list(getattr(message, key)) if key in
                         ("geom_a", "geom_b", "signed_distance_m", "normal_force_n") else getattr(message, key)
                         for key in _FRAME_KEYS})

        self._subscription = node.create_subscription(
            RobotContactEvidence, "/so101/simulation/robot_contacts", callback,
            QoSProfile(depth=10000, reliability=ReliabilityPolicy.RELIABLE))


PHYSICS_HAZARD_CODE = "DYNAMIC_PHYSICS_HAZARD"
_CHUNK_TOPIC = "/so101/simulation/physics_step_chunks"


class PhysicsHazardWatch:
    """Per-physics-step (500 Hz) watch of the chunk stream: the plugin's two hazard flags and the cup limits.

    `static_shadow_crossed` is the largest single cup contact force of a step above `static_shadow_force_n`
    (1.1579 N) and `diagnostic_hazard_breached` the summed cup force at or above 11.60 N; the plugin sets both on every
    500 Hz step while `SimulationEvidence` is published at 100 Hz. With `limits` the same stream also carries the frozen
    cup rule on every step (summed force, then the larger fingertip compression, both strict `>`, exactly
    `evaluate_cup_contacts`): the first violating step is latched with its number, value and the Teacher state.
    Chunk and step contiguity, `evidence_loss` and a truncated sample are counted as gaps (`gaps`, `gap_detail`):
    missing evidence is unavailable, never OK. Only scalars of the first flagged/violating step are kept: no sample,
    array or chunk is copied. Samples of another session or an earlier reset epoch are ignored.
    """

    def __init__(self, *, session_id: str, reset_epoch: int, limits=None, state_getter=None,
                 clock=time.monotonic, record_only: bool = False, tap=None) -> None:
        #: Teacher policy v3: the watch still subscribes and counts, but nothing latches (no limit, no hazard). Every in-scope step
        #: is offered to `tap.offer_step` and every gap or truncated sample to `tap.note_incomplete`.
        self._record_only, self._tap = record_only, tap
        self._session_id, self._reset_epoch = session_id, reset_epoch
        self.hazard: str | None = None
        self.detail = ""
        self.hazard_step: int | None = None
        self.chunks_seen = 0
        self._subscription = None
        self.limits, self._state_getter, self.clock = limits, state_getter, clock
        self.limit_code: str | None = None
        self.limit_detail = ""
        self.limit_step: int | None = None
        self.limit_state: str | None = None
        self.limit_value: float | None = None
        self.limit_kind: str | None = None
        self.limit_limit: float | None = None
        self.gaps = 0
        self.gap_detail = ""
        self.last_chunk_monotonic_s: float | None = None
        self.armed_monotonic_s: float | None = None
        self._last_sequence: int | None = None
        self._last_step: int | None = None

    def arm(self) -> None:
        """Start the silence clock (the Teacher's execution begins)."""
        self.armed_monotonic_s = self.clock()

    def _gap(self, detail: str) -> None:
        self.gaps += 1
        self.gap_detail = detail
        if self._tap is not None:
            self._tap.note_incomplete("PHYSICS_" + detail.split(" ")[0].upper().rstrip(":"))

    def _limit(self, code: str, kind: str, value: float, limit: float, step: int) -> None:
        state = None if self._state_getter is None else self._state_getter()
        state = getattr(state, "value", state)
        self.limit_code, self.limit_step, self.limit_state = code, step, state
        self.limit_value, self.limit_kind, self.limit_limit = value, kind, limit
        self.limit_detail = (f"per-step: {kind} {value:.9g} exceeds {limit:.9g} at physics step {step} "
                             f"in state {state}")

    def accept_chunk(self, message) -> None:
        self.chunks_seen += 1
        limits = self.limits
        tracking = limits is not None or self._record_only
        if self._record_only and self._tap is not None:
            self._tap.note_receipt("physics", self.clock())
        if tracking:
            self.last_chunk_monotonic_s = self.clock()
            sequence = message.chunk_sequence
            if self._last_sequence is not None and sequence != self._last_sequence + 1:
                self._gap(f"chunk_sequence {self._last_sequence} -> {sequence}")
            self._last_sequence = sequence
            if message.evidence_loss is not False:
                self._gap("evidence_loss in chunk " + str(sequence))
        for item in message.samples:
            if item.simulation_session_id != self._session_id or item.reset_epoch != self._reset_epoch:
                continue
            step = int(item.physics_step)
            if self._tap is not None and not item.truncated:
                self._tap.offer_step(step, item.simulation_time_s, item.total_normal_force_n,
                                     max(item.left_fingertip_compression_m, item.right_fingertip_compression_m))
            if tracking:
                if self._last_step is not None and step != self._last_step + 1:
                    self._gap(f"physics_step {self._last_step} -> {step}")
                self._last_step = step
                if item.truncated is not False:
                    self._gap(f"truncated sample at physics step {step}")
                elif limits is not None and self.limit_code is None:
                    force = item.total_normal_force_n
                    compression = max(item.left_fingertip_compression_m, item.right_fingertip_compression_m)
                    if force > limits.maximum_safe_force_n:
                        self._limit(CUP_FORCE_CODE, "summed_force_n", force, limits.maximum_safe_force_n, step)
                    elif compression > limits.maximum_compression_distance_m:
                        self._limit(CUP_COMPRESSION_CODE, "compression_m", compression,
                                    limits.maximum_compression_distance_m, step)
            if self._record_only:
                continue
            if self.hazard is None and (item.static_shadow_crossed or item.diagnostic_hazard_breached):
                name = "static_shadow_crossed" if item.static_shadow_crossed else "diagnostic_hazard_breached"
                self.hazard, self.hazard_step = PHYSICS_HAZARD_CODE, step
                self.detail = f"{name} at physics step {item.physics_step}"
            if limits is None and self.hazard is not None:
                return

    def attach(self, node) -> None:
        """Subscribe to the chunk topic: reliable, depth 100 (one second at the 5-sample chunk rate)."""
        from rclpy.qos import QoSProfile, ReliabilityPolicy
        from so101_mujoco_support.msg import PhysicsStepEvidenceChunk

        self._subscription = node.create_subscription(
            PhysicsStepEvidenceChunk, _CHUNK_TOPIC, self.accept_chunk,
            QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE))


@dataclass(frozen=True, slots=True)
class TeacherSafetyInputs:
    limits: CupSafetyLimits
    process_pairs: frozenset
    known_geoms: frozenset
    fingerprint: str


def load_frozen_safety(manifest_path: Path) -> TeacherSafetyInputs:
    """Build the limits and the collision geometry from the frozen diagnostic-episode inputs.

    Same inputs the broker-era Teacher source used: the verified frozen manifest, its execution snapshot's scene, the
    activated contact proposal and receipt. Any mismatch refuses before motion.
    """
    import json

    import mujoco

    from ..act.execution_snapshot import verify_execution_snapshot
    from ..act.diagnostic_episode_inputs import verify_frozen_inputs
    from ..act.contact_policy import spot_check_receipt_allowed
    from ..adapters.act.phase_contact_allowlist import PhaseContactAllowlist

    manifest_path = Path(manifest_path)
    frozen = verify_frozen_inputs(manifest_path)
    binding = frozen["execution_snapshot"]
    root = manifest_path.parent / binding["path"]
    snapshot = verify_execution_snapshot(root, expected_sha256=binding["sha256"])
    scene = root / snapshot["scene_path"]
    model = mujoco.MjModel.from_xml_path(str(scene))
    proposal = manifest_path.parent / frozen["roles"]["contact_proposal"]["path"]
    receipt = manifest_path.parent / frozen["roles"]["contact_activation"]["path"]
    pairs = PhaseContactAllowlist(
        model=model, scene_path=scene, proposal_path=proposal, receipt_path=receipt,
        expected_fingerprint=json.loads(proposal.read_bytes())["policy_fingerprint"],
        allow_spot_check_candidate=spot_check_receipt_allowed(frozen.get("mode")))
    if verify_frozen_inputs(manifest_path) != frozen:
        raise ValueError("TEACHER_SAFETY_FROZEN_BINDING_INVALID")
    return TeacherSafetyInputs(limits_from_thresholds(pairs.thresholds), pairs.process_pairs,
                               pairs.known_geoms, pairs.fingerprint)
