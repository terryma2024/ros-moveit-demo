# SO-101 cross-platform profiling design

**Date:** 2026-08-31

**Status:** Approved in chat on 2026-08-31

**Implementation branch:** `codex/so101-cross-platform-profiling`

**Implementation worktree:**
`/Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/so101-cross-platform-profiling`

**Base commit:** `e7e0299cf8115214a0daf483cc40da6b09309091`

**Primary launch:**
`src/so101_demo_py/launch/so101_mujoco_text_pick_agent.launch.py`

## 1. Goal

Add stage-level profiling to the SO-101 MuJoCo Text Agent workflow without changing its planning,
validation, dispatch, motion, or physical safety decisions. The same semantic spans and artifact
schema must work on macOS and Linux. Linux may add ROS 2 and operating-system detail through
`ros2_tracing`; macOS uses the portable timeline in the first implementation.

Profiling is off by default. When it is off, the workflow must not open files, read profiling
clocks, allocate events, start a tracing session, or wrap runtime dependencies.

## 2. Platform boundary

The semantic layer is the portable source of truth. It records phases that matter to this demo,
including perception, model planning, command validation, dispatch, runtime setup, and each
pick-place state.

The system layer is optional:

| Platform | Semantic profiling | System tracing |
|---|---|---|
| macOS | Summary JSON and Perfetto-compatible timeline | Not included in the first implementation |
| Linux | The same summary JSON and timeline | `ros2_tracing` with LTTng when available |

The official `ros2_tracing` implementation currently supports LTTng and therefore Linux only.
Its macOS build disables tracepoints. This design does not maintain a private macOS LTTng port.

References:

- [ros2_tracing](https://github.com/ros2/ros2_tracing)
- [Perfetto tracing SDK and platform support](https://perfetto.dev/docs/instrumentation/tracing-sdk)
- [Perfetto external trace formats](https://perfetto.dev/docs/getting-started/other-formats)

## 3. Public launch contract

The Text Agent launch adds these arguments:

| Argument | Default | Meaning |
|---|---|---|
| `profiling` | `off` | One of `off`, `summary`, or `trace` |
| `profiling_output_root` | Empty | Optional absolute output root; an empty value uses the current session evidence root |
| `profiling_require_system_trace` | `false` | On Linux, fail before execution if the requested `ros2_tracing` backend is unavailable |

Mode behavior:

- `off` leaves the current process graph and business behavior unchanged.
- `summary` records completed semantic spans and writes aggregate JSON.
- `trace` records semantic spans and writes both aggregate JSON and a Perfetto-compatible Chrome
  Trace Event file. On Linux it also enables `ros2_tracing` when the dependency is available.

`profiling_output_root` must be an absolute path under the run's registered evidence root. The
launch rejects traversal, an existing non-directory path, and an output root that escapes the run
evidence boundary.

## 4. Components

### 4.1 Profiling configuration

A small immutable configuration object parses the launch or CLI values once. It holds the mode,
session ID, request ID when known, process role, output root, and system-trace requirement.

Invalid configuration fails before ROS nodes or simulator processes start. The disabled
configuration does not construct sinks.

### 4.2 Semantic profiler

The semantic profiler has a narrow interface:

```text
start_span(name, attributes) -> token
finish_span(token, outcome, attributes)
instant(name, attributes)
close()
```

Span names and required attributes are defined centrally. Call sites do not know the file format or
platform backend. Attributes are scalar JSON values only. They must not contain API keys, raw model
responses, full environment dumps, image payloads, point clouds, or arbitrary ROS messages.

Each process writes its own append-only event stream. Separate files avoid cross-process locks on
the hot path. A finalizer merges those streams into the session summary and portable timeline.

### 4.3 Composition-time wrappers

Instrumentation is attached at existing dependency boundaries:

- a planner wrapper measures provider calls;
- a dispatcher wrapper measures command resolution;
- an executor wrapper measures preview or runtime dispatch;
- state action wrappers measure each `StateAction.run()` call;
- the RGB-D CLI measures startup, synchronized-frame acquisition, estimation, tf2 conversion, and
  publication;
- the launch layer measures owned-process startup, scene readiness, workflow lifetime, and cleanup.

When profiling is off, each wrapper factory returns the original object or action mapping. The
state loop, planner, dispatcher, and executor therefore keep their existing call path.

The few semantic boundaries that remain inside `TextAgent.handle()` use a single disabled-mode
branch. The disabled branch must not call a no-op profiler.

### 4.4 Portable artifact writer

The writer produces deterministic JSON with atomic final files. Raw per-process events remain
available if the launch is interrupted before finalization.

The Perfetto artifact uses the Chrome Trace Event JSON format. It records process and thread
metadata plus complete duration events. It does not require a Perfetto daemon or SDK at runtime.

### 4.5 Linux system backend

The Linux backend uses the official `tracetools_launch.actions.Trace` action so tracing starts
before the application processes. Its output is kept beside the semantic artifacts and referenced
from the profiling manifest.

The module is imported only when all of these conditions hold:

1. `profiling=trace`;
2. the platform is Linux;
3. the `tracetools_launch` package is discoverable.

An unavailable backend degrades to semantic trace unless
`profiling_require_system_trace=true`. The required mode fails during launch materialization,
before physical execution.

## 5. Semantic span contract

Stable span names form a versioned contract. Version 1 includes:

| Span | Owner | Required outcome data |
|---|---|---|
| `launch.total` | launch | exit status and shutdown reason |
| `launch.stack_startup` | launch | readiness result |
| `launch.scene_setup` | launch | process exit code |
| `perception.total` | RGB-D process | published, rejected, timeout, or error |
| `perception.wait_synchronized_frame` | RGB-D process | frame availability |
| `perception.estimate_cup_pose` | RGB-D process | accepted or reason code |
| `perception.transform_world` | RGB-D process | accepted or tf2 error class |
| `agent.total` | Text Agent | `AgentStatus` and reason code |
| `agent.validate_input` | Text Agent | accepted or reason code |
| `agent.plan` | planner wrapper | provider, model, fallback flag, and outcome |
| `agent.validate_command` | Text Agent | planner outcome and reason code |
| `agent.dispatch` | dispatcher wrapper | preview, rejected, or execute |
| `runtime.total` | executor wrapper | runtime status and session ID |
| `runtime.setup` | runtime composition | accepted or reason code |
| `runtime.state.<STATE>` | state action wrapper | action status and failure category |
| `runtime.cleanup` | runtime | cleanup status |

Span attributes carry identifiers already present in the workflow, including `session_id`,
`request_id`, `backend`, `run_mode`, process role, state name, and reason code. The profiler does not
create execution authorization or infer physical success.

## 6. Time and correlation

Durations use `time.perf_counter_ns()`. Each process also records a wall-clock anchor, process ID,
thread ID, session ID, request ID when available, source commit, and installed package prefix.

Events from different processes are merged only when their session IDs match. The finalizer keeps
the original process timestamps and reports incomplete streams rather than inventing missing
durations.

Profiling time is observation data. It must not be used for controller deadlines, state-machine
timeouts, freshness checks, or retry policy.

## 7. Artifact layout

Profiling stays inside the run evidence directory:

```text
<run-evidence-root>/profiling/
  manifest.json
  summary.json
  trace.json
  processes/
    launch.events.jsonl
    perception.events.jsonl
    text-agent.events.jsonl
    dynamic-runtime.events.jsonl
  ros2-tracing/
    ... LTTng CTF output on Linux only ...
```

`summary.json` contains schema version, platform, mode, provenance, completeness, backend status,
total duration, ordered spans, and aggregates by span name. Aggregates include count, total,
minimum, maximum, mean, and p50. They include p95 when a span has at least 20 samples.

The manifest records artifact paths and backend errors. Existing `AgentResult`, runtime manifests,
physical evidence, and qualification artifacts keep their current schemas.

## 8. Failure handling

Profiling must not change a valid robot outcome.

- A sink write failure disables that sink, records a warning when possible, and lets the workflow
  continue.
- A malformed event is skipped by the finalizer and listed in `manifest.json`.
- An interrupted process leaves an incomplete raw stream. The summary marks it incomplete.
- A missing Linux system backend degrades to the portable trace by default.
- `profiling_require_system_trace=true` converts only system-backend setup failure into a launch
  error before execution.

Business errors remain authoritative. Profiling never rewrites `AgentStatus`, state transitions,
runtime exit codes, MoveIt results, controller results, Gazebo or MuJoCo evidence, or Planning Scene
state.

## 9. Disabled-mode performance contract

The `off` path is part of the public behavior and has explicit tests:

- no profiling directory is created;
- no clock function supplied by the profiling module is called;
- composition factories return the original planner, dispatcher, executor, and action objects by
  identity;
- the launch does not import or construct `tracetools_launch` actions;
- existing launch commands and result JSON remain byte-for-byte compatible where values are
  deterministic.

A focused microbenchmark compares the Text Agent preview path and a dry-run state-machine path with
profiling absent versus explicitly set to `off`. Each case runs 30 paired repeats of at least 10,000
iterations after five warm-up repeats. The disabled path passes when its median per-iteration time
is no more than 2 percent or 100 nanoseconds above the unconfigured path, whichever allowance is
larger. The exact command and raw data will be recorded in the task evidence root before the
implementation is accepted.

## 10. Implementation order

### Phase 1: macOS portable profiling

1. Add failing contracts for configuration, disabled identity, span lifecycle, atomic artifacts,
   and Perfetto JSON.
2. Implement the semantic module with standard-library dependencies only.
3. Instrument Text Agent, dynamic runtime states, RGB-D perception, and launch lifecycle.
4. Add launch arguments and installed launch tests.
5. Run focused tests, the full `so101_demo_py` package suite, a fresh build, installed provenance
   checks, and a dry-run profiling smoke test on macOS.

Phase 1 does not add `OSSignposter`, PyObjC, OpenTelemetry, or a resident collector. A native macOS
backend can be added later without changing the semantic span contract.

### Phase 2: Linux `ros2_tracing`

1. Add platform and dependency-discovery contracts.
2. Add the conditional `Trace` action and output manifest linkage.
3. Verify disabled and semantic-only modes without LTTng.
4. Build and source the candidate overlay on ai-station.
5. Run an isolated dry-run or plan-only launch, confirm semantic artifacts and LTTng events, and
   verify owned-process cleanup.

Linux runtime validation must record source commit, installed prefix, runtime executable,
`ROS_DOMAIN_ID`, and `GZ_PARTITION`. It must preserve unrelated remote files, evidence, tmux
sessions, and processes.

## 11. Test and acceptance plan

Development follows RED, GREEN, and package-level verification.

Required automated coverage includes:

- configuration validation and launch defaults;
- disabled object identity and zero artifact creation;
- nested spans, exceptions, interrupted spans, and deterministic serialization;
- per-process file ownership and merge correlation;
- summary aggregation and Perfetto trace validation;
- redaction of secrets and unsupported attribute types;
- planner, dispatcher, executor, perception, and state-action wrappers;
- unchanged `AgentResult` and runtime-manifest contracts;
- macOS portable trace without Linux imports;
- Linux backend discovery, graceful degradation, and required-backend failure;
- old launch behavior when the new arguments are omitted.

The macOS package gate uses the repository's direct-pytest contract with the ROS Jazzy virtual
environment and writes ROS logs and JUnit output under the registered evidence root. Linux uses
`colcon build`, `colcon test`, installed-package provenance checks, and a runtime trace smoke test on
ai-station.

The runtime smoke tests do not claim physical pick-place success. Profiling acceptance requires
correct durations, identifiers, artifacts, provenance, and clean shutdown. Physical success remains
subject to the existing Gazebo, MoveIt, controller, joint, TF, contact, pose, and visual evidence
gates.

## 12. Out of scope

- Porting LTTng or ROS 2 core tracepoints to macOS;
- a graphical profiling dashboard;
- network export, OpenTelemetry collectors, or cloud telemetry;
- sampling CPU stacks or heap allocations;
- changing planner prompts, command validation, dispatch authorization, motion policy, or retry
  behavior;
- changing physical acceptance rules;
- profiling Gazebo or real-arm launches in the first implementation.
