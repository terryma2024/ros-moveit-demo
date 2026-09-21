# SO-101 macOS service campaign closure implementation ledger

Single writer for this task. Dispatch `2208b154-6e9f-4ae1-a448-1fa0101df9b1`. This ledger records
facts for audit; it does not itself authorize measurement, promotion, publication, process
termination, or evidence deletion.

```yaml
task_id: so101-macos-service-campaign-closure
goal: close service-driven macOS W2, W1 and single-point retry with qualified N1/N2 budgets
success_contract: design section 14, with candidate and production evidence kept separate
executor: DeepSeek Harness TUI (dst) inline on mac-mini, per plan and dispatch executor rules
worktree: /Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp
branch: codex/so101-unified-webapp
base_commit: 6d5069026fbd322076f58d0d4b9504891abeb861
current_commit: see CP-MSC-A (Task 2 + its defect repair; no submodule commit was required)
upstream: origin/codex/so101-unified-webapp (ahead 23, no push authorized)
evidence_root: /tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1
dispatch_receipt: /tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1/dispatch.receipt
dispatch_receipt_sha256: bea49ba76cf9d131529ca0b72d82bf8c9c6350d9eebc69fdefbe8ad19bc34b51
handoff_sha256: 4e672949dba8b72e18ed85ae6ef103063c1ce537b974e735defd492a2bcfede9
design: docs/superpowers/specs/2026-09-21-so101-macos-service-campaign-closure-design.md
design_sha256: 0a5f5e0d8006016fb778d186f7029247b7fe828f0e1efaea34e4e96b00480015
plan: docs/superpowers/plans/2026-09-21-so101-macos-service-campaign-closure-implementation.md
plan_sha256: 8fdce5b60eb1218726ab9eedd4fdf84da68e233e20f1f0ddadc00c4ba3f41538
execution_host: Terry-Mac-mini.local (macOS, arm64, user matianyi)
run_root: /tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1
test_python: /Users/matianyi/ros2_jazzy/.venv/bin/python (Python 3.11.15, pytest 8.4.2, pydantic 2.13.4)
test_python_declared_by_plan: python3 (resolves to /opt/homebrew/bin/python3, Python 3.14.6, no pytest/pydantic; see D-1)
ros_workspace: /Users/matianyi/ros2_jazzy (macOS source build; no /opt/ros/jazzy on this host)
gate_recorder: src/so101_teleop/test/e2e/record_gate.py
gate_policy: <RUN_ROOT>/operator/gate-policy.json
gate_policy_sha256: 374439d0bbf02f74a428cfa444ab4e78c965e06063dd3ef32e5ee0c759f1b9fa
gate_env: <RUN_ROOT>/operator/gate-env.sh
gate_env_sha256: 55cc16fc22210fd144f600b1ab3c2b1365ecfb3e4ba01438b4d48085894d28d9
confirmed_conclusions:
  - Minimal controller-manager path reaches CONTROLLER_MANAGER_SERVICES_READY and answers a direct list_controllers call (EXP-MSC-001E)
  - Task-owned MuJoCo RobotSystem path loads the plugin, services the main-thread UI task and publishes a callable controller-manager service about 5.1 s after hardware init (EXP-MSC-002B)
  - The full macOS task station reaches READY with the task-owned closure: 3 controllers active, 3 MoveIt services, 3 actions (EXP-MSC-003B)
  - An incomplete dynamic-library closure reproduces the campaign symptom exactly (EXP-MSC-002)
disproven_routes:
  - Controller service registration requires the aggregate MoveIt graph first (EXP-MSC-001E)
  - The shipped macOS UI dispatcher deadlocks controller construction (EXP-MSC-002B, EXP-MSC-003B)
open_hypotheses:
  - Product C++ root cause for the campaign's STATION_NOT_READY stays UNCONFIRMED; the working hypothesis is an overlay/dylib-closure defect in the environment that campaign used
latest_checkpoint: CP-MSC-A
next_experiment: NONE (Gate A stopped for Sol/High review)
```

## CP-MSC-000: registration, frozen base and baseline (Task 0 Steps 1-3)

### Required first actions

- Receipt written first, exactly `2208b154-6e9f-4ae1-a448-1fa0101df9b1` + newline, file and
  containing directory fsynced, before any other task action (file mode 0644, 37 bytes,
  sha256 `bea49ba7...`).
- Read: `AGENTS.md`, `.agents/skills/so101-dev/SKILL.md` with references
  (`ai-station-access.md`, `so101-system-map.md`, `debug-evidence.md`, `test-and-acceptance.md`,
  `experiment-ledger.md`), the design and plan above, and both predecessor document pairs:
  `2026-09-18-so101-parallel-unbounded-queue-resource-budget` design
  (`5e085f98e9926591fbefd3d6e16c16b33bfc9956df9221c46f383b310553657b`) / plan
  (`cd1b606fd8a40d7bb6e576f6f59a6ef5abcb45a8bee7e2a669c7b7a40bcfc8789`), and
  `2026-09-19-so101-macos-mps-private-ipc` design
  (`480da6dcdfea1da988f9f4e706c8340dbb6d7283200c27bb723859119145db1b`) / plan
  (`d018aae3bae372abd9a58a6e0ec7d7fef1f09dbef67860680690614bc31bb875`).

### Checkout ownership read-back (fail-closed checks passed)

- `hostname` = `Terry-Mac-mini.local`; `pwd` = the target worktree above. This dispatch runs
  directly on mac-mini; no SSH to mac-mini or ai-station was issued.
- Branch `codex/so101-unified-webapp`; HEAD `90385e3fb4aa748788c5d8a4b4551ee307db4987` — exactly
  the required starting HEAD. Upstream `origin/codex/so101-unified-webapp`, ahead 23.
- `git status --short` empty; `git diff --submodule=log` empty; submodule
  `third_party/mujoco_ros2_control` at `e4c0241aee52a40727681bd5872c09bf814e941a`, clean.
- Raw read-backs: `<RUN_ROOT>/baseline/git-baseline.txt`,
  `<RUN_ROOT>/baseline/process-inventory.txt`, `<RUN_ROOT>/baseline/evidence-root-identity.txt`.

### Writer and process ownership

- The only processes referencing this worktree are this dispatch's own TUI chain
  (pid 64248 dst -> 64249 dsh-tui -> 64251 dsh, tmux session `dst-so101-macos-closure`, created
  2026-09-21 10:24:48). No second writer overlaps the worktree.
- Preserved, not touched: tmux `dst` (pid 44357 shell), tmux `dst-so101-macos-mps-w2` (pane pid
  10776, TUI of dispatch 6954bbb9 in a different worktree, state `blocked`), tmux
  `so101-teleop-w2-e2e` with long-running pid 62670
  (`so101_teleop.expert_validation.main`, started ~24 h earlier, belongs to another task),
  and legacy TF publishers pid 1541/1542 (`static_transform_publisher`, ~1 day 10 h old).
- No TCP listener exists on this host (empty `lsof -nP -iTCP -sTCP:LISTEN`), so no duplicate
  service or port conflict was started or observed.

### Frozen run environment (adopted dispatch root, not a second root)

The handoff makes the dispatch directory the task's single ordinary evidence root, so Task 0 Step 2
adopted it instead of running `mktemp -d`; no second root was created. Within it:

| item | frozen value |
| --- | --- |
| `RUN_ROOT` | `/tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1` (mode 0700, uid 501) |
| `TEST_PYTHON` | `/Users/matianyi/ros2_jazzy/.venv/bin/python` |
| `ROS_HOME` | `<RUN_ROOT>/ros_home` |
| `ROS_LOG_DIR` | `<RUN_ROOT>/ros_log` |
| `TMPDIR`/`TMP`/`TEMP` | `<RUN_ROOT>/tmp` (per gate invocation: `<RUN_ROOT>/gates/<uuid>/tmp`) |
| gate policy | `<RUN_ROOT>/operator/gate-policy.json`, sha256 `374439d0...` |

Proof of the frozen interpreter/tempfile pair (both assertions exit 0, recorded in
`<RUN_ROOT>/baseline/task0-step2.txt`):
`sys.executable=/Users/matianyi/ros2_jazzy/.venv/bin/python`,
`tempfile.gettempdir()=/private/tmp/so101-debug-macos-service-campaign-closure-2208b154-.../tmp`.

### Deviations (reported, not silent substitutions)

- **D-1 test interpreter.** The plan's literal `TEST_PYTHON="$(command -v python3)"` resolves on
  this host to `/opt/homebrew/bin/python3` (Python 3.14.6), which cannot import `pytest` or
  `pydantic` and therefore cannot run any gate; treating its failures as RED/GREEN would be
  invalid. The repository's own macOS test contract
  (`.agents/skills/so101-dev/references/test-and-acceptance.md`) and the predecessor dispatch on
  this exact worktree and branch both register `/Users/matianyi/ros2_jazzy/.venv/bin/python`
  (3.11.15, pytest 8.4.2, pydantic 2.13.4, `rclpy` importable after sourcing
  `~/ros2_jazzy/install/setup.bash`). That verified interpreter is frozen as `TEST_PYTHON`; the
  literal value and its failed capability probe are recorded in
  `<RUN_ROOT>/baseline/task0-step2.txt`.
- **D-2 `/data` durable root.** `/data/work/so101-evidence` does not exist on this host and
  `AGENTS.md` exempts macOS from the ai-station NVMe rule. Per plan Global Constraints this only
  blocks Stage C's high-rate sampling: before the first durable high-frequency sample the plan
  requires the durable root to be created and registered, and if it is unavailable the run must
  stop and ask for a storage decision. That decision is not required for Tasks 0-3.
- **D-3 plan literal root command.** Task 0 Step 2's `mktemp -d` invocation was superseded by the
  dispatch handoff's "adopt the already-created root, do not create a second task root" rule.
  Every other literal element of the step (directory layout, exports, interpreter/tempfile
  assertion, read-back into the ledger) was executed.

### Baseline collection (Task 0 Step 3, read-only)

- Module origins (`gates/a46b2848efa24fb8bf1d33504e1a6ccc`):
  `rclpy` from `/Users/matianyi/ros2_jazzy/install/rclpy/lib/python3.11/site-packages/rclpy/__init__.py`,
  `so101_demo` from the source shim `<RUN_ROOT>/pyshim/so101_demo/__init__.py` (the package maps
  `so101_demo -> src/` only at install time), `so101_teleop` from this worktree's source tree,
  `sys.executable=/Users/matianyi/ros2_jazzy/.venv/bin/python`.
- Frozen config bytes: `parallel_batch_v4_macos_mps_w2.yaml`
  `2f9d7a87fe57a0440cdfd139c2ac42b7af86002edfcc2ed2ef3077568dc6b06b`,
  `parallel_batch_v3.yaml` `991b5c1b4fbd0cc1f0a97bd20a5b5a4e02028634f3f4ef288ad87554b383ab70`,
  `rgbd_task_points.yaml` `75591214ba3d1dfdd2827c390c0f2ec1d61e7a8dca80d89daabb1e7840627e73`.
- Retired measurement entry still fails closed: `-m so101_demo.cli.measure_parallel_resources`
  exits 2 with `MEASUREMENT_ENTRY_RETIRED` / `authorizes_execution=false`, both bare and with
  `--authorization /nonexistent --intent QUALIFICATION`
  (`gates/4874802dd6ae449f9e2e0421ad25bf32`, `gates/762c6f5691b84947b0882d7026a79d0a`).
- Package collection counts: `src/so101_demo_py/test` collects 3517 tests with 2 pre-existing
  collection errors (`test_mujoco_reset_client.py`, `test_teleop_owner.py`: `FreeJointState`
  missing from the installed `mujoco_ros2_control_msgs` fork overlay — an underlay gap on this
  host, unrelated to this dispatch), exit 2; `src/so101_teleop/test` collects 744 tests, exit 0.
  Summary: `<RUN_ROOT>/baseline/collection-baseline.txt`.
- Targeted baseline for the files Tasks 1-2 touch: `test_task_stack.py` +
  `test_motion_stack_ready.py` = 8 passed
  (`gates/da96626319de4fa388fe604ce519a2d2`).
- RED-target absence confirmed: `so101_demo.runtime.runtime_closure` and
  `so101_demo.cli.diagnose_macos_station` do not exist yet
  (`<RUN_ROOT>/baseline/probe_task1_task2_targets.py`).

### Evidence accounting at CP-MSC-000

- Retained: dispatch receipt/handoff/pane captures, `baseline/`, `operator/`, all `gates/<uuid>/`
  records, `pytest-*/junit.xml` invocation directories.
- Archived: none. Deletion candidates: none proposed at this checkpoint (the two `/tmp` trees of
  other dispatches are not this task's evidence and are left untouched).

## CP-MSC-002: Tasks 1-2 (runtime closure and independent controller evidence)

### Task 1 - runtime closure, run binding, attestation  (commit `fea8f57c`)

Delivered `src/so101_demo_py/src/runtime/runtime_closure.py` plus the `PersistentTaskStack`
wiring (closure verified before the first spawn, attestation only after PID/birth identity and
loaded-image read-back) and `src/so101_demo_py/test/test_runtime_closure.py`.

RED: `gates/bcc93e0c8bc14af8b56392935596ec1a` + `task1-red-pre-edit.xml` - 21 tests, 21
failures, 0 errors, every failure `AssertionError: so101_demo.runtime.runtime_closure is not
implemented yet` (collection succeeded, so this is an assertion RED and not a bootstrap
failure). The test file was then changed three times for self-consistency, each change making
an assertion stricter or better targeted (forbidden root = the canonical checkout itself; the
station environment used to build the closure is the merged launch environment; the stack tests
pass `ROS_DOMAIN_ID`). A second RED run (`task1-red.xml`) recorded 4 failures / 17 passes with
the module present but `task_stack` not yet wired - exactly the stack-integration assertions -
so the remaining RED is still genuine.

GREEN: `gates/8d665e8e4b0649f582fb46d1f7f275a6` - 23 passed, exit 0
(`test_runtime_closure.py` + the unmodified `test_task_stack.py`).
Adjacent: `pyrgate test_parallel_worker_runtime.py + closure + task_stack` =
`gates/7e049300ef91458f864d2704d96c2a90`, 81 passed, exit 0. A first attempt without the ROS
overlay produced 37 failures whose only cause was `RuntimeError: ros2 executable is not
available`; that is an environment artifact, not a regression, and the ROS-sourced run is the
recorded result.

Covered by the tests: stable closure hash across fresh domain/session/evidence roots; volatile
environment keys excluded; distinct run/attestation hashes; relative, classified inventories;
unclassified installed bytes changing the install inventory; config drift; source/submodule
commit drift; missing submodule commit; environment drift; canonical checkout prefix
contamination; symlinked prefix and symlinked file; replacement race through a single fd;
loaded image outside the copied install; loaded-image byte drift; ROS-domain mismatch; empty
process identities; verify-before-spawn; attest-only-after-read-back with child reaping;
closure/run-binding pairing in the stack config.

### Task 2 - direct controller query separated from MoveIt readiness  (commit `e264d1eb`)

Delivered `src/so101_demo_py/src/cli/diagnose_macos_station.py` (closed
`MINIMAL_CONTROLLER_MANAGER` / `ROBOT_SYSTEM_CONTROLLER_MANAGER` modes, six design phases with
independent deadlines, distinct failure codes, direct observation without the MoveIt graph,
JSON report) and changed `motion_stack_ready` so controller traffic no longer waits behind the
MoveIt service/action graph while final READY still requires all three active controllers plus
the three MoveIt services and actions. `setup.py` registers the
`so101_diagnose_macos_station` console script.

RED: `gates/adfb42b8bf9046ad9b3dea54e55e7452` - 13 failed / 5 passed, exit 1; the 13 are the
new diagnostic contract plus the three new `motion_stack_ready` assertions, the 5 passes are the
untouched pre-existing readiness tests.
GREEN: `gates/25fecc1763b446e4ac907f046a45365a` - 18 passed, exit 0.
Adjacent: `gates/8ce6ec5d63e34f02bf003c80c017ad1f` - install contract + copied entrypoint +
readiness + diagnostic = 36 passed, 8 skipped, exit 0.

### Provenance found while scouting Gate A (read-only)

- `ros2 pkg prefix mujoco_ros2_control` resolves to
  `/Users/matianyi/ros2_jazzy/ws_mujoco_ros2_control_fork/install`, a foreign workspace whose
  source tree has uncommitted modifications (`M CMakeLists.txt`,
  `mujoco_system_interface.{hpp,cpp}`, `mujoco_ros2_control_node.cpp`, tests...). That prefix
  is NOT this task's provenance and must not be used as a result carrier.
- `ros2 pkg prefix so101_demo_py` resolves to
  `/Users/matianyi/ros2_jazzy/so101_isolated_ws/install/so101_demo_py` - another branch's
  install, also not this task's provenance.
- The worktree submodule `third_party/mujoco_ros2_control` (commit
  `e4c0241aee52a40727681bd5872c09bf814e941a`) contains `mujoco_ros2_control_msgs`,
  `mujoco_ros2_control_plugins` (including
  `mujoco_ros2_control_plugin_capabilities.hpp`), `mujoco_ros2_control` and test sources, so a
  task-owned overlay for the A/B has to be built from it rather than borrowed from the fork.

### Planned experiments (frozen before any stack starts)

```yaml
experiment_id: EXP-MSC-001
status: PLANNED
prior_experiment: NONE
hypothesis: The controller manager registers /controller_manager/list_controllers and answers a direct query even when no RobotSystem is loaded, so a station that never reaches readiness is not failing at service registration itself.
prediction: With MINIMAL_CONTROLLER_MANAGER the direct client observes service_visible=true and call_completed=true with an empty controller list, and no C++ or config change is needed for that path.
single_variable: NONE (first observation of the minimal path)
lifecycle: ISOLATED_STACK
preconditions:
  - no other station, controller manager or ROS graph owned by this task is running
  - fresh ROS_DOMAIN_ID, fresh session id, task-owned child process
success_criteria:
  - report shows service_visible and call_completed with ros_domain_id equal to the fresh domain
failure_criteria:
  - service_visible never becomes true within the bounded timeout
invalid_criteria:
  - another writer's controller manager or a stale ROS daemon answers instead
provenance:
  source_commit: e264d1eb (Task 2 HEAD)
  install_overlay: ros2_jazzy/install (ROS) + ws_mujoco_ros2_control_fork/install is NOT used
  runtime_executable: controller_manager/ros2_control_node from the ROS underlay
  ros_domain_id: 231
  gz_partition: so101_msc_ga_minimal
commands:
  - command: PENDING
    exit_code: PENDING
observed: []
inferred: []
conclusion: PENDING
evidence: []
decision: PENDING
next_experiment: EXP-MSC-002

experiment_id: EXP-MSC-002
status: PLANNED
prior_experiment: EXP-MSC-001
hypothesis: Changing only the controller-manager launch to the MuJoCo RobotSystem path moves the last observed structured phase, which locates the first bad boundary between service registration and hardware bring-up.
prediction: The robot-system run reaches a different (earlier) structured phase or stalls before CONTROLLER_MANAGER_SERVICES_READY, and the difference from EXP-MSC-001 is attributable to the RobotSystem path alone.
single_variable: controller-manager mode (MINIMAL -> ROBOT_SYSTEM)
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-MSC-001 completed with a valid observation
  - task-owned build of third_party/mujoco_ros2_control if the foreign fork prefix may not be used
success_criteria:
  - a structured phase/failure-code pair that differs from EXP-MSC-001
failure_criteria:
  - both runs observe exactly the same phase and code (boundary NOT distinguished)
invalid_criteria:
  - the run depends on the foreign fork install or its modified working tree
provenance:
  source_commit: e264d1eb plus the frozen submodule commit e4c0241a
  install_overlay: PENDING (task-owned submodule build under the registered root)
  runtime_executable: PENDING
  ros_domain_id: 232
  gz_partition: so101_msc_ga_robotsystem
commands:
  - command: PENDING
    exit_code: PENDING
observed: []
inferred: []
conclusion: PENDING
evidence: []
decision: PENDING
next_experiment: NONE
```

## CP-MSC-003: Gate A execution log (controller-manager A/B)

All runs below are task-owned: the child processes were started by this dispatch's runners,
recorded through the registered gate, and stopped by the same runner. No foreign process was
signalled and no shared service was started or stopped.

| run | command (recorded gate) | exit | key observation |
| --- | --- | --- | --- |
| EXP-MSC-001 | `gates/d0577436bda742f5b0acd248732ef220` | 1 | MINIMAL without any robot description: controller_manager logs `Subscribing to '/robot_description' topic` and then `Waiting for data ... to finish initialization` for the whole 25 s; `/controller_manager/list_controllers` never becomes callable |
| EXP-MSC-001B | `gates/446da084ff72414ea1d456915004ff8d` | 3 | same, with `-p robot_description:=<stub>`: the parameter is ignored and the node still waits on the topic |
| EXP-MSC-001C | `gates/6cdc68aa59a849599c89db2466006b5b` | 3 | a task-owned latched `/robot_description` publisher delivers the stub; controller_manager logs `no 'ros2_control' tag found in the URDF` and never registers services |
| EXP-MSC-001D | `gates/7fe70aa9332a4ee6afb1370fd0f7b5e3` | 1 | **INVALID**: `ROS_DOMAIN_ID=233` exceeds the RMW port range (`Calculated port number is too high. Probably the domainId is over 232`). Not counted; re-run as 001E on domain 230 |
| EXP-MSC-001E | `gates/ad8facff3e9c481f950537c3e224e98b` | 0 | MINIMAL with the station's own joint/interface set and `mock_components/GenericSystem` as the only difference: `Loaded hardware 'RobotSystem' ... Initialize ... Activating ... Resource Manager has been successfully initialized. Starting Controller Manager services...`; direct call completes, phase `CONTROLLER_MANAGER_SERVICES_READY`, controllers `{}` |
| EXP-MSC-002 | `gates/8746ac496a6440ff9845facafb03ba6a` | 0 | first robot-system attempt from the task-owned overlay: the plugin could not be dlopen'ed (`Library not loaded: @rpath/libmujoco.3.4.0.dylib`), so controller_manager kept waiting and never registered services - the *same* downstream symptom as the campaign, caused by an incomplete dynamic-library closure of the build, not by controller construction |
| EXP-MSC-002B | `gates/07182fcc2b3046bdad8efd5eb309d67a` | 0 | same command with `DYLD_LIBRARY_PATH` including the MuJoCo vendor lib dir: `Loaded hardware 'RobotSystem' from plugin 'mujoco_ros2_control/MujocoSystemInterface'`, `Submitting MuJoCo UI task to the process main thread`, `Running MuJoCo UI task on the process main thread`, then ~5.1 s later `Resource Manager has been successfully initialized. Starting Controller Manager services...`; direct call completes, phase `CONTROLLER_MANAGER_SERVICES_READY`, controllers `{}` (no spawner was run in this diagnostic) |

### Provenance of the Gate A runs

- `EXP-MSC-001*`: `controller_manager` from `/Users/matianyi/ros2_jazzy/extra_ws/install`
  (host underlay), no project install involved.
- `EXP-MSC-002*`: `ros2 pkg prefix mujoco_ros2_control` =
  `<RUN_ROOT>/gate-a/ga-install2/mujoco_ros2_control`, i.e. a **task-owned colcon build of the
  worktree submodule** `third_party/mujoco_ros2_control` at `e4c0241a`, built into
  `<RUN_ROOT>/gate-a/ga-build2` / `ga-install2` by `gate-a/build_submodule.sh`
  (`COLCON_BUILD_RC=0`, 4 packages: msgs 17.7 s, mujoco_3d_lidar 3.7 s, plugins 15.3 s,
  mujoco_ros2_control 26.5 s). The foreign fork install
  `/Users/matianyi/ros2_jazzy/ws_mujoco_ros2_control_fork/install` was **not** used.
- Fresh `ROS_DOMAIN_ID` per run (231 / 231 / 231 / invalid 233 / 230 / 229 / 228) and a
  task-local `ROS_HOME`/`ROS_LOG_DIR`/`TMPDIR` per experiment.
- The robot description in EXP-MSC-001E and EXP-MSC-002B is rendered by the station's own
  renderer from `assets/mujoco/so101.urdf`; 001E differs from 002B in the hardware plugin
  block only, and the runner prints
  `same_bytes_except_hardware=True` for that comparison.

### Experiment states after Gate A

- `EXP-MSC-001` -> **VALID** (observation of the deliberate wait; batch continues as 001B/001C).
- `EXP-MSC-001D` -> **INVALID** (invalid ROS domain; not counted).
- `EXP-MSC-001E` -> **VALID** (minimal boundary reached).
- `EXP-MSC-002` -> **VALID** but diagnosed as an incomplete dylib closure of the build
  (`@rpath/libmujoco.3.4.0.dylib`), not a controller/hardware startup defect; superseded by 002B.
- `EXP-MSC-002B` -> **VALID** (robot-system boundary reached in ~5.1 s with the task-owned
  overlay).

### Conclusion at this point (Gate A)

`OBSERVED`: with the task-owned overlay built from the worktree submodule, the macOS
`RobotSystem` path loads the MuJoCo plugin, services the main-thread UI task through the
existing dispatcher, and controller_manager publishes a callable
`/controller_manager/list_controllers` about 5.1 s after `Initialize hardware`. The failure
described in the design ("`ros2_control_node` stops while loading `RobotSystem`, the service
never appears stably") **did not reproduce** in this closure.

`OBSERVED`: the same downstream symptom (no callable service, spawners therefore unable to
activate controllers) is produced by an incomplete dynamic-library closure of the built plugin
(EXP-MSC-002).

`INFERRED`: the campaign's `STATION_NOT_READY` is consistent with an overlay/loader-path defect
in the environment the campaign used (a foreign, locally modified fork workspace whose prefix
the project's own `.envrc.example` deliberately excludes) rather than with a controller
constructions or macOS UI-dispatch ordering defect in the allowlisted C++ files. This is stated
as an inference, not a confirmed root cause: the campaign's own overlay was not re-run because
its provenance is foreign to this dispatch.

`UNCONFIRMED`: the plan's Gate A requires a *confirmed* first bad boundary plus a RED/GREEN
regression at that boundary. No product C++ boundary was confirmed, and per the plan
("Do not edit C++ based only on timeout length or downstream `STATION_NOT_READY`") no
speculative product edit was made. CP-MSC-A therefore cannot be declared PASS in this state.

### Task 2 defect found and repaired during Gate A (commit `82b7a7d9`)

The first live diagnostic run failed with
`TypeError: replace() argument 2 must be str, not PosixPath` in
`station_robot_description`. RED with the ROS-sourced gate:
`gates/86a6c121b5064516876369fa09cec6fe` (1 failed / 10 passed, the failure being exactly that
TypeError); the same test under the plain gate first failed with
`ModuleNotFoundError: ament_index_python` (`gates/8c108966cb5d45798cb67cbac2bf605f`), which is
a runner/overlay artifact and was **not** counted as RED. GREEN:
`gates/e7c1b6983ddc448fae555ffb9e90d53d` (19 passed, exit 0).

## CP-MSC-003B: full task station with the task-owned closure reaches READY

`gates/74d6aafae26a4413bf8d60d2a4c31d6c` (exit 0). One bounded run
(`gate-a/run_station_once.sh`), fresh `ROS_DOMAIN_ID=227`, `GZ_PARTITION=so101_msc_ga_station`:

- Prefixes read back before the launch:
  `so101_demo_py` = `<RUN_ROOT>/gate-a/station-install/so101_demo_py`,
  `mujoco_ros2_control` = `<RUN_ROOT>/gate-a/ga-install2/mujoco_ros2_control`,
  `so101_mujoco_support` = `<RUN_ROOT>/gate-a/station-install/so101_mujoco_support`.
  All three are task-owned builds of this worktree; the foreign fork prefix was not sourced.
- `ros2 launch so101_demo_py so101_mujoco_task_station.launch.py headless:=false
  sensor_rendering:=true include_teleop:=false session_id:=msc-ga-003` started, and
  `ros2 run so101_demo_py motion_stack_ready --timeout-s 100` returned exit 0 with
  `{"ready": true, "phase": "READY", "failure_code": null}` and all three controllers
  `active`, all three MoveIt services and all three actions `true`
  (`experiments/EXP-MSC-003/readiness.json`).
- Launch log (retained at `experiments/EXP-MSC-003/station-launch.log`) shows the full macOS
  path working: `mujoco_macos_ui: Waiting for a MuJoCo UI task on the process main thread` ->
  `Loaded hardware 'RobotSystem' from plugin 'mujoco_ros2_control/MujocoSystemInterface'` ->
  `Submitting MuJoCo UI task to the process main thread` ->
  `Running MuJoCo UI task on the process main thread` -> `Resource Manager has been
  successfully initialized` -> `spawner_* : Configured and activated <controller>` ->
  `Successfully switched controllers!`.
- Run 003 (`gates/ea3824fd5b644dbb940cda7785cd1f41`) is **INVALID**: `setsid` and `timeout` do
  not exist on macOS, so the readiness probe never ran (`READINESS_RC=127`). Fixed by removing
  both and using an explicit bounded wait; 003B is the recorded run.
- Cleanup: the first SIGINT to the `ros2 launch` process stopped the spawners but left the
  launch process and three children alive (`LAUNCH_TREE_STILL_ALIVE=true`). They were stopped by
  the exact PIDs this run recorded (77417, 77423, 77427, then 77422, 77420, 77421) with
  SIGTERM, SIGKILL only where SIGTERM did not settle. Final scans:
  `ps -Ao pid,ppid,etime,command | grep -E "ros2_control_node|move_group|spawner|robot_state_publisher|msc-ga-003"` -> **no task-owned ROS residue**.
  Preserved and untouched: pid 1541/1542 (long-lived foreign TF publishers) and pid 62670
  (another task's `so101_teleop.expert_validation.main`).

### What this means for Gate A

- `OBSERVED`: with a task-owned closure built from this worktree (source `82b7a7d9` plus
  submodule `e4c0241a`), the macOS task station reaches full readiness - controllers active,
  MoveIt services and actions ready - on the first bounded attempt. The failure the design
  describes did **not** reproduce.
- `OBSERVED`: an incomplete dynamic-library closure of the built MuJoCo plugin reproduces the
  exact downstream symptom (controller_manager never publishes a callable service; the
  spawners then time out), see EXP-MSC-002.
- `INFERRED`: the campaign's `STATION_NOT_READY` is consistent with an overlay / loader-path
  defect in the environment the campaign was using, not with a macOS UI-dispatch ordering or
  controller-construction defect in the allowlisted C++ files.
- `UNCONFIRMED`: no product-code first bad boundary was confirmed. Per the plan no C++
  regression was written and no product edit was made; `CP-MSC-A` cannot be declared PASS and
  `Gate B` live work stays forbidden.

## CP-MSC-A checkpoint

```yaml
checkpoint_id: CP-MSC-A
last_valid_experiment: EXP-MSC-002B (robot-system boundary) and EXP-MSC-003B (station READY)
current_hypothesis: >-
  The campaign's STATION_NOT_READY came from an incomplete overlay/dylib closure in the
  environment it used, not from a defect in the allowlisted macOS controller-startup code.
  Product C++ root cause: UNCONFIRMED.
working_tree_status: >-
  clean except this ledger (to be committed together with the checkpoint);
  commits 1f50619c (ledger baseline), fea8f57c (runtime closure), e264d1eb (controller/MoveIt
  readiness separation), 82b7a7d9 (diagnostic robot-description repair)
owned_processes: NONE (all task-owned children stopped by recorded PID; final scan empty)
preserved_processes:
  - pid 1541, 1542 static_transform_publisher (pre-existing, >1 day old, untouched)
  - pid 62670 so101_teleop.expert_validation.main (another task's service, untouched)
  - tmux sessions dst, dst-so101-macos-mps-w2, so101-teleop-w2-e2e (untouched)
confirmed_conclusions:
  - Minimal controller-manager path reaches CONTROLLER_MANAGER_SERVICES_READY and answers a
    direct list_controllers call (EXP-MSC-001E)
  - Task-owned MuJoCo RobotSystem path loads the plugin, services the main-thread UI task and
    publishes a callable controller-manager service about 5.1 s after hardware init (EXP-MSC-002B)
  - The full task station reaches READY (3 controllers active, 3 MoveIt services, 3 actions)
    with the task-owned closure (EXP-MSC-003B)
  - A missing dylib closure reproduces the campaign symptom exactly (EXP-MSC-002)
disproven_routes:
  - "controller service registration needs the MoveIt graph first" (the direct client works
    without it; EXP-MSC-001E)
  - "the shipped macOS UI dispatcher deadlocks controller construction" (it appears in the
    successful runs and completes the main-thread task; EXP-MSC-002B/003B)
open_risks:
  - The station reached readiness once, not five consecutive FULL_RESTART times; Gate A's 5/5
    requirement is unmet and Gate B live work is forbidden until the boundary question is
    resolved with Sol/High
  - The task-owned overlay needs DYLD_LIBRARY_PATH to include the MuJoCo vendor lib dir;
    whether the product's frozen install must encode that rpath (allowlisted CMakeLists.txt)
    is an open question for review
  - ros2 launch on macOS did not stop its children on SIGINT; a task-owned cleanup step with
    recorded PIDs was required
next_command: NONE - wait for GPT-5.6 Sol / High review of CP-MSC-A
```

## Evidence accounting at CP-MSC-A

- Retained (all under the single registered root): dispatch receipt/handoff, `baseline/`,
  `operator/`, every `gates/<uuid>/` record with argv/exit/elapsed/JUnit, the three experiment
  directories (`experiments/EXP-MSC-001`, `-002`, `-003`) including runner scripts, rendered
  URDF variants, launch logs and `readiness.json`, and the task-owned build trees
  `gate-a/ga-install2` and `gate-a/station-install` with their logs (`COLCON_BUILD_RC=0`).
- Archived: none.
- Deletion candidates (reported only; nothing deleted): `gate-a/ga-build`, `gate-a/ga-build2`,
  `gate-a/station-build` (regenerable build trees, ~417 MB total for the root) and the
  `pytest-XXXXXXXX` invocation directories of green runs. Deletion requires explicit user
  authorisation.
