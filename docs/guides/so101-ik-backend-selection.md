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

The backend is chosen when the solver is created. A missing or unloadable `so101_quik` package raises
`QUIK_BACKEND_UNAVAILABLE`; it does not switch to native. Unknown names raise
`IK_BACKEND_UNSUPPORTED`.

## Set up both CPU backends on a new machine

Clone the repository with `--recurse-submodules`, then run:

```bash
bash scripts/setup-so101-quik.sh --prefix "$HOME/.local/share/so101-quik"
source "$HOME/.local/share/so101-quik/activate.sh"
```

The setup supports Ubuntu 24.04 on x86_64 and macOS on Apple Silicon. It downloads
its pinned `uv`, CPython and Eigen dependencies, installs the pinned Python
packages, and compiles both kernels. Ubuntu prepares missing compiler, curl and
certificate packages through `apt-get`; this step requires root or `sudo`.
Mac uses the installed Apple toolchain and its active SDK. If that toolchain is
missing, the script opens Apple's installer and stops. Complete the OS installation
and rerun the command.

The prefix must be empty or owned by this setup. A source checkout, symbolic-link
prefix or nonempty unrelated directory is rejected. Downloads, Python, headers,
source copies, wheels and logs stay under the prefix. Builds leave the checkout
untouched. The standalone environment provides CPU IK; use the project's existing
ROS and simulator installers to prepare a complete robot application.

`scripts/so101-quik-bootstrap.lock.env` pins `uv` 0.12.23, managed CPython 3.11.15
on Mac and 3.12.13 on Linux, Eigen 3.4.0, setuptools 79.0.1, wheel 0.45.1,
typing_extensions 4.15.0, PyYAML 6.0.2 and CMake 3.31.6. The existing
`config/ik/requirements.lock` supplies NumPy 2.4.6 on Mac and 1.26.4 on Linux.
The `uv` and Eigen archives have committed SHA256 checks. Python downloads use
the pinned `uv` release's managed-Python metadata. The Python package index
defaults to the TUNA mirror; `--index URL` selects another index. Mirror proxy
exclusions apply only to the setup process.
The `uv` download tries Astral's official release host first, with GitHub as a
fallback. Both use the same pinned checksum. Archive transfers have connection,
total-time and stalled-transfer limits; an unavailable download stops setup.

Setup builds and installs `so101-quik==0.1.0` first, then `so101_demo_py`. The demo
declares this dependency in both `package.xml` and its Python distribution metadata.
Installation finishes by importing both installed kernels and solving two pose
targets from the zero joint seed. Canonical FK checks the original 2 mm position,
0.10 rad orientation and 0.002 rad joint-margin gates. `manifest.json` records
source hashes, versions, compiler, installed artifact hashes and solve results.
Rerunning the same command checks those artifacts and repeats the solves. Changed
sources or pins require a fresh prefix; corrupted artifacts fail explicitly.

## Build into an existing ROS workspace

To use an existing ROS Python, pass its executable explicitly. Dependencies are
installed into a private virtual environment derived from that interpreter:

```zsh
bash scripts/setup-so101-quik.sh \
  --prefix "$HOME/.local/share/so101-quik-ros" \
  --python /opt/ros/jazzy/.venv/bin/python
```

For the ROS package build, source the normal ROS underlays and use their Python
and `colcon`. Source the generated header/build settings before building:

```zsh
source "$HOME/.local/share/so101-quik-ros/build-env.sh"
colcon build --packages-up-to so101_demo_py \
  --cmake-args -DPython3_EXECUTABLE=/opt/ros/jazzy/.venv/bin/python
source install/local_setup.zsh
```

This setup does not install into a shared ROS runtime. Keep its existing Python
dependencies consistent with `config/ik/requirements.lock` and the project
dependency configuration. The standalone `activate.sh` and the ROS workspace's
`local_setup.zsh` serve their respective environments.

## Manual build

A normal demo build now includes the independent `so101_quik` dependency. Use
Eigen **3.4.0** with its CMake package configuration:

```zsh
export Eigen3_DIR=/usr/share/eigen3/cmake
colcon build --packages-up-to so101_demo_py
source install/local_setup.zsh
```

On Mac, use the private `Eigen3_DIR` generated by setup. The build requires the
exact Eigen version in CMake and checks it at compile time; Eigen 5.x is not
accepted. Use the project's fixed ROS Python and normal dependency underlays.
The former `SO101_BUILD_QUIK` and `SO101_EIGEN_INCLUDE_DIR` options are no longer
used. Building only the new package uses `colcon build --packages-select so101_quik`.

`src/so101_quik/config/quik.lock.json` pins the upstream commit, local weighted header, source
hashes, Eigen version and compiler flags. The build verifies the vendored sources.
`config/ik/requirements.lock` continues to pin NumPy separately for Mac and Linux.
The QuIK package retains its AGPL-3.0-only license and unchanged source notice under
`src/so101_quik/third_party/quik/`; the default project-owned solver remains available.

## Independent QuIK package

`so101_quik` owns the vendored sources and one shared C++ library. It exports the
CMake target `so101_quik::core` and header `<so101_quik/c_api.h>`. Python consumers
call `so101_quik.load_native_library()` to get the same C ABI and its installed
artifact path. The Python loader uses the standard library and does not import
ROS, NumPy or the demo.

The demo keeps URDF-to-DH conversion, angle normalization, context serialization
and canonical FK acceptance checks. It calls the package in the same process;
there is no ROS service round trip. See [the package README](../../src/so101_quik/README.md)
for downstream C++ and Python examples and buffer ownership.

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
