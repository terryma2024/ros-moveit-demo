# SO-101 MuJoCo ROS 2 Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不修改 `src/so101_gazebo_demo_py/**` 的前提下，新建独立 ROS 2 Python package `so101_mujoco_demo_py` 与最小 C++ 支持 package `so101_mujoco_support`，用 MuJoCo + `mujoco_ros2_control` 实现 SO-101 pick-place 的 ROS 2 / MoveIt 2 / 纯物理抓取链路。

**Architecture:** `so101_mujoco_demo_py` 从第一笔实现提交起就是独立 `ament_python` package。它拥有自己的 MJCF、launch、配置、domain/workflow、MoveIt adapter、MuJoCo observer/reset、可重放 upstream patch/build/provenance 工具和测试；`so101_mujoco_support` 提供来自同一 simulation step 的原子 pose/twist/contact/reset-generation 证据。reset-qualified runtime 强制从官方稳定 0.0.3 commit 加最小 reset hook patch 构建到隔离 dependency overlay；Gazebo package 只作为历史行为来源，不能成为 build、test、runtime 或 installed-asset 依赖。

**Tech Stack:** Ubuntu 24.04、ROS 2 Jazzy、Python 3.12、`ament_python`、`ament_cmake`、`rclpy`、MoveIt 2、`ros2_control`、`mujoco_vendor 0.0.8`、`mujoco_ros2_control 0.0.3`、MuJoCo 3.x、MJCF、`pluginlib`、`realtime_tools`、`pytest`、GTest、`launch_testing`。

## Reset-Qualified Dependency Constraints

- Upstream is exactly `https://github.com/ros-controls/mujoco_ros2_control`, tag `0.0.3`, commit `35ba8174b62d9560093614f981a3d4b978a96036`; floating `main` is forbidden.
- Reset-qualified runtime must come from `/data/work/ws_mujoco_ros2_control_003/install`; apt 0.0.3 remains underlay only and `/opt/ros/jazzy` is never overwritten.
- Source order is exactly `/opt/ros/jazzy/setup.zsh` → dependency overlay `setup.zsh` → project `install/setup.zsh`.
- The repository owns a minimal replayable patch and build/provenance scripts under `src/so101_mujoco_demo_py/**`; it does not vendor or runtime-load an upstream checkout.
- The patch adds a default no-op virtual `on_reset()` to the plugin base and calls it once per initialized plugin only after a successful central reset. Invalid keyframes call it zero times.
- Evidence `reset_epoch` comes only from an atomic reset generation incremented by `on_reset()` and consumed by `update()`; time decrease and pose jump are forbidden epoch authorities.

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

**Interfaces:** `ContactSample` contains `body1_id`, `geom1_id`, `body1`, `geom1`, `body2_id`, `geom2_id`, `body2`, `geom2`, world position/normal, `signed_distance_m`, and `normal_force_n`. `SimulationEvidence` contains `header` (simulation time and `world` frame), `publisher_sequence`, `simulation_step`, `reset_epoch`, `simulation_session_id`, `paused`, `object_body_id`, `object_body`, object pose/twist, `has_contact`, `minimum_signed_distance_m`, `maximum_normal_force_n`, `truncated`, and separate `left_fingertip_contacts`, `right_fingertip_contacts`, `other_object_contacts` arrays. One publish call must use one locked MuJoCo snapshot; `(simulation_session_id, reset_epoch, simulation_step)` is the consumer ordering key. `SimulationEvidencePlugin::on_reset()` atomically increments a generation and does nothing else; when `update()` sees a new generation it assigns both consumed generation and authoritative `reset_epoch` to that observed value and resets step to zero. A pending generation bypasses only the ordinary publish-period throttle so the first post-reset `update()` publishes it. The pinned base also exposes default no-op `on_pause(bool paused)`; each successful, including idempotent, `SetPause` call notifies every plugin exactly once, and the evidence plugin stores only an atomic authoritative pause value. Time decrease, pose jump, and time-equality pause inference are forbidden; `publisher_sequence` remains monotonic across reset.

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

### Task 10A: Build the Reset-Qualified Dependency Overlay

**Files:**
- Create: `src/so101_mujoco_demo_py/patches/mujoco_ros2_control-0.0.3-reset-hook.patch`
- Create: `src/so101_mujoco_demo_py/scripts/{build_reset_qualified_overlay.sh,check_reset_qualified_runtime.py}`
- Create: `src/so101_mujoco_demo_py/test/test_reset_qualified_dependency.py`
- Update: `src/so101_mujoco_demo_py/config/dependency-lock.yaml`
- Update: `src/so101_mujoco_support/include/so101_mujoco_support/simulation_evidence_plugin.hpp`
- Update: `src/so101_mujoco_support/src/simulation_evidence_plugin.cpp`
- Update: `src/so101_mujoco_support/test/test_simulation_evidence_plugin.cpp`
- Update: migration ledger

**Interfaces:** The build script uses the dedicated source checkout `/data/work/ws_mujoco_ros2_control_003/src/mujoco_ros2_control`. If absent it clones only the official repository and checks out exact commit `35ba8174b62d9560093614f981a3d4b978a96036`; if present it verifies remote URL, HEAD, clean status, and patch state and fails closed instead of resetting or cleaning. It applies the exact versioned patch and installs only to `/data/work/ws_mujoco_ros2_control_003/install`. The patch adds default no-op `virtual void on_reset() {}` and invokes it at the successful tail of central `reset_simulation_state`, after all state/interface updates, once for every initialized plugin; invalid keyframes return before entering central reset and invoke zero hooks. The runtime checker requires `mujoco_ros2_control`, `mujoco_ros2_control_msgs`, and `mujoco_ros2_control_plugins` to resolve to the dependency overlay, `mujoco_vendor` to resolve to `/opt/ros/jazzy`, the project packages to resolve to project install, the base header to contain the hook, executable/library hashes to match the lock, and upstream commit/tag plus patch SHA-256 to match exactly.

- [ ] Write RED tests that require the exact upstream URL/tag/commit, overlay prefix, patch SHA-256, source order, exact four-prefix mapping, default-compatible `on_reset()` and `on_pause(bool)` hook signatures, exactly-once reset success, zero-call invalid-keyframe reset, exactly-once successful/idempotent pause notification, zero-call failed pause notification, generation consumption without lost increments, and pending-generation priority over the ordinary publish throttle. Tests must apply the patch to a disposable clean checkout and must reject floating refs or `/opt/ros/jazzy` installation targets.
- [ ] Run RED; expected failures are absent patch/build/checker artifacts and missing `on_reset()` in the apt header.
- [ ] Create the minimal patch and replay scripts. Do not copy upstream source into this repository and do not use `/data/work/so_arm_ws` as an input.
- [ ] Run `src/so101_mujoco_demo_py/scripts/build_reset_qualified_overlay.sh`; it must source `/opt/ros/jazzy/setup.zsh`, build the three pinned upstream packages with `colcon build --merge-install --install-base /data/work/ws_mujoco_ros2_control_003/install`, and run their upstream tests. Then source `/opt/ros/jazzy/setup.zsh`, `/data/work/ws_mujoco_ros2_control_003/install/setup.zsh`, and project `install/setup.zsh` in that order and run `python3 src/so101_mujoco_demo_py/scripts/check_reset_qualified_runtime.py` to record URL/tag/commit/patch/header/runtime hashes and the exact four-prefix mapping. Save raw logs under `/tmp/so101-debug-mujoco-migration/`.
- [ ] Rebuild `so101_mujoco_support` and `so101_mujoco_demo_py` after sourcing dependency overlay, run focused/package/Ruff/isolation/protected-tree gates, and commit only dependency-hook artifacts plus the required support-plugin generation change as `build(so101_mujoco): qualify reset dependency hook`.

---

### Task 10B: Implement Transactional Pause/Reset/Step

**Files:**
- Create: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/mujoco/{client.py,reset.py}`
- Create: `src/so101_mujoco_demo_py/test/{test_mujoco_reset.py,test_reset_live_contract.py}`
- Update: launch/config and ledger

**Interfaces:** `MujocoResetClient.reset("task_start")` performs running strict deactivate → pause → keyframe `ResetWorld` → bounded resume → strict activate → re-pause → exactly one bounded simulation step → atomic evidence verification and returns `ResetReceipt(old_epoch, new_epoch, keyframe, simulation_step, simulation_session_id)`. The one-step value is fixed by CP-030 evidence and is not a threshold relaxation. Within the original deadline it may retry only typed `EvidenceStale`; every other evidence/controller/session/epoch/pose failure is terminal. Failure leaves the world paused with an explicit error.

- [ ] Preserve the existing Task 10 dirty work. Complete RED tests for the exact service order, timeout, typed-stale-only retry, epoch mismatch, controller failure, invalid keyframe, failure-paused behavior, and two idempotent reset calls.
- [ ] Implement only against interfaces proven by Task 10A; do not invent APIs from newer `main`.
- [ ] Before runtime, preregister EXP-023 with prior EXP-022 and a confirmed-empty ROS domain 105 or higher. Source `/opt/ros/jazzy` → dependency overlay → project install and record PID, prefix, commit, patch, binary/header, MJCF and config provenance.
- [ ] Execute two live `task_start` reset cycles. Require each epoch to increment exactly once; record four finite pause-window atomic snapshots; require object error ≤ `0.003 m`, each of six joints ≤ `0.002 rad`, controllers active, final paused state, and failure paths paused. Invalid keyframe must leave epoch unchanged.
- [ ] Run upstream/package tests, real Ruff gate, `colcon test`, two-package build, dependency-overlay provenance/isolation, and both protected Gazebo tree gates.
- [ ] Commit only Task 10 Python/test/metadata/ledger paths as `feat(so101_mujoco): add deterministic world reset`. Do not push.

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
