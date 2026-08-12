# SO-101 MuJoCo RESET_WORLD Final Five Experiment Ledger

```yaml
task_id: so101-mujoco-reset-world-final-five
goal: Complete the final exact five-consecutive-success RESET_WORLD challenge on ai-station, merge the qualified feature branch into ai-station local main, and verify local main without any remote push.
success_contract: Exactly five serial VALID SUCCESS records on one unchanged non-headless stack, with reset epochs 1 through 5, one simulation_session_id, the frozen runtime fingerprint and policies, complete nine-phase traces, successful physical and Planning Scene outcomes, clean shutdown, and no owned-process residue.
worktree: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
branch: codex/so101-mujoco-ros2-teleop
base_commit: 302c4ef9550e036f127111e473f44a823b1ab643
current_commit: 34e2000b15227d1bcb6ec67d482d78e5354b0918
evidence_root: /data/work/so101-debug-mujoco-maintainability-remediation/reset-world-exp141-145
confirmed_conclusions:
  - MNT-CP-057 terminated MNT-Q-RESET-EXP131-135 permanently after EXP-131 used high-rate evidence on the slow /tmp volume and the old runner continued into polluted EXP-132/133 attempts.
  - Commit 302c4ef9550e036f127111e473f44a823b1ab643 makes fixed target-count qualification stop after the first VALID_FAILURE or INVALID record; its 20 qualification contract tests and Ruff gate passed before this challenge.
  - EXP-126 through EXP-130 established five FULL_RESTART successes using the /data/work NVMe evidence volume and the same frozen runtime fingerprint.
  - The exact diagnostic-only phase-aware proposal SHA-256 4391efe670f7c881667434706a2ed40b7d33ea6a8d7908c64796d01f177c848f is approved as evidence only and is forbidden as a runtime contact policy.
disproven_routes:
  - High-rate lossless evidence under /tmp backed by /dev/sda3; EXP-131 observed a chunk sequence mismatch.
  - Continuing a fixed five-run batch after its first non-SUCCESS record; EXP-132/133 were polluted follow-on attempts and cannot count.
open_hypotheses: []
latest_checkpoint: RESET-FIVE-CP-009
next_experiment: EXP-142
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
exit_code: 1
manifest: /data/work/so101-debug-mujoco-maintainability-remediation/reset-world-exp136-140/qualification-manifest.json
manifest_sha256: cdd932110c84eb67fcd77f185490a081b4a273b8a66d9aa21727633edb969ffa
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
  status: VALID
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
  observed:
    - SUCCESS; reset epoch 3; unchanged simulation session; exact nine-phase trace and fresh checkpoint.
    - Physical primary_failure null; moveit_attached false; world_object_synchronized true; intended support retained and gripper contact absent.
    - Final cup pose [-0.07956426011483758, -0.2462792849843199, 0.1654739580668193] m; upright tilt 0.017368007192561315 rad.
    - actions SHA-256 1e241904ef80f705a4d22e3a35909c36c7de6dc86c100a388bfeb29299dff09a.
    - owner manifest SHA-256 8984a44b9df464ad79d006fe6c74bf19e68138741e38e0ba30c0a3ab9b1da849.
    - raw run-index SHA-256 c16ab3137fdec7f52488fe12e4c64a261a84f434b30d99a6cd1d124b9e2ab973.
    - dynamic summary SHA-256 0daebc24632e1e7a58675ad3135edf41af1b7315244ad6ec8a5561901b2905b6.
    - Shared launch log SHA-256 is deferred until clean shutdown closes the common file.
  conclusion: VALID SUCCESS 3/5 in the frozen RESET_WORLD batch.
  decision: KEEP
  next_experiment: EXP-139
- experiment_id: EXP-139
  manifest_record_id: MNT-Q-RESET-EXP136-140-04
  status: VALID
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
  observed:
    - SUCCESS; reset epoch 4; unchanged simulation session; exact nine-phase trace and fresh checkpoint.
    - Physical primary_failure null; moveit_attached false; world_object_synchronized true; intended support retained and gripper contact absent.
    - Final cup pose [-0.07943893586054612, -0.24690689413099687, 0.16537425718711438] m; upright tilt 0.017384344672837507 rad.
    - actions SHA-256 dd101000a3d8ea1a7a4a14263299acda990eca40ad1e8847e805572e1be7619f.
    - owner manifest SHA-256 7730c49326663423592fa9200d7696acc54785d0b669d8788161bcc28b982a4b.
    - raw run-index SHA-256 3e92965a395b0a650eda5067b8bd2346e3aeeff66dbbd86831d74718948a254a.
    - dynamic summary SHA-256 1be12fda32c1608c21d8ca21f64e7ac356eafd30184c44f6663aa00d8cf3b235.
    - Shared launch log SHA-256 is deferred until clean shutdown closes the common file.
  conclusion: VALID SUCCESS 4/5 in the frozen RESET_WORLD batch.
  decision: KEEP
  next_experiment: EXP-140
- experiment_id: EXP-140
  manifest_record_id: MNT-Q-RESET-EXP136-140-05
  status: INVALID
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
  observed:
    - Reset service succeeded from epoch 4 to epoch 5 for the unchanged session, with simulation_step 0.
    - The immediately following workflow owner returned HTTP 503 before staged_approach with owner_failure_code STALE_OR_MISMATCHED_MUJOCO_EVIDENCE.
    - Owner diagnostic reports fresh atomic MuJoCo evidence unavailable; no fifth workflow evidence directory, owner manifest, raw run-index, or dynamic summary exists.
    - actions SHA-256 4ebebc5ba31d0eaab2ff83c7094131b54916b174822ff730625eb62cda4a160b.
    - failure SHA-256 20041322d0d39188491472913071065fef2a14f6b5d18b6effff198100e44b56.
    - preserved owner diagnostic SHA-256 912579658d5da94c90116cfb0cd28a81916e6174f82d5a4dfab6059dd7a8f6e2.
    - Shared stack shutdown passed with ordered marker and no process-died or fatal-signal marker.
  conclusion: INVALID before the first workflow phase; this terminates MNT-Q-RESET-EXP136-140 at four consecutive successes and cannot be counted as a product failure.
  decision: ABANDON
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

## Checkpoint RESET-FIVE-CP-005 — MNT-Q-RESET-EXP136-140 terminal INVALID

```yaml
checkpoint_id: RESET-FIVE-CP-005
recorded_at: 2026-08-13T01:36:47+08:00
prior_checkpoint: RESET-FIVE-CP-004
status: TERMINAL_INVALID
batch:
  batch_id: MNT-Q-RESET-EXP136-140
  lifecycle: RESET_WORLD
  experiments: [EXP-136, EXP-137, EXP-138, EXP-139, EXP-140]
  identifiers_reusable: false
  attempt_count: 5
  successful_runs: [EXP-136, EXP-137, EXP-138, EXP-139]
  invalid_run: EXP-140
  consecutive_successes: 4
  qualified: false
  batch_invalid: true
  reset_epochs_observed_from_actions: [1, 2, 3, 4, 5]
  manifest_record_epochs: [1, 2, 3, 4, -1]
  manifest_secondary_invalid_reason: run 5 reset epoch did not increase
  primary_invalid_reason: The workflow owner could not acquire a fresh atomic MuJoCo snapshot after the successful epoch-5 reset.
  simulation_session_id: MNT-Q-RESET-EXP136-140-reset
  manifest: /data/work/so101-debug-mujoco-maintainability-remediation/reset-world-exp136-140/qualification-manifest.json
  manifest_sha256: cdd932110c84eb67fcd77f185490a081b4a273b8a66d9aa21727633edb969ffa
  runner_log_sha256: d796644c256d69bb3fdf04001f1e7ad6921be53ae83a0046e6471565ad53d09c
  shared_launch_log_sha256: 03360c7ecc49728ea435b5b2d546f255ed2400487fa0ab2847b897e267705cf4
  runner_exit_code: 1
  clean_shutdown: true
  ordered_shutdown_marker: true
  owned_processes_after_probe: NONE
  ros_domain_204_nodes_after_probe: NONE
artifact_contract:
  EXP-136: {actions: ebbb44abbf98b80d877dc69b77d01333f16a460377c6ecd324d9efefa1a62fe6, owner_manifest: 9de471de921f6e15ec68d95402488c0f4b147b9a5235e094a408a3eab7566be3, raw_run_index: 86345dbd2e8df2f10677fe59b09f5d243cae5549bf81fd4f153b8c0a0f58e73e, dynamic_summary: a8c51bd110f25f831e4cbf664c12072fa2ded0b961ae8fa52cfb522a3a06101b, launch_log: 03360c7ecc49728ea435b5b2d546f255ed2400487fa0ab2847b897e267705cf4}
  EXP-137: {actions: bd561ba517a039e1e2669d0ff4dfe0701ede7e0ff1a506334148af6c0732a550, owner_manifest: 79f2389020b2544d3acaa90788ff3da2a51503215adc951c1b42345a6c3d44dc, raw_run_index: 2e3ebd39b74bb7039bb542cec381b830a9a92c0f9f175a4a1960058641e8fdee, dynamic_summary: 0261e227b1064831173bb0ab4d14cf37f7936200b99646eaa6dac81ae779df17, launch_log: 03360c7ecc49728ea435b5b2d546f255ed2400487fa0ab2847b897e267705cf4}
  EXP-138: {actions: 1e241904ef80f705a4d22e3a35909c36c7de6dc86c100a388bfeb29299dff09a, owner_manifest: 8984a44b9df464ad79d006fe6c74bf19e68138741e38e0ba30c0a3ab9b1da849, raw_run_index: c16ab3137fdec7f52488fe12e4c64a261a84f434b30d99a6cd1d124b9e2ab973, dynamic_summary: 0daebc24632e1e7a58675ad3135edf41af1b7315244ad6ec8a5561901b2905b6, launch_log: 03360c7ecc49728ea435b5b2d546f255ed2400487fa0ab2847b897e267705cf4}
  EXP-139: {actions: dd101000a3d8ea1a7a4a14263299acda990eca40ad1e8847e805572e1be7619f, owner_manifest: 7730c49326663423592fa9200d7696acc54785d0b669d8788161bcc28b982a4b, raw_run_index: 3e92965a395b0a650eda5067b8bd2346e3aeeff66dbbd86831d74718948a254a, dynamic_summary: 1be12fda32c1608c21d8ca21f64e7ac356eafd30184c44f6663aa00d8cf3b235, launch_log: 03360c7ecc49728ea435b5b2d546f255ed2400487fa0ab2847b897e267705cf4}
  EXP-140: {actions: 4ebebc5ba31d0eaab2ff83c7094131b54916b174822ff730625eb62cda4a160b, owner_manifest: ABSENT_PREPHASE_INVALID, raw_run_index: ABSENT_PREPHASE_INVALID, dynamic_summary: ABSENT_PREPHASE_INVALID, failure: 20041322d0d39188491472913071065fef2a14f6b5d18b6effff198100e44b56, owner_diagnostic: 912579658d5da94c90116cfb0cd28a81916e6174f82d5a4dfab6059dd7a8f6e2, launch_log: 03360c7ecc49728ea435b5b2d546f255ed2400487fa0ab2847b897e267705cf4}
visual_process_evidence:
  screenshot: /data/work/so101-debug-mujoco-maintainability-remediation/reset-world-exp136-140/cua-run4-baseline.png
  screenshot_sha256: 8c39212ad1ba6769abdc629befe08620508e12ee64fd714edda83b9999e63d43
  interpretation: Fresh CUA process frame during EXP-139 showed the running MuJoCo Viewer with robot, pedestal, table, cup, and red ring; it is not a final-success acceptance image and does not count toward 5/5.
first_bad_boundary:
  observed: The epoch-5 transactional reset succeeded and the next workflow owner failed before staged_approach because current_evidence timed out without accepting a fresh atomic snapshot.
  hypothesis: current_evidence creates a new best-effort volatile subscription and immediately requests a pause snapshot before discovery is guaranteed; if that single paused publication is missed, the paused simulator emits no replacement and the five-second observer loop expires.
  competing_hypotheses:
    - Publisher stopped or wrong session after reset; less likely because reset receipt and four prior workflows used the same live publisher/session and shutdown remained clean.
    - Evidence was rejected as truncated or out of order; less likely because the diagnostic says no fresh atomic evidence rather than a conversion/rejection message, but callback counters were not persisted.
  classification: HYPOTHESIS_PENDING_RED_GREEN_AB_TEST
allowed_fix_boundary: Evidence subscriber/publisher discovery synchronization only; no robot motion, policy, threshold, target, timing, speed, replanning, delay, contact, or grasp behavior may change.
protected_user_state:
  ordinary_gazebo_pyc_count: 24
  pyc_deleted: false
  protected_documents_byte_hashes_unchanged: true
merge_state: NOT_AUTHORIZED_BATCH_NOT_QUALIFIED
remote_push_state: FORBIDDEN
next_experiment: NEW_BATCH_AFTER_EVIDENCE_DISCOVERY_FIX
next_command: Add a failing unit contract for pause-snapshot discovery, implement the minimum evidence-discovery synchronization, rebuild/test, then preregister fresh EXP-141 through EXP-145 on a new absent NVMe evidence root.
```

## Checkpoint RESET-FIVE-CP-006 — evidence discovery race fixed RED to GREEN

```yaml
checkpoint_id: RESET-FIVE-CP-006
recorded_at: 2026-08-13T01:43:00+08:00
prior_checkpoint: RESET-FIVE-CP-005
status: FIX_GREEN_PENDING_REBUILD_AND_NEW_BATCH_PREREGISTRATION
root_cause:
  classification: CONFIRMED
  first_bad_boundary: A newly created best-effort volatile evidence subscription could trigger the one-shot paused snapshot before DDS publisher discovery, miss that publication, and then time out because physics remained paused.
  excluded_alternatives:
    - Robot strategy failure: EXP-136 through EXP-139 completed the unchanged nine-phase physical workflow successfully.
    - Reset service failure: EXP-140 actions contain a successful epoch-4 to epoch-5 receipt at simulation_step 0.
    - Slow evidence volume: all high-rate artifacts for the four workflows were lossless on /dev/nvme0n1p5; EXP-140 failed before high-rate collection.
red_test:
  name: test_pause_snapshot_waits_for_evidence_publisher_discovery
  result: FAIL_AS_EXPECTED
  first_failure: pause called before evidence discovery
green_tests:
  result: PASS
  summary: 59 passed
  scope: [Teleop owner, MuJoCo observer, MuJoCo reset, qualification]
ruff: {result: PASS, summary: All checks passed; 131 files already formatted}
change:
  - Expose the live ROS subscription publisher count from MujocoWorldObserver.
  - Before requesting the pause snapshot, spin only until the subscription has discovered its publisher or the existing timeout expires.
fixed_sleep_added: false
behavior_changes:
  motion_policy: NONE
  contact_policy: NONE
  thresholds_targets_timing_speed_replanning_delay_grasp: NONE
protected_user_state:
  ordinary_gazebo_pyc_count: 24
  pyc_deleted: false
  protected_documents_byte_hashes_unchanged: true
next_experiment: NEW_BATCH_AFTER_REBUILD_AND_PREREGISTRATION
next_command: Commit this evidence-boundary fix, rebuild and probe the three packages, then preregister EXP-141 through EXP-145 with a new batch ID and absent NVMe evidence root before startup.
```

## Checkpoint RESET-FIVE-CP-007 — rebuilt fix and registered frozen artifact

```yaml
checkpoint_id: RESET-FIVE-CP-007
recorded_at: 2026-08-13T01:44:00+08:00
prior_checkpoint: RESET-FIVE-CP-006
status: READY_FOR_FRESH_BATCH_PREREGISTRATION
fix_commit: 1b49979824b89fe7d333b393a02208ca7550219d
build:
  packages: [so101_teleop, so101_mujoco_support, so101_mujoco_demo_py]
  result: PASS
  summary: 3 packages finished
focused_tests:
  result: PASS
  summary: 79 passed, 1 skipped
  scope:
    - mujoco reset unit contracts
    - reset live contract
    - qualification contract including fail-fast
    - Teleop owner contract including evidence-publisher discovery
    - MuJoCo launch contract
    - fork dependency contract
    - frozen behavior contract
    - diagnostic-only proposal contract
frozen_behavior_registration:
  first_gate_result: EXPECTED_REGISTRATION_FAILURE
  first_gate_reason: The verifier correctly detected observer.py and teleop_runtime.py as changed instrumentation files not yet named by the frozen-behavior allowlist.
  correction: Add only those two evidence-plumbing paths to the frozen manifest and update the manifest's pinned test hash.
  runtime_behavior_change: NONE
  manifest_sha256: d74395d79ea62246656f820abe0cba54b3f18cf8104e735e2c7b91e196dc2c5b
  instrumentation_diff_gate: MATCH
  transport_semantics: MATCH
  frozen_runtime_artifact_diff: NONE
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
behavior_changes:
  motion_policy: NONE
  contact_policy: NONE
  thresholds_targets_timing_speed_replanning_delay_grasp: NONE
protected_user_state:
  ordinary_gazebo_pyc_count: 24
  pyc_deleted: false
  protected_documents_byte_hashes_unchanged: true
next_experiment: EXP-141
next_command: Commit the frozen artifact registration, then preregister EXP-141 through EXP-145 before any stack startup.
remote_push_state: FORBIDDEN
```

## Fresh immutable challenge boundary — MNT-Q-RESET-EXP141-145

```yaml
batch_id: MNT-Q-RESET-EXP141-145
experiments: [EXP-141, EXP-142, EXP-143, EXP-144, EXP-145]
lifecycle: RESET_WORLD
target_count: 5
shared_stack_count: 1
shared_simulation_session_id: MNT-Q-RESET-EXP141-145-reset
ros_domain_id: 205
teleop_port: 8045
gz_partition: NOT_APPLICABLE_MUJOCO_RUNTIME
expected_reset_epochs: [1, 2, 3, 4, 5]
evidence_root: /data/work/so101-debug-mujoco-maintainability-remediation/reset-world-exp141-145
evidence_root_pre_registration_state: ABSENT
evidence_filesystem: {source: /dev/nvme0n1p5, mount_target: /data, filesystem: ext4}
engineering_source_commit: 34e2000b15227d1bcb6ec67d482d78e5354b0918
evidence_discovery_fix_commit: 1b49979824b89fe7d333b393a02208ca7550219d
runtime_fingerprint_file: /tmp/so101-debug-mujoco-maintainability-remediation/exp126-five-run-runtime-fingerprint.json
runtime_fingerprint_file_sha256: 76d232a44949c1750a771a57d3f1026c8321637e9d41fe110fc3d72e88f4867c
frozen_runtime_source_commit: d30bf2bd54ea9359d08b866cdda447dfe2a3c271
fork_commit: 738e304551b4ea6db020b466086a13db71b65607
fork_tag: so101-0.0.3-r6
frozen_behavior_manifest_sha256: d74395d79ea62246656f820abe0cba54b3f18cf8104e735e2c7b91e196dc2c5b
motion_policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
contact_policy_sha256: c4ba607fea92f7c605fbc8cf08df0dfa3278113c71d1dd6ff10ea402e8186f82
diagnostic_only_proposal_sha256: 4391efe670f7c881667434706a2ed40b7d33ea6a8d7908c64796d01f177c848f
diagnostic_proposal_runtime_activation: FORBIDDEN
single_variable_from_failed_batch: Synchronize evidence subscription discovery before the existing pause-snapshot transaction; runtime robot strategy and all behavior inputs remain unchanged.
strategy_changes_forbidden: [thresholds, targets, timing, speed, replanning, delay, contact policy, grasp policy]
failure_rule: The first non-SUCCESS record immediately terminates execution and makes this entire batch unqualified. EXP-141 through EXP-145 are never reused. Any later attempt requires new monotonically increasing IDs, a new batch ID, a new absent evidence directory, and prior ledger registration.
counting_boundary: Only the one preregistered run_qualification invocation below may contribute to this 5/5. Visual corroboration is non-counting.
remote_boundary: No remote push is authorized. Final state after a qualified local-main merge must be REMOTE_PUSH_REVIEW_REQUIRED.
```

## Preregistered counting command — MNT-Q-RESET-EXP141-145

```yaml
command: >-
  ros2 run so101_mujoco_demo_py run_qualification
  --batch-id MNT-Q-RESET-EXP141-145
  --lifecycle RESET_WORLD
  --count 5
  --fingerprint /tmp/so101-debug-mujoco-maintainability-remediation/exp126-five-run-runtime-fingerprint.json
  --evidence-root /data/work/so101-debug-mujoco-maintainability-remediation/reset-world-exp141-145
  --base-domain-id 205
  --base-port 8045
  --no-headless
shell_contract:
  - source ~/gui-env.zsh
  - source /opt/ros/jazzy/setup.zsh
  - source /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install/setup.zsh
  - source /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/setup.zsh
  - export PYTHONDONTWRITEBYTECODE=1
tmux_session: MNT-Q-RESET-EXP141-145
invocation_count: 1
hidden_retries: FORBIDDEN
```

## Preregistered experiments EXP-141 through EXP-145

The manifest ordinals `MNT-Q-RESET-EXP141-145-01` through `-05` map one-to-one to these permanent IDs.

```yaml
- experiment_id: EXP-141
  manifest_record_id: MNT-Q-RESET-EXP141-145-01
  status: PREREGISTERED
  hypothesis: Publisher discovery synchronization lets the unchanged frozen workflow acquire the epoch-1 atomic snapshot and complete normally.
  prediction: SUCCESS with reset epoch 1, the shared session ID, exact nine-phase trace, null physical primary_failure, and detached/world-synchronized Planning Scene.
  lifecycle: RESET_WORLD
  expected_reset_epoch: 1
  preconditions: [fresh shared stack, absent NVMe evidence root, frozen fingerprint and policies, empty domain and port]
  success_criteria: [SUCCESS, exact nine-phase trace, physical success, Planning Scene detached and world synchronized]
  failure_criteria: [any valid physical or workflow failure]
  invalid_criteria: [provenance mismatch, stale evidence, missing artifact, epoch or session mismatch, contamination]
- experiment_id: EXP-142
  manifest_record_id: MNT-Q-RESET-EXP141-145-02
  status: PREREGISTERED
  hypothesis: The same unchanged stack repeats successfully after reset epoch 2 without stale state.
  prediction: SUCCESS with epoch 2 and the same complete physical and Planning Scene contract.
  lifecycle: RESET_WORLD
  expected_reset_epoch: 2
  preconditions: [EXP-141 SUCCESS, same stack and session]
  success_criteria: [SUCCESS, exact nine-phase trace, physical success, Planning Scene detached and world synchronized]
  failure_criteria: [any valid physical or workflow failure]
  invalid_criteria: [any challenge contract contamination]
- experiment_id: EXP-143
  manifest_record_id: MNT-Q-RESET-EXP141-145-03
  status: PREREGISTERED
  hypothesis: The same unchanged stack repeats successfully after reset epoch 3 without accumulated runtime state.
  prediction: SUCCESS with epoch 3 and the same complete physical and Planning Scene contract.
  lifecycle: RESET_WORLD
  expected_reset_epoch: 3
  preconditions: [EXP-141 and EXP-142 SUCCESS, same stack and session]
  success_criteria: [SUCCESS, exact nine-phase trace, physical success, Planning Scene detached and world synchronized]
  failure_criteria: [any valid physical or workflow failure]
  invalid_criteria: [any challenge contract contamination]
- experiment_id: EXP-144
  manifest_record_id: MNT-Q-RESET-EXP141-145-04
  status: PREREGISTERED
  hypothesis: The same unchanged stack repeats successfully after reset epoch 4 without accumulated runtime state.
  prediction: SUCCESS with epoch 4 and the same complete physical and Planning Scene contract.
  lifecycle: RESET_WORLD
  expected_reset_epoch: 4
  preconditions: [EXP-141 through EXP-143 SUCCESS, same stack and session]
  success_criteria: [SUCCESS, exact nine-phase trace, physical success, Planning Scene detached and world synchronized]
  failure_criteria: [any valid physical or workflow failure]
  invalid_criteria: [any challenge contract contamination]
- experiment_id: EXP-145
  manifest_record_id: MNT-Q-RESET-EXP141-145-05
  status: PREREGISTERED
  hypothesis: The fifth unchanged reset epoch completes the exact five-consecutive-success challenge after the evidence-discovery fix.
  prediction: SUCCESS with epoch 5; qualification summary reports attempt_count 5, consecutive_successes 5, qualified true, and batch_invalid false.
  lifecycle: RESET_WORLD
  expected_reset_epoch: 5
  preconditions: [EXP-141 through EXP-144 SUCCESS, same stack and session]
  success_criteria: [SUCCESS, exact nine-phase trace, physical success, Planning Scene detached and world synchronized, exact qualified 5/5 summary]
  failure_criteria: [any valid physical or workflow failure]
  invalid_criteria: [any challenge contract contamination]
```

## Checkpoint RESET-FIVE-CP-008 — fresh batch preregistered

```yaml
checkpoint_id: RESET-FIVE-CP-008
recorded_at: 2026-08-13T01:45:00+08:00
prior_checkpoint: RESET-FIVE-CP-007
status: PREREGISTERED_NOT_STARTED
batch_id: MNT-Q-RESET-EXP141-145
working_tree_status: Only the two byte-preserved user documents are untracked outside this ledger update.
preflight:
  evidence_root_absent: PASS
  evidence_filesystem: /dev/nvme0n1p5 mounted at /data as ext4
  ros_domain_205_nodes: NONE
  tcp_port_8045_listener: NONE
  tmux_session_MNT_Q_RESET_EXP141_145: ABSENT
  owned_runtime_processes: NONE
  runtime_fingerprint_sha256: 76d232a44949c1750a771a57d3f1026c8321637e9d41fe110fc3d72e88f4867c
  motion_policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
  contact_policy_sha256: c4ba607fea92f7c605fbc8cf08df0dfa3278113c71d1dd6ff10ea402e8186f82
protected_user_state:
  ordinary_gazebo_pyc_count: 24
  pyc_deleted: false
  protected_documents_byte_hashes_unchanged: true
next_experiment: EXP-141
next_command: Commit this preregistration before creating the evidence root or starting the one counting invocation.
remote_push_state: FORBIDDEN
```

## Checkpoint RESET-FIVE-CP-009 — EXP-141 SUCCESS 1/5

```yaml
checkpoint_id: RESET-FIVE-CP-009
recorded_at: 2026-08-13T01:48:00+08:00
prior_checkpoint: RESET-FIVE-CP-008
status: COUNTING_BATCH_RUNNING_SUCCESS_1_OF_5
experiment_id: EXP-141
manifest_record_id: MNT-Q-RESET-EXP141-145-01
result: VALID_SUCCESS
reset: {old_epoch: 0, new_epoch: 1, simulation_step: 0, simulation_session_id: MNT-Q-RESET-EXP141-145-reset}
trace: [staged_approach, contact_hold, micro_lift, policy_lift_waypoint1, remaining_lift, transport, descend, place_alignment, release_retreat]
physical_outcome:
  primary_failure: null
  final_pose_m: [-0.07938832523854986, -0.24800968017934866, 0.16532105236725436]
  final_upright_tilt_rad: 0.017341376768601483
  intended_support_contact: true
  gripper_contact: false
planning_scene: {moveit_attached: false, world_object_synchronized: true}
artifacts_sha256:
  actions: fd4adf317913a44a3492cf41263a49084a86618cdec020f12e247b9ed80b0631
  owner_manifest: f5b1552c79e891febec610712ff58abbe8b6784cbab00f9dff8d220d7d554b22
  raw_run_index: cd24fad14e1d235674d74a1deb35bad2e3dc7d97987b24d53960f64624091f92
  dynamic_summary: 49c8947bbe5c408ff360ff1de7767b6fb08f0ce4230e7351a309280476508a2f
  shared_launch_log: DEFERRED_UNTIL_CLEAN_SHUTDOWN
next_experiment: EXP-142
remote_push_state: FORBIDDEN
```
