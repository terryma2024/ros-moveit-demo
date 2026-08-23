# SO-101 Unified Simulation Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `so101_demo_py` as the single implementation package for the proven MuJoCo pick-place control chain, a normally executing Gazebo adapter, separate simulator launchers, reusable geometry, thin legacy forwarders, and a zero-I/O real-arm extension stub.

**Architecture:** Use the qualified MuJoCo implementation as a strangler-migration baseline: first preserve it under the mapped `so101_demo_py/src -> so101_demo` layout, then replace one external dependency at a time with typed ports. Runtime composition is the only layer that selects backend or policy; application phases and shared ROS 2/MoveIt control contain no backend branches.

**Tech Stack:** ROS 2 Jazzy, Python 3, `ament_python`, MoveIt 2, `ros2_control`, the pinned `mujoco_ros2_control` fork, Gazebo Harmonic/`ros_gz`, pytest, Ruff, YAML/JSON manifests, colcon, tmux, and ai-station CUA.

## Global Constraints

- Re-run the dynamic baseline gate first. Use the clean main-workspace HEAD only if ancestry, patch equivalence, package/asset presence, and qualification-bundle inspection prove the migration is merged; otherwise use the migration worktree's latest clean committed HEAD.
- Never absorb uncommitted files from a candidate worktree. Record and preserve dirty paths, tmux sessions, ROS graphs, and processes; do not stash, reset, clean, overwrite, or stop them.
- Implement in a new worktree on `codex/so101-demo-py-fusion`; do not modify the design-only worktree except for this plan.
- The ROS package is `so101_demo_py`, the Python namespace is `so101_demo`, and source lives directly under `so101_demo_py/src` with `package_dir={"so101_demo": "src"}`.
- Do not create `so101_demo_py/so101_demo_py` or `so101_demo_py/src/so101_demo_py`.
- MuJoCo's committed workflow, phase order, evidence semantics, and v1 policy are the behavioral baseline. Mechanical migration must not tune parameters, reorder phases, or reinterpret success.
- The v1 `mujoco.yaml` and `gazebo.yaml` are byte-identical copies of the live qualified MuJoCo policy. Its design-time SHA-256 was `aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356`; re-read the live hash before copying.
- Gazebo `execute` runs normally. It reports its real first failure boundary or success, never `SKIPPED`; the policy outcome is not a RED-to-GREEN or release gate.
- Gazebo adapter/build/launch/evidence validity is a hard gate. At least one non-`INVALID` Gazebo execute result with evidence is required.
- MuJoCo must independently re-qualify the new fixed bundle as five consecutive `FULL_RESTART` valid successes and five consecutive `RESET_WORLD` valid successes. Do not mix lifecycles or reuse historical qualification labels.
- A `VALID` failure breaks a streak; an `INVALID` run invalidates its batch; only a `VALID` success enters a winning streak.
- Physics-step tracing is capability-gated instrumentation. MuJoCo qualification may require it; base Gazebo execution must continue when it is unavailable.
- `core` and `application` must not import simulator implementations. Backend selection occurs only in `so101_demo.runtime` and launch/CLI composition.
- Share visual meshes, task-object visuals, link/joint names, TCP name, and common dimensions. Keep collision, friction, contact, inertia, solver, MJCF, and SDF backend-specific.
- Runtime must not auto-convert or download URDF, MJCF, SDF, or mesh assets.
- `so101_mujoco_demo_py` and `so101_gazebo_demo_py` remain for one version as forwarding packages only; they own no control logic, policy, model, mesh, or duplicated fixture.
- The v1 real-arm backend is a fail-closed, zero-I/O stub. It has no device discovery, serial access, hardware plugin, ROS control client/publisher, action, reset mapping, or real launcher.
- Every run result records backend, session/reset identity, source commit, installed prefix, policy hash, bundle hash, first failed phase, stable error code, classification, and evidence references.
- Runtime acceptance uses the installed overlay. A source-tree import, `0 packages`, or `0 tests` is not a pass.
- Do not run `ament_uncrustify --reformat`. Use scoped Ruff/pytest checks and `git diff --check`.
- Stop only exact task-owned process groups. Never use broad `pkill`; do not disturb existing Gazebo, MoveIt, RViz, MuJoCo, Teleop, or CUA sessions.
- Do not push, merge, force-push, or delete the compatibility packages in this plan.

---

## File Structure

```text
src/so101_demo_py/
├── src/                         # Python namespace so101_demo
│   ├── core/                    # ROS-free state, policy, result, recovery
│   ├── application/phases/      # qualified nine-phase orchestration
│   ├── control/                 # shared MoveIt/controller/scene services
│   ├── ports/                   # typed robot/world/lifecycle/evidence boundaries
│   ├── backends/mujoco/         # MuJoCo adapters
│   ├── backends/gazebo/         # Gazebo adapters
│   ├── backends/real_stub/      # safe structured rejection only
│   ├── runtime/                 # composition and provenance
│   └── cli/                     # thin entry points
├── launch/                      # four explicit simulator launchers
├── config/policies/             # complete versioned variants
├── assets/common/               # shared visual/task geometry
├── assets/mujoco/               # MuJoCo collision and scene
├── assets/gazebo/               # Gazebo collision and world
├── test/
├── package.xml
├── setup.py
└── setup.cfg
```

The legacy packages retain only package metadata, forwarding entry points, forwarding launch files, and forwarding-contract tests.

---

### Task 1: Select the live clean baseline and create the implementation worktree

**Files:**
- Create: `docs/experiments/so101-demo-py-fusion-experiment-ledger.md`
- Create: `docs/provenance/so101-demo-py-fusion-baseline.json`
- Read only: `docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md`
- Read only: the latest MuJoCo qualification bundle and referenced evidence

**Interfaces:**
- Consumes: both candidate HEADs, ancestry, patch equivalence, target package/assets, bundle, dirty paths, and process inventory.
- Produces: an immutable baseline record with `selected_commit`, `selection_reason`, `policy_sha256`, `qualification_bundle_sha256`, `dirty_inputs_included=false`, plus a new worktree on `codex/so101-demo-py-fusion`.

- [ ] **Step 1: Capture both candidates read-only**

```bash
git -C /data/work/ws_moveit status --short --branch
git -C /data/work/ws_moveit rev-parse HEAD
git -C /data/work/ws_moveit/.worktrees/so101-mujoco-ros2 status --short --branch
git -C /data/work/ws_moveit/.worktrees/so101-mujoco-ros2 rev-parse HEAD
git -C /data/work/ws_moveit merge-base main codex/so101-mujoco-ros2-teleop
git -C /data/work/ws_moveit cherry main codex/so101-mujoco-ros2-teleop
```

Expected: no tree changes; every dirty path is recorded and excluded.

- [ ] **Step 2: Apply the merge/content hard gate**

```bash
git -C /data/work/ws_moveit merge-base --is-ancestor codex/so101-mujoco-ros2-teleop main
test -f /data/work/ws_moveit/src/so101_mujoco_demo_py/package.xml
test -f /data/work/ws_moveit/src/so101_gazebo_demo_py/package.xml
rg -n 'EXP-158|EXP-167|FULL_RESTART|RESET_WORLD' /data/work/ws_moveit/docs /data/work/ws_moveit/src
fusion_main_head="$(git -C /data/work/ws_moveit rev-parse main)"
fusion_migration_head="$(git -C /data/work/ws_moveit/.worktrees/so101-mujoco-ros2 rev-parse HEAD)"
fusion_unique_patch_count="$(git -C /data/work/ws_moveit cherry main codex/so101-mujoco-ros2-teleop | rg -c '^\+' || true)"
fusion_history_merged=false
if git -C /data/work/ws_moveit merge-base --is-ancestor "$fusion_migration_head" "$fusion_main_head"; then
  fusion_history_merged=true
elif test "$fusion_unique_patch_count" -eq 0; then
  fusion_history_merged=true
fi
if test "$fusion_history_merged" = true \
  && test -f /data/work/ws_moveit/src/so101_mujoco_demo_py/package.xml \
  && rg -l 'EXP-158' /data/work/ws_moveit/docs >/dev/null \
  && rg -l 'EXP-167' /data/work/ws_moveit/docs >/dev/null; then
  fusion_selected_commit="$fusion_main_head"
else
  fusion_selected_commit="$fusion_migration_head"
fi
printf '%s\n' "$fusion_selected_commit"
printf '%s\n' "$fusion_selected_commit" > /tmp/so101-demo-py-fusion-selected-commit.txt
```

Expected: select main only when all history, content, and bundle checks succeed; otherwise freeze the latest clean migration commit.

- [ ] **Step 3: Create the isolated implementation worktree**

```bash
fusion_selected_commit="$(sed -n '1p' /tmp/so101-demo-py-fusion-selected-commit.txt)"
git -C /data/work/ws_moveit worktree add \
  /data/work/ws_moveit/.worktrees/so101-demo-py-fusion \
  -b codex/so101-demo-py-fusion "$fusion_selected_commit"
git -C /data/work/ws_moveit/.worktrees/so101-demo-py-fusion status --short --branch
```

Expected: the new worktree is clean and both candidate trees are unchanged.

- [ ] **Step 4: Write and validate the provenance record and ledger checkpoint**

Use `apply_patch` to add JSON with `schema_version: 1`, the exact commit/hash values printed by Steps 1-2, the branch selected by the hard gate, all observed candidate dirty paths, and `dirty_inputs_included: false`. Reject the file unless `selected_commit` matches `^[0-9a-f]{40}$` and both hashes match `^[0-9a-f]{64}$`.

Run: `python3 -m json.tool docs/provenance/so101-demo-py-fusion-baseline.json >/dev/null && git diff --check`

Expected: ledger cites the last trusted checkpoint without rewriting old experiments and records preserved sessions/PIDs/dirty paths.

- [ ] **Step 5: Commit the baseline checkpoint**

```bash
git add docs/experiments/so101-demo-py-fusion-experiment-ledger.md \
  docs/provenance/so101-demo-py-fusion-baseline.json
git commit -m "docs(so101): freeze demo fusion baseline"
```

### Task 2: Create the mapped package and installed identity contract

**Files:**
- Create: `src/so101_demo_py/src/__init__.py`
- Create: `src/so101_demo_py/resource/so101_demo_py`
- Create: `src/so101_demo_py/package.xml`
- Create: `src/so101_demo_py/setup.py`
- Create: `src/so101_demo_py/setup.cfg`
- Create: `src/so101_demo_py/ruff.toml`
- Create: `src/so101_demo_py/test/test_package_identity.py`
- Create: `src/so101_demo_py/test/test_src_layout.py`

**Interfaces:**
- Consumes: dependency union from the selected MuJoCo and Gazebo package manifests.
- Produces: importable `so101_demo`, ament package `so101_demo_py`, and a mapped setuptools layout.

- [ ] **Step 1: Write RED layout tests**

```python
def test_mapped_layout(package_root, setup_text):
    assert (package_root / "src" / "__init__.py").is_file()
    assert not (package_root / "so101_demo_py").exists()
    assert not (package_root / "src" / "so101_demo_py").exists()
    assert 'package_name = "so101_demo_py"' in setup_text
    assert 'python_package = "so101_demo"' in setup_text
    assert 'package_dir={python_package: "src"}' in setup_text
```

- [ ] **Step 2: Confirm the tests fail before scaffolding**

Run: `python3 -m pytest -q src/so101_demo_py/test/test_package_identity.py src/so101_demo_py/test/test_src_layout.py`

Expected: FAIL because `src/so101_demo_py` is absent.

- [ ] **Step 3: Implement the minimal package metadata**

```python
package_name = "so101_demo_py"
python_package = "so101_demo"
setup(
    name=package_name,
    packages=find_packages(where="src", include=(python_package, f"{python_package}.*")),
    package_dir={python_package: "src"},
)
```

`package.xml` contains the exact dependency union for ROS launch, MoveIt, controller/action messages, TF, `ros_gz`, xacro, MuJoCo messages/support, and robot state publishing.

- [ ] **Step 4: Prove source and installed identity**

```bash
python3 -m pytest -q src/so101_demo_py/test/test_package_identity.py src/so101_demo_py/test/test_src_layout.py
colcon build --base-paths src --packages-select so101_demo_py \
  --build-base build/fusion-t2 --install-base install/fusion-t2 --log-base log/fusion-t2
. install/fusion-t2/setup.sh
python3 -c 'import so101_demo; from ament_index_python.packages import get_package_prefix; print(so101_demo.__file__); print(get_package_prefix("so101_demo_py"))'
```

Expected: both paths resolve under `install/fusion-t2` and test discovery is nonzero.

- [ ] **Step 5: Commit the package skeleton**

```bash
git add src/so101_demo_py
git commit -m "build(so101): add unified mapped package"
```

### Task 3: Mechanically migrate the ROS-free core

**Files:**
- Create: `src/so101_demo_py/src/core/domain.py`
- Create: `src/so101_demo_py/src/core/workflow.py`
- Create: `src/so101_demo_py/src/core/runner.py`
- Create: `src/so101_demo_py/src/core/policy.py`
- Create: `src/so101_demo_py/src/core/outcome.py`
- Create: `src/so101_demo_py/src/core/recovery.py`
- Create: `src/so101_demo_py/test/characterization/test_core_parity.py`
- Create: `src/so101_demo_py/test/test_core_import_boundaries.py`

**Interfaces:**
- Consumes: selected committed MuJoCo domain/workflow/runner/policy/outcome/recovery code.
- Produces: unchanged `State`, `RunMode`, `RunStatus`, `ActionStatus`, `Failure`, `RunRequest`, `RunResult`, `SO101_WORKFLOW`, `resolve_transition`, `StateMachineRunner`, `TaskPolicy`, and `load_task_policy` under `so101_demo.core`.

- [ ] **Step 1: Write RED characterization and forbidden-import tests**

```python
def test_workflow_matches_frozen_mujoco(old, new):
    assert tuple(new.forward_states) == tuple(old.forward_states)
    assert dict(new.transitions) == dict(old.transitions)

def test_core_is_ros_free(core_sources):
    forbidden = ("rclpy", "moveit", "mujoco", "gazebo", "ros_gz", "launch")
    assert not any(name in source.read_text() for source in core_sources for name in forbidden)
```

- [ ] **Step 2: Run before the new core exists**

Run: `python3 -m pytest -q src/so101_demo_py/test/characterization/test_core_parity.py src/so101_demo_py/test/test_core_import_boundaries.py`

Expected: FAIL with missing `so101_demo.core` modules.

- [ ] **Step 3: Copy behavior and change only imports**

```python
from .domain import ActionResult, ActionStatus, Failure, RunRequest, RunResult, RunStatus, State
from .policy import TaskPolicy, load_task_policy
from .runner import StateMachineRunner
from .workflow import SO101_WORKFLOW, resolve_transition
```

Preserve enum values, dataclass fields/defaults, transitions, checkpoint serialization, validation, outcome math, and recovery decisions exactly.

- [ ] **Step 4: Run old/new parity**

```bash
python3 -m pytest -q src/so101_demo_py/test/characterization/test_core_parity.py \
  src/so101_demo_py/test/test_core_import_boundaries.py \
  src/so101_mujoco_demo_py/test/test_workflow_domain.py \
  src/so101_mujoco_demo_py/test/test_workflow_runner.py \
  src/so101_mujoco_demo_py/test/test_task_policy.py
```

Expected: PASS with identical frozen behavior.

- [ ] **Step 5: Commit the core**

```bash
git add src/so101_demo_py/src/core src/so101_demo_py/test
git commit -m "refactor(so101): migrate qualified workflow core"
```

### Task 4: Mechanically migrate shared control and MuJoCo application behavior

**Files:**
- Create: `src/so101_demo_py/src/control/moveit/*.py`
- Create: `src/so101_demo_py/src/control/trajectory/*.py`
- Create: `src/so101_demo_py/src/control/gripper/*.py`
- Create: `src/so101_demo_py/src/control/planning_scene/*.py`
- Create: `src/so101_demo_py/src/application/pick_place.py`
- Create: `src/so101_demo_py/src/application/qualification.py`
- Create: `src/so101_demo_py/src/application/phases/*.py`
- Create: `src/so101_demo_py/src/backends/mujoco/{client,observer,reset,viewer}.py`
- Create: `src/so101_demo_py/src/cli/{pick_place,qualification}.py`
- Create: `src/so101_demo_py/test/characterization/test_mujoco_parity.py`

**Interfaces:**
- Consumes: selected committed MuJoCo `motion`, `moveit`, ACM, live runtime, nine live phases, CLI, qualification, and backend clients.
- Produces: identical phase order/status strings, motion requests, timeouts, evidence, result schema, and temporary direct MuJoCo wiring under the new namespace.

- [ ] **Step 1: Write RED phase/control parity tests**

```python
def test_phase_sequence_is_frozen():
    assert LIVE_PHASES == (
        "staged_approach", "contact_hold", "micro_lift", "policy_lift_waypoint1",
        "remaining_lift", "transport", "descend", "place_alignment", "release_retreat",
    )

def test_plan_request_is_unchanged(old_request, new_request):
    assert asdict(new_request) == asdict(old_request)
```

- [ ] **Step 2: Run before migration**

Run: `python3 -m pytest -q src/so101_demo_py/test/characterization/test_mujoco_parity.py`

Expected: FAIL with missing new modules.

- [ ] **Step 3: Copy only committed files and rename only imports/resources**

```python
from so101_demo.core.domain import ActionResult, ActionStatus, Failure, FailureCategory
from so101_demo.control.trajectory.evidence import JointStateEvidence
```

Exclude all dirty/untracked migration-worktree files recorded in Task 1. Keep QoS, action/service names, tolerances, cancellations, phase order, Planning Scene shadow semantics, and physics behavior unchanged.

- [ ] **Step 4: Run characterization and the selected legacy suites**

```bash
python3 -m pytest -q src/so101_demo_py/test/characterization/test_mujoco_parity.py
python3 -m pytest -q src/so101_mujoco_demo_py/test \
  -k 'motion or moveit or runtime or phase or qualification or outcome or recovery'
```

Expected: PASS; no policy or result difference.

- [ ] **Step 5: Commit the mechanical migration**

```bash
git add src/so101_demo_py/src/control src/so101_demo_py/src/application \
  src/so101_demo_py/src/backends/mujoco src/so101_demo_py/src/cli src/so101_demo_py/test
git commit -m "refactor(so101): migrate qualified mujoco behavior"
```

### Task 5: Freeze strict policy variants and qualification provenance

**Files:**
- Create: `src/so101_demo_py/config/policies/light_cup_wall_pick/v1/{mujoco,gazebo,real_stub,manifest}.yaml`
- Create: `src/so101_demo_py/src/core/policy_registry.py`
- Create: `src/so101_demo_py/src/runtime/provenance.py`
- Create: `src/so101_demo_py/test/test_policy_registry.py`
- Create: `src/so101_demo_py/test/test_bundle_provenance.py`

**Interfaces:**
- Consumes: `load_task_policy(path: Path) -> TaskPolicy` and frozen policy bytes.
- Produces: `load_policy_variant(policy_id, version, backend, share_dir) -> LoadedPolicy`, `build_bundle_manifest(inputs) -> QualificationBundle`, and `python3 -m so101_demo.runtime.provenance --print-bundle-sha256`, with immutable policy/bundle hashes.

- [ ] **Step 1: Write RED strict-loader and byte-parity tests**

```python
def test_v1_simulator_variants_are_exact(paths, frozen_bytes):
    assert paths.mujoco.read_bytes() == frozen_bytes
    assert paths.gazebo.read_bytes() == frozen_bytes

@pytest.mark.parametrize("mutation", ["unknown_field", "missing_field", "nan", "boolean_number"])
def test_loader_rejects_noncanonical_variant(mutation, variant_factory):
    with pytest.raises(PolicyValidationError):
        load_policy_variant("light_cup_wall_pick", "v1", "mujoco", variant_factory(mutation))
```

- [ ] **Step 2: Run before registry and variants exist**

Run: `python3 -m pytest -q src/so101_demo_py/test/test_policy_registry.py src/so101_demo_py/test/test_bundle_provenance.py`

Expected: FAIL with missing policy files/registry.

- [ ] **Step 3: Implement complete variants and canonical bundle hashing**

```python
@dataclass(frozen=True, slots=True)
class LoadedPolicy:
    policy_id: str
    version: str
    backend: str
    path: Path
    policy: TaskPolicy
    policy_sha256: str
    qualification_status: str

@dataclass(frozen=True, slots=True)
class QualificationBundle:
    manifest: Mapping[str, object]
    bundle_sha256: str
```

The bundle covers source commit, installed prefix, policy, URDF/MJCF/SDF/collision assets, contact/solver/task-scene config, controllers/MoveIt config, evidence schema/plugin, lifecycle, and runner version. Hash sorted compact UTF-8 JSON.

- [ ] **Step 4: Verify strict policy and provenance contracts**

```bash
sha256sum src/so101_demo_py/config/policies/light_cup_wall_pick/v1/mujoco.yaml \
  src/so101_demo_py/config/policies/light_cup_wall_pick/v1/gazebo.yaml
python3 -m pytest -q src/so101_demo_py/test/test_policy_registry.py \
  src/so101_demo_py/test/test_bundle_provenance.py
```

Expected: simulator hashes equal the live baseline hash; Gazebo is `NOT_QUALIFIED`; real stub has no simulation contact threshold.

- [ ] **Step 5: Commit policy and provenance**

```bash
git add src/so101_demo_py/config/policies src/so101_demo_py/src/core/policy_registry.py \
  src/so101_demo_py/src/runtime/provenance.py src/so101_demo_py/test
git commit -m "feat(so101): freeze backend policy variants"
```

### Task 6: Extract neutral evidence, capabilities, WorldPort, and LifecyclePort

**Files:**
- Create: `src/so101_demo_py/src/ports/evidence.py`
- Create: `src/so101_demo_py/src/ports/capabilities.py`
- Create: `src/so101_demo_py/src/ports/world.py`
- Create: `src/so101_demo_py/src/ports/lifecycle.py`
- Modify: `src/so101_demo_py/src/backends/mujoco/{client,observer,reset}.py`
- Modify: `src/so101_demo_py/src/application/pick_place.py`
- Modify: `src/so101_demo_py/src/application/phases/*.py`
- Create: `src/so101_demo_py/test/contracts/test_world_lifecycle_ports.py`
- Create: `src/so101_demo_py/test/test_mujoco_world_lifecycle_adapter.py`

**Interfaces:**
- Consumes: atomic MuJoCo evidence, reset, readiness, pause, and shutdown behavior.
- Produces: `WorldPort.snapshot()`, `snapshot_with_receipt()`, `reset(keyframe)`, plus `LifecyclePort.readiness(timeout_s)`, `pause(paused)`, and `shutdown(timeout_s)`.

- [ ] **Step 1: Write RED neutral-evidence and receipt tests**

```python
@dataclass(frozen=True, slots=True)
class WorldEvidence:
    backend: str
    session_id: str
    reset_epoch: int
    simulation_step: int
    simulation_time_s: float
    object_pose: PoseEvidence
    object_twist: TwistEvidence
    contacts: tuple[ContactEvidence, ...]
    evidence_loss: bool
    truncated: bool
    backend_metadata: Mapping[str, object]

def test_service_success_without_observed_epoch_is_invalid(adapter):
    assert adapter.readiness(1.0).error_code == "WORLD_STATE_NOT_CONFIRMED"
```

- [ ] **Step 2: Run against direct MuJoCo dependencies**

Run: `python3 -m pytest -q src/so101_demo_py/test/contracts/test_world_lifecycle_ports.py src/so101_demo_py/test/test_mujoco_world_lifecycle_adapter.py`

Expected: FAIL because phases consume concrete types and raw service outcomes.

- [ ] **Step 3: Implement the ports and MuJoCo adapters**

```python
class WorldPort(Protocol):
    def snapshot(self) -> WorldEvidence: ...
    def snapshot_with_receipt(self) -> ReceivedWorldEvidence: ...
    def reset(self, keyframe: str) -> ResetReceipt: ...

class LifecyclePort(Protocol):
    def readiness(self, timeout_s: float) -> ReadinessResult: ...
    def pause(self, paused: bool) -> PauseReceipt: ...
    def shutdown(self, timeout_s: float) -> ShutdownResult: ...
```

Validate finite values, session/epoch, monotonic sequence/step, receipt freshness, collision identity, truncation, and observed post-request world state. Keep raw MuJoCo quantities in `backend_metadata`.

- [ ] **Step 4: Run tests and one installed complete MuJoCo execute**

```bash
python3 -m pytest -q src/so101_demo_py/test/contracts/test_world_lifecycle_ports.py \
  src/so101_demo_py/test/test_mujoco_world_lifecycle_adapter.py
colcon build --base-paths src --packages-select so101_demo_py so101_mujoco_support \
  --build-base build/fusion-t6 --install-base install/fusion-t6 --log-base log/fusion-t6
. install/fusion-t6/setup.sh
ros2 run so101_demo_py pick_place --backend mujoco --run-mode execute \
  --policy-id light_cup_wall_pick --policy-version v1 \
  --evidence-file /tmp/so101-fusion-t6.json
```

Expected: PASS, complete success, installed prefix/bundle recorded, bounded shutdown leaves no owned orphan.

- [ ] **Step 5: Commit world/lifecycle extraction**

```bash
git add src/so101_demo_py/src/ports src/so101_demo_py/src/backends/mujoco \
  src/so101_demo_py/src/application src/so101_demo_py/test
git commit -m "refactor(so101): extract world lifecycle ports"
```

### Task 7: Extract PlanningScenePort and RobotControlPort

**Files:**
- Create: `src/so101_demo_py/src/ports/planning_scene.py`
- Create: `src/so101_demo_py/src/ports/robot_control.py`
- Create: `src/so101_demo_py/src/control/robot_control.py`
- Modify: `src/so101_demo_py/src/control/planning_scene/*.py`
- Modify: `src/so101_demo_py/src/application/phases/*.py`
- Create: `src/so101_demo_py/test/contracts/test_planning_scene_port.py`
- Create: `src/so101_demo_py/test/contracts/test_robot_control_port.py`

**Interfaces:**
- Consumes: shared MoveIt, trajectory, gripper, robot-state, TF, Planning Scene, and ACM implementations.
- Produces: typed robot action methods plus scene world/shadow synchronization and auditable leases.

- [ ] **Step 1: Write RED ports and side-effect tests**

```python
def test_scene_attachment_is_not_physical_grasp(scene):
    result = scene.attach_shadow("cup", "so101_tcp")
    assert result.scene_applied
    assert not result.physical_grasp_proved

def test_execute_rejects_stale_start_state(control, stale_plan):
    assert control.execute(stale_plan).error_code == "PLAN_START_STATE_MISMATCH"
```

- [ ] **Step 2: Run while phases still instantiate concrete clients**

Run: `python3 -m pytest -q src/so101_demo_py/test/contracts/test_planning_scene_port.py src/so101_demo_py/test/contracts/test_robot_control_port.py`

Expected: FAIL with missing ports.

- [ ] **Step 3: Implement exact port methods and inject them**

```python
class RobotControlPort(Protocol):
    def current_joint_state(self, timeout_s: float) -> JointStateEvidence: ...
    def plan_joint_waypoints(self, request: JointWaypointRequest) -> PlanResult: ...
    def plan_tcp_motion(self, request: TcpMotionRequest) -> PlanResult: ...
    def execute(self, plan: PlanResult) -> ExecutionResult: ...
    def command_gripper(self, request: GripperRequest) -> GripperResult: ...
    def stop(self, reason: str) -> StopResult: ...

class PlanningScenePort(Protocol):
    def add_world_object(self, request: WorldObjectRequest) -> SceneResult: ...
    def attach_shadow(self, object_id: str, link_name: str) -> SceneResult: ...
    def detach_shadow(self, object_id: str) -> SceneResult: ...
    def synchronize_object_pose(self, object_id: str, pose: PoseEvidence) -> SceneResult: ...
    def temporary_allow_collision(self, pair: tuple[str, str]) -> SceneLease: ...
```

Every lease/attachment records matching release/detach. Recovery reverses only acquired side effects.

- [ ] **Step 4: Prove no direct clients in application and run MuJoCo**

```bash
if rg -n 'create_client|ActionClient|FollowJointTrajectory' src/so101_demo_py/src/application; then exit 1; fi
python3 -m pytest -q src/so101_demo_py/test/contracts/test_planning_scene_port.py \
  src/so101_demo_py/test/contracts/test_robot_control_port.py
. install/fusion-t6/setup.sh
ros2 run so101_demo_py pick_place --backend mujoco --run-mode execute \
  --policy-id light_cup_wall_pick --policy-version v1 \
  --evidence-file /tmp/so101-fusion-t7.json
```

Expected: no direct client creation; contracts and complete execute pass.

- [ ] **Step 5: Commit control/scene extraction**

```bash
git add src/so101_demo_py/src/ports src/so101_demo_py/src/control \
  src/so101_demo_py/src/application src/so101_demo_py/test
git commit -m "refactor(so101): extract robot and scene ports"
```

### Task 8: Add optional PhaseEvidencePort and explicit capability requirements

**Files:**
- Create: `src/so101_demo_py/src/ports/phase_evidence.py`
- Create: `src/so101_demo_py/src/backends/mujoco/phase_evidence.py`
- Modify: `src/so101_demo_py/src/ports/capabilities.py`
- Modify: `src/so101_demo_py/src/application/qualification.py`
- Modify: `src/so101_demo_py/src/application/phases/transport.py`
- Create: `src/so101_demo_py/test/contracts/test_phase_evidence_port.py`
- Create: `src/so101_demo_py/test/test_capability_requirements.py`

**Interfaces:**
- Consumes: committed MuJoCo physics-step transport evidence.
- Produces: `BackendCapabilities`, `CapabilityRequirements.validate()`, and optional trace begin/boundary/finish methods.

- [ ] **Step 1: Write RED optionality tests**

```python
def test_base_execute_accepts_missing_trace(gazebo_capabilities):
    assert CapabilityRequirements.base_execute().validate(gazebo_capabilities).accepted

def test_mujoco_qualification_requires_lossless_trace(mujoco_without_trace):
    result = CapabilityRequirements.mujoco_qualification().validate(mujoco_without_trace)
    assert result.error_code == "CAPABILITY_MISSING"
```

- [ ] **Step 2: Run while tracing is a concrete dependency**

Run: `python3 -m pytest -q src/so101_demo_py/test/contracts/test_phase_evidence_port.py src/so101_demo_py/test/test_capability_requirements.py`

Expected: FAIL because trace selection is implicit.

- [ ] **Step 3: Implement capabilities and diagnostic-only tracing**

```python
class PhaseEvidencePort(Protocol):
    def begin_trace(self, phase: str) -> TraceReceipt: ...
    def mark_boundary(self, trace_id: str, boundary: str) -> BoundaryReceipt: ...
    def finish_trace(self, trace_id: str) -> PhaseTrace: ...
```

Trace methods only observe/report. They cannot mutate policy/trajectory/world or pause physics.

- [ ] **Step 4: Verify optional Gazebo and required MuJoCo behavior**

```bash
python3 -m pytest -q src/so101_demo_py/test/contracts/test_phase_evidence_port.py \
  src/so101_demo_py/test/test_capability_requirements.py
. install/fusion-t6/setup.sh
ros2 run so101_demo_py pick_place --backend mujoco --run-mode execute \
  --policy-id light_cup_wall_pick --policy-version v1 \
  --evidence-file /tmp/so101-fusion-t8.json
```

Expected: fake Gazebo passes base capability validation; MuJoCo execute emits lossless trace evidence.

- [ ] **Step 5: Commit capability-gated tracing**

```bash
git add src/so101_demo_py/src/ports src/so101_demo_py/src/backends/mujoco/phase_evidence.py \
  src/so101_demo_py/src/application src/so101_demo_py/test
git commit -m "refactor(so101): gate phase trace by capability"
```

### Task 9: Centralize runtime composition and result classification

**Files:**
- Create: `src/so101_demo_py/src/runtime/composition.py`
- Create: `src/so101_demo_py/src/runtime/result_manifest.py`
- Modify: `src/so101_demo_py/src/core/domain.py`
- Modify: `src/so101_demo_py/src/application/pick_place.py`
- Modify: `src/so101_demo_py/src/cli/pick_place.py`
- Create: `src/so101_demo_py/test/test_runtime_composition.py`
- Create: `src/so101_demo_py/test/test_run_result_classification.py`

**Interfaces:**
- Consumes: ports/adapters, `LoadedPolicy`, and `QualificationBundle`.
- Produces: `compose_backend(request) -> BackendComposition`; `RunStatus` values `SUCCEEDED`, `FAILED`, `INVALID`, `REJECTED`; separate `QualificationStatus` values `QUALIFIED`, `NOT_QUALIFIED`.

- [ ] **Step 1: Write RED classification/import-boundary tests**

```python
def test_valid_policy_failure_is_not_invalid(factory):
    result = factory(error_code="PATH_TOLERANCE_VIOLATED", evidence_valid=True)
    assert result.run_status is RunStatus.FAILED
    assert result.qualification_status is QualificationStatus.NOT_QUALIFIED

def test_contaminated_evidence_is_invalid(factory):
    assert factory(evidence_valid=False).run_status is RunStatus.INVALID
```

AST checks reject imports rooted at `so101_demo.backends`, `mujoco`, `gazebo`, or `ros_gz` from `core` and `application`.

- [ ] **Step 2: Run before composition is centralized**

Run: `python3 -m pytest -q src/so101_demo_py/test/test_runtime_composition.py src/so101_demo_py/test/test_run_result_classification.py`

Expected: FAIL because construction/status logic is distributed.

- [ ] **Step 3: Implement composition and rich result manifest**

```python
@dataclass(frozen=True, slots=True)
class BackendComposition:
    backend: str
    capabilities: BackendCapabilities
    robot_control: RobotControlPort
    planning_scene: PlanningScenePort
    world: WorldPort
    lifecycle: LifecyclePort
    phase_evidence: PhaseEvidencePort | None
    policy: LoadedPolicy
    bundle: QualificationBundle

@dataclass(frozen=True, slots=True)
class RunResult:
    run_status: RunStatus
    qualification_status: QualificationStatus
    backend: str
    session_id: str
    reset_epoch: int
    policy_sha256: str
    bundle_sha256: str
    first_failed_phase: str | None
    failure_category: FailureCategory | None
    error_code: str | None
    evidence_refs: tuple[str, ...]
```

- [ ] **Step 4: Run boundaries and one complete MuJoCo execute**

```bash
python3 -m pytest -q src/so101_demo_py/test/test_runtime_composition.py \
  src/so101_demo_py/test/test_run_result_classification.py \
  src/so101_demo_py/test/test_core_import_boundaries.py
. install/fusion-t6/setup.sh
ros2 run so101_demo_py pick_place --backend mujoco --run-mode execute \
  --policy-id light_cup_wall_pick --policy-version v1 \
  --evidence-file /tmp/so101-fusion-t9.json
```

Expected: `SUCCEEDED` and every required provenance/evidence field is present.

- [ ] **Step 5: Commit composition and result semantics**

```bash
git add src/so101_demo_py/src/runtime src/so101_demo_py/src/core \
  src/so101_demo_py/src/application src/so101_demo_py/src/cli src/so101_demo_py/test
git commit -m "refactor(so101): centralize backend composition"
```

### Task 10: Unify visual geometry and keep backend physics assets separate

**Files:**
- Create: `src/so101_demo_py/assets/common/{visual,task_objects}/`
- Create: `src/so101_demo_py/assets/common/geometry-manifest.yaml`
- Create: `src/so101_demo_py/assets/mujoco/{collision,scene.xml,so101.xml}`
- Create: `src/so101_demo_py/assets/gazebo/{collision,world.sdf}`
- Create: `src/so101_demo_py/test/test_geometry_manifest.py`
- Create: `src/so101_demo_py/test/test_asset_closure.py`
- Modify: `src/so101_demo_py/setup.py`

**Interfaces:**
- Consumes: qualified MuJoCo assets and committed Gazebo URDF/SDF/world assets.
- Produces: one common visual/task source, distinct collision/physics trees, and installed manifest entries with source, format, dimensions/scale, and SHA-256.

- [ ] **Step 1: Write RED parity and closure tests**

```python
def test_backends_share_visual_source(manifest):
    assert manifest["backends"]["mujoco"]["visual_source"] == "assets/common/visual"
    assert manifest["backends"]["gazebo"]["visual_source"] == "assets/common/visual"

def test_installed_assets_do_not_reference_legacy_packages(installed_texts):
    assert not any("so101_mujoco_demo_py" in text or "so101_gazebo_demo_py" in text
                   for text in installed_texts)
```

- [ ] **Step 2: Run before the asset tree exists**

Run: `python3 -m pytest -q src/so101_demo_py/test/test_geometry_manifest.py src/so101_demo_py/test/test_asset_closure.py`

Expected: FAIL with missing manifest/assets.

- [ ] **Step 3: Copy/de-duplicate visuals and rewrite references explicitly**

```yaml
schema_version: 1
stable_names:
  tcp: so101_tcp
  task_object: light_plastic_cup
backends:
  mujoco: {visual_source: assets/common/visual, collision_source: assets/mujoco/collision}
  gazebo: {visual_source: assets/common/visual, collision_source: assets/gazebo/collision}
```

Preserve MuJoCo convex decomposition/fingertip pads and Gazebo primitive/SDF collision/physics. Compare names, dimensions, visuals, TCP, and initial object pose; do not compare contact-force semantics.

- [ ] **Step 4: Verify source and installed closure**

```bash
python3 -m pytest -q src/so101_demo_py/test/test_geometry_manifest.py src/so101_demo_py/test/test_asset_closure.py
colcon build --base-paths src --packages-select so101_demo_py \
  --build-base build/fusion-t10 --install-base install/fusion-t10 --log-base log/fusion-t10
. install/fusion-t10/setup.sh
python3 -m pytest -q src/so101_demo_py/test/test_asset_closure.py \
  --installed-share "$(ros2 pkg prefix --share so101_demo_py)"
```

Expected: common geometry matches and collision trees remain backend-specific; no old-package path is read.

- [ ] **Step 5: Commit asset ownership**

```bash
git add src/so101_demo_py/assets src/so101_demo_py/setup.py src/so101_demo_py/test
git commit -m "refactor(so101): unify visual geometry assets"
```

### Task 11: Add separate launchers over common launch composition

**Files:**
- Create: `src/so101_demo_py/src/runtime/launch_composition.py`
- Create: `src/so101_demo_py/launch/so101_mujoco.launch.py`
- Create: `src/so101_demo_py/launch/so101_mujoco_pick_place.launch.py`
- Create: `src/so101_demo_py/launch/so101_gazebo.launch.py`
- Create: `src/so101_demo_py/launch/so101_gazebo_pick_place.launch.py`
- Create: `src/so101_demo_py/test/test_launch_composition.py`
- Modify: `src/so101_demo_py/setup.py`

**Interfaces:**
- Consumes: runtime composition, policy registry, installed asset paths.
- Produces: `build_launch_description(backend: str, pick_place: bool) -> LaunchDescription` and four explicit user entry points; no default backend.

- [ ] **Step 1: Write RED argument/ownership tests**

```python
COMMON_ARGUMENTS = {"run_mode", "execute", "headless", "policy_id", "policy_version",
                    "session_id", "evidence_file", "readiness_timeout_s"}

def test_launchers_do_not_declare_backend_argument(launch_sources):
    assert all('DeclareLaunchArgument("backend"' not in source for source in launch_sources)
```

Also require `mujoco_scene` only for MuJoCo and `gazebo_world` only for Gazebo.

- [ ] **Step 2: Run before launchers exist**

Run: `python3 -m pytest -q src/so101_demo_py/test/test_launch_composition.py`

Expected: FAIL with missing launch files.

- [ ] **Step 3: Implement thin launchers and common composition**

```python
def generate_launch_description():
    return build_launch_description(backend="mujoco", pick_place=True)
```

Log backend, source commit, installed prefix, policy/bundle hashes, execute state, ROS domain, and Gazebo partition when applicable. Do not add a real launcher.

- [ ] **Step 4: Inspect installed launch arguments and MuJoCo dry-run**

```bash
python3 -m pytest -q src/so101_demo_py/test/test_launch_composition.py
colcon build --base-paths src --packages-select so101_demo_py \
  --build-base build/fusion-t11 --install-base install/fusion-t11 --log-base log/fusion-t11
. install/fusion-t11/setup.sh
ros2 launch so101_demo_py so101_mujoco_pick_place.launch.py --show-args
ros2 launch so101_demo_py so101_gazebo_pick_place.launch.py --show-args
ros2 launch so101_demo_py so101_mujoco_pick_place.launch.py \
  run_mode:=dry_run execute:=false evidence_file:=/tmp/so101-fusion-t11.json
```

Expected: arguments are backend-correct and manifest uses the installed package.

- [ ] **Step 5: Commit launch composition**

```bash
git add src/so101_demo_py/src/runtime/launch_composition.py src/so101_demo_py/launch \
  src/so101_demo_py/setup.py src/so101_demo_py/test/test_launch_composition.py
git commit -m "feat(so101): add explicit simulator launchers"
```

### Task 12: Implement Gazebo adapters without importing its old workflow

**Files:**
- Create: `src/so101_demo_py/src/backends/gazebo/{observer,reset,lifecycle,transport}.py`
- Modify: `src/so101_demo_py/src/runtime/composition.py`
- Create: `src/so101_demo_py/test/test_gazebo_world_lifecycle_adapter.py`

**Interfaces:**
- Consumes: committed Gazebo observer/reset/transport behavior and neutral ports.
- Produces: Gazebo `WorldPort`/`LifecyclePort`, capabilities, and metadata retaining contact depth/force, collision names, world stats, partition, and bridge identity.

- [ ] **Step 1: Write RED adapter tests**

```python
def test_gazebo_evidence_is_neutral_without_mujoco_semantics(adapter):
    evidence = adapter.snapshot()
    assert evidence.backend == "gazebo"
    assert "contact_depth_m" in evidence.backend_metadata
    assert "signed_distance_m" not in evidence.backend_metadata

def test_reset_requires_new_observed_epoch(adapter):
    assert adapter.reset("home").observed_after_request
```

- [ ] **Step 2: Run before registration**

Run: `python3 -m pytest -q src/so101_demo_py/test/test_gazebo_world_lifecycle_adapter.py`

Expected: FAIL because no Gazebo adapter exists.

- [ ] **Step 3: Adapt evidence and declare capabilities**

```python
GAZEBO_CAPABILITIES = BackendCapabilities(
    atomic_snapshot=False,
    snapshot_with_receipt=True,
    reset_epoch=True,
    pause=False,
    viewer_camera=False,
    physical_contact_force=True,
    lossless_physics_step_trace=False,
)
```

Do not migrate the legacy Gazebo state machine or duplicate its motion/MoveIt code.

- [ ] **Step 4: Run adapters and installed Gazebo dry-run**

```bash
python3 -m pytest -q src/so101_demo_py/test/test_gazebo_world_lifecycle_adapter.py \
  src/so101_demo_py/test/contracts/test_world_lifecycle_ports.py
. install/fusion-t11/setup.sh
ros2 launch so101_demo_py so101_gazebo_pick_place.launch.py \
  run_mode:=dry_run execute:=false evidence_file:=/tmp/so101-fusion-t12.json
```

Expected: Gazebo selects `gazebo.yaml`, reports trace unavailable, and passes base-execute capability validation.

- [ ] **Step 5: Commit Gazebo adapters**

```bash
git add src/so101_demo_py/src/backends/gazebo src/so101_demo_py/src/runtime/composition.py \
  src/so101_demo_py/test
git commit -m "feat(so101): add gazebo backend adapters"
```

### Task 13: Execute Gazebo normally and report its first real failure

**Files:**
- Modify: `src/so101_demo_py/src/application/pick_place.py`
- Modify: `src/so101_demo_py/src/runtime/result_manifest.py`
- Create: `src/so101_demo_py/test/test_gazebo_execute_result.py`
- Update: `docs/experiments/so101-demo-py-fusion-experiment-ledger.md`

**Interfaces:**
- Consumes: Gazebo composition and the common nine-phase application.
- Produces: a normal execute result: `FAILED` or `SUCCEEDED` for valid evidence, `INVALID` only for provenance/initial-state/evidence/infrastructure pollution, never `SKIPPED`.

- [ ] **Step 1: Write RED non-gating result tests**

```python
def test_policy_failure_reports_real_boundary(fake_gazebo):
    result = run(fake_gazebo.fail_at("MOVE_ABOVE_OBJECT", "PATH_TOLERANCE_VIOLATED"))
    assert result.run_status is RunStatus.FAILED
    assert result.qualification_status is QualificationStatus.NOT_QUALIFIED
    assert result.first_failed_phase == "MOVE_ABOVE_OBJECT"
    assert result.error_code == "PATH_TOLERANCE_VIOLATED"

def test_skipped_is_not_a_run_status():
    assert "SKIPPED" not in {value.value for value in RunStatus}
```

- [ ] **Step 2: Run and expose pre-rejection or invalid conflation**

Run: `python3 -m pytest -q src/so101_demo_py/test/test_gazebo_execute_result.py`

Expected: FAIL until Gazebo follows common execution/classification.

- [ ] **Step 3: Wire common execution without Gazebo policy changes**

```python
if evidence_valid and action.status is not ActionStatus.SUCCEEDED:
    return failed_result(
        backend="gazebo",
        first_failed_phase=current_state.value,
        error_code=action.failure.code,
        qualification_status=QualificationStatus.NOT_QUALIFIED,
    )
```

Do not add Gazebo-specific waypoint, tolerance, retry, phase, or contact thresholds.

- [ ] **Step 4: Run one bounded installed Gazebo execute**

```bash
colcon build --base-paths src --packages-select so101_demo_py \
  --build-base build/fusion-t13 --install-base install/fusion-t13 --log-base log/fusion-t13
. install/fusion-t13/setup.sh
ros2 launch so101_demo_py so101_gazebo_pick_place.launch.py \
  run_mode:=execute execute:=true policy_id:=light_cup_wall_pick policy_version:=v1 \
  evidence_file:=/tmp/so101-fusion-gazebo-execute.json
python3 -m json.tool /tmp/so101-fusion-gazebo-execute.json
```

Expected: nonzero exit for `FAILED`, zero for `SUCCEEDED`; either is accepted when evidence is valid. `INVALID` requires repair/retry and cannot satisfy this task.

- [ ] **Step 5: Record evidence and commit result handling**

```bash
python3 -m pytest -q src/so101_demo_py/test/test_gazebo_execute_result.py
git add src/so101_demo_py/src/application/pick_place.py \
  src/so101_demo_py/src/runtime/result_manifest.py src/so101_demo_py/test/test_gazebo_execute_result.py \
  docs/experiments/so101-demo-py-fusion-experiment-ledger.md
git commit -m "feat(so101): report gazebo execute boundary"
```

### Task 14: Convert both old packages to thin compatibility forwarders

**Files:**
- Modify: `src/so101_mujoco_demo_py/{package.xml,setup.py}`
- Replace: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/*.py`
- Replace: `src/so101_mujoco_demo_py/launch/*.launch.py`
- Modify: `src/so101_gazebo_demo_py/{package.xml,setup.py}`
- Replace: `src/so101_gazebo_demo_py/src/*.py`
- Replace: `src/so101_gazebo_demo_py/launch/*.launch.py`
- Create: `src/so101_demo_py/test/test_legacy_forwarders.py`
- Create: `src/so101_demo_py/test/test_forbidden_legacy_ownership.py`

**Interfaces:**
- Consumes: new CLI/launch entry points and explicit old-to-new argument maps.
- Produces: one deprecation warning, exact forwarding to the new installed prefix/bundle, and errors for unmappable arguments.

- [ ] **Step 1: Write RED forwarding and ownership tests**

```python
def test_old_mujoco_entry_uses_new_bundle(run_old, run_new):
    assert run_old().bundle_sha256 == run_new(backend="mujoco").bundle_sha256

def test_legacy_packages_own_no_runtime_assets(repo_root):
    assert legacy_runtime_owned_files(repo_root) == []
```

- [ ] **Step 2: Run and prove legacy ownership still exists**

Run: `python3 -m pytest -q src/so101_demo_py/test/test_legacy_forwarders.py src/so101_demo_py/test/test_forbidden_legacy_ownership.py`

Expected: FAIL with duplicated logic/assets.

- [ ] **Step 3: Replace entry points and launchers with explicit maps**

```python
def main(argv: Sequence[str] | None = None) -> int:
    warnings.warn("so101_mujoco_demo_py is deprecated; use so101_demo_py", DeprecationWarning, stacklevel=2)
    return so101_demo.cli.pick_place.main(map_legacy_mujoco_args(argv))
```

Remove duplicated logic/policies/models/meshes/fixtures only after new path tests pass in this same change. Unmappable legacy arguments raise a user-facing error.

- [ ] **Step 4: Build all packages and verify forwarding provenance**

```bash
colcon build --base-paths src --packages-select so101_demo_py so101_mujoco_demo_py so101_gazebo_demo_py \
  --build-base build/fusion-t14 --install-base install/fusion-t14 --log-base log/fusion-t14
. install/fusion-t14/setup.sh
python3 -m pytest -q src/so101_demo_py/test/test_legacy_forwarders.py \
  src/so101_demo_py/test/test_forbidden_legacy_ownership.py \
  src/so101_demo_py/test/test_asset_closure.py
```

Expected: old/new commands resolve one new prefix/bundle and legacy trees own no runtime implementation.

- [ ] **Step 5: Commit the compatibility window**

```bash
git add src/so101_mujoco_demo_py src/so101_gazebo_demo_py src/so101_demo_py/test
git commit -m "refactor(so101): make legacy demos forwarders"
```

### Task 15: Add the zero-I/O real-arm extension stub

**Files:**
- Create: `src/so101_demo_py/src/backends/real_stub/{backend,safety}.py`
- Modify: `src/so101_demo_py/src/runtime/composition.py`
- Create: `src/so101_demo_py/test/test_real_stub.py`

**Interfaces:**
- Consumes: port result types and `real_stub.yaml`.
- Produces: real capabilities and `REAL_HARDWARE_NOT_CONFIGURED` rejection for readiness, planning, execution, gripper, reset, stop, and recovery.

- [ ] **Step 1: Write RED fail-closed/zero-I-O tests**

```python
@pytest.mark.parametrize("operation", ["readiness", "plan_joint_waypoints", "plan_tcp_motion",
                                        "execute", "command_gripper", "reset", "stop"])
def test_every_real_operation_rejects_without_io(operation, io_spies):
    result = invoke_real_stub(operation)
    assert result.error_code == "REAL_HARDWARE_NOT_CONFIGURED"
    assert result.run_status is RunStatus.REJECTED
    io_spies.assert_no_calls()
```

Spies cover device enumeration, `open`, serial, socket, subprocess, ROS publishers/action/service clients, and hardware-plugin loading.

- [ ] **Step 2: Run before stub exists**

Run: `python3 -m pytest -q src/so101_demo_py/test/test_real_stub.py`

Expected: FAIL with missing backend.

- [ ] **Step 3: Implement only capabilities and structured rejection**

```python
def reject() -> RejectedResult:
    return RejectedResult(error_code="REAL_HARDWARE_NOT_CONFIGURED")
```

Do not create a real launcher and do not map simulation reset to hardware recovery.

- [ ] **Step 4: Verify zero side effects and launcher absence**

```bash
python3 -m pytest -q src/so101_demo_py/test/test_real_stub.py
test ! -e src/so101_demo_py/launch/so101_real.launch.py
if rg -n 'serial|pyudev|socket|create_publisher|ActionClient|create_client' src/so101_demo_py/src/backends/real_stub; then exit 1; fi
```

Expected: PASS with no I/O symbol or launch file.

- [ ] **Step 5: Commit the real extension boundary**

```bash
git add src/so101_demo_py/src/backends/real_stub \
  src/so101_demo_py/src/runtime/composition.py src/so101_demo_py/test/test_real_stub.py
git commit -m "feat(so101): add fail closed real stub"
```

### Task 16: Gate the complete source, build, install, and ownership contract

**Files:**
- Create: `src/so101_demo_py/scripts/check_fusion_contract.sh`
- Create: `src/so101_demo_py/test/test_installed_provenance.py`
- Create: `src/so101_demo_py/README.md`
- Update: `docs/experiments/so101-demo-py-fusion-experiment-ledger.md`

**Interfaces:**
- Consumes: all three ROS packages and the final implementation tree.
- Produces: a reproducible gate proving nonzero package/test discovery, installed namespace/prefix/executables/launchers/assets/policies, backend boundaries, and absence of legacy ownership.

- [ ] **Step 1: Write RED installed-provenance tests**

```python
def test_manifest_matches_installed_prefix(run_manifest, installed_prefix):
    assert run_manifest["package_prefix"] == str(installed_prefix)
    assert run_manifest["source_commit"] == git_head()

def test_collection_is_nonzero(pytest_collection):
    assert pytest_collection.collected > 0
```

- [ ] **Step 2: Run before the final overlay/gate exists**

Run: `python3 -m pytest -q src/so101_demo_py/test/test_installed_provenance.py`

Expected: FAIL because no final installed manifest is available.

- [ ] **Step 3: Implement the scoped gate and operator README**

```bash
#!/usr/bin/env bash
set -euo pipefail
colcon list --base-paths src | rg '^(so101_demo_py|so101_mujoco_demo_py|so101_gazebo_demo_py)\s'
python3 -m pytest -q src/so101_demo_py/test
python3 -m pytest --collect-only -q src/so101_demo_py/test | rg '[1-9][0-9]* tests collected'
git diff --check
```

README documents the four launch commands, policy/version selection, Gazebo non-gating semantics, real-stub boundary, evidence locations, and separate MuJoCo lifecycles.

- [ ] **Step 4: Build and run the clean installed gate**

```bash
colcon build --base-paths src --packages-select-up-to so101_demo_py so101_mujoco_demo_py so101_gazebo_demo_py \
  --build-base build/fusion-final --install-base install/fusion-final --log-base log/fusion-final
. install/fusion-final/setup.sh
src/so101_demo_py/scripts/check_fusion_contract.sh
python3 -m pytest -q src/so101_demo_py/test/test_installed_provenance.py
ros2 pkg prefix so101_demo_py
ros2 pkg executables so101_demo_py
```

Expected: all tests pass, discovery is nonzero, and every runtime resource resolves under `install/fusion-final`.

- [ ] **Step 5: Record and commit the static acceptance gate**

```bash
git add src/so101_demo_py/scripts/check_fusion_contract.sh \
  src/so101_demo_py/test/test_installed_provenance.py src/so101_demo_py/README.md \
  docs/experiments/so101-demo-py-fusion-experiment-ledger.md
git commit -m "test(so101): gate unified installed runtime"
```

### Task 17: Re-qualify MuJoCo with five FULL_RESTART successes

**Files:**
- Update: `docs/experiments/so101-demo-py-fusion-experiment-ledger.md`
- Runtime evidence outside repository: `/tmp/so101-debug-fusion-full-restart-*`

**Interfaces:**
- Consumes: clean `install/fusion-final`, fixed source/policy/bundle, `Lifecycle.FULL_RESTART`, qualification runner.
- Produces: exactly five consecutive `VALID`/`SUCCEEDED` runs using independent full stacks and identical provenance.

- [ ] **Step 1: Pre-register the batch**

```yaml
lifecycle: FULL_RESTART
required_consecutive_successes: 5
policy_id: light_cup_wall_pick
policy_version: v1
backend: mujoco
invalid_run_effect: invalidate_batch
valid_failure_effect: break_streak
```

Record source commit, installed prefix/hash, policy/bundle hash, ROS domains/ports, abort criteria, process ownership, and evidence root before launch.

- [ ] **Step 2: Verify frozen provenance and preserved process ownership**

```bash
. install/fusion-final/setup.sh
git status --short
ros2 pkg prefix so101_demo_py
sha256sum "$(ros2 pkg prefix --share so101_demo_py)/config/policies/light_cup_wall_pick/v1/mujoco.yaml"
tmux list-sessions
fusion_bundle_sha256="$(python3 -m so101_demo.runtime.provenance --print-bundle-sha256)"
printf '%s\n' "$fusion_bundle_sha256"
```

Expected: only the pre-registered ledger change is dirty, prefix/hash are exact, and no unowned process is selected for control.

- [ ] **Step 3: Run the bounded FULL_RESTART batch**

```bash
. install/fusion-final/setup.sh
fusion_bundle_sha256="$(python3 -m so101_demo.runtime.provenance --print-bundle-sha256)"
ros2 run so101_demo_py run_qualification \
  --batch-id fusion-full-restart-001 --lifecycle FULL_RESTART --count 5 \
  --fingerprint "$fusion_bundle_sha256" \
  --evidence-root /tmp/so101-debug-fusion-full-restart-001 \
  --base-domain-id 180 --base-port 27500 --headless
```

Expected: five independent stacks, five `VALID`/`SUCCEEDED` results, no drift, exit 0 only after the fifth win.

- [ ] **Step 4: Verify the batch independently**

```bash
. install/fusion-final/setup.sh
fusion_bundle_sha256="$(python3 -m so101_demo.runtime.provenance --print-bundle-sha256)"
python3 -m so101_demo.application.qualification verify-batch \
  --evidence-root /tmp/so101-debug-fusion-full-restart-001 \
  --expected-lifecycle FULL_RESTART --expected-count 5 \
  --expected-bundle "$fusion_bundle_sha256"
```

Expected: `QUALIFIED`; any invalid run, valid failure, lifecycle mismatch, or hash drift rejects the batch.

- [ ] **Step 5: Commit only the ledger checkpoint**

```bash
git add docs/experiments/so101-demo-py-fusion-experiment-ledger.md
git commit -m "test(so101): record full restart five wins"
```

### Task 18: Re-qualify RESET_WORLD 5/5 and capture fresh visual/numeric evidence

**Files:**
- Update: `docs/experiments/so101-demo-py-fusion-experiment-ledger.md`
- Create: `src/so101_demo_py/docs/provenance.json`
- Runtime evidence outside repository: `/tmp/so101-debug-fusion-reset-world-*` and one non-counting GUI review directory

**Interfaces:**
- Consumes: the exact frozen source/policy/bundle from Task 17 and `Lifecycle.RESET_WORLD`.
- Produces: an independent five-win batch, one fresh non-counting GUI/numeric review, final provenance, and completed checkpoint.

- [ ] **Step 1: Pre-register the independent RESET_WORLD batch**

```yaml
lifecycle: RESET_WORLD
required_consecutive_successes: 5
reuse_full_restart_results: false
policy_id: light_cup_wall_pick
policy_version: v1
backend: mujoco
```

- [ ] **Step 2: Run and verify RESET_WORLD**

```bash
. install/fusion-final/setup.sh
fusion_bundle_sha256="$(python3 -m so101_demo.runtime.provenance --print-bundle-sha256)"
ros2 run so101_demo_py run_qualification \
  --batch-id fusion-reset-world-001 --lifecycle RESET_WORLD --count 5 \
  --fingerprint "$fusion_bundle_sha256" \
  --evidence-root /tmp/so101-debug-fusion-reset-world-001 \
  --base-domain-id 190 --base-port 27600 --headless
python3 -m so101_demo.application.qualification verify-batch \
  --evidence-root /tmp/so101-debug-fusion-reset-world-001 \
  --expected-lifecycle RESET_WORLD --expected-count 5 \
  --expected-bundle "$fusion_bundle_sha256"
```

Expected: five `VALID`/`SUCCEEDED` runs and independent `QUALIFIED` output.

- [ ] **Step 3: Capture one fresh non-counting GUI mirror**

```bash
tmux new-session -d -s so101-fusion-gui \
  'source ~/gui-env.zsh && source /data/work/ws_moveit/.worktrees/so101-demo-py-fusion/install/fusion-final/setup.zsh && ros2 launch so101_demo_py so101_mujoco_pick_place.launch.py run_mode:=execute execute:=true headless:=false evidence_file:=/tmp/so101-debug-fusion-gui/result.json'
```

Use ai-station CUA `snapshot -> inspect -> fresh snapshot`. Record image path/hash and final world pose/twist, contact, joint/TF, controller, Planning Scene, session/epoch, and bundle hash. This run does not enter either 5/5 denominator.

- [ ] **Step 4: Run the completion audit**

```bash
git status --short
python3 -m pytest -q src/so101_demo_py/test
rg -n 'so101_mujoco_demo_py|so101_gazebo_demo_py' src/so101_demo_py \
  --glob '*.py' --glob '*.yaml' --glob '*.xml' --glob '*.sdf'
test ! -e src/so101_demo_py/launch/so101_real.launch.py
```

Expected: only intentional compatibility-test strings remain; unified source is the sole control owner; both batch verifiers pass; Gazebo has a valid execute result; real stub has zero side effects; preserved external state is unchanged.

- [ ] **Step 5: Finalize provenance and commit the completion checkpoint**

```bash
python3 -m json.tool src/so101_demo_py/docs/provenance.json >/dev/null
git diff --check
git add docs/experiments/so101-demo-py-fusion-experiment-ledger.md \
  src/so101_demo_py/docs/provenance.json
git commit -m "test(so101): qualify unified mujoco bundle"
```

Expected: final checkpoint cites both five-win batches, the valid Gazebo policy-result run, fresh GUI/numeric evidence, installed provenance, and preserved worker/process state. Stop without push or merge.
