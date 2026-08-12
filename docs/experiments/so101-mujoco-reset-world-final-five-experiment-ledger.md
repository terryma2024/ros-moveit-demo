# SO-101 MuJoCo RESET_WORLD Final Five Experiment Ledger

```yaml
task_id: so101-mujoco-reset-world-final-five
goal: Complete the final exact five-consecutive-success RESET_WORLD challenge on ai-station, merge the qualified feature branch into ai-station local main, and verify local main without any remote push.
success_contract: Exactly five serial VALID SUCCESS records on one unchanged non-headless stack, with reset epochs 1 through 5, one simulation_session_id, the frozen runtime fingerprint and policies, complete nine-phase traces, successful physical and Planning Scene outcomes, clean shutdown, and no owned-process residue.
worktree: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
branch: codex/so101-mujoco-ros2-teleop
base_commit: 302c4ef9550e036f127111e473f44a823b1ab643
current_commit: 302c4ef9550e036f127111e473f44a823b1ab643
evidence_root: /data/work/so101-debug-mujoco-maintainability-remediation/reset-world-exp136-140
confirmed_conclusions:
  - MNT-CP-057 terminated MNT-Q-RESET-EXP131-135 permanently after EXP-131 used high-rate evidence on the slow /tmp volume and the old runner continued into polluted EXP-132/133 attempts.
  - Commit 302c4ef9550e036f127111e473f44a823b1ab643 makes fixed target-count qualification stop after the first VALID_FAILURE or INVALID record; its 20 qualification contract tests and Ruff gate passed before this challenge.
  - EXP-126 through EXP-130 established five FULL_RESTART successes using the /data/work NVMe evidence volume and the same frozen runtime fingerprint.
  - The exact diagnostic-only phase-aware proposal SHA-256 4391efe670f7c881667434706a2ed40b7d33ea6a8d7908c64796d01f177c848f is approved as evidence only and is forbidden as a runtime contact policy.
disproven_routes:
  - High-rate lossless evidence under /tmp backed by /dev/sda3; EXP-131 observed a chunk sequence mismatch.
  - Continuing a fixed five-run batch after its first non-SUCCESS record; EXP-132/133 were polluted follow-on attempts and cannot count.
open_hypotheses: []
latest_checkpoint: RESET-FIVE-CP-001
next_experiment: EXP-136
```

## Immutable challenge boundary

```yaml
batch_id: MNT-Q-RESET-EXP136-140
experiments: [EXP-136, EXP-137, EXP-138, EXP-139, EXP-140]
lifecycle: RESET_WORLD
target_count: 5
shared_stack_count: 1
shared_simulation_session_id: MNT-Q-RESET-EXP136-140-reset
ros_domain_id: 204
teleop_port: 8044
gz_partition: NOT_APPLICABLE_MUJOCO_RUNTIME
expected_reset_epochs: [1, 2, 3, 4, 5]
evidence_root: /data/work/so101-debug-mujoco-maintainability-remediation/reset-world-exp136-140
evidence_root_pre_registration_state: ABSENT
evidence_filesystem:
  source: /dev/nvme0n1p5
  mount_target: /data
  filesystem: ext4
runtime_fingerprint_file: /tmp/so101-debug-mujoco-maintainability-remediation/exp126-five-run-runtime-fingerprint.json
runtime_fingerprint_file_sha256: 76d232a44949c1750a771a57d3f1026c8321637e9d41fe110fc3d72e88f4867c
frozen_runtime_source_commit: d30bf2bd54ea9359d08b866cdda447dfe2a3c271
fork_commit: 738e304551b4ea6db020b466086a13db71b65607
fork_tag: so101-0.0.3-r6
motion_policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
contact_policy_sha256: c4ba607fea92f7c605fbc8cf08df0dfa3278113c71d1dd6ff10ea402e8186f82
diagnostic_only_proposal_sha256: 4391efe670f7c881667434706a2ed40b7d33ea6a8d7908c64796d01f177c848f
diagnostic_proposal_runtime_activation: FORBIDDEN
single_variable: Lifecycle changes from the accepted FULL_RESTART baseline to RESET_WORLD; runtime strategy and all behavior inputs remain unchanged.
strategy_changes_forbidden:
  - thresholds
  - targets
  - timing
  - speed
  - replanning
  - delay
  - contact policy
  - grasp policy
failure_rule: The first non-SUCCESS record immediately terminates execution. Any VALID_FAILURE or INVALID makes the entire fixed batch unqualified. EXP-136 through EXP-140 are never reused; a new attempt requires fresh monotonically increasing experiment IDs, a new batch ID, a new absent evidence directory, and prior ledger registration.
counting_boundary: Only the single run_qualification invocation preregistered below may contribute to the exact 5/5 result. Any later visual corroboration cycle is explicitly non-counting.
remote_boundary: Fetch and read-only remote review are allowed after 5/5. No branch or main push is authorized in this task. Final state REMOTE_PUSH_REVIEW_REQUIRED must be recorded on local main.
```

## Preregistered command

```yaml
command: >-
  ros2 run so101_mujoco_demo_py run_qualification
  --batch-id MNT-Q-RESET-EXP136-140
  --lifecycle RESET_WORLD
  --count 5
  --fingerprint /tmp/so101-debug-mujoco-maintainability-remediation/exp126-five-run-runtime-fingerprint.json
  --evidence-root /data/work/so101-debug-mujoco-maintainability-remediation/reset-world-exp136-140
  --base-domain-id 204
  --base-port 8044
  --no-headless
shell_contract:
  - source ~/gui-env.zsh
  - source /opt/ros/jazzy/setup.zsh
  - source /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install/setup.zsh
  - source /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/setup.zsh
  - export PYTHONDONTWRITEBYTECODE=1
tmux_session: MNT-Q-RESET-EXP136-140
invocation_count: 1
hidden_retries: FORBIDDEN
exit_code: PENDING
manifest: /data/work/so101-debug-mujoco-maintainability-remediation/reset-world-exp136-140/qualification-manifest.json
manifest_sha256: PENDING
```

## Experiments EXP-136 through EXP-140

Each record below is frozen before stack startup. The qualification manifest uses batch ordinal
records `MNT-Q-RESET-EXP136-140-01` through `-05`; this ledger maps those ordinals one-to-one to
the permanent experiment IDs below.

```yaml
- experiment_id: EXP-136
  manifest_record_id: MNT-Q-RESET-EXP136-140-01
  status: PLANNED
  prior_experiment: EXP-131
  hypothesis: The frozen production workflow completes after transactional reset epoch 1 when lossless high-rate evidence is provisioned on the qualified NVMe volume.
  prediction: Nine phases complete; physical outcome succeeds; Gazebo/MuJoCo truth and the MoveIt Planning Scene end detached with the cup upright in the target ring.
  single_variable: NONE_FROZEN_CONFIGURATION_REVALIDATION
  lifecycle: RESET_WORLD
  expected_reset_epoch: 1
  preconditions: [fresh shared stack, frozen fingerprint, READY health, active controllers, initial cup and Planning Scene world membership]
  success_criteria: [status SUCCESS, exact nine-phase trace, physical primary_failure null, Planning Scene detached/world synchronized, clean shared-stack shutdown after the batch]
  failure_criteria: [any valid physical or workflow failure]
  invalid_criteria: [provenance mismatch, stale evidence, missing artifact, epoch/session mismatch, incomplete clean shutdown, evidence-volume or process contamination]
  provenance: {source_commit: d30bf2bd54ea9359d08b866cdda447dfe2a3c271, install_overlay: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install, runtime_executable: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/so101_mujoco_demo_py/lib/so101_mujoco_demo_py/run_qualification, ros_domain_id: 204, gz_partition: NOT_APPLICABLE_MUJOCO_RUNTIME}
  observed: [PENDING]
  conclusion: PENDING
  decision: PENDING
  next_experiment: EXP-137
- experiment_id: EXP-137
  manifest_record_id: MNT-Q-RESET-EXP136-140-02
  status: PLANNED
  prior_experiment: EXP-136
  hypothesis: The same shared stack repeats the frozen successful outcome after reset epoch 2 without stale attachment, checkpoint, lease, or evidence state.
  prediction: The second independent nine-phase workflow succeeds with the same session and strictly increasing epoch.
  single_variable: NONE_FROZEN_CONFIGURATION_REVALIDATION
  lifecycle: RESET_WORLD
  expected_reset_epoch: 2
  preconditions: [EXP-136 SUCCESS, same stack and session, transactional reset proof]
  success_criteria: [status SUCCESS, exact nine-phase trace, successful physical outcome, detached/world-synchronized Planning Scene]
  failure_criteria: [any valid physical or workflow failure]
  invalid_criteria: [any challenge contract contamination]
  provenance: {source_commit: d30bf2bd54ea9359d08b866cdda447dfe2a3c271, install_overlay: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install, runtime_executable: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/so101_mujoco_demo_py/lib/so101_mujoco_demo_py/run_qualification, ros_domain_id: 204, gz_partition: NOT_APPLICABLE_MUJOCO_RUNTIME}
  observed: [PENDING]
  conclusion: PENDING
  decision: PENDING
  next_experiment: EXP-138
- experiment_id: EXP-138
  manifest_record_id: MNT-Q-RESET-EXP136-140-03
  status: PLANNED
  prior_experiment: EXP-137
  hypothesis: The same shared stack repeats the frozen successful outcome after reset epoch 3 without accumulated runtime state.
  prediction: The third independent nine-phase workflow succeeds with the same session and strictly increasing epoch.
  single_variable: NONE_FROZEN_CONFIGURATION_REVALIDATION
  lifecycle: RESET_WORLD
  expected_reset_epoch: 3
  preconditions: [EXP-136 and EXP-137 SUCCESS, same stack and session, transactional reset proof]
  success_criteria: [status SUCCESS, exact nine-phase trace, successful physical outcome, detached/world-synchronized Planning Scene]
  failure_criteria: [any valid physical or workflow failure]
  invalid_criteria: [any challenge contract contamination]
  provenance: {source_commit: d30bf2bd54ea9359d08b866cdda447dfe2a3c271, install_overlay: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install, runtime_executable: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/so101_mujoco_demo_py/lib/so101_mujoco_demo_py/run_qualification, ros_domain_id: 204, gz_partition: NOT_APPLICABLE_MUJOCO_RUNTIME}
  observed: [PENDING]
  conclusion: PENDING
  decision: PENDING
  next_experiment: EXP-139
- experiment_id: EXP-139
  manifest_record_id: MNT-Q-RESET-EXP136-140-04
  status: PLANNED
  prior_experiment: EXP-138
  hypothesis: The same shared stack repeats the frozen successful outcome after reset epoch 4 without accumulated runtime state.
  prediction: The fourth independent nine-phase workflow succeeds with the same session and strictly increasing epoch.
  single_variable: NONE_FROZEN_CONFIGURATION_REVALIDATION
  lifecycle: RESET_WORLD
  expected_reset_epoch: 4
  preconditions: [EXP-136 through EXP-138 SUCCESS, same stack and session, transactional reset proof]
  success_criteria: [status SUCCESS, exact nine-phase trace, successful physical outcome, detached/world-synchronized Planning Scene]
  failure_criteria: [any valid physical or workflow failure]
  invalid_criteria: [any challenge contract contamination]
  provenance: {source_commit: d30bf2bd54ea9359d08b866cdda447dfe2a3c271, install_overlay: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install, runtime_executable: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/so101_mujoco_demo_py/lib/so101_mujoco_demo_py/run_qualification, ros_domain_id: 204, gz_partition: NOT_APPLICABLE_MUJOCO_RUNTIME}
  observed: [PENDING]
  conclusion: PENDING
  decision: PENDING
  next_experiment: EXP-140
- experiment_id: EXP-140
  manifest_record_id: MNT-Q-RESET-EXP136-140-05
  status: PLANNED
  prior_experiment: EXP-139
  hypothesis: The fifth unchanged reset epoch completes the exact five-consecutive-success RESET_WORLD challenge.
  prediction: The fifth independent nine-phase workflow succeeds and the fixed batch summary reports attempt_count 5, consecutive_successes 5, qualified true, and batch_invalid false.
  single_variable: NONE_FROZEN_CONFIGURATION_REVALIDATION
  lifecycle: RESET_WORLD
  expected_reset_epoch: 5
  preconditions: [EXP-136 through EXP-139 SUCCESS, same stack and session, transactional reset proof]
  success_criteria: [status SUCCESS, exact nine-phase trace, successful physical outcome, detached/world-synchronized Planning Scene, exact qualified 5/5 summary]
  failure_criteria: [any valid physical or workflow failure]
  invalid_criteria: [any challenge contract contamination]
  provenance: {source_commit: d30bf2bd54ea9359d08b866cdda447dfe2a3c271, install_overlay: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install, runtime_executable: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/so101_mujoco_demo_py/lib/so101_mujoco_demo_py/run_qualification, ros_domain_id: 204, gz_partition: NOT_APPLICABLE_MUJOCO_RUNTIME}
  observed: [PENDING]
  conclusion: PENDING
  decision: PENDING
  next_experiment: NONE
```

## Checkpoint RESET-FIVE-CP-001 — fresh batch preregistered

```yaml
checkpoint_id: RESET-FIVE-CP-001
recorded_at: 2026-08-13T01:22:48+08:00
last_valid_experiment: EXP-130
current_hypothesis: The previously frozen successful workflow will remain lossless and repeatable for five RESET_WORLD epochs when all high-rate evidence is written to the qualified NVMe volume.
working_tree_status: Only the two protected user documents were untracked before this new ledger was added; they remain byte-preserved and unstaged.
owned_processes: NONE
preserved_processes:
  - tmux session codex
  - idle tmux session codex-cua
  - historical tmux session so101-mujoco-gui and all its windows
confirmed_conclusions:
  - Source checkout is AI-STATION-001 at 302c4ef9550e036f127111e473f44a823b1ab643 on codex/so101-mujoco-ros2-teleop.
  - The ROS graph on domain 204 is empty and no live MuJoCo, move_group, RViz, workflow, or qualification process was observed.
  - The evidence root did not exist before preregistration; its parent filesystem is /dev/nvme0n1p5 mounted at /data.
  - Runtime fingerprint file SHA-256 is 76d232a44949c1750a771a57d3f1026c8321637e9d41fe110fc3d72e88f4867c.
disproven_routes:
  - Reusing EXP-131 through EXP-135 or their old /tmp evidence root.
  - Starting later batch records after a non-SUCCESS result.
open_risks:
  - Live five-run result and fresh CUA corroboration remain pending.
protected_user_state:
  ordinary_so101_gazebo_demo_py_pyc_count: 24
  additional_so101_gazebo_demo_script_pyc_count: 2
  pyc_deleted: false
  preserved_untracked_documents:
    - docs/experiments/so101-gazebo-mujoco-policy-parity-solver-iters-ledger.md
    - docs/experiments/so101-mujoco-ros2-migration-experiment-summary.md
next_command: Commit this preregistration before build or stack startup.
```
