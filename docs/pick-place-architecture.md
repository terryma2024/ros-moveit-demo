# Shared pick-place architecture

The dependency direction is one-way:

```text
panda_gazebo_demo ─┐
                   ├─> pick_place_common::ros_adapters ─> pick_place_common::core
so101_gazebo_demo_cpp ─┘
```

Current ROS 2 package identity is so101_gazebo_demo_cpp. The C++ namespace and include path remain so101_gazebo_demo. Dated historical experiments, handoffs, and provenance retain the legacy package name verbatim and are not current runtime commands.

`pick_place_common::core` owns the robot-independent domain model, workflow
interface, runner, state-action and transition contracts, plan validation,
common resume validation, world snapshot model, and simulation session ID.
`pick_place_common::ros_adapters` owns the generic Gazebo attachment and MoveIt
scene executors, including validation, cancellation, polling, timeout, and
convergence checks.

Each robot package owns its `WorkflowDefinition`, runner behavior and operation
policies, motion and gripper implementation, geometry/contact/reset/recovery
policy, concrete ROS/Gazebo/MoveIt adapters, and launch/world/URDF/SRDF/config
assets. SO-101 Teleop is also robot-specific. Compatibility headers in the
robot include trees may expose aliases or thin wrappers, but contain no copied
workflow or executor algorithm.

Checkpoint schema v3 types and common resume rules live in the common core.
Panda preserves `configuration_hash`; SO-101 preserves
`policy_bundle_sha256`. Their JSON codecs, file stores, and persistence paths
remain local because those are robot application boundaries.

SO-101 additionally owns a physical-grasp evidence sidecar at the checkpoint
path plus `.physical-grasp.json`. This is deliberately not part of the common
checkpoint schema: it atomically persists the two physical validation samples,
and binds them to the simulation session and policy fingerprint across separate
CLI processes. Its pre-attachment chain is `WAIT_GRASP_STABLE -> MICRO_LIFT ->
WAIT_MICRO_LIFT_STABLE -> VERIFY_PHYSICAL_GRASP`; validator failure takes
`VERIFY_PHYSICAL_GRASP -> VALIDATION_FAILED`.

SO-101's verification executor owns a bounded physical retry coordinator. It
allows five total attempts, not five additional retries. Each retry is
`PREOPEN -> saved-before-lift world-Z descend -> reclose -> stable capture ->
2 mm MICRO_LIFT -> verify`. A contact-present failure keeps the current reclose
q6. A contact-missing failure tightens only that target by exactly 1.0 mrad,
with a 4.0 mrad cumulative cap. The pre-lift stabilizer then applies the same
fixed 6.0 mrad preload on every attempt and holds it through MICRO_LIFT; the
retry adjustment never changes that preload. Nonretryable results cause no
retry. Exhaustion copies the fifth physical failure unchanged and only appends
attempt/retry/q6 metrics.

The sidecar's retry record contains the attempt index, cumulative missing-contact
count, current reclose target, fixed preload target, and a write-ahead phase for
each external side effect. Any resume with `OPEN_PENDING`, `DESCEND_PENDING`,
`CLOSE_PENDING`, `LIFT_PENDING`, or `VERIFY_PENDING` fails closed as
`PHYSICAL_GRASP_RETRY_INTERRUPTED`; it never guesses whether an interrupted
command completed. The workflow graph and common runner are unchanged. Panda
and `pick_place_common` have no SO-101 physical retry coordinator, parameters,
or sidecar semantics.

The common runner supports workflow-declared validation parking. Passive normal
execute resume at a validation pause has no side effects and preserves both the
original failure and checkpoint bytes. Only a declared execute-resume,
single-use force edge may continue; mismatches fail with
`FORCE_CONTINUE_STATE_MISMATCH` before observation or action. Panda keeps its
characterized behavior by declaring no force-continue state.

New robot consumers should link the exported targets and provide a
`WorkflowDefinition` plus explicit policies. `IRunnerBehaviorPolicy` names the
runner's execute preflight, observation-recovery, environment-failure,
transient-observation retry, resume-settling, original-failure preservation,
pre/postcondition retry, and trace decisions; `DefaultRunnerBehaviorPolicy`
is the characterized Panda baseline. A new consumer must not copy the runner,
domain/state-action implementation, or Gazebo/MoveIt executor sources.

The full automated gate is:

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-up-to panda_gazebo_demo so101_gazebo_demo_cpp \
  --symlink-install --cmake-clean-cache
source install/setup.zsh
PYTHONNOUSERSITE=1 colcon test \
  --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo_cpp \
  --event-handlers console_direct+
colcon test-result --verbose
```

## SO-101 physical outcome ownership

SO-101 的 normal forward workflow 中，Gazebo physics 是杯子运动的唯一 physical truth；
MoveIt attachment 仅是 planning shadow，不能驱动 Gazebo。物理抓取验证通过后，
`ATTACH_MOVEIT` 必须使用最新 Gazebo cup pose 建立 collision shadow；每个 carrying plan 前都
必须验证 shadow divergence。放置时先 `DETACH_MOVEIT`，再 `OPEN_GRIPPER`，随后执行
`WAIT_RELEASE_SETTLE -> VALIDATE_FINAL_PLACEMENT -> SYNC_WORLD_OBJECT -> RETREAT -> DONE`。

Release epoch 从确认物理开夹后的 Gazebo pose sequence 开始，所有 pre-release samples 都被
拒绝；post-release epoch is non-resumable。最终判定要求连续样本与最短持续时间、目标 XY、
support height、upright tilt、derived linear/angular speed、cup-bottom-to-table support contact、
无 gripper contact、Gazebo/MoveIt 均 detached，以及最终 world-object synchronization。
阈值来自 schema-2 validation policy；`CALIBRATION_REQUIRED` 不得用于宣称成功。

中间 contact/q6/object-relative drift 波动只作为有界 telemetry/distribution evidence。硬门仍包括
fresh finite evidence、controller/execution health、既有 collision/penetration ceilings、无
catastrophic loss，以及 planning shadow divergence。验收要求 five consecutive 有效运行，且每次
都有独立 Gazebo、MoveIt、controller、pose、contact 和 fresh visual evidence。

失败后不得在无支撑时自动开夹爪；应 stop/hold 并冻结证据，reset 是独立受控事务。拒绝恢复
R3 已证伪路线：0.75 mm seat、independent CLOSE seat、仅延长 close duration、放宽 safety gates，
以及 unregistered fixed-port retry fixture。
