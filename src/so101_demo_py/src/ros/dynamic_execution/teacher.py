"""Teacher run policies, observations and manifest fields of the dynamic execution."""

from __future__ import annotations

import copy
import math
from pathlib import Path
import time

from so101_demo.act.teacher_endpoint import EXECUTION_KIND, EXECUTION_POLICY_FILE
from so101_demo.application.e2e_acceptance import (
    MANIFEST_SCHEMA_VERSION,
    SCHEMA_GENERAL,
    SCHEMA_TEACHER,
)
from so101_demo.core.domain import State
from so101_demo.core.dynamic_pick import (
    compose_pose,
    inverse_pose,
)
from so101_demo.core.place_height import PlaceHeightRefused
from so101_demo.core.workflow import (
    SIM_INTEGRITY_CODES,
    TERMINAL_STOP_CODES,
    TERMINAL_STOP_CODES_TEACHER,
)
from so101_demo.ports.evidence import PoseEvidence
from so101_demo.ros.dynamic_execution.common import (
    _CONTROLLER_UNSETTLED_CODES,
    _TEACHER_CODE_MAP,
    _TEACHER_FAILED_CODES,
    _TEACHER_STOP_VELOCITY_RAD_S,
    _JointStateStale,
)
from so101_demo.ros.teacher_stop import TeacherStop


class TeacherRun:
    def _load_teacher_policies(self, urdf_path) -> None:
        """Load the Teacher endpoint policy and the general runtime policy from the installed share config dir the runtime already uses."""

        import hashlib

        from so101_demo.act.general_runtime_policy import (
            GENERAL_RUNTIME_FILE,
            load_general_runtime_policy,
        )
        from so101_demo.act.teacher_endpoint import load_teacher_endpoint_policy

        self._teacher_config_error = None
        self._teacher_policy_files = {}
        self._teacher_endpoint_policy = None
        self._execution_policy = None
        try:
            config_dir = Path(urdf_path).parents[2] / "config/act"
            self._teacher_config_dir = config_dir
            endpoint_path = config_dir / "teacher_endpoint.yaml"
            execution_path = config_dir / GENERAL_RUNTIME_FILE
            endpoint_bytes, execution_bytes = endpoint_path.read_bytes(), execution_path.read_bytes()
        except (OSError, IndexError) as error:
            self._teacher_config_error = f"TEACHER_POLICY_UNAVAILABLE: {error}"
            return
        try:
            self._teacher_endpoint_policy = load_teacher_endpoint_policy(endpoint_bytes)
            self._execution_policy = load_general_runtime_policy(execution_bytes)
        except ValueError as error:
            self._teacher_config_error = str(error)
            return
        self._teacher_policy_files = {
            "endpoint": {"path": str(endpoint_path), "file_sha256": hashlib.sha256(endpoint_bytes).hexdigest(),
                         "policy_sha256": self._teacher_endpoint_policy["policy_sha256"]},
            "execution": {"path": str(execution_path), "file_sha256": hashlib.sha256(execution_bytes).hexdigest(),
                          "policy_sha256": self._execution_policy["policy_sha256"]},
        }

    def _select_execution_policy(self, file_name: str = EXECUTION_POLICY_FILE) -> None:
        """Load the Teacher execution policy the freeze names instead of the general runtime policy, and start the Teacher run."""

        import hashlib

        from so101_demo.act.teacher_endpoint import load_teacher_execution_policy

        config_dir = getattr(self, "_teacher_config_dir", None)
        if config_dir is None:
            return                                      # the policies did not load at all: the config error is already set
        path = config_dir / file_name
        try:
            raw = path.read_bytes()
            policy = load_teacher_execution_policy(raw)
        except (OSError, ValueError) as error:
            self._execution_policy = None
            self._teacher_config_error = f"TEACHER_POLICY_UNAVAILABLE: {error}"
            return
        self._execution_policy = policy
        files = getattr(self, "_teacher_policy_files", None)
        if files:
            files["execution"] = {"path": str(path), "file_sha256": hashlib.sha256(raw).hexdigest(),
                                  "policy_sha256": policy["policy_sha256"]}
        self._activate_teacher_run()

    def _teacher_run(self) -> bool:
        """True for a Teacher run: its execution policy is the Teacher's (the minimal runtime gates, design 2026-10-10)."""
        return (getattr(self, "_execution_policy", None) or {}).get("kind") == EXECUTION_KIND

    def _activate_teacher_run(self) -> None:
        """Teacher run: the Teacher manifest schema, and the process-telemetry collector fed by taps on the existing streams.

        The taps only append (they run inside the control thread's spin); the summary is aggregated off the control thread."""
        from so101_demo.core.process_summary import ProcessSummary

        summary = ProcessSummary(limits=getattr(self, "_safety_limits", None))
        summary.silence_limit_s = float(self._execution_policy["state_unavailable_stop_s"])
        self._process_summary = summary
        self._document["schema"] = SCHEMA_TEACHER
        observer = getattr(self, "observer", None)
        if observer is not None and hasattr(observer, "add_tap"):
            observer.add_tap(lambda evidence, receipt: summary.offer_world(evidence))
        if observer is not None and hasattr(observer, "_accept_truncated"):
            # sustained truncated contact lists must never age the control evidence into an abort: accept them, mark the summary
            observer._accept_truncated = True
        if observer is not None and hasattr(observer, "_on_sequence_gap"):
            # a gap in the world stream is telemetry completeness in a Teacher run, not a hazard
            observer._on_sequence_gap = lambda previous, following: summary.note_incomplete("WORLD_SEQUENCE_GAP")

    def _failure_code(self, error) -> tuple[str, str]:
        """(code, message) of an exception; in a Teacher run the evidence and joint-state codes are the SIM_INTEGRITY / JOINT_STATE ones."""
        message = str(error)
        raw = message.split(":", 1)[0] or "DYNAMIC_EXECUTION_FAILED"
        if not self._teacher_run() or raw not in _TEACHER_CODE_MAP:
            return raw, message
        code = _TEACHER_CODE_MAP[raw]
        return code, code + message[len(raw):]

    @staticmethod
    def _teacher_pose_document(values) -> dict[str, object]:
        x, y, z, qx, qy, qz, qw = (float(item) for item in values)
        norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
        if not norm > 0.0:
            norm = 1.0
        return {"position": [x, y, z],
                "orientation": {"x": qx / norm, "y": qy / norm, "z": qz / norm, "w": qw / norm}}

    def _teacher_targets(self) -> tuple[dict[str, object], dict[str, object]]:
        """(start_target, end_target), both frozen before the first motion.

        The start target is the input cup pose this run was resolved from. The end target is the place pose today's
        VALIDATE_FINAL_PLACEMENT frozen (XY and attitude of the expected cup pose); its height is the input cup's
        resting height, because that expected pose is a TCP-derived geometric pose, not a table-resting height.
        """

        start_values = tuple(self._targets.input_pose.pose_world.values)
        expected = compose_pose(self._template.place_tcp_world, inverse_pose(self._template.cup_to_tcp_grasp))
        end_values = (expected.values[0], expected.values[1], start_values[2], *expected.values[3:7])
        return self._teacher_pose_document(start_values), self._teacher_pose_document(end_values)

    @staticmethod
    def _teacher_observation(value) -> dict[str, object]:
        x, y, z, w = value.object_state.orientation_xyzw
        return {
            "position": list(value.object_state.position_world),
            "orientation": {"x": x, "y": y, "z": z, "w": w},
            "simulation_time_s": value.simulation_time_s,
            "frame_id": value.frame_id,
            "object_id": value.object_state.body,
            "session_id": value.simulation_session_id,
            "reset_epoch": value.reset_epoch,
            "publisher_sequence": value.publisher_sequence,
            "simulation_step": value.simulation_step,
        }

    def _capture_teacher_start(self):
        """Refuse an invalid config, then read the one start observation before any arm or gripper motion.

        Returns the snapshot, or None when the object was built without the Teacher policies (legacy partial
        construction). It raises for a pre-motion config check that fails, and, under a schema 4 Teacher policy, with
        TEACHER_RESET_BOUNDARY_PAUSED_RING (recorded as `teacher_reset_boundary_error`) when the observer ring has no unpaused
        record after its last paused one.
        """

        error = getattr(self, "_teacher_config_error", None)
        if error is not None:
            self._document["teacher_config_error"] = error
            raise RuntimeError(error)
        policy = getattr(self, "_teacher_endpoint_policy", None)
        if policy is None:
            return None
        from so101_demo.act.teacher_endpoint import validate_task_targets

        start_target, end_target = self._teacher_targets()
        try:
            validate_task_targets(policy, start_target, end_target)
        except ValueError as invalid:
            self._document["teacher_config_error"] = str(invalid)
            self._write()
            raise RuntimeError(str(invalid)) from invalid
        self._document["teacher_targets"] = {"start_target": start_target, "end_target": end_target}
        self._check_episode_start_pose()
        snapshot = self._snapshot()
        self._document["teacher_start_observation"] = self._teacher_observation(snapshot)
        self._write()
        observation = self._document["teacher_start_observation"]
        boundary = self._verified_reset_boundary() or observation
        self._stream_emit("reset_complete", {
            "session_id": boundary["session_id"], "reset_epoch": boundary["reset_epoch"],
            "simulation_time_s": boundary["simulation_time_s"],
            "simulation_step": boundary["simulation_step"],
            "publisher_sequence": boundary["publisher_sequence"],
            # the receipt of that first evidence on the monotonic clock, for the Recorder's causal ordering
            "received_monotonic_ns": boundary.get("received_monotonic_ns", time.monotonic_ns())})
        self._stream_emit("teacher_start_observation", {"observation": copy.deepcopy(observation)})
        return snapshot

    def _record_episode_diversity(self, values) -> None:
        """R3-a: keep this episode's derived values (planning reads them) and put them, with their digest, on the Teacher document.

        The values are a pure function of (campaign seed, scene id) and were range-checked when derived; the document is what the
        episode identity and the case inputs are compared with."""

        import hashlib
        import json

        self._episode_diversity = values
        canonical = json.dumps(values, sort_keys=True, separators=(",", ":"), allow_nan=False)
        self._document["teacher_diversity"] = {"values": values, "values_sha256": hashlib.sha256(canonical.encode()).hexdigest()}
        self._write()

    def _record_teacher_source(self, entry, *, published_truth_gap_m) -> None:
        """Indoor P3: this episode's Teacher source and appearance draw (from the frozen scene list, re-derived from its plan) on the Teacher
        document, with the distance of the pose the Teacher was given from the simulator's cup position at the start. The offline processor
        compares it with the same row when it opens the episode."""

        appearance = entry["appearance"]
        self._document["teacher_source"] = {
            "source": entry["teacher_source"], "kind": appearance["kind"], "plan_sha256": appearance["plan_sha256"],
            "draw_sha256": appearance["draw_sha256"], "variant_sha256": appearance["variant_sha256"],
            "published_vs_simulator_m": published_truth_gap_m,
            # D1: the proof (both hashes, equal stripped physics fingerprints) of the declared model identity the scene state was published under
            "model_equivalence": entry.get("model_equivalence")}
        self._write()

    def _check_episode_start_pose(self) -> None:
        """R3-a, before any motion: the arm stands on one of the start poses this episode's seed draws.

        The reset path applied the first draw that passed the joint-limit and collision checks; the Teacher cannot see which, so it matches
        the measured joints back to a draw (within `START_MATCH_TOLERANCE_RAD`) and records the index. A start that matches none (the
        reset was not given the pose, or the arm is somewhere else) fails closed as ``TEACHER_DIVERSITY_START_POSE_MISMATCH``."""

        values = getattr(self, "_episode_diversity", None)
        if values is None:
            return
        from so101_demo.act.teacher_diversity import start_pose_matches

        measured = (*(float(item) for item in self._joint_state()), float(self._positions.get("6", 0.0)))
        # exactly the draw the reset applied (carried in the values): another draw that happens to be close is not it
        selected = values["start_pose"]["draw_index"]
        draw = selected if start_pose_matches(self._execution_policy["diversity"], values["scene_id"], measured, selected) else None
        record = self._document.setdefault("teacher_diversity", {})
        record["start_pose_measured_rad"] = list(measured)
        record["start_pose_draw_index"] = draw
        if draw is None:
            self._write()
            raise RuntimeError("TEACHER_DIVERSITY_START_POSE_MISMATCH")
        self._write()

    def _verified_reset_boundary(self):
        """The first retained `SimulationEvidence` of this session and the expected reset epoch, or None.

        This is the reset boundary the Teacher announces as `reset_complete`: the first sample the Teacher's own
        observer saw after the reset, not a later snapshot, and independent of whoever ran the reset.
        """
        try:
            retained = self.observer.retained_with_receipts()
        except Exception:
            return None
        matching = [record for record in retained
                    if record.evidence.simulation_session_id == self._session_id
                    and record.evidence.reset_epoch == self._expected_reset_epoch]
        if self._reset_boundary_follows_pause() and any(record.evidence.paused for record in matching):
            # Schema >= 4: the worker's perception pause ends inside the observer ring, so the first retained record
            # precedes it and the offline scan could not clip the window. The boundary is the first record after the
            # last paused one; a ring with no such record fails closed instead of announcing a paused boundary.
            last_paused = max(index for index, record in enumerate(matching) if record.evidence.paused)
            matching = matching[last_paused + 1:]
            if not matching:
                self._document["teacher_reset_boundary_error"] = "TEACHER_RESET_BOUNDARY_PAUSED_RING"
                self._write()
                raise RuntimeError("TEACHER_RESET_BOUNDARY_PAUSED_RING")
        for record in matching[:1]:
            return {**self._teacher_observation(record.evidence),
                    "received_monotonic_ns": round(record.received_monotonic_s * 1e9)}
        return None

    def _reset_boundary_follows_pause(self) -> bool:
        """True for a Teacher execution policy of schema 4 (EXECUTION_SCHEMA_SPEED) or later."""

        from so101_demo.act.teacher_endpoint import EXECUTION_SCHEMA_SPEED

        version = (getattr(self, "_execution_policy", None) or {}).get("schema_version")
        return type(version) is int and version >= EXECUTION_SCHEMA_SPEED

    def _controllers_stopped_at(self, execution_policy):
        """Receipt time (the observer's monotonic clock) of the fresh joint state that showed every arm and gripper
        joint below the stop velocity, or None.

        Bounded by the execution policy's state_unavailable_stop_s; missing, stale or undersized velocity data
        never counts as stopped. A stop flag ends the wait.
        """

        clock = getattr(self, "_monotonic", time.monotonic)
        deadline = clock() + execution_policy["state_unavailable_stop_s"]
        while True:
            received = getattr(self, "_joint_state_received_monotonic_s", None)
            velocities = getattr(self, "_joint_velocities", {})
            fresh = received is not None and 0.0 <= clock() - received <= execution_policy["state_max_age_s"]
            if fresh and all(
                    isinstance(velocities.get(name), (int, float)) and math.isfinite(velocities[name])
                    and abs(velocities[name]) <= _TEACHER_STOP_VELOCITY_RAD_S
                    for name in (*self._ARM_JOINTS, "6")):
                return received
            if clock() >= deadline:
                return None
            self._wait_progress()

    def _controllers_stopped(self, execution_policy) -> bool:
        """True once fresh joint states show every arm and gripper joint below the stop velocity."""
        return self._controllers_stopped_at(execution_policy) is not None

    def _settled_snapshot(self, settle_s: float, stall_s: float):
        """One world snapshot taken settle_s of simulation time after the first fresh one.

        The clock is the MuJoCo publisher's simulation time carried by the world snapshots, so the wait is in
        simulation time whatever the node clock is. It fails if simulation time stops advancing for stall_s.
        """

        clock = getattr(self, "_monotonic", time.monotonic)
        latest = self._snapshot()
        target_s = latest.simulation_time_s + settle_s
        advanced_at = clock()
        while latest.simulation_time_s < target_s:
            if clock() - advanced_at > stall_s:
                raise RuntimeError("TEACHER_END_SETTLE_CLOCK_STALLED")
            candidate = self._snapshot()
            if candidate.simulation_time_s > latest.simulation_time_s:
                latest, advanced_at = candidate, clock()
        return latest

    def _take_teacher_end_observation(self):
        """(observation or None, problem or None): stop check first, then settle_s, then ONE snapshot."""

        policy = getattr(self, "_teacher_endpoint_policy", None)
        execution_policy = getattr(self, "_execution_policy", None)
        if policy is None or execution_policy is None:
            return None, "TEACHER_ENDPOINT_POLICY_UNAVAILABLE"
        try:
            if not self._controllers_stopped(execution_policy):
                return None, "TEACHER_END_CONTROLLER_STOP_UNCONFIRMED"
            snapshot = self._settled_snapshot(policy["tolerances"]["settle_s"],
                                              execution_policy["state_unavailable_stop_s"])
        except Exception as error:
            return None, f"TEACHER_END_OBSERVATION_UNAVAILABLE: {error}"
        return self._teacher_observation(snapshot), None

    @staticmethod
    def _teacher_execution_status(result, failure_evidence) -> str:
        if result.status.value == "DONE":
            return "COMPLETED"
        code = "" if result.failure is None else result.failure.code
        config_code = code.startswith(("TEACHER_ENDPOINT_", "TEACHER_POLICY_", "TEACHER_EXECUTION_POLICY_"))
        if code in ("TEACHER_USER_STOP", "TEACHER_PARENT_DIED"):
            return "STOPPED_USER"
        if code == "TEACHER_DEADLINE":
            return "DEADLINE"
        # Teacher run (design 5b): a simulation-integrity failure and an execution precondition that did not hold are FAILED, not a stop
        if code in SIM_INTEGRITY_CODES or code in _TEACHER_FAILED_CODES:
            return "FAILED"
        if not config_code and code != "TEACHER_CANCEL_UNSETTLED" and (code in TERMINAL_STOP_CODES or code.startswith(
                ("DYNAMIC_RELEASE_", "DYNAMIC_NORMAL_STOP_", "TEACHER_"))):
            return "STOPPED_SAFETY"
        action_absent = bool((failure_evidence or {}).get("physical_action_proven_absent"))
        if code in _CONTROLLER_UNSETTLED_CODES and not action_absent:
            return "INDETERMINATE"
        return "FAILED"

    def _teacher_manifest_fields(self, result, failure_evidence, end_observation, end_problem) -> dict[str, object]:
        """The Teacher fields. PASS only for a COMPLETED execution whose endpoint judgement is PASS."""

        from so101_demo.act.teacher_endpoint import RULE_VERSION, evaluate_teacher_endpoint

        execution = self._teacher_execution_status(result, failure_evidence)
        start_observation = self._document.get("teacher_start_observation")
        targets = self._document.get("teacher_targets") or {}
        policy = getattr(self, "_teacher_endpoint_policy", None)
        reasons: list[str] = []
        try:
            if policy is None or not targets:
                raise ValueError(self._document.get("teacher_config_error") or getattr(
                    self, "_teacher_config_error", None) or "TEACHER_ENDPOINT_TARGETS_UNAVAILABLE")
            task = evaluate_teacher_endpoint(
                policy, start_target=targets["start_target"], end_target=targets["end_target"],
                start_observation=start_observation, end_observation=end_observation)
        except Exception as error:
            reasons.append(str(error))
            task = {
                "rule_version": RULE_VERSION, "policy_sha256": None if policy is None else policy["policy_sha256"],
                "result": "UNCONFIRMED", "reasons": reasons, "measured": None,
                "start_target": targets.get("start_target"), "end_target": targets.get("end_target"),
                "start_observation": start_observation, "end_observation": end_observation,
            }
        if end_problem is not None:
            task["reasons"] = [end_problem, *task["reasons"]]
        if execution != "COMPLETED" and task["result"] == "PASS":
            task["result"] = "UNCONFIRMED"
            task["reasons"] = ["TEACHER_EXECUTION_NOT_COMPLETED", *task["reasons"]]
        teacher_run_fields: dict[str, object] = {}
        if self._teacher_run():
            code = "" if result.failure is None else result.failure.code
            teacher_run_fields = {
                # SIM_INTEGRITY is a failure class of FAILED, not a new status (design 5b): the attempt is infrastructure, not Teacher
                "failure_class": "sim_integrity" if code in SIM_INTEGRITY_CODES else None,
                "teacher_process_summary": self._document.get("teacher_process_summary"),
            }
        return {
            **teacher_run_fields,
            "schema": SCHEMA_TEACHER if self._teacher_run() else SCHEMA_GENERAL,
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "teacher_execution_status": execution,
            "teacher_task_result": task,
            "teacher_start_observation": start_observation,
            "teacher_end_observation": end_observation,
            # The Teacher holds no data side. The data status of an attempt is the independent Recorder's
            # (`recorder-result.json`), mapped by the orchestrator; this field only says the Teacher recorded nothing.
            "act_data_status": "DISABLED",
            "process_diagnostics": self._document.setdefault("process_diagnostics", []),
            "teacher_policies": getattr(self, "_teacher_policy_files", {}),
        }

    @staticmethod
    def _contact_documents(items) -> list[dict[str, object]]:
        return [
            {
                "geom1": getattr(item, "geom1", None),
                "geom2": getattr(item, "geom2", None),
                "position_world_m": (None if getattr(item, "position_world", None) is None
                                     else list(item.position_world)),
                "signed_distance_m": getattr(item, "signed_distance_m", None),
                "normal_force_n": getattr(item, "normal_force_n", None),
            }
            for item in items
        ]

    def _perform_teacher_state(self, state: State) -> None:
        policy = self._execution_policy
        if state is State.WAIT_GRASP_STABLE:
            dwell = float(policy["grasp_stable_dwell_s"])
            before, after = self._fixed_dwell(dwell)
            self._note_pose("grasp_stable", after)
            self._record(state, before, after, dwell_s=dwell)
        elif state is State.WAIT_RELEASE_SETTLE:
            dwell = float(policy["release_settle_dwell_s"])
            before, after = self._fixed_dwell(dwell)
            self._final_samples.append(self._evidence(after))
            self._record(state, before, after, dwell_s=dwell)
        else:
            # OPEN_GRIPPER: the release marker is the evidence sample at the open (the data side requires it); no support,
            # bilateral or post-stop-source check
            source = self._snapshot()
            self._release_marker_sequence = source.publisher_sequence
            table = [item for item in source.other_object_contacts if item.geom2 == "table_collision"]
            self._note_pose("release_start", source, table_contact=bool(table),
                            table_normal_force_n=sum(float(item.normal_force_n) for item in table),
                            left_contacts=len(source.left_fingertip_contacts), right_contacts=len(source.right_fingertip_contacts))
            self._write()
            self._command_gripper(state, self._RELEASE_Q6, before=source)

    def _teacher_place_target(self, target, policy) -> PoseEvidence:
        """Design section 4: the tilt-compensated target is a strategy. Outside what was calibrated, or when the measurement
        fails, the fallback target (hover z + ``place_reference_offset_m``) is used and the closed reason is recorded (``teacher_place_height``).
        Nothing here refuses; a stop (operator, joint state, simulation integrity) keeps its own code."""
        from so101_demo.core import place_height as ph

        x, y, z = target.position_m
        height_policy = ph.PlaceHeightPolicy.from_document(policy)
        old_target = z + height_policy.reference_offset_m
        geometry = None
        try:
            geometry = self._place_geometry()
            theta, k = self._measure_place_height()
            document = ph.plan_place_height(theta, k, old_target, geometry, height_policy)
        except Exception as error:
            code, _ = self._failure_code(error)
            if isinstance(error, TeacherStop) or code in TERMINAL_STOP_CODES_TEACHER:
                raise
            if isinstance(error, _JointStateStale):
                reason = ph.FB_JOINT_STATE_STALE
            elif isinstance(error, PlaceHeightRefused) and error.code == ph.TILT_UNSTABLE:
                reason = ph.FB_TILT_UNSTABLE
            else:
                reason = ph.FB_MEASUREMENT_FAILED
            document = ph.fallback_record(reason, old_target, height_policy, geometry=geometry,
                                          detail=f"{type(error).__name__}: {error}"[:300])
        self._document["place_height"] = document
        self._write()
        return PoseEvidence((x, y, document["target_tcp_z_m"]), target.orientation_xyzw)
