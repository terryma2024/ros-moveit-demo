# SO-101 Adaptive Pick-Place Experiment Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `so101_gazebo_demo_py` 包内实现一个确定性、自适应分批的实验规划器（adaptive batched experiment planner），驱动完整 SO-101 物理 pick-place 从首个失败节点逐节点推进到冻结版本的最终验收（FULL_RESTART×5 + RESET_WORLD×5）。

**Architecture:** 纯 Python CLI（YAGNI，无 DB/Web）。动作图（ActionGraph）声明完整 pick-place 路径节点；参数注册表（ParameterRegistry）登记带 provenance 的批准边界；候选生成器（CandidateGenerator）按 50/30/20 wave 策略产出确定性候选；约束引擎（ConstraintEngine）做范围/依赖/plan-only/去重准入；候选以不可变 YAML+SHA 固化后经 lane 隔离执行；评估器（StageEvaluator）把真实物理证据分类为失败类别或可行评分；台账（ExperimentLedger）单写者 append-only。设计依据：`docs/superpowers/specs/2026-08-09-so101-adaptive-pick-place-experiment-planner-design.md`（commit `ded3364` 起）。

**Tech Stack:** Python 3.12、pytest、PyYAML、ROS 2 Jazzy、Gazebo Harmonic、MoveIt 2、colcon（`--symlink-install`）、tmux。不引入任何新第三方依赖。

## Global Constraints

- **本轮不执行**：本 plan 这一轮只写文档；所有 task 中的命令均为未来执行说明。任何 implementation/live/push/merge 仍需后续执行授权；计划完成不等于开始实施。
- **执行前置（Execution Setup Gate，未来执行时先做，本轮不做）**：
  - 实施时必须先用 superpowers:using-git-worktrees，从包含本 plan 的 `codex/so101-gazebo-demo-py` 最新 commit 创建干净分支/worktree：`codex/so101-adaptive-experiment-planner` / `/data/work/ws_moveit/.worktrees/so101-adaptive-experiment-planner`。
  - 当前原 worktree（`/data/work/ws_moveit/.worktrees/so101-gazebo-demo-py`）的六条 dirty paths 是历史工作，必须原样保留，不得 stash/reset/clean/复制到新 worktree：
    `M src/so101_gazebo_demo_py/config/so101_controllers.yaml`、`M .../config/task_objects/light_plastic_cup.yaml`、`M .../config/validation_policies/light_cup_wall_pick.yaml`、`M .../docs/provenance.json`、`M .../test/test_provenance.py`、`?? .../test/test_main_strategy_parity.py`。
  - 实施阶段需用 so101-dev skill；恢复 ledger checkpoint、source/install/runtime provenance、进程所有权确认后才允许任何 build/live。
- Gazebo 接触物理从 CLOSE_GRIPPER 到 OPEN_GRIPPER 始终拥有杯子真实运动；**禁止 forward Gazebo attach**。MoveIt Planning Scene attach/detach 仅作固定生命周期的 planning shadow（collision-planning shadow），不是搜索变量。
- 冻结 physics engine、geometry、mass/friction、controller/gains、collision 规则：不可搜索、不可修改。
- `penetration_target` 范围 `[0.0001, 0.001]` m；`0.001` m 是 global hard max。历史 `0.0013` m solver-limit fingerprint（ledger `CP-QUALIFICATION-FINGERPRINT-002`）全部结果历史隔离，不计入新搜索/qualification/五连验收。
- 最终验收的 tolerance/观测窗口/速度阈值 frozen；仅执行侧 settle wait（稳定等待时长）可搜索。
- MICRO_LIFT 成功合同：杯子完整 position+orientation 进入固定容差、已脱离桌面/非预期支撑、固定观测窗口内持续满足位姿/线速度/角速度阈值、运动由 Gazebo 接触物理产生；不得仅凭命令成功、TCP 运动或 world-Z delta 判成功。
- FINAL_STABLE 必须在 RETREAT 完成后重新采样判定；`WAIT_RELEASE_SETTLE`/`VALIDATE_FINAL_PLACEMENT` 的预撤离成功不能替代 post-retreat final outcome。
- 并发 screening 最多 3 lane，lane 间候选用 RESET_WORLD 隔离；最终 FULL_RESTART×5 与 RESET_WORLD×5 必须串行、同一冻结 commit/policy fingerprint、生命周期不混算（INVALID 不计数但结束批次，VALID_FAILURE 终止 streak）。
- `ROS_DOMAIN_ID` 必须 ≤ 232（FastDDS 上限；历史 INVALID：EXP-QUAL2-PLAN-234、EXP-QUAL2-GRASP-1-233）。
- 进程清理只允许 exact owned PIDs（TERM→读回→同 PID 存活才 KILL）；禁止 pkill/killall/宽泛匹配；preserved 进程（如 PID 3272995 gz sim server、652055 clang-tidy、tmux codex/codex-cua）永远不可触碰。
- 不运行 `ament_uncrustify --reformat`；格式问题用定向 patch。
- 每个 live task 本轮不执行；未来执行时遵守 so101-dev 的 ledger/provenance/GUI 证据门。

## File Structure

```
src/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/
    __init__.py              # 包导出（Task 2）
    model.py                 # 枚举/冻结 dataclass：ParameterMode, CandidateStatus, FailureCategory,
                             # ActionNodeSpec, ParameterSpec, Candidate, StageEvidence, StageEvaluation (Task 2)
    action_graph.py          # build_so101_action_graph() 完整路径节点声明 (Task 2)
    registry.py              # ParameterRegistry YAML schema/loader (Task 3)
    materializer.py          # 不可变候选 YAML + SHA、evaluation_only 规则 (Task 4)
    candidate_generator.py   # generate_wave() 确定性 50/30/20 (Task 5)
    constraints.py           # PlanOnlyProbe Protocol, admit_candidate() (Task 6)
    evaluator.py             # 证据解析、失败分类、maximin 排序、MICRO_LIFT 合同 (Task 7, 13)
    ledger.py                # 候选 YAML + 结果 JSONL 单写者台账 (Task 8)
    reset_contract.py        # RESET_WORLD 九项 proof (Task 9)
    supervisor.py            # lane/资源/domain/磁盘守卫 (Task 10)
    live_adapter.py          # 复用 pick_place_state_machine 的执行包装 (Task 12)
src/so101_gazebo_demo_py/so101_gazebo_demo_py/cli/experiment_planner.py  # CLI (Task 11)
src/so101_gazebo_demo_py/config/experiment_spaces/light_cup_wall_pick.yaml  # 参数空间登记 (Task 3)
src/so101_gazebo_demo_py/test/test_experiment_planner_*.py               # 每个 task 的 focused 测试
```

既有文件仅在对应 task 到达时修改：`gazebo/observer.py`（Task 1）、`policy_config.py`（Task 1, 4）、`setup.py`（Task 11）、`cli/pick_place_state_machine.py` / `live_execute.py`（Task 12, 13）、`physical_outcome.py`（Task 13）、`gazebo/reset.py`（Task 9）、validation YAML 与 provenance 测试（Task 1）。

---

### Task 1: Clean execution worktree + penetration contract gate（0.001 m hard max 入 runtime validation）

**Files:**
- Modify: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/gazebo/observer.py:9-16`（常量与注释）
- Modify: `src/so101_gazebo_demo_py/test/test_gazebo_attachment.py:73-90`（断言新常量）
- Modify: `src/so101_gazebo_demo_py/test/test_live_physical_outcome_contract.py`（hard-ceiling 边界用例）
- Modify: `src/so101_gazebo_demo_py/test/test_main_strategy_parity.py`（若存在于新 worktree 则同步字面量；不存在则跳过）
- Modify: `docs/experiments/so101-gazebo-demo-py-experiment-ledger.md`（append-only 历史隔离声明）

**Interfaces:**
- Consumes: 现有 `MOVING_PAD_MESH_PENETRATION_CEILING_M`（当前 0.0013，历史 solver-limit 语义）。
- Produces: `MOVING_PAD_MESH_PENETRATION_CEILING_M = 0.001`（新 fingerprint 唯一合法验收上限）；后续所有 task 的 gate 均以 0.001 m 为准。

**前置（未来执行时先做，本轮不做）**：完成 Global Constraints 的 Execution Setup Gate（新 worktree `codex/so101-adaptive-experiment-planner`）；本 task 全部操作只在新 worktree 进行，不操作当前 dirty worktree。

- [ ] **Step 1: 写 RED 测试——新 fingerprint 的验收上限必须恰好 0.001 m**

在 `src/so101_gazebo_demo_py/test/test_gazebo_attachment.py` 修改常量断言，并新增历史隔离测试：

```python
def test_penetration_ceiling_is_recontracted_hard_max() -> None:
    assert MOVING_PAD_MESH_PENETRATION_CEILING_M == 0.001
    assert SOLVER_REPORTED_CONTACT_DEPTH_LIMIT_M == 0.0013


def test_solver_limit_fingerprint_is_not_acceptance_ceiling() -> None:
    # 历史 0.0013 solver-limit 语义只能留在台账证据里，不得成为验收 gate。
    assert MOVING_PAD_MESH_PENETRATION_CEILING_M != SOLVER_REPORTED_CONTACT_DEPTH_LIMIT_M
```

（测试名按仓库既有 snake_case 惯例落定；断言内容不变。）

- [ ] **Step 2: 运行确认 RED**

Run: `cd src/so101_gazebo_demo_py && python3 -m pytest -q test/test_gazebo_attachment.py -k penetration`
Expected: FAIL（`assert 0.0013 == 0.001`）

- [ ] **Step 3: 最小实现——常量改为 0.001 并更新注释**

```python
# New-contract hard max (2026-08-09 adaptive planner, spec section 2): the acceptance
# ceiling equals the penetration_target global hard max 0.001 m. The historical 0.0013 m
# solver-limit fingerprint is evidence-only and never qualifies a grasp.
MOVING_PAD_MESH_PENETRATION_CEILING_M = 0.001
SOLVER_REPORTED_CONTACT_DEPTH_LIMIT_M = 0.0013
```

- [ ] **Step 4: 同步边界用例并跑 focused + 全量**

把 `test_gazebo_attachment.py` 中 `(0.0013,)` 样例深度改 `(0.001,)`，`test_live_physical_outcome_contract.py` 的越界深度 `0.001300001` 改 `0.001000001`。
Run: `python3 -m pytest -q test`（先 `source /opt/ros/jazzy/setup.bash && source install/setup.bash`）
Expected: 全量 PASS（基线 141 passed, 2 skipped 之上只允许净增，不允许回退）。

- [ ] **Step 5: ledger 追加历史隔离声明**

向 `docs/experiments/so101-gazebo-demo-py-experiment-ledger.md` append 一段 yaml checkpoint：声明 `CP-QUALIFICATION-FINGERPRINT-002`（0.0013 solver-limit）下全部结果仅作历史证据，新 fingerprint 验收上限 0.001 m。

- [ ] **Step 6: Rebuild + provenance + Commit**

```bash
source /opt/ros/jazzy/setup.bash && colcon build --packages-select so101_gazebo_demo_py --symlink-install
sha256sum build/so101_gazebo_demo_py/so101_gazebo_demo_py/gazebo/observer.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/gazebo/observer.py  # 必须一致
git add src/so101_gazebo_demo_py/so101_gazebo_demo_py/gazebo/observer.py src/so101_gazebo_demo_py/test/test_gazebo_attachment.py src/so101_gazebo_demo_py/test/test_live_physical_outcome_contract.py docs/experiments/so101-gazebo-demo-py-experiment-ledger.md
git commit -m "fix(so101_py): gate penetration acceptance at 0.001 m hard max"
```

---

### Task 2: Planner domain model + ActionGraph

**Files:**
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/__init__.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/model.py`
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/action_graph.py`
- Test: `src/so101_gazebo_demo_py/test/test_experiment_planner_action_graph.py`

**Interfaces:**
- Consumes: `so101_gazebo_demo_py.domain.State`（现有 20 态枚举）。
- Produces（后续 task 依赖的精确签名）:
  - `ParameterMode(Enum)`: `SEARCHABLE`, `FROZEN`, `VALIDATION`
  - `CandidateStatus(Enum)`: `INVALID_CANDIDATE`, `INVALID_ENVIRONMENT`, `VALID_FAILURE`, `PROVISIONAL_FEASIBLE`, `PROMOTED_ANCHOR`
  - `FailureCategory(Enum)`: `PLAN_IK_COLLISION`, `MISS_CONTACT`, `CONTACT_NO_LIFT`, `SLIP`, `TARGET_MISS`, `UNSTABLE`
  - `ActionNodeSpec`（frozen dataclass）: `state: State`, `preconditions: tuple[str, ...]`, `goal: str`, `searchable_keys: tuple[str, ...]`, `fixed_constraints: tuple[str, ...]`, `observables: tuple[str, ...]`, `success_criteria: tuple[str, ...]`, `failure_classes: tuple[FailureCategory, ...]`, `min_stop_after: str | None`, `reset_rule: str`, `reopenable_ancestors: tuple[State, ...]`
  - `ParameterSpec`（frozen dataclass）: `key: str`, `kind: str`, `unit: str`, `frame: str`, `default: float | tuple[float, ...] | str`, `mode: ParameterMode`, `lower: float | None`, `upper: float | None`, `allowed: tuple | None`, `step_generator: str`, `owning_node: State`, `dependencies: tuple[str, ...]`, `exclusions: tuple[str, ...]`, `hard_max: float | None`, `requires_plan_only: bool`, `eligible_interactions: tuple[str, ...]`, `provenance: str`
  - `Candidate`（frozen dataclass）: `candidate_id: str`, `wave_id: str`, `seed: int`, `values: Mapping[str, float | tuple[float, ...]]`, `evaluation_only: bool`, `sha256: str`
  - `StageEvidence`（frozen dataclass）: `state: State`, `metrics: Mapping[str, float | str | bool | None]`
  - `StageEvaluation`（frozen dataclass）: `candidate_id: str`, `status: CandidateStatus`, `first_failed_state: State | None`, `failure_category: FailureCategory | None`, `margins: Mapping[str, float]`, `reset_world_verified: bool`
  - `build_so101_action_graph() -> Mapping[State, ActionNodeSpec]`

- [ ] **Step 1: 写 RED 测试——完整路径覆盖、stop_after、可回溯祖先、恢复节点排除**

```python
from so101_gazebo_demo_py.domain import State
from so101_gazebo_demo_py.experiment_planner.action_graph import build_so101_action_graph
from so101_gazebo_demo_py.experiment_planner.model import FailureCategory


def test_action_graph_covers_complete_success_path() -> None:
    graph = build_so101_action_graph()
    expected_order = [
        State.IDLE, State.PREPARE_OPEN_GRIPPER, State.MOVE_ABOVE_OBJECT,
        State.DESCEND, State.CLOSE_GRIPPER, State.WAIT_GRASP_STABLE,
        State.MICRO_LIFT, State.WAIT_MICRO_LIFT_STABLE,
        State.VERIFY_PHYSICAL_GRASP, State.ATTACH_MOVEIT, State.LIFT,
        State.MOVE_ABOVE_PLACE, State.DESCEND_TO_PLACE, State.DETACH_MOVEIT,
        State.OPEN_GRIPPER, State.WAIT_RELEASE_SETTLE,
        State.VALIDATE_FINAL_PLACEMENT, State.SYNC_WORLD_OBJECT,
        State.RETREAT, State.DONE,
    ]
    assert tuple(graph) == tuple(expected_order)


def test_every_node_declares_required_fields() -> None:
    for state, node in build_so101_action_graph().items():
        assert node.state is state
        assert node.preconditions and node.goal and node.success_criteria
        assert node.observables and node.fixed_constraints
        assert node.failure_classes
        assert node.reset_rule


def test_micro_lift_stop_after_and_ancestors() -> None:
    graph = build_so101_action_graph()
    assert graph[State.MICRO_LIFT].min_stop_after == "VERIFY_PHYSICAL_GRASP"
    assert State.DESCEND in graph[State.MICRO_LIFT].reopenable_ancestors
    assert FailureCategory.CONTACT_NO_LIFT in graph[State.MICRO_LIFT].failure_classes


def test_no_recovery_node_on_success_path() -> None:
    # 恢复/重试属于失败收敛，成功路径 20 态之外不得出现 RECLOSE/RETRY 类节点。
    names = [state.value for state in build_so101_action_graph()]
    assert not any("RETRY" in name or "RECLOSE" in name for name in names)
```

- [ ] **Step 2: 运行确认 RED**

Run: `python3 -m pytest -q test/test_experiment_planner_action_graph.py`
Expected: FAIL（`ModuleNotFoundError: experiment_planner`）

- [ ] **Step 3: 实现 model.py（枚举 + 冻结 dataclass，签名见 Interfaces）**

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from ..domain import State


class ParameterMode(Enum):
    SEARCHABLE = "SEARCHABLE"
    FROZEN = "FROZEN"
    VALIDATION = "VALIDATION"


class CandidateStatus(Enum):
    INVALID_CANDIDATE = "INVALID_CANDIDATE"
    INVALID_ENVIRONMENT = "INVALID_ENVIRONMENT"
    VALID_FAILURE = "VALID_FAILURE"
    PROVISIONAL_FEASIBLE = "PROVISIONAL_FEASIBLE"
    PROMOTED_ANCHOR = "PROMOTED_ANCHOR"


class FailureCategory(Enum):
    PLAN_IK_COLLISION = "PLAN_IK_COLLISION"
    MISS_CONTACT = "MISS_CONTACT"
    CONTACT_NO_LIFT = "CONTACT_NO_LIFT"
    SLIP = "SLIP"
    TARGET_MISS = "TARGET_MISS"
    UNSTABLE = "UNSTABLE"


@dataclass(frozen=True, slots=True)
class ActionNodeSpec:
    state: State
    preconditions: tuple[str, ...]
    goal: str
    searchable_keys: tuple[str, ...]
    fixed_constraints: tuple[str, ...]
    observables: tuple[str, ...]
    success_criteria: tuple[str, ...]
    failure_classes: tuple[FailureCategory, ...]
    min_stop_after: str | None
    reset_rule: str
    reopenable_ancestors: tuple[State, ...]


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    key: str
    kind: str  # "scalar" | "vector" | "discrete"
    unit: str
    frame: str
    default: float | tuple[float, ...] | str
    mode: ParameterMode
    lower: float | None
    upper: float | None
    allowed: tuple | None
    step_generator: str
    owning_node: State
    dependencies: tuple[str, ...]
    exclusions: tuple[str, ...]
    hard_max: float | None
    requires_plan_only: bool
    eligible_interactions: tuple[str, ...]
    provenance: str


@dataclass(frozen=True, slots=True)
class Candidate:
    candidate_id: str
    wave_id: str
    seed: int
    values: Mapping[str, float | tuple[float, ...]]
    evaluation_only: bool
    sha256: str


@dataclass(frozen=True, slots=True)
class StageEvidence:
    state: State
    metrics: Mapping[str, float | str | bool | None]


@dataclass(frozen=True, slots=True)
class StageEvaluation:
    candidate_id: str
    status: CandidateStatus
    first_failed_state: State | None
    failure_category: FailureCategory | None
    margins: Mapping[str, float]
    reset_world_verified: bool
```

- [ ] **Step 4: 实现 action_graph.py**

`build_so101_action_graph()` 按 20 态顺序构造 `MappingProxyType` 有序映射；每节点填齐九个声明字段；`MICRO_LIFT` 节点 `min_stop_after="VERIFY_PHYSICAL_GRASP"`、`reopenable_ancestors=(State.DESCEND, State.CLOSE_GRIPPER, State.WAIT_GRASP_STABLE)`、`failure_classes` 含 `CONTACT_NO_LIFT` 与 `SLIP`；`ATTACH_MOVEIT`/`DETACH_MOVEIT` 的 `searchable_keys=()`（影子生命周期固定）；`VALIDATE_FINAL_PLACEMENT` 的 `success_criteria` 引用"post-retreat 重新采样后的最终位姿与稳定性"语义（与 Task 13 对齐）。

- [ ] **Step 5: 运行确认 GREEN + 全量无回退**

Run: `python3 -m pytest -q test/test_experiment_planner_action_graph.py && python3 -m pytest -q test`
Expected: focused PASS；全量 PASS 无回退。

- [ ] **Step 6: Commit**

```bash
git add src/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/__init__.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/model.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/action_graph.py src/so101_gazebo_demo_py/test/test_experiment_planner_action_graph.py
git commit -m "feat(so101_py): add planner domain model and action graph"
```

---

### Task 3: ParameterRegistry schema/loader + experiment-space YAML

**Files:**
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/registry.py`
- Create: `src/so101_gazebo_demo_py/config/experiment_spaces/light_cup_wall_pick.yaml`
- Test: `src/so101_gazebo_demo_py/test/test_experiment_planner_registry.py`

**Interfaces:**
- Consumes: `ParameterSpec`, `ParameterMode`, `build_so101_action_graph()`（Task 2）；`load_policy_bundle` 的现有锚点值（Task 1 后的 motion policy）。
- Produces:
  - `RegistryError(Exception)`（携带 `code: str`）
  - `load_parameter_registry(path: Path) -> Mapping[str, ParameterSpec]`
  - `experiment_space_path() -> Path`（指向 `config/experiment_spaces/light_cup_wall_pick.yaml` 的 installed share）

**审计批准边界（写入 YAML；除此之外一律 frozen，不虚构范围）：**
- `grasp_tcp_translation_offset_m[i]`（单轴互斥）：每轴 `baseline ± approach_outside_clearance_m`，当前 clearance `0.001` m（provenance：2026-08-07 plan 的 bounded target 授权）。
- `grasp_tcp_world_x_rotation_rad`：`|value| <= 0.08726646259971647` rad（axis tolerance）。
- `grasp_close_q6`：`[-0.059600220867817, -0.047608632840292]` rad（safe_lower_q6 到 baseline close）。
- `seating_preload_rad`：`[0.0, 0.006]` rad。
- `micro_lift_height_m`：`(0.0, 0.005)` m（小于 catastrophic relative drift 0.005 m）。
- `penetration_target_m`：`[0.0001, 0.001]` m，`hard_max=0.001`。
- waypoint count/timing/velocity-acceleration scaling、approach vector、standoff、dwell 等：登记但 `mode: FROZEN`（未完成明确审计）；验证容差/窗口/速度阈值与 Planning Scene attach lifecycle：`mode: VALIDATION` 或 `FROZEN`。

- [ ] **Step 1: 写 RED 测试——登记完整性、边界来源、frozen 纪律**

```python
from so101_gazebo_demo_py.experiment_planner.model import ParameterMode
from so101_gazebo_demo_py.experiment_planner.registry import (
    experiment_space_path, load_parameter_registry,
)


def test_registry_registers_full_parameter_tree() -> None:
    registry = load_parameter_registry(experiment_space_path())
    assert registry["penetration_target_m"].lower == 0.0001
    assert registry["penetration_target_m"].upper == 0.001
    assert registry["penetration_target_m"].hard_max == 0.001
    assert registry["penetration_target_m"].mode is ParameterMode.SEARCHABLE
    assert registry["seating_preload_rad"].upper == 0.006
    assert registry["grasp_close_q6"].lower == -0.059600220867817
    assert registry["grasp_close_q6"].upper == -0.047608632840292


def test_unaudited_parameters_are_frozen_not_invented() -> None:
    registry = load_parameter_registry(experiment_space_path())
    assert registry["carry_waypoint_count"].mode is ParameterMode.FROZEN
    assert registry["approach_vector_m"].mode is ParameterMode.FROZEN
    assert registry["micro_lift_settle_wait_s"].mode is ParameterMode.SEARCHABLE


def test_validation_fields_never_searchable() -> None:
    registry = load_parameter_registry(experiment_space_path())
    assert registry["final_position_tolerance_m"].mode is ParameterMode.VALIDATION
    assert registry["planning_shadow_lifecycle"].mode is ParameterMode.FROZEN


def test_every_searchable_key_owned_by_action_graph_node() -> None:
    from so101_gazebo_demo_py.experiment_planner.action_graph import build_so101_action_graph
    graph = build_so101_action_graph()
    registry = load_parameter_registry(experiment_space_path())
    for spec in registry.values():
        assert spec.owning_node in graph
        if spec.mode is ParameterMode.SEARCHABLE:
            assert spec.key in graph[spec.owning_node].searchable_keys
```

- [ ] **Step 2: 运行确认 RED**

Run: `python3 -m pytest -q test/test_experiment_planner_registry.py`
Expected: FAIL（`experiment_spaces/light_cup_wall_pick.yaml` 不存在 / `RegistryError`）

- [ ] **Step 3: 写 experiment-space YAML（每项参数一段，含全部 ParameterSpec 字段）**

```yaml
schema_version: 1
space_id: light_cup_wall_pick
parameters:
  penetration_target_m:
    kind: scalar
    unit: m
    frame: tcp_local_x
    default: 0.0005
    mode: SEARCHABLE
    lower: 0.0001
    upper: 0.001
    hard_max: 0.001
    step_generator: midpoint_bisect
    owning_node: CLOSE_GRIPPER
    dependencies: [grasp_tcp_translation_offset_m]
    exclusions: []
    requires_plan_only: false
    eligible_interactions: [grasp_tcp_translation_offset_m]
    provenance: "2026-08-09 spec section 2 penetration_target [0.0001, 0.001] m hard max"
  grasp_tcp_translation_offset_m:
    kind: vector
    unit: m
    frame: world
    default: [0.0, 0.0, 0.0004]
    mode: SEARCHABLE
    lower: -0.001
    upper: 0.001
    step_generator: midpoint_bisect
    owning_node: DESCEND
    dependencies: []
    exclusions: [single_axis_only]
    requires_plan_only: true
    eligible_interactions: [penetration_target_m]
    provenance: "2026-08-07 plan bounded target authorization; clearance 0.001 m"
  grasp_tcp_world_x_rotation_rad:
    kind: scalar
    unit: rad
    frame: world
    default: 0.0
    mode: SEARCHABLE
    lower: -0.08726646259971647
    upper: 0.08726646259971647
    step_generator: degree_ladder
    owning_node: DESCEND
    dependencies: []
    exclusions: []
    requires_plan_only: true
    eligible_interactions: [seating_preload_rad]
    provenance: "axis_tolerance_rad 0.08726646259971647 (2026-08-07 plan)"
  grasp_close_q6:
    kind: scalar
    unit: rad
    frame: joint
    default: -0.047608632840292
    mode: SEARCHABLE
    lower: -0.059600220867817
    upper: -0.047608632840292
    step_generator: midpoint_bisect
    owning_node: CLOSE_GRIPPER
    dependencies: []
    exclusions: []
    requires_plan_only: false
    eligible_interactions: [seating_preload_rad]
    provenance: "safe_lower_q6 .. baseline close (2026-08-07 plan q6 authorization)"
  seating_preload_rad:
    kind: scalar
    unit: rad
    frame: joint
    default: 0.006
    mode: SEARCHABLE
    lower: 0.0
    upper: 0.006
    step_generator: midpoint_bisect
    owning_node: WAIT_GRASP_STABLE
    dependencies: [grasp_close_q6]
    exclusions: []
    requires_plan_only: false
    eligible_interactions: [grasp_tcp_world_x_rotation_rad, grasp_close_q6]
    provenance: "2026-08-07 plan preload authorization [0.0, 0.006] rad"
  micro_lift_height_m:
    kind: scalar
    unit: m
    frame: world
    default: 0.002
    mode: SEARCHABLE
    lower: 0.0005
    upper: 0.004999
    step_generator: linspace_3
    owning_node: MICRO_LIFT
    dependencies: []
    exclusions: []
    requires_plan_only: true
    eligible_interactions: []
    provenance: "spec 4.3: >0 and < catastrophic relative drift 0.005 m"
  micro_lift_settle_wait_s:
    kind: scalar
    unit: s
    frame: wall
    default: 1.0
    mode: SEARCHABLE
    lower: 0.5
    upper: 3.0
    step_generator: linspace_3
    owning_node: WAIT_MICRO_LIFT_STABLE
    dependencies: []
    exclusions: []
    requires_plan_only: false
    eligible_interactions: []
    provenance: "spec section 2: settle wait searchable; acceptance semantics fixed"
  carry_waypoint_count:
    kind: discrete
    unit: count
    frame: n/a
    default: 10
    mode: FROZEN
    step_generator: none
    owning_node: MOVE_ABOVE_PLACE
    provenance: "audit pending; frozen until safety enumeration approved"
  approach_vector_m:
    kind: vector
    unit: m
    frame: world
    default: [0.0, 0.0, -0.05]
    mode: FROZEN
    step_generator: none
    owning_node: MOVE_ABOVE_OBJECT
    provenance: "audit pending; frozen until bounds registered"
  final_position_tolerance_m:
    kind: scalar
    unit: m
    frame: world
    default: 0.005
    mode: VALIDATION
    step_generator: none
    owning_node: VALIDATE_FINAL_PLACEMENT
    provenance: "validation policy planning_shadow.max_position_divergence_m (frozen acceptance)"
  planning_shadow_lifecycle:
    kind: discrete
    unit: n/a
    frame: moveit_scene
    default: "attach_at_ATTACH_MOVEIT_detach_at_DETACH_MOVEIT"
    mode: FROZEN
    step_generator: none
    owning_node: ATTACH_MOVEIT
    provenance: "spec section 2: shadow lifecycle fixed, never a search variable"
```

- [ ] **Step 4: 实现 registry.py loader**

严格 schema（未知 key 报 `RegistryError("REGISTRY_UNKNOWN_KEY", ...)`）、有限数值校验（拒绝 NaN/inf/bool）、`lower <= upper`、SEARCHABLE 必须有 `lower/upper` 或 `allowed` 与非空 `provenance`；FROZEN/VALIDATION 禁止出现 `eligible_interactions` 非空。colcon `--symlink-install` 已递归安装 `config/`，无需改 `setup.py` 的 data_files（验证：`install/so101_gazebo_demo_py/share/so101_gazebo_demo_py/config/experiment_spaces/` 存在）。

- [ ] **Step 5: 运行确认 GREEN + 全量 + installed 验证**

Run: `colcon build --packages-select so101_gazebo_demo_py --symlink-install && python3 -m pytest -q test`
Expected: focused PASS；全量 PASS；installed share 下 YAML 可读。

- [ ] **Step 6: Commit**

```bash
git add src/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/registry.py src/so101_gazebo_demo_py/config/experiment_spaces/light_cup_wall_pick.yaml src/so101_gazebo_demo_py/test/test_experiment_planner_registry.py
git commit -m "feat(so101_py): add parameter registry and experiment space"
```

---

### Task 4: Immutable candidate materializer + SHA（白名单 motion 快照）

**Files:**
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/materializer.py`
- Test: `src/so101_gazebo_demo_py/test/test_experiment_planner_materializer.py`
- Modify: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/policy_config.py`（仅当白名单新增 leaf 需要 loader 支持时；本 task 只允许复用既有 leaf）

**Interfaces:**
- Consumes: `Candidate`（Task 2）、`load_parameter_registry`（Task 3）、`load_policy_bundle`（既有）。
- Produces:
  - `MaterializedCandidate`（frozen dataclass）: `candidate: Candidate`, `motion_policy_path: Path`, `bundle_sha256: str`, `evaluation_only: bool`
  - `MOTION_WHITELIST: tuple[str, ...]` = `("grasp_tcp_translation_offset_m", "grasp_tcp_world_x_rotation_rad", "gripper_actions.preopen_q6", "gripper_actions.grasp_close_q6", "gripper_actions.seating_preload_rad")`
  - `ACTUATOR_KEYS: tuple[str, ...]` = `("grasp_tcp_translation_offset_m", "grasp_tcp_world_x_rotation_rad", "gripper_actions.grasp_close_q6")`
  - `materialize_candidate(candidate: Candidate, base_motion_policy: Path, out_dir: Path) -> MaterializedCandidate`
  - `MaterializationError(Exception)`

**核心语义**：候选 YAML = candidate metadata + 完整 motion policy snapshot + `penetration_target_m`（元数据，目标/评分参数，**不是** validation threshold）+ SHA/provenance。只允许白名单 motion leaf 变化；**绝不修改 validation YAML**。若候选相对 baseline 只改变 `penetration_target_m` 而没有 q6/TCP/approach 等 actuator 变量变化，则 `evaluation_only=True`——只能参与评分推演，**不得启动物理执行**。

- [ ] **Step 1: 写 RED 测试**

```python
import pytest

from so101_gazebo_demo_py.experiment_planner.materializer import (
    MaterializationError, materialize_candidate,
)
from so101_gazebo_demo_py.experiment_planner.model import Candidate

BASE_VALUES = {
    "grasp_tcp_translation_offset_m": (0.0, 0.0, 0.0004),
    "gripper_actions.seating_preload_rad": 0.006,
}


def make_candidate(values, candidate_id="cand-0001"):
    return Candidate(candidate_id=candidate_id, wave_id="wave-001", seed=7,
                     values=values, evaluation_only=False, sha256="")


def test_materializes_immutable_yaml_with_sha(tmp_path):
    materialized = materialize_candidate(
        make_candidate({**BASE_VALUES, "penetration_target_m": 0.0007}),
        BASE_MOTION_POLICY, tmp_path)
    assert materialized.motion_policy_path.exists()
    assert len(materialized.bundle_sha256) == 64
    assert not materialized.evaluation_only


def test_penetration_only_candidate_is_evaluation_only(tmp_path):
    materialized = materialize_candidate(
        make_candidate({**BASE_VALUES, "penetration_target_m": 0.0009}),
        BASE_MOTION_POLICY, tmp_path)
    # 与 baseline 的 actuator 值完全一致，仅 penetration_target 不同。
    assert materialized.evaluation_only  # baseline actuator 快照相等时成立


def test_rejects_non_whitelist_mutation(tmp_path):
    with pytest.raises(MaterializationError, match="whitelist"):
        materialize_candidate(
            make_candidate({"validation.final_position_tolerance_m": 0.01}),
            BASE_MOTION_POLICY, tmp_path)
```

（`BASE_MOTION_POLICY = Path(__file__).parents[1] / "config/motion_policies/light_cup_wall_pick.yaml"`；baseline actuator 快照从同一文件读出用于 evaluation_only 判定。）

- [ ] **Step 2: 运行确认 RED**

Run: `python3 -m pytest -q test/test_experiment_planner_materializer.py`
Expected: FAIL（`ModuleNotFoundError: materializer`）

- [ ] **Step 3: 实现 materializer.py**

深拷贝 baseline motion YAML -> 按白名单 dotted path 逐个覆盖（非白名单 key 抛 `MaterializationError("MATERIALIZE_WHITELIST", ...)`）-> 追加 candidate metadata 段（`candidate_id/wave_id/seed/penetration_target_m`）-> 写入 `out_dir/<candidate_id>/motion_policy.yaml`（`0o444` 只读）-> 用既有 `load_policy_bundle` 计算 `bundle_sha256`（object/validation 固定为 baseline 路径）-> `evaluation_only = (actuator 值与 baseline 快照完全相等)` -> 返回 `MaterializedCandidate`。SHA 计算复用 bundle 规范化（与 YAML 排版无关）。

- [ ] **Step 4: 运行确认 GREEN + 全量无回退**

Run: `python3 -m pytest -q test/test_experiment_planner_materializer.py && python3 -m pytest -q test`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/materializer.py src/so101_gazebo_demo_py/test/test_experiment_planner_materializer.py
git commit -m "feat(so101_py): add immutable candidate materializer"
```

---

### Task 5: Deterministic adaptive CandidateGenerator

**Files:**
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/candidate_generator.py`
- Test: `src/so101_gazebo_demo_py/test/test_experiment_planner_generator.py`

**Interfaces:**
- Consumes: `Candidate`, `ParameterSpec`, `FailureCategory`（Task 2）；`load_parameter_registry`（Task 3）；`build_so101_action_graph`（Task 2）。
- Produces:
  - `WaveContext`（frozen dataclass）: `seed: int`, `wave_id: str`, `first_failed_state: State | None`, `failure_category: FailureCategory | None`, `best_values: Mapping[str, float | tuple]`, `history_fingerprints: frozenset[str]`, `wave_mix: tuple[float, float, float] = (0.5, 0.3, 0.2)`
  - `generate_wave(context: WaveContext, registry: Mapping[str, ParameterSpec], batch_size: int) -> tuple[Candidate, ...]`
  - `FAILURE_SUBTREES: Mapping[FailureCategory, tuple[str, ...]]`（失败类别 -> 参数 key 子树）

**失败映射表（spec 6.4 逐字）**：`PLAN_IK_COLLISION -> approach/pose/waypoint keys`；`MISS_CONTACT -> grasp pose/preopen/penetration`；`CONTACT_NO_LIFT -> penetration/close/preload/dwell`；`SLIP -> orientation/preload/lift vector/speed`；`TARGET_MISS -> lift/carry/place vector/pose`；`UNSTABLE -> execution speed/duration/settle wait`。未审计 frozen 参数即使被子树命中也不得生成取值（跳过并记录）。

- [ ] **Step 1: 写 RED 测试——确定性、配额、子树、去重、eligible interactions**

```python
from so101_gazebo_demo_py.domain import State
from so101_gazebo_demo_py.experiment_planner.candidate_generator import (
    WaveContext, generate_wave,
)
from so101_gazebo_demo_py.experiment_planner.model import FailureCategory
from so101_gazebo_demo_py.experiment_planner.registry import (
    experiment_space_path, load_parameter_registry,
)


def make_context(**overrides):
    base = dict(seed=11, wave_id="wave-001",
                first_failed_state=State.WAIT_GRASP_STABLE,
                failure_category=FailureCategory.MISS_CONTACT,
                best_values={}, history_fingerprints=frozenset())
    base.update(overrides)
    return WaveContext(**base)


def test_same_seed_history_registry_same_batch() -> None:
    registry = load_parameter_registry(experiment_space_path())
    first = generate_wave(make_context(), registry, batch_size=10)
    second = generate_wave(make_context(), registry, batch_size=10)
    assert [c.candidate_id for c in first] == [c.candidate_id for c in second]
    assert [c.values for c in first] == [c.values for c in second]


def test_largest_remainder_mix_50_30_20() -> None:
    registry = load_parameter_registry(experiment_space_path())
    wave = generate_wave(make_context(), registry, batch_size=10)
    kinds = [c.candidate_id.split("-")[2] for c in wave]  # <wave>-<kind>-<seq>
    assert (kinds.count("exploit"), kinds.count("explore"), kinds.count("interact")) == (5, 3, 2)


def test_first_failure_opens_only_mapped_subtree() -> None:
    registry = load_parameter_registry(experiment_space_path())
    wave = generate_wave(make_context(), registry, batch_size=10)
    touched = {key for c in wave for key in c.values}
    assert "carry_waypoint_count" not in touched  # 下游 frozen 且不在 MISS_CONTACT 子树


def test_history_fingerprint_dedup() -> None:
    registry = load_parameter_registry(experiment_space_path())
    wave = generate_wave(make_context(), registry, batch_size=10)
    replay = generate_wave(
        make_context(history_fingerprints=frozenset(c.sha256 for c in wave)),
        registry, batch_size=10)
    assert all(c.sha256 not in {w.sha256 for w in wave} for c in replay)
```

- [ ] **Step 2: 运行确认 RED**

Run: `python3 -m pytest -q test/test_experiment_planner_generator.py`
Expected: FAIL（`ModuleNotFoundError: candidate_generator`）

- [ ] **Step 3: 实现 candidate_generator.py**

`generate_wave`：按 `wave_mix` 用 largest-remainder 法分配三类名额；候选 id 形如 `<wave>-<kind>-<seq>`；exploit 在 `best_values` 邻域按 `step_generator`（`midpoint_bisect`/`linspace`）取点；explore 在未覆盖区间用 `random.Random(seed)` 的 `sample` 确定性取点；interact 只组合双方都在对方 `eligible_interactions` 内的参数对；`first_failed_state=None` 时只对 `State.IDLE` 之后的首个未通过节点开子树；每个候选计算规范化 SHA（排序后的 values 摘要）并拒绝 `history_fingerprints` 命中。frozen 参数永不进 `values`。

- [ ] **Step 4: 运行确认 GREEN + 全量无回退**

Run: `python3 -m pytest -q test/test_experiment_planner_generator.py && python3 -m pytest -q test`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/candidate_generator.py src/so101_gazebo_demo_py/test/test_experiment_planner_generator.py
git commit -m "feat(so101_py): add deterministic adaptive candidate generator"
```

---

### Task 6: ConstraintEngine + plan-only admission

**Files:**
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/constraints.py`
- Test: `src/so101_gazebo_demo_py/test/test_experiment_planner_constraints.py`

**Interfaces:**
- Consumes: `MaterializedCandidate`（Task 4）、`ParameterSpec`（Task 2/3）。
- Produces:
  - `PlanOnlyResult`（frozen dataclass）: `ok: bool`, `detail: str`
  - `PlanOnlyProbe(Protocol)`: `def probe(self, materialized: MaterializedCandidate) -> PlanOnlyResult`
  - `AdmissionDecision`（frozen dataclass）: `admitted: bool`, `reason: str | None`, `evaluation_only: bool`
  - `admit_candidate(materialized: MaterializedCandidate, registry: Mapping[str, ParameterSpec], history_fingerprints: frozenset[str], probe: PlanOnlyProbe) -> AdmissionDecision`

**准入顺序（任一不过即 `admitted=False`）**：范围/依赖/互斥 -> `hard_max`（penetration 0.001 m）-> actuator 依赖（`evaluation_only` 候选直接 `admitted=False, reason="evaluation_only"`，因为不得启动物理执行）-> plan-only（`requires_plan_only` 或 motion 变化候选）-> 历史去重。plan-only 失败 => `INVALID_CANDIDATE`，不 execute。

- [ ] **Step 1: 写 RED 测试**

```python
from so101_gazebo_demo_py.experiment_planner.constraints import (
    PlanOnlyResult, admit_candidate,
)


class FakeProbe:
    def __init__(self, ok):
        self._ok = ok
        self.calls = 0
    def probe(self, materialized):
        self.calls += 1
        return PlanOnlyResult(ok=self._ok, detail="fake")


def test_out_of_range_rejected_before_probe(materialized_factory, registry):
    probe = FakeProbe(ok=True)
    decision = admit_candidate(
        materialized_factory({"penetration_target_m": 0.0015}), registry, frozenset(), probe)
    assert not decision.admitted and "hard_max" in decision.reason
    assert probe.calls == 0


def test_evaluation_only_candidate_never_executes(materialized_factory, registry):
    decision = admit_candidate(
        materialized_factory({"penetration_target_m": 0.0009}, evaluation_only=True),
        registry, frozenset(), FakeProbe(ok=True))
    assert not decision.admitted and decision.reason == "evaluation_only"


def test_plan_only_failure_is_invalid_candidate(materialized_factory, registry):
    decision = admit_candidate(
        materialized_factory({"grasp_tcp_translation_offset_m": (0.0, 0.0, 0.00045)}),
        registry, frozenset(), FakeProbe(ok=False))
    assert not decision.admitted and "plan_only" in decision.reason


def test_duplicate_fingerprint_rejected(materialized_factory, registry):
    candidate = materialized_factory({"grasp_tcp_translation_offset_m": (0.0, 0.0, 0.00045)})
    decision = admit_candidate(candidate, registry, frozenset({candidate.bundle_sha256}), FakeProbe(ok=True))
    assert not decision.admitted and "duplicate" in decision.reason
```

（`materialized_factory`/`registry` 为模块级 pytest fixture：直接用 Task 4 的 `materialize_candidate` 与 Task 3 的 loader 构造真实对象。）

- [ ] **Step 2: 运行确认 RED**

Run: `python3 -m pytest -q test/test_experiment_planner_constraints.py`
Expected: FAIL（`ModuleNotFoundError: constraints`）

- [ ] **Step 3: 实现 constraints.py**

按准入顺序实现纯函数检查；范围比较含浮点 `math.isfinite` 守卫；互斥检查单轴平移（沿用 `policy_config` 的"只许单轴非零"语义）；probe 只在前置检查全过后调用一次。

- [ ] **Step 4: 运行确认 GREEN + 全量无回退**

Run: `python3 -m pytest -q test/test_experiment_planner_constraints.py && python3 -m pytest -q test`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/constraints.py src/so101_gazebo_demo_py/test/test_experiment_planner_constraints.py
git commit -m "feat(so101_py): add constraint engine with plan-only admission"
```

---

### Task 7: Evidence parsing + StageEvaluator

**Files:**
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/evaluator.py`
- Test: `src/so101_gazebo_demo_py/test/test_experiment_planner_evaluator.py`

**Interfaces:**
- Consumes: `StageEvidence`, `StageEvaluation`, `CandidateStatus`, `FailureCategory`（Task 2）；既有 runtime 证据格式（`physical-gate.json`/`physical-failure.json`/`live-summary.json`，见 `live_execute.py`）。
- Produces:
  - `parse_stage_evidence(evidence_dir: Path) -> tuple[StageEvidence, ...]`
  - `first_failed_state(evidences: tuple[StageEvidence, ...]) -> State | None`
  - `classify_failure(evidence: StageEvidence) -> FailureCategory`
  - `evaluate_candidate(candidate_id: str, evidences: tuple[StageEvidence, ...], reset_world_verified: bool) -> StageEvaluation`
  - `rank_feasible(evaluations: tuple[StageEvaluation, ...]) -> tuple[StageEvaluation, ...]`（maximin normalized margin + RESET_WORLD robustness）
  - `micro_lift_contract_ok(metrics: Mapping[str, float | bool | None]) -> bool`

**MICRO_LIFT 合同判据（固定阈值，来自 frozen 验收语义）**：完整 position+orientation 在固定容差内、脱离非预期支撑、固定窗口内位姿/线速度/角速度持续达标、`physics_source == "gazebo_contact"`。任一缺失/不达标 => False。硬门失败（`VALID_FAILURE`/`INVALID_*`）不进 `rank_feasible` 输入。

- [ ] **Step 1: 写 RED 测试**

```python
from so101_gazebo_demo_py.domain import State
from so101_gazebo_demo_py.experiment_planner.evaluator import (
    classify_failure, first_failed_state, micro_lift_contract_ok, rank_feasible,
)
from so101_gazebo_demo_py.experiment_planner.model import (
    CandidateStatus, FailureCategory, StageEvidence,
)


def test_micro_lift_contract_requires_full_pose_not_z_delta_only() -> None:
    metrics = {"cup_world_z_delta_m": 0.002, "lateral_drift_m": 0.0002,
               "physics_source": "gazebo_contact"}
    assert not micro_lift_contract_ok(metrics)  # 缺姿态/支撑/窗口证据
    full = {**metrics, "orientation_within_tolerance": True,
            "support_cleared": True, "window_stable": True}
    assert micro_lift_contract_ok(full)


def test_command_success_alone_never_passes() -> None:
    assert not micro_lift_contract_ok({"controller_result": "SUCCEEDED",
                                       "cup_world_z_delta_m": 0.002})


def test_classify_existing_failure_signatures() -> None:
    no_contact = StageEvidence(State.WAIT_GRASP_STABLE, {"bilateral": False, "moving_jaw": False})
    assert classify_failure(no_contact) is FailureCategory.MISS_CONTACT
    no_lift = StageEvidence(State.MICRO_LIFT, {"bilateral": True, "cup_world_z_delta_m": 0.0004})
    assert classify_failure(no_lift) is FailureCategory.CONTACT_NO_LIFT


def test_first_failed_state_from_trace() -> None:
    evidences = (
        StageEvidence(State.CLOSE_GRIPPER, {"ok": True}),
        StageEvidence(State.WAIT_GRASP_STABLE, {"ok": False}),
    )
    assert first_failed_state(evidences) is State.WAIT_GRASP_STABLE


def test_hard_gate_failures_never_ranked() -> None:
    import pytest
    with pytest.raises(ValueError, match="PROVISIONAL_FEASIBLE"):
        rank_feasible((_evaluation(CandidateStatus.VALID_FAILURE),))
```

（`_evaluation` helper 构造最小 `StageEvaluation`。）

- [ ] **Step 2: 运行确认 RED**

Run: `python3 -m pytest -q test/test_experiment_planner_evaluator.py`
Expected: FAIL（`ModuleNotFoundError: evaluator`）

- [ ] **Step 3: 实现 evaluator.py**

`parse_stage_evidence` 读 `physical-gate.json`/`physical-failure.json`/`live-summary.json` 并映射到 `StageEvidence`；`classify_failure` 实现 spec 6.4 的六类签名表；`rank_feasible` 拒绝非 `PROVISIONAL_FEASIBLE`/`PROMOTED_ANCHOR` 输入，按各 margin 归一化后的 maximin（最差余量最大者优先）+ `reset_world_verified` 次序排序。

- [ ] **Step 4: 运行确认 GREEN + 全量无回退**

Run: `python3 -m pytest -q test/test_experiment_planner_evaluator.py && python3 -m pytest -q test`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/evaluator.py src/so101_gazebo_demo_py/test/test_experiment_planner_evaluator.py
git commit -m "feat(so101_py): add stage evaluator with failure classification"
```

---

### Task 8: Candidate/Result ledger（单写者、幂等恢复、生命周期分账）

**Files:**
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/ledger.py`
- Test: `src/so101_gazebo_demo_py/test/test_experiment_planner_ledger.py`

**Interfaces:**
- Consumes: `Candidate`, `StageEvaluation`, `CandidateStatus`（Task 2）；`MaterializedCandidate`（Task 4）。
- Produces:
  - `LedgerError(Exception)`
  - `ExperimentLedger(root: Path)`，方法：
    - `register_candidate(materialized: MaterializedCandidate) -> None`（写不可变候选 YAML）
    - `append_result(evaluation: StageEvaluation, session_id: str, fingerprint_commit: str) -> None`（append-only JSONL）
    - `history_fingerprints() -> frozenset[str]`
    - `recover(session_id: str, candidate_sha256: str) -> StageEvaluation | None`（幂等：重复提交返回既有结果）
    - `lifecycle_counts() -> Mapping[CandidateStatus, int]`
    - `promote_anchor(candidate_id: str, evidence: tuple[StageEvaluation, StageEvaluation]) -> None`（两次跨 lane RESET_WORLD 复验；0.0013 历史 fingerprint 拒绝晋升）

**规则**：单写者锁（`root/.writer.lock`，`os.open(O_CREAT|O_EXCL)`）；候选 YAML 写后 `0o444`；合法状态转换 `PROVISIONAL_FEASIBLE -> PROMOTED_ANCHOR` 只能经 `promote_anchor`；`INVALID_*` 与 `VALID_FAILURE`/`PROVISIONAL_FEASIBLE` 分开计数；`fingerprint_commit` 属于历史 0.0013 fingerprint 清单时 `promote_anchor` 抛 `LedgerError("LEGACY_FINGERPRINT", ...)`。

- [ ] **Step 1: 写 RED 测试**

```python
import pytest

from so101_gazebo_demo_py.experiment_planner.ledger import ExperimentLedger, LedgerError
from so101_gazebo_demo_py.experiment_planner.model import CandidateStatus


def test_append_only_and_idempotent_recovery(tmp_path, materialized, evaluation):
    ledger = ExperimentLedger(tmp_path)
    ledger.register_candidate(materialized)
    ledger.append_result(evaluation, session_id="sess-1", fingerprint_commit="abc123")
    again = ledger.recover("sess-1", materialized.bundle_sha256)
    assert again == evaluation
    assert materialized.motion_policy_path.stat().st_mode & 0o222 == 0


def test_single_writer_lock(tmp_path, evaluation):
    first = ExperimentLedger(tmp_path)
    first.acquire()
    second = ExperimentLedger(tmp_path)
    with pytest.raises(LedgerError, match="writer"):
        second.acquire()
    first.release()


def test_lifecycle_counts_never_mixed(tmp_path, ledger_with_mixed_results):
    counts = ledger_with_mixed_results.lifecycle_counts()
    assert counts[CandidateStatus.INVALID_ENVIRONMENT] == 1
    assert counts[CandidateStatus.VALID_FAILURE] == 1
    assert counts[CandidateStatus.PROVISIONAL_FEASIBLE] == 1


def test_legacy_0013_fingerprint_cannot_promote(tmp_path, ledger_with_mixed_results):
    with pytest.raises(LedgerError, match="LEGACY_FINGERPRINT"):
        ledger_with_mixed_results.promote_anchor(
            "cand-legacy", evidence=(_ev("lane-a"), _ev("lane-b")),
        )  # evidence 的 fingerprint_commit 在 0.0013 历史清单中
```

（fixture 在测试文件内定义：`_ev(lane)` 构造两次跨 lane RESET_WORLD 复验的 `StageEvaluation`。）

- [ ] **Step 2: 运行确认 RED**

Run: `python3 -m pytest -q test/test_experiment_planner_ledger.py`
Expected: FAIL（`ModuleNotFoundError: ledger`）

- [ ] **Step 3: 实现 ledger.py**

JSONL 每行一条结果（`candidate_id/session_id/status/first_failed_state/failure_category/margins/fingerprint_commit/recorded_at`）；`recover` 按 `(session_id, candidate_sha256)` 索引扫描；`history_fingerprints` 聚合候选 YAML 的 SHA；历史 fingerprint 清单内嵌常量 `LEGACY_FINGERPRINTS = frozenset({"CP-QUALIFICATION-FINGERPRINT-002"})` 及对应 commit `6cd8c7d`。

- [ ] **Step 4: 运行确认 GREEN + 全量无回退**

Run: `python3 -m pytest -q test/test_experiment_planner_ledger.py && python3 -m pytest -q test`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/ledger.py src/so101_gazebo_demo_py/test/test_experiment_planner_ledger.py
git commit -m "feat(so101_py): add single-writer experiment ledger"
```

---

### Task 9: RESET_WORLD contract（九项 proof report）

**Files:**
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/reset_contract.py`
- Modify: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/gazebo/reset.py`（仅补齐 probe 需要的只读查询接口；不改动既有 reset 语义）
- Test: `src/so101_gazebo_demo_py/test/test_experiment_planner_reset.py`

**Interfaces:**
- Consumes: 既有 `gazebo/reset.py` 的复位边界与 `RosGazeboLiveBackend` 只读采样。
- Produces:
  - `ResetContractProbe(Protocol)`: `cancel_actions() -> bool` / `gazebo_unexpected_attachment() -> bool` / `restore_moveit_world_object() -> bool` / `robot_home() -> bool` / `cup_at_spawn() -> bool` / `controllers_active() -> bool` / `readings_stable() -> bool` / `allocate_session() -> str` / `residual_contact_or_attached() -> bool`
  - `ResetReport`（frozen dataclass）: `proofs: Mapping[str, bool]`, `session_id: str | None`, `ok: bool`
  - `verify_reset_world(probe: ResetContractProbe) -> ResetReport`（九项任一失败 => `ok=False`，调用方记 `INVALID_ENVIRONMENT`）

**边界**：proof 组合逻辑在 `reset_contract.py`；实际 shell/服务调用留在 `gazebo/reset.py` 既有边界内（新增只读查询函数，如 `unexpected_attachment_state()`），不在纯 coordinator 里塞 shell 命令；绝不 broad-kill。

- [ ] **Step 1: 写 RED 测试**

```python
from so101_gazebo_demo_py.experiment_planner.reset_contract import verify_reset_world


class FakeProbe:
    def __init__(self, fail_at=None):
        self.fail_at = fail_at
    def cancel_actions(self): return self.fail_at != "cancel"
    def gazebo_unexpected_attachment(self): return self.fail_at == "attachment"
    def restore_moveit_world_object(self): return self.fail_at != "scene"
    def robot_home(self): return self.fail_at != "home"
    def cup_at_spawn(self): return self.fail_at != "spawn"
    def controllers_active(self): return self.fail_at != "controllers"
    def readings_stable(self): return self.fail_at != "stable"
    def allocate_session(self): return "sess-test"
    def residual_contact_or_attached(self): return self.fail_at == "residual"


def test_all_proofs_pass_yields_session():
    report = verify_reset_world(FakeProbe())
    assert report.ok and report.session_id == "sess-test"
    assert len(report.proofs) == 9


def test_any_single_failure_invalidates_environment():
    for fail_at in ("cancel", "attachment", "scene", "home", "spawn",
                    "controllers", "stable", "residual"):
        report = verify_reset_world(FakeProbe(fail_at))
        assert not report.ok
        assert report.session_id is None  # 失败时不分配新 session
```

- [ ] **Step 2: 运行确认 RED**

Run: `python3 -m pytest -q test/test_experiment_planner_reset.py`
Expected: FAIL（`ModuleNotFoundError: reset_contract`）

- [ ] **Step 3: 实现 reset_contract.py + gazebo/reset.py 只读查询**

`verify_reset_world` 依序调用九个 probe 方法，逐项记入 `proofs`（key 为九项合同名），全部通过才调用 `allocate_session`。`gazebo/reset.py` 只补只读查询（attachment state、scene membership 读回），复用既有复位实现。

- [ ] **Step 4: 运行确认 GREEN + 全量无回退**

Run: `python3 -m pytest -q test/test_experiment_planner_reset.py && python3 -m pytest -q test`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/reset_contract.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/gazebo/reset.py src/so101_gazebo_demo_py/test/test_experiment_planner_reset.py
git commit -m "feat(so101_py): add reset-world contract proofs"
```

---

### Task 10: Lane Supervisor + resource/domain/disk guard

**Files:**
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/supervisor.py`
- Test: `src/so101_gazebo_demo_py/test/test_experiment_planner_supervisor.py`

**Interfaces:**
- Consumes: `ResetReport`（Task 9）、`StageEvaluation`（Task 2）。
- Produces:
  - `LaneSpec`（frozen dataclass）: `lane_id: str`, `ros_domain_id: int`, `gz_partition: str`, `tmux_session: str`, `ros_log_dir: Path`, `evidence_dir: Path`, `session_id: str`, `checkpoint_dir: Path`
  - `OwnedProcessManifest`（frozen dataclass）: `lane_id: str`, `pids: tuple[int, ...]`
  - `ResourceSnapshot`（frozen dataclass）: `cpu_percent: float`, `memory_percent: float`, `swap_percent: float`, `rtf: float`, `disk_free_bytes: int`
  - `GuardError(Exception)`
  - `allocate_lanes(requested: int, probe: ResourceProbe, watermark: DiskWatermark | None, base_domain: int, root: Path) -> tuple[LaneSpec, ...]`（1->2->3 递增探测；资源/RTF 恶化自动降级；domain > 232 直接 `GuardError("DOMAIN_ILLEGAL", ...)`）
  - `DiskWatermark`（frozen dataclass）: `min_free_bytes: int`
  - `wave_global_invalid(manifests: tuple[OwnedProcessManifest, ...], snapshot: ResourceSnapshot) -> str | None`（共享写入/manifest 失配/domain-partition 冲突/磁盘水位 => 原因字符串，否则 None）
  - `ResourceProbe(Protocol)`: `snapshot() -> ResourceSnapshot`

**清理纪律**：只允许对 `OwnedProcessManifest.pids` 中的 exact PID 先 TERM、读回、同 PID 存活才 KILL；测试中用 fake launcher 断言绝不出现 `pkill`/`killall`。

- [ ] **Step 1: 写 RED 测试**

```python
import pytest

from so101_gazebo_demo_py.experiment_planner.supervisor import (
    GuardError, LaneSpec, OwnedProcessManifest, ResourceSnapshot, allocate_lanes,
    wave_global_invalid,
)


class FakeResources:
    def __init__(self, rtf=0.99, disk=10 * 1024**3, cpu=20.0):
        self.rtf, self.disk, self.cpu = rtf, disk, cpu
    def snapshot(self):
        return ResourceSnapshot(cpu_percent=self.cpu, memory_percent=30.0,
                                swap_percent=1.0, rtf=self.rtf,
                                disk_free_bytes=self.disk)


def test_domain_above_232_rejected(tmp_path):
    with pytest.raises(GuardError, match="DOMAIN_ILLEGAL"):
        allocate_lanes(1, FakeResources(), watermark=None, base_domain=233, root=tmp_path)


def test_probe_degrades_on_low_rtf(tmp_path):
    lanes = allocate_lanes(3, FakeResources(rtf=0.4), watermark=None, base_domain=200, root=tmp_path)
    assert len(lanes) == 1  # 资源探测 1->2->3，RTF 恶化自动降级


def test_wave_invalid_on_manifest_mismatch(tmp_path):
    lanes = allocate_lanes(2, FakeResources(), watermark=None, base_domain=200, root=tmp_path)
    manifests = (OwnedProcessManifest(lanes[0].lane_id, (1,)),
                 OwnedProcessManifest(lanes[0].lane_id, (2,)))  # 重复 lane => 冲突
    assert wave_global_invalid(manifests, FakeResources().snapshot()) is not None
```

- [ ] **Step 2: 运行确认 RED**

Run: `python3 -m pytest -q test/test_experiment_planner_supervisor.py`
Expected: FAIL（`ModuleNotFoundError: supervisor`）

- [ ] **Step 3: 实现 supervisor.py**

lane 资源命名确定性（`so101-planner-lane<i>-<domain>`、partition `so101_planner_<domain>`）；domain 合法性 `0 < domain <= 232`；递增探测时第二次 `snapshot()` 的 RTF/CPU/磁盘低于阈值即降级；`wave_global_invalid` 检查 lane_id 唯一、domain 唯一、evidence/log/checkpoint 路径无交集、磁盘水位。

- [ ] **Step 4: 运行确认 GREEN + 全量无回退**

Run: `python3 -m pytest -q test/test_experiment_planner_supervisor.py && python3 -m pytest -q test`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/supervisor.py src/so101_gazebo_demo_py/test/test_experiment_planner_supervisor.py
git commit -m "feat(so101_py): add lane supervisor with resource guards"
```

---

### Task 11: CLI and dry orchestration

**Files:**
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/cli/experiment_planner.py`
- Modify: `src/so101_gazebo_demo_py/setup.py`（`entry_points` 增加 `so101_experiment_planner`；config 已递归安装，无需动 data_files）
- Test: `src/so101_gazebo_demo_py/test/test_experiment_planner_cli.py`

**Interfaces:**
- Consumes: 全部上游组件（Task 2-10）。
- Produces:
  - `main(argv: list[str] | None = None) -> int`
  - subcommands：`plan-wave`（只生成候选+准入选型，不 execute）、`status`（生命周期计数/当前 anchor）、`resume`（按 session_id+candidate SHA 幂等恢复）、`run-wave`（**要求** `--approved-checkpoint <ledger checkpoint id>` 与 `--mode {screening,qualification}`，缺一即拒绝；绝不自动 build/source/改源码）
  - console entry：`so101_experiment_planner = so101_gazebo_demo_py.cli.experiment_planner:main`

- [ ] **Step 1: 写 RED 测试**

```python
from so101_gazebo_demo_py.cli.experiment_planner import main


def test_plan_wave_dry_run_never_executes(tmp_path, capsys):
    rc = main(["plan-wave", "--seed", "11", "--batch-size", "4",
               "--ledger-root", str(tmp_path)])
    assert rc == 0
    assert "EXECUTE_DISABLED" in capsys.readouterr().out


def test_run_wave_requires_approved_checkpoint(tmp_path):
    rc = main(["run-wave", "--ledger-root", str(tmp_path)])
    assert rc == 2  # argparse 缺必需参数


def test_run_wave_rejects_unknown_checkpoint(tmp_path):
    rc = main(["run-wave", "--ledger-root", str(tmp_path),
               "--approved-checkpoint", "CP-DOES-NOT-EXIST", "--mode", "screening"])
    assert rc == 3  # 未授权 checkpoint 专用退出码


def test_status_reports_lifecycle_counts(tmp_path, seeded_ledger, capsys):
    rc = main(["status", "--ledger-root", str(tmp_path)])
    assert rc == 0 and "PROVISIONAL_FEASIBLE" in capsys.readouterr().out
```

（`seeded_ledger` fixture 在测试文件内定义：用 Task 8 的 `ExperimentLedger` 写入一条 `PROVISIONAL_FEASIBLE` 与一条 `VALID_FAILURE` 结果。）

- [ ] **Step 2: 运行确认 RED**

Run: `python3 -m pytest -q test/test_experiment_planner_cli.py`
Expected: FAIL（`ModuleNotFoundError: cli.experiment_planner`）

- [ ] **Step 3: 实现 CLI + setup.py entry point**

`main` 只做编排与打印；`plan-wave` 调 Task 5/6 生成并准入，输出候选清单与 `EXECUTE_DISABLED`；`run-wave` 校验 checkpoint 存在且 mode 匹配后才构造 lane/执行（实际执行走 Task 12 的 live adapter）；`resume` 走 `ExperimentLedger.recover`。`setup.py` 的 `entry_points["console_scripts"]` 追加一行。

- [ ] **Step 4: Rebuild + 运行确认 GREEN + installed entry point**

```bash
colcon build --packages-select so101_gazebo_demo_py --symlink-install
source install/setup.bash
which so101_experiment_planner && so101_experiment_planner --help
python3 -m pytest -q test
```

Expected: entry point 存在且 `--help` 列出四个 subcommand；全量 PASS。

- [ ] **Step 5: Commit**

```bash
git add src/so101_gazebo_demo_py/so101_gazebo_demo_py/cli/experiment_planner.py src/so101_gazebo_demo_py/setup.py src/so101_gazebo_demo_py/test/test_experiment_planner_cli.py
git commit -m "feat(so101_py): add experiment planner CLI"
```

---

### Task 12: Live adapter and candidate policy plumbing

**Files:**
- Create: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/live_adapter.py`
- Modify: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/cli/pick_place_state_machine.py`（仅当 lane 私有 motion snapshot 传入路径需要显式化时；保持既有默认行为不变）
- Modify: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/live_execute.py`（仅补显式接口；禁止改动 gate 语义）
- Test: `src/so101_gazebo_demo_py/test/test_experiment_planner_live_adapter.py`

**Interfaces:**
- Consumes: `MaterializedCandidate`（Task 4）、`LaneSpec`（Task 10）；既有 `run_live_execute(evidence_directory, stop_after, motion_policy)` 签名（`live_execute.py:486-490`）。
- Produces:
  - `LiveRunResult`（frozen dataclass）: `command: tuple[str, ...]`, `exit_code: int`, `evidence_dir: Path`, `policy_sha256: str`, `ros_domain_id: int`, `gz_partition: str`
  - `build_execute_command(materialized: MaterializedCandidate, lane: LaneSpec, stop_after: str) -> tuple[str, ...]`
  - `capture_result(command: tuple[str, ...], lane: LaneSpec) -> LiveRunResult`

**红线**：object/validation policy 固定 baseline；只有 lane 私有的 motion snapshot 经 `--motion-policy` 传入；既有防 forward attach 的 contract test（`test_live_forward_path_never_commands_gazebo_attachment`）必须保持绿色；本 task 不改任何 gate/threshold。

- [ ] **Step 1: 写 RED 测试**

```python
from so101_gazebo_demo_py.experiment_planner.live_adapter import build_execute_command


def test_command_uses_lane_private_motion_snapshot(materialized, lane):
    command = build_execute_command(materialized, lane, stop_after="VERIFY_PHYSICAL_GRASP")
    joined = " ".join(command)
    assert "--motion-policy" in joined
    assert str(materialized.motion_policy_path) in joined
    assert "--stop-after VERIFY_PHYSICAL_GRASP" in joined
    assert "validation" not in joined.split("--motion-policy")[1]  # validation 永不被候选覆盖


def test_command_carries_exact_lane_environment(materialized, lane):
    command = build_execute_command(materialized, lane, stop_after="VERIFY_PHYSICAL_GRASP")
    assert f"ROS_DOMAIN_ID={lane.ros_domain_id}" in command
    assert f"GZ_PARTITION={lane.gz_partition}" in command


def test_existing_no_forward_attach_contract_unchanged():
    from pathlib import Path
    source = (Path(__file__).parents[1]
              / "so101_gazebo_demo_py/live_execute.py").read_text()
    assert ".set_attached(" not in source
    assert '"ATTACH_GAZEBO"' not in source
```

- [ ] **Step 2: 运行确认 RED**

Run: `python3 -m pytest -q test/test_experiment_planner_live_adapter.py`
Expected: FAIL（`ModuleNotFoundError: live_adapter`）

- [ ] **Step 3: 实现 live_adapter.py**

`build_execute_command` 产出 `("env", f"ROS_DOMAIN_ID={...}", f"GZ_PARTITION={...}", sys.executable, "-m", "so101_gazebo_demo_py.cli.pick_place_state_machine", "--motion-policy", <lane snapshot>, "--stop-after", <state>, "--evidence-dir", <lane evidence>)`；`capture_result` 记录精确命令/exit code/policy SHA/domain/partition。`pick_place_state_machine.py` 与 `live_execute.py` 仅在缺 `--evidence-dir` 或 motion-policy 显式路径支持时做最小补齐，既有默认路径行为不变。

- [ ] **Step 4: 运行确认 GREEN + 全量无回退**

Run: `python3 -m pytest -q test/test_experiment_planner_live_adapter.py && python3 -m pytest -q test`
Expected: PASS（含既有 contract tests）。

- [ ] **Step 5: Commit**

```bash
git add src/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/live_adapter.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/cli/pick_place_state_machine.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/live_execute.py src/so101_gazebo_demo_py/test/test_experiment_planner_live_adapter.py
git commit -m "feat(so101_py): add live execution adapter for candidates"
```

---

### Task 13: MICRO_LIFT full-pose stable evaluator + post-retreat FINAL_STABLE

**Files:**
- Modify: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/live_execute.py`（`verify_physical_micro_lift` 与 RETREAT 后 final 采样段）
- Modify: `src/so101_gazebo_demo_py/so101_gazebo_demo_py/physical_outcome.py`（复用固定阈值的窗口稳定评估）
- Modify: `src/so101_gazebo_demo_py/test/test_live_physical_outcome_contract.py`
- Modify: `src/so101_gazebo_demo_py/test/test_gazebo_attachment.py`（如需新证据构造 helper）

**Interfaces:**
- Consumes: 既有 `verify_physical_micro_lift`（`live_execute.py:382`）、`ReleaseSettleExecutor`/`FinalPlacementSample`（`physical_outcome.py`）、Task 7 的 `micro_lift_contract_ok` 判据。
- Produces:
  - `verify_physical_micro_lift` 返回扩展证据：在原 `(lift, lateral, micro_points, micro_start_z, before, after)` 之外，经 `StageEvidence` 兼容 dict 输出 `orientation_within_tolerance / support_cleared / window_stable / physics_source="gazebo_contact"`；签名保持 `verify_physical_micro_lift(backend, execute=_moveit_world_z_execute)` 不变。
  - `evaluate_post_retreat_final(backend, outcome_policy) -> FinalPlacementEvaluation`：RETREAT 完成后开启新 release/final epoch 重新采样并判定最终位姿与稳定性。
  - `live_execute.run_live_execute` 在 `RETREAT` 后调用 `evaluate_post_retreat_final`，其结果写入 summary 的 `final_outcome`（post-retreat 判定取代预撤离判定作为最终成功依据）。

- [ ] **Step 1: 写 RED 测试——证明只看 Z/预撤离判定不足**

```python
from types import SimpleNamespace

import pytest

from so101_gazebo_demo_py.live_execute import verify_physical_micro_lift
from so101_gazebo_demo_py.physical_outcome import evaluate_post_retreat_final


class FakeBackendTipped:
    """Z 达标但姿态倾倒：旧 lift/lateral 检查会漏过的样本。"""

    def __init__(self):
        self._calls = 0

    def sample(self):
        self._calls += 1
        z = 0.0 if self._calls == 1 else 0.002
        # 绕 X 倒 0.2 rad（远超 upright 阈值），但 Z delta 恰好 0.002。
        xyzw_tipped = (0.099, 0.0, 0.0, 0.995)
        return SimpleNamespace(object_xyz=(0.0, 0.0, z), object_xyzw=xyzw_tipped)


def test_micro_lift_rejects_tipped_carry(monkeypatch):
    monkeypatch.setattr(
        "so101_gazebo_demo_py.live_execute._stable_bilateral", lambda backend: None)
    monkeypatch.setattr(
        "so101_gazebo_demo_py.live_execute._moveit_world_z_execute",
        lambda delta: (["p"], 0.0))
    with pytest.raises(RuntimeError, match="micro-lift full-pose"):
        verify_physical_micro_lift(FakeBackendTipped())


def test_final_outcome_resampled_after_retreat():
    # 预撤离窗口稳定、RETREAT 扰动后倾倒：post-retreat epoch 必须判失败。
    backend = FakeBackendPreRetreatStablePostRetreatTipped()
    result = evaluate_post_retreat_final(backend, OUTCOME_POLICY)
    assert not result.success and result.failure_code == "POST_RETREAT_UNSTABLE"
```

（`FakeBackendPreRetreatStablePostRetreatTipped` 与 `OUTCOME_POLICY` 在测试文件内定义：前者按采样序返回"稳定 -> retreat 后 tilt 0.2 rad"的确定性样本；后者从 `config/validation_policies/light_cup_wall_pick.yaml` 经 `load_policy_bundle` 读出，阈值一律取自配置、测试内不硬编码新数值。）

- [ ] **Step 2: 运行确认 RED**

Run: `python3 -m pytest -q test/test_live_physical_outcome_contract.py -k "full_pose or post_retreat"`
Expected: FAIL（新接口缺失/旧实现未检查姿态与窗口）

- [ ] **Step 3: 最小实现**

`verify_physical_micro_lift` 在既有 lift/lateral 检查上追加：姿态容差（复用 `outcome_policy.max_upright_tilt_rad`）、脱离非预期支撑（复用 `evaluate_support_contact` 的反向断言）、固定窗口稳定（复用 `ReleaseSettleExecutor` 的窗口/速度阈值，只读不改动阈值数值）。`evaluate_post_retreat_final` 在 RETREAT 完成后新建 epoch 采样并产出 `FinalPlacementEvaluation`；`run_live_execute` 把 `final_outcome` 切换为 post-retreat 结果，预撤离结果保留为 `pre_retreat_outcome` 仅供审计。**不改任何固定阈值数值。**

- [ ] **Step 4: 运行确认 GREEN + 全量无回退**

Run: `python3 -m pytest -q test && colcon build --packages-select so101_gazebo_demo_py --symlink-install`
Expected: PASS；installed hash 与 src 一致。

- [ ] **Step 5: Commit**

```bash
git add src/so101_gazebo_demo_py/so101_gazebo_demo_py/live_execute.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/physical_outcome.py src/so101_gazebo_demo_py/test/test_live_physical_outcome_contract.py
git commit -m "feat(so101_py): enforce full-pose micro-lift and post-retreat final"
```

---

### Task 14: Package contract/full tests and installed provenance

**Files:**
- 不新增源码；本 task 是验收门（verification gate）。

**Interfaces:**
- Consumes: Task 1-13 全部产物。
- Produces: 可通过 CI 复跑的验收命令序列与 provenance 记录格式。

- [ ] **Step 1: focused 测试**

Run: `source /opt/ros/jazzy/setup.bash && source install/setup.bash && python3 -m pytest -q test/test_experiment_planner_action_graph.py test/test_experiment_planner_registry.py test/test_experiment_planner_materializer.py test/test_experiment_planner_generator.py test/test_experiment_planner_constraints.py test/test_experiment_planner_evaluator.py test/test_experiment_planner_ledger.py test/test_experiment_planner_reset.py test/test_experiment_planner_supervisor.py test/test_experiment_planner_cli.py test/test_experiment_planner_live_adapter.py`
Expected: 全 PASS。

- [ ] **Step 2: 包级测试**

Run: `python3 -m pytest -q test && colcon test --packages-select so101_gazebo_demo_py && colcon test-result --verbose`
Expected: 无回退（基线 141 passed, 2 skipped 起，只允许净增）；不运行 `ament_uncrustify --reformat`。

- [ ] **Step 3: installed provenance**

Run: `sha256sum build/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/*.py src/so101_gazebo_demo_py/so101_gazebo_demo_py/experiment_planner/*.py`（逐文件 build==src）；`which so101_experiment_planner`；`python3 -c "from ament_index_python.packages import get_package_share_directory; print(get_package_share_directory('so101_gazebo_demo_py'))"` 确认 prefix 是本 worktree 的 `install/`。
Expected: 全部一致；prefix 正确。

- [ ] **Step 4: Commit（仅当 Step 1-3 有伴随产物变更，如 provenance 记录追加）**

```bash
git add docs/experiments/so101-gazebo-demo-py-experiment-ledger.md
git commit -m "docs(so101_py): record planner package verification"
```

（本 task 只在**未来执行阶段**运行；本轮不执行。）

---

### Task 15: Isolated concurrency pilot（先证明编排隔离，再谈参数搜索）

**Files:**
- 不新增源码；live 编排任务，证据写入 `/tmp/so101-planner-pilot-*/` 与 ledger。

**Interfaces:**
- Consumes: Task 10 的 `allocate_lanes`/`wave_global_invalid`、Task 9 的 RESET_WORLD、Task 12 的 live adapter。
- Produces: 1->2->3 lane 的隔离证据（ROS graph 无串扰、GZ partition 独立、log/evidence/session/PID manifest 互不相交、RTF/内存/swap/磁盘快照）。

- [ ] **Step 1: ledger 预注册 PLANNED（pilot 三个 wave：1 lane、2 lane、3 lane，各带唯一 domain ≤ 232 与 partition）**

- [ ] **Step 2: 1 lane pilot**：启动干净 stack，执行一个 `evaluation_only=False` 的 baseline 候选到 `VERIFY_PHYSICAL_GRASP`，记录 RTF/内存/磁盘快照与 OwnedProcessManifest，清理并读回。

- [ ] **Step 3: 2 lane pilot**：两 lane 并行各跑 baseline 候选；断言无 cross-talk（`ros2 node list` 按 domain 隔离、partition 独立）；任一异常 => 整个 wave 记 `INVALID_ENVIRONMENT` 并降级。

- [ ] **Step 4: 3 lane pilot**：同上；资源/RTF 恶化 => 自动降级并记录。

- [ ] **Step 5: 记录与 Commit**：ledger 追加 pilot 结果（VALID_SUCCESS/INVALID_ENVIRONMENT 与证据路径）。

```bash
git add docs/experiments/so101-gazebo-demo-py-experiment-ledger.md
git commit -m "docs(so101_py): record concurrency pilot results"
```

（本 task 只在**未来执行阶段**运行；live 部分遵守 so101-dev 全部证据门。）

---

### Task 16: Adaptive physical search through complete ActionGraph

**Files:**
- 不新增源码；live 搜索任务，候选/结果走 Task 4-8 的 materializer/ledger，执行走 Task 11 `run-wave --mode screening`。

**Interfaces:**
- Consumes: Task 1-15 全部。
- Produces: 逐节点推进的 `PROVISIONAL_FEASIBLE` 候选与跨 lane 复验后的 `PROMOTED_ANCHOR`；完整单次成功路径的冻结 commit+policy fingerprint。

- [ ] **Step 1: 从首个失败节点（预期 `WAIT_GRASP_STABLE`/`MICRO_LIFT` 区段）开子树**：`plan-wave --batch-size 10` -> 准入 -> `run-wave --approved-checkpoint <id> --mode screening`；每 wave 先 ledger PLANNED；同 lane 候选间 RESET_WORLD（Task 9 九项 proof 全过，否则 INVALID_ENVIRONMENT 不用于学习）。

- [ ] **Step 2: 失败分类驱动下一 wave**：`StageEvaluator` 输出 `FailureCategory` -> `generate_wave` 只开映射子树；不做全量笛卡尔积；历史去重禁止结果购物；单次成功仅 `PROVISIONAL_FEASIBLE`。

- [ ] **Step 3: 跨 lane 两次 RESET_WORLD 复验 -> `promote_anchor`**；锚点仍不算最终验收。

- [ ] **Step 4: 逐节点推进 CARRY/PLACE/RELEASE/RETREAT/FINAL_STABLE**：下游证据指向上游余量不足时，带理由重开祖先节点（`reopenable_ancestors`），冻结前缀只冻参数、每次仍从初态完整执行物理前缀。

- [ ] **Step 5: 完整单次路径打通即冻结 commit+policy fingerprint**，ledger 记录 `CP-ADAPTIVE-ANCHOR-*` checkpoint 并 Commit。

```bash
git add docs/experiments/so101-gazebo-demo-py-experiment-ledger.md
git commit -m "docs(so101_py): record adaptive search anchor"
```

（本 task 只在**未来执行阶段**运行。）

---

### Task 17: Serial qualification/acceptance/publication gate

**Files:**
- 不新增源码；验收与发布门。

**Interfaces:**
- Consumes: Task 16 冻结 fingerprint、Task 11 `run-wave --mode qualification`。
- Produces: 最终验收证据链与发布闸门结论。

- [ ] **Step 1: 干净环境串行 FULL_RESTART×5**：同一冻结 commit/policy，每次全新 stack（唯一合法 domain/partition/tmux/证据目录）；post-retreat final outcome 为成功依据；`INVALID_*` 不计数但结束批次、`VALID_FAILURE` 清零 streak。

- [ ] **Step 2: 同一冻结版本串行 RESET_WORLD×5**：单 stack 内五次复位复跑，同样生命周期语义。

- [ ] **Step 3: fresh GUI/CUA 视觉证据**：按 so101-dev 的 snapshot -> action -> fresh snapshot 门获取本轮新截图。

- [ ] **Step 4: 验收电池**：fresh clean-cache build、全量 suite、dry-run、完整六态 plan-only、headless 各跑一遍并记录。

- [ ] **Step 5: 发布闸门**：全部通过后准备 scoped commits；push 前**再次停下请求用户确认**；不 force push、不用 `gh`、不在 dirty main 上合并；合并后重跑合并树测试再推 main。

（本 task 只在**未来执行阶段**运行。）

---

## Appendix A: Spec 覆盖表（spec 14 节 -> 本 plan task）

| Spec 节 | 覆盖 task |
|---|---|
| 1 目标（完整 pick-place，MICRO_LIFT 非中心） | Task 2（完整 20 态图）、Task 16（逐节点推进）、Task 17（最终验收） |
| 2 支配性边界 | Global Constraints 逐条；Task 1（0.001 hard max 与 0.0013 历史隔离）、Task 4（validation 不可变） |
| 3 动作图/节点声明/冻结前缀/祖先重开 | Task 2；祖先重开执行于 Task 16 Step 4 |
| 4 参数树 | Task 3（registry YAML 六组 + frozen/validation 字段） |
| 5 ParameterRegistry 字段 | Task 3（ParameterSpec 18 字段） |
| 6 自适应分批搜索（50/30/20、交互、准入、失败映射） | Task 5（生成）、Task 6（准入）、Task 7（失败映射） |
| 7 候选状态/评分/晋升 | Task 2（状态枚举）、Task 7（排序）、Task 8（晋升与分账） |
| 8 并发（3 lane、探测降级、单写者） | Task 10、Task 8（锁）、Task 15（pilot） |
| 9 RESET_WORLD 合同 | Task 9 |
| 10 晋级/最终验收 | Task 16（晋升）、Task 17（FULL_RESTART×5 + RESET_WORLD×5） |
| 11 架构组件 | File Structure + Task 2-12 一一对应 |
| 12 数据流/恢复幂等/provenance/资源守卫/磁盘水位/全局 invalid/可观察性 | Task 8（幂等/provenance）、Task 10（守卫/水位/全局 invalid）、Task 11（status 可观察性） |
| 13 异常与测试设计/非目标 | 各 task RED 测试；Task 14（防回退）；非目标落实于 Global Constraints 与非冻结纪律 |
| 14 完成条件/开放风险 | Task 17；开放风险由 Task 1（历史隔离）、Task 3（未审计 frozen）承载 |

## Execution Handoff

用户本轮明确要求**不执行**：本 plan 仅作为文档交付，不提供自动开始。后续用户再次授权执行时，两个选项：

1. **Subagent-Driven（推荐）**——按 superpowers:subagent-driven-development，每个 task 派新 subagent 实现、任务间两段式 review，迭代快。
2. **Inline Execution**——按 superpowers:executing-plans 在当前会话分批执行、checkpoint 处停下 review。

无论哪个选项，执行前都必须先完成 Global Constraints 的 Execution Setup Gate（新 worktree + so101-dev 证据门恢复）。
