# Complete Panda Pick-Place State Machine Design

**Status:** Approved on 2026-07-23

## 1. Goal and scope

Complete the fixed-space Panda simulation state machine from `CLOSE_GRIPPER` through `DONE`, including every normal executor, motion planner, plan validator, transition contract, checkpoint boundary, and automatic recovery action.

The implementation preserves the current uncommitted `DESCEND` work and the committed `FixedPickPlaceTargetPolicy`. It does not add perception, an Agent, SO-ARM101 support, navigation, or a generic behavior-tree framework.

## 2. Fixed targets

All fixed targets belong to `FixedPickPlaceTargetPolicy` and its configuration signature. No planner or validator may duplicate a target literal.

| Semantic target | TCP pose in world |
| --- | --- |
| `above_pick` | position `(0.30, 0.00, 0.987)`, quaternion `(1, 0, 0, 0)` |
| `pick` | position `(0.30, 0.00, 0.870)`, quaternion `(1, 0, 0, 0)` |
| `above_place` | position `(0.30, 0.20, 0.987)`, quaternion `(1, 0, 0, 0)` |
| `place` | position `(0.30, 0.20, 0.870)`, quaternion `(1, 0, 0, 0)` |

The expected final Coke centre is approximately `(0.30, 0.20, 0.836)`. Recovery safe-height targets retain the observed TCP `x/y` and raise `z` to at least `0.987`. Recovery return-to-pick uses the fixed `above_pick` and `pick` targets.

The pick/place TCP height is derived from the simulated Panda finger collision geometry. With
`panda_tcp` at hand-local `z=0.1034`, the finger collision boxes span world
`[target_z-0.00885, target_z+0.04487]` in the downward grasp orientation. At the former
`target_z=0.930` they ended 24 mm above the Coke top (`z=0.897`), so the gripper closed empty.
`target_z=0.870` gives 36 mm of vertical overlap and was verified in Gazebo by a symmetric
contact-stalled grasp at approximately `0.0308 m` per finger without moving the Coke outside
tolerance.

## 3. Architectural rules

1. One state produces one independently observable side effect.
2. API acceptance is not sufficient evidence of completion.
3. A forward state follows `observe → pre-validate → plan → plan-validate → execute → observe → post-validate → checkpoint`.
4. A state with a registered planner must have a registered `IPlanValidator`; absence is a configuration error.
5. Missing executors and transition contracts fail closed.
6. Motion recovery always starts from the observed stopped robot state, never from a planned endpoint.
7. Gazebo is authoritative for physical Coke pose and physical attachment. MoveIt is authoritative for collision-world membership and attached collision objects.
8. Recovery routing uses stopped-world facts, not only the failed state name.
9. Primary business actions are not automatically retried. Adapters may poll an already-issued asynchronous operation until it converges or times out.
10. Every recovery action is idempotent and is attempted at most once per recovery pass. A recovery action failure terminates in `ERROR`.

## 4. Component boundaries

### 4.1 Pure state-machine core

- `StateMachineRunner`
- `TransitionTable`
- `StateActionRegistry`
- `PlanValidatorRegistry`
- `TransitionContractRegistry`
- `IRecoveryPolicy`
- `ICheckpointStore`

The core remains independent of ROS, MoveIt, and Gazebo message types.

### 4.2 State-level components

Each forward or recovery state has a thin state-level component that declares the allowed state and delegates to a reusable adapter:

- gripper: close, normal open, recovery open;
- Gazebo: attach, detach, recovery detach;
- MoveIt: attach, detach, recovery detach;
- motion: lift, move above place, descend to place, retreat, and the three carrying-recovery motions;
- Planning Scene: normal and recovery world-object synchronization.

### 4.3 Reusable adapters

- `MoveItMotionAdapter`: pose planning, Cartesian planning, trajectory execution, cancellation, FK evidence, and current state.
- `GripperCommandAdapter`: action goal, result, cancellation acknowledgement, and timeout handling.
- `GazeboAttachmentAdapter`: publish attach/detach commands and wait for `/panda/coke_attached`
  convergence. Gazebo Sim 8 DetachableJoint publishes event-driven `gz.msgs.StringMsg` values on
  `/panda/coke_attached_event`. A launch-lifetime relay validates `attached` / `detached`, retains
  the latest fact, and periodically publishes it on `/panda/coke_attached`, so a resumed process
  observes physical state instead of guessing from configuration. The local Gazebo Sim 8 plugin
  binary does not implement the `initially_detached` SDF tag and starts attached; the relay keeps
  state unknown, requests one initial detach after the first raw `attached`, and publishes nothing
  until raw `detached` confirms the safe state.
- `GazeboWorldObserver`: treats `max_observation_age_seconds` as both the maximum accepted sample
  age and the bounded startup wait for the first Coke-pose and durable attachment-state messages;
  it still fails closed when either fact is absent at the deadline. Pose and attachment samples
  have independent receive timestamps; a relay state that is present but older than the same
  bound fails as `GAZEBO_ATTACHMENT_STATE_UNAVAILABLE`.
- `MoveItAttachmentAdapter`: attach/detach and wait for Planning Scene membership convergence.
- `PlanningSceneSyncAdapter`: apply the Gazebo-authoritative Coke 6D pose to the MoveIt world object and verify it.
- `PickPlaceTargetPolicy`: the single target source.

### 4.4 Execution context

Replace the executor's state-only input with a context that includes the verified pre-action world:

```cpp
struct ExecutionContext
{
  State state;
  State next_state;
  WorldSnapshot before;
  std::shared_ptr<const PlanArtifact> plan;
};
```

`IStateExecutor::execute(const ExecutionContext &)` lets synchronization, continuity checks, and idempotent recovery use the same pre-action facts that the Runner validated.

### 4.5 Plan validation

`PlanValidatorRegistry` is keyed by `State`. Motion artifacts expose generic evidence:

- trajectory point count and valid timing;
- planned start joint state;
- planned TCP path and final 6D pose;
- Cartesian fraction when applicable;
- adjacent joint deltas;
- collision-aware planning result;
- carried-object relative-pose and clearance evidence when applicable.

Separate validators cover pose motion, empty-gripper Cartesian motion, and carried-object motion.

## 5. Normal state graph

```text
IDLE
→ PREPARE_OPEN_GRIPPER
→ MOVE_ABOVE_OBJECT
→ DESCEND
→ CLOSE_GRIPPER
→ ATTACH_GAZEBO
→ ATTACH_MOVEIT
→ LIFT
→ MOVE_ABOVE_PLACE
→ DESCEND_TO_PLACE
→ OPEN_GRIPPER
→ DETACH_GAZEBO
→ DETACH_MOVEIT
→ SYNC_WORLD_OBJECT
→ RETREAT
→ DONE
```

The release order is intentionally `OPEN_GRIPPER → DETACH_GAZEBO → DETACH_MOVEIT → SYNC_WORLD_OBJECT`. Gazebo keeps Coke fixed while the fingers open; physical detach occurs only after safe opening.

## 6. Normal execution contracts

### 6.1 `CLOSE_GRIPPER → ATTACH_GAZEBO`

- Action: send `GripperCommand` with `gripper_close_position=0.0`.
- Preconditions: TCP at `pick`; arm stationary; Coke stable; both attachment models detached.
- Success: action succeeds; both finger joints are finite, symmetric, stopped, and inside the Coke grasp range; Coke 6D pose stays within drift tolerance.
- Failure entry: `RECOVER_OPEN_GRIPPER`.

Contact stopping is expected. Success does not require an empty gripper to reach zero position.

### 6.2 `ATTACH_GAZEBO → ATTACH_MOVEIT`

- Action: publish `gz.msgs.Empty` on `/panda/attach_coke` and wait for
  `/panda/coke_attached="attached"`.
- Preconditions: valid grasp; both models detached; arm and Coke stationary.
- Success: Gazebo attached, MoveIt detached, Coke world pose does not snap, and `TCP→Coke` relative pose is continuous.
- Failure entry: recovery policy, normally `RECOVER_OPEN_GRIPPER`.

### 6.3 `ATTACH_MOVEIT → LIFT`

- Action: `attachObject("coke", "panda_hand", touch_links)` and poll Planning Scene convergence.
- Preconditions: Gazebo attached; MoveIt Coke exists only in world; arm stationary.
- Success: Coke is absent from MoveIt world and present exactly once as an attached object; attached link is `panda_hand`; touch links contain `panda_hand`, `panda_leftfinger`, and `panda_rightfinger`; both models report attached; relative pose stays continuous.
- Failure entry: recovery policy, normally `RECOVER_OPEN_GRIPPER`.

### 6.4 `LIFT → MOVE_ABOVE_PLACE`

- Action: collision-aware Cartesian motion from `pick` to `above_pick` along world `+Z`.
- Preconditions: gripper closed, both models attached, TCP at `pick`.
- Plan gates: finite fraction at least `0.99`, nonempty timed trajectory, joint jumps at most `0.2 rad`, no lateral/rising-direction violation, valid FK, final 6D target tolerance.
- Success: actual TCP reaches `above_pick` and stops; Coke follows TCP; `TCP→Coke` relative pose remains within tolerance; both models remain attached.
- Failure entry: carrying recovery.

### 6.5 `MOVE_ABOVE_PLACE → DESCEND_TO_PLACE`

- Action: collision-aware pose planning to `above_place`, with attached Coke in the collision model.
- Preconditions: safe transport height, gripper closed, both models attached.
- Plan gates: nonempty timed collision-aware trajectory, valid start state, final 6D target tolerance, attached-object evidence present.
- Success: actual TCP reaches `above_place` and stops; Coke and TCP motion agree; relative pose and attachments remain stable.
- Failure entry: carrying recovery.

### 6.6 `DESCEND_TO_PLACE → OPEN_GRIPPER`

- Action: collision-aware Cartesian descent to `place`.
- Preconditions: TCP at `above_place`, gripper closed, both models attached.
- Plan gates: the same Cartesian completeness, joint-jump, vertical-path, orientation, timing, and endpoint gates used by `DESCEND`, plus attached-object evidence.
- Success: actual TCP reaches `place` and stops; Coke reaches the supported placement height without lateral drift; relative pose and attachments remain stable.
- Failure entry: carrying recovery.

### 6.7 `OPEN_GRIPPER → DETACH_GAZEBO`

- Action: send the open GripperCommand.
- Preconditions: TCP at `place`, both models attached, robot stationary.
- Success: both fingers reach the safe-open range and stop; both models still report attached; Coke stays fixed by the Gazebo joint.
- Failure entry: `RECOVER_OPEN_GRIPPER` at the place location.

### 6.8 `DETACH_GAZEBO → DETACH_MOVEIT`

- Action: publish `/panda/detach_coke` and wait for `coke_attached="detached"`.
- Preconditions: gripper open, both models attached, Coke in the place region.
- Success: Gazebo detached and MoveIt still attached; sampled Gazebo poses show Coke settled on the table without unacceptable translation or tilt.
- Failure entry: `RECOVER_DETACH_GAZEBO`.

### 6.9 `DETACH_MOVEIT → SYNC_WORLD_OBJECT`

- Action: `detachObject("coke")` and poll Planning Scene convergence.
- Preconditions: Gazebo detached and Coke settled; MoveIt attached.
- Success: MoveIt attached object disappears, Coke returns to the world object set, and both models report detached. Cross-world pose equality is intentionally deferred to synchronization.
- Failure entry: `RECOVER_DETACH_MOVEIT`.

### 6.10 `SYNC_WORLD_OBJECT → RETREAT`

- Action: apply the observed Gazebo Coke 6D pose to the MoveIt world object.
- Preconditions: both models detached; Gazebo Coke settled; Coke exists in MoveIt world.
- Success: Gazebo and MoveIt Coke poses match within tolerance; Coke and table exist in MoveIt world; no attached Coke remains.
- Failure entry: `RECOVER_SYNC_WORLD_OBJECT`.

### 6.11 `RETREAT → DONE`

- Action: empty-gripper Cartesian motion from `place` to `above_place` along world `+Z`.
- Preconditions: gripper open, both models detached, cross-world pose synchronized.
- Plan gates: complete, timed, collision-safe vertical retreat from the observed actual state.
- Success: TCP reaches `above_place` and stops; Coke remains stable; final gripper and attachment invariants hold.
- Failure entry: `RECOVER_RETREAT`.

### 6.12 `DONE`

`DONE` has no executor. Entry requires gripper open, both models detached, safe TCP, stable Coke in the fixed place region, and Gazebo/MoveIt pose consistency.

## 7. Fact-driven recovery

After a forward failure, Runner cancels the active operation, waits for all robot joints to become stationary, observes a fresh world snapshot, and asks `IRecoveryPolicy` for a route.

| Observed facts | Recovery entry |
| --- | --- |
| both attached below safe height, with Coke following TCP | `RECOVER_LIFT_TO_SAFE_HEIGHT` |
| both attached at/above safe height but not at `above_pick` | `RECOVER_MOVE_ABOVE_PICK` |
| both attached at `above_pick` 6DoF with Coke following TCP | `RECOVER_DESCEND_TO_PICK` |
| both attached and TCP plus Gazebo Coke are in the same pick/place 6DoF support region, gripper closed | `RECOVER_OPEN_GRIPPER` |
| both attached at support with gripper safely open | `RECOVER_DETACH_GAZEBO` |
| Gazebo attached only at support | closed: `RECOVER_OPEN_GRIPPER`; open: `RECOVER_DETACH_GAZEBO` |
| MoveIt attached only at support | closed: `RECOVER_OPEN_GRIPPER`; open: `RECOVER_DETACH_MOVEIT` |
| either partial-attachment case without positive support evidence | fail closed without releasing Coke |
| both detached, gripper not safely open | `RECOVER_OPEN_GRIPPER` |
| both detached/open but Gazebo and MoveIt Coke 6DoF differ | `RECOVER_SYNC_WORLD_OBJECT` |
| both detached/open/synchronized | `RECOVER_RETREAT` (including its safe-height no-op) |
| missing required facts, stale observation, moving Coke, or robot not stopped | terminal `ERROR` without another side effect |

The original business failure is retained throughout recovery.

For deterministic cross-process verification, `stop_after` accepts any
non-terminal forward or recovery action and writes the ordinary validated
checkpoint after that action. `IDLE`, `DONE`, and `ERROR` are not valid
`stop_after` values. This control changes only where a run returns to the
caller; it does not bypass planning, execution, contracts, observation, or
checkpoint persistence.

This table is evaluated from fresh facts both at initial failure and on every recovery checkpoint
resume. The persisted recovery state is only a hint: already completed physical side effects advance
the selected entry point, so process restart cannot repeatedly re-enter the first recovery action.

Forward runtime failures after static coverage is established—including precondition, observation,
planner, plan-validation, execution, post-validation, and checkpoint persistence failures—use the
same stop/cancel, stationary observation, fact classification, and recovery workflow. Missing
executor, transition contract, or plan validator remains a configuration error and never executes.

## 8. Recovery state graph and contracts

```text
RECOVER_LIFT_TO_SAFE_HEIGHT
→ RECOVER_MOVE_ABOVE_PICK
→ RECOVER_DESCEND_TO_PICK
→ RECOVER_OPEN_GRIPPER
→ RECOVER_DETACH_GAZEBO
→ RECOVER_DETACH_MOVEIT
→ RECOVER_SYNC_WORLD_OBJECT
→ RECOVER_RETREAT
→ ERROR
```

Routes may enter at any cleanup state selected by observed facts. Recovery motion never releases Coke in the air.

### 8.1 Carrying recovery

- `RECOVER_LIFT_TO_SAFE_HEIGHT`: Cartesian `+Z` from actual TCP `x/y` to at least `z=0.987`; no-op if already at its 6D target. Both attachments and relative pose must remain stable.
- `RECOVER_MOVE_ABOVE_PICK`: collision-aware carried-object pose motion to `above_pick`; no-op if already at its 6D target.
- `RECOVER_DESCEND_TO_PICK`: carried-object Cartesian descent to `pick`; no-op if already at its 6D target; Coke must return to the original support region.

### 8.2 Release cleanup

- `RECOVER_OPEN_GRIPPER`: no-op if safely open, otherwise issue one open command. If Gazebo is attached, Coke must stay fixed; otherwise it must remain stable on the table.
- `RECOVER_DETACH_GAZEBO`: no-op if detached, otherwise issue one detach command and wait for physical detachment and settling.
- `RECOVER_DETACH_MOVEIT`: no-op if detached, otherwise detach and wait until Coke is in MoveIt world.
- `RECOVER_SYNC_WORLD_OBJECT`: idempotently copy Gazebo Coke pose into MoveIt and verify cross-world equality.
- `RECOVER_RETREAT`: Cartesian `+Z` from the actual TCP location to safe height; no-op if already safe. It requires open fingers, both models detached, synchronized world state, and stable Coke.

All recovery-motion no-ops require a fresh, stationary observation at the policy-provided 6D
target. They still pass through plan validation, execute-time target revalidation, observation,
the normal transition post-contract, and checkpoint commit. Forward motions never use this
shortcut, and a zero-duration MoveIt trajectory is never accepted as a substitute.

A recovery action failure immediately terminates in `ERROR`; the Runner does not cross a failed recovery precondition. Final Failure includes original category/code and recovery state/code/metrics.

## 9. Checkpoint and resume schema v3

Add:

```text
phase: FORWARD | RECOVERY
failed_state: optional State
original_failure: optional Failure
next_state: State
expected: ExpectedWorldState
```

Forward checkpoints retain current behavior. Once a failed action is stopped, freshly observed, and classified, Runner commits a recovery checkpoint before the first recovery side effect. Each successful recovery state commits the next recovery boundary.

Checkpoint persistence is subordinate to physical safety. If writing the recovery-entry checkpoint
fails, Runner records `recovery_checkpoint_persisted=0` and continues emergency recovery only in
the current process. If a later recovery checkpoint also fails, the same in-process recovery pass
continues without claiming a durable resume boundary. The terminal result remains `ERROR`, retains
the original workflow failure, and includes the persistence failure in its message/metrics.

On recovery resume, Runner validates the simulation session, configuration hash, and current world,
waits within the bounded stationary window for fresh Gazebo Coke stationary evidence, then runs
`IRecoveryPolicy` again. It never executes the persisted recovery state without reclassification.
Terminal cleanup completion reports the original workflow as `ERROR`, not `DONE`.

## 10. Configuration

All behavior-affecting values participate in the configuration hash.

| Parameter | Default |
| --- | ---: |
| `velocity_scaling` | `0.10` |
| `acceleration_scaling` | `0.10` |
| `cartesian_eef_step` | `0.005 m` |
| `cartesian_min_fraction` | `0.99` |
| `joint_jump_threshold` | `0.20 rad` |
| `motion_start_joint_tolerance` | `0.010 rad` |
| `tcp_position_tolerance` | `0.020 m` |
| `tcp_orientation_tolerance_rad` | `0.0872665 rad` |
| `coke_position_tolerance` | `0.010 m` |
| `coke_orientation_tolerance_rad` | `0.0872665 rad` |
| `gripper_open_position` | `0.040 m` |
| `gripper_open_min_position` | `0.038 m` |
| `gripper_close_position` | `0.000 m` |
| `gripper_grasp_min_position` | `0.028 m` |
| `gripper_grasp_max_position` | `0.037 m` |
| `gripper_symmetry_tolerance` | `0.003 m` |
| `joint_velocity_tolerance` | `0.010 rad/s` |
| `attachment_timeout_seconds` | `2.0 s` |
| `planning_scene_timeout_seconds` | `2.0 s` |
| `state_poll_interval_seconds` | `0.05 s` |
| `coke_settle_samples` | `5` |
| `coke_settle_interval_seconds` | `0.05 s` |
| `coke_settle_position_tolerance` | `0.002 m` |
| `coke_settle_orientation_tolerance_rad` | `0.020 rad` |
| `recovery_safe_height` | `0.987 m` (minimum canonical safe height) |

Every motion artifact contains a complete map of named planned-start joints. Plan validation
compares it with the pre-plan snapshot, and the MoveIt adapter rereads current joints immediately
before `execute()` using `motion_start_joint_tolerance`; missing, non-finite, or changed state fails
closed. Recovery no-op artifacts carry the same verifiable start-joint evidence. Forward resume
applies the same tolerance to the checkpoint's complete named-joint map. Recovery resume requires
complete finite named-joint evidence but deliberately permits drift from an old recovery checkpoint,
then reclassifies current stopped-world facts; this covers a crash after an action but before its
checkpoint commit. All shared 6DoF distance calculations reject non-finite position or quaternion
input with an infinite error so NaN observations cannot satisfy a contract.

`FixedPickPlaceTargetPolicy` owns both the canonical recovery safe height and the single TCP-to-Coke
center offset. A recovery lift target uses `max(observed_tcp_z, recovery_safe_height)`. Forward and
recovery support checks derive pick/place Coke center poses from the policy's TCP targets and require
the Coke's absolute position and upright orientation.

The launch-lifetime attachment relay actively republishes detach commands while initial attachment
state is unknown, independent of whether an initial `attached` event was observed. It stops only
after a raw `detached` confirmation. A timed-out gripper goal retains its pending goal-response
future; cancellation resolves it within a bound, cancels and acknowledges an accepted goal, accepts
an explicit rejection as proof of no goal, and otherwise fails closed.

The force-reset utility is `reset_world.sh`. It actively detaches the Gazebo Coke, resets its fixed
6DoF pose, detaches and upserts the MoveIt world Coke through `reset_moveit_world`, verifies durable
Gazebo detach, and only then opens the gripper, returns the Panda arm to ready, and closes the
gripper. This utility establishes a new test world; it is not a replacement for in-workflow safety
recovery.

The installed Jazzy `GripperActionController` parameter schema is verified before editing `controllers.yaml`. The intended configuration is `allow_stalling=true`, `stall_velocity_threshold=0.001`, `stall_timeout=1.0`, and `goal_tolerance=0.002`, so Coke contact can complete a grasp action without requiring an empty-gripper zero position.

## 11. Observability

Every state logs structured evidence with state and transition names:

- target, planned-end, and executed-end TCP poses;
- Cartesian fraction, trajectory points, maximum joint jump, and trajectory duration;
- both finger positions and velocities;
- Gazebo and MoveIt attachment states;
- Coke pose before/after and drift;
- `TCP→Coke` relative-pose error while carrying;
- MoveIt world/attached membership, attached link, and touch links;
- plan, action, postcondition, and recovery failure codes;
- checkpoint phase, sequence, and next state.

## 12. Testing strategy

### 12.1 Pure unit tests

- every normal success transition and canonical dry-run failure route;
- all RecoveryPolicy attachment/height/observation combinations;
- pose, Cartesian, and carried-object plan validators;
- every transition contract's precondition, postcondition, and resume behavior;
- fail-closed behavior for missing executor, contract, planner validator, observer, checkpoint store, or recovery policy;
- checkpoint v3 serialization and recovery resume reclassification.

### 12.2 ROS adapter tests

- Gripper action success, rejection, contact stall, timeout, acknowledged cancel, and asymmetric finger feedback;
- Gazebo attach/detach command and output convergence;
- MoveIt world/attached mutual exclusion, attached link, touch links, and convergence timeout;
- Planning Scene sync with full 6D object pose.

### 12.3 Headless integration tests

- one complete fixed pick-place cycle;
- plan-only for every motion state with no physical motion or recovery checkpoint;
- plan-only target and planned endpoints compared in position and quaternion angular distance;
- stop-after and resume across forward and recovery process boundaries;
- three representative partial-side-effect recoveries: Gazebo-only attach, failure while carrying, and Gazebo-detached/MoveIt-attached release;
- final invariants: safe TCP, open gripper, both models detached, Coke at fixed place, and cross-world pose consistency.

### 12.4 Course acceptance

After reset, run the full fixed pick-place three consecutive times. Record initial/final Coke pose, every motion plan result, gripper result, attachment state, and final invariants. The user must explain one normal trace and one recovery trace before `V3-T004` is marked complete.

## 13. Delivery and implementation order

The complete capability is delivered as one integrated change, but implementation follows test-driven, reviewable batches:

1. finish and verify the existing `DESCEND` work;
2. add shared execution context, plan-validator registry, recovery policy, and checkpoint v3;
3. implement gripper close/open and controller configuration;
4. implement Gazebo and MoveIt attach/detach adapters;
5. implement carried-object motion states;
6. implement release, synchronization, and retreat;
7. implement carrying recovery and idempotent cleanup;
8. wire the node, configuration hash, logging, and launch parameters;
9. run unit, adapter, lint, explicit cppcheck, headless, and three-run acceptance verification.

No production behavior is added without first observing its focused test fail for the expected reason.
