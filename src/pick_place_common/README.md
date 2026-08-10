# pick_place_common

`pick_place_common` is the robot-independent C++ foundation used by the Panda
and SO-101 fixed-space pick-place applications.

It exports two CMake targets:

- `pick_place_common::core` owns domain types, workflow definitions, state
  actions, transition contracts, runner behavior, plan validation, common
  resume validation, world snapshots, and simulation-session resolution.
- `pick_place_common::ros_adapters` owns the generic Gazebo attachment and
  MoveIt scene command/poll/cancel/timeout executors. It depends on `core`.

The package deliberately does not own robot motion or gripper commands,
collision geometry, contact thresholds, reset/recovery choices, launch/world
assets, URDF/SRDF, or robot configuration. Checkpoint data and validation are
shared, while each robot package retains its JSON codec and file persistence.

Validation parking is declared by each workflow rather than hard-coded by state
name. A declared postcondition pause preserves its original failure for passive
resume; an execute-only, single-use force continuation may cross only the
workflow's declared succeeded edge. Panda intentionally declares no such state.
When constructing `RunRequest`, use named extension fields (`single_step`,
`force_continue`, and `plan_only_state`) to keep positional aggregate callers
compatible.

Build and test both consumers from the workspace root:

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-up-to panda_gazebo_demo so101_gazebo_demo_cpp --symlink-install
source install/setup.zsh
PYTHONNOUSERSITE=1 colcon test \
  --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo_cpp
colcon test-result --verbose
```

For another robot, depend on this package, implement a `WorkflowDefinition`
and the required behavior/adapter policies, and reuse the exported runner and
executors. Do not copy their implementations into the consumer package.

The shared `State` enum includes the SO-101-only `WAIT_RELEASE_SETTLE` and
`VALIDATE_FINAL_PLACEMENT` identifiers, while the default workflow and transition definition keeps
them out of the Panda path. Panda state order, serialized names, and behavior remain compatible;
robot-specific physical truth, planning shadow, and final-outcome policies stay in the consumer.
