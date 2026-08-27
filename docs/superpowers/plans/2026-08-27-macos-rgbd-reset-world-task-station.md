# macOS RGB-D RESET_WORLD Task Station Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one visible macOS MuJoCo task station that reuses a single environment to execute arbitrary RGB-D perception-driven cup pick-place points, exposes the workflow on a separate Teleop `/tasks` page, and retains browsable RGB, point-cloud, runtime, and failure evidence.

**Architecture:** `so101_demo_py` owns typed point input, atomic cup-position reset, sequential MoveIt reachability, RGB-D artifacts, batch state, per-point process orchestration, and the persistent stack supervisor. `so101_teleop` invokes installed owner executables through typed adapters, serves asynchronous task and artifact APIs, and renders a separate React task application with a Three.js PLY viewer. The browser never owns ROS lifecycle or task transitions.

**Tech Stack:** Python 3.12, ROS 2 Jazzy, `mujoco_ros2_control` 0.1.0, MoveIt 2 `MoveGroup` action, FastAPI/Pydantic, React 18, TypeScript, Vite, Bun, Three.js 0.184.0, Vitest, Playwright, pytest, colcon.

**Spec:** `docs/superpowers/specs/2026-08-27-macos-rgbd-reset-world-task-station-design.md`

## Global Constraints

- Execute implementation in an isolated worktree created with `superpowers:using-git-worktrees`; do not edit or clean unrelated user work.
- Register exactly one evidence root in `docs/experiments/macos-rgbd-reset-world-task-station-experiment-ledger.md`: `/tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/`.
- Use `RESET_WORLD` only for the qualifying batch, one unchanged simulation session, and reset epochs increasing by exactly one per executed point.
- Use `headless=false` for macOS live acceptance and inspect fresh MuJoCo Viewer screenshots through the project `gui-capture` skill.
- Source and prove the exact candidate overlay; source, installed metadata, and runtime must all use `mujoco_ros2_control` package version `0.1.0` at submodule SHA `5e9d67ce9fde39d35bf94cc498721abf203a0ddd`.
- Preserve the frozen dynamic policy, cup geometry, place target, state transition table, camera TFs, and perception thresholds.
- Never substitute declared positions, MJCF keyframes, or simulator truth for failed RGB-D `/cup_pose` perception.
- Point-local failures retain evidence and continue only from a verified safe state; shared-stack failures abort; an unsupported held cup enters `NEEDS_OPERATOR_RECOVERY`.
- Keep the old Teleop `/` page and current telemetry/API semantics compatible. The task application lives at `/tasks`.
- Use Bun and `bun.lock` for all Web work. Do not introduce npm, npx, CDN runtime dependencies, or `package-lock.json`.
- Do not run `ament_uncrustify --reformat`. Make formatting changes with targeted patches.
- Do not delete evidence. Final reporting must classify retained, archived, and deletion-candidate runs.

---

## File and ownership map

### `so101_demo_py`

- `src/core/task_points.py`: ROS-free immutable point-list values and mapping validation.
- `src/runtime/task_point_config.py`: strict YAML load/dump and installed preset loading.
- `config/mujoco/rgbd_task_points.yaml`: the four shipped presets.
- `src/backends/mujoco/client.py`: construct the 0.1.0 ResetWorld free-joint override.
- `src/backends/mujoco/reset.py`: verify the requested per-point pose, identity orientation, zero twist, step zero, and epoch `+1`.
- `src/application/task_reachability.py`: backend-neutral sequential target reachability state machine and result model.
- `src/ros/task_reachability.py`: MoveIt `MoveGroup` plan-only action adapter with a request-local Planning Scene diff.
- `src/cli/task_reachability.py`: installed JSON CLI used by Teleop prechecks.
- `src/cli/rgbd_point_cloud.py`: retain full cloud and RGB alongside the selected cup cloud.
- `src/ros/rgbd_cup_pose_node.py`: write synchronized RGB/full PLY/cup PLY evidence from the accepted frame.
- `src/ros/rgbd_snapshot.py` and `src/cli/rgbd_sensor_capture.py`: one-shot current sensor capture.
- `src/runtime/point_cloud_preview.py`: deterministic Pillow/NumPy diagnostic PNG when no browser is connected.
- `src/runtime/task_artifacts.py`: exclusive directories, atomic manifests, checksums, and artifact IDs.
- `src/application/task_batch.py`: point/batch statuses, continuation policy, recovery policy, and application loop.
- `src/runtime/task_batch_runtime.py`: ROS/process implementation of the application ports.
- `src/runtime/task_stack.py`: persistent stack process groups, readiness, shutdown, and environment-control request.
- `src/runtime/viewer_capture.py`: unique MuJoCo Viewer window discovery and bounded macOS screenshot capture.
- `assets/macos/list_windows.swift`: CoreGraphics window inventory scoped to the recorded MuJoCo PID.
- `src/cli/mujoco_rgbd_batch.py`: automatic and attach-to-task-station owner executable.
- `src/runtime/launch_composition.py` and `launch/so101_mujoco_task_station.launch.py`: persistent stack, camera TF, and interactive Teleop composition.
- `setup.py`, `package.xml`, and installed-provenance tests: package new executables/config/launch and runtime dependencies.

### `so101_teleop`

- `so101_teleop/backends/protocol.py`, `profile.py`, `cli_adapter.py`, and `config/backends/*.yaml`: advertise task capabilities and resolve installed task owners.
- `so101_teleop/task_gateway.py`: asynchronous owner process and batch-state gateway.
- `so101_teleop/task_artifacts.py`: manifest-only, path-safe artifact reads.
- `so101_teleop/task_service.py`: lease/session gates, single active task, recovery, capture, and old-command lockout state.
- `so101_teleop/models.py`, `api.py`, `server.py`, and `main.py`: task wire models, routes, service composition, and WebSocket stream.
- `web/src/task-app.tsx`: separate `/tasks` application shell.
- `web/src/api/task-client.ts` and `task-types.ts`: typed task API and events.
- `web/src/lib/task-yaml.ts`: browser import/export for the versioned point schema.
- `web/src/components/tasks/*`: task builder, sensor capture, PLY viewer, progress, and evidence browser.
- `web/src/main.tsx`: pathname dispatch only; the existing `App` stays the `/` component.
- `web/package.json` and `bun.lock`: exact Three.js dependency.

---

### Task 1: Register the experiment and implement strict point-list input

**Files:**
- Create: `docs/experiments/macos-rgbd-reset-world-task-station-experiment-ledger.md`
- Create: `src/so101_demo_py/src/core/task_points.py`
- Create: `src/so101_demo_py/src/runtime/task_point_config.py`
- Create: `src/so101_demo_py/config/mujoco/rgbd_task_points.yaml`
- Create: `src/so101_demo_py/test/test_task_points.py`

**Interfaces:**
- Produces: `TaskPoint`, `TaskPointList`, `parse_task_point_list(document, workspace_bounds_m)`, `load_task_point_list(path, workspace_bounds_m)`, and `dump_task_point_list(points)`.
- Consumes: `DynamicPickTemplate.workspace_bounds_m` from `src/core/dynamic_pick.py` when runtime callers validate inputs.

- [ ] **Step 1: Create the ledger before any build or runtime action**

Write `CP-001` with reviewed HEAD, branch, exact dirty paths, submodule SHA, the one evidence root, no owned processes, lifecycle `RESET_WORLD`, and the next command pointing to the Task 1 RED test. Add `EXP-001` as `PLANNED` for source-level point-schema work; do not start a simulator.

- [ ] **Step 2: Write failing schema and round-trip tests**

```python
def test_four_presets_and_custom_point_round_trip(tmp_path, workspace_bounds):
    points = load_task_point_list(PRESET_PATH, workspace_bounds)
    custom = parse_task_point_list(
        {"schema_version": 1, "points": [
            {"id": "custom_1", "label": "Custom 1",
             "cup_position_world_m": [0.01, -0.30, 0.165]}
        ]},
        workspace_bounds,
    )
    restored = parse_task_point_list(yaml.safe_load(dump_task_point_list(custom)), workspace_bounds)
    assert [point.id for point in points.points] == [
        "task_start", "cup_test_forward_5cm", "cup_test_left_5cm", "cup_test_right_5cm"
    ]
    assert restored == custom


@pytest.mark.parametrize("payload", [
    {"schema_version": 2, "points": []},
    {"schema_version": 1, "points": []},
    {"schema_version": 1, "points": [
        {"id": "bad/id", "label": "Bad", "cup_position_world_m": [0.0, 0.0, 0.0]}
    ]},
    {"schema_version": 1, "points": [
        {"id": "p", "label": "P", "cup_position_world_m": [float("nan"), 0.0, 0.0]}
    ]},
])
def test_invalid_point_lists_fail_closed(payload, workspace_bounds):
    with pytest.raises(TaskPointError):
        parse_task_point_list(payload, workspace_bounds)
```

- [ ] **Step 3: Run the RED tests**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q src/so101_demo_py/test/test_task_points.py
```

Expected: collection fails because `so101_demo.core.task_points` does not exist.

- [ ] **Step 4: Implement the immutable point values and strict YAML boundary**

Use these public definitions:

```python
_POINT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class TaskPointError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TaskPoint:
    id: str
    label: str
    cup_position_world_m: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class TaskPointList:
    schema_version: int
    points: tuple[TaskPoint, ...]


def parse_task_point_list(
    document: Mapping[str, object],
    workspace_bounds_m: tuple[float, float, float, float, float, float],
) -> TaskPointList:
    # Require the exact top-level and point fields, schema_version == 1,
    # non-empty unique IDs, finite XYZ, and lower <= XYZ <= upper.
```

`dump_task_point_list` must use `yaml.safe_dump(..., sort_keys=False)` and must not write a file.
`load_task_point_list` reads one explicit path and wraps YAML/OSError failures in `TaskPointError`.

- [ ] **Step 5: Run GREEN and package-resource tests**

```bash
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q src/so101_demo_py/test/test_task_points.py src/so101_demo_py/test/test_asset_closure.py
```

Expected: all selected tests pass and the config is included by `installed_resources()`.

- [ ] **Step 6: Update the ledger and commit**

Record the RED command, GREEN command, exit codes, and `EXP-001` conclusion. Commit only Task 1 files:

```bash
git add docs/experiments/macos-rgbd-reset-world-task-station-experiment-ledger.md src/so101_demo_py/config/mujoco/rgbd_task_points.yaml src/so101_demo_py/src/core/task_points.py src/so101_demo_py/src/runtime/task_point_config.py src/so101_demo_py/test/test_task_points.py
git commit -m "feat: add RGB-D task point lists"
```

### Task 2: Add atomic arbitrary cup-position RESET_WORLD

**Files:**
- Modify: `src/so101_demo_py/src/backends/mujoco/client.py`
- Modify: `src/so101_demo_py/src/backends/mujoco/reset.py`
- Modify: `src/so101_demo_py/src/backends/mujoco/teleop_runtime.py`
- Modify: `src/so101_demo_py/src/cli/teleop_reset.py`
- Modify: `src/so101_demo_py/test/test_mujoco_reset_client.py`
- Modify: `src/so101_demo_py/test/test_teleop_reset_cli.py`

**Interfaces:**
- Produces: `FreeJointResetOverride`, `MujocoRosClient.reset_world(keyframe, overrides)`, and `transactional_reset(..., expected_object_position, free_joint_overrides)`.
- Consumes: `mujoco_ros2_control_msgs.msg.FreeJointState` and 0.1.0 `ResetWorld.Request.state_overrides`.

- [ ] **Step 1: Write the ResetWorld wire-contract RED test**

```python
def test_reset_world_sends_plastic_cup_override():
    services = fake_services()
    client = MujocoRosClient(services.node, services.joint_node)
    override = FreeJointResetOverride(
        name="plastic_cup",
        position_world_m=(-0.03, -0.28, 0.165),
        orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
    )
    assert client.reset_world("task_start", (override,)) is True
    request = services.reset_client.request
    assert request.keyframe == "task_start"
    assert len(request.state_overrides.free_joints) == 1
    assert request.state_overrides.free_joints[0].name == "plastic_cup"
    assert request.state_overrides.free_joints[0].pose.header.frame_id == ""
    assert request.state_overrides.free_joints[0].pose.pose.position.x == -0.03
    assert request.state_overrides.free_joints[0].pose.pose.orientation.w == 1.0
```

Add tests that reject duplicate names, non-finite poses, non-unit quaternions, and prove
`MujocoResetClient` checks the per-call expected position, identity orientation, zero linear and
angular velocity, step zero, unchanged session, and epoch `old + 1`.

- [ ] **Step 2: Run the reset RED tests**

```bash
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q src/so101_demo_py/test/test_mujoco_reset_client.py src/so101_demo_py/test/test_teleop_reset_cli.py
```

Expected: failures show that `reset_world` does not accept overrides and the CLI has no cup-position arguments.

- [ ] **Step 3: Implement the neutral override and 0.1.0 message conversion**

```python
@dataclass(frozen=True, slots=True)
class FreeJointResetOverride:
    name: str
    position_world_m: tuple[float, float, float]
    orientation_xyzw: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)


def reset_world(
    self,
    keyframe: str,
    free_joint_overrides: tuple[FreeJointResetOverride, ...] = (),
) -> bool:
    request = ResetWorld.Request()
    request.keyframe = keyframe
    request.state_overrides.free_joints = [
        _free_joint_message(value) for value in free_joint_overrides
    ]
    return bool(self._call(self._reset, request, "reset").success)
```

`_free_joint_message` sets an empty frame for world, the full pose, and an explicit zero twist.
Update `MujocoResetClient.reset(keyframe, free_joint_overrides=())` to pass the overrides while its
constructor retains the expected state used for verification.

- [ ] **Step 4: Expose the arbitrary point through `teleop_reset` without changing its default**

Add `--cup-position-world-m X Y Z`. Omission keeps `(0.02, -0.28, 0.165)`. Presence creates exactly
one `plastic_cup` override and makes the requested value the verifier expectation. Include
`requested_object_position_world_m` in JSON evidence.

- [ ] **Step 5: Run reset GREEN and regression tests**

```bash
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q src/so101_demo_py/test/test_mujoco_reset_client.py src/so101_demo_py/test/test_teleop_reset_cli.py src/so101_demo_py/test/test_transactional_reset.py src/so101_demo_py/test/test_teleop_owner.py
```

Expected: all selected reset and legacy-default tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/so101_demo_py/src/backends/mujoco/client.py src/so101_demo_py/src/backends/mujoco/reset.py src/so101_demo_py/src/backends/mujoco/teleop_runtime.py src/so101_demo_py/src/cli/teleop_reset.py src/so101_demo_py/test/test_mujoco_reset_client.py src/so101_demo_py/test/test_teleop_reset_cli.py
git commit -m "feat: reset MuJoCo cup to arbitrary points"
```

### Task 3: Implement backend-neutral sequential TCP reachability

**Files:**
- Create: `src/so101_demo_py/src/application/task_reachability.py`
- Create: `src/so101_demo_py/test/test_task_reachability.py`
- Modify: `src/so101_demo_py/src/core/dynamic_pick.py` only if a public ordered motion-state tuple is needed.

**Interfaces:**
- Produces: `ReachabilityStatus`, `ReachabilitySegment`, `ReachabilityReport`, `ReachabilityPlannerPort`, and `check_task_reachability(...)`.
- Consumes: `TaskPoint`, `CupPoseSample`, `DynamicPickTemplate`, `resolve_motion_targets`, and `JointStateEvidence`.

- [ ] **Step 1: Write RED tests for full-sequence planning and first-failure evidence**

```python
def test_reachability_plans_dynamic_sequence_from_each_terminal_state(template, start_state):
    planner = RecordingPlanner()
    report = check_task_reachability(point(), template, start_state, planner)
    assert report.status is ReachabilityStatus.REACHABLE
    assert [segment.state for segment in report.segments] == [
        State.MOVE_ABOVE_OBJECT, State.DESCEND, State.MICRO_LIFT, State.LIFT,
        State.MOVE_ABOVE_PLACE, State.DESCEND_TO_PLACE, State.RETREAT,
    ]
    assert planner.starts[1] == planner.terminals[0]


def test_reachability_stops_at_first_failed_segment(template, start_state):
    planner = RecordingPlanner(fail_state=State.DESCEND)
    report = check_task_reachability(point(), template, start_state, planner)
    assert report.status is ReachabilityStatus.UNREACHABLE
    assert report.first_failure_code == "MOVEIT_PLAN_FAILED"
    assert report.segments[-1].state is State.DESCEND
```

Add `UNKNOWN` cases for stale scene/joints and planner unavailability. Prove no execution method is
part of `ReachabilityPlannerPort`.

- [ ] **Step 2: Run the reachability RED test**

```bash
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q src/so101_demo_py/test/test_task_reachability.py
```

Expected: collection fails because `task_reachability` does not exist.

- [ ] **Step 3: Implement exact immutable results and the sequential algorithm**

```python
class ReachabilityStatus(StrEnum):
    REACHABLE = "REACHABLE"
    UNREACHABLE = "UNREACHABLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class SegmentPlanReceipt:
    accepted: bool
    terminal_state: JointStateEvidence | None
    moveit_error_code: int | None
    failure_code: str | None
    collision_pairs: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class ReachabilitySegment:
    state: State
    target: PoseEvidence
    accepted: bool
    moveit_error_code: int | None
    failure_code: str | None
    collision_pairs: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class ReachabilityReport:
    point_id: str
    status: ReachabilityStatus
    segments: tuple[ReachabilitySegment, ...]
    first_failure_code: str | None
    scene_revision: int | None


class ReachabilityPlannerPort(Protocol):
    def plan(
        self,
        state: State,
        target: PoseEvidence,
        start: JointStateEvidence,
        cup_pose_world: PoseEvidence,
        timeout_s: float,
    ) -> SegmentPlanReceipt: ...
```

`check_task_reachability` builds `CupPoseSample` from the declared point, calls
`resolve_motion_targets`, runs the seven ordered states, passes each accepted terminal state into
the next segment, and returns the first failure without attempting later segments.

- [ ] **Step 4: Run GREEN and dynamic-target regressions**

```bash
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q src/so101_demo_py/test/test_task_reachability.py src/so101_demo_py/test/test_dynamic_pick.py src/so101_demo_py/test/test_dynamic_plan_only.py
```

- [ ] **Step 5: Commit**

```bash
git add src/so101_demo_py/src/application/task_reachability.py src/so101_demo_py/src/core/dynamic_pick.py src/so101_demo_py/test/test_task_reachability.py
git commit -m "feat: add sequential pick reachability checks"
```

### Task 4: Add the MoveIt plan-only scene-diff adapter and CLI

**Files:**
- Create: `src/so101_demo_py/src/ros/task_reachability.py`
- Create: `src/so101_demo_py/src/cli/task_reachability.py`
- Create: `src/so101_demo_py/test/test_task_reachability_ros.py`
- Create: `src/so101_demo_py/test/test_task_reachability_cli.py`
- Modify: `src/so101_demo_py/src/ros/dynamic_runtime.py`
- Modify: `src/so101_demo_py/src/ros/dynamic_mujoco_execution.py`
- Modify: `src/so101_demo_py/test/test_dynamic_execute.py`
- Modify: `src/so101_demo_py/setup.py`
- Modify: `src/so101_demo_py/test/test_installed_provenance.py`

**Interfaces:**
- Produces: `RosMoveGroupReachabilityPlanner`, `make_move_group_goal(...)`, and installed executable `task_reachability`.
- Consumes: Task 3 `ReachabilityPlannerPort`; MoveIt `MoveGroup` action at `/move_action`.

- [ ] **Step 1: Write a RED wire-message test**

```python
def test_goal_is_plan_only_and_contains_request_local_cup_scene():
    goal = make_move_group_goal(
        state=State.MOVE_ABOVE_OBJECT,
        target=target_pose(),
        start=start_joints(),
        cup_pose_world=cup_pose(),
        template=template(),
    )
    assert goal.planning_options.plan_only is True
    assert goal.planning_options.replan is False
    assert goal.planning_options.planning_scene_diff.is_diff is True
    objects = goal.planning_options.planning_scene_diff.world.collision_objects
    assert [item.id for item in objects] == ["plastic_cup"]
    assert goal.request.start_state.joint_state.position == list(start_joints().positions_rad)
```

Add tests that accepted results return the final trajectory point, rejected goals retain the
MoveIt error code, timeout returns `UNKNOWN`, and no execute-trajectory action is created.
Add a dynamic-execute test that freezes a perceived pose, fails its sequential reachability report,
records `DYNAMIC_TARGET_UNREACHABLE`, and proves zero arm/gripper execution and zero workflow-state
actions.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q src/so101_demo_py/test/test_task_reachability_ros.py src/so101_demo_py/test/test_task_reachability_cli.py
```

- [ ] **Step 3: Implement the plan-only `MoveGroup` action adapter**

Create an `ActionClient(node, MoveGroup, "/move_action")`. Build the same pose constraints,
tolerances, scaling, planning group, and TCP link as production. Set `planning_options.plan_only`
to true and place the canonical cup collision object in `planning_scene_diff`; never call
`/execute_trajectory`, `/apply_planning_scene`, or controller actions. Convert the final trajectory
point into `JointStateEvidence` for the next segment.

- [ ] **Step 4: Implement the installed JSON CLI**

The parser requires `--points`, `--policy`, `--session-id`, and `--evidence-file`; it accepts either
`--point-id` or all points. Output this stable envelope on the final stdout line:

```json
{"status":"SUCCEEDED","reports":[{"point_id":"task_start","status":"REACHABLE","segments":[]}]}
```

Return 0 when every report is `REACHABLE`, 2 when at least one is `UNREACHABLE`, and 1 for
`UNKNOWN` or infrastructure failure. Write the same envelope atomically to the evidence file.

Integrate the same planner inside MuJoCo dynamic execute after fresh `/cup_pose` freeze,
perception-versus-MuJoCo validation, and Planning Scene synchronization, but before building or
running dynamic actions. Write `reachability-observed.json` in the dynamic evidence root. A
non-`REACHABLE` result exits before motion with `DYNAMIC_TARGET_UNREACHABLE` or
`DYNAMIC_TARGET_REACHABILITY_UNKNOWN`.

- [ ] **Step 5: Run GREEN and installed-executable expectations**

```bash
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q src/so101_demo_py/test/test_task_reachability_ros.py src/so101_demo_py/test/test_task_reachability_cli.py src/so101_demo_py/test/test_dynamic_execute.py src/so101_demo_py/test/test_installed_provenance.py
```

- [ ] **Step 6: Commit**

```bash
git add src/so101_demo_py/setup.py src/so101_demo_py/src/cli/task_reachability.py src/so101_demo_py/src/ros/dynamic_mujoco_execution.py src/so101_demo_py/src/ros/dynamic_runtime.py src/so101_demo_py/src/ros/task_reachability.py src/so101_demo_py/test/test_dynamic_execute.py src/so101_demo_py/test/test_installed_provenance.py src/so101_demo_py/test/test_task_reachability_cli.py src/so101_demo_py/test/test_task_reachability_ros.py
git commit -m "feat: expose MoveIt task reachability"
```

### Task 5: Produce synchronized RGB, full-cloud, and cup-cloud artifacts

**Files:**
- Modify: `src/so101_demo_py/src/cli/rgbd_point_cloud.py`
- Modify: `src/so101_demo_py/src/ros/rgbd_cup_pose_node.py`
- Modify: `src/so101_demo_py/src/cli/rgbd_cup_pose.py`
- Create: `src/so101_demo_py/src/ros/rgbd_snapshot.py`
- Create: `src/so101_demo_py/src/cli/rgbd_sensor_capture.py`
- Create: `src/so101_demo_py/src/runtime/point_cloud_preview.py`
- Modify: `src/so101_demo_py/package.xml`
- Modify: `src/so101_demo_py/setup.py`
- Modify: `src/so101_demo_py/test/test_rgbd_point_cloud.py`
- Modify: `src/so101_demo_py/test/test_rgbd_cup_pose.py`
- Create: `src/so101_demo_py/test/test_rgbd_sensor_capture.py`
- Create: `src/so101_demo_py/test/test_point_cloud_preview.py`

**Interfaces:**
- Produces: `RgbdPointCloudFrame`, `RgbdSnapshotResult`, `write_rgb_png`, `write_full_point_cloud`, `render_point_cloud_preview`, `capture_rgbd_snapshot`, and executable `rgbd_sensor_capture`.
- Consumes: the existing exact-stamp `AlignedRgbdBuffer` and production segmentation/fitting functions.

- [ ] **Step 1: Write RED tests proving one source frame owns every artifact**

```python
def test_frame_retains_rgb_full_and_cup_cloud(aligned_messages):
    frame = build_cup_point_cloud(*aligned_messages, **OPTIONS)
    assert frame.stamp_ns == message_stamp_ns(aligned_messages[0])
    assert frame.rgb8.shape == (frame.image_height, frame.image_width, 3)
    assert frame.full_points_xyz.shape == frame.full_colors_rgb.shape
    assert frame.cup_points_xyz.shape == frame.cup_colors_rgb.shape
    assert frame.full_point_count > frame.cup_point_count > 0


def test_snapshot_writes_checksummed_artifacts_from_same_stamp(tmp_path, aligned_messages):
    result = capture_rgbd_snapshot(FakeSource(aligned_messages), FakeTf(), tmp_path)
    assert result.summary["source_stamp_ns"] == result.frame.stamp_ns
    assert set(result.artifacts) == {
        "rgb", "full_cloud", "cup_cloud", "point_cloud_preview", "summary"
    }
```

Add tests for mismatched stamps, missing exact TF, invalid depth, PNG magic, PLY headers, and fatal
write errors before success output.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q src/so101_demo_py/test/test_rgbd_point_cloud.py src/so101_demo_py/test/test_rgbd_cup_pose.py src/so101_demo_py/test/test_rgbd_sensor_capture.py src/so101_demo_py/test/test_point_cloud_preview.py
```

- [ ] **Step 3: Refactor the in-memory frame without a file round-trip**

Use one immutable result with explicit arrays:

```python
@dataclass(frozen=True, slots=True)
class RgbdPointCloudFrame:
    frame_id: str
    stamp_ns: int
    image_width: int
    image_height: int
    intrinsics_fx_fy_cx_cy: tuple[float, float, float, float]
    rgb8: np.ndarray
    full_points_xyz: np.ndarray
    full_colors_rgb: np.ndarray
    cup_points_xyz: np.ndarray
    cup_colors_rgb: np.ndarray
    color_candidate_point_count: int


@dataclass(frozen=True, slots=True)
class RgbdSnapshotResult:
    frame: RgbdPointCloudFrame
    summary: Mapping[str, object]
    artifacts: Mapping[str, Path]
```

Keep compatibility properties `points_xyz`, `colors_rgb`, `full_point_count`, and
`cup_point_count` so the production pose estimator does not fork.

- [ ] **Step 4: Add output paths to production perception and the one-shot CLI**

Extend `RgbdCupPoseOptions` with optional absolute `output_rgb` and `output_full_ply`. The accepted
frame writes RGB, full PLY, cup PLY, and summary before first `/cup_pose` publication. The one-shot
CLI requires an exclusive `--output-directory` and exits after one fresh synchronized frame.
`render_point_cloud_preview` applies a fixed documented camera matrix, z-buffer, point size, and
background to the full or cup XYZ/RGB arrays and writes a deterministic PNG plus view metadata.
This guarantees an automatic point-cloud image even when `/tasks` is not open; the Three.js page
may add separate operator-view screenshots without replacing it.

- [ ] **Step 5: Run GREEN**

```bash
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q src/so101_demo_py/test/test_rgbd_point_cloud.py src/so101_demo_py/test/test_rgbd_cup_pose.py src/so101_demo_py/test/test_rgbd_sensor_capture.py src/so101_demo_py/test/test_point_cloud_preview.py
```

- [ ] **Step 6: Commit**

```bash
git add src/so101_demo_py/package.xml src/so101_demo_py/setup.py src/so101_demo_py/src/cli/rgbd_cup_pose.py src/so101_demo_py/src/cli/rgbd_point_cloud.py src/so101_demo_py/src/cli/rgbd_sensor_capture.py src/so101_demo_py/src/ros/rgbd_cup_pose_node.py src/so101_demo_py/src/ros/rgbd_snapshot.py src/so101_demo_py/src/runtime/point_cloud_preview.py src/so101_demo_py/test/test_point_cloud_preview.py src/so101_demo_py/test/test_rgbd_cup_pose.py src/so101_demo_py/test/test_rgbd_point_cloud.py src/so101_demo_py/test/test_rgbd_sensor_capture.py
git commit -m "feat: retain synchronized RGB-D artifacts"
```

### Task 6: Implement exclusive manifests and path-safe artifact registration

**Files:**
- Create: `src/so101_demo_py/src/runtime/task_artifacts.py`
- Create: `src/so101_demo_py/test/test_task_artifacts.py`

**Interfaces:**
- Produces: `ArtifactRecord`, `TaskArtifactRegistry`, `atomic_json`, `register_file`, `allocate_batch`, and `allocate_point`.
- Consumes: the single caller-provided evidence root; it never invents a second root.

- [ ] **Step 1: Write RED tests for immutability, checksums, and path escape**

```python
def test_registry_allocates_exclusive_batch_and_registers_checksum(tmp_path):
    registry = TaskArtifactRegistry(tmp_path)
    batch = registry.allocate_batch("batch-1")
    point = registry.allocate_point(batch, 1, "task_start")
    payload = point / "point.json"
    payload.write_text('{"status":"RUNNING"}\n')
    artifact = registry.register_file("point-input", payload, "application/json", "sim-a", 1)
    assert artifact.relative_path == "batches/batch-1/points/01-task_start/point.json"
    assert artifact.sha256 == hashlib.sha256(payload.read_bytes()).hexdigest()
    with pytest.raises(ArtifactRegistryError):
        registry.allocate_batch("batch-1")


def test_registry_rejects_symlink_escape(tmp_path):
    registry = TaskArtifactRegistry(tmp_path / "root")
    outside = tmp_path / "outside"; outside.write_text("secret")
    link = registry.root / "escape"; link.symlink_to(outside)
    with pytest.raises(ArtifactRegistryError):
        registry.register_file("escape", link, "text/plain", "sim-a", 1)
```

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q src/so101_demo_py/test/test_task_artifacts.py
```

- [ ] **Step 3: Implement atomic writes and opaque artifact IDs**

`atomic_json` writes a same-directory temporary file, `fsync`s it, then uses `os.replace`.
`register_file` requires a regular non-symlink file under `root.resolve()`, computes size and SHA256,
and returns `artifact_id = sha256(f"{relative_path}\0{sha256}")[:24]`. Store only relative paths in
manifests.

Use this immutable public value:

```python
@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    artifact_id: str
    relative_path: str
    media_type: str
    byte_size: int
    sha256: str
    producing_process: str
    simulation_session_id: str
    reset_epoch: int | None
    captured_at: str
```

- [ ] **Step 4: Run GREEN and commit**

```bash
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q src/so101_demo_py/test/test_task_artifacts.py
git add src/so101_demo_py/src/runtime/task_artifacts.py src/so101_demo_py/test/test_task_artifacts.py
git commit -m "feat: add task evidence registry"
```

### Task 7: Implement the batch application loop and continuation policy

**Files:**
- Create: `src/so101_demo_py/src/application/task_batch.py`
- Create: `src/so101_demo_py/test/test_task_batch.py`

**Interfaces:**
- Produces: `BatchStatus`, `PointStatus`, `BatchRequest`, `BatchResult`, `BatchRuntimePort`, `run_task_batch`.
- Consumes: Task 1 points, Task 3 reachability reports, Task 6 registry, and dynamic workflow manifests.

- [ ] **Step 1: Write RED tests for success, local continuation, fatal abort, and held-cup recovery**

```python
def test_point_failure_is_finalized_and_later_point_runs(registry):
    runtime = FakeRuntime(outcomes={"first": LocalPointFailure("PERCEPTION_TIMEOUT")})
    result = run_task_batch(request("first", "second"), runtime, registry, events=[])
    assert [point.status for point in result.points] == [PointStatus.FAILED, PointStatus.SUCCEEDED]
    assert runtime.started_points == ["first", "second"]
    assert result.status is BatchStatus.FAILED


def test_shared_failure_aborts_remaining_points(registry):
    runtime = FakeRuntime(outcomes={"first": SharedStackFailure("SESSION_MISMATCH")})
    result = run_task_batch(request("first", "second"), runtime, registry, events=[])
    assert [point.id for point in result.points] == ["first"]
    assert result.status is BatchStatus.FAILED


def test_unsupported_held_cup_requires_operator_recovery(registry):
    runtime = FakeRuntime(outcomes={"first": HeldCupFailure("PHYSICAL_GRASP_UNSUPPORTED")})
    result = run_task_batch(request("first", "second"), runtime, registry, events=[])
    assert result.status is BatchStatus.NEEDS_OPERATOR_RECOVERY
    assert runtime.reset_calls == []
```

Also test `SKIPPED_UNREACHABLE`, cancel-at-safe-checkpoint, monotonic epochs, point cleanup ordering,
manifest finalization before advancing, and emitted progress sequence.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q src/so101_demo_py/test/test_task_batch.py
```

- [ ] **Step 3: Implement the application port and first-failure state machine**

```python
class BatchRuntimePort(Protocol):
    def check_declared(self, point: TaskPoint) -> ReachabilityReport: ...
    def reset_point(self, point: TaskPoint) -> ResetPointReceipt: ...
    def start_consumer(self, point_root: Path, epoch: int) -> ManagedChild: ...
    def wait_consumer_subscription(self, child: ManagedChild, timeout_s: float) -> None: ...
    def start_perception(self, point_root: Path) -> ManagedChild: ...
    def wait_point_result(self, point: TaskPoint, epoch: int, point_root: Path) -> PointExecutionReceipt: ...
    def capture_terminal(self, point_root: Path, reason: str) -> tuple[Path, ...]: ...
    def safe_to_continue(self, epoch: int) -> SafetyReceipt: ...
    def stop_point_children(self) -> None: ...
    def pause_world(self) -> None: ...
```

Define the referenced values and failure classes in the same module so runtime adapters share one
contract:

```python
class PointStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED_UNREACHABLE = "SKIPPED_UNREACHABLE"


class BatchStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    NEEDS_OPERATOR_RECOVERY = "NEEDS_OPERATOR_RECOVERY"


@dataclass(frozen=True, slots=True)
class ManagedChild:
    role: str
    pid: int
    pgid: int


@dataclass(frozen=True, slots=True)
class ResetPointReceipt:
    old_epoch: int
    new_epoch: int
    simulation_session_id: str
    evidence_file: Path


@dataclass(frozen=True, slots=True)
class SafetyReceipt:
    safe_to_reset: bool
    unsupported_held_cup: bool
    failure_code: str | None


@dataclass(frozen=True, slots=True)
class PointExecutionReceipt:
    succeeded: bool
    failure_code: str | None
    workflow_manifest: Path | None
    safe_state: SafetyReceipt


class LocalPointFailure(RuntimeError):
    pass


class SharedStackFailure(RuntimeError):
    pass


class HeldCupFailure(RuntimeError):
    pass
```

`BatchRequest` carries `batch_id`, `simulation_session_id`, `points`, and `evidence_root`.
`BatchResult` carries `batch_id`, terminal `status`, immutable point results, first shared failure,
and the final manifest path.

`run_task_batch` checks declared reachability, skips unreachable points without reset, performs one
reset for each executed point, requires `new_epoch == prior_epoch + 1`, always finalizes and cleans
point children in `finally`, and advances only after `safe_to_continue` passes.
Call `capture_terminal` for successful and failed points before manifest finalization; a missing
required RGB/PLY/preview/Viewer image makes that point fail rather than silently succeeding.

- [ ] **Step 4: Run GREEN and commit**

```bash
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q src/so101_demo_py/test/test_task_batch.py
git add src/so101_demo_py/src/application/task_batch.py src/so101_demo_py/test/test_task_batch.py
git commit -m "feat: add reset-world RGB-D batch loop"
```

### Task 8: Implement ROS/process runtime, persistent stack, and public batch CLI

**Files:**
- Create: `src/so101_demo_py/src/runtime/task_batch_runtime.py`
- Create: `src/so101_demo_py/src/runtime/task_stack.py`
- Create: `src/so101_demo_py/src/runtime/viewer_capture.py`
- Create: `src/so101_demo_py/assets/macos/list_windows.swift`
- Create: `src/so101_demo_py/src/cli/mujoco_rgbd_batch.py`
- Create: `src/so101_demo_py/launch/so101_mujoco_task_station.launch.py`
- Modify: `src/so101_demo_py/src/runtime/launch_composition.py`
- Modify: `src/so101_demo_py/setup.py`
- Modify: `src/so101_demo_py/test/test_installed_provenance.py`
- Create: `src/so101_demo_py/test/test_task_batch_runtime.py`
- Create: `src/so101_demo_py/test/test_task_stack.py`
- Create: `src/so101_demo_py/test/test_viewer_capture.py`
- Create: `src/so101_demo_py/test/test_mujoco_rgbd_batch_cli.py`
- Create: `src/so101_demo_py/test/test_task_station_launch.py`

**Interfaces:**
- Produces: `RosTaskBatchRuntime`, `PersistentTaskStack`, `MacViewerCapture`, executable `so101_mujoco_rgbd_batch`, and launch `so101_mujoco_task_station.launch.py`.
- Consumes: Task 7 `BatchRuntimePort`, existing camera TF helpers, `dynamic_cup_pick_place`, `rgbd_cup_pose`, `teleop_reset`, `scene_setup`, and lifecycle resume/pause services.

- [ ] **Step 1: Write RED process-order and command tests**

```python
def test_runtime_waits_for_consumer_before_starting_perception(fake_processes):
    runtime = RosTaskBatchRuntime(fake_processes, fake_ros_graph())
    consumer = runtime.start_consumer(ROOT, epoch=3)
    runtime.wait_consumer_subscription(consumer, 5.0)
    runtime.start_perception(ROOT)
    assert fake_processes.roles == ["dynamic-consumer", "rgbd-perception"]


def test_stack_shutdown_is_reverse_dependency_order(fake_popen):
    stack = PersistentTaskStack(fake_popen)
    stack.start(config())
    stack.shutdown()
    assert fake_popen.signals == [
        ("teleop", signal.SIGINT), ("move-group", signal.SIGINT),
        ("controllers", signal.SIGINT), ("robot-state", signal.SIGINT),
        ("mujoco", signal.SIGINT),
    ]


def test_viewer_capture_requires_one_mujoco_window(fake_window_backend, tmp_path):
    capture = MacViewerCapture(fake_window_backend, fake_screencapture)
    result = capture.capture(tmp_path / "mujoco-viewer.png")
    assert result.path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert result.window_title == "MuJoCo"
```

Add tests for same session, exact expected epoch arguments, point-specific evidence paths,
`headless=false`, Darwin `sys.executable` ROS invocation, DYLD preservation, first-terminal-status,
owned PGIDs only, bounded SIGINT/SIGTERM escalation, and CLI nonzero when any point fails.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q src/so101_demo_py/test/test_task_batch_runtime.py src/so101_demo_py/test/test_task_stack.py src/so101_demo_py/test/test_viewer_capture.py src/so101_demo_py/test/test_mujoco_rgbd_batch_cli.py src/so101_demo_py/test/test_task_station_launch.py
```

- [ ] **Step 3: Implement the per-point runtime commands**

Build argument arrays without `shell=True`:

```python
consumer_argv = ros2_command(
    "run", "so101_demo_py", "dynamic_cup_pick_place",
    "--backend", "mujoco", "--mode", "execute", "--execute",
    "--session-id", session_id, "--expected-reset-epoch", str(epoch),
    "--evidence-root", str(point_root / "dynamic"),
    "--scene-source", "observe_only",
)
perception_argv = ros2_command(
    "run", "so101_demo_py", "rgbd_cup_pose",
    "--output-ply", str(point_root / "perception/cup-cloud.ply"),
    "--output-full-ply", str(point_root / "perception/full-cloud.ply"),
    "--output-rgb", str(point_root / "perception/rgb.png"),
    "--evidence-json", str(point_root / "perception/summary.json"),
)
```

Poll the ROS graph until node `so101_dynamic_cup_pick_place` advertises a `/cup_pose` subscription.
After reset scene sync, call the existing lifecycle resume boundary before either child starts.
`MacViewerCapture` invokes `/usr/bin/swift` on the package-installed
`assets/macos/list_windows.swift`; that helper uses CoreGraphics to emit JSON only for onscreen
windows owned by the recorded MuJoCo PID. The Python boundary accepts exactly one matching window
and invokes
`/usr/sbin/screencapture -x -l <CGWindowID> <absolute-output>`. It rejects zero/ambiguous windows,
session/process mismatches, non-PNG output, and capture timestamps older than the point terminal
event. Preserve the error as screenshot evidence; never capture the entire desktop as fallback.

- [ ] **Step 4: Implement the persistent stack and interactive launch**

Refactor a public persistent stack composition that includes the base MuJoCo stack and the two
camera static TF nodes but no perception or dynamic workflow. Interactive composition adds Teleop
with `SO101_TASK_EVIDENCE_ROOT` and a local supervisor control endpoint. The automatic CLI owns the
stack, while `--attach-existing-stack` requires an explicit session and never shuts down the parent.

- [ ] **Step 5: Run GREEN and existing launch regressions**

```bash
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q src/so101_demo_py/test/test_task_batch_runtime.py src/so101_demo_py/test/test_task_stack.py src/so101_demo_py/test/test_viewer_capture.py src/so101_demo_py/test/test_mujoco_rgbd_batch_cli.py src/so101_demo_py/test/test_task_station_launch.py src/so101_demo_py/test/test_launch_composition.py src/so101_demo_py/test/test_perception_pick_place_launch.py src/so101_demo_py/test/test_installed_provenance.py
```

- [ ] **Step 6: Commit**

```bash
git add src/so101_demo_py/assets/macos/list_windows.swift src/so101_demo_py/launch/so101_mujoco_task_station.launch.py src/so101_demo_py/setup.py src/so101_demo_py/src/cli/mujoco_rgbd_batch.py src/so101_demo_py/src/runtime/launch_composition.py src/so101_demo_py/src/runtime/task_batch_runtime.py src/so101_demo_py/src/runtime/task_stack.py src/so101_demo_py/src/runtime/viewer_capture.py src/so101_demo_py/test/test_installed_provenance.py src/so101_demo_py/test/test_mujoco_rgbd_batch_cli.py src/so101_demo_py/test/test_task_batch_runtime.py src/so101_demo_py/test/test_task_stack.py src/so101_demo_py/test/test_task_station_launch.py src/so101_demo_py/test/test_viewer_capture.py
git commit -m "feat: add persistent MuJoCo RGB-D task runtime"
```

### Task 9: Extend Teleop backend profiles and add an asynchronous task owner

**Files:**
- Modify: `src/so101_teleop/so101_teleop/backends/protocol.py`
- Modify: `src/so101_teleop/so101_teleop/backends/profile.py`
- Modify: `src/so101_teleop/so101_teleop/backends/cli_adapter.py`
- Modify: `src/so101_teleop/config/backends/gazebo_cpp.yaml`
- Modify: `src/so101_teleop/config/backends/gazebo_py.yaml`
- Modify: `src/so101_teleop/config/backends/mujoco_py.yaml`
- Create: `src/so101_teleop/so101_teleop/task_gateway.py`
- Create: `src/so101_teleop/test/teleop/test_task_gateway.py`
- Modify: `src/so101_teleop/test/backends/test_profiles.py`
- Modify: `src/so101_teleop/test/backends/test_mujoco_profile.py`
- Modify: `src/so101_teleop/test/teleop/test_backend_capabilities.py`

**Interfaces:**
- Produces: new capability flags, backend operations, `TaskOwnerRequest`, and `CliTaskGateway`.
- Consumes: installed `so101_mujoco_rgbd_batch`, `task_reachability`, and `rgbd_sensor_capture` executables.

- [ ] **Step 1: Write profile and process RED tests**

```python
def test_mujoco_profile_exposes_only_installed_task_owners(profile):
    assert profile.capabilities.task_batch is True
    assert profile.capabilities.task_reachability is True
    assert profile.capabilities.sensor_capture is True
    assert profile.operations[BackendOperation.TASK_BATCH].executable == "so101_mujoco_rgbd_batch"
    assert profile.operations[BackendOperation.TASK_REACHABILITY].executable == "task_reachability"


def test_task_gateway_starts_one_owned_process_group(fake_popen, profile):
    gateway = CliTaskGateway(profile, popen=fake_popen)
    handle = gateway.start_batch(TaskOwnerRequest("sim-a", POINTS, ROOT))
    assert handle.run_id
    assert fake_popen.calls[0].start_new_session is True
    with pytest.raises(TaskGatewayError, match="TASK_BATCH_ACTIVE"):
        gateway.start_batch(TaskOwnerRequest("sim-a", POINTS, ROOT))
```

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src/so101_teleop python3 -m pytest -q src/so101_teleop/test/backends/test_profiles.py src/so101_teleop/test/backends/test_mujoco_profile.py src/so101_teleop/test/teleop/test_backend_capabilities.py src/so101_teleop/test/teleop/test_task_gateway.py
```

- [ ] **Step 3: Add exact capability and operation fields**

Add `task_batch`, `task_reachability`, `sensor_capture`, and `task_environment_shutdown` booleans to
`BackendCapabilities`. Add matching `BackendOperation` enum values. Set all four false for Gazebo
profiles. In `mujoco_py.yaml`, set the first three true and environment shutdown true only for the
task-station supervisor operation.

- [ ] **Step 4: Implement non-shell asynchronous process ownership**

`CliTaskGateway.start_batch` resolves the installed executable through the profile, writes the
submitted YAML into the exclusive batch input directory, and starts one process group with
`subprocess.Popen(..., shell=False, start_new_session=True)`. `status` reads the atomic manifest;
`cancel` signals only that PGID and waits through bounded SIGINT/SIGTERM stages.

Use these task-owner values:

```python
@dataclass(frozen=True, slots=True)
class TaskOwnerRequest:
    simulation_session_id: str
    points_yaml: str
    evidence_root: Path


@dataclass(frozen=True, slots=True)
class TaskHandle:
    run_id: str
    pid: int
    pgid: int
    manifest_path: Path


class TaskGatewayError(RuntimeError):
    pass
```

`CliTaskGateway.start_batch(request) -> TaskHandle`, `status(run_id) -> Mapping[str, object]`,
`cancel(run_id) -> Mapping[str, object]`, and `capture(request) -> Mapping[str, object]` are the only
process methods TaskService may call.

- [ ] **Step 5: Run GREEN and commit**

```bash
PYTHONPATH=src/so101_teleop python3 -m pytest -q src/so101_teleop/test/backends/test_profiles.py src/so101_teleop/test/backends/test_mujoco_profile.py src/so101_teleop/test/teleop/test_backend_capabilities.py src/so101_teleop/test/teleop/test_task_gateway.py
git add src/so101_teleop/config/backends/gazebo_cpp.yaml src/so101_teleop/config/backends/gazebo_py.yaml src/so101_teleop/config/backends/mujoco_py.yaml src/so101_teleop/so101_teleop/backends/cli_adapter.py src/so101_teleop/so101_teleop/backends/profile.py src/so101_teleop/so101_teleop/backends/protocol.py src/so101_teleop/so101_teleop/task_gateway.py src/so101_teleop/test/backends/test_mujoco_profile.py src/so101_teleop/test/backends/test_profiles.py src/so101_teleop/test/teleop/test_backend_capabilities.py src/so101_teleop/test/teleop/test_task_gateway.py
git commit -m "feat: add Teleop task owner gateway"
```

### Task 10: Add task models, lease-gated API, events, and artifact sandbox

**Files:**
- Create: `src/so101_teleop/so101_teleop/task_artifacts.py`
- Create: `src/so101_teleop/so101_teleop/task_service.py`
- Modify: `src/so101_teleop/so101_teleop/models.py`
- Modify: `src/so101_teleop/so101_teleop/api.py`
- Modify: `src/so101_teleop/so101_teleop/server.py`
- Modify: `src/so101_teleop/so101_teleop/main.py`
- Modify: `src/so101_teleop/so101_teleop/openapi.json`
- Create: `src/so101_teleop/test/teleop/test_task_service.py`
- Create: `src/so101_teleop/test/teleop/test_task_artifacts.py`
- Modify: `src/so101_teleop/test/teleop/test_api.py`
- Modify: `src/so101_teleop/test/teleop/test_server_safety.py`
- Modify: `src/so101_teleop/test/teleop/test_openapi_export.py`

**Interfaces:**
- Produces: all `/tasks/*` HTTP routes, `WS /tasks/events`, `TaskService`, and `ManifestArtifactStore`.
- Consumes: Task 9 `CliTaskGateway`, current lease/session mutation gate, and configured `SO101_TASK_EVIDENCE_ROOT`.

- [ ] **Step 1: Write RED API and security tests**

```python
def test_start_requires_current_lease_and_session(task_client):
    response = task_client.post("/tasks/runs", json=task_request(lease_id="bad"))
    assert response.status_code == 409
    assert response.json()["code"] == "LEASE_REQUIRED"


def test_active_batch_blocks_old_motion_commands(task_service):
    task_service.start(valid_request())
    result = asyncio.run(task_service.teleop.command("plan_tcp", old_command()))
    assert result.code == "TASK_BATCH_ACTIVE"


def test_artifact_endpoint_rejects_manifest_escape(task_client, artifact_manifest):
    artifact_manifest["artifacts"][0]["relative_path"] = "../../etc/passwd"
    response = task_client.get("/tasks/artifacts/bad-id")
    assert response.status_code == 404
```

Add tests for single active run, idempotent command IDs, cancel, recovery confirmations, capture,
environment shutdown confirmation, browser-refresh status, PNG upload magic/size, and WebSocket
event order. Verify existing `/snapshot` and `/telemetry` responses are unchanged.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src/so101_teleop python3 -m pytest -q src/so101_teleop/test/teleop/test_task_service.py src/so101_teleop/test/teleop/test_task_artifacts.py src/so101_teleop/test/teleop/test_api.py src/so101_teleop/test/teleop/test_server_safety.py
```

- [ ] **Step 3: Add strict Pydantic request/response models**

Define `TaskPointModel`, `TaskRunRequest`, `TaskRunSummary`, `TaskPointSummary`,
`ReachabilityResponse`, `CaptureResponse`, `RenderedImageRequest`, and `TaskEvent`. Require
`schema_version=1`, safe IDs, finite XYZ, current `session_id`, `lease_id`, and `command_id`.
Implement the complete spec route table, including `GET /tasks/presets`, run list/detail,
reachability, start/cancel/recovery, capture/render upload, opaque artifact read, supervisor shutdown,
and `WS /tasks/events`; do not overload the existing `/workflow/*` routes.

- [ ] **Step 4: Implement TaskService and old-command lockout**

`TaskService` delegates process work to `CliTaskGateway`, maintains subscribers through bounded
`asyncio.Queue`s, and exposes immutable snapshots. Add one predicate to `TeleopService._mutation_gate`
so motion/reset/attachment/scene/workflow commands return `TASK_BATCH_ACTIVE`; health, snapshot,
capabilities, camera reads, and evidence reads remain available.

- [ ] **Step 5: Implement manifest-only artifact reads and routes**

`ManifestArtifactStore.open(artifact_id)` resolves only IDs present in `task-manifest.json`, rejects
absolute paths, `..`, symlinks, non-regular files, root escapes, and checksum changes. Use
`FileResponse` with the registered media type. Validate uploaded PNG magic, maximum 10 MiB, finite
view matrices, and a source PLY artifact ID from the same capture.

- [ ] **Step 6: Regenerate OpenAPI and run GREEN**

```bash
PYTHONPATH=src/so101_teleop python3 -m so101_teleop.openapi_export src/so101_teleop/so101_teleop/openapi.json
PYTHONPATH=src/so101_teleop python3 -m pytest -q src/so101_teleop/test/teleop/test_task_service.py src/so101_teleop/test/teleop/test_task_artifacts.py src/so101_teleop/test/teleop/test_api.py src/so101_teleop/test/teleop/test_server_safety.py src/so101_teleop/test/teleop/test_openapi_export.py
```

- [ ] **Step 7: Commit**

```bash
git add src/so101_teleop/so101_teleop/api.py src/so101_teleop/so101_teleop/main.py src/so101_teleop/so101_teleop/models.py src/so101_teleop/so101_teleop/openapi.json src/so101_teleop/so101_teleop/server.py src/so101_teleop/so101_teleop/task_artifacts.py src/so101_teleop/so101_teleop/task_service.py src/so101_teleop/test/teleop/test_api.py src/so101_teleop/test/teleop/test_openapi_export.py src/so101_teleop/test/teleop/test_server_safety.py src/so101_teleop/test/teleop/test_task_artifacts.py src/so101_teleop/test/teleop/test_task_service.py
git commit -m "feat: add Teleop task and evidence API"
```

### Task 11: Build the separate `/tasks` shell and free-point task builder

**Files:**
- Create: `src/so101_teleop/web/src/task-app.tsx`
- Create: `src/so101_teleop/web/src/api/task-client.ts`
- Create: `src/so101_teleop/web/src/api/task-types.ts`
- Create: `src/so101_teleop/web/src/lib/task-yaml.ts`
- Create: `src/so101_teleop/web/src/lib/task-yaml.test.ts`
- Create: `src/so101_teleop/web/src/components/tasks/task-builder.tsx`
- Create: `src/so101_teleop/web/src/components/tasks/task-builder.test.tsx`
- Modify: `src/so101_teleop/web/src/main.tsx`
- Modify: `src/so101_teleop/web/src/api/types.ts`

**Interfaces:**
- Produces: `TaskApp`, `TaskApiClient`, `TaskBuilder`, `parseTaskYaml`, and `dumpTaskYaml`.
- Consumes: Task 10 OpenAPI shapes; no ROS or filesystem APIs.

- [ ] **Step 1: Record Bun provenance and write frontend RED tests**

Record `command -v bun` and `bun --version` in the ledger, then add:

```tsx
it("adds presets and free points without mutating the old app", async () => {
  render(<TaskBuilder presets={PRESETS} points={[]} onChange={onChange} />);
  await user.click(screen.getByRole("button", { name: "Add task_start" }));
  await user.click(screen.getByRole("button", { name: "Add free point" }));
  await user.type(screen.getByLabelText("Free point X metres"), "0.01");
  expect(onChange).toHaveBeenCalled();
});


it("round trips schema version 1 and rejects non-finite XYZ", () => {
  const yaml = dumpTaskYaml(POINTS);
  expect(parseTaskYaml(yaml)).toEqual(POINTS);
  expect(() => parseTaskYaml("schema_version: 1\npoints:\n- id: p\n  label: P\n  cup_position_world_m: [.nan, 0, 0]\n"))
    .toThrow("TASK_POINT_INVALID");
});
```

- [ ] **Step 2: Run RED**

```bash
bun --cwd="$PWD/src/so101_teleop/web" test src/lib/task-yaml.test.ts src/components/tasks/task-builder.test.tsx
```

- [ ] **Step 3: Implement path dispatch without modifying `App`**

```tsx
const Root = location.pathname === "/tasks" ? TaskApp : App;
createRoot(document.getElementById("root")!).render(
  <TooltipProvider><Root /><Toaster richColors position="top-right" /></TooltipProvider>,
);
```

Do not add task controls or task state to `app.tsx`. Unknown SPA paths continue through the existing
FastAPI index fallback and render the old app only when the path is `/`.

- [ ] **Step 4: Implement task editing and API submission**

Use controlled inputs for ID, label, and XYZ; preserve order; reject duplicate IDs and non-finite
numbers before POST; provide Move Up/Down/Delete; import from a local file; export a Blob named
`so101-rgbd-task-points.yaml`; show `PENDING/REACHABLE/UNREACHABLE/UNKNOWN`; require the acquired
lease before Validate, Start, Cancel, Recovery, Capture, or Shutdown.

- [ ] **Step 5: Run GREEN and commit**

```bash
bun --cwd="$PWD/src/so101_teleop/web" test src/lib/task-yaml.test.ts src/components/tasks/task-builder.test.tsx
git add src/so101_teleop/web/src/api/task-client.ts src/so101_teleop/web/src/api/task-types.ts src/so101_teleop/web/src/api/types.ts src/so101_teleop/web/src/components/tasks/task-builder.test.tsx src/so101_teleop/web/src/components/tasks/task-builder.tsx src/so101_teleop/web/src/lib/task-yaml.test.ts src/so101_teleop/web/src/lib/task-yaml.ts src/so101_teleop/web/src/main.tsx src/so101_teleop/web/src/task-app.tsx
git commit -m "feat: add Teleop RGB-D task builder"
```

### Task 12: Add the Three.js PLY viewer and current sensor capture

**Files:**
- Modify: `src/so101_teleop/web/package.json`
- Modify: `src/so101_teleop/web/bun.lock`
- Create: `src/so101_teleop/web/src/components/tasks/point-cloud-viewer.tsx`
- Create: `src/so101_teleop/web/src/components/tasks/point-cloud-viewer.test.tsx`
- Create: `src/so101_teleop/web/src/components/tasks/live-sensor.tsx`
- Create: `src/so101_teleop/web/src/components/tasks/live-sensor.test.tsx`
- Modify: `src/so101_teleop/web/src/task-app.tsx`

**Interfaces:**
- Produces: `PointCloudViewer`, `PointCloudViewMetadata`, and `LiveSensor`.
- Consumes: Task 10 capture/artifact endpoints and Task 11 client.

```ts
export type PointCloudViewMetadata = {
  source_artifact_id: string;
  source_sha256: string;
  original_point_count: number;
  displayed_point_count: number;
  sampling_rule: "all" | "fixed-stride";
  sampling_stride: number;
  color_mode: "rgb" | "uniform";
  point_size: number;
  background_rgb: [number, number, number];
  viewport_px: [number, number];
  view_matrix: number[];
  projection_matrix: number[];
};
```

- [ ] **Step 1: Pin Three.js with Bun**

```bash
bun --cwd="$PWD/src/so101_teleop/web" add --exact three@0.184.0
bun --cwd="$PWD/src/so101_teleop/web" add --dev --exact @types/three@0.184.0
```

Verify `package.json` contains exact versions and `bun.lock` changes without a `package-lock.json`.

- [ ] **Step 2: Write RED component tests with a mocked renderer**

```tsx
it("loads full and cup PLY and saves the current rendered view", async () => {
  render(<PointCloudViewer capture={CAPTURE} api={api} rendererFactory={fakeRenderer} />);
  await user.selectOptions(screen.getByLabelText("Point cloud"), "cup");
  await user.click(screen.getByRole("button", { name: "Save point-cloud screenshot" }));
  expect(api.uploadRenderedImage).toHaveBeenCalledWith(
    "capture-1",
    expect.any(Blob),
    expect.objectContaining({ source_artifact_id: "cup-ply", color_mode: "rgb" }),
  );
});


it("Capture now displays artifacts sharing one source stamp", async () => {
  render(<LiveSensor api={apiReturningCapture} lease={LEASE} sessionId="sim-a" />);
  await user.click(screen.getByRole("button", { name: "Capture now" }));
  expect(await screen.findByAltText("Current RGB camera frame")).toBeVisible();
  expect(screen.getByText("source stamp 123456789")).toBeVisible();
});
```

- [ ] **Step 3: Run RED**

```bash
bun --cwd="$PWD/src/so101_teleop/web" test src/components/tasks/point-cloud-viewer.test.tsx src/components/tasks/live-sensor.test.tsx
```

- [ ] **Step 4: Implement the viewer with deterministic resource cleanup**

Use `PLYLoader.parse(await response.arrayBuffer())`, `THREE.Points`, `PointsMaterial`, axes helpers,
cup-center marker, perspective camera, and `OrbitControls`. Revoke object URLs, dispose geometries,
materials, controls, and renderer on capture change/unmount. Reset view from the cloud bounding box.
Render all points up to 400,000; above that limit select fixed indices with
`stride = Math.ceil(originalCount / 400000)`. Record `fixed-stride`, original count, displayed
count, and stride in the upload metadata while retaining the original PLY artifact unchanged.
Before screenshot, call `renderer.render(scene, camera)` and `renderer.domElement.toBlob(...,
"image/png")`; upload view/projection matrices, point size, color mode, viewport, background, and
source artifact ID.

- [ ] **Step 5: Run GREEN and production build**

```bash
bun --cwd="$PWD/src/so101_teleop/web" test src/components/tasks/point-cloud-viewer.test.tsx src/components/tasks/live-sensor.test.tsx
bun --cwd="$PWD/src/so101_teleop/web" run build
```

Expected: tests and TypeScript/Vite build pass with no external CDN request in generated code.

- [ ] **Step 6: Commit**

```bash
git add src/so101_teleop/web/bun.lock src/so101_teleop/web/package.json src/so101_teleop/web/src/components/tasks/live-sensor.test.tsx src/so101_teleop/web/src/components/tasks/live-sensor.tsx src/so101_teleop/web/src/components/tasks/point-cloud-viewer.test.tsx src/so101_teleop/web/src/components/tasks/point-cloud-viewer.tsx src/so101_teleop/web/src/task-app.tsx
git commit -m "feat: view and capture RGB-D point clouds"
```

### Task 13: Add live task progress, evidence browsing, and page-isolation E2E tests

**Files:**
- Create: `src/so101_teleop/web/src/components/tasks/task-progress.tsx`
- Create: `src/so101_teleop/web/src/components/tasks/task-progress.test.tsx`
- Create: `src/so101_teleop/web/src/components/tasks/evidence-browser.tsx`
- Create: `src/so101_teleop/web/src/components/tasks/evidence-browser.test.tsx`
- Modify: `src/so101_teleop/web/src/api/task-client.ts`
- Modify: `src/so101_teleop/web/src/task-app.tsx`
- Modify: `src/so101_teleop/web/e2e/teleop.spec.ts`
- Create: `src/so101_teleop/web/e2e/tasks.spec.ts`

**Interfaces:**
- Produces: reconnecting task-event client, `TaskProgress`, and `EvidenceBrowser`.
- Consumes: Task 10 API/event shapes and artifact IDs; never accepts a filesystem path.

- [ ] **Step 1: Write RED tests for refresh recovery and evidence rows**

```tsx
it("restores a running batch and shows a failed point followed by success", async () => {
  render(<TaskProgress run={RUN_WITH_FAILURE_THEN_SUCCESS} />);
  expect(screen.getByText("first — FAILED")).toBeVisible();
  expect(screen.getByText("second — SUCCEEDED")).toBeVisible();
});


it("renders only registered artifact URLs", () => {
  render(<EvidenceBrowser run={RUN} />);
  expect(screen.getByRole("link", { name: "RGB PNG" })).toHaveAttribute(
    "href", "/tasks/artifacts/rgb-id"
  );
  expect(screen.queryByText(/\/tmp\//)).not.toBeInTheDocument();
});
```

Add Playwright tests that `/` still exposes existing tabs and `/tasks` exposes Task Builder, Live
Sensor, and Runs & Evidence; refresh during `RUNNING` restores state; an unreachable point remains
visible while the following point succeeds.

- [ ] **Step 2: Run RED**

```bash
bun --cwd="$PWD/src/so101_teleop/web" test src/components/tasks/task-progress.test.tsx src/components/tasks/evidence-browser.test.tsx
bun --cwd="$PWD/src/so101_teleop/web" run test:e2e -- e2e/tasks.spec.ts
```

- [ ] **Step 3: Implement bounded reconnect and evidence presentation**

On mount, fetch `/tasks/runs`, select the active/latest run, then connect `/tasks/events`. Reconnect
with bounded backoff and always refetch status after reconnection. Render batch and point statuses,
epoch, current phase, first failure code, RGB, PLY, point-cloud screenshot, Viewer screenshot,
reachability JSON, dynamic manifest, physical outcome, and logs through opaque artifact URLs.

- [ ] **Step 4: Run all Web tests and E2E**

```bash
bun --cwd="$PWD/src/so101_teleop/web" test
bun --cwd="$PWD/src/so101_teleop/web" run test:e2e
bun --cwd="$PWD/src/so101_teleop/web" run build
```

Expected: all prior `/` tests and new `/tasks` tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/so101_teleop/web/e2e/tasks.spec.ts src/so101_teleop/web/e2e/teleop.spec.ts src/so101_teleop/web/src/api/task-client.ts src/so101_teleop/web/src/components/tasks/evidence-browser.test.tsx src/so101_teleop/web/src/components/tasks/evidence-browser.tsx src/so101_teleop/web/src/components/tasks/task-progress.test.tsx src/so101_teleop/web/src/components/tasks/task-progress.tsx src/so101_teleop/web/src/task-app.tsx
git commit -m "feat: browse RGB-D task evidence"
```

### Task 14: Run full source, package, install, and provenance gates

**Files:**
- Modify: `src/so101_demo_py/test/test_macos_install_contract.py`
- Modify: `src/so101_teleop/test/teleop/test_web_bundle.py`
- Modify: `src/so101_teleop/test/test_launch_contract.py`
- Modify: `docs/experiments/macos-rgbd-reset-world-task-station-experiment-ledger.md`
- Modify: `docs/so101-rgbd-perception-pick-place-source-guide.md`

**Interfaces:**
- Produces: fresh candidate overlay and documented installed entry points.
- Consumes: all prior task commits.

- [ ] **Step 1: Add install-contract RED assertions**

Assert the candidate install contains `so101_mujoco_rgbd_batch`, `task_reachability`,
`rgbd_sensor_capture`, `so101_mujoco_task_station.launch.py`, preset YAML, `/tasks` Web assets, and
Three.js chunks. Assert the runtime package versions for all `mujoco_ros2_control` packages are
`0.1.0`.

- [ ] **Step 2: Run focused RED, patch only packaging omissions, and rerun GREEN**

```bash
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q src/so101_demo_py/test/test_macos_install_contract.py
PYTHONPATH=src/so101_teleop python3 -m pytest -q src/so101_teleop/test/teleop/test_web_bundle.py src/so101_teleop/test/test_launch_contract.py
```

Only modify `setup.py`, `package.xml`, `CMakeLists.txt`, or launch install declarations when these
tests prove an omitted runtime resource.

- [ ] **Step 3: Run complete affected source suites**

```bash
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q src/so101_demo_py/test
PYTHONPATH=src/so101_teleop python3 -m pytest -q src/so101_teleop/test
bun --cwd="$PWD/src/so101_teleop/web" test
bun --cwd="$PWD/src/so101_teleop/web" run build
```

Record exact pass counts and exit codes in the ledger; an exit-zero run that collects zero tests is invalid.

- [ ] **Step 4: Build a fresh isolated candidate overlay**

Use one build/install/log base under the registered task root and source the current macOS ROS 2
environment with the repository's existing direnv procedure. Build the dependency-closed set:

```bash
colcon build --merge-install --install-base /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/install --build-base /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/build --log-base /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/colcon-log --packages-up-to so101_demo_py so101_teleop
```

- [ ] **Step 5: Prove installed runtime and fork provenance**

After sourcing the exact candidate overlay, record:

```bash
ros2 pkg prefix so101_demo_py
ros2 pkg prefix so101_teleop
ros2 pkg prefix mujoco_ros2_control
ros2 pkg xml mujoco_ros2_control
ros2 pkg executables so101_demo_py
ros2 launch so101_demo_py so101_mujoco_task_station.launch.py --show-args
```

Also record executable `realpath`/`stat`, submodule SHA, installed package XML hashes, and active
library paths. Reject parent/default overlay resolution.

- [ ] **Step 6: Update the teaching guide and commit packaging/docs**

Add the persistent RESET_WORLD batch, `/tasks` page, live RGB/point-cloud capture, component list,
topic/service/action flow, and copyable macOS commands to the existing source guide. Keep the
earlier single-run FULL_RESTART instructions clearly separate.

```bash
git add docs/experiments/macos-rgbd-reset-world-task-station-experiment-ledger.md docs/so101-rgbd-perception-pick-place-source-guide.md src/so101_demo_py/package.xml src/so101_demo_py/setup.py src/so101_demo_py/test/test_macos_install_contract.py src/so101_teleop/CMakeLists.txt src/so101_teleop/package.xml src/so101_teleop/test/teleop/test_web_bundle.py src/so101_teleop/test/test_launch_contract.py
git commit -m "test: qualify installed RGB-D task station"
```

### Task 15: Perform macOS visible runtime acceptance

**Files:**
- Modify: `docs/experiments/macos-rgbd-reset-world-task-station-experiment-ledger.md`
- Evidence only under: `/tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/`

**Interfaces:**
- Produces: one qualifying four-point batch, one unreachable-then-reachable robustness batch, manual sensor capture, inspected screenshots, and final cleanup evidence.
- Consumes: the exact installed overlay from Task 14 and the `gui-capture` skill.

- [ ] **Step 1: Perform a read-only live inventory before starting anything**

Record `pwd`, branch, commit, submodule, status, existing MuJoCo/MoveIt/controller/Teleop processes,
ROS graph, relevant ports, and GUI windows. Preserve unrelated processes. Create a unique
`ROS_DOMAIN_ID` and session ID in the ledger before launch.

- [ ] **Step 2: Start the task station with the visible Viewer**

Run the installed launch with `headless:=false`, the registered evidence root, one session ID, and
the installed preset YAML. Wait for readiness and prove real aligned CameraInfo/RGB/depth samples,
positive finite depth, TF, controllers, MoveIt, scene readback, and task API health before submitting
a batch.

- [ ] **Step 3: Use `/tasks` to validate and run the four presets**

Select the four points in the approved order, run reachability, and start the batch. Observe the
Viewer manually. For each point, record reset epoch, RGB-D source stamp, PLY counts, `/cup_pose`,
target calculation, complete dynamic trace, MoveIt result, controller/joint/TCP changes, physical
grasp/transport/release, final stable pose, Planning Scene detach, and fresh RGB/point-cloud/Viewer
screenshots.

- [ ] **Step 4: Inspect each fresh GUI result**

Use `gui-capture` with `snapshot -> action -> fresh snapshot`. Inspect, do not merely list, the
Viewer and browser images. Confirm the cup visibly starts at each requested position and finishes
released in the target region. Save screenshot paths and hashes in the ledger.

- [ ] **Step 5: Run the continuation robustness batch**

Submit one deliberately unreachable point followed by one known reachable preset. Verify the first
is `SKIPPED_UNREACHABLE`, its evidence is retained, no motion state starts for it, and the later point
succeeds in the same healthy session. Keep this separate from the four-point success denominator.

- [ ] **Step 6: Validate manual current sensor capture and point-cloud screenshot**

Click `Capture now`; verify RGB and full/cup PLY share one source stamp and TF. Orbit the Three.js
cloud, switch full/cup mode, change point size, save a point-cloud screenshot, reload the page, and
prove the capture remains browsable through artifact IDs.

- [ ] **Step 7: Shut down and verify cleanup**

Use `Shutdown Environment` or terminate the controlling launch. Prove every owned process, ROS
node, Viewer window, and task port is gone while unrelated processes remain. Finalize the ledger
checkpoint with retained, archived, and deletion-candidate evidence; do not delete anything.

- [ ] **Step 8: Run final verification and commit the immutable ledger conclusion**

```bash
git diff --check
git status --short
git submodule status
```

Repeat the focused/full source gates if any source changed after Task 14. Commit only the final
ledger and any evidence index tracked by repository policy:

```bash
git add docs/experiments/macos-rgbd-reset-world-task-station-experiment-ledger.md
git commit -m "docs: record macOS RGB-D task station acceptance"
```

Do not merge or push until a fresh `superpowers:requesting-code-review` pass finds no blocking
issues and `superpowers:verification-before-completion` re-runs the completion evidence.
