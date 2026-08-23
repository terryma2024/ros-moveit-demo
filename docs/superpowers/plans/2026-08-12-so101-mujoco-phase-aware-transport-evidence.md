# SO-101 MuJoCo Phase-Aware Transport Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a disabled, exact-hash schema-v4 proposal from five independent FULL_RESTART
dynamic-transport runs while preserving the successful five-win behavior exactly.

**Architecture:** The MuJoCo plugin records every 2 ms physics step into continuous lossless chunks
and latches the first `>=11.60 N` hazard. Python adds typed static-versus-dynamic force handling,
durable raw chunk recording, pure metric analysis, schema-v4 proposal generation, and semantic
verification against a pre-change frozen-behavior manifest. The existing motion targets and normal
execution path do not change.

**Tech Stack:** C++17, MuJoCo, ROS 2 Jazzy, rosidl, realtime_tools, Python 3.12, rclpy, PyYAML,
pytest, GoogleTest, Ruff, ament/colcon, SHA-256 JSON artifacts.

## Global Constraints

- Work only in `/data/work/ws_moveit/.worktrees/so101-mujoco-ros2` on
  `codex/so101-mujoco-ros2-teleop`; never SSH to `ai-station`.
- Freeze seating preload `q6=-0.04850794875050089` and every waypoint, trajectory input, planner,
  planning time, velocity/acceleration scaling, initial state, MJCF, scene, geometry, controller,
  phase order, and normal execution semantic.
- Static `maximum_safe_force_n=1.1579004532160448` remains a hard gate only in
  `PRE_TRANSPORT_STATIC_HOLD`.
- From waypoint 1 goal dispatch through transport outcome, `1.1579004532160448 N` is shadow-only.
- Dynamic diagnostic hazard is `global_max_single_contact_force_n >= 11.60`; no grace period.
- Do not generate a dynamic acceptance threshold; dynamic results use
  `acceptance_role: diagnostic_only`.
- Do not edit `src/so101_gazebo_demo_py`.
- Preserve and never stage the two unrelated untracked experiment documents named in the ledger.
- Do not use `ament_uncrustify --reformat`; only read-only checks and targeted patches are allowed.
- Do not enter Project B/C/D, formal nine-stage regression, RESET_WORLD five-win, merge, or push.
- Stop immediately after creating the disabled exact-hash proposal and ledger state
  `USER_APPROVAL_REQUIRED`.

## File structure

- `docs/experiments/so101-mujoco-phase-aware-frozen-behavior-manifest.json`: canonical pre-change
  behavior inputs and semantic contracts.
- `docs/experiments/so101-mujoco-phase-aware-frozen-behavior-manifest.sha256`: exact manifest hash.
- `src/so101_mujoco_support/msg/PhysicsStepEvidence.msg`: one raw physics-step sample.
- `src/so101_mujoco_support/msg/PhysicsStepEvidenceChunk.msg`: continuous step-range transport.
- `src/so101_mujoco_support/msg/PhysicsHazardLatch.msg`: first-breach notification and identity.
- `src/so101_mujoco_support/{include,src}/simulation_evidence_plugin.*`: per-step accumulation,
  loss detection, chunk publication, and non-overwritable hazard latch.
- `src/so101_mujoco_demo_py/so101_mujoco_demo_py/dynamic_transport_evidence.py`: typed phase events,
  durable chunk store, validity checks, and pure diagnostic analyzer.
- `src/so101_mujoco_demo_py/so101_mujoco_demo_py/mujoco/transport_observer.py`: rclpy adapter for
  chunks and hazard notifications.
- `src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_phases/transport.py`: minimum typed wiring at
  the pre-hold/goal-dispatch/post-settle boundary; no motion-input changes.
- `src/so101_mujoco_demo_py/so101_mujoco_demo_py/contact_calibration.py`: schema-v4 disabled proposal
  validation and deterministic generation while retaining v1-v3 read compatibility.
- `src/so101_mujoco_demo_py/so101_mujoco_demo_py/contact_calibration_collector.py`: exact raw
  per-step serialization shared by live dynamic recording.
- `src/so101_mujoco_demo_py/so101_mujoco_demo_py/frozen_behavior.py`: semantic manifest verifier.
- C++ and Python test files beside their owning boundaries.

---

### Task 1: Commit the approved documents and frozen-behavior manifest

**Files:**
- Create: `docs/superpowers/specs/2026-08-12-so101-mujoco-phase-aware-transport-evidence-design.md`
- Create: `docs/superpowers/plans/2026-08-12-so101-mujoco-phase-aware-transport-evidence.md`
- Create: `docs/experiments/so101-mujoco-phase-aware-frozen-behavior-manifest.json`
- Create: `docs/experiments/so101-mujoco-phase-aware-frozen-behavior-manifest.sha256`
- Modify: `docs/superpowers/specs/2026-08-12-so101-mujoco-maintainability-remediation-design.md`
- Modify: `docs/experiments/so101-mujoco-maintainability-remediation-experiment-ledger.md`

**Interfaces:**
- Consumes: behavior baseline `8f71442`, EXP-109, current file hashes, and the approved review text.
- Produces: immutable Project-A measurement design, this execution plan, `MNT-CP-015`, and the
  canonical manifest hash used by all later gates.

- [ ] **Step 1: Verify the manifest binds the reviewed baseline**

Run:

```zsh
sha256sum \
  src/so101_mujoco_demo_py/config/motion_policies/light_cup_wall_pick.yaml \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_phases/grasp_strategy.py \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_phases/transport.py \
  src/so101_mujoco_demo_py/mjcf/scene.xml \
  src/so101_mujoco_demo_py/mjcf/so101.xml
git diff --quiet -- src/so101_gazebo_demo_py
```

Expected hashes are `aa83a43c...`, `8ae37f96...`, `d2edcb46...`, `b98eca6f...`, and
`f87a033f...`; protected-tree diff exits zero.

- [ ] **Step 2: Self-review the documents**

Run:

```zsh
rg -n 'T[B]D|T[O]DO|implement[ ]later|fill[ ]in' \
  docs/superpowers/specs/2026-08-12-so101-mujoco-phase-aware-transport-evidence-design.md \
  docs/superpowers/plans/2026-08-12-so101-mujoco-phase-aware-transport-evidence.md
git diff --check
```

Expected: no placeholder match and no whitespace error.

- [ ] **Step 3: Commit only the document checkpoint**

Run `git status --short`, explicitly exclude the two protected untracked documents, stage the six
files listed in this task, and commit:

```zsh
git commit -m "docs(so101_mujoco): freeze phase-aware evidence design"
```

Expected: no source/config file in the commit and no runtime process started.

---

### Task 2: Preregister the implementation and five independent runs

**Files:**
- Modify: `docs/experiments/so101-mujoco-maintainability-remediation-experiment-ledger.md`

**Interfaces:**
- Consumes: MNT-CP-015 and frozen manifest SHA-256.
- Produces: one implementation-validation record and `EXP-110` through `EXP-114` as separate
  `PLANNED` FULL_RESTART entries referencing EXP-109.

- [ ] **Step 1: Record the sole implementation hypothesis**

Append a planned record stating that only the evidence boundary and typed threshold interpretation
change. Freeze the predictions: a 500 Hz spike survives 100 Hz publishing, all physics steps are
continuous, static pre-hold still fails closed, dynamic shadow crossing does not cancel, and the
behavior manifest remains equal.

- [ ] **Step 2: Register five run records before any stack**

For each of EXP-110..EXP-114 record:

```yaml
status: PLANNED
prior_experiment: EXP-109
single_variable: independent FULL_RESTART run identity; behavior and instrumentation commit fixed
lifecycle: FULL_RESTART
qualification_counting: false
```

Runs 110..113 are descriptive repeats; EXP-114 is the preregistered replication. Record that
experiment `status: VALID` plus `outcome_class: VALID_SAFETY_ABORT`, or `status: INVALID`, stops the
batch and cannot be replaced.

- [ ] **Step 3: Commit the preregistration**

```zsh
git add -- docs/experiments/so101-mujoco-maintainability-remediation-experiment-ledger.md
git commit -m "test(so101_mujoco): preregister phase-aware transport evidence"
```

Expected: no stack, reset, controller, or live action exists.

---

### Task 3: RED -> GREEN the per-physics-step plugin boundary

**Files:**
- Create: `src/so101_mujoco_support/msg/PhysicsStepEvidence.msg`
- Create: `src/so101_mujoco_support/msg/PhysicsStepEvidenceChunk.msg`
- Create: `src/so101_mujoco_support/msg/PhysicsHazardLatch.msg`
- Modify: `src/so101_mujoco_support/msg/SimulationEvidence.msg`
- Modify: `src/so101_mujoco_support/include/so101_mujoco_support/simulation_evidence_plugin.hpp`
- Modify: `src/so101_mujoco_support/src/simulation_evidence_plugin.cpp`
- Modify: `src/so101_mujoco_support/test/test_simulation_evidence_plugin.cpp`
- Modify: `src/so101_mujoco_support/CMakeLists.txt`

**Interfaces:**
- Consumes: `mjModel`, `mjData`, current contact whitelist, session/reset generation, and 2 ms
  timestep.
- Produces: true physics-step snapshots, continuous `PhysicsStepEvidenceChunk`, and latched
  `PhysicsHazardLatch`.

- [ ] **Step 1: Write C++ RED tests**

Add literal tests whose break is a dropped intermediate step, publish-count step, strict `>` hazard,
or overwritten latch. The core fixture advances exactly five `0.002 s` steps and injects a middle
sample of `12.0 N`; it asserts output steps `[1,2,3,4,5]`, peak `12.0`, and trigger step `3` even
when the ordinary 100 Hz snapshot would expose only steps 0 and 5. Add a forced `trylock` failure
fixture that retains the range and increments a failed-attempt field rather than dropping it.

- [ ] **Step 2: Verify RED**

```zsh
source /opt/ros/jazzy/setup.zsh
colcon test --packages-select so101_mujoco_support \
  --ctest-args -R test_simulation_evidence_plugin --output-on-failure
```

Expected: compilation/test failure because the step/chunk/latch messages and accumulator do not
exist.

- [ ] **Step 3: Implement the minimal accumulator and messages**

The public scalar contract is:

```text
maximum_normal_force_n == global_max_single_contact_force_n
hazard_breached == (global_max_single_contact_force_n >= 11.60)
left_compression_m == max(0, -min(left signed distance))
right_compression_m == max(0, -min(right signed distance))
```

Increment physics step on every advancing `data->time`, enqueue without overwrite, flush continuous
ranges at five-step cadence, retain samples on failed publication lock, and publish the first hazard
notification without allowing a later sample to mutate the latch.

- [ ] **Step 4: Verify GREEN and commit**

Run the focused C++ test twice, then:

```zsh
git add -- src/so101_mujoco_support
git commit -m "feat(so101_mujoco): capture every transport physics step"
```

Expected: all focused C++ tests pass with no format rewrite.

---

### Task 4: RED -> GREEN typed raw recording, validity, and metric analysis

**Files:**
- Create: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/dynamic_transport_evidence.py`
- Create: `src/so101_mujoco_demo_py/test/test_dynamic_transport_evidence.py`
- Modify: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/contact_calibration_collector.py`
- Modify: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/simulation/types.py`
- Modify: `src/so101_mujoco_demo_py/test/test_contact_calibration_collector.py`
- Modify: `src/so101_mujoco_demo_py/test/test_simulation_types.py`

**Interfaces:**
- Consumes: ordered physics-step chunks and typed boundary events.
- Produces: `ContactForceMode`, `TransportBoundaryKind`, immutable step/chunk/run types,
  `AtomicTransportEvidenceStore`, and `analyze_dynamic_transport(run) -> DynamicTransportSummary`.

- [ ] **Step 1: Write Python RED tests with hand-derived literals**

Use five samples at `0.002 s` with literal forces `[1.0, 2.0, 4.0, 2.0, 1.0]`. Assert the global
maximum-single-contact trapezoidal exposure is `0.018 N*s`, derived as
`(1.5 + 3.0 + 3.0 + 1.5) * 0.002`. Add literal vector-force values and assert the three component
integrals. Add separate tests for left/right total force, fingertip-only compression, shadow-excess
exposure, discrete contiguous windows, no cross-boundary integration, missing/duplicate/reversed
step rejection, reset/session mismatch, truncation, and unclosed boundary rejection.

- [ ] **Step 2: Verify RED**

```zsh
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/so101_mujoco_demo_py/test/test_dynamic_transport_evidence.py \
  src/so101_mujoco_demo_py/test/test_contact_calibration_collector.py \
  src/so101_mujoco_demo_py/test/test_simulation_types.py
```

Expected: import/attribute failures for the new typed evidence boundary.

- [ ] **Step 3: Implement pure validation and analysis**

Use only `simulation_time_s` and consecutive `physics_step`. Define overpressure as strict
`maximum_normal_force_n > 1.1579004532160448`; define hazard as
`global_max_single_contact_force_n >= 11.60`. Never use callback receipt wall time for an integral.

- [ ] **Step 4: Implement atomic chunk checkpoints**

Write every chunk to a temporary sibling, flush and `fsync`, rename atomically, hash the closed
file, and atomically replace the run index. Make partial evidence readable after a synthetic safety
abort and abnormal-close test.

- [ ] **Step 5: Verify GREEN and commit**

```zsh
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/so101_mujoco_demo_py/test/test_dynamic_transport_evidence.py \
  src/so101_mujoco_demo_py/test/test_contact_calibration_collector.py \
  src/so101_mujoco_demo_py/test/test_simulation_types.py
git add -- src/so101_mujoco_demo_py
git commit -m "feat(so101_mujoco): analyze phase-aware transport evidence"
```

Expected: the focused tests pass and evidence writes only to test temporary directories.

---

### Task 5: RED -> GREEN typed transport shadow and hazard cancellation

**Files:**
- Create: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/mujoco/transport_observer.py`
- Create: `src/so101_mujoco_demo_py/test/test_transport_observer.py`
- Modify: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_phases/transport.py`
- Modify: `src/so101_mujoco_demo_py/test/test_moveit_boundary.py`
- Create: `src/so101_mujoco_demo_py/test/test_transport_phase_policy.py`

**Interfaces:**
- Consumes: typed chunks/latch, existing `MoveItExecutionClient`, approved static contact policy,
  and unchanged motion constants.
- Produces: explicit pre-static and dynamic-shadow bilateral checks, goal-dispatch boundary events,
  partial evidence, and bounded cancellation-request evidence.

- [ ] **Step 1: Write RED tests**

Prove these observable outcomes with real typed helpers:

```python
assert check_force(1.20, ContactForceMode.DYNAMIC_TRANSPORT_SHADOW).cancel is False
assert check_force(1.20, ContactForceMode.PRE_TRANSPORT_STATIC_HOLD).cancel is True
assert check_force(11.60, ContactForceMode.DYNAMIC_TRANSPORT_SHADOW).cancel is True
```

Add tests that waypoint post-settle uses dynamic mode, the first dynamic boundary is emitted at
goal dispatch, the latch survives later low-force frames, cancellation-request step delta above 25
is invalid, and valid safety abort evidence remains readable.

- [ ] **Step 2: Verify RED**

```zsh
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/so101_mujoco_demo_py/test/test_transport_phase_policy.py \
  src/so101_mujoco_demo_py/test/test_transport_observer.py \
  src/so101_mujoco_demo_py/test/test_moveit_boundary.py
```

Expected: missing typed policy/observer failures and the legacy dynamic hard-stop assertion fails.

- [ ] **Step 3: Implement the minimum wiring**

Replace only the shared implicit bilateral helper and force-monitor branch. Do not change `TARGETS`,
`EXPECTED_START_ARM`, `EXPECTED_Q6`, `JointPlanRequest` arguments, timeout values, loop order,
trajectory execution, contact-loss contract, table-support contract, or physical outcome checks.

- [ ] **Step 4: Verify GREEN, semantic manifest, and commit**

Run focused tests and the frozen verifier. Inspect `git diff --word-diff=porcelain` for
`transport.py`; only typed force/evidence wiring may differ. Commit:

```zsh
git commit -m "fix(so101_mujoco): separate static and transport force modes"
```

---

### Task 6: RED -> GREEN schema-v4 diagnostic-only proposal

**Files:**
- Modify: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/contact_calibration.py`
- Modify: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/contact_policy.py`
- Modify: `src/so101_mujoco_demo_py/test/test_contact_calibration_contract.py`
- Modify: `src/so101_mujoco_demo_py/test/test_contact_policy.py`

**Interfaces:**
- Consumes: existing approved static calibration and exactly five valid dynamic run summaries.
- Produces: deterministic schema-v4 disabled proposal with no dynamic acceptance threshold.

- [ ] **Step 1: Write RED tests**

Require exact `acceptance_role: diagnostic_only`, five independent run IDs, waypoint detail marked
`repeated_measure`, exact metric definitions/units, all raw/summary/manifest/provenance hashes,
static `1.1579004532160448`, diagnostic stop `11.60`, and disabled approval. Reject 4 or 6 runs,
duplicate run IDs, a dynamic threshold field, enabled approval, any safety/invalid run, missing raw
hash, or treating 25 waypoint rows as independent samples.

- [ ] **Step 2: Verify RED**

```zsh
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/so101_mujoco_demo_py/test/test_contact_calibration_contract.py \
  src/so101_mujoco_demo_py/test/test_contact_policy.py
```

Expected: schema-v4 generation/validation failures.

- [ ] **Step 3: Implement v4 with read-only v1-v3 adapters**

Keep checked-in approved runtime policy bytes unchanged. Generate the new proposal only at an
explicit output path outside the repository. Hash every field except the complete approval
envelope, exactly as the existing approval lifecycle requires.

- [ ] **Step 4: Verify GREEN and commit**

```zsh
git commit -m "feat(so101_mujoco): generate diagnostic transport proposals"
```

---

### Task 7: Pass every automatic gate before live sampling

**Files:**
- Modify: ledger only for observed gate results.

**Interfaces:**
- Consumes: committed TDD implementation.
- Produces: one source commit, clean isolated three-package install overlay, and runtime provenance
  eligible for EXP-110..114.

- [ ] **Step 1: Run focused and complete Python gates**

```zsh
PYTHONNOUSERSITE=1 python3 -m pytest -q src/so101_mujoco_demo_py/test
ruff check src/so101_mujoco_demo_py
ruff format --check src/so101_mujoco_demo_py
```

- [ ] **Step 2: Run C++ read-only checks and package tests**

Use repository-discovered ament checks. Never pass `--reformat`.

- [ ] **Step 3: Build/test three packages in a fresh isolated prefix**

Source `/opt/ros/jazzy/setup.zsh` and the pinned fork overlay, assign a new `/tmp` build/install/log
root, then build and test exactly `so101_teleop`, `so101_mujoco_support`, and
`so101_mujoco_demo_py`. Record `colcon test-result --verbose`.

- [ ] **Step 4: Verify installed/runtime/frozen/protected provenance**

Check all three `ros2 pkg prefix` results point at the fresh install; rerun the MuJoCo runtime and
reset-qualified checks; run the frozen semantic verifier; require:

```zsh
git diff --quiet -- src/so101_gazebo_demo_py
git status --short -- src/so101_gazebo_demo_py
```

Any failure returns to the owning RED -> GREEN task. Do not start a stack.

- [ ] **Step 5: Commit the green-gate ledger checkpoint**

Record commands, exit codes, test counts, install prefix, hashes, and `next_experiment: EXP-110`.

---

### Task 8: Execute EXP-110 through EXP-114 sequentially

**Files:**
- Modify after each run: `docs/experiments/so101-mujoco-maintainability-remediation-experiment-ledger.md`
- Raw evidence: unique `/tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-exp-<id>/`

**Interfaces:**
- Consumes: the same committed source/install/frozen manifest for all five runs.
- Produces: five independent terminal experiment records or one batch-stopping safety/invalid event.

- [ ] **Step 1: Promote one PLANNED record to RUNNING**

Confirm empty unique ROS domain, unique Gazebo partition, unique session/evidence root, current
source/install/runtime hashes, qualified reset, and absence of conflicting owned processes. Record
the exact command before dispatching the registered runner.

- [ ] **Step 2: Run one FULL_RESTART cycle**

Do not retry. Capture physical transport outcome, raw chunk/index and summary hashes, waypoint
repeated-measure detail, breach/latency fields, cancellation/ordered shutdown, process ownership,
ROS graph cleanup, and fresh visual corroboration under `so101-dev`/`ai-station-gui` when the live
outcome is claimed.

- [ ] **Step 3: Close the experiment before starting the next**

Set experiment `status` exactly to `VALID` or `INVALID`. Under `VALID`, set `outcome_class` to
`PHYSICAL_TRANSPORT_SUCCESS`, `VALID_SAFETY_ABORT`, or another preregistered valid physical
failure. A safety abort or invalid record stops the batch immediately. Only a valid physical
transport success permits the next preregistered experiment.

- [ ] **Step 4: Repeat Steps 1-3 for the remaining registered IDs**

EXP-114 remains the preregistered replication and is not evaluated against an empirical dynamic
range.

---

### Task 9: Generate the exact-hash disabled proposal and stop

**Files:**
- Modify: `docs/experiments/so101-mujoco-maintainability-remediation-experiment-ledger.md`
- Proposal output: `/tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-proposal/contact-calibration-v4-proposal.yaml`

**Interfaces:**
- Consumes: five valid run summaries and all bound hashes.
- Produces: one deterministic disabled proposal hash and `USER_APPROVAL_REQUIRED` checkpoint.

- [ ] **Step 1: Replay and compare all five summaries**

Regenerate each summary from raw chunks and require byte-identical canonical summary hashes.
Confirm five independent runs and waypoint repeated measures.

- [ ] **Step 2: Generate twice and prove deterministic identity**

Run the analyzer twice to separate output paths and require identical bytes and SHA-256. Validate
that approval is disabled and no dynamic acceptance threshold exists.

- [ ] **Step 3: Record the terminal approval checkpoint**

Write the exact proposal path/hash, five results, per-run/waypoint diagnostic summaries, safety or
invalid events (normally none), remaining risks, all evidence/provenance hashes, and
`next_experiment: NONE_USER_APPROVAL_REQUIRED`.

- [ ] **Step 4: Stop**

Do not approve, activate, edit the checked-in policy, start Project B/C/D, run later regressions,
merge, or push. Present the exact hash to the user and request approval of that hash only.
