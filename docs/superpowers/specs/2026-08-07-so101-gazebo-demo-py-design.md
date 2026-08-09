# SO-101 Gazebo Demo Python Rewrite Design

**Date:** 2026-08-07
**Status:** Approved
**Reference checkout:** `/data/work/ws_moveit/.worktrees/refactor-optimization-r3`
**Reference branch and observed HEAD:** `codex/refactor-optimization-r3` at `89acb20bc6a4889ca1ed212b736d44c4f2c2de4a`, plus the preserved uncommitted R3 changes present when this design was approved

## Objective

Create a new, self-contained ROS 2 package named `so101_gazebo_demo_py` that reproduces the externally observable core behavior of `so101_gazebo_demo` in Python. The rewrite is based on the live R3 checkout, but it does not import, link, execute, or otherwise depend on the original package's C++ components or on `pick_place_common`.

The rewrite preserves the boundaries that matter to a robot operator and to downstream ROS tools: launch entry points, CLI arguments, workflow states, configuration schema, checkpoint and resume behavior, failure semantics, MoveIt planning and execution, controller feedback, Gazebo attachment, Planning Scene convergence, reset and recovery, and visible pick-place results.

## Scope

### Included

- A standalone `ament_python` package at `src/so101_gazebo_demo_py`.
- Package-owned copies of the SO-101 URDF/Xacro, meshes, Gazebo world, SRDF, MoveIt/controller configuration, RViz configuration, task-object policy, motion policy, and validation policy required by the core demo.
- Public launch entry points for display, controller, Gazebo, MoveIt, headless move_group, pick-place, and the attachment relay needed by those launches.
- Python executables for the pick-place state machine, world reset, MoveIt scene observation/update, and Gazebo attachment-state relay.
- The R3 pick-place workflow, including physical-grasp stabilization, 2 mm micro-lift, bounded retry behavior, attachment, placement, detach, scene synchronization, checkpoint/resume, plan-only, single-step, recovery, and request-scoped planning-failure diagnostics.
- Unit, contract, characterization, package, headless runtime, and GUI acceptance tests.

### Explicit non-goals

- Web Teleop and its Vite/FastAPI assets.
- Workspace sampling and workspace artifacts.
- Motion calibration and motion-matrix validation tools.
- Video capture, frame extraction, mosaics, camera-preset helpers, GUI tiling helpers, geometry-generation utilities, and other developer-only auxiliary scripts.
- Real-hardware operation. The package is simulation-only.
- Reusable abstractions shared with Panda or the original C++ package.
- Source compatibility with C++ classes. Compatibility is defined at the external behavior boundary.

## Compatibility Contract

### Package independence

`so101_gazebo_demo_py/package.xml`, `setup.py`, launch files, modules, and installed assets must not declare or perform a runtime dependency on:

- `so101_gazebo_demo`
- `pick_place_common`
- any executable or shared library installed by either package

The package may depend on ROS 2 Jazzy, Gazebo Harmonic, MoveIt 2, `ros_gz_*`, `gz.transport13`, standard Python packages supplied by Ubuntu/ROS, and the controller/action/message packages required by the public behavior.

### Public commands

The new package exposes these commands under the new package name:

```bash
ros2 launch so101_gazebo_demo_py so101_display.launch.py
ros2 launch so101_gazebo_demo_py so101_controller.launch.py
ros2 launch so101_gazebo_demo_py so101_gazebo.launch.py
ros2 launch so101_gazebo_demo_py so101_moveit.launch.py
ros2 launch so101_gazebo_demo_py so101_move_group_headless.launch.py
ros2 launch so101_gazebo_demo_py so101_pick_place.launch.py
ros2 run so101_gazebo_demo_py pick_place_state_machine
ros2 run so101_gazebo_demo_py gazebo_attachment_state_relay
ros2 run so101_gazebo_demo_py reset_so101_world
ros2 run so101_gazebo_demo_py so101_moveit_scene
```

The pick-place executable preserves the R3 arguments and exit behavior:

- `--mode dry_run|plan_only|execute`
- `--fail-at STATE`
- `--stop-after STATE`
- `--plan-only-state STATE`
- `--resume [true|false]`
- `--step`
- `--force-continue`
- `--checkpoint PATH`
- `--session-id ID`
- `--planning-diagnostics-dir PATH`
- `--object-config PATH`
- `--motion-policy PATH`
- `--validation-policy PATH`

The launch defaults remain safe: `run_mode:=dry_run` and `start_simulation:=false`.

### Workflow compatibility

The Python workflow uses the same named states and success/failure transitions as R3:

```text
IDLE
PREPARE_OPEN_GRIPPER
MOVE_ABOVE_OBJECT
DESCEND
CLOSE_GRIPPER
WAIT_GRASP_STABLE
MICRO_LIFT
WAIT_MICRO_LIFT_STABLE
VERIFY_PHYSICAL_GRASP
VALIDATION_FAILED
ATTACH_GAZEBO
ATTACH_MOVEIT
LIFT
MOVE_ABOVE_PLACE
DESCEND_TO_PLACE
OPEN_GRIPPER
DETACH_GAZEBO
DETACH_MOVEIT
SYNC_WORLD_OBJECT
RETREAT
RECOVER_LIFT_TO_SAFE_HEIGHT
RECOVER_MOVE_ABOVE_PICK
RECOVER_DESCEND_TO_PICK
RECOVER_OPEN_GRIPPER
RECOVER_DETACH_GAZEBO
RECOVER_DETACH_MOVEIT
RECOVER_SYNC_WORLD_OBJECT
RECOVER_RETREAT
DONE
ERROR
```

`VALIDATION_FAILED` remains the only force-continue state. Plan-only is limited to the motion states supported by R3. Recovery reverses only side effects already established by evidence.

### Result and failure compatibility

The Python domain model uses string enums and frozen dataclasses for state, run mode, run status, action status, failure category, failure, action result, run request, and run result. Console output remains machine-comparable with R3: state trace, current/next state, status, failure code/message/metrics, transition count, and process exit code are stable acceptance surfaces.

Checkpoint JSON and the physical-grasp sidecar preserve the R3 field names, session binding, policy fingerprint, durable-write behavior, and fail-closed resume semantics. A pending retry side effect resumes as `PHYSICAL_GRASP_RETRY_INTERRUPTED` rather than replaying an ambiguous command.

## Architecture

### Package layout

```text
src/so101_gazebo_demo_py/
├── package.xml
├── setup.py
├── setup.cfg
├── resource/so101_gazebo_demo_py
├── launch/
├── config/
├── urdf/
├── meshes/
├── worlds/
├── rviz/
├── docs/
├── so101_gazebo_demo_py/
│   ├── domain.py
│   ├── workflow.py
│   ├── runner.py
│   ├── checkpoint.py
│   ├── policy_config.py
│   ├── profile.py
│   ├── diagnostics.py
│   ├── cli/
│   │   ├── pick_place_state_machine.py
│   │   ├── reset_so101_world.py
│   │   ├── gazebo_attachment_state_relay.py
│   │   └── so101_moveit_scene.py
│   ├── motion/
│   │   ├── planner.py
│   │   ├── executor.py
│   │   ├── gripper.py
│   │   └── evidence.py
│   ├── gazebo/
│   │   ├── transport.py
│   │   ├── attachment.py
│   │   ├── observer.py
│   │   └── reset.py
│   ├── moveit/
│   │   ├── planning.py
│   │   ├── scene.py
│   │   └── robot_state.py
│   ├── grasp/
│   │   ├── stabilizer.py
│   │   ├── validator.py
│   │   ├── retry.py
│   │   └── evidence_store.py
│   └── recovery/
│       ├── policy.py
│       └── coordinator.py
└── test/
```

Each module has one ownership boundary. Domain and workflow modules contain no ROS imports. ROS/Gazebo/MoveIt calls live behind Python protocols so the state machine and failure behavior can be tested with deterministic fakes.

### Runtime data flow

1. Launch resolves package-owned assets and starts the selected ROS/Gazebo/MoveIt stack.
2. The CLI validates arguments, loads the three YAML policies, derives a policy fingerprint, and creates a `RunRequest`.
3. The runner loads or initializes checkpoint state, validates session and world readiness, and dispatches one state at a time.
4. Motion states request plans from `/plan_kinematic_path`, validate the returned trajectory, and execute through `/execute_trajectory` or the appropriate `FollowJointTrajectory` action.
5. Feedback is proven with bounded samples from `/joint_states`, tf2, controller action results, Gazebo model pose/contact state, and Planning Scene membership.
6. Gazebo and MoveIt attachment are separate side effects with separate convergence checks.
7. After each accepted transition, the checkpoint is atomically replaced. Physical-grasp retry progress is persisted before each side effect in the separate sidecar.
8. Failure dispatches the recovery path associated with the side effects actually observed, then returns a nonzero exit code unless the requested checkpoint boundary was intentionally reached.

## ROS and MoveIt Integration

`moveit_py` and `moveit.planning` are not available in the observed ai-station ROS Jazzy environment. The rewrite therefore uses `rclpy` clients directly:

- `moveit_msgs/srv/GetMotionPlan` on `/plan_kinematic_path`
- `moveit_msgs/action/ExecuteTrajectory` on `/execute_trajectory`
- `moveit_msgs/srv/GetPositionIK` on `/compute_ik` where an IK request is required
- `moveit_msgs/srv/ApplyPlanningScene` and `GetPlanningScene` for world/attached membership
- `control_msgs/action/FollowJointTrajectory` for controller-facing arm or gripper commands where R3 uses the controller action directly
- `sensor_msgs/msg/JointState` and tf2 for observed robot state

Service and action clients have explicit availability, request, result, cancellation, and convergence timeouts. A planning success code does not imply execution success. An execution result does not imply the joints, TCP, Gazebo object, or Planning Scene converged.

## Gazebo Integration and Physics Gate

Python uses the installed `gz.transport13` binding for Gazebo command, event, model-pose, and contact traffic. The SDF continues to use Gazebo Harmonic's built-in `DetachableJoint` system. The original `libso101_attachment_collision_system.so` is removed and is never loaded by the new package.

The original C++ collision system dynamically disables task-object collisions after physical attachment. Replacing this behavior is the first implementation risk gate:

1. Build the minimal Python package and launch a package-owned world with `DetachableJoint` and no custom collision plugin.
2. Establish physical contact, attach, lift, hold, detach, and settle while recording object pose, attachment state, controller/joint/TF evidence, contact behavior, and a fresh screenshot.
3. Accept the built-in path only if it is stable and preserves the pre-attach physical-grasp gate.
4. If it fails, test a package-owned Gazebo Python System Loader module that toggles collision components. The actual ROS-sourced process must import compatible `gz.sim8`; an isolated import outside the launch environment is not sufficient.
5. The observed ai-station has a system Gazebo 8.14 Python binding and a ROS vendor Gazebo 8.11 runtime that currently produce an ABI-symbol error when `gz.sim8` is imported from the ROS-sourced shell. The plan must resolve and prove the loader/runtime provenance before using this fallback.
6. If neither pure-Python path passes, stop with evidence and request a design decision. Do not load the original C++ plugin, write a new C++ plugin, permanently disable pre-attach collisions, or simulate attachment by repeatedly teleporting the object.

The fixed moving-pad penetration ceiling of `0.000800002 m`, the approximately `0.4 mm` moving-jaw retraction represented in the R3 checkout, q6 semantics, containment checks, and physical validation assertions are not relaxed to make the Python rewrite pass.

## Physical-Grasp and Retry Contract

Before Gazebo attachment, the object must be held by physical finger contact. The gate remains:

```text
WAIT_GRASP_STABLE -> MICRO_LIFT -> WAIT_MICRO_LIFT_STABLE -> VERIFY_PHYSICAL_GRASP
```

The micro-lift is 2 mm in world Z. Retry behavior allows at most five total attempts. A retry performs pre-open, descend to the saved pre-lift world Z, reclose, stable capture, micro-lift, and verification. Contact-present failures retain the reclose q6 target. Contact-missing failures tighten only that target by 1.0 mrad per retry, capped at 4.0 mrad cumulative tightening. The 6.0 mrad seating preload remains fixed. Nonretryable failures do not retry, and exhaustion preserves the fifth physical failure while adding retry metrics.

## Assets and Provenance

Assets are copied from the approved R3 checkout into the new package so it is installable and runnable without the old package. A provenance manifest records:

- reference worktree and branch
- reference committed HEAD
- files copied
- whether each source file had an uncommitted R3 delta at copy time
- SHA-256 of the copied source and destination

Generated caches, `__pycache__`, build/install/log output, screenshots, diagnostics, checkpoints, and local editor state are not committed.

## Error Handling

- Invalid CLI or YAML fails before starting side effects and returns a nonzero exit code.
- Missing ROS services/actions/topics fail with a named failure category and bounded timeout.
- Planning, plan validation, execution, controller convergence, Gazebo attachment, MoveIt scene, TF, collision, checkpoint, and resume errors remain distinct.
- All file stores use owner-only temporary files, flush and fsync, atomic `os.replace`, and owner-only final permissions.
- Diagnostics writing is best-effort and cannot replace or mask the original workflow failure.
- Cancellation is request-scoped; the rewrite must not cancel unrelated MoveIt or controller goals.
- Reset detaches Gazebo first, restores the object pose, resets the Planning Scene, returns the arm and gripper home, and proves final convergence.

## Testing Strategy

### Unit and contract tests

- Enum/string and CLI compatibility.
- Complete workflow transition table and definition validation.
- YAML schema, numeric constraints, and policy fingerprints.
- Checkpoint and sidecar atomicity, corruption behavior, session mismatch, and pending-side-effect fail-closed behavior.
- Plan validation, request-scoped cancellation, attachment event reduction, motion evidence, physical-grasp validation, retry limits, and recovery decisions.
- Launch defaults, installed asset closure, and absence of dependencies on the old packages or binaries.

### Characterization tests

For deterministic inputs, run the R3 C++ executable and Python executable separately and compare:

- state trace
- run status and exit code
- current/next state
- failure code and metrics
- checkpoint and sidecar schema
- `dry_run`, injected failure, stop-after, single-step, resume, force-continue, and plan-only behavior

The comparison harness is test-only. The installed Python package does not invoke the C++ executable.

### Runtime acceptance ladder

1. Targeted Python tests.
2. Full `colcon test --packages-select so101_gazebo_demo_py` with no failures.
3. `dry_run` full workflow and failure/recovery paths.
4. `plan_only` for every supported motion state.
5. Headless, isolated Gazebo/MoveIt execute with a unique `ROS_DOMAIN_ID`, `GZ_PARTITION`, session ID, checkpoint path, and log directory.
6. GUI execute from the newly installed package, followed by a fresh screenshot inspected by the agent.

Final execute acceptance requires mutually consistent evidence from:

- installed-package provenance
- state-machine result and exit code
- MoveIt plan and execute result
- controller result plus `/joint_states` and TCP delta
- Gazebo attachment state and task-object 6D pose
- MoveIt world/attached collision membership
- a new visual showing the actual grasp, lift, placement, release, and final scene

No single success log, test result, topic, or screenshot proves the whole demo.

## Execution and Git Boundaries

- The implementation agent runs directly on ai-station in tmux session `codex`; it must not SSH to ai-station and must not operate `codex-cua`.
- The implementation checkout is `/data/work/ws_moveit/.worktrees/refactor-optimization-r3` on `codex/refactor-optimization-r3`.
- Before every commit, inspect the full dirty state and cached diff. Stage only the files named by the current task.
- Existing R3 modifications belong to the user and must not be reset, stashed, cleaned, overwritten, or included in Python-rewrite commits.
- Long-running GUI processes use a named tmux-held shell with `~/gui-env.zsh`; the `codex` session remains the coding-control channel.
- Runtime evidence is written under a unique `/tmp/so101-py-<timestamp>/` directory, not the source tree.
- No push or merge to a protected/default branch is authorized by this design approval.

## Completion Criteria

The rewrite is complete only when all of the following are true:

1. `so101_gazebo_demo_py` builds and installs from a ROS-only Jazzy shell without building or sourcing the original demo package as a dependency.
2. Dependency and source scans prove there is no runtime import, link, executable call, or asset lookup into `so101_gazebo_demo` or `pick_place_common`.
3. All included public launches and executables are installed and pass their contract tests.
4. Characterization tests prove compatible workflow, CLI, result, failure, checkpoint, resume, and recovery behavior.
5. Package tests pass with no new failures.
6. A fresh single-stack execute run completes pick-place using the Python executable and new package assets.
7. Gazebo physics, MoveIt Planning Scene, controller/joint/TF state, and the new screenshot independently prove the expected result.
8. The original R3 dirty files remain preserved and are not included in rewrite commits.
9. Remaining differences and risks are documented precisely; no unverified claim is reported as complete.

## 2026-08-08 Physical-outcome validation addendum

本 addendum 覆盖原设计中 normal forward workflow 使用 `DetachableJoint` 搬杯的语义。只读参考为
physical worktree `641f7c470bfea81934b0dc094afc42da4aaa5111`；Python 逐项重建外部 contract
和证据，禁止 import、link、执行或 runtime 查找 `so101_gazebo_demo`、`pick_place_common` 及其
binary/asset。

### Ownership 与状态机

从 `CLOSE_GRIPPER` 到 physical release，cup motion 只由 Gazebo contact、friction、gravity 和 robot
motion 决定。normal forward path 不调用 Gazebo attach/detach，也不保留 no-op state。MoveIt attach
仅是从 physical grasp 后最新 fresh finite Gazebo cup pose 派生的 collision-planning shadow。

```text
CLOSE_GRIPPER -> WAIT_GRASP_STABLE -> MICRO_LIFT -> WAIT_MICRO_LIFT_STABLE
-> VERIFY_PHYSICAL_GRASP -> ATTACH_MOVEIT -> LIFT -> MOVE_ABOVE_PLACE
-> DESCEND_TO_PLACE -> DETACH_MOVEIT -> OPEN_GRIPPER -> WAIT_RELEASE_SETTLE
-> VALIDATE_FINAL_PLACEMENT -> SYNC_WORLD_OBJECT -> RETREAT -> DONE
```

Python `State` 新增 `WAIT_RELEASE_SETTLE` 与 `VALIDATE_FINAL_PLACEMENT`。Reset/recovery 可防御性清理
stale Gazebo joint，但该接口不进入 forward graph。checkpoint 记录 release epoch；post-release window
首版 non-resumable，中断后必须新建 epoch，绝不复用 pre-release/旧 epoch sample。

### Policy、observer 与 evaluator

validation policy 新增 strict `physical_outcome`：intended table collision、live-calibrated
`minimum_support_contact_depth_m`、final XY region、support height、upright tilt、derived linear/angular
speed、consecutive samples/minimum duration、freshness/cadence/timeout、bounded telemetry capacity 和
Planning Shadow divergence/pair-age limits。只复用 `641f7c4` 中语义/单位相同且已有证据的值；其余
使用 fail-closed calibration sentinel，禁止选择 permissive value。

snapshot 为 cup/TCP/joints/q6/controller、Gazebo attachment、MoveIt scene、finger/support contact 分别
保存 source timestamp、receipt sequence、freshness。Bullet Featherstone compound-owner 上真实
`task object ↔ intended table` contact 可作 support evidence；counterparty 必须匹配 intended table，
depth 必须 finite 且 `>= minimum_support_contact_depth_m`。缺失、non-finite、更负 depth fail-closed；
raw names、owner、depth min/max、accepted/rejected counts 作为 bounded metrics。

carry contact/q6/object-relative drift 的随机波动是 telemetry，不单独决定成功。fresh finite evidence、
controller/execution health、所有 collision/penetration ceilings、catastrophic loss 和每个 carrying plan 前
Gazebo-vs-shadow divergence 仍为 hard gates。support noise bound 不得用于 finger penetration；现有
`0.000800002 m` moving-pad ceiling 及其他 ceiling 不变。

`DETACH_MOVEIT` 先于 `OPEN_GRIPPER`。opening 后创建 release epoch；settle executor 负责 cadence、
cancellation、timeout，只收 marker 后 samples。纯 deterministic evaluator 无 ROS/sleep，以相邻
fresh pose/time 导出线/角速度，并同时要求 target XY、height、upright、stable speeds、真实 table
support、无 gripper contact、Gazebo detached、MoveIt detached。之后用冻结 Gazebo pose 同步 MoveIt
world object。failure code 区分 out-of-region、unsupported、tipped、still-moving、gripper-contact、
stale、shadow divergence、safety failure，并保留全部 bounded metrics。

### Recovery 与 acceptance

unsupported held cup 永不自动 open；先 stop/hold、冻结 controller/Gazebo/MoveIt/pose/contact/policy
证据，再进行独立 reset。final failure 在证据冻结前不得移动 cup。验收按 targeted Python tests、
package full test、dry-run、plan-only、isolated headless、GUI fresh screenshot、同 commit/policy 每次
FULL_RESTART 连续五次。纯 policy/domain/evaluator 循环不触发 C++ quality gate；只有 Python package
安装/ROS runtime 边界才做必要 colcon build。

## 2026-08-08 Target-only calibration authorization addendum

用户在 physical-outcome ownership 不变的前提下，仅授权调 grasp/motion target：TCP 抓取位置/姿态、
q6 close、micro-lift、carry/place/retreat waypoint 与姿态、trajectory duration/velocity/acceleration。
controller algorithm/gain/plugin、physics engine、geometry、mass、friction、final tolerance、collision/
penetration/planning-shadow/recovery ceiling 均冻结。normal forward Gazebo attach 继续禁止。

Python migration baseline 来自 preserved Task 15 target 及 `main@05dff7a` 对齐记录；physical
`641f7c4` 仅提供 contract/evidence 语义，不形成 C++ runtime dependency。baseline 尚未 qualification：
`grasp_close_q6=-0.047608632840292 rad`、micro-lift `+0.002 m world Z`、当前 motion YAML waypoints/
scaling，以及 task-object YAML 的 measured grasp-relative pose。杯体约束为 radius `0.040 m`、height
`0.090 m`、rim clearance `0.008 m`、bottom clearance `0.020 m`；q6 hard lower limit 为
`-0.059600220867817 rad`。fingertip geometry 只作约束，不允许修改。

搜索严格逐层、逐分量：A TCP translation 每轴独立，范围不超过已配置
`approach_outside_clearance_m` 的正负界；B orientation 每分量独立，范围不超过该 state 已有
`axis_tolerance_rad`；C q6 仅在 baseline 与 URDF safe lower limit 间；D micro-lift 从既有 `0.002 m`
起且必须严格低于既有 catastrophic relative-position ceiling；E waypoint 候选必须同时在 joint
limits 和原 state validation envelope 内；F timing/scaling 仅使用预注册且不超过当前 policy 的候选。
这些是探索边界，不是新 pass threshold；每个具体数值必须先由 geometry/plan-only/live evidence
说明并写入 ledger。变量顺序固定 A→B→C→D→E→F，上一层未消除首个 hard-gate failure 不进入下一层。

每个候选先 contract RED→GREEN，再 fresh install、全 state live plan-only，随后唯一
FULL_RESTART 的 `stop_after=VERIFY_PHYSICAL_GRASP`。VALID failure 淘汰且不重复抽样；INVALID 终止批次。
入选值冻结后至少三次独立 FULL_RESTART qualification，任一 valid failure 回退。只有短路径通过后
才做 full physical outcome、GUI 和同 commit/policy 连续五次 acceptance。

## 2026-08-08 Z → q6 → orientation 恢复授权 addendum

本 addendum 记录用户在 A 层 X/Y/Z 有界候选全部 VALID failure（止于 ledger
`PY-A-Z-POS-0004-GRASP-001`，decision `STOP_AND_REPORT_APPROVAL_BOUNDARY_EXHAUSTED`）之后批准的
新实验计划。它**仅**取代此前两条边界：（1）同方向三个有界候选失败后禁止继续细分的
no-interpolation 停止规则；（2）严格 A 全层完成后才进入 B、再进入 C 的顺序约束。所有其他
safety gate、frozen 约束与 process/session ownership 规则不变。

### 唯一写者转移

此前 executor（tmux `codex-cua`）在只读 Phase-0 audit 后暂停，未追加本授权、未改 target、未
build、未启动 stack。自本 checkpoint 起，Python ledger/worktree 的唯一写者为 tmux 会话 `kimi`
中的本 executor；不得恢复或向 `codex-cua` 发送输入。checkpoint recovery 为只读（git、ledger、
既有测试证据、status、PID ownership），不 rerun test suite、不 build、不 launch。

### 冻结约束（不变）

- 不改/不放宽 collision、penetration、planning-shadow、controller、freshness、finite-value、
  recovery、final-outcome、support、pose-stability 任何 gate；pad penetration ceiling 保持
  `0.000800002 m`。
- 不改 physics engine、geometry、mass、friction、controller/plugin/gain、task-object geometry、
  attachment 语义；normal forward 禁止 Gazebo attach。
- 无随机重试、无结果挑选、不复用 experiment ID；一个候选只改一个 scalar。
- VALID failure 淘汰该候选；INVALID 终止该批次，先只调试 contamination/实现缺陷，再用新
  batch/id；绝不把 target 变更叠加到未解决缺陷上。
- 每个实验先 PLANNED 预注册；provenance/preflight 后才记 RUNNING；以 VALID_SUCCESS /
  VALID_FAILURE / VALID_SAFETY_FAILURE / INVALID 之一加精确证据收尾。

### Phase 1：Z 二分，最多三个确定性候选

已知 bracket：下界 `+0.000400000 m`（bilateral、moving depth 过高），上界 `+0.000500000 m`
（moving contact 缺失）。只改 `grasp_tcp_translation_offset_m[2]`，X/Y/orientation/q6/路径/
scaling/gate 全部冻结。候选 1 为 `+0.000450000 m`；若 bilateral 保持但 penetration 越顶则以候选
替换下界，若 moving contact 缺失/不稳定则替换上界，候选 2/3 依次取更新后 bracket 的精确中点。
任一候选全部 hard gate 通过立即停止；本 phase 最多三个 VALID 物理候选。每候选走完整
RED→GREEN、focused+全量 package suite（不得回退于 136 passed, 2 skipped）、rebuild/source/
installed provenance 验证、六状态 plan-only（plan 失败即无物理执行地淘汰）、唯一 owned
FULL_RESTART、仅执行到 `VERIFY_PHYSICAL_GRASP` 的阶梯，并记录六个 post-command sample、双侧
contact、各 pad 最大 penetration、q6_contact/final、pose-pair age、controller result、Gazebo/
MoveIt attachment 状态、exit code 与精确证据路径。三个候选全败则关闭该 Z bracket，不再细分，
不组合 X/Y/Z，进入 Phase 2。

### Phase 2：q6 seating-preload 因果二分，最多三个 VALID 候选

这是对当前失败的显式批准顺序修正：q6 preload 先于 orientation 测试。确定性选择并冻结具有
bilateral contact 且 worst normalized penetration 最小的 Z 候选作为诊断锚点（非 qualified
winner）；冻结其余全部 target/config。若缺少 `seating_preload_rad` 配置 plumbing，仅以 TDD 增加
最小实现。允许幅度 `[0.0, 0.006] rad`；q6 target 必须保持在
`safe_lower_q6 <= q6_target <= baseline grasp_close_q6` 且继续由实测 `q6_contact` 推导。候选 1 为
`0.003 rad`；bilateral 保持但 penetration 过高则在 `[0, current]` 内减小二分，contact/stability
丢失则在 `[current, 0.006]` 内增大二分。最多三个 VALID 物理候选，首个全 gate 通过即停。全部失败
则关闭 q6 preload，进入 Phase 3。

### Phase 3：单一证据选定的 orientation 方向，最多三个 VALID 候选

先对既有证据做只读 geometry/contact-normal/TF/FK 分析，写出竞争假设并选定最可能在保持 fixed
contact 的同时卸载 moving pad 的唯一 roll/pitch/yaw 轴与符号；不得猜测。若无可辩护的轴/符号，
不做任何 orientation 物理实验，直接进入 Phase 4。冻结最佳诊断 Z 锚点，并恢复文档化 q6 baseline
（除非 Phase 2 已全 gate 通过）。只改一个 orientation scalar，幅度按序为
`0.017453292519943295`、`0.04363323129985824`、`0.08726646259971647 rad`，不超过既有
`axis_tolerance_rad`。响应与假设相反地恶化或候选通过即提前停止；不自动尝试另一轴或反号。

### Phase 4：只读 geometry/contract 可行性审计

停止 target 实验。在不改任何控制 geometry/physics/controller/gate 的文件前提下审计 cup
radius/wall、pad gap/thickness/collision surface、contact normal/depth 分布、实测 q6、TCP/cup
pose 与 `0.000800002 m` ceiling，判断在当前模型与已授权 target DOF 下是否存在非空稳健区域使
bilateral contact 且双侧 penetration 均在 ceiling 内。提交审计证据/checkpoint 并恰好给出以下之一
结论：`FEASIBLE_WITH_NEXT_EXACT_TARGET_HYPOTHESIS` 或
`TARGET_ONLY_INFEASIBLE_UNDER_CURRENT_MODEL`。若不可行，停止并请求用户决策；绝不放宽 gate 或
修改 geometry。

### Qualification 与原流水线

首个 grasp 候选通过后：冻结完整 commit/config/policy fingerprint，至少三次独立 FULL_RESTART
grasp qualification（任一 VALID failure 结束 qualification 并仅回到仍获授权的有界 phase；INVALID
终止批次）；三次通过后预注册并运行 detached 物理 micro-lift（精确 world-Z `+0.002 m`，无 forward
Gazebo attach，lateral/orientation/penetration/shadow gate 不变）；随后在下一个首个失败边界重新
接入已批准的 D→E→F target-only 流程，一次一个 scalar；执行完整物理 pick/place，最终 Gazebo cup
pose 必须稳定、直立、落在已批准放置范围内，MoveIt scene membership 独立验证；之后 fresh
clean-cache build/全量 suite、dry-run、完整 plan-only、headless、GUI/CUA 新截图，以及同一冻结
commit/policy 连续五次 FULL_RESTART 物理结果成功（INVALID 不计且终止批次，VALID failure 清零
连击）。仅在完整 contract 与五连成功后才做 scoped commit、推送 feature branch 到 Gitee、验证
remote SHA、按既有批准 merge gate 合并到干净 main worktree、重跑合并树测试并推送 main。禁止
force-push、禁止 `gh`、禁止在 dirty main 上合并。

## 2026-08-08 增补授权：penetration gate 诊断性放宽（非重校准）

用户在 know-how 总结（`docs/experiments/2026-08-08-so101-grasp-gate-failure-knowhow.md`）之后授权一次诊断性尝试：
在文档化诊断锚点（`grasp_tcp_translation_offset_m [0.0, 0.0, 0.0004]`、`seating_preload_rad 0.006`、
`grasp_tcp_world_x_rotation_rad 0.0`）下，适度放开 moving-pad penetration gate，观察 MICRO_LIFT
物理上能否把杯子带起来。明确不解除 orientation 可规划性。

- 该尝试不是 qualification，也不是 ceiling 重校准；`0.000800002 m` frozen ceiling 仍是未来任何
  qualification 的验收 gate。诊断结束无论结果如何都把诊断 scalar 复原为禁用。
- 实现为 motion policy 的可选字段 `diagnostic_moving_pad_penetration_ceiling_m`：`0.0` 表示禁用
  （默认，走 frozen 常量），启用值界为 `(0.000800002, 0.0012]`。诊断取值 `0.0012 m`：高于双侧运行
  观测到的最大 moving-pad 深度（`0.001193 m`），低于 solver 上报接触深度上限 `0.0013 m` 与
  profile 的 2 mm 硬安全上限。
- 几何、物理引擎、质量、摩擦、controller/plugin/gain、task-object、attachment 语义全部不变；
  不做 forward Gazebo attach；execute 仍只走到 `VERIFY_PHYSICAL_GRASP`（其内部含 `+0.002 m`
  micro-lift 探针），以 Gazebo cup pose 为物理事实源读出 `cup_world_z_delta_m`、lateral drift 与
  双侧 contact/depth。
- 结论与证据写回 experiment ledger；任何 ceiling 重校准都只能由用户决策。

## 2026-08-09 增补授权：moving-pad penetration ceiling 重校准

基于 EXP-PEN-DIAG-001-GRASP-229 的物理证据（杯子在 moving-pad 深度约 0.0010 m 时被
micro-lift 稳定带起，lift 误差 0.4 µm、lateral 0.216 mm、双侧接触稳定）与 Phase-4 分布审计，
用户裁决重校准验收 ceiling。

- 确定性取值规则：新 ceiling = solver 上报深度上限 `0.0013 m` − `0.00005 m` 可测量性护栏
  = `0.00125 m`。高于观测分布 max `0.001193 m`（余量 57 µm），低于 solver 饱和点，
  远低于 2 mm 硬安全上限。
- 实现：`MOVING_PAD_MESH_PENETRATION_CEILING_M` 常量改为 `0.00125`；诊断 override 界同步改为
  `(0.00125, 0.0013]`，防止 override 隐式收紧验收 gate；override 默认 0.0 禁用不变。
- 统计坦白：余量约 0.18σ，不保证五连成功；qualification 实证检验。若 0.00125 m 下仍复发
  VALID penetration failure，则绑定约束是模型/solver 上限本身，回到用户决策。
- 其余全部不变：锚点 target、几何、物理、摩擦、质量、controller、attachment 语义、
  lateral/lift/shadow/freshness/support/final-outcome gates。

## 2026-08-09 增补授权：solver-limit gate 语义（用户选项 1）

用户在 `CP-QUALIFICATION-ENDED-001` 之后选择选项 1：把 grasp 深度 gate 改为 solver-limit 区间。

- `MOVING_PAD_MESH_PENETRATION_CEILING_M = 0.0013`（= solver 上报上限）：对 bilateral（可上报）
  接触，瞬时深度 ceiling 实际 vacuous；唯一深度 gate 是 within-solver-limit 可上报性检查。
  grasp 验收落在稳定双侧接触 + 物理 micro-lift 携带 gate（lift `+0.002 m`、lateral `<= 0.001 m`）。
- 依据：该接触模型下的虚拟穿透深度在观测物理方差下不是可用健康指标；诊断已证明杯子在
  ~0.0010 m 深度被物理携带（EXP-PEN-DIAG-001-GRASP-229），0.00125 m 在 run 间方差下失败
  （EXP-QUAL-GRASP-1-231），solver 饱和点以下仅剩 50 µm。
- 连带移除 diagnostic override 全部 apparatus（motion policy 字段、loader 界、gate ceiling
  kwargs）：solver 上限以上不可测量、以下会隐式收紧 gate；恢复单一常量 gate 语义。
- 其余不变：锚点 target、几何、物理、摩擦、质量、controller、attachment 语义、
  lift/lateral/shadow/freshness/support/final-outcome gates。
