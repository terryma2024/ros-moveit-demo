# Reset World Detach Design

## Goal

Replace `reset_coke.sh` with `reset_world.sh`. A successful reset must leave the Panda arm at its
ready pose with the gripper closed, while Gazebo and MoveIt both report Coke detached and represent
Coke at the same fixed world pose `(0.3, 0.0, 0.836)` with identity orientation.

## Scope

The change covers the reset script, a focused MoveIt reset helper, installation, unit/headless
fixtures, README text, and every in-repository caller. It does not add a new state-machine state or
change the normal/recovery transition graph.

## Components

### `reset_world.sh`

The renamed script owns orchestration and Gazebo operations. It must:

1. preflight the required Gazebo services, ROS actions, attachment topic, and MoveIt helper;
2. publish a Gazebo detach command even when Coke is currently attached;
3. wait for durable `/panda/coke_attached` evidence equal to `detached`;
4. pause Gazebo and reset Coke to the canonical fixed pose;
5. invoke the MoveIt helper to detach and synchronize Coke;
6. resume Gazebo and verify the final Gazebo detached fact;
7. poll and verify the final Gazebo Coke 6DoF pose within configured tolerances;
8. open the gripper, move the arm to ready, and close the gripper;
9. exit nonzero immediately when any required command or convergence check fails.

The existing world-resume trap remains active while Gazebo is paused. Reset is intentionally a
force-reset operation: unlike recovery, it may detach a carried Coke and teleport it to the fixed
pick pose. It must not be used as a substitute for state-machine recovery during an active workflow.

`EXPECTED_COKE_DETACHED=true` remains available only as caller-provided durable Gazebo evidence. It
may skip the initial Gazebo detach observation in harnesses whose event-driven plugin cannot replay
the last state, but it does not skip the detach command, MoveIt detach, MoveIt synchronization, or
final validation.

### MoveIt reset helper

A small ROS 2 executable owns MoveIt-specific mutation. It uses the existing MoveIt adapter
semantics to:

- detach object ID `coke` when attached;
- ensure Coke is absent from attached collision objects;
- add or replace the world CollisionObject at the canonical 6DoF pose;
- wait for Planning Scene convergence;
- fail nonzero when MoveGroup services are unavailable or convergence times out.

The helper is idempotent: an already detached Coke is still synchronized to the canonical pose.
It must not report success from command acknowledgement alone; final Planning Scene membership and
pose are required.

## Ordering and failure behavior

Gazebo detach happens before any arm motion. Coke is then reset and synchronized while the arm is
stationary. Only after both worlds converge does the script open the gripper, move the arm to ready,
and close it. This avoids carrying an attached Coke to the ready pose and prevents a MoveIt/Gazebo
split world from being treated as reset success.

If Gazebo detach cannot be confirmed, no Coke pose reset or arm/gripper command is allowed. If a
later Gazebo or MoveIt reset step fails, the script restores an accidentally paused world through
the trap and exits nonzero without moving the arm. If the final arm or gripper command fails, the
already-reset world remains valid but the overall reset still fails.

## Naming and migration

`reset_coke.sh` is removed rather than retained as a compatibility alias. CMake installation,
CTest, README instructions, complete-state-machine documentation, and all headless harnesses use
`reset_world.sh`. The test file is renamed to `test_reset_world.sh` and its CTest name becomes
`test_reset_world`.

## Test strategy

Tests are written before implementation and must demonstrate RED for the missing behavior.

- Shell fixture: attached Gazebo Coke triggers detach and waits for detached confirmation.
- Shell fixture: missing/unknown detach confirmation fails before pose or arm side effects.
- Shell fixture: MoveIt helper failure fails before arm side effects.
- Shell fixture: missing preflight interfaces fail before world or robot side effects.
- Shell fixture: a non-convergent Gazebo 6DoF pose fails before arm side effects.
- Shell fixture: command ordering is detach, reset/synchronize, open, ready, close.
- Helper tests: attached, detached/idempotent, unavailable scene, and non-convergent scene cases.
- Headless harnesses validate the reset helper's Planning Scene result before any subsequent scene
  setup can replace Coke.
- Migration check: no active source, CMake, README, or headless reference uses `reset_coke.sh`.
- Verification: targeted tests, package build, complete `colcon test`, read-only uncrustify, shell
  syntax checks, and `git diff --check`.

## Acceptance criteria

A real headless reset must prove from independent observations that:

- `/panda/coke_attached` is detached;
- Planning Scene has no attached Coke and has one world Coke;
- Gazebo and MoveIt Coke 6DoF poses match the canonical reset pose within configured tolerances;
- the Panda arm is at ready, both fingers are stationary and closed;
- the command exits zero only after all these facts hold.
