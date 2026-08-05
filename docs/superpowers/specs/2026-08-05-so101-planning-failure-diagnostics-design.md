# SO-101 Planning-Failure Diagnostics Design

**Status:** Proposed for written review

**Date:** 2026-08-05

**Selected approach:** A1 — opt-in failure artifact plus test-owned request replay

## Context

R3 observed an intermittent failure at the SO-101 physical-grasp probe:
`MICRO_LIFT_MOVEIT_PLAN_FAILED`. The production boundary currently maps all of
the following post-request outcomes to that one public failure:

- the MoveGroup action terminates with a non-success transport result;
- the action result is absent;
- MoveIt returns a non-success error code;
- MoveIt reports success but returns an empty trajectory.

The original failure did not preserve the exact request, start-state velocity
shape, Planning Scene evidence, Allowed Collision Matrix (ACM), MoveIt error
code, or trajectory metadata. Bounded diagnosis added temporary logs and
replayed the captured request twice. The baseline attempt and both replays
succeeded, each replay returned eight trajectory points, and the permitted
jaw/cup contact disappeared under the request's touch ACM. The earlier failure
therefore remains **not confirmed** and does not justify a retry, motion-policy,
collision-policy, tolerance, or geometry change.

The existing schema-v3 checkpoint is a workflow recovery contract. The
physical-grasp sidecar is durable physical validation evidence. Neither may be
extended with planner diagnostics because doing so would couple non-behavioral
debug data to resume, provenance, and force-continue semantics.

## Decision

Add an SO-101-local, failure-only planning diagnostics boundary. It is disabled
by default and enabled explicitly with a diagnostics directory. When an enabled
request-scoped micro-lift planning request fails after the request has been
constructed, the boundary writes one self-contained schema-v1 JSON artifact.
Artifact persistence is best-effort after startup validation: the workflow must
return its original failure even when diagnostic persistence fails.

Add a test-owned replay harness that can reconstruct and compare the exact
captured MoveGroup request. Its optional live mode may submit that exact request
as `plan_only`; it must never execute a trajectory.

"Deterministic replay" in this design means deterministic artifact parsing,
canonicalization, hashing, and request reconstruction. It does **not** mean that
OMPL must return the same result. A live planner outcome remains stochastic
unless a future, separately approved design establishes a controlled planner
seed and isolated world snapshot.

## Goals

- Preserve enough evidence at the first failing MoveGroup boundary to
  distinguish transport failure, missing result, MoveIt error, and empty
  trajectory without rebuilding temporary instrumentation.
- Bind every artifact to the SO-101 simulation session and policy bundle that
  produced it.
- Reconstruct the outgoing request field-for-field, with canonical JSON hashes
  that make differences inspectable.
- Preserve the original workflow failure, checkpoint, recovery, controller,
  Gazebo, and MoveIt side-effect semantics.
- Keep the feature opt-in and document its launch/CLI surface in the dedicated
  launch-parameter guide.
- Provide an offline replay contract and a guarded live `plan_only` diagnostic
  path that is unavailable from production launch files.

## Non-goals

- Do not add retries, fallback planners, seed cycling, or a second planning
  attempt to production execution.
- Do not change the micro-lift target, 2 mm safety cap, tolerances, planner ID,
  planning time, velocity/acceleration scaling, touch links, or ACM policy.
- Do not change any public workflow failure code, failure category, transition,
  recovery selection, checkpoint byte format, checkpoint sequence, session
  semantics, or physical-grasp sidecar.
- Do not move diagnostics into `pick_place_common`; the captured MoveIt request,
  SO-101 profile, task object, touch policy, and physical-grasp probe are
  robot-specific.
- Do not instrument Panda or regular SO-101 joint-segment planning in this
  round. The artifact kind is extensible, but schema-v1 supports only
  `MICRO_LIFT_WORLD_Z`.
- Do not install a general-purpose trajectory execution or arbitrary Planning
  Scene mutation tool.
- Do not claim the original intermittent failure is reproduced or fixed.

## Considered Approaches

### A1: Opt-in artifact plus test-owned request replay — selected

An explicit `planning_diagnostics_dir` enables a structured failure artifact.
The test harness validates and replays only planning requests. This adds no
default file side effect, keeps evidence durable when investigation is enabled,
and separates diagnostic provenance from workflow provenance.

Trade-off: a run that does not explicitly enable diagnostics cannot recover an
artifact after the fact. Acceptance and failure-investigation commands must
therefore enable the option deliberately.

### A2: Default-on checkpoint-sibling artifact — rejected

Deriving a diagnostic path from `checkpoint_path` would capture unexpected
failures automatically, but it would add a default file side effect to every
failed run and would visually associate diagnostics with the recovery contract.
It also makes retention and cleanup implicit. This conflicts with the selected
opt-in boundary.

### B: Structured ROS logs only — rejected

Logs are easy to add but may be truncated, interleaved, or detached from the
exact process and session. They cannot provide strict request round-trip or a
stable replay input.

### C: Extend checkpoint or physical-grasp evidence — rejected

This would contaminate behavior-bearing persistence, risk checkpoint/schema
compatibility, and make diagnostic I/O capable of affecting resume or
force-continue decisions.

## Ownership and API Boundary

The feature belongs entirely to `so101_gazebo_demo`:

- a robot-local value type describes one planning-failure artifact;
- a robot-local writer interface accepts an immutable artifact;
- a file writer owns schema-v1 JSON, canonical hashing, permissions, and atomic
  persistence;
- `MoveItJointPlanningBoundary` receives an optional diagnostics dependency;
- production assembly selects a null implementation when the option is empty;
- tests inject a memory writer and fake MoveGroup outcomes.

Do not add raw path or provenance strings to the existing long positional
constructor. Preserve the current constructor as a compatible delegating entry
and add a named diagnostics options/dependency type for production assembly.
Existing call sites, including reset, calibration, motion-matrix validation, and
tests, must retain their current behavior without edits unless they explicitly
exercise diagnostics.

`pick_place_common`, Panda, the runner, recovery policy, checkpoint store, and
physical-grasp validator must not depend on the new types.

## Configuration Contract

Add one SO-101 launch/CLI option:

| Surface | Name | Default | Meaning |
|---|---|---|---|
| launch | `planning_diagnostics_dir` | empty | Empty disables diagnostics; non-empty enables failure artifacts |
| CLI | `--planning-diagnostics-dir PATH` | absent | Passed only when the launch value is non-empty |

When enabled:

- `PATH` must be absolute;
- startup creates it with owner-only permissions when absent and verifies that
  it is a directory writable by the current process;
- invalid configuration fails before readiness checks or robot motion with a
  configuration error;
- no prior artifact is removed on fresh run or resume;
- automatic retention or cleanup is not performed; the operator owns the
  explicitly configured diagnostic directory.

When disabled, production assembly uses a null sink. It must not create a
directory, artifact, temporary file, warning, ROS action, or timing-dependent
branch beyond the null dependency check.

## Artifact Identity and Persistence

Each artifact file is named:

```text
<captured_at_unix_ns>-<process_sequence>-micro-lift-<request_sha256_prefix>.json
```

The simulation session ID remains inside the document rather than the filename,
so untrusted separator characters cannot escape the configured directory. The
writer uses an exclusive temporary file, writes mode `0600`, calls `fsync`,
atomically renames within the same directory, and syncs the directory. Existing
artifacts are never overwritten.

The canonical request and scene documents use stable key ordering and explicit
representations for missing vectors and optional values. `request_sha256` and
`scene_sha256` are computed from those canonical subdocuments, not from pretty
printing or filesystem metadata. A separate `replay_scene_fingerprint` hashes
only replay-relevant stable topology: robot model frame, world/attached object
geometry and poses, attached/touch links, and relevant ACM entries. It excludes
timestamps and the observed current robot joint state because the request
already carries its explicit start state and live feedback may contain harmless
sub-tolerance drift.

## Schema-v1

The top-level JSON object contains:

```text
schema_version: 1
artifact_kind: "SO101_PLANNING_FAILURE"
operation: "MICRO_LIFT_WORLD_Z"
captured_at_unix_ns
process_sequence
simulation_session_id
configuration_fingerprint
request_sha256
scene_sha256
replay_scene_fingerprint
request
scene
result
```

### Request evidence

`request` contains the exact values sent to MoveGroup:

- action name and planning group;
- planner ID, planning attempts, allowed planning time, workspace parameters,
  velocity scaling, and acceleration scaling;
- complete `start_state`, including joint names, positions, velocities, effort,
  multi-DOF state, `is_diff`, and explicit presence/absence markers for each
  optional vector;
- every goal constraint, including link/frame, target pose, tolerances, weights,
  and timestamps;
- `planning_options.plan_only` and the complete request-scoped Planning Scene
  diff, including the ACM entries applied for the task object and touch links;
- the requested world-Z delta and source TCP pose used to construct the target.

The serializer must preserve absent start-state velocities as absent. It must
not silently replace them with zero or NaN.

### Scene evidence

`scene` is an independent observation captured immediately before sending the
goal. It contains:

- robot model frame and current robot-state joint data;
- world collision object IDs, operation, headers, primitive/mesh/plane type
  summaries, dimensions or resource identifiers, and poses;
- attached collision object IDs, attached links, touch links, relative poses,
  and object geometry summaries;
- the relevant ACM entry names and matrix values;
- raw collision status and contact pairs before the touch exception;
- collision status and contact pairs after applying the request ACM;
- task object, table, pedestal, TCP, and attach-link identities from the active
  SO-101 profile.

This snapshot is diagnostic evidence. It is not automatically applied to the
live MoveGroup scene by the replay harness.

### Result evidence

`result` contains:

- `failure_stage`, one of `GOAL_ACCEPT_TIMEOUT`, `GOAL_REJECTED`,
  `RESULT_TIMEOUT`, `TRANSPORT_FAILURE`, `MISSING_RESULT`, `MOVEIT_ERROR`, or
  `EMPTY_TRAJECTORY`;
- the original public failure category and code;
- action transport result code when present;
- MoveIt error code and planning time when present;
- trajectory joint names, point count, first/last point shapes, duration, and
  whether the trajectory was empty;
- cancellation acknowledgement and terminal state evidence for result timeout.

The artifact must not manufacture values that were unavailable. Missing values
are encoded as `null` with a corresponding presence flag where ambiguity would
otherwise remain.

## Runtime Data Flow

1. Production assembly validates the optional diagnostics directory and creates
   either a file writer or null sink.
2. The micro-lift boundary constructs the same MoveGroup request it constructs
   today.
3. Immediately before submission it canonicalizes the exact outgoing request
   and captures the independent local scene/contact evidence.
4. A successful plan follows the existing execution path and emits no artifact.
5. A post-request planning failure is classified for diagnostic purposes and
   passed to the sink exactly once.
6. The boundary returns the same action status, public failure category, public
   failure code, and message that the current implementation would return.
7. Recovery, checkpointing, and physical-grasp evidence continue from that
   unchanged failure.

Diagnostic classification is additional evidence only. For example, a
non-success MoveIt error still returns `MICRO_LIFT_MOVEIT_PLAN_FAILED`; its
specific error code and `MOVEIT_ERROR` stage live only in the artifact.

## Diagnostic-Write Failure Semantics

Directory configuration errors are detected before the workflow can move and
fail with a dedicated configuration error.

After planning has begun, an artifact serialization or write failure must:

- emit one throttled warning containing a diagnostic-specific error code and
  the configured directory, without dumping the request into logs;
- return the original planning/cancellation failure unchanged;
- not add, remove, or modify a checkpoint or physical-grasp sidecar;
- not retry planning, execute a trajectory, alter the Planning Scene, or select
  a different recovery edge;
- not append a secondary failure to `original_failure` or mutate failure
  metrics used by workflow logic.

## Replay Harness

The replay harness is built only under `BUILD_TESTING` and is not installed by
the package. Production launch files cannot invoke it.

It has two modes:

### Offline round-trip

- parse schema-v1 strictly and reject unknown schema versions or missing
  required fields;
- recompute and verify request and scene hashes;
- reconstruct the MoveGroup goal from the artifact;
- canonicalize the reconstructed goal and require exact equality with the
  stored request;
- perform no ROS graph, Planning Scene, controller, Gazebo, filesystem, or
  checkpoint mutation.

### Guarded live plan-only replay

- require an explicit live flag, artifact path, expected simulation session ID,
  and expected configuration fingerprint;
- connect to the already selected single R3 stack; never start a second stack;
- observe the current scene and refuse submission when its stable
  `replay_scene_fingerprint` does not match the artifact, reporting
  `REPLAY_SCENE_MISMATCH`; timestamps and current feedback joints are reported
  separately but do not participate in that fingerprint;
- submit the reconstructed MoveGroup goal with `plan_only=true`;
- never call `MoveGroupInterface::execute`, a trajectory controller action, or
  any Gazebo/Planning Scene mutation service;
- print and persist replay outcome separately without changing the original
  artifact.

A matching request and scene do not require the same OMPL outcome. The harness
reports success, failure, MoveIt code, planning time, and trajectory metadata as
new evidence; it never rewrites history or labels a different outcome as a test
failure by itself.

## Compatibility and Migration

- Checkpoint schema remains v3 and checkpoint bytes do not gain diagnostic
  fields.
- Physical-grasp evidence remains schema v1 and retains its current path and
  validation semantics.
- `simulation_session_id`, policy bundle fingerprint, resume, force-continue,
  plan-only, stop-after, and recovery semantics remain unchanged.
- Existing `MoveItJointPlanningBoundary` construction remains source compatible.
- Existing launch commands remain behaviorally identical because the new launch
  argument defaults to empty.
- The dedicated launch-parameter guide and SO-101 README document the opt-in
  option, artifact ownership, no-retention rule, replay limitations, and the
  fact that artifacts are diagnostic rather than resumable state.
- No existing artifact migration is required; this is a new, independently
  versioned file family.

## Risks and Mitigations

### Artifact does not represent the actual request

Mitigation: capture the final outgoing message, hash canonical message fields,
and require strict offline round-trip equality in tests.

### Captured local scene differs from MoveGroup's internal scene

Mitigation: label it as an independent observation, capture timestamps and
scene hash, and never claim it is the server's hidden internal snapshot. A live
replay is refused when the observable scene differs.

### Diagnostics alter the public failure

Mitigation: make persistence best-effort after startup and test the exact
original `ActionResult`, checkpoint bytes, transition count, trace, and recovery
selection under writer failure.

### Replay accidentally moves the robot

Mitigation: test-only target, no install rule, strict `plan_only`, no executor
dependency, controller-goal assertions, and before/after joint, TCP, Gazebo, and
Planning Scene evidence.

### Optional diagnostics silently miss failures

Mitigation: acceptance and investigation commands must explicitly set
`planning_diagnostics_dir`; startup prints one provenance line stating enabled
directory or `disabled`. Ordinary users retain the selected no-side-effect
default.

### Artifact accumulation

Mitigation: diagnostics are opt-in, files never overwrite one another, and
documentation assigns retention and cleanup to the operator. Automatic deletion
is intentionally outside this round.

## Acceptance Rules

Implementation is acceptable only when all of the following are independently
verified:

1. **Default compatibility:** with an empty launch value or absent CLI flag, no
   diagnostic directory or file is created and existing CLI/launch behavior is
   unchanged.
2. **Startup validation:** an enabled relative, non-directory, or unwritable
   path returns `PLANNING_DIAGNOSTICS_DIR_INVALID` before readiness checks and
   before any planner, executor,
   controller, Gazebo, MoveIt scene, checkpoint, or physical-evidence side
   effect.
3. **Failure-only persistence:** each injected post-request failure stage writes
   exactly one valid schema-v1 artifact; a successful plan writes none.
4. **Original failure preservation:** for transport failure, missing result,
   MoveIt error, empty trajectory, cancellation timeout, and writer failure, the
   returned public status/category/code/message match the pre-change baseline.
5. **Workflow preservation:** diagnostic success or failure does not change
   state trace, transition count, recovery selection, original failure,
   checkpoint bytes, checkpoint sequence, session ID, or physical-grasp sidecar
   bytes relative to the same injected baseline.
6. **Exact request round-trip:** offline replay verifies both hashes and rebuilds
   a request whose canonical representation equals the captured request,
   including explicit absence of start-state velocities.
7. **Corruption rejection:** truncated JSON, unsupported schema, altered hashes,
   session mismatch, fingerprint mismatch, and scene mismatch fail closed before
   ROS submission.
8. **No execution:** fake and live replay record zero execution calls, zero arm
   or gripper controller goals, unchanged arm/gripper joints and TCP, unchanged
   Gazebo attachment/object pose, unchanged MoveIt world/attached membership,
   and unchanged checkpoint/sidecar files.
9. **Stochastic honesty:** a matching live replay may succeed or fail; acceptance
   requires accurate reporting and immutable original evidence, not an identical
   planner outcome.
10. **Build and automated regression:** targeted RED-to-GREEN tests pass, then
    `pick_place_common`, `panda_gazebo_demo`, and `so101_gazebo_demo` build and
    test with zero failures/errors from the R3 worktree overlay.
11. **Live provenance:** the enabled failure-injection and guarded replay use the
    R3 worktree build/install overlay, one identified ROS domain/partition and
    one stack; source, install prefix, executable, PID, session, artifact, and
    logs agree.
12. **Fresh runtime and visual evidence:** a fresh SO-101 failure-injection run
    proves artifact creation and no execution side effect through MoveIt,
    controller/joint/TF, Gazebo, Planning Scene, checkpoint, and a new inspected
    visual capture. A normal successful SO-101 run proves no artifact is emitted.
    Panda receives a fresh regression run because the three-package refactor
    branch must remain behaviorally stable.
13. **Cleanup and Git scope:** only owned diagnostic/runtime processes are
    stopped; unrelated sampler clang-tidy, other worktrees, root checkout,
    `kimi`, `refactor`, and `codex-cua` are preserved. Generated artifacts remain
    outside Git. The final implementation worktree is clean with scoped commits
    and is neither pushed nor merged without separate approval.

## Stop Conditions

Stop implementation and return for a new decision if any of the following is
required:

- changing the public `MICRO_LIFT_*` failure taxonomy or recovery behavior;
- weakening the 2 mm probe bound, target tolerances, touch ACM, planner settings,
  checkpoint/session/provenance, or physical validation gates;
- installing a replay executable or enabling trajectory execution;
- mutating the live Planning Scene to force a replay;
- extending diagnostics to Panda, common, ordinary joint planning, automatic
  retry, planner seeds, or retention policy;
- accepting a replay when scene/session/fingerprint provenance does not match;
- cleaning a ROS/Gazebo process whose ownership cannot be established;
- observing a live or visual result that contradicts the no-execution evidence.

## Approval Gate

This document authorizes no implementation by itself. After written approval,
write a separate RED-to-GREEN implementation plan with exact files, tests,
commands, evidence paths, commit boundaries, and stop conditions. Only after
that plan is approved may the existing ai-station `tmux codex` goal be resumed.
