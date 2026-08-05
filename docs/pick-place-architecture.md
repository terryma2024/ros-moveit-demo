# Shared pick-place architecture

The dependency direction is one-way:

```text
panda_gazebo_demo ─┐
                   ├─> pick_place_common::ros_adapters ─> pick_place_common::core
so101_gazebo_demo ─┘
```

`pick_place_common::core` owns the robot-independent domain model, workflow
interface, runner, state-action and transition contracts, plan validation,
common resume validation, world snapshot model, and simulation session ID.
`pick_place_common::ros_adapters` owns the generic Gazebo attachment and MoveIt
scene executors, including validation, cancellation, polling, timeout, and
convergence checks.

Each robot package owns its `WorkflowDefinition`, runner behavior and operation
policies, motion and gripper implementation, geometry/contact/reset/recovery
policy, concrete ROS/Gazebo/MoveIt adapters, and launch/world/URDF/SRDF/config
assets. SO-101 Teleop is also robot-specific. Compatibility headers in the
robot include trees may expose aliases or thin wrappers, but contain no copied
workflow or executor algorithm.

Checkpoint schema v3 types and common resume rules live in the common core.
Panda preserves `configuration_hash`; SO-101 preserves
`policy_bundle_sha256`. Their JSON codecs, file stores, and persistence paths
remain local because those are robot application boundaries.

New robot consumers should link the exported targets and provide a
`WorkflowDefinition` plus explicit policies. `IRunnerBehaviorPolicy` names the
runner's execute preflight, observation-recovery, environment-failure,
transient-observation retry, resume-settling, original-failure preservation,
pre/postcondition retry, and trace decisions; `DefaultRunnerBehaviorPolicy`
is the characterized Panda baseline. A new consumer must not copy the runner,
domain/state-action implementation, or Gazebo/MoveIt executor sources.

The full automated gate is:

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-up-to panda_gazebo_demo so101_gazebo_demo \
  --symlink-install --cmake-clean-cache
source install/setup.zsh
PYTHONNOUSERSITE=1 colcon test \
  --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo \
  --event-handlers console_direct+
colcon test-result --verbose
```
