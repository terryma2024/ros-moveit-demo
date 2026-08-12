# SO-101 MuJoCo RESET_WORLD Final Five Experiment Ledger

```yaml
task_id: so101-mujoco-reset-world-final-five
goal: Complete the final exact five-consecutive-success RESET_WORLD challenge on ai-station, merge the qualified feature branch into ai-station local main, and verify local main without any remote push.
success_contract: Exactly five serial VALID SUCCESS records on one unchanged non-headless stack, with reset epochs 1 through 5, one simulation_session_id, the frozen runtime fingerprint and policies, complete nine-phase traces, successful physical and Planning Scene outcomes, clean shutdown, and no owned-process residue.
worktree: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
branch: codex/so101-mujoco-ros2-teleop
base_commit: 302c4ef9550e036f127111e473f44a823b1ab643
current_commit: eb7e3323cc7ab4cbf9d3cc34aa16ee4f80166a38
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
latest_checkpoint: RESET-FIVE-CP-004
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
  status: VALID
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
  observed:
    - SUCCESS; reset epoch 1; simulation_session_id MNT-Q-RESET-EXP136-140-reset.
    - Exact nine-phase trace completed and checkpoint_fresh was true.
    - Physical primary_failure was null; moveit_attached false; world_object_synchronized true; intended_support_contact true; gripper_contact false.
    - Final cup pose was [-0.0795477441285091, -0.24844227651236556, 0.16532876395858584] m with upright tilt 0.01749758371864703 rad.
    - actions SHA-256 ebbb44abbf98b80d877dc69b77d01333f16a460377c6ecd324d9efefa1a62fe6.
    - owner manifest SHA-256 9de471de921f6e15ec68d95402488c0f4b147b9a5235e094a408a3eab7566be3.
    - raw run-index SHA-256 86345dbd2e8df2f10677fe59b09f5d243cae5549bf81fd4f153b8c0a0f58e73e.
    - dynamic summary SHA-256 a8c51bd110f25f831e4cbf664c12072fa2ded0b961ae8fa52cfb522a3a06101b.
    - Shared launch log SHA-256 is deferred until clean shutdown closes the common file.
  conclusion: VALID SUCCESS 1/5 in the frozen RESET_WORLD batch.
  decision: KEEP
  next_experiment: EXP-137
- experiment_id: EXP-137
  manifest_record_id: MNT-Q-RESET-EXP136-140-02
  status: VALID
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
  observed:
    - SUCCESS; reset epoch 2; unchanged simulation session; exact nine-phase trace and fresh checkpoint.
    - Physical primary_failure null; moveit_attached false; world_object_synchronized true; intended_support_contact true; gripper_contact false.
    - Final cup pose [-0.08020823295568298, -0.24698249983207335, 0.16540693501038675] m; upright tilt 0.017284985379184038 rad.
    - actions SHA-256 bd561ba517a039e1e2669d0ff4dfe0701ede7e0ff1a506334148af6c0732a550.
    - owner manifest SHA-256 79f2389020b2544d3acaa90788ff3da2a51503215adc951c1b42345a6c3d44dc.
    - raw run-index SHA-256 2e3ebd39b74bb7039bb542cec381b830a9a92c0f9f175a4a1960058641e8fdee.
    - dynamic summary SHA-256 0261e227b1064831173bb0ab4d14cf37f7936200b99646eaa6dac81ae779df17.
    - Shared launch log SHA-256 is deferred until clean shutdown closes the common file.
  conclusion: VALID SUCCESS 2/5 in the frozen RESET_WORLD batch.
  decision: KEEP
  next_experiment: EXP-138
- experiment_id: EXP-138
  manifest_record_id: MNT-Q-RESET-EXP136-140-03
  status: RUNNING
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

## Checkpoint RESET-FIVE-CP-002 — build and runtime preflight passed

```yaml
checkpoint_id: RESET-FIVE-CP-002
recorded_at: 2026-08-13T01:27:00+08:00
prior_checkpoint: RESET-FIVE-CP-001
preregistration_commit: a622f82ec331191363609e1b5a4a9d414862b232
status: READY_TO_START_SINGLE_COUNTING_INVOCATION
source_order:
  - /opt/ros/jazzy/setup.zsh
  - /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install/setup.zsh
  - /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/setup.zsh
build:
  packages: [so101_teleop, so101_mujoco_support, so101_mujoco_demo_py]
  result: PASS
  summary: 3 packages finished
  symlink_install: true
focused_tests:
  result: PASS
  summary: 78 passed, 1 skipped
  scope:
    - mujoco reset unit contracts
    - reset live contract
    - qualification contract including fail-fast
    - Teleop owner contract
    - MuJoCo launch contract
    - fork dependency contract
    - frozen behavior contract
    - diagnostic-only proposal contract
ruff:
  version: 0.15.20
  result: PASS
  summary: All checks passed; 131 files already formatted
backend_integration:
  result: PASS
  output: backend integration contract passed
fork_and_reset_runtime:
  result: PASS
  fork_commit: 738e304551b4ea6db020b466086a13db71b65607
  fork_tag: so101-0.0.3-r6
  fork_status: CLEAN
  reset_qualified_runtime_probe: PASS
  project_package_prefixes: ALL_CURRENT_PROJECT_INSTALL
  fork_package_prefixes: ALL_PINNED_FORK_INSTALL
frozen_behavior:
  verifier_result: PASS
  manifest_sha256: 2587388a204f58d12c072ede6005e45d167d2bd861135dcc1c3dadc13efa8dfd
  instrumentation_diff_gate: MATCH
  transport_semantics: MATCH
  frozen_runtime_artifact_diff: NONE
  dependency_sha256: be6bc595cd71a10df32765e11884183c0096db765a5ee35c3ef6a0b109ef5a3a
  task_scene_sha256: a2a49391e52d1f885e8ebb4c85fd282d1e83f0ce82eb63e83bac645343b1f9a0
  scene_sha256: b98eca6f2ae8547b8b7213625512ef360c5496c7ea2d124535698ea58b24e7c0
  robot_mjcf_sha256: f87a033fab8cf7291e737519290a639e0310e703f8169288f075f3fe0c8b5aca
  urdf_sha256: 0646707fbfb8fdfea5076afbf89f297027c0324465ab7ebe8129fc36c0445f4a
  motion_policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
  contact_policy_sha256: c4ba607fea92f7c605fbc8cf08df0dfa3278113c71d1dd6ff10ea402e8186f82
counting_evidence_root_after_preflight: ABSENT
owned_processes: NONE
protected_user_state:
  protected_documents_byte_hashes_unchanged: true
  pyc_deleted: false
next_experiment: EXP-136
next_command: Start the preregistered run_qualification command once in tmux session MNT-Q-RESET-EXP136-140 with non-headless GUI environment.
```

## Checkpoint RESET-FIVE-CP-003 — wrapper nounset failures preserved

```yaml
checkpoint_id: RESET-FIVE-CP-003
recorded_at: 2026-08-13T01:29:00+08:00
prior_checkpoint: RESET-FIVE-CP-002
status: READY_AFTER_NON_PRODUCT_WRAPPER_CORRECTION
non_product_wrapper_attempts:
  count: 2
  attempts:
    - detached tmux wrapper start
    - direct zsh trace mistakenly used for diagnosis and transparently counted here
  common_output: Package 'so101_mujoco_demo_py' not found
  first_bad_boundary: set -u caused gui-env/ROS/colcon setup scripts to encounter unset optional variables before complete project package registration.
  runner_python_entered: false
  stack_started: false
  reset_world_called: false
  experiment_id_consumed: false
  shared_stack_directory_created: false
  run_01_directory_created: false
  qualification_manifest_created: false
  hidden_retry: false
  retained_log: /data/work/so101-debug-mujoco-maintainability-remediation/reset-world-exp136-140/qualification-runner.log
  retained_log_size_bytes: 41
  retained_log_sha256: bdc5f46bd641e1b4e3621b1376791ea578fb2b18821a03b01190ba8cfd33e383
correction:
  wrapper: /tmp/so101-reset-final-five-run.zsh
  wrapper_sha256: e73592de360f6b6b026ef3e69e3f70c1e26d62e7717589773c305b394b2df8f3
  change: Remove nounset, fail explicitly on each source error, preserve the existing log with tee append, and print the true runner exit code.
  gui_shell_probe: PASS
  project_prefix: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/so101_mujoco_demo_py
  fork_prefix: /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install
batch_state:
  batch_id: MNT-Q-RESET-EXP136-140
  status: PLANNED_NOT_STARTED
  actual_runner_entry_count: 0
  experiments_consumed: []
  ids_reusable_within_this_preregistered_batch: true
  evidence_root_note: The root now contains only the preserved 41-byte wrapper failure log; the runner-owned shared-stack, run, and manifest paths remain absent.
owned_processes: NONE
next_experiment: EXP-136
next_command: Start the corrected wrapper once in tmux; this is the first attempt that may enter ProductionQualificationRunner and consume EXP-136.
```

## Checkpoint RESET-FIVE-CP-004 — counting runner entered

```yaml
checkpoint_id: RESET-FIVE-CP-004
recorded_at: 2026-08-13T01:29:11+08:00
prior_checkpoint: RESET-FIVE-CP-003
status: RUNNING
runner_entry_attempt: 1
tmux_session: MNT-Q-RESET-EXP136-140
wrapper_sha256: e73592de360f6b6b026ef3e69e3f70c1e26d62e7717589773c305b394b2df8f3
simulation_session_id: MNT-Q-RESET-EXP136-140-reset
ros_domain_id: 204
teleop_port: 8044
headless: false
health: READY
capability_owner: {backend: mujoco_py, package: so101_mujoco_demo_py, executable: pick_place_state_machine}
runtime_processes:
  qualification_entrypoint_pid: 2788356
  launch_pid: 2788357
  ros2_control_node_pid: 2788373
  move_group_pid: 2788377
first_experiment: EXP-136
first_reset_epoch_started: 1
evidence_volume: /dev/nvme0n1p5 mounted at /data
owned_process_cleanup_rule: Only the qualification runner's own process group and tmux session may be stopped; historical sessions remain untouched.
next_command: Monitor run-01 and owner evidence until the runner records SUCCESS or the first fail-fast terminal result.
```
