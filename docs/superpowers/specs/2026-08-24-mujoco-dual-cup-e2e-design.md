# MuJoCo dual cup pick-place end-to-end validation design

**Date:** 2026-08-24

**Scope:** `fixed_cup_pick_place` and `dynamic_cup_pick_place` in local MuJoCo only

**Evidence root:** `/Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/<run-id>/`

## 1. Objective

Demonstrate one complete, physically successful MuJoCo pick-place run for each public executable:

- `fixed_cup_pick_place`: V1 consumes the configured fixed cup pose and qualified motion policy.
- `dynamic_cup_pick_place`: V2 consumes a fresh valid `/cup_pose`, derives the pick strategy at runtime, and never falls back to the V1 pose.

This is a two-run end-to-end demonstration, not a repeated-run stability qualification. Gazebo is explicitly out of scope.

## 2. Success contract

Each executable passes only when all of the following evidence layers agree:

1. **Input/provenance:** installed executable, source checkout, ROS domain, MuJoCo session ID, reset epoch, policy or perceived pose, and runtime dependencies are recorded.
2. **Workflow:** the executable exits zero, reaches `DONE`, and records the complete expected state/phase trace without a failed phase.
3. **Commanded motion:** arm and gripper controllers remain active, and fresh joint/TCP evidence changes consistently with descent, grasp, lift, transport, release, and retreat.
4. **Physical outcome:** MuJoCo evidence proves that the cup leaves the pick region with the gripper, is released at the place region, is upright, table-supported, stable, and no longer in fingertip contact.
5. **Planning Scene convergence:** the cup follows the attach/detach lifecycle and ends detached as a world object.
6. **Independent visual evidence:** fresh MuJoCo viewer screenshots visibly show an in-motion grasp/descent, cup transport, and the final released cup. Black, stale, hidden, or headless screenshots are invalid.

Failure in any layer makes the run fail. Missing provenance, duplicate stacks, mismatched session/reset epoch, or unavailable visual capture makes the run invalid rather than successful.

## 3. Runtime topology

Both variants use the same ROS 2, MoveIt, controller, MuJoCo, Planning Scene, and physical validation stack. The strategy-input boundary is the intended variable.

```text
fixed_cup_pick_place                 dynamic_cup_pick_place
        |                                      |
fixed pose + qualified YAML              fresh /cup_pose
        |                                      |
        +---------- strategy parameters -------+
                           |
                  shared StateMachineRunner
                           |
        MoveIt planning / trajectory and gripper control
                           |
                mujoco_ros2_control + MuJoCo
                           |
          atomic physical and Planning Scene evidence
```

The dynamic test-only bridge publishes `/cup_pose` from the current MuJoCo cup state. It is an observation adapter only: it must not move the cup, command the robot, or inject a hard-coded fallback pose.

## 4. Isolation and environment

- Use a unique `ROS_DOMAIN_ID` and session ID for each stack.
- Confirm no competing `move_group`, MuJoCo `ros2_control_node`, or pick-place executable before launch.
- Source the local ROS/Jazzy environment and repository overlay through `direnv`.
- On macOS, ensure the pinned `mujoco_ros2_control` fork is first in `AMENT_PREFIX_PATH` while `so101_demo_py` still resolves from this repository install.
- Give ordinary runtime logs a unique `/tmp/so101-debug-<task-id>/` root.
- Retain qualified outputs only under the registered persistent evidence root.
- A native GUI run requires an unlocked, visible macOS desktop session. A locked session is an environment blocker, not a workflow failure.

## 5. Fixed-position run

### Input boundary

V1 must identify the installed fixed motion/contact policy and retain their hashes or paths. The initial MuJoCo cup must match the configured fixed pick assumptions.

### Expected workflow

The qualified fixed workflow must complete its nine phases and produce its live runtime manifest plus release/retreat artifact.

### Acceptance

- CLI exits `0` with `status=DONE`.
- Every phase artifact exits `0` and the manifest has no `failed_phase` or `failure`.
- Final cup is inside the configured place target and passes the stability, support, upright, and no-gripper-contact gates.
- `plastic_cup` is detached and present in the world Planning Scene.
- All required controllers remain active.
- Descent, transport, and final screenshots are visually inspected and retained.

## 6. Dynamic-position run

### Perception contract

Before the state machine starts, V2 waits up to `cup_pose_timeout_s` for `/cup_pose` (`geometry_msgs/msg/PoseStamped`). A valid sample requires:

- non-empty `header.frame_id`;
- finite position and quaternion components;
- non-zero quaternion norm;
- an allowed frame/transform path to the planning frame;
- a sample fresh enough for this run.

Invalid samples are reported and ignored while listening continues. Timeout is terminal. No V1 pose or hard-coded pose may be substituted.

### Strategy derivation

The accepted perceived pose is normalized/transformed, recorded, and converted into dynamic approach, grasp, lift, place, and retreat parameters. The executable then uses the same state-machine lifecycle as V1, with the dynamic execute path providing segmented trajectory execution, underactuated IK, narrowly scoped collision allowances, and physical grasp/release gates.

### Acceptance

- The retained manifest records the accepted `/cup_pose` and derived strategy.
- The state trace is exactly:
  `IDLE -> PREPARE_OPEN_GRIPPER -> MOVE_ABOVE_OBJECT -> DESCEND -> CLOSE_GRIPPER -> WAIT_GRASP_STABLE -> MICRO_LIFT -> WAIT_MICRO_LIFT_STABLE -> VERIFY_PHYSICAL_GRASP -> ATTACH_MOVEIT -> LIFT -> MOVE_ABOVE_PLACE -> DESCEND_TO_PLACE -> DETACH_MOVEIT -> OPEN_GRIPPER -> WAIT_RELEASE_SETTLE -> VALIDATE_FINAL_PLACEMENT -> SYNC_WORLD_OBJECT -> RETREAT -> DONE`.
- CLI exits `0`; the final physical, Planning Scene, controller, and visual gates match the fixed-run standard.
- Evidence proves V2 used the topic-derived pose and did not load the V1 fixed-pose strategy.

## 7. Visual evidence protocol

For each executable, capture at least:

- `in-motion-descent.png`: robot actively approaching or closing around the cup;
- `transport.png`: cup visibly lifted and transported with the gripper;
- `final.png`: cup visibly released at the place marker with the gripper retreated.

Each screenshot must be fresh for the same session and manually inspected. The final screenshot alone is insufficient because it cannot prove the transport path. A screenshot is rejected if the desktop is locked, the image is black, the viewer is obscured, or the robot/cup relationship is not visible.

## 8. Evidence layout

```text
<run-id>/
  experiment-ledger.md (or repository ledger reference)
  exp-004/                    # fixed successful run
    workflow.log
    final-readback.log
    fixed-run/
    screenshots/
  exp-006/                    # dynamic headless numeric success
    headless-dynamic/
  exp-007/                    # failed GUI diagnostic and retreat defect
    dynamic-run/
    screenshots/
  exp-008/                    # accepted dynamic GUI run
    dynamic-run/
    screenshots/
    controllers.log
  final-verification/
    pytest.log
    colcon-build.log
    executables.log
    git-diff-check.log
    sha256.txt
```

The headless dynamic success is retained as strong numeric/runtime evidence, but it does not satisfy the independent visual gate by itself. A later GUI run is accepted only when it reaches `DONE`; a physically placed cup with a failed final retreat remains a failed workflow.

## 9. Final verification and reporting

After both demonstrations:

1. Run the complete `so101_demo_py` test suite with an isolated `ROS_LOG_DIR`.
2. Rebuild the package with `colcon build --packages-select so101_demo_py --symlink-install`.
3. Re-source the installed overlay and prove both public executable names through `ros2 pkg executables so101_demo_py`.
4. Run `git diff --check` and record the dirty-worktree scope without modifying unrelated changes.
5. Generate SHA-256 hashes and sizes for retained final evidence.
6. Update the experiment ledger with valid, failed, invalid, and blocked attempts; never promote a diagnostic attempt to success.
7. Report retained runs, archived runs, and deletion candidates. Do not delete evidence without explicit authorization.

## 10. Stop conditions

Stop and report rather than weakening the acceptance criteria when:

- the desktop remains locked and visual evidence cannot be captured;
- a required runtime dependency or controller cannot be restored safely;
- the topic pose is missing, invalid, stale, or untransformable;
- either workflow or physical outcome gate fails;
- provenance cannot be tied to the installed overlay and registered session.
