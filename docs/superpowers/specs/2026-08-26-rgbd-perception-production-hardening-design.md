# RGB-D Perception Pick-Place Production Hardening Design

**Date:** 2026-08-26

**Status:** Proposed for user review

**Task branch:** `codex/rgbd-perception-pick-place`

**Reviewed parent HEAD:** `f5def65331a47e0d681855214f6e39b80c111ff0`

**Implementation under review:** `a8b3d87ac08dc124e0d54f27fbee93f62c8cfb4a`

**MuJoCo submodule:** `f19a8cc3af61feccacb22a9f0d16cc972e3b2c08` (`so101-0.0.3-r8-3-gf19a8cc`)

**Registered evidence root:** `/tmp/so101-debug-rgbd-perception-pick-place-20260826/`

## Context and decision

EXP-017 through EXP-020 independently proved the production RGB-D-to-pick-place chain at the four frozen initial keyframes. The source, tests, fresh overlay, runtime provenance, physical outcome, GUI evidence, and cleanup gates all passed for implementation `a8b3d87a`.

The final code review nevertheless found three production-boundary gaps and two packaging-contract gaps. The task is therefore not complete at `f5def653`: the accepted runs remain immutable, valid historical evidence for `a8b3d87a`, but they cannot qualify the hardened implementation that will replace it.

The approved direction is a minimal boundary hardening change. It does not redesign perception, manipulation, or the launch graph. It closes the identified fail-open and overwrite paths at their existing ownership boundaries, proves them first with focused regression tests, and then repeats the four full-restart physical runs under new provenance.

## Scope

The hardening includes:

1. Preserve the first terminal status while monitoring every required process in the MuJoCo execute launch graph.
2. Prove MuJoCo session identity, reset epoch, and unpaused state before any Planning Scene mutation.
3. Make each session evidence directory exclusive so a repeated session cannot overwrite an accepted run.
4. Complete installed-executable provenance coverage for the production runner.
5. Declare the Linux OpenGL/EGL build dependencies used by `so101_mujoco_support`.

## Non-goals

- No segmentation, point-cloud, cylinder-fit, pose transform, radius, or confidence changes.
- No changes to frozen policy, thresholds, keyframes, target geometry, grasp, attachment, placement, or recovery behavior.
- No new central supervisor abstraction and no broad launch rewrite.
- No change to the exact `f19a8cc3af61feccacb22a9f0d16cc972e3b2c08` MuJoCo plugin provenance.
- No reuse of the superseded r6 overlay or the old failed fetch route.
- No deletion, rewriting, or migration of existing evidence. EXP-017 through EXP-020 and CP-016 remain immutable history.

## Design

### 1. Status-preserving required-process lifecycle

The existing `PerceptionLaunchExitStatus` remains the single owner of the process exit code. It records only the first terminal status; shutdown events from later teardown cannot replace an earlier failure.

The MuJoCo execute graph will remove the simulator node's direct `on_exit=Shutdown(...)`. Instead, launch-level exit handlers will cover these process roles:

- required long-lived processes: MuJoCo `ros2_control_node`, `robot_state_publisher`, `move_group`, static TF publisher, and RGB-D perception publisher;
- required one-shot predecessors: scene setup and every controller spawner;
- terminal workflow: dynamic pick-place runner.

The lifecycle rules are:

- A required long-lived process exiting before the workflow becomes terminal is unexpected. Its nonzero return code is preserved; an unexpected clean exit is normalized to status `1`. The handler emits a role-specific terminal diagnostic and requests global shutdown.
- A required one-shot predecessor returning nonzero records that exact status and requests shutdown. A successful scene setup advances the launch graph. A successful controller spawner is expected to exit and does not terminate the graph.
- The workflow handler marks the workflow terminal before requesting shutdown and preserves its exact return code. Required-process exits caused by that teardown are ignored for status purposes.
- Once any terminal status exists, all later handlers may request idempotent shutdown but cannot overwrite the status. This covers near-simultaneous failures deterministically.
- Dry-run and Gazebo paths retain their existing behavior unless they share the status object directly and a focused test demonstrates that the common helper is behavior-preserving.

Focused launch tests will inject each process exit independently. They must prove exact nonzero propagation, normalized failure for an unexpected zero exit, correct successful predecessor advancement, successful workflow status, ignored expected teardown, and first-failure-wins ordering.

### 2. Fail-closed MuJoCo identity preflight

The dynamic runtime currently obtains a truth observation and then mutates the Planning Scene before the execution layer checks reset provenance. That ordering permits a wrong-epoch or paused simulator snapshot to influence MoveIt.

`CupSceneObservation` will expose optional simulator identity fields so the abstraction remains usable by non-MuJoCo backends:

- `simulation_session_id: str | None`
- `reset_epoch: int | None`
- `paused: bool | None`

The MuJoCo observer factory will accept both the expected session ID and expected reset epoch. Its first observation must contain:

- the exact expected session ID;
- the exact expected reset epoch;
- `paused is False`.

Missing, mismatched, or paused identity is a terminal preflight error. Validation occurs immediately after the first truth observation and before constructing or calling the task-scene mutation port. Existing pose, attachment, timestamp, and convergence validation remains unchanged and follows the identity gate.

Regression tests will inject a mismatched session, mismatched epoch, missing identity, and paused snapshot. Each case must return nonzero with a stable failure code and prove zero Planning Scene mutation calls. A valid unpaused snapshot must preserve the current flow.

### 3. Exclusive session evidence allocation

The derived task container `<evidence-file-stem>.d` remains reusable because it holds distinct runs. Its ownership, directory type, symlink, resolution, and path-containment checks remain fail-closed.

The child `<derived-root>/<session-id>` is different: it is an immutable run boundary. It must be created atomically with `mkdir(mode=0o700, exist_ok=False)`. Any pre-existing filesystem entry at that path, including an empty owned directory, is an error. `perception/` and `dynamic/` are created only after that exclusive allocation succeeds.

The nominal `evidence_file` path must also be absent before launch preparation so the command cannot reuse or overwrite a prior top-level artifact. The implementation does not remove, truncate, or repurpose any existing path after a collision.

Tests will prove that an existing base container is accepted, a fresh session is allocated, an existing session is rejected without modifying its contents, an existing nominal evidence file is rejected, and all existing symlink/ownership/path-escape protections remain in force.

### 4. Installed provenance and build dependency contracts

The installed-provenance executable set will include `so101_mujoco_perception_pick_place`, making the public production runner subject to the same source/install identity gate as the other CLIs.

`so101_mujoco_support/package.xml` will declare the rosdep-resolvable Linux build dependencies corresponding to the existing `find_package(OpenGL REQUIRED COMPONENTS EGL)` call. The exact dependency keys will be selected only after `rosdep resolve` succeeds on ai-station. CMake behavior itself does not change.

## Test-first implementation sequence

Each boundary starts with a failing regression and is implemented only after the failure proves the gap:

1. Add lifecycle failure-injection tests, observe RED, implement the shared handlers, then run the focused launch suite.
2. Add identity/preflight tests proving zero scene calls, observe RED, implement observation/factory validation, then run the dynamic runtime and scene-sync suites.
3. Replace the current existing-session acceptance test with exclusive-allocation cases, observe RED, implement atomic allocation, then run path-safety tests.
4. Add the installed runner expectation and package dependency checks, observe RED where applicable, then update package metadata.

The source verification gate is:

- all focused tests green;
- the complete affected Python suite at least matches the prior 375 passing tests;
- Ruff check and formatting checks pass without broad reformatting;
- all five task packages rebuild into the same fresh task-owned overlay;
- installed CLI ROS-argument smoke tests pass;
- `rosdep resolve` confirms the new package dependency keys;
- task worktree, submodule, canonical main, owned processes, ROS domains, tmux, Viewer, and evidence provenance checks pass.

## Runtime reacceptance

Any production-code change creates new implementation provenance. EXP-017 through EXP-020 therefore remain retained and valid only for `a8b3d87a`; they are not counted toward the hardened commit.

After source verification, four new independent FULL_RESTART runs will be frozen, using unique ROS domains, session IDs, partitions, tmux names, GUI sessions, and evidence directories:

- EXP-021: `task_start`
- EXP-022: `cup_test_forward_5cm`
- EXP-023: `cup_test_left_5cm`
- EXP-024: `cup_test_right_5cm`

Each run must repeat the existing acceptance gates: production CameraPlugin RGB-D, sole `/cup_pose` producer, dynamic consumer agreement, 19-state DONE trace, controller/FK/joint movement, bilateral unsupported grasp and lift, transport, release, detached final Planning Scene, final pose/upright bounds, three fresh same-session screenshots, natural exit, and exact-owned cleanup.

No separate perception-only rerun is required because this design does not change perception math or filtering. A standalone perception gate becomes mandatory again if implementation expands into those modules or the focused/full tests expose a perception regression.

## Completion gate

After EXP-024, run the final source/overlay/provenance/cleanup verification again, request a fresh final code review, and regenerate the evidence inventory as the final evidence write. The inventory must exclude its own `sha256.txt` and `sizes.txt` outputs and must verify cleanly without creating later files.

Completion requires all review findings closed, all four hardened-provenance runs accepted, the task branch pushed and clean, the exact submodule clean, canonical main untouched, no task-owned runtime residue, and a ledger checkpoint listing retained, archived, and deletion-candidate evidence. Evidence is not deleted without explicit user authorization.
