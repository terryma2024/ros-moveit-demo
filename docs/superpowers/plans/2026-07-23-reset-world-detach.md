# Reset World Detach Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the reset utility to `reset_world.sh` and make success prove that Gazebo and MoveIt both hold a detached Coke at the canonical reset pose before returning the arm and gripper to their initial configuration.

**Architecture:** A testable `MoveItWorldResetter` coordinates MoveIt detach and world-object upsert through `IMoveItSceneAdapter`; a small ROS executable supplies the real adapter. The shell script owns Gazebo detach/reset ordering and invokes the helper before any arm motion. Existing headless harnesses independently verify both worlds after reset.

**Tech Stack:** C++17, ROS 2 Jazzy, MoveIt 2 PlanningSceneInterface/MoveGroupInterface, Gazebo Sim transport CLI, Bash, GoogleTest, CMake/ament.

## Global Constraints

- Canonical Coke pose is position `(0.3, 0.0, 0.836)` and quaternion `(0, 0, 0, 1)` in `world`.
- Gazebo detach must be confirmed before Coke pose reset or arm/gripper motion.
- MoveIt must contain no attached Coke and exactly one world Coke at the canonical pose before arm motion.
- `EXPECTED_COKE_DETACHED=true` may skip one initial observation but never skips the detach command, MoveIt reset, or final Gazebo validation.
- Any failure exits nonzero; a paused Gazebo world is resumed by the existing trap.
- Do not keep `reset_coke.sh` as a compatibility alias.
- Do not use `ament_uncrustify --reformat`; run only its read-only CTest check.
- Do not push.

---

### Task 1: Add a testable MoveIt world reset coordinator

**Files:**
- Create: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/moveit_world_resetter.hpp`
- Create: `src/panda_gazebo_demo/src/pick_place/moveit_world_resetter.cpp`
- Create: `src/panda_gazebo_demo/test/pick_place/test_moveit_world_resetter.cpp`
- Modify: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/moveit_scene_adapter.hpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/moveit_scene_adapter.cpp`
- Modify: `src/panda_gazebo_demo/test/pick_place/test_moveit_scene_executor.cpp`
- Modify: `src/panda_gazebo_demo/test/pick_place/test_registration_coverage.cpp`
- Modify: `src/panda_gazebo_demo/test/pick_place/test_recovery_workflow.cpp`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`

**Interfaces:**
- Consumes: `IMoveItSceneAdapter::observe()`, `detachCoke()`, `Pose3d`, `ActionResult`.
- Produces: `IMoveItSceneAdapter::upsertCokeWorldPose(const Pose3d &)`, and `MoveItWorldResetter::reset(const Pose3d &) -> ActionResult`.

- [x] **Step 1: Write failing coordinator tests**

Add a fake adapter and tests that require detach-before-upsert, already-detached idempotence,
missing-object creation, detach command failure, observation timeout, and final 6DoF convergence:

```cpp
TEST(MoveItWorldResetter, DetachesThenUpsertsCanonicalWorldPose)
{
  auto adapter = std::make_shared<FakeMoveItSceneAdapter>();
  adapter->observations = {attachedState(), detachedState(), detachedState(kResetPose)};
  MoveItWorldResetter resetter(adapter, 0.05, 0.001);

  const auto result = resetter.reset(kResetPose);

  EXPECT_EQ(ActionStatus::SUCCEEDED, result.status);
  EXPECT_EQ(1, adapter->detach_calls);
  EXPECT_EQ(1, adapter->upsert_calls);
  EXPECT_EQ((std::vector<std::string>{"detach", "upsert"}), adapter->commands);
}

TEST(MoveItWorldResetter, RejectsNonConvergentScene)
{
  auto adapter = std::make_shared<FakeMoveItSceneAdapter>();
  adapter->observations = {attachedState()};
  MoveItWorldResetter resetter(adapter, 0.01, 0.001);

  const auto result = resetter.reset(kResetPose);

  EXPECT_EQ(ActionStatus::TIMED_OUT, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("MOVEIT_RESET_DETACH_TIMEOUT", result.failure->code);
}
```

- [x] **Step 2: Run RED**

Run:

```bash
colcon build --packages-select panda_gazebo_demo --symlink-install \
  --cmake-args -DBUILD_TESTING=ON
```

Expected: compilation fails because `MoveItWorldResetter` and `upsertCokeWorldPose` do not exist.

- [x] **Step 3: Implement the coordinator and adapter upsert**

Define the interface and coordinator:

```cpp
class MoveItWorldResetter
{
public:
  MoveItWorldResetter(
    std::shared_ptr<IMoveItSceneAdapter> adapter,
    double timeout_seconds = 2.0, double poll_interval_seconds = 0.05);
  [[nodiscard]] ActionResult reset(const Pose3d & target_pose);
};
```

`reset()` must observe first, detach only if attached, poll until detached, call
`upsertCokeWorldPose(target_pose)`, then poll until Coke is detached, present in the world, and
within `1e-5 m / 1e-4 rad`. Missing/non-finite observations and invalid timing fail closed.

Implement `MoveItSceneAdapter::upsertCokeWorldPose()` so an existing world Coke preserves its
geometry and a missing Coke is created as a `CYLINDER` with height `0.122` and radius `0.033`.
It rejects upsert while attached and requires `applyCollisionObject()` success.

- [x] **Step 4: Run GREEN**

Run:

```bash
colcon build --packages-select panda_gazebo_demo --symlink-install \
  --cmake-args -DBUILD_TESTING=ON
ctest --test-dir build/panda_gazebo_demo \
  -R '^(test_moveit_world_resetter|test_moveit_scene_executor|test_registration_coverage|test_recovery_workflow)$' \
  --output-on-failure
```

Expected: all selected tests pass.

- [x] **Step 5: Commit**

```bash
git add src/panda_gazebo_demo/CMakeLists.txt \
  src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/moveit_scene_adapter.hpp \
  src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/moveit_world_resetter.hpp \
  src/panda_gazebo_demo/src/pick_place/moveit_scene_adapter.cpp \
  src/panda_gazebo_demo/src/pick_place/moveit_world_resetter.cpp \
  src/panda_gazebo_demo/test/pick_place
git commit -m "feat: add MoveIt world reset coordinator"
```

---

### Task 2: Add the MoveIt reset executable

**Files:**
- Create: `src/panda_gazebo_demo/src/nodes/reset_moveit_world.cpp`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`
- Create: `src/panda_gazebo_demo/test/scripts/test_reset_moveit_world_cli.sh`

**Interfaces:**
- Consumes: `MoveItSceneAdapter(node, planning_group, object_id)` and `MoveItWorldResetter::reset()`.
- Produces: installed executable `ros2 run panda_gazebo_demo reset_moveit_world` with parameters `planning_group`, `object_id`, `timeout_seconds`, and `poll_interval_seconds`.

- [x] **Step 1: Write a failing installed-interface test**

Add a CTest shell check that receives `$<TARGET_FILE:reset_moveit_world>`, requires an executable,
and invokes the node's side-effect-free `--help` path:

```bash
[[ -x "${executable}" ]] || fail 'reset_moveit_world is not executable'
"${executable}" --help >"${output}" 2>&1
grep -Fq 'reset_moveit_world [--ros-args ...]' "${output}" ||
  fail 'reset_moveit_world usage was not produced'
```

- [x] **Step 2: Run RED**

Run:

```bash
cmake --build build/panda_gazebo_demo --target reset_moveit_world
```

Expected: fails with `No rule to make target 'reset_moveit_world'`.

- [x] **Step 3: Implement the node and CMake target**

The node handles plain `--help` before initializing ROS. Otherwise it constructs the real adapter,
resolves the fixed pose, calls `reset()`, logs the failure code/message on error, and returns
`EXIT_FAILURE`; it returns success only after coordinator convergence:

```cpp
const Pose3d target{0.3, 0.0, 0.836, 0.0, 0.0, 0.0, 1.0};
auto adapter = std::make_shared<MoveItSceneAdapter>(node, planning_group, object_id);
MoveItWorldResetter resetter(adapter, timeout_seconds, poll_interval_seconds);
const auto result = resetter.reset(target);
return result.status == ActionStatus::SUCCEEDED ? EXIT_SUCCESS : EXIT_FAILURE;
```

Link the target with `pick_place_core`, `pick_place_ros_adapters`, and `rclcpp`, install it with the
other executables, and register `test_reset_moveit_world_cli`.

- [x] **Step 4: Run GREEN**

Run:

```bash
colcon build --packages-select panda_gazebo_demo --symlink-install \
  --cmake-args -DBUILD_TESTING=ON
ctest --test-dir build/panda_gazebo_demo \
  -R '^test_reset_moveit_world_cli$' --output-on-failure
```

Expected: build and CLI test pass.

- [x] **Step 5: Commit**

```bash
git add src/panda_gazebo_demo/CMakeLists.txt \
  src/panda_gazebo_demo/src/nodes/reset_moveit_world.cpp \
  src/panda_gazebo_demo/test/scripts/test_reset_moveit_world_cli.sh
git commit -m "feat: add MoveIt world reset command"
```

---

### Task 3: Rename and make the shell reset force both worlds detached

**Files:**
- Create: `src/panda_gazebo_demo/scripts/reset_world.sh`
- Create: `src/panda_gazebo_demo/test/scripts/test_reset_world.sh`
- Delete: `src/panda_gazebo_demo/scripts/reset_coke.sh`
- Delete: `src/panda_gazebo_demo/test/scripts/test_reset_coke.sh`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`

**Interfaces:**
- Consumes: Gazebo `/panda/detach_coke`, durable `/panda/coke_attached`, Gazebo control/set-pose services, ROS arm/gripper actions, and `ros2 run panda_gazebo_demo reset_moveit_world`.
- Produces: installed script `reset_world.sh` and CTest `test_reset_world`.

- [x] **Step 1: Write the failing shell behavior test**

The fake `gz` command stores attachment state in a file. Publishing detach changes it to detached
unless `FAKE_DETACH_CONVERGES=false`. The fake `ros2` command supports the MoveIt helper and returns
`FAKE_MOVEIT_RESET_STATUS`.

Assertions must include:

```bash
run_reset attached >/dev/null
grep -Fq 'gz topic -t /panda/detach_coke' "${command_log}"
detach_line="$(grep -n 'gz topic -t /panda/detach_coke' "${command_log}" | cut -d: -f1)"
pose_line="$(grep -n 'gz service -s /world/pick_place_world/set_pose' "${command_log}" | cut -d: -f1)"
moveit_line="$(grep -n 'ros2 run panda_gazebo_demo reset_moveit_world' "${command_log}" | cut -d: -f1)"
open_line="$(grep -n 'position: 0.04' "${command_log}" | head -1 | cut -d: -f1)"
[[ detach_line -lt pose_line && pose_line -lt moveit_line && moveit_line -lt open_line ]]
```

Add negative cases proving detach non-convergence and MoveIt reset failure produce nonzero status
and no arm/gripper goals.

- [x] **Step 2: Run RED**

Run:

```bash
bash src/panda_gazebo_demo/test/scripts/test_reset_world.sh \
  src/panda_gazebo_demo/scripts/reset_coke.sh
```

Expected: fails because the old script rejects attached Coke and never invokes the MoveIt helper.

- [x] **Step 3: Implement `reset_world.sh` and migrate CTest**

Use this required orchestration order:

```bash
request_gazebo_detach
if [[ "${EXPECTED_COKE_DETACHED}" != true ]]; then
  require_detached_coke
fi
call_service "${CONTROL_SERVICE}" gz.msgs.WorldControl 'pause: true'
paused=true
canonical_pose_request='name: "coke", position: {x: 0.3, y: 0.0, z: 0.836}, orientation: {x: 0.0, y: 0.0, z: 0.0, w: 1.0}'
call_service "${SET_POSE_SERVICE}" gz.msgs.Pose "${canonical_pose_request}"
ros2 run panda_gazebo_demo reset_moveit_world
call_service "${CONTROL_SERVICE}" gz.msgs.WorldControl 'pause: false'
paused=false
require_detached_coke
command_gripper "${GRIPPER_OPEN_POSITION}" Opening
move_arm_to_ready
command_gripper "${GRIPPER_CLOSED_POSITION}" Closing
```

Delete both old filenames. Rename the CTest and pass the new script path.

- [x] **Step 4: Run GREEN**

Run:

```bash
bash src/panda_gazebo_demo/test/scripts/test_reset_world.sh \
  src/panda_gazebo_demo/scripts/reset_world.sh
colcon build --packages-select panda_gazebo_demo --symlink-install \
  --cmake-args -DBUILD_TESTING=ON
ctest --test-dir build/panda_gazebo_demo -R '^test_reset_world$' --output-on-failure
```

Expected: shell fixture and CTest pass.

- [x] **Step 5: Commit**

```bash
git add -A src/panda_gazebo_demo/scripts src/panda_gazebo_demo/test/scripts \
  src/panda_gazebo_demo/CMakeLists.txt
git commit -m "feat: reset Gazebo and MoveIt worlds together"
```

---

### Task 4: Migrate callers and verify the real reset

**Files:**
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`
- Modify: `src/panda_gazebo_demo/scripts/reset_world.sh`
- Modify: `src/panda_gazebo_demo/test/scripts/test_reset_world.sh`
- Create: `src/panda_gazebo_demo/test/headless/assert_reset_moveit_scene.py`
- Create: `src/panda_gazebo_demo/test/headless/test_assert_reset_moveit_scene.sh`
- Modify: `src/panda_gazebo_demo/test/headless/run_pick_place_e2e.sh`
- Modify: `src/panda_gazebo_demo/test/headless/run_plan_only_resume_matrix.sh`
- Modify: `src/panda_gazebo_demo/test/headless/run_recovery_scenarios.sh`
- Modify: `src/panda_gazebo_demo/README.md`
- Modify: `docs/superpowers/plans/2026-07-23-complete-pick-place-state-machine.md`
- Modify: `docs/superpowers/specs/2026-07-23-complete-pick-place-state-machine-design.md`

**Interfaces:**
- Consumes: `reset_world.sh` and independent Gazebo/MoveIt snapshot validators.
- Produces: no active caller of `reset_coke.sh`, and retained real headless reset evidence.

- [x] **Step 1: Add a failing migration assertion**

Before replacing callers, run:

```bash
if rg -n 'reset_coke\.sh' src/panda_gazebo_demo/CMakeLists.txt \
    src/panda_gazebo_demo/README.md src/panda_gazebo_demo/test/headless; then
  exit 1
fi
```

Expected: fails and prints every remaining active caller.

- [x] **Step 2: Replace active references and update semantics documentation**

All harnesses call `${package_root}/scripts/reset_world.sh`. README and complete-state-machine
documents state that reset actively detaches Gazebo, detaches MoveIt, synchronizes the canonical
pose, then returns the arm/gripper to their initial state. Historical reset design/plan documents
remain unchanged as historical records.

Code review additionally requires all ROS/Gazebo interfaces to be preflighted before mutations,
Gazebo Coke 6DoF convergence to gate robot motion, and an independent Planning Scene assertion
immediately after `reset_world.sh` and before `planning_scene_setup`.

- [x] **Step 3: Run targeted static and package verification**

Run:

```bash
rg -n 'reset_coke\.sh' src/panda_gazebo_demo/CMakeLists.txt \
  src/panda_gazebo_demo/README.md src/panda_gazebo_demo/test/headless && exit 1 || true
bash -n src/panda_gazebo_demo/scripts/reset_world.sh
find src/panda_gazebo_demo/test/headless src/panda_gazebo_demo/test/scripts \
  -type f -name '*.sh' -print0 | xargs -0 -n1 bash -n
colcon build --packages-select panda_gazebo_demo --symlink-install \
  --cmake-args -DBUILD_TESTING=ON
colcon test --packages-select panda_gazebo_demo --event-handlers console_direct+
AMENT_CPPCHECK_ALLOW_SLOW_VERSIONS=1 colcon test \
  --packages-select panda_gazebo_demo --ctest-args -R '^cppcheck$'
colcon test-result --test-result-base build/panda_gazebo_demo/test_results --verbose
```

Expected: all tests pass with zero failures; read-only uncrustify and explicit cppcheck pass.

- [x] **Step 4: Run one real headless reset and inspect independent facts**

Launch headless Gazebo/MoveIt, establish an attached Coke, then run `reset_world.sh`. Capture:

```bash
gz model -m coke -p
timeout 3 gz topic -e -t /panda/coke_attached -n 1
timeout 3 ros2 topic echo /joint_states --once
timeout 5 ros2 service call /get_planning_scene \
  moveit_msgs/srv/GetPlanningScene '{components: {components: 28}}'
```

Expected: Gazebo detached, no MoveIt attached Coke, one MoveIt world Coke at the canonical 6DoF
pose, closed/stationary fingers, ready arm, and cross-world consistency.

- [x] **Step 5: Commit**

```bash
git add src/panda_gazebo_demo/test/headless src/panda_gazebo_demo/README.md \
  docs/superpowers/plans/2026-07-23-complete-pick-place-state-machine.md \
  docs/superpowers/specs/2026-07-23-complete-pick-place-state-machine-design.md
git commit -m "test: verify complete world reset"
```
