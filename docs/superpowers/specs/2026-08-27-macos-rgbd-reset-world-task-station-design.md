# macOS RGB-D RESET_WORLD batch pick-place and Teleop task station design

**Date:** 2026-08-27

**Status:** Approved in chat on 2026-08-27

**Runtime target:** Local macOS MuJoCo simulation with `headless=false`

**Package scope:** `src/so101_demo_py`, `src/so101_teleop`

**Reviewed main HEAD:** `a2b3f0d386f7abddbe16254430f3360379dc9b40`

**Required MuJoCo fork source:**
`third_party/mujoco_ros2_control@5e9d67ce9fde39d35bf94cc498721abf203a0ddd`, package version
`0.1.0`

**Implementation and acceptance evidence root:**
`/tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/`

## 1. Objective

Add a reusable macOS workflow that starts one visible MuJoCo environment and executes an arbitrary
ordered list of cup positions through the complete perception-driven pick-place chain:

```text
prepare persistent environment
  -> for each point
       atomic RESET_WORLD plus cup pose override
       -> RGB-D perception
       -> point cloud and cup segmentation
       -> tf2 world pose
       -> /cup_pose
       -> dynamic target derivation and reachability gate
       -> dynamic_cup_pick_place
       -> MoveIt
       -> controllers
       -> MuJoCo physical outcome
  -> clean up the owned environment
```

The first acceptance batch contains these four positions:

| ID | World position in metres |
|---|---|
| `task_start` | `(0.02, -0.28, 0.165)` |
| `cup_test_forward_5cm` | `(0.02, -0.33, 0.165)` |
| `cup_test_left_5cm` | `(-0.03, -0.28, 0.165)` |
| `cup_test_right_5cm` | `(0.07, -0.28, 0.165)` |

The implementation must also accept positions that are not named MJCF keyframes. A custom point is
a cup body-origin position in `world`; the cup retains the canonical upright orientation. Custom
points are runtime inputs, not MJCF mutations.

The same task engine is exposed through a standalone batch CLI and a new Teleop task-station page.
The existing Teleop page and API behavior remain compatible.

## 2. Chosen architecture

Use a shared Python batch engine in `so101_demo_py`, a persistent task-station supervisor, and a
separate `/tasks` React page in `so101_teleop`.

This is preferred over a shell loop because the batch owns ROS readiness, process groups, reset
identity, failure classification, checksummed evidence, and ordered cleanup. It is preferred over
browser-driven orchestration because a browser refresh or network interruption must not interrupt a
robot task. The browser submits intent and displays state; the Python engine remains the execution
authority.

The architecture has four boundaries:

1. **Point-list core:** parses, validates, names, orders, and serializes preset and custom points.
2. **Reachability service:** derives the real dynamic pick targets and performs non-executing
   MoveIt checks without changing the live global Planning Scene.
3. **Batch engine:** owns the persistent-session lifecycle and each reset/perception/workflow
   transaction.
4. **Task-station transport:** exposes typed asynchronous job and artifact APIs to the new page. It
   does not contain reset, planning, or workflow policy.

No task-state transition table is copied into Teleop or the browser. The existing dynamic workflow
remains the motion and physical-outcome authority.

## 3. Public runtime entry points

### 3.1 Standalone automatic batch

Add an installed console executable named `so101_mujoco_rgbd_batch`. Its required input is a point
list YAML file. It starts one persistent visible stack, runs all points, writes a batch manifest, and
shuts down only its owned process groups when the batch reaches a normal terminal state.

The default mode is `RESET_WORLD`; `FULL_RESTART` is not offered by this executable. The CLI always
passes `headless=false` for the user-facing macOS run. A future headless test entry may be separate,
but cannot satisfy visual acceptance.

### 3.2 Interactive task station

Add a task-station launch entry that starts the same persistent stack plus Teleop and prints the
local `/tasks` URL. The user selects points and triggers a batch from the page. Completing a batch
stops its per-point perception and workflow children but keeps the Viewer, Teleop, and evidence
browser alive.

The task-station supervisor, not the page, owns the stack process groups. An explicit
`Shutdown Environment` command asks the supervisor to perform the same ordered cleanup as the
standalone CLI. Terminating the launch from its controlling terminal has the same effect.

The task page uses an installed owner executable through the existing Teleop backend-adapter
pattern. It does not import `so101_demo_py` implementation modules into the FastAPI transport.

## 4. Persistent environment

The environment is prepared once per batch or interactive station and contains:

- `robot_state_publisher`;
- `mujoco_ros2_control/ros2_control_node` with the SO-101 MJCF and visible Viewer;
- `joint_state_broadcaster`, `arm_controller`, and `gripper_controller`;
- the SO-101 MoveIt `move_group` process;
- canonical Planning Scene setup;
- `base -> camera_link` and `camera_link -> task_camera_frame` static TF publishers;
- MuJoCo RGB, depth, and CameraInfo publishers;
- the atomic MuJoCo simulation-evidence publisher;
- Teleop in interactive mode only.

The camera transforms remain:

```text
base -> camera_link
  translation = (0.65, -0.65, 0.3600814)
  RPY = (0, 0.517, 2.35619449)

camera_link -> task_camera_frame
  translation = (0, 0, 0)
  RPY = (-1.57079633, 0, -1.57079633)
```

Before the first point, readiness must prove live camera samples, TF, MoveIt, active controllers,
joint feedback, canonical scene readback, one simulation session ID, writable evidence storage, and
source/install/runtime provenance. Source, installed package metadata, and the loaded fork must all
resolve to `mujoco_ros2_control` version `0.1.0` from the approved candidate overlay. A package name
or submodule SHA alone is insufficient runtime proof.

## 5. Point-list contract

The versioned YAML schema is:

```yaml
schema_version: 1
points:
  - id: task_start
    label: Task start
    cup_position_world_m: [0.02, -0.28, 0.165]
```

The parser requires:

- one or more points;
- a unique safe ID and a non-empty label;
- exactly three finite numeric coordinates;
- coordinates accepted by the existing dynamic-policy workspace boundary;
- no unknown fields at schema version 1.

The four presets ship as a package configuration. Teleop may copy them into a task list, but the
server validates the submitted values rather than trusting a preset name.

Custom points exist only in the current browser session until exported. Import and export use the
same schema as the CLI. Teleop does not write custom points into MJCF, package configuration, or the
source tree.

## 6. TCP reachability contract

Reachability is not an XYZ bounding-box check and not a single IK call. It uses the same frozen
dynamic policy and allowed-contact rules as execution to derive and validate the pick-related TCP
sequence, including pre-grasp, grasp, lift, and the transition toward the fixed transport/place
path. The fixed place and retreat path is validated once per batch; point-dependent segments are
validated for every point.

### 6.1 Declared-position precheck

The task builder may request a non-moving precheck for one point or the whole list. It uses:

- the canonical `task_start` robot joint state as the start state;
- the declared cup pose;
- a request-local Planning Scene diff containing the cup at that pose;
- the production dynamic policy, collision geometry, and allowed-contact matrix;
- sequential MoveIt planning so each segment starts from the prior segment's planned end state.

The request-local diff must not mutate the global Planning Scene or move the simulator. The result
records each derived TCP target, IK outcome, joint-limit outcome, planner error code, collision
evidence, and the first failed segment.

The UI states are `PENDING`, `REACHABLE`, `UNREACHABLE`, and `UNKNOWN`. `UNKNOWN` covers unavailable
or stale MoveIt/scene evidence and is never treated as reachable.

### 6.2 Perceived-position execution gate

After reset and perception, the engine derives targets again from the fresh world-frame
`/cup_pose`. It first applies the existing dynamic-policy perception-versus-MuJoCo tolerance. It
then performs the same sequential plan-only reachability check from the actual current joint state
and current scene revision.

Only a passing perceived-position check may enter the motion state machine. A declared point that
was reachable but whose perceived pose is not reachable is a point-local failure. No fixed pose,
declared pose, or prior successful plan may replace a failed perceived target.

## 7. Atomic RESET_WORLD transaction

Each point uses the `mujoco_ros2_control` 0.1.0 `ResetWorld` request with a `SimulationState`
override for the `plastic_cup` free joint. Reset and cup placement are one atomic request; the engine
does not reset and then teleport the cup through a second service.

The reset transaction must:

1. pause physics and quiesce controllers through the existing reset coordinator;
2. reset to the canonical `task_start` keyframe with the requested cup pose override;
3. verify the same non-empty simulation session ID;
4. verify that `reset_epoch` increased by exactly one;
5. verify step-zero cup position and upright orientation against the requested point;
6. verify zero cup twist, canonical robot joints, controller convergence, and no stale attachment;
7. rebuild and read back the canonical Planning Scene;
8. resume physics before perception or dynamic-workflow preflight.

The reset verifier accepts the per-point expected cup pose instead of a hard-coded start position.
All points in a batch share one session and have strictly increasing epochs. RESET_WORLD and prior
FULL_RESTART qualification evidence are never combined into one stability claim.

## 8. Per-point lifecycle

For each point, the batch engine executes this ordered transaction:

1. Allocate an exclusive point evidence directory and record declared input.
2. Run or reuse a fresh declared-position reachability result for the current source and policy.
3. If the point is unreachable, mark `SKIPPED_UNREACHABLE`, capture available visual evidence, and
   continue without resetting or entering the state machine.
4. Perform atomic RESET_WORLD with the cup free-joint override and verify the new epoch.
5. Synchronize and read back the Planning Scene, then resume physics.
6. Start a fresh `dynamic_cup_pick_place` consumer process.
7. Prove through the ROS graph that the consumer has a live `/cup_pose` subscription.
8. Start a fresh `rgbd_cup_pose` process for this point.
9. Obtain one fresh, source-stamped RGB-D result, full point cloud, selected cup cloud, TF result,
   and world-frame `/cup_pose`.
10. Compare the perceived cup pose with atomic MuJoCo evidence.
11. Derive dynamic targets and pass the perceived-position reachability gate.
12. Execute the dynamic state machine through MoveIt and the controllers.
13. Validate the final MuJoCo physical outcome, Planning Scene, controllers, joints, and TF.
14. Capture fresh RGB, point-cloud, and MuJoCo Viewer images and finalize the point manifest.
15. Stop the point-owned perception and workflow children before advancing.

Starting the consumer before the perception publisher removes the volatile `/cup_pose` discovery
race. Each point gets a new perception process so a prior first-valid sample cannot be reused.

## 9. Failure and continuation policy

Point-local failures preserve their evidence and continue with the next point. They include:

- declared or perceived TCP target unreachable;
- reset rejection that leaves the shared stack healthy and verifiably paused;
- fresh-camera or perception timeout;
- RGB-D, segmentation, clustering, TF, or cup-fit rejection;
- perception-versus-MuJoCo divergence;
- point-local planning, execution, grasp, transport, release, or placement failure that reaches a
  verified safe state.

Before continuing, the engine must prove that the cup is not unsupported while physically held and
that the next atomic reset can start from a safe paused state. It captures a MuJoCo Viewer image,
the synchronized RGB frame when available, the point-cloud view when available, the terminal atomic
evidence, and the failing process logs. Screenshot failure is itself recorded and cannot turn the
point into a success.

Shared-environment failures abort the batch because later point results would not be trustworthy.
They include simulator exit, unexpected session change, reset-epoch ambiguity, controller or
MoveIt loss, evidence-root failure, process-ownership loss, and source/install/runtime provenance
change.

If failure or cancellation occurs while the cup is physically held without support, the engine
must not open the gripper, reset automatically, or continue. It pauses MuJoCo, retains evidence,
and enters `NEEDS_OPERATOR_RECOVERY`. Teleop offers explicit `Reset and Continue` and
`Reset and Stop` actions. Both start a new audited reset transaction; neither bypasses the failure.

The batch terminal state is `SUCCEEDED` only if every requested point succeeds. Any skipped or
failed point makes the batch `FAILED` even though later points may succeed. Cancellation produces
`CANCELLED` only after a safe checkpoint; an unresolved held-object state remains
`NEEDS_OPERATOR_RECOVERY`.

## 10. Teleop task page

The existing `/` route continues to render the existing `App` component with its current tabs and
behavior. A separate `/tasks` route renders a new task-station application. It is not added as a tab
inside the old page and does not move old controls.

The new page has three areas.

### 10.1 Task Builder

Task Builder supports:

- adding the four presets;
- adding, editing, deleting, and reordering custom XYZ points;
- YAML import and export without server-side source writes;
- single-point and whole-list reachability checks;
- start, cancel, safe recovery, and environment shutdown actions;
- live batch, point, reset epoch, perception, planning, and state-machine status.

Submitting a batch requires the current simulation session and Teleop control lease. One Teleop
server permits one active batch. While it is active, old-page commands that can move, reset, attach,
detach, repair, or start another workflow fail with `TASK_BATCH_ACTIVE`; read-only telemetry remains
available.

Closing or refreshing the browser does not stop the server-owned job. A fresh `/tasks` page reloads
the active status and completed evidence. Restarting the task-station server is a shared-environment
failure and is not promised to reconnect to an orphan process.

### 10.2 Live Sensor

`Capture now` obtains one synchronized RGB, depth, and CameraInfo triple plus the exact-stamp TF. It
produces:

- source RGB PNG;
- full RGB-D PLY;
- selected cup PLY when segmentation succeeds;
- cup center, source stamp, frame IDs, TF metadata, dimensions, point counts, and checksums;
- a browser-rendered point-cloud PNG when the user saves the current view.

The capture fails closed when the samples are stale or mismatched, depth is invalid, or exact-stamp
TF is unavailable. It never returns a prior frame as the current capture.

### 10.3 Runs and Evidence

The evidence browser lists batches and their point results. A point expands into RGB, full/cup
point-cloud views, MuJoCo Viewer screenshot, reachability records, perception summary, dynamic
manifest, action results, physical outcome, and logs. The page can download individual registered
artifacts and the batch manifest.

## 11. Browser point-cloud viewer

Use Three.js under its MIT license. The viewer uses `PLYLoader`, `THREE.Points`,
`THREE.PointsMaterial`, and `OrbitControls`. This directly accepts the existing PLY evidence and
does not require a Potree conversion pipeline or a geospatial visualization framework.

The dependency decision is grounded in the upstream
[PLYLoader documentation](https://threejs.org/docs/pages/PLYLoader.html) and
[Three.js MIT license](https://github.com/mrdoob/three.js/blob/dev/LICENSE). The implementation pins
one exact Three.js release in `bun.lock`; it does not load viewer code from a CDN at runtime.

The viewer supports:

- full-cloud and cup-cloud selection;
- source RGB color or uniform diagnostic color;
- camera and world coordinate axes;
- detected cup-center marker;
- orbit, pan, zoom, point-size control, and reset view;
- PLY download;
- PNG capture of the current canvas view.

The browser may render a deterministic downsampled derivative when the full cloud exceeds the UI
point budget. The original lossless PLY remains the evidence artifact. The derivative records its
source SHA256, original and displayed point counts, and sampling rule.

Saving a point-cloud screenshot forces one render and obtains a PNG blob from the WebGL canvas. The
upload records source PLY SHA256, view and projection matrices, point size, color mode, background,
viewport dimensions, and capture time. The server verifies PNG type and bounded size before
registering it; it does not trust a client-provided filesystem name.

## 12. Task and artifact API

Add these routes without changing the meaning of existing routes:

| Method and route | Purpose |
|---|---|
| `GET /tasks/presets` | Return the four server-validated presets and schema version. |
| `POST /tasks/reachability` | Run a non-moving check for submitted points. |
| `POST /tasks/runs` | Start one asynchronous batch. |
| `GET /tasks/runs` | List retained batch summaries under the registered root. |
| `GET /tasks/runs/{run_id}` | Return current batch and per-point state. |
| `POST /tasks/runs/{run_id}/cancel` | Request cancellation at a safe checkpoint. |
| `POST /tasks/runs/{run_id}/recovery` | Execute an explicit audited reset-and-continue/stop choice. |
| `POST /tasks/captures` | Capture one fresh synchronized sensor sample. |
| `POST /tasks/captures/{capture_id}/rendered-image` | Register a browser point-cloud PNG and view metadata. |
| `GET /tasks/artifacts/{artifact_id}` | Read one manifest-registered artifact by opaque ID. |
| `POST /tasks/environment/shutdown` | Ask the owning supervisor for ordered shutdown. |
| `WS /tasks/events` | Stream task progress independently of existing telemetry. |

Start, cancel, recovery, reachability, capture, and shutdown commands require the current session
and control lease. Evidence listing and artifact reads are read-only. Mutating commands retain
command-ID idempotency and server-side confirmation for recovery and shutdown.

Artifact IDs resolve only through the task manifest. The server rejects absolute paths, `..`,
unknown artifacts, symlink escapes, non-regular files, and files outside the one registered evidence
root.

## 13. Evidence layout

The implementation and macOS acceptance use the single root registered at the top of this design.
Ordinary logs, selected one-frame PLY files, JSON, and PNG files remain under that root:

```text
/tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/
  task-manifest.json
  shared/
    provenance.json
    stack.log
  batches/<batch-id>/
    batch.json
    points/01-<point-id>/
      point.json
      reset.json
      reachability-declared.json
      perception/
        rgb.png
        full-cloud.ply
        cup-cloud.ply
        summary.json
      reachability-observed.json
      dynamic/
        dynamic-execute-manifest.json
        actions.json
      mujoco-viewer.png
      point-cloud-view.png
      point-cloud-view.json
  manual-captures/<capture-id>/
    rgb.png
    full-cloud.ply
    cup-cloud.ply
    summary.json
    point-cloud-view.png
    point-cloud-view.json
```

Directories are allocated exclusively. Every registered artifact has a relative path, media type,
byte size, SHA256, producing process, source session, reset epoch when applicable, and capture time.
Point manifests are finalized atomically before the batch advances.

No high-frequency rosbag or lossless trace is planned for this acceptance. If debugging requires
high-rate durable evidence, the entire task root must be migrated through the repository evidence
procedure to one `/data/work/so101-evidence/...` root; evidence may not be split silently.

At completion, the ledger and report classify retained runs, archived runs, and deletion
candidates. Nothing is deleted without explicit user authorization.

## 14. Process ownership and cleanup

The supervisor starts children in owned process groups and records their PIDs, commands, roles, and
session identity. It never kills unrelated ROS or GUI processes.

Normal standalone cleanup runs in reverse dependency order:

1. stop point-owned perception and workflow children;
2. stop Teleop if the supervisor started it;
3. stop MoveIt and scene helpers;
4. stop controller spawners/controllers and robot state publisher;
5. stop `mujoco_ros2_control` and wait for Viewer exit;
6. verify no owned process, ROS node, or task domain remains;
7. finalize cleanup evidence.

Interactive completion stops only point-owned children. Explicit environment shutdown performs the
full sequence. Shared-environment failure first pauses or holds safely, writes terminal evidence,
and then cleans up only when the safety state permits it.

## 15. Test-first implementation strategy

Implementation uses RED -> GREEN tests at each owning boundary.

### 15.1 Python and ROS contract tests

- point schema accepts the four presets and generic finite XYZ lists and rejects malformed,
  duplicate, non-finite, out-of-policy, or unknown-field input;
- import/export round trips without modifying package configuration;
- reachability derives the production target sequence and records IK, collision, joint-limit, and
  segment failures;
- reachability uses a request-local scene and performs no global mutation or execution;
- ResetWorld carries the `plastic_cup` free-joint override in the same request;
- reset verification uses the submitted point, preserves the session, and requires epoch `+1`;
- a fresh consumer subscription exists before perception publishes `/cup_pose`;
- stale RGB-D, TF, `/cup_pose`, session, epoch, scene, or plan evidence is rejected;
- a point-local failure finalizes evidence and advances to the next point;
- a shared-environment or unsupported-held-cup failure aborts or enters operator recovery;
- cancellation stops only at a safe checkpoint;
- all process groups receive ordered graceful shutdown before bounded escalation;
- artifact lookup rejects traversal, symlink, type, and manifest mismatches.

### 15.2 Teleop API and frontend tests

- `/` still renders the existing application and all prior API tests remain green;
- `/tasks` renders the separate task application;
- lease, session, command-ID, one-active-batch, old-command lockout, cancel, recovery, and shutdown
  gates are enforced;
- browser refresh restores active and completed task state;
- free-point editing, ordering, preset selection, YAML import/export, and reachability states work;
- live capture displays a matched RGB and PLY result and rejects stale input;
- Three.js viewer loads PLY, switches clouds/colors, resets view, and produces bounded PNG metadata;
- evidence browsing cannot request an arbitrary path;
- WebSocket progress does not alter the existing Teleop telemetry schema.

The web package continues to use Bun for dependency installation, build, Vitest, and Playwright.
No npm, npx, or `package-lock.json` is introduced.

### 15.3 Package and installed-runtime gates

- run focused Python and web tests first;
- run the complete affected `so101_demo_py` and `so101_teleop` suites;
- build the dependency-closed ROS package set into a fresh candidate overlay;
- source that exact overlay and prove every new executable, launch file, frontend bundle, and
  package prefix resolves from it;
- prove source, installed, and loaded `mujoco_ros2_control` version `0.1.0` and exact fork SHA;
- run `git diff --check` and read-only formatting/lint checks without broad reformatting;
- preserve unrelated user files and existing evidence.

## 16. macOS runtime acceptance

Create a dedicated experiment ledger before the first live run and register the one evidence root.
Every experiment records source commit, overlay, installed executables, fork provenance,
`ROS_DOMAIN_ID`, session ID, reset epoch, commands, exit codes, process ownership, and evidence
paths.

The qualifying batch must prove:

1. `headless=false` and a visible, freshly inspected MuJoCo Viewer;
2. one unchanged simulation session for all four preset points;
3. four atomic reset epochs increasing exactly once per executed point;
4. fresh aligned RGB, depth, CameraInfo, PLY, TF, and perception summary for each point;
5. `/cup_pose` produced only by the RGB-D perception node and consumed after subscription
   readiness;
6. declared and perceived reachability checks pass for each point;
7. each dynamic workflow reaches its complete successful state trace;
8. MoveIt planning/execution, controller feedback, joint/TCP motion, MuJoCo physical grasp,
   transport, release, stable placement, and Planning Scene detach all agree;
9. each point has fresh RGB, point-cloud, and MuJoCo Viewer images;
10. the user can perform a manual `Capture now`, inspect the interactive PLY, and save a
    point-cloud screenshot;
11. an additional non-qualifying robustness batch contains an unreachable point followed by a
    reachable point, proves `SKIPPED_UNREACHABLE`, preserves its evidence, and succeeds at the later
    point in the same healthy session;
12. final ordered cleanup leaves no task-owned process, node, or GUI.

Four successful state-machine traces alone are insufficient. The qualification result requires all
camera, point-cloud, TF, MoveIt, controller, physical, Planning Scene, visual, provenance, and
cleanup layers above.

## 17. Non-goals

- No change to RGB-D segmentation thresholds, cup geometry, frozen motion policy, place target, or
  state transition table unless a failing RED test proves an independent defect and the design is
  revisited.
- No MJCF keyframe is created for custom points.
- No fallback from perception to declared, keyframe, or simulator-truth `/cup_pose` publication.
- No multi-robot, real-hardware execute, remote ai-station qualification, or browser control of
  arbitrary ROS commands.
- No Potree conversion, LAS/LAZ pipeline, persistent custom-point database, or historical evidence
  mutation.
- No change to the old Teleop page layout or telemetry wire contract.

## 18. Completion gate

Completion requires all focused and package tests, fresh installed-runtime provenance, the four
successful macOS RESET_WORLD points, the unreachable-then-reachable continuation experiment, fresh
GUI and sensor evidence, artifact-browser verification, and clean owned-process shutdown.

The final report lists every changed file, exact commands and exit codes, batch and point results,
retained evidence, archived evidence, deletion candidates, preserved user changes, and remaining
risks. No completion, merge, or publication claim may rely only on source inspection, `DONE`, a
single screenshot, or remote-reference parity.
