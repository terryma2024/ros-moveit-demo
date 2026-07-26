# SO-101 固定位置 Pick-Place 状态机迁移实施计划

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. A fresh implementer and an independent reviewer are required for every task.

**Goal:** 在自包含 `so101_gazebo_demo` package 内，以复制隔离方式实现 SO-101 固定位置 Coke pick-place、事实驱动 recovery、checkpoint/resume 和 headless E2E，同时保持 Panda 子树不变。

**Architecture:** 保留 Panda 的纯状态机/runner/checkpoint 结构；用 `SO101Profile` 集中承载机器人绑定；用 joint-space goals/waypoint ladders 驱动 5-DOF 手臂，用 TCP 位置与工具轴倾角验证；用单关节 FollowJointTrajectory 驱动夹爪；Gazebo DetachableJoint 与 MoveIt AttachedCollisionObject 分别建模物理和规划 attachment。

**Tech Stack:** ROS 2 Jazzy, C++17, rclcpp/rclcpp_action, control_msgs, MoveIt 2, ros_gz/gz transport, Gazebo Harmonic, ament_cmake_gtest, launch_testing, shell headless tests.

**Design:** `docs/superpowers/specs/2026-07-26-so101-pick-place-port-design.md`

## Global Constraints

- Work directly in `/data/work/ws_moveit` `main`; the user explicitly approved direct-main execution for this migration.
- Do not modify `src/panda_gazebo_demo`; its Git tree object must remain `75fb2e1e66ad1440f47f52f708b91887384084fd`.
- Do not create a shared Panda/SO library in this phase.
- Source only `/opt/ros/jazzy/setup.zsh` and `/data/work/ws_moveit/install/setup.zsh`; never source `/data/work/so101_lerobot_ws`.
- Use `apply_patch` for source edits. Stage and commit only files in this task's explicit scope.
- Test first: add/adjust a failing test, observe the expected failure, implement the minimum code, then run the focused and package-level gates.
- Do not treat action success, logs, visual mesh, or checkpoint history as physical truth. Use fresh independent observations.
- Constants binding SO-101 must come from one profile/config source: arm group `arm`; TCP `so101_tcp`; joints `1..5`; gripper joint `6`; q_preopen `0.707194871`; q_contact `0.662818811`; attachment topics `/so101/*`; MoveIt attach link `gripper`; touch links `gripper`,`jaw`.
- Complete quaternion error is forbidden for SO motion acceptance. Validate TCP position plus tool approach-axis angle and leave axial twist free.
- Before contact execution, prove Gazebo collision geometry exists for the gripper/jaw and eliminate or explicitly isolate the DART mesh collision construction warnings.
- Before carrying motion, Gazebo and MoveIt must both independently report Coke attached.
- All GUI programs on ai-station follow the repository tmux/gui-env/capture SOP.

---

### Task 1: Establish SO-101 simulation physics and observation prerequisites

**Files:**

- Modify: `src/so101_gazebo_demo/urdf/so101_ros2_control.xacro`
- Modify: `src/so101_gazebo_demo/urdf/so101_gazebo.xacro`
- Modify: `src/so101_gazebo_demo/urdf/so101_base.xacro`
- Modify: `src/so101_gazebo_demo/launch/so101_gazebo.launch.py`
- Add/Modify tests under: `src/so101_gazebo_demo/test/`

**Requirements:**

1. Add finite, observable velocity state for joints `1..6`, or implement a documented multi-sample position-window stationary source if Gazebo cannot expose finite velocity. Never coerce missing/NaN velocity to zero.
2. Add Gazebo `DetachableJoint` for Coke with SO topics and `initially_detached=true`. Resolve the actual parent link from runtime Gazebo entity evidence; expected MoveIt link names do not substitute for Gazebo evidence.
3. Replace/augment collision geometry needed for gripper/jaw/Coke contact with Gazebo-supported geometry. Preserve visual meshes and MoveIt collision correctness. The gate is no DART construction failure for load-bearing contact geometry.
4. Bridge only topics that ROS consumers need; keep attachment raw event/state separation compatible with the later relay.
5. Add static contract tests plus a runtime smoke test that proves finite joint evidence, attach/detach state changes, Coke follows the gripper when attached, and is independent after detach.

**Verification:**

```bash
cd /data/work/ws_moveit
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_gazebo_demo --symlink-install
source install/setup.zsh
colcon test --packages-select so101_gazebo_demo
colcon test-result --verbose
```

Record exact Gazebo parent link, warning scan, topic evidence and Coke pose deltas in the task report.

---

### Task 2: Copy the pure state-machine core and dry-run contracts

**Files:**

- Add: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/*.hpp`
- Add: `src/so101_gazebo_demo/src/pick_place/*.cpp` for pure core only
- Add: `src/so101_gazebo_demo/test/pick_place/*.cpp` for pure core
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`
- Modify: `src/so101_gazebo_demo/package.xml`

**Requirements:**

1. Copy and namespace-convert domain types, state enum/table, action/registry interfaces, runner, plan validation, checkpoint v3, file checkpoint store, simulation session id, world snapshot types and common resume validator.
2. Preserve the full forward and recovery state graph from Panda, including PREPARE_OPEN_GRIPPER and RECOVER_SYNC_WORLD_OBJECT.
3. Preserve `dry_run`, `plan_only`, `execute`, `fail_at`, `stop_after`, checkpoint and resume business semantics.
4. Do not copy ROS adapters, target policy, Panda finger logic, Panda links, or the unused `move_above_object_planner` / `descend_planner_executor` wrappers.
5. Add a minimal `pick_place_state_machine` executable or test harness sufficient to prove dry-run normal/fail_at state sequences without registering unsafe physical executors.

**Verification:**

- Focused gtests for transition coverage, modes, checkpoint v3, resume boundary and recovery selection.
- `rg -n "panda_|panda_arm|panda_hand|panda_tcp" src/so101_gazebo_demo/include src/so101_gazebo_demo/src src/so101_gazebo_demo/test/pick_place` has no runtime leakage; provenance comments may be narrowly allowlisted.
- Dry-run normal sequence ends DONE; `fail_at=ATTACH_MOVEIT` enters the complete recovery chain and ends ERROR.

---

### Task 3: Implement SO-101 gripper, scene, attachment, and observation adapters

**Files:**

- Add/Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_profile.hpp`
- Add/Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/*adapter*.hpp`
- Add/Modify: `src/so101_gazebo_demo/src/pick_place/*adapter*.cpp`
- Add: `src/so101_gazebo_demo/src/nodes/gazebo_attachment_state_relay.cpp`
- Add: `src/so101_gazebo_demo/src/nodes/reset_moveit_world.cpp`
- Add/Modify: `src/so101_gazebo_demo/test/pick_place/`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`, `package.xml`, and launch files

**Requirements:**

1. Introduce a single SO profile for all values listed under Global Constraints plus table/Coke geometry.
2. Implement a single-joint `FollowJointTrajectory` gripper adapter. Commands contain only joint `6`; pre-open/contact completion uses action result, fresh joint state, q6 tolerance, stopped evidence and the same 20 mm-section width geometry used by the calculator.
3. Implement attachment relay/executor/observer using `/so101/attach_coke`, `/so101/detach_coke`, `/so101/coke_attached_event`, `/so101/coke_attached`.
4. Implement MoveIt scene adapter/executor with table `0.50 × 0.60 × 0.04`, canonical table/Coke poses, attach link `gripper`, touch links exactly `gripper`,`jaw`.
5. Implement reset that converges from detached, gazebo-only, moveit-only, or both-attached states to detached canonical world state.
6. Implement SO transition/recovery contract pieces that depend on q6 or attachment evidence. Recovery decisions use current observations, not historical flags.

**Verification:**

- Unit/fake-action tests for q6 command payload, error/timeout/cancel, q6/width validation and no Panda-finger symmetry assumption.
- Unit tests for exact scene geometry/link/touch-link contract and all four reset initial states.
- Live tests prove q6 pre-open/contact feedback and independent Gazebo/Planning Scene attachment evidence.

---

### Task 4: Implement 5-DOF motion evidence and calibrate fixed targets

**Files:**

- Add/Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/*motion*.hpp`
- Add/Modify: `src/so101_gazebo_demo/src/pick_place/*motion*.cpp`
- Add/Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/pick_place_target_policy.hpp`
- Add/Modify: `src/so101_gazebo_demo/src/pick_place/pick_place_target_policy.cpp`
- Add calibration executable under: `src/so101_gazebo_demo/src/nodes/`
- Add tests under: `src/so101_gazebo_demo/test/pick_place/`
- Modify: `CMakeLists.txt`, `package.xml`, README/config as needed

**Requirements:**

1. Add joint-goal and joint-waypoint-ladder planning requests/evidence. Reconstruct the TCP path through MoveIt FK and preserve collision/time/joint-start evidence.
2. Validate TCP endpoint position and approach-axis angle. The axis error is `acos(clamp((R*a_local) dot a_target,-1,1))`; do not reject axial twist.
3. For DESCEND/LIFT/PLACE_DESCEND ladders, validate axial monotonicity, lateral deviation, endpoint, tool-axis error at every sample, joint jump, duration and collision awareness.
4. Add a CLI calibration/plan-only utility. Starting from the actual canonical world, discover reachable collision-free above-pick, pick, above-place, place and retreat joint targets plus local ladders. Do not copy Panda XYZ/quaternion targets.
5. Version the accepted fixed targets in one SO policy/config source and lock them with tests. Record exact joint and FK TCP values.
6. Cartesian planning may be measured, but must not become an E2E dependency unless it independently passes all the same plan gates.

**Verification:**

- Pure geometry tests include identical tool axes with different axial twist and reject excessive tilt/lateral drift/non-monotonic paths.
- Plan-only matrix covers every forward and recovery motion state against live MoveIt Planning Scene.
- No motion execute is permitted until the entire matrix passes.

---

### Task 5: Assemble the runtime and pass fixed-position forward execution

**Files:**

- Add/Modify: `src/so101_gazebo_demo/src/nodes/pick_place_state_machine_node.cpp`
- Add/Modify: `src/so101_gazebo_demo/src/pick_place/pick_place_runtime.cpp`
- Add/Modify: forward actions/contracts/registries under `include/.../pick_place` and `src/pick_place`
- Add/Modify: `src/so101_gazebo_demo/launch/so101_pick_place.launch.py`
- Add/Modify: runtime tests and README
- Modify: `CMakeLists.txt`, `package.xml`

**Requirements:**

1. Register every forward action, planner, executor and transition validator exactly once.
2. Enforce `observe → precondition → plan → plan validate → execute → observe → transition validate` for every action state.
3. Wire full forward sequence from IDLE through DONE. `ATTACH_MOVEIT` executes once in its state and never inside LIFT planning/execution.
4. Implement checkpoint/stop/resume parameters with the same semantics as the copied core.
5. Run staged execution gates: PREPARE_OPEN, MOVE_ABOVE, DESCEND, CLOSE, two attaches, LIFT, transfer, place, two detaches, world sync, retreat. Persist evidence for each boundary.
6. Failure after a side effect must enter the correct recovery path; environment observation failure before planning stops without blind recovery.

**Verification:**

- Registration coverage and dry-run tests.
- `plan_only` stop/resume matrix.
- Execute staged tests, then one complete fixed-position run ending DONE with Coke at fixed place, q6 open, both worlds detached and Coke poses synchronized.
- Confirm `src/panda_gazebo_demo` tree object remains unchanged.

---

### Task 6: Complete recovery, headless CI, repeated E2E, and final evidence

**Files:**

- Add/Modify: `src/so101_gazebo_demo/test/headless/*`
- Add/Modify: `src/so101_gazebo_demo/launch/so101_pick_place.launch.py`
- Add/Modify: recovery policy/contracts and reset helpers as findings require
- Add/Modify: `src/so101_gazebo_demo/README.md`
- Add/Modify: package test registration

**Requirements:**

1. Port headless orchestration with deterministic startup/readiness/timeout/process cleanup and `headless` launch parameter.
2. Test normal execute plus `gazebo_only`, `moveit_only`, `both_attached` recovery scenarios. Each scenario must seed and independently observe its stated boundary.
3. Test stop/checkpoint/resume success and rejection of stale, inconsistent or skipped boundaries.
4. Run three consecutive complete fixed-position pick-place trials from canonical reset.
5. Capture final GUI using the ai-station SOP and independently collect controller state, TF, `/joint_states`, Gazebo Coke pose/attachment, MoveIt Planning Scene attachment/world pose, terminal status and failure categories.
6. Run full package and Panda regression gates. Update README with build, launch, calibration, dry-run, plan-only, execute, resume, recovery and headless commands.

**Final Verification:**

```bash
cd /data/work/ws_moveit
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select panda_gazebo_demo so101_gazebo_demo --symlink-install
source install/setup.zsh
colcon test --packages-select panda_gazebo_demo so101_gazebo_demo
colcon test-result --verbose
git status --short
git rev-parse HEAD:src/panda_gazebo_demo
```

The task report must list all three E2E runs, all recovery scenarios, final screenshot path, independent state evidence, warning scan, exact commits and remaining non-blocking limitations.
