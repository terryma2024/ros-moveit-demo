# SO-101 MuJoCo Maintainability Remediation Experiment Ledger

```yaml
task_id: so101-mujoco-maintainability-remediation
goal: Replace migration experiment scaffolding with approved policy-driven state-machine production runtime and requalify it.
success_contract: All seven audit findings pass automated gates plus independent FULL_RESTART qualification and a fresh final five-consecutive-success RESET_WORLD challenge; only then merge this branch to main and push main to Gitee origin.
worktree: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
branch: codex/so101-mujoco-ros2-teleop
base_commit: 70bece06e008b27da8f0923472668e95a369309e
current_commit: ac9986cb96af6daac6459a404daa8b0aa08bc911
evidence_root: /tmp/so101-debug-mujoco-maintainability-remediation/
confirmed_conclusions:
  - CP-156: prior implementation passed the published five FULL_RESTART plus five RESET_WORLD simulation qualification.
  - AUDIT-001: contact_calibration.yaml is PLANNED/disabled while production phases hard-code contact limits.
  - AUDIT-002: execute bypasses StateMachineRunner and ignores public checkpoint controls.
disproven_routes:
  - Treating the prior 857-result colcon summary as a clean three-package result; it included 240 stale Gazebo tests.
open_hypotheses:
  - A bounded MoveIt translation along the model-derived gripper closing axis can produce repeatable physical left_only evidence without changing geometry or simulator state.
latest_checkpoint: MNT-CP-008
next_experiment: EXP-032
```

## Checkpoint MNT-CP-001

```yaml
checkpoint_id: MNT-CP-001
recorded_at: 2026-08-12T12:13:33+08:00
last_valid_experiment: NONE
current_hypothesis: A typed motion-policy loader can remove duplicated final-outcome data without changing existing physical evaluation behavior.
working_tree_status: Clean at 68c5ab1ab2cb4da62a26b6e521590db54aa14e01 before this ledger was created; dirty_paths_at_capture is NONE.
owned_processes: NONE
preserved_processes:
  - tmux session codex
  - tmux session codex-cua, idle after prior passive visual acceptance
  - tmux session so101-mujoco-gui with historical windows; no task-owned ROS process was observed
confirmed_conclusions:
  - OBSERVED: Host is AI-STATION-001 and the target checkout is a linked worktree on codex/so101-mujoco-ros2-teleop.
  - OBSERVED: Root and target worktrees were clean; fork submodule was f42b7b3d77288c2fee750fe53b0258e0a3d18194 at tag so101-0.0.3-r5.
  - OBSERVED: The ROS graph was empty and the process probe found no MuJoCo, move_group, RViz, pick-place, or ros2_control runtime process other than the probe shell itself.
disproven_routes:
  - Reusing the prior contaminated 857-test total as the clean Project D qualification count.
open_risks:
  - Exact contact thresholds remain uncalibrated and require a new seven-regime campaign plus explicit hash-bound user approval.
  - Projects B, C, and D remain pending after the Project A gate.
next_command: PYTHONNOUSERSITE=1 python3 -m pytest -q src/so101_mujoco_demo_py/test/test_task_policy.py
```

## Checkpoint MNT-CP-002

```yaml
checkpoint_id: MNT-CP-002
recorded_at: 2026-08-12T12:21:11+08:00
last_valid_experiment: NONE
current_hypothesis: A schema-v2 contact proposal can bind calibration evidence and approval without permitting an unapproved execute path.
working_tree_status: Clean at 120cefa069b96210db88a72678df10dc3983e380 after Project A Task 2.
owned_processes: NONE
preserved_processes:
  - Existing codex, codex-cua, and so101-mujoco-gui tmux sessions remain untouched.
confirmed_conclusions:
  - OBSERVED: The typed task-policy RED failed on the missing module and the YAML contract RED failed on missing physical_outcome.
  - OBSERVED: Three validator mutations for excessive scaling, zero sample count, and zero duration each failed before the minimal bounds were restored.
  - OBSERVED: Thirty-five affected tests passed; Ruff 0.15.20 lint and format checks passed.
  - OBSERVED: The motion YAML parses with one 11.60 N literal and compatibility aliases for the two legacy consumers.
  - USER-DIRECTIVE: After A through D, run a new frozen RESET_WORLD five-success streak. Only a valid 5/5 result authorizes merge to main and push of main to Gitee origin.
disproven_routes:
  - Invoking Ruff as /usr/bin/python3 -m ruff; the repository tool is the installed ruff 0.15.20 executable.
open_risks:
  - Contact calibration remains PLANNED and disabled; execute activation still requires exact hash-bound user approval.
  - The final RESET_WORLD challenge must not reuse historical qualification runs, and any INVALID or valid failure terminates its batch.
next_command: PYTHONNOUSERSITE=1 python3 -m pytest -q src/so101_mujoco_demo_py/test/test_contact_policy.py src/so101_mujoco_demo_py/test/test_contact_calibration_contract.py src/so101_mujoco_demo_py/test/test_contact_calibration_collector.py src/so101_mujoco_demo_py/test/test_task_policy.py
```

## Checkpoint MNT-CP-003

```yaml
checkpoint_id: MNT-CP-003
recorded_at: 2026-08-12T12:34:30+08:00
last_valid_experiment: NONE
current_hypothesis: A pure evaluator can distinguish a fresh bilateral stable grasp from every stale, unsafe, unilateral, slipping, or forbidden-contact window.
working_tree_status: Clean at b526f5167e996f2247b9577594a100b27a36c82b after Project A Task 3.
owned_processes: NONE
preserved_processes:
  - Existing codex, codex-cua, and so101-mujoco-gui tmux sessions remain untouched.
confirmed_conclusions:
  - OBSERVED: Proposal hashing excludes exactly the approval envelope; activating an exact proposal preserves its proposal_sha256 while threshold mutation changes it.
  - OBSERVED: New collector raw output is schema v2 with source/dependency/model/scene/motion identities; malformed, placeholder, or changed identities fail closed.
  - OBSERVED: Analyzer accepts archived schema-v1 raw data through an explicit adapter and emits schema-v2 proposals; new raw data follows the schema-v2 path.
  - OBSERVED: Approval CLI writes atomically for an exact hash and refuses to overwrite an approved file with a different hash.
  - OBSERVED: Fifty-seven focused tests and the full MuJoCo Python package gate of 388 passed plus 4 skipped completed without failures; Ruff lint/format passed.
  - OBSERVED: Checked-in contact_calibration.yaml validates as PLANNED, unapproved, and disabled.
disproven_routes:
  - Keeping enabled outside the approval envelope; changing it during activation would invalidate the exact proposal hash.
  - Accepting an approved_at timestamp without timezone; the new mutation test failed before validation was added and passes afterward.
open_risks:
  - The schema-v1 adapter maps its legacy config hash to scene and motion fields only for archived-read compatibility; live activation will use fresh schema-v2 evidence.
  - Physical thresholds remain unavailable until the seven-regime campaign and exact user approval.
next_command: PYTHONNOUSERSITE=1 python3 -m pytest -q src/so101_mujoco_demo_py/test/test_grasp_outcome.py
```

## Checkpoint MNT-CP-004

```yaml
checkpoint_id: MNT-CP-004
recorded_at: 2026-08-12T12:38:06+08:00
last_valid_experiment: NONE
current_hypothesis: Correlated cup/TCP motion plus table-clearance and relative-pose evidence can reject non-causal micro-lift and transport false positives.
working_tree_status: Clean at ad73015c80664b23f1f967fde6346a1b57e9bf5f after Project A Task 4.
owned_processes: NONE
preserved_processes:
  - Existing codex, codex-cua, and so101-mujoco-gui tmux sessions remain untouched.
confirmed_conclusions:
  - OBSERVED: A five-sample fresh bilateral window with allowed table evidence passes and returns immutable metrics/telemetry.
  - OBSERVED: Stale, provenance, truncation, forbidden contact, missing side, low/high force, compression, slip, and dwell failures have stable distinct codes and declared precedence.
  - OBSERVED: Receipt-age and reset-epoch fault injections each made their dedicated regression fail before restoring the checks.
  - OBSERVED: Twenty-five grasp/contact focused tests and Ruff lint/format passed.
disproven_routes:
  - Treating evidence newer than the action sequence as automatically fresh regardless of callback receipt age.
  - Checking session identity without independently checking reset epoch.
open_risks:
  - Grasp proof alone does not establish causal cup carry; micro-lift and every transport segment remain unproved.
next_command: PYTHONNOUSERSITE=1 python3 -m pytest -q src/so101_mujoco_demo_py/test/test_micro_lift_outcome.py
```

## Checkpoint MNT-CP-005

```yaml
checkpoint_id: MNT-CP-005
recorded_at: 2026-08-12T12:49:08+08:00
last_valid_experiment: NONE
current_hypothesis: A typed final-outcome evaluator can preserve strict legacy parity while consuming the canonical motion policy.
working_tree_status: Clean at f1666cec5fe8e0ee3c09f53491416dca89f159a0 after Project A Task 5.
owned_processes: NONE
preserved_processes:
  - Existing codex, codex-cua, and so101-mujoco-gui tmux sessions remain untouched.
confirmed_conclusions:
  - OBSERVED: CarrySample rejects invalid identity, time, pose, clearance, force, and boolean atoms at construction.
  - OBSERVED: Micro-lift checks the maximum cup excursion over the full trace, correlated TCP/cup displacement, relative drift, post-boundary table separation, and stable dwell.
  - OBSERVED: Transport requires ordered LIFT, MOVE_ABOVE_PLACE, and DESCEND_TO_PLACE segments with continuous bilateral force, clearance, workspace, and relative-pose bounds.
  - OBSERVED: Atomic-data, intermediate-teleport, table-recontact, and policy-bound tests each failed before their corresponding minimal constraint was present; the bounds test also failed under an explicit implementation mutation.
  - OBSERVED: The full Python package gate passed 439 tests with 4 skipped; Ruff lint/format and git diff checks passed.
disproven_routes:
  - Judging a micro-lift only from the final cup pose; an intermediate over-limit excursion can recover to an apparently valid endpoint.
  - Accepting transport segments as an unordered set; the causal carry proof requires the declared state order.
open_risks:
  - The final-target evaluator and legacy parity boundary are still pending.
  - Contact calibration remains PLANNED; its checked-in motion hash was refreshed for the new policy bytes but it is not executable or approved.
next_command: PYTHONNOUSERSITE=1 python3 -m pytest -q src/so101_mujoco_demo_py/test/test_physical_outcome_policy.py src/so101_mujoco_demo_py/test/test_pick_place_outcome.py
```

## Checkpoint MNT-CP-006

```yaml
checkpoint_id: MNT-CP-006
recorded_at: 2026-08-12T12:53:36+08:00
last_valid_experiment: NONE
current_hypothesis: Execute can fail closed before orchestration unless one approved contact policy matches every runtime artifact fingerprint.
working_tree_status: Clean at 99801ba9c4e0a4ef4ac12eb0447c387bc28dfc5f after Project A Task 6.
owned_processes: NONE
preserved_processes:
  - Existing codex, codex-cua, and so101-mujoco-gui tmux sessions remain untouched.
confirmed_conclusions:
  - OBSERVED: The final placement target is loaded once from the typed motion policy; old production ±5 mm target-region literals were removed.
  - OBSERVED: Live runtime strictly deserializes the recorded sample window and recomputes evaluate_final_placement; it does not trust serialized success or latest-position fields.
  - OBSERVED: Unknown sample fields, mistyped booleans, changed injected bounds, ACM restoration failure, and Planning Scene readback mismatch fail closed.
  - OBSERVED: A repository parity test binds MuJoCo final region, support height, tilt, and linear/angular settle limits to the read-only Gazebo policy reference.
  - OBSERVED: Forty final-outcome, runtime, release, and policy tests passed; Ruff lint/format and diff checks passed.
disproven_routes:
  - Treating final_evaluation.success as authoritative evidence.
  - Repeating final-region bounds in live orchestration after the typed policy has already loaded them.
open_risks:
  - Live execute still enters phase orchestration without an approved contact policy and several phase modules retain contact-limit literals.
next_command: PYTHONNOUSERSITE=1 python3 -m pytest -q src/so101_mujoco_demo_py/test/test_pick_place_cli.py src/so101_mujoco_demo_py/test/test_live_runtime_contract.py
```

## Checkpoint MNT-CP-007

```yaml
checkpoint_id: MNT-CP-007
recorded_at: 2026-08-12T13:01:36+08:00
last_valid_experiment: NONE
current_hypothesis: One isolated seven-regime campaign can produce separable physical thresholds without crossing the diagnostic safety ceiling.
working_tree_status: Clean at d03e48f3ac294bb629daee3d1427aefcf08b9f0a after Project A Task 7.
owned_processes: NONE
preserved_processes:
  - Existing codex, codex-cua, and so101-mujoco-gui tmux sessions remain untouched.
confirmed_conclusions:
  - OBSERVED: Disabled approval returns CONTACT_POLICY_NOT_APPROVED and changed model identity returns POLICY_FINGERPRINT_MISMATCH before resume, subprocess, or ROS side effects.
  - OBSERVED: Live phase environment contains only motion/contact paths plus dependency, model, scene, motion, and source-evidence hashes; thresholds are not serialized through environment variables.
  - OBSERVED: Every temporary phase loads the same immutable approved TaskPolicy; a 4.25 N fixture controls the observed maximum-safe-force value.
  - OBSERVED: MAX_FORCE_N, MIN_SIDE_NORMAL_FORCE_N, and old ±5 mm target-region literals have zero matches in live phases/runtime.
  - OBSERVED: The full Python package gate passed 446 tests with 4 skipped; Ruff lint/format and diff checks passed.
disproven_routes:
  - Entering physics resume before contact-policy approval and fingerprint verification.
  - Retaining a diagnostic-force literal in each phase and assuming equal spelling proves equal policy consumption.
open_risks:
  - The checked-in contact policy remains PLANNED and deliberately makes execute unavailable.
  - Temporary subprocess phases remain until the in-process state-action replacement passes parity in Task 9.
next_command: colcon --log-base /tmp/so101-debug-mujoco-maintainability-remediation/project-a-build/log build --base-paths src --packages-select so101_mujoco_support so101_mujoco_demo_py --build-base /tmp/so101-debug-mujoco-maintainability-remediation/project-a-build/build --install-base /tmp/so101-debug-mujoco-maintainability-remediation/project-a-build/install --symlink-install
```

## Experiments EXP-001 through EXP-007 preregistration

```yaml
status: PLANNED
recorded_at: 2026-08-12T13:12:00+08:00
ordered_experiments:
  - [EXP-001, no_contact, "collector only at verified CLOSE_READY before Close"]
  - [EXP-002, left_only, "q1 offset search plus bounded q6 close until exactly left-only"]
  - [EXP-003, right_only, "opposite q1 offset search plus bounded q6 close until exactly right-only"]
  - [EXP-004, bilateral_touch, "centered bounded q6 close to first bilateral light touch"]
  - [EXP-005, over_compression, "only q6 advances 0.004 rad from bilateral touch below 11.60 N"]
  - [EXP-006, micro_lift_slip, "light bilateral preload plus registered 2 mm arm target while collecting"]
  - [EXP-007, stable_hold, "centered >=0.50 N bilateral preload plus 0.30 s verified preroll"]
frozen_provenance:
  source_commit: 540d51b2596cb441409d4545c298f153646c2a52
  dependency_commit: f42b7b3d77288c2fee750fe53b0258e0a3d18194
  model_sha256: f87a033fab8cf7291e737519290a639e0310e703f8169288f075f3fe0c8b5aca
  scene_sha256: b98eca6f2ae8547b8b7213625512ef360c5496c7ea2d124535698ea58b24e7c0
  motion_policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
  overlay: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-build/install
  ros_domain_id: 176
  gz_partition: so101-mnt-cal-001
  simulation_session_id: so101-mnt-cal-001
  reset_epoch: 0
  driver: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/calibration_driver.py
  driver_sha256: 957c382ac53aa73f1df3c6d1282f826107b5c7d96d073352015c111d0bea8bc9
matrix_output: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/contact-calibration-raw.json
sample_count_per_regime: 25
common_collector_command: >-
  ros2 run so101_mujoco_demo_py collect_contact_calibration --regime REGIME
  --sample-count 25 --simulation-session-id so101-mnt-cal-001 --reset-epoch 0
  --output /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/contact-calibration-raw.json
  --source-commit 540d51b2596cb441409d4545c298f153646c2a52
  --dependency-commit f42b7b3d77288c2fee750fe53b0258e0a3d18194
  --model-sha256 f87a033fab8cf7291e737519290a639e0310e703f8169288f075f3fe0c8b5aca
  --scene-sha256 b98eca6f2ae8547b8b7213625512ef360c5496c7ea2d124535698ea58b24e7c0
  --motion-policy-sha256 aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
  --reference-object-position-m 0.020 -0.280 0.1649 --timeout-s 30
safety_aborts:
  - maximum_normal_force_n > 11.60
  - pre-contact cup displacement > 0.003 m
  - session/reset/pause/freshness/truncation/nonfinite/sequence mismatch
  - driver cup displacement > 0.010 m
valid_failure_stop: Any physically unavailable declared regime or overlapping analyzed distribution stops the campaign without relabeling or manufactured samples.
owned_processes: NONE before stack start; domain 176 no-daemon preflight was empty.
decision: PENDING
```

## Experiment EXP-023 terminal result and registered recovery

```yaml
experiment_id: EXP-023
status: INVALID
observed:
  - Centered q6 search physically reached right-only first, but the driver failed to terminate on the undeclared side and was externally bounded before emitting a terminal result.
  - The resulting state is right-only but cannot be relabeled or used; q6 is approximately -0.04675 and cup displacement is approximately 1.02 mm.
decision: Exclude EXP-022 through EXP-028, fix the task-external driver only, then run the production qualified teleop_reset transaction before a new full matrix.
registered_recovery:
  command: ROS_DOMAIN_ID=176 ros2 run so101_mujoco_demo_py teleop_reset --session-id so101-mnt-cal-001 --keyframe task_start
  expected: epoch 0 to 1, controller/pause/reset/resume/feedback/re-pause proof, followed by explicit resume and staged approach.
```

## Experiment EXP-029

```yaml
experiment_id: EXP-029
status: RUNNING
lifecycle: RESET_WORLD_EPOCH_1_LEFT_ONLY_ALIGNMENT_DIAGNOSTIC
precondition: Qualified reset 0 to 1 succeeded; explicit resume and production staged approach restored CLOSE_READY with no fingertip contact.
single_variable: q1_offset_rad +0.003 while q6 follows the unchanged -0.040 to -0.059 bounded search.
success: left force reaches 0.08 N while right contact remains absent.
failure: right contact appears first; stop immediately without relabeling.
safety: Common force, displacement, session, epoch, pause, and freshness aborts remain active.
driver_sha256: 3a3736da369d4f744514f793c527f0bd88b571c3c15017b4f0f56bb7457e68ff
decision: PENDING before first controller action.
```

## Experiment EXP-030 terminal result and EXP-031 plan

```yaml
EXP-030:
  status: VALID
  behavioral_result: FAILURE
  observed: q1 -0.003 produced right contact before declared left-only; driver terminated itself before further closing.
EXP-031:
  status: PLANNED
  lifecycle: RESET_WORLD_EPOCH_3_BILATERAL_THEN_MOVING_JAW_RELEASE_DIAGNOSTIC
  single_variable: Centered q6 closes to >=0.08 N per side, then only q6 opens in 0.0001 rad steps until right is absent and left remains >=0.08 N.
  success: Exact physical left-only shape; failure if both sides release or bounds are reached.
  prerequisite: Qualified reset 2 to 3 and production staged approach CLOSE_READY.
  driver_sha256: 86b7884dc08a032a85374d1f6a9900aabe3410fbb8a97a6c655f4a26c8d2bf05
decision: Reset and CLOSE_READY passed; PENDING before first q6 action.
```

## Experiment EXP-031 terminal result

```yaml
experiment_id: EXP-031
status: VALID
behavioral_result: FAILURE
terminal_time: 2026-08-12T13:36:00+08:00
observed:
  - Qualified ResetWorld advanced epoch 2 to 3, explicit resume succeeded, and the production 15-segment staged approach restored CLOSE_READY.
  - Centered q6 close physically reached bilateral contact at or above 0.08 N per side within force/displacement bounds.
  - Opening only q6 in 0.0001 rad steps released both sides without any sample where left remained at or above 0.08 N while right was absent.
  - The driver emitted its own terminal failure; session, epoch, pause, force, freshness, and displacement safety gates remained valid.
related_diagnostics:
  - EXP-030 VALID failure proved q1 -0.003 reaches right contact before left-only.
  - EXP-029 INVALID terminal readback at q1 +0.003 also showed right-only and supplies no counted conclusion.
conclusion: The registered controller-only paths cannot populate the required left_only regime under the frozen geometry; the seven-regime matrix and proposal do not exist.
decision: STOP per the approved campaign contract. Do not manufacture samples, relabel right-only evidence, analyze an incomplete matrix, approve policy, enter production execute, or proceed to Projects B/C/D.
```

## Checkpoint MNT-CP-008

```yaml
checkpoint_id: MNT-CP-008
recorded_at: 2026-08-12T13:36:00+08:00
last_valid_experiment: EXP-031
current_hypothesis: A separately authorized bounded Cartesian alignment change may be required to produce physical fixed-finger-only evidence before calibration can resume.
working_tree_status: Source clean at d325e2d2e518553805a6850ca1c59e7e033b4a64 before this ledger-only terminal record.
owned_processes: NONE; task-owned tmux so101-mnt-cal-001 was terminated, domain 176 no-daemon postflight is empty, and no matching process remains.
preserved_processes: Existing codex, codex-cua, and so101-mujoco-gui tmux sessions remain untouched.
confirmed_conclusions:
  - Isolated build and pinned fork provenance passed; three controllers and atomic evidence were ready.
  - EXP-022 collected 25 valid no_contact samples, but its batch was invalidated by the later harness-invalid EXP-023 and is excluded.
  - Calibration readiness bugs for first evidence, first robot state, and repeated snapshots were independently RED/GREEN fixed; table support force and stable-hold preroll statistics were also corrected before counted analysis.
  - No complete seven-regime raw matrix, proposal, threshold activation, or user approval was produced.
open_risks:
  - Expanding the alignment search changes the approved campaign method and requires user direction.
  - Execute remains correctly unavailable because contact_calibration.yaml is PLANNED, disabled, and unapproved.
next_command: Wait for user direction on a broader bounded Cartesian alignment experiment; do not merge or push main.
```

## Experiment EXP-029 terminal result and epoch-2 recovery

```yaml
experiment_id: EXP-029
status: INVALID
observed: q1 +0.003 produced right-only at q6 approximately -0.04518, but the fine-step driver hit the outer bound before emitting its own terminal failure.
decision: Do not infer a calibrated side alignment. Increase only the task-external diagnostic q6 step from 0.00002 to 0.0001 rad, retain all safety gates, run qualified reset 1 to 2, then test the opposite q1 direction as EXP-030.
```

## Experiment EXP-030

```yaml
experiment_id: EXP-030
status: RUNNING
precondition: Qualified reset 1 to 2 and production staged approach restored CLOSE_READY.
single_variable: q1_offset_rad -0.003 with bounded q6 step 0.0001 rad; target left-only >=0.08 N and right absent.
driver_sha256: 3c5b3454bfa76cd89727dc5639c966f78f97e6fc2d8c43454b127ec8aecedfea
safety_and_terminal_contract: Identical to EXP-029.
decision: PENDING before first controller action.
```

## EXP-022 result and EXP-023 exact action

```yaml
EXP-022:
  status: VALID
  result: 25 no_contact samples; table-only; matrix write succeeded with strict sequence/session/epoch provenance.
EXP-023:
  status: RUNNING
  single_variable: q6 decreases from -0.040 in 0.00002 rad steps at q1_offset_rad 0.0 until left_force >= 0.08 N while right_count remains zero.
  stop: Any right contact before the declared shape is a VALID behavioral failure; all common safety aborts remain active.
decision: PENDING before first controller action.
```

## Experiment EXP-008 terminal result

```yaml
experiment_id: EXP-008
status: INVALID
terminal_time: 2026-08-12T13:19:30+08:00
observed:
  - Atomic simulation evidence was accepted, but sample serialization ran before the joint-state subscription received its first message and returned no joint state is available.
  - No sample was written and no controller, reset, pause, or object-state action occurred; fresh readback remains CLOSE_READY.
inference: NONE about physical distributions.
decision: Exclude EXP-008 through EXP-014 and restart under new IDs only after readiness-pending is explicitly separated from terminal collection errors.
```

## Experiments EXP-015 through EXP-021 preregistration

```yaml
status: PLANNED
recorded_at: 2026-08-12T13:22:00+08:00
ordered_experiments: [[EXP-015, no_contact], [EXP-016, left_only], [EXP-017, right_only], [EXP-018, bilateral_touch], [EXP-019, over_compression], [EXP-020, micro_lift_slip], [EXP-021, stable_hold]]
source_commit: 2f4d5326a87099e511136436169d6270b7c93e0f
other_frozen_provenance_driver_commands_safety_and_terminal_contract: Identical to EXP-008 through EXP-014; the live stack is unchanged and fresh atomic readback remains CLOSE_READY.
decision: PENDING
```

## Experiment EXP-015 terminal result

```yaml
experiment_id: EXP-015
status: INVALID
terminal_time: 2026-08-12T13:23:00+08:00
observed:
  - Snapshot polling read the same fresh publisher sequence twice before the next 100 Hz callback; the collector rejected equality as non-monotonic.
  - No sample, controller command, reset, pause, or physical action occurred; CLOSE_READY remains unchanged.
inference: NONE about physical distributions.
decision: Exclude EXP-015 through EXP-021 and restart after equality is treated as bounded waiting while true sequence regression remains terminal.
```

## Experiments EXP-022 through EXP-028 preregistration

```yaml
status: PLANNED
recorded_at: 2026-08-12T13:26:00+08:00
ordered_experiments: [[EXP-022, no_contact], [EXP-023, left_only], [EXP-024, right_only], [EXP-025, bilateral_touch], [EXP-026, over_compression], [EXP-027, micro_lift_slip], [EXP-028, stable_hold]]
source_commit: d325e2d2e518553805a6850ca1c59e7e033b4a64
other_frozen_provenance_driver_commands_safety_and_terminal_contract: Identical to EXP-015 through EXP-021; live state remains unchanged CLOSE_READY.
decision: PENDING
```

## Experiment EXP-001 terminal result

```yaml
experiment_id: EXP-001
status: INVALID
terminal_time: 2026-08-12T13:15:00+08:00
observed:
  - The isolated stack and production staged approach reached verified CLOSE_READY at epoch 0 with zero fingertip contacts.
  - The first collector invocation called snapshot_with_receipt before its first sensor-data callback and propagated EvidenceStale instead of continuing its bounded pump loop.
  - No controller command, reset, pause, object state write, or other physical action occurred during EXP-001; the stack remains at CLOSE_READY.
inference: NONE about the no_contact distribution; zero samples were admitted.
decision: Exclude EXP-001 through EXP-007 from all denominators and restart the full ordered batch under fresh experiment IDs after a TDD-covered readiness fix.
```

## Experiments EXP-008 through EXP-014 preregistration

```yaml
status: PLANNED
recorded_at: 2026-08-12T13:18:00+08:00
ordered_experiments:
  - [EXP-008, no_contact]
  - [EXP-009, left_only]
  - [EXP-010, right_only]
  - [EXP-011, bilateral_touch]
  - [EXP-012, over_compression]
  - [EXP-013, micro_lift_slip]
  - [EXP-014, stable_hold]
frozen_provenance:
  source_commit: d38d4be7c87958b0af182235083641032c804d57
  dependency_commit: f42b7b3d77288c2fee750fe53b0258e0a3d18194
  model_sha256: f87a033fab8cf7291e737519290a639e0310e703f8169288f075f3fe0c8b5aca
  scene_sha256: b98eca6f2ae8547b8b7213625512ef360c5496c7ea2d124535698ea58b24e7c0
  motion_policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
  ros_domain_id: 176
  gz_partition: so101-mnt-cal-001
  simulation_session_id: so101-mnt-cal-001
  reset_epoch: 0
state_reuse_justification: EXP-001 executed no controller, reset, pause, or physical action; fresh atomic readback still matches CLOSE_READY with zero fingertip contacts.
driver_and_commands: Identical reviewed driver and per-regime commands from the EXP-001 through EXP-007 registration except source_commit is d38d4be7c87958b0af182235083641032c804d57.
safety_and_terminal_contract: Identical to the prior registration; any INVALID invalidates this full batch and any physically unavailable regime is a VALID behavioral failure that stops it.
decision: PENDING
```

## Experiments EXP-032 through EXP-043 Cartesian alignment scan preregistration

```yaml
status: PLANNED
recorded_at: 2026-08-12T14:00:00+08:00
authorization: USER_APPROVED bounded MoveIt scan along the gripper closing axis, maximum +/-0.003 m, controller motions only.
prior_experiment: EXP-031
hypothesis: Translating the open gripper toward the moving-pad side along the physical fixed-pad-to-moving-pad closing axis will make the fixed/left pad contact first; the opposite sign distinguishes an incorrect axis/sign inference.
prediction: At least one bounded offset reaches left force >=0.08 N with zero right-pad contact before the diagnostic force and displacement limits; if none does, Cartesian alignment is disproven for the approved range.
ordered_experiments:
  - [EXP-032, 0.0005]
  - [EXP-033, 0.0010]
  - [EXP-034, 0.0015]
  - [EXP-035, 0.0020]
  - [EXP-036, 0.0025]
  - [EXP-037, 0.0030]
  - [EXP-038, -0.0005]
  - [EXP-039, -0.0010]
  - [EXP-040, -0.0015]
  - [EXP-041, -0.0020]
  - [EXP-042, -0.0025]
  - [EXP-043, -0.0030]
single_variable: requested TCP translation in metres; one frozen value per experiment.
lifecycle: RESET_WORLD; every candidate starts after a qualified teleop_reset transaction, explicit resume, and production staged approach to CLOSE_READY.
preconditions:
  - One isolated headless stack, no other ROS nodes in domain 176, simulation session so101-mnt-align-001, and partition so101-mnt-align-001.
  - Fresh CLOSE_READY evidence has zero fingertip contact, the cup is at the reset reference within the production approach bound, and all three controllers plus MoveIt planning/execution are ready.
  - Source worktree differs from installed source commit only by this experiment ledger and prior ledger checkpoint commits.
success_criteria:
  - MoveIt returns and executes a non-empty pose-constrained trajectory from fresh joint state while keeping the TCP orientation fixed.
  - TCP projected displacement converges within 0.001 m of the requested scalar, orthogonal error is <=0.001 m, and pre-contact cup displacement is <=0.003 m.
  - Controller-only q6 closing reaches physical left force >=0.08 N with no right contact; maximum force remains <=11.60 N and total cup displacement <=0.010 m.
failure_criteria:
  - Right contact appears before the declared left-only shape, the q6 lower bound is reached, or every registered offset is exhausted without success.
invalid_criteria:
  - Planning/execution/readiness/provenance failure, reset/session/pause/freshness mismatch, unexpected pre-close contact, or a diagnostic harness failure.
frozen_provenance:
  worktree_commit: ac9986cb96af6daac6459a404daa8b0aa08bc911
  installed_source_commit: d325e2d2e518553805a6850ca1c59e7e033b4a64
  dependency_commit: f42b7b3d77288c2fee750fe53b0258e0a3d18194
  install_overlay: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-build/install
  runtime_package_prefix: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-build/install/so101_mujoco_demo_py
  ros_domain_id: 176
  gz_partition: so101-mnt-align-001
  simulation_session_id: so101-mnt-align-001
  driver: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/cartesian_alignment_driver.py
  driver_sha256: 352f451d5cbc5201235be2c710b3851e4b52d276d8f12800d1582b9c040a6e25
  urdf_sha256: 0646707fbfb8fdfea5076afbf89f297027c0324465ab7ebe8129fc36c0445f4a
  fixed_pad_mesh_sha256: 0c707b10ba8fe5918431a3d42a764266440ac8fbe37a8e1e66496f288c4d3781
  moving_pad_mesh_sha256: f33f0818f86177fbe2e12faf10c08b6eb48d8f39cd6b66c2e900268f0161995a
  closing_axis_tcp_fixed_to_moving_at_q6_minus_0_045: [0.74107100, 0.00792509, -0.67137989]
commands:
  - command: ROS_DOMAIN_ID=176 GZ_PARTITION=so101-mnt-align-001 ros2 launch so101_mujoco_demo_py so101_pick_place.launch.py run_mode:=dry_run execute:=false headless:=true start_simulation:=true launch_workflow:=false simulation_session_id:=so101-mnt-align-001
    exit_code: PENDING
  - command: ROS_DOMAIN_ID=176 ros2 run so101_mujoco_demo_py teleop_reset --session-id so101-mnt-align-001 --keyframe task_start
    exit_code: PENDING_PER_EXPERIMENT
  - command: ROS_DOMAIN_ID=176 ros2 service call /mujoco_ros2_control_node/set_pause mujoco_ros2_control_msgs/srv/SetPause '{paused: false}'
    exit_code: PENDING_PER_EXPERIMENT
  - command: ROS_DOMAIN_ID=176 ros2 run so101_mujoco_demo_py staged_approach --mode execute --execute --stop-after DESCEND --simulation-session-id so101-mnt-align-001 --evidence-file /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-staged-EXP-ID.json
    exit_code: PENDING_PER_EXPERIMENT
  - command: ROS_DOMAIN_ID=176 python3 /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/cartesian_alignment_driver.py --session-id so101-mnt-align-001 --epoch EPOCH --offset-m OFFSET --minimum-force-n 0.08
    exit_code: PENDING_PER_EXPERIMENT
safety_aborts:
  - No model/scene/motion-policy change, no object-state write, no simulator constraint or attachment, and no hidden contact relabeling.
  - Maximum normal force >11.60 N, pre-contact cup displacement >0.003 m, total diagnostic cup displacement >0.010 m, or any session/epoch/pause/freshness mismatch.
early_stop: Stop the ordered scan at the first valid physical left_only result, then preregister independent RESET_WORLD repeatability trials at that exact offset before resuming the seven-regime matrix.
decision: PENDING
```

### Provenance correction before EXP-032 runtime start

```yaml
recorded_at: 2026-08-12T14:03:00+08:00
scope: Historical MNT-CP-008, EXP-022-through-EXP-028, and the EXP-032-through-EXP-043 preregistration expanded short commit d325e2d to a nonexistent object.
incorrect_text: d325e2d2e518553805a6850ca1c59e7e033b4a64
correct_installed_source_commit: d325e2d98a75039e76b597d2ba1ef6484b752b64
verification: git rev-parse d325e2d returned the corrected object; the isolated overlay was built after that implementation commit and before ledger-only commits.
runtime_state: No stack, reset, controller, simulator, or object-state action had started when this correction was recorded.
decision: Use the corrected object for EXP-032 and every later provenance comparison; retain the original text as auditable history.
```
