# MuJoCo dual cup pick-place end-to-end validation plan

**Design:** `docs/superpowers/specs/2026-08-24-mujoco-dual-cup-e2e-design.md`

**Evidence root:** `/Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z`

## Phase 1: Register and audit the local environment

- [x] Register the persistent evidence root and document the `/data/work` read-only-root exception.
- [x] Create a unique ordinary debug root under `/tmp/so101-debug-*`.
- [x] Record repository commit, worktree status, package prefixes, installed executables, ROS distribution, and Python environment.
- [x] Build `so101_demo_py` with `--symlink-install`.
- [x] Run the direct package test suite with an isolated `ROS_LOG_DIR`.
- [x] Prove the headless MuJoCo/MoveIt/controller/evidence stack starts in an isolated ROS domain.

## Phase 2: Qualify the fixed executable

- [x] Detect and correct stale-overlay shadowing by placing the pinned macOS MuJoCo fork first.
- [x] Start a fresh GUI-enabled stack and retain a baseline viewer screenshot.
- [x] Run `fixed_cup_pick_place` with the qualified V1 motion/contact policies.
- [x] Prove exit `0`, `DONE`, all nine phases, and no failed phase.
- [x] Prove final physical placement, release, support, stability, upright pose, and no fingertip contact.
- [x] Prove Planning Scene detach/world-object convergence and controller health.
- [x] Retain and visually inspect descent, transport, and final screenshots.
- [x] Seal EXP-004 as the single successful fixed-position demonstration.

## Phase 3: Implement and qualify dynamic execution

- [x] Add the perception-driven dynamic execute path without changing V1 semantics.
- [x] Keep one shared `StateMachineRunner` and workflow lifecycle.
- [x] Require a fresh valid `/cup_pose`; reject invalid samples and forbid fixed-pose fallback.
- [x] Add dynamic strategy derivation, segmented trajectory execution, underactuated IK, narrow ACM use, and physical gates.
- [x] Add the MuJoCo-to-`/cup_pose` test bridge as an observation-only adapter.
- [x] Add/update unit, contract, package-identity, and installed-provenance tests.
- [x] Run the full package suite after implementation (248 tests passed at the implementation checkpoint).

## Phase 4: Prove dynamic runtime and physics

- [x] Start a clean headless MuJoCo stack with a unique session and reset epoch.
- [x] Start the observation bridge and prove it publishes the current MuJoCo cup pose.
- [x] Run `dynamic_cup_pick_place` in execute mode.
- [x] Prove exit `0`, `DONE`, and the exact 19-action dynamic state trace.
- [x] Prove the retained input pose and absence of V1 fallback.
- [x] Prove final physical placement, release, support, stability, upright pose, no fingertip contact, Planning Scene convergence, and controller health.
- [x] Seal EXP-006 as a headless numeric/runtime success, explicitly not the final visual qualification.

## Phase 5: Capture dynamic visual evidence

- [x] Diagnose native macOS GUI startup failures rather than counting black screenshots.
- [x] Add and rebuild the external GLFW/MuJoCo monitor-null and VSync guards required when the host starts without an active primary display.
- [x] Start the EXP-007 r5 GUI MuJoCo/MoveIt/controller stack and prove model/controller initialization.
- [x] Unlock and keep the macOS desktop session visible.
- [x] Move the off-screen native viewer onto the primary desktop and retain a valid baseline.
- [x] Start the observation bridge for the same session/reset epoch.
- [x] Run `dynamic_cup_pick_place` against the visible stack; retain EXP-007 as failed because post-release retreat planning collided with the restored world cup.
- [x] Add RED/GREEN regression coverage and narrowly allow cup/gripper contact only during `RETREAT` and `RECOVER_RETREAT`, restoring normal collision checks immediately afterward.
- [x] Full-restart as EXP-008 and reach `DONE` with transition count 19.
- [x] Retain and inspect `in-motion-descent.png`, `transport.png`, and `final.png`.
- [x] Re-prove final numeric, Planning Scene, and controller gates for the GUI run.
- [x] Seal EXP-008 as the valid dynamic GUI demonstration.

## Phase 6: Final regression and evidence sealing

- [x] Stop all task-owned bridge/workflow/stack processes with one clean SIGINT each.
- [x] Re-run the complete `so101_demo_py` test suite and retain its output (250 passed).
- [x] Re-run the package build and retain its output (one package finished).
- [x] Re-source the overlay and retain executable discovery for `fixed_cup_pick_place` and `dynamic_cup_pick_place`.
- [x] Run and retain `git diff --check` plus final `git status --short`.
- [x] Hash all retained final evidence and record file sizes.
- [x] Update the experiment ledger through the final checkpoint.
- [x] Report retained runs, archived runs, and deletion candidates without deleting evidence.

## Completion state

EXP-004 and EXP-008 satisfy the requested fixed and dynamic single-run MuJoCo acceptance contract. Executable discovery, diff checks, the 140-file hash/size inventory, and the retained evidence report are sealed for handoff.
