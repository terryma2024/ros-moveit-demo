# Refactor Optimization R2 Design

## Status and baseline

This design is the independent follow-up review of `codex/refactor-optimization-r1` at
`644b9ba58fa244fab428be31d6036dbb03da38d3`, compared with merge-base and current
`origin/main` at `60bb4bf2ebb7006ba7f999ab3aaa19103900c218` on 2026-08-05.

R1 is accepted as its own scoped change: the fresh SO-101 plan-validation failure path skips
`RECOVER_RETREAT` only when the target was not executed, the arm is verified at safe home, and
Gazebo and MoveIt are canonically detached. It preserves the original
`TCP_ENDPOINT_OUTSIDE_TOLERANCE` failure. The R1 three-package gate reported 1149 tests, 0 errors,
0 failures, and 92 skipped, and fresh GUI evidence showed an unattached cup and safe-home SO-101.

R2 does not reopen those accepted semantics. It closes three contract gaps discovered after R1 and
adds one low-risk configuration hardening.

## Verified findings

### F1 — High: a later execute-resume can undo the accepted recovery skip

**Fact.** `pick_place_common/src/runner.cpp:324-332` calls
`IRecoveryPolicy::canSkipRecoveryAction` only inside `runExecuteWorkflow` when the request mode is
`PLAN_ONLY`. `runner.cpp:738-765` handles a recovery checkpoint resume by calling `select()` and
immediately running the selected action. It never applies the skip predicate.

**Fact.** `so101_gazebo_demo/src/pick_place/so101_recovery_policy.cpp:137-145` selects
`RECOVER_RETREAT` for a canonical detached world. The R1 runtime checkpoint remains resumable with
`phase=RECOVERY`, `next_state=RECOVER_RETREAT`, the original plan-validation failure, and
`plan_only_target_not_executed=1` after the fresh path correctly returns the original failure.

**Fact.** `so101_gazebo_demo/test/pick_place/test_pick_place_runner.cpp:1030-1050` currently asserts
that an execute recovery-resume from detached facts executes `RECOVER_RETREAT`. No runner-level test
distinguishes an ordinary execute failure from an unexecuted plan-only target.

**Inference.** If an operator explicitly resumes the R1 checkpoint with execute mode, the runner can
execute the retreat that R1 proved unnecessary. That can reintroduce unwanted motion and can replace
the original plan-validation result with a retreat failure.

### F2 — Medium: shared request validation accepts meaningless stop/failure states

**Fact.** `pick_place_common/src/run_request_validation.cpp:52-92` validates plan-only state
whitelisting but does not validate `stop_after` against `WorkflowDefinition::action_states`, nor
`fail_at` against forward action states.

**Fact.** `so101_gazebo_demo/src/pick_place/pick_place_state_machine.cpp:74-86` accepts every value
recognized by `stateFromString`, including terminal states. By contrast,
`panda_gazebo_demo/src/nodes/pick_place_state_machine_node.cpp:227-251,281-295` rejects terminal or
out-of-scope values before it calls the common validator.

**Runtime evidence.** The following command exited 0 and ran the full dry-run trace to `DONE`:

```bash
ros2 run so101_gazebo_demo pick_place_state_machine --mode dry_run --stop-after DONE
```

**Inference.** The two robot entry points expose different semantics for a shared control. More
importantly, an execute invocation that appears to specify a stopping boundary can silently execute
the complete workflow.

### F3 — Medium: policy pointer nullness is an undocumented robot selector

**Fact.** `IRunnerBehaviorPolicy` declares only retry-precondition, retry-postcondition, and
include-idle decisions (`pick_place_common/include/pick_place_common/runner.hpp:18-25`).

**Fact.** `pick_place_common/src/runner.cpp` also uses whether the pointer is null to choose execute
preflight (`:113`), forward observation recovery (`:480-483`), environment-precondition recovery
(`:509-519`), observation retry (`:566-568`), resume settling (`:710-724`), and original-failure or
transient-observation handling (`:794-796,869-871`). SO-101 supplies a policy; Panda supplies null.

**Fact.** `NoRetryRunnerBehaviorPolicy` (`runner.hpp:27-42`) is not referenced outside its
declaration, and supplying it would not reproduce the null baseline despite its name.

**Inference.** Adding a behavior policy to another robot, or replacing null with the existing
no-retry object, changes safety and failure semantics that are absent from the interface. This is an
abstraction leak, not merely dead code.

### F4 — Low: Panda safety tolerances use a fragile positional aggregate

**Fact.** `panda_gazebo_demo/src/nodes/pick_place_state_machine_node.cpp:479-484` initializes all
nine fields of `MotionPlanLimits` positionally. The current order matches
`motion_plan_evidence.hpp:58-69`, so this review found no current value-mapping defect.

**Recommendation.** Replace the aggregate with named assignments and add a characterization test.
This prevents a later insertion or reordering from silently assigning a safety threshold to the
wrong field.

## Duplication and dead-code conclusion

The review did not find another copied workflow, runner, or Gazebo/MoveIt executor algorithm that
should move into `pick_place_common`. The matching robot headers are aliases or thin adapters allowed
by `docs/pick-place-architecture.md:18-28`; robot checkpoint codecs and stores legitimately preserve
different provenance fields. `NoRetryRunnerBehaviorPolicy` is the only verified dead abstraction and
is resolved as part of F3.

## Approaches considered

### A. Recommended — make common decisions explicit and keep robot predicates local

Apply a common recovery-disposition check in both fresh and resume paths; centralize request-state
scope validation; expand or split the behavior-policy interface so every differing decision is named;
keep SO-101 safe-home/canonical-detach geometry inside `SO101RecoveryPolicy`.

This is the smallest approach that makes the public contracts truthful and prevents cross-robot
semantic drift. It adds no robot geometry or controller assumptions to common.

### B. Duplicate resume and CLI guards in each robot

This is initially smaller but preserves the inconsistency that caused F1 and F2. New robot consumers
would have to rediscover the same rules. Rejected.

### C. Move complete SO-101 recovery classification into common

This would make the runner simpler but incorrectly genericizes SO-101 joint-6, safe-home, table-pose,
and gripper tolerances. Rejected because these are robot policy, not workflow mechanics.

## Target architecture and boundaries

### Common core owns

- Applying a policy-selected recovery disposition consistently in fresh and resume execution.
- Request-shape and state-scope validation using `WorkflowDefinition`.
- Explicit runner behavior decisions and their default behavior.
- Stable configuration failure codes and common unit/integration tests.
- Checkpoint/session/original-failure preservation mechanics.

### Robot packages own

- Whether a particular recovery action may be skipped for the current robot and world snapshot.
- SO-101 safe-home, joint-6, canonical table/object, attachment, and gripper predicates.
- Panda and SO-101 launch/CLI parsing and user-facing error logging.
- Motion evidence, controller adapters, geometry, and checkpoint JSON/provenance codecs.

### Required data flow

For recovery resume, common loads and validates the checkpoint and current snapshot, asks the robot
policy to select the current recovery route, then asks the same policy whether that selected action is
unnecessary. A skip returns `ERROR` with the unchanged original failure and executes no state action.
All negative conditions continue into the selected recovery action or return the existing validation
failure.

For request validation, parsers convert strings to `State`; common validates mode combinations and
state membership. `stop_after` must name an action state. `fail_at` must name a forward action and is
valid only in dry-run. Robot parsers may provide friendly syntax errors but may not define a different
semantic scope.

## Compatibility and failure semantics

- No launch argument or CLI spelling changes.
- Existing valid `stop_after`, `fail_at`, `plan_only_state`, resume, checkpoint, and session requests
  remain valid.
- Newly rejected requests receive stable codes: `STOP_AFTER_STATE_NOT_ACTION` and
  `FAIL_AT_STATE_NOT_FORWARD_ACTION`.
- Plan-only whitelist and run-to-target behavior remain unchanged: predecessors execute, the target is
  planned and validated only, and the target is not executed.
- F1 applies only when the robot policy returns true for the complete R1 predicate. It must not skip
  for execute-origin failures, an executed target, unsafe/non-home robot state, stale observations,
  unknown or attached object state, noncanonical Gazebo/MoveIt state, or any recovery action other
  than the selected action.
- A skipped recovery resume returns the byte-equivalent original failure category/code/message/metrics
  in the `RunResult`; it does not wrap or replace it.
- No additional checkpoint write, sequence increment, session-ID change, plan, controller command,
  Gazebo attach/detach, or MoveIt scene mutation occurs on a skip.
- Panda behavior remains equivalent to its pre-R2 null-policy baseline.

## Migration

1. Add failing common and SO-101 tests for recovery resume, invalid request scopes, and policy baseline
   equivalence.
2. Make recovery skip evaluation mode-independent at the common recovery routing boundary.
3. Move semantic state-scope validation into `validateRunRequest`; align both entry points with its
   stable failures.
4. Replace pointer-presence branches with explicit decisions. Keep current Panda and SO-101 outcomes
   as named defaults/overrides.
5. Remove `NoRetryRunnerBehaviorPolicy` if the explicit default object supersedes it; otherwise rename
   and test it as the exact baseline.
6. Replace the Panda positional aggregate with named field assignments.
7. Update launch parameter documentation and architecture policy documentation.

## Risks and controls

- **Unexpected robot motion:** test executor call counts and joint/TCP snapshots before runtime; run
  only in the isolated ai-station worktree and verified overlay.
- **Over-broad skip:** require all R1 positive predicates and add one negative test for every predicate.
- **Panda behavior change:** characterization tests compare null/default policy results for preflight,
  recovery, settling, and failure wrapping before deleting null branches.
- **Checkpoint drift:** compare checkpoint bytes and session ID before and after a skipped resume.
- **Environment collision:** identify ROS/Gazebo/MoveIt PIDs before cleanup; do not touch non-ROS
  processes, other worktrees, `codex-cua`, or unrelated sampler jobs.

## Acceptance rules

R2 is accepted only when all conditions below are evidenced.

1. RED evidence exists for each F1-F4 test before implementation; the same tests are GREEN afterward.
2. A recovery checkpoint with plan-validation category, target-not-executed metric, safe-home robot,
   canonical detached Gazebo/MoveIt state, and selected `RECOVER_RETREAT` resumes without invoking a
   planner or executor and returns the exact original failure.
3. Every negative F1 predicate proves the skip is not applied. At minimum: non-plan-validation,
   missing/zero metric, non-home, moving arm, stale snapshot, unknown/attached Gazebo, unknown/attached
   MoveIt, noncanonical object/table, closed/nonstationary gripper, and a different recovery action.
4. The skipped resume leaves checkpoint bytes, checkpoint sequence, simulation session ID, robot joint
   state, TCP pose, Gazebo object pose/attachment, MoveIt world/attachment, controllers, and TF
   unchanged within existing project tolerances.
5. Both robot entry points reject `stop_after=IDLE|DONE|ERROR` and out-of-workflow states with
   `STOP_AFTER_STATE_NOT_ACTION`; both reject terminal/recovery `fail_at` with
   `FAIL_AT_STATE_NOT_FORWARD_ACTION`. Valid action controls remain accepted.
6. Supplying the explicit default runner policy produces the same results as the old Panda null
   baseline for preflight, observation failures, environment preconditions, resume settling, and
   original-failure preservation. SO-101 retry and trace behavior remains unchanged.
7. Panda `MotionPlanLimits` launch values map to all nine named fields, and default-value tests pass.
8. `pick_place_common`, `panda_gazebo_demo`, and `so101_gazebo_demo` build and test with 0 failures and
   0 errors using the worktree overlay.
9. Fresh SO-101 failure injection and explicit recovery-resume both have runtime logs plus fresh GUI
   evidence. Visual and queried Gazebo/MoveIt/controller/joint/TF state must agree.
10. The final diff is scoped, the worktree is clean after a local commit, all owned/conflicting ROS
    processes are cleaned, and nothing is pushed, merged, or sent to `codex-cua` without a later user
    approval.
