# SO-101 macOS semantic profiling implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add switchable stage timing and a portable timeline to `so101_mujoco_text_pick_agent.launch.py` on macOS while preserving the existing workflow and making the disabled path effectively free.

**Architecture:** A standard-library profiling package owns configuration, per-process JSONL streams, aggregation, and Chrome Trace Event output. Existing planner, dispatcher, executor, state-action, perception, and launch boundaries receive optional profilers. Disabled factories return existing objects by identity and no disabled path reads a clock or creates an artifact.

**Tech Stack:** Python 3.11, ROS 2 Jazzy launch and rclpy, pytest, JSON Lines, Chrome Trace Event JSON, `time.perf_counter_ns()`.

**Spec:** [`docs/superpowers/specs/2026-08-31-so101-cross-platform-profiling-design.md`](../specs/2026-08-31-so101-cross-platform-profiling-design.md)

## Global constraints

- Work only in `/Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/so101-cross-platform-profiling` on branch `codex/so101-cross-platform-profiling`.
- Keep all task logs, JUnit XML, benchmark data, and smoke-test artifacts under the registered evidence root `/tmp/so101-debug-cross-platform-profiling-design-20260831/`. Record every retained artifact in its `task-ledger.md`.
- Preserve `AgentResult`, runtime manifests, launch exit ownership, safety validation, controller behavior, and state transitions.
- Do not create a profiling directory, import a platform backend, read a profiling clock, or wrap a dependency when `profiling=off`.
- Use RED, GREEN, REFACTOR for each task. Run the stated failing test before editing production code.
- Use `apply_patch` for source edits. Do not use `ament_uncrustify --reformat`.
- Do not claim physical pick-place success from these tests. This plan accepts profiling artifacts and unchanged control behavior only.

## File map

| Path | Responsibility |
|---|---|
| `src/so101_demo_py/src/profiling/model.py` | Modes, immutable configuration, event model, scalar attribute validation |
| `src/so101_demo_py/src/profiling/session.py` | Optional profiler construction, span lifecycle, one process-owned JSONL sink |
| `src/so101_demo_py/src/profiling/artifacts.py` | Stream loading, aggregation, manifest, summary, Chrome Trace Event JSON |
| `src/so101_demo_py/src/profiling/wrappers.py` | Identity-preserving planner, dispatcher, executor, and state-action composition |
| `src/so101_demo_py/src/profiling/launch_support.py` | Launch argument parsing, path policy, process arguments, launch spans, finalization |
| `src/so101_demo_py/src/application/text_agent.py` | Input and command-validation spans |
| `src/so101_demo_py/src/cli/text_pick_agent.py` | Request-correlated profiler construction and wrapper composition |
| `src/so101_demo_py/src/ros/dynamic_runtime.py` | Runtime setup, cleanup, and state-action instrumentation |
| `src/so101_demo_py/src/ros/rgbd_cup_pose_node.py` | Perception total, frame wait, estimate, and tf2 spans |
| `src/so101_demo_py/src/cli/rgbd_cup_pose.py` | Perception process profiling arguments and profiler construction |
| `src/so101_demo_py/src/runtime/launch_composition.py` | Public launch arguments and launch-process lifecycle integration |
| `src/so101_demo_py/test/test_profiling_*.py` | Unit contracts for the new profiling package |
| Existing focused tests | Compatibility and integration coverage at each instrumented boundary |

---

### Task 1: Define modes, configuration, and the disabled factory

**Files:**

- Create: `src/so101_demo_py/src/profiling/__init__.py`
- Create: `src/so101_demo_py/src/profiling/model.py`
- Create: `src/so101_demo_py/src/profiling/session.py`
- Create: `src/so101_demo_py/test/test_profiling_session.py`

- [ ] **Step 1: Write the failing configuration and disabled-path tests**

Add tests with these contracts:

```python
def test_parse_mode_accepts_only_public_values() -> None:
    assert ProfilingMode.parse("off") is ProfilingMode.OFF
    assert ProfilingMode.parse("summary") is ProfilingMode.SUMMARY
    assert ProfilingMode.parse("trace") is ProfilingMode.TRACE
    with pytest.raises(ValueError, match="profiling"):
        ProfilingMode.parse("yes")


def test_disabled_factory_does_not_read_clocks_or_create_files(tmp_path: Path) -> None:
    def forbidden_clock() -> int:
        raise AssertionError("disabled profiling read a clock")

    config = ProfilingConfig.disabled(
        session_id="session-1",
        process_role="text-agent",
    )
    profiler = build_profiler(
        config,
        monotonic_ns=forbidden_clock,
        wall_time_ns=forbidden_clock,
    )
    assert profiler is None
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("value", [{"nested": 1}, [1], object()])
def test_event_attributes_reject_non_scalar_values(value: object) -> None:
    with pytest.raises(TypeError, match="scalar JSON"):
        validate_attributes({"bad": value})
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run:

```bash
PYTHONPATH=/tmp/so101-debug-cross-platform-profiling-design-20260831/pythonpath \
  /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -q \
  src/so101_demo_py/test/test_profiling_session.py
```

Expected: collection fails because `so101_demo.profiling` does not exist.

- [ ] **Step 3: Implement the public types and disabled factory**

Implement this public surface:

```python
class ProfilingMode(str, Enum):
    OFF = "off"
    SUMMARY = "summary"
    TRACE = "trace"

    @classmethod
    def parse(cls, value: str) -> "ProfilingMode": ...


@dataclass(frozen=True, slots=True)
class ProfilingConfig:
    mode: ProfilingMode
    output_root: Path | None
    session_id: str
    process_role: str
    request_id: str | None = None
    source_commit: str | None = None
    installed_prefix: str | None = None

    @classmethod
    def disabled(cls, *, session_id: str, process_role: str) -> "ProfilingConfig": ...


Scalar = str | int | float | bool | None


def validate_attributes(values: Mapping[str, object]) -> dict[str, Scalar]: ...


def build_profiler(
    config: ProfilingConfig,
    *,
    monotonic_ns: Callable[[], int] = time.perf_counter_ns,
    wall_time_ns: Callable[[], int] = time.time_ns,
) -> "SemanticProfiler | None":
    if config.mode is ProfilingMode.OFF:
        return None
    return SemanticProfiler(...)
```

Do not create a no-op profiler. The return value `None` is the disabled marker used throughout this plan.

- [ ] **Step 4: Add span lifecycle and sink-failure tests**

Cover a completed span, an exception outcome, an instant event, `close()` idempotence, one wall-clock anchor per process, and a sink write error that disables only profiling. Use injected clocks so every expected nanosecond value is exact.

- [ ] **Step 5: Implement the process-owned JSONL writer**

`SemanticProfiler` must expose:

```python
def start_span(self, name: str, attributes: Mapping[str, object] = {}) -> SpanToken: ...
def finish_span(
    self,
    token: SpanToken,
    *,
    outcome: str,
    attributes: Mapping[str, object] = {},
) -> None: ...
def instant(self, name: str, attributes: Mapping[str, object] = {}) -> None: ...
def close(self) -> None: ...
```

Write newline-delimited JSON to `profiling/processes/<process-role>.events.jsonl`, flush after each complete record, and use `perf_counter_ns` for duration. On the first I/O error, close the sink, store a warning, and turn later calls into in-memory returns without raising into the robot workflow.

- [ ] **Step 6: Run the focused test and confirm GREEN**

Run the command from Step 2. Expected: all tests pass.

- [ ] **Step 7: Commit the core**

```bash
git add src/so101_demo_py/src/profiling src/so101_demo_py/test/test_profiling_session.py
git commit -m "feat: add portable semantic profiling core"
```

---

### Task 2: Build deterministic summary and timeline artifacts

**Files:**

- Create: `src/so101_demo_py/src/profiling/artifacts.py`
- Create: `src/so101_demo_py/test/test_profiling_artifacts.py`
- Modify: `src/so101_demo_py/src/profiling/__init__.py`

- [ ] **Step 1: Write failing finalizer tests**

Create fixture streams for two process roles with a shared session ID. Assert:

```python
result = finalize_profiling(profiling_root)
summary = json.loads((profiling_root / "summary.json").read_text())
trace = json.loads((profiling_root / "trace.json").read_text())
manifest = json.loads((profiling_root / "manifest.json").read_text())

assert result.complete is True
assert summary["schema_version"] == 1
assert summary["aggregates"]["runtime.state.PLAN"]["count"] == 2
assert summary["aggregates"]["runtime.state.PLAN"]["p50_ns"] == 150
assert any(event["ph"] == "X" for event in trace["traceEvents"])
assert manifest["artifacts"]["trace"] == "trace.json"
```

Also test that a mismatched session is excluded, malformed JSON is listed in `manifest.json`, an unfinished span makes `complete=false`, p95 appears only at 20 samples, and final files are replaced atomically.

- [ ] **Step 2: Run the test and confirm RED**

```bash
PYTHONPATH=/tmp/so101-debug-cross-platform-profiling-design-20260831/pythonpath \
  /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -q \
  src/so101_demo_py/test/test_profiling_artifacts.py
```

Expected: import failure for `so101_demo.profiling.artifacts`.

- [ ] **Step 3: Implement stream loading and aggregation**

Use `runtime.task_artifacts.atomic_json` for final JSON. Keep raw streams untouched. Sort complete spans by `(wall_start_ns, process_role, sequence)`. Aggregate `count`, `total_ns`, `min_ns`, `max_ns`, `mean_ns`, and nearest-rank `p50_ns`; add nearest-rank `p95_ns` at 20 samples.

- [ ] **Step 4: Implement Chrome Trace Event JSON**

Emit process and thread metadata events plus one complete event per completed span:

```python
{
    "name": span.name,
    "cat": "so101.semantic",
    "ph": "X",
    "ts": span.wall_start_ns / 1_000,
    "dur": span.duration_ns / 1_000,
    "pid": span.pid,
    "tid": span.thread_id,
    "args": span.attributes | {"outcome": span.outcome},
}
```

Keep integer nanoseconds in `summary.json`. Microseconds are required only by the Chrome Trace Event format.

- [ ] **Step 5: Run the focused tests and confirm GREEN**

Run the command from Step 2. Expected: all tests pass.

- [ ] **Step 6: Commit the artifact layer**

```bash
git add src/so101_demo_py/src/profiling src/so101_demo_py/test/test_profiling_artifacts.py
git commit -m "feat: write profiling summaries and timelines"
```

---

### Task 3: Add identity-preserving boundary wrappers

**Files:**

- Create: `src/so101_demo_py/src/profiling/wrappers.py`
- Create: `src/so101_demo_py/test/test_profiling_wrappers.py`
- Modify: `src/so101_demo_py/src/profiling/__init__.py`

- [ ] **Step 1: Write failing identity and behavior tests**

Test all disabled factories with `is`, not equality:

```python
assert profile_planner(planner, None, provider="deepseek", model="m") is planner
assert profile_dispatcher(dispatcher, None) is dispatcher
assert profile_executor(executor, None) is executor
assert profile_actions(actions, None) is actions
assert profile_actions(actions, None)[state] is actions[state]
```

Enabled tests must assert delegated return values and exceptions are unchanged while the correct spans finish with `ok` or `error` outcomes.

- [ ] **Step 2: Run the test and confirm RED**

```bash
PYTHONPATH=/tmp/so101-debug-cross-platform-profiling-design-20260831/pythonpath \
  /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -q \
  src/so101_demo_py/test/test_profiling_wrappers.py
```

- [ ] **Step 3: Implement wrapper factories**

Provide these signatures:

```python
def profile_planner(planner: PlannerPort, profiler: SemanticProfiler | None, *, provider: str, model: str) -> PlannerPort: ...
def profile_dispatcher(dispatcher: TaskDispatcher, profiler: SemanticProfiler | None) -> TaskDispatcher: ...
def profile_executor(executor: PickPlaceExecutorPort, profiler: SemanticProfiler | None) -> PickPlaceExecutorPort: ...
def profile_actions(actions: Mapping[TaskState, StateAction], profiler: SemanticProfiler | None) -> Mapping[TaskState, StateAction]: ...
```

Each function must start with `if profiler is None: return original`. The wrappers delegate once, return the exact result object, re-raise the exact exception, and add only scalar metadata.

- [ ] **Step 4: Run the focused tests and confirm GREEN**

- [ ] **Step 5: Commit the wrappers**

```bash
git add src/so101_demo_py/src/profiling src/so101_demo_py/test/test_profiling_wrappers.py
git commit -m "feat: instrument SO-101 profiling boundaries"
```

---

### Task 4: Instrument TextAgent without changing its result contract

**Files:**

- Modify: `src/so101_demo_py/src/application/text_agent.py`
- Modify: `src/so101_demo_py/src/cli/text_pick_agent.py`
- Modify: `src/so101_demo_py/test/test_text_agent.py`
- Modify: `src/so101_demo_py/test/test_text_pick_agent_cli.py`

- [ ] **Step 1: Add failing tests for agent spans and unchanged results**

Construct `TextAgent(..., profiler=recording_profiler)` and cover accepted input, rejected input, planner rejection, command validation, preview dispatch, execute dispatch, and a raised planner exception. Compare enabled and disabled `AgentResult` values directly:

```python
assert profiled_result == baseline_result
assert span_names == [
    "agent.total",
    "agent.validate_input",
    "agent.plan",
    "agent.validate_command",
    "agent.dispatch",
]
```

The exact list may omit stages that are never reached after a rejection. Assert the reason code and `AgentStatus` on every finished stage.

- [ ] **Step 2: Run the focused tests and confirm RED**

```bash
PYTHONPATH=/tmp/so101-debug-cross-platform-profiling-design-20260831/pythonpath \
  /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -q \
  src/so101_demo_py/test/test_text_agent.py \
  src/so101_demo_py/test/test_text_pick_agent_cli.py
```

- [ ] **Step 3: Add the optional profiler and narrow in-method spans**

Add `profiler: SemanticProfiler | None = None` to `TextAgent.__init__`. Keep the existing control flow. Guard each in-method boundary with one `if self._profiler is not None` branch and never call a no-op object.

The planner, dispatcher, and executor spans come from Task 3 wrappers. The method itself owns `agent.total`, `agent.validate_input`, and `agent.validate_command`.

- [ ] **Step 4: Add internal CLI profiling arguments**

Add these non-ROS arguments to `text_pick_agent`:

```text
--profiling {off,summary,trace}
--profiling-output-root ABSOLUTE_PATH
--profiling-session-id SESSION_ID
```

Defaults preserve direct CLI behavior: `off`, empty output root, and the existing session ID source. Build the profiler only after request and session IDs are known. Compose wrappers only when the profiler is not `None`. Always call `profiler.close()` in a `finally` block when it exists.

- [ ] **Step 5: Run the focused tests and confirm GREEN**

- [ ] **Step 6: Commit the Text Agent integration**

```bash
git add src/so101_demo_py/src/application/text_agent.py \
  src/so101_demo_py/src/cli/text_pick_agent.py \
  src/so101_demo_py/test/test_text_agent.py \
  src/so101_demo_py/test/test_text_pick_agent_cli.py
git commit -m "feat: profile Text Agent stages"
```

---

### Task 5: Instrument dynamic runtime setup, states, total, and cleanup

**Files:**

- Modify: `src/so101_demo_py/src/adapters/pick_place_executor.py`
- Modify: `src/so101_demo_py/src/ros/dynamic_runtime.py`
- Modify: `src/so101_demo_py/test/test_pick_place_executor_adapter.py`
- Modify: `src/so101_demo_py/test/test_dynamic_execute.py`

- [ ] **Step 1: Write failing runtime correlation tests**

Extend `DynamicRuntimeContext` with an optional profiler and assert the adapter passes it into `run_dynamic_execute`. In dynamic runtime tests, inject a recording profiler and verify:

- `runtime.total` surrounds the whole call;
- `runtime.setup` finishes before `runner.run`;
- every executed state has one `runtime.state.<STATE>` span;
- `runtime.cleanup` runs on success and error;
- action return values, runner status, exit codes, and cleanup order do not change;
- `profiler=None` returns the original action mapping by identity.

- [ ] **Step 2: Run the focused tests and confirm RED**

```bash
PYTHONPATH=/tmp/so101-debug-cross-platform-profiling-design-20260831/pythonpath \
  /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -q \
  src/so101_demo_py/test/test_pick_place_executor_adapter.py \
  src/so101_demo_py/test/test_dynamic_execute.py
```

- [ ] **Step 3: Pass the profiler through runtime composition**

Add `profiler: SemanticProfiler | None = None` to `DynamicRuntimeContext`. Pass it to `run_dynamic_execute(options, profiler=...)`. Extend `run_dynamic_execute` with a keyword-only profiler defaulting to `None` so all current callers remain source compatible.

- [ ] **Step 4: Wrap the existing action mapping**

Immediately after `build_actions(...)`, call `profile_actions(actions, profiler)`. Keep the runner and state loop unchanged. Measure setup and cleanup at their current composition boundaries, and finish `runtime.total` in the outermost `finally` block.

- [ ] **Step 5: Run the focused tests and confirm GREEN**

- [ ] **Step 6: Commit dynamic runtime profiling**

```bash
git add src/so101_demo_py/src/adapters/pick_place_executor.py \
  src/so101_demo_py/src/ros/dynamic_runtime.py \
  src/so101_demo_py/test/test_pick_place_executor_adapter.py \
  src/so101_demo_py/test/test_dynamic_execute.py
git commit -m "feat: profile dynamic runtime states"
```

---

### Task 6: Instrument RGB-D perception

**Files:**

- Modify: `src/so101_demo_py/src/cli/rgbd_cup_pose.py`
- Modify: `src/so101_demo_py/src/ros/rgbd_cup_pose_node.py`
- Modify: `src/so101_demo_py/test/test_rgbd_cup_pose.py`

- [ ] **Step 1: Write failing perception span tests**

Use the existing fake runtime and exact injected clocks. Cover:

- `perception.total` for success, timeout, interrupt, and error;
- `perception.wait_synchronized_frame` from runtime readiness until the first synchronized callback;
- `perception.estimate_cup_pose` for accepted and rejected estimates;
- `perception.transform_world` for success and tf2 failure;
- unchanged publication, evidence, startup deadline, cleanup, and exit-code behavior.

- [ ] **Step 2: Run the focused test and confirm RED**

```bash
PYTHONPATH=/tmp/so101-debug-cross-platform-profiling-design-20260831/pythonpath \
  /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -q \
  src/so101_demo_py/test/test_rgbd_cup_pose.py
```

- [ ] **Step 3: Add optional profiler plumbing**

Use `run_rgbd_cup_pose(options, *, profiler=None, ...)`; do not put the profiler inside `RgbdCupPoseOptions`. Pass the profiler into the runtime and frame processor only where needed. A boolean flag must ensure the wait span finishes once on the first synchronized frame.

- [ ] **Step 4: Add internal CLI arguments**

Add the same `--profiling`, `--profiling-output-root`, and `--profiling-session-id` arguments used by the Text Agent CLI. Fix the process role to `perception`. Close the profiler in `finally` without changing the existing ROS cleanup owner.

- [ ] **Step 5: Run the focused test and confirm GREEN**

- [ ] **Step 6: Commit perception profiling**

```bash
git add src/so101_demo_py/src/cli/rgbd_cup_pose.py \
  src/so101_demo_py/src/ros/rgbd_cup_pose_node.py \
  src/so101_demo_py/test/test_rgbd_cup_pose.py
git commit -m "feat: profile RGB-D cup pose stages"
```

---

### Task 7: Add the public launch contract and lifecycle finalization

**Files:**

- Create: `src/so101_demo_py/src/profiling/launch_support.py`
- Create: `src/so101_demo_py/test/test_profiling_launch_support.py`
- Modify: `src/so101_demo_py/src/runtime/launch_composition.py`
- Modify: `src/so101_demo_py/test/test_text_pick_agent_launch.py`

- [ ] **Step 1: Write failing path-policy and launch-default tests**

Test all public values and path failures. The output root must be absolute and resolve under the registered run evidence root. Test symlink escape, `..` escape, and an existing non-directory.

Extend the launch test expected argument set with:

```python
{
    "profiling": "off",
    "profiling_output_root": "",
    "profiling_require_system_trace": "false",
}
```

Assert the existing `profiling=off` process commands remain byte-for-byte equal to the pre-change expected commands and no profiling directory exists after materialization.

- [ ] **Step 2: Run the focused tests and confirm RED**

```bash
PYTHONPATH=/tmp/so101-debug-cross-platform-profiling-design-20260831/pythonpath \
  /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -q \
  src/so101_demo_py/test/test_profiling_launch_support.py \
  src/so101_demo_py/test/test_text_pick_agent_launch.py
```

- [ ] **Step 3: Implement launch configuration parsing**

`resolve_launch_profiling(...)` returns `None` for `off`. For enabled modes it creates `<output-root>/profiling/processes`, constructs the launch profiler, and returns the exact child CLI arguments. An empty `profiling_output_root` resolves to the current session evidence root.

- [ ] **Step 4: Add child arguments only when enabled**

For `summary` and `trace`, append the internal profiling arguments to `rgbd_cup_pose` and `text_pick_agent`. For `off`, do not append any new process argument. This preserves the original command path and makes the byte-for-byte assertion meaningful.

- [ ] **Step 5: Measure launch lifecycle with event handlers**

Use launch event callbacks for `launch.stack_startup`, `launch.scene_setup`, and `launch.total`. Finish `launch.total`, close the launch stream, and call `finalize_profiling()` from an `OnShutdown` callback. Catch finalizer errors and log them without replacing the launch's existing business exit status.

Do not change the existing event handlers that own scene gating, terminal status, or shutdown. Register profiling handlers beside them only when profiling is enabled.

- [ ] **Step 6: Add enabled-mode integration assertions**

Assert `summary` passes profiling arguments to both child processes, `trace` also requests `trace.json`, and simulated process exits cause final files to appear. Verify finalization lists an interrupted stream rather than inventing a completion event.

- [ ] **Step 7: Run the focused tests and confirm GREEN**

- [ ] **Step 8: Commit the launch integration**

```bash
git add src/so101_demo_py/src/profiling/launch_support.py \
  src/so101_demo_py/src/runtime/launch_composition.py \
  src/so101_demo_py/test/test_profiling_launch_support.py \
  src/so101_demo_py/test/test_text_pick_agent_launch.py
git commit -m "feat: expose SO-101 launch profiling"
```

---

### Task 8: Prove disabled-mode overhead stays within the contract

**Files:**

- Create: `src/so101_demo_py/test/benchmark_profiling_off.py`
- Modify if needed: only the call sites identified by the benchmark

- [ ] **Step 1: Write the paired benchmark harness**

The script must run five warm-up repeats and 30 measured paired repeats. Each repeat must execute at least 10,000 Text Agent preview calls and 10,000 dry-run state action calls for these cases:

1. unconfigured baseline, using all constructor defaults;
2. explicit `profiling=off` or `profiler=None`.

Randomize the order within each pair, use `perf_counter_ns`, print machine-readable JSON, and fail if the disabled median per iteration is more than `max(baseline * 0.02, 100)` nanoseconds above baseline.

- [ ] **Step 2: Run the benchmark before optimization**

```bash
PYTHONPATH=/tmp/so101-debug-cross-platform-profiling-design-20260831/pythonpath \
  /Users/matianyi/ros2_jazzy/.venv/bin/python3 \
  src/so101_demo_py/test/benchmark_profiling_off.py \
  > /tmp/so101-debug-cross-platform-profiling-design-20260831/macos-profiling-off-benchmark.json
```

Expected: exit 0 and both scenarios pass. If it fails, inspect the measured call path and remove disabled wrappers or repeated mode checks. Do not relax the threshold.

- [ ] **Step 3: Add deterministic structural assertions**

Keep the clock-spy, no-directory, object-identity, and exact-command tests as the primary non-flaky guarantees. The microbenchmark supplements them.

- [ ] **Step 4: Commit the benchmark**

```bash
git add src/so101_demo_py/test/benchmark_profiling_off.py
git commit -m "test: measure disabled profiling overhead"
```

---

### Task 9: Build, verify the installed package, and run a macOS dry-run smoke test

**Files:**

- Modify: `/tmp/so101-debug-cross-platform-profiling-design-20260831/task-ledger.md`
- No production source changes unless a failing check exposes a defect; fix defects through a new RED test first.

- [ ] **Step 1: Run focused profiling and compatibility tests**

```bash
PYTHONPATH=/tmp/so101-debug-cross-platform-profiling-design-20260831/pythonpath \
  ROS_LOG_DIR=/tmp/so101-debug-cross-platform-profiling-design-20260831/ros-logs-focused \
  /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -q \
  src/so101_demo_py/test/test_profiling_session.py \
  src/so101_demo_py/test/test_profiling_artifacts.py \
  src/so101_demo_py/test/test_profiling_wrappers.py \
  src/so101_demo_py/test/test_profiling_launch_support.py \
  src/so101_demo_py/test/test_text_agent.py \
  src/so101_demo_py/test/test_text_pick_agent_cli.py \
  src/so101_demo_py/test/test_dynamic_execute.py \
  src/so101_demo_py/test/test_rgbd_cup_pose.py \
  src/so101_demo_py/test/test_text_pick_agent_launch.py \
  --junitxml=/tmp/so101-debug-cross-platform-profiling-design-20260831/macos-focused.xml
```

- [ ] **Step 2: Run the full package suite**

```bash
PYTHONPATH=/tmp/so101-debug-cross-platform-profiling-design-20260831/pythonpath \
  ROS_LOG_DIR=/tmp/so101-debug-cross-platform-profiling-design-20260831/ros-logs-full \
  /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -q \
  src/so101_demo_py/test \
  --junitxml=/tmp/so101-debug-cross-platform-profiling-design-20260831/macos-full.xml
```

Expected: at least the baseline 793 tests plus the new tests pass.

- [ ] **Step 3: Build a fresh candidate overlay**

```bash
source /opt/ros/jazzy/setup.zsh
colcon build \
  --base-paths src \
  --packages-select so101_demo_py \
  --build-base /tmp/so101-debug-cross-platform-profiling-design-20260831/build-macos \
  --install-base /tmp/so101-debug-cross-platform-profiling-design-20260831/install-macos \
  --log-base /tmp/so101-debug-cross-platform-profiling-design-20260831/colcon-log-macos \
  --symlink-install
```

- [ ] **Step 4: Verify source and installed provenance**

Source the candidate overlay, then record:

```bash
source /tmp/so101-debug-cross-platform-profiling-design-20260831/install-macos/setup.zsh
ros2 pkg prefix so101_demo_py
python3 -c 'import inspect, so101_demo.profiling; print(inspect.getfile(so101_demo.profiling))'
ros2 launch so101_demo_py so101_mujoco_text_pick_agent.launch.py --show-args
```

The package prefix and Python module must resolve under the candidate install root. The launch output must show all three public profiling arguments with approved defaults.

- [ ] **Step 5: Run an isolated non-physical smoke test**

Use a unique `ROS_DOMAIN_ID`, `GZ_PARTITION`, and evidence subdirectory under the registered root. Run the existing dry-run or plan-only Text Agent path with `profiling=trace`. Assert:

- child processes receive one session ID;
- `profiling/manifest.json`, `summary.json`, and `trace.json` parse as JSON;
- stable span names and process roles are present;
- no `profiling/ros2-tracing` directory exists on macOS;
- owned processes stop cleanly;
- the existing result and runtime manifest retain their schemas and status.

If the launch has no safe dry-run configuration that exercises perception, run the Text Agent preview CLI and RGB-D fake-runtime integration separately. Record that limitation instead of starting physical execution.

- [ ] **Step 6: Inspect the final diff and evidence ledger**

```bash
git diff --check
git status --short
git log --oneline --decorate -10
```

Update the ledger with commands, return codes, installed prefix, retained runs, archived runs, and deletion candidates. Do not delete evidence.

- [ ] **Step 7: Commit any test-only acceptance updates**

If no source change was needed, no commit is required. If a tracked acceptance fixture changed, stage only that file and use:

```bash
git commit -m "test: verify macOS profiling integration"
```

## Phase 1 completion criteria

- All focused and full tests pass from the isolated worktree.
- The candidate install, not the source tree, supplies the runtime package.
- `profiling=off` produces no artifacts, no clock reads, no wrappers, and unchanged child commands.
- `summary` produces per-process raw streams, `manifest.json`, and `summary.json`.
- `trace` also produces a valid Chrome Trace Event `trace.json` on macOS.
- The paired benchmark meets the 2 percent or 100 nanosecond allowance.
- Business status, state order, cleanup ownership, and safety validation remain unchanged.
- The task ledger lists retained evidence, archived evidence, and deletion candidates.
