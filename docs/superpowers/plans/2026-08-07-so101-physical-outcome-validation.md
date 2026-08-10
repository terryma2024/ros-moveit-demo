
# SO-101 Physical Outcome Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SO-101 pick-place succeed only when an entirely physics-driven cup remains stably placed after release, while MoveIt attachment acts only as a bounded collision-planning shadow.

**Architecture:** Gazebo remains the sole physical truth source. A shared optional observation extension carries timestamped pose/contact evidence; SO-101 owns a pure deterministic `FinalPlacementEvaluator`, a polling `ReleaseSettleExecutor`, a run-scoped evidence store, planning-shadow contracts, and hold-first recovery. The shared state vocabulary grows compatibly, but only the SO-101 workflow removes forward Gazebo attach/detach; Panda retains its existing physical-attachment workflow unchanged.

**Tech Stack:** C++17, ROS 2 Jazzy, Gazebo Harmonic (`gz-msgs10`, `gz-transport13`), MoveIt 2, GoogleTest/ament, YAML-CPP, nlohmann JSON, Python 3/Pydantic/FastAPI, Bun/Vite, Git/Gitee.

## Global Constraints

- The approved design is `docs/superpowers/specs/2026-08-07-so101-physical-outcome-validation-design.md`; implementation choices may resolve its open details but must not change its semantics.
- Normal SO-101 forward execution must never issue a Gazebo attach or detach. `ATTACH_GAZEBO` and `DETACH_GAZEBO` remain real shared/Panda states, never SO-101 no-ops.
- Reset and narrowly scoped recovery may still defensively detach a stale Gazebo joint.
- MoveIt attachment is a one-way collision-planning shadow created from the latest authoritative Gazebo pose; it never writes pose or attachment state to Gazebo.
- MoveIt must detach before `OPEN_GRIPPER`; release and final settling are governed only by Gazebo contact, friction, gravity, and robot motion.
- Existing forbidden-collision, penetration, controller/execution, freshness, finite-value, and planning safety ceilings must not be relaxed.
- Carry contact/q6/object-relative drift is bounded telemetry unless it crosses a named hard safety or planning-shadow gate.
- A physically held cup must never be automatically opened off intended support. Final failure evidence must be frozen before any separately requested reset.
- New threshold values must not be guessed. Production YAML begins with the literal sentinel `CALIBRATION_REQUIRED`; execute mode fails closed until ledger-backed calibration replaces every sentinel with a finite value.
- Do not revive the falsified 0.75 mm seat, independent `CLOSE_GRIPPER` seat motion, longer-close-as-fix, relaxed safety gates, or the unregistered fixed-port retry fixture.
- Use Bun, not npm/npx, for `src/so101_gazebo_demo/web`; never run `ament_uncrustify --reformat`.
- `origin` is Gitee. Do not use `gh`; use standard Git commands.
- Every production change follows RED -> observed expected failure -> minimal GREEN -> focused tests -> one logical commit.
- On any unexpected failure, stop the task and invoke `superpowers:systematic-debugging`: record the first bad boundary, reproduce, inspect the complete error, compare the working pattern, state one hypothesis, and change one variable. Do not stack speculative fixes.

## Locked implementation decisions

1. New shared enum values are `WAIT_RELEASE_SETTLE` and `VALIDATE_FINAL_PLACEMENT`; their action/forward membership remains workflow-owned rather than inferred globally.
2. The first final region shape is an axis-aligned XY box (`min_xy_m`, `max_xy_m`). This is an explicit region and avoids unused shape polymorphism.
3. Pose speed is derived from adjacent release-epoch samples with strictly increasing monotonic receipt timestamps. Angular speed uses normalized-quaternion shortest angular distance. Invalid/non-increasing intervals are stale evidence, never zero speed.
4. The final pose is the last counted Gazebo sample in the qualifying consecutive window.
5. Primary final-failure precedence is: hard safety/Gazebo-attached/MoveIt-attached -> stale or incomplete evidence -> gripper contact -> unsupported -> tipped -> still moving -> out of region. Every violated predicate is still emitted as a bounded metric/subcode.
6. Any checkpoint at or after successful `OPEN_GRIPPER` and before successful `SYNC_WORLD_OBJECT` is non-resumable. A new run/reset creates a new epoch; no pre-release or prior-process samples are reused.
7. `FinalPlacementEvidenceStore` is an in-memory, run-scoped handoff. It freezes success or failure evidence before runner recovery selection; `SYNC_WORLD_OBJECT` consumes only a successful frozen record. The persistent checkpoint stores only the non-resumable boundary and failure summary, not the epoch window.
8. Telemetry buffers have a configured maximum sample count. Public evidence exposes count, first/last sequence/time, min/max/mean, violation counts, final sample, and named contacts—not an unbounded sample array.

---

### Task 1: Establish execution provenance and the physical-outcome ledger campaign

**Files:**
- Modify during execution only: `docs/experiments/so101-reset-world-five-success-experiment-ledger.md`
- Read: `AGENTS.md`
- Read: `.agents/skills/so101-dev/SKILL.md`
- Read: `.agents/skills/so101-dev/references/{ai-station-access,so101-system-map,debug-evidence,test-and-acceptance,experiment-ledger}.md`

**Interfaces:**
- Consumes: approved spec commit and this plan.
- Produces: immutable campaign header, execution checkpoint, unique `/tmp` evidence root, and ownership/provenance baseline used by all later runtime tasks.

- [ ] **Step 1: Load execution skills and verify the existing worktree**

Announce use of `superpowers:executing-plans` or `superpowers:subagent-driven-development`, then read the complete plan and project-local skill. Run locally:

```bash
pwd
hostname
git branch --show-current
git rev-parse HEAD
git status --short
git submodule status
git log -5 --oneline --decorate
```

Expected: the approved design/plan branch is active, and all pre-existing dirty paths are recorded rather than cleaned or overwritten.

- [ ] **Step 2: Inspect process ownership before any runtime action**

```bash
tmux list-sessions 2>/dev/null || true
pgrep -af 'gz sim|move_group|rviz2|pick_place_state_machine' || true
```

Expected: every existing process/session is classified as preserved or owned. Do not start or stop anything in this step.

- [ ] **Step 3: Create the evidence root and record exact provenance**

```bash
evidence_root=$(mktemp -d /tmp/so101-debug-physical-outcome-XXXXXX)
printf '%s\n' "$evidence_root"
git rev-parse HEAD
git status --short
```

Record the absolute evidence root. Never place logs, screenshots, rosbag, build products, or videos in the source tree.

- [ ] **Step 4: Add the separated campaign header and checkpoint to the ledger**

Append—not rewrite—a `physical-outcome campaign` section containing exactly:

```yaml
task_id: so101-physical-outcome-validation
success_contract: five consecutive VALID execute runs whose post-release stable physical outcome and every hard safety invariant pass
worktree: /data/work/ws_moveit/.worktrees/so101-physical-outcome-validation
branch: codex/so101-physical-outcome-validation
base_commit: <captured-base-sha>
current_commit: <captured-head-sha>
evidence_root: <absolute-/tmp-path>
confirmed_conclusions:
  - approved physical truth versus planning shadow semantics from the design commit
disproven_routes:
  - 0.75 mm seat
  - independent CLOSE seat motion
  - longer close duration as a fix
  - safety-gate relaxation
  - unregistered fixed-port retry fixture
open_hypotheses:
  - live calibration values for every CALIBRATION_REQUIRED field
latest_checkpoint: CP-PHYSICAL-001
next_experiment: CAL-PHYSICAL-001
```

The checkpoint must also record exact dirty paths, owned/preserved processes, last valid historical experiment, open risks, and one next command.

- [ ] **Step 5: Verify and commit only the campaign bootstrap**

```bash
git diff --check
git diff -- docs/experiments/so101-reset-world-five-success-experiment-ledger.md
git add docs/experiments/so101-reset-world-five-success-experiment-ledger.md
git diff --cached --check
git commit -m "docs(so101): start physical outcome campaign"
```

Expected: one ledger-only commit; no experiment is marked `RUNNING` or `VALID` yet.

### Task 2: Extend shared state serialization without changing Panda workflow

**Files:**
- Modify: `src/pick_place_common/include/pick_place_common/domain_types.hpp`
- Modify: `src/pick_place_common/src/domain_types.cpp`
- Modify: `src/pick_place_common/test/test_workflow_definition.cpp`
- Modify: `src/panda_gazebo_demo/test/pick_place/test_workflow_characterization.cpp`
- Modify: `src/panda_gazebo_demo/test/pick_place/test_registration_coverage.cpp`

**Interfaces:**
- Produces: `State::WAIT_RELEASE_SETTLE`, `State::VALIDATE_FINAL_PLACEMENT`, exact string round-trip.
- Preserves: Panda forward trace including `ATTACH_GAZEBO`, `DETACH_GAZEBO`, and real executor registrations.

- [ ] **Step 1: Write failing shared serialization and Panda compatibility tests**

Add `WorkflowDefinition.NewPhysicalOutcomeStatesRoundTripWithoutGlobalWorkflowMembership` and extend `PandaWorkflowCharacterization.ForwardAndRecoveryEdgesRemainStable` plus `RegistrationCoverage.FactoryBuildsTheCompleteRuntimeGraph` to assert the exact unchanged Panda trace and real Gazebo executors.

- [ ] **Step 2: Run RED**

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select pick_place_common panda_gazebo_demo --symlink-install
colcon test --packages-select pick_place_common panda_gazebo_demo --ctest-args -R '^(test_workflow_definition|test_workflow_characterization|test_registration_coverage)$' --event-handlers console_direct+
colcon test-result --verbose
```

Expected RED: compilation fails because the two enum values/string mappings do not exist. Panda assertions must not fail for a changed expected trace.

- [ ] **Step 3: Add enum and complete mapping only**

Insert the new values after `OPEN_GRIPPER` and before legacy detach states in `State`; update `kStates`, `toString`, and `stateFromString`. Do not remove or alias legacy values and do not change `pandaWorkflowDefinition()`.

- [ ] **Step 4: Run GREEN and commit**

```bash
colcon build --packages-select pick_place_common panda_gazebo_demo --symlink-install
colcon test --packages-select pick_place_common panda_gazebo_demo --ctest-args -R '^(test_workflow_definition|test_workflow_characterization|test_registration_coverage)$' --event-handlers console_direct+
colcon test-result --verbose
git add src/pick_place_common/include/pick_place_common/domain_types.hpp src/pick_place_common/src/domain_types.cpp src/pick_place_common/test/test_workflow_definition.cpp src/panda_gazebo_demo/test/pick_place/test_workflow_characterization.cpp src/panda_gazebo_demo/test/pick_place/test_registration_coverage.cpp
git commit -m "feat(pick-place): add physical outcome states"
```

Expected GREEN: selected tests pass and Panda still issues real physical attach/detach.

### Task 3: Add fail-closed physical-outcome policy schema

**Files:**
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/policy_config.hpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/policy_config.cpp`
- Modify: `src/so101_gazebo_demo/config/validation_policies/light_cup_wall_pick.yaml`
- Modify: `src/so101_gazebo_demo/test/pick_place/test_policy_config.cpp`
- Modify: `src/so101_gazebo_demo/test/test_configuration_contract.py`

**Interfaces:**
- Produces: `PhysicalOutcomePolicyConfig`, `AxisAlignedTargetRegion`, `CatastrophicLossPolicy`, `PlanningShadowPolicy`, and `bool calibration_complete`.
- Consumes: one strict validation-policy map; execution gating consumes `calibration_complete` later.

- [ ] **Step 1: Write failing parser tests**

Add these exact tests:

```text
PolicyConfig.LoadsExplicitCalibrationRequiredPhysicalOutcomePolicy
PolicyConfig.LoadsFullyCalibratedPhysicalOutcomePolicyFromFixture
PolicyConfig.RejectsUnknownPhysicalOutcomeField
PolicyConfig.RejectsMissingPhysicalOutcomeField
PolicyConfig.RejectsNonFiniteOrNonPositivePhysicalOutcomeThreshold
PolicyConfig.RejectsReversedRegionHeightAndWorkspaceBounds
PolicyConfig.RejectsSettleTimeoutShorterThanMinimumDuration
PolicyConfig.RejectsMixedSentinelAndNumericCalibration
```

Use test-local YAML copies for numeric GREEN cases. Numeric literals in fixtures are test vectors only and must not be copied to production YAML or described as calibrated values.

- [ ] **Step 2: Run RED**

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select pick_place_common so101_gazebo_demo --symlink-install
colcon test --packages-select so101_gazebo_demo --ctest-args -R '^(test_policy_config|test_configuration_contract)$' --event-handlers console_direct+
colcon test-result --verbose
```

Expected RED: the parser rejects/ignores the absent `physical_outcome` schema and lacks the new types.

- [ ] **Step 3: Implement strict schema version 2 and sentinel parsing**

Define:

```cpp
struct AxisAlignedTargetRegion { double min_x, min_y, max_x, max_y; };
struct PhysicalOutcomePolicyConfig {
  std::string intended_support_collision;
  std::optional<AxisAlignedTargetRegion> final_target_region;
  std::optional<std::array<double, 2>> support_height_range_m;
  std::optional<double> max_upright_tilt_rad;
  std::optional<double> max_linear_speed_m_s;
  std::optional<double> max_angular_speed_rad_s;
  std::optional<std::size_t> consecutive_samples;
  std::optional<double> minimum_stable_duration_s;
  std::optional<double> sample_interval_s;
  std::optional<double> settle_timeout_s;
  std::optional<double> max_observation_age_s;
  std::optional<std::size_t> max_telemetry_samples;
  CatastrophicLossPolicy catastrophic_loss;
  PlanningShadowPolicy planning_shadow;
  bool calibration_complete{false};
};
```

Every threshold field must be either numeric across the whole map or the exact scalar `CALIBRATION_REQUIRED`; mixed mode is invalid. `intended_support_collision` is not a threshold and must be the normalized identity `table::link::collision`, derived from the existing SDF names `table`, `link`, and `collision`.

- [ ] **Step 4: Add explicit production sentinels**

Upgrade the production validation policy to schema 2 and add every design field with `CALIBRATION_REQUIRED`, including `max_telemetry_samples`. Do not choose values and do not change existing grasp/motion/safety numbers.

- [ ] **Step 5: Run GREEN and commit**

```bash
colcon build --packages-select pick_place_common so101_gazebo_demo --symlink-install
colcon test --packages-select so101_gazebo_demo --ctest-args -R '^(test_policy_config|test_configuration_contract)$' --event-handlers console_direct+
colcon test-result --verbose
git diff --check
git add src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/policy_config.hpp src/so101_gazebo_demo/src/pick_place/policy_config.cpp src/so101_gazebo_demo/config/validation_policies/light_cup_wall_pick.yaml src/so101_gazebo_demo/test/pick_place/test_policy_config.cpp src/so101_gazebo_demo/test/test_configuration_contract.py
git commit -m "feat(so101): define physical outcome policy"
```

Expected GREEN: parser/config contract tests pass; production execute remains intentionally uncalibrated.

### Task 4: Extend timestamped snapshot and independent support evidence

**Files:**
- Modify: `src/pick_place_common/include/pick_place_common/world_observer.hpp`
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/gazebo_world_observer.hpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/gazebo_world_observer.cpp`
- Create: `src/so101_gazebo_demo/test/pick_place/test_gazebo_world_observer.cpp`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`
- Modify: `src/panda_gazebo_demo/test/pick_place/test_gazebo_world_observer.cpp`

**Interfaces:**
- Produces in `WorldSnapshot`: `gazebo_pose_sequence`, `gazebo_pose_observed_at`, independent gripper/support timestamps, `gazebo_task_object_intended_support_contact`, support collision names/samples, and optional derived velocity fields.
- Preserves: all additions are optional; Panda observer compiles and retains current behavior.

- [ ] **Step 1: Add RED observer tests**

Register `test_gazebo_world_observer` and add:

```text
GazeboWorldObserver.PreservesFreshBottomToIntendedTableContact
GazeboWorldObserver.DoesNotTreatOtherBottomCollisionAsSupport
GazeboWorldObserver.KeepsBottomAndFingerFreshnessIndependent
GazeboWorldObserver.RejectsNegativeMissingAndNonFiniteSupportDepth
GazeboWorldObserver.IncrementsPoseReceiptSequenceAndTimestamp
```

Extend Panda `GazeboWorldObserver` tests to prove missing SO-101-only optional fields do not fail its workflow.

- [ ] **Step 2: Run RED**

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --symlink-install
colcon test --packages-select so101_gazebo_demo panda_gazebo_demo --ctest-args -R '^test_gazebo_world_observer$' --event-handlers console_direct+
colcon test-result --verbose
```

Expected RED: new snapshot fields and SO-101 test target are absent.

- [ ] **Step 3: Implement evidence classification**

Add a generic `TaskObjectSupportContactSample` holding both collision names, point/normal/depth, and receipt timestamp. In `onContacts`, branch on sensor identity before gripper filtering. Normalize scoped names and accept support only when the other collision equals configured `table::link::collision`. Preserve per-sensor `observed_at`; remove the single aggregate `contact_received_at_` freshness shortcut.

- [ ] **Step 4: Implement monotonic pose receipt metadata**

Increment one observer-owned `std::uint64_t` only when a finite task-object pose is accepted; copy its steady-clock receipt time and sequence into each enriched snapshot. Do not derive speed in the observer callback.

- [ ] **Step 5: Run GREEN and commit**

```bash
colcon build --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --symlink-install
colcon test --packages-select so101_gazebo_demo panda_gazebo_demo --ctest-args -R '^test_gazebo_world_observer$' --event-handlers console_direct+
colcon test-result --verbose
git add src/pick_place_common/include/pick_place_common/world_observer.hpp src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/gazebo_world_observer.hpp src/so101_gazebo_demo/src/pick_place/gazebo_world_observer.cpp src/so101_gazebo_demo/test/pick_place/test_gazebo_world_observer.cpp src/so101_gazebo_demo/CMakeLists.txt src/panda_gazebo_demo/test/pick_place/test_gazebo_world_observer.cpp
git commit -m "feat(so101): observe physical support evidence"
```

### Task 5: Implement the pure deterministic final placement evaluator

**Files:**
- Create: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/final_placement_evaluator.hpp`
- Create: `src/so101_gazebo_demo/src/pick_place/final_placement_evaluator.cpp`
- Create: `src/so101_gazebo_demo/test/pick_place/test_final_placement_evaluator.cpp`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`

**Interfaces:**
- Produces: `ReleaseEpoch`, `FinalPlacementSample`, `FinalPlacementMetrics`, `FinalPlacementEvidence`, `FinalPlacementEvaluation`, and `FinalPlacementEvaluator::evaluate(...) const`.
- Pure input: policy, epoch marker, ordered snapshots. No clock reads, sleeps, ROS, files, callbacks, or mutable global state.

- [ ] **Step 1: Write the success and epoch-isolation RED tests**

Add:

```text
FinalPlacementEvaluator.AcceptsOnlyConsecutivePostReleaseStableSamples
FinalPlacementEvaluator.RejectsEverySampleAtOrBeforeReleaseSequence
FinalPlacementEvaluator.UsesLastCountedGazeboPoseAsFinalPose
FinalPlacementEvaluator.ResetsConsecutiveWindowOnSessionOrSequenceBreak
FinalPlacementEvaluator.RequiresConfiguredCountAndMinimumDuration
```

- [ ] **Step 2: Write speed and failure-precedence RED tests**

Add:

```text
FinalPlacementEvaluator.DerivesAdjacentLinearAndShortestQuaternionAngularSpeed
FinalPlacementEvaluator.TreatsNonIncreasingOrNonFiniteTimeAsStale
FinalPlacementEvaluator.BoundsTelemetryAndPreservesAggregates
FinalPlacementEvaluator.AppliesSafetyStaleContactSupportTiltMotionRegionPrecedence
FinalPlacementEvaluator.ReportsAllViolatedPredicatesAlongsidePrimaryCode
```

Cover each required primary code exactly: `FINAL_PLACEMENT_SAFETY_FAILURE`, `FINAL_PLACEMENT_EVIDENCE_STALE`, `FINAL_PLACEMENT_GRIPPER_CONTACT`, `FINAL_PLACEMENT_UNSUPPORTED`, `FINAL_PLACEMENT_TIPPED`, `FINAL_PLACEMENT_STILL_MOVING`, and `FINAL_PLACEMENT_OUT_OF_REGION`.

- [ ] **Step 3: Run RED**

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select pick_place_common so101_gazebo_demo --symlink-install
colcon test --packages-select so101_gazebo_demo --ctest-args -R '^test_final_placement_evaluator$' --event-handlers console_direct+
colcon test-result --verbose
```

Expected RED: target/source/API do not exist.

- [ ] **Step 4: Implement the minimal pure evaluator**

Use this public shape:

```cpp
struct ReleaseEpoch { std::string id; std::string simulation_session_id; std::uint64_t start_sequence; };
struct FinalPlacementEvaluation {
  bool stable{false};
  bool terminal_failure{false};
  std::optional<Failure> failure;
  FinalPlacementMetrics metrics;
  std::optional<FinalPlacementEvidence> evidence;
};
class FinalPlacementEvaluator {
public:
  explicit FinalPlacementEvaluator(PhysicalOutcomePolicyConfig policy);
  FinalPlacementEvaluation evaluate(const ReleaseEpoch &, const std::vector<WorldSnapshot> &) const;
};
```

Compute adjacent velocities only after epoch/session/fresh/finite ordering checks. Count a window sample only when every final predicate passes. Cap retained sample summaries at `max_telemetry_samples`, while aggregate count/min/max/mean/violations cover all observations.

- [ ] **Step 5: Run GREEN and commit**

```bash
colcon build --packages-select pick_place_common so101_gazebo_demo --symlink-install
colcon test --packages-select so101_gazebo_demo --ctest-args -R '^test_final_placement_evaluator$' --event-handlers console_direct+
colcon test-result --verbose
git add src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/final_placement_evaluator.hpp src/so101_gazebo_demo/src/pick_place/final_placement_evaluator.cpp src/so101_gazebo_demo/test/pick_place/test_final_placement_evaluator.cpp src/so101_gazebo_demo/CMakeLists.txt
git commit -m "feat(so101): evaluate final physical placement"
```

### Task 6: Add release epoch, bounded settle executor, and evidence handoff

**Files:**
- Create: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/final_placement_evidence_store.hpp`
- Create: `src/so101_gazebo_demo/src/pick_place/final_placement_evidence_store.cpp`
- Create: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/release_settle_executor.hpp`
- Create: `src/so101_gazebo_demo/src/pick_place/release_settle_executor.cpp`
- Create: `src/so101_gazebo_demo/test/pick_place/test_release_settle_executor.cpp`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`

**Interfaces:**
- `IFinalPlacementEvidenceStore::{beginEpoch, recordEvaluation, frozen}`.
- `ReleaseSettleExecutor(IWorldObserver &, FinalPlacementEvaluator, IFinalPlacementEvidenceStore &, PhysicalOutcomePolicyConfig)`.
- Consumes post-open marker from `ExecutionContext.before/after`; produces frozen evidence before returning success/failure.

- [ ] **Step 1: Write executor RED tests with a fake observer/clock waiter**

Add:

```text
ReleaseSettleExecutor.StartsEpochAfterConfirmedOpenPostObservation
ReleaseSettleExecutor.NeverPassesPreReleaseSamplesToEvaluator
ReleaseSettleExecutor.PollsUntilConsecutiveWindowSucceeds
ReleaseSettleExecutor.TimesOutWithSpecificLatestPredicateFailure
ReleaseSettleExecutor.CancellationStopsPollingAndFreezesEvidence
ReleaseSettleExecutor.RejectsCalibrationRequiredPolicyBeforePolling
ReleaseSettleExecutor.KeepsBoundedMetricsAcrossTransientFluctuations
```

Inject `ISettleWaiter::waitFor(duration)` so tests advance deterministically; the pure evaluator tests remain sleep-free.

- [ ] **Step 2: Run RED**

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select pick_place_common so101_gazebo_demo --symlink-install
colcon test --packages-select so101_gazebo_demo --ctest-args -R '^test_release_settle_executor$' --event-handlers console_direct+
colcon test-result --verbose
```

Expected RED: executor/store interfaces are missing.

- [ ] **Step 3: Implement executor and in-memory store**

Generate epoch id from run/session plus confirmed open post-observation sequence. The executor uses condition polling at configured interval, checks cancellation before and after observe/wait, stops at configured timeout, and always freezes the last evaluation before returning. Never call reset, motion, gripper, Gazebo attachment, or MoveIt mutation.

- [ ] **Step 4: Run GREEN and commit**

```bash
colcon build --packages-select pick_place_common so101_gazebo_demo --symlink-install
colcon test --packages-select so101_gazebo_demo --ctest-args -R '^test_release_settle_executor$' --event-handlers console_direct+
colcon test-result --verbose
git add src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/final_placement_evidence_store.hpp src/so101_gazebo_demo/src/pick_place/final_placement_evidence_store.cpp src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/release_settle_executor.hpp src/so101_gazebo_demo/src/pick_place/release_settle_executor.cpp src/so101_gazebo_demo/test/pick_place/test_release_settle_executor.cpp src/so101_gazebo_demo/CMakeLists.txt
git commit -m "feat(so101): settle post-release outcome"
```

### Task 7: Refactor attachment contracts into physical carry and planning shadow contracts

**Files:**
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_attachment_contracts.hpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/so101_attachment_contracts.cpp`
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_moveit_scene_policy.hpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/so101_moveit_scene_policy.cpp`
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/pick_place_runtime.hpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/pick_place_runtime.cpp`
- Modify: `src/so101_gazebo_demo/test/pick_place/test_so101_attachment_contracts.cpp`
- Modify: `src/so101_gazebo_demo/test/pick_place/test_so101_pick_place_runtime.cpp`

**Interfaces:**
- Produces: `derivePlanningShadowPose(snapshot)`, `evaluatePlanningShadowDivergence(snapshot, policy)`, and carrying plan validator.
- Consumes: actual attach-time Gazebo pose plus MoveIt gripper pose; no calibrated-relative-pose substitution.

- [ ] **Step 1: Replace old Gazebo-forward expectations with RED shadow tests**

Add/rename exact tests:

```text
SO101AttachmentContracts.MoveItAttachUsesLatestFreshGazeboPoseAndDerivedRelativePose
SO101AttachmentContracts.NormalForwardCarryRequiresGazeboDetached
SO101AttachmentContracts.PreservesForbiddenCollisionAndPenetrationCeilings
SO101AttachmentContracts.ShadowDivergenceWithinLimitIsTelemetry
SO101AttachmentContracts.ShadowDivergenceAtLimitFailsPlanningValidity
SO101AttachmentContracts.FinalSyncUsesFrozenFinalGazeboPose
SO101PickPlaceRuntime.CarryingPlansGateFreshPairedShadowEvidence
```

Remove tests whose desired behavior is forward Gazebo attach/detach, not safety-contact tests that remain applicable to physical grasp.

- [ ] **Step 2: Run RED**

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select pick_place_common so101_gazebo_demo --symlink-install
colcon test --packages-select so101_gazebo_demo --ctest-args -R '^(test_so101_attachment_contracts|test_so101_pick_place_runtime)$' --event-handlers console_direct+
colcon test-result --verbose
```

Expected RED: current contracts demand both Gazebo and MoveIt attached and compare to calibrated relative pose.

- [ ] **Step 3: Implement one-way shadow creation and drift gate**

`SO101MoveItScenePolicy::prepare(ATTACH, context)` must require fresh finite `context.before.gazebo_task_object_pose_world`, set `upsert_before_attach`, and retain the derived attach-relative pose in run-scoped shadow evidence. Compute divergence from paired Gazebo world pose and `moveit_gripper_pose_world * moveit_task_object_attached_relative_pose`. Return `PLANNING_SHADOW_DIVERGENCE` before `LIFT`, `MOVE_ABOVE_PLACE`, and `DESCEND_TO_PLACE` planning when missing/stale/outside the calibrated hard bound.

- [ ] **Step 4: Preserve hard safety gates**

Keep `grasp_contact.forbidden_collisions`, `max_penetration_m`, controller health, non-finite/freshness checks, and catastrophic-loss failure paths. Replace only nominal-equality carry checks with telemetry aggregation below hard limits.

- [ ] **Step 5: Run GREEN and commit**

```bash
colcon build --packages-select pick_place_common so101_gazebo_demo --symlink-install
colcon test --packages-select so101_gazebo_demo --ctest-args -R '^(test_so101_attachment_contracts|test_so101_pick_place_runtime)$' --event-handlers console_direct+
colcon test-result --verbose
git add src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_attachment_contracts.hpp src/so101_gazebo_demo/src/pick_place/so101_attachment_contracts.cpp src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_moveit_scene_policy.hpp src/so101_gazebo_demo/src/pick_place/so101_moveit_scene_policy.cpp src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/pick_place_runtime.hpp src/so101_gazebo_demo/src/pick_place/pick_place_runtime.cpp src/so101_gazebo_demo/test/pick_place/test_so101_attachment_contracts.cpp src/so101_gazebo_demo/test/pick_place/test_so101_pick_place_runtime.cpp
git commit -m "refactor(so101): separate physical carry from planning shadow"
```

### Task 8: Switch only the SO-101 workflow and runtime registrations

**Files:**
- Modify: `src/so101_gazebo_demo/src/pick_place/so101_workflow.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/transition_table.cpp`
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_task3_runtime.hpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/so101_task3_runtime.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/pick_place_runtime.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/pick_place_state_machine.cpp`
- Modify: `src/so101_gazebo_demo/test/pick_place/{test_workflow_characterization,test_transition_table,test_dry_run,test_so101_task3_runtime,test_so101_pick_place_runtime}.cpp`
- Modify: `src/panda_gazebo_demo/test/pick_place/{test_workflow_characterization,test_registration_coverage}.cpp`

**Interfaces:**
- Produces exact SO-101 trace from approved design.
- Runtime dependencies add observer/evaluator/evidence store; remove `gazebo_attach` and forward `gazebo_detach`, retain `recovery_gazebo_detach`.

- [ ] **Step 1: Write exact trace/registration RED tests**

Assert this subsequence exactly:

```text
VERIFY_PHYSICAL_GRASP -> ATTACH_MOVEIT -> LIFT -> MOVE_ABOVE_PLACE ->
DESCEND_TO_PLACE -> DETACH_MOVEIT -> OPEN_GRIPPER -> WAIT_RELEASE_SETTLE ->
VALIDATE_FINAL_PLACEMENT -> SYNC_WORLD_OBJECT -> RETREAT -> DONE
```

Assert `findExecutor(ATTACH_GAZEBO) == nullptr`, `findExecutor(DETACH_GAZEBO) == nullptr`, both new executors exist, and `RECOVER_DETACH_GAZEBO` remains registered. Reassert Panda's old graph unchanged.

- [ ] **Step 2: Run RED**

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --symlink-install
colcon test --packages-select so101_gazebo_demo panda_gazebo_demo --ctest-args -R '^(test_workflow_characterization|test_registration_coverage|test_pick_place_transition_table|test_pick_place_dry_run|test_so101_task3_runtime|test_so101_pick_place_runtime)$' --event-handlers console_direct+
colcon test-result --verbose
```

Expected RED: SO-101 still routes through forward Gazebo attachment and opens before MoveIt detach.

- [ ] **Step 3: Atomically switch workflow and registrations**

Remove SO-101 normal transitions/forward-state membership and production construction for `ATTACH_GAZEBO`/`DETACH_GAZEBO`; do not register no-ops. Wire `DETACH_MOVEIT -> OPEN_GRIPPER -> WAIT_RELEASE_SETTLE -> VALIDATE_FINAL_PLACEMENT -> SYNC_WORLD_OBJECT`. `VALIDATE_FINAL_PLACEMENT` reads the frozen store and returns its already-determined result without new sampling.

- [ ] **Step 4: Gate executable mode on calibration**

At bootstrap, allow policy loading and dry-run contract inspection with sentinels, but reject `PLAN_ONLY`/`EXECUTE` before any scene or robot mutation with `PHYSICAL_OUTCOME_CALIBRATION_REQUIRED`. Once all fields are numeric and valid, set `execution_safe` normally.

- [ ] **Step 5: Run GREEN and commit**

```bash
colcon build --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --symlink-install
colcon test --packages-select so101_gazebo_demo panda_gazebo_demo --ctest-args -R '^(test_workflow_characterization|test_registration_coverage|test_pick_place_transition_table|test_pick_place_dry_run|test_so101_task3_runtime|test_so101_pick_place_runtime)$' --event-handlers console_direct+
colcon test-result --verbose
git add src/so101_gazebo_demo/src/pick_place/so101_workflow.cpp src/so101_gazebo_demo/src/pick_place/transition_table.cpp src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_task3_runtime.hpp src/so101_gazebo_demo/src/pick_place/so101_task3_runtime.cpp src/so101_gazebo_demo/src/pick_place/pick_place_runtime.cpp src/so101_gazebo_demo/src/pick_place/pick_place_state_machine.cpp src/so101_gazebo_demo/test/pick_place/test_workflow_characterization.cpp src/so101_gazebo_demo/test/pick_place/test_transition_table.cpp src/so101_gazebo_demo/test/pick_place/test_dry_run.cpp src/so101_gazebo_demo/test/pick_place/test_so101_task3_runtime.cpp src/so101_gazebo_demo/test/pick_place/test_so101_pick_place_runtime.cpp src/panda_gazebo_demo/test/pick_place/test_workflow_characterization.cpp src/panda_gazebo_demo/test/pick_place/test_registration_coverage.cpp
git commit -m "feat(so101): run physics-only forward workflow"
```

Before committing, inspect staged paths and exclude unrelated generated `web/dist`, build, install, logs, screenshots, and ledger changes.

### Task 9: Make post-release checkpoints non-resumable and epoch-safe

**Files:**
- Modify: `src/pick_place_common/include/pick_place_common/checkpoint.hpp`
- Modify: `src/pick_place_common/src/runner.cpp`
- Modify: `src/pick_place_common/src/checkpoint_validation.cpp`
- Modify: `src/pick_place_common/test/{test_common_runner,test_checkpoint_validation}.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/file_checkpoint_store.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/common_resume_validator.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/so101_resume_validation_policy.cpp`
- Modify: `src/so101_gazebo_demo/test/pick_place/{test_checkpoint,test_pick_place_runner}.cpp`
- Modify: `src/panda_gazebo_demo/test/pick_place/test_checkpoint_v3.cpp`

**Interfaces:**
- Produces checkpoint schema 4 and `POST_RELEASE_EPOCH_NON_RESUMABLE` rejection.
- Preserves Panda's schema-4 round-trip with no post-release restriction unless its workflow reaches the SO-101-only states.

- [ ] **Step 1: Write RED checkpoint tests**

Add:

```text
CheckpointV4.RoundTripPreservesObservationSequencesAndSupportEvidence
CheckpointV4.RejectsSchemaThreeInsteadOfSilentlyMigrating
CheckpointV4.MarksOpenThroughFinalSyncBoundaryNonResumable
CommonResumeValidator.RejectsPostReleaseEpochCheckpoint
CommonRunner.CommitsFinalFailureBeforeSelectingRecovery
```

Update Panda `CheckpointV3` suite name/content to schema 4 and prove ordinary Panda forward/recovery checkpoints remain resumable under its existing rules.

- [ ] **Step 2: Run RED**

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --symlink-install
colcon test --packages-select pick_place_common so101_gazebo_demo panda_gazebo_demo --ctest-args -R '^(test_common_runner|test_checkpoint_validation|test_pick_place_checkpoint|test_pick_place_runner|test_checkpoint_v3)$' --event-handlers console_direct+
colcon test-result --verbose
```

Expected RED: schema remains 3 and post-release checkpoints can reuse stationary evidence.

- [ ] **Step 3: Implement schema 4 and non-resumability**

Serialize observation sequence/timestamp summaries and support facts needed to explain the boundary, but never serialize a reusable release window. Runner sets `resumable=false` after successful `OPEN_GRIPPER` until successful `SYNC_WORLD_OBJECT`. Resume returns `POST_RELEASE_EPOCH_NON_RESUMABLE`; operator must preserve evidence and start a separate reset/new run.

- [ ] **Step 4: Run GREEN and commit**

```bash
colcon build --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --symlink-install
colcon test --packages-select pick_place_common so101_gazebo_demo panda_gazebo_demo --ctest-args -R '^(test_common_runner|test_checkpoint_validation|test_pick_place_checkpoint|test_pick_place_runner|test_checkpoint_v3)$' --event-handlers console_direct+
colcon test-result --verbose
git add src/pick_place_common src/so101_gazebo_demo/src/pick_place/file_checkpoint_store.cpp src/so101_gazebo_demo/src/pick_place/common_resume_validator.cpp src/so101_gazebo_demo/src/pick_place/so101_resume_validation_policy.cpp src/so101_gazebo_demo/test/pick_place/test_checkpoint.cpp src/so101_gazebo_demo/test/pick_place/test_pick_place_runner.cpp src/panda_gazebo_demo/test/pick_place/test_checkpoint_v3.cpp
git commit -m "feat(pick-place): isolate post-release checkpoints"
```

### Task 10: Enforce hold-first recovery and preserve failed outcomes

**Files:**
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/recovery_policy.hpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/so101_recovery_policy.cpp`
- Modify: `src/pick_place_common/src/runner.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/world_reset_coordinator.cpp`
- Modify: `src/so101_gazebo_demo/test/pick_place/{test_so101_recovery_policy,test_pick_place_runner,test_so101_world_reset}.cpp`

**Interfaces:**
- Produces hold-first `RecoveryRoute` with no automatic action when physically held and unsupported.
- Preserves defensive `RECOVER_DETACH_GAZEBO` and reset detach for stale historical joints.

- [ ] **Step 1: Write RED recovery tests**

Add:

```text
SO101RecoveryPolicy.PhysicallyHeldUnsupportedCupStopsWithoutOpening
SO101RecoveryPolicy.SupportedHeldCupMaySelectControlledOpen
SO101RecoveryPolicy.PostReleaseFailurePreservesEvidenceWithoutMotion
SO101RecoveryPolicy.StaleGazeboJointStillSelectsDefensiveDetachDuringReset
CommonRunner.FreezesFinalFailureBeforeRecoverySelection
SO101WorldReset.DefensivelyDetachesStaleGazeboJointInSeparateTransaction
```

- [ ] **Step 2: Run RED**

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select pick_place_common so101_gazebo_demo --symlink-install
colcon test --packages-select pick_place_common so101_gazebo_demo --ctest-args -R '^(test_common_runner|test_so101_recovery_policy|test_pick_place_runner|test_so101_world_reset)$' --event-handlers console_direct+
colcon test-result --verbose
```

Expected RED: current policy can route a held unsupported cup through `RECOVER_OPEN_GRIPPER`.

- [ ] **Step 3: Implement hold-first selection**

Require fresh finite support contact/height and detached MoveIt shadow before selecting controlled open. If held and unsupported, cancel active actions, return the original failure plus `recovery_disposition=HOLD_FOR_OPERATOR`, and commit a non-resumable evidence checkpoint. Do not move, open, sync, or reset automatically. Keep reset's explicit defensive detach path unchanged.

- [ ] **Step 4: Run GREEN and commit**

```bash
colcon build --packages-select pick_place_common so101_gazebo_demo --symlink-install
colcon test --packages-select pick_place_common so101_gazebo_demo --ctest-args -R '^(test_common_runner|test_so101_recovery_policy|test_pick_place_runner|test_so101_world_reset)$' --event-handlers console_direct+
colcon test-result --verbose
git add src/pick_place_common/src/runner.cpp src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/recovery_policy.hpp src/so101_gazebo_demo/src/pick_place/so101_recovery_policy.cpp src/so101_gazebo_demo/src/pick_place/world_reset_coordinator.cpp src/so101_gazebo_demo/test/pick_place/test_so101_recovery_policy.cpp src/so101_gazebo_demo/test/pick_place/test_pick_place_runner.cpp src/so101_gazebo_demo/test/pick_place/test_so101_world_reset.cpp
git commit -m "fix(so101): hold unsafe recovery outcomes"
```

### Task 11: Expose bounded final evidence through Teleop without duplicating policy

**Files:**
- Modify: `src/so101_gazebo_demo/so101_teleop/models.py`
- Modify: `src/so101_gazebo_demo/so101_teleop/server.py`
- Modify: `src/so101_gazebo_demo/so101_teleop/telemetry.py`
- Modify: `src/so101_gazebo_demo/so101_teleop/workflow_gateway.py`
- Modify: `src/so101_gazebo_demo/so101_teleop/openapi.json`
- Modify: `src/so101_gazebo_demo/test/teleop/{test_models,test_telemetry,test_workflow_gateway,test_server_safety,test_openapi_export}.py`

**Interfaces:**
- Produces `PhysicalOutcomeEvidence` on `/snapshot` and workflow result: epoch id, first/last sequence, sample count/duration, aggregate metrics, final pose, support/gripper contacts, both attachment states, sync status, and primary failure.
- Does not implement transitions, thresholds, or final predicates in Python.

- [ ] **Step 1: Write RED API tests**

Add:

```text
test_snapshot_exposes_bounded_physical_outcome_evidence
test_workflow_accepts_new_states_without_python_transition_table
test_force_continue_rejects_final_outcome_and_shadow_failures
test_final_failure_metrics_survive_cpp_checkpoint_transport
test_openapi_contains_physical_outcome_evidence_schema
```

- [ ] **Step 2: Run RED with the project Python test command**

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select pick_place_common so101_gazebo_demo --symlink-install
PYTHONNOUSERSITE=1 colcon test --packages-select so101_gazebo_demo --ctest-args -R '^test_teleop_(models|telemetry|workflow_gateway|server_safety|openapi_export)$' --event-handlers console_direct+
colcon test-result --verbose
```

Expected RED: Pydantic/OpenAPI models lack physical outcome fields.

- [ ] **Step 3: Add transport-only models and parsing**

Parse C++ checkpoint/run output into bounded evidence. Keep `WorkflowGateway` transition-free. Extend blocked override prefixes with `FINAL_PLACEMENT_` and `PLANNING_SHADOW_`; only the existing `PHYSICAL_GRASP_` override boundary remains eligible.

- [ ] **Step 4: Regenerate OpenAPI using the existing exporter and run GREEN**

```bash
source /opt/ros/jazzy/setup.zsh
PYTHONNOUSERSITE=1 python3 -m so101_teleop.openapi_export --output src/so101_gazebo_demo/so101_teleop/openapi.json
colcon build --packages-select pick_place_common so101_gazebo_demo --symlink-install
PYTHONNOUSERSITE=1 colcon test --packages-select so101_gazebo_demo --ctest-args -R '^test_teleop_(models|telemetry|workflow_gateway|server_safety|openapi_export)$' --event-handlers console_direct+
colcon test-result --verbose
```

If the exporter invocation differs, stop and discover it from `test_openapi_export.py`; do not invent a new generator.

- [ ] **Step 5: Commit**

```bash
git add src/so101_gazebo_demo/so101_teleop/models.py src/so101_gazebo_demo/so101_teleop/server.py src/so101_gazebo_demo/so101_teleop/telemetry.py src/so101_gazebo_demo/so101_teleop/workflow_gateway.py src/so101_gazebo_demo/so101_teleop/openapi.json src/so101_gazebo_demo/test/teleop/test_models.py src/so101_gazebo_demo/test/teleop/test_telemetry.py src/so101_gazebo_demo/test/teleop/test_workflow_gateway.py src/so101_gazebo_demo/test/teleop/test_server_safety.py src/so101_gazebo_demo/test/teleop/test_openapi_export.py
git commit -m "feat(so101): expose final outcome evidence"
```

### Task 12: Complete package contracts and operator documentation

**Files:**
- Modify: `docs/pick-place-architecture.md`
- Modify: `docs/pick-place-launch-parameters.md`
- Modify: `src/pick_place_common/README.md`
- Modify: `src/so101_gazebo_demo/README.md`
- Modify: `.agents/skills/so101-dev/SKILL.md`
- Modify: `.agents/skills/so101-dev/references/{so101-system-map,test-and-acceptance}.md`
- Modify: `src/so101_gazebo_demo/test/{test_source_manifest.py,test_so101_launch_contract.py,test_package_layout.py}`
- Modify: `src/pick_place_common/test/test_package_contract.py`

**Interfaces:**
- Produces installed/source manifest coverage and accurate operator evidence guidance.

- [ ] **Step 1: Write RED package/launch assertions**

Assert new source/header installation, schema-2 policy, exact SO-101 trace documentation, absence of normal Gazebo attach/detach claims, and continued reset detach support.

- [ ] **Step 2: Run RED**

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select pick_place_common so101_gazebo_demo --symlink-install
PYTHONNOUSERSITE=1 colcon test --packages-select pick_place_common so101_gazebo_demo --ctest-args -R '^(test_package_contract|test_source_manifest|test_so101_launch_contract|test_package_layout)$' --event-handlers console_direct+
colcon test-result --verbose
```

Expected RED: manifests/docs do not describe/install the new components.

- [ ] **Step 3: Update docs and manifests**

Document physics ownership, new states, `CALIBRATION_REQUIRED`, non-resumable release epoch, failure codes, independent Gazebo/MoveIt/controller/contact/visual evidence, and five-run rule. Explicitly list rejected R3 routes. Do not edit this implementation plan or design semantics.

- [ ] **Step 4: Run GREEN and commit**

```bash
colcon build --packages-select pick_place_common so101_gazebo_demo --symlink-install
PYTHONNOUSERSITE=1 colcon test --packages-select pick_place_common so101_gazebo_demo --ctest-args -R '^(test_package_contract|test_source_manifest|test_so101_launch_contract|test_package_layout)$' --event-handlers console_direct+
colcon test-result --verbose
git add docs/pick-place-architecture.md docs/pick-place-launch-parameters.md src/pick_place_common/README.md src/so101_gazebo_demo/README.md .agents/skills/so101-dev/SKILL.md .agents/skills/so101-dev/references/so101-system-map.md .agents/skills/so101-dev/references/test-and-acceptance.md src/pick_place_common/test/test_package_contract.py src/so101_gazebo_demo/test/test_source_manifest.py src/so101_gazebo_demo/test/test_so101_launch_contract.py src/so101_gazebo_demo/test/test_package_layout.py
git commit -m "docs(so101): document physical outcome evidence"
```

### Task 13: Run automated verification on the actual branch tree

**Files:**
- Modify only if a test exposes a proven defect: the owning source plus its failing regression test.
- Modify checkpoint after verification: `docs/experiments/so101-reset-world-five-success-experiment-ledger.md`

**Interfaces:**
- Produces fresh branch-tree build/test/quality evidence before live calibration.

- [ ] **Step 1: Confirm Bun and cleanly rebuild the actual branch**

```bash
command -v bun
bun --version
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --symlink-install --cmake-clean-cache
source install/setup.zsh
ros2 pkg prefix pick_place_common
ros2 pkg prefix panda_gazebo_demo
ros2 pkg prefix so101_gazebo_demo
stat install/so101_gazebo_demo/lib/so101_gazebo_demo/pick_place_state_machine
```

Expected: build exits 0 and all prefixes point to this workspace overlay.

- [ ] **Step 2: Run full package tests and read-only quality gates**

```bash
PYTHONNOUSERSITE=1 colcon test --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --event-handlers console_direct+
colcon test-result --verbose
```

Expected: zero failures. The configured C++ quality gate may run `ament_uncrustify` read-only; never pass `--reformat`.

- [ ] **Step 3: Exercise dry-run and fail-closed plan-only before calibration**

```bash
ros2 launch so101_gazebo_demo so101_pick_place.launch.py --show-args
ros2 launch so101_gazebo_demo so101_pick_place.launch.py run_mode:=dry_run start_simulation:=false
ros2 launch so101_gazebo_demo so101_pick_place.launch.py run_mode:=plan_only start_simulation:=false
```

Expected: dry-run trace contains the new SO-101 states and no forward Gazebo states; uncalibrated plan-only exits nonzero with `PHYSICAL_OUTCOME_CALIBRATION_REQUIRED` before mutation.

- [ ] **Step 4: Apply the systematic-debugging checkpoint on any unexpected result**

Do not patch immediately. Save command/output/exit code, identify first bad layer, compare source/install/runtime provenance, state one hypothesis in the ledger, create a failing regression test, then repeat RED/GREEN in a new focused commit.

- [ ] **Step 5: Record verification checkpoint and commit it**

Record commands, exits, package prefixes, actual test counts, dirty paths, and next calibration experiment. Never write “all pass” without the fresh outputs above.

```bash
git add docs/experiments/so101-reset-world-five-success-experiment-ledger.md
git commit -m "docs(so101): checkpoint physical outcome verification"
```

### Task 14: Calibrate every new threshold without changing approved semantics

**Files:**
- Modify: `src/so101_gazebo_demo/config/validation_policies/light_cup_wall_pick.yaml`
- Modify: `docs/experiments/so101-reset-world-five-success-experiment-ledger.md`
- Modify tests only for the resulting exact config contract: `src/so101_gazebo_demo/test/pick_place/test_policy_config.cpp`

**Interfaces:**
- Consumes raw isolated Gazebo observations and existing hard safety ceilings.
- Produces evidence-backed finite policy values replacing every sentinel as one frozen parameter set.

- [ ] **Step 1: Create `CAL-PHYSICAL-001` as `PLANNED` before running**

The entry must include hypothesis, prediction, `single_variable: observation-only calibration`, lifecycle, preconditions, success/failure/invalid criteria, source commit, absolute install overlay/executable, unique ROS domain, unique Gazebo partition, commands, and evidence paths. Calibration runs cannot count toward the five successes.

- [ ] **Step 2: Allocate isolated runtime identifiers and launch only owned processes**

Choose unused values after inspecting current graph; do not copy placeholders literally:

```bash
candidate_domain=$(( $(od -An -N2 -tu2 /dev/urandom) % 200 + 20 ))
export ROS_DOMAIN_ID=$candidate_domain
export GZ_PARTITION=so101-physical-outcome-$(uuidgen)
export ROS_LOG_DIR=$evidence_root/calibration/ros
mkdir -p "$ROS_LOG_DIR"
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_moveit/install/setup.zsh
timeout 2 ros2 node list
```

Expected before launch: the candidate ROS domain contains no nodes. If it is occupied, generate another candidate and repeat. Record the selected values and all PIDs/tmux panes. Never kill preserved processes or use broad `pkill`/`killall`.

- [ ] **Step 3: Gather calibration distributions, not success claims**

Use bounded stop-after/single-state observations and controlled reset transactions to measure target XY region, support height, upright tilt, derived speeds, settle timing/sample cadence, telemetry capacity, catastrophic-loss boundary observability, and shadow divergence pairing. Each threshold needs source samples, distribution summary, conservative margin, and proof it does not relax an existing collision/penetration ceiling.

- [ ] **Step 4: Mark invalid data correctly**

If provenance, initial state, controller, contact topic, session, duplicate stack, or screenshot timing is wrong, mark the experiment `INVALID`, stop the batch, and do not derive a value. Invoke systematic debugging for unexpected runtime behavior.

- [ ] **Step 5: Replace all sentinels in one frozen policy change**

Only after ledger evidence exists, replace every `CALIBRATION_REQUIRED`. Add YAML comments referencing calibration experiment ids. No field may remain unresolved; no existing safety number may be increased.

- [ ] **Step 6: RED/GREEN the calibrated config and commit**

First change the exact config expectation so it fails against sentinels; then update YAML and run:

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select pick_place_common so101_gazebo_demo --symlink-install
PYTHONNOUSERSITE=1 colcon test --packages-select so101_gazebo_demo --ctest-args -R '^(test_policy_config|test_configuration_contract)$' --event-handlers console_direct+
colcon test-result --verbose
git add src/so101_gazebo_demo/config/validation_policies/light_cup_wall_pick.yaml src/so101_gazebo_demo/test/pick_place/test_policy_config.cpp docs/experiments/so101-reset-world-five-success-experiment-ledger.md
git commit -m "config(so101): calibrate physical outcome policy"
```

### Task 15: Validate headless runtime, GUI evidence, and five consecutive physical outcomes

**Files:**
- Modify: `docs/experiments/so101-reset-world-five-success-experiment-ledger.md`
- Store raw evidence only under the campaign `/tmp` root and ignored screenshot capture directory.

**Interfaces:**
- Produces independent runtime evidence and the only acceptable five-run claim.

- [ ] **Step 1: Rebuild/retest the calibrated commit and freeze campaign provenance**

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --symlink-install --cmake-clean-cache
source install/setup.zsh
PYTHONNOUSERSITE=1 colcon test --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --event-handlers console_direct+
colcon test-result --verbose
ros2 pkg prefix so101_gazebo_demo
git rev-parse HEAD
git status --short
```

Expected: zero failures and a frozen clean source commit/policy fingerprint before counting runs.

- [ ] **Step 2: Run dry-run then plan-only evidence stages**

Dry-run must show the exact new trace and no normal Gazebo states. Plan-only must prove valid plans and shadow gate availability but is not physical success. Save full commands, exit codes, session ids, plan artifacts, and controller/scene provenance.

- [ ] **Step 3: Run one isolated headless execute qualification**

Create a `PLANNED -> RUNNING -> VALID|INVALID` ledger entry before launch. Require independent evidence for:

```text
controller/action result and joint/TCP change
Gazebo cup 6D pose sequence and derived speeds
fresh bottom-to-table support contact
no gripper contact after release
Gazebo detached throughout normal forward path
MoveIt attached only as carry shadow, detached before OPEN_GRIPPER
shadow divergence below hard limit before every carrying plan
final MoveIt world object synchronized to frozen Gazebo pose
forbidden collision and penetration ceilings never exceeded
```

Headless success qualifies the GUI stage but does not count toward the final five unless the campaign lifecycle explicitly matches the frozen five-run batch.

- [ ] **Step 4: Run GUI qualification with fresh visual evidence**

In an owned tmux shell load `~/gui-env.zsh`, ROS Jazzy, and the exact overlay. Run `tile_ai_station_guis.py`, require `LAYOUT_OK`, then capture a baseline. Execute one run, capture a new post-action image, and actually inspect it. Record visible robot posture, open gripper, cup final position/uprightness, absence of fall/penetration, and RViz/Gazebo consistency. Follow `snapshot -> action -> fresh snapshot`; never reuse a CUA element index.

- [ ] **Step 5: Execute a fresh five-consecutive-run batch**

Create five monotonic experiment ids before each run, all with the same commit, policy fingerprint, overlay, lifecycle, success contract, and isolated runtime identity. For each run record the exact fields from Task 1 plus epoch marker, count/duration, final pose, XY/height/tilt/speeds, support/gripper contact, both detach facts, sync fact, carry distributions, maximum shadow divergence, controller result, trace, hard-gate metrics, and fresh screenshot.

Counting rules:

```text
VALID success: extends the consecutive sequence
VALID failure: enters the denominator and ends the sequence
INVALID contamination: does not enter the denominator but ends the batch
```

Do not claim success until five consecutive `VALID` successes exist. Intermediate samples may differ; final stable outcome and all hard invariants must pass every time.

- [ ] **Step 6: Preserve failure evidence and debug one variable at a time**

On failure, do not auto-open a held unsupported cup and do not reset before evidence freeze. Mark the experiment, save all six evidence layers, then start a separate reset transaction. Invoke systematic debugging; any code fix requires a new RED/GREEN task commit and invalidates the frozen five-run batch.

- [ ] **Step 7: Clean up only owned processes and commit the final ledger checkpoint**

Stop only recorded PIDs/tmux sessions. Re-list ROS nodes/processes and record preserved processes. Commit ledger evidence separately:

```bash
git add docs/experiments/so101-reset-world-five-success-experiment-ledger.md
git commit -m "docs(so101): record physical outcome acceptance"
```

### Task 16: Final branch verification, scoped publication, safe main merge, and remote verification

**Files:**
- No source changes expected.
- Modify only the ledger if recording final provenance/checkpoint is required.

**Interfaces:**
- Produces verified branch SHA, pushed feature branch, safely merged/pushed main, and verified remote SHA under the user's already granted authorization.

- [ ] **Step 1: Invoke verification-before-completion and inspect exact scope**

```bash
git status --short
git log --oneline --decorate origin/main..HEAD
git diff --check origin/main...HEAD
git diff --stat origin/main...HEAD
git diff --name-status origin/main...HEAD
```

Expected: only approved implementation, tests, config, docs, skill updates, and the continued ledger. No build/install/log/screenshot/generated web bundle or unrelated user files.

- [ ] **Step 2: Re-run the full actual-branch verification**

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --symlink-install --cmake-clean-cache
source install/setup.zsh
PYTHONNOUSERSITE=1 colcon test --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --event-handlers console_direct+
colcon test-result --verbose
git diff --check origin/main...HEAD
```

Expected: build exit 0, zero test failures, diff check exit 0. Also verify the ledger contains five consecutive valid final-outcome runs from the current HEAD/policy; otherwise stop without publication claim.

- [ ] **Step 3: Push only the feature branch to Gitee**

```bash
feature_branch=$(git branch --show-current)
test "$feature_branch" = codex/so101-physical-outcome-validation
feature_sha=$(git rev-parse HEAD)
git push origin "$feature_branch"
git ls-remote origin "refs/heads/$feature_branch"
```

Expected: remote feature SHA equals `$feature_sha`. Do not use `gh`.

- [ ] **Step 4: Apply the safe main merge gate**

Before touching main, fetch and verify there are no unexpected remote changes or dirty main worktree:

```bash
git fetch origin main
git rev-parse origin/main
git worktree list --porcelain
```

Locate the existing main worktree from `git worktree list`; do not assume a path. In that worktree require `git status --short` empty. If `origin/main` moved since the implementation base, stop, merge/rebase only with a reviewed conflict plan, and rerun all branch tests. If unchanged and main is an ancestor of the feature branch, merge with:

```bash
git merge --ff-only codex/so101-physical-outcome-validation
```

No force push, reset, checkout-over-dirty-worktree, or automatic conflict resolution.

- [ ] **Step 5: Run merged-tree tests before pushing main**

From the clean main worktree:

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --symlink-install --cmake-clean-cache
source install/setup.zsh
PYTHONNOUSERSITE=1 colcon test --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --event-handlers console_direct+
colcon test-result --verbose
git status --short
```

Expected: build/test success and clean main. Unexpected failures trigger systematic debugging; do not push.

- [ ] **Step 6: Push main under the user's granted authorization and verify remote SHA**

```bash
main_sha=$(git rev-parse HEAD)
git push origin main
remote_main_sha=$(git ls-remote origin refs/heads/main | awk '{print $1}')
test "$remote_main_sha" = "$main_sha"
printf 'main_sha=%s\nremote_main_sha=%s\n' "$main_sha" "$remote_main_sha"
```

Expected: push exits 0 and the remote SHA exactly equals the locally tested merged-tree SHA.

- [ ] **Step 7: Report evidence, not inference**

Report feature SHA, main SHA, remote SHA, exact build/test commands and counts, five-run experiment ids, screenshot paths, preserved processes, and any remaining risk. Do not claim physical success from `DONE`, MoveIt success, plan-only, headless logs, or screenshots alone.

## 2026-08-08 approved support-evidence amendment

用户已明确批准 `DBG-PHYSICAL-001` 所要求的窄化修订。以下步骤插入 Task 14，必须在任何重新校准
或 execute 前完成；本段修改与文件开头来源未确认的空行无关，该空行必须原样保留：

1. 在 policy schema 增加严格 finite、`<= 0` 的
   `physical_outcome.minimum_support_contact_depth_m` sentinel/解析/序列化字段；production 数值只能
   来自新的有效 live calibration，不能复制测试向量。
2. RED：扩展 `test_gazebo_world_observer.cpp`，证明 Featherstone compound owner 的真实
   task-object/table contact 在 depth 位于配置 noise bound 内时成为 intended support；缺失、
   non-finite、比 bound 更负的 depth 必须拒绝，并保留原始 collision/depth metrics。现有专用
   bottom-topic 正例继续通过。
3. GREEN：`GazeboWorldObserver` 同时订阅专用 bottom topic 与已知 compound-owner contact stream，
   但只有 counterparty 精确匹配 `intended_support_collision` 的真实 contact 才可成为 support。
   finger/contact freshness 继续独立；不得从 pose/height/MoveIt 推断 support。
4. 增加 world/launch contract，锁定 production Bullet Featherstone owner mapping；不得修改 engine、
   geometry、mass、friction、controller 或 motion target。
5. 以一个逻辑提交完成上述 regression 和最小实现；定向 observer/policy/config/launch tests、包级测试
   和 `git diff --check` 全部 GREEN 后，创建新的 calibration experiment。任何意外失败继续调用
   systematic-debugging，不能叠加修改。
6. 新 calibration 必须独立测量稳定 owner-contact depth 分布并给出保守 margin；该 noise bound 只
   决定 support sample 的数值有效性，不改变既有 collision/penetration safety ceilings。随后才校准
   Task 14 的其他 sentinel，并继续 Task 15/16 的 headless、GUI、五次连续成功、push/merge gates。

批准后仍不允许：forward Gazebo attach/detach、MoveIt shadow 驱动 Gazebo、off-support 自动 open、
R3 已证伪路线、安全 gate 放宽，或修改旧
`docs/experiments/so101-reset-world-five-success-experiment-ledger.md`。

## Spec coverage self-review

- Sections 1–4: Tasks 2, 7, and 8 establish physics ownership, shared/Panda compatibility, and the exact SO-101 state graph.
- Section 5: Tasks 4, 6, and 9 add timestamped independent evidence, release epoch isolation, and checkpoint semantics.
- Sections 6–8: Tasks 5 and 7 distinguish bounded telemetry from immutable hard gates and implement shadow divergence.
- Section 9: Task 10 implements hold-first recovery, final evidence preservation, and separate reset cleanup.
- Section 10: Tasks 3 and 14 provide strict schema, fail-closed sentinels, and evidence-backed calibration without invented values.
- Section 11: Tasks 2–13 cover unit, contract, package, dry-run, plan-only, and compatibility tests with explicit RED/GREEN commands.
- Section 12: Tasks 1, 14, and 15 continue the existing ledger and enforce five consecutive valid physical outcomes.
- Section 13: Tasks 2, 8, 9, 11, 12, and 16 cover migration, Teleop, rollout, branch publication, safe main merge, merged-tree tests, and remote SHA proof.
- Section 14: Global constraints and Tasks 7, 10, and 14 explicitly exclude every rejected R3 route and safety relaxation.
- Section 15: Locked decisions resolve region shape, speed derivation, failure precedence, final pose, non-resumable epoch, evidence handoff, bounded metrics, collision identity, and calibration protocol without altering approved semantics.

## Approved execution addendum: bounded grasp/motion target calibration (2026-08-08)

This addendum resumes the blocked checkpoint at baseline HEAD `2eda34c`; it does not change Tasks 1–16
physical ownership or hard-safety semantics. Exclude
`docs/experiments/so101-reset-world-five-success-experiment-ledger.md` from every future add. Use only the new
physical-outcome ledger. Preserve and do not stage the pre-existing leading blank-line diff in this file.

### Ordered TDD calibration workflow

1. Commit authorization, baseline and matrix documentation separately.
2. Execute A TCP translation (x,y,z), B orientation (roll,pitch,yaw), C q6, D micro-lift, E carry/place/
   retreat, F timing/scaling. One candidate changes exactly one scalar; a layer advances only after the previous
   layer removes the current first hard-gate failure.
3. Each candidate starts with an exact named unit/config RED. Apply minimal target/config plumbing, rerun focused
   GREEN and make one logical commit. Unexpected failure invokes systematic-debugging before another change.
4. Clean build, source, verify `ros2 pkg prefix so101_gazebo_demo`, and run full `plan_only`. Only then run an
   owned `execute stop_after:=<earliest-boundary>` with isolated FULL_RESTART provenance.
5. Ledger transition is `PLANNED -> RUNNING -> VALID_FAILURE|VALID_SUCCESS` or `INVALID`, with unique id,
   domain, partition, source SHA, config hash and `/tmp` evidence root. Valid failure eliminates the candidate;
   invalid ends the batch. Never repeat a candidate to select a random success.
6. Rank only all-hard-gate-passing candidates by greatest worst normalized safety margin. Freeze the winner for
   at least three FULL_RESTART qualifications. Any valid failure returns to the layer; three failed candidates in
   one direction stop the search.
7. After short-path qualification, run full headless final outcome, a genuine fresh three-package clean-cache
   build/full suite, dry-run, plan-only, headless, GUI/CUA fresh screenshot and five consecutive frozen-policy
   successes. No push/merge before all five.

Design §17.2–17.3 is the authoritative baseline/range table. The first A-x candidate moves only TCP x from
`0.020676684 m` to cup-center `0.020000000 m` (`-0.000676684 m`, inside the existing `0.001 m` bound).

```text
RED test: SO101FixedMotionTargets.GraspTcpXCandidateMovesTowardCupCenterOnly
RED command: colcon test --packages-select so101_gazebo_demo --ctest-args -R test_so101_fixed_motion_targets --output-on-failure
Expected RED: FK x remains baseline; assertions require cup-center x while y/z/orientation remain baseline.
GREEN scope: the exact DESCEND endpoint and paired LIFT/recovery endpoint target plus validation endpoint only.
GREEN command: the same focused test, followed by clean build/source/prefix and full plan_only before execute.
```

If IK cannot preserve y/z/orientation and all existing path/collision contracts, record a plan-only valid failure;
do not compensate by changing a second scalar or any ceiling.

## Approved execution addendum: release-stage orientation telemetry and GUI qualification (2026-08-10)

This addendum implements Design §18 and supersedes the earlier detach-before-open ordering. It changes only
release-phase validation semantics; the EXP081 motion targets and every listed physics/controller/safety value
remain fixed.

### Task 17: Make release-stage orientation telemetry-only while preserving final pose validation

**Files:**
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_motion_planner.hpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/so101_motion_planner.cpp`
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_attachment_contracts.hpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/so101_attachment_contracts.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/so101_joint_motion_adapter.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/pick_place_runtime.cpp`
- Test: `src/so101_gazebo_demo/test/pick_place/test_so101_motion_planner.cpp`
- Test: `src/so101_gazebo_demo/test/pick_place/test_so101_joint_motion_adapter.cpp`
- Test: `src/so101_gazebo_demo/test/pick_place/test_so101_attachment_contracts.cpp`
- Test: `src/so101_gazebo_demo/test/pick_place/test_so101_pick_place_runtime.cpp`
- Verify existing: `src/so101_gazebo_demo/test/pick_place/test_final_placement_evaluator.cpp`
- Update: `docs/experiments/so101-physical-outcome-validation-experiment-ledger.md`

**Interfaces:**
- Produces: `usesAttachedPlanningShadow(State) noexcept` and
  `enforcesPlanningShadowOrientation(State) noexcept`.
- Changes: `evaluatePlanningShadowDivergence` accepts state and always evaluates position while making
  orientation failure state-aware.
- Preserves: final `max_upright_tilt_rad` evaluation and every non-orientation safety gate.

- [ ] **Step 1: Write RED behavior tests**

Add tests with hand-derived fixtures:

```cpp
TEST(SO101JointMotionAdapter, ReleaseDescentAllowsShadowTiltButStillRejectsPositionDivergence);
TEST(SO101JointMotionAdapter, LiftStillRejectsTheSameShadowTilt);
TEST(SO101MotionPlanner, RetreatUsesAttachedPlanningShadowAfterPhysicalRelease);
TEST(SO101AttachmentContracts, ReleaseStageShadowOrientationIsTelemetryOnly);
TEST(SO101PickPlaceRuntime, RetreatAllowsReleasedCupToRemainOnSupportWhileShadowStaysAttached);
```

The production mutation caught by these tests is treating all attached-shadow states as physical carrying with
one global orientation predicate.

- [ ] **Step 2: Run RED and record the expected failures**

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --base-paths src/so101_gazebo_demo --packages-select so101_gazebo_demo --cmake-args -DBUILD_TESTING=ON
ctest --test-dir build/so101_gazebo_demo -R 'test_so101_(motion_planner|joint_motion_adapter|attachment_contracts|pick_place_runtime)' --output-on-failure
```

Expected: release-descent angle and retreat attached-shadow assertions fail against `b021d5a`; the LIFT and
position controls remain GREEN.

- [ ] **Step 3: Implement the minimal state-aware semantics**

Implement exact state behavior:

```cpp
usesAttachedPlanningShadow(LIFT | MOVE_ABOVE_PLACE | DESCEND_TO_PLACE |
                           RECOVER_* carrying states | RETREAT) == true;
enforcesPlanningShadowOrientation(DESCEND_TO_PLACE | RETREAT) == false;
```

Use the first predicate for MoveIt attached scene/path validation. Use the second only for the orientation
failure branch; continue recording orientation metrics. In `MotionContract`, make RETREAT object motion
telemetry-only because Gazebo physics owns the released cup; do not reuse that exception for other detached
motions.

- [ ] **Step 4: Run focused GREEN, package tests and build provenance checks**

```bash
ctest --test-dir build/so101_gazebo_demo -R 'test_so101_(motion_planner|joint_motion_adapter|attachment_contracts|pick_place_runtime)|test_final_placement_evaluator' --output-on-failure
ctest --test-dir build/so101_gazebo_demo --output-on-failure
source /data/work/ws_moveit/.worktrees/so101-physical-outcome-validation/install/setup.zsh
ros2 pkg prefix so101_gazebo_demo
sha256sum build/so101_gazebo_demo/pick_place_state_machine install/so101_gazebo_demo/lib/so101_gazebo_demo/pick_place_state_machine
```

Expected: all package tests pass, final tipped-cup rejection remains GREEN, and build/install executable hashes
match.

- [ ] **Step 5: Run one GUI FULL_RESTART qualification**

Pre-register a unique experiment, verify empty domain/partition and no existing stack, then create one tmux-held
GUI process after sourcing `~/gui-env.zsh`, Jazzy and this worktree overlay. Launch with `run_mode:=execute`,
`start_simulation:=true`, `headless:=false`, unique `simulation_session_id`, checkpoint and diagnostics paths.
Capture a fresh baseline and terminal screenshot with `scripts/capture-ai-station.sh`; freeze Gazebo pose,
attachment topic, MoveIt scene, controller and joint evidence before stopping only the owned tmux process tree.

- [ ] **Step 6: Record the result and commit the scoped change**

Update the experiment from `PLANNED -> RUNNING -> VALID|INVALID`, add a checkpoint, run `git diff --check`,
stage only Design §18, this plan addendum, scoped source/tests and the physical-outcome ledger, then commit:

```bash
git commit -m "fix(so101): validate cup pose after physical release"
```

Do not push, merge, run a second experiment, or claim five-run acceptance in this task.
