"""Fixtures and helpers shared by the Head search calibration command tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from so101_demo.perception_benchmark.contracts import canonical_sha256

#: the synthetic run's sealed controlled dependencies, one real file each
RUN_SEALED_CONTENTS = {
    "dataset_manifest": b'{"kind": "head_search_dataset", "scenes": 40}\n',
    "model_manifest": b'{"kind": "head_search_model", "candidate": "C"}\n',
    "scenario_partitions": b'{"kind": "scenario_partitions", "val": 12, "test": 12}\n',
    "production_config": b'{"kind": "head_search_v2", "values": {}}\n',
    "camera_config": b'{"kind": "head_camera", "width_px": 640, "height_px": 480}\n',
}


RUN_GEOMETRY_BODY = {
    "schema_version": 1,
    "kind": "head_camera_geometry",
    "horizontal_fov_rad": 0.4,
    "lock_valid_neck_rad": [-2.0, 2.0],
    "required_search_domain_rad": [-0.35, 0.35],
    "coarse_step_candidate_rad": 0.15,
    "anchors": ["default"],
    "in_frame_matrix": {"default": {"neck_start_rad": 0.0}},
}


RUN_PLAN_SHA = "a" * 64


RUN_SELECTION_SPLITS = ("val", "calibration")


RUN_HELD_OUT_SPLITS = ("held_out_evaluation",)


RUN_HIGH_POINT = {
    "min_confidence": 0.1 + 0.2,
    "tracking_iou": 0.6,
    "min_bbox_aspect": 1.25,
    "min_area_px2": 100.0,
}


RUN_LOW_POINT = {
    "min_confidence": 0.25,
    "tracking_iou": 0.5,
    "min_bbox_aspect": 1.0,
    "min_area_px2": 64.0,
}


RUN_WEIGHT_SHA256 = canonical_sha256({"seed": "candidate-C-weights"})


RUN_MEASUREMENTS = (
    {
        "split": "val",
        "domain": "head",
        "seed": 0,
        "scenario": "nominal",
        "truth": [{"x": 100, "y": 100}],
        "detections": {"C": [{"x": 100.2, "y": 100.2, "conf": 0.90}]},
        "match_radius_px": 8.0,
    },
    {
        "split": "calibration",
        "domain": "head",
        "seed": 1,
        "scenario": "nominal",
        "truth": [{"x": 400, "y": 400}],
        "detections": {"C": [{"x": 400.4, "y": 400.4, "conf": 0.85}]},
        "match_radius_px": 8.0,
    },
)


def _write_json(path: Path, document) -> Path:
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _sealed(body: dict) -> dict:
    """One document sealed the way the campaign sealed its geometry: canonical digest of the body."""

    sealed = {key: value for key, value in body.items() if key != "seal_sha256"}
    return {**sealed, "seal_sha256": canonical_sha256(sealed)}


def _run_arguments(
    tmp_path: Path,
    *,
    bounded: bool = True,
    seal: str | None = None,
    omit: tuple[str, ...] = (),
) -> list[str]:
    """A complete synthetic argument set for `run`, with every declared input written under tmp_path.

    The sealed documents, the search configuration the entry preconditions read, the admission, the
    phase-3 rule and measurements, the frozen candidate, the bundle inputs and the phase-6/phase-7
    measurement documents are all real files produced by the repository's own writers or declared as
    plainly as the phases read them; no detector, GPU or simulator is involved, because what this
    exercises is the CLI's parsing, validation and orchestration. `omit` drops a flag and its value, so
    a test can show what a run that fails to declare one of its inputs does.
    """

    from so101_demo.act.head_search.candidate_freeze import freeze_candidate
    from so101_demo.act.head_search.operating_point import record_selection_rule

    declared = {}
    for name, payload in RUN_SEALED_CONTENTS.items():
        path = tmp_path / f"{name}.json"
        path.write_bytes(payload)
        declared[name] = {"path": str(path), "sha256": hashlib.sha256(payload).hexdigest()}
    geometry_path = _write_json(tmp_path / "geometry-seal.json", _sealed(RUN_GEOMETRY_BODY))
    declared["geometry_seal"] = {
        "path": str(geometry_path),
        "sha256": _digest(geometry_path),
    }

    search_config = {
        "attempt_id": "attempt-1",
        "session_id": "session-1",
        "search_start_rad": 0.0,
        "horizontal_fov_rad": 0.4,
        "coarse_step_rad": 0.15,
        "search_timeout_s": 12.0,
        "max_age_s": 0.15,
        "max_skew_s": 0.05,
        "settle_velocity_rad_s": 0.05,
        "goal_tolerance_rad": 0.05,
        "center_deadband_px": 18.0,
        "vertical_bounds_px": [110.0, 370.0],
        "min_area_px2": 64.0,
        "min_confidence": 0.4,
        "max_fine_corrections": 4,
        "max_fine_total_rad": 0.4,
        "frame_id": "head_camera_frame",
        "ray_origin_frame_id": "head_camera_frame",
    }
    if bounded:
        search_config["required_search_domain_rad"] = list(
            RUN_GEOMETRY_BODY["required_search_domain_rad"]
        )
        search_config["lock_valid_neck_rad"] = list(RUN_GEOMETRY_BODY["lock_valid_neck_rad"])
    search_path = _write_json(tmp_path / "production-search-config.json", search_config)

    admission_path = _write_json(
        tmp_path / "admission.json",
        {
            "generation": "g1",
            "status": "CALIBRATION_REQUIRED",
            "measurement_plan_sha256": RUN_PLAN_SHA,
            "safe_interval_rad": list(RUN_GEOMETRY_BODY["lock_valid_neck_rad"]),
            "controller_generation": "ctrl-1",
            "broker_generation": "g1",
        },
    )
    rule = record_selection_rule(
        points=(RUN_LOW_POINT, RUN_HIGH_POINT),
        selection_splits=RUN_SELECTION_SPLITS,
        held_out_splits=RUN_HELD_OUT_SPLITS,
        domain="head",
    )
    rule_path = _write_json(tmp_path / "selection-rule.json", rule)
    measurements_path = _write_json(tmp_path / "measurements.json", list(RUN_MEASUREMENTS))
    frozen_path = tmp_path / "frozen-C.json"
    freeze_candidate(
        candidate_id="C",
        weight_sha256=RUN_WEIGHT_SHA256,
        min_confidence=RUN_HIGH_POINT["min_confidence"],
        tracking_iou=RUN_HIGH_POINT["tracking_iou"],
        output=frozen_path,
    )
    task_dataset = _write_json(tmp_path / "task-dataset.json", {"kind": "task_dataset"})
    bundle_inputs = _write_json(
        tmp_path / "bundle-inputs.json",
        {
            "runtime_identity": {
                "package_prefix": "/toolchain/install/so101_demo_py",
                "console_script_path": "/toolchain/install/so101_head_search_calibration",
                "detector_weights_sha256": RUN_WEIGHT_SHA256,
                "torch_version": "2.5.1",
                "ultralytics_version": "8.3.0",
                "cuda_version": "12.4",
                "driver_version": "550.54.14",
                "mujoco_version": "3.2.3",
                "camera_id": "head-cam-0",
                "camera_intrinsics_sha256": canonical_sha256({"seed": "intrinsics"}),
                "tracker_id": "iou-tracker-v1",
                "web_bundle_id": "web-20260930",
            },
            "also_recorded": {},
            "parameter_evidence": {"perception_operating_point": {"parameters": {}}},
        },
    )

    arguments = [
        "run",
        "--run-root",
        str(tmp_path / "run"),
        "--dataset",
        declared["dataset_manifest"]["path"],
        "--candidate",
        declared["model_manifest"]["path"],
        "--geometry-seal",
        str(geometry_path),
        "--episode-partitions",
        declared["scenario_partitions"]["path"],
        "--production-config",
        declared["production_config"]["path"],
        "--camera-config",
        declared["camera_config"]["path"],
        "--production-search-config",
        str(search_path),
        "--admission",
        str(admission_path),
        "--selection-rule",
        str(rule_path),
        "--operating-point-measurements",
        str(measurements_path),
        "--candidate-id",
        "C",
        "--frozen-candidate",
        str(frozen_path),
        "--task-dataset",
        str(task_dataset),
        "--bundle-inputs",
        str(bundle_inputs),
    ]
    # the phase-6 and phase-7 measurement documents this run declares. The synthetic candidate set
    # makes the frozen-candidate gate refuse before either phase reads its measurements, so what these
    # files have to be here is what the CLI validates: a declared input that exists. The phases that
    # consume them are covered, with their own measurement documents, by their own tests.
    measurements = {
        "--search-timing": (
            "search-timing.json",
            {"p99_settle_s": 0.5, "p99_frame_s": 0.1, "control_period_s": 0.05},
        ),
        "--camera-measurements": (
            "camera-measurements.json",
            {
                "horizontal_fov_rad": 0.4,
                "image_width_px": 640,
                "image_height_px": 480,
                "safety_margin_px": 10.0,
                "centre_jitter_rad": 0.002,
            },
        ),
        "--deadband-candidates": (
            "deadband-candidates.json",
            [
                {
                    "center_deadband_px": 18.0,
                    "longest_locked_run_frames": 3,
                    "direction_reversals": 0,
                }
            ],
        ),
        "--workspace-projection": (
            "workspace-projection.json",
            {"top_px": 110.0, "bottom_px": 370.0},
        ),
        "--coarse-step-observations": (
            "coarse-step-observations.json",
            {
                "schema_version": 1,
                "kind": "head_search_coarse_step_val_sweep",
                "phase": "coarse_step_measurement",
                "domain": "head",
                "split": "val",
                "match_radius_px": 8.0,
                "passes": 1,
                "geometry": {
                    "path": str(geometry_path),
                    "sha256": _digest(geometry_path),
                    "seal_sha256": canonical_sha256(RUN_GEOMETRY_BODY),
                    "horizontal_fov_rad": RUN_GEOMETRY_BODY["horizontal_fov_rad"],
                    "lock_valid_neck_rad": list(RUN_GEOMETRY_BODY["lock_valid_neck_rad"]),
                    "required_search_domain_rad": list(
                        RUN_GEOMETRY_BODY["required_search_domain_rad"]
                    ),
                    "anchors_rad": {"default": 0.0},
                },
                "model": {
                    "candidate_id": "C",
                    "weights_sha256": RUN_WEIGHT_SHA256,
                    "min_confidence": RUN_HIGH_POINT["min_confidence"],
                    "tracking_iou": RUN_HIGH_POINT["tracking_iou"],
                },
                "dataset": {
                    "manifest_path": declared["dataset_manifest"]["path"],
                    "manifest_sha256": declared["dataset_manifest"]["sha256"],
                    "split": "val",
                    "scene_count": 2,
                    "scene_limit": None,
                },
                "candidates": [],
                "path": str(tmp_path / "coarse-step-observations.json"),
            },
        ),
        "--fine-correction-episodes": (
            "fine-correction-episodes.json",
            [
                {
                    "split": "held_out_evaluation",
                    "episode_id": "episode-1",
                    "succeeded": True,
                    "fine_corrections": 1,
                    "fine_corrections_rad": [0.01],
                }
            ],
        ),
        "--frame-age-measurements": (
            "frame-age.json",
            {"samples": [{"received_monotonic_s": 0.0, "decision_monotonic_s": 0.02}]},
        ),
        "--skew-measurements": (
            "skew.json",
            {"clock_resolution_s": 0.001, "samples": [{"stamps": [0.0, 0.005, 0.008]}]},
        ),
        "--frame-contract": ("frame-contract.json", {"frame_rate_hz": 10.0}),
        "--controller-submissions": (
            "controller-submissions.json",
            {
                "samples": [
                    {
                        "time_base": "simulation",
                        "submit_snapshot_sim_s": 1.0,
                        "first_target_sim_s": 1.02,
                    }
                ]
            },
        ),
        "--mujoco-measurements": ("mujoco.json", {"simulation_timestep_s": 0.002}),
        "--stationary-measurements": (
            "stationary.json",
            {"samples": [{"velocity_rad_s": [0.0, 0.001]}]},
        ),
        "--feedback-measurements": (
            "feedback.json",
            {"quantisation_rad": 0.0001, "period_s": 0.01},
        ),
        "--controller-stop-config": (
            "controller-stop-config.json",
            {"stopped_tolerance_rad_s": 0.01},
        ),
        "--stop-proofs": (
            "stop-proofs.json",
            {
                "samples": [
                    {
                        "stop_request_monotonic_s": 0.0,
                        "third_confirming_receive_monotonic_s": 0.02,
                    }
                ]
            },
        ),
    }
    for flag, (name, document) in measurements.items():
        arguments.append(flag)
        arguments.append(str(_write_json(tmp_path / name, document)))

    if seal is not None:
        sealed = {name: dict(record) for name, record in declared.items()}
        if seal == "broken":
            sealed["camera_config"]["sha256"] = "0" * 64
        arguments += ["--seal", str(_write_json(tmp_path / "seal.json", sealed))]
    return _without(arguments, omit)


def _without(arguments: list[str], flags: tuple[str, ...]) -> list[str]:
    """The same argument list without the named flags and their single values."""

    remaining: list[str] = []
    index = 0
    while index < len(arguments):
        if arguments[index] in flags:
            index += 2
            continue
        remaining.append(arguments[index])
        index += 1
    return remaining


def _digest(path: Path) -> str:
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


TIMING_CONTROLLERS = """controller_manager:
  ros__parameters:
    update_rate: 500
"""


#: the sealed scene stand-in of the deadband entry: the same yaw hinge and head camera, plus the cup the
#: anchor places. The trials themselves are handed to a declared plant and detector in these tests, so no
#: detector, GPU, renderer or ROS is needed to exercise the entry end to end
DEADBAND_SCENE = """<mujoco model="deadband-fixture">
  <option timestep="0.002" gravity="0 0 -9.81" integrator="implicitfast"/>
  <worldbody>
    <body name="cup">
      <joint name="cup_free_joint" type="free"/>
      <geom name="cup_geom" type="cylinder" size="0.04 0.045"/>
    </body>
    <body name="head_mount">
      <joint name="neck_yaw_joint" type="hinge" axis="0 0 1" damping="0.05" armature="0.001"/>
      <geom name="head_geom" type="box" size="0.05 0.05 0.05"/>
      <camera name="head_camera" pos="0 0 0.05" fovy="60" xyaxes="1 0 0 0 1 0"/>
    </body>
  </worldbody>
  <actuator>
    <position name="neck_yaw_joint" joint="neck_yaw_joint" kp="8" kv="0.6"
              forcelimited="false" ctrllimited="false"/>
  </actuator>
</mujoco>
"""


def _deadband_inputs(tmp_path: Path) -> dict:
    """The six declared inputs of the lock-trial measurement, with one sealed anchor."""

    scene = tmp_path / "head_search_scene.xml"
    scene.write_text(DEADBAND_SCENE, encoding="utf-8")
    scene_sha256 = hashlib.sha256(scene.read_bytes()).hexdigest()
    seal = tmp_path / "head-camera-geometry.json"
    seal.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "camera_name": "head_camera",
                "camera": {
                    "camera_name": "head_camera",
                    "parent_body": "head_mount",
                    "width": 640,
                    "height": 480,
                    "fovy_rad": 1.0471975511965976,
                },
                "image_width": 640,
                "image_height": 480,
                "horizontal_fov_rad": 1.3121067481206794,
                "required_search_domain_rad": [-0.17559216195018026, 0.08047101126546086],
                "lock_valid_neck_rad": [-6.283175307179587, 6.283175307179587],
                "in_frame_matrix": {"left": {"neck_start_rad": 0.0}},
                "workspace_matrix": {
                    "key_samples": [
                        {"anchor": "left", "kind": "anchor", "point_m": [-0.08, -0.28, 0.165]}
                    ]
                },
                "source_digests": {"scene_sha256": scene_sha256},
            }
        ),
        encoding="utf-8",
    )
    weights = tmp_path / "C.pt"
    weights.write_bytes(b"selected-model")
    production = tmp_path / "head_search_runtime.json"
    production.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "runtime_id": "head-search-runtime",
                "weight_path": "models/head-search/yolo11n-seg-best.pt",
                "weight_sha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
                "camera": {
                    "name": "head_camera",
                    "frame_id": "head_camera_frame",
                    "ray_origin_frame_id": "head_camera_frame",
                },
                "motion": {"settle_velocity_rad_s": 0.05, "goal_tolerance_rad": 0.05},
                "tracker": {"name": "bytetrack", "iou_threshold": 0.3},
                "values": {
                    "coarse_step_rad": 0.3,
                    "horizontal_fov_rad": 1.3121067481206794,
                    "lock_valid_neck_rad": [-6.283175307179587, 6.283175307179587],
                    "max_age_s": 0.05,
                    "max_skew_s": 0.02,
                    "search_timeout_s": 12.0,
                    "center_deadband_px": 18.0,
                    "vertical_bounds_px": [110.0, 370.0],
                    "min_area_px2": 64.0,
                    "min_confidence": 0.4,
                    "tracking_iou": 0.3,
                    "max_fine_corrections": 4,
                    "max_fine_total_rad": 0.4,
                    "min_bbox_aspect": 0.5,
                },
            }
        ),
        encoding="utf-8",
    )
    frozen = tmp_path / "frozen-c.json"
    frozen.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "head-search-frozen-candidate",
                "candidate_id": "C",
                "weight_sha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
                "operating_points": {
                    "head": {"min_confidence": 0.25, "tracker": {"iou": 0.5}},
                    "task": {"min_confidence": 0.25, "tracker": {"iou": 0.5}},
                },
            }
        ),
        encoding="utf-8",
    )
    controllers = tmp_path / "ros2_controllers.yaml"
    controllers.write_text(TIMING_CONTROLLERS, encoding="utf-8")
    return {
        "scene": scene,
        "seal": seal,
        "production": production,
        "controllers": controllers,
        "weights": weights,
        "frozen": frozen,
    }


#: the held-out seeds this entry's fixture declares, with the recorder's own condition-class convention
#: (`record_episodes7.py:40`): positions 0 and 1 are `nominal`, so both seeds prepare a one-cup scene
FINE_CORRECTION_PARTITIONS = {
    "schema_version": 1,
    "document": "head-search-scenario-partitions/v1",
    "condition_classes": [
        "nominal",
        "left_anchor",
        "two_cups",
        "no_cup",
    ],
    "anchors": ["default", "left", "forward"],
    "calibration": [700000, 700001],
    "held_out_evaluation": [800000, 800001],
}


def _fine_correction_inputs(tmp_path: Path) -> dict:
    """The eight declared inputs of the episode measurement: the deadband fixture plus two."""

    inputs = _deadband_inputs(tmp_path)
    dataset_config = tmp_path / "head_camera_yolo_seg.yaml"
    dataset_config.write_text(
        f"mjcf_path: {inputs['scene'].name}\ncamera_name: head_camera\n"
        f"image_width: 640\nimage_height: 480\n",
        encoding="utf-8",
    )
    partitions = tmp_path / "head-search-scenario-partitions.json"
    partitions.write_text(json.dumps(FINE_CORRECTION_PARTITIONS), encoding="utf-8")
    inputs["dataset_config"] = dataset_config
    inputs["partitions"] = partitions
    return inputs


def _restart_inputs(tmp_path: Path) -> dict:
    """The declared inputs of `measure-restarts`: the fine-correction fixture plus the rest."""

    inputs = _fine_correction_inputs(tmp_path)
    final_run = tmp_path / "head-toolchain"
    final_run.mkdir()
    inputs["final_run"] = final_run
    seal = json.loads(Path(inputs["seal"]).read_text(encoding="utf-8"))
    seal["in_frame_matrix"] = {
        "default": {"neck_start_rad": 0.1, "centre_angle_rad": 0.23109066719589708},
        "left": {"neck_start_rad": 0.0, "centre_angle_rad": -0.0587558227157227},
        "forward": {"neck_start_rad": 0.0, "centre_angle_rad": 0.18822150530477078},
    }
    seal["workspace_matrix"] = {
        "key_samples": [
            {"kind": "anchor", "anchor": "default", "point_m": [0.02, -0.28, 0.165]},
            {"kind": "anchor", "anchor": "left", "point_m": [-0.08, -0.28, 0.165]},
            {"kind": "anchor", "anchor": "forward", "point_m": [0.02, -0.36, 0.165]},
        ]
    }
    Path(inputs["seal"]).write_text(json.dumps(seal), encoding="utf-8")
    urdf = tmp_path / "so101.urdf"
    urdf.write_text("<robot/>", encoding="utf-8")
    inputs["urdf"] = urdf
    inputs["plugins"] = inputs["controllers"]
    inputs["workdir"] = tmp_path / "workdir"
    inputs["workdir"].mkdir()
    inputs["ownership"] = tmp_path / "exclusive-ownership.json"
    inputs["ownership"].write_text(
        json.dumps(
            {
                "operation": "QUALIFICATION_OWNERSHIP_CHECK",
                "status": "EXCLUSIVE_OWNERSHIP_OK",
                "refusals": [],
                "planned_run_root": str(tmp_path / "restart-run"),
            }
        ),
        encoding="utf-8",
    )
    return inputs
