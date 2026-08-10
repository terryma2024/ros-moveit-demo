# Panda C++ Gazebo Demo ROS Package Rename Design

**Date:** 2026-08-10
**Status:** Approved for written specification; implementation not started

## 1. Goal

Rename the C++-based Panda ROS 2 package so that its implementation language is explicit and its naming is consistent with the SO-101 C++ package:

- source directory: `src/panda_gazebo_demo` -> `src/panda_gazebo_demo_cpp`
- ROS package name: `panda_gazebo_demo` -> `panda_gazebo_demo_cpp`

The migration changes packaging and operational references only. It must not change Panda pick-place behavior, physics, robot geometry, controller settings, validation policy, C++ APIs, or shared pick-place behavior.

## 2. Naming Contract

| Boundary | Before | After |
|---|---|---|
| Source directory | `src/panda_gazebo_demo` | `src/panda_gazebo_demo_cpp` |
| `package.xml` name | `panda_gazebo_demo` | `panda_gazebo_demo_cpp` |
| CMake project | `panda_gazebo_demo` | `panda_gazebo_demo_cpp` |
| ROS install prefix | `install/panda_gazebo_demo` | `install/panda_gazebo_demo_cpp` |
| `ros2 run/launch` package argument | `panda_gazebo_demo` | `panda_gazebo_demo_cpp` |
| C++ namespace | `panda_gazebo_demo` | unchanged |
| Public include tree | `include/panda_gazebo_demo/...` | unchanged |
| C++ include expressions | `#include "panda_gazebo_demo/..."` | unchanged |
| Shared package | `pick_place_common` | unchanged |
| SO-101 packages | `so101_gazebo_demo_cpp`, `so101_gazebo_demo_py` | unchanged |

The ROS package identity becomes `panda_gazebo_demo_cpp`, while the existing C++ namespace and public include API remain stable.

## 3. Migration Scope

### 3.1 Production and package metadata

The implementation will use `git mv` for the source directory and update active package-identity consumers, including:

- `package.xml` and `CMakeLists.txt`;
- `ament_index_python` package-share lookups;
- launch `package=` fields and launch-time package resolution;
- Xacro package-share expressions;
- scripts that invoke `ros2 run`, `ros2 launch`, `colcon build`, or `colcon test`;
- reset helpers whose default package value names the ROS package;
- package-layout, source-manifest, launch-contract, shared-consumer, and provenance tests;
- current operational configuration that points at the source package directory or package-scoped build/test paths.

Library target names, executable names, node names, logger names, topics, services, actions, configuration keys, environment-variable names, C++ namespaces, and include paths remain unchanged unless they explicitly encode the ROS package identity and a focused test proves that migration is required.

### 3.2 Current documentation and guidance

Current operational documentation will use the new package name and path:

- the Panda package README;
- current pick-place architecture and launch-parameter documentation;
- the shared package README and current package-consumer contract;
- any active runbook or configuration page used to build, test, launch, or inspect Panda.

Current documentation will state that older records may contain the legacy name because those records preserve commands and paths that were correct before the migration.

### 3.3 Historical evidence

Historical evidence remains unchanged. This includes dated experiment ledgers, handoffs, and pre-migration plan/spec documents. Their old paths and commands are historical facts rather than current instructions.

Static reference checks will use an explicit historical allowlist rather than require the legacy token to disappear globally. The allowlist is limited to:

- `docs/experiments/`;
- `docs/handoffs/`;
- pre-migration files under `docs/superpowers/plans/` and `docs/superpowers/specs/`.

The new design and implementation-plan documents may mention the old name only when describing the migration contract.

## 4. Compatibility Policy

There will be no compatibility metapackage, alias package, duplicate resource-index entry, or wrapper that preserves `ros2 run/launch panda_gazebo_demo ...`.

After migration:

- current commands must use `panda_gazebo_demo_cpp`;
- the old package must not be discoverable in a clean isolated overlay;
- stale generated artifacts for the old package will be removed only from explicit package-scoped build/install paths after isolated validation succeeds.

This prevents two discoverable packages from presenting the same executables and share resources.

## 5. TDD and Implementation Sequence

1. Add or update a package-layout contract so it requires the new source-directory and ROS package names while explicitly asserting that the C++ namespace and include tree remain unchanged.
2. Run the focused contract against the old tree and capture the expected RED failure caused by the absent new identity.
3. Rename the source directory with `git mv`.
4. Make the minimum metadata and active-reference changes needed to satisfy the contract.
5. Update current documentation without rewriting historical evidence.
6. Run focused static, launch-contract, shell, and shared-consumer tests until GREEN.
7. Build and test the renamed package in isolated `/tmp` build/install/log bases sourced only from ROS Jazzy, preventing a stale workspace overlay from masking missing dependencies or references.
8. After isolated verification passes, remove only these stale generated paths if present:
   - `/data/work/ws_moveit/build/panda_gazebo_demo`
   - `/data/work/ws_moveit/install/panda_gazebo_demo`
9. Build the renamed package into the main workspace overlay and re-source it.
10. Verify installed provenance and final Git scope. Do not start Gazebo/MoveIt execution because this is a packaging-only migration.

## 6. Reference Classification

A blind global replacement is forbidden because it would rename the public C++ API and corrupt historical evidence.

Every remaining `panda_gazebo_demo` occurrence must belong to one of these allowed classes:

1. C++ namespace, symbol, or include-tree usage;
2. explicitly preserved historical evidence;
3. migration documentation contrasting old and new identities.

Any active package lookup, source path, ROS CLI package argument, package metadata, package-scoped generated path, test expectation, or current operational instruction using the old identity is a migration defect.

## 7. Verification and Acceptance

The migration is complete only when fresh evidence demonstrates all of the following:

1. The worktree was clean before the change, and the final diff contains only Panda rename-related files.
2. The focused package-layout contract shows a genuine RED -> GREEN transition.
3. `colcon list --base-paths src/panda_gazebo_demo_cpp` reports `panda_gazebo_demo_cpp` and never reports the old package.
4. A clean isolated build succeeds for `pick_place_common` and `panda_gazebo_demo_cpp` with `--cmake-clean-cache --symlink-install`.
5. The renamed package's complete test suite and the shared package's affected contract tests report zero failures through package-scoped `colcon test-result` queries.
6. In the isolated overlay:
   - `ros2 pkg prefix panda_gazebo_demo_cpp` resolves to the isolated install;
   - `ros2 pkg executables panda_gazebo_demo_cpp` lists the expected executables;
   - `ros2 pkg prefix panda_gazebo_demo` fails.
7. `ros2 launch panda_gazebo_demo_cpp panda_gazebo.launch.py --show-args` succeeds without starting a simulation stack.
8. Active package/path reference scans contain no legacy package identity outside the documented allowed classes.
9. Namespace/include scans show no migration to `panda_gazebo_demo_cpp`.
10. `git diff --check` succeeds, source directories contain no tracked runtime/cache artifacts, and no unrelated worktree, branch, tmux session, or remote ref changes.

Pre-existing failures must be baselined before implementation. They do not authorize unrelated fixes, but any failure caused or exposed by the rename must be resolved before completion is claimed.

## 8. Risks and Controls

- **Stale overlay masks errors:** validate first with isolated build/install/log bases.
- **Accidental C++ API rename:** enforce namespace/include preservation in the RED/GREEN contract and final scans.
- **Historical provenance corruption:** exclude historical evidence from mechanical replacement and confirm it remains unchanged.
- **Missed runtime lookup:** validate launch argument discovery, installed executables, Xacro resolution, and reset helpers from the isolated overlay.
- **Shared-consumer drift:** update and run `pick_place_common` consumer contracts together with the Panda package.
- **Unrelated cleanup:** remove only old Panda package-scoped generated paths; preserve other packages, worktrees, branches, tmux sessions, and processes.

## 9. Commit and Push Policy

The written specification and later implementation will be committed locally in scoped commits. No push is part of this request unless separately authorized.

## 10. Rollback

Before commit, rollback is the inverse Git rename plus restoration of the scoped diff. After commit, rollback uses a normal revert commit. No force reset, force push, or broad workspace cleanup is part of this migration.
