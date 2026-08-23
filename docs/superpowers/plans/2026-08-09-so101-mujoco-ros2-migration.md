# SO-101 MuJoCo ROS 2 Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不修改 `src/so101_gazebo_demo_py/**` 的前提下，新建独立 ROS 2 Python package `so101_mujoco_demo_py` 与最小 C++ 支持 package `so101_mujoco_support`，用 MuJoCo + `mujoco_ros2_control` 实现 SO-101 pick-place 的 ROS 2 / MoveIt 2 / 纯物理抓取链路。

**Architecture:** `so101_mujoco_demo_py` 从第一笔实现提交起就是独立 `ament_python` package。它拥有自己的 MJCF、launch、配置、domain/workflow、MoveIt adapter、MuJoCo observer/reset、可重放 upstream patch/build/provenance 工具和测试；`so101_mujoco_support` 提供来自同一锁定 MuJoCo snapshot 的原子 pose/twist/contact/reset-generation 证据。reset-qualified runtime 强制从官方稳定 0.0.3 commit 加最小 reset/pause/state-snapshot hook patch 构建到隔离 dependency overlay；成功/幂等 re-pause 在 `sim_mutex_` 下发布 step-zero paused snapshot，不通过 StepSimulation 推进 physics；Gazebo package 只作为历史行为来源，不能成为 build、test、runtime 或 installed-asset 依赖。

**Tech Stack:** Ubuntu 24.04、ROS 2 Jazzy、Python 3.12、`ament_python`、`ament_cmake`、`rclpy`、MoveIt 2、`ros2_control`、`mujoco_vendor 0.0.8`、`mujoco_ros2_control 0.0.3`、MuJoCo 3.x、MJCF、`pluginlib`、`realtime_tools`、`pytest`、GTest、`launch_testing`。

## Reset-Qualified Dependency Constraints

- Upstream is exactly `https://github.com/ros-controls/mujoco_ros2_control`, tag `0.0.3`, commit `35ba8174b62d9560093614f981a3d4b978a96036`; floating `main` is forbidden.
- Reset-qualified runtime must come from `/data/work/ws_mujoco_ros2_control_003/install`; apt 0.0.3 remains underlay only and `/opt/ros/jazzy` is never overwritten.
- Source order is exactly `/opt/ros/jazzy/setup.zsh` → dependency overlay `setup.zsh` → project `install/setup.zsh`.
- The repository owns a minimal replayable patch and build/provenance scripts under `src/so101_mujoco_demo_py/**`; it does not vendor or runtime-load an upstream checkout.
- The patch adds source-compatible default no-op virtuals `on_reset()`, `on_pause(bool paused)`, and `on_state_snapshot(const mjModel * model, const mjData * data, bool paused)`; ordinary third-party plugins require no changes.
- A successful central reset calls `on_reset()` once per initialized plugin; an invalid keyframe calls it zero times. Every successful or idempotent `SetPause(true)` calls `on_pause(true)` and then exactly one `on_state_snapshot(model_, mj_data_, true)` per initialized plugin while `sim_mutex_` is held; pause false and failed requests call zero snapshot hooks.
- The snapshot hook is read-only and is not generic `update()`: it must not advance physics or write qpos/qvel/ctrl/xfrc/constraint. Atomic evidence contains object pose/twist/contact only; `/joint_states` remains independent asynchronous controller feedback.
- Evidence `reset_epoch` comes only from the atomic generation incremented by `on_reset()`. A running `update()` must not consume a pending generation; only a successful paused snapshot publication consumes it as `old+1`, `simulation_step=0`, `paused=true`. Publisher contention retains the pending generation.
- Task 10 keeps the original 10 s deadline, object tolerance `0.003 m`, and per-joint tolerance `0.002 rad`. Only typed `EvidenceStale` permits retrying idempotent `SetPause(true)` within that same deadline. Task 10 qualification never calls `StepSimulation(1)`.

## Frozen References and Working Boundary

- Approved design: `docs/superpowers/specs/2026-08-09-so101-mujoco-ros2-migration-design.md`.
- Implementation branch: `codex/so101-mujoco-ros2`.
- ai-station worktree: `/data/work/ws_moveit/.worktrees/so101-mujoco-ros2`.
- Exact rebased main baseline: `d300e7a41fb274d6d7e120699b7040666ea61904`.
- Behavior/provenance source only: `8d7913e7f552a40ee627d65be8b873ac16748bc9`.
- Historical kickoff: `8464038e7cc13f638e2e336c625ed6677fa7db22`.
- Rejected implementation backup, read-only: `codex/so101-mujoco-ros2-pre-isolation-20260810` @ `3add34f8390b78a1f4a13ff49aefb2dc87638245`.
- Allowed implementation trees: `src/so101_mujoco_demo_py/**`, `src/so101_mujoco_support/**`, the migration ledger, and this migration's spec/plan.
- Protected tree: `src/so101_gazebo_demo_py/**`. No add, edit, delete, format, generated file, test, symlink, or cleanup is allowed there.
- The rejected backup may be inspected with `git show`; never cherry-pick a whole backup commit. Any reused implementation must be rewritten into the new package namespace and recorded in provenance.
- Preserve all unrelated tmux sessions and processes, including `so101-py-qual` and `kimi`. Only stop PIDs that this plan starts and records.
- Simulation only. Never connect to a real SO-101 controller.
- Do not push, merge, force-update, or delete branches from the ai-station implementation session. The orchestrator owns publication.

## Mandatory Gate After Every Task

Run from the target worktree before every task commit and again immediately after it:

```bash
src/so101_mujoco_demo_py/scripts/check_migration_isolation.sh
git diff --quiet d300e7a41fb274d6d7e120699b7040666ea61904 -- src/so101_gazebo_demo_py
test -z "$(git status --short -- src/so101_gazebo_demo_py)"
git diff --cached --check
git status --short
```

If any isolation command fails, stop immediately and record a checkpoint. Do not repair the protected tree in a later commit and do not introduce an exception list.

Runtime evidence belongs under `/tmp/so101-debug-mujoco-migration/`. The repository stores only hashes, concise results, decisions, and provenance. Every experiment is written to `docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md` as `PLANNED` before execution and changed to `VALID` or `INVALID` afterward.

---

### Task 1: Freeze the Rebased Baseline and Encode Isolation

**Files:**
- Create: `src/so101_mujoco_demo_py/scripts/check_migration_isolation.sh`
- Create: `docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md`
- Create: `src/so101_mujoco_demo_py/test/test_repository_isolation_contract.py`

**Interfaces:**
- Script exits non-zero if the protected Gazebo tree differs from `d300e7a`, if new package metadata/imports depend on the Gazebo Python package, or if the worktree is not on `codex/so101-mujoco-ros2`.
- Ledger front matter records `main_base_commit`, `behavior_source_commit`, `branch`, `worktree`, `evidence_root`, `next_experiment`, and the strict no-weld/no-teleport contract.

- [ ] Verify current state without touching processes:

```bash
cd /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
git fetch origin main codex/so101-mujoco-ros2
test "$(git merge-base HEAD origin/main)" = d300e7a41fb274d6d7e120699b7040666ea61904
git status --short --branch
git worktree list --porcelain
tmux list-sessions 2>/dev/null || true
pgrep -af 'gz sim|move_group|rviz2|mujoco|pick_place' || true
```

- [ ] Write the isolation test first. It must assert the exact main base, reject `so101_gazebo_demo_py` in `package.xml`, `setup.py`, Python imports and launch resource lookup, and require the backup branch to appear only in documentation.
- [ ] Run RED:

```bash
python3 -m pytest -q src/so101_mujoco_demo_py/test/test_repository_isolation_contract.py
```

Expected: failure because the script and ledger do not exist.

- [ ] Implement the executable shell gate and ledger header. The gate uses `git diff --quiet` and `git status --short -- src/so101_gazebo_demo_py`; its namespace scan excludes `docs/provenance.json` because provenance must name source paths.
- [ ] Run GREEN, the mandatory gate, then commit only the three listed files:

```bash
python3 -m pytest -q src/so101_mujoco_demo_py/test/test_repository_isolation_contract.py
src/so101_mujoco_demo_py/scripts/check_migration_isolation.sh
git add -- src/so101_mujoco_demo_py/scripts/check_migration_isolation.sh src/so101_mujoco_demo_py/test/test_repository_isolation_contract.py docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md
git diff --cached --check
git commit -m "test(so101_mujoco): lock package isolation baseline"
src/so101_mujoco_demo_py/scripts/check_migration_isolation.sh
```

---

### Task 2: Create the Independent `ament_python` Package

**Files:**
- Create: `src/so101_mujoco_demo_py/package.xml`
- Create: `src/so101_mujoco_demo_py/setup.py`
- Create: `src/so101_mujoco_demo_py/setup.cfg`
- Create: `src/so101_mujoco_demo_py/resource/so101_mujoco_demo_py`
- Create: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/__init__.py`
- Create: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/cli.py`
- Create: `src/so101_mujoco_demo_py/test/test_package_identity.py`

**Interfaces:** Package name and Python namespace are both exactly `so101_mujoco_demo_py`; console entry point is `pick_place_state_machine = so101_mujoco_demo_py.cli:main`, preserving the existing ROS-facing executable name under the new package identity. There is no dependency on either Gazebo package.

- [ ] Add RED tests for package name, resource marker, entry point, installed share layout, and absence of `gazebo`, `gz_`, `ros_gz`, or `so101_gazebo_demo_py` from metadata/imports.
- [ ] Run RED with `pytest` and `colcon list`; expected failure is missing package metadata.
- [ ] Add the minimal skeleton, including an empty `cli.py` whose `main()` raises a clear “runtime not implemented” error.
- [ ] Run GREEN and build only the new package:

```bash
python3 -m pytest -q src/so101_mujoco_demo_py/test/test_package_identity.py
colcon list --base-paths src | rg '^so101_mujoco_demo_py\s'
colcon build --base-paths src --packages-select so101_mujoco_demo_py --symlink-install
```

- [ ] Run the mandatory isolation gate and commit:

```bash
git add -- src/so101_mujoco_demo_py/package.xml src/so101_mujoco_demo_py/setup.py src/so101_mujoco_demo_py/setup.cfg src/so101_mujoco_demo_py/resource src/so101_mujoco_demo_py/so101_mujoco_demo_py/__init__.py src/so101_mujoco_demo_py/so101_mujoco_demo_py/cli.py src/so101_mujoco_demo_py/test/test_package_identity.py
git diff --cached --check
git commit -m "build(so101_mujoco): create independent Python package"
src/so101_mujoco_demo_py/scripts/check_migration_isolation.sh
```

---

### Task 3: Pin and Prove the MuJoCo Dependency

**Files:**
- Create: `src/so101_mujoco_demo_py/config/dependency-lock.yaml`
- Create: `src/so101_mujoco_demo_py/scripts/check_mujoco_runtime.py`
- Create: `src/so101_mujoco_demo_py/test/test_dependency_contract.py`
- Update: `src/so101_mujoco_demo_py/package.xml`
- Update: migration ledger

**Interfaces:** The early binary probe may use apt 0.0.3, but reset qualification requires tag `0.0.3` commit `35ba8174b62d9560093614f981a3d4b978a96036` plus the repository-owned minimal patch built into `/data/work/ws_mujoco_ros2_control_003/install`. Never overwrite `/opt/ros/jazzy` and never use floating `main`.

- [ ] Record preflight as `PLANNED`; inspect `apt-cache policy`, `ros2 pkg prefix`, package XML, exported targets, services, and plugin headers.
- [ ] Add RED contract tests that require exact version/source/overlay/hash fields and forbid unpinned Git refs.
- [ ] Install apt 0.0.3 if absent for the underlay probe. Record that it is not reset-qualified because its reset preserves time and its plugin base lacks `on_reset()`.
- [ ] Run the probe in the sourced ROS environment and update the ledger to `VALID` or `INVALID` with command logs and SHA-256 hashes.
- [ ] Run tests, mandatory isolation gate, and commit:

```bash
python3 -m pytest -q src/so101_mujoco_demo_py/test/test_dependency_contract.py
python3 src/so101_mujoco_demo_py/scripts/check_mujoco_runtime.py
git add -- src/so101_mujoco_demo_py/config/dependency-lock.yaml src/so101_mujoco_demo_py/scripts/check_mujoco_runtime.py src/so101_mujoco_demo_py/test/test_dependency_contract.py src/so101_mujoco_demo_py/package.xml docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md
git diff --cached --check
git commit -m "build(so101_mujoco): pin simulation dependency"
src/so101_mujoco_demo_py/scripts/check_migration_isolation.sh
```

---

### Task 4: Add Atomic Simulation Evidence Support

**Files:**
- Create: `src/so101_mujoco_support/{CMakeLists.txt,package.xml,so101_mujoco_plugins.xml}`
- Create: `src/so101_mujoco_support/msg/{ContactSample.msg,SimulationEvidence.msg}`
- Create: `src/so101_mujoco_support/include/so101_mujoco_support/simulation_evidence_plugin.hpp`
- Create: `src/so101_mujoco_support/src/simulation_evidence_plugin.cpp`
- Create: `src/so101_mujoco_support/test/test_simulation_evidence_plugin.cpp`

**Interfaces:** `ContactSample` contains `body1_id`, `geom1_id`, `body1`, `geom1`, `body2_id`, `geom2_id`, `body2`, `geom2`, world position/normal, `signed_distance_m`, and `normal_force_n`. `SimulationEvidence` contains `header` (simulation time and `world` frame), `publisher_sequence`, `simulation_step`, `reset_epoch`, `simulation_session_id`, `paused`, `object_body_id`, `object_body`, object pose/twist, `has_contact`, `minimum_signed_distance_m`, `maximum_normal_force_n`, `truncated`, and separate `left_fingertip_contacts`, `right_fingertip_contacts`, `other_object_contacts` arrays. One publish call uses one locked MuJoCo snapshot; `(simulation_session_id, reset_epoch, simulation_step)` is the consumer ordering key. `SimulationEvidencePlugin::on_reset()` atomically increments generation and does nothing else. Under the later Task 10A amendment, ordinary running `update()` retains pending generation and the dedicated paused snapshot path consumes it only after publisher-lock success as `old+1/step0/paused=true`; no-pending ordinary publication cadence stays unchanged. Time decrease, pose jump, and time-equality pause inference are forbidden; `publisher_sequence` remains monotonic across reset.

- [ ] Write GTest RED cases for same-step atomicity, numeric/name id agreement, side classification, force sign, zero-contact aggregates/empty arrays, session immutability, exactly-once generation consumption, idempotent same-time reset epoch change, monotonic publisher sequence, and monotonic step id within one epoch; reject time-decrease and pose-jump authority.
- [ ] Create the standalone `ament_cmake` messages/plugin package. The plugin is read-only except for its publisher state; it never changes qpos/qvel or creates equality constraints.
- [ ] Build and test only the support package:

```bash
colcon build --base-paths src --packages-select so101_mujoco_support
source install/setup.zsh
colcon test --base-paths src --packages-select so101_mujoco_support --event-handlers console_direct+
colcon test-result --verbose
```

- [ ] Run the mandatory isolation gate and commit all listed support-package files as `feat(so101_mujoco): publish atomic simulation evidence`.

---

### Task 5: Define Backend-Neutral Python Contracts and Provenance

**Files:**
- Create: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/simulation/{__init__.py,types.py,protocols.py}`
- Create: `src/so101_mujoco_demo_py/docs/provenance.json`
- Create: `src/so101_mujoco_demo_py/test/{test_simulation_types.py,test_provenance_contract.py}`
- Update: `src/so101_mujoco_demo_py/setup.py`

**Interfaces:** Define immutable `ObjectState`, `ContactEvidence`, `SimulationEvidence`, `ResetReceipt`; protocols `WorldObserver.snapshot() -> SimulationEvidence` and `WorldReset.reset(keyframe: str) -> ResetReceipt`. `SimulationEvidence` carries the same ordering/session/contact fields fixed in spec §10.1; `ResetReceipt` carries `old_epoch`, `new_epoch`, `keyframe`, `simulation_step`, and `simulation_session_id`. Freshness timeout and expected session id are constructor configuration, not call-site parameters. No type may expose Gazebo messages.

- [ ] Add RED tests for type validation, same-step evidence, reset epoch ordering, and provenance entries `{source_commit, source_path, destination_path, source_sha256, adaptation}`.
- [ ] Implement the minimal dataclasses/protocols and provenance validator. Initially provenance contains only files actually adapted from `8d7913e`; do not claim copied files that do not exist.
- [ ] Run target tests, build the Python package, mandatory isolation gate, and commit as `feat(so101_mujoco): define simulation contracts`.

---

### Task 6: Build the SO-101 MJCF and URDF Parity Gate

**Files:**
- Create: `src/so101_mujoco_demo_py/mjcf/{so101.xml,assets/README.md}`
- Create: `src/so101_mujoco_demo_py/config/model-parity.yaml`
- Create: `src/so101_mujoco_demo_py/scripts/check_model_parity.py`
- Create: `src/so101_mujoco_demo_py/test/{test_mjcf_compiles.py,test_model_parity.py}`
- Update: provenance and package data

**Interfaces:** MJCF exposes joints `1`–`6`, TCP site `so101_tcp`, left/right fingertip geoms, actuator/control ranges, home keyframe, and stable geom/body names used by evidence. Parity checks joint axes, limits, zero pose, parent-child transforms, mesh hashes, and TCP pose against the repository URDF assets copied into the new package.

- [ ] Copy only required URDF/mesh inputs into the new package, record their exact `8d7913e` source paths and hashes, and never read them at runtime from an installed Gazebo package.
- [ ] Write RED compile/parity tests, then add the smallest valid MJCF.
- [ ] Run MuJoCo load, FK samples at zero/home/limits, and numeric parity tolerances declared in `model-parity.yaml`; the test must distinguish geometry parity from collision-free or IK feasibility.
- [ ] Run package tests, mandatory isolation gate, and commit as `feat(so101_mujoco): add versioned robot model`.

---

### Task 7: Add the Task Scene and Deterministic Keyframes

**Files:**
- Create: `src/so101_mujoco_demo_py/mjcf/scene.xml`
- Create: `src/so101_mujoco_demo_py/config/task_scene.yaml`
- Create: `src/so101_mujoco_demo_py/test/{test_task_scene.py,test_no_hidden_grasp_constraint.py}`
- Update: provenance and package data

**Interfaces:** Scene contains table, rigid cup, free joint, robot, lights/camera, `home` and `task_start` keyframes. It contains no weld/equality/adhesion/mocap-follow relation and no code path teleports the cup during execute.

- [ ] Write RED structural tests that reject `<equality>`, weld, mocap following, hidden object actuators, and post-start qpos mutation.
- [ ] Implement scene assets and deterministic initial state; declare friction/damping as uncalibrated inputs, not migrated Gazebo values.
- [ ] Load and step headlessly for 10 simulated seconds, prove finite state and a stationary table/cup, save raw log hash in the ledger.
- [ ] Run gates and commit as `feat(so101_mujoco): add deterministic task scene`.

---

### Task 8: Wire `mujoco_ros2_control`, Controllers, and Minimal Launch

**Files:**
- Create: `src/so101_mujoco_demo_py/config/{ros2_controllers.yaml,mujoco_plugins.yaml}`
- Create: `src/so101_mujoco_demo_py/launch/so101_mujoco.launch.py`
- Create: `src/so101_mujoco_demo_py/test/{test_controller_contract.py,test_mujoco_launch.py}`
- Update: package metadata/data files

**Interfaces:** Launch starts MuJoCo, `/clock`, `robot_state_publisher`, controller manager, `joint_state_broadcaster`, and the existing arm trajectory controller name expected by MoveIt. Defaults are `start_simulation:=false`, `run_mode:=dry_run`, and a unique `simulation_session_id`.

- [ ] Write RED launch tests for controller names, six joint interfaces, `use_sim_time`, readiness timeout, session id, and safe defaults.
- [ ] Implement the minimal launch/config without starting MoveIt or workflow.
- [ ] In a dedicated tmux window owned by this task, launch once, query controller/list, `/joint_states`, `/clock`, and atomic evidence, then stop only recorded PIDs.
- [ ] Run launch tests, mandatory isolation gate, and commit as `feat(so101_mujoco): launch ros2 control simulation`.

---

### Task 9: Implement the MuJoCo Observer

**Files:**
- Create: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/mujoco/{__init__.py,observer.py}`
- Create: `src/so101_mujoco_demo_py/test/{test_mujoco_observer.py,test_observer_live_contract.py}`
- Update: package dependencies

**Interfaces:** `MujocoWorldObserver` subscribes to the atomic evidence topic and returns the newest internally consistent `SimulationEvidence`; it rejects stale session ids, mixed reset epochs, non-monotonic steps, missing sides, and messages older than the configured age.

- [ ] Write RED unit tests with synthetic messages and a launch test with real plugin output.
- [ ] Implement subscription, validation, timeout, and diagnostics with no Gazebo imports.
- [ ] Run unit/live tests, package build, mandatory isolation gate, and commit as `feat(so101_mujoco): observe atomic world evidence`.

---

### Task 10A: Build the Reset/Pause/State-Snapshot Qualified Dependency Overlay

**Files:**
- Modify: `src/so101_mujoco_demo_py/patches/mujoco_ros2_control-0.0.3-reset-hook.patch`
- Verify unchanged replay entry point: `src/so101_mujoco_demo_py/scripts/build_reset_qualified_overlay.sh`
- Modify: `src/so101_mujoco_demo_py/scripts/check_reset_qualified_runtime.py`
- Modify: `src/so101_mujoco_demo_py/test/test_reset_qualified_dependency.py`
- Modify: `src/so101_mujoco_demo_py/config/dependency-lock.yaml`
- Modify: `src/so101_mujoco_support/include/so101_mujoco_support/simulation_evidence_plugin.hpp`
- Modify: `src/so101_mujoco_support/src/simulation_evidence_plugin.cpp`
- Modify: `src/so101_mujoco_support/test/test_simulation_evidence_plugin.cpp`
- Modify: `docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md`

**Interfaces:** The build script uses `/data/work/ws_mujoco_ros2_control_003/src/mujoco_ros2_control`, verifies official URL/tag/commit/clean-or-exact-patch state, and installs only to `/data/work/ws_mujoco_ros2_control_003/install`. The base API is exactly `virtual void on_reset() {}`, `virtual void on_pause(bool paused)`, and `virtual void on_state_snapshot(const mjModel * model, const mjData * data, bool paused) {}`. A successful central reset invokes `on_reset()` once per initialized plugin; invalid keyframes invoke zero. Every successful/idempotent `SetPause(true)` invokes `on_pause(true)` followed by exactly one `on_state_snapshot(model_, mj_data_, true)` per initialized plugin under `sim_mutex_`; pause false and failed requests invoke zero snapshots. Snapshot dispatch never calls generic `update()`, advances physics, or writes qpos/qvel/ctrl/xfrc/constraint. `SimulationEvidencePlugin::on_state_snapshot()` uses the shared publish helper; only publisher-lock success consumes pending generation and publishes `old+1/step0/paused=true`. Running update and publisher contention retain pending generation.

- [ ] **Step 1: Extend dependency RED contracts.** Modify `test_reset_qualified_dependency.py` so a disposable clean `35ba8174...` checkout requires the exact default-compatible snapshot signature, `sim_mutex_`-guarded authoritative `mj_data_`, successful/idempotent pause-true exactly-once dispatch after `on_pause(true)`, and zero snapshot dispatch for pause false or failed requests. Assert the patched pause callback contains neither `plugin->update` nor writes matching `qpos|qvel|ctrl|xfrc|constraint`.

- [ ] **Step 2: Extend support-plugin RED contracts.** Modify `test_simulation_evidence_plugin.cpp` to prove: running `update()` cannot consume pending generation; paused snapshot lock success consumes it once and publishes `reset_epoch=old+1`, `simulation_step=0`, `paused=true`; publisher-lock contention leaves the generation pending for a later idempotent snapshot; no-pending update preserves its existing rate; snapshot leaves the force buffer and MuJoCo state byte-for-byte unchanged.

- [ ] **Step 3: Run focused RED before implementation.** Run:

```bash
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_mujoco_ros2_control_003/install/setup.zsh
PYTHONPATH=src/so101_mujoco_demo_py python3 -m pytest -q src/so101_mujoco_demo_py/test/test_reset_qualified_dependency.py
colcon build --base-paths src --packages-select so101_mujoco_support --symlink-install
colcon test --base-paths src --packages-select so101_mujoco_support --ctest-args -R test_simulation_evidence_plugin --output-on-failure
```

Expected: dependency tests fail because `on_state_snapshot` and its `sim_mutex_` dispatch are absent; support tests fail because running `update()` currently consumes pending generation and no snapshot publish path exists. Save complete output under `/tmp/so101-debug-mujoco-migration/task10a-snapshot-hook-red/`.

- [ ] **Step 4: Implement the minimal upstream patch.** Modify only `mujoco_ros2_control-0.0.3-reset-hook.patch`, `dependency-lock.yaml`, and `check_reset_qualified_runtime.py`: add the exact default no-op snapshot virtual; invoke it only in successful/idempotent pause-true paths after `on_pause(true)` while `sim_mutex_` protects authoritative `mj_data_`; extend header/runtime/patch SHA validation. Keep the existing pinned build script and source order; do not copy upstream source into the repository or reset/clean an existing checkout.

- [ ] **Step 5: Implement the minimal shared publisher boundary.** In the support header/cpp, add `on_state_snapshot(const mjModel *, const mjData *, bool) override` and one private `try_publish_snapshot(...)` helper used by ordinary update and snapshot. Gate generation consumption on `authoritative_paused=true` and successful realtime publisher lock; preserve pending generation otherwise. Do not modify the message schema or force-buffer ownership.

- [ ] **Step 6: Run focused GREEN.** Repeat the exact Step 3 commands. Expected: all dependency replay contracts and support snapshot/generation tests pass; inspect test output for zero skipped snapshot cases.

- [ ] **Step 7: Rebuild and qualify the pinned overlay.** Run:

```bash
src/so101_mujoco_demo_py/scripts/build_reset_qualified_overlay.sh
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_mujoco_ros2_control_003/install/setup.zsh
colcon build --base-paths src --packages-select so101_mujoco_support so101_mujoco_demo_py --symlink-install
source install/setup.zsh
python3 src/so101_mujoco_demo_py/scripts/check_reset_qualified_runtime.py --lock src/so101_mujoco_demo_py/config/dependency-lock.yaml
colcon test --base-paths src --packages-select so101_mujoco_support so101_mujoco_demo_py --event-handlers console_direct+
colcon test-result --verbose
src/so101_mujoco_demo_py/scripts/check_ruff.sh
src/so101_mujoco_demo_py/scripts/check_migration_isolation.sh
git diff --quiet d300e7a41fb274d6d7e120699b7040666ea61904 -- src/so101_gazebo_demo_py
test -z "$(git status --short -- src/so101_gazebo_demo_py)"
```

Expected: upstream tests, both package suites, Ruff, exact overlay URL/tag/commit/patch/header/runtime provenance, dependency isolation, and both Gazebo gates pass.

- [ ] **Step 8: Commit only Task 10A scope.** Stage exactly the patch, lock, checker, support header/cpp/test, and Task 10A ledger checkpoint; verify `git diff --cached --check` and both Gazebo gates, then commit `build(so101_mujoco): qualify pause snapshot dependency hook`. Do not push.

---

### Task 10B: Implement Transactional Pause/Reset/Snapshot

**Files:**
- Create: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/mujoco/{client.py,reset.py}`
- Create: `src/so101_mujoco_demo_py/test/{test_mujoco_reset.py,test_reset_live_contract.py}`
- Modify: `src/so101_mujoco_demo_py/package.xml`
- Modify: `docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md`

**Interfaces:** `MujocoResetClient.reset("task_start")` performs running strict deactivate → pause → `ResetWorld(task_start)` → bounded resume → strict activate → re-pause, whose successful/idempotent `SetPause(true)` triggers the snapshot hook → verify `old+1/step0/paused=true` atomic object evidence plus independent fresh `/joint_states` and controller feedback. It never calls StepSimulation. Within the original 10 s deadline only typed `EvidenceStale` may cause another idempotent `pause(True)`; session/epoch/sequence/object/controller/joint failures are terminal. Object error remains `<=0.003 m`, each joint remains `<=0.002 rad`; joints are not atomic message fields. Every success or failure returns/leaves the world paused, and invalid keyframes do not change epoch.

- [ ] **Step 1: Write Python RED service-order tests.** In `test_mujoco_reset.py`, assert the exact call list `switch(deactivate)`, `pause(true)`, `reset_world(task_start)`, `pause(false)`, `switch(activate)`, `pause(true)` followed by evidence/controller/joint verification; assert no `step` call and no `StepSimulation` client construction in the qualification path.

- [ ] **Step 2: Write RED retry and evidence tests.** Require only `EvidenceStale` to trigger idempotent `pause(true)` retry inside the same deadline. Require exact session, `reset_epoch=old+1`, monotonic publisher sequence, `simulation_step=0`, `paused=true`, finite atomic object pose/twist/contact, independent fresh six-joint feedback, active controllers, object error `<=0.003 m`, and each joint error `<=0.002 rad`. Add terminal cases for future/wrong epoch, session mismatch, non-stale observer error, stale joint feedback, inactive controller, object/joint threshold failure, invalid keyframe epoch change, and failure-not-paused.

- [ ] **Step 3: Write RED repeated-reset tests.** Two idempotent `reset("task_start")` calls must return sequential receipts with epochs `n+1` and `n+2`, both `simulation_step=0`, and must each finish paused. An invalid-keyframe call between or after them must fail paused and leave the observed epoch unchanged.

- [ ] **Step 4: Run Python RED.** Run:

```bash
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_mujoco_ros2_control_003/install/setup.zsh
PYTHONPATH=src/so101_mujoco_demo_py python3 -m pytest -q src/so101_mujoco_demo_py/test/test_mujoco_reset.py src/so101_mujoco_demo_py/test/test_reset_live_contract.py
```

Expected: focused failures show the current StepSimulation call, missing typed-stale re-pause retry, and acceptance logic that does not require the dedicated step-zero paused snapshot. Save complete output under `/tmp/so101-debug-mujoco-migration/task10b-transaction-red/`.

- [ ] **Step 5: Implement minimal transaction changes.** Modify only `mujoco/reset.py`, `mujoco/client.py` if removing the qualification-only StepSimulation facade is necessary, the two reset tests, package metadata required by those imports, and the ledger. Delete the step call from `reset()`; after re-pause accept only exact expected-epoch step-zero paused atomic evidence. On typed `EvidenceStale`, call idempotent `pause(True)` and retry within the existing deadline; every other exception enters the existing failure-paused path. Validate freshness of `/joint_states` independently through callback count/timestamp captured after reset.

- [ ] **Step 6: Run focused GREEN and non-live package tests.** Repeat Step 4, then run:

```bash
PYTHONPATH=src/so101_mujoco_demo_py python3 -m pytest -q src/so101_mujoco_demo_py/test -m 'not live'
src/so101_mujoco_demo_py/scripts/check_ruff.sh
colcon build --base-paths src --packages-select so101_mujoco_support so101_mujoco_demo_py --symlink-install
source install/setup.zsh
python3 src/so101_mujoco_demo_py/scripts/check_reset_qualified_runtime.py --lock src/so101_mujoco_demo_py/config/dependency-lock.yaml
colcon test --base-paths src --packages-select so101_mujoco_support so101_mujoco_demo_py --event-handlers console_direct+
colcon test-result --verbose
```

Expected: focused and non-live suites pass, Ruff check and format check pass, the reset unit trace contains no step service, both packages rebuild/test against the qualified overlay, and URL/tag/commit/patch/header/runtime prefix provenance passes before EXP-031 is registered.

- [ ] **Step 7: Pre-register EXP-031 only after GREEN/build/provenance pass.** Append `EXP-031` with `prior_experiment: EXP-030`, `status: PLANNED`, `lifecycle: FULL_RESTART`, exact HEAD plus dirty scope, source order, overlay URL/tag/commit/patch/header/runtime hashes, fresh confirmed-empty `ROS_DOMAIN_ID` integer `>=112`, owned session/PIDs, and evidence path `/tmp/so101-debug-mujoco-migration/exp-031/`. Do not reuse domains 105–111.

- [ ] **Step 8: Run EXP-031 live qualification.** Execute two `task_start` resets and one invalid-keyframe failure. Require each successful reset to increment epoch exactly once, return `simulation_step=0`, publish finite `paused=true` atomic object pose/twist/contact with object error `<=0.003 m`, obtain independent fresh six-joint feedback with each error `<=0.002 rad`, keep controllers active, and end paused. Invalid keyframe must leave epoch unchanged and fail paused. If provenance, readiness, evidence completeness, or cleanup is invalid, mark EXP-031 `INVALID`. If those prerequisites and the evidence contract are valid but a live reset assertion fails, mark EXP-031 `VALID` with behavioral failure, include it in the failure denominator, and stop. If every assertion passes, mark EXP-031 `VALID` with behavioral success. Persist exact commands/exits/hashes and never change step/timeout/threshold/order in response to either failure class.

```bash
setopt PIPE_FAIL
run_exp031() {
mkdir -p /tmp/so101-debug-mujoco-migration/exp-031
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_mujoco_ros2_control_003/install/setup.zsh
source install/setup.zsh
evidence_dir=/tmp/so101-debug-mujoco-migration/exp-031
session_name=so101-mujoco-exp031
launch_rc=125
readiness_rc=125
pytest_rc=125
kill_rc=125
domain_cleanup_rc=125
hash_rc=125

ROS_DOMAIN_ID=112 ros2 node list --no-daemon | tee "$evidence_dir/domain-before-no-daemon.txt"
domain_before_rc=$?

if (( domain_before_rc == 0 )) && [[ ! -s "$evidence_dir/domain-before-no-daemon.txt" ]]; then
  tmux new-session -d -s "$session_name" "zsh -lc 'setopt PIPE_FAIL; cd /data/work/ws_moveit/.worktrees/so101-mujoco-ros2; source /opt/ros/jazzy/setup.zsh; source /data/work/ws_mujoco_ros2_control_003/install/setup.zsh; source install/setup.zsh; ROS_DOMAIN_ID=112 ros2 launch so101_mujoco_demo_py so101_mujoco.launch.py start_simulation:=true headless:=true run_mode:=dry_run simulation_session_id:=exp031-snapshot-domain112 |& tee /tmp/so101-debug-mujoco-migration/exp-031/launch.log'"
  launch_rc=$?
else
  launch_rc=64
fi

if (( launch_rc == 0 )); then
  tmux list-panes -t "$session_name" -F '#{pane_pid}' > "$evidence_dir/pane-pid.txt"
  pane_pid=$(<"$evidence_dir/pane-pid.txt")
  ps -o pid,ppid,lstart,cmd -p "$pane_pid" > "$evidence_dir/pane-owner-before-test.txt"
  pstree -ap "$pane_pid" > "$evidence_dir/process-tree-before-test.txt"

  timeout 45 zsh -lc '
    setopt PIPE_FAIL
    source /opt/ros/jazzy/setup.zsh
    source /data/work/ws_mujoco_ros2_control_003/install/setup.zsh
    source /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/setup.zsh
    export ROS_DOMAIN_ID=112
    until ros2 service list | rg -x "/mujoco_ros2_control_node/(set_pause|reset_world)" | sort | diff -u <(print -l /mujoco_ros2_control_node/reset_world /mujoco_ros2_control_node/set_pause | sort) -; do sleep 0.25; done
    while true; do
      ros2 control list_controllers | tee /tmp/so101-debug-mujoco-migration/exp-031/controllers-readiness.txt
      active_count=0
      for controller_name in arm_controller gripper_controller joint_state_broadcaster; do
        rg -q "^${controller_name}\\s+.*\\sactive$" /tmp/so101-debug-mujoco-migration/exp-031/controllers-readiness.txt && (( active_count += 1 ))
      done
      (( active_count == 3 )) && break
      sleep 0.25
    done
    ros2 topic info -v /so101/simulation/evidence | tee /tmp/so101-debug-mujoco-migration/exp-031/evidence-topic-readiness.txt
    rg -q "Publisher count: [1-9]" /tmp/so101-debug-mujoco-migration/exp-031/evidence-topic-readiness.txt
    timeout 10 ros2 topic echo /so101/simulation/evidence --once > /tmp/so101-debug-mujoco-migration/exp-031/evidence-subscriber-readiness.yaml
    test -s /tmp/so101-debug-mujoco-migration/exp-031/evidence-subscriber-readiness.yaml
  ' |& tee "$evidence_dir/readiness.log"
  readiness_rc=$?
else
  readiness_rc=64
fi

if (( readiness_rc == 0 )); then
  ROS_DOMAIN_ID=112 SO101_MUJOCO_RESET_LIVE_TEST=1 SO101_MUJOCO_SESSION_ID=exp031-snapshot-domain112 \
    python3 -m pytest -q -s src/so101_mujoco_demo_py/test/test_reset_live_contract.py \
    |& tee "$evidence_dir/live-reset-contract.log"
  pytest_rc=$?
fi

print -r -- "$pytest_rc" > "$evidence_dir/pytest-exit-code.txt"
tmux capture-pane -p -t "$session_name" -S -200 > "$evidence_dir/launch-tail-before-cleanup.txt" 2>&1 || true
tail -200 "$evidence_dir/launch.log" > "$evidence_dir/launch-log-tail-before-cleanup.txt" 2>&1 || true
if [[ -n "${pane_pid:-}" ]]; then
  ps -o pid,ppid,lstart,cmd -p "$pane_pid" > "$evidence_dir/pane-owner-after-test.txt" 2>&1 || true
  pstree -ap "$pane_pid" > "$evidence_dir/process-tree-after-test.txt" 2>&1 || true
fi

if tmux has-session -t "$session_name" 2>/dev/null; then
  tmux kill-session -t "$session_name"
  kill_rc=$?
else
  kill_rc=0
fi

timeout 20 zsh -lc '
  source /opt/ros/jazzy/setup.zsh
  export ROS_DOMAIN_ID=112
  while [[ -n "$(ros2 node list --no-daemon)" ]]; do sleep 0.25; done
  ros2 node list --no-daemon
' > "$evidence_dir/domain-after-no-daemon.txt"
domain_cleanup_rc=$?
test ! -s "$evidence_dir/domain-after-no-daemon.txt" || domain_cleanup_rc=1

hash_inputs=()
for evidence_file in \
  "$evidence_dir/launch.log" \
  "$evidence_dir/readiness.log" \
  "$evidence_dir/live-reset-contract.log" \
  "$evidence_dir/process-tree-before-test.txt" \
  "$evidence_dir/process-tree-after-test.txt" \
  "$evidence_dir/launch-tail-before-cleanup.txt" \
  "$evidence_dir/launch-log-tail-before-cleanup.txt" \
  "$evidence_dir/domain-after-no-daemon.txt"; do
  [[ -f "$evidence_file" ]] && hash_inputs+=("$evidence_file")
done
if (( ${#hash_inputs} > 0 )); then
  sha256sum "${hash_inputs[@]}" | tee "$evidence_dir/evidence-sha256.txt"
  hash_rc=$?
else
  : > "$evidence_dir/evidence-sha256.txt"
  hash_rc=0
fi
print -r -- "domain_before_rc=$domain_before_rc launch_rc=$launch_rc readiness_rc=$readiness_rc pytest_rc=$pytest_rc kill_rc=$kill_rc domain_cleanup_rc=$domain_cleanup_rc hash_rc=$hash_rc" \
  | tee "$evidence_dir/exit-codes.txt"

if (( domain_before_rc != 0 || launch_rc != 0 || readiness_rc != 0 || kill_rc != 0 || domain_cleanup_rc != 0 || hash_rc != 0 )); then
  return 64
fi
if (( pytest_rc != 0 )); then
  return "$pytest_rc"
fi
return 0
}
run_exp031
```

Expected: zsh `PIPE_FAIL` preserves every launch/readiness/pytest pipeline failure instead of accepting `tee` success. The first no-daemon node list is empty; pane PID plus before/after `ps` and `pstree` bind ownership to only `so101-mujoco-exp031`. The bounded readiness loop does not exit until both MuJoCo services exist, the unique active-controller count is exactly three for `arm_controller`, `gripper_controller`, and `joint_state_broadcaster`, an evidence publisher exists, and a one-message evidence subscription succeeds. Regardless of pytest outcome, its exact exit code, process tree, and launch tail are saved before only the named task-owned tmux session is stopped; the final bounded domain-112 no-daemon list must be empty. The hash list includes only evidence files that actually exist, and `hash_rc` is recorded, so an earlier skipped phase cannot create a secondary missing-file failure. Provenance/readiness/evidence-completeness/hash/cleanup pollution makes EXP-031 `INVALID`. With those contracts valid, pytest success is a `VALID` behavioral success and pytest assertion failure is a `VALID` behavioral failure that enters the failure denominator and stops further work. Never use `pkill`.

- [ ] **Step 9: Run final Task 10 gates.** Run the exact Task 10A Step 7 build/provenance/package/Ruff/isolation/Gazebo commands again, plus `git diff --check`. Expected: all pass with no owned runtime remaining and unrelated sessions preserved.

- [ ] **Step 10: Commit only Task 10B scope.** Stage exactly `mujoco/client.py`, `mujoco/reset.py`, `test_mujoco_reset.py`, `test_reset_live_contract.py`, directly required package metadata, and the ledger; verify the index allowlist and Gazebo gates, then commit `feat(so101_mujoco): add transactional pause reset snapshot`. Do not push.

---

### Task 11: Port the ROS-Free Workflow and MoveIt Boundary

**Files:**
- Create under `src/so101_mujoco_demo_py/so101_mujoco_demo_py/`: `domain.py`, `workflow.py`, `runner.py`, `physical_outcome.py`, `release_settle.py`, `motion/**`, `moveit/**`, `recovery/**`
- Create: `src/so101_mujoco_demo_py/config/motion_policies/light_cup_wall_pick.yaml`
- Create corresponding characterization tests under `src/so101_mujoco_demo_py/test/`
- Update: `docs/provenance.json`, package metadata, and `cli.py`

**Interfaces:** Preserve public state names, run modes, failure-code semantics, MoveIt services/actions, planning group `arm`, TCP `so101_tcp`, joints `1`–`6`, collision-shadow behavior, checkpoint transitions, and final result schema. Replace only observer/reset/backend bindings with the Task 5 protocols.

- [ ] Enumerate each source file from `8d7913e` with `git show`; add provenance before adaptation. Do not copy old imports, package resource names, Gazebo messages, or backend tests.
- [ ] Port characterization tests first into the new package namespace and demonstrate RED for missing new modules.
- [ ] Port the minimum domain/workflow/MoveIt code in small boundaries. MoveIt attachment remains a Planning Scene collision shadow and never changes MuJoCo physics.
- [ ] Run all ROS-free characterization tests, then build and test only the two new packages:

```bash
python3 -m pytest -q src/so101_mujoco_demo_py/test -m 'not live'
colcon build --base-paths src --packages-select so101_mujoco_support so101_mujoco_demo_py --symlink-install
colcon test --base-paths src --packages-select so101_mujoco_support so101_mujoco_demo_py --event-handlers console_direct+
colcon test-result --verbose
```

- [ ] Run the mandatory isolation gate and commit as `feat(so101_mujoco): port pick place workflow`.

---

### Task 12: Prove the Headless ROS 2 / MoveIt Execution Chain

**Files:**
- Create: `src/so101_mujoco_demo_py/launch/so101_pick_place.launch.py`
- Create: `src/so101_mujoco_demo_py/test/test_headless_execution_contract.py`
- Update: config, ledger, package data

**Interfaces:** Full launch composes MuJoCo, controllers, robot description/TF, MoveIt, planning scene, observer, reset, and workflow. `dry_run` proves planning without controller execution; `execute` requires an explicit launch argument.

- [ ] Add a RED launch test for node/topic/service/action readiness, TF, planning group, controller mapping, safe defaults, and clean shutdown.
- [ ] Implement launch composition and readiness diagnostics.
- [ ] Run one dry-run and one non-grasp execute to a safe pose. Independently prove: plan accepted, trajectory executed, `/joint_states` converged, MuJoCo evidence moved, and no unrelated stack was started/stopped.
- [ ] Record commands, exit codes, log hashes, ROS graph snapshot and exact HEAD in the ledger.
- [ ] Run gates and commit as `test(so101_mujoco): prove headless execution chain`.

---

### Task 13: Calibrate MuJoCo Contact Evidence and Stop for Approval

**Files:**
- Create: `src/so101_mujoco_demo_py/config/contact_calibration.yaml`
- Create: `src/so101_mujoco_demo_py/scripts/analyze_contact_calibration.py`
- Create: `src/so101_mujoco_demo_py/test/test_contact_calibration_contract.py`
- Update: ledger

**Interfaces:** Calibration produces distributions for no-contact, left-only, right-only, bilateral-touch, over-compression, micro-lift slip, and stable-hold. Proposed thresholds include units, sample count, quantiles, safety margin, false-positive/negative observations, exact model/config hashes, and are disabled until user authorization.

- [ ] Pre-register the calibration matrix as `PLANNED`; do not copy Gazebo depth/penetration thresholds.
- [ ] Write RED schema tests requiring all regimes and rejecting an enabled policy without `approved_by_user: true`.
- [ ] Collect the bounded headless matrix with no weld/equality/teleport and analyze it into the proposed YAML.
- [ ] Mark the experiment `VALID` or `INVALID`, run gates, and commit as `experiment(so101_mujoco): calibrate contact evidence`.
- [ ] **Mandatory stop:** present the threshold table, plots/log hashes, failure cases, and proposed acceptance values to the user. Do not start Task 14 until the user explicitly approves the thresholds. Approval of this plan is not threshold approval.

---

### Task 14: Enforce Physical Grasp and Final Placement Outcomes

**Files:**
- Update: `src/so101_mujoco_demo_py/config/{contact_calibration.yaml,motion_policies/light_cup_wall_pick.yaml}`
- Update: `physical_outcome.py`, `release_settle.py`, workflow/runner/recovery modules
- Create/update: physical-outcome, micro-lift, transport, release, and final-placement tests in the new package
- Update: ledger and provenance

**Interfaces:** Success requires fresh bilateral contact, bounded compression/force, cup motion caused by gripper motion during micro-lift, stable transport evidence, actual release, final cup pose/twist inside the approved region, and no forbidden constraints or qpos writes. Planning/action success alone is insufficient.

- [ ] Encode only user-approved thresholds and approval metadata.
- [ ] Add RED tests for one-sided touch, stale evidence, table-supported false positive, collision-shadow-only attachment, cup teleport, excessive force, slip, and unstable final placement.
- [ ] Implement the smallest outcome/recovery changes and run characterization plus live single-cycle experiments.
- [ ] Independently verify MoveIt state, controller result, MuJoCo pose/twist/contact, reset epoch, and final physical region. Store raw evidence outside the repo and hashes in the ledger.
- [ ] Run gates and commit as `feat(so101_mujoco): enforce physical pick place outcome`.

---

### Task 15: Qualify Restart/Reset Repeatability and Prepare Review

**Files:**
- Create: `src/so101_mujoco_demo_py/scripts/run_qualification.py`
- Create: `src/so101_mujoco_demo_py/test/test_qualification_contract.py`
- Create: `docs/experiments/so101-mujoco-ros2-migration-qualification.md`
- Update: ledger

**Interfaces:** Qualification requires 5 consecutive `FULL_RESTART` successes and, separately, 5 consecutive `RESET_WORLD` successes. A failed attempt resets that series to zero. Each run records git/model/config hashes, session id, reset epoch, ROS graph, controller result, physical evidence summary, final pose/twist, exit code, and artifact hashes.

- [ ] Write RED tests for series reset-on-failure, evidence completeness, exact run count, and rejection of mixed commits/configs.
- [ ] Implement the runner without retry-hiding or threshold mutation.
- [ ] Run the full two-series qualification. Use a fresh visual capture for GUI/RViz/MuJoCo state after headless qualification, but do not treat the screenshot as physical proof.
- [ ] Run the complete verification suite:

```bash
python3 -m pytest -q src/so101_mujoco_demo_py/test
colcon build --base-paths src --packages-select so101_mujoco_support so101_mujoco_demo_py --symlink-install
source install/setup.zsh
colcon test --base-paths src --packages-select so101_mujoco_support so101_mujoco_demo_py --event-handlers console_direct+
colcon test-result --verbose
src/so101_mujoco_demo_py/scripts/check_migration_isolation.sh
git diff --quiet d300e7a41fb274d6d7e120699b7040666ea61904 -- src/so101_gazebo_demo_py
test -z "$(git status --short -- src/so101_gazebo_demo_py)"
git diff --check
```

- [ ] Write the qualification report with pass/fail evidence and unresolved risks. Do not claim success if either consecutive series fails.
- [ ] Commit only qualification files as `test(so101_mujoco): qualify restart and reset repeatability`.
- [ ] Stop the ai-station implementation session at a review checkpoint. Do not push or merge; report exact HEAD, test counts, runtime evidence paths/hashes, process cleanup, Gazebo zero-diff result, and any failure.

## Final Acceptance Checklist

- [ ] `so101_mujoco_demo_py` and `so101_mujoco_support` are independently discoverable and buildable.
- [ ] Neither package has build/test/runtime/resource dependency on `so101_gazebo_demo_py` or Gazebo.
- [ ] `git diff --quiet d300e7a41fb274d6d7e120699b7040666ea61904 -- src/so101_gazebo_demo_py` passes and the protected-tree status is empty.
- [ ] URDF/MJCF parity, controller, TF, MoveIt, atomic evidence, reset, contact, physical outcome, and final placement gates all pass.
- [ ] No weld/equality/adhesion/mocap following/object teleport/direct object qpos/qvel write exists in the positive path.
- [ ] Contact thresholds have separate explicit user approval after Task 13 calibration.
- [ ] Five consecutive full restarts and five consecutive world resets pass on one fixed commit/model/config.
- [ ] Existing unrelated tmux sessions/processes remain intact; task-owned processes are cleaned up.
- [ ] Remote worker has not pushed or merged; final publication remains an orchestrator/user decision.
