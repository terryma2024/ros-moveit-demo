# SO-101 MoveIt expert validation Web implementation plan

> **For the ai-station Codex:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` and execute
> this plan inline in the current session. Do not delegate tasks to subagents. Steps use checkbox
> (`- [ ]`) syntax for tracking.

**Updated:** 2026-09-16 against merged upstream implementation
`origin/main@25d1130a990f34334b20e9ced4bcde4f4ed83aba`.

**Goal:** 在 Teleop Web 中交付一个独立的 MoveIt 专家随机点位验证页面，支持固定顺序、
固定并发和显式自适应 Worker 池三种模式、4 至 20 个确定性点位、实时 Worker/分代/俯视
状态、证据查看，以及业务失败点的串行 `FULL_RESTART` 重试。

**Architecture:** 长生命周期的 validation server 位于所有 MuJoCo stack 之外。它只持久化
Web lease、命令幂等、campaign-to-upstream binding、顶层执行 owner 和 retry queue。固定
`SEQUENTIAL`/`PARALLEL` 由 `ParallelBatchCoordinator` 权威执行；显式 `ADAPTIVE` 由生产
wrapper 持有 `AdaptiveBatchRunner`，Runner 跨 pool generation 保持唯一顶层 journal 和结果
权威，每个 generation 复用 coordinator。失败点重试仍是新的固定 N=1/K=1 coordinator batch。

**Tech Stack:** Python 3.12、ROS 2 Jazzy、MuJoCo、MoveIt 2、FastAPI、Pydantic、SQLite、React、TypeScript、SVG、Bun、Vitest、Playwright。

**Spec:** [SO-101 MoveIt expert random-position validation Web design](../specs/2026-09-11-so101-moveit-expert-validation-web-design.md)。执行者必须先完整阅读设计和本计划；设计是行为契约，本计划只拆解实现顺序。

**Upstream dependencies:**

- `docs/superpowers/specs/2026-09-11-so101-parallel-multipoint-validation-design.md` and
  `docs/superpowers/plans/2026-09-12-so101-parallel-multipoint-validation-implementation.md`;
- `docs/superpowers/specs/2026-09-14-so101-adaptive-worker-pool-design.md` and
  `docs/superpowers/plans/2026-09-14-so101-adaptive-worker-pool-implementation.md`.

本计划从两个上游计划的已验收产物开始，不复制 coordinator、Runner、wrapper、journal、
Worker、PerceptionBroker、精确 cleanup、资源观测或故障恢复实现。

**Implemented upstream baseline:** `25d1130a` contains `AdaptiveBatchRunner`,
`ProductionAdaptivePoolFactory`, `so101_parallel_batch`, `so101_parallel_batch_cleanup`,
`scripts/run_so101_adaptive_batch.zsh`, the frozen W8/W6/W4/W2/W1 configuration, C2 stateless
PerceptionBroker, W1–W16 contract support, and retained W1/W2/W4/W6/W8 plus W10 scaling evidence.
W8 remains the default; W16 is not live-qualified. This plan implements only the missing Teleop Web
adapter, projection, API, UI, evidence browser, and retry workflow.

## Global Constraints

- 本功能仅允许 MuJoCo 仿真，不得发送真实机械臂命令。实体机械臂继续保持 fail-closed 或 plan-only。
- `total_points` 是最终点位数，首版只接受 `4 <= total_points <= 20`，并始终包含四个固定锚点。
- API、event log、store、process ownership 和 retry command 一律使用 manifest 中不可变的 canonical `point.id`，例如 `task_start` 或 `sample_05_near_center`。`P01` 至 `P20` 只作为 `display_id` 出现在页面、图例和无障碍标签中；转换只能通过当前 manifest 完成。
- 默认 profile 是 `ai_station_baseline_v1`。`seed=20260911`、20 个点、15 mm 最小中心距、六位小数舍入、10,000 次拒绝上限和历史坐标必须逐项一致。
- 现有 35 mm geometry sampler 保留为独立 profile `geometry_v2`。不得静默修改任一 profile 的结果。
- `SEQUENTIAL` 强制 `worker_count=1`；`PARALLEL` 只接受 2–3 个 Worker。两者都使用上游
  动态 lease，不做固定分片。K 是正整数且不大于 20，`N × K < total_points` 时拒绝启动。
- `ADAPTIVE` 必须显式选择，默认 preferred W8、fallback W6/W4/W2/W1、
  `initial_points_per_worker=3`、`worker_start_timeout_s=120`、
  `max_infra_attempts_per_point=5`、`yolo_executor_count=2`。显式 preferred tier 接受 W1–W16，
  fallback 必须严格递减且可为空；Web 首版固定 C2，不开放任意 executor 修改。它禁止 K；
  initial affinity 不是容量上限。
- 页面默认顺序模式。固定并发必须通过上游 resource admission；自适应 preflight 只把
  CPU/RAM/GPU/pressure/RTF 记为 observation，不能据此拒绝、选 tier 或静默降级。自适应只
  根据真实 startup/process/OOM/RPC/Broker/cleanup 结果沿冻结 ladder 降级。
- 首轮点位状态使用上游 `PASSED | FAILED | INDETERMINATE | UNRUN`；`INVALID` 是 attempt
  状态，不得折叠成普通产品失败。`coverage_complete`、`execution_complete`、
  `batch_cleanup_complete` 和 `qualification_passed` 直接取 coordinator 结果。
- 自适应点位工作状态使用 Runner 的 `UNRUN | LEASED | RUNNING | INFRA_INTERRUPTED |
  PASSED | FAILED`。`PASSED`/`FAILED` 跨 generation 不可变；可能已开始的基础设施中断尝试
  保留 attempt-level `INDETERMINATE`，完成旧 generation 精确 cleanup 和 fresh initial gate
  后才可重跑。Web 不自行推导固定模式的四个 qualification flags。
- retry 不能覆盖首轮结果，也不能改变首轮成功率分母。固定模式安全终态或 adaptive
  `COMPLETED_WITH_FAILURES` 且 cleanup complete 后，只有业务 `FAILED` 具备 retry 资格；
  `INDETERMINATE`、`INFRA_INTERRUPTED`、`UNRUN`、`INFRA_FAILED` 和 unresolved `INVALID`
  不可重试。
- 每个人工 retry 是新的固定 `SEQUENTIAL` N=1/K=1 coordinator batch，使用 fresh Worker stack、batch/attempt ID、
  coordinator epoch、ROS domain、session 和 evidence child。
- 固定模式下 validation server 只拥有 coordinator identity；自适应模式下只拥有 wrapper
  的精确 PID identity。Wrapper 拥有 Runner child，Runner 拥有 generations，generation
  coordinator 独占 Broker/Worker/ROS/MuJoCo/MoveIt/controller。Web 不 signal wrapper PGID、
  Runner、Worker 或 Broker。所有层都禁止 broad `pkill`、`killall` 和进程名匹配。
- 未取得 mode-specific upstream 的 `batch_cleanup_complete=true` 和可验证 cleanup receipt
  时，Web supervisor 不得回收 fixed coordinator、结束 adaptive owner、启动下一次执行或推进
  retry queue；状态进入
  `NEEDS_OPERATOR_RECOVERY`。
- 固定 coordinator journal 或 adaptive Runner 顶层 journal 是执行进度提交权威。Generation
  journal 只作为 Runner 引用的嵌套证据。Web snapshot 只是缓存；HTTP/WebSocket
  只能发布已验证 journal frame 和 sealed manifest 的投影。
- 共享 Broker 保持 YOLO-first、Grounded-SAM 受限回退、generation fencing、有界公平队列
  和公共依赖暂停。Web 不发布共享 `/cup_pose`，也不重新判断模型结果。
- 浏览器只提交类型化意图。它不生成 shell、状态机 transition、关节目标或高频控制命令。
- MoveIt expert、ACT collection、ACT rollout 使用不同 executor/operation 和统计口径。MoveIt 成功点不能自动获得 ACT 数据资格。
- Web 依赖、测试和一次性 CLI 统一使用 Bun 与现有 `bun.lock`，不用 npm、npx 或 `package-lock.json`。
- 普通 `so101_demo_py` gate 只收集 `src/so101_demo_py/test/`。本任务不改变 benchmark，不运行 `benchmark_test/`。
- 不运行 `ament_uncrustify --reformat`，不使用 `gh`，不 force-push。每个 commit 只包含该任务列出的文件；计划中的 commit 不自动授权 push。
- README 保持英文。本计划不修改课程、learner session、`progress.yaml` 或 ACT 实现。

---

## 执行前准备与证据门

2026-09-16 文档同步以 `origin/main@25d1130a990f34334b20e9ced4bcde4f4ed83aba` 为源代码基线。
该 merge 已包含固定并发、自适应 Worker 池、stateless Broker、完整普通 pytest gate 和现场扩容
账本。实施开始时仍须重新核对 ai-station 的 commit、dirty state、tmux、进程、安装 overlay 和
上游证据哈希；不得把“已合并”直接当成当前安装可用。

- [ ] fetch `origin/main`，确认待实现基线包含 `25d1130a`，并回读
  `src/so101_demo_py/src/parallel_batch/adaptive_runner.py`、
  `src/so101_demo_py/src/parallel_batch/adaptive_pool.py`、
  `src/so101_demo_py/src/cli/parallel_batch_cleanup.py`、
  `scripts/run_so101_adaptive_batch.zsh` 和
  `src/so101_demo_py/config/mujoco/parallel_adaptive_workers_v1.yaml`。缺一即停止，不写兼容 shim。
- [ ] 核对 retained upstream ledger：固定并发验收、自适应故障注入、20 点执行、
  W1/W2/W4/W6/W8 scaling 和 ordinary package gate。W10 只作为附加合格样本；W16 只报告
  contract-supported/live-unqualified。证据或 installed provenance 不匹配时，仅把受影响模式标为
  unavailable，不改变其他模式。
- [ ] 使用 `superpowers:using-git-worktrees` 创建 Web 实现 worktree。起点必须同时包含
  已批准的并发实现、Web 设计与本计划；不要从未提交输入猜测基线。
- [ ] 读取根 `AGENTS.md`、`so101-dev`、`ai-station-access.md`、`so101-system-map.md`、`debug-evidence.md`、`test-and-acceptance.md` 和 `experiment-ledger.md`。
- [ ] 创建 `docs/experiments/so101-moveit-expert-validation-web-experiment-ledger.md`，并在任何代码或 live run 之前写入 base commit、worktree、dirty files、进程清单与第一个 `PLANNED` 条目。
- [ ] 为整个执行任务只建立一个 evidence root。macOS 使用 `/tmp`；ai-station 使用 `/data` durable root：

```zsh
if [[ "$(uname -s)" == Darwin ]]; then
  VALIDATION_EVIDENCE=$(mktemp -d /tmp/so101-debug-expert-validation-XXXXXXXX)
  VALIDATION_PYTHON=/Users/matianyi/ros2_jazzy/.venv/bin/python3
  eval "$(direnv export zsh)"
else
  source /opt/ros/jazzy/setup.zsh
  mkdir -p /data/work/so101-evidence/moveit-expert-validation
  VALIDATION_EVIDENCE=$(mktemp -d /data/work/so101-evidence/moveit-expert-validation/run-XXXXXXXX)
  VALIDATION_PYTHON=$(command -v python3)
fi
export VALIDATION_EVIDENCE VALIDATION_PYTHON
export ROS_HOME="$VALIDATION_EVIDENCE/ros-home"
export ROS_LOG_DIR="$ROS_HOME/log"
mkdir -p "$ROS_LOG_DIR"
export PYTHONPATH="$PWD/src/so101_demo_py/src:$PWD/src/so101_teleop${PYTHONPATH:+:$PYTHONPATH}"
"$VALIDATION_PYTHON" -c 'import sys,rclpy; print(sys.executable); print(rclpy.__file__)'
```

新 worktree 不得假设存在 `install/setup.zsh`。开发期定向测试使用上面的 source-tree `PYTHONPATH`；只有 Task 16 完成本轮隔离 build 后，才能 source `$VALIDATION_EVIDENCE/install/setup.zsh` 并声明 installed-runtime provenance。

- [ ] 在同一 shell 定义测试函数。ai-station 的每次 pytest/colcon test 都创建全新 NVMe scratch，并先证明 `tempfile.gettempdir()` 指向它：

```zsh
validation_pytest() {
  if [[ "$(uname -s)" == Linux ]]; then
    mkdir -p "$VALIDATION_EVIDENCE/scratch"
    VALIDATION_SCRATCH=$(mktemp -d "$VALIDATION_EVIDENCE/scratch/pytest-XXXXXXXX")
    mkdir "$VALIDATION_SCRATCH/tmp"
    export TMPDIR="$VALIDATION_SCRATCH/tmp"
    export TMP="$TMPDIR"
    export TEMP="$TMPDIR"
    "$VALIDATION_PYTHON" -c 'import os,tempfile; from pathlib import Path; assert Path(tempfile.gettempdir()).resolve()==Path(os.environ["TMPDIR"]).resolve()' || return 1
  fi
  PYTHONNOUSERSITE=1 /usr/bin/time -p "$VALIDATION_PYTHON" -m pytest -p no:cacheprovider "$@"
}

VALIDATION_REPO_ROOT=$PWD
validation_web() {
  (
    cd "$VALIDATION_REPO_ROOT/src/so101_teleop/web" || exit 1
    command -v bun
    bun --version
    bun install --frozen-lockfile
    bun "$@"
  )
}
```

每个 Task 的 RED/GREEN 命令使用 `validation_pytest` 或 `validation_web`。环境/bootstrap 失败不是 RED；先修复 provenance。每轮把命令、退出码、耗时和 scratch 路径写入实验账本。scratch 只列为 deletion candidate，未获授权不得删除。

## 文件结构与职责

| 单元 | 文件 | 责任 |
|---|---|---|
| Catalog 与几何 | `so101_teleop/expert_validation/catalog.py`, `projection.py`, `config/expert_validation/*` | 上游冻结 catalog 的 selection manifest、geometry 和共享投影 fixture |
| 上游执行 | `so101_demo.parallel_batch.*`, adaptive Runner/wrapper, `runtime/parallel_*.py`, `cli/mujoco_parallel_batch.py` | 固定 queue/lease/K 和 adaptive generations/fallback、journal、Worker、Broker、sealed result、recovery 和 terminal authority；本计划只消费 |
| Execution bridge | `so101_teleop/expert_validation/coordinator.py`, `adaptive.py`, `process_owner.py` | 固定 coordinator 或 adaptive wrapper 的 typed 启动/重连、顶层 journal cursor 和精确 owner identity |
| 持久化 | `so101_teleop/expert_validation/store.py` | SQLite Web command、service lease、campaign/upstream binding、tagged execution config、accepted top-level cursor、generation/fallback cache 和 retry queue |
| 监督器 | `so101_teleop/expert_validation/supervisor.py`, `service.py` | 三模式 preflight、首轮 binding、串行 retry、恢复与 mode-specific 只读统计投影 |
| API | `so101_teleop/expert_validation/api.py`, `main.py` | 独立 FastAPI 入口、lease、manifest、campaign、artifact 与 WebSocket |
| 证据适配 | `so101_teleop/expert_validation/artifacts.py` | 上游 opaque artifact 注册、Worker/attempt/recovery/Broker 证据只读映射 |
| Web | `web/src/expert-validation-app.tsx`, `api/expert-validation-*`, `components/expert-validation/*` | mode-specific setup、地图、Worker/generation/fallback、Broker、证据和 FULL_RESTART 操作 |
| 验收 | `docs/experiments/so101-moveit-expert-validation-web-experiment-ledger.md` | source/install/runtime、固定 4 点 smoke、adaptive 20 点首轮和重试证据 |

## 批次 A：冻结点位与 batch 协议

### Task 1: 复用上游冻结 catalog，并生成确定性 selection manifest

**Files:**

- Create: `src/so101_teleop/so101_teleop/expert_validation/__init__.py`
- Create: `src/so101_teleop/so101_teleop/expert_validation/catalog.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_catalog.py`
- Modify: `scripts/generate_so101_moveit_expert_position_top_view.py`

**Interfaces:**

- Consumes: installed
  `so101_demo_py/config/mujoco/moveit_expert_validation_points_v1.yaml`, frozen SHA256
  `c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5`, and the
  coordinator's canonical point parser.
- Produces: `CatalogPoint`, `PointSelection`,
  `load_baseline_catalog() -> tuple[CatalogPoint, ...]`,
  `select_catalog_points(total_points: int) -> PointSelection`, and
  `selection_sha256(point_ids: Sequence[str]) -> str`.

- [ ] **Step 1: 写 catalog/selection RED tests。**

```python
def test_baseline_catalog_is_shared_with_parallel_runtime():
    points = load_baseline_catalog()
    assert [p.id for p in points[:4]] == [
        "task_start", "cup_test_forward_5cm",
        "cup_test_left_5cm", "cup_test_right_5cm",
    ]
    assert points[4].position_world_m == (-0.020732, -0.249568, 0.165)
    assert points[-1].id == "sample_16_far_right"
    assert points[-1].position_world_m == (0.071574, -0.319255, 0.165)

def test_selection_is_stable_and_uses_only_catalog_ids():
    selection = select_catalog_points(total_points=9)
    assert len(selection.points) == 9
    assert [p.display_id for p in selection.points[:4]] == ["P01", "P02", "P03", "P04"]
    assert selection.catalog_seed == 20260911
    assert selection.selection_sha256 == selection_sha256([p.id for p in selection.points])
```

补测 3/21、catalog 字节哈希漂移、重复 ID、非有限坐标、四锚点顺序错误、selection
largest-remainder tie break、display ID 连续性，以及 selection 中每个 canonical ID 在上游
catalog 中恰好出现一次。

- [ ] **Step 2: 运行 RED。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_catalog.py -q
```

- [ ] **Step 3: 实现严格 catalog adapter。** 通过
  `ament_index_python.get_package_share_directory("so101_demo_py")` 定位 installed catalog，
  复用上游 parser，逐字节核对 SHA256。4–20 点 selection 按设计中的 nine-strata
  largest-remainder 规则从 catalog 选择，不重新运行随机数生成器，不复制另一份 YAML。
  `PointSelection` 保存 `catalog_id`、`catalog_seed=20260911`、catalog hash、有序 canonical
  IDs、selection hash 和连续 display IDs。

- [ ] **Step 4: 把维护脚本改成 catalog selection consumer。**

```python
parser.add_argument(
    "--catalog-profile",
    choices=("ai_station_baseline_v1", "geometry_v2"),
    default="ai_station_baseline_v1",
)
```

脚本继续生成 SVG/PNG/CSV/YAML。baseline execute 图只调用
`select_catalog_points(total_points)`；`geometry_v2` 保留为明确标注的 preview-only profile，
不得提交给 campaign API。通过 `ament_index_python` 查 installed config，源码模式只接受
显式 `--repository-root`。

- [ ] **Step 5: 运行 GREEN 和脚本 readback。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_catalog.py -q
"$VALIDATION_PYTHON" scripts/generate_so101_moveit_expert_position_top_view.py \
  --repository-root "$PWD" \
  --catalog-profile ai_station_baseline_v1 \
  --total-points 20 \
  --output-dir "$VALIDATION_EVIDENCE/top-view-fixture"
sha256sum "$VALIDATION_EVIDENCE/top-view-fixture"/*
```

预期 20 个坐标与上游 catalog 逐项一致，selection hash 可重复，最小间距为
`0.015116191120781703` m。

- [ ] **Step 6: Commit。**

```zsh
git add src/so101_teleop/so101_teleop/expert_validation \
  src/so101_teleop/test/teleop/test_expert_validation_catalog.py \
  scripts/generate_so101_moveit_expert_position_top_view.py
git commit -m "feat: select parallel validation catalog points"
```

### Task 2: 建立共享 world-to-SVG 投影契约

**Files:**

- Create: `src/so101_teleop/so101_teleop/expert_validation/projection.py`
- Create: `src/so101_teleop/config/expert_validation/top_view_projection_v1.json`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_projection.py`
- Modify: `scripts/generate_so101_moveit_expert_position_top_view.py`

**Interfaces:**

- Consumes: `PointSelection`, geometry, coordinator point status, active Worker stage, and blocking
  invalid-attempt state.
- Produces: `Projection(width_px: int, height_px: int, bounds_m: tuple[float, float, float, float])`, `project_xy(projection, x_m, y_m) -> tuple[float, float]`, `marker_style(status: str) -> MarkerStyle`, and one JSON golden fixture for React tests.

- [ ] **Step 1: 写投影与样式 RED tests。**

```python
def test_projection_uses_equal_xy_scale_and_equal_marker_radius(fixture):
    projection = Projection.from_geometry(fixture["geometry"], 1200, 900)
    assert projection.pixels_per_m_x == projection.pixels_per_m_y
    assert project_xy(projection, 0.02, -0.28) == pytest.approx(tuple(fixture["p01_px"]))
    assert marker_style("PASSED").radius_px == marker_style("FAILED").radius_px

@pytest.mark.parametrize("state,color", [
    ("ELIGIBLE_UNRUN", "blue"), ("LEASED", "blue"), ("EXECUTING", "blue"),
    ("PASSED", "green"), ("FAILED", "red"),
    ("INDETERMINATE", "red"), ("TERMINAL_UNRUN", "red"),
    ("INVALID_BLOCKED", "red"),
])
def test_status_palette_is_fixed(state, color):
    assert marker_style(state).semantic_color == color
```

- [ ] **Step 2: 运行 RED。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_projection.py -q
```

- [ ] **Step 3: 实现纯函数投影并生成 golden fixture。**

```python
@dataclass(frozen=True)
class Projection:
    width_px: int
    height_px: int
    bounds_m: tuple[float, float, float, float]
    pixels_per_m: float
    offset_x_px: float
    offset_y_px: float

    @property
    def pixels_per_m_x(self) -> float:
        return self.pixels_per_m

    @property
    def pixels_per_m_y(self) -> float:
        return self.pixels_per_m

def project_xy(value: Projection, x_m: float, y_m: float) -> tuple[float, float]:
    return (
        value.offset_x_px + x_m * value.pixels_per_m,
        value.offset_y_px - y_m * value.pixels_per_m,
    )
```

fixture 必须包含 table/base/target/P01/20 点投影、cup footprint radius、target tolerance
radius、marker radius 和 palette。P01 杯底与 target tolerance 使用虚线；selection 只增加
外圈。终态还要提供 shape/icon 和无障碍 label fixture，不能只靠颜色。

- [ ] **Step 4: 运行 GREEN，并核对 Python 输出仍使用新投影。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_projection.py -q
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_catalog.py -q
```

- [ ] **Step 5: Commit。**

```zsh
git add src/so101_teleop/so101_teleop/expert_validation/projection.py \
  src/so101_teleop/config/expert_validation/top_view_projection_v1.json \
  src/so101_teleop/test/teleop/test_expert_validation_projection.py \
  scripts/generate_so101_moveit_expert_position_top_view.py
git commit -m "feat: share expert validation map projection"
```

### Task 3: 建立 fixed coordinator / adaptive Runner 顶层 journal 的只读事件桥

**Files:**

- Create: `src/so101_teleop/so101_teleop/expert_validation/coordinator_events.py`
- Create: `src/so101_teleop/so101_teleop/expert_validation/adaptive_events.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_coordinator_events.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_adaptive_events.py`

**Interfaces:**

- Consumes: upstream `CoordinatorJournal.replay()` or the `AdaptiveBatchRunner` top-level journal
  replay API, immutable
  tagged `CampaignUpstreamBinding`, sealed manifests, and stored top-level cursor.
- Produces: `CoordinatorEventReader`, `AdaptiveEventReader`, mode-specific event views, and
  `verify_event_binding(event, binding) -> None`. Adaptive generation journals are never read as an
  independent second truth; only Runner references are exposed.

- [ ] **Step 1: 写 journal relay RED tests。**

```python
def test_reader_accepts_only_bound_batch_and_contiguous_chain(reader, binding):
    batch = reader.read_after(AcceptedCoordinatorCursor.initial(binding))
    assert [event.type for event in batch.events[:3]] == [
        "BATCH_STARTED", "LEASE_GRANTED", "ATTEMPT_STARTED",
    ]
    assert all(event.batch_id == binding.batch_id for event in batch.events)
    assert batch.next_cursor.previous_frame_sha256 == batch.events[-1].frame_sha256

def test_result_is_not_visible_before_coordinator_commit(reader, sealed_attempt):
    sealed_attempt.install()
    assert "PASSED" not in reader.read_after(reader.cursor).projected_point_states
    reader.journal.append("RESULT_COMMITTED", "result-p01", sealed_attempt.reference())
    assert reader.read_after(reader.cursor).projected_point_states["task_start"] == "PASSED"

def test_adaptive_reader_projects_runner_generations_not_nested_journal_directly(reader):
    view = reader.read_after(runner_cursor()).projection
    assert view.current_level == 6
    assert view.levels_used == (8, 6)
    assert view.fallbacks[0].transition == "W8_TO_W6"
    assert view.points["task_start"].status == "INFRA_INTERRUPTED"
```

补测 coordinator epoch、batch ID、event chain、lease/attempt identity、manifest hash、重复 result、
完整 frame checksum 错误、中段损坏、Web cursor 超前、Runner generation identity、terminal
result import、READY barrier、fallback transaction 和旧 generation 的迟到事件。EOF torn tail
由上游 journal recovery 裁决；Web 不能自行忽略或修补。

- [ ] **Step 2: 运行 RED。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_coordinator_events.py \
  src/so101_teleop/test/teleop/test_expert_validation_adaptive_events.py -q
```

- [ ] **Step 3: 实现 mode-specific 只读 adapter。** 直接调用上游 replay/verification API，不复制 frame parser。
  reader 只接受当前 `campaign_id -> batch_id/coordinator_epoch/journal_root` binding；先验证
  contiguous chain 和 referenced sealed manifest，再返回 immutable event views。任何冲突抛
  `CoordinatorProjectionError`，由 supervisor 转为 `NEEDS_OPERATOR_RECOVERY`。Adaptive reader
  只接受 Runner 顶层 batch/generation/hash chain，展示其 nested coordinator references、
  `levels_used`、fallback、infra attempt 和 cleanup；不得自行合并 generation journal。
  当前实现的 adaptive runtime root 固定为 `<evidence_root>/r/<batch_id>`，顶层 journal root 是
  其下的 `journal/`，终态投影是 `aggregate_results.json`，wrapper cleanup 回执是
  `cleanup-receipt.json`。这些路径从已绑定 request 推导并逐项校验，不做递归文件搜索。

- [ ] **Step 4: GREEN，并运行上游 journal regression。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_coordinator_events.py \
  src/so101_teleop/test/teleop/test_expert_validation_adaptive_events.py \
  src/so101_demo_py/test/test_parallel_batch_journal.py \
  src/so101_demo_py/test/test_parallel_batch_artifacts.py -q
```

- [ ] **Step 5: Commit。**

```zsh
git add src/so101_teleop/so101_teleop/expert_validation/coordinator_events.py \
  src/so101_teleop/so101_teleop/expert_validation/adaptive_events.py \
  src/so101_teleop/test/teleop/test_expert_validation_coordinator_events.py \
  src/so101_teleop/test/teleop/test_expert_validation_adaptive_events.py
git commit -m "feat: project validation upstream events"
```

### Task 4: 补齐点位终态和统计口径

**Files:**

- Create: `src/so101_teleop/so101_teleop/expert_validation/statistics.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_statistics.py`

**Interfaces:**

- Consumes: upstream fixed `BatchSummary` or adaptive `AdaptiveBatchSummary`, point/attempt/Worker
  projections, and accepted top-level events.
- Produces: `PointProjection`, `WorkerProjection`, `BrokerProjection`,
  `FixedFirstPassStatistics | AdaptiveFirstPassStatistics`, and mode-specific summary functions.

- [ ] **Step 1: 写状态与统计 RED tests。**

```python
def test_unreachable_is_evaluated_failure_not_unexecuted():
    view = summarize_first_pass(
        batch_summary(coverage_complete=True, qualification_passed=False),
        [point("task_start", "FAILED", reason="UNREACHABLE",
               evaluated=True, execution_started=False)],
    )
    assert view.valid_failed == 1
    assert view.not_executed == 0

def test_indeterminate_is_not_product_failure_or_retry_candidate():
    view = summarize_first_pass(
        batch_summary(execution_complete=True),
        [point("task_start", "INDETERMINATE", reason="OWNER_LOST")],
    )
    assert view.indeterminate == 1
    assert view.valid_failed == 0
    assert not view.points[0].retry_eligible

def test_web_never_upgrades_coordinator_qualification():
    view = summarize_first_pass(
        batch_summary(batch_cleanup_complete=False, qualification_passed=False),
        [point("task_start", "PASSED")],
    )
    assert view.valid_succeeded == 1
    assert view.qualified_success_rate is None
    assert view.qualification_passed is False

def test_adaptive_summary_preserves_attempt_history_and_runner_terminal():
    view = summarize_adaptive_first_pass(adaptive_summary(status="COMPLETED"))
    assert view.status == "COMPLETED"
    assert view.levels_used == (8, 6)
    assert view.points[0].status == "PASSED"
    assert view.points[0].attempts[0].status == "INDETERMINATE"
```

补测多 Worker 同时 active、`INVALID -> 新 attempt -> PASSED`、`FAILED`、terminal `UNRUN`、
capacity exhausted、Broker unavailable、Worker quarantine、最后一点恢复失败，以及 terminal
batch 不得有 active lease。Adaptive 补测 business `FAILED` 不触发降级、
`INFRA_INTERRUPTED` 可重排、`PASSED`/`FAILED` immutable、`COMPLETED`、
`COMPLETED_WITH_FAILURES`、`INFRA_FAILED` 和 W1 failure。Web 的计数必须等于 upstream
summary；不一致时 fail closed。

- [ ] **Step 2: 运行 RED。**

```zsh
validation_pytest src/so101_demo_py/test/test_parallel_batch_coordinator.py \
  src/so101_teleop/test/teleop/test_expert_validation_statistics.py -q
```

- [ ] **Step 3: 实现只读 projection 与公式。**

```python
@dataclass(frozen=True)
class PointProjection:
    point_id: str
    status: Literal["UNRUN", "PASSED", "FAILED", "INDETERMINATE"]
    evaluated: bool
    execution_started: bool
    active_worker_id: str | None
    invalid_attempts: int
    retry_eligible: bool
    reason: str | None = None

@dataclass(frozen=True)
class FirstPassStatistics:
    requested: int
    evaluated: int
    execution_started: int
    valid_succeeded: int
    valid_failed: int
    indeterminate: int
    invalid_attempts: int
    not_executed: int
    evaluation_coverage: float
    execution_coverage: float
    qualified_success_rate: float | None
    coverage_complete: bool
    execution_complete: bool
    batch_cleanup_complete: bool
    qualification_passed: bool
```

以 `BatchSummary` 的四个布尔值为权威。display counters 可从 accepted events 计算，但必须与
summary 相等。`FAILED` 才可 retry；`INDETERMINATE`、`UNRUN` 和 active point 不可 retry。
eligible `UNRUN` 在 active batch 投影为蓝色 pending，terminal `UNRUN` 投影为红色并显示原因。
Adaptive 使用独立 tagged summary：只接受 Runner 的 terminal status、final points、
`batch_cleanup_complete`、levels/fallbacks/generations、infra attempts 和 resource observations，
不生成 fixed 四 flags。`INFRA_INTERRUPTED` 在可继续时为蓝色；Runner `INFRA_FAILED` 后仍未
完成的点为红色。只有 `COMPLETED_WITH_FAILURES` 且 cleanup complete 的 business `FAILED`
允许人工 retry。

- [ ] **Step 4: 运行 GREEN。**

```zsh
validation_pytest src/so101_demo_py/test/test_parallel_batch_coordinator.py \
  src/so101_teleop/test/teleop/test_expert_validation_statistics.py -q
```

- [ ] **Step 5: Commit。**

```zsh
git add src/so101_teleop/so101_teleop/expert_validation/statistics.py \
  src/so101_teleop/test/teleop/test_expert_validation_statistics.py
git commit -m "feat: project parallel validation outcomes"
```

## 批次 B：进程、安全、持久化与服务

### Task 5: 建立 fixed coordinator / adaptive wrapper 顶层进程桥

**Files:**

- Create: `src/so101_teleop/so101_teleop/expert_validation/coordinator.py`
- Create: `src/so101_teleop/so101_teleop/expert_validation/adaptive.py`
- Create: `src/so101_teleop/so101_teleop/expert_validation/process_owner.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_process_owner.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_adaptive_owner.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_process_owner_integration.py`
- Create: `src/so101_teleop/test/fixtures/process_tree_helper.py`

**Interfaces:**

- Consumes: exact installed `so101_parallel_batch` executable, exact production
  `scripts/run_so101_adaptive_batch.zsh`, frozen fixed/adaptive start requests, Web store callbacks,
  fixed control/status socket, and Runner identity/journal handshake.
- Produces: tagged `OwnedExecution = OwnedCoordinator | OwnedAdaptiveWrapper`, mode-specific
  `spawn()`, `reconnect()`, `poll()`, `request_cancel()`, `request_status()`, and cleanup gating.

- [ ] **Step 1: 写所有权与重连 RED tests。**

```python
def test_owner_reconnects_only_to_exact_recorded_coordinator(owner, store):
    running = owner.spawn(start_request(batch_id="batch-a"))
    store.acknowledge_coordinator(running)
    assert owner.reconnect(store.binding("batch-a")) == running
    store.replace_started_ticks(running.started_ticks + 1)
    with pytest.raises(CoordinatorOwnershipError, match="PROCESS_IDENTITY_MISMATCH"):
        owner.reconnect(store.binding("batch-a"))

def test_web_owner_never_signals_worker_groups(owner, upstream):
    running = owner.spawn(start_request(batch_id="batch-a"))
    upstream.cleanup_complete = False
    with pytest.raises(CoordinatorOwnershipError, match="CLEANUP_NOT_CONFIRMED"):
        owner.stop_after_cleanup(running)
    assert upstream.worker_signal_calls == []

def test_adaptive_cancel_targets_exact_wrapper_pid_only(owner, wrapper):
    running = owner.spawn(adaptive_start_request(batch_id="a20"))
    owner.request_cancel(running)
    assert wrapper.signals == [(running.pid, "SIGINT")]
    assert wrapper.process_group_signals == []
```

补测 spawn intent 前/后崩溃、exec barrier ACK 丢失、socket owner/mode/token 错误、PID
复用、leader 退出而 descendant 留存、coordinator 返回码与 journal terminal 冲突、bounded
stdout/stderr、wrapper PID reuse、Runner binding mismatch、Runner crash cleanup、wrapper
SIGKILL 后 ACTIVE domain claim fail-closed，以及两个 campaign 不能同时拥有 execution owner。

- [ ] **Step 2: 运行 RED。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_process_owner.py \
  src/so101_teleop/test/teleop/test_expert_validation_adaptive_owner.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner_integration.py -q
```

- [ ] **Step 3: 实现 tagged execution owner。**

```python
@dataclass(frozen=True)
class CoordinatorStartRequest:
    campaign_id: str
    batch_id: str
    execution_mode: Literal["SEQUENTIAL", "PARALLEL"]
    worker_count: int
    max_points_per_worker: int
    argv: tuple[str, ...]
    environment: Mapping[str, str]
    batch_root: Path
    control_socket: Path
    control_token_sha256: str

@dataclass(frozen=True)
class OwnedCoordinator:
    campaign_id: str
    batch_id: str
    pid: int
    pgid: int
    started_ticks: int
    argv_sha256: str
    environment_sha256: str
    control_socket: Path
    coordinator_epoch: int
```

另定义 `AdaptiveStartRequest`，冻结 1–5 字符 ASCII batch ID、
`<evidence-root>/r/<batch-id>`、W1–W16 preferred tier、严格递减且可为空的 fallback tiers、
initial affinity、startup timeout、infra attempt limit、只读 C2 `yolo_executor_count`、adaptive
config/model/Broker hashes；它必须拒绝 K 和 fixed-mode live-headroom 字段。`OwnedAdaptiveWrapper` 只记录
wrapper PID/start ticks/argv/env hash、Runner PID/batch handshake 和 Runner journal root，不把
Runner 或 generation descendants 变成 Web-owned process。

owner 在 coordinator exec barrier 前调用 Web store 写 `COORDINATOR_SPAWN_INTENT`，收到
PID/PGID/start-time/socket/coordinator-epoch ACK 后写 `COORDINATOR_RUNNING` 并放行。argv
必须从 typed request 构造，精确传递 catalog、repeatable point IDs、config、batch ID、N/K、
batch root、Broker image/model hashes 和 `--run-mode execute`；浏览器不能提供 argv。
Worker/Broker process ownership 完全留在上游 coordinator。

Adaptive argv 必须调用生产 wrapper 并显式传 `--adaptive-workers`；wrapper 负责 Runner child
和 `so101_parallel_batch_cleanup`，Runner 负责 generations。浏览器不能提供 argv。Web cancel
只向身份复核后的 wrapper PID 发请求，不用 `killpg`；无 ACK 或 cleanup 不明时进入
`NEEDS_OPERATOR_RECOVERY`。Web server 可重连仍存活的 wrapper/Runner；Runner crash 不自动
resume，wrapper cleanup 成功投影 `INFRA_FAILED`。

- [ ] **Step 4: 写并运行真实 OS process integration gate。**

`process_tree_helper.py` 只创建无 ROS 的短生命周期 coordinator/descendant 进程。测试使用
真实 PID/PGID、0600 control socket、adaptive wrapper/Runner helper 和 fsync store callback，覆盖 leader 先退出、exec
barrier 前崩溃、ACK 丢失、server restart 重连、cleanup receipt 前拒绝 signal，以及 cleanup
后只停止 fixed coordinator group，以及 adaptive cancel 仅命中 wrapper PID。测试不能
monkeypatch `Popen`、`killpg` 或 `/proc` 读取。

```zsh
validation_pytest \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner_integration.py -q
```

- [ ] **Step 5: 运行 GREEN。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_process_owner.py \
  src/so101_teleop/test/teleop/test_expert_validation_adaptive_owner.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner_integration.py -q
```

- [ ] **Step 6: Commit。**

```zsh
git add src/so101_teleop/so101_teleop/expert_validation/coordinator.py \
  src/so101_teleop/so101_teleop/expert_validation/adaptive.py \
  src/so101_teleop/so101_teleop/expert_validation/process_owner.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner.py \
  src/so101_teleop/test/teleop/test_expert_validation_adaptive_owner.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner_integration.py \
  src/so101_teleop/test/fixtures/process_tree_helper.py
git commit -m "feat: own validation execution wrappers"
```

### Task 6: 接入 mode-specific control 和 cleanup 门

**Files:**

- Create: `src/so101_teleop/so101_teleop/expert_validation/control.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_control.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/coordinator.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/process_owner.py`

**Interfaces:**

- Consumes: Web command identity, tagged upstream binding, fixed coordinator epoch/token/replies or
  adaptive wrapper/Runner status, Worker/generation recovery receipts, and mode-specific terminal
  summary.
- Produces: fixed `CoordinatorControlClient`, adaptive `AdaptiveWrapperControl`, tagged cleanup
  authorization, and owner-specific stop/cancel gates.

- [ ] **Step 1: 写取消、失联和 cleanup RED tests。**

```python
def test_cancel_goes_to_coordinator_not_worker_groups(control, owner):
    control.cancel(command_id="cancel-1", binding=binding("campaign-a", "batch-a", epoch=4))
    assert control.sent_messages[-1]["operation"] == "CANCEL_BATCH"
    assert owner.signal_calls == []

def test_coordinator_stop_requires_terminal_cleanup(control, owner):
    control.reply = terminal_summary(batch_cleanup_complete=False)
    with pytest.raises(CleanupNotAuthorized, match="BATCH_CLEANUP_INCOMPLETE"):
        authorize_coordinator_stop(control.status(), binding("campaign-a", "batch-a", epoch=4))
    assert owner.signal_calls == []

def test_stale_epoch_reply_is_rejected(control):
    control.reply = status_reply(batch_id="batch-a", coordinator_epoch=3)
    with pytest.raises(ControlProtocolError, match="COORDINATOR_EPOCH_MISMATCH"):
        control.status(binding("campaign-a", "batch-a", epoch=4))

def test_adaptive_cleanup_failure_never_starts_next_generation(control):
    control.reply = adaptive_status(state="DEGRADING", cleanup_complete=False)
    with pytest.raises(CleanupNotAuthorized):
        control.await_next_generation()
```

补测 token/schema/command ID 错误、partial/oversized frame、ACK timeout、coordinator socket
断开、Web lease expiry、parallel active Workers、Broker recovery、Worker quarantine、cancel 后
terminal `UNRUN`、adaptive wrapper PID mismatch、Runner loss、generation cleanup failure、
surviving descendant 和 owner 已退出但 top-level journal 非 terminal。

- [ ] **Step 2: 运行 RED。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_control.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner.py -q
```

- [ ] **Step 3: 实现闭合 control schema。**

```python
@dataclass(frozen=True)
class CoordinatorControlRequest:
    schema_version: int
    command_id: str
    campaign_id: str
    batch_id: str
    coordinator_epoch: int
    operation: Literal["STATUS", "CANCEL_BATCH"]
    request_sha256: str

@dataclass(frozen=True)
class BatchCleanupAuthorization:
    batch_id: str
    coordinator_epoch: int
    batch_cleanup_complete: bool
    owned_descendants_gone: bool
    assigned_ros_domains_clear: bool
    receipt_sha256: str
```

control socket 必须位于绑定的 batch root，目录 0700、socket 0600，校验 peer token、batch ID
和 coordinator epoch。Web lease expiry 与 operator cancel 都发送幂等 `CANCEL_BATCH`；coordinator
负责停止新 lease、fence、controller cancel/confirm、Worker recovery 和点位终态。
Web 从不向 Worker/Broker socket 发消息。

Adaptive control 只面向精确 wrapper PID；wrapper 转发 Runner cancel 并执行 upstream cleanup。
Web 读取 Runner journal 判断 generation/batch terminal，不能跳过旧 generation cleanup、直接
启动下一 tier，或从 process exit 推导 cleanup。

- [ ] **Step 4: 接入 mode-specific stop gate。** 固定模式只有 terminal `BatchSummary`、
  `batch_cleanup_complete=true`、cleanup receipt hash、descendant inventory 和 assigned ROS
  domain clear 同时通过，process owner 才能停止 coordinator PGID。ACK timeout、socket
  消失或证据不一致进入 `NEEDS_OPERATOR_RECOVERY`。
  Adaptive 模式只请求 wrapper cooperative cancel/cleanup；Web 不直接 stop Runner 或
  generation coordinator。Runner `INFRA_FAILED` 且 wrapper cleanup complete 可安全终止，
  cleanup 证据缺失则进入 `NEEDS_OPERATOR_RECOVERY`。

- [ ] **Step 5: 运行 GREEN。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_control.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner.py -q
```

- [ ] **Step 6: Commit。**

```zsh
git add src/so101_teleop/so101_teleop/expert_validation/control.py \
  src/so101_teleop/so101_teleop/expert_validation/coordinator.py \
  src/so101_teleop/so101_teleop/expert_validation/process_owner.py \
  src/so101_teleop/test/teleop/test_expert_validation_control.py
git commit -m "feat: control parallel validation coordinators"
```

### Task 7: 实现 durable supervisor store 与幂等事务

**Files:**

- Create: `src/so101_teleop/so101_teleop/expert_validation/store.py`
- Create: `src/so101_teleop/so101_teleop/expert_validation/models.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_store.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/process_owner.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_process_owner_integration.py`

**Interfaces:**

- Consumes: canonical Web command bodies, campaign manifests, Task 5 tagged execution ownership
  callbacks, Task 3 accepted top-level cursors, and mode-specific terminal/cleanup receipts.
- Produces: `SupervisorStore.open(root: Path)`, `begin_command()`,
  `record_preflight_receipt()`, `consume_preflight_and_bind_campaign_batch()`,
  `record_execution_owner_intent()`, `acknowledge_execution_owner()`,
  `accept_upstream_cursor()`, `record_cleanup_and_advance_retry()`, `finish_command()`,
  `reconcile()`, and immutable query projections.

- [ ] **Step 1: 写 crash-window RED tests。**

```python
def test_reopen_returns_completed_idempotent_command(tmp_path):
    store = SupervisorStore.open(tmp_path)
    store.begin_command("cmd-1", "sha-a", "START_CAMPAIGN")
    store.finish_command("cmd-1", {"campaign_id": "campaign-1"})
    store.close()
    assert SupervisorStore.open(tmp_path).repeat_command("cmd-1", "sha-a") == {
        "campaign_id": "campaign-1"
    }

def test_same_id_different_payload_is_rejected(store):
    store.begin_command("cmd-1", "sha-a", "START_CAMPAIGN")
    with pytest.raises(StoreConflict, match="COMMAND_ID_REUSED"):
        store.repeat_command("cmd-1", "sha-b")

def test_reopen_recovers_ownership_and_retry_cursor_without_memory_state(tmp_path):
    store = SupervisorStore.open(tmp_path)
    store.bind_campaign_batch(binding("campaign-1", "batch-1", "PARALLEL", 2, 10))
    store.record_coordinator_intent(coordinator_intent("batch-1", token="spawn-a"))
    store.acknowledge_coordinator(coordinator_ack("batch-1", pid=123, pgid=123, epoch=4))
    store.enqueue_retries("campaign-1", ["sample_05_near_center", "sample_14_far_right"])
    store.close()
    reopened = SupervisorStore.open(tmp_path)
    assert reopened.owned_coordinator("batch-1").spawn_token == "spawn-a"
    assert reopened.next_retry("campaign-1").point_id == "sample_05_near_center"

def test_cleanup_and_retry_advance_are_one_transaction(store):
    store.enqueue_retries("campaign-1", ["sample_05_near_center"])
    store.record_cleanup_and_advance_retry(batch_cleanup_receipt("retry-batch-1"))
    assert store.next_retry("campaign-1") is None
```

补充 fixed/adaptive owner intent 后崩溃、ACK 后崩溃、Runner generation change、upstream journal commit 后 Web cursor 前、cursor
后 HTTP 前、retry terminal 后 cleanup 前、cleanup 后 dequeue 前、singleton lock 和 ambiguous
command 测试。证明 store 中不存在 Worker lease、point result 或 Broker health 的第二写入路径。

- [ ] **Step 2: 运行 RED。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_store.py -q
```

- [ ] **Step 3: 创建 SQLite schema。**

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
PRAGMA foreign_keys=ON;

CREATE TABLE commands (
  command_id TEXT PRIMARY KEY,
  request_sha256 TEXT NOT NULL,
  operation TEXT NOT NULL,
  state TEXT NOT NULL,
  result_json TEXT
);
CREATE TABLE manifests (
  manifest_id TEXT PRIMARY KEY,
  canonical_json TEXT NOT NULL,
  manifest_sha256 TEXT NOT NULL,
  source_config_sha256 TEXT NOT NULL,
  created_at_ns INTEGER NOT NULL
);
CREATE TABLE preflight_receipts (
  receipt_id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL UNIQUE,
  manifest_id TEXT NOT NULL REFERENCES manifests(manifest_id),
  canonical_start_request_sha256 TEXT NOT NULL,
  receipt_json TEXT NOT NULL,
  receipt_sha256 TEXT NOT NULL,
  expires_at_monotonic_ns INTEGER NOT NULL,
  consumed_at_ns INTEGER
);
CREATE TABLE campaigns (
  campaign_id TEXT PRIMARY KEY,
  state TEXT NOT NULL,
  manifest_id TEXT NOT NULL REFERENCES manifests(manifest_id),
  executor_id TEXT NOT NULL,
  operation_id TEXT NOT NULL,
  executor_config_sha256 TEXT NOT NULL,
  execution_mode TEXT NOT NULL CHECK (execution_mode IN ('SEQUENTIAL','PARALLEL','ADAPTIVE')),
  execution_config_json TEXT NOT NULL,
  execution_config_sha256 TEXT NOT NULL,
  preflight_receipt_id TEXT NOT NULL UNIQUE REFERENCES preflight_receipts(receipt_id)
);
CREATE TABLE campaign_batches (
  batch_id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
  batch_kind TEXT NOT NULL CHECK (batch_kind IN ('FIRST_PASS','FULL_RESTART_RETRY')),
  point_id TEXT,
  state TEXT NOT NULL,
  coordinator_epoch INTEGER,
  pool_generation INTEGER,
  journal_root TEXT NOT NULL,
  terminal_summary_sha256 TEXT,
  cleanup_receipt_sha256 TEXT
);
CREATE TABLE upstream_cursors (
  batch_id TEXT PRIMARY KEY REFERENCES campaign_batches(batch_id),
  owner_kind TEXT NOT NULL CHECK (owner_kind IN ('COORDINATOR','ADAPTIVE_RUNNER')),
  owner_epoch_or_generation INTEGER NOT NULL,
  segment_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  frame_sha256 TEXT NOT NULL
);
CREATE TABLE owned_execution (
  batch_id TEXT PRIMARY KEY REFERENCES campaign_batches(batch_id),
  owner_kind TEXT NOT NULL CHECK (owner_kind IN ('COORDINATOR','ADAPTIVE_WRAPPER')),
  state TEXT NOT NULL,
  spawn_token TEXT NOT NULL UNIQUE,
  expected_executable TEXT NOT NULL,
  argv_sha256 TEXT NOT NULL,
  environment_sha256 TEXT NOT NULL,
  source_commit TEXT NOT NULL,
  install_prefix TEXT NOT NULL,
  runtime_sha256 TEXT NOT NULL,
  pid INTEGER,
  pgid INTEGER,
  started_ticks INTEGER,
  control_socket TEXT,
  coordinator_epoch INTEGER,
  runner_pid INTEGER,
  runner_journal_root TEXT,
  acknowledged_at_ns INTEGER
);
CREATE TABLE adaptive_projection_cache (
  batch_id TEXT PRIMARY KEY REFERENCES campaign_batches(batch_id),
  current_generation INTEGER,
  current_level INTEGER,
  fallback_history_json TEXT NOT NULL,
  resource_observations_json TEXT NOT NULL
);
CREATE TABLE retry_queue (
  campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
  ordinal INTEGER NOT NULL,
  point_id TEXT NOT NULL,
  state TEXT NOT NULL,
  batch_id TEXT REFERENCES campaign_batches(batch_id),
  cleanup_receipt_sha256 TEXT,
  PRIMARY KEY (campaign_id, ordinal)
);
CREATE TABLE leases (lease_id TEXT PRIMARY KEY, service_session_id TEXT NOT NULL, generation INTEGER NOT NULL, expires_monotonic_ns INTEGER NOT NULL, state TEXT NOT NULL);
```

所有 mutation 使用 `BEGIN IMMEDIATE`，canonical JSON 使用 sorted keys 与 UTF-8，store root 必须是绝对非 symlink 路径。OS-level lock 文件在 SQLite 打开前取得，第二个 writer 返回 `VALIDATION_SUPERVISOR_ACTIVE`。

`execution_config_json` 是 tagged union：固定模式保存 N/K，自适应保存 preferred/fallback、
initial affinity、timeout、infra-attempt limit 和 config hash，二者互斥。自适应 cache 可由 Runner
journal删除重建，不具备提交权。

事务顺序固定为：command/campaign/batch binding 或 retry queue 先落盘；execution owner fork 前单独
提交 ownership intent；child 停在 exec barrier；mode-specific identity readback 在
同一 acknowledgement 事务写入后才放行；accepted upstream cursor 单独提交；terminal batch
cleanup receipt 与 retry cursor advance 必须处于同一事务；最后提交 command result，随后才
返回 HTTP。重启测试关闭旧 store、丢弃全部 Python 对象，再从 SQLite、fixed coordinator 或
adaptive Runner 顶层 journal 和 `/proc` 重建状态。Worker/point/Broker 状态只从绑定的顶层
journal 重放。任何缺失 ACK、
fingerprint mismatch 或 cursor/cleanup 不一致都返回 `COMMAND_OUTCOME_UNKNOWN` 或进入
`NEEDS_OPERATOR_RECOVERY`。

- [ ] **Step 4: 运行 GREEN。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_store.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner_integration.py -q
```

- [ ] **Step 5: Commit。**

```zsh
git add src/so101_teleop/so101_teleop/expert_validation/models.py \
  src/so101_teleop/so101_teleop/expert_validation/store.py \
  src/so101_teleop/so101_teleop/expert_validation/process_owner.py \
  src/so101_teleop/test/teleop/test_expert_validation_store.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner_integration.py
git commit -m "feat: persist expert validation supervisor state"
```

### Task 8: 实现三模式 campaign supervisor

**Files:**

- Create: `src/so101_teleop/so101_teleop/expert_validation/supervisor.py`
- Create: `src/so101_teleop/so101_teleop/expert_validation/preflight.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_supervisor.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_preflight.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/coordinator.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/adaptive.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/control.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/process_owner.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/store.py`

**Interfaces:**

- Consumes: `SupervisorStore`, `PointSelection`, upstream fixed/adaptive configs,
  model/install/domain/resource probes, tagged process/control/event ports, and statistics projection.
- Produces: `CampaignPreflightReceipt`,
  `ExpertValidationSupervisor.preflight()`, `start_first_pass()`, `cancel()`,
  `start_retries()`, `status()`, `list_campaigns()`, and `reconcile_startup()`.

- [ ] **Step 1: 写 lifecycle RED tests。**

```python
async def test_sequential_and_parallel_use_same_coordinator_path(supervisor, owner):
    await supervisor.start_first_pass(start_request("manifest-4", "SEQUENTIAL", n=1, k=4))
    await owner.finish(batch_cleanup_complete=True)
    await supervisor.start_first_pass(start_request("manifest-4b", "PARALLEL", n=2, k=2))
    assert [(r.worker_count, r.max_points_per_worker) for r in owner.requests] == [
        (1, 4), (2, 2),
    ]

async def test_each_retry_gets_new_n1_k1_batch_and_cleanup_before_next(owner, supervisor):
    await supervisor.start_retries(retry_request(
        "campaign-1", ["sample_05_near_center", "sample_14_far_right"]
    ))
    assert owner.timeline == [
        "start-batch-sample_05_near_center-n1-k1",
        "cleanup-batch-sample_05_near_center",
        "start-batch-sample_14_far_right-n1-k1",
        "cleanup-batch-sample_14_far_right",
    ]

async def test_parallel_never_silently_downgrades(supervisor, resources):
    resources.reject("GPU_HEADROOM")
    with pytest.raises(PreflightRejected, match="GPU_HEADROOM"):
        await supervisor.start_first_pass(
            start_request("manifest-20", "PARALLEL", n=2, k=10)
        )
    assert supervisor.process_owner.spawn_calls == []

async def test_adaptive_uses_wrapper_ladder_without_k(supervisor, owner):
    request = adaptive_start_request(
        "manifest-20", preferred=8, fallback=(6, 4, 2, 1), initial_affinity=3
    )
    await supervisor.start_first_pass(request)
    assert owner.requests[-1].owner_kind == "ADAPTIVE_WRAPPER"
    assert owner.requests[-1].max_points_per_worker is None

async def test_adaptive_resource_observations_do_not_reject_start(supervisor, resources):
    resources.observe(gpu_headroom="LOW", memory_pressure="HIGH")
    receipt = await supervisor.preflight(adaptive_start_request("manifest-20"))
    assert receipt.admitted is True
    assert receipt.resource_observations["memory_pressure"] == "HIGH"
```

覆盖 `SEQUENTIAL` N≠1、`PARALLEL` N<2/N>3、N×K 不足、默认 K、显式 K、adaptive 与 K
互斥、ladder 顺序、1–5 字符 ASCII batch ID、runtime root、stale preflight、no second active
execution owner、只有安全终态 business `FAILED` 可 retry、cleanup failure stops queue、
fixed owner/Runner death、server restart reconciliation 和
`LIVE_RETRY_NOT_APPLICABLE_ALL_SUCCEEDED`。

- [ ] **Step 2: 运行 RED。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_preflight.py \
  src/so101_teleop/test/teleop/test_expert_validation_supervisor.py -q
```

- [ ] **Step 3: 实现 campaign preflight contract。**

```python
@dataclass(frozen=True)
class CampaignPreflightReceipt:
    receipt_id: str
    campaign_id: str
    service_session_id: str
    lease_generation: int
    manifest_id: str
    canonical_start_request_sha256: str
    execution_mode: Literal["SEQUENTIAL", "PARALLEL", "ADAPTIVE"]
    execution_config: FixedExecutionConfig | AdaptiveExecutionConfig
    point_count: int
    capacity: int
    source_commit: str
    install_prefix: str
    coordinator_executable_sha256: str
    adaptive_runner_module_sha256: str | None
    adaptive_pool_module_sha256: str | None
    adaptive_cleanup_executable_sha256: str | None
    adaptive_wrapper_sha256: str | None
    parallel_config_sha256: str
    adaptive_config_sha256: str | None
    catalog_sha256: str
    selection_sha256: str
    yolo_weights_sha256: str
    grounded_sam_manifest_sha256: str
    broker_image_id: str
    resource_manifest_sha256: str
    observed_at_ns: int
    expires_at_monotonic_ns: int
    admitted: bool
    reason_codes: tuple[str, ...]
```

preflight 直接调用上游严格配置解析、catalog/selection 校验、模型/Broker provenance、domain
claim 和 execution-owner singleton probe。固定模式调用 resource allocator；省略 K 时使用
`ceil(total_points / worker_count)`，显式 K 不足或资源不足拒绝。Adaptive 校验字段互斥、冻结
ladder、config/wrapper/Runner/cleanup provenance、短 batch ID、runtime root 和 unresolved owner，
但资源指标只作为 observation，不参与 admitted 或 tier 选择。依赖缺失或 hash 漂移都返回稳定
reason code，不启动 owner，也不改变请求模式。receipt 绑定 canonical start body、prospective campaign ID、service session 和
lease generation，并使用短期 monotonic expiry；start 时必须重算请求 hash、确认未过期且未被
消费，并重新检查 singleton 与未解决 cleanup。start 在创建 campaign/batch binding 的同一事务中
消费一次性 receipt。

- [ ] **Step 4: 实现 typed fixed coordinator / adaptive wrapper 启动。**

```python
def coordinator_argv(request: CoordinatorStartRequest) -> tuple[str, ...]:
    return (
        "ros2", "run", "so101_demo_py", "so101_parallel_batch",
        "--points", str(request.points_path),
        "--config", str(request.parallel_config_path),
        "--batch-id", request.batch_id,
        "--worker-count", str(request.worker_count),
        "--max-points-per-worker", str(request.max_points_per_worker),
        "--evidence-root", str(request.batch_root),
        "--run-mode", "execute",
    )
```

argv 还要按 manifest 顺序追加 repeatable canonical `--point-id`，并传递 frozen model/Broker
provenance；所有参数都由服务端 typed request 构造。Web supervisor 只执行一次 coordinator spawn，
Worker stack、ROS domain、session、Broker token 和 point gate 全由上游 coordinator 分配与记录。
retry 使用相同路径但固定 N=1/K=1 和单点 selection；禁止 `--attach-existing-stack` 或旧
`mujoco_rgbd_batch.py` fallback。

Adaptive 路径只能执行 `scripts/run_so101_adaptive_batch.zsh`，显式传
`--adaptive-workers`、`--worker-count 8`、`--fallback-worker-counts 6,4,2,1`、
`--initial-points-per-worker 3`、`--worker-start-timeout-s 120`、
`--max-infra-attempts-per-point 5`、`--yolo-executor-count 2`、`--adaptive-config`、短 batch ID 和 runtime root，且不得传
`--max-points-per-worker`。Web 只 spawn
一次 wrapper；Runner 负责 W8/W6/W4/W2/W1 generation 与 top-level journal。

- [ ] **Step 5: 实现 terminal/recovery 顺序。**

固定模式先接受 coordinator 的 terminal `BatchSummary`；adaptive 接受 Runner
`COMPLETED | COMPLETED_WITH_FAILURES | INFRA_FAILED`、final point set、generation/fallback
history 和 sealed references。两者随后接受 `batch_cleanup_complete=true` 的 cleanup receipt。
Web 只在授权后停止/回收固定 coordinator；adaptive 只通过 wrapper cleanup。Wrapper exit 0
只对应 `COMPLETED`；exit 1 可能是 `COMPLETED_WITH_FAILURES` 或 `INFRA_FAILED`，必须结合 Runner
journal 裁决，不能把非零退出一律当进程故障；
任何缺口写 `NEEDS_OPERATOR_RECOVERY`。retry queue 只有在 one-point batch 的 cleanup receipt
与 coordinator reconciliation 同一事务落盘后推进。

- [ ] **Step 6: 运行 GREEN。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_preflight.py \
  src/so101_teleop/test/teleop/test_expert_validation_supervisor.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner.py \
  src/so101_teleop/test/teleop/test_expert_validation_store.py \
  src/so101_demo_py/test/test_parallel_batch_cli.py -q
```

- [ ] **Step 7: Commit。**

```zsh
git add src/so101_teleop/so101_teleop/expert_validation/supervisor.py \
  src/so101_teleop/so101_teleop/expert_validation/preflight.py \
  src/so101_teleop/so101_teleop/expert_validation/coordinator.py \
  src/so101_teleop/so101_teleop/expert_validation/adaptive.py \
  src/so101_teleop/so101_teleop/expert_validation/control.py \
  src/so101_teleop/so101_teleop/expert_validation/process_owner.py \
  src/so101_teleop/so101_teleop/expert_validation/store.py \
  src/so101_teleop/test/teleop/test_expert_validation_preflight.py \
  src/so101_teleop/test/teleop/test_expert_validation_supervisor.py
git commit -m "feat: supervise validation execution modes"
```

### Task 9: 加入 lease、executor registry 和 application service

**Files:**

- Create: `src/so101_teleop/so101_teleop/expert_validation/lease.py`
- Create: `src/so101_teleop/so101_teleop/expert_validation/executor_registry.py`
- Create: `src/so101_teleop/so101_teleop/expert_validation/service.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_lease.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_executor_registry.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_service.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/models.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/store.py`

**Interfaces:**

- Consumes: stable `service_session_id`, monotonic clock, store and supervisor.
- Produces: `ValidationLeaseService.acquire()`, `renew()`, `release()`, `expire_due()`, typed `ExecutorRegistry`, immutable manifest validation, plus `ExpertValidationService` methods matching every API operation.

- [ ] **Step 1: 写 lease、registry 与 stale-manifest RED tests。**

```python
def test_browser_disconnect_does_not_release_lease(lease_service):
    lease = lease_service.acquire("browser-a")
    lease_service.browser_disconnected("browser-a")
    assert lease_service.current().lease_id == lease.lease_id

def test_expiry_requests_cancel_and_blocks_new_campaign(lease_service, supervisor):
    lease_service.acquire("browser-a")
    lease_service.expire_due(now_ns=lease_service.expiry_ns + 1)
    assert supervisor.cancel_requests == ["LEASE_EXPIRED"]
    assert lease_service.can_start_campaign("browser-b") is False

def test_v1_registry_exposes_three_explicit_modes(registry):
    capability = registry.require("moveit_expert", "validate_pick_place")
    assert capability.execution_modes == ("SEQUENTIAL", "PARALLEL", "ADAPTIVE")
    assert capability.batch_kinds == ("FIRST_PASS", "FULL_RESTART_RETRY")
    with pytest.raises(UnknownOperation):
        registry.require("act_collect", "collect_demonstration")

def test_parallel_capability_fails_closed_without_upstream_acceptance(registry, probes):
    probes.two_worker_live_acceptance = None
    capability = registry.require("moveit_expert", "validate_pick_place")
    assert capability.mode_availability["PARALLEL"].available is False
    assert capability.mode_availability["PARALLEL"].reason == "PARALLEL_NOT_QUALIFIED"

def test_adaptive_capability_is_independent_from_fixed_modes(registry, probes):
    probes.adaptive_acceptance = None
    capability = registry.require("moveit_expert", "validate_pick_place")
    assert capability.mode_availability["SEQUENTIAL"].available is True
    assert capability.mode_availability["ADAPTIVE"].reason == "ADAPTIVE_NOT_QUALIFIED"

def test_stale_manifest_remains_readable_but_cannot_start(service, stale_manifest):
    assert service.get_manifest(stale_manifest.manifest_id) == stale_manifest
    with pytest.raises(ServiceConflict, match="VALIDATION_MANIFEST_STALE"):
        service.start_campaign(start_command(stale_manifest.manifest_id))
```

再覆盖 renew generation、active release rejection、restart invalidation、new holder inspect/cancel-only 和 stale lease mutation。

- [ ] **Step 2: 运行 RED。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_lease.py \
  src/so101_teleop/test/teleop/test_expert_validation_executor_registry.py \
  src/so101_teleop/test/teleop/test_expert_validation_service.py -q
```

- [ ] **Step 3: 实现 service session 与 lease。**

```python
@dataclass(frozen=True)
class Lease:
    lease_id: str
    service_session_id: str
    generation: int
    expires_monotonic_ns: int

@dataclass(frozen=True)
class LeaseCapabilities:
    duration_s: float
    renewal_margin_s: float

class ValidationLeaseService:
    def acquire(self, service_session_id: str) -> Lease: ...
    def renew(self, service_session_id: str, lease_id: str) -> Lease: ...
    def release(self, service_session_id: str, lease_id: str) -> None: ...

@dataclass(frozen=True)
class ExecutorCapability:
    executor_id: str
    operation_id: str
    request_model: type[BaseModel]
    evidence_schema_id: str
    execution_modes: tuple[Literal["SEQUENTIAL", "PARALLEL", "ADAPTIVE"], ...]
    batch_kinds: tuple[Literal["FIRST_PASS", "FULL_RESTART_RETRY"], ...]
    mode_availability: Mapping[str, ModeAvailability]
    success_contract_id: str

class ExecutorRegistry:
    def register(self, capability: ExecutorCapability) -> None: ...
    def require(self, executor_id: str, operation_id: str) -> ExecutorCapability: ...
```

启动时使旧 generation 全部失效。browser disconnect 不自动释放。lease expiry 只通过
mode-specific owner control 请求 cooperative cancellation；没有 batch cleanup receipt 时仍进入
recovery。新 holder 在 unresolved campaign 期间只能 read/cancel/recover。V1 registry 只注册
`moveit_expert/validate_pick_place`，默认 `SEQUENTIAL`；`PARALLEL` 只有在上游模块、配置、
Broker 镜像、资源探针和双 Worker live acceptance 都可核验时才标为 available。
`ADAPTIVE` 只有在 Runner、`ProductionAdaptivePoolFactory`、production wrapper、cleanup、
frozen config、fault injection、20 点 live 和 W1/W2/W4/W6/W8 performance evidence 都可核验时
才 available；它与 fixed availability 分开判定。W10 作为附加证据展示，不改变 W8 默认；
W16 只标为 contract-supported/live-unqualified。未来
`act_collect` 和 `act_rollout` operation 只能通过新 request model、evidence schema 和 success
contract 显式注册，不能复用 MoveIt 统计。

- [ ] **Step 4: 实现 immutable manifest 与 durable command idempotency。**

manifest generation 将上游完整 20 点 catalog 按 Task 1 规则裁成请求点数，生成 server-owned
`manifest_id`，并把 canonical document 与 SHA256 作为同一 durable transaction 写入 store。
service 提供 `preflight()`，绑定 tagged execution config、manifest/selection、
source/install/config、模型与 mode-specific probe hash；start 重算这些值并校验 receipt 尚未
过期。不一致时只拒绝启动，旧 manifest 仍可查询。
service 对 campaign start/cancel/retry 使用 canonical request SHA256。相同 command ID 与 payload
返回存储结果，不同 payload 返回 `COMMAND_ID_REUSED`；崩溃后无法判定的命令返回
`COMMAND_OUTCOME_UNKNOWN`，禁止换 ID 绕过 reconciliation。

- [ ] **Step 5: 运行 GREEN。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_lease.py \
  src/so101_teleop/test/teleop/test_expert_validation_executor_registry.py \
  src/so101_teleop/test/teleop/test_expert_validation_service.py \
  src/so101_teleop/test/teleop/test_expert_validation_store.py -q
```

- [ ] **Step 6: Commit。**

```zsh
git add src/so101_teleop/so101_teleop/expert_validation/lease.py \
  src/so101_teleop/so101_teleop/expert_validation/executor_registry.py \
  src/so101_teleop/so101_teleop/expert_validation/service.py \
  src/so101_teleop/so101_teleop/expert_validation/models.py \
  src/so101_teleop/so101_teleop/expert_validation/store.py \
  src/so101_teleop/test/teleop/test_expert_validation_lease.py \
  src/so101_teleop/test/teleop/test_expert_validation_executor_registry.py \
  src/so101_teleop/test/teleop/test_expert_validation_service.py
git commit -m "feat: lease expert validation campaigns"
```

### Task 10: 接入上游 artifact manifest 与证据隔离

**Files:**

- Create: `src/so101_teleop/so101_teleop/expert_validation/artifacts.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_artifacts.py`
- Modify: `src/so101_teleop/so101_teleop/task_artifacts.py`
- Modify: `src/so101_teleop/test/teleop/test_task_artifacts.py`

**Interfaces:**

- Consumes: bound fixed batch root or adaptive Runner root, accepted Runner generation references,
  sealed Worker/attempt/recovery/Broker manifests, and upstream artifact references.
- Produces: `ValidationArtifactRegistry.register_manifest()`, `resolve_opaque_id()`,
  `ArtifactView`, and checksum-verified read streams scoped to one campaign/Runner batch/pool
  generation/coordinator batch/Worker/attempt.

- [ ] **Step 1: 写 manifest、隔离与 traversal RED tests。**

```python
def test_artifact_cannot_escape_bound_batch_root(registry, foreign_file):
    with pytest.raises(ArtifactAccessError):
        registry.register_manifest(
            upstream_manifest(file=foreign_file), binding("campaign-1", "batch-1")
        )

def test_worker_artifact_cannot_be_claimed_by_another_attempt(registry):
    artifact = registry.register_manifest(
        worker_manifest(worker_id="worker-1", attempt_id="attempt-1"),
        binding("campaign-1", "batch-1"),
    )[0]
    with pytest.raises(ArtifactAccessError, match="ARTIFACT_IDENTITY_MISMATCH"):
        registry.resolve_opaque_id(
            artifact.artifact_id,
            expected_attempt_id="attempt-2",
        )
```

补测 checksum/media type、absolute path、`..`、symlink、cross-campaign、cross-batch、
cross-Worker、旧 generation、未提交 result、Broker evidence 和 recovery receipt。只有
mode-specific top-level journal 已接受并引用的 sealed manifest 才能注册。

- [ ] **Step 2: 运行 RED。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_artifacts.py \
  src/so101_teleop/test/teleop/test_task_artifacts.py \
  src/so101_demo_py/test/test_parallel_batch_artifacts.py -q
```

- [ ] **Step 3: 实现只读 artifact bridge。**

```python
@dataclass(frozen=True)
class ArtifactView:
    artifact_id: str
    campaign_id: str
    batch_id: str
    worker_id: str | None
    worker_generation: int | None
    attempt_id: str | None
    role: str
    media_type: str
    size_bytes: int
    sha256: str

class ValidationArtifactRegistry:
    def register_manifest(
        self, manifest: SealedArtifactManifest, binding: CampaignBatchBinding
    ) -> tuple[ArtifactView, ...]: ...
    def resolve_opaque_id(self, artifact_id: str) -> VerifiedArtifact: ...
```

registry 从当前 campaign-to-batch binding 推导允许的 batch root，不接受客户端路径。它重新
验证 upstream manifest identity、relative path、regular-file/symlink 边界、size 和 SHA256，再
产生 server-owned opaque ID。task-camera RGB-D、point-cloud、planning/controller/physical、
Worker recovery 和 Broker diagnostics 都保留原始 role 与 identity；Web 不复制文件，也不把
共享 Broker 证据错误归到某个 Worker。现有 `task_artifacts` 只复用安全读取与 media-type
allow-list，不成为第二个结果提交权威。

计数型并发 campaign 使用每个 Worker 的固定 task camera 证据，不要求共享 GNOME/macOS
桌面截图；既有交互 Teleop capture adapter 保持不变并继续由原测试覆盖。

- [ ] **Step 4: 运行 GREEN。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_artifacts.py \
  src/so101_teleop/test/teleop/test_task_artifacts.py \
  src/so101_demo_py/test/test_parallel_batch_artifacts.py -q
```

- [ ] **Step 5: Commit。**

```zsh
git add src/so101_teleop/so101_teleop/expert_validation/artifacts.py \
  src/so101_teleop/test/teleop/test_expert_validation_artifacts.py \
  src/so101_teleop/so101_teleop/task_artifacts.py \
  src/so101_teleop/test/teleop/test_task_artifacts.py
git commit -m "feat: expose parallel validation artifacts"
```

### Task 11: 暴露独立 validation API 与 server entry point

**Files:**

- Create: `src/so101_teleop/so101_teleop/expert_validation/api.py`
- Create: `src/so101_teleop/so101_teleop/expert_validation/main.py`
- Create: `src/so101_teleop/scripts/so101_expert_validation_server.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_api.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_main.py`
- Create: `src/so101_teleop/so101_teleop/expert_validation_openapi.json`
- Create: `src/so101_teleop/web/src/api/expert-validation-schema.d.ts`
- Modify: `src/so101_teleop/CMakeLists.txt`
- Modify: `src/so101_teleop/so101_teleop/api.py`
- Modify: `src/so101_teleop/so101_teleop/openapi_export.py`
- Modify: `src/so101_teleop/test/teleop/test_api.py`
- Modify: `src/so101_teleop/test/teleop/test_openapi_export.py`
- Modify: `src/so101_teleop/web/package.json`

**Interfaces:**

- Consumes: `ExpertValidationService`, installed Web bundle and configured evidence root.
- Produces: all `/expert-validation/*` routes from the spec, `/health`, `/` redirect, disabled `/tasks`, WebSocket events, regular-server unavailable capability, deterministic OpenAPI/TypeScript contracts, and installed executable `so101_expert_validation_server.py`.

- [ ] **Step 1: 写 API RED tests。**

```python
def test_dedicated_root_redirects_and_tasks_are_disabled(client):
    assert client.get("/", follow_redirects=False).headers["location"] == "/expert-validation"
    response = client.post("/tasks/runs", json={})
    assert response.status_code == 503
    assert response.json()["code"] == "VALIDATION_TASKS_DISABLED"

def test_retry_requires_lease_command_and_confirmation(client):
    response = client.post("/expert-validation/campaigns/c1/full-restart-retries", json={
        "service_session_id": "browser-a", "lease_id": "lease-a",
        "command_id": "retry-1", "point_ids": ["sample_05_near_center"],
        "confirmation": "wrong",
    })
    assert response.status_code == 409
    assert response.json()["code"] == "CONFIRMATION_REQUIRED"

def test_parallel_start_requires_matching_preflight_and_capacity(client):
    preflight = client.post("/expert-validation/campaigns/preflight", json={
        "service_session_id": "browser-a", "lease_id": "lease-a",
        "manifest_id": "manifest-20", "execution_mode": "PARALLEL",
        "worker_count": 2, "max_points_per_worker": 10,
    }).json()
    response = client.post("/expert-validation/campaigns", json={
        "service_session_id": "browser-a", "lease_id": "lease-a",
        "command_id": "start-1",
        "manifest_id": "manifest-20", "execution_mode": "PARALLEL",
        "worker_count": 2, "max_points_per_worker": 9,
        "preflight_receipt_id": preflight["receipt_id"],
    })
    assert response.status_code == 409
    assert response.json()["code"] == "PREFLIGHT_REQUEST_MISMATCH"

def test_adaptive_start_rejects_k_and_freezes_ladder(client):
    response = client.post("/expert-validation/campaigns/preflight", json={
        "manifest_id": "manifest-20", "execution_mode": "ADAPTIVE",
        "preferred_worker_count": 8, "fallback_worker_counts": [6, 4, 2, 1],
        "initial_points_per_worker": 3, "yolo_executor_count": 2,
        "max_points_per_worker": 10,
    })
    assert response.status_code == 422

def test_regular_server_reports_validation_unavailable(regular_client):
    assert regular_client.get("/expert-validation/capabilities").json() == {
        "available": False,
        "reason": "VALIDATION_SERVER_REQUIRED",
    }
```

- [ ] **Step 2: 运行 RED。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_api.py \
  src/so101_teleop/test/teleop/test_expert_validation_main.py \
  src/so101_teleop/test/teleop/test_api.py \
  src/so101_teleop/test/teleop/test_openapi_export.py -q
```

- [ ] **Step 3: 实现 app factory 和 artifact route。**

`create_expert_validation_app(service, static_dir)` 只接受 loopback 或 Tailscale CGNAT bind。实现
设计中列出的 14 个 HTTP/WebSocket endpoints，其中 preflight 返回绑定 tagged execution
config、manifest 和 provenance 的短期 receipt；start body 必须逐项匹配。campaign response
返回 Web campaign ID、owner kind/identity、固定 coordinator summary 或 adaptive Runner
status/levels/fallbacks/generation/final points/infra attempts/resource observations。固定模式才
返回四个 qualification flags。artifact route
通过 registry 打开 opaque ID，拒绝 absolute client path、`..`、symlink、跨 campaign、
cross-Worker 和 hash mismatch。WebSocket 只推 journal 已接受的 sequence；reconnect 后客户端先
GET campaign。现有 `create_app()` 只新增只读 unavailable capability route，不获得 supervisor、
lease 或进程控制引用，原 `/tasks` 行为保持不变。

- [ ] **Step 4: 安装 entry point 和 config。**

```cmake
install(
  PROGRAMS scripts/so101_expert_validation_server.py
  DESTINATION lib/${PROJECT_NAME}
)
```

server 启动必须显式给出 absolute non-symlink `SO101_VALIDATION_EVIDENCE_ROOT`；缺失时 fail closed。进程不调用 `rclpy.init()`，不加入 simulation ROS graph。

- [ ] **Step 5: 冻结 validation OpenAPI 和 TypeScript schema。**

`openapi_export.py` 保留现有 `OUTPUT` 用法，并新增精确命令 `--validation OUTPUT`。`package.json` 新增 `generate:api:validation`，内容固定为 `openapi-typescript ../so101_teleop/expert_validation_openapi.json -o src/api/expert-validation-schema.d.ts`。

```zsh
"$VALIDATION_PYTHON" -m so101_teleop.openapi_export --validation \
  src/so101_teleop/so101_teleop/expert_validation_openapi.json
validation_web run generate:api:validation
```

- [ ] **Step 6: 运行 GREEN 和 OpenAPI readback。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_api.py \
  src/so101_teleop/test/teleop/test_expert_validation_main.py \
  src/so101_teleop/test/teleop/test_api.py \
  src/so101_teleop/test/teleop/test_openapi_export.py -q
"$VALIDATION_PYTHON" -m so101_teleop.openapi_export --validation \
  "$VALIDATION_EVIDENCE/expert-validation-openapi.json"
diff -u src/so101_teleop/so101_teleop/expert_validation_openapi.json \
  "$VALIDATION_EVIDENCE/expert-validation-openapi.json"
validation_web run generate:api:validation
git diff --exit-code \
  src/so101_teleop/web/src/api/expert-validation-schema.d.ts
```

- [ ] **Step 7: Commit。**

```zsh
git add src/so101_teleop/so101_teleop/expert_validation/api.py \
  src/so101_teleop/so101_teleop/expert_validation/main.py \
  src/so101_teleop/scripts/so101_expert_validation_server.py \
  src/so101_teleop/test/teleop/test_expert_validation_api.py \
  src/so101_teleop/test/teleop/test_expert_validation_main.py \
  src/so101_teleop/so101_teleop/expert_validation_openapi.json \
  src/so101_teleop/web/src/api/expert-validation-schema.d.ts \
  src/so101_teleop/web/package.json \
  src/so101_teleop/so101_teleop/api.py \
  src/so101_teleop/so101_teleop/openapi_export.py \
  src/so101_teleop/test/teleop/test_api.py \
  src/so101_teleop/test/teleop/test_openapi_export.py \
  src/so101_teleop/CMakeLists.txt
git commit -m "feat: expose expert validation service"
```

## 批次 C：Web 页面

### Task 12: 建立 Web API types、client 和恢复 store

**Files:**

- Create: `src/so101_teleop/web/src/api/expert-validation-types.ts`
- Create: `src/so101_teleop/web/src/api/expert-validation-client.ts`
- Create: `src/so101_teleop/web/src/api/expert-validation-client.test.ts`
- Create: `src/so101_teleop/web/src/state/expert-validation-store.ts`
- Create: `src/so101_teleop/web/src/state/expert-validation-store.test.ts`

**Interfaces:**

- Consumes: generated OpenAPI schema and command ID helper.
- Produces: `ExpertValidationClient` and `ExpertValidationStore` with one authoritative campaign projection.

- [ ] **Step 1: 写 reconnect 与 command body RED tests。**

```typescript
test("reconnect fetches campaign before applying later events", async () => {
  const client = fakeClient({ campaignSequence: 8, websocketSequence: 10 });
  const store = new ExpertValidationStore(client);
  await store.reconnect("campaign-1");
  expect(client.calls).toEqual(["GET campaign-1", "OPEN events after=8"]);
  expect(store.state.sequence).toBe(10);
});

test("retry sends exact confirmation and selected failed ids", async () => {
  await client.retry(
    "campaign-1", ["sample_05_near_center"], lease,
    "CONFIRM FULL_RESTART RETRIES",
  );
  expect(lastBody()).toMatchObject({
    point_ids: ["sample_05_near_center"],
    confirmation: "CONFIRM FULL_RESTART RETRIES",
  });
});

test("parallel start preserves admitted mode N and K", async () => {
  const receipt = await client.preflight("manifest-20", "PARALLEL", 2, 10);
  await client.startCampaign({
    manifest_id: "manifest-20", execution_mode: "PARALLEL",
    worker_count: 2, max_points_per_worker: 10,
    preflight_receipt_id: receipt.receipt_id,
  }, lease);
  expect(lastBody()).toMatchObject({
    execution_mode: "PARALLEL", worker_count: 2, max_points_per_worker: 10,
  });
});

test("adaptive start preserves ladder and never sends K", async () => {
  const request = adaptiveRequest({ preferred: 8, fallback: [6, 4, 2, 1] });
  const receipt = await client.preflight(request);
  await client.startCampaign({ ...request, preflight_receipt_id: receipt.receipt_id }, lease);
  expect(lastBody().max_points_per_worker).toBeUndefined();
  expect(lastBody().fallback_worker_counts).toEqual([6, 4, 2, 1]);
  expect(lastBody().yolo_executor_count).toBe(2);
});
```

- [ ] **Step 2: 运行 RED。**

```zsh
validation_web run test \
  src/api/expert-validation-client.test.ts \
  src/state/expert-validation-store.test.ts
```

- [ ] **Step 3: 实现 client 与 store。**

`expert-validation-types.ts` 只从生成的 `expert-validation-schema.d.ts` 提取 aliases，禁止再
手写第二份 wire schema。生成契约必须闭合列出 `ExecutionMode`、mode availability、tagged
fixed/adaptive config 与 preflight、manifest geometry、fixed/adaptive point states、attempt
states、Worker slot/generation/state/current point/K/heartbeat/deadline/recovery/quarantine、Broker
health、fixed 四 flags、adaptive Runner status/levels/fallbacks/generations/observations、
statistics、lease、artifact 和 campaign/upstream identity。client
对非 2xx machine-readable error 保留 `code`；store 丢弃 `sequence <= current` 的 hint，并在
sequence gap 时重新 GET campaign。它只投影固定 coordinator 或 adaptive Runner 返回值，
不从 Web events 推导新的终态、fallback 或 qualification。

- [ ] **Step 4: 运行 GREEN。**

```zsh
validation_web run test \
  src/api/expert-validation-client.test.ts \
  src/state/expert-validation-store.test.ts
```

- [ ] **Step 5: Commit。**

```zsh
git add src/so101_teleop/web/src/api/expert-validation-types.ts \
  src/so101_teleop/web/src/api/expert-validation-client.ts \
  src/so101_teleop/web/src/api/expert-validation-client.test.ts \
  src/so101_teleop/web/src/state/expert-validation-store.ts \
  src/so101_teleop/web/src/state/expert-validation-store.test.ts
git commit -m "feat: add expert validation web client"
```

### Task 13: 实现精确 SVG 俯视图

**Files:**

- Create: `src/so101_teleop/web/src/components/expert-validation/top-view-map.tsx`
- Create: `src/so101_teleop/web/src/components/expert-validation/top-view-map.test.tsx`
- Create: `src/so101_teleop/web/src/components/expert-validation/projection.ts`
- Create: `src/so101_teleop/web/src/components/expert-validation/projection.test.ts`
- Create: `src/so101_teleop/web/src/fixtures/top_view_projection_v1.json`

**Interfaces:**

- Consumes: server manifest geometry, point projection/status and selected point ID.
- Produces: `<TopViewMap manifest campaign selectedPointId onSelect />` and a TypeScript projection matching Python golden values.

- [ ] **Step 1: 写 exact-coordinate 与 style RED tests。**

两个 test 文件首行写 `// @vitest-environment jsdom`，沿用 `src/setup-tests.ts` 的 cleanup。断言使用标准 DOM property/attribute，不新增 jest-dom 依赖。

```typescript
test("matches Python projection fixture", () => {
  const point = projectXY(fixture.projection, 0.02, -0.28);
  expect(point).toEqual(fixture.p01_px);
});

test.each([
  ["ELIGIBLE_UNRUN", "blue"], ["LEASED", "blue"], ["EXECUTING", "blue"],
  ["INFRA_INTERRUPTED_REQUEUEABLE", "blue"],
  ["PASSED", "green"], ["FAILED", "red"], ["INDETERMINATE", "red"],
  ["TERMINAL_UNRUN", "red"], ["INVALID_BLOCKED", "red"],
  ["INFRA_FAILED_REMAINDER", "red"],
])("renders %s with %s semantic style", (state, color) => {
  renderMap(pointWithState(state));
  expect(screen.getByLabelText(/P01/).getAttribute("data-color")).toBe(color);
});
```

- [ ] **Step 2: 运行 RED。**

```zsh
validation_web run test src/components/expert-validation/projection.test.ts \
  src/components/expert-validation/top-view-map.test.tsx
```

- [ ] **Step 3: 实现 SVG。**

使用一个 viewBox 和单一 equal-scale transform。绘制 table/grid、方形 base、base origin、
target center、target region、target tolerance 虚线圆、P01 cup footprint 虚线圆和全部等半径
点位。active Worker point 只加粗蓝色 stroke；selection 只增加外 focus ring。每个 point 是可
键盘选择的 `<button>` 等价 SVG 元素，并提供状态、Worker ID、阶段和失败原因的完整 aria label。

- [ ] **Step 4: 同 Python golden fixture 做双向 readback。**

```zsh
validation_web run test src/components/expert-validation/projection.test.ts \
  src/components/expert-validation/top-view-map.test.tsx
diff -u \
  src/so101_teleop/config/expert_validation/top_view_projection_v1.json \
  src/so101_teleop/web/src/fixtures/top_view_projection_v1.json
```

- [ ] **Step 5: Commit。**

```zsh
git add src/so101_teleop/web/src/components/expert-validation \
  src/so101_teleop/web/src/fixtures/top_view_projection_v1.json
git commit -m "feat: render expert validation top view"
```

### Task 14: 实现 campaign 页面、证据和重试操作

**Files:**

- Create: `src/so101_teleop/web/src/expert-validation-app.tsx`
- Create: `src/so101_teleop/web/src/expert-validation-app.test.tsx`
- Create: `src/so101_teleop/web/src/components/expert-validation/campaign-setup.tsx`
- Create: `src/so101_teleop/web/src/components/expert-validation/campaign-progress.tsx`
- Create: `src/so101_teleop/web/src/components/expert-validation/point-evidence.tsx`
- Create: `src/so101_teleop/web/src/components/expert-validation/retry-panel.tsx`
- Create: `src/so101_teleop/web/src/components/expert-validation/components.test.tsx`
- Modify: `src/so101_teleop/web/src/main.tsx`

**Interfaces:**

- Consumes: Tasks 12-13 client/store/map and existing UI primitives.
- Produces: `/expert-validation` SPA route with setup, progress, map selection, artifact preview and confirmed serial retry.

- [ ] **Step 1: 写 operator-flow RED tests。**

所有 `.tsx` test 文件首行写 `// @vitest-environment jsdom`，并继续使用原生 `HTMLButtonElement.disabled` / `HTMLInputElement.disabled` 断言。

```typescript
test("changing count invalidates generated preview", async () => {
  render(<ExpertValidationApp api={fakeApi()} />);
  await user.click(screen.getByRole("button", { name: "Generate points" }));
  await user.clear(screen.getByLabelText("Final point count"));
  await user.type(screen.getByLabelText("Final point count"), "12");
  const start = screen.getByRole("button", { name: "Start validation" });
  expect((start as HTMLButtonElement).disabled).toBe(true);
});

test("only valid failures are retry eligible", async () => {
  renderCampaign(points("PASSED", "FAILED", "INDETERMINATE", "UNRUN"));
  expect((screen.getByLabelText("Retry P02") as HTMLInputElement).disabled).toBe(false);
  expect((screen.getByLabelText("Retry P01") as HTMLInputElement).disabled).toBe(true);
  expect((screen.getByLabelText("Retry P03") as HTMLInputElement).disabled).toBe(true);
  expect((screen.getByLabelText("Retry P04") as HTMLInputElement).disabled).toBe(true);
});

test("parallel setup shows capacity admission and worker lanes", async () => {
  render(<ExpertValidationApp api={fakeParallelApi()} />);
  await user.selectOptions(screen.getByLabelText("Execution mode"), "PARALLEL");
  await user.selectOptions(screen.getByLabelText("Worker count"), "2");
  expect(screen.getByText("Capacity 20 / 20")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Check resources" }));
  expect(screen.getByText("Parallel admission passed")).toBeTruthy();
  expect(screen.getByLabelText("Worker worker-1")).toBeTruthy();
  expect(screen.getByLabelText("Worker worker-2")).toBeTruthy();
});

test("adaptive setup shows fallback timeline and observational resources", async () => {
  render(<ExpertValidationApp api={fakeAdaptiveApi({ levels: [8, 6] })} />);
  await user.selectOptions(screen.getByLabelText("Execution mode"), "ADAPTIVE");
  expect(screen.queryByLabelText("Max points per worker")).toBeNull();
  expect(screen.getByText("W8 -> W6 -> W4 -> W2 -> W1")).toBeTruthy();
  expect(screen.getByText("Resource observations only")).toBeTruthy();
  expect(screen.getByText("W8 -> W6: WORKER_START_FAILED")).toBeTruthy();
});
```

再覆盖 count 3/21、只读 seed、顺序默认、任一 mode-specific input 改动使 preflight 失效、
fixed N×K 不足、adaptive K rejection、ladder validation、
parallel unavailable、lease required、map/list/Worker shared selection、Broker degraded、并发 active
points、separate first-pass/retry statistics、recovery lockout、inline image media types、opaque
download URL 和 exact confirmation。

- [ ] **Step 2: 运行 RED。**

```zsh
validation_web run test src/expert-validation-app.test.tsx \
  src/components/expert-validation/components.test.tsx
```

- [ ] **Step 3: 实现页面布局。**

setup 显示执行模式；固定模式显示 Worker 数、K、`N × K` capacity、preflight expiry 和资源
拒绝原因；adaptive 显示 preferred/fallback、initial affinity、startup timeout、infra attempt
limit，并将资源指标标为只读 observation。默认顺序模式。左侧固定 `TopViewMap`，右侧显示
campaign/upstream identity、execution mode、mode-specific config、fixed coordinator state 或
adaptive Runner state/current/final level/levels used/fallback timeline/generation/remaining/load/
elapsed、evaluation/execution coverage、固定四 flags 或 adaptive terminal status、qualified first-pass
fraction、Broker health、first shared failure 和 lifecycle。Worker lanes 显示 generation、state、
current point、K used/remaining、heartbeat/deadline、recovery 与 quarantine。selected point panel 按
时间显示 first pass 与 retry attempts；支持 task RGB-D/point-cloud preview inline，PLY/JSON/log
下载。

- [ ] **Step 4: 实现 lease 与 retry。**

页面加载取得 stable service session，再显式 acquire lease 并按 capabilities 周期 renew。browser
disconnect 不发送 release。start 前用当前 manifest/tagged execution config 取得 preflight receipt；任何输入
变化或 receipt 过期都禁用 start。retry modal 要求用户输入
`CONFIRM FULL_RESTART RETRIES`，只发送当前 campaign 中 authoritative first-pass status 为
`FAILED` 的 canonical IDs；adaptive 只有 `COMPLETED_WITH_FAILURES` 且 cleanup complete 才开放
该操作，`INFRA_INTERRUPTED`/attempt-level `INDETERMINATE`/`INFRA_FAILED` 不可进入 retry。
unreachable 已属于 `FAILED` reason，不使用第二种状态名。

- [ ] **Step 5: 运行 GREEN。**

```zsh
validation_web run test src/expert-validation-app.test.tsx \
  src/components/expert-validation/components.test.tsx \
  src/components/expert-validation/top-view-map.test.tsx
```

- [ ] **Step 6: Commit。**

```zsh
git add src/so101_teleop/web/src/expert-validation-app.tsx \
  src/so101_teleop/web/src/expert-validation-app.test.tsx \
  src/so101_teleop/web/src/components/expert-validation \
  src/so101_teleop/web/src/main.tsx
git commit -m "feat: add expert validation web page"
```

### Task 15: 完成 browser、真实进程与 package integration gates

**Files:**

- Create: `src/so101_teleop/web/e2e/expert-validation.spec.ts`
- Create: `src/so101_teleop/test/test_expert_validation_package_layout.py`
- Modify: `src/so101_teleop/CMakeLists.txt`
- Modify: `src/so101_teleop/test/test_package_layout.py`

**Interfaces:**

- Consumes: installed server, generated Web bundle, fake API fixtures, Task 5 process-tree helper and Task 7 durable store wiring.
- Produces: deterministic browser acceptance, real OS process restart/cleanup evidence and installed-package checks without starting MuJoCo.

- [ ] **Step 1: 写 Playwright RED scenario。**

```typescript
test("restores an adaptive campaign and retries a business-failed point", async ({ page }) => {
  const fake = await installFakeRunner(page, adaptiveCampaignWithFailedP09());
  await page.goto("/expert-validation");
  await expect(page.getByLabel("P09 FAILED")).toBeVisible();
  await expect(page.getByLabel("Worker worker-1")).toBeVisible();
  await expect(page.getByLabel("Worker worker-2")).toBeVisible();
  await page.getByLabel("Retry P09").check();
  await page.getByRole("button", { name: "Retry selected with FULL_RESTART" }).click();
  await page.getByLabel("Confirmation").fill("CONFIRM FULL_RESTART RETRIES");
  await page.getByRole("button", { name: "Confirm retry" }).click();
  expect(fake.lastRetryBody.point_ids).toEqual(["sample_05_near_center"]);
  await expect(page.getByText("FULL_RESTART attempt 2")).toBeVisible();
});
```

fake Runner scenario 必须给出 W8 -> W6 fallback、交错 Worker events、Broker pause/recovery、
attempt-level `INDETERMINATE`、requeued point、sequence gap 后 HTTP resync、
`COMPLETED_WITH_FAILURES`，以及 retry batch N=1/K=1；另保留 fixed coordinator compatibility
fixture。它只验证浏览器投影，不模拟
MuJoCo、ROS 或 Worker 进程。

- [ ] **Step 2: 运行 RED。**

```zsh
validation_web run build
validation_web run test:e2e -- e2e/expert-validation.spec.ts
```

- [ ] **Step 3: 完成 build/install checks。**

package layout 必须证明 catalog adapter、projection fixture、server executable 和 SPA route 均
安装，并且上游 `so101_parallel_batch`、adaptive Runner/production wrapper/cleanup、configs 和
catalog 可由 installed overlay 解析。
`so101_demo_py/setup.py` 已用 `find_packages(where="src")` 自动安装新增 modules；新增 coordinator
console script 属于上游实施计划，本计划不再复制。CMake 逐个注册 Tasks 1-11 新增的 Python
test files，其中必须包括 `test_expert_validation_process_owner_integration.py`。layout test 对注册
集合做 readback，避免本地 pytest 通过而 colcon gate 漏测。

- [ ] **Step 4: 运行全部 Web gate。**

```zsh
validation_web run test
validation_web run build
validation_web run test:e2e -- e2e/expert-validation.spec.ts
```

- [ ] **Step 5: 运行 Python package gates。**

```zsh
validation_pytest \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner_integration.py -q \
  --junitxml="$VALIDATION_EVIDENCE/process-owner-integration.xml"
validation_pytest src/so101_demo_py/test -q \
  --junitxml="$VALIDATION_EVIDENCE/so101_demo_py.xml"
validation_pytest src/so101_teleop/test -q \
  --junitxml="$VALIDATION_EVIDENCE/so101_teleop.xml"
```

真实进程 integration file 在 macOS 可跳过 Linux `/proc` 专属 cases，但在 Task 16 的 ai-station gate 必须收集并执行非零 tests，不能全部 skip。两个 package gate 的收集数也都必须大于零、exit 0、errors/failures 为零；不得收集 `benchmark_test/`。

- [ ] **Step 6: Commit。**

```zsh
git add src/so101_teleop/web/e2e/expert-validation.spec.ts \
  src/so101_teleop/CMakeLists.txt \
  src/so101_teleop/test/test_expert_validation_package_layout.py \
  src/so101_teleop/test/test_package_layout.py
git commit -m "test: cover expert validation end to end"
```

## 批次 D：ai-station build 与 live acceptance

### Task 16: 在 ai-station 做隔离 build、固定模式 smoke 和 20 点 adaptive 首轮

**Files:**

- Create: `docs/experiments/so101-moveit-expert-validation-web-experiment-ledger.md`
- Modify: the same ledger after every experiment and checkpoint

**Interfaces:**

- Consumes: clean implementation commit, one durable evidence root, no active SO-101 stack.
- Produces: installed-runtime provenance, package results, fresh campaign manifests, per-point evidence and process cleanup receipts.

- [ ] **Step 1: 冻结 PLANNED entries。**

账本先写 `EXP-001` package gate、`EXP-002` 4-point sequential smoke、`EXP-003` 相同
selection 的 4-point parallel smoke、`EXP-004` 20-point adaptive first pass。每条分别写
commit、overlay、coordinator/Runner/wrapper/cleanup/config/catalog/Broker image hashes、固定
N/K 或 adaptive ladder/affinity/timeout/infra-attempt limit/C2、资源 observation、
成功/失败/indeterminate/invalid 判据和唯一变量。不要复用任何正在运行或未登记的 checkout、
tmux 或进程，也不复用本计划编写时观察到的 adaptive tmux/worktree。

- [ ] **Step 2: 创建 NVMe scratch 并 build。**

```zsh
mkdir -p "$VALIDATION_EVIDENCE/scratch"
BUILD_SCRATCH=$(mktemp -d "$VALIDATION_EVIDENCE/scratch/build-XXXXXXXX")
mkdir "$BUILD_SCRATCH/tmp"
export TMPDIR="$BUILD_SCRATCH/tmp" TMP="$TMPDIR" TEMP="$TMPDIR"
"$VALIDATION_PYTHON" -c 'import os,tempfile; from pathlib import Path; assert Path(tempfile.gettempdir()).resolve()==Path(os.environ["TMPDIR"]).resolve()'
colcon --log-base "$VALIDATION_EVIDENCE/colcon-log" build \
  --base-paths "$PWD/src" \
  --build-base "$VALIDATION_EVIDENCE/build" \
  --install-base "$VALIDATION_EVIDENCE/install" \
  --packages-select so101_demo_py so101_teleop \
  --symlink-install --event-handlers console_direct+
source "$VALIDATION_EVIDENCE/install/setup.zsh"
ros2 pkg prefix so101_demo_py
ros2 pkg prefix so101_teleop
ros2 pkg executables so101_teleop | rg so101_expert_validation_server
ros2 run so101_demo_py so101_parallel_batch --help | rg -- '--adaptive-workers'
ros2 pkg executables so101_demo_py | rg 'so101_parallel_batch_cleanup'
test -x scripts/run_so101_adaptive_batch.zsh
rg '^yolo_executor_count: 2$' src/so101_demo_py/config/mujoco/parallel_adaptive_workers_v1.yaml
```

- [ ] **Step 3: 运行 ai-station package gate。**

```zsh
TEST_SCRATCH=$(mktemp -d "$VALIDATION_EVIDENCE/scratch/colcon-test-XXXXXXXX")
mkdir "$TEST_SCRATCH/tmp"
export TMPDIR="$TEST_SCRATCH/tmp" TMP="$TMPDIR" TEMP="$TMPDIR"
"$VALIDATION_PYTHON" -c 'import os,tempfile; from pathlib import Path; assert Path(tempfile.gettempdir()).resolve()==Path(os.environ["TMPDIR"]).resolve()'
validation_pytest \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner_integration.py -q \
  --junitxml="$VALIDATION_EVIDENCE/process-owner-integration-linux.xml"
colcon --log-base "$VALIDATION_EVIDENCE/colcon-test-log" test \
  --base-paths "$PWD/src" \
  --build-base "$VALIDATION_EVIDENCE/build" \
  --test-result-base "$VALIDATION_EVIDENCE/test-results" \
  --packages-select so101_demo_py so101_teleop \
  --event-handlers console_direct+
colcon test-result --test-result-base "$VALIDATION_EVIDENCE/test-results" --verbose
"$VALIDATION_PYTHON" - <<'PY'
import os
from pathlib import Path
import xml.etree.ElementTree as ET

root = Path(os.environ["VALIDATION_EVIDENCE"])
integration_cases = ET.parse(root / "process-owner-integration-linux.xml").getroot().findall(".//testcase")
assert integration_cases, "real process integration collected zero tests"
assert any(case.find("skipped") is None for case in integration_cases), "all real process integration tests skipped"
for package in ("so101_demo_py", "so101_teleop"):
    files = list((root / "test-results" / package).rglob("*.xml"))
    cases = [case for path in files for case in ET.parse(path).getroot().findall(".//testcase")]
    assert cases, f"{package} collected zero tests"
    assert not [case for case in cases if case.find("failure") is not None or case.find("error") is not None]
PY
```

- [ ] **Step 4: 启动独立 validation server。**

先按 `so101-dev` 清点进程、ROS graph 和 tmux，要求无 pre-existing SO-101 application stack。server 用明确 tmux 持有，只绑定 loopback 或 Tailscale 地址：

```zsh
export SO101_VALIDATION_EVIDENCE_ROOT="$VALIDATION_EVIDENCE/runtime"
export SO101_TELEOP_BIND=127.0.0.1
export SO101_TELEOP_PORT=8010
ros2 run so101_teleop so101_expert_validation_server.py
```

- [ ] **Step 5: 通过页面执行 4 点 smoke。**

生成 frozen catalog 的 `total_points=4` selection，核对只读 `seed=20260911` 和 selection
hash，取得 lease，选择 `SEQUENTIAL, N=1, K=4` 并通过 preflight 后启动 first pass。必须从
页面看到 coordinator/Worker/point 进度，并逐点核对 fresh task-camera RGB-D、输入 stamp、
MoveIt plan/execute、controller/joint/TF、MuJoCo lift/transport/release/final pose/contact、Planning
Scene attached/world、Worker recovery 和 batch cleanup。任何 provenance/reset 污染将该 attempt
记为 `INVALID`；point 终态仍由 coordinator 裁决，不得由 Web 混算。

- [ ] **Step 6: 对相同 4 点执行并发 smoke。**

复用同一 immutable point selection，创建新的 campaign，选择 `PARALLEL, N=2, K=2` 并通过
resource admission。核对两个独立 Worker 的 ROS domain、simulation session、process tree、
runtime/evidence root、generation、dynamic point lease 和 K debit，以及共享 Broker 的 request
identity/generation/fairness。任一 cross-Worker pose、artifact 或 ownership 泄漏都判为并发门失败；
不得降级为顺序重跑后声称通过。

- [ ] **Step 7: 通过页面执行精确 20 点 adaptive 首轮。**

生成 `ai_station_baseline_v1` manifest，逐项核对 20 点坐标、catalog/selection hash，选择
`ADAPTIVE`，preferred W8、fallback W6/W4/W2/W1、`initial_points_per_worker=3`、
`worker_start_timeout_s=120`、`max_infra_attempts_per_point=5`、`yolo_executor_count=2`，确认请求
不含 K 或 fixed-mode live-headroom 字段后重新 preflight
并通过 production wrapper 启动。资源 snapshot 只记录为 observation，不作为启动门或 tier
选择器。保存 Runner status、initial/final Worker count、levels used、fallback transition/reason、
pool generations、每点 final state、attempt-level infra history、Worker/Broker recovery、elapsed、
resource observations、batch cleanup 和每点 artifact IDs。不得将 retry 或固定 smoke 结果合并
进首轮统计；也不得由 Web 重新推导固定模式的四个 qualification flags。

- [ ] **Step 8: 写 checkpoint。**

账本记录 retained root、scratch deletion candidates、无 archived run、owned process cleanup、剩余风险和下一条精确命令。未获用户授权不删除任何证据。

### Task 17: 验证 adaptive 业务失败点 FULL_RESTART、视觉结果和最终边界

**Files:**

- Modify: `docs/experiments/so101-moveit-expert-validation-web-experiment-ledger.md`

**Interfaces:**

- Consumes: Task 16 的 fresh terminal campaign。
- Produces: 至少一个 eligible failure 的页面重试证据，或明确的 `LIVE_RETRY_NOT_APPLICABLE_ALL_SUCCEEDED`，以及最终交付报告。

- [ ] **Step 1: 冻结 retry experiment。**

若 20 点 adaptive 首轮以 `COMPLETED_WITH_FAILURES` 安全结束、cleanup complete 且有业务
`FAILED`，为最早 eligible point 建 `EXP-005`，`batch_kind:
FULL_RESTART_RETRY`，记录 canonical point ID、display ID、首坏边界和首轮 batch ID。unreachable
是 `FAILED` 的 reason，不另设状态。若全部有效点成功，不制造失败，记录
`LIVE_RETRY_NOT_APPLICABLE_ALL_SUCCEEDED`；同时把 Task 16 的 Linux real-process integration
JUnit、store-reopen reconciliation 和 cleanup-before-next-start assertions 登记为 restart/cleanup
证据，再跳到 Step 4。若 adaptive 首轮是 `INFRA_FAILED`，禁止 retry，先记录 Runner/fallback/
cleanup 诊断并结束验收。fake Runner/coordinator 或 Playwright 不能替代这组证据。

- [ ] **Step 2: 从页面执行 retry。**

选中点位，输入 `CONFIRM FULL_RESTART RETRIES`。证明这不是 adaptive 自动 infra rerun，而是
新 fixed `SEQUENTIAL` coordinator batch，固定 N=1/K=1 且不带 `--adaptive-workers`；
batch/attempt ID、coordinator epoch、simulation session、ROS domain、
coordinator/Worker PGID 和 evidence child 均与首轮不同。开始下一 retry 前，前一 batch 的
cleanup receipt 必须落盘，registered descendants/ROS graph 已消失，Web 才推进 durable queue。

- [ ] **Step 3: 核对 retry 不改首轮统计。**

GET campaign readback 必须保持首轮 numerator、denominator 和 point receipt 不变；retry 在独立 attempt list 中。cleanup ambiguity、held cup 或 stale receipt 必须进入 `NEEDS_OPERATOR_RECOVERY`，不得自动 signal 或启动下一 stack。

- [ ] **Step 4: 做 fresh task-camera visual acceptance。**

从 Web artifact panel 逐项打开选中 point 的 fresh task-camera before/after RGB-D 与
point-cloud preview，核对 robot pose、gripper、cup initial/final pose、穿透/掉落、target
tolerance 和 Planning Scene 一致性。必要时可用 `$gui-capture` 补充顺序 smoke 的交互桌面
诊断，但共享桌面截图不是并发 qualification 证据，也不能替代数值与 action/physics evidence。

- [ ] **Step 5: 最终 readback。**

```zsh
git rev-parse HEAD
git status --short
ros2 pkg prefix so101_demo_py
ros2 pkg prefix so101_teleop
curl --fail http://127.0.0.1:8010/health
ps -eo pid,pgid,cmd | rg '(move_group|mujoco|so101_expert_validation|so101_parallel_batch)' || true
```

停止 validation server 前先确认没有 active attempt，并保存 server 自身退出与清理记录。不得
停止任何用户任务或其他未登记进程。

- [ ] **Step 6: 写最终账本 checkpoint。**

报告 manifest ID/hash、commit/overlay/runtime provenance、4 点 fixed smoke、20 点 adaptive
首轮、levels/fallbacks/generations、retry、first-bad-boundary、artifact hashes、ROS/process
cleanup、retained/archived/deletion candidates 和未解决风险。明确区分实现完成、package
test、仿真 runtime 与 ACT 未实现边界。

- [ ] **Step 7: Commit 实验账本。**

```zsh
git add docs/experiments/so101-moveit-expert-validation-web-experiment-ledger.md
git commit -m "docs: record expert validation acceptance"
```

## 最终验收清单

- [ ] `ai_station_baseline_v1` 精确复现 20 点；`geometry_v2` 仍为独立 35 mm profile。
- [ ] Python 和 React 对 table/base/target/P01/20 点投影、半径与颜色的 golden tests 一致。
- [ ] fixed coordinator 与 adaptive Runner framed journal 的 manifest/event 顺序通过 crash-window tests；Web snapshot 可删除重建。
- [ ] API、journal、store 和 retry command 只使用 canonical point ID；`P01` 至 `P20` 只用于展示。
- [ ] 三模式 start 都使用未过期 `CampaignPreflightReceipt`；tagged config、catalog/selection、
  source/install/config、model/Broker 与 mode-specific probes 全部匹配。
- [ ] `SEQUENTIAL` 走 coordinator N=1；`PARALLEL` 走 N=2..3；不存在 Web 自有 legacy
  attached-stack 路径或静默降级。
- [ ] `ADAPTIVE` 只通过 production wrapper 启动 Runner，默认使用 W8/W6/W4/W2/W1、C2 和
  initial affinity 而非 K；显式 preferred tier 受 W1–W16 契约约束。资源指标只观察，真实
  infra failure 才触发降级。
- [ ] fixed coordinator 独占固定 point lease/K；Runner 独占 adaptive generations/fallback/final
  results；Web 只拥有 fixed coordinator 或 exact wrapper identity，并且从不 signal Runner、
  Worker 或 Broker groups。
- [ ] Linux real-process integration gate 实际执行非零 tests，并通过 descendant、barrier、ack、reopen 和 serial cleanup cases。
- [ ] 所有 exit path 产生 Worker recovery 与 batch cleanup receipt，或进入 `NEEDS_OPERATOR_RECOVERY`。
- [ ] command idempotency、lease restart/expiry、browser disconnect 和 singleton lock 均通过测试。
- [ ] terminal campaign 没有 active lease/stage；fixed points 归入
  `PASSED | FAILED | INDETERMINATE | UNRUN`，adaptive final points 和 attempt history 保持 Runner
  语义；unreachable、infra interrupted 和 business failed 的统计不混淆。
- [ ] `/expert-validation` 页面支持 mode-specific config/preflight、生成、开始、并发
  Worker/Broker 进度、adaptive levels/fallbacks/generations、选择、证据和 confirmed retry；
  `/tasks` 在 dedicated server 上禁用。
- [ ] Web tests、Playwright、两个 Python package gates 均收集非零测试且无新增 failure/error。
- [ ] ai-station 使用 task-owned overlay、fresh source、独立 ROS domain/GZ partition 和 registered durable evidence root。
- [ ] 4 点 N=1/K=4 顺序 smoke、同一 selection 的 N=2/K=2 固定并发 smoke，以及 20 点
  adaptive W8->W6->W4->W2->W1 首轮都有 fresh task-camera/MoveIt/controller/pose/contact/
  generation/cleanup 证据；共享
  GUI 截图不是并发 qualification 前提。
- [ ] upstream W8 startup->W6、W8 mid-run->W6、20 点 adaptive run 和 W1/W2/W4/W6/W8
  performance gates 已验收；W10 附加样本和 W16 未现场验收边界显示正确；Web 只复用，不另造
  fault-injection 语义。
- [ ] 人工 `FULL_RESTART` 只接受安全完成首轮的 business `FAILED`，固定 N=1/K=1；adaptive
  infra rerun、`INFRA_INTERRUPTED` 和 `INFRA_FAILED` 不进入 retry queue。
- [ ] 每个 generation/Worker/attempt/recovery/Broker artifact 都通过 bound manifest 和 opaque ID 隔离；无
  duplicate coordinator、未知 descendants 或失控后台进程；未触碰用户已有 ai-station 改动、
  tmux 任务或其他 worktree。
- [ ] retained、archived 和 deletion candidates 已分类，且没有未经授权删除证据。

## 执行方式

本轮锁定 **Inline Execution**：ai-station Codex 在当前 session 使用
`superpowers:executing-plans`，不创建 subagent，按批次 A、B、C、D 执行，并在每批结束时完成
计划要求的测试、账本更新和 checkpoint 后继续。只有需要用户扩大授权、真实硬件动作或处理不明
所有权资源时才停止并请求用户输入。
