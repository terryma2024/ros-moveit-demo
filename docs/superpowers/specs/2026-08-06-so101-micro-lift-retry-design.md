# SO-101 MICRO_LIFT Regrasp Retry Design

**Date:** 2026-08-06
**Status:** Proposed; written-spec approval is required before an implementation plan or code changes
**Reviewed worktree:** `/data/work/ws_moveit/.worktrees/refactor-optimization-r3`
**Reviewed branch/HEAD:** `codex/refactor-optimization-r3` at `37fb18677910505ca415de580513a7ad5def7090`
**Scope:** SO-101 physical-grasp probe only; Panda and `pick_place_common` behavior remain unchanged

## 1. Problem statement

The SO-101 physical-grasp probe can complete the commanded 2 mm world-Z TCP lift while the cup remains on the table. Fresh runtime evidence shows two distinct outcomes:

1. the cup still has at least one Gazebo gripper contact after the failed probe; or
2. the cup has no Gazebo gripper contact after the failed probe.

A single fixed close command does not recover either outcome. The required behavior is a bounded SO-101-only retry loop:

```text
open gripper
  -> descend TCP to the saved pre-MICRO_LIFT height
  -> close gripper
  -> wait for stable evidence
  -> MICRO_LIFT 2 mm
  -> validate cup/TCP following
```

If contact remains, the next reclose command reuses the current reclose target. If contact is absent, the next reclose target becomes 1.0 mrad tighter. After that reclose command, the existing fixed `q6_contact - 6.0 mrad` preload is still applied and held through MICRO_LIFT. The initial probe counts as attempt 1; no more than five total attempts are permitted.

## 2. Verified implementation constraints

- `MICRO_LIFT` currently commands a 2 mm displacement in the fixed world Z direction.
- `IWorldZMicroLift` and `MoveItJointPlanningBoundary::captureWorldZMicroLiftPlanningRequest` accept only positive deltas. A negative value cannot be used as an undocumented descend command.
- The calibrated nominal close target is `SO101Profile::q6_contact`.
- Lower q6 values close the SO-101 moving jaw more tightly.
- The existing transient seating action is bounded by `q6_regrasp_squeeze_offset = 0.0060` rad and `q6_safe_lower`.
- The current runtime holds that fixed 6.0 mrad preload through MICRO_LIFT and releases it only after Gazebo attachment becomes authoritative.
- Four contact-missing retries at 1.0 mrad each produce at most 4.0 mrad cumulative tightening, which remains inside both existing bounds.
- Physical-grasp samples already persist the before/after TCP pose, cup pose, contact fact, simulation session, and configuration fingerprint in the SO-101 sidecar.
- The current common runner has no generic representation for a robot-specific open/descend/reclose/probe sequence. Adding one would leak SO-101 grasp policy into Panda/common.

## 3. Goals

1. Retry only the observed failure mode in which the MICRO_LIFT motion succeeds but the cup does not follow it.
2. Reuse the current reclose target when cup/gripper contact remains.
3. Tighten only the reclose target by exactly 0.001 rad after each contact-missing failed attempt.
4. Cap the full operation at five total attempts: one initial attempt plus at most four retries.
5. Descend to the saved pre-lift TCP world-Z position before every regrasp, without cumulative Z drift.
6. Preserve the latest real physical-grasp failure and its metrics if all attempts fail.
7. Make cancellation, process interruption, checkpoint resume, and partial retry failure fail closed.
8. Keep Panda and common runtime behavior byte-for-byte equivalent apart from test/build dependency effects.

## 4. Non-goals

- No change to the current nominal gripper angle, fixed 6.0 mrad MICRO_LIFT preload, 2 mm lift distance, fixed-finger geometry, cup geometry, friction coefficients, physical-grasp thresholds, attachment policy, or existing pre-lift bilateral seating strategy.
- No force/torque-controlled grasping and no online optimization of q6.
- No retry for planning failure, execution failure, stale observation, unsafe motion, excessive XY slip, excessive cup tilt, inconsistent Gazebo/MoveIt attachment state, or a moved/unstable support object.
- No new common state, common runner retry directive, checkpoint schema change, or Panda retry behavior.
- No automatic continuation from the middle of a retry after a crash or process restart.
- No merge, push, root-workspace mutation, or `codex-cua` operation in this work.

## 5. Approaches considered

### A. SO-101 composite retry coordinator (selected)

Keep the public workflow states unchanged. The SO-101 physical-grasp verification action delegates failed-probe handling to a robot-local coordinator that owns the bounded sequence and returns one final success or failure to the common runner.

Advantages:

- keeps contact interpretation, q6 changes, micro-descend, and retry limits in SO-101;
- does not change Panda or common workflow semantics;
- preserves the existing external checkpoint state sequence;
- permits exact unit testing with fake gripper, observer, evidence store, and world-Z motion dependencies.

Trade-off:

- retry substeps are not common workflow states, so the SO-101 evidence sidecar must record attempt and phase for diagnostics and interruption safety.

### B. Add retry states and failure cycles to the common workflow

Add common states for regrasp open, micro-descend, reclose, and retry verification.

Rejected because it exposes a SO-101 friction-grasp strategy to Panda, expands run-to/plan-only/checkpoint state compatibility, and requires new cycle semantics in the common runner.

### C. Jump directly to one fixed tighter close target

Use the existing 6.0 mrad transient squeeze target on the first contact-missing result.

Rejected because it removes the bounded incremental search requested by the user and increases the risk of pushing or tilting the cup.

## 6. Retry eligibility

The coordinator evaluates eligibility only after all of the following have completed successfully for the current attempt:

1. the world-Z MICRO_LIFT plan and execution;
2. its existing motion validation/postcondition;
3. `WAIT_MICRO_LIFT_STABLE` and fresh after-lift evidence capture; and
4. `PhysicalGraspValidator::evaluate`.

An attempt is retryable only when every condition below is true:

- `attempt_index < 5`;
- the saved after-lift TCP Z is greater than its matching before-lift TCP Z;
- the cup failed to follow the TCP, expressed by table-clearance failure or follow-ratio failure, or by contact-missing combined with the same insufficient cup lift;
- XY displacement does not exceed the configured physical-grasp slip threshold;
- orientation change does not exceed the configured physical-grasp orientation threshold;
- Gazebo reports the cup detached;
- MoveIt reports the cup in the world and not attached;
- Gazebo and MoveIt cup poses remain mutually consistent;
- the cup and arm are stationary at the retry boundary;
- the simulation session and configuration fingerprint still match the current request.

The contact branch uses the aggregate fresh Gazebo cup/gripper contact fact from the after-lift sample:

- `gripper_contact == true`: preserve `current_reclose_target_q6` exactly;
- `gripper_contact == false`: set

```text
contact_missing_count += 1
current_reclose_target_q6 = max(
    q6_contact - contact_missing_count * 0.001,
    q6_contact - physical_grasp_max_tighten_q6,
    q6_contact - q6_regrasp_squeeze_offset,
    q6_safe_lower)
```

Because at most four retries exist, the selected reclose configuration reaches at most `q6_contact - 0.004`. A contact-present retry never resets a previously tightened target and never tightens it further. This dynamic reclose target is not the preload held during MICRO_LIFT: every attempt still uses the existing fixed `max(q6_safe_lower, q6_contact - q6_regrasp_squeeze_offset)` preload.

The coordinator must not use controller goal abort as a substitute for Gazebo contact evidence. A controller abort may accompany physical contact but does not prove cup contact.

## 7. Retry sequence

For each eligible retry, the coordinator performs exactly this sequence:

1. Persist `attempt_index`, `contact_missing_count`, `current_reclose_target_q6`, and phase `OPEN_PENDING`.
2. Command the existing SO-101 `PREOPEN` target and verify the normal gripper convergence contract.
3. Re-observe the world and compute `descend_delta_z = saved_before_lift_tcp_z - current_tcp_z`.
4. Require the delta to be finite, negative, no larger in magnitude than the configured 2 mm probe plus its existing endpoint tolerance, and targeted at the saved before-lift TCP Z.
5. Execute a collision-aware SO-101 world-Z micro-descend and verify the final TCP against that saved Z. The target is always the saved pre-lift Z, not `current_z - 0.002`, so retries cannot accumulate vertical drift.
6. Re-observe and revalidate detached/stationary/session/fingerprint preconditions.
7. Command `current_reclose_target_q6` and wait for convergence.
8. Run the unchanged pre-lift bilateral stabilization. It commands the same fixed `max(q6_safe_lower, q6_contact - q6_regrasp_squeeze_offset)` preload as the initial attempt, proves the same depth-bounded bilateral stable window, and holds that preload through MICRO_LIFT. It does not subtract the retry tightening from the preload.
9. Capture and atomically replace the before-lift evidence for this attempt.
10. Execute the existing positive 2 mm world-Z MICRO_LIFT while the fixed preload remains commanded.
11. Wait for stable after-lift evidence and atomically replace the after-lift sample.
12. Run the unchanged `PhysicalGraspValidator` thresholds.
13. On success, persist phase `COMPLETE`, return success, and allow `ATTACH_GAZEBO` to proceed.
14. On a retryable result with attempts remaining, return to step 1.
15. On a non-retryable result or attempt 5 failure, return failure without attachment.

The initial normal MICRO_LIFT is attempt 1. Retry sequences use attempt indices 2 through 5. No sixth lift, open, descend, or close command is allowed.

## 8. SO-101 interfaces and ownership

Add a SO-101-only `PhysicalGraspRetryCoordinator` with explicit dependencies:

- gripper command interface;
- collision-aware world-Z micro-lift/micro-descend interface;
- physical world observer;
- physical evidence store;
- unchanged physical-grasp validator and geometry;
- SO-101 profile and retry configuration.

Preserve the existing positive-only `IWorldZMicroLift::executeWorldZMicroLift` API. Add an explicitly named SO-101 micro-descend operation instead of passing a negative lift delta. Production lift and descend implementations may share a private signed world-Z planning helper, but their public validation remains direction-specific:

- lift: `0 < delta_z <= 0.002`;
- descend: `-0.002 - endpoint_tolerance <= delta_z < 0` and final target equals the recorded pre-lift Z within tolerance.

The micro-descend method must have cancellation semantics equivalent to MICRO_LIFT and must run through the same MoveIt planning scene, controller, collision, request-scoped cancellation, and endpoint validation boundaries.

No type, enum, transition, policy, or behavior is added to `pick_place_common`. No Panda source or runtime configuration is changed.

## 9. Evidence, checkpoint, and interruption semantics

The robot-local physical-grasp evidence schema is extended to record:

- total attempt index;
- contact-missing count;
- current q6 reclose target and fixed MICRO_LIFT preload target;
- retry phase;
- the before/after samples for the current attempt;
- the existing session ID and configuration fingerprint.

Every phase transition is written atomically before the next side effect. A fresh non-resume run resets retry metadata. A successful attempt records `COMPLETE`.

If the process exits or crashes during `OPEN_PENDING`, `DESCEND_PENDING`, `CLOSE_PENDING`, `LIFT_PENDING`, or `VERIFY_PENDING`, a later resume must not continue from the middle and must not replay an uncertain command. It returns a deterministic SO-101 postcondition failure such as `PHYSICAL_GRASP_RETRY_INTERRUPTED`, containing attempt, phase, and q6 metrics. Existing common checkpoint bytes, session identity, state ownership, and resume authorization remain unchanged.

An ordinary substep failure preserves its exact category, code, message, and metrics, augmented only with retry diagnostics. The coordinator calls the request-scoped cancel method owned by the failed substep and issues no later retry action.

When all five attempts fail physical verification, the final returned failure is the fifth attempt's original `PhysicalGraspValidator` failure. It is augmented with:

- `physical_grasp_attempts = 5`;
- `physical_grasp_retries = 4`;
- `contact_missing_count`;
- `final_reclose_target_q6`;
- `micro_lift_preload_target_q6`;
- `retry_exhausted = 1`.

The failure must then follow the already-approved SO-101 validation parking/recovery semantics. It must not be replaced by a generic retry-exhausted code.

## 10. Configuration

The initial implementation uses named SO-101 profile/configuration fields:

```text
physical_grasp_max_attempts = 5
physical_grasp_contact_missing_tighten_step_q6 = 0.001
physical_grasp_max_tighten_q6 = 0.004
micro_lift_world_z_delta_m = 0.002
```

Validation rejects non-finite values, attempts outside `[1, 5]`, non-positive tightening steps, a maximum tightening above `q6_regrasp_squeeze_offset`, or any resulting target below `q6_safe_lower`. Defaults preserve the approved values. These are SO-101 policy values and are not exposed as Panda/common launch arguments in this iteration.

## 11. Failure and safety semantics

- PREOPEN failure: cancel the gripper goal; preserve the gripper failure; stop.
- Micro-descend planning/validation failure: send no trajectory; preserve the planning failure; stop.
- Micro-descend execution/endpoint failure: cancel request-scoped motion; preserve the execution/postcondition failure; stop.
- Reclose or stabilization failure: cancel the gripper goal; preserve the exact failure; stop.
- MICRO_LIFT failure: use existing cancellation and failure diagnostics; do not regrasp.
- Stale/mismatched evidence: fail as observation/provenance error; do not regrasp.
- Cup attached on either Gazebo or MoveIt side: fail world consistency; do not open or descend.
- Unsafe XY/orientation change: preserve the physical failure; do not regrasp.
- Cancellation: no subsequent substep is dispatched after cancellation begins.

The coordinator never attaches the cup. Gazebo attachment remains possible only after final physical verification succeeds.

## 12. Test strategy

Implementation follows RED -> GREEN with deterministic fakes before live simulation.

### 12.1 Unit tests

1. Initial attempt succeeds: no PREOPEN, descend, extra close, or extra lift.
2. Failed lift with contact: retry sequence executes and reuses the exact current reclose q6 target.
3. Failed lift without contact: retry sequence tightens by exactly 0.001 rad.
4. Contact sequence `false, true, false, true`: reclose targets are `q6_contact-0.001`, `-0.001`, `-0.002`, `-0.002` relative to nominal, while all four MICRO_LIFT preload targets remain `q6_contact-0.006` subject only to `q6_safe_lower`.
5. Success on attempts 2, 3, 4, and 5 stops immediately with no later command.
6. Five failures produce exactly five lifts and four retry sequences; no sixth side effect occurs.
7. Exhaustion preserves the fifth physical failure code/message/metrics and adds retry metrics.
8. Contact missing without positive TCP lift is not retryable.
9. Excessive XY slip or orientation is not retryable even if cup lift is insufficient.
10. Attached, inconsistent, moving, stale, wrong-session, or wrong-fingerprint evidence is not retryable.
11. Each PREOPEN/descend/close/stability/lift/observation failure cancels the owned action and stops the sequence.
12. Descend targets the saved before-lift Z on every retry and never subtracts 2 mm cumulatively.
13. Tightening validation clamps below neither the 4.0 mrad configured cap nor existing q6 safety limits.
14. An interrupted sidecar phase fails closed on resume and dispatches no motion.
15. Panda workflow traces, actions, runner policy, and runtime tests remain unchanged.

### 12.2 Build and package tests

- Build `pick_place_common`, `panda_gazebo_demo`, and `so101_gazebo_demo` from the R3 worktree.
- Source only that worktree's `install/setup.bash`.
- Run all three package test suites and require zero failures and zero errors.
- Run focused SO-101 physical validator, evidence store, retry coordinator, MoveIt boundary, cancellation, checkpoint/resume, and workflow tests.
- Prove installed headers and binaries come from the R3 worktree overlay, not `/data/work/ws_moveit` root build/install.

### 12.3 Runtime and visual acceptance

Use one isolated SO-101 Gazebo/MoveIt stack with unique ROS domain and Gazebo partition. Do not start a second stack.

Required fresh cases:

1. baseline success without retry;
2. deterministic contact-present failed probe followed by same-q6 successful retry;
3. deterministic contact-missing failed probe followed by exactly 1.0 mrad tighter retry;
4. mixed contact sequence proving cumulative tightening occurs only on missing-contact attempts;
5. forced five-attempt exhaustion proving no sixth command and preservation of the final physical failure;
6. forced XY-slip/orientation/attached/observation failures proving no retry side effects;
7. cancellation and interrupted-sidecar resume proving fail-closed behavior;
8. at least five consecutive unforced end-to-end SO-101 pick runs using the approved current gripper strategy;
9. one fresh Panda end-to-end runtime regression.

For each retry attempt, retain timestamped evidence for:

- before/after TCP and cup poses;
- TCP and cup Z deltas and follow ratio;
- aggregate, fixed-finger, and moving-jaw contact facts when available;
- commanded and achieved q6;
- attempt/contact-missing counters and phase;
- Gazebo and MoveIt detached/attached facts;
- controller state, joints, TF, checkpoint/sidecar hashes, overlay provenance, and process ownership.

Capture fresh Gazebo screenshots for at least the contact-present retry, contact-missing tightened retry, final successful lift, and exhaustion case. A log-only pass is insufficient.

## 13. Acceptance rules

The work is accepted only if all of the following are independently verified:

1. The current nominal q6 close strategy and fixed 6.0 mrad MICRO_LIFT preload remain unchanged.
2. The initial lift is attempt 1 and the maximum is exactly five total attempts.
3. Every contact-present retry reuses the previous reclose target byte-for-byte.
4. Every contact-missing retry tightens only the reclose target by exactly 0.001 rad, cumulatively, with a maximum 0.004 rad change.
5. Every retry uses the unchanged fixed `q6_contact - q6_regrasp_squeeze_offset` MICRO_LIFT preload subject to `q6_safe_lower`; the dynamic reclose offset is never added to that preload.
6. Every retry descends to the matching saved pre-lift TCP Z with no cumulative drift.
7. Success stops the loop immediately and is the only path to Gazebo attachment.
8. Exhaustion issues no sixth side effect and preserves the fifth validator failure.
9. Non-retryable and substep failures issue no later retry action and retain exact failure provenance.
10. Interrupted retry phases fail closed and do not auto-resume motion.
11. Common and Panda code/behavior are unchanged.
12. Focused tests show RED before implementation and GREEN afterward.
13. All three package test suites report zero failures/errors.
14. Fresh SO-101 and Panda runtime/visual gates pass from the correct R3 overlay.
15. The final worktree contains only scoped intended changes, has scoped commits, and is clean; owned ROS/Gazebo/MoveIt processes are cleaned; nothing is pushed or merged; `codex-cua` is untouched.

## 14. Documentation impact

After implementation, update the SO-101 runtime/launch documentation to describe:

- five total attempts rather than five additional retries;
- the contact-present versus contact-missing reclose q6 rule and unchanged fixed MICRO_LIFT preload;
- the 1.0 mrad incremental and 4.0 mrad cumulative bounds;
- the exact retry sequence;
- non-retryable failures;
- final-failure preservation;
- sidecar interruption behavior and evidence locations.

No Panda launch parameter or common architecture documentation should claim this as generic behavior.
