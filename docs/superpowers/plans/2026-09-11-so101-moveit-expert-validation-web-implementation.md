# SO-101 MoveIt expert validation Web implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Teleop Web 中交付一个独立的 MoveIt 专家随机点位验证页面，支持 4 至 20 个确定性点位、实时俯视状态、证据查看，以及失败点的串行 `FULL_RESTART` 重试。

**Architecture:** 长生命周期的 validation server 位于所有 MuJoCo stack 之外。它持久化 campaign、lease、命令幂等、进程所有权与安全回执，并通过 supervisor-owned process broker 启动 stack、batch 和逐点 worker。现有 `so101_demo_py` batch 保留任务状态机所有权，但通过新端口上报持久进度、检查取消、安全关栈，不再直接拥有验证模式下的子进程。

**Tech Stack:** Python 3.12、ROS 2 Jazzy、MuJoCo、MoveIt 2、FastAPI、Pydantic、SQLite、React、TypeScript、SVG、Bun、Vitest、Playwright。

**Spec:** [SO-101 MoveIt expert random-position validation Web design](../specs/2026-09-11-so101-moveit-expert-validation-web-design.md)。执行者必须先完整阅读设计和本计划；设计是行为契约，本计划只拆解实现顺序。

## Global Constraints

- 本功能仅允许 MuJoCo 仿真，不得发送真实机械臂命令。实体机械臂继续保持 fail-closed 或 plan-only。
- `total_points` 是最终点位数，首版只接受 `4 <= total_points <= 20`，并始终包含四个固定锚点。
- API、event log、store、process ownership 和 retry command 一律使用 manifest 中不可变的 canonical `point.id`，例如 `task_start` 或 `sample_05_near_center`。`P01` 至 `P20` 只作为 `display_id` 出现在页面、图例和无障碍标签中；转换只能通过当前 manifest 完成。
- 默认 profile 是 `ai_station_baseline_v1`。`seed=20260911`、20 个点、15 mm 最小中心距、六位小数舍入、10,000 次拒绝上限和历史坐标必须逐项一致。
- 现有 35 mm geometry sampler 保留为独立 profile `geometry_v2`。不得静默修改任一 profile 的结果。
- 首轮 campaign 使用一个 fresh stack，并在点之间执行 `RESET_WORLD`。失败点重试时，每个点独占一个 fresh stack 和一个 `FULL_RESTART` attempt。
- retry 不能覆盖首轮结果，也不能改变首轮成功率分母。`INVALID`、`NOT_RUN` 和 `BLOCKED` 不具备失败重试资格。
- validation server、stack、batch、每个 point worker 使用分别登记的进程所有权。禁止 broad `pkill`、`killall` 和进程名匹配。
- 未取得新鲜 `ShutdownSafetyReceipt` 时，不得 signal stack、reset、开夹爪或启动下一次执行；状态进入 `NEEDS_OPERATOR_RECOVERY`。
- event log 是进度提交权威。snapshot 只是缓存；HTTP/WebSocket 只能发布 supervisor journal 已接受的 sequence。
- 浏览器只提交类型化意图。它不生成 shell、状态机 transition、关节目标或高频控制命令。
- MoveIt expert、ACT collection、ACT rollout 使用不同 executor/operation 和统计口径。MoveIt 成功点不能自动获得 ACT 数据资格。
- Web 依赖、测试和一次性 CLI 统一使用 Bun 与现有 `bun.lock`，不用 npm、npx 或 `package-lock.json`。
- 普通 `so101_demo_py` gate 只收集 `src/so101_demo_py/test/`。本任务不改变 benchmark，不运行 `benchmark_test/`。
- 不运行 `ament_uncrustify --reformat`，不使用 `gh`，不 force-push。每个 commit 只包含该任务列出的文件；计划中的 commit 不自动授权 push。
- README 保持英文。本计划不修改课程、learner session、`progress.yaml` 或 ACT 实现。

---

## 执行前准备与证据门

编写本计划时，本地是 detached `6e816d66b8aa109a7bf84d4276d0c918cd19cd7a`，设计文档有未提交修改。ai-station 是 `main@ea0215180ed8cc0a90d6683a5e80d475987b5bc0`，存在另一任务的 MoveIt expert 优化改动和 attached `codex-19`。执行时把这些内容视为用户工作，禁止覆盖、stash、clean 或混入提交。

- [ ] 使用 `superpowers:using-git-worktrees` 创建实现 worktree。起点必须是同时包含已批准设计与本计划的 commit；不要从当前未提交状态猜测基线。
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
| 采样与几何 | `so101_teleop/expert_validation/sampler.py`, `projection.py`, `config/expert_validation/*` | 冻结 sampler profile、manifest、geometry 和共享投影 fixture |
| Batch 协议 | `so101_demo/application/task_batch.py`, `runtime/task_progress.py`, `runtime/task_batch_runtime.py` | 进度事件、完整点位终态、取消检查和安全回执 |
| 进程控制 | `so101_demo/runtime/process_owner.py`, `so101_teleop/expert_validation/process_owner.py` | supervisor-owned stack/batch/worker PGID 和本地 IPC |
| 持久化 | `so101_teleop/expert_validation/store.py` | SQLite journal、命令幂等、lease generation、accepted sequence 和恢复事务 |
| 监督器 | `so101_teleop/expert_validation/supervisor.py`, `service.py` | 首轮、重试、清理、恢复与统计状态机 |
| API | `so101_teleop/expert_validation/api.py`, `main.py` | 独立 FastAPI 入口、lease、manifest、campaign、artifact 与 WebSocket |
| 截图 | `so101_teleop/expert_validation/capture.py`, `so101_demo/runtime/viewer_capture.py` | GNOME/macOS adapter 与新鲜截图回执 |
| Web | `web/src/expert-validation-app.tsx`, `api/expert-validation-*`, `components/expert-validation/*` | 表单、地图、进度、证据和 FULL_RESTART 操作 |
| 验收 | `docs/experiments/so101-moveit-expert-validation-web-experiment-ledger.md` | source/install/runtime、4 点 smoke、20 点首轮和重试证据 |

## 批次 A：冻结点位与 batch 协议

### Task 1: 冻结 sampler profiles 和 20 点兼容 fixture

**Files:**

- Create: `src/so101_teleop/so101_teleop/expert_validation/__init__.py`
- Create: `src/so101_teleop/so101_teleop/expert_validation/sampler.py`
- Create: `src/so101_teleop/config/expert_validation/ai_station_baseline_v1.yaml`
- Create: `src/so101_teleop/config/expert_validation/ai_station_baseline_v1_points.yaml`
- Create: `src/so101_teleop/config/expert_validation/geometry_v2.yaml`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_sampler.py`
- Modify: `scripts/generate_so101_moveit_expert_position_top_view.py`

**Interfaces:**

- Consumes: four canonical anchors and versioned scene/policy/anchor hashes.
- Produces: `SamplerProfile`, `ManifestPoint`, `GeneratedManifest`, `load_sampler_profile(path: Path) -> SamplerProfile`, and `generate_manifest(profile: SamplerProfile, total_points: int, seed: int, geometry: dict[str, object]) -> GeneratedManifest`.

- [ ] **Step 1: 写 sampler RED tests。**

```python
def test_baseline_profile_reproduces_frozen_twenty_points(profile, geometry):
    manifest = generate_manifest(profile, 20, 20260911, geometry)
    assert [p.display_id for p in manifest.points[:4]] == ["P01", "P02", "P03", "P04"]
    assert [p.id for p in manifest.points[:4]] == [
        "task_start", "cup_test_forward_5cm",
        "cup_test_left_5cm", "cup_test_right_5cm",
    ]
    assert manifest.points[4].display_id == "P05"
    assert manifest.points[4].id == "sample_01_near_left"
    assert manifest.points[4].position_world_m == (-0.020732, -0.249568, 0.165)
    assert manifest.points[-1].display_id == "P20"
    assert manifest.points[-1].id == "sample_16_far_right"
    assert manifest.points[-1].position_world_m == (0.071574, -0.319255, 0.165)
    assert manifest.profile_id == "ai_station_baseline_v1"

def test_geometry_profile_cannot_replace_baseline(profile_v2, geometry):
    with pytest.raises(SamplerError, match="FIXTURE_PROFILE_MISMATCH"):
        verify_baseline_fixture(generate_manifest(profile_v2, 20, 20260911, geometry))
```

- [ ] **Step 2: 运行 RED。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_sampler.py -q
```

预期因 `so101_teleop.expert_validation.sampler` 不存在而失败。

- [ ] **Step 3: 写入精确 profile 和采样器。**

```yaml
schema_version: 1
profile_id: ai_station_baseline_v1
profile_version: 1
seed_default: 20260911
total_points_min: 4
total_points_max: 20
z_m: 0.165
minimum_pairwise_center_distance_m: 0.015
table_edge_margin_beyond_cup_radius_m: 0.010
rejection_limit_per_point: 10000
x_bands_m:
  left: [-0.045, -0.015]
  center: [-0.005, 0.035]
  right: [0.045, 0.080]
y_bands_m:
  near: [-0.255, -0.240]
  mid: [-0.305, -0.275]
  far: [-0.340, -0.315]
strata_order:
  - [near, left]
  - [near, center]
  - [near, right]
  - [near, left]
  - [near, center]
  - [mid, left]
  - [mid, center]
  - [mid, right]
  - [mid, left]
  - [mid, center]
  - [mid, right]
  - [far, left]
  - [far, center]
  - [far, right]
  - [far, center]
  - [far, right]
source_commit: ea0215180ed8cc0a90d6683a5e80d475987b5bc0
source_manifest_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
source_sampler_sha256: 81063ca943fd616d01c8e338c1f3d5b7c1bd091b8e79c538cce5c7bb69badccb
```

实现必须使用 `random.Random(seed).uniform()`，坐标先 `round(value, 6)` 再检查距离。小于 20 点时先生成完整 16 点 pool，再按 largest remainder 分配并恢复原 pool 顺序。拒绝 NaN、Inf、越界、间距不足、edge clearance 不足和超出 rejection cap。`geometry_v2` 保留当前 35 mm 规则。

- [ ] **Step 4: 把维护脚本改成 profile consumer。**

```python
parser.add_argument(
    "--sampler-profile",
    choices=("ai_station_baseline_v1", "geometry_v2"),
    default="ai_station_baseline_v1",
)
```

脚本继续生成 SVG/PNG/CSV/YAML，但点位来源只调用 `generate_manifest()`；删除脚本内第二套随机算法。通过 `ament_index_python` 查 installed config，源码模式只接受显式 `--repository-root`。

- [ ] **Step 5: 运行 GREEN 和脚本 readback。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_sampler.py -q
"$VALIDATION_PYTHON" scripts/generate_so101_moveit_expert_position_top_view.py \
  --repository-root "$PWD" \
  --sampler-profile ai_station_baseline_v1 \
  --seed 20260911 \
  --output-dir "$VALIDATION_EVIDENCE/top-view-fixture"
sha256sum "$VALIDATION_EVIDENCE/top-view-fixture"/*
```

预期 20 个坐标与 fixture 逐项一致，最小间距为 `0.015116191120781703` m。

- [ ] **Step 6: Commit。**

```zsh
git add src/so101_teleop/so101_teleop/expert_validation \
  src/so101_teleop/config/expert_validation \
  src/so101_teleop/test/teleop/test_expert_validation_sampler.py \
  scripts/generate_so101_moveit_expert_position_top_view.py
git commit -m "feat: freeze expert validation point sampler"
```

### Task 2: 建立共享 world-to-SVG 投影契约

**Files:**

- Create: `src/so101_teleop/so101_teleop/expert_validation/projection.py`
- Create: `src/so101_teleop/config/expert_validation/top_view_projection_v1.json`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_projection.py`
- Modify: `scripts/generate_so101_moveit_expert_position_top_view.py`

**Interfaces:**

- Consumes: `GeneratedManifest.geometry` and point status values.
- Produces: `Projection(width_px: int, height_px: int, bounds_m: tuple[float, float, float, float])`, `project_xy(projection, x_m, y_m) -> tuple[float, float]`, `marker_style(status: str) -> MarkerStyle`, and one JSON golden fixture for React tests.

- [ ] **Step 1: 写投影与样式 RED tests。**

```python
def test_projection_uses_equal_xy_scale_and_equal_marker_radius(fixture):
    projection = Projection.from_geometry(fixture["geometry"], 1200, 900)
    assert projection.pixels_per_m_x == projection.pixels_per_m_y
    assert project_xy(projection, 0.02, -0.28) == pytest.approx(tuple(fixture["p01_px"]))
    assert marker_style("SUCCEEDED").radius_px == marker_style("FAILED").radius_px

@pytest.mark.parametrize("state,color", [
    ("PENDING", "blue"), ("RUNNING", "blue"),
    ("SUCCEEDED", "green"), ("FAILED", "red"),
    ("INVALID", "red"), ("NOT_RUN", "red"), ("BLOCKED", "red"),
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

fixture 必须包含 table/base/target/P01/20 点投影、cup footprint radius、target tolerance radius、marker radius和 palette。P01 杯底与 target tolerance 使用虚线；selection 只增加外圈。

- [ ] **Step 4: 运行 GREEN，并核对 Python 输出仍使用新投影。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_projection.py -q
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_sampler.py -q
```

- [ ] **Step 5: Commit。**

```zsh
git add src/so101_teleop/so101_teleop/expert_validation/projection.py \
  src/so101_teleop/config/expert_validation/top_view_projection_v1.json \
  src/so101_teleop/test/teleop/test_expert_validation_projection.py \
  scripts/generate_so101_moveit_expert_position_top_view.py
git commit -m "feat: share expert validation map projection"
```

### Task 3: 把 batch 进度写成 authoritative append-only event log

**Files:**

- Create: `src/so101_demo_py/src/runtime/task_progress.py`
- Create: `src/so101_demo_py/test/test_task_progress.py`
- Modify: `src/so101_demo_py/src/application/task_batch.py`
- Modify: `src/so101_demo_py/src/cli/mujoco_rgbd_batch.py`
- Modify: `src/so101_demo_py/test/test_task_batch.py`
- Modify: `src/so101_demo_py/test/test_mujoco_rgbd_batch_cli.py`

**Interfaces:**

- Consumes: `campaign_id`, `attempt_id`, batch callbacks and installed result manifests.
- Produces: `ProgressEvent`, `ProgressWriter.append(kind: str, payload: dict[str, object], referenced_manifest: Path | None = None) -> ProgressEvent`, and CLI options `--campaign-id`, `--attempt-id`, `--progress-log`.

- [ ] **Step 1: 写 durability RED tests。**

```python
def test_point_finished_installs_manifest_before_fsynced_event(tmp_path, recorder):
    writer = ProgressWriter(tmp_path / "progress.ndjson", fsync=recorder.fsync)
    manifest = atomic_result(tmp_path / "point-result.json", {"status": "SUCCEEDED"})
    event = writer.append("POINT_FINISHED", {"point_id": "task_start"}, manifest)
    assert recorder.order == ["manifest", "manifest_dir", "event_log"]
    assert event.sequence == 1

def test_reader_buffers_live_partial_tail(tmp_path):
    path = tmp_path / "progress.ndjson"
    path.write_bytes(b'{"sequence":1')
    assert ProgressReader(path).read_complete(writer_alive=True) == []
    with pytest.raises(ProgressIntegrityError, match="TORN_TERMINAL_EVENT"):
        ProgressReader(path).read_complete(writer_alive=False)
```

- [ ] **Step 2: 运行 RED。**

```zsh
validation_pytest src/so101_demo_py/test/test_task_progress.py \
  src/so101_demo_py/test/test_task_batch.py \
  src/so101_demo_py/test/test_mujoco_rgbd_batch_cli.py -q
```

- [ ] **Step 3: 实现 canonical NDJSON。**

```python
@dataclass(frozen=True)
class ProgressEvent:
    schema_version: int
    campaign_id: str
    attempt_id: str
    sequence: int
    kind: str
    payload_sha256: str
    payload: dict[str, object]
    timestamp_ns: int
```

每条完整 record 以单个 `os.write(O_APPEND)` 写入并带换行，随后 `fsync`。`POINT_FINISHED` 和 `BATCH_FINISHED` 只能引用已 atomic replace、fsync 文件并 fsync parent directory 的 manifest。禁止通过解析日志推断 phase。

- [ ] **Step 4: 在 batch 边界发事件。**

依次发送 `BATCH_STARTED`、`POINT_REACHABILITY`、`POINT_STARTED`、每个 `ARTIFACT_REGISTERED`、`POINT_FINISHED`、`BATCH_FINISHED`。现有无 progress writer 的 CLI 行为保持兼容；validation supervisor 启动时三个新参数必填。

- [ ] **Step 5: 运行 GREEN。**

```zsh
validation_pytest src/so101_demo_py/test/test_task_progress.py \
  src/so101_demo_py/test/test_task_batch.py \
  src/so101_demo_py/test/test_mujoco_rgbd_batch_cli.py -q
```

- [ ] **Step 6: Commit。**

```zsh
git add src/so101_demo_py/src/runtime/task_progress.py \
  src/so101_demo_py/src/application/task_batch.py \
  src/so101_demo_py/src/cli/mujoco_rgbd_batch.py \
  src/so101_demo_py/test/test_task_progress.py \
  src/so101_demo_py/test/test_task_batch.py \
  src/so101_demo_py/test/test_mujoco_rgbd_batch_cli.py
git commit -m "feat: persist task batch progress events"
```

### Task 4: 补齐点位终态和统计口径

**Files:**

- Modify: `src/so101_demo_py/src/application/task_batch.py`
- Modify: `src/so101_demo_py/test/test_task_batch.py`
- Create: `src/so101_teleop/so101_teleop/expert_validation/statistics.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_statistics.py`

**Interfaces:**

- Consumes: accepted progress events.
- Produces: `PointProjection`, `FirstPassQualification`, terminal states `SUCCEEDED | FAILED | SKIPPED_UNREACHABLE | INVALID | NOT_RUN | BLOCKED`, and `summarize_first_pass(points: Sequence[PointProjection], qualification: FirstPassQualification) -> FirstPassStatistics`.

- [ ] **Step 1: 写 unreachable 与中断 RED tests。**

```python
def test_unreachable_is_evaluated_failure_not_unexecuted():
    summary = summarize_first_pass([
        point("task_start", "SKIPPED_UNREACHABLE", evaluated=True, execution_started=False),
    ], qualification=qualified())
    assert summary.evaluated == 1
    assert summary.execution_started == 0
    assert summary.valid_failed == 1
    assert summary.not_executed == 0

def test_started_point_without_terminal_receipt_is_invalid():
    result = reconcile_terminal(point_events("task_start", "POINT_STARTED"), "OWNER_LOST")
    assert result.status == "INVALID"
    assert result.reason == "OWNER_LOST"

def test_shutdown_qualification_changes_rate_without_changing_point_counts():
    points = [point("task_start", "SUCCEEDED", evaluated=True, execution_started=True)]
    safe = summarize_first_pass(points, qualification=qualified())
    unresolved = summarize_first_pass(
        points,
        qualification=FirstPassQualification(False, False, "SHUTDOWN_SAFETY_UNRESOLVED"),
    )
    assert safe.valid_succeeded == unresolved.valid_succeeded == 1
    assert safe.qualified_success_rate == 1.0
    assert unresolved.qualified_success_rate is None
```

补充 `UNKNOWN` reachability、reachability 后 owner loss、shared failure 后 untouched、cancel 后 untouched、receipt integrity failure，以及 terminal campaign 不得含 `PENDING/RUNNING` 的测试。

- [ ] **Step 2: 运行 RED。**

```zsh
validation_pytest src/so101_demo_py/test/test_task_batch.py \
  src/so101_teleop/test/teleop/test_expert_validation_statistics.py -q
```

- [ ] **Step 3: 实现 reconciliation table 与公式。**

```python
@dataclass(frozen=True)
class PointProjection:
    point_id: str
    status: Literal[
        "SUCCEEDED", "FAILED", "SKIPPED_UNREACHABLE",
        "INVALID", "NOT_RUN", "BLOCKED",
    ]
    evaluated: bool
    execution_started: bool
    receipt_integrity_valid: bool
    reason: str | None = None

@dataclass(frozen=True)
class FirstPassQualification:
    shutdown_safety_confirmed: bool
    receipt_integrity_complete: bool
    reason: str | None = None

@dataclass(frozen=True)
class FirstPassStatistics:
    requested: int
    evaluated: int
    execution_started: int
    valid_succeeded: int
    valid_failed: int
    invalid: int
    not_executed: int
    evaluation_coverage: float
    execution_coverage: float
    qualified_success_rate: float | None
```

先验证 point receipt integrity，再应用产品状态。receipt 失效优先成为 `INVALID`；后续 campaign 级失败不能覆盖仍然有效的 point receipt。`qualification.shutdown_safety_confirmed` 或 `receipt_integrity_complete` 为 false 时保留计数，但 `qualified_success_rate=None`。

- [ ] **Step 4: 运行 GREEN。**

```zsh
validation_pytest src/so101_demo_py/test/test_task_batch.py \
  src/so101_teleop/test/teleop/test_expert_validation_statistics.py -q
```

- [ ] **Step 5: Commit。**

```zsh
git add src/so101_demo_py/src/application/task_batch.py \
  src/so101_demo_py/test/test_task_batch.py \
  src/so101_teleop/so101_teleop/expert_validation/statistics.py \
  src/so101_teleop/test/teleop/test_expert_validation_statistics.py
git commit -m "feat: reconcile expert validation point outcomes"
```

## 批次 B：进程、安全、持久化与服务

### Task 5: 建立 supervisor-owned process broker

**Files:**

- Create: `src/so101_demo_py/src/runtime/process_owner.py`
- Create: `src/so101_demo_py/test/test_process_owner.py`
- Create: `src/so101_teleop/so101_teleop/expert_validation/process_owner.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_process_owner.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_process_owner_integration.py`
- Create: `src/so101_teleop/test/fixtures/process_tree_helper.py`
- Modify: `src/so101_demo_py/src/runtime/task_batch_runtime.py`
- Modify: `src/so101_demo_py/src/cli/mujoco_rgbd_batch.py`
- Modify: `src/so101_demo_py/test/test_task_batch_runtime.py`
- Modify: `src/so101_demo_py/test/test_mujoco_rgbd_batch_cli.py`

**Interfaces:**

- Consumes: argv arrays, attempt token, role `stack | batch | point_worker`, and supervisor journal callback.
- Produces: `OwnedProcess`, `CommandResult`, `ProcessOwnerPort.spawn()`, `run()`, `poll()`, `stop()`, `BrokeredPointProcesses`, `BrokeredCommandRunner`, and Unix socket RPC with canonical JSON frames.

- [ ] **Step 1: 写独立 PGID RED tests。**

```python
def test_two_points_stop_worker_groups_without_stopping_batch(owner, batch):
    first = owner.spawn(worker_request("task_start", "perception"))
    owner.stop(first.worker_id, safety_receipt_id="safe-p01")
    assert owner.group_is_gone(first.pgid)
    assert batch.poll() is None
    second = owner.spawn(worker_request("cup_test_forward_5cm", "perception"))
    assert second.pgid != first.pgid

def test_group_leader_exit_does_not_hide_descendant(owner):
    process = owner.spawn(worker_with_descendant())
    process.leader.exit()
    assert owner.cleanup(process.worker_id).status == "DESCENDANT_REMAINS"

def test_validation_runtime_cannot_bypass_broker(monkeypatch, brokered_runtime):
    monkeypatch.setattr(subprocess, "Popen", forbidden("Popen"))
    monkeypatch.setattr(subprocess, "run", forbidden("run"))
    monkeypatch.setattr(os, "killpg", forbidden("killpg"))
    brokered_runtime.check_declared(task_start())
    brokered_runtime.reset_point(task_start())
    brokered_runtime.start_consumer(point_root(), 1)
```

再覆盖 batch dies after spawn intent、missing child acknowledgement、unknown descendant、attempt token mismatch、one-shot timeout 和 bounded stdout/stderr。迁移清单必须覆盖 `OwnedPointProcesses.start/stop_all`、`RosGraphProbe.subscription_count`、`RosTaskBatchRuntime._run` 中的 reachability/reset，以及 validation capture 调用；validation mode 下这些路径都只能使用 broker。

- [ ] **Step 2: 运行 RED。**

```zsh
validation_pytest src/so101_demo_py/test/test_process_owner.py \
  src/so101_demo_py/test/test_task_batch_runtime.py \
  src/so101_demo_py/test/test_mujoco_rgbd_batch_cli.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner_integration.py -q
```

- [ ] **Step 3: 实现类型与 broker。**

```python
@dataclass(frozen=True)
class SpawnRequest:
    attempt_id: str
    role: Literal["stack", "batch", "point_worker"]
    argv: tuple[str, ...]
    environment: Mapping[str, str]
    evidence_root: Path

@dataclass(frozen=True)
class RunRequest:
    attempt_id: str
    role: Literal["ros_probe", "reachability", "reset", "capture"]
    argv: tuple[str, ...]
    environment: Mapping[str, str]
    evidence_root: Path
    timeout_s: float

@dataclass(frozen=True)
class OwnedProcess:
    worker_id: str
    attempt_id: str
    role: str
    pid: int
    pgid: int
    started_ticks: int
    argv_sha256: str
    environment_sha256: str

@dataclass(frozen=True)
class CleanupReceipt:
    worker_id: str
    safety_receipt_id: str
    descendants_gone: bool
    stopped_at_monotonic_ns: int

@dataclass(frozen=True)
class CommandResult:
    worker_id: str
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    cleanup_receipt_id: str

class ProcessOwnerPort(Protocol):
    def spawn(self, request: SpawnRequest) -> OwnedProcess: ...
    def run(self, request: RunRequest) -> CommandResult: ...
    def poll(self, worker_id: str) -> int | None: ...
    def stop(self, worker_id: str, safety_receipt_id: str) -> CleanupReceipt: ...
```

supervisor 在 child exec barrier 前持久化 `SPAWN_INTENT`，收到 PID/PGID/start-time acknowledgement 后写 `RUNNING` 并放行。每个 point worker 和 one-shot command 使用独立 PGID；one-shot 输出有字节上限并在 timeout 后走同一安全清理协议。`mujoco_rgbd_batch.py` 新增 `--process-owner-socket` 与 `--process-owner-token`；两者必须同时出现。validation mode 将 `BrokeredPointProcesses` 注入 point workers，将 `BrokeredCommandRunner` 同时注入 `RosGraphProbe` 和 `RosTaskBatchRuntime`。validation mode 下 batch 本地不得调用 `Popen`、`subprocess.run`、`start_new_session` 或 `killpg`；无 broker 参数的旧 CLI 仍可使用 `LocalPointProcesses` 和本地 runner。

- [ ] **Step 4: 写并运行真实 OS process integration gate。**

`process_tree_helper.py` 只创建无 ROS 的短生命周期父子进程。测试必须使用真实 PID/PGID 和一个 fsync 的 test journal callback，覆盖 leader 先退出而 descendant 留存、exec barrier 前崩溃、ack 丢失、两个点共用同一 batch、两个 retry 的 fresh group，以及 cleanup receipt 写入后才能启动下一组。测试不能 monkeypatch `Popen`、`killpg` 或 `/proc` 读取。Task 7 再把同一 broker 接到 `SupervisorStore` 并验证关闭后重开恢复。

```zsh
validation_pytest \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner_integration.py -q
```

- [ ] **Step 5: 运行 GREEN。**

```zsh
validation_pytest src/so101_demo_py/test/test_process_owner.py \
  src/so101_demo_py/test/test_task_batch_runtime.py \
  src/so101_demo_py/test/test_mujoco_rgbd_batch_cli.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner_integration.py -q
```

- [ ] **Step 6: Commit。**

```zsh
git add src/so101_demo_py/src/runtime/process_owner.py \
  src/so101_demo_py/src/runtime/task_batch_runtime.py \
  src/so101_demo_py/src/cli/mujoco_rgbd_batch.py \
  src/so101_demo_py/test/test_process_owner.py \
  src/so101_demo_py/test/test_task_batch_runtime.py \
  src/so101_demo_py/test/test_mujoco_rgbd_batch_cli.py \
  src/so101_teleop/so101_teleop/expert_validation/process_owner.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner_integration.py \
  src/so101_teleop/test/fixtures/process_tree_helper.py
git commit -m "feat: broker expert validation processes"
```

### Task 6: 分离 execution outcome、取消和 shutdown safety

**Files:**

- Create: `src/so101_demo_py/src/application/shutdown_safety.py`
- Create: `src/so101_demo_py/src/runtime/shutdown_safety_probe.py`
- Create: `src/so101_demo_py/src/cli/task_shutdown_safety.py`
- Create: `src/so101_demo_py/config/expert_validation/shutdown_safety_v1.yaml`
- Create: `src/so101_demo_py/test/test_shutdown_safety.py`
- Create: `src/so101_demo_py/test/test_task_shutdown_safety_cli.py`
- Modify: `src/so101_demo_py/src/application/task_batch.py`
- Modify: `src/so101_demo_py/src/runtime/task_batch_runtime.py`
- Modify: `src/so101_demo_py/src/runtime/process_owner.py`
- Modify: `src/so101_demo_py/test/test_task_batch.py`
- Modify: `src/so101_demo_py/test/test_task_batch_runtime.py`
- Modify: `src/so101_demo_py/setup.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/process_owner.py`

**Interfaces:**

- Consumes: session/epoch-bound MuJoCo evidence, arm/gripper joint feedback, controller action state, brokered shutdown-probe command, and cancellation checkpoint RPC.
- Produces: `ShutdownSafetyReceipt`, `ShutdownSafetyProbePort.probe()`, `TaskBatchRuntime.probe_shutdown_safety(reason: str)`, CLI `task_shutdown_safety`, and `ControlPort.checkpoint(name: str) -> CancelDecision`.

- [ ] **Step 1: 写所有 exit path 的 RED tests。**

```python
@pytest.mark.parametrize("exit_reason", [
    "SUCCESS", "PRODUCT_FAILURE", "SHARED_FAILURE", "TIMEOUT",
    "CANCELLED", "CORRUPT_PROGRESS", "OWNER_DIED",
])
def test_every_exit_requires_fresh_shutdown_receipt(exit_reason, runtime):
    runtime.receipt = None
    result = finalize_attempt(runtime, exit_reason)
    assert result.status == "NEEDS_OPERATOR_RECOVERY"
    assert result.shutdown_safe is False

def test_stale_epoch_never_authorizes_signal(runtime):
    runtime.receipt = safe_receipt(session="sim-a", epoch=7)
    result = authorize_signal(runtime.receipt, expected_session="sim-a", expected_epoch=8)
    assert result.allowed is False

def test_height_and_contact_count_cannot_substitute_for_authentic_hold_evidence(probe):
    probe.physics = physical_sample(cup_z_m=0.24, authenticity=False)
    receipt = probe.probe(shutdown_request())
    assert receipt.safe_to_shutdown is False
    assert receipt.reason_code == "PHYSICAL_EVIDENCE_NOT_AUTHENTIC"

def test_unsupported_held_cup_is_held_without_opening_gripper(probe):
    probe.physics = physical_sample(cup_held=True, support_confirmed=False)
    receipt = probe.probe(shutdown_request())
    assert probe.gripper_open_requests == 0
    assert receipt.robot_hold_confirmed is True
    assert receipt.safe_to_shutdown is False
```

- [ ] **Step 2: 运行 RED。**

```zsh
validation_pytest src/so101_demo_py/test/test_shutdown_safety.py \
  src/so101_demo_py/test/test_task_shutdown_safety_cli.py \
  src/so101_demo_py/test/test_task_batch.py \
  src/so101_demo_py/test/test_task_batch_runtime.py -q
```

- [ ] **Step 3: 实现独立安全回执。**

```python
@dataclass(frozen=True)
class ShutdownSafetyReceipt:
    receipt_id: str
    campaign_id: str
    attempt_id: str
    simulation_session_id: str
    epoch: int
    observed_at_ns: int
    freshness_limit_ns: int
    cup_held: bool
    support_confirmed: bool
    robot_hold_requested: bool
    robot_hold_confirmed: bool
    controller_stop_confirmed: bool
    safe_to_shutdown: bool
    reason_code: str | None
    artifact_ids: tuple[str, ...]

class ShutdownSafetyProbePort(Protocol):
    def probe(
        self,
        campaign_id: str,
        attempt_id: str,
        simulation_session_id: str,
        reset_or_release_epoch: int,
        reason: str,
    ) -> ShutdownSafetyReceipt: ...
```

移除 `wait_point_result()` 中硬编码的 `SafetyReceipt(True, False, None)`，并删除当前以杯高加接触数量推断 held 的 fallback。共享失败也必须探测安全。`task_shutdown_safety` 由 broker 启动，使用 authentic `SimulationEvidence` 读取 simulation session、reset/release epoch、双侧指尖接触和桌面支撑接触；读取 arm/gripper `/joint_states`，向现有 FollowJointTrajectory control boundary 发送“保持当前关节位置”的 bounded hold goal，随后验证 action result、没有 active motion goal、连续静止窗口内关节速度小于阈值。它不发 reset，也不打开夹爪。

`shutdown_safety_v1.yaml` 固定 `physical_evidence_max_age_s: 0.5`、`joint_state_max_age_s: 0.5`、`hold_timeout_s: 5.0`、`stationary_window_s: 0.5` 和 `max_abs_joint_velocity_rad_s: 0.02`。`safe_to_shutdown` 只在 session/epoch、两类 freshness、authentic evidence、not-held-or-supported、hold acknowledgement 和 controller stationary 均满足时成立；任何 timeout、缺 topic、非 authentic sample 或 identity mismatch 都返回具体 `reason_code` 并 fail closed。

- [ ] **Step 4: 接入 cooperative cancellation。**

batch 在 reachability 前、point start 前、execution 返回后、worker cleanup 前、reset 前和 batch finalize 前调用 `ControlPort.checkpoint()`。收到 cancel 后先完成 hold/stop 与 safety receipt；超时或无 receipt 时进入 recovery，不 signal stack。

- [ ] **Step 5: 运行 GREEN。**

```zsh
validation_pytest src/so101_demo_py/test/test_shutdown_safety.py \
  src/so101_demo_py/test/test_task_shutdown_safety_cli.py \
  src/so101_demo_py/test/test_task_batch.py \
  src/so101_demo_py/test/test_task_batch_runtime.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner.py -q
```

- [ ] **Step 6: Commit。**

```zsh
git add src/so101_demo_py/src/application/shutdown_safety.py \
  src/so101_demo_py/src/runtime/shutdown_safety_probe.py \
  src/so101_demo_py/src/cli/task_shutdown_safety.py \
  src/so101_demo_py/config/expert_validation/shutdown_safety_v1.yaml \
  src/so101_demo_py/src/application/task_batch.py \
  src/so101_demo_py/src/runtime/task_batch_runtime.py \
  src/so101_demo_py/src/runtime/process_owner.py \
  src/so101_demo_py/test/test_shutdown_safety.py \
  src/so101_demo_py/test/test_task_shutdown_safety_cli.py \
  src/so101_demo_py/test/test_task_batch.py \
  src/so101_demo_py/test/test_task_batch_runtime.py \
  src/so101_teleop/so101_teleop/expert_validation/process_owner.py \
  src/so101_demo_py/setup.py
git commit -m "feat: gate validation shutdown on safety evidence"
```

### Task 7: 实现 durable supervisor store 与幂等事务

**Files:**

- Create: `src/so101_teleop/so101_teleop/expert_validation/store.py`
- Create: `src/so101_teleop/so101_teleop/expert_validation/models.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_store.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/process_owner.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_process_owner_integration.py`

**Interfaces:**

- Consumes: canonical JSON command bodies, progress events, Task 5 process-owner journal callbacks, process intents and receipts.
- Produces: `SupervisorStore.open(root: Path)`, `begin_command()`, `record_spawn_intent()`, `acknowledge_process()`, `record_cleanup_and_advance_retry()`, `accept_event()`, `finish_command()`, `reconcile()`, and immutable query projections.

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
    store.record_spawn_intent(spawn_intent("worker-1", token="spawn-a"))
    store.acknowledge_process(process_ack("worker-1", pid=123, pgid=123))
    store.enqueue_retries("campaign-1", ["sample_05_near_center", "sample_14_far_right"])
    store.close()
    reopened = SupervisorStore.open(tmp_path)
    assert reopened.owned_process("worker-1").spawn_token == "spawn-a"
    assert reopened.next_retry("campaign-1").point_id == "sample_05_near_center"

def test_cleanup_and_retry_advance_are_one_transaction(store):
    store.enqueue_retries("campaign-1", ["sample_05_near_center"])
    store.record_cleanup_and_advance_retry(cleanup_receipt("worker-1"))
    assert store.next_retry("campaign-1") is None
```

补充 spawn intent 后崩溃、child ack 后崩溃、event log fsync 后 journal 前、journal 后 HTTP 前、retry finish 后 dequeue 前、singleton lock 和 ambiguous command 测试。

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
CREATE TABLE campaigns (
  campaign_id TEXT PRIMARY KEY,
  state TEXT NOT NULL,
  manifest_id TEXT NOT NULL REFERENCES manifests(manifest_id),
  executor_id TEXT NOT NULL,
  operation_id TEXT NOT NULL,
  executor_config_sha256 TEXT NOT NULL
);
CREATE TABLE attempts (
  attempt_id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
  state TEXT NOT NULL,
  accepted_sequence INTEGER NOT NULL DEFAULT 0,
  simulation_session_id TEXT NOT NULL,
  ros_domain_id INTEGER NOT NULL
);
CREATE TABLE accepted_events (
  attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
  sequence INTEGER NOT NULL,
  event_sha256 TEXT NOT NULL,
  canonical_json TEXT NOT NULL,
  PRIMARY KEY (attempt_id, sequence)
);
CREATE TABLE owned_processes (
  worker_id TEXT PRIMARY KEY,
  attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
  parent_worker_id TEXT,
  role TEXT NOT NULL,
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
  acknowledged_at_ns INTEGER
);
CREATE TABLE process_descendants (
  worker_id TEXT NOT NULL REFERENCES owned_processes(worker_id),
  pid INTEGER NOT NULL,
  pgid INTEGER NOT NULL,
  started_ticks INTEGER NOT NULL,
  executable_sha256 TEXT NOT NULL,
  PRIMARY KEY (worker_id, pid, started_ticks)
);
CREATE TABLE cleanup_receipts (
  cleanup_receipt_id TEXT PRIMARY KEY,
  worker_id TEXT NOT NULL REFERENCES owned_processes(worker_id),
  safety_receipt_id TEXT NOT NULL,
  descendants_gone INTEGER NOT NULL,
  canonical_json TEXT NOT NULL,
  receipt_sha256 TEXT NOT NULL,
  recorded_at_ns INTEGER NOT NULL
);
CREATE TABLE retry_queue (
  campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
  ordinal INTEGER NOT NULL,
  point_id TEXT NOT NULL,
  state TEXT NOT NULL,
  attempt_id TEXT,
  cleanup_receipt_id TEXT,
  PRIMARY KEY (campaign_id, ordinal)
);
CREATE TABLE leases (lease_id TEXT PRIMARY KEY, service_session_id TEXT NOT NULL, generation INTEGER NOT NULL, expires_monotonic_ns INTEGER NOT NULL, state TEXT NOT NULL);
CREATE TABLE artifacts (
  artifact_id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
  attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
  relative_path TEXT NOT NULL,
  media_type TEXT NOT NULL,
  sha256 TEXT NOT NULL
);
CREATE TABLE safety_receipts (
  receipt_id TEXT PRIMARY KEY,
  attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
  canonical_json TEXT NOT NULL,
  receipt_sha256 TEXT NOT NULL
);
CREATE TABLE readiness_receipts (
  receipt_id TEXT PRIMARY KEY,
  attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
  receipt_kind TEXT NOT NULL,
  canonical_json TEXT NOT NULL,
  receipt_sha256 TEXT NOT NULL
);
```

所有 mutation 使用 `BEGIN IMMEDIATE`，canonical JSON 使用 sorted keys 与 UTF-8，store root 必须是绝对非 symlink 路径。OS-level lock 文件在 SQLite 打开前取得，第二个 writer 返回 `VALIDATION_SUPERVISOR_ACTIVE`。

事务顺序固定为：command/campaign/attempt 或 retry queue 先落盘；每次 fork 前单独提交 ownership intent；child 停在 exec barrier；PID/PGID/start ticks、parent/descendant identity 和 executable readback 在同一 acknowledgement 事务写入后才放行；event journal acceptance 单独提交；cleanup receipt 与 retry cursor advance 必须处于同一事务；最后提交 command result，随后才返回 HTTP。重启测试必须关闭旧 store、丢弃全部 Python 对象，再从 SQLite、event log 和 `/proc` 重建状态。任何缺失 ack、fingerprint mismatch 或 cursor/cleanup 不一致都返回 `COMMAND_OUTCOME_UNKNOWN` 或进入 `NEEDS_OPERATOR_RECOVERY`，不得猜测执行完成。

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

### Task 8: 实现 first-pass 与 FULL_RESTART supervisor

**Files:**

- Create: `src/so101_teleop/so101_teleop/expert_validation/supervisor.py`
- Create: `src/so101_teleop/so101_teleop/expert_validation/readiness.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_supervisor.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_readiness.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/process_owner.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/store.py`

**Interfaces:**

- Consumes: `SupervisorStore`, sampler manifests, process broker, `ShutdownSafetyReceipt`, brokered ROS/physics probes, installed ROS argv builder and progress log.
- Produces: `ReadinessReceipt`, `InitialStateReceipt`, `ReadinessProbePort`, `ExpertValidationSupervisor.start_first_pass()`, `cancel()`, `start_retries()`, `status()`, `list_campaigns()`, and `reconcile_startup()`.

- [ ] **Step 1: 写 lifecycle RED tests。**

```python
async def test_first_pass_uses_one_stack_and_one_batch(fake_owner, supervisor):
    campaign = await supervisor.start_first_pass(start_request("manifest-20"))
    await fake_owner.finish_batch(campaign.attempt_id, shutdown_safe=True)
    assert fake_owner.roles_started == ["stack", "batch"]
    assert fake_owner.stack_starts == 1

async def test_each_retry_gets_fresh_stack_and_cleanup_before_next(fake_owner, supervisor):
    await supervisor.start_retries(retry_request(
        "campaign-1", ["sample_05_near_center", "sample_14_far_right"]
    ))
    assert fake_owner.timeline == [
        "start-stack-sample_05_near_center",
        "start-batch-sample_05_near_center",
        "cleanup-sample_05_near_center",
        "start-stack-sample_14_far_right",
        "start-batch-sample_14_far_right",
        "cleanup-sample_14_far_right",
    ]

@pytest.mark.parametrize("failure", [
    "CONTROLLER_NOT_ACTIVE", "JOINT_STATE_STALE", "MOVEIT_NOT_READY",
    "PLANNING_SCENE_NOT_READY", "CAMERA_NOT_READY",
    "PHYSICAL_EVIDENCE_STALE", "SESSION_OR_EPOCH_MISMATCH",
])
async def test_readiness_failure_never_starts_batch(supervisor, readiness, failure):
    readiness.stack_receipt = failed_readiness(failure)
    await supervisor.start_first_pass(start_request("manifest-20"))
    assert supervisor.process_owner.roles_started == ["stack"]

async def test_retry_wrong_canonical_initial_state_never_executes(supervisor, readiness):
    readiness.initial_receipt = failed_initial_state(
        point_id="sample_05_near_center", reason="CUP_POSITION_MISMATCH"
    )
    await supervisor.start_retries(
        retry_request("campaign-1", ["sample_05_near_center"])
    )
    assert supervisor.process_owner.roles_started == ["stack"]
```

覆盖 no second active execution、invalid retry eligibility、cleanup failure stops queue、held cup、unknown process、owner death、server restart reconciliation 和 `LIVE_RETRY_NOT_APPLICABLE_ALL_SUCCEEDED`。readiness tests 还要覆盖错误 joint 初态、gripper 未打开、cup 未受桌面支撑、指尖仍接触、MoveIt 中杯子仍 attached，以及 receipt 超出 freshness bound。

- [ ] **Step 2: 运行 RED。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_readiness.py \
  src/so101_teleop/test/teleop/test_expert_validation_supervisor.py -q
```

- [ ] **Step 3: 实现 readiness 与 canonical initial-state contracts。**

```python
@dataclass(frozen=True)
class AttemptRequest:
    campaign_id: str
    attempt_id: str
    manifest_id: str
    simulation_session_id: str
    ros_domain_id: int
    evidence_root: Path

@dataclass(frozen=True)
class ReadinessReceipt:
    attempt_id: str
    simulation_session_id: str
    reset_epoch: int
    observed_at_ns: int
    freshness_limit_ns: int
    source_commit: str
    install_prefix: str
    runtime_sha256: str
    active_controllers: tuple[str, ...]
    joint_state_stamp_ns: int
    moveit_ready: bool
    planning_scene_revision: str
    camera_stamps_ns: Mapping[str, int]
    physical_evidence_stamp_ns: int
    physical_evidence_authentic: bool
    ready: bool
    reason_codes: tuple[str, ...]

@dataclass(frozen=True)
class InitialStateReceipt:
    attempt_id: str
    point_id: str
    simulation_session_id: str
    reset_epoch: int
    observed_at_ns: int
    maximum_joint_error_rad: float
    gripper_open: bool
    cup_position_error_m: float
    cup_orientation_error_rad: float
    support_confirmed: bool
    fingertip_contact_count: int
    moveit_world_contains_cup: bool
    moveit_attached_object_ids: tuple[str, ...]
    valid: bool
    reason_codes: tuple[str, ...]

class ReadinessProbePort(Protocol):
    def probe_stack(self, request: AttemptRequest) -> ReadinessReceipt: ...
    def probe_initial_state(
        self, request: AttemptRequest, point: ManifestPoint
    ) -> InitialStateReceipt: ...
```

`probe_stack()` 必须通过 brokered commands 运行现有 `motion_stack_ready`，读取 fresh `/joint_states`，执行 Planning Scene observe，并读取 task RGB-D 与 authentic `SimulationEvidence`。所有样本必须匹配 attempt session/epoch，且来源 commit、install prefix 和 runtime SHA256 与 ownership intent 一致。`probe_initial_state()` 从 installed MuJoCo scene 的 `task_start` keyframe 和当前 manifest point 取得期望值；joint tolerance 使用 installed `headless_execution.yaml:joint_convergence_tolerance_rad`，cup pose tolerance 使用 installed dynamic policy 的 `scene_position_tolerance_m` 与 `scene_orientation_tolerance_rad`。它还要求 gripper open、桌面支撑、零指尖接触、杯子在 MoveIt world 集合且 attached 集合为空。receipt 连同输入 hashes 写入 store；任何缺项都不启动 batch。

- [ ] **Step 4: 实现 argv-only stack 与 batch 启动。**

```python
def stack_argv(request: AttemptRequest) -> tuple[str, ...]:
    return (
        "ros2", "launch", "so101_demo_py", "so101_mujoco_task_station.launch.py",
        "headless:=false", "sensor_rendering:=true", "include_teleop:=false",
        f"session_id:={request.simulation_session_id}",
        f"task_evidence_root:={request.evidence_root}",
    )
```

batch argv 必须包含 `--attach-existing-stack`、准确 MuJoCo PID、campaign/attempt IDs、progress log、broker socket 和 broker token。每次 attempt 分配新 simulation session、ROS domain、evidence child 和 process identities。stack acknowledgement 后先接受 `ReadinessReceipt`，retry 还必须接受 `InitialStateReceipt`，之后才能 spawn batch。未知冲突只报告，不自动 kill。不得依赖 `mujoco_rgbd_batch.py` attached 分支中当前缺失的 `_wait_for_task_station()` 调用。

- [ ] **Step 5: 实现 terminal/recovery 顺序。**

先接受 `BATCH_FINISHED` 与 result manifest，再接受 fresh shutdown receipt，之后按 point workers、batch、stack 顺序 cleanup 并验证 descendants 和 ROS graph 消失。任何缺口写 `NEEDS_OPERATOR_RECOVERY`；retry queue 只有在 cleanup receipt 落盘后推进。

- [ ] **Step 6: 运行 GREEN。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_readiness.py \
  src/so101_teleop/test/teleop/test_expert_validation_supervisor.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner.py \
  src/so101_teleop/test/teleop/test_expert_validation_store.py -q
```

- [ ] **Step 7: Commit。**

```zsh
git add src/so101_teleop/so101_teleop/expert_validation/supervisor.py \
  src/so101_teleop/so101_teleop/expert_validation/readiness.py \
  src/so101_teleop/so101_teleop/expert_validation/process_owner.py \
  src/so101_teleop/so101_teleop/expert_validation/store.py \
  src/so101_teleop/test/teleop/test_expert_validation_readiness.py \
  src/so101_teleop/test/teleop/test_expert_validation_supervisor.py
git commit -m "feat: supervise expert validation campaigns"
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

def test_v1_registry_only_exposes_moveit_validation(registry):
    capability = registry.require("moveit_expert", "validate_pick_place")
    assert capability.lifecycle_modes == ("RESET_WORLD", "FULL_RESTART")
    with pytest.raises(UnknownOperation):
        registry.require("act_collect", "collect_demonstration")

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
    lifecycle_modes: tuple[str, ...]
    success_contract_id: str

class ExecutorRegistry:
    def register(self, capability: ExecutorCapability) -> None: ...
    def require(self, executor_id: str, operation_id: str) -> ExecutorCapability: ...
```

启动时使旧 generation 全部失效。browser disconnect 不自动释放。lease expiry 只请求 cooperative cancellation；没有 safety receipt 时仍进入 recovery。新 holder 在 unresolved campaign 期间只能 read/cancel/recover。V1 registry 只注册 `moveit_expert/validate_pick_place`；未来 `act_collect` 和 `act_rollout` operation 只能通过新 request model、evidence schema 和 success contract 显式注册，不能复用 MoveIt 统计。

- [ ] **Step 4: 实现 immutable manifest 与 durable command idempotency。**

manifest generation 将完整 16 点 pool 按 Task 1 规则裁成请求点数，生成 server-owned `manifest_id`，并把 canonical document 与 SHA256 作为同一 durable transaction 写入 store。start 重新计算 installed sampler/policy/scene/geometry/anchor hashes；不一致时只拒绝启动，旧 manifest 仍可查询。service 对 campaign start/cancel/retry 使用 canonical request SHA256。相同 command ID 与 payload 返回存储结果，不同 payload 返回 `COMMAND_ID_REUSED`；崩溃后无法判定的命令返回 `COMMAND_OUTCOME_UNKNOWN`，禁止换 ID 绕过 reconciliation。

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

### Task 10: 接入 GNOME/macOS 截图和 artifact registry

**Files:**

- Create: `src/so101_teleop/so101_teleop/expert_validation/capture.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_capture.py`
- Modify: `src/so101_demo_py/src/runtime/viewer_capture.py`
- Modify: `src/so101_demo_py/test/test_viewer_capture.py`
- Modify: `src/so101_demo_py/src/cli/mujoco_rgbd_batch.py`
- Modify: `src/so101_demo_py/test/test_mujoco_rgbd_batch_cli.py`
- Modify: `src/so101_teleop/so101_teleop/task_artifacts.py`
- Modify: `src/so101_teleop/test/teleop/test_task_artifacts.py`

**Interfaces:**

- Consumes: brokered `capture_viewer` request, exact PID/window identity and attempt evidence root.
- Produces: `CaptureReceipt(artifact_id, captured_at_ns, window_id, process_started_ticks, sha256)` and registered opaque artifact IDs.

- [ ] **Step 1: 写 stale-window 与 traversal RED tests。**

```python
def test_capture_rejects_image_older_than_request(adapter):
    with pytest.raises(CaptureError, match="STALE_VIEWER_CAPTURE"):
        adapter.capture(requested_at_ns=200, image_mtime_ns=199)

def test_artifact_cannot_escape_campaign_root(store, foreign_file):
    with pytest.raises(ArtifactAccessError):
        store.register_file(foreign_file, "image/png", campaign_id="campaign-1")

def test_linux_validation_cli_uses_brokered_capture_not_mac_adapter(cli, broker):
    result = cli.run(platform="linux", process_owner=broker)
    assert result.capture_adapter == "gnome"
    assert broker.requests[-1].role == "capture"
    assert "MacViewerCapture" not in result.imported_types
```

- [ ] **Step 2: 运行 RED。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_capture.py \
  src/so101_teleop/test/teleop/test_task_artifacts.py \
  src/so101_demo_py/test/test_viewer_capture.py \
  src/so101_demo_py/test/test_mujoco_rgbd_batch_cli.py -q
```

- [ ] **Step 3: 实现 adapter factory。**

```python
def capture_adapter(platform: str, process_owner: ProcessOwnerPort) -> ViewerCapture:
    if platform == "linux":
        return GnomeViewerCapture(process_owner)
    if platform == "darwin":
        return MacViewerCapture(process_owner)
    raise CaptureError("VIEWER_CAPTURE_PLATFORM_UNSUPPORTED")
```

GNOME adapter 从本次 attempt 的 MuJoCo PID 查窗口，记录 window ID、PID start time、capture start/end 和 manifest；macOS 保留现有窗口选择规则。`mujoco_rgbd_batch.py` 删除顶层硬编码的 `MacViewerCapture.from_package(...)`，改为从 Task 5 的 broker token 构造 `BrokeredViewerCapture`；supervisor 根据平台选择 GNOME 或 macOS adapter 并拥有平台工具进程。无 broker 的旧 CLI 才在本地调用 `capture_adapter(sys.platform, ...)`。batch 不直接启动截图工具，也不复用旧图片。

- [ ] **Step 4: 运行 GREEN。**

```zsh
validation_pytest src/so101_teleop/test/teleop/test_expert_validation_capture.py \
  src/so101_teleop/test/teleop/test_task_artifacts.py \
  src/so101_demo_py/test/test_viewer_capture.py \
  src/so101_demo_py/test/test_mujoco_rgbd_batch_cli.py -q
```

- [ ] **Step 5: Commit。**

```zsh
git add src/so101_teleop/so101_teleop/expert_validation/capture.py \
  src/so101_teleop/test/teleop/test_expert_validation_capture.py \
  src/so101_teleop/so101_teleop/task_artifacts.py \
  src/so101_teleop/test/teleop/test_task_artifacts.py \
  src/so101_demo_py/src/runtime/viewer_capture.py \
  src/so101_demo_py/test/test_viewer_capture.py \
  src/so101_demo_py/src/cli/mujoco_rgbd_batch.py \
  src/so101_demo_py/test/test_mujoco_rgbd_batch_cli.py
git commit -m "feat: capture validation evidence across platforms"
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

`create_expert_validation_app(service, static_dir)` 只接受 loopback 或 Tailscale CGNAT bind。实现设计中列出的 13 个 HTTP/WebSocket endpoints。artifact route 通过 registry 打开 opaque ID，拒绝 absolute client path、`..`、symlink、跨 campaign 和 hash mismatch。WebSocket 只推 journal 已接受的 sequence；reconnect 后客户端先 GET campaign。现有 `create_app()` 只新增只读 unavailable capability route，不获得 supervisor、lease 或进程控制引用，原 `/tasks` 行为保持不变。

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
```

- [ ] **Step 2: 运行 RED。**

```zsh
validation_web run test \
  src/api/expert-validation-client.test.ts \
  src/state/expert-validation-store.test.ts
```

- [ ] **Step 3: 实现 client 与 store。**

`expert-validation-types.ts` 只从生成的 `expert-validation-schema.d.ts` 提取 aliases，禁止再手写第二份 wire schema。生成契约必须闭合列出 manifest geometry、point states、attempts、statistics、lease、artifact、safety receipt 和 campaign state。client 对非 2xx machine-readable error 保留 `code`；store 丢弃 `sequence <= current` 的 hint，并在 sequence gap 时重新 GET campaign。

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
  ["PENDING", "blue"], ["RUNNING", "blue"], ["SUCCEEDED", "green"],
  ["FAILED", "red"], ["INVALID", "red"], ["NOT_RUN", "red"], ["BLOCKED", "red"],
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

使用一个 viewBox 和单一 equal-scale transform。绘制 table/grid、方形 base、base origin、target center、target region、target tolerance 虚线圆、P01 cup footprint 虚线圆和全部等半径点位。`RUNNING` 只加粗蓝色 stroke；selection 只增加外 focus ring。每个 point 是可键盘选择的 `<button>` 等价 SVG 元素，并提供完整 aria label。

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
  renderCampaign(points("SUCCEEDED", "FAILED", "INVALID", "BLOCKED"));
  expect((screen.getByLabelText("Retry P02") as HTMLInputElement).disabled).toBe(false);
  expect((screen.getByLabelText("Retry P01") as HTMLInputElement).disabled).toBe(true);
  expect((screen.getByLabelText("Retry P03") as HTMLInputElement).disabled).toBe(true);
  expect((screen.getByLabelText("Retry P04") as HTMLInputElement).disabled).toBe(true);
});
```

再覆盖 count 3/21、default seed、lease required、map/list shared selection、separate first-pass/retry statistics、recovery lockout、inline image media types、opaque download URL 和 exact confirmation。

- [ ] **Step 2: 运行 RED。**

```zsh
validation_web run test src/expert-validation-app.test.tsx \
  src/components/expert-validation/components.test.tsx
```

- [ ] **Step 3: 实现页面布局。**

左侧固定 `TopViewMap`，右侧显示 campaign state、evaluation/execution coverage、qualified first-pass fraction、current point、first shared failure 和 lifecycle。selected point panel 按时间显示 first pass 与 retry attempts；支持 RGB/Viewer/point-cloud preview inline，PLY/JSON/log 下载。

- [ ] **Step 4: 实现 lease 与 retry。**

页面加载取得 stable service session，再显式 acquire lease 并按 capabilities 周期 renew。browser disconnect 不发送 release。retry modal 要求用户输入 `CONFIRM FULL_RESTART RETRIES`，只发送当前 campaign 中选中的 `FAILED` 或 `SKIPPED_UNREACHABLE` IDs。

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
test("restores a campaign and retries a failed point", async ({ page }) => {
  const fake = await installFakeSupervisor(page, campaignWithFailedP09());
  await page.goto("/expert-validation");
  await expect(page.getByLabel("P09 FAILED")).toBeVisible();
  await page.getByLabel("Retry P09").check();
  await page.getByRole("button", { name: "Retry selected with FULL_RESTART" }).click();
  await page.getByLabel("Confirmation").fill("CONFIRM FULL_RESTART RETRIES");
  await page.getByRole("button", { name: "Confirm retry" }).click();
  expect(fake.lastRetryBody.point_ids).toEqual(["sample_05_near_center"]);
  await expect(page.getByText("FULL_RESTART attempt 2")).toBeVisible();
});
```

- [ ] **Step 2: 运行 RED。**

```zsh
validation_web run build
validation_web run test:e2e -- e2e/expert-validation.spec.ts
```

- [ ] **Step 3: 完成 build/install checks。**

package layout 必须证明 sampler configs、projection fixture、server executable 和 SPA route 均安装。`so101_demo_py/setup.py` 已用 `find_packages(where="src")` 自动安装新增 modules；Task 6 只为新增 `task_shutdown_safety` console script 修改它。CMake 逐个注册 Tasks 1-11 新增的 Python test files，其中必须包括 `test_expert_validation_process_owner_integration.py`。layout test 对注册集合做 readback，避免本地 pytest 通过而 colcon gate 漏测。

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

### Task 16: 在 ai-station 做隔离 build、4 点 smoke 和 20 点首轮

**Files:**

- Create: `docs/experiments/so101-moveit-expert-validation-web-experiment-ledger.md`
- Modify: the same ledger after every experiment and checkpoint

**Interfaces:**

- Consumes: clean implementation commit, one durable evidence root, no active SO-101 stack.
- Produces: installed-runtime provenance, package results, fresh campaign manifests, per-point evidence and process cleanup receipts.

- [ ] **Step 1: 冻结 PLANNED entries。**

账本先写 `EXP-001` package gate、`EXP-002` 4-point smoke、`EXP-003` 20-point first pass。每条分别写 commit、overlay、runtime executable、`ROS_DOMAIN_ID`、`GZ_PARTITION`、成功/失败/invalid 判据和唯一变量。不要复用正在运行的 `codex-19` checkout 或进程。

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

生成 `total_points=4, seed=20260911`，取得 lease，启动 first pass。必须从页面看到进度，并逐点核对 fresh RGB/Viewer、输入 stamp、MoveIt plan/execute、controller/joint/TF、MuJoCo lift/transport/release/final pose/contact、Planning Scene attached/world 和 cleanup。任何 provenance/reset 污染将 `EXP-002` 标为 `INVALID`，不得继续混算。

- [ ] **Step 6: 通过页面执行精确 20 点首轮。**

生成 `ai_station_baseline_v1` manifest，核对 20 点坐标和 manifest hash后启动。保存 requested/evaluated/execution_started/valid_succeeded/valid_failed/invalid/not_executed、两种 coverage、qualified success rate、首坏阶段与每点 artifact IDs。首轮只用一个 fresh stack 和点间 `RESET_WORLD`。

- [ ] **Step 7: 写 checkpoint。**

账本记录 retained root、scratch deletion candidates、无 archived run、owned process cleanup、剩余风险和下一条精确命令。未获用户授权不删除任何证据。

### Task 17: 验证失败点 FULL_RESTART、视觉结果和最终边界

**Files:**

- Modify: `docs/experiments/so101-moveit-expert-validation-web-experiment-ledger.md`

**Interfaces:**

- Consumes: Task 16 的 fresh terminal campaign。
- Produces: 至少一个 eligible failure 的页面重试证据，或明确的 `LIVE_RETRY_NOT_APPLICABLE_ALL_SUCCEEDED`，以及最终交付报告。

- [ ] **Step 1: 冻结 retry experiment。**

若首轮有 `FAILED` 或 `SKIPPED_UNREACHABLE`，为最早 eligible point 建 `EXP-004`，`lifecycle: FULL_RESTART`，记录 canonical point ID、display ID 与首坏边界。若全部有效点成功，不制造失败，记录 `LIVE_RETRY_NOT_APPLICABLE_ALL_SUCCEEDED`；同时把 Task 16 的 Linux real-process integration JUnit、store-reopen reconciliation 和 cleanup-before-next-start assertions 登记为 restart/cleanup 证据，再跳到 Step 4。fake owner 或 Playwright 不能替代这组证据。

- [ ] **Step 2: 从页面执行 retry。**

选中点位，输入 `CONFIRM FULL_RESTART RETRIES`。证明新 attempt ID、simulation session、ROS domain、stack PGID、batch PGID、worker PGIDs 和 evidence child 均与首轮不同。开始下一 attempt 前，前一 attempt 的 cleanup receipt 必须落盘且 descendants/ROS graph 已消失。

- [ ] **Step 3: 核对 retry 不改首轮统计。**

GET campaign readback 必须保持首轮 numerator、denominator 和 point receipt 不变；retry 在独立 attempt list 中。cleanup ambiguity、held cup 或 stale receipt 必须进入 `NEEDS_OPERATOR_RECOVERY`，不得自动 signal 或启动下一 stack。

- [ ] **Step 4: 做 fresh visual acceptance。**

使用 `$gui-capture` 执行 `snapshot -> action -> fresh snapshot`，打开新截图并描述 robot pose、gripper、cup initial/final pose、穿透/掉落、target tolerance 和 Planning Scene 一致性。截图不能替代数值与 action/physics evidence。

- [ ] **Step 5: 最终 readback。**

```zsh
git rev-parse HEAD
git status --short
ros2 pkg prefix so101_demo_py
ros2 pkg prefix so101_teleop
curl --fail http://127.0.0.1:8010/health
ps -eo pid,pgid,cmd | rg '(move_group|mujoco|so101_expert_validation|so101_mujoco_rgbd_batch)' || true
```

停止 validation server 前先确认没有 active attempt，并保存 server 自身退出与清理记录。不得停止用户的 `codex-19` 或其他未登记进程。

- [ ] **Step 6: 写最终账本 checkpoint。**

报告 manifest ID/hash、commit/overlay/runtime provenance、4 点 smoke、20 点首轮、retry、first-bad-boundary、artifact hashes、ROS/process cleanup、retained/archived/deletion candidates 和未解决风险。明确区分实现完成、package test、仿真 runtime 与 ACT 未实现边界。

- [ ] **Step 7: Commit 实验账本。**

```zsh
git add docs/experiments/so101-moveit-expert-validation-web-experiment-ledger.md
git commit -m "docs: record expert validation acceptance"
```

## 最终验收清单

- [ ] `ai_station_baseline_v1` 精确复现 20 点；`geometry_v2` 仍为独立 35 mm profile。
- [ ] Python 和 React 对 table/base/target/P01/20 点投影、半径与颜色的 golden tests 一致。
- [ ] progress log 的 manifest/event/journal 顺序通过 crash-window tests；snapshot 可删除重建。
- [ ] API、journal、store 和 retry command 只使用 canonical point ID；`P01` 至 `P20` 只用于展示。
- [ ] stack 在 batch 前产生完整 `ReadinessReceipt`；每个 `FULL_RESTART` retry 还产生有效 `InitialStateReceipt`。
- [ ] normal point cleanup 只停止该点 worker PGIDs，长生命周期 batch 能继续下一个点。
- [ ] validation batch 的 `Popen`、one-shot command、poll、signal 和 capture 均通过 broker；没有 direct `subprocess.run` 或 `killpg` 旁路。
- [ ] Linux real-process integration gate 实际执行非零 tests，并通过 descendant、barrier、ack、reopen 和 serial cleanup cases。
- [ ] 所有 exit path 产生 fresh shutdown receipt 或进入 `NEEDS_OPERATOR_RECOVERY`。
- [ ] command idempotency、lease restart/expiry、browser disconnect 和 singleton lock 均通过测试。
- [ ] terminal campaign 没有 `PENDING`/`RUNNING`，unreachable 和 interrupted points 的统计符合设计。
- [ ] `/expert-validation` 页面支持生成、开始、进度、选择、证据和 confirmed retry；`/tasks` 在 dedicated server 上禁用。
- [ ] Web tests、Playwright、两个 Python package gates 均收集非零测试且无新增 failure/error。
- [ ] ai-station 使用 task-owned overlay、fresh source、独立 ROS domain/GZ partition 和 registered durable evidence root。
- [ ] fresh GUI 截图与 Gazebo/MoveIt/controller/pose/contact 数值证据共同通过。
- [ ] 无 duplicate stack、未知 descendants 或失控后台进程；未触碰用户已有 ai-station 改动与 `codex-19`。
- [ ] retained、archived 和 deletion candidates 已分类，且没有未经授权删除证据。

## 执行选择

计划执行时使用以下一种方式：

1. **Subagent-Driven（推荐）**：按 Task 派发 fresh subagent，每个 Task 完成后先做 spec compliance review，再做 code-quality review。
2. **Inline Execution**：在当前 session 使用 `superpowers:executing-plans`，按批次 A、B、C、D 执行并在每批结束时停下复核。
