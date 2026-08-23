---
task_id: so101-gazebo-python-capabilities
goal: >-
  Implement and validate manifest-driven Gazebo Python Planning Scene, package-owned
  camera presets, complete transactional reset, and five final MuJoCo FULL_RESTART wins.
worktree: /data/work/ws_moveit/.worktrees/so101-demo-py-canonical
branch: codex/so101-demo-py-canonical
approved_base: 1fa155e1524fc24b7059e76eb88540abda327ba6
design_commit: fccb1a49
evidence_root: /tmp/so101-debug-gazebo-python-capabilities-boWK6J
frozen_policy:
  path: src/so101_demo_py/config/policies/light_cup_wall_pick/v1/mujoco.yaml
  sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
live_state_values: [PLANNED, RUNNING, VALID, INVALID]
---

# SO-101 Gazebo Python Capabilities Experiment Ledger

## Success contract

- Planning Scene apply and independent read-back prove table/pedestal/plastic_cup primitive counts `1/1/13`, canonical 6D poses, world membership, and no unexpected attachment.
- Gazebo camera preset receives positive `/gui/move_to/pose` acknowledgement and an inspected fresh before/after GUI snapshot pair proves a real viewpoint change.
- After deliberate arm and cup disturbance, full reset independently proves Gazebo pose/attachment, MoveIt pose/membership/attachment/`1/1/13`, active controllers, arm/gripper joint positions and velocities, TF, and visual convergence.
- The final committed source, installed bundle, frozen policy, and fixed geometry contract achieve five consecutive independent qualified MuJoCo `FULL_RESTART` successes.
- A valid failed outcome stops a qualification sequence. An invalid experiment stops its batch. Historical successes do not count.

## Immutable safety boundary

- Direct execution on `AI-STATION-001`; SSH to self is forbidden and has not been used.
- No push, merge, main modification, other-worktree cleanup, real-arm operation, broad `pkill`, `gh`, or `ament_uncrustify --reformat`.
- Do not invoke, wrap, or read runtime executable/configuration from `so101_gazebo_demo_cpp`.
- Stop only task-owned PIDs recorded by an experiment. Preserve all pre-existing tmux sessions and unrelated processes.

## CP-GZPY-001 — Verified baseline

status: VALID
outcome: BASELINE_ACCEPTED
recorded_at: 2026-08-13 Asia/Shanghai

### Provenance

- Host: `AI-STATION-001`
- Target worktree: `/data/work/ws_moveit/.worktrees/so101-demo-py-canonical`
- Target branch: `codex/so101-demo-py-canonical`
- Initial target HEAD: `1fa155e1524fc24b7059e76eb88540abda327ba6`
- Design commit: `fccb1a49`
- Target status before task changes: clean
- Git common dir: `/data/work/ws_moveit/.git`
- Submodule gitlink: `738e304551b4ea6db020b466086a13db71b65607` (uninitialized and preserved)
- Main worktree: `/data/work/ws_moveit`, branch `main`, HEAD `072541a0e537080c3f2abf3945a156b26d06f48d`, clean
- `origin/main`: `072541a0e537080c3f2abf3945a156b26d06f48d`
- Origin: Gitee (`git@gitee.com:zjumty/ros-moveit-demo.git`)
- Frozen MuJoCo policy SHA-256: `aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356`

### Preserved runtime state

- Existing tmux sessions: `MNT-Q-RESET-EXP136-140`, `codex`, `codex-cua`, `so101-mujoco-gui`
- No exact running Gazebo, MoveIt, ros2_control, RViz, or robot-state-publisher process at baseline.
- Baseline ROS graph had no nodes and only `/parameter_events`, `/rosout` topics.
- These sessions and unrelated state are outside task ownership and must remain untouched.

### Baseline evidence

- `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/baseline-audit.log`
- `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/host-runtime-audit.log`
- `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/baseline-so101-demo-py-installed-tests-corrected.log`
- Installed-baseline `so101_demo_py` suite: `97 passed`.

### Rejected invocations and disproven routes

- Unsourced direct pytest could not import the installed canonical package; it is an invalid test invocation, not a product failure.
- A run with default `~/.ros` logging failed under the workspace sandbox; all subsequent test/live commands set a task-specific `ROS_LOG_DIR`.
- The complete baseline Teleop suite collected `214` tests but hung after `119`; the task will run affected focused/package tests and will not silently classify that unrelated baseline hang as a feature failure.
- Whole-tree Ruff reported `196` pre-existing errors and is not the repository's scoped gate. Ruff will cover `so101_demo_py` plus touched Teleop Python files, without auto-formatting.

## Live experiment queue

## CP-GZPY-SCENE-001 — Manifest-driven Planning Scene

status: VALID
outcome: FAILED
lifecycle: GAZEBO_SHARED_STACK
source_commit: `68c590a6b21ac39244232df5f1f98ed902882531`
installed_prefix: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/task-09-final-install/so101_demo_py`
bundle_sha256: `c55d43be8f3e78d5ceeebb429e36d37e03f426bcd5dce4c5bd0d5e0a1ae1d062`
geometry_manifest_sha256: `6dc64c197a82316c4ac856530c6caf5d905ffd2b0ea2778d85d87b9a3e89b235`
policy_sha256: `aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356`
ros_domain_id: `187`
gz_partition: `cp-gzpy-001`
simulation_session_id: `cp-gzpy-shared-001`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/live/scene-001`

Hypothesis: the installed Python-owned Gazebo stack becomes ready and the public
`scene_setup --backend gazebo setup` applies the canonical manifest to MoveIt.

Acceptance contract: require a zero owner receipt plus an independent
`/get_planning_scene` observation with exact world IDs `table`, `pedestal`,
`plastic_cup`; no attached task object; canonical 6D object and primitive-local
poses/colors/dimensions; and exact primitive counts `1/1/13`. Record stack supervisor
PID/PGID and every task-owned child before review. Any missing read-back field is
`INVALID`; a complete nonconvergent product receipt is `VALID` with `outcome: FAILED`.

Terminal review: readiness proved all three controllers active and all required
MoveIt services/actions available. Apply/read-back returned complete evidence with exact
world IDs and primitive counts `1/1/13`, but failed `READ_BACK / SCENE_READBACK_MISMATCH`
for `plastic_cup.primitive[4].pose` and `plastic_cup.primitive[5].pose`. This is a valid
product failure. Evidence:
`/tmp/so101-debug-gazebo-python-capabilities-boWK6J/live/scene-001/readiness.log`,
`scene-setup.log`, `controllers-before.txt`, and `owned-processes-before.txt`.

## CP-GZPY-SCENE-002 — Quaternion-invariant Planning Scene read-back

status: VALID
outcome: SUCCEEDED
lifecycle: GAZEBO_SHARED_STACK
source_commit: `9c38547bdc0675a6197ee374be0ef923cfdfd40b`
installed_prefix: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/task-10-candidate-install/so101_demo_py`
bundle_sha256: `6e6d59611b485699896db5a850eb919b5729fb6f041a30f4a54a5183ccadf51b`
geometry_manifest_sha256: `6dc64c197a82316c4ac856530c6caf5d905ffd2b0ea2778d85d87b9a3e89b235`
policy_sha256: `aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356`
ros_domain_id: `188`
gz_partition: `cp-gzpy-002`
simulation_session_id: `cp-gzpy-shared-002`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/live/scene-002`

Hypothesis: after the focused quaternion-double-cover fix, the installed Python-owned
scene client accepts MoveIt's equivalent `q`/`-q` representation without weakening any
position, geometry, color, membership, or count check.

Acceptance contract: require readiness, zero apply/read-back receipt, exact world IDs,
no MoveIt attachment, canonical 6D geometry modulo quaternion sign only, and primitive
counts `1/1/13`. Retain independent raw `/get_planning_scene` values and provenance.
Incomplete evidence is `INVALID`; a complete mismatch is `VALID`/`FAILED`.

Terminal review: readiness proved the required services/actions and exact active
controller set. The shared CLI returned `success: true`, `phase: READ_BACK`, exact world
IDs, no attachments, no mismatches, and counts table/pedestal/plastic_cup `1/1/13`.
Independent `/get_planning_scene` raw JSON retained every world/object/primitive 6D pose,
dimension, type, color, and empty attachment list. Evidence directory:
`/tmp/so101-debug-gazebo-python-capabilities-boWK6J/live/scene-002`.

## CP-GZPY-CAMERA-001 — Gazebo GUI camera preset

status: VALID
outcome: SUCCEEDED
lifecycle: GAZEBO_SHARED_STACK
source_commit: `9c38547bdc0675a6197ee374be0ef923cfdfd40b`
installed_prefix: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/task-10-candidate-install/so101_demo_py`
bundle_sha256: `6e6d59611b485699896db5a850eb919b5729fb6f041a30f4a54a5183ccadf51b`
ros_domain_id: `188`
gz_partition: `cp-gzpy-002`
simulation_session_id: `cp-gzpy-shared-002`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/live/camera-001`

Hypothesis: the Python-owned `overview` then `top` preset calls
`/gui/move_to/pose`, receives positive acknowledgement, and changes the real Gazebo
viewpoint.

Acceptance contract: use one declared CUA session and exact Gazebo window; capture and
inspect a fresh pre-action window snapshot, invoke the public CLI only after it exists,
capture and inspect a fresh post-action snapshot, and retain both absolute PNG paths and
SHA-256 values. The adapter receipt must contain the positive transport acknowledgement.
Missing/stale/uninspected imagery is `INVALID`; a complete negative acknowledgement is
`VALID` with `outcome: FAILED`.

Terminal review: CUA session `cp-gzpy-camera-001` was scoped to Gazebo window
`35651598` owned by PID `3386274`. Snapshot `s00000005` was captured before the action,
inspected, and showed the angled overview; its PNG is
`/tmp/so101-debug-gazebo-python-capabilities-boWK6J/live/camera-001/cua-before-overview.png`
with SHA-256 `d147aff37abba509a2a6a1a7f6d3207843febbdd3f51f2c4096c9527c3e1d730`.
The public `camera_preset --backend gazebo top` receipt records service
`/gui/move_to/pose`, `acknowledged: true`, and transport output `data: true`.
Fresh post-action snapshot `s00000006` was inspected and showed the true top-down view;
its PNG is
`/tmp/so101-debug-gazebo-python-capabilities-boWK6J/live/camera-001/cua-after-top.png`
with SHA-256 `631bf5d93d9eec90069c21d74a2b4a649093b509ab1b10be50ab53b6bd4882f6`.
The two snapshots also show the GUI pose controls changing from the overview values to
the configured top preset. The complete receipt is retained as
`camera-top-receipt.log` in the experiment evidence directory.

## CP-GZPY-RESET-001 — Disturbed transactional Reset

status: VALID
outcome: FAILED
lifecycle: GAZEBO_SHARED_STACK
source_commit: `9c38547bdc0675a6197ee374be0ef923cfdfd40b`
installed_prefix: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/task-10-candidate-install/so101_demo_py`
bundle_sha256: `6e6d59611b485699896db5a850eb919b5729fb6f041a30f4a54a5183ccadf51b`
ros_domain_id: `188`
gz_partition: `cp-gzpy-002`
simulation_session_id: `cp-gzpy-shared-002`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/live/reset-001`

Hypothesis: after independently recorded arm and cup disturbance, the public
`teleop_reset --backend gazebo` completes all thirteen phases as one transaction.

Acceptance contract: prove the disturbance before Reset, then require a zero complete
transaction receipt and independent final observations for Gazebo cup 6D pose and
physical attachment, MoveIt world membership/attachment/6D pose and `1/1/13`, exact
active controller set, arm/gripper joint positions and velocities, required TF, plus a
fresh inspected visual convergence snapshot. A first phase failure with complete
evidence is `VALID`/`FAILED`; missing independent evidence is `INVALID`; partial success
is never accepted.

Terminal review: the disturbance was independently proven before Reset. Gazebo emitted
`{"data":"detached"}`; native pose read-back placed `plastic_cup` at approximately
`(0.3500013, 0.1500003, 0.0449999)`; `/joint_states` placed arm joints at approximately
`[0.30, -0.30, 0.25, -0.20, 0.15]`; and all three required controllers remained active.
The public Reset returned nonzero with first phase `OBSERVE_INITIAL`, failure code
`RESET_OBSERVE_INITIAL_FAILED`, and no completed phases. Its evidence showed
`cup_pose: null`, `attached: null`, and TF frames `wrist/gripper/jaw/...` rather than
the adapter's hard-coded `so101_tcp`. The raw bridge observation independently shows
that converting Gazebo `Pose_V` to `TFMessage` loses entity names, while the
detachable-joint state is an edge-triggered Gazebo `StringMsg`. This is a complete,
attributable product failure, not missing evidence. The inspected ai-station-gui
fallback image shows the disturbed arm and cup separated from canonical spawn at
`/tmp/so101-debug-gazebo-python-capabilities-boWK6J/live/reset-001/gui-disturbed-fallback/20260813T115614-22f187bb601b/desktop.png`.
All raw receipts and observations are retained in the experiment evidence directory.

## CP-GZPY-RESET-002 — Direct Gazebo state transactional Reset

status: VALID
outcome: FAILED
lifecycle: GAZEBO_SHARED_STACK
source_commit: `cd48cd1663d7e884c6a1adb2288feb4508fa05b0`
installed_prefix: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/task-11-install/so101_demo_py`
bundle_sha256: `2d4c97282788b057bcb2fec7df6d3d6d0aab994661bb6ab2f1d859a7c3df2008`
geometry_sha256: `6dc64c197a82316c4ac856530c6caf5d905ffd2b0ea2778d85d87b9a3e89b235`
ros_domain_id: `188`
gz_partition: `cp-gzpy-002`
simulation_session_id: `cp-gzpy-shared-002`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/live/reset-002`

Hypothesis: direct named Gazebo `Pose_V` observation, ECS detachable-joint read-back,
and transient-local static TF observation allow the same public Reset transaction to
complete after a fresh independently recorded arm and cup disturbance.

Acceptance contract: independently reapply and prove both disturbances after this
entry becomes `RUNNING`; require all thirteen public Reset phases, then independently
read back native Gazebo cup 6D pose and physical detachment, MoveIt world membership,
attachment, pose and `1/1/13`, all required active controllers, joint positions and
velocities, canonical TCP TF, plus a fresh inspected visual convergence image. Any
complete first-phase failure is `VALID`/`FAILED`; missing evidence is `INVALID`.

Terminal review: the fresh arm goal reached approximately
`[0.20, -0.25, 0.30, -0.15, 0.10]`; native Gazebo read-back placed the detached cup at
approximately `(0.3200, 0.1400, 0.0450)` and proved the exact detachable joint absent.
Reset then completed `OBSERVE_INITIAL`, both cancellation phases, `DETACH_PHYSICAL`,
and `DETACH_MOVEIT`. Initial evidence now included the named cup pose, exact Gazebo
entity IDs, `attached: false`, canonical `so101_tcp`, all joints/velocities, and all
required active controllers. It failed at `PARK_CUP` with
`RESET_GAZEBO_POSE_VERIFY_FAILED`: the command received `data: true`, but the configured
table-exterior pose `(0.45, 0.25, 0.08)` falls under gravity to the ground-rest height
near `0.045`, so exact physical convergence is impossible. This is a complete,
attributable product failure. The inspected disturbed image is
`/tmp/so101-debug-gazebo-python-capabilities-boWK6J/live/reset-002/gui-disturbed-fallback/20260813T120617-2ef193be5a72/desktop.png`.

## CP-GZPY-RESET-003 — Stable parking transactional Reset

status: VALID
outcome: FAILED
lifecycle: GAZEBO_SHARED_STACK
source_commit: `f00ce7f1025fc37cbaf29e5988c4f67161c05813`
installed_prefix: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/task-12-install/so101_demo_py`
bundle_sha256: `93e64010fe6e9ea26d6409b11a8600bc4d7a9c0804abb2a5f5b47066f5d0efcf`
geometry_sha256: `6dc64c197a82316c4ac856530c6caf5d905ffd2b0ea2778d85d87b9a3e89b235`
ros_domain_id: `188`
gz_partition: `cp-gzpy-002`
simulation_session_id: `cp-gzpy-shared-002`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/live/reset-003`

Hypothesis: the ground-stable parking pose `(0.45, 0.25, 0.045)` allows the full
thirteen-phase transaction to complete without weakening physical pose verification.

Acceptance contract: independently reapply and prove fresh arm/cup disturbance after
transition to `RUNNING`; require all thirteen phases and the same independent final
Gazebo, MoveIt, controller, joints/velocities, TF, and inspected visual gates declared
for Reset-002. Any complete first-phase failure is `VALID`/`FAILED`; missing evidence is
`INVALID`.

Terminal review: the fresh disturbed arm reached approximately
`[0.25, -0.20, 0.20, -0.25, 0.20]`, while native Gazebo placed the detached cup near
`(0.30, 0.12, 0.045)`. Reset completed initial observation, both goal cancellations,
both detach phases, stable physical parking, and parked Planning Scene synchronization.
At `OPEN_GRIPPER`, the action returned `SUCCEEDED`, but the single immediate verification
sample still had joint 6 at `-0.0567392` with velocity `-0.0297988`; it therefore failed
closed with `RESET_JOINT_VERIFY_FAILED`. This is an attributable settle-timing defect:
position and velocity must converge together within the existing bounded timeout rather
than weakening either tolerance. The inspected disturbed image is
`/tmp/so101-debug-gazebo-python-capabilities-boWK6J/live/reset-003/gui-disturbed-fallback/20260813T121133-f38986eab733/desktop.png`.

## CP-GZPY-RESET-004 — Bounded joint-settle transactional Reset

status: VALID
outcome: FAILED
lifecycle: GAZEBO_SHARED_STACK
source_commit: `53b648a9a0cd239c7ab57a3e673b2289ba431a98`
installed_prefix: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/task-13-install/so101_demo_py`
bundle_sha256: `33493d524b14a8cda8ba252970679020f8b97ddc15e72a04fcc730dcfd90edb8`
geometry_sha256: `6dc64c197a82316c4ac856530c6caf5d905ffd2b0ea2778d85d87b9a3e89b235`
ros_domain_id: `188`
gz_partition: `cp-gzpy-002`
simulation_session_id: `cp-gzpy-shared-002`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/live/reset-004`

Hypothesis: bounded joint position-and-velocity convergence after each successful action
allows the full transaction to complete while retaining the exact tolerances.

Acceptance contract: independently reapply and prove fresh arm/cup disturbance after
transition to `RUNNING`; require all thirteen phases and independent final Gazebo,
MoveIt, controller, joints/velocities, TF, and inspected visual gates. A complete
first-phase failure is `VALID`/`FAILED`; missing evidence is `INVALID`.

Terminal review: the fresh disturbance placed the arm near
`[0.20, -0.15, 0.25, -0.20, 0.15]` and the physically detached cup near
`(0.3012, 0.1003, 0.0450)`. Reset completed initial observation, cancellations,
physical and MoveIt detach, physical and MoveIt parking, and bounded gripper opening;
the final gripper sample was within both exact position and velocity tolerances. It
then failed at `PLAN_HOME` with stable code `RESET_PLAN_HOME_FAILED` and exception type
`TypeError`. The empty exception message requires a traceback-preserving diagnostic
before changing planning behavior. The inspected disturbed image is
`/tmp/so101-debug-gazebo-python-capabilities-boWK6J/live/reset-004/gui-disturbed-fallback/20260813T121549-d71d7dcb2d5a/desktop.png`.

## CP-GZPY-RESET-005 — MoveIt wire-request transactional Reset

status: VALID
outcome: SUCCEEDED
lifecycle: GAZEBO_SHARED_STACK
source_commit: `615dd8bdc104f4405125e03762e41f58eeb1bb00`
installed_prefix: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/task-14-install/so101_demo_py`
bundle_sha256: `56c074a10bef879a7b190b8628522b2e184a35343720199b2e4369ff6a4c5cff`
geometry_sha256: `6dc64c197a82316c4ac856530c6caf5d905ffd2b0ea2778d85d87b9a3e89b235`
ros_domain_id: `188`
gz_partition: `cp-gzpy-002`
simulation_session_id: `cp-gzpy-shared-002`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/live/reset-005`

Hypothesis: converting the reset application's joint-domain request into a native
`GetMotionPlan.Request` allows the exact Home plan and all remaining transaction phases
to complete after an independently proven fresh arm and cup disturbance.

Acceptance contract: transition to `RUNNING` before disturbance; independently prove
fresh arm and cup disturbance; require all thirteen phases and independent final Gazebo
cup 6D pose/physical detachment, MoveIt membership/pose/attachment and `1/1/13`, all
required active controllers, joint positions and velocities, canonical TCP TF, and a
fresh inspected convergence image. A complete first-phase failure is `VALID`/`FAILED`;
missing independent evidence is `INVALID`.

Terminal review: the fresh arm action reached approximately
`[0.15, -0.20, 0.20, -0.15, 0.10]`, native Gazebo read-back placed the detached cup at
approximately `(0.28, 0.14, 0.045)`, and the exact ECS detachable-joint component was
absent before Reset. The public Reset returned zero and completed all thirteen phases:
initial observation, both cancellations, both detach operations, physical and Planning
Scene parking, bounded gripper opening, exact MoveIt Home plan and execute, physical cup
restore, final Planning Scene synchronization, and final verification.

Independent post-transaction evidence confirms native Gazebo cup pose
`(0.01999999, -0.28000072, 0.16499963, 0.00000008, 0.00000008,
0.00000190, 1.0)` and no `component: "94 18 fixed"` in the ECS snapshot (snapshot
SHA-256 `c51749ca59948a17e96e382c6b90f1b6456c0223082eba8ffd60aa9de10cc904`).
The raw `/get_planning_scene` response has world IDs `pedestal`, `plastic_cup`, and
`table`, zero attached objects, exact object poses/colors, and primitive counts
`1/13/1`. Independent `/joint_states` has arm errors below `0.0001`, gripper at
`-0.05959819`, and all velocities below `4.1e-7`; the exact three controllers are
active. Reliable `/tf_static` and `/tf` samples prove `world -> base`, the complete
dynamic arm chain, and `gripper -> so101_tcp`; bounded `tf2_echo` resolves
`world -> so101_tcp` repeatedly.

The freshly captured disturbed image was inspected at
`/tmp/so101-debug-gazebo-python-capabilities-boWK6J/live/reset-005/gui-disturbed-fallback/20260813T122142-2c279c838b8a/desktop.png`
(SHA-256 `3f09ca90bcd719c89bbe5787737a51b53b8c0a82eb8c6cce5d80a06a3f726576`).
The fresh post-Reset image was separately inspected and shows the arm converged to Home
and the cup restored at canonical spawn:
`/tmp/so101-debug-gazebo-python-capabilities-boWK6J/live/reset-005/gui-final-fallback/20260813T122713-02e1b84358e8/desktop.png`
(SHA-256 `b419ee89fbdfc017e8ec7f7300d0eab959c1a38d8428cb66a147e1eaea14d00d`).

## CP-GZPY-FULL-RESTART-001 through 005 — final fixed-bundle preregistration

batch_status: INVALID
backend: mujoco
lifecycle: FULL_RESTART
qualification_source_commit: `615dd8bdc104f4405125e03762e41f58eeb1bb00`
registration_parent_commit: `d94ad500baf112c3b9c57263c82e81d3404cedc8`
installed_prefix: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/final-candidate-001-install/so101_demo_py`
bundle_sha256: `f8a2910a945c72fa8f08f889589f52f9944b4382a7d4d27e4c873852a2f08725`
policy_sha256: `aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356`
geometry_sha256: `6dc64c197a82316c4ac856530c6caf5d905ffd2b0ea2778d85d87b9a3e89b235`
mujoco_ros2_control_prefix: `/data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install`
mujoco_ros2_control_gitlink: `738e304551b4ea6db020b466086a13db71b65607`
mujoco_ros2_control_executable_sha256: `9fd047eaae7ed2eff3f49aeb42880f88019ccf84787ecd5183ee5de78d73506e`
required_consecutive_successes: 5
reuse_old_successes: false
invalid_effect: stop and invalidate the batch
valid_failure_effect: stop and break the streak

Fixed acceptance contract for every attempt: one new evidence directory and unique
simulation session; exact qualification source/install/bundle/policy/geometry/dependency;
one true independently started and stopped stack; reset epoch `1`; all nine production
phases in order; fresh lossless owner evidence and successful physical outcome; complete
artifact SHA-256 values; and ordered clean shutdown. Any source/config/policy/contract
change restarts the sequence at attempt 1. Only a terminal `VALID/SUCCEEDED/QUALIFIED`
attempt advances the streak.

### CP-GZPY-FULL-RESTART-001

status: INVALID
outcome: NOT_COUNTED
ros_domain_id: `220`
port: `28100`
simulation_session_id: `cp-gzpy-fr-001-full-01`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-001`
command: `run_qualification --batch-id cp-gzpy-fr-001 --lifecycle FULL_RESTART --count 1 --fingerprint f8a2910a945c72fa8f08f889589f52f9944b4382a7d4d27e4c873852a2f08725 --evidence-root /tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-001 --base-domain-id 220 --base-port 28100 --headless`

Terminal review: the stack, controller manager, MoveIt, public scene setup, and Teleop
health all started successfully. Public scene setup returned a successful `READ_BACK`
receipt with exact `1/13/1`; however, the qualification runner still waited for the
removed legacy stdout token `SCENE_SETUP_OK` and timed out before starting workflow.
The run is therefore `INVALID`, not a product failure and not countable. It preserved
complete failure and launch-log hashes, and ordered shutdown passed with return code
zero and no died/fatal process. Manifest SHA-256:
`85b5c72162b7ea878c4b5df6546ed508afc9f632d2ae44baa782eabc596b0df5`.
Per the preregistered rule, this batch stops immediately and attempts 002 through 005
below are permanently unexecuted in this batch.

### CP-GZPY-FULL-RESTART-002

status: PLANNED
outcome: PENDING
batch_invalid_before_start: true
ros_domain_id: `221`
port: `28101`
simulation_session_id: `cp-gzpy-fr-002-full-01`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-002`
command: `run_qualification --batch-id cp-gzpy-fr-002 --lifecycle FULL_RESTART --count 1 --fingerprint f8a2910a945c72fa8f08f889589f52f9944b4382a7d4d27e4c873852a2f08725 --evidence-root /tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-002 --base-domain-id 221 --base-port 28101 --headless`

### CP-GZPY-FULL-RESTART-003

status: PLANNED
outcome: PENDING
batch_invalid_before_start: true
ros_domain_id: `222`
port: `28102`
simulation_session_id: `cp-gzpy-fr-003-full-01`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-003`
command: `run_qualification --batch-id cp-gzpy-fr-003 --lifecycle FULL_RESTART --count 1 --fingerprint f8a2910a945c72fa8f08f889589f52f9944b4382a7d4d27e4c873852a2f08725 --evidence-root /tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-003 --base-domain-id 222 --base-port 28102 --headless`

### CP-GZPY-FULL-RESTART-004

status: PLANNED
outcome: PENDING
batch_invalid_before_start: true
ros_domain_id: `223`
port: `28103`
simulation_session_id: `cp-gzpy-fr-004-full-01`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-004`
command: `run_qualification --batch-id cp-gzpy-fr-004 --lifecycle FULL_RESTART --count 1 --fingerprint f8a2910a945c72fa8f08f889589f52f9944b4382a7d4d27e4c873852a2f08725 --evidence-root /tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-004 --base-domain-id 223 --base-port 28103 --headless`

### CP-GZPY-FULL-RESTART-005

status: PLANNED
outcome: PENDING
batch_invalid_before_start: true
ros_domain_id: `224`
port: `28104`
simulation_session_id: `cp-gzpy-fr-005-full-01`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-005`
command: `run_qualification --batch-id cp-gzpy-fr-005 --lifecycle FULL_RESTART --count 1 --fingerprint f8a2910a945c72fa8f08f889589f52f9944b4382a7d4d27e4c873852a2f08725 --evidence-root /tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-005 --base-domain-id 224 --base-port 28104 --headless`

## CP-GZPY-FULL-RESTART-006 through 010 — replacement fixed-bundle preregistration

batch_status: INVALID
backend: mujoco
lifecycle: FULL_RESTART
supersedes_invalid_batch: `CP-GZPY-FULL-RESTART-001 through 005`
qualification_source_commit: `9830059a4479a5f1490ed59cc071c05e3cdadcc4`
registration_parent_commit: `2810cd2a`
installed_prefix: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/final-candidate-002-install/so101_demo_py`
bundle_sha256: `3beaed4cf9101dc3304dfb8f83ad44198c9c806a9483872fdb290eab7f776b61`
policy_sha256: `aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356`
geometry_sha256: `6dc64c197a82316c4ac856530c6caf5d905ffd2b0ea2778d85d87b9a3e89b235`
mujoco_ros2_control_prefix: `/data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install`
mujoco_ros2_control_gitlink: `738e304551b4ea6db020b466086a13db71b65607`
mujoco_ros2_control_executable_sha256: `9fd047eaae7ed2eff3f49aeb42880f88019ccf84787ecd5183ee5de78d73506e`
required_consecutive_successes: 5
reuse_old_or_invalid_results: false
invalid_effect: stop and invalidate this replacement batch
valid_failure_effect: stop and break the streak

Fixed acceptance contract: each attempt has a new evidence directory, unique ROS domain,
port, and simulation session, plus one independently started/stopped stack. Every record
must bind the exact fixed source/install/bundle/policy/geometry/dependency, reset epoch
`1`, all nine production phases, a fresh lossless owner manifest, successful physical
outcome, complete artifact SHA-256 values, and ordered clean shutdown. Only terminal
`VALID/SUCCEEDED/QUALIFIED` advances the consecutive streak. Any drift, `INVALID`, or
valid failure stops the batch; any source/config/policy/contract change requires another
new batch beginning at one.

### CP-GZPY-FULL-RESTART-006

status: INVALID
outcome: NOT_COUNTED
ros_domain_id: `225`
port: `28105`
simulation_session_id: `cp-gzpy-fr-006-full-01`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-006`
command: `run_qualification --batch-id cp-gzpy-fr-006 --lifecycle FULL_RESTART --count 1 --fingerprint 3beaed4cf9101dc3304dfb8f83ad44198c9c806a9483872fdb290eab7f776b61 --evidence-root /tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-006 --base-domain-id 225 --base-port 28105 --headless`

Terminal review: readiness used the shared scene JSON receipt successfully, the reset
receipt bound epoch `1`, and the production workflow completed through
`remaining_lift`. At `transport`, its lossless execution monitor failed closed with
`EvidenceInvalid: chunk sequence mismatch`; the phase artifact and raw index are
present, so the cause is attributable but the physical run is not valid qualification
evidence. The outer adapter incorrectly selected the earlier generic
`PHASE_EXIT_NONZERO` instead of the final emitted
`TELEOP_WORKFLOW_EVIDENCE_INVALID`; terminal review therefore classifies this attempt
`INVALID`, and a focused RED/GREEN cycle repairs that propagation before any retry.
Ordered shutdown passed with return code zero and no died/fatal process. Manifest
SHA-256: `1722a598c63ef7591e0926a25109d5dbd2b3eda49aee8784af824b2b56f28c57`.
Attempts 007 through 010 are not executed because this batch is invalid.

### CP-GZPY-FULL-RESTART-007

status: PLANNED
outcome: PENDING
batch_invalid_before_start: true
ros_domain_id: `226`
port: `28106`
simulation_session_id: `cp-gzpy-fr-007-full-01`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-007`
command: `run_qualification --batch-id cp-gzpy-fr-007 --lifecycle FULL_RESTART --count 1 --fingerprint 3beaed4cf9101dc3304dfb8f83ad44198c9c806a9483872fdb290eab7f776b61 --evidence-root /tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-007 --base-domain-id 226 --base-port 28106 --headless`

### CP-GZPY-FULL-RESTART-008

status: PLANNED
outcome: PENDING
batch_invalid_before_start: true
ros_domain_id: `227`
port: `28107`
simulation_session_id: `cp-gzpy-fr-008-full-01`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-008`
command: `run_qualification --batch-id cp-gzpy-fr-008 --lifecycle FULL_RESTART --count 1 --fingerprint 3beaed4cf9101dc3304dfb8f83ad44198c9c806a9483872fdb290eab7f776b61 --evidence-root /tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-008 --base-domain-id 227 --base-port 28107 --headless`

### CP-GZPY-FULL-RESTART-009

status: PLANNED
outcome: PENDING
batch_invalid_before_start: true
ros_domain_id: `228`
port: `28108`
simulation_session_id: `cp-gzpy-fr-009-full-01`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-009`
command: `run_qualification --batch-id cp-gzpy-fr-009 --lifecycle FULL_RESTART --count 1 --fingerprint 3beaed4cf9101dc3304dfb8f83ad44198c9c806a9483872fdb290eab7f776b61 --evidence-root /tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-009 --base-domain-id 228 --base-port 28108 --headless`

### CP-GZPY-FULL-RESTART-010

status: PLANNED
outcome: PENDING
batch_invalid_before_start: true
ros_domain_id: `229`
port: `28109`
simulation_session_id: `cp-gzpy-fr-010-full-01`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-010`
command: `run_qualification --batch-id cp-gzpy-fr-010 --lifecycle FULL_RESTART --count 1 --fingerprint 3beaed4cf9101dc3304dfb8f83ad44198c9c806a9483872fdb290eab7f776b61 --evidence-root /tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-010 --base-domain-id 229 --base-port 28109 --headless`

## CP-GZPY-FULL-RESTART-011 through 015 — evidence-classified fixed-bundle preregistration

batch_status: INVALID
backend: mujoco
lifecycle: FULL_RESTART
supersedes_invalid_batches: `[001..005, 006..010]`
qualification_source_commit: `25f9e4b202f069127919649614ea0ff3628c339d`
registration_parent_commit: `2321ede1`
installed_prefix: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/final-candidate-003-install/so101_demo_py`
bundle_sha256: `920e81fea7e2fbcd2800ac847402bd6df9ebaf650f4c6032ecf8ee6f8e910f03`
policy_sha256: `aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356`
geometry_sha256: `6dc64c197a82316c4ac856530c6caf5d905ffd2b0ea2778d85d87b9a3e89b235`
mujoco_ros2_control_prefix: `/data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install`
mujoco_ros2_control_gitlink: `738e304551b4ea6db020b466086a13db71b65607`
mujoco_ros2_control_executable_sha256: `9fd047eaae7ed2eff3f49aeb42880f88019ccf84787ecd5183ee5de78d73506e`
required_consecutive_successes: 5
reuse_old_or_invalid_results: false
invalid_effect: stop and invalidate this batch
valid_failure_effect: stop and break the streak

Fixed acceptance contract: each attempt uses a new evidence directory, unique ROS domain,
port, and simulation session, and independently creates and destroys its complete stack.
Every terminal record must bind the exact fixed source/install/bundle/policy/geometry and
pinned controller executable; prove reset epoch `1`, all nine ordered production phases,
fresh lossless evidence, successful physical outcome, complete artifact hashes, and clean
ordered shutdown. The final specific owner failure code governs evidence classification.
Only `VALID/SUCCEEDED/QUALIFIED` advances the streak; drift, `INVALID`, or a valid failure
stops the batch, and any behavior/config/contract change requires a new batch at one.

### CP-GZPY-FULL-RESTART-011

status: INVALID
outcome: NOT_COUNTED
ros_domain_id: `210`
port: `28110`
simulation_session_id: `cp-gzpy-fr-011-full-01`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-011`
command: `run_qualification --batch-id cp-gzpy-fr-011 --lifecycle FULL_RESTART --count 1 --fingerprint 920e81fea7e2fbcd2800ac847402bd6df9ebaf650f4c6032ecf8ee6f8e910f03 --evidence-root /tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-011 --base-domain-id 210 --base-port 28110 --headless`

Terminal review: the fixed source, installed prefix, bundle, frozen policy, geometry,
and pinned controller executable all matched. Reset completed at epoch `1`, scene setup
succeeded, and the production workflow completed through `remaining_lift`. At
`transport`, the owner correctly surfaced `TELEOP_WORKFLOW_EVIDENCE_INVALID` after the
lossless observer detected `EvidenceInvalid: chunk sequence mismatch`. The first raw
chunk was sequence `4783` for physics steps `23916..23920`, followed by a sequence gap;
the raw index and phase evidence are retained. This is incomplete lossless evidence, so
the attempt is `INVALID` and cannot count. Ordered shutdown passed with no residual
task process. Manifest SHA-256:
`a10bc5668ca225a1855c960ccfbe0f23bb1346921a928473826177205fab6b1d`.
The repeated gap on the `/tmp` evidence volume is traced to synchronous per-chunk file,
directory, and index fsync work at the default 100 chunks/second. Attempts 012 through
015 are canceled before start; a TDD configuration fix requires a new fixed bundle and
new batch.

### CP-GZPY-FULL-RESTART-012

status: PLANNED
outcome: PENDING
batch_invalid_before_start: true
ros_domain_id: `211`
port: `28111`
simulation_session_id: `cp-gzpy-fr-012-full-01`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-012`
command: `run_qualification --batch-id cp-gzpy-fr-012 --lifecycle FULL_RESTART --count 1 --fingerprint 920e81fea7e2fbcd2800ac847402bd6df9ebaf650f4c6032ecf8ee6f8e910f03 --evidence-root /tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-012 --base-domain-id 211 --base-port 28111 --headless`

### CP-GZPY-FULL-RESTART-013

status: PLANNED
outcome: PENDING
batch_invalid_before_start: true
ros_domain_id: `212`
port: `28112`
simulation_session_id: `cp-gzpy-fr-013-full-01`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-013`
command: `run_qualification --batch-id cp-gzpy-fr-013 --lifecycle FULL_RESTART --count 1 --fingerprint 920e81fea7e2fbcd2800ac847402bd6df9ebaf650f4c6032ecf8ee6f8e910f03 --evidence-root /tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-013 --base-domain-id 212 --base-port 28112 --headless`

### CP-GZPY-FULL-RESTART-014

status: PLANNED
outcome: PENDING
batch_invalid_before_start: true
ros_domain_id: `213`
port: `28113`
simulation_session_id: `cp-gzpy-fr-014-full-01`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-014`
command: `run_qualification --batch-id cp-gzpy-fr-014 --lifecycle FULL_RESTART --count 1 --fingerprint 920e81fea7e2fbcd2800ac847402bd6df9ebaf650f4c6032ecf8ee6f8e910f03 --evidence-root /tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-014 --base-domain-id 213 --base-port 28113 --headless`

### CP-GZPY-FULL-RESTART-015

status: PLANNED
outcome: PENDING
batch_invalid_before_start: true
ros_domain_id: `214`
port: `28114`
simulation_session_id: `cp-gzpy-fr-015-full-01`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-015`
command: `run_qualification --batch-id cp-gzpy-fr-015 --lifecycle FULL_RESTART --count 1 --fingerprint 920e81fea7e2fbcd2800ac847402bd6df9ebaf650f4c6032ecf8ee6f8e910f03 --evidence-root /tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-015 --base-domain-id 214 --base-port 28114 --headless`

## CP-GZPY-FULL-RESTART-016 through 020 — durable-evidence fixed-bundle preregistration

batch_status: INVALID
backend: mujoco
lifecycle: FULL_RESTART
supersedes_invalid_batches: `[001..005, 006..010, 011..015]`
qualification_source_commit: `86ceb656714a308288098c41f0d2184c99ced9dd`
registration_parent_commit: `86ceb656714a308288098c41f0d2184c99ced9dd`
installed_prefix: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/final-candidate-004-install/so101_demo_py`
bundle_sha256: `4d1a717e780df30180d2fca018d7c31e838bf9d1de31700b953e7551daeb816a`
policy_sha256: `aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356`
geometry_sha256: `6dc64c197a82316c4ac856530c6caf5d905ffd2b0ea2778d85d87b9a3e89b235`
mujoco_ros2_control_prefix: `/data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install`
mujoco_ros2_control_gitlink: `738e304551b4ea6db020b466086a13db71b65607`
mujoco_ros2_control_executable_sha256: `9fd047eaae7ed2eff3f49aeb42880f88019ccf84787ecd5183ee5de78d73506e`
physics_step_buffer_capacity: 5000
physics_step_chunk_size: 50
durable_chunk_rate_hz: 10
required_consecutive_successes: 5
reuse_old_or_invalid_results: false
invalid_effect: stop and invalidate this batch
valid_failure_effect: stop and break the streak

Fixed acceptance contract: every attempt has a new evidence directory, unique ROS domain,
port, simulation session, and independently created/destroyed stack. Every terminal record
must bind the exact fixed source/install/bundle/policy/geometry/pinned controller and the
explicit lossless chunk configuration; prove reset epoch `1`, all nine ordered production
phases, fresh gap-free raw physics-step evidence, successful physical outcome, complete
artifact SHA-256 values, and clean ordered shutdown. Only terminal
`VALID/SUCCEEDED/QUALIFIED` advances the streak. Any drift, `INVALID`, or valid failure
stops the batch; any behavior/config/policy/contract change requires a new batch at one.

### CP-GZPY-FULL-RESTART-016

status: INVALID
outcome: NOT_COUNTED
ros_domain_id: `200`
port: `28115`
simulation_session_id: `cp-gzpy-fr-016-full-01`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-016`
command: `run_qualification --batch-id cp-gzpy-fr-016 --lifecycle FULL_RESTART --count 1 --fingerprint 4d1a717e780df30180d2fca018d7c31e838bf9d1de31700b953e7551daeb816a --evidence-root /tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-016 --base-domain-id 200 --base-port 28115 --headless`

Terminal review: fixed source/install/bundle/policy/geometry/controller provenance and the
installed `5000/50` lossless chunk configuration matched. The observer retained twelve
strictly consecutive chunks `483..494`, each with fifty consecutive samples, eliminating
the prior sequence-gap failure. A durable chunk checkpoint nevertheless took about
`0.532s`, longer than the independent atomic snapshot freshness bound of `0.500s` on the
same single-threaded ROS executor. The monitor correctly canceled waypoint 1 for stale
evidence, while the hazard-only cancellation recorder then failed closed with
`EvidenceInvalid: cancellation request has no hazard latch`; the owner surfaced
`TELEOP_WORKFLOW_EVIDENCE_INVALID`. This is incomplete physical evidence and therefore
`INVALID`, not a policy failure. Ordered shutdown passed. Manifest SHA-256:
`48d29b3309ff890dc10d4ebbcdfc29701379a9f0f06e32576bf7b79640b6b49b`.
Attempts 017 through 020 are canceled before start. The next TDD change must decouple
durable checkpoint latency from ROS safety/snapshot callbacks and requires a new bundle.

### CP-GZPY-FULL-RESTART-017

status: PLANNED
outcome: PENDING
batch_invalid_before_start: true
ros_domain_id: `201`
port: `28116`
simulation_session_id: `cp-gzpy-fr-017-full-01`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-017`
command: `run_qualification --batch-id cp-gzpy-fr-017 --lifecycle FULL_RESTART --count 1 --fingerprint 4d1a717e780df30180d2fca018d7c31e838bf9d1de31700b953e7551daeb816a --evidence-root /tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-017 --base-domain-id 201 --base-port 28116 --headless`

### CP-GZPY-FULL-RESTART-018

status: PLANNED
outcome: PENDING
batch_invalid_before_start: true
ros_domain_id: `202`
port: `28117`
simulation_session_id: `cp-gzpy-fr-018-full-01`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-018`
command: `run_qualification --batch-id cp-gzpy-fr-018 --lifecycle FULL_RESTART --count 1 --fingerprint 4d1a717e780df30180d2fca018d7c31e838bf9d1de31700b953e7551daeb816a --evidence-root /tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-018 --base-domain-id 202 --base-port 28117 --headless`

### CP-GZPY-FULL-RESTART-019

status: PLANNED
outcome: PENDING
batch_invalid_before_start: true
ros_domain_id: `203`
port: `28118`
simulation_session_id: `cp-gzpy-fr-019-full-01`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-019`
command: `run_qualification --batch-id cp-gzpy-fr-019 --lifecycle FULL_RESTART --count 1 --fingerprint 4d1a717e780df30180d2fca018d7c31e838bf9d1de31700b953e7551daeb816a --evidence-root /tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-019 --base-domain-id 203 --base-port 28118 --headless`

### CP-GZPY-FULL-RESTART-020

status: PLANNED
outcome: PENDING
batch_invalid_before_start: true
ros_domain_id: `204`
port: `28119`
simulation_session_id: `cp-gzpy-fr-020-full-01`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-020`
command: `run_qualification --batch-id cp-gzpy-fr-020 --lifecycle FULL_RESTART --count 1 --fingerprint 4d1a717e780df30180d2fca018d7c31e838bf9d1de31700b953e7551daeb816a --evidence-root /tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-020 --base-domain-id 204 --base-port 28119 --headless`

## CP-GZPY-FULL-RESTART-021 through 025 — ordered-async-evidence fixed-bundle preregistration

batch_status: QUALIFIED
backend: mujoco
lifecycle: FULL_RESTART
supersedes_invalid_batches: `[001..005, 006..010, 011..015, 016..020]`
qualification_source_commit: `213ac0da3b4f2a756c2c4e66e8e6c28af9e2168a`
registration_parent_commit: `213ac0da3b4f2a756c2c4e66e8e6c28af9e2168a`
installed_prefix: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/final-candidate-005-install/so101_demo_py`
bundle_sha256: `438f968141ff3b3999799b8dc06d36c386950eed335a82e314a2fe2e050119dd`
policy_sha256: `aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356`
geometry_sha256: `6dc64c197a82316c4ac856530c6caf5d905ffd2b0ea2778d85d87b9a3e89b235`
mujoco_ros2_control_prefix: `/data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install`
mujoco_ros2_control_gitlink: `738e304551b4ea6db020b466086a13db71b65607`
mujoco_ros2_control_executable_sha256: `9fd047eaae7ed2eff3f49aeb42880f88019ccf84787ecd5183ee5de78d73506e`
physics_step_buffer_capacity: 5000
physics_step_chunk_size: 50
ordered_async_persistence: true
terminal_drain_required: true
required_consecutive_successes: 5
reuse_old_or_invalid_results: false
invalid_effect: stop and invalidate this batch
valid_failure_effect: stop and break the streak

Fixed acceptance contract: every attempt has a new evidence directory, unique ROS domain,
port, simulation session, and independently created/destroyed stack. Every terminal record
must bind the exact fixed source/install/bundle/policy/geometry/pinned controller and
lossless persistence configuration; prove reset epoch `1`, all nine ordered production
phases, fresh gap-free raw physics-step evidence durably drained before terminal success,
successful physical outcome, complete artifact SHA-256 values, and clean ordered shutdown.
Only terminal `VALID/SUCCEEDED/QUALIFIED` advances the streak. Any drift, `INVALID`, or
valid failure stops the batch; any behavior/config/policy/contract change requires a new
batch at one.

### CP-GZPY-FULL-RESTART-021

status: VALID
outcome: SUCCEEDED
ros_domain_id: `205`
port: `28120`
simulation_session_id: `cp-gzpy-fr-021-full-01`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-021`
command: `run_qualification --batch-id cp-gzpy-fr-021 --lifecycle FULL_RESTART --count 1 --fingerprint 438f968141ff3b3999799b8dc06d36c386950eed335a82e314a2fe2e050119dd --evidence-root /tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-021 --base-domain-id 205 --base-port 28120 --headless`

Terminal review: independent `verify-batch` returned `QUALIFIED`. Exact fixed provenance,
reset epoch `1`, all nine ordered phases, workflow success, synchronized unattached world
object, intended support contact, null primary failure, complete artifact hashes, and
ordered clean shutdown all passed. The lossless raw index is `COMPLETE` with outcome
`PHYSICAL_TRANSPORT_SUCCESS`: 82 consecutive fifty-step chunks `482..563`, physics
steps `24101..28200`, twelve ordered boundaries, and no invalid reason. Manifest
SHA-256: `25dd6a49bebdb6b87729ce1b707f8c65562ecf32f3c781696900d29e0477464a`.

### CP-GZPY-FULL-RESTART-022

status: VALID
outcome: SUCCEEDED
ros_domain_id: `206`
port: `28121`
simulation_session_id: `cp-gzpy-fr-022-full-01`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-022`
command: `run_qualification --batch-id cp-gzpy-fr-022 --lifecycle FULL_RESTART --count 1 --fingerprint 438f968141ff3b3999799b8dc06d36c386950eed335a82e314a2fe2e050119dd --evidence-root /tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-022 --base-domain-id 206 --base-port 28121 --headless`

Terminal review: independent `verify-batch` returned `QUALIFIED`; exact provenance,
reset epoch `1`, nine phases, physical success, artifact hashes, and clean shutdown all
passed. The lossless raw index is `COMPLETE/PHYSICAL_TRANSPORT_SUCCESS` with 85
consecutive chunks `489..573`, physics steps `24451..28700`, twelve boundaries, and no
invalid reason. Manifest SHA-256:
`fc3e1a12c19679dd63f1d839a8af1e6cec16a4e90780135a2fae4b93adecfc17`.

### CP-GZPY-FULL-RESTART-023

status: VALID
outcome: SUCCEEDED
ros_domain_id: `207`
port: `28122`
simulation_session_id: `cp-gzpy-fr-023-full-01`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-023`
command: `run_qualification --batch-id cp-gzpy-fr-023 --lifecycle FULL_RESTART --count 1 --fingerprint 438f968141ff3b3999799b8dc06d36c386950eed335a82e314a2fe2e050119dd --evidence-root /tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-023 --base-domain-id 207 --base-port 28122 --headless`

Terminal review: independent `verify-batch` returned `QUALIFIED`; all fixed provenance,
reset, nine-phase workflow, physical outcome, artifact hashes, and shutdown gates passed.
The raw index is `COMPLETE/PHYSICAL_TRANSPORT_SUCCESS` with 82 consecutive chunks
`463..544`, physics steps `23151..27250`, twelve boundaries, and no invalid reason.
Manifest SHA-256:
`0da61cc8b4c16e79691b4e7a69078e679a6c93fa8cd676b50300954313bb8fa5`.

### CP-GZPY-FULL-RESTART-024

status: VALID
outcome: SUCCEEDED
ros_domain_id: `208`
port: `28123`
simulation_session_id: `cp-gzpy-fr-024-full-01`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-024`
command: `run_qualification --batch-id cp-gzpy-fr-024 --lifecycle FULL_RESTART --count 1 --fingerprint 438f968141ff3b3999799b8dc06d36c386950eed335a82e314a2fe2e050119dd --evidence-root /tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-024 --base-domain-id 208 --base-port 28123 --headless`

Terminal review: independent `verify-batch` returned `QUALIFIED`; all fixed provenance,
reset, workflow, physical, artifact, and shutdown gates passed. The raw index is
`COMPLETE/PHYSICAL_TRANSPORT_SUCCESS` with 82 consecutive chunks `492..573`, physics
steps `24601..28700`, twelve boundaries, and no invalid reason. Manifest SHA-256:
`b14c9338998a27d6e09848757ac0956bc3602a048afe3a11f0d4440f012f2766`.

### CP-GZPY-FULL-RESTART-025

status: VALID
outcome: SUCCEEDED
ros_domain_id: `209`
port: `28124`
simulation_session_id: `cp-gzpy-fr-025-full-01`
evidence_dir: `/tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-025`
command: `run_qualification --batch-id cp-gzpy-fr-025 --lifecycle FULL_RESTART --count 1 --fingerprint 438f968141ff3b3999799b8dc06d36c386950eed335a82e314a2fe2e050119dd --evidence-root /tmp/so101-debug-gazebo-python-capabilities-boWK6J/qualification/cp-gzpy-fr-025 --base-domain-id 209 --base-port 28124 --headless`

Terminal review: independent `verify-batch` returned `QUALIFIED`; all fixed provenance,
reset, workflow, physical, artifact, and shutdown gates passed. The raw index is
`COMPLETE/PHYSICAL_TRANSPORT_SUCCESS` with 82 consecutive chunks `492..573`, physics
steps `24601..28700`, twelve boundaries, and no invalid reason. Manifest SHA-256:
`ddfaf9e9df89308d9441ac4a87ff8b0961f61fcdcae606be4c5c015e27276246`.

Batch terminal review: experiments `cp-gzpy-fr-021-01` through
`cp-gzpy-fr-025-01` are five consecutive, independently started and stopped
`VALID/SUCCEEDED` FULL_RESTART runs on exact source
`213ac0da3b4f2a756c2c4e66e8e6c28af9e2168a`, installed bundle
`438f968141ff3b3999799b8dc06d36c386950eed335a82e314a2fe2e050119dd`, and frozen
policy `aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356`.
Every attempt independently returned `QUALIFIED`, reset epoch `1`, all nine phases,
successful physical outcome, complete lossless raw evidence, artifact hashes, and clean
ordered shutdown. No old or invalid result contributes to this streak.
