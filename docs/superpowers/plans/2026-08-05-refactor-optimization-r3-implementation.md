# Refactor Optimization R3 Implementation Plan

> **For the tmux `codex` worker:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore SO-101 physical-grasp validation and safe force-continue semantics, preserve the public request source contract, and remove verified dead execution paths without changing Panda or R1/R2 recovery behavior.

**Architecture:** `pick_place_common` remains the sole runner/checkpoint owner and interprets only workflow-declared pause states. SO-101 owns physical failure codes, evidence, and transitions; Panda declares no pause state. Public request compatibility is restored by retaining the former aggregate prefix, while dead robot-specific entry points are removed.

**Tech Stack:** C++17, ROS 2 Jazzy, MoveIt 2, Gazebo Harmonic, `ament_cmake`, GoogleTest, `pytest`, launch testing, zsh, tmux, CUA screenshots.

## Global Constraints

- Implement only after the R3 document commit is an ancestor of the latest `origin/main`.
- Create `/data/work/ws_moveit/.worktrees/refactor-optimization-r3` on branch `codex/refactor-optimization-r3` from that updated `origin/main`.
- Use only the R3 worktree's `build/`, `install/`, and `log/`; never source `/data/work/ws_moveit/install`.
- Do not weaken physical-grasp thresholds, contact rules, recovery-skip predicates, resume validation, checkpoint/session/provenance, or robot safety policy.
- Force-continue remains execute-resume only; do not add plan-only force-continue.
- Panda must keep an empty force-continue state set and its existing trace/recovery/runtime behavior.
- Do not run `ament_uncrustify --reformat`.
- Do not merge, push, or operate `codex-cua`.
- Preserve unrelated worktrees, root checkout, sampler clang-tidy, and non-R3 processes.

---

### Task 1: Establish the R3 baseline and evidence directory

**Files:**
- Read: `docs/superpowers/specs/2026-08-05-refactor-optimization-r3-design.md`
- Read: `docs/superpowers/plans/2026-08-05-refactor-optimization-r3-implementation.md`
- Evidence only: a directory created by `mktemp -d /tmp/so101-refactor-r3-$(date +%Y%m%d-%H%M%S)-XXXXXX`

**Interfaces:**
- Consumes: the user-approved R3 document commit integrated into `origin/main`.
- Produces: an isolated R3 worktree, recorded baseline, and a stop/go decision.

- [ ] **Step 1: Read project instructions and the approved documents**

Run from the repository root:

```bash
sed -n '1,260p' AGENTS.md
sed -n '1,260p' moveit-demo/AGENTS.md
sed -n '1,260p' .agents/skills/so101-dev/SKILL.md
sed -n '1,260p' .agents/skills/so101-dev/references/ai-station-access.md
sed -n '1,260p' .agents/skills/so101-dev/references/so101-system-map.md
sed -n '1,260p' .agents/skills/so101-dev/references/debug-evidence.md
sed -n '1,260p' .agents/skills/so101-dev/references/test-and-acceptance.md
```

Expected: all files are present; the agent records that it is already on `AI-STATION-001` and does not SSH to itself.

- [ ] **Step 2: Verify the integration gate**

```bash
cd /data/work/ws_moveit
git fetch origin --prune
git log -1 --format='%H %s' origin/main
document_commit=$(git log -1 --format=%H origin/main -- \
  docs/superpowers/specs/2026-08-05-refactor-optimization-r3-design.md \
  docs/superpowers/plans/2026-08-05-refactor-optimization-r3-implementation.md)
test -n "$document_commit"
git show --stat --oneline "$document_commit"
git merge-base --is-ancestor "$document_commit" origin/main
```

Expected: exit 0. If the document commit is absent or not an ancestor, stop and report `R2/R3 documents are not integrated into latest origin/main`; do not create or rebase an implementation branch.

- [ ] **Step 3: Create the isolated worktree**

Use the `superpowers:using-git-worktrees` skill, then:

```bash
git worktree add /data/work/ws_moveit/.worktrees/refactor-optimization-r3 \
  -b codex/refactor-optimization-r3 origin/main
cd /data/work/ws_moveit/.worktrees/refactor-optimization-r3
git status --short
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
```

Expected: clean status, branch `codex/refactor-optimization-r3`, HEAD equal to the fetched `origin/main`.

- [ ] **Step 4: Record provenance and process ownership**

```bash
evidence_dir=$(mktemp -d /tmp/so101-refactor-r3-$(date +%Y%m%d-%H%M%S)-XXXXXX)
printf '%s\n' "$evidence_dir" > /tmp/refactor-r3-evidence-dir
pwd > "$evidence_dir/baseline.txt"
git rev-parse HEAD >> "$evidence_dir/baseline.txt"
git status --short >> "$evidence_dir/baseline.txt"
tmux list-sessions > "$evidence_dir/tmux-before.txt" 2>&1 || true
ps -eo pid,ppid,lstart,args | rg 'gz sim|move_group|rviz2|controller_manager|pick_place_state_machine|clang-tidy' \
  > "$evidence_dir/processes-before.txt" || true
```

Expected: existing stacks and sampler processes are identified before any launch.

---

### Task 2: Add RED contracts for the restored SO-101 chain and common force-continue state

**Files:**
- Modify: `src/so101_gazebo_demo/test/pick_place/test_workflow_characterization.cpp:22-47`
- Modify: `src/pick_place_common/test/test_run_to_plan_only.cpp`
- Modify: `src/pick_place_common/test/test_run_request_validation.cpp:35-100`

**Interfaces:**
- Consumes: `WorkflowDefinition::force_continue_states`, schema-v3 `Checkpoint`, `RunRequest::force_continue`, and the existing test harness in `test_run_to_plan_only.cpp`.
- Produces: failing behavioral tests for the safety chain, validation parking, passive resume, override consumption, mismatch rejection, and negative failure categories.

- [ ] **Step 1: Make the SO-101 expected trace require every physical-grasp state**

Change the expected trace segment to:

```cpp
pp::State::CLOSE_GRIPPER,
pp::State::WAIT_GRASP_STABLE,
pp::State::MICRO_LIFT,
pp::State::WAIT_MICRO_LIFT_STABLE,
pp::State::VERIFY_PHYSICAL_GRASP,
pp::State::ATTACH_GAZEBO,
```

Add exact edge assertions:

```cpp
EXPECT_EQ(pp::State::MICRO_LIFT,
          pp::so101WorkflowDefinition()
            .transitions.at(pp::State::WAIT_GRASP_STABLE).succeeded);
EXPECT_EQ(pp::State::VALIDATION_FAILED,
          pp::so101WorkflowDefinition()
            .transitions.at(pp::State::VERIFY_PHYSICAL_GRASP).failed);
```

- [ ] **Step 2: Add common validation-pause tests**

Extend the existing common harness with a workflow whose relevant edges are:

```cpp
workflow.transitions[State::VERIFY_PHYSICAL_GRASP] =
  {State::ATTACH_GAZEBO, State::VALIDATION_FAILED};
workflow.transitions[State::VALIDATION_FAILED] =
  {State::ATTACH_GAZEBO, State::VALIDATION_FAILED};
workflow.force_continue_states = {State::VALIDATION_FAILED};
```

Add these tests with exact assertions:

```cpp
TEST(ForceContinue, PostconditionFailureParksWithoutRecoveryOrAttachment);
TEST(ForceContinue, PassiveExecuteResumePreservesFailureCheckpointAndWorld);
TEST(ForceContinue, ValidSingleStepOverrideExecutesOnlyGazeboAttach);
TEST(ForceContinue, RejectsNormalForwardAndRecoveryCheckpoint);
TEST(ForceContinue, ActionControllerObservationAndPlanningFailuresNeverPark);
TEST(ForceContinue, EmptyWorkflowDeclarationPreservesPandaBehavior);
```

The tests must assert:

```cpp
EXPECT_EQ(RunStatus::CHECKPOINT_COMPLETE, result.status);
EXPECT_EQ(State::VALIDATION_FAILED, result.current_state);
EXPECT_EQ("PHYSICAL_GRASP_FOLLOW_RATIO", result.failure->code);
EXPECT_EQ(State::VERIFY_PHYSICAL_GRASP, stored.failed_state);
EXPECT_EQ(State::VALIDATION_FAILED, stored.next_state);
EXPECT_EQ(CheckpointPhase::FORWARD, stored.phase);
EXPECT_EQ(0, gazebo_attach_calls);
EXPECT_EQ(0, moveit_attach_calls);
```

For passive resume, serialize or compare the full in-memory checkpoint before/after and require zero executor/planner/controller calls. For valid force single-step, require trace `VALIDATION_FAILED, ATTACH_GAZEBO, ATTACH_MOVEIT`, transition count 2, one Gazebo attach call, zero MoveIt attach calls, and next checkpoint `ATTACH_MOVEIT`.

- [ ] **Step 3: Add stable request/checkpoint mismatch assertions**

Keep the existing request-shape code and assert that force-continue with execute-resume is accepted before checkpoint inspection:

```cpp
RunRequest valid;
valid.mode = RunMode::EXECUTE;
valid.resume = true;
valid.force_continue = true;
EXPECT_FALSE(validateRunRequest(workflow, valid));
```

The runner tests must then require `FORCE_CONTINUE_STATE_MISMATCH` for normal forward and recovery checkpoints and verify the store's commit count remains unchanged.

- [ ] **Step 4: Run RED tests**

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select pick_place_common so101_gazebo_demo --symlink-install
source install/setup.zsh
colcon test --packages-select pick_place_common so101_gazebo_demo \
  --ctest-args -R 'test_run_to_plan_only|test_run_request_validation|test_workflow_characterization' \
  --event-handlers console_direct+
colcon test-result --verbose
```

Expected failures:

- SO-101 trace is missing `MICRO_LIFT`, `WAIT_MICRO_LIFT_STABLE`, and `VERIFY_PHYSICAL_GRASP`.
- common runner recovers/rejects instead of parking;
- passive resume reports `CHECKPOINT_INCOMPATIBLE` or loses the failure;
- valid force resume cannot advance;
- mismatch requests are not rejected at checkpoint scope.

- [ ] **Step 5: Commit RED tests**

```bash
git add src/so101_gazebo_demo/test/pick_place/test_workflow_characterization.cpp \
  src/pick_place_common/test/test_run_to_plan_only.cpp \
  src/pick_place_common/test/test_run_request_validation.cpp
git commit -m "test: expose physical validation and force-continue gaps"
```

---

### Task 3: Implement declaration-driven validation parking and force-continue

**Files:**
- Modify: `src/pick_place_common/include/pick_place_common/runner.hpp:66-90`
- Modify: `src/pick_place_common/src/runner.cpp:308-445,638-795,797-860`
- Modify: `src/so101_gazebo_demo/src/pick_place/so101_workflow.cpp:18-23`
- Test: `src/pick_place_common/test/test_run_to_plan_only.cpp`
- Test: `src/so101_gazebo_demo/test/pick_place/test_workflow_characterization.cpp`

**Interfaces:**
- Consumes: a workflow failed edge, `force_continue_states`, `FailureCategory::POSTCONDITION`, `ICheckpointStore`, `CommonResumeValidator`, and the robot transition contract.
- Produces: generic parking/checkpoint behavior and force-resume behavior; no new public robot policy API.

- [ ] **Step 1: Add private runner helpers**

Declare focused private helpers:

```cpp
[[nodiscard]] bool isForceContinueState(State) const noexcept;
[[nodiscard]] bool isForceContinuableFailure(State failed_state,
                                              const Failure &) const noexcept;
[[nodiscard]] RunResult parkForceContinuableFailure(
  State failed_state, State pause_state, Failure, const WorldSnapshot &,
  std::uint64_t checkpoint_sequence) const;
```

`isForceContinuableFailure` returns true only when the failure category is `POSTCONDITION` and `resolve(failed_state, FAILED)` is a declared force-continue state.

- [ ] **Step 2: Persist the parked checkpoint after stop-and-observe**

In `handleActionFailure`, keep cancellation and stopped-world observation first. Before selecting a recovery route, call the parking helper when eligible. Populate:

```cpp
checkpoint.phase = CheckpointPhase::FORWARD;
checkpoint.source_mode = RunMode::EXECUTE;
checkpoint.last_completed_state = failed_state;
checkpoint.failed_state = failed_state;
checkpoint.original_failure = original_failure;
checkpoint.next_state = pause_state;
checkpoint.resumable = true;
```

Copy expected world state, exact session, and fingerprint using the same functions as normal forward checkpoints. Return `CHECKPOINT_COMPLETE` with the original failure. A commit error returns the checkpoint-persistence failure with the physical failure preserved and must not start recovery.

- [ ] **Step 3: Replace the hard-coded validation state branch**

Replace `state == State::VALIDATION_FAILED` with declaration-driven behavior:

```cpp
if (isForceContinueState(state) && !request.force_continue) {
  return {RunStatus::CHECKPOINT_COMPLETE, state, state, workflow_failure,
          transition_count, std::move(trace)};
}
```

When `request.force_continue` is true, validate and count the declared success edge, append the resulting real action state to the trace, clear the parked failure from recovery context, and continue execution. Preserve `single_step`: one real action runs before returning its normal checkpoint.

- [ ] **Step 4: Accept only a valid failed-edge checkpoint**

In `runResume`, compute:

```cpp
const bool validation_pause =
  checkpoint.phase == CheckpointPhase::FORWARD &&
  checkpoint.failed_state == checkpoint.last_completed_state &&
  checkpoint.original_failure.has_value() &&
  isForceContinueState(checkpoint.next_state) &&
  resolve(checkpoint.last_completed_state, ActionStatus::FAILED) == checkpoint.next_state;
```

Accept `validation_pause` as the only exception to the normal forward success-edge check. Reject `request.force_continue` when `validation_pause` is false with:

```cpp
FailureCategory::RESUME_VALIDATION,
"FORCE_CONTINUE_STATE_MISMATCH",
"force_continue requires a declared validation-pause checkpoint"
```

Run common plus robot resume validation before returning passive pause or consuming the override. For the override, validate `pause_state -> succeeded_target`, not `failed_state -> pause_state`.

- [ ] **Step 5: Restore the SO-101 edge**

Change exactly:

```cpp
{S::WAIT_GRASP_STABLE, {S::MICRO_LIFT, S::RECOVER_OPEN_GRIPPER}},
```

Do not change the remaining SO-101 transitions, executors, contracts, policies, or thresholds.

- [ ] **Step 6: Run GREEN targeted tests**

```bash
colcon build --packages-select pick_place_common so101_gazebo_demo --symlink-install
source install/setup.zsh
colcon test --packages-select pick_place_common so101_gazebo_demo \
  --ctest-args -R 'test_run_to_plan_only|test_run_request_validation|test_workflow_characterization|test_pick_place_runner|test_checkpoint' \
  --event-handlers console_direct+
colcon test-result --verbose
```

Expected: all targeted tests pass; SO trace contains the full chain; negative categories still recover/error; Panda-specific code is untouched.

- [ ] **Step 7: Commit common and SO workflow behavior**

```bash
git add src/pick_place_common/include/pick_place_common/runner.hpp \
  src/pick_place_common/src/runner.cpp \
  src/so101_gazebo_demo/src/pick_place/so101_workflow.cpp
git commit -m "fix: enforce physical validation and force-continue semantics"
```

---

### Task 4: Persist SO-101 physical-grasp evidence across CLI processes

**Files:**
- Create: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/physical_grasp_evidence_store.hpp`
- Create: `src/so101_gazebo_demo/src/pick_place/physical_grasp_evidence_store.cpp`
- Create: `src/so101_gazebo_demo/test/pick_place/test_physical_grasp_evidence_store.cpp`
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/pick_place_runtime.hpp:43-49`
- Modify: `src/so101_gazebo_demo/src/pick_place/pick_place_runtime.cpp:497-504,509-640,734-773,805-835`
- Modify: `src/so101_gazebo_demo/src/pick_place/pick_place_state_machine.cpp:224-254`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`
- Test: `src/so101_gazebo_demo/test/pick_place/test_pick_place_runner.cpp`

**Interfaces:**
- Consumes: checkpoint path, simulation session ID, policy-bundle fingerprint, and the historical fields used by `PhysicalGraspValidator`.
- Produces: an atomic robot-local sidecar whose path is the checkpoint path plus `.physical-grasp.json`, and identical continuous/step-mode evidence semantics.

- [ ] **Step 1: Write RED codec, provenance, and lifetime tests**

Define the expected public types in the new test:

```cpp
struct PhysicalGraspSample
{
  State capture_state;
  std::int64_t captured_at_unix_ns;
  Pose3d tcp_pose_world;
  Pose3d task_object_pose_world;
  bool gripper_contact;
};

struct PhysicalGraspEvidenceRecord
{
  std::string simulation_session_id;
  std::string configuration_fingerprint;
  std::optional<PhysicalGraspSample> before_lift;
  std::optional<PhysicalGraspSample> after_lift;
};
```

Add these tests:

```cpp
TEST(PhysicalGraspEvidenceStore, AtomicallyRoundTripsFiniteOrderedSamples);
TEST(PhysicalGraspEvidenceStore, FreshRunRemovesPriorSessionEvidence);
TEST(PhysicalGraspEvidenceStore, RejectsMissingCorruptAndTruncatedFiles);
TEST(PhysicalGraspEvidenceStore, RejectsSessionFingerprintAndStateMismatch);
TEST(PhysicalGraspEvidenceStore, RejectsNonFinitePoseAndReverseCaptureTime);
TEST(PhysicalGraspEvidenceStore, SurvivesDestroyAndRecreateBetweenEveryState);
```

The last test must create/destroy three store/runtime instances: save before, reopen and save after, reopen and load for verification. It must compare the resulting `PhysicalGraspResult` with a continuous in-memory evaluation of the same snapshots.

- [ ] **Step 2: Run RED build**

Add the new test target to CMake but not the implementation source yet:

```cmake
ament_add_gtest(test_physical_grasp_evidence_store
  test/pick_place/test_physical_grasp_evidence_store.cpp)
target_link_libraries(test_physical_grasp_evidence_store
  so101_pick_place_runtime)
```

Then run:

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_gazebo_demo --symlink-install
```

Expected: compile/link failure for the missing evidence-store types and methods.

- [ ] **Step 3: Implement the robot-local version-1 sidecar**

Implement:

```cpp
class IPhysicalGraspEvidenceStore
{
public:
  virtual ~IPhysicalGraspEvidenceStore() = default;
  virtual std::optional<Failure> resetForFreshRun() = 0;
  virtual std::optional<Failure> saveBefore(const WorldSnapshot &) = 0;
  virtual std::optional<Failure> saveAfter(const WorldSnapshot &) = 0;
  virtual std::variant<PhysicalGraspEvidenceRecord, Failure> load() const = 0;
};

class FilePhysicalGraspEvidenceStore final : public IPhysicalGraspEvidenceStore
{
public:
  FilePhysicalGraspEvidenceStore(std::filesystem::path path,
                                 std::string simulation_session_id,
                                 std::string configuration_fingerprint);
  // overrides above
};
```

Use JSON schema:

```json
{
  "schema_version": 1,
  "simulation_session_id": "...",
  "configuration_fingerprint": "...",
  "before_lift": {
    "capture_state": "WAIT_GRASP_STABLE",
    "captured_at_unix_ns": 0,
    "tcp_pose_world": {"x": 0, "y": 0, "z": 0, "qx": 0, "qy": 0, "qz": 0, "qw": 1},
    "task_object_pose_world": {"x": 0, "y": 0, "z": 0, "qx": 0, "qy": 0, "qz": 0, "qw": 1},
    "gripper_contact": true
  },
  "after_lift": null
}
```

Write a same-directory temporary file with mode `0600`, loop on partial writes, `fsync` the file, rename atomically, and `fsync` the parent directory. Reject empty identifiers, unsupported schema, missing fields, non-finite poses, non-unit/degenerate quaternion under the current pose rules, wrong capture states, reverse timestamps, session mismatch, and fingerprint mismatch with stable `PHYSICAL_GRASP_EVIDENCE_*` codes.

Add `src/pick_place/physical_grasp_evidence_store.cpp` to the existing `so101_pick_place_runtime` source list and keep the new test linked only to that runtime library and its existing dependencies.

- [ ] **Step 4: Replace the process-local evidence object**

Add `std::shared_ptr<IPhysicalGraspEvidenceStore> physical_grasp_evidence` to `SO101PickPlaceRuntimeDependencies` and require it in `missingDependencyFailure`.

- `WAIT_GRASP_STABLE` calls `saveBefore` after its stable window succeeds.
- `WAIT_MICRO_LIFT_STABLE` calls `load`, requires `before_lift`, then calls `saveAfter`.
- `VERIFY_PHYSICAL_GRASP` calls `load`, requires both samples, reconstructs the minimal historical `WorldSnapshot` values, and invokes `PhysicalGraspValidator`.
- Any store error fails closed before attachment and is not converted into a force-continuable physical result unless it is the validator's own `PHYSICAL_GRASP_*` postcondition.

In `pick_place_state_machine.cpp`, construct the store with:

```cpp
auto physical_evidence = std::make_shared<FilePhysicalGraspEvidenceStore>(
  options.checkpoint_path.string() + ".physical-grasp.json",
  *session.value,
  bundle.bundle_sha256);
if (!options.request.resume) {
  if (const auto failure = physical_evidence->resetForFreshRun()) {
    printPreRunnerFailure(*failure);
    return 1;
  }
}
dependencies.physical_grasp_evidence = physical_evidence;
```

- [ ] **Step 5: Run GREEN unit and process-lifetime tests**

```bash
colcon build --packages-select so101_gazebo_demo --symlink-install
source install/setup.zsh
colcon test --packages-select so101_gazebo_demo \
  --ctest-args -R 'test_physical_grasp_evidence_store|test_pick_place_runner|test_so101_pick_place_runtime' \
  --event-handlers console_direct+
colcon test-result --verbose
```

Expected: all evidence-store tests pass; recreated runtimes produce the same physical result; missing/corrupt/stale evidence fails before attachment.

- [ ] **Step 6: Commit durable robot evidence**

```bash
git add src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/physical_grasp_evidence_store.hpp \
  src/so101_gazebo_demo/src/pick_place/physical_grasp_evidence_store.cpp \
  src/so101_gazebo_demo/test/pick_place/test_physical_grasp_evidence_store.cpp \
  src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/pick_place_runtime.hpp \
  src/so101_gazebo_demo/src/pick_place/pick_place_runtime.cpp \
  src/so101_gazebo_demo/src/pick_place/pick_place_state_machine.cpp \
  src/so101_gazebo_demo/test/pick_place/test_pick_place_runner.cpp \
  src/so101_gazebo_demo/CMakeLists.txt
git commit -m "fix(so101): persist physical grasp evidence across steps"
```

---

### Task 5: Restore `RunRequest` aggregate source compatibility

**Files:**
- Modify: `src/pick_place_common/include/pick_place_common/domain_types.hpp:98-108`
- Modify: `src/pick_place_common/test/test_run_request_validation.cpp`
- Modify: `src/panda_gazebo_demo/test/pick_place/test_workflow_characterization.cpp`
- Modify: `src/so101_gazebo_demo/test/pick_place/test_workflow_characterization.cpp`

**Interfaces:**
- Consumes: both robot compatibility aliases of `pick_place_common::RunRequest`.
- Produces: the historical field prefix plus appended `plan_only_state`; `RunRequest` remains an aggregate.

- [ ] **Step 1: Add RED source-contract assertions**

In `src/pick_place_common/test/test_run_request_validation.cpp`, add only the aggregate property assertion:

```cpp
#include <type_traits>

static_assert(std::is_aggregate_v<pick_place_common::RunRequest>);
```

In the Panda characterization test, compile the historical five-field form:

```cpp
const panda_gazebo_demo::pick_place::RunRequest panda_old{
  RunMode::EXECUTE, std::nullopt, true, std::nullopt, 100};
EXPECT_TRUE(panda_old.resume);
EXPECT_EQ(100U, panda_old.max_state_transitions);
EXPECT_FALSE(panda_old.plan_only_state);
```

In the SO-101 characterization test, compile the historical seven-field form:

```cpp
const so101_gazebo_demo::pick_place::RunRequest so101_old{
  RunMode::EXECUTE, std::nullopt, true, std::nullopt, 100, true, true};
EXPECT_TRUE(so101_old.single_step);
EXPECT_TRUE(so101_old.force_continue);
EXPECT_FALSE(so101_old.plan_only_state);
```

Run the owning characterization tests. Expected RED: both initializers fail to compile because the third field is `plan_only_state`.

- [ ] **Step 2: Append the new field**

Reorder only the declaration:

```cpp
RunMode mode{RunMode::DRY_RUN};
std::optional<State> stop_after;
bool resume{false};
std::optional<State> fail_at;
std::uint64_t max_state_transitions{100};
bool single_step{false};
bool force_continue{false};
std::optional<State> plan_only_state;
```

Do not add a constructor. Confirm every in-tree non-test caller assigns fields by name.

- [ ] **Step 3: Run GREEN compile and request tests**

```bash
colcon build --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo \
  --symlink-install
source install/setup.zsh
colcon test --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo \
  --ctest-args -R 'test_run_request_validation|test_workflow_characterization' \
  --event-handlers console_direct+
colcon test-result --verbose
```

Expected: old forms compile, defaults remain unchanged, and all plan-only request tests pass.

- [ ] **Step 4: Commit the compatibility repair**

```bash
git add src/pick_place_common/include/pick_place_common/domain_types.hpp \
  src/pick_place_common/test/test_run_request_validation.cpp \
  src/panda_gazebo_demo/test/pick_place/test_workflow_characterization.cpp \
  src/so101_gazebo_demo/test/pick_place/test_workflow_characterization.cpp
git commit -m "fix(api): preserve RunRequest aggregate prefix"
```

---

### Task 6: Remove the dead Panda bypass and SO Teleop callback

**Files:**
- Delete: `src/panda_gazebo_demo/src/attach_and_lift_demo.cpp`
- Delete: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/headless_fault_fixture.hpp`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt:151-180,454-462`
- Modify: `src/panda_gazebo_demo/test/pick_place/test_pick_place_targets.cpp:1-109`
- Modify: `src/panda_gazebo_demo/test/test_source_manifest.py`
- Modify: `src/so101_gazebo_demo/so101_teleop/server.py:210-220`
- Modify: `src/so101_gazebo_demo/test/teleop/test_server_safety.py`

**Interfaces:**
- Consumes: the supported `pick_place_state_machine` and active `_on_gazebo_pose` path.
- Produces: no installed alternate attach/lift executable and no unused pose mutation callback.

- [ ] **Step 1: Add RED package/source contracts**

Add to the Panda manifest test:

```python
def test_no_state_machine_bypass_executable_is_built_or_installed():
    cmake = (PACKAGE_ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
    assert 'attach_and_lift_demo' not in cmake
    assert not (PACKAGE_ROOT / 'src' / 'attach_and_lift_demo.cpp').exists()
    assert not (PACKAGE_ROOT / 'include' / 'panda_gazebo_demo' / 'pick_place' /
                'headless_fault_fixture.hpp').exists()
```

Add to SO Teleop safety tests:

```python
def test_legacy_gazebo_pose_callback_is_removed():
    source = (PACKAGE_ROOT / 'so101_teleop' / 'server.py').read_text()
    assert '_legacy_bridge_pose_unused' not in source
```

Run both tests. Expected RED: the executable/header/method still exist.

- [ ] **Step 2: Remove only dead Panda artifacts**

Delete the two files. Remove `attach_and_lift_demo` from `add_executable`, `ament_target_dependencies`, `target_link_libraries`, the common quality-gate target list, and the install target list. Remove the three `HeadlessFaultFixture` tests and their now-unused `<limits>` include; keep all `FixedTargets` tests.

- [ ] **Step 3: Remove only the unused SO callback**

Delete `_legacy_bridge_pose_unused`. Keep `_on_gazebo_pose`, its `/so101/gazebo_pose_info` subscription, and the `TFMessage` import.

- [ ] **Step 4: Run GREEN package/source tests and executable inspection**

```bash
colcon build --packages-select panda_gazebo_demo so101_gazebo_demo --symlink-install
source install/setup.zsh
PYTHONNOUSERSITE=1 colcon test --packages-select panda_gazebo_demo so101_gazebo_demo \
  --ctest-args -R 'test_source_manifest|test_pick_place_targets|test_server_safety' \
  --event-handlers console_direct+
ros2 pkg executables panda_gazebo_demo | tee "$(cat /tmp/refactor-r3-evidence-dir)/panda-executables.txt"
! ros2 pkg executables panda_gazebo_demo | rg 'attach_and_lift_demo'
```

Expected: tests pass and the removed executable is absent from the R3 install.

- [ ] **Step 5: Commit dead-code removal**

```bash
git add -A -- src/panda_gazebo_demo/CMakeLists.txt \
  src/panda_gazebo_demo/src/attach_and_lift_demo.cpp \
  src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/headless_fault_fixture.hpp \
  src/panda_gazebo_demo/test/pick_place/test_pick_place_targets.cpp \
  src/panda_gazebo_demo/test/test_source_manifest.py \
  src/so101_gazebo_demo/so101_teleop/server.py \
  src/so101_gazebo_demo/test/teleop/test_server_safety.py
git commit -m "refactor: remove stale robot bypass paths"
```

---

### Task 7: Update architecture and launch documentation

**Files:**
- Modify: `docs/pick-place-architecture.md`
- Modify: `docs/pick-place-launch-parameters.md`
- Modify: `src/so101_gazebo_demo/README.md`
- Modify: `src/panda_gazebo_demo/README.md`
- Modify: `src/pick_place_common/README.md`
- Modify: `src/so101_gazebo_demo/test/test_so101_launch_contract.py`
- Modify: `src/panda_gazebo_demo/test/test_panda_launch_contract.py`

**Interfaces:**
- Consumes: final R3 behavior and installed `--show-args` output.
- Produces: one authoritative startup/control manual with exact pause, resume, force, and deep plan-only semantics.

- [ ] **Step 1: Add RED documentation contracts**

Assert the launch manual contains the exact chain and codes:

```python
assert 'WAIT_GRASP_STABLE -> MICRO_LIFT -> WAIT_MICRO_LIFT_STABLE' in manual
assert 'VERIFY_PHYSICAL_GRASP -> VALIDATION_FAILED' in manual
assert 'FORCE_CONTINUE_STATE_MISMATCH' in manual
assert 'normal execute resume' in manual
assert 'checkpoint bytes unchanged' in manual
```

Expected RED: current docs claim grasp-stability predecessors but omit the real chain and force-resume matrix.

- [ ] **Step 2: Update the docs**

Document:

- restored physical-grasp states before attachment;
- robot-local evidence sidecar path, session/fingerprint binding, and fresh-run reset;
- identical continuous and subprocess-per-step validation semantics;
- the passive validation checkpoint and original failure;
- normal resume as side-effect-free at `VALIDATION_FAILED`;
- force-continue as execute-resume only and mismatch rejection;
- deep plan-only must pass physical validation naturally;
- `RunRequest` new fields must be set by name;
- `attach_and_lift_demo` is no longer an installed entry point;
- common is declaration-driven and Panda has no force-continue state.

Do not duplicate every launch argument in package READMEs; link them to `docs/pick-place-launch-parameters.md`.

- [ ] **Step 3: Compare installed arguments with the manual**

```bash
source /opt/ros/jazzy/setup.zsh
source install/setup.zsh
ros2 launch panda_gazebo_demo panda_gazebo.launch.py --show-args \
  > "$(cat /tmp/refactor-r3-evidence-dir)/panda-show-args.txt"
ros2 launch so101_gazebo_demo so101_pick_place.launch.py --show-args \
  > "$(cat /tmp/refactor-r3-evidence-dir)/so101-show-args.txt"
```

Expected: defaults, names, and mode semantics match the manual; no new launch parameter is invented.

- [ ] **Step 4: Run docs/launch tests and commit**

```bash
PYTHONNOUSERSITE=1 colcon test --packages-select panda_gazebo_demo so101_gazebo_demo \
  --ctest-args -R 'test_panda_launch_contract|test_so101_launch_contract' \
  --event-handlers console_direct+
colcon test-result --verbose
git add docs/pick-place-architecture.md docs/pick-place-launch-parameters.md \
  src/pick_place_common/README.md src/panda_gazebo_demo/README.md \
  src/so101_gazebo_demo/README.md \
  src/panda_gazebo_demo/test/test_panda_launch_contract.py \
  src/so101_gazebo_demo/test/test_so101_launch_contract.py
git commit -m "docs: define physical validation and force-resume controls"
```

---

### Task 8: Run the clean three-package automated gate

**Files:**
- Evidence: `$evidence_dir/three-package-build.log`
- Evidence: `$evidence_dir/three-package-test.log`
- Evidence: `$evidence_dir/test-result.txt`

**Interfaces:**
- Consumes: all R3 commits.
- Produces: a clean build and complete affected-package regression result.

- [ ] **Step 1: Clean-cache build from the R3 worktree**

```bash
cd /data/work/ws_moveit/.worktrees/refactor-optimization-r3
source /opt/ros/jazzy/setup.zsh
evidence_dir=$(cat /tmp/refactor-r3-evidence-dir)
colcon build --packages-up-to panda_gazebo_demo so101_gazebo_demo \
  --symlink-install --cmake-clean-cache 2>&1 | tee "$evidence_dir/three-package-build.log"
source install/setup.zsh
```

Expected: build exit 0; no source or install path from the root workspace.

- [ ] **Step 2: Verify overlay provenance**

```bash
for package in pick_place_common panda_gazebo_demo so101_gazebo_demo; do
  ros2 pkg prefix "$package"
done | tee "$evidence_dir/r3-overlay-provenance.txt"
printf '%s\n' "$AMENT_PREFIX_PATH" >> "$evidence_dir/r3-overlay-provenance.txt"
```

Expected: all package prefixes begin with `/data/work/ws_moveit/.worktrees/refactor-optimization-r3/install`.

- [ ] **Step 3: Run all three package tests**

```bash
PYTHONNOUSERSITE=1 colcon test \
  --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo \
  --event-handlers console_direct+ 2>&1 | tee "$evidence_dir/three-package-test.log"
colcon test-result --verbose | tee "$evidence_dir/test-result.txt"
```

Expected: 0 errors, 0 failures. Record the new total and explain count changes caused by removed fault-fixture tests and added R3 tests.

- [ ] **Step 4: Commit any test-only corrections**

If a scoped test expectation needs correction without changing approved semantics, name the exact files in the completion log, stage only those named files, and make a separate `test: finalize R3 regression contracts` commit. Stop instead of editing if a failure requires threshold, geometry, policy, checkpoint, session, or provenance changes.

---

### Task 9: Validate SO-101 physical pause and force-resume at runtime

**Files:**
- Evidence: `$evidence_dir/so101-runtime/`
- No source changes unless an existing approved assertion has a clear implementation bug.

**Interfaces:**
- Consumes: the R3 overlay and restored chain.
- Produces: authoritative Gazebo, MoveIt, controller/joint/TF, checkpoint, failure, trace, session, and visual evidence.

- [ ] **Step 1: Confirm no conflicting stack and launch one isolated R3 stack**

Identify exact existing PIDs and ownership first. Create the evidence directories, then add two named windows to the existing tmux `codex` session; do not create or touch `codex-cua`:

```bash
evidence_dir=$(cat /tmp/refactor-r3-evidence-dir)
mkdir -p "$evidence_dir/so101-runtime/ros"
tmux new-window -d -t codex -n r3-so101-gazebo \
  "zsh -lc 'export ROS_DOMAIN_ID=143 GZ_PARTITION=r3-so101-validation ROS_LOG_DIR=$evidence_dir/so101-runtime/ros; source ~/gui-env.zsh; source /opt/ros/jazzy/setup.zsh; source /data/work/ws_moveit/.worktrees/refactor-optimization-r3/install/setup.zsh; exec ros2 launch so101_gazebo_demo so101_gazebo.launch.py headless:=false'"
tmux new-window -d -t codex -n r3-so101-moveit \
  "zsh -lc 'export ROS_DOMAIN_ID=143 GZ_PARTITION=r3-so101-validation ROS_LOG_DIR=$evidence_dir/so101-runtime/ros; source ~/gui-env.zsh; source /opt/ros/jazzy/setup.zsh; source /data/work/ws_moveit/.worktrees/refactor-optimization-r3/install/setup.zsh; exec ros2 launch so101_gazebo_demo so101_move_group_headless.launch.py'"
```

Expected: exactly one R3-owned Gazebo/MoveIt/controller stack in domain 143 and partition `r3-so101-validation`.

- [ ] **Step 2: Run the natural physical-grasp path continuously and step-by-step**

In the controlling `codex` window, use only the R3 overlay. Run a canonical reset before each case. The continuous case is one process:

```bash
export ROS_DOMAIN_ID=143 GZ_PARTITION=r3-so101-validation
evidence_dir=$(cat /tmp/refactor-r3-evidence-dir)
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_moveit/.worktrees/refactor-optimization-r3/install/setup.zsh
ros2 run so101_gazebo_demo reset_so101_world
ros2 run so101_gazebo_demo pick_place_state_machine \
  --mode execute \
  --checkpoint /tmp/so101-r3-continuous-checkpoint.json \
  --session-id r3-so101-continuous \
  2>&1 | tee "$evidence_dir/so101-runtime/continuous.log"
cp /tmp/so101-r3-continuous-checkpoint.json.physical-grasp.json \
  "$evidence_dir/so101-runtime/continuous-physical-grasp.json"
```

The natural step case uses a new session and a new CLI process for every state. The initial request executes `PREPARE_OPEN_GRIPPER`; the seven resumes execute through `VERIFY_PHYSICAL_GRASP` and leave the normal next-state checkpoint at `ATTACH_GAZEBO`:

```bash
ros2 run so101_gazebo_demo reset_so101_world
ros2 run so101_gazebo_demo pick_place_state_machine \
  --mode execute --step \
  --checkpoint /tmp/so101-r3-natural-step-checkpoint.json \
  --session-id r3-so101-natural-step \
  2>&1 | tee "$evidence_dir/so101-runtime/natural-step-00.log"
for step_index in {1..7}; do
  ros2 run so101_gazebo_demo pick_place_state_machine \
    --mode execute --resume --step \
    --checkpoint /tmp/so101-r3-natural-step-checkpoint.json \
    --session-id r3-so101-natural-step \
    2>&1 | tee "$evidence_dir/so101-runtime/natural-step-${step_index}.log"
done
cp /tmp/so101-r3-natural-step-checkpoint.json.physical-grasp.json \
  "$evidence_dir/so101-runtime/natural-step-physical-grasp.json"
```

Record traces, sidecar JSON, and physical metrics for both. If either reset does not independently prove canonical detached world, safe-home joints, and open gripper, stop before the corresponding run.

Required trace prefix:

```text
... CLOSE_GRIPPER -> WAIT_GRASP_STABLE -> MICRO_LIFT ->
WAIT_MICRO_LIFT_STABLE -> VERIFY_PHYSICAL_GRASP -> ATTACH_GAZEBO
```

Required evidence: positive TCP Z delta, cup-follow ratio, table clearance, contact, XY slip, orientation delta, fresh timestamps, and PASS before any attachment. If it fails naturally, stop with the exact evidence; do not alter thresholds or force the result green.

Required A/B: the two runs produce the same pass/fail decision and equivalent metrics within observation tolerance; the step run's sidecar contains ordered `WAIT_GRASP_STABLE` and `WAIT_MICRO_LIFT_STABLE` samples with the exact session/fingerprint.

- [ ] **Step 3: Create a deterministic validation-pause checkpoint**

Start a third canonical-reset step flow. Run the fresh request plus six resume subprocesses so its checkpoint names `VERIFY_PHYSICAL_GRASP`; also save the initial normal-forward checkpoint for the negative override check:

```bash
ros2 run so101_gazebo_demo reset_so101_world
ros2 run so101_gazebo_demo pick_place_state_machine \
  --mode execute --step \
  --checkpoint /tmp/so101-r3-step-checkpoint.json \
  --session-id r3-so101-injected-step \
  2>&1 | tee "$evidence_dir/so101-runtime/injected-step-00.log"
sha256sum /tmp/so101-r3-step-checkpoint.json \
  > "$evidence_dir/so101-runtime/normal-forward-before.sha256"
ros2 run so101_gazebo_demo pick_place_state_machine \
  --mode execute --resume --force-continue \
  --checkpoint /tmp/so101-r3-step-checkpoint.json \
  --session-id r3-so101-injected-step \
  2>&1 | tee "$evidence_dir/so101-runtime/normal-forward-force-rejected.log"
sha256sum /tmp/so101-r3-step-checkpoint.json \
  > "$evidence_dir/so101-runtime/normal-forward-after.sha256"
for step_index in {1..6}; do
  ros2 run so101_gazebo_demo pick_place_state_machine \
    --mode execute --resume --step \
    --checkpoint /tmp/so101-r3-step-checkpoint.json \
    --session-id r3-so101-injected-step \
    2>&1 | tee "$evidence_dir/so101-runtime/injected-step-${step_index}.log"
done
```

Copy the resulting sidecar to the evidence directory, then create a test-owned failing version with the same valid session/fingerprint and a cup Z value that does not follow the TCP micro-lift:

```bash
checkpoint_path=/tmp/so101-r3-step-checkpoint.json
sidecar=/tmp/so101-r3-step-checkpoint.json.physical-grasp.json
cp "$sidecar" "$evidence_dir/so101-runtime/physical-grasp-sidecar-pass.json"
jq '.after_lift.task_object_pose_world.z = .before_lift.task_object_pose_world.z' \
  "$sidecar" > "$sidecar.injected.tmp"
mv "$sidecar.injected.tmp" "$sidecar"
```

Run the next `VERIFY_PHYSICAL_GRASP` execute-resume step:

```bash
ros2 run so101_gazebo_demo pick_place_state_machine \
  --mode execute --resume --step \
  --checkpoint /tmp/so101-r3-step-checkpoint.json \
  --session-id r3-so101-injected-step \
  2>&1 | tee "$evidence_dir/so101-runtime/injected-validation-failure.log"
```

This is a test-owned `/tmp` evidence mutation, not a production parameter or threshold change. It must produce a deterministic `PHYSICAL_GRASP_*` failure from the real validator and live stack.

Required:

```text
status=CHECKPOINT_COMPLETE
trace ends VERIFY_PHYSICAL_GRASP -> VALIDATION_FAILED
checkpoint.phase=FORWARD
checkpoint.next_state=VALIDATION_FAILED
checkpoint.original_failure.code=PHYSICAL_GRASP_...
Gazebo detached
MoveIt world=true attached=false
```

- [ ] **Step 4: Prove passive execute-resume has no side effects**

Before and after normal execute-resume, capture the checkpoint and sidecar SHA plus:

```bash
checkpoint_path=/tmp/so101-r3-step-checkpoint.json
sidecar=/tmp/so101-r3-step-checkpoint.json.physical-grasp.json
sha256sum "$checkpoint_path" "$sidecar"
ros2 topic echo /joint_states --once
timeout 5 ros2 run tf2_ros tf2_echo base so101_tcp
ros2 control list_controllers
gz topic -e -t /so101/object_attached -n 1
ros2 run so101_gazebo_demo so101_moveit_scene observe
```

Run the passive request explicitly:

```bash
ros2 run so101_gazebo_demo pick_place_state_machine \
  --mode execute --resume \
  --checkpoint /tmp/so101-r3-step-checkpoint.json \
  --session-id r3-so101-injected-step \
  2>&1 | tee "$evidence_dir/so101-runtime/passive-validation-resume.log"
```

Normalize timestamps only; retain raw files. Required: checkpoint bytes/SHA, original failure, session, trace, controllers, joints, TF, Gazebo, and MoveIt all unchanged; no planner/executor/controller request occurs.

- [ ] **Step 5: Prove mismatch rejection**

The normal-forward mismatch was run immediately after the fresh step request in Step 3, while the live world still matched that checkpoint. Compare its before/after SHA files now. Defer the recovery-checkpoint mismatch until after the valid override workflow finishes so it cannot perturb the parked validation world.

Expected: `FORCE_CONTINUE_STATE_MISMATCH`, nonzero command result, checkpoint bytes unchanged, and zero physical/planning side effects.

- [ ] **Step 6: Consume one valid override step**

Independently prove that the live world still matches the parked validation checkpoint after the passive resume. Then run:

```bash
ros2 run so101_gazebo_demo pick_place_state_machine \
  --mode execute --resume --force-continue --step \
  --checkpoint /tmp/so101-r3-step-checkpoint.json \
  --session-id r3-so101-injected-step \
  2>&1 | tee "$evidence_dir/so101-runtime/valid-force-step.log"
```

Expected:

- trace `VALIDATION_FAILED -> ATTACH_GAZEBO -> ATTACH_MOVEIT`;
- transition count 2;
- Gazebo attached=true;
- MoveIt still world=true and attached=false;
- checkpoint next state `ATTACH_MOVEIT` with the same session/fingerprint;
- Teleop audit retains command ID, confirmation, snapshot revision, and original physical failure metrics.

- [ ] **Step 7: Finish and inspect fresh visuals**

Resume normally to `DONE`:

```bash
ros2 run so101_gazebo_demo pick_place_state_machine \
  --mode execute --resume \
  --checkpoint /tmp/so101-r3-step-checkpoint.json \
  --session-id r3-so101-injected-step \
  2>&1 | tee "$evidence_dir/so101-runtime/finish-after-force.log"
```

Capture and inspect fresh images at baseline, validation pause, after Gazebo attach, after MoveIt attach, and final detached supported pose. Use the project `so101-dev` CUA/capture procedure, record the generated absolute paths in `$evidence_dir/so101-runtime/visual-evidence.txt`, and correlate each image to logs/state samples.

- [ ] **Step 8: Reject a recovery checkpoint, then clean only R3-owned processes**

After the valid workflow is complete, reset to canonical state and generate the same precise plan-validation recovery fixture used by R2. The unchanged policy must naturally produce `TCP_ENDPOINT_OUTSIDE_TOLERANCE`; do not alter its endpoint or tolerance:

```bash
ros2 run so101_gazebo_demo reset_so101_world
ros2 run so101_gazebo_demo pick_place_state_machine \
  --mode plan_only --plan-only-state MOVE_ABOVE_OBJECT \
  --checkpoint /tmp/so101-r3-recovery-checkpoint.json \
  --session-id r3-so101-recovery \
  2>&1 | tee "$evidence_dir/so101-runtime/recovery-fixture.log"
rg 'TCP_ENDPOINT_OUTSIDE_TOLERANCE' "$evidence_dir/so101-runtime/recovery-fixture.log"
sha256sum /tmp/so101-r3-recovery-checkpoint.json \
  > "$evidence_dir/so101-runtime/recovery-before.sha256"
ros2 run so101_gazebo_demo pick_place_state_machine \
  --mode execute --resume --force-continue \
  --checkpoint /tmp/so101-r3-recovery-checkpoint.json \
  --session-id r3-so101-recovery \
  2>&1 | tee "$evidence_dir/so101-runtime/recovery-force-rejected.log"
sha256sum /tmp/so101-r3-recovery-checkpoint.json \
  > "$evidence_dir/so101-runtime/recovery-after.sha256"
```

Expected: `FORCE_CONTINUE_STATE_MISMATCH`, nonzero command result, checkpoint bytes unchanged, and zero attachment/planning/controller side effects. If the unchanged fixture no longer produces the exact R2 failure, stop and report the new runtime facts instead of inventing another injection.

Finally stop the identified `r3-so101-gazebo` and `r3-so101-moveit` tmux windows/PIDs, then re-run process and ROS-node listings. Preserve sampler clang-tidy, other worktrees, root checkout, and unrelated user processes.

---

### Task 10: Run Panda runtime regression and final audit

**Files:**
- Evidence: `$evidence_dir/panda-runtime/`
- Evidence: `$evidence_dir/final-audit.txt`

**Interfaces:**
- Consumes: final R3 overlay.
- Produces: Panda non-regression proof and a clean, reviewable branch.

- [ ] **Step 1: Run the six-target Panda plan-only/resume matrix**

Run the existing R3-worktree harness with a unique ROS domain/partition:

```bash
cd /data/work/ws_moveit/.worktrees/refactor-optimization-r3
evidence_dir=$(cat /tmp/refactor-r3-evidence-dir)
mkdir -p "$evidence_dir/panda-runtime"
ROS_DOMAIN_ID=144 GZ_PARTITION=r3-panda-plan-matrix \
  bash src/panda_gazebo_demo/test/headless/run_plan_only_resume_matrix.sh \
  2>&1 | tee "$evidence_dir/panda-runtime/plan-only-resume-matrix.log"
```

Expected: all six approved targets pass; target action is planned but not executed; predecessor/reset invariants remain valid.

- [ ] **Step 2: Run Panda recovery scenarios**

Run the R3-worktree recovery suite from a clean canonical reset:

```bash
ROS_DOMAIN_ID=145 GZ_PARTITION=r3-panda-recovery \
  bash src/panda_gazebo_demo/test/headless/run_recovery_scenarios.sh \
  2>&1 | tee "$evidence_dir/panda-runtime/recovery-scenarios.log"
```

Expected: every scenario passes, original failures remain correct, and Panda declares no force-continue state.

- [ ] **Step 3: Run one fresh Panda GUI execute regression**

Use one isolated R3-owned launch from the R3 overlay in a named window of tmux `codex`:

```bash
tmux new-window -d -t codex -n r3-panda-gui \
  "zsh -lc 'export ROS_DOMAIN_ID=146 GZ_PARTITION=r3-panda-gui; source ~/gui-env.zsh; source /opt/ros/jazzy/setup.zsh; source /data/work/ws_moveit/.worktrees/refactor-optimization-r3/install/setup.zsh; ros2 launch panda_gazebo_demo panda_gazebo.launch.py headless:=false run_state_machine:=true mode:=execute checkpoint_path:=/tmp/panda-r3-gui-checkpoint.json simulation_session_id:=r3-panda-gui 2>&1 | tee $evidence_dir/panda-runtime/gui-execute.log'"
```

Do not use `codex-cua`; stop the window only after the workflow reaches its terminal result. Capture and inspect baseline and final images with the project capture procedure; verify Gazebo object pose/attachment, MoveIt world/attached membership, controllers, joints, TCP/TF, checkpoints, and final supported pose.

- [ ] **Step 4: Final code and Git audit**

```bash
cd /data/work/ws_moveit/.worktrees/refactor-optimization-r3
git diff --check origin/main...HEAD
git status --short
git log --oneline origin/main..HEAD
rg -n 'attach_and_lift_demo|_legacy_bridge_pose_unused' src || true
ros2 pkg executables panda_gazebo_demo | rg 'attach_and_lift_demo' && exit 1 || true
ps -eo pid,ppid,lstart,args | rg 'r3-so101-validation|refactor-optimization-r3|ROS_DOMAIN_ID=143' || true
```

Expected: `git diff --check` passes, worktree is clean, only scoped R3 commits are present, removed symbols are absent, no R3-owned stack remains, and there was no merge, push, or `codex-cua` interaction.

- [ ] **Step 5: Produce the completion report**

Report exact commit IDs, new test count, 0 errors/failures, RED/GREEN evidence, SO-101 natural validation and parked/force-resume evidence, Panda regressions, screenshot paths, overlay provenance, Git state, process cleanup, and remaining risks. Do not claim completion if any required evidence field is blank.
