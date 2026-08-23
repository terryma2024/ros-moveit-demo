# Project README Refresh Design

## Purpose

Replace the root README's obsolete Panda fixed-pose-only description with a concise workspace-level
entry point that matches the current repository. The README should help a new developer understand
what the workspace contains, how its major packages relate, how to build the supported targets, and
which commands start the principal demos.

## Audience and scope

The primary audience is a developer arriving at the repository root. The README describes the
workspace as a whole, with SO-101 simulation and teleoperation as the main project and the Panda
examples as secondary examples that remain available.

The README will cover:

1. A short project introduction and supported simulator/toolchain summary.
2. A high-level architecture showing shared pick-place code, the canonical SO-101 Python package,
   the Gazebo C++ implementation, Teleop, simulator support, and the Panda examples.
3. A curated directory tree containing only maintained source packages and key documentation.
4. Prerequisites and build commands for the common workspace, the canonical Python demo, and the
   pinned MuJoCo control dependency.
5. Run commands for the canonical MuJoCo and Gazebo Python launchers, shared operator CLIs, Teleop,
   the Gazebo C++ demo, and the Panda examples.
6. Links to package-specific architecture, integration, and operating documentation.

## Information architecture

The root README will use this order:

1. Project overview
2. Main capabilities
3. Architecture
4. Repository layout
5. Environment requirements
6. Build
7. Run
8. Documentation index
9. Safety boundary

The architecture section stays conceptual. It explains ownership and dependency direction without
listing internal classes, transaction phases, evidence schemas, qualification hashes, or historical
experiments. Detailed SO-101 Python behavior remains in `src/so101_demo_py/README.md` and
`docs/pick-place-python-architecture.md`; MuJoCo dependency details remain in
`docs/guides/so101-mujoco-ros2-integration-guide.md`.

## Source-of-truth rules

Commands and paths must be derived from current tracked files:

- package names and dependencies from `package.xml`;
- executable names from CMake/install rules and Python `setup.py`;
- launch names and arguments from current `launch/` files;
- simulator dependency setup from `scripts/install-mujoco-ros2-control.zsh` and its lock file;
- supported public SO-101 operations from `src/so101_demo_py/README.md` and current CLI entry points.

The deleted `so101_mujoco_demo_py` and `so101_gazebo_demo_py` packages must not be documented as
available packages. Historical experiment paths and machine-specific qualification overlays must
not appear in general build or run instructions.

## Build and run presentation

Examples will use ROS 2 Jazzy and show both Bash and Zsh sourcing only where that distinction is
useful. The default build path will use package selection rather than implying every optional
component must be built. MuJoCo setup will point to the repository installer instead of duplicating
its lock and fork logic.

Run examples will default to safe inspection or dry-run behavior. Commands that enable simulation
execution will explicitly show the required execution arguments. The README will state that no
real-arm launcher is provided and that real hardware requires a separate safety integration.

## Non-goals

- Rewriting package-specific READMEs or architecture documents.
- Documenting implementation classes, complete CLI schemas, test counts, evidence layouts, or
  qualification history in the root README.
- Changing source code, launch behavior, dependencies, or simulator policy.
- Adding real-hardware instructions.

## Acceptance criteria

- Every documented package, directory, launcher, executable, script, and linked document exists.
- Removed Python compatibility-package names do not appear as available components.
- Build commands match the current package and installer structure.
- Run commands match current launch and console-script names.
- The README is concise and centered on introduction, architecture, layout, build, and operation.
- Markdown links resolve within the repository and `git diff --check` passes.
