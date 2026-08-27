# macOS Headless CGL RGB-D Full-Restart Design

## Goal

Make the MuJoCo RGB-D perception pick-place launch work on macOS with
`headless=true`, without a Cocoa/GLFW window, and qualify the installed runtime
from all four supported cup keyframes with an independent full restart per
keyframe.

## Frozen acceptance contract

The four runs are:

| Run | MuJoCo keyframe | Cup position (m) |
| --- | --- | --- |
| 1 | `task_start` | `(0.02, -0.28, 0.165)` |
| 2 | `cup_test_forward_5cm` | `(0.02, -0.33, 0.165)` |
| 3 | `cup_test_left_5cm` | `(-0.03, -0.28, 0.165)` |
| 4 | `cup_test_right_5cm` | `(0.07, -0.28, 0.165)` |

Every run must use the same committed source and installed overlay while using
a new process tree, ROS domain ID, simulation session ID, and evidence file.
Passing requires all of the following from each run:

1. The launch runs with `headless=true` and does not create a Viewer window.
2. RGB, depth, and camera-info topics contain real payloads; topic registration
   alone is not evidence.
3. Depth encoding and values are usable by perception: finite positive depth is
   present in the cup region.
4. The RGB-D perception node publishes a valid `/cup_pose` derived from the
   current run.
5. The perception-driven MoveIt workflow grasps and places the cup successfully.
6. The whole process tree exits cleanly before the next keyframe starts.

## Architecture

`headless` and sensor rendering are separate decisions:

| Viewer | Sensor rendering | Rendering backend |
| --- | --- | --- |
| off | off | none |
| off | on, macOS | worker-owned CGL |
| off | on, Linux | EGL (existing fallback) |
| on | on, macOS | main-thread-created, worker-borrowed GLFW (existing path) |

The launch layer exposes `sensor_rendering`. The generic MuJoCo launch defaults
it to `auto`, preserving the existing behavior (`false` in headless mode and
`true` with a Viewer). The RGB-D perception launch defaults it to `true`, so
`headless=true` selects CGL on macOS without an extra user override. The value
is rendered into the existing `disable_rendering` hardware parameter.

`MujocoSystemInterface` must consume `disable_rendering` and pass the resulting
rendering-enabled policy to `MujocoSimulation`. The simulation lifecycle then
enables rendering plugins independently of Viewer availability. On macOS it
passes a GLFW context only for interactive mode; a null platform context plus
rendering enabled means the camera plugin must own a CGL context.

The CGL context is created, made current, locked, used, unlocked, and destroyed
on the camera rendering worker. MuJoCo scene/context destruction happens before
CGL release. Shutdown order remains:

1. reject new render work;
2. stop and join the camera worker;
3. free MuJoCo rendering resources;
4. release CGL or borrowed GLFW ownership;
5. destroy simulation model/data and Viewer resources.

## Failure behavior

- CGL initialization failure disables image publication and emits a specific
  backend error; it must not fall back to a Cocoa window from a worker thread.
- `sensor_rendering=false` keeps headless CI and physics-only launches free of
  graphics initialization.
- The four-run qualification stops at the first invalid run and preserves all
  evidence. A topic name without samples, stale evidence, a reused session, or
  incomplete shutdown is a failure.

## Evidence root

All low-rate logs, JUnit results, runtime provenance, and per-run evidence for
this task are registered under:

`/tmp/so101-debug-macos-headless-cgl-four-point-20260827/`
