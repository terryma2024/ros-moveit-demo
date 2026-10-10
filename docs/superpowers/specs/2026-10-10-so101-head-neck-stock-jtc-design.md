# SO-101 Head neck on stock JTC: retire the broker-owned controller

Status: design, 2026-10-10. Owner: root (Claude Opus 5.5). Execution: one Claude Sonnet 5.5 executor. Ledger: `docs/experiments/so101-act-data-experiment-ledger.md` CP-3530, CP-3534.

## 1. Goal and user decisions

**Goal.** The Head neck, and the arm and gripper in the Head stack, use the stock `joint_trajectory_controller/JointTrajectoryController` (Jazzy 4.42.1). The ACT/Teacher already uses it. Once nothing loads them, these are deleted:

- `so101_mujoco_support/BrokerOwnedTrajectoryController`
- the SOGB v2 reservation protocol
- the stop and ingress witnesses
- the native revocation transport

**User decisions.**

- CP-3530: refactor after both live tasks pass. Both passed: CP-3532 and CP-3533.
- 2026-10-10 answers:
  1. **Safety checks.** The Head-mode real-time checks move to the Python pre-dispatch side.
  2. **Calibration line.** The Head calibration and qualification line is ported, not removed.

## 2. What exists today (research 2026-10-10)

- **Where the broker type is selected.** The in-tree ACT `ros2_controllers.yaml` is already stock for arm, gripper and neck. Only the Head inputs file `ros2-controllers-file-v1.yaml` selects the broker type, for all three controllers. The neck block adds `head_simulation_mode`, `head_fault_connection_timeout_ns`, `head_measured_prefix_guard` and `speed_scaling_input_enabled`. That file has no in-tree generator.
- **How the Head runtime uses the broker on a functional case:**
  - **Admission.** It reserves every neck goal over SOGB v2 (`head_inventory_dispatch.py:219`).
  - **Startup.** It reads the 80-byte prearm/ARM stop-witness proof at startup: 51 samples at 2 ms, velocity ≤ 0.002 rad/s (`head_local_runtime._arm_once`).
  - **Native close.** It closes natively through `libso101_head_revocation_transport` after the raw stop.
  - **Raw stop.** It already proves the raw stop from `/joint_states`: 3 advancing samples within the stop velocity (`RosControllerPort.stopped`, `OrderedStopConfirmation`).
  - **Verdict.** The functional verdict `stop_confirmed` ANDs the native close ACK with the raw stop.
- **Head-mode checks in the broker's `update()`:**
  - goal shape: 2 points, duration 0.1–5 s, peak velocity and acceleration;
  - the measured-prefix envelope (`validate_head_prefix`);
  - hold on fault or NaN;
  - the revocation latch;
  - single-owner admission.
- **120 s nominal hold.** It reads the controllers' `SOTM0001` per-update streams. Those streams carry the `period` passed to `update`, the body duration, `update_id`, the sim stamp and loss counters. The open 4 ms skip (CP-HFP-1028) is a controller-manager/clock issue, not a broker one.
- **The ACT side.** It already records `/<c>/controller_state` on a 2 ms grid with continuity accounting (`act/offline/scan.py`, `native_endpoints.validate_reference_continuity`). The p12 run had 0 gaps.

## 3. Design

### 3.1 Controllers

- **Controller types.** The Head stack's controllers file becomes the in-tree ACT `ros2_controllers.yaml`, with all three controllers stock. Head needs no extra keys. Keep `allow_partial_joints_goal: false` and `allow_integration_in_goal_trajectories: false` only if stock behaviour needs them, and verify each against the 4.42.1 parameter list.
- **Generator.** Add a generator in-tree (`act/head_controllers_file.py`) so that the Head inputs file is derived from source, not copied from a bundle. It is bound by sha256 into the Head inputs.

### 3.2 Admission and safety, on the Python pre-dispatch side (user decision 1)

- **Head dispatch guard.** `head_trajectory_guard.py` gains a `HeadDispatchGuard`. It runs before every neck `send_goal` and refuses with a named code. It enforces exactly the broker's head-mode limits, with the values read from the same frozen policy that the broker read:
  - 2-point shape;
  - duration in [0.1, 5] s;
  - peak velocity and acceleration limits;
  - the measured-prefix envelope (`quintic_measured_prefix_v1`) against the latest `/joint_states`.
- **Single sender.** The only neck sender is the Head runtime's own `ActionClient`. A graph check at startup and at stop requires exactly one action client on `/neck_controller/follow_joint_trajectory`, and that it is this process. This replaces single-owner admission.
- **Fault and NaN hold.** A non-finite `/joint_states` sample, or a guard refusal mid-search, cancels the active goal and runs the raw-stop proof. Stock JTC holds position when it has no active goal.
- **Revocation latch.** It becomes a per-run Python latch. Once it is set, no further goal is sent in that run.

### 3.3 Stop proof

- **Startup proof (replaces prearm/ARM).** Before the first goal, the neck must show 51 consecutive `/neck_controller/controller_state` samples on the 2 ms sim-stamp grid, with |feedback velocity| ≤ 0.002 rad/s and |reference velocity| ≤ 0.002 rad/s. These are the same constants as `controller_stop_witness.hpp:26-29`, now read from a Python constant module that is shared with the tests.
- **End of a case (replaces the native close ACK).**
  1. The goal reaches a terminal result, or is cancelled.
  2. Then the existing raw `/joint_states` stop proof (3 advancing samples).
  3. Then the same 51-sample `controller_state` window.
- **Verdict.** The functional verdict `stop_confirmed` = terminal result AND raw stop AND the 51-sample window.
- **Event log.** The run log replaces the `NATIVE_CLOSE` event with `STOCK_STOP_PROOF`, which carries the stamps of the window. `head_run_audit` HFA-009 and the retirement receipt change to match.

### 3.4 Calibration and qualification line (user decision 2: port)

- **Ported modules.** `head_search_restarts.py`, `head_search_stop_measurement.py`, `measure-restarts` and `qualify` are ported to the §3.3 evidence:
  - The restart owner no longer provisions a reservation; it uses the §3.2 guard and the single-sender check.
  - Stop measurement reads `controller_state` and `/joint_states` instead of the witness constants from the installed header.
- **Shared helpers.** Helpers that do not depend on reservations (`RestartRefused`, `stop_proof`) move to a small shared module first.
- **120 s hold criterion (new checkpoint, not a rewrite of old evidence).** Per controller:
  - at least 60,000 `controller_state` stamps inside the hold window;
  - consecutive stamp deltas exactly 2 ms;
  - no gap or duplicate;
  - topic-loss accounting as in `topic_loss_v2`;
  - the §3.3 stop window at the end.
- **Dropped from the old criterion.** The per-update `period` value, the body duration (< 2 ms) and the native close ACK. With stock JTC, a skipped controller tick shows as a 4 ms stamp gap.
- **What the criterion does not fix.** It neither hides nor fixes the open CP-HFP-1028 4 ms skip, which remains a clock/CM investigation.

### 3.5 Deletions

These are deleted once nothing imports them, as proven by the static import graph and a grep for every name:

- **C++ in `so101_mujoco_support`.** The controller, the plugin XML, goal admission and its types, bound reservation, sha256, role, the reservation protocol, provision and socket, the stop and ingress witnesses, stop evaluation, the stop-timing collector, the head revocation transport, their CMake targets and install rules, and their about 146 gtests. The evidence plugin, physics fence, planning-scene colour and graceful shutdown stay.
- **Python.** `controller_reservation_client/provision`, `so101_teleop.unified.controller_reservation_paths`, `head_execution_native`, `head_reservation_authority`, `head_revocation`, `head_native_policy_readback`, `broker_execution`, the broker branch of `ros_neck`, and the reservation parts of `head_control_protocol`. Each module's tests are deleted with it.
- **Tests that are rewritten instead.** The Head runtime, dispatch, provider, runner, event log, run audit, functional campaign, simulation policy, startup binding and neck port tests are rewritten to the new admission and stop proof. `test_b3_cleanup` becomes stricter: the broker controller and reservation sources must be absent.
- **Tooling.** New versions sit next to r9/r6/r16: freeze r10, qualify r7, live r17. They forbid the broker controller, its plugin XML, the reservation sources and the revocation transport library. The Teacher cycle and live scripts are unaffected. The Head nominal harness `maps` check names the stock JTC library.
- **Existing evidence.** The Head ledger, its sealed runs and the CP-3532 case refer to broker artefacts. They are not rewritten.

## 4. Order and acceptance

1. **Shared helpers.** Move them out of the calibration modules (no behaviour change).
2. **Guard and proofs.** Add the §3.2 guard, the single-sender check and the §3.3 proofs. Use RED → GREEN for each limit and for each refusal code.
3. **Runtime switch.** Switch the Head runtime to stock JTC and the generated controllers file. Then port the calibration line.
4. **Deletions.** Delete per §3.5. Tighten `test_b3_cleanup` and cut the new tooling versions.
5. **Gates.** Run the full gates: `so101_demo_py` ordinary pytest under grounded-sam, and colcon test plus test-result for all packages. The target is 0 failures and 0 errors.
6. **Live, sequential, one stack at a time:**
   - the Head-search single case, seed 900000: PASS with the CP-3532 criteria, except that `stop_confirmed` follows §3.3;
   - one pick-place Teacher run: PASS, VALID and readback PASS.
7. **Not in acceptance.** A new 120 s hold run is a separate experiment under the §3.4 criterion. It is expected to still show the CP-HFP-1028 skip until the clock investigation resumes.

## 5. Risks

- **Weaker admission.** Admission becomes a client-side guard plus a graph check, not an in-RT refusal. Any other process on the graph could still send goals. In sim with a single owner and a verified graph this is acceptable, but on real hardware it is not equivalent.
- **Less precise evidence.** `controller_state` publication can drop under load. Topic-loss accounting makes a drop visible, but it is no longer a lossless in-controller record.
- **Calibration scope.** Porting the calibration line is the largest part of the work. If a piece cannot be ported without inventing evidence, it stops and is reported.
