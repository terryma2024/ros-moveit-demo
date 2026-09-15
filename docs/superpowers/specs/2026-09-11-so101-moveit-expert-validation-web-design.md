# SO-101 MoveIt expert random-position validation Web design

**Date:** 2026-09-11

**Updated:** 2026-09-16 against merged parallel/adaptive implementation `25d1130a990f34334b20e9ced4bcde4f4ed83aba`

**Status:** Approved compatibility approach A. The fixed/adaptive sampling runtime is implemented
and merged; the Teleop Web workflow described here is not yet implemented.

**Runtime target:** ai-station Linux with isolated MuJoCo workers and sensor rendering; the existing
interactive Teleop task station remains a separate workflow

**Package scope:** `src/so101_demo_py`, `src/so101_teleop`, and the maintained top-view generator under `scripts/`

**2026-09-16 implementation-sync evidence root:**
`/tmp/so101-debug-teleop-sync-dispatch-rw2rl6/`

**Normative dependencies:**

- `docs/superpowers/specs/2026-09-11-so101-parallel-multipoint-validation-design.md` for the
  fixed-cardinality coordinator, Worker, Broker, journal, K accounting, and qualification contract;
- `docs/superpowers/specs/2026-09-14-so101-adaptive-worker-pool-design.md` for the adaptive Runner,
  pool generations, fallback transaction, wrapper ownership, and adaptive terminal semantics.

The upstream implementation is present on `origin/main` at merge commit
`25d1130a990f34334b20e9ced4bcde4f4ed83aba`. Source presence does not by itself admit execution:
the Web capability probe still verifies the installed console entry points, source/install/config
and model hashes, accepted upstream qualification records, current domain ownership, and clean
runtime state. Availability remains mode-specific, and a failed adaptive probe does not change
fixed-mode semantics.

## 1. Objective

Add a separate MoveIt expert validation page to the Teleop Web application. The operator chooses a
final point count, generates a reproducible position manifest containing the four canonical points,
runs the current RGB-D perception and MoveIt expert workflow sequentially, with a fixed isolated
parallel pool, or with an adaptive isolated Worker pool, follows progress on an exact top-view map,
and opens point, Worker, pool-generation, recovery, and shared-perception evidence. Business-failed
points can be selected for independent `FULL_RESTART` retries after the first pass safely ends.

The first pass exposes three explicit modes:

- `SEQUENTIAL` fixes `worker_count=1`; the Worker keeps one isolated stack and restores each
  leased point before execution;
- `PARALLEL` accepts `worker_count=2..3`; every Worker owns an isolated ROS domain,
  MuJoCo/MoveIt/controller process tree, runtime directories, and evidence subtree;
- fixed `SEQUENTIAL` and `PARALLEL` use `max_points_per_worker=K`; start is rejected unless
  `worker_count × K >= total_points`;
- `ADAPTIVE` starts at the preferred tier, normally W8, and may degrade only through the frozen
  fallback ladder W8 -> W6 -> W4 -> W2 -> W1 after an infrastructure failure. It uses point
  affinity rather than a K capacity limit and never silently becomes a fixed mode;
- the adaptive CLI accepts an explicit preferred tier from W1 through W16 and a strictly decreasing
  fallback list. W8 -> W6 -> W4 -> W2 -> W1 remains the frozen Web default; W16 is a contract ceiling,
  not a live-qualified default;
- each selected retry runs as a separate one-point coordinator batch with
  fixed `SEQUENTIAL`, `worker_count=1`, `K=1`, a fresh stack, and a `FULL_RESTART` lifecycle
  record. Automatic adaptive infrastructure reruns are not operator retries;
- a retry never overwrites the first-pass result or changes its denominator.

This is simulation-only work. The page and its APIs do not authorize real-hardware movement.

## 2. Existing implementation and the missing boundary

The existing `/tasks` application already provides strict task-point input, a server-owned batch,
control-lease checks, run summaries, artifact IDs, evidence downloads, and WebSocket reconnect
handling. The batch engine in `so101_demo_py` performs declared reachability, transactional
`RESET_WORLD`, RGB-D perception, dynamic target construction, MoveIt execution, physical outcome
checks, terminal capture, and per-point artifact registration.

The merged parallel implementation provides a `ParallelBatchCoordinator`, isolated Worker slots,
a shared `PerceptionBroker`, a crash-safe event journal, lease/K accounting, generation fencing,
sealed attempt evidence, and Worker recovery receipts. Those components are the execution source
of truth for both sequential and parallel campaigns. The Teleop service must not recreate their
queue, lease, result-commit, Worker lifecycle, or Broker logic in SQLite.

The merged adaptive implementation provides `AdaptiveBatchRunner` above successive coordinator
generations, `ProductionAdaptivePoolFactory`, the `so101_parallel_batch` console entry point,
`so101_parallel_batch_cleanup`, and `scripts/run_so101_adaptive_batch.zsh`. The wrapper owns the
Runner subprocess and exact cleanup. The Runner is the sole
top-level journal writer and final point-status authority across generations; each generation still
uses an unchanged `ParallelBatchCoordinator` internally.

The missing boundary is a durable Web-facing process adapter and projection. For fixed modes it
starts or reconnects to one coordinator process. For adaptive mode it starts or reconnects to the
production wrapper, then projects only the Runner's top-level journal and its references to nested
generation evidence. It translates Web commands without changing upstream meaning and exposes only
registered artifacts.
The current task-station child service cannot own this boundary because a `FULL_RESTART` would
terminate or orphan its own stack.

The frozen W1/W2/W4/W6/W8 scaling series completed 20/20 points at each tier with exact cleanup;
one later fixed W10 sample also completed 20/20. W8 remains the Web default because W10 has only one
successful sample and two retained failed attempts. W16 remains contract-tested but not live
qualified. These upstream results establish dependency readiness; they do not constitute Teleop Web
acceptance evidence.

## 3. Chosen architecture

Add a dedicated validation server entry point in `so101_teleop`. It serves the installed Web bundle
and the `/expert-validation` route, but it does not join a simulation ROS graph. Its
`ExpertValidationSupervisor` owns Web control leases, durable command idempotency, campaign-to-upstream
bindings, retry ordering, and the top-level execution-owner identity: coordinator for fixed modes,
wrapper for adaptive mode. It does not own or signal Runner, Worker, Broker, MuJoCo, MoveIt,
controller, or point-process groups.

```text
browser /expert-validation
        |
        v
FastAPI validation service + lease + artifact registry
        |
        v
ExpertValidationSupervisor (Web command and batch binding authority)
        |
        +-- SEQUENTIAL -> coordinator N=1, K=total_points
        |
        +-- PARALLEL -> coordinator N=2..3, validated K
        |
        +-- ADAPTIVE -> production wrapper -> AdaptiveBatchRunner
        |                                    -> coordinator generations W8/W6/W4/W2/W1
        |
        +-- FULL_RESTART retry Pxx -> new coordinator batch N=1, K=1
                                |
                                v
                 ParallelBatchCoordinator
                    |              |
              isolated Workers   PerceptionBroker
```

In fixed modes, the coordinator is the only authority for the global point queue, atomic point
lease, slot K debit,
`coordinator_epoch`, `worker_generation`, `lease_generation`, `ATTEMPT_STARTED`,
`RESULT_COMMITTED`, point terminal state, Worker recovery, Broker health, and batch qualification.
It owns and signals only its registered Broker and Worker process groups. The Web supervisor owns
only the coordinator process identity and uses the coordinator control socket for cancellation and
shutdown.
It may signal that PGID only after the coordinator has returned a fresh batch cleanup receipt or an
operator has resolved `NEEDS_OPERATOR_RECOVERY`.

In adaptive mode, the Runner is the only authority across pool generations. It imports fsynced
terminal results from each nested coordinator, preserves `PASSED` and `FAILED`, classifies eligible
infrastructure-interrupted work, performs the exact stop/fence/cleanup/requeue/start transaction,
and records every generation and fallback. The wrapper owns the Runner child and exact cleanup; the
Web layer owns only the wrapper PID identity and sends cancellation to that exact PID after identity
verification. It never broadcasts to a wrapper process group or signals descendants directly.

The authoritative journal is mode-specific: the coordinator journal for fixed modes and the Runner
top-level journal for adaptive mode. Sealed manifests remain authoritative evidence. The Web store
keeps command fingerprints, service leases, batch bindings, accepted upstream cursor/hash, and
retry queue state.
It may cache a campaign projection, but it cannot independently commit a point result or reconstruct
one from logs. On restart it reconnects only when batch ID, coordinator epoch, PID/PGID/start time,
control-socket or wrapper ownership, source/install/config hashes, and the applicable journal chain
all reconcile. A Web-server restart may reconnect to a still-running adaptive wrapper/Runner after
this reconciliation. A Runner process crash is not automatically resumed: wrapper-confirmed cleanup
ends the campaign as `INFRA_FAILED`; unresolved cleanup becomes `NEEDS_OPERATOR_RECOVERY`.
If the wrapper itself is killed before it can clean up, persistent `ACTIVE` domain claims block new
runs until exact operator reconciliation; the Web layer never clears or overrides those claims.

Fixed sequential and parallel modes differ only in resource cardinality. All three modes use the
same point manifest and perception/evidence primitives. Adaptive state, event, terminal, and
qualification semantics come only from the Runner. The Web service never implements a hidden
legacy execution path or converts one mode into another.

The browser submits typed intent and renders state. It never constructs shell commands, chooses ROS
state-machine transitions, or sends joint targets.

The existing Teleop server and `/tasks` task station remain unchanged. On the dedicated validation
server, `/` redirects to `/expert-validation`; `/tasks` and existing task-mutation APIs return a
disabled capability and never attach to a simulation. A regular Teleop server that was not started
in validation mode also reports validation as unavailable rather than pretending it can restart its
own stack.

### 3.1 Execution configuration

The frozen campaign request contains:

```text
execution_mode: SEQUENTIAL | PARALLEL | ADAPTIVE
worker_count
max_points_per_worker                 # fixed modes only
preferred_worker_count                # adaptive, default 8
fallback_worker_counts                # adaptive, default [6, 4, 2, 1]
initial_points_per_worker             # adaptive affinity, default 3
worker_start_timeout_s                # adaptive, default 120
max_infra_attempts_per_point          # adaptive, default 5
yolo_executor_count                   # adaptive, default 2; allowed 1, 2, or 4
parallel_config_sha256
adaptive_config_sha256                # adaptive mode only
run_mode: execute
```

`SEQUENTIAL` requires `worker_count=1`. `PARALLEL` requires `2 <= worker_count <= 3`.
`K` is a positive integer no greater than 20. The server defaults K to
`ceil(total_points / worker_count)`, shows the computed value before start, and allows an advanced
override. It never silently lowers Worker count, raises K, changes the selected mode, or creates
fixed point shards. A Worker dynamically leases the next eligible point.

`ADAPTIVE` invokes `scripts/run_so101_adaptive_batch.zsh`, which in turn owns
`so101_parallel_batch --adaptive-workers`; it rejects `max_points_per_worker` and fixed-mode
live-headroom arguments. The preferred Worker count defaults to 8 and accepts W1 through W16.
Fallback counts default to `6,4,2,1` and must be strictly decreasing below the preferred tier; an
explicit experiment may use an empty fallback list, including a W1 run. The Web default remains the
full ladder ending at W1. `initial_points_per_worker=3` is only an initial affinity hint and never a
capacity limit. The request also freezes `worker_start_timeout_s=120`,
`max_infra_attempts_per_point=5`, `yolo_executor_count=2`, and the adaptive configuration hash.
The upstream contract accepts executor counts 1, 2, or 4; version 1 of this Web page exposes the
frozen value 2 read-only. All Workers in a generation must report READY before the Runner records
`POOL_RUNNING` or releases work.

Version 1 Web campaigns expose only `run_mode=execute`. The coordinator CLI may support
`dry_run` and `plan_only` for implementation tests, but those results keep physical points
`UNRUN` and can never produce a Web qualification result.

### 3.2 Capability and admission boundary

Capabilities report the installed coordinator, adaptive Runner, production pool factory, cleanup
entry point, and wrapper executable/module hashes, parallel/adaptive config hashes,
supported modes, default mode, Worker range, K range, available ROS domains, model hashes, queue
limits, deadlines, `yolo_executor_count`, and current admission result. The source dependency is
satisfied by `25d1130a`, but `PARALLEL` remains unavailable on a concrete host unless the installed
implementation, combined model Broker, task-owned overlay, resource probe, and accepted fixed-mode
live gate all exist and match their declared provenance. `ADAPTIVE` remains unavailable unless its
Runner, production pool factory, wrapper, cleanup entry point, frozen configuration, and accepted
W1/W2/W4/W6/W8 qualification evidence exist and match current provenance. The W10 sample is reported
as additional evidence, not used to change the default. W16 must be reported as contract-supported
and live-unqualified.

Before start, the service validates `N × K`, manifest identity, source/install/config/policy/scene
and model hashes, evidence-root ownership, coordinator singleton status, CPU/RAM/GPU admission, and
the absence of unresolved owned processes. Resource failure rejects start; it does not downgrade a
parallel request to sequential.

Adaptive preflight instead validates mutually exclusive request fields, ladder ordering, short
1-5-character ASCII batch ID and `<evidence-root>/r/<batch-id>` runtime path,
source/install/config/model/Broker provenance, domain claims, singleton ownership, and unresolved
cleanup. CPU, RAM, GPU, pressure, and real-time-factor measurements are recorded as observations
only and cannot admit, reject, or choose a tier. Only observed process, OOM, RPC, Broker, startup,
or cleanup outcomes drive adaptive degradation.

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
pool. The capabilities API returns this limit and the selected catalog profile. Version 1 execute
campaigns use only the frozen `seed=20260911` catalog required by the parallel coordinator; seed is
displayed as provenance, not editable input. A later calibrated catalog can add another profile
without changing a stored manifest, but it needs a new catalog/version/hash and separate runtime
qualification.

### 4.2 Catalog and selection contract

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

The installed package contains the exact complete 16-point pool for `seed=20260911`; the Web
service verifies its catalog SHA256 rather than regenerating execute coordinates at request time.
For a request below 20 total points, it allocates the requested pool size across the nine strata with
the largest-remainder method, using the 16-entry schedule above as the quota source. Ties follow
first appearance in that schedule. It selects the earliest catalog members of each allocated
stratum, restores canonical pool order, and assigns consecutive display IDs. The selected canonical
point-ID list has its own selection hash. This matches the coordinator's complete catalog plus
repeatable `--point-id` contract and avoids creating another point YAML.

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
different profile, such as `geometry_v2`; that profile is preview-only until a matching coordinator
catalog and runtime qualification exist. The Web page uses `ai_station_baseline_v1` for version 1
execute campaigns.

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
catalog_seed, total_points and ordered selection hash
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
| Eligible `UNRUN`, `LEASED`, `RUNNING`, `INFRA_INTERRUPTED` while adaptive fallback remains possible, or active Worker stage | blue | matching pale blue |
| `PASSED` | green | matching pale green |
| Business `FAILED`, fixed-mode `INDETERMINATE`, terminal `UNRUN`, or any point blocked by terminal `INFRA_FAILED` or unresolved invalid evidence | red | matching pale red |

An active point uses a thicker blue stroke and an accessible label containing Worker ID and stage.
Marker diameter does not change with state. Selection adds an outer focus ring without changing the
position marker. Colour is not the only status signal: terminal markers also carry a shape/icon and
screen-reader label. Fixed-mode `INDETERMINATE` remains a distinct state even though it shares the
red palette. Adaptive attempt-level `INDETERMINATE` remains visible in history, but the point stays
blue when the Runner has safely classified it `INFRA_INTERRUPTED` and can requeue it; if the Runner
ends `INFRA_FAILED`, remaining `UNRUN` and `INFRA_INTERRUPTED` points become red terminal blockers.

The maintained Python top-view tool and the React SVG component consume the same geometry and
status model. Shared golden tests compare their projected coordinates, point order, radii, status
colours, and the 20-point compatibility fixture. The Web page does not invoke the Python script at
runtime.

## 6. Page layout and operator flow

The new route is `/expert-validation`.

### 6.1 Campaign setup

The setup card contains:

- final point count;
- catalog profile and read-only seed/hash provenance;
- execution mode, defaulting to `SEQUENTIAL`;
- Worker count, fixed to 1 for sequential mode and selectable from 2 to the admitted maximum for
  parallel mode;
- fixed-mode `max_points_per_worker`, with an advanced override and a visible `N × K` capacity
  check;
- adaptive preferred tier, fallback ladder, initial points-per-Worker affinity, startup timeout,
  and infrastructure-attempt limit. Adaptive mode hides and rejects K;
- `Generate points`, which creates a frozen manifest but does not move the robot;
- sampler version, capacity, manifest hash, geometry/policy hashes, parallel config hash, model
  hashes, and current mode-specific preflight result. Adaptive resource readings are labelled
  observational and are never displayed as an admission score;
- `Start validation`, enabled only with a current manifest and valid control lease.

Changing count invalidates the preview until the operator generates a new manifest.
Changing execution mode or any mode-specific execution field leaves the point manifest intact but
invalidates the start-request preview and requires a new preflight.

### 6.2 Map and progress

The map occupies the left side of the main area. The right side shows campaign state, execution
mode, mode-specific execution summary, coverage, first-pass success state, shared Broker health,
first shared failure, and an ordered point list. Adaptive campaigns additionally show preferred,
current, and final Worker tiers; `levels_used`; fallback transitions and reasons; current pool
generation; remaining points; per-Worker load; elapsed time; infrastructure-attempt count; and
observational CPU/RAM/GPU/pressure/RTF data. A Worker panel shows each stable slot's
`worker_id`, generation, state, current point, lease count/K, last heartbeat, active deadline,
recovery result, and quarantine reason. Selecting a map point, point row, or Worker's current-point
link updates the same selected-point state.

Fixed-mode first-pass summaries use these explicit counts:

```text
requested = every point in the frozen manifest
evaluated = points with an accepted reachability decision
execution_started = points with an accepted ATTEMPT_STARTED event
valid_succeeded = point status PASSED
valid_failed = point status FAILED
indeterminate = point status INDETERMINATE
invalid_attempts = attempt records with status INVALID
not_executed = terminal point status UNRUN
evaluation_coverage = evaluated / requested
execution_coverage = execution_started / requested
qualified_first_pass_success_rate = valid_succeeded / (valid_succeeded + valid_failed)
```

`qualified_first_pass_success_rate` is unavailable when its denominator is zero or when campaign
cleanup is unresolved. An unreachable point is an evaluated `FAILED` result with an unreachable
reason; it does not increment `execution_started` and is not `UNRUN`. Invalid attempts and
unexecuted points do not enter the success-rate denominator. When capacity exhaustion, shared
dependency failure, cancellation, or quarantine prevents more leases, untouched points finish as
`UNRUN` with a reason. A point result accepted before a later shared failure remains frozen.
Recovery failure after commit preserves the point result but makes `batch_cleanup_complete=false`.

Terminal reconciliation uses this precedence:

| Observed boundary | Terminal point state | Counting rule |
|---|---|---|
| Accepted successful result manifest and `RESULT_COMMITTED` | `PASSED` | `valid_succeeded` |
| Accepted product-failure result, including unreachable | `FAILED` | `valid_failed` |
| Formal attempt started, but its outcome cannot be proven after lease expiry, owner loss, timeout, or journal ambiguity | `INDETERMINATE` | separate count; never retried in this campaign |
| Attempt invalidated before formal execution and safely fenced | remains eligible until capacity or batch termination | increment `invalid_attempts`; a later attempt may execute the point |
| Point never obtains a terminal execution opportunity | `UNRUN` with capacity, cancellation, dependency, or quarantine reason | `not_executed` |

Historical `RESULT_COMMITTED`, `LEASE_EXPIRED`, and point-terminal events cannot be overwritten by
a later file scan or Web projection. A later campaign-level failure does not overwrite an accepted
point result. Every terminal campaign must reconcile all requested points into
`PASSED | FAILED | INDETERMINATE | UNRUN` and contain no active lease or Worker stage.

The Web reads the coordinator's authoritative `coverage_complete`, `execution_complete`,
`batch_cleanup_complete`, and `qualification_passed` fields. It may derive display counters from
accepted events, but a derived value can never turn a false coordinator qualification into true.
`coverage_complete` requires every point to be `PASSED` or `FAILED`;
`qualification_passed` additionally requires every point to be `PASSED` and batch cleanup to be
complete.

Retry outcomes appear in a separate attempt summary and never alter first-pass counts or the frozen
first-pass fraction.

Adaptive campaigns use the Runner's mode-specific summary instead of deriving the four fixed-mode
qualification flags. Runner terminal status is `COMPLETED`, `COMPLETED_WITH_FAILURES`, or
`INFRA_FAILED`. `COMPLETED` requires every final point to be `PASSED` and cleanup complete;
`COMPLETED_WITH_FAILURES` requires every point to have a business terminal result, at least one
`FAILED`, and cleanup complete. `INFRA_FAILED` covers exhaustion at W1, infrastructure-attempt
limits, Runner loss, or failure to complete the required degradation/cleanup transaction. The UI
must preserve attempt-level `INDETERMINATE` records and fallback history while showing the Runner's
final per-point state; a later result never deletes or rewrites an earlier attempt.
Wrapper exit status is not a substitute for this journal summary: exit 0 represents only
`COMPLETED`, while exit 1 may represent either `COMPLETED_WITH_FAILURES` or `INFRA_FAILED`.

### 6.3 Evidence

The selected-point panel lists the first-pass result followed by retry attempts in time order. It
shows image artifacts inline when their media type is supported and exposes downloads for RGB,
task-camera frames, point-cloud previews, PLY, JSON, and logs. It also exposes the assigned Worker,
lease/attempt identity, initial-state receipt, YOLO/Grounded-SAM decision chain,
`POSE_ACCEPTED`, planning/controller/physical evidence, sealed result, and recovery receipt.
Every link uses a manifest-registered opaque artifact ID. Browser-visible responses contain no
absolute evidence path.

### 6.4 Retry

After a fixed first pass reaches a safe terminal state, or an adaptive first pass reaches
`COMPLETED_WITH_FAILURES` with cleanup complete, points whose authoritative first-pass status is
`FAILED` can be selected. `INDETERMINATE`, `UNRUN`, and points with unresolved invalid attempts
require a new first-pass campaign after the underlying condition is corrected; they are not product
failure retries. The
`Retry selected with FULL_RESTART` action requires the explicit confirmation string
`CONFIRM FULL_RESTART RETRIES`.

An adaptive infrastructure interruption, fallback, or automatic re-execution is never eligible for
this action. An adaptive `INFRA_FAILED` campaign must be diagnosed and rerun as a new first-pass
campaign; it cannot enter the product-failure retry queue.

Selected points run serially. Each becomes a new fixed-mode one-point coordinator batch with
`worker_count=1`, `max_points_per_worker=1`, a new batch/attempt ID, simulation session,
coordinator epoch, Worker generation, lease generation, ROS domain, process groups, evidence child,
and terminal cleanup record. The next retry is not dequeued until the previous batch reports
`batch_cleanup_complete=true` and all registered descendants are gone. A retry button is disabled
for `PASSED`, `INDETERMINATE`, `UNRUN`, a non-terminal first pass, any active execution,
`NEEDS_OPERATOR_RECOVERY`, or unresolved cleanup.

## 7. API

The validation server exposes these routes:

| Method and route | Purpose |
|---|---|
| `GET /expert-validation/capabilities` | Return mode-specific availability, sampler limits, fixed Worker/K limits, adaptive ladder/defaults, executor operations, frozen hashes, and preflight capability. |
| `POST /expert-validation/lease` | Acquire the supervisor-scoped control lease for one service session. |
| `PUT /expert-validation/lease/{lease_id}` | Renew the current lease before its server-defined expiry. |
| `DELETE /expert-validation/lease/{lease_id}` | Release an idle lease; an active campaign requires cancellation or completion first. |
| `POST /expert-validation/manifests` | Generate and persist one immutable point/geometry manifest. |
| `GET /expert-validation/manifests/{manifest_id}` | Read an existing manifest. |
| `POST /expert-validation/campaigns/preflight` | Validate the typed fixed or adaptive execution configuration, provenance, singleton/domain ownership, cleanup state, and Broker readiness without starting motion. |
| `POST /expert-validation/campaigns` | Start one fixed coordinator batch or one adaptive production wrapper. |
| `GET /expert-validation/campaigns` | List retained campaign summaries. |
| `GET /expert-validation/campaigns/{campaign_id}` | Read mode-specific execution owner, batch/Runner summary, generation, Worker, point, progress, evidence, and retry state. |
| `POST /expert-validation/campaigns/{campaign_id}/cancel` | Request cancellation at a safe checkpoint. |
| `POST /expert-validation/campaigns/{campaign_id}/full-restart-retries` | Start serial retries for selected failed point IDs. |
| `GET /expert-validation/artifacts/{artifact_id}` | Read one manifest-registered artifact. |
| `WS /expert-validation/events` | Stream sequenced progress hints; HTTP state remains authoritative. |

Manifest generation and evidence reads are non-moving operations. Preflight requires the current
supervisor-scoped lease because its receipt is bound to that lease generation. Campaign start,
cancel, and retry additionally require a command ID and durable server-side idempotency. A repeated
command ID with the same canonical request returns its stored result. The same ID with different
content fails with `COMMAND_ID_REUSED`; an ambiguous pre-crash command returns
`COMMAND_OUTCOME_UNKNOWN` and cannot be submitted under a new ID until reconciliation finishes.

The start body freezes `manifest_id`, `execution_mode`, a tagged execution-configuration object,
`executor_id`, `operation_id`, and the preflight receipt ID. Fixed configuration contains
`worker_count` and `max_points_per_worker`; adaptive configuration contains preferred/fallback
tiers, initial affinity, startup timeout, infrastructure-attempt limit, frozen
`yolo_executor_count=2`, and adaptive config hash, and must not contain K or fixed-mode live-headroom
arguments.
`SEQUENTIAL` with N other than 1, `PARALLEL` outside the admitted 2–3 range, insufficient N×K,
or a stale preflight receipt is rejected before execution-owner spawn. Invalid adaptive field
combinations, ladder order, batch ID, or runtime-root identity are rejected before wrapper spawn.
The response returns the Web `campaign_id`, execution-owner kind/identity, and immutable upstream
batch identity; the IDs are never inferred from each other.
Preflight allocates and returns the prospective `campaign_id` inside its receipt but starts no
process and performs no motion. Start atomically consumes that one-shot receipt and returns the same
campaign ID; the receipt binds the service session and current lease generation and cannot be reused
for a second campaign or with a different lease/session.

The validation service creates a stable service session for the browser. It is independent of
`batch_id`, coordinator epoch, Worker generation, lease generation, attempt ID, and simulation
session. Lease duration and renewal margin come from capabilities. A browser disconnect does not
release the lease or stop an attempt. Web lease expiry asks the fixed coordinator through its
authenticated control channel, or sends the adaptive wrapper an identity-checked cancellation
request, to stop issuing work and cancel safely; it never signals a Runner, Worker, Broker, or
simulation process directly. After expiry, another service session may acquire the lease only to inspect,
cancel, or reconcile the unresolved campaign. A server restart invalidates every Web lease,
restores durable command/batch bindings, and requires a new lease after execution-owner reconciliation.
Releasing a lease while a campaign is active fails closed.

The WebSocket is an acceleration path, not the source of truth. Reconnect always reads the campaign
resource before applying later event sequences.

## 8. Persistent state, progress, and evidence

### 8.1 Web store and upstream journals

The Web supervisor uses one durable store under its configured evidence root. It contains manifest
references, canonical Web command fingerprints and results, service leases, campaign-to-batch
bindings, tagged execution configuration and hash, execution-owner kind and process identity,
accepted top-level upstream cursor/hash, current adaptive generation and fallback-history cache,
retry queue/cursor, and Web projection cache. A process-wide lock admits only one Web writer.

For fixed modes, the coordinator's framed fsync journal remains authoritative for queue state, K debit, point lease,
Worker generation, attempt authorization, Broker health, sealed result acceptance, point status,
recovery, capacity exhaustion, and batch qualification. The Web store does not duplicate those
events as independent truth. It records the last accepted upstream event identity and validates the
hash chain again after restart.

For adaptive mode, the Runner's framed fsync journal is the top-level authority for pool state,
generation transitions, imported terminal results, infrastructure interruptions and attempt counts,
fallback history, final point states, terminal Runner status, and batch cleanup. Generation
coordinator journals and manifests are nested evidence referenced by the Runner; the Web relay does
not merge them independently or bypass the Runner.

State-changing commands follow this order:

1. validate the Web lease, manifest, tagged execution configuration, preflight receipt, current state, and command
   fingerprint;
2. commit the Web command intent and campaign-to-upstream identity;
3. commit execution-owner intent before the coordinator or wrapper crosses its exec barrier;
4. record the fixed coordinator PID/PGID/start-time/control socket or adaptive wrapper PID/start
   time/Runner binding acknowledgement and only then release the barrier;
5. let the coordinator or Runner persist and ACK all transitions in its authoritative journal;
6. accept the mode-specific terminal summary and cleanup receipt before returning a terminal Web
   command result;
7. dequeue a retry only after the preceding one-point batch is terminal, cleanup-complete, and its
   coordinator process is reconciled.

On restart, the supervisor takes the singleton lock, invalidates old leases, and reconciles the
durable execution-owner record. It asks a fixed coordinator to replay its journal or reconnects to
a still-running adaptive wrapper/Runner and replays the Runner journal. It never reconstructs
Worker state by scanning processes or
sealed directories itself, repeats an ambiguous command, or starts a second coordinator while
ownership or cleanup is unresolved. A cleanly terminal batch can be restored. An adaptive Runner
crash is never resumed automatically. Journal corruption, identity mismatch, an unreachable active
execution owner, or an unresolved descendant inventory becomes
`NEEDS_OPERATOR_RECOVERY`.

### 8.2 Progress framing

The Web event relay consumes the mode-specific top-level framed, checksum-protected journal. Fixed
coordinator boundaries include:

```text
BATCH_STARTED / LEASE_GRANTED / ATTEMPT_STARTED
POSE_ACCEPTED / RESULT_COMMITTED / LEASE_EXPIRED
WORKER_RECOVERY_RECORDED / WORKER_QUARANTINED
BROKER_HEALTH_CHANGED / BATCH_FINISHED
```

Adaptive Runner boundaries additionally include pool state
`CREATED | STARTING(Wn) | RUNNING(Wn) | DEGRADING(Wn->Wm) | COMPLETED |
COMPLETED_WITH_FAILURES | INFRA_FAILED`, generation identity, READY barrier, fallback reason,
terminal-result import, infrastructure-attempt count, and cleanup result. Adaptive point working
states are `UNRUN | LEASED | RUNNING | INFRA_INTERRUPTED | PASSED | FAILED`; `PASSED` and `FAILED`
are immutable across generations.

Worker stage and heartbeat events may provide finer progress when their schema is frozen. Log
parsing is never an authoritative phase signal.

Each top-level event carries schema version, batch ID, event ID, idempotency
key, previous-frame hash, identity fields, event type, canonical payload, and timestamp. The
fixed schema includes coordinator epoch; the adaptive schema includes Runner and pool-generation
identity plus nested coordinator references. The validated contiguous journal is the commit authority. Upstream and Web snapshots are rebuildable
caches, not additional commit decisions.

For a point result, the Worker fsyncs its files, atomically changes `working/` to `sealed/`, and
submits the manifest under the current lease. The coordinator validates identity and evidence,
fsyncs `RESULT_COMMITTED`, and only then returns ACK. The Web relay validates the next committed
frame and referenced manifest, records its accepted cursor, and only then exposes the projection
through HTTP or WebSocket.

The Web relay reads only the bound fixed coordinator journal or adaptive Runner journal. An
incomplete EOF tail is handled by the applicable upstream recovery contract. A complete checksum error, broken segment chain, identity mismatch,
invalid manifest, duplicate result, or event that conflicts with the stored binding blocks the Web
projection and enters `NEEDS_OPERATOR_RECOVERY`. On recovery, accepted frames are replayed
idempotently; snapshots ahead of the journal are discarded. If the Web process crashed after
coordinator commit but before HTTP response, Web command idempotency returns the already-bound
batch and current coordinator state.

The first-pass campaign manifest stores every requested point from the start. A fixed point can be
presented as pending while its coordinator status is eligible `UNRUN`, and fixed terminal
reconciliation uses `PASSED | FAILED | INDETERMINATE | UNRUN`. Adaptive projection follows the
Runner working and terminal states above. A possibly-started infrastructure attempt remains
attempt-level `INDETERMINATE`; after exact old-generation cleanup and a fresh initial-state gate,
the Runner may safely requeue the point as `INFRA_INTERRUPTED`. Point result manifests and the
terminal batch
manifest reuse the artifact registry and checksum rules. Retry attempts link to `campaign_id`,
their one-point `batch_id`, and the original point ID.

Evidence roots follow the repository SO-101 policy. The validation server is started with one
absolute, non-symlink task-family root. Each campaign receives a child, and each coordinator batch
owns the expected `workers/`, `events/`, `scratch/`, and `reports/` layout beneath it. The
Adaptive campaigns additionally allocate the required short-ID runtime root
`<evidence-root>/r/<batch-id>` and identify every artifact by Runner batch, pool generation,
coordinator batch, Worker, lease, and attempt. The service rejects `..`, absolute client paths, symlink traversal, unregistered files, and files
outside the configured root. Worker and Broker evidence remain single-writer.

## 9. Supervisor lifecycle

The first-pass state machine is:

```text
IDLE
  -> PREFLIGHTING
  -> STARTING_COORDINATOR | STARTING_ADAPTIVE_WRAPPER
  -> RUNNING_SEQUENTIAL_BATCH | RUNNING_PARALLEL_BATCH | RUNNING_ADAPTIVE_BATCH
  -> FINALIZING
  -> COMPLETED | PARTIAL_FAILED | FAILED | CANCELLED | NEEDS_OPERATOR_RECOVERY
```

The retry queue is:

```text
IDLE
  -> PREFLIGHTING_ONE_POINT_BATCH
  -> STARTING_COORDINATOR_N1_K1
  -> RUNNING_FULL_RESTART_POINT_BATCH
  -> FINALIZING_BATCH
  -> next selected point or terminal retry summary
```

Only one of these paths can be active. Before starting a stack, the supervisor reconciles its durable
execution-owner record and verifies that no previous coordinator, adaptive wrapper/Runner, or batch cleanup is
unresolved. The selected upstream owner then performs its own domain/Worker/Broker reconciliation.
Unknown conflicting processes fail the request; neither layer kills them automatically.

For a fixed first pass, the Web supervisor starts one coordinator with the frozen mode/N/K request. The
coordinator creates stable Worker slots, starts one isolated headless
`sensor_rendering=true,include_teleop=false` stack per execute Worker, starts the shared model
Broker, and dynamically leases points. `SEQUENTIAL` uses the same path with one slot. Every point
must pass `worker_ready_gate`, receive a durable lease, reset to its exact scene, pass
`point_initial_gate`, and receive a durable `ATTEMPT_STARTED` ACK before perception or motion.

For an adaptive first pass, the supervisor invokes the production wrapper with the frozen adaptive
request. The wrapper owns one Runner child; the Runner starts exactly one coordinator generation at
a time. Every generation must pass the all-Workers READY barrier before point release. On an
infrastructure failure, the Runner stops new leases, fsyncs accepted terminal results, classifies
in-flight attempts, performs exact generation cleanup, proves old resources gone, requeues only
`UNRUN` and `INFRA_INTERRUPTED`, and starts the next configured tier. Business `FAILED` does not
degrade the pool. A W1 infrastructure failure or any failed cleanup ends `INFRA_FAILED`.

For a retry, the Web supervisor starts a new one-point coordinator batch. The Worker proves initial
state, executes one point, seals terminal evidence, recovers, and shuts down. This is the counted
`FULL_RESTART` boundary. Reusing a first-pass Worker or changing only its world state is not a
`FULL_RESTART` retry.

Visual evidence comes from each Worker's fixed task camera with source stamps newer than the reset
or action boundary. Shared desktop screenshots are not required for a parallel qualification and
cannot replace RGB-D, TF, controller, physical, Planning Scene, or cleanup evidence. The maintained
GNOME/macOS capture adapters remain available to existing interactive Teleop workflows but are not
an ownership dependency of a counted parallel campaign.

The supervisor records execution-owner kind and intent, spawn token, exact process identity,
control endpoint where applicable, source/install/runtime fingerprints, batch ID, and cleanup state
before reporting ownership. After restart, it resumes observation only after durable Web
command/binding state and the applicable top-level journal, ownership, point, safety, and cleanup
records reconcile. It does not
resume robot execution from a guessed state. An active coordinator with ambiguous identity is
preserved for operator recovery, and the campaign becomes `NEEDS_OPERATOR_RECOVERY`.

## 10. Cancellation, safety, and failure semantics

Execution outcome, Worker recovery, pool-generation cleanup, and batch cleanup are separate records. Every attempt exit,
including product failure, shared failure, timeout, corrupt progress, owner death, lease expiry, and
cancellation, must seal or attempt to seal its result and append a Worker recovery receipt. The
coordinator emits a batch cleanup receipt only after every Worker/Broker/controller/process boundary
is reconciled. Safety evidence contains:

```text
campaign_id, batch_id, worker_id/generation, lease generation and attempt_id
simulation_session_id and reset/release epoch
observed_at and freshness bound
cup_held and support_confirmed
robot_hold_requested and robot_hold_confirmed
controller_stop_confirmed
safe_to_shutdown
reason_code
evidence artifact IDs
```

No layer fabricates a recovery or cleanup receipt from a process exit code. Missing, stale, or
identity-mismatched evidence makes recovery fail and normally quarantines that Worker. Other healthy
Workers may continue while queue and capacity remain. The Web campaign cannot qualify unless
`batch_cleanup_complete=true`. If the coordinator cannot safely contain the affected Worker or
cannot prove control has stopped, the campaign enters `NEEDS_OPERATOR_RECOVERY`; it does not reset,
open the gripper, start another coordinator, or claim cleanup.

Fixed-mode cancellation uses an authenticated Web-supervisor-to-coordinator control channel tied to
campaign/batch identity and coordinator epoch. The coordinator stops new leases, fences invalid
generations, asks active Workers to cancel and confirm controller goals, and reconciles untouched
points to `UNRUN`. If the coordinator does not acknowledge within the configured bound, the Web
supervisor does not signal Worker groups. It records the timeout and enters
`NEEDS_OPERATOR_RECOVERY`. Signalling the coordinator PGID is allowed only after a fresh batch
cleanup receipt confirms no held cup, active controller goal, or unresolved descendant.

Adaptive cancellation targets only the registered wrapper PID after PID/start-time/batch identity
verification. The wrapper forwards the request to the Runner and owns the exact
`so101_parallel_batch_cleanup` boundary. The Web layer never signals the wrapper PGID because that
would directly broadcast to Runner or generation descendants. Missing acknowledgement with
unresolved cleanup becomes `NEEDS_OPERATOR_RECOVERY`; wrapper-confirmed cleanup produces the
Runner-defined terminal result.

The UI distinguishes product failures, indeterminate outcomes, invalid attempts, and unexecuted
points, although their terminal point markers share the requested red palette:

- a valid perception, planning, controller, grasp, transport, release, placement, or evidence-gate
  failure counts in that lifecycle's denominator;
- an authorized attempt whose result cannot be proven is `INDETERMINATE`, not an ordinary
  `FAILED` result;
- missing provenance, wrong initial state, stale lease, Broker infrastructure error, or a safely
  fenced pre-execution loss is an `INVALID` attempt and is reported separately;
- an unreachable point is a valid `FAILED` point and later points continue when capacity and
  shared dependencies remain healthy;
- Broker failure pauses new leases; recovery deadline expiry terminates with
  `SHARED_DEPENDENCY_UNAVAILABLE`;
- Worker recovery failure quarantines that slot. Other slots continue if they have capacity;
- cleanup failure after a one-point retry stops the retry queue before another coordinator starts.

When signal escalation is permitted, the coordinator signals only its registered Broker/Worker
groups, first with `SIGINT` and then bounded `SIGTERM`. The Web supervisor applies the same rule only
to the registered coordinator group. Neither uses process-name matching. Cleanup is complete only
after all registered descendants disappear and assigned ROS domains no longer expose owned graphs.
A surviving descendant or unknown process keeps ownership unresolved.

## 11. ACT extension boundary

Campaigns carry an `executor_id`, `operation_id`, execution mode, tagged fixed/adaptive execution
configuration, and executor configuration hash. Version 1
registers:

```text
executor_id: moveit_expert
operation_id: validate_pick_place
```

The backend registry exposes typed executor capabilities, allowed operations, and compatible
execution modes. Future ACT work
can register `act_collect` and `act_rollout` operations with their own request model, evidence
schema, controls, and success contract. Expected collection actions include Search, Start
Recording, Run Expert, Keep, and Discard, as described in the ACT head/wrist design.

The extension does not put high-frequency control in the browser. An ACT executor must still use a
server-side controller-ownership broker, safety supervisor, and evidence writer. A batch point lease
never grants ACT control authority. MoveIt expert, ACT collection, and ACT rollout statistics remain
separate even when they share the same point manifest or scheduler implementation.

A successful MoveIt validation point does not automatically qualify as an ACT demonstration or
held-out ACT evaluation point. ACT collection adds a separate immutable manifest with head/wrist
camera visibility, frame timestamps and freshness, robot observation/action alignment, deterministic
neck-search initial state, scene randomization, Keep/Discard decision, and split membership. ACT
rollout adds its own policy checkpoint, observation contract, safety result, and success denominator.

## 12. Testing

### 12.1 Catalog, selection, and map

- exact `ai_station_baseline_v1` 20-point compatibility fixture for `seed=20260911`, including
  source manifest and sampler hashes, bands, ordered strata, 15 mm threshold, six-decimal rounding,
  and rejection cap;
- frozen catalog byte/hash verification, four-anchor prefix, deterministic count-based selection,
  ordered selection hash, and stable subset tests;
- count bounds, finite values, pairwise separation, table clearance, and stale-input rejection;
- shared Python/React projection fixtures for table, base, target, cup radius, marker radius, and
  status colours;
- an explicit test that the separate 35 mm geometry profile cannot be substituted for the frozen
  baseline profile.

### 12.2 Supervisor and service

- request tests for `SEQUENTIAL => N=1`, `PARALLEL => N=2..3`, default K, explicit K,
  `N×K` rejection, `ADAPTIVE` field exclusivity, W1–W16 bounds, frozen default fallback ladder,
  optional empty fallback, no K, frozen C2 executor count, short batch ID, no silent mode conversion,
  and stale preflight rejection;
- coordinator-process tests for spawn intent/ACK, reconnect, conflicting PID/start time, socket
  ownership, journal corruption, and surviving descendants;
- projection tests for multiple simultaneous Worker stages, generation changes, K debit,
  quarantine, Broker pause/recovery, capacity exhaustion, and dynamic point assignment;
- adaptive projection tests for W8 startup failure to W6, W8 mid-run infrastructure failure to W6,
  READY barriers, immutable business terminals, attempt-level `INDETERMINATE`,
  `INFRA_INTERRUPTED` requeue, cleanup failure, W1 exhaustion, and all Runner terminal statuses;
- one fresh N=1/K=1 coordinator batch per selected retry, strict serial order, unique
  batch/epoch/session/domain/attempt identities, and cleanup-before-next-start assertions;
- durable Web idempotency tests at coordinator spawn, batch binding, terminal acceptance, and retry
  dequeue boundaries; the upstream coordinator suite remains responsible for Worker lease/result
  commit crash windows;
- cancellation tests proving the Web layer uses authenticated fixed-coordinator control or an
  identity-checked adaptive wrapper PID and never signals Runner, Worker, or Broker groups;
- count and denominator tests for `PASSED`, `FAILED`, `INDETERMINATE`, retried `INVALID`
  attempts, terminal `UNRUN`, zero valid attempts, unreachable failures, quarantine, shared
  dependency failure, and cleanup ambiguity;
- upstream journal relay tests after coordinator fsync, before Web cursor commit, after Web cursor
  commit, and before HTTP response;
- artifact allow-list, symlink, traversal, media type, checksum, and cross-campaign isolation tests;
- OpenAPI snapshot and generated TypeScript schema checks.

### 12.3 Web

Use the repository Bun toolchain. Component tests cover count/catalog input, manifest invalidation,
mode-specific input, fixed capacity/admission feedback, adaptive observational metrics and fallback
timeline, equal-radius SVG markers, exact status colours, map/list/Worker shared selection,
concurrent progress recovery, Broker/Worker health, evidence
previews, retry eligibility, confirmation, and separate first-pass/retry statistics. Playwright
uses fixed-coordinator and adaptive-Runner API fixtures; it must not start MuJoCo.

### 12.4 ai-station simulation acceptance

After source tests and package tests pass, build a task-owned overlay on ai-station and verify the
installed coordinator, validation server, Web bundle, model container, config, and point-manifest
provenance. With no pre-existing SO-101 application stack:

1. start the validation server with one registered durable evidence root;
2. generate `total_points=4`, run a fixed sequential N=1/K=4 anchor smoke campaign, and inspect fresh
   progress, numeric evidence, task-camera frames, and cleanup through the page;
3. run the same four-point selection as a parallel N=2/K=2 campaign. Verify distinct ROS domains,
   Worker roots, sessions, process trees, dynamic leases, Broker request identity, and no
   cross-Worker artifact or pose exchange;
4. only after both fixed-mode compatibility smokes pass, generate the exact `total_points=20`
   compatibility manifest and start an adaptive first pass through the production wrapper with
   preferred W8, fallback W6/W4/W2/W1, `initial_points_per_worker=3`,
   `yolo_executor_count=2`, and no K. Display and retain every generation, fallback reason, resource
   observation, final point result, and cleanup record;
5. reuse the upstream adaptive acceptance rather than inventing a Web-only fault model: the
   upstream package/live gates must already prove W8 startup failure to W6, W8 mid-run failure to
   W6, a 20-point adaptive run, and W1/W2/W4/W6/W8 performance evidence. The page additionally
   proves one live adaptive launch and projection; deterministic fake-Runner tests exercise every
   fallback UI branch;
6. if that fresh adaptive first pass ends `COMPLETED_WITH_FAILURES` and contains a business
   `FAILED` point, select one and run one independent
   N=1/K=1 `FULL_RESTART` retry through the same page;
7. if every valid point succeeds, record `LIVE_RETRY_NOT_APPLICABLE_ALL_SUCCEEDED` rather than
   fabricating a failure; the deterministic fake-supervisor acceptance must still exercise the
   failure-selection and retry UI, while real-process integration tests prove coordinator restart
   and cleanup;
8. read back campaigns, the Runner journal, nested generation coordinator journals,
   Worker/attempt/recovery manifests, artifact hashes, assigned ROS graphs, Broker generation,
   complete process inventory, and batch cleanup state.

The live result is accepted only from those new runs. Historical baseline screenshots and success
messages do not replace fresh MuJoCo, MoveIt, controller, Planning Scene, perception, task-camera,
recovery, and cleanup evidence. The 20-point result qualifies only when all points are `PASSED`,
`coverage_complete=true`, `execution_complete=true`, `batch_cleanup_complete=true`, and
`qualification_passed=true` under one frozen hash set for fixed modes. The adaptive 20-point result
is accepted only as Runner `COMPLETED` with all final points `PASSED` and
`batch_cleanup_complete=true`; `COMPLETED_WITH_FAILURES` is a valid completed business-failure run,
not a qualification pass. No real-hardware command is part of this acceptance.

## 13. Delivery boundary

The first implementation delivers the MoveIt expert validation workflow, exact map,
sequential/fixed-parallel/adaptive mode selection, coordinator- or Runner-backed Worker progress,
pool generations and fallback history, evidence browser
integration, Web command idempotency, and serial one-point `FULL_RESTART` retries. It depends on the
approved fixed parallel coordinator plus the adaptive Runner, production wrapper, exact cleanup,
Worker, Broker, journals, process supervisor, and headless sensor-rendering runtime. The Web plan
must integrate those modules rather than duplicate or weaken them.

The merged source and retained upstream evidence satisfy the design-time dependency gate. At
runtime, capabilities still return a mode as unavailable whenever the current installed entry
points, hashes, model image, accepted qualification records, domain claims, or cleanup state fail
reconciliation. The Web service must never replace that live check with a hard-coded availability
bit. If the coordinator dependency is absent
entirely, campaign start fails closed; the server does not fall back to the old attached-stack
batch. The existing `/tasks` workflow remains available through its own server mode.

This version does not implement head/wrist cameras, episode recording, ACT training, ACT inference,
Keep/Discard data curation, or real-hardware control. Those operations use the executor extension
after their own approved design tasks are implemented.
