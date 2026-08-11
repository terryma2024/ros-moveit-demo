---
task_id: so101-teleop-extraction
goal: Extract Teleop and GUI tooling into independently owned packages and validate explicit backend adapters without disturbing active robot stacks.
success_contract: Standalone so101_teleop and ai-station-gui owners pass package, Web, adapter, capture, installed-overlay, and approved live backend evidence gates; parent repository retains no duplicate capture implementation.
worktree: /data/work/ws_moveit/.worktrees/so101-teleop-extraction
branch: codex/so101-teleop-extraction
base_commit: c6982116d79c834de60b21d9e324a449a569a9c9
current_commit: e5ac41a28c3f59b71d43fb759d40aa5c2ab5601d
evidence_root: /tmp/so101-debug-teleop-extraction-20260811/
confirmed_conclusions:
  - Approved design keeps robot workflow and physics ownership in each backend module; Teleop owns only the control plane (SPEC-2026-08-11).
  - Active physical-five-success and MuJoCo GUI stacks are preserved and are not implementation test fixtures (CP-001).
  - Gazebo Python scene CLI lacks Teleop scene-repair upsert, so scene_operations must remain false initially (CP-001).
disproven_routes:
  - FULL_RESTART is not an authorized lifecycle for later validation; use RESET_WORLD where reset is required (prior user decision).
open_hypotheses:
  - Gazebo C++ and Gazebo Python installed owner envelopes can preserve the existing Teleop workflow/session semantics through fixed CLI profiles.
  - Full desktop capture remains valid when RViz and Ghostty are both absent.
latest_checkpoint: CP-004
next_experiment: NONE
---

# SO-101 Teleop Extraction Experiment Ledger

This ledger begins before implementation. Automated RED/GREEN/build evidence is recorded in commits and `/tmp`; live experiments will be added as `PLANNED` entries before any new stack, reset, workflow command, GUI action, or capture validation.

## CP-001 — Approved design and execution start

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: Fixed installed CLI profiles can preserve control-plane semantics without moving robot workflow ownership.
working_tree_status: clean at 3cba80f before this ledger and plan correction
owned_processes: NONE
preserved_processes: physical-five-success Gazebo/RViz/move_group; existing MuJoCo GUI; codex-cua and other user tmux sessions
confirmed_conclusions:
  - Standalone worktree and three implementation plans are committed.
  - Current Gazebo Python scene owner lacks upsert and cannot honestly expose Teleop scene repair.
disproven_routes:
  - No compatibility wrapper at the old C++ Teleop or tiler entry.
open_risks:
  - CMake ownership moves must be atomic so neither package has a broken intermediate commit.
  - Live backend validation requires an isolated domain/partition or explicit authorization to reuse a verified idle stack.
next_command: Write and run the Task 1 package ownership RED test.
```

## CP-002 — Ownership RED complete; shared X11 dependency decision required

```yaml
checkpoint_id: CP-002
last_valid_experiment: NONE
current_hypothesis: The standalone package move is valid, but X11 helper ownership must preserve non-Teleop diagnostic commands without reversing dependencies.
working_tree_status: dirty with tracked Teleop/Web/config/docs/server moves into src/so101_teleop plus untracked src/so101_teleop/test/test_launch_contract.py; no implementation edits applied after the moves
owned_processes: NONE
preserved_processes: physical-five-success Gazebo/RViz/move_group; existing MuJoCo GUI; codex-cua and other user tmux sessions
confirmed_conclusions:
  - Task 1 ownership contract failed RED for exactly the missing standalone owner and present legacy owner, then committed as a54598f.
  - New launch contract failed RED because the standalone launch path does not yet exist.
  - ai_station_x11.py is imported by gazebo_window_recorder.py and so101_stack_inventory.py in addition to tile_ai_station_guis.py.
disproven_routes:
  - Deleting ai_station_x11.py while leaving the two dependent C++ diagnostic commands unchanged would create a broken installed package.
  - Making so101_gazebo_demo_cpp depend on so101_teleop violates the approved dependency direction.
open_risks:
  - Moving the two additional diagnostic commands changes their package owner beyond the explicitly named tiler migration.
  - Retaining a C++ copy leaves two X11 helper owners and weakens the intended extraction boundary.
next_command: NONE pending user selection between moving the dependent diagnostic commands or retaining a backend-local X11 helper copy.
```

## CP-003 — Shared X11 owner selected; GREEN migration resumed

```yaml
checkpoint_id: CP-003
last_valid_experiment: NONE
current_hypothesis: A single X11 owner in so101_teleop can support tiling, read-only stack inventory, and Gazebo window recording without a reverse dependency from the C++ robot package.
working_tree_status: HEAD 58cd719 contains the mechanical Teleop move; launch RED test is untracked and the package remains intentionally non-buildable until this GREEN step completes
owned_processes: NONE
preserved_processes: physical-five-success Gazebo/RViz/move_group; existing MuJoCo GUI; codex-cua and other user tmux sessions
confirmed_conclusions:
  - The user selected moving both dependent diagnostic commands and their tests into so101_teleop.
  - gazebo_window_recorder.py and so101_stack_inventory.py are operator diagnostics, not C++ robot behavior owners.
  - The new package will expose one importable so101_teleop.gui.x11 implementation and install all three operator commands as executables.
disproven_routes:
  - Keeping a second C++-local X11 implementation is unnecessary under the selected ownership model.
  - A C++ dependency on so101_teleop remains forbidden.
open_risks:
  - Source-tree script tests must explicitly expose the new Python package root before importing installed-style modules.
  - Both CMake install/test manifests must change atomically before the next commit.
next_command: Move the three diagnostic commands and four tests, then implement the standalone package CMake, launch, and installed lookup GREEN changes.
```

## CP-004 — Standalone package and shared GUI diagnostics GREEN

```yaml
checkpoint_id: CP-004
last_valid_experiment: NONE
current_hypothesis: Immutable installed backend profiles can now replace the remaining hard-coded Gazebo C++ owner lookup without moving workflow logic into Teleop.
working_tree_status: implementation committed as b95432c; only this ledger checkpoint remains dirty
owned_processes: NONE
preserved_processes: physical-five-success Gazebo/RViz/move_group PIDs 580035/580038/580060/580061/581537; move_group PID 2049562; existing MuJoCo GUI; codex-cua and other user tmux sessions
confirmed_conclusions:
  - so101_teleop owns the Web/FastAPI/Python package, launch, tiler, stack inventory, Gazebo recorder, and one importable gui.x11 implementation.
  - Explicit backend is required by launch; the extraction checkpoint accepts gazebo_cpp only and freezes SO101_TELEOP_BACKEND in the server environment.
  - Focused source tests passed: GUI/ownership/launch 82 and migrated Teleop 81; Web passed 38 of 38.
  - Installed package test passed 182 tests with 0 errors, 0 failures, and 0 skipped.
  - so101_teleop build and so101_gazebo_demo_cpp build passed after first building the worktree-local pick_place_common dependency.
  - Installed ownership exposes four so101_teleop executables; the C++ package no longer exposes Teleop, tiler, inventory, or recorder commands.
disproven_routes:
  - The worktree-local C++ build cannot run before pick_place_common is installed in the same worktree overlay.
  - bun --cwd ... run test was not accepted by the installed Bun CLI; running bun commands from the Web directory is the verified form.
deviations:
  - A direct run of test_so101_launch_contract.py unexpectedly started one temporary headless Gazebo server pair, PIDs 2290778/2290780. The existing test cleaned both processes on completion; no user stack was stopped or modified. Do not repeat this file outside a PLANNED isolated test lifecycle.
open_risks:
  - server.py still resolves so101_gazebo_demo_cpp executables directly; backend profiles and the fixed registry are not implemented yet.
  - No live Teleop backend validation is claimed at this checkpoint.
next_command: Write RED tests for frozen backend profiles, fixed backend IDs, strict schema rejection, and probe-only MuJoCo capabilities.
```

## EXP-001 — Isolated installed-package contract suite

```yaml
experiment_id: EXP-001
status: COMPLETE
hypothesis: The extracted Teleop owner and the unchanged C++ robot owner pass their installed package suites together without observing or modifying the preserved live stacks.
source_commit: e5ac41a28c3f59b71d43fb759d40aa5c2ab5601d
branch: codex/so101-teleop-extraction
overlay: /data/work/ws_moveit/.worktrees/so101-teleop-extraction/install/setup.zsh
installed_owners:
  - /data/work/ws_moveit/.worktrees/so101-teleop-extraction/install/so101_gazebo_demo_cpp
  - /data/work/ws_moveit/.worktrees/so101-teleop-extraction/install/so101_teleop
runtime_executable: colcon test --packages-select so101_gazebo_demo_cpp so101_teleop
lifecycle: REUSE_STACK
isolation:
  ros_domain_id: Per-test unique values from test_so101_pick_place_world.py, beginning at 100 + pytest PID modulo 100.
  gz_partition: Per-test UUID-suffixed so101_task1 and so101_task1_ready partitions; one one-iteration static world check uses so101_pick_place_world_contract.
owned_processes: Only subprocesses created by this test invocation; test cleanup may stop those exact child process groups.
preserved_processes: physical-five-success Gazebo/RViz/move_group; existing MuJoCo GUI; codex-cua and all other user/agent tmux sessions
motion_scope: Isolated headless test fixtures only; no commands target the preserved live ROS domain or Gazebo partition.
evidence_dir: /tmp/so101-debug-teleop-extraction-20260811/exp-001-installed-package-tests
success_gate: colcon test completes and colcon test-result --verbose reports zero errors and zero failures for both selected packages; post-test inventory shows no surviving test-owned Gazebo children.
abort_gate: Any evidence that a test resolves the preserved live ROS domain/partition, any unowned process cleanup target, or any attempt to stop/take over another agent process.
observed_result:
  - so101_teleop passed all 24 CTest entries.
  - so101_gazebo_demo_cpp passed all 67 CTest entries, including the isolated headless Gazebo contracts and C++ quality gate.
  - colcon test-result reported 1000 tests, 0 errors, 0 failures, and 8 skipped.
  - Post-test process audit found no surviving task1/task1_ready/world-contract process; only the audit shell and rg command matched their own query text.
conclusion: The extracted Teleop and C++ robot owners pass together from the worktree-installed overlay without leaking isolated test children or disturbing preserved stacks.
next_command: Commit the Task 10 ownership boundary and proceed to the ai-station-gui skill TDD plan.
```
