# Head Search calibration runtime - implementation plan (revision 2)

Implements the eight fixed `run` phases (design §8.2) so `so101_head_search_calibration run` produces
`head-search-calibration-bundle.json` carrying the 17 parameters. Today the CLI writes only `run-receipt.json` and a
378-byte `calibration-state.json` (ledger HS-233). Revision 1 was rejected by review (ledger HS-279); this revision
answers its five findings and adds the runtime contract that revision 1 omitted (ledger HS-280).

## 1. Hard rules (from the design; none are optional)

1. **The installed program produces the values.** Design line 25 forbids ad-hoc scripts generating final parameters.
   Every bundle number is computed by repository code executed through
   `ros2 run so101_demo_py so101_head_search_calibration run`.
2. **Runtime contract, design §8.2** (verbatim in ledger HS-280): `run` and the first `qualify` **reuse the existing
   `CalibrationMeasurementAdmission` and `CalibrationSearchBinding`**; only a **single measurement flight with
   `role=calibration`** is admitted; **release and recorder are refused unconditionally**; every neck target binds to
   **one generation, one measurement plan, one safe interval**, and carries an **independent sweep-check receipt**;
   **resources are bound exactly once at the CLI entry and never rebound inside a phase**.
3. **No deadlock**: the first calibration must not call production Head Search entry points gated on
   `TASK8_READY/QUALIFIED`.
4. **Architecture**: mathematics and policy live in independently testable library modules; the CLI only parses
   arguments, validates inputs and orchestrates phases.
5. **No `--resume`**. `run-status.json` is audit only, never a checkpoint. The result is `SUCCEEDED` or `FAILED`;
   on failure the run records the first failing phase, failure code, command, exit code and the evidence already
   produced, and stops immediately.
6. **Per-parameter evidence**: value, unit, selection formula, input evidence + SHA256, observed distribution,
   safety margin, production owner, and the startup readback proving the value took effect (design §7.1).
7. **Pre-requisite outside this plan's phases**: the production controller's current forward-cumulative `2*pi` motion
   does **not** satisfy the trajectory contract and must be changed to the bounded stop-point sequence through
   RED/GREEN before phases 6 and 7 can be validated. This is a change to existing code, gated first.

## 2. Phase plan (fixed order, one artefact per phase)

| # | phase | library module (new) | required outputs | refusal / failure codes |
| --- | --- | --- | --- | --- |
| 1 | input validation | `act/head_search_calibration_inputs.py` | validated manifest of sealed inputs + digests; admission decision (`role=calibration`); resource binding record | `CAL_INPUT_UNSEALED`, `CAL_ADMISSION_REFUSED`, `CAL_BINDING_REBOUND` |
| 2 | geometry + required-domain coverage | `act/head_search_calibration_geometry.py` | `horizontal_fov_rad`, `lock_valid_neck_rad`, **generated coarse-step candidates**, coverage proof over `required_search_domain_rad`, per-target sweep-check receipts | `CAL_DOMAIN_UNCOVERED`, `CAL_SWEEP_RECEIPT_MISSING` |
| 3 | perception operating point per candidate | `act/head_search_operating_point.py` | searched `min_confidence`, `tracking_iou`, `min_bbox_aspect`, `min_area_px2` per candidate, with the selection rule persisted **before** its measurement, on head val + calibration episodes; calibration/held-out isolation asserted | `CAL_RULE_AFTER_MEASUREMENT`, `CAL_SPLIT_LEAK`, `CAL_NO_CUP_FALSE_CANDIDATE` |
| 4 | frozen candidate evaluation and selection | `perception_benchmark/head_search_models.py` (exists) | comparison cells, scene-level intervals, `model-selection-verdict.json` | existing gate codes |
| 5 | selected perception values carried over | `act/head_search_calibration_readback.py` | readback proving the selected values entered the bundle **unmodified** (no digest of a later artefact: the readback compares against the candidate document and the rule record, both of phase 3/4) | `CAL_VALUE_MUTATED`, `CAL_SELECTION_MISMATCH` |
| 6 | search parameters | `act/head_search_search_params.py` | `coarse_step_rad` final value with the selected model's **val sweep/lock evidence**, `search_timeout_s`, `center_deadband_px`, `vertical_bounds_px`, `max_fine_corrections`, `max_fine_total_rad` | `CAL_SWEEP_UNSTABLE`, `CAL_TIMEOUT_UNBOUNDED`, `CAL_DEADBAND_OSCILLATES` |
| 7 | timing and stop parameters | `act/head_search_timing_params.py` | `max_age_s`, `max_skew_s`, `submit_lead_s`, `stop_velocity_rad_s`, `stop_latency_s` with measured distributions | `CAL_FRESHNESS_EXCEEDED`, `CAL_STOP_LATENCY_EXCEEDED` |
| 8 | bundle generation | `act/head_search_calibration_bundle.py` | `head-search-calibration-bundle.json` (17 values + evidence), `manifest.json`, `run-status.json`; **no approval state** | `CAL_BUNDLE_INCOMPLETE` |

**Approval is not phase 8.** Promotion is a separate command (`promote`) that consumes the bundle plus
`--approved-bundle-sha256` taken only from the user's approval message and writes `approval-receipt.json`
(design §8.3). Phase 8 must leave the bundle in a state that a later `promote` can verify byte-for-byte; it must not
record or assume approval.

## 3. Parameter to phase map (all 17)

| phase | parameters |
| --- | --- |
| 2 | `horizontal_fov_rad`, `lock_valid_neck_rad` |
| 3 (+5 readback) | `min_confidence`, `tracking_iou`, `min_bbox_aspect`, `min_area_px2` |
| 6 | `coarse_step_rad`, `search_timeout_s`, `center_deadband_px`, `vertical_bounds_px`, `max_fine_corrections`, `max_fine_total_rad` |
| 7 | `max_age_s`, `max_skew_s`, `submit_lead_s`, `stop_velocity_rad_s`, `stop_latency_s` |

## 4. Test strategy

Ordinary tests live in `src/so101_demo_py/test/` (the package gate must not collect `benchmark_test/`); the full suite
runs under `pytest-xdist` with `min(8, logical CPUs)` workers, with `TMPDIR` set inside the registered evidence root.
Required cases:

1. **Split isolation**: a calibration measurement that reads a held-out seed fails (`CAL_SPLIT_LEAK`); a rule written
   after its grid is measured fails (`CAL_RULE_AFTER_MEASUREMENT`).
2. **Formulas and bounds**: each of the 17 has a unit test asserting its documented formula and its stated bound
   (e.g. `max_age_s <= 1.5` frame periods, `max_skew_s <= 0.5` frame period) and the documented failure condition
   when the bound cannot be met.
3. **Fail-fast ordering**: injecting a failure into phase `n` leaves phases `n+1..8` unrun and the artefacts of
   phases `1..n-1` unchanged (`run-status.json` records the first failing phase).
4. **Failed-run immutability**: a failed run never overwrites or truncates a previous run's bundle, manifest or
   receipts; two runs in the same root are refused without `--run-root` pointing at a fresh directory.
5. **Contract enforcement**: an admission with any role other than `calibration` is refused; any release or recorder
   request is refused; a second resource binding raises `CAL_BINDING_REBOUND`; a neck target without its own
   sweep-check receipt raises `CAL_SWEEP_RECEIPT_MISSING`.
6. **Installed end-to-end**: the phases are exercised through the installed console script
   (`ros2 pkg prefix so101_demo_py` assertion first), not by importing the module from the source tree.
7. **Bundle determinism**: generating the bundle twice from identical inputs yields byte-identical output, and a
   promoted config whose digest differs from `APPROVED_BUNDLE_SHA256` is refused before any write.

## 5. Acceptance (plan Task 13, Steps 1-5)

1. **Step 1** guards pass, including `test -f "$MODEL_RUN/evaluation/model-selection-verdict.json"` and
   `test "$(ros2 pkg prefix so101_demo_py)" = "$TOOLCHAIN_RUN/install/so101_demo_py"`; the run is brand new
   (`test ! -e "$CAL_RUN"`).
2. **Step 2**: the approval pause presents the 17 values with units, formulas, distributions, margins, the selected
   model/camera/tracker identities and the first failure if any; nothing is modified during the pause.
3. **Step 3**: `promote` runs once with `APPROVED_BUNDLE_SHA256` taken only from the user's approval message, verifies
   byte-for-byte, and copies identities and values into `head_search_v2.json` without recomputing, rounding, clamping
   or substituting; the config edit is a single `apply_patch`.
4. **Step 4**: the promotion is **committed** and the two source-level affected gates are rerun (the package test gate
   and the source-level gate the plan names), with their exit codes recorded.
5. **Step 5**: the final frozen runtime is built from a **commit-stamped** fresh root, the installed gates pass
   (`prefix` and artefact checks), the run is recorded in the ledger with package, console script, model, CUDA,
   config, camera, tracker and web-bundle identities, and the Task 14 handoff names that root.

## 6. Already available - do not re-measure

- `horizontal_fov_rad`, `lock_valid_neck_rad`: measured by the Task 11 geometry campaign and sealed as
  `head-camera-geometry.json` (`7d963fdc…`).
- The selected perception point for the final model C2a: `min_confidence 0.25`, `tracker.iou 0.5`, chosen on
  calibration under a rule declared before measuring (HS-265, HS-276); the candidate documents were produced by the
  repository's `freeze_candidate` and accepted by the gate.
- The recorder's per-camera ground-truth semantics (HS-261) and the per-scene memoisation (HS-264): port into phases
  3/6 as library code; the campaign-root scripts are not an acceptable producer (rule 1).
