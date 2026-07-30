# SO-101 Joint Safe-Range UX Design

## Goal

Clarify that MoveIt planning and planned execution control only arm joints 1–5,
and prevent every Web UI joint-target editing path from exceeding a two-degree
safety inset from the SO-101 URDF position limits.

## Terminology

- Rename `Plan joints` to `Plan Arm`.
- Rename `Execute planned` to `Execute Arm`.
- Keep `Execute gripper` for joint 6 and `Execute All` for the ordered arm-then-
  gripper operation.

## Authoritative limits

The Teleop backend owns the position-limit source used by the browser. It
publishes each joint's URDF hard lower and upper limits in the existing
`JointSample.lower_limit_rad` and `JointSample.upper_limit_rad` fields. The
values cover joints 1–6 and match `urdf/so101_base.xacro`:

| Joint | Hard lower (rad) | Hard upper (rad) |
|---|---:|---:|
| 1 | -1.91986 | 1.91986 |
| 2 | -1.74533 | 1.74533 |
| 3 | -1.74533 | 1.5708 |
| 4 | -1.65806 | 1.65806 |
| 5 | -2.79253 | 2.79253 |
| 6 | -0.059303612618397 | 1.74533 |

The UI derives the safe editable range using one uniform margin:

```text
safe lower = hard lower + 2 degrees
safe upper = hard upper - 2 degrees
```

The backend telemetry is the runtime contract; the frontend does not maintain
a second hard-coded joint-limit table. If either bound is unavailable or the
inset produces an invalid interval, the corresponding target editor is
disabled and reports that safe limits are unavailable.

## UI behavior

Each joint row displays its safe range in degrees and supplies the same values
as the numeric input's `min` and `max`. A shared pure clamp function is used by
all browser target mutation paths:

1. direct number entry;
2. the `-1°` and `+1°` trim buttons;
3. Target YAML import.

Values inside the safe range pass through unchanged. Values outside it stop at
the nearest safe boundary. The page emits a visible notice naming the joint,
the clamped boundary in degrees, and the two-degree safety margin. Clamping a
target continues to invalidate any existing plan through the existing target
state reducer.

This feature constrains browser targets. Existing MoveIt and controller limit
checks remain independent downstream safety layers; the browser does not claim
to replace them.

## Data flow and boundaries

`RosTelemetryWorker` attaches authoritative hard bounds to each joint sample.
`App` receives them over the existing snapshot/WebSocket contract. A small
frontend joint-limit module calculates safe bounds and clamp results. The
`JointPanel` applies it to manual edits and trims; the Target YAML import path
applies the same function before dispatching edits. No new API endpoint or
persistent process is introduced.

Every failed API response that contains a machine-readable `code` is surfaced
through one global official shadcn toast boundary. This includes lease, plan,
execute, gripper, Gazebo, workflow, parameter, reset, and both `Execute All`
sub-results. The toast includes the response `code` and human `message`, so
failures such as `MOVEIT_IK_FAILED_-31` are diagnosable without opening browser
developer tools. Successful responses do not emit error toasts. The existing
inline notice and Event log remain available as persistent context.

TCP IK planning supplies a 60-second request timeout and permits the ROS service
call to return after that full search budget. While `/plan/tcp` is pending, the
TCP panel replaces `Plan TCP` with `Planning TCP…` and disables duplicate plan
submissions. The pending state clears on success and every failure path. A
longer timeout does not convert an unreachable target into a reachable one;
`MOVEIT_IK_FAILED_-31` remains an explicit target conflict.

Web dependency installation, scripts, shadcn CLI calls, and the one-command
launch preflight use Bun consistently with `bun.lock`; npm and
`package-lock.json` are not part of the project build path.

## Tests and acceptance

TDD must establish RED before implementation and GREEN afterward for:

- `Plan Arm` / `Execute Arm` labels and removal of the ambiguous labels;
- backend telemetry limits for all six joints matching the URDF values;
- the uniform two-degree inset;
- lower and upper clamping for direct entry and trim buttons;
- Target YAML import clamping;
- disabled editing when safe bounds are unavailable;
- visible clamp feedback and plan invalidation.
- failed API response codes and messages rendered in a toast.
- the 60-second TCP IK budget and visible, duplicate-safe pending state.

Then run complete Vitest, Playwright, production Web build, targeted Python
Teleop tests, and the full `so101_gazebo_demo` package suite. Rebuild and source
the installed overlay, restart only the owned Teleop service, and visually
confirm the renamed actions, safe-range display, and boundary behavior in the
existing simulation stack. Do not execute Attach during acceptance.
