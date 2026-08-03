# Panda / SO-101 Pick-Place Common Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one `pick_place_common` ROS 2 package that owns the shared pick-place workflow kernel and selected Gazebo/MoveIt executors while preserving Panda and SO-101 behavior, safety evidence, ROS APIs, and checkpoint v3 compatibility.

**Architecture:** `pick_place_common::core` owns robot-independent domain types, workflow definitions, registries, runner, checkpoint/resume orchestration, and common task-object evidence. `pick_place_common::ros_adapters` owns transport/convergence algorithms; each robot package retains a thin workflow/composition wrapper plus all motion, gripper, geometry, contact, reset, and robot-profile policy.

**Tech Stack:** ROS 2 Jazzy, C++17, ament_cmake, GoogleTest, MoveIt 2, Gazebo Harmonic (`gz-transport13`, `gz-msgs10`), nlohmann JSON, colcon, zsh, tmux/CUA on ai-station.

**Design:** `docs/superpowers/specs/2026-08-03-panda-so101-pick-place-common-refactor-design.md`

## Global Constraints

- Start from `moveit-demo/main@d2a2761617397d9b6fdd14346e1aabca854caa05`; the local documentation commits `ecf8438` and the plan commit may be supplied separately and do not authorize rewriting remote `main`.
- Work on branch `codex/pick-place-common-refactor` in a new validated worktree; do not modify, stash, clean, reset, or reuse a dirty `/data/work/ws_moveit` checkout.
- Read repository `AGENTS.md`, `moveit-demo/AGENTS.md`, and use the project-local `$so101-dev` skill before source changes, tests, runtime work, or visual validation.
- Preserve package names, executable names, launch names, ROS topic/service/action/parameter names, defaults, exit codes, failure codes, state traces, and Teleop Start/Run/Resume owner arguments.
- Preserve checkpoint schema v3 compatibility. A schema v4 migration is outside this plan.
- Gazebo remains authoritative for physical task-object pose/attachment; MoveIt remains authoritative for world/attached collision membership. Neither API success nor `DONE` substitutes for independent evidence.
- Keep motion planning, gripper geometry/control, robot profiles, collision geometry, physical contact validation, reset coordination, recovery policy, launch/world/URDF/SRDF/config, and SO-101 Teleop in their robot packages.
- Do not run `ament_uncrustify --reformat`; use targeted `apply_patch` edits and read-only formatting checks.
- Use RED/GREEN for each changed boundary. Run focused tests before package tests. After C++ changes, rebuild, source the new overlay, and prove package/binary provenance before runtime tests.
- Do not start a second Gazebo, `/move_group`, RViz, controller, or Teleop stack. Reuse or deliberately replace only a PID/session-owned stack.
- Do not operate a real robot. All execute acceptance in this plan is Gazebo simulation.
- Commit each task independently. Stage only paths listed by that task. Do not push, merge, or update the root repository submodule pointer without separate user authorization.

## Target File Structure

```text
src/pick_place_common/
├── CMakeLists.txt
├── package.xml
├── cmake/
│   ├── cpp_quality_gate.cmake
│   ├── pick_place_common-extras.cmake
│   └── run_cpp_quality_gate.cmake
├── include/pick_place_common/
│   ├── checkpoint.hpp
│   ├── common_resume_validator.hpp
│   ├── domain_types.hpp
│   ├── gazebo_attachment_executor.hpp
│   ├── moveit_scene_executor.hpp
│   ├── plan_validation.hpp
│   ├── recovery_policy.hpp
│   ├── runner.hpp
│   ├── simulation_session_id.hpp
│   ├── state_action.hpp
│   ├── transition_contract.hpp
│   ├── workflow_definition.hpp
│   └── world_observer.hpp
├── src/
│   ├── common_resume_validator.cpp
│   ├── domain_types.cpp
│   ├── gazebo_attachment_executor.cpp
│   ├── moveit_scene_executor.cpp
│   ├── plan_validation.cpp
│   ├── runner.cpp
│   ├── simulation_session_id.cpp
│   ├── state_action.cpp
│   ├── transition_contract.cpp
│   ├── workflow_definition.cpp
│   └── world_observer.cpp
└── test/
    ├── test_common_runner.cpp
    ├── test_gazebo_attachment_executor.cpp
    ├── test_moveit_scene_executor.cpp
    └── test_workflow_definition.cpp
```

Robot packages retain forwarding headers under their existing include paths for source compatibility; these headers may contain `using pick_place_common::...` declarations but no algorithm implementation.

---

### Task 1: Capture the pre-refactor behavioral contract

**Files:**
- Create: `src/panda_gazebo_demo/test/pick_place/test_workflow_characterization.cpp`
- Create: `src/so101_gazebo_demo/test/pick_place/test_workflow_characterization.cpp`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`

**Interfaces:**
- Consumes: Existing `State`, `TransitionTable`, `StateMachineRunner`, `RunRequest`, `RunResult`, and `toString()` implementations in each package.
- Produces: Executable behavior locks that later tasks must keep GREEN without changing expected state names, transitions, counts, or request defaults.

- [ ] **Step 1: Record repository and runtime provenance before editing**

Run in the new ai-station worktree shell:

```bash
pwd
git branch --show-current
git rev-parse HEAD
git status --short
git submodule status 2>/dev/null || true
tmux list-sessions 2>/dev/null || true
pgrep -af 'gz sim|move_group|rviz2|pick_place_state_machine|so101_teleop' || true
```

Expected: branch is `codex/pick-place-common-refactor`; source base is `d2a2761`; any pre-existing processes and dirty files are recorded rather than changed.

- [ ] **Step 2: Add Panda workflow characterization**

Create a test that asserts the exact forward success path and representative recovery edges:

```cpp
TEST(PandaWorkflowCharacterization, ForwardAndRecoveryEdgesRemainStable)
{
  using S = panda_gazebo_demo::pick_place::State;
  using A = panda_gazebo_demo::pick_place::ActionStatus;
  const std::vector<S> expected_forward{
    S::IDLE, S::PREPARE_OPEN_GRIPPER, S::MOVE_ABOVE_OBJECT, S::DESCEND,
    S::CLOSE_GRIPPER, S::ATTACH_GAZEBO, S::ATTACH_MOVEIT, S::LIFT,
    S::MOVE_ABOVE_PLACE, S::DESCEND_TO_PLACE, S::OPEN_GRIPPER,
    S::DETACH_GAZEBO, S::DETACH_MOVEIT, S::SYNC_WORLD_OBJECT, S::RETREAT, S::DONE};
  std::vector<S> actual{S::IDLE};
  for (std::size_t i = 1; i < expected_forward.size(); ++i) {
    actual.push_back(panda_gazebo_demo::pick_place::TransitionTable::resolve(
      actual.back(), A::SUCCEEDED));
  }
  EXPECT_EQ(expected_forward, actual);
  EXPECT_EQ(S::RECOVER_RETREAT,
            panda_gazebo_demo::pick_place::TransitionTable::resolve(
              S::MOVE_ABOVE_OBJECT, A::FAILED));
  EXPECT_EQ(S::RECOVER_OPEN_GRIPPER,
            panda_gazebo_demo::pick_place::TransitionTable::resolve(S::DESCEND, A::FAILED));
  EXPECT_EQ(S::RECOVER_LIFT_TO_SAFE_HEIGHT,
            panda_gazebo_demo::pick_place::TransitionTable::resolve(S::LIFT, A::FAILED));
}
```

Add a second test asserting `RunRequest{}` defaults to dry-run, no stop/fail state, no resume, and `max_state_transitions == 100`.

- [ ] **Step 3: Add SO-101 workflow characterization**

Lock both the current default dry-run trace and the extended vocabulary:

```cpp
TEST(SO101WorkflowCharacterization, DefaultDryRunTraceAndExtendedStatesRemainStable)
{
  namespace pp = so101_gazebo_demo::pick_place;
  const pp::StateMachineRunner runner;
  const auto result = runner.run({pp::RunMode::DRY_RUN});
  const std::vector<pp::State> expected{
    pp::State::IDLE, pp::State::PREPARE_OPEN_GRIPPER, pp::State::MOVE_ABOVE_OBJECT,
    pp::State::DESCEND, pp::State::CLOSE_GRIPPER, pp::State::WAIT_GRASP_STABLE,
    pp::State::ATTACH_GAZEBO, pp::State::ATTACH_MOVEIT, pp::State::LIFT,
    pp::State::MOVE_ABOVE_PLACE, pp::State::DESCEND_TO_PLACE, pp::State::OPEN_GRIPPER,
    pp::State::DETACH_GAZEBO, pp::State::DETACH_MOVEIT, pp::State::SYNC_WORLD_OBJECT,
    pp::State::RETREAT, pp::State::DONE};
  EXPECT_EQ(expected, result.state_trace);
  EXPECT_EQ("MICRO_LIFT", std::string(pp::toString(pp::State::MICRO_LIFT)));
  EXPECT_EQ("VERIFY_PHYSICAL_GRASP",
            std::string(pp::toString(pp::State::VERIFY_PHYSICAL_GRASP)));
  EXPECT_EQ("VALIDATION_FAILED",
            std::string(pp::toString(pp::State::VALIDATION_FAILED)));
}
```

Add assertions that default `single_step` and `force_continue` are false and that `fail_at=ATTACH_MOVEIT` preserves the existing failure code, transition count, recovery trace, and non-zero terminal semantics already asserted by `test_dry_run.cpp`.

- [ ] **Step 4: Register and run the characterization tests**

Add `ament_add_gtest(test_workflow_characterization ...)` to both CMake files and link the existing local `pick_place_core` target.

Run:

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select panda_gazebo_demo so101_gazebo_demo --symlink-install
source install/setup.zsh
colcon test --packages-select panda_gazebo_demo so101_gazebo_demo \
  --ctest-args -R workflow_characterization --output-on-failure
colcon test-result --verbose
```

Expected: both new characterization targets pass on the pre-refactor implementation. If either fails, correct the expected fixture from current source/runtime evidence before moving code; do not change production behavior in this task.

- [ ] **Step 5: Commit the baseline contract**

```bash
git add src/panda_gazebo_demo/test/pick_place/test_workflow_characterization.cpp \
  src/so101_gazebo_demo/test/pick_place/test_workflow_characterization.cpp \
  src/panda_gazebo_demo/CMakeLists.txt src/so101_gazebo_demo/CMakeLists.txt
git diff --cached --check
git commit -m "test: lock Panda and SO-101 workflow behavior"
```

---

### Task 2: Create the shared ROS package and quality-gate export

**Files:**
- Create: `src/pick_place_common/CMakeLists.txt`
- Create: `src/pick_place_common/package.xml`
- Create: `src/pick_place_common/cmake/cpp_quality_gate.cmake`
- Create: `src/pick_place_common/cmake/run_cpp_quality_gate.cmake`
- Create: `src/pick_place_common/cmake/pick_place_common-extras.cmake`
- Create: `src/pick_place_common/test/test_package_contract.py`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`
- Modify: `src/panda_gazebo_demo/package.xml`
- Modify: `src/panda_gazebo_demo/test/scripts/test_cpp_quality_gate.sh`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`
- Modify: `src/so101_gazebo_demo/package.xml`
- Modify: `src/so101_gazebo_demo/test/scripts/test_cpp_quality_gate.sh`

**Interfaces:**
- Consumes: The current byte-identical `run_cpp_quality_gate.cmake` and the stricter union of both current `cpp_quality_gate.cmake` implementations.
- Produces: `find_package(pick_place_common REQUIRED)` and exported `pick_place_common_add_cpp_quality_gate(...)`; no C++ libraries are added until Task 3.

- [ ] **Step 1: Write the package contract test and confirm RED**

Create a pytest that parses `package.xml`/`CMakeLists.txt` and asserts package name, exported extras, and consumer dependency:

```python
from pathlib import Path
import xml.etree.ElementTree as ET


def test_common_package_exports_quality_gate_and_both_consumers_depend_on_it():
    root = Path(__file__).parents[1]
    cmake = (root / "CMakeLists.txt").read_text()
    package = ET.parse(root / "package.xml").getroot()
    assert package.findtext("name") == "pick_place_common"
    assert 'CONFIG_EXTRAS "cmake/pick_place_common-extras.cmake"' in cmake
    for consumer in (root.parent / "panda_gazebo_demo", root.parent / "so101_gazebo_demo"):
        assert "<depend>pick_place_common</depend>" in (consumer / "package.xml").read_text()
        assert "pick_place_common_add_cpp_quality_gate(" in (consumer / "CMakeLists.txt").read_text()
```

Run `python3 -m pytest src/pick_place_common/test/test_package_contract.py -q`.

Expected: FAIL because the package does not exist.

- [ ] **Step 2: Implement the package and exported CMake function**

Use this package skeleton:

```cmake
cmake_minimum_required(VERSION 3.22)
project(pick_place_common)
find_package(ament_cmake REQUIRED)
install(FILES
  cmake/cpp_quality_gate.cmake
  cmake/run_cpp_quality_gate.cmake
  DESTINATION share/${PROJECT_NAME}/cmake)
if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_package_contract test/test_package_contract.py)
endif()
ament_package(CONFIG_EXTRAS "cmake/pick_place_common-extras.cmake")
```

`pick_place_common-extras.cmake` must contain:

```cmake
include("${pick_place_common_DIR}/cpp_quality_gate.cmake")
```

Rename the exported function to `pick_place_common_add_cpp_quality_gate`. Keep arguments `WORKSPACE_ROOT`, `SOURCE_ROOT`, `RUN_CLANG_TIDY_EXECUTABLE`, `CLANG_FORMAT_EXECUTABLE`, `EXCLUDE_FILES`, and `TARGETS`. Preserve finite tool discovery failures and the SO-101 exclusion behavior.

Declare `ament_cmake` as the build tool and add `ament_cmake_gtest`, `ament_cmake_pytest`, and `ament_lint_auto` as test dependencies in `package.xml`. Add `gz_transport_vendor` and `gz_msgs_vendor` only when Task 7 introduces the Gazebo adapter library; the common core must remain free of ROS/Gazebo/MoveIt dependencies.

- [ ] **Step 3: Switch both consumers to the exported function**

Add `find_package(pick_place_common REQUIRED)` and `<depend>pick_place_common</depend>`. Remove local `include(cmake/cpp_quality_gate.cmake)` calls and call `pick_place_common_add_cpp_quality_gate` with the current package-specific target/exclusion lists. Update the shell contract tests to inspect the installed common scripts rather than require local copies.

- [ ] **Step 4: Run GREEN and package build**

```bash
python3 -m pytest src/pick_place_common/test/test_package_contract.py -q
source /opt/ros/jazzy/setup.zsh
colcon build --packages-up-to panda_gazebo_demo so101_gazebo_demo --symlink-install
source install/setup.zsh
colcon test --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo \
  --ctest-args -R 'package_contract|cpp_quality_gate' --output-on-failure
colcon test-result --verbose
```

Expected: common package is discoverable; both quality-gate contract tests pass; no source target has moved yet.

- [ ] **Step 5: Commit the package boundary**

```bash
git add src/pick_place_common src/panda_gazebo_demo/CMakeLists.txt \
  src/panda_gazebo_demo/package.xml src/panda_gazebo_demo/test/scripts/test_cpp_quality_gate.sh \
  src/so101_gazebo_demo/CMakeLists.txt src/so101_gazebo_demo/package.xml \
  src/so101_gazebo_demo/test/scripts/test_cpp_quality_gate.sh
git diff --cached --check
git commit -m "build: add shared pick-place package"
```

---

### Task 3: Implement common domain types, evidence, workflow, and registries

**Files:**
- Create: `src/pick_place_common/include/pick_place_common/domain_types.hpp`
- Create: `src/pick_place_common/include/pick_place_common/world_observer.hpp`
- Create: `src/pick_place_common/include/pick_place_common/workflow_definition.hpp`
- Create: `src/pick_place_common/include/pick_place_common/state_action.hpp`
- Create: `src/pick_place_common/include/pick_place_common/plan_validation.hpp`
- Create: `src/pick_place_common/include/pick_place_common/transition_contract.hpp`
- Create: `src/pick_place_common/include/pick_place_common/recovery_policy.hpp`
- Create: corresponding `.cpp` files under `src/pick_place_common/src/`
- Create: `src/pick_place_common/test/test_workflow_definition.cpp`
- Modify: `src/pick_place_common/CMakeLists.txt`
- Modify: `src/pick_place_common/package.xml`

**Interfaces:**
- Consumes: Union of current Panda/SO-101 state/error/evidence types.
- Produces: `pick_place_common::core`, `State`, `RunRequest`, `RunResult`, `WorldSnapshot`, `WorkflowDefinition`, registries, validators, and recovery interface used by Tasks 4-8.

- [ ] **Step 1: Write failing workflow-definition tests**

Cover valid Panda/SO-like graphs and each construction error:

```cpp
TEST(WorkflowDefinition, RejectsMissingTransitionAndUnknownTarget)
{
  WorkflowDefinition missing;
  missing.initial_state = State::IDLE;
  missing.action_states = {State::PREPARE_OPEN_GRIPPER};
  missing.terminal_states = {State::DONE, State::ERROR};
  EXPECT_EQ("WORKFLOW_TRANSITION_MISSING", validateWorkflowDefinition(missing)->code);

  missing.transitions[State::IDLE] = {State::PREPARE_OPEN_GRIPPER, State::ERROR};
  EXPECT_EQ("WORKFLOW_TRANSITION_TARGET_UNKNOWN", validateWorkflowDefinition(missing)->code);
}
```

Also assert terminal/action overlap rejection, invalid force-continue membership, and a valid definition resolving success/failure edges.

Run the test target after registering it. Expected: compile FAIL because `WorkflowDefinition` is absent.

- [ ] **Step 2: Implement the exact common state vocabulary and request/result model**

Define the union enum in this order to keep deterministic serialization:

```cpp
enum class State {
  IDLE, PREPARE_OPEN_GRIPPER, MOVE_ABOVE_OBJECT, DESCEND, CLOSE_GRIPPER,
  WAIT_GRASP_STABLE, MICRO_LIFT, WAIT_MICRO_LIFT_STABLE,
  VERIFY_PHYSICAL_GRASP, VALIDATION_FAILED,
  ATTACH_GAZEBO, ATTACH_MOVEIT, LIFT, MOVE_ABOVE_PLACE, DESCEND_TO_PLACE,
  OPEN_GRIPPER, DETACH_GAZEBO, DETACH_MOVEIT, SYNC_WORLD_OBJECT, RETREAT,
  RECOVER_LIFT_TO_SAFE_HEIGHT, RECOVER_MOVE_ABOVE_PICK, RECOVER_DESCEND_TO_PICK,
  RECOVER_DETACH_MOVEIT, RECOVER_OPEN_GRIPPER, RECOVER_DETACH_GAZEBO,
  RECOVER_SYNC_WORLD_OBJECT, RECOVER_RETREAT, DONE, ERROR
};
```

Define `RunRequest` with `single_step=false` and `force_continue=false`; define `RunResult` with `std::vector<State> state_trace`. Copy current failure categories and keep all current `toString`/`stateFromString` spellings.

- [ ] **Step 3: Implement the common snapshot as the SO-101 superset**

Use current SO-101 task-object/contact field names. Add Panda's reusable `positionDistance` and `orientationDistance`. Required attachment fields are:

```cpp
std::optional<bool> moveit_task_object_attached;
std::optional<std::string> moveit_task_object_attached_link;
std::set<std::string> moveit_task_object_touch_links;
std::optional<Pose3d> gazebo_task_object_pose_world;
std::optional<bool> gazebo_task_object_attached;
std::optional<bool> gazebo_task_object_stationary;
```

Retain every current SO-101 typed contact sample/vector/depth/height field; Panda will leave them empty.

- [ ] **Step 4: Implement WorkflowDefinition and generic StateMachine**

Use:

```cpp
struct WorkflowDefinition {
  State initial_state{State::IDLE};
  std::map<State, StateTransitions> transitions;
  std::set<State> action_states;
  std::set<State> forward_states;
  std::set<State> terminal_states;
  std::set<State> force_continue_states;
};

class StateMachine {
public:
  StateMachine(const WorkflowDefinition & workflow, State initial);
  State advance(ActionStatus outcome) noexcept;
private:
  const WorkflowDefinition * workflow_;
  State current_state_;
};
```

`validateWorkflowDefinition()` returns `std::optional<Failure>` with category `CONFIGURATION` and the exact codes asserted in Step 1.

- [ ] **Step 5: Move registry and validation interfaces without robot policies**

Move `PlanArtifact`, `PlanResult`, `ExecutionContext`, planner/executor/action registry, `ValidationResult`, plan-validator registry, transition key/contract registry, `AlwaysPassValidator`, `RecoveryRoute`, and `IRecoveryPolicy`. Do not move Panda target validators or SO-101 contact validators.

- [ ] **Step 6: Export and run GREEN**

Build `pick_place_common_core`, set `EXPORT_NAME core`, add alias `pick_place_common::core`, and install/export with `NAMESPACE pick_place_common::`.

```bash
colcon build --packages-select pick_place_common --symlink-install
source install/setup.zsh
colcon test --packages-select pick_place_common --event-handlers console_direct+
colcon test-result --verbose
```

Expected: workflow/type/registry tests pass; Panda/SO consumers still use local implementations.

- [ ] **Step 7: Commit the shared types and workflow**

```bash
git add src/pick_place_common
git diff --cached --check
git commit -m "feat: add shared pick-place workflow types"
```

---

### Task 4: Implement the shared runner and checkpoint/resume orchestration

**Files:**
- Create: `src/pick_place_common/include/pick_place_common/checkpoint.hpp`
- Create: `src/pick_place_common/include/pick_place_common/common_resume_validator.hpp`
- Create: `src/pick_place_common/include/pick_place_common/runner.hpp`
- Create: `src/pick_place_common/include/pick_place_common/simulation_session_id.hpp`
- Create: corresponding `.cpp` files under `src/pick_place_common/src/`
- Create: `src/pick_place_common/test/test_common_runner.cpp`
- Modify: `src/pick_place_common/CMakeLists.txt`

**Interfaces:**
- Consumes: `WorkflowDefinition`, registries, `IWorldObserver`, `IRecoveryPolicy`, and common result/evidence types from Task 3.
- Produces: One implementation of dry-run, plan-only, execute, step, failure recovery, checkpoint commit, resume validation, and state tracing. File JSON stores remain robot-specific.

- [ ] **Step 1: Port runner tests to a definition-driven harness and confirm RED**

Create a compact workflow fixture with `IDLE -> PREPARE_OPEN_GRIPPER -> MOVE_ABOVE_OBJECT -> DONE` and a recovery edge to `RECOVER_RETREAT -> ERROR`. Port the existing SO-101 event harness so this exact order is asserted:

```cpp
const std::vector<std::string> expected{
  "observe", "precondition:MOVE_ABOVE_OBJECT", "plan:MOVE_ABOVE_OBJECT",
  "plan-validate:MOVE_ABOVE_OBJECT", "execute:MOVE_ABOVE_OBJECT", "observe",
  "transition-validate:MOVE_ABOVE_OBJECT", "checkpoint:MOVE_ABOVE_OBJECT"};
EXPECT_EQ(expected, scenario.events);
```

Add tests for dry-run trace, plan-only no execute, single-step checkpoint, resume, force-continue rejection outside declared states, failed action cancel/observe/recovery, missing registrations, and transition-budget exhaustion.

Expected initial result: compile FAIL because common runner/checkpoint APIs do not exist.

- [ ] **Step 2: Implement common checkpoint types**

Use generic fields:

```cpp
struct ExpectedWorldState {
  Pose3d tcp_pose_world{};
  bool gripper_open{false};
  std::map<std::string, double> joint_positions;
  std::map<std::string, Pose3d> moveit_world_object_poses;
  std::optional<bool> moveit_task_object_attached;
  std::optional<Pose3d> gazebo_task_object_pose_world;
  std::optional<bool> gazebo_task_object_attached;
  std::optional<bool> gazebo_task_object_stationary;
  std::vector<std::string> required_world_objects;
};

struct Checkpoint {
  std::uint32_t schema_version{3};
  std::string run_id;
  std::uint64_t sequence{0};
  RunMode source_mode{RunMode::EXECUTE};
  CheckpointPhase phase{CheckpointPhase::FORWARD};
  State last_completed_state{State::IDLE};
  std::optional<State> failed_state;
  std::optional<Failure> original_failure;
  State next_state{State::IDLE};
  ExpectedWorldState expected;
  std::string configuration_fingerprint;
  std::string simulation_session_id;
  bool resumable{true};
};
```

Keep `ICheckpointStore::commit()` and `loadLatestCompatible()` signatures. Do not add JSON dependencies to common core.

- [ ] **Step 3: Implement definition-driven runner construction**

The common runner constructor begins with the workflow:

```cpp
StateMachineRunner(const WorkflowDefinition & workflow,
                   const StateActionRegistry & actions,
                   const TransitionContractRegistry & contracts,
                   IWorldObserver * observer = nullptr,
                   ICheckpointStore * checkpoint_store = nullptr,
                   const CommonResumeValidator * resume_validator = nullptr,
                   IExecutionObservationSink * observation_sink = nullptr,
                   const PlanValidatorRegistry * plan_validators = nullptr,
                   const IRecoveryPolicy * recovery_policy = nullptr,
                   const IRunnerBehaviorPolicy * behavior_policy = nullptr);
```

Merge the Panda observation-sink capability with the SO-101 step/state-trace behavior. All state decisions use `workflow.transitions`, `workflow.action_states`, and `workflow.force_continue_states`; no robot-name or robot-package checks are allowed.

Inject the current robot-specific retry differences through:

```cpp
class IRunnerBehaviorPolicy {
public:
  virtual ~IRunnerBehaviorPolicy() = default;
  virtual bool retryPrecondition(State, const Failure &, std::size_t attempt) const = 0;
  virtual bool retryPostcondition(State, const Failure &, std::size_t attempt) const = 0;
  virtual bool includeIdleInTrace() const noexcept = 0;
};
```

Provide `NoRetryRunnerBehaviorPolicy` in common core. Panda uses it. Task 6 supplies an SO-101 policy containing the current bounded transient precondition/postcondition retry codes and counts from `runner.cpp`; this keeps those rules out of the generic algorithm.

- [ ] **Step 4: Implement common resume validation and session ID resolution**

Define a robot-policy hook rather than forcing SO-101's stricter evidence rules onto Panda:

```cpp
class IResumeValidationPolicy {
public:
  virtual ~IResumeValidationPolicy() = default;
  virtual ValidationResult validateBoundary(const Checkpoint & checkpoint,
                                            const WorldSnapshot & current,
                                            double tolerance) const = 0;
  virtual std::string fingerprintMismatchCode() const = 0;
};
```

`CommonResumeValidator` owns finite/non-negative tolerance validation, schema version, fingerprint equality, simulation-session equality, fresh/stationary observation, result aggregation, and calls `validateBoundary()` for robot rules. Rename the in-memory identity accessor to `configurationFingerprint()`. Task 5 implements Panda's existing joint/completeness rules and codes; Task 6 implements SO-101's resumable/source-mode, physical-validation checkpoint, TCP/gripper/world/attachment/pose/stationary rules and codes. Port `resolveSimulationSessionId` with its current dry-run/execute/resume behavior and deterministic injected timestamp.

Its common constructor is explicit about the robot policy:

```cpp
CommonResumeValidator(std::string configuration_fingerprint,
                      std::string simulation_session_id,
                      std::shared_ptr<const IResumeValidationPolicy> policy,
                      double tolerance = 0.01);
```

The Panda and SO-101 compatibility wrappers keep their current public constructor shapes and instantiate `PandaResumeValidationPolicy` and `SO101ResumeValidationPolicy` respectively.

- [ ] **Step 5: Run common RED/GREEN and regression build**

```bash
colcon build --packages-select pick_place_common --symlink-install
source install/setup.zsh
colcon test --packages-select pick_place_common --event-handlers console_direct+
colcon test-result --verbose
colcon build --packages-select panda_gazebo_demo so101_gazebo_demo --symlink-install
```

Expected: common runner tests pass; consumers still build against local code.

- [ ] **Step 6: Commit the common runner**

```bash
git add src/pick_place_common
git diff --cached --check
git commit -m "feat: add shared pick-place runner"
```

---

### Task 5: Migrate Panda to the common core

**Files:**
- Create: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/panda_workflow.hpp`
- Create: `src/panda_gazebo_demo/src/pick_place/panda_workflow.cpp`
- Replace with forwarding aliases: `domain_types.hpp`, `world_observer.hpp`, `checkpoint.hpp`, `state_action.hpp`, `plan_validation.hpp`, `simulation_session_id.hpp`, `recovery_policy.hpp`, and common parts of `transition_contract.hpp`
- Create: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/panda_resume_validation_policy.hpp`
- Create: `src/panda_gazebo_demo/src/pick_place/panda_resume_validation_policy.cpp`
- Modify: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/common_resume_validator.hpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/common_resume_validator.cpp`
- Modify: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/runner.hpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/runner.cpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/file_checkpoint_store.cpp`
- Modify: all Panda pick-place sources/tests referencing `*_coke_*` snapshot fields
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`

**Interfaces:**
- Consumes: `pick_place_common::core` and existing Panda policy/adapters.
- Produces: `makePandaWorkflowDefinition()` and a thin compatibility `StateMachineRunner` wrapper with the old Panda constructor/run surface.

- [ ] **Step 1: Add a RED dependency test**

Extend `test_workflow_characterization.cpp`:

```cpp
TEST(PandaWorkflowCharacterization, UsesCommonDomainType)
{
  static_assert(std::is_same_v<panda_gazebo_demo::pick_place::State,
                               pick_place_common::State>);
}
```

Expected: compile FAIL before forwarding aliases are installed.

- [ ] **Step 2: Define the Panda workflow explicitly**

`makePandaWorkflowDefinition()` must contain the current Panda transition map verbatim, action states excluding `IDLE/DONE/ERROR`, forward states through `RETREAT`, terminal states `{DONE, ERROR}`, and an empty `force_continue_states` set. Validate once during static initialization and throw `std::logic_error` with the failure code if invalid.

- [ ] **Step 3: Replace local core headers with compatibility forwarders**

For example, `domain_types.hpp` becomes:

```cpp
#pragma once
#include <pick_place_common/domain_types.hpp>
namespace panda_gazebo_demo::pick_place {
using pick_place_common::ActionResult;
using pick_place_common::ActionStatus;
using pick_place_common::Failure;
using pick_place_common::FailureCategory;
using pick_place_common::RunMode;
using pick_place_common::RunRequest;
using pick_place_common::RunResult;
using pick_place_common::RunStatus;
using pick_place_common::State;
using pick_place_common::stateFromString;
using pick_place_common::toString;
}
```

Apply the same alias-only pattern to common interfaces. Keep Panda-specific validator classes in Panda headers and make them derive from common interfaces.

- [ ] **Step 4: Wrap the common runner without duplicating algorithms**

Panda `StateMachineRunner` retains its existing constructor but stores `pick_place_common::StateMachineRunner impl_`; initialize it with `pandaWorkflowDefinition()` and forward `run()` directly. No dry-run/execute/resume method body remains in Panda.

Keep Panda `CommonResumeValidator` as a thin compatibility wrapper around the common validator. `PandaResumeValidationPolicy` must reproduce current `CHECKPOINT_INCOMPATIBLE`, `RECOVERY_CHECKPOINT_CONTEXT_INCOMPLETE`, `RESUME_CONFIGURATION_MISMATCH`, session/quiescence/completeness, and forward joint-position mismatch behavior without adding SO-101's TCP/world/pose requirements.

- [ ] **Step 5: Migrate snapshot/checkpoint names and preserve Panda JSON schema**

Rename in-memory fields from `moveit_coke_attached`/`gazebo_coke_*` to common `moveit_task_object_attached`/`gazebo_task_object_*`. In `file_checkpoint_store.cpp`, keep writing and reading Panda's current JSON keys, including `configuration_hash`; map that key to/from `Checkpoint::configuration_fingerprint`. Add assertions to `test_checkpoint_v3.cpp` that the serialized JSON contains `configuration_hash` and does not contain `configuration_fingerprint`.

- [ ] **Step 6: Change the Panda local target boundary**

Rename local libraries to `panda_pick_place_runtime` and `panda_pick_place_ros_adapters`. Remove common `.cpp` files from their source lists, add `panda_workflow.cpp`, and link `pick_place_common::core`. Update all Panda test links. Keep executable names unchanged.

- [ ] **Step 7: Run Panda focused and package GREEN**

```bash
colcon build --packages-up-to panda_gazebo_demo --symlink-install
source install/setup.zsh
colcon test --packages-select pick_place_common panda_gazebo_demo \
  --event-handlers console_direct+
colcon test-result --verbose
ros2 pkg prefix panda_gazebo_demo
ros2 run panda_gazebo_demo pick_place_state_machine --help
```

Expected: characterization, checkpoint v3, runner, recovery, registration, scene, attachment, quality, and all Panda package tests pass; the executable remains installed under `panda_gazebo_demo`.

- [ ] **Step 8: Commit Panda migration**

```bash
git add src/panda_gazebo_demo src/pick_place_common
git diff --cached --check
git commit -m "refactor: migrate Panda to shared pick-place core"
```

---

### Task 6: Migrate SO-101 to the common core

**Files:**
- Create: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_workflow.hpp`
- Create: `src/so101_gazebo_demo/src/pick_place/so101_workflow.cpp`
- Replace with forwarding aliases: SO-101 equivalents of the common headers migrated in Task 5, excluding the robot-specific resume-validator wrapper
- Create: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_resume_validation_policy.hpp`
- Create: `src/so101_gazebo_demo/src/pick_place/so101_resume_validation_policy.cpp`
- Create: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_runner_behavior_policy.hpp`
- Create: `src/so101_gazebo_demo/src/pick_place/so101_runner_behavior_policy.cpp`
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/runner.hpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/runner.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/file_checkpoint_store.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/pick_place_state_machine.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/pick_place_runtime.cpp`
- Modify: SO-101 pick-place tests and `CMakeLists.txt`

**Interfaces:**
- Consumes: `pick_place_common::core`, the SO-101 profile/policies/adapters, and the common runner extension points.
- Produces: `makeSO101WorkflowDefinition()` and a thin compatibility runner retaining current default constructor, step, force-continue, and state-trace behavior.

- [ ] **Step 1: Add RED type and behavior assertions**

Add the same `std::is_same_v` assertion for SO-101 `State`, plus:

```cpp
const auto & workflow = so101_gazebo_demo::pick_place::so101WorkflowDefinition();
EXPECT_EQ((std::set<pick_place_common::State>{pick_place_common::State::VALIDATION_FAILED}),
          workflow.force_continue_states);
EXPECT_TRUE(workflow.action_states.count(pick_place_common::State::MICRO_LIFT));
EXPECT_TRUE(workflow.action_states.count(pick_place_common::State::VERIFY_PHYSICAL_GRASP));
```

Expected: compile FAIL before the common alias/workflow exists.

- [ ] **Step 2: Define the SO-101 workflow from current source**

Copy the current transition map exactly, including the current default success edge from `WAIT_GRASP_STABLE` and the declared MICRO_LIFT/VERIFY states. Use the current `kActionStates` and planned-state sets from `test_pick_place_runner.cpp` as the coverage source. Declare only `VALIDATION_FAILED` force-continuable.

- [ ] **Step 3: Forward common types and wrap the runner**

Replace common SO-101 headers with alias-only compatibility headers. Keep SO-101 physical validators, motion evidence, profile, runtime assembly, world readiness, reset types, and resume-validator wrapper in the SO namespace. The wrapper default constructor must create empty registries and the SO workflow exactly as the old dry-run constructor did; the injected constructor forwards all dependencies to common runner.

`SO101RunnerBehaviorPolicy` must copy the current bounded retryable precondition/postcondition failure-code sets and maximum attempt counts from the pre-refactor `runner.cpp`. `SO101ResumeValidationPolicy` must copy the current schema/resumable/source-mode, physical-validation checkpoint, TCP/gripper/joint/world/required-object/attachment/Gazebo-pose/stationary rules and keep all existing failure codes and metrics.

- [ ] **Step 4: Preserve SO checkpoint JSON and security behavior**

Map `Checkpoint::configuration_fingerprint` to the existing JSON key `policy_bundle_sha256`. Preserve current symlink/path/temporary-file, permission, null-optionals, plan-only/recovery rejection, attachment-metadata exclusion, and schema checks. Extend `test_checkpoint.cpp` to assert the JSON contains `policy_bundle_sha256` and no `configuration_fingerprint`.

- [ ] **Step 5: Change the SO target boundary**

Rename local `pick_place_core` to `so101_pick_place_runtime`; remove common `.cpp` files from the source list; add `so101_workflow.cpp`; link `pick_place_common::core`; update every SO executable and test target link. Do not move Teleop, generated assets, Gazebo plugin, policy loader, motion, gripper, contact, reset, or scene geometry code.

- [ ] **Step 6: Run SO focused and package GREEN**

```bash
colcon build --packages-up-to so101_gazebo_demo --symlink-install
source install/setup.zsh
colcon test --packages-select pick_place_common so101_gazebo_demo \
  --event-handlers console_direct+
colcon test-result --verbose
ros2 pkg prefix so101_gazebo_demo
ros2 pkg executables so101_gazebo_demo
stat install/so101_gazebo_demo/lib/so101_gazebo_demo/pick_place_state_machine
```

Expected: all SO gtests, Python tests, Teleop tests, configuration/geometry tests, and quality gate pass with no state-trace/failure-code change.

- [ ] **Step 7: Run both consumers together**

```bash
colcon build --packages-up-to panda_gazebo_demo so101_gazebo_demo --symlink-install
source install/setup.zsh
colcon test --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo \
  --event-handlers console_direct+
colcon test-result --verbose
```

Expected: no duplicate exported target/library collision; all three packages pass in one overlay.

- [ ] **Step 8: Commit SO-101 migration**

```bash
git add src/so101_gazebo_demo src/pick_place_common
git diff --cached --check
git commit -m "refactor: migrate SO-101 to shared pick-place core"
```

---

### Task 7: Extract the Gazebo attachment executor

**Files:**
- Create: `src/pick_place_common/include/pick_place_common/gazebo_attachment_executor.hpp`
- Create: `src/pick_place_common/src/gazebo_attachment_executor.cpp`
- Create: `src/pick_place_common/test/test_gazebo_attachment_executor.cpp`
- Modify: `src/pick_place_common/CMakeLists.txt`, `package.xml`
- Replace with forwarding aliases: both robot `gazebo_attachment_executor.hpp`
- Remove from build: both robot `gazebo_attachment_executor.cpp`
- Modify: Panda runtime registration to inject Panda convergence policy
- Modify: SO-101 runtime registration to use default convergence policy
- Modify: both robot attachment tests/CMake links

**Interfaces:**
- Consumes: Common `ExecutionContext`, `State`, `ActionResult`, Gazebo topic transport, and robot-specific convergence policy.
- Produces: One command/poll/timeout/cancel/idempotency implementation in `pick_place_common::ros_adapters`.

- [ ] **Step 1: Write common RED tests**

Move transport-level assertions into the common test: attach publishes once and waits for `attached`; detach waits for `detached`; opposite state times out with `GAZEBO_ATTACHMENT_TIMEOUT`; wrong state returns `STATE_NOT_EXECUTABLE`; cancellation returns `GAZEBO_ATTACHMENT_CANCELLED`; idempotent recovery skips the command only when the policy approves.

Expected: compile FAIL because the common executor/target does not exist.

- [ ] **Step 2: Define configuration and convergence policy**

```cpp
struct GazeboAttachmentConfig {
  State allowed_state;
  bool desired_attached;
  std::string attach_topic;
  std::string detach_topic;
  std::string state_topic;
  double timeout_seconds;
  double poll_interval_seconds;
  bool idempotent{false};
};

class IAttachmentConvergencePolicy {
public:
  virtual ~IAttachmentConvergencePolicy() = default;
  virtual bool canTreatAsConverged(const ExecutionContext & context,
                                   bool desired_attached) const = 0;
};
```

Provide a default policy that requires a fresh optional Gazebo attachment fact equal to the desired value. Panda supplies a policy that also applies its existing gripper-open boundary before skipping recovery detach; SO uses the default.

- [ ] **Step 3: Move the transport algorithm**

Use the stricter union of current checks: finite positive timing, wrong-state rejection, null/missing policy rejection only when idempotency is enabled, one command publication, durable-state polling, cancellation through condition variable, and unchanged failure codes/metrics.

- [ ] **Step 4: Export `pick_place_common::ros_adapters` and switch consumers**

Create target `pick_place_common_ros_adapters`, set `EXPORT_NAME ros_adapters`, link `pick_place_common::core`, `gz-msgs10::core`, and `gz-transport13::core`; export alias `pick_place_common::ros_adapters`. Replace local headers with aliases, remove local sources from CMake, and link consumer runtime/tests to the common target.

- [ ] **Step 5: Run GREEN**

```bash
colcon build --packages-up-to panda_gazebo_demo so101_gazebo_demo --symlink-install
source install/setup.zsh
colcon test --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo \
  --ctest-args -R 'gazebo_attachment|workflow_characterization' --output-on-failure
colcon test-result --verbose
```

Expected: common transport tests pass; Panda strict-gripper no-op test and SO durable-state tests preserve their current command counts and failure codes.

- [ ] **Step 6: Commit attachment extraction**

```bash
git add src/pick_place_common src/panda_gazebo_demo src/so101_gazebo_demo
git diff --cached --check
git commit -m "refactor: share Gazebo attachment executor"
```

---

### Task 8: Extract the MoveIt scene executor without merging geometry

**Files:**
- Create: `src/pick_place_common/include/pick_place_common/moveit_scene_executor.hpp`
- Create: `src/pick_place_common/src/moveit_scene_executor.cpp`
- Create: `src/pick_place_common/test/test_moveit_scene_executor.cpp`
- Modify: `src/pick_place_common/CMakeLists.txt`
- Modify: both robot `moveit_scene_adapter.hpp/.cpp`
- Replace with forwarding aliases: both robot `moveit_scene_executor.hpp`
- Remove from build: both robot `moveit_scene_executor.cpp`
- Create: `panda_moveit_scene_policy.hpp/.cpp` in Panda package
- Create: `so101_moveit_scene_policy.hpp/.cpp` in SO package
- Modify: both runtime registration and scene tests/CMake links

**Interfaces:**
- Consumes: Generic task-object scene adapter, operation policy, attachment metadata, and common snapshot.
- Produces: One validation/cancel/poll/timeout/convergence executor while preserving Panda versus SO command preparation and failure codes.

- [ ] **Step 1: Write common RED tests**

The common fake adapter must assert ordered `upsert`/`attach`, exclusive world/attached membership, exact ordered touch links, detach return to world, sync pose convergence, timeout observation count, cancel, and idempotent skip controlled by policy.

- [ ] **Step 2: Define the generic scene boundary**

```cpp
enum class MoveItSceneOperation { ATTACH, DETACH, SYNC };

struct MoveItAttachmentSpec {
  std::string link_name;
  std::vector<std::string> touch_links;
};

struct MoveItSceneState {
  bool task_object_in_world{false};
  bool task_object_attached{false};
  std::string attached_link;
  std::vector<std::string> touch_links;
  std::optional<Pose3d> task_object_world_pose;
};

class IMoveItSceneAdapter {
public:
  virtual ~IMoveItSceneAdapter() = default;
  virtual ActionResult attachTaskObject(const MoveItAttachmentSpec &) = 0;
  virtual ActionResult detachTaskObject() = 0;
  virtual ActionResult upsertTaskObjectWorldPose(const Pose3d &) = 0;
  virtual std::optional<MoveItSceneState> observe() = 0;
};
```

Table/pedestal upsert and collision-object factories remain separate robot-specific interfaces/classes.

- [ ] **Step 3: Define robot-specific operation policy**

```cpp
struct ScenePreparation {
  bool skip_command{false};
  bool upsert_before_attach{false};
  std::optional<Pose3d> task_object_pose;
  std::optional<ActionResult> failure;
};

class IMoveItScenePolicy {
public:
  virtual ~IMoveItScenePolicy() = default;
  virtual ScenePreparation prepare(MoveItSceneOperation,
                                   const ExecutionContext &) const = 0;
};
```

Panda policy preserves `GAZEBO_COKE_POSE_MISSING`, Panda gripper/open/world-object idempotency gates, and attach-without-pre-upsert behavior. SO policy preserves `GAZEBO_TASK_OBJECT_POSE_MISSING`, settled-pose upsert before attach, generic task-object fields, and current detach/sync idempotency.

- [ ] **Step 4: Implement the common executor**

`MoveItSceneConfig` contains state, operation, idempotent flag, task-object ID, attachment spec, timeout, and poll interval. Executor validates state/timing/adapter/policy, applies `ScenePreparation`, issues the command sequence, and polls `MoveItSceneState`. It preserves `STATE_NOT_EXECUTABLE`, `MOVEIT_SCENE_ADAPTER_MISSING`, `MOVEIT_SCENE_TIMING_INVALID`, `MOVEIT_SCENE_CANCELLED`, and `MOVEIT_SCENE_CONVERGENCE_TIMEOUT`.

- [ ] **Step 5: Adapt concrete scene adapters without moving geometry**

Rename Panda Coke methods/fields internally to task-object equivalents while keeping object ID `coke`. SO already uses task-object naming; keep `MoveItSceneGeometry`, collision-object factories, table/pedestal operations, and initializer in SO. Robot policies own the differing preparation semantics.

- [ ] **Step 6: Run GREEN**

```bash
colcon build --packages-up-to panda_gazebo_demo so101_gazebo_demo --symlink-install
source install/setup.zsh
colcon test --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo \
  --ctest-args -R 'moveit_scene|workflow_characterization|checkpoint' --output-on-failure
colcon test-result --verbose
```

Expected: Panda exact hand/touch-link and gripper-idempotency tests pass; SO settled-pose upsert, ordered touch-link, geometry, initializer, and missing-pose tests pass.

- [ ] **Step 7: Commit scene extraction**

```bash
git add src/pick_place_common src/panda_gazebo_demo src/so101_gazebo_demo
git diff --cached --check
git commit -m "refactor: share MoveIt scene executor"
```

---

### Task 9: Remove duplicate implementations and close automated gates

**Files:**
- Delete algorithm-bearing local files superseded by common core/adapters
- Keep alias-only compatibility headers under both robot include paths
- Modify: all three `CMakeLists.txt` and `package.xml`
- Modify: `src/panda_gazebo_demo/README.md`
- Modify: `src/so101_gazebo_demo/README.md`
- Modify: repository architecture documentation that describes local `pick_place_core`
- Create: `src/pick_place_common/README.md`

**Interfaces:**
- Consumes: All migrated targets and compatibility headers from Tasks 2-8.
- Produces: One implementation source for the approved common components, documented ownership, and a clean three-package build/test result.

- [ ] **Step 1: Add static ownership checks**

Extend `test_package_contract.py` to assert:

```python
for consumer in (panda, so101):
    cmake = (consumer / "CMakeLists.txt").read_text()
    assert "src/pick_place/runner.cpp" not in cmake
    assert "src/pick_place/domain_types.cpp" not in cmake
    assert "src/pick_place/state_action.cpp" not in cmake
    assert "src/pick_place/gazebo_attachment_executor.cpp" not in cmake
    assert "src/pick_place/moveit_scene_executor.cpp" not in cmake
assert "pick_place_common::core" in panda_cmake and "pick_place_common::core" in so101_cmake
assert "pick_place_common::ros_adapters" in panda_cmake
assert "pick_place_common::ros_adapters" in so101_cmake
```

Expected before cleanup: FAIL on remaining compiled duplicates.

- [ ] **Step 2: Remove only superseded algorithms**

Delete local `.cpp` files no longer compiled and remove obsolete local quality-gate copies. Keep robot workflow definitions, runner wrappers, file checkpoint stores/codecs, concrete observers, scene adapters/geometry, and all robot policies. Confirm forwarding headers contain only includes, aliases, and thin wrappers.

- [ ] **Step 3: Update documentation**

Document dependency direction, exported targets, common ownership, robot-specific ownership, checkpoint codec split, build/test commands, and the rule that new robot packages implement a `WorkflowDefinition` plus policies rather than copy the runner.

- [ ] **Step 4: Run the full automated gate**

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-up-to panda_gazebo_demo so101_gazebo_demo \
  --symlink-install --cmake-clean-cache
source install/setup.zsh
PYTHONNOUSERSITE=1 colcon test \
  --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo \
  --event-handlers console_direct+
colcon test-result --verbose
git diff --check
git status --short
```

Expected: all three packages pass; no unexpected generated files are staged; no `ament_uncrustify --reformat` output is present.

- [ ] **Step 5: Commit cleanup and docs**

```bash
git add src/pick_place_common src/panda_gazebo_demo src/so101_gazebo_demo docs
git diff --cached --check
git commit -m "docs: finalize shared pick-place architecture"
```

---

### Task 10: Perform ai-station runtime, recovery, and visual acceptance

**Files:**
- Create outside source tree: `/tmp/so101-debug-<timestamp>/` evidence directory
- Modify source only if a new regression is proven with RED/A-B evidence; any fix becomes a separate scoped commit and repeats the affected automated gate

**Interfaces:**
- Consumes: The final branch build and installed overlay from Tasks 1-9.
- Produces: Provenance, runtime, Gazebo, MoveIt, controller/joint/TF, checkpoint/recovery, and fresh visual evidence for both consumers.

- [ ] **Step 1: Prove installed provenance and no duplicate stack**

```bash
source ~/gui-env.zsh
source /opt/ros/jazzy/setup.zsh
cd /data/work/ws_moveit-pick-place-common
source install/setup.zsh
ros2 pkg prefix pick_place_common
ros2 pkg prefix panda_gazebo_demo
ros2 pkg prefix so101_gazebo_demo
ros2 pkg executables panda_gazebo_demo
ros2 pkg executables so101_gazebo_demo
pgrep -af 'gz sim|move_group|rviz2|pick_place_state_machine|so101_teleop' || true
ros2 node list | sort
```

Expected: prefixes point to this worktree's install; only the deliberately owned runtime stack exists.

- [ ] **Step 2: Run dry-run and plan-only matrices**

First inspect current arguments:

```bash
ros2 launch so101_gazebo_demo so101_pick_place.launch.py --show-args
```

Run both package dry-run normal/fail-at cases and plan-only for every registered planned state using the existing package scripts/tests. Save command, output, exit code, state trace, unique `simulation_session_id`, and checkpoint path. Expected: before/after characterization traces and failure codes match; plan-only changes no joints/TCP/Gazebo pose.

- [ ] **Step 3: Run recovery/resume evidence**

Exercise stale/incompatible checkpoint rejection and the existing Gazebo-only, MoveIt-only, and both-attached recovery scenarios. Expected: recovery undoes only observed side effects, returns non-zero for the injected failure path, and ends with Gazebo/MoveIt detached and task-object world pose synchronized.

- [ ] **Step 4: Run Panda simulation execute acceptance**

Run the current owned headless entry:

```bash
src/panda_gazebo_demo/test/headless/run_pick_place_e2e.sh \
  --runs 1 --label common-refactor
src/panda_gazebo_demo/test/headless/run_recovery_scenarios.sh
src/panda_gazebo_demo/test/headless/run_plan_only_resume_matrix.sh
```

Record MoveIt plan/error codes, controller results, `/joint_states` and TCP before/after, Gazebo Coke attachment/pose, Planning Scene membership, process exit code, and fresh RViz/Gazebo screenshot.

Expected: current Panda baseline behavior is preserved; a plan success without joint/TCP/Gazebo changes is a failure.

- [ ] **Step 5: Run SO-101 staged and repeated execute acceptance**

Use the current CLI contract. Allocate one evidence directory, reset before every independent run, and first run staged boundaries with distinct checkpoint/session IDs:

```bash
debug_dir="/tmp/so101-common-refactor-$(date +%Y%m%d-%H%M%S)"
mkdir -p "${debug_dir}"
ros2 run so101_gazebo_demo reset_so101_world \
  >"${debug_dir}/attach_reset.log" 2>&1
ros2 run so101_gazebo_demo pick_place_state_machine --mode execute \
  --stop-after ATTACH_GAZEBO \
  --checkpoint "${debug_dir}/attach-checkpoint.json" \
  --session-id "common-refactor-attach-$(date +%s%N)" \
  >"${debug_dir}/attach.log" 2>&1
ros2 run so101_gazebo_demo reset_so101_world \
  >"${debug_dir}/moveit_reset.log" 2>&1
ros2 run so101_gazebo_demo pick_place_state_machine --mode execute \
  --stop-after ATTACH_MOVEIT \
  --checkpoint "${debug_dir}/moveit-checkpoint.json" \
  --session-id "common-refactor-moveit-$(date +%s%N)" \
  >"${debug_dir}/moveit.log" 2>&1
```

Then run three canonical complete simulations, each with a reset, unique `--checkpoint` and `--session-id`, and no `--stop-after`:

```bash
for run in 1 2 3; do
  ros2 run so101_gazebo_demo reset_so101_world \
    >"${debug_dir}/run_${run}_reset.log" 2>&1
  session_id="common-refactor-${run}-$(date +%s%N)"
  timeout 300 ros2 run so101_gazebo_demo pick_place_state_machine \
    --mode execute \
    --checkpoint "${debug_dir}/run_${run}_checkpoint.json" \
    --session-id "${session_id}" \
    >"${debug_dir}/run_${run}.log" 2>&1
done
```

For each run record:

```text
state trace and exit code
arm/gripper action result
joint/TCP before-after delta
Gazebo task-object attached state and 6D final pose
MoveIt world/attached membership, link, touch links, collision state
contact/penetration/settling evidence at affected grasp boundaries
```

Expected: three runs reach `DONE`; release/detach/sync/retreat are present; final Gazebo and MoveIt attachment states are false; final facts remain within the current committed validation policies.

- [ ] **Step 6: Capture and inspect fresh visual evidence**

In the tmux-held GUI shell:

```bash
ros2 run so101_gazebo_demo tile_ai_station_guis.py
```

Require `LAYOUT_OK`, then from the local root run `./scripts/capture-ai-station.sh`. Open the new desktop/RViz/Gazebo images and describe the arm pose, gripper opening, task-object start/end pose, penetration/drop status, and Planning Scene consistency. CUA actions must use `snapshot -> action -> fresh snapshot`.

- [ ] **Step 7: Produce the final evidence report**

Report exact commits and fill every field:

```text
Baseline and final provenance:
Preserved user changes:
Automated RED/GREEN commands and results:
Panda runtime command and exit code:
SO-101 three run results:
Gazebo proof:
MoveIt proof:
Controller/joint/TF proof:
Checkpoint/recovery proof:
Visual proof and screenshot paths:
Remaining risks and next exact command:
```

Do not mark complete if any field is blank or if source/install/runtime provenance is unresolved.

## Plan Self-Review Checklist

- Every design requirement maps to Tasks 2-10: common package, workflow/core, checkpoint compatibility, Panda/SO migration, selected executors, cleanup, and layered acceptance.
- The only shared state type is `pick_place_common::State`; robot include compatibility is alias-only.
- The only common checkpoint identity name is `configuration_fingerprint`; Panda and SO disk codecs preserve `configuration_hash` and `policy_bundle_sha256` respectively.
- `pick_place_common::core` contains no Gazebo/MoveIt transport dependency; `pick_place_common::ros_adapters` owns those dependencies.
- Full observers, concrete scene geometry, file checkpoint stores, motion, gripper, contact, reset, recovery policies, and Teleop remain robot-specific.
- No task authorizes push, main merge, root submodule update, real-hardware motion, broad process killing, worktree cleanup, or automatic reformatting.
