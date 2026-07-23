# World Reset Caller Migration Design

## Goal

Remove every active reference to the deleted `planning_scene_setup` executable. The existing world
reset flow becomes the only source of MoveIt scene setup: `reset_moveit_world` establishes the
required `table` and canonical detached Coke objects at launch, while `reset_world.sh` establishes
both Gazebo and MoveIt state for headless runs.

## Launch setup

`panda_gazebo.launch.py` replaces its `planning_scene_setup` node with a one-shot
`reset_moveit_world` node. It retains the same package, screen output, and startup position in the
launch description after `move_group`; it restores the canonical Planning Scene `table`, detaches
and upserts Coke, and never moves the robot or Gazebo world.

The table uses the former setup geometry: a `1.2 × 0.8 × 0.05 m` box in `world` at
`(0.0, 0.0, 0.75)` with identity orientation. `reset_moveit_world` fails if either required object
cannot converge, so callers cannot silently continue with a Coke-only scene.

## Headless reset

Each of these scripts already invokes `reset_world.sh` before the obsolete setup call:

- `run_pick_place_e2e.sh`
- `run_recovery_scenarios.sh`
- `run_plan_only_resume_matrix.sh`

The redundant `ros2 run panda_gazebo_demo planning_scene_setup` invocation is removed from each.
Their existing post-reset `GetPlanningScene` captures and `assert_reset_moveit_scene.py` checks
remain, so the reset script—not an unobserved setup side effect—must establish both the canonical
table and detached MoveIt Coke object.

## Failure handling

Launch fails visibly if the one-shot MoveIt reset node fails. Headless scripts already use
`set -e` and therefore fail immediately when `reset_world.sh` or either independent world assertion
fails. No compatibility alias or fallback to `planning_scene_setup` is retained.

## Verification

Add static regression coverage that rejects active `planning_scene_setup` references in the launch
file and the three headless harnesses. Extend the launch test to require `reset_moveit_world`.
Run the focused shell tests, the resetter unit tests, Python launch syntax compilation, package
build, and the affected headless static tests. Real headless runs continue to use captured Gazebo
and Planning Scene evidence after reset; the complete pick-place run must pass the `table` and Coke
required-world-object gate.
