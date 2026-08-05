# Refactor Optimization R2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make recovery skip, request-state validation, and runner behavior policies consistent and explicit across fresh execution, resume, SO-101, and Panda while preserving R1 safety semantics.

**Architecture:** `pick_place_common` owns workflow mechanics and explicit policy decisions; robot packages own geometry, controller, and safe-recovery predicates. Recovery selection and skip disposition pass through one common routing boundary, and request state scopes are validated once against `WorkflowDefinition`.

**Tech Stack:** C++17, ROS 2 Jazzy, MoveIt 2, Gazebo Harmonic, ament/colcon, GoogleTest, pytest, launch_testing.

## Global Constraints

- Base work on the latest `origin/main` fetched with `git fetch origin --prune`; do not pull, merge, rebase, push, or modify the root checkout during implementation setup.
- Use a new isolated ai-station worktree/branch for R2; never operate `codex-cua` or another worktree.
- Preserve R1's complete skip predicate and exact original failure.
- Do not move SO-101 safe-home, joint-6, gripper, table, object-pose, attachment, or tolerance policy into common.
- Do not change valid launch/CLI spelling, plan-only whitelist, predecessor execution, target-only planning, checkpoint schema, provenance field, or session semantics.
- Use TDD for every task and retain RED and GREEN logs.
- Do not start a second ROS/Gazebo/MoveIt stack; identify and clean only owned or conflicting ROS processes.

---

### Task 1: Make recovery skip stable across execute-resume

**Files:**
- Modify: `src/pick_place_common/src/runner.cpp:301-345,738-765`
- Test: `src/pick_place_common/test/test_run_to_plan_only.cpp`
- Test: `src/so101_gazebo_demo/test/pick_place/test_pick_place_runner.cpp:1030-1050`
- Test: `src/so101_gazebo_demo/test/pick_place/test_so101_recovery_policy.cpp`

**Interfaces:**
- Consumes: `IRecoveryPolicy::select(State, const Failure &, const WorldSnapshot &)` and `IRecoveryPolicy::canSkipRecoveryAction(State, const Failure &, State, const WorldSnapshot &)`.
- Produces: one common recovery-route execution path that returns the original `Failure` without invoking an action when the selected action is skippable.

- [ ] **Step 1: Add a failing common runner test for recovery resume disposition**

Add a recovery policy fixture whose `select()` returns `RECOVER_RETREAT`, whose
`canSkipRecoveryAction()` records arguments and returns true, and an executor whose call count is
observable. Add this assertion shape:

```cpp
TEST(RunToPlanOnly, RecoveryResumeSkipsSelectedActionAndPreservesOriginalFailure)
{
  // Seed a RECOVERY checkpoint with failed_state, original_failure,
  // next_state=RECOVER_RETREAT, and a fresh canonical snapshot.
  const auto result = runner.run(executeResumeRequest());

  EXPECT_EQ(RunStatus::ERROR, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ(original_failure.category, result.failure->category);
  EXPECT_EQ(original_failure.code, result.failure->code);
  EXPECT_EQ(original_failure.message, result.failure->message);
  EXPECT_EQ(original_failure.metrics, result.failure->metrics);
  EXPECT_EQ(0, retreat_executor.calls);
  EXPECT_EQ((std::vector<State>{State::RECOVER_RETREAT, State::ERROR}), result.state_trace);
}
```

- [ ] **Step 2: Run the focused test and retain RED evidence**

Run:

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select pick_place_common --symlink-install
source install/setup.zsh
build/pick_place_common/test_run_to_plan_only \
  --gtest_filter='RunToPlanOnly.RecoveryResumeSkipsSelectedActionAndPreservesOriginalFailure'
```

Expected: FAIL because the retreat executor is called once.

- [ ] **Step 3: Apply the skip predicate at the recovery route boundary**

After `select()` validates `route.next_state` in `runResume`, evaluate the selected action against the
same failed state, original failure, and current snapshot before calling `runExecuteWorkflow`:

```cpp
const State selected = *route.next_state;
if (recovery_policy_->canSkipRecoveryAction(
      *checkpoint.failed_state, *checkpoint.original_failure, selected, snapshot)) {
  return {RunStatus::ERROR,
          State::ERROR,
          std::nullopt,
          *checkpoint.original_failure,
          0,
          {selected, State::ERROR}};
}
return runExecuteWorkflow(selected, request, snapshot, checkpoint.sequence + 1, 0,
                          CheckpointPhase::RECOVERY, checkpoint.failed_state,
                          checkpoint.original_failure);
```

Extract a private helper only if it removes the duplicated fresh/resume disposition without changing
trace or transition-count semantics.

- [ ] **Step 4: Add SO-101 positive and negative integration coverage**

Preserve the existing ordinary execute-failure expectation at
`RecoveryResumeReclassifiesFromCurrentFactsInsteadOfCheckpointHistory`, then add a separate checkpoint
whose original failure is `PLAN_VALIDATION` with `plan_only_target_not_executed=1.0`. Assert zero
recovery executor calls for the complete safe predicate. Parameterize negative cases for category,
metric, freshness, stationary/home joints, Gazebo/MoveIt attachment facts, canonical poses/table,
gripper state, and selected action; assert the action is executed or the existing policy failure is
returned.

- [ ] **Step 5: Run focused GREEN tests**

Run:

```bash
colcon build --packages-select pick_place_common so101_gazebo_demo --symlink-install
source install/setup.zsh
build/pick_place_common/test_run_to_plan_only \
  --gtest_filter='*RecoveryResume*'
build/so101_gazebo_demo/test_pick_place_runner \
  --gtest_filter='*RecoveryResume*'
build/so101_gazebo_demo/test_so101_recovery_policy \
  --gtest_filter='*Skip*:*PlanOnly*'
```

Expected: all selected tests PASS, ordinary execute recovery still calls retreat, and only the complete
R1 plan-only predicate skips it.

- [ ] **Step 6: Commit the recovery change**

```bash
git add src/pick_place_common/src/runner.cpp \
  src/pick_place_common/test/test_run_to_plan_only.cpp \
  src/so101_gazebo_demo/test/pick_place/test_pick_place_runner.cpp \
  src/so101_gazebo_demo/test/pick_place/test_so101_recovery_policy.cpp
git commit -m 'fix(recovery): preserve safe plan-only skip on resume'
```

**Stop condition:** stop and request a semantic decision if any negative predicate must be weakened,
or if preserving the original failure requires a checkpoint schema/provenance change.

### Task 2: Centralize stop-after and fail-at state scopes

**Files:**
- Modify: `src/pick_place_common/src/run_request_validation.cpp:52-92`
- Test: `src/pick_place_common/test/test_run_request_validation.cpp`
- Modify: `src/panda_gazebo_demo/src/nodes/pick_place_state_machine_node.cpp:220-305`
- Modify: `src/so101_gazebo_demo/src/pick_place/pick_place_state_machine.cpp:65-100`
- Test: `src/panda_gazebo_demo/test/test_panda_launch_contract.py`
- Test: `src/so101_gazebo_demo/test/pick_place/test_dry_run.cpp`
- Modify: `docs/pick-place-launch-parameters.md:33-45`

**Interfaces:**
- Consumes: `WorkflowDefinition::action_states` and `WorkflowDefinition::forward_states`.
- Produces: stable failures `STOP_AFTER_STATE_NOT_ACTION` and `FAIL_AT_STATE_NOT_FORWARD_ACTION` from `validateRunRequest`.

- [ ] **Step 1: Add failing common request-validation tests**

Add these cases to `RejectsInvalidRequestsWithStableCodes`:

```cpp
pp::RunRequest terminal_stop;
terminal_stop.stop_after = pp::State::DONE;
expectFailureCode(workflow, terminal_stop, "STOP_AFTER_STATE_NOT_ACTION");

pp::RunRequest idle_stop;
idle_stop.stop_after = pp::State::IDLE;
expectFailureCode(workflow, idle_stop, "STOP_AFTER_STATE_NOT_ACTION");

pp::RunRequest recovery_fail;
recovery_fail.mode = pp::RunMode::DRY_RUN;
recovery_fail.fail_at = pp::State::RECOVER_RETREAT;
expectFailureCode(workflow, recovery_fail, "FAIL_AT_STATE_NOT_FORWARD_ACTION");

pp::RunRequest terminal_fail;
terminal_fail.mode = pp::RunMode::DRY_RUN;
terminal_fail.fail_at = pp::State::ERROR;
expectFailureCode(workflow, terminal_fail, "FAIL_AT_STATE_NOT_FORWARD_ACTION");
```

Also assert that every valid action `stop_after` and forward action `fail_at` remains accepted.

- [ ] **Step 2: Run the common validation test and retain RED evidence**

Run:

```bash
colcon build --packages-select pick_place_common --symlink-install
source install/setup.zsh
build/pick_place_common/test_run_request_validation
```

Expected: FAIL because current validation returns no failure for these scopes.

- [ ] **Step 3: Implement common state-scope checks**

Insert checks after mode-combination validation and before the plan-only early return:

```cpp
if (request.stop_after && !workflow.action_states.count(*request.stop_after)) {
  return configurationFailure("STOP_AFTER_STATE_NOT_ACTION",
                              "stop_after must name an action state in this workflow");
}
if (request.fail_at && !workflow.forward_states.count(*request.fail_at)) {
  return configurationFailure("FAIL_AT_STATE_NOT_FORWARD_ACTION",
                              "fail_at must name a forward action state in this workflow");
}
```

Exclude `workflow.initial_state` and terminal states even when they appear in `forward_states`; use
`action_states` plus the forward-success path to define a forward action.

- [ ] **Step 4: Align Panda and SO-101 entry-point tests**

Keep syntax parsing local, but make the common validator authoritative for semantic scope. Add CLI or
node tests that prove both robots reject `IDLE`, `DONE`, and `ERROR` for `stop_after`, and recovery or
terminal states for `fail_at`, while accepting one valid forward action and one valid recovery
`stop_after`.

Run:

```bash
PYTHONNOUSERSITE=1 pytest -q \
  src/panda_gazebo_demo/test/test_panda_launch_contract.py
build/so101_gazebo_demo/test_dry_run --gtest_filter='*Invalid*State*:*StopAfter*:*FailAt*'
ROS_LOG_DIR=/tmp/r2-invalid-stop-after \
  ros2 run so101_gazebo_demo pick_place_state_machine --mode dry_run --stop-after DONE
```

Expected: tests PASS; the live CLI exits nonzero, prints `STOP_AFTER_STATE_NOT_ACTION`, and prints no
full action trace.

- [ ] **Step 5: Document exact scopes and failure codes**

Update the common controls table so `stop_after` says “any nonterminal action in the workflow” and
`fail_at` says “dry-run forward action only”. Add an invalid-controls table with the two stable codes.

- [ ] **Step 6: Commit validation and documentation**

```bash
git add src/pick_place_common/src/run_request_validation.cpp \
  src/pick_place_common/test/test_run_request_validation.cpp \
  src/panda_gazebo_demo/src/nodes/pick_place_state_machine_node.cpp \
  src/panda_gazebo_demo/test/test_panda_launch_contract.py \
  src/so101_gazebo_demo/src/pick_place/pick_place_state_machine.cpp \
  src/so101_gazebo_demo/test/pick_place/test_dry_run.cpp \
  docs/pick-place-launch-parameters.md
git commit -m 'fix(cli): validate workflow control state scopes'
```

**Stop condition:** stop if existing users intentionally rely on terminal `stop_after` as an alias for
a full run; that is a new compatibility decision, not an implementation detail.

### Task 3: Replace policy nullness with explicit runner decisions

**Files:**
- Modify: `src/pick_place_common/include/pick_place_common/runner.hpp:18-51`
- Modify: `src/pick_place_common/src/runner.cpp:84-113,450-590,700-725,780-880`
- Test: `src/pick_place_common/test/test_common_runner.cpp`
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_runner_behavior_policy.hpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/so101_runner_behavior_policy.cpp`
- Test: `src/so101_gazebo_demo/test/pick_place/test_pick_place_runner.cpp`
- Modify: `docs/pick-place-architecture.md:18-32`

**Interfaces:**
- Consumes: existing Panda/null and SO-101 runtime behavior as characterization baselines.
- Produces: an explicit `IRunnerBehaviorPolicy` contract for preflight, recovery routing, observation retry, settle-wait, and failure preservation; no branch may use pointer presence as a robot decision.

- [ ] **Step 1: Characterize the old null and SO-101 behavior before interface edits**

Add tests covering: execute preflight, missing pre-execution observation, environment precondition,
transient post-observation, recovery-resume stationary wait, and original-failure wrapping. For each
case, record the expected status, failure code, state trace, observer calls, recovery-policy calls, and
executor calls for the Panda/null baseline and SO-101 policy baseline.

- [ ] **Step 2: Run characterization tests and save GREEN baseline**

Run:

```bash
colcon build --packages-select pick_place_common so101_gazebo_demo --symlink-install
source install/setup.zsh
build/pick_place_common/test_common_runner --gtest_filter='*BehaviorPolicy*'
build/so101_gazebo_demo/test_pick_place_runner --gtest_filter='*BehaviorPolicy*:*Observation*'
```

Expected: new characterization tests PASS against pre-refactor behavior.

- [ ] **Step 3: Write a compile-failing test for an explicit default policy**

Construct the runner with a named default policy object and assert it matches every Panda/null baseline
from Step 1. Expected RED is a missing explicit decision method or a result mismatch caused by current
pointer-presence branches.

- [ ] **Step 4: Expand the policy contract and provide one default object**

Name every current decision. The exact interface must express, at minimum:

```cpp
virtual bool runExecutePreflight() const noexcept = 0;
virtual bool recoverForwardObservationFailure() const noexcept = 0;
virtual bool preserveEnvironmentFailureWithoutRecovery() const noexcept = 0;
virtual bool retryTransientObservation(State, const Failure &, std::size_t) const = 0;
virtual bool waitForStationaryObjectOnResume() const noexcept = 0;
virtual bool preserveOriginalFailureOnRecoveryError() const noexcept = 0;
```

Keep the existing retry and trace methods. Define `DefaultRunnerBehaviorPolicy` to reproduce the old
Panda/null behavior. Make `StateMachineRunner` use a non-null default reference/object when the caller
does not supply a policy. Delete `NoRetryRunnerBehaviorPolicy`, or rename it only if it becomes this
tested exact default.

- [ ] **Step 5: Replace every pointer-presence branch**

Replace all `behavior_policy_`, `!behavior_policy_`, and guarded method checks in `runner.cpp` with a
named decision. Verify with:

```bash
rg -n 'behavior_policy_\s*[!&|=)]|!behavior_policy_|behavior_policy_ &&' \
  src/pick_place_common/src/runner.cpp
```

Expected: no pointer-nullness decision remains; only direct named policy calls remain.

- [ ] **Step 6: Run common/SO/Panda behavioral tests**

Run:

```bash
colcon build --packages-up-to panda_gazebo_demo so101_gazebo_demo --symlink-install
source install/setup.zsh
build/pick_place_common/test_common_runner
build/so101_gazebo_demo/test_pick_place_runner
ctest --test-dir build/panda_gazebo_demo --output-on-failure
```

Expected: all PASS; characterized Panda and SO-101 results are unchanged.

- [ ] **Step 7: Document the explicit behavior-policy boundary and commit**

Document each common decision and state that robot packages may override behavior but not embed robot
geometry in common.

```bash
git add src/pick_place_common/include/pick_place_common/runner.hpp \
  src/pick_place_common/src/runner.cpp \
  src/pick_place_common/test/test_common_runner.cpp \
  src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_runner_behavior_policy.hpp \
  src/so101_gazebo_demo/src/pick_place/so101_runner_behavior_policy.cpp \
  src/so101_gazebo_demo/test/pick_place/test_pick_place_runner.cpp \
  docs/pick-place-architecture.md
git commit -m 'refactor(common): make runner behavior decisions explicit'
```

**Stop condition:** stop if a named decision cannot reproduce both existing robot behaviors without
introducing robot identity checks or SO-101 geometry into common.

### Task 4: Make Panda motion-limit mapping resilient

**Files:**
- Modify: `src/panda_gazebo_demo/src/nodes/pick_place_state_machine_node.cpp:469-485`
- Test: `src/panda_gazebo_demo/test/pick_place/test_motion_plan_validation.cpp`
- Test: `src/panda_gazebo_demo/test/test_panda_launch_contract.py`

**Interfaces:**
- Consumes: the nine existing launch parameter values and `MotionPlanLimits` fields.
- Produces: named field assignment with unchanged values and defaults.

- [ ] **Step 1: Add a mapping characterization test**

Give every limit a distinct sentinel value and assert each lands in its named field:

```cpp
EXPECT_DOUBLE_EQ(0.91, limits.min_cartesian_fraction);
EXPECT_DOUBLE_EQ(0.12, limits.max_joint_jump);
EXPECT_DOUBLE_EQ(0.013, limits.max_lateral_deviation);
EXPECT_DOUBLE_EQ(0.014, limits.max_orientation_error_rad);
EXPECT_DOUBLE_EQ(0.015, limits.endpoint_position_tolerance);
EXPECT_DOUBLE_EQ(0.016, limits.endpoint_orientation_tolerance_rad);
EXPECT_DOUBLE_EQ(0.017, limits.carried_relative_position_tolerance);
EXPECT_DOUBLE_EQ(0.018, limits.carried_relative_orientation_tolerance_rad);
EXPECT_DOUBLE_EQ(0.019, limits.start_joint_tolerance);
```

- [ ] **Step 2: Replace the positional aggregate with named assignments**

```cpp
runtime_config.motion_plan_limits.min_cartesian_fraction = parameters.cartesian_min_fraction;
runtime_config.motion_plan_limits.max_joint_jump = parameters.joint_jump_threshold;
runtime_config.motion_plan_limits.max_lateral_deviation = parameters.tcp_position_tolerance;
runtime_config.motion_plan_limits.max_orientation_error_rad = parameters.tcp_orientation_tolerance_rad;
runtime_config.motion_plan_limits.endpoint_position_tolerance = parameters.tcp_position_tolerance;
runtime_config.motion_plan_limits.endpoint_orientation_tolerance_rad = parameters.tcp_orientation_tolerance_rad;
runtime_config.motion_plan_limits.carried_relative_position_tolerance = parameters.coke_position_tolerance;
runtime_config.motion_plan_limits.carried_relative_orientation_tolerance_rad = parameters.coke_orientation_tolerance_rad;
runtime_config.motion_plan_limits.start_joint_tolerance = parameters.motion_start_joint_tolerance;
```

- [ ] **Step 3: Run Panda focused tests and commit**

```bash
colcon build --packages-select panda_gazebo_demo --symlink-install
source install/setup.zsh
build/panda_gazebo_demo/test_motion_plan_validation
PYTHONNOUSERSITE=1 pytest -q src/panda_gazebo_demo/test/test_panda_launch_contract.py
git add src/panda_gazebo_demo/src/nodes/pick_place_state_machine_node.cpp \
  src/panda_gazebo_demo/test/pick_place/test_motion_plan_validation.cpp \
  src/panda_gazebo_demo/test/test_panda_launch_contract.py
git commit -m 'refactor(panda): name motion limit assignments'
```

Expected: all tests PASS and every launch/default value maps to the same field as before.

**Stop condition:** stop if the distinct-value test reveals that current launch-to-struct mapping is
already intentionally different from the field names; that requires a policy decision.

### Task 5: Run full automated, failure-injection, runtime, and visual gates

**Files:**
- Verify only: all files changed in Tasks 1-4
- Evidence directory: `/tmp/so101-refactor-optimization-r2-<timestamp>/`

**Interfaces:**
- Consumes: the committed R2 implementation and isolated worktree overlay.
- Produces: reproducible build/test/runtime/visual evidence and a clean scoped branch.

- [ ] **Step 1: Prove overlay provenance before runtime**

```bash
source /opt/ros/jazzy/setup.zsh
source install/setup.zsh
ros2 pkg prefix pick_place_common
ros2 pkg prefix panda_gazebo_demo
ros2 pkg prefix so101_gazebo_demo
git rev-parse HEAD
git status --short
```

Expected: all prefixes are inside the R2 worktree, HEAD is the R2 branch, and status is clean.

- [ ] **Step 2: Run clean three-package build and tests**

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-up-to panda_gazebo_demo so101_gazebo_demo \
  --symlink-install --cmake-clean-cache
source install/setup.zsh
PYTHONNOUSERSITE=1 colcon test \
  --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo \
  --event-handlers console_direct+
colcon test-result --verbose
```

Expected: 0 failures and 0 errors; skipped tests are listed and justified.

- [ ] **Step 3: Reproduce fresh SO-101 failure injection**

Start exactly one SO-101 Gazebo/MoveIt stack from a dedicated tmux window after loading
`~/gui-env.zsh`. Use the R1 fixture pattern with a motion-policy override that makes
`MOVE_ABOVE_OBJECT` fail plan validation. Run plan-only with
`plan_only_state=MOVE_ABOVE_OBJECT` and a new checkpoint/session.

Expected: predecessors execute, the target is planned but never executed,
`plan_only_target_not_executed=1`, the result preserves `TCP_ENDPOINT_OUTSIDE_TOLERANCE`, no retreat
command occurs, and Gazebo/MoveIt remain canonically detached at safe home.

- [ ] **Step 4: Explicitly execute-resume the produced recovery checkpoint**

Capture before and after joint states, TCP TF, Gazebo object pose/attachment, MoveIt planning scene,
controller state, checkpoint SHA-256, and session ID. Invoke the normal SO-101 execute-resume CLI
against the checkpoint.

Expected: nonzero result with the same original failure; no planner/executor/controller or scene
mutation; checkpoint hash/session/sequence unchanged; before/after robot and world snapshots equal
within existing project tolerances.

- [ ] **Step 5: Capture fresh visual evidence**

Use `ai-station-capture.sh` after the resume result. Inspect the image, not only logs. Expected:
SO-101 remains at verified safe home, gripper is open, cup is on the canonical support pose and not
carried, table and planning scene agree, and no duplicate GUI/stack is present.

- [ ] **Step 6: Run Panda regression runtime gate**

Run the existing Panda plan-only/resume matrix and one valid recovery `stop_after`; query Gazebo,
MoveIt, joints, controllers, and TF. Expected: unchanged behavior and successful matrix.

- [ ] **Step 7: Clean owned ROS processes and verify final scope**

List PIDs and command lines before termination; clean only the R2 ROS/Gazebo/MoveIt processes. Then:

```bash
git diff --check origin/main...HEAD
git status --short
git log --oneline origin/main..HEAD
```

Expected: no owned stack remains, unrelated sampler/non-ROS processes and other worktrees remain,
diff check passes, worktree is clean, and commits contain only R2 scope. Do not push or merge.

**Stop condition:** do not declare completion if runtime/visual evidence disagrees with logs, overlay
prefixes resolve outside the worktree, another stack cannot be safely identified, any checkpoint or
session field changes on the skipped resume, or any three-package test fails.
