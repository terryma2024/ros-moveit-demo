# SO-101 MoveIt Expert Adaptive Worker Pool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 ai-station 上实现轻量自适应 Worker 池：优先运行 W8，发生基础设施故障时按 `W8 → W6 → W4 → W2 → W1` 缩容，保留已完成点并完成同一批 20 点回归。

2026-09-15 的扩展把显式请求上限设为 W16，并把 Domain 池扩展到 `215..230`。默认仍是 W8，
默认降级序列不变；W10 只在单独登记的实验中运行，不能据此声称 W16 已通过现场测试。

**Architecture:** 从 `origin/main` 的 v1 `ParallelBatchCoordinator` 新建干净实现分支。顶层 `AdaptiveBatchRunner` 跨 pool generation 保存点位终态和 fallback journal；每个档位复用现有 Coordinator、Worker、Broker、初始状态门控和精确进程清理。自适应扩展全部由显式 `--adaptive-workers` 开启，旧的 `--max-points-per-worker` 和 v1 资源门保持原行为。

**Tech Stack:** Python 3.12、ROS 2 Jazzy、MuJoCo、MoveIt 2、pytest、colcon、YAML/JSONL、Unix socket、Linux process group、Fast DDS ROS Domain claim、Docker PerceptionBroker。

**Spec:** `docs/superpowers/specs/2026-09-14-so101-adaptive-worker-pool-design.md`

## Global Constraints

- 只实现 MuJoCo MoveIt 专家模式；不运行实体机械臂，不扩展 Gazebo 并发。
- 实现 worktree 固定为 `/data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool`，分支固定为 `codex/parallel-adaptive-worker-pool`。
- 从包含本设计和计划的最新 `origin/main` 建立新 worktree。不得在旧的 `/data/work/ws_moveit/.worktrees/parallel-w8-admission-v2` 上继续实现。
- 旧 W8 worktree 的 HEAD `2d13ae65490cf1eccfd57fa683e4b13b41784402`、26 个实现提交、未跟踪的 `src/so101_demo_py/test/test_parallel_admission.py` 和 `/data/work/so101-evidence/parallel-w8/20260913-q01` 全部只读保留。
- 新任务只使用一个 durable evidence root：`/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01`。普通日志、测试 scratch、现场运行和性能子批次都放在它下面。
- ai-station 上每次 pytest/colcon 前创建从未存在的 `scratch/<test-run-id>/tmp`，设置 `TMPDIR`、`TMP`、`TEMP`，并由实际测试 Python 回读 `tempfile.gettempdir()`；用过的 scratch 只列为删除候选。
- 所有测试 shell 先 `set -euo pipefail`。RED、GREEN、复跑和 final gate 使用不同 test-run-id；任何
  `test ! -e "$scratch"` 失败都立即停止，不能复用旧 scratch。每次记录开始/结束 monotonic 时间和
  elapsed time。
- 自适应模式必须显式传 `--adaptive-workers`、`--config ...parallel_batch_v1.yaml` 和 `--adaptive-config ...parallel_adaptive_workers_v1.yaml`。
- 默认降级序列是 `W8 → W6 → W4 → W2 → W1`；只有启动、进程、ROS/Broker 通信、OOM 或恢复/清理故障触发降级。
- 显式 `worker_count` 支持 `1..16`，省略时仍使用 W8；Broker handler、每模型队列和精确清理必须使用同一上限。
- 点位感知、IK、规划、碰撞、抓取、释放和放置失败是业务失败，提交 `FAILED` 后继续当前档位。
- `initial_points_per_worker` 只控制初始亲和，不是硬容量；空闲 Worker 可以抢任何尚未 lease 的点。
- 每个点开始前必须通过现有 `point_initial_gate` 的状态读回。不得用 reset 调用成功或 `DONE` 日志代替初始状态、动作和物理结果证据。
- YOLO-Seg 始终优先；只有尚无 `POSE_ACCEPTED` 的允许感知失败才调用 Grounded-SAM。Broker/CUDA/RPC 故障不触发模型回退。
- 资源指标只采样，不做 CPU/GPU/RAM/PSI/RTF 阈值准入；已经发生的 OOM、GPU 服务失效和通信中断仍算基础设施故障。
- 只按登记的 PID、PGID、start ticks、Domain claim、session、socket 和容器 ID 清理。禁止宽泛 `pkill -f`、`killall`、共享 tmux 清理或模糊容器匹配。
- 不运行 `ament_uncrustify --reformat`。普通包测试只收集 `src/so101_demo_py/test/`，不隐式收集 `benchmark_test/`。
- 每个任务先 RED、再最小实现、再 GREEN，并单独提交。计划完成前不 push、不 merge、不删除证据。

## File Structure

新文件：

- `src/so101_demo_py/config/mujoco/parallel_adaptive_workers_v1.yaml`：轻量 Worker 档位、Domain 池和超时默认值。
- `src/so101_demo_py/src/parallel_batch/adaptive_contracts.py`：自适应请求、档位、失败、transition 和 summary 类型。
- `src/so101_demo_py/src/parallel_batch/adaptive_queue.py`：初始 preferred deque 与动态抢任务。
- `src/so101_demo_py/src/parallel_batch/adaptive_runner.py`：跨 pool generation 的点位权威状态、journal 和降级循环。
- `src/so101_demo_py/src/parallel_batch/adaptive_pool.py`：v1 production composition 到 `PoolExecutionResult` 的适配层。
- `src/so101_demo_py/src/cli/parallel_batch_cleanup.py`：Runner 异常退出后的精确 owned-process 收敛入口。
- `src/so101_demo_py/test/test_parallel_adaptive_contracts.py`：配置、请求和 CLI 兼容契约。
- `src/so101_demo_py/test/test_parallel_adaptive_queue.py`：初始分配和动态抢任务。
- `src/so101_demo_py/test/test_parallel_adaptive_runner.py`：业务失败、基础设施中断和完整降级链。
- `src/so101_demo_py/test/test_parallel_adaptive_pool.py`：READY barrier、资源分配、进程退出和 pool 结果导出。
- `src/so101_demo_py/test/test_parallel_adaptive_integration.py`：CLI、journal、精确清理和 fallback 集成测试。
- `scripts/run_so101_adaptive_worker_scaling.zsh`：默认 W1/W2/W4/W6/W8 性能驱动，也接受单独登记的 W9–W16 显式实验。
- `scripts/run_so101_adaptive_batch.zsh`：持有 Runner 子进程并在异常退出后调用精确清理入口。
- `docs/experiments/so101-parallel-adaptive-worker-pool-experiment-ledger.md`：唯一长程实验账本。

受控修改：

- `src/so101_demo_py/src/cli/mujoco_parallel_batch.py`：显式自适应 CLI、READY control RPC、pool factory、summary 输出。
- `src/so101_demo_py/src/parallel_batch/coordinator.py`：默认关闭的 point selector 注入点。
- `src/so101_demo_py/src/parallel_batch/resources.py`：默认保持 v1 的 `AllocationPolicy` 注入点；自适应模式跳过资源阈值但保留 Domain/目录隔离。
- `src/so101_demo_py/src/parallel_batch/broker.py`：允许自适应 pool 把每模型队列容量设为当前 Worker 数。
- `src/so101_demo_py/src/cli/parallel_perception_broker.py`：读取经过校验的 pool 队列容量。
- `src/so101_demo_py/src/runtime/parallel_processes.py`：可选的首个非零 Worker 退出回调；默认等待行为不变。
- `src/so101_demo_py/setup.py`：安装 `so101_parallel_batch_cleanup` 入口。
- `src/so101_demo_py/test/test_parallel_batch_cli.py`、`test_parallel_batch_coordinator.py`、`test_parallel_batch_resources.py`、`test_parallel_batch_broker.py`、`test_parallel_processes.py`：冻结 v1 兼容性并覆盖注入点。

---

### Task 1: 建立隔离实现基线和自适应契约

**Files:**
- Create: `src/so101_demo_py/config/mujoco/parallel_adaptive_workers_v1.yaml`
- Create: `src/so101_demo_py/src/parallel_batch/adaptive_contracts.py`
- Create: `src/so101_demo_py/test/test_parallel_adaptive_contracts.py`
- Create: `docs/experiments/so101-parallel-adaptive-worker-pool-experiment-ledger.md`

**Interfaces:**
- Consumes: v1 `RunMode`, `PointStatus` 和 `_require_*` 风格的严格校验规则。
- Produces: `AdaptiveWorkerOptions`, `AdaptiveBatchRequest`, `PoolRequest`, `InfrastructureFailure`, `FallbackTransition`, `PoolExecutionResult`, `AdaptiveBatchSummary`, `load_adaptive_worker_options(path)`。

- [ ] **Step 1: 用 worktree skill 建立新分支并登记现场快照**

先使用 `superpowers:using-git-worktrees`。在 ai-station 本机执行，不得 SSH 自身：

```zsh
cd /data/work/ws_moveit
git fetch origin
git show origin/main:docs/superpowers/specs/2026-09-14-so101-adaptive-worker-pool-design.md >/dev/null
git show origin/main:docs/superpowers/plans/2026-09-14-so101-adaptive-worker-pool-implementation.md >/dev/null
test ! -e /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool
git worktree add -b codex/parallel-adaptive-worker-pool \
  /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool origin/main
cd /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool
hostname
pwd
git rev-parse HEAD
git branch --show-current
git status --short
git submodule status
test "$(git -C /data/work/ws_moveit/.worktrees/parallel-w8-admission-v2 rev-parse HEAD)" = \
  2d13ae65490cf1eccfd57fa683e4b13b41784402
test -f /data/work/ws_moveit/.worktrees/parallel-w8-admission-v2/src/so101_demo_py/test/test_parallel_admission.py
```

预期：新 worktree 干净；旧 worktree 的 HEAD 和未跟踪文件均未变化。创建并登记唯一证据根：

```zsh
test ! -e /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01
mkdir -p /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/scratch
chmod 700 /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01
```

- [ ] **Step 2: 写自适应配置和请求的失败测试**

在 `test_parallel_adaptive_contracts.py` 写入以下核心断言：

```python
def test_default_options_form_the_frozen_fallback_ladder():
    options = load_adaptive_worker_options(CONFIG)
    assert options.worker_count == 8
    assert options.levels == (8, 6, 4, 2, 1)
    assert options.initial_points_per_worker == 3
    assert options.worker_start_timeout_s == 120.0
    assert options.max_infra_attempts_per_point == 5
    assert options.ros_domain_ids == tuple(range(215, 231))


def test_initial_chunk_is_not_a_capacity_gate(tmp_path):
    request = AdaptiveBatchRequest(
        batch_id="at01",
        run_mode=RunMode.EXECUTE,
        selected_point_ids=tuple(f"p{number:02d}" for number in range(20)),
        options=load_adaptive_worker_options(CONFIG),
        evidence_root=tmp_path,
    )
    assert request.point_count == 20
    assert request.options.worker_count * request.options.initial_points_per_worker == 24
```

再覆盖布尔值、零值、重复/升序 fallback、W17、Domain 数不足、未知 YAML 字段和相对 evidence root。
从 W1 启动时允许 `fallback_worker_counts=()`；`levels` 仍包含首选档位，因此序列不会为空。

- [ ] **Step 3: 运行 RED**

```zsh
set -euo pipefail
cd /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool
scratch=/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/scratch/task-01-red/tmp
test ! -e "$scratch"
mkdir -p "$scratch"
export TMPDIR="$scratch" TMP="$scratch" TEMP="$scratch"
python_bin=/usr/bin/python3
test -x "$python_bin"
"$python_bin" -c 'import tempfile; print(tempfile.gettempdir())' | \
  rg '^/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/scratch/task-01-red/tmp$'
PYTHONNOUSERSITE=1 "$python_bin" -m pytest -p no:cacheprovider \
  src/so101_demo_py/test/test_parallel_adaptive_contracts.py -q
```

预期：导入 `so101_demo.parallel_batch.adaptive_contracts` 失败。

- [ ] **Step 4: 实现严格类型和配置**

`adaptive_contracts.py` 的公开骨架固定为：

```python
class BatchTerminalStatus(StrEnum):
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_FAILURES = "COMPLETED_WITH_FAILURES"
    INFRA_FAILED = "INFRA_FAILED"


class InfrastructureFailureKind(StrEnum):
    STARTUP = "STARTUP"
    PROCESS_EXIT = "PROCESS_EXIT"
    ROS_DISCONNECTED = "ROS_DISCONNECTED"
    BROKER_DISCONNECTED = "BROKER_DISCONNECTED"
    OOM = "OOM"
    RECOVERY = "RECOVERY"
    CLEANUP = "CLEANUP"
    COORDINATOR = "COORDINATOR"


@dataclass(frozen=True, slots=True)
class AdaptiveWorkerOptions:
    worker_count: int
    fallback_worker_counts: tuple[int, ...]
    initial_points_per_worker: int
    worker_start_timeout_s: float
    max_infra_attempts_per_point: int
    ros_domain_ids: tuple[int, ...]

    @property
    def levels(self) -> tuple[int, ...]:
        return (self.worker_count, *self.fallback_worker_counts)


@dataclass(frozen=True, slots=True)
class AdaptiveBatchRequest:
    batch_id: str
    run_mode: RunMode
    selected_point_ids: tuple[str, ...]
    options: AdaptiveWorkerOptions
    evidence_root: Path

    @property
    def point_count(self) -> int:
        return len(self.selected_point_ids)


@dataclass(frozen=True, slots=True)
class PoolRequest:
    """Internal one-generation request; never accepted directly from legacy CLI."""
    batch_id: str
    run_mode: RunMode
    selected_point_ids: tuple[str, ...]
    worker_count: int
    max_points_per_worker: int
    evidence_root: Path
```

同文件另行定义不可变的 `InfrastructureFailure`、`FallbackTransition`、
`CommittedPointResult`、`PoolExecutionResult` 和 `AdaptiveBatchSummary`。所有路径必须为绝对路径；
所有 ID 必须匹配 `[A-Za-z0-9][A-Za-z0-9_-]*`；所有浮点值必须有限。`PoolRequest` 与 v1
`BatchRequest` 共享 Coordinator 所需字段和 `asdict()` 形状，但单独校验 Worker 为 1–16、点数不超过
20，且只允许 `ProductionAdaptivePoolFactory` 构造；不得放宽或继承 v1 `BatchRequest` 的 W3 冻结
上限。自适应顶层 `batch_id` 同时作为 run ID，限制为 1–5 个 ASCII ID 字符；其 runtime root
确定为 `evidence_root / "r" / batch_id`。

配置文件写入：

```yaml
schema_version: 1
backend: mujoco
worker_count: 8
fallback_worker_counts: [6, 4, 2, 1]
initial_points_per_worker: 3
worker_start_timeout_s: 120.0
max_infra_attempts_per_point: 5
ros_domain_ids: [215, 216, 217, 218, 219, 220, 221, 222, 223, 224, 225, 226, 227, 228, 229, 230]
```

- [ ] **Step 5: 使用新 scratch 运行 GREEN，并建立账本头部**

不得复用 RED scratch。把 Step 3 的 `scratch` 改为
`.../scratch/task-01-green/tmp`，重新执行 `test ! -e`、创建、三个 temp export 和实际 Python 的
`tempfile.gettempdir()` 回读，再运行相同 pytest；记录 RED/GREEN 各自 elapsed time。预期全部通过。
建立实验账本，写入实际 `git rev-parse HEAD`、分支、worktree、唯一
evidence root、旧分支只读约束和 checkpoint `CP-001`。`next_experiment` 写 `EXP-001`，状态
`PLANNED`，主题是自适应 CLI/contract 自动化验证。

- [ ] **Step 6: 提交契约**

```zsh
git add -- \
  src/so101_demo_py/config/mujoco/parallel_adaptive_workers_v1.yaml \
  src/so101_demo_py/src/parallel_batch/adaptive_contracts.py \
  src/so101_demo_py/test/test_parallel_adaptive_contracts.py \
  docs/experiments/so101-parallel-adaptive-worker-pool-experiment-ledger.md
git diff --cached --check
git commit -m "feat: define adaptive worker pool contracts"
```

### Task 2: 增加显式自适应 CLI，冻结 v1 兼容性

**Files:**
- Modify: `src/so101_demo_py/src/cli/mujoco_parallel_batch.py`
- Modify: `src/so101_demo_py/test/test_parallel_batch_cli.py`
- Modify: `src/so101_demo_py/test/test_parallel_adaptive_contracts.py`

**Interfaces:**
- Consumes: `AdaptiveWorkerOptions`, `AdaptiveBatchRequest`, `load_adaptive_worker_options()`。
- Produces: `PreparedBatch.adaptive_request: AdaptiveBatchRequest | None`；`PreparedBatch.request` 改为
  `BatchRequest | None`，但旧模式运行时仍始终填入原 `BatchRequest`，序列化内容不变。

- [ ] **Step 1: 写 CLI RED 测试**

添加两个 argv helper，分别产生旧模式和自适应模式。核心断言：

```python
def test_adaptive_cli_requires_its_own_initial_chunk_flag(tmp_path):
    prepared = prepare_batch(adaptive_argv(tmp_path), provenance_verifier=verified)
    assert prepared.adaptive_request is not None
    assert prepared.adaptive_request.options.levels == (8, 6, 4, 2, 1)
    assert prepared.request is None


def test_adaptive_cli_rejects_legacy_hard_capacity_flag(tmp_path):
    with pytest.raises(CliError, match="ADAPTIVE_MAX_POINTS_CONFLICT"):
        prepare_batch(
            adaptive_argv(tmp_path) + ["--max-points-per-worker", "3"],
            provenance_verifier=verified,
        )
```

保留现有旧模式 helper，断言不传 `--adaptive-workers` 时 `--max-points-per-worker` 默认仍为 10，
W4 仍由 v1 `MAX_WORKER_COUNT` 拒绝。

- [ ] **Step 2: 运行 RED**

使用新的 `scratch/task-02-red/tmp` 运行：

```zsh
PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider \
  src/so101_demo_py/test/test_parallel_adaptive_contracts.py \
  src/so101_demo_py/test/test_parallel_batch_cli.py -q
```

预期：parser 不认识 `--adaptive-workers`。

- [ ] **Step 3: 最小修改 parser 和 `PreparedBatch`**

给 parser 增加：

```python
parser.add_argument("--adaptive-workers", action="store_true")
parser.add_argument("--adaptive-config", type=Path)
parser.add_argument("--fallback-worker-counts")
parser.add_argument("--initial-points-per-worker")
parser.add_argument("--worker-start-timeout-s")
parser.add_argument("--max-infra-attempts-per-point")
```

把 `--max-points-per-worker` 和 `--worker-count` 的 parser 默认值都改为 `None`，只在旧模式解析
阶段分别回填字符串 `"10"` 和 `"2"`。自适应模式省略 `--worker-count` 时采用 adaptive YAML 的
W8；增加两条兼容测试，分别证明旧模式省略后仍是 W2、自适应模式省略后是 W8。
自适应模式要求 `--adaptive-config`，拒绝 `--resume`、`--max-points-per-worker` 和旧三 Worker
live-headroom 参数。命令行提供的 Worker 数、fallback、K 和 timeout 覆盖 adaptive YAML 默认值，
覆盖后的完整 options 写入 manifest。未显式提供 fallback 时，只保留 YAML 中严格小于首选
`worker_count` 的档位，因此 W6 得到 `(6,4,2,1)`，W1 得到 `(1,)`；显式列表包含大于等于首选
档位的值则拒绝。

`PreparedBatch` 改为：

```python
request: BatchRequest | None
adaptive_request: AdaptiveBatchRequest | None
config: ParallelRuntimeConfig
adaptive_config_path: Path | None
```

旧模式的 manifest bytes、journal request identity 和 `prepare_batch()` 结果不得改变。

- [ ] **Step 4: GREEN 和旧模式回归**

运行 Task 2 两个测试文件，随后运行：

```zsh
PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider \
  src/so101_demo_py/test/test_parallel_batch_contracts.py \
  src/so101_demo_py/test/test_parallel_batch_journal.py \
  src/so101_demo_py/test/test_parallel_batch_crash_recovery.py -q
```

预期：新测试和旧 v1 journal/CLI 测试全部通过。

- [ ] **Step 5: 提交 CLI 契约**

```zsh
git add -- src/so101_demo_py/src/cli/mujoco_parallel_batch.py \
  src/so101_demo_py/test/test_parallel_batch_cli.py \
  src/so101_demo_py/test/test_parallel_adaptive_contracts.py
git diff --cached --check
git commit -m "feat: add explicit adaptive worker CLI"
```

### Task 3: 实现初始亲和和动态抢任务

**Files:**
- Create: `src/so101_demo_py/src/parallel_batch/adaptive_queue.py`
- Create: `src/so101_demo_py/test/test_parallel_adaptive_queue.py`
- Modify: `src/so101_demo_py/src/parallel_batch/coordinator.py`
- Modify: `src/so101_demo_py/test/test_parallel_batch_coordinator.py`

**Interfaces:**
- Consumes: Worker ID、稳定点位顺序和 Coordinator 当前 eligible 点集合。
- Produces: `AdaptivePointSelector.choose(worker_id, eligible_point_ids) -> str | None`；
  `BatchCoordinator(..., point_selector=None)`。

- [ ] **Step 1: 写 balanced preferred deque RED 测试**

```python
def test_twenty_points_seed_eight_workers_as_three_three_three_three_two_two_two_two():
    selector = AdaptivePointSelector(
        tuple(f"p{number:02d}" for number in range(1, 21)),
        tuple(f"worker-{number:02d}" for number in range(1, 9)),
        initial_points_per_worker=3,
    )
    assert tuple(map(len, selector.preferred.values())) == (3, 3, 3, 3, 2, 2, 2, 2)


def test_idle_worker_steals_an_unleased_point_after_its_preferred_deque_is_empty():
    selector = AdaptivePointSelector(("p1", "p2", "p3"), ("w1", "w2"), 1)
    assert selector.choose("w1", {"p1", "p2", "p3"}) == "p1"
    assert selector.choose("w1", {"p2", "p3"}) == "p3"
```

再写一个 Coordinator 测试，注入 selector 后由同一 Worker 连续领取超过 K 的点；默认 selector
为 `None` 时，现有 K 硬上限仍成立。

- [ ] **Step 2: 运行 RED**

在 `scratch/task-03-red/tmp` 下运行两个测试文件，预期缺少 `AdaptivePointSelector` 和 Coordinator
注入参数。

- [ ] **Step 3: 实现 selector 和默认关闭的注入点**

`AdaptivePointSelector` 使用 `threading.RLock`，构造时按“每轮遍历所有 Worker”的方式填充
preferred deque，随后保留 global deque。`choose()` 只返回调用时仍在 `eligible_point_ids` 中的点；
顺序固定为本 Worker preferred、global、其他 Worker 尾部、最后按原 catalog 顺序兜底。

`BatchCoordinator.__init__` 只增加一个可选参数：

```python
point_selector: Callable[[str, frozenset[str]], str | None] | None = None
```

selector 只在注入时取代现有 `next(...)`；旧路径一行不动。自适应路径在
`_grant_lease_outcome_locked()` 和 `_evaluate()` 两处都不把 `worker.lease_count >= K` 当容量耗尽，
判断依据是 selector 是否注入以及是否仍有 eligible 点；旧路径继续执行原 K 判断。测试必须覆盖
N×K 小于点数时不会提前得到 `CAPACITY_EXHAUSTED`。启动门不复用 Coordinator 的 Broker-recovery
pause wire schema；Worker 在全部 READY 前根本不会调用 grant RPC。

- [ ] **Step 4: GREEN 和并发 lease 回归**

运行 Task 3 测试，再运行：

```zsh
PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider \
  src/so101_demo_py/test/test_parallel_batch_coordinator.py \
  src/so101_demo_py/test/test_parallel_batch_fault_injection.py -q
```

预期：动态抢任务不产生重复 lease；默认 v1 顺序、K debit、deadline 和 fencing 全部通过。

- [ ] **Step 5: 提交调度器**

```zsh
git add -- src/so101_demo_py/src/parallel_batch/adaptive_queue.py \
  src/so101_demo_py/src/parallel_batch/coordinator.py \
  src/so101_demo_py/test/test_parallel_adaptive_queue.py \
  src/so101_demo_py/test/test_parallel_batch_coordinator.py
git diff --cached --check
git commit -m "feat: add adaptive point stealing"
```

### Task 4: 增加轻量资源策略和全部 Worker READY barrier

**Files:**
- Create: `src/so101_demo_py/src/parallel_batch/adaptive_pool.py`
- Create: `src/so101_demo_py/test/test_parallel_adaptive_pool.py`
- Modify: `src/so101_demo_py/src/parallel_batch/resources.py`
- Modify: `src/so101_demo_py/src/parallel_batch/worker.py`
- Modify: `src/so101_demo_py/src/runtime/parallel_ipc.py`
- Modify: `src/so101_demo_py/src/cli/mujoco_parallel_batch.py`
- Modify: `src/so101_demo_py/test/test_parallel_batch_resources.py`
- Modify: `src/so101_demo_py/test/test_parallel_batch_worker.py`
- Modify: `src/so101_demo_py/test/test_parallel_ipc.py`
- Modify: `src/so101_demo_py/test/test_parallel_batch_cli.py`

**Interfaces:**
- Consumes: `WorkerResourceAllocator`、worker control socket、`AdaptivePointSelector`。
- Produces: `AllocationPolicy`, `WorkerStartGate`, `WorkerReadinessReceipt`, `AdaptivePoolContext`；独立
  control RPC `readiness` 和 `release_start`。

- [ ] **Step 1: 写资源策略和 READY RED 测试**

核心断言：

```python
def test_observational_policy_allocates_eight_without_headroom_rejection(tmp_path):
    policy = AllocationPolicy(
        max_worker_count=8,
        ros_domain_ids=tuple(range(215, 223)),
        enforce_resource_thresholds=False,
    )
    allocator = WorkerResourceAllocator(
        CONFIG, tmp_path / "batch", probe=LowResourceProbe(),
        claim_root=tmp_path / "claims", allocation_policy=policy,
        batch_id="batch-a",
    )
    manifest = allocator.allocate(8)
    assert len(manifest.workers) == 8
    assert manifest.admission.admitted is True
    assert manifest.admission.failures == ()


def test_worker_cannot_request_a_lease_before_release_start():
    gate = WorkerStartGate(expected_worker_id="w1", generation=1)
    gate.record_readiness(valid_receipt("w1", generation=1))
    assert gate.wait_released(timeout_s=0.0) is False
    gate.release("w1", generation=1)
    assert gate.wait_released(timeout_s=0.0) is True
```

添加真实 control RPC 往返测试，并让请求经过 `WorkerTokenAuthority`：只为 token、Worker ID、
generation 和 coordinator epoch 都合法的 `readiness`/`release_start` 允许 `lease=None`；其他 operation
仍执行原 lease 检查。socket 尚未创建时 readiness 必须是 false；receipt 缺字段、过期、
Worker/generation 不符、Broker generation 不符或 Worker 在最终复核前退出都拒绝。一个 control 一直
未 READY 时，在 120 秒 fake clock deadline 报 `WORKER_READY_TIMEOUT`，且 Coordinator 从未收到
grant RPC。

- [ ] **Step 2: 运行 RED**

使用 `scratch/task-04-red/tmp` 运行新增测试和资源测试，预期缺少 `AllocationPolicy`、
`WorkerStartGate`。

- [ ] **Step 3: 实现 `AllocationPolicy`**

在 `resources.py` 定义：

```python
@dataclass(frozen=True, slots=True)
class AllocationPolicy:
    max_worker_count: int
    ros_domain_ids: tuple[int, ...]
    enforce_resource_thresholds: bool = True
    persistent_cleanup_claims: bool = False
```

`WorkerResourceAllocator(..., allocation_policy=None)` 的默认策略必须从 v1 config 生成，保持现有
资源阈值、三 Worker headroom 和 Domain 181–183。自适应策略使用 215–230，仍执行原子的 flock、
ROS Domain 冲突探测、私有目录创建和环境隔离；只跳过 `_resource_failures` 的拒绝。manifest 中
`admission.admitted=true`、`required=(0,0,0)`、`failures=()`，并保留 observed snapshot 供报告。
自适应策略同时启用 `persistent_cleanup_claims`：取得 flock 后先读取 claim record；若上一次记录仍是
`ACTIVE`，即使持锁 PID 已退出也报 `ROS_DOMAIN_UNCLEAN`，只有匹配批次的精确 cleanup receipt 能
把它改为 `RELEASED`。v1 策略保持 false，不改变既有 claim 语义。
如果失败发生在首个 owned process 启动前，allocator 可以写入带 `no_processes_started=true` 的回滚
receipt 后释放为 `RELEASED`；一旦登记过任何进程，就必须走 Task 8 的完整 cleanup gate。

- [ ] **Step 4: 实现 READY control 和 Worker 本地启动门**

`adaptive_pool.py` 定义：

```python
@dataclass(frozen=True, slots=True)
class WorkerReadinessReceipt:
    worker_id: str
    generation: int
    process_start_ticks: int
    coordinator_registered: bool
    runtime_ready: bool
    broker_ready: bool
    broker_generation: int
    observed_monotonic_s: float


class WorkerStartGate:
    def record_readiness(self, receipt: WorkerReadinessReceipt) -> None: ...
    def release(self, worker_id: str, generation: int) -> None: ...
    def wait_released(self, timeout_s: float) -> bool: ...


@dataclass(frozen=True, slots=True)
class AdaptivePoolContext:
    request: PoolRequest
    options: AdaptiveWorkerOptions
    selector: AdaptivePointSelector
```

自适应 worker spec 写入 `start_paused=true`。给 `ParallelWorker` 增加幂等
`prepare_for_start() -> bool`，只执行现有 `_register()` 与 `_ready()`，不领取 lease；普通 v1 路径不
调用它。内部 Worker 先 `prepare_for_start()`、启动独立 control server，再阻塞在本地
`WorkerStartGate`，因此此时不会调用 `grant_lease()`。释放后仍调用原 `run()`，其重复 register/ready
检查保持幂等。`readiness` RPC 必须用
专门的启动语义：control socket 不存在返回 false，不能复用 `_WorkerControlProxy.call()` 在关闭阶段
把缺失 socket 视作成功的分支。每份新鲜 receipt 同时证明：登记身份和进程 start ticks 未变、
`runtime.worker_ready_gate()` 为真、Broker health RPC 由该 Worker 成功往返且 generation 匹配。

composition 先收齐 N 份 receipt，再执行一次全量最终复核；全部仍有效后才逐个发送
`release_start`。receipt 的最大年龄冻结为 1.0 秒。最终复核通过后，composition 先把顶层
`POOL_RUNNING` 作为启动成功线性化点写入并 fsync，然后逐个放行 Worker。线性化点之前发生故障按
启动故障处理且保证零 lease；线性化点之后，包括第二个或后续 `release_start` 失败，都按运行中
基础设施故障处理，裁决可能已领取的在途点后降级。增加确定性测试：第一个 Worker 放行并领取
lease 后，第二个 release 失败，结果必须是 runtime fallback 而不是 startup-zero-lease。

`runtime/parallel_ipc.py` 的 lease-optional 白名单只增加 `readiness` 和 `release_start`；control
handler 仍校验专属 Worker identity，不能让其他 operation 绕过 lease。启动等待共用一个绝对
`worker_start_timeout_s` deadline，覆盖 control socket 出现、prepare、readiness、最终复核和 release；
自适应 `_start_workers()` 使用这个 deadline，旧 v1 仍保持 `heartbeat_timeout_s` 的五秒等待。测试
覆盖 control socket 在第六秒出现但仍在 120 秒预算内的成功路径。

- [ ] **Step 5: GREEN 和 v1 资源回归**

运行 Task 4 测试，再运行现有资源、Worker 和 CLI 测试。额外断言 v1 低资源 probe 仍失败、v1
W4 仍被拒绝、v1 Domain 仍为 181–183。

- [ ] **Step 6: 提交资源与 READY barrier**

```zsh
git add -- src/so101_demo_py/src/parallel_batch/adaptive_pool.py \
  src/so101_demo_py/src/parallel_batch/resources.py \
  src/so101_demo_py/src/parallel_batch/worker.py \
  src/so101_demo_py/src/runtime/parallel_ipc.py \
  src/so101_demo_py/src/cli/mujoco_parallel_batch.py \
  src/so101_demo_py/test/test_parallel_adaptive_pool.py \
  src/so101_demo_py/test/test_parallel_batch_resources.py \
  src/so101_demo_py/test/test_parallel_batch_worker.py \
  src/so101_demo_py/test/test_parallel_ipc.py \
  src/so101_demo_py/test/test_parallel_batch_cli.py
git diff --cached --check
git commit -m "feat: gate adaptive pools on worker readiness"
```

### Task 5: 实现跨档位权威状态和降级循环

**Files:**
- Create: `src/so101_demo_py/src/parallel_batch/adaptive_runner.py`
- Create: `src/so101_demo_py/test/test_parallel_adaptive_runner.py`

**Interfaces:**
- Consumes: `AdaptiveBatchRequest` 和 `pool_factory(PoolRequest) -> PoolExecutor`。
- Produces: `AdaptiveBatchRunner.run() -> AdaptiveBatchSummary`；追加式事件 `POOL_STARTING`, `POOL_RUNNING`, `POINT_RESULT_IMPORTED`, `POINT_INFRA_INTERRUPTED`, `POOL_DEGRADED`, `BATCH_TERMINAL`。

- [ ] **Step 1: 写 fake pool 的完整状态机 RED 测试**

至少写五个独立测试：

```python
def test_startup_failure_falls_from_w8_to_w6():
    pools = FakePools(startup_failure_levels={8})
    summary = runner(pools).run()
    assert summary.status is BatchTerminalStatus.COMPLETED
    assert summary.initial_worker_count == 8
    assert summary.final_worker_count == 6
    assert [(item.from_count, item.to_count) for item in summary.transitions] == [(8, 6)]


def test_business_failure_does_not_downgrade():
    pools = FakePools(failed_points={"p09"})
    summary = runner(pools).run()
    assert summary.status is BatchTerminalStatus.COMPLETED_WITH_FAILURES
    assert summary.final_worker_count == 8
    assert summary.transitions == ()


def test_midrun_failure_preserves_terminal_results_and_requeues_only_remaining():
    pools = FakePools(interrupt_at={8: {"passed": ("p01",), "failed": ("p09",), "active": ("p18",)}})
    summary = runner(pools).run()
    assert pools.requests[1].worker_count == 6
    assert "p01" not in pools.requests[1].point_ids
    assert "p09" not in pools.requests[1].point_ids
    assert "p18" in pools.requests[1].point_ids


def test_full_ladder_ends_in_infra_failed_after_w1_failure(): ...
def test_cleanup_failure_never_starts_the_next_pool(): ...
```

- [ ] **Step 2: 运行 RED**

在 `scratch/task-05-red/tmp` 运行 `test_parallel_adaptive_runner.py`，预期缺少 runner。

- [ ] **Step 3: 实现 append-only journal 和降级事务**

复用 `CoordinatorJournal` 的 append/fsync/replay，不引入数据库。runner 维护：

```python
self._terminal_results: dict[str, CommittedPointResult]
self._infra_attempts: dict[str, int]
self._transitions: list[FallbackTransition]
self._remaining: set[str]
```

每个现场 batch 使用 `AdaptiveBatchRequest.batch_id` 作为不超过 5 个 ASCII 字符的 run ID；runtime
root 固定为 `evidence_root / "r" / batch_id`，每级 pool root 固定为
`runtime_root / f"p/g{generation:02d}w{count:02d}"`。导入
`PASSED`/`FAILED` 前先验证 point ID 尚无终态；重复且相同的 committed event 幂等，不同结果
报 `TERMINAL_RESULT_CONFLICT`。在途点先写 `POINT_INFRA_INTERRUPTED`，增加 infra attempt，再进入
下一档。任何点达到 `max_infra_attempts_per_point` 后以 `INFRA_FAILED` 结束。

- [ ] **Step 4: GREEN 和 journal 重放测试**

新增一次中途重建 runner 的测试：用同一 journal replay 后，`PASSED`/`FAILED`、infra attempt 和
fallback history 完全一致；runner 不自动恢复崩溃批次，只允许生成终态报告。

- [ ] **Step 5: 提交 runner**

```zsh
git add -- src/so101_demo_py/src/parallel_batch/adaptive_runner.py \
  src/so101_demo_py/test/test_parallel_adaptive_runner.py
git diff --cached --check
git commit -m "feat: add adaptive pool fallback runner"
```

### Task 6: 把 production composition 接到自适应 runner

**Files:**
- Modify: `src/so101_demo_py/src/parallel_batch/adaptive_pool.py`
- Modify: `src/so101_demo_py/src/cli/mujoco_parallel_batch.py`
- Modify: `src/so101_demo_py/src/parallel_batch/worker.py`
- Modify: `src/so101_demo_py/test/test_parallel_adaptive_pool.py`
- Modify: `src/so101_demo_py/test/test_parallel_batch_worker.py`
- Modify: `src/so101_demo_py/test/test_parallel_batch_cli.py`

**Interfaces:**
- Consumes: `PreparedBatch`, `PoolRequest`, `AdaptivePoolContext`, `ProductionBatchComposition`。
- Produces: `ProductionAdaptivePool.run() -> PoolExecutionResult`；`ProductionAdaptivePoolFactory.__call__(PoolRequest)`。

- [ ] **Step 1: 写 production adapter RED 测试**

用 fake `ProductionBatchComposition` 分别返回：全通过、业务失败、一个 `AttemptStatus.INVALID`、
Worker 非零退出、Broker 异常和 cleanup false。断言只有业务 `FAILED` 留在当前档位；其余情况生成
具名 `InfrastructureFailure`。再由真实 `ProductionAdaptivePoolFactory` 构造 W8，证明内部
`PoolRequest(worker_count=8)` 可进入 Coordinator；同时 v1 `BatchRequest(worker_count=4)` 仍抛
`MAX_WORKER_COUNT`。

- [ ] **Step 2: 运行 RED**

在 `scratch/task-06-red/tmp` 运行 adaptive pool、Worker 和 CLI 定向测试，预期缺少 factory 和
`PoolExecutionResult` 映射。

- [ ] **Step 3: 实现 pool 子批次适配**

`ProductionAdaptivePoolFactory` 为每级构造 pool-local request：

```python
pool_batch_id = f"{batch_id}-g{generation:02d}-w{worker_count:02d}"
pool_root = runtime_root / f"p/g{generation:02d}w{worker_count:02d}"
max_points_per_worker = len(point_ids)
```

`runtime_root` 必须是 evidence root 下短名 `r/<batch-id>`，自适应 batch ID 最长 5 个 ASCII 字符。factory
在启动前对每个实际 `socket_path` 执行既有 107-byte 预检；计划中的最长 W8 路径也必须进入测试，
不得靠 `/proc/self/fd` 绕过 allocator 的失败关闭。自适应路径把 Broker authority 文件名从 v1 的
`broker-authority.sock` 缩短为 `authority.sock`，同步 host endpoint 和 Broker spec 内的
`/runtime/authority.sock`；未启用自适应时必须保留旧文件名和 manifest bytes。至少冻结下面两个
边界路径，并枚举 Worker、Coordinator、Broker 的全部实际 socket 断言都不超过 107 bytes：

```text
/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/abcde/p/g01w08/ipc/worker-08-control.sock
/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/abcde/p/g01w08/ipc/broker/authority.sock
```

测试断言第一条为 107 bytes、第二条为 106 bytes，并证明自适应 spec 中不再出现较长的
`broker-authority.sock`。

factory 使用独立 `PoolRequest`，不得构造或放宽 v1 `BatchRequest`。`PreparedBatch.request` 的联合
类型为 `BatchRequest | PoolRequest | None`；顶层自适应 prepared 对象保持 `request=None`，factory
用 `dataclasses.replace()` 生成只供本代 `ProductionBatchComposition` 使用的副本。Coordinator 的
request annotation、`asdict(request)` freeze/replay、manifest、worker spec 和 subprocess 只依赖两种
request 共有的六个字段。不得给旧 v1 journal 或 manifest 增加 type marker；单代 journal 位于自适应
runtime root，其来源由顶层自适应 manifest 绑定。测试覆盖 replay 时任一共有字段变化被拒绝，并
断言旧 v1 manifest/journal bytes 不变。

内部 `max_points_per_worker` 只用于兼容 v1 Coordinator 数据形状；真正调度由 selector 注入，不能
进入顶层用户 manifest 或重新成为硬上限。pool-local Coordinator journal 继续负责 lease、attempt
ACK、sealed result 和 recovery receipt；顶层 runner 只导入其已 fsync 的 `RESULT_COMMITTED`。本
计划所有现场自适应实验使用 `execute`，不把 `VALIDATION_COMMITTED` 或 `VALIDATION_PASSED` 升级为
物理点位终态；另加 `plan_only` adapter 测试，断言 validation 保持独立且不会写入顶层
`PASSED`/`FAILED`。

composition 增加默认值为 `None` 的 `adaptive_context` 和 `allocation_policy`，不改变旧构造调用。
自适应模式关闭 Broker 原地重启；Broker generation 丢失直接返回
`InfrastructureFailureKind.BROKER_DISCONNECTED`。

- [ ] **Step 4: 统一 Worker 基础设施分类**

worker spec 增加布尔字段 `adaptive_workers`。在 `ParallelWorker.run()` 每次 `run_one()` 返回后立即
调用纯函数：

```python
def adaptive_result_is_infrastructure(result: WorkerRunResult) -> bool: ...
```

一旦返回 true，Worker 立刻置 quarantined 并退出循环，由子进程用非零退出码通知 pool；在此之后
不得再次调用 `grant_lease()`。`_worker_results_failed()` 仍作为进程结束后的二次防线，把签名改为：

```python
def _worker_results_failed(results, *, adaptive_workers: bool = False) -> bool:
```

旧模式规则保持不变。自适应模式中，`INITIAL_GATE_FAILED`、任何 `AttemptStatus.INVALID`、
`WORKER_NOT_READY`、`LEASE_ACK_FAILED`、`START_ACK_FAILED`、`TERMINAL_ACK_FAILED`、
`PORT_FAILURE` 都返回 true。`NO_POINT` 是正常空闲/队列耗尽，必须返回 false；pool-directed
`STOP_REQUESTED` 也不能单独制造第二个 infra 原因。“recovery false”只在结果带有非空 point ID、
确实取得过 lease/attempt 且该路径要求 canonical recovery 时算 infra，不能笼统判断布尔字段。
`AttemptStatus.FAILED` 且 recovered true 返回 false。新增测试必须覆盖 N 大于点数、正常队列耗尽、
业务失败后成功 recovery、真实 recovery 失败，并断言首次 recovered `INITIAL_GATE_FAILED` 或
`INVALID` 后 grant 调用计数不再增加，而业务 `FAILED` 完成 recovery 后仍可领取下一个点。

- [ ] **Step 5: GREEN 和旧 Worker 回归**

运行 Task 6 的三个测试文件，再运行 `test_parallel_batch_fault_injection.py` 和
`test_parallel_batch_crash_recovery.py`。预期旧模式 recovered `INITIAL_GATE_FAILED/INVALID` 行为不变，
自适应模式将其上报 runner。

- [ ] **Step 6: 提交 production adapter**

```zsh
git add -- src/so101_demo_py/src/parallel_batch/adaptive_pool.py \
  src/so101_demo_py/src/cli/mujoco_parallel_batch.py \
  src/so101_demo_py/src/parallel_batch/worker.py \
  src/so101_demo_py/test/test_parallel_adaptive_pool.py \
  src/so101_demo_py/test/test_parallel_batch_worker.py \
  src/so101_demo_py/test/test_parallel_batch_cli.py
git diff --cached --check
git commit -m "feat: connect adaptive runner to production workers"
```

### Task 7: 将 PerceptionBroker 队列扩到当前 Worker 档位

**Files:**
- Modify: `src/so101_demo_py/src/parallel_batch/broker.py`
- Modify: `src/so101_demo_py/src/cli/parallel_perception_broker.py`
- Modify: `src/so101_demo_py/src/cli/mujoco_parallel_batch.py`
- Modify: `src/so101_demo_py/test/test_parallel_batch_broker.py`
- Modify: `src/so101_demo_py/test/test_parallel_adaptive_pool.py`

**Interfaces:**
- Consumes: 当前 pool 的 `worker_count` 和 v1 模型/timeout/freshness 配置。
- Produces: `PerceptionBroker(..., queue_capacity_per_model: int | None = None)`；broker spec 字段 `queue_capacity_per_model`。

- [ ] **Step 1: 写八 Worker Broker RED 测试**

```python
def test_adaptive_broker_accepts_one_yolo_request_from_each_of_eight_workers():
    broker = PerceptionBroker(
        CONFIG,
        grounded_model_id="grounded-sam",
        authorize=lambda _request: True,
        queue_capacity_per_model=8,
    )
    submissions = [broker.submit(request(worker=f"worker-{n:02d}")) for n in range(1, 9)]
    assert all(item.accepted for item in submissions)
```

再断言第九个请求拒绝、八 Worker round-robin 无饥饿、单 Worker/模型仍只有一个 in-flight、Broker
timeout 仍是 `INFRA_ERROR`，YOLO `NORMAL_REJECTION` 才进入 Grounded-SAM。

- [ ] **Step 2: 运行 RED**

在 `scratch/task-07-red/tmp` 运行 Broker 和 adaptive pool 测试，预期 constructor 不接受容量覆盖。

- [ ] **Step 3: 实现容量覆盖和 spec 校验**

容量覆盖必须是正整数且不超过冻结的自适应上限 8。未传时继续使用 v1
`broker_queue_capacity_per_model=3`。production pool 写当前档位 N；broker CLI 回读 spec，并把 N
传入 `PerceptionBroker`。不移植旧重型分支的 canary ticket、Authority 或资源监视器协议。

- [ ] **Step 4: GREEN 和感知矩阵回归**

运行：

```zsh
PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider \
  src/so101_demo_py/test/test_parallel_batch_broker.py \
  src/so101_demo_py/test/test_parallel_batch_perception.py \
  src/so101_demo_py/test/test_parallel_perception_runtime.py \
  src/so101_demo_py/test/test_parallel_adaptive_pool.py -q
```

- [ ] **Step 5: 提交 Broker 扩容**

```zsh
git add -- src/so101_demo_py/src/parallel_batch/broker.py \
  src/so101_demo_py/src/cli/parallel_perception_broker.py \
  src/so101_demo_py/src/cli/mujoco_parallel_batch.py \
  src/so101_demo_py/test/test_parallel_batch_broker.py \
  src/so101_demo_py/test/test_parallel_adaptive_pool.py
git diff --cached --check
git commit -m "feat: scale adaptive perception queues"
```

### Task 8: 首个基础设施故障立即收敛并精确清理

**Files:**
- Modify: `src/so101_demo_py/src/runtime/parallel_processes.py`
- Modify: `src/so101_demo_py/src/parallel_batch/resources.py`
- Modify: `src/so101_demo_py/src/parallel_batch/adaptive_pool.py`
- Modify: `src/so101_demo_py/src/cli/mujoco_parallel_batch.py`
- Create: `src/so101_demo_py/src/cli/parallel_batch_cleanup.py`
- Create: `scripts/run_so101_adaptive_batch.zsh`
- Modify: `src/so101_demo_py/setup.py`
- Create: `src/so101_demo_py/test/test_parallel_adaptive_integration.py`
- Modify: `src/so101_demo_py/test/test_parallel_processes.py`
- Modify: `src/so101_demo_py/test/test_parallel_batch_resources.py`

**Interfaces:**
- Consumes: `ProcessSupervisor` 的 exact owned identities 和 Worker control RPC。
- Produces: `wait_for_children(..., stop_on_nonzero=False, on_nonzero=None)`；自适应 summary
  `aggregate_results.json`；`so101_parallel_batch_cleanup --runtime-root ...`；监督脚本
  `run_so101_adaptive_batch.zsh`。

- [ ] **Step 1: 写非零退出和哨兵清理 RED 测试**

创建三个 fake owned groups：两个 batch Worker 和一个不登记的哨兵。第一个 Worker 返回 17 后，
断言 `on_nonzero` 只执行一次、停止新 lease、请求其他 Worker stop，并且 signal 列表中没有哨兵
PGID。再写 cleanup false 测试，断言 runner 不创建 W6 pool。最后以真实的无害 sleep 子进程模拟
Runner 和 owned Worker：SIGKILL Runner 子进程但保留监督脚本，断言监督脚本只按 manifest 清理
owned Worker，哨兵仍存活。Runner 死后、cleanup 完成前，用新 batch ID 的 allocator 申请相同
Domain 必须因持久 `ACTIVE` marker 失败；只有 owned Worker 退出并写入精确 cleanup receipt 后 marker
才能变成 `RELEASED`。

- [ ] **Step 2: 运行 RED**

在 `scratch/task-08-red/tmp` 运行 integration/process tests，预期缺少 `stop_on_nonzero`。

- [ ] **Step 3: 实现首错回调和 pool 收尾**

`ProcessSupervisor.wait_for_children()` 增加两个 keyword-only 参数，默认值保持旧行为。自适应调用
传 `stop_on_nonzero=True`；首个非零 Worker exit 或 health dependency failure 时，按顺序执行：

```text
coordinator stop_new_leases
worker control cancel_motion
worker control confirm_no_controller_goal
worker control recover
supervisor exact shutdown
container exact retirement
Domain/socket/session cleanup readback
```

相同 generation 的后续错误只进入 `PoolExecutionResult.diagnostics`，不能重复触发 fallback。

- [ ] **Step 4: 实现轻量外部监督和异常清理**

`run_so101_adaptive_batch.zsh` 使用 `set -euo pipefail`，把 `so101_parallel_batch` 作为子进程启动并
保留其精确 PID。脚本严格解析且只接受一个 `--evidence-root` 和一个 1–5 字符 `--batch-id`，由两者
推导 runtime root；缺失或重复参数在启动前拒绝。子进程正常或异常退出后，脚本都调用：

```zsh
so101_parallel_batch_cleanup --runtime-root <absolute-short-runtime-root>
```

`parallel_batch_cleanup.py` 从顶层 journal 读取唯一 active generation，再读取该代
`owned-processes.json`、resource manifest 和 cleanup gates；复用 `OwnedProcessIdentity` 与
`ProcessSupervisor` 的 PID/PGID/start ticks 校验，先停止登记进程和容器，再读回 controller、Domain、
socket、session，最后写 fsync cleanup receipt。任何身份漂移都失败关闭，绝不扫描或清理 manifest
外进程；cleanup 未完成时 wrapper 返回非零，下一代不得启动。正常批次重复调用只做幂等读回。
cleanup 成功时 wrapper 保留 Runner 原退出码；cleanup 失败时无条件返回非零。

自适应 Domain claim record 增加 `claim_state=ACTIVE|RELEASED` 和 generation/batch identity。正常
Runner 与异常 cleanup 入口都只能在全部登记进程、controller、session 和 socket 清理回读成功后，
持有对应 claim flock 把 record 原子改为 `RELEASED` 并 fsync；仅仅发现原 Runner PID 消失不够。

这层监督覆盖 Python 异常、SIGINT/SIGTERM 和 Runner 子进程 SIGKILL；监督 shell 本身被 SIGKILL
不承诺自动恢复。此时新运行会因既有 runtime root/Domain claim 失败关闭，操作者只能显式调用同一
精确 cleanup 入口后用新 run ID 重启。

- [ ] **Step 5: 写自适应最终输出**

`run_cli()` 在 `prepared.adaptive_request is not None` 时创建 `AdaptiveBatchRunner`。输出字段固定为：

```json
{
  "schema_version": 1,
  "mode": "adaptive_workers",
  "status": "COMPLETED",
  "initial_worker_count": 8,
  "final_worker_count": 6,
  "levels_used": [8, 6],
  "fallback_transitions": [],
  "point_statuses": {},
  "infra_attempts": {},
  "batch_cleanup_complete": true,
  "elapsed_s": 0.0
}
```

实际 transition 和点位内容由 summary 填入。`COMPLETED` 返回 0；
`COMPLETED_WITH_FAILURES` 和 `INFRA_FAILED` 返回 1。旧 `outcome_document()` bytes 不变。

- [ ] **Step 6: GREEN 和精确清理回归**

运行 Task 8 测试，并重跑 `test_parallel_processes.py`、`test_parallel_batch_cli.py`、
`test_parallel_batch_crash_recovery.py`。确认 PID reuse、leaderless PGID 和 unowned identity 仍拒绝
signal。

- [ ] **Step 7: 提交清理与输出**

```zsh
git add -- src/so101_demo_py/src/runtime/parallel_processes.py \
  src/so101_demo_py/src/parallel_batch/resources.py \
  src/so101_demo_py/src/parallel_batch/adaptive_pool.py \
  src/so101_demo_py/src/cli/mujoco_parallel_batch.py \
  src/so101_demo_py/src/cli/parallel_batch_cleanup.py \
  src/so101_demo_py/setup.py \
  scripts/run_so101_adaptive_batch.zsh \
  src/so101_demo_py/test/test_parallel_adaptive_integration.py \
  src/so101_demo_py/test/test_parallel_processes.py \
  src/so101_demo_py/test/test_parallel_batch_resources.py
git diff --cached --check
git commit -m "feat: degrade adaptive pools on infrastructure failure"
```

### Task 9: 安装产物、负面重型依赖和完整包测试

**Files:**
- Modify: `src/so101_demo_py/test/test_parallel_adaptive_integration.py`
- Modify: `docs/experiments/so101-parallel-adaptive-worker-pool-experiment-ledger.md`

**Interfaces:**
- Consumes: 前八个任务的全部代码和 config install 规则。
- Produces: package-level 自动化验收和 `CP-002`。

- [ ] **Step 1: 增加负面依赖测试**

断言自适应路径：

- 安装并能定位 `parallel_adaptive_workers_v1.yaml`；
- `--help` 包含六个自适应参数；
- 不接受 `--admission-mode`、profile、Authority、cgroup、qualification 或 canary 参数；
- 导入自适应模块不会导入 `parallel_batch.qualification`、`resource_monitor`、`watchdog` 或
  `cgroups`；
- 旧 W8 分支的 `parallel_batch_v2.yaml` 不会被自适应 CLI 读取。

- [ ] **Step 2: 运行完整定向 suite**

创建 `scratch/task-09-targeted/tmp`，回读 tempfile 后运行：

```zsh
PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider \
  src/so101_demo_py/test/test_parallel_adaptive_contracts.py \
  src/so101_demo_py/test/test_parallel_adaptive_queue.py \
  src/so101_demo_py/test/test_parallel_adaptive_runner.py \
  src/so101_demo_py/test/test_parallel_adaptive_pool.py \
  src/so101_demo_py/test/test_parallel_adaptive_integration.py -q
```

- [ ] **Step 3: build、source 和 package gate**

```zsh
cd /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_demo_py --symlink-install
source install/setup.zsh
ros2 pkg prefix so101_demo_py
command -v so101_parallel_batch
command -v so101_parallel_batch_cleanup
```

创建 `scratch/task-09-package/tmp`，设置三个 temp 变量并回读，然后运行：

```zsh
set -euo pipefail
python_bin=/usr/bin/python3
test -x "$python_bin"
"$python_bin" -c 'import tempfile; print(tempfile.gettempdir())' | \
  rg '^/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/scratch/task-09-package/tmp$'
PYTHONNOUSERSITE=1 "$python_bin" -m colcon test --packages-select so101_demo_py \
  --event-handlers console_direct+ \
  --pytest-args -p no:cacheprovider
"$python_bin" -m colcon test-result --verbose
```

预期：`/usr/bin/python3 -m colcon` 可导入并实际收集非零测试，errors=0、failures=0；pytest collection
日志只落在 `src/so101_demo_py/test/`，不收集 `benchmark_test/`。若 ai-station 的 colcon 不属于该
解释器，先记录实际 shebang/`sys.executable` 并改用同一个绝对 Python 做 tempfile 回读和 test；
不得把两个解释器的结果拼在一起。

- [ ] **Step 4: 更新账本和提交测试门**

把命令、退出码、耗时、scratch 路径、test-result 摘要、source commit、install prefix 写入
`EXP-001`，状态改为 `VALID`。追加 `CP-002`，下一实验为 `EXP-002` 现场故障注入。

```zsh
git add -- src/so101_demo_py/test/test_parallel_adaptive_integration.py \
  docs/experiments/so101-parallel-adaptive-worker-pool-experiment-ledger.md
git diff --cached --check
git commit -m "test: verify adaptive worker package integration"
```

### Task 10: 现场验证 W8 启动失败和 W8→W6 运行中降级

**Files:**
- Modify: `scripts/inject_so101_parallel_fault.py`
- Modify: `src/so101_demo_py/test/test_inject_so101_parallel_fault.py`
- Modify: `docs/experiments/so101-parallel-adaptive-worker-pool-experiment-ledger.md`

**Interfaces:**
- Consumes: `owned-processes.json` 中的 exact Worker identity。
- Produces: `inject_so101_parallel_fault.py --batch-root ... --worker-id ... --signal TERM`，只对精确匹配的登记 PGID 发信号。

- [ ] **Step 1: 给 fault injector 写 identity RED 测试**

测试必须拒绝 PID reuse、错误 batch ID、非 Worker role、leaderless PGID 和 manifest 外 PID；成功
路径只返回一个精确 PGID。不得增加模糊进程搜索。

- [ ] **Step 2: 实现并通过 fault injector 测试**

运行 `test_inject_so101_parallel_fault.py` 到 RED，再做最小实现并跑 GREEN。提交：

```zsh
git add -- scripts/inject_so101_parallel_fault.py \
  src/so101_demo_py/test/test_inject_so101_parallel_fault.py
git diff --cached --check
git commit -m "test: add exact adaptive worker fault injection"
```

- [ ] **Step 3: 冻结 `EXP-002A/B` 并建立旁路哨兵**

`EXP-002A` 的唯一变量是在 W8 尚未进入 `POOL_RUNNING` 时终止一个已登记 Worker，预测是 W8 无
lease、精确清理后 W6 接管。`EXP-002B` 的唯一变量是在 W8 已提交至少一个终态且另有 active
attempt 时终止该 attempt 的 Worker，预测是终态保留、在途点 `INFRA_INTERRUPTED`、W6 继续。
两次实验使用不同短 run ID。先记录：

```zsh
hostname
pwd
git rev-parse HEAD
git status --short
ros2 pkg prefix so101_demo_py
tmux list-sessions 2>/dev/null || true
pgrep -af 'move_group|rviz2|gz sim|pick_place_state_machine|so101_parallel_batch' || true
```

发现不属于本任务的 stack 时停止，不清理它。

启动一个任务自有、但不写入 batch manifest 的 sleep 哨兵和一个 ROS Domain 230 哨兵。用
`setsid` 启动后立即记录 PID、PGID、start ticks 和完整 cmdline；若 `demo_nodes_cpp` 不存在则在创建
batch 前停止，不用别的共享节点替代。两次 fallback 后都必须证明两个哨兵仍存活，最后仅按记录的
精确身份停止它们并登记清理回读。

- [ ] **Step 4: 运行启动未 READY 的四点 execute 实验 `EXP-002A`**

使用四个既有点 `task_start`、`cup_test_forward_5cm`、`sample_05_near_center`、
`sample_14_far_right`，runtime root 固定为 evidence root 下 `r/su01`，由
`scripts/run_so101_adaptive_batch.zsh` 启动。命令必须包含：

```text
--adaptive-workers
--config src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml
--adaptive-config src/so101_demo_py/config/mujoco/parallel_adaptive_workers_v1.yaml
--batch-id su01
--evidence-root /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01
--worker-count 8
--fallback-worker-counts 6,4,2,1
--initial-points-per-worker 1
--worker-start-timeout-s 120
--max-infra-attempts-per-point 5
--run-mode execute
```

其余模型路径和 SHA 使用已验证的 v1 值：YOLO
`/data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt`、
SHA `f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781`；Grounded-SAM
`/data/work/so101-models/grounded-sam-v2-scipy-lock`、SHA
`0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775`。

轮询 `r/su01/p/g01w08/owned-processes.json`，解析一个精确 Worker ID，并在顶层 journal 尚无
`POOL_RUNNING` 和本代 `LEASE_GRANTED` 时立即注入 SIGTERM。若注入前已经出现其中任一事件，本次
记 `INVALID` 并用新短 run ID 重做。有效实验必须看到 W8→W6、W8 零 lease、W6 全部 READY 后四点
获得业务终态、旧 PGID/Domain/socket 清理，且旁路哨兵仍存活。

- [ ] **Step 5: 运行 active attempt 故障实验 `EXP-002B`**

runtime root 使用 `r/mr01`（即命令改为 `--batch-id mr01`），选择完整 20 点以扩大稳定注入窗口，
其余参数与 Step 4 相同。等待
`POOL_RUNNING W8`、至少一个 `RESULT_COMMITTED`，并从同一次最新 snapshot 解析一个
`ATTEMPT_STARTED` 且仍 active 的 lease；立即再次确认该 attempt 仍 active，再把显式 Worker ID
传给 injector。若信号发出前 attempt 已自然完成，或信号后没有该 attempt 的
`POINT_INFRA_INTERRUPTED` 证据，本次记 `INVALID`，用新 run ID 重做，不把自然完成冒充注入成功。

等待批次结束，验证 transition 为 8→6、已提交点没有第二个业务 attempt、被中断点在 W6 重新通过
初始状态门、W6 只领取剩余和中断点、旧资源精确清理，且旁路哨兵仍存活。20 点中的业务失败按
原样保留，不触发额外 fallback；它不影响对基础设施 transition 的判断。

- [ ] **Step 6: 记录两个实验并收敛哨兵**

分别保存命令、退出码、事件序列、进程身份、旧/新 Domain、点位结果和 cleanup receipt。证据完整
才记 `VALID`；任何初始状态、provenance、注入时序或身份不明都记 `INVALID`。两个实验结束后只按
Step 3 保存的 PID/PGID/start ticks 停止任务自有哨兵，证明不存在 batch 外误清理。

### Task 11: 完成 20 点自适应 execute 回归

**Files:**
- Modify: `docs/experiments/so101-parallel-adaptive-worker-pool-experiment-ledger.md`

**Interfaces:**
- Consumes: 已通过的 package gate、故障注入、20 点 catalog 和模型身份。
- Produces: 一个 `COMPLETED` 的 20/20 批次，允许最终档位为 W8、W6、W4、W2 或 W1。

- [ ] **Step 1: 冻结 `EXP-003`**

记录当前 commit、installed wrapper、package prefix、点位 catalog SHA
`c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5`、两个模型 SHA、运行策略、
全部 ROS Domain、20 点成功判据和短 runtime root `r/e2001`。生命周期记
`ISOLATED_STACK`；不冒充 `RESET_WORLD` 或 `FULL_RESTART`。

- [ ] **Step 2: 运行完整 20 点**

使用 Task 10 相同模型参数，改为：

```text
--batch-id e2001
--worker-count 8
--fallback-worker-counts 6,4,2,1
--initial-points-per-worker 3
--run-mode execute
--evidence-root /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01
```

通过 tmux 持有 `scripts/run_so101_adaptive_batch.zsh` 包装后的命令和退出码。运行期间只观察本任务
登记的进程、ROS graph、Broker、GPU、RTF 和
journal，不用资源指标人工中止正常批次。

- [ ] **Step 3: 按证据层验收每个点**

对 20 个点逐项核对：新 `point_initial_gate`、YOLO 先行、必要时 Grounded-SAM、`POSE_ACCEPTED`、
MoveIt 规划/执行、controller/joint/TF、MuJoCo 杯子最终 pose、Planning Scene 无残留 attachment、
terminal RGB 和 sealed result。所有点必须为 `PASSED`，`batch_cleanup_complete=true`。

若出现业务 `FAILED`，保持该批原结论，先在账本新增单点 `PLANNED` 实验，按首个坏边界做
RED→修复→GREEN；不得在同批自动重跑覆盖。修复后使用新 batch ID
短 ID `e2002` 从 20 点重新验证。

- [ ] **Step 4: 视觉回读**

实际打开 20 份 terminal RGB；至少保存并查看 P01、P09、P18、P19 和最终一个点的 fresh 图像。
任何失败点必须全部查看。运行现有俯视图脚本生成状态图，确认图中点位和 batch summary 一致；
图片只作视觉投影，不能改变 Coordinator 结果。

- [ ] **Step 5: 记录 `EXP-003` 和 checkpoint**

只有 20 个点全部 `PASSED`、清理回读通过时将实验记为 `VALID` success。记录 initial/final Worker
数、fallback history、每 Worker 负载、总耗时、模型使用和证据路径。追加 `CP-003`，下一实验
为性能矩阵。

### Task 12: 测量 W1/W2/W4/W6/W8 性能

**Files:**
- Create: `scripts/run_so101_adaptive_worker_scaling.zsh`
- Modify: `docs/experiments/so101-parallel-adaptive-worker-pool-experiment-ledger.md`

**Interfaces:**
- Consumes: 已通过 20 点 execute 的同一 commit、overlay、catalog、模型和初始状态契约。
- Produces: `reports/worker-scaling-summary.json`，包含每档 wall time、实际 levels、点位结果和相对 W1 speedup。

- [ ] **Step 1: 写只读 `--dry-run` 脚本合同检查**

脚本支持：

```text
--worker-counts 1,2,4,6,8
--evidence-root /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01
--dry-run
```

`--dry-run` 只打印五条通过 `scripts/run_so101_adaptive_batch.zsh` 包装的完整命令，不启动 ROS。
每条命令使用不同且不超过 5 字符的 batch ID（runtime root 自动落到 `r/<batch-id>`），其他参数
完全一致。用 shell test 检查五个 Worker 数各出现一次、没有 `--max-points-per-worker`、都有
`--initial-points-per-worker 3`。

- [ ] **Step 2: 实现脚本并提交**

脚本使用 zsh `set -euo pipefail`，顺序运行五档以避免跨批资源重叠。每批用 `/usr/bin/time -p`
记录 wall time，结束后确认本批 owned process/Domain/socket 全部清理，再开始下一批。它不得删除
既有 evidence root；目标 `r/<batch-id>` 已存在即停止。

```zsh
git add -- scripts/run_so101_adaptive_worker_scaling.zsh
git diff --cached --check
git commit -m "test: add adaptive worker scaling driver"
```

- [ ] **Step 3: 冻结并运行 `EXP-004` 至 `EXP-008`**

五个实验分别固定 Worker 数 1、2、4、6、8。每次仍保留该档允许的较小 fallback，但只有
`levels_used` 仅含目标档位、20 点全 `PASSED` 且 cleanup 通过的运行才是有效性能样本。发生
fallback 的运行保留为自适应恢复证据，不计入目标档位 speedup。

- [ ] **Step 4: 生成性能汇总**

汇总 JSON 固定字段：

```json
{
  "baseline_worker_count": 1,
  "runs": [
    {
      "requested_worker_count": 1,
      "levels_used": [1],
      "elapsed_s": 0.0,
      "point_passed": 20,
      "point_failed": 0,
      "valid_performance_sample": true,
      "speedup_vs_w1": 1.0
    }
  ]
}
```

实际时间替换 0.0。speedup 使用 `w1_elapsed_s / current_elapsed_s`。W8 若降为 W6，W8 条目标记
`valid_performance_sample=false`，不能使用降级后时间冒充 W8。

- [ ] **Step 5: 更新账本**

每档记录 source/install/runtime provenance、Domain、完整命令、退出码、墙钟时间、点位结果、
fallback、清理和资源观察值。不得混合不同 commit 或失败后修复前后的样本。

### Task 13: 最终回归、代码审查和交接

**Files:**
- Modify: `docs/experiments/so101-parallel-adaptive-worker-pool-experiment-ledger.md`

**Interfaces:**
- Consumes: 所有实现提交、包测试、现场 20 点与性能证据。
- Produces: clean feature branch、最终 checkpoint 和可审查证据索引。

- [ ] **Step 1: 最终自动化 gate**

先 `set -euo pipefail`，创建新的 `scratch/task-13-final/tmp`，把三个 temp 变量指向它，并用将要
运行测试的绝对 `/usr/bin/python3` 回读 tempfile。用该解释器分别运行全部新增 pytest 和
`-m colcon test --packages-select so101_demo_py --event-handlers console_direct+ --pytest-args -p no:cacheprovider`，
再运行 `-m colcon test-result --verbose` 与 `git diff --check`。确认实际收集非零测试且
`benchmark_test/` 未被普通 gate 收集；若实际 colcon 解释器不同，按 Task 9 的 fail-closed 规则处理。

- [ ] **Step 2: 运行 implementation code review**

使用 `superpowers:requesting-code-review`，审查范围为 `origin/main..HEAD`。P0/P1 必须修复并重新
跑受影响 RED/GREEN、package 和现场 gate；P2 明确记录接受或修复理由。不得以计划阶段 Astra
审查代替实现代码审查。

- [ ] **Step 3: 最终 provenance 与清理回读**

```zsh
cd /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool
git status --short
git log --oneline origin/main..HEAD
ros2 pkg prefix so101_demo_py
command -v so101_parallel_batch
command -v so101_parallel_batch_cleanup
pgrep -af 'move_group|rviz2|gz sim|pick_place_state_machine|so101_parallel_batch' || true
```

只报告本任务拥有的进程；其他进程标为 preserved，不清理。

- [ ] **Step 4: 完成账本 checkpoint**

追加最终 checkpoint，写入：20/20 结果、最终 Worker 档位、性能矩阵、测试计数、review 结论、
branch HEAD、dirty files、owned/preserved processes、retained evidence、archived evidence 和 deletion
candidates。所有 scratch 都只列为删除候选，未经授权不删除。

- [ ] **Step 5: 提交最终账本**

```zsh
git add -- docs/experiments/so101-parallel-adaptive-worker-pool-experiment-ledger.md
git diff --cached --check
git commit -m "docs: record adaptive worker pool qualification"
git status --short
```

预期：worktree 干净。停止在本地 feature branch；push、merge、旧分支删除和证据删除等待用户单独
授权。
