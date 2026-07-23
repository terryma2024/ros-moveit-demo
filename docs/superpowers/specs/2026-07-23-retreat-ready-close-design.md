# Retreat Ready-and-Close Design

## Goal

Make both terminal retreat paths leave the Panda in its reproducible initial operating posture:
the arm reaches MoveIt's `ready` named target and the gripper is closed. A normal completed
pick-place run reaches `DONE`; a recovery run still reaches `ERROR` because the task objective was
not achieved.

## Scope

This changes the behavior of the existing `RETREAT -> DONE` and `RECOVER_RETREAT -> ERROR`
transitions only. It does not add states, alter the recovery decision policy, or change the meaning
of terminal run status.

## State semantics

The two transitions share the same physical completion sequence:

1. Plan a collision-aware arm motion to the MoveIt named target `ready`.
2. Execute that arm motion and observe a fresh, stationary robot at the named target.
3. Command the gripper closed and observe that both fingers are in the configured closed range.
4. Validate the detached, synchronized Coke and Planning Scene invariants already required at the
   terminal boundary.

The logical results remain distinct:

- `RETREAT -> DONE` means the pick-place objective and this reset sequence both succeeded.
- `RECOVER_RETREAT -> ERROR` means recovery completed the reset sequence, but the original task
  failed. The original failure remains the run's reported cause.

If planning, arm execution, stationary observation, or gripper closure fails, the transition fails
closed. `RETREAT` follows its existing failure edge into recovery; `RECOVER_RETREAT` reaches
`ERROR` with the recovery failure recorded.

## Design

Introduce a focused ready-retreat planner/executor and register it only for the two retreat states.
It composes the existing MoveIt motion and gripper adapters instead of teaching every generic pose
or Cartesian action about gripper behavior.

The MoveIt adapter gains a named-target planning path. The target name is a runtime parameter
defaulting to `ready`, which is resolved by MoveIt's Panda SRDF. This is the single source of the
seven ready joint values; neither C++ nor shell scripts duplicate them for state-machine planning.

The ready plan artifact records the requested named target, planned end joint positions, and the
ordinary MoveIt trajectory. Its plan validator rejects an absent/empty trajectory, an unresolved
named target, or an end joint vector outside the configured ready-joint tolerance. It never
substitutes a TCP-pose validator, since a named joint target is the contract.

In execute mode the action executes the accepted arm plan first. Only after the arm is stationary
at ready does it command the gripper closed. In `plan_only`, it creates and validates only the arm
plan; it does not command the gripper or mutate the world.

## Transition contracts

Both retreat preconditions retain their current safety checks: fresh stationary observation,
detached Coke in Gazebo and MoveIt, synchronized world object, supported/stationary Coke, and
open gripper before the reset action.

Both postconditions require:

- a successful composite action and a fresh stationary observation;
- arm joints within `ready_joint_tolerance` of the resolved named target;
- both gripper fingers within the configured closed range;
- Coke detached in both worlds, stable/supported, and present/synchronized in the Planning Scene.

The normal contract additionally preserves its place-completion checks. The recovery contract
continues to verify recovery-world consistency, but no longer treats the old vertical TCP retreat
target as its final target.

`DONE` consequently represents a reset robot with a closed gripper. `ERROR` reached through
`RECOVER_RETREAT` has the same verified physical reset, while retaining error status.

## Observability and resume

The existing arm trajectory and gripper action logs identify the two phases. Checkpoints written
after either retreat contain the observed ready joints and closed fingers. Resume validation uses
the same transition contract at the preceding/next state boundary, so it rejects a checkpoint that
claims terminal retreat completion but does not match the ready-and-closed physical state.

## Test strategy

Tests are written before implementation and cover:

- registration coverage: the two retreat states use the ready-retreat action, not generic
  Cartesian motion;
- named-target plan validation: missing trajectory, missing target, and wrong planned joints fail
  closed; a valid `ready` plan passes;
- action ordering: execute arm-to-ready before close-gripper; plan-only never commands the
  gripper; arm failure prevents close-gripper;
- forward and recovery contracts: preconditions still demand an open, detached world; postconditions
  demand ready joints and closed fingers; recovery still has `ERROR` as its terminal state;
- focused and complete package tests, read-only uncrustify, and `git diff --check`.
