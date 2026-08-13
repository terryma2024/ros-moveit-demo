# SO-101 Python Demo Canonicalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `so101_demo_py` the only Python SO-101 simulation package, remove both deprecated compatibility packages, update the current MuJoCo integration guide through fork release `so101-0.0.3-r6`, and publish a source-derived Python pick-place architecture guide.

**Architecture:** Enforce one canonical ament package and Python namespace while retaining explicit MuJoCo/Gazebo launch composition. Historical experiments, plans, specs, and provenance snapshots remain immutable process records; active code, scripts, tests, profiles, READMEs, and guides may not depend on or direct users to either removed package.

**Tech Stack:** ROS 2 Jazzy, ament_python, Python 3.12, pytest, Ruff 0.15.20, colcon, MuJoCo, Gazebo Harmonic, MoveIt 2.

## Global Constraints

- Preserve the qualified MuJoCo v1 policy bytes at SHA-256 `aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356`.
- Keep explicit simulator launchers; do not introduce a default backend.
- Do not rewrite historical process records under `docs/experiments/`, `docs/plans/`, `docs/superpowers/plans/`, `docs/superpowers/specs/`, or `docs/provenance/`.
- Remove `src/so101_gazebo_demo_py/` and `src/so101_mujoco_demo_py/` completely.
- Active code, scripts, tests, profiles, READMEs, and guides must contain no dependency on the removed packages.
- Real-arm support remains fail-closed through `real_stub`; no hardware I/O is added.

---

### Task 1: Add the canonical-package repository contract

**Files:**
- Modify: `src/so101_demo_py/test/test_forbidden_legacy_ownership.py`
- Modify: `src/so101_demo_py/scripts/check_fusion_contract.sh`
- Modify: `scripts/check_backend_integration.py`

**Interfaces:**
- Consumes: repository root and the canonical package directory `src/so101_demo_py`.
- Produces: a failing-then-green contract requiring both removed directories to be absent and active surfaces to resolve only through `so101_demo_py`.

- [ ] Replace compatibility-forwarder assertions with absence assertions and an active-surface text scan.
- [ ] Run the focused pytest and confirm RED because both directories and active references still exist.
- [ ] Update both integration scripts to discover only `so101_demo_py`, its installed executables, assets, policy, and pinned dependency lock.
- [ ] Run the focused pytest and scripts after Tasks 2–3 and require GREEN.

### Task 2: Migrate Teleop's Gazebo Python profile to the canonical owner

**Files:**
- Modify: `src/so101_teleop/config/backends/gazebo_py.yaml`
- Modify: `src/so101_teleop/test/backends/test_cli_adapter.py`
- Modify: `src/so101_teleop/test/backends/test_profiles.py`
- Modify: `src/so101_teleop/test/teleop/test_backend_capabilities.py`
- Modify: `src/so101_teleop/test/teleop/test_main_backend.py`
- Modify: `src/so101_teleop/web/e2e/teleop.spec.ts`
- Modify: `src/so101_teleop/web/src/api/client.test.ts`
- Modify: `src/so101_teleop/web/src/components/teleop/environment-panel.test.tsx`

**Interfaces:**
- Consumes: installed `so101_demo_py/pick_place` probe and the existing fixed backend ID `gazebo_py`.
- Produces: a fail-closed profile owned by `so101_demo_py`; unsupported Teleop operations remain disabled instead of targeting deleted executables.

- [ ] Change tests first to expect `owner_package=so101_demo_py`, probe executable `pick_place`, and no unavailable workflow/reset/scene/camera operations.
- [ ] Run focused Python/Web tests and confirm RED against the old profile.
- [ ] Apply the minimal profile changes and update fixtures that display owner-package provenance.
- [ ] Re-run focused tests and require GREEN.

### Task 3: Remove both compatibility packages and all active references

**Files:**
- Delete: `src/so101_gazebo_demo_py/`
- Delete: `src/so101_mujoco_demo_py/`
- Modify: `src/so101_demo_py/README.md`
- Modify: `src/so101_demo_py/src/backends/gazebo/model_asset.py`
- Modify: `src/so101_demo_py/test/test_asset_closure.py`
- Modify: `scripts/install-mujoco-ros2-control.zsh`

**Interfaces:**
- Consumes: canonical package assets, configs, launchers, and `config/mujoco/dependency-lock.yaml`.
- Produces: exactly one discoverable Python SO-101 simulation package and no compatibility surface.

- [ ] Delete the two compatibility directories.
- [ ] Replace legacy-name-specific runtime checks with canonical asset/self-containment checks.
- [ ] Point the fork installer at `src/so101_demo_py/config/mujoco/dependency-lock.yaml`.
- [ ] Verify `colcon list --base-paths src` discovers `so101_demo_py` but neither removed package.

### Task 4: Update the MuJoCo ROS 2 integration guide through r6

**Files:**
- Rewrite: `docs/guides/so101-mujoco-ros2-integration-guide.md`

**Interfaces:**
- Consumes: canonical package layout, dependency lock, gitlink `738e304551b4ea6db020b466086a13db71b65607`, and fork diff `so101-0.0.3-r5..so101-0.0.3-r6`.
- Produces: current build/source/launch/reset/evidence instructions and an explicit r1–r6 change ledger.

- [ ] Replace obsolete package paths and patched-overlay instructions with the committed submodule plus canonical package workflow.
- [ ] Document r6's `on_physics_step(const mjModel*, const mjData*)`, mutex/cadence semantics, all three stepping paths, source-compatibility default, tests, and why controller `update()` cannot provide lossless 500 Hz evidence.
- [ ] Verify every command and path exists in the current tree or installed contract.

### Task 5: Write the source-derived Python pick-place architecture guide

**Files:**
- Create: `docs/pick-place-python-architecture.md`

**Interfaces:**
- Consumes: `so101_demo_py` core/application/ports/control/backends/runtime/cli modules and four explicit launchers.
- Produces: a durable architecture description covering dependency direction, composition, state/evidence flow, backend differences, qualification, failure semantics, and real-arm extension seams.

- [ ] Document package/namespace mapping and layer responsibilities with exact source paths.
- [ ] Add Mermaid diagrams for dependency direction and execute/evidence flow.
- [ ] Explain MuJoCo qualified phases versus Gazebo bounded execute, lifecycle separation, Planning Scene shadow versus simulator truth, and `real_stub` fail-closed behavior.
- [ ] Include extension rules for a future real SO-101 arm without allowing simulator types into the core.

### Task 6: Build and verify on ai-station

**Files:**
- No source changes unless a verified gate exposes a scoped defect.

**Interfaces:**
- Consumes: committed canonicalization branch and the pinned `mujoco_ros2_control` overlay.
- Produces: fresh source, build, installed-prefix, test, policy-hash, and reference-scan evidence.

- [ ] Run focused RED/GREEN tests and complete `src/so101_demo_py/test` plus affected `so101_teleop` tests.
- [ ] Build `so101_teleop`, `so101_mujoco_support`, and `so101_demo_py` into a fresh isolated prefix on ai-station.
- [ ] Source the fork overlay then the new project overlay; prove `ros2 pkg prefix so101_demo_py` and executables resolve there.
- [ ] Run `check_fusion_contract.sh`, `check_backend_integration.py`, Ruff, `git diff --check`, policy hash, directory-absence, and active-reference scans.
- [ ] Confirm the branch is clean and report that live MuJoCo 5/5 was not rerun because policy/runtime behavior was not changed; retain the existing qualified evidence boundary.
