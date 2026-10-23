"""Measure the operating points over the plan."""

from __future__ import annotations

import json
import os
from pathlib import Path
import time

import so101_demo
from so101_demo.act.head_search_operating_point import (
    validate_head_search_calibration_operating_point,
)
from so101_demo.act.head_search_operating_point_measurement.documents import (
    _boxes,
    _verified_rule,
    episode_frame,
    operating_point_measurement_document,
    static_frame,
    toolchain_identity,
    truth_from_instances,
)
from so101_demo.act.head_search_operating_point_measurement.planning import (
    CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY,
    CAL_OPERATING_POINT_EVIDENCE_MISSING,
    CANDIDATE_IDS,
    DOCUMENT_NAME,
    DOMAINS,
    HELD_OUT_SPLIT,
    MATCH_RADIUS_PX,
    PHASE,
    RECEIPT_KIND,
    RECEIPT_NAME,
    RECORDING_MIN_CONFIDENCE,
    RECORDING_TRACKING_IOU,
    SCHEMA_VERSION,
    SELECTION_SPLITS,
    VAL_SPLIT,
    _digest_of,
    _finite,
    _refuse,
    image_size,
    operating_point_grid,
    plan_operating_point_measurement,
)


def measure_operating_point_measurements(
    *,
    geometry_seal_path,
    head_dataset_manifest_path,
    task_dataset_manifest_path,
    dataset_config_path,
    production_config_path,
    episode_partitions_path,
    selection_rule_path,
    task_selection_rule_path,
    weights_dir,
    frozen_candidate_paths,
    output_dir,
    device="cuda",
    seed_limit=None,
    match_radius_px=MATCH_RADIUS_PX,
    command=None,
) -> dict:
    """Measure the frames phase 3 consumes, then let the installed phase 3 select every candidate's point.

    The heavy half: it renders the calibration episodes in the sealed scene (the same deterministic
    `_prepare` the campaign's recorder used, with the ground truth of each camera's own segmentation) and
    predicts on the frozen datasets' val images, recording one detection list per candidate per frame at
    the grid's recording point - the production detector's own point (`conf=0.25`, Ultralytics' default
    NMS IoU 0.7), which is the grid's own corner, and with the production detector's own RGB-to-BGR
    conversion for a rendered frame. The val cells are re-measured with the gate's own `_measure_static` at
    each candidate's declared point and reported as a reference. The measurement document is written
    before phase 3 runs, so a phase-3 refusal (a dirty no-cup point, a split leak) leaves the measured
    frames behind as evidence instead of an empty directory. Nothing here commands motion or starts ROS.
    """

    import mujoco
    import numpy as np
    from ultralytics import YOLO

    from so101_demo.act.head_search_coarse_step_measurement.measurement import runtime_identity
    from so101_demo.adapters.perception.mujoco_dataset.config import load_dataset_config
    from so101_demo.adapters.perception.mujoco_dataset.models import DatasetScenario
    from so101_demo.adapters.perception.mujoco_dataset.renderer import MuJoCoDatasetRenderer
    from so101_demo.cli.evaluate_head_search_yolo_candidates import _dataset_sums, _measure_static
    from so101_demo.perception_benchmark.head_search_models import (
        load_frozen_candidate,
        verify_split_manifest,
    )

    started = time.time()
    geometry_path = Path(geometry_seal_path)
    head_manifest_path = Path(head_dataset_manifest_path)
    task_manifest_path = Path(task_dataset_manifest_path)
    config_path = Path(dataset_config_path)
    production_path = Path(production_config_path)
    partitions_path = Path(episode_partitions_path)
    rule_paths = {"head": Path(selection_rule_path), "task": Path(task_selection_rule_path)}
    weights_root = Path(weights_dir)
    output = Path(output_dir)
    for path in (
        geometry_path,
        head_manifest_path,
        task_manifest_path,
        config_path,
        production_path,
        partitions_path,
        *rule_paths.values(),
    ):
        if not path.is_file():
            raise FileNotFoundError(f"the measurement needs {path}")
    if not weights_root.is_dir():
        raise FileNotFoundError(f"the measurement needs the weights directory {weights_root}")
    try:
        output.mkdir(parents=True)
    except FileExistsError as error:
        raise _refuse(
            CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY,
            f"{output} exists; a measurement is never resumed, continued or overwritten",
        ) from error

    seal = json.loads(geometry_path.read_text(encoding="utf-8"))
    head_manifest = json.loads(head_manifest_path.read_text(encoding="utf-8"))
    task_manifest = json.loads(task_manifest_path.read_text(encoding="utf-8"))
    partitions = json.loads(partitions_path.read_text(encoding="utf-8"))
    production_config = json.loads(production_path.read_text(encoding="utf-8"))
    rules = {
        domain: _verified_rule(
            rule=json.loads(path.read_text(encoding="utf-8")),
            domain=domain,
            grid=operating_point_grid(production_config=production_config),
        )
        for domain, path in rule_paths.items()
    }

    frozen_paths = {}
    frozen_documents = {}
    for path in frozen_candidate_paths:
        loaded = load_frozen_candidate(path)
        frozen_paths[loaded.candidate_id] = Path(path)
        frozen_documents[loaded.candidate_id] = dict(loaded.document)
    candidates = sorted(
        (dict(load_frozen_candidate(path).document) for path in frozen_paths.values()),
        key=lambda document: document["candidate_id"],
    )
    weights_paths = {
        candidate["candidate_id"]: weights_root / f"{candidate['candidate_id']}.pt"
        for candidate in candidates
    }
    missing = sorted(str(path) for path in weights_paths.values() if not path.is_file())
    if missing:
        raise _refuse(
            CAL_OPERATING_POINT_EVIDENCE_MISSING,
            f"no weight file for {', '.join(missing)}; every candidate is measured as its own bytes",
        )
    weights_digests = {name: _digest_of(path) for name, path in weights_paths.items()}

    plan = plan_operating_point_measurement(
        geometry_seal=seal,
        head_dataset_manifest=head_manifest,
        task_dataset_manifest=task_manifest,
        partitions=partitions,
        production_config=production_config,
        frozen_candidates=candidates,
        weights_sha256=weights_digests,
        seed_limit=seed_limit,
        match_radius_px=match_radius_px,
    )

    roots = {"head": head_manifest_path.parent, "task": task_manifest_path.parent}
    verified = {}
    for domain, manifest, manifest_path in (
        ("head", head_manifest, head_manifest_path),
        ("task", task_manifest, task_manifest_path),
    ):
        samples = verify_split_manifest(
            manifest,
            plan["val_split"],
            dataset_root=roots[domain],
            domain=domain,
            sums=_dataset_sums(roots[domain]),
        )
        declared = {sample["seed"] for sample in plan["domains"][domain]["val_samples"]}
        if {int(sample["seed"]) for sample in samples} != declared:
            raise _refuse(
                CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY,
                f"the gate's own reading of the {domain} {plan['val_split']} split is not the one this "
                "measurement planned; the two must measure the same images",
            )
        verified[domain] = samples

    renderer = MuJoCoDatasetRenderer(
        load_dataset_config(
            config_path,
            generator_commit=head_manifest.get("generator_commit"),
            sample_limit=None,
        )
    )
    models = {name: YOLO(str(path)) for name, path in weights_paths.items()}
    frames: list[dict] = []
    predictions = 0
    without_geometry = 0
    static_reference: dict[str, dict] = {}
    try:
        neck = mujoco.mj_name2id(renderer._model, mujoco.mjtObj.mjOBJ_JOINT, "neck_yaw_joint")
        if neck < 0:
            raise _refuse(
                CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY,
                "the sealed scene has no neck_yaw_joint, so no calibration episode can be rendered",
            )
        address = int(renderer._model.jnt_qposadr[neck])
        cameras = {}
        for domain in DOMAINS:
            camera_name = plan["domains"][domain]["camera_name"]
            camera = mujoco.mj_name2id(renderer._model, mujoco.mjtObj.mjOBJ_CAMERA, camera_name)
            if camera < 0:
                raise _refuse(
                    CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY,
                    f"the sealed scene has no camera {camera_name!r} for the {domain} domain",
                )
            cameras[domain] = camera
        body_of_geom = {
            geom: int(renderer._model.geom_bodyid[geom]) for geom in range(renderer._model.ngeom)
        }
        body_name = {
            body: mujoco.mj_id2name(renderer._model, mujoco.mjtObj.mjOBJ_BODY, body)
            for body in set(body_of_geom.values())
        }
        cup_bodies = sorted(
            body for body, name in body_name.items() if name and "cup" in name.lower()
        )
        geoms_of_body = {
            body: [geom for geom, owner in body_of_geom.items() if owner == body]
            for body in cup_bodies
        }

        def segmentation(camera: int) -> np.ndarray:
            segmentation_renderer = renderer._segmentation_renderer
            segmentation_renderer.enable_segmentation_rendering()
            try:
                segmentation_renderer.update_scene(renderer._data, camera=camera)
                return renderer._geom_ids(np.array(segmentation_renderer.render(), copy=True))
            finally:
                segmentation_renderer.disable_segmentation_rendering()

        def episode_truth(image) -> list[dict]:
            records = []
            for body in cup_bodies:
                rows, columns = np.nonzero(np.isin(image, geoms_of_body[body]))
                if columns.size:
                    records.append(
                        {
                            "instance_id": body_name[body],
                            "x": float(columns.mean()),
                            "y": float(rows.mean()),
                            "visible_px": int(columns.size),
                            "truth_source": "camera_segmentation",
                        }
                    )
            return records

        def detect(image) -> tuple[dict, dict, int]:
            """Every candidate's detections on one rendered image, and how many boxes carried no bbox."""

            recorded = {}
            latency = {}
            unmeasured = 0
            for candidate_id in CANDIDATE_IDS:
                began = time.perf_counter()
                result = models[candidate_id].predict(
                    image,
                    conf=RECORDING_MIN_CONFIDENCE,
                    iou=RECORDING_TRACKING_IOU,
                    device=device,
                    verbose=False,
                )
                latency[candidate_id] = (time.perf_counter() - began) * 1000.0
                recorded[candidate_id] = _boxes(result[0])
                unmeasured += sum(
                    1
                    for box in recorded[candidate_id]
                    if not (_finite(box["w"]) and _finite(box["h"]))
                )
            return recorded, latency, unmeasured

        # the frozen val images of both domains: the split the gate itself verifies and measures
        for domain in DOMAINS:
            dataset_root = roots[domain]
            width, height = image_size(
                head_manifest if domain == "head" else task_manifest, domain=domain
            )
            for sample in plan["domains"][domain]["val_samples"]:
                truth_document = json.loads(
                    (dataset_root / sample["truth"]).read_text(encoding="utf-8")
                )
                truth = truth_from_instances(
                    truth_document.get("instances") or (), width=width, height=height
                )
                recorded, latency, unmeasured = detect(str(dataset_root / sample["image"]))
                predictions += len(CANDIDATE_IDS)
                without_geometry += unmeasured
                frames.append(
                    static_frame(
                        domain=domain,
                        camera_name=plan["domains"][domain]["camera_name"],
                        sample={
                            **sample,
                            "neck_rad": truth_document.get("camera", {}).get("neck_rad"),
                        },
                        truth=truth,
                        detections=recorded,
                        latency_ms=latency,
                        match_radius_px=plan["match_radius_px"],
                    )
                )

        # the calibration episodes: one scene per declared seed, the recorder's own scenario assignment
        for episode in plan["domains"]["head"]["calibration_episodes"]:
            renderer._prepare(
                np.random.default_rng(int(episode["seed"])),
                DatasetScenario.for_cup_count(int(episode["cup_count"])),
            )
            for angle in episode["neck_angles_rad"]:
                renderer._data.qpos[address] = float(angle)
                mujoco.mj_forward(renderer._model, renderer._data)
                for domain in DOMAINS:
                    truth = episode_truth(segmentation(cameras[domain]))
                    renderer._renderer.update_scene(renderer._data, camera=cameras[domain])
                    image = np.array(renderer._renderer.render(), copy=True)
                    # the renderer yields RGB and Ultralytics reads a numpy source as BGR, exactly as
                    # `YoloSegDetector._predict` converts the production frame before predicting
                    recorded, latency, unmeasured = detect(np.ascontiguousarray(image[:, :, ::-1]))
                    predictions += len(CANDIDATE_IDS)
                    without_geometry += unmeasured
                    frames.append(
                        episode_frame(
                            domain=domain,
                            camera_name=plan["domains"][domain]["camera_name"],
                            seed=int(episode["seed"]),
                            neck_rad=float(angle),
                            scenario=episode["scenario"],
                            split="calibration",
                            truth=truth,
                            detections=recorded,
                            latency_ms=latency,
                            match_radius_px=plan["match_radius_px"],
                        )
                    )
    finally:
        renderer.close()

    # the gate's own measurement of every val cell, at the candidate's declared point, for reference only
    for domain in DOMAINS:
        dataset_root = roots[domain]
        samples = verified[domain]
        for candidate in plan["candidates"]:
            candidate_id = candidate["candidate_id"]
            point = candidate["operating_points"].get(domain)
            if point is None:
                continue
            scratch = output / "static-reference" / f"{candidate_id}-{domain}"
            scratch.mkdir(parents=True, exist_ok=True)
            working = os.getcwd()
            try:
                # Ultralytics writes its run directory into the working directory
                os.chdir(scratch)
                measured = _measure_static(
                    weights_paths[candidate_id],
                    dataset_root,
                    samples,
                    point,
                    device,
                    scratch,
                    document=frozen_documents[candidate_id],
                )
            finally:
                os.chdir(working)
            static_reference[f"{candidate_id}-{domain}"] = {
                "candidate_id": candidate_id,
                "domain": domain,
                "split": plan["val_split"],
                "declared_point": dict(point),
                "sample_count": len(samples),
                "metrics": {key: float(value) for key, value in measured.items()},
                "consumed_for_selection": False,
                "note": (
                    "the gate's own validator at the candidate's declared point; its mask metrics are a "
                    "different measurement from the frame-level centre-matched cells phase 3 selects on, "
                    "so it is a reference and never part of the choice"
                ),
            }

    provenance = {
        "geometry_seal_path": str(geometry_path),
        "geometry_seal_sha256": _digest_of(geometry_path),
        "head_dataset_manifest_path": str(head_manifest_path),
        "head_dataset_manifest_sha256": _digest_of(head_manifest_path),
        "task_dataset_manifest_path": str(task_manifest_path),
        "task_dataset_manifest_sha256": _digest_of(task_manifest_path),
        "dataset_config_path": str(config_path),
        "dataset_config_sha256": _digest_of(config_path),
        "production_search_config_path": str(production_path),
        "production_search_config_sha256": _digest_of(production_path),
        "episode_partitions_path": str(partitions_path),
        "episode_partitions_sha256": _digest_of(partitions_path),
        "selection_rule_path": str(rule_paths["head"]),
        "selection_rule_sha256": _digest_of(rule_paths["head"]),
        "task_selection_rule_path": str(rule_paths["task"]),
        "task_selection_rule_sha256": _digest_of(rule_paths["task"]),
        "weights": {
            name: {"path": str(path), "sha256": weights_digests[name]}
            for name, path in sorted(weights_paths.items())
        },
        "frozen_candidates": {
            candidate_id: {"path": str(path), "sha256": _digest_of(path)}
            for candidate_id, path in sorted(frozen_paths.items())
        },
        "toolchain": toolchain_identity(so101_demo.__file__),
        "mujoco_only": True,
        "ros_nodes_started": False,
        "motion_commanded": False,
    }
    document_path = output / DOCUMENT_NAME
    document = operating_point_measurement_document(
        plan=plan,
        frames=frames,
        rules=rules,
        static_reference=static_reference,
        provenance=provenance,
        path=document_path,
    )

    chosen: dict[str, dict] = {}
    phase3_paths: dict[str, dict] = {}
    for domain in DOMAINS:
        chosen[domain] = {}
        phase3_paths[domain] = {}
        for candidate in plan["candidates"]:
            candidate_id = candidate["candidate_id"]
            target = output / f"phase3-selection-{domain}-{candidate_id}.json"
            selection = validate_head_search_calibration_operating_point(
                rule=rules[domain],
                measurements=frames,
                candidate_id=candidate_id,
                held_out_measurements=(),
                output_path=target,
            )
            phase3_paths[domain][candidate_id] = str(target)
            chosen[domain][candidate_id] = {
                "min_confidence": selection["chosen_point"]["min_confidence"],
                "tracking_iou": selection["chosen_point"]["tracking_iou"],
                "min_bbox_aspect": selection["chosen_point"]["min_bbox_aspect"],
                "min_area_px2": selection["chosen_point"]["min_area_px2"],
                "chosen_index": selection["chosen_index"],
                "ties_broken_by": selection["ties_broken_by"],
                "no_cup_false_candidates": selection["no_cup_guard"]["no_cup_false_candidates"],
                "no_cup_frames_checked": selection["no_cup_guard"]["frames_checked"],
                "measurements_consumed": selection["measurements_consumed"],
                "document_path": str(target),
            }

    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": RECEIPT_KIND,
        "phase": PHASE,
        "status": "MEASURED",
        "command": command,
        "selection_splits": list(SELECTION_SPLITS),
        "held_out_split": HELD_OUT_SPLIT,
        "grid_point_count": len(plan["grid"]),
        "grid_sha256": plan["grid_sha256"],
        "plan_sha256": plan["plan_sha256"],
        "candidate_count": len(plan["candidates"]),
        "frame_count": len(frames),
        "val_frame_count": sum(1 for frame in frames if frame["split"] == VAL_SPLIT),
        "episode_frame_count": sum(1 for frame in frames if frame["split"] == "calibration"),
        "detector_predictions": predictions,
        "detections_without_geometry": without_geometry,
        "recording": dict(plan["recording"]),
        "chosen": chosen,
        "phase3_documents": phase3_paths,
        "static_reference": static_reference,
        "document_path": str(document_path),
        "document_sha256": document["sha256"],
        "elapsed_s": time.time() - started,
        "runtime_identity": runtime_identity(
            weights=weights_paths[CANDIDATE_IDS[0]],
            weights_sha256=weights_digests[CANDIDATE_IDS[0]],
            output_dir=output,
            device=device,
        ),
        "provenance": provenance,
        "motion_commanded": False,
    }
    (output / RECEIPT_NAME).write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"document": document, "receipt": receipt, "plan": plan, "rules": rules}
