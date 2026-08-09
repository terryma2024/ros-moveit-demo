# SO-101 Gazebo Demo Python Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone ROS 2 Jazzy package named `so101_gazebo_demo_py` that reproduces the approved core external behavior of the R3 `so101_gazebo_demo` in Python without importing, linking, executing, or looking up runtime assets from the original C++ package or `pick_place_common`.

**Architecture:** Use an `ament_python` package with ROS-free domain/workflow/checkpoint modules and explicit `rclpy`, MoveIt service/action, controller action, tf2, and `gz.transport13` adapters. Keep Gazebo physical attachment and MoveIt Planning Scene attachment as separately observed side effects. Port behavior vertically, proving each external boundary before adding the next one.

**Tech Stack:** Ubuntu 24.04, ROS 2 Jazzy, Python 3.12, `ament_python`, `rclpy`, Gazebo Harmonic / Gazebo Sim 8, `gz.transport13`, `ros_gz_sim`, `gz_ros2_control`, MoveIt 2 services/actions, `pytest`, and `launch_testing` for live launch contracts.

## Global Constraints

- Work directly on ai-station in `/data/work/ws_moveit/.worktrees/refactor-optimization-r3`; do not SSH to ai-station from the implementation agent.
- Use tmux session `codex` as the coding-control channel. Do not operate or interrupt `codex-cua`.
- Preserve every pre-existing R3 modification and untracked file. Never reset, stash, clean, overwrite, or include them in a Python-rewrite commit.
- Stage only paths named by the current task. Before each commit run `git status --short`, `git diff --cached --name-status`, and `git diff --cached --check`.
- The new package must not depend on `so101_gazebo_demo`, `pick_place_common`, their executables, their shared libraries, or their installed assets.
- The package is simulation-only. Do not connect it to real hardware.
- Launch defaults remain `run_mode:=dry_run` and `start_simulation:=false`.
- Web Teleop, workspace sampler, calibration, motion-matrix validation, video helpers, camera helpers, GUI tiling helpers, and geometry-generation utilities are out of scope.
- Keep the fixed moving-pad penetration ceiling `0.000800002 m`, the R3 approximately `0.4 mm` moving-jaw retraction, q6 semantics, containment assertions, 2 mm micro-lift, fixed 6.0 mrad seating preload, and physical-grasp gates unchanged.
- Do not load the original C++ attachment collision plugin, create a replacement C++ plugin, permanently disable pre-attach collisions, or emulate physical attachment by repeatedly teleporting the task object.
- Runtime evidence belongs in a directory created by `mktemp -d /tmp/so101-py-XXXXXXXX`; never write logs, checkpoints, screenshots, or generated artifacts into the source package.
- Source ROS commands in zsh with `source /opt/ros/jazzy/setup.zsh`; after each build, source `/data/work/ws_moveit/.worktrees/refactor-optimization-r3/install/setup.zsh`.
- The approved design is `docs/superpowers/specs/2026-08-07-so101-gazebo-demo-py-design.md`.

---

### Task 1: Freeze the R3 Reference and Scaffold an Independent Package

**Files:**
- Create: `src/so101_gazebo_demo_py/package.xml`
- Create: `src/so101_gazebo_demo_py/setup.py`
- Create: `src/so101_gazebo_demo_py/setup.cfg`
- Create: `src/so101_gazebo_demo_py/resource/so101_gazebo_demo_py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/__init__.py`
- Create: `src/so101_gazebo_demo_py/docs/provenance.json`
- Create: `src/so101_gazebo_demo_py/test/test_package_independence.py`
- Create: `src/so101_gazebo_demo_py/test/test_provenance.py`

**Interfaces:**
- Consumes: live source and dirty-state evidence from `src/so101_gazebo_demo` in the R3 worktree.
- Produces: installable package `so101_gazebo_demo_py`; provenance schema `{"reference_head": str, "reference_branch": str, "files": [{"source": str, "destination": str, "source_dirty": bool, "source_sha256": str, "destination_sha256": str}]}`.

- [ ] **Step 1: Capture baseline evidence without changing the checkout**

Run:

```bash
cd /data/work/ws_moveit/.worktrees/refactor-optimization-r3
evidence_dir=/tmp/so101-py-baseline-$(date +%Y%m%d-%H%M%S)
mkdir -p "$evidence_dir"
git rev-parse HEAD | tee "$evidence_dir/reference-head.txt"
git branch --show-current | tee "$evidence_dir/reference-branch.txt"
git status --short | tee "$evidence_dir/reference-status.txt"
tmux list-sessions | tee "$evidence_dir/tmux-sessions.txt"
pgrep -af 'gz sim|move_group|rviz2|pick_place_state_machine' | tee "$evidence_dir/processes.txt" || true
```

Expected: HEAD and branch are recorded; the existing R3 dirty files remain visible; no process is stopped.

- [ ] **Step 2: Write failing independence and provenance tests**

Create tests that assert:

```python
from pathlib import Path
import json
import xml.etree.ElementTree as ET

PACKAGE = Path(__file__).parents[1]

def test_package_name_and_build_type() -> None:
    root = ET.parse(PACKAGE / "package.xml").getroot()
    assert root.findtext("name") == "so101_gazebo_demo_py"
    assert root.find("./export/build_type").text == "ament_python"

def test_forbidden_runtime_dependencies_absent() -> None:
    text = "\n".join(
        path.read_text(errors="ignore")
        for path in PACKAGE.rglob("*")
        if path.is_file() and ".pyc" not in path.name
    )
    assert "<depend>so101_gazebo_demo</depend>" not in text
    assert "<depend>pick_place_common</depend>" not in text
    assert "get_package_share_directory(\"so101_gazebo_demo\")" not in text
    assert "ros2 run so101_gazebo_demo " not in text

def test_provenance_has_exact_reference_and_hashes() -> None:
    payload = json.loads((PACKAGE / "docs/provenance.json").read_text())
    assert len(payload["reference_head"]) == 40
    assert payload["reference_branch"] == "codex/refactor-optimization-r3"
    assert payload["files"] == []
```

- [ ] **Step 3: Run tests to verify RED**

Run:

```bash
cd /data/work/ws_moveit/.worktrees/refactor-optimization-r3
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_package_independence.py src/so101_gazebo_demo_py/test/test_provenance.py
```

Expected: failure because package metadata and provenance do not exist.

- [ ] **Step 4: Add the minimal ament_python scaffold**

Use package metadata with these dependencies: `ament_index_python`, `control_msgs`, `controller_manager_msgs`, `geometry_msgs`, `launch`, `launch_ros`, `moveit_msgs`, `rclpy`, `ros_gz_interfaces`, `rosgraph_msgs`, `sensor_msgs`, `shape_msgs`, `std_msgs`, `std_srvs`, `tf2_msgs`, `tf2_ros`, `trajectory_msgs`, `xacro`, `robot_state_publisher`, `rviz2`, `ros_gz_sim`, `ros_gz_bridge`, `gz_ros2_control`, `controller_manager`, `joint_state_broadcaster`, `joint_trajectory_controller`, `moveit_configs_utils`, `moveit_ros_move_group`, `moveit_simple_controller_manager`, and `python3-yaml`. Use `<build_type>ament_python</build_type>`. Because this ai-station rosdep database has no key for the already installed `gz.transport13`/`gz.msgs10` Python bindings, add a startup preflight that imports both and reports the missing Ubuntu binding explicitly instead of inventing a package.xml dependency key.

`setup.py` must install package metadata now and add asset directories only as they are created by later tasks. Define no console scripts until their modules exist.

Initialize `provenance.json` with the captured branch/HEAD and an empty `files` array. The test deliberately requires an empty array at this stage.

- [ ] **Step 5: Verify GREEN and build isolation**

Run:

```bash
cd /data/work/ws_moveit/.worktrees/refactor-optimization-r3
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_package_independence.py src/so101_gazebo_demo_py/test/test_provenance.py
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_gazebo_demo_py --symlink-install
source install/setup.zsh
ros2 pkg prefix so101_gazebo_demo_py
```

Expected: tests pass, build succeeds, and prefix is under this worktree's `install/so101_gazebo_demo_py`.

- [ ] **Step 6: Commit only Task 1 paths**

```bash
git add -- src/so101_gazebo_demo_py/package.xml src/so101_gazebo_demo_py/setup.py src/so101_gazebo_demo_py/setup.cfg src/so101_gazebo_demo_py/resource src/so101_gazebo_demo_py/so101_gazebo_demo_py/__init__.py src/so101_gazebo_demo_py/docs/provenance.json src/so101_gazebo_demo_py/test/test_package_independence.py src/so101_gazebo_demo_py/test/test_provenance.py
git diff --cached --check
git diff --cached --name-status
git commit -m "build(so101_py): scaffold independent ROS package"
```

---

### Task 2: Port the ROS-Free Domain Model and Workflow

**Files:**
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/domain.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/workflow.py`
- Create: `src/so101_gazebo_demo_py/test/test_domain.py`
- Create: `src/so101_gazebo_demo_py/test/test_workflow.py`

**Interfaces:**
- Consumes: no runtime dependency; state names and transitions characterized from R3.
- Produces: `State`, `RunStatus`, `RunMode`, `ActionStatus`, `FailureCategory`, `Failure`, `ActionResult`, `RunRequest`, `RunResult`, `WorkflowDefinition`, `SO101_WORKFLOW`, `resolve_transition(state, outcome) -> State`.

- [ ] **Step 1: Write failing enum and transition tests**

Tests must instantiate every state listed in the design, assert exact string values, assert the full transition table from `so101_workflow.cpp`, assert terminal states `{DONE, ERROR}`, force-continue states `{VALIDATION_FAILED}`, and plan-only states `{MOVE_ABOVE_OBJECT, DESCEND, LIFT, MOVE_ABOVE_PLACE, DESCEND_TO_PLACE, RETREAT}`.

Include:

```python
def test_physical_grasp_precedes_attachment() -> None:
    assert resolve_transition(State.WAIT_GRASP_STABLE, ActionStatus.SUCCEEDED) is State.MICRO_LIFT
    assert resolve_transition(State.MICRO_LIFT, ActionStatus.SUCCEEDED) is State.WAIT_MICRO_LIFT_STABLE
    assert resolve_transition(State.WAIT_MICRO_LIFT_STABLE, ActionStatus.SUCCEEDED) is State.VERIFY_PHYSICAL_GRASP
    assert resolve_transition(State.VERIFY_PHYSICAL_GRASP, ActionStatus.SUCCEEDED) is State.ATTACH_GAZEBO
```

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_domain.py src/so101_gazebo_demo_py/test/test_workflow.py
```

Expected: import failure for the two modules.

- [ ] **Step 3: Implement exact string enums and frozen dataclasses**

Use `enum.StrEnum` and `@dataclass(frozen=True, slots=True)`. `Failure.metrics` is `Mapping[str, float]`; `RunResult.state_trace` is `tuple[State, ...]`. Validate the workflow on module import: every nonterminal state has two destinations, all destinations exist, `VALIDATION_FAILED` is not an action state, and every plan-only state is an action state.

- [ ] **Step 4: Run GREEN and prove no ROS import**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_domain.py src/so101_gazebo_demo_py/test/test_workflow.py
python3 -c 'import sys; from so101_gazebo_demo_py import workflow; assert "rclpy" not in sys.modules'
```

- [ ] **Step 5: Commit**

```bash
git add -- src/so101_gazebo_demo_py/so101_gazebo_demo_py/domain.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/workflow.py src/so101_gazebo_demo_py/test/test_domain.py src/so101_gazebo_demo_py/test/test_workflow.py
git diff --cached --check
git commit -m "feat(so101_py): define pick-place workflow"
```

---

### Task 3: Copy Runtime Assets and Prove the Package Is Self-Contained

**Files:**
- Create: `src/so101_gazebo_demo_py/{config,urdf,meshes,worlds,rviz}/**`
- Modify: `src/so101_gazebo_demo_py/setup.py`
- Modify: `src/so101_gazebo_demo_py/docs/provenance.json`
- Modify: `src/so101_gazebo_demo_py/test/test_provenance.py`
- Create: `src/so101_gazebo_demo_py/test/test_asset_closure.py`

**Interfaces:**
- Consumes: exact R3 assets required by display/controller/Gazebo/MoveIt/pick-place.
- Produces: package-local asset closure and a verified per-file provenance ledger.

- [ ] **Step 1: Write RED tests for required installed assets and forbidden references**

Assert existence of the six core YAML configs, all Xacro files, required SO-101 mesh trees, `worlds/so101_pick_place.sdf`, `config/so101.srdf`, and RViz config. Parse text assets and reject `package://so101_gazebo_demo/`, `libso101_attachment_collision_system.so`, and absolute `/data/work` paths.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_asset_closure.py src/so101_gazebo_demo_py/test/test_provenance.py
```

- [ ] **Step 3: Copy only in-scope assets and rewrite package URIs**

Copy from `src/so101_gazebo_demo`:

```text
config/initial_positions.yaml
config/joint_limits.yaml
config/kinematics.yaml
config/moveit_controllers.yaml
config/moveit.rviz
config/ompl_planning.yaml
config/pilz_cartesian_limits.yaml
config/so101_controllers.yaml
config/so101.srdf
config/motion_policies/light_cup_wall_pick.yaml
config/task_objects/light_plastic_cup.yaml
config/validation_policies/light_cup_wall_pick.yaml
urdf/*.xacro
meshes/so101/**
worlds/so101_pick_place.sdf
rviz/display.rviz
```

Do not copy caches. Rewrite package URIs to `package://so101_gazebo_demo_py/`. In `so101_gazebo.xacro`, retain `gz-sim-detachable-joint-system` and remove the custom attachment-collision plugin block.

Generate provenance entries from the source bytes before copy and destination bytes after package-URI/plugin edits. For edited text assets, store both `source_sha256` and `destination_sha256`; for unchanged assets they must match. For each entry, run `git status --short -- "$source_path"` and set `source_dirty` to whether that command returns a status line.

- [ ] **Step 4: Install assets and run GREEN**

Update `setup.py` `data_files` using deterministic `glob` traversal. Run:

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_asset_closure.py src/so101_gazebo_demo_py/test/test_provenance.py
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_gazebo_demo_py --symlink-install
source install/setup.zsh
python3 -c 'from ament_index_python.packages import get_package_share_directory; import pathlib; p=pathlib.Path(get_package_share_directory("so101_gazebo_demo_py")); assert (p/"urdf/so101.urdf.xacro").is_file()'
```

- [ ] **Step 5: Commit**

```bash
git add -- src/so101_gazebo_demo_py/config src/so101_gazebo_demo_py/urdf src/so101_gazebo_demo_py/meshes src/so101_gazebo_demo_py/worlds src/so101_gazebo_demo_py/rviz src/so101_gazebo_demo_py/setup.py src/so101_gazebo_demo_py/docs/provenance.json src/so101_gazebo_demo_py/test/test_provenance.py src/so101_gazebo_demo_py/test/test_asset_closure.py
git diff --cached --check
git commit -m "feat(so101_py): add self-contained simulation assets"
```

---

### Task 4: Port Policy Loading, Profile Construction, and Fingerprint Binding

**Files:**
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/policy_config.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/profile.py`
- Create: `src/so101_gazebo_demo_py/test/test_policy_config.py`
- Create: `src/so101_gazebo_demo_py/test/test_profile.py`

**Interfaces:**
- Consumes: the three package-local YAML files.
- Produces: `load_policy_bundle(object_path: Path, motion_path: Path, validation_path: Path) -> PolicyBundle`; `PolicyBundle.sha256: str`; `SO101Profile.from_bundle(bundle: PolicyBundle) -> SO101Profile`.

- [ ] **Step 1: Write RED tests using the installed YAML values**

Assert schema version, matching `policy_id`/`object_id`, five arm joints named `1` through `5`, gripper joint `6`, finite numeric arrays, exact waypoint lengths, state coverage, q6 bounds, and deterministic canonical JSON hashing with sorted keys and compact separators.

Assert `SO101Profile` binds configured q6 values and fixed names: world `so101_pick_place`, planning group `arm`, TCP `so101_tcp`, attach/detach topics, object `plastic_cup`, and link `body`.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_policy_config.py src/so101_gazebo_demo_py/test/test_profile.py
```

- [ ] **Step 3: Implement strict typed loaders**

Use frozen dataclasses for `Pose3D`, `TaskObjectConfig`, `StateMotionConfig`, `MotionPolicyConfig`, `StateValidationConfig`, `ValidationPolicyConfig`, `PolicyBundle`, and `SO101Profile`. Reject unknown state names, missing keys, booleans in numeric fields, NaN/Inf, mismatched IDs, non-six-dimensional poses, and wrong joint-vector lengths with `ConfigurationError(code: str, message: str)`.

Fingerprint the normalized three-document bundle with SHA-256. Do not hash filesystem paths or YAML formatting.

- [ ] **Step 4: Run GREEN**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_policy_config.py src/so101_gazebo_demo_py/test/test_profile.py
```

- [ ] **Step 5: Commit**

```bash
git add -- src/so101_gazebo_demo_py/so101_gazebo_demo_py/policy_config.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/profile.py src/so101_gazebo_demo_py/test/test_policy_config.py src/so101_gazebo_demo_py/test/test_profile.py
git diff --cached --check
git commit -m "feat(so101_py): load fingerprinted robot policies"
```

---

### Task 5: Implement Durable Checkpoints and Physical-Grasp Sidecars

**Files:**
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/checkpoint.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/grasp/evidence_store.py`
- Create: `src/so101_gazebo_demo_py/test/test_checkpoint.py`
- Create: `src/so101_gazebo_demo_py/test/test_grasp_evidence_store.py`

**Interfaces:**
- Produces: `Checkpoint`, `CheckpointPhase`, `ExpectedWorldState`, `FileCheckpointStore.commit(checkpoint) -> Failure | None`, `FileCheckpointStore.load() -> tuple[Checkpoint | None, Failure | None]`, `RetryPhase`, `PhysicalGraspEvidence`, `FilePhysicalGraspEvidenceStore`.

- [ ] **Step 1: Write RED tests from the R3 schema**

Cover schema version 3 fields: `run_id`, `sequence`, `source_mode`, `phase`, `last_completed_state`, `failed_state`, `original_failure`, `next_state`, `expected`, `policy_bundle_sha256`, `simulation_session_id`, and `resumable`. Cover the sidecar fields `attempt_index`, `contact_missing_count`, `current_reclose_target_q6`, `micro_lift_preload_target_q6`, and retry phase.

Use monkeypatching of `os.replace` and `os.fsync` to assert atomic replacement, file mode `0o600`, directory mode `0o700`, corruption errors, and unchanged prior file after a failed commit.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_checkpoint.py src/so101_gazebo_demo_py/test/test_grasp_evidence_store.py
```

- [ ] **Step 3: Implement strict JSON codecs and durable stores**

Serialize enums by exact string value. Create the same-directory temporary file with `os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)`, write the complete UTF-8 payload with repeated `os.write` calls until all bytes are consumed, call `os.fsync(fd)`, close it, call `os.replace(temp_path, final_path)`, open the parent directory read-only, fsync the directory descriptor, and close it. Reject extra/missing top-level fields and nonfinite metrics. Map errors to the R3 codes such as `CHECKPOINT_NOT_FOUND`, `CHECKPOINT_PARSE_FAILED`, `CHECKPOINT_INCOMPATIBLE`, `CHECKPOINT_INVALID_ENUM`, `CHECKPOINT_INVALID_DATA`, and write/rename/fsync failures.

- [ ] **Step 4: Run GREEN**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_checkpoint.py src/so101_gazebo_demo_py/test/test_grasp_evidence_store.py
```

- [ ] **Step 5: Commit**

```bash
git add -- src/so101_gazebo_demo_py/so101_gazebo_demo_py/checkpoint.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/grasp/evidence_store.py src/so101_gazebo_demo_py/test/test_checkpoint.py src/so101_gazebo_demo_py/test/test_grasp_evidence_store.py
git diff --cached --check
git commit -m "feat(so101_py): persist resumable workflow state"
```

---

### Task 6: Build the Deterministic Runner and Dry-Run CLI

**Files:**
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/runner.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/cli/pick_place_state_machine.py`
- Modify: `src/so101_gazebo_demo_py/setup.py`
- Create: `src/so101_gazebo_demo_py/test/test_runner.py`
- Create: `src/so101_gazebo_demo_py/test/test_pick_place_cli.py`

**Interfaces:**
- Consumes: domain, workflow, checkpoint, policies.
- Produces: `StateAction` protocol with `run(context: ExecutionContext) -> ActionResult`; `StateMachineRunner.run(request: RunRequest) -> RunResult`; console script `pick_place_state_machine`.

- [ ] **Step 1: Write RED tests for full dry-run, injected failure, step, stop, resume, plan-only rejection, and force-continue gate**

The fake action registry returns success unless `fail_at` matches. Assert the full successful trace begins with `IDLE`, follows every forward state, and ends at `DONE`. Assert transition count never exceeds 100. Assert `--force-continue` outside `VALIDATION_FAILED` fails closed.

Use subprocess CLI tests and require parseable lines:

```text
status=DONE
current_state=DONE
transition_count=19
state_trace=IDLE,PREPARE_OPEN_GRIPPER,MOVE_ABOVE_OBJECT,DESCEND,CLOSE_GRIPPER,WAIT_GRASP_STABLE,MICRO_LIFT,WAIT_MICRO_LIFT_STABLE,VERIFY_PHYSICAL_GRASP,ATTACH_GAZEBO,ATTACH_MOVEIT,LIFT,MOVE_ABOVE_PLACE,DESCEND_TO_PLACE,OPEN_GRIPPER,DETACH_GAZEBO,DETACH_MOVEIT,SYNC_WORLD_OBJECT,RETREAT,DONE
```

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_runner.py src/so101_gazebo_demo_py/test/test_pick_place_cli.py
```

- [ ] **Step 3: Implement runner and CLI without importing rclpy in dry-run mode**

Use `argparse` with the exact approved arguments. Generate a nonempty session ID only for fresh execute runs that need it. Map `DONE`, `PLAN_ONLY_COMPLETE`, and `CHECKPOINT_COMPLETE` to exit 0; map configuration/runtime `ERROR` to exit 1; map CLI syntax errors to argparse exit 2.

Register deterministic no-side-effect actions for every action state in `dry_run`. Persist checkpoint after each accepted transition and before returning a requested step/stop boundary.

- [ ] **Step 4: Run GREEN and installed CLI smoke test**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_runner.py src/so101_gazebo_demo_py/test/test_pick_place_cli.py
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_gazebo_demo_py --symlink-install
source install/setup.zsh
ros2 run so101_gazebo_demo_py pick_place_state_machine --mode dry_run --checkpoint /tmp/so101-py-dry-run.json
```

Expected: exit 0 and `current_state=DONE`.

- [ ] **Step 5: Commit**

```bash
git add -- src/so101_gazebo_demo_py/so101_gazebo_demo_py/runner.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/cli/pick_place_state_machine.py src/so101_gazebo_demo_py/setup.py src/so101_gazebo_demo_py/test/test_runner.py src/so101_gazebo_demo_py/test/test_pick_place_cli.py
git diff --cached --check
git commit -m "feat(so101_py): run deterministic dry-run workflow"
```

---

### Task 7: Port Display, Controller, Gazebo, and MoveIt Launch Composition

**Files:**
- Create: `src/so101_gazebo_demo_py/launch/so101_display.launch.py`
- Create: `src/so101_gazebo_demo_py/launch/so101_controller.launch.py`
- Create: `src/so101_gazebo_demo_py/launch/so101_gazebo.launch.py`
- Create: `src/so101_gazebo_demo_py/launch/so101_move_group_headless.launch.py`
- Create: `src/so101_gazebo_demo_py/launch/so101_moveit.launch.py`
- Modify: `src/so101_gazebo_demo_py/setup.py`
- Create: `src/so101_gazebo_demo_py/test/test_launch_contract.py`

**Interfaces:**
- Produces: the five approved stack launch files, all resolving only package-local assets.

- [ ] **Step 1: Write RED launch-contract tests**

Import each launch module with `importlib.util`, call `generate_launch_description`, and inspect entities. Assert package name is `so101_gazebo_demo_py`, Gazebo defaults headless false, MoveIt uses group `arm`, controller spawners name `joint_state_broadcaster`, `arm_controller`, and `gripper_controller`, and no old package path appears in source.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_launch_contract.py
```

- [ ] **Step 3: Port launch composition with package-local lookups**

Translate the five R3 launch files, replacing package lookup and executable names only where the implementation is Python-owned. Preserve robot description generation, semantic description, kinematics, joint limits, OMPL/Pilz config, controller manager, `ros_gz_sim`, bridge mappings, and safe defaults.

- [ ] **Step 4: Build, inspect arguments, and run non-GUI Xacro checks**

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_gazebo_demo_py --symlink-install
source install/setup.zsh
ros2 launch so101_gazebo_demo_py so101_gazebo.launch.py --show-args
ros2 launch so101_gazebo_demo_py so101_moveit.launch.py --show-args
xacro $(ros2 pkg prefix so101_gazebo_demo_py)/share/so101_gazebo_demo_py/urdf/so101.urdf.xacro use_gazebo:=true >/tmp/so101-py-robot.urdf
check_urdf /tmp/so101-py-robot.urdf
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_launch_contract.py
```

- [ ] **Step 5: Commit**

```bash
git add -- src/so101_gazebo_demo_py/launch src/so101_gazebo_demo_py/setup.py src/so101_gazebo_demo_py/test/test_launch_contract.py
git diff --cached --check
git commit -m "feat(so101_py): launch standalone simulation stack"
```

---

### Task 8: Prove the Pure-Python Gazebo Attachment Boundary

**Files:**
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/gazebo/transport.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/gazebo/attachment.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/gazebo/observer.py`
- Conditional create after a failed built-in DetachableJoint gate and a proven compatible Python System Loader: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/gazebo/collision_system.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/cli/gazebo_attachment_state_relay.py`
- Modify: `src/so101_gazebo_demo_py/setup.py`
- Create: `src/so101_gazebo_demo_py/test/test_gazebo_attachment.py`
- Conditional create with the Python System Loader fallback: `src/so101_gazebo_demo_py/test/test_gazebo_collision_system.py`
- Create: `src/so101_gazebo_demo_py/test/headless/test_gazebo_attachment_live.py`

**Interfaces:**
- Produces: `GazeboTransport.publish_empty(topic: str) -> bool`; `GazeboAttachmentClient.set_attached(attached: bool, timeout_s: float) -> ActionResult`; `GazeboWorldObserver.observe() -> WorldObservation`; relay executable publishing durable attachment state.

- [ ] **Step 1: Write deterministic RED tests with a fake transport**

Assert raw `attached`/`detached` events reduce to durable state, invalid events are ignored, attach and detach use distinct topics, convergence waits for the requested durable state, and timeout returns category `GAZEBO_ATTACHMENT` with a stable code.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_gazebo_attachment.py
```

- [ ] **Step 3: Implement `gz.transport13` adapters**

Use `gz.transport13.Node`, `gz.msgs10.empty_pb2.Empty`, and `gz.msgs10.stringmsg_pb2.StringMsg`. Keep Gazebo callbacks thread-safe with `threading.Lock` and `threading.Event`; do not spin a second rclpy executor inside a callback. Publish relay readiness on `/so101/object_attachment_relay_ready` with transient-local QoS.

- [ ] **Step 4: Run the built-in DetachableJoint live risk gate**

Launch an isolated stack in tmux with unique `ROS_DOMAIN_ID`, `GZ_PARTITION`, and `ROS_LOG_DIR`. The live test must:

1. record detached object pose;
2. establish the configured bilateral contact condition;
3. publish attach and observe durable `attached`;
4. move the arm through the 2 mm lift and a bounded hold;
5. prove the object follows the TCP without solver explosion or loss;
6. detach, prove durable `detached`, and prove the object settles independently.

Save commands, exit codes, joint/TF/object-pose samples, attachment events, contacts, and logs under the evidence directory.

Run:

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/headless/test_gazebo_attachment_live.py -s
```

Expected: PASS using only `gz-sim-detachable-joint-system`; `pgrep -af` and loaded-plugin logs show no `libso101_attachment_collision_system.so`.

- [ ] **Step 5: Apply the documented fallback only if Step 4 fails**

Before creating fallback code, record the failing physical assertion. Test `gz.sim8` import inside the exact ROS/Gazebo launch environment and record linked `libgz-sim8`. Use a package-owned Python System Loader collision component only if import and runtime provenance match and the live test then passes. If ABI remains split between system 8.14 and ROS vendor 8.11, or physics remains invalid, stop execution and report this design gate; do not continue to later tasks.

- [ ] **Step 6: Run unit GREEN and commit only after the live gate passes**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_gazebo_attachment.py src/so101_gazebo_demo_py/test/headless/test_gazebo_attachment_live.py -s
git add -- src/so101_gazebo_demo_py/so101_gazebo_demo_py/gazebo src/so101_gazebo_demo_py/so101_gazebo_demo_py/cli/gazebo_attachment_state_relay.py src/so101_gazebo_demo_py/setup.py src/so101_gazebo_demo_py/test/test_gazebo_attachment.py src/so101_gazebo_demo_py/test/headless/test_gazebo_attachment_live.py
git diff --cached --check
git commit -m "feat(so101_py): control physical Gazebo attachment"
```

---

### Task 9: Implement MoveIt Planning, Execution, and Robot-State Evidence

**Files:**
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/moveit/planning.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/moveit/robot_state.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/motion/planner.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/motion/executor.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/motion/evidence.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/diagnostics.py`
- Create: `src/so101_gazebo_demo_py/test/test_moveit_planning.py`
- Create: `src/so101_gazebo_demo_py/test/test_motion_validation.py`
- Create: `src/so101_gazebo_demo_py/test/test_planning_diagnostics.py`

**Interfaces:**
- Produces: `MoveItPlanningClient.plan_joint_path(request: JointPlanRequest) -> PlanOutcome`; `MoveItExecutionClient.execute(trajectory: RobotTrajectory, timeout_s: float) -> ActionResult`; `RobotStateObserver.sample(timeout_s: float) -> RobotStateEvidence`; `MotionPlanner.plan(state: State, profile: SO101Profile, policy: MotionPolicyConfig) -> PlanOutcome`; `validate_plan(state: State, trajectory: RobotTrajectory, evidence: RobotStateEvidence, profile: SO101Profile, policy: ValidationPolicyConfig) -> Failure | None`.

- [ ] **Step 1: Write RED service/action and validation tests**

Use fake `GetMotionPlan` and `ExecuteTrajectory` clients. Cover unavailable service, rejected goal, result timeout, MoveIt error code, empty trajectory, missing joints, wrong start state, endpoint tolerance, waypoint ladder, max joint jump, minimum duration, axial monotonicity, lateral deviation, allowed/forbidden contacts, request-scoped cancellation, and diagnostics file permissions.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_moveit_planning.py src/so101_gazebo_demo_py/test/test_motion_validation.py src/so101_gazebo_demo_py/test/test_planning_diagnostics.py
```

- [ ] **Step 3: Implement direct rclpy MoveIt clients**

Construct `moveit_msgs.srv.GetMotionPlan` requests with planning group `arm`, current observed robot state, ordered joint constraints, velocity/acceleration scaling, one planning attempt, and bounded planning time. Use `moveit_msgs.action.ExecuteTrajectory` for execution. Store the goal handle owned by the current request and cancel only that handle on timeout.

Write diagnostics only for failed requests, under an explicitly configured directory with modes `0o700`/`0o600`. Diagnostics failure must not replace the planning failure.

- [ ] **Step 4: Run GREEN and a plan-only smoke test against a live move_group**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_moveit_planning.py src/so101_gazebo_demo_py/test/test_motion_validation.py src/so101_gazebo_demo_py/test/test_planning_diagnostics.py
ros2 service type /plan_kinematic_path
ros2 action info /execute_trajectory
```

Use a minimal Python probe from the installed package to plan `MOVE_ABOVE_OBJECT`; assert a nonempty trajectory and do not execute it.

- [ ] **Step 5: Commit**

```bash
git add -- src/so101_gazebo_demo_py/so101_gazebo_demo_py/moveit/planning.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/moveit/robot_state.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/motion src/so101_gazebo_demo_py/so101_gazebo_demo_py/diagnostics.py src/so101_gazebo_demo_py/test/test_moveit_planning.py src/so101_gazebo_demo_py/test/test_motion_validation.py src/so101_gazebo_demo_py/test/test_planning_diagnostics.py
git diff --cached --check
git commit -m "feat(so101_py): plan and execute MoveIt trajectories"
```

---

### Task 10: Implement Gripper Commands, Physical-Grasp Validation, and Bounded Retry

**Files:**
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/motion/gripper.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/grasp/stabilizer.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/grasp/validator.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/grasp/retry.py`
- Create: `src/so101_gazebo_demo_py/test/test_gripper.py`
- Create: `src/so101_gazebo_demo_py/test/test_grasp_stabilizer.py`
- Create: `src/so101_gazebo_demo_py/test/test_grasp_validator.py`
- Create: `src/so101_gazebo_demo_py/test/test_grasp_retry.py`

**Interfaces:**
- Produces: `GripperClient.command(q6: float, duration_s: float, timeout_s: float) -> ActionResult`; `PhysicalGraspStabilizer.capture(session_id: str, window_s: float) -> StabilizedGraspEvidence`; `PhysicalGraspValidator.validate(before: StabilizedGraspEvidence, after: StabilizedGraspEvidence) -> ActionResult`; `PhysicalGraspRetryCoordinator.retry(failure: Failure, evidence: PhysicalGraspEvidence) -> ActionResult`.

- [ ] **Step 1: Write RED tests for the exact physical contract**

Cover bilateral fixed-finger and moving-jaw contact, required wall, forbidden rim/bottom/opposite-wall contact, penetration ceiling, q6 position/velocity stop, contact height, object drift, 2 mm world-Z lift, session/fingerprint binding, retryable versus nonretryable failure codes, five total attempts, 1.0 mrad contact-missing tightening, 4.0 mrad cap, unchanged contact-present q6, and fixed 6.0 mrad seating preload.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_gripper.py src/so101_gazebo_demo_py/test/test_grasp_stabilizer.py src/so101_gazebo_demo_py/test/test_grasp_validator.py src/so101_gazebo_demo_py/test/test_grasp_retry.py
```

- [ ] **Step 3: Implement gripper action and evidence windows**

Send joint `6` through `/gripper_controller/follow_joint_trajectory`. Treat the configured contact-stop abort as potentially acceptable only when fresh bilateral contact, bounded penetration, stopped q6, and requested target identity all agree. Sample evidence in bounded monotonic-time windows; reject stale or cross-session samples.

Persist retry phase before each side effect: `OPEN_PENDING`, `DESCEND_PENDING`, `CLOSE_PENDING`, `LIFT_PENDING`, or `VERIFY_PENDING`. Clear the sidecar only after verified success or explicit fresh-run initialization.

- [ ] **Step 4: Run GREEN**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_gripper.py src/so101_gazebo_demo_py/test/test_grasp_stabilizer.py src/so101_gazebo_demo_py/test/test_grasp_validator.py src/so101_gazebo_demo_py/test/test_grasp_retry.py
```

- [ ] **Step 5: Commit**

```bash
git add -- src/so101_gazebo_demo_py/so101_gazebo_demo_py/motion/gripper.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/grasp src/so101_gazebo_demo_py/test/test_gripper.py src/so101_gazebo_demo_py/test/test_grasp_stabilizer.py src/so101_gazebo_demo_py/test/test_grasp_validator.py src/so101_gazebo_demo_py/test/test_grasp_retry.py
git diff --cached --check
git commit -m "feat(so101_py): validate and retry physical grasps"
```

---

### Task 11: Implement Planning Scene, World Reset, and Recovery

**Files:**
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/moveit/scene.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/gazebo/reset.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/recovery/policy.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/recovery/coordinator.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/cli/reset_so101_world.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/cli/so101_moveit_scene.py`
- Modify: `src/so101_gazebo_demo_py/setup.py`
- Create: `src/so101_gazebo_demo_py/test/test_moveit_scene.py`
- Create: `src/so101_gazebo_demo_py/test/test_world_reset.py`
- Create: `src/so101_gazebo_demo_py/test/test_recovery.py`

**Interfaces:**
- Produces: `MoveItSceneClient.attach_task_object(object_id: str, link_name: str, touch_links: tuple[str, ...]) -> ActionResult`; `MoveItSceneClient.detach_task_object(object_id: str, world_pose: Pose3D) -> ActionResult`; `MoveItSceneClient.observe(timeout_s: float) -> SceneObservation`; `WorldResetCoordinator.reset() -> ActionResult`; `RecoveryPolicy.path_for(failed_state: State, evidence: ExpectedWorldState) -> tuple[State, ...]`.

- [ ] **Step 1: Write RED scene and recovery tests**

Assert Gazebo attach precedes MoveIt attach; Gazebo detach precedes MoveIt detach; sync restores the object to the world at the final Gazebo pose; attached link is `gripper`; touch links are exactly `gripper` and `jaw`; table and pedestal remain required world objects. Verify recovery skips side effects never observed and orders established side effects in reverse.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_moveit_scene.py src/so101_gazebo_demo_py/test/test_world_reset.py src/so101_gazebo_demo_py/test/test_recovery.py
```

- [ ] **Step 3: Implement MoveIt services and reset orchestration**

Use `ApplyPlanningScene` and `GetPlanningScene`. Require convergence after every apply call. Reset sequence is: command Gazebo detach, wait detached, set object pose with `ros_gz_interfaces/srv/SetEntityPose`, restore Planning Scene world membership, return arm joints to five zeros, return q6 home, then prove stationary object, controller convergence, TCP/home convergence, and scene membership.

- [ ] **Step 4: Run GREEN and installed CLI help checks**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_moveit_scene.py src/so101_gazebo_demo_py/test/test_world_reset.py src/so101_gazebo_demo_py/test/test_recovery.py
ros2 run so101_gazebo_demo_py reset_so101_world --help
ros2 run so101_gazebo_demo_py so101_moveit_scene --help
```

- [ ] **Step 5: Commit**

```bash
git add -- src/so101_gazebo_demo_py/so101_gazebo_demo_py/moveit/scene.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/gazebo/reset.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/recovery src/so101_gazebo_demo_py/so101_gazebo_demo_py/cli/reset_so101_world.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/cli/so101_moveit_scene.py src/so101_gazebo_demo_py/setup.py src/so101_gazebo_demo_py/test/test_moveit_scene.py src/so101_gazebo_demo_py/test/test_world_reset.py src/so101_gazebo_demo_py/test/test_recovery.py
git diff --cached --check
git commit -m "feat(so101_py): synchronize scene and recovery"
```

---

### Task 12: Compose the Execute Runtime and Pick-Place Launch

**Files:**
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/runtime.py`
- Modify: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/cli/pick_place_state_machine.py`
- Create: `src/so101_gazebo_demo_py/launch/so101_pick_place.launch.py`
- Modify: `src/so101_gazebo_demo_py/setup.py`
- Create: `src/so101_gazebo_demo_py/test/test_runtime.py`
- Create: `src/so101_gazebo_demo_py/test/test_pick_place_launch.py`

**Interfaces:**
- Consumes: every adapter and protocol from Tasks 6 through 11.
- Produces: `build_runtime(node, profile, policies, options) -> Runtime`; complete `dry_run`, `plan_only`, and `execute` behavior; installed pick-place launch.

- [ ] **Step 1: Write RED integration tests with fakes**

Register concrete action ownership for every workflow state. Assert each state calls only its intended boundary. Verify planning without execution in plan-only, execution plus evidence in execute, force-continue freshness rules, checkpoint updates, recovery dispatch, and terminal exit codes.

Launch tests must assert arguments and defaults from the design, package-local config paths, conditional simulation/move_group inclusion, and the Python console executable.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_runtime.py src/so101_gazebo_demo_py/test/test_pick_place_launch.py
```

- [ ] **Step 3: Compose runtime actions and launch**

Create one rclpy node and one `MultiThreadedExecutor`; adapter callbacks must not create nested executors. Build state actions from explicit dependencies. `plan_only_state` plans exactly one supported state. `execute` performs readiness checks before the first side effect. `start_simulation:=true` includes the Python package's Gazebo and headless move_group launches.

- [ ] **Step 4: Run GREEN, rebuild, and show args**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_runtime.py src/so101_gazebo_demo_py/test/test_pick_place_launch.py
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_gazebo_demo_py --symlink-install
source install/setup.zsh
ros2 launch so101_gazebo_demo_py so101_pick_place.launch.py --show-args
ros2 launch so101_gazebo_demo_py so101_pick_place.launch.py run_mode:=dry_run start_simulation:=false
```

Expected: dry-run reaches `DONE` without requiring a ROS/Gazebo stack.

- [ ] **Step 5: Commit**

```bash
git add -- src/so101_gazebo_demo_py/so101_gazebo_demo_py/runtime.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/cli/pick_place_state_machine.py src/so101_gazebo_demo_py/launch/so101_pick_place.launch.py src/so101_gazebo_demo_py/setup.py src/so101_gazebo_demo_py/test/test_runtime.py src/so101_gazebo_demo_py/test/test_pick_place_launch.py
git diff --cached --check
git commit -m "feat(so101_py): compose executable pick-place runtime"
```

---

### Task 13: Add C++-to-Python Characterization and Resume Compatibility Tests

**Files:**
- Create: `src/so101_gazebo_demo_py/test/characterization/run_behavior_matrix.py`
- Create: `src/so101_gazebo_demo_py/test/characterization/test_behavior_parity.py`
- Create: `src/so101_gazebo_demo_py/test/characterization/test_checkpoint_parity.py`
- Create: `src/so101_gazebo_demo_py/test/fixtures/behavior_matrix.yaml`

**Interfaces:**
- Consumes: test-only access to both installed executables.
- Produces: normalized behavior records `{case, exit_code, status, current_state, next_state, failure_code, failure_metrics, state_trace, checkpoint}`.

- [ ] **Step 1: Define the exact behavior matrix and write RED comparison tests**

Cases include full dry-run; each `--fail-at` action state; every `--stop-after`; each supported `--plan-only-state`; single-step followed by resume; invalid resume session; changed policy fingerprint; validation pause; allowed and rejected force-continue; retry sidecar pending phase; and max-transition exhaustion.

Normalize nondeterministic run IDs, timestamps, paths, and floating formatting only. Do not normalize state names, codes, metrics, ordering, checkpoint fields, or exit codes.

- [ ] **Step 2: Run the Python side and confirm comparison RED**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/characterization
```

Expected: failure until the harness records the R3 reference and exposes any actual parity differences.

- [ ] **Step 3: Run the R3 executable in test-only mode and close differences**

Build/source both packages for the test only. The harness invokes the old executable only from tests and stores normalized results under pytest temporary directories. Fix Python behavior when the R3 result is within the approved contract. If R3 behavior conflicts with the approved design or safety gate, preserve the design and document the deliberate difference in the fixture with `reason` and exact evidence.

- [ ] **Step 4: Run GREEN**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/characterization
```

- [ ] **Step 5: Commit**

```bash
git add -- src/so101_gazebo_demo_py/test/characterization src/so101_gazebo_demo_py/test/fixtures/behavior_matrix.yaml
git diff --cached --check
git commit -m "test(so101_py): characterize R3 behavior parity"
```

---

### Task 14: Run Package-Level Verification and Independence Audit

**Files:**
- Create: `src/so101_gazebo_demo_py/test/test_installed_independence.py`
- Create: `src/so101_gazebo_demo_py/README.md`
- Modify: `src/so101_gazebo_demo_py/setup.py`

**Interfaces:**
- Produces: package-level acceptance report and operator documentation.

- [ ] **Step 1: Write the installed independence test**

In a fresh ROS-only shell, inspect package XML, Python imports, launch sources, installed text assets, executable scripts, `ldd` of any native Python extension imported by the package, and running process command lines. Reject old package share paths, executable calls, and libraries. Assert every approved launch and console script is installed.

- [ ] **Step 2: Run the test RED before final metadata/docs installation**

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_gazebo_demo_py --symlink-install
source install/setup.zsh
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_installed_independence.py
```

- [ ] **Step 3: Complete setup metadata and README**

Document build, source, dry-run, plan-only, execute, reset, evidence, safe defaults, simulation-only boundary, known Gazebo ABI risk, and the exact excluded features. Make `setup.py` install `README.md`, `docs/provenance.json`, and the approved package-local operator documentation, and include every approved console script.

- [ ] **Step 4: Run all package tests from a ROS-only shell**

```bash
cd /data/work/ws_moveit/.worktrees/refactor-optimization-r3
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_gazebo_demo_py --symlink-install
source install/setup.zsh
PYTHONNOUSERSITE=1 colcon test --packages-select so101_gazebo_demo_py --event-handlers console_direct+
colcon test-result --verbose
```

Expected: zero failed tests and no errors. Record counts and logs in the evidence directory.

- [ ] **Step 5: Commit**

```bash
git add -- src/so101_gazebo_demo_py/test/test_installed_independence.py src/so101_gazebo_demo_py/README.md src/so101_gazebo_demo_py/setup.py
git diff --cached --check
git commit -m "docs(so101_py): document verified standalone demo"
```

---

### Task 15: Headless End-to-End Pick-Place Acceptance

**Files:**
- Create: `src/so101_gazebo_demo_py/test/headless/run_pick_place_e2e.sh`
- Create: `src/so101_gazebo_demo_py/test/headless/assert_pick_place_evidence.py`
- Create: `src/so101_gazebo_demo_py/test/headless/test_pick_place_e2e_contract.py`

**Interfaces:**
- Produces: one reproducible single-stack E2E command and machine-readable evidence summary.

- [ ] **Step 1: Write the E2E evidence contract RED test**

Require a JSON summary with source/install provenance, launch command, exit code, state trace, controller results, joint/TCP before/after samples, Gazebo attach/detach events, object poses, Planning Scene membership transitions, cleanup results, and evidence file paths. The assertion script fails if any layer is missing or inconsistent.

- [ ] **Step 2: Run contract RED against an empty evidence directory**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/headless/test_pick_place_e2e_contract.py
```

- [ ] **Step 3: Implement isolated runner and execute incrementally**

The shell script creates unique `ROS_DOMAIN_ID`, `GZ_PARTITION`, `simulation_session_id`, checkpoint, and `ROS_LOG_DIR`; records owned PIDs; launches one headless stack; waits for controllers, move_group, attachment relay, and world readiness; then executes with `stop_after` boundaries in this order:

```text
MOVE_ABOVE_OBJECT
DESCEND
VERIFY_PHYSICAL_GRASP
ATTACH_MOVEIT
LIFT
DESCEND_TO_PLACE
SYNC_WORLD_OBJECT
DONE
```

Reset between incompatible partial runs. Do not advance past the first failing boundary. When all boundaries pass, run one uninterrupted fresh execute to `DONE`.

- [ ] **Step 4: Prove every runtime layer and cleanup**

Run:

```bash
bash src/so101_gazebo_demo_py/test/headless/run_pick_place_e2e.sh
evidence_root=$(ls -dt /tmp/so101-py-* | head -1)
python3 src/so101_gazebo_demo_py/test/headless/assert_pick_place_evidence.py "$evidence_root/summary.json"
```

Expected: state machine exit 0; joints and TCP move as expected; physical grasp precedes attach; object follows TCP after attach; Gazebo and Planning Scene detach separately; final object is stable at the place pose; only owned PIDs are stopped; pre-existing sessions/processes remain.

- [ ] **Step 5: Run GREEN and commit**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/headless/test_pick_place_e2e_contract.py
git add -- src/so101_gazebo_demo_py/test/headless/run_pick_place_e2e.sh src/so101_gazebo_demo_py/test/headless/assert_pick_place_evidence.py src/so101_gazebo_demo_py/test/headless/test_pick_place_e2e_contract.py
git diff --cached --check
git commit -m "test(so101_py): verify headless pick-place runtime"
```

---

### Task 16: GUI Acceptance, Final Audit, and Handoff Report

**Files:**
- Create: `docs/superpowers/reports/2026-08-07-so101-gazebo-demo-py-acceptance.md`
- Modify only if evidence requires a real fix: files under `src/so101_gazebo_demo_py/`

**Interfaces:**
- Produces: final evidence-backed acceptance report; no default-branch push.

- [ ] **Step 1: Rebuild and start one GUI stack in an owned tmux session**

Use a dedicated runtime session such as `so101-py-gui`, not `codex-cua`. In that shell:

```bash
source ~/gui-env.zsh
source /opt/ros/jazzy/setup.zsh
cd /data/work/ws_moveit/.worktrees/refactor-optimization-r3
colcon build --packages-select so101_gazebo_demo_py --symlink-install
source install/setup.zsh
gui_session_id=so101-py-gui-$(date +%Y%m%d-%H%M%S)
ros2 launch so101_gazebo_demo_py so101_pick_place.launch.py run_mode:=execute start_simulation:=true headless:=false simulation_session_id:="$gui_session_id" checkpoint_path:=/tmp/so101-py-gui-checkpoint.json
```

- [ ] **Step 2: Capture and inspect fresh visual evidence**

Run the repository capture helper from the ai-station host after the action. Inspect the new desktop/Gazebo/RViz images. Record visible robot pose, gripper contact, cup lift, final cup pose, release, absence of obvious penetration/drop, and Planning Scene consistency. File existence alone is not acceptance.

- [ ] **Step 3: Run the final requirement-by-requirement audit**

The report must list each design completion criterion with authoritative evidence and mark it `PROVED`, `CONTRADICTED`, or `MISSING`. Include:

- commit list and dirty-state preservation;
- source/install/runtime provenance;
- package test counts;
- characterization results;
- headless and GUI commands with exit codes;
- Gazebo, MoveIt, controller/joint/TF, and visual evidence paths;
- independence scan results;
- remaining risks and exact next command for any unproved item.

Do not call the rewrite complete while any required item is `CONTRADICTED` or `MISSING`.

- [ ] **Step 4: Clean up only owned runtime resources**

Stop the dedicated runtime tmux session and its recorded PIDs. Re-list ROS/Gazebo/MoveIt processes and tmux sessions. Preserve unrelated stacks and the `codex`/`codex-cua` sessions.

- [ ] **Step 5: Commit the acceptance report if and only if all criteria are proved**

```bash
git add -- docs/superpowers/reports/2026-08-07-so101-gazebo-demo-py-acceptance.md
git diff --cached --check
git diff --cached --name-status
git commit -m "docs(so101_py): record runtime acceptance"
```

If acceptance is incomplete, leave the report uncommitted or commit it explicitly as a partial evidence report with no completion claim. Do not push or merge without separate user authorization.

## Physical-outcome parity migration tasks (approved 2026-08-08)

这些任务覆盖 Task 15 的 forward Gazebo-attachment acceptance 路径。保留所有现有 Task 15 脏文件，
先建立 parity，不把来源不明改动夹入提交。只读参考 physical worktree `641f7c4`；installed Python
package 绝不 import/link/execute C++ package。

### P1: Domain、workflow 与 package independence

- 在 `test/test_domain.py`、`test/test_workflow.py`、`test/test_package_independence.py` 写 RED：两个新
  state 精确序列化；forward trace 无 Gazebo attach/detach；MoveIt detach 早于 open；扫描拒绝 C++
  import、binary、asset lookup。
- 最小 GREEN 修改 `domain.py`/`workflow.py`；防御性 Gazebo detach 只留 reset/recovery protocol。
- 运行 `python3 -m pytest -q` 的上述文件；预期 RED 为 state/trace 缺失，GREEN 为零失败。单独提交。

### P2: Strict physical-outcome policy

- `test/test_policy_config.py` RED 覆盖每个 final/shadow 字段、missing/unknown/non-finite、range/timing
  consistency 和 calibration sentinel。
- GREEN 修改 `policy_config.py` 与 validation YAML。仅复用 `641f7c4` 中语义相同的证据值；不得改
  现有 hard ceiling。纯 pytest 循环不运行 C++ quality gate。

### P3: Snapshot、observer 与 evidence

- observer/snapshot/checkpoint RED 覆盖独立 source timestamp/sequence、fresh finite evidence、bounded
  telemetry、真实 intended-table contact、compound-owner identity、bounded-negative-depth 与 release epoch。
- GREEN 保留 raw collision/depth metrics，support depth 不得进入 finger penetration；CLI/snapshot 暴露
  epoch、sample、support/detach/sync facts，但不复制 evaluator 逻辑。

### P4: Pure evaluator 与 release settle

- RED 精确覆盖 post-release-only、consecutive/minimum duration、derived linear/angular speed、非单调/
  non-finite 时间、全部 final predicates、bounded metrics 和固定 failure precedence。
- 纯 evaluator 无 ROS、无 sleep；settle executor 拥有 cadence/cancel/timeout，新 epoch non-resumable。
  注册 `WAIT_RELEASE_SETTLE`/`VALIDATE_FINAL_PLACEMENT`，冻结 final evidence 交给 sync。

### P5: MoveIt-only planning shadow

- RED 证明 ATTACH_MOVEIT 使用最新 Gazebo pose、每个 carrying plan 前 shadow divergence gate、detach
  先于 open，forward adapter 不发布 Gazebo attach/detach。
- GREEN 移除 forward `backend.set_attached(True/False)` 与 attach events，不能变成 no-op；reset readiness
  仍可 detach stale state。保留所有 collision/penetration/shadow ceilings 与 carry telemetry。

### P6: Hold-first recovery 与 consumers

- RED 证明 unsupported held cup 不 open、final failure 在 reset 前冻结、headless wrapper 传播 installed
  execute 非零状态。
- GREEN 更新 recovery/CLI/launch/headless assertion；checkpoint 禁止恢复 interrupted release epoch。

### P7: Python parity gate

先 targeted pytest，再 package source 全 pytest。仅 source 全绿后做
`colcon build --packages-select so101_gazebo_demo_py --symlink-install`、source overlay、验证 package prefix
和 package tests；随后 dry-run、所有 plan-only state 和一个唯一 domain/partition/session/hash/evidence
root 的 isolated headless。physical-outcome parity 未成立前不调 target。

### P8: 固定单变量 target 顺序

顺序为 grasp TCP position（逐轴）、orientation（逐分量）、q6 close、micro-lift、carry/place waypoint、
trajectory timing。每个候选先 Python config/range RED→最小 GREEN→targeted pytest→installed policy→
full plan_only→`stop_after`/最早边界 headless；记录 solver depth、cup/TCP pose、tilt/orientation drift、
q6 feedback/velocity、shadow divergence。valid failure 淘汰，invalid 终止批次，禁止随机筛成功。
controller、physics、geometry、mass、friction、final tolerance 和 hard ceilings 全部冻结。

### P9: Qualification、acceptance 与 publication

冻结候选后做 fresh Python package 全测、完整 headless outcome、GUI/CUA fresh screenshot、同 commit/
policy 五次连续 FULL_RESTART。保留 controller/joint/TF、Gazebo pose/contact/detached、MoveIt shadow/
detached/world-sync 与视觉独立证据。valid failure 清零，invalid 终止。五连前不 push/merge；之后才按
授权做 scoped Gitee publication 和 remote SHA verification。

任何 unexpected failure 先用 systematic-debugging，不叠加第二变量。

### P10: Target-only calibration matrix（批准于 2026-08-08）

- 以 preserved Task 15/current Python target 为未 qualification baseline；记录 source commit、dirty
  config hash、单位、杯/指垫几何与 symbolic bounded range。不得把 preserved `0.012 rad` controller
  tolerance 实验值用于有效运行；runtime 必须证明加载冻结 `0.008 rad` physical-outcome config。
- 固定顺序 A TCP translation（每次一轴）→B orientation（每次一分量）→C q6→D micro-lift→E
  carry/place/retreat waypoint→F timing/scaling。具体候选必须先在新 ledger `PLANNED`，不得并改。
- 每候选：精确 config/range contract RED→GREEN；fresh Python build/source/prefix；所有 motion state
  `--mode plan_only --live-runtime`；唯一 FULL_RESTART `--stop-after VERIFY_PHYSICAL_GRASP`；保存
  cup↔finger depth、cup/TCP 7D pose、tilt/orientation drift、q6/velocity 和 shadow divergence。
- VALID failure 淘汰，不重跑挑随机成功；INVALID 终止批次。连续三个同方向有界候选失败即停止该
  方向。短路径候选需冻结后三次 FULL_RESTART qualification，任一 valid failure 回退。
- 只有 qualification 后执行 full physical outcome；然后 fresh full package suite、headless、GUI fresh
  screenshot、同 commit/policy 五次连续 FULL_RESTART。controller/physics/geometry/material/final tolerance/
  all hard ceilings 始终冻结。

### P11: Z → q6 → orientation 恢复计划（批准于 2026-08-08，取代仅限两项旧边界）

本任务在 A 层 X/Y/Z 有界候选全部 VALID failure（止于 `PY-A-Z-POS-0004-GRASP-001`）之后恢复
target 校准。仅取代：（1）同方向三候选失败后的 no-interpolation 停止规则；（2）严格 A→B→C
顺序。所有 frozen 约束（见 design 同名 addendum）与 process/session ownership 规则不变。

- **唯一写者**：tmux `codex-cua` 已暂停且不得恢复；Python ledger/worktree 唯一写者为 tmux
  `kimi`。Phase 0 checkpoint recovery 只读（git/ledger/既有测试证据/status/PID ownership），不
  rerun 测试、不 build、不 launch、不改 target；授权文档作为独立 scoped commit 先行提交，六个
  preserved dirty path 不进入该 commit。
- **Phase 1（Z 二分，≤3 VALID 物理候选）**：bracket `[+0.000400000, +0.000500000] m`，只改
  `grasp_tcp_translation_offset_m[2]`。候选 1 `+0.000450000 m`；按规则替换下界（bilateral 保持但
  penetration 越顶）或上界（moving contact 缺失/不稳定），候选 2/3 取更新后 bracket 精确中点。
  全 gate 通过即停；三败则关闭 bracket 进入 Phase 2，不细分、不组合轴。
- **Phase 2（q6 seating-preload 因果二分，≤3 VALID 候选）**：显式批准的顺序修正，q6 先于
  orientation。确定性冻结 bilateral contact 且 worst normalized penetration 最小的 Z 候选为诊断
  锚点；其余全冻结。仅在缺失时以 TDD 增加最小 `seating_preload_rad` plumbing。幅度
  `[0.0, 0.006] rad`，`safe_lower_q6 <= q6_target <= baseline grasp_close_q6`，仍由实测
  `q6_contact` 推导。候选 1 `0.003 rad`；penetration 过高则在 `[0, current]` 减小二分，
  contact/stability 丢失则在 `[current, 0.006]` 增大二分；首个全 gate 通过即停。
- **Phase 3（单一证据选定 orientation 方向，≤3 VALID 候选）**：先只读 geometry/contact-normal/
  TF/FK 分析并写竞争假设，选定唯一轴与符号；无可辩护轴/符号则跳过物理实验直接 Phase 4。
  冻结最佳诊断 Z 锚点并恢复文档化 q6 baseline（除非 Phase 2 已通过）。只改一个 scalar，幅度
  1°/2.5°/5°（`0.017453292519943295`/`0.04363323129985824`/`0.08726646259971647 rad`），不超过
  `axis_tolerance_rad`；恶化或通过即提前停止，不自动换轴/反号。
- **Phase 4（只读可行性审计）**：停止 target 实验，审计 cup/pad 几何、contact normal/depth
  分布、实测 q6、TCP/cup pose 与 `0.000800002 m` ceiling，提交审计 checkpoint 并恰好给出
  `FEASIBLE_WITH_NEXT_EXACT_TARGET_HYPOTHESIS` 或 `TARGET_ONLY_INFEASIBLE_UNDER_CURRENT_MODEL`；
  不可行则停止并请求用户决策，绝不放宽 gate 或改 geometry。
- **每候选执行 contract**：精确 config/contract RED（先观察到预期失败）→最小 scalar GREEN→
  focused test + 全量 Python package suite（不回退于 136 passed, 2 skipped）→rebuild、source 正确
  overlay、验证 installed provenance/prefix/hash→六状态 plan-only（plan 失败即无物理执行淘汰）→
  唯一 owned FULL_RESTART stack，仅执行到 `VERIFY_PHYSICAL_GRASP`→记录六个 post-command sample、
  双侧 contact、各 pad max penetration、q6_contact/final、pose-pair age、controller result、Gazebo/
  MoveIt attachment 状态、exit code、精确证据路径。仅在 bilateral 稳定接触、两侧 depth
  `<= 0.000800002 m` 且其余 frozen gate 全过时判通过。
- **Qualification 与发布**：首个通过后冻结 commit/config/policy fingerprint，≥3 次独立
  FULL_RESTART grasp qualification（VALID failure 结束并仅回到仍授权 phase；INVALID 终止批次）→
  预注册 detached 物理 micro-lift（精确 `+0.002 m` world-Z，无 forward attach）→在下一个首个失败
  边界重接 D→E→F→完整物理 pick/place（最终 pose 稳定/直立/在批准范围内，MoveIt membership 独立
  验证）→fresh clean-cache build/全量 suite、dry-run、完整 plan-only、headless、GUI/CUA 新截图→
  同冻结 commit/policy 连续五次 FULL_RESTART 成功（INVALID 不计且终止批次，VALID failure 清零）。
  全部成立后才 scoped commit、推 Gitee、验证 remote SHA、按批准 merge gate 合干净 main、重跑
  合并树测试、推 main。禁止 force-push、`gh`、dirty main 合并。
- 每批次保留：source commit 与精确 dirty status、installed overlay/executable/prefix/hash、
  experiment ID/lifecycle/ROS_DOMAIN_ID/GZ_PARTITION/tmux/PID、命令与 exit code、plan trajectory、
  controller/joint/TF、Gazebo contact/pose/attachment、MoveIt membership、必要的本轮新视觉证据、
  preserved 进程与精确 cleanup readback。结论先写
  `docs/experiments/so101-gazebo-demo-py-experiment-ledger.md` 再做聊天汇报或继续。

## 2026-08-08 增补执行计划：penetration gate 诊断性放宽的 micro-lift 观察

对应设计增补「2026-08-08 增补授权：penetration gate 诊断性放宽（非重校准）」。

1. 授权增补先写入本计划、设计与 experiment ledger，并作为独立 docs-only commit 提交
   （六个 preserved dirty path 不入该 commit）。
2. TDD 增加可选 plumbing：motion policy `diagnostic_moving_pad_penetration_ceiling_m`
   （默认 `0.0` 禁用，启用界 `(0.000800002, 0.0012]`），loader 校验 + gate 函数 ceiling 参数
   （默认 frozen 常量，既有测试不回退）。
3. scoped commit plumbing；随后单 scalar 把该字段置 `0.0012`（RED→GREEN→全量 suite→scoped
   commit→rebuild→验证 installed provenance/hash）。
4. ledger 预注册 PLANNED；跑六状态 plan-only（唯一 FULL_RESTART stack，新 ROS_DOMAIN_ID /
   GZ_PARTITION / tmux / 证据目录）；plan-only 通过且 provenance/preflight 完成后记 RUNNING。
5. 第二次 FULL_RESTART 执行到 `VERIFY_PHYSICAL_GRASP`（含 `+0.002 m` micro-lift 探针，无
   forward attach）；恰好一次物理尝试；INVALID 即停止诊断。
6. 读出并记录：cup_world_z_delta_m、lateral、post-lift 双侧 contact 与各 pad max depth、
   q6_contact/final、pose-pair age、controller result、Gazebo/MoveIt attachment、exit code、证据路径。
7. 无论结果，scalar 复原 `0.0`（RED/GREEN + 全量 suite + scoped commit），ledger 写终态结论，
   向用户汇报并等待 ceiling 重校准决策；不自行进入 qualification。

## 2026-08-09 增补执行计划：ceiling 重校准 + QUALIFICATION

对应设计增补「2026-08-09 增补授权：moving-pad penetration ceiling 重校准」。

1. 授权增补写入本计划/设计/ledger，docs-only 提交（preserved dirty path 不入）。
2. RED/GREEN 把 `MOVING_PAD_MESH_PENETRATION_CEILING_M` 改为 `0.00125`，override 界改
   `(0.00125, 0.0013]`；更新相关断言（含本地未跟踪 parity 测试的界面适配，不 stage）；
   全量 suite 无回退；scoped commit；rebuild + 验证 installed provenance。
3. ledger 预注册三次 qualification（独立 FULL_RESTART，新 domain/partition/tmux/证据目录，
   冻结同一 commit/config fingerprint，锚点配置，execute 到 `VERIFY_PHYSICAL_GRASP`，其内部
   含 +0.002 m micro-lift 探针）。
4. 每次运行先 plan-only 合同（随 runner preflight），provenance/preflight 通过后记 RUNNING；
   任一 VALID failure 结束 qualification 回到用户；INVALID 终止批次并先调试污染/实现缺陷。
5. 三次通过后按计划继续：完整物理 pick/place（D→E→F 边界、shadow gate、release/settle、
   最终 outcome 稳定/直立/落区、MoveIt membership 独立验证），随后验收电池（clean build/
   全量 suite、dry-run、完整 plan-only、headless、GUI/CUA 新截图）与同一冻结 commit/policy
   连续五次 FULL_RESTART 成功，最后才 scoped commit、推 Gitee、合 main。

## 2026-08-09 增补执行计划：solver-limit gate + 重启 QUALIFICATION

对应设计增补「2026-08-09 增补授权：solver-limit gate 语义（用户选项 1）」。

1. 授权增补写入本计划/设计/ledger，docs-only 提交（preserved dirty path 不入）。
2. RED/GREEN：`MOVING_PAD_MESH_PENETRATION_CEILING_M` 改 `0.0013`；移除 diagnostic override
   apparatus（policy 字段/loader/gate kwargs/相关测试）；更新边界断言（含本地未跟踪 parity
   测试界面适配，不 stage）；全量 suite 无回退；scoped commit；rebuild + 验证 provenance。
3. ledger 预注册新 fingerprint 下的 plan-only + 三次 FULL_RESTART grasp qualification
   （新 domain/partition/tmux/证据目录）；EXP-QUAL-GRASP-2-232 / EXP-QUAL-GRASP-3-233 记 NOT_RUN。
4. 任一 VALID failure 结束 qualification 回到用户；INVALID 终止批次先调试。
5. 三次通过后继续：完整物理 pick/place（D→E→F、shadow、release/settle、最终 outcome、
   MoveIt membership 独立验证）→ 验收电池（clean build/全量 suite、dry-run、完整 plan-only、
   headless、GUI/CUA 新截图）→ 同冻结 fingerprint 连续五次 FULL_RESTART 成功 → scoped commit、
   推 Gitee、合 main。
