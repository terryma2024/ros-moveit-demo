"""Build the stop configuration, feedback, stationary, submission and stop proof documents."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from pathlib import Path

from so101_demo.act.head_search_stop_measurement.contracts import (
    _GRID_TOLERANCE_S,
    ADMISSION_RULE,
    CAL_FEEDBACK_QUANTISATION_UNDECLARED,
    CONSECUTIVE_RULE,
    FEEDBACK_KIND,
    FEEDBACK_PERIOD_RULE,
    FEEDBACK_PHASE,
    JOINT_SCOPE_RULE,
    LEAD_DEFINITION,
    MONITORED_JOINTS,
    PACING_FAITHFUL_RULE,
    PACING_TOLERANCE,
    QUALIFICATION_RULE,
    SCHEMA_VERSION,
    SINGLE_EXCEEDANCE_RULE,
    STATIONARY_KIND,
    STATIONARY_PHASE,
    STATIONARY_RULE,
    STOP_CONFIG_KIND,
    STOP_CONFIG_PHASE,
    STOP_DECLARATION_RULE,
    STOP_PROOFS_KIND,
    STOP_PROOFS_PHASE,
    SUBMISSIONS_KIND,
    SUBMISSIONS_PHASE,
    TRANSPORT_RULE,
    _mapping,
    _positive_number,
    _refuse,
)
from so101_demo.act.head_search_stop_measurement.declarations import (
    _declaration_runtime,
    _document,
)
from so101_demo.act.head_search_timing_measurement.contracts import (
    CAL_TIMING_TIME_BASE_UNVERIFIED,
    DIGEST_CONVENTION,
    SIMULATION_TIME_BASE,
    _digest,
    _number,
)
from so101_demo.act.head_search_timing_params import P99_9, p99_9


def build_controller_stop_config(
    *, path, tolerance: Mapping, controller_config_path, command=None
) -> dict:
    """The controller stop configuration document phase 7 reads its tolerance out of."""

    config_path = Path(controller_config_path)
    period = _positive_number("the controller cycle period", tolerance["controller_cycle_period_s"])
    body = {
        "schema_version": SCHEMA_VERSION,
        "kind": STOP_CONFIG_KIND,
        "phase": STOP_CONFIG_PHASE,
        "measured_here": False,
        "stopped_tolerance_rad_s": float(tolerance["stopped_tolerance_rad_s"]),
        "unit": "rad/s",
        "quantity": (
            "the controller's own stopped-velocity tolerance: a feedback sample whose measured or reference "
            "velocity exceeds it is not a stopped sample"
        ),
        "declaration_rule": STOP_DECLARATION_RULE,
        "declared_by": dict(tolerance["declared_by"]),
        "source_declaration": dict(tolerance["source_declaration"]),
        "window": {
            "samples": int(tolerance["window_samples"]),
            "step_s": float(tolerance["window_step_s"]),
            "max_age_s": float(tolerance["window_max_age_s"]),
            "span_s": float(tolerance["window_samples"]) * float(tolerance["window_step_s"]),
            "rule": (
                "the controller's stop proof requires this many consecutive samples of its own window, each "
                "stepped by `step_s` and no older than `max_age_s`"
            ),
        },
        "controller_cycle_period_s": period,
        "controller_cycle_rate_hz": 1.0 / period,
        "controller_config": {"path": str(config_path), "sha256": _digest(config_path)},
        "cross_checks": dict(tolerance["cross_checks"]),
        "production_owner": (
            "so101_demo.act.head_neck_limits.STOP_WINDOW_MAX_VELOCITY_RAD_S "
            "(so101_mujoco_support/HeadNeckTrajectoryController)"
        ),
        "consumed_by": (
            "so101_demo.act.head_search_timing_params.compute_stop_velocity_rad_s(controller=...): the "
            "tolerance is the third term of the conservative envelope"
        ),
        "command": command,
        "refusals": [],
        "runtime": _declaration_runtime(),
        "ros_nodes_started": False,
        "mujoco_neck_commanded": False,
        "hardware_motion_commanded": False,
        "cuda_used": False,
        "digest_convention": DIGEST_CONVENTION,
    }
    return _document(path, body)


def build_feedback_measurements(*, path, declaration: Mapping, quantisation: Mapping, command=None) -> dict:
    """The feedback measurements document phase 7 reads the period and the quantisation out of."""

    period = _positive_number("the declared feedback period", declaration["period_s"])
    cycle = _positive_number(
        "the declared controller cycle period", declaration["controller_cycle_period_s"]
    )
    declared = bool(quantisation["declared"])
    refusals = []
    if not declared:
        refusals.append(
            {
                "field": "quantisation_rad",
                "code": CAL_FEEDBACK_QUANTISATION_UNDECLARED,
                "detail": quantisation["detail"],
                "searched": quantisation["declaration_search"],
            }
        )
    body = {
        "schema_version": SCHEMA_VERSION,
        "kind": FEEDBACK_KIND,
        "phase": FEEDBACK_PHASE,
        "measured_here": False,
        "period_s": period,
        "unit": "s",
        "period_rule": FEEDBACK_PERIOD_RULE,
        "feedback_rate_hz": float(declaration["feedback_rate_hz"]),
        "controller_cycle_period_s": cycle,
        "controller_cycle_rate_hz": float(declaration["controller_cycle_rate_hz"]),
        "declared_by": dict(declaration["declared_by"]),
        "controller_config": {"path": declaration["path"], "sha256": declaration["sha256"]},
        "quantisation_rad": quantisation["quantisation_rad"],
        "quantisation_unit": "rad",
        "quantisation": dict(quantisation),
        "consumed_by": (
            "so101_demo.act.head_search_timing_params.compute_stop_velocity_rad_s(feedback=...): "
            "quantisation_rad / period_s is the second term of the envelope, and "
            "compute_stop_latency_s(feedback=...) adds one period to the p99.9 stop latency"
        ),
        "command": command,
        "refusals": refusals,
        "runtime": _declaration_runtime(),
        "ros_nodes_started": False,
        "mujoco_neck_commanded": False,
        "hardware_motion_commanded": False,
        "cuda_used": False,
        "digest_convention": DIGEST_CONVENTION,
    }
    return _document(path, body)


def verify_submission_time_base(samples, *, simulation_timestep_s, control_period_s) -> dict:
    """Prove every submission's lead is the simulation clock's, or refuse rather than record it.

    Phase 7 refuses a submission record it cannot verify in simulation time. The proof here is stronger than
    a declaration: every stamp has to be a whole number of the sealed timestep, the lead has to be the
    difference the record states, the plant's own consumption stamp has to agree with it, and no lead may
    exceed the admission bound of one control period plus one timestep.
    """

    timestep = _positive_number("the sealed simulation timestep", simulation_timestep_s)
    period = _positive_number("the sealed control period", control_period_s)
    if isinstance(samples, (str, bytes)) or not isinstance(samples, Sequence) or not samples:
        raise _refuse(
            CAL_TIMING_TIME_BASE_UNVERIFIED,
            "the submission measurement records no submission, so no lead can be verified in simulation time",
        )
    bound = period + timestep
    leads: list[float] = []
    previous_snapshot = None
    for index, sample in enumerate(samples):
        record = _mapping("a controller submission", sample)
        if record.get("time_base") != SIMULATION_TIME_BASE:
            raise _refuse(
                CAL_TIMING_TIME_BASE_UNVERIFIED,
                f"submission {index} declares the time base {record.get('time_base')!r} instead of "
                f"{SIMULATION_TIME_BASE!r}: a wall-clock submission is not verified in simulation time",
            )
        snapshot = _number(record, f"submission {index}", "submit_snapshot_sim_s", nonnegative=True)
        first = _number(record, f"submission {index}", "first_target_sim_s", nonnegative=True)
        consumed = _number(record, f"submission {index}", "plant_consumed_sim_s", nonnegative=True)
        lead = _number(record, f"submission {index}", "lead_s", positive=True)
        for name, value in (("submit_snapshot_sim_s", snapshot), ("first_target_sim_s", first)):
            steps = value / timestep
            if not math.isclose(steps, round(steps), rel_tol=0.0, abs_tol=_GRID_TOLERANCE_S):
                raise _refuse(
                    CAL_TIMING_TIME_BASE_UNVERIFIED,
                    f"submission {index} is stamped {value} s, which is not a whole number of the sealed "
                    f"{timestep} s timesteps: the stamp is not the simulation clock's",
                )
        if not math.isclose(first - snapshot, lead, rel_tol=0.0, abs_tol=_GRID_TOLERANCE_S):
            raise _refuse(
                CAL_TIMING_TIME_BASE_UNVERIFIED,
                f"submission {index} records a lead of {lead} s but its stamps differ by "
                f"{first - snapshot} s",
            )
        if not math.isclose(consumed, first, rel_tol=0.0, abs_tol=_GRID_TOLERANCE_S):
            raise _refuse(
                CAL_TIMING_TIME_BASE_UNVERIFIED,
                f"submission {index} puts the plant's own consumption at {consumed} s but the record claims "
                f"{first} s, so the lead was not read back out of the stepped plant",
            )
        if lead > bound + _GRID_TOLERANCE_S:
            raise _refuse(
                CAL_TIMING_TIME_BASE_UNVERIFIED,
                f"submission {index} records a lead of {lead} s, beyond the admission bound of one "
                f"{period} s control period plus one {timestep} s timestep ({bound} s): a submission cannot "
                f"wait longer than the cycle it is drained at plus the step that consumes it",
            )
        if previous_snapshot is not None and snapshot <= previous_snapshot:
            raise _refuse(
                CAL_TIMING_TIME_BASE_UNVERIFIED,
                f"submission {index} is snapshotted at {snapshot} s, not after submission {index - 1} at "
                f"{previous_snapshot} s: the submissions are not the simulation clock's own order",
            )
        previous_snapshot = snapshot
        leads.append(lead)
    return {
        "time_base": SIMULATION_TIME_BASE,
        "sample_count": len(leads),
        "submission_count": len(leads),
        "simulation_timestep_s": timestep,
        "control_period_s": period,
        "admission_bound_s": bound,
        "minimum_lead_s": min(leads),
        "maximum_lead_s": max(leads),
        "lead_spread_s": max(leads) - min(leads),
        "all_leads_within_admission_bound": True,
        "plant_consumption_matches": True,
        "stamps_on_timestep_grid": True,
        "submissions_verified_in_simulation_time": True,
    }


def build_stationary_measurements(
    *, path, records, samples_per_pose, flight: Mapping, command=None
) -> dict:
    """The stationary measurements document phase 7 reads the velocity noise out of."""

    samples: list[dict] = []
    poses: list[dict] = []
    for record in records:
        for sample in record["samples"]:
            samples.append(
                {
                    **sample,
                    "index": len(samples),
                    "pose_index": record["pose_index"],
                    "anchor": record["anchor"],
                    "pose_rad": record["pose_rad"],
                    "pose_kind": record["pose_kind"],
                }
            )
        magnitudes = [max(abs(value) for value in sample["velocity_rad_s"]) for sample in record["samples"]]
        poses.append(
            {
                "pose_index": record["pose_index"],
                "anchor": record["anchor"],
                "pose_rad": record["pose_rad"],
                "pose_kind": record["pose_kind"],
                "settle": record["settle"],
                "sample_count": len(record["samples"]),
                "p99_9_velocity_rad_s": p99_9(magnitudes),
                "max_velocity_rad_s": max(magnitudes),
            }
        )
    magnitudes = [max(abs(value) for value in sample["velocity_rad_s"]) for sample in samples]
    body = {
        "schema_version": SCHEMA_VERSION,
        "kind": STATIONARY_KIND,
        "phase": STATIONARY_PHASE,
        "measured_here": True,
        "time_base": SIMULATION_TIME_BASE,
        "monitored_joints": list(MONITORED_JOINTS),
        "joint_scope_rule": JOINT_SCOPE_RULE,
        "measurement_rule": STATIONARY_RULE,
        "feedback_period_s": float(flight["feedback_period_s"]),
        "controller_cycle_period_s": float(flight["control_period_s"]),
        "simulation_timestep_s": float(flight["simulation_timestep_s"]),
        "samples_per_pose": int(samples_per_pose),
        "pose_count": len(poses),
        "sample_count": len(samples),
        "settle_velocity_rad_s": float(flight["settle_velocity_rad_s"]),
        "goal_tolerance_rad": float(flight["goal_tolerance_rad"]),
        "settle_consecutive_steps": int(flight["settle_consecutive_steps"]),
        "poses": poses,
        "samples": samples,
        "p99_9_velocity_rad_s": p99_9(magnitudes),
        "max_velocity_rad_s": max(magnitudes),
        "percentile": {
            "quantile": P99_9,
            "convention": "nearest_rank_ceil(quantile * n)",
            "sample_count": len(magnitudes),
            "rank": max(1, math.ceil(P99_9 * len(magnitudes))),
        },
        "magnitude_rule": (
            "each sample's magnitude is max(abs(velocity_rad_s)) over the monitored joints, which is the "
            "magnitude the Task-8 stop protocol and phase 7 both take"
        ),
        "real_time_factor": flight["real_time_factor"],
        "pacing": dict(flight["pacing"]),
        "scene_path": flight["scene_path"],
        "scene_sha256": flight["scene_sha256"],
        "geometry_seal": dict(flight["geometry_seal"]),
        "production_search_config": dict(flight["production_search_config"]),
        "controller_config": dict(flight["controller_config"]),
        "runtime_identity": dict(flight["runtime_identity"]),
        "ros_nodes_started": False,
        "mujoco_neck_commanded": True,
        "hardware_motion_commanded": False,
        "cuda_used": False,
        "detector_loaded": False,
        "command": command,
        "refusals": [],
        "digest_convention": DIGEST_CONVENTION,
    }
    return _document(path, body)


def build_controller_submissions(*, path, records, flight: Mapping, command=None) -> dict:
    """The controller submissions document phase 7 reads the goal-admission lead out of."""

    samples = [
        {
            "index": index,
            "purpose": record["purpose"],
            "submitted_by": record["submitted_by"],
            "target_rad": float(record["target_rad"]),
            "reference_before_rad": float(record["reference_before_rad"]),
            "motion_rad": float(record["target_rad"]) - float(record["reference_before_rad"]),
            "submit_snapshot_sim_s": float(record["submit_snapshot_sim_s"]),
            "first_target_sim_s": float(record["first_target_sim_s"]),
            "plant_consumed_sim_s": float(record["plant_consumed_sim_s"]),
            "lead_s": float(record["lead_s"]),
            "time_base": SIMULATION_TIME_BASE,
            "control_cycles": int(record["control_cycles"]),
            "steps": int(record["steps"]),
            "settled": bool(record["settled"]),
            "reached": bool(record["reached"]),
            "final_velocity_rad_s": float(record["final_velocity_rad_s"]),
            "final_position_error_rad": float(record["final_position_error_rad"]),
        }
        for index, record in enumerate(records)
    ]
    proof = verify_submission_time_base(
        samples,
        simulation_timestep_s=flight["simulation_timestep_s"],
        control_period_s=flight["control_period_s"],
    )
    leads = [sample["lead_s"] for sample in samples]
    body = {
        "schema_version": SCHEMA_VERSION,
        "kind": SUBMISSIONS_KIND,
        "phase": SUBMISSIONS_PHASE,
        "measured_here": True,
        "time_base": SIMULATION_TIME_BASE,
        "simulation_timestep_s": float(flight["simulation_timestep_s"]),
        "control_period_s": float(flight["control_period_s"]),
        "controller_cycle_rate_hz": 1.0 / float(flight["control_period_s"]),
        "monitored_joints": list(MONITORED_JOINTS),
        "lead_definition": LEAD_DEFINITION,
        "admission_rule": ADMISSION_RULE,
        "transport_rule": TRANSPORT_RULE,
        "transport": {
            "in_process": True,
            "dds_transport_measured": False,
            "wire_goal_encoded": False,
            "detail": TRANSPORT_RULE,
        },
        "samples": samples,
        "submission_count": len(samples),
        "minimum_lead_s": min(leads),
        "maximum_lead_s": max(leads),
        "lead_spread_s": max(leads) - min(leads),
        "time_base_proof": proof,
        "real_time_factor": flight["real_time_factor"],
        "pacing": dict(flight["pacing"]),
        "scene_path": flight["scene_path"],
        "scene_sha256": flight["scene_sha256"],
        "geometry_seal": dict(flight["geometry_seal"]),
        "production_search_config": dict(flight["production_search_config"]),
        "controller_config": dict(flight["controller_config"]),
        "runtime_identity": dict(flight["runtime_identity"]),
        "ros_nodes_started": False,
        "mujoco_neck_commanded": True,
        "hardware_motion_commanded": False,
        "cuda_used": False,
        "detector_loaded": False,
        "command": command,
        "refusals": [],
        "digest_convention": DIGEST_CONVENTION,
    }
    return _document(path, body)


def build_stop_proofs(*, path, records, flight: Mapping, command=None) -> dict:
    """The stop/revoke proofs document phase 7 reads the stop latency out of."""

    samples = [
        {
            "index": index,
            "reason": record["reason"],
            "anchor": record["anchor"],
            "pose_rad": float(record["pose_rad"]),
            "pose_kind": record["pose_kind"],
            "revoke_offset_s": float(record["revoke_offset_s"]),
            "motion_target_rad": float(record["motion_target_rad"]),
            "hold_rad": float(record["hold_rad"]),
            "stop_request_monotonic_s": float(record["stop_request_monotonic_s"]),
            "stop_request_sim_s": float(record["stop_request_sim_s"]),
            "third_confirming_receive_monotonic_s": float(
                record["third_confirming_receive_monotonic_s"]
            ),
            "third_confirming_receive_sim_s": float(record["third_confirming_receive_sim_s"]),
            "latency_s": float(record["latency_s"]),
            "sim_latency_s": float(record["sim_latency_s"]),
            "window_real_time_factor": record["window_real_time_factor"],
            "pacing_faithful": bool(record["pacing_faithful"]),
            "confirming_sample_indices": list(record["confirming_sample_indices"]),
            "third_confirming_sample_index": int(record["third_confirming_sample_index"]),
            "sample_count": len(record["feedback_samples"]),
            "feedback_samples": list(record["feedback_samples"]),
            "exceeds_declared_production_latency_s": record[
                "exceeds_declared_production_latency_s"
            ],
        }
        for index, record in enumerate(records)
    ]
    latencies = [sample["latency_s"] for sample in samples]
    exceedances = [
        sample
        for sample in samples
        if sample["exceeds_declared_production_latency_s"] is True
    ]
    body = {
        "schema_version": SCHEMA_VERSION,
        "kind": STOP_PROOFS_KIND,
        "phase": STOP_PROOFS_PHASE,
        "measured_here": True,
        "feedback_period_s": float(flight["feedback_period_s"]),
        "controller_cycle_period_s": float(flight["control_period_s"]),
        "simulation_timestep_s": float(flight["simulation_timestep_s"]),
        "monitored_joints": list(MONITORED_JOINTS),
        "joint_scope_rule": JOINT_SCOPE_RULE,
        "stop_velocity_rad_s": float(flight["stop_velocity_rad_s"]),
        "max_age_s": float(flight["max_age_s"]),
        "qualification_rule": QUALIFICATION_RULE,
        "consecutive_rule": CONSECUTIVE_RULE,
        "qualification_source": (
            "so101_demo.adapters.act.ros_execution.RosControllerPort.stopped(): the installed stop criterion "
            "is called on every receipt this flight delivers, so the qualification is the running system's"
        ),
        "samples": samples,
        "proof_count": len(samples),
        "p99_9_latency_s": p99_9(latencies),
        "slowest_latency_s": max(latencies),
        "percentile": {
            "quantile": P99_9,
            "convention": "nearest_rank_ceil(quantile * n)",
            "sample_count": len(latencies),
            "rank": max(1, math.ceil(P99_9 * len(latencies))),
        },
        "single_exceedance_rule": SINGLE_EXCEEDANCE_RULE,
        "pacing_faithful_rule": PACING_FAITHFUL_RULE,
        "pacing_faithful_tolerance": PACING_TOLERANCE,
        "pacing_faithful_proof_count": sum(1 for sample in samples if sample["pacing_faithful"]),
        "off_schedule_sample_indices": [
            sample["index"] for sample in samples if not sample["pacing_faithful"]
        ],
        "declared_production_latency_s": flight["declared_production_latency_s"],
        "exceedance_count": len(exceedances),
        "exceeding_sample_indices": [sample["index"] for sample in exceedances],
        "stop_budget_s": float(flight["stop_budget_s"]),
        "revoke_offsets_s": [float(value) for value in flight["revoke_offsets_s"]],
        "real_time_factor": flight["real_time_factor"],
        "pacing": dict(flight["pacing"]),
        "scene_path": flight["scene_path"],
        "scene_sha256": flight["scene_sha256"],
        "geometry_seal": dict(flight["geometry_seal"]),
        "production_search_config": dict(flight["production_search_config"]),
        "controller_config": dict(flight["controller_config"]),
        "runtime_identity": dict(flight["runtime_identity"]),
        "ros_nodes_started": False,
        "mujoco_neck_commanded": True,
        "hardware_motion_commanded": False,
        "cuda_used": False,
        "detector_loaded": False,
        "command": command,
        "refusals": [],
        "digest_convention": DIGEST_CONVENTION,
    }
    return _document(path, body)
