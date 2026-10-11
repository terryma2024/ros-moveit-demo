"""The formal head search calibration CLI: check-ownership, run, measure-coarse-step, measure-mujoco, measure-search-timing, measure-deadband-candidates, measure-camera, measure-workspace-projection, measure-selection-rule, measure-operating-point, measure-scenarios, measure-restarts, verify-promoted-config, qualify.

The CLI parses arguments, validates the inputs a run declares and orchestrates nothing itself: `run`
hands the phases to `so101_demo.act.head_search_calibration_run`, where the order, the entry binding, the
trajectory precondition and the run status live (plan rule 4). `check-ownership` is the
stack-free ownership gate: it reads the process table, ROS graph, GPU processes, tmux panes and evidence root,
refuses any second owner by name, binds the frozen runtime identity, writes its receipt into a brand-new
root and starts nothing (`so101_demo.act.head_search_ownership`). Every subcommand refuses a run root that
already exists, so there is no way to resume or continue a stage. `measure-coarse-step`,
`measure-mujoco`, `measure-search-timing`, `measure-deadband-candidates`, `measure-camera` and
`measure-workspace-projection` are the measurement flights the run cannot take itself - the run declares
documents, it does not render, read a sealed model, step a simulator, project a workspace or close a
control loop - so they are their own installed entries, validated
here and produced by `so101_demo.act.head_search_coarse_step_measurement`,
`so101_demo.act.head_search_mujoco_measurements`,
`so101_demo.act.head_search_timing_measurement`,
`so101_demo.act.head_search_deadband_measurement`,
`so101_demo.act.head_search_camera_measurement` and
`so101_demo.act.head_search_workspace_projection`. `measure-selection-rule` and
`measure-operating-point` are phase 3's two inputs: the first writes the rule record before any
measurement can exist, the second measures the frames that rule consumes and has the installed phase 3
select every candidate's point (`so101_demo.act.head_search_operating_point_measurement`).
`measure-scenarios` is the scenario flight: it runs the declared qualification seeds one at a time through the producer controller's closed loop, journals every outcome - including the ones that fail or refuse - and writes the aggregate that claims no verdict. `measure-admission` produces the run's `--admission` from the six sealed inputs the run declares - the
flat measurement plan the installed controller is constructed with, the six-field
`CalibrationMeasurementAdmission` for `role=calibration`, and the receipt that records every refusal the
runtime contract fixes - and `measure-bundle-inputs` produces the declared geometry and perception
parameter blocks with the live effective-value readback
(`so101_demo.act.head_search_calibration_admission_document`,
`so101_demo.act.head_search_calibration_bundle_inputs`), and `measure-episode-records` reshapes the
installed phase-3 measurement document into the per-seed contract phase 4's gate declares
(`so101_demo.act.head_search_episode_records`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from so101_demo.act import head_search_ownership as ownership
from so101_demo.act.head_search_ownership import process_ancestry
from so101_demo.act.head_search_qualification import (
    HEAD_SEARCH_QUALIFIED,
    qualification_parser,
    qualify_head_search,
)

if TYPE_CHECKING:  # pragma: no cover - the run module is imported where it is used
    from so101_demo.act.head_search_calibration_run import CalibrationPhaseInputs

#: a run whose declared inputs are missing or unreadable is refused before any phase, by name
HEAD_SEARCH_RUN_INPUTS_INCOMPLETE = "HEAD_SEARCH_RUN_INPUTS_INCOMPLETE"

#: a measurement flight whose inputs are missing or unreadable is refused before it renders anything
HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE = "HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE"

#: the measurement documents phases 6 and 7 consume (plan section 2 rows 6 and 7), each with the flag it
#: is declared under and its shape: `document` is one JSON object the phase cites by path and sha256,
#: `records` is the JSON list of measured records the phase itself builds its evidence from. The raw
#: coarse-step val sweep is the fifteenth: the run never measures it, it declares the sweep the installed
#: `measure-coarse-step` entry produced with the selected model. The run reads these files and never
#: invents a measurement; a run that omits one is refused at this entry.
RUN_PHASE_SIX_MEASUREMENTS = (
    ("search_timing", "--search-timing", "document"),
    ("camera_measurements", "--camera-measurements", "document"),
    ("deadband_candidates", "--deadband-candidates", "records"),
    ("workspace_projection", "--workspace-projection", "document"),
    ("fine_correction_episodes", "--fine-correction-episodes", "records"),
    ("coarse_step_observations", "--coarse-step-observations", "document"),
)
RUN_PHASE_SEVEN_MEASUREMENTS = (
    ("frame_age_measurements", "--frame-age-measurements", "document"),
    ("skew_measurements", "--skew-measurements", "document"),
    ("frame_contract", "--frame-contract", "document"),
    ("controller_submissions", "--controller-submissions", "document"),
    ("mujoco_measurements", "--mujoco-measurements", "document"),
    ("stationary_measurements", "--stationary-measurements", "document"),
    ("feedback_measurements", "--feedback-measurements", "document"),
    ("controller_stop_config", "--controller-stop-config", "document"),
    ("stop_proofs", "--stop-proofs", "document"),
)
RUN_PHASE_MEASUREMENTS = RUN_PHASE_SIX_MEASUREMENTS + RUN_PHASE_SEVEN_MEASUREMENTS

#: the six sealed controlled dependencies of plan section 2b, and the flag each is declared with
RUN_SEALED_INPUT_FLAGS = (
    ("dataset_manifest", "dataset", "--dataset"),
    ("model_manifest", "candidate", "--candidate"),
    ("geometry_seal", "geometry_seal", "--geometry-seal"),
    ("scenario_partitions", "episode_partitions", "--episode-partitions"),
    ("production_config", "production_config", "--production-config"),
    ("camera_config", "camera_config", "--camera-config"),
)

#: the flags a run cannot start without; each is validated before the run root is claimed
RUN_REQUIRED_FLAGS = (
    ("run_root", "--run-root"),
    ("dataset", "--dataset"),
    ("candidate", "--candidate"),
    ("geometry_seal", "--geometry-seal"),
    ("episode_partitions", "--episode-partitions"),
    ("production_config", "--production-config"),
    ("camera_config", "--camera-config"),
    ("production_search_config", "--production-search-config"),
    ("admission", "--admission"),
    ("selection_rule", "--selection-rule"),
    ("operating_point_measurements", "--operating-point-measurements"),
    ("candidate_id", "--candidate-id"),
    ("frozen_candidate", "--frozen-candidate"),
    ("task_dataset", "--task-dataset"),
    ("bundle_inputs", "--bundle-inputs"),
) + tuple((name, flag) for name, flag, _shape in RUN_PHASE_MEASUREMENTS)

#: the required flags that name a file that must already exist; `--run-root` must not, and a candidate
#: id is a name rather than a path
RUN_REQUIRED_FILE_FLAGS = (
    "dataset",
    "candidate",
    "geometry_seal",
    "episode_partitions",
    "production_config",
    "camera_config",
    "production_search_config",
    "admission",
    "selection_rule",
    "operating_point_measurements",
    "frozen_candidate",
    "task_dataset",
    "bundle_inputs",
) + tuple(name for name, _flag, _shape in RUN_PHASE_MEASUREMENTS)

#: the optional flags that name a file, and the ones that name an existing directory. The gate of phase 4
#: reads `--episode-records` as the directory of per-seed documents its own loader globs, so it is a
#: directory here too: a file of that name never held an episode recording
RUN_OPTIONAL_FILE_FLAGS = ("seal", "held_out_measurements")
RUN_OPTIONAL_DIRECTORY_FLAGS = (
    "evidence_root",
    "weights_dir",
    "head_dataset_root",
    "task_dataset_root",
    "episode_records",
)

#: the two `measure-selection-rule` inputs: the sealed production search configuration the grid and the
#: two fixed geometric values come from, the directory the measurement will own (which must not exist
#: yet - a rule written after its measurement is exactly what the ordering forbids) and the brand-new
#: directory the rule records own
SELECTION_RULE_REQUIRED_FLAGS = (
    ("production_search_config", "--production-search-config"),
    ("measurements_output_dir", "--measurements-output-dir"),
    ("output_dir", "--output-dir"),
)

#: the `measure-operating-point` inputs: the sealed geometry (its camera and required search domain),
#: the two sealed datasets, the dataset profile, the sealed production configuration (the grid and the
#: two fixed geometric values), the sealed partitions, the two rule records written before this
#: measurement, the three frozen candidates, the directory their `<candidate>.pt` weights live in and the
#: brand-new directory the measurement owns
OPERATING_POINT_REQUIRED_FILE_FLAGS = (
    ("geometry_seal", "--geometry-seal"),
    ("head_dataset", "--head-dataset"),
    ("task_dataset", "--task-dataset"),
    ("dataset_config", "--dataset-config"),
    ("production_search_config", "--production-search-config"),
    ("episode_partitions", "--episode-partitions"),
    ("selection_rule", "--selection-rule"),
    ("task_selection_rule", "--task-selection-rule"),
    ("frozen_candidate", "--frozen-candidate"),
)
OPERATING_POINT_REQUIRED_DIRECTORY_FLAGS = (("weights_dir", "--weights-dir"),)

#: the `measure-coarse-step` entry: the sealed geometry, the sealed head dataset and its profile, the
#: selected model's weights and frozen candidate, and the brand-new directory the measurement owns
MEASUREMENT_REQUIRED_FLAGS = (
    ("geometry_seal", "--geometry-seal"),
    ("head_dataset", "--head-dataset"),
    ("dataset_config", "--dataset-config"),
    ("weights", "--weights"),
    ("frozen_candidate", "--frozen-candidate"),
    ("output_dir", "--output-dir"),
)

#: the `measure-mujoco` entry: the sealed scene, at least one sealed document that pins its bytes, and
#: the brand-new directory the document owns. `--mujoco-readback` is optional: it loads the scene in
#: MuJoCo and records `model.opt.timestep` next to the declaration
MUJOCO_REQUIRED_FLAGS = (
    ("scene", "--scene"),
    ("output_dir", "--output-dir"),
)
MUJOCO_IDENTITY_FLAGS = (
    ("geometry_seal", "--geometry-seal"),
    ("dataset_manifest", "--dataset-manifest"),
    ("geometry_contract", "--geometry-contract"),
)

#: the `measure-workspace-projection` entry: the sealed scene whose camera pose every projected pose is
#: read from, the sealed geometry whose workspace matrix, required domain and mount model the projection
#: is checked against, the geometry contract that declares the workspace box, and the brand-new directory
#: the document owns. No detector, no weights, no controller and no renderer take part: the legal pick
#: workspace is geometry, and the projection is arithmetic over it
WORKSPACE_PROJECTION_REQUIRED_FLAGS = (
    ("scene", "--scene"),
    ("geometry_seal", "--geometry-seal"),
    ("geometry_contract", "--geometry-contract"),
    ("output_dir", "--output-dir"),
)

#: the `measure-search-timing` entry: the sealed scene the sweep steps the neck in, the sealed geometry
#: the controller plan and the sweep's thresholds come from, the production search configuration, the
#: sealed controller period and the brand-new directory the documents own. `--weights` is optional: with
#: it the sweep times its frames with the sealed detector, without it no frame age is invented
TIMING_REQUIRED_FLAGS = (
    ("scene", "--scene"),
    ("geometry_seal", "--geometry-seal"),
    ("production_search_config", "--production-search-config"),
    ("controller_config", "--controller-config"),
    ("output_dir", "--output-dir"),
)
TIMING_OPTIONAL_FILE_FLAGS = (("weights", "--weights"),)

#: the `measure-admission` entry: the six sealed inputs the run itself declares, the brand-new run root
#: whose name is the generation, and the brand-new directory the plan, the admission and the receipt own.
#: `--seal` is optional, exactly as it is for `run`: the seal is either declared or computed here
ADMISSION_REQUIRED_FLAGS = (
    ("dataset", "--dataset"),
    ("candidate", "--candidate"),
    ("geometry_seal", "--geometry-seal"),
    ("episode_partitions", "--episode-partitions"),
    ("production_config", "--production-config"),
    ("camera_config", "--camera-config"),
    ("run_root", "--run-root"),
    ("output_dir", "--output-dir"),
)
#: the required flags that name a file that must already exist; the run root and the output directory
#: must not exist, which is what makes the generation new and the documents unwritten
ADMISSION_REQUIRED_FILE_FLAGS = (
    "dataset",
    "candidate",
    "geometry_seal",
    "episode_partitions",
    "production_config",
    "camera_config",
)
ADMISSION_OPTIONAL_FILE_FLAGS = (("seal", "--seal"),)

#: the `measure-bundle-inputs` entry: the sealed geometry the two geometry values come from, the
#: production configuration the values and the controller's motion tolerances are read from, the phase-3
#: selection document, the frozen candidate document, the selected model's weights and the brand-new
#: directory the declared document and its receipt own. `--operating-point-measurements` is optional: it
#: is the frame-level measurement the selection was made on, cited as input evidence when it is declared
BUNDLE_INPUTS_REQUIRED_FLAGS = (
    ("geometry_seal", "--geometry-seal"),
    ("production_config", "--production-config"),
    ("operating_point", "--operating-point"),
    ("frozen_candidate", "--frozen-candidate"),
    ("weights", "--weights"),
    ("output_dir", "--output-dir"),
)
BUNDLE_INPUTS_REQUIRED_FILE_FLAGS = (
    "geometry_seal",
    "production_config",
    "operating_point",
    "frozen_candidate",
    "weights",
)
BUNDLE_INPUTS_OPTIONAL_FILE_FLAGS = (
    ("operating_point_measurements", "--operating-point-measurements"),
)

#: the `measure-episode-records` entry: the installed phase-3 measurement document whose calibration
#: frames are the episodes, the sealed partitions that declare which seeds the split holds, and the
#: brand-new directory the gate's `--episode-records` points at
EPISODE_RECORDS_REQUIRED_FLAGS = (
    ("operating_point_measurements", "--operating-point-measurements"),
    ("episode_partitions", "--episode-partitions"),
    ("output_dir", "--output-dir"),
)
EPISODE_RECORDS_REQUIRED_FILE_FLAGS = ("operating_point_measurements", "episode_partitions")


#: the `measure-deadband-candidates` entry: the sealed scene the lock trials step the neck in, the sealed
#: geometry the controller plan, the motion corridor and the anchor cup placements come from, the
#: production search configuration, the sealed controller period, the selected candidate's frozen
#: document, the selected model's weights and the brand-new directory the documents own. At least one
#: `--candidate` has to be declared: the trials measure the candidates the run declares, never a default
DEADBAND_REQUIRED_FLAGS = (
    ("scene", "--scene"),
    ("geometry_seal", "--geometry-seal"),
    ("production_search_config", "--production-search-config"),
    ("controller_config", "--controller-config"),
    ("frozen_candidate", "--frozen-candidate"),
    ("weights", "--weights"),
    ("output_dir", "--output-dir"),
)
DEADBAND_CANDIDATE_FLAG = ("candidate", "--candidate")


#: the `measure-fine-correction-episodes` entry: the sealed scene the episodes step the neck in, the sealed
#: geometry whose corridors and camera the episodes are checked against, the production search
#: configuration (whose declared fine-correction bounds are the production values, not this flight's
#: instrument budget), the sealed controller period, the selected candidate's frozen document, the selected
#: model's weights, the head dataset profile whose own renderer prepares each held-out seed's scene, the
#: scenario partitions that declare which seeds are held out, and the brand-new directory the documents own
FINE_CORRECTION_REQUIRED_FLAGS = (
    ("scene", "--scene"),
    ("geometry_seal", "--geometry-seal"),
    ("production_search_config", "--production-search-config"),
    ("controller_config", "--controller-config"),
    ("frozen_candidate", "--frozen-candidate"),
    ("weights", "--weights"),
    ("dataset_config", "--dataset-config"),
    ("scenario_partitions", "--scenario-partitions"),
    ("output_dir", "--output-dir"),
)


#: the `measure-scenarios` entry: the nine declared inputs of the qualification scenarios. The scene, the
#: seal, the production configuration, the controller configuration, the frozen candidate, the selected
#: weights, the dataset profile and the tracked partitions are the sealed inputs the closed loop closes
#: over; `--evidence-root` is the registered campaign root the ownership gate checks, and `--final-run` is
#: the frozen runtime of record whose identity the run must hold.
SCENARIO_REQUIRED_FLAGS = (
    ("scene", "--scene"),
    ("geometry_seal", "--geometry-seal"),
    ("production_search_config", "--production-search-config"),
    ("controller_config", "--controller-config"),
    ("frozen_candidate", "--frozen-candidate"),
    ("weights", "--weights"),
    ("dataset_config", "--dataset-config"),
    ("scenario_partitions", "--scenario-partitions"),
    ("output_dir", "--output-dir"),
    ("evidence_root", "--evidence-root"),
)


#: the `measure-restarts` entry: the three independent FULL_RESTART anchor phases. The owner
#: presents Step 1's own receipt, the frozen runtime of record, the promoted configuration and bundle, and
#: the sealed inputs the production composition is started from; `--run-root` is the brand-new campaign
#: root whose three anchor directories hold the receipts, and `--workdir` is scratch. The neck's dead-man
#: directory is the one the sealed `--controller-config` declares.
RESTART_REQUIRED_FLAGS = (
    ("ownership_receipt", "--ownership-receipt"),
    ("run_root", "--run-root"),
    ("final_run", "--final-run"),
    ("production_config", "--production-config"),
    ("approved_bundle", "--approved-bundle"),
    ("geometry_seal", "--geometry-seal"),
    ("scene", "--scene"),
    ("urdf", "--urdf"),
    ("plugin_config", "--plugin-config"),
    ("controller_config", "--controller-config"),
    ("weights", "--weights"),
    ("frozen_candidate", "--frozen-candidate"),
    ("workdir", "--workdir"),
)


def _restart_parser() -> argparse.ArgumentParser:
    """The `measure-restarts` entry: one restart per declared anchor, each with its own teardown proof."""

    from so101_demo.act.head_search_restarts import ANCHORS as RESTART_ANCHORS

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-restarts",
        description=(
            "Run exactly one independent FULL_RESTART per anchor (default, left, forward): take the Step 1 "
            "ownership receipt, start the one production composition, prove its graph, camera rate, "
            "simulation clock and one CUDA detector, run one bounded anchor search through the production "
            "transport, prove the stop, then stop the stack and prove it is gone before the next anchor"
        ),
    )
    parser.add_argument("--run-root", type=Path, help="the brand-new run root the three receipts own")
    parser.add_argument(
        "--ownership-receipt", type=Path, help="Step 1's exclusive-ownership receipt for this run root"
    )
    parser.add_argument("--final-run", type=Path, help="the frozen runtime of record")
    parser.add_argument("--production-config", type=Path, help="the promoted production search config")
    parser.add_argument("--approved-bundle", type=Path, help="the approved calibration bundle")
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument("--scene", type=Path, help="the sealed MuJoCo scene the stack steps")
    parser.add_argument("--urdf", type=Path, help="the ACT URDF the stack's robot description is built from")
    parser.add_argument("--plugin-config", type=Path, help="the production MuJoCo plugin configuration")
    parser.add_argument("--controller-config", type=Path, help="the sealed controller configuration")
    parser.add_argument("--weights", type=Path, help="the selected model's weights file")
    parser.add_argument("--frozen-candidate", type=Path, help="the selected frozen candidate document")
    parser.add_argument("--workdir", type=Path, help="the scratch directory the phase writes into")
    parser.add_argument("--device", default="cuda", help="the detector device (never a CPU fallback)")
    parser.add_argument(
        "--anchors",
        default=",".join(RESTART_ANCHORS),
        help="the anchors to run, in order; the plan fixes default,left,forward",
    )
    parser.add_argument(
        "--max-settle-s", type=float, default=None, help="the per-stop settle budget of the cadence check"
    )
    parser.add_argument(
        "--expected-source-commit", help="the frozen runtime's source commit the identity must match"
    )
    parser.add_argument(
        "--expected-production-config-sha256", help="the promoted config digest the identity must match"
    )
    parser.add_argument("--expected-values-sha256", help="the 17 values' digest the identity must match")
    parser.add_argument(
        "--expected-weights-sha256", help="the detector weights digest the identity must match"
    )
    parser.add_argument(
        "--expected-package-prefix", help="the `ros2 pkg prefix so101_demo_py` the gate must observe"
    )
    return parser


def _measure_restarts(arguments: list[str]) -> int:
    """Validate the declared inputs, then hand the three anchor restarts to the library."""

    parsed = _restart_parser().parse_args(arguments)
    missing = [flag for name, flag in RESTART_REQUIRED_FLAGS if getattr(parsed, name) is None]
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a restart declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    # the run root is the one declared input that must NOT exist, and the scratch directory is created by
    # the phase itself: everything else is a sealed input the caller has to present
    absent = [
        str(getattr(parsed, name))
        for name, _flag in RESTART_REQUIRED_FLAGS
        if name not in ("run_root", "workdir") and not Path(getattr(parsed, name)).exists()
    ]
    if absent:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2
    if parsed.run_root.exists():
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.run_root} exists; a qualification run "
            f"is never resumed, continued or overwritten",
            file=sys.stderr,
        )
        return 2
    anchors = [name for name in str(parsed.anchors).split(",") if name]

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_restarts import (
        read_runtime_of_record,
        run_anchor_restart,
        write_head_search_restarts,
    )

    production = json.loads(parsed.production_config.read_text(encoding="utf-8"))
    values = production.get("values") if isinstance(production.get("values"), Mapping) else {}
    if not values:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.production_config} declares no values "
            f"block",
            file=sys.stderr,
        )
        return 2
    seal = json.loads(parsed.geometry_seal.read_text(encoding="utf-8"))
    try:
        runtime = read_runtime_of_record(parsed.final_run, parsed.production_config)
        expected: dict = {}
        for key, attribute in (
            ("source_commit", "expected_source_commit"),
            ("production_config_sha256", "expected_production_config_sha256"),
            ("values_sha256", "expected_values_sha256"),
            ("weight_sha256_declared", "expected_weights_sha256"),
        ):
            value = getattr(parsed, attribute)
            if value:
                expected[key] = value
        for key, wanted in sorted(expected.items()):
            if runtime.get(key) != wanted:
                raise CalibrationInputsRefused(
                    "RESTART_RUNTIME_UNVERIFIED",
                    f"{key}: the run declares {wanted!r} and the frozen runtime reads "
                    f"{runtime.get(key)!r}",
                )
        result = write_head_search_restarts(
            run_root=parsed.run_root,
            ownership_receipt=parsed.ownership_receipt,
            runtime=runtime,
            approved_bundle_sha256=hashlib.sha256(parsed.approved_bundle.read_bytes()).hexdigest(),
            seal=seal,
            workdir=parsed.workdir,
            values=values,
            anchors=anchors,
            producer={
                "entry": "so101_head_search_calibration measure-restarts",
                "argv_sha256": hashlib.sha256(
                    " ".join(_command_line(arguments, subcommand="measure-restarts").split()).encode()
                ).hexdigest(),
                "command": _command_line(arguments, subcommand="measure-restarts"),
            },
            run_anchor=lambda **kwargs: run_anchor_restart(
                urdf_path=parsed.urdf,
                scene_path=parsed.scene,
                plugin_config_path=parsed.plugin_config,
                controller_config_path=parsed.controller_config,
                production_config_path=parsed.production_config,
                weights_path=parsed.weights,
                frozen_candidate_path=parsed.frozen_candidate,
                values=values,
                seal=seal,
                production=production,
                device=parsed.device,
                excluded_pids=process_ancestry(),
                **kwargs,
            ),
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    for anchor in result["aggregate"]["anchors"]:
        document = result["documents"][anchor]
        print(
            f"restart_{anchor}: status={document['status']} gates={json.dumps(document['gates'], sort_keys=True)} "
            f"elapsed_s={document.get('elapsed_s')} receipt={result['receipts'][anchor]}"
        )
    print(
        f"HEAD_SEARCH_RESTARTS_MEASURED anchors={','.join(result['aggregate']['anchors'])} "
        f"status={result['aggregate']['status']} run_root={result['run_root']}"
    )
    return 0 if result["aggregate"]["status"] == "PASS" else 2


#: the `measure-camera` entry: the sealed scene the frames are rendered in, the sealed geometry whose
#: field of view and image size are the declared camera, the production search configuration, the sealed
#: controller period, the selected candidate's frozen document, the selected model's weights and the
#: brand-new directory the documents own. `--safety-margin-declaration` is optional: it names the artefact
#: that declares `image_safety_margin_fraction` (the approved production form, the fraction of the shorter
#: production image edge this producer derives into pixels with `ceil`) or `safety_margin_px` directly, and
#: without it that field is written as null and refused rather than defaulted
CAMERA_REQUIRED_FLAGS = (
    ("scene", "--scene"),
    ("geometry_seal", "--geometry-seal"),
    ("production_search_config", "--production-search-config"),
    ("controller_config", "--controller-config"),
    ("frozen_candidate", "--frozen-candidate"),
    ("weights", "--weights"),
    ("output_dir", "--output-dir"),
)
CAMERA_OPTIONAL_FILE_FLAGS = (("safety_margin_declaration", "--safety-margin-declaration"),)

#: the `measure-controller-stop-config` entry: the controller's own installed declaration, the tree it was
#: built from (which has to declare the same bytes), the sealed controller configuration whose period the
#: declaration's window step is cross-checked against, and the brand-new output directory
STOP_CONFIG_REQUIRED_FLAGS = (
    ("controller_declaration", "--controller-declaration"),
    ("source_declaration", "--source-declaration"),
    ("controller_config", "--controller-config"),
    ("output_dir", "--output-dir"),
)

#: the `measure-feedback` entry: the sealed controller configuration that declares both rates, and the
#: optional artefact that declares the quantisation resolution. Without that artefact the resolution is
#: written as null and refused, exactly like the camera measurement's undeclared safety margin; the
#: retained declaration `config/act/feedback-quantisation-declaration.json` states this platform's
#: explicit zero with its basis (HS-305)
FEEDBACK_REQUIRED_FLAGS = (
    ("controller_config", "--controller-config"),
    ("output_dir", "--output-dir"),
)
FEEDBACK_OPTIONAL_FILE_FLAGS = (("quantisation_declaration", "--quantisation-declaration"),)

#: the three stop flights: the sealed scene they step, the sealed geometry that pins it, the production
#: search configuration whose declared values they read, the sealed controller period, and the output
#: directory. None of them loads a detector or touches a GPU
STOP_FLIGHT_REQUIRED_FLAGS = (
    ("scene", "--scene"),
    ("geometry_seal", "--geometry-seal"),
    ("production_search_config", "--production-search-config"),
    ("controller_config", "--controller-config"),
    ("output_dir", "--output-dir"),
)


def _measurement_parser() -> argparse.ArgumentParser:
    """The `measure-coarse-step` entry: it declares inputs and calls one library function.

    This is the measurement flight the run cannot take itself (the run declares documents, it does not
    render): the installed program rebuilds the sealed head val scenes, walks the bounded stops of every
    generated candidate step with the selected model, and writes the raw observations, the decision and
    the receipt. Nothing is computed here beyond parsing and validating what the caller declared.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-coarse-step",
        description=(
            "Measure the coarse-step val sweep once, into a brand-new output directory, and choose "
            "coarse_step_rad from the head val split"
        ),
    )
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument("--head-dataset", type=Path, help="the sealed head dataset manifest")
    parser.add_argument("--dataset-config", type=Path, help="the dataset profile it was rendered from")
    parser.add_argument("--weights", type=Path, help="the selected model's weights file")
    parser.add_argument("--frozen-candidate", type=Path, help="the selected frozen candidate document")
    parser.add_argument("--output-dir", type=Path, help="the brand-new directory the sweep owns")
    parser.add_argument("--scene-limit", type=int, help="measure only the first N val scenes")
    parser.add_argument("--passes", type=int, default=1, help="independent passes over every stop")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--split", default="val")
    parser.add_argument("--domain", default="head")
    return parser


def _measure_coarse_step(arguments: list[str]) -> int:
    """Validate the declared measurement inputs, then hand the flight to the library module."""

    parsed = _measurement_parser().parse_args(arguments)
    missing = [
        flag for name, flag in MEASUREMENT_REQUIRED_FLAGS if getattr(parsed, name) is None
    ]
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    absent = [
        str(getattr(parsed, name))
        for name, _flag in MEASUREMENT_REQUIRED_FLAGS
        if name != "output_dir" and not Path(getattr(parsed, name)).is_file()
    ]
    if absent:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2
    if parsed.output_dir.exists():
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.output_dir} exists; a measurement is "
            f"never resumed, continued or overwritten",
            file=sys.stderr,
        )
        return 2

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_coarse_step_measurement.measurement import (
        measure_coarse_step_val_sweep,
    )

    try:
        result = measure_coarse_step_val_sweep(
            geometry_seal_path=parsed.geometry_seal,
            dataset_manifest_path=parsed.head_dataset,
            dataset_config_path=parsed.dataset_config,
            weights_path=parsed.weights,
            frozen_candidate_path=parsed.frozen_candidate,
            output_dir=parsed.output_dir,
            split=parsed.split,
            domain=parsed.domain,
            scene_limit=parsed.scene_limit,
            passes=parsed.passes,
            device=parsed.device,
            command=_command_line(arguments, subcommand="measure-coarse-step"),
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    print(
        f"COARSE_STEP_MEASURED {receipt['chosen_coarse_step_rad']} "
        f"scenes={receipt['scene_count']} candidates={receipt['candidate_count']} "
        f"passes={receipt['passes']} output_dir={parsed.output_dir}"
    )
    return 0


def _mujoco_parser() -> argparse.ArgumentParser:
    """The `measure-mujoco` entry: it declares the sealed scene and calls one library function.

    The document phase 7 declares under `--mujoco-measurements` carries one number, the sealed MuJoCo
    model's simulation timestep, which is a declaration of the sealed scene rather than a measurement
    flight. Nothing is computed here beyond parsing and validating what the caller declared.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-mujoco",
        description=(
            "Read the sealed MuJoCo scene's simulation timestep once, into a brand-new output directory, "
            "and write the document the run declares under --mujoco-measurements"
        ),
    )
    parser.add_argument("--scene", type=Path, help="the sealed MuJoCo scene the runtime steps")
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument("--dataset-manifest", type=Path, help="the sealed head dataset manifest")
    parser.add_argument("--geometry-contract", type=Path, help="the sealed geometry contract")
    parser.add_argument("--output-dir", type=Path, help="the brand-new directory the document owns")
    parser.add_argument(
        "--mujoco-readback",
        action="store_true",
        help="load the scene in MuJoCo and record model.opt.timestep next to the declaration",
    )
    return parser


def _measure_mujoco(arguments: list[str]) -> int:
    """Validate the declared scene and its sealed identities, then hand the flight to the library."""

    parsed = _mujoco_parser().parse_args(arguments)
    missing = [flag for name, flag in MUJOCO_REQUIRED_FLAGS if getattr(parsed, name) is None]
    if not missing and all(getattr(parsed, name) is None for name, _flag in MUJOCO_IDENTITY_FLAGS):
        missing = [flag for _name, flag in MUJOCO_IDENTITY_FLAGS]
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    declared = MUJOCO_REQUIRED_FLAGS + MUJOCO_IDENTITY_FLAGS
    absent = [
        str(getattr(parsed, name))
        for name, _flag in declared
        if name != "output_dir" and getattr(parsed, name) is not None
        and not Path(getattr(parsed, name)).is_file()
    ]
    if absent:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2
    if parsed.output_dir.exists():
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.output_dir} exists; a measurement is "
            f"never resumed, continued or overwritten",
            file=sys.stderr,
        )
        return 2

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_mujoco_measurements import write_mujoco_measurements

    try:
        result = write_mujoco_measurements(
            scene_path=parsed.scene,
            geometry_seal_path=parsed.geometry_seal,
            dataset_manifest_path=parsed.dataset_manifest,
            geometry_contract_path=parsed.geometry_contract,
            output_dir=parsed.output_dir,
            mujoco_readback=parsed.mujoco_readback,
            command=_command_line(arguments, subcommand="measure-mujoco"),
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    print(
        f"MUJOCO_TIMESTEP_PRODUCED {receipt['simulation_timestep_s']} "
        f"scene={receipt['scene_path']} readback={receipt['mujoco_readback']} "
        f"output_dir={parsed.output_dir}"
    )
    return 0


def _workspace_projection_parser() -> argparse.ArgumentParser:
    """The `measure-workspace-projection` entry: the sealed scene, the seal and the contract.

    This flight is the one phase 6's `vertical_bounds_px` was missing: the legal pick workspace the
    geometry contract declares, projected into the sealed head camera at the neck poses the bounded search
    actually holds, with the image-space extent per pose and over the pose set. It loads the scene for the
    camera pose alone - no detector, no renderer, no GPU and no controller take part.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-workspace-projection",
        description=(
            "Project the geometry contract's declared legal pick workspace into the sealed head camera at "
            "the bounded plan's in-domain neck poses, into a brand-new output directory, and write the "
            "document the run declares under --workspace-projection"
        ),
    )
    parser.add_argument("--scene", type=Path, help="the sealed MuJoCo scene the camera pose is read from")
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument(
        "--geometry-contract", type=Path, help="the contract that declares the legal pick workspace box"
    )
    parser.add_argument("--output-dir", type=Path, help="the brand-new directory the document owns")
    parser.add_argument(
        "--coarse-step-rad",
        type=float,
        default=None,
        help=(
            "the coarse step the run's own bounded plan was receipted at; without it the step is the one "
            "phase 2's selection rule chooses, and a declared step has to be a generated candidate that "
            "covers the required domain"
        ),
    )
    return parser


def _measure_workspace_projection(arguments: list[str]) -> int:
    """Validate the declared inputs, then hand the projection to the library."""

    parsed = _workspace_projection_parser().parse_args(arguments)
    refused = _refuse_measurement_inputs(parsed, WORKSPACE_PROJECTION_REQUIRED_FLAGS)
    if refused is not None:
        print(refused, file=sys.stderr)
        return 2

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_workspace_projection import (
        write_head_search_workspace_projection,
    )

    try:
        result = write_head_search_workspace_projection(
            scene_path=parsed.scene,
            geometry_seal_path=parsed.geometry_seal,
            geometry_contract_path=parsed.geometry_contract,
            output_dir=parsed.output_dir,
            coarse_step_rad=parsed.coarse_step_rad,
            command=_command_line(arguments, subcommand="measure-workspace-projection"),
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    print(
        f"WORKSPACE_PROJECTION_PRODUCED top_px={receipt['top_px']!r} "
        f"bottom_px={receipt['bottom_px']!r} poses={receipt['pose_count']} "
        f"points={receipt['point_count']} union={receipt['union_px']} "
        f"intersection={receipt['intersection_px']} step={receipt['chosen_step_rad']!r} "
        f"({receipt['step_source']}) output_dir={parsed.output_dir}"
    )
    return 0


def _deadband_parser() -> argparse.ArgumentParser:
    """The `measure-deadband-candidates` entry: it declares the sealed inputs and the candidates.

    This is the closed-loop flight the run cannot take itself: the installed program walks the production
    controller's own bounded plan in the sealed MuJoCo scene, renders the head camera, detects the cup with
    the selected model and feeds the measured centre error back as the next correction, once per declared
    deadband candidate. Nothing is computed here beyond parsing and validating what the caller declared.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-deadband-candidates",
        description=(
            "Run one closed-loop lock trial per declared deadband candidate in the sealed MuJoCo scene, "
            "into a brand-new output directory, and write the deadband candidates document phase 6 reads"
        ),
    )
    parser.add_argument("--scene", type=Path, help="the sealed MuJoCo scene the trials step")
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument(
        "--production-search-config", type=Path, help="the sealed production search configuration"
    )
    parser.add_argument(
        "--controller-config", type=Path, help="the sealed controller configuration (the control period)"
    )
    parser.add_argument("--frozen-candidate", type=Path, help="the selected frozen candidate document")
    parser.add_argument("--weights", type=Path, help="the selected model's weights file")
    parser.add_argument("--output-dir", type=Path, help="the brand-new directory the documents own")
    parser.add_argument(
        "--candidate",
        type=float,
        action="append",
        help="a declared deadband candidate in pixels; repeat once per candidate",
    )
    parser.add_argument("--anchor", action="append", help="trial only these sealed anchors")
    parser.add_argument("--device", default="cuda", help="the detector device (never a CPU fallback)")
    parser.add_argument("--max-settle-s", type=float, default=None, help="the per-stop settle budget")
    parser.add_argument(
        "--settle-consecutive-steps", type=int, default=None, help="the consecutive quiet control steps"
    )
    parser.add_argument("--max-frames", type=int, default=None, help="the per-trial frame budget")
    return parser


def _measure_deadband_candidates(arguments: list[str]) -> int:
    """Validate the declared inputs and candidates, then hand the lock trials to the library."""

    parsed = _deadband_parser().parse_args(arguments)
    missing = [flag for name, flag in DEADBAND_REQUIRED_FLAGS if getattr(parsed, name) is None]
    name, flag = DEADBAND_CANDIDATE_FLAG
    if not getattr(parsed, name):
        missing.append(flag)
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    absent = [
        str(getattr(parsed, name))
        for name, _flag in DEADBAND_REQUIRED_FLAGS
        if name != "output_dir" and not Path(getattr(parsed, name)).is_file()
    ]
    if absent:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2
    if parsed.output_dir.exists():
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.output_dir} exists; a measurement is "
            f"never resumed, continued or overwritten",
            file=sys.stderr,
        )
        return 2

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_timing_measurement.contracts import SETTLE_CONSECUTIVE_STEPS
    from so101_demo.act.head_search_deadband_measurement.contracts import DEFAULT_MAX_FRAMES
    from so101_demo.act.head_search_deadband_measurement.writer import (
        write_head_search_deadband_measurement,
    )

    optional = {"max_frames": DEFAULT_MAX_FRAMES, "settle_consecutive_steps": SETTLE_CONSECUTIVE_STEPS}
    for key in ("max_settle_s", "settle_consecutive_steps", "max_frames"):
        if getattr(parsed, key) is not None:
            optional[key] = getattr(parsed, key)
    try:
        result = write_head_search_deadband_measurement(
            scene_path=parsed.scene,
            geometry_seal_path=parsed.geometry_seal,
            production_search_config_path=parsed.production_search_config,
            controller_config_path=parsed.controller_config,
            frozen_candidate_path=parsed.frozen_candidate,
            weights_path=parsed.weights,
            output_dir=parsed.output_dir,
            candidates=parsed.candidate,
            anchors=parsed.anchor,
            device=parsed.device,
            command=_command_line(arguments, subcommand="measure-deadband-candidates"),
            **optional,
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    locking = [
        record
        for record in receipt["records"]
        if record["longest_locked_run_frames"] >= receipt["lock_frames_required"]
        and record["direction_reversals"] == 0
    ]
    print(
        f"DEADBAND_CANDIDATES_MEASURED candidates={receipt['candidate_count']} "
        f"anchors={','.join(receipt['anchor_names'])} trials={receipt['trial_count']} "
        f"locking={len(locking)} output_dir={parsed.output_dir}"
    )
    return 0


def _fine_correction_parser() -> argparse.ArgumentParser:
    """The `measure-fine-correction-episodes` entry: the sealed inputs, the split and the budget.

    This is the closed-loop flight the run cannot take itself: one episode per held-out seed of the
    declared split, in that seed's own prepared scene, driven by the production controller's bounded sweep
    and its own fine corrections, with the head camera and the selected model closing the loop. Nothing is
    computed here beyond parsing and validating what the caller declared.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-fine-correction-episodes",
        description=(
            "Run one closed-loop episode per held-out seed of the declared scenario split, in the scene "
            "that seed prepares, and write the fine-correction episodes document phase 6 reads"
        ),
    )
    parser.add_argument("--scene", type=Path, help="the sealed MuJoCo scene the episodes step")
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument(
        "--production-search-config", type=Path, help="the sealed production search configuration"
    )
    parser.add_argument(
        "--controller-config", type=Path, help="the sealed controller configuration (the control period)"
    )
    parser.add_argument("--frozen-candidate", type=Path, help="the selected frozen candidate document")
    parser.add_argument("--weights", type=Path, help="the selected model's weights file")
    parser.add_argument(
        "--dataset-config", type=Path, help="the head dataset profile every seed's scene is prepared from"
    )
    parser.add_argument(
        "--scenario-partitions", type=Path, help="the tracked source of the head-search seed partitions"
    )
    parser.add_argument("--output-dir", type=Path, help="the brand-new directory the documents own")
    parser.add_argument(
        "--split",
        default="held_out_evaluation",
        help="the declared split whose seeds are measured (never the calibration split)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        action="append",
        help="measure only these seeds of the declared split; repeat once per seed",
    )
    parser.add_argument(
        "--anchor",
        action="append",
        help=(
            "the sealed anchor every episode starts from (default `left`, the anchor whose start lies "
            "inside the HS-302 corridor and whose sweep sees the held-out scenes' cup)"
        ),
    )
    parser.add_argument("--device", default="cuda", help="the detector device (never a CPU fallback)")
    parser.add_argument(
        "--generator-commit",
        default="unrecorded",
        help="the commit the dataset profile is used at (the renderer records it, it changes no scene)",
    )
    parser.add_argument("--max-settle-s", type=float, default=None, help="the per-stop settle budget")
    parser.add_argument(
        "--settle-consecutive-steps", type=int, default=None, help="the consecutive quiet control steps"
    )
    parser.add_argument("--max-frames", type=int, default=None, help="the per-episode frame budget")
    parser.add_argument(
        "--max-fine-corrections",
        type=int,
        default=None,
        help=(
            "the harness's own measurement budget for one episode; an episode that reaches it refuses the "
            "document rather than understating the maximum (default 8, never the calibrated value)"
        ),
    )
    parser.add_argument(
        "--max-fine-total-rad",
        type=float,
        default=None,
        help="the harness's own cumulative measurement budget for one episode, in radians (default 2.0)",
    )
    return parser


def _measure_fine_correction_episodes(arguments: list[str]) -> int:
    """Validate the declared inputs, then hand the closed-loop episodes to the library."""

    parsed = _fine_correction_parser().parse_args(arguments)
    missing = [flag for name, flag in FINE_CORRECTION_REQUIRED_FLAGS if getattr(parsed, name) is None]
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    absent = [
        str(getattr(parsed, name))
        for name, _flag in FINE_CORRECTION_REQUIRED_FLAGS
        if name != "output_dir" and not Path(getattr(parsed, name)).is_file()
    ]
    if absent:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2
    if parsed.output_dir.exists():
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.output_dir} exists; a measurement is "
            f"never resumed, continued or overwritten",
            file=sys.stderr,
        )
        return 2

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_fine_correction_episodes.contracts import (
        DEFAULT_MAX_FRAMES,
        DEFAULT_MEASUREMENT_BUDGET,
    )
    from so101_demo.act.head_search_fine_correction_episodes.writer import (
        write_head_search_fine_correction_episodes,
    )
    from so101_demo.act.head_search_timing_measurement.contracts import SETTLE_CONSECUTIVE_STEPS

    optional = {"max_frames": DEFAULT_MAX_FRAMES, "settle_consecutive_steps": SETTLE_CONSECUTIVE_STEPS}
    for key in ("max_settle_s", "settle_consecutive_steps", "max_frames"):
        if getattr(parsed, key) is not None:
            optional[key] = getattr(parsed, key)
    budget = dict(DEFAULT_MEASUREMENT_BUDGET)
    if parsed.max_fine_corrections is not None:
        budget["max_fine_corrections"] = parsed.max_fine_corrections
    if parsed.max_fine_total_rad is not None:
        budget["max_fine_total_rad"] = parsed.max_fine_total_rad
    try:
        result = write_head_search_fine_correction_episodes(
            scene_path=parsed.scene,
            geometry_seal_path=parsed.geometry_seal,
            production_search_config_path=parsed.production_search_config,
            controller_config_path=parsed.controller_config,
            frozen_candidate_path=parsed.frozen_candidate,
            weights_path=parsed.weights,
            dataset_config_path=parsed.dataset_config,
            scenario_partitions_path=parsed.scenario_partitions,
            output_dir=parsed.output_dir,
            seeds=parsed.seed,
            split=parsed.split,
            anchors=parsed.anchor or ["left"],
            device=parsed.device,
            generator_commit=parsed.generator_commit,
            measurement_budget=budget,
            command=_command_line(arguments, subcommand="measure-fine-correction-episodes"),
            **optional,
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    for refused in receipt["refused_episodes"]:
        print(
            f"{refused['failure_code']}: the episode {refused['episode_id']} did not lock "
            f"({refused['failure_detail']})",
            file=sys.stderr,
        )
    succeeded = [
        record for record in receipt["records"] if record["succeeded"] is True
    ]
    print(
        f"FINE_CORRECTION_EPISODES_MEASURED episodes={receipt['episode_count']} "
        f"succeeded={receipt['succeeded_count']} refused={receipt['refused_count']} "
        f"split={receipt['split']} anchor={','.join(receipt['anchor_names'])} "
        f"max_fine_corrections_observed="
        f"{max((record['fine_corrections'] for record in succeeded), default=0)} "
        f"max_cumulative_fine_correction_rad="
        f"{max((sum(record['fine_corrections_rad']) for record in succeeded), default=0.0)!r} "
        f"output_dir={parsed.output_dir}"
    )
    return 0


def _scenario_parser() -> argparse.ArgumentParser:
    """The `measure-scenarios` entry: the sealed inputs, the campaign root and the declared subset.

    This is the scenario flight: the forty declared qualification scenarios, one at a time, each in its
    own prepared scene, from its own declared anchor, with the production controller's bounded sweep and
    its own fine corrections, and with the selected model closing the loop. Nothing is computed here
    beyond parsing and validating what the caller declared.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-scenarios",
        description=(
            "Run the declared qualification scenarios one at a time in the closed loop, journal every "
            "outcome honestly and write the scenarios document, its journal and its receipt"
        ),
    )
    parser.add_argument("--scene", type=Path, help="the sealed MuJoCo scene the scenarios step")
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument(
        "--production-search-config", type=Path, help="the promoted production search configuration"
    )
    parser.add_argument(
        "--controller-config", type=Path, help="the sealed controller configuration (the control period)"
    )
    parser.add_argument("--frozen-candidate", type=Path, help="the selected frozen candidate document")
    parser.add_argument("--weights", type=Path, help="the selected model's weights file")
    parser.add_argument(
        "--dataset-config", type=Path, help="the head dataset profile every scenario is prepared from"
    )
    parser.add_argument(
        "--scenario-partitions", type=Path, help="the tracked source of the head-search seed partitions"
    )
    parser.add_argument("--output-dir", type=Path, help="the brand-new run root the documents own")
    parser.add_argument(
        "--evidence-root", type=Path, help="the registered campaign root the ownership gate checks"
    )
    parser.add_argument(
        "--final-run", type=Path, help="the frozen runtime of record whose identity the run must hold"
    )
    parser.add_argument(
        "--seed",
        type=int,
        action="append",
        help="run only these declared qualification seeds; repeat once per seed",
    )
    parser.add_argument("--device", default="cuda", help="the detector device (never a CPU fallback)")
    parser.add_argument(
        "--generator-commit",
        default="unrecorded",
        help="the commit the dataset profile is used at (it changes no scene)",
    )
    parser.add_argument("--max-settle-s", type=float, default=None, help="the per-stop settle budget")
    parser.add_argument(
        "--settle-consecutive-steps", type=int, default=None, help="the consecutive quiet control steps"
    )
    parser.add_argument("--max-frames", type=int, default=None, help="the per-attempt frame budget")
    parser.add_argument(
        "--interruption-frame",
        type=int,
        default=None,
        help="the frame index at which the declared interrupted classes are stopped fail-closed",
    )
    parser.add_argument(
        "--expected-source-commit", help="the frozen runtime's source commit the identity must match"
    )
    parser.add_argument(
        "--expected-production-config-sha256",
        help="the promoted config digest the identity must match",
    )
    parser.add_argument("--expected-values-sha256", help="the 17 values' digest the identity must match")
    parser.add_argument(
        "--expected-weights-sha256", help="the detector weights digest the identity must match"
    )
    parser.add_argument(
        "--expected-package-prefix", help="the `ros2 pkg prefix so101_demo_py` the gate must observe"
    )
    return parser


def _measure_scenarios(arguments: list[str]) -> int:
    """Validate the declared inputs, then hand the closed-loop scenarios to the library."""

    parsed = _scenario_parser().parse_args(arguments)
    missing = [flag for name, flag in SCENARIO_REQUIRED_FLAGS if getattr(parsed, name) is None]
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    # the campaign root the gate checks is a directory; every other declared input is a file
    absent = [
        str(getattr(parsed, name))
        for name, _flag in SCENARIO_REQUIRED_FLAGS
        if name != "output_dir"
        and not (
            Path(getattr(parsed, name)).is_dir()
            if name == "evidence_root"
            else Path(getattr(parsed, name)).is_file()
        )
    ]
    if absent:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2
    if parsed.output_dir.exists():
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.output_dir} exists; a qualification run "
            f"is never resumed, continued or overwritten",
            file=sys.stderr,
        )
        return 2

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_scenarios import (
        DEFAULT_MAX_FRAMES,
        SETTLE_CONSECUTIVE_STEPS,
        write_head_search_scenarios,
    )

    optional: dict = {"max_frames": DEFAULT_MAX_FRAMES, "settle_consecutive_steps": SETTLE_CONSECUTIVE_STEPS}
    for key in ("max_settle_s", "settle_consecutive_steps", "max_frames", "interruption_frame"):
        if getattr(parsed, key) is not None:
            optional[key] = getattr(parsed, key)
    expected: dict = {}
    for key, attribute in (
        ("source_commit", "expected_source_commit"),
        ("production_config_sha256", "expected_production_config_sha256"),
        ("values_sha256", "expected_values_sha256"),
        ("weight_sha256_declared", "expected_weights_sha256"),
    ):
        value = getattr(parsed, attribute)
        if value:
            expected[key] = value
    try:
        result = write_head_search_scenarios(
            scene_path=parsed.scene,
            geometry_seal_path=parsed.geometry_seal,
            production_search_config_path=parsed.production_search_config,
            controller_config_path=parsed.controller_config,
            frozen_candidate_path=parsed.frozen_candidate,
            weights_path=parsed.weights,
            dataset_config_path=parsed.dataset_config,
            scenario_partitions_path=parsed.scenario_partitions,
            output_dir=parsed.output_dir,
            evidence_root=parsed.evidence_root,
            final_run=parsed.final_run,
            seeds=parsed.seed,
            device=parsed.device,
            generator_commit=parsed.generator_commit,
            expected_runtime=expected or None,
            expected_package_prefix=parsed.expected_package_prefix,
            command=_command_line(arguments, subcommand="measure-scenarios"),
            **optional,
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    for record in receipt["records"]:
        if record["outcome"] == "PASSED":
            continue
        print(
            f"{record['outcome_code']}: the scenario {record['seed']} "
            f"({record['condition_class']}, anchor {record['anchor']}) {record['outcome'].lower()} "
            f"({record.get('outcome_detail')})",
            file=sys.stderr,
        )
    print(
        f"HEAD_SEARCH_SCENARIOS_MEASURED scenarios={receipt['scenario_count']} "
        f"passed={receipt['passed_count']} failed={receipt['failed_count']} "
        f"refused={receipt['refused_count']} "
        f"anchors={json.dumps(receipt['anchor_split'], sort_keys=True)} "
        f"zero_wrong_locks={receipt['zero_wrong_locks']} "
        f"cadence_all_continuous={receipt['cadence_all_continuous']} "
        f"stop_proofs_all_proven={receipt['stop_proofs_all_proven']} "
        f"output_dir={result['output_dir']}"
    )
    return 0


def _camera_parser() -> argparse.ArgumentParser:
    """The `measure-camera` entry: it declares the sealed inputs and the frame budget.

    This is the flight the run cannot take itself: the installed program holds the production controller's
    own settled poses in the sealed MuJoCo scene, renders the head camera once per frame period, detects
    the cup with the selected model and measures the spread of the detected centre, which is the
    `centre_jitter_rad` phase 6 starts `center_deadband_px` from. It measures that field and only that
    field: the image safety margin is a declaration, so it is read from `--safety-margin-declaration` or
    refused, never defaulted.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-camera",
        description=(
            "Hold every sealed anchor's settled poses in the sealed MuJoCo scene, measure the detected "
            "cup centre's spread frame by frame, and write the camera measurements document phase 6 reads"
        ),
    )
    parser.add_argument("--scene", type=Path, help="the sealed MuJoCo scene the frames are rendered in")
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument(
        "--production-search-config", type=Path, help="the sealed production search configuration"
    )
    parser.add_argument(
        "--controller-config", type=Path, help="the sealed controller configuration (the control period)"
    )
    parser.add_argument("--frozen-candidate", type=Path, help="the selected frozen candidate document")
    parser.add_argument("--weights", type=Path, help="the selected model's weights file")
    parser.add_argument("--output-dir", type=Path, help="the brand-new directory the documents own")
    parser.add_argument(
        "--safety-margin-declaration",
        type=Path,
        help=(
            "the artefact that declares image_safety_margin_fraction (derived with ceil against the sealed "
            "image dimensions) or safety_margin_px directly; without one the field is refused, not defaulted"
        ),
    )
    parser.add_argument("--anchor", action="append", help="measure only these sealed anchors")
    parser.add_argument("--device", default="cuda", help="the detector device (never a CPU fallback)")
    parser.add_argument(
        "--frames-per-pose", type=int, default=None, help="how many repeated frames each pose is held for"
    )
    parser.add_argument("--max-settle-s", type=float, default=None, help="the per-pose settle budget")
    parser.add_argument(
        "--settle-consecutive-steps", type=int, default=None, help="the consecutive quiet control steps"
    )
    return parser


def _measure_camera(arguments: list[str]) -> int:
    """Validate the declared inputs, then hand the pose holds to the library.

    The measurement itself is complete when the jitter has been measured; a field no artefact declares is
    a refusal this entry reports with the library's own code and exit status 2, even though the document
    carrying the measured jitter is on disk - a caller must never read a defaulted margin out of it.
    """

    parsed = _camera_parser().parse_args(arguments)
    missing = [flag for name, flag in CAMERA_REQUIRED_FLAGS if getattr(parsed, name) is None]
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    absent = [
        str(getattr(parsed, name))
        for name, _flag in CAMERA_REQUIRED_FLAGS + CAMERA_OPTIONAL_FILE_FLAGS
        if getattr(parsed, name) is not None
        and name != "output_dir"
        and not Path(getattr(parsed, name)).is_file()
    ]
    if absent:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2
    if parsed.output_dir.exists():
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.output_dir} exists; a measurement is "
            f"never resumed, continued or overwritten",
            file=sys.stderr,
        )
        return 2

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_camera_measurement.declarations import DEFAULT_FRAMES_PER_POSE
    from so101_demo.act.head_search_camera_measurement.writer import (
        write_head_search_camera_measurement,
    )
    from so101_demo.act.head_search_timing_measurement.contracts import SETTLE_CONSECUTIVE_STEPS

    optional = {
        "frames_per_pose": DEFAULT_FRAMES_PER_POSE,
        "settle_consecutive_steps": SETTLE_CONSECUTIVE_STEPS,
    }
    for key in ("frames_per_pose", "max_settle_s", "settle_consecutive_steps"):
        if getattr(parsed, key) is not None:
            optional[key] = getattr(parsed, key)
    try:
        result = write_head_search_camera_measurement(
            scene_path=parsed.scene,
            geometry_seal_path=parsed.geometry_seal,
            production_search_config_path=parsed.production_search_config,
            controller_config_path=parsed.controller_config,
            frozen_candidate_path=parsed.frozen_candidate,
            weights_path=parsed.weights,
            output_dir=parsed.output_dir,
            safety_margin_declaration_path=parsed.safety_margin_declaration,
            anchors=parsed.anchor,
            device=parsed.device,
            command=_command_line(arguments, subcommand="measure-camera"),
            **optional,
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    print(
        f"CAMERA_MEASUREMENTS_MEASURED centre_jitter_px={receipt['centre_jitter_px']!r} "
        f"centre_jitter_rad={receipt['centre_jitter_rad']!r} "
        f"poses={receipt['pose_count']} frames={receipt['frame_count']} "
        f"rad_per_px={receipt['rad_per_px']!r} "
        f"safety_margin_px={receipt['safety_margin_px']!r} output_dir={parsed.output_dir}"
    )
    for refusal in receipt["refusals"]:
        print(f"{refusal['code']}: {refusal['detail']}", file=sys.stderr)
    return 2 if receipt["refusals"] else 0


def _refuse_measurement_inputs(parsed, required, optional_file_flags=()) -> str | None:
    """The shared input check of a measurement entry: a missing or absent declaration is refused here."""

    missing = [flag for name, flag in required if getattr(parsed, name) is None]
    if missing:
        return f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}"
    absent = [
        str(getattr(parsed, name))
        for name, _flag in tuple(required) + tuple(optional_file_flags)
        if getattr(parsed, name) is not None
        and name != "output_dir"
        and not Path(getattr(parsed, name)).is_file()
    ]
    if absent:
        return f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}"
    if parsed.output_dir.exists():
        return (
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.output_dir} exists; a measurement is never "
            f"resumed, continued or overwritten"
        )
    return None


def _stop_config_parser() -> argparse.ArgumentParser:
    """The `measure-controller-stop-config` entry: it reads the controller's own declaration.

    This is not a flight: the controller's stopped tolerance is a constant the running controller declares,
    so the entry cites it from the installed header, checks the source tree declares the same bytes, and
    cross-checks the declaration's window step against the sealed controller period. A header that declares
    no tolerance is refused rather than defaulted.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-controller-stop-config",
        description=(
            "Cite the controller's own declared stopped tolerance (the installed ControllerStopWitness "
            "constant) as the document phase 7 reads its third envelope term from"
        ),
    )
    parser.add_argument(
        "--controller-declaration", type=Path, help="the installed controller header that declares it"
    )
    parser.add_argument(
        "--source-declaration", type=Path, help="the same declaration in the tree it was built from"
    )
    parser.add_argument("--controller-config", type=Path, help="the sealed controller configuration")
    parser.add_argument("--output-dir", type=Path, help="the brand-new directory the documents own")
    return parser


def _measure_controller_stop_config(arguments: list[str]) -> int:
    parsed = _stop_config_parser().parse_args(arguments)
    refusal = _refuse_measurement_inputs(parsed, STOP_CONFIG_REQUIRED_FLAGS)
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 2

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_stop_measurement import write_controller_stop_config

    try:
        result = write_controller_stop_config(
            installed_declaration=parsed.controller_declaration,
            source_declaration=parsed.source_declaration,
            controller_config_path=parsed.controller_config,
            output_dir=parsed.output_dir,
            command=_command_line(arguments, subcommand="measure-controller-stop-config"),
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    print(
        f"CONTROLLER_STOP_CONFIG_DECLARED "
        f"stopped_tolerance_rad_s={receipt['stopped_tolerance_rad_s']!r} "
        f"window_samples={receipt['window']['samples']} "
        f"window_step_s={receipt['window']['step_s']!r} "
        f"controller_cycle_period_s={receipt['controller_cycle_period_s']!r} "
        f"measured_here=False output_dir={parsed.output_dir}"
    )
    return 0


def _feedback_parser() -> argparse.ArgumentParser:
    """The `measure-feedback` entry: the declared period, and the quantisation or its refusal."""

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-feedback",
        description=(
            "Read the declared feedback period the stop path consumes and the declared feedback quantisation "
            "resolution; without a declaration of the resolution the field is refused, never defaulted, and "
            "an explicitly zero resolution has to state its basis"
        ),
    )
    parser.add_argument("--controller-config", type=Path, help="the sealed controller configuration")
    parser.add_argument("--output-dir", type=Path, help="the brand-new directory the documents own")
    parser.add_argument(
        "--quantisation-declaration",
        type=Path,
        help=(
            "the artefact that declares quantisation_rad (explicitly zero needs the basis of the zero), or "
            "counts_per_revolution with joint_travel_rad; without one the field is written as null and refused"
        ),
    )
    return parser


def _measure_feedback(arguments: list[str]) -> int:
    parsed = _feedback_parser().parse_args(arguments)
    refusal = _refuse_measurement_inputs(
        parsed, FEEDBACK_REQUIRED_FLAGS, FEEDBACK_OPTIONAL_FILE_FLAGS
    )
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 2

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_stop_measurement import write_feedback_measurements

    try:
        result = write_feedback_measurements(
            controller_config_path=parsed.controller_config,
            output_dir=parsed.output_dir,
            quantisation_declaration_path=parsed.quantisation_declaration,
            command=_command_line(arguments, subcommand="measure-feedback"),
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    print(
        f"FEEDBACK_MEASUREMENTS_MEASURED period_s={receipt['period_s']!r} "
        f"feedback_rate_hz={receipt['feedback_rate_hz']!r} "
        f"controller_cycle_period_s={receipt['controller_cycle_period_s']!r} "
        f"quantisation_rad={receipt['quantisation_rad']!r} output_dir={parsed.output_dir}"
    )
    for record in receipt["refusals"]:
        print(f"{record['code']}: {record['detail']}", file=sys.stderr)
    return 2 if receipt["refusals"] else 0


def _stop_flight_parser(subcommand: str, description: str) -> argparse.ArgumentParser:
    """One of the three stop flights: the sealed scene, the sealed inputs and the brand-new directory."""

    parser = argparse.ArgumentParser(
        prog=f"so101_head_search_calibration {subcommand}", description=description
    )
    parser.add_argument("--scene", type=Path, help="the sealed MuJoCo scene the neck is stepped in")
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument(
        "--production-search-config", type=Path, help="the sealed production search configuration"
    )
    parser.add_argument(
        "--controller-config", type=Path, help="the sealed controller configuration (the control period)"
    )
    parser.add_argument("--output-dir", type=Path, help="the brand-new directory the documents own")
    parser.add_argument("--anchor", action="append", help="measure only these sealed anchors")
    parser.add_argument("--max-settle-s", type=float, default=None, help="the per-pose settle budget")
    parser.add_argument(
        "--settle-consecutive-steps", type=int, default=None, help="the consecutive quiet control steps"
    )
    parser.add_argument(
        "--no-realtime",
        dest="realtime",
        action="store_false",
        default=True,
        help="step the plant as fast as the machine allows instead of pacing it to the monotonic clock",
    )
    return parser


def _measure_stationary(arguments: list[str]) -> int:
    parser = _stop_flight_parser(
        "measure-stationary",
        "Hold the production controller's own settled poses in the sealed MuJoCo scene and sample the "
        "monitored joints' velocities at the declared feedback period",
    )
    parser.add_argument(
        "--samples-per-pose", type=int, default=None, help="how many feedback periods each pose is held for"
    )
    parsed = parser.parse_args(arguments)
    refusal = _refuse_measurement_inputs(parsed, STOP_FLIGHT_REQUIRED_FLAGS)
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 2

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_stop_measurement import (
        DEFAULT_SAMPLES_PER_POSE,
        SETTLE_CONSECUTIVE_STEPS,
        write_stationary_measurements,
    )

    optional = {"samples_per_pose": DEFAULT_SAMPLES_PER_POSE}
    for key, default in (
        ("samples_per_pose", DEFAULT_SAMPLES_PER_POSE),
        ("max_settle_s", None),
        ("settle_consecutive_steps", SETTLE_CONSECUTIVE_STEPS),
    ):
        value = getattr(parsed, key)
        optional[key] = default if value is None else value
    if optional["max_settle_s"] is None:
        optional.pop("max_settle_s")
    try:
        result = write_stationary_measurements(
            scene_path=parsed.scene,
            geometry_seal_path=parsed.geometry_seal,
            production_search_config_path=parsed.production_search_config,
            controller_config_path=parsed.controller_config,
            output_dir=parsed.output_dir,
            anchors=parsed.anchor,
            realtime=parsed.realtime,
            command=_command_line(arguments, subcommand="measure-stationary"),
            **optional,
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    print(
        f"STATIONARY_MEASUREMENTS_MEASURED "
        f"p99_9_velocity_rad_s={receipt['p99_9_velocity_rad_s']!r} "
        f"max_velocity_rad_s={receipt['max_velocity_rad_s']!r} poses={receipt['pose_count']} "
        f"samples={receipt['sample_count']} samples_per_pose={receipt['samples_per_pose']} "
        f"feedback_period_s={receipt['feedback_period_s']!r} output_dir={parsed.output_dir}"
    )
    return 0


def _measure_controller_submissions(arguments: list[str]) -> int:
    parser = _stop_flight_parser(
        "measure-controller-submissions",
        "Submit the installed production controller's own targets through the admission port and record the "
        "simulation-time goal-admission lead of every submission",
    )
    parsed = parser.parse_args(arguments)
    refusal = _refuse_measurement_inputs(parsed, STOP_FLIGHT_REQUIRED_FLAGS)
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 2

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_stop_measurement import (
        SETTLE_CONSECUTIVE_STEPS,
        write_controller_submissions,
    )

    optional = {}
    if parsed.max_settle_s is not None:
        optional["max_settle_s"] = parsed.max_settle_s
    optional["settle_consecutive_steps"] = (
        SETTLE_CONSECUTIVE_STEPS
        if parsed.settle_consecutive_steps is None
        else parsed.settle_consecutive_steps
    )
    try:
        result = write_controller_submissions(
            scene_path=parsed.scene,
            geometry_seal_path=parsed.geometry_seal,
            production_search_config_path=parsed.production_search_config,
            controller_config_path=parsed.controller_config,
            output_dir=parsed.output_dir,
            anchors=parsed.anchor,
            realtime=parsed.realtime,
            command=_command_line(arguments, subcommand="measure-controller-submissions"),
            **optional,
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    print(
        f"CONTROLLER_SUBMISSIONS_MEASURED minimum_lead_s={receipt['minimum_lead_s']!r} "
        f"maximum_lead_s={receipt['maximum_lead_s']!r} lead_spread_s={receipt['lead_spread_s']!r} "
        f"submissions={receipt['submission_count']} control_period_s={receipt['control_period_s']!r} "
        f"time_base={receipt['time_base']} output_dir={parsed.output_dir}"
    )
    return 0


def _measure_stop_proofs(arguments: list[str]) -> int:
    parser = _stop_flight_parser(
        "measure-stop-proofs",
        "Revoke real neck motions at the declared offsets and prove every stop with the installed stop "
        "criterion at the third consecutive qualifying feedback receipt",
    )
    parser.add_argument(
        "--revoke-offset-s",
        type=float,
        action="append",
        default=None,
        help="how long after the motion starts the revoke is requested, in simulation seconds",
    )
    parser.add_argument(
        "--stop-budget-s",
        type=float,
        default=None,
        help="how long a stop proof may look for three consecutive qualifying receipts",
    )
    parsed = parser.parse_args(arguments)
    refusal = _refuse_measurement_inputs(parsed, STOP_FLIGHT_REQUIRED_FLAGS)
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 2

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_stop_measurement import (
        DEFAULT_STOP_BUDGET_S,
        SETTLE_CONSECUTIVE_STEPS,
        write_stop_proofs,
    )

    optional = {
        "stop_budget_s": DEFAULT_STOP_BUDGET_S if parsed.stop_budget_s is None else parsed.stop_budget_s,
        "settle_consecutive_steps": (
            SETTLE_CONSECUTIVE_STEPS
            if parsed.settle_consecutive_steps is None
            else parsed.settle_consecutive_steps
        ),
    }
    if parsed.max_settle_s is not None:
        optional["max_settle_s"] = parsed.max_settle_s
    if parsed.revoke_offset_s:
        optional["revoke_offsets_s"] = parsed.revoke_offset_s
    try:
        result = write_stop_proofs(
            scene_path=parsed.scene,
            geometry_seal_path=parsed.geometry_seal,
            production_search_config_path=parsed.production_search_config,
            controller_config_path=parsed.controller_config,
            output_dir=parsed.output_dir,
            anchors=parsed.anchor,
            realtime=parsed.realtime,
            command=_command_line(arguments, subcommand="measure-stop-proofs"),
            **optional,
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    print(
        f"STOP_PROOFS_MEASURED p99_9_latency_s={receipt['p99_9_latency_s']!r} "
        f"slowest_latency_s={receipt['slowest_latency_s']!r} proofs={receipt['proof_count']} "
        f"feedback_period_s={receipt['feedback_period_s']!r} "
        f"declared_production_latency_s={receipt['declared_production_latency_s']!r} "
        f"exceedances={receipt['exceedance_count']} output_dir={parsed.output_dir}"
    )
    return 0


def _timing_parser() -> argparse.ArgumentParser:
    """The `measure-search-timing` entry: it declares the sealed inputs and calls one library function.

    This is the measurement flight the run cannot take itself: the installed program walks the production
    controller's own bounded stop points in the sealed MuJoCo scene, commanding the scene's neck joint at
    the sealed controller period, applies the declared settle rule to every stop, and - when a detector is
    declared - times one frame per declared frame period of simulation time. Nothing is computed here
    beyond parsing and validating what the caller declared.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-search-timing",
        description=(
            "Walk the bounded stop-point sweep of the production head search controller in the sealed "
            "MuJoCo scene once, into a brand-new output directory, and write the search timing document "
            "phase 6 reads and - with a detector - the frame age document phase 7 reads"
        ),
    )
    parser.add_argument("--scene", type=Path, help="the sealed MuJoCo scene the sweep steps")
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument(
        "--production-search-config", type=Path, help="the sealed production search configuration"
    )
    parser.add_argument(
        "--controller-config", type=Path, help="the sealed controller configuration (the control period)"
    )
    parser.add_argument("--weights", type=Path, help="the sealed detector weights, when frames are timed")
    parser.add_argument("--output-dir", type=Path, help="the brand-new directory the documents own")
    parser.add_argument("--anchor", action="append", help="measure only these sealed anchors")
    parser.add_argument("--device", default="cuda", help="the detector device (never a CPU fallback)")
    parser.add_argument("--max-settle-s", type=float, default=None, help="the per-stop settle budget")
    parser.add_argument(
        "--settle-consecutive-steps", type=int, default=None, help="the consecutive quiet control steps"
    )
    return parser


def _measure_search_timing(arguments: list[str]) -> int:
    """Validate the declared inputs, then hand the sweep to the library module."""

    parsed = _timing_parser().parse_args(arguments)
    missing = [flag for name, flag in TIMING_REQUIRED_FLAGS if getattr(parsed, name) is None]
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    declared = TIMING_REQUIRED_FLAGS
    absent = [
        str(getattr(parsed, name))
        for name, _flag in declared
        if name != "output_dir" and not Path(getattr(parsed, name)).is_file()
    ] + [
        str(getattr(parsed, name))
        for name, _flag in TIMING_OPTIONAL_FILE_FLAGS
        if getattr(parsed, name) is not None and not Path(getattr(parsed, name)).is_file()
    ]
    if absent:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2
    if parsed.output_dir.exists():
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.output_dir} exists; a measurement is "
            f"never resumed, continued or overwritten",
            file=sys.stderr,
        )
        return 2

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_timing_measurement.contracts import (
        DEFAULT_MAX_SETTLE_S,
        SETTLE_CONSECUTIVE_STEPS,
    )
    from so101_demo.act.head_search_timing_measurement.writer import (
        write_head_search_timing_measurement,
    )

    optional = {
        name: getattr(parsed, name)
        for name, _flag in (
            ("max_settle_s", "--max-settle-s"),
            ("settle_consecutive_steps", "--settle-consecutive-steps"),
        )
        if getattr(parsed, name) is not None
    }
    if "max_settle_s" not in optional:
        optional["max_settle_s"] = DEFAULT_MAX_SETTLE_S
    if "settle_consecutive_steps" not in optional:
        optional["settle_consecutive_steps"] = SETTLE_CONSECUTIVE_STEPS
    try:
        result = write_head_search_timing_measurement(
            scene_path=parsed.scene,
            geometry_seal_path=parsed.geometry_seal,
            production_search_config_path=parsed.production_search_config,
            controller_config_path=parsed.controller_config,
            weights_path=parsed.weights,
            output_dir=parsed.output_dir,
            anchors=parsed.anchor,
            device=parsed.device,
            command=_command_line(arguments, subcommand="measure-search-timing"),
            **optional,
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    print(
        f"SEARCH_TIMING_MEASURED p99_settle_s={receipt['p99_settle_s']} "
        f"p99_frame_s={receipt['p99_frame_s']} stops={receipt['stable_stop_count']} "
        f"frames={receipt['frame_count']} anchors={','.join(receipt['anchors'])} "
        f"output_dir={parsed.output_dir}"
    )
    return 0


def _selection_rule_parser() -> argparse.ArgumentParser:
    """The `measure-selection-rule` entry: the sealed config, the future measurement and the output.

    The rule of record has to exist before its measurement, so this entry takes the directory the
    measurement will own and refuses to write anything when that directory already exists; it never
    measures, renders or detects, and `so101_demo.act.head_search_operating_point_measurement` is the
    only library it calls.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-selection-rule",
        description=(
            "Record the phase-3 selection rule (the declared grid, the splits it selects on and the "
            "tie-break chain) into a brand-new output directory, before any measurement exists"
        ),
    )
    parser.add_argument(
        "--production-search-config",
        type=Path,
        help="the sealed production search configuration the grid and its two fixed values come from",
    )
    parser.add_argument(
        "--measurements-output-dir",
        type=Path,
        help="the directory the operating-point measurement will own; it must not exist yet",
    )
    parser.add_argument(
        "--output-dir", type=Path, help="the brand-new directory the rule records own"
    )
    parser.add_argument(
        "--generation", help="the generation the rule binds to, when one is declared"
    )
    parser.add_argument(
        "--measurement-plan-sha256",
        help="the digest of the measurement plan the rule binds to, when one is declared",
    )
    return parser


def _measure_selection_rule(arguments: list[str]) -> int:
    """Validate the declared inputs, then hand the rule record to the library module."""

    parsed = _selection_rule_parser().parse_args(arguments)
    missing = [
        flag for name, flag in SELECTION_RULE_REQUIRED_FLAGS if getattr(parsed, name) is None
    ]
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    absent = [
        str(getattr(parsed, name))
        for name, _flag in SELECTION_RULE_REQUIRED_FLAGS
        # the measurement directory is the one path that must NOT exist yet: it is what proves the rule
        # was written before its measurement
        if name not in ("output_dir", "measurements_output_dir")
        and not Path(getattr(parsed, name)).is_file()
    ]
    if absent:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_operating_point_measurement import (
        record_selection_rule_documents,
    )

    config_path = Path(parsed.production_search_config)
    try:
        result = record_selection_rule_documents(
            production_config=json.loads(config_path.read_text(encoding="utf-8")),
            measurements_output_dir=parsed.measurements_output_dir,
            output_dir=parsed.output_dir,
            generation=parsed.generation,
            measurement_plan_sha256=parsed.measurement_plan_sha256,
            provenance={
                "production_search_config_path": str(config_path),
                "production_search_config_sha256": _digest(config_path),
                "command": _command_line(arguments, subcommand="measure-selection-rule"),
            },
            command=_command_line(arguments, subcommand="measure-selection-rule"),
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    print(
        f"SELECTION_RULE_RECORDED points={receipt['point_count']} "
        f"splits={','.join(receipt['selection_splits'])} "
        f"domains={','.join(receipt['domains'])} "
        f"rule_sha256={receipt['rule_sha256']['head']} output_dir={parsed.output_dir}"
    )
    return 0


def _operating_point_parser() -> argparse.ArgumentParser:
    """The `measure-operating-point` entry: every sealed input, the rules and the three candidates.

    Nothing is computed here beyond parsing and validating what the caller declared: the measurement is
    one library call, and the point it selects is the installed phase 3's own choice, not this entry's.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-operating-point",
        description=(
            "Measure the phase-3 operating-point frames (both domains' val images and calibration "
            "episodes) for the three frozen candidates, into a brand-new output directory, and let the "
            "installed phase 3 select each candidate's point"
        ),
    )
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument("--head-dataset", type=Path, help="the sealed head dataset manifest")
    parser.add_argument("--task-dataset", type=Path, help="the sealed task dataset manifest")
    parser.add_argument(
        "--dataset-config", type=Path, help="the dataset profile the scenes are rendered from"
    )
    parser.add_argument(
        "--production-search-config",
        type=Path,
        help="the sealed production search configuration the grid and its two fixed values come from",
    )
    parser.add_argument("--episode-partitions", type=Path, help="the sealed scenario partitions")
    parser.add_argument(
        "--selection-rule", type=Path, help="the head-domain rule record, written first"
    )
    parser.add_argument(
        "--task-selection-rule", type=Path, help="the task-domain rule record, written first"
    )
    parser.add_argument(
        "--frozen-candidate",
        type=Path,
        action="append",
        help="one frozen candidate document; the measurement covers exactly A, B and C",
    )
    parser.add_argument("--weights-dir", type=Path, help="the directory holding <candidate>.pt")
    parser.add_argument(
        "--output-dir", type=Path, help="the brand-new directory the measurement owns"
    )
    parser.add_argument("--device", default="cuda")
    parser.add_argument(
        "--seed-limit",
        type=int,
        help="measure only the first N calibration seeds (a declared subset, never a silent one)",
    )
    return parser


def _measure_operating_point(arguments: list[str]) -> int:
    """Validate the declared inputs, then hand the whole measurement to the library module."""

    parsed = _operating_point_parser().parse_args(arguments)
    declared = OPERATING_POINT_REQUIRED_FILE_FLAGS + OPERATING_POINT_REQUIRED_DIRECTORY_FLAGS
    missing = [flag for name, flag in declared if getattr(parsed, name) is None]
    if parsed.frozen_candidate is None:
        missing.append("--frozen-candidate")
    if parsed.output_dir is None:
        missing.append("--output-dir")
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    absent = [
        str(getattr(parsed, name))
        for name, _flag in OPERATING_POINT_REQUIRED_FILE_FLAGS
        if not _has_file(getattr(parsed, name))
    ] + [
        str(getattr(parsed, name))
        for name, _flag in OPERATING_POINT_REQUIRED_DIRECTORY_FLAGS
        if not Path(getattr(parsed, name)).is_dir()
    ]
    if absent:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2
    if parsed.output_dir.exists():
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.output_dir} exists; a measurement is "
            f"never resumed, continued or overwritten",
            file=sys.stderr,
        )
        return 2

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_operating_point_measurement import (
        measure_operating_point_measurements,
    )

    try:
        result = measure_operating_point_measurements(
            geometry_seal_path=parsed.geometry_seal,
            head_dataset_manifest_path=parsed.head_dataset,
            task_dataset_manifest_path=parsed.task_dataset,
            dataset_config_path=parsed.dataset_config,
            production_config_path=parsed.production_search_config,
            episode_partitions_path=parsed.episode_partitions,
            selection_rule_path=parsed.selection_rule,
            task_selection_rule_path=parsed.task_selection_rule,
            weights_dir=parsed.weights_dir,
            frozen_candidate_paths=list(parsed.frozen_candidate),
            output_dir=parsed.output_dir,
            device=parsed.device,
            seed_limit=parsed.seed_limit,
            command=_command_line(arguments, subcommand="measure-operating-point"),
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    chosen = ",".join(
        f"{domain}:{candidate}:{point['min_confidence']}/{point['tracking_iou']}"
        for domain in sorted(receipt["chosen"])
        for candidate, point in sorted(receipt["chosen"][domain].items())
    )
    print(
        f"OPERATING_POINTS_MEASURED frames={receipt['frame_count']} "
        f"candidates={receipt['candidate_count']} points={receipt['grid_point_count']} "
        f"chosen={chosen} output_dir={parsed.output_dir}"
    )
    return 0


def _admission_document_parser() -> argparse.ArgumentParser:
    """The `measure-admission` entry: the six sealed inputs, the new run root and the output directory.

    Nothing is decided here: the six sealed inputs are digested by the same helper the run uses, the
    generation is the brand-new run root's name, and the plan, the admission and the receipt are one
    library call. The entry refuses a missing or absent input before the library runs, and the library
    refuses an existing run root or output directory, a document that cannot yield a plan, and a plan the
    installed controller will not accept.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-admission",
        description=(
            "Produce the run's --admission: the flat measurement plan the installed controller is "
            "constructed with, the six-field CalibrationMeasurementAdmission for role=calibration, and "
            "the receipt that records the refusals and the single resource binding"
        ),
    )
    parser.add_argument("--dataset", type=Path, help="dataset manifest (sealed input)")
    parser.add_argument("--candidate", type=Path, help="model manifest (sealed input)")
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument("--episode-partitions", type=Path, help="scenario partitions (sealed input)")
    parser.add_argument("--production-config", type=Path, help="the sealed production configuration")
    parser.add_argument("--camera-config", type=Path, help="the production camera configuration")
    parser.add_argument("--seal", type=Path, help="declared digests of the six sealed inputs")
    parser.add_argument(
        "--run-root", type=Path, help="the brand-new run root the run will claim; it must not exist"
    )
    parser.add_argument(
        "--output-dir", type=Path, help="the brand-new directory the plan, admission and receipt own"
    )
    parser.add_argument("--operation", default="neck_target", help="the admitted operation")
    parser.add_argument("--cpu-cores", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--gpu-device", default="0")
    parser.add_argument(
        "--search-start-rad",
        type=float,
        default=0.0,
        help="the neck angle the bounded plan starts from; it must lie in the sealed interval",
    )
    return parser


def _measure_admission(arguments: list[str]) -> int:
    """Validate the declared inputs, then hand the admission document to the library module."""

    parsed = _admission_document_parser().parse_args(arguments)
    missing = [flag for name, flag in ADMISSION_REQUIRED_FLAGS if getattr(parsed, name) is None]
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    absent = [
        str(getattr(parsed, name))
        for name in ADMISSION_REQUIRED_FILE_FLAGS
        if not Path(getattr(parsed, name)).is_file()
    ] + [
        str(getattr(parsed, name))
        for name, _flag in ADMISSION_OPTIONAL_FILE_FLAGS
        if getattr(parsed, name) is not None and not Path(getattr(parsed, name)).is_file()
    ]
    if absent:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2

    from so101_demo.act.head_search_calibration_admission_document import (
        record_admission_document,
    )
    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused

    try:
        result = record_admission_document(
            sealed_inputs=_sealed_inputs(parsed),
            run_root=parsed.run_root,
            output_dir=parsed.output_dir,
            operation=parsed.operation,
            cpu_cores=parsed.cpu_cores,
            gpu_device=_gpu_device(parsed.gpu_device),
            search_start_rad=parsed.search_start_rad,
            command=_command_line(arguments, subcommand="measure-admission"),
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    admission = result["admission"]
    print(
        f"ADMISSION_RECORDED generation={admission['generation']} "
        f"plan_sha256={admission['measurement_plan_sha256']} "
        f"safe_interval_rad={admission['safe_interval_rad']} output_dir={parsed.output_dir}"
    )
    return 0


def _bundle_inputs_parser() -> argparse.ArgumentParser:
    """The `measure-bundle-inputs` entry: the declared documents, the device and the output directory.

    Nothing is computed and nothing is constructed here: the entry validates the declared inputs and hands
    them to `so101_demo.act.head_search_calibration_bundle_inputs`, which constructs the installed
    controller and the production detector with the recorded values and records what it observes. The
    output directory must be brand new, exactly as every other runner's is.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-bundle-inputs",
        description=(
            "Produce the run's --bundle-inputs: the geometry and perception evidence blocks, each with the "
            "evidence phase 8 requires and the startup readback observed on the production components"
        ),
    )
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument(
        "--production-config", type=Path, help="the sealed production search configuration"
    )
    parser.add_argument(
        "--operating-point", type=Path, help="the installed phase 3's selection document"
    )
    parser.add_argument("--frozen-candidate", type=Path, help="the selected frozen candidate document")
    parser.add_argument("--weights", type=Path, help="the selected model's weights file")
    parser.add_argument(
        "--operating-point-measurements",
        type=Path,
        help="the phase-3 frame measurements the selection was made on, cited as input evidence",
    )
    parser.add_argument(
        "--output-dir", type=Path, help="the brand-new directory the document and receipt own"
    )
    parser.add_argument("--device", default="cuda", help="the detector device (never a CPU fallback)")
    parser.add_argument(
        "--readback-identity",
        default=None,
        help="the identity the readback's controller is constructed under",
    )
    parser.add_argument(
        "--web-bundle-root",
        type=Path,
        help="the installed teleop web bundle whose digest the runtime identity records",
    )
    return parser


def _measure_bundle_inputs(arguments: list[str]) -> int:
    """Validate the declared inputs, then hand the declaration to the library module."""

    parsed = _bundle_inputs_parser().parse_args(arguments)
    missing = [flag for name, flag in BUNDLE_INPUTS_REQUIRED_FLAGS if getattr(parsed, name) is None]
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    absent = [
        str(getattr(parsed, name))
        for name in BUNDLE_INPUTS_REQUIRED_FILE_FLAGS
        if not Path(getattr(parsed, name)).is_file()
    ] + [
        str(getattr(parsed, name))
        for name, _flag in BUNDLE_INPUTS_OPTIONAL_FILE_FLAGS
        if getattr(parsed, name) is not None and not Path(getattr(parsed, name)).is_file()
    ]
    if absent:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2
    if parsed.output_dir.exists():
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.output_dir} exists; a measurement is "
            f"never resumed, continued or overwritten",
            file=sys.stderr,
        )
        return 2

    from so101_demo.act.head_search_calibration_bundle_inputs import (
        DECLARED_PARAMETERS,
        record_bundle_inputs,
    )
    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused

    request = {
        "geometry_seal": parsed.geometry_seal,
        "production_config": parsed.production_config,
        "operating_point": parsed.operating_point,
        "frozen_candidate": parsed.frozen_candidate,
        "weights": parsed.weights,
        "output_dir": parsed.output_dir,
        "operating_point_measurements": parsed.operating_point_measurements,
        "device": parsed.device,
        "web_bundle_root": parsed.web_bundle_root,
        "command": _command_line(arguments, subcommand="measure-bundle-inputs"),
    }
    if parsed.readback_identity is not None:
        request["readback_identity"] = parsed.readback_identity
    try:
        result = record_bundle_inputs(**request)
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    unverified = sorted(result["receipt"]["unverified"])
    print(
        f"BUNDLE_INPUTS_RECORDED parameters={len(DECLARED_PARAMETERS)} "
        f"unverified={','.join(unverified) if unverified else 'none'} "
        f"detector_device={parsed.device} output_dir={parsed.output_dir}"
    )
    return 0


def _episode_records_parser() -> argparse.ArgumentParser:
    """The `measure-episode-records` entry: the measurement document, the partitions and the output.

    The entry measures nothing: phase 4's gate reads one document per declared seed, and the installed
    phase-3 flight's measurement document already holds those frames. The library re-shapes them verbatim
    and refuses a seed, a candidate's measurement or a domain that is missing.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-episode-records",
        description=(
            "Write the gate's --episode-records from the installed phase-3 measurement document: one "
            "document per declared seed, every measured frame verbatim"
        ),
    )
    parser.add_argument(
        "--operating-point-measurements", type=Path, help="the installed phase-3 measurement document"
    )
    parser.add_argument(
        "--episode-partitions", type=Path, help="the sealed scenario partitions the seeds come from"
    )
    parser.add_argument("--split", default="calibration", help="the partition the episodes belong to")
    parser.add_argument(
        "--output-dir", type=Path, help="the brand-new directory the per-seed documents own"
    )
    return parser


def _measure_episode_records(arguments: list[str]) -> int:
    """Validate the declared inputs, then hand the re-shaping to the library module."""

    parsed = _episode_records_parser().parse_args(arguments)
    missing = [flag for name, flag in EPISODE_RECORDS_REQUIRED_FLAGS if getattr(parsed, name) is None]
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    absent = [
        str(getattr(parsed, name))
        for name in EPISODE_RECORDS_REQUIRED_FILE_FLAGS
        if not Path(getattr(parsed, name)).is_file()
    ]
    if absent:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2
    if parsed.output_dir.exists():
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.output_dir} exists; a measurement is "
            f"never resumed, continued or overwritten",
            file=sys.stderr,
        )
        return 2

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_episode_records import record_episode_records

    try:
        result = record_episode_records(
            measurements=parsed.operating_point_measurements,
            partitions=parsed.episode_partitions,
            output_dir=parsed.output_dir,
            split=parsed.split,
            command=_command_line(arguments, subcommand="measure-episode-records"),
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    print(
        f"EPISODE_RECORDS_RECORDED split={receipt['split']} seeds={receipt['seed_count']} "
        f"frames={receipt['frame_count']} output_dir={parsed.output_dir}"
    )
    return 0


def _has_file(value) -> bool:
    """Every declared file must exist: a repeated flag declares one file per candidate."""

    values = value if isinstance(value, list) else [value]
    return bool(values) and all(Path(item).is_file() for item in values)


def _run_parser() -> argparse.ArgumentParser:
    """The `run` entry: the six sealed inputs, the phase inputs and the gate's own arguments.

    Nothing is fabricated here. The search configuration is the one the installed controller is
    constructed with, the admission is the repository's own `CalibrationMeasurementAdmission`, the rule
    and the measurements come from the phase-3 producers, and the argument list of the frozen-candidate
    gate is assembled from the declared documents rather than rebuilt.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration run",
        description="Run a frozen Head execution input or the eight calibration phases into a new run root",
    )
    parser.add_argument('--execution-inputs', type=Path,
                        help='absolute frozen input for one stage-one development execution; excludes calibration phase flags')
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--seal", type=Path, help="declared digests of the six sealed inputs")
    parser.add_argument("--dataset", type=Path, help="dataset manifest")
    parser.add_argument("--candidate", type=Path, help="model manifest")
    parser.add_argument("--geometry-seal", type=Path)
    parser.add_argument("--episode-partitions", type=Path)
    parser.add_argument("--production-config", type=Path)
    parser.add_argument("--camera-config", type=Path)
    parser.add_argument("--production-search-config", type=Path)
    parser.add_argument("--admission", type=Path)
    parser.add_argument("--selection-rule", type=Path)
    parser.add_argument("--operating-point-measurements", type=Path)
    parser.add_argument("--candidate-id")
    parser.add_argument("--held-out-measurements", type=Path)
    parser.add_argument("--frozen-candidate", type=Path, action="append")
    parser.add_argument("--task-dataset", type=Path)
    parser.add_argument("--episode-split", default="calibration")
    parser.add_argument("--episode-records", type=Path)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--bootstrap-repetitions", type=int, default=10_000)
    parser.add_argument("--weights-dir", type=Path)
    parser.add_argument("--head-dataset-root", type=Path)
    parser.add_argument("--task-dataset-root", type=Path)
    parser.add_argument("--bundle-inputs", type=Path)
    for name, flag, _shape in RUN_PHASE_MEASUREMENTS:
        parser.add_argument(flag, dest=name, type=Path, help=f"phase measurement: {name}")
    parser.add_argument("--operation", default="neck_target")
    parser.add_argument("--cpu-cores", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--gpu-device", default="0")
    return parser


def _run(arguments: list[str]) -> int:
    """Validate the declared inputs, then hand the phases to the orchestration library.

    The formal stage-one file-protocol entry is the same `run` command with
    `--execution-inputs`: it is mutually exclusive with the legacy eight-phase
    flags, and a mixed invocation is refused before anything reads a path.
    """

    if any(argument == "--execution-inputs" or argument.startswith("--execution-inputs=")
           for argument in arguments):
        formal_flags = {'--execution-inputs', '--print-readback', '--help'}
        legacy = [argument for argument in arguments
                  if argument.startswith("--") and argument.split('=',1)[0] not in formal_flags]
        if legacy:
            print(
                f"{HEAD_SEARCH_RUN_INPUTS_INCOMPLETE}: --execution-inputs is the formal stage-one "
                f"entry and cannot be combined with the legacy phase flags {' '.join(sorted(legacy))}",
                file=sys.stderr,
            )
            return 2
        from .head_execution_run import main as execution_main

        return execution_main(arguments)

    parsed = _run_parser().parse_args(arguments)
    missing = [flag for name, flag in RUN_REQUIRED_FLAGS if getattr(parsed, name) is None]
    if missing:
        print(
            f"{HEAD_SEARCH_RUN_INPUTS_INCOMPLETE}: a run declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    absent = [str(path) for path in _declared_paths(parsed) if not Path(path).is_file()] + [
        str(path) for path in _declared_directories(parsed) if not Path(path).is_dir()
    ]
    if absent:
        print(
            f"{HEAD_SEARCH_RUN_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2
    try:
        phase_inputs = _phase_inputs(parsed)
    except (KeyError, TypeError, ValueError) as error:
        print(
            f"{HEAD_SEARCH_RUN_INPUTS_INCOMPLETE}: a declared document is not the one it must be: "
            f"{error}",
            file=sys.stderr,
        )
        return 2

    from so101_demo.act.head_search_calibration_run import (
        CalibrationInputsRefused,
        execute_calibration_run,
    )

    try:
        result = execute_calibration_run(
            run_root=parsed.run_root,
            phase_inputs=phase_inputs,
            command=_command_line(arguments),
        )
    except CalibrationInputsRefused as error:
        # the entry's own refusals - the trajectory contract and an existing root - and nothing ran
        print(str(error), file=sys.stderr)
        return 2
    status = result.run_status
    if result.status == "SUCCEEDED":
        print(f"RUN_SUCCEEDED {result.run_root}")
        return 0
    print(
        f"RUN_FAILED first_failing_phase={status['first_failing_phase']} "
        f"code={status['failure_code']} run_root={result.run_root}",
        file=sys.stderr,
    )
    return int(status["failure_exit_code"])


def _phase_inputs(parsed) -> CalibrationPhaseInputs:
    """Build the phase inputs from the declared documents; nothing is computed here."""

    from so101_demo.act.head_search_calibration_run import CalibrationPhaseInputs
    from so101_demo.act.head_search_measured_readback import observe_measured_readbacks
    from so101_demo.act.pick_place_calibration_admission import CalibrationMeasurementAdmission

    admission_document = _json_document(parsed.admission)
    fields = (
        "generation",
        "status",
        "measurement_plan_sha256",
        "safe_interval_rad",
        "controller_generation",
        "broker_generation",
    )
    if set(admission_document) != set(fields):
        raise ValueError(f"a production admission declares exactly {list(fields)}")
    generation = admission_document["generation"]
    if type(generation) is not str or not generation:
        raise ValueError("a production admission names the generation it admits")

    held_out = (
        _frames(parsed.held_out_measurements) if parsed.held_out_measurements is not None else ()
    )
    measurements = {
        name: (
            _records(getattr(parsed, name))
            if shape == "records"
            else _json_document(getattr(parsed, name))
        )
        for name, _flag, shape in RUN_PHASE_MEASUREMENTS
    }
    return CalibrationPhaseInputs(
        production_search_config=_json_document(parsed.production_search_config),
        sealed_inputs=_sealed_inputs(parsed),
        admission=CalibrationMeasurementAdmission(**admission_document),
        generation=generation,
        operation=parsed.operation,
        cpu_cores=parsed.cpu_cores,
        gpu_device=_gpu_device(parsed.gpu_device),
        selection_rule=_json_document(parsed.selection_rule),
        operating_point_measurements=_frames(parsed.operating_point_measurements),
        candidate_id=parsed.candidate_id,
        held_out_measurements=held_out,
        evaluation_arguments=_evaluation_arguments(parsed),
        bundle_inputs=_json_document(parsed.bundle_inputs),
        # phases 6 and 7 prove the eleven values they measure by constructing the production component
        # that consumes each one (plan section 2b): the run observes them at startup rather than
        # restating the number it just computed
        readback_observer=observe_measured_readbacks,
        **measurements,
    )


def _sealed_inputs(parsed) -> dict:
    """The seal of the six dependencies: the declared one, or what the run just read and digested."""

    if parsed.seal is not None:
        declared = _json_document(parsed.seal)
        if not isinstance(declared, Mapping):
            raise ValueError("a seal declares one entry per sealed input")
        return dict(declared)
    sealed = {}
    for name, attribute, _flag in RUN_SEALED_INPUT_FLAGS:
        path = Path(getattr(parsed, attribute))
        sealed[name] = {"path": str(path), "sha256": _digest(path)}
    return sealed


def _evaluation_arguments(parsed) -> list[str]:
    """The frozen-candidate gate's own argument list, assembled from the declared documents."""

    arguments = ["compare"]
    for path in parsed.frozen_candidate:
        arguments += ["--candidate", str(path)]
    arguments += [
        "--head-dataset",
        str(parsed.dataset),
        "--task-dataset",
        str(parsed.task_dataset),
        "--episode-partitions",
        str(parsed.episode_partitions),
        "--episode-split",
        parsed.episode_split,
        "--bootstrap-repetitions",
        str(parsed.bootstrap_repetitions),
        "--device",
        parsed.device,
    ]
    for flag, value in (
        ("--episode-records", parsed.episode_records),
        ("--weights-dir", parsed.weights_dir),
        ("--head-dataset-root", parsed.head_dataset_root),
        ("--task-dataset-root", parsed.task_dataset_root),
    ):
        if value is not None:
            arguments += [flag, str(value)]
    return arguments


def _declared_paths(parsed) -> list[Path]:
    """Every file a run declares: the required ones, the repeated ones and the optional ones."""

    values: list[Path] = []
    for name in RUN_REQUIRED_FILE_FLAGS:
        value = getattr(parsed, name)
        if value is None:
            continue
        values.extend(value if isinstance(value, list) else [value])
    for name in RUN_OPTIONAL_FILE_FLAGS:
        value = getattr(parsed, name)
        if value is not None:
            values.append(value)
    return [Path(value) for value in values]


def _declared_directories(parsed) -> list[Path]:
    return [
        Path(getattr(parsed, name))
        for name in RUN_OPTIONAL_DIRECTORY_FLAGS
        if getattr(parsed, name) is not None
    ]


def _json_document(path) -> Mapping:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError(f"{path} is not a JSON object")
    return document


def _records(path) -> list:
    """A phase's declared list of measured records, or a document that carries them under `records`."""

    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(document, Mapping):
        document = document.get("records")
    if isinstance(document, (str, bytes)) or not isinstance(document, Sequence):
        raise ValueError(f"{path} declares no list of measured records")
    return list(document)


def _frames(path) -> list:
    """A phase-3 measurement document: a list of frames, or a document that carries them."""

    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(document, Mapping):
        document = document.get("frames")
    if isinstance(document, (str, bytes)) or not isinstance(document, Sequence):
        raise ValueError(f"{path} declares no list of measurement frames")
    return list(document)


def _gpu_device(value: str):
    return int(value) if value.isdigit() else value


def _command_line(arguments: Sequence[str], *, subcommand: str = "run") -> str:
    return (
        f"ros2 run so101_demo_py so101_head_search_calibration {subcommand} "
        + " ".join(shlex.quote(str(item)) for item in arguments)
    )


def _verify_promoted_config(
    run_root: Path, approved: str | None, promoted_config: Path | None
) -> int:
    """Hash the promoted bundle's bytes and record the approval once, immutably.

    The bundle is hashed as bytes, so a formatting-only difference is caught rather than normalised away,
    and the receipt is created exclusively: a second verification cannot overwrite what was approved. The
    receipt belongs to a run root that does not exist yet, so verification obeys the same no-resume rule as
    every other runner.
    """

    from so101_demo.act.head_search_qualification import _require_new_root, write_exclusive

    if not approved:
        print("HEAD_SEARCH_APPROVAL_REQUIRED: pass --approved-bundle-sha256", file=sys.stderr)
        return 2
    if promoted_config is None:
        print("HEAD_SEARCH_BUNDLE_REQUIRED: pass --promoted-config", file=sys.stderr)
        return 2
    promoted = Path(promoted_config)
    if not promoted.is_file():
        print(f"HEAD_SEARCH_BUNDLE_MISSING: {promoted} is absent", file=sys.stderr)
        return 2
    measured = hashlib.sha256(promoted.read_bytes()).hexdigest()
    if measured != approved:
        print(
            f"HEAD_SEARCH_APPROVAL_MISMATCH: promoted {measured} differs from approved {approved}",
            file=sys.stderr,
        )
        return 2
    try:
        root = _require_new_root(run_root)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    try:
        write_exclusive(
            root,
            "approval-receipt.json",
            {
                "approved_bundle_sha256": approved,
                "promoted_bundle_sha256": measured,
                "promoted_config": str(promoted),
                "hashed": "bytes",
                "verified": True,
            },
        )
    except FileExistsError:
        print("APPROVAL_RECEIPT_EXISTS: an approval is immutable", file=sys.stderr)
        return 2
    print(f"HEAD_SEARCH_APPROVED {measured}")
    return 0


# --- measure-frame-contract and measure-skew --------------------------------------------------------

#: the frame contract declaration reads one production artefact; the skew measurement starts the running
#: stack, so it declares the scene, the seal, the plugin and controller configurations, the URDF and the
#: frame contract the capture is paced against
FRAME_CONTRACT_FLAGS = (
    ("plugin_config", "--plugin-config", True),
    ("output_dir", "--output-dir", False),
)
SKEW_FLAGS = (
    ("scene", "--scene", True),
    ("geometry_seal", "--geometry-seal", True),
    ("plugin_config", "--plugin-config", True),
    ("controller_config", "--controller-config", True),
    ("urdf", "--urdf", True),
    ("frame_contract", "--frame-contract", True),
    ("output_dir", "--output-dir", False),
)


def _frame_contract_parser() -> argparse.ArgumentParser:
    """The `measure-frame-contract` entry: the production artefact that declares the head camera rate."""

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-frame-contract",
        description=(
            "Declare the 10 Hz head-search frame contract phase 7 expresses every cap in, citing the "
            "production camera plugin configuration that declares the head camera stream and its rate, "
            "into a brand-new output directory"
        ),
    )
    parser.add_argument("--plugin-config", type=Path, help="the production MuJoCo plugin configuration")
    parser.add_argument("--output-dir", type=Path, help="the brand-new directory the document owns")
    parser.add_argument(
        "--skew-measurements",
        type=Path,
        default=None,
        help=(
            "a measured skew document whose capture achieved rate is recorded beside the declaration; "
            "the declared rate stays the value and the document says so"
        ),
    )
    return parser


def _validate_flight(parsed, flags) -> tuple[list[str], list[str]]:
    """The declared inputs of one measurement flight: the flags it is missing and the paths that are not files."""

    missing = [flag for name, flag, required in flags if required and getattr(parsed, name) is None]
    if missing:
        return missing, []
    absent = [
        str(getattr(parsed, name))
        for name, _flag, required in flags
        if required and not Path(getattr(parsed, name)).is_file()
    ]
    return [], absent


def _measure_frame_contract(arguments: list[str]) -> int:
    """Validate the declared production artefact, then hand the declaration to the library."""

    parsed = _frame_contract_parser().parse_args(arguments)
    missing, absent = _validate_flight(parsed, FRAME_CONTRACT_FLAGS)
    if parsed.skew_measurements is not None and not parsed.skew_measurements.is_file():
        absent.append(str(parsed.skew_measurements))
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    if absent:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2
    if parsed.output_dir.exists():
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.output_dir} exists; a measurement is "
            f"never resumed, continued or overwritten",
            file=sys.stderr,
        )
        return 2

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_transport_measurement import write_transport_measurements

    try:
        result = write_transport_measurements(
            mode="frame_contract",
            plugin_config_path=parsed.plugin_config,
            output_dir=parsed.output_dir,
            measured_rate_from=parsed.skew_measurements,
            command=_command_line(arguments, subcommand="measure-frame-contract"),
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    document, receipt = result["measurement"], result["receipt"]
    print(
        f"FRAME_CONTRACT_DECLARED {document['frame_rate_hz']} Hz "
        f"declared_by={document['declared_by']['source']} "
        f"sha256={document['declared_by']['sha256']} "
        f"measured={document['measured_frame_rate_hz']} value_source={document['value_source']} "
        f"output_dir={parsed.output_dir}"
    )
    return 0 if receipt["status"] == "DECLARED" else 2


def _skew_parser() -> argparse.ArgumentParser:
    """The `measure-skew` entry: the running MuJoCo head-camera transport, sampled for its stamps.

    This flight starts the production MuJoCo simulation with the production camera plugin, the robot state
    publisher and the joint-state broadcaster, subscribes to the image, CameraInfo and joint-state topics
    exactly as `RosSearchAdapter` does, and records the paired stamps. It loads no detector and uses no
    GPU, and it leaves no node behind.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-skew",
        description=(
            "Measure the image/CameraInfo/joint skew of the running head-camera transport, with the clock "
            "resolution the capture itself observed, into a brand-new output directory"
        ),
    )
    parser.add_argument("--scene", type=Path, help="the sealed MuJoCo scene the stack is started with")
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument("--plugin-config", type=Path, help="the production MuJoCo plugin configuration")
    parser.add_argument(
        "--controller-config", type=Path, help="the production ros2_controllers.yaml the stack loads"
    )
    parser.add_argument("--urdf", type=Path, help="the ACT URDF template the stack's robot is built from")
    parser.add_argument(
        "--frame-contract", type=Path, help="the declaration the capture is paced against"
    )
    parser.add_argument("--output-dir", type=Path, help="the brand-new directory the document owns")
    parser.add_argument("--frames", type=int, default=300, help="the frames to pair (default 300)")
    parser.add_argument(
        "--timeout-s", type=float, default=180.0, help="the whole capture's budget (default 180 s)"
    )
    parser.add_argument(
        "--startup-timeout-s",
        type=float,
        default=90.0,
        help="the stack's readiness budget (default 90 s)",
    )
    parser.add_argument(
        "--pair-window-s",
        type=float,
        default=0.15,
        help="the causal pairing window of CameraInfo and joint state (default 0.15 s)",
    )
    return parser


def _measure_skew(arguments: list[str]) -> int:
    """Validate the declared stack inputs, start the running transport, and hand the flight to the library."""

    parsed = _skew_parser().parse_args(arguments)
    missing, absent = _validate_flight(parsed, SKEW_FLAGS)
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    if absent:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2
    if parsed.output_dir.exists():
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.output_dir} exists; a measurement is "
            f"never resumed, continued or overwritten",
            file=sys.stderr,
        )
        return 2

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_transport_measurement import (
        MujocoRosTransport,
        RosTopicSkewCapture,
        leave_nothing_running,
        write_transport_measurements,
    )

    transport = MujocoRosTransport(
        urdf_path=parsed.urdf,
        scene_path=parsed.scene,
        plugin_config_path=parsed.plugin_config,
        controller_config_path=parsed.controller_config,
        workspace=parsed.output_dir / "transport",
        startup_timeout_s=parsed.startup_timeout_s,
        logger=lambda message: print(f"transport: {message}", file=sys.stderr),
    )
    capture = RosTopicSkewCapture(
        frames=parsed.frames,
        timeout_s=parsed.timeout_s,
        pair_window_s=parsed.pair_window_s,
        startup_timeout_s=parsed.startup_timeout_s,
    )
    transport.capture = capture.capture
    transport.frames = parsed.frames
    try:
        result = write_transport_measurements(
            mode="skew",
            plugin_config_path=parsed.plugin_config,
            scene_path=parsed.scene,
            controller_config_path=parsed.controller_config,
            frame_contract_path=parsed.frame_contract,
            transport=transport,
            frames=parsed.frames,
            timeout_s=parsed.timeout_s,
            pair_window_s=parsed.pair_window_s,
            output_dir=parsed.output_dir,
            runtime_identity=_transport_runtime_identity(parsed),
            command=_command_line(arguments, subcommand="measure-skew"),
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    finally:
        leftovers = leave_nothing_running()
        if leftovers:
            print(
                "TRANSPORT_LEFT_RUNNING: " + "; ".join(leftovers), file=sys.stderr
            )
    document = result["measurement"]
    print(
        f"SKEW_MEASURED samples={len(document['samples'])} "
        f"max_skew_s={document['observed']['max_skew_s']} "
        f"clock_resolution_s={document['clock_resolution_s']} "
        f"achieved_rate_hz={document['capture'].get('achieved_rate_hz')} "
        f"inside_cap={document['observed']['inside_cap']} "
        f"output_dir={parsed.output_dir}"
    )
    return 0


def _transport_runtime_identity(parsed) -> dict:
    """What ran, for the document's provenance: never a measurement, and never allowed to fail the run."""

    identity = {"ros_distro": os.environ.get("ROS_DISTRO"), "python": sys.executable}
    try:
        from ament_index_python.packages import get_package_prefix

        identity["prefix_mujoco_ros2_control"] = get_package_prefix("mujoco_ros2_control")
        identity["prefix_so101_demo_py"] = get_package_prefix("so101_demo_py")
    except Exception as error:  # noqa: BLE001 - provenance is recorded, it never fails a measurement
        identity["prefix_lookup_error"] = str(error)
    for library in sorted(
        Path(identity.get("prefix_mujoco_ros2_control", "/nonexistent")).glob(
            "opt/mujoco_vendor/lib/libmujoco.so.*"
        )
    ):
        identity["mujoco_c_library"] = str(library)
    identity["stack_nodes"] = ["mujoco_ros2_control", "robot_state_publisher", "joint_state_broadcaster"]
    identity["detector_loaded"] = False
    identity["cuda_used"] = False
    identity["motion_commanded"] = False
    identity["frames_requested"] = parsed.frames
    return identity


def _ownership_parser() -> argparse.ArgumentParser:
    """Step 1's entry: the gate root, the campaign root, and the frozen runtime it must match."""

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration check-ownership",
        description=(
            "Read the fresh process table, ROS graph, GPU processes, tmux ownership and evidence root, "
            "refuse any second owner, and bind the frozen runtime of record before a qualifier starts"
        ),
    )
    parser.add_argument("--run-root", type=Path, required=True, help="a brand-new gate root")
    parser.add_argument("--evidence-root", type=Path, required=True, help="the registered campaign root")
    parser.add_argument("--planned-run-root", type=Path, help="the qualifier root that must not exist")
    parser.add_argument("--final-run", type=Path, help="the frozen qualification runtime root of record")
    parser.add_argument(
        "--production-config", type=Path, help="a promoted config; defaults to the frozen install copy"
    )
    parser.add_argument("--expected-source-commit")
    parser.add_argument("--expected-production-config-sha256")
    parser.add_argument("--expected-values-sha256")
    parser.add_argument("--expected-weights-sha256")
    parser.add_argument("--expected-package-prefix")
    return parser


def _check_ownership(arguments: list[str]) -> int:
    """Run the stack-free ownership gate, write its receipt, and fail closed on any refusal."""

    parsed = _ownership_parser().parse_args(arguments)
    if parsed.production_config is not None and parsed.final_run is None:
        print(
            "RUNTIME_IDENTITY_UNREADABLE: --production-config is read relative to --final-run",
            file=sys.stderr,
        )
        return 2
    expected: dict[str, str] = {}
    if parsed.expected_source_commit:
        expected["source_commit"] = parsed.expected_source_commit
    if parsed.expected_production_config_sha256:
        expected["production_config_sha256"] = parsed.expected_production_config_sha256
    if parsed.expected_values_sha256:
        expected["values_sha256"] = parsed.expected_values_sha256
    if parsed.expected_weights_sha256:
        expected["weight_sha256_declared"] = parsed.expected_weights_sha256
    runtime = None
    if parsed.final_run is not None:
        # the identity is read before the run root is claimed: a bad runtime must leave nothing behind
        try:
            runtime = ownership.read_runtime_identity(
                parsed.final_run, production_config=parsed.production_config
            )
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 2
    try:
        document = ownership.check_exclusive_ownership(
            run_root=parsed.run_root,
            evidence_root=parsed.evidence_root,
            planned_run_root=parsed.planned_run_root,
            runtime=runtime,
            expected_runtime=expected or None,
            expected_package_prefix=parsed.expected_package_prefix,
        )
    except ValueError as error:
        if "RUN_ROOT_ALREADY_EXISTS" not in str(error):
            raise
        print(str(error), file=sys.stderr)
        return 2
    if document["status"] == ownership.EXCLUSIVE_OWNERSHIP_OK:
        print(f"{document['status']} {document['run_root']}")
        return 0
    codes = ",".join(str(item["code"]) for item in document["refusals"])
    print(f"{document['status']} {codes}", file=sys.stderr)
    return 2


#: the `measure-production-smoke` entry: the production smoke. It declares the exclusive-ownership receipt,
#: the frozen runtime of record, the promoted configuration and bundle, and the sealed inputs the one
#: production composition is started from; `--run-root` is the brand-new phase root the journal owns and
#: the neck's dead-man directory is the one the sealed `--controller-config` declares.
PRODUCTION_SMOKE_REQUIRED_FLAGS = (
    ("ownership_receipt", "--ownership-receipt"),
    ("run_root", "--run-root"),
    ("final_run", "--final-run"),
    ("production_config", "--production-config"),
    ("approved_bundle", "--approved-bundle"),
    ("geometry_seal", "--geometry-seal"),
    ("scene", "--scene"),
    ("urdf", "--urdf"),
    ("plugin_config", "--plugin-config"),
    ("controller_config", "--controller-config"),
    ("weights", "--weights"),
    ("frozen_candidate", "--frozen-candidate"),
    ("workdir", "--workdir"),
)

#: the entry as it is recorded in the journal, one name per script that can run it
PRODUCTION_SMOKE_ENTRY = "so101_head_search_calibration measure-production-smoke"
PRODUCTION_SMOKE_SCRIPT_ENTRY = "so101_head_search_smoke --run-root"


def _production_smoke_parser() -> argparse.ArgumentParser:
    """The `measure-production-smoke` entry: one owned stack, one bounded search, one sealed journal."""

    from so101_demo.act.head_search_production_smoke import ANCHORS as SMOKE_ANCHORS
    from so101_demo.act.head_search_production_smoke import CONDITION_CLASS

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-production-smoke",
        description=(
            "Run the production smoke: take the exclusive-ownership receipt, start the one "
            "production composition, place the anchor's cup where the seal declares it, run the bounded "
            "search through the real adapter and controller, prove the lock, the 10 Hz cadence, the "
            "bounded commands and the three-sample stop, then stop the stack and prove it is gone. The "
            "success condition is the sealed journal the aggregate phase consumes, not the planning "
            "coverage proof, which is written beside it"
        ),
    )
    parser.add_argument("--run-root", type=Path, help="the brand-new phase root the journal owns")
    parser.add_argument(
        "--ownership-receipt",
        type=Path,
        help="Step 1's exclusive-ownership receipt for this run root",
    )
    parser.add_argument("--final-run", type=Path, help="the frozen runtime of record")
    parser.add_argument(
        "--production-config", type=Path, help="the promoted production search config"
    )
    parser.add_argument("--approved-bundle", type=Path, help="the approved calibration bundle")
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument("--scene", type=Path, help="the sealed MuJoCo scene the stack steps")
    parser.add_argument(
        "--urdf", type=Path, help="the ACT URDF the stack's robot description is built from"
    )
    parser.add_argument(
        "--plugin-config", type=Path, help="the production MuJoCo plugin configuration"
    )
    parser.add_argument(
        "--controller-config", type=Path, help="the sealed controller configuration"
    )
    parser.add_argument("--weights", type=Path, help="the selected model's weights file")
    parser.add_argument(
        "--frozen-candidate", type=Path, help="the selected frozen candidate document"
    )
    parser.add_argument("--workdir", type=Path, help="the scratch directory the phase writes into")
    parser.add_argument(
        "--anchor",
        default=SMOKE_ANCHORS[0],
        help=f"the seal anchor to search, one of {','.join(SMOKE_ANCHORS)}",
    )
    parser.add_argument(
        "--scenario",
        dest="condition_class",
        default=CONDITION_CLASS,
        help=(
            "the declared condition class the terminal is judged against (the flag the coverage smoke "
            "accepted and never read); the production smoke is the legal single cup, `nominal`"
        ),
    )
    parser.add_argument(
        "--device", default="cuda", help="the detector device (never a CPU fallback)"
    )
    parser.add_argument(
        "--expected-source-commit",
        help="the frozen runtime's source commit the identity must match",
    )
    parser.add_argument(
        "--expected-production-config-sha256",
        help="the promoted config digest the identity must match",
    )
    parser.add_argument(
        "--expected-values-sha256", help="the 17 values' digest the identity must match"
    )
    parser.add_argument(
        "--expected-weights-sha256", help="the detector weights digest the identity must match"
    )
    parser.add_argument(
        "--expected-package-prefix",
        help="the `ros2 pkg prefix so101_demo_py` the gate must observe",
    )
    return parser


def _measure_production_smoke(arguments: list[str], *, entry: str = PRODUCTION_SMOKE_ENTRY) -> int:
    """Validate the declared inputs, then hand the one smoke flight to the library.

    The CLI is thin on purpose: the library owns the order (class, runtime, receipt, seal, root, flight,
    seal the journal, aggregate it) and this entry owns the flag surface and the exit code.
    """

    parsed = _production_smoke_parser().parse_args(arguments)
    missing = [
        flag for name, flag in PRODUCTION_SMOKE_REQUIRED_FLAGS if getattr(parsed, name) is None
    ]
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a production smoke declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    absent = [
        str(getattr(parsed, name))
        for name, _flag in PRODUCTION_SMOKE_REQUIRED_FLAGS
        if name not in ("run_root", "workdir") and not Path(getattr(parsed, name)).exists()
    ]
    if absent:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2
    if parsed.run_root.exists():
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.run_root} exists; a qualification run "
            f"is never resumed, continued or overwritten",
            file=sys.stderr,
        )
        return 2

    from functools import partial

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_production_smoke import (
        read_runtime_of_record,
        run_smoke_flight,
        write_head_search_production_smoke,
    )

    production = json.loads(parsed.production_config.read_text(encoding="utf-8"))
    values = production.get("values") if isinstance(production.get("values"), Mapping) else {}
    if not values:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.production_config} declares no values "
            f"block",
            file=sys.stderr,
        )
        return 2
    seal = json.loads(parsed.geometry_seal.read_text(encoding="utf-8"))
    command = _command_line(arguments, subcommand="measure-production-smoke")
    try:
        runtime = read_runtime_of_record(parsed.final_run, parsed.production_config)
        expected: dict = {}
        for key, attribute in (
            ("source_commit", "expected_source_commit"),
            ("production_config_sha256", "expected_production_config_sha256"),
            ("values_sha256", "expected_values_sha256"),
            ("weight_sha256_declared", "expected_weights_sha256"),
        ):
            value = getattr(parsed, attribute)
            if value:
                expected[key] = value
        for key, wanted in sorted(expected.items()):
            if runtime.get(key) != wanted:
                raise CalibrationInputsRefused(
                    "SMOKE_RUNTIME_UNVERIFIED",
                    f"{key}: the run declares {wanted!r} and the frozen runtime reads "
                    f"{runtime.get(key)!r}",
                )
        result = write_head_search_production_smoke(
            run_root=parsed.run_root,
            ownership_receipt=parsed.ownership_receipt,
            runtime=runtime,
            seal=seal,
            workdir=parsed.workdir,
            anchor=parsed.anchor,
            condition_class=parsed.condition_class,
            values=values,
            approved_bundle_sha256=hashlib.sha256(parsed.approved_bundle.read_bytes()).hexdigest(),
            producer={
                "entry": entry,
                "argv_sha256": hashlib.sha256(" ".join(command.split()).encode()).hexdigest(),
                "command": command,
                "pid": os.getpid(),
            },
            run_flight=partial(
                run_smoke_flight,
                urdf_path=parsed.urdf,
                scene_path=parsed.scene,
                plugin_config_path=parsed.plugin_config,
                controller_config_path=parsed.controller_config,
                production_config_path=parsed.production_config,
                weights_path=parsed.weights,
                frozen_candidate_path=parsed.frozen_candidate,
                production=production,
                device=parsed.device,
                excluded_pids=process_ancestry(),
            ),
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    document = result["document"]
    print(
        f"production_smoke: anchor={document['anchor']} scenario={document['condition_class']} "
        f"terminal_status={document['terminal_status']} status={document['status']} "
        f"gates={json.dumps(document['gates'], sort_keys=True)} "
        f"elapsed_s={document.get('elapsed_s')} journal={result['journal']}"
    )
    for refusal in result["refusals"]:
        print(f"{refusal['code']}: {refusal['detail']}", file=sys.stderr)
    print(
        f"SMOKE_MEASURED status={document['status']} run_root={result['run_root']} "
        f"sealed_journal={result['sealed_journal']} frames={document['frame_cadence']['frame_count']} "
        f"rate_hz={document['frame_cadence']['achieved_rate_hz']}"
    )
    return 0 if document["status"] == "PASS" else 2


#: the two spellings of the during-qualification readback entry: the `measure-` name the other phase
#: entries use, and the bare name the aggregate's own gate vocabulary uses for the artefact
QUALIFICATION_READBACK_ENTRY = "so101_head_search_calibration measure-qualification-readback"
QUALIFICATION_READBACK_ALIASES = ("readback", "qualification-readback")

#: every declared input of the readback, and the flag it is declared under. The run root is the
#: qualification run root the readback is taken FOR - the aggregate claims it afterwards - so it must not
#: exist yet, exactly like the ownership receipt's own `planned_run_root`
QUALIFICATION_READBACK_REQUIRED_FLAGS = (
    ("ownership_receipt", "--ownership-receipt"),
    ("final_run", "--final-run"),
    ("production_config", "--production-config"),
    ("approved_bundle", "--approved-bundle"),
    ("geometry_seal", "--geometry-seal"),
    ("scene", "--scene"),
    ("urdf", "--urdf"),
    ("plugin_config", "--plugin-config"),
    ("controller_config", "--controller-config"),
    ("weights", "--weights"),
)


def _qualification_readback_parser() -> argparse.ArgumentParser:
    """The `measure-qualification-readback` entry: one owned stack, seventeen values, four measurements."""

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-qualification-readback",
        description=(
            "Run the during-qualification approved-values readback: take the exclusive-ownership "
            "receipt that guards the qualification run root, start the one production composition, read "
            "each of the seventeen approved values off the production component that consumes it while "
            "the stack runs, read the four camera measurements off the running camera and TF, load the "
            "one CUDA detector from the frozen weights, then stop the stack and prove it is gone. The "
            "document the aggregate's `approved_values_readback` gate consumes is written under the "
            "evidence root, and the qualification run root it declares stays unclaimed for the aggregator"
        ),
    )
    parser.add_argument(
        "--run-root",
        type=Path,
        help="the qualification run root this readback is taken for; it must not exist yet",
    )
    parser.add_argument(
        "--evidence-root",
        type=Path,
        help="the readback's own evidence root (the campaign's qualification-readback-<UTC>)",
    )
    parser.add_argument(
        "--ownership-receipt",
        type=Path,
        help="Step 1's exclusive-ownership receipt, whose planned root is the run root above",
    )
    parser.add_argument("--final-run", type=Path, help="the frozen runtime of record")
    parser.add_argument(
        "--production-config", type=Path, help="the promoted production search config whose values are read"
    )
    parser.add_argument("--approved-bundle", type=Path, help="the approved calibration bundle")
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument("--scene", type=Path, help="the sealed MuJoCo scene the stack steps")
    parser.add_argument("--urdf", type=Path, help="the ACT URDF the stack's robot description is built from")
    parser.add_argument("--plugin-config", type=Path, help="the production MuJoCo plugin configuration")
    parser.add_argument("--controller-config", type=Path, help="the sealed controller configuration")
    parser.add_argument("--weights", type=Path, help="the selected model's weights file")
    parser.add_argument("--workdir", type=Path, help="the scratch directory the phase writes into")
    parser.add_argument(
        "--anchor",
        default="default",
        help="the seal anchor whose controller configuration the running controller is built with",
    )
    parser.add_argument("--device", default="cuda", help="the detector device (never a CPU fallback)")
    parser.add_argument(
        "--camera-reference",
        type=Path,
        help="an optional document carrying approved values for the four camera measurements",
    )
    parser.add_argument(
        "--expected-source-commit", help="the frozen runtime's source commit the identity must match"
    )
    parser.add_argument(
        "--expected-production-config-sha256",
        help="the promoted config digest the identity must match",
    )
    parser.add_argument(
        "--expected-values-sha256", help="the 17 values' digest the identity must match"
    )
    parser.add_argument(
        "--expected-weights-sha256", help="the detector weights digest the identity must match"
    )
    return parser


def _measure_qualification_readback(
    arguments: list[str], *, entry: str = QUALIFICATION_READBACK_ENTRY
) -> int:
    """Validate the declared inputs, then hand the one readback to the library.

    The CLI is thin on purpose: the library owns the order (recorded values against the approval, the
    receipt, the run root, one stack, the observations, the teardown proof) and this entry owns the flag
    surface and the exit code.
    """

    parsed = _qualification_readback_parser().parse_args(arguments)
    missing = [
        flag for name, flag in QUALIFICATION_READBACK_REQUIRED_FLAGS if getattr(parsed, name) is None
    ]
    if parsed.run_root is None:
        missing.insert(0, "--run-root")
    if parsed.evidence_root is None:
        missing.insert(0, "--evidence-root")
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a qualification readback declares "
            f"{' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    absent = [
        str(getattr(parsed, name))
        for name, _flag in QUALIFICATION_READBACK_REQUIRED_FLAGS
        if not Path(getattr(parsed, name)).exists()
    ]
    if absent:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2
    if parsed.run_root.exists():
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.run_root} exists; the readback is "
            f"taken for a qualification run root the aggregate has not claimed yet, and no qualification "
            f"phase is ever resumed",
            file=sys.stderr,
        )
        return 2
    if parsed.evidence_root.exists() and any(parsed.evidence_root.iterdir()):
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.evidence_root} exists and is not "
            f"empty; a readback is never resumed or overwritten",
            file=sys.stderr,
        )
        return 2

    from functools import partial

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_qualification_readback import (
        run_readback_observation,
        write_head_search_qualification_readback,
    )

    production = json.loads(parsed.production_config.read_text(encoding="utf-8"))
    seal = json.loads(parsed.geometry_seal.read_text(encoding="utf-8"))
    approved_bundle = json.loads(parsed.approved_bundle.read_text(encoding="utf-8"))
    camera_reference = (
        json.loads(parsed.camera_reference.read_text(encoding="utf-8"))
        if parsed.camera_reference is not None
        else None
    )
    command = _command_line(arguments, subcommand="measure-qualification-readback")
    try:
        runtime = ownership.read_runtime_identity(parsed.final_run, production_config=parsed.production_config)
        expected: dict = {}
        for key, attribute in (
            ("source_commit", "expected_source_commit"),
            ("production_config_sha256", "expected_production_config_sha256"),
            ("values_sha256", "expected_values_sha256"),
            ("weight_sha256_declared", "expected_weights_sha256"),
        ):
            value = getattr(parsed, attribute)
            if value:
                expected[key] = value
        for key, wanted in sorted(expected.items()):
            if runtime.get(key) != wanted:
                raise CalibrationInputsRefused(
                    "READBACK_RUNTIME_UNVERIFIED",
                    f"{key}: the run declares {wanted!r} and the frozen runtime reads "
                    f"{runtime.get(key)!r}",
                )
        result = write_head_search_qualification_readback(
            run_root=parsed.run_root,
            evidence_root=parsed.evidence_root,
            ownership_receipt=parsed.ownership_receipt,
            runtime=runtime,
            approved_bundle=approved_bundle,
            production_config=production,
            observe=partial(
                run_readback_observation,
                workdir=parsed.workdir,
                production=production,
                seal=seal,
                anchor=parsed.anchor,
                production_config_path=parsed.production_config,
                urdf_path=parsed.urdf,
                scene_path=parsed.scene,
                plugin_config_path=parsed.plugin_config,
                controller_config_path=parsed.controller_config,
                weights_path=parsed.weights,
                device=parsed.device,
                excluded_pids=process_ancestry(),
            ),
            approved_bundle_path=parsed.approved_bundle,
            production_config_path=parsed.production_config,
            camera_reference=camera_reference,
            command=f"{entry} {command}",
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    document = result["document"]
    observed = [
        f"{name}={row.get('observed_value')}"
        for name, row in sorted(document["values"].items())
    ]
    for row in observed:
        print(f"observed {row}")
    print(
        f"camera_measurements="
        f"{json.dumps({name: row.get('observed_value') for name, row in document['camera_measurements'].items()}, sort_keys=True)}"
    )
    print(
        f"READBACK_MEASURED status={document['status']} run_root={result['run_root']} "
        f"evidence_root={result['evidence_root']} values={document['values_count']} "
        f"values_sha256={document['values_sha256']} elapsed_s={result['elapsed_s']:.1f} "
        f"document={result['document_path']} teardown={result['teardown_proof']}"
    )
    return 0 if document["status"] == "PASS" else 2


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == ['measure-feedback-bootstrap']:
        print('HEAD_ONLINE_BOOTSTRAP_REMOVED: use run --execution-inputs with '
              'fresh stage-one development inputs', file=sys.stderr)
        return 2
    # Step 1's gate is stack-free and runs before any run root is claimed: it must not be routed through
    # the qualifier's four-subcommand parser, which owns the runners that do start things
    if arguments[:1] == ["check-ownership"]:
        return _check_ownership(arguments[1:])
    # `run` declares the inputs of the eight phases, so its entry is the run module's and not a stub
    if arguments[:1] == ["run"]:
        return _run(arguments[1:])
    # the one measurement the run cannot take itself is its own installed entry, never a script
    if arguments[:1] == ["measure-coarse-step"]:
        return _measure_coarse_step(arguments[1:])
    # the sealed scene's own declaration is the other document the run declares but does not read itself
    if arguments[:1] == ["measure-mujoco"]:
        return _measure_mujoco(arguments[1:])
    # the bounded stop-point sweep's settle and frame timing is the third flight the run cannot take
    if arguments[:1] == ["measure-search-timing"]:
        return _measure_search_timing(arguments[1:])
    # the closed-loop deadband lock trials are the fourth flight the run cannot take
    if arguments[:1] == ["measure-deadband-candidates"]:
        return _measure_deadband_candidates(arguments[1:])
    # the camera's centre jitter is the fifth flight the run cannot take; its safety margin is a
    # declaration this entry reads or refuses, never a number it makes up
    if arguments[:1] == ["measure-camera"]:
        return _measure_camera(arguments[1:])
    # the held-out fine-correction episodes are the sixth closed-loop flight: one scene per held-out seed,
    # the production controller's own sweep and corrections, and the selected model closing the loop
    if arguments[:1] == ["measure-fine-correction-episodes"]:
        return _measure_fine_correction_episodes(arguments[1:])
    # The forty serial scenarios are their own installed flight: the closed loop per declared
    # qualification seed, the per-scenario journal, and the honest aggregate that claims no verdict
    if arguments[:1] == ["measure-scenarios"]:
        return _measure_scenarios(arguments[1:])
    # The production smoke is its own installed flight: one owned stack, the production
    # closed loop, the sealed journal and the aggregator the qualification gate consumes
    if arguments[:1] == ["measure-production-smoke"]:
        return _measure_production_smoke(arguments[1:])
    # the during-qualification readback: the same entry under the aggregate's own vocabulary for it
    if arguments[:1] == ["measure-qualification-readback"]:
        return _measure_qualification_readback(arguments[1:])
    for alias in QUALIFICATION_READBACK_ALIASES:
        if arguments[:1] == [alias]:
            return _measure_qualification_readback(
                arguments[1:], entry=f"so101_head_search_calibration {alias}"
            )
    # The three restarts are their own installed flight: one owned stack per anchor, the
    # production admission for every neck goal, and a teardown the phase proves before the next anchor
    if arguments[:1] == ["measure-restarts"]:
        return _measure_restarts(arguments[1:])
    # the legal pick workspace's projection is the sixth: it reads the scene's camera pose and projects,
    # loading no detector, no renderer and no GPU
    if arguments[:1] == ["measure-workspace-projection"]:
        return _measure_workspace_projection(arguments[1:])
    # the controller's stopped tolerance is a declaration of the running controller: this entry cites it
    if arguments[:1] == ["measure-controller-stop-config"]:
        return _measure_controller_stop_config(arguments[1:])
    # the feedback period is declared; the feedback resolution is declared or refused, never defaulted
    if arguments[:1] == ["measure-feedback"]:
        return _measure_feedback(arguments[1:])
    # the stationary velocity noise, the goal-admission lead and the stop proofs are the last three flights
    if arguments[:1] == ["measure-stationary"]:
        return _measure_stationary(arguments[1:])
    if arguments[:1] == ["measure-controller-submissions"]:
        return _measure_controller_submissions(arguments[1:])
    if arguments[:1] == ["measure-stop-proofs"]:
        return _measure_stop_proofs(arguments[1:])
    # the running-topic frame contract declaration is the seventh measurement's declaration half; the
    # skew measurement that paces itself against it is the eighth
    if arguments[:1] == ["measure-frame-contract"]:
        return _measure_frame_contract(arguments[1:])
    if arguments[:1] == ["measure-skew"]:
        return _measure_skew(arguments[1:])
    # phase 3's two inputs are the two flights whose ordering is part of the evidence: the rule record is
    # written before the measurement it governs can own a directory, and the measurement is the one the
    # rule consumes
    if arguments[:1] == ["measure-selection-rule"]:
        return _measure_selection_rule(arguments[1:])
    if arguments[:1] == ["measure-operating-point"]:
        return _measure_operating_point(arguments[1:])
    # the run's admission is its own declared input: the plan, the six-field admission and the receipt
    # that records the refusals are produced here, from the same six sealed inputs the run declares
    if arguments[:1] == ["measure-admission"]:
        return _measure_admission(arguments[1:])
    # the run's declared parameter evidence is its other declared input: the six blocks with the live
    # effective-value readback are produced here
    if arguments[:1] == ["measure-bundle-inputs"]:
        return _measure_bundle_inputs(arguments[1:])
    # phase 4's gate reads the measured calibration episodes one document per seed: this entry reshapes
    # the installed phase-3 measurement document into that declared contract, verbatim
    if arguments[:1] == ["measure-episode-records"]:
        return _measure_episode_records(arguments[1:])
    parsed = qualification_parser().parse_args(arguments)
    run_root = Path(parsed.run_root)
    if parsed.command == "verify-promoted-config":
        return _verify_promoted_config(
            run_root, parsed.approved_bundle_sha256, parsed.promoted_config
        )
    if parsed.command == "qualify":
        # the aggregate phase: only the declared evidence that was actually presented goes in, and an
        # absent flag stays absent so the verdict refuses it by name instead of defaulting to something
        inputs = {
            name: value
            for name, value in (
                ("final_run", parsed.final_run),
                ("production_config", parsed.promoted_config),
                ("approved_bundle", parsed.approved_bundle),
                ("ownership_receipt", parsed.ownership_receipt),
                ("runtime_readback", parsed.runtime_readback),
                ("production_smoke_root", parsed.production_smoke_root),
                ("scenarios_root", parsed.scenarios_root),
                ("restart_receipts", parsed.restart_receipts),
                ("teleop_acceptance_receipt", parsed.teleop_acceptance_receipt),
                ("scenario_partitions", parsed.scenario_partitions),
            )
            if value is not None
        }
        expected_runtime = {
            key: value
            for key, value in (
                ("source_commit", parsed.expected_source_commit),
                ("production_config_sha256", parsed.expected_production_config_sha256),
                ("values_sha256", parsed.expected_values_sha256),
                ("weight_sha256_declared", parsed.expected_weights_sha256),
            )
            if value is not None
        }
        if expected_runtime:
            inputs["expected_runtime"] = expected_runtime
        try:
            report = qualify_head_search(inputs, run_root)
        except ValueError as error:
            if "RUN_ROOT_ALREADY_EXISTS" not in str(error):
                raise
            print(str(error), file=sys.stderr)
            return 2
        if report["status"] == HEAD_SEARCH_QUALIFIED:
            print(f"{report['status']} {report['runtime_id']}")
            return 0
        # a refusal is not a traceback: every missing item and every violated gate is named, and the
        # exit code says no pass was published
        for reason in report["blocking_reasons"]:
            print(
                f"{reason['code']} {reason['gate']}: {reason['item']}: {reason['detail']}",
                file=sys.stderr,
            )
        print(
            f"{report['status']} missing={len(report['missing'])} "
            f"violations={len(report['violations'])} "
            f"verdict={run_root / 'qualification-verdict.json'}",
            file=sys.stderr,
        )
        return 2
    if parsed.command == "serve-teleop":
        return _serve_teleop(parsed)
    print(f"HEAD_SEARCH_COMMAND_UNKNOWN: {parsed.command!r}", file=sys.stderr)
    return 2


def _frozen_run_root(final_run) -> Path:
    """The frozen toolchain root, from the flag or from the installed package prefix."""

    if final_run is not None:
        return Path(final_run)
    from ament_index_python.packages import get_package_prefix

    prefix = Path(get_package_prefix("so101_demo_py"))
    if prefix.parent.name != "install":
        raise ValueError(
            f"RUNTIME_IDENTITY_UNREADABLE: {prefix} is not an install prefix of a toolchain root"
        )
    return prefix.parent.parent


def _source_web_dir() -> Path | None:
    """The worktree's own web package, for the case's Bun invocation."""

    override = os.environ.get("SO101_TELEOP_WEB_DIR")
    if override:
        return Path(override)
    candidate = Path(__file__).resolve().parents[4] / "so101_teleop" / "web"
    return candidate if (candidate / "package.json").is_file() else None


def _serve_teleop(parsed) -> int:
    """The owned acceptance: start, probe, run the case, tear down, then write the receipt.

    Refusing is a result and it is recorded as one: every declared input is read off disk, every probe is
    measured, and the receipt is written only after the teardown has been observed. There is no longer a
    path that writes a descriptor without measuring anything, and no path that reports
    ``teardown: not-attempted``.
    """

    from so101_demo.act.head_search_teleop_acceptance import (
        DEFAULT_FRAME_PROBE,
        DEFAULT_WEB_PORT,
        PROFILE,
        RECEIPT_ARTIFACT,
        TeleopAcceptanceRefused,
        accept_teleop,
    )

    if not parsed.bundle:
        print(
            "TELEOP_ACCEPTANCE_INPUTS_INCOMPLETE: pass --bundle (the approved calibration bundle)",
            file=sys.stderr,
        )
        return 2
    if not parsed.runtime_id:
        print("TELEOP_ACCEPTANCE_INPUTS_INCOMPLETE: pass --runtime-id", file=sys.stderr)
        return 2
    try:
        final_run = _frozen_run_root(parsed.final_run)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    production_config = parsed.production_config or (
        final_run
        / "install/so101_demo_py/share/so101_demo_py/config/mujoco/act/head_search_runtime.json"
    )
    run_root = Path(parsed.run_root)
    ready_file = Path(parsed.ready_file) if parsed.ready_file else run_root / "head-camera-connection.json"
    acceptance_root = Path(parsed.acceptance_root) if parsed.acceptance_root else ready_file.parent
    socket_root = (
        Path(parsed.bridge_socket_root)
        if parsed.bridge_socket_root
        else Path(os.environ.get("SO101_UNIFIED_SOCKET_DIR") or acceptance_root / "bridge")
    )
    expected = {
        key: value
        for key, value in (
            ("source_commit", parsed.expected_source_commit),
            ("production_config_sha256", parsed.expected_production_config_sha256),
            ("values_sha256", parsed.expected_values_sha256),
            ("weight_sha256_declared", parsed.expected_weights_sha256),
        )
        if value is not None
    }
    try:
        receipt = accept_teleop(
            run_root=run_root,
            acceptance_root=acceptance_root,
            socket_root=socket_root,
            ready_file=ready_file,
            final_run=final_run,
            production_config=production_config,
            approved_bundle=parsed.bundle,
            approval_receipt=parsed.approval_receipt,
            qualification_report=parsed.qualification_report,
            runtime_id=parsed.runtime_id,
            profile=parsed.profile or PROFILE,
            device=parsed.device,
            frames=parsed.frames if parsed.frames is not None else DEFAULT_FRAME_PROBE,
            web_port=parsed.web_port if parsed.web_port is not None else DEFAULT_WEB_PORT,
            weights_path=parsed.weights,
            frozen_candidate=parsed.frozen_candidate,
            expected=expected or None,
            web_dir=parsed.web_dir or _source_web_dir(),
            ros_python=os.environ.get("SO101_UNIFIED_ROS_PYTHON") or sys.executable,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
    except TeleopAcceptanceRefused as error:
        print(f"{error.code}: {error.detail}", file=sys.stderr)
        return 2
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt_path = acceptance_root / RECEIPT_ARTIFACT
    print(f"TELEOP_ACCEPTANCE {receipt['status']} receipt={receipt_path}")
    for reason in receipt["refusals"]:
        print(f"  refusal {reason['code']}: {reason['detail']}", file=sys.stderr)
    return 0 if receipt["status"] == "PASSED" else 2


def _digest(path: Path) -> str:
    if not Path(path).is_file():
        return ""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


if __name__ == "__main__":  # pragma: no cover - console script entry
    raise SystemExit(main())
