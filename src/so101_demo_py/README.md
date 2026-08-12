# SO-101 unified Python demo

`so101_demo_py` is the sole implementation and runtime-resource owner for the SO-101
MuJoCo and Gazebo pick-place demos. The old `so101_mujoco_demo_py` and
`so101_gazebo_demo_py` packages are deprecated compatibility forwarders only.

## Launchers

After sourcing the selected install overlay, the four supported simulator launchers are:

```bash
ros2 launch so101_demo_py so101_mujoco.launch.py
ros2 launch so101_demo_py so101_mujoco_pick_place.launch.py
ros2 launch so101_demo_py so101_gazebo.launch.py
ros2 launch so101_demo_py so101_gazebo_pick_place.launch.py
```

All launchers default to `run_mode:=dry_run execute:=false`. Live simulation requires the
explicit pair `run_mode:=execute execute:=true`. Select a policy with
`policy_id:=light_cup_wall_pick policy_version:=v1`; backend selection is fixed by the
launcher and never falls back to another backend.

The Gazebo path exercises the common application and reports its natural policy or
controller result, but it is not a qualification backend because it cannot provide a
lossless physics-step trace. A valid Gazebo `FAILED` result is evidence of a real execution
boundary, not a skipped run and not MuJoCo qualification evidence.

## Evidence and lifecycle

Pass `evidence_file:=/absolute/path/result.json` for an execute launch. The common manifest
links backend evidence under the sibling `result.d` directory and records source, policy,
bundle, session, reset epoch, and the first failed phase when applicable.

MuJoCo qualification uses two separate lifecycle batches:

- `FULL_RESTART`: every counted run owns an independent simulator/ROS stack.
- `RESET_WORLD`: one owned stack is reset to a newly observed epoch between counted runs.

Results from one lifecycle never count toward the other lifecycle's denominator.

## Real-arm boundary

`real_stub` parses only the committed fail-closed safety mapping. It has no launcher and
performs no device discovery, serial/socket access, ROS control I/O, planning, execution,
gripper command, reset, stop, or recovery. Every operation returns
`REJECTED / REAL_HARDWARE_NOT_CONFIGURED`. Real hardware enablement requires a separate
safety design and implementation.

## Static acceptance gate

From a shell already sourced with `install/fusion-final/setup.*`, run:

```bash
src/so101_demo_py/scripts/check_fusion_contract.sh
```

The gate verifies package and test discovery, the exact final install prefix, installed
executables/launchers/assets/policies, frozen policy bytes, backend boundaries, legacy
ownership removal, zero-I/O real-stub symbols, and a clean textual diff.
