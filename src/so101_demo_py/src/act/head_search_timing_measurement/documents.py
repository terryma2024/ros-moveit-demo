"""The frame contract, search timing and frame age measurement documents."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
import sys

from so101_demo.act.head_search_timing_measurement.contracts import (
    AGE_DEFINITION,
    AGE_PERCENTILE_QUANTILE,
    AGE_TIME_BASE,
    CAL_TIMING_SWEEP_UNSETTLED,
    DIGEST_CONVENTION,
    FRAME_AGE_KIND,
    FRAME_AGE_PHASE,
    FRAME_CONTRACT_DECLARED_BY,
    FRAME_CONTRACT_KIND,
    FRAME_CONTRACT_PHASE,
    FRAME_PERIOD_S,
    FRAME_RATE_HZ,
    FRAME_TIME_DEFINITION,
    PERCENTILE_CONVENTION,
    PERCENTILE_QUANTILE,
    SCHEMA_VERSION,
    SEARCH_TIMING_KIND,
    SEARCH_TIMING_PHASE,
    SETTLE_RULE,
    SIMULATION_TIME_BASE,
    _finite,
    _optional_number,
    _refuse,
)
from so101_demo.act.head_search_timing_measurement.control import _reference
from so101_demo.act.head_search_timing_params import (
    FRAME_CONTRACT_ITEM,
    nearest_rank_percentile,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256


def frame_contract_document(*, path, command=None, startup_readback=None) -> dict:
    """The declared 10 Hz frame contract every cap of phase 7 is expressed in, as its own artefact.

    Phase 7 cites its frame contract by path and sha256, so the declaration the frame ages are timed
    against has to exist as a document rather than as a nested copy. The rate is the design's own and the
    module refuses any other, so this declaration can only ever confirm it; the startup readback that
    proves the running pipeline uses it belongs to the run and is recorded as not taken here.
    """

    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": FRAME_CONTRACT_KIND,
        "phase": FRAME_CONTRACT_PHASE,
        "path": None if path is None else str(path),
        "command": command,
        "item": FRAME_CONTRACT_ITEM,
        "frame_rate_hz": FRAME_RATE_HZ,
        "frame_period_s": FRAME_PERIOD_S,
        "declared_by": FRAME_CONTRACT_DECLARED_BY,
        "production_owner": "so101_demo.act.head_search_timing_params.FRAME_CONTRACT_HZ",
        "measured_here": False,
        "startup_readback": (
            {
                "verified": False,
                "detail": (
                    "the startup readback that proves the running pipeline uses the 10 Hz contract belongs "
                    "to the run (phase 8); this declaration is the rate the frames of this measurement "
                    "were produced at"
                ),
            }
            if startup_readback is None
            else dict(startup_readback)
        ),
        "ros_nodes_started": False,
        "motion_commanded": False,
        "digest_convention": DIGEST_CONVENTION,
    }
    document["sha256"] = canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    return document


def build_search_timing(
    *,
    path,
    command,
    request: Mapping,
    result: Mapping,
    stops: Sequence[Mapping],
    frames: Sequence[Mapping],
    control: Mapping,
    scene_path,
    scene_sha256: str,
    geometry_seal_path,
    geometry_seal_sha256: str,
    production_search_config_path,
    production_search_config_sha256: str,
    weights_path=None,
    weights_sha256: str | None = None,
    runtime_identity: Mapping | None = None,
) -> dict:
    """The `search_timing` document: what phase 6 reads, with the sweep that measured it.

    `stable_stop_count` is how many of the controller's own bounded stops settled stably in the runtime
    sweep; the percentiles are over those stops' measured settle times and the measured per-frame pipeline
    times. Without a detector there are no frame times, so `p99_frame_s` is `None` and
    `frame_timing.measured` is false - the document never fills the gap with a number that was not
    measured.
    """

    plan_stops = [stop for stop in stops if stop.get("kind") == "plan"]
    if not plan_stops:
        raise _refuse(
            CAL_TIMING_SWEEP_UNSETTLED,
            "the sweep settled no bounded stop point of the controller's plan, so no search timeout can "
            "be bounded from it",
        )
    settles = [float(stop["settle_s"]) for stop in plan_stops]
    frame_times = [float(frame["frame_time_s"]) for frame in frames]
    p99_settle = nearest_rank_percentile(settles, PERCENTILE_QUANTILE)
    p99_frame = (
        nearest_rank_percentile(frame_times, PERCENTILE_QUANTILE) if frame_times else None
    )
    detector = result.get("detector") if isinstance(result.get("detector"), Mapping) else {}
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": SEARCH_TIMING_KIND,
        "phase": SEARCH_TIMING_PHASE,
        "path": None if path is None else str(path),
        "command": command,
        "time_base": SIMULATION_TIME_BASE,
        "simulation_timestep_s": float(result["simulation_timestep_s"]),
        "control_period_s": float(control["control_period_s"]),
        "control_period_source": dict(control),
        "settle_rule": SETTLE_RULE,
        "settle_velocity_rad_s": float(request["settle_velocity_rad_s"]),
        "goal_tolerance_rad": float(request["goal_tolerance_rad"]),
        "settle_consecutive_steps": int(request["settle_consecutive_steps"]),
        "max_settle_s": float(request["max_settle_s"]),
        "percentile_quantile": PERCENTILE_QUANTILE,
        "percentile_convention": PERCENTILE_CONVENTION,
        "stops_planned": len(plan_stops),
        "stable_stop_count": len(plan_stops),
        "p99_settle_s": p99_settle,
        "p99_frame_s": p99_frame,
        "settle_s": {
            "sample_count": len(settles),
            "min": min(settles),
            "max": max(settles),
            "plan_stops_only": True,
            "anchor_positioning_stops": sum(1 for stop in stops if stop.get("kind") == "anchor"),
        },
        "frame_timing": {
            "measured": bool(frame_times),
            "sample_count": len(frame_times),
            "time_base": AGE_TIME_BASE,
            "frame_time_definition": FRAME_TIME_DEFINITION,
            "p99_frame_time_s": p99_frame,
            "max_frame_time_s": max(frame_times) if frame_times else None,
            "warmup": dict(result.get("warmup") or {"performed": False}),
            "not_measured_because": (
                None
                if frame_times
                else "no detector was declared, so no frame of this sweep could be timed; a frame time is "
                "never inferred from the settle timing"
            ),
        },
        "stops": list(stops),
        "anchors": [
            {
                "anchor": anchor["anchor"],
                "search_start_rad": anchor["search_start_rad"],
                "targets_rad": list(anchor["targets_rad"]),
            }
            for anchor in request["anchors"]
        ],
        "sweep_sim_time_s": _optional_number(result, "sim_time_s"),
        "sweep_wall_time_s": _optional_number(result, "wall_time_s"),
        "scene_path": str(scene_path),
        "scene_sha256": scene_sha256,
        "geometry_seal": _reference("the sealed geometry", geometry_seal_path, geometry_seal_sha256),
        "production_search_config": _reference(
            "the production search configuration",
            production_search_config_path,
            production_search_config_sha256,
        ),
        "weights": (
            None
            if weights_path is None
            else _reference("the detector weights", weights_path, weights_sha256)
        ),
        "detector_loaded": bool(detector.get("loaded")),
        "cuda_used": bool(detector.get("loaded")) and str(detector.get("device", "")).startswith("cuda"),
        "transport_measured": False,
        "ros_nodes_started": False,
        "mujoco_neck_commanded": True,
        "hardware_motion_commanded": False,
        "measured_here": True,
        "motion_commanded": False,
        "runtime_identity": dict(runtime_identity or result.get("runtime_identity") or {}),
        "digest_convention": DIGEST_CONVENTION,
    }
    document["sha256"] = canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    return document


def build_frame_age_measurements(
    *,
    path,
    command,
    frame_contract: Mapping,
    samples: Sequence[Mapping],
    result: Mapping,
    scene_sha256: str,
    weights_sha256: str | None,
    runtime_identity: Mapping | None = None,
) -> dict:
    """The `frame_age_measurements` document: phase 7's per-frame ages and the declared frame contract.

    Every sample carries the two monotonic stamps phase 7 subtracts, the simulation stamps that prove the
    sweep's own time base, and the derived age, frame time and simulation-time age. The frame contract is
    cited by path and sha256, so phase 7's `compute_max_age_s` can consume the two documents as they are.
    """

    if not samples:
        raise ValueError("the frame-age document needs at least one measured frame")
    ages = [float(sample["age_s"]) for sample in samples]
    frame_times = [float(sample["frame_time_s"]) for sample in samples]
    sim_time = _optional_number(result, "sim_time_s")
    wall_time = _optional_number(result, "wall_time_s")
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": FRAME_AGE_KIND,
        "phase": FRAME_AGE_PHASE,
        "path": None if path is None else str(path),
        "command": command,
        "time_base": AGE_TIME_BASE,
        "age_definition": AGE_DEFINITION,
        "simulation_time_base": SIMULATION_TIME_BASE,
        "simulation_time_base_verified": True,
        "frame_contract": dict(frame_contract),
        "frame_rate_hz": float(frame_contract["frame_rate_hz"]),
        "frame_period_s": float(frame_contract["frame_period_s"]),
        "percentile_quantile": AGE_PERCENTILE_QUANTILE,
        "percentile_convention": PERCENTILE_CONVENTION,
        "samples": list(samples),
        "frame_age_s": {
            "sample_count": len(ages),
            "min": min(ages),
            "max": max(ages),
            "p99_9": nearest_rank_percentile(ages, AGE_PERCENTILE_QUANTILE),
        },
        "frame_time_s": {
            "sample_count": len(frame_times),
            "min": min(frame_times),
            "max": max(frame_times),
            "p99": nearest_rank_percentile(frame_times, PERCENTILE_QUANTILE),
        },
        "clock_mapping": {
            "simulation_timestep_s": float(result["simulation_timestep_s"]),
            "frames_with_simulation_stamps": sum(
                1 for sample in samples if _finite(sample.get("frame_sim_s"))
            ),
            "real_time_factor": (
                None
                if not sim_time or not wall_time
                else sim_time / wall_time
            ),
        },
        "warmup": dict(result.get("warmup") or {"performed": False}),
        "warmup_samples_excluded": True,
        "transport_measured": False,
        "simulation_paused_while_perceiving": True,
        "scene_sha256": scene_sha256,
        "weights_sha256": weights_sha256,
        "detector_loaded": True,
        "ros_nodes_started": False,
        "mujoco_neck_commanded": True,
        "hardware_motion_commanded": False,
        "measured_here": True,
        "motion_commanded": False,
        "runtime_identity": dict(runtime_identity or result.get("runtime_identity") or {}),
        "digest_convention": DIGEST_CONVENTION,
    }
    document["sha256"] = canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    return document


def _frame_samples(frames: Sequence[Mapping]) -> list[dict]:
    """The per-frame records, with the intervals this module derives from their raw stamps."""

    samples = []
    for index, frame in enumerate(frames):
        record = dict(frame)
        frame_wall = float(record["frame_monotonic_s"])
        received_wall = float(record["received_monotonic_s"])
        decision_wall = float(record["decision_monotonic_s"])
        frame_sim = float(record["frame_sim_s"])
        received_sim = float(record["received_sim_s"])
        decision_sim = float(record["decision_sim_s"])
        record["age_s"] = decision_wall - received_wall
        record["frame_time_s"] = decision_wall - frame_wall
        record["sim_age_s"] = decision_sim - received_sim
        record["sim_frame_time_s"] = decision_sim - frame_sim
        record["age_time_base"] = AGE_TIME_BASE
        record["frame_sim_time_base"] = SIMULATION_TIME_BASE
        samples.append(record)
    return samples


def runtime_identity(*, device=None, detector_loaded=False, weights_sha256=None) -> dict:
    """What the measurement ran as: the interpreter, the module, the tools and what it never started."""

    import mujoco
    import torch

    import so101_demo

    ultralytics_version = None
    try:
        import ultralytics

        ultralytics_version = getattr(ultralytics, "__version__", None)
    except ImportError:  # pragma: no cover - the detector is an optional declaration
        ultralytics_version = None
    cuda_available = bool(torch.cuda.is_available())
    return {
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "so101_demo_module_path": str(Path(so101_demo.__file__).resolve()),
        "mujoco_version": mujoco.__version__,
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "ultralytics_version": ultralytics_version,
        "cuda_available": cuda_available,
        "cuda_device_name": torch.cuda.get_device_name(0) if cuda_available else None,
        "device": device,
        "detector_loaded": bool(detector_loaded),
        "weights_sha256": weights_sha256,
        "mujoco_only": not detector_loaded,
        "ros_nodes_started": False,
        "mujoco_neck_commanded": True,
        "hardware_motion_commanded": False,
    }
