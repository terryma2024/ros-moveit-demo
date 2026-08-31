# Text Agent RGB-D 端到端 Launch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一个 MuJoCo launch，用一条命令启动 Text Agent、RGB-D 感知、动态摘取和整套 motion stack，并在本机 Mac 上证明四个预制点位各自独立抓取成功。

**Architecture:** 新入口复用现有 MuJoCo perception launch 的 stack、RGB-D 节点、证据目录和 fail-closed 生命周期，只把直接 `dynamic_cup_pick_place` 工作流替换为 `text_pick_agent --mode execute --execute --skip-confirmation`。新增 canonical installed execution identity resolver，使 launch 自动传入与当前工作目录无关的 source commit 和 ament package prefix；DeepSeek 与 Ollama 保持为 launch 外部服务。

**Tech Stack:** ROS 2 Jazzy launch/launch_ros、Python 3、pytest、ament index、MoveIt 2、MuJoCo、`mujoco_ros2_control`、RGB-D image transport、tf2、DeepSeek HTTPS API、Ollama `qwen3.5:4b`。

**Spec:** `docs/superpowers/specs/2026-08-31-text-agent-rgbd-e2e-launch-design.md`

## Global Constraints

- 只支持 MuJoCo 仿真，不增加 Gazebo 或真实机械臂入口。
- 执行必须同时满足 `run_mode:=execute`、`execute:=true`、`skip_confirmation:=true`；任一缺失都不得物化 ROS 节点。
- `sensor_rendering` 固定为 `true`；四个 keyframe 只能是 `task_start`、`cup_test_forward_5cm`、`cup_test_left_5cm`、`cup_test_right_5cm`。
- 每次计数运行都使用新的 session、request、evidence stem、ROS log 目录和独立 `FULL_RESTART` stack；不得用 `RESET_WORLD` 混算。
- launch 只管理自己启动的进程，不停止或复用未知所有权的 MuJoCo、MoveIt、RGB-D、tmux 或 Ollama 进程。
- `DEEPSEEK_API_KEY` 只从进程环境继承；日志不得输出 API key、完整环境变量或未经过滤的模型响应。
- README 只能写英文；中文 guide 使用 `humanizer-zh`，英文 README 使用 `humanizer`，技术字面量保持不变。
- 本任务唯一登记证据根为 `/tmp/so101-debug-text-agent-e2e-launch-20260831/`；不删除任何证据。
- 不运行 `ament_uncrustify --reformat`。

---

### Task 1: Canonical installed execution identity

**Files:**
- Modify: `src/so101_demo_py/src/runtime/provenance.py`
- Modify: `src/so101_demo_py/test/test_text_agent_execution_provenance.py`

**Interfaces:**
- Consumes: `so101_demo.application.text_agent.__file__` and `ament_index_python.packages.get_package_prefix("so101_demo_py")`.
- Produces: `InstalledExecutionIdentity(source_commit: str, package_prefix: str)` and `resolve_installed_execution_identity() -> InstalledExecutionIdentity`.
- Preserves: `verify_execution_provenance(...) -> ExecutionProvenance` and its existing stable reason codes.

- [ ] **Step 1: Write the cwd-independence RED test**

Add this test and the required imports:

```python
def test_resolve_installed_execution_identity_is_cwd_independent(
    tmp_path: Path, monkeypatch
) -> None:
    from ament_index_python.packages import get_package_prefix
    from so101_demo.application import text_agent as runtime_module
    from so101_demo.runtime.provenance import resolve_installed_execution_identity

    monkeypatch.chdir(tmp_path)
    identity = resolve_installed_execution_identity()

    module_path = Path(runtime_module.__file__).resolve(strict=True)
    expected_commit = subprocess.run(
        ["git", "-C", str(module_path.parent), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().lower()
    assert identity.source_commit == expected_commit
    assert identity.package_prefix == str(
        Path(get_package_prefix("so101_demo_py")).resolve(strict=True)
    )
```

- [ ] **Step 2: Run the focused test and observe RED**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q \
  src/so101_demo_py/test/test_text_agent_execution_provenance.py \
  -k cwd_independent
```

Expected: collection or import fails because `resolve_installed_execution_identity` does not exist.

- [ ] **Step 3: Add the resolver and make verification consume it**

Add this immutable value object and resolver to `provenance.py`:

```python
@dataclass(frozen=True, slots=True)
class InstalledExecutionIdentity:
    source_commit: str
    package_prefix: str


def resolve_installed_execution_identity() -> InstalledExecutionIdentity:
    from ament_index_python.packages import get_package_prefix
    from ..application import text_agent as runtime_module

    try:
        module_path = Path(runtime_module.__file__).resolve(strict=True)
    except (OSError, RuntimeError, TypeError):
        raise ExecutionProvenanceError(
            "EXECUTION_SOURCE_PROVENANCE_UNAVAILABLE"
        ) from None
    try:
        package_prefix = Path(get_package_prefix("so101_demo_py")).resolve(strict=True)
    except (LookupError, OSError, RuntimeError):
        raise ExecutionProvenanceError(
            "EXECUTION_PACKAGE_PREFIX_UNAVAILABLE"
        ) from None
    return InstalledExecutionIdentity(
        source_commit=_resolved_source_commit(module_path),
        package_prefix=str(package_prefix),
    )
```

Change `verify_execution_provenance()` to call this resolver once and compare the declared prefix and commit with its fields. Resolve `runtime_module.__file__` separately for the existing module-artifact hash. Preserve `EXECUTION_PACKAGE_PREFIX_UNAVAILABLE`, `EXECUTION_INSTALLED_PREFIX_MISMATCH`, and `EXECUTION_SOURCE_COMMIT_MISMATCH` exactly.

- [ ] **Step 4: Run the provenance suite and observe GREEN**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q \
  src/so101_demo_py/test/test_text_agent_execution_provenance.py \
  src/so101_demo_py/test/test_text_pick_agent_cli.py
```

Expected: all tests pass, including the new test from a non-Git cwd.

- [ ] **Step 5: Commit the identity resolver**

```bash
git add -- \
  src/so101_demo_py/src/runtime/provenance.py \
  src/so101_demo_py/test/test_text_agent_execution_provenance.py
git diff --cached --check
git commit -m "feat(text-agent): resolve installed execution identity"
```

---

### Task 2: Public launch contract and fail-closed preflight

**Files:**
- Create: `src/so101_demo_py/launch/so101_mujoco_text_pick_agent.launch.py`
- Create: `src/so101_demo_py/test/test_text_pick_agent_launch.py`
- Modify: `src/so101_demo_py/src/runtime/launch_composition.py`

**Interfaces:**
- Consumes: `MUJOCO_CUP_KEYFRAMES`, `_positive_finite_launch_value()`, `_prepare_perception_evidence_root()`, and `resolve_installed_execution_identity()`.
- Produces: `build_text_pick_agent_launch_description(exit_status: PerceptionLaunchExitStatus | None = None) -> LaunchDescription` and `_configured_text_pick_agent_actions(context, *, exit_status)`.
- Public launch: `ros2 launch so101_demo_py so101_mujoco_text_pick_agent.launch.py`.

- [ ] **Step 1: Write the thin-entry and argument RED tests**

Start `test_text_pick_agent_launch.py` with materialization helpers equivalent to the existing perception-launch test, then add:

```python
def test_public_text_agent_launch_is_thin_and_declares_contract() -> None:
    description = launch_composition.build_text_pick_agent_launch_description()
    declared = _declared(description)

    assert {
        "instruction",
        "run_mode",
        "execute",
        "skip_confirmation",
        "headless",
        "sensor_rendering",
        "session_id",
        "evidence_file",
        "readiness_timeout_s",
        "mujoco_scene",
        "mujoco_initial_keyframe",
        "perception_startup_timeout_s",
        "cup_pose_timeout_s",
    } == declared.keys()
    assert _default(declared["run_mode"]) == "dry_run"
    assert _default(declared["execute"]) == "false"
    assert _default(declared["skip_confirmation"]) == "false"
    assert _default(declared["headless"]) == "false"
    assert _default(declared["sensor_rendering"]) == "true"
    assert _default(declared["mujoco_initial_keyframe"]) == "task_start"

    source = LAUNCH_PATH.read_text(encoding="utf-8")
    assert "DeclareLaunchArgument" not in source
    assert "build_text_pick_agent_launch_description" in source
```

The helper must inject the concrete instruction `Pick the plastic cup. Apply no constraints.` before executing the `OpaqueFunction`; it must use a temporary `evidence_file` and monkeypatch `resolve_installed_execution_identity()` to return commit `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` and prefix `/tmp/so101-text-agent-install`.

- [ ] **Step 2: Write the authorization and input RED matrix**

Add a parameterized test for these exact failures:

```python
@pytest.mark.parametrize(
    ("overrides", "message"),
    (
        ({"instruction": ""}, "instruction"),
        ({"run_mode": "dry_run"}, "run_mode=execute"),
        ({"execute": "false"}, "execute:=true"),
        ({"skip_confirmation": "false"}, "skip_confirmation:=true"),
        ({"sensor_rendering": "false"}, "sensor_rendering=true"),
        ({"headless": "sometimes"}, "headless"),
        ({"mujoco_initial_keyframe": "unknown"}, "initial keyframe"),
        ({"readiness_timeout_s": "0"}, "readiness_timeout_s"),
        ({"perception_startup_timeout_s": "inf"}, "perception_startup_timeout_s"),
        ({"cup_pose_timeout_s": "nan"}, "cup_pose_timeout_s"),
        ({"session_id": "../escape"}, "session_id"),
        ({"evidence_file": "relative.json"}, "evidence_file"),
        ({"mujoco_scene": "relative.xml"}, "mujoco_scene"),
    ),
)
def test_invalid_text_agent_inputs_fail_before_nodes_or_evidence(
    tmp_path: Path, overrides: dict[str, str], message: str
) -> None:
    evidence_file = tmp_path / "run.json"
    with pytest.raises(RuntimeError, match=message):
        _materialize(evidence_file=evidence_file, **overrides)
    assert not (tmp_path / "run.d").exists()
```

- [ ] **Step 3: Run the new file and observe RED**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q \
  src/so101_demo_py/test/test_text_pick_agent_launch.py
```

Expected: import fails because the builder and launch file do not exist.

- [ ] **Step 4: Implement the thin public file and preflight**

The new launch file contains only:

```python
"""MuJoCo natural-language RGB-D dynamic pick-place launcher."""

from so101_demo.runtime.launch_composition import (
    build_text_pick_agent_launch_description,
)


def generate_launch_description():
    return build_text_pick_agent_launch_description()
```

In `launch_composition.py`, declare the exact public arguments from the test. `instruction` has no default. `sensor_rendering` uses `choices=("true",)`. `_configured_text_pick_agent_actions()` validates all strings and paths before calling `resolve_installed_execution_identity()` and before `_prepare_perception_evidence_root()`; only then does it call `_mujoco_text_pick_agent_execute_actions()`.

Use these fixed preflight checks:

```python
if run_mode != "execute":
    raise RuntimeError("text-agent launch requires run_mode=execute")
if execute != "true":
    raise RuntimeError("text-agent launch requires execute:=true")
if skip_confirmation != "true":
    raise RuntimeError("text-agent launch requires skip_confirmation:=true")
if sensor_rendering != "true":
    raise RuntimeError("text-agent launch requires sensor_rendering=true")
if not instruction.strip():
    raise RuntimeError("instruction must be non-empty")
```

- [ ] **Step 5: Run the launch-contract tests and observe GREEN**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q \
  src/so101_demo_py/test/test_text_pick_agent_launch.py \
  -k 'public or invalid'
```

Expected: all selected tests pass and invalid inputs leave no `run.d` directory.

- [ ] **Step 6: Commit the public contract**

```bash
git add -- \
  src/so101_demo_py/launch/so101_mujoco_text_pick_agent.launch.py \
  src/so101_demo_py/src/runtime/launch_composition.py \
  src/so101_demo_py/test/test_text_pick_agent_launch.py
git diff --cached --check
git commit -m "feat(text-agent): add RGB-D launch contract"
```

---

### Task 3: Text Agent workflow graph and lifecycle ownership

**Files:**
- Modify: `src/so101_demo_py/src/runtime/launch_composition.py`
- Modify: `src/so101_demo_py/test/test_text_pick_agent_launch.py`
- Verify unchanged: `src/so101_demo_py/test/test_perception_pick_place_launch.py`

**Interfaces:**
- Consumes: `_mujoco_stack_actions()`, `camera_static_transform_nodes()`, `perception_pick_place_exit_handlers()`, `_PerceptionEvidencePaths`, and `InstalledExecutionIdentity`.
- Produces: `_mujoco_text_pick_agent_execute_actions(context, share, session_id, *, instruction, evidence_paths, perception_timeout, cup_pose_timeout, execution_identity, exit_status)`.
- Starts after successful scene setup: one `rgbd_cup_pose` and one `text_pick_agent`.

- [ ] **Step 1: Write the exact-node RED test**

Add a test that dispatches `scene_setup` exit 0 and asserts the two resulting nodes. The Text Agent arguments must be exactly:

```python
assert workflow._Node__arguments == [
    "--instruction",
    "Pick the plastic cup. Apply no constraints.",
    "--mode",
    "execute",
    "--execute",
    "--skip-confirmation",
    "--backend",
    "mujoco",
    "--cup-pose-timeout-s",
    "45.0",
    "--session-id",
    "text-e2e-session-001",
    "--expected-reset-epoch",
    "0",
    "--evidence-root",
    str(tmp_path / "run.d/text-e2e-session-001/dynamic"),
    "--source-commit",
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "--installed-prefix",
    "/tmp/so101-text-agent-install",
]
```

Assert the perception node still writes `perception/cup.ply` and `perception/summary.json`, both nodes use `use_sim_time=True` where applicable, and no `dynamic_cup_pick_place`, `cup_pose_tf_demo`, or `mujoco_cup_pose_bridge` node appears.

- [ ] **Step 2: Write lifecycle RED tests**

Cover these exact cases with `_dispatch_process_exit()`:

- scene setup exit 12 starts neither perception nor Text Agent and fails the launch;
- RGB-D exit 0 or 9 before Text Agent completion is terminal;
- MuJoCo, robot state publisher, MoveIt, or camera static TF early exit is terminal;
- controller spawner exit 0 is accepted, while exit 19 is terminal;
- Text Agent exit 0 marks workflow terminal and ignores later owned teardown `-15` exits;
- Text Agent exit 23 preserves return code 23 and fails launch;
- the first nonzero terminal child status wins.

Use the expected workflow reason strings `Text Agent RGB-D workflow completed with exit code 0` and `Text Agent RGB-D workflow failed with exit code 23`.

- [ ] **Step 3: Run the graph tests and observe RED**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q \
  src/so101_demo_py/test/test_text_pick_agent_launch.py \
  -k 'scene or workflow or required or spawner or terminal'
```

Expected: node and lifecycle assertions fail because the production graph is not yet present.

- [ ] **Step 4: Implement the graph with a reusable workflow label**

Create the RGB-D node with the existing perception arguments and the Text Agent node with the exact arguments above. Extend `perception_pick_place_exit_handlers()` with a keyword-only parameter:

```python
def perception_pick_place_exit_handlers(
    scene_setup,
    perception,
    workflow,
    *,
    required_long_lived: tuple[tuple[str, object], ...],
    successful_one_shots: tuple[tuple[str, object], ...],
    exit_status: PerceptionLaunchExitStatus,
    workflow_label: str = "Dynamic perception workflow",
):
```

Use `workflow_label` only in workflow completion/failure reasons. Existing perception callers omit it and retain byte-for-byte reason text; the new caller passes `workflow_label="Text Agent RGB-D workflow"`.

The required long-lived set is MuJoCo, `robot_state_publisher`, MoveIt, both camera TF nodes, and RGB-D perception. The three controller spawners remain successful one-shots. `scene_setup` success returns `[perception, workflow]`.

- [ ] **Step 5: Run both launch suites and observe GREEN**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q \
  src/so101_demo_py/test/test_text_pick_agent_launch.py \
  src/so101_demo_py/test/test_perception_pick_place_launch.py
```

Expected: both suites pass; the old perception launch behavior remains unchanged.

- [ ] **Step 6: Commit the owned lifecycle graph**

```bash
git add -- \
  src/so101_demo_py/src/runtime/launch_composition.py \
  src/so101_demo_py/test/test_text_pick_agent_launch.py
git diff --cached --check
git commit -m "feat(text-agent): compose owned RGB-D workflow"
```

---

### Task 4: Installed resource contract and operator documentation

**Files:**
- Modify: `src/so101_demo_py/test/test_package_identity.py`
- Modify: `src/so101_demo_py/test/test_installed_provenance.py`
- Modify: `src/so101_demo_py/README.md`
- Modify: `docs/so101-text-pick-agent-source-guide.md`

**Interfaces:**
- Consumes: the public launch arguments from Task 2 and runtime ownership from Task 3.
- Produces: an installed `share/so101_demo_py/launch/so101_mujoco_text_pick_agent.launch.py`, an English README entry, and a Chinese one-command operating section.

- [ ] **Step 1: Write installed-resource RED assertions**

Add this assertion to `test_package_identity.py`:

```python
assert "launch/so101_mujoco_text_pick_agent.launch.py" in installed_files
```

Add `"so101_mujoco_text_pick_agent.launch.py"` to `EXPECTED_LAUNCHERS` in `test_installed_provenance.py`.

- [ ] **Step 2: Run resource tests and observe RED**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q \
  src/so101_demo_py/test/test_package_identity.py \
  src/so101_demo_py/test/test_installed_provenance.py \
  -k 'publishes or final_install'
```

Expected: the source-resource assertion passes after Task 2, while the installed overlay assertion fails until the package is rebuilt in Task 5.

- [ ] **Step 3: Update the English README with the actual launch contract**

Use `humanizer` before editing. Change “six launch files” to “seven launch files”, add the new launch to the workflow table and launch catalog, and add this minimal command:

```bash
ros2 launch so101_demo_py so101_mujoco_text_pick_agent.launch.py \
  instruction:="Pick the plastic cup. Apply no constraints." \
  run_mode:=execute \
  execute:=true \
  skip_confirmation:=true \
  headless:=false \
  sensor_rendering:=true \
  mujoco_initial_keyframe:=task_start \
  session_id:=text-rgbd-task-start-001 \
  evidence_file:="$SO101_EVIDENCE_ROOT/text-rgbd-task-start-001.json"
```

State directly that the launch owns MuJoCo, controllers, MoveIt, scene setup, camera TF, RGB-D perception, Text Agent, and cleanup; it inherits but does not own DeepSeek/Ollama. State that it accepts only direct execute with `skip_confirmation:=true`; reviewed digest execution still uses the two-step CLI documented in the guide.

- [ ] **Step 4: Add the one-command path to the Chinese source guide**

Use `humanizer-zh` before editing. Keep §19.1 for the reviewed Preview/digest workflow and §19.2 for direct CLI execution. Add §19.3 “用一个 launch 启动整条链路” with the same command, plus these boundaries:

- `instruction`、三重执行授权、keyframe、session 和 evidence file 由操作者给出；
- source commit、installed prefix、reset epoch 和 dynamic evidence root 由 launch 自动传入；
- DeepSeek/Ollama 是外部服务，launch 不负责启动或停止；
- Text Agent 结束后，launch 只清理本轮拥有的 ROS/MuJoCo 进程；
- Preview/digest 路径不使用这个 launch。

Link the launch source and `build_text_pick_agent_launch_description()` using repository-relative links.

- [ ] **Step 5: Run documentation and resource checks**

Run:

```bash
rg -n "so101_mujoco_text_pick_agent|seven launch files" \
  src/so101_demo_py/README.md \
  docs/so101-text-pick-agent-source-guide.md
git diff --check
```

Expected: README prose is English, the guide prose is Chinese, and both show the same executable command and ownership boundary.

- [ ] **Step 6: Commit resource and documentation changes**

```bash
git add -- \
  src/so101_demo_py/test/test_package_identity.py \
  src/so101_demo_py/test/test_installed_provenance.py \
  src/so101_demo_py/README.md \
  docs/so101-text-pick-agent-source-guide.md
git diff --cached --check
git commit -m "docs(text-agent): document RGB-D end-to-end launch"
```

---

### Task 5: Source tests, fresh install, and installed launch smoke tests

**Files:**
- Modify: `docs/experiments/text-agent-rgbd-e2e-launch-experiment-ledger.md`
- Evidence: `/tmp/so101-debug-text-agent-e2e-launch-20260831/static/`

**Interfaces:**
- Consumes: all source and tests from Tasks 1–4.
- Produces: a freshly built local overlay whose installed launch is discoverable and fails closed before runtime when authorization is incomplete.

- [ ] **Step 1: Run focused and full source tests**

```bash
set -o pipefail
mkdir -p /tmp/so101-debug-text-agent-e2e-launch-20260831/static
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q \
  src/so101_demo_py/test/test_text_agent_execution_provenance.py \
  src/so101_demo_py/test/test_text_pick_agent_launch.py \
  src/so101_demo_py/test/test_perception_pick_place_launch.py \
  src/so101_demo_py/test/test_package_identity.py \
  2>&1 | tee /tmp/so101-debug-text-agent-e2e-launch-20260831/static/focused-pytest.log
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q src/so101_demo_py/test \
  2>&1 | tee /tmp/so101-debug-text-agent-e2e-launch-20260831/static/full-pytest.log
```

Expected: nonzero tests are collected and all pass. If either command fails, invoke `superpowers:systematic-debugging`, preserve the logs, and fix only the first proven boundary before rerunning.

- [ ] **Step 2: Build and source the candidate overlay**

```zsh
source /Users/matianyi/ros2_jazzy/.venv/bin/activate
source /Users/matianyi/ros2_jazzy/extra_ws/install/setup.zsh
colcon build --packages-select so101_demo_py --symlink-install \
  --event-handlers console_direct+ \
  2>&1 | tee /tmp/so101-debug-text-agent-e2e-launch-20260831/static/colcon-build.log
source install/setup.zsh
```

Expected: build exits 0 and `ros2 pkg prefix so101_demo_py` resolves to this repository’s `install/so101_demo_py`.

- [ ] **Step 3: Verify installed resources and exact arguments**

```zsh
ros2 pkg prefix so101_demo_py | tee \
  /tmp/so101-debug-text-agent-e2e-launch-20260831/static/package-prefix.log
ros2 launch so101_demo_py so101_mujoco_text_pick_agent.launch.py --show-args \
  2>&1 | tee /tmp/so101-debug-text-agent-e2e-launch-20260831/static/show-args.log
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/so101_demo_py/test/test_installed_provenance.py \
  2>&1 | tee /tmp/so101-debug-text-agent-e2e-launch-20260831/static/installed-provenance.log
```

Expected: the launch appears in installed share, all 13 arguments appear, and installed provenance tests pass.

- [ ] **Step 4: Prove incomplete authorization has no runtime side effects**

Use an isolated ROS domain and task-owned ROS logs:

```zsh
export ROS_DOMAIN_ID=221
export ROS_HOME=/tmp/so101-debug-text-agent-e2e-launch-20260831/static/ros-home
export ROS_LOG_DIR=/tmp/so101-debug-text-agent-e2e-launch-20260831/static/ros-log
mkdir -p "$ROS_HOME" "$ROS_LOG_DIR"
ros2 launch so101_demo_py so101_mujoco_text_pick_agent.launch.py \
  instruction:="Pick the plastic cup. Apply no constraints." \
  run_mode:=execute execute:=true skip_confirmation:=false \
  evidence_file:=/tmp/so101-debug-text-agent-e2e-launch-20260831/static/rejected.json \
  2>&1 | tee /tmp/so101-debug-text-agent-e2e-launch-20260831/static/rejected-launch.log
test ! -e /tmp/so101-debug-text-agent-e2e-launch-20260831/static/rejected.d
ros2 node list | tee \
  /tmp/so101-debug-text-agent-e2e-launch-20260831/static/domain-221-nodes.log
```

Expected: launch exits nonzero with `skip_confirmation:=true`, creates no evidence run directory, and domain 221 has no nodes.

- [ ] **Step 5: Record the static checkpoint and commit it**

Add `CP-STATIC-GREEN` to the experiment ledger with source commit, installed prefix, test counts, `show-args` log, rejected-launch reason, retained evidence paths, and no cleanup candidates.

```bash
git add -- docs/experiments/text-agent-rgbd-e2e-launch-experiment-ledger.md
git diff --cached --check
git commit -m "test(text-agent): record launch static acceptance"
```

---

### Task 6: Four independent Mac FULL_RESTART acceptance runs

**Files:**
- Modify: `docs/experiments/text-agent-rgbd-e2e-launch-experiment-ledger.md`
- Evidence: `/tmp/so101-debug-text-agent-e2e-launch-20260831/macos/`

**Interfaces:**
- Consumes: the installed candidate from Task 5, `~/.env`, local Ollama, exact-window `gui-capture`, and the four installed MuJoCo keyframes.
- Produces: four qualified independent runs with text-agent, RGB-D, controller, MoveIt, physical, visual, exit, provenance, and cleanup evidence.

- [ ] **Step 1: Recheck ownership and provider health without exposing secrets**

```zsh
mkdir -p /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/preflight
ps -axo pid,ppid,lstart,command | \
  rg 'ros2 launch|ros2_control_node|move_group|rgbd_cup_pose|text_pick_agent' | \
  tee /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/preflight/processes.log
set -a
source "$HOME/.env" >/dev/null 2>&1
env_load_exit=$?
set +a
test "$env_load_exit" -eq 0
[[ -n ${DEEPSEEK_API_KEY:-} ]] && print 'DEEPSEEK_API_KEY=SET' || print 'DEEPSEEK_API_KEY=UNSET'
ollama list | grep 'qwen3.5:4b' | \
  tee /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/preflight/ollama-model.log
```

Do not stop the previously observed PID 79408 tree unless current parent/session evidence proves it belongs to this task. The four new runs use isolated domains 222–225, so an unrelated stack in another domain is preserved. Fast DDS on this Mac rejects domain IDs above 232.

- [ ] **Step 2: Run `task_start` as a fresh owned stack**

Run the launch in terminal A. Use terminal B for window inventory and capture while terminal A is still active; do not wait for terminal A to return before looking up the Viewer.

```zsh
set -o pipefail
export ROS_DOMAIN_ID=222
export ROS_HOME=/tmp/so101-debug-text-agent-e2e-launch-20260831/macos/task_start/ros-home
export ROS_LOG_DIR=/tmp/so101-debug-text-agent-e2e-launch-20260831/macos/task_start/ros-log
mkdir -p "$ROS_HOME" "$ROS_LOG_DIR" \
  /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/task_start/gui
ros2 launch so101_demo_py so101_mujoco_text_pick_agent.launch.py \
  instruction:="Pick the plastic cup. Apply no constraints." \
  run_mode:=execute execute:=true skip_confirmation:=true \
  headless:=false sensor_rendering:=true \
  mujoco_initial_keyframe:=task_start \
  session_id:=text-e2e-task-start-20260831 \
  evidence_file:=/tmp/so101-debug-text-agent-e2e-launch-20260831/macos/task_start/run.json \
  2>&1 | tee /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/task_start/launch.log
```

While the run is active, list windows, select the exact visible layer-zero MuJoCo Viewer ID, and use `capture-gui.sh --local --window-id` to capture a fresh frame immediately after the log’s terminal `DONE` transition. Store the helper JSON manifest and PNG under `macos/task_start/gui/`, then inspect the original-resolution PNG.

```zsh
.agents/skills/gui-capture/scripts/capture-gui.sh --local --list-windows \
  2> /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/task_start/gui/window-list.stderr | \
  tee /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/task_start/gui/window-list.json
.agents/skills/gui-capture/scripts/capture-gui.sh --local \
  --window-id "$MUJOCO_WINDOW_ID" \
  --output-root /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/task_start/gui \
  2> /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/task_start/gui/capture.stderr | \
  tee /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/task_start/gui/capture.json
```

Set `MUJOCO_WINDOW_ID` only after the inventory shows one unambiguous current MuJoCo Viewer window with matching PID, title, bounds, and current run timing.

- [ ] **Step 3: Run `cup_test_forward_5cm` as a fresh owned stack**

```zsh
set -o pipefail
export ROS_DOMAIN_ID=223
export ROS_HOME=/tmp/so101-debug-text-agent-e2e-launch-20260831/macos/cup_test_forward_5cm/ros-home
export ROS_LOG_DIR=/tmp/so101-debug-text-agent-e2e-launch-20260831/macos/cup_test_forward_5cm/ros-log
mkdir -p "$ROS_HOME" "$ROS_LOG_DIR" \
  /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/cup_test_forward_5cm/gui
ros2 launch so101_demo_py so101_mujoco_text_pick_agent.launch.py \
  instruction:="Pick the plastic cup. Apply no constraints." \
  run_mode:=execute execute:=true skip_confirmation:=true \
  headless:=false sensor_rendering:=true \
  mujoco_initial_keyframe:=cup_test_forward_5cm \
  session_id:=text-e2e-forward-20260831 \
  evidence_file:=/tmp/so101-debug-text-agent-e2e-launch-20260831/macos/cup_test_forward_5cm/run.json \
  2>&1 | tee /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/cup_test_forward_5cm/launch.log
```

List windows again, resolve the new Viewer ID, and capture it under `macos/cup_test_forward_5cm/gui/`; do not reuse the Step 2 ID.

- [ ] **Step 4: Run `cup_test_left_5cm` as a fresh owned stack**

```zsh
set -o pipefail
export ROS_DOMAIN_ID=224
export ROS_HOME=/tmp/so101-debug-text-agent-e2e-launch-20260831/macos/cup_test_left_5cm/ros-home
export ROS_LOG_DIR=/tmp/so101-debug-text-agent-e2e-launch-20260831/macos/cup_test_left_5cm/ros-log
mkdir -p "$ROS_HOME" "$ROS_LOG_DIR" \
  /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/cup_test_left_5cm/gui
ros2 launch so101_demo_py so101_mujoco_text_pick_agent.launch.py \
  instruction:="Pick the plastic cup. Apply no constraints." \
  run_mode:=execute execute:=true skip_confirmation:=true \
  headless:=false sensor_rendering:=true \
  mujoco_initial_keyframe:=cup_test_left_5cm \
  session_id:=text-e2e-left-20260831 \
  evidence_file:=/tmp/so101-debug-text-agent-e2e-launch-20260831/macos/cup_test_left_5cm/run.json \
  2>&1 | tee /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/cup_test_left_5cm/launch.log
```

List windows again, resolve the new Viewer ID, and capture it under `macos/cup_test_left_5cm/gui/`; do not reuse an earlier ID.

- [ ] **Step 5: Run `cup_test_right_5cm` as a fresh owned stack**

```zsh
set -o pipefail
export ROS_DOMAIN_ID=225
export ROS_HOME=/tmp/so101-debug-text-agent-e2e-launch-20260831/macos/cup_test_right_5cm/ros-home
export ROS_LOG_DIR=/tmp/so101-debug-text-agent-e2e-launch-20260831/macos/cup_test_right_5cm/ros-log
mkdir -p "$ROS_HOME" "$ROS_LOG_DIR" \
  /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/cup_test_right_5cm/gui
ros2 launch so101_demo_py so101_mujoco_text_pick_agent.launch.py \
  instruction:="Pick the plastic cup. Apply no constraints." \
  run_mode:=execute execute:=true skip_confirmation:=true \
  headless:=false sensor_rendering:=true \
  mujoco_initial_keyframe:=cup_test_right_5cm \
  session_id:=text-e2e-right-20260831 \
  evidence_file:=/tmp/so101-debug-text-agent-e2e-launch-20260831/macos/cup_test_right_5cm/run.json \
  2>&1 | tee /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/cup_test_right_5cm/launch.log
```

List windows again, resolve the new Viewer ID, and capture it under `macos/cup_test_right_5cm/gui/`; do not reuse an earlier ID.

- [ ] **Step 6: Evaluate every run against the joint acceptance gate**

For each of the four directories, record all of these facts in the ledger:

- actual planner `provider`, `model`, `fallback_used`, request ID, validated `TaskCommand`, and `confirmation_mode=skipped`;
- RGB, depth, and CameraInfo dimensions/encodings plus a finite positive depth count;
- fresh `world` `/cup_pose` session/reset provenance consumed by dynamic runtime;
- all 19 dynamic transitions and nonempty controller action/joint/TCP evidence;
- cup lift, transport, release, target-region stability, `table_contact=true`, and no fingertip contact;
- empty MoveIt attached-object IDs and `plastic_cup` restored to world objects;
- exact-window GUI manifest whose capture time and Viewer identity belong to that run;
- launch exit 0 and no remaining nodes/processes owned by that session/domain.

If any fact is missing, mark the point invalid, preserve the run, fix only the first proven boundary, and repeat that point with a new session/evidence directory. An invalid run never enters the 4/4 denominator.

- [ ] **Step 7: Run final regression and commit the acceptance ledger**

Invoke `superpowers:verification-before-completion`, then run:

```bash
PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q src/so101_demo_py/test
git diff --check
git status --short --branch
```

Update the ledger with the four retained qualified run roots, any retained invalid attempts, archived runs (`NONE` unless explicitly moved), deletion candidates (`NONE` unless separately authorized), final source commit, installed prefix, and owned cleanup result.

```bash
git add -- docs/experiments/text-agent-rgbd-e2e-launch-experiment-ledger.md
git diff --cached --check
git commit -m "test(text-agent): qualify four RGB-D pick positions"
```

Expected final claim: exactly four independent qualified Mac `FULL_RESTART` runs pass the joint gate; source/install provenance and owned cleanup are current. Do not push or merge unless the user requests it after reviewing the result.
