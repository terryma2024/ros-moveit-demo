# SO-101 Python Source Directory Layout

## Goal

Move the importable Python package implementation from
`src/so101_gazebo_demo_py/so101_gazebo_demo_py` to
`src/so101_gazebo_demo_py/src`, matching the repository's convention that implementation code lives
under a directory named `src`, without changing the public Python package name, ROS package name,
console scripts, launch files, or runtime behavior.

## Packaging design

`setup.py` will explicitly map the public package `so101_gazebo_demo_py` to the physical directory
`src`. Subpackages will remain public as `so101_gazebo_demo_py.cli`,
`so101_gazebo_demo_py.gazebo`, and so on. Package discovery must not expose those subpackages as
unrelated top-level packages.

All Python implementation files, including `__init__.py` files and `test_support`, will move as a
single tree. Configuration, launch, resource, URDF, mesh, model, RViz, world, documentation, and test
directories remain at the ROS package root.

## Compatibility

Existing imports and console-script entry points remain unchanged. Tests must import the installed
or explicitly configured public package name rather than depending on the old physical directory.
References that intentionally describe historical paths remain unchanged; active build, test, and
developer documentation references will be updated.

## Verification

The migration will use a layout contract as the RED/GREEN regression boundary: before migration it
must reject the old implementation directory and require the new `src` directory; after migration it
must pass.

Verification will then include:

- a clean package build of `so101_gazebo_demo_py`;
- the package's complete unit-test suite and `colcon test-result --verbose`;
- installed-package provenance checks for imports and ROS executables;
- launch-description loading and `--show-args` checks from the newly sourced install overlay;
- a bounded launch smoke test that confirms startup reaches its expected initialization boundary and
  exits cleanly under timeout or an explicit safe mode, without executing robot motion.

No Gazebo/MoveIt stack will be started if an existing stack is detected. Runtime and visual robot
behavior are outside this source-layout-only change unless the launch smoke test exposes a packaging
regression.
