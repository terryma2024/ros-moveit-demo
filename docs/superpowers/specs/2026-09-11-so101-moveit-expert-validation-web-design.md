# SO-101 MoveIt expert random-position validation Web design

**Date:** 2026-09-11

**Status:** Approved after independent GPT-6 high written-spec review

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

Add a dedicated validation server entry point in `so101_teleop`. It serves the installed Web bundle
and the `/expert-validation` route, but it does not join a simulation ROS graph. Its
`ExpertValidationSupervisor` owns every simulation process group, session identifier, ROS domain,
input manifest, progress stream, and cleanup result.

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

Only the supervisor starts or signals simulation processes. The existing batch logic remains the
point-workflow owner, but its attached-stack mode no longer calls `Popen`, `start_new_session`,
`killpg`, or direct process signals. It requests launch, perception, and consumer processes through
a supervisor process-owner port. The supervisor creates one stack process group, one batch process
group, and a separately registered process group for each point worker. A point worker's descendants
remain in that worker group. This lets normal point cleanup stop perception and consumer workers
without signalling the long-lived batch. It also keeps every group reachable after its original
leader exits.

Before a child crosses its exec barrier, the supervisor durably records an ownership intent with an
attempt-scoped spawn token, expected executable and environment fingerprints, target process group,
and cleanup state. It then records PID, PGID, process start time, and the child acknowledgement before
the child may run. A missing acknowledgement, unexpected descendant, or ambiguous process identity
blocks new work and moves the campaign to `NEEDS_OPERATOR_RECOVERY`. Cleanup verifies that every
registered process and descendant has disappeared; checking only the group leader is insufficient.

The batch requests cooperative point-worker shutdown only after its execution boundary has returned
and controller stop has been confirmed. The supervisor signals only the registered worker groups for
that point. If worker-stop safety is unknown, the attempt enters `NEEDS_OPERATOR_RECOVERY`; the
supervisor does not signal the batch or stack as a substitute.

The browser submits typed intent and renders state. It never constructs shell commands, chooses ROS
state-machine transitions, or sends joint targets.

The existing Teleop server and `/tasks` task station remain unchanged. On the dedicated validation
server, `/` redirects to `/expert-validation`; `/tasks` and existing task-mutation APIs return a
disabled capability and never attach to a simulation. A regular Teleop server that was not started
in validation mode also reports validation as unavailable rather than pretending it can restart its
own stack.

## 4. Deterministic point generation

### 4.1 Input meaning

`total_points` is the final point count. It includes these four canonical anchors, in this order:

| Display ID | Point ID | World position in metres |
|---|---|---|
| `P01` | `task_start` | `(0.02, -0.28, 0.165)` |
| `P02` | `cup_test_forward_5cm` | `(0.02, -0.33, 0.165)` |
| `P03` | `cup_test_left_5cm` | `(-0.03, -0.28, 0.165)` |
| `P04` | `cup_test_right_5cm` | `(0.07, -0.28, 0.165)` |

Version 1 accepts `4 <= total_points <= 20`. The upper bound matches the frozen 16-sample continuous
pool. The capabilities API returns this limit and the selected sampler profile. A later calibrated
profile can raise the limit without changing the Web form, but it receives a new sampler version and
does not change a stored manifest.

### 4.2 Sampler contract

The sampler runs on the server. Version 1 names the compatibility profile
`ai_station_baseline_v1`. Its authoritative historical inputs are:

- source manifest:
  `/data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/manifest/candidate-points.yaml`;
- source manifest SHA256:
  `c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5`;
- source sampler SHA256:
  `81063ca943fd616d01c8e338c1f3d5b7c1bd091b8e79c538cce5c7bb69badccb`;
- source checkout commit: `ea0215180ed8cc0a90d6683a5e80d475987b5bc0`;
- Python `random.Random(20260911)` with `uniform(low, high)`, acceptance in generation order,
  six-decimal rounding before distance checks, and at most 10,000 proposals per point;
- X bands: left `[-0.045, -0.015]`, center `[-0.005, 0.035]`, right `[0.045, 0.080]` metres;
- Y bands: near `[-0.255, -0.240]`, mid `[-0.305, -0.275]`, far
  `[-0.340, -0.315]` metres;
- ordered strata: near/left, near/center, near/right, near/left, near/center, mid/left,
  mid/center, mid/right, mid/left, mid/center, mid/right, far/left, far/center,
  far/right, far/center, far/right;
- minimum pairwise center distance `0.015` metres across anchors and generated points, Z `0.165`
  metres, a table-edge margin of one cup radius plus `0.010` metres, and the four anchors listed
  above.

The historical paths are provenance, not runtime dependencies. Implementation copies the manifest
fixture and sampler profile into versioned repository files and checks their SHA256 values. The
installed package is the runtime source of truth.

The profile configuration also records:

- seed, generator version, source commit, policy SHA256, scene-geometry SHA256, and anchor-file
  SHA256;
- near/mid/far and left/center/right world-coordinate bands;
- the 16-entry stratum schedule and its quotas;
- cup centre Z, upright orientation, minimum pairwise XY distance, and minimum cup-edge clearance;
- the four anchor identities and positions.

The service always generates the complete 16-point pool for a seed. For a request below 20 total
points, it allocates the requested pool size across the nine strata with the largest-remainder
method, using the 16-entry schedule above as the quota source. Ties follow first appearance in that
schedule. It selects the earliest generated members of each allocated stratum, restores canonical
pool order, and then assigns consecutive display IDs. Generating the full pool first avoids changing
a point merely because the requested count changed.

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

The maintained top-view generator currently has a separate geometry-derived sampler whose 35 mm
minimum separation cannot reproduce this fixture. Implementation must expose that behaviour under a
different profile, such as `geometry_v2`, and add `ai_station_baseline_v1` without silently changing
either profile. The Web page defaults to `ai_station_baseline_v1` for this validation campaign.

Sampling fails closed when a coordinate is non-finite, outside the selected profile, too close to
another point under that profile, exceeds the rejection cap, or lacks the profile's required
table-edge clearance. The API does not reduce a margin or silently return fewer points. Pairwise
spacing is sampling-diversity control across independent reset scenes; it is not a physical
simultaneous-cup clearance requirement.

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
| `FAILED`, `SKIPPED_UNREACHABLE`, `INVALID`, `NOT_RUN`, or `BLOCKED` | red | matching pale red |

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

The map occupies the left side of the main area. The right side shows campaign state, coverage,
first-pass success rate when qualified, current point, first shared failure, lifecycle, and an
ordered point list. Selecting a map point or list row updates the same selected-point state.

The first-pass summary uses these explicit counts:

```text
requested = every point in the frozen manifest
evaluated = points with an accepted POINT_REACHABILITY decision
execution_started = points that reached POINT_STARTED
valid_succeeded = accepted SUCCEEDED point results
valid_failed = accepted product failures, including SKIPPED_UNREACHABLE
invalid = attempts rejected for provenance, initial-state, progress, or cleanup ambiguity
not_executed = terminal NOT_RUN + BLOCKED points
evaluation_coverage = evaluated / requested
execution_coverage = execution_started / requested
qualified_first_pass_success_rate = valid_succeeded / (valid_succeeded + valid_failed)
```

`qualified_first_pass_success_rate` is unavailable when its denominator is zero or when campaign
shutdown safety is unresolved. An unreachable point is evaluated, does not increment
`execution_started`, becomes `SKIPPED_UNREACHABLE`, and enters `valid_failed`; it is never reported as
unexecuted. Invalid and unexecuted points do not enter the success-rate denominator. When a shared
failure, cancellation, or recovery condition stops the campaign, unresolved points become `BLOCKED`
or `NOT_RUN` with a reason instead of remaining `PENDING`. A point result accepted before a later
shared failure remains frozen. A cleanup ambiguity for that point makes its attempt `INVALID`; a
later campaign-level shutdown ambiguity preserves accepted point outcomes but marks the campaign
qualification unresolved.

Terminal reconciliation uses this precedence:

| Observed boundary | Terminal point state | Counting rule |
|---|---|---|
| Accepted successful point receipt | `SUCCEEDED` | `valid_succeeded` |
| Accepted product-failure receipt | `FAILED` | `valid_failed` |
| Accepted unreachable decision | `SKIPPED_UNREACHABLE` | `valid_failed`, evaluated but not execution-started |
| Accepted non-unreachable reachability decision, but interruption before `POINT_STARTED` or a terminal receipt | `INVALID` with reachability or owner-loss reason | `invalid`; evaluated but not execution-started |
| Point started, but no accepted terminal receipt after cancellation, owner loss, timeout, or torn progress | `INVALID` with interruption reason | `invalid` |
| Point not yet evaluated when a shared failure or recovery condition stops the batch | `BLOCKED` with blocking reason | `not_executed` |
| Point not yet evaluated when the operator cancels | `NOT_RUN` with cancellation reason | `not_executed` |

An integrity failure that invalidates a point receipt takes precedence over its earlier product
outcome. A later campaign-level failure does not overwrite a point receipt that remains valid. Every
terminal campaign must reconcile all requested points and contain no `PENDING` or `RUNNING` state.

Retry outcomes appear in a separate attempt summary and never alter first-pass counts or the frozen
first-pass fraction.

### 6.3 Evidence

The selected-point panel lists the first-pass result followed by retry attempts in time order. It
shows image artifacts inline when their media type is supported and exposes downloads for RGB,
Viewer screenshots, point-cloud previews, PLY, JSON, and logs. Every link uses a manifest-registered
opaque artifact ID. Browser-visible responses contain no absolute evidence path.

### 6.4 Retry

After a first pass reaches a safe terminal state, valid product failures and
`SKIPPED_UNREACHABLE` points can be selected. `INVALID`, `NOT_RUN`, and `BLOCKED` points require a
new first-pass campaign after the underlying execution condition is corrected; they are not product
failure retries. The
`Retry selected with FULL_RESTART` action requires the explicit confirmation string
`CONFIRM FULL_RESTART RETRIES`.

Selected points run serially. Each receives a new attempt ID, simulation session ID, ROS domain,
owned process group, evidence directory, and terminal cleanup record. A retry button is disabled
for successful points, a non-terminal first pass, an active execution, or a campaign in
`NEEDS_OPERATOR_RECOVERY`, or a campaign without a confirmed shutdown-safety receipt.

## 7. API

The validation server exposes these routes:

| Method and route | Purpose |
|---|---|
| `GET /expert-validation/capabilities` | Return availability, sampler limits, executors, operations, and lifecycle support. |
| `POST /expert-validation/lease` | Acquire the supervisor-scoped control lease for one service session. |
| `PUT /expert-validation/lease/{lease_id}` | Renew the current lease before its server-defined expiry. |
| `DELETE /expert-validation/lease/{lease_id}` | Release an idle lease; an active campaign requires cancellation or completion first. |
| `POST /expert-validation/manifests` | Generate and persist one immutable point/geometry manifest. |
| `GET /expert-validation/manifests/{manifest_id}` | Read an existing manifest. |
| `POST /expert-validation/campaigns` | Start one first-pass `RESET_WORLD` campaign. |
| `GET /expert-validation/campaigns` | List retained campaign summaries. |
| `GET /expert-validation/campaigns/{campaign_id}` | Read authoritative campaign, point, progress, and retry state. |
| `POST /expert-validation/campaigns/{campaign_id}/cancel` | Request cancellation at a safe checkpoint. |
| `POST /expert-validation/campaigns/{campaign_id}/full-restart-retries` | Start serial retries for selected failed point IDs. |
| `GET /expert-validation/artifacts/{artifact_id}` | Read one manifest-registered artifact. |
| `WS /expert-validation/events` | Stream sequenced progress hints; HTTP state remains authoritative. |

Manifest generation and evidence reads are non-moving operations. Campaign start, cancel, and retry
require the supervisor-scoped lease, a command ID, and durable server-side idempotency. A repeated
command ID with the same canonical request returns its stored result. The same ID with different
content fails with `COMMAND_ID_REUSED`; an ambiguous pre-crash command returns
`COMMAND_OUTCOME_UNKNOWN` and cannot be submitted under a new ID until reconciliation finishes.

The validation service creates a stable service session for the browser. It is independent of every
attempt's `simulation_session_id`. Lease duration and renewal margin come from capabilities. A
browser disconnect does not release the lease or stop an attempt. Lease expiry requests cooperative
cancellation at the next safe checkpoint and blocks new attempts. After expiry, another service
session may acquire the lease only to inspect state or cancel/recover the unresolved campaign; it
cannot start a second campaign. A server restart invalidates every lease, restores durable campaign
state, and requires a new lease after reconciliation. Releasing a lease while a campaign is active
fails closed.

The WebSocket is an acceleration path, not the source of truth. Reconnect always reads the campaign
resource before applying later event sequences.

## 8. Persistent state, progress, and evidence

### 8.1 Supervisor journal

The supervisor uses one durable store under its configured evidence root. It contains manifest
references, canonical command fingerprints and results, campaign and attempt states, retry queue and
cursor, lease generation, simulation identifiers, ownership intents and acknowledgements, safety
receipts, and cleanup state. A process-wide lock admits only one supervisor writer.

State-changing commands follow this order:

1. validate the lease, manifest, current state, and command fingerprint;
2. commit command intent and the next campaign/attempt state;
3. commit ownership intent before any child crosses its exec barrier;
4. record the child acknowledgement and only then let execution continue;
5. commit progress and terminal receipts before returning a terminal command result;
6. dequeue a retry only after the preceding attempt has a confirmed cleanup receipt.

On restart, the supervisor takes the singleton lock, invalidates old leases, compares the durable
ownership registry with the complete descendant inventory, and reconciles every non-terminal
command and attempt. It never repeats an ambiguous command or starts a new stack while ownership or
cleanup is unresolved. A cleanly terminal attempt can be restored. Any mismatch becomes
`NEEDS_OPERATOR_RECOVERY`.

### 8.2 Progress framing

The batch engine writes a flushed, append-only progress event for each boundary:

```text
BATCH_STARTED
POINT_REACHABILITY
POINT_STARTED
ARTIFACT_REGISTERED
POINT_FINISHED
BATCH_FINISHED
```

Phase-level progress is optional in version 1 because the current batch has no authoritative phase
callback. It may be added later only from an execution-owned event source; log parsing is not an
authoritative phase signal.

Events are newline-delimited canonical JSON written by one batch writer. Each complete record
contains schema version, campaign ID, attempt ID, sequence, event type, payload hash, and timestamp.
The validated contiguous event log is the commit authority. The snapshot is a rebuildable cache, not
a second commit decision.

For `POINT_FINISHED` and `BATCH_FINISHED`, the writer first atomically installs and fsyncs the
referenced result manifest, then appends one bounded event record, terminates it with a newline, and
fsyncs the log. The supervisor validates the next contiguous record and its referenced manifest,
commits the accepted sequence and projected state in its durable journal, and only then exposes that
state through HTTP or WebSocket. It may rewrite an atomic progress snapshot after journal acceptance.

The supervisor tails only the owned event file. It buffers a final byte range without a newline and
does not parse or publish it while the writer is alive. A malformed complete record, duplicate or
reordered sequence, identity mismatch, invalid referenced manifest, or dangling partial record after
the writer exits makes the attempt invalid. On recovery, every complete contiguous record beyond the
journal's accepted sequence is validated and accepted idempotently; a stale snapshot is rebuilt. A
snapshot ahead of either the log or the journal is discarded. If the supervisor crashed after
journal acceptance but before an HTTP response, durable command idempotency returns the already
accepted result. These rules cover crashes after log fsync, after journal acceptance, and after
snapshot replacement without making a terminal point disappear.

The first-pass campaign manifest stores every requested point from the start. Points are `PENDING`
only while they remain eligible to run; terminal reconciliation converts untouched points to
`NOT_RUN` or `BLOCKED` with a reason. Point result manifests and the terminal campaign manifest reuse
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

Only one of these paths can be active. Before starting a stack, the supervisor reconciles its durable
ownership registry, inventories descendants and the assigned ROS domain, and verifies that no
previous cleanup is unresolved. Unknown conflicting processes fail the request; they are never
killed automatically.

For a first pass, the supervisor starts one visible stack without a nested Teleop server, waits for
controllers, joint feedback, MoveIt, Planning Scene, camera, and physical-evidence readiness, then
runs the existing batch logic in `--attach-existing-stack` mode through the supervisor process-owner
port. The implementation must wire the batch's cancellation callback and replace the current
hard-coded post-execution `SafetyReceipt` with an actual session- and epoch-bound probe. The
supervisor performs ordered shutdown only after it receives a fresh shutdown-safety receipt.

For a retry, the supervisor starts a fresh stack, proves canonical initial state, runs exactly one
point, captures terminal evidence, and performs ordered shutdown before dequeuing the next point.
This is the counted `FULL_RESTART` boundary.

The ai-station GNOME capture adapter is moved from task-local evidence into maintained product
source behind the existing viewer-capture interface. macOS keeps its current adapter. Platform
selection is explicit and tested; neither adapter may return an old screenshot as current
evidence.

The supervisor records ownership intent, spawn token, PID, PGID, process start time, parent and
descendant identities, session, source/install/runtime fingerprints, ROS domain, and cleanup state
before reporting ownership. After a restart, it may resume observation of an attempt only after
durable command, ownership, progress, safety, and cleanup records all reconcile. It does not resume
robot execution from a guessed state. A running stack with ambiguous batch state is preserved for
operator recovery, and the campaign becomes `NEEDS_OPERATOR_RECOVERY`.

## 10. Cancellation, safety, and failure semantics

Execution outcome and shutdown safety are separate records. Every attempt exit, including product
failure, shared failure, timeout, corrupt progress, owner death, and cancellation, must produce or
attempt to produce a fresh `ShutdownSafetyReceipt` containing:

```text
campaign_id and attempt_id
simulation_session_id and reset/release epoch
observed_at and freshness bound
cup_held and support_confirmed
robot_hold_requested and robot_hold_confirmed
controller_stop_confirmed
safe_to_shutdown
reason_code
evidence artifact IDs
```

The batch never fabricates this receipt from a process exit code. Missing, stale, or identity-mismatched
evidence sets `safe_to_shutdown=false`. The supervisor then enters `NEEDS_OPERATOR_RECOVERY`, keeps
the owned stack available for inspection when possible, and does not reset, open the gripper, start
another stack, or claim cleanup.

Cancellation uses a supervisor-to-batch control channel tied to campaign and attempt identity. The
batch acknowledges the request at a declared safe checkpoint, requests hold/stop through the normal
robot-control boundary, emits the shutdown-safety receipt, and exits cooperatively. If it does not
acknowledge within the configured bound, the supervisor does not assume that signalling is safe. It
records the timeout and enters `NEEDS_OPERATOR_RECOVERY`. Signal escalation is allowed only after a
fresh receipt says the cup is supported or not held and controller stop is confirmed.

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

When signal escalation is permitted, the supervisor signals only registered process groups, first
with `SIGINT` and then with a bounded `SIGTERM`. It never uses wide process-name matching. Cleanup is
complete only after registered descendants disappear and the ROS domain no longer exposes the owned
graph. A surviving descendant or unknown process keeps ownership unresolved.

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

A successful MoveIt validation point does not automatically qualify as an ACT demonstration or
held-out ACT evaluation point. ACT collection adds a separate immutable manifest with head/wrist
camera visibility, frame timestamps and freshness, robot observation/action alignment, deterministic
neck-search initial state, scene randomization, Keep/Discard decision, and split membership. ACT
rollout adds its own policy checkpoint, observation contract, safety result, and success denominator.

## 12. Testing

### 12.1 Sampler and map

- exact `ai_station_baseline_v1` 20-point compatibility fixture for `seed=20260911`, including
  source manifest and sampler hashes, bands, ordered strata, 15 mm threshold, six-decimal rounding,
  and rejection cap;
- deterministic repeat, changed-seed divergence, four-anchor prefix, stable subset behaviour, and
  canonical hash tests;
- count bounds, finite values, pairwise separation, table clearance, and stale-input rejection;
- shared Python/React projection fixtures for table, base, target, cup radius, marker radius, and
  status colours;
- an explicit test that the separate 35 mm geometry profile cannot be substituted for the frozen
  baseline profile.

### 12.2 Supervisor and service

- fake-process tests for one first-pass stack, per-point progress, ordered cleanup, and no second
  active execution;
- process-owner tests where the batch dies after requesting a child, a group leader exits while a
  descendant remains, a spawn acknowledgement is missing, and cleanup leaves a descendant;
- a two-point lifecycle test proving point-one worker groups disappear while the same batch process
  stays alive and starts point two;
- one fresh stack per selected retry, strict serial order, unique session/domain/attempt IDs, and
  cleanup-before-next-start assertions;
- durable idempotency tests at every spawn/result/dequeue transaction boundary, singleton lock,
  lease acquisition/renewal/expiry, browser disconnect, cancel checkpoint, held-cup blocking, stale
  manifest, corrupt complete event, live partial event, torn terminal event, ownership mismatch, and
  restart reconciliation tests;
- fresh shutdown-safety receipt tests for success, product failure, shared failure, timeout,
  cancellation, corrupt progress, and owner death; missing evidence must enter
  `NEEDS_OPERATOR_RECOVERY`;
- count and denominator tests for early shared failure, invalid attempt, cancellation, zero valid
  attempts, all-unreachable and mixed unreachable campaigns, a started point interrupted before its
  terminal receipt, an `UNKNOWN` reachability decision, owner loss between `POINT_REACHABILITY` and
  `POINT_STARTED`, campaign cleanup ambiguity, and first-pass results after retries;
- progress crash tests immediately after result-manifest fsync, event-log fsync, journal acceptance,
  snapshot replacement, and before the HTTP response;
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
2. generate `total_points=4`, run the anchor smoke campaign, and inspect fresh progress, numeric
   evidence, and Viewer screenshots through the page;
3. generate the exact `total_points=20` compatibility manifest and run its first pass;
4. if that fresh first pass contains a valid failed or unreachable point, select one such point and
   run one independent `FULL_RESTART` retry through the same page;
5. if every valid point succeeds, record `LIVE_RETRY_NOT_APPLICABLE_ALL_SUCCEEDED` rather than
   fabricating a failure; the deterministic fake-supervisor acceptance must still exercise the
   failure-selection and retry UI, while supervisor integration tests prove real process restart and
   cleanup;
6. read back both campaigns, attempts, artifact hashes, ROS graph, complete process inventory,
   shutdown-safety receipts, and cleanup state.

The live result is accepted only from that new run. Historical baseline screenshots and success
messages do not replace fresh Gazebo/MuJoCo, MoveIt, controller, Planning Scene, perception, and
visual evidence. No real-hardware command is part of this acceptance.

## 13. Delivery boundary

The first implementation delivers the MoveIt expert validation workflow, exact map, persistent
supervisor journal, lease boundary, progress, evidence browser integration, and `FULL_RESTART` retry
supervisor. The current attached batch cannot be reused unchanged: implementation must add the
process-owner port, cooperative cancellation channel, and real shutdown-safety probe described
above before live execution is enabled.

This version does not implement head/wrist cameras, episode recording, ACT training, ACT inference,
Keep/Discard data curation, or real-hardware control. Those operations use the executor extension
after their own approved design tasks are implemented.
