# SO-101 Linux ros2_tracing implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional Linux `ros2_tracing` capture to the approved semantic profiling layer while keeping macOS, summary mode, graceful degradation, and the disabled path unchanged.

**Architecture:** A Linux-only adapter lazily discovers and imports `tracetools_launch.action.Trace`. Launch composition inserts the official `Trace` action before application processes only for `profiling=trace` on Linux. The semantic manifest records whether LTTng started, degraded, or was required and unavailable.

**Tech Stack:** Python 3.11, ROS 2 Jazzy, `ros2_tracing`, `tracetools_launch`, LTTng UST, Babeltrace 2, pytest, colcon, ai-station Linux runtime.

**Spec:** [`docs/superpowers/specs/2026-08-31-so101-cross-platform-profiling-design.md`](../specs/2026-08-31-so101-cross-platform-profiling-design.md)

## Global constraints

- Start only after every Phase 1 completion criterion in [`2026-08-31-so101-macos-semantic-profiling.md`](2026-08-31-so101-macos-semantic-profiling.md) passes and the macOS commits are present on `codex/so101-cross-platform-profiling`.
- Keep the public semantic span names and artifact schema unchanged.
- Never import `tracetools_launch`, call LTTng, or add a Trace action on macOS, in `summary` mode, or when profiling is off.
- Use the official Jazzy `tracetools_launch.action.Trace` API with its default ROS UST event set. Do not copy the default event list into this repository.
- Missing system tracing degrades only when `profiling_require_system_trace=false`. Required mode must fail during launch materialization, before simulator or robot processes start.
- Preserve unrelated files, tmux sessions, processes, and evidence on ai-station. Use unique runtime identifiers and stop only processes started by the validation run.
- Keep Linux evidence in a new run directory under `/data/work/so101-evidence/so101-cross-platform-profiling/<run-id>/`, register it in the same task ledger, and do not delete it without authorization.
- Use RED, GREEN, REFACTOR and `apply_patch`. Do not use `ament_uncrustify --reformat`.

## File map

| Path | Responsibility |
|---|---|
| `src/so101_demo_py/src/profiling/system_trace.py` | Platform and dependency discovery, lazy Trace construction, backend status |
| `src/so101_demo_py/src/profiling/launch_support.py` | Linux backend selection and semantic manifest metadata |
| `src/so101_demo_py/src/runtime/launch_composition.py` | Places Trace before owned application actions |
| `src/so101_demo_py/test/test_profiling_system_trace.py` | Platform matrix, lazy import, degradation, required failure |
| `src/so101_demo_py/test/test_profiling_launch_support.py` | Manifest integration and cross-platform regression |
| `src/so101_demo_py/test/test_text_pick_agent_launch.py` | Action ordering and unchanged off/summary process graph |

---

### Task 1: Implement lazy Linux backend discovery

**Files:**

- Create: `src/so101_demo_py/src/profiling/system_trace.py`
- Create: `src/so101_demo_py/test/test_profiling_system_trace.py`
- Modify: `src/so101_demo_py/src/profiling/__init__.py`

- [ ] **Step 1: Write the failing platform matrix tests**

Use injected `platform_name`, `find_spec`, and `import_module` functions. Cover this matrix:

| Mode | Platform | Dependency | Require | Result |
|---|---|---|---|---|
| `off` | Linux | present | either | disabled, no discovery or import |
| `summary` | Linux | present | either | semantic only, no discovery or import |
| `trace` | macOS | present | either | portable only, no discovery or import |
| `trace` | Linux | present | either | one Trace action |
| `trace` | Linux | missing | false | degraded status, no exception |
| `trace` | Linux | missing | true | preflight exception |
| `trace` | Linux | import fails | false | degraded status with error class |
| `trace` | Linux | import fails | true | preflight exception |

Include spies that fail if macOS, off, or summary mode calls `find_spec` or `import_module`.

- [ ] **Step 2: Run the focused test and confirm RED**

```bash
PYTHONPATH=/tmp/so101-debug-cross-platform-profiling-design-20260831/pythonpath \
  /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -q \
  src/so101_demo_py/test/test_profiling_system_trace.py
```

Expected: import failure for `so101_demo.profiling.system_trace`.

- [ ] **Step 3: Implement the backend result and lazy factory**

Use this public surface:

```python
@dataclass(frozen=True, slots=True)
class SystemTraceResult:
    status: Literal["disabled", "unsupported", "unavailable", "ready"]
    action: object | None
    backend: str | None
    output_path: Path | None
    error: str | None = None


class RequiredSystemTraceUnavailable(RuntimeError):
    pass


def build_system_trace(
    *,
    mode: ProfilingMode,
    require: bool,
    profiling_root: Path,
    session_id: str,
    platform_name: str = sys.platform,
    find_spec: Callable[[str], ModuleSpec | None] = importlib.util.find_spec,
    import_module: Callable[[str], ModuleType] = importlib.import_module,
) -> SystemTraceResult: ...
```

Return before dependency discovery unless `mode is TRACE` and `platform_name.startswith("linux")`.

- [ ] **Step 4: Construct the official action with verified Jazzy arguments**

Import `tracetools_launch.action` lazily and construct:

```python
trace_action = module.Trace(
    session_name=f"so101-{session_id}",
    append_timestamp=False,
    base_path=str(profiling_root / "ros2-tracing"),
)
```

Omit `events_ust` so Jazzy uses `tracetools_trace.tools.names.DEFAULT_EVENTS_ROS`. Omit kernel events and wrapper libraries from the first version.

- [ ] **Step 5: Run the focused tests and confirm GREEN**

- [ ] **Step 6: Commit backend discovery**

```bash
git add src/so101_demo_py/src/profiling/system_trace.py \
  src/so101_demo_py/src/profiling/__init__.py \
  src/so101_demo_py/test/test_profiling_system_trace.py
git commit -m "feat: add optional Linux ros2 tracing backend"
```

---

### Task 2: Insert Trace before application actions and record backend status

**Files:**

- Modify: `src/so101_demo_py/src/profiling/launch_support.py`
- Modify: `src/so101_demo_py/src/runtime/launch_composition.py`
- Modify: `src/so101_demo_py/test/test_profiling_launch_support.py`
- Modify: `src/so101_demo_py/test/test_text_pick_agent_launch.py`

- [ ] **Step 1: Write failing action-order and degradation tests**

With a fake Trace action, assert:

```python
actions = configured_text_agent_actions(..., profiling="trace", platform_name="linux")
assert actions[0] is fake_trace_action
assert index_of(actions, fake_trace_action) < index_of(actions, scene_setup_process)
```

Also assert:

- off and summary action lists are unchanged by identity and order;
- macOS trace contains no system action;
- missing dependency with `require=false` returns semantic actions and a warning;
- missing dependency with `require=true` raises before evidence subdirectories for owned processes or application actions are created;
- `manifest.json` records `backend.status`, `backend.name`, relative output path, and sanitized error class.

- [ ] **Step 2: Run the focused tests and confirm RED**

```bash
PYTHONPATH=/tmp/so101-debug-cross-platform-profiling-design-20260831/pythonpath \
  /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -q \
  src/so101_demo_py/test/test_profiling_launch_support.py \
  src/so101_demo_py/test/test_text_pick_agent_launch.py
```

- [ ] **Step 3: Add backend selection to launch support**

Resolve semantic configuration first, then call `build_system_trace`. Store the result in the launch profiling session. Return a separate `prefix_actions` tuple so the caller cannot accidentally place Trace after nodes.

- [ ] **Step 4: Prepend the Trace action**

In `_configured_text_pick_agent_actions`, build the current application actions exactly as Phase 1 does, then return:

```python
return [*profiling_session.prefix_actions, *application_actions]
```

The list is empty for off, summary, macOS trace, and degraded Linux trace.

- [ ] **Step 5: Link the CTF output in the manifest**

The portable finalizer receives backend metadata but does not parse CTF. It records a relative `ros2-tracing/so101-<session-id>` path only when the backend status is `ready`. It must not claim the CTF directory is complete until shutdown finalization sees it.

- [ ] **Step 6: Run the focused tests and confirm GREEN**

- [ ] **Step 7: Run macOS regression tests before committing**

```bash
PYTHONPATH=/tmp/so101-debug-cross-platform-profiling-design-20260831/pythonpath \
  /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -q \
  src/so101_demo_py/test/test_profiling_session.py \
  src/so101_demo_py/test/test_profiling_artifacts.py \
  src/so101_demo_py/test/test_profiling_system_trace.py \
  src/so101_demo_py/test/test_text_pick_agent_launch.py
```

Assert the import-spy tests still prove that macOS never imports `tracetools_launch`.

- [ ] **Step 8: Commit launch integration**

```bash
git add src/so101_demo_py/src/profiling/launch_support.py \
  src/so101_demo_py/src/runtime/launch_composition.py \
  src/so101_demo_py/test/test_profiling_launch_support.py \
  src/so101_demo_py/test/test_text_pick_agent_launch.py
git commit -m "feat: start ros2 tracing before SO-101 workflow"
```

---

### Task 3: Verify package tests and disabled performance on macOS

**Files:**

- Modify: `/tmp/so101-debug-cross-platform-profiling-design-20260831/task-ledger.md`
- No production files unless a new failing test demonstrates a regression.

- [ ] **Step 1: Run the full package suite**

```bash
PYTHONPATH=/tmp/so101-debug-cross-platform-profiling-design-20260831/pythonpath \
  ROS_LOG_DIR=/tmp/so101-debug-cross-platform-profiling-design-20260831/ros-logs-linux-code-macos \
  /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -q \
  src/so101_demo_py/test \
  --junitxml=/tmp/so101-debug-cross-platform-profiling-design-20260831/linux-code-macos-regression.xml
```

- [ ] **Step 2: Re-run the disabled benchmark**

```bash
PYTHONPATH=/tmp/so101-debug-cross-platform-profiling-design-20260831/pythonpath \
  /Users/matianyi/ros2_jazzy/.venv/bin/python3 \
  src/so101_demo_py/test/benchmark_profiling_off.py \
  > /tmp/so101-debug-cross-platform-profiling-design-20260831/linux-code-macos-off-benchmark.json
```

Expected: the same 2 percent or 100 nanosecond threshold passes. Confirm no `tracetools_launch` module appears in `sys.modules` during the macOS cases.

- [ ] **Step 3: Inspect diff and record evidence**

```bash
git diff --check
git status --short
```

Record return codes and artifact paths in the ledger.

---

### Task 4: Prepare a clean candidate overlay on ai-station

**Files:**

- Remote candidate checkout only. Do not edit unrelated remote files.
- Create: `/data/work/so101-evidence/so101-cross-platform-profiling/<run-id>/task-ledger.md`

- [ ] **Step 1: Inspect remote ownership and provenance before mutation**

On ai-station, record:

```bash
hostname
uname -a
git -C <remote-moveit-demo-checkout> status --short
git -C <remote-moveit-demo-checkout> rev-parse HEAD
git -C <remote-moveit-demo-checkout> submodule status
tmux list-sessions
pgrep -af 'ros2|gz sim|mujoco|move_group|controller_manager|lttng'
```

Do not reuse a dirty checkout, active tmux session, or another run's processes. Create an isolated worktree or clean candidate checkout from the exact local branch commit.

- [ ] **Step 2: Create and register one durable evidence run**

Choose a unique `<run-id>` and create:

```text
/data/work/so101-evidence/so101-cross-platform-profiling/<run-id>/
```

Record source commit, parent checkout, worktree path, `ROS_DOMAIN_ID`, `GZ_PARTITION`, start time, and process ownership. Add this root to the existing local task ledger as the Linux runtime evidence root.

- [ ] **Step 3: Check the tracing dependency without installing anything**

```bash
source /opt/ros/jazzy/setup.bash
ros2 pkg prefix tracetools
ros2 pkg prefix tracetools_launch
ros2 pkg prefix ros2trace
command -v lttng
command -v babeltrace2
python3 -c 'from tracetools_launch.action import Trace; print(Trace)'
```

Record each return code. If `tracetools_launch` is absent, check package availability with `apt-cache policy ros-jazzy-tracetools-launch ros-jazzy-ros2trace`. Installing system packages requires explicit user authorization. Do not replace the official backend with shell-managed LTTng.

- [ ] **Step 4: Build the exact candidate commit**

Use unique build, install, log, and ROS log directories inside the Linux evidence run. Build `so101_demo_py` and its necessary workspace dependencies with `colcon build --symlink-install`. Do not source an older shared install after the candidate overlay.

- [ ] **Step 5: Verify installed provenance**

After sourcing underlay then candidate overlay, record:

```bash
ros2 pkg prefix so101_demo_py
python3 -c 'import inspect, so101_demo.profiling; print(inspect.getfile(so101_demo.profiling))'
python3 -c 'from tracetools_launch.action import Trace; import inspect; print(inspect.getfile(Trace))'
ros2 launch so101_demo_py so101_mujoco_text_pick_agent.launch.py --show-args
```

The SO-101 prefix and module must resolve to the candidate install. The Trace module must resolve to the selected Jazzy tracing installation.

---

### Task 5: Run Linux degradation and required-backend acceptance

**Files:**

- Linux evidence root from Task 4
- No source edits unless a failing test reproduces the defect locally.

- [ ] **Step 1: Verify semantic summary without system tracing**

Run the safe dry-run or plan-only workflow with `profiling=summary`. Assert no LTTng session starts, semantic artifacts parse, and the business result is unchanged.

- [ ] **Step 2: Verify graceful degradation in an isolated environment**

Use a controlled Python/AMENT environment that hides `tracetools_launch` without renaming or deleting installed packages. Run `profiling=trace profiling_require_system_trace:=false`. Assert portable `summary.json` and `trace.json` exist, the manifest says `unavailable`, and the application path continues.

- [ ] **Step 3: Verify required-backend preflight failure**

In the same controlled environment, run `profiling=trace profiling_require_system_trace:=true`. Assert launch materialization fails before MuJoCo, ROS nodes, scene setup, or Text Agent processes start. Confirm no owned runtime PID exists after exit.

- [ ] **Step 4: Record exact commands and process cleanup**

Save stdout, stderr, environment identifiers without secrets, return codes, manifests, and process snapshots under the Linux evidence root.

---

### Task 6: Run a real ros2_tracing smoke test on ai-station

**Files:**

- Linux evidence root from Task 4
- No tracked source files unless a RED test requires a fix.

- [ ] **Step 1: Start from a clean tracing state**

List current sessions with `lttng list`. Do not destroy sessions owned by other users or runs. Use the unique session name `so101-<session-id>` and unique `ROS_DOMAIN_ID` and `GZ_PARTITION` values.

- [ ] **Step 2: Run the safe trace workflow**

Launch the installed candidate with:

```text
profiling:=trace
profiling_output_root:=<linux-run-evidence-root>
profiling_require_system_trace:=true
```

Use an existing dry-run or plan-only configuration. If the primary launch cannot exercise the desired stages without physical execution, validate launch plus system trace with a bounded scene setup and preview workflow. Do not weaken the execution gate.

- [ ] **Step 3: Validate semantic artifacts**

Check that `manifest.json`, `summary.json`, and `trace.json` parse; session IDs match; stable span names are present; backend status is `ready`; and the referenced `ros2-tracing/so101-<session-id>` directory exists.

- [ ] **Step 4: Validate CTF data with Babeltrace**

Run:

```bash
babeltrace2 <linux-run-evidence-root>/profiling/ros2-tracing/so101-<session-id>
```

Save a bounded event listing and counts. Require at least one ROS UST event from the candidate processes. Record the available event names rather than assuming a particular callback tracepoint exists.

- [ ] **Step 5: Validate clean shutdown**

After launch exits, assert:

- `lttng list` has no active `so101-<session-id>` session;
- every PID recorded for this run has exited;
- no owned MuJoCo, MoveIt, controller, RGB-D, or Text Agent process remains;
- unrelated pre-existing sessions and processes are unchanged.

- [ ] **Step 6: Run installed tests on Linux**

Run `colcon test --packages-select so101_demo_py` against the candidate build and save `colcon test-result --verbose`. Also run the focused pytest files if the package test configuration does not execute them all.

- [ ] **Step 7: Complete the evidence ledger**

Record retained runs, archived runs, and deletion candidates. Keep all current Linux runs retained unless the user authorizes cleanup.

---

### Task 7: Final branch verification

**Files:**

- No planned source changes
- Update both local and Linux task ledgers

- [ ] **Step 1: Verify branch state and commits**

```bash
git status --short
git diff --check
git log --oneline --decorate e7e0299cf8115214a0daf483cc40da6b09309091..HEAD
```

Expected: clean tracked worktree, no whitespace errors, and separate reviewable commits for semantic core, artifacts, wrappers, macOS integrations, benchmark, Linux backend, and Linux launch integration.

- [ ] **Step 2: Re-run the smallest complete acceptance set**

On macOS, run the full `src/so101_demo_py/test` suite and disabled benchmark. On Linux, retain the latest passing installed test result, semantic artifacts, CTF event listing, provenance, and cleanup snapshot.

- [ ] **Step 3: Review the public contract**

Confirm:

- defaults are `off`, empty output override, and `false` for required system tracing;
- summary behavior is identical across macOS and Linux;
- trace creates the portable timeline on both platforms;
- Linux adds CTF only when available;
- required mode fails before application start;
- off and macOS paths do not import `tracetools_launch`;
- no result schema, safety rule, state transition, or physical acceptance rule changed.

## Phase 2 completion criteria

- Every Phase 1 criterion still passes.
- Linux trace mode places the official `Trace` action before application actions.
- The backend uses the Jazzy default ROS UST events and writes CTF below the profiling root.
- Degraded and required-backend behaviors match the approved launch contract.
- ai-station evidence proves candidate source and installed provenance, semantic artifacts, at least one ROS UST event, and clean owned-process shutdown.
- The final branch diff is clean and the evidence ledgers list retained runs, archived runs, and deletion candidates.
