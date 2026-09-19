# SO-101 macOS MPS 与私有 IPC 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. 本计划只允许 mac-mini 上新建的 DeepSeek Harness TUI `dst` tmux session inline 执行；用户的执行器规则覆盖技能中泛化的 subagent/Codex 建议。所有步骤使用 checkbox 作为唯一进度清单。

**Goal:** 在现有 `codex/so101-unbounded-queue-resource-budget` 分支和 mac-mini worktree 上实现 schema v4，使 exact `worker_count=2` 能以真实 PyTorch MPS、私有短路径 AF_UNIX IPC、共享 Broker 和单一 MPS execution lane 完成安全、可恢复的 W2 仿真验证。

**Architecture:** schema v3 的 Linux CUDA/NVML 与 `proc_fd_unix` 语义保持冻结；schema v4 通过 `AcceleratorProbe` 和 `UnixAddressStrategy` 选择闭合的平台组合。`CampaignSupervisor` 是 Broker 和两个 Worker 的真实 parent/spawner/reaper，Coordinator 保留动作安全、一次性请求准入和精确清理。v4 IPC 只依赖目录和 socket 权限，不传输或校验 token、generation、lease；Broker 故障时重建整个 W2 pool。

**Tech Stack:** Python 3.11、ROS 2 Jazzy、PyTorch MPS、MuJoCo、MoveIt 2、AF_UNIX、FastAPI/Pydantic、React/TypeScript、Bun、Vitest、Playwright、colcon、pytest。

**Spec:** [macOS MPS 与私有 IPC 设计](../specs/2026-09-19-so101-macos-mps-private-ipc-design.md)，SHA-256 `480da6dcdfea1da988f9f4e706c8340dbb6d7283200c27bb723859119145db1b`；[独立设计审查](../reviews/2026-09-19-so101-macos-mps-private-ipc-design-review.md)，SHA-256 `05a483e59dff596c37cbad737d85fa0a096242a7f6c9a1324a22c1c8329b71c8`。实施前完整阅读二者；设计 PASS 不是实现或运行 PASS。

## 全局约束

- 唯一执行 worktree 是 `/Users/matianyi/Projects/robot_demo_001/.worktrees/so101-unbounded-queue-resource-budget-mac-mini`，唯一分支是 `codex/so101-unbounded-queue-resource-budget`。不得新建 worktree、分支或第二执行器，不得切换到别的 checkout。
- 计划由 `gpt-5.6-sol/high` 编写，必须经独立 `gpt-6-astra/high` 审查为 PASS 后才能执行。实现只交给 mac-mini 上新建的 tmux `dst` session；目标预算精确为 100 轮，不得擅自重置、扩容或创建第二个 goal。
- 本轮用户授权 task-owned 代码修改、隔离测试、可逆仿真、fresh GUI/Chrome 验收和本地 scoped commit；不授权真实硬件、sudo、全局配置或驱动修改、foreign process stop、证据删除、force push、合并 main 或发布远端。
- 继续使用已登记证据根 `/tmp/so101-debug-unbounded-queue-w2-mac-mini-3eed4ddd-a50c-4c21-b78f-60be2216ef9d`，并在现有单写账本 `docs/experiments/so101-parallel-unbounded-queue-resource-budget-experiment-ledger.md` 追加 checkpoint。不得新建第二 evidence root；未经授权不删除 retained、archived 或 deletion candidate。
- 只实现并验收 macOS exact W2。不得运行或声称 W4/W6/W8，不得从 W2 外推跨 N 资格，不得恢复 N1–N8 certified budget/provider/promotion、swap/PSI、源码 commit 或 ament-prefix 运行时准入。
- 当前没有可用 Linux 环境。所有 Linux CUDA/NVML、`proc_fd_unix`、EGL、package/CTest 和 W2 回归一律标记 `DEFERRED_ENVIRONMENT`，本轮不执行，不写成 PASS、SKIP 或 N/A。在这些 gate 完成前不得声称 cross-platform、Linux regression 或发布资格。
- MPS 模型算子不允许 CPU fallback。Broker 进程在 import PyTorch 前必须证明 `PYTORCH_ENABLE_MPS_FALLBACK=0`；明确列出的 RGB 解码和 shape 整理可在 CPU 执行，但模型参数和预期推理张量必须在 MPS。
- v4 Client 不校验 endpoint receipt、inode、peer credential、token、generation 或 lease；v4 Server 不校验 token、generation 或 lease。访问私有 socket 即视为有 IPC 访问权限。Coordinator 本地状态机、active point、一次性 consume、controller 状态和结果完整性检查不得删除。
- macOS IPC 验证保持轻量：目录 `0700`、socket `0600`、路径长度、两 Client round-trip、协议负面路径、restart、精确 cleanup 和一次性 consume。不得重新加入 token/generation/lease replay 或 peer credential 矩阵。
- 每个功能修改都执行 RED→GREEN；环境导入失败、DYLD runner/bootstrap 失败、零收集或错误 interpreter 不算产品 RED。每次代码变化都使相关旧验收失效，必须重跑受影响 gate。
- 普通测试不得收集 `src/so101_demo_py/benchmark_test/`，也不运行无关 benchmark。macOS 不适用 ai-station `/data` scratch 规则；测试临时目录必须位于登记的 mac evidence root 下，并保存 argv、时间、exit、JUnit、module origin 和 provenance。
- GUI/Chrome/仿真前先只读核验无重复 task-owned stack 和 ownership；GUI 使用项目 `gui-capture` 的 fresh snapshot/action/snapshot。不得按端口、进程名、年龄或命令子串停止进程。
- 每个 task 结束执行 scoped `git diff --check`、回读 diff、追加 ledger checkpoint，并核对 retained/archived/deletion candidates。只 stage 当前 task 文件；不得宽泛 `git add -A`。

## 起点与执行环境

- 起点提交：`a3468eca697ae4b09a9a0cda84c421a94db54e86`，包含已批准设计及其独立审查；执行开始时必须重新读回 HEAD、branch、status 和 upstream，若已变化则记录新起点并确认变更仍属于本任务。
- mac-mini ROS Python：`/Users/matianyi/ros2_jazzy/.venv/bin/python3`。每个 gate 保存 `python`, `rclpy`, `torch`, `so101_demo`, `so101_teleop` 的实际 origin；source gate、copied install gate 和 served bytes gate 不能互相替代。
- 代理只用于 `dst`/依赖访问：`HTTP_PROXY`、`HTTPS_PROXY` 为 `http://127.0.0.1:10809`，`ALL_PROXY` 为 `socks5h://127.0.0.1:10808`，`NO_PROXY=127.0.0.1,localhost`。不得写入全局配置。
- macOS 测试环境必须设置唯一 `ROS_DOMAIN_ID`、`GZ_PARTITION`、task-local `ROS_HOME`、`ROS_LOG_DIR`、`TMPDIR`、`TMP`、`TEMP`。不得借用 canonical checkout 的 install 作为本分支证明。

## 执行器投递门

协调者在实施开始前完成以下一次性投递门，DST 只能回读，不能重复创建：

1. 核验 `dst` 实际 executable、launcher/profile version 与 help，确认旧 Codex session 已在无活跃 child 时关闭，mac-mini 上没有其他 task-owned DST/Codex executor；
2. 在现有 worktree 中创建唯一的新 tmux session，并显式携带 task-local proxy 与本计划/设计/审查 handoff SHA；
3. 使用 task-local DSH patch 把新 goal 的 `defaultMaxGoalRounds` 设为精确 `100`，不修改全局 profile；
4. 在 TUI 创建唯一 goal，读回实际 goal ID、`roundsStarted`、`maxGoalRounds=100` 与 active/continuation 状态；不得用提示词中的“100”代替 goal 状态；
5. 只有 handoff receipt、相同 goal 状态和第一个真实 repository/tool action 都出现后才算 dispatch ACK。tmux 存活、命令回显、shell exit 0 或模型复述任务均不算 ACK；
6. 将 session 名、pane、launcher PID、DSH session/goal ID、plan SHA、receipt 和首个工具动作写入协调 checkpoint。若 pane/process crash，只能在确认无重复 executor 后恢复同一 DSH session/goal；不得创建第二 goal。

## 代码边界与新增接口

| 边界 | 文件与职责 |
| --- | --- |
| v3/v4 契约 | `src/so101_demo_py/src/parallel_batch/contracts.py` 与 `config/mujoco/parallel_batch_v4_macos_mps_w2.yaml`；冻结 v3，新增闭合 v4 解析 |
| accelerator/start guard | `parallel_batch/accelerator_probe.py`、`start_guard.py`、`start_guard_probe.py`；Darwin MPS snapshot、固定 headroom 和两秒 deadline |
| supervisor/ownership | `parallel_batch/campaign_supervisor.py`、`resource_identity.py`、`runtime/parallel_processes.py`；真实 parent/spawner/reaper 和 durable SPAWNING/ACTIVE intent |
| IPC 地址/协议 | `runtime/unix_address.py`、`runtime/parallel_ipc.py`；Darwin 私有短路径、v4 permission-only envelope、bounded queue |
| 输入数据面 | `parallel_batch/input_snapshot.py`、`runtime/parallel_perception_runtime.py`；不可变 snapshot descriptor 与上限 |
| 请求准入 | `parallel_batch/inference_registry.py`、`coordinator.py`、`worker.py`；一次性 request register/consume/cancel/invalidate |
| MPS Broker | `runtime/mps_broker_bootstrap.py`、`runtime/parallel_perception_runtime.py`、`parallel_batch/broker.py`；spawn、共享模型、单 lane、ready receipt |
| W2 组合与恢复 | `cli/mujoco_parallel_batch.py`、`runtime/parallel_ros_runtime.py`、`parallel_batch/coordinator.py`；exact W2 与整池重建 |
| Teleop/OpenAPI/Web | `src/so101_teleop/so101_teleop/expert_validation/`、`openapi_export.py`、`web/src/`；只投影 v4 resolved manifest 与 W2 状态 |

新增类型必须保持以下最小接口；若现有命名可直接复用，应扩展原类型而不是创建同义重复层：

```python
@dataclass(frozen=True)
class AcceleratorSnapshot:
    kind: Literal["cuda", "mps"]
    selector: str
    available_bytes: int
    recommended_max_memory_bytes: int | None
    current_allocated_memory_bytes: int | None
    driver_allocated_memory_bytes: int | None
    metric_source: str

class AcceleratorProbe(Protocol):
    def probe(self, *, deadline_monotonic_ns: int) -> AcceleratorSnapshot: ...

class UnixAddressStrategy(Protocol):
    def create_campaign_root(self) -> "CampaignIpcRoot": ...
    def endpoint_path(self, root: "CampaignIpcRoot", role: str) -> Path: ...
    def cleanup_registered_endpoint(self, endpoint: "RegisteredEndpoint") -> "CleanupReceipt": ...

@dataclass(frozen=True)
class InputSnapshotDescriptor:
    relative_path: str
    size_bytes: int
    sha256: str
    shape: tuple[int, ...]
    dtype: str
    encoding: str
    frame_timestamp_ns: int

class InferenceRegistry:
    def register_request(self, binding: "InferenceBinding") -> str: ...
    def consume_result(self, request_id: str, result: "InferenceResult") -> "ConsumeDecision": ...
    def cancel_request(self, request_id: str, reason: str) -> None: ...
    def invalidate_broker(self, identity: "ProcessIdentity") -> tuple[str, ...]: ...
```

## 通用命令与证据模板

执行器先在证据根创建唯一 implementation run 目录，并把路径写入 ledger。每个测试 invocation 使用新的子目录；下列变量须回读后才能运行：

```zsh
export WORKTREE=/Users/matianyi/Projects/robot_demo_001/.worktrees/so101-unbounded-queue-resource-budget-mac-mini
export TASK_ROOT=/tmp/so101-debug-unbounded-queue-w2-mac-mini-3eed4ddd-a50c-4c21-b78f-60be2216ef9d
export TEST_PYTHON=/Users/matianyi/ros2_jazzy/.venv/bin/python3
export ROS_DOMAIN_ID=203
export GZ_PARTITION=so101_uq_mps_w2_3eed4ddd
export ROS_HOME="$TASK_ROOT/ros-home"
export ROS_LOG_DIR="$TASK_ROOT/ros-log"
export TMPDIR="$TASK_ROOT/tmp"
export TMP="$TMPDIR"
export TEMP="$TMPDIR"
mkdir -p "$ROS_HOME" "$ROS_LOG_DIR" "$TMPDIR"
cd "$WORKTREE"
```

每个 pytest gate 使用精确 `TEST_PYTHON -m pytest` 并写 JUnit；每个 build/test gate 保存 stdout/stderr 和结果。任何命令 exit 0 前必须检查非零收集数或真实 package 数，避免把空 gate 当 PASS。

---

### Task 0：接管现有 worktree、冻结起点并建立单写 checkpoint

**Files:** Modify `docs/experiments/so101-parallel-unbounded-queue-resource-budget-experiment-ledger.md`; create task-root implementation checkpoint/command records only.

- [ ] 完整阅读当前 `AGENTS.md`、`so101-dev` 及必需 references、设计、设计审查和本计划；记录文件 SHA。
- [ ] 读回 branch、HEAD、upstream、status、diff、submodule、现有 tmux/process、端口和 task-owned ownership。回读协调者保存的唯一 DST dispatch checkpoint：session/pane/PID、DSH session/goal ID、`roundsStarted`、`maxGoalRounds=100`、plan SHA、receipt 和首个真实工具动作必须一致；DST 不得自行停止未知进程或创建第二 goal。
- [ ] 确认没有其他 `dst` 或任务执行器，且本 worktree 未被另一个进程写入。发现重复执行器时停止，不猜测所有权。
- [ ] 建立唯一 implementation run 子目录，写入 `environment.json`、`git-status.txt`、`process-inventory.txt`、`module-origins.txt` 和 command runner；在 ledger 追加 `IMPLEMENTATION_START` checkpoint。
- [ ] 运行基线冻结测试，证明 schema v3 现状和设计文件未被改写：

```zsh
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_parallel_batch_contracts.py \
  src/so101_demo_py/test/test_parallel_start_guard.py \
  src/so101_demo_py/test/test_parallel_unix_transport.py \
  --junitxml="$RUN_ROOT/task0-baseline.xml"
```

- [ ] 若基线因 macOS DYLD/bootstrap 失败，记录 `INVALID_ENVIRONMENT` 并先修复 task-local runner；不得修改产品断言来隐藏环境问题。
- [ ] Ledger checkpoint 后执行 `git diff --check`；只提交 task 0 的 ledger/checkpoint 元数据：`chore(so101): checkpoint macOS MPS W2 implementation start`。

### Task 1：冻结 schema v3，增加闭合的 schema v4 MPS W2 契约

**Files:** Modify `src/so101_demo_py/src/parallel_batch/contracts.py`, `src/so101_demo_py/test/test_parallel_batch_contracts.py`, `src/so101_demo_py/setup.py`; create `src/so101_demo_py/config/mujoco/parallel_batch_v4_macos_mps_w2.yaml`.

- [ ] 先写 RED：v3 bytes/解析保持不变；v4 保留两个闭合平台组合——Linux `cuda + proc_fd_unix` 与 Darwin `mps + darwin_private_path_unix`。本轮只执行后者的 exact `worker_count=2 + allow_cpu_fallback=false`；拒绝 W1/W4/W6/W8、CPU、交叉平台组合、未知字段和非正 headroom。Linux 组合的现场回归按 Task 15 延期，但不能从契约中删除。
- [ ] 运行最小 RED，确认失败是 v4 未实现：

```zsh
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_parallel_batch_contracts.py \
  -k 'schema_v4 or schema_v3_frozen' \
  --junitxml="$RUN_ROOT/task1-red.xml"
```

- [ ] 实现 `AcceleratorKind`、`IpcTransport`、v4 accelerator/start-guard 配置及 closed-combination validator；v3 继续走原解析分支，禁止把 MPS 字段塞进 v3。
- [ ] 将 v4 YAML 安装进 package data；resolved manifest 必须记录 `accelerator=mps`、`ipc_transport=darwin_private_path_unix`、`mujoco_gl=cgl`、`worker_count=2` 和固定 headroom。
- [ ] GREEN 后运行整个 contracts test 文件，并提交：`feat(so101): add closed macOS MPS W2 schema v4`。

### Task 2：实现 Darwin MPS AcceleratorProbe 与 lightweight start guard

**Files:** Create `src/so101_demo_py/src/parallel_batch/accelerator_probe.py`; modify `parallel_batch/start_guard.py`, `parallel_batch/start_guard_probe.py`, `test/test_parallel_start_guard.py`, `test/test_parallel_start_guard_probe.py`, `test/test_parallel_start_guard_composition.py`.

- [ ] 写 RED 覆盖 `is_built/is_available`、`recommended_max_memory`、`vm_stat` 解析、`min(host_available,recommended)`、固定 1 GiB headroom、两秒共享 deadline、helper timeout/reap 和 metric provenance。
- [ ] 写 RED 证明 v3 CUDA/NVML probe 仍被选择，MPS snapshot 不填入 v3 `gpu_free_bytes`。
- [ ] 实现 `DarwinMpsAcceleratorProbe`；helper 只得到剩余 deadline，输出缺失、单位非法、超时或无法 reap 均 fail closed。
- [ ] 在真实 mac-mini 上做只读 probe smoke，保存 PyTorch/MPS 版本、`is_built`、`is_available`、recommended/current/driver allocated 和 `vm_stat` 原始输出；此 smoke 不加载模型。
- [ ] GREEN：

```zsh
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_parallel_start_guard.py \
  src/so101_demo_py/test/test_parallel_start_guard_probe.py \
  src/so101_demo_py/test/test_parallel_start_guard_composition.py \
  --junitxml="$RUN_ROOT/task2-green.xml"
```

- [ ] 提交：`feat(so101): add lightweight Darwin MPS start guard`。

### Task 3：让 CampaignSupervisor 成为真实 parent、spawner 与 reaper

**Files:** Create `src/so101_demo_py/src/parallel_batch/campaign_supervisor.py`, `src/so101_demo_py/test/test_campaign_supervisor.py`; modify `runtime/parallel_processes.py`, `parallel_batch/resource_identity.py`, `test/test_parallel_processes.py`, `test/test_parallel_resource_identity.py`.

- [ ] 写 RED 覆盖 flock conflict、durable receipt 原子写、spawn 前 `SPAWNING`、child registered ACK 后 `ACTIVE`、ACK timeout、未决 intent、Coordinator heartbeat loss、Supervisor crash 和精确 waitpid/reap。
- [ ] receipt 记录 role、预期 argv、nonce、PID、出生身份、process group、endpoint 和状态；未知或 identity 不匹配的进程只能报告，不能 signal。
- [ ] child bootstrap 必须在模型 import、controller 连接或任务循环前等待 registered ACK；超时退出，不允许先运行再补登记。
- [ ] Supervisor 清理完成前保持 `MPS:DEFAULT` claim；无法证明 controller goal absence、owned child reap 或 endpoint cleanup 时保留 receipt 并阻止下一 campaign。
- [ ] GREEN 后运行新增文件与原 process/resource tests，提交：`feat(so101): supervise owned W2 children durably`。

### Task 4：增加 DarwinPrivatePathUnixAddress 与精确 endpoint cleanup

**Files:** Create `src/so101_demo_py/src/runtime/unix_address.py`, `src/so101_demo_py/test/test_unix_address_strategy.py`; modify `runtime/parallel_ipc.py`, `test/test_parallel_unix_transport.py`, `test/test_parallel_ipc.py`.

- [ ] 写 RED 覆盖 canonical `/private/tmp/so101-ipc-<uid>/b-<random>/`、root-owned sticky base、owned `0700` dirs、非 symlink、socket `0600`、编码字节长度加 NUL、冲突 fail closed、新 restart 新路径。
- [ ] `ProcFdUnixAddress` 保持原 Linux v3 行为；`DarwinPrivatePathUnixAddress` 只在 v4 Darwin 闭合组合中选择。
- [ ] registry 记录 endpoint path、role、PID/出生身份和文件身份，只用于 cleanup/audit，不提供 Client 认证语义。
- [ ] cleanup 只 unlink registry 中 exact socket，并在 readback 为空时删除 exact campaign dir；禁止 glob、扫描其他 campaign 或删除未知对象。
- [ ] GREEN：运行 `test_unix_address_strategy.py`、`test_parallel_unix_transport.py`、`test_parallel_ipc.py`，提交：`feat(so101): add private Darwin Unix address strategy`。

### Task 5：实现 v4 permission-only RPC envelope 与轻量 IPC 验证

**Files:** Modify `src/so101_demo_py/src/runtime/parallel_ipc.py`, `src/so101_demo_py/test/test_parallel_ipc.py`, `test/test_parallel_broker_hot_path.py`, `test/test_parallel_unix_transport.py`.

- [ ] 写 RED 证明 v4 request 只有 `request_id/operation/deadline_monotonic_ns/payload`，response 只有 `request_id/status/output_descriptor|error/timing`；序列化结果不出现 token、generation、lease。
- [ ] 写 RED 证明 v4 Client 直接 connect，不执行 endpoint receipt、`stat()`、inode、peer UID/PID 或 replacement 检查；snapshot 文件访问不属于 endpoint auth hot path。
- [ ] Server 只校验固定 frame 上限、闭合 schema、operation allowlist、deadline 和 bounded queue；malformed、oversized、unknown、expired、queue full 返回稳定错误。
- [ ] 用两个并发 Client 做最小 round-trip；断开后精确 cleanup，restart 后旧路径不可用，新路径可用。
- [ ] 保留 v3 protocol tests，不用 v4 放宽去改写旧 Linux 协议。
- [ ] GREEN 后提交：`feat(so101): add permission-only v4 Unix RPC`。

### Task 6：实现不可变推理输入 snapshot

**Files:** Create `src/so101_demo_py/src/parallel_batch/input_snapshot.py`, `src/so101_demo_py/test/test_input_snapshot.py`; modify `runtime/parallel_perception_runtime.py`, `test/test_parallel_perception_runtime.py`, `parallel_batch/contracts.py`.

- [ ] 写 RED 覆盖 relative path、regular file、size、SHA-256、shape、dtype、encoding、timestamp、`max_input_snapshot_bytes`、绝对路径/`..`/symlink/篡改/超大拒绝。
- [ ] Worker 以 task-owned input root 内临时名写入、fsync、原子 rename 后登记；Broker 从已固定 root 打开并验证 descriptor，读取完成立即关闭。
- [ ] snapshot 至少保留到 request 完成、cancel 或 invalidation 并完成 readback；只登记 deletion candidate，不删除 evidence。
- [ ] frame 上限和 snapshot 上限分别执行，不能把大数组塞进控制帧。
- [ ] GREEN 后提交：`feat(so101): validate immutable inference snapshots`。

### Task 7：Coordinator 本地一次性 request registry

**Files:** Create `src/so101_demo_py/src/parallel_batch/inference_registry.py`, `src/so101_demo_py/test/test_inference_registry.py`; modify `parallel_batch/coordinator.py`, `parallel_batch/worker.py`, `test/test_parallel_batch_coordinator.py`, `test/test_parallel_batch_worker.py`.

- [ ] 写 RED 覆盖 opaque request ID campaign 内不复用，以及 `slot_id/point/attempt/model/input SHA/deadline/Broker PID+出生身份` 的原子绑定。
- [ ] `consume_result` 与 cancel/timeout 使用同一锁；成功 consume 立即移除。unknown、duplicate、cancelled、expired、snapshot mismatch、old Broker result 都拒绝并记录。
- [ ] v4 控制通道不接收 token/generation/lease；状态机继续校验 active point、操作顺序、controller 状态和结果完整性。
- [ ] Broker identity 失效时一次性 invalidate 所有绑定；迟到结果不得进入 RGB-D freshness、TF、geometry、pose admission 或动作门。
- [ ] GREEN 后提交：`feat(so101): gate inference results with one-time requests`。

### Task 8：实现真实 MPS Broker bootstrap、共享模型与单执行 lane

**Files:** Create `src/so101_demo_py/src/runtime/mps_broker_bootstrap.py`, `src/so101_demo_py/test/test_mps_broker_bootstrap.py`; modify `runtime/parallel_perception_runtime.py`, `parallel_batch/broker.py`, `test/test_parallel_batch_broker.py`, `test/test_parallel_perception_runtime.py`.

- [ ] RED：继承 `PYTORCH_ENABLE_MPS_FALLBACK=1` 或缺失预期值时，child 必须在 import torch 前 fail closed；保存 child env readback。
- [ ] Broker 使用 multiprocessing `spawn`。bootstrap 在 import 前固定并读回 fallback=0，设置 `mps_process_memory_fraction` 后再加载模型。
- [ ] 一个 Broker 只加载一组真实模型，两个 Worker 共用；所有模型经过一个 bounded MPS execution lane，不能每模型各建 executor 形成并行 Metal 调用。
- [ ] ready receipt 必须等模型真实 MPS warm-up 和 `torch.mps.synchronize()` 成功后发布，并包含 PID/出生身份、device、权重/配置 SHA、MPS memory metrics、fraction、PyTorch 版本、warm-up latency、output shape/dtype。
- [ ] 模型参数或预期张量不在 MPS、unsupported operator、warm-up/synchronize 失败均阻止 ready；不得改用 CPU。
- [ ] 先以 synthetic torch seam 完成 RED/GREEN，再运行真实 mac-mini MPS 最小模型 smoke。真实 smoke 保存设备、参数、输出和同步证据，不声称完整 W2。
- [ ] 提交：`feat(so101): bootstrap a single-lane shared MPS broker`。

### Task 9：Broker 故障时整池重建与安全取消

**Files:** Modify `src/so101_demo_py/src/cli/mujoco_parallel_batch.py`, `runtime/parallel_ros_runtime.py`, `runtime/parallel_worker_runtime.py`, `parallel_batch/coordinator.py`, `test/test_parallel_batch_crash_recovery.py`, `test/test_parallel_ros_runtime.py`, `test/test_parallel_worker_runtime.py`.

- [ ] 写 RED 覆盖 request timeout、OOM、Broker crash：先移除 active request，标记 infrastructure failure，再安全停止两个 Worker，取消运动中的 controller goal 并确认 absence。
- [ ] Supervisor 按精确 PID/出生身份/process group 终止并 reap owned 两 Worker 和 Broker；未知进程不 signal。
- [ ] restart 必须创建新随机 campaign IPC 路径，重新 warm-up Broker，再重新 spawn 两个 Worker；存活 Worker 不允许动态切 endpoint。
- [ ] 两 Worker 都 ready 后，Coordinator 才能按既有 `FULL_RESTART` 重新排队；旧 request/旧路径结果均拒绝。
- [ ] GREEN 后提交：`feat(so101): rebuild the full W2 pool after broker failure`。

### Task 10：组合 exact W2、resolved manifest 与 package 资源

**Files:** Modify `src/so101_demo_py/src/cli/mujoco_parallel_batch.py`, `parallel_batch/dynamic_manifest.py`, `parallel_batch/resources.py`, `runtime/parallel_processes.py`, `src/so101_demo_py/setup.py`, `test/test_parallel_batch_cli.py`, `test/test_parallel_batch_resources.py`, `test/test_parallel_processes.py`, `test/test_parallel_batch_artifacts.py`.

- [ ] RED：在 Darwin v4 中 only W2 可启动，固定两个 slot 即使点数少于二；manifest 记录 resolved MPS/IPC/CGL/W2、Broker identity、模型 provenance、snapshot root 和 supervisor receipt。
- [ ] 保持 v3 Linux composition bytes/semantics；Darwin v4 不调用 NVML 或 `/proc/self/fd`，Linux v4 保留 CUDA/NVML 与 `proc_fd_unix` 组合但本轮不现场执行；v3 不调用 MPS/vm_stat path。
- [ ] package data 安装 v4 config 和新模块；copied install 不能通过 Git/source import 偷渡。
- [ ] 运行 CLI/resources/process/artifact tests，提交：`feat(so101): compose exact W2 macOS MPS campaigns`。

### Task 11：同步 Teleop、OpenAPI 与 Web 的 v4 W2 投影

**Files:** Modify scoped files under `src/so101_teleop/so101_teleop/expert_validation/`, `src/so101_teleop/so101_teleop/openapi_export.py`, generated OpenAPI/types, `src/so101_teleop/web/src/components/expert-validation/`, and matching tests only where the runtime schema is exposed.

- [ ] 先查清现有 API 是否暴露 accelerator/guard/IPC/resolved manifest。若没有公开契约变化，只记录 no-op readback，不做无关 UI 重构。
- [ ] 若有变化，RED 覆盖 W2-only option、MPS guard summary、permission-only IPC 的非敏感 resolved 字段、失败原因和整池恢复进度；UI 不显示不存在的 token/generation/lease。
- [ ] Backend 仍是 authoritative；互斥、租约、安全取消和 evidence requirement 保持，但它们不再作为 v4 IPC Server 调用方认证字段。
- [ ] 只使用 `openapi_export.py` 重新生成 OpenAPI/types，不手改生成文件；运行 teleop pytest、Bun typecheck/unit/build 和 exact installed E2E fixture。
- [ ] 提交：`feat(teleop): expose macOS MPS W2 runtime state`；若 no-op，则不创建空提交。

### Task 12：fresh source、package、CTest、OpenAPI、copied-install 与 served-byte gate

**Files:** No intended product edits; append ledger and evidence records. Any discovered defect returns to the owning task and invalidates affected evidence.

- [ ] 先运行普通 demo pytest 的精确并行/串行 nodeid 集合，确认 union 等于非 benchmark 全集、交集为空、collection 非零；不得用单一 `pytest -n` 掩盖串行分组。
- [ ] fresh build 到 task-root build/install/log，source 该 install 后核对实际 executable/module/package prefix；运行真实 `colcon test`/CTest/test-result。若 macOS runner 出现已知 DYLD bootstrap 失败，记录 INVALID 并修复 runner 环境后重试，不能以 direct pytest 替代 package gate。
- [ ] 运行 OpenAPI export consistency、Bun install（现有 lock）、typecheck、unit、build；验证 copied install 无 `.git`、无 source-tree import，并比对 served JS/CSS/OpenAPI bytes 与 build artifact hash。
- [ ] 保存所有 argv、时间、exit、counts、JUnit/CTest、origin 和 hashes。任一 product assertion 失败则返回对应 task 做 RED→GREEN，随后重跑本 task 全部受影响 gate。

### Task 13：真实 macOS MPS 与轻量 IPC W2 smoke

**Files:** No intended source edits; evidence and ledger only unless a genuine defect returns to Tasks 2–10.

- [ ] 只读核验无重复 stack/claim/endpoint，创建新 campaign dir，执行真实 start guard 和 Supervisor claim。
- [ ] 启动一个真实 MPS Broker，加载并 warm-up 当前配置的全部真实模型；确认 `PYTORCH_ENABLE_MPS_FALLBACK=0`、参数/张量 device、single lane、memory metrics 和 ready receipt。
- [ ] 启动 exact 两个 Worker；证明两者共享同一 Broker/模型集合、slot 0/1 都产生独立 progress/result/evidence，且不是两个 Broker。
- [ ] 执行两 Client round-trip、malformed、oversized、unknown op、expired deadline、queue full、snapshot traversal/symlink/tamper/oversize 和正常 hot-path no-auth-check 证据。
- [ ] 分别完成三项 task-owned 故障证据：inference timeout、活动 Worker cancel、Broker crash。timeout 与 Broker crash 必须证明一次性 consume 拒绝迟到/重复结果、两个 Worker 安全停止、controller goal absent、owned 进程 reap，并以新路径重建整个 W2 pool。普通 Worker cancel 只按既有安全取消契约证明 fence、controller goal absence、该请求结果失权和精确 cleanup，不额外引入整池重建要求。任一缺失都不能通过本 gate。
- [ ] 完成精确 endpoint/process cleanup readback；不删除 snapshot/evidence。只有全部真实证据闭合才标记 `MACOS_MPS_W2_RUNTIME_SMOKE_PASS`。

### Task 14：五次连续 FULL_RESTART W2 仿真与 fresh GUI 证据

**Files:** No intended source edits; evidence and ledger only unless a genuine defect returns to the owning task.

- [ ] 冻结同一 commit、exact W2、点集、参数、成功契约和 lifecycle；每个 batch 使用独立新 epoch 和新 campaign IPC 路径。
- [ ] 每次启动前核验无重复 stack/claim/controller goal。使用 fresh GUI snapshot/action/snapshot，保存窗口 identity 和时间；不得复用旧截图。
- [ ] 每批都证明 MoveIt shadow、controller/joints、MuJoCo pose/contact/detach/release、final placement、两个 slot 的 progress/result/evidence、shared Broker 和 cleanup。
- [ ] 连续性按实际 batch 结果计算：任何 VALID 失败、INVALID、提前终止、旧 epoch、缺 slot、缺物理证据或 cleanup 不完整都会立即中断序列，下一次有效 batch 从 1/5 重新累计。环境修复即使没有代码变更也不能跨过失败/无效批次继续累计；任何代码变更还会使相关旧验收失效。
- [ ] 五个独立完整成功批次后才记录 `five_batch_stability=5/5`。一个 20 点 batch 不能替代五次。

### Task 15：Linux 回归 checkpoint（本轮只登记，不执行）

**Files:** Modify ledger only.

- [ ] 写入以下精确状态，不运行任何 Linux 命令：

```text
status: DEFERRED_ENVIRONMENT
reason: no Linux environment available
resume_when: Linux CUDA/NVML environment is ready
required_gates: schema-v3 CUDA/NVML; schema-v4 CUDA+proc_fd_unix; EGL; real Broker device; package/CTest; exact W2
```

- [ ] 明确 macOS 结果不替代 Linux，`LINUX_REGRESSION_DEFERRED` 阻止 cross-platform、Linux regression 和 main/release 声明。

### Task 16：最终审查、checkpoint 与本地提交

**Files:** Modify ledger; optionally update persistent guide only if user-facing operation changed, using `humanizer-zh`. Do not publish.

- [ ] 汇总每个 task 的 RED/GREEN、fresh package/web、真实 MPS/IPC、W2 slots、恢复、5/5、GUI/物理和 cleanup 原始证据；逐项对照设计 §9.1。
- [ ] 运行 final scoped `git diff --check`、普通 pytest collection equality、source/install/module origins、OpenAPI/build/served-byte hash、ownership/process/endpoint/controller absence readback。
- [ ] 由 `gpt-5.6-sol/high` 基于最新完整证据判定：只有全部 macOS 项满足才写 `MACOS_MPS_W2_PASS`；否则写 `PARTIAL`/`FAIL` 和精确缺口。无论结果如何保留 `LINUX_REGRESSION_DEFERRED`。
- [ ] 记录 retained、archived、deletion candidates；不删除任何证据。
- [ ] 本地提交本任务的 scoped 代码、测试、设计/计划/审查和 ledger。不得 merge main、push origin/github 或启动后续 UI 重构。

## 完成定义

本轮完成必须同时满足：schema v3 冻结；v4 exact W2 契约；真实 MPS start guard、模型 warm-up 和单 lane Broker；私有权限型 IPC；不可变 snapshot；一次性结果 consume；Supervisor durable ownership；Broker 故障整池重建；fresh package/OpenAPI/copied-install/served-byte gates；真实 W2 两个 slot；五次连续 FULL_RESTART 仿真；新 epoch 的 MoveIt/controller/MuJoCo/GUI/placement 证据；精确 cleanup；以及 ledger 中明确的 Linux `DEFERRED_ENVIRONMENT`。

tmux 存活、DST `DONE`、socket bind、单元测试截图、一个 ready receipt、一个 20 点 batch 或旧 epoch 都不能代替上述完成条件。
