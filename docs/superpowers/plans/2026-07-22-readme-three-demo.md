# README Three-Demo Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the repository README so it accurately presents `fixed_pose_goal`, `panda_gazebo_demo`, and the planned `so_arm_gazebo_demo` as three independent demos.

**Architecture:** Keep one repository-level README as the entry point. Lead with a status table and repository structure, then give each demo a self-contained section; retain verified fixed-pose details, derive Panda entry points from current CMake and launch files, and describe SO-ARM101 only as planned work.

**Tech Stack:** Markdown, ROS 2 Jazzy, MoveIt 2, Gazebo Sim, `colcon`, C++17

## Global Constraints

- Modify documentation only; do not change ROS 2 source, launch, build, or runtime behavior.
- Use the exact paths `src/fixed_pose_goal`, `src/panda_gazebo_demo`, and `src/so_arm_gazebo_demo`.
- Mark the demos as `已实现`, `开发中`, and `规划中`, respectively.
- Do not invent dependencies, executables, launch files, or commands for `so_arm_gazebo_demo`.
- Preserve the valid fixed Pose, RViz Marker, safety, and Panda IK-multiplicity explanations from the current README.

---

### Task 1: Restructure the repository README

**Files:**
- Modify: `README.md`
- Reference: `src/fixed_pose_goal/CMakeLists.txt`
- Reference: `src/fixed_pose_goal/launch/fixed_pose_goal.launch.py`
- Reference: `src/panda_gazebo_demo/CMakeLists.txt`
- Reference: `src/panda_gazebo_demo/launch/panda_gazebo.launch.py`

**Interfaces:**
- Consumes: The package, executable, launch, and `headless` names declared by the reference files.
- Produces: A repository-level README with an accurate three-demo overview and runnable commands only for existing packages.

- [ ] **Step 1: Replace the single-demo opening with the repository overview**

  Use `# ROS 2 MoveIt 机械臂 Demo` as the title. Add this status table before implementation details:

  ```markdown
  | Demo | 状态 | 定位 |
  | --- | --- | --- |
  | `fixed_pose_goal` | 已实现 | 固定目标 Pose、RViz Goal State 同步、规划与执行 |
  | `panda_gazebo_demo` | 开发中 | Panda、Gazebo、MoveIt 2 与抓取状态机 |
  | `so_arm_gazebo_demo` | 规划中 | SO-ARM101 与 Gazebo 仿真 |
  ```

  Follow it with a `src/` tree showing the two current directories and `so_arm_gazebo_demo/ # 规划中，目录尚未创建`.

- [ ] **Step 2: Create a self-contained `fixed_pose_goal` section**

  Preserve the existing node responsibilities, fixed target Pose, marker name, package build commands, launch command, individual `ros2 run` commands, execution safety warning, and seven-degree-of-freedom IK explanation. Label `fixed_pose_goal` and `interactive_marker_pose_feedback` as nodes inside this demo, not as separate demos.

- [ ] **Step 3: Add a source-backed `panda_gazebo_demo` section**

  State that `panda_gazebo.launch.py` starts Gazebo, Panda, controllers, `move_group`, Planning Scene setup, and RViz. Document these commands:

  ```bash
  colcon build --packages-select panda_gazebo_demo
  source install/setup.bash
  ros2 launch panda_gazebo_demo panda_gazebo.launch.py
  ros2 launch panda_gazebo_demo panda_gazebo.launch.py headless:=true
  ```

  List the current executables exactly as `planning_scene_setup`, `pre_grasp_plan`, `attach_and_lift_demo`, and `pick_place_state_machine`. Describe the grasp workflow as under development rather than complete.

- [ ] **Step 4: Add the planned `so_arm_gazebo_demo` section and common setup**

  Say that the goal is an SO-ARM101 Gazebo simulation integrated with MoveIt 2. Explicitly state that the package directory, dependencies, executables, and run commands do not exist yet. Add common ROS 2 Jazzy, MoveIt 2, Gazebo, `colcon`, and C++17 requirements plus a whole-workspace build command.

- [ ] **Step 5: Verify the README against the repository**

  Run:

  ```bash
  git diff --check
  rg -n "fixed_pose_goal|panda_gazebo_demo|so_arm_gazebo_demo|已实现|开发中|规划中" README.md
  rg -n "planning_scene_setup|pre_grasp_plan|attach_and_lift_demo|pick_place_state_machine" README.md
  rg -n "add_executable" src/fixed_pose_goal/CMakeLists.txt src/panda_gazebo_demo/CMakeLists.txt
  ```

  Expected: `git diff --check` exits 0; all three Demo names and statuses appear; all documented Panda executables match CMake; no SO-ARM101 execution command is present.

- [ ] **Step 6: Review the final diff**

  Run:

  ```bash
  git diff -- README.md
  git status --short
  ```

  Expected: Runtime source files are untouched; the only implementation change is `README.md`, alongside the design and plan documentation created for this change.
