---
task_id: so101-macos-jazzy-path-deps-20260923-703e5272
goal: Move the macOS Jazzy logical prefix to /opt/ros/jazzy, install the missing Gazebo Harmonic and MoveIt build closure, and pass the C++ project test gate.
success_contract: The physical /Users/matianyi/ros2_jazzy tree is reached through /opt/ros/jazzy; active scripts and guides use that prefix; the old /opt/ros2_jazzy link is absent; a fresh complete project build and C++ CTest gate pass.
worktree: /Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp
branch: codex/so101-unified-webapp
base_commit: 703e5272c5e665bbd44c7ae098ad072c46f7901e
current_commit: 703e5272c5e665bbd44c7ae098ad072c46f7901e
evidence_root: /tmp/so101-debug-macos-jazzy-path-deps-20260923-703e5272
confirmed_conclusions:
  - CP-008: /opt/ros/jazzy now links to the physical home ROS tree; the root-owned /opt/ros2_jazzy link still needs admin authentication to remove.
  - CP-008: Homebrew Harmonic and the isolated Jazzy Gazebo, MoveIt, and ros_gz packages compile; seven project C++ packages compile.
  - CP-008: so101_demo_py passed its full -n8 gate (3918 passed, 10 skipped); SO-101 Gazebo's live world and launch contract CTests passed after fixing macOS launch subprocess library paths.
  - CP-009: All 29 selected dependency packages were installed under /opt/ros/jazzy/extra_ws/install, and the full macOS doctor passed.
  - CP-010: Standard project build passed for eight packages; the migrated fork passed 10/10 CTests; six C++ package CTest suites passed (124 registered tests, one package with no tests).
  - CP-011: All five relevant Python module scopes passed their complete pytest -n8 gates; Web Bun unit passed 300/300; final macOS doctor passed.
disproven_routes: []
open_hypotheses:
  - Whether an administrator can retire the root-owned /opt/ros2_jazzy compatibility link.
latest_checkpoint: CP-011
next_experiment: EXP-012
---

## CP-001: baseline

The source worktree was clean at `703e5272`; the fork submodule was `5a590b2`.
The existing runtime Python is the executable
`/Users/matianyi/ros2_jazzy/.venv/bin/python`, previously exposed as
`/opt/ros2_jazzy/.venv/bin/python`. The existing workspace contains two
unrelated static transform publishers; no Gazebo or MoveIt process was found.
`sudo -n true` returned 1 because sudo requires a password. The current user
owns `/opt/ros`, but `/opt/ros2_jazzy` is a root-owned entry under root-owned
`/opt`. The Linux host has a real `/opt/ros/jazzy` directory, confirming the
requested logical path convention. No ROS stack was started for this task.

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: A new user-writable logical prefix can be prepared first; the old root-owned link requires a separate privilege boundary.
working_tree_status: Clean before this ledger was added.
owned_processes: NONE
preserved_processes: Existing static_transform_publisher PIDs 1541 and 1542.
confirmed_conclusions:
  - The old logical prefix is a symlink to /Users/matianyi/ros2_jazzy.
  - The project CMake pins Gazebo Harmonic package versions; Homebrew currently has Jetty.
disproven_routes: []
open_risks:
  - Passwordless sudo is unavailable for removing the old /opt symlink.
  - Installing Harmonic may upgrade or conflict with existing Jetty formulae.
next_command: Inspect exact Homebrew formula closure, MoveIt sources, and active prefix references before editing.
```

## EXP-001: prefix and dependency closure reconnaissance

```yaml
experiment_id: EXP-001
status: VALID
prior_experiment: NONE
hypothesis: The missing compiled dependency closure can be identified without changing the shared installed ROS tree.
prediction: CMake and Homebrew metadata identify exact missing Harmonic and MoveIt packages and possible isolated install paths.
single_variable: NONE (read-only baseline)
lifecycle: REUSE_STACK
preconditions:
  - No task-owned ROS or Gazebo process exists.
success_criteria:
  - Exact dependency packages and prefix references are inventoried before installation or source changes.
failure_criteria:
  - A dependency requirement remains unknown after inspecting the package manifests and available formulae.
invalid_criteria:
  - Inspection reads stale source or an unexpected ROS prefix.
provenance:
  source_commit: 703e5272c5e665bbd44c7ae098ad072c46f7901e
  install_overlay: /opt/data/so101/workspace/install
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python
  ros_domain_id: 227
  gz_partition: so101-macos-path-deps-227
commands:
  - command: Inspect path references, Homebrew formula graph, MoveIt source and CMake package locations.
    exit_code: 0
observed:
  - gz-harmonic would add 16 missing versioned Harmonic formulae and upgrade 93 installed dependencies under the current Homebrew solver.
  - moveit_core and moveit_configs_utils resolve from extra_ws/install; moveit_ros_planning_interface does not, although its source is present.
  - gz_ros2_control and ros_gz_sim are absent from the installed ROS package index; gz_ros2_control source is absent from the existing extra_ws source tree.
inferred:
  - The missing C++ closure has separate Gazebo, ROS bridge, and MoveIt install boundaries.
conclusion: The package gaps are identified; installation must be staged and tested by boundary.
evidence:
  - /tmp/so101-debug-macos-jazzy-path-deps-20260923-703e5272
decision: KEEP
next_experiment: EXP-002
```

## CP-002: dependency map and path-change entry

`/opt/ros/jazzy` is a real directory on Linux, but the requested Mac entry
does not exist yet. The Mac `/opt/ros` directory is user-owned, while the old
`/opt/ros2_jazzy` link cannot be removed with passwordless sudo. The
repository's production path literals occur in `so101-macos.zsh`, the runtime
contract, dylib farm setup, campaign scripts, diagnostic CLI, Web host
fixtures, tests, guides, and the project-local skill reference. Historic
experiment ledgers and approved plans are not implementation inputs to
rewrite. The Homebrew dry-run and JSON formula metadata are saved in
`package-notes/` under the registered evidence root.

```yaml
checkpoint_id: CP-002
last_valid_experiment: EXP-001
current_hypothesis: The new logical prefix can be introduced and verified before replacing the root-owned old link.
working_tree_status: docs/experiments/so101-macos-jazzy-path-deps-20260923-experiment-ledger.md added.
owned_processes: NONE
preserved_processes: Existing static_transform_publisher PIDs 1541 and 1542.
confirmed_conclusions:
  - MoveIt planning interface source exists but is not installed.
  - Gazebo Harmonic 8/10/13 formulae and gz_ros2_control are not installed.
disproven_routes:
  - The current Jetty formulae cannot satisfy CMake requests for gz-msgs10/gz-sim8.
open_risks:
  - Existing Homebrew formulae are outdated; the standard Harmonic install plan would upgrade 93 dependencies.
  - The old root-owned symlink needs administrative credentials for removal.
next_command: Run the current base doctor, then make the new-path contract tests RED before changing production path literals.
```

## EXP-002: logical prefix migration

```yaml
experiment_id: EXP-002
status: VALID
prior_experiment: EXP-001
hypothesis: Repointing the logical prefix to /opt/ros/jazzy while retaining the same physical tree preserves the macOS runtime contract.
prediction: The new-path contract tests fail before code edits, then pass after the link and active setup scripts change; the base doctor passes through the new path.
single_variable: Logical ROS prefix path.
lifecycle: REUSE_STACK
preconditions:
  - The physical ROS tree and existing unrelated ROS processes remain untouched.
success_criteria:
  - New-path tests and doctor --base exit 0; active references no longer use /opt/ros2_jazzy.
failure_criteria:
  - A code assertion or base doctor fails after the new link exists and paths change.
invalid_criteria:
  - Missing physical ROS setup files or stale test interpreter prevents the intended boundary from running.
provenance:
  source_commit: 703e5272c5e665bbd44c7ae098ad072c46f7901e
  install_overlay: /opt/data/so101/workspace/install
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python
  ros_domain_id: 227
  gz_partition: so101-macos-path-deps-227
commands:
  - command: scripts/so101-macos.zsh doctor --base before and after migration
    exit_code: 0 before and after
  - command: New-path contract pytest (RED then GREEN)
    exit_code: 1 (RED before production changes; expected path /opt/ros/jazzy, observed /opt/ros2_jazzy)
observed:
  - The new /opt/ros/jazzy symlink resolves to the same physical ROS tree and doctor --base passes.
  - The dylib farm was regenerated with 767 library links and no targets under /opt/ros2_jazzy.
  - Existing fork and project setup.zsh files embed the old underlay; sourcing their local_setup.zsh files after the explicit new underlays yields package prefixes under /opt/ros/jazzy and doctor --json PASS.
inferred:
  - The existing physical ROS tree works through the new logical prefix without rebuilding the base underlay.
conclusion: The new symlink, active scripts, and runtime contract use /opt/ros/jazzy; old root-owned symlink removal remains pending admin authentication.
evidence:
  - /tmp/so101-debug-macos-jazzy-path-deps-20260923-703e5272
decision: KEEP
next_experiment: EXP-003
```

## EXP-003: Gazebo Harmonic installation

```yaml
experiment_id: EXP-003
status: VALID
prior_experiment: EXP-002
hypothesis: Homebrew's versioned Harmonic formulae can be installed alongside existing Jetty packages to satisfy the CMake version pins.
prediction: gz-msgs10, gz-transport13, and gz-sim8 CMake packages resolve without removing Jetty.
single_variable: Install the versioned Gazebo Harmonic package closure.
lifecycle: REUSE_STACK
provenance:
  source_commit: 703e5272c5e665bbd44c7ae098ad072c46f7901e
  install_overlay: /opt/data/so101/workspace/install
  runtime_executable: /opt/ros/jazzy/.venv/bin/python
  ros_domain_id: 227
  gz_partition: so101-macos-path-deps-227
commands:
  - command: brew install osrf/simulation/gz-msgs10 osrf/simulation/gz-transport13
    exit_code: 0
  - command: brew install osrf/simulation/gz-sim8
    exit_code: 1 (ogre2.3 link collision)
  - command: brew unlink ogre2.3; brew link ogre2.3-with-freeimage; brew install osrf/simulation/gz-sim8
    exit_code: 0
observed:
  - Homebrew installed gz-msgs10 10.4.0, gz-transport13 13.6.0, gz-sim8 8.15.0, and gz-plugin2 2.0.4.
  - The old ogre2.3 formula remains installed but unlinked; ogre2.3-with-freeimage is linked.
conclusion: The Harmonic CMake package closure is installed from Homebrew.
evidence:
  - /tmp/so101-debug-macos-jazzy-path-deps-20260923-703e5272/package-notes
decision: KEEP
next_experiment: EXP-004
```

## EXP-004: MoveIt planning interface overlay

```yaml
experiment_id: EXP-004
status: VALID
prior_experiment: EXP-003 (independent package boundary, run during Homebrew download)
hypothesis: The missing warehouse_ros, moveit_ros_warehouse, and moveit_ros_planning_interface packages build from the existing Jazzy source tree against the installed ROS underlays.
prediction: Their CMake package files appear in a task-owned isolated install prefix.
single_variable: Build the three missing MoveIt packages from existing source.
lifecycle: REUSE_STACK
provenance:
  source_commit: 703e5272c5e665bbd44c7ae098ad072c46f7901e
  install_overlay: /tmp/so101-debug-macos-jazzy-path-deps-20260923-703e5272/build/moveit-install
  runtime_executable: /opt/ros/jazzy/.venv/bin/colcon
  ros_domain_id: 227
  gz_partition: so101-macos-path-deps-227
commands:
  - command: colcon build --packages-select warehouse_ros moveit_ros_warehouse moveit_ros_planning_interface --cmake-args -DBUILD_TESTING=OFF
    exit_code: 1 (CMake 4.4 selected Homebrew Python 3.14 without catkin_pkg)
  - command: Repeat with -DPython3_EXECUTABLE=/opt/ros/jazzy/.venv/bin/python and a clean CMake cache.
    exit_code: 1 while Homebrew was upgrading Boost; 0 after Boost upgrade completed and the CMake cache was reset
observed:
  - The intended warehouse_ros source reached ament_package, but CMake selected /opt/homebrew/Frameworks/Python.framework/Versions/3.14/bin/python3 instead of the Jazzy Python 3.11 interpreter.
conclusion: The three missing MoveIt package configs are available in the isolated moveit-install prefix.
evidence:
  - /tmp/so101-debug-macos-jazzy-path-deps-20260923-703e5272/build/moveit-build.log
decision: KEEP
next_experiment: EXP-005
```

## EXP-005: C++ auxiliary ROS packages

```yaml
experiment_id: EXP-005
status: VALID
prior_experiment: EXP-004 (independent source set)
hypothesis: The missing xacro, Panda MoveIt resource, and simulation_interfaces packages can be built in a task-owned overlay against the existing Jazzy underlays.
prediction: Their CMake package configurations resolve from the auxiliary install prefix.
single_variable: Build the additional ROS package closure used by the project C++ packages.
lifecycle: REUSE_STACK
provenance:
  source_commit: 703e5272c5e665bbd44c7ae098ad072c46f7901e
  install_overlay: /tmp/so101-debug-macos-jazzy-path-deps-20260923-703e5272/build/aux-install
  runtime_executable: /opt/ros/jazzy/.venv/bin/colcon
  ros_domain_id: 227
  gz_partition: so101-macos-path-deps-227
commands:
  - command: colcon build --packages-select xacro moveit_resources_panda_description moveit_resources_panda_moveit_config simulation_interfaces
    exit_code: 0
  - command: colcon build --packages-select actuator_msgs gps_msgs marine_acoustic_msgs vision_msgs
    exit_code: 0
observed:
  - Four auxiliary packages built successfully in the isolated aux-install prefix.
  - Four message packages needed by ros_gz_bridge also built in the isolated aux-install prefix.
conclusion: The auxiliary C++ and bridge message closure is available for integration builds.
evidence:
  - /tmp/so101-debug-macos-jazzy-path-deps-20260923-703e5272/build
decision: KEEP
next_experiment: EXP-006
```

## EXP-006: ROS Gazebo vendor packages

```yaml
experiment_id: EXP-006
status: VALID
prior_experiment: EXP-003
hypothesis: Official Jazzy Gazebo vendor packages accept the matching Homebrew Harmonic CMake packages without rebuilding Gazebo.
prediction: The 13 missing vendor package configs are installed in an isolated overlay, with no vendored Gazebo source build.
single_variable: Build the ROS Gazebo vendor package wrappers against installed Homebrew Harmonic.
lifecycle: REUSE_STACK
provenance:
  source_commit: 703e5272c5e665bbd44c7ae098ad072c46f7901e
  install_overlay: /tmp/so101-debug-macos-jazzy-path-deps-20260923-703e5272/build/vendor-install
  runtime_executable: /opt/ros/jazzy/.venv/bin/colcon
  ros_domain_id: 227
  gz_partition: so101-macos-path-deps-227
commands:
  - command: Build 11 Gazebo vendor packages.
    exit_code: 1 (gz_dartsim_vendor and gz_ogre_next_vendor were missing from initial source selection)
  - command: Build complete vendor dependency closure up to gz_sim_vendor.
    exit_code: 1 (gz_ogre_next_vendor attempted an unnecessary Ogre source build and required vcs)
  - command: Apply tools/macos/gz-ogre-next-vendor-homebrew.patch and repeat with GZ_RELAX_VERSION_MATCH=1.
    exit_code: 0
observed:
  - Four wrappers built before the initial missing gz_dartsim_vendor CMake package stopped configuration.
  - Homebrew Ogre 2.3.1 is available via pkg-config, while the official Ogre vendor wrapper defaults to building Ogre 2.3.3 from source.
conclusion: All 13 Gazebo vendor wrappers built against Homebrew Harmonic; the Ogre wrapper was adapted to use Homebrew's OGRE-2.3 pkg-config package.
evidence:
  - /tmp/so101-debug-macos-jazzy-path-deps-20260923-703e5272/build
decision: KEEP
next_experiment: EXP-007
```

## EXP-007: Gazebo ROS integration packages

```yaml
experiment_id: EXP-007
status: VALID
prior_experiment: EXP-006
hypothesis: Official Jazzy ros_gz_sim and gz_ros2_control source builds against the Homebrew Harmonic and ROS vendor overlays.
prediction: The required CMake package configurations and libraries install into an isolated integration prefix.
single_variable: Build the missing Gazebo ROS integration packages.
lifecycle: REUSE_STACK
provenance:
  source_commit: 703e5272c5e665bbd44c7ae098ad072c46f7901e
  install_overlay: /tmp/so101-debug-macos-jazzy-path-deps-20260923-703e5272/build/integration-install
  runtime_executable: /opt/ros/jazzy/.venv/bin/colcon
  ros_domain_id: 227
  gz_partition: so101-macos-path-deps-227
commands:
  - command: colcon build --packages-select ros_gz_sim gz_ros2_control
    exit_code: 1 (ros_gz_sim requires ros_gz_bridge package.sh in the same build graph)
  - command: Build gz_ros2_control separately while preparing the ros_gz_bridge message closure.
    exit_code: 1 (Qt5 keg-only path), 2 (TINYXML2 target), 2 (macOS Entity printf format), then 0 after targeted compatibility fixes
  - command: Build ros_gz_bridge after four message packages and dylib farm migration.
    exit_code: 2 (Python generator lost DYLD_LIBRARY_PATH under system Make), 1 (same under Ninja)
  - command: Build ros_gz_bridge from the pinned local ros_gz clone after applying tools/macos/ros-gz-bridge-dyld-farm.patch.
    exit_code: 0
  - command: Build ros_gz_sim against the bridge and vendor overlays.
    exit_code: 1 (Homebrew CLI11's target config did not populate legacy CLI11_INCLUDE_DIRS)
  - command: Repeat ros_gz_sim with -DCLI11_INCLUDE_DIRS=/opt/homebrew/opt/cli11/include.
    exit_code: 0
observed:
  - Colcon reached package scheduling but stopped before CMake because ros_gz_bridge was not installed.
  - gz_ros2_control built at commit 7937b309 after setting Qt5_DIR, preloading the Homebrew TINYXML2 target, and applying the Entity format patch.
  - The pre-migration dylib farm linked to /opt/ros2_jazzy; regenerating it through /opt/ros/jazzy enabled the ROS Python import used by ros_gz_bridge code generation.
  - Direct ROS Python import passes with the regenerated farm, but colcon's code-generator child lacks DYLD_LIBRARY_PATH under both Make and Ninja. The targeted CMake patch reintroduces it only for the two Python generation commands.
  - The patched ros_gz_bridge built successfully in 34 seconds; ros_gz_sim then reached compilation and stopped on a missing CLI/CLI.hpp include path despite Homebrew cli11 being installed.
  - ros_gz_sim completed after its legacy CLI11 include variable was bound to the installed Homebrew header directory.
conclusion: gz_ros2_control, ros_gz_bridge, and ros_gz_sim now have isolated CMake and library install artifacts.
evidence:
  - /tmp/so101-debug-macos-jazzy-path-deps-20260923-703e5272/build
decision: KEEP
next_experiment: EXP-008
```

## EXP-008: fresh project C++ build and test

```yaml
experiment_id: EXP-008
status: RUNNING
prior_experiment: EXP-007
hypothesis: The complete isolated Harmonic, MoveIt, and bridge closure allows all project C++ packages to configure, compile, and pass CTest on macOS.
prediction: A fresh C++ install prefix contains the selected packages and colcon test-result reports no failures.
single_variable: Rebuild the project C++ package set against the complete dependency overlays.
lifecycle: REUSE_STACK
provenance:
  source_commit: 703e5272c5e665bbd44c7ae098ad072c46f7901e (working tree includes current path migration)
  install_overlay: /tmp/so101-debug-macos-jazzy-path-deps-20260923-703e5272/build/project-install
  runtime_executable: /opt/ros/jazzy/.venv/bin/colcon
  ros_domain_id: 227
  gz_partition: so101-macos-path-deps-227
commands:
  - command: Fresh colcon build of seven project packages against the isolated dependency overlays.
    exit_code: 1; panda_gazebo_demo_cpp configuration found the missing run-clang-tidy CMake variable.
  - command: Repeat with installed LLVM run-clang-tidy path.
    exit_code: 1; next CMake gate required the clang-format path.
  - command: Repeat with both LLVM paths and LLVM bin on PATH.
    exit_code: 1; six packages built, while LLVM 22 clang-tidy reported new warnings as errors in so101_gazebo_demo_cpp.
  - command: Repeat with Homebrew llvm@18.
    exit_code: 1; Clang 18 cannot parse the current Xcode SDK libc++ headers.
  - command: Fix the 25 distinct LLVM 22 diagnostics and repeat with LLVM 22.
    exit_code: 1; the clang-tidy gate passed and clang-format found three existing files to format.
  - command: Apply clang-format only to the three reported C++ files and repeat the failed package.
    exit_code: 0
  - command: Run the full so101_demo_py pytest scope with eight xdist workers and a unique short TMPDIR parent.
    exit_code: 0 (3918 passed, 10 skipped in 48.78 seconds)
  - command: Run SO-101 Gazebo live world and launch contract CTests after macOS shell and plugin fixes.
    exit_code: 0 (2/2; 103.84 and 79.63 seconds)
observed:
  - LLVM 22.1.8 already supplies /opt/homebrew/Cellar/llvm/22.1.8/bin/run-clang-tidy; the binary is absent from the shell PATH.
  - panda_gazebo_demo_cpp passes its C++ quality gate with the toolchain on PATH.
  - The CMake tool lookup names versions 16 through 18; llvm@18 is available from Homebrew and is the next isolated version comparison.
  - LLVM 18 fails in system libc++ headers, while LLVM 22 parses the SDK and passes static analysis after 25 targeted source fixes.
  - The first 8-worker so101_demo_py full run loaded the older installed Python package and used an overlong /tmp fixture path; 142 tests failed at that environment boundary. An isolated build of current so101_demo_py and a short /opt/data/tmp basetemp made the six representative 8-worker tests pass.
  - The later 8-worker run had 49 resource allocator failures because its TMPDIR parent was shared across runs; a unique parent under /opt/data/tmp resolved all of them without reducing worker count. The final isolated Python run passed 3918 cases with 10 skips.
  - The project C++ build completed for seven selected packages. Earlier whole-package CTest runs exposed missing GNU commands, macOS SIP stripping DYLD_LIBRARY_PATH through /bin/bash and /bin/sh, an installed Gazebo plugin suffix mismatch, and undersized cold-start timeouts.
  - Homebrew Bash, a macOS-only ros_gz_sim launch patch, the project plugin .so suffix, explicit plugin search paths, and bounded Mac CTest headroom made the SO-101 live world and launch contract pass in a two-case direct CTest.
conclusion: The isolated project C++ build and critical SO-101 live CTests pass; full CTest after promotion remains pending.
evidence:
  - /tmp/so101-debug-macos-jazzy-path-deps-20260923-703e5272/build
  - /tmp/so101-debug-macos-jazzy-path-deps-20260923-703e5272/tests
decision: KEEP
next_experiment: EXP-009
```

## CP-008: isolated closure and live launch

The old `/opt/ros2_jazzy` entry remains root-owned. A passwordless sudo check
and a macOS admin authorization attempt both failed; no link was deleted. The
new `/opt/ros/jazzy` entry, source scripts, doctor, and dylib farm work. The
isolated Gazebo, MoveIt, bridge, and project builds now pass, as do the Python
eight-worker gate and the two live SO-101 Gazebo CTests. The full C++ test set
must be rerun after promoting dependencies. No task-owned simulation process
was left running after the direct CTest.

```yaml
checkpoint_id: CP-008
last_valid_experiment: EXP-008
current_hypothesis: Promoting the verified isolated dependency sources into extra_ws/install will let the ordinary project build and full CTest use stable package prefixes.
working_tree_status: Path, runtime, CMake, tests, guides, and dependency patch changes remain uncommitted.
owned_processes: NONE
preserved_processes: Existing static_transform_publisher PIDs 1541 and 1542.
confirmed_conclusions:
  - The 8-worker Python gate passed with a unique short TMPDIR parent.
  - Homebrew Harmonic plus pinned Jazzy ROS packages compile in isolated overlays.
  - SO-101 Gazebo live world and launch contract pass under direct CTest.
disproven_routes:
  - The Linux /usr/bin/timeout and macOS system /bin/bash or /bin/sh do not retain the required ROS dylib path in launch children.
open_risks:
  - Stable dependency promotion and final complete C++ test run are pending.
  - Root-owned old symlink removal requires administrator authentication.
next_command: Run the prepared stable dependency promotion build from base and existing extra_ws underlays only.
```

## EXP-009: stable ROS dependency promotion

```yaml
experiment_id: EXP-009
status: VALID
prior_experiment: EXP-008
hypothesis: The pinned dependency sources can be installed into /opt/ros/jazzy/extra_ws/install without references to the task's isolated build prefixes.
prediction: All 29 selected ament packages build and resolve from the stable extra_ws/install prefix; the macOS doctor passes afterward.
single_variable: Change the install target from the isolated overlays to the stable Jazzy dependency prefix.
lifecycle: REUSE_STACK
provenance:
  source_commit: 703e5272c5e665bbd44c7ae098ad072c46f7901e (working tree includes current fixes)
  install_overlay: /opt/ros/jazzy/extra_ws/install
  runtime_executable: /opt/ros/jazzy/.venv/bin/colcon
  ros_domain_id: 227
  gz_partition: so101-macos-path-deps-227
commands:
  - command: /tmp/so101-debug-macos-jazzy-path-deps-20260923-703e5272/build/promote-dependencies.zsh
    exit_code: 2 (ros_gz_bridge generator missing CMake SO101_MACOS_DYLIB_FARM setting)
  - command: Repeat with -DSO101_MACOS_DYLIB_FARM=/opt/ros/jazzy/dylib_farm/current.
    exit_code: 1 (moveit_ros_planning_interface test dependency closure lacks Fanuc resource package setup files)
  - command: Repeat with moveit_resources_fanuc_description and moveit_resources_fanuc_moveit_config in the selection.
    exit_code: 0 (29 packages finished in 1min 31s)
observed:
  - First pass installed 22 packages; bridge code generation failed because an environment export did not set the CMake cache variable used by the existing DYLD patch.
  - Second pass reached the MoveIt planning interface, but colcon required Fanuc test dependency package.sh files even with BUILD_TESTING=OFF.
  - The complete third pass installed 29 package index entries, including gz_ros2_control, ros_gz_bridge, ros_gz_sim, and moveit_ros_planning_interface.
  - The installed ros_gz_sim launch contains the macOS shell patch. No task /tmp prefix appeared in selected installed package CMake configs or environment .dsv files.
  - A fresh dylib farm run was created at /opt/ros/jazzy/dylib_farm/runs/20260923T104009Z-14428, and scripts/so101-macos.zsh doctor --json returned PASS.
conclusion: The stable Jazzy dependency prefix contains the full selected closure and passes the macOS runtime doctor.
evidence:
  - /tmp/so101-debug-macos-jazzy-path-deps-20260923-703e5272/build
decision: KEEP
next_experiment: EXP-010
```

## CP-009: stable dependency prefix

The third promotion pass completed all 29 selected ROS packages. The package
index entries, patched installed Gazebo launch, regenerated dylib farm, and
full doctor all passed. The old root-owned `/opt/ros2_jazzy` entry remains
unmodified. The next boundary is a fresh project build and C++ test run that
sources only the stable ROS dependency prefix.

```yaml
checkpoint_id: CP-009
last_valid_experiment: EXP-009
current_hypothesis: The stable ROS dependency prefix supports a normal project build and full C++ CTest gate.
working_tree_status: Path, runtime, CMake, tests, guides, and dependency patch changes remain uncommitted.
owned_processes: Stable project colcon build in progress.
preserved_processes: Existing static_transform_publisher PIDs 1541 and 1542.
confirmed_conclusions:
  - All 29 selected dependency package index entries exist in extra_ws/install.
  - The patched ros_gz_sim launch was installed and doctor --json passed.
disproven_routes:
  - Exporting SO101_MACOS_DYLIB_FARM as a shell variable alone does not set its CMake cache variable.
  - The MoveIt planning interface build omits Fanuc resources only if the package selection ignores colcon test dependency setup files.
open_risks:
  - Project stable build and full C++ CTest remain pending.
  - Root-owned old symlink removal requires administrator authentication.
next_command: Finish the ongoing stable project build, then run CTest with stable prefixes.
```

## EXP-010: stable project build and C++ test

```yaml
experiment_id: EXP-010
status: VALID
prior_experiment: EXP-009
hypothesis: The promoted Jazzy dependencies support the project C++ build and complete CTest gate without isolated /tmp install overlays.
prediction: The standard /opt/data/so101/workspace/install packages build and all C++ CTest suites pass with the stable dylib farm.
single_variable: Replace isolated dependency and project install overlays with their standard macOS prefixes.
lifecycle: REUSE_STACK
provenance:
  source_commit: 703e5272c5e665bbd44c7ae098ad072c46f7901e (working tree includes current fixes)
  install_overlay: /opt/data/so101/workspace/install
  runtime_executable: /opt/ros/jazzy/.venv/bin/colcon
  ros_domain_id: 227
  gz_partition: so101-macos-path-deps-227
commands:
  - command: /tmp/so101-debug-macos-jazzy-path-deps-20260923-703e5272/build/build-project-stable.zsh
    exit_code: 0 (eight packages finished in 3min 23s)
  - command: scripts/so101-macos.zsh prepare, with a new locked fork run under the opt-ros-jazzy path.
    exit_code: 8 (fork CTest found a stale RPATH expectation), then 0 after the controlled fork test patch; 10/10 fork CTests and 233 nested tests passed
  - command: Repeat the standard project build with --cmake-clean-cache against the migrated fork.
    exit_code: 0 (eight packages finished in 2min 58s)
  - command: Run full direct CTest for six C++ packages with the stable ROS, fork, project, and dylib farm prefixes.
    exit_code: 0 (6, 12, 38, 0, 67, and 1 tests registered by package)
observed:
  - The initial stable build exposed old /opt/ros2_jazzy vendor include and RPATH references in the previously installed fork export.
  - The new fork run retained the locked 5a590b2 commit and used /opt/ros/jazzy; its own macOS test expected only @loader_path despite the locked CMake requiring a second relative MuJoCo vendor RPATH. An exact one-file patch corrected the test.
  - After prepare and a clean-cache project rebuild, a full text and binary scan of the current ROS dependency, fork, and project install prefixes found no /opt/ros2_jazzy literal.
  - Direct CTest passed all registered tests in fixed_pose_goal, pick_place_common, panda_gazebo_demo_cpp, so101_gazebo_demo_cpp, and so101_mujoco_support; panda_mujoco_demo registers no tests.
  - The two live SO-101 Gazebo CTests passed in 76.55 and 89.26 seconds with the stable prefixes.
  - Ten pinned source roots were retained under /opt/ros/jazzy/extra_ws/so101_macos_source_pins after matching each copied entry's relative path, size, and SHA256 to the isolated build source.
conclusion: Standard macOS project C++ compilation and the full registered CTest gate pass against stable prefixes.
evidence:
  - /tmp/so101-debug-macos-jazzy-path-deps-20260923-703e5272/build
  - /tmp/so101-debug-macos-jazzy-path-deps-20260923-703e5272/tests
decision: KEEP
next_experiment: EXP-011
```

## CP-010: stable C++ gate

The current fork and project installs have been rebuilt against `/opt/ros/jazzy`.
The fork's 10 CTests passed, and every registered C++ package CTest passed from
the standard `/opt/data/so101/workspace` build. The pinned supplemental
dependency source copies are retained outside the normal `src/` discovery tree
and verified byte for byte. Python module eight-worker gates and final package
checks remain. The old root-owned symlink still requires admin authentication.

```yaml
checkpoint_id: CP-010
last_valid_experiment: EXP-010
current_hypothesis: The stable project overlays also pass each relevant Python module's complete eight-worker gate.
working_tree_status: Path, runtime, CMake, tests, guides, and dependency patch changes remain uncommitted.
owned_processes: First stable Python module eight-worker test in progress.
preserved_processes: Existing static_transform_publisher PIDs 1541 and 1542.
confirmed_conclusions:
  - Eight standard project packages compile against the migrated fork.
  - The migrated fork passed 10/10 CTests and the full registered C++ CTest set passed.
  - Current install prefixes contain no old logical path literals.
disproven_routes:
  - The previous fork CMake export can safely remain active after removing the old symlink.
open_risks:
  - Each Python module full -n8 gate and final doctor remain pending.
  - Root-owned old symlink removal requires administrator authentication.
next_command: Finish stable Python module eight-worker gates and inspect results.
```

## EXP-011: stable Python module parallel gates

```yaml
experiment_id: EXP-011
status: VALID
prior_experiment: EXP-010
hypothesis: The standard macOS installs support every relevant Python module's full ordinary pytest scope with eight xdist workers.
prediction: Each module produces JUnit and exits zero under -n8 with a unique short scratch parent.
single_variable: Exercise the complete Python module scopes against stable install prefixes instead of isolated installs.
lifecycle: REUSE_STACK
provenance:
  source_commit: 703e5272c5e665bbd44c7ae098ad072c46f7901e (working tree includes current fixes)
  install_overlay: /opt/data/so101/workspace/install
  runtime_executable: /opt/ros/jazzy/.venv/bin/python
  ros_domain_id: 227
  gz_partition: so101-macos-path-deps-227
commands:
  - command: Run complete src/so101_demo_py/test with pytest -n8 --dist loadscope.
    exit_code: 1 (2 failed, 3916 passed, 10 skipped), then 0 (3918 passed, 10 skipped in 30.27s)
  - command: Run complete src/so101_teleop/test with pytest -n8 --dist loadscope.
    exit_code: 1 (1 failed, 1053 passed, 19 skipped), then 0 (1054 passed, 19 skipped in 84.55s)
  - command: Run complete src/pick_place_common/test and src/panda_gazebo_demo_cpp/test with pytest -n8.
    exit_code: 0 (3/3 and 20/20)
  - command: Run complete src/so101_gazebo_demo_cpp/test with pytest -n8.
    exit_code: 1 (3 failed, 213 passed, 9 skipped), then 0 (216 passed, 9 skipped after installed-build asset path correction)
  - command: Run Bun Web unit tests and the final macOS doctor.
    exit_code: 0 (300 Web tests; doctor status PASS)
observed:
  - The first stable Python run found an installer source-contract assertion that prohibited the new exact macOS fork test patch.
  - A resource allocation concurrency test released the winning claim after five seconds and timed out waiting for its competitor under eight-worker load. It now holds the claim until the competing outcome arrives and releases it in a finally block.
  - The second full so101_demo_py run passed all 3918 cases, with 10 skips, at eight workers and a unique short TMPDIR parent.
  - The first teleop run expected a historical service campaign /tmp root to exist before rejecting a missing selection manifest. The runner now checks the supplied manifest first; the second full teleop run passed 1054 cases, with 19 skips.
  - The pick_place_common and Panda Gazebo Python scopes passed with eight workers.
  - The SO-101 Gazebo Python scope found three calibration tests looking for generated meshes in the source worktree build directory. The tests now locate the standard build through the installed package prefix, as the other package tests do.
  - The second complete Gazebo Python scope passed 216 cases with 9 skips at eight workers. The other completed scopes passed 1054/19 (teleop), 3/0 (pick_place_common), and 20/0 (Panda Gazebo), with passed/skipped counts respectively.
  - Five final JUnit files contain zero failures and errors. Bun passed 53 files and 300 tests. The final full macOS doctor returned PASS.
conclusion: All relevant module scopes pass at eight workers against stable prefixes, and the full runtime doctor passes.
evidence:
  - /tmp/so101-debug-macos-jazzy-path-deps-20260923-703e5272/tests
decision: KEEP
next_experiment: EXP-012
```

## CP-011: complete local test gate

The standard Jazzy dependency and project installs remain under the new logical
prefix. The final project build and six C++ package CTest suites passed, with
124 registered tests; the package test-result summary recorded 1110 tests,
zero errors, zero failures, and 93 skips. All five full Python module scopes
passed with eight xdist workers. Bun passed 300 Web unit tests, and the full
macOS doctor returned PASS. No task-owned Gazebo or MoveIt process remains.
The existing two static transform publishers were preserved.

```yaml
checkpoint_id: CP-011
last_valid_experiment: EXP-011
current_hypothesis: The migrated install no longer requires the root-owned compatibility symlink; retiring it needs administrator authentication.
working_tree_status: Source, tests, guides, patch files, and this ledger await commit.
owned_processes: NONE
preserved_processes: Existing static_transform_publisher PIDs 1541 and 1542.
confirmed_conclusions:
  - Standard project C++ build and all registered C++ CTests pass.
  - All five relevant complete Python module pytest -n8 gates pass.
  - Bun Web unit and full macOS doctor pass.
  - Current base, dependency, fork, and project install prefixes contain no /opt/ros2_jazzy literal in scanned text or binary files.
disproven_routes:
  - The previous root-owned /opt/ros2_jazzy link can be removed by passwordless sudo in this session.
open_risks:
  - The root-owned old link remains until an administrator runs sudo unlink /opt/ros2_jazzy.
next_command: Check the review findings, commit and publish the verified changes, then inspect the old link again.
```

## Evidence retention

The registered low-rate evidence root is
`/tmp/so101-debug-macos-jazzy-path-deps-20260923-703e5272`. The active
`/opt/ros/jazzy` link, stable ROS dependency overlay, source pins, fork run,
project install, and dylib farm run are retained. The earlier fork and dylib
farm runs are retained for audit. No run was moved to an archive. The 29
task-owned short scratch directories listed in
`package-notes/scratch-deletion-candidates.txt` under the evidence root are
deletion candidates after readback; none was deleted.

## Dependency source pins

| Source repository | Commit |
| --- | --- |
| `ros-planning/moveit2` | `0b5a54206` |
| `ros-planning/warehouse_ros` | `c1e9809` |
| `ros/xacro` | `da4b3849f8320903d625250089f67f0632be86f2` |
| `moveit/moveit_resources` | `e1657c128ea61621777a041e3783c9c7c93db4ca` |
| `ros-simulation/simulation_interfaces` | `a3c60ff2715dbe5e9d5cddce410d9a7ffe771960` |
| `rudislabs/actuator_msgs` | `4594004f568b81aa5222c02f4784e6be6baa81ba` |
| `swri-robotics/gps_umd` | `ad0b508965282807ab07045b028ebc43ab942b98` |
| `apl-ocean-engineering/marine_msgs` | `14bddb417a51767600e3feada3bc7fc378d0e6f9` |
| `ros-perception/vision_msgs` | `1adca4dd009d529e08c953aaa4ff9a75ed79a22a` |
| `ros-controls/gz_ros2_control` | `7937b3093ffed51a20c9b638df0061c9bb82e610` |
| `ros_gz` (existing `extra_ws/src/ros_gz`) | `f84c00e779929b1a354591b5b0e35bdc574eacda` |
| `gazebo-release/gz_common_vendor` | `9cde321b457ad1d4e072c36ff0a851d50a1a6ca6` |
| `gazebo-release/gz_dartsim_vendor` | `b8956de4c0ae0152dada98a22693f7f0e0655706` |
| `gazebo-release/gz_fuel_tools_vendor` | `cd9a7cb58c2964aadcb46d687943be2ba309cc19` |
| `gazebo-release/gz_gui_vendor` | `b530d15e7a273159b5daf612c79b6d421b26d72b` |
| `gazebo-release/gz_msgs_vendor` | `6016bae281f2196e3522e0d2b0729eed9f4b5402` |
| `gazebo-release/gz_ogre_next_vendor` | `3c4b98201c23ccd3f6fb00cc4937cbe490808836` |
| `gazebo-release/gz_physics_vendor` | `589ad989654933c4cd85b9f557a18a0def14741a` |
| `gazebo-release/gz_plugin_vendor` | `746e24236d23653eb72a983886f4852d36e56461` |
| `gazebo-release/gz_rendering_vendor` | `d6ea9d95c88e7b2ba6cb7a8601d1edc9d459bc86` |
| `gazebo-release/gz_sensors_vendor` | `f270b684bfc9cb6e7b51affcaf992175015c659a` |
| `gazebo-release/gz_sim_vendor` | `2c82e3037c01c9eac0d723f340d8948ee8c68bfb` |
| `gazebo-release/gz_transport_vendor` | `2026b3bff03f5d2855c4bbfa57d5443de348348d` |
| `gazebo-release/sdformat_vendor` | `19d78ba3dd51e3d47c3c6501b9e1480bcb54d1f4` |
