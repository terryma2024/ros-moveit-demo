"""Read-only 500 Hz SEARCH history anchored to one selected scene frame.

The production SEARCH source lifecycle is not wired to this verifier yet.
"""

from __future__ import annotations

import copy

from so101_demo.act.contracts import finite, vector

from .contact_evidence import RobotContactObserver, contact_hazard
from .physics_clock_history import PhysicsClockHistory
from .scene_state import SceneStateObserver
from .selected_physics_join import join_selected_physics_sample
from .selected_search_source import freeze_selected_search_source


_FRAME_COUNT = 51
_STEP_NS = 2_000_000
_SPAN_NS = 100_000_000


def _integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("integer invalid")
    return value


def _simulation_ns(value):
    return round(finite(value, nonnegative=True) * 1_000_000_000)


def _receipt_ns(value, *, now_ns, max_age_ns):
    stamp = _simulation_ns(value)
    if not 0 <= now_ns - stamp <= max_age_ns:
        raise ValueError("contact receipt stale or future")
    return stamp


def verify_cadence_correct_search_history(
    observed, selected_source, physics_history, scene_observer, contact_observer,
    *, expected_model_sha256, max_source_skew_s, max_source_age_ns,
    allowed_contact_pairs, robot_dof_indices, stop_velocity_rad_s,
    stopped_wall_s, clock_ns,
):
    """Require one exact post-ACK 100 ms physics/contact interval, without authority."""
    try:
        now_ns = _integer(clock_ns(), 1)
        max_age_ns = _integer(max_source_age_ns, 1)
        stop_wall = finite(stopped_wall_s, nonnegative=True)
        stop_velocity = finite(stop_velocity_rad_s)
        skew = finite(max_source_skew_s)
        if (stop_velocity <= 0 or skew <= 0
                or not isinstance(physics_history, PhysicsClockHistory)
                or not isinstance(scene_observer, SceneStateObserver)
                or not isinstance(contact_observer, RobotContactObserver)
                or not isinstance(allowed_contact_pairs, (set, frozenset))
                or frozenset(allowed_contact_pairs) != contact_observer.allowed
                or type(robot_dof_indices) is not tuple
                or len(robot_dof_indices) != 7
                or any(type(index) is not int or not 0 <= index < physics_history.nv
                       for index in robot_dof_indices)
                or len(set(robot_dof_indices)) != 7):
            raise ValueError("history configuration invalid")

        current_source = freeze_selected_search_source(
            observed, max_skew_s=skew)
        if type(selected_source) is not dict or selected_source != current_source:
            raise ValueError("selected source changed")
        joined = join_selected_physics_sample(
            observed.physical_readback, physics_history, scene_observer,
            contact_observer, expected_model_sha256=expected_model_sha256,
            max_source_age_ns=max_age_ns, clock_ns=clock_ns)
        scope = (current_source["session_id"], current_source["reset_epoch"])
        end_step = current_source["physics_step"]
        first_step = end_step - (_FRAME_COUNT - 1)
        if first_step < 1 or joined["physics_sample"].physics_step != end_step:
            raise ValueError("history window invalid")

        marker = copy.deepcopy(observed.physics_step_fence)
        if (type(marker) is not dict or marker.get("session_id") != scope[0]
                or marker.get("reset_epoch") != scope[1]
                or marker.get("request_sequence") != 1
                or marker.get("command_authority") is not False):
            raise ValueError("marker scope invalid")
        marked_step = _integer(marker["marked_physics_step"], 1)
        if marked_step >= first_step:
            raise ValueError("marker does not precede window")
        marked = physics_history.step_at(marked_step)["sample"]
        marked_ns = _simulation_ns(marker["marked_simulation_time_s"])
        sent_wall = finite(marker["request_sent_wall_s"], nonnegative=True)
        ack_wall = finite(marker["ack_received_wall_s"], nonnegative=True)
        sent_ns = _integer(marker["request_sent_monotonic_ns"], 1)
        ack_ns = _integer(marker["ack_received_monotonic_ns"], 1)
        begin_ns = _integer(marker["clock_interval_begin_monotonic_ns"], 1)
        end_ns = _integer(marker["clock_interval_end_monotonic_ns"], 1)
        marked_begin_ns = _integer(
            marker["marked_sample_clock_interval_begin_monotonic_ns"], 1)
        marked_end_ns = _integer(
            marker["marked_sample_clock_interval_end_monotonic_ns"], 1)
        if (sent_wall < stop_wall or ack_wall < sent_wall
                or sent_ns < _simulation_ns(stop_wall)
                or not sent_ns <= begin_ns == marked_begin_ns <=
                   marked_end_ns <= end_ns <= ack_ns <= now_ns
                or (marked.simulation_session_id, marked.reset_epoch,
                    marked.physics_step) != (*scope, marked_step)
                or _simulation_ns(marked.simulation_time_s) != marked_ns
                or marked.clock_interval_begin_monotonic_ns != marked_begin_ns
                or marked.clock_interval_end_monotonic_ns != marked_end_ns
                or tuple(marked.model_qpos) != vector(marker["model_qpos"],
                                                      physics_history.nq)
                or tuple(marked.model_qvel) != vector(marker["model_qvel"],
                                                      physics_history.nv)):
            raise ValueError("marker sample changed")

        physics_entries = tuple(
            entry for entry in physics_history.recent_with_receipts()
            if first_step <= entry["sample"].physics_step <= end_step)
        contact_entries = tuple(
            entry for entry in contact_observer.recent_frames_with_receipts()
            if first_step <= entry[0]["physics_step"] <= end_step)
        if len(physics_entries) != _FRAME_COUNT or len(contact_entries) != _FRAME_COUNT:
            raise ValueError("physical history incomplete")
        first_ns = _simulation_ns(physics_entries[0]["sample"].simulation_time_s)
        end_sim_ns = _simulation_ns(joined["physics_sample"].simulation_time_s)
        if (end_sim_ns - first_ns != _SPAN_NS
                or first_ns - marked_ns != (first_step - marked_step) * _STEP_NS
                or physics_entries[0]["sample"].clock_interval_begin_monotonic_ns
                   < ack_ns):
            raise ValueError("history starts before ACK or off grid")

        base_qpos = base_qvel = None
        previous_source_end = 0
        physics_samples = []
        contact_frames = []
        physics_receipts = []
        contact_receipts = []
        for index, (physics, contact_entry) in enumerate(zip(
            physics_entries, contact_entries, strict=True
        )):
            step = first_step + index
            expected_ns = first_ns + index * _STEP_NS
            sample = physics["sample"]
            contact, receipt = contact_entry
            source_begin = _integer(sample.clock_interval_begin_monotonic_ns, 1)
            source_end = _integer(sample.clock_interval_end_monotonic_ns, 1)
            physics_receipt = _integer(physics["received_monotonic_ns"], 1)
            contact_receipt = _receipt_ns(
                receipt, now_ns=now_ns, max_age_ns=max_age_ns)
            if ((sample.simulation_session_id, sample.reset_epoch,
                 sample.physics_step) != (*scope, step)
                    or _simulation_ns(sample.simulation_time_s) != expected_ns
                    or sample.truncated is not False
                    or sample.diagnostic_hazard_breached is not False
                    or not previous_source_end <= source_begin <= source_end <= now_ns
                    or now_ns - source_end > max_age_ns
                    or not 0 <= now_ns - physics_receipt <= max_age_ns
                    or (contact["simulation_session_id"], contact["reset_epoch"],
                        contact["physics_step"]) != (*scope, step)
                    or _simulation_ns(contact["simulation_time_s"]) != expected_ns
                    or contact_hazard(contact, allowed_contact_pairs)
                    or contact_receipt < ack_ns):
                raise ValueError("physical interval invalid")
            qpos = vector(tuple(sample.model_qpos), physics_history.nq)
            qvel = vector(tuple(sample.model_qvel), physics_history.nv)
            if (any(abs(qvel[dof]) > stop_velocity for dof in robot_dof_indices)
                    or base_qpos is not None and
                    (qpos != base_qpos or qvel != base_qvel)):
                raise ValueError("physical interval moving or drifting")
            if base_qpos is None:
                base_qpos, base_qvel = qpos, qvel
            previous_source_end = source_end
            physics_samples.append(copy.deepcopy(sample))
            contact_frames.append(copy.deepcopy(contact))
            physics_receipts.append(physics_receipt)
            contact_receipts.append(contact_receipt)
        if (physics_samples[-1] != joined["physics_sample"]
                or contact_frames[-1] != joined["readback"]["contact"]
                or physics_history.epoch != scope[1]
                or physics_history.hazard is not None
                or scene_observer.epoch != scope[1]
                or scene_observer.hazard is not None
                or contact_observer.epoch != scope[1]
                or contact_observer.hazard is not None
                or contact_observer.allowed != frozenset(allowed_contact_pairs)
                or observed.physics_step_fence != marker
                or freeze_selected_search_source(
                    observed, max_skew_s=skew) != current_source):
            raise ValueError("history changed during verification")

        return {
            "first_physics_step": first_step,
            "selected_physics_step": end_step,
            "bridge_sim_time_s": first_ns / 1_000_000_000,
            "selected_sim_time_s": end_sim_ns / 1_000_000_000,
            "interval_ns": _SPAN_NS,
            "model_qpos": base_qpos,
            "model_qvel": base_qvel,
            "selected_source_sha256": current_source["observation_sha256"],
            "physics_samples": tuple(physics_samples),
            "contact_frames": tuple(contact_frames),
            "physics_received_monotonic_ns": tuple(physics_receipts),
            "contact_received_monotonic_ns": tuple(contact_receipts),
            "selected_join": joined,
            "controller_interval_proof_required": True,
            "command_authority": False,
            "eligible_for_collection": False,
        }
    except (AttributeError, IndexError, KeyError, TypeError, ValueError,
            RuntimeError, OverflowError) as error:
        raise ValueError("CADENCE_CORRECT_SEARCH_HISTORY_INVALID") from error
