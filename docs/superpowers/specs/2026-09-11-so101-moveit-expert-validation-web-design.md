# SO-101 MoveIt expert random-position validation Web design

**Date:** 2026-09-11

**Status:** Design approved in chat; written-spec review pending

**Runtime target:** ai-station GNOME Linux with visible MuJoCo; macOS remains supported through its existing capture adapter

**Package scope:** `src/so101_demo_py`, `src/so101_teleop`, and the maintained top-view generator under `scripts/`

**Design evidence root:** `/tmp/so101-debug-teleop-random-validation-EADE4s/`

## 1. Objective

Add a separate MoveIt expert validation page to the Teleop Web application. The operator chooses a
final point count, generates a reproducible position manifest containing the four canonical points,
runs the current RGB-D perception and MoveIt expert workflow, follows progress on an exact top-view
map, and opens evidence for any point. Failed points can be selected for independent
`FULL_RESTART` retries.

The first pass and retries have different lifecycle meanings:

- the first pass starts one fresh owned stack and executes the requested points in order, using
  `RESET_WORLD` between points;
- each selected retry starts and stops its own fresh stack and is recorded as one
  `FULL_RESTART` attempt;
- a retry never overwrites the first-pass result or changes its denominator.

This is simulation-only work. The page and its APIs do not authorize real-hardware movement.

## 2. Existing implementation and the missing boundary

The existing `/tasks` application already provides strict task-point input, a server-owned batch,
control-lease checks, run summaries, artifact IDs, evidence downloads, and WebSocket reconnect
handling. The batch engine in `so101_demo_py` performs declared reachability, transactional
`RESET_WORLD`, RGB-D perception, dynamic target construction, MoveIt execution, physical outcome
checks, terminal capture, and per-point artifact registration.

It cannot implement this feature by itself. The current Teleop task service is a child of the
persistent MuJoCo task-station stack and attaches its batch process to that stack. A service in
that position cannot perform a true `FULL_RESTART` without either terminating itself or leaving a
second stack running. The batch manifest also appears only at terminal completion, so the current
Web API cannot report authoritative point-by-point progress while the batch is running.

The new page therefore uses the existing task and artifact types where they fit, but execution is
owned by a long-lived validation supervisor outside all MuJoCo stacks.

## 3. Chosen architecture

Add a dedicated validation server entry point in `so101_teleop`. It serves the same installed Web
bundle and the `/expert-validation` route, but it does not join a simulation ROS graph. Its
`ExpertValidationSupervisor` owns every child process group, session identifier, ROS domain, input
manifest, progress stream, and cleanup result.

```text
browser /expert-validation
        |
        v
FastAPI validation service + lease + artifact registry
        |
        v
ExpertValidationSupervisor (long-lived, no robot control loop)
        |
        +-- first pass: fresh stack -> attached RESET_WORLD batch -> ordered shutdown
        |
        +-- retry Pxx: fresh stack -> one-point batch -> ordered shutdown
        +-- retry Pyy: fresh stack -> one-point batch -> ordered shutdown
```

Only the supervisor starts or signals simulation processes. The browser submits typed intent and
renders state. It never constructs shell commands, chooses ROS state-machine transitions, or sends
joint targets.

The existing `/` Teleop page and `/tasks` task station remain compatible. A regular Teleop server
that was not started with the validation service returns a disabled validation capability rather
than pretending it can restart its own stack.

## 4. Deterministic point generation

### 4.1 Input meaning

`total_points` is the final point count. It includes these four canonical anchors, in this order:

| Display ID | Point ID | World position in metres |
|---|---|---|
| `P01` | `task_start` | `(0.02, -0.28, 0.165)` |
| `P02` | `cup_test_forward_5cm` | `(0.02, -0.33, 0.165)` |
| `P03` | `cup_test_left_5cm` | `(-0.03, -0.28, 0.165)` |
| `P04` | `cup_test_right_5cm` | `(0.07, -0.28, 0.165)` |

Version 1 accepts `4 <= total_points <= 20`. The upper bound matches the currently qualified
16-sample continuous pool. It is returned by the capabilities API and lives in the installed
sampler configuration, so a later calibrated region can raise it without changing the Web form.

### 4.2 Sampler contract

The sampler runs on the server. Its versioned configuration records:

- seed, generator version, source commit, policy SHA256, scene-geometry SHA256, and anchor-file
  SHA256;
- near/mid/far and left/center/right world-coordinate bands;
- the 16-entry stratum schedule and its quotas;
- cup centre Z, upright orientation, minimum pairwise XY distance, and minimum cup-edge clearance;
- the four anchor identities and positions.

The service always generates the complete 16-point pool for a seed. For a request below 20 total
points, it allocates the requested pool size across the nine strata with the largest-remainder
method. Ties follow the installed stratum order. It selects the first generated members of each
allocated stratum, restores canonical pool order, and then assigns consecutive display IDs.
Generating the full pool first avoids changing a point merely because the requested count changed.

`seed=20260911` and `total_points=20` are a compatibility fixture. They must reproduce the exact
four anchors and 16 generated coordinates from the 2026-09-11 ai-station MoveIt expert baseline.
The fixture is checked coordinate-for-coordinate; a visually similar distribution is not enough.

| Pool ID | Stratum | World XY in metres |
|---|---|---|
| `sample_01_near_left` | near/left | `(-0.020732, -0.249568)` |
| `sample_02_near_center` | near/center | `(0.012943, -0.253631)` |
| `sample_03_near_right` | near/right | `(0.077260, -0.247428)` |
| `sample_04_near_left` | near/left | `(-0.040923, -0.243568)` |
| `sample_05_near_center` | near/center | `(0.021124, -0.240778)` |
| `sample_06_mid_left` | mid/left | `(-0.044253, -0.285035)` |
| `sample_07_mid_center` | mid/center | `(0.030324, -0.303335)` |
| `sample_08_mid_right` | mid/right | `(0.053252, -0.288054)` |
| `sample_09_mid_left` | mid/left | `(-0.024572, -0.294181)` |
| `sample_10_mid_center` | mid/center | `(0.003947, -0.279123)` |
| `sample_11_mid_right` | mid/right | `(0.076749, -0.295132)` |
| `sample_12_far_left` | far/left | `(-0.037607, -0.327555)` |
| `sample_13_far_center` | far/center | `(0.007874, -0.320800)` |
| `sample_14_far_right` | far/right | `(0.051023, -0.339445)` |
| `sample_15_far_center` | far/center | `(0.008183, -0.339434)` |
| `sample_16_far_right` | far/right | `(0.071574, -0.319255)` |

Sampling fails closed when a coordinate is non-finite, outside the installed region, too close to
another point, or lacks the required table-edge clearance. The API does not reduce a safety margin
or silently return fewer points.

### 4.3 Frozen manifest

Creating a manifest returns a server-generated `manifest_id` and a canonical document containing:

```text
schema_version
manifest_id
sampler_id and sampler_version
seed and total_points
source, policy, scene, geometry and anchor hashes
points[]: display_id, id, label, source, stratum, cup_position_world_m
geometry: table, base, candidate region, target, cup radius and target tolerance
manifest_sha256
```

Starting a campaign requires this immutable manifest. If any installed source/config hash no longer
matches, the old manifest remains readable but start returns `VALIDATION_MANIFEST_STALE`.

## 5. Exact top-view map

The page renders an SVG from the geometry and point document returned by the server. The drawing
uses one world-to-pixel transform and equal X/Y scale; it is not an image-generation result.

The map includes:

- table bounds and world-coordinate grid;
- the square robot pedestal and base-origin mark;
- the move target centre, target region, and dashed tolerance circle;
- all cup centre points with equal marker radius;
- the dashed cup-footprint circle at `P01`;
- point display ID, fixed/generated identity, and the selected point.

Point colours are fixed:

| State | Stroke | Fill |
|---|---|---|
| `PENDING` or `RUNNING` | blue | matching pale blue |
| `SUCCEEDED` | green | matching pale green |
| `FAILED`, `SKIPPED_UNREACHABLE`, or invalid execution result | red | matching pale red |

`RUNNING` uses a thicker blue stroke and an accessible current-point label. Marker diameter does
not change with state. Selection adds an outer focus ring without changing the position marker.

The maintained Python top-view tool and the React SVG component consume the same geometry and
status model. Shared golden tests compare their projected coordinates, point order, radii, status
colours, and the 20-point compatibility fixture. The Web page does not invoke the Python script at
runtime.

## 6. Page layout and operator flow

The new route is `/expert-validation`.

### 6.1 Campaign setup

The setup card contains:

- final point count;
- seed, under an advanced control, defaulting to `20260911`;
- `Generate points`, which creates a frozen manifest but does not move the robot;
- sampler version, capacity, manifest hash, and geometry/policy hashes;
- `Start validation`, enabled only with a current manifest and valid control lease.

Changing count or seed invalidates the preview until the operator generates a new manifest.

### 6.2 Map and progress

The map occupies the left side of the main area. The right side shows campaign state, completed/total,
first-pass success rate, current point, first shared failure, lifecycle, and an ordered point list.
Selecting a map point or list row updates the same selected-point state.

The phrase `first-pass success rate` is deliberate. Retry outcomes appear in a separate attempt
summary and do not alter the original fraction.

### 6.3 Evidence

The selected-point panel lists the first-pass result followed by retry attempts in time order. It
shows image artifacts inline when their media type is supported and exposes downloads for RGB,
Viewer screenshots, point-cloud previews, PLY, JSON, and logs. Every link uses a manifest-registered
opaque artifact ID. Browser-visible responses contain no absolute evidence path.

### 6.4 Retry

After a first pass reaches a terminal state, failed points can be selected. The
`Retry selected with FULL_RESTART` action requires the explicit confirmation string
`CONFIRM FULL_RESTART RETRIES`.

Selected points run serially. Each receives a new attempt ID, simulation session ID, ROS domain,
owned process group, evidence directory, and terminal cleanup record. A retry button is disabled
for successful points, a non-terminal first pass, an active execution, or a campaign in
`NEEDS_OPERATOR_RECOVERY`.

## 7. API

The validation server exposes these routes:

| Method and route | Purpose |
|---|---|
| `GET /expert-validation/capabilities` | Return availability, sampler limits, executors, operations, and lifecycle support. |
| `POST /expert-validation/manifests` | Generate and persist one immutable point/geometry manifest. |
| `GET /expert-validation/manifests/{manifest_id}` | Read an existing manifest. |
| `POST /expert-validation/campaigns` | Start one first-pass `RESET_WORLD` campaign. |
| `GET /expert-validation/campaigns` | List retained campaign summaries. |
| `GET /expert-validation/campaigns/{campaign_id}` | Read authoritative campaign, point, progress, and retry state. |
| `POST /expert-validation/campaigns/{campaign_id}/cancel` | Request cancellation at a safe checkpoint. |
| `POST /expert-validation/campaigns/{campaign_id}/full-restart-retries` | Start serial retries for selected failed point IDs. |
| `GET /expert-validation/artifacts/{artifact_id}` | Read one manifest-registered artifact. |
| `WS /expert-validation/events` | Stream sequenced progress hints; HTTP state remains authoritative. |

Manifest generation and evidence reads are non-moving operations. Campaign start, cancel, and
retry require the current lease, a command ID, and server-side idempotency. A repeated command ID
with different content fails with `COMMAND_ID_REUSED`.

The WebSocket is an acceleration path, not the source of truth. Reconnect always reads the campaign
resource before applying later event sequences.

## 8. Persistent progress and evidence

The batch engine writes a flushed, append-only progress event for each boundary:

```text
BATCH_STARTED
POINT_REACHABILITY
POINT_STARTED
POINT_PHASE_CHANGED
ARTIFACT_REGISTERED
POINT_FINISHED
BATCH_FINISHED
```

It also rewrites an atomic progress snapshot after each accepted event. The supervisor tails only
the owned event file, verifies monotonically increasing sequence numbers and campaign/attempt
identity, then publishes WebSocket hints. A malformed, truncated, reordered, or foreign event makes
the attempt invalid; it does not become browser state.

The first-pass campaign manifest stores every requested point from the start, so not-yet-executed
points remain visible as `PENDING`. Point result manifests and the terminal campaign manifest reuse
the current artifact registry and checksum rules. Retry attempts link to both `campaign_id` and the
original point ID.

Evidence roots follow the repository SO-101 policy. The validation server is started with one
absolute, non-symlink task-family root. Each campaign and attempt receives a child directory under
that root. The service rejects `..`, absolute client paths, symlink traversal, unregistered files,
and files outside the configured root.

## 9. Supervisor lifecycle

The first-pass state machine is:

```text
IDLE
  -> PREPARING_STACK
  -> RUNNING_RESET_WORLD_BATCH
  -> FINALIZING
  -> COMPLETED | PARTIAL_FAILED | FAILED | CANCELLED | NEEDS_OPERATOR_RECOVERY
```

The retry queue is:

```text
IDLE
  -> PREPARING_FRESH_STACK
  -> RUNNING_FULL_RESTART_POINT
  -> FINALIZING_ATTEMPT
  -> next selected point or terminal retry summary
```

Only one of these paths can be active. Before starting a stack, the supervisor inventories its
recorded processes and the assigned ROS domain. Unknown conflicting processes fail the request;
they are never killed automatically.

For a first pass, the supervisor starts one visible stack without a nested Teleop server, waits for
controllers, joint feedback, MoveIt, Planning Scene, camera, and physical-evidence readiness, then
runs the existing batch in `--attach-existing-stack` mode. It performs ordered shutdown when the
batch reaches a normal terminal state.

For a retry, the supervisor starts a fresh stack, proves canonical initial state, runs exactly one
point, captures terminal evidence, and performs ordered shutdown before dequeuing the next point.
This is the counted `FULL_RESTART` boundary.

The ai-station GNOME capture adapter is moved from task-local evidence into maintained product
source behind the existing viewer-capture interface. macOS keeps its current adapter. Platform
selection is explicit and tested; neither adapter may return an old screenshot as current
evidence.

The supervisor records PID, PGID, process start time, session, source/install/runtime fingerprints,
ROS domain, and cleanup state before reporting ownership. After a supervisor restart, it may
reattach only when every field matches. Otherwise the campaign becomes
`NEEDS_OPERATOR_RECOVERY`.

## 10. Failure semantics

The UI distinguishes product failures from invalid execution, although both use the requested red
map styling:

- a valid perception, planning, controller, grasp, transport, release, placement, or evidence-gate
  failure counts in that lifecycle's denominator;
- missing provenance, duplicate stack, wrong initial state, corrupt progress, stale manifest, or
  cleanup ambiguity is invalid execution and is reported separately;
- `SKIPPED_UNREACHABLE` is a first-pass failure and later points may continue when the shared stack
  is healthy;
- a shared-stack failure stops the first pass;
- an unsupported held cup or uncertain reset safety enters `NEEDS_OPERATOR_RECOVERY`; no automatic
  opening, reset, shutdown, or retry follows;
- cleanup failure after a retry stops the retry queue before another stack starts.

Cancellation is cooperative until a safe checkpoint. The supervisor signals only its recorded
process group, first with `SIGINT` and then with a bounded `SIGTERM` escalation. It does not use
wide process-name matching.

## 11. ACT extension boundary

Campaigns carry an `executor_id`, `operation_id`, and executor configuration hash. Version 1
registers:

```text
executor_id: moveit_expert
operation_id: validate_pick_place
```

The backend registry exposes typed executor capabilities and allowed operations. Future ACT work
can register `act_collect` and `act_rollout` operations with their own request model, evidence
schema, controls, and success contract. Expected collection actions include Search, Start
Recording, Run Expert, Keep, and Discard, as described in the ACT head/wrist design.

The extension does not put high-frequency control in the browser. An ACT executor must still use a
server-side owner, safety supervisor, and evidence writer. MoveIt expert, ACT collection, and ACT
rollout statistics remain separate even when they share the same point manifest.

## 12. Testing

### 12.1 Sampler and map

- exact 20-point compatibility fixture for `seed=20260911`;
- deterministic repeat, changed-seed divergence, four-anchor prefix, stable subset behaviour, and
  canonical hash tests;
- count bounds, finite values, pairwise separation, table clearance, and stale-input rejection;
- shared Python/React projection fixtures for table, base, target, cup radius, marker radius, and
  status colours.

### 12.2 Supervisor and service

- fake-process tests for one first-pass stack, per-point progress, ordered cleanup, and no second
  active execution;
- one fresh stack per selected retry, strict serial order, unique session/domain/attempt IDs, and
  cleanup-before-next-start assertions;
- idempotency, lease expiry, cancel checkpoint, held-cup blocking, stale manifest, corrupt event,
  ownership mismatch, and restart recovery tests;
- artifact allow-list, symlink, traversal, media type, checksum, and cross-campaign isolation tests;
- OpenAPI snapshot and generated TypeScript schema checks.

### 12.3 Web

Use the repository Bun toolchain. Component tests cover count/seed input, manifest invalidation,
equal-radius SVG markers, exact status colours, map/list selection, progress recovery, evidence
previews, retry eligibility, confirmation, and separate first-pass/retry statistics. Playwright
uses a fake supervisor API; it must not start MuJoCo.

### 12.4 ai-station simulation acceptance

After source tests and package tests pass, build a task-owned overlay on ai-station and verify the
installed executable and Web bundle provenance. With no pre-existing SO-101 application stack:

1. start the validation server with one registered durable evidence root;
2. generate `total_points=4`, run the first pass, and inspect fresh progress, numeric evidence, and
   Viewer screenshots through the page;
3. select one known failure-scene coordinate and run one independent `FULL_RESTART` retry through
   the same page;
4. read back the campaign, attempt, artifact hashes, ROS graph, process inventory, and cleanup
   state.

The live result is accepted only from that new run. Historical baseline screenshots and success
messages do not replace fresh Gazebo/MuJoCo, MoveIt, controller, Planning Scene, perception, and
visual evidence. No real-hardware command is part of this acceptance.

## 13. Delivery boundary

The first implementation delivers the MoveIt expert validation workflow, exact map, persistent
progress, evidence browser integration, and `FULL_RESTART` retry supervisor. It does not implement
head/wrist cameras, episode recording, ACT training, ACT inference, Keep/Discard data curation, or
real-hardware control. Those operations use the executor extension after their own approved design
tasks are implemented.
