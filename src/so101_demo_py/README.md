# SO-101 unified Python demo

`so101_demo_py` is the sole ROS package and runtime-resource owner for the SO-101
MuJoCo and Gazebo pick-place demos. Its import namespace is `so101_demo`, stored directly
under this package's `src/` directory.

## Launchers

After sourcing the selected install overlay, choose the simulator explicitly:

```bash
ros2 launch so101_demo_py so101_mujoco.launch.py
ros2 launch so101_demo_py so101_mujoco_pick_place.launch.py
ros2 launch so101_demo_py so101_gazebo.launch.py
ros2 launch so101_demo_py so101_gazebo_pick_place.launch.py
```

All launchers default to `run_mode:=dry_run execute:=false`. Live simulation requires the
explicit pair `run_mode:=execute execute:=true`. Select the qualified policy with
`policy_id:=light_cup_wall_pick policy_version:=v1`; the launcher fixes the backend and
never falls back to another simulator.

The Gazebo path runs the common application and reports the phase at which the policy or
controller succeeds or fails. Gazebo is not a qualification backend because it does not
provide the lossless physics-step evidence required by the MuJoCo gate.

## Evidence and lifecycle

Pass `evidence_file:=/absolute/path/result.json` for an execute launch. The common manifest
links backend evidence under the sibling `result.d` directory and records source, policy,
bundle, session, reset epoch, and the first failed phase when applicable.

MuJoCo qualification keeps two lifecycle batches separate:

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

From a shell sourced with the isolated project overlay, run:

```bash
SO101_DEMO_EXPECTED_PREFIX="$(ros2 pkg prefix so101_demo_py)" \
  src/so101_demo_py/scripts/check_fusion_contract.sh
```

The gate verifies package discovery, the installed prefix, executables, launchers, assets,
frozen policy bytes, backend boundaries, repository ownership, zero-I/O real-stub symbols,
and a clean textual diff.
