# Run-to-Plan-Only Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the implicit single-state `plan_only` behavior with an explicit run-to-plan-only target that executes and validates every forward predecessor, plans and validates the whitelisted target exactly once, and never executes that target.

**Architecture:** Keep one execution loop in `pick_place_common::StateMachineRunner`. `RunRequest` carries `plan_only_state`, each robot workflow declares the same six-state whitelist, common request/path validation rejects invalid combinations before observation, and the runner switches from execute to plan-only only when it reaches the target entry boundary. Panda and SO-101 only parse/wire arguments and assemble robot-specific dependencies; checkpoint schema v3 and robot-specific policies remain unchanged.

**Tech Stack:** C++17, ROS 2 Jazzy, MoveIt 2, Gazebo Sim, Python launch, Bash acceptance scripts, GTest, pytest, ament/colcon, zsh, Git worktree.

## Global Constraints

- Work only in `/data/work/ws_moveit/.worktrees/refactor-optimization-r1` on branch `codex/refactor-optimization-r1`; do not create another worktree and do not modify `/data/work/ws_moveit` or another worktree.
- The approved design is `docs/superpowers/specs/2026-08-05-run-to-plan-only-design.md`; implementation may not change its semantics without stopping for user approval.
- Use tmux session `codex`; do not send input to, interrupt, rename, or reuse `codex-cua`.
- Before edits, read root `AGENTS.md`, `.agents/skills/so101-dev/SKILL.md`, and all four SO-101 references required for remote/code/test/visual work. Use `superpowers:test-driven-development`, `superpowers:verification-before-completion`, and this plan's required `superpowers:executing-plans` workflow.
- Create the evidence directory with `run_to_plan_evidence="/tmp/so101-debug-run-to-plan-only-$(date +%Y%m%d-%H%M%S)"; mkdir -p "$run_to_plan_evidence"` and store baseline, RED/GREEN output, build/test logs, runtime commands, PID ownership, ROS/Gazebo facts, checkpoints, and screenshot inventory there. Do not write runtime evidence into the source tree.
- Preserve checkpoint schema version `3` and every serialized key. Panda keeps `configuration_hash`; SO-101 keeps `policy_bundle_sha256`; common memory continues to use `configuration_fingerprint`.
- Do not modify Gazebo/ros2_control initial joint positions, SO-101 q6 targets/tolerances, physical grasp contracts, attachment contracts, MoveIt Scene contracts, recovery policy, or robot motion targets.
- The only plan-only targets for both robots are exactly `MOVE_ABOVE_OBJECT`, `DESCEND`, `LIFT`, `MOVE_ABOVE_PLACE`, `DESCEND_TO_PLACE`, and `RETREAT`. No `RECOVER_*`, gripper, attachment, validation, initial, or terminal state is allowed.
- Plan-only means predecessor states execute with their normal physical, Gazebo, Planning Scene, checkpoint, and recovery side effects. At the target boundary run only observe, precondition, plan, and plan validation; target executor and target postcondition are never called.
- A successful target plan does not write a target-completed checkpoint and does not auto-recover. A failed target precondition, plan, or plan validation invokes existing cancel/stop/recovery logic and preserves original failure provenance.
- Fresh plan-only session ID lifecycle matches execute; plan-only resume requires an explicit matching session ID and an execute/FORWARD checkpoint at or upstream of the target.
- `plan_only_state` with non-plan-only mode, plan-only without a target, plan-only with `stop_after`, plan-only with `single_step`, a non-whitelisted target, a recovery checkpoint, or an already-passed target must fail before observer/planner/executor/checkpoint writes.
- Do not run `ament_uncrustify --reformat`; formatting changes must be explicit targeted patches. Every behavior task follows RED then GREEN, ends with `git diff --check`, and receives its own scoped commit.
- Do not push or merge. Do not stop processes not started by this task. Final runtime is simulation-only; no real robot operation is authorized.

## File Map

| Responsibility | Files |
| --- | --- |
| Request and workflow contract | `src/pick_place_common/include/pick_place_common/domain_types.hpp`, `workflow_definition.hpp`, new `run_request_validation.hpp` |
| Pure request/path validation | new `src/pick_place_common/src/run_request_validation.cpp`, new `test/test_run_request_validation.cpp` |
| Single-loop run-to target behavior | `src/pick_place_common/include/pick_place_common/runner.hpp`, `src/pick_place_common/src/runner.cpp`, new `test/test_run_to_plan_only.cpp` |
| Session lifecycle | `src/pick_place_common/src/simulation_session_id.cpp`, Panda session tests, SO-101 CLI bootstrap |
| Robot whitelist declarations | `src/panda_gazebo_demo/src/pick_place/panda_workflow.cpp`, `src/so101_gazebo_demo/src/pick_place/so101_workflow.cpp`, both workflow characterization tests |
| Panda entry and full dependency assembly | `src/panda_gazebo_demo/src/nodes/pick_place_state_machine_node.cpp`, `launch/panda_gazebo.launch.py`, new Panda launch contract test |
| SO-101 CLI and launch | `src/so101_gazebo_demo/src/pick_place/pick_place_state_machine.cpp`, `launch/so101_pick_place.launch.py`, existing launch contract test |
| Compatibility tests and headless matrix | robot runner tests plus Panda `test/headless/run_plan_only_resume_matrix.sh` and its assertion helpers |
| Operator documentation | new `docs/pick-place-launch-parameters.md`, root README, Panda README, SO-101 README, both launch descriptions |

---

### Task 1: Freeze Provenance and Add the Pure Request/Workflow Contract

**Files:**

- Modify: `src/pick_place_common/include/pick_place_common/domain_types.hpp`
- Modify: `src/pick_place_common/include/pick_place_common/workflow_definition.hpp`
- Modify: `src/pick_place_common/src/workflow_definition.cpp`
- Create: `src/pick_place_common/include/pick_place_common/run_request_validation.hpp`
- Create: `src/pick_place_common/src/run_request_validation.cpp`
- Modify: `src/pick_place_common/CMakeLists.txt`
- Modify: `src/pick_place_common/test/test_workflow_definition.cpp`
- Create: `src/pick_place_common/test/test_run_request_validation.cpp`

**Interfaces:**

- Consumes: existing `State`, `RunMode`, `RunRequest`, `WorkflowDefinition`, and deterministic `StateTransitions::succeeded` edges.
- Produces:

```cpp
struct RunRequest
{
  RunMode mode{RunMode::DRY_RUN};
  std::optional<State> stop_after;
  std::optional<State> plan_only_state;
  bool resume{false};
  std::optional<State> fail_at;
  std::uint64_t max_state_transitions{100};
  bool single_step{false};
  bool force_continue{false};
};

struct WorkflowDefinition
{
  State initial_state{State::IDLE};
  std::map<State, StateTransitions> transitions;
  std::set<State> action_states;
  std::set<State> forward_states;
  std::set<State> terminal_states;
  std::set<State> force_continue_states;
  std::set<State> plan_only_states;
};

enum class ForwardPathRelation
{
  UPSTREAM,
  SAME,
  DOWNSTREAM,
  UNREACHABLE
};

[[nodiscard]] ForwardPathRelation
compareForwardPathPosition(const WorkflowDefinition &, State cursor, State target) noexcept;

[[nodiscard]] std::optional<Failure>
validateRunRequest(const WorkflowDefinition &, const RunRequest &);
```

- [ ] **Step 1: Record the clean baseline and external process inventory**

Run from a fresh zsh and save output in the evidence directory:

```zsh
cd /data/work/ws_moveit/.worktrees/refactor-optimization-r1
run_to_plan_evidence="/tmp/so101-debug-run-to-plan-only-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$run_to_plan_evidence"
git rev-parse HEAD | tee "$run_to_plan_evidence/implementation-base.txt"
git status --short --branch
git worktree list --porcelain
tmux list-sessions
tmux capture-pane -pt codex -S -120
pgrep -af 'gz sim|move_group|rviz2|pick_place_state_machine|so101_teleop'
source /opt/ros/jazzy/setup.zsh
ros2 node list | sort
```

Expected: branch is `codex/refactor-optimization-r1`, source worktree is clean, and any pre-existing processes are recorded rather than stopped.

- [ ] **Step 2: Write RED workflow-definition tests**

Define this concrete valid fixture and add tests with these exact names:

```cpp
pp::WorkflowDefinition validPlanOnlyWorkflow()
{
  pp::WorkflowDefinition workflow;
  workflow.transitions[pp::State::IDLE] =
    {pp::State::PREPARE_OPEN_GRIPPER, pp::State::ERROR};
  workflow.transitions[pp::State::PREPARE_OPEN_GRIPPER] =
    {pp::State::MOVE_ABOVE_OBJECT, pp::State::ERROR};
  workflow.transitions[pp::State::MOVE_ABOVE_OBJECT] =
    {pp::State::DONE, pp::State::ERROR};
  workflow.action_states =
    {pp::State::PREPARE_OPEN_GRIPPER, pp::State::MOVE_ABOVE_OBJECT};
  workflow.forward_states =
    {pp::State::IDLE, pp::State::PREPARE_OPEN_GRIPPER,
     pp::State::MOVE_ABOVE_OBJECT, pp::State::DONE};
  workflow.terminal_states = {pp::State::DONE, pp::State::ERROR};
  return workflow;
}

TEST(WorkflowDefinition, AcceptsReachableActionPlanOnlyState)
{
  auto workflow = validPlanOnlyWorkflow();
  workflow.plan_only_states = {pp::State::MOVE_ABOVE_OBJECT};
  EXPECT_FALSE(pp::validateWorkflowDefinition(workflow));
}

TEST(WorkflowDefinition, RejectsInvalidPlanOnlyDeclarations)
{
  auto terminal = validPlanOnlyWorkflow();
  terminal.plan_only_states = {pp::State::DONE};
  ASSERT_TRUE(pp::validateWorkflowDefinition(terminal));
  EXPECT_EQ("WORKFLOW_PLAN_ONLY_STATE_TERMINAL",
            pp::validateWorkflowDefinition(terminal)->code);

  auto non_action = validPlanOnlyWorkflow();
  non_action.forward_states.insert(pp::State::RECOVER_RETREAT);
  non_action.transitions[pp::State::RECOVER_RETREAT] =
    {pp::State::DONE, pp::State::ERROR};
  non_action.plan_only_states = {pp::State::RECOVER_RETREAT};
  ASSERT_TRUE(pp::validateWorkflowDefinition(non_action));
  EXPECT_EQ("WORKFLOW_PLAN_ONLY_STATE_NOT_FORWARD_ACTION",
            pp::validateWorkflowDefinition(non_action)->code);

  auto unreachable = validPlanOnlyWorkflow();
  unreachable.action_states.insert(pp::State::DESCEND);
  unreachable.forward_states.insert(pp::State::DESCEND);
  unreachable.transitions[pp::State::DESCEND] =
    {pp::State::DONE, pp::State::ERROR};
  unreachable.plan_only_states = {pp::State::DESCEND};
  ASSERT_TRUE(pp::validateWorkflowDefinition(unreachable));
  EXPECT_EQ("WORKFLOW_PLAN_ONLY_STATE_UNREACHABLE",
            pp::validateWorkflowDefinition(unreachable)->code);

  auto ambiguous = validPlanOnlyWorkflow();
  ambiguous.action_states.insert(pp::State::RECOVER_RETREAT);
  ambiguous.transitions[pp::State::RECOVER_RETREAT] =
    {pp::State::MOVE_ABOVE_OBJECT, pp::State::ERROR};
  ambiguous.plan_only_states = {pp::State::MOVE_ABOVE_OBJECT};
  ASSERT_TRUE(pp::validateWorkflowDefinition(ambiguous));
  EXPECT_EQ("WORKFLOW_PLAN_ONLY_PREDECESSOR_AMBIGUOUS",
            pp::validateWorkflowDefinition(ambiguous)->code);

  auto cycle = validPlanOnlyWorkflow();
  cycle.transitions[pp::State::MOVE_ABOVE_OBJECT].succeeded =
    pp::State::PREPARE_OPEN_GRIPPER;
  ASSERT_TRUE(pp::validateWorkflowDefinition(cycle));
  EXPECT_EQ("WORKFLOW_FORWARD_SUCCESS_CYCLE",
            pp::validateWorkflowDefinition(cycle)->code);
}
```

- [ ] **Step 3: Write RED request-validation table tests**

Use a parameterized table with the exact expected codes:

| Request | Expected code |
| --- | --- |
| plan-only without target | `PLAN_ONLY_STATE_REQUIRED` |
| plan-only target outside whitelist | `PLAN_ONLY_STATE_NOT_ALLOWED` |
| allowed but unreachable target in a deliberately invalid fixture | `PLAN_ONLY_STATE_UNREACHABLE` |
| execute or dry-run with `plan_only_state` | `PLAN_ONLY_ARGUMENT_CONFLICT` |
| plan-only with `stop_after` | `PLAN_ONLY_ARGUMENT_CONFLICT` |
| plan-only with `single_step=true` | `PLAN_ONLY_ARGUMENT_CONFLICT` |
| `max_state_transitions=0` | existing `INVALID_MAX_TRANSITIONS` |
| non-dry-run with `fail_at` | existing `FAIL_AT_MODE_MISMATCH` |
| `force_continue` without execute resume | existing `FORCE_CONTINUE_REQUEST_INVALID` |

Also assert `compareForwardPathPosition()` returns `UPSTREAM`, `SAME`, `DOWNSTREAM`, and `UNREACHABLE` for concrete cursor/target pairs on the fixture.

- [ ] **Step 4: Run RED tests**

```zsh
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select pick_place_common --symlink-install
./build/pick_place_common/test_workflow_definition --gtest_color=yes
./build/pick_place_common/test_run_request_validation --gtest_color=yes
```

Expected: compile/test failure because the new fields, enum, and functions are absent; save the first relevant failure output.

- [ ] **Step 5: Implement the minimal pure validation**

`compareForwardPathPosition()` must walk only `succeeded` edges starting at `workflow.initial_state`, record visited states, and compare indexes. A missing edge, cycle, cursor not on the path, or target not on the path returns `UNREACHABLE`.

`validateWorkflowDefinition()` must preserve all existing checks, then validate every `plan_only_states` member in this order: non-terminal, action+forward membership, forward-success reachability, exactly one successful predecessor on the declared graph. It must reject a succeeded-edge cycle before accepting the definition.

`validateRunRequest()` must be side-effect-free and return the exact request codes above. Check `PLAN_ONLY_STATE_REQUIRED` before whitelist membership, and check plan-only argument conflicts before path comparison.

- [ ] **Step 6: Run GREEN tests and commit**

```zsh
colcon build --packages-select pick_place_common --symlink-install
./build/pick_place_common/test_workflow_definition --gtest_color=yes
./build/pick_place_common/test_run_request_validation --gtest_color=yes
git diff --check
git add -- src/pick_place_common
git commit -m "feat(common): define explicit plan-only targets"
```

**Acceptance:** all request codes are stable, workflow invalidity is detected without ROS dependencies, and `pick_place_common::core` gains no ROS/MoveIt/Gazebo dependency.

---

### Task 2: Implement Fresh Run-to-Plan-Only in the Single Common Loop

**Files:**

- Modify: `src/pick_place_common/include/pick_place_common/runner.hpp`
- Modify: `src/pick_place_common/src/runner.cpp`
- Modify: `src/pick_place_common/test/test_common_runner.cpp`
- Create: `src/pick_place_common/test/test_run_to_plan_only.cpp`
- Modify: `src/pick_place_common/CMakeLists.txt`

**Interfaces:**

- Consumes: `RunRequest::plan_only_state`, `WorkflowDefinition::plan_only_states`, `validateRunRequest()`, existing executor/planner/validator/contract/checkpoint/recovery interfaces.
- Produces: private `runPlanOnlyTarget(State, std::optional<ObservationResult>, std::uint64_t checkpoint_sequence)` and a `runExecuteWorkflow()` target-boundary branch; removes implicit planner scanning and plan-only checkpoint synthesis.

- [ ] **Step 1: Build a reusable multi-state fake harness**

The fixture workflow must be exactly:

```text
IDLE -> PREPARE_OPEN_GRIPPER -> MOVE_ABOVE_OBJECT -> DESCEND -> DONE
```

Declare `MOVE_ABOVE_OBJECT` and `DESCEND` as plan-only states. The fake observer, store, planners, validators, contracts, executors, and recovery policy must count calls and append events including the state name. The store must retain every committed `Checkpoint`.

- [ ] **Step 2: Write the RED fresh-success tests**

Add these exact tests:

```cpp
TEST(RunToPlanOnly, ExecutesPredecessorsThenPlansTargetWithoutExecutingIt);
TEST(RunToPlanOnly, DeepTargetExecutesEveryUpstreamActionExactlyOnce);
TEST(RunToPlanOnly, SuccessLeavesCheckpointAtTargetEntry);
TEST(RunToPlanOnly, ResultTraceAndTransitionCountDescribeOnlyRealTransitions);
```

For `MOVE_ABOVE_OBJECT`, assert this event subsequence exactly:

```text
observe PREPARE precondition PREPARE execute PREPARE observe PREPARE
postcondition PREPARE checkpoint PREPARE
observe MOVE_ABOVE_OBJECT precondition MOVE_ABOVE_OBJECT
plan MOVE_ABOVE_OBJECT validate-plan MOVE_ABOVE_OBJECT
```

Assert no `execute MOVE_ABOVE_OBJECT`, no target postcondition, and no target checkpoint. Assert `status=PLAN_ONLY_COMPLETE`, `current_state=MOVE_ABOVE_OBJECT`, `next_state=DESCEND`, trace contains `IDLE`, `PREPARE_OPEN_GRIPPER`, `MOVE_ABOVE_OBJECT` but not `DESCEND`, and transition count is `2` (`IDLE -> PREPARE`, `PREPARE -> target`).

- [ ] **Step 3: Write RED zero-side-effect and infrastructure tests**

For every request-validation error from Task 1, run through a real `StateMachineRunner` and assert:

```cpp
EXPECT_EQ(0, scenario.observer_calls);
EXPECT_EQ(0, scenario.planner_calls);
EXPECT_EQ(0, scenario.executor_calls);
EXPECT_EQ(0, store.commit_calls);
```

Then remove each required observer, checkpoint store, resume validator, recovery policy, predecessor executor/contract, target executor/planner/plan-validator/contract in separate subcases. Expect existing infrastructure/registration codes, and still assert zero calls before the missing component is reported.

- [ ] **Step 4: Run RED**

```zsh
colcon build --packages-select pick_place_common --symlink-install
./build/pick_place_common/test_run_to_plan_only \
  --gtest_filter='RunToPlanOnly.*' --gtest_color=yes
```

Expected: old runner plans the first planner directly, fails to execute PREPARE, or writes the old synthetic plan-only checkpoint.

- [ ] **Step 5: Replace the implicit plan-only path**

Make `run()` call `validateRunRequest()` before every other validation. For fresh plan-only, require execute-grade observer, checkpoint store, resume validator, recovery policy, executors, contracts, and paired planner/validator registrations, then enter `runExecuteWorkflow()` at the initial success successor exactly as execute does.

Delete the old `runPlanOnly(const RunRequest&)` planner scan and the block that writes `source_mode=PLAN_ONLY`. Rename the state-specific method to `runPlanOnlyTarget()` and make its sequence unconditional for both robots:

```cpp
observe -> validatePrecondition -> plan -> validate plan -> PLAN_ONLY_COMPLETE
```

It must never call `executor.execute()`. It may obtain the target executor only for failure cancellation/recovery.

At the top of the forward loop, before `runExecuteStep()`:

```cpp
if (phase == CheckpointPhase::FORWARD &&
    request.mode == RunMode::PLAN_ONLY &&
    state == *request.plan_only_state) {
  // plan target and return success without incrementing transition_count;
  // on recoverable failure, enter the existing recovery loop.
}
```

The target entry is already in `state_trace`; do not append its success successor on plan success.

- [ ] **Step 6: Make target failures enter existing recovery**

For target observation, precondition, planner, and plan-validation failure, call `handleActionFailure(state, *target_executor, failure, checkpoint_sequence)`. Do not special-case Panda or environment-category failures. When it returns a recovery route, increment the count for the failed transition, append the recovery state, set phase/original failure exactly as execute does, and continue the same loop. When target planning succeeds, do not cancel, recover, or checkpoint.

- [ ] **Step 7: Run GREEN and existing common regressions**

```zsh
colcon build --packages-select pick_place_common --symlink-install
./build/pick_place_common/test_run_to_plan_only --gtest_color=yes
./build/pick_place_common/test_common_runner --gtest_color=yes
PYTHONNOUSERSITE=1 colcon test --packages-select pick_place_common --event-handlers console_direct+
colcon test-result --test-result-base build/pick_place_common --verbose
git diff --check
git add -- src/pick_place_common
git commit -m "feat(common): run predecessors before plan-only target"
```

**Acceptance:** all predecessor execute/checkpoint events occur in order, target planner and validator each run once, target executor/postcondition/checkpoint run zero times, and request errors are zero-side-effect.

---

### Task 3: Add Plan-Only Resume Position Rules and Failure Provenance

**Files:**

- Modify: `src/pick_place_common/src/runner.cpp`
- Modify: `src/pick_place_common/test/test_run_to_plan_only.cpp`

**Interfaces:**

- Consumes: schema-v3 execute checkpoints, `ForwardPathRelation`, `CommonResumeValidator`, existing recovery checkpoint fields.
- Produces: plan-only resume that accepts only `FORWARD` checkpoints with `next_state` equal to or upstream of the requested target.

- [ ] **Step 1: Write RED resume-position tests**

Add exact tests:

```cpp
TEST(RunToPlanOnlyResume, SameTargetCheckpointValidatesThenPlansWithoutExecuting);
TEST(RunToPlanOnlyResume, UpstreamCheckpointExecutesRemainderThenPlansTarget);
TEST(RunToPlanOnlyResume, PassedTargetFailsBeforeObservation);
TEST(RunToPlanOnlyResume, RecoveryCheckpointFailsBeforeObservation);
TEST(RunToPlanOnlyResume, WorldSessionAndFingerprintMismatchRemainFailClosed);
```

The first case uses `last_completed_state=PREPARE_OPEN_GRIPPER`, `next_state=MOVE_ABOVE_OBJECT`. The upstream case uses the same checkpoint but requests `DESCEND`; it must execute `MOVE_ABOVE_OBJECT`, commit a checkpoint with `next_state=DESCEND`, then plan `DESCEND` without executing it. The passed-target case uses `next_state=DESCEND` with target `MOVE_ABOVE_OBJECT` and expects `PLAN_ONLY_TARGET_ALREADY_PASSED`. The recovery case expects `PLAN_ONLY_RECOVERY_RESUME_UNSUPPORTED`.

For passed/recovery cases assert observer/planner/executor/commit calls are zero. `loadLatestCompatible()` may be called once.

- [ ] **Step 2: Write RED target-failure recovery tests**

Parameterize target failure at precondition, planning, and plan validation. Expect the original category/code in the recovery checkpoint and final result provenance. Add a recovery executor failure case and assert its returned failure message includes the original code. In every case assert the target executor's `execute_calls == 0` and `cancel_calls == 1`.

- [ ] **Step 3: Run RED**

```zsh
colcon build --packages-select pick_place_common --symlink-install
./build/pick_place_common/test_run_to_plan_only \
  --gtest_filter='RunToPlanOnlyResume.*:RunToPlanOnlyFailure.*' --gtest_color=yes
```

- [ ] **Step 4: Enforce resume rules before observation**

After loading and structurally validating the checkpoint, but before `observer_->observe()`:

```cpp
if (request.mode == RunMode::PLAN_ONLY) {
  if (checkpoint.phase == CheckpointPhase::RECOVERY) {
    return error(checkpoint.next_state,
      {FailureCategory::RESUME_VALIDATION,
       "PLAN_ONLY_RECOVERY_RESUME_UNSUPPORTED",
       "plan_only resume accepts only forward execute checkpoints", {}});
  }
  const auto relation = compareForwardPathPosition(
    workflow_, checkpoint.next_state, *request.plan_only_state);
  if (relation == ForwardPathRelation::DOWNSTREAM) {
    return error(checkpoint.next_state,
      {FailureCategory::RESUME_VALIDATION,
       "PLAN_ONLY_TARGET_ALREADY_PASSED",
       "checkpoint next_state is downstream of plan_only_state", {}});
  }
  if (relation == ForwardPathRelation::UNREACHABLE) {
    return error(checkpoint.next_state,
      {FailureCategory::RESUME_VALIDATION,
       "PLAN_ONLY_STATE_UNREACHABLE",
       "checkpoint cannot reach plan_only_state on the forward success path", {}});
  }
}
```

Keep `checkpoint.source_mode == RunMode::EXECUTE`, schema, resumable, transition-shape, common resume, transition-resume, session, configuration, world, and stationary-object validation unchanged.

- [ ] **Step 5: Resume through the single execute loop**

After common and transition resume validation, call `runExecuteWorkflow(checkpoint.next_state, request, snapshot, checkpoint.sequence + 1)` for plan-only as well as execute. Remove both old resume calls to the direct plan-only method. This allows an upstream cursor to execute remaining predecessors and a same-target cursor to hit the target branch immediately.

- [ ] **Step 6: Run GREEN and commit**

```zsh
colcon build --packages-select pick_place_common --symlink-install
./build/pick_place_common/test_run_to_plan_only --gtest_color=yes
PYTHONNOUSERSITE=1 colcon test --packages-select pick_place_common --event-handlers console_direct+
colcon test-result --test-result-base build/pick_place_common --verbose
git diff --check
git add -- src/pick_place_common
git commit -m "feat(common): validate plan-only resume position"
```

**Acceptance:** same/upstream resume works, passed/recovery resume has zero physical calls, target failures recover without executing the target, and recovery failure retains original provenance.

---

### Task 4: Declare Robot Whitelists and Unify Session Lifecycle

**Files:**

- Modify: `src/panda_gazebo_demo/src/pick_place/panda_workflow.cpp`
- Modify: `src/panda_gazebo_demo/test/pick_place/test_workflow_characterization.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/so101_workflow.cpp`
- Modify: `src/so101_gazebo_demo/test/pick_place/test_workflow_characterization.cpp`
- Modify: `src/pick_place_common/src/simulation_session_id.cpp`
- Modify: `src/panda_gazebo_demo/test/pick_place/test_simulation_session_id.cpp`
- Modify: positional `RunRequest` construction sites under both robot packages

**Interfaces:**

- Consumes: approved six-state whitelist and new `RunRequest` layout.
- Produces: identical explicit whitelist in both workflow definitions; common session resolution for fresh plan-only.

- [ ] **Step 1: Write RED whitelist characterization tests**

Both package tests must compare exact set equality, not subset membership:

```cpp
const std::set<State> expected{
  State::MOVE_ABOVE_OBJECT,
  State::DESCEND,
  State::LIFT,
  State::MOVE_ABOVE_PLACE,
  State::DESCEND_TO_PLACE,
  State::RETREAT,
};
EXPECT_EQ(expected, workflow.plan_only_states);
```

Also loop through `plan_only_states` and assert action, forward, non-terminal, and planner-state characterization where the runtime test exposes registrations.

- [ ] **Step 2: Write RED session tests**

Replace `DoesNotGenerateForNonResumeNonExecuteModes` with these cases:

```cpp
EXPECT_EQ("plan-only-1784779200123",
          *resolveSimulationSessionId(RunMode::PLAN_ONLY, false, "", 1784779200123ULL).value);
EXPECT_EQ("operator-session",
          *resolveSimulationSessionId(RunMode::PLAN_ONLY, false, "operator-session", 1).value);
EXPECT_FALSE(resolveSimulationSessionId(RunMode::DRY_RUN, false, "ignored", 1).value);
```

Keep resume-without-explicit-ID rejection and execute prefix tests.

- [ ] **Step 3: Add the whitelist and session behavior**

Set the exact six states in both workflow builders before `validateWorkflowDefinition(w)`. In `resolveSimulationSessionId()`, handle both executable modes:

```cpp
if (resume || mode == RunMode::EXECUTE || mode == RunMode::PLAN_ONLY) {
  const char * prefix = mode == RunMode::PLAN_ONLY ? "plan-only-" : "execute-";
  return {configured_id.empty()
            ? std::optional<std::string>{prefix + std::to_string(unix_timestamp_milliseconds)}
            : std::optional<std::string>{std::move(configured_id)},
          ""};
}
```

The resume empty-ID guard remains first.

- [ ] **Step 4: Eliminate positional aggregate ambiguity**

Every `RunRequest` construction with more than one field in Panda/SO-101 production and tests must use named assignments:

```cpp
RunRequest request;
request.mode = RunMode::EXECUTE;
request.stop_after = State::DESCEND;
request.resume = true;
request.max_state_transitions = 100;
```

Plan-only calls set `request.plan_only_state`; they never put a target in `stop_after`. Single-field `{RunMode::EXECUTE}` and `{RunMode::DRY_RUN}` calls may remain.

- [ ] **Step 5: Run GREEN and commit**

```zsh
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --symlink-install
./build/panda_gazebo_demo/test_workflow_characterization --gtest_color=yes
./build/so101_gazebo_demo/test_workflow_characterization --gtest_color=yes
./build/panda_gazebo_demo/test_simulation_session_id --gtest_color=yes
git diff --check
git add -- src/pick_place_common/src/simulation_session_id.cpp \
  src/panda_gazebo_demo src/so101_gazebo_demo
git commit -m "feat: declare robot plan-only whitelists"
```

**Acceptance:** both whitelist sets are exactly equal, recovery planners remain excluded, plan-only fresh sessions are generated centrally, and no multi-field positional request initializer remains.

---

### Task 5: Wire Panda and SO-101 Entry Points Without Duplicating Semantics

**Files:**

- Modify: `src/panda_gazebo_demo/src/nodes/pick_place_state_machine_node.cpp`
- Modify: `src/panda_gazebo_demo/launch/panda_gazebo.launch.py`
- Create: `src/panda_gazebo_demo/test/test_panda_launch_contract.py`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`
- Modify: `src/so101_gazebo_demo/src/pick_place/pick_place_state_machine.cpp`
- Modify: `src/so101_gazebo_demo/launch/so101_pick_place.launch.py`
- Modify: `src/so101_gazebo_demo/test/test_so101_launch_contract.py`
- Modify: robot runner tests that encode old direct-plan or plan-only checkpoint behavior

**Interfaces:**

- Consumes: `validateRunRequest()`, robot workflow whitelist, `RunRequest::plan_only_state`, common session resolver.
- Produces: Panda ROS parameter `plan_only_state`; SO-101 CLI `--plan-only-state`; SO-101 launch argument `plan_only_state`; full predecessor-capable Panda runtime assembly.

- [ ] **Step 1: Write RED launch/entry contract tests**

Panda launch test must load `panda_gazebo.launch.py` and define the same direct-source helpers used by the SO-101 contract test:

```python
def load_launch_description(path):
    spec = importlib.util.spec_from_file_location('panda_gazebo_launch', path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.generate_launch_description()

def launch_default_text(argument):
    return ''.join(part.text for part in argument.default_value)

description = load_launch_description(PANDA_LAUNCH)
declared = {
    entity.name: entity
    for entity in description.entities
    if isinstance(entity, DeclareLaunchArgument)
}
defaults = {name: launch_default_text(argument) for name, argument in declared.items()}
assert defaults['plan_only_state'] == ''
assert "'plan_only_state': LaunchConfiguration('plan_only_state')" in source
assert 'docs/pick-place-launch-parameters.md' in declared['plan_only_state'].description
```

SO-101 launch test must extend the safe-default test:

```python
assert arguments['plan_only_state'] == ''
assert '--plan-only-state' in source
assert (
    'docs/pick-place-launch-parameters.md'
    in declared_argument(PICK_PLACE_LAUNCH, 'plan_only_state').description
)
```

Add a source/CLI test that proves usage contains `--plan-only-state STATE` and that policy provenance selects `request.plan_only_state` before `stop_after`.

- [ ] **Step 2: Write RED Panda runtime-assembly tests**

Extend Panda runner/runtime coverage so a plan-only request for `MOVE_ABOVE_OBJECT` requires and receives PREPARE executor+contract, checkpoint store, resume validator, recovery policy, target executor, planner, validator, and contract. Assert the old planner-only assembly returns an infrastructure error before the production change.

- [ ] **Step 3: Implement Panda parsing and fail-fast request validation**

Add `StateParameterScope::PLAN_ONLY` and validate membership through `pandaWorkflowDefinition().plan_only_states`. Parse `plan_only_state` separately from `stop_after`. Construct one explicit `RunRequest`, call `validateRunRequest(pandaWorkflowDefinition(), request)`, log its code/message, and return before session resolution, MoveIt adapter construction, scene actions, or checkpoint creation on failure.

For both plan-only and execute, assemble every dependency needed by predecessor execution: gripper, motion, MoveIt scene, Gazebo attach/detach, observer, checkpoint store, resume validator, plan validators, contracts, and recovery policy. Do not retain the current `if (mode == EXECUTE)` gate around executor dependencies.

- [ ] **Step 4: Implement SO-101 CLI/launch wiring**

Parse:

```text
--plan-only-state STATE
```

with `stateFromString()` into `request.plan_only_state`. In `main()`, call `validateRunRequest(so101WorkflowDefinition(), request)` immediately after CLI parsing and before policy loading or ROS initialization. Print fail-closed errors through `printPreRunnerFailure()`-equivalent text and return `2`.

Remove the SO-101-specific fresh plan-only session fallback at the old lines 173-175; use only the common resolver. Pass `request.plan_only_state.value_or(request.stop_after.value_or(MOVE_ABOVE_OBJECT))` to policy provenance.

Add `plan_only_state` to `so101_pick_place.launch.py`, default `""`, and pass it as `--plan-only-state` after `--mode`.

- [ ] **Step 5: Migrate robot runner tests to run-to semantics**

Replace old expectations that plan-only starts directly at a planner or writes `source_mode=PLAN_ONLY`. Required replacements:

- Panda `PlanOnlyUsesExactlyOnePlannerAndDoesNotAdvanceBusinessState`: register full predecessor infrastructure, set `plan_only_state=MOVE_ABOVE_OBJECT`, expect PREPARE execution and an execute checkpoint at target entry.
- Panda resume plan-only tests: set explicit target; same-target checkpoint plans directly; upstream target executes remaining predecessors.
- SO-101 `PlanOnlyStopBoundaryPlansValidatesAndCheckpointsWithoutActing`: rename to `PlanOnlyExecutesPrepareThenPlansMoveAboveWithoutExecutingTarget`, expect one predecessor executor, no target executor, and latest checkpoint `source_mode=EXECUTE`, `last_completed_state=PREPARE_OPEN_GRIPPER`, `next_state=MOVE_ABOVE_OBJECT`.
- SO-101 missing registration tests: register all non-target execute-grade infrastructure first, then remove only the component under test.

- [ ] **Step 6: Run targeted GREEN tests**

```zsh
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --symlink-install
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/panda_gazebo_demo/test/test_panda_launch_contract.py \
  src/so101_gazebo_demo/test/test_so101_launch_contract.py
./build/panda_gazebo_demo/test_pick_place_core --gtest_color=yes
./build/so101_gazebo_demo/test_pick_place_runner --gtest_color=yes
git diff --check
git add -- src/panda_gazebo_demo src/so101_gazebo_demo
git commit -m "feat: expose run-to-plan-only in robot entry points"
```

**Acceptance:** invalid combinations fail before production bootstrap, Panda plan-only owns all predecessor side effects, SO-101 has no private session workaround, and both entries forward the same common request.

---

### Task 6: Replace the Old Panda Plan-Only/Recovery Matrix

**Files:**

- Modify: `src/panda_gazebo_demo/test/headless/run_plan_only_resume_matrix.sh`
- Modify: `src/panda_gazebo_demo/test/headless/assert_plan_only_resume.py`
- Modify: `src/panda_gazebo_demo/test/headless/assert_plan_only_tcp_unchanged.py`
- Modify: `src/panda_gazebo_demo/test/headless/test_plan_only_resume_helpers.sh`
- Modify: `src/panda_gazebo_demo/README.md`

**Interfaces:**

- Consumes: six forward targets, fresh run-to behavior, execute/FORWARD checkpoints, same-target plan-only resume.
- Produces: headless evidence that each target is reached through real predecessors, target is not executed, latest checkpoint remains at target entry, and a same-target resume replans without movement.

- [ ] **Step 1: Write RED helper fixtures for the new log/checkpoint contract**

Update shell fixtures to include:

```text
Run completed: status=PLAN_ONLY_COMPLETE current_state=DESCEND next_state=CLOSE_GRIPPER transitions=3
CHECKPOINT_PHASE=FORWARD CHECKPOINT_SEQUENCE=2 NEXT_STATE=DESCEND
```

and a checkpoint with `source_mode=execute`, `last_completed_state=MOVE_ABOVE_OBJECT`, `next_state=DESCEND`. Assert the helper rejects `source_mode=plan_only`, any `RECOVER_*` expected target, target execute evidence, target postcondition evidence, a checkpoint beyond the target, or changed same-target-resume checkpoint bytes.

- [ ] **Step 2: Rewrite the matrix around independent fresh targets**

For each of the exact six targets:

1. reset the Panda fixture;
2. use a unique session and checkpoint;
3. capture the initial snapshot;
4. run fresh `mode:=plan_only plan_only_state:="$target" resume:=false`;
5. assert predecessor checkpoint sequence and `next_state` equals `$target`;
6. capture the target-entry snapshot and compare it with checkpoint expected state;
7. copy/hash the checkpoint;
8. run `mode:=plan_only plan_only_state:="$target" resume:=true` with the same session;
9. assert checkpoint bytes and target-entry snapshot remain unchanged across the resumed plan;
10. assert the target plan evidence exists and target execute/postcondition evidence does not.

Delete the recovery matrix, `seed_recovery_checkpoint.py` use, recovery plan-only targets, bridge execution, and `RECOVER_RETREAT` plan-only call from this script. Recovery behavior remains covered by execute recovery tests and Task 3 target-failure tests.

- [ ] **Step 3: Run helper RED/GREEN and shell syntax checks**

```zsh
bash -n src/panda_gazebo_demo/test/headless/run_plan_only_resume_matrix.sh
bash -n src/panda_gazebo_demo/test/headless/test_plan_only_resume_helpers.sh
src/panda_gazebo_demo/test/headless/test_plan_only_resume_helpers.sh
```

- [ ] **Step 4: Commit the matrix migration**

```zsh
git diff --check
git add -- src/panda_gazebo_demo/test/headless src/panda_gazebo_demo/README.md
git commit -m "test(panda): validate run-to-plan-only matrix"
```

**Acceptance:** no recovery state is treated as plan-only, each target has an independent reset/session/checkpoint, and same-target resume proves no target motion or checkpoint mutation.

---

### Task 7: Publish the Unified Launch Parameter Manual

**Files:**

- Create: `docs/pick-place-launch-parameters.md`
- Modify: `README.md`
- Modify: `src/panda_gazebo_demo/README.md`
- Modify: `src/so101_gazebo_demo/README.md`
- Modify: `src/panda_gazebo_demo/launch/panda_gazebo.launch.py`
- Modify: `src/so101_gazebo_demo/launch/so101_pick_place.launch.py`
- Modify: launch contract tests from Task 5

**Interfaces:**

- Consumes: installed `--show-args` output, actual node/CLI defaults, approved side-effect and compatibility rules.
- Produces: one authoritative operator manual linked from both packages and both launch surfaces.

- [ ] **Step 1: Capture installed argument truth after rebuilding**

```zsh
source /opt/ros/jazzy/setup.zsh
source install/setup.zsh
ros2 launch panda_gazebo_demo panda_gazebo.launch.py --show-args
ros2 launch so101_gazebo_demo so101_pick_place.launch.py --show-args
ros2 run so101_gazebo_demo pick_place_state_machine --invalid-argument
```

Save output in the evidence directory. The last command must return `2` and print usage containing `--plan-only-state STATE`.

- [ ] **Step 2: Write the manual with exact sections**

`docs/pick-place-launch-parameters.md` must contain, in this order:

1. simulation-only safety warning;
2. mode table for `dry_run`, run-to-`plan_only`, and `execute`, including physical/Gazebo/Planning Scene/checkpoint/recovery side effects;
3. the exact six-state whitelist and a predecessor-stage table for each target;
4. common request table: `mode`/`run_mode`, `plan_only_state`, `stop_after`, `resume`, `checkpoint_path`, `simulation_session_id`, `max_state_transitions`, plus SO CLI `--step` and `--force-continue`;
5. invalid-combination table with all six new error codes;
6. Panda launch table copied from current `--show-args`, grouped into lifecycle, motion planning, tolerances, gripper, Gazebo/attachment, and recovery;
7. SO-101 launch table for `run_mode`, `start_simulation`, `headless`, lifecycle/checkpoint/session, object config, motion policy, and validation policy;
8. fresh Panda and SO-101 `MOVE_ABOVE_OBJECT` commands;
9. deep `LIFT` warning and command;
10. forward resume command using the same checkpoint/session/target;
11. successful deep target handling: execute resume or explicit reset;
12. diagnostics table mapping request, q6, checkpoint/session, MoveIt plan, attachment, and duplicate-stack failures to first checks;
13. provenance commands for package prefix, executable, AMENT prefix, PIDs, ROS nodes, Gazebo attachment, and MoveIt scene.

The run-to-plan-only warning must appear before the first plan-only command: predecessors really execute; only the named target does not execute.

- [ ] **Step 3: Link without duplicating tables**

Add a short link next to `docs/pick-place-architecture.md` in root README and both package READMEs. Replace Panda's old paragraph claiming plan-only/resume is side-effect-free and recovery-plannable with the new forward-only semantics. Add the manual path to both `plan_only_state` launch argument descriptions.

- [ ] **Step 4: Validate documentation and commit**

```zsh
rg -n "pick-place-launch-parameters.md" \
  README.md src/panda_gazebo_demo/README.md src/so101_gazebo_demo/README.md \
  src/panda_gazebo_demo/launch/panda_gazebo.launch.py \
  src/so101_gazebo_demo/launch/so101_pick_place.launch.py
rg -n "RECOVER_.*plan.only|plan.only.*RECOVER_" \
  README.md docs/pick-place-launch-parameters.md \
  src/panda_gazebo_demo/README.md src/so101_gazebo_demo/README.md
git diff --check
git add -- docs/pick-place-launch-parameters.md README.md \
  src/panda_gazebo_demo/README.md src/so101_gazebo_demo/README.md \
  src/panda_gazebo_demo/launch/panda_gazebo.launch.py \
  src/so101_gazebo_demo/launch/so101_pick_place.launch.py \
  src/panda_gazebo_demo/test/test_panda_launch_contract.py \
  src/so101_gazebo_demo/test/test_so101_launch_contract.py
git commit -m "docs: add pick-place launch parameter manual"
```

**Acceptance:** manual defaults match installed `--show-args`, all four required links exist, no README advertises old stop-after plan-only or recovery plan-only behavior, and warnings precede commands.

---

### Task 8: Run Full Regression and ai-station Runtime Acceptance

**Files:**

- No source changes expected; if a product defect is found, return to the owning task, add a RED test, patch there, and create a new scoped fix commit.
- Evidence only under the Task 1 `$run_to_plan_evidence` directory and existing ignored capture locations.

**Interfaces:**

- Consumes: final worktree source and install overlay.
- Produces: package, runtime, physical-state, and visual evidence required by the approved spec.

- [ ] **Step 1: Clean-cache build and provenance verification**

```zsh
cd /data/work/ws_moveit/.worktrees/refactor-optimization-r1
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo \
  --symlink-install --cmake-clean-cache
source install/setup.zsh
ros2 pkg prefix pick_place_common
ros2 pkg prefix panda_gazebo_demo
ros2 pkg prefix so101_gazebo_demo
ros2 pkg executables panda_gazebo_demo | rg pick_place_state_machine
ros2 pkg executables so101_gazebo_demo | rg pick_place_state_machine
```

Expected: all prefixes point into this worktree's `install`, not `/data/work/ws_moveit/install` or another worktree.

- [ ] **Step 2: Run all three package tests and quality gates**

```zsh
PYTHONNOUSERSITE=1 colcon test \
  --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo \
  --event-handlers console_direct+
colcon test-result --verbose
git diff --check
```

Expected: zero errors and zero failures. Record skips separately; do not count skipped runtime evidence as passed runtime acceptance.

- [ ] **Step 3: Prove invalid requests have no runtime side effects**

Run SO-101 CLI and Panda node cases for missing target, recovery target, plan-only+stop-after, plan-only+step where available, and non-plan-only+target. Capture exit code and before/after PID, ROS node, attachment, and checkpoint facts. Expect the corresponding `PLAN_ONLY_*` code, no changed checkpoint, no target process surviving, and no robot/world change.

- [ ] **Step 4: Validate SO-101 fresh MOVE_ABOVE_OBJECT**

Use an isolated `ROS_DOMAIN_ID`, `GZ_PARTITION`, session ID, checkpoint path, and task-owned tmux runtime session. Source `~/gui-env.zsh` only inside the GUI-holding tmux shell. Run:

```zsh
so101_move_above_session="run-to-plan-only-move-above-$(date +%s%N)"
so101_move_above_checkpoint="$run_to_plan_evidence/so101-move-above-checkpoint.json"
ros2 launch so101_gazebo_demo so101_pick_place.launch.py \
  start_simulation:=true headless:=false \
  run_mode:=plan_only plan_only_state:=MOVE_ABOVE_OBJECT \
  simulation_session_id:="$so101_move_above_session" \
  checkpoint_path:="$so101_move_above_checkpoint"
```

Record both concrete variable values before execution. Verify PREPARE executor/postcondition/checkpoint, q6 convergence to configured preopen within policy tolerance, target plan/validation, target executor absence, and unchanged arm joints/TCP across the target plan boundary.

- [ ] **Step 5: Validate SO-101 deep LIFT and target-failure recovery**

Reset to canonical state and run fresh `plan_only_state:=LIFT`. Verify real close-gripper, physical grasp evidence, Gazebo attached state, MoveIt attached collision object, target-entry checkpoint, LIFT plan/validation, and no LIFT execution.

For failure injection, set `failed_validation_policy="$run_to_plan_evidence/plan-only-validation-failure.yaml"`, copy the installed validation policy to that exact path, and use an explicit targeted patch to change only `states.MOVE_ABOVE_OBJECT.endpoint_position` to `[0.5, 0.5, 0.5]` while leaving schema valid. Launch with `validation_policy:="$failed_validation_policy"`. Verify plan validation fails, target executor remains unused, recovery is selected/executed, original failure is retained, and Gazebo/MoveIt return to the recovery-defined safe facts. Do not commit the temporary policy.

- [ ] **Step 6: Validate Panda shallow and deep targets**

Run the migrated headless matrix, then perform GUI runs for `MOVE_ABOVE_OBJECT` and `LIFT` with unique sessions/checkpoints. For each, verify predecessor checkpoint sequence, target plan evidence, no target execution, `/joint_states` and TCP target-entry facts, Gazebo Coke pose/attachment, and MoveIt world/attached membership.

- [ ] **Step 7: Capture and inspect fresh visual evidence**

For the SO-101 GUI stack, run in a GUI-enabled tmux shell:

```zsh
source ~/gui-env.zsh
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_moveit/.worktrees/refactor-optimization-r1/install/setup.zsh
ros2 run so101_gazebo_demo tile_ai_station_guis.py
```

Require `LAYOUT_OK`, then run the repository capture helper and inspect the new desktop/RViz/Gazebo images. Record what is visible: robot pose, gripper opening, Coke pose, attachment state, and absence of penetration/drop. Pair each screenshot with same-run numeric joint/TF/Coke evidence.

- [ ] **Step 8: Clean only owned processes and audit Git**

Stop only PIDs/process groups/runtime tmux sessions recorded as created by this task. Re-run PID, ROS node, and Gazebo service inventory and distinguish preserved pre-existing processes from removed task processes.

```zsh
implementation_base="$(cat "$run_to_plan_evidence/implementation-base.txt")"
git status --short --branch
git log --oneline --decorate "$implementation_base"..HEAD
git diff "$implementation_base"..HEAD --check
git diff --stat "$implementation_base"..HEAD
```

- [ ] **Step 9: Produce the final evidence report**

Report all fields, with no blank entries:

```text
Root cause: CONFIRMED
First bad boundary: old fresh plan-only skipped PREPARE_OPEN_GRIPPER
Change: common run-to target boundary plus robot entry migration
RED tests: commands, exit codes, first expected failures
GREEN/package tests: commands, exit codes, totals
SO-101 shallow/deep runtime: commands and result
Panda shallow/deep runtime: commands and result
Target failure recovery: original code, recovery route, final facts
Gazebo proof: attachment and Coke pose
MoveIt proof: world/attached membership and link
Controller/joint/TF proof: target-entry before/after values
Visual proof: fresh screenshot paths and observed scene
Provenance: branch, commits, package prefixes, executable paths
Preserved user state: worktrees/processes left untouched
Remaining risks: exact unverified item or none
```

**Acceptance:** all automated and runtime gates in the approved spec pass, new screenshots are actually inspected, no target executor is observed for any plan-only target, no duplicate stack remains, worktree is clean, and nothing is pushed or merged.

---

## Final Spec-Coverage Checklist

- Explicit target and six-state whitelist: Tasks 1 and 4.
- Execute every verified predecessor: Tasks 2, 5, 6, and 8.
- Observe/precondition/plan/validate target without execute: Tasks 2, 5, 6, and 8.
- Execute/FORWARD checkpoint at target entry and schema-v3 stability: Tasks 2, 3, 6, and 8.
- Same/upstream resume, passed/recovery rejection: Task 3.
- Target failure recovery and original provenance: Tasks 2, 3, and 8.
- Panda full dependency assembly: Task 5.
- Common session lifecycle and SO-101 workaround removal: Task 4 and Task 5.
- Standalone launch parameter manual and all links: Task 7.
- RED/GREEN, three-package tests, runtime provenance, Gazebo/MoveIt/controller/joint/TF, and fresh visual evidence: Task 8.
- No initial q6 change, no recovery whitelist, no checkpoint schema change, no push/merge: Global Constraints and Task 8 audit.
