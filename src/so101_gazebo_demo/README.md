# SO-101 Gazebo Demo

The offline TCP 6D workspace sampler is documented in
[docs/so101-workspace-sampler.md](docs/so101-workspace-sampler.md).

`so101_gazebo_demo` is the self-contained SO-101 description, Gazebo, controller,
MoveIt, and geometry-tool package used by `/data/work/ws_moveit`.

## System prerequisites

Install the ROS 2 Jazzy dependencies through rosdep. The optional GUI tiling
helper additionally calls `xprop` and `xwininfo`, which Ubuntu supplies in
`x11-utils`; its native EWMH client loads `libX11` from `libx11-6`.

```bash
sudo apt-get install libx11-6 x11-utils
command -v xprop
command -v xwininfo
```

The tiling helper validates all three prerequisites before opening the X
display and reports the packages above when one is missing.

## Build and test from a ROS-only shell

Start a fresh shell that has not sourced the original SO-101 workspace:

```bash
cd /data/work/ws_moveit
source /opt/ros/jazzy/setup.zsh
rosdep check --from-paths src/so101_gazebo_demo --ignore-src
colcon build --packages-select so101_gazebo_demo --cmake-clean-cache
source install/setup.zsh
PYTHONNOUSERSITE=1 colcon test --packages-select so101_gazebo_demo --event-handlers console_direct+
colcon test-result --verbose
```

## Launch entry points

After sourcing `/opt/ros/jazzy/setup.zsh` and this workspace's
`install/setup.zsh`, the four public launch entry points are:

```bash
ros2 launch so101_gazebo_demo so101_display.launch.py
ros2 launch so101_gazebo_demo so101_controller.launch.py
ros2 launch so101_gazebo_demo so101_gazebo.launch.py
ros2 launch so101_gazebo_demo so101_moveit.launch.py
```

The display launch provides URDF/RViz inspection. The controller launch starts
the controller stack without Gazebo. The Gazebo launch starts the SO-101
pick-place world, and the MoveIt launch starts `move_group` plus RViz against
the same package-local robot description.

## Geometry calculator

The installed calculator derives the 20 mm-depth Coke pre-open and contact
angles directly from the package's binary STL triangles:

```bash
PYTHONNOUSERSITE=1 ros2 run so101_gazebo_demo gripper_preopen_calc.py
```

## GUI tiling on ai-station

Start Gazebo and RViz in their tmux-held GUI sessions first. Then load the live
GNOME display environment and place RViz on the left and Gazebo on the right:

```bash
source ~/gui-env.zsh
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_moveit/install/setup.zsh
ros2 run so101_gazebo_demo tile_ai_station_guis.py
```

## Provenance

Its Phase 1 baseline was copied from `/data/work/so101_lerobot_ws` at verified
source commit `65c371e`.

## Scope

The package is deliberately self-contained: it will install its own robot
description, simulation, controller, MoveIt, test, and helper assets without a
runtime dependency on the original workspace. Phase 1 intentionally excludes
Panda pick-place code; that migration happens separately after the SO-101
environment is proven from this workspace.

Phase 2 will copy and adapt the Panda pick-place state-machine structure for
SO-101. Shared abstractions are intentionally deferred until both robot-specific
implementations have passed their own runtime gates.

## Simulation-only Teleop Web UI

The full operator guide, Target YAML schema, workflow safety boundary and
shutdown procedure are documented in
[`docs/so101-teleop-web-ui.md`](docs/so101-teleop-web-ui.md).

The installable `so101_teleop_server.py` serves the production Vite bundle and
owns its ROS 2 worker.  It is intentionally simulation-only: it binds only to
`127.0.0.1` or a Tailscale `100.64.0.0/10` address and rejects every other
bind address.  Never use it with hardware.

Build the Web package with Bun (`bun.lock` is authoritative), then use the
single launch command in a tmux-held shell. The launch preflight builds a
missing or stale Web bundle before FastAPI starts; no persistent Vite server is
used:

```bash
cd /data/work/ws_moveit
source ~/gui-env.zsh
source /opt/ros/jazzy/setup.zsh
source install/setup.zsh
export ROS_DOMAIN_ID=<existing-simulation-domain>
export GZ_PARTITION=<existing-gazebo-partition>
command -v bun && bun --version
ros2 launch so101_gazebo_demo so101_teleop.launch.py \
  bind_address:=127.0.0.1 \
  simulation_session_id:=<new-session-id>
```

The server uses `rclpy` subscriptions/TF, MoveIt's
`/plan_kinematic_path`, `/compute_ik`, and `/execute_trajectory`, plus the
controller actions.  Browser commands require a short-lived lease, an idempotent
command id, and a non-stale plan.  The web UI treats axes 1–5 as the arm and
axis 6 as gripper opening; it never makes axis 6 a Cartesian planning target.
`Force Continue` is limited to a fresh, auditable physical-grasp
post-validation failure and is never evidence of a successful grasp.
