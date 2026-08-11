---
task_id: so101-teleop-extraction
goal: Extract Teleop and GUI tooling into independently owned packages and validate explicit backend adapters without disturbing active robot stacks.
success_contract: Standalone so101_teleop and ai-station-gui owners pass package, Web, adapter, capture, installed-overlay, and approved live backend evidence gates; parent repository retains no duplicate capture implementation.
worktree: /data/work/ws_moveit/.worktrees/so101-teleop-extraction
branch: codex/so101-teleop-extraction
base_commit: c6982116d79c834de60b21d9e324a449a569a9c9
current_commit: a54598f
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
latest_checkpoint: CP-002
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
