# SO-101 Gazebo physical five-success V2 experiment ledger

```yaml
task_id: so101-physical-five-success-v2
goal: Qualify five consecutive SO-101 pick-place successes using Gazebo contact, friction, gravity, and gripper motion without Gazebo attachment.
success_contract: Fixed commit and policy; Gazebo attachment remains detached throughout the workflow; MoveIt attachment is collision shadow only; physical grasp gate passes; final upright cup center is inside the axis-aligned target box centered at [-0.080, -0.250] m with 0.010 m tolerance on each axis, stable, table-supported, free of gripper contact, Gazebo-detached, MoveIt-detached, and controllers healthy. Qualification requires five consecutive VALID RESET_WORLD successes.
worktree: /data/work/ws_moveit/.worktrees/so101-physical-five-success
branch: codex/so101-physical-five-success
base_commit: ef73c10f159c270b91748a41df9c4bac728fde80
current_commit: f31ee7af0179c7107661afbc10ba55ab48ce3cd6
evidence_root: /tmp/so101-physical-five-success-v2/
confirmed_conclusions:
  - The superseded campaign CP-RESULT-EXP-081-261 proved one RESET_WORLD physical-outcome success with Gazebo detached throughout; it did not count toward qualification.
  - CP-RESULT-EXP-099-314 proved the aligned-release branch can fail after OPEN_GRIPPER at a world-Z MoveGroup plan with error 99999.
  - CP-RESULT-EXP-100-316 proved physical grasp and every terminal condition except region membership; final y missed the unchanged upper bound by 0.0005617541 m.
  - The superseded campaign terminated at CP-TERMINAL-EXP-100-317 without a five-success streak and froze the EXP-081 implementation; this V2 campaign uses new experiment IDs and does not rewrite that history.
  - Current-main package baseline in this worktree passed 203 tests with 0 failures and 2 skipped before runtime experiments.
  - PHY5-B0-001 is a VALID current-main FULL_RESTART failure: the physical grasp gate passed, but a fixed-pad-only release onset transitioned to moving-pad contact while opening and displaced the cup 0.0245826293 m in XY before RETREAT.
  - On 2026-08-10 the user explicitly revised the final center tolerance from 0.005 m to 0.010 m and required the program gate and visual ring to change together; results under the former region remain historical evidence but cannot be mixed into the new five-success streak.
disproven_routes:
  - Counting the C++ Teleop Gazebo-attachment Reset-to-Run trials toward this physical-grasp campaign.
  - Treating the MoveIt Planning Scene shadow as Gazebo physical attachment.
  - Relaxing any physical acceptance bound without an explicit user-approved contract revision.
  - Reusing EXP-101 after the prior campaign's explicit terminal cap.
open_hypotheses:
  - H-B0: current main ef73c10 preserves the frozen EXP-081 runtime behavior after the Python source-layout refactor.
  - H-R1: the aligned-release post-open Cartesian and world-Z MoveGroup branch is a distinct first-bad boundary; using the existing fixed RETREAT with the MoveIt shadow attached until separation removes that planning failure without weakening physical gates.
  - H-R2: per-motion ros2 action CLI process startup adds timing variance that amplifies held-cup tilt and release scatter; persistent rclpy action clients may reduce that variance after H-R1 is isolated.
  - H-R0: requiring and, when necessary, boundedly reacquiring bilateral pad contact immediately before OPEN_GRIPPER prevents the moving-pad sweep observed in PHY5-B0-001 without changing the target region or penetration ceilings.
  - H-G1: the current 0.0001 m target-penetration lower bound accepts a bilateral but torsionally weak grasp; raising only that lower bound to 0.0008 m while preserving the 0.0010 m target maximum and 0.0013 m hard ceiling reduces in-gripper rotation during carry.
  - H-G2: when a bilateral contact is present but shallower than 0.8 mm, direct bounded 1 mrad tightening preserves contact topology better than fully opening and regrasping before every tightening step.
latest_checkpoint: CP-V2-PREOPEN-TILT-DOC-M9-M15-LOW-062
next_experiment: PHY5-G13-XY-ONLY-ALIGNMENT
```

```yaml
checkpoint_id: CP-V2-PREFLIGHT-001
recorded_at: 2026-08-10 Asia/Shanghai
last_valid_experiment: NONE_IN_V2
current_hypothesis: H-B0
working_tree_status: clean source tree at ef73c10; build, install, and log are ignored worktree outputs
owned_processes: NONE
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated MuJoCo worker and worktree must not be touched
confirmed_conclusions:
  - ai-station main and origin/main were both ef73c10 when this worktree was created
  - package build succeeded and package tests reported 203 passed, 2 skipped
disproven_routes:
  - inheriting old attach-based success counts
open_risks:
  - no current-main Gazebo runtime execution has been performed in this V2 campaign
next_command: preregister and execute PHY5-B0-001 after proving ROS_DOMAIN_ID 241 and GZ_PARTITION so101_phy5_v2_b0_001 are empty
```

## PHY5-B0-001 current-main FULL_RESTART baseline

```yaml
experiment_id: PHY5-B0-001
status: PLANNED
prior_experiment: EXP-100 from the superseded campaign
hypothesis: H-B0; current main ef73c10 preserves the frozen EXP-081 physical runtime behavior after the Python source-layout refactor.
prediction:
  - source, install overlay, package prefix, and installed policy provenance all resolve to this worktree
  - exactly one Gazebo, MoveIt, controller, and execute stack starts on the dedicated domain and partition
  - reset proof establishes canonical cup pose, Gazebo detached, MoveIt world-only, no finger contact, and finite arm TCP
  - the run reaches either a fully evidenced authoritative success or a VALID first-bad boundary suitable for the R1 regression
single_variable: NONE; exact current-main baseline
lifecycle: FULL_RESTART
preconditions:
  - worktree source remains clean at ef73c10
  - ROS_DOMAIN_ID 241 and GZ_PARTITION so101_phy5_v2_b0_001 are empty before launch
  - no existing Gazebo, MoveIt, RViz, controller, or pick-place process will be reused or stopped
  - package baseline remains 203 passed and 2 skipped
success_criteria:
  - workflow exit 0 and status DONE
  - physical grasp gate passes with Gazebo attachment detached
  - final physical result passes every unchanged acceptance gate
failure_criteria:
  - any valid physical-grasp, motion, planning-shadow, release, controller, or final-outcome failure with complete evidence
invalid_criteria:
  - provenance mismatch, duplicate stack or execute client, failed reset proof, missing bounded telemetry or visual evidence, stale screenshot, or uncontrolled cleanup
provenance:
  source_commit: ef73c10f159c270b91748a41df9c4bac728fde80
  install_overlay: /data/work/ws_moveit/.worktrees/so101-physical-five-success/install
  runtime_executable: /data/work/ws_moveit/.worktrees/so101-physical-five-success/install/so101_gazebo_demo_py/lib/so101_gazebo_demo_py/pick_place_state_machine
  ros_domain_id: 241
  gz_partition: so101_phy5_v2_b0_001
commands:
  - command: FULL_RESTART launch, reset proof, bounded telemetry and video, then one execute from the worktree overlay
    exit_code: PENDING
observed:
  - PENDING
inferred:
  - NONE
conclusion: PENDING
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-b0-001/
decision: PENDING
next_experiment: PHY5-R1-RED if the aligned-release first-bad boundary is observed; otherwise update from the first valid boundary
```

```yaml
correction_id: CORR-PHY5-B0-001-DOMAIN-001
recorded_at: 2026-08-10 Asia/Shanghai
experiment_id: PHY5-B0-001
reason: ROS_DOMAIN_ID 241 failed the preflight before any stack or execute process started because Fast DDS reported that the calculated port was too high and the domain ID exceeded 232.
effect_on_status: experiment remains PLANNED; no runtime attempt exists and no success or failure is counted
replacement:
  ros_domain_id: 188
  gz_partition: so101_phy5_v2_b0_001
replacement_preflight:
  ros_nodes: empty
  gazebo_topics: empty
  relevant_processes: none
unchanged:
  - source commit, install overlay, runtime executable, policy, hypothesis, lifecycle, success contract, and evidence root
next_command: launch the sole FULL_RESTART stack with ROS_DOMAIN_ID 188 and GZ_PARTITION so101_phy5_v2_b0_001
```

```yaml
checkpoint_id: CP-V2-B0-RUNNING-002
recorded_at: 2026-08-10 Asia/Shanghai
experiment_id: PHY5-B0-001
status: RUNNING
orchestration_attempts_before_running:
  - INVALID_PRE_START: initial nested tmux quoting failed before directories, session, or processes were created
  - INVALID_PRE_START: temporary scripts used nounset while sourcing gui-env and ROS setup; both scripts exited before ros2 launch and left the domain and partition empty
root_cause_and_correction:
  - use dedicated temporary launch scripts instead of nested shell quoting
  - retain errexit but remove nounset because the sourced environment scripts legitimately inspect unset variables
provenance:
  source_commit: ef73c10f159c270b91748a41df9c4bac728fde80
  install_overlay: /data/work/ws_moveit/.worktrees/so101-physical-five-success/install
  runtime_executable: /data/work/ws_moveit/.worktrees/so101-physical-five-success/install/so101_gazebo_demo_py/lib/so101_gazebo_demo_py/pick_place_state_machine
  runtime_sha256: 25ac4e503f959b937d80bde1e33f05e73c1bf7ebd022ad12e055f5b8c9847afb
  motion_policy_sha256: 0656cf02ba194d415eb5aea4183591ced584519c74a3990007e17bd6566dff31
  ros_domain_id: 188
  gz_partition: so101_phy5_v2_b0_001
runtime_inventory:
  - one ros2 launch so101_gazebo.launch.py parent with one gz server and one gz gui
  - one ros2 launch so101_moveit.launch.py parent with one move_group and one rviz2 process
  - arm_controller, gripper_controller, and joint_state_broadcaster are active
  - no pick_place_state_machine execute process exists before reset
owned_processes: all children of tmux session so101-phy5-v2-b0
preserved_processes: all other tmux sessions and unrelated worktrees
next_command: run reset_so101_world with SO101_PY_EVIDENCE_DIR=/tmp/so101-physical-five-success-v2/phy5-b0-001/reset
```

```yaml
checkpoint_id: CP-V2-B0-RESULT-003
recorded_at: 2026-08-10 Asia/Shanghai
experiment_id: PHY5-B0-001
status: VALID
lifecycle: FULL_RESTART
command_exit_code: 1
reset:
  status: RESET_WORLD_PROVED
  object_pose_error_m: 0.000001689581315516809
  gazebo_attachment_state: detached
  moveit_world_objects: [plastic_cup]
  moveit_attached_objects: []
  finger_contact: false
  arm_tcp_finite: true
physical_grasp:
  status: PROVED
  attempts: 1
  moving_pad_penetration_m: 0.0009458349668420851
  hard_ceiling_m: 0.0013
  micro_lift_world_z_m: 0.002265527844429016
  lateral_drift_m: 0.00011466722183182013
  gazebo_attachment_state: detached
release:
  place_alignment_attempts: 0
  pre_retreat_outcome: null
  branch: no-alignment immediate fixed RETREAT with MoveIt shadow attached
  opening_onset_contact_topology: fixed-pad-only
  opening_onset_cup_xyz_m: [-0.07912638783454895, -0.26167115569114685, 0.18312810361385345]
  opening_onset_tilt_rad: 0.13101774045681694
  opening_onset_bottom_clearance_m: 0.013288049406977503
  release_start_to_q6_0_74_s: 1.8678353312425315
  release_start_to_q6_0_74_xy_displacement_m: 0.02458262927449087
  q6_0_74_to_retreat_motion_s: 3.4285075180232525
  q6_0_74_to_retreat_xy_displacement_m: 0.0
  retreat_motion_to_final_xy_displacement_m: 0.0
final:
  failure_code: FINAL_OUT_OF_REGION
  object_xyz_m: [-0.10487272590398788, -0.2701064348220825, 0.16499999165534973]
  upright_tilt_rad: 0.0000001541388099311085
  stable: true
  supported: true
  gripper_free: true
  gazebo_detached: true
  moveit_detached: true
  controller_healthy: true
  visual: final Gazebo frame shows the cup upright and table-supported to the negative-x/negative-y side of the target while the open gripper has retreated
comparison_to_prior_success:
  - EXP-081 and EXP-100 both had bilateral fixed-plus-moving pad contact at opening onset
  - EXP-081 opening XY displacement through q6 0.74 was 0.0000384853 m
  - EXP-100 opening XY displacement through q6 0.74 was 0.0010527049 m
  - persistent ActionClient work cannot explain or remove the PHY5-B0-001 opening displacement because all displacement completed before q6 reached 0.74 and no further displacement occurred during the 3.43 s pre-retreat delay
conclusion: H-B0 is false as a success prediction but the baseline is valid; the first bad physical boundary is release-onset contact topology and cup displacement during OPEN_GRIPPER, not post-open MoveGroup planning or RETREAT timing
evidence:
  reset_sha256: a04acf11a7522bba33e09f8d211b6f40ab44efd6f710ed9615e0019b93e8ef0c
  execute_log_sha256: 5d2d5815c0fd4439b5f17d3de2204ef8ed1a6327337e06bc06c17e3f74e985ea
  physical_gate_sha256: 55f67ee61b9613da32da2b61b32da8872ea3ba49461c4e8c956326dea391af40
  final_failure_sha256: d53e09bfe0a191aa62e90b20ad94d4cc9a9d5aaec9575bd7865bc39ba7c663a9
  telemetry_sha256: 534bcae5975d5e2d891630d125306c8605da05fcd92374a47aae6039dddef0fa
  video_sha256: bf5f15816f5accfcb228bcac400e77c7501f7dee27e52881e0bd164fde754b16
  final_gazebo_sha256: e94be1f7bada729161e07921f06a6143c3ff3490bb0e41e24307e3d234356429
  final_rviz_sha256: 15ce904820d0350b791a04ef9757cbb01971fa954b92e1e91abadd0f9dcb93f6
decision: KEEP_EVIDENCE_AND_PIVOT_TO_H_R0
next_experiment: PHY5-R0-RED
```

## PHY5-R0 bilateral release preparation

```yaml
experiment_id: PHY5-R0-RED
status: PASSED_AUTOMATED
prior_experiment: PHY5-B0-001
hypothesis: H-R0; release must not begin from fixed-pad-only or moving-pad-only contact, and one bounded reuse of the existing seating preload can reacquire bilateral contact before OPEN_GRIPPER.
prediction:
  - a regression test fails because the current live path calls final OPEN_GRIPPER without a bilateral release-preparation gate
  - the minimal GREEN introduces no Gazebo attachment and changes no target, geometry, friction, motion waypoint, penetration ceiling, or final acceptance threshold
  - already-bilateral release passes without another gripper command
  - unilateral release commands only the existing bounded seating target, requires stable bilateral evidence, and fails closed before OPEN_GRIPPER if bilateral contact is not recovered
single_variable: pre-OPEN_GRIPPER bilateral contact preparation using the existing seating preload and hard penetration gate
lifecycle: AUTOMATED_TDD_THEN_RESET_WORLD_RUNTIME
preconditions:
  - owned PHY5-B0-001 stack is stopped before source edits or rebuild
  - current runtime evidence and hashes are frozen
success_criteria:
  - focused RED fails for the missing behavior
  - focused GREEN and full package tests pass
  - one subsequent reset-proved runtime either reaches bilateral opening onset or fails closed before opening without displacing the cup
failure_criteria:
  - tests require relaxing a safety bound, or runtime opens from unilateral contact, or the cup is displaced before the new gate can stop it
invalid_criteria:
  - dirty provenance outside the ledger/test/implementation scope, duplicate stack, wrong overlay, or missing telemetry
provenance:
  source_commit: ef73c10f159c270b91748a41df9c4bac728fde80
  install_overlay: /data/work/ws_moveit/.worktrees/so101-physical-five-success/install
  runtime_executable: PENDING_AFTER_GREEN_BUILD
  ros_domain_id: PENDING
  gz_partition: PENDING
commands:
  - command: PYTHONNOUSERSITE=1 python3 -m pytest test/test_outcome_first_continuation.py -k "bilateral_release or fixed_only_release or release_fails_closed" -q
    phase: RED
    exit_code: 1
    result: 3 failed with expected AttributeError because open_gripper_from_bilateral_release did not exist
  - command: same focused pytest after minimal implementation in sourced worktree overlay
    phase: GREEN
    exit_code: 0
    result: 3 passed, 30 deselected
  - command: colcon build --packages-select so101_gazebo_demo_py --symlink-install; colcon test --packages-select so101_gazebo_demo_py; colcon test-result --verbose
    phase: PACKAGE_VERIFICATION
    exit_code: 0
    result: build passed; 206 passed, 2 skipped, 0 failed, 0 errors
observed:
  - already-bilateral contact opens directly with no seating command
  - unilateral contact issues exactly one existing normalized seating target, requires six stable bilateral samples, then opens
  - unresolved unilateral contact raises bilateral stability timeout before any final-release command
inferred:
  - focused tests prove fail-closed command ordering; Gazebo runtime is still required to prove contact reacquisition and cup motion
conclusion: AUTOMATED_BEHAVIOR_AND_PACKAGE_TESTS_PASS; GAZEBO_RUNTIME_PENDING
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-r0/
decision: PENDING
next_experiment: PHY5-R0-RUNTIME-001 after GREEN verification
```

```yaml
checkpoint_id: CP-V2-R0-GREEN-004
recorded_at: 2026-08-10 Asia/Shanghai
experiment: PHY5-R0-RED
source_commit: ef73c10f159c270b91748a41df9c4bac728fde80 plus uncommitted scoped test and implementation
implementation:
  - add open_gripper_from_bilateral_release
  - reuse normalized_seating_target only when the immediate contact sample is unilateral
  - preserve the moving-pad penetration ceiling through _stable_bilateral
  - do not issue final OPEN_GRIPPER when stable bilateral contact is not recovered
focused_test: 3 passed, 30 deselected
package_verification: 206 passed, 2 skipped, 0 failed, 0 errors
next_command: execute preregistered PHY5-R0-RUNTIME-001
```

## PHY5-R0-RUNTIME-001 FULL_RESTART physical verification

```yaml
experiment_id: PHY5-R0-RUNTIME-001
status: FAILED_VALID
prior_experiment: PHY5-R0-RED
hypothesis: H-R0; the new release preparation either restores stable bilateral contact before opening or fails closed before the opening command, preventing the 24.58 mm opening sweep seen in PHY5-B0-001.
single_variable: pre-OPEN_GRIPPER bilateral contact preparation using the already-computed normalized seating target
lifecycle: FULL_RESTART
ros_domain_id: 189
gz_partition: so101_phy5_v2_r0_001
tmux_session: so101-phy5-v2-r0
evidence_directory: /tmp/so101-physical-five-success-v2/phy5-r0-runtime-001
preflight:
  ros_nodes: empty
  gz_topics: empty
  tmux_session: absent
  matching_processes: none except the preflight shell itself
  package_build: passed
  package_tests: 206 passed, 2 skipped, 0 failed, 0 errors
reset_proof:
  status: RESET_WORLD_PROVED
  object_pose_error_m: 0.0000006766671113859931
  gazebo_attachment_state: detached
  moveit_world_objects: [plastic_cup]
  moveit_attached_objects: []
  finger_contact: false
  arm_tcp_finite: true
success_criteria:
  - reset proof passes with Gazebo detached and MoveIt world-only membership
  - immediate pre-open evidence is stable bilateral and final opening proceeds without excessive cup displacement
  - unchanged final physical-outcome contract passes
bounded_safe_failure:
  - if bilateral contact cannot be recovered, execution raises bilateral stability timeout before final OPEN_GRIPPER and the cup is not swept by opening
failure_criteria:
  - final OPEN_GRIPPER begins from unilateral contact, cup displacement repeats during opening, or any safety/acceptance threshold is relaxed
invalid_criteria:
  - wrong overlay, duplicate stack, wrong domain/partition, missing reset proof, missing telemetry, or Gazebo attachment not detached
decision: PENDING
observed:
  physical_gate: PROVED
  moving_pad_penetration_m: 0.0002381877275183797
  lift_end_tilt_rad: 0.008083001603050994
  move_above_place_end_tilt_rad: 0.33832581569361103
  descend_to_place_end_tilt_rad: 0.8209091666932163
  pre_open_tilt_rad: 0.9017638615462458
  pre_open_contact: bilateral
  pre_open_table_contact: false
  release_start_to_q6_0_74_xy_displacement_m: 0.039386279249722454
  retreat_motion_detected: false
  terminal_error: world-Z MoveGroup planning failed 99999
inferred:
  - H-R0 is insufficient as a success condition: bilateral contact was present before opening but did not prevent rotational slip accumulated during carry
  - tilt began in MOVE_ABOVE_PLACE while airborne, then increased during DESCEND_TO_PLACE; table collision did not initiate it
  - the 0.238 mm accepted penetration provides weak rotational restraint compared with the still-unchanged 1.0 mm target maximum and 1.3 mm hard ceiling
conclusion: FIRST_BAD_BOUNDARY_IS_IN_GRIPPER_ROTATIONAL_SLIP_DURING_CARRY; POST_OPEN_MOVEGROUP_99999_IS_SECONDARY
evidence_hashes:
  reset_world_json: b807fd81fb9c57ba4cdbf5ab85fccab88a6660523711fc8d246bc040e8896304
  execute_log: f11a168f9384ab9d5179bd3f9c57c254d7898061242af53bef25f44cae0ae4d0
  physical_gate: 035633fe3124574618133c097733bc37c788c99a4958e9c205e7634bc12105df
  telemetry: 2d2c2bf141540326289a836c9e6a5e36769ea6767551c88007c29bd8cbab2e63
  video: 7b51ad2ef2e0e86e35201240ef1985790710001e7ab7c2a774c604267d209925
  release_analysis: 375695729b7a5dfb487911b85aa2e002535a82827795558965680b83ffbd6039
  final_gazebo: 4d123cc65b9f2023249737b45f33a6e0d3b34ce56fc664e5f455002026f051be
decision: KEEP_EVIDENCE_AND_PIVOT_TO_H_G1
next_experiment: PHY5-G1-RED; all further tuning runs use RESET_WORLD on the existing stack per user direction
```

```yaml
checkpoint_id: CP-V2-R0-PLAN-005
recorded_at: 2026-08-10 Asia/Shanghai
experiment: PHY5-R0-RUNTIME-001
status: PLANNED_NOT_STARTED
next_command: launch the isolated Gazebo and MoveIt stack, then prove reset before execute
```

```yaml
checkpoint_id: CP-V2-R0-RESET-006
recorded_at: 2026-08-10 Asia/Shanghai
experiment: PHY5-R0-RUNTIME-001
status: RUNNING_RESET_PROVED
reset_evidence: /tmp/so101-physical-five-success-v2/phy5-r0-runtime-001/reset/reset-world.json
next_command: execute one live physical pick-place with telemetry and Gazebo video active
```

```yaml
checkpoint_id: CP-V2-R0-RESULT-007
recorded_at: 2026-08-10 Asia/Shanghai
experiment: PHY5-R0-RUNTIME-001
status: FAILED_VALID
first_bad_boundary: rotational cup slip begins during airborne MOVE_ABOVE_PLACE despite bilateral pad contact
recovery:
  method: RESET_WORLD on the same ROS_DOMAIN_ID 189 and GZ_PARTITION so101_phy5_v2_r0_001 stack
  status: RESET_WORLD_PROVED
  object_pose_error_m: 0.0000016332951249655477
  gazebo_attachment_state: detached
  moveit_world_objects: [plastic_cup]
  moveit_attached_objects: []
  finger_contact: false
  arm_tcp_finite: true
user_constraint: do not use FULL_RESTART for tuning experiments; use RESET_WORLD
next_command: preregister and RED-test PHY5-G1 using the existing stack
```

## PHY5-G1 stronger bounded physical preload

```yaml
experiment_id: PHY5-G1-RED
status: PASSED_AUTOMATED
prior_experiment: PHY5-R0-RUNTIME-001
hypothesis: H-G1; requiring 0.8-1.0 mm stable moving-pad penetration before carry improves rotational restraint enough to keep the cup near upright through MOVE_ABOVE_PLACE and DESCEND_TO_PLACE.
single_variable: target penetration lower bound changes from 0.0001 m to 0.0008 m
unchanged_bounds:
  target_penetration_maximum_m: 0.0010
  hard_penetration_ceiling_m: 0.0013
  q6_safe_lower: -0.059600220867817
  adjustment_step_rad: 0.001
  maximum_adjustments: 4
  carry_waypoints_and_scaling: unchanged
  target_region_and_final_acceptance: unchanged
lifecycle: AUTOMATED_TDD_THEN_RESET_WORLD_RUNTIME
success_criteria:
  - RED proves the old default accepts 0.2 mm penetration without adjustment
  - GREEN and full package tests pass with the stricter lower bound
  - RESET_WORLD runtime reaches 0.8-1.0 mm without exceeding 1.3 mm and materially reduces carry tilt
failure_criteria:
  - bounded adjustment cannot reach the new target, hard ceiling is crossed, or carry tilt remains large
invalid_criteria:
  - stack restart, wrong overlay/domain/partition, missing reset proof, or any unrelated policy change
automated_results:
  red: 2 expected failures; the old 0.2 mm default contact was accepted without adjustment and the source contract still specified 0.1 mm
  focused_green: 85 passed
  package_build: passed
  package_tests: 207 passed, 2 skipped, 0 failed, 0 errors
decision: PROCEED_TO_RESET_WORLD_RUNTIME
next_experiment: PHY5-G1-RUNTIME-001 on the existing stack after GREEN
```

```yaml
checkpoint_id: CP-V2-G1-GREEN-008
recorded_at: 2026-08-10 Asia/Shanghai
experiment: PHY5-G1-RED
status: AUTOMATED_GREEN
implementation: target penetration lower bound 0.0001 m to 0.0008 m only
unchanged_safety: target maximum 0.0010 m; hard ceiling 0.0013 m; bounded q6 adjustment policy unchanged
existing_stack:
  ros_domain_id: 189
  gz_partition: so101_phy5_v2_r0_001
  restart: none
next_command: RESET_WORLD into a new evidence directory, prove state, then execute PHY5-G1-RUNTIME-001
```

## PHY5-G1-RUNTIME-001 RESET_WORLD physical verification

```yaml
experiment_id: PHY5-G1-RUNTIME-001
status: FAILED_VALID
prior_experiment: PHY5-G1-RED
lifecycle: RESET_WORLD
ros_domain_id: 189
gz_partition: so101_phy5_v2_r0_001
tmux_session: so101-phy5-v2-r0
evidence_directory: /tmp/so101-physical-five-success-v2/phy5-g1-runtime-001
single_variable: target penetration lower bound 0.0008 m
reset_proof:
  status: RESET_WORLD_PROVED
  object_pose_error_m: 0.0000017571344711155568
  gazebo_attachment_state: detached
  moveit_world_objects: [plastic_cup]
  moveit_attached_objects: []
  finger_contact: false
  arm_tcp_finite: true
success_criteria:
  - independent RESET_WORLD proof passes immediately before execute
  - physical gate records 0.0008-0.0010 m moving-pad penetration and remains below the 0.0013 m hard ceiling
  - MOVE_ABOVE_PLACE_END and DESCEND_TO_PLACE_END tilt are materially lower than 0.3383 and 0.8209 rad
  - unchanged final physical-outcome contract passes
bounded_failure:
  - fail before carry if the bounded q6 adjustments cannot reach 0.0008-0.0010 m
invalid_criteria:
  - Gazebo or MoveIt process restart, missing reset proof/telemetry, wrong overlay/domain/partition, or unrelated source/policy change
decision: PENDING
observed:
  physical_gate: PROVED
  normalized_target_q6: -0.052582551836967466
  seating_adjustments: 1
  physical_attempts: 2
  post_seating_penetration_m: 0.0009236636105924845
  gated_penetration_m: 0.0009483465692028403
  lift_end_tilt_rad: 0.24617892336657202
  move_above_place_end_tilt_rad: 0.23578722892718804
  descend_to_place_end_tilt_rad: 0.21791713115432898
  pre_open_tilt_rad: 0.29697651936718594
  release_xy_displacement_to_q6_0_74_m: 0.013076016774439467
  final_xyz_m: [-0.09686437994241714, -0.26171278953552246, 0.16499999165534973]
  final_tilt_rad: 0.00000037873581132706733
  final_supported: true
  final_gripper_contact: false
  final_gazebo_detached: true
  final_moveit_detached: true
  reported_failure_code: FINAL_STALE_EVIDENCE
inferred:
  - G1 materially reduced carry tilt versus PHY5-R0-RUNTIME-001, especially at DESCEND_TO_PLACE_END from 0.8209 to 0.2179 rad
  - the cup still settles outside the unchanged target region, so FINAL_STALE_EVIDENCE is not a false-negative success
  - the second bounded grasp attempt introduces a stochastic regrasp boundary; one unchanged RESET_WORLD replicate is needed before adding another variable
conclusion: G1_IMPROVES_ROTATIONAL_RESTRAINT_BUT_RUN_IS_NOT_SUCCESS
evidence_hashes:
  reset_world_json: 8526fbf4949a1b56dc022fa165d9f4863efe4221c94eb812844bf12a8aa765f2
  execute_log: 383405c08520bfad43346a6ea19d4282c67394d64fa3edc7c8fb5391f94c6631
  physical_gate: b1b96f30899f1df1db03e5025595da7948f7887dc7951e5208d3b16747b7ed2e
  final_failure: fc8843cf1d771184fe829f9ba068cb2bd2ad870161e8a65d3910869c8c7039c4
  telemetry: d83987acbcb2fe238a7169294dc7a482346ab2f44fedfe76ee82cee28cf175bf
  video: 8375ab12718319171a711024a5b890edcea0004c8f9b709b4ec5e35beb7f7d97
  release_analysis: 25da3d33fae0ad5a283ba983cb1320652ee298518c135f57ab816b9112c4c931
  tilt_analysis: 39a3076a29b5400e265b96efdd10ca94636145892b14a716e4f76da0f3d74e06
  final_gazebo: 6d07b0dfd9c441f364badf98c1981cc1ecf510db4221649a6f5cff364a474ec1
decision: REPLICATE_UNCHANGED_WITH_RESET_WORLD
next_experiment: PHY5-G1-RUNTIME-002; no source, policy, threshold, or stack change
```

```yaml
checkpoint_id: CP-V2-G1-RESET-009
recorded_at: 2026-08-10 Asia/Shanghai
experiment: PHY5-G1-RUNTIME-001
status: RUNNING_RESET_PROVED
stack_restart: false
reset_evidence: /tmp/so101-physical-five-success-v2/phy5-g1-runtime-001/reset/reset-world.json
next_command: start isolated recorder/video windows and execute once
```

```yaml
checkpoint_id: CP-V2-G1-RESULT-010
recorded_at: 2026-08-10 Asia/Shanghai
experiment: PHY5-G1-RUNTIME-001
status: FAILED_VALID
comparison_to_r0:
  penetration_m: 0.0002382 to 0.0009483
  descend_end_tilt_rad: 0.8209 to 0.2179
  pre_open_tilt_rad: 0.9018 to 0.2970
terminal: upright and detached but outside unchanged target region
next_command: RESET_WORLD and run unchanged PHY5-G1-RUNTIME-002 on the same stack
```

## PHY5-G1-RUNTIME-002 unchanged RESET_WORLD replicate

```yaml
experiment_id: PHY5-G1-RUNTIME-002
status: FAILED_VALID
prior_experiment: PHY5-G1-RUNTIME-001
lifecycle: RESET_WORLD
ros_domain_id: 189
gz_partition: so101_phy5_v2_r0_001
stack_restart: false
evidence_directory: /tmp/so101-physical-five-success-v2/phy5-g1-runtime-002
single_variable: none; exact replicate of G1-RUNTIME-001
purpose: determine whether G1's stronger rotational restraint and second-attempt behavior repeat before changing another variable
reset_proof:
  status: RESET_WORLD_PROVED
  object_pose_error_m: 0.0000015818269323344898
  gazebo_attachment_state: detached
  moveit_world_objects: [plastic_cup]
  moveit_attached_objects: []
  finger_contact: false
  arm_tcp_finite: true
success_criteria:
  - reset proof passes
  - penetration remains 0.0008-0.0010 m below hard ceiling
  - carry tilt remains materially below R0
  - unchanged final contract passes
observed:
  phase: POST_SEATING_PHYSICAL_STABILITY
  failure: target penetration not reached within bounded adjustments
  final_contact_topology: moving-pad-only
  final_moving_pad_penetration_m: 0.0009892367525026202
  hard_ceiling_exceeded: false
  gazebo_attachment_state: detached
  carry_started: false
conclusion: G1_IS_NOT_REPEATABLE_WITH_THE_CURRENT_FULL_PREOPEN_BEFORE_EACH_SHALLOW_CONTACT_TIGHTENING
evidence_hashes:
  reset_world_json: 7fb8421aa189228193a6dc0853997fac2b3ec981e7c83e9c9c88c32863a98c18
  execute_log: b6b64ccd14dd762a505754804c15e98a969afe4f14294356d1d6ae82d460e4ec
  physical_failure: 171f9ddde39b4c3736cb0ee0619fca7939e63d92002c1a04756503ddf0a0cd91
  telemetry: 2da4bd3a0894de4ecedabf41689a024fb9c220aff9258f573a8055cbd448ad2d
  video: afebbe7b2567e14bf25248ae4e1b1fc7c105a0a8226fc5ab79d4ba7b4a9d5122
  failure_gazebo: 1993f102eef0f94f1baad0e563feb8c5135cdd0eda08e55b7b5142e6dae4491e
  provenance: d35643b48b307e59ad9333e5f2496bd256d31da3b3538116e99e0f878c35e5e9
decision: PIVOT_TO_H_G2_WITHOUT_CHANGING_G1_DEPTH_TARGET
```

```yaml
checkpoint_id: CP-V2-G1-REPLICA-RESET-011
recorded_at: 2026-08-10 Asia/Shanghai
experiment: PHY5-G1-RUNTIME-002
status: RUNNING_RESET_PROVED
stack_restart: false
next_command: start recorder/video and execute unchanged replicate once
```

```yaml
checkpoint_id: CP-V2-G1-REPLICA-RESULT-012
recorded_at: 2026-08-10 Asia/Shanghai
experiment: PHY5-G1-RUNTIME-002
status: FAILED_VALID_SAFE_EARLY_EXIT
first_bad_boundary: full-preopen regrasp loses the fixed-pad contact while tuning penetration
next_command: RED-test direct incremental tightening for an already-bilateral shallow contact
```

## PHY5-G2 preserve bilateral topology while tightening

```yaml
experiment_id: PHY5-G2-RED
status: PASSED_AUTOMATED
prior_experiment: PHY5-G1-RUNTIME-002
hypothesis: H-G2; an already-bilateral shallow grasp should tighten directly by one bounded milliradian, without the full preopen command that can move the cup out of the fixed pad.
single_variable: remove the preopen command only from the bilateral-but-shallow adjustment branch
unchanged_behavior:
  - missing bilateral contact still uses preopen and reclose recovery
  - too-deep contact still opens by one milliradian
  - 0.8-1.0 mm target interval remains unchanged
  - 1.3 mm hard ceiling and q6 safe lower bound remain unchanged
  - carry, release, target region, and final acceptance remain unchanged
lifecycle: AUTOMATED_TDD_THEN_RESET_WORLD_RUNTIME
success_criteria:
  - RED proves current shallow-bilateral adjustment issues an unnecessary preopen
  - GREEN command sequence tightens directly and all package tests pass
  - RESET_WORLD runtime reaches stable bilateral target depth without full-preopen topology loss
automated_results:
  red: current implementation emitted [preopen, tighter_target] instead of [tighter_target]
  focused_green: 85 passed
  package_build: passed
  package_tests: 207 passed, 2 skipped, 0 failed, 0 errors
decision: PROCEED_TO_RESET_WORLD_RUNTIME
```

```yaml
checkpoint_id: CP-V2-G2-GREEN-013
recorded_at: 2026-08-10 Asia/Shanghai
experiment: PHY5-G2-RED
status: AUTOMATED_GREEN
implementation: shallow bilateral contact now tightens directly; missing-contact and too-deep branches are unchanged
stack_restart: false
next_command: RESET_WORLD and execute PHY5-G2-RUNTIME-001 on the existing stack
```

## PHY5-G2-RUNTIME-001 RESET_WORLD physical verification

```yaml
experiment_id: PHY5-G2-RUNTIME-001
status: PAUSED_AFTER_RESET_NOT_EXECUTED
prior_experiment: PHY5-G2-RED
lifecycle: RESET_WORLD
ros_domain_id: 189
gz_partition: so101_phy5_v2_r0_001
stack_restart: false
evidence_directory: /tmp/so101-physical-five-success-v2/phy5-g2-runtime-001
single_variable: direct 1 mrad tightening for a bilateral-but-shallow contact
success_criteria:
  - reset proof passes
  - stable bilateral 0.8-1.0 mm penetration is reached without full-preopen topology loss
  - physical grasp gate passes below the hard ceiling
  - carry tilt and unchanged terminal outcome are recorded
failure_criteria:
  - topology still becomes unilateral, bounded target is not reached, hard ceiling is exceeded, or final contract fails
reset_proof:
  status: RESET_WORLD_PROVED
  object_pose_error_m: 0.0000017060808514182714
  gazebo_attachment: detached
  moveit_world_objects: [plastic_cup]
  moveit_attached_objects: []
  finger_contact: none
  tcp_state: finite
execute_started: false
decision: PAUSED_FOR_TARGET_LANDING_MARKER
```

## Target landing tolerance ring

```yaml
checkpoint_id: CP-V2-TARGET-RING-014
recorded_at: 2026-08-10 Asia/Shanghai
status: IMPLEMENTED_AND_VISUALLY_VERIFIED
purpose: show a conservative landing boundary whose no-touch condition guarantees that an upright cup center is inside the unchanged target tolerance
target_center_world_m: [-0.080, -0.250]
cup_radius_m: 0.040
accepted_center_box_m:
  min: [-0.085, -0.255]
  max: [-0.075, -0.245]
conservative_center_tolerance_radius_m: 0.005
ring_inner_radius_m: 0.045
ring_line_width_m: 0.005
ring_outer_radius_m: 0.050
mesh_height_m: 0.0
render_offset_above_table_m: 0.0001
material: red
collision_geometry: none
interpretation: if the upright cup footprint does not touch the ring inner edge, the cup center radial error is less than 5 mm and is therefore inside the unchanged 10 mm by 10 mm accepted center box
implementation:
  world_visual: table/target_landing_tolerance_ring
  mesh_uri: model://so101_gazebo_demo_py/meshes/target_landing_tolerance_ring.stl
  current_stack: dynamically spawned visual-only marker without restarting Gazebo or MoveIt
verification:
  package_build: passed
  package_tests: 208 passed, 2 skipped, 0 failed, 0 errors
  git_diff_check: clean
  runtime_marker_pose_world_m: [-0.080, -0.250, 0.1201]
  screenshot: /tmp/so101-physical-five-success-v2/target-landing-tolerance-ring-v6.png
  screenshot_sha256: d75ae6dbf22c96fbc019f5f7f366bd0a0752f7568e67697723a1046694ae96bc
stack_restart: false
next_command: wait for user confirmation, then execute PHY5-G2-RUNTIME-001 from the already-proved RESET_WORLD state
```

## Revise target center tolerance and landing ring to 10 mm

```yaml
experiment_id: TARGET-RING-10MM-015
status: VALID
status_history:
  - PLANNED before the first targeted test
  - RUNNING after source, installed overlay, ROS_DOMAIN_ID 189, GZ partition, stack ownership, and paused G2 state were verified
  - VALID after RED, GREEN, build, package tests, installed-policy read-back, runtime marker replacement, and fresh visual inspection passed
prior_experiment: CP-V2-TARGET-RING-014
hypothesis: a 10 mm per-axis program tolerance can be represented conservatively by a no-touch ring whose inner radius equals the 40 mm cup radius plus 10 mm center tolerance
prediction:
  - program final target bounds become x [-0.090, -0.070] m and y [-0.260, -0.240] m
  - ring inner radius becomes 0.050 m and its unchanged 0.005 m line width gives a 0.055 m outer radius
  - an upright cup fully inside and not touching the red line has center radial error below 0.010 m and therefore passes the program's per-axis bounds
single_variable: final target center tolerance changes from 0.005 m to 0.010 m; all grasp, penetration, tilt, stability, support, contact, motion, and release gates remain unchanged
lifecycle: REUSE_STACK
preconditions:
  - PHY5-G2-RUNTIME-001 execute remains not started
  - the existing ROS_DOMAIN_ID 189 and GZ_PARTITION so101_phy5_v2_r0_001 stack remains alive
  - no Gazebo or MoveIt stack restart is performed
success_criteria:
  - RED tests fail on the old 5 mm program bounds and old 45/50 mm ring
  - GREEN tests prove the new program bounds and 50/55 mm zero-height red visual ring
  - package build and full package tests pass
  - the current Gazebo stack shows the replacement visual marker at the unchanged target center
failure_criteria:
  - any unrelated acceptance gate changes, the marker gains collision geometry, build/test regression, or visual evidence does not show the larger ring
invalid_criteria:
  - G2 execute starts, stack provenance changes, another target marker remains visible, or screenshot comes from the old marker
provenance:
  source_commit: ef73c10f159c270b91748a41df9c4bac728fde80
  install_overlay: /data/work/ws_moveit/.worktrees/so101-physical-five-success/install
  runtime_executable: /data/work/ws_moveit/.worktrees/so101-physical-five-success/install/so101_gazebo_demo_py
  ros_domain_id: 189
  gz_partition: so101_phy5_v2_r0_001
commands:
  - command: targeted policy and ring RED tests
    exit_code: 1
  - command: targeted policy and ring GREEN tests
    exit_code: 0
  - command: colcon build --packages-select so101_gazebo_demo_py --symlink-install
    exit_code: 0
  - command: PYTHONNOUSERSITE=1 colcon test --packages-select so101_gazebo_demo_py --event-handlers console_direct+
    exit_code: 0
  - command: delete the old target_landing_tolerance_marker and create its 10 mm replacement at the same pose
    exit_code: 0
  - command: fresh X11 desktop capture after marker replacement
    exit_code: 0
observed:
  - OBSERVED RED: program loaded [-0.085, -0.255] to [-0.075, -0.245] instead of the expected [-0.090, -0.260] to [-0.070, -0.240]; ring mesh minimum radius was 0.045 m instead of 0.050 m
  - OBSERVED GREEN: both targeted tests passed
  - OBSERVED package result: 210 tests, 0 errors, 0 failures, 2 skipped
  - OBSERVED installed policy read-back: min [-0.090, -0.260] m, max [-0.070, -0.240] m
  - OBSERVED source and installed config SHA-256 both 00801092af2cc5b30572389da8d4ab687124c074d4b4c8b4708c5918f2e58618
  - OBSERVED source, installed, and runtime ring mesh SHA-256 all 7650822c44a353967637f456440c1334f92b808c26c45b599a1b830a8417ff37
  - OBSERVED Gazebo model list contains exactly one target_landing_tolerance_marker at [-0.080, -0.250, 0.1201] m
  - OBSERVED fresh desktop screenshot shows the red replacement ring rendered on the table at the target location; cup and robot remained in the paused pre-run state
  - OBSERVED no G2 execute process started and no Gazebo or MoveIt restart occurred
conclusion: the program now accepts 10 mm per-axis center deviation and the visual no-touch boundary is a zero-height 50 mm inner-radius ring with unchanged 5 mm line width
evidence:
  - /tmp/so101-physical-five-success-v2/target-ring-10mm-015/red-targeted.log sha256=f22b651f6526e32709e787d84a0d79ca1e7e1b8275e52a94fbaa81e239c4aae6
  - /tmp/so101-physical-five-success-v2/target-ring-10mm-015/green-targeted.log sha256=e8b12eb9c14e20ba6d6f42d6a6564099a0106363b2d2c716df325fb3a6e8b6f6
  - /tmp/so101-physical-five-success-v2/target-ring-10mm-015/colcon-build.log sha256=a8ccba92c2df47c85a269ba230c223bc310d5662e3dee97e0f3604d5a9a44dd2
  - /tmp/so101-physical-five-success-v2/target-ring-10mm-015/colcon-test.log sha256=2391397ed4d00e72b0075f5d3c3ab7f53e1fee9fa4091fa7e221624dedc72580
  - /tmp/so101-physical-five-success-v2/target-ring-10mm-015/desktop-ring-10mm.png sha256=4c176fa3cf9eb046608573daad810ee2c4921fe179f5ec60fc422d5a1d63a338
decision: KEEP
next_experiment: PHY5-G2-RUNTIME-001_PAUSED_AFTER_RESET
```

```yaml
checkpoint_id: CP-V2-TARGET-RING-10MM-015
recorded_at: 2026-08-10 22:31:24 CST
last_valid_experiment: TARGET-RING-10MM-015
current_hypothesis: H-G2 remains pending runtime execution under the revised target contract
working_tree_status: expected dirty physical-policy implementation plus target config, world visual, ring STL, tests, provenance, and this ledger; git diff --check clean
owned_processes: tmux so101-phy5-v2-r0 with Gazebo and MoveIt, ROS_DOMAIN_ID 189, GZ_PARTITION so101_phy5_v2_r0_001
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes remain untouched
confirmed_conclusions:
  - target center tolerance is now 0.010 m per axis in the installed runtime policy
  - the red marker has 0.050 m inner radius, 0.005 m line width, zero mesh height, and no collision geometry
  - current stack contains the replacement marker without a restart and G2 execute remains not started
disproven_routes:
  - visual-only resizing without changing the installed physical-outcome policy
  - retaining the 45 mm inner ring after increasing the center tolerance
open_risks:
  - five consecutive RESET_WORLD physical successes have not started under the revised target contract
next_command: wait for user continuation, then execute PHY5-G2-RUNTIME-001 from a freshly proved RESET_WORLD state without FULL_RESTART
```

## PHY5-G2-RUNTIME-002 revised-contract RESET_WORLD physical verification

```yaml
experiment_id: PHY5-G2-RUNTIME-002
status: VALID
prior_experiment: PHY5-G2-RUNTIME-001
correction:
  - PHY5-G2-RUNTIME-001 was reset-proved but never executed; its reset evidence predates TARGET-RING-10MM-015 and is not reused
  - this new experiment ID binds the runtime trial to the revised 0.010 m per-axis target contract and a fresh RESET_WORLD proof
hypothesis: H-G2; direct bounded 1 mrad tightening of an already-bilateral shallow grasp preserves both-pad topology long enough to reach the 0.8-1.0 mm target penetration and carry the cup to release.
prediction:
  - a fresh RESET_WORLD proves canonical detached, contact-free initial state on the existing stack
  - grasp stabilization reaches bilateral 0.8-1.0 mm penetration without a full-preopen topology loss
  - if the run reaches OPEN_GRIPPER, bounded telemetry distinguishes pre-existing carry tilt from displacement caused during the unchanged q6=0.750 release
single_variable: direct 1 mrad tightening for a bilateral-but-shallow contact; no release, waypoint, target, settling, material, controller, or lifecycle change
lifecycle: RESET_WORLD
preconditions:
  - reuse exactly the existing tmux so101-phy5-v2-r0 Gazebo and MoveIt stack
  - ROS_DOMAIN_ID 189 and GZ_PARTITION so101_phy5_v2_r0_001 remain unchanged
  - no other live execute or diagnostic recorder is present
  - source and installed policy/config provenance resolve to the isolated worktree
success_criteria:
  - reset proof passes with canonical cup pose, Gazebo detached, MoveIt world-only, no finger contact, and finite TCP
  - stable bilateral penetration reaches 0.0008-0.0010 m below the 0.0013 m hard ceiling
  - physical grasp gate passes and the run records carry, release, and final physical outcome
failure_criteria:
  - any valid topology loss, penetration gate failure, motion failure, release sweep, or final acceptance failure with complete evidence
invalid_criteria:
  - provenance mismatch, duplicate execute/stack, failed reset proof, missing telemetry/video/log, stale evidence reuse, or any FULL_RESTART
provenance:
  source_commit: ef73c10f159c270b91748a41df9c4bac728fde80
  install_overlay: /data/work/ws_moveit/.worktrees/so101-physical-five-success/install
  runtime_executable: /data/work/ws_moveit/.worktrees/so101-physical-five-success/install/so101_gazebo_demo_py
  ros_domain_id: 189
  gz_partition: so101_phy5_v2_r0_001
commands:
  - command: /tmp/so101-physical-five-success-v2/phy5-g2-runtime-002/run-phy5-g2-002-reset.zsh
    exit_code: 0
  - command: start bounded recorder/video, then /tmp/so101-physical-five-success-v2/phy5-g2-runtime-002/run-phy5-g2-002-execute.zsh
    exit_code: 1
observed:
  - OBSERVED RESET_WORLD_PROVED with 0.0000016831024184418815 m object-pose error, Gazebo detached, MoveIt world-only plastic_cup, no finger contact, and finite TCP
  - OBSERVED source/runtime live_execute SHA-256 match; source/installed policy and target-ring hashes match; package prefix resolves to the isolated worktree
  - OBSERVED arm, gripper, and joint-state controllers active; one owned Gazebo/MoveIt/RViz stack and no execute or diagnostic process
  - OBSERVED G2 reached stable bilateral 0.0009153993451036513 m post-seating moving-pad penetration with one direct-tightening adjustment and stayed below the 0.0013 m hard ceiling
  - OBSERVED the current physical gate passed despite 0.004223085748530782 m micro-lift lateral drift; the prior carried G1 run measured only 0.0003970497095406248 m
  - OBSERVED during LIFT cup height peaked at 0.1970781832933426 m, 0.03207892179489136 m above first-close height; bilateral contact ended at wall_s 2698655.924552181 and sustained finger-contact loss followed 0.060926372185349464 s later as the cup landed on the table
  - OBSERVED the arm reached the unchanged LIFT endpoint within 0.000000875827466328911 rad while the cup remained table-supported without finger contact; it later reached MOVE_ABOVE_PLACE and DESCEND_TO_PLACE without carrying the cup
  - OBSERVED the downstream error was place alignment correction exceeds bound with delta [-0.08561669737100601, 0.020785714387893672, 0.014000351071357747]
  - OBSERVED OPEN_GRIPPER was not reached; release_q6=0.750 was not exercised
  - OBSERVED after failure Gazebo remained detached, MoveIt retained plastic_cup as a gripper-attached collision shadow, and all controllers remained active
  - OBSERVED fresh Gazebo screenshots and video frames show the cup left on the pick side of the table while the arm finishes at the place-side pose
inferred:
  - INFERRED the place-alignment error is a downstream detector, not the first bad physical boundary; the first bad boundary is loss of the moving-pad load path during LIFT after a high-drift micro-lift false-positive
  - INFERRED direct tightening solves the G1-replica full-preopen topology loss, but the current 6 mm lateral-drift gate is too permissive to select a carry-stable grasp
conclusion: H-G2 is partially supported for penetration normalization but false as a carry-to-release prediction; this run is a VALID pre-release carry failure and contributes no qualification success
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g2-runtime-002
  - /tmp/so101-physical-five-success-v2/phy5-g2-runtime-002/provenance.txt
  - /tmp/so101-physical-five-success-v2/phy5-g2-runtime-002/reset/reset-world.json sha256=c920f50cba0c1901ebac8f5587ee2513d6fa93d2be5908193f308e36a574ea83
  - /tmp/so101-physical-five-success-v2/phy5-g2-runtime-002/reset-gazebo.png sha256=14721d01180f8d6d5b4940408458fa1db422f1edfcafadb2d35ad20af1ce3669
  - /tmp/so101-physical-five-success-v2/phy5-g2-runtime-002/run/execute.log sha256=3780ce6490861b30b51b8147733ed49f1b3e49ea2971842cbc81c31440e093c7
  - /tmp/so101-physical-five-success-v2/phy5-g2-runtime-002/run/physical-gate.json sha256=75c7d00600b0cf02629a64df3f184e8911a4226444e0de60f5df8f0195a21b3f
  - /tmp/so101-physical-five-success-v2/phy5-g2-runtime-002/run/diagnostic/samples.jsonl sha256=2cb6c4b28228e437ac0ce64f764921f699cc5f54cf35f8f319ada732a45cca70
  - /tmp/so101-physical-five-success-v2/phy5-g2-runtime-002/run/diagnostic/gazebo-gui.mp4 sha256=66fd2dcc4801a85c0fdd54fcf29d52002c5d6abf19daa34d9108ec5c22a499f9
  - /tmp/so101-physical-five-success-v2/phy5-g2-runtime-002/carry-analysis.json sha256=8105b575f76774c75dee23e349a540e3a5242cd065c486140d2c56e8e5e7a370
  - /tmp/so101-physical-five-success-v2/phy5-g2-runtime-002/planning-scene-after-failure.json sha256=ed53ba4237090654f9af90202ac1e030893ea069fca36b63b194b0ef59e00000
  - /tmp/so101-physical-five-success-v2/phy5-g2-runtime-002/failure-gazebo.png sha256=829771ebb649af59201912eca2de6ea062dcf380bad3153994993e9fcd37a8bc
decision: KEEP_DIRECT_TIGHTENING_AND_RESTORE_1MM_MICRO_LIFT_LATERAL_GATE
next_experiment: PHY5-G3-RED; do not modify release_q6 because OPEN_GRIPPER was not reached
```

```yaml
checkpoint_id: CP-V2-G2-RUNTIME-002-PLANNED-016
recorded_at: 2026-08-10 Asia/Shanghai
last_valid_experiment: TARGET-RING-10MM-015
current_hypothesis: H-G2
working_tree_status: expected dirty physical-policy implementation plus target config, world visual, ring STL, tests, provenance, and this ledger; all preserved
owned_processes: existing tmux so101-phy5-v2-r0 Gazebo and MoveIt stack only; no execute process
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes must not be touched
confirmed_conclusions:
  - current installed target tolerance is 0.010 m per axis and its visual marker is present
  - current package prefix resolves to the isolated worktree and controllers are active
disproven_routes:
  - reusing the stale pre-contract-change RESET_WORLD proof from PHY5-G2-RUNTIME-001
open_risks:
  - H-G2 has not yet been executed under the revised target contract
next_command: create the new evidence directory and run fresh RESET_WORLD on the existing stack
```

```yaml
checkpoint_id: CP-V2-G2-RUNTIME-002-RESET-PROVED-017
recorded_at: 2026-08-10 23:06:14 CST
last_valid_experiment: TARGET-RING-10MM-015
current_hypothesis: H-G2
working_tree_status: expected dirty G2 implementation, target contract and marker changes, tests, provenance, and ledger; no paths cleaned or overwritten
owned_processes: unchanged tmux so101-phy5-v2-r0 Gazebo and MoveIt stack; no execute, recorder, or video process yet
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes untouched
confirmed_conclusions:
  - fresh RESET_WORLD proof is valid under the revised 0.010 m target contract
  - source/runtime module, installed policy, marker, ROS domain, Gazebo partition, controllers, and stack ownership are aligned
disproven_routes:
  - reusing PHY5-G2-RUNTIME-001 reset evidence
open_risks:
  - the first live boundary for G2 remains unobserved
next_command: start recorder and Gazebo-window video in owned tmux windows, then start exactly one G2 execute
```

```yaml
checkpoint_id: CP-V2-G2-RUNTIME-002-RESULT-018
recorded_at: 2026-08-10 Asia/Shanghai
last_valid_experiment: PHY5-G2-RUNTIME-002
current_hypothesis: H-G3; a 1 mm micro-lift lateral-drift gate rejects the observed off-center grasp and activates the existing bounded regrasp before carry
working_tree_status: expected dirty G2 implementation, target contract and marker changes, tests, provenance, and ledger; no user paths cleaned or overwritten
owned_processes: tmux so101-phy5-v2-r0 Gazebo and MoveIt only; G2 execute, recorder, and video processes ended
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes untouched
confirmed_conclusions:
  - G2 direct tightening reaches the intended bilateral penetration without the G1-replica full-preopen loss
  - 4.223 mm micro-lift lateral drift predicts a failed LIFT; the current 6 mm gate admitted it
  - OPEN_GRIPPER was not reached, so release-q6 work is not authorized by the decision rule
  - historical EXP-089 and EXP-090 independently observed the same high-drift carry-failure boundary and showed that a 1 mm gate activates the existing bounded regrasp path
disproven_routes:
  - treating 0.8-1.0 mm penetration alone as sufficient proof of carry stability
  - diagnosing the downstream place-alignment exception as the first physical failure
open_risks:
  - the current path lacks the later historical one-second held micro-lift check, so an instantaneous 1 mm gate may still admit a transient grasp
  - Planning Scene retains the failed run's attached shadow until the next RESET_WORLD proof
next_command: preregister PHY5-G3-RED and TDD only maximum_lateral_drift_m from 0.006 to 0.001; keep G2 tightening, target, motion, release, and physics unchanged
```

## PHY5-G3 reject high-drift micro-lift before carry

```yaml
experiment_id: PHY5-G3-RED
status: PASSED_AUTOMATED
prior_experiment: PHY5-G2-RUNTIME-002
hypothesis: H-G3; the 4.223 mm micro-lift lateral drift is an early outcome signal for the later LIFT contact loss, and restoring the historical 1 mm live gate will reject that grasp and activate the existing second bounded attempt before carry.
prediction:
  - a focused regression reproducing G2's 4.223 mm lateral drift fails against the current 6 mm live gate
  - changing only verify_physical_micro_lift maximum_lateral_drift_m from 0.006 to 0.001 makes that regression pass
  - existing tests prove sub-1 mm positive-progress behavior and the bounded retry sequence remain accepted
  - after rebuild and fresh RESET_WORLD, an EXP-089/G2-like first attempt is rejected before carry; only a selected attempt at or below 1 mm may proceed
single_variable: verify_physical_micro_lift maximum_lateral_drift_m changes from 0.006 m to 0.001 m
lifecycle: AUTOMATED_TDD_THEN_RESET_WORLD_RUNTIME
historical_reference:
  - superseded EXP-089 observed 3.886 mm drift before a carry/place failure
  - superseded EXP-090 already validated the same 1 mm boundary and existing bounded regrasp path; G3 reapplies that isolated gate to the current G2 plus 10 mm-target candidate rather than claiming a novel mechanism
unchanged:
  - G2 direct 1 mrad tightening and 0.8-1.0 mm penetration target
  - 1.3 mm hard penetration ceiling, q6 lower bound, and two-attempt budget
  - no one-second held micro-lift is added in this experiment
  - all arm waypoints, speeds, target region, release q6, final outcome, physics, materials, controllers, and RESET_WORLD lifecycle
success_criteria:
  - RED fails for the current live 6 mm gate
  - GREEN focused tests, build, and full package tests pass
  - runtime either rejects a high-drift attempt before carry or selects a <=1 mm attempt and advances to a fully evidenced next boundary
failure_criteria:
  - regression remains green before the code change, unrelated behavior changes, bounded retry is bypassed, or runtime admits >1 mm drift
invalid_criteria:
  - provenance mismatch, failed RESET_WORLD proof, duplicate stack/execute, missing telemetry, or any FULL_RESTART
commands:
  - command: focused regression with correctly sourced worktree overlay before implementation
    exit_code: 1
  - command: focused regression and full test_outcome_first_continuation.py after one-line implementation
    exit_code: 0
  - command: colcon build and full so101_gazebo_demo_py package test/result
    exit_code: 0
automated_results:
  invalid_setup_attempt: direct PYTHONPATH=src collection failed with exit 2 and is excluded from RED evidence
  red: focused regression failed because the current live gate did not raise for 0.004223 m lateral drift
  focused_green: 1 passed, 33 deselected
  owning_test_file_green: 34 passed
  package_build: 1 package finished
  package_tests: 209 passed, 2 skipped, 0 failed, 0 errors
  runtime_module_sha256: ada0b0cd55df26f7b263ce159b734fdc0ad407b0aaef2f73095fd0bf25fb5ec7
  source_runtime_hash_match: true
  git_diff_check: clean
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g3-red/red-focused-overlay.log sha256=d73bc037f9709ad969194f14244c8a5ef428298f4704168a95aa941bd4d7d956
  - /tmp/so101-physical-five-success-v2/phy5-g3-red/green-focused.log sha256=f8c8763c3c3ecb5a53efa45ad05902fafdadc5f1de7bc8e392927959ebf05611
  - /tmp/so101-physical-five-success-v2/phy5-g3-red/green-file.log sha256=3a5419b3d44f2063492f9d14c4021edc19b05c528534bac0effa4215055fc17e
  - /tmp/so101-physical-five-success-v2/phy5-g3-red/colcon-build.log sha256=05e739c769ecf7aadbaa62d8f505351714bd775e78eb91c0abf2c7ae4b13e89c
  - /tmp/so101-physical-five-success-v2/phy5-g3-red/colcon-test.log sha256=1b2d07fc5f62efdf14a7eea8fb79615f871ecd6654ea7a77e69f462dc1f2e79b
  - /tmp/so101-physical-five-success-v2/phy5-g3-red/colcon-test-result.log sha256=5db74eb19ee8351d8d03865ac4e4bd0a3e056ae7af442cfc3cb1fdd74bcea61a
decision: PROCEED_TO_RESET_WORLD_RUNTIME
next_experiment: PHY5-G3-RUNTIME-001 after automated GREEN
```

```yaml
checkpoint_id: CP-V2-G3-PLANNED-019
recorded_at: 2026-08-10 Asia/Shanghai
last_valid_experiment: PHY5-G2-RUNTIME-002
current_hypothesis: H-G3
working_tree_status: expected dirty G2, target marker/contract, tests, provenance, and ledger changes; no cleanup performed
owned_processes: existing tmux so101-phy5-v2-r0 Gazebo and MoveIt only
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes untouched
confirmed_conclusions:
  - the next test is the earliest observable false-positive gate, not release or place compensation
disproven_routes:
  - release_q6 change before a run reaches OPEN_GRIPPER
open_risks:
  - a <=1 mm instantaneous result may still be transient because held validation is intentionally out of scope for G3
next_command: add and run the focused G2-drift regression before modifying live_execute.py
```

```yaml
checkpoint_id: CP-V2-G3-GREEN-020
recorded_at: 2026-08-10 Asia/Shanghai
last_valid_experiment: PHY5-G2-RUNTIME-002
current_hypothesis: H-G3
working_tree_status: expected dirty G2 plus G3 live gate, target contract/marker, tests, provenance, and ledger; git diff --check clean
owned_processes: existing tmux so101-phy5-v2-r0 Gazebo and MoveIt only
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes untouched
confirmed_conclusions:
  - RED/GREEN proves the live gate now rejects G2's measured 4.223 mm drift at the earliest outcome boundary
  - full package result is 211 tests, 0 errors, 0 failures, 2 skipped
disproven_routes:
  - treating the invalid unsourced collection error as a regression RED
open_risks:
  - live retry behavior with G2 direct tightening and the revised target contract remains unverified
next_command: preregister PHY5-G3-RUNTIME-001, then fresh RESET_WORLD on the existing stack
```

## PHY5-G3-RUNTIME-001 one-millimetre gate physical verification

```yaml
experiment_id: PHY5-G3-RUNTIME-001
status: VALID
prior_experiment: PHY5-G3-RED
hypothesis: H-G3; the one-millimetre micro-lift lateral gate rejects off-center grasps like G2 and allows only a carry-stable selected attempt to proceed.
prediction:
  - fresh RESET_WORLD clears the failed run's attached Planning Scene shadow and restores canonical detached state
  - an attempt with lateral drift above 0.001 m fails with CUP_LATERAL_DRIFT and activates the existing second bounded attempt
  - any attempt proceeding to LIFT has lateral drift at or below 0.001 m; telemetry determines whether instantaneous gating is sufficient or a held check is next
single_variable: maximum micro-lift lateral drift 0.006 m to 0.001 m; all G2 and target-contract changes retained
lifecycle: RESET_WORLD
preconditions:
  - reuse only tmux so101-phy5-v2-r0 on ROS_DOMAIN_ID 189 and GZ_PARTITION so101_phy5_v2_r0_001
  - no execute, recorder, or video process remains
  - fresh reset proves cup canonical, Gazebo detached, MoveIt world-only, no finger contact, and finite TCP
success_criteria:
  - no selected grasp exceeds 0.001 m micro-lift lateral drift
  - run either reaches a fully evidenced later boundary or safely rejects both bounded attempts before carry
failure_criteria:
  - gate admits more than 0.001 m drift, selected grasp loses contact during LIFT, or any later valid workflow/final-outcome failure
invalid_criteria:
  - provenance mismatch, failed reset, duplicate stack/execute, missing telemetry/video/log, stale evidence, or FULL_RESTART
commands:
  - command: /tmp/so101-physical-five-success-v2/phy5-g3-runtime-001/run-phy5-g3-001-reset.zsh
    exit_code: 0
  - command: bounded recorder/video, then one execute with session-id phy5-g3-runtime-001
    exit_code: 1
observed:
  - OBSERVED RESET_WORLD_PROVED with 0.0000015517560886057796 m object-pose error, Gazebo detached, MoveIt world-only plastic_cup, no finger contact, and finite TCP
  - OBSERVED source and runtime module SHA-256 match at ada0b0cd55df26f7b263ce159b734fdc0ad407b0aaef2f73095fd0bf25fb5ec7
  - OBSERVED source and installed target policy SHA-256 match; three controllers active; no execute/recorder/video process
  - OBSERVED physical gate selected attempt 2 with 0.00007776665133393004 m lateral drift, 0.0022053122520446777 m cup lift, bilateral contact, and 0.0010757017880678177 m moving-pad depth below the 0.0013 m hard ceiling
  - OBSERVED the selected grasp stayed bilateral through LIFT, MOVE_ABOVE_PLACE, DESCEND_TO_PLACE, alignment, and release preparation
  - OBSERVED cup tilt was 0.16305822151136357 rad at LIFT end, 0.2314343998965017 rad at MOVE_ABOVE_PLACE end, 0.29784536828470026 rad at DESCEND_TO_PLACE end, and 0.32519401975789475 rad at release start
  - OBSERVED release start center [-0.07218142598867416, -0.2551400363445282] m and q6>=0.74 center [-0.0713760256767273, -0.255668967962265] m are both inside the revised per-axis target box
  - OBSERVED opening to q6>=0.74 took 1.970227540936321 s and displaced cup XY by only 0.0009635550418765912 m; later idle displacement was 0.00012633316684125678 m
  - OBSERVED no retreat arm motion occurred; aligned release detached/synchronized the Planning Scene, then failed at world-Z MoveGroup planning error 99999
  - OBSERVED after failure Gazebo was detached, MoveIt held plastic_cup as a world object with no attached objects, and all controllers remained active
inferred:
  - INFERRED G3's 1 mm gate selected a materially stronger carry outcome and exposed the registered H-R1 post-open planning boundary
  - INFERRED q6=0.750 did not reproduce a material pad-sweep displacement in this run; reducing release q6 is not the next causal variable
conclusion: H-G3 is supported for selecting a low-drift carry grasp; this is a VALID later-boundary failure at aligned-release post-open planning and contributes no qualification success
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g3-runtime-001/provenance.txt
  - /tmp/so101-physical-five-success-v2/phy5-g3-runtime-001/reset/reset-world.json sha256=eb15cb5a4eaca207a5cecebb703097b03b4b5ab2085c7315c7f1529940dc347f
  - /tmp/so101-physical-five-success-v2/phy5-g3-runtime-001/reset-gazebo.png sha256=dfa4df322f6e3adee1559567fc72cbca1492b51099fd18bb57804e98b3b0a0a5
  - /tmp/so101-physical-five-success-v2/phy5-g3-runtime-001/run/execute.log sha256=c119243b8359127ae694ce7e31a6c5809dec318a83eaa5f8ac1e4332d4e844f5
  - /tmp/so101-physical-five-success-v2/phy5-g3-runtime-001/run/physical-gate.json sha256=5fd383a99573a251b0f3f5afa7137dd4e95395c7b1b6eb4a9d46c3ff4b5d5f27
  - /tmp/so101-physical-five-success-v2/phy5-g3-runtime-001/run/diagnostic/samples.jsonl sha256=517f747b7e4b44a92154e096b2287fbc001f65c3be06a6be881ae4b9ea13bb9e
  - /tmp/so101-physical-five-success-v2/phy5-g3-runtime-001/run/diagnostic/gazebo-gui.mp4 sha256=f0dd39eb318fed2f5c5d4ec406e6aadaae131405f47aa04ca07e45e555b3aa99
  - /tmp/so101-physical-five-success-v2/phy5-g3-runtime-001/release-analysis.json sha256=7319970742b533af40de582fb4ee22ada88a81b7b55e24d0253806ddc0787840
  - /tmp/so101-physical-five-success-v2/phy5-g3-runtime-001/tilt-analysis.json sha256=e4efedb533eb474a5da1a3f247df20b5a09b871229dd89ffe5c3ea3ae8be114c
  - /tmp/so101-physical-five-success-v2/phy5-g3-runtime-001/planning-scene-after-failure.json sha256=b05de7bb74c2ed24b97dbcba6a5b559b6c65375b2eb777b22037c4dc3f0b8b1b
  - /tmp/so101-physical-five-success-v2/phy5-g3-runtime-001/failure-gazebo.png sha256=45c605f7ee1eb620ee5cf78285e1dba3b42dabffd0d4999e326422aa16f36df8
decision: KEEP_G3_AND_PROCEED_TO_H_R1_FIXED_RETREAT
next_experiment: PHY5-R1-RED; release_q6 remains unchanged because opening displacement was 0.964 mm
```

```yaml
checkpoint_id: CP-V2-G3-RUNTIME-001-RESET-PROVED-021
recorded_at: 2026-08-10 Asia/Shanghai
last_valid_experiment: PHY5-G2-RUNTIME-002
current_hypothesis: H-G3
working_tree_status: expected dirty G2/G3, target contract/marker, tests, provenance, and ledger; no cleanup performed
owned_processes: unchanged tmux so101-phy5-v2-r0 Gazebo and MoveIt stack; no execute, recorder, or video process yet
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes untouched
confirmed_conclusions:
  - fresh RESET_WORLD cleared G2's attached Planning Scene shadow and restored canonical detached state
  - installed runtime contains the 1 mm gate and matches source
disproven_routes:
  - carrying the failed G2 scene state into G3
open_risks:
  - live bounded retry outcome remains unknown
next_command: start bounded recorder and Gazebo video, then exactly one G3 execute
```

```yaml
checkpoint_id: CP-V2-G3-RUNTIME-001-RESULT-022
recorded_at: 2026-08-10 Asia/Shanghai
last_valid_experiment: PHY5-G3-RUNTIME-001
current_hypothesis: H-R1
working_tree_status: expected dirty G2/G3, target contract/marker, tests, provenance, and ledger; no cleanup performed
owned_processes: tmux so101-phy5-v2-r0 Gazebo and MoveIt only; G3 execute, recorder, and video ended
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes untouched
confirmed_conclusions:
  - selected second grasp had 0.078 mm drift and remained bilateral through release
  - q6=0.750 opening displacement was 0.964 mm and did not leave the per-axis target box
  - aligned release still calls the known failing Cartesian/world-Z planning branch and performs no retreat motion
disproven_routes:
  - reducing release q6 as the next variable for this run
  - treating the world-Z error as caused by Gazebo attachment; Gazebo remained detached throughout
open_risks:
  - pre-open tilt is 0.325 rad; final upright settling cannot be evaluated until the gripper actually retreats
next_command: preregister and RED-test unified fixed RETREAT for aligned and unaligned releases
```

## PHY5-R1 unified fixed post-open retreat

```yaml
experiment_id: PHY5-R1-RED
status: PASSED_AUTOMATED
prior_experiment: PHY5-G3-RUNTIME-001
hypothesis: H-R1; after any release-alignment outcome, the existing fixed-joint RETREAT should execute before Planning Scene detach and final settling, avoiding the contact-adjacent Cartesian and world-Z planning failure.
prediction:
  - source-contract RED proves the aligned branch still detaches first and calls radial/world-Z MoveGroup planners
  - GREEN uses exactly the existing RETREAT waypoints and policy scaling for both aligned and unaligned paths
  - the MoveIt shadow remains attached during fixed RETREAT and is detached/synchronized only from the post-retreat Gazebo pose
  - runtime performs measurable retreat arm motion and reaches authoritative final-outcome evaluation without error 99999
single_variable: replace the aligned release detach-first radial plus world-Z retreat branch with the existing fixed-joint RETREAT-before-detach path
lifecycle: AUTOMATED_TDD_THEN_RESET_WORLD_RUNTIME
historical_reference:
  - EXP-076 and EXP-077 reproduced contact-adjacent MoveGroup error 99999
  - EXP-088 previously validated unified fixed RETREAT in the superseded route; R1 reapplies that boundary to the current G2/G3/10 mm candidate
unchanged:
  - G2 direct tightening, G3 1 mm micro-lift gate, two-attempt budget, penetration target/ceiling
  - alignment computation/tolerance, all fixed RETREAT waypoints/speed, target region, q6=0.750, physics/materials/controllers, and final outcome bounds
  - no release-q6, MOVE_TO_PLACE, target compensation, or settling change
success_criteria:
  - RED/GREEN source contracts and full package tests pass
  - RESET_WORLD runtime has retreat arm motion, Gazebo detached, MoveIt world-only after retreat, and an authoritative final outcome
failure_criteria:
  - aligned path still calls radial/world-Z planning, detaches before retreat, or any physical/final contract is weakened
invalid_criteria:
  - provenance mismatch, failed RESET_WORLD, duplicate stack/execute, missing telemetry/video/log, or FULL_RESTART
commands:
  - command: focused source-contract RED for unified fixed retreat
    exit_code: 1
  - command: focused GREEN plus owning release/final-outcome test files
    exit_code: 0
  - command: colcon build, full package test, and colcon test-result after all downstream contracts were updated
    exit_code: 0
automated_results:
  red: 2 expected failures because aligned release still branched to collect_final_outcomes_around_retreat and Cartesian/world-Z plans
  focused_green: 2 passed, 35 deselected
  owning_files_green: 43 passed
  first_package_followup: 207 passed, 2 failed, 2 skipped because two stale evidence tests still named the removed dual-epoch entrypoint
  final_package_build: 1 package finished
  final_package_tests: 209 passed, 2 skipped, 0 failed, 0 errors
  runtime_module_sha256: 3cd7db733a89aec5e2bca5c23754aa8b044fa4e8a87432b623d93a20f5456126
  source_runtime_hash_match: true
  git_diff_check: clean
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-r1-red/red-focused.log sha256=d9809d5fc20786cc258c605650353fd60a73bdd3c3ccc17a86bd6afeff812f03
  - /tmp/so101-physical-five-success-v2/phy5-r1-red/green-owning-files.log sha256=d86e2a1b7d0cdaa20a7cce8830aa7731e885a60978c6e9c6808d0e3529365e25
  - /tmp/so101-physical-five-success-v2/phy5-r1-red/colcon-build.log sha256=aa093adb8d508cbcc30e22338ea12bedd9ced03702d36962501af4f85c297027
  - /tmp/so101-physical-five-success-v2/phy5-r1-red/colcon-test-v2.log sha256=005629595b91156cdcce54d44c0d40f9b1eff42df3e89679e2a2fa2327952e30
  - /tmp/so101-physical-five-success-v2/phy5-r1-red/colcon-test-result-v2.log sha256=5db74eb19ee8351d8d03865ac4e4bd0a3e056ae7af442cfc3cb1fdd74bcea61a
decision: PROCEED_TO_RESET_WORLD_RUNTIME
next_experiment: PHY5-R1-RUNTIME-001 after automated GREEN
```

```yaml
checkpoint_id: CP-V2-R1-PLANNED-023
recorded_at: 2026-08-10 Asia/Shanghai
last_valid_experiment: PHY5-G3-RUNTIME-001
current_hypothesis: H-R1
working_tree_status: expected dirty G2/G3, target contract/marker, tests, provenance, and ledger; no cleanup performed
owned_processes: existing tmux so101-phy5-v2-r0 Gazebo and MoveIt only
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes untouched
confirmed_conclusions:
  - the next boundary is control-flow/planning after opening, not the release aperture
disproven_routes:
  - another q6 adjustment before retreat/final settling is observable
open_risks:
  - fixed retreat may expose an upright/final-region failure after the planning blocker is removed
next_command: update the two release-retreat source-contract tests and run them RED before changing live_execute.py
```

```yaml
checkpoint_id: CP-V2-R1-GREEN-024
recorded_at: 2026-08-10 Asia/Shanghai
last_valid_experiment: PHY5-G3-RUNTIME-001
current_hypothesis: H-R1
working_tree_status: expected dirty G2/G3/R1, target contract/marker, tests, provenance, and ledger; git diff --check clean
owned_processes: existing tmux so101-phy5-v2-r0 Gazebo and MoveIt only
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes untouched
confirmed_conclusions:
  - installed runtime uses one fixed RETREAT path for every alignment outcome and detaches the Planning Scene only after retreat
  - package result is 211 tests, 0 errors, 0 failures, 2 skipped
disproven_routes:
  - retaining stale source contracts for the removed aligned dual-epoch path
open_risks:
  - final physical settling and target acceptance remain unobserved with R1
next_command: preregister PHY5-R1-RUNTIME-001 and fresh RESET_WORLD on the existing stack
```

## PHY5-R1-RUNTIME-001 fixed-retreat physical verification

```yaml
experiment_id: PHY5-R1-RUNTIME-001
status: VALID
prior_experiment: PHY5-R1-RED
hypothesis: H-R1; unified fixed RETREAT removes error 99999 and exposes an authoritative post-retreat physical outcome.
prediction:
  - fresh RESET_WORLD clears G3 failure state without restarting the stack
  - G2/G3 grasp gates still select a <=1 mm drift bilateral grasp
  - after OPEN_GRIPPER, arm joints move along fixed RETREAT before Planning Scene detach
  - Gazebo remains detached, MoveIt becomes world-only after retreat, and final outcome is evaluated
single_variable: unified fixed RETREAT for aligned release; all other current candidate variables retained
lifecycle: RESET_WORLD
preconditions:
  - reuse only tmux so101-phy5-v2-r0 on ROS_DOMAIN_ID 189 and GZ_PARTITION so101_phy5_v2_r0_001
  - no execute/recorder/video process remains
  - source/runtime hash and RESET_WORLD proof pass
success_criteria:
  - no post-open world-Z/radial planning command or error 99999
  - measurable fixed RETREAT arm motion, post-retreat Planning Scene world-only, Gazebo detached
  - authoritative final outcome is present; full success requires every current final gate
failure_criteria:
  - valid grasp/carry/release/retreat/final-outcome failure with complete evidence
invalid_criteria:
  - provenance mismatch, failed reset, duplicate stack/execute, missing telemetry/video/log, stale evidence, or FULL_RESTART
commands:
  - command: /tmp/so101-physical-five-success-v2/phy5-r1-runtime-001/run-phy5-r1-001-reset.zsh
    exit_code: 0
  - command: bounded recorder/video, then one execute with session-id phy5-r1-runtime-001
    exit_code: 1
observed:
  - OBSERVED RESET_WORLD_PROVED with 0.000000456774436995216 m object-pose error, Gazebo detached, MoveIt world-only plastic_cup, no finger contact, and finite TCP
  - OBSERVED source/runtime SHA-256 match at 3cd7db733a89aec5e2bca5c23754aa8b044fa4e8a87432b623d93a20f5456126; source/installed policy hashes match
  - OBSERVED all controllers active, one owned stack, and no execute/recorder/video process
  - OBSERVED execution stopped before micro-lift: target penetration stabilization exhausted its bounded adjustments because the final stable-contact sample had fixed-finger contact only; moving-pad evidence was absent
  - OBSERVED physical-failure q6_contact=-0.0474808961, seating_target_q6=-0.0534808961, Gazebo detached; no shadow attach, carry, release, or RETREAT occurred
  - OBSERVED 232.899 s telemetry contained transient bilateral contacts, but cup XY drift reached 1.3238 mm and maximum tilt reached 0.05104 rad while the bounded seating loop searched for a stable 0.8--1.0 mm moving-pad penetration
  - OBSERVED final Gazebo scene retained the cup at the pick side and the robot at the grasp pose; this is not a target-placement observation
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-r1-runtime-001/provenance.txt
  - /tmp/so101-physical-five-success-v2/phy5-r1-runtime-001/reset/reset-world.json sha256=faac82bae53ec73c6644d8d75a458a0dd384d33061a5252ba344c9aa5d743833
  - /tmp/so101-physical-five-success-v2/phy5-r1-runtime-001/reset-gazebo.png sha256=1e117f515e5e5b72d82630aac2b573069c99d57cd5ac4f1e7aa97c28ef4d9fd7
  - /tmp/so101-physical-five-success-v2/phy5-r1-runtime-001/run/execute.log sha256=2c84eeb42a969884610ecd208ab10a1f645390f021ee40a8233d0b93f1cd1ddd
  - /tmp/so101-physical-five-success-v2/phy5-r1-runtime-001/run/physical-failure.json sha256=3b210b848060a1151db446c2c4b4bad996cff47ed6966f0646de9605708f817b
  - /tmp/so101-physical-five-success-v2/phy5-r1-runtime-001/run/diagnostic/samples.jsonl sha256=2edc6d1fef8bb63ab50a799389c57f3ea7ea1aaaebd1ee62aff4669e1f280479
  - /tmp/so101-physical-five-success-v2/phy5-r1-runtime-001/run/diagnostic/gazebo-gui.mp4 sha256=2fa0a2bc822a343d45118c53b3cafd96f242ea9d9c37249a788f52bfa3ec862b
  - /tmp/so101-physical-five-success-v2/phy5-r1-runtime-001/run/gate-analysis.json sha256=b5f739d52fb89a73fcb4fc97cbe7db249ad2b34fca071f64bda215263544de2a
  - /tmp/so101-physical-five-success-v2/phy5-r1-runtime-001/run/final-gazebo.png sha256=9da62648996f1ecc61a1777bd0aedaa97b4cdf3febfdbaa3b93a83a155ee2e06
decision: KEEP_CONFIGURATION_AND_REPEAT; the 1 mm gate correctly prevented an unstable seating sample from reaching carry, but H-R1 was not exercised
next_experiment: PHY5-R1-RUNTIME-002 with identical source/policy and a fresh RESET_WORLD
```

```yaml
checkpoint_id: CP-V2-R1-RUNTIME-001-RESET-PROVED-025
recorded_at: 2026-08-10 Asia/Shanghai
last_valid_experiment: PHY5-G3-RUNTIME-001
current_hypothesis: H-R1
working_tree_status: expected dirty G2/G3/R1, target contract/marker, tests, provenance, and ledger; no cleanup performed
owned_processes: unchanged tmux so101-phy5-v2-r0 Gazebo and MoveIt stack; no execute, recorder, or video yet
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes untouched
confirmed_conclusions:
  - fresh RESET_WORLD and runtime provenance pass with R1 installed
disproven_routes:
  - reusing G3 post-open scene state
open_risks:
  - R1 may expose final physical failure after retreat
next_command: start recorder/video and exactly one R1 execute
```

```yaml
checkpoint_id: CP-V2-R1-RUNTIME-001-VALID-026
recorded_at: 2026-08-10 Asia/Shanghai
last_valid_experiment: PHY5-R1-RUNTIME-001
current_hypothesis: H-R1 remains unresolved because runtime 001 stopped at the pre-attach physical gate
working_tree_status: expected dirty G2/G3/R1, target contract/marker, tests, provenance, and ledger; no cleanup performed
owned_processes: existing tmux so101-phy5-v2-r0 Gazebo and MoveIt only; R1 recorder/video stopped and execute exited
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes untouched
confirmed_conclusions:
  - the tightened 1 mm micro-lift policy was not bypassed; unstable seating never reached micro-lift or carry
  - release q6 and R1 RETREAT remain untested by this sample and therefore stay unchanged
disproven_routes:
  - interpreting transient bilateral contact as a successful grasp without the stable target-penetration gate
open_risks:
  - R1 post-open RETREAT and authoritative final placement outcome remain unobserved
next_command: preregister PHY5-R1-RUNTIME-002, then fresh RESET_WORLD on the unchanged stack
```

## PHY5-R1-RUNTIME-002 unchanged repeat after protected seating failure

```yaml
experiment_id: PHY5-R1-RUNTIME-002
status: VALID
prior_experiment: PHY5-R1-RUNTIME-001
hypothesis: H-R1; a fresh physical sample that passes the unchanged G2/G3 gates will exercise the unified fixed RETREAT and remove the aligned-path error 99999.
prediction:
  - RESET_WORLD again restores the canonical upright cup, detached Gazebo state, and MoveIt world-only state
  - unchanged target-penetration and 1 mm micro-lift gates either fail closed or select a stable bilateral grasp
  - if release is reached, fixed RETREAT occurs before Planning Scene detach and no post-open MoveGroup 99999 path runs
  - final outcome is evaluated only after retreat and physical settling
single_variable: physical stochastic repeat only; source, policy, release q6, placement target, target tolerance, and physics remain unchanged
lifecycle: RESET_WORLD
success_criteria:
  - valid pre-attach gate, carry, release, fixed RETREAT, post-retreat detach, and authoritative final-outcome evidence
  - full success additionally requires upright cup center strictly inside the red ring and all current final gates
failure_criteria:
  - any complete fail-closed physical gate or later failure with synchronized telemetry, log, video, and final scene
invalid_criteria:
  - provenance mismatch, failed reset, duplicate stack/execute, missing evidence, stale state, or FULL_RESTART
commands:
  - fresh RESET_WORLD on existing tmux so101-phy5-v2-r0
  - bounded recorder/video, then exactly one execute with session-id phy5-r1-runtime-002
observed:
  - RESET_WORLD_PROVED with 0.0000016872503309481983 m object-pose error, Gazebo detached, MoveIt world-only plastic_cup, no finger contact, and finite TCP
  - source/runtime live_execute hashes match; source/installed policy hashes match; all controllers active
  - execution again stopped at POST_SEATING_PHYSICAL_STABILITY before shadow attach and micro-lift; the last stable bilateral moving-pad depth was 0.000505372125 m at target q6=-0.0495707836
  - telemetry shows the same physical sample occupied two penetration modes: about 1.02--1.21 mm before the last adjustment and about 0.48--0.55 mm after it, so a 1 mrad adjustment crossed the 0.8--1.0 mm window instead of converging
  - the bounded adjustment search itself accumulated 2.6080 mm cup XY drift and 0.08581 rad maximum tilt; no carry, release, or RETREAT occurred
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-r1-runtime-002/provenance.txt
  - /tmp/so101-physical-five-success-v2/phy5-r1-runtime-002/reset/reset-world.json sha256=53e07a28f7f1959704e25487f5a2ee9188af69c718a06d9be2e30c20f880c22f
  - /tmp/so101-physical-five-success-v2/phy5-r1-runtime-002/reset-gazebo.png sha256=36b13c72b682d56c615c27bedc333502fc055b0c5e772d7cf9e17ed892e0e02b
  - /tmp/so101-physical-five-success-v2/phy5-r1-runtime-002/run/execute.log sha256=97eb0c46b545f4ce1cc155a1682ec47226de00addb4b942d1b999b37ab07fda0
  - /tmp/so101-physical-five-success-v2/phy5-r1-runtime-002/run/physical-failure.json sha256=101a98bccc10d8c66429420baccd253eb0c34269b8976b18d066e3370d6dc6de
  - /tmp/so101-physical-five-success-v2/phy5-r1-runtime-002/run/diagnostic/samples.jsonl sha256=a4c70bec207f7c4773ad37b7aa2b98744464e31dd8dccf57409275df1ef067d1
  - /tmp/so101-physical-five-success-v2/phy5-r1-runtime-002/run/diagnostic/gazebo-gui.mp4 sha256=fcd4435ecfeb070c1acc28a8a34759b90f66d3d7b4a6dd406f1b855a2d09f6b7
  - /tmp/so101-physical-five-success-v2/phy5-r1-runtime-002/run/gate-analysis.json sha256=eddb70f108e780c68326d8eb21094f58da368e264bf052214389ca810fbda326
  - /tmp/so101-physical-five-success-v2/phy5-r1-runtime-002/run/depth-response.json sha256=46dd243c5d4ac8351e2d5149e34ff2c80b9748c2eb583de8f0ce5b2159dd6057
  - /tmp/so101-physical-five-success-v2/phy5-r1-runtime-002/run/final-gazebo.png sha256=63ae2411bfcba1b586761e932f2d5386ed91182ba8d854949062b1756b93a45d
decision: CHANGE_GATE_BAND; repeating unchanged is no longer the priority because two consecutive complete runs failed before R1 on the same narrow-window controller
next_experiment: PHY5-G4-RED; admit stable bilateral depth 0.5--1.1 mm, retain hard 1.3 mm ceiling and 1 mm micro-lift gate
```

```yaml
checkpoint_id: CP-V2-R1-RUNTIME-002-RESET-PROVED-027
recorded_at: 2026-08-10 Asia/Shanghai
last_valid_experiment: PHY5-R1-RUNTIME-001
current_hypothesis: H-R1
working_tree_status: expected dirty G2/G3/R1, target contract/marker, tests, provenance, and ledger; no cleanup performed
owned_processes: unchanged tmux so101-phy5-v2-r0 Gazebo and MoveIt stack; no execute, recorder, or video yet
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes untouched
confirmed_conclusions:
  - a second fresh RESET_WORLD restored canonical detached state without restarting Gazebo or MoveIt
  - R1 source/runtime and policy provenance remain frozen
disproven_routes:
  - changing release q6 in response to a pre-release seating failure
open_risks:
  - stable grasp selection and R1 post-open RETREAT still require runtime evidence
next_command: start bounded recorder/video and exactly one PHY5-R1-RUNTIME-002 execute
```

```yaml
checkpoint_id: CP-V2-R1-RUNTIME-002-VALID-028
recorded_at: 2026-08-10 Asia/Shanghai
last_valid_experiment: PHY5-R1-RUNTIME-002
current_hypothesis: H-G4; the narrow 0.8--1.0 mm target band causes unnecessary contact-mode switching, cup drift, and tilt before the stronger micro-lift outcome gate
working_tree_status: expected dirty G2/G3/R1, target contract/marker, tests, provenance, and ledger; no cleanup performed
owned_processes: existing tmux so101-phy5-v2-r0 Gazebo and MoveIt only; recorder/video stopped and execute exited
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes untouched
confirmed_conclusions:
  - two unchanged RESET_WORLD runs stopped at the same pre-attach target-penetration controller, so H-R1 cannot be tested until that upstream gate is made robust
  - both failures were fail-closed and never used Gazebo attach; q6=0.750 and R1 remain unchanged
disproven_routes:
  - continuing stochastic repeats against the 0.8--1.0 mm band without changing its control contract
open_risks:
  - a wider safe band must still retain stable bilateral contact, the 1.3 mm ceiling, and the 1 mm outcome-based micro-lift gate
next_command: add the G4 regression, prove RED, then implement only the safe-band change
```

## PHY5-G4 safe bilateral admission band

```yaml
experiment_id: PHY5-G4-RED
status: VALID
prior_experiment: PHY5-R1-RUNTIME-002
hypothesis: H-G4; admitting stable bilateral penetration in 0.5--1.1 mm prevents 1 mrad control oscillation while the unchanged 1.3 mm hard ceiling and 1 mm micro-lift gate retain safety and carry evidence.
prediction:
  - an observed R1-002-like stable 0.505 mm sample is accepted without another gripper adjustment
  - weak 0.2 mm samples still tighten, missing bilateral contact still preopens/recloses, and >1.3 mm still fails immediately
  - no target pose, release q6, micro-lift, RETREAT, physics, or final tolerance changes
single_variable: target-penetration admission band 0.8--1.0 mm to 0.5--1.1 mm
success_criteria:
  - new regression fails before implementation and passes after it
  - owning tests, package tests, build, installed runtime provenance, and git diff check pass
failure_criteria:
  - hard ceiling or micro-lift safety contract weakens, or unrelated behavior changes
observed:
  - RED: source-contract and observed 0.505372 mm admission tests both failed on the 0.8--1.0 mm implementation
  - GREEN: only the admission defaults changed to 0.5--1.1 mm; missing contact, weak-contact tightening, 1 mrad adjustment, 1.3 mm hard ceiling, and 1 mm micro-lift contracts remain covered
  - owning test files: 53 passed; package result: 212 tests, 0 errors, 0 failures, 2 skipped
  - build succeeded, git diff check is clean, and source/runtime live_execute SHA-256 match at 9a68b571f1d5b6399e56a54983e5122a61e8fc776b1080c995155240c539e60c
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g4-red/red.log sha256=c8e290d16dbca3c4dc64c81158e8c92a4db26a58d5aa8f250059aee722162a30
  - /tmp/so101-physical-five-success-v2/phy5-g4-red/green-owning.log sha256=28dd56dbc861435378dfe7fd8473a43995933ac1775dedd1e9e0d97d9c9e05bb
  - /tmp/so101-physical-five-success-v2/phy5-g4-red/build.log sha256=b793ddff652c8447b536cba05f8126e6d2040b5432b1f83edbf427c9f1c348ad
  - /tmp/so101-physical-five-success-v2/phy5-g4-red/test.log sha256=354b2f6b69622423c78839d16a7d543f29a4e8bc8c5882008a92b91cd0711ad0
  - /tmp/so101-physical-five-success-v2/phy5-g4-red/test-result.log sha256=2d1d3d55b3fe3270363255025c2301af44be3484b3b24a139247f80a055b008a
decision: GREEN; proceed to one physical runtime verification before any qualification streak
next_experiment: PHY5-G4-RUNTIME-001 via RESET_WORLD if automated GREEN
```

```yaml
checkpoint_id: CP-V2-G4-GREEN-029
recorded_at: 2026-08-11 Asia/Shanghai
last_valid_experiment: PHY5-G4-RED
current_hypothesis: H-G4
working_tree_status: expected dirty G2/G3/G4/R1, target contract/marker, tests, provenance, and ledger; git diff check clean
owned_processes: existing tmux so101-phy5-v2-r0 Gazebo and MoveIt only
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes untouched
confirmed_conclusions:
  - automated contracts admit the observed safe bilateral band while preserving the independent hard ceiling and outcome-based micro-lift gate
  - installed runtime is rebuilt from the G4 source and all package tests pass
disproven_routes:
  - treating a narrow target-depth band as stronger carry evidence than the physical micro-lift outcome
open_risks:
  - G4 must demonstrate that the physical run reaches micro-lift without introducing a deep-contact or carry regression
  - R1 RETREAT and final placement remain unobserved
next_command: preregister PHY5-G4-RUNTIME-001 and perform a fresh RESET_WORLD on the existing stack
```

## PHY5-G4-RUNTIME-001 safe-band physical verification

```yaml
experiment_id: PHY5-G4-RUNTIME-001
status: VALID
prior_experiment: PHY5-G4-RED
hypothesis: H-G4 plus H-R1; safe-band admission avoids pre-lift oscillation, then the unchanged micro-lift gate selects a stable carry and unified fixed RETREAT produces an authoritative final outcome.
prediction:
  - RESET_WORLD restores canonical detached state without stack restart
  - stable bilateral depth 0.5--1.1 mm is admitted with fewer adjustments while >1.3 mm remains impossible
  - micro-lift lateral drift must remain <=1 mm before shadow carry continues
  - if release is reached, fixed RETREAT precedes Planning Scene detach and no error 99999 occurs
single_variable: G4 admission band; all other current candidate parameters frozen
lifecycle: RESET_WORLD
success_criteria:
  - complete provenance, reset, telemetry, video, gate, scene, retreat, and final-outcome evidence
  - full success requires upright placement strictly inside the red ring after retreat/settling
failure_criteria:
  - complete fail-closed evidence at any physical boundary
invalid_criteria:
  - provenance mismatch, failed reset, duplicate stack/execute, missing evidence, or FULL_RESTART
observed:
  - RESET_WORLD_PROVED with 0.0000016739771106665257 m object-pose error, Gazebo detached, MoveIt world-only plastic_cup, no finger contact, and finite TCP
  - G4 source/runtime hashes match; validation policy source/install hashes match; all controllers active
  - safe-band gate passed after one adjustment at 1.064096 mm; micro-lift passed with 0.404016 mm lateral drift and 2.252609 mm world-Z lift, below the unchanged 1 mm drift and 1.3 mm penetration ceilings
  - carry and release completed; release began at cup center (-0.0798890,-0.2610247,0.1837756) with 14.10 mm bottom clearance and 0.127 rad tilt
  - opening/fall displaced the cup 7.12446 mm before q6 reached 0.74; the cup settled upright at (-0.0866730,-0.2631526,0.1649998), tilt 0.0000207 rad
  - unified fixed RETREAT arm motion was observed before Planning Scene detach; no error 99999 occurred; final Gazebo detached, MoveIt world-only, controllers active
  - authoritative post-retreat outcome failed only FINAL_OUT_OF_REGION: x error -6.673 mm and y error -13.153 mm from the intended center
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g4-runtime-001/provenance.txt
  - /tmp/so101-physical-five-success-v2/phy5-g4-runtime-001/reset/reset-world.json sha256=c101d294373e040eef18036150a28b91640b9bdf8ffc42b3ce070d22531050ec
  - /tmp/so101-physical-five-success-v2/phy5-g4-runtime-001/reset-gazebo.png sha256=f1238292ae55c12b4113c779e0fab6a935bd80e48eb03cca55c34440024ae399
  - /tmp/so101-physical-five-success-v2/phy5-g4-runtime-001/run/execute.log sha256=5d2d5815c0fd4439b5f17d3de2204ef8ed1a6327337e06bc06c17e3f74e985ea
  - /tmp/so101-physical-five-success-v2/phy5-g4-runtime-001/run/physical-gate.json sha256=ac7995e2dee387be03038782f1141827e5c8b014ee9f7642fab10eb8e1aa1dd7
  - /tmp/so101-physical-five-success-v2/phy5-g4-runtime-001/run/final-outcome-failure.json sha256=99b759fee660bf855f03a10ea319af7e0beff77f72efe38994697145d0c80891
  - /tmp/so101-physical-five-success-v2/phy5-g4-runtime-001/run/final-summary.json sha256=fe9d13977021823587248a13a64ba6792419373c4edb2dfc7fa8eb0b323917a0
  - /tmp/so101-physical-five-success-v2/phy5-g4-runtime-001/run/diagnostic/samples.jsonl sha256=6e4588a6e7eadf6a932898fcdaf3c94bea3dceb687803c7faae13cf4b15eab84
  - /tmp/so101-physical-five-success-v2/phy5-g4-runtime-001/run/diagnostic/gazebo-gui.mp4 sha256=a9fa7cd668429732df8827a87a14af81d9c889538f28ad74d1b8e716fabbcf8a
  - /tmp/so101-physical-five-success-v2/phy5-g4-runtime-001/run/release-analysis.json sha256=f2879342dcd613f86b8d8a92fce0c9f8154fed63a1c9015014ccc6ad64dbc729
  - /tmp/so101-physical-five-success-v2/phy5-g4-runtime-001/run/tilt-analysis.json sha256=03ed7483d4bc571d751629af2767e274e69138b331e2ae891e41b200232c6760
  - /tmp/so101-physical-five-success-v2/phy5-g4-runtime-001/run/final-gazebo.png sha256=9b113ce4c9eb5e70254d69139d3b7faf6788abee324a266940d7444568359544
decision: G4_AND_R1_PROVED_TARGET_ONLY_FAILURE; keep release q6 because the 7.12 mm motion is a gravity landing from 14.10 mm clearance, then compensate the measured release-to-settle displacement
next_experiment: PHY5-G5-RED; update only release settling compensation so the feedback alignment targets the inverse observed landing displacement
```

```yaml
checkpoint_id: CP-V2-G4-RUNTIME-001-RESET-PROVED-030
recorded_at: 2026-08-11 Asia/Shanghai
last_valid_experiment: PHY5-G4-RED
current_hypothesis: H-G4 plus H-R1
working_tree_status: expected dirty G2/G3/G4/R1, target contract/marker, tests, provenance, and ledger; no cleanup performed
owned_processes: unchanged tmux so101-phy5-v2-r0 Gazebo and MoveIt stack; no execute, recorder, or video yet
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes untouched
confirmed_conclusions:
  - fresh RESET_WORLD and G4 installed-runtime provenance pass without FULL_RESTART
disproven_routes:
  - reusing R1-002 contact/tilt state
open_risks:
  - G4 physical admission, micro-lift, R1 RETREAT, and final outcome remain unobserved
next_command: start bounded recorder/video and exactly one PHY5-G4-RUNTIME-001 execute
```

```yaml
checkpoint_id: CP-V2-G4-RUNTIME-001-VALID-031
recorded_at: 2026-08-11 Asia/Shanghai
last_valid_experiment: PHY5-G4-RUNTIME-001
current_hypothesis: H-G5; current settling compensation predicts the wrong XY landing displacement and its 10 mm alignment tolerance therefore accepts a held pose that lands outside the circle
working_tree_status: expected dirty G2/G3/G4/R1, target contract/marker, tests, provenance, and ledger; no cleanup performed
owned_processes: existing tmux so101-phy5-v2-r0 Gazebo and MoveIt only; G4 recorder/video stopped and execute exited
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes untouched
confirmed_conclusions:
  - G4 safe-band and 1 mm micro-lift gates selected a stable carry
  - R1 fixed RETREAT executed and removed the previous post-open planning failure
  - final cup was upright, settled, supported, detached, and scene-synchronized; target region was the only failing final gate
disproven_routes:
  - changing q6 because release motion was caused by a measurable 14.10 mm free landing, not continued finger sweep after q6 0.74
open_risks:
  - one-run settling compensation may not generalize; it requires a new RESET_WORLD validation before qualification
next_command: add G5 compensation regression, prove RED/GREEN, then one RESET_WORLD runtime
```

## PHY5-G5 measured settling compensation

```yaml
experiment_id: PHY5-G5-RED
status: VALID
prior_experiment: PHY5-G4-RUNTIME-001
hypothesis: H-G5; targeting the inverse measured release-to-settle displacement moves the pre-release cup center so the same physical landing settles at the intended center.
prediction:
  - compensation changes from (5.0,-5.0,14.0) mm to (6.8,2.1,18.8) mm
  - current G4 held pose is outside the unchanged 10 mm alignment tolerance, so same-run feedback commands an XY correction before release
  - q6, G4 gate, micro-lift, fixed RETREAT, target tolerance, and physics remain unchanged
single_variable: release settling compensation vector only
success_criteria:
  - regression proves target (-73.2,-247.9,183.8) mm for the nominal place center
  - owning/package tests, build, runtime provenance, and diff check pass
failure_criteria:
  - any safety or final acceptance limit changes, or unrelated policy behavior changes
observed:
  - RED: old (5.0,-5.0,14.0) mm compensation failed the measured-landing target regression
  - GREEN: default compensation changed only to (6.8,2.1,18.8) mm; owning files 71 passed
  - package result: 212 tests, 0 errors, 0 failures, 2 skipped; build passed and git diff check is clean
  - source/runtime live_execute SHA-256 match at c4f390ad86d4fe65a0b0c0567b5bbc32c57aa92555138343366d79dea3ace85a
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g5-red/red.log sha256=11590532368f7a574fa05479d1b2893d0baa7246bb7409a49ecc13c1d0d77633
  - /tmp/so101-physical-five-success-v2/phy5-g5-red/green-owning.log sha256=6ff2bdc6c63f7700724e1038d9249a3a0dc06504da08b2a8e6c70b39337f0237
  - /tmp/so101-physical-five-success-v2/phy5-g5-red/build.log sha256=32720c1035935d06f68ebff97c42f65b45bc1854d0a451fd6cffc6890756de3e
  - /tmp/so101-physical-five-success-v2/phy5-g5-red/test.log sha256=43a403e9e7dbec717576c3fe13cd29fec5e66474f4b9c3bcc91f4599923f708f
  - /tmp/so101-physical-five-success-v2/phy5-g5-red/test-result.log sha256=2d1d3d55b3fe3270363255025c2301af44be3484b3b24a139247f80a055b008a
decision: GREEN; perform one physical RESET_WORLD validation before freezing the candidate
next_experiment: PHY5-G5-RUNTIME-001 via RESET_WORLD after GREEN
```

```yaml
checkpoint_id: CP-V2-G5-GREEN-032
recorded_at: 2026-08-11 Asia/Shanghai
last_valid_experiment: PHY5-G5-RED
current_hypothesis: H-G5
working_tree_status: expected dirty G2/G3/G4/G5/R1, target contract/marker, tests, provenance, and ledger; git diff check clean
owned_processes: existing tmux so101-phy5-v2-r0 Gazebo and MoveIt only
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes untouched
confirmed_conclusions:
  - installed runtime contains the measured settling compensation and all automated contracts pass
disproven_routes:
  - changing q6 or final tolerance before correcting the predicted pre-release center
open_risks:
  - MoveGroup same-run alignment may reject the required correction or physical landing displacement may vary
next_command: preregister PHY5-G5-RUNTIME-001 and fresh RESET_WORLD
```

## PHY5-G5-RUNTIME-001 measured-compensation validation

```yaml
experiment_id: PHY5-G5-RUNTIME-001
status: VALID
prior_experiment: PHY5-G5-RED
hypothesis: H-G5; feedback alignment to the measured inverse landing displacement yields an upright final cup center inside the 10 mm target circle after fixed RETREAT.
prediction:
  - unchanged G4 and micro-lift gates pass or fail closed
  - pre-release place alignment is non-empty and moves the held cup toward (-0.0732,-0.2479,0.1838) m
  - fixed RETREAT precedes detach; final cup is upright and its radial center error is <10 mm
single_variable: G5 release settling compensation only
lifecycle: RESET_WORLD
success_criteria:
  - authoritative DONE/final success with all physical, scene, support, upright, stability, and region gates
failure_criteria:
  - complete fail-closed evidence at the first physical boundary
invalid_criteria:
  - provenance mismatch, failed reset, duplicate stack/execute, missing evidence, or FULL_RESTART
observed:
  - RESET_WORLD_PROVED with 0.0000016872503309481983 m object-pose error, Gazebo detached, MoveIt world-only plastic_cup, no finger contact, and finite TCP
  - G5 source/runtime hashes and validation-policy source/install hashes match
  - unchanged physical gate passed at 1.027568 mm post-seating penetration and 0.211066 mm micro-lift lateral drift
  - G5 same-run alignment moved the held cup to approximately (-0.0736640,-0.2446561,0.1818171) m, proving the new XY compensation affected the intended boundary
  - immediately after alignment, both bounded pose-pair subscriptions returned no fresh Gazebo object or TCP sample; execution failed before opening with fresh Gazebo/TCP pose pair unavailable
  - final live state remained Gazebo detached but MoveIt shadow attached, as expected for a pre-release exception; controllers remained active and RESET_WORLD is required before any repeat
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g5-runtime-001/provenance.txt
  - /tmp/so101-physical-five-success-v2/phy5-g5-runtime-001/reset/reset-world.json sha256=53e07a28f7f1959704e25487f5a2ee9188af69c718a06d9be2e30c20f880c22f
  - /tmp/so101-physical-five-success-v2/phy5-g5-runtime-001/reset-gazebo.png sha256=98721a5034d9e1568668b40050eb0b44e4df6ea2fb5a1495546d379319dfc657
  - /tmp/so101-physical-five-success-v2/phy5-g5-runtime-001/run/execute.log sha256=1f20abe17c81695c2f80cbabadf083d51c885ef2f87f9d1f8bb7a61b9b40966f
  - /tmp/so101-physical-five-success-v2/phy5-g5-runtime-001/run/physical-gate.json sha256=49330efcdcd95ec430d26fe224187e03c961b78f700662b87034d4edac86f209
  - /tmp/so101-physical-five-success-v2/phy5-g5-runtime-001/run/diagnostic/samples.jsonl sha256=e2729bbee437a2d1e42ecc767df6124a283838c387e732a7c500c24ae3a5de1c
  - /tmp/so101-physical-five-success-v2/phy5-g5-runtime-001/run/diagnostic/gazebo-gui.mp4 sha256=dc00cced5bf36ea0ebf20195ae108c8d7d999ff45e432b2ef367836f7a8baca8
  - /tmp/so101-physical-five-success-v2/phy5-g5-runtime-001/run/final-gazebo.png sha256=fa9db849c4dd2e3c71b75f29d7858f50123bcf4d9620a98747495415af937ea3
decision: G5_ALIGNMENT_EFFECT_PROVED_OUTCOME_UNRESOLVED; add one bounded backoff/retry to the already-approved transient pose-pair sampler, then repeat unchanged compensation
next_experiment: PHY5-G6-RED
```

```yaml
checkpoint_id: CP-V2-G5-RUNTIME-001-RESET-PROVED-033
recorded_at: 2026-08-11 Asia/Shanghai
last_valid_experiment: PHY5-G5-RED
current_hypothesis: H-G5
working_tree_status: expected dirty G2/G3/G4/G5/R1, target contract/marker, tests, provenance, and ledger; no cleanup performed
owned_processes: unchanged tmux so101-phy5-v2-r0 Gazebo and MoveIt stack; no execute, recorder, or video yet
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes untouched
confirmed_conclusions:
  - fresh RESET_WORLD and G5 installed-runtime provenance pass without FULL_RESTART
disproven_routes:
  - reusing G4 final placement state
open_risks:
  - same-run alignment and compensated physical landing remain unobserved
next_command: start bounded recorder/video and exactly one PHY5-G5-RUNTIME-001 execute
```

```yaml
checkpoint_id: CP-V2-G5-RUNTIME-001-VALID-034
recorded_at: 2026-08-11 Asia/Shanghai
last_valid_experiment: PHY5-G5-RUNTIME-001
current_hypothesis: H-G6; immediate back-to-back pose subscription retries do not allow transport cleanup after a MoveGroup alignment helper exits
working_tree_status: expected dirty G2/G3/G4/G5/R1, target contract/marker, tests, provenance, and ledger; no cleanup performed
owned_processes: existing tmux so101-phy5-v2-r0 Gazebo and MoveIt only; G5 recorder/video stopped and execute exited
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes untouched
confirmed_conclusions:
  - G5 compensation triggered a real same-run correction; landing outcome remains unknown because opening never began
  - failure was telemetry fail-closed, not a physical target miss
disproven_routes:
  - classifying the compensated target from its pre-release pose alone
open_risks:
  - a third delayed pose-pair attempt may still fail if the subscription outage is persistent
next_command: TDD a three-attempt bounded retry with 250 ms cleanup backoff; no motion-policy change
```

## PHY5-G6 bounded pose-pair recovery

```yaml
experiment_id: PHY5-G6-RED
status: VALID
prior_experiment: PHY5-G5-RUNTIME-001
hypothesis: H-G6; three bounded subscription attempts with 250 ms backoff recover a transient post-alignment empty pose pair without masking persistent telemetry loss.
prediction:
  - two transient empty subscriptions followed by a fresh sample succeed
  - three transient empty subscriptions still raise the original error
  - motion, grasp, release, compensation, target, and safety policies remain unchanged
single_variable: pose-pair transient retry budget/backoff only
success_criteria:
  - RED/GREEN regression, owning/package tests, build, runtime hash, and diff check pass
failure_criteria:
  - non-transient errors retry, persistent loss is masked, or motion policy changes
observed:
  - RED: recovery-on-third-attempt and three-attempt bounded-failure tests both failed against the two immediate retry implementation
  - GREEN: sampler now makes at most three attempts with 250 ms cleanup backoff only for the exact transient empty-pair error; owning file 38 passed
  - package result: 213 tests, 0 errors, 0 failures, 2 skipped; build and git diff check pass
  - source/runtime backend SHA-256 match at 6a8861f72038766ca9ea1f00b91be18a8465d4f94d1ba4e76bd13c8657d1ca84; live_execute remains c4f390ad86d4fe65a0b0c0567b5bbc32c57aa92555138343366d79dea3ace85a
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g6-red/red.log sha256=07f6846a79a4c4460d67c3e547a7dae11f91179ac24f347d2e3465939a138642
  - /tmp/so101-physical-five-success-v2/phy5-g6-red/green-owning.log sha256=c7cb9d89547bf9ed61602dcad41ee9c8c0f819e62825b20d51c77b4b2ef2f866
  - /tmp/so101-physical-five-success-v2/phy5-g6-red/build.log sha256=32720c1035935d06f68ebff97c42f65b45bc1854d0a451fd6cffc6890756de3e
  - /tmp/so101-physical-five-success-v2/phy5-g6-red/test.log sha256=af09f9436a0c934c5e47073f2ece4e995664290a3cfc069a229d5ba57b7688aa
  - /tmp/so101-physical-five-success-v2/phy5-g6-red/test-result.log sha256=25e4a31f47c961116a81d1631698a4851dbf6768292a4d77cf437d659d262d19
decision: GREEN; repeat the compensated runtime from fresh RESET_WORLD
next_experiment: PHY5-G6-RUNTIME-001 via RESET_WORLD after GREEN
```

```yaml
checkpoint_id: CP-V2-G6-GREEN-035
recorded_at: 2026-08-11 Asia/Shanghai
last_valid_experiment: PHY5-G6-RED
current_hypothesis: H-G6 plus H-G5
working_tree_status: expected dirty G2/G3/G4/G5/G6/R1, target contract/marker, tests, provenance, and ledger; git diff check clean
owned_processes: existing tmux so101-phy5-v2-r0 Gazebo and MoveIt only
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes untouched
confirmed_conclusions:
  - bounded telemetry recovery is automated and persistent loss still fails after three attempts
disproven_routes:
  - unbounded retry or swallowing non-transient sampling errors
open_risks:
  - live transport outage may last beyond the third delayed attempt
  - G5 final landing remains unobserved
next_command: preregister PHY5-G6-RUNTIME-001 and fresh RESET_WORLD
```

## PHY5-G6-RUNTIME-001 compensated landing with bounded sampling recovery

```yaml
experiment_id: PHY5-G6-RUNTIME-001
status: VALID
prior_experiment: PHY5-G6-RED
hypothesis: H-G6 plus H-G5; bounded recovery supplies the post-alignment pose, then compensated release settles upright inside the target circle after fixed RETREAT.
prediction:
  - RESET_WORLD restores detached canonical state
  - G4 gate passes or fails closed; G5 place alignment is non-empty
  - post-alignment pose sampling succeeds within three attempts or reports the same bounded failure
  - final success requires all existing final gates and radial center error <10 mm
single_variable: G6 sampling recovery relative to G5 runtime
lifecycle: RESET_WORLD
success_criteria:
  - complete authoritative DONE outcome plus video/telemetry/scene/retreat evidence
failure_criteria:
  - complete evidence at first fail-closed boundary
invalid_criteria:
  - provenance mismatch, failed reset, duplicate stack/execute, missing evidence, or FULL_RESTART
observed:
  - RESET_WORLD_PROVED with 0.0000016778094788836903 m object-pose error, Gazebo detached, MoveIt world-only plastic_cup, no finger contact, and finite TCP
  - G5 live_execute and G6 backend source/runtime hashes match
  - G6 passed the prior post-alignment sampling boundary and the G5 alignment reduced XY target error from 14.0179 mm to 1.87744 mm with 15 planned points
  - the full compensation correction increased pre-release tilt; cup remained in fixed-finger contact through q6=0.74 and the beginning of fixed RETREAT
  - authoritative post-retreat outcome failed FINAL_GRIPPER_CONTACT; after the failure epoch the cup was carried/expelled 115.126 mm and finally lay on its side near (-0.17338,-0.19666)
  - fixed RETREAT, Gazebo detach, MoveIt world-only synchronization, and telemetry recovery all executed; G5 full-vector compensation is the disproven variable
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g6-runtime-001/provenance.txt
  - /tmp/so101-physical-five-success-v2/phy5-g6-runtime-001/reset/reset-world.json sha256=425dd4961fbf886966caf3d02cf91943a271d0046747fd2594190f9a370875e1
  - /tmp/so101-physical-five-success-v2/phy5-g6-runtime-001/reset-gazebo.png sha256=3c8cfcdd0c171c907e002e4c5ee92bff9fdd9841e26a0fd70bf2b428a4e1013a
  - /tmp/so101-physical-five-success-v2/phy5-g6-runtime-001/run/execute.log sha256=c6e4b0bc2b1e88e17b8809360acca24cd47fe67deeb956fab6f74ffbcc878705
  - /tmp/so101-physical-five-success-v2/phy5-g6-runtime-001/run/physical-gate.json sha256=e9e20b70c7cbb9fa2921ea02bb68769f532b904999a9ac3505df80733e9693c0
  - /tmp/so101-physical-five-success-v2/phy5-g6-runtime-001/run/final-outcome-failure.json sha256=d7a3d694bd37dff9bbedcf93f053c89c81568a671e06c462f4f2715c4a616786
  - /tmp/so101-physical-five-success-v2/phy5-g6-runtime-001/run/diagnostic/samples.jsonl sha256=10155dfcc8ae537dca3904b3963de217c003b53f0e1b46f2a7c167ef18a9084e
  - /tmp/so101-physical-five-success-v2/phy5-g6-runtime-001/run/diagnostic/gazebo-gui.mp4 sha256=4b5a713350f1087e8ed9b597828f8204e0cd166017a7b6f3e473f0bc6c9b111c
  - /tmp/so101-physical-five-success-v2/phy5-g6-runtime-001/run/release-analysis.json sha256=1c4add91a607028cb104c681bcd5d1989aa172adf77d5b1fdbd4900c54ba0924
  - /tmp/so101-physical-five-success-v2/phy5-g6-runtime-001/run/tilt-analysis.json sha256=613f93de8a1fc51cee54d1846f0ebf1cd415eed41a7412a5b33941c9abbfa3b3
  - /tmp/so101-physical-five-success-v2/phy5-g6-runtime-001/run/final-gazebo.png sha256=2be450f17358f48ac8a67b31d3471e8d3bb83dd1709979ba79772b8c72f01216
decision: G6_PROVED_G5_DISPROVED; retain sampling recovery, revert the full-vector compensation, and test a smaller correction toward the former release target
next_experiment: PHY5-G7-RED
```

```yaml
checkpoint_id: CP-V2-G6-RUNTIME-001-RESET-PROVED-036
recorded_at: 2026-08-11 Asia/Shanghai
last_valid_experiment: PHY5-G6-RED
current_hypothesis: H-G6 plus H-G5
working_tree_status: expected dirty G2/G3/G4/G5/G6/R1, target contract/marker, tests, provenance, and ledger; no cleanup performed
owned_processes: unchanged tmux so101-phy5-v2-r0 Gazebo and MoveIt stack; no execute, recorder, or video yet
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes untouched
confirmed_conclusions:
  - fresh RESET_WORLD and installed runtime provenance pass without FULL_RESTART
open_risks:
  - post-alignment pose recovery and final compensated landing remain unobserved
next_command: start bounded recorder/video and exactly one PHY5-G6-RUNTIME-001 execute
```

```yaml
checkpoint_id: CP-V2-G6-RUNTIME-001-VALID-037
recorded_at: 2026-08-11 Asia/Shanghai
last_valid_experiment: PHY5-G6-RUNTIME-001
current_hypothesis: H-G7; the former compensation target was reasonable but the 10 mm live alignment tolerance skipped a 7.9 mm correction that would have reduced both drop height and XY miss
working_tree_status: expected dirty G2/G3/G4/G5/G6/R1, target contract/marker, tests, provenance, and ledger; no cleanup performed
owned_processes: existing tmux so101-phy5-v2-r0 Gazebo and MoveIt only; G6 recorder/video stopped and execute exited
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes untouched
confirmed_conclusions:
  - G6 telemetry recovery is useful and retained
  - active full-vector correction is unsafe because it left fixed-finger contact during RETREAT
disproven_routes:
  - inverse compensation derived from one uncontrolled free-fall sample
open_risks:
  - a smaller correction may still increase tilt or retain gripper contact
next_command: rollback G5 compensation, set only the live alignment tolerance to 5 mm, TDD, then RESET_WORLD
```

## PHY5-G7 smaller live place alignment

```yaml
experiment_id: PHY5-G7-RED
status: VALID
prior_experiment: PHY5-G6-RUNTIME-001
hypothesis: H-G7; restoring the former target (-75,-255,179) mm but requiring 5 mm live XY alignment applies a smaller correction than G5 and reduces free-fall/landing error without trapping the cup.
prediction:
  - G5 compensation is fully rolled back
  - only live execution uses xy_tolerance_m=0.005; reusable alignment helper default remains 0.010
  - current G4-like 7.9 mm residual now triggers correction, while final target and safety limits remain unchanged
single_variable: live pre-release alignment tolerance 10 mm to 5 mm relative to the proven G4/R1 baseline
success_criteria:
  - RED/GREEN regression, package tests, build, runtime provenance, and physical validation
failure_criteria:
  - correction retains gripper contact during RETREAT, increases tilt materially, or changes acceptance/safety limits
observed:
  - RED: both compensation rollback and 5 mm live-call contract failed against G5/G6
  - GREEN: former compensation restored and only the live call supplies xy_tolerance_m=0.005; owning files 73 passed
  - package result: 214 tests, 0 errors, 0 failures, 2 skipped; build and git diff check pass
  - live_execute source/runtime hashes match at de4c2a12f7d0aa6013eb69464f086eae140d2f125368d6e7f8da2a1b0330e94e; G6 backend remains matched
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g7-red/red.log sha256=0d7f744585b09ed009c0bc6d87c56ed301319d7fb89755eac5ac02340111b9e1
  - /tmp/so101-physical-five-success-v2/phy5-g7-red/green-owning.log sha256=62d8e310f7c344c4347fbdea24be4982a24bd6df81074b7c34c93ab328e6ba1a
  - /tmp/so101-physical-five-success-v2/phy5-g7-red/build.log sha256=e97bf86af110774efc5d2dab1988c9a81269a3d29302322495ca3cd590bdf964
  - /tmp/so101-physical-five-success-v2/phy5-g7-red/test.log sha256=069a70e1a7ca4ceeaaef3edea228f76481d4971be9bf99c5302bc91818990cb3
  - /tmp/so101-physical-five-success-v2/phy5-g7-red/test-result.log sha256=49b8f906cf33c9e3068b1fe1dd915c6a8ecfc4fbf8f09b86ef646f9ad4a490c8
decision: GREEN; perform one fresh physical validation
next_experiment: PHY5-G7-RUNTIME-001 after automated GREEN
```

```yaml
checkpoint_id: CP-V2-G7-GREEN-038
recorded_at: 2026-08-11 Asia/Shanghai
last_valid_experiment: PHY5-G7-RED
current_hypothesis: H-G7
working_tree_status: expected dirty G2/G3/G4/G6/G7/R1, target contract/marker, tests, provenance, and ledger; G5 compensation rolled back; git diff check clean
owned_processes: existing tmux so101-phy5-v2-r0 Gazebo and MoveIt only
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes untouched
confirmed_conclusions:
  - G5 full compensation is no longer in source/runtime
  - G6 bounded telemetry recovery and all other current gates remain
open_risks:
  - smaller correction may still retain cup contact during retreat
next_command: preregister PHY5-G7-RUNTIME-001 and fresh RESET_WORLD
```

## PHY5-G7-RUNTIME-001 smaller-alignment physical verification

```yaml
experiment_id: PHY5-G7-RUNTIME-001
status: VALID
prior_experiment: PHY5-G7-RED
hypothesis: H-G7; smaller feedback correction yields a clean release, fixed RETREAT, and upright in-circle final outcome.
prediction:
  - G4/G6 gates pass or fail closed
  - place_alignment is non-empty but commanded translation is materially smaller than G6
  - cup loses all gripper contact before fixed RETREAT and final center error is <10 mm
single_variable: 5 mm live alignment tolerance relative to G4 baseline
lifecycle: RESET_WORLD
success_criteria:
  - authoritative DONE with all current gates, scene synchronization, upright and in-circle final pose
failure_criteria:
  - complete first-boundary evidence including contact through retreat if present
invalid_criteria:
  - provenance mismatch, failed reset, duplicate stack/execute, missing evidence, or FULL_RESTART
observed:
  - RESET_WORLD_PROVED with 0.0000008795271890195908 m object-pose error, Gazebo detached, MoveIt world-only plastic_cup, no finger contact, and finite TCP
  - G7 live_execute and G6 backend source/runtime hashes match
  - execution stopped before carry/place: after two micro-lift attempts, the final probe had 1.30342 mm lift but 4.02884 mm lateral drift, exceeding the unchanged 1 mm gate
  - Gazebo remained detached; MoveIt shadow was attached because the exception occurred after shadow attach and before carry; no release or G7 place alignment occurred
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g7-runtime-001/provenance.txt
  - /tmp/so101-physical-five-success-v2/phy5-g7-runtime-001/reset/reset-world.json sha256=a021103c0c6077624bad1d88311f4b0cbc451c6852cc0523c922e665c966cc23
  - /tmp/so101-physical-five-success-v2/phy5-g7-runtime-001/reset-gazebo.png sha256=cfaec89115f19f73fe726534145e78311e486dea907bc63bc931dec195fad470
  - /tmp/so101-physical-five-success-v2/phy5-g7-runtime-001/run/execute.log sha256=e459bf757e4327fb7ad6032ebc002762eb70d3410db6a835b95fda7a1f1b8368
  - /tmp/so101-physical-five-success-v2/phy5-g7-runtime-001/run/physical-failure.json sha256=f6101335c366d014a19acbe93523aab1d0cd897d86b9d0f66840f1828ded6601
  - /tmp/so101-physical-five-success-v2/phy5-g7-runtime-001/run/diagnostic/samples.jsonl sha256=5f7989680a44e4bb12df044712b9e08ac17aff37dd975baa2ecece28c61c11eb
  - /tmp/so101-physical-five-success-v2/phy5-g7-runtime-001/run/diagnostic/gazebo-gui.mp4 sha256=9057325bc8d8d24eead690368601024588bb82d68b53ba5de634604e82982531
  - /tmp/so101-physical-five-success-v2/phy5-g7-runtime-001/run/final-gazebo.png sha256=b7b58b8320cdb169b99acb53f215746260e3316a69cdf27970175d0c810b0f47
decision: KEEP_CONFIGURATION_AND_REPEAT; G7 was not exercised and the 1 mm gate correctly rejected the stochastic grasp sample
next_experiment: PHY5-G7-RUNTIME-002 with identical source/policy and fresh RESET_WORLD
```

```yaml
checkpoint_id: CP-V2-G7-RUNTIME-001-RESET-PROVED-039
recorded_at: 2026-08-11 Asia/Shanghai
last_valid_experiment: PHY5-G7-RED
current_hypothesis: H-G7
working_tree_status: expected dirty G2/G3/G4/G6/G7/R1, target contract/marker, tests, provenance, and ledger; no cleanup performed
owned_processes: unchanged tmux so101-phy5-v2-r0 Gazebo and MoveIt stack; no execute, recorder, or video yet
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes untouched
confirmed_conclusions:
  - fresh RESET_WORLD and G7 installed runtime provenance pass without FULL_RESTART
open_risks:
  - smaller live alignment physical release remains unobserved
next_command: start bounded recorder/video and exactly one PHY5-G7-RUNTIME-001 execute
```

```yaml
checkpoint_id: CP-V2-G7-RUNTIME-001-VALID-040
recorded_at: 2026-08-11 Asia/Shanghai
last_valid_experiment: PHY5-G7-RUNTIME-001
current_hypothesis: H-G7 remains unresolved
working_tree_status: expected dirty G2/G3/G4/G6/G7/R1, target contract/marker, tests, provenance, and ledger; no cleanup performed
owned_processes: existing tmux so101-phy5-v2-r0 Gazebo and MoveIt only; G7 runtime-001 recorder/video stopped and execute exited
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes untouched
confirmed_conclusions:
  - 1 mm micro-lift gate prevented a 4.03 mm lateral-drift sample from reaching carry
disproven_routes:
  - attributing the pre-carry failure to the unexecuted G7 place alignment
open_risks:
  - G7 smaller correction still lacks runtime evidence
next_command: preregister PHY5-G7-RUNTIME-002 and fresh RESET_WORLD with unchanged runtime
```

## PHY5-G7-RUNTIME-002 unchanged repeat

```yaml
experiment_id: PHY5-G7-RUNTIME-002
status: VALID
prior_experiment: PHY5-G7-RUNTIME-001
hypothesis: H-G7; a fresh sample passing the unchanged upstream gates will exercise the smaller place alignment.
prediction:
  - all provenance and reset conditions match runtime-001
  - upstream gate either fails closed or selects <=1 mm lateral drift
  - if place is reached, correction is smaller than G6 and release loses gripper contact before RETREAT
single_variable: stochastic repeat only
lifecycle: RESET_WORLD
success_criteria:
  - authoritative full outcome with complete evidence
failure_criteria:
  - first fail-closed boundary with complete evidence
invalid_criteria:
  - provenance/reset/evidence/duplicate failure or FULL_RESTART
observed:
  - RESET_WORLD_PROVED with 0.0000017319652427829308 m object-pose error, Gazebo detached, MoveIt world-only, no finger contact, and finite TCP
  - installed G7/G6 runtime hashes unchanged
  - upstream grasp and micro-lift gates passed, so the smaller live alignment was exercised
  - live alignment reduced XY target error from 11.464 mm to 1.232 mm; release began at (-0.0743039,-0.2539835,0.1780809)
  - the cup was already tilted about 0.453 rad before opening; tilt grew from 0.04494 rad at LIFT_END to 0.21868 rad at MOVE_ABOVE_PLACE_END and 0.47239 rad at DESCEND_TO_PLACE_END
  - motion through q6=0.74 was only 0.323 mm, so additional q6 closure is not supported by this run
  - fixed RETREAT then displaced the still-contacting cup by 18.832 mm; the final cup was upright, Gazebo-detached, and MoveIt world-only at (-0.0913302,-0.2464802,0.16499998)
  - final radial center error was about 11.864 mm, missing the strict 10 mm circle by about 1.864 mm; authoritative outcome was FINAL_OUT_OF_REGION
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g7-runtime-002/provenance.txt
  - /tmp/so101-physical-five-success-v2/phy5-g7-runtime-002/reset/reset-world.json sha256=c0816717f6bcb5c51a12429d8cd2b50d2a1533c8f678c0e63f301e695d38917f
  - /tmp/so101-physical-five-success-v2/phy5-g7-runtime-002/reset-gazebo.png sha256=d3fe975f759bc223909d81121a53a8d8a3a77dcbe4e2ba2c15636194fa816b9a
  - /tmp/so101-physical-five-success-v2/phy5-g7-runtime-002/run/execute.log sha256=bc5e6e4f5984c85921cc980668e08156d3e78c52e4870e62746a530686288385
  - /tmp/so101-physical-five-success-v2/phy5-g7-runtime-002/run/physical-gate.json sha256=1e77958bd58204c490c853479e220c15bcb1bb3955ed8c4349fa8a12440fb2f4
  - /tmp/so101-physical-five-success-v2/phy5-g7-runtime-002/run/final-outcome-failure.json sha256=0622f4b5a8be9d129237d57521c8059336496574a51d24699e2159cc7d917e74
  - /tmp/so101-physical-five-success-v2/phy5-g7-runtime-002/run/diagnostic/samples.jsonl sha256=fb74a42beb866fdf0a282153215012e368306f38f5ac45c81a7716e44e03ae89
  - /tmp/so101-physical-five-success-v2/phy5-g7-runtime-002/run/diagnostic/gazebo-gui.mp4 sha256=8412b7602077c797ffc09c54da040d02b5b8cfa30a70da772c799ead1937264d
  - /tmp/so101-physical-five-success-v2/phy5-g7-runtime-002/run/release-analysis.json sha256=4dda6312c879231440ecf9f72a63dd07dc94bcfebf035609b54299060241b02d
  - /tmp/so101-physical-five-success-v2/phy5-g7-runtime-002/run/tilt-analysis.json sha256=8fd52bf31c9926dcf8add4ceab82e1c3fe6c3d206c7aa46849e404aeae5ad5d3
  - /tmp/so101-physical-five-success-v2/phy5-g7-runtime-002/run/final-gazebo.png sha256=224812b077497f36d50b30bf20a1a0cba5bc2f385426ae7f2a38c1c1d28ab65c
decision: G7_ALIGNMENT_EFFECTIVE_BUT_CARRY_TILT_DOMINANT; retain G7, do not change q6 or target compensation, and address carry dynamics before qualification
next_experiment: PHY5-G8-RED
```

```yaml
checkpoint_id: CP-V2-G7-RUNTIME-002-RESET-PROVED-041
recorded_at: 2026-08-11 Asia/Shanghai
last_valid_experiment: PHY5-G7-RUNTIME-001
current_hypothesis: H-G7
working_tree_status: expected dirty G2/G3/G4/G6/G7/R1, target contract/marker, tests, provenance, and ledger; no cleanup performed
owned_processes: unchanged tmux so101-phy5-v2-r0 Gazebo and MoveIt stack; no execute, recorder, or video yet
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes untouched
confirmed_conclusions:
  - unchanged repeat starts from a fresh RESET_WORLD proof
open_risks:
  - upstream stochastic grasp may again fail before G7
next_command: start bounded recorder/video and exactly one PHY5-G7-RUNTIME-002 execute
```

```yaml
checkpoint_id: CP-V2-G7-RUNTIME-002-VALID-042
recorded_at: 2026-08-11 Asia/Shanghai
last_valid_experiment: PHY5-G7-RUNTIME-002
current_hypothesis: H-G8; cup slip/tilt is driven primarily by carry and descent dynamics, leaving fixed-finger contact at release and converting RETREAT into lateral cup displacement
working_tree_status: expected dirty G2/G3/G4/G6/G7/R1, target contract/marker, tests, provenance, and ledger; G5 compensation remains rolled back; git diff check clean
owned_processes: existing tmux so101-phy5-v2-r0 Gazebo and MoveIt only; G7 runtime-002 recorder/video stopped and execute exited
preserved_processes: tmux codex, codex-temp, kimi, and so101-py-qual; unrelated worktrees and processes untouched
confirmed_conclusions:
  - G7 smaller feedback correction materially improves the pre-release XY target error
  - the cup is already strongly tilted before opening; opening itself is not the primary source of tilt
  - q6=0.74 contributes negligible additional motion in this run and remains unchanged
  - R1 fixed retreat is reliable as a robot recovery path but cannot prevent cup displacement while fixed-finger contact persists
disproven_routes:
  - more static XY/Z target compensation from one fall sample
  - attributing the observed pre-open tilt to finger opening
open_risks:
  - carry/descent dynamics may be stochastic and may require a policy-level place waypoint change if speed reduction alone is insufficient
next_command: implement and validate one preregistered G8 carry-speed profile with a non-relaxing pre-release tilt diagnostic, then RESET_WORLD
```

## PHY5-G8 carry stability before release

```yaml
experiment_id: PHY5-G8-RED
status: PREREGISTERED
prior_experiment: PHY5-G7-RUNTIME-002
hypothesis: H-G8; reducing the carry/descent speed profile will reduce inertial slip, keep the cup close to vertical before opening, and allow the retained G7 alignment plus R1 retreat to finish inside the 10 mm circle.
prediction:
  - unchanged grasp, G4 micro-lift gate, G6 sampling retry, G7 alignment target/tolerance, q6=0.74, final acceptance, and RESET_WORLD lifecycle
  - only MOVE_ABOVE_PLACE and DESCEND_TO_PLACE velocity/acceleration scaling are reduced as one carry-speed profile variable
  - diagnostic phase samples explicitly report tilt at LIFT_END, MOVE_ABOVE_PLACE_END, DESCEND_TO_PLACE_END, and RELEASE_START
  - MOVE_ABOVE_PLACE_END and DESCEND_TO_PLACE_END tilt are materially below G7 runtime-002; cup loses fixed-finger contact before RETREAT
single_variable: carry/descent velocity and acceleration profile
success_criteria:
  - automated RED/GREEN and build pass
  - fresh RESET_WORLD physical run reaches release with materially reduced pre-open tilt
  - authoritative final cup is upright, contact-free, scene-synchronized, and strictly inside the 10 mm center circle
failure_criteria:
  - unchanged or worse pre-open tilt, persistent fixed-finger contact, or any existing safety/acceptance regression
invalid_criteria:
  - provenance/reset/evidence/duplicate failure or FULL_RESTART
decision: PENDING_IMPLEMENTATION
next_experiment: PHY5-G8-RUNTIME-001 only after automated GREEN
```

## PHY5-G8 results

```yaml
experiment_id: PHY5-G8-RED
status: VALID
observed:
  - RED failed on the preregistered MOVE_ABOVE_PLACE velocity 0.05 contract
  - GREEN changes only carrying velocity scaling: MOVE_ABOVE_PLACE 0.10 to 0.05 and DESCEND_TO_PLACE 0.05 to 0.03; acceleration, waypoints, q6, target, and acceptance remain unchanged
  - build passed; package result 214 tests, 0 errors, 0 failures, 2 skipped; source/installed motion policy hashes match at fba29550038074b745bb394a2e198a7793c9d8a0ef0718f878fd7cee1f461284
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g8-red/red.log sha256=9dcb46bc79042fd2f75a1d20dfc2b7ab8a1e7a92eb4cfa4376ed7055c24891ad
  - /tmp/so101-physical-five-success-v2/phy5-g8-red/green-package.log sha256=ced46befd0aae6f9f156d956a187b369eba3bdc39698c824d69a0becb7e566bc
  - /tmp/so101-physical-five-success-v2/phy5-g8-red/build.log sha256=c4df531e0e175f2b79590580416280eebb16895f49d856b4a4749875e1c7573c
  - /tmp/so101-physical-five-success-v2/phy5-g8-red/test-result.log sha256=649612b6b467a257def449fe50579a1b8970d12825d846acb4a2ca6ea28b5af4
decision: GREEN
```

```yaml
experiment_id: PHY5-G8-RUNTIME-001
status: VALID_UPSTREAM_FAILURE
lifecycle: RESET_WORLD
observed:
  - first reset set_pose timed out and was invalid before execute; unchanged RESET_WORLD retry proved all reset postconditions with 0.0000017464519474885777 m pose error
  - execution failed before carry with CUP_INSUFFICIENT_LIFT: lift -0.146762 mm and lateral drift 1.57513 mm
  - G8 was not exercised and no attribution is made to its speed profile
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g8-runtime-001/reset/reset-attempt-001.log sha256=5fef34340f58c6f17a3637b37532ac0f245bf6457fcd7ccfa155206f3ca11704
  - /tmp/so101-physical-five-success-v2/phy5-g8-runtime-001/reset/reset-world.json sha256=685382294de8609f8dac3d80b811d7012f759817905c65f32dde865c6e990092
  - /tmp/so101-physical-five-success-v2/phy5-g8-runtime-001/run/execute.log sha256=52ad5eb7e3a8fd45763911cf56661be89266b9bb0bd13bb9faa873fc2cac1806
  - /tmp/so101-physical-five-success-v2/phy5-g8-runtime-001/run/physical-failure.json sha256=05e640bcbb07c3688f43bea7af9dad9ce778c817384671c5d93c25c25cd700d7
decision: KEEP_CONFIGURATION_AND_REPEAT
```

```yaml
experiment_id: PHY5-G8-RUNTIME-002
status: VALID
lifecycle: RESET_WORLD
observed:
  - RESET_WORLD_PROVED with 0.0000019038278011399631 m object-pose error
  - physical gate passed: 0.825956 mm micro-lift and 0.622523 mm lateral drift
  - G8 reduced DESCEND_TO_PLACE_END tilt from G7's 0.47239 rad to 0.127442 rad; MOVE_ABOVE_PLACE_END tilt was 0.267841 rad
  - live alignment reduced XY target error from 9.24390 mm to 3.12964 mm; immediate release-start bottom clearance remained 6.83586 mm and tilt 0.181561 rad
  - fixed-finger contact persisted through q6=0.74; opening displacement was 0.966074 mm and RETREAT-to-final displacement was 29.2565 mm
  - final cup was upright, Gazebo detached, MoveIt world-only, and contact-free at (-0.0920810,-0.2369106,0.1650000), but failed FINAL_OUT_OF_REGION
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g8-runtime-002/reset/reset-world.json sha256=f5805e6d99f80d87c0f81de49896b35211f4801e72a79f1b64c3624edeb13a06
  - /tmp/so101-physical-five-success-v2/phy5-g8-runtime-002/run/execute.log sha256=74795aca80c1dee881d8ff69c35d49fe64ba96977b64ef25f8b199ee2d8535cb
  - /tmp/so101-physical-five-success-v2/phy5-g8-runtime-002/run/physical-gate.json sha256=5470ea2ae733a29dc19f969157d6a4b56791bbb0af930311d3512533cd6e47a0
  - /tmp/so101-physical-five-success-v2/phy5-g8-runtime-002/run/final-outcome-failure.json sha256=8123646d155e98d748e28f3fb7dba797376f276d3c70f72faecdeb658a5b41e8
  - /tmp/so101-physical-five-success-v2/phy5-g8-runtime-002/run/tilt-analysis.json sha256=3d651bb0ef3bf68e80bb1a4447000dce10e36fc107d728ec4b894f465ee0bb62
  - /tmp/so101-physical-five-success-v2/phy5-g8-runtime-002/run/release-analysis.json sha256=bbbf9b2eea3b1296c8e057e7fc152876f086eef935f646cd22147e971bb19b82
  - /tmp/so101-physical-five-success-v2/phy5-g8-runtime-002/run/diagnostic/samples.jsonl sha256=f49f8af5fc66929cec0844c4fa9b79d18a83f95d7110d9c1dea182d9b4e3b4dc
  - /tmp/so101-physical-five-success-v2/phy5-g8-runtime-002/run/diagnostic/gazebo-gui.mp4 sha256=6f02006e626c05a85e0ffdd0d265da25d8c1b2cc62b540bf737e35c127c43e3d
decision: G8_EFFECTIVE_FOR_DESCENT_BUT_RELEASE_CLEARANCE_DOMINANT; retain G8 and preregister bounded release seating
next_experiment: PHY5-G9-RED
```

## PHY5-G9 pose-aware release seating

```yaml
experiment_id: PHY5-G9-RED
status: VALID
hypothesis: lower the tilted cup in world Z to a computed 1 mm bottom clearance before opening so table support occurs before fixed-finger RETREAT displacement
single_variable: pre-release bottom clearance target 1 mm
safety_bounds:
  - XY translation is exactly zero
  - maximum downward correction is 10 mm
  - measured post-move clearance must be between -0.5 mm and 3 mm
  - q6, G7 alignment, G8 speed profile, target region, and all grasp/final gates remain unchanged
observed:
  - RED failed at missing release_seating_translation import
  - GREEN owning tests 42 passed; build passed; package result 217 tests, 0 errors, 0 failures, 2 skipped
  - live_execute source/runtime hash matches at 6f212d1c741785eafb9fe60f63f29911eed8b0f251684798c926cd7ec4b0ad07
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g9-red/red.log sha256=f4755f5623c5080d60c937b0e1165cedf07b8a12cc7258366a129d6f6a61072c
  - /tmp/so101-physical-five-success-v2/phy5-g9-red/green-owning.log sha256=2cf363ce4ecdfd7a1ba71469c62ac22c9d925143a947af7debe8c0e9ed68d0f8
  - /tmp/so101-physical-five-success-v2/phy5-g9-red/build.log sha256=7b5b013fe98cefb5aab33deaa203b4632ffb40130c8cc8e983ad6a0b07b8353e
  - /tmp/so101-physical-five-success-v2/phy5-g9-red/test-result.log sha256=6986c10e6264204bcb2c1589e1bd8734fefe1d905418296a2c44acb4de6fe1df
decision: AUTOMATED_GREEN_PHYSICAL_UNRESOLVED
```

```yaml
experiment_id: PHY5-G9-RUNTIME-001
status: VALID_UPSTREAM_FAILURE
lifecycle: RESET_WORLD
observed:
  - RESET_WORLD_PROVED with 0.0000016057900211635848 m object-pose error
  - physical grasp gate passed, but DESCEND_TO_PLACE controller aborted with error_code -4 path tolerance violation before G9
decision: KEEP_CONFIGURATION_AND_REPEAT
```

```yaml
experiment_id: PHY5-G9-RUNTIME-002
status: VALID_UPSTREAM_FAILURE
lifecycle: RESET_WORLD
observed:
  - RESET_WORLD_PROVED with 0.0000005930963352966882 m object-pose error
  - target penetration adjustment failed closed with fixed-finger contact but no stable moving-jaw contact; no carry, alignment, or G9 seating occurred
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g9-runtime-002/reset/reset-world.json sha256=fd59582ee225cb45e8cf04ecad64afe491b61c92e80a07fadc84d1916d261655
  - /tmp/so101-physical-five-success-v2/phy5-g9-runtime-002/run/execute.log sha256=5ce8075bd46fbfd28221d15d2db7fd21820bdabdc68c81b394e449e7cf226934
  - /tmp/so101-physical-five-success-v2/phy5-g9-runtime-002/run/physical-failure.json sha256=3cc19934ea7eb28339016970dba8c9e719c7a5d3a526b4844e4159f5d9bd01c2
  - /tmp/so101-physical-five-success-v2/phy5-g9-runtime-002/run/diagnostic/samples.jsonl sha256=9da2f7cbcf83fd49834f11aa167fb25c1f898922e27542d248d9bb055bd3dbeb
  - /tmp/so101-physical-five-success-v2/phy5-g9-runtime-002/run/diagnostic/gazebo-gui.mp4 sha256=f87d602aa5cb5c02bd6fe366e5f5c6b7a90d40051493facf2a8e20888181ec66
decision: G9_PHYSICAL_UNRESOLVED; stop repeated sampling and address upstream grasp/carry repeatability before another G9 attempt
next_experiment: PHY5-G10-DESIGN_OR_G9_RUNTIME_003 only after reviewing upstream failure distribution
```

```yaml
checkpoint_id: CP-V2-G9-RUNTIME-002-VALID-048
recorded_at: 2026-08-11 Asia/Shanghai
last_valid_experiment: PHY5-G9-RUNTIME-002
current_hypothesis: G8 reduces descent tilt, while a low-clearance release is still the most direct candidate for eliminating fixed-finger RETREAT displacement; G9 lacks physical evidence because two attempts failed upstream
working_tree_status: expected dirty G2/G3/G4/G6/G7/G8/G9/R1, target contract/marker, tests, provenance, and ledger; git diff check clean
owned_processes: existing tmux so101-phy5-v2-r0 Gazebo and MoveIt only; no execute, recorder, or video
preserved_processes: unrelated tmux sessions, worktrees, and processes untouched
qualification_status: NOT_STARTED; no frozen candidate has one complete success, so a five-run streak would be invalid
next_command: inspect G8/G9 upstream failure distribution and decide whether to improve grasp repeatability or run one unchanged G9 sample
```

## PHY5-G9-RUNTIME-003 user-observed unchanged retry

```yaml
experiment_id: PHY5-G9-RUNTIME-003
status: VALID
prior_experiment: PHY5-G9-RUNTIME-002
hypothesis: the unchanged G9 candidate can pass the stochastic upstream grasp and controller gates and exercise pose-aware release seating for the first physical observation
prediction:
  - fresh RESET_WORLD proves detached Gazebo, MoveIt world-only plastic_cup, no finger contact, finite TCP, and canonical cup pose
  - source/install/runtime hashes remain identical to the G9 automated GREEN candidate
  - if upstream gates pass, release_seating is non-empty, Z-only, no more than 10 mm downward, and measured post-seating bottom clearance is within [-0.5, 3] mm
  - final outcome is recorded authoritatively regardless of success or failure
single_variable: NONE; unchanged fixed-configuration retry requested by user
lifecycle: RESET_WORLD
preconditions:
  - reuse only tmux so101-phy5-v2-r0 Gazebo and MoveIt windows
  - ROS_DOMAIN_ID=189 and GZ_PARTITION=so101_phy5_v2_r0_001
  - no existing pick_place_state_machine, diagnostic recorder, or experiment video process
success_criteria:
  - G9 release seating is physically exercised with complete 50 Hz samples and Gazebo video
  - authoritative DONE requires upright, support-contacting, gripper-contact-free, Gazebo-detached, MoveIt-world-only cup strictly inside the 10 mm center circle
failure_criteria:
  - complete evidence at the first fail-closed boundary, explicitly distinguishing upstream rejection from an exercised G9 failure
invalid_criteria:
  - provenance mismatch, failed reset, duplicate stack/execute, missing evidence, or FULL_RESTART
provenance:
  source_commit: ef73c10f159c270b91748a41df9c4bac728fde80
  install_overlay: /data/work/ws_moveit/.worktrees/so101-physical-five-success/install
  runtime_executable: /data/work/ws_moveit/.worktrees/so101-physical-five-success/install/so101_gazebo_demo_py/lib/so101_gazebo_demo_py/pick_place_state_machine
  ros_domain_id: 189
  gz_partition: so101_phy5_v2_r0_001
commands:
  - command: ros2 run so101_gazebo_demo_py reset_so101_world --timeout 15
    exit_code: 0
  - command: ros2 run so101_gazebo_demo_py pick_place_state_machine --mode execute --planning-diagnostics-dir <run>/planning
    exit_code: 1
observed:
  - RESET_WORLD_PROVED with 0.0000007269599716807382 m object-pose error, Gazebo detached, MoveIt world-only plastic_cup, no finger contact, and finite TCP
  - live_execute source/runtime hash 6f212d1c741785eafb9fe60f63f29911eed8b0f251684798c926cd7ec4b0ad07; backend source/runtime hash 6a8861f72038766ca9ea1f00b91be18a8465d4f94d1ba4e76bd13c8657d1ca84; motion source/install hash fba29550038074b745bb394a2e198a7793c9d8a0ef0718f878fd7cee1f461284
  - execution failed at POST_SEATING_PHYSICAL_STABILITY before micro-lift/carry/G9 release seating; the stable-window result had fixed_finger=True, moving_jaw=False, fixed penetration 0.719631 mm, and no moving-pad penetration sample
  - q6 contact was -0.0476062 rad and requested seating target was -0.0536062 rad; Gazebo remained detached
  - final diagnostic snapshot remained at the pick pose: cup (0.0201946,-0.2801743,0.1650011), q6 -0.0516038 rad, table contact, and near-zero bottom clearance; the final asynchronous snapshot contained both pad contacts but does not replace the failed stable-window evidence
  - visual evidence shows the cup still at its original pick location and the arm stopped in the grasp pose; no lift, place, release, or G9 Z seating occurred
inferred:
  - NONE
conclusion: VALID_UPSTREAM_FAILURE; unchanged G9 still has no physical release-seating result because the grasp stability gate rejected the sample before carry
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g9-runtime-003/reset/reset-world.json sha256=f62caa3f469fd992aff60714922fa1bab88fa89ec8b3e599e14d68344fe97556
  - /tmp/so101-physical-five-success-v2/phy5-g9-runtime-003/run/execute.log sha256=b74738c32772d76545a5660d30a66ab00d0d37848821717b4d4e789074d0f4ea
  - /tmp/so101-physical-five-success-v2/phy5-g9-runtime-003/run/physical-failure.json sha256=b696b7a1a967e0fd9a7995a818b0209e77f7332ffa9d524e23f75c135e88a413
  - /tmp/so101-physical-five-success-v2/phy5-g9-runtime-003/run/diagnostic/samples.jsonl sha256=fdb76873b1e7fb24032dcce8675204104a08db4f0c4c5d756d7b00a1c99aa88e
  - /tmp/so101-physical-five-success-v2/phy5-g9-runtime-003/run/diagnostic/gazebo-gui.mp4 sha256=8f3c1b84aad5882c961aa014856e03aa43922bae1746f70446d81da8e4785a99
  - /tmp/so101-physical-five-success-v2/phy5-g9-runtime-003/run/final-desktop.png sha256=2bc37efa77a4f501c998c1be055a8c38ea19b2252e444a65ac8453525133f92d
decision: KEEP_G9_BUT_STOP_UNCHANGED_REPEATS; investigate the repeated moving-pad stable-window loss before requesting another G9 sample
next_experiment: PHY5-G10-GRASP-STABILITY-DESIGN
```

```yaml
checkpoint_id: CP-V2-G9-RUNTIME-003-VALID-049
recorded_at: 2026-08-11 Asia/Shanghai
last_valid_experiment: PHY5-G9-RUNTIME-003
current_hypothesis: G9 release seating remains plausible but is unreachable often enough that moving-pad grasp stability is now the first failing boundary
working_tree_status: expected dirty G2/G3/G4/G6/G7/G8/G9/R1, target contract/marker, tests, provenance, and ledger; no cleanup performed
owned_processes: existing tmux so101-phy5-v2-r0 Gazebo and MoveIt only; no execute, recorder, video, or capture window
preserved_processes: unrelated tmux sessions, worktrees, and processes untouched
confirmed_conclusions:
  - this unchanged retry did not exercise G9 and cannot be used to judge G9 release behavior
  - POST_SEATING_PHYSICAL_STABILITY moving-pad loss has now repeated in G9 runtime-002 and runtime-003
open_risks:
  - final asynchronous bilateral contact conflicts with the earlier failed stability window and requires time-window analysis before any grasp-policy change
  - five-run qualification remains NOT_STARTED
next_command: analyze runtime-002/runtime-003 moving-pad contact and q6 timing windows before modifying or rerunning
```

## PHY5-G10 bounded normalization exhaustion continuation

```yaml
experiment_id: PHY5-G10-STRATEGY
status: PLANNED
hypothesis: requiring the 0.5-1.1 mm moving-pad target window before any physical probe rejects recoverable grasps; after bounded normalization retries, a guarded 2 mm micro-lift can provide the authoritative cup/arm outcome without weakening the hard penetration ceiling
prediction:
  - target-window success remains unchanged and is recorded as proved
  - ordinary normalization exhaustion records final contact evidence and proceeds to the existing 2 mm micro-lift stage
  - moving-pad penetration above 1.3 mm still fails immediately before micro-lift
  - q6 safe lower bound and the existing micro-lift continuation gate remain unchanged and fail closed
single_variable: on ordinary target-penetration adjustment exhaustion, continue to the existing physical micro-lift instead of raising POST_SEATING_PHYSICAL_STABILITY
lifecycle: RESET_WORLD
automated_acceptance:
  - RED proves the new opt-in continuation contract is absent before implementation
  - focused tests prove exhaustion continuation, default fail-close compatibility, and hard-ceiling fail-close behavior
  - package build and complete package tests pass from the owning worktree overlay
runtime_acceptance:
  - one RESET_WORLD run reaches the micro-lift command after ordinary normalization exhaustion, or records the first unchanged safety boundary with complete telemetry and video
invalid_criteria:
  - FULL_RESTART, provenance mismatch, duplicate execute/recorder, missing reset proof, or bypass of the 1.3 mm hard ceiling
provenance:
  source_commit: ef73c10f159c270b91748a41df9c4bac728fde80
  worktree: /data/work/ws_moveit/.worktrees/so101-physical-five-success
  branch: codex/so101-physical-five-success
  ros_domain_id: 189
  gz_partition: so101_phy5_v2_r0_001
decision: PENDING_RED
```

```yaml
experiment_id: PHY5-G10-STRATEGY
status: AUTOMATED_GREEN
observed:
  - RED failed 3/3 because the continuation option, live-path wiring, and telemetry were absent
  - focused owning tests passed 62/62 after implementation
  - owning package built successfully with matching source/runtime live_execute sha256 a954b254e7f582ded17b35652e0abf955dffa0d4c04f4e7c3951c0366df789af
  - complete package tests passed 219 with 2 skipped; git diff check and Python syntax check passed
  - default callers remain fail-close on exhaustion; both stable-window and final-evidence observations remain fail-close above the 1.3 mm moving-pad ceiling
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g10-strategy/red.log sha256=f01117d0ab8c7e9cb650df77747d24d6573bec8f9963c5eab0a3b0c191d42d35
  - /tmp/so101-physical-five-success-v2/phy5-g10-strategy/green-owning.log sha256=e7d48ca2dfd0557b4170700ff74cdbfc7f8997e6aa54cff328a7af8463a38f51
  - /tmp/so101-physical-five-success-v2/phy5-g10-strategy/build.log sha256=afff7f5ee2f3b78c1b8b74eef00ab85e8c701f10305126d80dbd4ef62cf7bbd6
  - /tmp/so101-physical-five-success-v2/phy5-g10-strategy/test-result.log sha256=1f83ff4ec2fd0d3ff1d5c06a00e5b265de7b5a99a4356f2b35629a7407e6cffc
decision: AUTOMATED_GREEN_RUNTIME_PENDING
```

```yaml
experiment_id: PHY5-G10-RUNTIME-001
status: PLANNED
prior_experiment: PHY5-G9-RUNTIME-003
hypothesis: when bounded target-depth normalization cannot prove its preferred moving-pad window, the existing guarded micro-lift can distinguish a physically carried cup from a failed grasp without treating normalization exhaustion itself as terminal
prediction:
  - fresh RESET_WORLD proves Gazebo detached, MoveIt world-only cup, no finger contact, finite TCP, and canonical cup pose
  - if normalization exhausts ordinarily, seating_telemetry records target_penetration_proved false and continued_after_adjustment_exhaustion true
  - after ordinary exhaustion the run issues the existing 2 mm micro-lift; its cup/arm continuation gate remains authoritative and fail-close
  - any moving-pad depth above 1.3 mm still terminates before micro-lift
single_variable: G10 exhaustion continuation implemented by PHY5-G10-STRATEGY
lifecycle: RESET_WORLD
preconditions:
  - reuse only tmux so101-phy5-v2-r0 Gazebo and MoveIt windows
  - ROS_DOMAIN_ID=189 and GZ_PARTITION=so101_phy5_v2_r0_001
  - no existing pick_place_state_machine, diagnostic recorder, or experiment video process
success_criteria:
  - ordinary normalization exhaustion reaches the micro-lift evidence boundary with complete 50 Hz samples and Gazebo video
  - if the preferred target window is proved instead, the unchanged downstream path is recorded without claiming exhaustion validation
failure_criteria:
  - complete evidence at the first unchanged fail-close safety boundary
invalid_criteria:
  - FULL_RESTART, provenance mismatch, failed reset, duplicate stack/execute, or missing evidence
provenance:
  source_commit: ef73c10f159c270b91748a41df9c4bac728fde80
  live_execute_sha256: a954b254e7f582ded17b35652e0abf955dffa0d4c04f4e7c3951c0366df789af
  backend_sha256: 6a8861f72038766ca9ea1f00b91be18a8465d4f94d1ba4e76bd13c8657d1ca84
  motion_policy_sha256: fba29550038074b745bb394a2e198a7793c9d8a0ef0718f878fd7cee1f461284
  install_overlay: /data/work/ws_moveit/.worktrees/so101-physical-five-success/install
  ros_domain_id: 189
  gz_partition: so101_phy5_v2_r0_001
decision: PENDING_RESET_WORLD
```

```yaml
experiment_id: PHY5-G11-RUNTIME-002
status: VALID_UPSTREAM_FAILURE
lifecycle: RESET_WORLD
observed:
  - RESET_WORLD_PROVED with 0.000001062883128505557 m object-pose error, Gazebo detached, MoveIt world-only plastic_cup, no finger contact, and finite TCP
  - current source/runtime live_execute sha256 e8c6906f783ac3f9abde3101637e40bce97684f1d722b7560d7fc8411a14f061 matched
  - target normalization exhausted 4 adjustments with fixed-only final observation and recorded the bilateral stability timeout instead of failing closed
  - seating telemetry recorded target_penetration_proved false, continued_after_adjustment_exhaustion true, and the complete stability_observation
  - existing micro-lift outcome gate then passed on attempt 2: cup Z +0.540242 mm, lateral drift 0.143583 mm, position error 1.466803 mm; post-lift bilateral contact was observed and moving-pad depth remained below the 1.3 mm ceiling
  - the next unchanged boundary failed later with arm controller error_code -4 path tolerance violation; no claim is made about pre-release observation in this sample
  - 11524 diagnostic samples, a fresh 3840x2160 screenshot, and a decodable H.264 avc1 1888x1046 10 fps 235.2 s video were retained
conclusion: G11 grasp-side ordinary bilateral timeout is physically proved observational rather than fail-close; release-side timeout continuation is automated-behavior proved but not physically exercised by this sample
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g11-runtime-002/reset/reset-world.json sha256=80ea945fbf99c05e1b826cfbbdb366ccb8610d058a46145e0abf4b83c9c577ad
  - /tmp/so101-physical-five-success-v2/phy5-g11-runtime-002/run/execute.log sha256=e4db5c48fd75cbdecb884ffd0e849a0af51579345e097bed81313d858094c21e
  - /tmp/so101-physical-five-success-v2/phy5-g11-runtime-002/run/physical-gate.json sha256=057823634009c6bd2c0c19950a81a9c5e21ef0d418b495b7be88d99fbaafdcaf
  - /tmp/so101-physical-five-success-v2/phy5-g11-runtime-002/run/diagnostic/samples.jsonl sha256=61fc4aa52aad8320e3246c4849aa6301c678e5aaedf88eb0c2eaa138d6a552d6
  - /tmp/so101-physical-five-success-v2/phy5-g11-runtime-002/run/diagnostic/gazebo-gui.mp4 sha256=afcaf0e306d171e0c1499c7695cc1f6f3c02df0d4fe736570be599db26959f90
  - /tmp/so101-physical-five-success-v2/phy5-g11-runtime-002/run/final-desktop.png sha256=d23bb75c48a411ddc1fff33a348690cd86d5731027a4d458eb98e04b8a715ffa
decision: KEEP_G11_POLICY; stop repeated sampling and address the existing carry/controller repeatability before the next placement experiment
```

```yaml
checkpoint_id: CP-V2-G11-RUNTIME-002-VALID-050
recorded_at: 2026-08-11 Asia/Shanghai
last_valid_experiment: PHY5-G11-RUNTIME-002
current_hypothesis: bilateral stability should remain analysis/strategy-selection telemetry, while cup/arm outcomes and hard physical limits govern continuation
working_tree_status: expected dirty G2/G3/G4/G6/G7/G8/G9/G10/G11/R1, target contract/marker, tests, provenance, and ledger; git diff check clean; no cleanup performed
owned_processes: existing tmux so101-phy5-v2-r0 Gazebo and MoveIt only; no execute, recorder, video, or capture process
confirmed_conclusions:
  - ordinary target-normalization bilateral timeout no longer fails closed and physically reached a proved micro-lift on the current runtime
  - ordinary pre-release bilateral timeout is behavior-tested to record telemetry and open; moving-pad penetration above 1.3 mm remains fail-close
  - complete package result is 223 tests with 221 passed and 2 skipped
open_risks:
  - release-side timeout continuation has not yet been physically exercised on the final evidence-payload build
  - carry path tolerance violation and final placement dispersion still prevent a frozen five-success candidate
  - five-run qualification remains NOT_STARTED
next_command: analyze the existing DESCEND_TO_PLACE path-tolerance failure distribution before another physical sample; do not repeat G11 unchanged solely to chase release-side telemetry
```

```yaml
experiment_id: PHY5-G11-RUNTIME-001
status: INVALID_NEW_TELEMETRY_PROVENANCE
lifecycle: RESET_WORLD
observed:
  - RESET_WORLD_PROVED with 0.0000016642111579179987 m object-pose error, Gazebo detached, MoveIt world-only plastic_cup, no finger contact, and finite TCP
  - target penetration was proved at 0.587442 mm without adjustment; micro-lift passed on attempt 1 with cup Z +1.129881 mm and lateral drift 0.192319 mm
  - execution passed release, fixed RETREAT, Gazebo/MoveIt detach, settling, support-contact, upright, and gripper-contact-free checks
  - authoritative final failure was FINAL_OUT_OF_REGION at cup center (-0.0653117,-0.3041406), about 49.45 mm from target center (-0.080,-0.255); upright tilt was 0.00000554 rad
  - 22 final samples agreed; Gazebo detached, MoveIt world-only, support contact true, gripper contact false
  - H.264 avc1 Gazebo video is decodable at 1888x1046, 10 fps, 164.6 s; final screenshot is 3840x2160
invalid_reason: this run used live_execute sha256 f66074a47639a2ebe2d8534da399eb88ab743b2b7344f5258cf88484147608c7, before release_preparation telemetry was added to final-outcome-failure.json; behavior evidence is valid but the requested diagnostic payload is incomplete
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g11-runtime-001/reset/reset-world.json sha256=d654a7559daefdbb9c53b452ae2257bbf7fe6307e486b35808c8c8156d581e
  - /tmp/so101-physical-five-success-v2/phy5-g11-runtime-001/run/execute.log sha256=516bebc216a845e53c9a2eddc673d0e9cd961a5e95ba5857df723509bc3a9e9a
  - /tmp/so101-physical-five-success-v2/phy5-g11-runtime-001/run/physical-gate.json sha256=09f08030fcedf5300738f869a840eb341bd76535b8ab06469d249f84b0406eb3
  - /tmp/so101-physical-five-success-v2/phy5-g11-runtime-001/run/final-outcome-failure.json sha256=10bc9be82ab6e7f832675cd4aedd381c183a8e10ac14c6d09ba9aeaa5722bf66
  - /tmp/so101-physical-five-success-v2/phy5-g11-runtime-001/run/diagnostic/samples.jsonl sha256=0356f9103c7fd0c1ca5e35973dca82bf83ec1be31355d9a487b80d32a19d261f
  - /tmp/so101-physical-five-success-v2/phy5-g11-runtime-001/run/diagnostic/gazebo-gui.mp4 sha256=b485c7565855247985b8fc6417bae69fd8d5017c00a667ec3e21e11a909d99a2
  - /tmp/so101-physical-five-success-v2/phy5-g11-runtime-001/run/final-desktop.png sha256=fbc0d0c5656bca2bd967993967560910af74822bd00084d5df9da81a8ca06e27
decision: retain as physical behavior evidence; repeat once with current evidence payload provenance
next_experiment: PHY5-G11-RUNTIME-002
```

```yaml
experiment_id: PHY5-G11-EVIDENCE-PAYLOAD
status: AUTOMATED_GREEN
observed:
  - RED proved final-outcome-failure.json omitted release_preparation observations
  - final failure and DONE payloads now share the same release_preparation telemetry
  - complete package tests passed 221 with 2 skipped; source/runtime hash match and git diff check passed
provenance:
  live_execute_sha256: e8c6906f783ac3f9abde3101637e40bce97684f1d722b7560d7fc8411a14f061
decision: PROCEED_TO_ONE_RESET_WORLD_RUNTIME
```

```yaml
experiment_id: PHY5-G11-RUNTIME-002
status: PLANNED
prior_experiment: PHY5-G11-RUNTIME-001
hypothesis: current G11 runtime preserves bilateral stability as analysis telemetry in both success and final-failure evidence while never using ordinary timeout as a live fail-close gate
prediction:
  - fresh RESET_WORLD and current source/runtime hash are proved
  - if release is reached, release_preparation is present in DONE or final-outcome-failure with initial_bilateral, bilateral, bilateral_stability_proved, stability_observation, and moving-pad depth
  - ordinary bilateral timeout still proceeds; 1.3 mm hard ceiling and all cup/arm/final gates remain authoritative
single_variable: EVIDENCE_PAYLOAD_ONLY relative to G11 runtime-001; behavioral strategy unchanged
lifecycle: RESET_WORLD
success_criteria:
  - authoritative runtime evidence contains release_preparation observations, complete 50 Hz samples, decodable video, and fresh screenshot
failure_criteria:
  - complete evidence at the first unchanged safety or outcome boundary
invalid_criteria:
  - FULL_RESTART, provenance mismatch, failed reset, duplicate execute/recorder, or incomplete evidence
provenance:
  source_commit: ef73c10f159c270b91748a41df9c4bac728fde80
  live_execute_sha256: e8c6906f783ac3f9abde3101637e40bce97684f1d722b7560d7fc8411a14f061
  ros_domain_id: 189
  gz_partition: so101_phy5_v2_r0_001
decision: PENDING_RESET_WORLD
```

```yaml
experiment_id: PHY5-G10-RUNTIME-001
status: INVALID_EVIDENCE
lifecycle: RESET_WORLD
observed:
  - RESET_WORLD_PROVED with 0.0000007448197370876408 m object-pose error, Gazebo detached, MoveIt world-only plastic_cup, no finger contact, and finite TCP
  - target-depth normalization exhausted all 4 adjustments at normalized q6 -0.0574811; telemetry explicitly recorded target_penetration_proved false and continued_after_adjustment_exhaustion true
  - the existing physical micro-lift gate ran and passed on attempt 2: cup Z +2.108485 mm, lateral drift 0.088665 mm, position error 0.140108 mm, Gazebo detached
  - the run later failed at the unchanged pre-release bilateral-contact recovery: fixed finger absent, moving jaw present, moving-pad depth 1.119782 mm
  - final cup was support-contacting near the target but tilted 18.026 degrees while still held by the gripper; no release occurred
  - diagnostic recorder captured 13552 JSONL samples and a fresh 3840x2160 screenshot
invalid_reason: ffmpeg was terminated with its tmux window before writing the MP4 moov index; gazebo-gui.mp4 is not decodable, violating the pre-registered complete-video requirement
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g10-runtime-001/reset/reset-world.json sha256=1ed006f231152304b7f682ed3bb5620342b7720ce24ef0ce3ffee11f7e85538c
  - /tmp/so101-physical-five-success-v2/phy5-g10-runtime-001/run/execute.log sha256=5614835724b7dc41c3bdc23343e248fb518693b499c5ccc78780a6dd64c0ee33
  - /tmp/so101-physical-five-success-v2/phy5-g10-runtime-001/run/physical-gate.json sha256=1013a75b736420ac2bf33618418e84b646349b303a5018b7c263f5b2051af87e
  - /tmp/so101-physical-five-success-v2/phy5-g10-runtime-001/run/diagnostic/samples.jsonl sha256=0271c78e7156fdfc00c06ba39e7efb9dd0d9c4356725c0b51ba1a59bbc17e998
  - /tmp/so101-physical-five-success-v2/phy5-g10-runtime-001/run/final-desktop.png sha256=1e1b933dfc51034fd1315576faf94649f282fc50816e439d982f71fa2ea7ef84
decision: DISCARD_FROM_FORMAL_RUNTIME_ACCEPTANCE; retain only as diagnostic evidence that the requested branch was exercised
next_experiment: PHY5-G10-RUNTIME-002 with unchanged policy and graceful ffmpeg SIGINT finalization
```

```yaml
experiment_id: PHY5-G10-RUNTIME-002
status: PLANNED
prior_experiment: PHY5-G10-RUNTIME-001
hypothesis: the unchanged G10 strategy will again exercise either proved target penetration or exhaustion continuation, while graceful recorder/video shutdown will produce complete formal evidence
prediction:
  - fresh RESET_WORLD proves the canonical detached initial state
  - target normalization outcome and any micro-lift outcome are recorded exactly as observed
  - ffmpeg receives SIGINT and produces a decodable H.264 MP4 with nonzero duration
single_variable: EVIDENCE_FINALIZATION_ONLY; G10 source, policy, limits, and runtime overlay unchanged
lifecycle: RESET_WORLD
success_criteria:
  - authoritative runtime JSON plus complete 50 Hz samples, decodable Gazebo video, and fresh screenshot
  - if ordinary normalization exhausts, the existing 2 mm micro-lift is physically exercised
failure_criteria:
  - complete evidence at the first unchanged fail-close safety boundary
invalid_criteria:
  - FULL_RESTART, provenance mismatch, failed reset, duplicate execute/recorder, or incomplete evidence
provenance:
  source_commit: ef73c10f159c270b91748a41df9c4bac728fde80
  live_execute_sha256: a954b254e7f582ded17b35652e0abf955dffa0d4c04f4e7c3951c0366df789af
  ros_domain_id: 189
  gz_partition: so101_phy5_v2_r0_001
decision: PENDING_RESET_WORLD
```

```yaml
experiment_id: PHY5-G10-RUNTIME-002
status: SUPERSEDED_BEFORE_EXECUTE
lifecycle: RESET_WORLD
observed:
  - RESET_WORLD_PROVED with 0.0000018579312534110873 m object-pose error
  - no recorder, video, or pick_place_state_machine execute process was started
reason: user replaced the policy before execution; bilateral stability observations must no longer act as a fail-close gate
decision: NO_SAMPLE; preserve reset evidence only and proceed to PHY5-G11-OBSERVATIONAL-BILATERAL
```

## PHY5-G11 observational bilateral-contact policy

```yaml
experiment_id: PHY5-G11-OBSERVATIONAL-BILATERAL
status: AUTOMATED_GREEN
hypothesis: bilateral stability is useful diagnostic and strategy-selection data, but the cup/arm motion outcome is the authoritative continuation gate; ordinary bilateral timeout should not terminate grasp normalization or pre-release opening
prediction:
  - target-penetration exhaustion returns final contact telemetry by default instead of raising
  - unilateral pre-release contact may trigger the existing one-time reseat, but a subsequent ordinary bilateral timeout is recorded and the gripper still opens
  - moving-pad penetration above 1.3 mm remains fail-close before any continuation or release command
  - micro-lift, controller, release-seating, final upright/support/contact/detachment, and 10 mm placement bounds remain unchanged fail-close gates
single_variable: remove ordinary bilateral-stability timeout as a live fail-close condition
lifecycle: RESET_WORLD
automated_results:
  - RED failed 3/3 at the old target-normalization, pre-release stability, and live-path contracts
  - focused behavior tests passed 7/7 and owning files passed 97/97
  - owning package built successfully; complete package tests passed 220 with 2 skipped
  - git diff check, Python syntax check, and source/runtime hash match passed
  - live_execute source/runtime sha256 f66074a47639a2ebe2d8534da399eb88ab743b2b7344f5258cf88484147608c7
runtime_acceptance:
  - one RESET_WORLD physical-simulation run records the bilateral observations and reaches the next unchanged outcome boundary
invalid_criteria:
  - FULL_RESTART, provenance mismatch, bypass of the 1.3 mm hard ceiling, duplicate execute, or incomplete evidence
provenance:
  source_commit: ef73c10f159c270b91748a41df9c4bac728fde80
  worktree: /data/work/ws_moveit/.worktrees/so101-physical-five-success
  branch: codex/so101-physical-five-success
  ros_domain_id: 189
  gz_partition: so101_phy5_v2_r0_001
decision: AUTOMATED_GREEN_RUNTIME_PENDING
```

```yaml
experiment_id: PHY5-G11-RUNTIME-001
status: PLANNED
prior_experiment: PHY5-G10-RUNTIME-001
hypothesis: ordinary bilateral stability timeout can be retained as diagnostic telemetry while the existing cup/arm and final physical outcomes govern continuation
prediction:
  - fresh RESET_WORLD proves the canonical detached initial state
  - target normalization ordinary exhaustion cannot terminate the run and records stability_observation
  - pre-release ordinary bilateral timeout cannot terminate opening and records bilateral_stability_proved false plus stability_observation
  - the first unchanged physical outcome gate is authoritative
single_variable: PHY5-G11 observational bilateral-contact policy
lifecycle: RESET_WORLD
success_criteria:
  - new strategy reaches the next outcome boundary with authoritative JSON, complete 50 Hz samples, decodable Gazebo video, and fresh screenshot
failure_criteria:
  - complete evidence at an unchanged controller, hard-penetration, micro-lift, release-seating, or final-outcome boundary
invalid_criteria:
  - FULL_RESTART, provenance mismatch, failed reset, duplicate execute/recorder, or incomplete evidence
provenance:
  source_commit: ef73c10f159c270b91748a41df9c4bac728fde80
  live_execute_sha256: f66074a47639a2ebe2d8534da399eb88ab743b2b7344f5258cf88484147608c7
  ros_domain_id: 189
  gz_partition: so101_phy5_v2_r0_001
decision: PENDING_RESET_WORLD
```

```yaml
checkpoint_id: CP-V2-G11-TAIL-051
recorded_at: 2026-08-11 Asia/Shanghai
authoritative_result: PHY5-G11-RUNTIME-002
current_runtime_sha256: e8c6906f783ac3f9abde3101637e40bce97684f1d722b7560d7fc8411a14f061
summary: ordinary grasp-side bilateral stability timeout is physically proved observational and reached the existing micro-lift outcome gate; the run later stopped at unchanged arm-controller path tolerance error -4
release_side_status: ordinary timeout continuation and telemetry persistence are automated-behavior proved; not physically exercised on the final build
qualification_status: NOT_STARTED
next_command: analyze DESCEND_TO_PLACE path-tolerance repeatability before another RESET_WORLD sample
```

```yaml
experiment_id: PHY5-G11-RUNTIME-003
status: VALID_FAILURE
lifecycle: RESET_WORLD
observed:
  - RESET_WORLD_PROVED with 0.0000005969116517593637 m object-pose error, Gazebo detached, MoveIt world-only plastic_cup, no finger contact, and finite TCP
  - final source/runtime hash 392522b9b9748710850c0a3d1503eb3ec2f20652439c0a626cc979bfa14f6f39 matched
  - target normalization exhausted all 4 adjustments with fixed-only stable-window evidence; stability_observation recorded the bilateral timeout and continuation proceeded
  - micro-lift outcome passed on attempt 1: cup Z +4.733905 mm, lateral drift 0.783801 mm, position error 2.844043 mm; post-lift bilateral contact was observed and moving-pad depth remained below 1.3 mm
  - carry and same-run XY alignment reached the place side; the authoritative next failure was release seating correction -10.476447 mm, exceeding the unchanged 10 mm downward correction bound by 0.476447 mm
  - no open-gripper or final placement evaluation occurred
  - final asynchronous diagnostic sample placed cup center 7.991057 mm from target center, tilt 0.091669 rad, and bottom clearance 10.844510 mm while still held bilaterally; it does not replace the earlier release-seating calculation
  - 10328 samples, fresh 3840x2160 screenshot, and fully decodable H.264 avc1 1888x1046 10 fps 210.9 s video were retained
conclusion: ordinary bilateral stability timeout again did not fail close; the visible blocker is now the release-seating Z correction bound, not contact stability
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g11-runtime-003/reset/reset-world.json sha256=c2f844876471df63a574215c997f4b0a15a1c143d5188494e161be4ac16dcd70
  - /tmp/so101-physical-five-success-v2/phy5-g11-runtime-003/run/execute.log sha256=63e418fcaff50dfb52701ec5b7336d3cbca8ef7855b9d1048ac23e7cb4a6723f
  - /tmp/so101-physical-five-success-v2/phy5-g11-runtime-003/run/physical-gate.json sha256=7d635f4ba58639fb1b1ef6174954aba2d2f84dd613f1491c07ce01a0175a3b65
  - /tmp/so101-physical-five-success-v2/phy5-g11-runtime-003/run/diagnostic/samples.jsonl sha256=87823e412dcff645a8ea6b33181bf925f10077ca243d58aa3c6b8c671713db95
  - /tmp/so101-physical-five-success-v2/phy5-g11-runtime-003/run/diagnostic/gazebo-gui.mp4 sha256=e89975a9d40575f754b89e2cb17185af72517bc9b881e3705f0e56e9ce93ec4b
  - /tmp/so101-physical-five-success-v2/phy5-g11-runtime-003/run/final-desktop.png sha256=124dc7d87989d24ffcaf16f1f779f2e07f37f8108a435b1ad88ea0e54ddac13c
decision: KEEP_G11_POLICY; analyze why release seating needs 10.476 mm and whether the configured 10 mm bound or upstream place Z should change before another sample
```

```yaml
checkpoint_id: CP-V2-G11-RUNTIME-003-VALID-053
recorded_at: 2026-08-11 Asia/Shanghai
last_valid_experiment: PHY5-G11-RUNTIME-003
current_runtime_sha256: 392522b9b9748710850c0a3d1503eb3ec2f20652439c0a626cc979bfa14f6f39
owned_processes: existing Gazebo and MoveIt windows only; no execute, recorder, video, or capture process
confirmed_conclusions:
  - bilateral stable-window timeout is observational at the grasp side and did not block micro-lift or carry
  - place XY reached the 10 mm center region in the final diagnostic sample, but the cup remained about 10.8 mm above support and still gripped
  - release-side bilateral timeout was not reached because release seating stopped first
qualification_status: NOT_STARTED
next_command: inspect release_seating_translation inputs and the 10 mm bound before changing or repeating the policy
```

```yaml
experiment_id: PHY5-G11-MANUAL-OPEN-001
status: PLANNED
prior_state: terminal held state from PHY5-G11-RUNTIME-003
hypothesis: opening q6 directly from the current held pose will let the cup fall roughly 10-11 mm and reveal whether it settles upright without arm or seating motion
prediction:
  - no RESET_WORLD and no arm command occur
  - exactly one gripper FollowJointTrajectory position goal commands joint 6 to 0.750 rad over 2 seconds
  - Gazebo physics alone determines the cup landing; telemetry and video capture the fall, support contact, tilt, XY displacement, and final gripper contact
single_variable: gripper position command q6=0.750 rad from the preserved G11-003 terminal state
lifecycle: CURRENT_STATE_NO_RESET
success_criteria:
  - cup reaches table support, loses gripper contact, remains upright, and settles without material XY displacement
failure_criteria:
  - cup tips, bounces/drifts materially, remains held, or leaves the accepted center region
invalid_criteria:
  - RESET_WORLD, arm command, duplicate gripper goal, missing video/samples, or any object teleport/attachment command
provenance:
  source_commit: ef73c10f159c270b91748a41df9c4bac728fde80
  live_execute_sha256: 392522b9b9748710850c0a3d1503eb3ec2f20652439c0a626cc979bfa14f6f39
  ros_domain_id: 189
  gz_partition: so101_phy5_v2_r0_001
decision: PENDING_DIRECT_GRIPPER_POSITION_GOAL
```

```yaml
experiment_id: PHY5-G11-RUNTIME-003
status: PLANNED
prior_experiment: PHY5-G11-RUNTIME-002
hypothesis: the unchanged final G11 build can again treat ordinary bilateral stability timeout as telemetry and expose the next authoritative physical outcome for direct user observation
prediction:
  - fresh RESET_WORLD proves the canonical detached initial state
  - source/runtime hash remains 392522b9b9748710850c0a3d1503eb3ec2f20652439c0a626cc979bfa14f6f39
  - ordinary bilateral timeout, if observed, is recorded and cannot terminate the run; penetration above 1.3 mm remains fail-close
  - the first unchanged controller, micro-lift, release, or final-placement outcome is authoritative
single_variable: NONE; unchanged repeat requested by user
lifecycle: RESET_WORLD
success_criteria:
  - one execute only, complete runtime JSON, 50 Hz samples, decodable Gazebo video, and fresh screenshot
failure_criteria:
  - complete evidence at the first unchanged safety or outcome boundary
invalid_criteria:
  - FULL_RESTART, provenance mismatch, failed reset, duplicate execute/recorder, or incomplete evidence
provenance:
  source_commit: ef73c10f159c270b91748a41df9c4bac728fde80
  live_execute_sha256: 392522b9b9748710850c0a3d1503eb3ec2f20652439c0a626cc979bfa14f6f39
  ros_domain_id: 189
  gz_partition: so101_phy5_v2_r0_001
decision: PENDING_RESET_WORLD
```

```yaml
checkpoint_id: CP-V2-G11-SAFETY-FINAL-052
recorded_at: 2026-08-11 Asia/Shanghai
change: initial bilateral observation now distinguishes ordinary stability timeout from moving-pad penetration ceiling; only ordinary timeout is observational
automated_result: 221 passed, 2 skipped; build, syntax, git diff check, and source/runtime hash match passed
current_runtime_sha256: 392522b9b9748710850c0a3d1503eb3ec2f20652439c0a626cc979bfa14f6f39
runtime_evidence_basis: PHY5-G11-RUNTIME-002 physically proved ordinary target-normalization timeout continuation on the immediately preceding behavior-equivalent build; the final delta only restores the existing hard-ceiling fail-close boundary and was automated-tested
owned_processes: existing Gazebo and MoveIt windows only; no execute, recorder, video, or capture process
qualification_status: NOT_STARTED
next_command: analyze DESCEND_TO_PLACE path-tolerance repeatability before another RESET_WORLD sample
```

```yaml
checkpoint_id: CP-V2-G11-RUNTIME-003-TAIL-054
recorded_at: 2026-08-11 Asia/Shanghai
authoritative_result: PHY5-G11-RUNTIME-003 VALID_FAILURE
summary: unchanged final G11 build passed ordinary bilateral-timeout continuation, micro-lift, carry, and XY alignment; release seating required -10.476447 mm and stopped 0.476447 mm beyond the 10 mm safety bound before opening
visual_state: cup upright and held over the red target circle; final asynchronous center error 7.991057 mm and bottom clearance 10.844510 mm
qualification_status: NOT_STARTED
next_command: inspect release_seating_translation inputs and the 10 mm bound before changing or repeating the policy
```

```yaml
experiment_id: PHY5-G11-MANUAL-OPEN-001
status: VALID_FAILURE
lifecycle: CURRENT_STATE_NO_RESET
command:
  action: /gripper_controller/follow_joint_trajectory
  joint: "6"
  position_rad: 0.750
  duration_s: 2
  result: SUCCEEDED error_code 0
observed:
  - no RESET_WORLD, arm, object-pose, Gazebo attachment, or MoveIt scene command occurred
  - by command time the held cup had already settled from the earlier decision-time clearance to 2.230564 mm bottom clearance; this manual action therefore did not test an 11 mm free fall
  - after opening, cup center moved 1.209730 mm in XY and 2.269685 mm downward
  - final cup center error was 7.989573 mm, inside the 10 mm center region; table support contact was present
  - final tilt was 0.219489 rad (12.576 deg), above the 0.087266 rad (5 deg) upright limit
  - final fixed-fingertip contact remained with about 0.601099 mm maximum positive penetration; the cup was leaning against the gripper rather than freely standing
  - last 100 open-gripper samples had zero X/Y range and 0.003889 mm Z range, so the leaning state was stationary but not an acceptable contact-free upright placement
  - q6 reached 0.750001 rad; 1683 valid samples and a fully decodable H.264 avc1 36.3 s video were retained
conclusion: the cup reached support without continued bounce or sliding, but did not land acceptably upright or gripper-contact-free; direct opening alone is not a successful release strategy
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g11-manual-open-001/run/gripper-open.log sha256=02be4a34f74b03ef45af561e7f7d4f3d97bc4b0a19cd1d626f7baca4f1affc6d
  - /tmp/so101-physical-five-success-v2/phy5-g11-manual-open-001/run/diagnostic/samples.jsonl sha256=0919ca9bcb3571d315a6c471e859bd1ac4074501253d841dc17dd506308ff936
  - /tmp/so101-physical-five-success-v2/phy5-g11-manual-open-001/run/diagnostic/gazebo-gui.mp4 sha256=6db40bf2dae9b917550110a683f1dbdb988c4729f2db1fa797b267d91be4cf2e
  - /tmp/so101-physical-five-success-v2/phy5-g11-manual-open-001/run/final-desktop.png sha256=6c2a91b9e9c2a7878b305b725601cfffebcf2d26e206dd2a04ad28406db09594
decision: DO_NOT_ADOPT_DIRECT_OPEN; next release strategy must create gripper clearance without leaning the cup on the fixed fingertip
```

```yaml
checkpoint_id: CP-V2-G11-MANUAL-OPEN-001-VALID-055
recorded_at: 2026-08-11 Asia/Shanghai
last_valid_experiment: PHY5-G11-MANUAL-OPEN-001
current_state: q6 open at 0.750 rad; cup support-contacting inside center tolerance but tilted 12.576 degrees and still touching the fixed fingertip
owned_processes: existing Gazebo and MoveIt windows only; no recorder, video, execute, or capture process
qualification_status: NOT_STARTED
next_command: decide a pre-open separation/retreat or improved release seating strategy; RESET_WORLD before any new full sample
```

```yaml
experiment_id: PHY5-G11-MANUAL-Z-LIFT-001
status: PLANNED
prior_state: terminal open-gripper leaning-cup state from PHY5-G11-MANUAL-OPEN-001
hypothesis: lifting the open gripper vertically 10 mm will remove residual fixed-fingertip support and reveal whether the cup is independently stable
prediction:
  - no RESET_WORLD, gripper position, object-pose, or attachment command occurs
  - exactly one MoveIt TCP world-Z translation of +0.010 m is executed
  - if the cup is independently stable it remains support-contacting, upright, and nearly stationary after fingertip contact clears
  - if it was relying on the fingertip it tips or shifts once the arm rises
single_variable: TCP world-Z +10 mm with q6 remaining open at 0.750 rad
lifecycle: CURRENT_STATE_NO_RESET
success_criteria:
  - fixed-fingertip contact clears and cup remains within final upright, support, and 10 mm center bounds
failure_criteria:
  - cup tips, drifts outside the region, loses support, or gripper contact remains
invalid_criteria:
  - RESET_WORLD, duplicate motion, gripper command, object teleport, missing samples/video, or non-Z TCP translation
decision: PENDING_WORLD_Z_LIFT
```

```yaml
experiment_id: PHY5-G11-MANUAL-Z-LIFT-001
status: AMENDED_BEFORE_MOTION
observed:
  - first MoveIt request returned planning error 99999 and executed no arm motion
  - read-only Planning Scene query proved plastic_cup remained attached to gripper while the physical cup was already support-contacting
amendment: synchronize the stale MoveIt shadow to a world object at the current Gazebo cup pose, then retry the same single +10 mm world-Z physical motion
unchanged: no RESET_WORLD, gripper, object-pose, Gazebo attachment, or non-Z arm command
decision: PENDING_SCENE_SYNC_AND_RETRY
```

```yaml
experiment_id: PHY5-G11-MANUAL-Z-LIFT-001
status: BLOCKED_BY_MOVEIT_COLLISION_GATE
lifecycle: CURRENT_STATE_NO_RESET
observed:
  - first +10 mm world-Z MoveIt request failed planning with error 99999; no arm joint motion occurred
  - Planning Scene readback proved stale plastic_cup attached to gripper; it was synchronized to a world object at the current Gazebo pose
  - second identical +10 mm world-Z request again failed planning with error 99999 because the world cup remained in real contact with the fixed fingertip at the start state
  - arm joints 1-5 changed by at most 0.000003934 rad across the evidence window, confirming no commanded lift executed
  - physical cup remained support-contacting and fixed-fingertip-contacting; slow passive settling shifted it about 2.82 mm in XY during the extended observation
  - Planning Scene final state is world-only plastic_cup with no attached object, matching the physically released cup
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g11-manual-z-lift-001/run/world-z-lift.log sha256=4e998b345f86d4acad797e450bdf564d03019dd8b5fe325e1b3f5761dd76985d
  - /tmp/so101-physical-five-success-v2/phy5-g11-manual-z-lift-001/run/scene-sync-z-lift.log sha256=0f6b38941c185f2c609a8368b749b9f596697501d60de7109daffde88a454abf
  - /tmp/so101-physical-five-success-v2/phy5-g11-manual-z-lift-001/run/diagnostic/samples.jsonl sha256=4d7efac17b6a40c7500b3834b65d84c39284472192929bf23fca5d42f0ec8bd7
  - /tmp/so101-physical-five-success-v2/phy5-g11-manual-z-lift-001/run/diagnostic/gazebo-gui.mp4 sha256=b2943b86a10d12aecc5486cbd23571a88b5588e68a52aed9ad3f53305252c08e
decision: REQUIRE_EXPLICIT_APPROVAL_TO_BYPASS_MOVEIT_COLLISION; physical state preserved, no arm lift executed
```

```yaml
experiment_id: PHY5-G11-MANUAL-Z-LIFT-APPROVED-001
status: PLANNED
prior_state: unchanged physical terminal state from blocked PHY5-G11-MANUAL-Z-LIFT-001
authorization: user explicitly approved temporary Planning Scene cup removal for the +10 mm vertical retreat
hypothesis: a single +10 mm TCP world-Z motion will clear fixed-fingertip contact; contact-free evidence, not nominal displacement, decides sufficiency
single_variable: temporarily omit plastic_cup from MoveIt collision scene during one +10 mm upward-away motion, then restore it at the latest Gazebo pose
lifecycle: CURRENT_STATE_NO_RESET
success_criteria:
  - MoveIt motion executes, observed TCP world-Z increases approximately 10 mm, world object is restored, and no gripper contact appears in the final stable window
failure_criteria:
  - planning/execution fails, gripper contact remains, cup tips materially, or world object restoration fails
invalid_criteria:
  - RESET_WORLD, gripper command, duplicate arm motion, object teleport, missing evidence, or failure to restore Planning Scene
decision: PENDING_APPROVED_COLLISION-OMITTED_Z_LIFT
```

```yaml
experiment_id: PHY5-G11-MANUAL-Z-LIFT-APPROVED-001
status: BLOCKED_NO_ARM_MOTION
lifecycle: CURRENT_STATE_NO_RESET
observed:
  - the approved temporary removal of world plastic_cup succeeded
  - the +10 mm MoveGroup plan-only request failed with generic client code 99999; the MoveIt log identifies GOAL_STATE_INVALID and no ExecuteTrajectory request followed
  - the action wrapper's post-motion sampler raised a duplicate-rclpy-context exception before its restoration line; an independent recovery immediately restored plastic_cup as a world object
  - the recovery helper inherited an old trailing +10 mm plan request; that second request was rejected at start-state collision with jaw-plastic_cup and also executed no trajectory
  - all six measured joints had exactly zero range across 4720 valid samples; the cup pose also had zero range, proving no physical lift occurred
  - the final 100 samples all retained table support and fixed-fingertip contact; maximum recorded finger penetration was 0.969285 mm
  - final cup center error was 7.030996 mm and tilt was 12.277832 degrees
  - final Planning Scene readback is world_objects=[plastic_cup], attached_objects=[]
geometry_answer:
  - the current projected cup-rim top is z=0.224263 m
  - the complete fixed fingertip pad spans down to z=0.193683 m; its lowest point is 30.580156 mm below the projected rim
  - after a nominal +10 mm world-Z motion, that lowest point would still be 20.580156 mm below the rim, so +10 mm is not a complete withdrawal
  - a +35 mm lift would provide about 4.42 mm geometric rim clearance; this is the smallest probed round target with useful margin
read_only_kinematics:
  - /compute_ik with collision checking disabled returned success for +2, +5, +10, +20, +26, +30, and +35 mm targets
  - therefore +35 mm is kinematically solvable, but the normal MoveIt goal-state validity path remains blocked and must not be bypassed without explicit approval
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g11-manual-z-lift-approved-001/run/approved-z-lift.log sha256=2c16bd6608b5f56d97e05840e8783753989d61bcf9d0b23f5be3fdb5256f8938
  - /tmp/so101-physical-five-success-v2/phy5-g11-manual-z-lift-approved-001/run/diagnostic/samples.jsonl sha256=f96a5da05f81e7a63e4396a8c46f957dde2d2d72de1d350668543d0e05222e86
  - /tmp/so101-physical-five-success-v2/phy5-g11-manual-z-lift-approved-001/run/diagnostic/gazebo-gui.mp4 sha256=18439d71831d1b5aa3c8fa9b4583335aa8b3512046db89efbdc3608882389bd5
  - /tmp/so101-physical-five-success-v2/phy5-g11-manual-z-lift-approved-001/run/geometry-clearance.log sha256=5fb41aad4e498739ca4b5bbf4a81b69ad9ac07d84065bc41ac6a4ab6d92286de
  - /tmp/so101-physical-five-success-v2/phy5-g11-manual-z-lift-approved-001/run/ik-probe.log sha256=5037ab247bcfc5582e9909b0f2d95f70c646334f3da9d1ac95e9d730390b7b40
  - /tmp/so101-physical-five-success-v2/phy5-g11-manual-z-lift-approved-001/run/final-moveit-scene.log sha256=f0a2340a3b2bb1f5e493e6261e95d647333438f9e915d2b2bcecb20442e1204e
decision: STOP_WITH_CURRENT_STATE; require explicit approval before any direct-controller staged +35 mm retreat that bypasses MoveIt goal-state validation
```

```yaml
checkpoint_id: CP-V2-G11-MANUAL-Z-LIFT-APPROVED-001-BLOCKED-056
recorded_at: 2026-08-11 Asia/Shanghai
last_experiment: PHY5-G11-MANUAL-Z-LIFT-APPROVED-001
current_state: unchanged open-gripper leaning-cup state; q6=0.750001 rad, cup center error=7.030996 mm, tilt=12.277832 degrees, fixed fingertip contact persists
moveit_scene: world-only plastic_cup; no attached object
owned_processes: existing Gazebo and MoveIt windows only; no execute, recorder, video, or capture process
qualification_status: NOT_STARTED
next_command: only after explicit approval, send a multi-waypoint arm-controller trajectory generated from collision-disabled IK targets up to world-Z +35 mm and verify contact-free clearance
```

```yaml
experiment_id: PHY5-G11-GOAL-STATE-DIAG-001
status: PLANNED
prior_experiment: PHY5-G11-MANUAL-Z-LIFT-APPROVED-001
hypothesis: GOAL_STATE_INVALID is caused by the mismatch between position_only_ik=True and the request's 0.005 rad three-axis TCP orientation constraint, not raw positional IK failure
prediction:
  - with plastic_cup temporarily omitted from the Planning Scene, the unchanged +10 mm plan-only goal fails at orientation tolerance 0.005 rad
  - changing only orientation tolerance to 0.020 rad makes the same plan-only goal valid
single_variable: MoveGroup orientation tolerance 0.005 rad versus 0.020 rad
lifecycle: CURRENT_STATE_NO_RESET
preconditions:
  - q6 remains open at 0.750001 rad and no arm/controller execute request is sent
  - physical cup and arm remain unchanged
  - world plastic_cup is temporarily removed only to isolate goal validity from the known jaw-cup start collision, then restored
success_criteria:
  - strict request returns GOAL_STATE_INVALID while relaxed request returns SUCCESS with a non-empty planned trajectory
failure_criteria:
  - both requests have the same result or evidence identifies a different first invalidity
invalid_criteria:
  - any ExecuteTrajectory or FollowJointTrajectory request, joint change, RESET_WORLD, object teleport, or failed Planning Scene restoration
provenance:
  source_commit: ef73c10f159c270b91748a41df9c4bac728fde80
  install_overlay: /data/work/ws_moveit/.worktrees/so101-physical-five-success/install
  runtime_executable: /opt/ros/jazzy/lib/moveit_ros_move_group/move_group
  ros_domain_id: 189
  gz_partition: so101_phy5_v2_r0_001
decision: PENDING_PLAN_ONLY_AB
```

```yaml
experiment_id: PHY5-G11-GOAL-STATE-DIAG-001
status: VALID
commands:
  - command: python3 /tmp/so101-probe-z-ik-fk.py
    exit_code: 0
  - command: python3 /tmp/so101-plan-only-orientation-ab.py | tee orientation-ab.json
    exit_code: 0 for diagnostic pipeline; enclosing zsh exited 1 afterward because it assigned reserved variable status
observed:
  - live /move_group uses kdl_kinematics_plugin/KDLKinematicsPlugin with position_only_ik=True
  - the +10 mm position-only IK solution has 0.000141 mm position error but 0.011912 rad (0.682527 degree) TCP orientation error, concentrated on the relative Y rotation
  - the request constrains each TCP orientation axis to 0.005 rad, so the returned position-only solution fails goal validation
  - with plastic_cup temporarily omitted, the unchanged +10 mm plan-only request at 0.005 rad returned error 99999 with zero trajectory points
  - changing only the orientation tolerance to 0.020 rad returned MoveIt SUCCESS with 14 trajectory points
  - no ExecuteTrajectory or FollowJointTrajectory request was sent; every measured joint delta was exactly 0
  - Planning Scene was restored to world_objects=[plastic_cup], attached_objects=[]
  - the enclosing shell's reserved-variable error occurred after the complete JSON result and scene restoration; it does not invalidate the diagnostic boundary
inferred:
  - confirmed root cause is an internally inconsistent pose goal: a position-only five-DoF IK solver is paired with a near-fixed 6D orientation constraint during world-Z retreat
  - raw positional reachability is not the cause, and the known jaw-cup start collision is a separate failure mode seen only when the cup remains in the scene
conclusion: GOAL_STATE_INVALID is caused by the 0.005 rad orientation constraint rejecting the position-only IK solutions required for +10 mm vertical translation
evidence:
  - /tmp/so101-debug-goal-state-invalid-yJ22k2/ik-fk-probe.json sha256=c7c762b0be8acc06733470178112a2c0eea0b715dfef2cd3c2e40bb986de2761
  - /tmp/so101-debug-goal-state-invalid-yJ22k2/orientation-ab.json sha256=6ce20ec0163b6f5ff90a33214c18f437e445e7876eafd47028220d30f1953ad2
decision: KEEP_DIAGNOSIS_ONLY; no policy or motion change authorized in this experiment
next_experiment: NONE_PENDING_USER_DIRECTION
```

```yaml
checkpoint_id: CP-V2-G11-GOAL-STATE-DIAG-001-VALID-057
recorded_at: 2026-08-11 Asia/Shanghai
last_valid_experiment: PHY5-G11-GOAL-STATE-DIAG-001
current_state: unchanged open-gripper leaning-cup physical state; no arm motion occurred
moveit_scene: world-only plastic_cup; no attached object
confirmed_conclusions:
  - +10 mm GOAL_STATE_INVALID is the position_only_ik versus 0.005 rad full-orientation-constraint mismatch
  - relaxing only that tolerance to 0.020 rad makes the same +10 mm plan-only request succeed with 14 points
owned_processes: existing Gazebo and MoveIt windows only; no diagnostic process remains
qualification_status: NOT_STARTED
next_command: NONE until the retreat-goal correction is selected and approved
```

```yaml
experiment_id: PHY5-G11-SELECTIVE-RETREAT-PLAN-001
status: PLANNED
prior_experiment: PHY5-G11-GOAL-STATE-DIAG-001
authorization: user selected controlled option 2
hypothesis: a +35 mm world-Z retreat with orientation tolerances X=0.005, Y=0.060, Z=0.005 rad will preserve lateral orientation control while admitting the measured five-DoF pitch change
prediction:
  - an automated regression test first fails because the goal builder cannot represent per-axis tolerances
  - after the minimal implementation, the same test passes
  - with plastic_cup temporarily omitted, the +35 mm selective-tolerance plan-only request succeeds with a non-empty trajectory and no joint motion
single_variable: replace one shared orientation tolerance with axis-specific X/Y/Z tolerances for this retreat request
lifecycle: CURRENT_STATE_NO_RESET
preconditions:
  - existing Gazebo and MoveIt stack is reused; no RESET_WORLD or FULL_RESTART
  - no ExecuteTrajectory or FollowJointTrajectory request is sent
  - Planning Scene cup removal is diagnostic-only and restored before completion
success_criteria:
  - RED then GREEN test evidence exists
  - correct overlay is rebuilt and sourced
  - +35 mm plan-only returns SUCCESS with X/Z 0.005 and Y 0.060 rad
  - all joint deltas remain zero and Planning Scene returns to world-only plastic_cup
failure_criteria:
  - selective tolerance remains GOAL_STATE_INVALID, the trajectory is empty, or package tests regress
invalid_criteria:
  - any physical arm/gripper command, failed scene restoration, reset, object teleport, or evidence/provenance mismatch
provenance:
  source_commit: ef73c10f159c270b91748a41df9c4bac728fde80
  install_overlay: /data/work/ws_moveit/.worktrees/so101-physical-five-success/install
  runtime_executable: /opt/ros/jazzy/lib/moveit_ros_move_group/move_group
  ros_domain_id: 189
  gz_partition: so101_phy5_v2_r0_001
decision: PENDING_TDD_AND_PLAN_ONLY
```

```yaml
experiment_id: PHY5-G11-SELECTIVE-RETREAT-PLAN-001
status: VALID
commands:
  - command: targeted RED pytest
    exit_code: 1
  - command: targeted GREEN pytest
    exit_code: 0
  - command: colcon build --base-paths src/so101_gazebo_demo_py --packages-select so101_gazebo_demo_py --symlink-install
    exit_code: 0
  - command: targeted two-file pytest and package-level colcon test
    exit_code: 0
  - command: +35 mm selective-tolerance MoveGroup plan-only
    exit_code: 0
observed:
  - RED failed for the intended reason: make_pose_move_group_goal did not accept orientation_tolerances_rad
  - the minimal change added axis-specific goal tolerances while preserving the existing scalar/default path
  - GREEN passed both the new selective Y tolerance test and the existing default three-axis tolerance test
  - targeted suite passed 64/64; package result was 224 tests, 0 failures, 0 errors, 2 skipped
  - rebuilt package prefix is /data/work/ws_moveit/.worktrees/so101-physical-five-success/install/so101_gazebo_demo_py
  - +35 mm plan-only with X=0.005, Y=0.060, Z=0.005 rad returned MoveIt SUCCESS and 24 trajectory points
  - every observed joint delta was exactly zero; no execute action was sent
  - Planning Scene was restored to world_objects=[plastic_cup], attached_objects=[]
conclusion: controlled option 2 is implemented and proven plan-valid for the current +35 mm retreat target
evidence:
  - /tmp/so101-debug-selective-retreat-TPhDjc/red-test-import-fixed.log sha256=05b3505e285566a3206e84f4d2d2cea4a28f6b47b9b4d3228f93173c83e11226
  - /tmp/so101-debug-selective-retreat-TPhDjc/green-targeted.log sha256=b1a06b26972c2140d432c34fda543615763c138b875a7c41cc50eedff85f4e4a
  - /tmp/so101-debug-selective-retreat-TPhDjc/build.log sha256=032ba983aad886d95c4c67bbcbe12cffd01a6796fe7e8d3a0f31cdd540b96747
  - /tmp/so101-debug-selective-retreat-TPhDjc/targeted-tests.log sha256=33124fbf1256853baf70727dfe5e4fc74ae760f0e9e4bef1e9c3009f5e239497
  - /tmp/so101-debug-selective-retreat-TPhDjc/package-tests.log sha256=a1a21488ab63607c009792bd4c8fba784b170f784452f28f6d4532fc0b251f90
  - /tmp/so101-debug-selective-retreat-TPhDjc/test-result.log sha256=4aae1e5f0f7d9514497f03b94fe038c5620b853ab834c98d2234a5c588a43d85
  - /tmp/so101-debug-selective-retreat-TPhDjc/plan-only-selective-retreat.json sha256=58a056bf58f2863f08c662106c10384309187debc62c87f5b3e807a6abf1c93d
decision: KEEP
next_experiment: PHY5-G11-SELECTIVE-RETREAT-EXEC-001
```

```yaml
experiment_id: PHY5-G11-SELECTIVE-RETREAT-EXEC-001
status: PLANNED
prior_experiment: PHY5-G11-SELECTIVE-RETREAT-PLAN-001
authorization: user selected controlled option 2 in the active vertical-retreat request
hypothesis: executing the proven +35 mm plan with X/Z 0.005 and Y 0.060 rad will withdraw the complete fixed fingertip above the projected cup rim without disturbing the supported cup materially
prediction:
  - TCP world Z rises approximately 35 mm with bounded XY drift and controlled pitch
  - fixed-fingertip contact clears and does not reappear in the final stable window
  - the cup remains table-supported, inside the 10 mm center tolerance, and does not tip further materially
single_variable: execute the already proven +35 mm selective-orientation trajectory once
lifecycle: CURRENT_STATE_NO_RESET
preconditions:
  - q6 remains open at 0.750001 rad
  - cup remains support-contacting at the preserved G11 pose
  - world plastic_cup is temporarily removed only during MoveIt planning/execution and restored afterward
success_criteria:
  - one ExecuteTrajectory succeeds and observed TCP Z rises about 35 mm
  - final 100 samples contain no gripper-cup contact
  - cup remains supported and within the accepted landing center region
failure_criteria:
  - execution fails, contact persists, cup loses support, tips materially, or exits the center region
invalid_criteria:
  - RESET_WORLD, gripper command, duplicate arm execution, object teleport, failed scene restoration, or missing samples/video
provenance:
  source_commit: ef73c10f159c270b91748a41df9c4bac728fde80
  source_sha256: 8395a603ab38d24fc95976a4335b413defa5a932062c391985fda92c99c5acd7
  install_overlay: /data/work/ws_moveit/.worktrees/so101-physical-five-success/install
  runtime_executable: /opt/ros/jazzy/lib/moveit_ros_move_group/move_group
  ros_domain_id: 189
  gz_partition: so101_phy5_v2_r0_001
decision: PENDING_SINGLE_EXECUTION
```

```yaml
experiment_id: PHY5-G11-SELECTIVE-RETREAT-EXEC-001
status: VALID_FAILURE
command:
  action: one MoveGroup plan plus one ExecuteTrajectory
  world_z_delta_m: 0.035
  orientation_tolerances_rad: [0.005, 0.060, 0.005]
  result: SUCCEEDED with 24 planned points
observed:
  - no RESET_WORLD, gripper command, object teleport, or duplicate arm execution occurred
  - TCP delta was [+0.079805, -0.177915, +34.884949] mm; orientation changed 0.054300 rad (3.111189 degrees)
  - fixed-fingertip contact cleared; the final 500 samples contained zero gripper-cup contacts and all 500 retained table support
  - the final cup pose was stationary over the last 500 samples with zero measured XYZ range
  - cup tilt improved from 12.277832 degrees to 0.000035 degrees
  - cup center shifted by [-15.457973, +8.828193] mm and final center error became 12.300551 mm
  - final center error exceeds the 10 mm acceptance limit by 2.300551 mm, so the run is not a successful placement
  - Planning Scene final readback is world_objects=[plastic_cup], attached_objects=[]
conclusion: selective +35 mm retreat solves the GOAL_STATE_INVALID and contact-clearance problems, but withdrawal from the already leaning cup pushes the now-upright cup outside the landing-center tolerance
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g11-selective-retreat-exec-001/run/before-state.json sha256=29f1173743d509b0748ccd9f00a48d3328de0bb422550f2cdc8a0ad6c72a15d2
  - /tmp/so101-physical-five-success-v2/phy5-g11-selective-retreat-exec-001/run/scene.log sha256=566a1963885f1d5e3cba38b7c35e6d7aabd44a079fe9ffc86e419aefe69b7622
  - /tmp/so101-physical-five-success-v2/phy5-g11-selective-retreat-exec-001/run/execute.log sha256=45c81f9fbb233de0d23a99c6048f43ddf9ff2f40d48d27a04cba7d746d47b197
  - /tmp/so101-physical-five-success-v2/phy5-g11-selective-retreat-exec-001/run/after-state.json sha256=b888f6123cbb1e59ffd7f524eda318b9cc9159e3cdb21a414799470d2eddfca8
  - /tmp/so101-physical-five-success-v2/phy5-g11-selective-retreat-exec-001/run/diagnostic/samples.jsonl sha256=875deef1a68745ad234632cafdcc0a8ac9f19f9ede19b062848233f71383dc7a
  - /tmp/so101-physical-five-success-v2/phy5-g11-selective-retreat-exec-001/run/diagnostic/gazebo-gui.mp4 sha256=7bccfb99d430a03194e7556391e6d7317d7d6da319bd139b7af1dbce4a02c775
decision: KEEP_SELECTIVE_ORIENTATION_CAPABILITY; DO_NOT_COUNT_RUN; investigate pre-open leaning and predictable withdrawal push before qualification
next_experiment: NONE_PENDING_POLICY_DECISION
```

```yaml
checkpoint_id: CP-V2-G11-SELECTIVE-RETREAT-EXEC-001-VALID-058
recorded_at: 2026-08-11 Asia/Shanghai
last_valid_experiment: PHY5-G11-SELECTIVE-RETREAT-EXEC-001
current_state: cup upright, table-supported, contact-free, and stationary; center error 12.300551 mm outside the 10 mm limit; arm remains at the +35 mm retreat pose and q6 remains open
moveit_scene: world-only plastic_cup; no attached object
confirmed_conclusions:
  - controlled X/Z 0.005 and Y 0.060 rad removes GOAL_STATE_INVALID for +35 mm
  - +35 mm provides complete contact clearance
  - lifting out of an already leaning cup moves the cup outside center tolerance even though it becomes upright
owned_processes: existing Gazebo and MoveIt windows only; no recorder, video, diagnostic, or execute process remains
qualification_status: NOT_STARTED
next_command: decide whether to prevent leaning before opening or compensate the pre-release center target for the measured withdrawal push; use RESET_WORLD for the next complete sample
```

## PHY5-G12 continuous controlled release retreat

```yaml
experiment_id: PHY5-G12-CONTROLLED-RELEASE-RETREAT-AUTOMATED
status: AUTOMATED_GREEN
hypothesis: the continuous strategy can make the already proven selective-tolerance Cartesian retreat its only final release path while preserving Planning Scene recovery and final-outcome semantics
implemented:
  - pre-open +35 mm plan-only readiness gate with orientation tolerances X=0.005, Y=0.060, Z=0.005 rad
  - post-open Planning Scene omission, fresh-state replan and execution, and world-object restoration from the latest Gazebo pose
  - no fixed-joint RETREAT waypoint fallback in the continuous release path
  - pre-open and post-open failure evidence plus combined primary/restoration error reporting
automated_results:
  - Task 1 RED failed only because the omit scene operation was absent; GREEN passed after the minimal REMOVE diff
  - Task 2 RED failed only because the preflight/execution helpers and selective wrapper were absent; GREEN passed 5 focused tests
  - Task 3 RED failed on the three obsolete fixed-joint contracts; updated controlled-path contracts passed
  - targeted owning suites passed 105/105
  - owning package built successfully; colcon test-result reports 230 tests, 0 errors, 0 failures, 2 skipped
  - git diff check and Python syntax check passed
provenance:
  source_commit: 952648d3a3f9b9ed54ae6e5d42e433462aee8fa0
  live_execute_source_runtime_sha256: f8c8eff3cc63c2b3b4bdb17b5c26b510d083cb8f3bbecc78bc69b90b6beca896
  worktree: /data/work/ws_moveit/.worktrees/so101-physical-five-success
  branch: codex/so101-physical-five-success
  ros_domain_id: 189
  gz_partition: so101_phy5_v2_r0_001
decision: PROCEED_TO_ONE_RESET_WORLD_RUNTIME
```

```yaml
experiment_id: PHY5-G12-CONTROLLED-RELEASE-RETREAT-RUNTIME-001
status: PLANNED
prior_experiment: PHY5-G11-SELECTIVE-RETREAT-EXEC-001
hypothesis: one complete continuous run will preflight the selective +35 mm goal before opening, then open, omit the MoveIt cup, execute the same controlled retreat, and restore world-only cup membership before final validation
prediction:
  - fresh RESET_WORLD proves canonical detached state without restarting Gazebo or MoveIt
  - if the run reaches release, preflight returns a non-empty trajectory before q6 opens
  - after q6 opens, the continuous path executes world Z +35 mm with X/Z=0.005 and Y=0.060 rad and never invokes fixed-joint RETREAT waypoints
  - Planning Scene is world-only plastic_cup before final outcome collection, including a retreat failure path
single_variable: replace the continuous final fixed-joint retreat with the preflighted controlled Cartesian retreat already proven manually
lifecycle: RESET_WORLD
success_criteria:
  - complete strategy reaches release and records nonzero preflight/execution point counts
  - q6 reaches the configured open position and TCP world Z rises approximately 35 mm
  - final Planning Scene contains world plastic_cup and no attached plastic_cup
  - complete 50 Hz samples, decodable video, fresh screenshot, and authoritative runtime JSON are retained
failure_criteria:
  - complete evidence at the first unchanged upstream or final physical-outcome boundary
invalid_criteria:
  - FULL_RESTART, provenance mismatch, failed reset, duplicate execute/recorder/video, fixed-joint fallback, missing scene restoration, or incomplete visual/telemetry evidence
provenance:
  source_commit: 952648d3a3f9b9ed54ae6e5d42e433462aee8fa0
  live_execute_sha256: f8c8eff3cc63c2b3b4bdb17b5c26b510d083cb8f3bbecc78bc69b90b6beca896
  ros_domain_id: 189
  gz_partition: so101_phy5_v2_r0_001
decision: PENDING_RESET_WORLD
```

```yaml
experiment_id: PHY5-G12-CONTROLLED-RELEASE-RETREAT-RUNTIME-001
status: VALID_FAILURE
lifecycle: RESET_WORLD
observed:
  - RESET_WORLD_PROVED with 0.0000016099357596319931 m object-pose error, Gazebo detached, MoveIt world-only plastic_cup, no finger contact, and finite TCP
  - the continuous pre-open retreat preflight succeeded with 24 trajectory points while Planning Scene temporarily contained no plastic_cup, then restored attached plastic_cup before opening
  - release q6 reached 0.7500017285346985 rad
  - after opening, the continuous controlled retreat again omitted the cup, planned 24 points, and executed successfully
  - observed TCP translation was [+0.097457, -0.100138, +35.165350] mm; no fixed-joint RETREAT fallback ran
  - Planning Scene was restored to world_objects=[plastic_cup], attached_objects=[] before the final outcome epoch
  - the final 500 recorder samples all retained table support and contained zero robot-cup contact samples
  - cup tilt changed from 17.732582 degrees at release seating to 0.023429 degrees after withdrawal
  - cup center moved [-13.921238, -1.754552] mm during release/withdrawal; final center error was 15.446894 mm
  - the authoritative final failure was FINAL_OUT_OF_REGION; this sample is not countable toward five consecutive successes
  - 11531 diagnostic samples span 234.229526 s; H.264 avc1 video is 1888x1046 at 10 fps for 212.8 s and passes a complete null decode
conclusion: the requested continuous final open-and-retreat scheme is physically executed and scene-safe; the remaining failure is upstream pre-open leaning plus release displacement, not missing gripper opening, GOAL_STATE_INVALID, retreat execution, contact clearance, or scene restoration
evidence:
  - /tmp/so101-physical-five-success-v2/phy5-g12-controlled-release-retreat-runtime-001/reset/reset-world.json sha256=93f455afdf7a01bc48d83509de8291b13064a7e268096633e97b3f27ee9b7d7c
  - /tmp/so101-physical-five-success-v2/phy5-g12-controlled-release-retreat-runtime-001/run/execute.log sha256=da2016fe9aebde9760f80b987ede6e9effca3bce1fdd859cdbec7942970b330f
  - /tmp/so101-physical-five-success-v2/phy5-g12-controlled-release-retreat-runtime-001/run/physical-gate.json sha256=3be18ea815e3cd8f3afe8e17888bc8fb2b7722bf3a3196e71fc81c25630d6977
  - /tmp/so101-physical-five-success-v2/phy5-g12-controlled-release-retreat-runtime-001/run/final-outcome-failure.json sha256=cc47873b6b2dbb8751491eab50c744835a61747b59564001ba1e9171b661d603
  - /tmp/so101-physical-five-success-v2/phy5-g12-controlled-release-retreat-runtime-001/run/diagnostic/samples.jsonl sha256=3d1fba4eae0f2aeddcf308b6aa2ff25aec90e560782c35234a29f8bf92b10443
  - /tmp/so101-physical-five-success-v2/phy5-g12-controlled-release-retreat-runtime-001/run/diagnostic/gazebo-gui.mp4 sha256=ecfd3f84dda357f23e13be2f3ed6c0bffde9d58b6d18a8117cf888ba74520322
  - /tmp/so101-physical-five-success-v2/phy5-g12-controlled-release-retreat-runtime-001/run/final-gazebo-video-frame.png sha256=375e37c3fd06b9b43a95e9686750a3af6410151f0ba7e4367fa51026e1e62b0c
decision: KEEP_CONTROLLED_CONTINUOUS_RETREAT; DO_NOT_COUNT_SAMPLE
next_experiment: prevent pre-open leaning or compensate the release target from fresh RESET_WORLD; do not modify the proved retreat path
```

```yaml
checkpoint_id: CP-V2-G12-CONTROLLED-RELEASE-RETREAT-RUNTIME-001-VALID-059
recorded_at: 2026-08-11 Asia/Shanghai
last_valid_experiment: PHY5-G12-CONTROLLED-RELEASE-RETREAT-RUNTIME-001
current_state: cup upright, table-supported, contact-free, and stationary; center error 15.446894 mm outside the 10 mm limit; q6 open and arm at the +35 mm controlled retreat endpoint
moveit_scene: world-only plastic_cup; no attached object
confirmed_conclusions:
  - the continuous strategy preflights the selective Cartesian retreat before opening
  - the same selective +35 mm route executes after opening with complete contact clearance
  - scene omission and restoration occur in the intended order, with no fixed-joint fallback
  - placement still fails because the cup is already tilted before opening and withdrawal shifts its center outside tolerance
owned_processes: existing Gazebo and MoveIt windows only; no execute, recorder, video, or capture process remains
qualification_status: NOT_STARTED
next_command: choose a pre-open anti-leaning correction or center compensation; use RESET_WORLD for the next complete sample
```

```yaml
checkpoint_id: CP-V2-PREOPEN-TILT-MATRIX-RESET-PROVED-060
recorded_at: 2026-08-11 Asia/Shanghai
last_valid_experiment: PHY5-G12-CONTROLLED-RELEASE-RETREAT-RUNTIME-001
source_commit: f31ee7af0179c7107661afbc10ba55ab48ce3cd6
active_install_overlay: /data/work/ws_moveit/.worktrees/so101-physical-five-success/install
ros_domain_id: 189
gz_partition: so101_phy5_v2_r0_001
analysis_document: docs/experiments/so101-pre-open-tilt-root-cause-and-drop-strategy-matrix.md
analysis_document_sha256: 0a162cf3c7a07f63a2d37e50b38e12501bd9ac495c119d92fd86d7681ae7947c
current_state: RESET_WORLD_PROVED; arm at home, cup upright at canonical pick pose, gripper separated, Gazebo detached, MoveIt world-only plastic_cup
reset:
  command: SO101_PY_EVIDENCE_DIR=<evidence>/reset ros2 run so101_gazebo_demo_py reset_so101_world --timeout 15.0
  exit_code: 0
  object_pose_error_m: 0.0000007536096944757548
  gazebo_attachment_state: detached
  moveit_world_objects: [plastic_cup]
  moveit_attached_objects: []
  finger_contact: false
  arm_tcp_finite: true
  evidence: /tmp/so101-physical-five-success-v2/phy5-pre-open-tilt-reset-hH9OaU/reset/reset-world.json
  evidence_sha256: a691f181b86e706015e2f7c20cb9fda0abc5de2c2fe5a8641071794787f4e642
observed:
  - the first shell attempt at /tmp/so101-physical-five-success-v2/phy5-pre-open-tilt-reset-hGwGk8 stopped before ros2 was loaded because nounset was incompatible with the ROS setup script; it issued no reset or robot command
  - the successful attempt reused the existing Gazebo and MoveIt stack and did not perform FULL_RESTART
  - all three controllers remained active before reset
  - fresh Gazebo capture visually confirms the arm at home, the upright cup at the pick-side spawn pose, and the red target ring at the place side
visual_evidence:
  remote: /tmp/so101-physical-five-success-v2/phy5-pre-open-tilt-reset-hH9OaU/reset/gazebo-after-reset.png
  sha256: 51b1058471d1bd98d6eae41e173e4fa726ce4dab8f4c4616e075ca317cced8f8
  local_copy: /Users/matianyi/Projects/robot_demo_001/assets/captures/ai-station/20260811-phy5-pre-open-tilt-reset/gazebo-after-reset.png
confirmed_conclusions:
  - G12 tilt grows primarily during MOVE_ABOVE_PLACE, coupled XYZ PLACE_ALIGNMENT, and clamped RELEASE_SEATING; OPEN_GRIPPER is not the first bad boundary
  - the next highest-information isolated variable is XY-only PLACE_ALIGNMENT at safe height; the proved +35 mm controlled retreat remains frozen
working_tree_status: expected documentation-only changes in the matrix document and this ledger checkpoint
owned_processes: existing tmux so101-phy5-v2-r0 Gazebo and MoveIt stack only; no execute, recorder, or video process
qualification_status: NOT_STARTED
next_experiment: PHY5-G13-XY-ONLY-ALIGNMENT
next_command: preregister PHY5-G13-XY-ONLY-ALIGNMENT and add its RED test before changing runtime behavior
```

```yaml
checkpoint_id: CP-V2-PREOPEN-TILT-DOC-C10-M1-M8-061
recorded_at: 2026-08-11 Asia/Shanghai
last_valid_experiment: PHY5-G12-CONTROLLED-RELEASE-RETREAT-RUNTIME-001
source_commit: f31ee7af0179c7107661afbc10ba55ab48ce3cd6
current_state: unchanged RESET_WORLD_PROVED state from CP-V2-PREOPEN-TILT-MATRIX-RESET-PROVED-060
runtime_action: NONE
document: docs/experiments/so101-pre-open-tilt-root-cause-and-drop-strategy-matrix.md
document_sha256: 02ce5178b9e7234687fb18633475787439061839aa1a8157d06ad19b7b48cb7a
document_changes:
  - clarify that cup pose, tilt, bottom clearance, alignment feedback, and final outcome come from Gazebo; TCP comes from TF; MoveIt only holds a collision shadow seeded from Gazebo
  - reclassify C10 as low direct physical causality, high control/modeling gap, and medium indirect planning influence
  - retain only M1 through M8 in the drop-strategy matrix
  - remove T5 and T6 because they depended on out-of-scope M9 through M11 routes
preserved_processes:
  - SO-101 physical stack in tmux so101-phy5-v2-r0, ROS_DOMAIN_ID 189, GZ_PARTITION so101_phy5_v2_r0_001
  - separately owned MuJoCo MoveIt process in ROS_DOMAIN_ID 138; no conflict and no action taken
working_tree_status: expected documentation-only changes in the matrix document and experiment ledger
qualification_status: NOT_STARTED
next_experiment: PHY5-G13-XY-ONLY-ALIGNMENT
next_command: preregister PHY5-G13-XY-ONLY-ALIGNMENT and add its RED test before changing runtime behavior
```

```yaml
checkpoint_id: CP-V2-PREOPEN-TILT-DOC-M9-M15-LOW-062
recorded_at: 2026-08-11 Asia/Shanghai
last_valid_experiment: PHY5-G12-CONTROLLED-RELEASE-RETREAT-RUNTIME-001
source_commit: f58fc5eea02274cd697a1c2d819da1c0132e50e6
current_state: unchanged RESET_WORLD_PROVED state from CP-V2-PREOPEN-TILT-MATRIX-RESET-PROVED-060
runtime_action: NONE
document: docs/experiments/so101-pre-open-tilt-root-cause-and-drop-strategy-matrix.md
document_sha256: b40ab3faa0082c29581cb65c809e18995f55baae36eadb8ade90ec8c0d6f5458
document_changes:
  - retain M1 through M8 as the current executable experiment scope
  - restore M9 through M15 in the complete drop-strategy matrix
  - classify every M9 through M15 route as low expected effectiveness
  - explicitly exclude M9 through M15 from the current follow-up experiments
preserved_processes:
  - SO-101 physical stack in tmux so101-phy5-v2-r0, ROS_DOMAIN_ID 189, GZ_PARTITION so101_phy5_v2_r0_001
  - separately owned MuJoCo MoveIt process in ROS_DOMAIN_ID 138; no conflict and no action taken
working_tree_status: expected documentation-only changes in the matrix document and experiment ledger
qualification_status: NOT_STARTED
next_experiment: PHY5-G13-XY-ONLY-ALIGNMENT
next_command: preregister PHY5-G13-XY-ONLY-ALIGNMENT and add its RED test before changing runtime behavior
```
