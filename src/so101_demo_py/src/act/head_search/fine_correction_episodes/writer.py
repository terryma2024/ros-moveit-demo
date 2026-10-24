"""Write the fine-correction episodes document."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
from pathlib import Path
import time

from so101_demo.act.head_search.deadband_measurement.lock_trial import (
    detector_operating_point,
)
from so101_demo.act.head_search.deadband_measurement.plant import (
    _anchor_requests,
    _plant_request,
    build_production_head_detector,
)
from so101_demo.act.head_search.fine_correction_episodes.contracts import (
    ARTIFACT,
    CAL_FINE_EPISODE_SCENE_CONTRADICTORY,
    DEFAULT_MAX_FRAMES,
    HELD_OUT_SPLIT,
    MEASUREMENT_ATTEMPT_ID,
    MEASUREMENT_SESSION_ID,
    RECEIPT_ARTIFACT,
    RECEIPT_KIND,
    SCHEMA_VERSION,
    _re_raised,
    _refuse,
)
from so101_demo.act.head_search.fine_correction_episodes.episode import (
    _fine_corridor_check,
    build_fine_correction_episodes,
    coarse_corridor_rad,
    condition_class_for_index,
    cup_count_for_condition_class,
    declared_split_seeds,
    fine_corridor_rad,
    run_fine_correction_episode,
)
from so101_demo.act.head_search.fine_correction_episodes.scene import (
    MujocoEpisodePlant,
    _cuda_available,
    _measurement_budget,
    _resolve_config_scene,
    prepare_episode_scene,
    scenario_name_for_cup_count,
    scene_preparation_request,
)
from so101_demo.act.head_search.mujoco_measurements import read_mujoco_timestep
from so101_demo.act.head_search.timing_measurement.contracts import (
    CAL_TIMING_DEVICE_UNAVAILABLE,
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    CAL_TIMING_EVIDENCE_MISSING,
    DEFAULT_MAX_SETTLE_S,
    SETTLE_CONSECUTIVE_STEPS,
    _digest,
)
from so101_demo.act.head_search.timing_measurement.control import (
    read_control_period,
)
from so101_demo.act.head_search.timing_measurement.documents import (
    runtime_identity as measurement_runtime_identity,
)
from so101_demo.act.head_search.timing_measurement.sweep_runner import _declared_weights
from so101_demo.perception_benchmark.contracts import canonical_sha256


def write_head_search_fine_correction_episodes(
    *,
    scene_path,
    geometry_seal_path,
    production_search_config_path,
    controller_config_path,
    frozen_candidate_path,
    weights_path,
    dataset_config_path,
    scenario_partitions_path,
    output_dir,
    seeds=None,
    split: str = HELD_OUT_SPLIT,
    anchors=None,
    device: str = "cuda",
    generator_commit: str = "unrecorded",
    max_settle_s: float = DEFAULT_MAX_SETTLE_S,
    settle_consecutive_steps: int = SETTLE_CONSECUTIVE_STEPS,
    max_frames: int = DEFAULT_MAX_FRAMES,
    measurement_budget: Mapping | None = None,
    attempt_id: str = MEASUREMENT_ATTEMPT_ID,
    session_id: str = MEASUREMENT_SESSION_ID,
    command=None,
    plant=None,
    detector_factory=None,
    scene_preparer=None,
) -> dict:
    """Run one closed-loop episode per declared held-out seed and write the document phase 6 reads.

    Every declared input is read and cross-checked before a single scene is prepared: the scene has to be
    the one the sealed geometry pins, the dataset profile has to render that same scene, the control period
    has to be a whole number of the scene's own timesteps, the detector has to be the weight the sealed
    configuration declares, the frozen candidate has to declare its head operating point, the seeds have to
    belong to the declared held-out split, and the anchor's start and the instrument budget have to lie
    inside their corridors. The episodes then run one seed at a time, and the document and its receipt are
    the only files this producer creates.
    """

    started = time.time()
    scene = Path(scene_path)
    seal_path = Path(geometry_seal_path)
    production_path = Path(production_search_config_path)
    controller_path = Path(controller_config_path)
    frozen_path = Path(frozen_candidate_path)
    dataset_path = Path(dataset_config_path)
    partitions_path = Path(scenario_partitions_path)
    for path in (scene, seal_path, production_path, controller_path, frozen_path, dataset_path,
                 partitions_path):
        if not path.is_file():
            raise FileNotFoundError(f"the fine-correction episodes need {path}")
    weights = Path(weights_path)
    if not weights.is_file():
        raise FileNotFoundError(f"the fine-correction episodes need {weights}")

    partitions = json.loads(partitions_path.read_text(encoding="utf-8"))
    declared_seeds = declared_split_seeds(partitions, split=split, seeds=seeds)
    condition_classes = partitions.get("condition_classes")
    scenarios = [
        condition_class_for_index(index, condition_classes) for index in range(len(declared_seeds))
    ]

    declaration = read_mujoco_timestep(scene)
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    production = json.loads(production_path.read_text(encoding="utf-8"))
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    scene_sha256 = declaration["scene_sha256"]
    sealed_scene = (seal.get("source_digests") or {}).get("scene_sha256")
    if sealed_scene != scene_sha256:
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the sealed geometry pins the scene {sealed_scene}, but the scene these episodes would step "
            f"the neck in digests to {scene_sha256}",
        )
    declared_scene = _resolve_config_scene(dataset_path)
    if declared_scene.resolve() != scene.resolve():
        raise _refuse(
            CAL_FINE_EPISODE_SCENE_CONTRADICTORY,
            f"the dataset profile {dataset_path} renders {declared_scene}, but these episodes would step "
            f"the neck in {scene}: the scenes a held-out seed prepares and the scene this measurement "
            f"renders have to be the same one",
        )
    control_period = _re_raised(read_control_period, controller_path)
    timestep = float(declaration["simulation_timestep_s"])
    steps_per_period = control_period / timestep
    if not math.isclose(steps_per_period, round(steps_per_period), rel_tol=0.0, abs_tol=1e-12):
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the sealed controller period {control_period} s is not a whole number of the sealed scene's "
            f"{timestep} s steps, so the episodes could not command the neck at the production period",
        )
    weights_sha256 = _re_raised(_declared_weights, production, {"weights_path": weights_path})
    if str(device).startswith("cuda") and not _cuda_available():
        raise _refuse(
            CAL_TIMING_DEVICE_UNAVAILABLE,
            f"the detector was declared for {device!r} but no CUDA device is available, and this "
            f"measurement never falls back to the CPU",
        )
    operating_point = detector_operating_point(frozen)
    frozen_weights = frozen.get("weight_sha256")
    if isinstance(frozen_weights, str) and frozen_weights != weights_sha256:
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the frozen candidate seals the weights {frozen_weights}, but the production search "
            f"configuration seals {weights_sha256}: the episodes would not close the loop with the "
            f"selected model",
        )
    coarse = coarse_corridor_rad(geometry_seal=seal)
    fine = fine_corridor_rad(geometry_seal=seal)
    requests = _anchor_requests(
        seal=seal,
        production=production,
        anchors=anchors,
        attempt_id=attempt_id,
        session_id=session_id,
    )
    if len(requests) != 1:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            f"this measurement runs one episode per held-out seed from exactly one sealed anchor, but "
            f"{len(requests)} were declared: the anchor is the search start every episode shares, and the "
            f"the coarse corridor admits only the anchors whose start lies inside the required search domain",
        )
    request = requests[0]
    _fine_corridor_check(
        angle_rad=request["search_start_rad"],
        corridor_rad=coarse,
        what=f"declared search start of the anchor {request['anchor']!r}",
    )
    budget = _measurement_budget(
        measurement_budget, start_rad=float(request["search_start_rad"]), fine_corridor_rad=fine
    )
    controller = dict(request["controller_config"])
    controller["max_fine_corrections"] = budget["max_fine_corrections"]
    controller["max_fine_total_rad"] = budget["max_fine_total_rad"]
    camera = seal.get("camera") if isinstance(seal.get("camera"), Mapping) else {}
    output = Path(output_dir)
    output.mkdir(parents=True)

    prepare = prepare_episode_scene if scene_preparer is None else scene_preparer
    detector = (
        None
        if detector_factory is not None
        else build_production_head_detector(
            weights_path=weights,
            operating_point=operating_point,
            production=production,
            frame_id=controller["frame_id"],
            device=device,
            attempt_id=attempt_id,
            session_id=session_id,
        )
    )
    episodes: list[dict] = []
    scene_state_digests: dict[str, str] = {}
    for seed, scenario in zip(declared_seeds, scenarios):
        cup_count = cup_count_for_condition_class(scenario)
        state = prepare(
            **scene_preparation_request(
                dataset_config_path=dataset_path,
                generator_commit=generator_commit,
                seed=seed,
                cup_count=cup_count,
                scenario=scenario,
                scene_path=scene,
                split=split,
            )
        )
        episode_request = dict(request)
        episode_request["controller_config"] = controller
        episode_request["scene_state"] = state
        episode_request["seed"] = int(seed)
        scene_state_digests[str(seed)] = (
            canonical_sha256(dict(state)) if isinstance(state, Mapping) and state else ""
        )
        episode_plant = (
            plant(episode_request)
            if plant is not None
            else MujocoEpisodePlant(
                {
                    **_plant_request(
                        request=episode_request,
                        scene=scene,
                        seal=seal,
                        camera=camera,
                        control_period_s=control_period,
                        max_settle_s=max_settle_s,
                        settle_consecutive_steps=settle_consecutive_steps,
                    ),
                    "scene_state": state,
                    "seed": int(seed),
                    "scenario": scenario,
                    "split": split,
                }
            )
        )
        try:
            episodes.append(
                run_fine_correction_episode(
                    controller_config=controller,
                    plant=episode_plant,
                    detector=(
                        detector
                        if detector_factory is None
                        else detector_factory(episode_plant, episode_request)
                    ),
                    coarse_corridor_rad=coarse,
                    fine_corridor_rad=fine,
                    episode_id=f"{split}-{int(seed)}",
                    seed=int(seed),
                    split=split,
                    scenario=scenario,
                    anchor=request["anchor"],
                    max_frames=max_frames,
                    settle_consecutive_steps=settle_consecutive_steps,
                    max_settle_s=max_settle_s,
                )
            )
        finally:
            close = getattr(episode_plant, "close", None)
            if callable(close):
                close()
    document_path = output / ARTIFACT
    document = build_fine_correction_episodes(
        path=document_path,
        command=command,
        episodes=episodes,
        controller_config=controller,
        control={
            "control_period_s": control_period,
            "source_path": str(controller_path),
            "source_sha256": _digest(controller_path),
            "key": "controller_manager.ros__parameters.update_rate",
            "update_rate_hz": 1.0 / control_period,
            "steps_per_period": int(round(steps_per_period)),
            "declared_by": "the sealed controller configuration",
        },
        scene_path=scene,
        scene_sha256=scene_sha256,
        dataset_config_path=dataset_path,
        dataset_config_sha256=_digest(dataset_path),
        geometry_seal_path=seal_path,
        geometry_seal_sha256=_digest(seal_path),
        production_search_config_path=production_path,
        production_search_config_sha256=_digest(production_path),
        frozen_candidate_path=frozen_path,
        frozen_candidate_sha256=_digest(frozen_path),
        weights_path=weights,
        weights_sha256=weights_sha256,
        scenario_partitions_path=partitions_path,
        scenario_partitions_sha256=_digest(partitions_path),
        split=split,
        seeds=declared_seeds,
        detector_operating_point=operating_point,
        coarse_corridor_rad=coarse,
        fine_corridor_rad=fine,
        measurement_budget=budget,
        runtime_identity_document=(
            {}
            if plant is not None
            else measurement_runtime_identity(
                device=device, detector_loaded=True, weights_sha256=weights_sha256
            )
        ),
        scene_preparation={
            "cup_placement": (
                "prepared by the dataset renderer of the head profile for this seed "
                "(MuJoCoDatasetRenderer._prepare with numpy.random.default_rng(seed)), not the seal's "
                "anchor sample: the held-out scenes place their cup where the dataset put it"
            ),
            "dataset_config_path": str(dataset_path),
            "generator_commit": str(generator_commit),
            "condition_class_by_seed": {
                str(seed): scenario for seed, scenario in zip(declared_seeds, scenarios)
            },
            "scenario_by_seed": {
                str(seed): scenario_name_for_cup_count(cup_count_for_condition_class(scenario))
                for seed, scenario in zip(declared_seeds, scenarios)
            },
            "cup_count_by_seed": {
                str(seed): cup_count_for_condition_class(scenario)
                for seed, scenario in zip(declared_seeds, scenarios)
            },
            "scene_state_sha256_by_seed": scene_state_digests,
            "held_actuators": (
                "every actuator except the neck holds the position the dataset preparation left it in, so "
                "the frames are rendered from the prepared scene rather than from one whose arm drifted "
                "toward the actuators' unset targets; each episode records the residual drift"
            ),
        },
        anchors=[request["anchor"]],
        detector_loaded=detector is not None or detector_factory is not None,
        device=device,
    )
    document["production_declaration"] = {
        "max_fine_corrections": production.get("values", {}).get("max_fine_corrections"),
        "max_fine_total_rad": production.get("values", {}).get("max_fine_total_rad"),
        "center_deadband_px": production.get("values", {}).get("center_deadband_px"),
        "vertical_bounds_px": production.get("values", {}).get("vertical_bounds_px"),
        "path": str(production_path),
        "sha256": _digest(production_path),
    }
    document["sha256"] = canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    document_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": RECEIPT_KIND,
        "status": "SUCCEEDED" if document["refused_count"] == 0 else "MEASURED_WITH_REFUSED_EPISODES",
        "command": command,
        "output_dir": str(output),
        "document_path": str(document_path),
        "document_sha256": document["sha256"],
        "scene_path": str(scene),
        "scene_sha256": scene_sha256,
        "dataset_config_path": str(dataset_path),
        "dataset_config_sha256": _digest(dataset_path),
        "geometry_seal_path": str(seal_path),
        "geometry_seal_sha256": _digest(seal_path),
        "production_search_config_path": str(production_path),
        "production_search_config_sha256": _digest(production_path),
        "frozen_candidate_path": str(frozen_path),
        "frozen_candidate_sha256": _digest(frozen_path),
        "scenario_partitions_path": str(partitions_path),
        "scenario_partitions_sha256": _digest(partitions_path),
        "weights_path": str(weights),
        "weights_sha256": weights_sha256,
        "detector_operating_point": dict(operating_point),
        "split": split,
        "seeds": declared_seeds,
        "scenario_by_seed": {
            str(seed): scenario for seed, scenario in zip(declared_seeds, scenarios)
        },
        "episode_count": document["episode_count"],
        "succeeded_count": document["succeeded_count"],
        "refused_count": document["refused_count"],
        "records": document["records"],
        "warmup": dict(document["warmup"]),
        "refused_episodes": [
            {
                "episode_id": record["episode_id"],
                "failure_code": episode.get("failure_code"),
                "failure_detail": episode.get("failure_detail"),
            }
            for record, episode in zip(document["records"], episodes)
            if record["succeeded"] is False
        ],
        "coarse_corridor_rad": [float(bound) for bound in coarse],
        "fine_corridor_rad": [float(bound) for bound in fine],
        "measurement_budget": dict(budget),
        "anchor_names": [request["anchor"]],
        "simulation_timestep_s": timestep,
        "control_period_s": control_period,
        "max_settle_s": float(max_settle_s),
        "settle_consecutive_steps": int(settle_consecutive_steps),
        "max_frames": int(max_frames),
        "elapsed_s": time.time() - started,
        "runtime_identity": dict(document["runtime_identity"]),
        "ros_nodes_started": False,
        "mujoco_neck_commanded": True,
        "hardware_motion_commanded": False,
        "transport_measured": False,
        "tracking_measured": False,
        "motion_commanded": False,
        "detector_loaded": document["detector_loaded"],
    }
    (output / RECEIPT_ARTIFACT).write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "document": document,
        "receipt": receipt,
        "document_path": document_path,
        "output_dir": output,
        "episodes": episodes,
    }
