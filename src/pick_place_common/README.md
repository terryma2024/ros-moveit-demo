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

Build and test both consumers from the workspace root:

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-up-to panda_gazebo_demo so101_gazebo_demo --symlink-install
source install/setup.zsh
PYTHONNOUSERSITE=1 colcon test \
  --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo
colcon test-result --verbose
```

For another robot, depend on this package, implement a `WorkflowDefinition`
and the required behavior/adapter policies, and reuse the exported runner and
executors. Do not copy their implementations into the consumer package.
