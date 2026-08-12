# SO-101 Gazebo / MuJoCo policy parity and Bullet solver experiment ledger

This ledger isolates exact motion-policy parity from Bullet solver tuning. None of the temporary world or controller measurement files are project configuration candidates.

## Frozen provenance and contract

```yaml
recorded_at: 2026-08-12 Asia/Shanghai
worktree: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
source_commit: c4a64d9db3da09ef767758a11b69d759c25a4725
exact_mujoco_policy:
  path: src/so101_mujoco_demo_py/config/motion_policies/light_cup_wall_pick.yaml
  sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
gazebo_world_sha256: d12b381af049a08998c4ab2f14dbf5347fceb37e31720763e20c7957b4c6a8d3
controller_source_sha256: 7c4c2c5660cb13f2efbf2cfdbc224e20ec0e1c39d77d60f8d9fc62cd6e3ffdea
object_config_sha256: da271bbba8a64eb9f6840227de67a6faecb4b224a7f3c9412eef65a9f5cc9dfe
validation_policy_sha256: 00801092af2cc5b30572389da8d4ab687124c074d4b4c8b4708c5918f2e58618
engine: gz-physics-bullet-featherstone-plugin
physics_step_s: 0.001
isolation:
  ros_domain_id: 230
  existing_mujoco_stack: preserved and never reused or stopped
counts_toward_any_existing_success_streak: false
```

## Chronological checkpoints

```yaml
checkpoint_id: CP-GZ-POLICY-PARITY-001-INVALID
experiment_id: GZ-POLICY-PARITY-001
status: INVALID_SETUP
reason: preregistered ROS_DOMAIN_ID 248 exceeded the Fast DDS port range
observed: Gazebo server started but ROS nodes exited before robot spawn, MoveIt, or policy execution
cleanup: only owned process group 1720046 was terminated
counts_as_policy_result: false
```

```yaml
checkpoint_id: CP-GZ-POLICY-PARITY-002-FAIL
experiment_id: GZ-POLICY-PARITY-002
status: VALID_FAILURE
lifecycle: FULL_RESTART
solver_iters: unspecified_SDFormat_default_50
pre_client_stabilization: normal launch readiness
policy_sha256_runtime: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
first_bad_boundary: first arm trajectory in MOVE_ABOVE_OBJECT
result:
  controller_error_code: -4
  controller_error: PATH_TOLERANCE_VIOLATED
  failed_joint: "2"
  position_error_rad: 0.008015
  path_tolerance_rad: 0.008000
evidence_root: /tmp/so101-gazebo-policy-parity/GZ-POLICY-PARITY-002
interpretation: failure occurred before grasp and carry; the 0.000015-rad overrun required an unchanged confirmation
```

```yaml
checkpoint_id: CP-GZ-POLICY-PARITY-003-FAIL
experiment_id: GZ-POLICY-PARITY-003
status: VALID_FAILURE_CONFIRMED
lifecycle: FULL_RESTART
solver_iters: unspecified_SDFormat_default_50
pre_client_stabilization_s: 30
pre_client_joint_state:
  max_abs_position_rad: 0.00000431
  max_abs_velocity_rad_s: 0.000000117
policy_sha256_runtime: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
first_bad_boundary: first arm trajectory in MOVE_ABOVE_OBJECT
result:
  controller_error_code: -4
  controller_error: PATH_TOLERANCE_VIOLATED
  failed_joint: "2"
  position_error_rad: 0.008018
  path_tolerance_rad: 0.008000
  elapsed_from_goal_acceptance_to_abort_s: 0.339
evidence_root: /tmp/so101-gazebo-policy-parity/GZ-POLICY-PARITY-003
decision: startup settling is not the cause; proceed to the solver-only experiment
```

```yaml
checkpoint_id: CP-GZ-SOLVER-ITERS-100-001-PRE
experiment_id: GZ-SOLVER-ITERS-100-001
status: PREREGISTERED
hypothesis: doubling Bullet main solver iterations from 50 to 100 keeps the first exact-policy trajectory within the unchanged 0.008-rad tolerance and permits full pick-place
single_variable: temporary world explicitly sets bullet.solver.iters to 100
unchanged: exact policy, controller, object, validation, MoveIt, physics step, and 30-s stabilization
success: first trajectory passes and authoritative full pick-place outcome passes
failure: same first-trajectory violation or a later valid failure
```

```yaml
checkpoint_id: CP-GZ-SOLVER-ITERS-100-001-FAIL
experiment_id: GZ-SOLVER-ITERS-100-001
status: VALID_FAILURE
lifecycle: FULL_RESTART
temporary_world:
  path: /tmp/so101-gazebo-policy-parity/GZ-SOLVER-ITERS-100-001/so101_pick_place_iters_100.sdf
  sha256: e407b39e7e6e8c20602531f69cc2e2a424b00ac11f16ec25b2a58df3ee2e4ba5
  parsed_iters: 100
runtime_engine: gz::physics::bullet_featherstone::Plugin
policy_sha256_runtime: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
first_bad_boundary: first arm trajectory in MOVE_ABOVE_OBJECT
result:
  controller_error_code: -4
  controller_error: PATH_TOLERANCE_VIOLATED
  failed_joint_log_index: 0
  position_error_rad: 0.008056
  path_tolerance_rad: 0.008000
  elapsed_from_goal_acceptance_to_abort_s: 0.231
comparison_to_default_50:
  error_change_rad: 0.000038
  abort_time_change_s: -0.108
  direction: worse
evidence_root: /tmp/so101-gazebo-policy-parity/GZ-SOLVER-ITERS-100-001
decision: reject iters 100 as a remedy for exact-policy trajectory tracking; carry was not reached
```

```yaml
checkpoint_id: CP-GZ-DRIFT-PAIR-001-BLOCKED
experiment_id: GZ-DRIFT-050-001
status: MEASUREMENT_BLOCKED
purpose: expose MOVE_ABOVE_PLACE while preserving the exact policy, using the same temporary controller path tolerance in both planned solver arms
solver_iters: unspecified_SDFormat_default_50
temporary_arm_path_tolerance_rad: 0.012
first_bad_boundary: first arm trajectory in MOVE_ABOVE_OBJECT
result:
  position_error_rad: 0.012013
  path_tolerance_rad: 0.012000
evidence_root: /tmp/so101-gazebo-policy-parity/GZ-DRIFT-050-001
decision: 0.012 merely delayed the same persistent tracking violation and exposed no carry metric
```

```yaml
checkpoint_id: CP-GZ-DRIFT-PAIR-002-PRE
experiment_id: GZ-DRIFT-PAIR-002
status: PREREGISTERED
purpose: final bounded attempt to expose MOVE_ABOVE_PLACE with a shared diagnostic 0.050-rad path tolerance
policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
baseline: GZ-DRIFT-050-002 with default 50 iterations
treatment: GZ-DRIFT-100-002 with 100 iterations, only if baseline reaches carry
only_paired_variable: solver iterations
stop_rule: stop without the treatment arm if baseline still fails before grasp or carry
source_persistence_of_diagnostic_tolerance: forbidden
```

```yaml
checkpoint_id: CP-GZ-DRIFT-PAIR-002-BLOCKED
experiment_id: GZ-DRIFT-050-002
status: MEASUREMENT_BLOCKED_STOP
lifecycle: FULL_RESTART
solver_iters: unspecified_SDFormat_default_50
temporary_controller:
  path: /tmp/so101-gazebo-policy-parity/GZ-DRIFT-PAIR-001/so101_controllers_measurement.yaml
  sha256: e9d4ec81fe863a8c9ebea187973194cc668da34a0d84de95a1a2c58a935bf6ff
  arm_path_tolerance_rad: 0.050
policy_sha256_runtime: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
first_bad_boundary: first arm trajectory in MOVE_ABOVE_OBJECT
result:
  controller_error_code: -4
  controller_error: PATH_TOLERANCE_VIOLATED
  failed_joint: "2"
  position_error_rad: 0.050026
  path_tolerance_rad: 0.050000
evidence_root: /tmp/so101-gazebo-policy-parity/GZ-DRIFT-050-002
stop_rule_applied: GZ-DRIFT-100-002 was not run because the target carry metric remained unobservable
final_conclusions:
  - exact MuJoCo five-success policy does not complete on the current Gazebo arm/controller stack
  - increasing Bullet iterations from 50 to 100 did not improve the earlier trajectory-tracking blocker and was slightly worse in both error and time-to-abort
  - MOVE_ABOVE_PLACE cup drift cannot yet be compared because a persistent arm trajectory-following failure occurs before grasp
  - the next causal investigation belongs to Gazebo actuator/controller tracking, not contact solver iterations
cleanup: all owned experiment tmux stacks stopped and no isolated experiment process remained
source_changes_applied: none
counts_toward_any_existing_success_streak: false
```
