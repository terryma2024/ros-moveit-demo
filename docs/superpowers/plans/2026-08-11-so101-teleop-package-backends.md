# SO-101 Teleop Package and Backend Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the complete SO-101 Teleop backend/frontend and GUI tiler into `src/so101_teleop`, then connect it to explicitly selected Gazebo C++, Gazebo Python, or MuJoCo Python owners through capability-gated installed CLI adapters.

**Architecture:** `so101_teleop` is an `ament_cmake + ament_cmake_python` control-plane package. It owns HTTP/WebSocket APIs, lease/session/idempotency, common ROS telemetry and manual controls, immutable backend profiles, and subprocess result normalization; each selected robot package remains the sole workflow/reset/scene/physics owner. `backend:=gazebo_cpp|gazebo_py|mujoco_py` is mandatory and never auto-detected or switched.

**Tech Stack:** ROS 2 Jazzy, ament/colcon, Python 3.12, FastAPI/Pydantic/rclpy, ament index, YAML, pytest, Bun/Vite/React/TypeScript, Vitest, Playwright, X11/EWMH.

## Global Constraints

- Work only in `/data/work/ws_moveit/.worktrees/so101-teleop-extraction` on `codex/so101-teleop-extraction`; preserve every other worktree and running stack.
- The Teleop launch must require `backend:=gazebo_cpp|gazebo_py|mujoco_py`; do not add auto-detection or fallback.
- `so101_teleop` must not own or copy robot workflow transitions, checkpoint contents, reset/recovery logic, physical result judgment, or backend-internal classes.
- Resolve only package-installed profiles and executables through ament; Web/API input must never select a package, executable, shell command, environment key, argument template, or profile path.
- Use argument arrays with `subprocess.run(argv, shell=False)`; write sanitized diagnostics only under `/tmp/so101-teleop/{sanitized_session_id}/`.
- Direct calls to unsupported operations return `BACKEND_CAPABILITY_UNAVAILABLE` before creating a run, checkpoint, or subprocess.
- `mujoco_py` initially exposes only `backend_probe=true`; every live workflow/reset/scene/physical/manual/camera capability remains false.
- `gazebo_py` initially exposes `scene_operations=false`: its installed scene owner accepts `observe|attach|detach` but not the `upsert` operation required by Teleop scene repair. Do not mark the broader capability true until that owner contract exists.
- Move `tile_ai_station_guis.py` and its X11/EWMH implementation to `so101_teleop`; delete the C++ package entry and do not leave a wrapper.
- Keep historical specs, plans, handoffs, and experiment ledgers unchanged; update only current package/operator/Skill documentation.
- Use RED -> GREEN for each behavior change, then package tests, installed-overlay provenance, and live validation. Never count `DONE`, API success, or a screenshot alone as robot-runtime acceptance.

---

## File Structure

The completed package owns these focused units:

```text
src/so101_teleop/
├── CMakeLists.txt                         # Web build, Python/script/resource install, pytest registration
├── package.xml                            # Direct Teleop-only ROS/system dependencies
├── launch/so101_teleop.launch.py          # Explicit backend preflight and server process
├── config/so101_teleop.yaml               # Common ROS topics/frames
├── config/backends/{gazebo_cpp,gazebo_py,mujoco_py}.yaml
├── docs/so101-teleop-web-ui.md
├── scripts/{so101_teleop_server.py,tile_ai_station_guis.py}
├── so101_teleop/
│   ├── backends/
│   │   ├── protocol.py                    # Backend operation/request/envelope protocol
│   │   ├── profile.py                     # Frozen typed profile and strict YAML parser
│   │   ├── registry.py                    # Fixed backend-id to installed profile registry
│   │   └── cli_adapter.py                 # ament executable resolution and subprocess normalization
│   ├── gui/x11.py                         # Shared X11/EWMH primitives
│   ├── api.py                             # FastAPI route ownership
│   ├── server.py                          # ROS worker and application service
│   ├── models.py                          # API and telemetry models
│   └── web_bundle.py                      # Installed Vite bundle preflight
├── test/
│   ├── backends/                          # Profile, registry, adapter, and capability tests
│   ├── teleop/                            # Migrated FastAPI/service/ROS-boundary tests
│   ├── test_package_layout.py
│   ├── test_tile_ai_station_guis.py
│   └── test_ai_station_x11.py
└── web/                                   # Migrated Vite/React application and browser tests
```

The C++ package keeps only Gazebo/MoveIt/C++ robot behavior and its own tests.

---

### Task 1: Lock Package Ownership with RED Contract Tests

**Files:**
- Create: `src/so101_teleop/test/test_package_layout.py`
- Modify later in this task: `src/so101_teleop/CMakeLists.txt`
- Modify later in this task: `src/so101_teleop/package.xml`

**Interfaces:**
- Consumes: approved ownership rule and current `src/so101_gazebo_demo_cpp` layout.
- Produces: a discoverable `so101_teleop` ROS package and a failing contract that names every legacy path that must disappear.

- [ ] **Step 1: Create the minimal ROS package metadata and RED ownership test.**

Create `package.xml` with package name `so101_teleop`, build tools `ament_cmake` and `ament_cmake_python`, and test dependency `ament_cmake_pytest`. Create a minimal `CMakeLists.txt` that calls `project(so101_teleop)`, finds those three packages, registers `test_package_layout`, and calls `ament_package()`.

The test must assert the final ownership, including the absence of wrappers:

```python
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
CPP = PACKAGE.parent / "so101_gazebo_demo_cpp"


def test_teleop_is_a_single_standalone_package():
    assert PACKAGE.name == "so101_teleop"
    assert (PACKAGE / "package.xml").is_file()
    assert (PACKAGE / "CMakeLists.txt").is_file()
    assert (PACKAGE / "so101_teleop" / "server.py").is_file()
    assert (PACKAGE / "web" / "package.json").is_file()
    assert (PACKAGE / "launch" / "so101_teleop.launch.py").is_file()


def test_cpp_package_has_no_legacy_teleop_or_tiler_entry():
    forbidden = (
        CPP / "so101_teleop",
        CPP / "web",
        CPP / "launch" / "so101_teleop.launch.py",
        CPP / "config" / "so101_teleop.yaml",
        CPP / "scripts" / "so101_teleop_server.py",
        CPP / "scripts" / "tile_ai_station_guis.py",
        CPP / "scripts" / "ai_station_x11.py",
        CPP / "test" / "teleop",
        CPP / "test" / "test_tile_ai_station_guis.py",
        CPP / "test" / "test_ai_station_x11.py",
    )
    assert not [str(path) for path in forbidden if path.exists()]
```

- [ ] **Step 2: Run the contract and verify the intended RED state.**

Run:

```bash
source /opt/ros/jazzy/setup.zsh
cd /data/work/ws_moveit/.worktrees/so101-teleop-extraction
PYTHONNOUSERSITE=1 pytest -q src/so101_teleop/test/test_package_layout.py
```

Expected: FAIL because the new package does not yet own the server/Web/launch files and the C++ legacy paths still exist.

- [ ] **Step 3: Commit the executable RED contract.**

```bash
git add src/so101_teleop
git commit -m "test: lock standalone Teleop ownership"
```

---

### Task 2: Move the Existing Teleop as a Gazebo C++ Equivalent Package

**Files:**
- Move: `src/so101_gazebo_demo_cpp/so101_teleop/` -> `src/so101_teleop/so101_teleop/`
- Move: `src/so101_gazebo_demo_cpp/web/` -> `src/so101_teleop/web/`
- Move: `src/so101_gazebo_demo_cpp/test/teleop/` -> `src/so101_teleop/test/teleop/`
- Move: `src/so101_gazebo_demo_cpp/launch/so101_teleop.launch.py` -> `src/so101_teleop/launch/so101_teleop.launch.py`
- Move: `src/so101_gazebo_demo_cpp/config/so101_teleop.yaml` -> `src/so101_teleop/config/so101_teleop.yaml`
- Move: `src/so101_gazebo_demo_cpp/docs/so101-teleop-web-ui.md` -> `src/so101_teleop/docs/so101-teleop-web-ui.md`
- Move: `src/so101_gazebo_demo_cpp/scripts/so101_teleop_server.py` -> `src/so101_teleop/scripts/so101_teleop_server.py`
- Modify: `src/so101_teleop/CMakeLists.txt`
- Modify: `src/so101_teleop/package.xml`
- Modify: `src/so101_teleop/launch/so101_teleop.launch.py`
- Modify: `src/so101_gazebo_demo_cpp/CMakeLists.txt`

**Interfaces:**
- Consumes: current FastAPI, ROS worker, Bun build, OpenAPI, lease/session, and Teleop tests unchanged in behavior.
- Produces: installed `so101_teleop/so101_teleop_server.py`, `so101_teleop.launch.py`, Web bundle, and Python module while still using the current C++ owner internally.

- [ ] **Step 1: Move tracked files without copying or leaving wrappers.**

Use `git mv` for every path above. Preserve history and do not edit robot workflow code. In the same working change, remove the C++ CMake references to every moved Web, Python, launch, config, doc, script, and test path; never leave an intermediate commit that cannot configure or build.

- [ ] **Step 2: Give the new package direct dependencies and complete install rules.**

Move only Teleop dependencies out of the C++ package in Task 9; for now make the new package independently correct. Its CMake must:

```cmake
find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(ament_cmake_pytest REQUIRED)

ament_python_install_package(so101_teleop)
install(DIRECTORY web/dist/ DESTINATION share/${PROJECT_NAME}/web)
install(DIRECTORY config docs launch DESTINATION share/${PROJECT_NAME})
install(PROGRAMS scripts/so101_teleop_server.py DESTINATION lib/${PROJECT_NAME})
```

Move the existing Bun discovery, `SO101_TELEOP_WEB_SOURCES`, frozen install, Vite build, and `so101_teleop_web ALL` target from the C++ CMake into this CMake, changing only paths/package name. Move every Teleop pytest registration into the new package. Keep both package CMake files internally valid in this same step.

- [ ] **Step 3: Retarget installed package lookup and launch ownership.**

In `launch/so101_teleop.launch.py`, change `_installed_bundle()` and the `Node` package field to `so101_teleop`, add a required `backend` launch argument with no silent default, and pass it as `SO101_TELEOP_BACKEND`. At this intermediate commit, accept only `gazebo_cpp` and fail other values explicitly; later tasks add profiles.

- [ ] **Step 4: Run migrated Python, Web, and package build tests.**

```bash
source /opt/ros/jazzy/setup.zsh
cd /data/work/ws_moveit/.worktrees/so101-teleop-extraction
PYTHONNOUSERSITE=1 pytest -q src/so101_teleop/test/teleop src/so101_teleop/test/test_package_layout.py
PATH=/home/lenovo/.bun/bin:$PATH bun --cwd src/so101_teleop/web test
colcon build --packages-select so101_teleop --symlink-install
```

Expected: migrated Teleop tests and Web unit tests pass; package build installs `share/so101_teleop/web/index.html`.

- [ ] **Step 5: Verify installed ownership and commit.**

```bash
source install/setup.zsh
ros2 pkg prefix so101_teleop
ros2 pkg executables so101_teleop
ros2 launch so101_teleop so101_teleop.launch.py --show-args
git add src/so101_teleop src/so101_gazebo_demo_cpp
git commit -m "refactor: extract standalone SO101 Teleop package"
```

Expected: server executable and launch belong to `so101_teleop`; `backend` appears in launch arguments.

---

### Task 3: Add Frozen Backend Profiles and Fixed Registry

**Files:**
- Create: `src/so101_teleop/so101_teleop/backends/__init__.py`
- Create: `src/so101_teleop/so101_teleop/backends/protocol.py`
- Create: `src/so101_teleop/so101_teleop/backends/profile.py`
- Create: `src/so101_teleop/so101_teleop/backends/registry.py`
- Create: `src/so101_teleop/config/backends/gazebo_cpp.yaml`
- Create: `src/so101_teleop/config/backends/gazebo_py.yaml`
- Create: `src/so101_teleop/config/backends/mujoco_py.yaml`
- Create: `src/so101_teleop/test/backends/test_profiles.py`

**Interfaces:**
- Produces: `BackendId`, `BackendOperation`, `BackendCapabilities`, `ExecutableSpec`, `BackendProfile`, `BackendEnvelope`, `load_backend_profile(backend_id, share_dir=None)`.
- Consumes later: CLI adapter, server launch preflight, `/capabilities`, and Web types.

- [ ] **Step 1: Write failing strict-profile tests.**

Tests must prove fixed IDs, frozen data, exact MuJoCo false capabilities, and rejection of unknown keys/IDs:

```python
def test_mujoco_profile_exposes_probe_only(profile_root):
    profile = load_backend_profile("mujoco_py", profile_root)
    assert profile.owner_package == "so101_mujoco_demo_py"
    assert profile.capabilities.as_dict() == {
        "backend_probe": True,
        "workflow_execute": False,
        "workflow_start": False,
        "workflow_run": False,
        "workflow_resume": False,
        "reset_world": False,
        "scene_operations": False,
        "physical_observation": False,
        "manual_joint_execute": False,
        "manual_tcp_execute": False,
        "camera_presets": False,
    }


def test_profile_rejects_request_selected_executable(tmp_path):
    path = tmp_path / "gazebo_cpp.yaml"
    path.write_text("backend: gazebo_cpp\nowner_package: injected\nextra: shell\n")
    with pytest.raises(ProfileError, match="PROFILE_SCHEMA_INVALID"):
        load_profile_file(path, expected_backend="gazebo_cpp")
```

- [ ] **Step 2: Run the profile tests RED.**

```bash
PYTHONNOUSERSITE=1 pytest -q src/so101_teleop/test/backends/test_profiles.py
```

Expected: FAIL because profile types/loader do not exist.

- [ ] **Step 3: Implement frozen profile types and a strict loader.**

Use `@dataclass(frozen=True)` and `MappingProxyType` or tuples for nested data. `BackendOperation` must enumerate only `workflow`, `reset_world`, and `scene`. `load_backend_profile` accepts only a backend ID and an optional trusted test share directory; production resolves `share/so101_teleop/config/backends/{backend_id}.yaml`. Reject missing/extra YAML fields and any profile whose internal `backend` differs from the requested ID.

Profile executable specifications must contain only:

```python
@dataclass(frozen=True)
class ExecutableSpec:
    package: str
    executable: str
    timeout_s: float
    fixed_args: tuple[str, ...] = ()
    scene_style: Literal["positional", "flag"] | None = None
```

No method may accept package/executable/profile-path values from an HTTP body.

- [ ] **Step 4: Encode the three installed-owner profiles.**

Use these exact owner differences:

- `gazebo_cpp`: package `so101_gazebo_demo_cpp`; workflow `pick_place_state_machine`; reset `reset_so101_world`; scene `so101_moveit_scene` with positional operation.
- `gazebo_py`: package `so101_gazebo_demo_py`; workflow fixed args include `--live-runtime`; reset `reset_so101_world`; scene `so101_moveit_scene` with `--operation observe|attach|detach`.
- `mujoco_py`: package `so101_mujoco_demo_py`; probe executable `pick_place_state_machine`; no live operation specs.

`gazebo_cpp` sets the listed capabilities true. `gazebo_py` sets workflow, reset, physical observation, manual joint/TCP, and camera capabilities true but `scene_operations=false`, because the current Python scene CLI cannot perform Teleop's `upsert` repair. Capability values are explicit profile facts and are never inferred from executable presence.

- [ ] **Step 5: Run tests and commit.**

```bash
PYTHONNOUSERSITE=1 pytest -q src/so101_teleop/test/backends/test_profiles.py
git add src/so101_teleop
git commit -m "feat: define immutable Teleop backend profiles"
```

---

### Task 4: Implement the Installed CLI Adapter and Error Envelope

**Files:**
- Create: `src/so101_teleop/so101_teleop/backends/cli_adapter.py`
- Create: `src/so101_teleop/test/backends/test_cli_adapter.py`

**Interfaces:**
- Consumes: `BackendProfile`, fixed `ExecutableSpec`, request types from `protocol.py`.
- Produces: `CliBackendAdapter.probe()`, `.capabilities()`, `.run_workflow(request)`, `.reset_world(request)`, `.scene_operation(request)` returning `BackendEnvelope`.

- [ ] **Step 1: Write adapter RED tests for every infrastructure boundary.**

Use injected `package_prefix_resolver` and `run_process` fakes. Cover:

```python
def test_probe_normalizes_missing_package(gazebo_profile, fake_run):
    def missing_package(_package: str) -> str:
        raise PackageNotFoundError("owner package is absent")

    adapter = CliBackendAdapter(
        gazebo_profile,
        package_prefix_resolver=missing_package,
        run_process=fake_run,
    )
    result = adapter.probe()
    assert result.ok is False
    assert result.error.code == "BACKEND_PACKAGE_NOT_FOUND"
    fake_run.assert_not_called()


def test_adapter_never_uses_shell_or_request_selected_program(fake_run):
    adapter.run_workflow(WorkflowRequest(operation="run", session_id="s", checkpoint=Path("/tmp/c.json")))
    assert fake_run.call_args.kwargs["shell"] is False
    assert fake_run.call_args.args[0][0].endswith(
        "/lib/so101_gazebo_demo_py/pick_place_state_machine"
    )


def test_nonzero_owner_result_preserves_sanitized_failure_code(adapter, fake_run):
    fake_run.return_value = subprocess.CompletedProcess(["owner"], 7, "", "failure_code=Q6_NOT_STATIONARY")
    result = adapter.run_workflow(workflow_request("run"))
    assert result.ok is False
    assert result.error.code == "BACKEND_OPERATION_FAILED"
    assert result.error.owner_failure_code == "Q6_NOT_STATIONARY"


def test_unparseable_owner_output_returns_backend_output_invalid(adapter, fake_run):
    fake_run.return_value = subprocess.CompletedProcess(["owner"], 0, "unstructured", "")
    result = adapter.run_workflow(workflow_request("run"))
    assert result.ok is False
    assert result.error.code == "BACKEND_OUTPUT_INVALID"


def test_unsupported_operation_does_not_call_subprocess(probe_only_adapter, fake_run):
    result = probe_only_adapter.run_workflow(workflow_request("run"))
    assert result.error.code == "BACKEND_CAPABILITY_UNAVAILABLE"
    fake_run.assert_not_called()
```

- [ ] **Step 2: Run adapter tests RED.**

```bash
PYTHONNOUSERSITE=1 pytest -q src/so101_teleop/test/backends/test_cli_adapter.py
```

- [ ] **Step 3: Implement executable resolution and argument builders.**

Resolve the selected ament prefix plus `lib/{owner_package}/{owner_executable}`, require an executable regular file, and build workflow args from `WorkflowRequest.operation`:

```python
args = ["--mode", "execute", "--checkpoint", str(request.checkpoint),
        "--session-id", request.session_id]
if request.operation == "start":
    args.append("--step")
elif request.operation == "step":
    args.extend(("--resume", "true", "--step"))
elif request.operation in {"resume", "force-continue"}:
    args.extend(("--resume", "true"))
if request.operation == "force-continue":
    args.append("--force-continue")
```

Prepend profile `fixed_args`. Build scene arguments according to `scene_style`; never reinterpret Python `--operation` as the C++ positional CLI.

- [ ] **Step 4: Implement normalized envelope and diagnostics.**

`BackendEnvelope` must include `ok`, backend, operation, session ID, owner package/executable, exit code, result, and error. On nonzero/timeout/invalid output, atomically write a sanitized diagnostic under `/tmp/so101-teleop/{sanitized_session_id}/`, with a maximum captured stdout/stderr size and no environment dump.

- [ ] **Step 5: Run tests and commit.**

```bash
PYTHONNOUSERSITE=1 pytest -q src/so101_teleop/test/backends
git add src/so101_teleop
git commit -m "feat: add fail-closed installed CLI adapter"
```

---

### Task 5: Inject Backend Ownership and Capability Gates into the Service

**Files:**
- Modify: `src/so101_teleop/so101_teleop/main.py`
- Modify: `src/so101_teleop/so101_teleop/server.py`
- Modify: `src/so101_teleop/so101_teleop/models.py`
- Modify: `src/so101_teleop/so101_teleop/api.py`
- Modify: `src/so101_teleop/launch/so101_teleop.launch.py`
- Modify: `src/so101_teleop/test/teleop/test_server_safety.py`
- Create: `src/so101_teleop/test/teleop/test_backend_capabilities.py`

**Interfaces:**
- Consumes: one frozen `BackendProfile` and `CliBackendAdapter` selected at process startup.
- Produces: immutable `/capabilities` response and pre-command `require_capability(key)` gate.

- [ ] **Step 1: Write RED tests proving unsupported calls have no side effects.**

```python
def test_unsupported_workflow_fails_before_run_or_checkpoint(tmp_path):
    adapter = FakeAdapter(capabilities={"workflow_run": False})
    service = TeleopService(worker=Worker(), backend=adapter)
    result = asyncio.run(service.command("workflow_run", valid_body()))
    assert result.code == "BACKEND_CAPABILITY_UNAVAILABLE"
    assert service._workflow == {}
    assert adapter.calls == []
    assert list(tmp_path.iterdir()) == []


def test_capabilities_include_frozen_owner_provenance():
    payload = asyncio.run(service.capabilities())
    assert payload["backend"] == "gazebo_py"
    assert payload["owner_package"] == "so101_gazebo_demo_py"
    assert payload["capabilities"]["workflow_run"] is True
```

Also test reset and scene failure do not clear lease/run/plan/idempotency state.

- [ ] **Step 2: Run tests RED.**

```bash
PYTHONNOUSERSITE=1 pytest -q \
  src/so101_teleop/test/teleop/test_backend_capabilities.py \
  src/so101_teleop/test/teleop/test_server_safety.py
```

- [ ] **Step 3: Move package CLI calls out of `RosTelemetryWorker`.**

Delete `RosTelemetryWorker.package_cli`. Inject a `BackendProtocol` into `TeleopService`. Route workflow/reset/scene owner calls only through that backend. Keep direct ROS telemetry, joint/TCP planning/execution, attachment convergence, and Gazebo screenshot in the Teleop worker, but gate each exposed command by the selected profile.

- [ ] **Step 4: Freeze startup selection and preflight.**

`main.py` reads only `SO101_TELEOP_BACKEND`, calls `load_backend_profile`, constructs one adapter, runs `probe`, and then constructs the service/app. Launch must reject empty/unknown backend before starting the `Node`; missing packages/executables must surface their normalized code and must not switch backend.

- [ ] **Step 5: Preserve workflow/reset semantics while changing owner transport.**

Retain current run/checkpoint/session rules. Only after a successful backend reset envelope may the service invalidate the simulation session and clear plan, lease, workflow, and command-id state. Preserve force-continue confirmation and checkpoint-derived physical outcome parsing.

- [ ] **Step 6: Run the migrated service suite and commit.**

```bash
PYTHONNOUSERSITE=1 pytest -q src/so101_teleop/test/teleop src/so101_teleop/test/backends
git add src/so101_teleop
git commit -m "refactor: route Teleop commands through selected backend"
```

---

### Task 6: Verify Gazebo Python Uses Its Own CLI Contract

**Files:**
- Modify: `src/so101_teleop/config/backends/gazebo_py.yaml`
- Modify: `src/so101_teleop/test/backends/test_cli_adapter.py`
- Modify: `src/so101_teleop/test/teleop/test_backend_capabilities.py`

**Interfaces:**
- Consumes: Python console scripts from `so101_gazebo_demo_py/setup.py`.
- Produces: exact Python owner commands, including `--live-runtime` and `--operation` scene syntax.

- [ ] **Step 1: Add exact argv characterization tests.**

Assert:

```python
assert workflow_argv == [
    python_owner, "--live-runtime", "--mode", "execute", "--checkpoint", checkpoint,
    "--session-id", "session-a"
]
assert reset_argv == [python_reset]
assert capabilities["scene_operations"] is False
```

Also assert no workflow/reset argv path contains `so101_gazebo_demo_cpp` when `gazebo_py` is selected, and a Teleop scene-repair request returns `BACKEND_CAPABILITY_UNAVAILABLE` without invoking the Python scene executable.

- [ ] **Step 2: Run the new tests RED, fix only profile/adapter mapping, then run GREEN.**

```bash
PYTHONNOUSERSITE=1 pytest -q src/so101_teleop/test/backends/test_cli_adapter.py -k gazebo_py
```

- [ ] **Step 3: Run both installed owner help/preflight commands without executing motion.**

```bash
source /opt/ros/jazzy/setup.zsh
source install/setup.zsh
ros2 pkg executables so101_gazebo_demo_cpp | rg 'pick_place_state_machine|reset_so101_world|so101_moveit_scene'
ros2 pkg executables so101_gazebo_demo_py | rg 'pick_place_state_machine|reset_so101_world|so101_moveit_scene'
```

Expected: both owner sets resolve from their own package prefixes.

- [ ] **Step 4: Commit.**

```bash
git add src/so101_teleop
git commit -m "feat: connect Teleop to Gazebo Python owners"
```

---

### Task 7: Pin MuJoCo to Probe-Only Behavior

**Files:**
- Modify: `src/so101_teleop/config/backends/mujoco_py.yaml`
- Create: `src/so101_teleop/test/backends/test_mujoco_profile.py`

**Interfaces:**
- Consumes: future package ID/executable name from `so101_mujoco_demo_py/setup.py`.
- Produces: package provenance probe with no live robot command path.

- [ ] **Step 1: Write RED tests for every forbidden MuJoCo call.**

Parameterize workflow start/run/resume, reset, scene, manual joint/TCP, physical observation, and camera preset. Every call must return `BACKEND_CAPABILITY_UNAVAILABLE`, leave adapter call history empty, and not create a checkpoint.

- [ ] **Step 2: Run RED, set the exact fixed false matrix, and rerun GREEN.**

```bash
PYTHONNOUSERSITE=1 pytest -q src/so101_teleop/test/backends/test_mujoco_profile.py
```

- [ ] **Step 3: Characterize the future package without treating dry/headless as live.**

Read `/data/work/ws_moveit/.worktrees/so101-mujoco-ros2/src/so101_mujoco_demo_py/setup.py` and assert only the package/executable provenance in tests. Do not invoke execute, reset, or observer and do not add a dependency from the MuJoCo package to Teleop.

- [ ] **Step 4: Commit.**

```bash
git add src/so101_teleop
git commit -m "feat: expose probe-only MuJoCo Teleop profile"
```

---

### Task 8: Make the Web UI Capability-Driven

**Files:**
- Modify: `src/so101_teleop/web/src/api/types.ts`
- Modify: `src/so101_teleop/web/src/api/client.ts`
- Modify: `src/so101_teleop/web/src/app.tsx`
- Modify: `src/so101_teleop/web/src/components/teleop/workflow-panel.tsx`
- Modify: `src/so101_teleop/web/src/components/teleop/joint-panel.tsx`
- Modify: `src/so101_teleop/web/src/components/teleop/tcp-panel.tsx`
- Modify: `src/so101_teleop/web/src/components/teleop/environment-panel.tsx`
- Create: `src/so101_teleop/web/src/api/capabilities.test.ts`
- Modify: relevant component tests and `src/so101_teleop/web/e2e/teleop.spec.ts`
- Regenerate: `src/so101_teleop/so101_teleop/openapi.json`
- Regenerate: `src/so101_teleop/web/src/api/schema.d.ts`

**Interfaces:**
- Consumes: `/capabilities` payload with backend/owner/capability map.
- Produces: typed `BackendCapabilities`; disabled/hidden unsupported actions and visible backend provenance.

- [ ] **Step 1: Add failing Vitest fixtures for supported and probe-only profiles.**

For a MuJoCo fixture, assert Run/Start/Resume, joint execute, TCP execute, reset, scene, and camera controls are disabled or absent, while backend name/probe status remains visible. For Gazebo C++/Python fixtures, assert currently supported controls remain enabled subject to lease/readiness.

- [ ] **Step 2: Run Web tests RED.**

```bash
PATH=/home/lenovo/.bun/bin:$PATH bun --cwd src/so101_teleop/web test
```

- [ ] **Step 3: Fetch capabilities once at application startup and pass them explicitly.**

Define:

```ts
export type BackendCapabilities = {
  backend: "gazebo_cpp" | "gazebo_py" | "mujoco_py";
  owner_package: string;
  capabilities: Record<
    "backend_probe" | "workflow_execute" | "workflow_start" | "workflow_run" |
    "workflow_resume" | "reset_world" | "scene_operations" |
    "physical_observation" | "manual_joint_execute" |
    "manual_tcp_execute" | "camera_presets",
    boolean
  >;
};
```

Do not infer support from telemetry presence or button history.

- [ ] **Step 4: Gate each control and keep server errors visible.**

The UI prevents ordinary unsupported clicks, but the API remains authoritative. If a direct/stale client receives `BACKEND_CAPABILITY_UNAVAILABLE`, render that exact code rather than generic success/failure text.

- [ ] **Step 5: Regenerate OpenAPI/client schema and run Web acceptance.**

```bash
PYTHONNOUSERSITE=1 python3 -m so101_teleop.openapi_export \
  src/so101_teleop/so101_teleop/openapi.json
PATH=/home/lenovo/.bun/bin:$PATH bun --cwd src/so101_teleop/web run generate:api
PATH=/home/lenovo/.bun/bin:$PATH bun --cwd src/so101_teleop/web test
PATH=/home/lenovo/.bun/bin:$PATH bun --cwd src/so101_teleop/web run build
PATH=/home/lenovo/.bun/bin:$PATH bun --cwd src/so101_teleop/web run test:e2e
```

- [ ] **Step 6: Commit.**

```bash
git add src/so101_teleop
git commit -m "feat: drive Teleop controls from backend capabilities"
```

---

### Task 9: Move the X11 Tiler and Delete Its Legacy Entry

**Files:**
- Move: `src/so101_gazebo_demo_cpp/scripts/ai_station_x11.py` -> `src/so101_teleop/so101_teleop/gui/x11.py`
- Move: `src/so101_gazebo_demo_cpp/scripts/tile_ai_station_guis.py` -> `src/so101_teleop/scripts/tile_ai_station_guis.py`
- Move: `src/so101_gazebo_demo_cpp/test/test_ai_station_x11.py` -> `src/so101_teleop/test/test_ai_station_x11.py`
- Move: `src/so101_gazebo_demo_cpp/test/test_tile_ai_station_guis.py` -> `src/so101_teleop/test/test_tile_ai_station_guis.py`
- Modify: `src/so101_teleop/CMakeLists.txt`

**Interfaces:**
- Produces: `ros2 run so101_teleop tile_ai_station_guis.py` with unchanged parser, `LAYOUT_OK`/`LAYOUT_ERROR`, exit codes, timeout, geometry tolerance, tiling, and maximize behavior.

- [ ] **Step 1: Move tests first and make them import only the new owner.**

Change tests to import `so101_teleop.gui.x11` and load `src/so101_teleop/scripts/tile_ai_station_guis.py`. Run them before moving implementation; expected RED is import/path failure.

- [ ] **Step 2: Move implementation and replace sibling script imports.**

The executable must use:

```python
from so101_teleop.gui.x11 import (
    Rect, WindowInfo, X11EwmhBackend, classify_window,
    rect_is_close, select_unique_window, wait_for_unique_window,
)
```

Retain re-exports required by current tests/callers until they directly import the package module; do not create a C++ wrapper.

- [ ] **Step 3: Install and test the new command.**

```bash
PYTHONNOUSERSITE=1 pytest -q \
  src/so101_teleop/test/test_ai_station_x11.py \
  src/so101_teleop/test/test_tile_ai_station_guis.py
colcon build --packages-select so101_teleop --symlink-install
source install/setup.zsh
ros2 pkg executables so101_teleop | rg tile_ai_station_guis.py
! ros2 pkg executables so101_gazebo_demo_cpp | rg tile_ai_station_guis.py
```

- [ ] **Step 4: Commit.**

```bash
git add src/so101_teleop src/so101_gazebo_demo_cpp
git commit -m "refactor: move ai-station GUI tiler to Teleop"
```

---

### Task 10: Remove All Legacy C++ Teleop Ownership and Update Current Docs

**Files:**
- Modify: `src/so101_gazebo_demo_cpp/CMakeLists.txt`
- Modify: `src/so101_gazebo_demo_cpp/package.xml`
- Modify: `src/so101_gazebo_demo_cpp/test/test_package_layout.py`
- Modify: `src/so101_gazebo_demo_cpp/test/test_so101_launch_contract.py`
- Modify: `src/so101_gazebo_demo_cpp/README.md`
- Modify: `src/so101_teleop/docs/so101-teleop-web-ui.md`
- Modify: current repository docs that present the Teleop command as active

**Interfaces:**
- Produces: C++ package free of FastAPI/Bun/Teleop/tile install/test rules and dependencies; current docs use only `ros2 launch so101_teleop` and `ros2 run so101_teleop` entries.

- [ ] **Step 1: Make C++ package tests assert the new boundary.**

Replace legacy Teleop ownership assertions with negative checks. Keep robot/Gazebo/C++ tool assertions unchanged.

- [ ] **Step 2: Remove Teleop CMake blocks and direct-only dependencies.**

Confirm Task 2 already removed the Bun/Web target, `ament_python_install_package(so101_teleop)`, Web install, Teleop scripts, and Teleop pytest registrations, while Task 9 removed tiler/X11 rules. Remove only now-unused package dependencies and any remaining stale ownership reference; verify with `rg` before each removal.

- [ ] **Step 3: Update active documentation only.**

Current README/operator docs must show:

```bash
ros2 launch so101_teleop so101_teleop.launch.py \
  backend:=gazebo_py \
  simulation_session_id:=teleop-session-001
ros2 run so101_teleop tile_ai_station_guis.py
```

State explicitly that Teleop connects to an already-running backend stack and does not start Gazebo/MuJoCo/MoveIt/controllers. Do not rewrite historical plans, specs, handoffs, or ledgers.

- [ ] **Step 4: Build and test both package boundaries.**

```bash
source /opt/ros/jazzy/setup.zsh
cd /data/work/ws_moveit/.worktrees/so101-teleop-extraction
colcon build --packages-select so101_gazebo_demo_cpp so101_teleop --symlink-install
PYTHONNOUSERSITE=1 colcon test --packages-select so101_gazebo_demo_cpp so101_teleop \
  --event-handlers console_direct+
colcon test-result --verbose
```

Expected: nonzero test count for both packages, zero new failures, and no `0 tests` false pass.

- [ ] **Step 5: Run static ownership scans and commit.**

```bash
test ! -e src/so101_gazebo_demo_cpp/so101_teleop
test ! -e src/so101_gazebo_demo_cpp/web
test ! -e src/so101_gazebo_demo_cpp/launch/so101_teleop.launch.py
! rg -n "so101_teleop|tile_ai_station_guis" \
  src/so101_gazebo_demo_cpp/CMakeLists.txt src/so101_gazebo_demo_cpp/package.xml
git diff --check
git add src/so101_gazebo_demo_cpp src/so101_teleop README.md docs .agents
git commit -m "refactor: remove legacy C++ Teleop entrypoints"
```

---

### Task 11: Installed Overlay and Live Backend Acceptance

**Files:**
- Modify only if needed for current operator truth: `src/so101_teleop/docs/so101-teleop-web-ui.md`

**Interfaces:**
- Consumes: built packages, current ai-station process inventory, explicit isolated ROS/Gazebo lifecycle.
- Produces: provenance and runtime evidence for Gazebo C++ and Gazebo Python; no MuJoCo live-success claim.

- [ ] **Step 1: Recheck shared runtime ownership before any launch.**

```bash
tmux list-sessions 2>/dev/null || true
pgrep -af 'gz sim|move_group|rviz2|pick_place_state_machine|so101_teleop' || true
```

Do not reuse the active physical-five-success stack for destructive reset/workflow commands. Select an unused `ROS_DOMAIN_ID` and `GZ_PARTITION`, or stop and obtain authorization to reuse a verified idle stack.

- [ ] **Step 2: Prove installed provenance.**

```bash
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_moveit/.worktrees/so101-teleop-extraction/install/setup.zsh
ros2 pkg prefix so101_teleop
ros2 pkg executables so101_teleop
ros2 launch so101_teleop so101_teleop.launch.py --show-args
```

Inspect installed launch, profiles, Web index, server, and tile executable under that prefix.

- [ ] **Step 3: Validate fail-closed profile preflight without starting robot motion.**

Run the launch once with an invalid backend and once with a deliberately absent package fixture in a test overlay. Require explicit failure and no server process. Run `mujoco_py` only far enough to read `/capabilities`; require probe true and every live capability false.

- [ ] **Step 4: Validate Gazebo C++ and Python connections separately.**

For each backend, start Teleop against a dedicated already-running stack and read `/health`, `/capabilities`, and `/snapshot`. Require owner package/executable/session provenance. Execute only the smallest approved non-destructive workflow boundary first (`Start`/single-step), then verify its backend checkpoint and owner output. Reset uses `RESET_WORLD`, never `FULL_RESTART`.

- [ ] **Step 5: Capture independent robot evidence for any live command.**

For an executed workflow boundary, record backend CLI exit/result, controller and joint/TF change, Gazebo physical facts, MoveIt Planning Scene facts, and a fresh GUI image from the `ai-station-gui` Skill. Do not count API success or `DONE` alone.

- [ ] **Step 6: Run final regression and commit any documentation correction.**

```bash
PYTHONNOUSERSITE=1 colcon test --packages-select so101_gazebo_demo_cpp so101_teleop \
  --event-handlers console_direct+
colcon test-result --verbose
PATH=/home/lenovo/.bun/bin:$PATH bun --cwd src/so101_teleop/web test
PATH=/home/lenovo/.bun/bin:$PATH bun --cwd src/so101_teleop/web run build
git diff --check
git status --short
```

If operator documentation changed during live validation:

```bash
git add src/so101_teleop/docs/so101-teleop-web-ui.md
git commit -m "docs: record standalone Teleop runtime validation"
```

Otherwise leave the worktree clean without an empty commit.
