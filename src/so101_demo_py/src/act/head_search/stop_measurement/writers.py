"""Write the controller stop configuration, feedback, stationary, submission and stop proof measurements."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
from pathlib import Path
import time

from so101_demo.act.head_search.camera_measurement.frames import (
    _anchor_pose_requests,
    _corridor_check,
)
from so101_demo.act.head_search.deadband_measurement.lock_trial import motion_corridor_rad
from so101_demo.act.head_search.deadband_measurement.plant import (
    _plant_request,
)
from so101_demo.act.head_search.stop_measurement.contracts import (
    DEFAULT_REALTIME,
    DEFAULT_REVOKE_OFFSETS_S,
    DEFAULT_SAMPLES_PER_POSE,
    DEFAULT_STOP_BUDGET_S,
    FEEDBACK_ARTIFACT,
    FEEDBACK_PHASE,
    MEASUREMENT_ATTEMPT_ID,
    MEASUREMENT_SESSION_ID,
    MONITORED_JOINTS,
    RECEIPT_KIND,
    SCHEMA_VERSION,
    STATIONARY_ARTIFACT,
    STATIONARY_PHASE,
    STOP_CONFIG_ARTIFACT,
    STOP_CONFIG_PHASE,
    STOP_PROOFS_ARTIFACT,
    STOP_PROOFS_PHASE,
    SUBMISSIONS_ARTIFACT,
    SUBMISSIONS_PHASE,
    _refuse,
)
from so101_demo.act.head_search.stop_measurement.declarations import (
    declared_controller_stop_tolerance,
    declared_quantisation,
    read_feedback_declarations,
)
from so101_demo.act.head_search.stop_measurement.documents import (
    build_controller_stop_config,
    build_controller_submissions,
    build_feedback_measurements,
    build_stationary_measurements,
    build_stop_proofs,
)
from so101_demo.act.head_search.stop_measurement.flights import (
    _write,
    run_stationary_flight,
    run_stop_proof_flight,
    run_submission_flight,
)
from so101_demo.act.head_search.timing_measurement.contracts import (
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    CAL_TIMING_EVIDENCE_MISSING,
    DEFAULT_MAX_SETTLE_S,
    SETTLE_CONSECUTIVE_STEPS,
    _digest,
    _number,
)
from so101_demo.act.head_search.timing_measurement.control import (
    planned_stops,
    read_control_period,
)


def _receipt(*, kind_phase, output, document_path, command, fields) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": RECEIPT_KIND,
        "phase": kind_phase,
        "command": command,
        "output_dir": str(output),
        "document_path": str(document_path),
        "document_sha256": fields.pop("document_sha256"),
        "status": fields.pop("status"),
        "refusals": fields.pop("refusals"),
        "fields_refused": fields.pop("fields_refused"),
        **fields,
    }


def write_controller_stop_config(
    *,
    installed_declaration,
    source_declaration,
    controller_config_path,
    output_dir,
    command=None,
) -> dict:
    """Read the controller's declared stopped tolerance and write the document phase 7 consumes."""

    output = Path(output_dir)
    output.mkdir(parents=True)
    tolerance = declared_controller_stop_tolerance(
        installed_declaration=installed_declaration,
        source_declaration=source_declaration,
        controller_config_path=controller_config_path,
    )
    document_path = output / STOP_CONFIG_ARTIFACT
    document = build_controller_stop_config(
        path=document_path,
        tolerance=tolerance,
        controller_config_path=controller_config_path,
        command=command,
    )
    receipt = _receipt(
        kind_phase=STOP_CONFIG_PHASE,
        output=output,
        document_path=document_path,
        command=command,
        fields={
            "document_sha256": document["sha256"],
            "status": "DECLARED",
            "refusals": [],
            "fields_refused": [],
            "stopped_tolerance_rad_s": document["stopped_tolerance_rad_s"],
            "declared_by": document["declared_by"],
            "source_declaration": document["source_declaration"],
            "window": document["window"],
            "controller_cycle_period_s": document["controller_cycle_period_s"],
            "measured_here": False,
            "ros_nodes_started": False,
            "mujoco_neck_commanded": False,
            "hardware_motion_commanded": False,
            "cuda_used": False,
        },
    )
    _write(output, document, receipt)
    return {"document": document, "receipt": receipt, "document_path": document_path,
            "output_dir": output, "refusals": []}


def write_feedback_measurements(
    *, controller_config_path, output_dir, quantisation_declaration_path=None, command=None
) -> dict:
    """Read the declared feedback period and resolution, write the document, refuse the undeclared field."""

    output = Path(output_dir)
    output.mkdir(parents=True)
    declaration = read_feedback_declarations(controller_config_path)
    quantisation = declared_quantisation(quantisation_declaration_path)
    document_path = output / FEEDBACK_ARTIFACT
    document = build_feedback_measurements(
        path=document_path,
        declaration=declaration,
        quantisation=quantisation,
        command=command,
    )
    refusals = list(document["refusals"])
    receipt = _receipt(
        kind_phase=FEEDBACK_PHASE,
        output=output,
        document_path=document_path,
        command=command,
        fields={
            "document_sha256": document["sha256"],
            "status": "MEASURED_WITH_REFUSED_FIELD" if refusals else "DECLARED",
            "refusals": refusals,
            "fields_refused": [record["field"] for record in refusals],
            "period_s": document["period_s"],
            "feedback_rate_hz": document["feedback_rate_hz"],
            "controller_cycle_period_s": document["controller_cycle_period_s"],
            "quantisation_rad": document["quantisation_rad"],
            "quantisation": document["quantisation"],
            "measured_here": False,
            "ros_nodes_started": False,
            "mujoco_neck_commanded": False,
            "hardware_motion_commanded": False,
            "cuda_used": False,
        },
    )
    _write(output, document, receipt)
    return {"document": document, "receipt": receipt, "document_path": document_path,
            "output_dir": output, "refusals": refusals}


def _flight_inputs(
    *, scene_path, geometry_seal_path, production_search_config_path, controller_config_path,
    anchors=None,
) -> dict:
    """Every sealed input of a flight, cross-checked before a single step is taken."""

    scene = Path(scene_path)
    seal_path = Path(geometry_seal_path)
    production_path = Path(production_search_config_path)
    controller_path = Path(controller_config_path)
    for path in (scene, seal_path, production_path, controller_path):
        if not path.is_file():
            raise FileNotFoundError(f"the stop measurement needs {path}")
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    production = json.loads(production_path.read_text(encoding="utf-8"))
    from so101_demo.act.head_search.mujoco_measurements import read_mujoco_timestep

    declaration = read_mujoco_timestep(scene)
    scene_sha256 = declaration["scene_sha256"]
    sealed_scene = (seal.get("source_digests") or {}).get("scene_sha256")
    if sealed_scene != scene_sha256:
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the sealed geometry pins the scene {sealed_scene}, but the scene this flight would step "
            f"digests to {scene_sha256}",
        )
    control_period = read_control_period(controller_path)
    timestep = float(declaration["simulation_timestep_s"])
    steps_per_period = control_period / timestep
    if not math.isclose(steps_per_period, round(steps_per_period), rel_tol=0.0, abs_tol=1e-12):
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the sealed controller period {control_period} s is not a whole number of the sealed scene's "
            f"{timestep} s steps, so the plant could not be driven at the production period",
        )
    requests = _anchor_pose_requests(
        seal=seal,
        production=production,
        anchors=anchors,
        attempt_id=MEASUREMENT_ATTEMPT_ID,
        session_id=MEASUREMENT_SESSION_ID,
    )
    feedback = read_feedback_declarations(controller_path)
    motion = production.get("motion") if isinstance(production.get("motion"), Mapping) else {}
    values = production.get("values") if isinstance(production.get("values"), Mapping) else {}
    return {
        "scene": scene,
        "scene_sha256": scene_sha256,
        "seal": seal,
        "seal_path": seal_path,
        "production": production,
        "production_path": production_path,
        "controller_path": controller_path,
        "controller_period_s": control_period,
        "feedback_period_s": feedback["period_s"],
        "simulation_timestep_s": timestep,
        "requests": requests,
        "corridor": motion_corridor_rad(geometry_seal=seal),
        "camera": seal.get("camera") if isinstance(seal.get("camera"), Mapping) else {},
        "settle_velocity_rad_s": _number(
            motion, "the production motion thresholds", "settle_velocity_rad_s", positive=True
        ),
        "goal_tolerance_rad": _number(
            motion, "the production motion thresholds", "goal_tolerance_rad", positive=True
        ),
        "stop_velocity_rad_s": _number(
            values, "the production search values", "stop_velocity_rad_s", positive=True
        ),
        "max_age_s": _number(values, "the production search values", "max_age_s", positive=True),
        "declared_production_latency_s": _number(
            values, "the production search values", "stop_latency_s", positive=True
        ),
    }


def _plant_request_for(*, inputs, request, realtime, settle_consecutive_steps, max_settle_s) -> dict:
    plant_request = _plant_request(
        request=request,
        scene=inputs["scene"],
        seal=inputs["seal"],
        camera=inputs["camera"],
        control_period_s=inputs["controller_period_s"],
        max_settle_s=max_settle_s,
        settle_consecutive_steps=settle_consecutive_steps,
    )
    plant_request.update(
        {
            "feedback_period_s": inputs["feedback_period_s"],
            "realtime": bool(realtime),
            "stop_velocity_rad_s": inputs["stop_velocity_rad_s"],
            "max_age_s": inputs["max_age_s"],
            "monitored_joints": list(MONITORED_JOINTS),
        }
    )
    return plant_request


def _flight_evidence(*, inputs, flight: Mapping, timestep: float) -> dict:
    from so101_demo.act.head_search.timing_measurement.documents import runtime_identity

    return {
        **flight,
        "simulation_timestep_s": timestep,
        "scene_path": str(inputs["scene"]),
        "scene_sha256": inputs["scene_sha256"],
        "geometry_seal": {"path": str(inputs["seal_path"]), "sha256": _digest(inputs["seal_path"])},
        "production_search_config": {
            "path": str(inputs["production_path"]),
            "sha256": _digest(inputs["production_path"]),
        },
        "controller_config": {
            "path": str(inputs["controller_path"]),
            "sha256": _digest(inputs["controller_path"]),
        },
        "runtime_identity": runtime_identity(detector_loaded=False),
    }


def _check_poses(*, requests, corridor) -> None:
    for request in requests:
        for pose in request["poses"]:
            _corridor_check(
                angle_rad=pose["pose_rad"],
                corridor_rad=corridor,
                what=f"planned pose of the anchor {request['anchor']!r}",
            )


def write_stationary_measurements(
    *,
    scene_path,
    geometry_seal_path,
    production_search_config_path,
    controller_config_path,
    output_dir,
    anchors=None,
    samples_per_pose=DEFAULT_SAMPLES_PER_POSE,
    max_settle_s=DEFAULT_MAX_SETTLE_S,
    settle_consecutive_steps=SETTLE_CONSECUTIVE_STEPS,
    realtime=DEFAULT_REALTIME,
    command=None,
) -> dict:
    """Hold every sealed anchor's planned poses and write the stationary velocity document."""

    started = time.time()
    output = Path(output_dir)
    output.mkdir(parents=True)
    inputs = _flight_inputs(
        scene_path=scene_path,
        geometry_seal_path=geometry_seal_path,
        production_search_config_path=production_search_config_path,
        controller_config_path=controller_config_path,
        anchors=anchors,
    )
    _check_poses(requests=inputs["requests"], corridor=inputs["corridor"])
    results = []
    for request in inputs["requests"]:
        plant_request = _plant_request_for(
            inputs=inputs,
            request=request,
            realtime=realtime,
            settle_consecutive_steps=settle_consecutive_steps,
            max_settle_s=max_settle_s,
        )
        result = run_stationary_flight(
            request={
                "poses": [
                    {**pose, "anchor": request["anchor"]} for pose in request["poses"]
                ],
                "plant_request": plant_request,
                "samples_per_pose": samples_per_pose,
                "feedback_period_s": inputs["feedback_period_s"],
                "control_period_s": inputs["controller_period_s"],
            }
        )
        results.append((request, result))
    records = [record for _request, result in results for record in result["records"]]
    flight = _flight_evidence(
        inputs=inputs, flight=results[0][1]["flight"], timestep=inputs["simulation_timestep_s"]
    )
    document_path = output / STATIONARY_ARTIFACT
    document = build_stationary_measurements(
        path=document_path,
        records=records,
        samples_per_pose=samples_per_pose,
        flight=flight,
        command=command,
    )
    receipt = _receipt(
        kind_phase=STATIONARY_PHASE,
        output=output,
        document_path=document_path,
        command=command,
        fields={
            "document_sha256": document["sha256"],
            "status": "MEASURED",
            "refusals": [],
            "fields_refused": [],
            "pose_count": document["pose_count"],
            "sample_count": document["sample_count"],
            "samples_per_pose": document["samples_per_pose"],
            "p99_9_velocity_rad_s": document["p99_9_velocity_rad_s"],
            "max_velocity_rad_s": document["max_velocity_rad_s"],
            "anchor_names": [request["anchor"] for request in inputs["requests"]],
            "poses_measured": [
                {
                    "anchor": record["anchor"],
                    "pose_rad": record["pose_rad"],
                    "pose_kind": record["pose_kind"],
                    "p99_9_velocity_rad_s": record["p99_9_velocity_rad_s"],
                }
                for record in document["poses"]
            ],
            "feedback_period_s": document["feedback_period_s"],
            "controller_cycle_period_s": document["controller_cycle_period_s"],
            "simulation_timestep_s": document["simulation_timestep_s"],
            "real_time_factor": document["real_time_factor"],
            "pacing": document["pacing"],
            "scene_path": str(inputs["scene"]),
            "scene_sha256": inputs["scene_sha256"],
            "elapsed_s": time.time() - started,
            "runtime_identity": document["runtime_identity"],
            "ros_nodes_started": False,
            "mujoco_neck_commanded": True,
            "hardware_motion_commanded": False,
            "cuda_used": False,
            "detector_loaded": False,
            "transport_measured": False,
        },
    )
    _write(output, document, receipt)
    return {"document": document, "receipt": receipt, "document_path": document_path,
            "output_dir": output, "refusals": []}


def write_controller_submissions(
    *,
    scene_path,
    geometry_seal_path,
    production_search_config_path,
    controller_config_path,
    output_dir,
    anchors=None,
    max_settle_s=DEFAULT_MAX_SETTLE_S,
    settle_consecutive_steps=SETTLE_CONSECUTIVE_STEPS,
    realtime=DEFAULT_REALTIME,
    command=None,
) -> dict:
    """Submit the installed controller's own targets and write the goal-admission lead document."""

    started = time.time()
    output = Path(output_dir)
    output.mkdir(parents=True)
    inputs = _flight_inputs(
        scene_path=scene_path,
        geometry_seal_path=geometry_seal_path,
        production_search_config_path=production_search_config_path,
        controller_config_path=controller_config_path,
        anchors=anchors,
    )
    _check_poses(requests=inputs["requests"], corridor=inputs["corridor"])
    records = []
    flights = []
    for request in inputs["requests"]:
        plan = planned_stops(request["controller_config"])
        submissions = [
            {
                "purpose": "anchor_positioning",
                "submitted_by": (
                    "the sealed anchor's own search start (so101_demo.act.search.HeadSearchController "
                    "search_start_rad)"
                ),
                "target_rad": float(request["search_start_rad"]),
            },
            *[
                {
                    "purpose": "plan_stop",
                    "submitted_by": (
                        "so101_demo.act.search.HeadSearchController.next_target(): the installed controller's "
                        "own bounded plan stop"
                    ),
                    "target_rad": float(target),
                }
                for target in plan
            ],
        ]
        result = run_submission_flight(
            request={
                "submissions": submissions,
                "plant_request": _plant_request_for(
                    inputs=inputs,
                    request=request,
                    realtime=realtime,
                    settle_consecutive_steps=settle_consecutive_steps,
                    max_settle_s=max_settle_s,
                ),
                "control_period_s": inputs["controller_period_s"],
            }
        )
        records.extend(result["records"])
        flights.append((request, result))
    flight = _flight_evidence(
        inputs=inputs, flight=flights[0][1]["flight"], timestep=inputs["simulation_timestep_s"]
    )
    document_path = output / SUBMISSIONS_ARTIFACT
    document = build_controller_submissions(
        path=document_path, records=records, flight=flight, command=command
    )
    receipt = _receipt(
        kind_phase=SUBMISSIONS_PHASE,
        output=output,
        document_path=document_path,
        command=command,
        fields={
            "document_sha256": document["sha256"],
            "status": "MEASURED",
            "refusals": [],
            "fields_refused": [],
            "submission_count": document["submission_count"],
            "minimum_lead_s": document["minimum_lead_s"],
            "maximum_lead_s": document["maximum_lead_s"],
            "lead_spread_s": document["lead_spread_s"],
            "control_period_s": document["control_period_s"],
            "simulation_timestep_s": document["simulation_timestep_s"],
            "time_base": document["time_base"],
            "time_base_proof": document["time_base_proof"],
            "anchor_names": [request["anchor"] for request in inputs["requests"]],
            "submissions": [
                {
                    "purpose": sample["purpose"],
                    "target_rad": sample["target_rad"],
                    "submit_snapshot_sim_s": sample["submit_snapshot_sim_s"],
                    "first_target_sim_s": sample["first_target_sim_s"],
                    "lead_s": sample["lead_s"],
                }
                for sample in document["samples"]
            ],
            "real_time_factor": document["real_time_factor"],
            "pacing": document["pacing"],
            "scene_path": str(inputs["scene"]),
            "scene_sha256": inputs["scene_sha256"],
            "elapsed_s": time.time() - started,
            "runtime_identity": document["runtime_identity"],
            "ros_nodes_started": False,
            "mujoco_neck_commanded": True,
            "hardware_motion_commanded": False,
            "cuda_used": False,
            "detector_loaded": False,
            "transport_measured": False,
        },
    )
    _write(output, document, receipt)
    return {"document": document, "receipt": receipt, "document_path": document_path,
            "output_dir": output, "refusals": []}


def write_stop_proofs(
    *,
    scene_path,
    geometry_seal_path,
    production_search_config_path,
    controller_config_path,
    output_dir,
    anchors=None,
    revoke_offsets_s=None,
    stop_budget_s=DEFAULT_STOP_BUDGET_S,
    max_settle_s=DEFAULT_MAX_SETTLE_S,
    settle_consecutive_steps=SETTLE_CONSECUTIVE_STEPS,
    realtime=DEFAULT_REALTIME,
    command=None,
) -> dict:
    """Revoke declared motions and write the stop/revoke proof document phase 7 bounds the latency with."""

    started = time.time()
    output = Path(output_dir)
    output.mkdir(parents=True)
    inputs = _flight_inputs(
        scene_path=scene_path,
        geometry_seal_path=geometry_seal_path,
        production_search_config_path=production_search_config_path,
        controller_config_path=controller_config_path,
        anchors=anchors,
    )
    _check_poses(requests=inputs["requests"], corridor=inputs["corridor"])
    records = []
    flights = []
    for request in inputs["requests"]:
        poses = [pose for pose in request["poses"] if pose["pose_kind"] == "plan"]
        if not poses:
            raise _refuse(
                CAL_TIMING_EVIDENCE_MISSING,
                f"the anchor {request['anchor']!r} has no plan stop, so there is no motion to revoke",
            )
        result = run_stop_proof_flight(
            request={
                "poses": [{**pose, "anchor": request["anchor"]} for pose in poses],
                "plant_request": _plant_request_for(
                    inputs=inputs,
                    request=request,
                    realtime=realtime,
                    settle_consecutive_steps=settle_consecutive_steps,
                    max_settle_s=max_settle_s,
                ),
                "revoke_offsets_s": (
                    DEFAULT_REVOKE_OFFSETS_S if revoke_offsets_s is None else tuple(revoke_offsets_s)
                ),
                "stop_budget_s": stop_budget_s,
                "feedback_period_s": inputs["feedback_period_s"],
                "control_period_s": inputs["controller_period_s"],
                "stop_velocity_rad_s": inputs["stop_velocity_rad_s"],
                "max_age_s": inputs["max_age_s"],
                "declared_production_latency_s": inputs["declared_production_latency_s"],
            }
        )
        records.extend(result["records"])
        flights.append((request, result))
    flight = _flight_evidence(
        inputs=inputs, flight=flights[0][1]["flight"], timestep=inputs["simulation_timestep_s"]
    )
    document_path = output / STOP_PROOFS_ARTIFACT
    document = build_stop_proofs(path=document_path, records=records, flight=flight, command=command)
    receipt = _receipt(
        kind_phase=STOP_PROOFS_PHASE,
        output=output,
        document_path=document_path,
        command=command,
        fields={
            "document_sha256": document["sha256"],
            "status": "MEASURED",
            "refusals": [],
            "fields_refused": [],
            "proof_count": document["proof_count"],
            "p99_9_latency_s": document["p99_9_latency_s"],
            "slowest_latency_s": document["slowest_latency_s"],
            "feedback_period_s": document["feedback_period_s"],
            "stop_velocity_rad_s": document["stop_velocity_rad_s"],
            "max_age_s": document["max_age_s"],
            "stop_budget_s": document["stop_budget_s"],
            "revoke_offsets_s": document["revoke_offsets_s"],
            "declared_production_latency_s": document["declared_production_latency_s"],
            "exceedance_count": document["exceedance_count"],
            "pacing_faithful_proof_count": document["pacing_faithful_proof_count"],
            "off_schedule_sample_indices": document["off_schedule_sample_indices"],
            "exceeding_sample_indices": document["exceeding_sample_indices"],
            "anchor_names": [request["anchor"] for request in inputs["requests"]],
            "proofs": [
                {
                    "index": sample["index"],
                    "pose_rad": sample["pose_rad"],
                    "revoke_offset_s": sample["revoke_offset_s"],
                    "stop_request_monotonic_s": sample["stop_request_monotonic_s"],
                    "third_confirming_receive_monotonic_s": sample[
                        "third_confirming_receive_monotonic_s"
                    ],
                    "latency_s": sample["latency_s"],
                    "sim_latency_s": sample["sim_latency_s"],
                    "sample_count": sample["sample_count"],
                }
                for sample in document["samples"]
            ],
            "real_time_factor": document["real_time_factor"],
            "pacing": document["pacing"],
            "scene_path": str(inputs["scene"]),
            "scene_sha256": inputs["scene_sha256"],
            "elapsed_s": time.time() - started,
            "runtime_identity": document["runtime_identity"],
            "ros_nodes_started": False,
            "mujoco_neck_commanded": True,
            "hardware_motion_commanded": False,
            "cuda_used": False,
            "detector_loaded": False,
            "transport_measured": False,
        },
    )
    _write(output, document, receipt)
    return {"document": document, "receipt": receipt, "document_path": document_path,
            "output_dir": output, "refusals": []}
