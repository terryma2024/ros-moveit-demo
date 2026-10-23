# SO-101 Teacher MoveIt/JTC Simplification: Implementation Plan

- Date: 2026-10-06
- Authoritative design: [`2026-10-06-so101-teacher-moveit-simplification-amendment.md`](../specs/2026-10-06-so101-teacher-moveit-simplification-amendment.md) (sha256 `9d54f821f4cca6ab234cb0f247fd06c1d94e9f6348928e0cfe49ae3641ae61c9`). It amends the 10-05 decoupling amendment and wins on conflict.
- Base plan: [`2026-10-05-so101-teacher-act-decoupling-implementation.md`](2026-10-05-so101-teacher-act-decoupling-implementation.md). This document revises it. Anything not revised here still applies: D1, D2, D5, the D3 audit-only rows, the D4 data-side rows, D7 (except the dispatch receipts), the §5 live cases and the §6 report.
- Evidence root, dispatch directory, ledger, executors and model note: unchanged from the base plan. Plans and reviews are done by Opus 5.5; source changes and gates by one Sonnet 5.5 writer at a time. GPT-6 Astra is not available, so the independent review is done by a fresh Opus 5.5 reviewer and recorded as a model-rule limitation.
- Facts used here: `<dispatch>/writer-artifacts/s2-facts.md` (read-only pass, 2026-10-06). Items it marked UNVERIFIED are verified in the phases below, not assumed.

## R0. Starting state

- **Worktree and branch:** unchanged. HEAD is `fa8c82b98` with about 392 uncommitted paths (the takeover series plus the decoupling work). Do not reset, clean, stash or checkout.
- **Old-identity evidence:** freeze `nonhead-installed-freeze.m9qnDMSz`, inputs `nonhead-qualified-inputs.tHHgm22D` and live run `nonhead-first-episode-d6a3deaf-…` (CP-3362) are the last runs of the broker chain. They are kept and are not valid for the new identity.
- **Superseded work (ledger CP-3363):** A40 renewal audit, 5.1 bound-mode, A41/A42/A42b and the base plan's D8. The evidence stays where it is.
- **What `main` has:** no `adapters/act`, no `src/act`, and no broker or reservation C++. The ACT stack lives only in HEAD and in uncommitted work. The original pick-place execution path (`control/trajectory/executor.py`, `dynamic_cup_pick_place`, `run_dynamic_execute`, `StateMachineRunner` over `RosDynamicMujocoExecution`, `RECOVER_*` in `core/workflow.py:56-63`) is in `main`. `executor.py` is byte-identical to `main`.

## R1. Controllers

- **ACT yaml:** in `config/mujoco/act/ros2_controllers.yaml`, set `arm_controller`, `gripper_controller` and `neck_controller` to `joint_trajectory_controller/JointTrajectoryController`.
  - Align the arm and gripper parameters with the original `config/mujoco/ros2_controllers.yaml` (`update_rate` 500).
  - Delete the fork-only parameters: the three `enable_*`, the four `speed_scaling.*`, `interpolation_method`, and `interpolate_from_desired_state` where the original does not have it.
  - The `neck_controller` block stays because it is ACT-only and spawned at `launch_composition.py:869`. It uses the same stock type, with joint parameters unchanged.
- **Vendored fork:** `src/third_party/ros2_controllers/joint_trajectory_controller` is untracked and carries the `enable_*` fork. Move it out of the source tree into `<root>/archived/teacher-moveit-simplification/vendored-jtc-<stamp>/`, and record its sha manifest. Then the build cannot overlay the apt JTC 4.42.1. Move, do not delete.
- **Check:** the installed tree resolves `joint_trajectory_controller` to `/opt/ros/jazzy`, and no `BrokerOwnedTrajectoryController` plugin XML or library is installed.

## R2. Teacher execution path (replaces the base plan's D6 broker wording and all of D8)

- **Path:** the Teacher runs the original pick-place path: MoveIt plan → `move_group` `ExecuteTrajectory` → stock JTC, through `MoveItExecutionClient` with its `monitor` callback.
- **Seams to restore to the `main` behaviour:**
  - `dynamic_mujoco_execution.py:162`: plain `ActionClient`, not `leased_action_client.make_action_client`.
  - `dynamic_runtime.py:886-901`: remove `_bind_teacher_native_arm` (L214) and `_bind_teacher_native_gripper` (L236). `_motion_planning_start` (L1214) and `_command_gripper` (L1393) go back to the `main` implementations.
  - `backends/mujoco/client.py:129-142` and `teleop/server.py:164-176`: remove the leased-client swap.
  - `launch_composition.py:2336-2567`: no `act_command_broker` node.
- **Stop paths.** None of these needs a broker.

| Protection | Mechanism | Test (RED first) |
|---|---|---|
| Dangerous force 11.60 N (existing `_motion_monitor`) and compression | `monitor()` raises → `cancel_goal_async` → `_cancel_and_settle` (5 s) → JTC hold. The compression limit moves from `teacher_cup_safety.py` into the monitor and reads the Teacher's own observer. | monitor raise cancels the goal and enters the failure state |
| Necessary state unavailable longer than `state_unavailable_stop_s` (1.0 s), or `paused`/`reset_epoch`/session change | monitor raise → cancel | stale observer → cancel |
| Plan start drift > 0.01 rad (new on this path; same rule as `qualified_phases`) | refuse before `execute()`; no goal sent | drift 0.011 refused, 0.009 accepted |
| Segment timeout | existing `execute(timeout_s)` → cancel → `TIMED_OUT` | existing |
| Attempt deadline 180 s (`teacher_execution_deadline_s`, frozen at start) | Teacher-side watchdog thread: cancel the active goal, send no new goal, `teacher_execution_status=DEADLINE` | fake clock passes deadline → cancel, no new goal |
| User stop (SIGINT/SIGTERM, launch shutdown) | signal → cancel the active goal → bounded exit, `STOPPED_USER` | signal mid-goal → cancel + exit ≤ 6 s |
| Controller failure | `ExecuteTrajectory` reject/abort result → `FAILED` → original `RECOVER_*` or terminal | existing `MOVEIT_EXECUTION_FAILED` cases |
| Support before open | keep `_require_supported_bilateral` in the release phase, with freshness `state_max_age_s` (0.5 s) | unsupported held cup → no open |

- **What becomes audit-only.** These are the D3 process-quality rows (early table contact, bilateral contact loss, pre-close cup motion, grasp stable, micro-lift, release settle window, final placement checks, HOLD/STABILITY items). The monitor only records them; it never raises on them.
- **Deleted D3 rows:** "`TEACHER_PHASE_NOT_STOPPED` / ownership / predecessor / pending goal" and every generation, peer or permit check. They existed only to protect broker ownership.
- **Planning scene:** the original pick-place sync and attachment shadow, unchanged. No teleporting and no artificial physics attachment.

## R3. Labels and the event stream (revises D7)

- **Labels:** the Recorder already takes labels from `/{arm,gripper,neck}_controller/controller_state` (`episode_recorder_sources.py:60-100` → `collection_reference.py:build_collection_reference`). This stays. Installed `control_msgs` 5.9.0 has `reference`, `feedback`, `error` and `output`. The label is `reference.positions` (5 arm joints + 1 gripper joint) at `t+0.1 s` on the 10 Hz sim-time grid.
- **QoS:** the Recorder subscribes RELIABLE / KEEP_LAST depth 1000, about 2 s at 500 Hz. It does not use best-effort depth 5. This is data side only; a reliable keep-last subscriber cannot block the JTC publisher. A sequence gap, missing frame, cross-reset frame or out-of-tolerance stamp makes the data INVALID. Nothing is interpolated.
- **Teacher events:** schema `SO101_TEACHER_EVENT_V2`. It has the V1 content minus native dispatch receipts: reset complete, start/end pose, phase begin/finish, normal stop, terminal. The Recorder and QC reject V1.
- **Code that loses the dispatch-receipt dependency:**
  - `recorder_data_side.py:61-109`;
  - the `native_dispatch_v1` rules in `episode_qc.py` and `episode_audit.py`.
  - In their place, QC checks that `controller_state` reference frames are continuous over the episode window, with no sequence gap, one frame per grid instant, and the same reset epoch.
- **Verification (L0, inside the first live run).** A read-only sidecar subscriber records `controller_state` header stamps for all three controllers, during idle and motion. The run records:
  - the publish rate when idle and when moving;
  - whether stamps land on 2 ms sim steps, so that a frame exists exactly at each `t+0.1 s` grid instant;
  - the drop count at depth 1000.

  If a check fails (no idle publish, or off-grid stamps), stop and amend R3 before L2. Do not pick a tolerance to make it pass.

## R4. Isolation

- **One stack:** one headless MuJoCo stack per run, with a unique `ROS_DOMAIN_ID` chosen and recorded at prestart.
- **Prestart check:** no other DDS participants in that domain (`ros2 node list` returns empty with the daemon disabled). `SimulationEvidence.simulation_session_id` is checked as a backstop.
- **Out of scope:** no Docker and no new IPC socket directories.
- **Parallel scheduling:** remove only the reservation-serving parts of the parallel code (`RpcWireReceipt`, `call_with_receipt` and their callers) and leave the rest unchanged. "Broker" in `parallel_ipc.py` and `parallel_*_runtime.py` mostly means the perception inference Broker from `main`, which stays.

## R5. Cleanup inventory (replaces the base plan's §2)

Rules, for every row:
1. List the consumers before changing anything, with `rg -n -w <stem> src scripts tools`.
2. Implement the new owner first.
3. Delete or rewrite each test of the old contract and record `REPLACED_BY=<new test or "contract removed: design 10-06 §2.1">` in `writer-artifacts/b3-cleanup.tsv`.
4. Check imports, `setup.py` entries, CMake targets, plugin XML, configs, schemas, RPC names, `source_provenance.py` rows and doc references.
5. No skip/xfail, and no compatibility switch.

Back up every deleted file into `<dispatch>/writer-artifacts/b3-deleted/` with its path and sha256 before removing it. A tracked file deleted in the worktree is also recoverable from HEAD. An uncommitted file is not, so the backup is required.

| Group | Files (from s2-facts §5 / Appendix A–B) | New owner | Notes |
|---|---|---|---|
| C++ broker chain (`so101_mujoco_support`) | `BrokerOwnedTrajectoryController`, `controller_reservation_socket/protocol/provision`, `controller_goal_admission.hpp`, `bound_reservation.hpp`, `controller_goal_types.hpp`, `controller_ingress_witness`, `controller_stop_witness`, `controller_native_context`, `controller_callback_lifetime`, `native_goal_cdr`, `native_trajectory_sampler`, `native_sampler_c_api`, `sha256.hpp` (only if used solely by the chain), `so101_trajectory_controllers.xml`, their CMake targets and 17 gtests | stock JTC (R1) | Keep `simulation_evidence_plugin`, `physics_step_fence.hpp`, the msgs, `graceful_shutdown_move_group.cpp`, and the gtests `test_simulation_evidence_plugin` and `test_physics_step_fence`. |
| Python broker and reservation (HEAD-tracked) | `command_broker.py`, `ros_broker.py`, `broker_execution.py`, `broker_authority_composition.py`, `broker_authority_wiring.py`, `controller_reservation_client.py`, `controller_reservation_provision.py`, `dispatch_transaction.py`, `visible_approach_commit_ingress.py`, `ros_controller_port.py`, `leased_action_client.py`, `cli/act_command_broker.py` + its `setup.py` entry | R2 (plain `ActionClient`, `MoveItExecutionClient`) | See the decision gate below for consumers outside the chain (Task8, calibration, gate6). |
| Python native/teacher chain (uncommitted) | `teacher_native_forward/runtime/reconstruction/path_safety`, `native_controller_context`, `native_process_provenance`, `native_trajectory_sampler`, `teacher_bound_authority`, `teacher_bound_timing`, `teacher_owner_peer`, `teacher_physics_source`, `ros_teacher_physics_source`, `teacher_point_of_use`, `controller_initial_empty_observation`, `controller_retirement_observation`, `teacher_forward_diagnostics`, `teacher_goal_capture`, `teacher_trajectory`, `teacher_reset_binding`, `teacher_initial_empty_reset`, `teacher_episode_binding`, `teacher_coordinator_receipt`, `teacher_phase_lifecycle`, `act/native_dispatch.py`, `native_stop.py`, `broker_stop_policy.py`, `runtime/act_first_episode_composition.py`, `runtime/teacher_worker_lifecycle.py` | R2 / R3 | `native_endpoints.py`: keep only the validators QC still uses (base D4); delete the rest. |
| Teacher safety modules | `teacher_cup_safety.py`, `teacher_table_support.py` | the R2 monitor and release-support check | They depend on `TeacherPhysicsSelection`, which is deleted. Move the force, compression and support thresholds into the monitor with their existing values, then delete the modules. |
| Teleop ACT branches | `bridge.py:394-405`, `act_stack_probes.py:15-16,95-98`, `ros_child.py:246-259` (`_start_ros_broker`), the ACT branch in `server.py` + `act_control.py`, `controller_reservation_paths.py`; tests `test_controller_reservation_paths.py`, `test_act_worker_port.py`, `test_act_ros_child.py`, `test_act_stack_probes.py` | normal teleop (plain `ExecuteTrajectory` + JTC) | Delete only lines that refer to controller reservation. In arbiter/admission, "reservation" means the global mutation `Reservation`: do not touch it. The normal teleop tests must stay green. |
| Runtime and provenance | `launch_composition.py` broker node, `parallel_ipc.py` `RpcWireReceipt`/`call_with_receipt`, `parallel_worker_runtime.py` reservation assembly, `source_provenance.py` rows `command_broker` and `broker_owned_controller_plugin` | R2 / R4 | — |
| QC and recorder | `recorder_data_side.py:61-109`, the `native_dispatch_v1` rules in `episode_qc.py` / `episode_audit.py` | R3 | — |

**Decision gate for consumers outside the chain.** `command_broker` is also imported by Task8, calibration and gate6 modules (s2-facts §5). Before deleting it, the writer lists each such consumer and checks whether its feature works only through the broker (the superseded Task8 live path), or whether it is a separate feature that would break.
- The writer writes `writer-artifacts/b3-external-consumers.md`. The main agent decides each row before deletion.
- Default under the standing authorization: when a consumer is itself a broker-only ACT path superseded by the 10-05/10-06 designs, it is deleted with its tests and listed.
- Any non-ACT feature, or anything that exists in `main`, is kept working. Only its broker dependency is cut.

## R6. Phases and gates (replaces the base plan's §3 A-phases from now on)

Each phase follows the same sequence:
1. Ledger PLANNED.
2. Writer TDD: RED on the unchanged source, then GREEN.
3. Related tests (`-n 8`, plus `-n 1` for directly changed files).
4. Main-agent review of the diff and the test changes.
5. Ledger result.

- **B1, Teacher on MoveIt/JTC:** R1 yaml and the vendored-fork move, the R2 seams and stop paths, with the RED tests in the R2 table. A fixture test drives a full collection-off pick-place through `ExecuteTrajectory` fakes and checks that no broker module is imported (assert on `sys.modules`).
- **B2, labels and events:** R3 QoS, `SO101_TEACHER_EVENT_V2`, and the switch of the Recorder data side and QC away from dispatch receipts. RED tests: a reference gap makes the data INVALID; a cross-reset frame makes it INVALID; a V1 event is rejected; a reliable depth-1000 subscription is used.
- **B3, deletions:** R5 with the cleanup TSV, backups and the external-consumer gate. Done when `rg -w` finds no reference to any deleted stem in `src/ scripts/ tools/`, and the full ordinary Python set and the reduced ctest pass.
- **B4, freeze and gates.** The base plan's §4 applies, with changes:
  - `support-colcon` is required because C++ changed;
  - the installed-tree checks from R1 apply;
  - `cycle.zsh`/`live.zsh` and the TA scripts they call get new revisions wherever they reference broker sockets, the broker node or reservation provisioning (for example prestart socket checks). Each changed script is a new file revision, recorded in the ledger;
  - the watcher no longer expects a broker process.

## R7. Live runs

These are the base plan's §5 cases L1–L7, with these changes:
- L1 also carries the R3 L0 sidecar measurement and R4 prestart domain check.
- The L3–L7 "no data-sourced cancel" scan uses the Teacher and worker logs. There is no broker log.
- A Teacher-side cancel in L3–L7 must trace to a monitor reason, the deadline or a user stop, never to a data event.
- Expected results and acceptance criteria are unchanged.

## R8. Inline self review

- **Covers amendment §2–§8.** §3 → R2; §4 → R2 table; §5 → R3; §6 → R5; §7 → R4; §8 → R6/R7.
- **Corrections to the amendment, from facts:**
  - the 0.01 rad start-drift check is new on the dynamic path;
  - the `controller_state` fields are `reference`/`output`;
  - teleop does not depend on reservation; the arbiter/admission "Reservation" is a different concept;
  - more C++ files belong to the chain than the amendment lists.
- **Not lowered:** data contract, force/compression limits, support-before-open, collision constraints, controller failure handling, start drift and user/deadline stop.
- **Removed:** ownership, permit and generation protections. The amendment drops the exclusive-ownership requirement, so they go.
- **Risks:**
  - B3 is large and touches Task8/calibration/gate6 consumers, hence the decision gate;
  - the JTC behaviour (idle publish, stamp grid) is unverified until L0;
  - moving the vendored fork could break a build that depended on it, which B4 checks.
- **No new user decisions are needed.** If a protection cannot be kept as written, the exact item is reported.

## R9. Binding changes from the independent review (`writer-artifacts/s2-plan-review.md`, PASS-WITH-CHANGES)

These override R1–R7 where they conflict. The review numbering is kept.

1. **Release without the broker.**
   - The release scope is `(simulation_session_id, reset_epoch, attempt_id)`. It replaces the lease token used at `dynamic_mujoco_execution.py:1436`.
   - The normal-stop proof is the preceding `ExecuteTrajectory` SUCCEEDED result, followed by the original `_controllers_stopped` check on the Teacher's own `/joint_states`. It replaces `_collection_port.stop()` at `:1452`.
   - `_release_dispatch_guard` and its 100 ms permit are deleted.
   - The `normal_stop` Teacher event payload is built from that proof: joint positions, velocities and sim stamp.
   - Seams to remove: `:204-212`, `:1289`, `:1320`, `:1903` and `_close_teacher_sequence`. The writer lists any other seams it finds before editing.
2. **Where stops go.**
   - Force, compression, collision, state-unavailable, deadline, user and parent-death stops go straight to `ERROR`. They never go to `RECOVER_*` and never send a new goal.
   - Only a controller-originated failure may take the original `RECOVER_*` path. That means an `ExecuteTrajectory` reject or abort that our own cancel did not cause.
   - A cancel that does not settle within `_cancel_and_settle` (5 s) is terminal. The worker then runs `cancel_and_confirm_parallel_goals`.
   - `RECOVER_OPEN_GRIPPER` must pass support-before-open. If support is not proved, it does not open: it holds and ends in `ERROR`.
3. **Gripper stop hook.** `GripperClient.command` gets the same `monitor` hook and stop-flag check as the arm path, and cancels its goal on a raise. RED tests: compression during `CLOSE_GRIPPER`, the deadline flag and the user flag each cancel a gripper goal.
4. **Force and compression, exactly.** Both checks are kept and neither is loosened:
   - the original `_motion_monitor` maximum-force limit of 11.60 N;
   - the broker's cup-safety rule, ported verbatim: summed contact normal force > 1.158 N and compression > 1.25e-4 m, from `contact_calibration.yaml:195-196`. It uses the same phase set, observer fields and evaluation as `teacher_cup_safety.py` / `teacher_table_support.py`.

   Before deleting those modules, the writer writes a port table (metric, threshold source, phases, fields) into `writer-artifacts/b1-safety-port.md`. The modules' existing threshold test vectors are reused as RED tests against the monitor.
5. **Collision stop.** The robot–environment dangerous pairs from `phase_contact_allowlist.py` stay a monitor stop (raise → cancel → `ERROR`). Cup-contact pairs that are only process expectations are audit-only (D3).
6. **Stop timings.**
   - The monitor reads the latest observer state without blocking. It does not use `_snapshot()`, which waits 2.0 s. If state is older than `state_max_age_s` (0.5 s), the safety checks that need it count as unavailable. If it stays unavailable for longer than `state_unavailable_stop_s` (1.0 s), the monitor stops.
   - **SIGINT/SIGTERM:** the Teacher process uses `rclpy.init(signal_handler_options=SignalHandlerOptions.NO)`. A handler only sets a stop flag. The monitor or gripper hook sees the flag on the executing thread, raises, cancels and settles; the process then shuts down rclpy and exits.
   - **Deadline:** the watchdog only sets the deadline flag. The flag is checked by the monitor, the gripper hook and the state-machine loop before any new goal. No thread other than the executing one calls `cancel_goal_async`.
   - **Parent death:** the stop-flag check also compares `os.getppid()` with the parent pid recorded at start. A change sets the user-stop flag, with reason `PARENT_DIED`.
7. **Every `make_action_client` call site.** All call sites return to plain `ActionClient`, as in `main`. Besides the B1 seams, these include:
   - `backends/mujoco/reset.py`;
   - the nine `qualified_phases/*` files;
   - the live calibration runner, `contact_live_session` and `act_control`.

   The writer enumerates them with `rg -n make_action_client src` before and after; after B3 the result must be empty.
8. **Reset owner.**
   - Reset and pause return to the original `main` path (`backends/mujoco/reset.py` and the parallel runtime's pre-ACT reset), driven by the worker. `teacher_worker_lifecycle` is removed from `parallel_ros_runtime.py:885-1014,1951-1965` and `mujoco_parallel_batch.py:2480`.
   - `verified_reset_boundary` is the first `SimulationEvidence` after the reset whose `simulation_session_id` and new `reset_epoch` match. The Teacher's observer reads it and the Teacher publishes it as the `reset_complete` event.
   - `/act_command_broker` is removed from the required nodes at `parallel_ros_runtime.py:821`.
   - Before editing, the writer documents in `writer-artifacts/b1-reset-owner.md` what the `main` reset path does. If it lacks something the kept contract needs, stop and report.
9. **V2 sources for the Recorder.** Each item below gets RED tests.

| Recorder input | Old V1 source | New V2 source |
|---|---|---|
| `first_command` | `native_dispatch` | the first motion `phase_begin` event, which carries the sim stamp at which the Teacher sent the goal |
| Verified reset | `native_start` | the `reset_complete` event (item 8) |
| Normal-end window | `sequence_complete` | the `normal_stop` event (item 1) followed by the `terminal` event |

10. **Gaps, without sequence numbers.**
    - A `controller_state` gap is any consecutive header-stamp step, per controller inside the episode window, that is not one controller period (2 ms at `update_rate` 500).
    - The Recorder counts gaps and seals the count. QC requires zero gaps in the label-relevant window.
    - The JTC publisher can drop frames whatever the reader's queue depth (realtime `try_publish`, writer history 10). A drop is a data INVALID, never a control event.
    - The reference port's buffer is resized to hold at least 2 s by stamp, replacing `max_frames=256` and `max_age_s=0.1`. Its age is measured from the stamp.
11. **Ordering.** R1 (the yaml switch and the vendored JTC move) moves from B1 into B3. B3 also:
    - fixes `execution_snapshot.py:21-22,163` and the `source_provenance.py` rows;
    - replaces `test_act_teacher_native_runtime.py:202-208` and `test_act_first_episode_station.py:176`;
    - handles the binding in `task8-calibration-measurement-contract-v2.json:7` under the item-13 gate.

    B1 works on fixtures and does not need the yaml change.
12. **B4 tooling revisions.** Each is a new file revision recorded in the ledger:
    - `freeze-copy-build-r5`: drop `--allow-overriding joint_trajectory_controller` and use a fresh install base;
    - qualified gate `r8`: remove JTC from the native/support package selects, and add a `teleop-colcon` gate (also run at the end of B3);
    - `prepare-r4`: drop `--broker-stop-policy`;
    - `live-r5`: the JTC prefix must resolve to `/opt/ros/jazzy`;
    - the watcher no longer expects a broker process;
    - `cycle.zsh`/`live.zsh` call the new revisions.
13. **External-consumer gate, widened.**
    - The gate also covers `ros_neck.py`, `contact_live_calibration.py`, `pick_place_*`, and teleop `test_server_safety.py` / `test_act_ownership.py`. These two test files are split: their broker cases are deleted and the rest is kept.
    - The default delete rule never removes a producer or validator of an input the kept Teacher or QC uses, such as contact calibration or `phase_contact_allowlist`. Those modules keep working; only their broker dependency is cut.

**Non-blocking items, adopted:**
- **L0 timing probe before B2.** One short read-only probe on the installed freeze `m9qnDMSz`, using the original pick-place config (`config/mujoco/ros2_controllers.yaml`, stock JTC type). A sidecar records `controller_state` stamps for 30 s idle plus one arm trajectory sent through the CLI. It measures the idle publish rate, the stamp step histogram and the drops. One stack only; no ACT broker.
- **"Broker module" in the B1 `sys.modules` check** means the R5 file list.
- **The vendored JTC** is archived under `<platform root>/archived/act-data/teacher-moveit-simplification-<stamp>/vendored-jtc/`.

**Re-review additions (binding; `s2-plan-review.md` "Re-review"):**
- **A. Item 4, the cup-safety port.** The ported rule reads the Teacher observer's `SimulationEvidence` contact lists, not raw qpos and not `TeacherPhysicsSelection`.
  - **Summed normal force:** left + right + other contacts.
  - **Compression:** `max(0, -signed_distance_m)` over the left and right contacts.
  - **Truncated evidence:** `truncated=True` counts as unavailable, never as zero force.
  - **Audit-only:** the qpos-based hold and stability parts.
  - **Where the check applies:** `b1-safety-port.md` states, per phase, whether the 1.158 N / 1.25e-4 m check is continuous or limited to certain phases, with the old broker point-of-use phases as reference.
  - **Offline replay before L1:** replay the check against the CP-3362 recorded evidence and count the would-be trips. A trip on a normal grasp means stop and report; do not raise the threshold.
- **B. Item 6, where the stop flag is checked.** The flag is never raised from `_progress()`. During an active goal it raises only from `monitor()`, which `executor.py` turns into a cancel. It is also checked in every wait loop with no active goal:
  - `_call` service waits and planning;
  - `_joint_state` and `_settled_snapshot`;
  - `_controllers_stopped` and `_first_source_after_stop`.

  The RED test for "SIGINT exits ≤ 6 s" covers both a goal-active wait and a planning or service wait.
- **C. Item 6, monitor identity checks.** The non-blocking monitor keeps `_snapshot()`'s checks on the latest sample: it raises on a session mismatch, on `paused`, or on a reset-epoch change. One RED test.
- **D. Item 1, stop-proof timestamp.** The normal-stop proof carries `stop_confirmed_wall_s` on the same monotonic clock as observer receipts. `_first_source_after_stop` uses it.
- **E. Item 10, the gap window and the early probe.**
  - **Label-relevant window:** arm and gripper `controller_state` only (neck gaps are diagnostic), from the first grid instant through the last grid target (+0.1 s).
  - **Early probe:** the probe on freeze `m9qnDMSz` measures the vendored fork, which was built with `--allow-overriding`. It records the resolved JTC library path and is provisional only. The binding measurement is the one inside L1 on the apt JTC.

## R10. Cup-joint model fix and contact recalibration (user decisions CP-3387 and CP-3389)

**Background.**
- Live L1 runs CP-3373 to CP-3384 stopped on cup force or compression at the same base-yaw displacement during MOVE_ABOVE_PLACE.
- R-cal-mech and D-facts found the cause: the ACT cup free joint inherits `frictionloss 0.052` / `armature 0.028` from the robot joint defaults (`so101.xml:52`) and has `damping 1.0` (`act/scene.xml:33`), so the cup cannot yaw with the gripper and the pads edge-dig.
- In offline experiments, damping 0.01 + frictionloss 0 + armature 0 removes the runaway: a 0.35 rad yaw at 0.1 rad/s peaks at 1.56 N / 1.03e-4 m.

**User decisions.**
- CP-3387: fix the ACT scene only and re-run the offline calibration; the user approves the limits.
- CP-3389:
  - the live validation is an offline fit plus Teacher spot-checks;
  - the "5 live samples per regime" requirement is replaced, as an explicit, recorded rule deviation;
  - the live collector is not rebuilt.

**Steps.** Each one: ledger PLANNED → writer TDD → review → ledger.
1. **Model (D1).**
   - Set `cup_free_joint` in `assets/mujoco/act/scene.xml` explicitly to `damping="0.01" frictionloss="0" armature="0"`.
   - The main `scene.xml`, `v5_multi_object_scene.xml` and the perception scenes are unchanged.
   - Update every ACT pinned model/scene identity listed in `dfacts.md`: `contact_collector.py:24-25`, the six diagnostic modules, the seven JSONs under `config/mujoco/act/`, and the execution snapshot.
   - Tests:
     - the ACT model carries the three values;
     - the non-ACT scenes are byte-identical to `main`;
     - the rest-stability regression from `dfacts-exp` (a)/(b) passes as a fast offline test.
2. **Collector post_release control (D2).**
   - Fix the scripted release recipe, for example open fully, then retreat the gripper, until the `post_release` predicate (no fingertip contact) is realisable on the new model.
   - The predicates and the fit rules are unchanged.
   - RED: on the new model, post_release is 0 samples before the fix and at least the required count after it.
3. **Offline calibration (D3).**
   - Run the existing offline collector and analyzer on the new model. Every regime and control must be reached.
   - The analyzer gets an explicit validation mode `offline_fit_teacher_spot_check`, recorded in the proposal envelope.
   - The proposal names the user decision (CP-3389) and lists the Teacher spot-check as pending.
   - The default mode still requires the live cohort, so the old rule is not weakened for other uses.
   - The output is a DISABLED proposal with the new fingerprint, limits and evidence paths.
4. **Spot-check activation (D4).**
   - Activate the candidate only for `preselected_target_diagnostic` mode, which is never exportable, via a receipt marked `spot_check_candidate`.
   - Formal and collection modes refuse this receipt kind.
5. **Teacher spot-checks (D5).** Run live, single stack, collection on, on a fresh freeze:
   - **(a) Nominal pick-place:** expected Teacher COMPLETED + endpoint PASS with no cup-limit stop, and the max force and compression recorded against the new limits.
   - **(b) Forced over-squeeze:** a diagnostic-inputs variant sets `gripper_close_target_rad = -0.049`. It must stop with a cup force or compression code at CLOSE_GRIPPER or the hold, before LIFT ends.

   Both results go to the user with the proposal fingerprint and limits. The user approves (or rejects) the final activation by fingerprint.
6. **Final activation (D6).** After user approval, write a normal activation receipt for the approved fingerprint, freeze, and continue with the base plan's L1 → L2 → L3–L7.

**Not changed:**
- the fit formula and regime predicates;
- the strict `>` comparison and the per-step evaluation;
- the 11.6 N limit, collision, physics-hazard and support-before-open stops;
- the data contract.

**Remaining risks:**
- the force margin is narrower (normal 1.547 N vs over 2.236 N);
- the carry margin is 82% / 86% in the offline experiment;
- the live Teacher carry may differ, which is what D5(a) measures. A trip in D5(a) is stop-and-report.

### R10 review changes (binding; `writer-artifacts/r10-plan-review.md`, PASS-WITH-CHANGES)

1. **User gate before D4.**
   - After D3, the user authorises the candidate fingerprint for spot-checks only.
   - The candidate receipt's `approved_by` never names the user.
2. **D3 mode binding.**
   - The validation mode is bound into the fingerprinted payload: `live_collector_sha256` = sha256 of a canonical `{validation_mode: offline_fit_teacher_spot_check, decision: CP-3389}` descriptor.
   - An explicit `--validation-mode` flag is added to `verify_disabled_proposal`, to the analyze functions and to both CLIs. A missing flag means the default mode, which still requires the live cohort; omitting `--live` without the flag is refused.
   - The offline mode still self-classifies the offline cohort and checks the controls.
   - Tests:
     - a default-mode proposal without a live cohort is refused;
     - an envelope whose mode disagrees with its payload is refused.
3. **D4 receipt.**
   - A named receipt field `receipt_kind: spot_check_candidate` is refused by default.
   - Only the frozen-inputs path with `mode == preselected_target_diagnostic` may opt in. Any other mode, or no mode, refuses it, and `load_installed_phase_contact_allowlist` never accepts it.
   - RED tests: formal freeze, no-mode freeze, installed loader, bundle refusal.
   - `result_store.py:291` is guarded by mode, so a candidate-receipt run is never `export_eligible`.
4. **D5(b) pass criterion.** Run on its own single-use freeze with its own policy YAML (`gripper_close_target_rad -0.049`). PASS only if all of these hold:
   - the close is commanded at −0.049;
   - the first stop is `DYNAMIC_CUP_FORCE_EXCEEDED` or `DYNAMIC_CUP_COMPRESSION_EXCEEDED`;
   - the stop is latched in CLOSE_GRIPPER, WAIT_GRASP_STABLE, MICRO_LIFT, WAIT_MICRO_LIFT_STABLE or VERIFY_PHYSICAL_GRASP, before LIFT starts;
   - no collision, physics-hazard (including `static_shadow_crossed` at 1.1579 N), gap, VALIDATION_FAILED, deadline or 11.6 N stop came first.

   Anything else is FAIL: stop and report.
5. **D5(a) pass criterion.**
   - PASS only if the Teacher reaches COMPLETED with endpoint PASS and no stop of any kind.
   - Record for the report:
     - per-state maximum summed force and compression, as a percentage of the limits;
     - maximum single-contact force against 1.1579 N;
     - the release and settle behaviour.
6. **D1 identity pins.**
   - The list is extended: `act/visible_approach_diagnostic.py:17,20` (seven diagnostic modules), `config/act/contact-calibration-schema.json:15-16`, and the 10 test files that pin old hashes.
   - Gate: `rg` finds no `4db48e35` or `3c876e7b` outside docs, the ledger and old evidence.
   - Tests:
     - `act/so101.xml` is byte-identical;
     - the non-ACT scenes are byte-identical to the pre-D1 state (from the `d1-base` backups);
     - the rest and yaw-ramp regressions have numeric bounds.
7. **D2 scope.**
   - Edit only the collector phases after "hold". Prefer mirroring the Teacher OPEN_GRIPPER→RETREAT from the motion-policy waypoints, so the motion sha is unchanged.
   - Keep `_SCENARIOS`, `_qualifies`, the close values and the hard limits unchanged.
   - Test that the windows of the other eight regimes are identical before and after.
   - Report the D2 change to the user.
8. **Also unchanged:** `static_shadow_force_n` 1.1579 N, `DYNAMIC_FORCE_LIMIT_EXCEEDED`, the `_enforce_safety` stop order, the collector hard limits (11.6 N, 0.03 m), and `task_scene.yaml` (unused).
9. **D6.**
   - The final freeze holds only a normal receipt for the unchanged D3 fingerprint. Any refit restarts at D3 and goes back through the user gate, D4 and D5.
   - `approval_reference` cites the user decision and the D5 run ids.
   - The approval report covers:
     - the rule deviation;
     - the D2 change;
     - the D5 margins;
     - the narrow force gap (1.547 vs 2.236 N);
     - the stable_hold sensitivity to damping (lost at 0.001).

## Amendment 2026-10-07 (CP-3410): raw physics chunk delivery is telemetry, not a rule

User-authorized data-contract change. The history above is not rewritten; this note supersedes the per-chunk 100 ms delivery rule
wherever the plans, tests or QC state it.

**Why.** The rule (`receipt - newest sample begin <= 0.1 s`, `PHYSICS_RAW_CLOCK_INVALID`, permanent) failed L2 recordings on a single late
chunk: CP-3379 (313 ms, first chunk), CP-3409 (283 ms, 26 chunks in, 2.1 s after ready, before any K2 association, with a 334 ms hole
in the controller stamps at the same instant: the simulation producer stalled). The delay is the end-to-end path sample -> publish
thread -> DDS -> spooler, outside the Recorder's control, and the spooler performs no real-time intervention, so the rule discarded
valid, contiguous evidence. The spooler's receipt stamp stays; what it measures is now recorded, not judged.

**New rule.** A late chunk is admitted and audited. The data fails only on
- continuity (sequence, step and clock contiguity, receipt order), session and epoch, source loss, truncation and every other content
  check: unchanged;
- processing errors: deserialization failure (`PHYSICS_RAW_DESERIALIZE_FAILED`), spool corruption, spooler death, spool overflow;
- backlog beyond the frozen Recorder policy `episode_recorder_v1`: unprocessed spool frames > `physics_spool_backlog_frames_max`
  (64, `PHYSICS_RAW_SPOOL_BACKLOG_EXCEEDED`), and the newest received sample's begin more than `physics_receiver_lag_max_s`
  (5.0 s) behind now (`PHYSICS_RAW_RECEIVER_LAG_EXCEEDED`, ends when the tail begins).
  Rationale for the numbers is in the policy file (nominal peak backlog 6, worst observed lag 0.85 s; bounded by the 128-chunk pending queue
  and the 4096-step, 8.19 s lookup history).

**Publish-path instrumentation (same change set).** `PhysicsStepEvidenceChunk` gains `handoff_monotonic_ns` (physics thread posts the chunk),
`publish_monotonic_ns` (the publishing thread, immediately before `publish()`) and `publish_deferrals_total` (cumulative trylock deferrals).
`simulation_evidence_plugin.cpp` publishes through its own `StampingChunkPublisher` thread (`realtime_tools::RealtimePublisher` has no hook at
the publish call); the physics thread still never blocks. The Recorder telemetry splits sample -> handoff, handoff -> publish,
publish -> receipt and total (count, p50, p90, p99, max).

**CHANGED RULES (complete list).**
1. `raw_physics_chunks.verify_raw_chunk`: the age rule and its `max_age_s` argument are removed (used by the adapter, audit append, audit
   readback and QC; the "receipt precedes the sample's own end" clock check stays). The three new chunk fields are part of the closed schema.
2. `ros_episode_physics`: the C4 `stale_before_first` discard is removed (a late first chunk is admitted); new backlog, lag and
   deserialization failures; lateness percentiles; `max_age_s` remains only as the sim-time causal join window of `source_at`.
3. `continuous_capture`: a row whose physics chunk is still in flight (`awaiting_arrival`) waits without the 100 ms wall timer; every other
   source keeps the existing timer. The provider reports in-flight when the newest received sample is older than the grid instant.
4. `recorder_data_side._native_sources_expired` and K2 `_SOURCE_RETRY_S`: the fixed 100 ms / 1 s waits for a raw chunk step are now the receiver-lag
   policy value when a policy is given (defaults unchanged for callers without one).
5. `episode_recorder_v1`: two new required, strictly validated fields.
6. Chunk spooler: converts each chunk to its record in its own process (CPU, no rule change), writer threads, parent-death guard.

**Unchanged on purpose.** Teacher-side freshness and safety rules; the controller-state spooler (no per-message delivery rule exists there:
only ordering, gaps and the 2 s reference window); the world/scene receipt join (scene receipt within 100 ms of its world record); camera and
scene sample causal windows in simulation time; the 10 Hz grid, labels, seal and QC.

### Amendment 2026-10-07 (CP-3414): Teacher events received before the capture started

Changed rule: `RECORDER_NOT_READY_BEFORE_TEACHER_EVENT` is no longer latched when a non-scene Teacher event is received
before the capture starts. The episode needs a verified reset boundary that the capture covers (`episode_qc` boundary order
verified_reset <= capture_start <= initial_capture <= first_command <= normal_stop <= final_capture, both clocks), not a
capture that is already running at receipt. The Recorder now holds such events (bounded at 512), checks their sequence on
receipt as before, and retains them in order right after the capture starts. At replay a `reset_complete` stamped before the
earliest retained physics sample is INVALID (`RECORDER_EVENT_BEFORE_RETAINED_HISTORY`), a start observation or goal-sending
`phase_begin` stamped before the capture start is INVALID (`RECORDER_TEACHER_EVENT_BEFORE_CAPTURE_START`), a buffer overflow is
INVALID (`RECORDER_DEFERRED_EVENT_OVERFLOW`), and a capture that never starts still latches
`RECORDER_NOT_READY_BEFORE_TEACHER_EVENT`. Unchanged: sequence and gap checks, session/epoch and content checks, QC boundary
order, and the rule that the Teacher is never blocked or delayed. The start gate now records why it refused, by cause.

### Amendment 2026-10-07 (CP-3416): deterministic capture start

Changed rules: (1) the world evidence a capture is retained from is the newest retained world record at or before the seed
pair's oldest camera stamp, not the newest world record of the moment; (2) a native physics sample that is still in flight
(received newest older than the seed stamp) no longer closes the start gate: the capture waits for it under the receiver-lag
policy, any other non-causal row source still closes it; (3) a Teacher-named K2 source that has not arrived is retried like
any source within the same bound. Unchanged: every row source must be present before a row is accepted, QC boundary order,
all continuity, session/epoch and content checks, and the rule that the Teacher is never blocked. The gate reports its
outcomes by cause in `recorder-telemetry.json` (`sources.start_gate`), `recorder-result.json` (`stall_telemetry.start_gate`)
and the NOT_READY reason.

### Amendment 2026-10-07 (CP-3418): world sequence gaps are judged where the data is

Changed rule: the Recorder's world observer reports a publisher sequence gap instead of holding a sticky hazard. The world
records the capture retains (from the predecessor of its start) must be gap-free: a gap inside them is INVALID
(`atomic evidence publisher sequence gap`, raised when they are drained), a gap before them is outside the record. Teacher
scene operations are handed to K2 even after the verdict is INVALID. Unchanged: the gap rule for retained data, the geometry
check, every QC rule, and the rule that the Teacher is never blocked.

### Amendment 2026-10-07 (CP-3420, CP-3421): one source-age rule; source alignment renamed

Changed rules: (1) every layer admits a source by `synchronizer.source_age_ok_ns` (integer nanoseconds, 100 ms): the recorder's
row audit no longer compares float seconds; (2) each drain stage runs on every pass and a world/scene join failure moves the
cursor on. Rename only (CP-3421): the label K2 became "source alignment" in `src` and `test` (record kind `source_alignment_v1`,
`RECORDER_SOURCE_ALIGNMENT_*` reasons, `source-alignment-failure.json`, `ALIGNMENT_RETRY_S`); the alignment operation values
(`initial`, `attach`, `detach`) are the Teacher's operation names and are unchanged. No behaviour change in the rename.

### Amendment 2026-10-07 (CP-3423): loop load and the joint-state rings

Changed: the initial-boundary search settles once and is not rerun after the first command or after a failure; the arm and neck
rings of the synchronizer hold 2048 samples (4 s at 500 Hz). The order rule verified_reset <= capture_start is UNCHANGED and is
reported as unmeetable by a live start against the Teacher's current reset boundary (see rec12-pacing.md); the decision is open.

### Amendment 2026-10-07 (CP-3425): the capture runs before the Teacher starts

Changed rules (new episodes only; version-2 evidence is never re-validated and no alias is kept):
1. The `initial` source alignment (schema 3) is the Recorder's OWN read of the planning scene before the Teacher's SETUP. It asserts
   what the worker's initial gate guarantees (`parallel_ros_runtime` POINT_INITIAL_GATE): no attached collision object. World objects
   and colours are recorded, not required. It depends on no Teacher event.
2. The Teacher's SETUP apply of the task scene is a `world_sync` alignment (cup pose audit-only), and one whose read-back lies
   before the first command is required by QC (`NATIVE_QC_WORLD_SYNC_REQUIRED`).
3. The verified reset (boundary schema 3) is the Recorder's first retained evidence of the epoch that still has its physics step, on
   the evidence producer's clock (sample sim time, producer monotonic interval), not a receipt time. The Teacher's `reset_complete`
   must be consistent with it (same scope; its sequence and sim time not earlier).
4. QC order on both clocks: verified_reset <= capture_start <= initial_capture <= Teacher start (`reset_complete`) <= first command.
5. The orchestrator waits `ready_timeout_s` for LISTENING and then `capturing_timeout_s` (10 s) for CAPTURING (ready file rewritten when
   the initial boundary is committed). On a timeout the Teacher starts anyway; the data is INVALID
   (`RECORDER_NOT_CAPTURING_BEFORE_TEACHER_START`).
Unchanged: the Teacher's behaviour, every row source and continuity rule, the gap rule for retained world records.
