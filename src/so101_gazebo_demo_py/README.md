# SO-101 Gazebo Demo (Python)

`so101_gazebo_demo_py` is a standalone, simulation-only ROS 2 Jazzy rewrite of the SO-101 Gazebo pick-place demo. It owns its Python runtime, launch files, robot/world assets, policy files, Gazebo attachment transport, and MoveIt interfaces. It does not use the original C++ package or `pick_place_common` at runtime.

Build and source:

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_gazebo_demo_py --symlink-install
source install/setup.zsh
```

Safe, stack-free characterization defaults to dry-run:

```bash
ros2 launch so101_gazebo_demo_py so101_pick_place.launch.py
ros2 run so101_gazebo_demo_py pick_place_state_machine --mode plan_only --plan-only-state MOVE_ABOVE_OBJECT
```

An explicit simulation execution uses:

```bash
ros2 launch so101_gazebo_demo_py so101_pick_place.launch.py run_mode:=execute start_simulation:=true
ros2 run so101_gazebo_demo_py reset_so101_world
```

Checkpoints, private planning diagnostics, headless summaries, screenshots, and ROS logs must be written under a unique `/tmp/so101-py-*` evidence directory. The runtime is simulation-only: never connect these launch files to physical hardware.

The Gazebo path uses Harmonic's built-in DetachableJoint through `gz.transport13`. A ROS-vendor/system Gazebo ABI mismatch is a known environmental risk; the package preflight and acceptance evidence must prove the imported runtime provenance. Web teleop, workspace sampling, calibration/motion-matrix tools, video/camera/tiling helpers, and geometry-generation tools are deliberately excluded.
