# SO-101 Teleop Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a simulation-only SO-101 browser teleoperation console backed by a Python FastAPI/rclpy server on ai-station.

**Architecture:** One ROS worker thread owns all rclpy entities and publishes immutable telemetry to a FastAPI event loop. A serialized command coordinator gates all mutations and owns plans. A React + TypeScript + Vite SPA using shadcn/ui preset `bKsFBxgG` is built to static files and served by FastAPI.

**Tech Stack:** Python 3, rclpy, FastAPI, Uvicorn, Pydantic, ROS 2 Jazzy, MoveIt 2, ros_gz_bridge, Pillow/X11, React, TypeScript, Vite, shadcn/ui, Vitest, Testing Library, pytest.

## Global Constraints

- Simulation only; disable mutation unless Gazebo, MoveIt, both controllers, fresh joint/TF/object state, and Planning Scene are ready.
- Bind only to an explicit loopback or Tailscale `100.64.0.0/10` address; reject `0.0.0.0` and ordinary LAN addresses.
- Use React + TypeScript + Vite and shadcn/ui preset `bKsFBxgG`; no Next.js or persistent Node server.
- Joint step is exactly 1 degree; TCP XYZ step exactly 1 mm; TCP RPY step exactly 1 degree.
- Support World and Tool TCP steps, defaulting to World.
- Joints 1-5 use arm planning; q6 uses the gripper controller; Execute All runs arm then q6.
- Actual telemetry never overwrites Target state.
- Execute only the latest server-owned, collision-free, unexpired plan. Force Continue applies only to one pick-place post-action validation failure and never bypasses lease/readiness/staleness/action failures.
- Keep Gazebo contact and MoveIt collision evidence separate.
- Attach/Detach and Reset are verified multi-layer transactions.
- Reuse the existing C++ pick-place state machine/checkpoint for Step and Run; insert stable wait, 1 mm micro-lift and physical-grasp verification before Attach.
- Screenshot captures only one uniquely identified Gazebo window.
- Target YAML is downloaded/uploaded by the browser and is not persisted by the server.
- Follow `.agents/skills/so101-dev/SKILL.md` for every ai-station run; preserve all existing dirty files and stage only named teleop scope.

## File Map

```text
src/so101_gazebo_demo/
├── so101_teleop/
│   ├── models.py          # Pydantic wire/domain models
│   ├── geometry.py        # quaternion and World/Tool stepping
│   ├── control.py         # lease, command lock, idempotency, plan store
│   ├── ports.py           # typed ROS/screenshot boundaries
│   ├── telemetry.py       # immutable snapshot and readiness reducer
│   ├── moveit_gateway.py  # IK, plan, validity, execute, gripper, home
│   ├── scene_gateway.py   # attach, detach, repair, reset
│   ├── workflow_gateway.py # existing pick-place state machine step/run adapter
│   ├── screenshot.py      # Gazebo-only X11 capture
│   ├── service.py         # application orchestration
│   ├── api.py             # REST/WebSocket/static files
│   ├── openapi_export.py  # deterministic frontend contract
│   └── main.py            # process lifecycle
├── scripts/so101_teleop_server.py
├── launch/so101_teleop.launch.py
├── config/so101_teleop.yaml
├── web/                   # Vite/shadcn SPA
└── test/teleop/           # Python unit/contract tests
```

Targeted existing-file edits: `CMakeLists.txt`, `package.xml`, `launch/so101_gazebo.launch.py`, `test/test_package_layout.py`, and `test/test_so101_launch_contract.py`.

---

### Task 1: Installable Python Package and API Models

**Files:**
- Create: `so101_teleop/__init__.py`, `so101_teleop/models.py`, `test/teleop/test_models.py`
- Modify: `CMakeLists.txt`, `package.xml`, `test/test_package_layout.py`

**Interfaces:**
- Produces: `ServerMode`, `StepFrame`, `Pose6D`, `JointSample`, `CollisionPair`, `TelemetrySnapshot`, `JointPlanRequest`, `TcpPlanRequest`, `PlanSummary`, `WorkflowSnapshot`, `ValidationEvidence`, `OverrideAudit`, `CommandResult`.

- [ ] **Step 1: Write failing model and install-contract tests**

```python
def test_pose_names_frames_and_units():
    pose = Pose6D(frame_id="world", tcp_frame="so101_tcp", x_m=0.02,
                  y_m=-0.28, z_m=0.20, roll_rad=0.0, pitch_rad=0.0, yaw_rad=0.0)
    assert set(pose.dict()) >= {"frame_id", "tcp_frame", "x_m", "roll_rad"}

def test_result_separates_request_acceptance_from_robot_success():
    result = CommandResult(command_id="c1", accepted=True, succeeded=False,
                           code="PLAN_STALE", message="start changed", layers={})
    assert result.accepted and not result.succeeded
```

- [ ] **Step 2: Verify RED**

```bash
source /opt/ros/jazzy/setup.zsh
cd /data/work/ws_moveit
pytest -q src/so101_gazebo_demo/test/teleop/test_models.py \
  src/so101_gazebo_demo/test/test_package_layout.py
```

- [ ] **Step 3: Implement models and ament Python installation**

```python
class ServerMode(str, Enum):
    STARTING = "STARTING"
    READ_ONLY = "READ_ONLY"
    READY = "READY"
    BUSY = "BUSY"
    DEGRADED = "DEGRADED"

class StepFrame(str, Enum):
    WORLD = "WORLD"
    TOOL = "TOOL"
```

Use `ament_cmake_python` and `ament_python_install_package(so101_teleop)`. Declare direct dependencies for rclpy, tf2_ros, controller_manager_msgs, moveit_msgs, control_msgs, trajectory_msgs, tf2_msgs, ros_gz_interfaces, FastAPI, Uvicorn, Pydantic, Pillow, and YAML. Keep Pydantic calls compatible with the ai-station system version by using `dict()` and `copy(update=...)` in shared examples.

- [ ] **Step 4: Verify GREEN and installed import**

```bash
pytest -q src/so101_gazebo_demo/test/teleop/test_models.py \
  src/so101_gazebo_demo/test/test_package_layout.py
colcon build --packages-select so101_gazebo_demo --symlink-install
source install/setup.zsh
python3 -c 'import so101_teleop.models'
```

- [ ] **Step 5: Commit**

```bash
git add src/so101_gazebo_demo/so101_teleop src/so101_gazebo_demo/test/teleop/test_models.py \
  src/so101_gazebo_demo/test/test_package_layout.py src/so101_gazebo_demo/CMakeLists.txt \
  src/so101_gazebo_demo/package.xml
git commit -m "feat(so101): add teleop server models"
```

### Task 2: Pose Math and Exact Step Semantics

**Files:**
- Create: `so101_teleop/geometry.py`, `test/teleop/test_geometry.py`

**Interfaces:**
- Produces: `apply_translation_step`, `apply_rotation_step`, `quaternion_from_rpy`, `rpy_from_quaternion`.
- Consumes: `Pose6D`, `StepFrame`.

- [ ] **Step 1: Write failing exact-step tests**

```python
def test_world_y_step_is_one_millimetre():
    actual = apply_translation_step(BASE, "y", 0.001, StepFrame.WORLD)
    assert actual.y_m == pytest.approx(BASE.y_m + 0.001, abs=1e-12)

def test_tool_x_step_uses_tcp_orientation():
    yaw90 = BASE.copy(update={"yaw_rad": math.pi / 2})
    actual = apply_translation_step(yaw90, "x", 0.001, StepFrame.TOOL)
    assert actual.y_m == pytest.approx(yaw90.y_m + 0.001, abs=1e-12)
```

- [ ] **Step 2: Verify RED**

```bash
pytest -q src/so101_gazebo_demo/test/teleop/test_geometry.py
```

- [ ] **Step 3: Implement normalized quaternion composition**

World rotations pre-multiply the increment; Tool rotations post-multiply it. Never implement Tool RPY by adding Euler components.

```python
result = multiply(delta, current) if frame is StepFrame.WORLD else multiply(current, delta)
roll, pitch, yaw = rpy_from_quaternion(normalize(result))
```

- [ ] **Step 4: Verify GREEN**

```bash
pytest -q src/so101_gazebo_demo/test/teleop/test_geometry.py
```

- [ ] **Step 5: Commit**

```bash
git add src/so101_gazebo_demo/so101_teleop/geometry.py \
  src/so101_gazebo_demo/test/teleop/test_geometry.py
git commit -m "feat(so101): add world and tool pose stepping"
```

### Task 3: Lease, Command Lock, Idempotency, and Plan Store

**Files:**
- Create: `so101_teleop/control.py`, `test/teleop/test_control.py`

**Interfaces:**
- Produces: `ControlLeaseManager`, `CommandCoordinator`, `PlanStore`.
- Consumes: `PlanSummary`, `CommandResult`, `ServerMode`.

- [ ] **Step 1: Write failing one-writer and stale-plan tests**

```python
async def test_duplicate_command_runs_once():
    first = await coordinator.run("c1", FINGERPRINT, operation)
    second = await coordinator.run("c1", FINGERPRINT, operation)
    assert first == second
    assert operation.await_count == 1

def test_changed_scene_invalidates_plan():
    store.put(PLAN)
    with pytest.raises(PlanRejected, match="PLAN_STALE_SCENE"):
        store.require_executable(PLAN.start_fingerprint, PLAN.scene_revision + 1)
```

- [ ] **Step 2: Verify RED**

```bash
pytest -q src/so101_gazebo_demo/test/teleop/test_control.py
```

- [ ] **Step 3: Implement monotonic lease expiry and one asyncio mutation lock**

Cache completed results by command ID and payload fingerprint. Reusing an ID with a different fingerprint returns `COMMAND_ID_REUSED`. Busy mutations return `SERVER_BUSY`.

- [ ] **Step 4: Verify GREEN**

```bash
pytest -q src/so101_gazebo_demo/test/teleop/test_control.py
```

- [ ] **Step 5: Commit**

```bash
git add src/so101_gazebo_demo/so101_teleop/control.py \
  src/so101_gazebo_demo/test/teleop/test_control.py
git commit -m "feat(so101): gate teleop control and plans"
```

### Task 4: ROS Runtime, Telemetry, and Readiness

**Files:**
- Create: `so101_teleop/ports.py`, `so101_teleop/telemetry.py`, `test/teleop/test_telemetry.py`
- Modify: `launch/so101_gazebo.launch.py`, `test/test_so101_launch_contract.py`

**Interfaces:**
- Produces: `RosRuntime`, `TelemetryCollector.snapshot()`, `ReadinessEvaluator.evaluate()`.
- Consumes: `/joint_states`, world-to-TCP TF, controller list, contacts, attachment state, Gazebo pose info and world statistics.

- [ ] **Step 1: Write failing bridge/readiness tests**

```python
def test_bridge_exposes_pose_and_world_statistics():
    args = attachment_bridge_node().arguments
    assert any("pose/info@tf2_msgs/msg/TFMessage" in item for item in args)
    assert any("stats@ros_gz_interfaces/msg/WorldStatistics" in item for item in args)

def test_missing_q6_forces_read_only():
    assert evaluator.evaluate(snapshot_without_joint("6")).mode is ServerMode.READ_ONLY
```

- [ ] **Step 2: Verify RED**

```bash
pytest -q src/so101_gazebo_demo/test/test_so101_launch_contract.py \
  src/so101_gazebo_demo/test/teleop/test_telemetry.py
```

- [ ] **Step 3: Add configurable bridges and immutable snapshots**

Bridge world pose info to `/so101/gazebo_pose_info` and world stats to `/so101/gazebo_world_stats`. Each snapshot includes sequence, server timestamp, simulation session ID, source ages, joints, TCP, object, controllers, attachment, contacts, scene and RTF.

- [ ] **Step 4: Verify GREEN**

```bash
pytest -q src/so101_gazebo_demo/test/test_so101_launch_contract.py \
  src/so101_gazebo_demo/test/teleop/test_telemetry.py
```

- [ ] **Step 5: Commit**

```bash
git add src/so101_gazebo_demo/so101_teleop/{ports.py,telemetry.py} \
  src/so101_gazebo_demo/test/teleop/test_telemetry.py \
  src/so101_gazebo_demo/launch/so101_gazebo.launch.py \
  src/so101_gazebo_demo/test/test_so101_launch_contract.py
git commit -m "feat(so101): stream teleop simulation state"
```

### Task 5: MoveIt Planning, Collision Evidence, and Execution

**Files:**
- Create: `so101_teleop/moveit_gateway.py`, `test/teleop/test_moveit_gateway.py`

**Interfaces:**
- Produces: `plan_joints`, `plan_tcp`, `execute`, `cancel`, `execute_gripper`, `home`.
- Consumes: GetPositionIK, GetMotionPlan, GetStateValidity, ExecuteTrajectory and FollowJointTrajectory.

- [ ] **Step 1: Write failing gateway tests**

Cover joint order `1..5`, q6 exclusion from arm plans, actual-state IK seed, current/target validity, every trajectory waypoint validity, collision pair names, plan cancellation, and q6-only goals.

```python
async def test_first_colliding_waypoint_rejects_plan():
    result = await gateway.plan_joints(REQUEST, SNAPSHOT)
    assert result.code == "TRAJECTORY_COLLISION"
    assert result.collisions[0].waypoint_index == 3
    assert {result.collisions[0].object_a, result.collisions[0].object_b} == {"jaw", "plastic_cup"}
```

- [ ] **Step 2: Verify RED**

```bash
pytest -q src/so101_gazebo_demo/test/teleop/test_moveit_gateway.py
```

- [ ] **Step 3: Implement ROS service/action requests**

Use actual joints as start state. TCP planning calls IK then follows the joint-plan path. Keep `RobotTrajectory` only in `PlanStore`; expose a summary. Validate all returned waypoints and preserve the first collision pair/index.

- [ ] **Step 4: Verify GREEN**

```bash
pytest -q src/so101_gazebo_demo/test/teleop/test_moveit_gateway.py \
  src/so101_gazebo_demo/test/teleop/test_control.py
```

- [ ] **Step 5: Commit**

```bash
git add src/so101_gazebo_demo/so101_teleop/moveit_gateway.py \
  src/so101_gazebo_demo/test/teleop/test_moveit_gateway.py
git commit -m "feat(so101): plan and execute teleop targets"
```

### Task 6: Attach, Detach, Repair, Home, and Reset

**Files:**
- Create: `so101_teleop/scene_gateway.py`, `test/teleop/test_scene_gateway.py`

**Interfaces:**
- Produces: `attach`, `detach`, `repair`, `reset_simulation` with layer verification.
- Consumes: Gazebo attach/detach and durable state, GetPlanningScene, ApplyPlanningScene, object pose, ControlWorld, controllers, and `MoveItGateway.cancel()`.

- [ ] **Step 1: Write failing transaction tests**

```python
async def test_attach_rolls_back_gazebo_after_moveit_failure():
    result = await gateway.attach("plastic_cup")
    assert calls == ["gazebo_attach", "verify_gazebo", "moveit_attach",
                     "gazebo_detach", "verify_gazebo_detached"]
    assert result.layers == {"gazebo": "detached", "moveit": "world"}

async def test_reset_reports_unconverged_scene():
    result = await gateway.reset_simulation()
    assert result.code == "RESET_INCOMPLETE"
```

- [ ] **Step 2: Verify RED**

```bash
pytest -q src/so101_gazebo_demo/test/teleop/test_scene_gateway.py
```

- [ ] **Step 3: Implement verified transactions**

Detach waits for Gazebo stability and restores the MoveIt world object using the observed final 6D pose. Reset uses Gazebo ControlWorld reset-all, then verifies controllers, joints, TF, objects, Gazebo attachment and Planning Scene membership.

- [ ] **Step 4: Verify GREEN plus existing reset/attachment tests**

```bash
pytest -q src/so101_gazebo_demo/test/teleop/test_scene_gateway.py
colcon test --packages-select so101_gazebo_demo \
  --ctest-args -R 'test_so101_(world_reset|gazebo_reset_adapter|gazebo_attachment|moveit_scene)'
colcon test-result --verbose
```

- [ ] **Step 5: Commit**

```bash
git add src/so101_gazebo_demo/so101_teleop/scene_gateway.py \
  src/so101_gazebo_demo/test/teleop/test_scene_gateway.py
git commit -m "feat(so101): control teleop scene transactions"
```

### Task 7: Physical-Grasp Gates and Pick-place Step Adapter

**Files:**
- Modify: `include/so101_gazebo_demo/pick_place/domain_types.hpp`, `src/pick_place/domain_types.cpp`, `src/pick_place/transition_table.cpp`
- Modify: `include/so101_gazebo_demo/pick_place/runner.hpp`, `src/pick_place/runner.cpp`, `src/pick_place/pick_place_state_machine.cpp`
- Create: `include/so101_gazebo_demo/pick_place/physical_grasp_validator.hpp`, `src/pick_place/physical_grasp_validator.cpp`
- Create: `so101_teleop/workflow_gateway.py`, `test/teleop/test_workflow_gateway.py`
- Modify/Create: focused C++ tests under `test/pick_place/`

**Interfaces:**
- Produces: `WAIT_GRASP_STABLE`, `MICRO_LIFT`, `WAIT_MICRO_LIFT_STABLE`, `VERIFY_PHYSICAL_GRASP`, `WorkflowGateway.start/step/run/stop/reset/force_continue`.
- Consumes: the existing runner, checkpoint/session validator, world observer, motion/gripper adapters and installed `pick_place_state_machine` executable.

- [ ] **Step 1: Write failing transition, metric and override-boundary tests**

```cpp
TEST(PhysicalGraspValidator, passes_when_cup_clears_table_and_follows_tcp) {
  const auto result = validator.evaluate(before, after, contacts);
  EXPECT_TRUE(result.passed);
  EXPECT_GT(result.table_clearance_m, 0.0005);
  EXPECT_GT(result.cup_follow_ratio, 0.8);
}

TEST(Runner, force_continue_cannot_override_action_failure) {
  const auto result = runner.runStep(requestWithOverride(State::MICRO_LIFT), action_failure);
  EXPECT_EQ(result.failure->code, "OVERRIDE_NOT_ALLOWED");
}
```

Python contract tests must also prove that the browser cannot supply an arbitrary state, one `step()` runs exactly the checkpoint's next state, and an override is bound to one workflow run/state/snapshot revision and consumed once.

- [ ] **Step 2: Verify RED**

```bash
cd /data/work/ws_moveit
colcon test --packages-select so101_gazebo_demo \
  --ctest-args -R '(transition_table|pick_place_runner|physical_grasp_validator)'
pytest -q src/so101_gazebo_demo/test/teleop/test_workflow_gateway.py
```

- [ ] **Step 3: Add physical-grasp states before Attach**

Use consecutive sample windows for both stable waits. Configure a World-Z micro-lift of exactly `0.001` m. Emit structured evidence for table clearance, TCP/cup Z deltas, cup-follow ratio, XY slip, orientation change, contacts, thresholds and sample ages. Do not attach until verification passes or a permitted one-shot validation override is consumed.

- [ ] **Step 4: Expose the existing state machine through a serialized gateway**

Drive the installed executable with its checkpoint and simulation session ID; extend its CLI/result envelope only as needed for machine-readable single-step operation. `step` derives the next state from the verified checkpoint. In interactive step/run mode, a validation failure is checkpointed as `VALIDATION_FAILED` without automatically entering recovery; `run` stops there. `run` otherwise repeats the same step operation until pause/cancel or terminal state. Never maintain a second transition table in Python or TypeScript.

- [ ] **Step 5: Implement tightly scoped validation override**

Accept Force Continue only after an action succeeded and its post-action validation failed. Reject it for lease/readiness/session/checkpoint staleness, action failure, cancellation, command conflict or state mismatch. Log command ID, workflow run ID, state, snapshot revision, failure code, measured evidence, thresholds, operator confirmation and timestamp.

- [ ] **Step 6: Verify GREEN and existing workflow regressions**

```bash
colcon test --packages-select so101_gazebo_demo \
  --ctest-args -R '(transition_table|pick_place_runner|physical_grasp_validator|pick_place)'
pytest -q src/so101_gazebo_demo/test/teleop/test_workflow_gateway.py
colcon test-result --verbose
```

- [ ] **Step 7: Commit**

```bash
git add src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place \
  src/so101_gazebo_demo/src/pick_place \
  src/so101_gazebo_demo/so101_teleop/workflow_gateway.py \
  src/so101_gazebo_demo/test/pick_place \
  src/so101_gazebo_demo/test/teleop/test_workflow_gateway.py
git commit -m "feat(so101): validate and step physical grasps"
```

### Task 8: Gazebo-Only Screenshot Adapter

**Files:**
- Create: `so101_teleop/screenshot.py`, `test/teleop/test_screenshot.py`

**Interfaces:**
- Produces: `GazeboScreenshot.capture() -> ScreenshotResult` containing PNG bytes, timestamp, outer geometry and session ID.

- [ ] **Step 1: Write failing uniqueness and geometry tests**

```python
def test_ambiguous_gazebo_windows_are_rejected():
    with pytest.raises(ScreenshotError, match="GAZEBO_WINDOW_AMBIGUOUS"):
        GazeboScreenshot(fake_windows([GAZEBO_A, GAZEBO_B])).capture()

def test_exact_window_region_becomes_png():
    result = GazeboScreenshot(fake_windows([GAZEBO_A])).capture()
    assert result.geometry == Rect(66, 32, 3774, 2128)
    assert result.png.startswith(b"\x89PNG")
```

- [ ] **Step 2: Verify RED**

```bash
pytest -q src/so101_gazebo_demo/test/teleop/test_screenshot.py
```

- [ ] **Step 3: Implement capture using existing Gazebo WM_CLASS rules**

Reuse the window classification semantics from `tile_ai_station_guis.py`, include frame extents, and return bytes without writing to the source tree. Do not depend on RViz or Ghostty being open.

- [ ] **Step 4: Verify GREEN and tiling regression**

```bash
pytest -q src/so101_gazebo_demo/test/teleop/test_screenshot.py \
  src/so101_gazebo_demo/test/test_tile_ai_station_guis.py
```

- [ ] **Step 5: Commit**

```bash
git add src/so101_gazebo_demo/so101_teleop/screenshot.py \
  src/so101_gazebo_demo/test/teleop/test_screenshot.py
git commit -m "feat(so101): capture Gazebo teleop screenshots"
```

### Task 9: Application Service and FastAPI Contract

**Files:**
- Create: `so101_teleop/service.py`, `so101_teleop/api.py`, `so101_teleop/openapi_export.py`
- Create: `test/teleop/test_service.py`, `test/teleop/test_api.py`
- Create: `so101_teleop/openapi.json`

**Interfaces:**
- Produces: all REST/WebSocket endpoints in the approved design and deterministic OpenAPI.
- Consumes: lease/coordinator/plan store, telemetry, MoveIt, scene, workflow and screenshot gateways.

- [ ] **Step 1: Write failing API tests**

```python
def test_unsafe_bind_is_rejected():
    with pytest.raises(ValueError, match="BIND_ADDRESS_UNSAFE"):
        validate_bind_address("0.0.0.0")

def test_execute_rejects_stale_plan(client):
    response = client.post("/plans/p1/execute", json=EXECUTE_BODY)
    assert response.status_code == 409
    assert response.json()["code"] == "PLAN_STALE_SCENE"
```

Also cover readiness mutation gates, lease requirements, duplicate command IDs, PNG headers, increasing telemetry sequences and disconnect cancellation.
Cover `/workflow/start|step|run|stop|reset|force-continue`, including no arbitrary-state input, stopping on validation failure, one-shot override consumption and immutable override audit evidence.

- [ ] **Step 2: Verify RED**

```bash
pytest -q src/so101_gazebo_demo/test/teleop/test_service.py \
  src/so101_gazebo_demo/test/teleop/test_api.py
```

- [ ] **Step 3: Implement routes and stable error envelopes**

Use 409 for lease/busy/stale-plan conflicts and 503 for readiness failures. Every mutation returns `CommandResult`; HTTP success alone never denotes robot success.

- [ ] **Step 4: Export OpenAPI twice and verify determinism**

```bash
source install/setup.zsh
python3 -m so101_teleop.openapi_export \
  src/so101_gazebo_demo/so101_teleop/openapi.json
cp src/so101_gazebo_demo/so101_teleop/openapi.json /tmp/so101-openapi-first.json
python3 -m so101_teleop.openapi_export \
  src/so101_gazebo_demo/so101_teleop/openapi.json
diff -u /tmp/so101-openapi-first.json \
  src/so101_gazebo_demo/so101_teleop/openapi.json
pytest -q src/so101_gazebo_demo/test/teleop/test_service.py \
  src/so101_gazebo_demo/test/teleop/test_api.py
```

- [ ] **Step 5: Commit**

```bash
git add src/so101_gazebo_demo/so101_teleop/{service.py,api.py,openapi_export.py} \
  src/so101_gazebo_demo/test/teleop/{test_service.py,test_api.py} \
  src/so101_gazebo_demo/so101_teleop/openapi.json
git commit -m "feat(so101): expose teleop API"
```

### Task 10: Server Entrypoint, Launch, and Static Hosting

**Files:**
- Create: `so101_teleop/main.py`, `scripts/so101_teleop_server.py`
- Create: `launch/so101_teleop.launch.py`, `config/so101_teleop.yaml`
- Modify: `CMakeLists.txt`, `package.xml`, `test/test_package_layout.py`, `test/test_so101_launch_contract.py`

**Interfaces:**
- Produces: `ros2 run so101_gazebo_demo so101_teleop_server.py` and a launch entry with explicit `bind_address`.

- [ ] **Step 1: Write failing launch/install tests**

Assert an explicit bind address, `simulation_only=true`, configurable world/TCP/topic names, installed executable and optional installed `teleop_web` directory.

- [ ] **Step 2: Verify RED**

```bash
pytest -q src/so101_gazebo_demo/test/test_package_layout.py \
  src/so101_gazebo_demo/test/test_so101_launch_contract.py
```

- [ ] **Step 3: Implement process lifecycle and asset fallback**

Install `web/dist/` when present. If assets are absent, `/health` remains usable and `/` returns `WEB_ASSETS_NOT_BUILT`. The wrapper starts the ROS worker before Uvicorn and shuts both down on SIGINT/SIGTERM.

- [ ] **Step 4: Build and prove installed entrypoints**

```bash
colcon build --packages-select so101_gazebo_demo --symlink-install
source install/setup.zsh
ros2 pkg executables so101_gazebo_demo | rg so101_teleop_server
ros2 launch so101_gazebo_demo so101_teleop.launch.py --show-args
```

- [ ] **Step 5: Commit**

```bash
git add src/so101_gazebo_demo/so101_teleop/main.py \
  src/so101_gazebo_demo/scripts/so101_teleop_server.py \
  src/so101_gazebo_demo/launch/so101_teleop.launch.py \
  src/so101_gazebo_demo/config/so101_teleop.yaml \
  src/so101_gazebo_demo/{CMakeLists.txt,package.xml} \
  src/so101_gazebo_demo/test/{test_package_layout.py,test_so101_launch_contract.py}
git commit -m "feat(so101): launch teleop server"
```

### Task 11: Vite and shadcn/ui Frontend Foundation

**Files:**
- Create: `web/package.json`, `web/package-lock.json`, `web/components.json`, `web/vite.config.ts`
- Create: `web/src/main.tsx`, `web/src/app.tsx`, `web/src/api/schema.d.ts`, `web/src/api/client.ts`, `web/src/state/teleop-store.tsx`
- Test: `web/src/state/teleop-store.test.tsx`

**Interfaces:**
- Produces: typed `TeleopApi`, `TelemetryProvider`, Actual/Target store and `web/dist`.
- Consumes: `../so101_teleop/openapi.json`.

- [ ] **Step 1: Initialize the exact preset in `web/`**

```bash
cd /data/work/ws_moveit/src/so101_gazebo_demo
npx shadcn@latest init --name web --preset bKsFBxgG --template vite
```

Keep npm as package manager through `package-lock.json`.

- [ ] **Step 2: Read current component docs, then add only required components**

```bash
cd web
npx shadcn@latest docs button card field toggle-group tabs table badge alert \
  alert-dialog sonner skeleton collapsible scroll-area input select
npx shadcn@latest add button card field toggle-group tabs table badge alert \
  alert-dialog sonner skeleton collapsible scroll-area input select
```

- [ ] **Step 3: Write a failing Actual/Target separation test**

```tsx
it("does not overwrite an edited target when telemetry arrives", () => {
  const edited = reduce(INITIAL, editJointTarget("2", 0.5))
  const next = reduce(edited, telemetryReceived(NEW_ACTUAL))
  expect(next.actual.joints["2"]).toBe(NEW_ACTUAL.joints["2"])
  expect(next.target.joints["2"]).toBe(0.5)
})
```

- [ ] **Step 4: Generate API types and implement store/client**

```bash
npx openapi-typescript ../so101_teleop/openapi.json -o src/api/schema.d.ts
npm test -- --run src/state/teleop-store.test.tsx
npm run build
```

Reject non-increasing WebSocket sequence numbers and mark Actual stale after the schema-defined timeout.

- [ ] **Step 5: Commit**

```bash
git add src/so101_gazebo_demo/web
git commit -m "feat(so101): scaffold teleop web console"
```

### Task 12: Joint, TCP, Plan, and Execute UI

**Files:**
- Create: `web/src/lib/units.ts`
- Create: `web/src/components/teleop/connection-header.tsx`, `joint-panel.tsx`, `tcp-panel.tsx`, `plan-panel.tsx`
- Create: matching `*.test.tsx` files
- Modify: `web/src/app.tsx`

**Interfaces:**
- Produces: fixed increments, Current-to-Target, Plan Joint/TCP, Execute Latest, Execute Gripper/All and Stop.

- [ ] **Step 1: Write failing interactions**

```tsx
it("increments TCP Y by exactly one millimetre", async () => {
  await user.click(screen.getByRole("button", { name: "Y +1 mm" }))
  expect(store.target.tcp.y_m).toBeCloseTo(startY + 0.001, 12)
})
```

Also assert `Math.PI / 180` joint/RPY steps, World/Tool payloads, q6 separation, stale-plan disablement and visible disabled reasons.

- [ ] **Step 2: Verify RED**

```bash
cd src/so101_gazebo_demo/web
npm test -- --run src/components/teleop
```

- [ ] **Step 3: Implement with shadcn composition rules**

Use `FieldGroup`/`Field`, `ToggleGroup`, full `Card` composition, semantic `Badge`, and `Alert`. Do not use raw color classes, `space-y-*`, or hand-built active button loops.

- [ ] **Step 4: Verify GREEN and build**

```bash
npm test -- --run src/components/teleop
npm run build
```

- [ ] **Step 5: Commit**

```bash
git add src/so101_gazebo_demo/web/src
git commit -m "feat(so101): add teleop motion controls"
```

### Task 13: Objects, Collisions, Screenshot, Reset, YAML, and Workflow UI

**Files:**
- Create: `web/src/lib/target-yaml.ts` and its test
- Create: `web/src/components/teleop/object-panel.tsx`, `collision-panel.tsx`, `gazebo-panel.tsx`, `reset-controls.tsx`, `workflow-panel.tsx`, `event-log.tsx`
- Create: matching `*.test.tsx` files
- Modify: `web/src/app.tsx`

**Interfaces:**
- Produces: Attach/Detach, Repair, Home, Reset, screenshot/download, collision/contact tables, Target YAML, pick-place Step/Run/Stop/Reset/Force Continue and diagnostic snapshot.

- [ ] **Step 1: Write failing confirmation, evidence, and YAML tests**

```tsx
it("keeps MoveIt collisions separate from Gazebo contacts", () => {
  render(<CollisionPanel moveit={MOVEIT_ROWS} gazebo={GAZEBO_ROWS} />)
  expect(within(screen.getByLabelText("MoveIt collisions")).getByText("jaw")).toBeVisible()
  expect(within(screen.getByLabelText("Gazebo contacts")).getByText("solver-reported")).toBeVisible()
})
```

Assert Reset/Attach/Detach confirmation, PNG download MIME type, and a YAML round trip that contains every Target field and no Actual telemetry.

```tsx
it("offers force continue only for the current validation failure", async () => {
  render(<WorkflowPanel snapshot={VALIDATION_FAILED} />)
  expect(screen.getByRole("button", { name: "Force Continue" })).toBeVisible()
  expect(screen.getByText("PHYSICAL_GRASP_FAILED")).toBeVisible()
})
```

Also assert legal Next Step labels come from server telemetry, Run stops on a validation failure, workflow reset does not reset the Gazebo world, and the force dialog displays evidence/thresholds plus typed confirmation.

- [ ] **Step 2: Verify RED**

```bash
npm test -- --run src/components/teleop src/lib/target-yaml.test.ts
```

- [ ] **Step 3: Implement remaining panels**

Use `Table`, `AlertDialog`, `Sonner`, `Skeleton`, `Collapsible` and `ScrollArea`; keep advanced one-sided scene commands collapsed and double-confirmed. Render the server-provided workflow trace and next state; do not duplicate the transition table in TypeScript. Mark every forced transition in the trace and event log.

- [ ] **Step 4: Verify all frontend tests and build**

```bash
npm test -- --run
npm run build
```

- [ ] **Step 5: Commit**

```bash
git add src/so101_gazebo_demo/web/src
git commit -m "feat(so101): add teleop scene monitoring"
```

### Task 14: Full Build, Live Validation, and Operator Documentation

**Files:**
- Create: `docs/so101-teleop-web-ui.md`
- Modify: `README.md`
- Modify: `CMakeLists.txt` only if installed static-asset verification exposes a missing rule

**Interfaces:**
- Produces: installed, documented, Tailscale-reachable and visually verified tool.

- [ ] **Step 1: Run complete automated verification**

```bash
cd /data/work/ws_moveit/src/so101_gazebo_demo/web
npm ci
npm test -- --run
npm run build
cd /data/work/ws_moveit
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_gazebo_demo --symlink-install
source install/setup.zsh
PYTHONNOUSERSITE=1 colcon test --packages-select so101_gazebo_demo \
  --event-handlers console_direct+
colcon test-result --verbose
```

- [ ] **Step 2: Start exactly one tmux-held GUI stack and server**

Source `~/gui-env.zsh`, Jazzy and the installed overlay. Use unique ROS domain, Gazebo partition, simulation session ID and `/tmp/so101-debug-<run-id>/`. Pass the current ai-station Tailscale IP explicitly as `bind_address`.

- [ ] **Step 3: Verify read-only telemetry and Gazebo-only screenshot**

From the Mac browser, verify joints 1-6, TCP, controllers, object pose, attachment, Planning Scene, RTF, RTT and data age. Confirm downloaded PNG contains only the unique maximized Gazebo window.

- [ ] **Step 4: Verify increments and stale-plan behavior**

Record before/target/after values for joint +1/-1 degree, TCP World X +1 mm, Tool Z +1 mm, World yaw +1 degree and Tool pitch +1 degree. Edit Target after Plan and prove Execute is disabled with `PLAN_STALE_TARGET`.

- [ ] **Step 5: Verify collisions, physical grasp, workflow and transactions**

Create but do not execute a safe colliding target and verify object/link names. Then execute the workflow one state at a time through Close, both stable gates, the 1 mm Micro Lift and physical-grasp verification. Prove that Attach occurs only afterward. Compare TCP/cup Z delta, table clearance, cup-follow ratio and XY slip against the UI evidence. Continue through Lift/Place, then verify Run/Stop/resume, arm Execute, q6 Execute, Execute All, Cancel, Detach, Repair, Home and Reset with Gazebo, MoveIt, controller and joint/TF evidence.

- [ ] **Step 6: Verify Force Continue boundaries**

In a disposable simulation run, create a validation-only failure, confirm normal Step stops, then use the double-confirmed override and prove it advances exactly one state with an audit marker. Separately prove action failure, stale checkpoint/session, lost lease and unavailable controller remain blocked. Reset after the forced run; do not use its result as physical-grasp success evidence.

- [ ] **Step 7: Capture final evidence and clean only owned processes**

Save fresh browser and Gazebo screenshots, command exit codes and process/node lists. Stop only this run's tmux panes/PIDs and recheck that no duplicate Gazebo, MoveIt or teleop server remains.

- [ ] **Step 8: Write operator documentation**

Document dependencies, frontend build, colcon build, Tailscale binding, tmux launch, URL, lease, every operation, YAML schema, workflow/checkpoint semantics, physical-grasp metrics, failure codes, force-continue boundaries/audit meaning and clean shutdown. State simulation-only and distinguish an overridden workflow from a validated physical grasp.

- [ ] **Step 9: Commit documentation**

```bash
git add src/so101_gazebo_demo/docs/so101-teleop-web-ui.md \
  src/so101_gazebo_demo/README.md src/so101_gazebo_demo/CMakeLists.txt
git commit -m "docs(so101): document teleop web console"
```
