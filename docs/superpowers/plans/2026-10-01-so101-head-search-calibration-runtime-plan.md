# Head Search calibration runtime - implementation plan

Implements the eight `run` phases the design specifies (design §8.2) so that
`so101_head_search_calibration run` actually produces `head-search-calibration-bundle.json` with the 17 approved
parameters. Today the CLI writes only `run-receipt.json` and a 378-byte `calibration-state.json` (ledger HS-233).

## Hard rules carried from the design

1. **The installed program produces the values.** Design line 25 forbids generating the final parameters with ad-hoc
   scripts, so every number in the bundle must be computed by code merged into this repository and run through
   `ros2 run so101_demo_py so101_head_search_calibration run`.
2. **Architecture**: mathematics and policy live in independently testable library modules; the CLI only parses
   arguments, validates inputs and orchestrates phases.
3. **No `--resume`**; `run-status.json` is audit only, never a checkpoint. The result is `SUCCEEDED` or `FAILED`.
4. **No deadlock**: the first calibration must not call production Head Search entry points that require
   `TASK8_READY/QUALIFIED`.
5. Each of the 17 values must record value, unit, selection formula, input evidence and SHA256, observed
   distribution, safety margin, production owner and the startup readback that proves it took effect (design §7.1).

## Phase plan

| # | phase | library module (new) | output | reuses |
| --- | --- | --- | --- | --- |
| 1 | input validation | `act/head_search_calibration_inputs.py` | validated manifest of sealed inputs + digests | Task 11 geometry seal, dataset manifests, candidate `frozen-*.json` |
| 2 | geometry + coverage proof | `act/head_search_calibration_geometry.py` | `horizontal_fov_rad`, `lock_valid_neck_rad`, coverage proof for `required_search_domain_rad`, `coarse_step_rad` candidates | geometry seal values; the coverage-proof writer already used by `head_search_smoke` |
| 3 | per-candidate operating point | `act/head_search_operating_point.py` | searched `min_confidence`, `tracking_iou`, `min_bbox_aspect`, `min_area_px2` per candidate with the selection rule recorded before measuring | this campaign's grid + declared rule (HS-248/265), **moved from the campaign-root scripts into the module** |
| 4 | frozen candidate evaluation + selection | `perception_benchmark/head_search_models.py` (exists) | evaluation cells + `model-selection-verdict.json` | `evaluate_head_search_yolo_candidates compare` (exists, memoised) |
| 5 | selected-parameter readback | `act/head_search_calibration_readback.py` | proof the selected perception values are carried over unmodified | bundle digest + candidate identity |
| 6 | search parameters | `act/head_search_search_params.py` | `search_timeout_s`, `center_deadband_px`, `vertical_bounds_px`, `max_fine_corrections`, `max_fine_total_rad` | requires a bounded-sweep/fine-tune runtime |
| 7 | timing and stop parameters | `act/head_search_timing_params.py` | `max_age_s`, `max_skew_s`, `submit_lead_s`, `stop_velocity_rad_s`, `stop_latency_s` | requires the frame-freshness and stop/revoke paths |
| 8 | bundle generation | `act/head_search_calibration_bundle.py` | `head-search-calibration-bundle.json` + `manifest.json` + `run-status.json` | approval receipt writer (design §8.3) |

## Parameter to phase map (all 17)

| parameter | measured in phase |
| --- | --- |
| `horizontal_fov_rad`, `lock_valid_neck_rad`, `coarse_step_rad` | 2 |
| `min_confidence`, `tracking_iou`, `min_bbox_aspect`, `min_area_px2` | 3 (carried in 5) |
| `search_timeout_s`, `center_deadband_px`, `vertical_bounds_px`, `max_fine_corrections`, `max_fine_total_rad` | 6 |
| `max_age_s`, `max_skew_s`, `submit_lead_s`, `stop_velocity_rad_s`, `stop_latency_s` | 7 |

## Test strategy

- Library modules get ordinary unit tests in `src/so101_demo_py/test/` (the package gate must not collect
  `benchmark_test/`); the full suite runs under `pytest-xdist` with `min(8, logical CPUs)` workers.
- Phase 2 is testable against the sealed geometry root: the same inputs must reproduce the seal's values within the
  documented tolerance, and the coverage proof must fail closed when the required domain is not covered.
- Phase 3's rule must be unit-tested for "rule is recorded before measurement" (a rule written after the grid is a
  test failure, not a comment).
- Phases 6 and 7 need a runtime; their tests must assert the documented failure conditions (e.g. "raising the
  threshold instead of fixing the pipeline fails the phase").
- The bundle writer is tested for digest stability and for refusing a bundle whose approval message does not match
  `APPROVED_BUNDLE_SHA256` byte-for-byte.

## Acceptance (from the plan's Task 13)

1. Step 1's guards pass, including `test -f "$MODEL_RUN/evaluation/model-selection-verdict.json"`.
2. `run` completes with `SUCCEEDED` and produces the bundle with all 17 values plus evidence.
3. Step 2's approval pause presents the 17 values, units, formulas, distributions and margins; the bundle is not
   modified during the pause.
4. Step 3 promotes with `APPROVED_BUNDLE_SHA256` taken only from the user's approval message and verifies
   byte-for-byte; the config edit copies values and identities only, never recomputes or clamps.
5. Step 5 rebuilds the frozen runtime and the installed gates pass.

## What is already available (do not re-measure)

- `horizontal_fov_rad`, `lock_valid_neck_rad`: measured by the Task 11 geometry campaign, sealed as
  `head-camera-geometry.json` (`7d963fdc…`).
- The selected perception point for the final model (C2a): `min_confidence 0.25`, `tracker.iou 0.5`, chosen on
  calibration by a rule declared before measuring (ledger HS-265, HS-276).
- Frozen candidate documents produced by the repository's own `freeze_candidate`, accepted by the gate's
  `load_frozen_candidate`.
- A working recorder whose per-camera ground-truth semantics are documented (ledger HS-261) - to be ported into
  phase 3/6 rather than kept as a campaign-root script.
