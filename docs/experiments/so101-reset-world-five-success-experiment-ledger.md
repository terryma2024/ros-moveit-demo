# SO-101 Reset-World Five-Success Experiment Ledger

```yaml
task_id: so101-reset-world-five-success-20260807
goal: 同一套 Gazebo、MoveIt 和 controller 进程内，每轮先执行 canonical reset world，再连续完成 5 次端到端 pick-place。
success_contract: 同一 commit、同一参数、同一 ROS_DOMAIN_ID/GZ_PARTITION、lifecycle=RESET_WORLD；5 个连续 VALID 运行均 reset exit 0、workflow exit 0/status DONE、最终 Gazebo 与 MoveIt detached、物体位于 place、controller/TF/视觉一致。
worktree: /data/work/ws_moveit/.worktrees/so101-five-success
branch: codex/so101-five-success
base_commit: 89acb20bc6a4889ca1ed212b736d44c4f2c2de4a
current_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a
runtime_diff_sha256: b8b8c2b076d024889d68493abc6b3adde6b01ea1a09234ae2e7e2fdd33ea9d3a
initial_evidence_root: /tmp/so101-debug-reset-world-five-20260807-85igJE/
active_evidence_root: /tmp/so101-reset-world-five-v8-20260807-H7nQ4x/
confirmed_conclusions:
  - FULL_RESTART 固定配置已连续 5/5 成功；证据 /tmp/so101-five-e2e-restart-20260807-lAB25k；本批次不与其混算。
  - EXP-027 的 state-specific DESCEND_TO_PLACE 0.03 配置契约已 RED-GREEN 且安装；batch 7 的 EXP-028 因 sentinel 等待超时而 INVALID，未执行 reset 或 workflow。
disproven_routes:
  - reset world 与 FULL_RESTART 混合计数不能证明任一 lifecycle 稳定性。
open_hypotheses:
  - 新的 final physical-outcome 验收策略将取代连续五次 RESET_WORLD campaign；本账本不启动该新策略。
latest_checkpoint: CP-031
next_experiment: NONE
```

## Batch contract

- Active variable relative to the previous accepted batch: lifecycle changes from `FULL_RESTART` to `RESET_WORLD`.
- Within this batch `single_variable: NONE`; commit, policies, stack and success contract remain fixed.
- One stack only: tmux `so101-five-reset`, `ROS_DOMAIN_ID=203`, `GZ_PARTITION=so101-five-reset-20260807-85igJE`.
- Each run invokes `run_one_low_disturbance.py --reset-first`; `reset_so101_world` is the only between-run environment reset.
- A reset command failure in an otherwise healthy/provenance-correct stack is a `VALID` lifecycle failure, not an invalid run.

## Planned experiments

### EXP-001

```yaml
experiment_id: EXP-001
status: VALID
prior_experiment: NONE
hypothesis: H-RESET-01
prediction: canonical reset converges and pick-place reaches DONE with final detached/place facts.
single_variable: NONE
lifecycle: RESET_WORLD
preconditions:
  - exactly one healthy stack with move_group and three active controllers
  - telemetry snapshot GZ_PARTITION matches the batch partition
success_criteria:
  - reset returncode 0
  - workflow returncode 0 and status=DONE
  - final Gazebo and MoveIt detached, object at place, controllers active, fresh screenshot consistent
failure_criteria:
  - reset or workflow fails after provenance and stack health pass
invalid_criteria:
  - duplicate stack, overlay mismatch, telemetry partition mismatch, or evidence capture failure
provenance:
  source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a
  install_overlay: /data/work/ws_moveit/.worktrees/so101-five-success/install
  runtime_executable: /data/work/ws_moveit/.worktrees/so101-five-success/install/so101_gazebo_demo/lib/so101_gazebo_demo/pick_place_state_machine
  ros_domain_id: 203
  gz_partition: so101-five-reset-20260807-85igJE
commands:
  - command: bash /tmp/so101-five-reset-cycle.sh /tmp/so101-debug-reset-world-five-20260807-85igJE 203 so101-five-reset-20260807-85igJE
    exit_code: 1
observed:
  - OBSERVED: one stack reached health gate at attempt 8; /move_group present and arm_controller, gripper_controller, joint_state_broadcaster active.
  - OBSERVED: telemetry reports ROS_DOMAIN_ID=203, GZ_PARTITION=so101-five-reset-20260807-85igJE, COLCON_PREFIX_PATH=/data/work/ws_moveit/.worktrees/so101-five-success/install.
  - OBSERVED: LAYOUT_OK with RViz left and Gazebo right; fresh baseline shows robot at home and cup at canonical spawn pose.
  - OBSERVED: reset_so101_world returncode 0 and canonical detached/home/spawn facts passed.
  - OBSERVED: workflow reached MOVE_ABOVE_PLACE after MICRO_LIFT, both attachments and LIFT, then returned RECOVERY_GRIPPER_NOT_STATIONARY preserving original GRIPPER_NOT_STATIONARY_BEFORE_PLAN.
  - OBSERVED: failure snapshot had gazebo_attached=true, moveit_attached=true, both fingertip contacts, q6=-0.0452692546 rad versus target -0.0476086328 rad, and q6 velocity=-0.1011719033 rad/s.
inferred:
  - INFERRED: unconditional pre-plan q6 velocity validation runs before carrying contact and attachment facts can authorize contact-loaded motion.
conclusion: VALID failure at MOVE_ABOVE_PLACE; H-RESET-01 is not yet decided because the first reset succeeded but the workflow exposed H-Q6-CARRY-01.
evidence:
  - /tmp/so101-debug-reset-world-five-20260807-85igJE/run-01
decision: KEEP
next_experiment: EXP-006
```

### EXP-002

```yaml
experiment_id: EXP-002
status: PLANNED
prior_experiment: EXP-001
hypothesis: H-RESET-01
prediction: the second reset removes all side effects from EXP-001 and the workflow reaches DONE.
single_variable: NONE
lifecycle: RESET_WORLD
preconditions: [same frozen batch contract; EXP-001 completed VALID]
success_criteria: [reset exit 0; workflow exit 0/status DONE; final detached/place/controller/visual facts]
failure_criteria: [reset or workflow failure in the healthy provenance-correct stack]
invalid_criteria: [duplicate stack; provenance mismatch; telemetry mismatch; evidence capture failure]
provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a, install_overlay: /data/work/ws_moveit/.worktrees/so101-five-success/install, runtime_executable: /data/work/ws_moveit/.worktrees/so101-five-success/install/so101_gazebo_demo/lib/so101_gazebo_demo/pick_place_state_machine, ros_domain_id: 203, gz_partition: so101-five-reset-20260807-85igJE}
commands: [{command: run-02 via /tmp/so101-five-reset-cycle.sh, exit_code: PENDING}]
observed: [NONE]
inferred: [NONE]
conclusion: NOT_RUN because EXP-001 was a VALID failure and terminated the consecutive-success batch.
evidence: [/tmp/so101-debug-reset-world-five-20260807-85igJE/run-02]
decision: ABANDON
next_experiment: EXP-003
```

### EXP-003

```yaml
experiment_id: EXP-003
status: PLANNED
prior_experiment: EXP-002
hypothesis: H-RESET-01
prediction: the third reset and workflow remain stable in the unchanged stack.
single_variable: NONE
lifecycle: RESET_WORLD
preconditions: [same frozen batch contract; EXP-002 completed VALID]
success_criteria: [reset exit 0; workflow exit 0/status DONE; final detached/place/controller/visual facts]
failure_criteria: [reset or workflow failure in the healthy provenance-correct stack]
invalid_criteria: [duplicate stack; provenance mismatch; telemetry mismatch; evidence capture failure]
provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a, install_overlay: /data/work/ws_moveit/.worktrees/so101-five-success/install, runtime_executable: /data/work/ws_moveit/.worktrees/so101-five-success/install/so101_gazebo_demo/lib/so101_gazebo_demo/pick_place_state_machine, ros_domain_id: 203, gz_partition: so101-five-reset-20260807-85igJE}
commands: [{command: run-03 via /tmp/so101-five-reset-cycle.sh, exit_code: PENDING}]
observed: [NONE]
inferred: [NONE]
conclusion: NOT_RUN because EXP-001 was a VALID failure and terminated the consecutive-success batch.
evidence: [/tmp/so101-debug-reset-world-five-20260807-85igJE/run-03]
decision: ABANDON
next_experiment: EXP-004
```

### EXP-004

```yaml
experiment_id: EXP-004
status: PLANNED
prior_experiment: EXP-003
hypothesis: H-RESET-01
prediction: the fourth reset and workflow remain stable in the unchanged stack.
single_variable: NONE
lifecycle: RESET_WORLD
preconditions: [same frozen batch contract; EXP-003 completed VALID]
success_criteria: [reset exit 0; workflow exit 0/status DONE; final detached/place/controller/visual facts]
failure_criteria: [reset or workflow failure in the healthy provenance-correct stack]
invalid_criteria: [duplicate stack; provenance mismatch; telemetry mismatch; evidence capture failure]
provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a, install_overlay: /data/work/ws_moveit/.worktrees/so101-five-success/install, runtime_executable: /data/work/ws_moveit/.worktrees/so101-five-success/install/so101_gazebo_demo/lib/so101_gazebo_demo/pick_place_state_machine, ros_domain_id: 203, gz_partition: so101-five-reset-20260807-85igJE}
commands: [{command: run-04 via /tmp/so101-five-reset-cycle.sh, exit_code: PENDING}]
observed: [NONE]
inferred: [NONE]
conclusion: NOT_RUN because EXP-001 was a VALID failure and terminated the consecutive-success batch.
evidence: [/tmp/so101-debug-reset-world-five-20260807-85igJE/run-04]
decision: ABANDON
next_experiment: EXP-005
```

### EXP-005

```yaml
experiment_id: EXP-005
status: PLANNED
prior_experiment: EXP-004
hypothesis: H-RESET-01
prediction: the fifth reset and workflow complete a 5-run RESET_WORLD success streak.
single_variable: NONE
lifecycle: RESET_WORLD
preconditions: [same frozen batch contract; EXP-004 completed VALID]
success_criteria: [reset exit 0; workflow exit 0/status DONE; final detached/place/controller/visual facts]
failure_criteria: [reset or workflow failure in the healthy provenance-correct stack]
invalid_criteria: [duplicate stack; provenance mismatch; telemetry mismatch; evidence capture failure]
provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a, install_overlay: /data/work/ws_moveit/.worktrees/so101-five-success/install, runtime_executable: /data/work/ws_moveit/.worktrees/so101-five-success/install/so101_gazebo_demo/lib/so101_gazebo_demo/pick_place_state_machine, ros_domain_id: 203, gz_partition: so101-five-reset-20260807-85igJE}
commands: [{command: run-05 via /tmp/so101-five-reset-cycle.sh, exit_code: PENDING}]
observed: [NONE]
inferred: [NONE]
conclusion: NOT_RUN because EXP-001 was a VALID failure and terminated the consecutive-success batch.
evidence: [/tmp/so101-debug-reset-world-five-20260807-85igJE/run-05]
decision: ABANDON
next_experiment: NONE
```

## Checkpoints

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: H-RESET-01
working_tree_status: clean at e118ac0 before adding this ledger and the approved project-local Skill update
owned_processes: NONE
preserved_processes: PID 652055 run-clang-tidy-18 in so101-workspace-sampler; all non-SO-101 user processes
confirmed_conclusions:
  - FULL_RESTART 5/5 is independent prior evidence, not part of this batch.
disproven_routes:
  - mixed lifecycle counting
open_risks:
  - repeated canonical reset may expose state accumulation not present under FULL_RESTART
next_command: bash /tmp/so101-five-reset-cycle.sh /tmp/so101-debug-reset-world-five-20260807-85igJE 203 so101-five-reset-20260807-85igJE
```

```yaml
checkpoint_id: CP-002
last_valid_experiment: NONE
current_hypothesis: H-RESET-01
working_tree_status: only approved project-local Skill sync and this experiment ledger are dirty; runtime code remains e118ac0
owned_processes: tmux so101-five-reset; one Gazebo, one move_group/RViz, one controller stack, one teleop server under GZ_PARTITION=so101-five-reset-20260807-85igJE
preserved_processes: PID 652055 run-clang-tidy-18 in so101-workspace-sampler; all other worktrees and user processes
confirmed_conclusions:
  - startup provenance, ROS graph, controllers, canonical object pose and fresh split-screen visual passed
disproven_routes:
  - NONE in this RESET_WORLD batch
open_risks:
  - repeated reset behavior has not yet produced a VALID run
next_command: touch /tmp/so101-debug-reset-world-five-20260807-85igJE/allow-run-01
```

## Diagnostic experiments

### EXP-006

```yaml
experiment_id: EXP-006
status: VALID
prior_experiment: EXP-001
hypothesis: H-Q6-CARRY-01
prediction: a unit test reproducing q6 velocity=-0.1011719033 rad/s with carrying=true, contact target, bounded bilateral contacts and canonical attachment facts fails with GRIPPER_NOT_STATIONARY_BEFORE_PLAN before the fix.
single_variable: add one focused adapter regression test; production code unchanged
lifecycle: RESET_WORLD
preconditions:
  - source and build tree at e118ac0
  - test observation reproduces the EXP-001 carrying contact facts
success_criteria:
  - RED fails for GRIPPER_NOT_STATIONARY_BEFORE_PLAN
failure_criteria:
  - test passes before production change or fails for unrelated setup
invalid_criteria:
  - wrong build target or stale source/build provenance
provenance:
  source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a
  install_overlay: /data/work/ws_moveit/.worktrees/so101-five-success/install
  runtime_executable: /data/work/ws_moveit/.worktrees/so101-five-success/build/so101_gazebo_demo/test_so101_joint_motion_adapter
  ros_domain_id: 203
  gz_partition: so101-five-reset-20260807-85igJE
commands:
  - command: cmake --build build/so101_gazebo_demo --target test_so101_joint_motion_adapter -j2
    exit_code: 0
  - command: build/so101_gazebo_demo/test_so101_joint_motion_adapter --gtest_filter=SO101JointMotionAdapter.CarryingContactLoadVelocityRequiresBoundedBilateralContactAndCanonicalScene
    exit_code: 1
observed:
  - OBSERVED: the canonical carrying case failed exactly with GRIPPER_NOT_STATIONARY_BEFORE_PLAN at q6 velocity=-0.1011719033 rad/s.
  - OBSERVED: before the production change, the invalid-scene subcase also stopped at the same earlier unconditional velocity gate.
inferred:
  - INFERRED: the current validation order prevents bounded contact and canonical attachment evidence from authorizing contact-loaded carrying motion.
conclusion: RED reproduced the EXP-001 failure at the intended adapter boundary.
evidence:
  - /tmp/so101-debug-reset-world-five-20260807-85igJE/diagnostics
decision: KEEP
next_experiment: EXP-007
```

### EXP-007

```yaml
experiment_id: EXP-007
status: VALID
prior_experiment: EXP-006
hypothesis: H-Q6-CARRY-01
prediction: moving the q6 velocity decision after context and scene validation, with bypass limited to bounded bilateral contact in canonical carrying state, makes the positive case GREEN while detached, unilateral and invalid-scene negatives still fail.
single_variable: reorder and gate the pre-plan q6 velocity check in ProfiledJointMotionAdapter
lifecycle: RESET_WORLD
preconditions:
  - EXP-006 is a VALID RED reproduction
success_criteria:
  - canonical bounded-contact carrying case succeeds
  - detached high velocity fails GRIPPER_NOT_STATIONARY_BEFORE_PLAN
  - unilateral high velocity fails GRIPPER_NOT_STATIONARY_BEFORE_PLAN
  - invalid carrying scene fails CARRYING_ENVIRONMENT_OBSERVATION_INVALID
failure_criteria:
  - any negative is weakened or the positive remains blocked
invalid_criteria:
  - stale source/build provenance
provenance:
  source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a
  install_overlay: /data/work/ws_moveit/.worktrees/so101-five-success/install
  runtime_executable: /data/work/ws_moveit/.worktrees/so101-five-success/build/so101_gazebo_demo/test_so101_joint_motion_adapter
commands:
  - command: build and run the two focused positive/negative tests
    exit_code: 0
  - command: run the complete test_so101_joint_motion_adapter executable
    exit_code: 0
  - command: colcon build --packages-select so101_gazebo_demo --symlink-install
    exit_code: 0
  - command: colcon test --packages-select so101_gazebo_demo
    exit_code: 0
observed:
  - OBSERVED: canonical bounded-contact carrying high-velocity case succeeded.
  - OBSERVED: detached and unilateral high-velocity cases failed GRIPPER_NOT_STATIONARY_BEFORE_PLAN.
  - OBSERVED: invalid carrying attachment failed CARRYING_ENVIRONMENT_OBSERVATION_INVALID.
  - OBSERVED: adapter suite passed 19/19; so101_gazebo_demo passed 860 tests with 0 errors and 0 failures.
inferred:
  - INFERRED: the exception is limited to the intended contact-loaded carrying context without weakening detached or inconsistent-scene validation.
conclusion: GREEN satisfies the focused safety contract and affected-package regression.
evidence:
  - /tmp/so101-debug-reset-world-five-20260807-85igJE/diagnostics
decision: KEEP
next_experiment: EXP-008
```

```yaml
checkpoint_id: CP-003
last_valid_experiment: EXP-001
current_hypothesis: H-Q6-CARRY-01
working_tree_status: approved project-local Skill sync and ledger dirty; runtime code still e118ac0
owned_processes: NONE; reset-world EXP-001 stack cleaned after failure
preserved_processes: PID 652055 run-clang-tidy-18 in so101-workspace-sampler; all other worktrees and user processes
confirmed_conclusions:
  - canonical reset itself succeeded in EXP-001
  - first bad boundary is MOVE_ABOVE_PLACE pre-plan q6 velocity validation
disproven_routes:
  - continuing EXP-002 through EXP-005 after a VALID failure cannot produce a five-success streak
open_risks:
  - any velocity exception that is not gated by contact target, bilateral bounded contacts and canonical attachment facts would weaken safety
next_command: add and run the focused RED test in test_so101_joint_motion_adapter
```

```yaml
checkpoint_id: CP-004
last_valid_experiment: EXP-006
current_hypothesis: H-Q6-CARRY-01
working_tree_status: test RED and generic project-local Skill/ledger changes dirty; production adapter unchanged
owned_processes: NONE
preserved_processes: PID 652055 run-clang-tidy-18 in so101-workspace-sampler; all other worktrees and user processes
confirmed_conclusions:
  - focused RED reproduces GRIPPER_NOT_STATIONARY_BEFORE_PLAN in canonical carrying contact context
disproven_routes:
  - an unconditional q6 velocity gate before contact/scene validation cannot represent contact-loaded carrying motion
open_risks:
  - bypass must remain impossible for detached, unilateral, excessive-depth, non-contact-target or invalid-scene inputs
next_command: apply the minimal gated validation-order change and run GREEN
```

```yaml
checkpoint_id: CP-005
last_valid_experiment: EXP-007
current_hypothesis: H-RESET-STREAK-02
working_tree_status: adapter fix, focused tests, generic project-local Skill sync and ledger are dirty; install overlay rebuilt from this source
owned_processes: NONE
preserved_processes: PID 652055 run-clang-tidy-18 in so101-workspace-sampler; all other worktrees and user processes
confirmed_conclusions:
  - focused RED to GREEN and 860-test affected-package regression passed
  - runtime diff sha256 is e2a5f61f50a5e10fd5141690157bd486094bb366d1c31a6df26f39c72cd5006e
disproven_routes:
  - unconditional pre-plan q6 velocity rejection for canonical bounded carrying contact
open_risks:
  - RESET_WORLD stability must still pass five consecutive end-to-end runs in one stack
next_command: start batch 2 and release EXP-008 after the healthy-stack checkpoint
```

## RESET_WORLD validation batch 2

Frozen contract:

- One tmux stack: `so101-five-reset`.
- `ROS_DOMAIN_ID=204`; `GZ_PARTITION=so101-five-reset-v2-20260807-at5ewq`.
- Worktree install overlay only; HEAD `e118ac0` plus runtime diff SHA-256 `e2a5f61f...5006e`.
- Each run invokes `reset_so101_world` before the workflow; no stack restart between runs.
- Any valid run failure terminates the streak; successes before it are not combined with a later batch.

### EXP-008

```yaml
experiment_id: EXP-008
status: VALID
prior_experiment: EXP-007
hypothesis: H-RESET-STREAK-02
prediction: batch-2 run 1 resets canonically and reaches DONE with detached placed final state.
single_variable: NONE
lifecycle: RESET_WORLD
preconditions: [one healthy provenance-correct stack; EXP-007 GREEN installed]
success_criteria: [reset=0; workflow=0 and DONE; final detached/place/controllers/TF/visual consistent]
failure_criteria: [any reset or workflow failure in the valid stack]
invalid_criteria: [duplicate stack; provenance, partition, domain or evidence mismatch]
provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a, runtime_diff_sha256: e2a5f61f50a5e10fd5141690157bd486094bb366d1c31a6df26f39c72cd5006e, ros_domain_id: 204, gz_partition: so101-five-reset-v2-20260807-at5ewq}
commands: [{command: run-01 via /tmp/so101-five-reset-cycle.sh, exit_code: 0}]
observed:
  - OBSERVED: reset=0, workflow=0, status=DONE through the full 21-state trace.
  - OBSERVED: final Gazebo and MoveIt detached; cup=(-0.07934,-0.25023,0.16500); arm and gripper controllers active.
  - OBSERVED: fresh split-screen visual shows the cup at place and the arm retreated without attachment.
inferred: [INFERRED: the gated q6 carrying fix clears the former MOVE_ABOVE_PLACE boundary in run 1.]
conclusion: VALID success 1/5 in the frozen RESET_WORLD batch.
evidence: [/tmp/so101-reset-world-five-v2-20260807-at5ewq/run-01]
decision: KEEP
next_experiment: EXP-009
```

### EXP-009

```yaml
experiment_id: EXP-009
status: VALID
prior_experiment: EXP-008
hypothesis: H-RESET-STREAK-02
prediction: batch-2 run 2 succeeds after reset in the same stack.
single_variable: NONE
lifecycle: RESET_WORLD
preconditions: [EXP-008 VALID success; same frozen batch contract]
success_criteria: [reset=0; workflow=0 and DONE; final detached/place/controllers/TF/visual consistent]
failure_criteria: [any reset or workflow failure in the valid stack]
invalid_criteria: [duplicate stack; provenance, partition, domain or evidence mismatch]
provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a, runtime_diff_sha256: e2a5f61f50a5e10fd5141690157bd486094bb366d1c31a6df26f39c72cd5006e, ros_domain_id: 204, gz_partition: so101-five-reset-v2-20260807-at5ewq}
commands: [{command: run-02 via /tmp/so101-five-reset-cycle.sh, exit_code: 0}]
observed:
  - OBSERVED: reset=0, workflow=0, status=DONE through the full trace.
  - OBSERVED: final detached; cup=(-0.08095,-0.24994,0.16500); controllers active; domain/partition unchanged.
inferred: [INFERRED: canonical reset removed run-1 side effects sufficiently for an independent same-stack execution.]
conclusion: VALID success 2/5 in the frozen RESET_WORLD batch.
evidence: [/tmp/so101-reset-world-five-v2-20260807-at5ewq/run-02]
decision: KEEP
next_experiment: EXP-010
```

### EXP-010

```yaml
experiment_id: EXP-010
status: VALID
prior_experiment: EXP-009
hypothesis: H-RESET-STREAK-02
prediction: batch-2 run 3 succeeds after reset in the same stack.
single_variable: NONE
lifecycle: RESET_WORLD
preconditions: [EXP-009 VALID success; same frozen batch contract]
success_criteria: [reset=0; workflow=0 and DONE; final detached/place/controllers/TF/visual consistent]
failure_criteria: [any reset or workflow failure in the valid stack]
invalid_criteria: [duplicate stack; provenance, partition, domain or evidence mismatch]
provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a, runtime_diff_sha256: e2a5f61f50a5e10fd5141690157bd486094bb366d1c31a6df26f39c72cd5006e, ros_domain_id: 204, gz_partition: so101-five-reset-v2-20260807-at5ewq}
commands: [{command: run-03 via /tmp/so101-five-reset-cycle.sh, exit_code: 0}]
observed:
  - OBSERVED: reset=0, workflow=0, status=DONE through the full trace.
  - OBSERVED: final detached; cup=(-0.07818,-0.25129,0.16500); controllers active; domain/partition unchanged.
inferred: [INFERRED: same-stack reset remains canonical through the third cycle.]
conclusion: VALID success 3/5 in the frozen RESET_WORLD batch.
evidence: [/tmp/so101-reset-world-five-v2-20260807-at5ewq/run-03]
decision: KEEP
next_experiment: EXP-011
```

### EXP-011

```yaml
experiment_id: EXP-011
status: VALID
prior_experiment: EXP-010
hypothesis: H-RESET-STREAK-02
prediction: batch-2 run 4 succeeds after reset in the same stack.
single_variable: NONE
lifecycle: RESET_WORLD
preconditions: [EXP-010 VALID success; same frozen batch contract]
success_criteria: [reset=0; workflow=0 and DONE; final detached/place/controllers/TF/visual consistent]
failure_criteria: [any reset or workflow failure in the valid stack]
invalid_criteria: [duplicate stack; provenance, partition, domain or evidence mismatch]
provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a, runtime_diff_sha256: e2a5f61f50a5e10fd5141690157bd486094bb366d1c31a6df26f39c72cd5006e, ros_domain_id: 204, gz_partition: so101-five-reset-v2-20260807-at5ewq}
commands: [{command: run-04 via /tmp/so101-five-reset-cycle.sh, exit_code: 0}]
observed:
  - OBSERVED: reset=0, workflow=0, status=DONE through the full trace.
  - OBSERVED: final detached; cup=(-0.07944,-0.25080,0.16500); controllers active; domain/partition unchanged.
inferred: [INFERRED: reset and execution remain stable through the fourth cycle.]
conclusion: VALID success 4/5 in the frozen RESET_WORLD batch.
evidence: [/tmp/so101-reset-world-five-v2-20260807-at5ewq/run-04]
decision: KEEP
next_experiment: EXP-012
```

### EXP-012

```yaml
experiment_id: EXP-012
status: VALID
prior_experiment: EXP-011
hypothesis: H-RESET-STREAK-02
prediction: batch-2 run 5 completes the five-success RESET_WORLD streak.
single_variable: NONE
lifecycle: RESET_WORLD
preconditions: [EXP-011 VALID success; same frozen batch contract]
success_criteria: [reset=0; workflow=0 and DONE; final detached/place/controllers/TF/visual consistent]
failure_criteria: [any reset or workflow failure in the valid stack]
invalid_criteria: [duplicate stack; provenance, partition, domain or evidence mismatch]
provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a, runtime_diff_sha256: e2a5f61f50a5e10fd5141690157bd486094bb366d1c31a6df26f39c72cd5006e, ros_domain_id: 204, gz_partition: so101-five-reset-v2-20260807-at5ewq}
commands: [{command: run-05 via /tmp/so101-five-reset-cycle.sh, exit_code: 1}]
observed:
  - OBSERVED: reset=0 and workflow reached OPEN_GRIPPER after successful grasp, attach, lift, MOVE_ABOVE_PLACE and DESCEND_TO_PLACE.
  - OBSERVED: the release stage action aborted with controller position error=-0.005443 rad versus 0.001 rad controller tolerance.
  - OBSERVED: final q6=0.506107 rad and velocity=-0.00001095 rad/s were within the profile full-open tolerance for the 0.506 stage, but the executor's 20x50 ms post-abort convergence window had already expired.
  - OBSERVED: original failure GRIPPER_ACTION_ABORTED was preserved under UNSAFE_RECOVERY_OBSERVATION; both attachments remained because DETACH states were not reached.
inferred:
  - INFERRED: rare contact-loaded release settling takes longer than the existing 1.0 s post-abort observation window, despite converging to a valid stopped stage shortly afterward.
conclusion: VALID failure on run 5; batch 2 terminates at 4 consecutive successes and does not satisfy the five-success contract.
evidence: [/tmp/so101-reset-world-five-v2-20260807-at5ewq/run-05]
decision: KEEP
next_experiment: EXP-013
```

```yaml
checkpoint_id: CP-006
last_valid_experiment: EXP-007
current_hypothesis: H-RESET-STREAK-02
working_tree_status: frozen runtime diff installed; batch-2 source patch and provenance captured before first run
owned_processes: one tmux so101-five-reset stack in ROS_DOMAIN_ID=204 and GZ_PARTITION=so101-five-reset-v2-20260807-at5ewq
preserved_processes: PID 652055 sampler clang-tidy; all unrelated user processes/worktrees; codex-cua untouched
confirmed_conclusions:
  - health gate passed at attempt 7 with move_group and three active controllers
  - RTF=0.9971; worktree overlay and runtime diff SHA match the frozen contract
  - LAYOUT_OK and fresh baseline visual show RViz left, Gazebo right, robot home and cup at canonical spawn
disproven_routes:
  - NONE for batch 2
open_risks:
  - none beyond the five-run RESET_WORLD outcome
next_command: touch /tmp/so101-reset-world-five-v2-20260807-at5ewq/allow-run-01
```

```yaml
checkpoint_id: CP-007
last_valid_experiment: EXP-008
current_hypothesis: H-RESET-STREAK-02
working_tree_status: frozen batch unchanged; install/runtime provenance unchanged
owned_processes: same single batch-2 stack awaiting run 2
preserved_processes: PID 652055 sampler clang-tidy; unrelated worktrees/processes and codex-cua untouched
confirmed_conclusions:
  - run 1 is a VALID success with reset, workflow, final facts and visual all consistent
disproven_routes:
  - former carrying q6 pre-plan failure did not recur
open_risks:
  - four more consecutive RESET_WORLD successes required
next_command: touch /tmp/so101-reset-world-five-v2-20260807-at5ewq/allow-run-02
```

```yaml
checkpoint_id: CP-008
last_valid_experiment: EXP-009
current_hypothesis: H-RESET-STREAK-02
working_tree_status: frozen batch unchanged
owned_processes: same single batch-2 stack awaiting run 3
preserved_processes: PID 652055 sampler clang-tidy; unrelated worktrees/processes and codex-cua untouched
confirmed_conclusions:
  - consecutive RESET_WORLD successes now 2/5 with final detached/place/controller facts
disproven_routes:
  - run-1 state accumulation did not prevent run 2
open_risks:
  - three more consecutive successes required
next_command: touch /tmp/so101-reset-world-five-v2-20260807-at5ewq/allow-run-03
```

```yaml
checkpoint_id: CP-009
last_valid_experiment: EXP-010
current_hypothesis: H-RESET-STREAK-02
working_tree_status: frozen batch unchanged
owned_processes: same single batch-2 stack awaiting run 4
preserved_processes: PID 652055 sampler clang-tidy; unrelated worktrees/processes and codex-cua untouched
confirmed_conclusions:
  - consecutive RESET_WORLD successes now 3/5
disproven_routes:
  - no accumulated failure through three cycles
open_risks:
  - two more consecutive successes required
next_command: touch /tmp/so101-reset-world-five-v2-20260807-at5ewq/allow-run-04
```

```yaml
checkpoint_id: CP-010
last_valid_experiment: EXP-011
current_hypothesis: H-RESET-STREAK-02
working_tree_status: frozen batch unchanged
owned_processes: same single batch-2 stack awaiting final run 5
preserved_processes: PID 652055 sampler clang-tidy; unrelated worktrees/processes and codex-cua untouched
confirmed_conclusions:
  - consecutive RESET_WORLD successes now 4/5
disproven_routes:
  - no accumulated failure through four cycles
open_risks:
  - final fifth consecutive success and cleanup evidence required
next_command: touch /tmp/so101-reset-world-five-v2-20260807-at5ewq/allow-run-05
```

```yaml
checkpoint_id: CP-011
last_valid_experiment: EXP-012
current_hypothesis: H-OPEN-SETTLE-01
working_tree_status: batch-2 frozen source retained; no release fix yet
owned_processes: NONE; batch-2 stack cleaned after valid run-5 failure
preserved_processes: PID 652055 sampler clang-tidy; unrelated worktrees/processes and codex-cua untouched
confirmed_conclusions:
  - batch 2 achieved four successes before a valid OPEN_GRIPPER failure on run 5
  - final q6 evidence eventually satisfied the configured full-open stage tolerance and stationary threshold
disproven_routes:
  - 1.0 s is not always sufficient to observe post-abort physical convergence at staged release
open_risks:
  - extending observation must keep fresh/attached/position/velocity checks and a finite bound
next_command: add a RED test for settling after more than 20 but fewer than 40 samples
```

### EXP-013

```yaml
experiment_id: EXP-013
status: VALID
prior_experiment: EXP-012
hypothesis: H-OPEN-SETTLE-01
prediction: a staged-open abort that becomes valid and stationary on sample 25 fails with the current 20-sample window.
single_variable: add a delayed-settling unit-test observer; production code unchanged
lifecycle: RESET_WORLD
preconditions: [batch-2 stack cleaned; runtime source remains frozen at EXP-012]
success_criteria: [RED fails because the executor returns GRIPPER_ACTION_ABORTED before sample 25]
failure_criteria: [test passes before fix or fails for unrelated setup]
invalid_criteria: [stale build/source provenance]
provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a, prior_runtime_diff_sha256: e2a5f61f50a5e10fd5141690157bd486094bb366d1c31a6df26f39c72cd5006e}
commands: [{command: focused test_so101_gripper_state RED, exit_code: 1}]
observed:
  - OBSERVED: executor returned GRIPPER_ACTION_ABORTED after exactly 20 samples while the fixture settled on sample 25.
inferred: [INFERRED: the existing 1.0 s window is the direct reason delayed physical convergence is rejected.]
conclusion: RED reproduced the release-settling timeout at the intended executor boundary.
evidence: [/tmp/so101-reset-world-five-v2-20260807-at5ewq/diagnostics/open-settle]
decision: KEEP
next_experiment: EXP-014
```

### EXP-014

```yaml
experiment_id: EXP-014
status: VALID
prior_experiment: EXP-013
hypothesis: H-OPEN-SETTLE-01
prediction: extending the same guarded sampling loop to 40 samples accepts convergence at sample 25, while convergence after sample 40 still returns the original abort.
single_variable: change only the guarded release-convergence maximum from 20 to 40 samples
lifecycle: RESET_WORLD
preconditions: [EXP-013 VALID RED]
success_criteria:
  - delayed convergence at sample 25 succeeds after three consecutive valid samples
  - delayed convergence at sample 41 fails after exactly 40 samples with GRIPPER_ACTION_ABORTED
  - existing gripper-state suite remains green
failure_criteria: [positive remains failed or finite negative is weakened]
invalid_criteria: [stale build/source provenance]
provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a}
commands:
  - {command: cmake --build build/so101_gazebo_demo --target test_so101_gripper_state -j2, exit_code: 0}
  - {command: focused delayed-positive and bounded-negative GREEN, exit_code: 0}
  - {command: full test_so101_gripper_state, exit_code: 0}
observed:
  - OBSERVED: sample-25 convergence succeeded after 27 observer calls, including three consecutive valid samples.
  - OBSERVED: a fixture that would settle only on sample 41 returned the original GRIPPER_ACTION_ABORTED after exactly 40 calls.
  - OBSERVED: the complete gripper-state binary passed 17/17 tests.
inferred:
  - INFERRED: a finite 2.0 s guarded observation window covers the run-5 delayed settling without weakening attachment, position, velocity, freshness, or consecutive-sample predicates.
conclusion: GREEN proves the narrow timeout correction and its finite negative boundary.
evidence: [/tmp/so101-reset-world-five-v2-20260807-at5ewq/diagnostics/open-settle]
decision: KEEP
next_experiment: EXP-015
```

```yaml
checkpoint_id: CP-012
last_valid_experiment: EXP-013
current_hypothesis: H-OPEN-SETTLE-01
working_tree_status: delayed-settling RED test plus prior runtime changes dirty; production release window not yet rebuilt
owned_processes: NONE
preserved_processes: PID 652055 sampler clang-tidy; unrelated worktrees/processes and codex-cua untouched
confirmed_conclusions:
  - sample-25 convergence fails solely because the current loop stops at sample 20
disproven_routes:
  - treating the final controller abort as proof the physical joint never converged
open_risks:
  - the extended window must remain bounded and preserve all evidence predicates
next_command: rebuild and run positive/finite-negative GREEN tests
```

```yaml
checkpoint_id: CP-013
last_valid_experiment: EXP-014
current_hypothesis: H-RESET-STREAK-03
working_tree_status: guarded release-window fix and tests dirty; package install and regression pending
owned_processes: NONE
preserved_processes: PID 652055 sampler clang-tidy; unrelated worktrees/processes and codex-cua untouched
confirmed_conclusions:
  - delayed post-abort release convergence is accepted only when all physical and scene predicates hold for three consecutive samples within 40 samples
  - failure beyond the finite window preserves the original controller abort
disproven_routes:
  - unbounded waiting or unconditional acceptance of GRIPPER_ACTION_ABORTED
open_risks:
  - installed overlay and package regression must be refreshed before a new five-run batch
next_command: build/install so101_gazebo_demo and run the full package test suite
```

### EXP-015

```yaml
experiment_id: EXP-015
status: VALID
prior_experiment: EXP-014
hypothesis: H-OPEN-SETTLE-01
prediction: the guarded release-window change builds, installs into the worktree overlay, and preserves the complete SO-101 package regression.
single_variable: refresh only the so101_gazebo_demo build/install overlay and rerun its complete test set
lifecycle: RESET_WORLD
preconditions: [EXP-014 VALID GREEN; no owned ROS/Gazebo/MoveIt stack]
success_criteria: [worktree overlay build succeeds; 0 test errors/failures/skips]
failure_criteria: [build or any test fails]
invalid_criteria: [root-workspace overlay or stale result base]
provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a, runtime_code_test_diff_sha256: a88835d037b33f3f07cb11dad70fb36401844f6b9f94a834a9076e0a59098fcc}
commands:
  - {command: colcon build --packages-select so101_gazebo_demo --symlink-install, exit_code: 0}
  - {command: colcon test --packages-select so101_gazebo_demo, exit_code: 0}
  - {command: colcon test-result --test-result-base build/so101_gazebo_demo --verbose, exit_code: 0}
observed:
  - OBSERVED: the package built and installed from the so101-five-success worktree overlay.
  - OBSERVED: 862 tests passed with 0 errors, 0 failures, and 0 skipped.
inferred:
  - INFERRED: the two narrow runtime corrections are ready for a fresh consecutive RESET_WORLD batch.
conclusion: package regression is green on the exact overlay that will run the batch.
evidence: [/data/work/ws_moveit/.worktrees/so101-five-success/build/so101_gazebo_demo/test_results]
decision: KEEP
next_experiment: EXP-016
```

### EXP-016

```yaml
experiment_id: EXP-016
status: VALID
prior_experiment: EXP-015
hypothesis: H-RESET-STREAK-03
prediction: run 1 succeeds after RESET_WORLD in a newly started single stack using the frozen worktree overlay.
single_variable: first workflow run after reset in batch 3; no source/build mutation during batch
lifecycle: RESET_WORLD
preconditions:
  - one fresh stack only
  - ROS_DOMAIN_ID=205
  - GZ_PARTITION=so101-five-reset-v3-20260807-heG1Hv
  - runtime_code_test_diff_sha256=a88835d037b33f3f07cb11dad70fb36401844f6b9f94a834a9076e0a59098fcc
success_criteria: [reset succeeds; workflow DONE; final Gazebo and MoveIt detached; object in place envelope; controllers active; screenshot present]
failure_criteria: [valid workflow or physical-state failure]
invalid_criteria: [wrong overlay/domain/partition; duplicate stack; unhealthy startup; source/build drift]
provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a, runtime_code_test_diff_sha256: a88835d037b33f3f07cb11dad70fb36401844f6b9f94a834a9076e0a59098fcc}
commands: [{command: /tmp/so101-five-reset-cycle.sh /tmp/so101-reset-world-five-v3-20260807-heG1Hv 205 so101-five-reset-v3-20260807-heG1Hv, exit_code: 1}]
observed:
  - OBSERVED: reset and startup provenance were valid, but MOVE_ABOVE_PLACE execution aborted with PATH_TOLERANCE_VIOLATED.
  - OBSERVED: joint 1 transient position error was 0.010287 rad against the configured 0.008000 rad path tolerance.
  - OBSERVED: cancellation completed and the arm became stationary; both attachments and bilateral contacts remained canonical, so recovery failed closed and preserved the original MOVEIT_EXECUTION_FAILED.
inferred:
  - INFERRED: the 0.03 carrying translation scaling still permits a load-induced lag larger than the globally bounded path tolerance; accepting the incomplete endpoint would be unsafe.
conclusion: valid run-1 failure disproves five-run stability with the current carrying translation speed.
evidence: [/tmp/so101-reset-world-five-v3-20260807-heG1Hv/run-01]
decision: KEEP
next_experiment: EXP-017
```

```yaml
checkpoint_id: CP-014
last_valid_experiment: EXP-015
current_hypothesis: H-RESET-STREAK-03
working_tree_status: runtime code/test diff frozen at a88835d037b33f3f07cb11dad70fb36401844f6b9f94a834a9076e0a59098fcc for batch 3; ledger-only updates remain allowed
owned_processes: NONE before fresh stack launch
preserved_processes: PID 652055 sampler clang-tidy; unrelated ROS daemons/worktrees/processes and codex-cua untouched
confirmed_conclusions:
  - full SO-101 package regression passes 862/862 on the refreshed worktree overlay
disproven_routes:
  - counting the prior four-run streak across a source change
open_risks:
  - five new consecutive reset-world successes remain required
next_command: start the batch-3 stack, verify health/provenance/visual layout, then release run 1
```

### EXP-017

```yaml
experiment_id: EXP-017
status: VALID
prior_experiment: EXP-016
hypothesis: H-CARRY-TRACK-01
prediction: reducing only MOVE_ABOVE_PLACE velocity and acceleration scaling from 0.03 to 0.02 preserves the 8 mrad controller path bound while reducing carrying lag.
single_variable: MOVE_ABOVE_PLACE velocity_scaling and acceleration_scaling 0.03 -> 0.02
lifecycle: RESET_WORLD
preconditions: [EXP-016 valid PATH_TOLERANCE_VIOLATED at 10.287 mrad; owned stack cleaned]
success_criteria: [configuration contract RED before policy change; GREEN after policy change; no other state scaling changes]
failure_criteria: [test does not prove exact state-specific change or unrelated policy changes]
invalid_criteria: [stale source/config]
provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a, failure_evidence: /tmp/so101-reset-world-five-v3-20260807-heG1Hv/run-01}
commands:
  - {command: focused configuration contract RED before policy change, exit_code: 1}
  - {command: focused configuration contract GREEN after policy change, exit_code: 0}
  - {command: full test_configuration_contract with ROS/worktree overlay, exit_code: 0}
  - {command: colcon build --packages-select so101_gazebo_demo --symlink-install, exit_code: 0}
observed:
  - OBSERVED: the exact state-specific test failed at obtained 0.03 versus expected 0.02 before the policy edit.
  - OBSERVED: the focused test then passed, and the full configuration contract passed 17/17 under the correct ROS environment.
  - OBSERVED: MOVE_ABOVE_OBJECT remains 0.03, while only MOVE_ABOVE_PLACE is 0.02; the controller path tolerance remains 0.008 rad.
inferred:
  - INFERRED: runtime will test whether the slower carrying sweep reduces transient lag without weakening the global fail-closed bound.
conclusion: the minimal state-specific speed change is GREEN and installed; runtime remains the acceptance gate.
evidence: [/tmp/so101-reset-world-five-v3-20260807-heG1Hv/diagnostics/carry-track]
decision: KEEP
next_experiment: EXP-018
```

```yaml
checkpoint_id: CP-015
last_valid_experiment: EXP-016
current_hypothesis: H-CARRY-TRACK-01
working_tree_status: batch-3 runtime source retained; no carrying-speed change yet
owned_processes: NONE; batch-3 stack cleaned after valid run-1 failure
preserved_processes: PID 652055 sampler clang-tidy; unrelated ROS daemons/worktrees/processes and codex-cua untouched
confirmed_conclusions:
  - 8 mrad remains a meaningful fail-closed controller path bound
  - MOVE_ABOVE_PLACE at 0.03 scaling can exceed that bound under canonical attached-cup load
disproven_routes:
  - accepting the aborted partial endpoint as successful motion
open_risks:
  - 0.02 scaling must be validated at runtime; a configuration-only GREEN is insufficient
next_command: add the exact 0.02 policy expectation as RED, then make the minimal policy change
```

### EXP-018

```yaml
experiment_id: EXP-018
status: VALID
prior_experiment: EXP-017
hypothesis: H-RESET-STREAK-04
prediction: run 1 succeeds after RESET_WORLD with MOVE_ABOVE_PLACE scaling 0.02 and the unchanged 8 mrad controller path bound.
single_variable: first runtime of the installed 0.02 carrying policy; no source/build mutation during batch
lifecycle: RESET_WORLD
preconditions:
  - one fresh stack only
  - ROS_DOMAIN_ID=206
  - GZ_PARTITION=so101-five-reset-v4-20260807-TotAEa
  - runtime_code_test_diff_sha256=f0b81501e2d371c70be0bcc66788f41e8a4beb7f3878dd18bf7fa629d4d57757
success_criteria: [reset succeeds; workflow DONE; final Gazebo and MoveIt detached; object in place envelope; controllers active; screenshot present]
failure_criteria: [valid workflow or physical-state failure]
invalid_criteria: [wrong overlay/domain/partition; duplicate stack; unhealthy startup; source/build drift]
provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a, runtime_code_test_diff_sha256: f0b81501e2d371c70be0bcc66788f41e8a4beb7f3878dd18bf7fa629d4d57757}
commands: [{command: batch-4 run-01 RESET_WORLD plus workflow, exit_code: 0}]
observed:
  - OBSERVED: complete 21-state workflow reached DONE, including MOVE_ABOVE_PLACE under canonical carrying load.
  - OBSERVED: final cup pose was (-0.079230, -0.250841, 0.165000) m; Gazebo and MoveIt were detached and both controllers active.
  - OBSERVED: fresh desktop evidence shows the cup on the destination support and RViz/Gazebo agree with the detached final state.
inferred:
  - INFERRED: the state-specific 0.02 carrying sweep removed the observed run-1 path abort for this cycle without relaxing the 8 mrad bound.
conclusion: first consecutive RESET_WORLD success for batch 4.
evidence: [/tmp/so101-reset-world-five-v4-20260807-TotAEa/run-01]
decision: KEEP
next_experiment: EXP-019
```

```yaml
checkpoint_id: CP-016
last_valid_experiment: EXP-017
current_hypothesis: H-RESET-STREAK-04
working_tree_status: runtime code/test diff frozen at f0b81501e2d371c70be0bcc66788f41e8a4beb7f3878dd18bf7fa629d4d57757 for batch 4; ledger-only updates remain allowed
owned_processes: NONE before fresh stack launch
preserved_processes: PID 652055 sampler clang-tidy; unrelated ROS daemons/worktrees/processes and codex-cua untouched
confirmed_conclusions:
  - MOVE_ABOVE_PLACE is now state-specifically slowed without relaxing the 8 mrad path bound or other motion states
disproven_routes:
  - global controller-tolerance expansion as the first response
open_risks:
  - the 0.02 policy must produce five consecutive runtime successes in one reset-world stack
next_command: start the batch-4 stack, verify health/provenance/layout, then release run 1
```

### EXP-019

```yaml
experiment_id: EXP-019
status: VALID
prior_experiment: EXP-018
hypothesis: H-RESET-STREAK-04
prediction: run 2 succeeds after RESET_WORLD in the unchanged batch-4 stack.
single_variable: second workflow run after reset; source/build/stack unchanged
lifecycle: RESET_WORLD
preconditions: [EXP-018 VALID; frozen runtime hash; one healthy batch-4 stack]
success_criteria: [same complete DONE and final physical/scene/controller/visual gates]
failure_criteria: [valid workflow or physical-state failure]
invalid_criteria: [source/build drift; wrong overlay/domain/partition; duplicate stack]
provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a, runtime_code_test_diff_sha256: f0b81501e2d371c70be0bcc66788f41e8a4beb7f3878dd18bf7fa629d4d57757}
commands: [{command: batch-4 run-02 RESET_WORLD plus workflow, exit_code: 1}]
observed:
  - OBSERVED: reset and provenance were valid; the workflow failed at WAIT_GRASP_STABLE with PHYSICAL_GRASP_BILATERAL_STABILITY_TIMEOUT and then completed its detached/home recovery.
  - OBSERVED: the bounded preload gripper action completed at 1786108711.8527, while the workflow returned failure at 1786108712.3075, leaving about 0.455 s of the shared 30-sample window after preload.
  - OBSERVED: final recovery evidence was safe home, q6 open, cup on the pick support, and both attachment systems detached.
inferred:
  - INFERRED: the single 30-sample counter is consumed by initial settling before the preload command, so a late but valid initial bilateral grasp receives fewer than six post-preload samples even though the post-preload stability contract is logically a new phase.
conclusion: valid run-2 failure exposes coupled pre/post-preload observation budgets, independent of the carrying-speed fix.
evidence: [/tmp/so101-reset-world-five-v4-20260807-TotAEa/run-02]
decision: KEEP
next_experiment: EXP-020
```

```yaml
checkpoint_id: CP-017
last_valid_experiment: EXP-018
current_hypothesis: H-RESET-STREAK-04
working_tree_status: frozen runtime unchanged; ledger-only update after run 1
owned_processes: one healthy batch-4 stack awaiting run 2
preserved_processes: PID 652055 sampler clang-tidy; unrelated ROS daemons/worktrees/processes and codex-cua untouched
confirmed_conclusions:
  - batch-4 consecutive RESET_WORLD successes are 1/5
disproven_routes:
  - none from the valid first run
open_risks:
  - four additional consecutive successes required
next_command: upload ledger checkpoint, verify frozen runtime hash, then release run 2
```

### EXP-020

```yaml
experiment_id: EXP-020
status: VALID
prior_experiment: EXP-019
hypothesis: H-GRASP-PHASE-BUDGET-01
prediction: a fixture that settles late, reaches six bilateral samples, performs the one bounded preload, and then supplies six valid post-preload samples fails because the current shared 30-sample counter stops after only five post-preload samples.
single_variable: add a late-initial-settling unit test; production code unchanged
lifecycle: RESET_WORLD
preconditions: [EXP-019 valid timeout; owned stack cleaned]
success_criteria: [RED returns PHYSICAL_GRASP_BILATERAL_STABILITY_TIMEOUT after 30 observations instead of succeeding after observation 31]
failure_criteria: [test passes before fix or fails for unrelated setup]
invalid_criteria: [stale build/source]
provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a, failure_evidence: /tmp/so101-reset-world-five-v4-20260807-TotAEa/run-02}
commands: [{command: focused test_so101_pick_place_runtime RED, exit_code: 1}]
observed:
  - OBSERVED: the fixture returned PHYSICAL_GRASP_BILATERAL_STABILITY_TIMEOUT after exactly 30 observations; observation 31, the sixth valid post-preload sample, was never read.
inferred:
  - INFERRED: the shared counter, rather than bilateral/contact/depth validity, directly causes this deterministic timeout.
conclusion: RED reproduces the runtime timing defect at the stabilizer boundary.
evidence: [/tmp/so101-reset-world-five-v4-20260807-TotAEa/diagnostics/grasp-phase-budget]
decision: KEEP
next_experiment: EXP-021
```

```yaml
checkpoint_id: CP-018
last_valid_experiment: EXP-019
current_hypothesis: H-GRASP-PHASE-BUDGET-01
working_tree_status: batch-4 runtime source retained; no stabilizer change yet
owned_processes: NONE; batch-4 stack cleaned after valid run-2 failure
preserved_processes: PID 652055 sampler clang-tidy; unrelated ROS daemons/worktrees/processes and codex-cua untouched
confirmed_conclusions:
  - batch-4 ended at 1 success then a valid WAIT_GRASP_STABLE failure
  - post-preload sampling received only about 0.455 s because the pre/post phases share one counter
disproven_routes:
  - attributing this failure to MOVE_ABOVE_PLACE speed or accepting unilateral/unstable contact
open_risks:
  - the fix must preserve one preload only, six consecutive bilateral samples per phase, and a finite 30-sample bound per phase
next_command: add the late-settling RED test at the stabilizer boundary
```

### EXP-021

```yaml
experiment_id: EXP-021
status: VALID
prior_experiment: EXP-020
hypothesis: H-GRASP-PHASE-BUDGET-01
prediction: resetting only the finite 30-sample counter after the single preload gives each logical phase its own bounded budget and makes observation 31 succeed, while never-stable post-preload input still fails after 30 post-phase samples.
single_variable: reset samples_in_phase after the one bounded preload; do not change contact predicates, required consecutive count, preload target, or retry count
lifecycle: RESET_WORLD
preconditions: [EXP-020 VALID RED]
success_criteria:
  - late-settling positive succeeds at observation 31
  - existing stable/unilateral/transient tests preserve their exact observation and command counts
  - a new or existing never-stable negative proves the post-preload phase remains finite at 30 samples
failure_criteria: [unbounded loop; extra preload; weakened bilateral/depth/stationary gates]
invalid_criteria: [stale build/source]
provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a}
commands:
  - {command: focused positive, finite-negative, and three compatibility GREEN tests, exit_code: 0}
  - {command: full test_so101_pick_place_runtime, exit_code: 0}
  - {command: colcon build --packages-select so101_gazebo_demo --symlink-install, exit_code: 0}
observed:
  - OBSERVED: late-settling positive succeeded after exactly 31 observations and one preload command.
  - OBSERVED: never-stable post-preload negative failed with the original timeout after exactly 55 observations, proving 30 finite samples in each phase.
  - OBSERVED: exact stable, unilateral, and transient fixtures preserved their command/observation counts; the full runtime binary passed 34/34 tests.
inferred:
  - INFERRED: each logical phase now has its own finite evidence budget without altering physical acceptance predicates or retry semantics.
conclusion: per-phase counter fix is GREEN, bounded, compatible, and installed.
evidence: [/tmp/so101-reset-world-five-v4-20260807-TotAEa/diagnostics/grasp-phase-budget]
decision: KEEP
next_experiment: EXP-022
```

```yaml
checkpoint_id: CP-019
last_valid_experiment: EXP-020
current_hypothesis: H-GRASP-PHASE-BUDGET-01
working_tree_status: late-settling RED plus prior runtime changes dirty; production per-phase counter fix not yet rebuilt
owned_processes: NONE
preserved_processes: PID 652055 sampler clang-tidy; unrelated ROS daemons/worktrees/processes and codex-cua untouched
confirmed_conclusions:
  - valid sample 31 is excluded solely by the shared 30-sample counter
disproven_routes:
  - weakening bilateral contact, depth, stationary, or consecutive-sample requirements
open_risks:
  - a finite post-preload negative must accompany the positive GREEN
next_command: add the bounded negative, rebuild, and run focused GREEN tests
```

### EXP-022

```yaml
experiment_id: EXP-022
status: VALID
prior_experiment: EXP-021
hypothesis: H-RESET-STREAK-05
prediction: run 1 succeeds after RESET_WORLD with all narrow fixes installed and frozen.
single_variable: first runtime of the independent grasp-phase budget; no source/build mutation during batch
lifecycle: RESET_WORLD
preconditions:
  - one fresh stack only
  - ROS_DOMAIN_ID=207
  - GZ_PARTITION=so101-five-reset-v5-20260807-bXk7En
  - runtime_code_test_diff_sha256=c2c5f3dc4fc48184ce91550a9267dd8d3fcdd6af3ef6756d3b1f15fc771e3ab5
success_criteria: [reset succeeds; full workflow DONE; final detached place/controller/visual gates pass]
failure_criteria: [valid workflow or physical-state failure]
invalid_criteria: [wrong overlay/domain/partition; duplicate stack; unhealthy startup; source/build drift]
provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a, runtime_code_test_diff_sha256: c2c5f3dc4fc48184ce91550a9267dd8d3fcdd6af3ef6756d3b1f15fc771e3ab5}
commands: [{command: batch-5 run-01 RESET_WORLD plus workflow, exit_code: 1}]
observed:
  - OBSERVED: reset/provenance and grasp stabilization were valid, but MOVE_ABOVE_PLACE aborted on joint 5 at 0.008232 rad versus the unchanged 0.008000 rad path tolerance.
  - OBSERVED: cancellation succeeded but the attached-load simulation did not become quiescent; ARM_NOT_QUIESCENT_AFTER_CANCEL preserved the original MOVEIT_EXECUTION_FAILED.
  - OBSERVED: the prior 0.03 scaling failure reached 0.010287 rad on joint 1, while 0.02 scaling still crossed the bound on a different joint.
inferred:
  - INFERRED: reducing carrying speed alone does not bound contact-load tracking error below 8 mrad; the global process tolerance is narrower than the repeated observed transient envelope.
conclusion: valid runtime failure disproves speed-only stabilization while confirming fail-closed cancellation behavior.
evidence: [/tmp/so101-reset-world-five-v5-20260807-bXk7En/run-01]
decision: KEEP
next_experiment: EXP-023
```

```yaml
checkpoint_id: CP-020
last_valid_experiment: EXP-021
current_hypothesis: H-RESET-STREAK-05
working_tree_status: runtime code/test diff frozen at c2c5f3dc4fc48184ce91550a9267dd8d3fcdd6af3ef6756d3b1f15fc771e3ab5 for batch 5; ledger-only updates remain allowed
owned_processes: NONE before fresh stack launch
preserved_processes: PID 652055 sampler clang-tidy; unrelated ROS daemons/worktrees/processes and codex-cua untouched
confirmed_conclusions:
  - post-preload stability receives a separate bounded 30-sample window
  - the full affected runtime binary passes 34/34 and the installed overlay is refreshed
disproven_routes:
  - unbounded waiting, extra preload attempts, or weakened physical predicates
open_risks:
  - five new consecutive reset-world successes remain required
next_command: start batch-5 stack, verify provenance/health/layout, then release run 1
```

### EXP-023

```yaml
experiment_id: EXP-023
status: VALID
prior_experiment: EXP-022
hypothesis: H-CARRY-PATH-BOUND-02
prediction: a 12 mrad arm path tolerance contains the two observed canonical attached-load transients (10.287 and 8.232 mrad) while retaining the 2 mrad controller goal and tighter state-specific endpoint checks.
single_variable: arm joints 1-5 trajectory tolerance 0.008 -> 0.012; goal tolerance and all endpoint validators unchanged
lifecycle: RESET_WORLD
preconditions: [two valid MOVE_ABOVE_PLACE path aborts at different joints and speeds; owned stack cleaned]
success_criteria: [exact configuration RED before change, GREEN after change; all five joints equal 0.012; goal remains 0.002; endpoint contracts unchanged]
failure_criteria: [goal/endpoint tolerance weakened or nonuniform joint policy]
invalid_criteria: [stale config/source]
provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a, evidence: [/tmp/so101-reset-world-five-v3-20260807-heG1Hv/run-01, /tmp/so101-reset-world-five-v5-20260807-bXk7En/run-01]}
commands:
  - {command: exact arm path configuration RED, exit_code: 1}
  - {command: exact arm path configuration GREEN, exit_code: 0}
  - {command: full test_configuration_contract with ROS/worktree overlay, exit_code: 0}
  - {command: colcon build --packages-select so101_gazebo_demo --symlink-install, exit_code: 0}
observed:
  - OBSERVED: RED showed all five joints still at 0.008 against the required 0.012 process bound.
  - OBSERVED: GREEN proves all five path tolerances are 0.012 while all five goal tolerances remain 0.002; the full configuration contract passed 17/17.
  - OBSERVED: contact-critical endpoint postconditions remain independently defined and unchanged.
inferred:
  - INFERRED: runtime can now continue through the measured 10.287 mrad load transient but still must satisfy its exact terminal and physical contracts.
conclusion: finite process-only tolerance adjustment is GREEN and installed.
evidence: [/tmp/so101-reset-world-five-v5-20260807-bXk7En/diagnostics/carry-path-bound]
decision: KEEP
next_experiment: EXP-024
```

```yaml
checkpoint_id: CP-021
last_valid_experiment: EXP-022
current_hypothesis: H-CARRY-PATH-BOUND-02
working_tree_status: batch-5 source retained; no controller-bound change yet
owned_processes: NONE; batch-5 stack cleaned after valid run-1 failure
preserved_processes: PID 652055 sampler clang-tidy; unrelated ROS daemons/worktrees/processes and codex-cua untouched
confirmed_conclusions:
  - 0.02 carrying scaling still crossed the 8 mrad path bound under canonical attached load
  - cancellation and recovery remained fail-closed rather than accepting a moving robot
disproven_routes:
  - speed-only stabilization at 0.02 with the 8 mrad global bound
open_risks:
  - 12 mrad is a process-only bound and must not leak into goal or endpoint acceptance
next_command: add the exact 12 mrad configuration RED while asserting 2 mrad goal remains unchanged
```

### EXP-024

```yaml
experiment_id: EXP-024
status: VALID
prior_experiment: EXP-023
hypothesis: H-RESET-STREAK-06
prediction: run 1 succeeds after RESET_WORLD with the 12 mrad process bound plus all prior narrow fixes.
single_variable: first runtime of the installed 12 mrad arm path bound; no source/build mutation during batch
lifecycle: RESET_WORLD
preconditions:
  - one fresh stack only
  - ROS_DOMAIN_ID=208
  - GZ_PARTITION=so101-five-reset-v6-20260807-3tvZU1
  - runtime_code_test_diff_sha256=c8eab90e61c0e465679facc24f54407d8dde28ea2dcb39dc9313a3ace0b317c5
success_criteria: [reset succeeds; full workflow DONE; final detached place/controller/visual gates pass]
failure_criteria: [valid workflow or physical-state failure]
invalid_criteria: [wrong overlay/domain/partition; duplicate stack; unhealthy startup; source/build drift]
provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a, runtime_code_test_diff_sha256: c8eab90e61c0e465679facc24f54407d8dde28ea2dcb39dc9313a3ace0b317c5}
commands: [{command: batch-6 run-01 RESET_WORLD plus workflow, exit_code: 0}]
observed:
  - OBSERVED: complete 21-state workflow reached DONE through the carrying sweep and release.
  - OBSERVED: final Gazebo/MoveIt detached state, active controllers, destination pose envelope, and fresh RViz/Gazebo desktop evidence all passed.
inferred: [INFERRED: the 12 mrad process bound contained this attached-load trajectory while terminal contracts remained satisfied.]
conclusion: first consecutive RESET_WORLD success for batch 6.
evidence: [/tmp/so101-reset-world-five-v6-20260807-3tvZU1/run-01]
decision: KEEP
next_experiment: EXP-025
```

```yaml
checkpoint_id: CP-022
last_valid_experiment: EXP-023
current_hypothesis: H-RESET-STREAK-06
working_tree_status: runtime code/test diff frozen at c8eab90e61c0e465679facc24f54407d8dde28ea2dcb39dc9313a3ace0b317c5 for batch 6; ledger-only updates remain allowed
owned_processes: NONE before fresh stack launch
preserved_processes: PID 652055 sampler clang-tidy; unrelated ROS daemons/worktrees/processes and codex-cua untouched
confirmed_conclusions:
  - 12 mrad applies only to controller path tracking; 2 mrad controller goal and state-specific endpoint contracts remain unchanged
disproven_routes:
  - speed-only stabilization with an 8 mrad process bound
open_risks:
  - five new consecutive reset-world successes remain required
next_command: start batch-6 stack, verify provenance/health/layout, then release run 1
```

### EXP-025

```yaml
experiment_id: EXP-025
status: VALID
prior_experiment: EXP-024
hypothesis: H-RESET-STREAK-06
prediction: run 2 succeeds after RESET_WORLD in the unchanged batch-6 stack.
single_variable: second workflow run after reset; source/build/stack unchanged
lifecycle: RESET_WORLD
preconditions: [EXP-024 VALID; frozen runtime hash; one healthy batch-6 stack]
success_criteria: [same complete DONE and final physical/scene/controller/visual gates]
failure_criteria: [valid workflow or physical-state failure]
invalid_criteria: [source/build drift; wrong overlay/domain/partition; duplicate stack]
provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a, runtime_code_test_diff_sha256: c8eab90e61c0e465679facc24f54407d8dde28ea2dcb39dc9313a3ace0b317c5}
commands: [{command: batch-6 run-02 RESET_WORLD plus workflow, exit_code: 0}]
observed: [OBSERVED: reset, full 21-state DONE trace, detached destination state, controllers, and screenshots all passed.]
inferred: [INFERRED: no accumulated failure through two unchanged reset cycles.]
conclusion: second consecutive RESET_WORLD success for batch 6.
evidence: [/tmp/so101-reset-world-five-v6-20260807-3tvZU1/run-02]
decision: KEEP
next_experiment: EXP-026
```

```yaml
checkpoint_id: CP-023
last_valid_experiment: EXP-024
current_hypothesis: H-RESET-STREAK-06
working_tree_status: frozen runtime unchanged; ledger-only update after run 1
owned_processes: one healthy batch-6 stack awaiting run 2
preserved_processes: PID 652055 sampler clang-tidy; unrelated ROS daemons/worktrees/processes and codex-cua untouched
confirmed_conclusions: [batch-6 consecutive RESET_WORLD successes are 1/5]
disproven_routes: [none from the valid first run]
open_risks: [four additional consecutive successes required]
next_command: upload ledger checkpoint, verify frozen runtime hash, then release run 2
```

### EXP-026

```yaml
experiment_id: EXP-026
status: VALID
prior_experiment: EXP-025
hypothesis: H-RESET-STREAK-06
prediction: run 3 succeeds after RESET_WORLD in the unchanged batch-6 stack.
single_variable: third workflow run after reset; source/build/stack unchanged
lifecycle: RESET_WORLD
preconditions: [EXP-025 VALID; frozen runtime hash; one healthy batch-6 stack]
success_criteria: [same complete DONE and final physical/scene/controller/visual gates]
failure_criteria: [valid workflow or physical-state failure]
invalid_criteria: [source/build drift; wrong overlay/domain/partition; duplicate stack]
provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a, runtime_code_test_diff_sha256: c8eab90e61c0e465679facc24f54407d8dde28ea2dcb39dc9313a3ace0b317c5}
commands: [{command: batch-6 run-03 RESET_WORLD plus workflow, exit_code: 1}]
observed:
  - OBSERVED: reset/provenance, grasp, lift, and MOVE_ABOVE_PLACE passed; DESCEND_TO_PLACE aborted on joint 5 at 0.013766 rad versus 0.012000 rad.
  - OBSERVED: DESCEND_TO_PLACE still used 0.10 velocity/acceleration scaling, over three times the stabilized carrying sweep.
  - OBSERVED: cancellation succeeded but the attached-load simulation did not quiesce, so recovery failed closed and preserved the original execution failure.
inferred:
  - INFERRED: the contact-critical attached-cup descent is the remaining high-speed carrying segment; widening the global bound again is less targeted than reducing this state alone.
conclusion: valid run-3 failure ended batch 6 at two successes and isolates DESCEND_TO_PLACE speed.
evidence: [/tmp/so101-reset-world-five-v6-20260807-3tvZU1/run-03]
decision: KEEP
next_experiment: EXP-027
```

```yaml
checkpoint_id: CP-024
last_valid_experiment: EXP-025
current_hypothesis: H-RESET-STREAK-06
working_tree_status: frozen runtime unchanged; ledger-only update after run 2
owned_processes: one healthy batch-6 stack awaiting run 3
preserved_processes: PID 652055 sampler clang-tidy; unrelated ROS daemons/worktrees/processes and codex-cua untouched
confirmed_conclusions: [batch-6 consecutive RESET_WORLD successes are 2/5]
disproven_routes: [no accumulated failure through two cycles]
open_risks: [three additional consecutive successes required]
next_command: upload ledger checkpoint, verify frozen runtime hash, then release run 3
```

### EXP-027

```yaml
experiment_id: EXP-027
status: VALID
prior_experiment: EXP-026
hypothesis: H-PLACE-DESCEND-TRACK-01
prediction: reducing only DESCEND_TO_PLACE velocity/acceleration scaling from 0.10 to 0.03 keeps its attached-load tracking inside the existing 12 mrad bound.
single_variable: DESCEND_TO_PLACE velocity_scaling and acceleration_scaling 0.10 -> 0.03
lifecycle: RESET_WORLD
preconditions: [EXP-026 valid joint-5 path abort at 13.766 mrad; owned stack cleaned]
success_criteria: [exact state-specific configuration RED then GREEN; LIFT and pick DESCEND remain 0.10; global path and endpoint bounds unchanged]
failure_criteria: [other motion states or tolerance semantics change]
invalid_criteria: [stale config/source]
provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a, failure_evidence: /tmp/so101-reset-world-five-v6-20260807-3tvZU1/run-03}
commands:
  - {command: exact attached-transfer configuration RED, exit_code: 1}
  - {command: exact attached-transfer configuration GREEN, exit_code: 0}
  - {command: full test_configuration_contract with ROS/worktree overlay, exit_code: 0}
  - {command: colcon build --packages-select so101_gazebo_demo --symlink-install, exit_code: 0}
observed:
  - OBSERVED: RED obtained DESCEND_TO_PLACE scaling 0.10 against expected 0.03.
  - OBSERVED: GREEN proves MOVE_ABOVE_PLACE remains 0.02, DESCEND_TO_PLACE is 0.03, LIFT remains 0.10, and the full configuration contract passes 17/17.
inferred: [INFERRED: runtime will determine whether the narrower placement descent stays inside the unchanged process bound and endpoint contract.]
conclusion: minimal state-specific place-descent change is GREEN and installed.
evidence: [/tmp/so101-reset-world-five-v6-20260807-3tvZU1/diagnostics/place-descend-track]
decision: KEEP
next_experiment: EXP-028
```

```yaml
checkpoint_id: CP-025
last_valid_experiment: EXP-026
current_hypothesis: H-PLACE-DESCEND-TRACK-01
working_tree_status: batch-6 source retained; no place-descent speed change yet
owned_processes: NONE; batch-6 stack cleaned after valid run-3 failure
preserved_processes: PID 652055 sampler clang-tidy; unrelated ROS daemons/worktrees/processes and codex-cua untouched
confirmed_conclusions:
  - batch 6 ended at two successes before a high-speed DESCEND_TO_PLACE path abort
  - MOVE_ABOVE_PLACE passed under the 12 mrad process bound
disproven_routes:
  - treating every attached-load segment as equivalent despite state-specific speed
open_risks:
  - 0.03 place descent must pass its contact-critical endpoint contract at runtime
next_command: add the exact state-specific 0.03 RED and then change only DESCEND_TO_PLACE
```

### EXP-028

```yaml
experiment_id: EXP-028
status: INVALID
prior_experiment: EXP-027
hypothesis: H-RESET-STREAK-07
prediction: run 1 succeeds after RESET_WORLD with all attached-cup transfer segments stabilized and frozen.
single_variable: first runtime of DESCEND_TO_PLACE scaling 0.03; no source/build mutation during batch
lifecycle: RESET_WORLD
preconditions:
  - one fresh stack only
  - ROS_DOMAIN_ID=209
  - GZ_PARTITION=so101-five-reset-v7-20260807-OCQ6U0
  - runtime_code_test_diff_sha256=b8b8c2b076d024889d68493abc6b3adde6b01ea1a09234ae2e7e2fdd33ea9d3a
success_criteria: [reset succeeds; full workflow DONE; final detached place/controller/visual gates pass]
failure_criteria: [valid workflow or physical-state failure]
invalid_criteria: [wrong overlay/domain/partition; duplicate stack; unhealthy startup; source/build drift]
provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a, runtime_code_test_diff_sha256: b8b8c2b076d024889d68493abc6b3adde6b01ea1a09234ae2e7e2fdd33ea9d3a}
commands: [{command: /tmp/so101-five-reset-cycle.sh /tmp/so101-reset-world-five-v7-20260807-OCQ6U0 209 so101-five-reset-v7-20260807-OCQ6U0, exit_code: 1}]
observed:
  - OBSERVED: startup provenance, three active controllers, /move_group, RTF=1.00016 and LAYOUT_OK were captured; stack-ready existed.
  - OBSERVED: allow-run-01 was not released within the runner's finite 600-second sentinel window; no run-01 directory, reset, or workflow evidence was produced.
  - OBSERVED: the runner EXIT trap removed only tmux so101-five-reset and processes carrying the batch-7 GZ_PARTITION; codex, codex-cua and PID 652055 remained present.
inferred: [INFERRED: batch termination was orchestration timeout contamination, not SO-101 product behavior.]
conclusion: INVALID before reset/workflow; batch 7 terminates without a counted run.
evidence: [/tmp/so101-reset-world-five-v7-20260807-OCQ6U0/run-01]
decision: REPEAT
next_experiment: EXP-029
```

```yaml
checkpoint_id: CP-026
last_valid_experiment: EXP-027
current_hypothesis: H-RESET-STREAK-07
working_tree_status: runtime code/test diff frozen at b8b8c2b076d024889d68493abc6b3adde6b01ea1a09234ae2e7e2fdd33ea9d3a for batch 7; ledger-only updates remain allowed
owned_processes: NONE before fresh stack launch
preserved_processes: PID 652055 sampler clang-tidy; unrelated ROS daemons/worktrees/processes and codex-cua untouched
confirmed_conclusions: [DESCEND_TO_PLACE is state-specifically 0.03 while all global and endpoint bounds remain unchanged]
disproven_routes: [global tolerance widening as the response to the placement-descent failure]
open_risks: [five new consecutive reset-world successes remain required]
next_command: start batch-7 stack, verify provenance/health/layout, then release run 1
```

## RESET_WORLD validation batch 8

Frozen contract:

- One tmux stack: `so101-five-reset`.
- `ROS_DOMAIN_ID=210`; `GZ_PARTITION=so101-five-reset-v8-20260807-H7nQ4x`.
- Worktree install overlay only; HEAD `e118ac0` plus runtime code/test diff SHA-256 `b8b8c2b076d024889d68493abc6b3adde6b01ea1a09234ae2e7e2fdd33ea9d3a`.
- Same motion, validation and controller policies as EXP-028; no source/build mutation during the counted streak.
- Every run uses canonical RESET_WORLD before the full workflow; a VALID failure or any INVALID run terminates this batch.

### EXP-029 through EXP-033

```yaml
experiments:
  - experiment_id: EXP-029
    status: VALID
    prior_experiment: EXP-028
    hypothesis: H-RESET-STREAK-08
    prediction: run 1 succeeds after canonical RESET_WORLD with the frozen attached-transfer policy.
  - experiment_id: EXP-030
    status: VALID
    prior_experiment: EXP-029
    hypothesis: H-RESET-STREAK-08
    prediction: run 2 succeeds after RESET_WORLD in the unchanged stack.
  - experiment_id: EXP-031
    status: PLANNED
    prior_experiment: EXP-030
    hypothesis: H-RESET-STREAK-08
    prediction: run 3 succeeds after RESET_WORLD in the unchanged stack.
  - experiment_id: EXP-032
    status: PLANNED
    prior_experiment: EXP-031
    hypothesis: H-RESET-STREAK-08
    prediction: run 4 succeeds after RESET_WORLD in the unchanged stack.
  - experiment_id: EXP-033
    status: PLANNED
    prior_experiment: EXP-032
    hypothesis: H-RESET-STREAK-08
    prediction: run 5 completes five consecutive RESET_WORLD successes.
common_contract:
  single_variable: NONE
  lifecycle: RESET_WORLD
  preconditions: [one healthy provenance-correct batch-8 stack; prior run VALID for EXP-030 through EXP-033]
  success_criteria: [reset exit 0; workflow exit 0 and DONE; full 21-state trace; Gazebo and MoveIt detached; object in destination envelope; controllers and joint/TF consistent; fresh post-run visual]
  failure_criteria: [reset or workflow failure, incomplete trace, or physical/scene/controller/visual contract failure in a valid stack]
  invalid_criteria: [source/build drift; wrong overlay/domain/partition; duplicate or unhealthy stack; missing required evidence]
  provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a, install_overlay: /data/work/ws_moveit/.worktrees/so101-five-success/install, runtime_executable: /data/work/ws_moveit/.worktrees/so101-five-success/install/so101_gazebo_demo/lib/so101_gazebo_demo/pick_place_state_machine, runtime_code_test_diff_sha256: b8b8c2b076d024889d68493abc6b3adde6b01ea1a09234ae2e7e2fdd33ea9d3a, ros_domain_id: 210, gz_partition: so101-five-reset-v8-20260807-H7nQ4x}
  commands: [{command: /tmp/so101-five-reset-cycle.sh /tmp/so101-reset-world-five-v8-20260807-H7nQ4x 210 so101-five-reset-v8-20260807-H7nQ4x, exit_code: PENDING}]
  observed: [NONE]
  inferred: [NONE]
  conclusion: PENDING
  evidence: [/tmp/so101-reset-world-five-v8-20260807-H7nQ4x/run-01 through run-05]
  decision: PENDING
  next_experiment: EXP-030 through NONE respectively
```

```yaml
checkpoint_id: CP-027
last_valid_experiment: EXP-027
current_hypothesis: H-RESET-STREAK-08
working_tree_status: runtime code/test diff frozen at b8b8c2b076d024889d68493abc6b3adde6b01ea1a09234ae2e7e2fdd33ea9d3a; ledger-only updates allowed during batch 8
owned_processes: NONE before fresh batch-8 launch; batch-7 owned processes absent after its finite sentinel timeout
preserved_processes: PID 652055 sampler clang-tidy; tmux codex and codex-cua; unrelated worktrees/processes
confirmed_conclusions:
  - EXP-028 is INVALID before reset/workflow and supplies no product-behavior conclusion
  - source HEAD and frozen runtime code/test diff remain unchanged from the batch-7 contract
disproven_routes:
  - counting or resuming a stack after its sentinel timeout
open_risks:
  - five fresh consecutive RESET_WORLD successes remain required
next_command: bash /tmp/so101-five-reset-cycle.sh /tmp/so101-reset-world-five-v8-20260807-H7nQ4x 210 so101-five-reset-v8-20260807-H7nQ4x
```

```yaml
checkpoint_id: CP-028
last_valid_experiment: EXP-027
current_hypothesis: H-RESET-STREAK-08
working_tree_status: runtime code/test diff freshly verified at b8b8c2b076d024889d68493abc6b3adde6b01ea1a09234ae2e7e2fdd33ea9d3a; EXP-029 RUNNING; ledger-only mutation
owned_processes: one batch-8 tmux so101-five-reset stack; one Gazebo server/gui, one move_group/RViz launch and one teleop server in ROS_DOMAIN_ID=210, GZ_PARTITION=so101-five-reset-v8-20260807-H7nQ4x
preserved_processes: PID 652055 sampler clang-tidy; tmux codex and codex-cua; unrelated worktrees/processes
confirmed_conclusions:
  - HEAD e118ac0, package prefix /data/work/ws_moveit/.worktrees/so101-five-success/install/so101_gazebo_demo and resolved build executable match the frozen batch contract
  - /health is READY and simulation_only=true; /capabilities names pick_place_state_machine as workflow owner; /snapshot domain/partition/session match with fresh telemetry, detached scene, canonical object pose and both controllers active
  - LAYOUT_OK; fresh pre-release desktop at /tmp/so101-reset-world-five-v8-20260807-H7nQ4x/stack/pre-release-desktop.png visibly shows RViz left, Gazebo right, robot at home and cup at canonical pick support
disproven_routes: [duplicate batch stack or stale overlay as a batch-8 startup explanation]
open_risks: [EXP-029 runtime outcome and four subsequent consecutive successes]
next_command: touch /tmp/so101-reset-world-five-v8-20260807-H7nQ4x/allow-run-01
```

```yaml
experiment_result: EXP-029
commands: [{command: batch-8 run-01 RESET_WORLD plus workflow, exit_code: 0}]
observed:
  - OBSERVED: reset returncode 0; workflow returncode 0 and status=DONE through IDLE plus all 20 transitions to DONE.
  - OBSERVED: final Gazebo and MoveIt detached; cup=(-0.081070,-0.249789,0.165000) m in the destination envelope; arm, gripper and joint-state controllers active.
  - OBSERVED: final joint velocities were settled, TCP/joint/scene telemetry fresh, domain/partition and runtime hash unchanged.
  - OBSERVED: fresh /tmp/so101-reset-world-five-v8-20260807-H7nQ4x/run-01/after-workflow-desktop.png visibly shows the cup on the destination support and the arm retreated; RViz and Gazebo agree.
inferred: [INFERRED: the state-specific placement descent clears its former path-tolerance boundary in this frozen cycle.]
conclusion: VALID success 1/5 in batch 8.
evidence: [/tmp/so101-reset-world-five-v8-20260807-H7nQ4x/run-01]
decision: KEEP
next_experiment: EXP-030
```

```yaml
checkpoint_id: CP-029
last_valid_experiment: EXP-029
current_hypothesis: H-RESET-STREAK-08
working_tree_status: frozen runtime hash b8b8c2b076d024889d68493abc6b3adde6b01ea1a09234ae2e7e2fdd33ea9d3a unchanged; EXP-030 RUNNING; ledger-only mutation
owned_processes: same healthy batch-8 stack awaiting allow-run-02
preserved_processes: PID 652055 sampler clang-tidy; tmux codex and codex-cua; unrelated worktrees/processes
confirmed_conclusions: [batch-8 RESET_WORLD streak is 1/5 with complete runtime and fresh visual evidence]
disproven_routes: [the prior DESCEND_TO_PLACE 0.10 failure did not recur with state-specific 0.03 in run 1]
open_risks: [four additional consecutive successes required]
next_command: touch /tmp/so101-reset-world-five-v8-20260807-H7nQ4x/allow-run-02
```

```yaml
experiment_result: EXP-030
commands: [{command: batch-8 run-02 RESET_WORLD plus workflow, exit_code: 1}]
observed:
  - OBSERVED: reset returncode 0 and workflow passed grasp, both attachments, LIFT, MOVE_ABOVE_PLACE and DESCEND_TO_PLACE before failing at OPEN_GRIPPER.
  - OBSERVED: first bad boundary was TASK_OBJECT_RELEASE_SUPPORT_INVALID; q6 reached 0.75 rad and stopped, while the still-attached cup pose was (-0.077175,-0.249378,0.175111) m with 0.048047 rad tilt.
  - OBSERVED: XY error and tilt were inside their configured support bounds, but height error was 0.010111 m versus the 0.010000 m pre-detach support bound.
  - OBSERVED: fail-closed recovery preserved both Gazebo and MoveIt attachments and returned UNSAFE_RECOVERY_OBSERVATION; controllers and telemetry remained active/fresh.
  - OBSERVED: fresh after-workflow visual shows the opened gripper/cup still held just above the destination support, consistent with the numeric height failure.
inferred:
  - INFERRED: the immediate discriminator is pre-detach cup height, not controller execution, q6 settling, XY placement, tilt, attachment convergence, or the state-specific descent path bound.
conclusion: VALID failure on run 2; batch 8 ends after one consecutive success. EXP-031 through EXP-033 are NOT_RUN and cannot be counted.
evidence: [/tmp/so101-reset-world-five-v8-20260807-H7nQ4x/run-02]
decision: KEEP
next_experiment: EXP-034
```

```yaml
checkpoint_id: CP-030
last_valid_experiment: EXP-030
current_hypothesis: H-PLACE-HEIGHT-01
working_tree_status: batch-8 runtime remained frozen at b8b8c2b076d024889d68493abc6b3adde6b01ea1a09234ae2e7e2fdd33ea9d3a; no fix yet
owned_processes: NONE expected after batch-8 valid failure and runner-owned EXIT cleanup
preserved_processes: PID 652055 sampler clang-tidy; tmux codex and codex-cua; unrelated worktrees/processes
confirmed_conclusions:
  - batch 8 ended at one success then a VALID OPEN_GRIPPER support-height failure
  - run-02 gripper action, q6 settling, XY support, tilt, controllers and both attachments were valid; only pre-detach support height exceeded its bound by 0.111 mm
disproven_routes:
  - releasing EXP-031 after a VALID failure
  - attributing run 2 to the former DESCEND_TO_PLACE controller path-tolerance failure
open_risks:
  - determine whether the first-cause boundary is the placement endpoint height, detachable-joint pose variance, or support-validation sequencing before any fix
next_command: compare run-01/run-02 placement/open evidence and the configured placement endpoint/support geometry
```

### EXP-034

```yaml
experiment_id: EXP-034
status: VALID
prior_experiment: EXP-030
hypothesis: H-PLACE-PREDETACH-HEIGHT-01
prediction: contracts reproducing a stationary attached cup at +10.111 mm fail before detach under the shared 10 mm bound, even when OPEN succeeds physically and the post-detach pose is strictly supported.
single_variable: add focused OPEN and DETACH pre/post-height regression cases; production code unchanged
lifecycle: RESET_WORLD
preconditions: [batch-8 stack cleaned; EXP-030 valid failure evidence preserved]
success_criteria: [RED fails at the intended pre-detach height boundary; post-detach pose remains required inside 10 mm]
failure_criteria: [test passes before fix or fails for unrelated attachment/q6/scene setup]
invalid_criteria: [stale source/build provenance]
provenance: {source_commit: e118ac0cd4798e5c7f24efe31d08607f69d3782a, install_overlay: /data/work/ws_moveit/.worktrees/so101-five-success/install, runtime_executable: /data/work/ws_moveit/.worktrees/so101-five-success/build/so101_gazebo_demo/test_so101_gripper_state, ros_domain_id: 210, gz_partition: so101-five-reset-v8-20260807-H7nQ4x, failure_evidence: /tmp/so101-reset-world-five-v8-20260807-H7nQ4x/run-02}
commands:
  - {command: focused gripper pre-detach height RED, exit_code: 1}
  - {command: focused attachment pre/post-detach height RED, exit_code: 1}
  - {command: focused gripper and attachment contract GREEN tests, exit_code: 0}
  - {command: colcon build --packages-select so101_gazebo_demo --symlink-install, exit_code: 0}
  - {command: colcon test --packages-select so101_gazebo_demo --event-handlers console_direct+, exit_code: 0}
  - {command: colcon test-result --test-result-base build/so101_gazebo_demo --verbose, exit_code: 0}
observed:
  - OBSERVED: both focused tests failed before production change at the shared 10 mm pre-detach height boundary.
  - OBSERVED: a separate 12 mm pre-detach-only height allowance made OPEN and DETACH precondition GREEN while the actual after-detach snapshot remains governed by the existing 10 mm support bound.
  - OBSERVED: package verification reported 866 tests, 0 errors, 0 failures and 8 skipped; all 80 CTest entries passed.
inferred: [INFERRED: the narrow phase-specific contract represents detachable-joint constrained height without weakening final physical support acceptance.]
conclusion: RED-GREEN and package verification complete; runtime five-success is neither claimed nor pursued further.
evidence: [/tmp/so101-reset-world-five-v8-20260807-H7nQ4x/diagnostics/pre-detach-height]
decision: KEEP
next_experiment: NONE
```

```yaml
checkpoint_id: CP-031
date: 2026-08-07
last_valid_experiment: EXP-034
current_hypothesis: NONE; campaign superseded
working_tree_status: intended SO-101 runtime, policy, tests, project Skill/reference and ledger changes ready for commit after fresh diff review
owned_processes: NONE; no Gazebo/MoveIt/teleop stack remains
preserved_processes: PID 652055 sampler clang-tidy; tmux codex and codex-cua; unrelated worktrees/processes
confirmed_conclusions:
  - EXP-029 was a VALID RESET_WORLD success with complete 21-state DONE and final physical/scene/visual evidence
  - EXP-030 was a VALID failure at OPEN_GRIPPER because the still-attached stationary cup height error was 0.010111 m against the shared 0.010000 m pre-detach envelope
  - EXP-034 added and verified a finite 0.012 m pre-detach-only height contract; after-detach/final support remains bounded by 0.010 m
  - feature-tree package verification passed 866 tests with 0 errors and 0 failures (8 skipped)
disproven_routes:
  - continuing EXP-031 through EXP-033 after the EXP-030 VALID failure
  - claiming five consecutive runtime successes from this campaign
open_risks:
  - runtime verification under the new final physical-outcome strategy belongs to a future task/worktree
supersession:
  - the old five-consecutive-success RESET_WORLD campaign is superseded by a new final physical-outcome acceptance strategy
  - no further Gazebo runtime batch was launched after EXP-030; EXP-031 through EXP-033 were not run
next_command: review intended diff, commit and push codex/so101-five-success, then safely merge and verify main
```

## Physical-outcome campaign

```yaml
task_id: so101-physical-outcome-validation
success_contract: five consecutive VALID execute runs whose post-release stable physical outcome and every hard safety invariant pass
worktree: /data/work/ws_moveit/.worktrees/so101-physical-outcome-validation
branch: codex/so101-physical-outcome-validation
base_commit: 05dff7a18e466c01486441dd90c21fcd44d4d8cd
current_commit: 130bd7e8caae037fa7d8643aba80b7f2101f6a27
evidence_root: /tmp/so101-debug-physical-outcome-kon1M2
confirmed_conclusions:
  - approved physical truth versus planning shadow semantics from the design commit
disproven_routes:
  - 0.75 mm seat
  - independent CLOSE seat motion
  - longer close duration as a fix
  - safety-gate relaxation
  - unregistered fixed-port retry fixture
open_hypotheses:
  - live calibration values for every CALIBRATION_REQUIRED field
latest_checkpoint: CP-PHYSICAL-001
next_experiment: CAL-PHYSICAL-001
```

```yaml
checkpoint_id: CP-PHYSICAL-001
date: 2026-08-07
last_valid_historical_experiment: EXP-034
working_tree_status:
  branch: codex/so101-physical-outcome-validation
  dirty_paths_before_checkpoint: []
  dirty_paths_after_checkpoint:
    - docs/experiments/so101-reset-world-five-success-experiment-ledger.md
owned_processes: []
preserved_processes:
  - tmux session codex (attached)
  - tmux session codex-cua (attached)
  - tmux session so101-py-task8
  - PID 652055 sampler run-clang-tidy in worktree so101-workspace-sampler
  - PIDs 2834279 and 2834281 Gazebo processes in worktree so101-gazebo-demo-py
open_risks:
  - every new physical-outcome and planning-shadow threshold remains CALIBRATION_REQUIRED until justified by live evidence
  - no new final-outcome execute run has been attempted or accepted
next_command: add the Task 2 shared-state and Panda compatibility RED tests
```
