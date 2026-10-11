"""The supported release: stop proof, preflight, gripper opening and final validation."""

from __future__ import annotations

import copy
from dataclasses import asdict
import json
import math

from so101_demo.application.e2e_acceptance import (
    FINAL_MAX_ANGULAR_SPEED_RAD_S,
    FINAL_MAX_LINEAR_SPEED_M_S,
    FINAL_MAX_UPRIGHT_TILT_RAD,
    FINAL_SUPPORT_HEIGHT_RANGE_M,
    FINAL_XY_TOLERANCE_M,
)
from so101_demo.core.domain import State
from so101_demo.core.dynamic_pick import (
    compose_pose,
    inverse_pose,
)


class ReleaseSequence:
    def _normal_stop_proof(self):
        """The proof that the arm is stopped: a terminal `ExecuteTrajectory` result (SUCCEEDED, or a controller
        failure that left the arm held) followed by fresh `/joint_states` below the stop velocity.

        `stop_confirmed_wall_s` is the receipt time of the confirming joint state on the same monotonic clock as the
        observer receipts, which `_first_source_after_stop` uses to choose the first post-stop source.
        """
        from so101_demo.backends.mujoco.observer import EvidenceStale

        # Teacher run: the age bound is the execution policy's (the release policy is not part of it)
        age = float(self._execution_policy["state_max_age_s"]) if self._teacher_run() else self._release_bounds()[0]
        scope = self._release_scope()
        result = getattr(self, "_last_arm_result", None)
        if result not in ("SUCCEEDED", "CONTROLLER_FAILED"):
            raise RuntimeError("DYNAMIC_NORMAL_STOP_UNCONFIRMED")
        confirmed = self._controllers_stopped_at(self._execution_policy)
        if confirmed is None:
            raise RuntimeError("DYNAMIC_NORMAL_STOP_UNCONFIRMED")
        if not 0 <= self._monotonic() - confirmed <= age:
            raise RuntimeError("DYNAMIC_NORMAL_STOP_SOURCE_INVALID")
        try:
            record = self.observer.snapshot_with_receipt()
        except EvidenceStale as error:
            raise RuntimeError("DYNAMIC_NORMAL_STOP_UNCONFIRMED") from error
        world = record.evidence
        if (world.simulation_session_id, world.reset_epoch) != (scope[0], scope[1]):
            raise RuntimeError("DYNAMIC_NORMAL_STOP_SOURCE_INVALID")
        names = (*self._ARM_JOINTS, "6")
        # One instant on both clocks: the monotonic time now (never before the world receipt or the stop confirmation)
        # and the simulation clock read at that instant, after the node's queued `/clock` callbacks ran. The older world
        # record's own time alone would sit behind this instant by the steps simulated since it was received.
        self._refresh_node_clock()
        instant_ns = max(round(self._monotonic() * 1e9), round(record.received_monotonic_s * 1e9),
                         round(confirmed * 1e9))
        sim_ns = round(world.simulation_time_s * 1e9)
        try:
            sim_ns = max(sim_ns, int(self._node.get_clock().now().nanoseconds))
        except Exception:
            pass
        stop_clock = {"sim_time_ns": sim_ns, "begin_monotonic_ns": instant_ns, "end_monotonic_ns": instant_ns}
        proof = {
            "kind": "TEACHER_NORMAL_STOP",
            "scope": {"session_id": scope[0], "reset_epoch": scope[1], "attempt_id": scope[2]},
            "epoch": {"session_id": scope[0], "reset_epoch": scope[1]},
            "trajectory_result": result,
            "stop_confirmed_wall_s": float(confirmed),
            "joint_positions": {name: float(self._positions[name]) for name in names},
            "joint_velocities": {name: float(self._joint_velocities[name]) for name in names},
            "sim_stamp_s": world.simulation_time_s,
            "simulation_step": world.simulation_step,
            # the world sample this stop is anchored to, for the Recorder's own copy of the same evidence
            "publisher_sequence": world.publisher_sequence,
            "received_wall_s": float(record.received_monotonic_s),
            "source_clock": stop_clock,
        }
        self._document.setdefault("normal_stop_proofs", []).append(proof)
        return proof

    def _first_source_after_stop(self, proof, *, previous_step, previous_sequence):
        from so101_demo.adapters.act.scene_state import (
            SCENE_SOURCE_ABSENT_AFTER_S,
            SceneStateObserver,
        )

        age, _ = self._release_bounds()
        scene_observer = getattr(self, "_scene_source_observer", None)
        if not isinstance(scene_observer, SceneStateObserver):
            raise RuntimeError("DYNAMIC_RELEASE_SOURCE_CLOCK_REQUIRED")
        silent_for_s = scene_observer.silent_for_s()
        if silent_for_s is not None and silent_for_s >= SCENE_SOURCE_ABSENT_AFTER_S:
            # No scene frame was ever accepted since the source was armed: there is no publisher, and waiting out the
            # age bound would only end as a late DYNAMIC_RELEASE_SOURCE_EXPIRED that hides the cause.
            facts = {"silent_for_s": silent_for_s, "frames_accepted": 0,
                     "absent_after_s": SCENE_SOURCE_ABSENT_AFTER_S,
                     "stop_confirmed_wall_s": proof["stop_confirmed_wall_s"]}
            self._document["scene_source_absent"] = facts
            raise RuntimeError("DYNAMIC_SCENE_SOURCE_ABSENT: " + json.dumps(facts, sort_keys=True, default=str))
        deadline = self._monotonic() + age
        # The owner may read its epoch after confirming stop. That later observation
        # cannot move FIRST past a source already generated after stop confirmation.
        minimum_step = previous_step
        pending_source = None
        facts = {"iterations": 0, "last_scene_error": None, "scene_steps_held": [], "waiting_for_scene_frame": 0,
                 "skipped_before_stop": 0, "pending_step": None, "pending_sequence": None, "newest_evidence_step": None,
                 "newest_evidence_sequence": None, "previous_step": previous_step, "previous_sequence": previous_sequence,
                 "stop_confirmed_wall_s": proof["stop_confirmed_wall_s"]}
        while self._monotonic() <= deadline:
            now = self._monotonic()
            facts["iterations"] += 1
            current = self.observer.recent_with_receipts()
            if current:
                facts["newest_evidence_step"] = current[-1].evidence.simulation_step
                facts["newest_evidence_sequence"] = current[-1].evidence.publisher_sequence
                facts["newest_evidence_age_s"] = now - current[-1].received_monotonic_s
            if pending_source is not None and not 0 <= now - pending_source.received_monotonic_s <= age:
                # the candidate aged out while its scene frame never matched (seen at the deadline in two collection rounds): the same facts, so that a stalled executor (everything old) and a lost frame (newer
                # frames present, this one absent) can be told apart
                facts["ended_by"] = "pending_candidate_expired"
                facts["pending_age_s"] = now - pending_source.received_monotonic_s
                self._document["post_stop_source_unavailable"] = facts
                raise RuntimeError("DYNAMIC_RELEASE_SOURCE_EXPIRED: " + json.dumps(facts, sort_keys=True, default=str))
            for received in ((pending_source,) if pending_source is not None else current):
                source = received.evidence
                if (source.simulation_session_id, source.reset_epoch) != (
                        self._session_id, self._expected_reset_epoch):
                    raise RuntimeError("DYNAMIC_RELEASE_SOURCE_SCOPE_INVALID")
                if source.paused or source.truncated:
                    raise RuntimeError("DYNAMIC_RELEASE_SOURCE_INVALID")
                if (source.simulation_step > minimum_step and source.publisher_sequence > previous_sequence
                        and received.received_monotonic_s >= proof["stop_confirmed_wall_s"]
                        and 0 <= now - received.received_monotonic_s <= age):
                    pending_source = received
                    facts["pending_step"], facts["pending_sequence"] = source.simulation_step, source.publisher_sequence
                    try:
                        scenes = scene_observer.recent_frames_with_receipts()
                    except ValueError as error:
                        if str(error) in ("SCENE_STATE_UNAVAILABLE", "SCENE_STATE_STALE"):
                            facts["last_scene_error"] = str(error)
                            break  # wait for this candidate's association, never skip to a later source
                        raise RuntimeError("DYNAMIC_RELEASE_SOURCE_CLOCK_INVALID") from error
                    facts["scene_steps_held"] = [frame["simulation_step"] for frame, _ in scenes][-8:]
                    if scenes:
                        facts["scene_newest_step"] = scenes[-1][0]["simulation_step"]
                        facts["scene_newest_age_s"] = now - scenes[-1][1]
                    matched = [(frame, receipt) for frame, receipt in scenes if
                        (frame["simulation_session_id"], frame["reset_epoch"], frame["simulation_step"])
                        == (source.simulation_session_id, source.reset_epoch, source.simulation_step)]
                    if not matched:
                        facts["waiting_for_scene_frame"] += 1
                        break
                    if len(matched) != 1:
                        raise RuntimeError("DYNAMIC_RELEASE_SOURCE_CLOCK_INVALID")
                    scene, scene_receipt = matched[0]
                    begin, end = (scene["clock_interval_begin_monotonic_ns"],
                                  scene["clock_interval_end_monotonic_ns"])
                    if (scene["paused"] or scene["model_sha256"] != scene_observer.model_sha256
                            or round(scene["simulation_time_s"] * 1e9) != round(source.simulation_time_s * 1e9)
                            or not 0 < begin <= end <= round(scene_receipt * 1e9)
                            or begin > round(received.received_monotonic_s * 1e9)):
                        raise RuntimeError("DYNAMIC_RELEASE_SOURCE_CLOCK_INVALID")
                    if begin < round(proof["stop_confirmed_wall_s"] * 1e9):
                        facts["skipped_before_stop"] += 1
                        pending_source = None
                        continue  # actually generated before stop; a later receipt cannot change that
                    if not 0 <= now - end * 1e-9 <= age:
                        raise RuntimeError("DYNAMIC_RELEASE_SOURCE_CLOCK_INVALID")
                    # Selection is independent of support/pose quality. A bad first eligible source
                    # is refused by the next gate, never skipped for a later good sample.
                    self._document.setdefault("post_stop_sources", []).append({
                        "source_physics": asdict(source),
                        "received_monotonic_s": received.received_monotonic_s,
                        "source_scene": scene,
                        "scene_received_monotonic_s": scene_receipt,
                        "stop_confirmed_wall_s": proof["stop_confirmed_wall_s"]})
                    self._selected_release_source = received
                    self._selected_release_source_clock = (begin, end, scene_receipt)
                    self._selected_release_source_scene = (copy.deepcopy(scene), scene_receipt)
                    self._selected_release_stop_proof = copy.deepcopy(proof)
                    return source
            self._wait_progress()
        # the code stays DYNAMIC_RELEASE_POST_STOP_SOURCE_UNAVAILABLE (what follows the colon is detail only); the facts say what the
        # loop was waiting for, so that the next occurrence can be explained
        facts["ended_by"] = "deadline"
        self._document["post_stop_source_unavailable"] = facts
        raise RuntimeError("DYNAMIC_RELEASE_POST_STOP_SOURCE_UNAVAILABLE: " + json.dumps(facts, sort_keys=True, default=str))

    def _check_selected_release_freshness(self, source):
        age, _ = self._release_bounds()
        selected = getattr(self, "_selected_release_source", None)
        if (selected is None or selected.evidence != source
                or not 0 <= self._monotonic() - selected.received_monotonic_s <= age):
            raise RuntimeError("DYNAMIC_RELEASE_SOURCE_EXPIRED")
        clock = getattr(self, "_selected_release_source_clock", None)
        if clock is not None and (not 0 <= self._monotonic() - clock[1] * 1e-9 <= age
                                  or not 0 <= self._monotonic() - clock[2] <= age):
            raise RuntimeError("DYNAMIC_RELEASE_SOURCE_EXPIRED")

    def _require_supported_bilateral(self, source):
        from so101_demo.act.pick_place_live_evidence import actual_table_support

        _, distance = self._release_bounds()
        if (not actual_table_support(source, support_distance_max_m=distance)
                or not source.left_fingertip_contacts or not source.right_fingertip_contacts):
            raise RuntimeError("DYNAMIC_RELEASE_SUPPORT_NOT_PROVED")

    def _supported_release_preflight(self):
        self._release_authorization = None
        self._release_bounds()
        scope = self._release_scope()
        if self._attached is not True:
            raise RuntimeError("DYNAMIC_RELEASE_ATTACHMENT_NOT_PROVED")
        baseline = self._snapshot()
        proof = self._normal_stop_proof()
        source = self._first_source_after_stop(proof, previous_step=baseline.simulation_step,
                                              previous_sequence=baseline.publisher_sequence)
        self._require_supported_bilateral(source)
        self._release_authorization = (*scope, source.simulation_step, source.publisher_sequence)
        return source

    def _confirm_detached_shadow(self):
        from so101_demo.control.planning_scene.task_scene import verify_task_scene

        if self._attached is not False or self._release_scene_geometry is None:
            return False
        self._scene_membership()
        return verify_task_scene(self._last_scene_response, self._release_scene_geometry).success

    def _open_supported_gripper(self, state):
        self._release_bounds()
        scope = self._release_scope()
        if state is State.RECOVER_OPEN_GRIPPER:
            # Recovery has no forward preflight, but it opens only on the same proofs: arm stopped, a first post-stop
            # source, and the cup force-bearing on the table with both fingertip sides in contact. Without them it
            # does not open: the gripper holds and the run ends in ERROR.
            self._release_authorization = None
            baseline = self._snapshot()
            previous_step, previous_sequence = baseline.simulation_step, baseline.publisher_sequence
        else:
            authorization = self._release_authorization
            self._release_authorization = None
            if authorization is None or authorization[:3] != scope:
                raise RuntimeError("DYNAMIC_RELEASE_PREFLIGHT_REQUIRED")
            if self._attached is not False or self._confirm_detached_shadow() is not True:
                raise RuntimeError("DYNAMIC_RELEASE_DETACH_NOT_PROVED")
            previous_step, previous_sequence = authorization[3], authorization[4]
        proof = self._normal_stop_proof()
        source = self._first_source_after_stop(proof, previous_step=previous_step,
                                              previous_sequence=previous_sequence)
        self._require_supported_bilateral(source)
        self._release_marker_sequence = source.publisher_sequence
        self._write()
        self._check_selected_release_freshness(source)
        self._command_gripper(state, self._RELEASE_Q6, before=source)

    def _wait_release(self, state: State) -> None:
        before = self._snapshot()

        def released(value) -> bool:
            linear = max(abs(item) for item in value.object_state.linear_velocity_world)
            angular = max(abs(item) for item in value.object_state.angular_velocity_world)
            return (
                self._table_contact(value)
                and not value.left_fingertip_contacts
                and not value.right_fingertip_contacts
                and linear <= FINAL_MAX_LINEAR_SPEED_M_S
                and angular <= FINAL_MAX_ANGULAR_SPEED_RAD_S
            )

        try:
            after = self._wait_stable(released, 0.20, 4.0)
        except RuntimeError as error:
            if str(error) != "DYNAMIC_STABLE_STATE_TIMEOUT":
                raise
            # The stability window is an observation now (D3); the task result is the endpoint pose.
            after = self._snapshot()
            self._record_process_diagnostic(
                "DYNAMIC_SETTLE_WINDOW_NOT_MET", state, sample=after,
                facts={"window_s": 0.20, "timeout_s": 4.0})
        self._final_samples.append(self._evidence(after))
        self._record(state, before, after)

    def _validate_final(self, state: State) -> None:
        before = self._snapshot()
        expected = compose_pose(
            self._template.place_tcp_world,
            inverse_pose(self._template.cup_to_tcp_grasp),
        )
        actual = before.object_state
        xy_error = math.dist(actual.position_world[:2], expected.values[:2])
        q = actual.orientation_xyzw
        upright = self._upright_tilt_rad(q)
        if not self._teacher_run() and (
            xy_error > FINAL_XY_TOLERANCE_M
            or not (
                FINAL_SUPPORT_HEIGHT_RANGE_M[0]
                <= actual.position_world[2]
                <= FINAL_SUPPORT_HEIGHT_RANGE_M[1]
            )
            or upright > FINAL_MAX_UPRIGHT_TILT_RAD
            or not self._table_contact(before)
            or before.left_fingertip_contacts
            or before.right_fingertip_contacts
        ):
            # Audit-only (D3): the pass/fail verdict is the Teacher endpoint rule applied at the end of the run.
            self._record_process_diagnostic(
                "DYNAMIC_FINAL_PLACEMENT_NOT_PROVED", state, sample=before,
                facts={"xy_error_m": xy_error, "height_m": actual.position_world[2], "upright_tilt_rad": upright,
                       "table_contact": self._table_contact(before),
                       "left_contact_count": len(before.left_fingertip_contacts),
                       "right_contact_count": len(before.right_fingertip_contacts)})
        self._record(
            state,
            before,
            before,
            expected_cup_pose_world=list(expected.values),
            final_xy_error_m=xy_error,
            final_upright_tilt_rad=upright,
        )
