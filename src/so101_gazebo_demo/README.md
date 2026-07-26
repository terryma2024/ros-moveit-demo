# SO-101 Gazebo Demo

`so101_gazebo_demo` is the self-contained SO-101 description, Gazebo, controller,
and MoveIt package used by this workspace.

## Provenance

Its Phase 1 baseline was copied from `/data/work/so101_lerobot_ws` at verified
source commit `65c371e`.

## Scope

The package is deliberately self-contained: it will install its own robot
description, simulation, controller, MoveIt, test, and helper assets without a
runtime dependency on the original workspace. Phase 1 intentionally excludes
Panda pick-place code; that migration happens separately after the SO-101
environment is proven from this workspace.
