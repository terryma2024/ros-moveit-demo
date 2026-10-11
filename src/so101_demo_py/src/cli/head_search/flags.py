"""Required and optional flags and entry names of the Head search calibration subcommands."""

from __future__ import annotations

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
