# SO-101 ACT Task 8 MuJoCo measurement protocol implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the production MuJoCo measurement driver and deterministic measurement protocol required to create a genuine `TASK8_READY`, then rerun Task 8L from a new generation root and make Task 8P4 capable of producing a genuine 33-field `QUALIFIED` report.

**Architecture:** A calibration-only admission creates a generation-bound, single-flight context with less authority than production ACT. The driver records indexed raw evidence for three independent anchors; a pure offline aggregator verifies the sealed file closure and recomputes all 21 head-search fields, seven support fields, and phase-camera checks. Task 8P4 separately derives the five live-only fields from five FULL runs.

**Tech Stack:** Python 3, ROS 2 Jazzy/rclpy, MuJoCo, NumPy, OpenCV, Ultralytics/Torch CUDA, JSON/JSON Schema, pytest/xdist.

**Spec:** `docs/superpowers/specs/2026-09-29-so101-act-task8-measurement-protocol-design.md`

## Global constraints

- Work only in `/home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a`; preserve all existing dirty work.
- Execute with the existing ai-station `dst` goal. Do not start a second writer, Codex session, ROS stack, or MuJoCo stack.
- Use MuJoCo only. Do not add or invoke Gazebo support.
- CUDA is required for detector execution; no CPU fallback.
- Campaign resource binding occurs once at the calibration or Task 8 launch entry, not in internal components.
- Keep generation-scoped, single-flight cleanup. A stale generation may not clean a newer generation.
- Do not run W4 or W6. After W2, the only scale target is independent exact-W8 over 40 scenes.
- Stop for human decision on CPU, GPU, RAM, disk, MuJoCo RTF, recorder queue, 10 Hz continuity, throughput, or QC bottlenecks. Do not lower thresholds or worker count.
- Registered evidence root is `/data/work/so101-evidence/act-data/20260924-fbc25063-resume`; do not move or delete it.
- Every ai-station pytest/colcon run that creates fsync-heavy fixtures must use a new nonexistent scratch directory below that evidence root, set `TMPDIR/TMP/TEMP`, and verify `tempfile.gettempdir()` with the exact Python executable before running.
- Keep ordinary low-rate logs in a unique `/tmp/so101-debug-<task-id>/`; never write `/data/work/so101-debug-*`.
- Use targeted RED/GREEN tests for Tasks 1 through 8. Run the full xdist/package gate only at Task 9.
- Any controlled source, config, policy, contract, or phase-camera matrix change invalidates older Task 8L bundles and live qualification for the new identity.
- Do not push, delete evidence, or execute a real SO-101.

## File structure

Create focused modules instead of adding runtime logic to the CLI:

- `src/so101_demo_py/src/act/task8_measurement_schema.py`: closed schemas, identity, indexed file closure, immutable writers.
- `src/so101_demo_py/src/act/task8_measurement_formulas.py`: pure formulas for the 21 plus seven pre-live fields.
- `src/so101_demo_py/src/act/task8_phase_camera.py`: replay/live coverage matrix, projection, visibility, occluder ownership.
- `src/so101_demo_py/src/act/task8_calibration_admission.py`: calibration-only context and command authorization.
- `src/so101_demo_py/src/adapters/act/task8_calibration_search_binding.py`: owner=`calibration` dynamic neck command adapter.
- `src/so101_demo_py/src/act/task8_measurement_driver.py`: three-anchor raw acquisition orchestration and invalid sealing.
- `src/so101_demo_py/src/act/task8_calibration_aggregator.py`: pure offline orchestration only; delegate formulas and schemas.
- `src/so101_demo_py/src/act/task8_live_qualification.py`: five live-only formulas and 33-field qualification.
- `src/so101_demo_py/src/cli/act_measure_task8_calibration.py`: launch-entry binding and production driver selection.
- `src/so101_demo_py/config/act/task8-calibration-measurement-contract-v2.json`: units, sources, comparators, formula IDs, thresholds, windows, failure codes.
- `src/so101_demo_py/config/act/task8-calibration-measurement-contract-schema.json`: v2 schema.
- `src/so101_demo_py/config/act/task8-calibration-search-candidate-v1.json`: frozen 17 search values and three anchor starts.
- `src/so101_demo_py/config/act/task8-calibration-search-policy-v1.json`: frozen state-machine and generation rules.
- `src/so101_demo_py/config/act/task8-phase-camera-matrix-v1.json`: nine phases, cameras, constants, exact visual occluder names.

---

### Task 1: Freeze contract v2, controlled inputs, and closed schemas

**Files:**
- Create: `src/so101_demo_py/src/act/task8_measurement_schema.py`
- Create: `src/so101_demo_py/config/act/task8-calibration-measurement-contract-v2.json`
- Create: `src/so101_demo_py/config/act/task8-calibration-search-candidate-v1.json`
- Create: `src/so101_demo_py/config/act/task8-calibration-search-policy-v1.json`
- Create: `src/so101_demo_py/config/act/task8-phase-camera-matrix-v1.json`
- Modify: `src/so101_demo_py/config/act/task8-calibration-measurement-contract-schema.json`
- Modify: `src/so101_demo_py/src/act/task8_measurement_contract.py`
- Modify: `src/so101_demo_py/test/test_act_task8_measurement_contract.py`

**Interfaces:**
- Produces: `MeasurementIdentity`, `BatchIndex`, `validate_closed_batch(root, contract)`, `write_closed_json(path, document, schema)`, `bind_measurement_contract(...)`.
- Consumes: canonical SHA256 helpers and existing source/runtime/contact/ACT identities.

- [ ] **Step 1: Write failing schema and closure tests**

Add parameterized tests proving v2 contains exactly 21 head/search fields and seven support fields with the units from `calibration.py`; bind all ten identity members; reject missing/unindexed/extra/symlink files; and reject a matrix whose exact occluder list differs from:

```python
EXPECTED_OCCLUDERS = [
    "fixed_fingertip_pad_visual",
    "gripper_visual_00",
    "gripper_visual_01",
    "jaw_visual_00",
    "moving_fingertip_pad_visual",
]
```

- [ ] **Step 2: Run the focused RED test**

Run: `python -m pytest -q src/so101_demo_py/test/test_act_task8_measurement_contract.py`

Expected: FAIL because contract v2 and closed schema helpers do not exist. Record command, exit code, elapsed time, and scratch path when the fixture is fsync-heavy.

- [ ] **Step 3: Implement immutable schema and contract binding**

Use frozen dataclasses or `MappingProxyType` at the public boundary. `validate_closed_batch()` must compare the recursive regular-file set to `batch.json.files` before any raw file is opened, reject path traversal and links, verify every digest, then return a validated identity plus indexed paths. Candidate, policy, matrix, driver source, model, runtime, and source provenance digests must be in the bound contract.

- [ ] **Step 4: Run GREEN and commit**

Run the same test; expected PASS. Then:

```bash
git add src/so101_demo_py/src/act/task8_measurement_schema.py \
  src/so101_demo_py/src/act/task8_measurement_contract.py \
  src/so101_demo_py/config/act/task8-calibration-measurement-contract-schema.json \
  src/so101_demo_py/config/act/task8-calibration-measurement-contract-v2.json \
  src/so101_demo_py/config/act/task8-calibration-search-candidate-v1.json \
  src/so101_demo_py/config/act/task8-calibration-search-policy-v1.json \
  src/so101_demo_py/config/act/task8-phase-camera-matrix-v1.json \
  src/so101_demo_py/test/test_act_task8_measurement_contract.py
git commit -m "feat(act): freeze task8 measurement protocol v2"
```

### Task 2: Implement pure 21-field and seven-field formulas

**Files:**
- Create: `src/so101_demo_py/src/act/task8_measurement_formulas.py`
- Create: `src/so101_demo_py/test/test_act_task8_measurement_formulas.py`
- Modify: `src/so101_demo_py/src/act/task8_calibration_aggregator.py`

**Interfaces:**
- Produces: `compute_head_search_fields(raw, contract) -> FieldResultSet`, `compute_support_fields(raw, contract) -> FieldResultSet`, `build_head_closed_sample(...)`, `build_support_closed_sample(...)`.
- Consumes: only already validated indexed records; no filesystem guessing and no runtime imports.

- [ ] **Step 1: Write table-driven RED tests for every formula**

For each of the 21 fields and seven support fields, provide one exact boundary-pass case and one single-point violation. Include coarse accumulator reissue, timeout beginning at `SEARCH_STARTED/advance_deadline`, circular yaw, continuous-neck component selection, three-sample stop proof, non-positive `dt`, quaternion norm, CameraInfo tolerance, and sample units `1`/`px^2`.

- [ ] **Step 2: Add adversarial sample-shape tests**

Assert the head closed sample has exactly:

```python
{
    "schema_version", "kind", "status", "head_search",
    "observed_lock_frames", "measurements", "camera_measurements",
    "source_commit", "config_sha256", "source_provenance_sha256",
}
```

Assert its measurement maps contain bare values, while report entries contain exactly `value/unit/sample_path/sample_sha256`. Reject raw `qualified`, `target_in_view`, `contact_ok`, or `*_ok` labels as formula inputs.

- [ ] **Step 3: Run RED, implement pure formulas, run GREEN**

Run: `python -m pytest -q src/so101_demo_py/test/test_act_task8_measurement_formulas.py src/so101_demo_py/test/test_act_task8_calibration_aggregator.py`

Expected RED: missing formula module. Implement with explicit formula IDs matching v2 and return per-field configured limit, observed summary, reported value, and raw refs for the aggregation receipt. Rerun; expected PASS.

- [ ] **Step 4: Commit**

```bash
git add src/so101_demo_py/src/act/task8_measurement_formulas.py \
  src/so101_demo_py/src/act/task8_calibration_aggregator.py \
  src/so101_demo_py/test/test_act_task8_measurement_formulas.py \
  src/so101_demo_py/test/test_act_task8_calibration_aggregator.py
git commit -m "feat(act): derive task8 calibration fields from raw evidence"
```

### Task 3: Implement phase-camera replay and live coverage

**Files:**
- Create: `src/so101_demo_py/src/act/task8_phase_camera.py`
- Create: `src/so101_demo_py/test/test_act_task8_phase_camera.py`
- Modify: `src/so101_demo_py/src/act/task8_calibration_aggregator.py`

**Interfaces:**
- Produces: `evaluate_replay_coverage(rows, matrix)`, `evaluate_live_continuity(frames, window_kind, matrix)`, `rasterize_cup_projection(...)`.
- Consumes: 2 ms replay rows separately from 10 Hz calibration-live or Task8-live rows.

- [ ] **Step 1: Write RED tests for time-axis separation and all nine phases**

Require matrix entries for SEARCH through FINAL_CHECK and both observation cameras. Reject stitching replay rows into live continuity, crossing session/reset/attempt, a 100 ms source gap, wrong group owner, out-of-frame fraction below `0.98`, visible fraction below `0.80`, and bbox center outside `[4,635]x[4,475]`.

- [ ] **Step 2: Write projection/occlusion RED tests**

Cover near-plane clipping, far/behind rejection, top-left fill, zero denominator, depth margin exactly `1e-6 m`, the five allowed group-0 visual geoms, and rejection of `table_visual`, collision geom, background, and unknown owner.

- [ ] **Step 3: Implement and run GREEN**

Keep projection/raster functions deterministic and free of ROS. A replay result may satisfy geometric feasibility but must never return live-continuity success. Run the focused test and aggregator test; expected PASS.

- [ ] **Step 4: Commit**

```bash
git add src/so101_demo_py/src/act/task8_phase_camera.py \
  src/so101_demo_py/src/act/task8_calibration_aggregator.py \
  src/so101_demo_py/test/test_act_task8_phase_camera.py
git commit -m "feat(act): enforce task8 phase camera coverage"
```

### Task 4: Add calibration admission and dynamic neck search binding

**Files:**
- Create: `src/so101_demo_py/src/act/task8_calibration_admission.py`
- Create: `src/so101_demo_py/src/adapters/act/task8_calibration_search_binding.py`
- Create: `src/so101_demo_py/test/test_act_task8_calibration_admission.py`
- Modify: `src/so101_demo_py/src/act/ownership.py`
- Modify: `src/so101_demo_py/src/adapters/act/command_broker.py`
- Modify: `src/so101_demo_py/src/cli/act_command_broker.py`
- Modify: `src/so101_demo_py/src/runtime/launch_composition.py`
- Modify: `src/so101_demo_py/test/test_act_control_event_timeline.py`
- Modify: `src/so101_demo_py/test/test_act_task8_search_binding.py`

**Interfaces:**
- Produces: `CalibrationMeasurementContext`, `CalibrationMeasurementAdmission.admit(...)`, `CalibrationSearchBinding.authorize_neck_target(...)`.
- Consumes: contract v2, candidate/policy hashes, broker lease, controller generation, `MujocoNeckSweepChecker`.

- [ ] **Step 1: Write authority RED tests**

Prove `CALIBRATION_REQUIRED` can admit exactly one calibration generation while production child remains rejected. Exercise the real `Ownership` and `CommandBroker` acquire to bounded-submit to stop to retire sequence. Prove arm commands must byte-match `measurement_plan_sha256`; neck targets may be dynamic only when uniquely derived from policy state, inside safe interval, and independently sweep-safe. Reject release, Recorder, unknown operations, second flight, stale generation, target outside interval, an ACT-owner forgery, and a caller that bypasses `CalibrationSearchBinding` and submits directly to the broker.

- [ ] **Step 2: Write state-machine RED tests**

Test coarse accumulator advances only on a new target; reissue does not advance; fine corrections are separate; timeout starts at the first advance deadline; and the first target beyond safe interval terminates without submitting a command as `TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL`.

- [ ] **Step 3: Implement minimal admission and composition adapter**

Extend `Ownership` with the explicit `calibration` role and a restricted capability set. Add broker-side enforcement so the role can submit only a byte-matching arm probe or a command receipt signed by the bound calibration search adapter. Wire the reservation and owner factory through launch composition; do not reuse the generic non-ACT submit path. Do not change the production `owner=act` binding semantics. Every acquire, state, command, feedback, stop, retire, and cleanup event must carry the admission generation. Resource binding remains in the CLI entry and is passed through the context.

- [ ] **Step 4: Run GREEN and commit**

Run the two focused test files plus existing child-port tests. Expected PASS.

```bash
git add src/so101_demo_py/src/act/task8_calibration_admission.py \
  src/so101_demo_py/src/adapters/act/task8_calibration_search_binding.py \
  src/so101_demo_py/src/act/ownership.py \
  src/so101_demo_py/src/adapters/act/command_broker.py \
  src/so101_demo_py/src/cli/act_command_broker.py \
  src/so101_demo_py/src/runtime/launch_composition.py \
  src/so101_demo_py/test/test_act_task8_calibration_admission.py \
  src/so101_demo_py/test/test_act_control_event_timeline.py \
  src/so101_demo_py/test/test_act_task8_search_binding.py
git commit -m "feat(act): admit bounded task8 calibration measurements"
```

### Task 5: Build the production MuJoCo measurement driver

**Files:**
- Create: `src/so101_demo_py/src/act/task8_measurement_driver.py`
- Create: `src/so101_demo_py/test/test_act_task8_measurement_driver.py`
- Modify: `src/so101_demo_py/src/cli/act_measure_task8_calibration.py`
- Modify: `src/so101_demo_py/setup.py`

**Interfaces:**
- Produces: `Task8MujocoMeasurementDriver.run(context, output_root) -> Path` returning only a sealed `CLOSED` or `INVALID` batch path.
- Consumes: admitted context, exactly one stack, raw camera/detector/TF/controller/MuJoCo writers, private replay, cleanup state machine.

- [ ] **Step 1: Replace the temporary-driver assumption with RED tests**

Test that the CLI defaults to the production driver and optional injection is test-only. A valid run must execute default/left/forward in order, with a different FULL_RESTART session/reset/attempt for each. A failure in any anchor must stop later anchors, run cleanup once for the current generation, and seal `INVALID` without a report.

- [ ] **Step 2: Test raw-only behavior**

Assert no driver output contains PASS/FAIL, `qualified`, `visible`, `target_in_view`, `contact_ok`, or execution `*_ok`. Assert every frame/index row carries source stamp, receive monotonic time, session, reset epoch, attempt, physics step, relative payload path, digest, encoding, and shape.

- [ ] **Step 3: Implement the orchestration**

For each anchor: launch/verify unique MuJoCo stack; reset; collect ten geometry samples; run private nine-phase replay at 2 ms; run live search; run the fixed non-contact arm probe; stop and generation-scoped single-flight cleanup; close the stack before the next anchor. Register every regular file before sealing. On exception, preserve raw outputs and error code, clean up, and seal INVALID.

- [ ] **Step 4: Run focused component tests and commit**

Use fakes for ROS, detector, controller, and MuJoCo; do not launch a second real stack in unit tests.

```bash
git add src/so101_demo_py/src/act/task8_measurement_driver.py \
  src/so101_demo_py/src/cli/act_measure_task8_calibration.py \
  src/so101_demo_py/setup.py \
  src/so101_demo_py/test/test_act_task8_measurement_driver.py
git commit -m "feat(act): add production mujoco task8 measurement driver"
```

### Task 6: Close the deterministic offline aggregator

**Files:**
- Modify: `src/so101_demo_py/src/act/task8_calibration_aggregator.py`
- Modify: `src/so101_demo_py/src/cli/act_build_task8_calibration_report.py`
- Modify: `src/so101_demo_py/test/test_act_task8_calibration_aggregator.py`
- Modify: `src/so101_demo_py/test/test_act_calibration.py`

**Interfaces:**
- Produces: `render_task8_calibration(batch_root: Path, contract: Mapping, publication_root: Path) -> Mapping[str, bytes]` and `publish_task8_calibration(rendered: Mapping[str, bytes], publication_root: Path) -> Mapping`.
- Consumes: one v2 sealed batch containing exactly three anchors, formula and phase-camera results.

- [ ] **Step 1: Write RED regression tests against the old aggregator**

Reject `roots[0]`, multiple unrelated roots, unindexed reads, mixed identities, malformed closed sample, fake lock labels, cleanup contamination, time reversal, and missing anchor. Verify raw label mutation does not change the result, while raw number/mask mutation fails the digest or recomputation.

- [ ] **Step 2: Implement one-root deterministic aggregation**

The pure render function emits canonical bytes for exactly `head-search-qualification.json`, `task8-ready-support.json`, `task8-ready-calibration.json`, and `aggregation-receipt.json`. It serializes `sample_path` against one caller-supplied absolute `publication_root`, independent of any staging directory. The publish function writes those bytes atomically to that exact root. The receipt owns field audit details. After publishing, run `require_gate(report, "task8_live")` and `validate_head_search_binding(runtime, report)` against the files that now exist.

- [ ] **Step 3: Verify byte determinism and GREEN**

Call the pure render function twice for the same immutable fixture and the same canonical `publication_root`, without publishing either result. Compare all four byte values; expected identical. Publish one rendered map to that root, verify every absolute `sample_path` exists and matches `sample_sha256`, then run the production validators. Do not use different output roots for this comparison, and do not weaken the absolute-path contract. Run focused calibration, head binding, contract, formula, phase-camera, driver, and aggregator tests; expected PASS.

- [ ] **Step 4: Commit**

```bash
git add src/so101_demo_py/src/act/task8_calibration_aggregator.py \
  src/so101_demo_py/src/cli/act_build_task8_calibration_report.py \
  src/so101_demo_py/test/test_act_task8_calibration_aggregator.py \
  src/so101_demo_py/test/test_act_calibration.py
git commit -m "fix(act): make task8 calibration aggregation deterministic"
```

### Task 7: Extend the Task 8 live raw-evidence producer

**Files:**
- Modify: `src/so101_demo_py/src/act/task8_live_evidence.py`
- Modify: `src/so101_demo_py/config/act/task8-live-evidence-schema.json`
- Modify: `src/so101_demo_py/src/act/pick_place_runner.py`
- Modify: `src/so101_demo_py/src/adapters/act/pick_place_child_port.py`
- Modify: `src/so101_teleop/so101_teleop/unified/ros_child.py`
- Modify: `src/so101_teleop/so101_teleop/unified/pick_place_case_execution.py`
- Modify: `src/so101_teleop/so101_teleop/unified/pick_place_case_owner.py`
- Modify: `src/so101_demo_py/test/test_act_task8_live_evidence.py`
- Modify: `src/so101_teleop/test/teleop/test_task8_case_execution.py`
- Create: `src/so101_teleop/test/teleop/test_task8_live_evidence_production_chain.py`

**Interfaces:**
- Produces: a sealed, indexed per-FULL evidence root whose `LiveEvidenceWindow.REQUIRED_PHASES` is exactly SEARCH through FINAL_CHECK and whose rows carry both observation cameras, segmentation/depth owners, controller/open events, exact contact pairs, pose, velocity, phase, and causal timestamps. The real `ros_child._run_pick_place()` to `PickPlaceRunner` to `pick_place_case_execution.run_pick_place_case()` chain returns and journals that artifact.
- Consumes: the existing case owner, child startup proof, production child port/readback, live campaign identity, phase-camera matrix, and single launch-entry resource binding.

- [ ] **Step 1: Write producer/schema RED tests for all nine phases**

Assert the required phase tuple is `SEARCH, APPROACH, CLOSE, MICRO_LIFT, TRANSPORT, ALIGN, RELEASE, RADIAL_RETREAT, FINAL_CHECK`. For every 10 Hz row require head/wrist RGB refs, CameraInfo, segmentation/depth refs, joint/TF/reference/physics receipts, session/reset/attempt, phase, source and receive timestamps, and file digests. Task camera remains audit-only and may not appear in ACT observations.

- [ ] **Step 2: Write release-correlation and closure RED tests**

Create a producer fixture with `bottom_collision`/`table_collision` signed distance and active-contact records, cup pose/velocity, and a controller event carrying the first gripper-open command in the same release epoch. Require the three immediately preceding rows to be consecutive at 10 Hz. Reject an open event from another epoch, a missing raw ref, an unindexed image/mask, and any summary-only substitute.

- [ ] **Step 3: Wire recorder and owner composition**

Provision the recorder through the real `PickPlaceCaseOwner` and child startup receipt. `ros_child._run_pick_place()` binds it to the real child port before constructing `PickPlaceRunner`; the runner opens the window at SEARCH, records each verified phase and the first gripper-open controller event, and seals only after FINAL_CHECK. `pick_place_case_execution.run_pick_place_case()` reads back the returned `live_evidence_artifact` before publishing its journal row. Internal recorder components consume the existing context without acquiring campaign resources again. On failure, the child closes or invalid-seals the window before owner retirement.

- [ ] **Step 4: Run focused producer/composition tests and commit**

The new production-chain component test must keep `run_pick_place_case()`, owner start/finish, child `_run_pick_place()`, `PickPlaceRunner`, artifact validation, and journal publication real. Replace only external ROS topics, MuJoCo/controller I/O, and process launch with deterministic fakes. It must observe SEARCH rows, the release open event and three pre-open support rows, FINAL_CHECK, sealed artifact readback, confirmed retirement, and the final journal path/hash.

Run: `python -m pytest -q src/so101_demo_py/test/test_act_task8_live_evidence.py src/so101_teleop/test/teleop/test_task8_case_execution.py src/so101_teleop/test/teleop/test_task8_live_evidence_production_chain.py`

Expected: PASS.

```bash
git add src/so101_demo_py/src/act/task8_live_evidence.py \
  src/so101_demo_py/config/act/task8-live-evidence-schema.json \
  src/so101_demo_py/src/act/pick_place_runner.py \
  src/so101_demo_py/src/adapters/act/pick_place_child_port.py \
  src/so101_teleop/so101_teleop/unified/ros_child.py \
  src/so101_teleop/so101_teleop/unified/pick_place_case_execution.py \
  src/so101_teleop/so101_teleop/unified/pick_place_case_owner.py \
  src/so101_demo_py/test/test_act_task8_live_evidence.py \
  src/so101_teleop/test/teleop/test_task8_case_execution.py \
  src/so101_teleop/test/teleop/test_task8_live_evidence_production_chain.py
git commit -m "feat(act): record complete task8 live evidence"
```

### Task 8: Produce the five live-only fields in Task 8P4

**Files:**
- Modify: `src/so101_demo_py/src/act/task8_live_qualification.py`
- Modify: `src/so101_demo_py/test/test_act_task8_live_qualification.py`

**Interfaces:**
- Produces: `derive_live_measurements(full_runs, contract) -> Mapping`, `build_task8_qualified_report(...)` returning an immutable 33-field report.
- Consumes: five sealed independent FULL roots produced by Task 7 plus the 28-field ready report.

- [ ] **Step 1: Write five-field RED tests**

Test extrema direction across five runs: occlusion max, support-distance max, release-stable min, retreat-distance min, placement-stable min. For support distance require the three consecutive 10 Hz samples immediately before first open in the same release epoch, exact `bottom_collision`/`table_collision` active contact, stable pose/velocity, and `max(0,d_signed)`.

- [ ] **Step 2: Write qualification rejection tests**

Reject missing live fields, mixed identity/policy/matrix, a summary without sealed sample path/hash, an allowed distance without real contact, discontinuous frame stamps, or any report that has not passed `require_qualified()`.

- [ ] **Step 3: Implement immutable report generation and GREEN**

Copy the 28 ready measurements by value, add exactly five newly derived entries, recompute checks, write a new report, then perform readback and call `require_qualified(report)`. Never mutate the ready report in place.

- [ ] **Step 4: Commit**

```bash
git add src/so101_demo_py/src/act/task8_live_qualification.py \
  src/so101_demo_py/test/test_act_task8_live_qualification.py
git commit -m "feat(act): derive task8 live qualification measurements"
```

### Task 9: Run the single full integration gate and implementation review

**Files:**
- Modify only files required by concrete gate failures; record each change and rerun its focused test first.
- Update: `docs/experiments/so101-act-data-experiment-ledger.md`

**Interfaces:**
- Produces: one implementation review packet with commit range, diff, targeted results, full gate result, scratch path, and cleanup/deletion-candidate classification.

- [ ] **Step 1: Create and verify a fresh NVMe scratch**

Choose a never-used path under:

```text
/data/work/so101-evidence/act-data/20260924-fbc25063-resume/scratch/task8-measurement-v2-<UTC>/tmp
```

Set `TMPDIR`, `TMP`, and `TEMP` to it. With the exact test Python executable, assert `tempfile.gettempdir()` equals that path. Fail closed if it does not.

- [ ] **Step 2: Run the planned full package gate once**

Run the repository-approved ordinary package gates for both `so101_demo_py` and `so101_teleop` with xdist, excluding `benchmark_test/`. This is one integration boundary even if the package commands run sequentially. Enable `set -o pipefail` when using `tee`, record each actual exit code and elapsed time, and keep both logs in the registered evidence root. Expected: zero failures in both packages.

- [ ] **Step 3: Request independent implementation review**

Provide the exact diff from the first Task 1 commit through HEAD, test logs, scratch path, and spec/plan hashes. Address only evidence-backed findings; after a correction, run its focused test. Rerun the full gate only if the correction crosses the package integration boundary.

- [ ] **Step 4: Record the checkpoint**

Append the implementation review verdict, commit SHA, test counts, command exit codes, retained evidence, scratch deletion candidate, and explicit statement that no live action has occurred. Commit the ledger checkpoint separately.

### Task 10: Rebuild Task 8L from a new generation subroot

**Files:**
- Update: `docs/experiments/so101-act-data-experiment-ledger.md`
- Runtime evidence only below the registered root; no generated evidence is added to Git.

**Interfaces:**
- Produces: a new generation containing source provenance, five identities, bound contract v2, raw three-anchor batch, aggregation receipt, 28-field `TASK8_READY`, and readback evidence.

- [ ] **Step 1: Allocate the generation without reuse**

Use `runtime-task8l-gen4/` only if it does not exist. If any filesystem entry already has that name, allocate the next integer generation. Record the chosen absolute subroot before writing. Never copy gen3 provenance, identity, contract, bundle, or measurement outputs.

- [ ] **Step 2: Rebuild provenance and binding from current controlled inputs**

Generate source provenance, the five required identities, candidate/policy/matrix hashes, driver source hash, and bound contract v2. Read every artifact back and verify its digest against the generation identity before starting MuJoCo.

- [ ] **Step 3: Run the production measurement driver**

Use the single authorized MuJoCo stack and CUDA detector. Execute default, left, and forward anchors as separate FULL_RESTARTs. If any resource bottleneck appears, stop, seal INVALID when possible, preserve evidence, leave the goal blocked, and report the exact metric/path for human decision.

- [ ] **Step 4: Aggregate and perform production readback**

Only a sealed CLOSED batch may be aggregated. Choose one new canonical publication root inside the new generation. Render twice with that same absolute publication identity and compare the four byte maps before writing. Publish one map atomically, then verify every absolute `sample_path` and digest before calling `require_gate(report, "task8_live")` and `validate_head_search_binding()`. A byte mismatch or readback failure blocks Task 8L; do not render against a second publication root.

- [ ] **Step 5: Complete the Task 8L checkpoint**

Record the new generation, hashes, three anchor identities, field/check outcomes, retained/invalid batches, and deletion candidates. Do not claim Task 8 live or training complete. Resume the existing goal only into the next already-approved Task 8 boundary after the checkpoint is reviewed.

## Completion gate

The plan is complete only when all ten tasks are checked, the implementation review passes, and a new-generation Task 8L report passes both production readbacks. `runtime-task8l-gen3` remains retained and ineligible. Task 8 live, five FULL runs, `QUALIFIED`, exact-W8 40-scene execution, collection, and training remain later gates; they are not implied by Task 8L completion.
