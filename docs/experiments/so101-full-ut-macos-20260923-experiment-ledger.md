---
task_id: so101-full-ut-macos-20260923-5a0b87a8
goal: Run every ordinary unit and package test on macOS for main commit 5a0b87a8.
success_contract: Fresh dependency-complete build; every package CTest/GTest and each module's complete ordinary pytest scope pass; Bun unit suite passes; all exclusions and skips recorded.
worktree: /Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp
branch: codex/so101-unified-webapp
base_commit: 5a0b87a835608987a41533547eb0c4457007efc3
current_commit: 5a0b87a835608987a41533547eb0c4457007efc3
evidence_root: /tmp/so101-debug-full-ut-macos-20260923-5a0b87a8
confirmed_conclusions:
  - CP-001: This worktree and main have identical 5a0b87a8 trees; the fork submodule is initialized at 5a590b2.
  - CP-002: Web, pick_place_common, so101_demo_py, and so101_teleop ordinary unit gates passed; the complete compiled gate could not start from a dependency-complete build on this host.
disproven_routes: []
open_hypotheses:
  - Whether an isolated macOS Harmonic and MoveIt dependency closure can be supplied without changing the shared Homebrew installation.
latest_checkpoint: CP-002
next_experiment: NONE
---

## CP-001: scope and provenance

The previous integration task ran Web Vitest and complete ordinary pytest only for
`so101_demo_py` and `so101_teleop`. This follow-up covers the remaining source packages and
the checked-out fork on the same commit. The host has ten logical CPUs, so every module-wide
pytest run uses eight xdist workers. Existing build/install trees are older; tests must use a
fresh task-owned build and install, with no benchmark collection.

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: Fresh source and a complete dependency closure can run the full package gate.
working_tree_status: Clean before this ledger was added.
owned_processes: NONE
preserved_processes: Existing tmux sessions and shared installed overlays.
confirmed_conclusions:
  - The project has eight source packages and six fork packages registered with colcon.
  - The current worktree is 5a0b87a8; the system has 10 logical CPUs.
disproven_routes: []
open_risks:
  - Installed global fork overlay points to an earlier pin; a task-owned build must carry the tested fork revision.
next_command: Build the complete package closure under the registered evidence root.
```

## EXP-001: fresh build and full unit gate

```yaml
experiment_id: EXP-001
status: INVALID
prior_experiment: NONE
hypothesis: All source and fork packages build, then all ordinary package tests, complete module pytest scopes, and Bun units pass on macOS.
prediction: Nonzero test collection in each eligible module, zero failed cases and zero unaccounted package tests.
single_variable: NONE (verification of published main tree)
lifecycle: REUSE_STACK
preconditions:
  - Exact ROS Python, Bun, fork source pin, underlays, and task-owned build paths verified.
success_criteria:
  - Build exit 0, package test exit 0, module pytest at eight workers exit 0, Bun units exit 0.
failure_criteria:
  - Any compiled, Python, or Web assertion fails after the intended boundary runs.
invalid_criteria:
  - Missing dependency closure or interpreter environment prevents test collection.
provenance:
  source_commit: 5a0b87a835608987a41533547eb0c4457007efc3
  install_overlay: /tmp/so101-debug-full-ut-macos-20260923-5a0b87a8/install
  runtime_executable: /opt/ros2_jazzy/.venv/bin/python; /opt/homebrew/bin/bun
  ros_domain_id: 230
  gz_partition: so101-full-ut-macos-230
commands:
  - command: Fresh colcon build of src and checked-out fork packages
    exit_code: nonzero; dependency configuration stopped before compiled tests
  - command: Full module pytest with -n 8, excluding benchmark_test
    exit_code: mixed; exact module results in CP-002
  - command: Full registered package CTest/GTest gate
    exit_code: NOT_RUN; build dependency closure unavailable
  - command: bun run test
    exit_code: 0
observed:
  - Missing gz-msgs10, gz_ros2_control, and moveit_ros_planning_interface stop the fresh build.
  - Four ordinary Python/Web gates passed; other direct Python runs are runner-blocked as recorded in CP-002.
inferred:
  - The macOS host cannot currently attest the complete compiled package gate for this commit.
conclusion: Dependency closure invalidated the compiled gate; the recorded Python and Web gates are valid partial evidence.
evidence:
  - /tmp/so101-debug-full-ut-macos-20260923-5a0b87a8
decision: Do not claim all macOS UT passed.
next_experiment: NONE
```

## CP-002: macOS execution evidence

Source and fork revisions remained at `5a0b87a8` and `5a590b2`. The task-owned Python
overlay is `/tmp/so101-debug-full-ut-macos-20260923-5a0b87a8/python-install-overlay`;
the exact Python is `/opt/ros2_jazzy/.venv/bin/python`. `ROS_DOMAIN_ID=230` and
`GZ_PARTITION=so101-full-ut-macos-230` were used for the direct Python runs. The host has
10 logical CPUs, so each full module run used `pytest -n 8` and wrote JUnit into the
registered evidence root.

- `bun run test`: exit 0, 53 files and 300 tests passed (`web-unit.log`).
- `pick_place_common/test`: exit 0, 3 passed (`pick_place_common.xml`).
- `so101_demo_py/test`: exit 0, 3918 passed and 10 skipped after correcting the
  runner's IPC and overlay environment (`so101_demo_py_final.xml`). The two earlier
  attempts are retained as invalid runner experiments.
- `so101_teleop/test`: exit 0, 1071 passed and 2 skipped (`so101_teleop_full.xml`).
- `panda_gazebo_demo_cpp/test`: exit 1, 5 failed and 15 passed. Installing task-owned
  `xacro` moved the failure boundary to absent `gz_ros2_control` and GNU `timeout`
  (`panda_gazebo_demo_cpp-2.xml`).
- `so101_gazebo_demo_cpp/test`: collection failed because the package is absent from
  the Mac overlay (`so101_gazebo_demo_cpp.xml`).
- Fork direct pytest: 116 passed, 3 failed because the CTest install and compile
  environment variables are absent (`mujoco_ros2_control.xml`); the CTest gate needs
  a fresh build.
- Fresh colcon build failed before a compiled test ran. The Mac underlay lacks
  `gz-msgs10`, `gz_ros2_control`, and `moveit_ros_planning_interface`. Homebrew's
  `gz-sim8` dry run would install 14 packages and upgrade 93 existing formulae; the
  global upgrade was not performed. See `build.log` and `build-2.log`.

The complete macOS package CTest/GTest gate is therefore blocked by dependency
closure. Retained evidence is the full registered `/tmp` root, with no archived runs.
Scratch directories, failed build trees, and invalid runner attempts are deletion
candidates after readback, but none has been deleted.
