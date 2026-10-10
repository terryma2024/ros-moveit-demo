# SO-101 Head neck: thin JTC subclass, retire the reservation and witness stack

**Status.** Design revision 3 with the review-3 changes applied (PASS-WITH-CHANGES), 2026-10-10.
- Owner: root (Claude Opus 5.5). Execution: one Claude Sonnet 5.5 executor. Ledger entries: CP-3530, CP-3534, CP-3535, CP-3536.
- Reviews: revision 1 failed the independent review (13 findings), and revision 2 failed the re-review (2 blockers plus partial items). The reviewer was a fresh Opus instance, which deviates from the AGENTS.md rule that names Astra as the reviewer; the deviation is recorded.

**User decisions (2026-10-10).**
- Thin JTC subclass for the neck; stock JTC for the arm and gripper.
- The shape, speed and prefix checks move to the Python pre-dispatch side.
- The calibration line is ported, not dropped.

## 1. Controllers

- **Arm and gripper (Head stack).** Stock `joint_trajectory_controller/JointTrajectoryController` 4.42.1. The Head controllers file keeps today's `interpolate_from_desired_state: true` for these two; this is intended.
- **Neck.** `so101_mujoco_support/HeadNeckTrajectoryController`, a subclass of the 4.42.1 JTC. The controller manager is 4.48.0.

### 1.1 Input closure

Applied after every base `on_configure`, the same way as the broker's existing code (`broker_owned_trajectory_controller.cpp:755-822`):
- Reset the protected `joint_command_subscriber_` and set `subscriber_is_active_ = false`.
- Drop the private `scaling_factor_sub_` through the explicit-instantiation access idiom already in use (f79134a58, cpp:675-693).
- Reset `query_state_srv_`, as the broker does (cpp:850).
- Force the protected `joints_angle_wraparound_` to false.
- Freeze the immutable parameters as read-only and refuse configure on a mismatch: open-loop off, `interpolate_from_desired_state` false, splines on, partial goals off, integration off, 500 Hz.

### 1.2 Per-tick checks in `update()`

Each check runs before the base update:
- If the protected `scaling_factor_` or `scaling_factor_cmd_` is not 1.0, return ERROR.
- Read the state with the protected `read_state_from_state_interfaces`. If the measured or commanded state is not finite, return ERROR.
- If the latch (§1.4) is set and a trajectory is pending or active, abort it through the protected `rt_active_goal_` / `rt_has_pending_goal_` handling (cpp:137-150) and hold.

### 1.3 ERROR consequence

Controller manager 4.48.0 deactivates a controller whose `update()` returned ERROR. The JTC's `on_deactivate` then writes the last commanded position; the executor must verify this against the 4.42.1 source. The subclass's `on_deactivate` must therefore never forward a non-finite command: if the last command is not finite, it writes the last finite one. On the Python side, the run faults with `HEAD_NECK_CONTROLLER_DEACTIVATED` once `controller_state` stops for longer than the window deadline, or once `list_controllers` shows the neck is not active.

### 1.4 Goal admission and dead-man

**Action server.** The goal callbacks in 4.42.1 are non-virtual, so the subclass destroys the protected `action_server_` after the base configure and re-creates it with wrapped callbacks, as the broker does (cpp:782-814). A goal is rejected unless all of these hold:
- an owner is connected;
- the latch is clear;
- the controller is active.

The latch is checked again in `update()` (§1.2).

**Socket.** One Unix stream socket per activation.
- The directory comes from a parameter. The owner creates it before activation with mode 0700, and the controller refuses to activate if the directory is missing, not owned by its own uid, or has a different mode.
- The socket path is `<dir>/neck-<activation_id>.sock`. `activation_id` is a counter that increases on every activation.
- A stale path is unlinked only if it is not live.
- The controller accepts one peer only: a second connect is refused. The peer is checked with `SO_PEERCRED`: same uid, and the pid named in a parameter set by the owner. The pid is recorded.
- Until the owner connects, every goal is rejected. This is the rule that leaves no unguarded window.

**Heartbeat.**
- The owner sends one byte every 20 ms from a separate helper process, which the Head runtime spawns, so the Python GIL cannot stall the socket.
- **The helper is tied to the runtime (review 3, issue 1).**
  - It sets `PR_SET_PDEATHSIG(SIGKILL)` and re-checks its parent pid after setting it.
  - It sends heartbeats only while liveness ticks keep arriving from the runtime over a pipe. If no tick arrives for 150 ms, or the pipe reaches EOF, the heartbeat stops at once.
  - So a runtime that is killed or wedged latches the controller within 150 ms + 200 ms.
- The controller latches after 200 ms with no byte, or on EOF. The policy fields are `head_deadman_period_s`, `head_deadman_timeout_s` and `head_deadman_liveness_s` (0.15).
- **The peer pid parameter (review 3, issue 2)** holds the helper's pid.
  - It is set exactly once per activation, before activate.
  - It is read-only while the controller is active, and any change request is refused.
  - It is read back in `CONTROLLER_READBACK`.
- An I/O thread outside the realtime loop reads the socket and sets an atomic that the realtime side reads. `on_deactivate` and `on_cleanup` join the thread and close the socket.

**Latch.**
- Setting it aborts the active goal and holds the last finite position.
- It refuses all goals until the controller is deactivated and activated again, and any new activation also requires a fresh owner connection.
- A planned close (for example at the end of a case, after the stop proof) is an expected latch. The owner writes `DEADMAN_CLOSED_PLANNED` before closing, and the stop proof is already complete at that point.

**Reset path.** `head_execution_reset.py` switches controllers mid-run.
- Every expected deactivate/activate is written to the event log in advance as `CONTROLLER_SWITCH_PLANNED`, carrying the old and new `activation_id`.
- After each activation the owner reconnects to the new socket.
- Any activation or deactivation that was not planned, seen through `list_controllers` polling or a gap in the `activation_id` sequence, faults the run with `HEAD_UNPLANNED_CONTROLLER_SWITCH`.

## 2. Python pre-dispatch

- **Guard.** Extend the existing `HeadTrajectoryGuard` (`head_trajectory_guard.py:378-543`).

  | Broker check | Where it moves | Fidelity |
  |---|---|---|
  | 2-point shape, duration in [0.1, 5] s, peak velocity and acceleration, safe interval inside (−π, π) | guard, before dispatch | exact |
  | goal arrived late; header lead ≤ first + 14 ms; measured \|v\| ≤ 0.04136 and \|Δq\| ≤ 0.002 at the consuming tick | guard, before dispatch, against the latest `controller_state` | approximated |
  | per-tick geometry limit while the goal is active | monitor after acceptance: `controller_state` reference compared against the sealed quintic and its envelope; divergence → cancel → stop path, refusal code `HEAD_REFERENCE_DIVERGED` | detected after the fact |

  The limits live in one Python constants module. The subclass holds none of them.
- **Graph check.**
  - Endpoint GIDs are read with `get_subscriptions_info_by_topic` on `/neck_controller/follow_joint_trajectory/_action/feedback` and `/_action/status`, and with `get_publishers_info_by_topic` on `/neck_controller/joint_trajectory` and the speed-scaling topic.
  - The allowed endpoints are this runtime's own GIDs, recorded at startup. Foreign subscriptions are also allowed when their node name is on a list, for example the ACT raw recorder or `ros2 bag`, and they are recorded in `GRAPH_PROOF` (review 3, issue 5).
  - The arm and gripper action topics must have no foreign clients. Clients of the controller manager `switch_controller` and `list_controllers` services are allowed and audited: each one is recorded with its node.
  - The check is polled at the watchdog period. Any change faults the run with `HEAD_GRAPH_CHANGED`.

## 3. Stop proof

**Window.** 51 consecutive `/neck_controller/controller_state` samples on the 2 ms sim-stamp grid, where every sample has:
- \|feedback velocity\| ≤ 0.002 and \|reference velocity\| ≤ 0.002;
- the same reference position across the window, which stands in for "holding and no active goal", since `controller_state` carries neither;
- a monotonic receive age ≤ 200 ms.

The owner sends no goal during the window, and if one is sent the window is void.

**Subscriber.** It runs on its own executor and thread, with reliable QoS and depth 64. A gap restarts the window. Policy field `head_stop_window_deadline_s` sets the deadline; if it passes, the refusal code is `HEAD_STOP_WINDOW_UNAVAILABLE`.

**When the window is required.**
- At startup, before the first goal.
- At the end of a case, in order: a terminal result or cancel, then the raw `/joint_states` stop proof (3 samples), then the window, then `DEADMAN_CLOSED_PLANNED`.
- `stop_confirmed` requires all three of the terminal result, the raw stop and the window.

**Shadow comparison.** It runs on the current broker stack before the switch, over the 900000 case, and its verdict blocks step 2 of §7.
- At startup, the shadow window must complete no later than the native PREARM READY sim stamp + 102 ms.
- At the end, the anchor is the raw-stop confirmation sim stamp in `CANCEL_STOP`, because the native close receipt carries no sim stamp (review 3, issue 3). The shadow window must complete within `head_stop_window_deadline_s` after it.
- In both cases the shadow and native verdicts must be equal: both pass or both fail.
- Any disagreement blocks the switch.
- Besides the passing 900000 run, one shadow negative must show fail/fail agreement: either a goal injected into the window, or motion forced before it.

## 4. Protocol, audit and evidence

`startup_protocol` v2 defines these events:

| Event | Fields |
|---|---|
| `CONTROLLER_READBACK` | controller type, the immutable parameter values, `activation_id` |
| `DEADMAN_ARMED` | socket path, peer pid, `activation_id`, `head_deadman_period_s`, `head_deadman_timeout_s` |
| `GRAPH_PROOF` | allowed GIDs, audited service clients |
| `STARTUP_STOP_WINDOW` | first and last sim stamp, n = 51, max \|v_fb\|, max \|v_ref\|, reference position, max age |
| `CONTROLLER_SWITCH_PLANNED` | old and new `activation_id` |
| `DEADMAN_CLOSED_PLANNED` | `activation_id` |

- **Retirement receipt.** `STOCK_STOP_PROOF` = {the terminal result, the raw-stop sample stamps, the window fields as in `STARTUP_STOP_WINDOW`, `deadman_closed_planned: true`}.
- **Downstream changes.** `_startup_complete`, `may_continue` and `stop_confirmed` in `head_search_functional_campaign.py` follow the v2 events.
- **Audit versions.** `head_run_audit` HFA-009 v1 covers broker-era runs and v2 covers subclass runs. Sealed evidence from before this change, including CP-3532, must still audit and read back unchanged under v1, and a test proves it.

## 5. Ports and deletions

- **Port** to §§1–4: `head_search_restarts.py`, `head_search_stop_measurement.py`, `head_search_qualification_readback.py` (its `publish_provisions` at `:934-943`), `measure-restarts` and `qualify`.
- **Import-graph test.** RED before the deletions, GREEN after.
- **Delete:**
  - the SOGB reservation protocol, provision and socket;
  - goal admission and bound reservation;
  - the stop and ingress witnesses, stop evaluation and the timing collector;
  - the native revocation transport;
  - `BrokerOwnedTrajectoryController`;
  - the Python `controller_reservation_client/provision`, `so101_teleop.unified.controller_reservation_paths`, `head_execution_native`, `head_reservation_authority`, `head_revocation`, `head_native_policy_readback`, `broker_execution` and the broker branch of `ros_neck`;
  - the tests for all of the above.
- **Tooling.** freeze r10, qualify r7, live r17, sitting beside the old versions. `test_b3_cleanup` is tightened to match.

## 6. 120 s hold criterion (a separate experiment, not part of acceptance)

- **Actors and window.** The Head nominal harness is the actor. The hold window runs on the sim clock from the first `controller_state` stamp after the harness's `HOLD_START` event to the stamp at its `HOLD_STOP` event. The expected count (end − start)/2 ms + 1 is computed and recorded.
- **Per controller.** Stamp deltas are exactly 2 ms, with no gaps and no duplicates. The ACT raw recorder records the data, with topic-loss accounting.
- **Overrun and skip attribution.** Uses `execution_time` and periodicity from the controller manager 4.48.0 introspection (`controller_interface_base.hpp:96-103`); the executor confirms these are published.
- **Open item.** The CP-HFP-1028 4 ms skip is still being investigated.

## 7. Order and acceptance

1. Constants module, shadow window, then the shadow comparison (§3). The comparison's verdict gates step 2.
2. The subclass, RED → GREEN for each duty:
   - topic subscription count 0;
   - scaling subscription absent;
   - a forced `scaling_factor_` ≠ 1 returns ERROR (test-only hook);
   - wraparound off after reconfigure;
   - NaN gives ERROR without a non-finite command, then deactivation;
   - a goal before the owner connects is rejected;
   - a second peer is refused;
   - a wrong `SO_PEERCRED` pid is refused;
   - EOF latch;
   - timeout latch, in a GIL-loaded test;
   - a reset cycle needs a reconnect, and an unplanned switch faults.
3. Guard extension, the after-acceptance monitor, the graph check, the v2 protocol, and audit v1/v2.
4. Port the calibration modules, the import-graph test, the deletions, then the tooling.
5. Gates: 0 failures and 0 errors on every package.
6. Sim negative tests. Each states its expected observable, code and time bound:

   | Case | Expected |
   |---|---|
   | foreign action client | its goal is accepted, because owner-only admission does not authenticate action clients. Then `HEAD_GRAPH_CHANGED` within one watchdog period, and the stop path. If its goal diverges from the sealed quintic, `HEAD_REFERENCE_DIVERGED` as well |
   | `~/joint_trajectory` publisher | neck subscription count 0, and the `controller_state` reference unchanged over 1 s |
   | scaling publisher | subscription absent; a forced ≠ 1 gives ERROR |
   | goal inside the stop window | window void, then `HEAD_STOP_WINDOW_UNAVAILABLE` after the deadline |
   | Head runtime SIGKILLed mid-goal (the runtime, not the helper) | within liveness 150 ms + timeout 200 ms + 2 ms: reference velocity 0, goal ABORTED, then the next goal is rejected |
   | Head runtime SIGSTOPped mid-goal | the same latch, within the same bound |
   | NaN tick | ERROR, controller deactivated, no non-finite command written, then `HEAD_NECK_CONTROLLER_DEACTIVATED` |
   | unplanned switch | `HEAD_UNPLANNED_CONTROLLER_SWITCH` |

7. Live, one stack at a time: the Head single case 900000 PASS under v2, then one pick-place Teacher PASS, VALID, readback PASS.

## 8. Remaining regression

- **Admission.** Admission authenticates the owner's dead-man connection, but not individual action clients. A foreign action client that appears between graph polls can get one goal accepted. That goal is bounded by the guard-free subclass checks (closed inputs, NaN, latch), the after-acceptance monitor, and the graph fault at the next poll.
- **Exactness.** The per-tick geometry and lateness checks become approximated or detected after the fact.
- **Timing evidence.** Timing evidence now comes from topics, not from inside the controller.

This is acceptable in sim with a single owner. It is not equivalent on hardware.
