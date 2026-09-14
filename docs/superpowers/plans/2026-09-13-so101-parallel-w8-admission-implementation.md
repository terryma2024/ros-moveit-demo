# SO-101 Parallel W8 Admission Implementation Plan

> **Status:** Superseded on 2026-09-14 by
> `docs/superpowers/plans/2026-09-14-so101-adaptive-worker-pool-implementation.md`.
> Preserve this file for history; do not execute its Authority, signed profile, cgroup admission,
> staged qualification, or canary tasks.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在当前 ai-station 上实现八个完整 MuJoCo MoveIt 专家 Worker 的冻结准入、同批次 `1 → 2 → 4 → 6 → 8` qualification、资源画像和 W8 正式 20 点回归。

**Architecture:** 保留 v1 的 W1–W3 契约，新增显式 v2 配置。v2 在启动第一个 Worker 前原子保留最终请求的 ROS Domain，以 cgroup v2 约束完整进程树；system-managed watchdog 独立持有 Domain/cgroup 生命周期，资源监视器和 AdmissionAuthority 审核五级 canary；W8 获得 provisional admission 后才开放正式动态队列。

**Tech Stack:** Python 3.12、ROS 2 Jazzy、`rmw_fastrtps_cpp`、MuJoCo、MoveIt 2、cgroup v2、Docker、NVML/`nvidia-smi`、pytest、colcon、YAML/JSON、fsync 事件账本。

**Spec:** `docs/superpowers/specs/2026-09-13-so101-parallel-w8-admission-design.md`

## Global Constraints

- 只支持 MuJoCo；不运行实体机械臂，不扩展 Gazebo。
- v1 配置和 W1–W3 行为保持不变。v2 必须显式选择。
- v2 normal 的请求 N 必须满足 `requested_worker_count == allocated_worker_count == started_worker_count == ready_worker_count == N`；qualification 只接受 N=8，W8 不能降级。
- qualification 在同一个 batch 中累积启动 `1, 2, 4, 6, 8`，每级三轮同步 canary。
- 正式 W8 使用八个完整 Worker，全部允许同时进入 `EXECUTING`；不增加低于八的活动并发令牌。
- ROS Domain 固定为 215–222，启动第一个 Worker 前一次性原子保留；v1/v2 共用既有 claim root。
- `RMW_IMPLEMENTATION=rmw_fastrtps_cpp`，discovery scope 为 localhost。
- Fast DDS 只使用 UDPv4 loopback，关闭 SHM/Data Sharing；每 Worker 最多 32 个 DDS participant。
- 控制面保留 4 个逻辑 CPU；八 Worker 共享 20 个逻辑 CPU。
- batch `memory.max=24 GiB`、`memory.swap.max=0`、主机 RAM 设计保留 6 GiB，`MemAvailable` 硬下限 4 GiB。
- GPU 保留至少 2 GiB；CPU、RAM、GPU 的 accepted W8 峰值至少有 20% 余量。
- PerceptionBroker 每模型队列容量为 8，每 Worker/模型最多一个在途请求；YOLO-Seg 优先，Grounded-SAM 只按现有感知失败矩阵回退。
- v2 Broker 先排不含图像的 ticket，收到 `CAPTURE_NOW` 后才捕帧；YOLO/Grounded ticket timeout 分别为 10/30 秒，capture submit 为 0.5 秒。
- accepted profile 不按时间过期；只因硬件、运行 provenance、能力或运行硬故障漂移而失效。
- 现场任务只使用 `/data/work/so101-evidence/parallel-w8/20260913-q01` 作为 durable evidence root；batch 只用 `b/s`、`b/q`、`b/n` 短路径。
- ai-station 上每次 pytest/colcon 临时目录必须是上述 evidence root 下从未存在的 task-specific `scratch/*/tmp`；先用实际 Python 回读 `tempfile.gettempdir()`，完成后只列为删除候选。
- 不删除旧证据，不停止非本任务进程，不使用宽泛 `pkill`，不运行 `ament_uncrustify --reformat`。
- 每项代码改动遵循 RED → GREEN，并在任务边界创建独立提交。

---

## 实施目录与职责

新增文件：

- `src/so101_demo_py/config/mujoco/parallel_batch_v2.yaml`：冻结 v2 配置。
- `src/so101_demo_py/config/mujoco/parallel_admission_profiles_v1.yaml`：repo-tracked 签名 profile 审计索引；不是 live 授权源。
- `src/so101_demo_py/src/parallel_batch/domain_pool.py`：八 Domain 原子 claim、进程/DDS 探测和释放。
- `src/so101_demo_py/src/parallel_batch/cgroups.py`：cgroup v2 层级、进程 enrollment 和完整后代验证。
- `src/so101_demo_py/src/parallel_batch/watchdog.py`：独立持有 Domain/cgroup 生命周期并处理异常清理。
- `src/so101_demo_py/src/parallel_batch/resource_monitor.py`：0.5 秒采样、阶段窗口和熔断判定。
- `src/so101_demo_py/src/parallel_batch/qualification.py`：`1,2,4,6,8` 状态机、barrier 和 canary 账本。
- `src/so101_demo_py/src/parallel_batch/admission.py`：provisional/final profile schema 与验证。
- `src/so101_demo_py/src/cli/parallel_admission_authority.py`：独立 Authority CLI/Unix RPC 入口。
- `src/so101_demo_py/src/cli/parallel_batch_watchdog.py`：systemd batch watchdog 入口。
- `src/so101_demo_py/test/test_parallel_batch_v2_contracts.py`：v1/v2 兼容和不降级契约。
- `src/so101_demo_py/test/test_parallel_domain_pool.py`：Domain claim、冲突、崩溃和释放测试。
- `src/so101_demo_py/test/test_parallel_cgroups.py`：cgroup 文件系统和后代归属测试。
- `src/so101_demo_py/test/test_parallel_watchdog.py`：组件死亡、pending terminal 与清理集成测试。
- `src/so101_demo_py/test/test_parallel_resource_monitor.py`：采样、headroom 和熔断测试。
- `src/so101_demo_py/test/test_parallel_qualification.py`：扩容状态机、canary 和 Worker replacement 测试。
- `src/so101_demo_py/test/test_parallel_admission.py`：Authority、profile 和 drift 测试。
- `docs/experiments/so101-parallel-w8-admission-experiment-ledger.md`：现场实验账本。

修改文件：

- `src/so101_demo_py/src/parallel_batch/contracts.py`：增加 v2 严格配置和 schema-aware request 上限。
- `src/so101_demo_py/src/parallel_batch/resources.py`：改由 DomainPool/cgroup 分配器提供资源 manifest。
- `src/so101_demo_py/src/parallel_batch/coordinator.py`：加入 qualification phase、W8 容量维持和队列门。
- `src/so101_demo_py/src/parallel_batch/broker.py`：八 Worker 公平队列和指标快照。
- `src/so101_demo_py/src/parallel_batch/journal.py`：新增 qualification/admission 事件及重放。
- `src/so101_demo_py/src/parallel_batch/worker.py`：canary execution kind、barrier 和 cgroup 身份回报。
- `src/so101_demo_py/src/runtime/parallel_ipc.py`：slot heartbeat 与 Broker ticket/grant/frame wire schema。
- `src/so101_demo_py/src/runtime/parallel_ros_runtime.py`：按模型重新捕获对齐 RGB-D/TF 和 admission latch。
- `src/so101_demo_py/src/cli/mujoco_parallel_batch.py`：新增 v2/admission CLI，保持 v1 路径。
- `src/so101_demo_py/setup.py`：注册 Authority 与 watchdog CLI。
- `scripts/inject_so101_parallel_fault.py`：增加 v2 阶段和资源故障注入。

## ai-station 执行准备

- [ ] **Step 1: 接管已投递 worktree，核验账本和唯一 evidence root**

你当前直接运行在 ai-station 上，不要再次 `ssh ai-station`。先只读检查：

```zsh
hostname
cd /data/work/ws_moveit
git rev-parse HEAD
git branch --show-current
git status --short
git submodule status
tmux list-sessions 2>/dev/null || true
pgrep -af 'gz sim|move_group|rviz2|pick_place_state_machine|so101_parallel_batch' || true
```

调度方会从已审查分支创建 `/data/work/ws_moveit/.worktrees/parallel-w8-admission-v2`，分支名
`codex/parallel-w8-admission-v2`，并把 handoff 放入唯一 evidence root。先核对 worktree HEAD、
branch、handoff SHA256/size/receipt；若与 handoff 不一致，停止，不覆盖或重建。

调度方会预创建唯一 evidence root，只允许已有 dispatch metadata。核验权限和内容后创建其余目录：

```zsh
evidence_root=/data/work/so101-evidence/parallel-w8/20260913-q01
test -d "$evidence_root"
test "$(stat -c '%a' "$evidence_root")" = 700
find "$evidence_root" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort
install -d -m 700 "$evidence_root/coordinator" "$evidence_root/qualification" \
  "$evidence_root/dispatch" "$evidence_root/authority-requests" \
  "$evidence_root/authority-receipts" "$evidence_root/production" \
  "$evidence_root/workers" "$evidence_root/broker" \
  "$evidence_root/metrics" "$evidence_root/b" "$evidence_root/scratch"
```

建立 `docs/experiments/so101-parallel-w8-admission-experiment-ledger.md`，写入 branch、commit、
overlay、Domain、生命周期、已确认 W1/W2 证据、下一实验和 evidence root。提交：

```zsh
git add docs/experiments/so101-parallel-w8-admission-experiment-ledger.md
git commit -m "docs: start SO-101 W8 admission ledger"
```

后续定向 pytest 统一使用下面的 zsh 函数。每次调用传入从未使用的固定 test run ID：

```zsh
set -euo pipefail
evidence_root=/data/work/so101-evidence/parallel-w8/20260913-q01
test_python=/usr/bin/python3
run_w8_pytest() {
  local test_run_id="$1"
  shift
  local test_tmp="$evidence_root/scratch/$test_run_id/tmp"
  test ! -e "$test_tmp" || return 90
  install -d -m 700 "$test_tmp" || return 91
  export TMPDIR="$test_tmp" TMP="$test_tmp" TEMP="$test_tmp"
  local resolved_tmp
  resolved_tmp=$(TMPDIR="$test_tmp" TMP="$test_tmp" TEMP="$test_tmp" \
    "$test_python" -c 'import tempfile; print(tempfile.gettempdir())') || return 92
  test "$resolved_tmp" = "$test_tmp" || return 93
  TMPDIR="$test_tmp" TMP="$test_tmp" TEMP="$test_tmp" PYTHONNOUSERSITE=1 \
    "$test_python" -m pytest -p no:cacheprovider "$@"
}
```

现场命令统一使用这些已知输入，并在任何 live run 前逐项 read-back；文件或 digest 不匹配时
停止，不自行替换模型：

```zsh
worktree=/data/work/ws_moveit/.worktrees/parallel-w8-admission-v2
point_catalog="$worktree/src/so101_demo_py/config/mujoco/moveit_expert_validation_points_v1.yaml"
v2_config="$worktree/src/so101_demo_py/config/mujoco/parallel_batch_v2.yaml"
broker_image=so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1
yolo_weights=/data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt
yolo_sha256=f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
grounded_root=/data/work/so101-models/grounded-sam-v2-scipy-lock
grounded_sha256=0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
```

### Task 1: 冻结 v2 配置并保持 v1 兼容

**Files:**
- Create: `src/so101_demo_py/config/mujoco/parallel_batch_v2.yaml`
- Create: `src/so101_demo_py/config/mujoco/parallel_admission_profiles_v1.yaml`
- Modify: `src/so101_demo_py/src/parallel_batch/contracts.py`
- Test: `src/so101_demo_py/test/test_parallel_batch_v2_contracts.py`
- Test: `src/so101_demo_py/test/test_parallel_batch_contracts.py`

**Interfaces:**
- Produces: `ParallelRuntimeConfigV2`, `AdmissionMode`, `load_parallel_runtime_config(path) -> ParallelRuntimeConfig | ParallelRuntimeConfigV2`.
- Produces: `BatchRequest.schema_version: int = 1`; schema 1 上限 3，schema 2 上限 8。
- Consumes: spec 第 4 节全部冻结字段。

- [ ] **Step 1: 写 v2 RED tests**

覆盖以下断言：

```python
config = load_parallel_runtime_config(V2_CONFIG)
assert config.schema_version == 2
assert config.max_worker_count == 8
assert config.ros_domain_ids == tuple(range(215, 223))
assert config.fastdds_transport == "udp_v4_loopback_only"
assert config.fastdds_data_sharing is False
assert config.max_dds_participants_per_worker == 32
assert config.max_unix_socket_path_bytes == 107
assert config.qualification_worker_stages == (1, 2, 4, 6, 8)
assert config.qualification_canary_rounds_per_stage == 3

request = BatchRequest(
    "w8-contract", RunMode.EXECUTE, tuple(f"P{i:02d}" for i in range(1, 21)),
    8, 3, Path("/tmp/w8-contract"), schema_version=2,
)
assert request.worker_count == 8
with pytest.raises(ContractError, match="MAX_WORKER_COUNT"):
    replace(request, worker_count=9)
```

参数化 N=1..8，断言 normal 模式四种 Worker 计数都必须等于请求 N；qualification 对 N!=8
返回 `EXACT_WORKER_COUNT_REQUIRED`，W8 的任一计数为 7 都拒绝。同时加载 v1 并断言 W4 仍返回 `MAX_WORKER_COUNT`。逐字段篡改 v2，断言
`FROZEN_RUNTIME_VALUE`。

- [ ] **Step 2: 运行 RED**

为本任务创建 `scratch/task-01-red/tmp`，设置 `TMPDIR/TMP/TEMP`，用 `/usr/bin/python3`
回读后运行两个 contract 文件。预期：v2 类型或配置不存在导致失败。

- [ ] **Step 3: 实现严格 v2 loader**

保留现有 `ParallelRuntimeConfig` 作为 v1。新增独立 frozen dataclass
`ParallelRuntimeConfigV2`，显式列出字段并校验 exact values。不要放宽 v1 的
`_FROZEN_RUNTIME_VALUES`。`BatchRequest` 新增末尾默认字段 `schema_version=1`，按 schema
选择最大 Worker 数。

repo-tracked 文件只是签名 profile 的审计索引，不是 live 授权源。初始内容只声明 schema 和
空的 accepted profiles：

```yaml
schema_version: 1
profiles: {}
```

- [ ] **Step 4: 运行 GREEN 和 v1 回归**

运行 Task 1 两个测试文件，要求全部通过、实际收集数非零。

- [ ] **Step 5: 提交**

```zsh
git add src/so101_demo_py/config/mujoco/parallel_batch_v2.yaml \
  src/so101_demo_py/config/mujoco/parallel_admission_profiles_v1.yaml \
  src/so101_demo_py/src/parallel_batch/contracts.py \
  src/so101_demo_py/test/test_parallel_batch_v2_contracts.py \
  src/so101_demo_py/test/test_parallel_batch_contracts.py
git commit -m "feat: freeze parallel batch v2 contract"
```

### Task 2: 实现八 Domain 原子池

**Files:**
- Create: `src/so101_demo_py/src/parallel_batch/domain_pool.py`
- Create: `src/so101_demo_py/config/mujoco/fastdds_parallel_udp_only.xml`
- Modify: `src/so101_demo_py/src/parallel_batch/resources.py`
- Test: `src/so101_demo_py/test/test_parallel_domain_pool.py`
- Test: `src/so101_demo_py/test/test_parallel_batch_resources.py`

**Interfaces:**
- Produces: `DomainPool.claim_all(batch_id: str, domains: tuple[int, ...]) -> DomainReservation`.
- Produces: `DomainReservation.receipts`, `DomainReservation.release_after_quiet()`.
- Consumes: `SystemResourceProbe` process identity helpers; does not trust timestamps.

- [ ] **Step 1: 写原子性和崩溃竞态 RED tests**

测试使用精确的 v1 root `/run/user/<uid>/so101-parallel-domain-claims/domain-<id>.lock`：
qualification 取得八个 lock、normal N 取得映射表前 N 个、第四个冲突时前三个回滚、不可读 ROS 候选失败、旧 Worker 持有 Domain 时拒绝、
quiet probe 后按序释放。receipt 必须含 boot ID 和 process start ticks。增加 Fast DDS 配置哈希、
SHM/Data Sharing 禁用、participant=33 拒绝和跨 Domain graph 不可见测试。
用固定现场 root 分别枚举 `b/s`、`b/q`、`b/n` 的 allocator `ipc/<slot>/s`、worker、control、
Broker perception/authority、Authority、watchdog 和 replacement 全部真实 socket template，断言
最长 UTF-8 路径 `<=107` bytes；构造 108-byte 路径必须在创建目录或进程前拒绝。

- [ ] **Step 2: 运行 RED**

在 `scratch/task-02-red/tmp` 运行 `test_parallel_domain_pool.py`。预期导入失败。

- [ ] **Step 3: 实现 `DomainPool`**

复用 v1 owner-controlled 0700 claim root 与 lock inode，使用 0600 regular file、`O_NOFOLLOW` 和 non-blocking
`flock`。先锁全部请求 Domain，再执行 `/proc` 与 direct DDS graph probe。任何检查失败都关闭
本轮已取得 FD。qualification 的 reservation handle 由独立 watchdog 进程持有，而非
Coordinator；释放前检查 owned process 已停、DDS quiet window 通过。

- [ ] **Step 4: 接入 `WorkerResourceAllocator`**

v1 保留当前前三个 Domain 行为；v2 qualification 总是预留八个，normal N 在启动前原子预留
映射表前 N 个，不能在运行中追加。worker resource manifest 只按阶段逐步 materialize slot，
保存全部 claim receipt 和当前 started slots。

- [ ] **Step 5: 运行 GREEN 和资源回归**

运行新 Domain tests 与现有 `test_parallel_batch_resources.py`，要求全通过。

- [ ] **Step 6: 提交**

```zsh
git add src/so101_demo_py/src/parallel_batch/domain_pool.py \
  src/so101_demo_py/config/mujoco/fastdds_parallel_udp_only.xml \
  src/so101_demo_py/src/parallel_batch/resources.py \
  src/so101_demo_py/test/test_parallel_domain_pool.py \
  src/so101_demo_py/test/test_parallel_batch_resources.py
git commit -m "feat: reserve eight ROS domains atomically"
```

### Task 3: 建立 cgroup v2 隔离

**Files:**
- Create: `src/so101_demo_py/src/parallel_batch/cgroups.py`
- Create: `src/so101_demo_py/src/parallel_batch/watchdog.py`
- Create: `src/so101_demo_py/src/cli/parallel_batch_watchdog.py`
- Create: `scripts/so101-parallel-systemd-cgroup.sh`
- Create: `deploy/systemd/so101-parallel-watchdog@.service`
- Modify: `src/so101_demo_py/src/parallel_batch/resources.py`
- Modify: `src/so101_demo_py/setup.py`
- Test: `src/so101_demo_py/test/test_parallel_cgroups.py`
- Test: `src/so101_demo_py/test/test_parallel_watchdog.py`

**Interfaces:**
- Produces: `CgroupCapabilityProbe.run() -> CgroupCapabilityReceipt`.
- Produces: `CgroupLayout.create(batch_id: str, limits: CgroupLimits) -> CgroupLayout`.
- Produces: `start_coordinator_scope()`, `start_monitor_scope()`, `docker_parent_slice()`, `start_worker_scope(slot)`, `verify_descendants()`, `snapshot()` and `close()`.
- Produces: `BatchWatchdog`，持有 Domain FD/cgroup ownership，以 pidfd/systemd unit 状态监视 Coordinator、monitor、Authority，执行 root-owned terminal/cleanup。
- Produces: root-owned pending terminal/pending revocation records，必须在停止 owned leaf 前 fsync。
- Consumes: topology probe and v2 resource fields.

- [ ] **Step 1: 写伪 cgroup 文件系统 RED tests**

验证 systemd driver、system manager 权限、空 parent slice、leaf scope、Docker parent 不能是 scope、
no-internal-process、20/4 CPU 拆分、24 GiB memory.max、swap=0、control `MemoryLow=1G`、八 scope、
PID enrollment、descendant 逃逸、稳定读回和幂等 close。权限不足必须返回
`CGROUP_DELEGATION_UNAVAILABLE`，不能降级。
验证 watchdog 而非 Coordinator 持有 Domain FD 与 slice 生命周期；Coordinator、monitor、
Authority 任一死亡都会写 pending terminal、终止 owned leaf、quiet-check、释放 Domain 并清理 slice。

- [ ] **Step 2: 运行 RED**

在 `scratch/task-03-red/tmp` 运行新测试，预期导入失败。

- [ ] **Step 3: 实现 cgroup 边界**

把 systemd/Docker/cgroup IO 封装在可注入 backend 中。使用 spec §7 的空 batch/control/
broker/workers slice 与独立 leaf scope；CPU 拓扑选择保留四个 SMT 对称逻辑 CPU 给 control，
其余 20 给 workers；实际 CPU 列表写 manifest。先执行无模型/无 ROS capability smoke，所有
PID 必须在副作用前进入目标 leaf 并回读。

- [ ] **Step 4: 接入 Worker 与 Broker 启动前门**

Worker launcher 在创建 ROS context 前进入 worker scope。Docker Broker 的
`--cgroup-parent` 指向空 broker slice，不指向有进程的 scope；容器 PID 启动后由 allocator
回读。Coordinator 与 monitor 分属 leaf，monitor 不进入 broker/worker OOM leaf。任何失败返回
`CGROUP_ENROLLMENT_FAILED`。

在 `setup.py` 注册 `so101_parallel_batch_watchdog =
so101_demo.cli.parallel_batch_watchdog:main`。systemd template 只调用 install space 的该入口，不
从 source tree 直接 import。

- [ ] **Step 5: 运行 GREEN**

运行 `test_parallel_cgroups.py` 和资源测试，要求全通过。

- [ ] **Step 6: 提交**

```zsh
git add src/so101_demo_py/src/parallel_batch/cgroups.py \
  src/so101_demo_py/src/parallel_batch/watchdog.py \
  src/so101_demo_py/src/cli/parallel_batch_watchdog.py \
  scripts/so101-parallel-systemd-cgroup.sh \
  deploy/systemd/so101-parallel-watchdog@.service \
  src/so101_demo_py/src/parallel_batch/resources.py \
  src/so101_demo_py/setup.py \
  src/so101_demo_py/test/test_parallel_cgroups.py \
  src/so101_demo_py/test/test_parallel_watchdog.py
git commit -m "feat: isolate W8 process trees with cgroup v2"
```

### Task 4: 实现资源监视器和熔断判定

**Files:**
- Create: `src/so101_demo_py/src/parallel_batch/resource_monitor.py`
- Modify: `src/so101_demo_py/src/parallel_batch/resources.py`
- Modify: `src/so101_demo_py/src/parallel_batch/worker.py`
- Modify: `src/so101_demo_py/src/runtime/parallel_worker_runtime.py`
- Modify: `src/so101_demo_py/src/runtime/parallel_ros_runtime.py`
- Modify: `src/so101_demo_py/src/runtime/parallel_ipc.py`
- Test: `src/so101_demo_py/test/test_parallel_resource_monitor.py`
- Test: `src/so101_demo_py/test/test_parallel_worker_runtime.py`
- Test: `src/so101_demo_py/test/test_parallel_ros_runtime.py`
- Test: `src/so101_demo_py/test/test_parallel_ipc.py`

**Interfaces:**
- Produces: `ResourceMonitor.start()`, `mark_stage(name, phase)`, `snapshot_window(stage)`, `stop()`.
- Produces: `ResourceDecision(kind: OK | SOFT_STOP | HARD_STOP, reasons: tuple[str, ...])`.
- Produces: `HardStopEvidence(profile_id, batch_id, reason, clean_host_window_sha256, raw_metrics_sha256)`.
- Produces: `ParallelRuntimeMetricsProbe` and `WorkerRuntimeMetricsSample` wire message.
- Consumes: `CgroupLayout.snapshot()`, NVML probe, Broker metrics and Worker runtime metrics.
- Consumes production topics: `/so101/simulation/physics_step_chunks`, `/task_camera/color`, `/joint_states`.

- [ ] **Step 1: 写时间序列 RED tests**

逐项实现 spec §7.4 表格，用 fake monotonic clock 验证来源、单位、窗口、0.5 秒采样、1.0 秒
最大间隔、缺样失败、CPU/PSI/RAM/GPU、realtime factor p05、render FPS p05、断帧、controller
deadline、进程逃逸及各自 SOFT/HARD 动作。验证所有指标连续 10 秒低于软门才恢复，30 秒不能
恢复则 HARD_STOP。任何生产指标接口缺失都 fail closed。
用真实 ROS message 类型的 deterministic callbacks 验证：physics chunk 计算 simulation/wall
realtime factor；color source/receive stamp 计算 FPS/断帧；100 Hz `/joint_states` 在非 pause/reset
窗口出现 `>0.05 s` source 或 receive gap 时累计 miss。验证 worker control IPC 的身份、sequence、
断线和旧 generation fencing。
增加真实消息 callback + reset 生命周期测试：已 journal 的当前 attempt 发送
`MeasurementResetBegin` 后，20 秒内匹配的 `ResetReceipt(reset_epoch=previous+1)` 才能 commit；
三类 runtime topic 允许记 `EXPECTED_RESET_GAP`，但 host/cgroup/GPU 采样不能中断。commit 后
5 秒内三类 topic 都恢复并建立 baseline，Worker metrics wire sequence 连续，才可进入 barrier/
EXECUTING。超时、epoch 跳变/重放、session 改变、topic 缺失全部 HARD_STOP。
生产顺序必须断言为 reset authorization/begin → reset/paused initial gate →
`resume_physics()` unpaused readback → commit → rebaseline/ACK → capture 或 canary barrier。

- [ ] **Step 2: 运行 RED**

在 `scratch/task-04-red/tmp` 运行新测试，预期导入失败。

- [ ] **Step 3: 实现采样与不可变窗口**

监视器使用独立线程和 bounded queue。原始 NDJSON 只追加；阶段结束后生成包含 sample count、
missing count、min/max/p05/p95/p99 的 sealed summary。不能用缺样补零。

- [ ] **Step 4: 接入 fail-closed callback**

SOFT_STOP 只阻止新 lease；HARD_STOP 先持久化原因，再请求独立 watchdog `abort_batch`，并让
现有 supervisor 走协作式停止。即使 Coordinator/supervisor 随后死亡，watchdog 仍完成清理。
保留 attempt 的 `INVALID/INDETERMINATE` 既有裁决。
normal 使用 accepted profile 时，watchdog 必须在清理前把 `HardStopEvidence` 写入 pending
failure；不能因 Authority 当时不可用而丢失撤销候选。

- [ ] **Step 5: 运行 GREEN**

运行新监视器测试与现有 resource/coordinator tests。

- [ ] **Step 6: 提交**

```zsh
git add src/so101_demo_py/src/parallel_batch/resource_monitor.py \
  src/so101_demo_py/src/parallel_batch/resources.py \
  src/so101_demo_py/src/parallel_batch/worker.py \
  src/so101_demo_py/src/runtime/parallel_worker_runtime.py \
  src/so101_demo_py/src/runtime/parallel_ros_runtime.py \
  src/so101_demo_py/src/runtime/parallel_ipc.py \
  src/so101_demo_py/test/test_parallel_resource_monitor.py \
  src/so101_demo_py/test/test_parallel_worker_runtime.py \
  src/so101_demo_py/test/test_parallel_ros_runtime.py \
  src/so101_demo_py/test/test_parallel_ipc.py
git commit -m "feat: monitor W8 resource envelopes"
```

### Task 5: 实现同批次五级 qualification 状态机

**Files:**
- Create: `src/so101_demo_py/src/parallel_batch/qualification.py`
- Modify: `src/so101_demo_py/src/parallel_batch/journal.py`
- Modify: `src/so101_demo_py/src/parallel_batch/coordinator.py`
- Test: `src/so101_demo_py/test/test_parallel_qualification.py`

**Interfaces:**
- Produces: `QualificationCoordinator.advance(event) -> QualificationSnapshot`.
- Produces: `QualificationStage(target_workers, completed_rounds, accepted, rejection_reason)`.
- Consumes: frozen stages `(1, 2, 4, 6, 8)` and three canary rounds.

- [ ] **Step 1: 写状态转移 RED tests**

验证不能跳级、倒退、少启动 Worker、少 canary round 或失败后继续。使用真实子进程逐一
SIGKILL Coordinator、monitor 和测试 Authority。qualification 在
barrier release、stage seal、provisional 和 queue-open 边界崩溃时必须 fence、受控清理并永久
terminal invalid；断言 watchdog 的 pending terminal、子进程归零、cgroup/Domain 释放；同一
batch 不能 resume，重试必须换 batch 并从 stage 1 开始。这些集成测试不启动 ROS/MuJoCo。

- [ ] **Step 2: 运行 RED**

在 `scratch/task-05-red/tmp` 运行 qualification 与 journal 测试。

- [ ] **Step 3: 实现状态机和事件**

新增 `QUALIFICATION_STARTED`、`STAGE_WORKERS_READY`、`CANARY_BARRIER_RELEASED`、
`CANARY_ROUND_SEALED`、`STAGE_ACCEPTED`、`STAGE_REJECTED`、
`PRODUCTION_QUEUE_OPENED`。事件先 fsync 后产生授权。

- [ ] **Step 4: 接入 Coordinator 队列门**

v2 qualification 在 `PRODUCTION_QUEUE_OPENED` 前不得为正式点发 lease。v1 继续走现有直接
队列路径。W8 正式阶段 ready slot 少于八时暂停发 lease。

- [ ] **Step 5: 运行 GREEN**

运行 qualification、journal、coordinator 和 crash recovery tests。

- [ ] **Step 6: 提交**

```zsh
git add src/so101_demo_py/src/parallel_batch/qualification.py \
  src/so101_demo_py/src/parallel_batch/journal.py \
  src/so101_demo_py/src/parallel_batch/coordinator.py \
  src/so101_demo_py/test/test_parallel_qualification.py
git commit -m "feat: add staged W8 qualification state machine"
```

### Task 6: 隔离 canary attempt 与正式结果

**Files:**
- Modify: `src/so101_demo_py/src/parallel_batch/contracts.py`
- Modify: `src/so101_demo_py/src/parallel_batch/worker.py`
- Modify: `src/so101_demo_py/src/parallel_batch/artifacts.py`
- Test: `src/so101_demo_py/test/test_parallel_qualification.py`
- Test: `src/so101_demo_py/test/test_parallel_batch_worker.py`
- Test: `src/so101_demo_py/test/test_parallel_batch_artifacts.py`

**Interfaces:**
- Produces: `ExecutionKind.QUALIFICATION_CANARY` and `CanaryIdentity(stage, round_id, worker_id, generation)`.
- Produces: barrier-ready and executing interval events.
- Consumes: existing point initial gate、pose admission、runtime execute、recovery gate。

- [ ] **Step 1: 写统计隔离 RED tests**

三轮 W8 canary 全通过时，正式 `point_statuses` 仍为空；canary 失败不能成为 point FAILED；
正式 20 点不能读取 canary pose、reset epoch 或 result manifest。

- [ ] **Step 2: 运行 RED**

运行三个目标测试文件，确认预期失败。

- [ ] **Step 3: 实现 canary workspace 和 barrier**

目录固定为 `qualification/stage-NN/round-NN/worker-NN/`。Worker 到 barrier 后先写 ready event；
收到当前 epoch 的 release ACK 才执行。保存 `executing_started_monotonic` 和
`executing_finished_monotonic`，Authority 计算 N 路交集。

- [ ] **Step 4: 复用完整 pick-place/recovery 但隔离 projection**

canary 走现有 YOLO-first 和物理证据链，结束后必须恢复；projection reducer 对
`QUALIFICATION_CANARY` 只更新 qualification，不更新正式 point summary。

保留 v1 FULL_RESTART recovery。增加经过真实 `ParallelWorker.run()` → `_recover()` →
`RosWorkerRuntimePorts.recover()`/`parallel_worker_runtime.py` 生产调用链的无 ROS 子进程集成测试：
Coordinator 先 fsync 120 秒 recovery deadline 和 `MeasurementRecoveryBegin`；外层 Worker 在
owned stack shutdown/restart 期间继续 slot heartbeat，三类 topic 只记
`EXPECTED_RECOVERY_GAP`，全局资源采样不中断。新 generation/session 完成 graph、paused gate、
resume、ready 后 commit，5 秒内 rebaseline/ACK 才重新 AVAILABLE。覆盖 deadline、旧 stack
残留、identity 漂移、topic 不恢复和 ACK 缺失；K 不能退款。

- [ ] **Step 5: 运行 GREEN 并提交**

```zsh
git add src/so101_demo_py/src/parallel_batch/contracts.py \
  src/so101_demo_py/src/parallel_batch/worker.py \
  src/so101_demo_py/src/parallel_batch/artifacts.py \
  src/so101_demo_py/test/test_parallel_qualification.py \
  src/so101_demo_py/test/test_parallel_batch_worker.py \
  src/so101_demo_py/test/test_parallel_batch_artifacts.py
git commit -m "feat: isolate W8 canary evidence"
```

### Task 7: 扩展 Broker 到八 Worker

**Files:**
- Modify: `src/so101_demo_py/src/parallel_batch/broker.py`
- Modify: `src/so101_demo_py/src/parallel_batch/worker.py`
- Modify: `src/so101_demo_py/src/cli/parallel_perception_broker.py`
- Modify: `src/so101_demo_py/src/cli/mujoco_parallel_batch.py`
- Modify: `src/so101_demo_py/src/runtime/parallel_ros_runtime.py`
- Modify: `src/so101_demo_py/src/runtime/parallel_ipc.py`
- Test: `src/so101_demo_py/test/test_parallel_batch_broker.py`
- Test: `src/so101_demo_py/test/test_parallel_batch_perception.py`
- Test: `src/so101_demo_py/test/test_parallel_batch_worker.py`
- Test: `src/so101_demo_py/test/test_parallel_batch_cli.py`
- Test: `src/so101_demo_py/test/test_parallel_ros_runtime.py`
- Test: `src/so101_demo_py/test/test_parallel_ipc.py`

**Interfaces:**
- Produces: `BrokerMetricsSnapshot` with per-model queue depth、per-worker wait、inference p99 and generation.
- Produces wire types: `BrokerTicketRequest`, `CaptureNowGrant`, `BrokerFrameRequest` and fenced replies.
- Produces proxy API: `acquire_ticket(model, lease_identity) -> CaptureNowGrant` and `submit_frame(grant, snapshot) -> BrokerResponse`.
- Consumes: v2 queue capacity 8、10/30 秒 ticket timeout、0.5 秒 capture submit 和 spec §8 的 frame freshness deadline。

- [ ] **Step 1: 写八 Worker 公平性 RED tests**

同时提交八个不含图像的 YOLO ticket，断言每 Worker 最多一个在途、轮转无饥饿、只有当前
`CAPTURE_NOW` 可在 0.5 秒内提交 frame、fenced ticket/frame 不进入 pose admission。再覆盖八个
Grounded-SAM ticket、YOLO/Grounded 混合队列、10/30 秒 ticket timeout、每种至少 24 个完成
样本、缺失 p99、capture 后 freshness budget 和 pose admission 最终帧龄。fallback 必须新建
ticket 并重新 capture，不能复用 YOLO 帧。

- [ ] **Step 2: 运行 RED**

运行 broker/perception、Worker、CLI、ROS runtime 和 IPC tests，确认新增断言失败。

- [ ] **Step 3: 实现指标和 deadline**

保持模型 outcome 矩阵不变。实现 spec §8 的两阶段 ticket/CAPTURE_NOW 协议与 freshness
deadline：YOLO/Grounded p99 ceiling 分别为 2.0/4.0 秒，保留 0.25 秒 commit，pose admission
帧龄严格 `<5.0 s`。把 ticket queue、capture、inference start/end 写入 bounded metrics stream；响应返回前继续检查 lease、
broker generation 和最终帧龄。专用 Broker canary 产生 fallback 压力，不伪造正式感知失败。

生产调用链必须端到端改造：Worker 不在 ticket 前调用 `inference_snapshot()`；
`_WorkerBrokerProxy` 不再把一个 snapshot 捕获进两个模型闭包；`run_perception_chain()` 接收按
模型调用的 capture callback，并为 fallback 重新锁存对齐 RGB-D/TF、stamp 和 hash；
`BrokerTransport` 实现 ticket/grant/frame 三类 wire schema。v1 仍走原单请求协议。增加经过
真实 proxy + transport + runtime 的无 ROS 集成测试，证明 YOLO 与 fallback 使用不同 capture
identity，且 admission latch 对应最终模型的新帧。

- [ ] **Step 4: 运行 GREEN 和 v1 回归**

运行上述全部测试和 v1 回归。

- [ ] **Step 5: 提交**

```zsh
git add src/so101_demo_py/src/parallel_batch/broker.py \
  src/so101_demo_py/src/parallel_batch/worker.py \
  src/so101_demo_py/src/cli/parallel_perception_broker.py \
  src/so101_demo_py/src/cli/mujoco_parallel_batch.py \
  src/so101_demo_py/src/runtime/parallel_ros_runtime.py \
  src/so101_demo_py/src/runtime/parallel_ipc.py \
  src/so101_demo_py/test/test_parallel_batch_broker.py \
  src/so101_demo_py/test/test_parallel_batch_perception.py \
  src/so101_demo_py/test/test_parallel_batch_worker.py \
  src/so101_demo_py/test/test_parallel_batch_cli.py \
  src/so101_demo_py/test/test_parallel_ros_runtime.py \
  src/so101_demo_py/test/test_parallel_ipc.py
git commit -m "feat: scale perception broker to eight workers"
```

### Task 8: 实现 AdmissionAuthority 与画像验证

**Files:**
- Create: `src/so101_demo_py/src/parallel_batch/admission.py`
- Create: `src/so101_demo_py/src/cli/parallel_admission_authority.py`
- Create: `src/so101_demo_py/config/mujoco/so101_admission_authority_ed25519.pub`
- Create: `deploy/systemd/so101-admission-authority.service`
- Create: `scripts/install-so101-admission-authority.sh`
- Modify: `src/so101_demo_py/src/parallel_batch/resources.py`
- Modify: `src/so101_demo_py/setup.py`
- Test: `src/so101_demo_py/test/test_parallel_admission.py`
- Test: `src/so101_demo_py/test/test_parallel_batch_resources.py`

**Interfaces:**
- Produces: `AdmissionAuthority.verify_stage(batch_id: str, nonce: str) -> StageAcceptance`，stage 由 Authority 推导；仅 stage=8 返回 `ProvisionalAdmission`.
- Produces: `AdmissionAuthority.verify_profile(batch_id: str, nonce: str) -> W8AdmissionProfile`.
- Produces: `AdmissionAuthority.revoke(profile_id: str, reason: str, evidence_sha256: str) -> RevocationReceipt`.
- Produces: `AdmissionAuthority.consume_pending_failures()` and `CleanHostWindowReceipt`.
- Produces: `AcceptedProfileRegistry.resolve(profile_id: str) -> AcceptedProfileIdentity`.
- Produces: `RuntimeContentIdentity.from_allowlist(repo_root) -> RuntimeContentIdentity`.
- Consumes: registry-owned batch root、sealed stage summaries、runtime provenance 和 frozen thresholds。

- [ ] **Step 1: 写不可信输入 RED tests**

验证 Authority 拒绝调用者路径、调用者 stage/阈值、自签或伪造 acceptance、registry 篡改、
错误 peer credential/nonce/Ed25519 signature、symlink、inode 替换、缺样、哈希不符、八路执行无重叠和
provenance 漂移。验证 revoke 在服务重启后仍拒绝，画像没有时间过期字段或 age gate。
验证 source/install 的同一逻辑 allowlist 排除 docs/evidence/ledger/profile/registry/Git commit，提交 profile 后 identity 不变，
而 Python、launch、Docker input、运行配置、策略或场景任一变化都拒绝。增加两个真实 UID 的
无 ROS smoke，验证 ACL 读桥、候选不能写 `/var/lib/so101-admission`、Authority 不写 candidate
root、symlink/inode 替换 fail closed。
验证 Authority 启动和每次 register/normal admission 前先消费 pending failures；存在无法验证的
pending record 时返回 `PENDING_REVOCATION_UNPROCESSED`。clean-host normal 的 OOM、GPU Xid、
controller miss、cgroup escape 或资源硬门必须持久 revoke；检测到 foreign workload 的同类失败
只拒绝当前 batch，不撤销 profile。

- [ ] **Step 2: 运行 RED**

在 `scratch/task-08-red/tmp` 运行新测试，预期导入失败。

- [ ] **Step 3: 实现 secure read 和重新计算**

实现 system-managed `so101-admission` 专用用户服务。权威 registry/revocation/acceptance 放在
`/var/lib/so101-admission/`，候选无写权限；Unix socket 用 `SO_PEERCRED` 和允许组认证，登记时
生成 nonce。evidence root/目录保持操作员 0700；对固定路径目录只授予 Authority `--x` ACL，
对 writer 已关闭的 regular file 只授予 `r--` ACL。Authority 不列举目录、不写 candidate root，
而是复制到自有 staging；socket 响应由 Coordinator 写入 receipts。响应使用 Authority-only Ed25519 私钥签名 batch/epoch/nonce/request，客户端只持有
固定公钥。使用 `O_NOFOLLOW`、目录 FD、大小上限、前后 stat；候选 writer close 后由 Authority
复制到自有 staging 并 fsync/rename seal。由原始样本重新计算分位数和 headroom，不信任
候选 summary 中的布尔结果。

安装脚本首次运行时把私钥生成到 root/Authority-only 路径，只导出公钥到仓库路径。公钥经审查
提交后，脚本再次安装并回读运行 fingerprint；代码只信任 repo 固定公钥。实现固定 runtime
content allowlist manifest 和 canonical SHA256；install space 对映射后的同一 allowlist 计算，
不哈希整个 install tree；`implementation_commit` 只记审计信息。

Authority/watchdog 服务必须从已审查 commit 构建 wheel，非 editable、非 symlink 地安装到
`/opt/so101-w8-admission/releases/<runtime_content_sha256>/venv`。root 拥有 release、解释器、
依赖、unit 和配置；systemd 用绝对解释器加 `-I -s`、`WorkingDirectory=/`、空 `PYTHONPATH`、
禁用 user site。安装测试枚举实际 module `__file__`，要求全部位于 root-owned release、无
symlink 且 candidate UID 不可写；候选还不能改 unit/key/registry/pending。服务启动时复核
release manifest hash，失败则 `AUTHORITY_UNAVAILABLE`/`WATCHDOG_UNAVAILABLE`。

- [ ] **Step 4: 实现 provisional/final 输出**

StageAcceptance 绑定 Authority 推导的 stage；provisional 只允许 stage=8，绑定 batch、epoch、
三轮 canary、config/runtime-content hash。final profile 绑定
五级指标、正式结果和 cleanup，但分别输出 `resource_profile_accepted` 与
`qualification_passed`。

- [ ] **Step 5: 注册 CLI 并运行 GREEN**

在 `setup.py` 注册：

```python
"so101_parallel_admission_authority = "
"so101_demo.cli.parallel_admission_authority:main"
```

运行 admission tests，要求全通过。

- [ ] **Step 6: 提交**

```zsh
git add src/so101_demo_py/src/parallel_batch/admission.py \
  src/so101_demo_py/src/cli/parallel_admission_authority.py \
  src/so101_demo_py/config/mujoco/so101_admission_authority_ed25519.pub \
  deploy/systemd/so101-admission-authority.service \
  scripts/install-so101-admission-authority.sh \
  src/so101_demo_py/src/parallel_batch/resources.py \
  src/so101_demo_py/setup.py \
  src/so101_demo_py/test/test_parallel_admission.py \
  src/so101_demo_py/test/test_parallel_batch_resources.py
git commit -m "feat: verify independent W8 admission profiles"
```

### Task 9: 接入 CLI、启动扩容和 normal profile

**Files:**
- Modify: `src/so101_demo_py/src/cli/mujoco_parallel_batch.py`
- Modify: `src/so101_demo_py/src/parallel_batch/coordinator.py`
- Test: `src/so101_demo_py/test/test_parallel_batch_cli.py`
- Test: `src/so101_demo_py/test/test_parallel_qualification.py`

**Interfaces:**
- Produces CLI flags: `--admission-mode {qualification,normal}` and `--admission-profile-id`.
- Consumes: v2 config、DomainPool、CgroupLayout、ResourceMonitor、QualificationCoordinator 和 Authority client。

- [ ] **Step 1: 写 CLI RED tests**

覆盖 v1 不接受 v2 flags、normal N=1..8 四计数精确相等、qualification 预留 8 Domain、normal
预留前 N 个 Domain、W4–W8 normal 缺 profile；验证 N=4/5/6/7/8 分别选择 stage
4/6/6/8/8 envelope。覆盖 W8 qualification 非 8 请求、请求 8 实际只启动 7、阶段跳过、provisional 缺失、revoked profile
和 profile drift。实现并测试精确的
`--stop-after {CREATE_CGROUPS,METRICS_READY_1}` 枚举选项；后者在 W1 runtime 连续采集 31 秒
生产指标后受控清理，二者都不创建正式 point attempt。错误码必须进入 stderr 与 summary。

- [ ] **Step 2: 运行 RED**

运行 `test_parallel_batch_cli.py` 和 qualification tests。

- [ ] **Step 3: 实现 v2 composition**

把 3060 行 CLI 中新增的 v2 编排放进 `qualification.py`/`admission.py`，CLI 只做解析、严格
composition 和生命周期调用。v1 `_prepare_live_headroom` 三 Worker 路径不改语义。

- [ ] **Step 4: 实现 normal 快速启动**

normal N 复核 Authority-owned registry/profile/current provenance，按
`startup_stages(N)=[s in (1,2,4,6) if s<N]+[N]` 累积启动；明确测试 N=3/5/7 分别为
`1,2,3`、`1,2,4,5`、`1,2,4,6,7`。每级只做 10 秒空载稳定检查，不运行 canary；N 个 Worker
全部 ready 后开放正式队列。

- [ ] **Step 5: 运行 GREEN 和 CLI 全回归**

运行 CLI、contracts、resources、coordinator、qualification tests。

- [ ] **Step 6: 提交**

```zsh
git add src/so101_demo_py/src/cli/mujoco_parallel_batch.py \
  src/so101_demo_py/src/parallel_batch/coordinator.py \
  src/so101_demo_py/test/test_parallel_batch_cli.py \
  src/so101_demo_py/test/test_parallel_qualification.py
git commit -m "feat: compose W8 qualification and normal admission"
```

### Task 10: 维持 W8 容量并恢复故障 slot

**Files:**
- Modify: `src/so101_demo_py/src/parallel_batch/coordinator.py`
- Modify: `src/so101_demo_py/src/parallel_batch/worker.py`
- Modify: `src/so101_demo_py/src/parallel_batch/journal.py`
- Modify: `src/so101_demo_py/src/runtime/parallel_ipc.py`
- Modify: `src/so101_demo_py/src/cli/mujoco_parallel_batch.py`
- Test: `src/so101_demo_py/test/test_parallel_qualification.py`
- Test: `src/so101_demo_py/test/test_parallel_batch_crash_recovery.py`

**Interfaces:**
- Produces: `pause_reason=W8_CAPACITY_LOST_PENDING_REPLACEMENT` and terminal `W8_CAPACITY_LOST`.
- Produces: `SlotHeartbeat`/`SlotHeartbeatAck` RPC，独立于 LeaseIdentity，1 秒发送、5 秒超时，只证明 slot 存活。
- Consumes: existing `worker_generation` fencing、Domain reservation 和 ready gate。

- [ ] **Step 1: 写 replacement RED tests**

定义 `slot_healthy` 与 `lease_eligible` 两个独立 predicate。覆盖首次领点前、K 用尽后、active
lease 同时发两类 heartbeat，以及旧 epoch/generation/session/sequence 被 fence；slot heartbeat
不得创建或续租 lease、授权动作或改变 K。覆盖首波同时八个 lease、20 点尾部
少于八点、四点 normal、Worker 暂时无点、K 用尽仍 heartbeat 等待 terminal。W8 正式队列中
杀掉一个 idle Worker，断言不再发新 lease；旧 generation fenced，replacement 沿用 Domain、
继承 slot 在 `LEASE_GRANTED` 已持久化的 `lease_count` 并通过 ready 后恢复；初始门失败、ACK
丢失、执行中崩溃、INVALID/INDETERMINATE 都不能退款。超时则 terminal，不能以七 Worker
继续，也不能通过 replacement 重置 K。normal N=3/5/7 分别丢失一个 slot 时只恢复至 N，不能
无条件启动八个。

- [ ] **Step 2: 运行 RED**

运行 qualification/crash recovery tests。

- [ ] **Step 3: 实现暂停、换代和超时**

先设置 `required_healthy_slots=requested_worker_count` 并持久化容量丢失事件，再暂停 dispatcher。`AVAILABLE/LEASED/INITIALIZING/EXECUTING/FINALIZING`
且 heartbeat/resource identity 正常都计作健康；只有 AVAILABLE 且 K 未用尽才可领 lease。
Worker 在 `BATCH_TERMINAL` 前不因空队列或 K 用尽退出，走独立 slot heartbeat IPC。已有
attempt 按原规则完成；replacement 使用同 slot resource identity、新 session ID、递增
generation 和不可重置的已授予 lease counter。

- [ ] **Step 4: 运行 GREEN 并提交**

```zsh
git add src/so101_demo_py/src/parallel_batch/coordinator.py \
  src/so101_demo_py/src/parallel_batch/worker.py \
  src/so101_demo_py/src/parallel_batch/journal.py \
  src/so101_demo_py/src/runtime/parallel_ipc.py \
  src/so101_demo_py/src/cli/mujoco_parallel_batch.py \
  src/so101_demo_py/test/test_parallel_qualification.py \
  src/so101_demo_py/test/test_parallel_batch_crash_recovery.py
git commit -m "feat: preserve exact W8 runtime capacity"
```

### Task 11: 扩展故障注入和包级测试

**Files:**
- Modify: `scripts/inject_so101_parallel_fault.py`
- Modify: `src/so101_demo_py/test/test_parallel_batch_fault_injection.py`
- Modify: `docs/experiments/so101-parallel-w8-admission-experiment-ledger.md`

**Interfaces:**
- Produces fault points: `stage_start`, `canary_barrier_released`, `stage_sealed`, `provisional_written`, `production_queue_opened`, `resource_soft_stop`, `resource_hard_stop`, `authority_before_accept`, `worker_capacity_loss`.
- Consumes: v2 journal and supervisor ownership manifest.

- [ ] **Step 1: 写故障矩阵 RED tests**

逐项断言错误码、点位统计隔离、Domain/cgroup cleanup 和 crash semantics。四个 qualification
崩溃边界全部 non-resumable，同 batch 永久 invalid；逐一 SIGKILL Coordinator、monitor、测试
Authority 后由 watchdog 完成 pending terminal、owned leaf、Domain 和 slice 清理。hard stop
发生在正式 attempt 后且结果未知时必须是 `INDETERMINATE`。
增加完整撤销链集成测试：accepted profile 的 clean-host normal 触发硬故障，同时停止 Authority；
watchdog 先持久化 pending revocation 并清理。Authority 重启后必须先消费并 revoke，同一 profile
下一次 normal 返回 `PROFILE_REVOKED`。另测 foreign workload 存在时只拒绝当前 batch。

- [ ] **Step 2: 运行 RED 并实现最小注入点**

注入器只作用于本任务拥有的 batch/PID，不增加宽泛进程匹配。实现后重跑 fault tests。

- [ ] **Step 3: 构建并运行完整普通测试门**

```zsh
set -euo pipefail
cd /data/work/ws_moveit/.worktrees/parallel-w8-admission-v2
source /opt/ros/jazzy/setup.zsh
underlay=/data/work/ws_moveit/install
test -f "$underlay/setup.zsh"
source "$underlay/setup.zsh"
for pkg in mujoco_ros2_control so101_mujoco_support; do
  prefix=$(ros2 pkg prefix "$pkg")
  test -n "$prefix"
  realpath "$prefix"
done
colcon build --packages-up-to so101_demo_py --symlink-install
source install/setup.zsh
test_tmp="$evidence_root/scratch/task-11-package/tmp"
test ! -e "$test_tmp" || exit 90
install -d -m 700 "$test_tmp"
export TMPDIR="$test_tmp" TMP="$test_tmp" TEMP="$test_tmp"
test_python=/usr/bin/python3
resolved_tmp=$(TMPDIR="$test_tmp" TMP="$test_tmp" TEMP="$test_tmp" \
  "$test_python" -c 'import tempfile; print(tempfile.gettempdir())')
test "$resolved_tmp" = "$test_tmp" || exit 91
PYTHONNOUSERSITE=1 "$test_python" -m pytest -p no:cacheprovider \
  src/so101_demo_py/test -q \
  --junitxml="$evidence_root/scratch/task-11-package/so101_demo_py.xml"
```

禁止收集 `benchmark_test/`。记录实际收集数、退出码和 elapsed time。

- [ ] **Step 4: 更新账本并提交**

```zsh
git add scripts/inject_so101_parallel_fault.py \
  src/so101_demo_py/test/test_parallel_batch_fault_injection.py \
  docs/experiments/so101-parallel-w8-admission-experiment-ledger.md
git commit -m "test: cover W8 admission failure boundaries"
```

### Task 12: ai-station 静态准入与隔离 smoke

**Files:**
- Modify: `docs/experiments/so101-parallel-w8-admission-experiment-ledger.md`

**Interfaces:**
- Consumes: installed v2 CLI and registered evidence root.
- Produces: source/install/runtime provenance、八 Domain claims、cgroup layout 和 cleanup receipt。

- [ ] **Step 1: 重新 source 并验证安装产物**

在不继承交互 overlay 的 fresh non-interactive zsh 中，先 source `/opt/ros/jazzy/setup.zsh`，再
source 已验证的 `/data/work/ws_moveit/install/setup.zsh`，最后必须 source
`/data/work/ws_moveit/.worktrees/parallel-w8-admission-v2/install/setup.zsh`；
回读 `mujoco_ros2_control`、`so101_mujoco_support` 和其余 package.xml 依赖的 prefix/realpath/hash，
并把 underlay identity 纳入 runtime profile。禁止继承未记录的交互 shell overlay。随后记录
commit、dirty status，断言 `ros2 pkg prefix so101_demo_py` 和 console script 位于 feature
worktree install，Python module `realpath` 位于该 worktree source/install 映射，installed v2
config SHA256 等于 source config；再记录 console/module/config SHA256、Docker
image digest、模型哈希、RMW report 和 cgroup controller。通过受审的 Authority 与 cgroup 脚本安装/更新
`so101-admission-authority.service` 与 `so101-parallel-watchdog@.service`，回读 unit、专用用户、0660 socket、Authority-owned 路径、
私钥权限和客户端固定公钥；不能建立该边界时以 `AUTHORITY_UNAVAILABLE` 停止。

```zsh
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_moveit/install/setup.zsh
source "$worktree/install/setup.zsh"
resolved_prefix=$(realpath "$(ros2 pkg prefix so101_demo_py)")
expected_prefix=$(realpath "$worktree/install/so101_demo_py")
test "$resolved_prefix" = "$expected_prefix"
console_bin="$resolved_prefix/lib/so101_demo_py/so101_parallel_batch"
test -x "$console_bin"
module_file=$(/usr/bin/python3 -c 'import pathlib, so101_demo; print(pathlib.Path(so101_demo.__file__).resolve())')
case "$module_file" in
  "$worktree"/*) ;;
  *) exit 94 ;;
esac
installed_v2="$resolved_prefix/share/so101_demo_py/config/mujoco/parallel_batch_v2.yaml"
test "$(sha256sum "$installed_v2" | cut -d ' ' -f 1)" = \
  "$(sha256sum "$v2_config" | cut -d ' ' -f 1)"
```

- [ ] **Step 2: 运行 W8 dry admission**

先运行 systemd/Docker capability smoke，确认 system cgroup v2、systemd driver、空 slice/leaf
拓扑、controller、权限与清理均成立。再以 v2 qualification 模式使用已实现并测试的
`--stop-after CREATE_CGROUPS`，断言八 Domain 都已 claim、Fast DDS UDP-only、32 participant
上限、cgroup 20/4 CPU 和 24 GiB/0 swap 回读一致，未启动正式动作。另起真实 participants
执行跨 Domain leak 和端口冲突 smoke。

```zsh
ros2 run so101_demo_py so101_parallel_batch \
  --points "$point_catalog" --config "$v2_config" \
  --batch-id w8-v2-cgroup-smoke-01 --worker-count 8 \
  --max-points-per-worker 3 --admission-mode qualification \
  --stop-after CREATE_CGROUPS \
  --evidence-root "$evidence_root/b/s" \
  --broker-image "$broker_image" \
  --yolo-weights "$yolo_weights" --yolo-weights-sha256 "$yolo_sha256" \
  --grounded-root "$grounded_root" \
  --grounded-manifest-sha256 "$grounded_sha256" \
  --run-mode execute
```

随后用同一组冻结输入运行 `--stop-after METRICS_READY_1`，只启动第一个隔离 Worker，连续 31 秒
采集真实 `/so101/simulation/physics_step_chunks`、`/task_camera/color` 和 `/joint_states`。要求每类
至少 60 个 0.5 秒样本、identity/sequence 连续、RTF/FPS 可计算、controller-state miss 为 0，
然后受控清理；任何缺 topic、缺样或 fake-only producer 都以 `INVALID` 停止。

```zsh
ros2 run so101_demo_py so101_parallel_batch \
  --points "$point_catalog" --config "$v2_config" \
  --batch-id w8-v2-metrics-smoke-01 --worker-count 8 \
  --max-points-per-worker 3 --admission-mode qualification \
  --stop-after METRICS_READY_1 \
  --evidence-root "$evidence_root/b/m" \
  --broker-image "$broker_image" \
  --yolo-weights "$yolo_weights" --yolo-weights-sha256 "$yolo_sha256" \
  --grounded-root "$grounded_root" \
  --grounded-manifest-sha256 "$grounded_sha256" \
  --run-mode execute
```

- [ ] **Step 3: 受控清理并回读**

只停止 owned manifest 中 PID，验证 Domain、cgroup、socket 和 ROS graph 没有本轮残留。
将本轮记为 `VALID` 或 `INVALID`，不计产品成功率。

- [ ] **Step 4: 更新账本并提交**

```zsh
git add docs/experiments/so101-parallel-w8-admission-experiment-ledger.md
git commit -m "docs: record W8 static admission smoke"
```

### Task 13: 同批次完成 `1 → 2 → 4 → 6 → 8` qualification

**Files:**
- Modify: `docs/experiments/so101-parallel-w8-admission-experiment-ledger.md`

**Interfaces:**
- Produces: five sealed stage summaries and `PROVISIONAL_W8_ADMISSION`.
- Consumes: one durable evidence root and one batch ID `w8-v2-qualification-01`.

- [ ] **Step 1: 预登记唯一实验**

在账本写 `PLANNED`：同一 batch、五级累积启动、每级三轮同步 canary、失败/无效判据、完整
provenance 和 cleanup 责任。然后改为 `RUNNING`。

- [ ] **Step 2: 启动 qualification**

使用 spec §13 的命令，固定 `worker-count=8`、`max-points-per-worker=3`、
`admission-mode=qualification`。命令由专用 tmux session 持有；不复用 Codex pane 承载
机器人进程。

```zsh
ros2 run so101_demo_py so101_parallel_batch \
  --points "$point_catalog" --config "$v2_config" \
  --batch-id w8-v2-qualification-01 --worker-count 8 \
  --max-points-per-worker 3 --admission-mode qualification \
  --evidence-root "$evidence_root/b/q" \
  --broker-image "$broker_image" \
  --yolo-weights "$yolo_weights" --yolo-weights-sha256 "$yolo_sha256" \
  --grounded-root "$grounded_root" \
  --grounded-manifest-sha256 "$grounded_sha256" \
  --run-mode execute
```

- [ ] **Step 3: 每级做 bounded read-back**

每个 stage 结束后检查 N 路 executing 交集、三轮 canary、资源分位数、Broker、recovery、
Domain/cgroup 和 Authority 结果。失败时不手改账本状态让流程继续。

- [ ] **Step 4: 核验 provisional admission**

W8 三轮全部通过后，回读 Authority record 的 batch、epoch、config/provenance hash 和
resource headroom。只有 `PROVISIONAL_W8_ADMISSION` 有效才允许正式队列打开。

### Task 14: 完成 W8 正式 20 点与 profile 接受

**Files:**
- Modify: `src/so101_demo_py/config/mujoco/parallel_admission_profiles_v1.yaml`
- Create: `src/so101_demo_py/config/mujoco/admission_profiles/ai-station-w8-v1.json`
- Modify: `docs/experiments/so101-parallel-w8-admission-experiment-ledger.md`
- Test: `src/so101_demo_py/test/test_parallel_admission.py`

**Interfaces:**
- Produces: `resource_profile_accepted=true` and repo-tracked profile identity.
- Consumes: Task 13 同一 batch 的正式 20 点和 cleanup evidence。

- [ ] **Step 1: 等待正式队列终态**

要求 20 个唯一点全部有首次有效结果、八 Worker 可并发领取、所有 attempt 可映射到唯一
Worker/Domain/generation。保存 terminal RGB、数值物理结果和 Worker 时间线。

- [ ] **Step 2: 验证产品与资源资格**

分别检查：

```text
coverage_complete=true
batch_cleanup_complete=true
qualification_passed=true
resource_profile_accepted=true
```

任一为 false 都不能写“W8 已安全准入”。

- [ ] **Step 3: 冻结 profile 到仓库**

profile 保存 `runtime_content_sha256` 的固定 allowlist manifest；排除 docs、evidence、ledger、
profile/registry 文件和 Git commit，`implementation_commit` 仅审计。先测试提交 profile/registry
后 runtime identity 不变，再修改一个 allowlist 内运行文件并断言拒绝。从 Authority accepted output 复制规范化 JSON 到
`config/mujoco/admission_profiles/ai-station-w8-v1.json`，计算 SHA256 并写入
`parallel_admission_profiles_v1.yaml`。新增测试篡改 profile 内容，断言 registry 拒绝。

- [ ] **Step 4: 运行 profile GREEN test 并提交**

```zsh
git add src/so101_demo_py/config/mujoco/admission_profiles/ai-station-w8-v1.json \
  src/so101_demo_py/config/mujoco/parallel_admission_profiles_v1.yaml \
  src/so101_demo_py/test/test_parallel_admission.py \
  docs/experiments/so101-parallel-w8-admission-experiment-ledger.md
git commit -m "feat: accept ai-station W8 resource profile"
```

### Task 15: normal W8 复用与最终验收

**Files:**
- Modify: `docs/experiments/so101-parallel-w8-admission-experiment-ledger.md`

**Interfaces:**
- Consumes: repo-tracked `ai-station-w8-v1` and v2 CLI normal mode.
- Produces: profile reuse、八 Worker ready、正式小规模执行和完整 cleanup evidence。

- [ ] **Step 1: 预登记 normal W8 实验**

使用新的 batch ID 和 evidence root 子目录，生命周期仍属于同一个 task root。继续传入
qualification 冻结的同一个完整 catalog，并用四个既有基准点的重复 `--point-id` 做 selection，
不得生成新 catalog。`worker_count=8`、`max_points_per_worker=1`；容量 8 大于点数 4，允许四个 Worker领取，八个 Worker 必须全部 healthy 并持续 heartbeat 到 terminal。

- [ ] **Step 2: 运行 normal 模式**

提供 `--admission-profile-id ai-station-w8-v1`。启动器按 `1,2,4,6,8` 做空载稳定检查，不
重复 canary。八个 Worker ready 后开放四点队列。

```zsh
ros2 run so101_demo_py so101_parallel_batch \
  --points "$point_catalog" \
  --point-id task_start --point-id cup_test_forward_5cm \
  --point-id sample_05_near_center --point-id sample_14_far_right \
  --config "$v2_config" --batch-id w8-v2-normal-reuse-01 \
  --worker-count 8 --max-points-per-worker 1 \
  --admission-mode normal --admission-profile-id ai-station-w8-v1 \
  --evidence-root "$evidence_root/b/n" \
  --broker-image "$broker_image" \
  --yolo-weights "$yolo_weights" --yolo-weights-sha256 "$yolo_sha256" \
  --grounded-root "$grounded_root" \
  --grounded-manifest-sha256 "$grounded_sha256" \
  --run-mode execute
```

- [ ] **Step 3: 最终 read-back**

确认 profile/current provenance 匹配、四点通过、八 Worker 资源仍安全、cleanup 完成、八
Domain 释放、本任务 owned PID 为零。现场打开新 terminal contact sheet，检查杯子终态。

- [ ] **Step 4: 运行最终普通包级门**

用新的 `scratch/task-15-final/tmp` 运行 `src/so101_demo_py/test/`，不收集 benchmark。随后运行
`git diff --check` 和文档 literal/fence 检查。

- [ ] **Step 5: 更新最终 checkpoint 并提交**

账本写清 retained run、archived run 和删除候选；不实际删除。记录未通过层和下一条命令，
或在全部通过时写 `next_experiment: NONE`。

```zsh
git add docs/experiments/so101-parallel-w8-admission-experiment-ledger.md
git commit -m "docs: record final W8 admission qualification"
```

## 计划完成前自检

- [ ] v1 W1–W3 所有测试和 CLI 语义保持不变。
- [ ] v2 W8 请求、分配、启动、ready 数都精确为 8。
- [ ] 八 Worker 可以同时进入 `EXECUTING`，没有隐藏的并发令牌。
- [ ] qualification 是同一 batch 的 `1,2,4,6,8` 累积启动，每级三轮 canary。
- [ ] canary 不污染正式 20 点结果。
- [ ] 八 Domain 在 `START_1` 前原子 claim，崩溃后不会被旧 Worker 与新 batch 双重使用。
- [ ] v1/v2 共用 claim root；Fast DDS UDP-only、无 SHM/Data Sharing、participant 上限和跨 Domain 隔离均有现场证据。
- [ ] cgroup 覆盖 Coordinator、Broker、八 Worker 和全部后代进程。
- [ ] 24 GiB memory.max、0 swap、4 GiB MemAvailable 硬门和 2 GiB GPU 保留均有现场回读。
- [ ] Authority 是独立 system service；peer/nonce/Ed25519、Authority-owned registry、持久 revoke 和 profile 无时间过期规则均通过测试。
- [ ] Worker 丢失时暂停新 lease；不能按 W7/W6 继续。
- [ ] 首波、20 点尾部、四点 normal 和 K 用尽时八个健康 Worker 不提前退出；replacement 不重置 K。
- [ ] YOLO-first、Grounded-SAM fallback 和 `INVALID/INDETERMINATE` 语义未漂移。
- [ ] qualification W8 正式 20 点与 normal W8 profile 复用均有新证据。
- [ ] 最终报告分别列出 retained、archived 和删除候选，未经授权没有删除证据。
