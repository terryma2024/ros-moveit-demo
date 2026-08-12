# SO-101 MuJoCo Maintainability Remediation Experiment Ledger

```yaml
task_id: so101-mujoco-maintainability-remediation
goal: Replace migration experiment scaffolding with approved policy-driven state-machine production runtime and requalify it.
success_contract: All seven audit findings pass automated gates plus independent FULL_RESTART qualification and a fresh final five-consecutive-success RESET_WORLD challenge; only then merge this branch to main and push main to Gitee origin.
worktree: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
branch: codex/so101-mujoco-ros2-teleop
base_commit: 70bece06e008b27da8f0923472668e95a369309e
current_commit: 23994b02062b2140f5fb4268ae796eb3be23a275
evidence_root: /tmp/so101-debug-mujoco-maintainability-remediation/
confirmed_conclusions:
  - CP-156: prior implementation passed the published five FULL_RESTART plus five RESET_WORLD simulation qualification.
  - AUDIT-001: contact_calibration.yaml is PLANNED/disabled while production phases hard-code contact limits.
  - AUDIT-002: execute bypasses StateMachineRunner and ignores public checkpoint controls.
  - EXP-109: the frozen five-win strategy passes MICRO_LIFT and all LIFT phases; transport crosses the static 1.1579004532160448 N threshold and shuts down cleanly.
  - USER-AUTH-2026-08-12-PHASE-AWARE: preserve the five-win strategy exactly; static contact and dynamic transport require separate evidence/acceptance semantics.
  - EXP-124: lossless 500 Hz physics-step capture completed through physical transport on the qualification-provisioned NVMe evidence volume.
  - EXP-125: the unchanged nine-phase production strategy completes in one FULL_RESTART when held-cup phases use the qualified 11.60 N dynamic hard stop and post-release support continues to use the 1.1579004532160448 N static limit.
  - USER-AUTH-2026-08-12-EXP126-VISUAL-WAIVER: the user personally observed the EXP-126 terminal screen, accepted the visual outcome, and authorized only EXP-126 to count as batch success despite its preserved truncated PNG artifact.
disproven_routes:
  - Treating the prior 857-result colcon summary as a clean three-package result; it included 240 stale Gazebo tests.
open_hypotheses: []
latest_checkpoint: MNT-CP-042
next_experiment: EXP-128
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

## Experiment EXP-032 runtime start

```yaml
experiment_id: EXP-032
status: RUNNING
recorded_at: 2026-08-12T14:06:00+08:00
prior_experiment: EXP-031
single_variable: TCP closing-axis offset +0.0005 m.
lifecycle: RESET_WORLD
provenance:
  worktree_commit_before_runtime: addef02
  installed_source_commit: d325e2d98a75039e76b597d2ba1ef6484b752b64
  install_overlay: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-build/install
  runtime_package_prefix: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-build/install/so101_mujoco_demo_py
  ros_domain_id: 176
  gz_partition: so101-mnt-align-001
  simulation_session_id: so101-mnt-align-001
  driver_sha256: 352f451d5cbc5201235be2c710b3851e4b52d276d8f12800d1582b9c040a6e25
observed:
  - Domain 176 was empty before launch; one task-owned tmux session so101-mnt-align-001 started the registered command.
  - MoveGroup, MuJoCo, robot_state_publisher, all three active controllers, and the pinned overlay prefixes passed readiness.
commands:
  - command: Registered isolated stack command from the EXP-032-through-EXP-043 plan.
    exit_code: RUNNING
decision: PENDING before the qualified reset transaction and first controller action.
```

## Experiment EXP-032 terminal result and EXP-033 runtime start

```yaml
EXP-032:
  status: VALID
  behavioral_result: FAILURE
  lifecycle: RESET_WORLD_EPOCH_1
  single_variable: TCP closing-axis offset +0.0005 m.
  commands:
    reset_exit: 0
    resume_exit: 0
    staged_approach_exit: 0
    alignment_driver_exit: 1
    terminal_snapshot_exit: 0
  observed:
    - Qualified reset advanced epoch 0 to 1; explicit resume and all 15 production staged-approach segments reached CLOSE_READY.
    - MoveIt pose planning and ExecuteTrajectory completed far enough for the driver convergence guards to pass and controller-only q6 closing to begin.
    - Driver stopped itself when right contact appeared before left-only; terminal q6=-0.0456581 rad, right_count=1, right_force=0.0358439 N, left_count=0, maximum_force=0.144546 N.
    - Terminal cup position [0.0199996921, -0.2794827542, 0.1648141980] m is approximately 0.000550 m from reset reference, inside all registered limits.
    - The outer zsh wrapper used reserved variable name status only after the driver had already exited; this did not issue an action or alter the terminal evidence.
  conclusion: A +0.5 mm closing-axis translation remains moving/right-pad-first and does not produce left_only.
  evidence:
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-reset-EXP-032.log
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-staged-EXP-032.json
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-driver-EXP-032.log
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-terminal-EXP-032.log
  decision: KEEP behavior conclusion; continue the preregistered ordered scan.
EXP-033:
  status: RUNNING
  prior_experiment: EXP-032
  lifecycle: RESET_WORLD
  single_variable: TCP closing-axis offset +0.0010 m.
  provenance_and_safety: Identical to the corrected EXP-032 registration; the outer wrapper variable is changed to rc.
  decision: PENDING before qualified reset epoch 1 to 2.
```

## Experiment EXP-033 terminal result and EXP-034 runtime start

```yaml
EXP-033:
  status: VALID
  behavioral_result: FAILURE
  lifecycle: RESET_WORLD_EPOCH_2
  single_variable: TCP closing-axis offset +0.0010 m.
  observed:
    - Qualified reset 1 to 2, resume, and the 15-segment staged approach passed.
    - MoveIt planning/execution and TCP convergence guards passed; q6 closing stopped on right-first contact.
    - Terminal q6=-0.0449584 rad, right_count=1, right_force=0.0314084 N, left_count=0, maximum_force=0.153841 N, cup displacement approximately 0.000477 m.
  conclusion: +1.0 mm remains moving/right-pad-first.
  evidence:
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-staged-EXP-033.json
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-driver-EXP-033.log
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-terminal-EXP-033.log
  decision: KEEP behavior conclusion; continue ordered scan.
EXP-034:
  status: RUNNING
  prior_experiment: EXP-033
  lifecycle: RESET_WORLD
  single_variable: TCP closing-axis offset +0.0015 m.
  provenance_and_safety: Identical to corrected registration.
  decision: PENDING before qualified reset epoch 2 to 3.
```

## Experiment EXP-034 invalid result and corrected-axis batch preregistration

```yaml
EXP-034:
  status: INVALID
  lifecycle: RESET_WORLD_EPOCH_3
  observed:
    - Qualified reset, resume, and 15-segment production staged approach passed and left fresh no-contact CLOSE_READY evidence.
    - The pose request timed out after 8.0 s with MoveIt TIMED_OUT before ExecuteTrajectory, q6, contact, or object-state action.
    - Geometry review then showed the registered [0.74107100, 0.00792509, -0.67137989] vector was a pad-centroid connecting line, not the q6 closing-motion tangent; its excessive vertical component explained the first planning divergence.
  conclusion: No physical conclusion for +1.5 mm; the registered axis model was invalid for the user-approved closing-axis scan.
  decision: Exclude EXP-034 through EXP-043 and stop that batch. Retain EXP-032/033 only as valid results for the explicitly different centroid-line diagnostic.
correction:
  physical_axis_definition: Unit derivative of the moving-pad centroid with respect to increasing q6 at q6=-0.045 rad; decreasing q6 is closing, so this derivative is fixed-to-moving.
  closing_axis_tcp: [0.972175254, 0.000000860, -0.234254722]
  derivation_inputs:
    urdf_sha256: 0646707fbfb8fdfea5076afbf89f297027c0324465ab7ebe8129fc36c0445f4a
    moving_pad_mesh_sha256: f33f0818f86177fbe2e12faf10c08b6eb48d8f39cd6b66c2e900268f0161995a
  corrected_driver_sha256: b29da4e8e6a294ada7fcd656da70bab31259b3958ec9ad38be1eea50db4f7e87
new_batch:
  status: PLANNED
  prior_experiment: EXP-034
  ordered_experiments:
    - [EXP-044, 0.0005]
    - [EXP-045, 0.0010]
    - [EXP-046, 0.0015]
    - [EXP-047, 0.0020]
    - [EXP-048, 0.0025]
    - [EXP-049, 0.0030]
    - [EXP-050, -0.0005]
    - [EXP-051, -0.0010]
    - [EXP-052, -0.0015]
    - [EXP-053, -0.0020]
    - [EXP-054, -0.0025]
    - [EXP-055, -0.0030]
  single_variable: Requested TCP translation along the corrected physical closing axis; one frozen scalar per experiment.
  lifecycle: RESET_WORLD for every candidate; initial epoch for EXP-044 is qualified reset 3 to 4.
  prediction: Positive fixed-to-moving translation delays moving/right contact and eventually makes fixed/left contact first; negative translation provides a registered sign check only if the positive range is exhausted.
  success_failure_invalid_safety: Identical to the EXP-032-through-EXP-043 contract except the corrected axis and driver hash above replace the invalid centroid-line values.
  early_stop: First valid left_only result stops the scan and triggers exact-offset RESET_WORLD repeatability preregistration.
EXP-044:
  status: RUNNING
  single_variable: Corrected closing-axis TCP offset +0.0005 m.
  lifecycle: RESET_WORLD
  provenance:
    installed_source_commit: d325e2d98a75039e76b597d2ba1ef6484b752b64
    install_overlay: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-build/install
    runtime_package_prefix: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-build/install/so101_mujoco_demo_py
    ros_domain_id: 176
    gz_partition: so101-mnt-align-001
    simulation_session_id: so101-mnt-align-001
    driver_sha256: b29da4e8e6a294ada7fcd656da70bab31259b3958ec9ad38be1eea50db4f7e87
  decision: PENDING before qualified reset epoch 3 to 4.
```

## Experiment EXP-044 terminal result and EXP-045 runtime start

```yaml
EXP-044:
  status: VALID
  behavioral_result: FAILURE
  lifecycle: RESET_WORLD_EPOCH_4
  single_variable: Corrected closing-axis TCP offset +0.0005 m.
  observed:
    - Qualified reset 3 to 4, resume, staged approach, MoveIt plan/execute, and convergence guards passed.
    - Right contact appeared first and stopped q6 at -0.0412587 rad; right_force=0.0348171 N, left_count=0, maximum_force=0.163345 N.
    - Terminal cup position differed from reset only by normal vertical settling (approximately 0.000225 m); no safety boundary was approached.
  conclusion: +0.5 mm on the q6-tangent axis makes the moving/right side contact substantially earlier and does not produce left_only.
  evidence:
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-staged-EXP-044.json
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-driver-EXP-044.log
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-terminal-EXP-044.log
  decision: KEEP; continue preregistered order without changing sign based on result.
EXP-045:
  status: RUNNING
  prior_experiment: EXP-044
  lifecycle: RESET_WORLD
  single_variable: Corrected closing-axis TCP offset +0.0010 m.
  provenance_and_safety: Identical to EXP-044.
  decision: PENDING before qualified reset epoch 4 to 5.
```

## Experiment EXP-045 terminal result and EXP-046 runtime start

```yaml
EXP-045:
  status: VALID
  behavioral_result: FAILURE
  lifecycle: RESET_WORLD_EPOCH_5
  single_variable: Corrected closing-axis TCP offset +0.0010 m.
  observed:
    - Reset/resume/staged approach and MoveIt plan/execute/convergence passed; right contact again appeared first.
    - Terminal q6=-0.0442580 rad, right_force=0.0202711 N, left_count=0, maximum_force=0.149774 N, cup displacement approximately 0.000197 m.
  conclusion: +1.0 mm does not produce left_only.
  evidence:
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-staged-EXP-045.json
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-driver-EXP-045.log
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-terminal-EXP-045.log
  decision: KEEP; continue ordered scan.
EXP-046:
  status: RUNNING
  prior_experiment: EXP-045
  lifecycle: RESET_WORLD
  single_variable: Corrected closing-axis TCP offset +0.0015 m.
  provenance_and_safety: Identical to EXP-044.
  decision: PENDING before qualified reset epoch 5 to 6.
```

## Experiment EXP-046 invalid result and native Cartesian batch preregistration

```yaml
EXP-046:
  status: INVALID
  lifecycle: RESET_WORLD_EPOCH_6
  observed:
    - Reset/resume/staged approach passed and left no-contact CLOSE_READY.
    - The single-attempt OMPL pose request timed out before ExecuteTrajectory or any driver controller action; terminal state remained open and no-contact.
  conclusion: No physical +1.5 mm result. The pose-goal method is not a robust Cartesian scan boundary at this offset.
  decision: Exclude EXP-046 through EXP-055 and stop the second batch.
new_method:
  rationale: Use MoveIt's native GetCartesianPath straight-line service instead of stochastic pose-goal OMPL, retain collision checking, then execute the returned RobotTrajectory through ExecuteTrajectory.
  service: /compute_cartesian_path
  service_type: moveit_msgs/srv/GetCartesianPath
  frozen_parameters:
    group_name: arm
    link_name: so101_tcp
    frame_id: world
    max_step_m: 0.0001
    revolute_jump_threshold_rad: 0.02
    avoid_collisions: true
    velocity_scaling: 0.02
    acceleration_scaling: 0.02
    maximum_cartesian_speed_m_s: 0.005
    required_fraction: 0.999
  execute_boundary: /execute_trajectory with unchanged contact, provenance, TCP convergence, force, and cup-displacement monitors.
  driver_sha256: b3a94d8a52f9b346d332fa29e1e5c1155240657638aa8f54c97554055da5bd99
new_batch:
  status: PLANNED
  prior_experiment: EXP-046
  ordered_experiments:
    - [EXP-056, -0.0005]
    - [EXP-057, -0.0010]
    - [EXP-058, -0.0015]
    - [EXP-059, -0.0020]
    - [EXP-060, -0.0025]
    - [EXP-061, -0.0030]
  single_variable: Requested TCP translation along the frozen q6-tangent axis; one negative scalar per experiment.
  lifecycle: RESET_WORLD for every candidate; EXP-056 begins with qualified reset 6 to 7.
  prediction: The sign opposite EXP-044/045 moves the gripper away from the moving/right side; a bounded value will reach left-only before right contact.
  success_criteria:
    - GetCartesianPath returns error SUCCESS, fraction >=0.999, and a non-empty collision-checked trajectory; ExecuteTrajectory succeeds and the TCP convergence guards pass.
    - q6 reaches left force >=0.08 N with zero right contact inside the unchanged 11.60 N, 0.003 m pre-contact, and 0.010 m total-displacement limits.
  failure_criteria:
    - Right contact appears first or q6 reaches its lower bound after a successfully executed full Cartesian path.
  invalid_criteria:
    - Reset/readiness/session/pause/freshness failure, incomplete Cartesian fraction, controller/trajectory/TCP convergence failure, or safety monitor abort.
  early_stop: First valid left_only result stops the scan and triggers three exact-offset RESET_WORLD repeatability trials before matrix collection.
EXP-056:
  status: RUNNING
  prior_experiment: EXP-046
  lifecycle: RESET_WORLD
  single_variable: Native Cartesian corrected-axis TCP offset -0.0005 m.
  provenance:
    installed_source_commit: d325e2d98a75039e76b597d2ba1ef6484b752b64
    install_overlay: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-build/install
    ros_domain_id: 176
    gz_partition: so101-mnt-align-001
    simulation_session_id: so101-mnt-align-001
    driver_sha256: b3a94d8a52f9b346d332fa29e1e5c1155240657638aa8f54c97554055da5bd99
  decision: PENDING before qualified reset epoch 6 to 7.
```

## Experiment EXP-056 terminal result and EXP-057 runtime start

```yaml
EXP-056:
  status: VALID
  behavioral_result: FAILURE
  lifecycle: RESET_WORLD_EPOCH_7
  single_variable: Native Cartesian corrected-axis TCP offset -0.0005 m.
  observed:
    - Reset/resume/staged approach passed; native Cartesian service returned a complete executable path and TCP convergence passed.
    - Right contact still appeared first, but only at q6=-0.0467579 rad versus -0.0412587 at the opposite +0.5 mm sign.
    - Terminal right_force=0.0469175 N, left_count=0, maximum_force=0.148200 N, cup displacement approximately 0.001738 m, inside the registered limit.
  conclusion: Negative sign moves in the predicted direction and delays moving/right contact, but -0.5 mm is insufficient.
  evidence:
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-staged-EXP-056.json
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-driver-EXP-056.log
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-terminal-EXP-056.log
  decision: KEEP; continue ordered negative scan.
EXP-057:
  status: RUNNING
  prior_experiment: EXP-056
  lifecycle: RESET_WORLD
  single_variable: Native Cartesian corrected-axis TCP offset -0.0010 m.
  provenance_and_safety: Identical to EXP-056.
  decision: PENDING before qualified reset epoch 7 to 8.
```

## Experiment EXP-057 terminal result and EXP-058 runtime start

```yaml
EXP-057:
  status: VALID
  behavioral_result: FAILURE
  lifecycle: RESET_WORLD_EPOCH_8
  single_variable: Native Cartesian corrected-axis TCP offset -0.0010 m.
  observed:
    - All reset, approach, Cartesian fraction, execution, and convergence gates passed; right contact still appeared first.
    - Terminal q6=-0.0448590 rad, right_force=0.0304853 N, left_count=0, maximum_force=0.150998 N, cup displacement approximately 0.002116 m.
  conclusion: -1.0 mm is insufficient for left_only.
  evidence:
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-staged-EXP-057.json
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-driver-EXP-057.log
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-terminal-EXP-057.log
  decision: KEEP; continue ordered scan.
EXP-058:
  status: RUNNING
  prior_experiment: EXP-057
  lifecycle: RESET_WORLD
  single_variable: Native Cartesian corrected-axis TCP offset -0.0015 m.
  provenance_and_safety: Identical to EXP-056.
  decision: PENDING before qualified reset epoch 8 to 9.
```

## Experiment EXP-058 terminal result and EXP-059 runtime start

```yaml
EXP-058:
  status: VALID
  behavioral_result: FAILURE
  lifecycle: RESET_WORLD_EPOCH_9
  single_variable: Native Cartesian corrected-axis TCP offset -0.0015 m.
  observed:
    - All lifecycle, Cartesian, execution, and convergence gates passed; right contact appeared first.
    - Terminal q6=-0.0463566 rad, right_force=0.0564620 N, left_count=0, maximum_force=0.148560 N, cup displacement approximately 0.002786 m.
  conclusion: -1.5 mm remains right-first and is insufficient.
  evidence:
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-staged-EXP-058.json
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-driver-EXP-058.log
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-terminal-EXP-058.log
  decision: KEEP; continue ordered scan.
EXP-059:
  status: RUNNING
  prior_experiment: EXP-058
  lifecycle: RESET_WORLD
  single_variable: Native Cartesian corrected-axis TCP offset -0.0020 m.
  provenance_and_safety: Identical to EXP-056.
  decision: PENDING before qualified reset epoch 9 to 10.
```

## Experiment EXP-059 terminal result and EXP-060 runtime start

```yaml
EXP-059:
  status: VALID
  behavioral_result: FAILURE
  lifecycle: RESET_WORLD_EPOCH_10
  single_variable: Native Cartesian corrected-axis TCP offset -0.0020 m.
  observed:
    - All lifecycle and Cartesian execution gates passed.
    - The first sampled contact boundary was already bilateral, not left_only: q6=-0.0470597 rad, left_force=0.0129097 N and right_force=0.0452115 N.
    - Maximum force=0.173157 N and total cup displacement approximately 0.003312 m remained inside the total diagnostic bound; the pre-contact monitor had passed its separate 0.003 m gate.
  conclusion: -2.0 mm reaches the side-order crossover but not the declared left-only shape.
  evidence:
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-staged-EXP-059.json
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-driver-EXP-059.log
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-terminal-EXP-059.log
  decision: KEEP; continue ordered scan.
EXP-060:
  status: RUNNING
  prior_experiment: EXP-059
  lifecycle: RESET_WORLD
  single_variable: Native Cartesian corrected-axis TCP offset -0.0025 m.
  provenance_and_safety: Identical to EXP-056.
  decision: PENDING before qualified reset epoch 10 to 11.
```

## Experiment EXP-060 invalid result and crossover-refinement preregistration

```yaml
EXP-060:
  status: INVALID
  lifecycle: RESET_WORLD_EPOCH_11
  observed:
    - Reset/resume/staged approach passed and current state remained open, no-contact CLOSE_READY.
    - GetCartesianPath returned SUCCESS but only fraction=0.846153846 with 8 points for -0.0025 m; the driver rejected it before ExecuteTrajectory or q6 action.
  conclusion: No physical result for -2.5 mm; collision-checked Cartesian reachability ends before the requested target.
  decision: Exclude EXP-060 and unrun EXP-061; stop the batch.
new_batch:
  status: PLANNED
  prior_experiment: EXP-060
  hypothesis: EXP-059's first 0.0001-rad sample was bilateral because the side-order crossover occurred inside that q6 interval; a five-times finer q6 search plus 0.1 mm TCP refinement can resolve a physical left-only window before the -2.5 mm Cartesian reachability boundary.
  frozen_method_change:
    q6_step_rad: 0.00002
    driver_sha256: 5a13574de22bbb7074be8b2f2c44881ab3ce5f6b9a7a72c4c77768926f673d32
    all_native_cartesian_parameters_and_safety_limits: Unchanged from EXP-056-through-EXP-061.
  ordered_experiments:
    - [EXP-062, -0.0021]
    - [EXP-063, -0.0022]
    - [EXP-064, -0.0023]
    - [EXP-065, -0.0024]
  single_variable: TCP offset within this frozen fine-q6 batch; one value per RESET_WORLD experiment.
  success_criteria: Complete collision-checked Cartesian execution followed by left force >=0.08 N with zero right contact.
  failure_criteria: Complete execution followed by right-first/bilateral-first contact or q6 lower-bound exhaustion.
  invalid_criteria: Identical readiness, provenance, Cartesian fraction, controller, convergence, and safety invalidators.
  early_stop: First valid left_only result stops the scan and is followed by three independently preregistered exact-offset RESET_WORLD repeatability trials.
EXP-062:
  status: RUNNING
  prior_experiment: EXP-060
  lifecycle: RESET_WORLD
  single_variable: Native Cartesian corrected-axis TCP offset -0.0021 m with frozen q6 step 0.00002 rad.
  provenance:
    installed_source_commit: d325e2d98a75039e76b597d2ba1ef6484b752b64
    install_overlay: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-build/install
    ros_domain_id: 176
    gz_partition: so101-mnt-align-001
    simulation_session_id: so101-mnt-align-001
    driver_sha256: 5a13574de22bbb7074be8b2f2c44881ab3ce5f6b9a7a72c4c77768926f673d32
  decision: PENDING before qualified reset epoch 11 to 12.
```

## Experiment EXP-062 success and exact-offset repeatability preregistration

```yaml
EXP-062:
  status: VALID
  behavioral_result: SUCCESS
  lifecycle: RESET_WORLD_EPOCH_12
  single_variable: Native Cartesian corrected-axis TCP offset -0.0021 m with q6 step 0.00002 rad.
  observed:
    - Qualified reset 11 to 12, resume, and staged approach passed.
    - GetCartesianPath returned SUCCESS, fraction=1.0, 8 trajectory points; ExecuteTrajectory and all monitors passed.
    - Requested -0.0021 m produced projected TCP delta -0.0021818203 m with 0.0001714014 m orthogonal error.
    - The first fine q6 step after coarse close produced physical left_only: left_count=1, left_force=0.0843368 N, right_count=0, maximum_force=0.179571 N.
    - Total cup displacement was 0.00340763 m, below the 0.010 m terminal limit; the separately monitored pre-contact displacement stayed below 0.003 m.
  conclusion: A physical left_only regime exists at the approved -2.1 mm Cartesian offset without model/state writes or hidden constraints.
  evidence:
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-reset-EXP-062.log
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-staged-EXP-062.json
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-driver-EXP-062.log
  decision: KEEP exact candidate; abandon unrun EXP-063 through EXP-065 per early stop and verify repeatability before calibration use.
repeatability_batch:
  status: PLANNED
  prior_experiment: EXP-062
  ordered_experiments: [EXP-066, EXP-067, EXP-068]
  lifecycle: RESET_WORLD for every run.
  single_variable: NONE; exact -0.0021 m offset, q6 step, driver hash, source, overlay, model, scene, and safety contract frozen.
  success_contract: Three consecutive VALID trials each return complete Cartesian execution and physical left_force >=0.08 N with zero right contact.
  invalid_contract: Any lifecycle/provenance/fraction/controller/convergence/safety failure stops and invalidates the batch; a valid right/bilateral-first result ends the streak.
  frozen_driver_sha256: 5a13574de22bbb7074be8b2f2c44881ab3ce5f6b9a7a72c4c77768926f673d32
EXP-066:
  status: RUNNING
  prior_experiment: EXP-062
  lifecycle: RESET_WORLD
  single_variable: NONE
  decision: PENDING before qualified reset epoch 12 to 13.
```

## Experiment EXP-066 repeatability failure and finer-offset continuation

```yaml
EXP-066:
  status: VALID
  behavioral_result: FAILURE
  lifecycle: RESET_WORLD_EPOCH_13
  single_variable: NONE; exact EXP-062 -0.0021 m candidate.
  observed:
    - Qualified reset/resume/staged approach and complete native Cartesian execution passed under the frozen driver.
    - Right contact appeared before left_only; terminal q6=-0.0463152 rad, right_force=0.0272864 N, left_count=0, maximum_force=0.150246 N.
    - Total cup displacement approximately 0.003373 m remained inside the registered total bound.
  conclusion: The EXP-062 -2.1 mm success is not repeatable across ResetWorld and cannot seed calibration.
  evidence:
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-staged-EXP-066.json
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-driver-EXP-066.log
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-terminal-EXP-066.log
  decision: End repeatability batch; abandon unrun EXP-067 and EXP-068.
continuation_batch:
  status: PLANNED
  prior_experiment: EXP-066
  hypothesis: A slightly larger reachable negative offset creates a nonzero left-only margin robust to ResetWorld variation while remaining below the -2.5 mm partial-path boundary.
  ordered_experiments:
    - [EXP-069, -0.0022]
    - [EXP-070, -0.0023]
    - [EXP-071, -0.0024]
  lifecycle: RESET_WORLD per candidate.
  frozen_method: Native GetCartesianPath method and q6 step 0.00002 rad from EXP-062, driver SHA-256 5a13574de22bbb7074be8b2f2c44881ab3ce5f6b9a7a72c4c77768926f673d32.
  success_failure_invalid_safety: Identical to the EXP-062 fine-search contract.
  early_stop: First valid left_only candidate stops offset search and starts a fresh three-run exact-offset repeatability batch.
EXP-069:
  status: RUNNING
  prior_experiment: EXP-066
  lifecycle: RESET_WORLD
  single_variable: Native Cartesian corrected-axis TCP offset -0.0022 m.
  decision: PENDING before qualified reset epoch 13 to 14.
```

## Experiment EXP-069 invalid result and reachability-edge preregistration

```yaml
EXP-069:
  status: INVALID
  lifecycle: RESET_WORLD_EPOCH_14
  observed:
    - Qualified reset/resume/staged approach passed and left no-contact CLOSE_READY.
    - The -0.0022 m native Cartesian request returned SUCCESS but fraction=0.956521739 with 8 points; no ExecuteTrajectory or q6 action occurred.
  conclusion: The complete Cartesian reachability boundary lies between the full -2.1 mm path and partial -2.2 mm path.
  decision: Exclude EXP-069 and abandon unrun EXP-070/071; stop batch.
edge_batch:
  status: PLANNED
  prior_experiment: EXP-069
  hypothesis: A point strictly inside the -2.1 to -2.2 mm reachability edge preserves fraction 1.0 while adding enough fixed-side bias to make left_only repeatable.
  ordered_experiments:
    - [EXP-072, -0.00212]
    - [EXP-073, -0.00214]
    - [EXP-074, -0.00216]
    - [EXP-075, -0.00218]
  lifecycle: RESET_WORLD per candidate.
  frozen_method_and_safety: Identical native Cartesian and q6-step-0.00002 contract, driver SHA-256 5a13574de22bbb7074be8b2f2c44881ab3ce5f6b9a7a72c4c77768926f673d32.
  invalid_criteria: Any fraction below 0.999 remains INVALID and stops this batch; no partial trajectory is executed.
  early_stop: First valid left_only starts a separately preregistered exact-offset repeatability batch.
EXP-072:
  status: RUNNING
  prior_experiment: EXP-069
  lifecycle: RESET_WORLD
  single_variable: Native Cartesian corrected-axis TCP offset -0.00212 m.
  decision: PENDING before qualified reset epoch 14 to 15.
```

## Experiment EXP-072 terminal result and EXP-073 runtime start

```yaml
EXP-072:
  status: VALID
  behavioral_result: FAILURE
  lifecycle: RESET_WORLD_EPOCH_15
  single_variable: Native Cartesian corrected-axis TCP offset -0.00212 m.
  observed:
    - Complete native Cartesian execution and all monitors passed; right contact still appeared before left_only.
    - Terminal q6=-0.0468145 rad, right_force=0.0184047 N, left_count=0, maximum_force=0.173847 N, total cup displacement approximately 0.003473 m.
  conclusion: -2.12 mm is fully reachable but not left_only in this ResetWorld trial.
  evidence:
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-driver-EXP-072.log
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-terminal-EXP-072.log
  decision: KEEP; continue edge scan.
EXP-073:
  status: RUNNING
  prior_experiment: EXP-072
  lifecycle: RESET_WORLD
  single_variable: Native Cartesian corrected-axis TCP offset -0.00214 m.
  provenance_and_safety: Identical to EXP-072.
  decision: PENDING before qualified reset epoch 15 to 16.
```

## Experiment EXP-073 terminal result and EXP-074 runtime start

```yaml
EXP-073:
  status: VALID
  behavioral_result: FAILURE
  lifecycle: RESET_WORLD_EPOCH_16
  single_variable: Native Cartesian corrected-axis TCP offset -0.00214 m.
  observed:
    - Full Cartesian execution passed; right contact appeared first at q6=-0.0468946 rad with right_force=0.0215051 N and no left contact.
    - Maximum force=0.173762 N and total cup displacement approximately 0.003499 m remained within bounds.
  conclusion: -2.14 mm is reachable but still right-first.
  evidence:
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-driver-EXP-073.log
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-terminal-EXP-073.log
  decision: KEEP; continue edge scan.
EXP-074:
  status: RUNNING
  prior_experiment: EXP-073
  lifecycle: RESET_WORLD
  single_variable: Native Cartesian corrected-axis TCP offset -0.00216 m.
  provenance_and_safety: Identical to EXP-072.
  decision: PENDING before qualified reset epoch 16 to 17.
```

## Experiment EXP-074 terminal result and EXP-075 runtime start

```yaml
EXP-074:
  status: VALID
  behavioral_result: FAILURE
  lifecycle: RESET_WORLD_EPOCH_17
  single_variable: Native Cartesian corrected-axis TCP offset -0.00216 m.
  observed:
    - Full Cartesian execution passed; right contact appeared first at q6=-0.0467749 rad with right_force=0.0170396 N and no left contact.
    - Maximum force=0.174781 N and total cup displacement approximately 0.003493 m remained within limits.
  conclusion: -2.16 mm remains right-first.
  evidence:
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-driver-EXP-074.log
    - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-terminal-EXP-074.log
  decision: KEEP; run the last registered edge point.
EXP-075:
  status: RUNNING
  prior_experiment: EXP-074
  lifecycle: RESET_WORLD
  single_variable: Native Cartesian corrected-axis TCP offset -0.00218 m.
  provenance_and_safety: Identical to EXP-072.
  decision: PENDING before qualified reset epoch 17 to 18.
```

## User-directed A8 scope correction and Cartesian-route abandonment

```yaml
recorded_at: 2026-08-12T14:47:00+08:00
directive:
  - Stop all live work intended to manufacture left_only; do not create or execute any further offset batch.
  - Do not modify the axis, planner, q6 step, 0.003 m/11.60 N safety gates, MJCF, scene, geometry, simulator state, motion waypoints, or the previously five-win grasp strategy.
  - Abandon every EXP-069-and-later offset route after any already-running atomic action ends naturally.
  - Revise A8 to keep physical no_contact, bilateral_touch, over_compression, micro_lift_slip, and stable_hold regimes; treat left_only/right_only as deterministic unilateral-rejection contracts.
  - Reuse authentic unilateral evidence where available; an unsafe/unreachable side must be recorded as physical_unreachable, never fabricated or counted as zero misclassification.
  - Schema/collector/analyzer changes require RED-GREEN typed sample and fault-injection tests; checked-in contact policy remains disabled.
  - Stop at USER_APPROVAL_REQUIRED after generating the proposal and complete evidence summary; no self-approval and no Task 9/live nine-phase regression before exact-hash user approval.
delivery_timing_correction:
  - EXP-072 had already ended before this directive arrived.
  - EXP-073 and EXP-074 had also ended before this directive was delivered to the active turn; their prior launches cannot be undone.
  - EXP-075 had already entered its qualified reset/staged-approach/controller sequence when the previous wait was interrupted; it was allowed to terminate naturally and no new action followed.
route_disposition:
  EXP-069: ABANDON; INVALID partial Cartesian fraction already recorded.
  EXP-070: ABANDON; never started.
  EXP-071: ABANDON; never started.
  EXP-072: ABANDON_AND_EXCLUDE_FROM_CALIBRATION.
  EXP-073: ABANDON; completed right-first evidence is not a calibration input.
  EXP-074: ABANDON; completed right-first evidence is not a calibration input.
  EXP-075: ABANDON; completed right-first evidence is not a calibration input.
  future_offsets: FORBIDDEN_BY_USER_DIRECTIVE.
```

## EXP-072 safety-contract audit correction

```yaml
experiment_id: EXP-072
correction_recorded_at: 2026-08-12T14:47:00+08:00
prior_terminal_text: VALID, all monitors passed, KEEP, total cup displacement approximately 0.003473 m.
audit_finding:
  - The durable result reports only terminal total displacement, not an independently serialized pre-contact displacement value.
  - Terminal total displacement approximately 0.003473 m exceeds the registered 0.003 m pre-contact comparison gate.
  - An internal monitor returning normally is insufficient evidence to retain the broad statement all monitors passed when the persisted metric cannot independently distinguish pre-contact from post-contact motion.
corrected_classification: INVALID_FOR_CALIBRATION_AND_SAFETY_CONCLUSION
corrected_decision: ABANDON
prohibited_inference: Do not use EXP-072 as a KEEP candidate, a left_only calibration sample, or proof that the registered 0.003 m gate passed.
evidence:
  - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-driver-EXP-072.log
  - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-terminal-EXP-072.log
```

## Experiment EXP-075 natural terminal result

```yaml
experiment_id: EXP-075
status: VALID
behavioral_result: FAILURE
lifecycle: RESET_WORLD_EPOCH_18
single_variable: Native Cartesian corrected-axis TCP offset -0.00218 m.
observed:
  - The command was already in flight before the user stop directive was delivered; no interrupt or subsequent controller action was sent.
  - Staged approach completed and the driver terminated itself on right-first contact.
  - Fresh terminal snapshot: q6=-0.0466751 rad, right_count=1, right_force=0.0239958 N, left_count=0, maximum_force=0.150455 N.
  - Cup position [0.0199989419, -0.2765083963, 0.1648048126] m; total displacement from reset is approximately 0.003492 m.
  - No cartesian_alignment_driver or staged_approach process remained; all three controllers were active before stack shutdown.
conclusion: Right-first behavioral failure; no left_only result and no calibration admission.
decision: ABANDON per user directive; do not run any later offset.
evidence:
  - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-staged-EXP-075.log
  - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-driver-EXP-075.log
  - /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/alignment-terminal-EXP-075.log
```

## Checkpoint MNT-CP-009

```yaml
checkpoint_id: MNT-CP-009
recorded_at: 2026-08-12T14:47:00+08:00
last_valid_experiment: EXP-075, behavioral failure and ABANDONED; no EXP-069+ result is admitted to calibration.
current_hypothesis: Five reachable physical regimes plus deterministic unilateral-rejection contracts can satisfy A8 without manufacturing an unreachable side.
working_tree_status: Only docs/experiments/so101-mujoco-maintainability-remediation-experiment-ledger.md modified before this checkpoint write; implementation HEAD 3006938fdaf53004fd17c348751de9d9952e3f31.
owned_processes:
  - One task-owned tmux stack so101-mnt-align-001 in ROS_DOMAIN_ID 176; no driver or staged-approach process remains and the stack is scheduled for immediate owned-session termination.
preserved_processes:
  - tmux codex
  - tmux codex-cua
  - tmux so101-mujoco-gui
confirmed_conclusions:
  - No repeatable safe left_only physical regime was established; EXP-062's one success failed its first exact ResetWorld repeat EXP-066.
  - Authentic right-only evidence exists from multiple bounded trials, including EXP-030 and later abandoned diagnostics.
  - EXP-072 is safety-evidence INVALID for calibration because persisted evidence did not independently prove the 0.003 m pre-contact bound and terminal total was approximately 0.003473 m.
  - No physical sample may be fabricated and no missing class may be reported as zero misclassification.
disproven_routes:
  - Cartesian reachability-edge refinement after EXP-069 is ABANDONED by explicit user directive.
  - Further axis/planner/step/offset refinement is forbidden.
open_risks:
  - The schema, collector, analyzer, proposal format, design, plan, and tests do not yet represent physical_unreachable plus deterministic unilateral rejection.
  - contact_calibration.yaml remains PLANNED, disabled, and unapproved; execute remains unavailable.
next_command: Terminate only tmux session so101-mnt-align-001, verify domain 176 is empty, then revise design/plan/A8 tests with RED first and no further live offset action.
```

### MNT-CP-009 owned-process cleanup completion

```yaml
recorded_at: 2026-08-12T14:49:00+08:00
owned_processes: NONE
observed:
  - tmux session so101-mnt-align-001 was terminated after EXP-075 had naturally ended.
  - No cartesian_alignment_driver, staged_approach, or session-owned launch process remains.
  - ROS_DOMAIN_ID 176 no-daemon node list is empty.
preserved_processes:
  - tmux codex
  - tmux codex-cua
  - tmux so101-mujoco-gui
next_command: Read the current A8 design, implementation plan, schema, collector, analyzer, and tests; revise documentation to the user-approved five-physical-plus-unilateral-contract boundary before writing RED tests.
```

## User correction to EXP-072 displacement audit

```yaml
recorded_at: 2026-08-12T14:51:00+08:00
supersedes: EXP-072 safety-contract audit correction recorded at 2026-08-12T14:47:00+08:00.
user_correction:
  - Terminal total cup displacement and maximum pre-contact cup displacement are distinct metrics.
  - The pre-contact limit remains 0.003 m and may only be failed by the independently monitored pre-contact displacement.
  - The terminal total displacement limit remains 0.010 m; a terminal total above 0.003 m but below 0.010 m is not a safety-gate failure.
audit_result:
  EXP-072:
    classification: VALID behavioral failure, as originally recorded before the erroneous audit correction.
    pre_contact_gate: The driver passed its separate pre-contact monitor before q6 closing; no pre-contact threshold failure was emitted.
    terminal_total_displacement_m: 0.003473 approximately, below 0.010.
    decision: ABANDON per the later user scope directive; not admitted to calibration.
  EXP-073:
    classification: VALID behavioral failure; do not invalidate from terminal total displacement.
    terminal_total_displacement_m: 0.003499 approximately, below 0.010.
    decision: ABANDON; not admitted to calibration.
  EXP-074:
    classification: VALID behavioral failure; do not invalidate from terminal total displacement.
    terminal_total_displacement_m: 0.003493 approximately, below 0.010.
    decision: ABANDON; not admitted to calibration.
checkpoint_correction:
  - MNT-CP-009's statement that EXP-072 is safety-evidence INVALID is superseded and must not be used.
  - The retained conclusion is only that EXP-069-and-later offset refinement is abandoned and none of those results is a calibration input.
```

## Checkpoint MNT-CP-010

```yaml
checkpoint_id: MNT-CP-010
recorded_at: 2026-08-12T15:08:00+08:00
last_valid_experiment: EXP-075, behavioral failure and ABANDONED; no EXP-069+ result is admitted to calibration.
current_hypothesis: A schema-v3 five-physical-cohort proposal plus evidence-bound unilateral rejection contracts can satisfy A8 without fabricated samples or missing-class statistics.
owned_processes: NONE
preserved_processes:
  - tmux codex
  - tmux codex-cua
  - tmux so101-mujoco-gui
design_revision:
  physical_regimes:
    - no_contact
    - bilateral_touch
    - over_compression
    - micro_lift_slip
    - stable_hold
  unilateral_contracts:
    left_only:
      stable_grasp_allowed: false
      expected_failure_code: GRASP_RIGHT_CONTACT_MISSING
      physical_disposition: physical_unreachable unless later authentic evidence changes only the evidence record, not the fail-closed rule.
    right_only:
      stable_grasp_allowed: false
      expected_failure_code: GRASP_LEFT_CONTACT_MISSING
      physical_disposition: observed from retained authentic evidence.
  missing_class_statistics: null; never encode an unavailable physical cohort as zero misclassification.
  threshold_input: Only the five physical cohorts; unilateral records are never threshold samples.
safety_contract:
  maximum_pre_contact_displacement_m: 0.003
  maximum_terminal_total_displacement_m: 0.010
  maximum_diagnostic_force_n: 11.60
  displacement_audit: Only the independently monitored pre-contact field can fail the 0.003 m gate; terminal total is compared only with 0.010 m.
frozen_scope:
  - No new unilateral offset live experiment.
  - No axis, planner, q6-step, MJCF, scene, geometry, simulator-state, waypoint, safety-gate, or qualified-grasp-strategy change.
documents_revised:
  - docs/superpowers/specs/2026-08-12-so101-mujoco-maintainability-remediation-design.md
  - docs/superpowers/plans/2026-08-12-so101-mujoco-approved-policy-outcomes.md
acceptance_boundary:
  - RED must precede schema/collector/analyzer/runtime implementation.
  - Typed/fault-injected unilateral windows prove deterministic rejection but are never serialized as physical calibration evidence.
  - Checked-in contact policy remains disabled and unapproved.
  - Generate a complete disabled proposal/evidence packet, then stop at USER_APPROVAL_REQUIRED for the exact proposal hash.
next_command: Write focused schema-v3 and unilateral fail-closed tests, run them to capture RED, then implement the smallest GREEN change.
```

## Checkpoint MNT-CP-011

```yaml
checkpoint_id: MNT-CP-011
recorded_at: 2026-08-12T15:37:00+08:00
implementation_commit: 1174d7675b5881d87ec1f6a46c501a379eace019
owned_processes: NONE
change_summary:
  - schema-v3 separates five physical calibration cohorts from left_only/right_only deterministic rejection contracts.
  - collector accepts only physical cohort labels and binds an external immutable unilateral-contract artifact into every raw matrix.
  - analyzer derives thresholds, quantiles, and confusion rows only from five physical cohorts; unilateral statistical fields are null.
  - approved-policy loading validates fail-closed contract codes and retains schema-v2 read compatibility.
  - typed unilateral fault injection proves left_only and right_only cannot become stable-grasp success.
  - collector independently enforces 0.003 m pre-contact and 0.010 m terminal-total displacement limits.
  - migration isolation gate ignores only its package-root .pytest_cache, preventing second-run self-contamination while retaining hidden/ignored source scanning.
red_evidence:
  environment_invalid:
    result: Initial pytest collection lacked the sourced so101_mujoco_support overlay; not counted as RED.
  schema_red:
    result: ImportError for missing PHYSICAL_REGIMES after correct isolated overlay provenance was sourced.
  displacement_red:
    result: 0.011 m terminal total displacement did not raise before the independent terminal-total guard was implemented.
  repeatability_gate_red:
    result: Second full package run failed because .pytest_cache/v/cache/nodeids was scanned as implementation evidence.
green_evidence:
  focused_suite: 76 passed in 3.17 s.
  full_package: 464 passed, 4 skipped in 25.73 s.
  ruff_gate: All checks passed; 118 files already formatted.
  isolation_gate: Passed with a pre-existing pytest cache and with the new explicit cache regression test.
  checked_in_policy_validation: analyze_contact_calibration --validate config/contact_calibration.yaml returned 0.
  diff_check: Passed.
unilateral_evidence:
  left_only:
    disposition: physical_unreachable
    authentic_observation:
      experiment_id: EXP-062
      artifact_sha256: 30ded56e85ed3a89cf5e34711da2820d8f5652fe38851470dfe27d3f33d846a0
    failed_exact_reset_repeat:
      experiment_id: EXP-066
      artifact_sha256: 085755077535972b10dd31ef18329bee8f7bc5a2b76da7ffd1bf523bb65be869
  right_only:
    disposition: observed
    authentic_observation:
      experiment_id: EXP-072
      artifact_sha256: 87e4a5e22d3cb30bcdf739f596465cd09807d40a6c6244a4f5d04806aa0d24c2
    audit_note: EXP-072 is a VALID behavioral failure and ABANDONED; terminal total approximately 0.003473 m is below 0.010 m and does not fail the separate 0.003 m pre-contact gate.
checked_in_policy_state:
  schema_version: 3
  calibration_status: PLANNED
  approval_enabled: false
  approval_approved: false
next_command: Generate and independently validate the external unilateral-contracts.json from the exact authentic hashes, then preregister only the five physical A8 collection experiments.
```

## Checkpoint MNT-CP-012 and EXP-076 through EXP-080 preregistration

```yaml
checkpoint_id: MNT-CP-012
recorded_at: 2026-08-12T15:55:00+08:00
source_commit: 66210bedc4a1f5670608fc8fe39bfda503bd263c
dependency_commit: f42b7b3d77288c2fee750fe53b0258e0a3d18194
model_sha256: f87a033fab8cf7291e737519290a639e0310e703f8169288f075f3fe0c8b5aca
scene_sha256: b98eca6f2ae8547b8b7213625512ef360c5496c7ea2d124535698ea58b24e7c0
motion_policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
collector_sha256: 03bfef5f8abaacbae99acd2b784e619b7d96299ea132222dbf7f49709a2da66d
driver:
  path: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/calibration_driver.py
  sha256: 86b7884dc08a032a85374d1f6a9900aabe3410fbb8a97a6c655f4a26c8d2bf05
unilateral_contract_artifact:
  path: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/unilateral-contracts.json
  sha256: a949e8f44c41dfd14edf54d7a153acc9d53d5bab8f50496940b2c403b636eeae
  validator_result: VALID
build:
  overlay: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-build-v3-final/install
  package_prefixes:
    so101_mujoco_demo_py: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-build-v3-final/install/so101_mujoco_demo_py
    so101_mujoco_support: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-build-v3-final/install/so101_mujoco_support
  result: Two packages built; runtime lock validation_errors empty.
run_identity:
  ros_domain_id: 177
  gz_partition: so101-mnt-cal-v3
  simulation_session_id: so101-mnt-cal-v3
  reset_epoch: 0
  tmux_session: so101-mnt-cal-v3
matrix_output: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/contact-calibration-raw-v3.json
proposal_output: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/contact-calibration-proposal-v3.yaml
preflight:
  domain_177_nodes: NONE
  task_tmux_session: NONE
  matrix_exists: false
  proposal_exists: false
  owned_processes: NONE
preserved_processes:
  - tmux codex
  - tmux codex-cua
  - tmux so101-mujoco-gui
safety_aborts:
  - independently monitored pre-contact displacement >0.003 m only while --pre-contact is active
  - terminal total displacement from reset reference >0.010 m at every collector sample and driver terminal readback
  - maximum normal force >11.60 N
  - stale/truncated/nonfinite/non-monotonic/session/reset/pause mismatch
  - missing declared bilateral contact, controller failure, or incomplete motion
frozen_scope:
  - No left_only/right_only live action and no offset search.
  - No axis, planner, q6 step, MJCF, scene, geometry, simulator state, waypoint, safety limit, or qualified grasp-strategy change.
  - No object-state write, weld, equality, adhesion, mocap, teleport, hidden retry, or relabeling.
common_stack_command: >-
  ROS_DOMAIN_ID=177 GZ_PARTITION=so101-mnt-cal-v3 ros2 launch
  so101_mujoco_demo_py so101_pick_place.launch.py run_mode:=dry_run
  execute:=false headless:=true start_simulation:=true launch_workflow:=false
  simulation_session_id:=so101-mnt-cal-v3
common_collector_identity: >-
  --simulation-session-id so101-mnt-cal-v3 --reset-epoch 0
  --output /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/contact-calibration-raw-v3.json
  --source-commit 66210bedc4a1f5670608fc8fe39bfda503bd263c
  --dependency-commit f42b7b3d77288c2fee750fe53b0258e0a3d18194
  --model-sha256 f87a033fab8cf7291e737519290a639e0310e703f8169288f075f3fe0c8b5aca
  --scene-sha256 b98eca6f2ae8547b8b7213625512ef360c5496c7ea2d124535698ea58b24e7c0
  --motion-policy-sha256 aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
  --unilateral-contracts /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/unilateral-contracts.json
  --reference-object-position-m 0.020 -0.280 0.1649 --timeout-s 30
ordered_experiments:
  EXP-076:
    regime: no_contact
    sample_contract:
      - Collect 13 CLOSE_READY table-only samples with --pre-contact --table-only.
      - Use the frozen prepare-bilateral operation at 0.08 N per side, then the frozen open operation; after fresh zero-fingertip readback, append 12 samples with --post-release --append.
    success: Exactly 25 no-contact samples, both subcohorts non-empty, zero fingertip contact in every admitted sample.
    invalid: Any admitted fingertip contact, failed release, or explicit append/fingerprint/provenance guard.
  EXP-077:
    regime: bilateral_touch
    single_variable: Frozen centered q6 close to minimum 0.08 N per side.
    success: 25 fresh bilateral samples while cup remains table-supported and below all safety gates.
  EXP-078:
    regime: over_compression
    single_variable: Frozen driver over-compress operation advances only q6 by 0.004 rad from EXP-077 bilateral touch.
    success: 25 bilateral samples with compression/force distribution separated from acceptable cohorts but below 11.60 N and 0.010 m.
  EXP-079:
    regime: micro_lift_slip
    single_variable: Frozen light 0.08 N bilateral preload plus the existing registered 2 mm MICRO_LIFT_ARM motion.
    sampling_order: Start the 25-sample collector on verified bilateral preload, then execute the frozen 1.0 s micro-lift while collection remains active.
    success: Bilateral continuity plus measured cup/TCP behavior that rejects causal stable carry and produces a slip-speed cohort; otherwise record a VALID behavioral failure and stop without relabeling.
  EXP-080:
    regime: stable_hold
    single_variable: Frozen centered >=0.50 N bilateral preload plus the same registered micro-lift, followed by >=0.30 s continuous bilateral preroll.
    success: Successful causal cup micro-lift, bilateral continuity, stable low-speed hold, and 25 post-preroll samples.
decision: PLANNED. Start only after this preregistration commit; stop at the first INVALID or unavailable physical regime and do not analyze an incomplete matrix.
```

## EXP-076 runtime start

```yaml
experiment_id: EXP-076
status: RUNNING
recorded_at: 2026-08-12T16:01:00+08:00
regime: no_contact
source_commit: 66210bedc4a1f5670608fc8fe39bfda503bd263c
preregistration_commit: bcf0c5a
owned_processes: NONE before registered stack launch.
unrelated_worktree_state:
  - docs/experiments/so101-mujoco-ros2-migration-experiment-summary.md appeared untracked after preregistration; it is preserved, excluded from task commits, and not present in the already built overlay.
decision: PENDING before stack launch and before any controller action.
```

## EXP-076 terminal result and EXP-081 through EXP-085 preregistration

```yaml
EXP-076:
  status: INVALID
  lifecycle: FRESH_STACK_EPOCH_0
  admitted_samples: 13 table_only no_contact samples; excluded with the batch.
  observed:
    - Production staged approach reached CLOSE_READY with zero fingertip contacts.
    - The schema-v3 collector atomically stored 13 table-only samples and passed the independent pre-contact monitor.
    - Frozen centered prepare-bilateral reached left_force=0.0811509 N and right_force=0.211059 N.
    - Frozen open released the moving/right side but left/fixed contact persisted: left_count=1, left_force=0.0773804 N, right_count=0.
    - Cup position [0.0199998203, -0.2789368471, 0.1648296520] m was approximately 0.001068 m from reset, below the 0.010 m terminal-total limit; no pre-contact comparison was made after contact.
  decision: Do not append a false post-release no_contact label. Exclude the entire EXP-076-through-080 batch, stop the owned stack, and preserve the partial matrix only as invalid evidence.
  evidence:
    partial_matrix_sha256: 2f88f8760d960fc38c5cd2d2a481445a7ab034c8af59ba6965614df0d9a2d704
    staged_evidence_sha256: 8f39b8b49a37b5a864d474004d89ffbb8f7c7776f29993ff55a72bfe03fe27ec
    stack_log_sha256: 32729251fc39639953a21b7e1808a28234e0b6946fecfc527349917835e59d6c
  cleanup: Ordered controller/MoveGroup shutdown completed; tmux so101-mnt-cal-v3 absent and domain 177 empty.
revised_hypothesis: The unchanged production MOVE_ABOVE_OBJECT path can provide a real post-release arm retreat after frozen open, eliminating residual fixed-finger contact without changing any waypoint.
batch_2:
  source_commit: 66210bedc4a1f5670608fc8fe39bfda503bd263c
  dependency_model_scene_motion_contract_driver_build: Identical to MNT-CP-012.
  ros_domain_id: 178
  gz_partition: so101-mnt-cal-v3b
  simulation_session_id: so101-mnt-cal-v3b
  reset_epoch: 0
  tmux_session: so101-mnt-cal-v3b
  matrix_output: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/contact-calibration-raw-v3-batch2.json
  proposal_output: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/contact-calibration-proposal-v3-batch2.yaml
  safety_and_frozen_scope: Identical to MNT-CP-012; pre-contact and terminal-total displacement fields remain independent.
  EXP-081:
    regime: no_contact
    ordered_actions:
      - Production staged approach to CLOSE_READY; collect 13 --pre-contact --table-only samples.
      - Frozen centered prepare-bilateral at 0.08 N per side, then frozen open.
      - Execute the unchanged production staged approach only through MOVE_ABOVE_OBJECT as the registered release retreat.
      - Require fresh zero-left/zero-right readback, then append 12 --post-release samples.
    success: Exactly 25 no-contact samples with both subcohorts and no admitted fingertip contact.
    failure: Any residual contact after the registered retreat, motion failure, or safety/provenance violation stops the batch.
  EXP-082: Same bilateral_touch method and acceptance as EXP-077 after the unchanged production staged approach returns from MOVE_ABOVE_OBJECT to CLOSE_READY.
  EXP-083: Same over_compression method and acceptance as EXP-078.
  EXP-084: Same concurrent micro_lift_slip method and acceptance as EXP-079.
  EXP-085: Same stable_hold method and acceptance as EXP-080.
decision: PLANNED before any batch-2 stack launch or controller action. No new waypoint or offset is introduced.
```

## EXP-081 terminal result and EXP-086 through EXP-090 preregistration

```yaml
EXP-081:
  status: INVALID
  admitted_samples: 13 table_only no_contact samples; excluded with batch 2.
  observed:
    - CLOSE_READY and the first 13 samples passed.
    - Frozen open again left one fixed-finger contact after moving-side release.
    - The production staged-approach entry rejected the registered MOVE_ABOVE_OBJECT retreat with STAGED_APPROACH_FAILED early fingertip contact before Close.
    - The rejected entry executed no arm waypoint and no sample was appended.
  decision: Exclude EXP-081-through-085 and stop the owned stack. Do not bypass the staged-approach early-contact guard.
  evidence:
    partial_matrix_sha256: c8cd6ae64b60daed04e5e7f5fbdb39c02723fafdc7097f7d0c9ade4928ee4a4c
    close_ready_evidence_sha256: a7e50c44a7fad8dadb67b5dad0f8bf2e5d65492a50578c24c495c63b8d7397b7
    stack_log_sha256: b9fb8a2ea5181fa16580baa80d114e0ffa45e5030d9cb1cbc1a81a183721ca54
  cleanup: Ordered shutdown complete; tmux so101-mnt-cal-v3b absent and domain 178 empty.
revised_hypothesis: After frozen open, the already registered 2 mm MICRO_LIFT_ARM target can separate the open fixed finger from the table-supported cup while remaining inside the unchanged total-displacement gate.
batch_3:
  source_commit: 66210bedc4a1f5670608fc8fe39bfda503bd263c
  dependency_model_scene_motion_contract_driver_build: Identical to MNT-CP-012.
  ros_domain_id: 179
  gz_partition: so101-mnt-cal-v3c
  simulation_session_id: so101-mnt-cal-v3c
  reset_epoch: 0
  tmux_session: so101-mnt-cal-v3c
  matrix_output: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/contact-calibration-raw-v3-batch3.json
  proposal_output: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/contact-calibration-proposal-v3-batch3.yaml
  safety_and_frozen_scope: Identical to MNT-CP-012; no offsets, new waypoint, planner change, or safety-limit change.
  EXP-086:
    regime: no_contact
    ordered_actions:
      - Collect 13 CLOSE_READY --pre-contact --table-only samples.
      - Frozen centered 0.08 N bilateral touch, then frozen open.
      - Execute only the existing calibration_driver micro-lift operation to the unchanged MICRO_LIFT_ARM target while q6 remains open.
      - Require fresh zero-left/zero-right contact and terminal total displacement <=0.010 m, then append 12 --post-release samples.
    failure: Any residual contact, object lift/instability incompatible with a negative control, or safety/provenance violation stops the batch.
  EXP-087: Same bilateral_touch method and acceptance as EXP-077 after frozen restore-close-ready.
  EXP-088: Same over_compression method and acceptance as EXP-078.
  EXP-089: Same concurrent micro_lift_slip method and acceptance as EXP-079.
  EXP-090: Same stable_hold method and acceptance as EXP-080.
decision: PLANNED before batch-3 stack launch. The only changed setup choice is reuse of an already frozen motion target after release.
```

## EXP-086 terminal result and EXP-091 through EXP-095 preregistration

```yaml
EXP-086:
  status: INVALID
  admitted_samples: 13 table_only no_contact samples; excluded with batch 3.
  observed:
    - Frozen open plus the existing 2 mm MICRO_LIFT_ARM target reduced penetration but did not clear the fixed finger.
    - Terminal readback remained left_count=1, left_force=0.111416 N, right_count=0; no post-release sample was appended.
    - Cup position [0.0199998594, -0.2792522200, 0.1649654536] m remained inside the unchanged 0.010 m terminal-total gate.
  decision: Exclude EXP-086-through-090 and stop the owned stack; do not continue micro-lift increments.
  evidence:
    partial_matrix_sha256: f24aab91bd3f388cfd25c235ce2b38971da7c80bab0c39e8dfd87d03a756ec26
    staged_evidence_sha256: 7a226b04f72d894a28a4e8ba4c1f5b11f565c3990b47eb6063b757ae64ddb32c
    stack_log_sha256: e464a2352909527f461d170d36d35b0b3db82bb23ef1fe5b85437d7a0c3b75d9
  cleanup: Ordered shutdown complete; tmux so101-mnt-cal-v3c absent and domain 179 empty.
revised_hypothesis: The first unchanged RECOVER_RETREAT/LIFT policy waypoint provides enough registered clearance to remove the open fixed finger from the table-supported cup.
batch_4:
  source_commit: 66210bedc4a1f5670608fc8fe39bfda503bd263c
  dependency_model_scene_motion_contract_driver_build: Identical to MNT-CP-012.
  ros_domain_id: 180
  gz_partition: so101-mnt-cal-v3d
  simulation_session_id: so101-mnt-cal-v3d
  reset_epoch: 0
  tmux_session: so101-mnt-cal-v3d
  matrix_output: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/contact-calibration-raw-v3-batch4.json
  proposal_output: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/contact-calibration-proposal-v3-batch4.yaml
  frozen_release_retreat:
    policy_state: RECOVER_RETREAT; waypoint index 0, identical to LIFT waypoint index 0.
    target_rad: [-0.000284124852, 0.381814591288, 0.272246878070, 0.916741182602, -0.000291565154]
    source: config/motion_policies/light_cup_wall_pick.yaml with sha256 aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
    execution: One direct arm_controller FollowJointTrajectory goal, 1.0 s, after frozen open; no waypoint or planner setting is changed.
  safety_and_frozen_scope: Identical to MNT-CP-012; terminal fresh evidence must satisfy <=11.60 N and <=0.010 m before any append.
  EXP-091:
    regime: no_contact
    ordered_actions:
      - Collect 13 CLOSE_READY --pre-contact --table-only samples.
      - Frozen centered 0.08 N bilateral touch, then frozen open.
      - Execute exactly frozen_release_retreat once; require controller success and fresh zero-left/zero-right table-supported readback.
      - Append 12 --post-release samples.
    failure: Residual fingertip contact, unsupported/moved cup, controller failure, or safety/provenance violation stops the batch.
  EXP-092: Frozen restore-close-ready plus the EXP-077 bilateral_touch method.
  EXP-093: Same over_compression method and acceptance as EXP-078.
  EXP-094: Same concurrent micro_lift_slip method and acceptance as EXP-079.
  EXP-095: Same stable_hold method and acceptance as EXP-080.
decision: PLANNED before batch-4 stack launch. No reachability boundary, offset, or new motion target is introduced.
```

## EXP-091 through EXP-094 results and EXP-096 through EXP-100 preregistration

```yaml
batch_4_results:
  EXP-091:
    status: VALID
    regime: no_contact
    observed: 13 table-only plus 12 post-release samples admitted; frozen RECOVER_RETREAT[0] controller goal succeeded and fresh release readback had zero fingertip contacts.
  EXP-092:
    status: VALID
    regime: bilateral_touch
    observed: 25 samples admitted at terminal left/right force approximately 0.0810/0.2099 N.
  EXP-093:
    status: VALID
    regime: over_compression
    observed: 25 samples admitted after frozen q6 -0.004 rad increment; terminal left/right summed force approximately 2.026/2.138 N and maximum single-contact force 1.646 N.
  EXP-094:
    status: INVALID
    regime: micro_lift_slip
    admitted_samples: 1 in the invalid partial artifact; not present in the matrix and excluded.
    observed:
      - Collector began on verified 0.08 N-per-side preload and overlapped the unchanged 1.0 s MICRO_LIFT_ARM motion.
      - One fingertip side disappeared during collection, triggering the unchanged bilateral-continuity guard.
      - Terminal motion readback was bilateral again, left/right force approximately 0.176/0.124 N, but this cannot erase the in-window continuity failure.
      - Terminal cup position [0.0199992502, -0.2792368145, 0.1667746266] m was approximately 0.002024 m from reset, below the 0.010 m terminal-total gate.
    decision: Exclude the entire batch 4 and do not execute EXP-095.
  EXP-095:
    status: NOT_RUN
    reason: Batch stopped at EXP-094 INVALID.
  evidence:
    partial_matrix_sha256: 3e74850abc5a55cdaf56a3e2851903b994be905dc813b982ddb061f540414db3
    invalid_partial_sha256: 493328c3ac4d11240a386671bef7d2adc352dc22ff756431994258293c1d10aa
    collector_log_sha256: 0156dbbd286e758db24d4493950bae812a704758ed0336a459fe86c13b8d45bf
    stack_log_sha256: e6ea90d4bbe450e54cab85ec51892a1123c359128b975c06a62a073d3c2145a4
  cleanup: Ordered shutdown complete; tmux so101-mnt-cal-v3d absent and domain 180 empty.
revised_hypothesis: Raising only the declared micro_lift_slip minimum bilateral preload from 0.08 N to 0.12 N can preserve bilateral continuity while remaining weak enough to reject stable carry.
batch_5:
  source_commit: 66210bedc4a1f5670608fc8fe39bfda503bd263c
  dependency_model_scene_motion_contract_driver_build: Identical to MNT-CP-012.
  ros_domain_id: 181
  gz_partition: so101-mnt-cal-v3e
  simulation_session_id: so101-mnt-cal-v3e
  reset_epoch: 0
  tmux_session: so101-mnt-cal-v3e
  matrix_output: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/contact-calibration-raw-v3-batch5.json
  proposal_output: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/contact-calibration-proposal-v3-batch5.yaml
  safety_frozen_release_retreat_and_no_contact_method: Identical to batch 4.
  ordered_experiments:
    - [EXP-096, no_contact, "13 table-only plus frozen release/RECOVER_RETREAT[0] and 12 explicit post-release append"]
    - [EXP-097, micro_lift_slip, "only minimum bilateral preload changes from 0.08 N to 0.12 N; same concurrent collector and MICRO_LIFT_ARM motion"]
    - [EXP-098, bilateral_touch, "frozen centered 0.08 N-per-side light touch"]
    - [EXP-099, over_compression, "frozen q6 -0.004 rad increment"]
    - [EXP-100, stable_hold, "frozen centered 0.50 N-per-side preload plus same MICRO_LIFT_ARM and >=0.30 s collector preroll"]
  EXP-097_success: 25 admitted bilateral samples spanning the motion, retained bilateral continuity, and a speed/carry response separable from stable_hold; otherwise stop without changing continuity or sample labels.
  safety_and_frozen_scope: Identical to MNT-CP-012; no q6 step, waypoint, planner, geometry, simulator-state, or threshold change.
decision: PLANNED before batch-5 stack launch. The calibration order moves the unresolved physical regime immediately after the required pre-contact/post-release negative controls to avoid unnecessary later motion if it remains unavailable.
```

## Superseding EXP-072/073/074 displacement audit correction

```yaml
recorded_at: 2026-08-12T16:24:00+08:00
supersedes: The section titled EXP-072 safety-contract audit correction above.
user_correction:
  - maximum pre-contact displacement and terminal total cup displacement are independent driver/monitor fields.
  - The pre-contact safety limit is 0.003 m and fails only when the independent pre-contact field exceeds it.
  - The terminal total-displacement limit is 0.010 m; total displacement alone must not be compared with the 0.003 m pre-contact limit.
corrected_audit:
  EXP-072:
    status: VALID
    behavioral_result: FAILURE
    route_disposition: ABANDONED_AND_EXCLUDED_FROM_CALIBRATION
    total_cup_displacement_m: approximately 0.003473
    total_displacement_contract: PASS because 0.003473 m is below 0.010 m.
    pre_contact_displacement_contract: Use only the driver's independent pre-contact monitor result; total displacement supplies no contrary inference.
  EXP-073:
    status: VALID
    behavioral_result: FAILURE
    route_disposition: ABANDONED_AND_EXCLUDED_FROM_CALIBRATION
  EXP-074:
    status: VALID
    behavioral_result: FAILURE
    route_disposition: ABANDONED_AND_EXCLUDED_FROM_CALIBRATION
prohibited_inference:
  - Do not rewrite EXP-072, EXP-073, or EXP-074 as invalid merely because terminal total displacement exceeds 0.003 m.
  - Do not use any of these abandoned offset-route results as a physical calibration cohort or KEEP candidate.
```

## EXP-096 through EXP-100 terminal results and offline analyzer diagnosis

```yaml
batch_5:
  status: PHYSICAL_COHORTS_VALID_ANALYSIS_FAILED
  lifecycle: FRESH_STACK_EPOCH_0
  physical_results:
    EXP-096: VALID; 25 no_contact samples, 13 table-only and 12 authentic post-release.
    EXP-097: VALID; 25 bilateral micro_lift_slip samples at the preregistered 0.12 N preload; terminal total cup displacement approximately 0.00207 m.
    EXP-098: VALID; 25 bilateral_touch samples.
    EXP-099: VALID; 25 over_compression samples below the unchanged 11.60 N and 0.010 m gates.
    EXP-100: VALID; 25 stable_hold samples after the preregistered 0.30 s preroll.
  raw_evidence:
    path: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/contact-calibration-raw-v3-batch5.json
    sha256: 3e9c05e3ecd7ff63660170e6cf1e542ec9bad2d62716ce2f75deb49046e667f0
    immutable: true
  unilateral_contracts_sha256: a949e8f44c41dfd14edf54d7a153acc9d53d5bab8f50496940b2c403b636eeae
  analyzer_result:
    status: FAILED
    first_failure: The original analyzer used global minimum_signed_distance_m, so allowed table support penetration inverted the fingertip compression ordering.
    post_fix_diagnostic_failure: The first micro_lift_slip sample preceded actual motion and had linear speed approximately 1.38e-08 m/s, overlapping the stable-hold cohort.
    duration_observation: The 0.30 s stable preroll yields early stable samples that overlap the bilateral-touch collection duration; the next batch must use a longer preregistered preroll.
  decision:
    - Preserve batch 5 unchanged as physical and diagnostic evidence, but do not issue or approve its FAILED proposal.
    - Correct fingertip compression semantics and the deterministic per-regime 20/5 split with RED-GREEN tests.
    - Before any new live action, preregister a fresh-source batch that changes sampling timing only: begin slip collection after motion onset and use a 0.60 s stable preroll.
cleanup: Task-owned domain 181 stack was shut down cleanly; no live action remains.
```

## Checkpoint MNT-CP-013 and EXP-101 through EXP-105 preregistration

```yaml
checkpoint_id: MNT-CP-013
recorded_at: 2026-08-12T16:34:00+08:00
last_valid_experiment: EXP-100; its immutable batch is diagnostic evidence, not an approvable proposal source.
current_hypothesis: Sampling after actual micro-lift onset and extending only the stable-hold observation preroll to 0.60 s will yield five physically separable cohorts without changing motion, contact, simulator, or safety policy.
implementation_source_commit: 2253aef3d8fb7f839922d47cf1939ca0331f7963
verified_before_preregistration:
  - RED-GREEN coverage proves allowed table penetration cannot define fingertip compression in the analyzer or live grasp evaluator.
  - The split is per-regime publisher-ordered index modulo five, guaranteeing 20 calibration and 5 evaluation samples from each 25-sample cohort.
  - Package test result: 468 passed, 4 skipped; Ruff lint/format and migration isolation gates passed.
owned_processes: NONE
batch_6:
  ros_domain_id: 182
  gz_partition: so101-mnt-cal-v3f
  simulation_session_id: so101-mnt-cal-v3f
  reset_epoch: 0
  tmux_session: so101-mnt-cal-v3f
  source_commit: 2253aef3d8fb7f839922d47cf1939ca0331f7963
  dependency_commit: f42b7b3d77288c2fee750fe53b0258e0a3d18194
  model_sha256: f87a033fab8cf7291e737519290a639e0310e703f8169288f075f3fe0c8b5aca
  scene_sha256: b98eca6f2ae8547b8b7213625512ef360c5496c7ea2d124535698ea58b24e7c0
  motion_policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
  calibration_driver_sha256: 86b7884dc08a032a85374d1f6a9900aabe3410fbb8a97a6c655f4a26c8d2bf05
  unilateral_contracts_sha256: a949e8f44c41dfd14edf54d7a153acc9d53d5bab8f50496940b2c403b636eeae
  matrix_output: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/contact-calibration-raw-v3-batch6.json
  proposal_output: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/contact-calibration-proposal-v3-batch6.yaml
  ordered_experiments:
    - [EXP-101, no_contact, "Unchanged batch-5 method: 13 table-only plus authentic release/RECOVER_RETREAT[0] and 12 post-release samples"]
    - [EXP-102, micro_lift_slip, "Unchanged 0.12 N preload and unchanged 1.0 s MICRO_LIFT_ARM action; start the collector 0.10 s after the controller action is accepted so every admitted sample is in the physical motion window"]
    - [EXP-103, bilateral_touch, "Unchanged centered 0.08 N-per-side light touch"]
    - [EXP-104, over_compression, "Unchanged q6 -0.004 rad increment"]
    - [EXP-105, stable_hold, "Unchanged centered 0.50 N-per-side preload and MICRO_LIFT_ARM action; only observation preroll extends from 0.30 s to 0.60 s before collection"]
  safety_contract:
    maximum_normal_force_n: 11.60
    maximum_pre_contact_displacement_m: 0.003; evaluate only the independent pre-contact monitor field while that monitor is active.
    maximum_terminal_total_displacement_m: 0.010; do not compare this field with the pre-contact limit.
    other_aborts: stale, truncated, nonfinite, non-monotonic, session/reset/pause mismatch, controller failure, missing declared bilateral contact, or incomplete motion.
  frozen_scope:
    - No unilateral/offset action and no axis, planner, q6 step, force threshold, MJCF, scene, geometry, simulator state, waypoint, or five-win grasp-strategy change.
    - The only differences from batch 5 are admission timing inside the same motion and the stable observation preroll duration.
  stop_rule: Stop at the first INVALID experiment. If all five are VALID, run the installed analyzer and independent evidence audit; never self-approve.
decision: PLANNED before the isolated build, stack launch, or any controller action.
```

## EXP-101 through EXP-105 terminal results and USER_APPROVAL_REQUIRED checkpoint

```yaml
recorded_at: 2026-08-12T16:58:00+08:00
batch_6:
  status: VALID
  lifecycle: FRESH_STACK_EPOCH_0
  simulation_session_id: so101-mnt-cal-v3f
  physical_results:
    EXP-101:
      status: VALID
      regime: no_contact
      observed: 25 samples; 13 table-only and 12 authentic post-release; every sample has zero left and zero right fingertip contact.
      maximum_total_displacement_m: 0.0010716728622378918
    EXP-102:
      status: VALID
      regime: micro_lift_slip
      observed: 25 bilateral samples collected after controller action acceptance; speed range 3.9177127736293275e-07 through 0.002163806880191998 m/s; no side loss.
      maximum_total_displacement_m: 0.0020618565020250304
    EXP-103:
      status: VALID
      regime: bilateral_touch
      observed: 25 bilateral samples; maximum force 0.2598167307265038 N.
    EXP-104:
      status: VALID
      regime: over_compression
      observed: 25 bilateral samples; fingertip compression 0.00018247585456424465 through 0.0001824817120959726 m; maximum force 1.7032279056003339 N.
    EXP-105:
      status: VALID
      regime: stable_hold
      observed: 25 bilateral samples after 0.60 s preroll; contact duration 0.6099999999999568 through 0.8499999999999659 s; maximum total displacement 0.0019991176850923356 m.
  safety:
    - All maximum forces remained below 11.60 N and all terminal total displacements remained below the independent 0.010 m limit.
    - EXP-101 pre-contact collection used the independent 0.003 m pre-contact monitor. No conclusion was inferred by comparing terminal total displacement with 0.003 m.
  raw_evidence:
    path: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/contact-calibration-raw-v3-batch6.json
    sha256: 3610de6a81ad5b5babc9c1d1172509a46d270f48f925e61906b753776369aefb
    collector_source_commit: 2253aef3d8fb7f839922d47cf1939ca0331f7963
analyzer_corrections:
  source_commit: c7afcd9ff149f83e58503848a5d7de6a19ded5ec
  findings:
    - Global minimum_signed_distance_m is a whole-scene diagnostic; fingertip compression now uses only left/right fingertip contact distances in both calibration and live grasp evaluation.
    - The deterministic split is per-regime publisher-ordered index modulo five, so appended negative-control timing cannot change the required 20/5 allocation.
    - Slip threshold fitting and held-out evaluation now use the same window-maximum speed contract as live evaluate_grasp; all atomic acceleration/decay samples remain in raw evidence and quantiles.
    - The strictly positive cross-scale speed threshold uses the geometric midpoint; force, compression, and duration keep linear separating thresholds.
  verification: 469 package tests passed, 4 skipped; Ruff and migration-isolation gates passed.
proposal:
  path: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/contact-calibration-proposal-v3-batch6.yaml
  file_sha256: 41fce814a2e15aa4ca843501e37efd9eb6fbb71dbe47ae6d2240401d544b08e5
  proposal_sha256: 670ffae8b5a1558c667376d62fab22011c65cca26b92b72565f08194fc1de897
  calibration_status: VALID
  approval: {enabled: false, approved: false, approved_by: null, approved_at: null}
  counts: {calibration: 100, evaluation: 25, false_positive: 0, false_negative: 0}
  thresholds:
    minimum_bilateral_force_n: 0.05126429271696818
    maximum_compression_distance_m: 0.00012528745142373227
    maximum_safe_force_n: 1.1579004532160448
    maximum_hold_linear_speed_m_s: 3.591036966769536e-05
    minimum_stable_hold_duration_s: 0.4199999999999875
  safety_margins:
    bilateral_force_n: 0.10252858543393636
    compression_distance_m: 0.00011437680628102478
    safe_force_n: 1.0905530025699317
    hold_linear_speed_m_s: 0.0021632109145069476
    stable_hold_duration_s: 0.3799999999999386
  held_out_matrix: Exactly 5/5 on the diagonal for each of no_contact, bilateral_touch, over_compression, micro_lift_slip, and stable_hold; every off-diagonal cell is zero.
  unilateral_contracts:
    left_only: physical_unreachable; GRASP_RIGHT_CONTACT_MISSING; stable_grasp_allowed false; all physical statistical fields null.
    right_only: observed; GRASP_LEFT_CONTACT_MISSING; stable_grasp_allowed false; all physical statistical fields null.
evidence_summary:
  path: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/contact-calibration-evidence-summary-v3-batch6.yaml
  sha256: 5a0e8d14e74c9c108e3d0d7dc1399d0490dfc7892d4fc7bbd9beb74a5507e861
cleanup: Task-owned tmux so101-mnt-cal-v3f is absent and ROS_DOMAIN_ID 182 has no nodes.
checked_in_policy: schema-v3 PLANNED, enabled false, approved false, proposal hash null; unchanged.
state: USER_APPROVAL_REQUIRED
next_step: Wait for the user to approve exact proposal_sha256 670ffae8b5a1558c667376d62fab22011c65cca26b92b72565f08194fc1de897. Do not self-approve, activate policy, enter Task 9, run the nine-stage regression, run RESET_WORLD five-win qualification, merge, or push main before that exact-hash approval.
```

## Task 9 exact-hash user approval and policy activation

```yaml
approval_event:
  stage_order: After the USER_APPROVAL_REQUIRED checkpoint above.
  user_response: "批准 proposal hash 670ffae8b5a1558c667376d62fab22011c65cca26b92b72565f08194fc1de897"
  user_approved_proposal_sha256: 670ffae8b5a1558c667376d62fab22011c65cca26b92b72565f08194fc1de897
  proposal_embedded_sha256: 670ffae8b5a1558c667376d62fab22011c65cca26b92b72565f08194fc1de897
  comparison: EXACT_MATCH
  approved_by: user
  approved_at_command_time: 2026-08-12T15:33:42+08:00
  clock_audit_note: The command-time wall clock is recorded verbatim even though it is earlier than the pre-existing 16:58 ledger timestamp; stage order is defined by this append position and Git history, not by rewriting either timestamp.
source_proposal:
  path: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/contact-calibration-proposal-v3-batch6.yaml
  file_sha256: 41fce814a2e15aa4ca843501e37efd9eb6fbb71dbe47ae6d2240401d544b08e5
  source_evidence_sha256: 3610de6a81ad5b5babc9c1d1172509a46d270f48f925e61906b753776369aefb
activation:
  mechanism: analyze_contact_calibration --approve with the exact supplied proposal hash
  checked_in_policy: src/so101_mujoco_demo_py/config/contact_calibration.yaml
  checked_in_policy_sha256: c4ba607fea92f7c605fbc8cf08df0dfa3278113c71d1dd6ff10ea402e8186f82
  state: {schema_version: 3, calibration_status: VALID, enabled: true, approved: true}
  thresholds_changed_from_proposal: false
  proposal_content_changed: false
validation:
  analyzer_validate: PASS
  first_focused_run:
    result: 40 passed, 1 failed
    failure: The Task-8 checked-in-artifact test still required PLANNED/disabled after the authorized Task-9 transition.
    diagnosis: Phase-bound test expectation was stale; approval CLI, proposal hash, and policy validation were not the cause.
  contract_test_update:
    scope: Replace the pre-approval state assertion with the exact approved hash plus real runtime-loader and immutable artifact-fingerprint acceptance.
    production_policy_or_threshold_change: false
  final_focused_run: 41 passed in 3.58 s
decision: TASK_9_COMPLETE; the exact user-approved policy is active. No simulation, controller action, formal nine-stage regression, RESET_WORLD five-win challenge, merge, or push was performed in Task 9.
next_step: Execute Task 10 automatic gates, fresh isolated build, and one preregistered FULL_RESTART Project-A physical acceptance cycle before entering Project B.
```

## Task 10 automatic gates and EXP-106 preregistration

```yaml
recorded_at: 2026-08-12T15:46:43+08:00
automatic_gates:
  source_commit: 607d1301e535298e0099e02d5019fe6f0a2b7d1c
  package_tests: 470 passed, 4 skipped
  ruff_check: PASS
  ruff_format_check_only: PASS; 118 files already formatted
  migration_isolation: PASS
  git_diff_check: PASS
  diagnostic_build:
    root: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-build-approved-e7eb844
    result: Build and fork runtime checker passed, but the reset-qualified checker rejected the non-default project install prefix.
    disposition: Diagnostic only; never used for live acceptance.
    root_cause: The checker had no explicit input for Task 10's required fresh project install root and could only enforce the canonical worktree install.
    red_green_fix: A failing path-resolution test preceded the optional --project-install implementation; the default lock-derived behavior remains unchanged.
  acceptance_build:
    root: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-build-approved-607d130
    source_commit: 607d1301e535298e0099e02d5019fe6f0a2b7d1c
    packages: [so101_mujoco_support, so101_mujoco_demo_py]
    build_result: PASS; 2 packages finished
    project_prefixes_exact: true
    mujoco_runtime_check: PASS
    reset_qualified_runtime_check: PASS with explicit acceptance project install
    fork_commit: f42b7b3d77288c2fee750fe53b0258e0a3d18194
EXP-106:
  status: PLANNED
  lifecycle: FULL_RESTART
  qualification_counting: false
  purpose: One Project-A acceptance of the exact user-approved contact policy before Project B; this run cannot count toward the final five-run qualification.
  source_commit: 607d1301e535298e0099e02d5019fe6f0a2b7d1c
  fingerprint:
    dependency_sha256: 1df4cf0677b1d92ae1c64d2e2064fd4dd88d7e92111c74320e7170dd431fde6d
    task_scene_sha256: a2a49391e52d1f885e8ebb4c85fd282d1e83f0ce82eb63e83bac645343b1f9a0
    scene_sha256: b98eca6f2ae8547b8b7213625512ef360c5496c7ea2d124535698ea58b24e7c0
    robot_mjcf_sha256: f87a033fab8cf7291e737519290a639e0310e703f8169288f075f3fe0c8b5aca
    urdf_sha256: 0646707fbfb8fdfea5076afbf89f297027c0324465ab7ebe8129fc36c0445f4a
    motion_policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
    contact_policy_sha256: c4ba607fea92f7c605fbc8cf08df0dfa3278113c71d1dd6ff10ea402e8186f82
    approved_proposal_sha256: 670ffae8b5a1558c667376d62fab22011c65cca26b92b72565f08194fc1de897
  fingerprint_artifact:
    path: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-exp106-fingerprint.json
    sha256: 821988557d8c40f6b69cfc0665fa4abb9bcf335ba8688b5a84b6c31894fb56db
  runtime:
    evidence_root: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-exp106
    batch_id: MNT-A-EXP106
    simulation_session_id: MNT-A-EXP106-full-01
    ros_domain_id: 183
    gz_partition: so101-mnt-a-exp106
    teleop_port: 8023
    headless: false
    tmux_session: so101-mnt-a-exp106
  preflight:
    - Domain 183 has no nodes, TCP port 8023 is not listening, the evidence root and tmux session are absent, and DISPLAY is :1.
    - The fresh acceptance overlay resolves both project packages and the exact pinned fork.
    - No task-owned runtime process exists before registration.
  success_contract:
    - One new MuJoCo, MoveIt, controller, Planning Scene, and Teleop stack reaches READY, applies the viewer preset, and returns a fresh qualified reset receipt at epoch 1 step 0.
    - All nine production phases complete once with controller/action success and joint/TCP convergence.
    - The approved contact policy proves fresh bilateral grasp, causal micro-lift, and stable transport without hidden aid.
    - MoveIt collision-shadow attach/detach readback, release-epoch settle, final target/support/twist, and world-object synchronization all succeed.
    - Ordered shutdown returns zero with its marker and leaves no owned residual process.
  failure_contract: A qualified physical/workflow failure is VALID_FAILURE; provenance, readiness, evidence, lifecycle, or cleanup contamination is INVALID. Either outcome stops after this one attempt.
  frozen_scope:
    - No automatic extra attempt or hidden retry.
    - No axis, planner, q6 step, 3 mm pre-contact gate, 11.60 N safety gate, MJCF, scene, geometry, simulator state, motion waypoint, contact threshold, or five-win grasp-strategy change.
decision: PLANNED and committed before stack launch or controller action. Only the registered production qualification runner may execute EXP-106.
```

## EXP-106 terminal result and startup-boundary remediation

```yaml
recorded_at: 2026-08-12T15:54:19+08:00
EXP-106:
  status: INVALID
  behavioral_result: NOT_STARTED
  attempts_started: 1
  automatic_extra_attempts: 0
  terminal_cause: The fresh acceptance install omitted the workspace runtime package so101_teleop, so the production launch exited with PackageNotFoundError before READY, reset, controller action, or workflow execution.
  runner_result:
    process_exit_code: 1
    manifest: MISSING because the pre-remediation runner allowed StackStartupError to escape before record finalization.
    wrapper_exit_artifact: Contains the malformed literal "1n" and is not used as authoritative exit evidence; the traceback and ros2run failure establish exit 1.
  evidence:
    runner_log: [/tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-exp106-runner.log, f6a23ea693fcb5ff2fa65d0b8081564a78827d5f5aeb8145cf1e2c14e2c91d3d]
    launch_log: [/tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-exp106/run-01/launch.log, 353770b73f217b0f6d329c216ca9c958dadd15044d40d06dfdf2e9de4e7f6092]
    malformed_wrapper_exit_file: [/tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-exp106-exit-code.txt, 741d14df730e53a5a019a710116f696db4ec23a132b74cf6fbb3cf7617e68313]
  cleanup:
    tmux_session_absent: true
    domain_183_nodes: []
    port_8023_listeners: []
    owned_runtime_processes: []
  disposition: Excluded from physical acceptance and from every later streak. Do not reinterpret it as a valid workflow failure or retry it under the same experiment ID.
remediation:
  red_green_contracts:
    - package.xml must declare so101_teleop as the production launch runtime dependency.
    - FULL_RESTART and RESET_WORLD startup failures must each emit exactly one INVALID record, preserve failure and launch-log artifacts, and enter no workflow or retry.
  implementation:
    - StackStartupError retains the owned handle for exact stop/finalization.
    - Failure finalization preserves the first startup cause when shutdown also fails its success-only marker contract.
    - Fresh builds use --packages-up-to so101_mujoco_demo_py and the reset-qualified checker verifies so101_teleop in the same explicit project install.
  verification: 473 package tests passed, 4 skipped; Ruff lint/format, migration isolation, and git diff check passed.
decision: Commit the remediation, create a new unique three-package acceptance build, and preregister EXP-107 before any further live action.
```

## EXP-107 preregistration

```yaml
registered_at: 2026-08-12T15:56:18+08:00
experiment_id: EXP-107
status: PLANNED
lifecycle: FULL_RESTART
qualification_counting: false
purpose: Replacement Project-A acceptance after correcting only EXP-106's missing declared runtime dependency and startup-evidence finalization.
source_commit: 90b6ff8631f8172a24a433af140759d43882faf6
fresh_build:
  root: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-build-approved-90b6ff8
  packages: [so101_teleop, so101_mujoco_support, so101_mujoco_demo_py]
  build_result: PASS; 3 packages finished
  all_three_project_prefixes_exact: true
  mujoco_runtime_check: PASS
  reset_qualified_runtime_check: PASS
fingerprint:
  dependency_sha256: 1df4cf0677b1d92ae1c64d2e2064fd4dd88d7e92111c74320e7170dd431fde6d
  task_scene_sha256: a2a49391e52d1f885e8ebb4c85fd282d1e83f0ce82eb63e83bac645343b1f9a0
  scene_sha256: b98eca6f2ae8547b8b7213625512ef360c5496c7ea2d124535698ea58b24e7c0
  robot_mjcf_sha256: f87a033fab8cf7291e737519290a639e0310e703f8169288f075f3fe0c8b5aca
  urdf_sha256: 0646707fbfb8fdfea5076afbf89f297027c0324465ab7ebe8129fc36c0445f4a
  motion_policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
  contact_policy_sha256: c4ba607fea92f7c605fbc8cf08df0dfa3278113c71d1dd6ff10ea402e8186f82
  approved_proposal_sha256: 670ffae8b5a1558c667376d62fab22011c65cca26b92b72565f08194fc1de897
fingerprint_artifact:
  path: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-exp107-fingerprint.json
  sha256: a4ac6cf1136fe6b622e5c9de7729b3eb877a308a8cc965e08c85b033ddbc5e03
runtime:
  evidence_root: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-exp107
  batch_id: MNT-A-EXP107
  simulation_session_id: MNT-A-EXP107-full-01
  ros_domain_id: 184
  gz_partition: so101-mnt-a-exp107
  teleop_port: 8024
  headless: false
  tmux_session: so101-mnt-a-exp107
preflight:
  - Domain 184 has no nodes, TCP port 8024 is not listening, and the evidence root, runner artifacts, and tmux session are absent.
  - All three declared project runtime packages resolve to the unique fresh install; the fork commit/tag/files remain locked.
success_contract:
  - One new stack reaches READY, applies table_corner_nw, returns a fresh qualified epoch-1 step-0 reset, and completes exactly the nine production phases.
  - Controller/action and joint/TCP convergence, exact approved fresh bilateral grasp, causal micro-lift/stable transport, MoveIt attach/detach readback, release settle, final target/support/twist, and world synchronization all pass.
  - Ordered shutdown exits zero with its marker and leaves no owned process, node, listener, or tmux session.
failure_contract: One VALID_FAILURE or INVALID result terminates this attempt; no automatic extra attempt or hidden retry.
frozen_scope: Identical to EXP-106. No motion, contact threshold, safety gate, planner, model, scene, geometry, simulator-state, waypoint, or five-win strategy change is authorized.
decision: PLANNED and committed before stack launch or controller action. Only the registered production runner may execute EXP-107.
```

## EXP-107 terminal result and owner-argument remediation

```yaml
recorded_at: 2026-08-12T16:00:08+08:00
EXP-107:
  raw_manifest_status: VALID_FAILURE
  corrected_audit_status: INVALID
  behavioral_result: NOT_STARTED
  attempts_started: 1
  automatic_extra_attempts: 0
  completed_boundaries:
    stack_ready: true
    viewer_preset: true
    qualified_reset: {old_epoch: 0, new_epoch: 1, simulation_step: 0}
  workflow:
    http_status: 503
    owner_failure_code: LIVE_RUNTIME_CONFIG_REQUIRED
    nine_phase_execution_started: false
  classification_audit: LIVE_RUNTIME_CONFIG_REQUIRED is a production runtime-configuration defect, not a qualified physical outcome; preserve the raw manifest but exclude this run as INVALID.
  clean_shutdown: {passed: true, returncode: 0, ordered_shutdown_marker: true, process_died: false, fatal_signal: false}
  runner_exit_code: 1
  evidence:
    qualification_manifest: [/tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-exp107/qualification-manifest.json, ea5edba919aa27e645b0eccd40ee32f4b96d13dad75445083d30fc45b867b47e]
    actions: [/tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-exp107/run-01/actions.json, 9194a823e441b37b5328b7cd2a23c5455f175d35f625bd060fecf264775a02c5]
    launch_log: [/tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-exp107/run-01/launch.log, 070341d3c7675fcb9f960e6610ad921ba5433238de9e629ed258d9e2c3e19f35]
    runner_log: [/tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-exp107-runner.log, 1ae7f459e47865b534a4976fc1e9c1e957f214c06fc4b2aa3261657d845f7b1e]
    exit_code_file: [/tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-exp107-exit-code.txt, 4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865]
  cleanup: {tmux_session_absent: true, domain_184_nodes: [], port_8024_listeners: [], owned_runtime_processes: []}
  disposition: Excluded from Project-A physical acceptance and every later streak; never rewrite as a physical VALID_FAILURE.
root_cause: teleop_workflow.production_arguments stopped after --motion-policy and did not pass the Task-8-required installed --contact-policy to the production CLI. Its existing test title promised the installed policy but lacked the corresponding assertion.
remediation:
  red_green_contracts:
    - Teleop owner argv contains the installed config/contact_calibration.yaml path.
    - LIVE_RUNTIME_CONFIG_REQUIRED and other enumerated owner configuration/provenance failures raise INVALID instead of entering physical-failure counting.
  production_change: Add only the installed --contact-policy argument and fail-visible classification; no policy value, threshold, motion, planner, model, scene, or simulator state changed.
  verification: 474 package tests passed, 4 skipped; Ruff lint/format, migration isolation, and git diff check passed.
decision: Commit the remediation, create another unique complete runtime build, and preregister EXP-108 before any further live action.
```

## EXP-108 preregistration

```yaml
registered_at: 2026-08-12T16:02:41+08:00
experiment_id: EXP-108
status: PLANNED
lifecycle: FULL_RESTART
qualification_counting: false
purpose: Project-A acceptance of the production owner with the installed exact approved contact policy now bound into its argv.
source_commit: 73ee752c02ba9c69fc1d11b81319733b61baf3e8
fresh_build:
  root: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-build-approved-73ee752
  packages: [so101_teleop, so101_mujoco_support, so101_mujoco_demo_py]
  build_and_three_prefixes: PASS
  mujoco_runtime_check: [/tmp/so101-debug-mujoco-maintainability-remediation/project-a-build-73ee752-runtime-check.json, 7aafeb88b3169104bd1ae1e52f6650c8b4b0cb3d7ca7b936dd4df2f757c5fc8e]
  reset_qualified_runtime_check: [/tmp/so101-debug-mujoco-maintainability-remediation/project-a-build-73ee752-reset-check.json, 6dfdf07333db31d09d301e5b98a677dd9890228e70a9259418a05b342544b087]
fingerprint:
  dependency_sha256: 1df4cf0677b1d92ae1c64d2e2064fd4dd88d7e92111c74320e7170dd431fde6d
  task_scene_sha256: a2a49391e52d1f885e8ebb4c85fd282d1e83f0ce82eb63e83bac645343b1f9a0
  scene_sha256: b98eca6f2ae8547b8b7213625512ef360c5496c7ea2d124535698ea58b24e7c0
  robot_mjcf_sha256: f87a033fab8cf7291e737519290a639e0310e703f8169288f075f3fe0c8b5aca
  urdf_sha256: 0646707fbfb8fdfea5076afbf89f297027c0324465ab7ebe8129fc36c0445f4a
  motion_policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
  contact_policy_sha256: c4ba607fea92f7c605fbc8cf08df0dfa3278113c71d1dd6ff10ea402e8186f82
  approved_proposal_sha256: 670ffae8b5a1558c667376d62fab22011c65cca26b92b72565f08194fc1de897
fingerprint_artifact: [/tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-exp108-fingerprint.json, 3342dcafe80fb66170bec18484172e4097236261c6fbaa909dd5644b579728a2]
runtime:
  evidence_root: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-exp108
  batch_id: MNT-A-EXP108
  simulation_session_id: MNT-A-EXP108-full-01
  ros_domain_id: 185
  gz_partition: so101-mnt-a-exp108
  teleop_port: 8025
  headless: false
  tmux_session: so101-mnt-a-exp108
preflight: Domain 185 empty; port 8025, evidence paths, and tmux session absent; complete fresh overlay and fingerprint validated.
success_contract: Identical to EXP-107; one READY/reset/nine-phase physical success plus ordered exact cleanup is required.
failure_contract: One VALID_FAILURE or INVALID terminates the attempt; no automatic extra attempt or hidden retry.
frozen_scope: Identical to EXP-106/107; only the RED-GREEN owner argv/classification remediation differs.
decision: PLANNED and committed before stack launch or controller action. Only the registered production runner may execute EXP-108.
```

## EXP-108 terminal result and frozen-strategy continuity audit

```yaml
recorded_at: 2026-08-12T16:10:33+08:00
EXP-108:
  raw_manifest_status: INVALID
  corrected_audit_status: INVALID
  behavioral_observation: MICRO_LIFT_MONITOR_ABORTED_AFTER_WEAK_CONTACT_HOLD
  qualification_counting: false
  attempts_started: 1
  automatic_extra_attempts: 0
  completed_boundaries:
    stack_ready: true
    viewer_preset: true
    qualified_reset: {old_epoch: 0, new_epoch: 1, simulation_step: 0}
    phases: [staged_approach, contact_hold]
  failed_phase: micro_lift
  owner_failure_code: PHASE_EXIT_NONZERO
  contact_hold:
    terminal_q6_rad: -0.04746121642596459
    hold_sample_count: 201
    left_force_n: {minimum: 0.12747616840546888, median: 0.12749057577425185, maximum: 0.1275179284008805}
    right_force_n: {minimum: 0.2481112377685798, median: 0.24812448588628147, maximum: 0.24813107655140987}
  micro_lift:
    moveit_attachment_readback: true
    trajectory_points: 6
    plan_to_execute_drift_rad: 6.065419833056751e-09
    pre_lift_bilateral: true
    failure: MOVEIT_EXECUTION_MONITOR_ABORTED
  clean_shutdown: {passed: false, returncode: 0, ordered_shutdown_marker: false, process_died: true, fatal_signal: false, signal: SIGINT}
  lifecycle_audit: move_group required SIGTERM then SIGKILL after the monitor abort; regardless of the physical observation, failed ordered cleanup makes the attempt INVALID.
  evidence:
    qualification_manifest: [/tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-exp108/qualification-manifest.json, facfab4bfc84a1bc6e9997f38e1962b63b8cc9821d3a16653617edb670a792f9]
    actions: [/tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-exp108/run-01/actions.json, 426d52de5e956ff63680e9aca700a68a013cd26793c527c5f657b5eaf121d8be]
    launch_log: [/tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-exp108/run-01/launch.log, cca38813713d61018cc3f4bcf891701cc685e560303ef781101079044317ade2]
    runner_log: [/tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-exp108-runner.log, 6a3bf6e490859eb4470991d733216a599c736da1008a82c068b1911d8d1cb762]
    contact_hold: [/tmp/so101-teleop-evidence/MNT-A-EXP108-full-01/so101-teleop-workflow-cfbff2ca-439a-49fe-af1b-14010b0b48d8/contact-hold.json, c30dd6bd150e3a18a76bec4887ac398438eff855ca47a6b43406bcd037b10dae]
    micro_lift: [/tmp/so101-teleop-evidence/MNT-A-EXP108-full-01/so101-teleop-workflow-cfbff2ca-439a-49fe-af1b-14010b0b48d8/micro-lift.json, eff8a07923d8032dab6413145f640c32536514a308a5e42d0384c3596932257b]
    owner_manifest: [/tmp/so101-teleop-evidence/MNT-A-EXP108-full-01/so101-teleop-workflow-cfbff2ca-439a-49fe-af1b-14010b0b48d8/live-runtime-manifest.json, 8f16e4fbcd0abdbcf6942bf19ce18add1ba8476ce1420d8fa6e528f051a09ba5]
  cleanup: {tmux_session_absent: true, domain_185_nodes: [], port_8025_listeners: [], owned_runtime_processes: []}
  disposition: Excluded from Project-A acceptance and every later streak. No additional live attempt is authorized by this entry.
continuity_audit:
  approved_threshold_role: 0.05126429271696818 N is the calibrated bilateral contact/rejection boundary; it is not an actuator preload target.
  migration_defect: Task 7 mechanically replaced the former 0.50 N contact-hold preload stop with minimum_bilateral_force_n, conflating contact classification with the already frozen five-win seating action.
  frozen_five_win_evidence:
    runs: [TASK15-FULL-B-full-01, TASK15-FULL-B-full-02, TASK15-FULL-B-full-03, TASK15-FULL-B-full-04, TASK15-FULL-B-full-05]
    terminal_q6_range_rad: [-0.04852635062241919, -0.04850666907805639]
    minimum_bilateral_force_range_n: [0.5054192607622616, 0.5187254499507077]
    result: five PHYSICAL_MICRO_LIFT_PROVED outcomes on the frozen strategy
  existing_strategy_identity:
    micro_lift_preload_q6_rad: -0.04850794875050089
    source: The value already gates MICRO_LIFT and matches the five-win contact-hold terminal range; restoring CONTACT_HOLD to this existing target changes no q6, waypoint, planner, threshold, model, scene, or simulator state.
  cancellation_defect: MoveItExecutionClient sent cancel asynchronously and returned immediately; the phase then destroyed its node while move_group still owned the active trajectory, preventing ordered shutdown and erasing the monitor message from phase evidence.
planned_red_green:
  - Prove CONTACT_HOLD separates the approved contact-detection boundary from the existing frozen seating-preload target and never opens an already more-closed gripper.
  - Prove CONTACT_HOLD and MICRO_LIFT consume one shared immutable frozen target rather than duplicated literals.
  - Prove monitor abort and execution timeout await bounded cancel acknowledgement and terminal action result, retaining the causal monitor message.
  - Keep all approved proposal bytes, policy hashes, safety gates, motion-policy bytes, MJCF, scene, geometry, planner, steps, and waypoints unchanged.
decision: Implement only the RED-GREEN continuity and cleanup fixes; run no live action until they are committed, freshly built, and a new experiment is separately preregistered.
```

## EXP-108 RED-GREEN remediation result

```yaml
recorded_at: 2026-08-12T16:16:04+08:00
source_commit_before_change: 3ba4b0d3ec8f95873a6164e8f2ea6b7549bd1eec
red:
  command: PYTHONPATH=$PWD/src/so101_mujoco_demo_py:$PYTHONPATH PYTHONNOUSERSITE=1 python3 -m pytest -q src/so101_mujoco_demo_py/test/test_live_grasp_strategy.py src/so101_mujoco_demo_py/test/test_moveit_boundary.py
  observed: Collection failed because the shared frozen grasp-strategy module did not exist.
green:
  focused: 15 passed
  complete_package: 478 passed, 4 skipped
  lint: Ruff 0.15.20 check PASS
  format: Ruff 0.15.20 format check PASS (120 files already formatted)
  migration_isolation: PASS
  git_diff_check: PASS
immutable_fingerprint_recheck:
  contact_policy_sha256: c4ba607fea92f7c605fbc8cf08df0dfa3278113c71d1dd6ff10ea402e8186f82
  motion_policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
  robot_mjcf_sha256: f87a033fab8cf7291e737519290a639e0310e703f8169288f075f3fe0c8b5aca
  scene_sha256: b98eca6f2ae8547b8b7213625512ef360c5496c7ea2d124535698ea58b24e7c0
  urdf_sha256: 0646707fbfb8fdfea5076afbf89f297027c0324465ab7ebe8129fc36c0445f4a
changes:
  - Shared the already-existing five-win preload target between CONTACT_HOLD and MICRO_LIFT.
  - Preserved the approved bilateral threshold solely as an observation/rejection boundary.
  - Added bounded action cancellation settlement and retained the causal monitor message.
  - Added the detected-contact q6 and applied preload target to contact-hold evidence.
unchanged: [approved proposal, approved policy, motion policy, q6 target, q6 steps, arm waypoints, planner, safety gates, MJCF, scene, geometry, simulator state]
live_actions_after_EXP-108: 0
decision: Commit this lifecycle/continuity repair, then create a fresh three-package build. A further live acceptance requires separate preregistration.
```

## EXP-109 preregistration

```yaml
registered_at: 2026-08-12T16:19:40+08:00
experiment_id: EXP-109
status: PLANNED
lifecycle: FULL_RESTART
qualification_counting: false
purpose: Project-A acceptance of the approved policy with the frozen five-win seating action restored and bounded MoveIt cancellation settlement.
source_commit: 4bade81c53390e6462ecc559e051ebdf3153c1cb
fresh_build:
  rejected_environment_attempt:
    root: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-build-approved-4bade81
    result: BUILD_FAILED_BEFORE_RUNTIME
    cause: The shell omitted the pinned fork overlay and resolved the older system mujoco_ros2_control plugin API.
    evidence: [/tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-build-approved-4bade81/log/latest_build/logger_all.log, 510116b5572102c746e211c782fd0dc70c02c358b91f897e6377bfade516e8f4]
    disposition: Environment-only build attempt; no stack, reset, controller, or live action existed.
  qualified:
    root: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-build-approved-4bade81b
    packages: [so101_teleop, so101_mujoco_support, so101_mujoco_demo_py]
    pinned_fork_overlay: /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install
    build_and_three_prefixes: PASS
    mujoco_runtime_check: [/tmp/so101-debug-mujoco-maintainability-remediation/project-a-build-4bade81-runtime-check.json, 7aafeb88b3169104bd1ae1e52f6650c8b4b0cb3d7ca7b936dd4df2f757c5fc8e]
    reset_qualified_runtime_check: [/tmp/so101-debug-mujoco-maintainability-remediation/project-a-build-4bade81-reset-check.json, 440b04337690f87c03ad7c31b0f3177de5e6ebb4bf40dd364c24fef5a405cb11]
fingerprint:
  dependency_sha256: 1df4cf0677b1d92ae1c64d2e2064fd4dd88d7e92111c74320e7170dd431fde6d
  task_scene_sha256: a2a49391e52d1f885e8ebb4c85fd282d1e83f0ce82eb63e83bac645343b1f9a0
  scene_sha256: b98eca6f2ae8547b8b7213625512ef360c5496c7ea2d124535698ea58b24e7c0
  robot_mjcf_sha256: f87a033fab8cf7291e737519290a639e0310e703f8169288f075f3fe0c8b5aca
  urdf_sha256: 0646707fbfb8fdfea5076afbf89f297027c0324465ab7ebe8129fc36c0445f4a
  motion_policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
  contact_policy_sha256: c4ba607fea92f7c605fbc8cf08df0dfa3278113c71d1dd6ff10ea402e8186f82
  approved_proposal_sha256: 670ffae8b5a1558c667376d62fab22011c65cca26b92b72565f08194fc1de897
fingerprint_artifact: [/tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-exp109-fingerprint.json, 1422aeae4fd14757d691c86569a92855507e522dc8c1efec7f33bb70521102d1]
runtime:
  evidence_root: /tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-exp109
  batch_id: MNT-A-EXP109
  simulation_session_id: MNT-A-EXP109-full-01
  ros_domain_id: 186
  gz_partition: so101-mnt-a-exp109
  teleop_port: 8026
  headless: false
  tmux_session: so101-mnt-a-exp109
preflight: Domain 186 empty; port 8026, evidence paths, and tmux session absent; complete fresh overlay and fingerprint validated.
success_contract: One READY/viewer-preset/reset/nine-phase physical success plus ordered exact cleanup. This one-cycle Project-A gate cannot count toward later five-win batches.
failure_contract: One VALID_FAILURE or INVALID terminates the attempt; no automatic extra attempt or hidden retry.
frozen_scope:
  changed: Only the restored, already-proven fixed seating action and bounded cancellation ownership from commit 4bade81.
  unchanged: Approved proposal/policy, motion policy bytes, q6 target/steps, arm waypoints, planner, safety gates, MJCF, scene, geometry, simulator state, and all later phase actions.
decision: PLANNED and committed before stack launch or controller action. Only the registered production runner may execute EXP-109.
```

## EXP-109 terminal result and Project-A safety incompatibility

```yaml
recorded_at: 2026-08-12T16:23:53+08:00
EXP-109:
  status: VALID_FAILURE
  qualification_counting: false
  attempts_started: 1
  automatic_extra_attempts: 0
  completed_boundaries:
    stack_ready: true
    viewer_preset: true
    qualified_reset: {old_epoch: 0, new_epoch: 1, simulation_step: 0}
    phases: [staged_approach, contact_hold, micro_lift, policy_lift_waypoint1, remaining_lift]
  failed_phase: transport
  owner_failure_code: PHASE_EXIT_NONZERO
  physical_results:
    contact_hold:
      detected_contact_q6_rad: -0.047409064174229305
      applied_frozen_preload_target_q6_rad: -0.04850794875050089
      terminal_q6_rad: -0.0484552286503998
      hold_sample_count: 202
      left_force_n: {minimum: 0.44577264723800947, median: 0.48786628264273313, maximum: 0.4879654084905088}
      right_force_n: {minimum: 0.5643542673147518, median: 0.6063307446047648, maximum: 0.6063390767054695}
    micro_lift: {status: PHYSICAL_MICRO_LIFT_PROVED, lift_m: 0.001975099095001126, lateral_m: 0.00035462683844240803}
    policy_lift_waypoint1: {status: POLICY_LIFT_WAYPOINT1_PHYSICAL_TRANSFER_PROVED, lift_m: 0.00806667112769921, lateral_m: 0.010690703094017297}
    remaining_lift: {status: REMAINING_FORMAL_LIFT_PROVED, segments: 4}
    transport:
      before_maximum_normal_force_n: 0.7681921528117486
      attempted_waypoint: 1
      failure: MOVEIT_EXECUTION_MONITOR_ABORTED
      cause: force boundary exceeded during transport
      approved_limit_n: 1.1579004532160448
      breach_observation: The live maximum exceeded 1.1579004532160448 N; the transitional phase did not persist the exact aborting sample, so no exact peak is claimed.
  clean_shutdown: {passed: true, returncode: 0, ordered_shutdown_marker: true, process_died: false, fatal_signal: false, signal: SIGINT}
  cancellation_fix_validation: PASS; the action canceled and settled, move_group emitted SO101_MOVE_GROUP_ORDERED_SHUTDOWN_OK, and no SIGTERM/SIGKILL escalation occurred.
  evidence:
    qualification_manifest: [/tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-exp109/qualification-manifest.json, 746c945a0273414c45617930f6646f2ad085ac2af97f35406e08d0daf52fb7f0]
    actions: [/tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-exp109/run-01/actions.json, a52cdaba26e0cbc96d8ec079df2842bdb5d06d38a1d91cd3ab71e890d33a14e2]
    launch_log: [/tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-exp109/run-01/launch.log, 2145df627edf9de0590e332dc83a0c5dc5b775189c59f779f1d414fdc6685d8e]
    runner_log: [/tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-exp109-runner.log, ae07180acc22488746813d95310973c5f3bf643b1386b726732b62d922920ca5]
    owner_manifest: [/tmp/so101-teleop-evidence/MNT-A-EXP109-full-01/so101-teleop-workflow-da6ff72d-960d-409a-874e-9a2aa0bd4496/live-runtime-manifest.json, 7312e6190bc0f1a3286b56a4655297470342862c6594f8f8548bb7b72102c1de]
    contact_hold: [/tmp/so101-teleop-evidence/MNT-A-EXP109-full-01/so101-teleop-workflow-da6ff72d-960d-409a-874e-9a2aa0bd4496/contact-hold.json, 0e3e6fabb17db2541dc34f9625078536ca9f234934efdcd2cfc2e715c86b613f]
    micro_lift: [/tmp/so101-teleop-evidence/MNT-A-EXP109-full-01/so101-teleop-workflow-da6ff72d-960d-409a-874e-9a2aa0bd4496/micro-lift.json, ce5cfa63c5e6e0c172158d4df9eb09cd807113dca6f6e67a5bf43963fa384402]
    transport: [/tmp/so101-teleop-evidence/MNT-A-EXP109-full-01/so101-teleop-workflow-da6ff72d-960d-409a-874e-9a2aa0bd4496/transport.json, d7f1ed211f6be656e02564ca1de41015b11a03c98985e79f2cf47a2341049301]
  cleanup: {domain_186_nodes: [], port_8026_listeners: [], tmux_session_absent: true, owned_runtime_processes: []}
  disposition: This valid physical safety failure terminates Project-A acceptance. Do not create EXP-110 or continue into Project B under the present frozen contract.
safety_compatibility_audit:
  approved_calibration:
    stable_hold_p95_maximum_normal_force_n: 0.6125653910063235
    over_compression_p05_maximum_normal_force_n: 1.7031795072193083
    approved_maximum_safe_force_n: 1.1579004532160448
  historical_same_strategy:
    source: TASK15-FULL-B five consecutive successes
    transport_waypoint1_terminal_force_range_n: [2.7456872063067905, 2.761349835927339]
    transport_terminal_peak_range_n: [4.912516652001531, 4.9746674881770785]
  conclusion: The unchanged five-win carry path exceeds the newly approved safety boundary deterministically; treating the boundary as a grace-timed warning or restoring the old 11.60 N runtime limit would weaken the approved gate, while altering q6/carry motion would change the user-frozen grasp strategy.
  rejected_routes:
    - Do not add a transient-force grace to bypass maximum_safe_force_n.
    - Do not restore 11.60 N as the runtime acceptance limit or edit the approved proposal/policy without a new exact user approval.
    - Do not modify q6, planner, velocity, waypoints, MJCF, scene, geometry, simulator state, or the five-win strategy without explicit new authority.
checkpoint:
  status: USER_DIRECTION_REQUIRED
  completed: Approved-policy activation, RED-GREEN preload continuity, full 478-pass package gate, fresh three-package build, runtime provenance checks, and cleanly classified EXP-109.
  blocked: Project-A requires one successful full physical cycle, but its approved force gate and frozen carry strategy are mutually incompatible.
  downstream_not_started: [Project B, Project C, Project D, formal nine-stage regression, RESET_WORLD five-win challenge, merge to main, remote push]
  required_authority: Either authorize redesign of the carry/gripper strategy to remain below the approved 1.1579004532160448 N gate, or authorize a new physical calibration/proposal cycle and later approve its exact hash. No option is self-approved.
```

## Checkpoint MNT-CP-014 — phase-aware calibration authorization

```yaml
checkpoint_id: MNT-CP-014
recorded_at: 2026-08-12T16:34:33+08:00
last_valid_experiment: EXP-109, VALID_FAILURE and excluded from qualification success counting
current_hypothesis: A phase-aware evidence schema can retain the approved static-contact threshold while measuring frozen-strategy dynamic transport under the unchanged 11.60 N absolute diagnostic stop.
working_tree_status:
  source_commit: a172765e3b193bfccad9782d02e2745e70f1cbd2
  branch: codex/so101-mujoco-ros2-teleop
  tracked_changes_before_this_entry: NONE
  preserved_untracked_user_files:
    - docs/experiments/so101-gazebo-mujoco-policy-parity-solver-iters-ledger.md
    - docs/experiments/so101-mujoco-ros2-migration-experiment-summary.md
provenance:
  host: AI-STATION-001
  worktree: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
  fork_submodule_commit: f42b7b3d77288c2fee750fe53b0258e0a3d18194
  fork_tag: so101-0.0.3-r5
owned_processes: NONE
preserved_processes:
  - tmux codex remains attached and belongs to the current coding session.
  - tmux codex-cua is idle after historical passive captures; it was inspected but not controlled.
  - tmux so101-mujoco-gui contains historical windows; no MuJoCo, move_group, RViz, pick-place, Teleop server, or Gazebo process was observed by the scoped process probe.
  - ROS domain 0 node probe returned no nodes.
last_trusted_checkpoint: EXP-109 terminal record at commit a172765; clean shutdown passed and all owned domain-186/port-8026 processes were absent afterward.
EXP-109_conclusion:
  observed:
    - Frozen preload target q6=-0.04850794875050089 was applied without changing the five-win strategy.
    - CONTACT_HOLD, MICRO_LIFT, policy lift waypoint 1, and the remaining four LIFT segments passed.
    - Transport waypoint 1 crossed 1.1579004532160448 N and the then-static hard monitor returned a clean VALID_FAILURE.
    - Historical same-strategy transport terminal forces are 2.7456872063067905..4.9746674881770785 N, still below the unchanged 11.60 N absolute diagnostic stop.
  correction_from_new_authorization: Exceeding 1.1579004532160448 N during transport is a shadow observation, not proof that the frozen strategy failed; static and dynamic phases must no longer share that hard-stop interpretation.
user_authorization_verbatim: |-
  你当前直接运行在 ai-station 上。不要 ssh 到 ai-station；仓库、tmux、进程、CUA 和截图命令都在当前主机直接执行。

  用户现已明确批准新的 phase-aware 接触校准/提案周期，并再次强调：坚决不要改动之前成功的五连胜策略。

  授权与硬边界：
  1. 完全冻结此前五连胜策略及其全部行为参数和模型：固定预载 q6=-0.04850794875050089、所有 q6/waypoint/轨迹、规划器、速度/加速度、MJCF、scene、geometry、初始状态和运动阶段设计均不得修改，也不得用新补偿逻辑变相改变。
  2. 当前已批准的 1.1579004532160448 N 继续作为静态接触阶段的正式阈值；运输阶段只把它作为 shadow 诊断观测，不得用它触发运输硬停止，也不得把运输超出它解释成策略失效。
  3. 新鲜动态运输采样期间保留原 11.60 N 作为绝对硬停止，仅用于诊断采样安全保护；不得把 11.60 N 直接恢复成新的接受阈值，也不得用 grace period 绕过安全门。
  4. 正式设计 phase-aware 契约：静态接触与动态运输分开；运输证据至少区分瞬时力峰/冲量、持续过压的时间窗口、压缩距离，并记录原始可复核样本。先预登记实验，引用 EXP-109，冻结唯一变量和判据，再执行。
  5. 只允许为测量、日志、分析器、proposal 生成和对应 RED→GREEN 测试做最小代码修改；不得改变抓取/搬运策略本身。继续遵守 provenance、包级测试、运行时证据、干净 shutdown 和 ledger 状态机。
  6. 生成新的 exact-hash proposal 后必须立即停止并请求用户审批；禁止自行批准、激活或把新阈值写入正式运行策略。
  7. 在新 exact hash 获批前，不得继续 Project B/C/D、正式九阶段回归、RESET_WORLD 五连胜、merge 或 push。
  8. 保留且不要提交两个无关未跟踪文档：
     - docs/experiments/so101-gazebo-mujoco-policy-parity-solver-iters-ledger.md
     - docs/experiments/so101-mujoco-ros2-migration-experiment-summary.md
phase_aware_authority:
  static_contact:
    formal_threshold_n: 1.1579004532160448
    semantics: Existing approved hard acceptance/rejection threshold for static contact phases.
  dynamic_transport:
    shadow_threshold_n: 1.1579004532160448
    semantics: Diagnostic crossing marker only; it never cancels transport and never classifies the frozen strategy as failed.
    absolute_diagnostic_hard_stop_n: 11.60
    required_metrics: [instantaneous_peak_force, force_impulse, sustained_overpressure_windows, compression_distance, raw_replayable_samples]
  approval: A new disabled exact-hash proposal is authorized; activation or approval is not.
disproven_routes:
  - Modifying the successful five-win strategy to satisfy the static threshold during transport.
  - Treating dynamic transport crossings of 1.1579004532160448 N as a hard failure.
  - Restoring 11.60 N as a proposal acceptance threshold or bypassing it with a grace period.
open_risks:
  - The existing evidence schema has no explicit phase discriminator or dynamic force-time/compression aggregates.
  - EXP-109 did not persist the exact aborting sample; a fresh preregistered diagnostic run is required after measurement RED-GREEN implementation.
next_experiment_new_information:
  prior: EXP-109 proves the frozen strategy reaches transport and that cancellation/cleanup are reliable, but only records a threshold crossing.
  new: The next experiment will preserve every behavior input and add only raw phase-tagged measurement sufficient to derive peak, impulse, sustained-overpressure duration, and compression distributions under the 11.60 N absolute stop.
next_experiment: NONE_PENDING_WRITTEN_DESIGN_APPROVAL
next_command: Read and review the proposed phase-aware design; no code, build, stack, reset, controller, GUI, or experiment action precedes approval.
```

## Checkpoint MNT-CP-015 — reviewed phase-aware design and implementation authorization

```yaml
checkpoint_id: MNT-CP-015
recorded_at: 2026-08-12T17:25:25+08:00
last_valid_experiment: EXP-109, VALID_FAILURE under the superseded transport force interpretation
current_hypothesis: Every 2 ms physics step can be recorded and replayed while typed phase semantics retain the approved static threshold and make the same value shadow-only after transport goal dispatch.
authorization:
  approval: The user explicitly approved the locally reviewed phase-aware design, implementation, and five independent FULL_RESTART dynamic-transport samples; no further design approval is required.
  execution_host: Commands run directly on AI-STATION-001; SSH to ai-station is forbidden.
  exact_stop: Generate one disabled exact-hash proposal, set USER_APPROVAL_REQUIRED, and stop without approval, activation, downstream projects, regression, merge, or push.
  user_boundaries:
    - Freeze q6=-0.04850794875050089, every q6/waypoint/trajectory, planner, velocity/acceleration, initial pose, MJCF, scene, geometry, phase order, and normal execution semantics.
    - Do not introduce compensation, force filtering, delay, grace period, replanning, or another strategy mutation.
    - Retain 1.1579004532160448 N as the formal static hard gate; after waypoint 1 goal dispatch it is shadow-only and cannot cancel transport or classify strategy failure.
    - Retain 11.60 N only as a dynamic diagnostic absolute stop, using >= with no grace; never emit it as an acceptance threshold.
    - Preserve and never stage docs/experiments/so101-gazebo-mujoco-policy-parity-solver-iters-ledger.md and docs/experiments/so101-mujoco-ros2-migration-experiment-summary.md.
review_amendments:
  P0_physics_step_integrity:
    observed_defect: scene.xml timestep is 0.002 s (500 Hz), ordinary evidence publishes at 100 Hz, trylock can skip a publish, and old simulation_step counts successful builds rather than physics steps.
    required_change: Compute and latch true physics_step, raw tracked contacts, per-side forces/compression, force-time terms, threshold crossings, evidence loss, and the first >=11.60 N breach inside the plugin update boundary for every physics step.
    transport: Keep ordinary 100 Hz snapshots, plus continuous-range lossless chunks that retain queued samples across failed trylock attempts and make any gap/overflow detectable.
    claims: Do not call the old data an instantaneous physics peak or gap-free raw trace. Do not claim same-step stop.
    reaction_contract: Latch and request hazard notification in the breaching callback; record cancellation-request step and require no more than 25 physics steps / 0.050 s live latency. A later/missing response is INVALID and stops the batch.
    red_green: Cover a 500 Hz intermediate spike, detectable trylock failure, continuous true steps, equality at 11.60 N, and a non-overwritable first latch.
  P1_typed_phase_boundary:
    PRE_TRANSPORT_STATIC_HOLD: Stationary bilateral confirmation before waypoint 1 dispatch; >1.1579004532160448 N fails closed.
    DYNAMIC_TRANSPORT_SHADOW: Begins at waypoint 1 ExecuteTrajectory goal dispatch and includes execution, settle/stable windows, inter-waypoint holds/planning, all later waypoints, and transport outcome; the static threshold is diagnostic only.
    implementation: Split or explicitly parameterize the reused stable_bilateral helper with a typed policy; strings and implicit no-argument semantics are forbidden.
  P1_metric_definitions:
    maximum_normal_force_n: Preserve as the largest single normal force among all tracked cup contacts; only this same-semantics metric is compared with the static shadow threshold.
    required_scalars: [left_fingertip_total_normal_force_n, right_fingertip_total_normal_force_n, fingertip_max_single_contact_force_n, global_max_single_contact_force_n]
    scalar_integral: Name the maximum-single-contact time integral force_time_exposure_n_s; never call it object impulse.
    physical_impulse: Sum each per-step contact force-on-cup vector, then integrate over simulation time as net_contact_impulse_vector_n_s.
    compression: Use only cup-to-left/right-fingertip whitelist pairs; table and other contacts are excluded; truncation invalidates the run.
  P1_time_and_validity:
    clock: Integrate only with simulation time/physics timestep, never receipt wall time.
    identity: session, reset_epoch, physics_step, and simulation_time must be strict and mutually consistent.
    invalid: Missing, duplicate, reversed, cross-reset, truncated, gap-crossing, or unclosed phase/waypoint data invalidates the run and stops the batch.
    boundaries: Do not connect integration across phase or waypoint boundaries; store explicit start/end samples.
    overpressure_rule: A window is a maximal consecutive run of samples with maximum_normal_force_n > 1.1579004532160448; no interpolation or grace; duration is sample_count times 0.002 s.
    durability: Atomically checkpoint content-addressed raw chunks and run index continuously, at least at every waypoint, so safety abort and abnormal shutdown retain a readable hashed prefix.
  P1_statistics:
    independent_units: Exactly five independent FULL_RESTART runs.
    within_run: Waypoints are repeated measures / stratified detail, never 25 independent samples.
    roles: Runs 1-4 are descriptive repeats; run 5 is preregistered replication, not training/holdout.
    replication_criteria: Validate identical frozen strategy, complete/replayable data, existing physical transport-success contract, and deterministic metric recomputation only.
    stopping: Every run transitions independently PLANNED->RUNNING->VALID/INVALID; VALID_SAFETY_ABORT or INVALID stops the batch with no replacement.
  P1_frozen_behavior_manifest:
    baseline: 8f71442/a172765 behavior is frozen before any source change.
    manifest_path: docs/experiments/so101-mujoco-phase-aware-frozen-behavior-manifest.json
    manifest_sha256: 912746ac6f6ac6589d5c11d7e9b9483e1ea4ebfeb3f6118a84ee0df48cd54195
    supplied_hashes:
      motion_policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
      grasp_strategy_sha256: 8ae37f96c2408ca061ca5c87c41ff6d92f320e273b9a5a8c4bc778c46fda2239
      transport_baseline_sha256: d2edcb461416f462503ae5b4f31ae55579ae5882a0c6340467871c61015930cd
      scene_sha256: b98eca6f2ae8547b8b7213625512ef360c5496c7ea2d124535698ea58b24e7c0
      robot_mjcf_sha256: f87a033fab8cf7291e737519290a639e0310e703f8169288f075f3fe0c8b5aca
    enforcement: Compare typed policy fields and relevant Python AST call semantics after instrumentation, plus a restricted path diff; do not require unchanged whole transport.py bytes.
    protected_gazebo: src/so101_gazebo_demo_py git tree 3158e296e2aad5d80dd3e484b87132c85b3832f7 and working-tree diff NONE.
proposal_contract:
  schema: v4 with read-only v1-v3 compatibility and v4-only new output
  dynamic_acceptance_role: diagnostic_only
  approval_enabled: false
  dynamic_acceptance_threshold: ABSENT
  contents: Static formal threshold, metric definitions, five run and waypoint repeated-measure summaries, raw/summary/strategy/provenance hashes, and diagnostic stop metadata.
working_tree_status:
  before_document_edits: tracked files clean at 8f71442
  preserved_untracked_user_files:
    - docs/experiments/so101-gazebo-mujoco-policy-parity-solver-iters-ledger.md
    - docs/experiments/so101-mujoco-ros2-migration-experiment-summary.md
process_state:
  owned_processes: NONE
  ros_domain_0_nodes: []
  preserved_tmux: [codex attached, codex-cua idle historical passive capture, so101-mujoco-gui historical windows]
provenance:
  host: AI-STATION-001
  worktree: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
  branch: codex/so101-mujoco-ros2-teleop
  source_commit_before_docs: 8f71442ae6cff43e0770eec929b13211d2057628
  fork_submodule_commit: f42b7b3d77288c2fee750fe53b0258e0a3d18194
  contact_policy_sha256: c4ba607fea92f7c605fbc8cf08df0dfa3278113c71d1dd6ff10ea402e8186f82
design: docs/superpowers/specs/2026-08-12-so101-mujoco-phase-aware-transport-evidence-design.md
implementation_plan: docs/superpowers/plans/2026-08-12-so101-mujoco-phase-aware-transport-evidence.md
next_experiment_new_information:
  prior: EXP-109 reached transport and proved clean cancellation, but its 100 Hz snapshot path did not persist the aborting physics-step peak and used the static threshold with the wrong phase semantics.
  new: EXP-110..114 will use a fixed instrumentation commit and frozen strategy to produce continuous 500 Hz raw evidence, replayable dynamic metrics, and a disabled diagnostic-only proposal.
next_experiment: NONE_PENDING_DOCUMENT_CHECKPOINT_COMMIT
next_command: Commit only the approved design, implementation plan, ledger checkpoint, frozen manifest, and manifest hash; then preregister EXP-110..114 before RED implementation.
```

## Checkpoint MNT-CP-016 — implementation and five-run preregistration

```yaml
checkpoint_id: MNT-CP-016
recorded_at: 2026-08-12T17:32:00+08:00
last_valid_experiment: EXP-109
current_hypothesis: A plugin-owned per-physics-step queue plus typed transport phase policy can close the EXP-109 evidence gap without changing any frozen behavior input.
document_checkpoint:
  commit: b5c1c23f224e5bef9cd6b7e0a33bd1df8074dbf2
  design: docs/superpowers/specs/2026-08-12-so101-mujoco-phase-aware-transport-evidence-design.md
  implementation_plan: docs/superpowers/plans/2026-08-12-so101-mujoco-phase-aware-transport-evidence.md
  frozen_behavior_manifest: docs/experiments/so101-mujoco-phase-aware-frozen-behavior-manifest.json
  frozen_behavior_manifest_sha256: 912746ac6f6ac6589d5c11d7e9b9483e1ea4ebfeb3f6118a84ee0df48cd54195
implementation_validation_preregistration:
  single_active_change: Measurement, logging, typed force interpretation, validity analysis, durable raw evidence, and disabled proposal generation only.
  predictions:
    - A force spike on an intermediate 500 Hz physics step remains in a continuous chunk even though ordinary snapshots are 100 Hz.
    - Failed trylock publication attempts are counted without discarding queued steps; queue loss/truncation is detectable and invalid.
    - True physics_step and simulation_time remain continuous across chunk boundaries and reset exactly with reset_epoch.
    - PRE_TRANSPORT_STATIC_HOLD remains fail-closed above 1.1579004532160448 N.
    - DYNAMIC_TRANSPORT_SHADOW records the same crossing and does not cancel until global_max_single_contact_force_n >= 11.60 N.
    - The first >=11.60 N latch is immutable and a live cancellation request is recorded within 25 physics steps / 0.050 s; no same-step-stop claim is made.
    - Frozen behavior and protected Gazebo gates remain exactly equal.
  red_before_green: Required for every C++ and Python production boundary.
  live_gate: No stack starts until focused/full tests, Ruff, C++ checks, isolated three-package build/test, installed/runtime provenance, frozen manifest, and protected Gazebo checks all pass.
experiment_state_contract:
  legal_statuses: [PLANNED, RUNNING, VALID, INVALID]
  safety_abort_encoding: {status: VALID, outcome_class: VALID_SAFETY_ABORT}
  batch_stop: A valid safety abort, any other valid physical failure, or any invalid run stops the batch without replacement.
working_tree_status:
  tracked: Only this preregistration plus the status-word clarification in the approved design/plan are dirty after b5c1c23.
  preserved_untracked_user_files:
    - docs/experiments/so101-gazebo-mujoco-policy-parity-solver-iters-ledger.md
    - docs/experiments/so101-mujoco-ros2-migration-experiment-summary.md
owned_processes: NONE
preserved_processes: [tmux codex, idle historical codex-cua, historical so101-mujoco-gui]
ros_domain_0_nodes: []
next_experiment: EXP-110
next_command: Write the C++ physics-step/chunk/latch RED tests without modifying production source.
```

## EXP-110 preregistration — dynamic transport descriptive run 1

```yaml
experiment_id: EXP-110
registered_at: 2026-08-12T17:32:00+08:00
status: INVALID
running_checkpoint_at: 2026-08-12T18:25:15+08:00
terminal_at: 2026-08-12T18:30:38+08:00
outcome_class: INVALID_EVIDENCE
physical_transport_outcome: NOT_EVALUABLE
resolved_runtime_provenance:
  implementation_source_commit: 368abe4d7388a15a9b18ef175b362e584f2812df
  ledger_checkpoint_commit_before_running: b44234c
  install_overlay: /tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-gate-368abe4/install
  install_tree_sha256: d7e73684f99aaa10acb9a9bf64b0b3f13870bcf99dd55328ee5280cddd438dbd
  runtime_fingerprint: /tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-runtime-fingerprint.json
  runtime_fingerprint_sha256: 9a35d05fc4ad97a92757b28e7886e84e0461a7ffbcb908e1df6f55728028fa90
running_preflight:
  ros_domain_187_nodes: []
  port_8027_listeners: []
  gz_partition_processes: []
  evidence_root_absent: true
  tmux_session_absent: true
  project_prefixes_exact: true
  protected_gazebo_zero_diff: true
prior_experiment: EXP-109
hypothesis: The frozen five-win strategy produces a complete replayable dynamic-transport force/compression trace below the unchanged 11.60 N diagnostic hard stop.
prediction: One independent FULL_RESTART reaches the existing physical transport-success outcome; every 2 ms step is continuous and all diagnostic metrics recompute from raw chunks.
single_variable: Independent run identity; all behavior, instrumentation, build, and policy fingerprints are fixed across EXP-110..114.
lifecycle: FULL_RESTART
qualification_counting: false
statistical_role: descriptive_repeat_1_of_4
preconditions:
  - All automatic gates in MNT-CP-016 are green on one committed instrumentation source and isolated install.
  - Domain 187, port 8027, partition so101-mnt-a-phase-exp110, session MNT-A-PHASE-exp110-full-01, evidence root, and owned tmux/process tree are absent before start.
  - Reset returns epoch 1 / true physics_step 0 and the frozen behavior manifest verifies.
success_criteria:
  - Existing physical transport outcome is FORMAL_MOVE_ABOVE_PLACE_PROVED with all five waypoints in order.
  - Raw chunks cover every dynamic physics step with closed typed boundaries, no duplicate/gap/reset crossing/truncation, and replay-identical summary hash.
  - Static threshold crossings during dynamic transport are shadow-only and do not cancel.
  - Clean cancellation ownership, ordered shutdown, empty owned ROS graph/process tree, and fresh visual corroboration are recorded.
valid_safety_abort_criteria:
  - First global tracked-contact maximum >=11.60 N is immutable with step/time/force and complete hashed raw prefix.
  - Cancellation request occurs within 25 physics steps; status becomes VALID with outcome_class VALID_SAFETY_ABORT and the batch stops.
failure_criteria:
  - Any other valid physical transport failure stops the batch and remains in the denominator as a valid outcome.
invalid_criteria:
  - Fingerprint/install/runtime mismatch, missing/duplicate/reversed step, time inconsistency, reset crossing, truncation, evidence loss, unclosed boundary, late/missing hazard response, startup/control pollution, or unclean shutdown.
provenance:
  source_commit_at_preregistration: b5c1c23f224e5bef9cd6b7e0a33bd1df8074dbf2
  required_runtime_source: One common post-TDD descendant commit recorded before RUNNING and unchanged through EXP-114.
  install_overlay: /tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-build/install
  runtime_executable: ros2 run so101_mujoco_demo_py run_qualification from the isolated install prefix
  ros_domain_id: 187
  gz_partition: so101-mnt-a-phase-exp110
  simulation_session_id: MNT-A-PHASE-exp110-full-01
  reset_epoch: 1
commands:
  - command: GZ_PARTITION=so101-mnt-a-phase-exp110 ros2 run so101_mujoco_demo_py run_qualification --batch-id MNT-A-PHASE-EXP110 --lifecycle FULL_RESTART --count 1 --fingerprint /tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-runtime-fingerprint.json --evidence-root /tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-exp110 --base-domain-id 187 --base-port 8027 --no-headless
    exit_code: 1
observed:
  - OBSERVED: Reset advanced epoch 0 to 1; staged approach, static CONTACT_HOLD, MICRO_LIFT, policy lift waypoint 1, and the remaining four lift segments all completed successfully under the frozen strategy.
  - OBSERVED: The transport phase rejected its first received per-physics-step chunk with EvidenceInvalid: chunk simulation session mismatch before any dynamic boundary or waypoint segment was persisted.
  - OBSERVED: The partial raw index is PARTIAL_CLOSED with outcome_class INVALID_EVIDENCE, chunks [], boundaries [], and no hazard or cancellation-latency evidence.
  - OBSERVED: transport.json contains zero segments and no dynamic summary; therefore no dynamic transport outcome or diagnostic distribution is available.
  - OBSERVED: The outer qualification runner generalized the owner exit to status VALID_FAILURE, but the experiment's explicit session-mismatch invalid criterion takes precedence; this is not counted as a valid physical failure.
  - OBSERVED: Ordered shutdown passed with SIGINT, no fatal signal, no SIGTERM/SIGKILL escalation, domain 187 and port 8027 are empty, and no owned runtime process remains.
  - OBSERVED: A fresh mid-run screenshot shows the live MuJoCo scene and arm staged above the cup; the terminal screenshot shows the MuJoCo GUI closed after ordered shutdown. Neither screenshot is claimed as transport success evidence.
inferred:
  - INFERRED: The first bad boundary is the new chunk identity handoff between SimulationEvidencePlugin and DynamicTransportEvidenceObserver, before waypoint 1 ExecuteTrajectory dispatch.
  - NOT_CONFIRMED: The actual mismatching chunk session value was not persisted by the invalid callback, so the exact producer-side cause cannot be proven from the closed artifacts without a separately authorized diagnostic/fix cycle.
conclusion: INVALID. The evidence identity contract failed before dynamic transport sampling; stop EXP-110..114 as one batch and do not replace, retry, or generate a proposal.
evidence:
  - [/tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-exp110/qualification-manifest.json, 34358908f15f4f16c35e695e929e07c5e1938843a32a5c1aeef1182b15a87844]
  - [/tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-exp110/run-01/actions.json, 3e2c324badceb6cbe4344a70e087f0613104fb1174224b557e12bd7475a28906]
  - [/tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-exp110/run-01/launch.log, fbede8e1fceca3c0dd3ad464880c92bac4589011b087783b2a62bbd3af2a3f44]
  - [/tmp/so101-teleop-evidence/MNT-A-PHASE-EXP110-full-01/so101-teleop-workflow-a2652516-37cc-4376-99c7-175a19e463f0/transport.json, e39991ddc717208b987d2f516395add76942602625f134611d3c93244b79a2c7]
  - [/tmp/so101-teleop-evidence/MNT-A-PHASE-EXP110-full-01/so101-teleop-workflow-a2652516-37cc-4376-99c7-175a19e463f0/transport-dynamic-raw/run-index.json, 883543a3d60dd725fbfd6c67ac725229f1fbc85e17562eaf81c048f8609bd652]
  - [/tmp/so101-teleop-evidence/MNT-A-PHASE-EXP110-full-01/so101-teleop-workflow-a2652516-37cc-4376-99c7-175a19e463f0/live-runtime-manifest.json, 1761b931e3357ed27b4fbc973ed5edce6c00244a5bde7bb4221dbbaeaad6e5c6]
  - [/tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-exp110/captures-midrun/20260812T182640-e524cbb74282/desktop.png, b77c925929b7db4e48b6a581ade7163face7d1c9ab268589ecf6c9530b4c123d]
  - [/tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-exp110/captures-terminal/20260812T182754-f9b2f90de6ba/desktop.png, e5b72ef7aea99f872135ea74b85e09ad67adbcbcdc7a75f2261b245fb084720e]
decision: ABANDON_BATCH
next_experiment: NONE_BATCH_STOPPED_EXP110_INVALID
```

## EXP-111 preregistration — dynamic transport descriptive run 2

```yaml
experiment_id: EXP-111
registered_at: 2026-08-12T17:32:00+08:00
status: PLANNED
prior_experiment: EXP-110
hypothesis: A second independent FULL_RESTART reproduces complete diagnostic evidence and the existing transport-success contract under the identical frozen build.
prediction: Results remain replayable without treating waypoint rows as independent experiments or using their values as acceptance bounds.
single_variable: Independent run identity only.
lifecycle: FULL_RESTART
qualification_counting: false
statistical_role: descriptive_repeat_2_of_4
preconditions:
  - EXP-110 is VALID with outcome_class PHYSICAL_TRANSPORT_SUCCESS.
  - Identical source/install/policy/manifest fingerprints; domain 188, port 8028, partition, session, evidence root, and owned process tree are absent before start.
success_criteria:
  - Existing five-waypoint physical transport outcome succeeds; continuous raw evidence and replay-identical summary are complete.
  - Dynamic static-threshold crossings remain shadow-only; ordered shutdown and cleanup pass.
valid_safety_abort_criteria:
  - First >=11.60 N latch and cancellation request within 25 physics steps are complete; status VALID/outcome_class VALID_SAFETY_ABORT stops the batch.
failure_criteria: Any other valid physical failure stops the batch.
invalid_criteria: Any provenance, step/time/reset, truncation/loss, boundary, hazard-latency, startup/control, artifact, or cleanup invalidity stops the batch.
provenance:
  source_commit_at_preregistration: b5c1c23f224e5bef9cd6b7e0a33bd1df8074dbf2
  required_runtime_source: Exactly the EXP-110 source/install/fingerprint.
  install_overlay: /tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-build/install
  runtime_executable: ros2 run so101_mujoco_demo_py run_qualification from the isolated install prefix
  ros_domain_id: 188
  gz_partition: so101-mnt-a-phase-exp111
  simulation_session_id: MNT-A-PHASE-exp111-full-01
  reset_epoch: 1
commands:
  - command: GZ_PARTITION=so101-mnt-a-phase-exp111 ros2 run so101_mujoco_demo_py run_qualification --batch-id MNT-A-PHASE-EXP111 --lifecycle FULL_RESTART --count 1 --fingerprint /tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-runtime-fingerprint.json --evidence-root /tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-exp111 --base-domain-id 188 --base-port 8028 --no-headless
    exit_code: PENDING
observed: [NONE_BEFORE_RUN]
inferred: [NONE]
conclusion: PENDING
evidence: [/tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-exp111]
decision: PENDING
next_experiment: EXP-112_ON_SUCCESS_ONLY
```

## EXP-112 preregistration — dynamic transport descriptive run 3

```yaml
experiment_id: EXP-112
registered_at: 2026-08-12T17:32:00+08:00
status: PLANNED
prior_experiment: EXP-111
hypothesis: A third independent FULL_RESTART reproduces the same frozen physical contract with continuous diagnostic evidence.
prediction: The run succeeds physically and remains replayable; dynamic values are descriptive only.
single_variable: Independent run identity only.
lifecycle: FULL_RESTART
qualification_counting: false
statistical_role: descriptive_repeat_3_of_4
preconditions:
  - EXP-110 and EXP-111 are VALID physical transport successes.
  - Identical source/install/policy/manifest fingerprints; domain 189, port 8029, partition, session, evidence root, and owned process tree are absent.
success_criteria:
  - Five-waypoint physical transport success, continuous raw chunks, replay-identical summary, shadow-only static crossings, ordered shutdown, and cleanup.
valid_safety_abort_criteria:
  - Immutable first >=11.60 N latch, complete hashed prefix, and cancellation request within 25 steps; status VALID/outcome_class VALID_SAFETY_ABORT stops the batch.
failure_criteria: Any other valid physical failure stops the batch.
invalid_criteria: Any provenance, step/time/reset, truncation/loss, boundary, hazard-latency, startup/control, artifact, or cleanup invalidity stops the batch.
provenance:
  source_commit_at_preregistration: b5c1c23f224e5bef9cd6b7e0a33bd1df8074dbf2
  required_runtime_source: Exactly the EXP-110 source/install/fingerprint.
  install_overlay: /tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-build/install
  runtime_executable: ros2 run so101_mujoco_demo_py run_qualification from the isolated install prefix
  ros_domain_id: 189
  gz_partition: so101-mnt-a-phase-exp112
  simulation_session_id: MNT-A-PHASE-exp112-full-01
  reset_epoch: 1
commands:
  - command: GZ_PARTITION=so101-mnt-a-phase-exp112 ros2 run so101_mujoco_demo_py run_qualification --batch-id MNT-A-PHASE-EXP112 --lifecycle FULL_RESTART --count 1 --fingerprint /tmp/so101-debug-mujoco-maintability-remediation/phase-aware-runtime-fingerprint.json --evidence-root /tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-exp112 --base-domain-id 189 --base-port 8029 --no-headless
    exit_code: PENDING
observed: [NONE_BEFORE_RUN]
inferred: [NONE]
conclusion: PENDING
evidence: [/tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-exp112]
decision: PENDING
next_experiment: EXP-113_ON_SUCCESS_ONLY
```

## EXP-113 preregistration — dynamic transport descriptive run 4

```yaml
experiment_id: EXP-113
registered_at: 2026-08-12T17:32:00+08:00
status: PLANNED
prior_experiment: EXP-112
hypothesis: A fourth independent FULL_RESTART completes the descriptive repeat set without changing or fitting the dynamic contract.
prediction: The run succeeds physically and all raw/summary hashes remain independently replayable.
single_variable: Independent run identity only.
lifecycle: FULL_RESTART
qualification_counting: false
statistical_role: descriptive_repeat_4_of_4
preconditions:
  - EXP-110..112 are VALID physical transport successes.
  - Identical source/install/policy/manifest fingerprints; domain 190, port 8030, partition, session, evidence root, and owned process tree are absent.
success_criteria:
  - Five-waypoint physical transport success, continuous raw chunks, replay-identical summary, shadow-only static crossings, ordered shutdown, and cleanup.
valid_safety_abort_criteria:
  - Immutable first >=11.60 N latch, complete hashed prefix, and cancellation request within 25 steps; status VALID/outcome_class VALID_SAFETY_ABORT stops the batch.
failure_criteria: Any other valid physical failure stops the batch.
invalid_criteria: Any provenance, step/time/reset, truncation/loss, boundary, hazard-latency, startup/control, artifact, or cleanup invalidity stops the batch.
provenance:
  source_commit_at_preregistration: b5c1c23f224e5bef9cd6b7e0a33bd1df8074dbf2
  required_runtime_source: Exactly the EXP-110 source/install/fingerprint.
  install_overlay: /tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-build/install
  runtime_executable: ros2 run so101_mujoco_demo_py run_qualification from the isolated install prefix
  ros_domain_id: 190
  gz_partition: so101-mnt-a-phase-exp113
  simulation_session_id: MNT-A-PHASE-exp113-full-01
  reset_epoch: 1
commands:
  - command: GZ_PARTITION=so101-mnt-a-phase-exp113 ros2 run so101_mujoco_demo_py run_qualification --batch-id MNT-A-PHASE-EXP113 --lifecycle FULL_RESTART --count 1 --fingerprint /tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-runtime-fingerprint.json --evidence-root /tmp/so101-debug-mujoco-maintability-remediation/phase-aware-exp113 --base-domain-id 190 --base-port 8030 --no-headless
    exit_code: PENDING
observed: [NONE_BEFORE_RUN]
inferred: [NONE]
conclusion: PENDING
evidence: [/tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-exp113]
decision: PENDING
next_experiment: EXP-114_ON_SUCCESS_ONLY
```

## EXP-114 preregistration — dynamic transport independent replication

```yaml
experiment_id: EXP-114
registered_at: 2026-08-12T17:32:00+08:00
status: PLANNED
prior_experiment: EXP-113
hypothesis: A fifth independent FULL_RESTART replicates evidence completeness, the unchanged physical transport-success contract, and deterministic metric recomputation without using the first four runs as fitted limits.
prediction: The run satisfies the preregistered integrity and physical contract; its dynamic metric values remain diagnostic-only regardless of empirical range.
single_variable: Independent run identity only.
lifecycle: FULL_RESTART
qualification_counting: false
statistical_role: preregistered_replication_not_holdout
preconditions:
  - EXP-110..113 are four VALID physical transport successes under one unchanged source/install/fingerprint.
  - No dynamic threshold or empirical pass range has been generated from the first four runs.
  - Domain 191, port 8031, partition, session, evidence root, and owned process tree are absent.
success_criteria:
  - Frozen behavior manifest, complete per-step evidence, existing five-waypoint physical transport success, deterministic recomputation, ordered shutdown, cleanup, and fresh visual evidence pass.
  - Dynamic metrics are recorded without comparing them to a learned range.
valid_safety_abort_criteria:
  - Immutable first >=11.60 N latch, complete hashed prefix, and cancellation request within 25 steps; status VALID/outcome_class VALID_SAFETY_ABORT stops before proposal generation.
failure_criteria: Any other valid physical failure stops before proposal generation.
invalid_criteria: Any provenance, step/time/reset, truncation/loss, boundary, hazard-latency, startup/control, artifact, or cleanup invalidity stops before proposal generation.
provenance:
  source_commit_at_preregistration: b5c1c23f224e5bef9cd6b7e0a33bd1df8074dbf2
  required_runtime_source: Exactly the EXP-110 source/install/fingerprint.
  install_overlay: /tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-build/install
  runtime_executable: ros2 run so101_mujoco_demo_py run_qualification from the isolated install prefix
  ros_domain_id: 191
  gz_partition: so101-mnt-a-phase-exp114
  simulation_session_id: MNT-A-PHASE-exp114-full-01
  reset_epoch: 1
commands:
  - command: GZ_PARTITION=so101-mnt-a-phase-exp114 ros2 run so101_mujoco_demo_py run_qualification --batch-id MNT-A-PHASE-EXP114 --lifecycle FULL_RESTART --count 1 --fingerprint /tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-runtime-fingerprint.json --evidence-root /tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-exp114 --base-domain-id 191 --base-port 8031 --no-headless
    exit_code: PENDING
observed: [NONE_BEFORE_RUN]
inferred: [NONE]
conclusion: PENDING
evidence: [/tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-exp114]
decision: PENDING
next_experiment: NONE_GENERATE_DISABLED_PROPOSAL_ON_SUCCESS_ONLY
```

## Checkpoint MNT-CP-017 — automatic live-sampling gates green

```yaml
checkpoint_id: MNT-CP-017
recorded_at: 2026-08-12T18:23:17+08:00
last_valid_experiment: EXP-109
current_hypothesis: The committed per-step evidence path can record the frozen strategy's dynamic transport without gaps and without changing its physical behavior.
implementation_source_commit: 368abe4d7388a15a9b18ef175b362e584f2812df
implementation_commits:
  physics_step_plugin: cb7381c
  raw_store_and_analyzer: 3acb85c
  typed_phase_and_cancel_measurement: 49020bb
  schema_v4_proposal: 3a4ce93
  targeted_cpp_style: 368abe4
automatic_gates:
  python_package:
    result: PASS
    tests: 526 passed, 4 skipped
    ruff_check: PASS
    ruff_format_check: PASS; 128 files already formatted
  proposal_and_legacy_focused: PASS; 48 tests
  frozen_verifier_tests: PASS; 3 tests
  cpp_changed_scope:
    ament_uncrustify: PASS; read-only check only
    ament_cpplint: PASS
    ament_lint_cmake: PASS
    support_gtests: PASS; 17 gtests in the isolated final report
  cpp_full_tree_baseline_exception:
    path: src/so101_mujoco_support/src/so101_move_group.cpp
    observation: The whole-directory uncrustify check reports pre-existing broad style divergence in this file.
    disposition: Outside the instrumentation allowlist and frozen behavior scope; deliberately unchanged. All changed C++ files pass the read-only format gate.
  isolated_three_package_build:
    result: PASS; 3 packages finished
    packages: [so101_teleop, so101_mujoco_support, so101_mujoco_demo_py]
    root: /tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-gate-368abe4
    build_log_sha256: ddd8cf0bc12edad6ffce29393016eca2061fe6c4c6e27a00b5ee6ca07d849bbf
    test_result: PASS; 785 tests, 0 errors, 0 failures, 4 skipped
    test_log_sha256: 4c8c7f83a8d399bfd38089cc49a4a15f26c59de5a10062fdae128aa1fd5333f4
    install_tree_sha256: d7e73684f99aaa10acb9a9bf64b0b3f13870bcf99dd55328ee5280cddd438dbd
    install_overlay: /tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-gate-368abe4/install
  installed_runtime:
    project_prefixes_exact: true
    so101_teleop: /tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-gate-368abe4/install/so101_teleop
    so101_mujoco_support: /tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-gate-368abe4/install/so101_mujoco_support
    so101_mujoco_demo_py: /tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-gate-368abe4/install/so101_mujoco_demo_py
    fork_overlay: /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install
    fork_commit: f42b7b3d77288c2fee750fe53b0258e0a3d18194
    mujoco_runtime_check: PASS
    reset_qualified_runtime_check: PASS
  frozen_behavior:
    manifest_sha256: 912746ac6f6ac6589d5c11d7e9b9483e1ea4ebfeb3f6118a84ee0df48cd54195
    instrumentation_diff_gate: MATCH
    transport_semantics: MATCH
    protected_gazebo_tree: MATCH; tree 3158e296e2aad5d80dd3e484b87132c85b3832f7 and zero worktree diff
working_tree_status:
  tracked: Clean at implementation source commit 368abe4 before this ledger checkpoint.
  preserved_untracked_user_files:
    - docs/experiments/so101-gazebo-mujoco-policy-parity-solver-iters-ledger.md
    - docs/experiments/so101-mujoco-ros2-migration-experiment-summary.md
runtime_preflight:
  host: AI-STATION-001; direct local execution, no SSH
  owned_processes: NONE
  ros_domain_0_nodes: []
  preserved_tmux: [codex attached, codex-cua idle historical, so101-mujoco-gui historical]
confirmed_conclusions:
  - OBSERVED: Every automatic gate required by Task 7 passed on one committed instrumentation source and one clean isolated three-package overlay.
  - OBSERVED: Frozen behavior, typed transport call semantics, and the protected Gazebo source remain equal to the registered baseline.
  - OBSERVED: No task-owned runtime or ROS graph is active before EXP-110.
open_risks:
  - Live physics-step continuity, cancellation latency, physical transport outcome, and fresh visual corroboration remain unproved until EXP-110.
next_experiment: EXP-110
next_command: Create and hash the fixed runtime fingerprint, then record EXP-110 RUNNING before its registered FULL_RESTART command.
```

## Checkpoint MNT-CP-018 — EXP-110 RUNNING dispatch boundary

```yaml
checkpoint_id: MNT-CP-018
recorded_at: 2026-08-12T18:25:15+08:00
last_valid_experiment: EXP-109
current_experiment: EXP-110
current_status: RUNNING
behavior_source_commit: 368abe4d7388a15a9b18ef175b362e584f2812df
install_overlay: /tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-gate-368abe4/install
runtime_fingerprint_sha256: 9a35d05fc4ad97a92757b28e7886e84e0461a7ffbcb908e1df6f55728028fa90
preflight: Domain 187, port 8027, partition/session process selectors, evidence root, and owned tmux session are all empty or absent; all three package prefixes resolve to the isolated install.
working_tree_status: Only the two protected untracked user documents plus this ledger update; no strategy, model, scene, geometry, policy, or source change.
owned_processes: NONE before dispatch
preserved_processes: [tmux codex, codex-cua, so101-mujoco-gui]
next_command: GZ_PARTITION=so101-mnt-a-phase-exp110 ros2 run so101_mujoco_demo_py run_qualification --batch-id MNT-A-PHASE-EXP110 --lifecycle FULL_RESTART --count 1 --fingerprint /tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-runtime-fingerprint.json --evidence-root /tmp/so101-debug-mujoco-maintainability-remediation/phase-aware-exp110 --base-domain-id 187 --base-port 8027 --no-headless
```

## Checkpoint MNT-CP-019 — EXP-110 INVALID and batch stopped

```yaml
checkpoint_id: MNT-CP-019
recorded_at: 2026-08-12T18:30:38+08:00
last_valid_experiment: EXP-109
terminal_experiment: EXP-110
terminal_status: INVALID
outcome_class: INVALID_EVIDENCE
first_bad_boundary: The first per-physics-step chunk received by transport failed simulation-session identity before waypoint 1 goal dispatch; zero chunks, typed boundaries, and transport segments were accepted.
physical_result: NOT_EVALUABLE; all pre-transport phases passed, but dynamic transport was never dispatched under a valid evidence stream.
safety:
  diagnostic_hazard_breached: false
  safety_abort: false
  note: No 11.60 N inference is possible because no valid dynamic raw sample was accepted.
shutdown:
  ordered_shutdown_marker: true
  returncode: 0
  signal: SIGINT
  fatal_signal: false
  owned_processes_after: []
  ros_domain_187_nodes_after: []
  port_8027_listeners_after: []
visual:
  midrun: Fresh MuJoCo desktop at step 15920 showed the arm staged above the cup; this corroborates live stack execution only.
  terminal: Fresh desktop after shutdown showed no MuJoCo window, consistent with owned GUI cleanup.
root_cause_status: NOT_CONFIRMED. Session inequality is directly observed, but the invalid callback retained only the reason and not the actual received session value; no producer-side value may be invented.
batch_decision: Stop EXP-110..114. Do not start EXP-111, create replacement runs, generate a schema-v4 proposal, activate policy, enter Project B/C/D or formal regression, run RESET_WORLD challenge, merge, or push.
working_tree_status: Tracked source unchanged from the tested implementation; only this ledger terminal update is dirty. The two protected user documents remain untracked and untouched.
owned_processes: NONE
preserved_processes: [tmux codex, codex-cua, so101-mujoco-gui]
open_risks:
  - The chunk producer/observer session-identity handoff lacks a live integration proof and currently omits actual-versus-expected identity from durable invalid evidence.
  - A corrected implementation would require a new RED-GREEN gate and a newly preregistered five-run batch; EXP-110 cannot be relabeled or rerun.
next_experiment: NONE_BATCH_STOPPED_EXP110_INVALID
next_command: Wait for explicit user direction before any code change or new experiment batch.
```

## Checkpoint MNT-CP-020 — authorized evidence-chain unblock

```yaml
checkpoint_id: MNT-CP-020
recorded_at: 2026-08-12T18:36:00+08:00
last_valid_experiment: EXP-109
immutable_experiment_history:
  EXP-110: Permanently INVALID_EVIDENCE; never rerun or reclassified.
  EXP-111_through_EXP-114: Unexecuted members of the abandoned batch; identifiers will never be reused.
authorization:
  scope: Directly execute a new RED-GREEN evidence-chain diagnosis and repair cycle, then EXP-115 identity-plumbing FULL_RESTART diagnostic, then only on success preregister EXP-116..120 and generate a disabled exact-hash schema-v4 proposal.
  design_reapproval_required: false
  root_cause_status: HYPOTHESIS_ONLY until RED evidence proves parameter resolution and excludes duplicate/old publishers or split snapshot/chunk producers.
  exact_stop: After a byte-identical twice-generated proposal, record its SHA-256 and stop at USER_APPROVAL_REQUIRED.
frozen_behavior:
  strategy: Fixed q6, all waypoints, velocities, acceleration, planner, MJCF, scene, geometry, controller, contact/grasp phase logic, phase-aware thresholds, and normal execution semantics remain unchanged.
  frozen_manifest_sha256: 912746ac6f6ac6589d5c11d7e9b9483e1ea4ebfeb3f6118a84ee0df48cd54195
  prior_runtime_fingerprint_sha256: 9a35d05fc4ad97a92757b28e7886e84e0461a7ffbcb908e1df6f55728028fa90
  protected_gazebo: src/so101_gazebo_demo_py must remain zero diff.
  forbidden_fix: Removing, weakening, or bypassing session equality is prohibited.
required_red_evidence:
  - Characterize fully-qualified parameter resolution for SimulationEvidencePlugin initialized through get_node()->create_sub_node(plugin_name).
  - Persist structured expected_session_id, actual_session_id, topic, and message_kind when DynamicTransportEvidenceObserver rejects a mismatch.
  - Prove ordinary SimulationEvidence and PhysicsStepEvidenceChunk have the same configured session source and identify publisher count/GID so duplicate or stale producers are excluded.
required_green_boundary:
  - Pass the runtime simulation_session_id explicitly into the exact plugin scope or make the plugin resolve one deterministic fully-qualified parameter without hard-coded run IDs or silent fallback.
  - Empty or unconfigured session must fail fast/unhealthy and must not publish acceptable evidence.
  - Focused/full tests, Ruff, C++ read-only style, clean isolated three-package build/test, installed provenance, frozen behavior, and protected Gazebo gates precede EXP-115.
working_tree_status:
  head: d68aaca8537b7fdf087580d8c7029ebd4bd7c43d
  tracked: Clean before this ledger checkpoint.
  preserved_untracked_user_files:
    - docs/experiments/so101-gazebo-mujoco-policy-parity-solver-iters-ledger.md
    - docs/experiments/so101-mujoco-ros2-migration-experiment-summary.md
runtime_state:
  host: AI-STATION-001; direct local execution, no SSH
  fork_commit: f42b7b3d77288c2fee750fe53b0258e0a3d18194
  owned_processes: NONE
  ros_domain_0_nodes: []
  preserved_tmux: [codex attached, codex-cua idle historical, so101-mujoco-gui historical]
next_experiment_new_information:
  prior: EXP-110 retained only a generic chunk session mismatch and could not distinguish plugin parameter fallback from duplicate/stale publisher or split producer identity.
  new: RED characterization will expose exact parameter scope plus structured actual/expected identity and publisher provenance before any live experiment.
next_experiment: NONE_PENDING_RED_DIAGNOSIS
next_command: Write and run the minimum failing launch/plugin parameter-resolution and structured mismatch persistence tests.
```

## Checkpoint MNT-CP-021 — evidence identity RED diagnosis

```yaml
checkpoint_id: MNT-CP-021
recorded_at: 2026-08-12T19:02:11+08:00
last_valid_experiment: EXP-109
immutable_invalid_experiment: EXP-110 INVALID_EVIDENCE; not rerun or reclassified
abandoned_unexecuted_ids: [EXP-111, EXP-112, EXP-113, EXP-114]
phase: RED_DIAGNOSIS_COMPLETE
red_results:
  structured_mismatch_persistence:
    status: RED
    observed: DynamicTransportEvidenceObserver strictly rejects the wrong chunk session, but AtomicTransportEvidenceStore does not persist expected_session_id, actual_session_id, topic, or message_kind.
  publisher_provenance:
    status: RED
    observed: No helper exists to persist publisher count, node name/namespace, and endpoint GID for the ordinary snapshot and physics-step chunk topics.
  launch_binding:
    status: RED
    observed: so101_pick_place.launch.py has no single helper that binds the runtime session at both the root parameter name and the plugin subnode typed-lookup name.
  unconfigured_session:
    status: RED
    observed: With otherwise valid plugin parameters and no session override, SimulationEvidencePlugin::init accepts the literal fallback unconfigured-session.
parameter_resolution_facts:
  upstream_call: MujocoSystemInterface passes get_node()->create_sub_node("simulation_evidence") to the plugin.
  typed_subnode_lookup: get_parameter("simulation_session_id", value) expands to simulation_evidence/simulation_session_id; a dotted simulation_evidence.simulation_session_id override does not satisfy it.
  actual_plugin_helper_lookup: The current helper calls has_parameter(name) and the non-template get_parameter(name); on the subnode this reads the root simulation_session_id rather than the typed slash-scoped parameter.
  hypothesis_disposition: The strongest initial hypothesis is only partially supported. Subnode lookup overloads do differ, but the current plugin helper reads root scope. Therefore parameter scope alone is not yet a confirmed cause of EXP-110; duplicate/stale publishers, runtime provenance, and the actual received identity remain open until EXP-115.
producer_code_facts:
  ordinary_snapshot: SimulationEvidencePlugin/EvidenceBuilder publishes /so101/simulation/evidence from EvidenceState.simulation_session_id.
  physics_chunk: The same plugin and EvidenceState build each PhysicsStepEvidence; PhysicsStepEvidenceBuffer copies the first sample session into the chunk header.
  split_producer_status: No split producer exists in source, but live publisher count and GIDs were not captured in EXP-110 and must be proved in EXP-115.
test_environment_note: The first aggregate CTest invocation omitted sourcing the just-built install and therefore produced unrelated missing-typesupport failures. Re-running the focused binaries with the isolated install sourced left the parameter-scope characterization green and the unconfigured-session acceptance as the intended RED. Those environment-induced failures are not product findings.
frozen_behavior: No production behavior, strategy, MJCF, scene, geometry, controller, waypoint, q6, speed, or threshold was changed during RED.
protected_documents: Both unrelated untracked documents remain untouched and untracked.
next_experiment: NONE_UNTIL_GREEN_GATES
next_command: Commit the RED diagnosis checkpoint and tests, then implement the minimum fail-fast session source, explicit launch binding, structured mismatch persistence, and publisher provenance without changing motion semantics.
```

## Checkpoint MNT-CP-022 — parameter-scope review correction

```yaml
checkpoint_id: MNT-CP-022
recorded_at: 2026-08-12T19:08:00+08:00
last_valid_experiment: EXP-109
immutable_invalid_experiment: EXP-110 INVALID_EVIDENCE; not rerun or reclassified
review_correction:
  authoritative_fact: The production parameter<T>() helper uses has_parameter(name) followed by the non-template get_parameter(name).get_value<T>(). The characterization probe proves this path reads the existing root simulation_session_id from the plugin subnode.
  consequence: Do not add a simulation_evidence slash-scoped override, do not change launch parameter scope, and do not call scope mismatch the confirmed EXP-110 root cause.
  characterization_only: The typed get_parameter(name, value) overload expands through the subnode slash namespace, but production does not use that overload for session initialization.
withdrawn_red_targets:
  - A launch helper that duplicates root and slash-scoped session parameters.
  - A production check that requires or compares a slash-scoped session.
  - Treating the existing placeholder fallback as the cause of EXP-110 without live producer evidence.
green_scope:
  - Preserve strict session equality rejection.
  - Persist durable expected_session_id, actual_session_id, topic, and message_kind on identity mismatch.
  - Persist publisher count, node name/namespace, and endpoint GID for both ordinary SimulationEvidence and PhysicsStepEvidenceChunk.
  - Trace and record the observer expected SESSION_ID, actual first snapshot/chunk sessions, and the shared message-construction path.
  - Use EXP-115 to locate the live cause before any parameter-binding fix.
production_revert: The uncommitted slash-scoped launch/session source changes were fully removed before validation or commit.
frozen_behavior: Strategy, motion parameters, models, controller, contact/grasp phases, and protected Gazebo source remain unchanged.
next_experiment: NONE_PENDING_OBSERVABILITY_GREEN
next_command: Remove obsolete launch/fallback RED expectations, implement only durable mismatch and producer provenance, then run the required automatic gates before preregistering EXP-115.
```

## Checkpoint MNT-CP-023 — observability GREEN and automatic gates

```yaml
checkpoint_id: MNT-CP-023
recorded_at: 2026-08-12T19:18:00+08:00
last_valid_experiment: EXP-109
behavior_source_commit: 4f168ec2f15c297d0509f91e4bb88e5983a8ae3d
implementation_commits:
  - cae0b4d: Durable expected/actual/topic/message-kind mismatch evidence, first-value latching, publisher count/GID provenance, and root-scope characterization correction.
  - 4f168ec: Ruff-only formatting of two changed Python files.
green_scope:
  session_equality: Unchanged and strict; no bypass or fallback acceptance was added.
  launch_and_plugin_parameter_source: Unchanged root simulation_session_id binding.
  durable_identity: First snapshot and first chunk sessions plus observer expected session are atomically checkpointed; first mismatch cannot be overwritten.
  publisher_provenance: Ordinary snapshot and physics-step chunk topic publisher count, node name/namespace, and endpoint GID are persisted before motion dispatch.
  message_construction_trace: Source characterization proves ordinary snapshots and chunks originate in one SimulationEvidencePlugin state; live equality remains for EXP-115 to prove.
automatic_gates:
  focused_python: 51 passed, 1 skipped before the package run; after formatting the instrumentation/frozen subset passed 21 tests.
  isolated_build: Three packages built successfully in /tmp/so101-debug-mujoco-maintainability-remediation/session-unblock-gate-cae0b4d/install.
  isolated_tests: 791 tests, 0 errors, 0 failures, 4 skipped.
  ruff: check and format check passed after one RED formatting failure was corrected and the full package suite was rerun.
  cpp_changed_scope: ament_uncrustify read-only, ament_cpplint, and ament_cppcheck passed for SimulationEvidencePlugin header/source and its test.
  cpp_package_baseline: A whole-directory style probe reproduced 35 pre-existing so101_move_group.cpp uncrustify/cpplint findings; that unchanged file is outside this evidence-only repair and was not reformatted.
  frozen_behavior: Manifest SHA-256 912746ac6f6ac6589d5c11d7e9b9483e1ea4ebfeb3f6118a84ee0df48cd54195; transport AST, fixed behavior files, instrumentation allowlist, and protected Gazebo tree all MATCH.
  protected_gazebo: src/so101_gazebo_demo_py has zero diff/status.
  installed_provenance:
    prefixes: All three packages resolve to the isolated gate install.
    dynamic_transport_evidence_sha256: 566c08d7ebcf7585d5d192109fb71cee865ad9c89aa849fdca646e832151a467 source=install.
    transport_observer_sha256: ff90b385296b3fd6318b2ec80a11424727bbf80bf315170afdc555d4af41588b source=install.
    transport_phase_sha256: db306bd47ea368ab4b71fb640158cf352c670a69df84a9c3789c73bc2e62cf9b source=install.
runtime_fingerprint:
  path: /tmp/so101-debug-mujoco-maintainability-remediation/session-unblock-runtime-fingerprint.json
  sha256: edcfa5067a2fe0fcd10d2d49617262b33180a6ea6c403d907bc74db8323e99f1
  validation: qualification.validate_fingerprint passed.
runtime_state: No task-owned stack; Domain 192 empty, port 8032 free, EXP-115 evidence root absent.
protected_documents: The two unrelated untracked documents remain untouched and untracked.
next_experiment: EXP-115
next_command: Execute the preregistered one-run identity diagnostic harness under the isolated install and stop the full stack at the first persisted transport boundary plus valid chunk.
```

## EXP-115 preregistration — FULL_RESTART evidence-identity plumbing diagnostic

```yaml
experiment_id: EXP-115
prior_experiment: EXP-110 retained permanently as INVALID_EVIDENCE; EXP-111..114 remain abandoned and unexecuted.
status: PLANNED
purpose: Prove live snapshot/chunk session identity and publisher provenance only; do not evaluate or tune the grasp/transport strategy.
lifecycle: FULL_RESTART
behavior_source_commit: 4f168ec2f15c297d0509f91e4bb88e5983a8ae3d
install_overlay: /tmp/so101-debug-mujoco-maintainability-remediation/session-unblock-gate-cae0b4d/install
runtime_fingerprint_sha256: edcfa5067a2fe0fcd10d2d49617262b33180a6ea6c403d907bc74db8323e99f1
frozen_behavior_manifest_sha256: 912746ac6f6ac6589d5c11d7e9b9483e1ea4ebfeb3f6118a84ee0df48cd54195
harness:
  path: /tmp/so101-debug-mujoco-maintainability-remediation/run_exp115_identity_diagnostic.py
  sha256: 1a92e6d5aec564f846d8e722909e32ebdcdc45b1eda9637a60830a0718673c95
runtime_identity:
  session: MNT-A-EXP115-full-01
  ros_domain_id: 192
  port: 8032
  gz_partition: so101-mnt-a-exp115
  evidence_root: /tmp/so101-debug-mujoco-maintainability-remediation/exp115
single_variable: Evidence observability added at behavior source 4f168ec; root session parameter binding, strategy, model, controller, thresholds, and execution inputs remain unchanged.
procedure:
  - Start exactly one fresh non-headless stack from the isolated overlay and perform the transactional reset.
  - Capture one fresh local desktop image only as live-stack corroboration; it is not an acceptance signal.
  - Start the unchanged production workflow.
  - Poll the atomically checkpointed raw index; at the first persisted transport boundary and first accepted physics-step chunk, request ordered whole-stack SIGINT shutdown immediately.
  - If identity_mismatch appears or the workflow ends before that boundary, stop without continuing or substituting another run.
acceptance:
  - Exactly one publisher exists on /so101/simulation/evidence and /so101/simulation/physics_step_chunks; both node identity and endpoint GID lists are persisted.
  - observer expected session, first ordinary snapshot session, and first chunk session all equal MNT-A-EXP115-full-01.
  - Raw store contains at least one content-addressed valid chunk and the first typed transport boundary; no identity_mismatch or evidence-loss marker exists.
  - Reset receipt uses the preregistered session and a fresh epoch; source/install/runtime fingerprint matches this preregistration.
  - Ordered shutdown marker is present, return code is zero, no fatal signal/process-died marker occurs, and owned processes/domain/port are empty afterward.
  - Visual evidence only corroborates that the fresh stack was alive.
failure_policy: Any failed condition makes EXP-115 INVALID_EVIDENCE, stops all further experiment work, preserves actual/expected/topic/GID/raw evidence, and forbids EXP-116..120.
command: GZ_PARTITION=so101-mnt-a-exp115 python3 /tmp/so101-debug-mujoco-maintainability-remediation/run_exp115_identity_diagnostic.py
next_if_valid: Preregister EXP-116..120 as new independent FULL_RESTART runs under the exact same behavior/install/fingerprint.
```

## Checkpoint MNT-CP-024 — EXP-115 RUNNING dispatch boundary

```yaml
checkpoint_id: MNT-CP-024
recorded_at: 2026-08-12T19:19:49+08:00
last_valid_experiment: EXP-109
current_experiment: EXP-115
current_status: RUNNING
behavior_source_commit: 4f168ec2f15c297d0509f91e4bb88e5983a8ae3d
ledger_head_before_dispatch: ddf5feb
install_overlay: /tmp/so101-debug-mujoco-maintainability-remediation/session-unblock-gate-cae0b4d/install
runtime_fingerprint_sha256: edcfa5067a2fe0fcd10d2d49617262b33180a6ea6c403d907bc74db8323e99f1
harness_sha256: 1a92e6d5aec564f846d8e722909e32ebdcdc45b1eda9637a60830a0718673c95
preflight: EXP-115 evidence root absent; ROS Domain 192 empty; port 8032 free; no task-owned stack exists.
working_tree_status: Only the two protected unrelated untracked documents; no tracked change and no protected Gazebo change.
stop_boundary: First atomically persisted typed transport boundary plus first accepted physics-step chunk, or any earlier identity/evidence failure.
next_command: GZ_PARTITION=so101-mnt-a-exp115 python3 /tmp/so101-debug-mujoco-maintainability-remediation/run_exp115_identity_diagnostic.py
```

## Checkpoint MNT-CP-025 — EXP-115 terminal INVALID_EVIDENCE

```yaml
checkpoint_id: MNT-CP-025
recorded_at: 2026-08-12T19:23:00+08:00
last_valid_experiment: EXP-109
terminal_experiment: EXP-115
terminal_status: INVALID_EVIDENCE
rerun_policy: EXP-115 is immutable and will not be rerun or reclassified.
stop_reason: IDENTITY_MISMATCH before any transport boundary or accepted physics-step chunk.
identity:
  expected_session_id: MNT-A-EXP115-full-01
  first_snapshot_session_id: MNT-A-EXP115-full-01
  first_chunk_session_id: ""
  mismatch_topic: /so101/simulation/physics_step_chunks
  mismatch_message_kind: PhysicsStepEvidenceChunk
publisher_provenance:
  snapshot:
    count: 1
    node: /mujoco_ros2_control_node
    endpoint_gid: 010ff4e9f6b2d1990000000000005903
  physics_step_chunk:
    count: 1
    node: /mujoco_ros2_control_node
    endpoint_gid: 010ff4e9f6b2d1990000000000005a03
  conclusion: Duplicate, stale, and split-node publisher explanations are excluded for this run. Distinct GIDs are the expected distinct publisher endpoints on two topics from one node.
parameter_scope_conclusion: Root simulation_session_id binding is live and correct for ordinary snapshots; EXP-115 disproves parameter scope as the common producer-session root cause.
message_path_conclusion: Source shows build_step copies EvidenceState session into PhysicsStepEvidence and prepare_chunk copies the first sample session into the chunk header, yet the received chunk header is empty. The next RED must reproduce and characterize the empty/loss-sentinel chunk path before changing code.
raw_evidence:
  index: /tmp/so101-teleop-evidence/MNT-A-EXP115-full-01/so101-teleop-workflow-65d59393-7a90-4990-8649-8d5c8e0d8b55/transport-dynamic-raw/run-index.json
  index_sha256: 8ad2c1b4dba4afbc5d39039a7e72e905dfb782b0e79d4471b062f2c100f9d361
  chunks: 0
  boundaries: 0
  identity_mismatch_persisted: true
experiment_artifacts:
  diagnostic_sha256: f092c95699dfb81a2e42f6734f6b22365146a9b6012a5b980245af3c334d4af7
  launch_log_sha256: 02e13a2ce2daef05b8f1f6611dbd6f64683ad8d6e738c08d51769f986869135e
  screenshot_manifest_sha256: c32f50c80e4aa3b32ea361ee21781f135ea713a04daed8fdd90ec1eff672d5c2
  desktop_sha256: e6fb2cb5f8d8cdd18c1c74fe78bf3dafbaf01767a999ecdb674fdaabb55485c4
visual: Fresh desktop capture shows a running MuJoCo so101_task_scene at step 490 with the robot and cup visible; this corroborates a live fresh stack only and is not an acceptance result.
reset: Fresh epoch 1 receipt exactly matched MNT-A-EXP115-full-01.
shutdown:
  ordered_shutdown_marker: true
  returncode: 0
  fatal_signal: false
  process_died_marker: true
  passed: false
  audit: The diagnostic whole-stack SIGINT occurred while the HTTP workflow was still unwinding, so robot_state_publisher and ros2_control_node were logged with SIGINT exit -2. This independently fails EXP-115 clean-shutdown acceptance and must not be hidden.
cleanup:
  owned_processes_after: []
  ros_domain_192_nodes_after: []
  port_8032_listeners_after: []
batch_decision: Do not start EXP-116..120. Continue a new RED-GREEN evidence-path cycle only; no Project B/C/D, formal regression, RESET_WORLD, proposal, merge, or push.
next_experiment: NONE_PENDING_POST_EXP115_RED
next_command: Add RED tests that retain the complete first chunk header and prove whether an empty evidence-loss sentinel loses session identity; then apply only the evidence-path fix justified by those tests.
```

## Checkpoint MNT-CP-026 — post-EXP-115 sentinel RED→GREEN and producer cadence diagnosis

```yaml
checkpoint_id: MNT-CP-026
recorded_at: 2026-08-12T19:29:16+08:00
last_valid_experiment: EXP-109
immutable_invalid_experiments:
  - EXP-110 INVALID_EVIDENCE; never rerun or reclassified.
  - EXP-115 INVALID_EVIDENCE; never rerun or reclassified.
abandoned_ids: EXP-111..114 remain unexecuted and will not be reused; EXP-116..120 were not started.
red_confirmation:
  cpp: PhysicsStepEvidenceBufferTest.EmptyLossSentinelRetainsTheLastObservedIdentity failed because prepare_chunk() returned a default empty session and epoch after mark_published() cleared samples and a later non-contiguous append latched evidence_loss.
  python: The durable mismatch test initially failed because the first received chunk header was not persisted; after adding the header assertion, the only incidental mismatch was the exact binary float representation used by the test fixture.
green_fix:
  producer: An empty evidence-loss sentinel now copies only simulation_session_id and reset_epoch from last_observed_; it does not fabricate a sample, range, or successful evidence.
  observer: The first chunk's complete header is atomically persisted before strict identity/evidence validation.
  strict_semantics: A correctly identified empty loss sentinel is rejected as `chunk evidence loss latched`; a wrong session remains a strict identity mismatch. No session equality check was weakened.
green_evidence:
  python: 2 focused observer tests passed, including the correctly identified empty loss sentinel.
  cpp: The focused empty loss sentinel GTest passed after rebuilding so101_mujoco_support.
live_root_cause_status:
  parameter_scope: DISPROVEN; root session binding produced the correct ordinary snapshot identity in EXP-115.
  empty_session: CONFIRMED as a secondary serialization defect in the evidence-loss sentinel path.
  evidence_loss_cadence: Source diagnosis shows generic plugin update() is invoked from MujocoSystemInterface::read(), i.e. the controller-manager cadence, while authoritative mj_step() executes independently in the physics loop. EvidenceBuilder advances physics_step by elapsed simulation time, so a read spanning multiple 2 ms physics steps creates a non-contiguous append and latches evidence_loss. A physics-step hook is required to meet the approved 500 Hz evidence contract; this must receive its own RED tests before implementation.
frozen_behavior: No q6, waypoint, planner, speed/acceleration, MJCF, scene, geometry, controller command, contact/grasp phase, or protected Gazebo source has changed.
runtime_state: No task-owned processes; no new live experiment is preregistered.
next_experiment: NONE_PENDING_PHYSICS_HOOK_GREEN
next_command: Add RED coverage in the pinned mujoco_ros2_control fork for one read-independent callback after each successful mj_step, then route only diagnostic evidence sampling through that hook while retaining ordinary snapshots at controller cadence.
```

## Checkpoint MNT-CP-027 — fork per-physics-step hook TDD checkpoint

```yaml
checkpoint_id: MNT-CP-027
recorded_at: 2026-08-12T19:40:12+08:00
last_valid_experiment: EXP-109
immutable_invalid_experiments: EXP-110 and EXP-115 remain INVALID_EVIDENCE and are not rerun or reclassified.
fork_before: f42b7b3d77288c2fee750fe53b0258e0a3d18194
fork_after: 738e304551b4ea6db020b466086a13db71b65607
fork_commit: "feat: add per-physics-step plugin hook"
red_evidence:
  interface: SnapshotCountingPlugin could not override on_physics_step because the base API did not exist; MujocoSystemInterface had no notifying entry point.
  path_audit: Source audit failed with three direct mj_step calls and zero uses of a shared notifying wrapper.
source_confirmation:
  controller_path: plugin->update(mj_model_, mj_data_control_) remains in MujocoSystemInterface::read at controller-manager cadence.
  physics_paths:
    - running timing-resynchronization single step
    - running catch-up loop step
    - paused StepSimulation/keyboard single step
  lock: All three paths execute while sim_mutex_ protects authoritative mj_model_/mj_data_.
green_contract:
  - MuJoCoROS2ControlPluginBase adds a source-compatible default no-op on_physics_step hook.
  - One step_authoritative_physics wrapper owns the only direct mj_step call, publishes clock, checks Diverged, and notifies plugins only when the step succeeds.
  - The three original physics paths call that wrapper; other plugins retain their existing controller-cadence update behavior and receive only the default no-op hook unless they opt in.
  - Hook callbacks receive authoritative mj_model_/mj_data_ under sim_mutex_.
verification:
  focused: Hook lock/identity, controller update cadence, and all-path source audit tests passed.
  fork_suite: 133 tests, 0 errors, 0 failures, 0 skipped across the three fork packages.
  diff_check: clean.
  style_audit: Read-only ament_uncrustify reports the fork's broad pre-existing style baseline; no reformat was run, and new lines follow the surrounding fork style.
parent_pointer: Will be committed as a dedicated parent checkpoint before the SimulationEvidencePlugin producer change.
frozen_behavior: No strategy, controller command, model, scene, geometry, waypoint, q6, speed, acceleration, or phase behavior changed.
next_experiment: NONE_PENDING_PROJECT_PLUGIN_GREEN
next_command: Commit the parent submodule pointer, then make SimulationEvidencePlugin the sole opt-in per-step producer while ordinary update remains snapshot-only.
```

## Checkpoint MNT-CP-028 — SimulationEvidencePlugin per-step producer GREEN

```yaml
checkpoint_id: MNT-CP-028
recorded_at: 2026-08-12T19:44:56+08:00
last_valid_experiment: EXP-109
immutable_invalid_experiments: EXP-110 and EXP-115 remain INVALID_EVIDENCE and are not rerun or reclassified.
parent_fork_pointer_commit: e802380
fork_commit: 738e304551b4ea6db020b466086a13db71b65607
red_evidence: The project test did not compile because SimulationEvidencePlugin lacked a dedicated physics_state_ and per-step override; the former update-only producer could not meet the new fork contract.
green_implementation:
  physics_producer: SimulationEvidencePlugin is the only plugin that overrides on_physics_step. It builds, validates, buffers, hazard-checks, and publishes diagnostic chunks from authoritative data after each successful MuJoCo step.
  ordinary_update: Retains the 100 Hz ordinary SimulationEvidence snapshot path only and never appends a PhysicsStepEvidence sample.
  identity: Snapshot state and physics state receive the same immutable simulation_session_id from the existing root-bound production parameter source.
  reset_pause: A successful paused reset snapshot atomically consumes the new generation for both states, clears the physics buffer/hazard latch, establishes step zero at the reset simulation time, and makes the first resumed successful physics hook step one. Publisher contention leaves both states pending and fail-closed.
  threading: Fork calls the physics hook under sim_mutex_ with authoritative mj_data_; controller update and paused snapshot hooks are already under the same mutex. The plugin adds no motion/control writes and no independent lock.
  failure_semantics: Missing/duplicate/backward physics time still latches evidence loss; strict observer session/epoch/gap checks remain unchanged.
verification:
  focused: Three producer/cadence/reset tests passed at explicit timestep 0.002 s.
  support_gtest: 19 SimulationEvidencePlugin tests passed; colcon reports 20 package test cases, 0 errors/failures/skips.
  cxx_style: Changed project files pass read-only ament_uncrustify and ament_cpplint.
  cppcheck: Header/source pass; cppcheck 2.13 cannot parse the GTest TEST_F macro and reports a parser syntaxError at the first unchanged TEST_F declaration, while the test translation unit compiles and all GTests pass.
  diff_check: clean.
protected_gazebo: src/so101_gazebo_demo_py remains clean.
frozen_behavior: No q6, waypoint, trajectory, planner, speed/acceleration, controller command, MJCF, scene, geometry, initial pose, phase order, or normal transport behavior changed.
runtime_state: No live stack or experiment started.
next_experiment: NONE_PENDING_FULL_AUTOMATIC_GATES
next_command: Commit this evidence-only producer change, rebuild the pinned fork overlay, then run clean isolated three-package build/test, Ruff, manifest/protected-tree/provenance gates before preregistering a new diagnostic ID.
```

## Checkpoint MNT-CP-029 — r6 exact-release and automatic-gate checkpoint

```yaml
checkpoint_id: MNT-CP-029
recorded_at: 2026-08-12T19:58:36+08:00
last_valid_experiment: EXP-109
immutable_invalid_experiments:
  - EXP-110 INVALID_EVIDENCE; never rerun or reclassified.
  - EXP-115 INVALID_EVIDENCE; never rerun or reclassified.
reserved_or_abandoned_ids:
  - EXP-111..114 remain abandoned and unexecuted.
  - EXP-116..120 were never started and will not be reused for the replacement diagnostic.
source_checkpoint:
  parent_head: a3d18a59b3ac955aed1cb53d20922ae7ba112709
  fork_commit: 738e304551b4ea6db020b466086a13db71b65607
  fork_release_tag: so101-0.0.3-r6
  tag_type: local annotated tag, matching the existing r1..r5 convention
  exact_release_gate: so101-0.0.3-r6 resolves exactly to locked commit 738e304551b4ea6db020b466086a13db71b65607; no ancestor relaxation remains in installer, runtime probes, or tests.
  publication: Fork commit/tag and parent submodule pointer exist locally only. Neither repository nor tag has been pushed; remote publication requires later explicit user authorization.
automatic_gates:
  fork_suite: 133 tests, 0 errors, 0 failures, 0 skipped at 738e304.
  isolated_build: PASS for so101_mujoco_support, so101_mujoco_demo_py, and so101_teleop under /tmp/so101-debug-mujoco-maintainability-remediation/physics-hook-r6-gate-install.
  isolated_tests: 793 tests, 0 errors, 0 failures, 4 skipped; MuJoCo Python package 532 passed and 4 skipped; SimulationEvidencePlugin 19 GTests passed.
  changed_scope_ruff: PASS for the five changed Python runtime/test files; Ruff 0.15.20 lint and format check both pass.
  whole_teleop_ruff_characterization: A broad src/so101_teleop Ruff probe reports 194 pre-existing legacy findings. The package's checked-in test_ruff_gate and all package tests pass; these unrelated legacy findings are not modified or counted as this evidence-only change.
  provenance: PASS; fork source is clean, exact tag equals locked commit, all fork packages resolve to the persistent fork overlay, all three project packages resolve to the isolated install, and required installed hashes match dependency-lock.yaml.
  frozen_behavior_manifest_sha256: d5b6dbd747192592e5bc2ccf95521c2c665d1045bbfcb2147825c534f353561c
  protected_gazebo: src/so101_gazebo_demo_py has zero diff/status and its registered tree matches.
  strategy_freeze: q6, waypoints, trajectories, planner, speeds/accelerations, controller, MJCF, scene, geometry, phase order, thresholds, and normal execution semantics are unchanged.
diagnostic_lifecycle_gate:
  replacement_experiment: EXP-121 only; FULL_RESTART evidence-plumbing diagnostic, not a policy qualification run.
  required_stop: Use the existing supported workflow cancellation/stop handshake or wait for normal workflow unwind before stack teardown. Never terminate the workflow process directly, never send whole-stack SIGINT while it is unwinding, and never use broad pkill.
  shutdown_order: After workflow terminal/unwind is observed, stop owned stack components in dependency order and verify clean exit, empty owned process set, empty experiment ROS domain, and free HTTP port.
  acceptance_scope: One publisher per evidence topic; snapshot and chunk sessions equal the preregistered session; first chunk has exactly five continuous samples at approximately 0.002 s timestep with no evidence_loss; first typed transport boundary persists; ordered clean shutdown succeeds.
  failure_policy: Any invalid identity, evidence continuity, boundary, provenance, lifecycle, or shutdown condition makes EXP-121 INVALID and stops all work. If EXP-121 is VALID, report its result before any five-run batch.
working_tree_status: Only the two protected unrelated untracked documents; no tracked change before this checkpoint edit.
owned_processes: NONE
protected_documents:
  - docs/experiments/so101-gazebo-mujoco-policy-parity-solver-iters-ledger.md remains untouched/untracked.
  - docs/experiments/so101-mujoco-ros2-migration-experiment-summary.md remains untouched/untracked.
next_experiment: EXP-121_PENDING_PREREGISTRATION
next_command: Commit this checkpoint, generate and validate a runtime fingerprint from that committed HEAD, then preregister EXP-121 before any stack starts.
```

## EXP-121 preregistration — authoritative physics-step evidence diagnostic

```yaml
experiment_id: EXP-121
recorded_at: 2026-08-12T20:11:56+08:00
prior_experiments:
  - EXP-110 and EXP-115 remain permanently INVALID_EVIDENCE and are not rerun or reclassified.
  - EXP-111..114 remain abandoned and unexecuted.
  - EXP-116..120 were never started and are not reused.
status: PLANNED
purpose: Validate authoritative 500 Hz physics-step evidence identity, continuity, publisher provenance, typed boundary persistence, and clean lifecycle only; do not evaluate or tune grasp policy.
lifecycle: FULL_RESTART
behavior_source_commit: 49d498d25d1da345622fb40054036e64942c5fbd
fork_commit: 738e304551b4ea6db020b466086a13db71b65607
fork_release_tag: so101-0.0.3-r6
install_overlay: /tmp/so101-debug-mujoco-maintainability-remediation/physics-hook-r6-gate-install
runtime_fingerprint:
  path: /tmp/so101-debug-mujoco-maintainability-remediation/physics-hook-r6-runtime-fingerprint.json
  sha256: 42dd62ef63c2719944dd96ca25adab2014e16f43880ba2ecd59f21a1ab8dac1f
frozen_behavior_manifest_sha256: d5b6dbd747192592e5bc2ccf95521c2c665d1045bbfcb2147825c534f353561c
harness:
  path: /tmp/so101-debug-mujoco-maintainability-remediation/run_exp121_evidence_diagnostic.py
  sha256: 515bda9df23c7777213adb18d95448a1c798b85473e96b2fbd1b8bd36cb98dfe
  static_checks: py_compile PASS; Ruff lint/format PASS; no terminate(), kill(), or /execution/cancel path.
runtime_identity:
  session: MNT-A-EXP121-full-01
  ros_domain_id: 193
  port: 8033
  gz_partition: so101-mnt-a-exp121
  evidence_root: /tmp/so101-debug-mujoco-maintainability-remediation/exp121
single_variable: PhysicsStepEvidence production moved from the approximately 100 Hz controller read cadence to the fork's authoritative post-mj_step 500 Hz hook. q6, waypoints, trajectories, planner, speeds/accelerations, controller, MJCF, scene, geometry, thresholds, and phase behavior remain frozen.
procedure:
  - Start exactly one fresh non-headless stack from the r6 isolated overlay and perform the existing transactional reset.
  - Start the unchanged production workflow and observe the atomically checkpointed raw index.
  - Record the first persisted typed boundary plus content-addressed physics-step chunk, but send no cancellation or other command to the independent workflow owner.
  - Wait for /workflow/run to return naturally, regardless of business success or failure; only after its HTTP terminal response may ordered stop_stack run.
  - If the workflow does not naturally return within the bounded timeout, mark INVALID_EVIDENCE and preserve the owned stack for manual handling; never terminate/kill the workflow or tear down underneath it.
acceptance:
  - Exactly one publisher exists on /so101/simulation/evidence and /so101/simulation/physics_step_chunks, with publisher identities/GIDs persisted.
  - Expected session, first snapshot session, first chunk session, and all five first-chunk sample sessions equal MNT-A-EXP121-full-01.
  - The first chunk contains exactly five samples, physics_step increases strictly by one, adjacent simulation_time_s differs by approximately 0.002 s, failed_publish_attempts is zero, and evidence_loss is false.
  - At least one typed transport boundary persists; no identity_mismatch or later invalid_reason is recorded.
  - Workflow returns through its HTTP ownership boundary before teardown; ordered shutdown passes with no process-died/fatal-signal marker and no owned process/domain/port residue.
  - Workflow grasp outcome is not an EXP-121 acceptance signal.
failure_policy: Any failed identity, continuity, publisher, boundary, provenance, workflow-unwind, or shutdown condition makes EXP-121 INVALID_EVIDENCE and stops further batch work. EXP-121 is run exactly once.
command: source /opt/ros/jazzy/setup.zsh; source /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install/setup.zsh; source /tmp/so101-debug-mujoco-maintainability-remediation/physics-hook-r6-gate-install/setup.zsh; GZ_PARTITION=so101-mnt-a-exp121 PYTHONPATH=/data/work/ws_moveit/.worktrees/so101-mujoco-ros2/src/so101_mujoco_demo_py python3 /tmp/so101-debug-mujoco-maintainability-remediation/run_exp121_evidence_diagnostic.py
next_if_valid: Stop and report EXP-121 before preregistering any new five-run batch.
```

## Checkpoint MNT-CP-030 — EXP-121 terminal pre-stack INVALID_EVIDENCE

```yaml
checkpoint_id: MNT-CP-030
recorded_at: 2026-08-12T20:17:11+08:00
terminal_experiment: EXP-121
status: INVALID_EVIDENCE
rerun_policy: EXP-121 is immutable and will not be rerun or reclassified.
execution_boundary:
  stack_ready: false
  workflow_started: false
  reset_started: false
  motion_or_strategy_executed: false
failure:
  class: StackStartupError
  message: stack exited during startup with 1
  root_cause: The preregistered shell command overwrote PYTHONPATH with only the project source path. The child /opt/ros/jazzy/bin/ros2 process therefore could not discover the ros2cli distribution metadata and exited before launch.
  launch_error: importlib.metadata.PackageNotFoundError: No package metadata was found for ros2cli
  disposition: This is a diagnostic execution-wrapper defect, not a MuJoCo, ROS-control, evidence-hook, reset, or frozen-policy failure.
evidence:
  result: /tmp/so101-debug-mujoco-maintainability-remediation/exp121/exp121-diagnostic.json
  result_sha256: 90f61229441615fc1865cb1397b2d82a49e635a2b40d5619f08711113b4415d9
  launch_log: /tmp/so101-debug-mujoco-maintainability-remediation/exp121/run-01/launch.log
  launch_log_sha256: 5f2da83e2a9ed5c3c1a43bcbb55c7b09a4aff240fa840aed448d53c92028f3b5
  residue: No EXP-121 process, ROS Domain 193 node, or port 8033 listener remained.
pre_dispatch_tmux_note: The first attempt to create a shell by respawning a dead historical pane inherited that pane's old Task14 /tmp/so101_exp115_run.bash start command. It was stopped by an exact tmux pane Ctrl-C before EXP-121 existed or was dispatched, used none of EXP-121's identity/root/domain/port, and is not classified as an EXP-121 execution. The replacement pane was created with explicit /bin/zsh -l before the actual EXP-121 dispatch.
frozen_behavior: No q6, waypoint, trajectory, planner, speed/acceleration, controller, MJCF, scene, geometry, threshold, or phase behavior changed or ran.
next_experiment: EXP-122_PENDING_PREREGISTRATION
next_command: Remove the PYTHONPATH override, prove ros2cli plus the installed qualification module are both importable after sourcing the exact overlays, then preregister a new diagnostic ID and run it once.
```

## EXP-122 preregistration — corrected authoritative physics-step evidence diagnostic

```yaml
experiment_id: EXP-122
recorded_at: 2026-08-12T20:17:11+08:00
prior_experiment: EXP-121 remains permanently INVALID_EVIDENCE and is not rerun or reclassified.
status: PLANNED
purpose: Validate authoritative 500 Hz physics-step evidence identity, continuity, publisher provenance, typed boundary persistence, and clean lifecycle only; do not evaluate or tune grasp policy.
lifecycle: FULL_RESTART
behavior_source_commit: 49d498d25d1da345622fb40054036e64942c5fbd
fork_commit: 738e304551b4ea6db020b466086a13db71b65607
fork_release_tag: so101-0.0.3-r6
install_overlay: /tmp/so101-debug-mujoco-maintainability-remediation/physics-hook-r6-gate-install
runtime_fingerprint:
  path: /tmp/so101-debug-mujoco-maintainability-remediation/physics-hook-r6-runtime-fingerprint.json
  sha256: 42dd62ef63c2719944dd96ca25adab2014e16f43880ba2ecd59f21a1ab8dac1f
frozen_behavior_manifest_sha256: d5b6dbd747192592e5bc2ccf95521c2c665d1045bbfcb2147825c534f353561c
harness:
  path: /tmp/so101-debug-mujoco-maintainability-remediation/run_exp122_evidence_diagnostic.py
  sha256: b18cb42fba9ff33470d85fd4467150210d04e370c6c8edeb625fc8774fc88374
  delta_from_exp121: Identity/root/domain/port only; evidence and lifecycle assertions are unchanged.
runtime_environment_gate:
  command_contract: Source ROS Jazzy, the persistent r6 fork overlay, and the isolated project overlay. Do not overwrite PYTHONPATH.
  proof: ros2cli distribution version 0.32.10 imports successfully; so101_mujoco_demo_py.qualification resolves from the isolated r6 gate build; ros2 --help exits zero.
runtime_identity:
  session: MNT-A-EXP122-full-01
  ros_domain_id: 194
  port: 8034
  gz_partition: so101-mnt-a-exp122
  evidence_root: /tmp/so101-debug-mujoco-maintainability-remediation/exp122
single_variable: The execution wrapper no longer overwrites PYTHONPATH. Physics hook, evidence consumer, frozen strategy, model, scene, controller, thresholds, and lifecycle assertions are identical to EXP-121.
procedure:
  - Start exactly one fresh non-headless stack from the r6 isolated overlay and perform the existing transactional reset.
  - Start the unchanged production workflow and observe the atomically checkpointed raw index.
  - Record the first persisted typed boundary plus content-addressed physics-step chunk, send no cancellation or other command to the independent workflow owner, and wait for /workflow/run to return naturally.
  - Only after a normal HTTP terminal response may ordered stop_stack run. A timeout preserves the owned stack and is INVALID_EVIDENCE.
acceptance:
  - Exactly one publisher exists on each evidence topic and publisher identities/GIDs persist.
  - Expected, snapshot, chunk, and all five sample session IDs equal MNT-A-EXP122-full-01.
  - The first chunk contains exactly five samples with strict physics_step +1, approximately 0.002 s time increments, zero failed publishes, and no evidence_loss.
  - A typed boundary persists; identity_mismatch and later invalid_reason remain absent.
  - Workflow naturally returns before teardown and ordered shutdown passes without owned process/domain/port residue.
  - Grasp business outcome is not an acceptance signal.
failure_policy: Any failed condition makes EXP-122 INVALID_EVIDENCE and stops further batch work. EXP-122 is run exactly once.
command: source /opt/ros/jazzy/setup.zsh; source /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install/setup.zsh; source /tmp/so101-debug-mujoco-maintainability-remediation/physics-hook-r6-gate-install/setup.zsh; GZ_PARTITION=so101-mnt-a-exp122 python3 /tmp/so101-debug-mujoco-maintainability-remediation/run_exp122_evidence_diagnostic.py
next_if_valid: Stop and report EXP-122 before preregistering any new five-run batch.
```

## Checkpoint MNT-CP-031 — EXP-122 terminal INVALID_EVIDENCE and provenance repair

```yaml
checkpoint_id: MNT-CP-031
recorded_at: 2026-08-12T20:29:03+08:00
terminal_experiment: EXP-122
status: INVALID_EVIDENCE
rerun_policy: EXP-122 is immutable and will not be rerun or reclassified.
execution_boundary:
  stack_ready: true
  reset_status: SUCCEEDED
  reset_session: MNT-A-EXP122-full-01
  workflow_motion_started: false
  policy_or_strategy_executed: false
terminal_reason: The workflow owner rejected preflight with POLICY_FINGERPRINT_MISMATCH before RESUME_PHYSICS or any phase command.
root_cause: dependency-lock fork.commit was correctly advanced from the r5 physical-policy baseline to the r6 runtime implementation, but live policy preflight overloaded that field as the approved contact policy's behavior-provenance commit. The unchanged approved policy correctly remained bound to r5 and therefore rejected the conflated r6 value.
evidence:
  result: /tmp/so101-debug-mujoco-maintainability-remediation/exp122/exp122-diagnostic.json
  result_sha256: 99cfcb486aae1bcdda8ced77fad66b802115369fbc3fb6b12987d17b934f37da
  launch_log: /tmp/so101-debug-mujoco-maintainability-remediation/exp122/run-01/launch.log
  launch_log_sha256: 01b79f208cb963c13a4d89a707fa10690a68f22b37630020862033c10ddf410c
  shutdown: PASS; ordered marker true, return code zero, no process_died or fatal signal, Domain 194 and port 8034 empty.
repair:
  commit: ee2f8ee022ca406e3175e49e9d1cfe27d39faa35
  runtime_provenance: fork.commit remains exact r6 738e304 and exact r6 tag equality remains enforced.
  policy_provenance: fork.policy_behavior_commit explicitly records r5 f42b7b3, the ancestor against which the unchanged approved physical policy was calibrated.
  invariant: The policy behavior commit must be an ancestor of the locked runtime commit. It does not weaken exact r6 runtime provenance.
  strategy_freeze: No contact policy, q6, waypoint, trajectory, planner, speed/acceleration, controller, MJCF, scene, geometry, threshold, or phase behavior changed.
red_green:
  RED: Two focused tests failed before policy_behavior_commit existed.
  GREEN: 18 focused provenance tests passed, frozen behavior plus Ruff gate passed, and clean isolated three-package build/test completed with 794 tests, 0 errors, 0 failures, 4 skipped.
  frozen_manifest_sha256: fa39a8b94071cf9e7aa6e800dbdfec77ed1d399bcd6b628000afeb373dc4e99f
next_experiment: EXP-123_PENDING_PREREGISTRATION
```

## EXP-123 preregistration — authoritative physics-step evidence diagnostic

```yaml
experiment_id: EXP-123
recorded_at: 2026-08-12T20:29:03+08:00
prior_experiment: EXP-122 remains permanently INVALID_EVIDENCE and is not rerun or reclassified.
status: PLANNED
purpose: Validate authoritative 500 Hz physics-step evidence identity, continuity, publisher provenance, typed boundary persistence, and clean lifecycle only; do not evaluate or tune grasp policy.
lifecycle: FULL_RESTART
behavior_source_commit: ee2f8ee022ca406e3175e49e9d1cfe27d39faa35
fork_runtime_commit: 738e304551b4ea6db020b466086a13db71b65607
fork_policy_behavior_commit: f42b7b3d77288c2fee750fe53b0258e0a3d18194
install_overlay: /tmp/so101-debug-mujoco-maintainability-remediation/policy-provenance-r6-install
runtime_fingerprint:
  path: /tmp/so101-debug-mujoco-maintainability-remediation/policy-provenance-r6-runtime-fingerprint.json
  sha256: a955bd250bcb0fec5dfd49c8dbe061d66858579ae380cb8c871109446282e6e9
frozen_behavior_manifest_sha256: fa39a8b94071cf9e7aa6e800dbdfec77ed1d399bcd6b628000afeb373dc4e99f
harness:
  path: /tmp/so101-debug-mujoco-maintainability-remediation/run_exp123_evidence_diagnostic.py
  sha256: 9bacf5156726ce7a55ab04a1386072441e0da7c554581c62c7d87620fc7ee718
  static_checks: py_compile and Ruff PASS; no terminate(), kill(), or /execution/cancel path.
runtime_identity:
  session: MNT-A-EXP123-full-01
  ros_domain_id: 195
  port: 8035
  gz_partition: so101-mnt-a-exp123
  evidence_root: /tmp/so101-debug-mujoco-maintainability-remediation/exp123
single_variable: Runtime and approved-policy provenance are represented separately. All motion, policy, model, scene, controller, threshold, evidence-hook, and lifecycle semantics remain unchanged from EXP-122.
procedure:
  - Start one fresh non-headless stack, perform the transactional reset, and run the unchanged production workflow.
  - Persist the first typed boundary and content-addressed chunk, send no cancellation, wait for the independent workflow owner to return naturally, then perform ordered shutdown.
acceptance:
  - One publisher per evidence topic; expected/snapshot/chunk/all five sample session IDs match MNT-A-EXP123-full-01.
  - First chunk has five samples, strict physics_step +1, approximately 0.002 s time increments, zero failed publishes, and no evidence_loss.
  - A typed boundary persists with no identity_mismatch or invalid_reason.
  - Workflow naturally returns before teardown; ordered shutdown and process/domain/port cleanup pass.
  - Grasp business outcome is not an acceptance signal.
failure_policy: Any failed condition makes EXP-123 INVALID_EVIDENCE and stops further batch work. Run exactly once.
command: source /opt/ros/jazzy/setup.zsh; source /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install/setup.zsh; source /tmp/so101-debug-mujoco-maintainability-remediation/policy-provenance-r6-install/setup.zsh; GZ_PARTITION=so101-mnt-a-exp123 python3 /tmp/so101-debug-mujoco-maintainability-remediation/run_exp123_evidence_diagnostic.py
next_if_valid: Stop and report EXP-123 before preregistering any new five-run batch.
```

## Checkpoint MNT-CP-032 — EXP-123 terminal INVALID_EVIDENCE and storage-throughput repair

```yaml
checkpoint_id: MNT-CP-032
recorded_at: 2026-08-12T20:48:54+08:00
terminal_experiment: EXP-123
status: INVALID_EVIDENCE
rerun_policy: EXP-123 is immutable and will not be rerun or reclassified.
execution_boundary:
  stack_ready: true
  reset_status: SUCCEEDED
  reset_session: MNT-A-EXP123-full-01
  workflow_http_status: 503 PHASE_EXIT_NONZERO
  clean_shutdown: PASS; ordered marker true, return code zero, no process_died or fatal signal, Domain 195 and port 8035 empty.
observed_authoritative_chunk:
  chunk_sequence: 5113
  physics_steps: [25566, 25567, 25568, 25569, 25570]
  simulation_times_s: [55.70200000002211, 55.70400000002211, 55.70600000002211, 55.70800000002212, 55.71000000002212]
  timestep_s: 0.002
  failed_publish_attempts: 0
  evidence_loss: false
  session_identity: All chunk and sample session IDs matched MNT-A-EXP123-full-01.
terminal_reason: The first chunk persisted, but the consumer later observed a nonconsecutive chunk sequence before the first typed transport boundary and closed INVALID_EVIDENCE.
root_cause:
  disproven: The consumer does not require the first observed global chunk sequence to be zero; sequence 5113 was accepted correctly.
  measured_tmp_store: The existing required per-chunk atomic file plus run-index fsync path averaged 89.543 ms per chunk on /tmp (/dev/sda3), with all 100 measurements above 20 ms.
  incoming_cadence: One five-step chunk every 10 ms (100 Hz).
  conclusion: Synchronous durable persistence on the slow /tmp volume could service only about 11 Hz, so the reliable DDS history eventually evicted unread chunks and the strict continuity detector correctly failed closed.
evidence:
  result: /tmp/so101-debug-mujoco-maintainability-remediation/exp123/exp123-diagnostic.json
  result_sha256: 16f4e1ee6d239c511ba596e3ed6a11604c7aaa294752471b8d72af0fa68c0015
  launch_log: /tmp/so101-debug-mujoco-maintainability-remediation/exp123/run-01/launch.log
  launch_log_sha256: 872ad6819ccd7c32c58094670a05f54a2fa20f71d183dd8189de2e1c3e7e800e
  raw_index: /tmp/so101-teleop-evidence/MNT-A-EXP123-full-01/so101-teleop-workflow-02435a60-81e3-49d9-a7ee-9103a4f6d00b/transport-dynamic-raw/run-index.json
  raw_index_sha256: f32ee31b0a09c9b91b5325e4b1d9f5706a2e73aa93f22e07dcadf828694e0195
  first_chunk_sha256: 2310563733bf96ea20464c22bbd37b42b8985b25b2246c633a29f877f176fc7c
repair:
  commit: b0f83b67a1414f394ac5aeb8693acc74cf575bd4
  contract: ProductionQualificationRunner binds SO101_TELEOP_EVIDENCE_BASE to its caller-provisioned evidence_root/teleop-evidence. Standalone Teleop retains the legacy default and accepts only an absolute explicit override.
  durability: Atomic per-chunk file fsync, atomic run-index fsync, content hashes, strict sequence checks, five-sample chunk format, and producer QoS are unchanged.
  measured_nvme_store: The identical synchronous persistence path averaged 2.136 ms per chunk on /data/work (/dev/nvme0n1p5), with one of 100 samples above 10 ms and DDS depth sufficient for that isolated spike.
  strategy_freeze: No contact policy, q6, waypoint, trajectory, planner, speed/acceleration, controller, MJCF, scene, geometry, threshold, phase order, or producer hook changed.
red_green:
  RED: Three focused tests failed before the absolute evidence-base override and qualification-volume binding existed.
  GREEN: 24 focused tests passed; full Python gate passed 537 with 4 skipped; Ruff and frozen-behavior gates passed.
  isolated_gate: Fresh three-package build/test at storage-route-r7-install passed 798 tests, 0 errors, 0 failures, 4 skipped.
  runtime_gate: Exact r6 fork/runtime and all three isolated project package prefixes passed; frozen manifest SHA-256 is 737e303cc0d57d14e9cbf392191fc289ff1a9875458202e852c37a0bdfdadd49.
protected_gazebo: src/so101_gazebo_demo_py working-tree diff NONE.
next_experiment: EXP-124_PENDING_PREREGISTRATION
```

## EXP-124 preregistration — qualified-volume physics-step evidence diagnostic

```yaml
experiment_id: EXP-124
recorded_at: 2026-08-12T20:48:54+08:00
prior_experiment: EXP-123 remains permanently INVALID_EVIDENCE and is not rerun or reclassified.
status: PLANNED
purpose: Validate authoritative 500 Hz physics-step evidence identity, continuity, typed boundary persistence, and clean lifecycle on caller-provisioned durable storage only; do not evaluate or tune grasp policy.
lifecycle: FULL_RESTART
behavior_source_commit: b0f83b67a1414f394ac5aeb8693acc74cf575bd4
fork_runtime_commit: 738e304551b4ea6db020b466086a13db71b65607
fork_policy_behavior_commit: f42b7b3d77288c2fee750fe53b0258e0a3d18194
install_overlay: /tmp/so101-debug-mujoco-maintainability-remediation/storage-route-r7-install
runtime_fingerprint:
  path: /tmp/so101-debug-mujoco-maintainability-remediation/storage-route-r7-runtime-fingerprint.json
  sha256: b2fcf7c04882248de07ca6716f26097f550d76c7e210479fa51273a587363234
frozen_behavior_manifest_sha256: 737e303cc0d57d14e9cbf392191fc289ff1a9875458202e852c37a0bdfdadd49
harness:
  path: /tmp/so101-debug-mujoco-maintainability-remediation/run_exp124_evidence_diagnostic.py
  sha256: 0411a5da59dc2d9ab2b1f7bf5e09080024fb6495b8a8e0d511d1828ae17c6281
  static_checks: py_compile and Ruff PASS; no terminate(), kill(), or /execution/cancel path.
runtime_identity:
  session: MNT-A-EXP124-full-01
  ros_domain_id: 196
  port: 8036
  gz_partition: so101-mnt-a-exp124
  qualification_evidence_root: /data/work/so101-debug-mujoco-maintainability-remediation/exp124
  teleop_evidence_base: /data/work/so101-debug-mujoco-maintainability-remediation/exp124/teleop-evidence
single_variable: The qualification owner routes unchanged high-rate durable evidence writes from the slow /tmp filesystem to its explicit NVMe evidence volume. Physics hook, producer cadence/chunk size/QoS, consumer validation, storage durability, frozen strategy, model, scene, controller, thresholds, and lifecycle assertions are identical to EXP-123.
procedure:
  - Start exactly one fresh non-headless stack from the isolated storage-route-r7 overlay and perform the existing transactional ResetWorld.
  - Run the unchanged production workflow, send no cancellation or other command, and wait for /workflow/run to return naturally.
  - Observe at least one content-addressed five-sample chunk plus the first typed transport boundary on the qualification-provisioned evidence volume.
  - Only after a normal HTTP terminal response perform ordered stop_stack. A timeout preserves the owned stack and is INVALID_EVIDENCE.
acceptance:
  - Exactly one publisher exists on each evidence topic; expected/snapshot/chunk/all five first-chunk sample session IDs equal MNT-A-EXP124-full-01.
  - First chunk has exactly five consecutive physics steps, approximately 0.002 s time increments, zero failed publishes, and no evidence_loss.
  - At least one typed boundary persists; identity_mismatch, invalid_reason, chunk gap, duplicate, or reversal remain absent through natural workflow return.
  - The raw index and chunk paths resolve under the provisioned NVMe evidence base and retain their verified SHA-256 hashes.
  - Ordered shutdown and owned process/domain/port cleanup pass. Grasp business outcome is not an acceptance signal.
failure_policy: Any failed condition makes EXP-124 INVALID_EVIDENCE and stops further batch work. Run exactly once.
command: source /opt/ros/jazzy/setup.zsh; source /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install/setup.zsh; source /tmp/so101-debug-mujoco-maintainability-remediation/storage-route-r7-install/setup.zsh; GZ_PARTITION=so101-mnt-a-exp124 python3 /tmp/so101-debug-mujoco-maintainability-remediation/run_exp124_evidence_diagnostic.py
next_if_valid: Stop and report EXP-124 before preregistering any new five-run batch.
```

## Checkpoint MNT-CP-033 — EXP-124 VALID qualified-volume evidence diagnostic

```yaml
checkpoint_id: MNT-CP-033
recorded_at: 2026-08-12T20:53:02+08:00
terminal_experiment: EXP-124
status: VALID
qualification_counting: false
purpose_result: The 500 Hz physics-step evidence plumbing, strict continuity detector, typed transport boundaries, and lifecycle are valid when the qualification owner provisions a storage volume that can sustain the required durable writes.
execution:
  stack_ready: true
  reset_status: SUCCEEDED
  reset_session: MNT-A-EXP124-full-01
  workflow_http_returned_naturally: true
  workflow_business_terminal: HTTP 503 BACKEND_OPERATION_FAILED / PHASE_EXIT_NONZERO after transport; excluded by the preregistered diagnostic acceptance contract.
  strategy_changed: false
authoritative_raw_evidence:
  index: /data/work/so101-debug-mujoco-maintainability-remediation/exp124/teleop-evidence/MNT-A-EXP124-full-01/so101-teleop-workflow-937f099c-1023-45c2-9822-5d936cf7de4c/transport-dynamic-raw/run-index.json
  index_sha256: 8d51eb34fed9c2248618a80eba1acf5fffc0681899cfb6595da63f68b1c4be83
  status: COMPLETE
  outcome_class: PHYSICAL_TRANSPORT_SUCCESS
  physical_transport_outcome: FORMAL_MOVE_ABOVE_PLACE_PROVED
  chunk_count: 741
  chunk_sequence_range: [4921, 5661]
  physics_sample_count: 3705
  physics_step_range: [24606, 28310]
  typed_boundary_count: 12
  independent_replay_checks:
    content_hashes_match: true
    chunk_sequence_and_physics_steps_continuous: true
    simulation_time_increment_s: 0.002
    session_ids_match: true
    evidence_loss: false
    failed_publish_attempts_total: 0
acceptance_checks:
  sessions_match: true
  publisher_counts_match: true
  first_chunk_present: true
  first_chunk_has_five_samples: true
  first_chunk_steps_are_consecutive: true
  first_chunk_timestep_is_2ms: true
  first_chunk_has_no_evidence_loss: true
  first_chunk_sample_sessions_match: true
  first_boundary_present: true
  no_identity_mismatch: true
  no_later_evidence_invalidity: true
  workflow_http_returned: true
  clean_shutdown: true
evidence:
  result: /data/work/so101-debug-mujoco-maintainability-remediation/exp124/exp124-diagnostic.json
  result_sha256: fe4d98ef2e738854ae415b431c40b3e8711b22710d215b6dc1136c798cc09038
  launch_log: /data/work/so101-debug-mujoco-maintainability-remediation/exp124/run-01/launch.log
  launch_log_sha256: 54affe710254524373634641242edd2e82f095217c45969be2c3bce22eee4e5a
provenance:
  behavior_source_commit: b0f83b67a1414f394ac5aeb8693acc74cf575bd4
  preregistration_commit: 12007c4
  runtime_fingerprint_sha256: b2fcf7c04882248de07ca6716f26097f550d76c7e210479fa51273a587363234
  frozen_behavior_manifest_sha256: 737e303cc0d57d14e9cbf392191fc289ff1a9875458202e852c37a0bdfdadd49
  fork_runtime_commit: 738e304551b4ea6db020b466086a13db71b65607
  fork_policy_behavior_commit: f42b7b3d77288c2fee750fe53b0258e0a3d18194
shutdown:
  ordered_marker: true
  returncode: 0
  fatal_signal: false
  process_died: false
  domain_196_nodes_after_stop: NONE
  port_8036_listener_after_stop: NONE
  owned_process_residue: NONE
protected_state:
  src_so101_gazebo_demo_py_diff: NONE
  preserved_untracked_user_files:
    - docs/experiments/so101-gazebo-mujoco-policy-parity-solver-iters-ledger.md
    - docs/experiments/so101-mujoco-ros2-migration-experiment-summary.md
conclusion: The EXP-123 chunk-gap block was a storage-volume throughput mismatch, not a producer, controller, MuJoCo physics, or grasp-strategy defect. The formal qualification path now supplies the evidence volume, and EXP-124 proves lossless 500 Hz capture through a successful physical transport without changing the five-win strategy.
next_experiment: NONE_STOP_AND_REPORT_BEFORE_ANY_FIVE_RUN_BATCH
next_command: Report EXP-124 and the remaining post-transport PHASE_EXIT_NONZERO as a separate business-phase issue. Do not preregister or start a five-run batch in this checkpoint.
```

## Checkpoint MNT-CP-034 — post-transport first-bad-boundary diagnosis

```yaml
checkpoint_id: MNT-CP-034
recorded_at: 2026-08-12T21:19:00+08:00
last_valid_experiment: EXP-124
current_hypothesis: Commit d03e48f mechanically mapped the approved 1.1579004532160448 N static-contact threshold onto dynamic held-cup phases, invalidating the already qualified force-mode semantics without changing motion.
working_tree_status: Clean tracked tree at 7b23f4fd943301672581ab31dd1d3aabbefa6831; two protected unrelated untracked experiment documents remain preserved.
owned_processes: NONE
preserved_processes: Existing codex, codex-cua, and so101-mujoco-gui tmux sessions; no task-owned ROS or MuJoCo process is running.
observed:
  - EXP-124 transport returned exit 0 with FORMAL_MOVE_ABOVE_PLACE_PROVED; the next phase descend returned exit 1 before issuing any descend waypoint, at stable_gate with force boundary exceeded.
  - EXP-124 final lossless transport samples measured approximately 4.93 to 5.01 N, above the static 1.1579004532160448 N threshold and below the unchanged 11.60 N diagnostic hard stop.
  - Five frozen successful TASK15 FULL_RESTART runs entered descend at 4.00 to 4.12 N, completed descend at up to 4.84 N, completed place alignment at up to 5.18 N, and entered release at up to 5.03 N.
  - Git history proves d03e48f replaced the previously qualified 11.60 N dynamic hard stop with maximum_safe_force_n in descend, place_alignment, and pre-release stable_state.
disproven_routes:
  - Transport evidence storage or r6 physics-hook instrumentation changed the physical strategy; EXP-124 endpoint force and pose match the historical successful transport population.
  - A post-transport retry or stale manifest caused the failure; descend is the first uncompleted phase and its own evidence records the direct force-gate exception.
open_risks:
  - The same incorrect static-mode mapping exists in descend, place_alignment, and the gripper-contact=true pre-release state; fixing only the first observed line would merely move the deterministic failure downstream.
next_command: Add RED contracts for typed dynamic-held-object force mode and post-transport phase wiring before implementation.
```

## EXP-125 preregistration — restore qualified post-transport force-mode semantics

```yaml
experiment_id: EXP-125
recorded_at: 2026-08-12T21:19:00+08:00
prior_experiment: EXP-124 VALID evidence diagnostic with separate business-phase failure.
status: RUNNING
lifecycle: FULL_RESTART
qualification_counting: false
purpose: Prove the production nine-phase workflow restores the previously qualified dynamic held-cup force semantics after transport while preserving every motion, controller, scene, model, contact-policy value, and evidence contract.
source_commit_before_fix: 7b23f4fd943301672581ab31dd1d3aabbefa6831
behavior_source_commit: d30bf2bd54ea9359d08b866cdda447dfe2a3c271
runtime_identity:
  simulation_session_id: MNT-A-EXP125-full-01
  ros_domain_id: 197
  port: 8037
  gz_partition: so101-mnt-a-exp125
isolated_install: /tmp/so101-debug-mujoco-maintainability-remediation/exp125-install
qualified_evidence_root: /data/work/so101-debug-mujoco-maintainability-remediation/exp125
runtime_fingerprint: /tmp/so101-debug-mujoco-maintainability-remediation/exp125-runtime-fingerprint.json
runtime_fingerprint_sha256: 76d232a44949c1750a771a57d3f1026c8321637e9d41fe110fc3d72e88f4867c
run_harness: /tmp/so101-debug-mujoco-maintainability-remediation/run_exp125_full.py
run_harness_sha256: 80aba66689620c71952dd799b86b24cac3b7f29cb5ad143002875121160369de
single_variable: Phase classification only. Descend, place alignment, and the pre-release gripper-contact state use the existing 11.60 N diagnostic hard stop with the 1.1579004532160448 N static threshold retained as shadow evidence; post-release support/settling continues to enforce the approved static threshold. No numeric threshold changes.
preconditions:
  - RED tests prove the current code cancels historical qualified 4 to 5 N held-cup samples solely because those phases are misclassified as static.
  - Motion-policy hash, all target vectors, planner scalings, q6, MJCF, scene, controllers, thresholds, release/retreat behavior, and protected Gazebo package remain unchanged.
  - Use one fresh isolated overlay, unique ROS domain/session/port, qualified NVMe evidence root, transactional ResetWorld, and exactly one natural workflow invocation.
success_criteria:
  - All nine production phases return their expected evidence statuses through RELEASE_RETREAT_FINAL_PLACEMENT_PROVED without retry, reset, pause, direct object write, simulator constraint, or hidden attachment.
  - Dynamic held-cup samples below 11.60 N do not cancel solely for crossing the static shadow threshold; an inclusive 11.60 N sample still cancels immediately.
  - Post-release final placement samples still require maximum_normal_force_n <= 1.1579004532160448 N plus the existing support, detachment, controller, scene, pose, and stability gates.
  - Lossless transport evidence, ordered shutdown, domain/port/process cleanup, frozen-behavior manifest, package tests, Ruff, and Gazebo isolation all pass.
  - Fresh CUA visual evidence shows the cup released stably inside the target ring and the arm/gripper clear.
failure_criteria:
  - Any phase or final physical/scene/visual gate fails under the single corrected phase classification.
invalid_criteria:
  - Any motion/threshold/model/scene/controller mutation, retry, lifecycle contamination, evidence gap, provenance mismatch, missing visual proof, or unclean shutdown.
next_if_valid: Commit and report EXP-125. Do not start the five-run qualification batch without a new ledger preregistration.
```

## EXP-125 terminal — one-shot full workflow and visual validation

```yaml
experiment_id: EXP-125
completed_at: 2026-08-12T21:29:30+08:00
status: VALID_SUCCESS
qualification_counting: false
lifecycle: FULL_RESTART
behavior_source_commit: d30bf2bd54ea9359d08b866cdda447dfe2a3c271
ledger_runtime_commit: 6bb9e20e7f749d51fe48eadfc75021188e4e92a1
single_variable_observed: Only the force-mode classification changed; all frozen motion, model, scene, controller, geometry, contact-policy values, and numeric thresholds retained their registered hashes.
runtime_identity:
  simulation_session_id: MNT-A-EXP125-full-01
  reset_epoch: 1
  ros_domain_id: 197
  port: 8037
  gz_partition: so101-mnt-a-exp125
workflow:
  http_status: 200
  manifest_status: DONE
  phases:
    staged_approach: CLOSE_READY
    contact_hold: CONTACT_ONLY_PROVED
    micro_lift: PHYSICAL_MICRO_LIFT_PROVED
    policy_lift_waypoint1: POLICY_LIFT_WAYPOINT1_PHYSICAL_TRANSFER_PROVED
    remaining_lift: REMAINING_FORMAL_LIFT_PROVED
    transport: FORMAL_MOVE_ABOVE_PLACE_PROVED
    descend: FORMAL_DESCEND_TO_PRE_RELEASE_CLEARANCE_PROVED
    place_alignment: PRE_RELEASE_ALIGNMENT_PROVED
    release_retreat: RELEASE_RETREAT_FINAL_PLACEMENT_PROVED
phase_force_evidence:
  descend_observed_range_n: [1.7920740359451592, 4.790514754509598]
  place_alignment_observed_range_n: [4.491798001059205, 4.99687211872404]
  pre_release_gripper_held_n: 4.669717899673312
  released_static_n: 0.23494367933416632
  static_limit_n: 1.1579004532160448
  dynamic_diagnostic_hard_stop_n: 11.60
physical_outcome:
  primary_failure: null
  final_xyz_m: [-0.0788784507776764, -0.24664117745912967, 0.16504929906275206]
  final_upright_tilt_rad: 0.010232942344296817
  maximum_linear_speed_m_s: 0.0
  maximum_angular_speed_rad_s: 0.0
  support_contact: true
  gripper_contact: false
  moveit_attached: false
  world_object_synchronized: true
  direct_object_state_writes: 0
  simulator_constraint_calls: 0
  physics_pause_calls: 0
transport_raw_evidence:
  chunk_count: 746
  sample_count: 3730
  first_physics_step: 23731
  last_physics_step: 27460
  physics_timestep_s: 0.002
  lossless: true
  run_index_sha256: 13f02db3c9ef203f984f3471e72f8af08ed50452adec0b8a72b2dacd8728cd8c
visual_acceptance:
  required_mujoco_claims_passed: true
  mujoco_status_running: true
  cup_upright_inside_target_ring: true
  open_gripper_and_arm_retired_clear: true
  robot_pedestal_table_cup_ring_visible: true
  screenshot: /data/work/so101-debug-mujoco-maintainability-remediation/exp125/cua-visual.png
  screenshot_sha256: cebd657c3363df16d6d1bfaea55317e2e54beb98f6a6ed55d9234ac14acb0e85
  auxiliary_rviz_window_available: false
  note: The fresh CUA image proves the preregistered MuJoCo physical visual gate. This launch did not create an RViz window, so RViz-only auxiliary claims remain explicitly unsupported rather than inferred.
gates:
  focused_regression: 74 passed
  full_source_pytest: 539 passed, 4 skipped
  isolated_colcon_test_result: 800 tests, 0 errors, 0 failures, 4 skipped
  ruff: PASS
  frozen_behavior_manifest: PASS
  runtime_source_lock: PASS
  reset_source_lock: PASS
  protected_gazebo_tree: NO_DIFF
shutdown:
  ordered_marker: true
  returncode: 0
  fatal_signal: false
  process_died: false
  domain_197_nodes_after_stop: NONE
  port_8037_listener_after_stop: NONE
  owned_process_residue: NONE
artifacts:
  result: /data/work/so101-debug-mujoco-maintainability-remediation/exp125/exp125-result.json
  result_sha256: 80a8c645603bdeac9c1f18bcfb4fc37621d99829e5eb701c6e3be5f57bd22d87
  manifest_sha256: 7dca300dbefc11ed4472eb8d8ed2db06080ae0e0be3e053cd40a866b5e6dbc04
protected_state:
  src_so101_gazebo_demo_py_diff: NONE
  preserved_untracked_user_files:
    - docs/experiments/so101-gazebo-mujoco-policy-parity-solver-iters-ledger.md
    - docs/experiments/so101-mujoco-ros2-migration-experiment-summary.md
conclusion: EXP-124's post-transport failure was a phase-classification regression, not a failed grasp strategy. Restoring the qualified dynamic held-cup force semantics allows the unchanged strategy to complete all nine phases and pass physical, lossless-evidence, visual, and shutdown gates in one natural workflow invocation.
next_experiment: NONE_STOP_BEFORE_FIVE_RUN_QUALIFICATION
next_command: Report EXP-125. If a new five-run qualification is authorized, preregister it separately without changing the now-proven strategy.
```

## Checkpoint MNT-CP-035 — post-transport regression closed

```yaml
checkpoint_id: MNT-CP-035
recorded_at: 2026-08-12T21:29:30+08:00
last_valid_experiment: EXP-125
working_tree_status: Tracked tree clean after the EXP-125 result commit; two protected unrelated untracked experiment documents remain preserved.
owned_processes: NONE
preserved_processes: Existing codex, codex-cua, and so101-mujoco-gui tmux sessions only.
resolved:
  - Dynamic held-cup descend, place alignment, and pre-release state no longer fail solely for crossing the static shadow threshold.
  - The inclusive 11.60 N diagnostic hard stop remains unchanged for held-cup motion.
  - Released-cup static support still enforces 1.1579004532160448 N and passed at 0.23494367933416632 N.
  - The unchanged production strategy completed all nine phases once without retry, reset, pause, direct object write, or simulator constraint.
next_command: Stop. Do not start a five-run batch until its own ledger preregistration is reviewed.
```

## Checkpoint MNT-CP-036 — five-run qualification recovery and preregistration

```yaml
checkpoint_id: MNT-CP-036
recorded_at: 2026-08-12T21:45:00+08:00
last_valid_experiment: EXP-125
recovery_status: COMPLETE
execution_host: AI-STATION-001; direct local execution, no SSH
worktree:
  path: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
  linked_worktree: true
  branch: codex/so101-mujoco-ros2-teleop
  head_before_preregistration: e18aedcbb593842553655df5b0070f6e2df3b2ff
  tracked_status: CLEAN
  protected_untracked_user_files:
    - docs/experiments/so101-gazebo-mujoco-policy-parity-solver-iters-ledger.md
    - docs/experiments/so101-mujoco-ros2-migration-experiment-summary.md
  protected_gazebo_status: src/so101_gazebo_demo_py has zero status, unstaged diff, and staged diff.
fork_provenance:
  local_commit: 738e304551b4ea6db020b466086a13db71b65607
  local_tag: so101-0.0.3-r6; annotated and peels to the local commit
  gitee_origin_main: 738e304551b4ea6db020b466086a13db71b65607
  gitee_remote_tag: so101-0.0.3-r6; annotated and peels to 738e304551b4ea6db020b466086a13db71b65607
  local_vs_origin_main: {ahead: 0, behind: 0}
  submodule_status: CLEAN
runtime_preflight:
  owned_processes: NONE
  relevant_processes: NONE
  ros_domains_empty: [0, 198, 199, 200, 201, 202]
  free_http_ports: [8038, 8039, 8040, 8041, 8042]
  absent_tmux_sessions: [so101-mnt-q-exp126, so101-mnt-q-exp127, so101-mnt-q-exp128, so101-mnt-q-exp129, so101-mnt-q-exp130]
  absent_evidence_roots:
    - /data/work/so101-debug-mujoco-maintainability-remediation/exp126
    - /data/work/so101-debug-mujoco-maintainability-remediation/exp127
    - /data/work/so101-debug-mujoco-maintainability-remediation/exp128
    - /data/work/so101-debug-mujoco-maintainability-remediation/exp129
    - /data/work/so101-debug-mujoco-maintainability-remediation/exp130
  preserved_tmux: [codex attached, codex-cua idle at zsh prompt, so101-mujoco-gui historical windows]
recovered_EXP_125:
  behavior_source_commit: d30bf2bd54ea9359d08b866cdda447dfe2a3c271
  result_commit: e18aedcbb593842553655df5b0070f6e2df3b2ff
  simulation_session_id: MNT-A-EXP125-full-01
  ros_domain_id: 197
  http_port: 8037
  gz_partition: so101-mnt-a-exp125
  result: VALID_SUCCESS; HTTP 200; manifest DONE; all nine phases passed.
  transport: 746 chunks, 3730 consecutive samples, 0.002 s timestep, run-index sha256 13f02db3c9ef203f984f3471e72f8af08ed50452adec0b8a72b2dacd8728cd8c.
  physical: Final cup upright and supported inside target, gripper contact false, MoveIt detached/world synchronized, arm clear.
  visual_sha256: cebd657c3363df16d6d1bfaea55317e2e54beb98f6a6ed55d9234ac14acb0e85
  shutdown: Ordered shutdown, Domain 197, port 8037, and owned-process cleanup passed.
confirmed_conclusions:
  - EXP-125 proves the unchanged strategy completes all nine phases when held-cup descend, alignment, and pre-release use the inclusive 11.60 N dynamic diagnostic hard stop while released static support retains 1.1579004532160448 N.
  - EXP-124 proves lossless 500 Hz evidence on the qualification-provisioned NVMe volume; its earlier post-transport failure was not an evidence or grasp-strategy defect.
  - The r6 fork commit/tag is now published and exactly synchronized with the local submodule.
disproven_routes:
  - Treating dynamic held-cup crossings of the static threshold as strategy failure.
  - Attributing EXP-124's post-transport failure to storage, the r6 physics hook, retry, stale manifests, or changed physical strategy.
  - Reusing stale installs or mixing FULL_RESTART with RESET_WORLD evidence.
next_experiment_new_information:
  prior: EXP-125 is one non-counting FULL_RESTART success under the frozen production contract.
  new: EXP-126 through EXP-130 will test whether the exact same behavior and one fresh common overlay produce five consecutive independent FULL_RESTART successes.
owned_processes: NONE
next_experiment: EXP-126
next_command: Commit this preregistration, then create one fresh isolated three-package build/test overlay before EXP-126 can transition to RUNNING.
```

## EXP-126 through EXP-130 — five consecutive FULL_RESTART qualification preregistration

```yaml
batch_id: MNT-Q-EXP126-130
status: INVALID_STOPPED
registered_at: 2026-08-12T21:45:00+08:00
prior_experiment: EXP-125
goal: Five consecutive VALID production nine-phase successes under independent FULL_RESTART lifecycles.
qualification_contract:
  lifecycle: FULL_RESTART
  target_consecutive_successes: 5
  workflow_invocations_per_run: 1
  reset_transactions_per_run: 1
  retry_count: 0
  forbidden_actions: [second reset, physics pause, direct object write, simulator constraint, hidden attachment, strategy tuning]
  stop_rule: Any VALID business failure ends the streak and batch; any INVALID run invalidates and stops the batch.
frozen_behavior:
  behavior_source_commit: d30bf2bd54ea9359d08b866cdda447dfe2a3c271
  parent_result_commit_before_preregistration: e18aedcbb593842553655df5b0070f6e2df3b2ff
  fork_runtime_commit: 738e304551b4ea6db020b466086a13db71b65607
  fork_release_tag: so101-0.0.3-r6
  motion_policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
  contact_policy_sha256: c4ba607fea92f7c605fbc8cf08df0dfa3278113c71d1dd6ff10ea402e8186f82
  dependency_lock_sha256: be6bc595cd71a10df32765e11884183c0096db765a5ee35c3ef6a0b109ef5a3a
  task_scene_sha256: a2a49391e52d1f885e8ebb4c85fd282d1e83f0ce82eb63e83bac645343b1f9a0
  scene_sha256: b98eca6f2ae8547b8b7213625512ef360c5496c7ea2d124535698ea58b24e7c0
  robot_mjcf_sha256: f87a033fab8cf7291e737519290a639e0310e703f8169288f075f3fe0c8b5aca
  urdf_sha256: 0646707fbfb8fdfea5076afbf89f297027c0324465ab7ebe8129fc36c0445f4a
  frozen_manifest_file_sha256: eb42f058017252c8c9824f408982a5f29939bba41a27a32c8ad963aab61a90ed
  static_threshold_n: 1.1579004532160448
  dynamic_diagnostic_hard_stop_n: 11.60; inclusive
common_provenance:
  install_overlay: /tmp/so101-debug-mujoco-maintainability-remediation/exp126-five-run-gate/install
  runtime_package_prefix: /tmp/so101-debug-mujoco-maintainability-remediation/exp126-five-run-gate/install/so101_mujoco_demo_py
  runtime_fingerprint: /tmp/so101-debug-mujoco-maintainability-remediation/exp126-five-run-runtime-fingerprint.json
  run_harness: /tmp/so101-debug-mujoco-maintainability-remediation/run_exp126_five_run.py
  source_contract: Build from the committed preregistration source; record the exact preregistration commit, install tree hash, runtime fingerprint hash, package prefixes, and harness hash before EXP-126 RUNNING.
common_success_criteria:
  - Fresh transactional ResetWorld receipt matches the run session, simulation step 0, and an increasing epoch.
  - One natural /workflow/run returns HTTP 200 with the exact nine-phase trace and terminal statuses through RELEASE_RETREAT_FINAL_PLACEMENT_PROVED; manifest status is DONE.
  - MuJoCo proves table support, upright cup inside target, no gripper contact, open gripper and clear arm, and bounded terminal twist.
  - MoveIt proves detached cup synchronized as a world object with correct table, pedestal, and cup primitives; controllers, action results, and joint feedback are healthy.
  - Transport evidence has one publisher per topic, exact session identity, consecutive 0.002 s physics steps, valid content hashes, and no truncation, loss, gap, duplicate, reversal, or identity mismatch.
  - Direct object writes, physics pause calls, simulator constraint calls, retries, and hidden attachments remain zero.
  - A fresh existing-codex-cua snapshot visibly proves MuJoCo Running, robot/pedestal/table/cup/ring visible, upright cup in ring, gripper open, and arm clear.
  - Ordered shutdown passes and the registered domain, port, tmux/process ownership set are empty before the next run.
common_failure_criteria:
  - Any fresh, provenance-valid business/physical/scene/controller/visual failure is VALID and ends the batch.
common_invalid_criteria:
  - Any source/install/fingerprint mismatch, initial-state pollution, missing visual proof, evidence identity/loss fault, unexpected retry/reset/pause/write/constraint, duplicate stack, or unclean cleanup is INVALID and stops the batch.
experiments:
  - experiment_id: EXP-126
    status: INVALID
    prior_experiment: EXP-125
    hypothesis: The frozen production contract succeeds after one independent FULL_RESTART.
    prediction: All common success criteria pass with consecutive_count 1.
    single_variable: NONE
    lifecycle: FULL_RESTART
    provenance:
      simulation_session_id: MNT-Q-EXP126-full-01
      ros_domain_id: 198
      http_port: 8038
      gz_partition: so101-mnt-q-exp126
      evidence_root: /data/work/so101-debug-mujoco-maintainability-remediation/exp126
    command: GZ_PARTITION=so101-mnt-q-exp126 python3 /tmp/so101-debug-mujoco-maintainability-remediation/run_exp126_five_run.py --experiment-id EXP-126 --session-id MNT-Q-EXP126-full-01 --domain-id 198 --port 8038 --evidence-root /data/work/so101-debug-mujoco-maintainability-remediation/exp126
    decision: PENDING
    next_experiment: EXP-127_ON_SUCCESS_ONLY
  - experiment_id: EXP-127
    status: VALID
    prior_experiment: EXP-126
    hypothesis: A second independent FULL_RESTART extends the unchanged streak.
    prediction: All common success criteria pass with consecutive_count 2.
    single_variable: NONE
    lifecycle: FULL_RESTART
    provenance:
      simulation_session_id: MNT-Q-EXP127-full-01
      ros_domain_id: 199
      http_port: 8039
      gz_partition: so101-mnt-q-exp127
      evidence_root: /data/work/so101-debug-mujoco-maintainability-remediation/exp127
    command: GZ_PARTITION=so101-mnt-q-exp127 python3 /tmp/so101-debug-mujoco-maintainability-remediation/run_exp126_five_run.py --experiment-id EXP-127 --session-id MNT-Q-EXP127-full-01 --domain-id 199 --port 8039 --evidence-root /data/work/so101-debug-mujoco-maintainability-remediation/exp127
    decision: KEEP_VALID_SUCCESS_2_OF_5
    next_experiment: EXP-128_ON_SUCCESS_ONLY
  - experiment_id: EXP-128
    status: PLANNED
    prior_experiment: EXP-127
    hypothesis: A third independent FULL_RESTART extends the unchanged streak.
    prediction: All common success criteria pass with consecutive_count 3.
    single_variable: NONE
    lifecycle: FULL_RESTART
    provenance:
      simulation_session_id: MNT-Q-EXP128-full-01
      ros_domain_id: 200
      http_port: 8040
      gz_partition: so101-mnt-q-exp128
      evidence_root: /data/work/so101-debug-mujoco-maintainability-remediation/exp128
    command: GZ_PARTITION=so101-mnt-q-exp128 python3 /tmp/so101-debug-mujoco-maintainability-remediation/run_exp126_five_run.py --experiment-id EXP-128 --session-id MNT-Q-EXP128-full-01 --domain-id 200 --port 8040 --evidence-root /data/work/so101-debug-mujoco-maintainability-remediation/exp128
    decision: PENDING
    next_experiment: EXP-129_ON_SUCCESS_ONLY
  - experiment_id: EXP-129
    status: PLANNED
    prior_experiment: EXP-128
    hypothesis: A fourth independent FULL_RESTART extends the unchanged streak.
    prediction: All common success criteria pass with consecutive_count 4.
    single_variable: NONE
    lifecycle: FULL_RESTART
    provenance:
      simulation_session_id: MNT-Q-EXP129-full-01
      ros_domain_id: 201
      http_port: 8041
      gz_partition: so101-mnt-q-exp129
      evidence_root: /data/work/so101-debug-mujoco-maintainability-remediation/exp129
    command: GZ_PARTITION=so101-mnt-q-exp129 python3 /tmp/so101-debug-mujoco-maintainability-remediation/run_exp126_five_run.py --experiment-id EXP-129 --session-id MNT-Q-EXP129-full-01 --domain-id 201 --port 8041 --evidence-root /data/work/so101-debug-mujoco-maintainability-remediation/exp129
    decision: PENDING
    next_experiment: EXP-130_ON_SUCCESS_ONLY
  - experiment_id: EXP-130
    status: PLANNED
    prior_experiment: EXP-129
    hypothesis: A fifth independent FULL_RESTART completes the unchanged streak.
    prediction: All common success criteria pass with consecutive_count 5 and qualifies the batch.
    single_variable: NONE
    lifecycle: FULL_RESTART
    provenance:
      simulation_session_id: MNT-Q-EXP130-full-01
      ros_domain_id: 202
      http_port: 8042
      gz_partition: so101-mnt-q-exp130
      evidence_root: /data/work/so101-debug-mujoco-maintainability-remediation/exp130
    command: GZ_PARTITION=so101-mnt-q-exp130 python3 /tmp/so101-debug-mujoco-maintainability-remediation/run_exp126_five_run.py --experiment-id EXP-130 --session-id MNT-Q-EXP130-full-01 --domain-id 202 --port 8042 --evidence-root /data/work/so101-debug-mujoco-maintainability-remediation/exp130
    decision: PENDING
    next_experiment: NONE_FINALIZE_BATCH_ON_SUCCESS
decision: PLANNED
```

## Checkpoint MNT-CP-037 — common five-run build and provenance gate

```yaml
checkpoint_id: MNT-CP-037
recorded_at: 2026-08-12T22:08:30+08:00
last_valid_experiment: EXP-125
preregistration_commit: f9c6fe6787d5c03c9835b5cf9c0f575deea4d1d0
batch_status: PLANNED
fresh_common_overlay:
  root: /tmp/so101-debug-mujoco-maintainability-remediation/exp126-five-run-gate
  install: /tmp/so101-debug-mujoco-maintainability-remediation/exp126-five-run-gate/install
  install_tree_sha256: 7ad7be4828e7b67b8147f4ec24cb32099e8e77859cd17f1b79a5cb21f49f01a7
  packages: [so101_teleop, so101_mujoco_support, so101_mujoco_demo_py]
  build: PASS; three packages completed from the preregistered source in a newly absent build/install root.
automated_gates:
  focused_regression: 82 passed
  full_source_pytest: 539 passed, 4 skipped
  isolated_colcon_test_result: 800 tests, 0 errors, 0 failures, 4 skipped
  ruff_check: PASS
  ruff_format_check: PASS; 128 files already formatted
  runtime_source_lock: PASS
  reset_source_lock: PASS
  frozen_behavior:
    manifest_sha256: eb42f058017252c8c9824f408982a5f29939bba41a27a32c8ad963aab61a90ed
    transport_semantics: MATCH
    protected_gazebo: MATCH
    instrumentation_diff_gate: MATCH
provenance:
  fork_commit: 738e304551b4ea6db020b466086a13db71b65607
  fork_tag_commit: 738e304551b4ea6db020b466086a13db71b65607
  fork_status: CLEAN
  fork_overlay: /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install
  project_package_prefixes:
    so101_teleop: /tmp/so101-debug-mujoco-maintainability-remediation/exp126-five-run-gate/install/so101_teleop
    so101_mujoco_support: /tmp/so101-debug-mujoco-maintainability-remediation/exp126-five-run-gate/install/so101_mujoco_support
    so101_mujoco_demo_py: /tmp/so101-debug-mujoco-maintainability-remediation/exp126-five-run-gate/install/so101_mujoco_demo_py
runtime_fingerprint:
  path: /tmp/so101-debug-mujoco-maintainability-remediation/exp126-five-run-runtime-fingerprint.json
  sha256: 76d232a44949c1750a771a57d3f1026c8321637e9d41fe110fc3d72e88f4867c
  byte_identical_to_EXP_125: true
run_harness:
  path: /tmp/so101-debug-mujoco-maintainability-remediation/run_exp126_five_run.py
  sha256: b90ff4d8ccf4b87aef7796d4125a1c907e9321d2c6ad826c903807b79bf14054
  contract: Parameter-only run identity; one stack start, one workflow/reset transaction, lossless transport validation, owner-manifest/artifact validation, forbidden-intervention validation, fresh CUA hold point, and ordered shutdown.
audit_artifacts:
  colcon_test_result:
    path: /tmp/so101-debug-mujoco-maintainability-remediation/exp126-five-run-gate/logs/colcon-test-result.txt
    sha256: d2a5d7dd2631d3e8839cb3a1270bcb3d886aa97097a9537baba6cfea33a418f6
  runtime_source_lock:
    path: /tmp/so101-debug-mujoco-maintainability-remediation/exp126-five-run-gate/logs/runtime-source-lock.json
    sha256: 62dd76ed9c32895c43341121d3461b2d168db0e6d5e5d360102ac2f706a89b9b
  reset_source_lock:
    path: /tmp/so101-debug-mujoco-maintainability-remediation/exp126-five-run-gate/logs/reset-source-lock.json
    sha256: 4a0c3d0705f3a980cbe8c21f83e0dfd08ea4399cca1fe187fe3010aa7051f761
  frozen_behavior:
    path: /tmp/so101-debug-mujoco-maintainability-remediation/exp126-five-run-gate/logs/frozen-behavior.json
    sha256: b7447ae8187668fe176868d1f87e284c3d9e132d876c93bd1ddfac7629e77edf
invalid_pre_run_audit_attempts:
  - Focused source pytest before the fresh overlay build could not collect generated so101_mujoco_support messages. This was an environment-invalid pre-build audit, not a product test result; the same focused suite passed 82 tests after the required fresh build.
  - The first reset-lock capture used a nonexistent lock filename, then the authoritative config/dependency-lock.yaml command passed and was saved above.
protected_state:
  src_so101_gazebo_demo_py_diff: NONE
  preserved_untracked_user_files:
    - docs/experiments/so101-gazebo-mujoco-policy-parity-solver-iters-ledger.md
    - docs/experiments/so101-mujoco-ros2-migration-experiment-summary.md
owned_processes: NONE
decision: PASS; EXP-126 may transition from PLANNED to RUNNING after this checkpoint is committed.
next_experiment: EXP-126
```

## Checkpoint MNT-CP-038 — EXP-126 RUNNING transition

```yaml
checkpoint_id: MNT-CP-038
recorded_at: 2026-08-12T22:08:12+08:00
experiment_id: EXP-126
status_transition: PLANNED -> RUNNING
prior_experiment: EXP-125
consecutive_successes_before_run: 0
preregistered_identity:
  simulation_session_id: MNT-Q-EXP126-full-01
  ros_domain_id: 198
  http_port: 8038
  gz_partition: so101-mnt-q-exp126
  evidence_root: /data/work/so101-debug-mujoco-maintainability-remediation/exp126
lifecycle: FULL_RESTART
workflow_invocations: 1
reset_transactions: 1
retry_count: 0
pre_run_gate_commit: 98a0689a2e587a1b6822ad6863b6f384fe32e30b
common_overlay: /tmp/so101-debug-mujoco-maintainability-remediation/exp126-five-run-gate/install
runtime_fingerprint_sha256: 76d232a44949c1750a771a57d3f1026c8321637e9d41fe110fc3d72e88f4867c
harness_sha256: b90ff4d8ccf4b87aef7796d4125a1c907e9321d2c6ad826c903807b79bf14054
preflight:
  domain_198_nodes: NONE
  port_8038_listener: NONE
  tmux_session_so101_mnt_q_exp126: ABSENT
  evidence_root: ABSENT
  relevant_processes: NONE
decision: RUN exactly one preregistered natural workflow and stop on any non-success terminal result.
```

## EXP-126 — physical success, INVALID visual artifact

```yaml
experiment_id: EXP-126
recorded_at: 2026-08-12T22:17:30+08:00
status: INVALID
validity_reason: The persisted CUA file is truncated and cannot be decoded as a complete PNG, so the preregistered fresh visual proof is missing even though the CUA observer reported all required claims true.
simulation_session_id: MNT-Q-EXP126-full-01
ros_domain_id: 198
http_port: 8038
gz_partition: so101-mnt-q-exp126
lifecycle: FULL_RESTART
workflow_invocations: 1
reset_transactions: 1
retry_count: 0
raw_harness_terminal_status: SUCCESS
workflow:
  reset_epoch: 1
  simulation_step_after_reset: 0
  owner_manifest_status: DONE
  completed_phases: [staged_approach, contact_hold, micro_lift, policy_lift_waypoint1, remaining_lift, transport, descend, place_alignment, release_retreat]
  phase_exit_codes: ALL_ZERO
physical_outcome:
  primary_failure: null
  final_xyz_m: [-0.0801261296279476, -0.2479513821234971, 0.1652618054705255]
  final_upright_tilt_rad: 0.015663107523971126
  maximum_linear_speed_m_s: 0.0
  maximum_angular_speed_rad_s: 0.0
  support_contact: true
  gripper_contact: false
  moveit_attached: false
  world_object_synchronized: true
  direct_object_state_writes: 0
  physics_pause_calls: 0
  simulator_constraint_calls: 0
transport_raw_evidence:
  chunk_count: 741
  sample_count: 3705
  first_physics_step: 25121
  last_physics_step: 28825
  physics_timestep_s: 0.002
  lossless: true
  run_index_sha256: c7853a24f84c3b4191768fe03bc6c45acb69d941be28318e99e4e40c8804419a
owner_evidence:
  manifest_sha256: 67dd97b3d30553342413a2e3a9aaa015e0b66dcefb4d7b63b872bb2b05a49439
  release_retreat_sha256: 5f79d825510d11f9e5bce484f9470a0337263df4f74eb64bb08e264693aafb5d
visual_observer_report:
  required_claims_reported_true: true
  auxiliary_rviz_window_available: false
  screenshot: /data/work/so101-debug-mujoco-maintainability-remediation/exp126/cua-visual.png
  screenshot_sha256: 798b10ac412a161adf08c49eca57349ccdd0578ae048e4b71e5905ec9860ef93
visual_artifact_integrity:
  file_identification: PNG image data, 5120 x 2880, 8-bit/color RGBA, non-interlaced
  file_size_bytes: 2304
  independent_decode: FAIL
  decoder_error: OSError; Truncated File Read
  consequence: Hash agreement proves only byte identity with the verdict, not that the bytes form a complete inspectable image.
shutdown:
  ordered_marker: true
  returncode: 0
  fatal_signal: false
  process_died: false
  domain_198_nodes_after_stop: NONE
  port_8038_listener_after_stop: NONE
  tmux_session_after_stop: NONE
  owned_process_residue: NONE
artifacts:
  result: /data/work/so101-debug-mujoco-maintainability-remediation/exp126/exp-126-result.json
  result_sha256: 26cd994123775e9b4be456c501243282a05ea8b9ddb2460405626d1ce76bd693
  visual_verdict: /data/work/so101-debug-mujoco-maintainability-remediation/exp126/cua-visual-verdict.json
  visual_verdict_sha256: 490b0849ca21d18c6776da85a8d0a4db4771cde5fe5ea16d02dea048e1f98cbf
decision: INVALID; stop the five-run batch under the preregistered stop rule. Do not count the physical success and do not rerun EXP-126.
next_experiment: NONE_BATCH_STOPPED_INVALID
```

## Checkpoint MNT-CP-039 — five-run batch stopped at EXP-126

```yaml
checkpoint_id: MNT-CP-039
recorded_at: 2026-08-12T22:17:30+08:00
last_valid_experiment: EXP-125
batch_id: MNT-Q-EXP126-130
batch_status: INVALID_STOPPED
consecutive_valid_successes: 0
terminal_experiment: EXP-126
terminal_classification: INVALID
stop_rule_applied: true
not_started: [EXP-127, EXP-128, EXP-129, EXP-130]
confirmed_new_information:
  - The frozen strategy again completed all nine physical phases with lossless 500 Hz transport evidence and no forbidden intervention.
  - The CUA persistence route can produce a hash-consistent but truncated PNG; independent image decoding is therefore required before accepting future visual evidence.
protected_state:
  src_so101_gazebo_demo_py_diff: NONE
  preserved_untracked_user_files:
    - docs/experiments/so101-gazebo-mujoco-policy-parity-solver-iters-ledger.md
    - docs/experiments/so101-mujoco-ros2-migration-experiment-summary.md
owned_processes: NONE
preserved_processes: Existing codex, idle codex-cua, and historical so101-mujoco-gui tmux sessions only.
next_command: Stop and report the invalid batch. A new explicitly authorized preregistration is required before any further qualification run.
```

## Correction and authorization addendum — EXP-126 visual waiver and batch resumption

```yaml
addendum_id: USER-AUTH-2026-08-12-EXP126-VISUAL-WAIVER
recorded_at: 2026-08-12T22:27:35+08:00
type: CORRECTION_AND_EXPLICIT_USER_AUTHORIZATION
historical_integrity:
  preserved_records:
    - EXP-126 remains historically recorded as INVALID at its original terminal decision.
    - MNT-CP-039 remains historically recorded as INVALID_STOPPED with zero counted successes at that checkpoint.
    - The EXP-126 screenshot remains truncated, independently undecodable, and unsuitable as a persisted visual artifact.
  prohibited_reinterpretation: This addendum does not repair, replace, conceal, or retrospectively validate the damaged PNG.
user_attestation:
  observer: USER
  observation_mode: Personal live observation of the EXP-126 terminal screen on ai-station.
  accepted_claims:
    - MuJoCo was Running.
    - Robot, pedestal, table, cup, and target ring were visible.
    - Cup was upright inside the target ring.
    - Gripper was open and the arm was retired clear.
  authorization: Skip only the damaged persisted screenshot requirement for EXP-126 and count the otherwise complete physical run as this batch's first VALID success.
waiver:
  waiver_scope: EXP-126_ONLY
  visual_artifact_integrity: FAIL_PRESERVED
  persisted_screenshot_accepted_as_evidence: false
  human_live_visual_attestation_accepted_for_batch_count: true
  rerun_EXP_126: PROHIBITED
  inherited_by_EXP_127_through_EXP_130: false
  expansion_without_new_user_authorization: PROHIBITED
effective_batch_correction:
  batch_id: MNT-Q-EXP126-130
  prior_checkpoint: MNT-CP-039
  prior_batch_state: INVALID_STOPPED
  resumed_batch_state: AUTHORIZED_RESUMED
  EXP_126_effective_result_for_this_batch_only: VALID_SUCCESS_BY_USER_VISUAL_WAIVER
  consecutive_valid_successes: 1
  target_consecutive_successes: 5
  remaining_experiments: [EXP-127, EXP-128, EXP-129, EXP-130]
  frozen_strategy_changed: false
future_visual_contract:
  experiments: [EXP-127, EXP-128, EXP-129, EXP-130]
  required_sequence: snapshot -> action -> fresh snapshot
  persisted_png_required: true
  independent_png_decode_before_acceptance: true
  new_damage_rule: Stop and report; do not inherit or expand the EXP-126 waiver.
decision: Resume the original preregistered batch at EXP-127 without rerunning EXP-126 and without changing motion strategy, thresholds, code, configuration, control path, or experiment criteria.
```

## Checkpoint MNT-CP-040 — authorized resumption at EXP-127

```yaml
checkpoint_id: MNT-CP-040
recorded_at: 2026-08-12T22:27:35+08:00
last_valid_experiment_for_batch: EXP-126_BY_USER_VISUAL_WAIVER
batch_id: MNT-Q-EXP126-130
batch_status: AUTHORIZED_RESUMED
consecutive_valid_successes: 1
waiver_scope: EXP-126_ONLY
execution_host: AI-STATION-001; direct local execution, no SSH
worktree:
  path: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
  linked_worktree: true
  branch: codex/so101-mujoco-ros2-teleop
  head_before_addendum: b6b4a205545418531994a2e245fb899b70f48226
  tracked_status: CLEAN
  protected_gazebo_status: ZERO_STATUS_AND_DIFF
  preserved_untracked_user_files:
    - docs/experiments/so101-gazebo-mujoco-policy-parity-solver-iters-ledger.md
    - docs/experiments/so101-mujoco-ros2-migration-experiment-summary.md
provenance:
  fork_local_commit: 738e304551b4ea6db020b466086a13db71b65607
  fork_origin_main: 738e304551b4ea6db020b466086a13db71b65607
  fork_remote_tag_peel: 738e304551b4ea6db020b466086a13db71b65607
  fork_local_vs_origin_main: {ahead: 0, behind: 0}
  fork_status: CLEAN
  common_overlay: /tmp/so101-debug-mujoco-maintainability-remediation/exp126-five-run-gate/install
  runtime_fingerprint_sha256: 76d232a44949c1750a771a57d3f1026c8321637e9d41fe110fc3d72e88f4867c
  harness_sha256: b90ff4d8ccf4b87aef7796d4125a1c907e9321d2c6ad826c903807b79bf14054
runtime_preflight:
  relevant_processes: NONE
  ros_domains_empty: [0, 198, 199, 200, 201, 202]
  free_http_ports: [8038, 8039, 8040, 8041, 8042]
  absent_evidence_roots: [exp127, exp128, exp129, exp130]
  codex_cua: IDLE_AT_ZSH_PROMPT
  preserved_tmux: [codex, codex-cua, so101-mujoco-gui]
next_experiment: EXP-127
next_command: Update EXP-127 to RUNNING after a fresh per-run provenance, dirty-state, process, domain, port, tmux, evidence-root, overlay, fingerprint, and harness preflight; commit that transition; then execute exactly its preregistered command once.
```

## Checkpoint MNT-CP-041 — EXP-127 RUNNING transition

```yaml
checkpoint_id: MNT-CP-041
recorded_at: 2026-08-12T22:30:04+08:00
experiment_id: EXP-127
status_transition: PLANNED -> RUNNING
prior_experiment: EXP-126_BY_USER_VISUAL_WAIVER
consecutive_successes_before_run: 1
waiver_inherited: false
preregistered_identity:
  simulation_session_id: MNT-Q-EXP127-full-01
  ros_domain_id: 199
  http_port: 8039
  gz_partition: so101-mnt-q-exp127
  evidence_root: /data/work/so101-debug-mujoco-maintainability-remediation/exp127
lifecycle: FULL_RESTART
workflow_invocations: 1
reset_transactions: 1
retry_count: 0
pre_run_authorization_commit: 5571004d75ec07b68e2f8f604c607b9ea6fa20ea
provenance:
  fork_local_origin_main_and_remote_tag_peel: 738e304551b4ea6db020b466086a13db71b65607
  fork_local_vs_origin_main: {ahead: 0, behind: 0}
  fork_status: CLEAN
  common_overlay: /tmp/so101-debug-mujoco-maintainability-remediation/exp126-five-run-gate/install
  project_package_prefixes:
    so101_teleop: /tmp/so101-debug-mujoco-maintainability-remediation/exp126-five-run-gate/install/so101_teleop
    so101_mujoco_support: /tmp/so101-debug-mujoco-maintainability-remediation/exp126-five-run-gate/install/so101_mujoco_support
    so101_mujoco_demo_py: /tmp/so101-debug-mujoco-maintainability-remediation/exp126-five-run-gate/install/so101_mujoco_demo_py
  runtime_fingerprint_sha256: 76d232a44949c1750a771a57d3f1026c8321637e9d41fe110fc3d72e88f4867c
  harness_sha256: b90ff4d8ccf4b87aef7796d4125a1c907e9321d2c6ad826c903807b79bf14054
preflight:
  root_status: Exactly the two protected untracked documents; index and all other tracked paths clean.
  protected_gazebo_status: ZERO_STATUS_AND_DIFF
  domain_199_nodes: NONE
  port_8039_listener: NONE
  tmux_session_so101_mnt_q_exp127: ABSENT
  evidence_root: ABSENT
  relevant_processes: NONE
  codex_cua: IDLE_AT_ZSH_PROMPT
preflight_command_corrections:
  - First read-only command stopped at a mistyped expected full HEAD value; no runtime action occurred.
  - Second read-only command stopped because zsh reserves the variable name status; no runtime action occurred.
  - Corrected read-only command passed every gate and printed EXP127_PREFLIGHT_PASS.
visual_acceptance:
  required_sequence: snapshot -> action -> fresh snapshot
  persisted_png_required: true
  independent_png_decode_before_acceptance: true
  EXP_126_waiver_applies: false
decision: RUN exactly one preregistered natural workflow and stop on any product, provenance, evidence, visual-integrity, or cleanup failure.
```

## EXP-127 — VALID FULL_RESTART success

```yaml
experiment_id: EXP-127
recorded_at: 2026-08-12T22:37:52+08:00
status: VALID
behavioral_result: SUCCESS
consecutive_successes: 2
prior_counted_success: EXP-126_BY_USER_VISUAL_WAIVER
waiver_applied: false
simulation_session_id: MNT-Q-EXP127-full-01
ros_domain_id: 199
http_port: 8039
gz_partition: so101-mnt-q-exp127
lifecycle: FULL_RESTART
workflow_invocations: 1
reset_transactions: 1
retry_count: 0
workflow:
  reset_epoch: 1
  simulation_step_after_reset: 0
  terminal_status: SUCCESS
  owner_manifest_status: DONE
  completed_phases: [staged_approach, contact_hold, micro_lift, policy_lift_waypoint1, remaining_lift, transport, descend, place_alignment, release_retreat]
  terminal_phase_statuses:
    staged_approach: CLOSE_READY
    contact_hold: CONTACT_ONLY_PROVED
    micro_lift: PHYSICAL_MICRO_LIFT_PROVED
    policy_lift_waypoint1: POLICY_LIFT_WAYPOINT1_PHYSICAL_TRANSFER_PROVED
    remaining_lift: REMAINING_FORMAL_LIFT_PROVED
    transport: FORMAL_MOVE_ABOVE_PLACE_PROVED
    descend: FORMAL_DESCEND_TO_PRE_RELEASE_CLEARANCE_PROVED
    place_alignment: PRE_RELEASE_ALIGNMENT_PROVED
    release_retreat: RELEASE_RETREAT_FINAL_PLACEMENT_PROVED
  phase_exit_codes: ALL_ZERO
phase_maximum_normal_force_n:
  contact_hold: 0.6075478496081999
  micro_lift: 0.607562898992172
  policy_lift_waypoint1: 0.7749622486255126
  remaining_lift: 0.7751705610107509
  transport: 4.9252519844336655
  descend: 4.782288947996148
  place_alignment: 4.727047822696706
  release_retreat: 4.727262284792989
  released_static_final: 0.24002329775729253
physical_outcome:
  primary_failure: null
  final_xyz_m: [-0.07897328681150646, -0.24783640578579427, 0.1653076033186954]
  final_upright_tilt_rad: 0.017010015335558515
  maximum_linear_speed_m_s: 0.0
  maximum_angular_speed_rad_s: 0.0
  support_contact: true
  gripper_contact: false
  moveit_attached: false
  world_object_synchronized: true
  planning_scene_attached_object_ids: []
  planning_scene_world_primitive_counts: {table: 1, pedestal: 1, plastic_cup: 13}
  direct_object_state_writes: 0
  physics_pause_calls: 0
  simulator_constraint_calls: 0
transport_raw_evidence:
  chunk_count: 743
  sample_count: 3715
  first_physics_step: 25421
  last_physics_step: 29135
  physics_timestep_s: 0.002
  lossless: true
  run_index_sha256: b2b79803342a1819387d57e00447587ef8a925f4be860b8e64c242ee1c21d148
visual_acceptance:
  passed: true
  required_claims_all_true: true
  screenshot: /data/work/so101-debug-mujoco-maintainability-remediation/exp127/cua-visual.png
  screenshot_sha256: 862fbe5acd34aae7242d84b6490698d8c1f58d16ddf418469d43c3fd21a80df9
  screenshot_size_bytes: 781131
  screenshot_dimensions: [5120, 2880]
  cua_png_verify_and_load: PASS
  independent_main_agent_png_verify_and_load: PASS
  main_agent_visual_review: PASS; MuJoCo Running, full scene visible, cup upright in red ring, gripper open, arm retired clear.
  auxiliary_rviz_window_available: false
shutdown:
  ordered_marker: true
  returncode: 0
  fatal_signal: false
  process_died: false
  domain_199_nodes_after_stop: NONE
  port_8039_listener_after_stop: NONE
  tmux_session_after_stop: NONE
  owned_process_residue: NONE
artifacts:
  result: /data/work/so101-debug-mujoco-maintainability-remediation/exp127/exp-127-result.json
  result_sha256: 08d5ab6029570c83fcfcfd5f970d5fac39739f5a7476101278b99765ca00f5c8
  owner_manifest_sha256: e50f7fe33bc13a74fed3d75a02d6ad5259f2553cae03664663164fc9f8ca6bd4
  release_retreat_sha256: c9be89201260ce54736c868e9de004282eb230ad8e4c17ef56c0ded92de27754
  visual_verdict_sha256: ba590d6a0f03aad3045f02a43a6ddbce3d7c302c3e9cdab7e543501a21547cea
decision: KEEP VALID success; continue only to the preregistered EXP-128 after a new full preflight and RUNNING commit.
next_experiment: EXP-128
```

## Checkpoint MNT-CP-042 — EXP-127 valid and clean

```yaml
checkpoint_id: MNT-CP-042
recorded_at: 2026-08-12T22:37:52+08:00
last_valid_experiment: EXP-127
batch_id: MNT-Q-EXP126-130
batch_status: AUTHORIZED_RUNNING
consecutive_valid_successes: 2
counted_successes: [EXP-126_BY_USER_VISUAL_WAIVER, EXP-127]
waiver_scope: EXP-126_ONLY
owned_processes: NONE
protected_state:
  src_so101_gazebo_demo_py_diff: NONE
  preserved_untracked_user_files:
    - docs/experiments/so101-gazebo-mujoco-policy-parity-solver-iters-ledger.md
    - docs/experiments/so101-mujoco-ros2-migration-experiment-summary.md
next_experiment: EXP-128
next_command: Run the complete EXP-128 preflight, transition EXP-128 from PLANNED to RUNNING in the ledger, commit the transition, and execute its preregistered command exactly once.
```
