# Panda fixed-space pick-place verification

The workflow engine is provided by `pick_place_common`. This package owns the
Panda workflow definition and policies, checkpoint JSON codec and file store,
motion and gripper behavior, concrete Gazebo/MoveIt adapters, collision
geometry, reset/recovery policy, launch files, and robot configuration. It
links `pick_place_common::core` and `pick_place_common::ros_adapters`; the
compatibility headers under this package's include path forward shared types.

See [`../../docs/pick-place-architecture.md`](../../docs/pick-place-architecture.md)
for the ownership boundary and extension rules.

Build and source the workspace before running the headless checks:

```bash
colcon build --packages-up-to panda_gazebo_demo --symlink-install
source install/setup.bash
```

Run one complete workflow, or the required three consecutive acceptance runs:

```bash
src/panda_gazebo_demo/test/headless/run_pick_place_e2e.sh --runs 1 --label smoke
src/panda_gazebo_demo/test/headless/run_pick_place_e2e.sh --runs 3 --label acceptance
```

Run all three attachment-fact recovery scenarios:

```bash
src/panda_gazebo_demo/test/headless/run_recovery_scenarios.sh
```

Run the cross-process plan-only/resume matrix for every forward motion and
each carrying-recovery motion:

```bash
src/panda_gazebo_demo/test/headless/run_plan_only_resume_matrix.sh
```

The scripts create an isolated `ROS_DOMAIN_ID` and `GZ_PARTITION`, own a launch
process group, and terminate only that group. Evidence is retained under
`build/panda_gazebo_demo/test_logs/`. A successful normal run requires the
ordered forward workflow to reach `DONE`, every motion plan to carry complete
trajectory evidence, the final gripper to be open, both Gazebo and MoveIt to be
detached, and the Gazebo and MoveIt Coke poses to agree near
`(0.30, 0.20, 0.836)`. The scripts independently assert the final Gazebo pose,
attachment state, `/joint_states`, and MoveIt Planning Scene snapshot; saved
files are not treated as evidence unless those assertions pass.

Recovery verification establishes each attachment combination through real
forward execution, converts the resulting schema-v3 checkpoint to recovery
phase, and resumes against current world facts. RecoveryPolicy must reclassify
those facts instead of trusting the checkpoint's next-state hint. Recovery
finishes in the expected `ERROR` terminal while preserving the injected
original failure, after safely opening/detaching/synchronizing/retreating. A
carried Coke must first return to the pick surface.

The plan-only/resume matrix wraps two independent plan-only processes with
joint, Gazebo Coke 6DoF, durable attachment, and MoveIt Planning Scene
snapshots. It also compares both processes' observed `START_TCP_POSE`, requires
complete finite plan evidence, rejects execute evidence, and proves the schema
v3 checkpoint remains byte-identical. Recovery motion coverage uses an explicit
headless fault fixture: `attach_and_lift_demo` first lifts the attached Coke by
30 mm, then shifts it by -30 mm in world y at the lifted height. This creates a
real low carrying state away from the support surface, allowing fact-driven
resume to exercise lift, move-above-pick, and descend in separate processes.
The fixture's `lateral_offset_y` defaults to zero, is finite/range checked, and
does not change the demo's legacy single-lift behavior unless explicitly set.

`stop_after` accepts any non-terminal forward or recovery action. It rejects
`IDLE`, `DONE`, and `ERROR`; `fail_at` remains restricted to forward actions in
`dry_run` mode.

Gazebo Sim 8's DetachableJoint output is event-driven. The launch-lifetime
`gazebo_attachment_state_relay` validates raw events on
`/panda/coke_attached_event`, enforces the initial safe detach, and publishes
fresh durable state on `/panda/coke_attached`. It publishes nothing while the
state is unknown. `reset_world.sh` actively requests Gazebo detach, resets the
physical Coke pose, invokes `reset_moveit_world` to detach and synchronize the
Planning Scene Coke, and verifies durable Gazebo detach before initializing the
arm and gripper. `EXPECTED_COKE_DETACHED=true` may supply already-validated
initial evidence, but never skips the detach command, MoveIt reset, or final
Gazebo validation.

Key safety parameters are explicit and configuration-hashed. In particular,
`motion_start_joint_tolerance` defaults to `0.010 rad`: every motion plan records
its named start joints, validation compares them with the pre-plan observation,
and execution rereads MoveIt state immediately before sending the trajectory.
`joint_velocity_tolerance` and all configured gripper limits are injected into
MoveIt observation and recovery no-op decisions. `recovery_safe_height` defaults
to `0.987 m`, may not be configured lower, and recovery lift targets never move
down from an already higher observed TCP pose.

The fixed target policy also owns the single TCP-to-supported-Coke center offset.
Forward completion and recovery release therefore derive the expected pick/place
Coke pose from the same dynamic target policy and require both absolute position
and upright 6D orientation.
