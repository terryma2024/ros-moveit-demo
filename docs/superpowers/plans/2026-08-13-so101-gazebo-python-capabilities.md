# SO-101 Gazebo Python Capabilities Implementation Plan

> **Execution mode:** Use `superpowers:executing-plans` inline in this worktree. Do not delegate. Every behavioral task follows `superpowers:test-driven-development`; every completion claim follows `superpowers:verification-before-completion`.

**Goal:** Add manifest-driven Gazebo Planning Scene setup/read-back, package-owned camera presets, a complete transactional Gazebo reset, honest normal Gazebo workflow execution, and Teleop exposure without changing qualified MuJoCo behavior.

**Architecture:** Keep public backend dispatch in three shared CLIs. Put schemas, requests, receipts, failure phases, and orchestration in backend-neutral modules; keep ROS/MoveIt and simulator operations in adapters. Make `assets/common/geometry-manifest.yaml` the sole task-scene contract and prove the Gazebo SDF agrees with it.

**Tech stack:** Python 3.12, ROS 2 Jazzy, MoveIt 2, Gazebo Harmonic, `ros_gz_bridge`, `gz` transport CLI, launch, ament_python, pytest, Ruff, colcon.

## Fixed Execution Contract

- Worktree: `/data/work/ws_moveit/.worktrees/so101-demo-py-canonical`
- Branch: `codex/so101-demo-py-canonical`
- Approved base: `1fa155e1524fc24b7059e76eb88540abda327ba6`
- Design commit: `fccb1a49`
- Evidence root: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J`
- Ledger: `docs/experiments/so101-gazebo-python-capabilities-experiment-ledger.md`
- Frozen file: `src/so101_demo_py/config/policies/light_cup_wall_pick/v1/mujoco.yaml`
- Frozen SHA-256: `aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356`
- Do not SSH, push, merge, modify main, operate a real arm, clean another worktree, use `gh`, run `ament_uncrustify --reformat`, or broadly kill processes.
- Do not import, read at runtime, invoke, or wrap any `so101_gazebo_demo_cpp` executable/configuration.
- Preserve all baseline tmux sessions and unrelated runtime state. Stop only PIDs started and recorded by this task.

## Evidence Rules

Before any live command, append a ledger experiment in `PLANNED`; immediately before launch change it to `RUNNING`; after complete evidence review change it to exactly one terminal state, `VALID` or `INVALID`. A valid failed product outcome is `VALID` plus `outcome: FAILED`; it stops a qualification sequence. `INVALID` stops the current batch. Never edit an experiment's hypothesis or acceptance contract after moving it to `RUNNING`.

For each RED/GREEN task, preserve the command, collected-test count, exit status, and output under the evidence root. Refuse any test command that collects zero tests. Commit only after the task's focused GREEN and frozen-policy check.

---

### Task 1: Lock the common geometry and SDF parity contract

**Files:**

- Modify: `src/so101_demo_py/assets/common/geometry-manifest.yaml`
- Modify: `src/so101_demo_py/assets/gazebo/world.sdf`
- Create: `src/so101_demo_py/src/core/task_geometry.py`
- Modify: `src/so101_demo_py/test/test_geometry_manifest.py`
- Create: `src/so101_demo_py/test/test_gazebo_sdf_geometry_parity.py`

**Contract:** The manifest defines canonical `table`, `pedestal`, and `plastic_cup` objects with frame, object pose, RGBA, and named primitive geometry/local poses. Counts are exactly `1/1/13`. World SDF model ID `base_pedestal` becomes `pedestal`; collision and diffuse data match the manifest.

- [ ] Add tests that load typed geometry and assert exact IDs, primitive types/counts, dimensions, local 6D poses, world 6D poses, normalized quaternions, and colors.
- [ ] Add an XML parity test that parses `world.sdf`, converts SDF RPY to quaternions, and compares all three models to the manifest within explicit tolerances.
- [ ] Run the two focused files; record nonzero collection and expected RED in `task-01-red.log`.
- [ ] Implement immutable dataclasses plus a strict YAML loader in `core/task_geometry.py`; reject unknown fields, nonfinite/invalid dimensions, duplicate IDs/names, wrong counts, and non-unit quaternions with `SCENE_MANIFEST_INVALID`.
- [ ] Expand the manifest with the current qualified table, pedestal, twelve cup wall boxes, and cylinder bottom; retain existing asset/hash sections.
- [ ] Rename only the Gazebo SDF pedestal model and align parity fields without touching MuJoCo scene bytes.
- [ ] Run focused tests and policy hash; save `task-01-green.log`.
- [ ] Commit: `feat: define canonical task geometry contract`.

### Task 2: Build and verify the manifest-driven MoveIt scene

**Files:**

- Create: `src/so101_demo_py/src/control/planning_scene/task_scene.py`
- Modify: `src/so101_demo_py/src/control/planning_scene/scene.py`
- Modify: `src/so101_demo_py/src/ports/planning_scene.py`
- Modify: `src/so101_demo_py/src/application/scene_setup.py`
- Create: `src/so101_demo_py/src/cli/scene_setup.py`
- Modify: `src/so101_demo_py/src/backends/mujoco/qualified_phases/scene_setup.py`
- Modify: `src/so101_demo_py/setup.py`
- Create: `src/so101_demo_py/test/test_task_scene_builder.py`
- Create: `src/so101_demo_py/test/test_scene_setup_cli.py`
- Modify: `src/so101_demo_py/test/contracts/test_planning_scene_port.py`

**Contract:** `scene_setup` owns backend dispatch and defaults to MuJoCo for compatibility. With no operation it performs `setup`; it also accepts Teleop's fixed `setup|observe|attach|detach|upsert` positional operation. Both backends apply manifest-derived collision objects and require `/get_planning_scene` read-back.

- [ ] Write pure tests for manifest-to-`CollisionObject` conversion and read-back comparison, including ID, membership, attachment, type, dimensions, primitive-local pose, object pose, and `1/1/13` mismatch failures.
- [ ] Write CLI dispatch tests for default MuJoCo, explicit MuJoCo/Gazebo, supported positional operations, stable JSON receipt, and nonzero first-failure exit.
- [ ] Run focused tests and save expected RED in `task-02-red.log`.
- [ ] Extend the planning-scene port with immutable apply/observation/verification receipts while preserving the rule that scene state cannot prove a physical grasp.
- [ ] Implement the builder and ROS clients for `/apply_planning_scene` and `/get_planning_scene` with bounded readiness and convergence.
- [ ] Refactor the existing qualified MuJoCo scene phase to use the shared builder without changing produced object bytes or phase semantics.
- [ ] Point the `scene_setup` entry point at `so101_demo.cli.scene_setup:main`; preserve no-argument launch behavior.
- [ ] Run focused tests, existing qualified scene tests, and policy hash; save `task-02-green.log`.
- [ ] Commit: `feat: share Planning Scene setup across backends`.

### Task 3: Add the shared camera schema and Gazebo adapter

**Files:**

- Create: `src/so101_demo_py/src/core/camera.py`
- Modify: `src/so101_demo_py/src/backends/mujoco/camera_presets.py`
- Create: `src/so101_demo_py/src/backends/gazebo/camera.py`
- Modify: `src/so101_demo_py/src/cli/camera_preset.py`
- Create: `src/so101_demo_py/config/gazebo/camera_views.yaml`
- Create: `src/so101_demo_py/test/test_camera_presets.py`
- Create: `src/so101_demo_py/test/test_gazebo_camera_adapter.py`

**Contract:** One schema/error family, backend-owned YAML, and one CLI. MuJoCo keeps all existing preset names and name-only invocation. Gazebo calls `gz service -s /gui/move_to/pose` using `gz.msgs.GUICamera`/`gz.msgs.Boolean`, `shell=False`, a bounded timeout, and positive `data: true` acknowledgement.

- [ ] Add tests for strict shared schema validation, backend config selection, default MuJoCo compatibility, command argv/message serialization, timeout, unavailable transport, malformed reply, negative acknowledgement, and positive receipt.
- [ ] Run focused tests and save expected RED in `task-03-red.log`.
- [ ] Extract shared immutable pose/preset/error types without changing MuJoCo viewer read-back logic.
- [ ] Add package-owned Gazebo presets (`overview`, `top`, `side`, `gripper`, `cup`) and adapter.
- [ ] Extend CLI parsing to `camera_preset [--backend mujoco|gazebo] PRESET`; emit stable JSON or `failure_code=...`.
- [ ] Run camera tests plus existing MuJoCo characterization tests and policy hash; save `task-03-green.log`.
- [ ] Commit: `feat: add Gazebo camera presets`.

### Task 4: Define a backend-neutral transactional reset application

**Files:**

- Create: `src/so101_demo_py/src/ports/reset.py`
- Create: `src/so101_demo_py/src/application/transactional_reset.py`
- Create: `src/so101_demo_py/test/contracts/test_reset_ports.py`
- Create: `src/so101_demo_py/test/test_transactional_reset.py`

**Contract:** The coordinator owns thirteen ordered phases: initial observation; arm cancel/wait; gripper cancel/wait; physical detach/verify; MoveIt detach/verify; cup park/verify; parked scene sync/read-back; gripper open/verify; exact named-state arm plan; execute the returned plan; joint position/velocity verify; cup restore/verify; final independent Gazebo/MoveIt/controller/joint/TF verification. The installed SRDF name `home` is the exact MoveIt state representing Home.

- [ ] Define fake ports and parameterized tests proving exact order, exact-plan identity propagation, evidence accumulation, first-failure stop at every phase, stable `RESET_*` codes, no partial-success receipt, and future real-arm fail-closed behavior.
- [ ] Run focused tests and save expected RED in `task-04-red.log`.
- [ ] Implement immutable requests/observations/phase receipts, a `ResetPhase` enum, first-failure result, and transaction coordinator with injected ports and clock.
- [ ] Ensure simulator teleport is absent from application/port types; ports express `park_task_object`/`restore_task_object`, not `set_pose`.
- [ ] Run focused tests and policy hash; save `task-04-green.log`.
- [ ] Commit: `feat: define transactional reset application`.

### Task 5: Implement Gazebo reset adapters and shared CLI dispatch

**Files:**

- Modify: `src/so101_demo_py/src/backends/gazebo/reset.py`
- Create: `src/so101_demo_py/src/backends/gazebo/commands.py`
- Create: `src/so101_demo_py/src/control/trajectory/reset_control.py`
- Create: `src/so101_demo_py/config/gazebo/reset.yaml`
- Modify: `src/so101_demo_py/src/cli/teleop_reset.py`
- Modify: `src/so101_demo_py/package.xml`
- Create: `src/so101_demo_py/test/test_gazebo_reset_adapter.py`
- Create: `src/so101_demo_py/test/test_teleop_reset_cli.py`

**Contract:** The Gazebo adapter observes `/so101/gazebo_pose_info`, detachable-joint state, MoveIt, controller manager, joint states/velocities, and TF. It cancels action goals and waits for terminal results, uses `/so101/detach_object` plus attachment observation, and uses `/world/so101_pick_place/set_pose` only inside the adapter. Home planning uses MoveIt and the exact returned plan; gripper and arm convergence use configured tolerances.

- [ ] Add adapter tests for exact Gazebo transport argv/payloads, positive acknowledgements, detach observation, 6D pose convergence, cancellation terminal states, exact plan-to-execute object propagation, joint/velocity convergence, and all timeout/rejection mappings.
- [ ] Add CLI tests for default MuJoCo compatibility, explicit Gazebo composition, required session ID, stable JSON, evidence path, and nonzero failure.
- [ ] Run focused tests and save expected RED in `task-05-red.log`.
- [ ] Implement task-owned transport runner with `shell=False`, bounded timeouts, atomic evidence, and no legacy C++ dependency.
- [ ] Add reset config for named state `home`, fully open joint target, tolerances, timeouts, controllers, cup parking pose, world/model names, and topics/services.
- [ ] Preserve the current MuJoCo `transactional_reset` call path when backend is omitted or `mujoco`.
- [ ] Run focused reset/MuJoCo reset tests and policy hash; save `task-05-green.log`.
- [ ] Commit: `feat: implement Gazebo transactional reset`.

### Task 6: Make Gazebo execute a normal honest workflow

**Files:**

- Modify: `src/so101_demo_py/src/backends/gazebo/execute.py`
- Modify: `src/so101_demo_py/src/application/backend_execute.py`
- Modify: `src/so101_demo_py/test/test_gazebo_execute_result.py`
- Create: `src/so101_demo_py/test/test_gazebo_execute_workflow.py`

**Contract:** Execute all configured policy phases through the shared planning, execution, gripper, scene, and observation clients. Success is `SUCCEEDED/NOT_QUALIFIED`. Actual valid phase failure is `FAILED/NOT_QUALIFIED`; evidence infrastructure failure alone is `INVALID`. No synthetic incomplete result and no `SKIPPED` state.

- [ ] Add a fake-client state-machine test for the entire phase order and a parameterized first-failure test for every phase.
- [ ] Add regression tests that a successful `MOVE_ABOVE_OBJECT` advances rather than forcing `GAZEBO_EXECUTE_INCOMPLETE`.
- [ ] Run focused tests and save expected RED in `task-06-red.log`.
- [ ] Extract testable workflow orchestration from ROS composition, use current immutable Gazebo policy waypoints, write per-phase evidence, and classify only the real boundary.
- [ ] Run focused plus result-classification tests and policy hash; save `task-06-green.log`.
- [ ] Commit: `feat: complete Gazebo Python workflow execution`.

### Task 7: Event-gate Gazebo launch on readiness and scene success

**Files:**

- Modify: `src/so101_demo_py/src/runtime/launch_composition.py`
- Create: `src/so101_demo_py/src/cli/gazebo_ready.py`
- Modify: `src/so101_demo_py/setup.py`
- Modify: `src/so101_demo_py/test/test_launch_composition.py`
- Create: `src/so101_demo_py/test/test_gazebo_ready.py`

**Contract:** Spawn and controller timing may bootstrap Gazebo, but workflow readiness is explicit. A bounded readiness node verifies all required controllers active and MoveIt services/actions ready. Its zero exit starts `scene_setup --backend gazebo`; scene zero exit starts `gazebo_execute`. A nonzero exit shuts down with the first phase and never emits a later phase.

- [ ] Add launch-entity tests proving readiness -> scene -> workflow `OnProcessExit` gates, explicit backend argument, failure shutdown reason, and absence of the old 12-second workflow `TimerAction`.
- [ ] Add readiness tests for complete services/controllers and each missing dependency.
- [ ] Run focused tests and save expected RED in `task-07-red.log`.
- [ ] Implement the bounded readiness executable and event handlers using `_advance_on_success` with stable phase labels.
- [ ] Run launch/readiness tests and policy hash; save `task-07-green.log`.
- [ ] Commit: `feat: gate Gazebo workflow on scene readiness`.

### Task 8: Enable the canonical capabilities in Teleop and documentation

**Files:**

- Modify: `src/so101_teleop/config/backends/gazebo_py.yaml`
- Modify: `src/so101_teleop/test/backends/test_profiles.py`
- Modify: `src/so101_teleop/test/backends/test_cli_adapter.py`
- Modify: `src/so101_teleop/test/teleop/test_backend_capabilities.py`
- Modify: `src/so101_teleop/test/teleop/test_main_backend.py`
- Modify: `src/so101_demo_py/README.md`
- Modify: `docs/pick-place-python-architecture.md`
- Modify: `docs/guides/so101-mujoco-ros2-integration-guide.md`
- Modify: `src/so101_demo_py/docs/provenance.json`
- Modify: installed-provenance expectations under `src/so101_demo_py/test/`

**Contract:** `gazebo_py` advertises scene/reset/camera true; all operation owners are `so101_demo_py`; fixed args select `--backend gazebo`; scene style is positional; configured presets equal package-owned YAML. MuJoCo profile and invocation remain compatible. Source and installed docs no longer claim these Gazebo operations are unavailable.

- [ ] Update Teleop tests first for the complete operation set, capabilities, fixed args, argv ordering, camera allowlist, reset request execution, and scene request execution.
- [ ] Run affected tests and save expected RED in `task-08-red.log`.
- [ ] Apply the minimal profile and documentation/provenance updates.
- [ ] Run affected Teleop and documentation/provenance tests; save `task-08-green.log`.
- [ ] Commit: `feat: expose Gazebo Python capabilities in Teleop`.

### Task 9: Run static, package, fresh-build, and installed-provenance gates

**Files:** No source change unless a scoped defect is demonstrated by a gate and fixed through a new RED/GREEN cycle.

- [ ] Record `git status`, current commit, submodule gitlink, main/origin refs, and policy hashes.
- [ ] Run `python3 -m pytest --collect-only -q src/so101_demo_py/test` and require a positive count.
- [ ] Run the complete `src/so101_demo_py/test` suite from the correct sourced environment with `ROS_LOG_DIR` under the evidence root.
- [ ] Run the affected Teleop files from Tasks 8 and any additional tests selected by dependency impact; record collection count. Do not treat the unrelated baseline full-suite hang as feature evidence.
- [ ] Run the repository's existing scoped Ruff command on `src/so101_demo_py/src`, `src/so101_demo_py/test`, and only touched Teleop Python files; do not auto-reformat.
- [ ] Run `git diff --check`, package identity/asset/fusion scripts, exact policy hashes, and forbidden legacy runtime-reference scan.
- [ ] Build `so101_teleop`, `so101_mujoco_support`, and `so101_demo_py` into a new evidence-root-local build/install/log set using `--symlink-install` only if the existing package contract allows it.
- [ ] Source `/opt/ros/jazzy`, the required pinned MuJoCo overlay, and only the new project overlay. Verify `ros2 pkg prefix so101_demo_py`, `ros2 pkg executables so101_demo_py`, every installed YAML/SDF, and bundle provenance resolve to the new install prefix/source commit.
- [ ] Commit any provenance update only after installed verification: `docs: record Gazebo Python capability provenance`.

### Task 10: Live-validate Gazebo scene, camera, and disturbed reset

**Files:**

- Update before/during/after each run: `docs/experiments/so101-gazebo-python-capabilities-experiment-ledger.md`
- Add reviewed evidence/provenance summaries under `docs/provenance/` only after raw evidence is terminal.

- [ ] Create one PLANNED scene experiment with fresh domain/partition/session and explicit `1/1/13`, membership, attachment, pose, and provenance acceptance fields.
- [ ] Move it to RUNNING, launch only task-owned processes, then mark VALID/INVALID after reviewing apply and independent `/get_planning_scene` read-back.
- [ ] Create PLANNED camera experiment; capture a fresh pre-action GUI snapshot, move to RUNNING, invoke a Gazebo preset, capture a fresh post-action snapshot, inspect both actual images, and record ack plus absolute paths before terminal state.
- [ ] Create PLANNED reset experiment; first disturb the arm and cup, independently record the disturbed state, run full reset, then independently verify Gazebo 6D pose/attachment, MoveIt world membership/attachment/6D pose/`1/1/13`, controller state, joints/velocities, TF, and visual convergence.
- [ ] If a valid product failure occurs, diagnose with `superpowers:systematic-debugging`, add a focused RED test, patch, rebuild freshly, and begin a new experiment ID. If evidence is invalid, stop that batch and repair evidence validity before another batch.
- [ ] Stop only recorded task PIDs after each live run; re-audit preserved tmux sessions and unrelated processes.

### Task 11: Final-commit five consecutive FULL_RESTART qualification

**Contract:** One final source commit, one installed bundle, the frozen MuJoCo policy, and one fixed geometry manifest across all five experiments. Old successes do not count.

- [ ] Commit all source/tests/docs/ledger/provenance needed before starting the sequence.
- [ ] Verify clean worktree, exact commit, exact policy hash, geometry-manifest hash, fresh installed prefix/bundle, and no task runtime before attempt 1.
- [ ] Predeclare five independent PLANNED experiment IDs and acceptance contract, but transition only the next attempt to RUNNING.
- [ ] For each attempt perform a true FULL_RESTART, preserve independent provenance/evidence, review qualification artifacts, and mark terminal before starting the next.
- [ ] Stop the sequence immediately on a VALID failed outcome. Stop the batch immediately on INVALID evidence. Any source/config/policy/contract change invalidates the sequence and restarts at attempt 1 after rebuild.
- [ ] Require five consecutive VALID `SUCCEEDED/QUALIFIED` outcomes on the same commit and record all five experiment IDs and evidence paths.

### Task 12: Verify completion and finish the branch safely

- [ ] Invoke `superpowers:verification-before-completion`; rerun the final scoped tests/static/build/provenance/policy checks from fresh state and inspect outputs before any success claim.
- [ ] Invoke `superpowers:finishing-a-development-branch`; use its no-push/no-merge handoff path because integration was explicitly forbidden.
- [ ] Verify target worktree clean; verify main HEAD/status, other worktrees, tmux sessions, and unrelated processes are unchanged/preserved.
- [ ] Mark the `/goal` complete only after every required artifact and live gate is satisfied.
- [ ] Final report: all commits, test collection/pass counts, exact policy hash, Gazebo scene/camera/reset evidence by layer, five FULL_RESTART experiment IDs, absolute screenshot paths, preserved state, and remaining risks.
