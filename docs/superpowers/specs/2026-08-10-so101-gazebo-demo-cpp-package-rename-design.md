# SO-101 C++ Gazebo Demo ROS Package Rename Design

**Date:** 2026-08-10
**Status:** Approved for written specification; implementation not started

## 1. Goal

Rename the C++-based SO-101 ROS 2 package so that it is unambiguous beside the independent Python implementation:

- source directory: `src/so101_gazebo_demo` -> `src/so101_gazebo_demo_cpp`
- ROS package name: `so101_gazebo_demo` -> `so101_gazebo_demo_cpp`

The migration changes packaging and operational references only. It must not change pick-place behavior, physics parameters, validation policy, C++ APIs, or the independent Python package.

## 2. Naming Contract

| Boundary | Before | After |
|---|---|---|
| Source directory | `src/so101_gazebo_demo` | `src/so101_gazebo_demo_cpp` |
| `package.xml` name | `so101_gazebo_demo` | `so101_gazebo_demo_cpp` |
| CMake project | `so101_gazebo_demo` | `so101_gazebo_demo_cpp` |
| ROS install prefix | `install/so101_gazebo_demo` | `install/so101_gazebo_demo_cpp` |
| `ros2 run/launch` package argument | `so101_gazebo_demo` | `so101_gazebo_demo_cpp` |
| C++ namespace | `so101_gazebo_demo` | unchanged |
| Public include tree | `include/so101_gazebo_demo/...` | unchanged |
| C++ include expressions | `#include "so101_gazebo_demo/..."` | unchanged |
| Python module inside C++ package | `so101_teleop` | unchanged |
| Independent Python ROS package | `so101_gazebo_demo_py` | unchanged |

The distinction is deliberate: the ROS package identity becomes `so101_gazebo_demo_cpp`, while the existing C++ namespace and public include API remain stable.

## 3. Migration Scope

### 3.1 Production and package metadata

The implementation will use `git mv` for the source directory and update all active package-identity consumers, including:

- `package.xml` and `CMakeLists.txt`;
- `ament_index_cpp` and `ament_index_python` package-share lookups;
- launch `package=` fields and launch-time package resolution;
- scripts that invoke `ros2 run`, `ros2 launch`, `colcon build`, or `colcon test`;
- generated or checked-in operational configuration whose package field names the ROS package;
- package-layout, source-manifest, launch-contract, self-containment, and provenance tests;
- current IDE/project configuration that points at the source package directory.

Target names, node names, logger names, topics, services, actions, configuration keys, and environment-variable names remain unchanged unless they explicitly encode the ROS package identity and a test demonstrates that they must migrate.

### 3.2 Current documentation and agent guidance

Current operational documentation will use the new package name and path:

- package README and current architecture/launch-parameter documentation;
- active project Skills and their system-map, access, and acceptance references;
- current runbooks or configuration pages used to build, test, launch, or inspect the package.

Current documentation will state that older experiment records may contain the legacy package name because those records preserve commands that were actually executed before the migration.

### 3.3 Historical evidence

Historical evidence remains byte-for-byte unchanged. This includes dated experiment ledgers, handoffs, and pre-migration plan/spec documents. Their old paths and commands are historical facts, not current instructions.

Static reference checks will therefore use an explicit historical allowlist rather than requiring the legacy token to disappear globally. The allowlist is limited to:

- `docs/experiments/`;
- `docs/handoffs/`;
- pre-migration files under `docs/superpowers/plans/` and `docs/superpowers/specs/`.

The new design and implementation-plan documents may mention the old name only when describing the migration contract.

## 4. Compatibility Policy

There will be no compatibility metapackage, alias package, duplicate resource-index entry, or wrapper that preserves `ros2 run/launch so101_gazebo_demo ...`.

After migration:

- current commands must use `so101_gazebo_demo_cpp`;
- the old package must not be discoverable in a clean isolated overlay;
- stale generated artifacts for the old package will be removed only from the explicit package-scoped build/install paths after isolated validation succeeds.

This avoids two discoverable packages presenting the same executables and share resources.

## 5. TDD and Implementation Sequence

1. Update the package-layout contract first so it requires the new source-directory and ROS package names while explicitly asserting that the C++ include namespace remains unchanged.
2. Run the focused contract from the old tree and capture the expected RED failure caused by the absent new identity.
3. Rename the source directory with `git mv`.
4. Make the minimum package-metadata and active-reference changes needed to satisfy the contract.
5. Update current documentation and Skills without rewriting historical evidence.
6. Run focused static and launch-contract tests until GREEN.
7. Build and test the renamed package in isolated `/tmp` build/install/log bases sourced only from ROS Jazzy. This prevents a stale old workspace overlay from masking missing dependencies or package references.
8. After isolated verification passes, remove only these stale generated paths if present:
   - `/data/work/ws_moveit/build/so101_gazebo_demo`
   - `/data/work/ws_moveit/install/so101_gazebo_demo`
9. Build the renamed package into the main workspace overlay and re-source it.
10. Verify installed provenance and current Git scope. Do not start an execute-mode Gazebo/MoveIt experiment because the migration is packaging-only.

## 6. Reference Classification

A blind global replacement is forbidden because it would incorrectly rename the public C++ API and corrupt historical evidence.

Every remaining `so101_gazebo_demo` occurrence must fall into one of these allowed classes:

1. C++ namespace, symbol, or include-tree usage;
2. independent Python package name `so101_gazebo_demo_py`;
3. explicitly preserved historical evidence;
4. migration documentation that contrasts old and new identities.

Any active package lookup, source path, ROS CLI package argument, package metadata, test expectation, or current operational instruction using the old identity is a migration defect.

## 7. Verification and Acceptance

The migration is complete only when fresh evidence demonstrates all of the following:

1. `git status --short` before the change was clean, and the final diff contains only rename-related files.
2. The focused package-layout contract shows a genuine RED -> GREEN transition.
3. `colcon list --base-paths src/so101_gazebo_demo_cpp` reports `so101_gazebo_demo_cpp` and never reports the old package.
4. A clean isolated build succeeds with `--packages-select so101_gazebo_demo_cpp --cmake-clean-cache --symlink-install`.
5. The renamed package's complete test suite reports zero failures through `colcon test-result`.
6. In the isolated overlay:
   - `ros2 pkg prefix so101_gazebo_demo_cpp` resolves to the isolated install;
   - `ros2 pkg executables so101_gazebo_demo_cpp` lists the expected executables;
   - `ros2 pkg prefix so101_gazebo_demo` fails.
7. `ros2 launch so101_gazebo_demo_cpp so101_pick_place.launch.py --show-args` succeeds without starting a simulation stack.
8. Active package/path reference scans contain no legacy package identity outside the documented allowed classes.
9. C++ namespace and include scans show no migration to `so101_gazebo_demo_cpp`.
10. `git diff --check` succeeds, the main workspace contains no generated artifacts, and no unrelated worktree or remote ref changed.

Known unrelated failures in other packages do not authorize changing their code as part of this rename. Any renamed-package failure must be resolved before completion is claimed.

## 8. Risks and Controls

- **Stale overlay masks errors:** use isolated build/install/log bases before rebuilding the main overlay.
- **Accidental C++ API rename:** keep namespace/include assertions in the RED/GREEN contract and scan the final diff.
- **Historical provenance corruption:** exclude historical evidence from mechanical replacement and confirm it is unchanged.
- **Missed runtime package lookup:** verify launch argument discovery and installed executables from the isolated overlay.
- **Unrelated cleanup:** remove only package-scoped old generated paths; preserve other worktrees, branches, tmux sessions, and ROS processes.

## 9. Rollback

Before commit, rollback is the inverse Git rename plus restoration of the scoped diff. After commit, rollback uses a normal revert commit. No force reset, force push, or broad workspace cleanup is part of this migration.
