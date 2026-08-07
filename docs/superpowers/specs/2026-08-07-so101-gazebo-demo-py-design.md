# SO-101 Gazebo Demo Python Rewrite Design

**Date:** 2026-08-07
**Status:** Approved
**Reference checkout:** `/data/work/ws_moveit/.worktrees/refactor-optimization-r3`
**Reference branch and observed HEAD:** `codex/refactor-optimization-r3` at `89acb20bc6a4889ca1ed212b736d44c4f2c2de4a`, plus the preserved uncommitted R3 changes present when this design was approved

## Objective

Create a new, self-contained ROS 2 package named `so101_gazebo_demo_py` that reproduces the externally observable core behavior of `so101_gazebo_demo` in Python. The rewrite is based on the live R3 checkout, but it does not import, link, execute, or otherwise depend on the original package's C++ components or on `pick_place_common`.

The rewrite preserves the boundaries that matter to a robot operator and to downstream ROS tools: launch entry points, CLI arguments, workflow states, configuration schema, checkpoint and resume behavior, failure semantics, MoveIt planning and execution, controller feedback, Gazebo attachment, Planning Scene convergence, reset and recovery, and visible pick-place results.

## Scope

### Included

- A standalone `ament_python` package at `src/so101_gazebo_demo_py`.
- Package-owned copies of the SO-101 URDF/Xacro, meshes, Gazebo world, SRDF, MoveIt/controller configuration, RViz configuration, task-object policy, motion policy, and validation policy required by the core demo.
- Public launch entry points for display, controller, Gazebo, MoveIt, headless move_group, pick-place, and the attachment relay needed by those launches.
- Python executables for the pick-place state machine, world reset, MoveIt scene observation/update, and Gazebo attachment-state relay.
- The R3 pick-place workflow, including physical-grasp stabilization, 2 mm micro-lift, bounded retry behavior, attachment, placement, detach, scene synchronization, checkpoint/resume, plan-only, single-step, recovery, and request-scoped planning-failure diagnostics.
- Unit, contract, characterization, package, headless runtime, and GUI acceptance tests.

### Explicit non-goals

- Web Teleop and its Vite/FastAPI assets.
- Workspace sampling and workspace artifacts.
- Motion calibration and motion-matrix validation tools.
- Video capture, frame extraction, mosaics, camera-preset helpers, GUI tiling helpers, geometry-generation utilities, and other developer-only auxiliary scripts.
- Real-hardware operation. The package is simulation-only.
- Reusable abstractions shared with Panda or the original C++ package.
- Source compatibility with C++ classes. Compatibility is defined at the external behavior boundary.

## Compatibility Contract

### Package independence

`so101_gazebo_demo_py/package.xml`, `setup.py`, launch files, modules, and installed assets must not declare or perform a runtime dependency on:

- `so101_gazebo_demo`
- `pick_place_common`
- any executable or shared library installed by either package

The package may depend on ROS 2 Jazzy, Gazebo Harmonic, MoveIt 2, `ros_gz_*`, `gz.transport13`, standard Python packages supplied by Ubuntu/ROS, and the controller/action/message packages required by the public behavior.

### Public commands

The new package exposes these commands under the new package name:

```bash
ros2 launch so101_gazebo_demo_py so101_display.launch.py
ros2 launch so101_gazebo_demo_py so101_controller.launch.py
ros2 launch so101_gazebo_demo_py so101_gazebo.launch.py
ros2 launch so101_gazebo_demo_py so101_moveit.launch.py
ros2 launch so101_gazebo_demo_py so101_move_group_headless.launch.py
ros2 launch so101_gazebo_demo_py so101_pick_place.launch.py
ros2 run so101_gazebo_demo_py pick_place_state_machine
ros2 run so101_gazebo_demo_py gazebo_attachment_state_relay
ros2 run so101_gazebo_demo_py reset_so101_world
ros2 run so101_gazebo_demo_py so101_moveit_scene
```

The pick-place executable preserves the R3 arguments and exit behavior:

- `--mode dry_run|plan_only|execute`
- `--fail-at STATE`
- `--stop-after STATE`
- `--plan-only-state STATE`
- `--resume [true|false]`
- `--step`
- `--force-continue`
- `--checkpoint PATH`
- `--session-id ID`
- `--planning-diagnostics-dir PATH`
- `--object-config PATH`
- `--motion-policy PATH`
- `--validation-policy PATH`

The launch defaults remain safe: `run_mode:=dry_run` and `start_simulation:=false`.

### Workflow compatibility

The Python workflow uses the same named states and success/failure transitions as R3:

```text
IDLE
PREPARE_OPEN_GRIPPER
MOVE_ABOVE_OBJECT
DESCEND
CLOSE_GRIPPER
WAIT_GRASP_STABLE
MICRO_LIFT
WAIT_MICRO_LIFT_STABLE
VERIFY_PHYSICAL_GRASP
VALIDATION_FAILED
ATTACH_GAZEBO
ATTACH_MOVEIT
LIFT
MOVE_ABOVE_PLACE
DESCEND_TO_PLACE
OPEN_GRIPPER
DETACH_GAZEBO
DETACH_MOVEIT
SYNC_WORLD_OBJECT
RETREAT
RECOVER_LIFT_TO_SAFE_HEIGHT
RECOVER_MOVE_ABOVE_PICK
RECOVER_DESCEND_TO_PICK
RECOVER_OPEN_GRIPPER
RECOVER_DETACH_GAZEBO
RECOVER_DETACH_MOVEIT
RECOVER_SYNC_WORLD_OBJECT
RECOVER_RETREAT
DONE
ERROR
```

`VALIDATION_FAILED` remains the only force-continue state. Plan-only is limited to the motion states supported by R3. Recovery reverses only side effects already established by evidence.

### Result and failure compatibility

The Python domain model uses string enums and frozen dataclasses for state, run mode, run status, action status, failure category, failure, action result, run request, and run result. Console output remains machine-comparable with R3: state trace, current/next state, status, failure code/message/metrics, transition count, and process exit code are stable acceptance surfaces.

Checkpoint JSON and the physical-grasp sidecar preserve the R3 field names, session binding, policy fingerprint, durable-write behavior, and fail-closed resume semantics. A pending retry side effect resumes as `PHYSICAL_GRASP_RETRY_INTERRUPTED` rather than replaying an ambiguous command.

## Architecture

### Package layout

```text
src/so101_gazebo_demo_py/
├── package.xml
├── setup.py
├── setup.cfg
├── resource/so101_gazebo_demo_py
├── launch/
├── config/
├── urdf/
├── meshes/
├── worlds/
├── rviz/
├── docs/
├── so101_gazebo_demo_py/
│   ├── domain.py
│   ├── workflow.py
│   ├── runner.py
│   ├── checkpoint.py
│   ├── policy_config.py
│   ├── profile.py
│   ├── diagnostics.py
│   ├── cli/
│   │   ├── pick_place_state_machine.py
│   │   ├── reset_so101_world.py
│   │   ├── gazebo_attachment_state_relay.py
│   │   └── so101_moveit_scene.py
│   ├── motion/
│   │   ├── planner.py
│   │   ├── executor.py
│   │   ├── gripper.py
│   │   └── evidence.py
│   ├── gazebo/
│   │   ├── transport.py
│   │   ├── attachment.py
│   │   ├── observer.py
│   │   └── reset.py
│   ├── moveit/
│   │   ├── planning.py
│   │   ├── scene.py
│   │   └── robot_state.py
│   ├── grasp/
│   │   ├── stabilizer.py
│   │   ├── validator.py
│   │   ├── retry.py
│   │   └── evidence_store.py
│   └── recovery/
│       ├── policy.py
│       └── coordinator.py
└── test/
```

Each module has one ownership boundary. Domain and workflow modules contain no ROS imports. ROS/Gazebo/MoveIt calls live behind Python protocols so the state machine and failure behavior can be tested with deterministic fakes.

### Runtime data flow

1. Launch resolves package-owned assets and starts the selected ROS/Gazebo/MoveIt stack.
2. The CLI validates arguments, loads the three YAML policies, derives a policy fingerprint, and creates a `RunRequest`.
3. The runner loads or initializes checkpoint state, validates session and world readiness, and dispatches one state at a time.
4. Motion states request plans from `/plan_kinematic_path`, validate the returned trajectory, and execute through `/execute_trajectory` or the appropriate `FollowJointTrajectory` action.
5. Feedback is proven with bounded samples from `/joint_states`, tf2, controller action results, Gazebo model pose/contact state, and Planning Scene membership.
6. Gazebo and MoveIt attachment are separate side effects with separate convergence checks.
7. After each accepted transition, the checkpoint is atomically replaced. Physical-grasp retry progress is persisted before each side effect in the separate sidecar.
8. Failure dispatches the recovery path associated with the side effects actually observed, then returns a nonzero exit code unless the requested checkpoint boundary was intentionally reached.

## ROS and MoveIt Integration

`moveit_py` and `moveit.planning` are not available in the observed ai-station ROS Jazzy environment. The rewrite therefore uses `rclpy` clients directly:

- `moveit_msgs/srv/GetMotionPlan` on `/plan_kinematic_path`
- `moveit_msgs/action/ExecuteTrajectory` on `/execute_trajectory`
- `moveit_msgs/srv/GetPositionIK` on `/compute_ik` where an IK request is required
- `moveit_msgs/srv/ApplyPlanningScene` and `GetPlanningScene` for world/attached membership
- `control_msgs/action/FollowJointTrajectory` for controller-facing arm or gripper commands where R3 uses the controller action directly
- `sensor_msgs/msg/JointState` and tf2 for observed robot state

Service and action clients have explicit availability, request, result, cancellation, and convergence timeouts. A planning success code does not imply execution success. An execution result does not imply the joints, TCP, Gazebo object, or Planning Scene converged.

## Gazebo Integration and Physics Gate

Python uses the installed `gz.transport13` binding for Gazebo command, event, model-pose, and contact traffic. The SDF continues to use Gazebo Harmonic's built-in `DetachableJoint` system. The original `libso101_attachment_collision_system.so` is removed and is never loaded by the new package.

The original C++ collision system dynamically disables task-object collisions after physical attachment. Replacing this behavior is the first implementation risk gate:

1. Build the minimal Python package and launch a package-owned world with `DetachableJoint` and no custom collision plugin.
2. Establish physical contact, attach, lift, hold, detach, and settle while recording object pose, attachment state, controller/joint/TF evidence, contact behavior, and a fresh screenshot.
3. Accept the built-in path only if it is stable and preserves the pre-attach physical-grasp gate.
4. If it fails, test a package-owned Gazebo Python System Loader module that toggles collision components. The actual ROS-sourced process must import compatible `gz.sim8`; an isolated import outside the launch environment is not sufficient.
5. The observed ai-station has a system Gazebo 8.14 Python binding and a ROS vendor Gazebo 8.11 runtime that currently produce an ABI-symbol error when `gz.sim8` is imported from the ROS-sourced shell. The plan must resolve and prove the loader/runtime provenance before using this fallback.
6. If neither pure-Python path passes, stop with evidence and request a design decision. Do not load the original C++ plugin, write a new C++ plugin, permanently disable pre-attach collisions, or simulate attachment by repeatedly teleporting the object.

The fixed moving-pad penetration ceiling of `0.000800002 m`, the approximately `0.4 mm` moving-jaw retraction represented in the R3 checkout, q6 semantics, containment checks, and physical validation assertions are not relaxed to make the Python rewrite pass.

## Physical-Grasp and Retry Contract

Before Gazebo attachment, the object must be held by physical finger contact. The gate remains:

```text
WAIT_GRASP_STABLE -> MICRO_LIFT -> WAIT_MICRO_LIFT_STABLE -> VERIFY_PHYSICAL_GRASP
```

The micro-lift is 2 mm in world Z. Retry behavior allows at most five total attempts. A retry performs pre-open, descend to the saved pre-lift world Z, reclose, stable capture, micro-lift, and verification. Contact-present failures retain the reclose q6 target. Contact-missing failures tighten only that target by 1.0 mrad per retry, capped at 4.0 mrad cumulative tightening. The 6.0 mrad seating preload remains fixed. Nonretryable failures do not retry, and exhaustion preserves the fifth physical failure while adding retry metrics.

## Assets and Provenance

Assets are copied from the approved R3 checkout into the new package so it is installable and runnable without the old package. A provenance manifest records:

- reference worktree and branch
- reference committed HEAD
- files copied
- whether each source file had an uncommitted R3 delta at copy time
- SHA-256 of the copied source and destination

Generated caches, `__pycache__`, build/install/log output, screenshots, diagnostics, checkpoints, and local editor state are not committed.

## Error Handling

- Invalid CLI or YAML fails before starting side effects and returns a nonzero exit code.
- Missing ROS services/actions/topics fail with a named failure category and bounded timeout.
- Planning, plan validation, execution, controller convergence, Gazebo attachment, MoveIt scene, TF, collision, checkpoint, and resume errors remain distinct.
- All file stores use owner-only temporary files, flush and fsync, atomic `os.replace`, and owner-only final permissions.
- Diagnostics writing is best-effort and cannot replace or mask the original workflow failure.
- Cancellation is request-scoped; the rewrite must not cancel unrelated MoveIt or controller goals.
- Reset detaches Gazebo first, restores the object pose, resets the Planning Scene, returns the arm and gripper home, and proves final convergence.

## Testing Strategy

### Unit and contract tests

- Enum/string and CLI compatibility.
- Complete workflow transition table and definition validation.
- YAML schema, numeric constraints, and policy fingerprints.
- Checkpoint and sidecar atomicity, corruption behavior, session mismatch, and pending-side-effect fail-closed behavior.
- Plan validation, request-scoped cancellation, attachment event reduction, motion evidence, physical-grasp validation, retry limits, and recovery decisions.
- Launch defaults, installed asset closure, and absence of dependencies on the old packages or binaries.

### Characterization tests

For deterministic inputs, run the R3 C++ executable and Python executable separately and compare:

- state trace
- run status and exit code
- current/next state
- failure code and metrics
- checkpoint and sidecar schema
- `dry_run`, injected failure, stop-after, single-step, resume, force-continue, and plan-only behavior

The comparison harness is test-only. The installed Python package does not invoke the C++ executable.

### Runtime acceptance ladder

1. Targeted Python tests.
2. Full `colcon test --packages-select so101_gazebo_demo_py` with no failures.
3. `dry_run` full workflow and failure/recovery paths.
4. `plan_only` for every supported motion state.
5. Headless, isolated Gazebo/MoveIt execute with a unique `ROS_DOMAIN_ID`, `GZ_PARTITION`, session ID, checkpoint path, and log directory.
6. GUI execute from the newly installed package, followed by a fresh screenshot inspected by the agent.

Final execute acceptance requires mutually consistent evidence from:

- installed-package provenance
- state-machine result and exit code
- MoveIt plan and execute result
- controller result plus `/joint_states` and TCP delta
- Gazebo attachment state and task-object 6D pose
- MoveIt world/attached collision membership
- a new visual showing the actual grasp, lift, placement, release, and final scene

No single success log, test result, topic, or screenshot proves the whole demo.

## Execution and Git Boundaries

- The implementation agent runs directly on ai-station in tmux session `codex`; it must not SSH to ai-station and must not operate `codex-cua`.
- The implementation checkout is `/data/work/ws_moveit/.worktrees/refactor-optimization-r3` on `codex/refactor-optimization-r3`.
- Before every commit, inspect the full dirty state and cached diff. Stage only the files named by the current task.
- Existing R3 modifications belong to the user and must not be reset, stashed, cleaned, overwritten, or included in Python-rewrite commits.
- Long-running GUI processes use a named tmux-held shell with `~/gui-env.zsh`; the `codex` session remains the coding-control channel.
- Runtime evidence is written under a unique `/tmp/so101-py-<timestamp>/` directory, not the source tree.
- No push or merge to a protected/default branch is authorized by this design approval.

## Completion Criteria

The rewrite is complete only when all of the following are true:

1. `so101_gazebo_demo_py` builds and installs from a ROS-only Jazzy shell without building or sourcing the original demo package as a dependency.
2. Dependency and source scans prove there is no runtime import, link, executable call, or asset lookup into `so101_gazebo_demo` or `pick_place_common`.
3. All included public launches and executables are installed and pass their contract tests.
4. Characterization tests prove compatible workflow, CLI, result, failure, checkpoint, resume, and recovery behavior.
5. Package tests pass with no new failures.
6. A fresh single-stack execute run completes pick-place using the Python executable and new package assets.
7. Gazebo physics, MoveIt Planning Scene, controller/joint/TF state, and the new screenshot independently prove the expected result.
8. The original R3 dirty files remain preserved and are not included in rewrite commits.
9. Remaining differences and risks are documented precisely; no unverified claim is reported as complete.
