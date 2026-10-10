# SO-101 Head neck: thin JTC subclass, retire the reservation and witness stack

Status: design revision 2, 2026-10-10. Owner: root (Claude Opus 5.5). Execution: one Claude Sonnet 5.5 executor. Ledger: CP-3530, CP-3534, CP-3535.

Revision 1 ("everything on stock JTC") failed independent review. The review was run by a fresh Opus reviewer, which is a recorded deviation from the AGENTS.md rule that names GPT-6 Astra for independent design reviews. The review found these gaps in stock `JointTrajectoryController` 4.42.1:

- it keeps the `~/joint_trajectory` topic input and the speed-scaling input (findings 1);
- it enables angle wraparound on the `continuous` neck joint, and 4.42.1 has no parameter that turns it off (finding 2);
- a cancel on a non-finite state commands a hold at NaN (finding 4);
- it has no owner dead-man (finding 5).

User decision, 2026-10-10: "Thin JTC subclass". This revision follows that decision. The user's earlier answers still apply: the Head-mode shape, speed and prefix checks go to the Python pre-dispatch side, and the Head calibration line is ported, not removed.

## 1. Target

- **Arm and gripper in the Head stack.** Both use stock `joint_trajectory_controller/JointTrajectoryController`, as on the ACT side. The Head controllers file keeps the arm and gripper values the Head inputs file has today: `interpolate_from_desired_state: true`, recorded as intended (finding 12).
- **The neck.** It uses a new thin subclass, `so101_mujoco_support/HeadNeckTrajectoryController`, of about 100–200 lines. It does only four things:
  1. **Closes the extra inputs.** It drops the `~/joint_trajectory` topic subscriber and the speed-scaling subscription, and it faults the controller (goes to ERROR) if a `controller_state` sample would ever carry a scaling factor other than 1.0.
  2. **Forces wraparound off.** For the continuous joint it keeps the unwrapped behaviour that the broker enforces today (`broker_owned_trajectory_controller.cpp:815-836`). It also keeps the broker's immutable configuration: open-loop off, `interpolate_from_desired_state` false, splines, partial and integration goals off, 500 Hz. These are read-only parameters, and a mismatch refuses configure.
  3. **Refuses to hold NaN.** On a non-finite measured or commanded state on any tick, it returns ERROR and does not hold (as `cpp:113-126, 509-515` does today).
  4. **Runs a dead-man.** At activate it opens a per-run Unix socket at a path from a parameter. The Head owner connects once and sends a heartbeat. When the connection closes (EOF) or no heartbeat arrives within `head_fault_connection_timeout_ns`, the controller latches. If the state is finite, it cancels the active goal and holds. It then refuses every new goal until it is deactivated and activated again. If the state is not finite, it goes to ERROR. There is no reservation, no goal binding and no capability exchange.
- **Deleted.** The SOGB v2 reservation protocol, provision and socket; goal admission and bound reservation; the stop and ingress witnesses with their stop evaluation and timing collector; the native revocation transport; `BrokerOwnedTrajectoryController`; and their tests and Python clients (§5).

## 2. Python pre-dispatch side (user decision 1)

- **Guard.** Extend the existing `HeadTrajectoryGuard` (`head_trajectory_guard.py:378-543`, which already holds the shape, duration, extrema and envelope checks). Do not create a parallel class (finding 6).
- **Where each broker check goes** (finding 6):

  | Broker check | New location | Fidelity |
  |---|---|---|
  | 2-point shape, duration in [0.1, 5] s, peak velocity and acceleration, safe interval inside (−π, π) | guard, before dispatch | exact |
  | Goal arrived late (`first_absolute_ns ≤ update_time`), header lead ≤ first + 14 ms, measured \|v\| ≤ 0.04136 and \|Δq\| ≤ 0.002 at the consuming tick | guard, before dispatch, against the latest `controller_state` | approximated |
  | Per-tick geometry limit while the goal runs | monitor after acceptance: the `controller_state` reference is compared with the sealed quintic and envelope, and a divergence cancels the goal and enters the stop path | detected after the fact |
  | Wraparound off, inputs closed, NaN → ERROR, dead-man | subclass | exact |

  The limit values move to one Python constants module, and the subclass's C++ `constexpr` values are checked against it by a test. They are both hard-coded today (`cpp:19-23`, `guard.py:34-41`).
- **Neck senders.** The action client name and the node GID are checked through `get_action_client_names_and_types_by_node` over all nodes. The check runs at startup and is then polled at the watchdog period, so any change faults the run (finding 8). The arm and gripper in the Head stack are not commanded by the Head runtime: the same graph check requires that they have no action clients or publishers at all.

## 3. Stop proof (findings 3 and 7)

- **The 51-sample window.** The window is 51 consecutive `/neck_controller/controller_state` samples on the 2 ms sim-stamp grid, and every sample must satisfy all of these:
  - |feedback velocity| ≤ 0.002 rad/s and |reference velocity| ≤ 0.002 rad/s;
  - the reference position is unchanged across the window;
  - the samples are fresh: monotonic receive age ≤ 200 ms;
  - no goal was sent or accepted inside the window, and none is active.

  Any arriving goal voids the window. These conditions match `ControllerStopWitness` (`controller_stop_witness.hpp:28, 412-443`), and the constants live in the shared Python module.
- **Subscriber.** It runs on its own executor and thread with reliable QoS, depth 64. On a gap it restarts the window. If no valid window completes within the deadline (from policy), the run refuses with the named code `HEAD_STOP_WINDOW_UNAVAILABLE`.
- **Startup proof.** The window must complete before the first goal.
- **End-of-case proof.** In order: a terminal result or cancel, then the existing raw `/joint_states` stop proof, then the window. `stop_confirmed` is all three. The dead-man socket is closed last.
- **Shadow first.** Before the switch, the new window runs in shadow on the current broker stack, which also publishes `controller_state`. The executor compares it with the native witness proof over the 900000 case and reports agreement or disagreement.

## 4. Protocol, audit and evidence versioning (finding 10)

- **New startup protocol.** `startup_protocol` v2 adds the event kinds `STARTUP_STOP_WINDOW`, `GRAPH_PROOF`, `CONTROLLER_READBACK` (the subclass parameters and the type) and `DEADMAN_ARMED`. It replaces `BOOTSTRAP_IDENTITY`, `PREARM_STATUS`, `ARM_RESULT` and `NATIVE_CLOSE`. `STOCK_STOP_PROOF` replaces the native close in the retirement receipt.
- **Code paths that change.** `_startup_complete`, `may_continue` and `stop_confirmed` in `head_search_functional_campaign.py` change to match.
- **Audit versions.** `head_run_audit` HFA-009 is versioned: v1 audits broker-era runs, v2 audits subclass runs. Existing sealed evidence, including CP-3532, must still audit and read back unchanged under v1, and a test proves this.

## 5. Ports and deletions (finding 9)

- **Port** to the new admission, dead-man and stop proof:
  - `head_search_restarts.py`
  - `head_search_stop_measurement.py`
  - `head_search_qualification_readback.py` (it calls `publish_provisions`, at `:934-943`)
  - `measure-restarts` and `qualify`

  `stop_proof` already lives in `head_search_scenarios.py`.
- **Import-graph test.** A test asserts that no remaining module imports any deleted symbol. It must fail (RED) before the deletions and pass after them.
- **Delete** once the import-graph test is green:
  - the C++ files listed in §1;
  - the Python `controller_reservation_client/provision`, `so101_teleop.unified.controller_reservation_paths`, `head_execution_native`, `head_reservation_authority`, `head_revocation`, `head_native_policy_readback`, `broker_execution`, and the broker branch of `ros_neck`;
  - their tests.

  The evidence plugin, physics fence, planning-scene colour and graceful shutdown stay.
- **Tooling.** New versions sit beside the old ones: freeze r10, qualify r7 and live r17. They forbid the deleted sources and libraries and allow the thin subclass. `test_b3_cleanup` is tightened to match.

## 6. 120 s hold criterion (finding 11; separate experiment, not acceptance)

- **Window.** The hold window runs on the sim clock, from the first `controller_state` stamp after the start command to the stop command. The expected number of updates is (end − start)/2 ms, computed and recorded.
- **Per controller.** All stamp deltas are exactly 2 ms, with no gaps or duplicates. The recorder is named: the ACT raw recorder, with topic-loss accounting.
- **Attribution.** `execution_time` and periodicity come from controller_manager introspection if 4.42.1 exposes them; the executor verifies this. If it does not, a 4 ms gap is reported as unattributed (skipped tick, dropped publish or transport).
- **Open problem.** The CP-HFP-1028 4 ms skip stays an open clock/CM investigation.

## 7. Order and acceptance

1. Write the shared constants module and the shadow stop window, then run the shadow comparison on the current stack (§3).
2. Write the subclass, with a RED test for each of its four duties: inputs closed, scaling ≠ 1 faults, wraparound off, NaN → ERROR, dead-man EOF and timeout latch.
3. Extend the guard, add the after-acceptance monitor, the graph check and the startup protocol v2. Version the audit.
4. Port the calibration line, then the import-graph test, then the deletions and the new tooling.
5. Gates: `so101_demo_py` ordinary pytest under grounded-sam, and colcon test and test-result for all packages. The target is 0 failures and 0 errors.
6. Sim negative tests (finding 13). Each must refuse at the intended boundary, which is the guard, the graph, the subclass or the window:
   - a foreign action client;
   - a `~/joint_trajectory` publisher;
   - a scaling publisher;
   - a goal sent inside the stop window;
   - the owner killed mid-goal, which must trigger the dead-man latch and hold.
7. Live, sequential, one stack at a time: the Head-search single case, seed 900000, must PASS under protocol v2; then one pick-place Teacher run must PASS, with VALID data and a passing readback.

## 8. Remaining regression, stated

- **Who may send goals.** Admission is a client-side guard plus a polled graph check. The subclass accepts any goal that passes its four duties, so a foreign client that appears between two graph polls could send one goal before the fault is raised. That goal is still bounded by the closed inputs, the dead-man and the after-acceptance monitor.
- **Checks no longer exact.** The per-tick geometry and lateness checks become approximated before dispatch or detected after the fact (§2 table).
- **Lost evidence.** The in-controller lossless timing record is gone; the 120 s evidence is topic-based (§6).

In simulation, with a single owner and a verified graph, this is acceptable. It is not equivalent on real hardware.
