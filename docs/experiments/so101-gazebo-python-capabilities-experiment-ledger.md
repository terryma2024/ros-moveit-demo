---
task_id: so101-gazebo-python-capabilities
goal: >-
  Implement and validate manifest-driven Gazebo Python Planning Scene, package-owned
  camera presets, complete transactional reset, and five final MuJoCo FULL_RESTART wins.
worktree: /data/work/ws_moveit/.worktrees/so101-demo-py-canonical
branch: codex/so101-demo-py-canonical
approved_base: 1fa155e1524fc24b7059e76eb88540abda327ba6
design_commit: fccb1a49
evidence_root: /tmp/so101-debug-gazebo-python-capabilities-boWK6J
frozen_policy:
  path: src/so101_demo_py/config/policies/light_cup_wall_pick/v1/mujoco.yaml
  sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
live_state_values: [PLANNED, RUNNING, VALID, INVALID]
---

# SO-101 Gazebo Python Capabilities Experiment Ledger

## Success contract

- Planning Scene apply and independent read-back prove table/pedestal/plastic_cup primitive counts `1/1/13`, canonical 6D poses, world membership, and no unexpected attachment.
- Gazebo camera preset receives positive `/gui/move_to/pose` acknowledgement and an inspected fresh before/after GUI snapshot pair proves a real viewpoint change.
- After deliberate arm and cup disturbance, full reset independently proves Gazebo pose/attachment, MoveIt pose/membership/attachment/`1/1/13`, active controllers, arm/gripper joint positions and velocities, TF, and visual convergence.
- The final committed source, installed bundle, frozen policy, and fixed geometry contract achieve five consecutive independent qualified MuJoCo `FULL_RESTART` successes.
- A valid failed outcome stops a qualification sequence. An invalid experiment stops its batch. Historical successes do not count.

## Immutable safety boundary

- Direct execution on `AI-STATION-001`; SSH to self is forbidden and has not been used.
- No push, merge, main modification, other-worktree cleanup, real-arm operation, broad `pkill`, `gh`, or `ament_uncrustify --reformat`.
- Do not invoke, wrap, or read runtime executable/configuration from `so101_gazebo_demo_cpp`.
- Stop only task-owned PIDs recorded by an experiment. Preserve all pre-existing tmux sessions and unrelated processes.

## CP-GZPY-001 — Verified baseline

status: VALID  
outcome: BASELINE_ACCEPTED  
recorded_at: 2026-08-13 Asia/Shanghai

### Provenance

- Host: `AI-STATION-001`
- Target worktree: `/data/work/ws_moveit/.worktrees/so101-demo-py-canonical`
- Target branch: `codex/so101-demo-py-canonical`
- Initial target HEAD: `1fa155e1524fc24b7059e76eb88540abda327ba6`
- Design commit: `fccb1a49`
- Target status before task changes: clean
- Git common dir: `/data/work/ws_moveit/.git`
- Submodule gitlink: `738e304551b4ea6db020b466086a13db71b65607` (uninitialized and preserved)
- Main worktree: `/data/work/ws_moveit`, branch `main`, HEAD `072541a0e537080c3f2abf3945a156b26d06f48d`, clean
- `origin/main`: `072541a0e537080c3f2abf3945a156b26d06f48d`
- Origin: Gitee (`git@gitee.com:zjumty/ros-moveit-demo.git`)
- Frozen MuJoCo policy SHA-256: `aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356`

### Preserved runtime state

- Existing tmux sessions: `MNT-Q-RESET-EXP136-140`, `codex`, `codex-cua`, `so101-mujoco-gui`
- No exact running Gazebo, MoveIt, ros2_control, RViz, or robot-state-publisher process at baseline.
- Baseline ROS graph had no nodes and only `/parameter_events`, `/rosout` topics.
- These sessions and unrelated state are outside task ownership and must remain untouched.

### Baseline evidence

- `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/baseline-audit.log`
- `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/host-runtime-audit.log`
- `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/baseline-so101-demo-py-installed-tests-corrected.log`
- Installed-baseline `so101_demo_py` suite: `97 passed`.

### Rejected invocations and disproven routes

- Unsourced direct pytest could not import the installed canonical package; it is an invalid test invocation, not a product failure.
- A run with default `~/.ros` logging failed under the workspace sandbox; all subsequent test/live commands set a task-specific `ROS_LOG_DIR`.
- The complete baseline Teleop suite collected `214` tests but hung after `119`; the task will run affected focused/package tests and will not silently classify that unrelated baseline hang as a feature failure.
- Whole-tree Ruff reported `196` pre-existing errors and is not the repository's scoped gate. Ruff will cover `so101_demo_py` plus touched Teleop Python files, without auto-formatting.

## Live experiment queue

No live experiment has started. The next live experiment must be appended here with an immutable hypothesis and acceptance contract in `PLANNED` before any simulator command is run. Its state must then transition `PLANNED -> RUNNING -> VALID|INVALID`.
