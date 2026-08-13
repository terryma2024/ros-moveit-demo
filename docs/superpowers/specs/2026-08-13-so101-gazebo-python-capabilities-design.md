# SO-101 Gazebo Python Capabilities Design

**Date:** 2026-08-13
**Status:** Approved for inline execution
**Scope:** `so101_demo_py` Gazebo Planning Scene, camera presets, transactional reset, and normal workflow execution

## Objective

Make the canonical `so101_demo_py` package own one backend-selectable public surface for Planning Scene setup, camera presets, and Teleop reset. The Gazebo implementation must expose the same user-facing operations as MuJoCo while retaining simulator-specific adapters, explicit evidence, and fail-closed behavior. The work must not change the frozen qualified MuJoCo policy at `config/policies/light_cup_wall_pick/v1/mujoco.yaml`, whose required SHA-256 is `aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356`.

The target branch is `codex/so101-demo-py-canonical` in `/data/work/ws_moveit/.worktrees/so101-demo-py-canonical`, based on `1fa155e1524fc24b7059e76eb88540abda327ba6`. No work may modify main, push, merge, clean another worktree, use the real robot, or depend on the legacy `so101_gazebo_demo_cpp` executable or configuration.

## Public Contract

The installed package continues to publish exactly these shared public CLIs:

- `scene_setup [--backend mujoco|gazebo] ...`
- `camera_preset [--backend mujoco|gazebo] PRESET`
- `teleop_reset [--backend mujoco|gazebo] ...`

MuJoCo remains the compatibility default so existing invocations without `--backend` retain their behavior. Teleop profiles pass an explicit backend. No `gazebo_scene_setup`, `gazebo_camera_preset`, or `gazebo_teleop_reset` executable is added.

Every command emits a machine-readable receipt containing the backend, phase, success flag, stable failure code, and evidence fields. Failures return nonzero at the first failed phase. A command that has changed only part of the world must still report failure; it must never claim partial success.

## Architecture

Dependency direction remains inward:

```text
CLI / ROS composition
        |
        v
application transaction coordinators
        |
        v
typed ports, requests, receipts, failures
        ^
        |
MuJoCo adapter | Gazebo adapter | MoveIt adapter
```

Shared schema and orchestration code may know backend-neutral object, pose, goal, and receipt types. Simulator commands, Gazebo service names, ROS messages, teleport operations, and MuJoCo viewer transport remain in backend adapters. The future real-arm adapter can implement the same application ports, but the current real backend remains fail-closed and no physical-arm I/O is introduced.

## One Geometry Contract

`assets/common/geometry-manifest.yaml` becomes the sole task-geometry contract for `table`, `pedestal`, and `plastic_cup`. It records, for every object:

- canonical ID and frame;
- six-degree pose, with translation plus normalized quaternion;
- primitive type and dimensions;
- primitive-local pose where an object has multiple primitives;
- RGBA color.

The required primitive counts are exact: table `1`, pedestal `1`, plastic cup `13` (twelve wall boxes and one cylinder bottom). The initial cup pose and all object dimensions remain numerically identical to the current qualified scene.

A backend-neutral manifest loader validates required IDs, finite dimensions, quaternion normalization, unique primitive names, and exact primitive counts. A MoveIt builder consumes only the parsed manifest to create collision objects. `scene_setup` applies all three objects through MoveIt, then performs `/get_planning_scene` read-back and verifies IDs, world membership, attachment state, primitive counts, dimensions, and six-degree poses within declared tolerances.

The Gazebo world SDF remains a simulator artifact, not a second source of truth. A parity test parses the SDF and proves that its model IDs, link collision geometry, colors, dimensions, and initial six-degree poses match the common manifest. The Gazebo model currently named `base_pedestal` is renamed to the canonical `pedestal`. A mismatch is a test/build failure.

Both `mujoco` and `gazebo` modes perform apply plus read-back. Backend selection controls readiness and physical-world verification, not the MoveIt object definition.

## Gazebo Launch Gate

Gazebo launch is changed from elapsed-time sequencing to an explicit ordered gate:

```text
Gazebo/spawn -> controllers ready -> move_group ready
             -> scene_setup succeeds -> gazebo_execute starts
```

The readiness phase checks the expected controllers and MoveIt services rather than treating process start as readiness. `scene_setup` must exit zero before the workflow process is emitted. Any failure prints the first failed launch phase and stable failure code. The workflow is not started after a setup failure.

`gazebo_execute` is a normal bounded workflow, not a MuJoCo qualification candidate. It executes the configured motion, gripper, scene, and release phases and reports the phase where it actually succeeds or fails. It must not deliberately reject a successful phase, rewrite failure as `SKIPPED` or `INVALID`, or gate MuJoCo qualification. A successful Gazebo run is explicitly `SUCCEEDED` and `NOT_QUALIFIED`.

## Camera Presets

Camera preset names, pose schema, validation rules, receipt fields, and stable errors are shared. Backend-owned YAML and adapters are separate:

- MuJoCo keeps its current preset file and viewer adapter unchanged in meaning.
- Gazebo presets live under `so101_demo_py/config/gazebo/` and are owned by this package.
- The Gazebo adapter invokes `/gui/move_to/pose` with the required Gazebo message types and accepts success only when the Boolean reply acknowledges the request.

Unknown preset, malformed schema, unavailable service, timeout, rejected acknowledgement, and transport failure receive distinct stable failure codes. Teleop's `gazebo_py` camera operation passes fixed arguments `--backend gazebo`; MuJoCo continues to work with its existing name-only invocation.

Live camera acceptance uses a fresh GUI snapshot before the action and a fresh snapshot after it. The action is only valid if the adapter acknowledgement is positive and the new image is visually inspected to confirm a real viewpoint change. `cua-driver` snapshot/action/fresh-snapshot is preferred; the project `ai-station-gui` workflow is the fallback.

## Transactional Gazebo Reset

Gazebo reset is an independent application transaction. It does not call or reuse the MuJoCo reset implementation. Its ordered phases are:

1. Observe initial Gazebo object pose and attachment, MoveIt world/attached state, controller state, arm/gripper joint positions and velocities, and TF.
2. Cancel outstanding arm goals and wait for terminal acknowledgement.
3. Cancel outstanding gripper goals and wait for terminal acknowledgement.
4. Request physical Gazebo detach and verify the cup is detached.
5. Detach the cup in MoveIt and verify it is not attached.
6. Move the physical cup to a configured safe parking pose through the Gazebo adapter and verify its full pose.
7. Synchronize table, pedestal, and parked cup into the Planning Scene and verify read-back.
8. Command the gripper fully open and verify position and stopped velocity.
9. Ask MoveIt for an exact plan to the named arm state `Home`; reject an approximate or missing plan.
10. Execute that exact plan and verify arm joint positions and velocities.
11. Restore the physical cup to the manifest spawn pose and verify its full pose.
12. Synchronize and verify the final Planning Scene.
13. Perform one final independent observation of Gazebo pose/attachment, MoveIt membership/attachment/pose and `1/1/13` primitive counts, controllers, joints, velocities, and TF.

The application layer defines the transaction phases, ports, receipts, and stable errors. Gazebo physical detach and pose teleport belong only to the Gazebo adapter. MoveIt scene synchronization, named-state planning/execution, action cancellation, joint observation, and TF observation are separate ports/adapters. This keeps the control flow reusable for a future real arm while ensuring a real implementation cannot silently inherit simulator teleport behavior.

Reset configuration contains tolerances, action/service timeouts, controller names, `Home`, fully-open gripper target, and the safe parking pose. It must not modify or derive from the frozen MuJoCo qualification policy.

No rollback is claimed after an external simulator mutation. Instead, each phase records before/after observations and the command receipt; any failure stops subsequent phases, returns nonzero, and identifies the exact residual state in evidence. Only completion of all thirteen phases is reported as transactional success.

## Teleop Integration

The `gazebo_py` backend profile advertises:

- `scene_operations: true`
- `reset_world: true`
- `camera_presets: true`

The owner package for workflow, scene, reset, and camera is `so101_demo_py`. Fixed arguments select `--backend gazebo`. Camera and reset requests execute their configured command rather than being declined as unsupported. The MuJoCo profile preserves existing CLI compatibility and qualified-policy behavior.

Source and installed documentation must describe the same capability matrix and remove the stale claim that Gazebo scene, camera, or reset operations are unavailable.

## Error and Evidence Contract

Stable failures use a namespaced code family rather than exception text, for example:

- `SCENE_MANIFEST_INVALID`, `SCENE_APPLY_FAILED`, `SCENE_READBACK_MISMATCH`
- `CAMERA_PRESET_UNKNOWN`, `CAMERA_SERVICE_UNAVAILABLE`, `CAMERA_ACK_REJECTED`
- `RESET_OBSERVE_FAILED`, `RESET_ARM_CANCEL_FAILED`, `RESET_GAZEBO_DETACH_FAILED`, `RESET_HOME_PLAN_FAILED`, `RESET_FINAL_VERIFY_FAILED`
- `GAZEBO_WORKFLOW_<PHASE>_FAILED`

Each receipt contains command/provenance, monotonic timestamps, configured tolerance, observed values, and the first failure. Live evidence is stored beneath one task-specific `/tmp` root. The experiment ledger is updated before each live run through `PLANNED`, `RUNNING`, and exactly one terminal state: `VALID` or `INVALID`. `INVALID` means infrastructure/evidence invalidity and stops its batch; a valid product failure is recorded as `VALID` with a failed outcome and stops a qualification sequence.

## Test and Acceptance Strategy

All behavioral changes follow RED then GREEN. Unit and contract tests cover:

- manifest schema, exact IDs/counts/poses/dimensions/colors, and SDF parity;
- backend dispatch and backward-compatible CLI parsing;
- MoveIt apply/read-back success and every mismatch class;
- camera schema, Gazebo command construction, acknowledgement and error mapping;
- every reset phase, phase ordering, first-failure stopping, and final verification;
- Gazebo workflow honest outcome semantics and launch event gating;
- Teleop profile ownership, fixed arguments, capability flags, and request dispatch.

Verification requires nonzero collected tests, all `so101_demo_py` tests, affected `so101_teleop` tests, the repository's existing scoped Ruff checks, `git diff --check`, and the unchanged policy hash. A fresh isolated colcon build and freshly sourced overlay must prove package prefix, executable discovery, and installed-file provenance.

Live acceptance then proves:

1. Planning Scene apply/read-back with exact `1/1/13` primitives.
2. An acknowledged Gazebo camera preset switch with inspected before/after screenshots.
3. A deliberately disturbed arm and cup followed by complete reset, with independent evidence from Gazebo pose/attachment, MoveIt pose/membership/attachment, controllers, joints/velocities, TF, and the GUI.
4. On the final committed tree, unchanged policy, and fixed geometry contract, five consecutive independent `FULL_RESTART` qualified MuJoCo successes. Each attempt has its own experiment ID, provenance, and evidence. A valid failed outcome stops the sequence; an invalid experiment stops the batch. Historical wins do not count.

Only task-owned PIDs may be stopped. Broad process-kill commands are forbidden, and unrelated tmux sessions and runtime state must be preserved.

## Completion Boundary

The work is complete only when the spec, implementation plan, source, tests, documentation, ledger, and provenance are committed; all static/build/installed/live gates pass; the final five-run sequence succeeds on one commit; the policy hash still matches; and the target worktree is clean. Completion does not authorize pushing, merging, modifying main, operating a real arm, or cleaning any other worktree.
