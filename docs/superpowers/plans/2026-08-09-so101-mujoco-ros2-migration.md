# SO-101 MuJoCo ROS 2 Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前 `so101_gazebo_demo_py` 渐进迁移为独立的 `so101_mujoco_demo_py`，保留 ROS 2 Jazzy、MoveIt 2、控制器、状态机和物理结果契约，以 MuJoCo 和 `mujoco_ros2_control` 0.0.3 替换 Gazebo。

**Architecture:** 先把 Gazebo observer/reset 收敛到 backend-neutral Python protocol，再加入仓库内 MJCF、`mujoco_ros2_control` launch 与一个最小 `ament_cmake` 原子仿真证据插件。MoveIt Planning Scene attachment 继续只做 collision shadow；MuJoCo 中不创建抓取约束。通过 model/control/reset/contact/physical outcome 分层门槛和两组连续成功后，删除 Gazebo backend 并改公开 package 名。

**Tech Stack:** Ubuntu 24.04、ROS 2 Jazzy、Python 3.12、`ament_python`、`rclpy`、MoveIt 2、`ros2_control`、`mujoco_vendor 0.0.8`、`mujoco_ros2_control 0.0.3`、MuJoCo 3.x、MJCF、`ament_cmake`、`pluginlib`、`realtime_tools`、`pytest`、`ament_cmake_gtest`、`launch_testing`。

## Global Constraints

- 用户已在 2026-08-09 明确批准启动实施，并要求由 ai-station 的 tmux Codex session 执行；Task 1 可以开始。
- 实施 agent 直接运行在 ai-station；不得从 ai-station 再 SSH 到自己。Mac 侧只用于审阅与同步文档。
- 实施必须使用 `/data/work/ws_moveit/.worktrees/so101-mujoco-ros2` 和分支 `codex/so101-mujoco-ros2`，不得写当前 `so101-gazebo-demo-py` worktree。
- 代码设计基线是 `8d7913e7f552a40ee627d65be8b873ac16748bc9`。实施起点允许在它之上仅包含本 spec、plan 和同步后的 `.agents/skills/so101-dev/`；Task 1 必须解析并记录实际 kickoff commit。若远端 delta 包含其他源码、配置或实验改动，先停止并做新的 design delta，不得静默换基线。
- 不抢占、发键或清理 `codex-cua`、`so101-py-qual` 或其他 worker 的 tmux/process。只停止本轮可追踪 PID/session。
- 新建并持续维护 `docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md`；实验前先写 `PLANNED`，结束写 `VALID` 或 `INVALID`。
- 实施前重新核对 apt/package/interface。2026-08-09 最新稳定 tag 是 0.0.3；在线 Jazzy 文档和未发布 `main` 比该 tag 更新，不依赖稳定 tag 中不存在的 `FreeJointState*` 或 `SetFreeJointState`。
- 用户已授权实施时升级 ai-station 或从 GitHub 最新稳定版构建。依赖只能按 Task 2 的固定 stable tag/commit 范围安装，转换工具的额外下载必须先展示清单并记录 provenance。
- 依赖优先使用 apt 0.0.3 binary；binary/dev export 不可用时，只允许从 tag `0.0.3`、commit `35ba8174b62d9560093614f981a3d4b978a96036` 构建到 `/data/work/ws_mujoco_ros2_control_003/install`。不得覆盖 `/opt/ros/jazzy` 或构建 floating `main`。
- simulation-only；不得连接真实机械臂。
- 正向任务链禁止 weld/equality/adhesion/mocap 跟随、object teleport、直接写 object qpos/qvel，禁止永久关闭抓取碰撞。
- MoveIt attached object 只做 collision shadow，不得作为 MuJoCo 物理抓取证据。
- Gazebo 的接触 depth/penetration 数值不得直接写入 MuJoCo policy。新 force/distance 门槛必须按 Task 12 标定，并等待用户确认。
- 保持 `run_mode:=dry_run` 和 `start_simulation:=false` 默认；execute 必须显式启用。
- 每个功能边界先写 RED test，再做最小实现，再运行定向 test；包级测试和 live gate 后置。
- 每个 task 只 stage 本 task 列出的路径，提交前运行 `git status --short`、`git diff --cached --name-status`、`git diff --cached --check`。
- 不运行 `ament_uncrustify --reformat`；格式修正用定向 patch。
- runtime 原始证据只放 `/tmp/so101-debug-mujoco-migration/`；源码树只保留账本摘要、hash、结论和 provenance。
- 不 push、merge、删除 Gazebo reference branch，除非用户另行明确要求。
- 设计依据：`docs/superpowers/specs/2026-08-09-so101-mujoco-ros2-migration-design.md`。

---

### Task 1: Freeze the Baseline and Create the Isolated Migration Worktree

**Files:**
- Create in the new worktree: `docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md`
- Create: `src/so101_gazebo_demo_py/test/test_mujoco_migration_ledger_contract.py`

**Interfaces:**
- Consumes: remote branch `origin/codex/so101-gazebo-demo-py`, immutable code design baseline `8d7913e`, and a docs/Skill-only kickoff delta.
- Produces: clean branch `codex/so101-mujoco-ros2`, isolated worktree, one-writer migration ledger, evidence root `/tmp/so101-debug-mujoco-migration/`.

- [ ] **Step 1: Prove the baseline has not drifted**

Run on ai-station without touching active processes:

```bash
cd /data/work/ws_moveit
git fetch origin codex/so101-gazebo-demo-py
git rev-parse origin/codex/so101-gazebo-demo-py
git merge-base --is-ancestor 8d7913e7f552a40ee627d65be8b873ac16748bc9 origin/codex/so101-gazebo-demo-py
git diff --name-status 8d7913e7f552a40ee627d65be8b873ac16748bc9..origin/codex/so101-gazebo-demo-py
git status --short
git worktree list --porcelain
tmux list-sessions 2>/dev/null || true
pgrep -af 'gz sim|move_group|rviz2|pick_place_state_machine|mujoco' || true
```

Expected: the remote tip descends from `8d7913e7f552a40ee627d65be8b873ac16748bc9`, and every changed path after that commit is one of the two migration documents or `.agents/skills/so101-dev/**`. Record the exact remote tip as the kickoff commit. Any other changed path requires a new design delta before implementation.

- [ ] **Step 2: Create the isolated branch/worktree**

First prove neither target exists:

```bash
cd /data/work/ws_moveit
test ! -e .worktrees/so101-mujoco-ros2
! git show-ref --verify --quiet refs/heads/codex/so101-mujoco-ros2
git worktree add -b codex/so101-mujoco-ros2 .worktrees/so101-mujoco-ros2 origin/codex/so101-gazebo-demo-py
cd .worktrees/so101-mujoco-ros2
git status --short --branch
git rev-parse HEAD
```

Expected: clean target worktree on the exact kickoff commit recorded in Step 1. Do not reset, stash, clean, or modify the source worktree. If the orchestrator already created this exact path/branch before handoff, verify its branch, HEAD and clean status and continue at Step 3; do not recreate it.

- [ ] **Step 3: Write the ledger contract test first**

The test reads the ledger front matter and asserts exact values:

```python
import re


def test_mujoco_migration_ledger_header() -> None:
    text = LEDGER.read_text()
    assert "task_id: so101-mujoco-ros2-migration" in text
    assert "branch: codex/so101-mujoco-ros2" in text
    assert "design_base_commit: 8d7913e7f552a40ee627d65be8b873ac16748bc9" in text
    assert re.search(r"(?m)^base_commit: [0-9a-f]{40}$", text)
    assert "evidence_root: /tmp/so101-debug-mujoco-migration/" in text
    assert "success_contract:" in text
    assert "next_experiment: NONE" in text
```

- [ ] **Step 4: Run RED**

```bash
cd /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_mujoco_migration_ledger_contract.py
```

Expected: fail because the ledger does not exist.

- [ ] **Step 5: Create the initial ledger**

Use the project experiment-ledger schema with these frozen header values:

```yaml
task_id: so101-mujoco-ros2-migration
goal: Replace the Gazebo simulation boundary with MuJoCo while preserving ROS 2, MoveIt, workflow and physical-outcome behavior.
success_contract: No simulator attachment or object mutation in the forward path; model/control/reset/evidence gates pass; final physical outcome passes for five consecutive FULL_RESTART and five consecutive RESET_WORLD runs.
worktree: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
branch: codex/so101-mujoco-ros2
design_base_commit: 8d7913e7f552a40ee627d65be8b873ac16748bc9
base_commit: <replace with the exact kickoff commit recorded in Step 1>
current_commit: <same exact kickoff commit before the first implementation commit>
evidence_root: /tmp/so101-debug-mujoco-migration/
confirmed_conclusions:
  - The Gazebo baseline has one valid final success but has not completed its required qualification streak; EXP-073 is automated-tested but not live-qualified.
  - The apt candidate is mujoco_ros2_control 0.0.3; its tag has ResetWorld, SetPause and StepSimulation but no FreeJointState or SetFreeJointState interface.
disproven_routes:
  - Treating current Jazzy online FreeJoint documentation as proof that the 0.0.3 binary exposes those interfaces.
open_hypotheses:
  - A curated SO-101 MJCF plus a read-only atomic evidence plugin can preserve the current physical-outcome semantics.
latest_checkpoint: CP-BASELINE-001
next_experiment: NONE
```

Append `CP-BASELINE-001` with exact worktree status, observed existing processes as preserved, and `next_command: NONE`.

- [ ] **Step 6: Run GREEN and commit**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_mujoco_migration_ledger_contract.py
git add -- docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md src/so101_gazebo_demo_py/test/test_mujoco_migration_ledger_contract.py
git diff --cached --check
git diff --cached --name-status
git commit -m "docs(so101_mujoco): initialize migration ledger"
```

---

### Task 2: Pin and Prove the Actual MuJoCo ROS 2 Interface

**Files:**
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/mujoco/__init__.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/mujoco/preflight.py`
- Create: `src/so101_gazebo_demo_py/config/mujoco_dependency_lock.yaml`
- Create: `src/so101_gazebo_demo_py/test/test_mujoco_preflight.py`
- Modify: `src/so101_gazebo_demo_py/setup.py`
- Modify: `docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md`

**Interfaces:**
- Consumes: `dpkg-query` or a source checkout HEAD, `ros2 pkg prefix`, `ros2 interface list/show` text.
- Produces: `MujocoDependencyReport`, `validate_dependency_report(report) -> tuple[str, ...]`, console script `so101_mujoco_preflight`.

- [ ] **Step 1: Write RED unit tests for the version/interface matrix**

Test the exact accepted matrix:

```python
VALID = MujocoDependencyReport(
    provider="apt",
    vendor_version="0.0.8-2noble.20260313.134558",
    control_version="0.0.3-1noble.20260615.175335",
    control_commit="35ba8174b62d9560093614f981a3d4b978a96036",
    control_prefix="/opt/ros/jazzy",
    packages=frozenset({
        "mujoco_vendor", "mujoco_ros2_control",
        "mujoco_ros2_control_msgs", "mujoco_ros2_control_plugins",
    }),
    interfaces=frozenset({
        "mujoco_ros2_control_msgs/srv/ResetWorld",
        "mujoco_ros2_control_msgs/srv/SetPause",
        "mujoco_ros2_control_msgs/srv/StepSimulation",
    }),
)

def test_stable_003_apt_matrix_is_accepted() -> None:
    assert validate_dependency_report(VALID) == ()

def test_stable_003_source_overlay_is_accepted() -> None:
    source = replace(
        VALID,
        provider="source",
        control_version="0.0.3",
        control_prefix="/data/work/ws_mujoco_ros2_control_003/install",
    )
    assert validate_dependency_report(source) == ()

def test_missing_control_package_is_rejected() -> None:
    assert "mujoco_ros2_control missing" in validate_dependency_report(
        replace(VALID, packages=VALID.packages - {"mujoco_ros2_control"})
    )

def test_unpublished_interfaces_are_not_required() -> None:
    assert "mujoco_ros2_control_msgs/srv/SetFreeJointState" not in REQUIRED_INTERFACES
```

Also reject an unknown provider, a control release other than `0.0.3`, a commit other than `35ba8174b62d9560093614f981a3d4b978a96036`, a vendor version not starting with `0.0.8-`, a provider/prefix mismatch, or missing Reset/Pause/Step.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_mujoco_preflight.py
```

Expected: import failure.

- [ ] **Step 3: Implement the pure parser/validator and console entry point**

The module may call subprocess only in `main()`. Parsing and validation remain pure and testable. It reads `config/mujoco_dependency_lock.yaml` and `main()` prints one JSON document containing provider, stable tag commit, package versions, prefixes, present interfaces and validation errors; exit `0` only when the matrix passes.

Initialize the lock for the preferred binary route:

```yaml
schema_version: 1
provider: apt
release: 0.0.3
commit: 35ba8174b62d9560093614f981a3d4b978a96036
prefix: /opt/ros/jazzy
```

Add to `setup.py`:

```python
"so101_mujoco_preflight = so101_gazebo_demo_py.mujoco.preflight:main"
```

- [ ] **Step 4: Run GREEN before installation**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_mujoco_preflight.py
```

- [ ] **Step 5: Install and prove the preferred stable binary package**

The user has authorized this scoped future upgrade/build. After Task 1 is explicitly started, show and record the current `apt-cache policy`; if the candidate still starts with `0.0.3-`, install:

```bash
sudo apt-get install ros-jazzy-mujoco-ros2-control
```

Do not install demos. Prove that `mujoco_ros2_control_plugins` exports `include/mujoco_ros2_control_plugins/mujoco_ros2_control_plugins_base.hpp` and `share/mujoco_ros2_control_plugins/cmake/mujoco_ros2_control_pluginsConfig.cmake` beneath its reported prefix. If either is absent, record the binary/dev-export failure and use Step 6. If apt candidate no longer starts with `0.0.3-`, stop for a stable-release delta review rather than accepting it silently.

- [ ] **Step 6: Use the fixed stable-tag source fallback only if the binary route fails**

This fallback is allowed only when Step 5 records a concrete binary/dev-export failure. It must not be selected merely because `main` has more features.

```bash
test ! -e /data/work/ws_mujoco_ros2_control_003
mkdir -p /data/work/ws_mujoco_ros2_control_003/src
git clone --branch 0.0.3 --depth 1 \
  https://github.com/ros-controls/mujoco_ros2_control.git \
  /data/work/ws_mujoco_ros2_control_003/src/mujoco_ros2_control
git -C /data/work/ws_mujoco_ros2_control_003/src/mujoco_ros2_control rev-parse HEAD
source /opt/ros/jazzy/setup.zsh
rosdep install -r --from-paths \
  /data/work/ws_mujoco_ros2_control_003/src/mujoco_ros2_control/mujoco_ros2_control \
  /data/work/ws_mujoco_ros2_control_003/src/mujoco_ros2_control/mujoco_ros2_control_msgs \
  /data/work/ws_mujoco_ros2_control_003/src/mujoco_ros2_control/mujoco_ros2_control_plugins \
  --ignore-src --rosdistro jazzy -y
cd /data/work/ws_mujoco_ros2_control_003
colcon build --merge-install --packages-up-to mujoco_ros2_control
source install/setup.zsh
```

Expected checkout HEAD: `35ba8174b62d9560093614f981a3d4b978a96036`. If it differs, stop. Update only the lock fields:

```yaml
provider: source
prefix: /data/work/ws_mujoco_ros2_control_003/install
```

Keep `release` and `commit` unchanged. Do not modify or overlay `/opt/ros/jazzy`.

- [ ] **Step 7: Prove live interfaces and record provenance**

```bash
source /opt/ros/jazzy/setup.zsh
# Source /data/work/ws_mujoco_ros2_control_003/install/setup.zsh here only when the lock provider is source.
ros2 pkg prefix mujoco_vendor
ros2 pkg prefix mujoco_ros2_control
ros2 interface show mujoco_ros2_control_msgs/srv/ResetWorld
ros2 interface show mujoco_ros2_control_msgs/srv/SetPause
ros2 interface show mujoco_ros2_control_msgs/srv/StepSimulation
ros2 interface list | rg 'mujoco_ros2_control_msgs/(msg|srv)'
PYTHONPATH=src/so101_gazebo_demo_py python3 -m so101_gazebo_demo_py.mujoco.preflight
```

Expected: preflight exit 0; `ResetWorld` request has `string keyframe`; no implementation dependency on FreeJoint/SetFreeJoint.

Write a ledger checkpoint containing selected provider, dpkg version or source checkout HEAD, all prefixes, interface text SHA-256 and upstream stable tag commit `35ba8174b62d9560093614f981a3d4b978a96036`. Record why the source fallback was selected when applicable.

- [ ] **Step 8: Build, retest and commit**

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_gazebo_demo_py --symlink-install
source install/setup.zsh
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_mujoco_preflight.py
ros2 run so101_gazebo_demo_py so101_mujoco_preflight
git add -- src/so101_gazebo_demo_py/so101_gazebo_demo_py/mujoco src/so101_gazebo_demo_py/config/mujoco_dependency_lock.yaml src/so101_gazebo_demo_py/test/test_mujoco_preflight.py src/so101_gazebo_demo_py/setup.py docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md
git diff --cached --check
git commit -m "build(so101_mujoco): pin simulator interface matrix"
```

---

### Task 3: Introduce Backend-Neutral Simulation Evidence

**Files:**
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/simulation/__init__.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/simulation/evidence.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/simulation/protocols.py`
- Modify: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/gazebo/observer.py`
- Modify: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/test_support/ros_gazebo_backend.py`
- Modify: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/live_execute.py`
- Modify: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/test_support/live_attachment.py`
- Create: `src/so101_gazebo_demo_py/test/test_simulation_evidence.py`
- Modify: `src/so101_gazebo_demo_py/test/test_gazebo_attachment.py`
- Modify: `src/so101_gazebo_demo_py/test/test_gazebo_observer.py`
- Modify: `src/so101_gazebo_demo_py/test/test_live_physical_outcome_contract.py`
- Modify: `src/so101_gazebo_demo_py/test/test_outcome_first_continuation.py`
- Modify: `src/so101_gazebo_demo_py/test/test_post_retreat_final_outcome.py`

**Interfaces:**
- Consumes: Gazebo depth values and current observation behavior.
- Produces: `ContactPointEvidence`, `ContactPair`, `SimulationObservation`, `SimulationObserver`, `SimulationResetter`; Gazebo becomes one adapter of these interfaces without behavior change.

- [ ] **Step 1: Write RED tests for normalized evidence**

Test exact invariants:

```python
def test_gazebo_depth_maps_to_normalized_contact_point() -> None:
    point = ContactPointEvidence.from_gazebo_depth(0.0008)
    assert point.signed_distance_m == pytest.approx(-0.0008)
    assert point.penetration_m == pytest.approx(0.0008)
    assert point.normal_force_n is None

def test_mujoco_distance_and_force_are_preserved() -> None:
    point = ContactPointEvidence.from_mujoco(-0.0002, 0.35)
    assert point.signed_distance_m == pytest.approx(-0.0002)
    assert point.penetration_m == pytest.approx(0.0002)
    assert point.normal_force_n == pytest.approx(0.35)

def test_nonfinite_or_negative_force_is_rejected() -> None:
    with pytest.raises(ValueError):
        ContactPointEvidence.from_mujoco(-0.0002, -0.1)
```

Add a source contract asserting `simulation/` contains no `ros_gz`, `gz.` or `mujoco_ros2_control_msgs` import.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_simulation_evidence.py src/so101_gazebo_demo_py/test/test_gazebo_observer.py src/so101_gazebo_demo_py/test/test_live_physical_outcome_contract.py
```

- [ ] **Step 3: Implement frozen values and protocols**

Use this public shape:

```python
@dataclass(frozen=True, slots=True)
class ContactPointEvidence:
    signed_distance_m: float
    penetration_m: float
    normal_force_n: float | None

@dataclass(frozen=True, slots=True)
class ContactPair:
    object_collision: str
    other_collision: str
    points: tuple[ContactPointEvidence, ...]

@dataclass(frozen=True, slots=True)
class SimulationObservation:
    source_timestamp_s: float
    receipt_sequence: int
    object_pose_world: tuple[float, float, float, float, float, float, float]
    object_twist_world: tuple[float, float, float, float, float, float]
    contacts: tuple[ContactPair, ...]
    truncated: bool = False
```

`SimulationObserver.observe(freshness_s=0.2)` raises a typed stale/truncated observation failure when the newest receipt is older than 0.2 s. Move the existing contact reducers to import normalized evidence and use `point.penetration_m`; keep current Gazebo acceptance values unchanged in the Gazebo adapter tests.

- [ ] **Step 4: Run characterization GREEN**

```bash
python3 -m pytest -q \
  src/so101_gazebo_demo_py/test/test_simulation_evidence.py \
  src/so101_gazebo_demo_py/test/test_gazebo_observer.py \
  src/so101_gazebo_demo_py/test/test_live_physical_outcome_contract.py \
  src/so101_gazebo_demo_py/test/test_main_strategy_parity.py
```

Expected: current Gazebo behavior remains green; this task does not launch Gazebo.

- [ ] **Step 5: Run the full Python suite and commit**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test
git add -- src/so101_gazebo_demo_py/so101_gazebo_demo_py/simulation src/so101_gazebo_demo_py/so101_gazebo_demo_py/gazebo/observer.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/test_support/ros_gazebo_backend.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/live_execute.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/test_support/live_attachment.py src/so101_gazebo_demo_py/test/test_simulation_evidence.py src/so101_gazebo_demo_py/test/test_gazebo_attachment.py src/so101_gazebo_demo_py/test/test_gazebo_observer.py src/so101_gazebo_demo_py/test/test_live_physical_outcome_contract.py src/so101_gazebo_demo_py/test/test_outcome_first_continuation.py src/so101_gazebo_demo_py/test/test_post_retreat_final_outcome.py
git diff --cached --check
git commit -m "refactor(so101_mujoco): define simulation evidence boundary"
```

---

### Task 4: Build the Atomic MuJoCo Simulation Evidence Plugin

**Files:**
- Create: `src/so101_mujoco_support/package.xml`
- Create: `src/so101_mujoco_support/CMakeLists.txt`
- Create: `src/so101_mujoco_support/msg/ContactSample.msg`
- Create: `src/so101_mujoco_support/msg/SimulationEvidence.msg`
- Create: `src/so101_mujoco_support/include/so101_mujoco_support/simulation_evidence_plugin.hpp`
- Create: `src/so101_mujoco_support/src/simulation_evidence_plugin.cpp`
- Create: `src/so101_mujoco_support/so101_mujoco_plugins.xml`
- Create: `src/so101_mujoco_support/test/fixtures/contact_probe.xml`
- Create: `src/so101_mujoco_support/test/test_simulation_evidence_plugin.cpp`

**Interfaces:**
- Consumes: `const mjModel*`, `mjData*`, configured object body and tracked geom names.
- Produces: `so101_mujoco_support/msg/SimulationEvidence` on `/so101/simulation/evidence`; pluginlib class `so101_mujoco_support/SimulationEvidencePlugin`.

- [ ] **Step 1: Define messages and write a RED model-backed test**

Messages must be exact:

```text
# ContactSample.msg
string geom1
string geom2
geometry_msgs/Point position_world
geometry_msgs/Vector3 normal_world
float64 signed_distance_m
float64 normal_force_n
```

```text
# SimulationEvidence.msg
std_msgs/Header header
uint64 sequence
string object_body
geometry_msgs/Pose object_pose_world
geometry_msgs/Twist object_twist_world
bool truncated
ContactSample[] contacts
```

The gtest loads `contact_probe.xml` with a free body named `plastic_cup`, named `cup_geom` overlapping named `finger_geom`, calls `mj_forward`, and asserts:

- plugin init fails for an unknown object body or geom;
- one snapshot has finite pose/twist;
- the contact pair contains the exact two geom names;
- `signed_distance_m <= 0.0` and `normal_force_n >= 0.0`;
- moving the cup clear and forwarding again produces an explicit empty contact array with incremented sequence;
- an imposed `max_contacts=0` produces `truncated=true` when contact exists.

- [ ] **Step 2: Run RED**

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_mujoco_support --cmake-args -DBUILD_TESTING=ON
```

Expected: package or plugin sources are incomplete and build/test fails.

- [ ] **Step 3: Implement the minimal read-only plugin**

In `init`:

- resolve `object_body` with `mj_name2id(model, mjOBJ_BODY, object_body_name_.c_str())`;
- resolve every tracked geom with `mj_name2id(model, mjOBJ_GEOM, tracked_geom_name.c_str())`;
- preallocate capacity `max_contacts`, default 128;
- create a non-blocking `realtime_tools::RealtimePublisher<SimulationEvidence>`;
- reject `publish_rate <= 0` or unknown names.

In `update`:

```cpp
const auto body = object_body_id_;
copy_pose_wxyz_to_ros_xyzw(data->xpos + 3 * body, data->xquat + 4 * body, message.object_pose_world);
mjtNum velocity[6]{};
mj_objectVelocity(model, data, mjOBJ_BODY, body, velocity, 0);
copy_world_velocity(velocity, message.object_twist_world);
for (int contact_id = 0; contact_id < data->ncon; ++contact_id) {
  const mjContact & contact = data->contact[contact_id];
  if (!tracked(contact.geom1, contact.geom2)) { continue; }
  mjtNum wrench[6]{};
  mj_contactForce(model, data, contact_id, wrench);
  append_bounded(contact, std::max<mjtNum>(0.0, wrench[0]), message);
}
```

The plugin must not write through `data`, call `mj_step`, change constraints, or expose a mutation service. Publish an empty array on schedule. Convert `data->time` to the ROS header stamp; do not substitute receipt time.

- [ ] **Step 4: Export the plugin and run GREEN**

Use:

```cmake
pluginlib_export_plugin_description_file(
  mujoco_ros2_control_plugins so101_mujoco_plugins.xml)
```

Run:

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_mujoco_support --cmake-args -DBUILD_TESTING=ON
source install/setup.zsh
colcon test --packages-select so101_mujoco_support --event-handlers console_direct+
colcon test-result --verbose
ros2 interface show so101_mujoco_support/msg/SimulationEvidence
```

- [ ] **Step 5: Commit**

```bash
git add -- src/so101_mujoco_support
git diff --cached --check
git diff --cached --name-status
git commit -m "feat(so101_mujoco): publish atomic simulation evidence"
```

---

### Task 5: Create and Prove the SO-101 Robot MJCF

**Files:**
- Create: `src/so101_gazebo_demo_py/mjcf/so101.xml`
- Create: `src/so101_gazebo_demo_py/mjcf/assets/**`
- Create: `src/so101_gazebo_demo_py/mjcf/README.md`
- Create: `src/so101_mujoco_support/include/so101_mujoco_support/model_parity.hpp`
- Create: `src/so101_mujoco_support/src/model_parity.cpp`
- Create: `src/so101_mujoco_support/test/model_parity_samples.yaml`
- Create: `src/so101_mujoco_support/test/test_model_parity.cpp`
- Modify: `src/so101_mujoco_support/CMakeLists.txt`
- Modify: `src/so101_mujoco_support/package.xml`
- Modify: `src/so101_gazebo_demo_py/setup.py`
- Modify: `src/so101_gazebo_demo_py/docs/provenance.json`

**Interfaces:**
- Consumes: resolved package-local SO-101 URDF/Xacro, current meshes and fixed 11-pose sample set.
- Produces: compilable `so101.xml`; `compare_urdf_mjcf(urdf_xml, mjcf_path, samples) -> ModelParityReport`.

- [ ] **Step 1: Write RED MJCF compile and parity tests**

The test fixture contains home plus 10 deterministic joint vectors within current limits. For each vector, compare bodies `base`, `shoulder`, `upper_arm`, `lower_arm`, `wrist`, `gripper`, `jaw`, and site/body `so101_tcp`.

Required assertions:

```cpp
EXPECT_LE(report.max_position_error_m, 0.0005);
EXPECT_LE(report.max_orientation_error_rad, 0.2 * M_PI / 180.0);
EXPECT_TRUE(report.joint_names_exact);
EXPECT_TRUE(report.joint_axes_exact);
EXPECT_TRUE(report.joint_limits_exact);
EXPECT_TRUE(report.q6_direction_exact);
```

Also assert there are exactly six controllable joints named `1` through `6`, position actuator names match joints, relevant collision geoms are named, and no `<equality>`, adhesion actuator or mocap body exists.

- [ ] **Step 2: Run RED**

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_mujoco_support --cmake-args -DBUILD_TESTING=ON
source install/setup.zsh
colcon test --packages-select so101_mujoco_support --event-handlers console_direct+
colcon test-result --verbose
```

Expected: MJCF missing or parity fails.

- [ ] **Step 3: Produce an offline conversion draft only after tool authorization**

Resolve the exact URDF first:

```bash
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/setup.zsh
xacro src/so101_gazebo_demo_py/urdf/so101.urdf.xacro \
  base_height:=0.1899186 use_gazebo:=false gazebo_collision_primitives:=true \
  object_config:=src/so101_gazebo_demo_py/config/task_objects/light_plastic_cup.yaml \
  > /tmp/so101-debug-mujoco-migration/so101-resolved.urdf
```

If the official converter would create a virtualenv or download Python dependencies, obtain authorization first. Then create only a temporary draft:

```bash
ros2 run mujoco_ros2_control robot_description_to_mjcf.sh \
  --save_only --no-fuse --convert_stl_to_obj \
  -u /tmp/so101-debug-mujoco-migration/so101-resolved.urdf \
  -o /tmp/so101-debug-mujoco-migration/mjcf-draft
```

Do not commit the raw converter output. Record converter command, generated-file hashes and tool/package versions in the ledger.

- [ ] **Step 4: Curate the committed robot MJCF**

Build `so101.xml` from the resolved URDF/draft and current package assets with:

- nested bodies matching the URDF chain;
- radians and local coordinates explicitly fixed in `<compiler>`;
- six named hinge joints with current limits/direction/zero pose;
- named position actuators with `ctrlrange` equal to current command limits;
- visual meshes separated from collision geoms;
- simple/convex named collision geoms for fingertips and arm links;
- `so101_tcp` site at the URDF TCP transform;
- explicit masses/inertias derived from the current model, with any compiler balancing decision documented;
- no scene, table, cup or camera in this robot-only file.

`mjcf/README.md` records derivation commands, current source paths, source/destination SHA-256, and that Menagerie SO-ARM100 was a modeling reference only.

- [ ] **Step 5: Run compile/parity GREEN**

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_mujoco_support --cmake-args -DBUILD_TESTING=ON
source install/setup.zsh
colcon test --packages-select so101_mujoco_support --event-handlers console_direct+
colcon test-result --verbose
ros2 pkg executables mujoco_vendor | rg '^mujoco_vendor simulate$'
```

The automated `mj_loadXML` test is authoritative for compile success; the last command only proves the installed executable is discoverable and must not start a long-lived GUI in this task.

- [ ] **Step 6: Install assets and commit**

Update deterministic `setup.py` data files and provenance hashes. Then:

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_asset_closure.py src/so101_gazebo_demo_py/test/test_provenance.py
git add -- src/so101_gazebo_demo_py/mjcf src/so101_gazebo_demo_py/setup.py src/so101_gazebo_demo_py/docs/provenance.json src/so101_mujoco_support
git diff --cached --check
git commit -m "feat(so101_mujoco): add parity-proved robot MJCF"
```

---

### Task 6: Add the Task Scene, Home Keyframe, and Cross-Asset Contract

**Files:**
- Create: `src/so101_gazebo_demo_py/mjcf/scene.xml`
- Create: `src/so101_gazebo_demo_py/test/test_mjcf_scene_contract.py`
- Create: `src/so101_mujoco_support/test/test_scene_reset_keyframe.cpp`
- Modify: `src/so101_gazebo_demo_py/setup.py`
- Modify: `src/so101_gazebo_demo_py/docs/provenance.json`
- Modify: `src/so101_mujoco_support/CMakeLists.txt`

**Interfaces:**
- Consumes: `so101.xml`, `initial_positions.yaml`, task-object YAML, final outcome policy.
- Produces: one deterministic MuJoCo scene with table, `plastic_cup` free joint, `home` keyframe and named collision geoms.

- [ ] **Step 1: Write RED cross-asset tests**

Python test parses MJCF/YAML and asserts:

- `scene.xml` includes `so101.xml` exactly once;
- option timestep is exactly `0.001` s and gravity is `[0, 0, -9.81]`;
- table collision geom is named `table_support`;
- cup body is named `plastic_cup`, has exactly one free joint and mass equals `model.mass_kg` from task-object YAML;
- cup initial pose in `home` matches task-object initial pose within `1e-9` before compilation;
- all fingertip, cup and table contact geoms have stable unique names;
- no equality, adhesion, mocap or hidden external-force plugin exists;
- headless and GUI launch will consume the same `scene.xml` path.

C++ test loads the compiled scene, applies `home` with `mj_resetDataKeyframe`, calls `mj_forward`, and asserts joint/cup qvel is zero and compiled cup transform matches the policy pose within `1e-9`.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_mjcf_scene_contract.py
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_mujoco_support --cmake-args -DBUILD_TESTING=ON
source install/setup.zsh
colcon test --packages-select so101_mujoco_support --event-handlers console_direct+
```

- [ ] **Step 3: Implement the minimal scene**

`scene.xml` contains:

- `<include file="so101.xml"/>`;
- fixed plane/table matching the current world frame and table top height;
- a rigid `plastic_cup` body with free joint, compound named wall/bottom geoms, configured mass/inertia and visible material;
- light and a fixed overview camera for GUI evidence only;
- `<keyframe>` with a single `<key name="home"/>`; its generated `qpos`, `qvel` and `ctrl` attributes restore all six joints, the cup free-joint pose, zero velocity and initial commands, and are checked against YAML by the cross-asset test;
- contact defaults that are explicit, finite and not presented as calibrated grasp thresholds.

The task-object YAML remains the source of task semantics. Any duplicated MJCF value is covered by the cross-asset test.

- [ ] **Step 4: Run GREEN and inspect only model metadata**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_mjcf_scene_contract.py
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_mujoco_support --cmake-args -DBUILD_TESTING=ON
source install/setup.zsh
colcon test --packages-select so101_mujoco_support --event-handlers console_direct+
colcon test-result --verbose
```

- [ ] **Step 5: Commit**

```bash
git add -- src/so101_gazebo_demo_py/mjcf/scene.xml src/so101_gazebo_demo_py/test/test_mjcf_scene_contract.py src/so101_gazebo_demo_py/setup.py src/so101_gazebo_demo_py/docs/provenance.json src/so101_mujoco_support
git diff --cached --check
git commit -m "feat(so101_mujoco): add deterministic pick-place scene"
```

---

### Task 7: Wire MJCF to ros2_control and Launch a Minimal Controller Stack

**Files:**
- Create: `src/so101_gazebo_demo_py/config/mujoco_plugins.yaml`
- Create: `src/so101_gazebo_demo_py/launch/so101_mujoco.launch.py`
- Modify: `src/so101_gazebo_demo_py/urdf/so101_ros2_control.xacro`
- Modify: `src/so101_gazebo_demo_py/urdf/so101.urdf.xacro`
- Modify: `src/so101_gazebo_demo_py/package.xml`
- Modify: `src/so101_gazebo_demo_py/setup.py`
- Create: `src/so101_gazebo_demo_py/test/test_mujoco_launch_contract.py`
- Create: `src/so101_gazebo_demo_py/test/headless/test_mujoco_controller_live.py`

**Interfaces:**
- Consumes: `scene.xml`, current controller YAML, `mujoco_ros2_control/MujocoSystemInterface`.
- Produces: `/clock`, `/joint_states`, `/controller_manager`, `/ros2_control_node/{set_pause,reset_world,step_simulation}`, arm/gripper FollowJointTrajectory actions, `/so101/simulation/evidence`.

- [ ] **Step 1: Write RED source/launch contracts**

Assert:

- MuJoCo xacro branch contains `mujoco_ros2_control/MujocoSystemInterface` and the installed absolute `scene.xml` path;
- Gazebo branch remains unchanged for migration A/B;
- launch uses package `mujoco_ros2_control`, executable `ros2_control_node`, `use_sim_time=True` and current controller YAML;
- plugin YAML loads only `so101_mujoco_support/SimulationEvidencePlugin` with object `plastic_cup`, tracked table/cup/fingertip geoms, topic `/so101/simulation/evidence`, publish rate 100 Hz and max contacts 128;
- launch does not import `ros_gz_*`, set `GZ_PARTITION`, load a weld/equality plugin or spawn a second robot model;
- default `headless=false`; the same scene path is used for both values.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_mujoco_launch_contract.py
```

- [ ] **Step 3: Implement the xacro backend branch**

Add xacro parameters `simulation_backend`, `mujoco_model` and `headless`. For `simulation_backend == 'mujoco'` emit:

```xml
<hardware>
  <plugin>mujoco_ros2_control/MujocoSystemInterface</plugin>
  <param name="mujoco_model">${mujoco_model}</param>
  <param name="headless">${headless}</param>
  <param name="initial_keyframe">home</param>
</hardware>
```

Keep joints `1`–`6` and their position command/state interfaces identical. Retain the Gazebo plugin only inside the Gazebo branch until Task 15.

- [ ] **Step 4: Implement launch and plugin config**

Launch:

- resolves package share before building robot description;
- passes the same controller config used by the current physical-outcome path;
- launches robot_state_publisher and `mujoco_ros2_control/ros2_control_node`;
- spawns `joint_state_broadcaster`, `arm_controller`, `gripper_controller` against `/controller_manager`;
- exits the launch if the control node exits;
- has no timer-only readiness assumption: headless test waits on concrete service/action/topic gates.

- [ ] **Step 5: Run source GREEN and build**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_mujoco_launch_contract.py
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_mujoco_support so101_gazebo_demo_py --symlink-install
source install/setup.zsh
ros2 launch so101_gazebo_demo_py so101_mujoco.launch.py --show-args
```

- [ ] **Step 6: Preregister and run one bounded headless controller test**

Create `EXP-CTRL-001` in the migration ledger before launch. Use a unique unused ROS domain and one owned tmux window. The live test must assert:

- exactly one `/controller_manager` and one `/ros2_control_node`;
- expected three controllers active;
- `/clock`, `/joint_states`, evidence topic and Reset/Pause/Step service types;
- one arm and one gripper trajectory result succeeds;
- max final joint error `<= 0.001 rad`;
- cup pose stays finite and no object mutation/constraint exists.

Run the installed test entry with a bounded timeout and preserve stdout/stderr/exit code under the task evidence root. Mark the experiment `VALID` or `INVALID` before continuing.

- [ ] **Step 7: Run package tests and commit**

```bash
source /opt/ros/jazzy/setup.zsh
source install/setup.zsh
PYTHONNOUSERSITE=1 colcon test --packages-select so101_mujoco_support so101_gazebo_demo_py --event-handlers console_direct+
colcon test-result --verbose
git add -- src/so101_gazebo_demo_py/config/mujoco_plugins.yaml src/so101_gazebo_demo_py/launch/so101_mujoco.launch.py src/so101_gazebo_demo_py/urdf src/so101_gazebo_demo_py/package.xml src/so101_gazebo_demo_py/setup.py src/so101_gazebo_demo_py/test/test_mujoco_launch_contract.py src/so101_gazebo_demo_py/test/headless/test_mujoco_controller_live.py docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md
git diff --cached --check
git commit -m "feat(so101_mujoco): launch controlled headless simulation"
```

---

### Task 8: Implement the MuJoCo Python Observer

**Files:**
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/mujoco/observer.py`
- Create: `src/so101_gazebo_demo_py/test/test_mujoco_observer.py`
- Create: `src/so101_gazebo_demo_py/test/headless/test_mujoco_observer_live.py`
- Modify: `src/so101_gazebo_demo_py/package.xml`
- Modify: `src/so101_gazebo_demo_py/setup.py`

**Interfaces:**
- Consumes: `/so101/simulation/evidence` (`so101_mujoco_support/msg/SimulationEvidence`).
- Produces: `MujocoWorldObserver.observe(freshness_s) -> SimulationObservation`, normalized `ContactPair` values and deterministic stale/truncated failures.

- [ ] **Step 1: Write RED message-conversion and freshness tests**

Cover:

```python
def test_message_maps_wxyz_boundary_to_ros_xyzw_without_reordering_ros_input() -> None:
    message = evidence_message(position=(1.0, 2.0, 3.0), xyzw=(0.1, 0.2, 0.3, 0.9))
    observed = observation_from_message(message, received_monotonic_s=10.0)
    assert observed.object_pose_world == pytest.approx((1.0, 2.0, 3.0, 0.1, 0.2, 0.3, 0.9))

def test_negative_mujoco_distance_maps_to_positive_penetration() -> None:
    observed = observation_from_message(
        evidence_message(contact_distance=-0.0004, normal_force=0.25),
        received_monotonic_s=10.0,
    )
    point = observed.contacts[0].points[0]
    assert point.penetration_m == pytest.approx(0.0004)
    assert point.normal_force_n == pytest.approx(0.25)

def test_explicit_empty_snapshot_is_not_stale() -> None:
    observer = observer_with_message(evidence_message(contacts=[]), received_monotonic_s=10.0)
    assert observer.observe(freshness_s=0.2, now_monotonic_s=10.1).contacts == ()
```

Also reject non-unit quaternion beyond `1e-6`, nonfinite pose/twist/contact fields, negative force, nonmonotonic sequence, stale receipt time and `truncated=true`.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_mujoco_observer.py
```

- [ ] **Step 3: Implement conversion and latest-snapshot storage**

Use one persistent rclpy subscription with `BEST_EFFORT`, volatile durability and depth 10. The callback validates the complete message before atomically replacing the previous snapshot. It never merges contacts from different messages.

Group contact samples by ordered normalized pair `(object_collision, other_collision)` while retaining every point. Normalize pair direction so a task-object geom is always `object_collision`. Preserve source simulation stamp and plugin sequence; track receipt monotonic time only for staleness.

Map failures to stable codes:

```text
MUJOCO_EVIDENCE_UNAVAILABLE
MUJOCO_EVIDENCE_STALE
MUJOCO_EVIDENCE_SEQUENCE_REGRESSION
MUJOCO_EVIDENCE_INVALID
MUJOCO_EVIDENCE_TRUNCATED
```

- [ ] **Step 4: Run unit GREEN**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_mujoco_observer.py src/so101_gazebo_demo_py/test/test_simulation_evidence.py
```

- [ ] **Step 5: Preregister and run one observer live test**

Create `EXP-OBS-001`, start one owned headless stack on a new ROS domain and assert 100 consecutive snapshots have strictly increasing sequence, finite normalized quaternion/twist, no truncation and bounded inter-message simulation time. Compare the first cup pose with the compiled `home` keyframe and policy pose at `<= 0.001 m` / `<= 0.5 deg`.

This experiment observes only; do not send a trajectory or change physics parameters.

- [ ] **Step 6: Package test and commit**

```bash
source /opt/ros/jazzy/setup.zsh
# Source the locked dependency overlay here when provider=source.
colcon build --packages-select so101_mujoco_support so101_gazebo_demo_py --symlink-install
source install/setup.zsh
PYTHONNOUSERSITE=1 colcon test --packages-select so101_mujoco_support so101_gazebo_demo_py --event-handlers console_direct+
colcon test-result --verbose
git add -- src/so101_gazebo_demo_py/so101_gazebo_demo_py/mujoco/observer.py src/so101_gazebo_demo_py/test/test_mujoco_observer.py src/so101_gazebo_demo_py/test/headless/test_mujoco_observer_live.py src/so101_gazebo_demo_py/package.xml src/so101_gazebo_demo_py/setup.py docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md
git diff --cached --check
git commit -m "feat(so101_mujoco): observe atomic world evidence"
```

---

### Task 9: Implement Deterministic MuJoCo Reset and Postcondition Proof

**Files:**
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/mujoco/client.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/mujoco/reset.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/cli/reset_so101_mujoco_world.py`
- Create: `src/so101_gazebo_demo_py/test/test_mujoco_reset.py`
- Create: `src/so101_gazebo_demo_py/test/headless/test_mujoco_reset_live.py`
- Modify: `src/so101_gazebo_demo_py/setup.py`
- Modify: `src/so101_gazebo_demo_py/package.xml`

**Interfaces:**
- Consumes: controller-manager switch service, `SetPause`, `ResetWorld`, `StepSimulation`, MuJoCo observer, MoveIt scene client, joint states.
- Produces: `MujocoResetCoordinator.reset_and_prove(request) -> ResetEvidence`, console script `reset_so101_mujoco_world`.

- [ ] **Step 1: Write RED orchestration-order tests**

With fake clients, require exact calls:

```python
assert calls == [
    "cancel_active_goals",
    "deactivate:arm_controller,gripper_controller",
    "pause:true",
    "reset_world:home",
    "step_simulation:250",
    "restore_scene_world_only",
    "activate:arm_controller,gripper_controller",
    "pause:false",
    "prove_postcondition",
]
```

Test short-circuit behavior at every failure. A failure after pause must attempt a bounded resume cleanup, retain the original failure code and report cleanup failure separately. Assert no client or interface named `set_free_joint_state`, `teleport`, `weld`, `attach` or `equality` exists in the MuJoCo reset path.

Postcondition test values:

```python
assert evidence.max_joint_error_rad <= 0.001
assert evidence.object_position_error_m <= 0.001
assert evidence.object_orientation_error_rad <= math.radians(0.5)
assert evidence.object_linear_speed_m_s <= 0.001
assert evidence.object_angular_speed_rad_s <= 0.01
assert evidence.gripper_contact is False
assert evidence.moveit_world_only is True
```

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_mujoco_reset.py
```

- [ ] **Step 3: Implement typed async service clients**

Create persistent clients for:

```text
/controller_manager/switch_controller
/ros2_control_node/set_pause
/ros2_control_node/reset_world
/ros2_control_node/step_simulation
```

Every call has an explicit discovery timeout and response timeout. `ResetWorld.Request.keyframe = "home"`; `StepSimulation.Request.steps = 250`. Controller switch uses strict mode and names exactly `arm_controller`, `gripper_controller`. Do not shell out to `ros2 service call` in runtime code.

- [ ] **Step 4: Implement postcondition proof**

The proof consumes one fresh joint-state sample, one fresh atomic simulation evidence sample and an authoritative Planning Scene query after resume. It derives support/gripper contacts from named geoms; it does not infer physical state from the command or keyframe request.

Console output is one JSON object containing every threshold, actual value, service result and session ID. Exit 0 only when every postcondition passes.

- [ ] **Step 5: Run unit GREEN and build**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_mujoco_reset.py
source /opt/ros/jazzy/setup.zsh
# Source locked dependency overlay if selected.
colcon build --packages-select so101_mujoco_support so101_gazebo_demo_py --symlink-install
source install/setup.zsh
```

- [ ] **Step 6: Preregister and run deterministic reset live tests**

Create `EXP-RESET-001` through `EXP-RESET-005`, all `lifecycle: RESET_WORLD`, `single_variable: NONE`, same commit/policy/MJCF. Before each run, place arm/cup in a different valid disturbed state using normal controller motion and physics; never mutate cup pose directly. Run installed reset and save independent JSON.

Each valid run must satisfy every numeric postcondition and show no extra stack/client. Any valid failure stops the five-run reset sequence; invalid run restarts the batch with new experiment IDs.

- [ ] **Step 7: Test and commit**

```bash
PYTHONNOUSERSITE=1 colcon test --packages-select so101_mujoco_support so101_gazebo_demo_py --event-handlers console_direct+
colcon test-result --verbose
git add -- src/so101_gazebo_demo_py/so101_gazebo_demo_py/mujoco/client.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/mujoco/reset.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/cli/reset_so101_mujoco_world.py src/so101_gazebo_demo_py/test/test_mujoco_reset.py src/so101_gazebo_demo_py/test/headless/test_mujoco_reset_live.py src/so101_gazebo_demo_py/setup.py src/so101_gazebo_demo_py/package.xml docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md
git diff --cached --check
git commit -m "feat(so101_mujoco): reset and prove world convergence"
```

---

### Task 10: Migrate Profile, Checkpoint, Runtime Factory, and Launch Behavior

**Files:**
- Modify: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/profile.py`
- Modify: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/checkpoint.py`
- Modify: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/runtime.py`
- Modify: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/live_execute.py`
- Modify: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/cli/pick_place_state_machine.py`
- Modify: `src/so101_gazebo_demo_py/launch/so101_pick_place.launch.py`
- Modify: `src/so101_gazebo_demo_py/launch/so101_controller.launch.py`
- Modify: `src/so101_gazebo_demo_py/test/test_checkpoint.py`
- Modify: `src/so101_gazebo_demo_py/test/test_profile.py`
- Modify: `src/so101_gazebo_demo_py/test/test_runtime_registration.py`
- Modify: `src/so101_gazebo_demo_py/test/test_launch_contract.py`
- Create: `src/so101_gazebo_demo_py/test/test_mujoco_runtime_contract.py`

**Interfaces:**
- Consumes: `simulation_backend := gazebo|mujoco` during migration.
- Produces: backend-neutral profile, checkpoint schema v5, `MujocoRuntime`, unchanged public run modes/states/errors where not simulator-specific.

- [ ] **Step 1: Write RED schema-v5 and runtime-factory tests**

Expected schema-v5 fields:

```python
ExpectedWorldState(
    simulator_backend="mujoco",
    simulator_task_object_pose_world=pose,
    simulator_task_object_constrained=False,
    simulator_task_object_stationary=True,
)
```

Tests require:

- v5 writes no `gazebo_*` keys;
- v4 with `gazebo_task_object_attached in {None, False}` migrates to v5;
- v4 with `gazebo_task_object_attached is True` refuses resume;
- backend/session/policy mismatch refuses resume;
- active release epoch remains non-resumable;
- `create_runtime("mujoco")` uses only MuJoCo observer/reset plus existing MoveIt/controller clients;
- `create_runtime("gazebo")` still satisfies characterization during migration;
- dry-run creates neither backend;
- unknown backend fails with `SIMULATION_BACKEND_INVALID`.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q \
  src/so101_gazebo_demo_py/test/test_checkpoint.py \
  src/so101_gazebo_demo_py/test/test_profile.py \
  src/so101_gazebo_demo_py/test/test_runtime_registration.py \
  src/so101_gazebo_demo_py/test/test_mujoco_runtime_contract.py \
  src/so101_gazebo_demo_py/test/test_launch_contract.py
```

- [ ] **Step 3: Implement checkpoint migration and profile endpoints**

Increment schema from 4 to 5. Reader accepts exactly schema 4 or 5; writer emits 5 only. Preserve atomic write/fsync behavior and all existing failure codes, adding:

```text
CHECKPOINT_SIMULATOR_BACKEND_MISMATCH
CHECKPOINT_LEGACY_CONSTRAINT_UNSAFE
```

Profile adds `simulation_backend`, `simulation_evidence_topic`, `reset_service`, `pause_service`, `step_service`. Gazebo attachment topics remain only in a `GazeboProfile` used by the migration adapter and disappear at Task 15.

- [ ] **Step 4: Implement runtime factory and launch routing**

`so101_pick_place.launch.py` adds `simulation_backend` defaulting to `gazebo` during A/B. When `start_simulation:=true`, it includes exactly one of `so101_gazebo.launch.py` or `so101_mujoco.launch.py`. It rejects `execute` with `start_simulation:=false`; dry-run remains simulator-free.

The MoveIt plan/execution, workflow, Planning Scene and final-outcome modules remain shared. Remove no Gazebo code in this task.

- [ ] **Step 5: Run GREEN, full Python suite and build**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test
source /opt/ros/jazzy/setup.zsh
# Source locked dependency overlay if selected.
colcon build --packages-select so101_mujoco_support so101_gazebo_demo_py --symlink-install
source install/setup.zsh
ros2 launch so101_gazebo_demo_py so101_pick_place.launch.py --show-args
```

Expected arguments include exact existing run/checkpoint/session controls plus `simulation_backend`.

- [ ] **Step 6: Commit**

```bash
git add -- src/so101_gazebo_demo_py/so101_gazebo_demo_py/profile.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/checkpoint.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/runtime.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/live_execute.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/cli/pick_place_state_machine.py src/so101_gazebo_demo_py/launch/so101_pick_place.launch.py src/so101_gazebo_demo_py/launch/so101_controller.launch.py src/so101_gazebo_demo_py/test/test_checkpoint.py src/so101_gazebo_demo_py/test/test_profile.py src/so101_gazebo_demo_py/test/test_runtime_registration.py src/so101_gazebo_demo_py/test/test_launch_contract.py src/so101_gazebo_demo_py/test/test_mujoco_runtime_contract.py
git diff --cached --check
git commit -m "feat(so101_mujoco): route workflow through simulator backend"
```

---

### Task 11: Prove MoveIt, Controller, TF, Scene, and MuJoCo Boundaries Headlessly

**Files:**
- Create: `src/so101_gazebo_demo_py/test/headless/run_mujoco_motion_e2e.sh`
- Create: `src/so101_gazebo_demo_py/test/headless/assert_mujoco_motion_evidence.py`
- Create: `src/so101_gazebo_demo_py/test/headless/test_mujoco_moveit_live.py`
- Modify: `src/so101_gazebo_demo_py/test/test_moveit_planning.py`
- Modify: `src/so101_gazebo_demo_py/test/test_moveit_scene.py`
- Modify: `docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md`

**Interfaces:**
- Consumes: installed MuJoCo stack, `/plan_kinematic_path`, `/execute_trajectory`, controller actions, joint states, TF, Planning Scene, atomic simulation evidence.
- Produces: a machine-readable L1–L4 boundary evidence JSON without performing a grasp.

- [ ] **Step 1: Write RED evidence assertions**

The assertion tool rejects missing or stale fields and requires:

```text
provenance.source_commit == current HEAD
provenance.mjcf_sha256 == installed scene SHA-256
ros_graph.controller_manager_count == 1
ros_graph.mujoco_service_node_count == 1
moveit.plan_error_code == SUCCESS
moveit.execute_error_code == SUCCESS
controller.arm_result == SUCCEEDED
controller.gripper_result == SUCCEEDED
joints.max_target_error_rad <= 0.001
tf.tcp_linear_delta_m > 0.001
scene.world_objects contains plastic_cup
scene.attached_objects does not contain plastic_cup
mujoco.object_pose_finite == true
mujoco.object_constraint_count == 0
```

The script must also prove there is no object mutation service/topic and no equality/adhesion in installed MJCF.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/headless/test_mujoco_moveit_live.py
```

Expected: test harness/evidence missing.

- [ ] **Step 3: Implement bounded staged motion test**

The script:

1. creates one evidence directory beneath `/tmp/so101-debug-mujoco-migration/`;
2. records commit/status, dependency lock, installed prefixes and file hashes;
3. launches one headless MuJoCo/controller/MoveIt stack on a new ROS domain;
4. waits on typed service/action/topic readiness;
5. calls reset and proves its JSON;
6. runs `plan_only` through `MOVE_ABOVE_OBJECT`;
7. runs execute only through `MOVE_ABOVE_OBJECT`, then returns home;
8. samples joint/TF/object pose before and after;
9. queries Planning Scene before and after;
10. stops only owned processes and writes exit codes.

This task never closes on the cup and never enters contact calibration.

- [ ] **Step 4: Preregister and run `EXP-MOTION-001`**

Use `lifecycle: FULL_RESTART`, fixed commit/policy/MJCF and exact pass/fail/invalid criteria. Run the installed script with a bounded timeout. Mark the ledger result before changing code.

- [ ] **Step 5: Run GREEN and commit**

```bash
python3 src/so101_gazebo_demo_py/test/headless/assert_mujoco_motion_evidence.py /tmp/so101-debug-mujoco-migration/exp-motion-001/evidence.json
PYTHONNOUSERSITE=1 colcon test --packages-select so101_mujoco_support so101_gazebo_demo_py --event-handlers console_direct+
colcon test-result --verbose
git add -- src/so101_gazebo_demo_py/test/headless src/so101_gazebo_demo_py/test/test_moveit_planning.py src/so101_gazebo_demo_py/test/test_moveit_scene.py docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md
git diff --cached --check
git commit -m "test(so101_mujoco): prove motion and scene boundaries"
```

---

### Task 12: Calibrate MuJoCo Contact Evidence Without Changing Release Policy

**Files:**
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/mujoco/contact_calibration.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/cli/calibrate_mujoco_contacts.py`
- Create: `src/so101_gazebo_demo_py/test/test_mujoco_contact_calibration.py`
- Create during implementation: `docs/experiments/so101-mujoco-contact-calibration-report.md`
- Create during implementation: `docs/experiments/so101-mujoco-contact-calibration-report.json`
- Modify: `src/so101_gazebo_demo_py/setup.py`
- Modify: `docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md`

**Interfaces:**
- Consumes: labeled windows of atomic simulation evidence.
- Produces: immutable calibration dataset hashes, classification matrix and a proposed `minimum_normal_force_n` / `maximum_penetration_m`; does not modify runtime policy.

- [ ] **Step 1: Write RED statistical-contract tests**

Use fixed synthetic labeled windows for `NO_CONTACT`, `FIXED_ONLY`, `MOVING_ONLY`, `BILATERAL_UNSTABLE`, `BILATERAL_MICRO_LIFT_SUCCESS`, `BILATERAL_MICRO_LIFT_FAILURE`.

The selector evaluates candidate thresholds formed only from observed finite values plus force floor `0.01 N`. A candidate is eligible only when leave-one-run-out evaluation has:

- zero positive predictions in `NO_CONTACT`, `FIXED_ONLY`, `MOVING_ONLY`;
- every `BILATERAL_MICRO_LIFT_SUCCESS` window positive;
- every positive window has both configured fingertip geom groups;
- no truncated/stale sample;
- `maximum_penetration_m` does not accept any sample labeled geometry-invalid.

When multiple candidates remain, sort by highest minimum normalized separation margin, then highest force threshold, then lowest penetration ceiling. If none remain, return `CALIBRATION_NO_SEPARATING_THRESHOLD`; never relax the criteria.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_mujoco_contact_calibration.py
```

- [ ] **Step 3: Implement pure selection/report generation**

The CLI only reads JSONL evidence files and a label manifest; it cannot command controllers or edit YAML. It writes equivalent Markdown and canonical JSON reports. Output includes:

- source commit, policy fingerprint, MJCF/dependency hashes;
- per-run lifecycle and label;
- force/distance distributions;
- every evaluated candidate and confusion matrix;
- deterministic selected proposal or explicit no-separation result;
- SHA-256 of every raw input file.

The JSON report schema is:

```json
{
  "schema_version": 1,
  "selected_candidate": {
    "minimum_normal_force_n": 0.01,
    "maximum_penetration_m": 0.0005
  },
  "authorization": {"status": "pending"}
}
```

The two numbers shown here belong only to the unit-test fixture. Live report values must be computed from collected evidence and may differ.

- [ ] **Step 4: Run unit GREEN**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_mujoco_contact_calibration.py
```

- [ ] **Step 5: Preregister and collect calibration runs**

Create one experiment ID per labeled condition. Each condition uses at least 3 independent `RESET_WORLD` runs and 100 consecutive 100 Hz samples after the condition stabilizes. Change only the named contact condition; keep commit, MJCF, friction, timestep, controller gains and all policy values fixed.

For micro-lift labels, outcome is determined by measured cup displacement and drift, never by contact itself. A run with missing evidence, duplicate stack, truncation or reset failure is `INVALID` and recollected under a new ID.

- [ ] **Step 6: Generate the proposal and stop at the authorization gate**

Run the installed calibration CLI, write the report, inspect raw hashes and classification matrix, and append a ledger checkpoint:

```text
status: CONTACT_THRESHOLDS_PROPOSED_AWAITING_USER_AUTHORIZATION
next_command: NONE
```

Present the exact proposed force/distance values and false-positive/false-negative matrix to the user. Do not modify validation policy or continue to Task 13 until the user explicitly authorizes the values.

- [ ] **Step 7: Commit only tooling/report/ledger**

```bash
git add -- src/so101_gazebo_demo_py/so101_gazebo_demo_py/mujoco/contact_calibration.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/cli/calibrate_mujoco_contacts.py src/so101_gazebo_demo_py/test/test_mujoco_contact_calibration.py src/so101_gazebo_demo_py/setup.py docs/experiments/so101-mujoco-contact-calibration-report.md docs/experiments/so101-mujoco-contact-calibration-report.json docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md
git diff --cached --check
git commit -m "test(so101_mujoco): propose contact evidence thresholds"
```

---

### Task 13: Integrate the Authorized Physical Grasp and Final Outcome Path

**Files:**
- Create: `src/so101_gazebo_demo_py/config/validation_policies/light_cup_wall_pick_mujoco.yaml`
- Modify: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/policy_config.py`
- Modify: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/live_execute.py`
- Modify: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/physical_outcome.py`
- Modify: `src/so101_gazebo_demo_py/launch/so101_pick_place.launch.py`
- Create: `src/so101_gazebo_demo_py/test/test_mujoco_physical_grasp_contract.py`
- Create: `src/so101_gazebo_demo_py/test/headless/assert_mujoco_pick_place_evidence.py`
- Create: `src/so101_gazebo_demo_py/test/headless/run_mujoco_pick_place_e2e.sh`
- Modify: `src/so101_gazebo_demo_py/test/test_live_physical_outcome_contract.py`
- Modify: `src/so101_gazebo_demo_py/test/test_physical_outcome.py`
- Modify: `src/so101_gazebo_demo_py/test/test_outcome_first_continuation.py`
- Modify: `src/so101_gazebo_demo_py/test/test_post_retreat_final_outcome.py`
- Modify: `src/so101_gazebo_demo_py/test/test_main_strategy_parity.py`
- Modify: `docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md`

**Interfaces:**
- Consumes: user-authorized MuJoCo contact thresholds and existing motion/final-outcome policy.
- Produces: physical micro-lift/carry/release/final outcome using MuJoCo evidence, with zero simulator constraint and zero object mutation.

- [ ] **Step 1: Record authorization and write RED physical-contract tests**

Before editing policy, append the user-authorized exact values and authorization timestamp/reference to the ledger.

Tests require:

- bilateral contact uses configured fixed/moving geom sets, authorized force floor and penetration ceiling;
- contact alone cannot pass physical grasp;
- 2 mm micro-lift requires measured cup axial progress and bounded lateral drift in the same session;
- missing/stale/truncated evidence fails closed;
- Planning Scene attach may occur only after physical micro-lift proof;
- simulator constraint remains false before/during/after carry;
- no object mutation service/call exists;
- final outcome uses MuJoCo pose/twist/support/gripper contacts and existing in-region/upright/stability/controller gates;
- Gazebo threshold constants do not appear in the MuJoCo validation policy.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q \
  src/so101_gazebo_demo_py/test/test_mujoco_physical_grasp_contract.py \
  src/so101_gazebo_demo_py/test/test_live_physical_outcome_contract.py \
  src/so101_gazebo_demo_py/test/test_physical_outcome.py
```

- [ ] **Step 3: Implement the MuJoCo validation policy and reducers**

Load `selected_candidate.minimum_normal_force_n` and `selected_candidate.maximum_penetration_m` from the canonical calibration JSON whose SHA-256 was authorized by the user. Copy those two JSON numbers byte-for-byte into the MuJoCo policy, set `simulation_backend: mujoco`, `require_fixed_and_moving: true` and `reject_truncated: true`, and record the report SHA-256 plus authorization reference in policy metadata. Do not invent, round or hand-retune either number. The policy loader rejects a MuJoCo policy with missing authorization metadata, report-hash mismatch or a Gazebo-only field.

Reuse existing `evaluate_continuation` and final placement semantics. Adapter code supplies normalized evidence; do not duplicate the state machine.

- [ ] **Step 4: Run unit GREEN and full package tests**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test
source /opt/ros/jazzy/setup.zsh
# Source locked dependency overlay if selected.
colcon build --packages-select so101_mujoco_support so101_gazebo_demo_py --symlink-install
source install/setup.zsh
PYTHONNOUSERSITE=1 colcon test --packages-select so101_mujoco_support so101_gazebo_demo_py --event-handlers console_direct+
colcon test-result --verbose
```

- [ ] **Step 5: Run staged live states before a full task**

Use separate preregistered experiments and one variable per run:

1. execute through `DESCEND` and prove no forbidden contact;
2. execute through `CLOSE_GRIPPER` and prove authorized bilateral evidence;
3. execute through `VERIFY_PHYSICAL_GRASP` and prove cup micro-lift displacement;
4. execute through `LIFT` and prove cup carry plus Planning Scene shadow;
5. execute full release/final outcome.

At every boundary record controller result, joints/TF, object pose/twist, contact samples and scene membership. A failure at an earlier stage blocks later stages.

- [ ] **Step 6: Obtain one GUI-observed valid final success**

Only after headless staged gates pass, launch a GUI stack in an owned tmux session after `source ~/gui-env.zsh`. Capture fresh MuJoCo and RViz views before and after the task. The valid success must show and numerically prove:

- cup physically lifts and moves without weld/teleport;
- gripper visibly closes/opens;
- final cup is in-region, upright, stable, table-supported and gripper-free;
- Planning Scene shadow is detached and world pose resynchronized;
- state machine exits 0 at `DONE`.

- [ ] **Step 7: Commit the validated path**

```bash
git add -- src/so101_gazebo_demo_py/config/validation_policies/light_cup_wall_pick_mujoco.yaml src/so101_gazebo_demo_py/so101_gazebo_demo_py/policy_config.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/live_execute.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/physical_outcome.py src/so101_gazebo_demo_py/launch/so101_pick_place.launch.py src/so101_gazebo_demo_py/test/test_mujoco_physical_grasp_contract.py src/so101_gazebo_demo_py/test/headless/assert_mujoco_pick_place_evidence.py src/so101_gazebo_demo_py/test/headless/run_mujoco_pick_place_e2e.sh src/so101_gazebo_demo_py/test/test_live_physical_outcome_contract.py src/so101_gazebo_demo_py/test/test_physical_outcome.py src/so101_gazebo_demo_py/test/test_outcome_first_continuation.py src/so101_gazebo_demo_py/test/test_post_retreat_final_outcome.py src/so101_gazebo_demo_py/test/test_main_strategy_parity.py docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md
git diff --cached --check
git commit -m "feat(so101_mujoco): execute physical pick place"
```

---

### Task 14: Qualify Five Full Restarts and Five World Resets

**Files:**
- Create: `src/so101_gazebo_demo_py/test/headless/run_mujoco_qualification.sh`
- Create: `src/so101_gazebo_demo_py/test/test_mujoco_qualification_contract.py`
- Modify: `docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md`
- Modify: `src/so101_gazebo_demo_py/README.md`

**Interfaces:**
- Consumes: one frozen implementation commit, dependency lock, MJCF/policy hashes and full physical-outcome script.
- Produces: two separately counted consecutive-success batches and fresh GUI evidence.

- [ ] **Step 1: Write RED qualification-runner tests**

The runner contract must enforce:

- exactly 5 `FULL_RESTART` and then exactly 5 `RESET_WORLD` slots;
- every slot has a unique experiment ID and evidence directory;
- commit, dependency provider/tag, MJCF hash, policy hash and success contract are frozen across a batch;
- `VALID failure` stops and resets the current streak;
- `INVALID` does not enter the denominator but terminates the batch; replacement uses new IDs;
- lifecycle counts are never mixed;
- a result cannot pass on state-machine `DONE` alone; all model/controller/MoveIt/MuJoCo/final/visual fields are required.

- [ ] **Step 2: Run RED, implement runner, then GREEN**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_mujoco_qualification_contract.py
```

Implement the runner as orchestration around the already installed reset/e2e/assertion tools; do not duplicate their logic. Rerun until unit test passes.

- [ ] **Step 3: Freeze release candidate provenance**

Run full unit/package tests, ensure worktree is clean, then append a preregistered batch checkpoint with exact:

```text
source_commit
dependency provider/release/commit/prefix
mujoco_vendor version
mjcf SHA-256
policy bundle SHA-256
controller YAML SHA-256
success contract
```

No parameter or code change is allowed after this checkpoint without abandoning the batch and starting new IDs.

- [ ] **Step 4: Run five consecutive FULL_RESTART qualifications**

Each run uses a new ROS domain and a newly launched owned stack. It proves no prior MuJoCo/MoveIt/controller process remains, reset postcondition passes, full pick-place passes and owned processes exit cleanly. Record exact exit codes and evidence hashes.

- [ ] **Step 5: Run five consecutive RESET_WORLD qualifications**

Use one healthy owned stack, but run the full reset proof before every task. Do not count the Task 9 reset tests as pick-place qualification. Apply the same valid/invalid streak rules.

- [ ] **Step 6: Perform final GUI/RViz visual acceptance**

On the frozen commit, run one additional non-counted GUI demonstration. Use current GNOME env via `~/gui-env.zsh`, capture fresh screenshots and actually inspect:

- SO-101 initial/final joint posture;
- gripper open/close;
- cup initial, carry and final pose;
- no visible interpenetration, weld-like lag or drop;
- RViz Planning Scene shadow attached only during carry and world-only at end.

Link screenshot paths and hashes to the ledger; GUI appearance alone does not replace numeric evidence.

- [ ] **Step 7: Update README status, test and commit**

README may state qualification only if both streaks passed. Include exact commit/hash/batch IDs, run commands and known simulation-only scope.

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test
PYTHONNOUSERSITE=1 colcon test --packages-select so101_mujoco_support so101_gazebo_demo_py --event-handlers console_direct+
colcon test-result --verbose
git add -- src/so101_gazebo_demo_py/test/headless/run_mujoco_qualification.sh src/so101_gazebo_demo_py/test/test_mujoco_qualification_contract.py docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md src/so101_gazebo_demo_py/README.md
git diff --cached --check
git commit -m "test(so101_mujoco): qualify simulator migration"
```

---

### Task 15: Cut Over the Public Package and Remove Gazebo Runtime Dependencies

**Precondition:** Task 14 has two valid five-run streaks and final GUI/RViz acceptance on the frozen release candidate. If not, this task is forbidden.

**Files:**
- Rename: `src/so101_gazebo_demo_py/` → `src/so101_mujoco_demo_py/`
- Rename Python namespace/resource marker: `so101_gazebo_demo_py` → `so101_mujoco_demo_py`
- Delete from the renamed package: `gazebo/`, Gazebo-only launch/model/world/CLI/test-support files and Gazebo-only tests.
- Modify: renamed `package.xml`, `setup.py`, `setup.cfg`, launch files, URDF package URIs, configs, README, provenance and remaining tests.
- Modify: `docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md`
- Create: `src/so101_mujoco_demo_py/test/test_final_mujoco_package_independence.py`

**Interfaces:**
- Consumes: qualified migration package.
- Produces: standalone installed package `so101_mujoco_demo_py`, public launch `so101_pick_place.launch.py`, console scripts with existing functional names, no Gazebo runtime dependency.

- [ ] **Step 1: Write RED final-independence tests before rename**

The test requires:

```python
assert package_name == "so101_mujoco_demo_py"
assert build_type == "ament_python"
assert forbidden_dependencies.isdisjoint({
    "ros_gz_sim", "ros_gz_bridge", "ros_gz_interfaces",
    "gz_ros2_control", "gz.transport13", "gz.msgs10",
})
assert installed_launches >= {
    "so101_display.launch.py", "so101_controller.launch.py",
    "so101_moveit.launch.py", "so101_move_group_headless.launch.py",
    "so101_mujoco.launch.py", "so101_pick_place.launch.py",
}
```

Scan runtime source/config/launch/URDF for imports, package URIs and executable references to `so101_gazebo_demo_py`, `ros_gz`, `gz_ros2_control`, Gazebo transport, attach/detach relay or Gazebo world files. Historical docs/ledger are excluded from this runtime scan and retained.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q src/so101_gazebo_demo_py/test/test_final_mujoco_package_independence.py
```

- [ ] **Step 3: Perform the mechanical rename with targeted patches**

Use `git mv` for the package directory, Python namespace and resource marker. Update:

- package name and all Python imports;
- setup entry points/data files;
- package URIs in Xacro/RViz/MJCF provenance;
- launch package names;
- installed asset lookups;
- test import paths and commands;
- README commands.

Keep public console script names such as `pick_place_state_machine` and `reset_so101_mujoco_world`.

- [ ] **Step 4: Remove Gazebo-only runtime paths and dependencies**

Remove:

```text
so101_mujoco_demo_py/gazebo/
so101_mujoco_demo_py/test_support/ros_gazebo_backend.py
launch/so101_gazebo.launch.py
models/so101_prepared.sdf
worlds/so101_pick_place.sdf
cli/gazebo_attachment_state_relay.py
Gazebo attach/detach tests and headless scripts
```

Collapse the xacro backend conditional to only `mujoco_ros2_control/MujocoSystemInterface`. Change `simulation_backend` default/final accepted value to `mujoco`; preserve a clear `SIMULATION_BACKEND_INVALID` error for any other value.

Do not delete project-level historical specs, plans, ledgers or the separate Gazebo reference branch.

- [ ] **Step 5: Run final source GREEN**

```bash
python3 -m pytest -q src/so101_mujoco_demo_py/test
rg -n 'ros_gz|gz_ros2_control|gz\.transport|gazebo_attachment|so101_gazebo_demo_py' \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py \
  src/so101_mujoco_demo_py/launch \
  src/so101_mujoco_demo_py/urdf \
  src/so101_mujoco_demo_py/config \
  src/so101_mujoco_demo_py/package.xml \
  src/so101_mujoco_demo_py/setup.py
```

Expected: pytest passes; `rg` returns no runtime references.

- [ ] **Step 6: Prove a clean installed package**

Build into a fresh task-specific build/install/log root without deleting the existing overlay:

```bash
source /opt/ros/jazzy/setup.zsh
# Source locked dependency overlay if selected.
colcon build \
  --base-paths src/so101_mujoco_support src/so101_mujoco_demo_py \
  --build-base /tmp/so101-debug-mujoco-migration/final-build \
  --install-base /tmp/so101-debug-mujoco-migration/final-install \
  --log-base /tmp/so101-debug-mujoco-migration/final-log \
  --symlink-install
source /tmp/so101-debug-mujoco-migration/final-install/setup.zsh
ros2 pkg prefix so101_mujoco_demo_py
ros2 pkg executables so101_mujoco_demo_py
ros2 launch so101_mujoco_demo_py so101_pick_place.launch.py --show-args
PYTHONNOUSERSITE=1 colcon test \
  --base-paths src/so101_mujoco_support src/so101_mujoco_demo_py \
  --build-base /tmp/so101-debug-mujoco-migration/final-build \
  --install-base /tmp/so101-debug-mujoco-migration/final-install \
  --log-base /tmp/so101-debug-mujoco-migration/final-test-log \
  --packages-select so101_mujoco_support so101_mujoco_demo_py \
  --event-handlers console_direct+
colcon test-result --test-result-base /tmp/so101-debug-mujoco-migration/final-build --verbose
```

Then run one non-counted final headless reset + full pick-place from this fresh install and assert the same release-candidate evidence contract. A rename/install-only failure blocks completion.

- [ ] **Step 7: Final ledger checkpoint and commit**

Update the ledger `current_commit`, final package prefix, dependency lock, installed hashes, test counts, final non-counted run and `next_experiment: NONE`.

```bash
git add -- src/so101_mujoco_demo_py src/so101_mujoco_support docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md
git diff --cached --check
git diff --cached --name-status
git commit -m "refactor(so101_mujoco): complete simulator cutover"
```

Do not push or merge. Report the local commit, preserved Gazebo branch, test/runtime/visual evidence and remaining simulation-only limitations to the user.
