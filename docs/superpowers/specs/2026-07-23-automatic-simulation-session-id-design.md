# Automatic Simulation Session ID Design

## Goal

Allow a new execute workflow to start without an explicit `simulation_session_id`, while retaining
the session boundary that protects checkpoints from stale simulation state. The selected session ID
must always be visible in the console so an operator can reuse it for resume.

## Scope

This change affects startup parameter resolution and logging for
`pick_place_state_machine`. It does not change checkpoint schema v3, resume validation, state
transitions, planning, or execution behavior.

## Resolution rules

Session ID resolution is centralized in a small pure function with an injected timestamp:

- `mode=execute`, `resume=false`, and a non-empty configured ID: preserve the configured ID.
- `mode=execute`, `resume=false`, and an empty configured ID: generate
  `execute-<unix_timestamp_milliseconds>`.
- `resume=true`: never generate an ID. An empty configured ID remains an error for both
  `plan_only` and `execute` resume.
- Non-resume `plan_only` and `dry_run`: do not generate or consume a session ID.

The generated value is passed unchanged to `GazeboWorldObserver`, `CommonResumeValidator`, and
checkpoint writes. `stop_after` does not affect resolution: initial execute runs generate an ID
whether they run continuously or stop at a checkpoint.

## Logging

Every startup path that consumes a session ID emits one INFO record before creating the world
observer or running the workflow:

```text
SIMULATION_SESSION_ID=<resolved-id>
```

Generated and explicitly configured IDs use the same record format. This includes execute startup
and plan-only/execute resume. Non-resume `plan_only` and `dry_run` do not emit the record because
they do not consume a simulation session ID.

## Failure behavior

Resume with an empty configured ID remains fail-closed and exits before planning, execution, world
observation, or checkpoint mutation. Timestamp generation cannot replace resume identity because a
new value would make a stale checkpoint appear to belong to a new session.

## Test strategy

Tests are written before implementation and exercise the pure resolver with a fixed millisecond
timestamp:

- initial execute with an empty configured ID generates the exact expected value;
- `stop_after` is irrelevant because it is outside session resolution;
- initial execute preserves an explicit ID;
- resume preserves an explicit ID and rejects an empty ID;
- non-resume `plan_only` and `dry_run` return no session ID;
- the node logs the final value through one shared INFO statement.

Package build, focused tests, complete `colcon test`, read-only uncrustify, and `git diff --check`
remain required before completion.
