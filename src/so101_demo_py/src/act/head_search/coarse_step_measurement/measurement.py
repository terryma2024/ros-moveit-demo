"""Plan and run the coarse step validation sweep."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time

from so101_demo.act.head_search.calibration_geometry import (
    generate_coarse_step_candidates,
)
from so101_demo.act.head_search.coarse_step_measurement.contracts import (
    _SHA256,
    CAL_SWEEP_EVIDENCE_CONTRADICTORY,
    CAL_SWEEP_EVIDENCE_MISSING,
    CAL_SWEEP_EVIDENCE_PARTIAL,
    DOMAIN,
    KIND,
    MATCH_RADIUS_PX,
    PHASE,
    RECONSTRUCTION_PIXEL_TOLERANCE,
    SCHEMA_VERSION,
    SPLIT,
    STOP_TOLERANCE_RAD,
    _finite,
    _mapping,
    _records,
    _refuse,
)
from so101_demo.act.head_search.coarse_step_measurement.sweep import sweep_plan
from so101_demo.act.head_search.coarse_step_measurement.verdicts import (
    load_selected_candidate,
    validate_head_search_coarse_step_measurement,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256


def plan_coarse_step_val_sweep(
    *,
    geometry_seal,
    dataset_manifest,
    frozen_candidate,
    weights_sha256,
    split=SPLIT,
    domain=DOMAIN,
    scene_limit=None,
    match_radius_px=MATCH_RADIUS_PX,
) -> dict:
    """Plan the real sweep: the val scenes, the operating point and the bounded plan per candidate.

    Pure and detector-free, so the plan can be checked without a GPU: it verifies that the weights really
    are the frozen candidate's own bytes, that the manifest is the sealed head dataset's, that the split
    holds measurable scenes, that the frozen candidate carries the domain's operating point, and it lays
    out every generated candidate's bounded plan per anchor. The heavy producer then renders exactly these
    scenes at exactly these stops.
    """

    from so101_demo.act.head_search.calibration_geometry import read_geometry_document

    seal = read_geometry_document(geometry_seal)
    manifest = _mapping("the dataset manifest", dataset_manifest)
    frozen = _mapping("the frozen candidate", frozen_candidate)
    if type(weights_sha256) is not str or _SHA256.fullmatch(weights_sha256) is None:
        raise ValueError("the weights digest must be a sha256 digest")
    frozen_digest = frozen.get("weight_sha256")
    if frozen_digest != weights_sha256:
        raise _refuse(
            CAL_SWEEP_EVIDENCE_CONTRADICTORY,
            f"the weights digest to measure is {weights_sha256} but the frozen candidate records "
            f"{frozen_digest!r}; the val sweep must measure the selected model's own bytes",
        )
    seal_digest = geometry_seal.get("seal_sha256")
    if manifest.get("geometry_seal_sha256") != seal_digest:
        raise _refuse(
            CAL_SWEEP_EVIDENCE_CONTRADICTORY,
            f"the dataset manifest was generated under the seal {manifest.get('geometry_seal_sha256')!r}, "
            f"not the sealed geometry's own {seal_digest!r}",
        )
    if manifest.get("camera_name") != geometry_seal.get("camera_name"):
        raise _refuse(
            CAL_SWEEP_EVIDENCE_CONTRADICTORY,
            f"the dataset manifest renders {manifest.get('camera_name')!r} but the seal names "
            f"{geometry_seal.get('camera_name')!r}",
        )
    points = _mapping("the frozen candidate's operating points", frozen.get("operating_points"))
    point = points.get(domain)
    if not isinstance(point, Mapping):
        raise _refuse(
            CAL_SWEEP_EVIDENCE_PARTIAL,
            f"the frozen candidate declares no {domain!r} operating point, so the sweep has no "
            f"confidence floor to measure at",
        )
    tracker = point.get("tracker")
    min_confidence = point.get("min_confidence")
    tracking_iou = tracker.get("iou") if isinstance(tracker, Mapping) else None
    if not (_finite(min_confidence) and _finite(tracking_iou)):
        raise _refuse(
            CAL_SWEEP_EVIDENCE_PARTIAL,
            f"the frozen candidate's {domain!r} operating point declares no finite min_confidence and "
            f"tracker.iou",
        )
    scenes = []
    for sample in _records("samples", manifest.get("samples", ())):
        if sample.get("split") != split:
            continue
        seed = sample.get("seed")
        scenario = sample.get("scenario")
        camera = sample.get("camera")
        if type(seed) is not int or isinstance(seed, bool):
            raise ValueError(f"every {split} sample declares an integer seed")
        if type(scenario) is not str or not scenario:
            raise ValueError(f"the {split} sample {seed} declares no scenario")
        neck = camera.get("neck_rad") if isinstance(camera, Mapping) else None
        if not _finite(neck):
            raise ValueError(f"the {split} sample {seed} declares no finite camera neck_rad")
        visible = sample.get("visible_instance_count")
        if type(visible) is not int or isinstance(visible, bool) or visible < 0:
            raise ValueError(f"the {split} sample {seed} declares no visible_instance_count")
        scenes.append(
            {
                "scene_id": int(seed),
                "scene_group_id": sample.get("scene_group_id"),
                "scenario": scenario,
                "neck_rad": float(neck),
                "visible_instance_count": int(visible),
                "image": sample.get("image"),
            }
        )
    if not scenes:
        raise _refuse(
            CAL_SWEEP_EVIDENCE_MISSING,
            f"the sealed head dataset holds no {split} scene, so there is no val evidence to measure",
        )
    if scene_limit is not None:
        if type(scene_limit) is not int or isinstance(scene_limit, bool) or scene_limit < 1:
            raise ValueError("scene_limit must be a positive integer when it is given")
        scenes = scenes[:scene_limit]
    if not (_finite(match_radius_px) and float(match_radius_px) >= 0.0):
        raise ValueError("match_radius_px must be finite and non-negative")
    candidates = generate_coarse_step_candidates(
        seal["horizontal_fov_rad"],
        sealed_candidate_rad=seal.get("sealed_coarse_step_candidate_rad"),
    )
    return {
        "geometry": seal,
        "scenes": scenes,
        "scene_limit": scene_limit,
        "candidates": [
            {"coarse_step_rad": float(step), **sweep_plan(coarse_step_rad=step, geometry=seal)}
            for step in candidates
        ],
        "model": {
            "candidate_id": frozen.get("candidate_id"),
            "weights_sha256": weights_sha256,
            "min_confidence": float(min_confidence),
            "tracking_iou": float(tracking_iou),
        },
        "split": split,
        "domain": domain,
        "match_radius_px": float(match_radius_px),
    }


def _unique_stops(candidates: Sequence[Mapping]) -> list[float]:
    """Every stop angle the candidates command, once, in a stable order."""

    angles: list[float] = []
    for candidate in candidates:
        for anchor in candidate["anchors"]:
            for target in anchor["targets_rad"]:
                if not any(
                    math.isclose(target, known, rel_tol=0.0, abs_tol=STOP_TOLERANCE_RAD)
                    for known in angles
                ):
                    angles.append(float(target))
    return angles


def _cached(cache: Mapping[float, Mapping], angle: float) -> Mapping:
    for known, record in cache.items():
        if math.isclose(float(angle), float(known), rel_tol=0.0, abs_tol=STOP_TOLERANCE_RAD):
            return record
    raise ValueError(f"the stop {angle} was never measured")


def measure_coarse_step_val_sweep(
    *,
    geometry_seal_path,
    dataset_manifest_path,
    dataset_config_path,
    weights_path,
    frozen_candidate_path,
    output_dir,
    split=SPLIT,
    domain=DOMAIN,
    scene_limit=None,
    passes=1,
    device="cuda",
    command=None,
) -> dict:
    """Measure the real val sweep and write the raw observations and the decision.

    This is the only measuring code in the calibration: it rebuilds every head val scene the way the
    dataset generator did (the accepted deterministic attempt, checked against the dataset's own image),
    walks the bounded stop points of every generated candidate step with the selected model's operating
    point, and records the per-camera ground truth and the detections of every stop. It commands no
    motion: the neck angle is a simulated scene state, not a controller target. The caller's brand-new
    output directory is claimed before anything is measured, and the three documents are written into it
    only once the whole sweep succeeded: the raw observations, the decision, and the receipt that records
    what ran and what it consumed.
    """

    import mujoco
    import numpy as np
    from ultralytics import YOLO

    from so101_demo.act.head_search.calibration_geometry import read_geometry_document

    started = time.time()
    geometry_path = Path(geometry_seal_path)
    manifest_path = Path(dataset_manifest_path)
    config_path = Path(dataset_config_path)
    weights = Path(weights_path)
    output = Path(output_dir)
    for path in (geometry_path, manifest_path, config_path, weights):
        if not path.is_file():
            raise FileNotFoundError(f"the sweep needs {path}")
    try:
        output.mkdir(parents=True)
    except FileExistsError as error:
        raise _refuse(
            CAL_SWEEP_EVIDENCE_CONTRADICTORY,
            f"{output} exists; a measurement is never resumed, continued or overwritten",
        ) from error

    seal_document = json.loads(geometry_path.read_text(encoding="utf-8"))
    read_geometry_document(seal_document)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frozen_document = load_selected_candidate(frozen_candidate_path)
    weights_digest = hashlib.sha256(weights.read_bytes()).hexdigest()

    from so101_demo.adapters.perception.mujoco_dataset.config import load_dataset_config
    from so101_demo.adapters.perception.mujoco_dataset.models import DatasetScenario
    from so101_demo.adapters.perception.mujoco_dataset.renderer import MuJoCoDatasetRenderer
    from so101_demo.adapters.perception.mujoco_dataset.verify import verify_head_search_manifest

    config = load_dataset_config(
        config_path,
        generator_commit=manifest.get("generator_commit"),
        sample_limit=None,
    )
    counted = dict(config.split_counts)
    verify_head_search_manifest(
        manifest,
        dataset_root=manifest_path.parent,
        geometry_seal=seal_document,
        expected_train=counted["train"],
        expected_val=counted["val"],
        expected_test=counted["test"],
    )
    plan = plan_coarse_step_val_sweep(
        geometry_seal=seal_document,
        dataset_manifest=manifest,
        frozen_candidate=frozen_document,
        weights_sha256=weights_digest,
        split=split,
        domain=domain,
        scene_limit=scene_limit,
    )
    samples = {
        int(sample["seed"]): sample
        for sample in manifest["samples"]
        if sample.get("split") == split
    }
    candidates = plan["candidates"]
    angles = _unique_stops(candidates)
    camera_name = seal_document.get("camera_name")
    renderer = MuJoCoDatasetRenderer(config)
    try:
        neck = mujoco.mj_name2id(renderer._model, mujoco.mjtObj.mjOBJ_JOINT, "neck_yaw_joint")
        if neck < 0:
            raise _refuse(
                CAL_SWEEP_EVIDENCE_CONTRADICTORY,
                "the sealed scene has no neck_yaw_joint, so no bounded stop can be measured",
            )
        address = int(renderer._model.jnt_qposadr[neck])
        camera = mujoco.mj_name2id(renderer._model, mujoco.mjtObj.mjOBJ_CAMERA, camera_name)
        if camera < 0:
            raise _refuse(
                CAL_SWEEP_EVIDENCE_CONTRADICTORY,
                f"the sealed scene has no camera {camera_name!r}",
            )
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

        def segmentation() -> np.ndarray:
            segmentation_renderer = renderer._segmentation_renderer
            segmentation_renderer.enable_segmentation_rendering()
            try:
                segmentation_renderer.update_scene(renderer._data, camera=camera)
                return renderer._geom_ids(np.array(segmentation_renderer.render(), copy=True))
            finally:
                segmentation_renderer.disable_segmentation_rendering()

        def truth_of(segmentation_image) -> list[dict]:
            records = []
            for body in cup_bodies:
                ys, xs = np.nonzero(np.isin(segmentation_image, geoms_of_body[body]))
                if xs.size:
                    records.append(
                        {
                            "body": body_name[body],
                            "body_id": int(body),
                            "x": float(xs.mean()),
                            "y": float(ys.mean()),
                            "visible_px": int(xs.size),
                        }
                    )
            return records

        model = YOLO(str(weights))
        min_confidence = plan["model"]["min_confidence"]
        tracking_iou = plan["model"]["tracking_iou"]
        measured: dict[int, dict] = {}
        reconstructions = []
        predictions = 0
        for scene in plan["scenes"]:
            sample = samples[scene["scene_id"]]
            renderer.render(int(scene["scene_id"]), DatasetScenario(scene["scenario"]))
            if renderer._neck_rad != scene["neck_rad"]:
                raise _refuse(
                    CAL_SWEEP_EVIDENCE_CONTRADICTORY,
                    f"the val scene {scene['scene_id']} reconstructs at the neck angle "
                    f"{renderer._neck_rad!r} but the dataset rendered it at {scene['neck_rad']!r}; the "
                    f"sweep would measure a scene the dataset never held",
                )
            renderer._data.qpos[address] = float(scene["neck_rad"])
            mujoco.mj_forward(renderer._model, renderer._data)
            renderer._renderer.update_scene(renderer._data, camera=camera)
            reference = np.array(renderer._renderer.render(), copy=True)
            difference = _image_difference(reference, manifest_path.parent / sample["image"])
            reconstructions.append(
                {"scene_id": scene["scene_id"], "max_abs_pixel_difference": difference}
            )
            if difference is None or difference > RECONSTRUCTION_PIXEL_TOLERANCE:
                raise _refuse(
                    CAL_SWEEP_EVIDENCE_CONTRADICTORY,
                    f"the val scene {scene['scene_id']} does not reconstruct to the dataset's own image "
                    f"(max abs pixel difference {difference!r} > {RECONSTRUCTION_PIXEL_TOLERANCE}); the "
                    f"sweep would measure a scene the dataset does not hold",
                )
            per_pass = []
            for _index in range(passes):
                cache: dict[float, dict] = {}
                for angle in angles:
                    renderer._data.qpos[address] = float(angle)
                    mujoco.mj_forward(renderer._model, renderer._data)
                    truth = truth_of(segmentation())
                    renderer._renderer.update_scene(renderer._data, camera=camera)
                    image = np.array(renderer._renderer.render(), copy=True)
                    result = model.predict(
                        image,
                        conf=float(min_confidence),
                        iou=float(tracking_iou),
                        device=device,
                        verbose=False,
                    )
                    predictions += 1
                    boxes = getattr(result[0], "boxes", None)
                    cache[float(angle)] = {
                        "truth": truth,
                        "detections": [
                            {
                                "x": float(box.xywh[0][0]),
                                "y": float(box.xywh[0][1]),
                                "conf": float(box.conf),
                            }
                            for box in (boxes if boxes is not None else [])
                        ],
                        "image_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
                    }
                per_pass.append(cache)
            measured[int(scene["scene_id"])] = {
                "declared_visible_instances": int(scene["visible_instance_count"]),
                "passes": per_pass,
            }
    finally:
        renderer.close()

    raw_candidates = []
    for candidate in candidates:
        if not candidate["covers_required_domain"]:
            raw_candidates.append(
                {
                    "coarse_step_rad": candidate["coarse_step_rad"],
                    "anchors": [],
                    "scenes": [],
                }
            )
            continue
        scenes = []
        for scene in plan["scenes"]:
            record = measured[scene["scene_id"]]
            scene_passes = []
            for index, cache in enumerate(record["passes"]):
                stops = []
                for anchor in candidate["anchors"]:
                    for stop_index, target in enumerate(anchor["targets_rad"]):
                        outcome = _cached(cache, target)
                        stops.append(
                            {
                                "anchor": anchor["anchor"],
                                "stop_index": stop_index,
                                "stop_rad": float(target),
                                "truth": outcome["truth"],
                                "detections": outcome["detections"],
                                "image_sha256": outcome["image_sha256"],
                            }
                        )
                scene_passes.append({"pass_index": index, "stops": stops})
            scenes.append(
                {
                    "scene_id": scene["scene_id"],
                    "scene_group_id": scene["scene_group_id"],
                    "scenario": scene["scenario"],
                    "dataset_visible_instances": record["declared_visible_instances"],
                    "passes": scene_passes,
                }
            )
        raw_candidates.append(
            {
                "coarse_step_rad": candidate["coarse_step_rad"],
                "anchors": [
                    {
                        "anchor": anchor["anchor"],
                        "anchor_rad": anchor["anchor_rad"],
                        "targets_rad": list(anchor["targets_rad"]),
                    }
                    for anchor in candidate["anchors"]
                ],
                "scenes": scenes,
            }
        )
    differences = [record["max_abs_pixel_difference"] for record in reconstructions]
    raw_document = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "phase": PHASE,
        "domain": domain,
        "split": split,
        "match_radius_px": plan["match_radius_px"],
        "passes": passes,
        "geometry": {
            "path": str(geometry_path),
            "sha256": hashlib.sha256(geometry_path.read_bytes()).hexdigest(),
            "seal_sha256": seal_document.get("seal_sha256"),
            "horizontal_fov_rad": plan["geometry"]["horizontal_fov_rad"],
            "lock_valid_neck_rad": list(plan["geometry"]["lock_valid_neck_rad"]),
            "required_search_domain_rad": list(
                plan["geometry"]["required_search_domain_rad"]
            ),
            "anchors_rad": dict(plan["geometry"]["anchors_rad"]),
        },
        "model": {
            "candidate_id": frozen_document.get("candidate_id"),
            "frozen_candidate_path": str(Path(frozen_candidate_path)),
            "frozen_candidate_sha256": hashlib.sha256(
                Path(frozen_candidate_path).read_bytes()
            ).hexdigest(),
            "weights_path": str(weights),
            "weights_sha256": weights_digest,
            "min_confidence": plan["model"]["min_confidence"],
            "tracking_iou": plan["model"]["tracking_iou"],
        },
        "dataset": {
            "manifest_path": str(manifest_path),
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "generator_commit": manifest.get("generator_commit"),
            "geometry_seal_sha256": manifest.get("geometry_seal_sha256"),
            "camera_name": manifest.get("camera_name"),
            "split": split,
            "scene_count": len(plan["scenes"]),
            "scene_limit": plan["scene_limit"],
            "scene_ids": [scene["scene_id"] for scene in plan["scenes"]],
            "scenes_verified_against_the_dataset_images": len(reconstructions),
            "max_abs_pixel_difference": max(differences) if differences else None,
            "reconstruction_pixel_tolerance": RECONSTRUCTION_PIXEL_TOLERANCE,
        },
        "candidates": raw_candidates,
        "path": str(output / "coarse-step-observations.json"),
    }
    raw_document["sha256"] = canonical_sha256(
        {key: value for key, value in raw_document.items() if key != "sha256"}
    )
    raw_path = output / "coarse-step-observations.json"
    raw_path.write_text(json.dumps(raw_document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    decision = validate_head_search_coarse_step_measurement(
        geometry=plan["geometry"],
        observations=raw_document,
        selected_weights_sha256=weights_digest,
        output_path=output / "coarse-step-measurement.json",
    )
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": "head_search_coarse_step_measurement_receipt",
        "phase": PHASE,
        "status": "SUCCEEDED",
        "command": command,
        "split": split,
        "domain": domain,
        "scene_count": len(plan["scenes"]),
        "scene_limit": plan["scene_limit"],
        "candidate_count": len(candidates),
        "stop_angles": len(angles),
        "passes": passes,
        "detector_predictions": predictions,
        "scenes_verified_against_the_dataset_images": len(reconstructions),
        "max_abs_pixel_difference": max(differences) if differences else None,
        "chosen_coarse_step_rad": decision["chosen_coarse_step_rad"],
        "observations_path": str(raw_path),
        "observations_sha256": raw_document["sha256"],
        "measurement_path": str(output / "coarse-step-measurement.json"),
        "elapsed_s": time.time() - started,
        "runtime_identity": runtime_identity(
            weights=weights, weights_sha256=weights_digest, output_dir=output, device=device
        ),
        "motion_commanded": False,
    }
    (output / "measurement-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"observations": raw_document, "measurement": decision, "receipt": receipt}


def _image_difference(rendered, image_path) -> int | None:
    """The largest per-channel difference between a rendered frame and the dataset's own image."""

    import cv2
    import numpy as np

    path = Path(image_path)
    if not path.is_file():
        return None
    stored = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if stored is None:
        return None
    stored = cv2.cvtColor(stored, cv2.COLOR_BGR2RGB)
    if stored.shape != rendered.shape:
        return None
    return int(np.abs(rendered.astype(int) - stored.astype(int)).max())


def runtime_identity(*, weights, weights_sha256, output_dir, device) -> dict:
    """What the measurement ran as: versions, module path and the weights it measured."""

    import mujoco
    import torch
    import ultralytics

    import so101_demo

    properties = None
    if torch.cuda.is_available():
        properties = torch.cuda.get_device_properties(0)
    return {
        "python_executable": sys.executable,
        "so101_demo_module_path": str(Path(so101_demo.__file__).resolve()),
        "mujoco_version": mujoco.__version__,
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "driver_version": _driver_version(),
        "gpu_name": properties.name if properties is not None else None,
        "ultralytics_version": ultralytics.__version__,
        "device": device,
        "weights_path": str(weights),
        "weights_sha256": weights_sha256,
        "output_dir": str(output_dir),
        "mujoco_only": True,
        "ros_nodes_started": False,
        "motion_commanded": False,
    }


def parse_driver_version(text: str) -> str | None:
    """The NVIDIA driver version out of `/proc/driver/nvidia/version`, or None when it names none.

    The kernel module line reads `NVRM version: NVIDIA UNIX Open Kernel Module for x86_64  595.84
    Release Build ...` on this host, so the version is the first dotted number after the `NVRM version:`
    label; the older `Kernel Module  <version>` spelling is read too. A file that names no version leaves
    the identity field None rather than inventing one.
    """

    for pattern in (
        r"NVRM version:.*?\b(\d+\.\d+(?:\.\d+)?)\b",
        r"Kernel Module\s+(\d+\.\d+(?:\.\d+)?)",
    ):
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def _driver_version() -> str | None:
    """The NVIDIA kernel module version, read from the host; None when it cannot be read."""

    path = Path("/proc/driver/nvidia/version")
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return parse_driver_version(text)
