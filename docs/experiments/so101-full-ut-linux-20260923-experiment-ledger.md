---
task_id: so101-full-ut-linux-20260923-5a0b87a8
goal: Run every ordinary unit and package test on Linux for main commit 5a0b87a8.
success_contract: Fresh dependency-complete build; every package CTest/GTest and each module's complete ordinary pytest scope pass with eight workers; all exclusions and skips recorded.
worktree: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/worktree
branch: detached at main commit 5a0b87a8
base_commit: 5a0b87a835608987a41533547eb0c4457007efc3
current_commit: 5a0b87a835608987a41533547eb0c4457007efc3
evidence_root: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8
confirmed_conclusions:
  - CP-001: The existing Linux main checkout is older; an independent worktree now contains the published 5a0b87a8 commit and fork pin 5a590b2.
  - CP-003: All 14 source and fork packages built; all ordinary test scopes were attempted, but the full Linux test gate failed.
disproven_routes:
  - The older /data/work/ws_moveit workspace path is absent on this host.
open_hypotheses:
  - Which platform-assumption and socket teardown fixes are needed for a green eight-worker Linux gate.
latest_checkpoint: CP-003
next_experiment: NONE
---

## CP-001: scope and provenance

The Linux host is `ai-station`. Its pre-existing main checkout remains on `0bce9179` and is
untouched. A detached worktree at published main commit `5a0b87a8` carries the source under
this task's durable evidence root. The host reports 32 logical CPUs, so every module-wide pytest
uses eight xdist workers. The system Python lacks xdist; the test environment must be task-owned.
No benchmark suite is in the ordinary gate.

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: A task-owned interpreter and fresh complete build can run the full package gate.
working_tree_status: Clean before this ledger was added.
owned_processes: NONE
preserved_processes: The older Linux main checkout and other task worktrees.
confirmed_conclusions:
  - The detached worktree and initialized fork use 5a0b87a8 and 5a590b2 respectively.
  - The host has 32 logical CPUs; /usr/bin/python3 has pytest 7.4.4 but no xdist.
disproven_routes:
  - /data/work/ws_moveit is not the workspace on this host.
open_risks:
  - The existing installed project and fork overlays are older than the target commit.
next_command: Prepare a task-owned Python and complete dependency build under this evidence root.
```

## EXP-001: fresh build and full unit gate

```yaml
experiment_id: EXP-001
status: VALID
prior_experiment: NONE
hypothesis: All source and fork packages build, then all ordinary package tests and module pytest scopes pass on Linux.
prediction: Nonzero test collection in each eligible module, zero failed cases and zero unaccounted package tests.
single_variable: NONE (verification of published main tree)
lifecycle: REUSE_STACK
preconditions:
  - Exact Python, xdist, ROS underlay, fork source pin, and NVMe scratch resolved before pytest or colcon test.
success_criteria:
  - Build exit 0, package test exit 0, module pytest at eight workers exit 0.
failure_criteria:
  - Any compiled or Python assertion fails after the intended boundary runs.
invalid_criteria:
  - Missing dependency closure or interpreter environment prevents test collection.
provenance:
  source_commit: 5a0b87a835608987a41533547eb0c4457007efc3
  install_overlay: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/install-3
  runtime_executable: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python
  ros_domain_id: 231
  gz_partition: so101-full-ut-linux-231
commands:
  - command: Fresh colcon build of src and checked-out fork packages
    exit_code: 0; 14 packages
  - command: Full module pytest with -n 8, excluding benchmark_test
    exit_code: mixed; exact module results in CP-002 and CP-003
  - command: Full registered package CTest/GTest gate
    exit_code: 1; 236 registered tests, 22 failures, no errors
observed:
  - Eight-worker complete pytest passed in pick_place_common, panda_gazebo_demo_cpp, so101_gazebo_demo_cpp, and the fork core; failed in so101_demo_py and so101_teleop.
  - The registered package gate failed in fixed_pose_goal, so101_teleop, and mujoco_ros2_control_tests.
inferred:
  - Published main commit 5a0b87a8 has no all-green Linux ordinary unit gate on this host.
conclusion: Complete Linux gate executed and failed; CP-003 records the failure boundaries.
evidence:
  - /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8
decision: Do not claim all Linux UT passed.
next_experiment: NONE
```

## CP-002: Linux build and Python gate in progress

The fresh target-commit build completed all 14 packages under
`/data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/build-3` and
`install-3` (`build-3.log`). The exact pytest executable is the task-owned
`venv/bin/python`; `ROS_DOMAIN_ID=231` and `GZ_PARTITION=so101-full-ut-linux-231`.
Each pytest had a unique NVMe scratch tree and a successful
`tempfile.gettempdir()` proof from that exact executable (`scratch-paths.txt`).
The host has 32 logical CPUs; all module-wide pytest runs used `-n 8`.

- `bun run test`: exit 0, 53 files and 300 tests passed (`web-unit.log`).
- `pick_place_common/test`: exit 0, 3 passed (`pick_place_common.xml`).
- `panda_gazebo_demo_cpp/test`: exit 0, 20 passed (`panda_gazebo_demo_cpp.xml`).
- `so101_gazebo_demo_cpp/test`: exit 0, 217 passed and 8 skipped after task-owned
  FFmpeg and correct generated-asset paths (`so101_gazebo_demo_cpp-3.xml`). Earlier
  runs are retained as invalid runner experiments.
- `so101_demo_py/test`: 13 failed, 3760 passed, 150 skipped, and 5 errors
  (`so101_demo_py-2.xml`). Twelve failures and five errors are macOS-specific
  tests that assume Darwin/MPS and `/opt/data/tmp` or `/private/tmp` on Linux.
  One `parallel_ipc` test assumes a non-null child environment. These reached
  their assertions; the full module gate is not green.
- `so101_teleop/test`: the first dependency-complete eight-worker run reached
  42 failed, 1007 passed, and 18 skipped, then stalled near completion for more
  than four minutes with all workers waiting. The parent was interrupted after
  process and log inspection (`so101_teleop-3.log`). Many failures assume
  Darwin/MPS; individual failures and the stalled test still need classification.
- Fresh `colcon test` of all built packages other than `so101_demo_py` is running
  with unique NVMe scratch and both system and venv Python temp-path proofs.

The full Linux gate is in progress and must not be reported as passed. Retained
evidence is the entire registered durable root, with no archived runs. Scratch,
prior failed build attempts, and invalid runner runs are deletion candidates
after readback; none has been deleted.

## CP-003: completed Linux gate and ownership

The source remained `5a0b87a8`, fork remained `5a590b2`, and the tested install
overlay remained `install-3`. All direct Python module gates used the exact
`venv/bin/python` with eight xdist workers on the 32 logical CPU host. The
ordinary scope excluded `src/so101_demo_py/benchmark_test/` as required.

- `so101_demo_py/test`: 13 failed, 3760 passed, 150 skipped, 5 errors;
  nonzero exit (`so101_demo_py-2.xml`). Twelve failing assertions and five
  fixture errors rely on macOS/MPS paths or behavior while running on Linux;
  one `parallel_ipc` assertion receives a null child environment.
- `so101_teleop/test`: the complete eight-worker rerun with a 15 second
  per-test diagnostic limit finished with exit 1, 49 failed, 1006 passed,
  18 skipped (`so101_teleop-5.xml`). Six `test_unified_two_channel` cases
  timed out in the event loop, and a CMake registry check also exceeded the
  short diagnostic timeout. Many other failures assume a Darwin MPS host;
  the 49 is the diagnostic run count, not a count of confirmed product defects.
  The prior 90 second run timed out on the first two of those socket cases
  before interruption; both logs are retained.
- `mujoco_ros2_control/tests`: exit 0, 116 passed and 3 skipped using the
  CTest-provided compile and install environment values (`mujoco_ros2_control.xml`).
- Package CTest/GTest: `colcon test` exit 1 after 658 seconds, with 236
  registered tests, 22 failures, zero collection errors, and zero skips
  (`colcon-test.log`, `colcon-test-result.txt`). The 22 are one flake8
  failure in `fixed_pose_goal` (eight `Q000` messages), 15 failed test
  registrations in `so101_teleop`, and six fork launch registrations in
  `mujoco_ros2_control_tests`. All 67 `so101_gazebo_demo_cpp` registrations
  passed. All six fork launch failures waited for camera topics while the
  simulation log said sensor rendering was disabled; one registration also
  failed a pose transform assertion. These are observed boundaries, not a
  claim that every case shares one cause.
- The first fork launch test created
  `/home/matianyi/.ros/ros2_control/.venv` via its own runtime helper because
  `ROS_HOME` was unset for that original CTest run. It is retained and is an
  out-of-root deletion candidate; no cleanup was performed. Subsequent
  direct tests set `ROS_HOME` under the registered evidence root.

The `ROS_DOMAIN_ID` / `GZ_PARTITION` pairs were 231 / `so101-full-ut-linux-231`
for the initial direct gates and CTest, 232 / `so101-full-ut-linux-232` for
the interrupted 90 second diagnostic, 233 / `so101-full-ut-linux-233` for
the complete 15 second diagnostic, and 234 / `so101-full-ut-linux-234` for
the fork pytest gate. The task-owned `venv/bin/python` ran all direct pytest;
CTest used `/usr/bin/python3` with the task venv on `PYTHONPATH`. Each Linux
pytest/CTest used a unique NVMe scratch tree with the exact interpreter's
`tempfile.gettempdir()` proved inside that tree. Scratch paths and elapsed
times are in `scratch-paths.txt` and the result logs.

Retained: the full registered durable evidence root and its task-owned
detached worktree, build, install, test logs, JUnit, scratch, and tools.
Archived: none. Deletion candidates after readback: all scratch trees,
invalid build and test attempts, `/run/user/1000/so101-ut.*` IPC roots made
for these runs, and the fork helper's home venv. Nothing has been deleted.
