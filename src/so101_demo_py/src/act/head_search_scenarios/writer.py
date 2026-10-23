"""Resolve the scene, gate ownership and write the scenarios document."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
from pathlib import Path
import time

from so101_demo.act.head_search_deadband_measurement.lock_trial import (
    detector_operating_point,
    motion_corridor_rad,
)
from so101_demo.act.head_search_deadband_measurement.plant import (
    _anchor_requests,
    _plant_request,
    build_production_head_detector,
)
from so101_demo.act.head_search_fine_correction_episodes.episode import (
    fine_corridor_rad,
)
from so101_demo.act.head_search_fine_correction_episodes.scene import (
    MujocoEpisodePlant,
    prepare_episode_scene,
    scene_preparation_request,
)
from so101_demo.act.head_search_mujoco_measurements import read_mujoco_timestep
from so101_demo.act.head_search_scenarios.contracts import (
    ARTIFACT,
    CAL_SCENARIO_OWNERSHIP_REFUSED,
    CAL_SCENARIO_RUN_ROOT_EXISTS,
    CAL_SCENARIO_RUNTIME_UNVERIFIED,
    CAL_SCENARIO_SCENE_CONTRADICTORY,
    DEFAULT_INTERRUPTION_FRAME,
    DEFAULT_MAX_FRAMES,
    EVIDENCE_DIR,
    EXPECTED_TERMINALS,
    INTERRUPTION_CLASSES,
    INTERRUPTION_STALE_MARGIN_S,
    JOURNAL_ARTIFACT,
    KIND,
    OUTCOME_CODES,
    PHASE,
    QUALIFICATION_SPLIT,
    RECEIPT_ARTIFACT,
    RECEIPT_KIND,
    SCENARIO_SESSION_ID,
    SCHEMA_VERSION,
    UNMEASURED_CODES,
    _re_raised,
    _refuse,
)
from so101_demo.act.head_search_scenarios.journal import (
    aggregate_scenarios,
    scenario_journal_entry,
)
from so101_demo.act.head_search_scenarios.plan import (
    declared_cup_count,
    qualification_scenarios,
    requires_interruption,
)
from so101_demo.act.head_search_scenarios.scenario_run import run_scenario
from so101_demo.act.head_search_timing_measurement.contracts import (
    CAL_TIMING_DEVICE_UNAVAILABLE,
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    CAL_TIMING_EVIDENCE_MISSING,
    DEFAULT_MAX_SETTLE_S,
    FRAME_PERIOD_S,
    FRAME_RATE_HZ,
    SETTLE_CONSECUTIVE_STEPS,
    SIMULATION_TIME_BASE,
    _digest,
    _finite,
)
from so101_demo.act.head_search_timing_measurement.control import (
    read_control_period,
)
from so101_demo.act.head_search_timing_measurement.documents import (
    runtime_identity as measurement_runtime_identity,
)
from so101_demo.act.head_search_timing_measurement.sweep_runner import _declared_weights
from so101_demo.perception_benchmark.contracts import canonical_sha256


def _resolve_config_scene(dataset_config_path) -> Path:
    """The MuJoCo scene a dataset profile renders, resolved from the profile's own declaration."""

    path = Path(dataset_config_path)
    contents = path.read_text(encoding="utf-8")
    try:
        document = json.loads(contents)
    except json.JSONDecodeError:
        import yaml

        document = yaml.safe_load(contents)
    if not isinstance(document, Mapping) or "mjcf_path" not in document:
        raise _refuse(
            CAL_SCENARIO_SCENE_CONTRADICTORY,
            f"the dataset profile {path} declares no mjcf_path, so the scene these scenarios would be "
            f"rendered from is not declared",
        )
    declared = Path(str(document["mjcf_path"]))
    return declared if declared.is_absolute() else (path.parent / declared).resolve()


def _ownership_gate(
    *, output_dir, evidence_root, final_run, expected_runtime, expected_package_prefix,
    ownership_check, runtime_identity_reader, weights_sha256, production_path,
):
    """Claim the run root through the exclusive-ownership gate, and refuse the run when it refuses.

    The gate is the exclusive-ownership producer (`so101_demo.act.head_search_ownership`): it reads the fresh
    process table, the ROS graph, the GPU compute processes, tmux ownership and the evidence root, binds
    the frozen runtime identity, and writes its receipt into the brand-new root. Nothing runs before it
    passes, and a refusal stops the whole run rather than one scenario.
    """

    runtime = None
    reader = runtime_identity_reader
    if reader is None and final_run is not None:
        from so101_demo.act import head_search_ownership as ownership

        reader = lambda root: ownership.read_runtime_identity(  # noqa: E731 - one-argument adapter
            root, production_config=production_path if production_path is not None else None
        )
    if reader is not None:
        if final_run is None:
            raise _refuse(
                CAL_SCENARIO_RUNTIME_UNVERIFIED,
                "a runtime identity reader was declared without a frozen runtime root to read it from",
            )
        try:
            runtime = dict(reader(Path(final_run)))
        except ValueError as error:
            raise _refuse(CAL_SCENARIO_RUNTIME_UNVERIFIED, str(error)) from error
        declared = runtime.get("weight_sha256_declared")
        if declared != weights_sha256:
            raise _refuse(
                CAL_SCENARIO_RUNTIME_UNVERIFIED,
                f"the runtime of record seals the detector weights {declared!r}, but these scenarios would "
                f"close the loop with {weights_sha256!r}: the run is not the runtime of record",
            )
        if runtime.get("allow_cpu_fallback") is not False:
            raise _refuse(
                CAL_SCENARIO_RUNTIME_UNVERIFIED,
                f"the runtime of record declares allow_cpu_fallback="
                f"{runtime.get('allow_cpu_fallback')!r}, and this producer never falls back to the CPU",
            )

    if ownership_check is None:
        from so101_demo.act import head_search_ownership as ownership

        ownership_check = ownership.check_exclusive_ownership
    document = dict(
        ownership_check(
            run_root=Path(output_dir),
            evidence_root=Path(evidence_root),
            runtime=runtime,
            expected_runtime=expected_runtime or None,
            expected_package_prefix=expected_package_prefix,
        )
    )
    if document.get("status") != "EXCLUSIVE_OWNERSHIP_OK":
        codes = ",".join(str(item.get("code")) for item in document.get("refusals") or ())
        raise _refuse(
            CAL_SCENARIO_OWNERSHIP_REFUSED,
            f"the exclusive-ownership gate refused the run with {codes or 'no code'}: a qualifier that "
            f"does not exclusively own the machine may not measure a scenario",
        )
    receipt_path = Path(output_dir) / "exclusive-ownership.json"
    observations = document.get("observations")
    summary = {
        "status": document.get("status"),
        "checked_at_utc": document.get("checked_at_utc"),
        "refusals": list(document.get("refusals") or ()),
        "owner": dict(document.get("owner") or {}),
        "expected_runtime": document.get("expected_runtime"),
        "expected_package_prefix": document.get("expected_package_prefix"),
        "resources": {
            str(name): {
                "rc": value.get("rc"),
                "row_count": len(value.get("rows") or ()),
                "value": value.get("value"),
                "note": value.get("note"),
            }
            for name, value in sorted((observations or {}).items())
        },
        "receipt_path": str(receipt_path),
        "receipt_sha256": _digest(receipt_path) if receipt_path.is_file() else None,
    }
    return runtime, summary


def write_head_search_scenarios(
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
    evidence_root,
    final_run=None,
    seeds=None,
    device: str = "cuda",
    generator_commit: str = "unrecorded",
    max_settle_s: float = DEFAULT_MAX_SETTLE_S,
    settle_consecutive_steps: int = SETTLE_CONSECUTIVE_STEPS,
    max_frames: int = DEFAULT_MAX_FRAMES,
    interruption_frame: int = DEFAULT_INTERRUPTION_FRAME,
    interruption_margin_s: float = INTERRUPTION_STALE_MARGIN_S,
    expected_runtime: Mapping | None = None,
    expected_package_prefix: str | None = None,
    ownership_check=None,
    runtime_identity_reader=None,
    command=None,
    plant=None,
    detector_factory=None,
    scene_preparer=None,
    clock=time.monotonic,
) -> dict:
    """Run the declared qualification scenarios one at a time and write the phase's own documents.

    Every declared input is read and cross-checked before a single scene is prepared: the scene has to be
    the one the sealed geometry pins, the dataset profile has to render that same scene, the control period
    has to be a whole number of the scene's own timesteps, the detector has to be the weight the sealed
    configuration declares, the frozen candidate has to declare its head operating point, and the device
    has to be a CUDA device that is really there. Then the exclusive-ownership gate claims the run root and
    binds the runtime of record, and only then does the first scenario start.

    The scenarios run **serially**, one MuJoCo plant at a time, each in its own prepared scene and from its
    own declared anchor, and every one of them is journalled - including the ones that fail or refuse. The
    documents this producer creates are `scenarios.json`, `scenario-journal.jsonl`,
    `scenarios/<seed>.json` and `measurement-receipt.json`, plus the gate's own
    `exclusive-ownership.json`.
    """

    started = time.time()
    scene = Path(scene_path)
    seal_path = Path(geometry_seal_path)
    production_path = Path(production_search_config_path)
    controller_path = Path(controller_config_path)
    frozen_path = Path(frozen_candidate_path)
    dataset_path = Path(dataset_config_path)
    partitions_path = Path(scenario_partitions_path)
    for path in (
        scene, seal_path, production_path, controller_path, frozen_path, dataset_path, partitions_path
    ):
        if not path.is_file():
            raise FileNotFoundError(f"the qualification scenarios need {path}")
    weights = Path(weights_path)
    if not weights.is_file():
        raise FileNotFoundError(f"the qualification scenarios need {weights}")

    partitions = json.loads(partitions_path.read_text(encoding="utf-8"))
    items = qualification_scenarios(partitions, seeds=seeds)

    declaration = read_mujoco_timestep(scene)
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    production = json.loads(production_path.read_text(encoding="utf-8"))
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    scene_sha256 = declaration["scene_sha256"]
    sealed_scene = (seal.get("source_digests") or {}).get("scene_sha256")
    if sealed_scene != scene_sha256:
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the sealed geometry pins the scene {sealed_scene}, but the scene these scenarios would step "
            f"the neck in digests to {scene_sha256}",
        )
    declared_scene = _resolve_config_scene(dataset_path)
    if declared_scene.resolve() != scene.resolve():
        raise _refuse(
            CAL_SCENARIO_SCENE_CONTRADICTORY,
            f"the dataset profile {dataset_path} renders {declared_scene}, but these scenarios would step "
            f"the neck in {scene}: the scenes a scenario prepares and the scene this producer renders have "
            f"to be the same one",
        )
    control_period = _re_raised(read_control_period, controller_path)
    timestep = float(declaration["simulation_timestep_s"])
    steps_per_period = control_period / timestep
    if not math.isclose(steps_per_period, round(steps_per_period), rel_tol=0.0, abs_tol=1e-12):
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the sealed controller period {control_period} s is not a whole number of the sealed scene's "
            f"{timestep} s steps, so the scenarios could not command the neck at the production period",
        )
    weights_sha256 = _re_raised(_declared_weights, production, {"weights_path": weights_path})
    if str(device).startswith("cuda") and not _cuda_available():
        raise _refuse(
            CAL_TIMING_DEVICE_UNAVAILABLE,
            f"the detector was declared for {device!r} but no CUDA device is available, and this producer "
            f"never falls back to the CPU",
        )
    operating_point = detector_operating_point(frozen)
    frozen_weights = frozen.get("weight_sha256")
    if isinstance(frozen_weights, str) and frozen_weights != weights_sha256:
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the frozen candidate seals the weights {frozen_weights}, but the production search "
            f"configuration seals {weights_sha256}: the scenarios would not close the loop with the "
            f"selected model",
        )
    values = production.get("values") if isinstance(production.get("values"), Mapping) else {}
    stop_velocity = values.get("stop_velocity_rad_s")
    if not _finite(stop_velocity) or float(stop_velocity) <= 0.0:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            "the production search configuration declares no positive stop_velocity_rad_s, so no scenario's "
            "stop can be proven",
        )
    coarse = _re_raised(motion_corridor_rad, geometry_seal=seal)
    fine = fine_corridor_rad(geometry_seal=seal)

    output = Path(output_dir)
    if output.exists():
        raise _refuse(
            CAL_SCENARIO_RUN_ROOT_EXISTS,
            f"{output} exists; a qualification run is never resumed, continued or overwritten",
        )

    runtime, ownership = _ownership_gate(
        output_dir=output,
        evidence_root=evidence_root,
        final_run=final_run,
        expected_runtime=expected_runtime,
        expected_package_prefix=expected_package_prefix,
        ownership_check=ownership_check,
        runtime_identity_reader=runtime_identity_reader,
        weights_sha256=weights_sha256,
        production_path=production_path,
    )

    prepared = prepare_episode_scene if scene_preparer is None else scene_preparer
    detector = (
        None
        if detector_factory is not None
        else build_production_head_detector(
            weights_path=weights,
            operating_point=operating_point,
            production=production,
            frame_id="head_camera_frame",
            device=device,
            attempt_id=f"{SCENARIO_SESSION_ID}-detector",
            session_id=SCENARIO_SESSION_ID,
        )
    )
    runtime_identity_document = (
        dict(runtime)
        if runtime is not None
        else measurement_runtime_identity(
            device=device, detector_loaded=True, weights_sha256=weights_sha256
        )
    )
    evidence_dir = output / EVIDENCE_DIR
    evidence_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []
    scene_state_digests: dict[str, str] = {}
    for index, item in enumerate(items):
        seed = int(item["seed"])
        condition_class = str(item["condition_class"])
        anchor = str(item["anchor"])
        request_base = f"{SCENARIO_SESSION_ID}-{seed}"
        requests = _anchor_requests(
            seal=seal,
            production=production,
            anchors=[anchor],
            attempt_id=request_base,
            session_id=SCENARIO_SESSION_ID,
        )
        if len(requests) != 1:
            raise _refuse(
                CAL_TIMING_EVIDENCE_MISSING,
                f"the scenario {seed} declares the anchor {anchor!r}, which the sealed geometry does not "
                f"resolve to exactly one search start",
            )
        request = requests[0]
        cup_count = declared_cup_count(condition_class)
        state = prepared(
            **scene_preparation_request(
                dataset_config_path=dataset_path,
                generator_commit=generator_commit,
                seed=seed,
                cup_count=cup_count,
                scenario=condition_class,
                scene_path=scene,
                split=QUALIFICATION_SPLIT,
            )
        )
        scene_state_digests[str(seed)] = (
            canonical_sha256(dict(state)) if isinstance(state, Mapping) and state else ""
        )
        scenario_evidence = {
            "scene_sha256": scene_sha256,
            "geometry_seal_sha256": _digest(seal_path),
            "production_search_config_sha256": _digest(production_path),
            "frozen_candidate_sha256": _digest(frozen_path),
            "weights_sha256": weights_sha256,
            "dataset_config_sha256": _digest(dataset_path),
            "scenario_partitions_sha256": _digest(partitions_path),
            "controller_config_sha256": _digest(controller_path),
            "scene_state_sha256": scene_state_digests[str(seed)],
            "runtime_identity": runtime_identity_document,
            "detector_operating_point": dict(operating_point),
            "device": str(device),
            "generator_commit": str(generator_commit),
            "command": command,
            "scene_group_id": item["scene_group_id"],
            "prepared_by": (
                "MuJoCoDatasetRenderer._prepare(numpy.random.default_rng(seed), "
                "DatasetScenario.for_cup_count(cup_count)) of the head dataset profile, exactly as the "
                "recorder prepared the split it rendered"
            ),
        }
        episode_request = dict(request)
        episode_request.update(
            {
                "scene_state": state,
                "seed": seed,
                "scenario": condition_class,
                "split": QUALIFICATION_SPLIT,
            }
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
                        camera=seal.get("camera") if isinstance(seal.get("camera"), Mapping) else {},
                        control_period_s=control_period,
                        max_settle_s=max_settle_s,
                        settle_consecutive_steps=settle_consecutive_steps,
                    ),
                    "scene_state": state,
                    "seed": seed,
                    "scenario": condition_class,
                    "split": QUALIFICATION_SPLIT,
                }
            )
        )
        try:
            entry = run_scenario(
                controller_config=request["controller_config"],
                plant=episode_plant,
                detector=(
                    detector
                    if detector_factory is None
                    else detector_factory(episode_plant, episode_request)
                ),
                coarse_corridor_rad=coarse,
                fine_corridor_rad=fine,
                scenario={**item, "scenario_index": index},
                stop_velocity_rad_s=float(stop_velocity),
                interruption=requires_interruption(condition_class),
                interruption_frame=interruption_frame,
                interruption_margin_s=interruption_margin_s,
                max_frames=max_frames,
                settle_consecutive_steps=settle_consecutive_steps,
                max_settle_s=max_settle_s,
                evidence=scenario_evidence,
                clock=clock,
            )
        finally:
            close = getattr(episode_plant, "close", None)
            if callable(close):
                close()
        entry["scenario_index"] = index
        entries.append(entry)
        row = scenario_journal_entry(entry)
        (evidence_dir / f"{seed}.json").write_text(
            json.dumps(entry, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        with (output / JOURNAL_ARTIFACT).open("a", encoding="utf-8") as journal:
            journal.write(json.dumps(row, sort_keys=True) + "\n")

    aggregate = aggregate_scenarios(entries)
    anchor_split: dict[str, int] = {}
    for item in items:
        anchor_split[str(item["anchor"])] = anchor_split.get(str(item["anchor"]), 0) + 1
    records = [scenario_journal_entry(entry) for entry in entries]
    document_path = output / ARTIFACT
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "phase": PHASE,
        "path": str(document_path),
        "command": command,
        "split": QUALIFICATION_SPLIT,
        "seeds": [int(item["seed"]) for item in items],
        "scenario_count": aggregate["scenario_count"],
        "passed_count": aggregate["passed_count"],
        "failed_count": aggregate["failed_count"],
        "refused_count": aggregate["refused_count"],
        "by_condition_class": aggregate["by_condition_class"],
        "by_anchor": aggregate["by_anchor"],
        "anchor_split": anchor_split,
        "terminal_statuses": aggregate["terminal_statuses"],
        "zero_wrong_locks": aggregate["zero_wrong_locks"],
        "wrong_locks": aggregate["wrong_locks"],
        "fine_corrections": aggregate["fine_corrections"],
        "cumulative_fine_correction_rad": aggregate["cumulative_fine_correction_rad"],
        "cadence_all_continuous": aggregate["cadence_all_continuous"],
        "stop_proofs_all_proven": aggregate["stop_proofs_all_proven"],
        "qualification_verdict": aggregate["qualification_verdict"],
        "qualification_verdict_owner": aggregate["qualification_verdict_owner"],
        "fit_warning": aggregate["fit_warning"],
        "expected_terminals": {name: list(values) for name, values in EXPECTED_TERMINALS.items()},
        "interruption_classes": list(INTERRUPTION_CLASSES),
        "records": records,
        "outcome_codes": list(OUTCOME_CODES),
        "unmeasured_codes": list(UNMEASURED_CODES),
        "time_base": SIMULATION_TIME_BASE,
        "simulation_timestep_s": timestep,
        "control_period_s": control_period,
        "steps_per_period": int(round(steps_per_period)),
        "frame_period_s": FRAME_PERIOD_S,
        "frame_rate_hz": FRAME_RATE_HZ,
        "coarse_corridor_rad": [float(bound) for bound in coarse],
        "fine_corridor_rad": [float(bound) for bound in fine],
        "scene_path": str(scene),
        "scene_sha256": scene_sha256,
        "geometry_seal": {"path": str(seal_path), "sha256": _digest(seal_path)},
        "production_search_config": {
            "path": str(production_path),
            "sha256": _digest(production_path),
        },
        "values_sha256": canonical_sha256(dict(values)),
        "values_count": len(values),
        "frozen_candidate": {"path": str(frozen_path), "sha256": _digest(frozen_path)},
        "weights": {"path": str(weights), "sha256": weights_sha256},
        "dataset_config": {"path": str(dataset_path), "sha256": _digest(dataset_path)},
        "controller_config": {"path": str(controller_path), "sha256": _digest(controller_path)},
        "scenario_partitions": {
            "path": str(partitions_path),
            "sha256": _digest(partitions_path),
        },
        "scene_state_sha256_by_seed": scene_state_digests,
        "detector_operating_point": dict(operating_point),
        "device": str(device),
        "cuda_used": str(device).startswith("cuda"),
        "detector_loaded": detector is not None or detector_factory is not None,
        "runtime_identity": runtime_identity_document,
        "ownership_receipt": ownership,
        "evidence_dir": str(evidence_dir),
        "journal_path": str(output / JOURNAL_ARTIFACT),
        "max_frames": int(max_frames),
        "interruption_frame": int(interruption_frame),
        "interruption_stale_margin_s": float(interruption_margin_s),
        "settle_consecutive_steps": int(settle_consecutive_steps),
        "max_settle_s": float(max_settle_s),
        "scenario_preparation": {
            "dataset_config_path": str(dataset_path),
            "generator_commit": str(generator_commit),
            "condition_class_by_seed": {
                str(item["seed"]): str(item["condition_class"]) for item in items
            },
            "cup_count_by_seed": {
                str(item["seed"]): declared_cup_count(str(item["condition_class"]))
                for item in items
            },
            "anchor_by_seed": {str(item["seed"]): str(item["anchor"]) for item in items},
            "serial": (
                "one scenario at a time: each one prepares its own scene, closes its own plant before the "
                "next seed starts, and no two scenarios share a MuJoCo instance"
            ),
        },
        "measured_here": (
            "one closed-loop MuJoCo search per declared qualification seed, on the head camera, with the "
            "selected model behind the production head detector at its declared head operating point"
        ),
        "ros_nodes_started": False,
        "mujoco_neck_commanded": True,
        "hardware_motion_commanded": False,
        "motion_commanded": False,
        "elapsed_s": time.time() - started,
    }
    document["sha256"] = canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    document_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    receipt = {
        **aggregate,
        "schema_version": SCHEMA_VERSION,
        "kind": RECEIPT_KIND,
        "phase": PHASE,
        "status": (
            "SUCCEEDED"
            if aggregate["refused_count"] == 0 and aggregate["failed_count"] == 0
            else "MEASURED_WITH_FAILED_OR_REFUSED_SCENARIOS"
        ),
        "command": command,
        "output_dir": str(output),
        "document_path": str(document_path),
        "document_sha256": document["sha256"],
        "journal_path": str(output / JOURNAL_ARTIFACT),
        "evidence_dir": str(evidence_dir),
        "seeds": [int(item["seed"]) for item in items],
        "anchor_split": anchor_split,
        "records": records,
        "scene_sha256": scene_sha256,
        "values_sha256": canonical_sha256(dict(values)),
        "weights_sha256": weights_sha256,
        "production_search_config_sha256": _digest(production_path),
        "geometry_seal_sha256": _digest(seal_path),
        "frozen_candidate_sha256": _digest(frozen_path),
        "dataset_config_sha256": _digest(dataset_path),
        "controller_config_sha256": _digest(controller_path),
        "scenario_partitions_sha256": _digest(partitions_path),
        "device": str(device),
        "cuda_used": str(device).startswith("cuda"),
        "allow_cpu_fallback": False,
        "detector_loaded": document["detector_loaded"],
        "detector_operating_point": dict(operating_point),
        "runtime_identity": runtime_identity_document,
        "ownership_receipt": ownership,
        "control_period_s": control_period,
        "simulation_timestep_s": timestep,
        "frame_period_s": FRAME_PERIOD_S,
        "frame_rate_hz": FRAME_RATE_HZ,
        "coarse_corridor_rad": [float(bound) for bound in coarse],
        "fine_corridor_rad": [float(bound) for bound in fine],
        "max_frames": int(max_frames),
        "elapsed_s": document["elapsed_s"],
        "ros_nodes_started": False,
        "mujoco_neck_commanded": True,
        "hardware_motion_commanded": False,
        "transport_measured": False,
        "tracking_measured": False,
        "motion_commanded": False,
    }
    (output / RECEIPT_ARTIFACT).write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "document": document,
        "receipt": receipt,
        "document_path": document_path,
        "output_dir": output,
        "entries": entries,
    }


def _cuda_available() -> bool:
    """Whether the declared CUDA device is really there; the producer never falls back to the CPU."""

    import torch

    return bool(torch.cuda.is_available())
