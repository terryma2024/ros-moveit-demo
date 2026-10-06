# SO-101 IK backend selection

The project keeps its native CPU solver and weighted QuIK behind the same pose IK
interface. The default is `native`. Selecting `quik` uses the frozen solver with
orientation weight `0.08`; the position, orientation and joint-limit acceptance
gates remain the same.

## Select a backend

The `dynamic_cup_pick_place` and `task_reachability` commands accept
`--ik-backend native` or `--ik-backend quik`. An explicit argument takes precedence
over `SO101_IK_BACKEND`; an unset environment variable selects `native`.

Set `SO101_IK_BACKEND=quik` in a service or batch owner's launch environment to
select QuIK for its children. The fixed Mac launcher and parallel worker allocator
retain this variable. Reachability preflight and dynamic MuJoCo execution resolve the
same backend. Runtime evidence records the actual solver and artifact hashes.

This switch selects the project's CPU pose IK. The legacy `plan_only` path sends
pose goals to MoveIt and uses MoveIt's configured IK plugin.

The backend is chosen when the solver is created. A missing QuIK module raises
`QUIK_BACKEND_UNAVAILABLE`; it does not switch to native. Unknown names raise
`IK_BACKEND_UNSUPPORTED`.

## Build the optional QuIK module

A normal build includes the existing native kernel. To install both kernels, use
Eigen **3.4.0** and enable the QuIK extension:

```zsh
export SO101_EIGEN_INCLUDE_DIR=/usr/include/eigen3
SO101_BUILD_QUIK=1 colcon build --packages-select so101_demo_py
source install/local_setup.zsh
```

On Mac, set `SO101_EIGEN_INCLUDE_DIR` to an Eigen 3.4.0 include directory containing
`Eigen/Core`. The build checks the version at compile time; Eigen 5.x is not
accepted. Use the project's fixed ROS Python and normal dependency underlays.

`config/ik/quik.lock.json` pins the upstream commit, local weighted header, source
hashes, Eigen version and compiler flags. The build verifies the vendored sources.
`config/ik/requirements.lock` continues to pin NumPy separately for Mac and Linux.
The QuIK component retains its AGPL-3.0-only license and source notice under
`third_party/quik/`; the default project-owned solver remains available.

## Shared Python interface

Create either solver through
`so101_demo.control.moveit.pose_ik.create_pose_ik(urdf_path, joint_names, root_link,
tip_link, backend="native")`, changing the backend to `"quik"` to select QuIK.
Both expose:

- `solve(target, seed, *, position_tolerance_m=0.002, orientation_tolerance_rad=0.10)`
  returning a tuple of five joint angles in radians.
- `forward(positions)` returning `PoseEvidence`, and `forward_positions(vectors)`
  returning TCP positions.
- `joint_limits` and `orientation_error_rad(actual, target)`.

The QuIK adapter uses canonical project FK to check every accepted solution. It
normalizes only equivalent angles separated by whole turns; it does not clip a
solved pose into the limits. Invalid seed length uses `DYNAMIC_IK_SEED_INVALID`;
unacceptable candidates use `DYNAMIC_IK_RESIDUAL_EXCEEDED`. Each QuIK instance owns
a native context and serializes concurrent calls to that context.

The algorithms can return different joint angles or reject different targets.
The frozen twenty-point comparison passed 20/20 complete IK prefixes with native
and 18/20 with weighted QuIK. QuIK rejected P18 and P19 at waypoint 6 of
`MOVE_ABOVE_OBJECT`. Backend selection preserves these outcomes and gates; it does
not qualify QuIK for those points or establish a physical grasp result.
