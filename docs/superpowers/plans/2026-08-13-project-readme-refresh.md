# Project README Refresh Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the obsolete Panda-only root README with a concise, accurate workspace overview centered on the current SO-101 Python, C++, Teleop, and shared-core packages.

**Architecture:** Treat the root README as a navigation and quick-start layer. Describe ownership and data flow at package granularity, link to authoritative component documents for detailed behavior, and derive every shown command from installed launch or console-script entry points that exist in the current tree.

**Tech Stack:** Markdown, ROS 2 Jazzy, colcon, MoveIt 2, Gazebo Harmonic, MuJoCo, ROS 2 Python/C++ packages.

---

### Task 1: Capture the documentation baseline

**Files:**
- Inspect: `README.md`
- Inspect: `src/so101_demo_py/README.md`
- Inspect: `src/so101_demo_py/setup.py`
- Inspect: `src/so101_demo_py/launch/*.launch.py`
- Inspect: `src/so101_teleop/docs/so101-teleop-web-ui.md`
- Inspect: `src/so101_gazebo_demo_cpp/README.md`
- Inspect: `src/panda_gazebo_demo_cpp/README.md`
- Inspect: `scripts/install-mujoco-ros2-control.zsh`

- [x] **Step 1: Record the expected failing README contract**

Run:

```bash
rg -q 'so101_demo_py' README.md
```

Expected: non-zero because the obsolete root README does not introduce the canonical Python package.

- [x] **Step 2: Record the stale scope**

Run:

```bash
rg -n '^#|fixed_pose_goal|Panda|so101_demo_py|so101_teleop' README.md
```

Expected: the README is Panda/fixed-pose focused and lacks the current SO-101 package overview.

- [x] **Step 3: Verify public entry points before documenting them**

Run:

```bash
find src/so101_demo_py/launch src/so101_teleop/launch src/so101_gazebo_demo_cpp/launch src/panda_gazebo_demo_cpp/launch src/fixed_pose_goal/launch \
  -maxdepth 1 -type f -name '*.launch.py' -printf '%p\n' | sort
rg -n 'console_scripts|pick_place =|scene_setup =|camera_preset =|teleop_reset =' src/so101_demo_py/setup.py
```

Expected: all commands selected for the README have a current source entry point.

### Task 2: Rewrite the root README

**Files:**
- Modify: `README.md`

- [x] **Step 1: Replace the obsolete introduction and capability list**

Write a short Chinese workspace introduction that identifies ROS 2 Jazzy, MoveIt 2, Gazebo Harmonic, MuJoCo, and the canonical `so101_demo_py` package. Summarize only the primary capabilities: unified SO-101 Python simulation, C++ Gazebo workflows, backend-neutral Teleop, shared pick-place core, and retained Panda/fixed-pose examples.

- [x] **Step 2: Add a package-level architecture overview**

Document the high-level flow:

```text
operator / Teleop
        |
        v
so101_demo_py or robot-specific C++ package
        |
        v
MoveIt 2 + ros2_control
        |
        v
Gazebo Harmonic or MuJoCo
```

Explain ownership at package granularity only. Link detailed Python and C++ architecture documents instead of copying implementation internals.

- [x] **Step 3: Add a curated repository tree**

Include the maintained source packages and the top-level documentation, scripts, and pinned third-party dependency. Do not list generated `build/`, `install/`, or `log/` content as source structure. Do not present the removed `so101_gazebo_demo_py` or `so101_mujoco_demo_py` directories as available packages.

- [x] **Step 4: Add environment and build quick starts**

Show:

```bash
cd /data/work/ws_moveit
source /opt/ros/jazzy/setup.zsh
rosdep install --from-paths src --ignore-src -r -y
zsh scripts/install-mujoco-ros2-control.zsh --init-submodule
source /data/work/ws_mujoco_ros2_control_fork/install/setup.zsh
colcon build --base-paths src --symlink-install
source install/setup.zsh
```

Clarify that the installer is needed for the full MuJoCo path and that Gazebo/C++ subsets can be built with `colcon build --packages-up-to <package>`.

- [x] **Step 5: Add safe run examples**

Use the canonical dry-run defaults first:

```bash
ros2 launch so101_demo_py so101_mujoco_pick_place.launch.py
ros2 launch so101_demo_py so101_gazebo_pick_place.launch.py
```

Show explicit simulation execution separately with `run_mode:=execute execute:=true`. Include short examples for the shared `scene_setup`, `camera_preset`, and `teleop_reset` CLIs; one Teleop launch; the primary C++ Gazebo launch; and one Panda/fixed-pose pointer. Keep advanced session, evidence, reset-phase, and qualification details in component documentation.

- [x] **Step 6: Add the documentation index and safety boundary**

Link the unified Python README, Python architecture, integration guide, C++ architecture/launch contracts, Gazebo C++ README, Teleop guide, and Panda README. State that current operator paths are simulation-only and real hardware remains fail-closed.

### Task 3: Validate README accuracy

**Files:**
- Verify: `README.md`
- Verify: repository paths referenced by `README.md`

- [x] **Step 1: Run the positive content contract**

Run:

```bash
rg -q 'so101_demo_py' README.md
rg -q 'so101_teleop' README.md
rg -q 'so101_gazebo_demo_cpp' README.md
rg -q 'panda_gazebo_demo_cpp' README.md
rg -q 'scripts/install-mujoco-ros2-control.zsh' README.md
```

Expected: all commands return zero.

- [x] **Step 2: Check paths, launch files, and Markdown links**

Run a small read-only Python verifier that extracts repository-relative Markdown links and backticked `src/`, `docs/`, `scripts/`, and `third_party/` paths from `README.md`, then asserts each target exists. Separately assert that every documented `ros2 launch <package> <file>` maps to a source launch file.

Expected: zero missing paths, links, or launch files.

- [x] **Step 3: Check removed-package and detail boundaries**

Run:

```bash
test ! -d src/so101_gazebo_demo_py
test ! -d src/so101_mujoco_demo_py
rg -n 'aa83a43c|FULL_RESTART|primitive counts|failure_code|retry metrics' README.md
```

Expected: both directory checks pass and the final search returns no matches, confirming the root README stays introductory.

- [x] **Step 4: Run repository text checks**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only the intended README and plan changes are present.

- [x] **Step 5: Review and commit**

Run:

```bash
git diff -- README.md docs/superpowers/plans/2026-08-13-project-readme-refresh.md
git add README.md docs/superpowers/plans/2026-08-13-project-readme-refresh.md
git commit -m "docs: refresh project README"
```

Expected: one documentation-only commit; no push, merge, generated artifacts, or runtime state changes.
