# DESCEND Cartesian Planner and Executor Design

## Scope

This phase implements the `DESCEND` action only. A successful execution validates and checkpoints
`DESCEND -> CLOSE_GRIPPER`. The `CLOSE_GRIPPER` executor remains intentionally unregistered, so an
unbounded execute workflow is expected to fail there. `stop_after:=DESCEND` remains a successful
checkpoint boundary.

## Architecture

Add a standalone `DescendPlannerExecutor` implementing both `IStatePlanner` and `IStateExecutor`.
It owns its own `MoveGroupInterface`, accepts the shared `PickPlaceTargetPolicy`, and supports only
`DESCEND -> CLOSE_GRIPPER`. It is registered independently from `MoveAboveObjectPlanner`, keeping
ordinary point-to-point pre-grasp planning separate from constrained Cartesian descent.

The planner calls the current MoveIt `computeCartesianPath` overload with one target waypoint,
`avoid_collisions=true`, and configurable `descend_eef_step`. ROS 2 Jazzy's deprecated overload
ignores its `jump_threshold` argument, so `descend_joint_jump_threshold` is enforced explicitly by
checking the absolute change of every joint between every adjacent trajectory point. The default
threshold is `0.2` radians and must be positive.

The returned path is accepted only when all of these conditions hold:

- Cartesian fraction is finite and at least `descend_min_fraction` (default `0.99`).
- The joint trajectory is nonempty.
- No adjacent joint change exceeds `descend_joint_jump_threshold`.
- FK for each trajectory point is available for the configured TCP link.
- The path does not rise and its lateral displacement remains within `tcp_position_tolerance`.
- TCP orientation remains within `tcp_orientation_tolerance_rad` of the DESCEND target.
- The final TCP 6-DoF pose reaches the DESCEND target tolerances.

`MoveGroupInterface` sends the configured velocity and acceleration scaling factors in the
`GetCartesianPath` request. The move_group server, which owns the configured joint limits,
time-parameterizes the returned trajectory. The client verifies that timestamps strictly increase
and the final timestamp is positive. It does not repeat time parameterization against a second,
potentially incomplete local RobotModel. Partial or un-timed Cartesian paths are never executed.

## Transition contract

`DescendToCloseGripperValidator` is the state-bound validator for this action and for resuming its
checkpoint. Its precondition requires a fresh, stationary observation; a safely open gripper; Coke
detached in both Gazebo and MoveIt; required Planning Scene objects; cross-world Coke consistency;
and the current TCP 6-DoF pose within the `MOVE_ABOVE_OBJECT -> DESCEND` target tolerance.

Its postcondition requires successful execution, a fresh and stationary result, the gripper still
open, Coke still detached and cross-world consistent, the actual TCP at the
`DESCEND -> CLOSE_GRIPPER` target, and Gazebo Coke position and orientation drift within the
configured tolerances. The same validator is used by `validateResume`, preserving the architecture
rule that transition completion and resume validation share one contract.

## Observability

The planner/executor logs these INFO records:

- `TARGET_TCP_POSE`
- `CARTESIAN_FRACTION`
- `PLANNED_END_TCP_POSE`
- `EXECUTED_END_TCP_POSE`

The runner receives an optional generic execution-observation sink. It emits the already captured
pre- and post-action snapshots without taking additional observations. The ROS node provides a sink
that logs `COKE_POSE_BEFORE` and `COKE_POSE_AFTER` as Gazebo 6-DoF poses for every executed step.
This keeps the runner independent of `DESCEND` while ensuring the requested real-world evidence is
recorded.

## Configuration and registration

Declare and validate:

- `descend_eef_step = 0.005` metres, positive.
- `descend_min_fraction = 0.99`, in `(0, 1]`.
- `descend_joint_jump_threshold = 0.2` radians, positive.

All three values participate in the checkpoint configuration hash. Register the DESCEND planner for
`plan_only` and `execute`; register its executor only for `execute`. Keep `CLOSE_GRIPPER`
unregistered.

## Verification

Unit tests cover Cartesian summary validation, including fraction, empty trajectory, joint jumps,
lateral/rising motion, orientation, and endpoint errors. Transition tests cover the added DESCEND
precondition and postcondition semantics. Runner tests cover the intended boundary at
`CLOSE_GRIPPER` and successful `stop_after:=DESCEND`. Then build the package, run the full package
test suite, and run read-only `ament_uncrustify`. If the simulator is available, verify the three
requested checkpoint/resume commands; otherwise report that runtime verification was unavailable.
