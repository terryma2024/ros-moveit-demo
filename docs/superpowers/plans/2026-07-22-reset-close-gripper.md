# Reset Script Close-Gripper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `reset_coke.sh` close the Panda gripper after moving the arm to its ready pose.

**Architecture:** Keep reset orchestration in the existing shell script and add one focused
`close_gripper` function using the ROS 2 gripper action. Exercise the complete script through
fake command-line adapters so the test does not require a running Gazebo or ROS graph.

**Tech Stack:** Bash, ROS 2 CLI, `control_msgs/action/GripperCommand`, CMake/CTest

## Global Constraints

- Do not run `ament_uncrustify --reformat`.
- Do not use GitHub CLI commands; this repository is hosted on Gitee.
- Preserve unrelated working-tree changes.

---

### Task 1: Close the gripper during reset

**Files:**
- Create: `src/panda_gazebo_demo/test/scripts/test_reset_coke.sh`
- Modify: `src/panda_gazebo_demo/scripts/reset_coke.sh`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`

**Interfaces:**
- Consumes: `/panda_hand_controller/gripper_cmd` with action type
  `control_msgs/action/GripperCommand`.
- Produces: `close_gripper`, which returns non-zero unless the action completes with status
  `SUCCEEDED`.

- [ ] **Step 1: Write the failing shell regression test**

  Add fake `gz` and `ros2` executables, invoke the reset script, and assert the ROS command log
  contains the arm goal followed by a gripper goal whose YAML includes `position: 0.0`.

- [ ] **Step 2: Run the test to verify it fails**

  Run:

  ```bash
  bash src/panda_gazebo_demo/test/scripts/test_reset_coke.sh \
    src/panda_gazebo_demo/scripts/reset_coke.sh
  ```

  Expected: failure because the gripper action is not called.

- [ ] **Step 3: Implement the minimal close action**

  Add configurable gripper action, position, effort, and timeout variables. Add
  `close_gripper`, validate action discovery, send the close goal, verify the CLI output reports
  `SUCCEEDED`, and invoke it after `move_arm_to_ready`.

- [ ] **Step 4: Register and run the test**

  Register the shell test using `add_test` inside `BUILD_TESTING`, then run:

  ```bash
  colcon build --packages-select panda_gazebo_demo --cmake-args -DBUILD_TESTING=ON
  colcon test --packages-select panda_gazebo_demo --event-handlers console_direct+
  colcon test-result --verbose
  ```

  Expected: package build succeeds and CTest reports no failures.

- [ ] **Step 5: Review the patch**

  Run:

  ```bash
  bash -n src/panda_gazebo_demo/scripts/reset_coke.sh
  bash -n src/panda_gazebo_demo/test/scripts/test_reset_coke.sh
  git diff --check
  ```

  Expected: all commands return zero.
