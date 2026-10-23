# Teacher event and reporting clocks, the ACM diff, and the single final stop

Date: 2026-10-08

Trigger: the production run of the offline processor on the pilot bag needed three diagnostic repairs (`--diagnostic-teacher-clock-repair`, `--diagnostic-ignore-scene-colors`, the stop-clock part of the same repair) and a skip rule for two extra `normal_stop` events. Decision CP-3441 (under CP-3394): remove the cause in the Teacher. These changes alter only event and reporting clocks, one message field of the ACM apply and which events are published. They never change a motion, a goal, a timeout, a gripper command or a decision.

## 1. Every scene operation is stamped from the clock at the actual call

- Evidence: the SETUP apply of the pilot bag stamped `request_ros_clock.sim_time_ns = 21.906 s` while the simulation was at 22.085 s (178 ms behind); the other scene operations lagged by 0 to 22 ms.
- Cause: the Teacher node is single threaded. Its ROS clock follows `/clock` only as the subscription callback runs, and the stamp was read from `node.get_clock()` without spinning. While the Teacher was busy (SETUP, a plan), the `/clock` messages waited in the queue.
- Rule: `record_scene_service_call` takes two optional callables. `clock_refresh()` runs before every ros-clock read (request and response); `clock_floor()` returns the simulation time of the newest world sample already received, and the stamp is never older. Both are best effort and can never change the call. The Teacher (`RosDynamicMujocoExecution._call`) refreshes with `_spin_burst` and uses the observer's newest world sample as floor; the setup port (`RosTaskScenePort._call`) refreshes with `refresh_node_clock`. The spin runs the same queued callbacks `_progress` runs; it adds at most 10 ms before a scene call.
- Tests: `test_p2_teacher_clocks.py` (`record_scene_service_call` refresh and floor, failing refresh, the real setup port and the Teacher `_call` with a clock that lags until the node is spun).

## 2. The ACM-only apply keeps the attached cup's colour

- Evidence: after `DYNAMIC_ACM_APPLY` the planning-scene reads no longer carried the attached cup's colour, so the scene geometry (which includes colours) no longer matched the association made at the attach.
- Cause: `_set_touch_collision` sent a diff whose `robot_state.is_diff` was left False. MoveIt's `setPlanningSceneDiffMsg` replaces the robot state when `robot_state.is_diff` is false and re-creates the attached bodies from the message, losing the colour of the attached cup. Every other apply in the Teacher already sets `robot_state.is_diff = True`.
- Rule: the ACM diff sets `scene.robot_state.is_diff = True` (and carries no attached object and no colour). The ACM content is unchanged.
- Test: `test_the_acm_only_apply_leaves_the_robot_state_and_so_the_attached_cup_colour_alone`, which applies MoveIt's replacement rule to the real `PlanningScene` message the Teacher builds.

## 3. The stop proof's simulation clock matches its monotonic instant

- Evidence: final `normal_stop` of the pilot bag: `sim_time = 115.292 s` (world record received at 889060.957941) with `begin = end = 889060.959727`; at that instant the simulation was 2 ms further. QC raised `NATIVE_QC_STOP_NATIVE_STALE`.
- Cause: the clock took the sim time of the earlier world record but the later monotonic of `max(receipt, confirmed)`.
- Rule (`_normal_stop_proof`): after a node-clock refresh the proof takes one instant `now = max(monotonic now, world receipt, confirmation)` as `begin = end` and `sim_time_ns = max(world sim time, node clock read after that instant)`. The world sample stays the anchor (`epoch`), and the boundary rule (sim time 0 to 100 ms after the anchor) still applies.
- Tests: `test_the_stop_proof_claims_the_current_simulation_clock_at_its_own_monotonic_instant`, `test_the_stop_proof_never_claims_a_time_before_its_world_record`.

## 4. Only the final boundary `normal_stop` is published

- Evidence: the release preflight (seq 36), the gripper-open proof (seq 41) and the final proof (seq 58) all published a `normal_stop`; the Recorder takes exactly one.
- Rule: `_normal_stop_proof` only builds and records the proof (`normal_stop_proofs` in the manifest, used by the release safety checks as before). `_publish_final_normal_stop` publishes the `normal_stop` event for the final proof after the sequence closed. The offline processor still tolerates several (`final_normal_stop_seq`).
- Tests: `test_an_intermediate_stop_proof_is_recorded_but_not_published`, `test_the_final_boundary_publishes_exactly_one_normal_stop`; the two existing final-stop stream tests now return a proof instead of publishing it themselves.

## Not changed

The live Recorder is not given a final boundary at the stop: it is being retired and the offline processor covers the rule (`2026-10-08-last-normal-stop-and-late-camera-sequence`, item 3).

Contract impact: none for control. Event stream: one `normal_stop` per episode instead of up to three. Scene message content: `robot_state.is_diff` of the ACM apply.

Rollback: `writer-artifacts/p2-teacher-base.tar.gz` (sha256 beside it) restores `ros/dynamic_mujoco_execution.py` and `control/planning_scene/task_scene.py`.

Ledger CP: CP-3441.
