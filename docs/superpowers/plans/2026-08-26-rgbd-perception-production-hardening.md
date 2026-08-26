# RGB-D Perception Pick-Place Production Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the five final-review gaps without changing perception or manipulation behavior, then requalify all four frozen MuJoCo keyframes under the hardened implementation provenance.

**Architecture:** Extend the existing launch status seam rather than adding a supervisor, validate MuJoCo identity before constructing the mutable Planning Scene port, and allocate each session evidence root atomically. Keep the public CLI and accepted data flow unchanged; use focused failure-injection tests before each minimal implementation and freeze the final code commit before new physical runs.

**Tech Stack:** Python 3.12, ROS 2 Jazzy launch/rclpy, pytest, Ruff, ament/colcon, MuJoCo ROS 2 control, MoveIt 2, rosdep, zsh, jq, cua-driver.

**Spec:** `docs/superpowers/specs/2026-08-26-rgbd-perception-production-hardening-design.md`

## Global Constraints

- Work only in `/data/work/ws_moveit/.worktrees/rgbd-perception-pick-place` on `codex/rgbd-perception-pick-place`; canonical main at `/data/work/ws_moveit` must remain untouched.
- Use the registered evidence root `/tmp/so101-debug-rgbd-perception-pick-place-20260826/`; do not create `/data/work/so101-debug-*` and do not delete evidence without explicit user authorization.
- Keep gitlink and submodule HEAD exactly `f19a8cc3af61feccacb22a9f0d16cc972e3b2c08` (`so101-0.0.3-r8-3-gf19a8cc`); do not reuse r6 or retry the superseded failed fetch route.
- Preserve CP-016 and EXP-017 through EXP-020 as immutable history. New code provenance requires EXP-021 through EXP-024.
- Do not change segmentation, point-cloud, cylinder-fit, pose transform, confidence, policy, thresholds, keyframes, geometry, grasp, attachment, placement, or recovery behavior.
- Do not run `ament_uncrustify --reformat`; formatting edits must be targeted and `ruff format --check` is read-only.
- Use standard Git against the Gitee `origin`; do not use `gh`.
- Source `/opt/ros/jazzy/setup.zsh`, then the task overlay. Prepend the task-owned Python dependency directory only for Python tests and ROS runtime verification that imports Open3D; do not prepend it for `colcon build`, because its newer setuptools is a runtime dependency and is incompatible with the ROS build's legacy `setup.py develop --uninstall` path:

```zsh
source /opt/ros/jazzy/setup.zsh
source /tmp/so101-debug-rgbd-perception-pick-place-20260826/ai-station-overlay/install/setup.zsh
export PYTHONPATH=/tmp/so101-debug-rgbd-perception-pick-place-20260826/ai-station-overlay/python-deps:$PYTHONPATH
```

---

## File map

- `src/so101_demo_py/src/runtime/launch_composition.py`: owns MuJoCo launch actions, process-exit status, and evidence-directory allocation.
- `src/so101_demo_py/test/test_perception_pick_place_launch.py`: deterministic launch graph, handler dispatch, and path-safety regressions.
- `src/so101_demo_py/test/test_perception_launch_runner.py`: real LaunchService return-code propagation.
- `src/so101_demo_py/src/ports/cup_scene_observation.py`: backend-neutral immutable observation contract.
- `src/so101_demo_py/src/application/cup_pose_preflight.py`: pure session/epoch/paused and pose consistency gates.
- `src/so101_demo_py/src/ros/cup_scene_observer.py`: Gazebo and MuJoCo read-only adapters.
- `src/so101_demo_py/src/ros/dynamic_runtime.py`: orders perception, truth preflight, Planning Scene mutation, and motion construction.
- `src/so101_demo_py/test/test_cup_pose_preflight.py`: pure identity validation tests.
- `src/so101_demo_py/test/test_dynamic_scene_sync.py`: orchestration order and zero-scene-mutation regressions.
- `src/so101_demo_py/test/test_installed_provenance.py`: installed executable closure.
- `src/so101_demo_py/test/test_mujoco_camera_plugin_contract.py`: source package metadata contract for the MuJoCo support consumer.
- `src/so101_mujoco_support/package.xml`: declares the rosdep-resolvable OpenGL/EGL build contract.
- `docs/experiments/mujoco-rgbd-perception-pick-place-experiment-ledger.md`: additive transitions, checkpoints, closures, and final evidence disposition.

### Task 1: Preserve required-process exit status

**Files:**

- Modify: `src/so101_demo_py/src/runtime/launch_composition.py:52-334`
- Modify: `src/so101_demo_py/test/test_perception_pick_place_launch.py:150-390`
- Modify: `src/so101_demo_py/test/test_perception_launch_runner.py:20-75`

**Interfaces:**

- Consumes: existing `PerceptionLaunchExitStatus.record(int)`, `resolve(int)`, `OnProcessExit`, and `_terminal_launch_actions(reason, failed)`.
- Produces: `_MujocoStackActions` fields for every process role; `PerceptionLaunchExitStatus.mark_workflow_terminal()` and `workflow_terminal`; `perception_pick_place_exit_handlers(scene_setup, perception, workflow, *, required_long_lived, successful_one_shots, exit_status)`.

- [ ] **Step 1: Add failing launch-policy tests**

Extend the test helper so all initially started nodes and both camera TF nodes can be dispatched. Add these cases:

```python
@pytest.mark.parametrize(
    ("executable", "label"),
    (
        ("ros2_control_node", "MuJoCo runtime"),
        ("robot_state_publisher", "robot_state_publisher"),
        ("so101_move_group", "MoveIt move_group"),
        ("static_transform_publisher", "camera static TF"),
    ),
)
def test_required_long_lived_exit_before_workflow_is_terminal(
    tmp_path: Path, executable: str, label: str
) -> None:
    context, actions, exit_status = _materialize(evidence_file=tmp_path / "run.json")
    target = next(node for node in _nodes(actions) if node.node_executable == executable)

    emitted = _dispatch_process_exit(actions, target, 17, context)

    assert exit_status.returncode == 17
    assert any(label in reason for reason in _shutdown_reasons(emitted))
    _assert_failure_status(emitted, context, "exit code 17")


def test_unexpected_clean_required_exit_normalizes_to_one(tmp_path: Path) -> None:
    context, actions, exit_status = _materialize(evidence_file=tmp_path / "run.json")
    simulator = _node(actions, "ros2_control_node")

    emitted = _dispatch_process_exit(actions, simulator, 0, context)

    assert exit_status.returncode == 1
    _assert_failure_status(emitted, context, "exit code 0")


@pytest.mark.parametrize("returncode", (0, 19))
def test_controller_spawner_exit_policy(tmp_path: Path, returncode: int) -> None:
    context, actions, exit_status = _materialize(evidence_file=tmp_path / "run.json")
    spawner = next(node for node in _nodes(actions) if node.node_executable == "spawner")

    emitted = _dispatch_process_exit(actions, spawner, returncode, context)

    if returncode == 0:
        assert emitted == []
    else:
        assert exit_status.returncode == 19
        _assert_failure_status(emitted, context, "exit code 19")


def test_first_terminal_process_status_wins(tmp_path: Path) -> None:
    context, actions, exit_status = _materialize(evidence_file=tmp_path / "run.json")
    _dispatch_process_exit(actions, _node(actions, "ros2_control_node"), 31, context)
    _dispatch_process_exit(actions, _node(actions, "so101_move_group"), 41, context)
    assert exit_status.returncode == 31
```

Adapt `_materialize()` to instantiate a `PerceptionLaunchExitStatus`, pass it into the builder, and return `(context, actions, exit_status)`. Update existing callers to unpack the third value. Also add a teardown test that first dispatches workflow exit `0`, then dispatches every required long-lived node with `-15`, asserting each later emission is empty and status remains `0`.

- [ ] **Step 2: Run the focused tests and retain RED**

```zsh
python3 -m pytest \
  src/so101_demo_py/test/test_perception_pick_place_launch.py \
  src/so101_demo_py/test/test_perception_launch_runner.py -q
```

Expected: failure because simulator/RSP/move_group/static-TF/spawner exits have no registered status-preserving policy and simulator still owns a direct shutdown action. Save output and exit code under `final-hardening/task-1-red/` in the registered evidence root.

- [ ] **Step 3: Expose the process roles and terminal workflow state**

Replace the opaque stack tuple with explicit fields and a computed action order:

```python
@dataclass(frozen=True, slots=True)
class _MujocoStackActions:
    robot_state_publisher: Node
    simulator: Node
    spawners: tuple[Node, ...]
    move_group: Node
    scene_setup: Node

    @property
    def actions(self) -> tuple:
        return (
            self.robot_state_publisher,
            self.simulator,
            *self.spawners,
            self.move_group,
            self.scene_setup,
        )
```

Remove `on_exit=Shutdown(reason="MuJoCo runtime exited")` from the simulator. Extend `PerceptionLaunchExitStatus` exactly as follows:

```python
workflow_terminal: bool = False

def mark_workflow_terminal(self) -> None:
    self.workflow_terminal = True
```

- [ ] **Step 4: Implement shared one-shot and long-lived handlers**

Change `perception_pick_place_exit_handlers` to accept:

```python
def perception_pick_place_exit_handlers(
    scene_setup,
    perception,
    workflow,
    *,
    required_long_lived: tuple[tuple[str, object], ...],
    successful_one_shots: tuple[tuple[str, object], ...],
    exit_status: PerceptionLaunchExitStatus,
):
```

For each long-lived role, register a closure that returns `[]` after `workflow_terminal`, otherwise records `event.returncode if event.returncode != 0 else 1` and calls `_terminal_launch_actions` with `failed=True`. For each controller spawner, return `[]` on zero; otherwise record the exact nonzero status and terminate. Keep scene setup special because zero starts perception and workflow. In the workflow closure call `mark_workflow_terminal()` before `record(event.returncode)`.

In `_mujoco_perception_execute_actions`, materialize `camera_transforms = tuple(camera_static_transform_nodes())`, pass these required roles:

```python
required_long_lived=(
    ("MuJoCo runtime", stack.simulator),
    ("robot_state_publisher", stack.robot_state_publisher),
    ("MoveIt move_group", stack.move_group),
    *((f"camera static TF {index}", node) for index, node in enumerate(camera_transforms, 1)),
    ("RGB-D perception", perception),
)
successful_one_shots=tuple(
    (f"controller spawner {_CONTROLLERS[index]}", node)
    for index, node in enumerate(stack.spawners)
)
```

Return `camera_transforms` once, followed by `stack.actions`; do not duplicate any node.
Update the real LaunchService fixture to pass empty tuples for the two new role collections because its synthetic perception process already receives the dedicated required-process policy.

- [ ] **Step 5: Run focused and launch-adjacent tests**

```zsh
python3 -m pytest \
  src/so101_demo_py/test/test_launch_composition.py \
  src/so101_demo_py/test/test_perception_pick_place_launch.py \
  src/so101_demo_py/test/test_perception_launch_runner.py \
  src/so101_demo_py/test/test_camera_tf_contract.py -q
```

Expected: all pass, including exact nonzero propagation, unexpected-zero normalization, successful spawner exits, workflow-owned teardown, and first-failure-wins.

- [ ] **Step 6: Commit the lifecycle boundary**

```zsh
git add src/so101_demo_py/src/runtime/launch_composition.py \
  src/so101_demo_py/test/test_perception_pick_place_launch.py \
  src/so101_demo_py/test/test_perception_launch_runner.py
git commit -m "fix: preserve required launch process failures"
```

### Task 2: Reject stale or paused MuJoCo identity before scene mutation

**Files:**

- Modify: `src/so101_demo_py/src/ports/cup_scene_observation.py:13-23`
- Modify: `src/so101_demo_py/src/application/cup_pose_preflight.py:12-70`
- Modify: `src/so101_demo_py/src/ros/cup_scene_observer.py:103-175`
- Modify: `src/so101_demo_py/src/ros/dynamic_runtime.py:255-325`
- Modify: `src/so101_demo_py/test/test_cup_pose_preflight.py:8-35`
- Modify: `src/so101_demo_py/test/test_dynamic_scene_sync.py:21-45,414-570`

**Interfaces:**

- Consumes: `SimulationEvidence.simulation_session_id`, `.reset_epoch`, `.paused`; existing `CupPosePreflightError.code`; `options.session_id` and `options.expected_reset_epoch`.
- Produces: optional identity fields on `CupSceneObservation`; `validate_mujoco_scene_identity(observation, *, expected_session_id, expected_reset_epoch) -> None`; `RosMujocoCupSceneObserver(node, session_id, expected_reset_epoch)`.

- [ ] **Step 1: Add pure identity RED tests**

Update the dynamic-test `_observation()` helper to default to session `task-5`, epoch `3`, and `paused=False`. Add:

```python
@pytest.mark.parametrize(
    ("changes", "code"),
    (
        ({"simulation_session_id": None}, "CUP_POSE_SCENE_IDENTITY_MISSING"),
        ({"reset_epoch": None}, "CUP_POSE_SCENE_IDENTITY_MISSING"),
        ({"paused": None}, "CUP_POSE_SCENE_IDENTITY_MISSING"),
        ({"simulation_session_id": "other"}, "CUP_POSE_SCENE_SESSION_MISMATCH"),
        ({"reset_epoch": 4}, "CUP_POSE_SCENE_RESET_EPOCH_MISMATCH"),
        ({"paused": True}, "CUP_POSE_SCENE_PAUSED"),
    ),
)
def test_mujoco_identity_gate_rejects_invalid_truth(changes, code) -> None:
    observation = replace(_observation(), **changes)
    with pytest.raises(CupPosePreflightError) as caught:
        validate_mujoco_scene_identity(
            observation,
            expected_session_id="task-5",
            expected_reset_epoch=3,
        )
    assert caught.value.code == code
```

- [ ] **Step 2: Add orchestration RED proving zero scene calls**

Parameterize invalid first observations in `test_dynamic_scene_sync.py`. Assert return `1`, the expected stable failure code is printed, and all of these are absent:

```python
assert "task_scene.create" not in events
assert "task_scene.apply" not in events
assert "targets.resolve" not in events
assert scene.calls == []
```

Update `observer_factory` to require `(node, session_id, expected_reset_epoch)` and assert `(session_id, expected_reset_epoch) == ("task-5", 3)`.

- [ ] **Step 3: Run RED tests**

```zsh
python3 -m pytest \
  src/so101_demo_py/test/test_cup_pose_preflight.py \
  src/so101_demo_py/test/test_dynamic_scene_sync.py -q
```

Expected: failures because `CupSceneObservation` lacks the fields, the helper is absent, and the observer factory receives only two arguments. Retain output under `final-hardening/task-2-red/`.

- [ ] **Step 4: Extend the observation and implement the pure gate**

Append defaults so existing Gazebo positional construction remains valid:

```python
simulation_session_id: str | None = None
reset_epoch: int | None = None
paused: bool | None = None
```

Implement `validate_mujoco_scene_identity` with this exact validation order: any missing field, session mismatch, epoch mismatch, paused. Raise `CupPosePreflightError` with the four codes used above and include expected/observed values in messages.

- [ ] **Step 5: Wire adapter and runtime before mutation**

Change the MuJoCo observer constructor to store `expected_reset_epoch`. Populate the returned observation with:

```python
simulation_session_id=str(evidence.simulation_session_id),
reset_epoch=int(evidence.reset_epoch),
paused=bool(evidence.paused),
```

Before requesting MoveIt readback, the adapter must also reject evidence whose session ID differs, whose epoch differs, or whose `paused` value is true, using the same stable failure codes. This makes the adapter use both constructor arguments and lets the runtime-level pure gate remain defense in depth.

In `run_dynamic_execute`:

```python
truth_observer = runtime.cup_scene_observer(
    node, options.session_id, options.expected_reset_epoch
)
initial = truth_observer.observe(5.0)
validate_mujoco_scene_identity(
    initial,
    expected_session_id=options.session_id,
    expected_reset_epoch=options.expected_reset_epoch,
)
task_scene = runtime.task_scene_port(
    node,
    "mujoco",
    loaded.template.planning_timeout_s,
)
```

The validation call must precede `task_scene_port`; pose convergence and motion construction retain their current order.

- [ ] **Step 6: Run identity, scene-sync, and adapter-adjacent tests**

```zsh
python3 -m pytest \
  src/so101_demo_py/test/test_cup_pose_preflight.py \
  src/so101_demo_py/test/test_dynamic_scene_sync.py \
  src/so101_demo_py/test/test_dynamic_execute.py \
  src/so101_demo_py/test/test_mujoco_world_lifecycle_adapter.py -q
```

Expected: all pass and every invalid identity reports zero task-scene calls.

- [ ] **Step 7: Commit the preflight boundary**

```zsh
git add src/so101_demo_py/src/ports/cup_scene_observation.py \
  src/so101_demo_py/src/application/cup_pose_preflight.py \
  src/so101_demo_py/src/ros/cup_scene_observer.py \
  src/so101_demo_py/src/ros/dynamic_runtime.py \
  src/so101_demo_py/test/test_cup_pose_preflight.py \
  src/so101_demo_py/test/test_dynamic_scene_sync.py
git commit -m "fix: gate scene mutation on mujoco identity"
```

### Task 3: Allocate immutable session evidence roots

**Files:**

- Modify: `src/so101_demo_py/src/runtime/launch_composition.py:658-706,735-755`
- Modify: `src/so101_demo_py/test/test_perception_pick_place_launch.py:230-355`

**Interfaces:**

- Consumes: reusable owned `<evidence-stem>.d` container and validated session ID.
- Produces: `_exclusive_owned_directory(path, label) -> Path`; fresh session/perception/dynamic roots or terminal `RuntimeError` without modification.

- [ ] **Step 1: Replace permissive evidence tests with immutability RED tests**

Keep a test proving an existing owned base directory is reusable. Replace `test_evidence_preflight_keeps_valid_preexisting_run_directory` with:

```python
def test_evidence_preflight_rejects_preexisting_session_without_modifying_it(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "result.d/session-123"
    run_root.mkdir(parents=True)
    sentinel = run_root / "accepted.txt"
    sentinel.write_text("immutable", encoding="utf-8")

    with pytest.raises(RuntimeError, match="session evidence root already exists"):
        _materialize(evidence_file=tmp_path / "result.json")

    assert sentinel.read_text(encoding="utf-8") == "immutable"
    assert sorted(path.name for path in run_root.iterdir()) == ["accepted.txt"]


def test_evidence_preflight_rejects_existing_nominal_file(tmp_path: Path) -> None:
    evidence_file = tmp_path / "result.json"
    evidence_file.write_text("accepted", encoding="utf-8")
    with pytest.raises(RuntimeError, match="must not already exist"):
        _materialize(evidence_file=evidence_file)
    assert evidence_file.read_text(encoding="utf-8") == "accepted"
    assert not (tmp_path / "result.d").exists()
```

Update symlink/non-directory cases so a pre-existing session entry is expected to fail as an existing immutable boundary; keep direct base validation tests for symlink, ownership, and non-directory protection.

- [ ] **Step 2: Run the evidence tests and retain RED**

```zsh
python3 -m pytest \
  src/so101_demo_py/test/test_perception_pick_place_launch.py \
  -k evidence_preflight -q
```

Expected: the existing session and nominal file are accepted, causing the new assertions to fail. Retain output under `final-hardening/task-3-red/`.

- [ ] **Step 3: Split reusable validation from exclusive allocation**

Keep `_owned_directory` for the reusable base. Add:

```python
def _exclusive_owned_directory(path: Path, label: str) -> Path:
    try:
        path.mkdir(mode=0o700, exist_ok=False)
    except FileExistsError as error:
        raise RuntimeError(f"{label} already exists: {path}") from error
    return _owned_directory(path, label)
```

Before creating the derived base, use `os.path.lexists(evidence_file)` to reject any existing nominal path, including a broken symlink, with `RuntimeError("evidence_file must not already exist")`. Use `_exclusive_owned_directory` for session, perception, and dynamic directories. Keep containment checks after every resolved path.

- [ ] **Step 4: Run path-safety and launch suites**

```zsh
python3 -m pytest \
  src/so101_demo_py/test/test_perception_pick_place_launch.py \
  src/so101_demo_py/test/test_launch_composition.py -q
```

Expected: all pass; the base remains reusable, while any session/output collision fails without altering existing content.

- [ ] **Step 5: Commit evidence immutability**

```zsh
git add src/so101_demo_py/src/runtime/launch_composition.py \
  src/so101_demo_py/test/test_perception_pick_place_launch.py
git commit -m "fix: reserve perception evidence sessions exclusively"
```

### Task 4: Complete install and OpenGL/EGL metadata contracts

**Files:**

- Modify: `src/so101_demo_py/test/test_installed_provenance.py:13-25`
- Modify: `src/so101_demo_py/test/test_mujoco_camera_plugin_contract.py:1-40`
- Modify: `src/so101_mujoco_support/package.xml:8-22`

**Interfaces:**

- Consumes: installed console script already declared in `setup.py`; CMake's existing `find_package(OpenGL REQUIRED COMPONENTS EGL)`.
- Produces: installed provenance expectation for `so101_mujoco_perception_pick_place`; `<build_depend>opengl</build_depend>`.

- [ ] **Step 1: Add source-level RED expectations**

Add `"so101_mujoco_perception_pick_place"` to `EXPECTED_EXECUTABLES`. Parse the support package in the camera-plugin contract:

```python
def test_support_package_declares_opengl_egl_build_contract() -> None:
    package = ElementTree.parse(PACKAGE.parent / "so101_mujoco_support/package.xml")
    build_dependencies = {
        element.text for element in package.getroot().findall("build_depend")
    }
    assert "opengl" in build_dependencies
```

- [ ] **Step 2: Run source-level RED**

```zsh
python3 -m pytest \
  src/so101_demo_py/test/test_mujoco_camera_plugin_contract.py \
  src/so101_demo_py/test/test_package_identity.py -q
```

Expected: metadata test fails because `opengl` is absent. The installed provenance test is deferred until rebuild because the current overlay already contains the runner.

- [ ] **Step 3: Add the rosdep-resolvable build dependency**

Add this immediately after the buildtool dependencies:

```xml
<build_depend>opengl</build_depend>
```

Do not add raw apt names. ai-station has already established that `rosdep resolve opengl` returns `libgl1-mesa-dev libglu1-mesa-dev`, whose installed dependency chain includes `libglvnd-dev`, `libgl-dev`, and `libegl-dev`.

- [ ] **Step 4: Verify metadata and rosdep resolution**

```zsh
python3 -m pytest src/so101_demo_py/test/test_mujoco_camera_plugin_contract.py -q
rosdep resolve opengl
```

Expected: pytest passes and rosdep prints an `#apt` stanza containing `libgl1-mesa-dev libglu1-mesa-dev`.

- [ ] **Step 5: Commit package contracts**

```zsh
git add src/so101_demo_py/test/test_installed_provenance.py \
  src/so101_demo_py/test/test_mujoco_camera_plugin_contract.py \
  src/so101_mujoco_support/package.xml
git commit -m "fix: declare rgbd runtime install contracts"
```

### Task 5: Integrated source verification and implementation freeze

**Files:**

- Modify: `docs/experiments/mujoco-rgbd-perception-pick-place-experiment-ledger.md`
- Evidence: `/tmp/so101-debug-rgbd-perception-pick-place-20260826/final-hardening/source-verification/`

**Interfaces:**

- Consumes: Tasks 1-4 commits and exact f19 submodule.
- Produces: one frozen `implementation_commit`, rebuilt fresh task overlay, green source gates, additive checkpoint, pushed clean branch.

- [ ] **Step 1: Run focused tests together**

```zsh
python3 -m pytest \
  src/so101_demo_py/test/test_launch_composition.py \
  src/so101_demo_py/test/test_perception_pick_place_launch.py \
  src/so101_demo_py/test/test_perception_launch_runner.py \
  src/so101_demo_py/test/test_cup_pose_preflight.py \
  src/so101_demo_py/test/test_dynamic_scene_sync.py \
  src/so101_demo_py/test/test_dynamic_execute.py \
  src/so101_demo_py/test/test_installed_provenance.py \
  src/so101_demo_py/test/test_mujoco_camera_plugin_contract.py -q
```

Expected: all pass from the correctly sourced environment.

- [ ] **Step 2: Run the complete Python suite and static checks**

```zsh
python3 -m pytest src/so101_demo_py/test -q
ruff check \
  src/so101_demo_py/src/runtime/launch_composition.py \
  src/so101_demo_py/src/ports/cup_scene_observation.py \
  src/so101_demo_py/src/application/cup_pose_preflight.py \
  src/so101_demo_py/src/ros/cup_scene_observer.py \
  src/so101_demo_py/src/ros/dynamic_runtime.py \
  src/so101_demo_py/test/test_perception_pick_place_launch.py \
  src/so101_demo_py/test/test_perception_launch_runner.py \
  src/so101_demo_py/test/test_cup_pose_preflight.py \
  src/so101_demo_py/test/test_dynamic_scene_sync.py \
  src/so101_demo_py/test/test_installed_provenance.py \
  src/so101_demo_py/test/test_mujoco_camera_plugin_contract.py
ruff format --check \
  src/so101_demo_py/src/runtime/launch_composition.py \
  src/so101_demo_py/src/ports/cup_scene_observation.py \
  src/so101_demo_py/src/application/cup_pose_preflight.py \
  src/so101_demo_py/src/ros/cup_scene_observer.py \
  src/so101_demo_py/src/ros/dynamic_runtime.py
```

Expected: at least the prior 375 tests plus new regressions pass; Ruff returns zero. Do not change code merely to reduce the count.

- [ ] **Step 3: Rebuild the dependency-closed six task packages into the registered overlay**

```zsh
colcon --log-base /tmp/so101-debug-rgbd-perception-pick-place-20260826/ai-station-overlay/log-hardening \
  build \
  --base-paths third_party/mujoco_ros2_control src \
  --build-base /tmp/so101-debug-rgbd-perception-pick-place-20260826/ai-station-overlay/build \
  --install-base /tmp/so101-debug-rgbd-perception-pick-place-20260826/ai-station-overlay/install \
  --symlink-install \
  --packages-select \
    mujoco_ros2_control_msgs \
    so101_teleop \
    mujoco_ros2_control_plugins \
    mujoco_ros2_control \
    so101_mujoco_support \
    so101_demo_py
```

Expected: six packages finish successfully and no selected prefix resolves to `/opt/ros/jazzy`. Run this build from the ROS/overlay environment without the task Open3D dependency directory on `PYTHONPATH`.

- [ ] **Step 4: Verify installed runner and ROS argument passthrough**

```zsh
ros2 pkg executables so101_demo_py | rg '^so101_demo_py so101_mujoco_perception_pick_place$'
ros2 run so101_demo_py rgbd_cup_pose --help
ros2 run so101_demo_py dynamic_cup_pick_place --help
```

Expected: all return zero; the first command prints exactly one matching executable. The perception launch runner intentionally has no argparse help surface: passing `--help` to it enters the launch contract and correctly fails closed because execution was not explicitly authorized. Its installed presence and provenance are covered by the executable readback and installed-provenance test; the two argparse CLIs exercise application-argument passthrough without starting the simulator.

- [ ] **Step 5: Freeze provenance and append the source checkpoint**

Record the current code HEAD as `implementation_commit`. Append a checkpoint containing test totals, build exit, six prefixes, rosdep output, Ruff results, exact gitlink/submodule, canonical main, and clean owned-runtime scan. State explicitly that EXP-017 through EXP-020 remain historical-only for `a8b3d87a`, and EXP-021 is next.

- [ ] **Step 6: Commit, push, and read back the freeze**

```zsh
git add docs/experiments/mujoco-rgbd-perception-pick-place-experiment-ledger.md
git commit -m "docs: freeze rgbd hardening provenance"
git push origin codex/rgbd-perception-pick-place
git ls-remote origin refs/heads/codex/rgbd-perception-pick-place
```

Expected: remote hash equals local HEAD; task tree and submodule are clean; canonical main remains `b3770360b26fe8f6fac0e19338d250b6f5cab0e7`.

### Task 6: Accept EXP-021 at `task_start`

**Files:**

- Modify twice: `docs/experiments/mujoco-rgbd-perception-pick-place-experiment-ledger.md`
- Evidence: `/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-021/`

**Interfaces:**

- Consumes: frozen implementation, helper scripts `helpers/full-restart.zsh` and `helpers/capture-coordinator.zsh`, `$ai-station-gui`, and `$cua-driver` strict window session.
- Produces: one independent accepted FULL_RESTART run or one retained invalid/blocked closure; never silently retries the same experiment ID.

- [ ] **Step 1: Prove isolation and append PLANNED -> RUNNING**

Use domain `199`, runtime session `rgbd-pick-task-start-exp021-20260826`, CUA session `rgbd-pick-exp021-viewer-20260826`, and keyframe `task_start`. Verify domain nodes, exact process arguments, tmux names, exact Viewer title, and the new evidence paths are absent. Append and commit the RUNNING transition before launch.

- [ ] **Step 2: Start strict-window capture and the full restart concurrently**

```zsh
cua-driver start_session '{"session":"rgbd-pick-exp021-viewer-20260826","capture_scope":"window"}'
/tmp/so101-debug-rgbd-perception-pick-place-20260826/helpers/capture-coordinator.zsh \
  /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-021 \
  rgbd-pick-task-start-exp021-20260826 \
  rgbd-pick-exp021-viewer-20260826 &
/tmp/so101-debug-rgbd-perception-pick-place-20260826/helpers/full-restart.zsh \
  /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-021 \
  199 rgbd-pick-task-start-exp021-20260826 task_start
```

Before these commands, create only the empty parents with:

```zsh
run_root=/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-021
mkdir -p "$run_root"/{run,ros,gui,pre-running}
```

Do not precreate `run.d/rgbd-pick-task-start-exp021-20260826`; the production launch must allocate it exclusively.

- [ ] **Step 3: Evaluate all acceptance gates and inspect all three images**

Require launch/capture exit `0`; summary status `OK`; CameraPlugin `task_camera_frame` 640x480; nonempty PLY; one RGB-D producer and no truth bridge; perception-to-keyframe and dynamic-input-to-keyframe errors at most `0.01 m`; manifest status/current state `DONE`, transition count `19`, expected trace, exact session/epoch; bilateral unsupported contact before attach; lift and transport; controller/FK/joint changes; detached release; final `xy <= 0.01 m`, upright tilt `<= 0.10 rad`; final Planning Scene `attached_object_ids=[]` and primitive counts `pedestal=1, plastic_cup=13, table=1`; three distinct 1568x862 screenshots from the same Viewer; natural exit and exact-owned cleanup. Retain nonfatal `pal_statistics` shutdown diagnostics separately from fatal/traceback counts.

- [ ] **Step 4: Close the experiment and commit**

End the CUA session with `cua-driver end_session '{"session":"rgbd-pick-exp021-viewer-20260826"}'`, save exact cleanup readback, visually describe baseline/transport/final, append either VALID or INVALID closure, and commit/push the ledger. Proceed only if VALID; otherwise diagnose under `$systematic-debugging` with a new experiment ID.

### Task 7: Accept EXP-022 at `cup_test_forward_5cm`

**Files:** ledger plus `/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-022/` evidence.

**Interfaces:** consumes frozen implementation and the two accepted helper scripts; produces one independently closed forward-keyframe run.

- [ ] **Step 1: Prove isolation and append PLANNED -> RUNNING**

Use domain `200`, runtime session `rgbd-pick-forward-exp022-20260826`, CUA session `rgbd-pick-exp022-viewer-20260826`, and keyframe `cup_test_forward_5cm`. Verify empty domain/process/tmux/Viewer/evidence identities; append, commit, and push RUNNING before launch.

- [ ] **Step 2: Start capture and full restart with exact identities**

```zsh
run_root=/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-022
mkdir -p "$run_root"/{run,ros,gui,pre-running}
cua-driver start_session '{"session":"rgbd-pick-exp022-viewer-20260826","capture_scope":"window"}'
/tmp/so101-debug-rgbd-perception-pick-place-20260826/helpers/capture-coordinator.zsh \
  "$run_root" rgbd-pick-forward-exp022-20260826 \
  rgbd-pick-exp022-viewer-20260826 &
/tmp/so101-debug-rgbd-perception-pick-place-20260826/helpers/full-restart.zsh \
  "$run_root" 200 rgbd-pick-forward-exp022-20260826 \
  cup_test_forward_5cm
```

Do not precreate `run.d/rgbd-pick-forward-exp022-20260826`.

- [ ] **Step 3: Evaluate the complete forward acceptance set**

Require both exit files `0`; summary `OK`, `task_camera_frame`, 640x480, nonempty PLY, one RGB-D producer, zero truth bridge, summary and dynamic input within `0.01 m` of `cup_test_forward_5cm`, exact input producer stamp match, manifest `DONE` with 19 transitions and exact session/epoch, controller/FK/joint movement, bilateral unsupported grasp, lift, transport, detach, released table support, zero final finger contacts, final `xy <= 0.01 m`, tilt `<= 0.10 rad`, detached final Planning Scene with `pedestal=1`, `plastic_cup=13`, `table=1`, three distinct 1568x862 same-window images, natural child exits, and exact domain/process/tmux/Viewer/CUA cleanup. Inspect baseline, transport, and final PNGs directly.

- [ ] **Step 4: Close and persist EXP-022**

```zsh
cua-driver end_session '{"session":"rgbd-pick-exp022-viewer-20260826"}'
```

Append VALID or INVALID with numeric/physical/visual evidence, commit, push, and proceed only if VALID. A rerun uses a new experiment ID.

### Task 8: Accept EXP-023 at `cup_test_left_5cm`

**Files:** ledger plus `/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-023/` evidence.

**Interfaces:** consumes frozen implementation and the two accepted helper scripts; produces one independently closed left-keyframe run.

- [ ] **Step 1: Prove isolation and append PLANNED -> RUNNING**

Use domain `201`, runtime session `rgbd-pick-left-exp023-20260826`, CUA session `rgbd-pick-exp023-viewer-20260826`, and keyframe `cup_test_left_5cm`. Verify empty domain/process/tmux/Viewer/evidence identities; append, commit, and push RUNNING before launch.

- [ ] **Step 2: Start capture and full restart with exact identities**

```zsh
run_root=/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-023
mkdir -p "$run_root"/{run,ros,gui,pre-running}
cua-driver start_session '{"session":"rgbd-pick-exp023-viewer-20260826","capture_scope":"window"}'
/tmp/so101-debug-rgbd-perception-pick-place-20260826/helpers/capture-coordinator.zsh \
  "$run_root" rgbd-pick-left-exp023-20260826 \
  rgbd-pick-exp023-viewer-20260826 &
/tmp/so101-debug-rgbd-perception-pick-place-20260826/helpers/full-restart.zsh \
  "$run_root" 201 rgbd-pick-left-exp023-20260826 \
  cup_test_left_5cm
```

Do not precreate `run.d/rgbd-pick-left-exp023-20260826`.

- [ ] **Step 3: Evaluate the complete left acceptance set**

Require both exit files `0`; summary `OK`, `task_camera_frame`, 640x480, nonempty PLY, one RGB-D producer, zero truth bridge, summary and dynamic input within `0.01 m` of `cup_test_left_5cm`, exact input producer stamp match, manifest `DONE` with 19 transitions and exact session/epoch, controller/FK/joint movement, bilateral unsupported grasp, lift, transport, detach, released table support, zero final finger contacts, final `xy <= 0.01 m`, tilt `<= 0.10 rad`, detached final Planning Scene with `pedestal=1`, `plastic_cup=13`, `table=1`, three distinct 1568x862 same-window images, natural child exits, and exact domain/process/tmux/Viewer/CUA cleanup. Inspect baseline, transport, and final PNGs directly.

- [ ] **Step 4: Close and persist EXP-023**

```zsh
cua-driver end_session '{"session":"rgbd-pick-exp023-viewer-20260826"}'
```

Append VALID or INVALID with numeric/physical/visual evidence, commit, push, and proceed only if VALID. A rerun uses a new experiment ID.

### Task 9: Accept EXP-024 at `cup_test_right_5cm`

**Files:** ledger plus `/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-024/` evidence.

**Interfaces:** consumes frozen implementation and the two accepted helper scripts; produces one independently closed right-keyframe run and a four-run checkpoint.

- [ ] **Step 1: Prove isolation and append PLANNED -> RUNNING**

Use domain `202`, runtime session `rgbd-pick-right-exp024-20260826`, CUA session `rgbd-pick-exp024-viewer-20260826`, and keyframe `cup_test_right_5cm`. Verify empty domain/process/tmux/Viewer/evidence identities; append, commit, and push RUNNING before launch.

- [ ] **Step 2: Start capture and full restart with exact identities**

```zsh
run_root=/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-024
mkdir -p "$run_root"/{run,ros,gui,pre-running}
cua-driver start_session '{"session":"rgbd-pick-exp024-viewer-20260826","capture_scope":"window"}'
/tmp/so101-debug-rgbd-perception-pick-place-20260826/helpers/capture-coordinator.zsh \
  "$run_root" rgbd-pick-right-exp024-20260826 \
  rgbd-pick-exp024-viewer-20260826 &
/tmp/so101-debug-rgbd-perception-pick-place-20260826/helpers/full-restart.zsh \
  "$run_root" 202 rgbd-pick-right-exp024-20260826 \
  cup_test_right_5cm
```

Do not precreate `run.d/rgbd-pick-right-exp024-20260826`.

- [ ] **Step 3: Evaluate the complete right acceptance set**

Require both exit files `0`; summary `OK`, `task_camera_frame`, 640x480, nonempty PLY, one RGB-D producer, zero truth bridge, summary and dynamic input within `0.01 m` of `cup_test_right_5cm`, exact input producer stamp match, manifest `DONE` with 19 transitions and exact session/epoch, controller/FK/joint movement, bilateral unsupported grasp, lift, transport, detach, released table support, zero final finger contacts, final `xy <= 0.01 m`, tilt `<= 0.10 rad`, detached final Planning Scene with `pedestal=1`, `plastic_cup=13`, `table=1`, three distinct 1568x862 same-window images, natural child exits, and exact domain/process/tmux/Viewer/CUA cleanup. Inspect baseline, transport, and final PNGs directly.

- [ ] **Step 4: Close and persist EXP-024 plus the four-run checkpoint**

```zsh
cua-driver end_session '{"session":"rgbd-pick-exp024-viewer-20260826"}'
```

Append VALID or INVALID with numeric/physical/visual evidence. If VALID, append a checkpoint naming EXP-021 through EXP-024 as the current countable hardened set. Commit and push. A rerun uses a new experiment ID.

### Task 10: Final verification, independent review, and inventory

**Files:**

- Modify: `docs/experiments/mujoco-rgbd-perception-pick-place-experiment-ledger.md`
- Regenerate: `/tmp/so101-debug-rgbd-perception-pick-place-20260826/sha256.txt`
- Regenerate: `/tmp/so101-debug-rgbd-perception-pick-place-20260826/sizes.txt`

**Interfaces:**

- Consumes: four accepted hardened-provenance runs and a clean pushed branch.
- Produces: independent review result, final clean verification, self-consistent evidence inventory, and completion checkpoint.

- [ ] **Step 1: Repeat complete source and static verification**

```zsh
python3 -m pytest src/so101_demo_py/test -q
ruff check \
  src/so101_demo_py/src/runtime/launch_composition.py \
  src/so101_demo_py/src/ports/cup_scene_observation.py \
  src/so101_demo_py/src/application/cup_pose_preflight.py \
  src/so101_demo_py/src/ros/cup_scene_observer.py \
  src/so101_demo_py/src/ros/dynamic_runtime.py \
  src/so101_demo_py/test/test_perception_pick_place_launch.py \
  src/so101_demo_py/test/test_perception_launch_runner.py \
  src/so101_demo_py/test/test_cup_pose_preflight.py \
  src/so101_demo_py/test/test_dynamic_scene_sync.py \
  src/so101_demo_py/test/test_installed_provenance.py \
  src/so101_demo_py/test/test_mujoco_camera_plugin_contract.py
ruff format --check \
  src/so101_demo_py/src/runtime/launch_composition.py \
  src/so101_demo_py/src/ports/cup_scene_observation.py \
  src/so101_demo_py/src/application/cup_pose_preflight.py \
  src/so101_demo_py/src/ros/cup_scene_observer.py \
  src/so101_demo_py/src/ros/dynamic_runtime.py
rosdep resolve opengl
```

Expected: all tests and static checks green and rosdep still resolves the declared key.

- [ ] **Step 2: Repeat build, installed provenance, and cleanup verification**

```zsh
colcon --log-base /tmp/so101-debug-rgbd-perception-pick-place-20260826/ai-station-overlay/log-final-hardening \
  build \
  --base-paths third_party/mujoco_ros2_control src \
  --build-base /tmp/so101-debug-rgbd-perception-pick-place-20260826/ai-station-overlay/build \
  --install-base /tmp/so101-debug-rgbd-perception-pick-place-20260826/ai-station-overlay/install \
  --symlink-install \
  --packages-select mujoco_ros2_control_msgs so101_teleop mujoco_ros2_control_plugins \
    mujoco_ros2_control so101_mujoco_support so101_demo_py
ros2 pkg executables so101_demo_py | rg '^so101_demo_py so101_mujoco_perception_pick_place$'
git rev-parse HEAD:third_party/mujoco_ros2_control
git -C third_party/mujoco_ros2_control rev-parse HEAD
git -C third_party/mujoco_ros2_control describe --tags --always
```

Expected: dependency-closed six-package build green, installed runner present, both hashes exact f19, describe `so101-0.0.3-r8-3-gf19a8cc`, and no owned process/domain/tmux/Viewer/CUA residue. Build without the task Open3D dependency directory on `PYTHONPATH`; restore it for runtime verification.

- [ ] **Step 3: Request a fresh code review**

Invoke `$superpowers:requesting-code-review`. Supply the approved spec, this plan, the original five findings, frozen implementation commit, exact submodule, test/build logs, and EXP-021 through EXP-024 closures. A reviewer must explicitly decide each finding and readiness. If any critical or important finding remains, append a checkpoint and return to a new RED task rather than declaring completion.

- [ ] **Step 4: Append the completion checkpoint before the inventory**

Record retained runs EXP-007 through EXP-024, archived runs (none unless already recorded), and deletion candidates without deleting them. Record old EXP-017 through EXP-020 as retained historical a8 evidence and EXP-021 through EXP-024 as the current countable set. Commit and push the ledger, then verify remote readback.

- [ ] **Step 5: Regenerate the inventory as the final evidence write**

```zsh
evidence_root=/tmp/so101-debug-rgbd-perception-pick-place-20260826
find "$evidence_root" -type f \
  ! -path "$evidence_root/sha256.txt" \
  ! -path "$evidence_root/sizes.txt" \
  -print0 | sort -z | xargs -0 sha256sum > "$evidence_root/sha256.txt"
find "$evidence_root" -type f \
  ! -path "$evidence_root/sha256.txt" \
  ! -path "$evidence_root/sizes.txt" \
  -printf '%s %p\n' | sort -k2 > "$evidence_root/sizes.txt"
sha256sum -c "$evidence_root/sha256.txt"
```

Expected: verification returns zero. Afterward perform only read-only checks so the inventory stays final.

- [ ] **Step 6: Final readback**

Verify local HEAD equals Gitee branch HEAD, task tree clean, submodule/gitlink exact f19 and clean, canonical main unchanged, all task-owned resources absent, and no unrecorded evidence disposition. Report completion only with this fresh evidence.
