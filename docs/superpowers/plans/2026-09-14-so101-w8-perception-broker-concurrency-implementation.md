# SO-101 W8 Perception Broker Concurrency Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 Broker accept-idle deadline 缺陷，让 W8 同时提交 8 个感知请求，并用默认 C2 YOLO 推理池降低 `/cup_pose` 尾延迟，同时保持 20 点 PickPlace 正确性和 W8→W6 降级能力。

**Architecture:** `AuthenticatedUnixServer` 只对 PerceptionBroker endpoint 开启最多 8 路有界连接；Broker 幂等表用 `PENDING/DONE/FAILED` 协调同 key 重试。`PerceptionService` 用独立 executor 消费现有公平队列，默认创建两个独立 YOLO detector 和一个 Grounded-SAM detector；5 秒是性能 SLO，inference RPC deadline 由 queue、inference 和回包预算推导。

**Tech Stack:** Python 3.12、Unix domain socket、threading/Condition、ROS 2 Jazzy、MuJoCo、MoveIt 2、Ultralytics YOLO、Grounded-SAM、pytest、colcon、Docker CUDA runtime。

**Spec:** `docs/superpowers/specs/2026-09-14-so101-w8-perception-broker-concurrency-design.md`

## Global Constraints

- 直接在 ai-station 的 `/data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool` 和分支 `codex/parallel-adaptive-worker-pool` 上继续；不要再次 SSH 到 ai-station。
- 基线是当前 HEAD `48ade9ab132a327ae7ec58001f87323c786093e9`。若 HEAD 已变化，先在 ledger 写出新 SHA、差异来源和是否仍包含该提交。
- 保留现有未提交文件：`docs/experiments/so101-parallel-adaptive-worker-pool-experiment-ledger.md`、`src/so101_demo_py/test/test_parallel_batch_resources.py` 和 `MUJOCO_LOG.TXT`。不得 reset、clean、stash、覆盖或夹带无关内容。
- 继续使用 evidence root `/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01`。
- ai-station 上每次 pytest/colcon 都创建此前不存在的 `scratch/<test-run-id>/tmp`，设置 `TMPDIR`、`TMP`、`TEMP`，并用同一个 `/usr/bin/python3` 回读 `tempfile.gettempdir()`；不删除 scratch。
- 不运行实体机械臂。本计划只允许 MuJoCo MoveIt 专家 execute。
- 不修改 YOLO-first、Grounded-SAM fallback 判定，不放宽 pose freshness、TF、reset、lease 或物理验收。
- `AuthenticatedUnixServer` 默认仍是单连接串行；只有 PerceptionBroker endpoint 显式开启并发。
- 自适应 W8 的 queue capacity 已等于当前 Worker 数，继续复用。v1 冻结配置的容量 3 不修改。
- 5 秒是性能 SLO，不是 inference hard timeout；`executing_hard_timeout_s=240.0` 保持不变。
- 每项实现先 RED、再做最小修改、再跑 GREEN 和相邻回归。每个代码任务单独提交。
- 不运行 `ament_uncrustify --reformat`。普通包级门只收集 `src/so101_demo_py/test/`。
- live 运行前先把实验写成 `PLANNED`，运行后落为 `VALID` 或 `INVALID`。
- 完成时报告 retained、archived 和删除候选；未经用户授权不删除证据。

每个引用 `$scratch_root` 的测试命令块都必须在同一次 shell 调用中先执行下面的固定前导：

```bash
test_label=w8-broker
test_run_id=$test_label-$(date -u +%Y%m%dT%H%M%SZ)-$$
scratch_root=/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/scratch/$test_run_id
test ! -e "$scratch_root"
mkdir -p "$scratch_root/tmp"
export TMPDIR="$scratch_root/tmp" TMP="$scratch_root/tmp" TEMP="$scratch_root/tmp"
/usr/bin/python3 -c 'import tempfile,sys; p=tempfile.gettempdir(); print(p); sys.exit(0 if p.startswith("/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/scratch/") else 1)'
```

## File responsibility map

- `src/so101_demo_py/src/runtime/parallel_ipc.py`：accept/receive/reply deadline、有界连接和幂等 replay。
- `src/so101_demo_py/src/parallel_batch/broker.py`：指定模型 dequeue、终态发布和并发安全。
- `src/so101_demo_py/src/runtime/parallel_perception_runtime.py`：独立 detector、executor、watchdog 和请求等待。
- `src/so101_demo_py/src/cli/parallel_perception_broker.py`：runtime spec、模型池启动和 READY receipt。
- `src/so101_demo_py/src/parallel_batch/adaptive_contracts.py`：`yolo_executor_count` 配置契约。
- `src/so101_demo_py/src/cli/mujoco_parallel_batch.py`：CLI override 和 Broker runtime spec。
- `src/so101_demo_py/config/mujoco/parallel_adaptive_workers_v1.yaml`：默认 C2。
- `src/so101_demo_py/src/ros/cup_pose_source.py`、`src/so101_demo_py/src/ros/dynamic_runtime.py`：clock-ready 接收边界。
- `src/so101_demo_py/test/test_parallel_*.py`、`test_cup_pose_source.py`、`test_dynamic_scene_sync.py`：自动化回归。
- `docs/experiments/so101-parallel-adaptive-worker-pool-experiment-ledger.md`：唯一实验账本。

---

### Task 1: Restore CP-009 and freeze CP-010

**Files:**
- Modify: `docs/experiments/so101-parallel-adaptive-worker-pool-experiment-ledger.md`
- Read: `docs/superpowers/specs/2026-09-14-so101-w8-perception-broker-concurrency-design.md`

**Interfaces:**
- Consumes: EXP-006、CP-008、CP-009、当前 worktree/process 状态。
- Produces: CP-010，下一命令固定为 Task 2 RED。

- [ ] **Step 1: Read back host and ownership**

```bash
hostname
pwd
git branch --show-current
git rev-parse HEAD
git status --short
git submodule status
pgrep -af 'move_group|rviz2|gz sim|pick_place|mujoco_parallel_batch|perception_broker' || true
tmux list-sessions 2>/dev/null || true
```

Expected: ai-station、指定 worktree/branch，没有本任务未知的活动 stack。

- [ ] **Step 2: Read the ledger, spec and plan completely**

```bash
cat docs/experiments/so101-parallel-adaptive-worker-pool-experiment-ledger.md
cat docs/superpowers/specs/2026-09-14-so101-w8-perception-broker-concurrency-design.md
cat docs/superpowers/plans/2026-09-14-so101-w8-perception-broker-concurrency-implementation.md
```

- [ ] **Step 3: Append CP-010**

记录实际 SHA/status/process，并写入：accept-idle 缺陷已由 EXP-006 A/B 确认；EXP-005 选择 C2；当前假设是“修复 deadline 后，用 8 路连接和两个独立 YOLO executor 降低尾延迟”。所有字段直接填写现场读回值。

- [ ] **Step 4: Check the ledger diff**

```bash
git diff --check
git status --short
```

不要提交既有 `test_parallel_batch_resources.py` 或 `MUJOCO_LOG.TXT`。

### Task 2: Fix the accept-idle deadline

**Files:**
- Modify: `src/so101_demo_py/src/runtime/parallel_ipc.py:391-499`
- Test: `src/so101_demo_py/test/test_parallel_ipc.py`

**Interfaces:**
- Consumes: `AuthenticatedUnixServer` 现有构造器。
- Produces: `AuthenticatedUnixServer(..., accept_poll_s: float = 0.25, error_reply_timeout_s: float = 1.0)`；`_serve_connection(connection) -> None`；request deadline 在 `accept()` 成功后开始。

- [ ] **Step 1: Add deterministic RED tests**

```python
def test_server_accept_idle_does_not_consume_request_deadline(tmp_path):
    server, client, message = authenticated_pair(
        tmp_path,
        deadline_s=0.20,
        handler=lambda _message: time.sleep(0.05) or {"ok": True},
    )
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    time.sleep(0.18)
    assert client.call(message)["payload"] == {"ok": True}
    server.close()
    thread.join(timeout=1.0)
    assert not thread.is_alive()


def test_server_handler_timeout_returns_structured_error(tmp_path):
    server, client, message = authenticated_pair(
        tmp_path,
        deadline_s=0.05,
        handler=lambda _message: time.sleep(0.20),
    )
    thread = threading.Thread(target=server.serve_once)
    thread.start()
    with pytest.raises(IpcError, match="HANDLER_DEADLINE_EXCEEDED"):
        client.call(message)
    thread.join(timeout=1.0)
    server.close()
```

使用现有 fixture 组装相同对象，不新造第二套协议。

- [ ] **Step 2: Run RED in a fresh NVMe scratch**

```bash
test_run_id=ipc-deadline-red-$(date -u +%Y%m%dT%H%M%SZ)-$$
scratch_root=/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/scratch/$test_run_id
test ! -e "$scratch_root"
mkdir -p "$scratch_root/tmp"
export TMPDIR="$scratch_root/tmp" TMP="$scratch_root/tmp" TEMP="$scratch_root/tmp"
/usr/bin/python3 -c 'import tempfile,sys; p=tempfile.gettempdir(); print(p); sys.exit(0 if p.startswith("/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/scratch/") else 1)'
PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider \
  src/so101_demo_py/test/test_parallel_ipc.py \
  -k 'accept_idle or handler_timeout_returns_structured_error' -vv \
  --junitxml="$scratch_root/pytest.xml"
```

Expected: 旧实现出现 `TRUNCATED_FRAME`、共享 deadline 耗尽或不完整回包。

- [ ] **Step 3: Implement the deadline split**

```python
def serve_once(self) -> None:
    self._socket.settimeout(self.accept_poll_s)
    try:
        connection, _ = self._socket.accept()
    except (TimeoutError, socket.timeout) as error:
        raise IpcError("ACCEPT_POLL") from error
    self._serve_connection(connection)


def _serve_connection(self, connection) -> None:
    deadline = time.monotonic() + self.deadline_s
    with connection:
        message = receive_frame(
            connection,
            deadline_s=deadline - time.monotonic(),
            max_frame_bytes=self.max_frame_bytes,
        )
        reply = self._invoke_with_deadline(message, deadline)
        connection.settimeout(self.error_reply_timeout_s)
        connection.sendall(encode_frame(reply, max_frame_bytes=self.max_frame_bytes))
```

`ACCEPT_POLL` 只用于 shutdown 轮询。请求可识别时，handler 超时必须返回原 request identity 的结构化错误，不能直接关闭 socket。

- [ ] **Step 4: Run GREEN and all IPC tests**

在新的 scratch 中运行：

```bash
PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider \
  src/so101_demo_py/test/test_parallel_ipc.py -vv \
  --junitxml="$scratch_root/pytest.xml"
```

Expected: 非零测试、零失败。

- [ ] **Step 5: Commit**

```bash
git add -- src/so101_demo_py/src/runtime/parallel_ipc.py src/so101_demo_py/test/test_parallel_ipc.py
git diff --cached --check
git commit -m "fix: reset IPC request deadline after accept"
```

### Task 3: Add Broker-only bounded connections and concurrent replay

**Files:**
- Modify: `src/so101_demo_py/src/runtime/parallel_ipc.py:391-830`
- Test: `src/so101_demo_py/test/test_parallel_ipc.py`

**Interfaces:**
- Produces: `AuthenticatedUnixServer(..., max_concurrent_connections: int = 1)`；`wait_handlers(timeout_s: float) -> bool`；Broker replay 状态 `PENDING/DONE/FAILED`。

- [ ] **Step 1: Add RED tests**

写三个测试：8 个不同 key 用 barrier 同时进入 handler；两个相同 key 只执行一次 mutation 并返回同一 detached result；没有显式并发参数的 server 最大 active handler 仍为 1。相同 key 不同 digest 继续返回 `IDEMPOTENCY_CONFLICT`。

- [ ] **Step 2: Run RED**

在新 scratch 中运行：

```bash
PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider \
  src/so101_demo_py/test/test_parallel_ipc.py \
  -k 'eight_distinct or pending_mutation or default_server_remains_serial' -vv \
  --junitxml="$scratch_root/pytest.xml"
```

- [ ] **Step 3: Implement bounded handlers**

`max_concurrent_connections > 1` 时才创建固定大小 `ThreadPoolExecutor`。accept loop 提交 `_serve_connection`；future 在完成回调中从受锁集合移除。`close()` 停止 accept 和新提交，`wait_handlers()` 用 Condition 在 deadline 前等待活动 future 归零。默认值 1 继续 inline 执行。

- [ ] **Step 4: Implement pending replay outside the global lock**

```python
@dataclass
class _BrokerReplayEntry:
    digest: str
    completed: threading.Event
    payload: bytes | None = None
    error: str | None = None
```

第一个 key 在锁内登记后释放锁执行 mutation；同 key/same digest 等待该 Event；不同 key 不等待 replay 锁。发布 `payload` 或规范化 `error` 后再 `completed.set()`。原连接断开不取消 mutation。

- [ ] **Step 5: Run all IPC tests and commit**

```bash
PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider \
  src/so101_demo_py/test/test_parallel_ipc.py -vv \
  --junitxml="$scratch_root/pytest.xml"
git add -- src/so101_demo_py/src/runtime/parallel_ipc.py src/so101_demo_py/test/test_parallel_ipc.py
git diff --cached --check
git commit -m "feat: add bounded Broker IPC concurrency"
```

### Task 4: Extend adaptive Broker runtime identity

**Files:**
- Modify: `src/so101_demo_py/src/parallel_batch/adaptive_contracts.py`
- Modify: `src/so101_demo_py/src/cli/mujoco_parallel_batch.py`
- Modify: `src/so101_demo_py/src/runtime/parallel_ipc.py`
- Modify: `src/so101_demo_py/src/cli/parallel_perception_broker.py`
- Modify: `src/so101_demo_py/config/mujoco/parallel_adaptive_workers_v1.yaml`
- Test: `src/so101_demo_py/test/test_parallel_adaptive_contracts.py`
- Test: `src/so101_demo_py/test/test_parallel_adaptive_pool.py`
- Test: `src/so101_demo_py/test/test_parallel_batch_cli.py`
- Test: `src/so101_demo_py/test/test_parallel_ipc.py`

**Interfaces:**
- Produces: `AdaptiveWorkerOptions.yolo_executor_count: int`；CLI `--yolo-executor-count`；runtime fields `connection_handler_count`、`yolo_executor_count`、`grounded_sam_executor_count`、`request_deadline_s`。

- [ ] **Step 1: Add RED contract tests**

断言默认 YAML 是 C2；CLI 只接受 1/2/4；W1 的 effective YOLO count 为 1；W8 默认为 2，可显式选 4；非 adaptive v1 不出现新 optional fields。deadline 必须满足：

```python
expected = max(
    config.yolo_queue_timeout_s + config.yolo_inference_timeout_s,
    config.grounded_sam_queue_timeout_s + config.grounded_sam_inference_timeout_s,
) + config.heartbeat_timeout_s
assert expected == 75.0
assert broker_spec["request_deadline_s"] == expected
```

- [ ] **Step 2: Run RED tests**

在新 scratch 中运行上述四个测试文件的 `-k 'executor or runtime_spec or adaptive'` 子集，保存 JUnit。

- [ ] **Step 3: Implement exact validation and derivation**

在 adaptive YAML 增加 `yolo_executor_count: 2`。dataclass 使用：

```python
if type(self.yolo_executor_count) is not int or self.yolo_executor_count not in {1, 2, 4}:
    raise AdaptiveContractError("YOLO_EXECUTOR_COUNT")
```

`--yolo-executor-count` 仅在 adaptive mode 有效。runtime spec 写入 handler=`worker_count`、YOLO=`min(requested, worker_count)`、Grounded=1、queue capacity=`worker_count` 和 deadline=75.0。schema 同时拒绝 bool、0、handler>8 和非法 YOLO count。

- [ ] **Step 4: Run complete contract/CLI files and commit**

```bash
PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider -q \
  src/so101_demo_py/test/test_parallel_adaptive_contracts.py \
  src/so101_demo_py/test/test_parallel_adaptive_pool.py \
  src/so101_demo_py/test/test_parallel_batch_cli.py \
  src/so101_demo_py/test/test_parallel_ipc.py \
  --junitxml="$scratch_root/pytest.xml"
git add -- \
  src/so101_demo_py/src/parallel_batch/adaptive_contracts.py \
  src/so101_demo_py/src/cli/mujoco_parallel_batch.py \
  src/so101_demo_py/src/runtime/parallel_ipc.py \
  src/so101_demo_py/src/cli/parallel_perception_broker.py \
  src/so101_demo_py/config/mujoco/parallel_adaptive_workers_v1.yaml \
  src/so101_demo_py/test/test_parallel_adaptive_contracts.py \
  src/so101_demo_py/test/test_parallel_adaptive_pool.py \
  src/so101_demo_py/test/test_parallel_batch_cli.py \
  src/so101_demo_py/test/test_parallel_ipc.py
git diff --cached --check
git commit -m "feat: configure adaptive Broker concurrency"
```

### Task 5: Build independent detector instances

**Files:**
- Modify: `src/so101_demo_py/src/runtime/parallel_perception_runtime.py:150-318`
- Modify: `src/so101_demo_py/src/cli/parallel_perception_broker.py:240-380`
- Test: `src/so101_demo_py/test/test_parallel_perception_runtime.py`
- Test: `src/so101_demo_py/test/test_parallel_perception_container.py`

**Interfaces:**
- Produces: `ParallelPerceptionRuntime(..., executor_counts: Mapping[str, int])`；`infer(request, snapshot, *, executor_index: int)`；`detectors: dict[str, tuple[BuiltDetector, ...]]`。

- [ ] **Step 1: Add RED tests**

```python
runtime = runtime_factory(yolo_executor_count=2, grounded_sam_executor_count=1)
runtime.start()
assert len(runtime.detectors[YOLO_ID]) == 2
assert runtime.detectors[YOLO_ID][0].detector is not runtime.detectors[YOLO_ID][1].detector
assert len(runtime.detectors[GROUNDED_ID]) == 1
receipt = read_receipt(runtime.ready_receipt)
assert receipt["models"][YOLO_ID]["executor_count"] == 2
assert len(receipt["models"][YOLO_ID]["instances"]) == 2
```

再测试任一实例 build/warm 失败时整个 generation 不得 READY。

- [ ] **Step 2: Run RED, implement, then run GREEN**

每个实例单独调用 factory，全部要求 CUDA；所有实例 ready 后才原子写 receipt。`infer(..., executor_index=N)` 选择对应实例并保留前后 `_frame()` 校验。smoke 对每个实例运行同一固定输入并记录 index。严格 READY receipt 增加 YOLO=2、Grounded=1 的 executor counts。

在新 scratch 中完整运行 `test_parallel_perception_runtime.py` 和 `test_parallel_perception_container.py`。

- [ ] **Step 3: Commit**

```bash
git add -- \
  src/so101_demo_py/src/runtime/parallel_perception_runtime.py \
  src/so101_demo_py/src/cli/parallel_perception_broker.py \
  src/so101_demo_py/test/test_parallel_perception_runtime.py \
  src/so101_demo_py/test/test_parallel_perception_container.py
git diff --cached --check
git commit -m "feat: isolate Broker detector executors"
```

### Task 6: Add model executor loops and terminal waiting

**Files:**
- Modify: `src/so101_demo_py/src/parallel_batch/broker.py:250-430`
- Modify: `src/so101_demo_py/src/runtime/parallel_perception_runtime.py:319-430`
- Test: `src/so101_demo_py/test/test_parallel_batch_broker.py`
- Test: `src/so101_demo_py/test/test_parallel_perception_runtime.py`

**Interfaces:**
- Produces: `PerceptionBroker.next_ready_request(model_id: str | None = None)`；`PerceptionService.wait_response(request, timeout_s)`；`PerceptionService.close(timeout_s) -> bool`。

- [ ] **Step 1: Add RED tests**

用 barrier fake detectors 证明两个 YOLO overlap、第三个等待、Grounded 最大并发为 1；指定 YOLO dequeue 不取 Grounded 请求。再让 detector 阻塞超过 `yolo_inference_timeout_s`，断言 watchdog 发布 `INFERENCE_TIMEOUT`、唤醒 waiter 并使 Broker unhealthy。

- [ ] **Step 2: Run RED**

在新 scratch 中运行两个测试文件的 `-k 'executor or model_specific or watchdog or wait_response'` 子集。

- [ ] **Step 3: Implement executor lifecycle**

`next_ready_request(None)` 保留旧 round-robin；传 model ID 时只扫描该模型队列。`PerceptionService.start()` 先启动 runtime，再按 executor count 建线程。每个线程循环：

```python
request = self.broker.next_ready_request(model_id)
if request is None:
    self._work_available.wait(0.02)
else:
    result = self.runtime.infer(
        request,
        self._snapshot_for(request),
        executor_index=executor_index,
    )
    self._publish_completion(request, result)
```

独立 watchdog 每 20 ms 通过 public `poll_response()` 检查 outstanding deadline。`submit()` 唤醒 executor；`wait_response()` 用 Condition 等 exact request 终态；`close()` fence、唤醒并有界 join。

- [ ] **Step 4: Run GREEN and commit**

```bash
PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider -q \
  src/so101_demo_py/test/test_parallel_batch_broker.py \
  src/so101_demo_py/test/test_parallel_perception_runtime.py \
  --junitxml="$scratch_root/pytest.xml"
git add -- \
  src/so101_demo_py/src/parallel_batch/broker.py \
  src/so101_demo_py/src/runtime/parallel_perception_runtime.py \
  src/so101_demo_py/test/test_parallel_batch_broker.py \
  src/so101_demo_py/test/test_parallel_perception_runtime.py
git diff --cached --check
git commit -m "feat: execute bounded concurrent perception jobs"
```

### Task 7: Wire Broker transport and concurrency evidence

**Files:**
- Modify: `src/so101_demo_py/src/runtime/parallel_ipc.py:657-830`
- Modify: `src/so101_demo_py/src/runtime/parallel_perception_runtime.py`
- Test: `src/so101_demo_py/test/test_parallel_ipc.py`
- Test: `src/so101_demo_py/test/test_parallel_perception_runtime.py`

**Interfaces:**
- Consumes: `connection_handler_count`、`wait_response()`、`wait_handlers()`。
- Produces: 8-client RPC path；monotonic events和 peak counters。

- [ ] **Step 1: Add 8-client RED test**

八个不同 Worker/request 同时调用，断言 pending RPC=8、queue depth>1、YOLO peak=2、logical inference=8、`TRUNCATED_FRAME=0`。同 key 并发重试的 logical inference 必须为 1。

- [ ] **Step 2: Replace inline inference**

```python
submission = service.submit(request, snapshot)
response = submission.response
if response is None and submission.accepted:
    response = service.wait_response(request, timeout_s=self.deadline_s)
if response is None:
    raise IpcError("BROKER_RESPONSE_PENDING")
return _broker_response(response)
```

Broker server 传 `max_concurrent_connections=connection_handler_count`。shutdown 顺序是 stop accept、fence/close service、wait handlers、unlink socket；任一 join 超时令进程非零退出。

- [ ] **Step 3: Add bounded timing output**

每个请求记录 accept、auth、idempotency、queued、started、completed、serialized、sent 的 monotonic 时间。最终摘要包含 pending RPC peak、queue peak、各模型 active peak、replay、logical inference 和结构化 transport error；不得写 token 或图像 payload。

- [ ] **Step 4: Run GREEN, crash recovery and commit**

```bash
PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider -q \
  src/so101_demo_py/test/test_parallel_ipc.py \
  src/so101_demo_py/test/test_parallel_perception_runtime.py \
  src/so101_demo_py/test/test_parallel_batch_crash_recovery.py \
  src/so101_demo_py/test/test_parallel_batch_fault_injection.py \
  --junitxml="$scratch_root/pytest.xml"
git add -- \
  src/so101_demo_py/src/runtime/parallel_ipc.py \
  src/so101_demo_py/src/runtime/parallel_perception_runtime.py \
  src/so101_demo_py/test/test_parallel_ipc.py \
  src/so101_demo_py/test/test_parallel_perception_runtime.py
git diff --cached --check
git commit -m "feat: connect W8 clients to the perception pool"
```

### Task 8: Arm `/cup_pose` after ROS clock readiness

**Files:**
- Modify: `src/so101_demo_py/src/ros/cup_pose_source.py`
- Modify: `src/so101_demo_py/src/ros/dynamic_runtime.py:390-445`
- Test: `src/so101_demo_py/test/test_cup_pose_source.py`
- Test: `src/so101_demo_py/test/test_dynamic_scene_sync.py`

**Interfaces:**
- Produces: `PoseReceiveBoundary(ready_ros_ns: int, ready_monotonic_s: float)`；`RosCupPoseSource.arm(timeout_s: float)`。

- [ ] **Step 1: Add RED tests**

测试 ROS clock 序列 `0,0,7_000_000_000` 时 `arm()` 等到正值；arm 清掉此前缓存；post-READY 消息的 source stamp 等于 `ready_ros_ns` 时允许，因为仿真可能暂停；更旧 stamp 或 pre-READY received monotonic 必须拒绝。

- [ ] **Step 2: Implement and move READY**

`arm()` spins 到 ROS time>0，清 `_messages`，记录 ROS/monotonic 边界。`_convert()` 继续原 age/future 检查，并要求 `received > ready_monotonic_s`、`stamp_ns >= ready_ros_ns`。dynamic runtime 在 `source.arm(min(5.0, options.cup_pose_timeout_s))` 之后才发 `RUNTIME_READY` 和 READY 行。保留 publisher 的 bounded retransmission。

- [ ] **Step 3: Run GREEN and commit**

```bash
PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider -q \
  src/so101_demo_py/test/test_cup_pose_source.py \
  src/so101_demo_py/test/test_dynamic_scene_sync.py \
  src/so101_demo_py/test/test_parallel_worker_runtime.py \
  src/so101_demo_py/test/test_task_batch_runtime.py \
  --junitxml="$scratch_root/pytest.xml"
git add -- \
  src/so101_demo_py/src/ros/cup_pose_source.py \
  src/so101_demo_py/src/ros/dynamic_runtime.py \
  src/so101_demo_py/test/test_cup_pose_source.py \
  src/so101_demo_py/test/test_dynamic_scene_sync.py
git diff --cached --check
git commit -m "fix: arm cup pose intake after ROS clock readiness"
```

### Task 9: Package gate, image build and 8-client production microbenchmark

**Files:**
- Evidence: `/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/`
- Modify: `docs/experiments/so101-parallel-adaptive-worker-pool-experiment-ledger.md`

**Interfaces:**
- Produces: package JUnit、new image digest、EXP-007 C2 concurrency evidence。

- [ ] **Step 1: Run ordinary package tests**

```bash
source /opt/ros/jazzy/setup.zsh
PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider -q \
  src/so101_demo_py/test \
  --junitxml="$scratch_root/so101-demo-py.xml"
```

Expected: 非零 ordinary tests，零 failures/errors；不收集 `benchmark_test/`。

- [ ] **Step 2: Build and verify overlay and Broker image**

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_demo_py --symlink-install --event-handlers console_direct+
source install/setup.zsh
ros2 pkg prefix so101_demo_py
python3 -c 'import so101_demo.runtime.parallel_ipc as m; print(m.__file__)'
```

然后用仓库现有 parallel-perception image wrapper 重建镜像，回读新 digest、`/opt/parallel-provenance.json` 和模型哈希。保存完整命令和退出码，不以旧镜像证明新代码。

- [ ] **Step 3: Plan and run EXP-007**

先在 ledger 写 `PLANNED`：`ISOLATED_STACK`、8 个真实 authenticated clients、C2、queue=8、同一 production-sized RGB input。脚本使用 `threading.Barrier(9)` 同步八个客户端。判据是 8 RPC pending、queue depth>1、YOLO peak=2、8 replies、每 key logical inference=1、`TRUNCATED_FRAME=0`、精确清理。

- [ ] **Step 4: Classify and checkpoint**

证据不完整、同步未形成或清理失败则 EXP-007=`INVALID`。成功则记录报告 JSON、日志 SHA256、image/source identity、scratch、retained/archived/deletion candidates。

### Task 10: Fixed-W8 C2 regression and conditional C4 A/B

**Files:**
- Modify: `docs/experiments/so101-parallel-adaptive-worker-pool-experiment-ledger.md`
- Evidence: `/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008-w8-c2/`
- Conditional evidence: `/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp009-w8-c4/`

**Interfaces:**
- Consumes: valid EXP-007、clean Domains 215-222、EXP-006 point catalog。
- Produces: fixed-W8 correctness/performance decision and selected C2/C4。

- [ ] **Step 1: Plan EXP-008 before starting**

冻结 fixed W8、无 fallback、YOLO-only、C2、同一 20 点和初始状态契约。成功条件：20/20 PASSED、零 `TRUNCATED_FRAME`、cleanup complete、READY→POSE_ACCEPTED P95<5 秒，并报告 max 和全部超 5 秒点。

- [ ] **Step 2: Preflight and execute once**

记录 source/overlay/image/model、Domains、containers、tmux、GPU apps 和 task-owned PIDs。运行现有 supervised adaptive batch wrapper，保留 stdout/stderr、manifest、journal、sealed results、timeline、host/GPU samples、exit code 和新鲜截图。

- [ ] **Step 3: Verify every correctness layer**

逐点检查 initial gate、YOLO `POSE_ACCEPTED`、MoveIt plan/execute、controller/joint/TF、MuJoCo cup/support/contact、final attachment empty 和 sealed hash。截图必须与数值终态一致。

- [ ] **Step 4: Compare EXP-008 with EXP-006**

报告 batch wall time、READY→POSE_ACCEPTED、Broker round trip、queue、model、response delivery 的 P50/P95/max，以及 RPC/queue/executor peaks、logical inference、replay、deadline errors 和超 5 秒点。

- [ ] **Step 5: Run C4 only when required**

若 EXP-008 为 20/20，但 P95 仍≥5 秒，新增 EXP-009，唯一变量为 `--yolo-executor-count 4`。C4 只有在降低 P95、保持 20/20、没有 Broker health loss 且清理完整时才保留；否则选 C2。

- [ ] **Step 6: Run one normal fallback-enabled adaptive regression**

使用选定并发，启用 YOLO-first Grounded-SAM fallback 和正常 W8→W6 ladder，不注入失败。要求 20 点终态和精确清理。若 YOLO 全部成功，记录 Grounded-SAM 调用数为 0，不强制制造 fallback。

### Task 11: Final gate and review handoff

**Files:**
- Modify: `docs/experiments/so101-parallel-adaptive-worker-pool-experiment-ledger.md`
- Modify design only if runtime evidence disproves a factual assumption.

**Interfaces:**
- Produces: scoped implementation commits、final package gate、completion/remaining-risk report。

- [ ] **Step 1: Inspect the branch and preserved changes**

```bash
git status --short
git diff --check
git log --oneline 48ade9ab132a327ae7ec58001f87323c786093e9..HEAD
git diff --stat 48ade9ab132a327ae7ec58001f87323c786093e9..HEAD
git diff --name-status 48ade9ab132a327ae7ec58001f87323c786093e9..HEAD
```

既有 `test_parallel_batch_resources.py` 和 `MUJOCO_LOG.TXT` 仍不得夹带。

- [ ] **Step 2: Re-run the ordinary package gate in a fresh scratch**

使用 Task 9 的完整 `src/so101_demo_py/test` 命令，确认非零 test count、零 failures/errors；回读 accepted W8 使用的 overlay 和 image digest。

- [ ] **Step 3: Commit the final ledger only**

```bash
git add -- docs/experiments/so101-parallel-adaptive-worker-pool-experiment-ledger.md
git diff --cached --check
git commit -m "docs: record W8 Broker concurrency qualification"
```

- [ ] **Step 4: Report exact outcome boundaries**

```text
IPC defect: FIXED only if accept-idle RED became GREEN and live TRUNCATED_FRAME is zero.
W8 correctness: PASSED only if all 20 points and physical evidence passed.
5-second SLO: PASSED only if READY-to-POSE_ACCEPTED P95 is below 5 seconds.
Selected YOLO concurrency: C2 or C4, with experiment IDs.
Adaptive fallback: PASSED only if normal W8/W6 behavior and exact cleanup remain healthy.
```

报告 source SHA、image digest、test counts、run IDs、证据路径、retained/archived/deletion candidates、保留的用户改动和未验证层。不得 push、merge 或删除证据，除非用户另行明确授权。
