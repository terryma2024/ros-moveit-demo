"""``teacher_process_summary_v1``: the process telemetry of one Teacher attempt (policy v3, design 2026-10-10 minimal runtime gates).

Collision, contact, force and perception facts observed during the run are recorded here, per phase, to tune the pick strategy and
to select episodes offline. They never stop, refuse or branch the Teacher. This module is pure: it holds scalars fed by the
runtime's existing streams and aggregates them when asked. The feed methods only append (they are called from callbacks of the
control thread); the aggregation (`build`, `compute_in_thread`) runs on its own thread.

Definitions (units: N, um, mm, deg, s and physics step numbers):

* **Phase**: a Teacher state bounded by its `phase_begin` / `phase_finish` simulation times (begin <= t <= finish).
* **Force and compression**: from the 500 Hz physics chunks. Summed force is the chunk's `total_normal_force_n`, compression the
  larger of the two fingertip compressions. The first exceedance of an r10b threshold is the first step with a strict `>` (no filter).
  `ORACLE_CUP_OVERLOAD` marks a phase with any step over either threshold.
* **Collision pairs**: robot contact pairs outside the cup process pairs (from `/robot_contacts`) with the step, depth and force.
  `ORACLE_COLLISION` marks a phase with one.
* **Bilateral contact lost**: an interval of at least 80 ms without contact on both fingertips (100 Hz evidence), in the holding phases.
* **Slip**: the cup pose in the TCP frame (forward kinematics), at the end of WAIT_GRASP_STABLE against just before OPEN_GRIPPER.
* **Settle time**: from the OPEN_GRIPPER finish to the start of the first 0.2 s window in which the cup rests on the table with no
  fingertip contact at most 1 mm/s and 0.05 rad/s.
* **Release displacement**: the cup pose at the OPEN_GRIPPER start against the end observation.
* **Completeness**: a lost chunk, a lost contact frame, a truncated sample or a missing threshold marks `complete = false` with a
  reason. It never aborts.
"""

from __future__ import annotations

import bisect
import math
import threading
from collections import deque
from typing import Any, Callable, Iterable

SCHEMA = "teacher_process_summary_v1"
FLAG_OVERLOAD = "ORACLE_CUP_OVERLOAD"
FLAG_COLLISION = "ORACLE_COLLISION"
ORACLE_FLAGS = (FLAG_OVERLOAD, FLAG_COLLISION)
UNITS = {"force": "N", "compression": "um", "distance": "mm", "angle": "deg", "time": "s", "step": "physics_step"}
#: the phases in which the cup is held (bilateral contact is expected between WAIT_GRASP_STABLE and the touchdown)
HOLD_PHASES = ("WAIT_GRASP_STABLE", "MICRO_LIFT", "WAIT_MICRO_LIFT_STABLE", "VERIFY_PHYSICAL_GRASP", "ATTACH_MOVEIT", "LIFT",
               "MOVE_ABOVE_PLACE", "DESCEND_TO_PLACE")
#: the carried phases in which a table contact is early (DESCEND_TO_PLACE records the touchdown step instead)
TABLE_PHASES = ("LIFT", "MOVE_ABOVE_PLACE", "DESCEND_TO_PLACE")
#: the pseudo phase of the samples that fall between two phases
BETWEEN_PHASES = "BETWEEN_PHASES"
BILATERAL_LOST_MIN_S = 0.080
SETTLE_WINDOW_S = 0.20
SETTLE_MAX_LINEAR_M_S = 0.001
SETTLE_MAX_ANGULAR_RAD_S = 0.05
MAX_COLLISION_PAIRS = 64
MAX_INTERVALS = 64
DEFAULT_CAPACITY = 400_000


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def sample_contact_metrics(left: Iterable, right: Iterable, other: Iterable) -> tuple[float, float]:
    """(summed normal force N, fingertip compression m) of one world sample's contact lists, as `evaluate_cup_contacts` computes them."""
    left, right, other = tuple(left), tuple(right), tuple(other)
    summed = sum(float(item.normal_force_n) for item in (*left, *right, *other))
    compression = max((max(0.0, -float(item.signed_distance_m)) for item in (*left, *right)), default=0.0)
    return summed, compression


def _quaternion_tilt_deg(q: tuple[float, float, float, float]) -> float:
    x, y, _z, _w = q
    return math.degrees(math.acos(min(1.0, max(-1.0, 1.0 - 2.0 * (x * x + y * y)))))


def _rotation_matrix(q: tuple[float, float, float, float]) -> list[list[float]]:
    x, y, z, w = q
    norm = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / norm, y / norm, z / norm, w / norm
    return [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ]


def _transpose(m):
    return [[m[j][i] for j in range(3)] for i in range(3)]


def _matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def relative_pose(cup_position, cup_quaternion, frame_position, frame_quaternion) -> tuple[list[float], list[list[float]]]:
    """The cup pose expressed in a frame (the TCP): (translation, rotation matrix)."""
    r_frame = _rotation_matrix(frame_quaternion)
    inverse = _transpose(r_frame)
    delta = [cup_position[i] - frame_position[i] for i in range(3)]
    translation = [sum(inverse[i][k] * delta[k] for k in range(3)) for i in range(3)]
    return translation, _matmul(inverse, _rotation_matrix(cup_quaternion))


def _rotation_angle_deg(a, b) -> float:
    relative = _matmul(_transpose(a), b)
    trace = relative[0][0] + relative[1][1] + relative[2][2]
    return math.degrees(math.acos(min(1.0, max(-1.0, (trace - 1.0) / 2.0))))


class ProcessSummary:
    """Collects the streams of one attempt and builds the summary document."""

    def __init__(self, *, limits=None, limits_error: str | None = None, capacity: int = DEFAULT_CAPACITY) -> None:
        self.limits = limits
        self._limits_error = limits_error
        self._capacity = capacity
        self._steps: deque = deque()          # (step, sim_time_s, summed_force_n, compression_m)
        self._worlds: deque = deque()         # (sim_time_s, step, left_contacts, right_contacts, table_contact, table_force_n, lin, ang)
        self._collisions: deque = deque()     # (step, sim_time_s, geom_a, geom_b, depth_m, force_n)
        self._phases: list[dict] = []
        self._incomplete: dict[str, int] = {}
        self._poses: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._overflowed = False
        #: a stream (physics chunks, contact frames) silent for longer than this while a phase is open is incomplete telemetry
        self.silence_limit_s: float | None = None
        self._last_receipt: dict[str, float] = {}
        self._phase_open_at_receipt: dict[str, bool] = {}
        self._open_phases = 0

    # ---- feed (cheap; callable from any callback; every append is under the lock, so `build` can copy consistently) ------------

    def _append(self, store: deque, record: tuple) -> None:
        overflow = False
        with self._lock:
            if len(store) >= self._capacity:
                overflow = not self._overflowed
                self._overflowed = True
            else:
                store.append(record)
        if overflow:
            self.note_incomplete("SUMMARY_CAPACITY_EXCEEDED")

    def offer_step(self, step: int, time_s: float, force_n: float, compression_m: float) -> None:
        self._append(self._steps, (int(step), float(time_s), float(force_n), float(compression_m)))

    def note_receipt(self, stream: str, monotonic_s: float) -> None:
        """A message of `stream` ("physics", "collision") arrived at `monotonic_s`. A gap longer than `silence_limit_s` in which a phase was
        open (at either end) marks the telemetry incomplete: the flags cannot be ruled out for the silent interval."""
        silent = False
        with self._lock:
            previous = self._last_receipt.get(stream)
            open_now = self._open_phases > 0
            if (previous is not None and self.silence_limit_s is not None and monotonic_s - previous > self.silence_limit_s
                    and (open_now or self._phase_open_at_receipt.get(stream, False))):
                silent = True
            self._last_receipt[stream] = monotonic_s
            self._phase_open_at_receipt[stream] = open_now
        if silent:
            self.note_incomplete(f"{stream.upper()}_STREAM_SILENT")

    def check_streams(self, now_s: float, expected: Iterable[str]) -> None:
        """End of the run: an expected stream that never delivered, or that fell silent in a phase that is still open, is incomplete."""
        for stream in expected:
            with self._lock:
                last = self._last_receipt.get(stream)
                open_now = self._open_phases > 0
            if last is None:
                self.note_incomplete(f"{stream.upper()}_STREAM_NEVER_RECEIVED")
            elif open_now and self.silence_limit_s is not None and now_s - last > self.silence_limit_s:
                self.note_incomplete(f"{stream.upper()}_STREAM_SILENT")

    def offer_world(self, value: Any) -> None:
        """One 100 Hz world evidence sample (`SimulationEvidence`)."""
        if getattr(value, "truncated", False):
            self.note_incomplete("WORLD_TRUNCATED")          # the contact lists of this sample are incomplete
        try:
            table = [item for item in value.other_object_contacts if getattr(item, "geom2", None) == "table_collision"]
            lin = max(abs(item) for item in value.object_state.linear_velocity_world)
            ang = max(abs(item) for item in value.object_state.angular_velocity_world)
            record = (float(value.simulation_time_s), int(value.simulation_step), len(value.left_fingertip_contacts),
                      len(value.right_fingertip_contacts), bool(table), sum(float(item.normal_force_n) for item in table), lin, ang)
        except (AttributeError, TypeError, ValueError):
            self.note_incomplete("WORLD_SAMPLE_UNREADABLE")
            return
        self._append(self._worlds, record)

    def offer_collision(self, step: int, time_s: float, geom_a: str, geom_b: str, depth_m: float, force_n: float) -> None:
        self._append(self._collisions, (int(step), float(time_s), str(geom_a), str(geom_b), float(depth_m), float(force_n)))

    def note_incomplete(self, reason: str) -> None:
        with self._lock:
            self._incomplete[reason] = self._incomplete.get(reason, 0) + 1

    def phase_begin(self, state: str, sim_time_s: float | None) -> None:
        with self._lock:
            self._phases.append({"state": state, "begin_s": sim_time_s, "finish_s": None, "status": None, "code": None})
            self._open_phases += 1

    def phase_finish(self, state: str, sim_time_s: float | None, status: str, code: str | None = None) -> None:
        with self._lock:
            for phase in reversed(self._phases):
                if phase["state"] == state and phase["finish_s"] is None:
                    phase["finish_s"], phase["status"], phase["code"] = sim_time_s, status, code
                    self._open_phases = max(0, self._open_phases - 1)
                    return

    def note_pose(self, label: str, *, time_s, cup_position, cup_quaternion, tcp_position=None, tcp_quaternion=None, **facts) -> None:
        """A pose pair (the cup, and the TCP when known) at a named instant: `grasp_stable`, `release_start`, `release_end`."""
        with self._lock:
            self._poses[label] = {"time_s": time_s, "cup_position": list(cup_position), "cup_quaternion": list(cup_quaternion),
                                  "tcp_position": None if tcp_position is None else list(tcp_position),
                                  "tcp_quaternion": None if tcp_quaternion is None else list(tcp_quaternion), **facts}

    # ---- aggregation -----------------------------------------------------------------------------------------------------------

    def build(self, *, policy: dict | None = None, place_height: dict | None = None, end_observation: dict | None = None,
              perception_error: dict | None = None, extra_incomplete: Iterable[str] = ()) -> dict:
        """The summary document. Pure aggregation of what was fed; safe to call on any thread."""
        with self._lock:
            phases = [dict(item) for item in self._phases]
            incomplete = dict(self._incomplete)
            poses = {key: dict(value) for key, value in self._poses.items()}
            steps_copy, worlds_copy, collisions_copy = list(self._steps), list(self._worlds), list(self._collisions)
        for reason in extra_incomplete:
            incomplete[reason] = incomplete.get(reason, 0) + 1
        # the feeds arrive in stream order, but the aggregation does not rely on it
        steps = sorted(steps_copy, key=lambda item: item[1])
        worlds = sorted(worlds_copy, key=lambda item: item[0])
        collisions = sorted(collisions_copy, key=lambda item: item[1])
        force_limit = comp_limit = None
        if self.limits is None:
            incomplete.setdefault(self._limits_error or "THRESHOLDS_UNAVAILABLE", 1)
        else:
            force_limit = float(self.limits.maximum_safe_force_n)
            comp_limit = float(self.limits.maximum_compression_distance_m)
        step_times = [item[1] for item in steps]
        world_times = [item[0] for item in worlds]
        collision_times = [item[1] for item in collisions]
        last_time = max([*step_times[-1:], *world_times[-1:]] or [0.0])
        phase_documents: dict[str, dict] = {}
        flags: dict[str, list[str]] = {flag: [] for flag in ORACLE_FLAGS}
        for index, phase in enumerate(phases):
            begin, finish = phase["begin_s"], phase["finish_s"]
            if not _finite(begin):
                incomplete["PHASE_TIME_UNKNOWN"] = incomplete.get("PHASE_TIME_UNKNOWN", 0) + 1
                begin = 0.0
            if not _finite(finish):
                finish = math.nextafter(last_time, math.inf) if index == len(phases) - 1 else begin   # an unfinished last phase: half-open, so include the last sample
            name = phase["state"]
            document = self._phase_document(name, phase, begin, finish, steps, step_times, worlds, world_times, collisions,
                                            collision_times, force_limit, comp_limit)
            key = name if name not in phase_documents else f"{name}#{index}"
            phase_documents[key] = document
            for flag in document["oracle_flags"]:
                flags[flag].append(key)
        # A sample between two phases (the place-height measurement runs there) belongs to no phase window: it is attributed to
        # BETWEEN_PHASES so that an exceedance in the gap cannot go unflagged. Before the first phase and after the last one
        # (reset transients, the end-observation settle) nothing is attributed.
        spans = [(item["begin_s"], item["finish_s"]) for item in phases if _finite(item["begin_s"]) and _finite(item["finish_s"])]
        if spans:
            first_begin, last_finish = min(item[0] for item in spans), max(item[1] for item in spans)

            def gap(time_s: float) -> bool:
                return first_begin <= time_s < last_finish and not any(begin <= time_s < finish for begin, finish in spans)

            gap_steps = [item for item in steps if gap(item[1])]
            gap_collisions = [item for item in collisions if gap(item[1])]
            if gap_steps or gap_collisions:
                times = [item[1] for item in (*gap_steps, *gap_collisions)]
                bucket = self._phase_document(
                    BETWEEN_PHASES, {"status": None, "code": None}, min(times), math.nextafter(max(times), math.inf), gap_steps,
                    [item[1] for item in gap_steps], [], [], gap_collisions, [item[1] for item in gap_collisions],
                    force_limit, comp_limit)
                phase_documents[BETWEEN_PHASES] = bucket
                for flag in bucket["oracle_flags"]:
                    flags[flag].append(BETWEEN_PHASES)
        document = {
            "schema": SCHEMA,
            "complete": not incomplete,
            "incomplete_reasons": sorted(incomplete),
            "units": dict(UNITS),
            "thresholds": None if force_limit is None else {
                "source": "r10b", "summed_force_n": force_limit, "compression_um": comp_limit * 1e6, "comparison": "strict >"},
            "policy": None if policy is None else {
                "execution_policy_schema": policy.get("schema_version"), "execution_policy_sha256": policy.get("policy_sha256"),
                "cup_pose_source": policy.get("cup_pose_source"), "verdict_source": policy.get("verdict_source")},
            "phases": phase_documents,
            "flags": flags,
            "slip_in_hand": self._slip(poses),
            "release": self._release(poses, worlds, world_times, phases, end_observation),
            "settle_time_s": self._settle_time(worlds, phases),
            "place_height_mode": None if place_height is None else place_height.get("mode"),
            "place_fallback_reason": None if place_height is None else place_height.get("fallback_reason"),
            "perception_error": perception_error,
            "completeness": {"samples": {"physics_steps": len(steps), "world": len(worlds), "collision_records": len(collisions)},
                             "reasons": {reason: incomplete[reason] for reason in sorted(incomplete)}},
        }
        return document

    @staticmethod
    def _slice(times: list[float], begin: float, finish: float) -> tuple[int, int]:
        # half-open [begin, finish): a sample on the boundary of two phases belongs to the later one, and is counted once
        return bisect.bisect_left(times, begin), bisect.bisect_left(times, finish)

    def _phase_document(self, name, phase, begin, finish, steps, step_times, worlds, world_times, collisions, collision_times,
                        force_limit, comp_limit) -> dict:
        lo, hi = self._slice(step_times, begin, finish)
        window = steps[lo:hi]
        peak_force = peak_compression = None
        peak_force_step = peak_compression_step = None
        first_force = first_compression = None
        for step, time_s, force, compression in window:
            if peak_force is None or force > peak_force:
                peak_force, peak_force_step = force, step
            if peak_compression is None or compression > peak_compression:
                peak_compression, peak_compression_step = compression, step
            if force_limit is not None:
                if first_force is None and force > force_limit:
                    first_force = (step, force)
                if first_compression is None and compression > comp_limit:
                    first_compression = (step, compression)
        flags = []
        if first_force is not None or first_compression is not None:
            flags.append(FLAG_OVERLOAD)
        wlo, whi = self._slice(world_times, begin, finish)
        wwindow = worlds[wlo:whi]
        clo, chi = self._slice(collision_times, begin, finish)
        pairs: dict[tuple[str, str], dict] = {}
        for step, time_s, geom_a, geom_b, depth, force in collisions[clo:chi]:
            key = tuple(sorted((geom_a, geom_b)))
            entry = pairs.get(key)
            if entry is None:
                if len(pairs) >= MAX_COLLISION_PAIRS:
                    continue
                entry = pairs[key] = {"pair": list(key), "first_step": step, "max_depth_mm": 0.0, "max_force_n": 0.0, "count": 0}
            entry["count"] += 1
            entry["max_depth_mm"] = max(entry["max_depth_mm"], max(0.0, -depth) * 1e3)
            entry["max_force_n"] = max(entry["max_force_n"], force)
        if chi > clo:
            flags.append(FLAG_COLLISION)
        document: dict[str, Any] = {
            "begin_sim_s": begin, "finish_sim_s": finish, "status": phase["status"], "code": phase["code"], "steps": len(window),
            "peak_force_n": peak_force, "peak_force_step": peak_force_step,
            "peak_compression_um": None if peak_compression is None else peak_compression * 1e6,
            "peak_compression_step": peak_compression_step,
            "force_margin_n": None if force_limit is None or peak_force is None else force_limit - peak_force,
            "compression_margin_um": None if comp_limit is None or peak_compression is None else (comp_limit - peak_compression) * 1e6,
            "first_force_exceedance_step": None if first_force is None else first_force[0],
            "first_force_exceedance_n": None if first_force is None else first_force[1],
            "first_compression_exceedance_step": None if first_compression is None else first_compression[0],
            "first_compression_exceedance_um": None if first_compression is None else first_compression[1] * 1e6,
            "collision_pairs": sorted(pairs.values(), key=lambda item: item["first_step"]),
            "oracle_flags": flags,
        }
        document["bilateral_contact_lost"] = self._bilateral_lost(wwindow) if name in HOLD_PHASES else []
        if name in TABLE_PHASES:
            touch = next((item for item in wwindow if item[4]), None)
            document["early_table_contact"] = touch is not None
            document["first_table_contact_step"] = None if touch is None else touch[1]
        return document

    @staticmethod
    def _bilateral_lost(window: list[tuple]) -> list[dict]:
        intervals: list[dict] = []
        start = None
        previous_time = None
        for time_s, _step, left, right, *_ in window:
            lost = not (left and right)
            if lost and start is None:
                start = time_s
            if not lost and start is not None:
                if previous_time - start >= BILATERAL_LOST_MIN_S and len(intervals) < MAX_INTERVALS:
                    intervals.append({"begin_s": start, "end_s": time_s, "duration_s": time_s - start})
                start = None
            previous_time = time_s
        if start is not None and previous_time is not None and previous_time - start >= BILATERAL_LOST_MIN_S \
                and len(intervals) < MAX_INTERVALS:
            intervals.append({"begin_s": start, "end_s": previous_time, "duration_s": previous_time - start})
        return intervals

    @staticmethod
    def _slip(poses: dict) -> dict | None:
        first, second = poses.get("grasp_stable"), poses.get("release_start")
        if not first or not second or any(item.get("tcp_position") is None for item in (first, second)):
            return None
        a_pos, a_rot = relative_pose(first["cup_position"], first["cup_quaternion"], first["tcp_position"], first["tcp_quaternion"])
        b_pos, b_rot = relative_pose(second["cup_position"], second["cup_quaternion"], second["tcp_position"], second["tcp_quaternion"])
        return {"translation_mm": math.dist(a_pos, b_pos) * 1e3, "rotation_deg": _rotation_angle_deg(a_rot, b_rot),
                "from": "end of WAIT_GRASP_STABLE", "to": "just before OPEN_GRIPPER"}

    @staticmethod
    def _release(poses, worlds, world_times, phases, end_observation) -> dict | None:
        start = poses.get("release_start")
        if start is None:
            return None
        document: dict[str, Any] = {
            "table_contact": start.get("table_contact"), "table_normal_force_n": start.get("table_normal_force_n"),
            "left_contacts": start.get("left_contacts"), "right_contacts": start.get("right_contacts"),
            "displacement_mm": None, "displacement_deg": None}
        if end_observation:
            try:
                end_position = list(end_observation["position"])
                o = end_observation["orientation"]
                end_q = (o["x"], o["y"], o["z"], o["w"])
                document["displacement_mm"] = math.dist(start["cup_position"], end_position) * 1e3
                document["displacement_deg"] = _rotation_angle_deg(_rotation_matrix(tuple(start["cup_quaternion"])), _rotation_matrix(end_q))
            except (KeyError, TypeError, ValueError):
                pass
        return document

    @staticmethod
    def _settle_time(worlds: list[tuple], phases: list[dict]) -> float | None:
        opened = next((p["finish_s"] for p in phases if p["state"] == "OPEN_GRIPPER" and _finite(p["finish_s"])), None)
        if opened is None:
            return None
        start = None
        for time_s, _step, left, right, table, _force, lin, ang in worlds:
            if time_s < opened:
                continue
            holds = bool(table and not left and not right and lin <= SETTLE_MAX_LINEAR_M_S and ang <= SETTLE_MAX_ANGULAR_RAD_S)
            if not holds:
                start = None
                continue
            if start is None:
                start = time_s
            if time_s - start >= SETTLE_WINDOW_S:
                return start - opened
        return None

    # ---- off the control thread ----------------------------------------------------------------------------------------------

    def compute_in_thread(self, **kwargs) -> Callable[[float], dict | None]:
        """Start `build(**kwargs)` on its own thread; the returned function waits at most `timeout` s for the document (None on timeout)."""
        holder: dict[str, Any] = {}

        def run() -> None:
            try:
                holder["document"] = self.build(**kwargs)
            except Exception as error:  # noqa: BLE001 - a summary failure is recorded, never raised into the Teacher
                holder["error"] = f"{type(error).__name__}: {error}"[:300]

        thread = threading.Thread(target=run, name="teacher-process-summary", daemon=True)
        thread.start()

        def result(timeout: float) -> dict | None:
            thread.join(timeout)
            return holder.get("document")

        result.error = lambda: holder.get("error")      # type: ignore[attr-defined]
        return result


def failure_summary(reason: str, *, policy: dict | None = None) -> dict:
    """The summary of an attempt whose telemetry could not be built: a valid document that says so."""
    document = ProcessSummary(limits=None, limits_error=reason).build(policy=policy)
    document["complete"] = False
    return document


def validate_summary(document: Any) -> None:
    """Structural check of a `teacher_process_summary_v1` (data side, ValueError): the schema, the completeness flag against its
    reasons, and the oracle flags against the phases they are derived from."""
    if type(document) is not dict or document.get("schema") != SCHEMA:
        raise ValueError("PROCESS_SUMMARY: schema")
    reasons = document.get("incomplete_reasons")
    if type(document.get("complete")) is not bool or type(reasons) is not list or any(not isinstance(item, str) for item in reasons):
        raise ValueError("PROCESS_SUMMARY: completeness")
    if document["complete"] != (not reasons):
        raise ValueError("PROCESS_SUMMARY: completeness flag disagrees with its reasons")
    phases, flags = document.get("phases"), document.get("flags")
    if type(phases) is not dict or type(flags) is not dict or set(flags) != set(ORACLE_FLAGS):
        raise ValueError("PROCESS_SUMMARY: phases or flags")
    for flag in ORACLE_FLAGS:
        listed = flags[flag]
        derived = sorted(name for name, phase in phases.items()
                         if type(phase) is dict and type(phase.get("oracle_flags")) is list and flag in phase["oracle_flags"])
        if type(listed) is not list or sorted(listed) != derived:
            raise ValueError(f"PROCESS_SUMMARY: {flag} disagrees with the phases")
    for phase in phases.values():
        if type(phase) is not dict or type(phase.get("oracle_flags")) is not list or not set(phase["oracle_flags"]) <= set(ORACLE_FLAGS):
            raise ValueError("PROCESS_SUMMARY: phase")


def oracle_exclusion(document: Any) -> tuple[str, str] | None:
    """(flag, phase) of the first oracle flag of a summary that makes the episode not training-eligible (design section 7), else None.
    An unreadable or incomplete summary is itself a reason: ``("INCOMPLETE", reason)``."""
    try:
        validate_summary(document)
    except ValueError as error:
        return ("INCOMPLETE", str(error)[:120])
    for flag in ORACLE_FLAGS:
        if document["flags"][flag]:
            return (flag, document["flags"][flag][0])
    if not document["complete"]:
        return ("INCOMPLETE", ",".join(document["incomplete_reasons"])[:120])
    return None
