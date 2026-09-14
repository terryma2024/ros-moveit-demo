# SO-101 W8 感知 Broker 并发优化设计

日期：2026-09-14

状态：聊天方案已确认，等待书面规格复核。

关联文档：

- `docs/superpowers/specs/2026-09-14-so101-adaptive-worker-pool-design.md`
- `docs/superpowers/plans/2026-09-14-so101-adaptive-worker-pool-implementation.md`
- `docs/experiments/so101-parallel-adaptive-worker-pool-experiment-ledger.md`

本文针对固定 W8 回归中暴露的感知延迟和 IPC 可靠性问题。它是自适应 Worker 池设计的补充，
不改变点位 lease、初始状态门控、MoveIt 执行、物理验收和 W8 失败后降到 W6 的既有语义。

## 1. 已知事实

本设计基于 ai-station 分支 `codex/parallel-adaptive-worker-pool` 的 EXP-006 和 CP-008/CP-009。
诊断运行使用固定 W8、禁用 fallback，20 个点全部通过，清理完整，总耗时约 362.454 秒。

与本次优化直接相关的观测如下：

- consumer READY 到 `POSE_ACCEPTED` 的中位数为 2.283755 秒，P95 为 6.869651 秒，最大值为
  7.921919 秒；20 个点中有 4 个超过单独定义的 5 秒目标。
- Broker client round trip 的中位数为 1.432061 秒，P95 为 3.663370 秒。它是感知链中最大的
  已测量片段。
- W8 期间最多只观察到 2 个 pending client RPC、1 个 Broker 内部排队请求和 1 路模型执行。
- GPU 利用率中位数为 3%，P95 为 21%，峰值为 24%；最低空闲显存约 10.876 GiB。GPU 容量没有
  被当前串行路径用满。
- 两次 `TRUNCATED_FRAME` 已通过单变量 A/B 复现。`AuthenticatedUnixServer.serve_once()` 在
  `accept()` 之前启动 5 秒 deadline，连接前的空闲时间侵蚀了接收、handler 和回包预算；预算
  耗尽后服务端无响应地关闭连接。客户端的同 idempotency key 重试取回了原结果，没有发生第二次
  逻辑推理。
- 一个点在 ROS clock 为 0 时拒绝了旧时间戳重发，随后时钟和新消息恢复，点位最终通过。

因此，确定性的 IPC deadline 缺陷已经确认。Broker 串行化是 W8 延迟的主要优化对象；GPU 资源
不足和 YOLO 单次执行过慢不符合现有证据。

## 2. 目标与非目标

### 2.1 目标

- 消除连接前空闲导致的 `TRUNCATED_FRAME`。
- 允许最多 8 个 Worker 同时持有 Broker RPC，不再由单一连接循环串行处理。
- 默认运行 2 路 YOLO 推理；只有 A/B 数据显示有收益时才升到 4 路。
- 保留 YOLO 优先、Grounded-SAM 按既有感知失败边界 fallback 的策略。
- 保证同一个 idempotency key 最多触发一次逻辑推理，重试只等待或回放原结果。
- 避免 ROS clock 为 0 或前一 attempt 的消息进入当前 `/cup_pose` admission。
- 保持 W8 失败后降到 W6 的轻量策略，不增加生产级资源准入机制。

### 2.2 非目标

- 不让 8 个 YOLO 实例同时运行。
- 不引入多个 Broker 进程、分布式队列、GPU 调度服务或 cgroup 硬保障。
- 不用放宽 pose 新鲜度、时间戳或 attempt identity 检查换取通过率。
- 不把 5 秒性能目标改成基础设施 hard timeout。
- 不改变 Grounded-SAM 的触发条件，也不让两个模型对同一输入竞速。
- 不承诺一次优化就让完整 W8 batch 获得线性 8 倍加速；MuJoCo、MoveIt 和 CPU 调度仍会限制总耗时。

## 3. 选定架构

```text
W1 ... W8
   │  最多 8 个并发 Unix RPC
   ▼
Broker accept loop
   │  只接受连接和登记所有权
   ▼
有界 connection handlers（上限等于本代 Worker 数，最大 8）
   │  authenticate + idempotent submit
   ▼
共享 PerceptionService
   ├── YOLO queue ─────► YOLO executor 1 ─► 独立 YOLO runtime 1
   │                 └► YOLO executor 2 ─► 独立 YOLO runtime 2
   └── Grounded queue ─► Grounded-SAM executor 1
   │
   ▼
幂等结果表（PENDING / DONE / FAILED）
   │
   ▼
原连接回包，或由同 key 重试回放
```

连接并发与模型并发是两个独立参数。W8 默认允许 8 个连接 handler，但 YOLO 只运行 2 个独立
executor。其余请求留在已有的公平队列中。这样可以释放 W8 的请求并发，又不会突然把模型副本、
CPU 预处理线程和显存占用放大到 8 倍。

`AuthenticatedUnixServer` 保持默认串行行为。只有 PerceptionBroker endpoint 显式启用有界并发，
避免 Coordinator 和其他控制 socket 在未评审的情况下改变时序。

## 4. IPC deadline 语义

### 4.1 接受连接

`accept()` 只使用短周期 poll 来检查 shutdown。这个 poll timeout 不属于任何请求，也不能生成
面向 Worker 的 `DEADLINE_EXCEEDED`。连接到达后，服务端才创建该连接的 request deadline。

### 4.2 请求和回包

请求处理使用下面的边界：

1. 接收完整 frame 后验证 schema、身份和 token。
2. inference RPC 等待 Broker 自己的 queue/inference deadline；health 和 cancel 仍由各自客户端的
   短 deadline 限制。
3. handler 超时或失败时构造结构化错误响应。
4. 错误响应和正常响应都有独立、短小的发送窗口。不得因为 handler 预算刚好耗尽而直接关闭连接。

Broker 的 `request_deadline_s` 不再复用 `heartbeat_timeout_s`。5 秒 heartbeat 只判断控制面存活；
inference RPC 的服务端预算必须覆盖配置中的 queue deadline、对应模型 inference deadline 和固定
回包余量。Worker 侧现有 240 秒执行 hard timeout 继续作为整个动作阶段的上限。

用户关注的 5 秒保留为 `get_one`/READY 到 `POSE_ACCEPTED` 的性能 SLO。超过 SLO 会进入报告，
但不会在模型仍处于合法 queue/inference 预算内时切断连接。

### 4.3 明确错误

协议至少要区分：

- `REQUEST_RECEIVE_DEADLINE_EXCEEDED`
- `HANDLER_DEADLINE_EXCEEDED`
- `RESPONSE_SEND_FAILED`
- 现有 Broker queue、inference 和 infrastructure outcome

已经建立连接且能读取请求身份时，服务端应返回带原 `request_id` 和 `idempotency_key` 的错误。
只有对端已经断开、frame 无法识别或 socket 本身失效时，客户端才可能看到传输级 EOF。

## 5. 幂等与并发

当前 `_CoordinatorBackedBrokerAuthority.dispatch()` 在持锁期间执行完整 mutation。即使 accept loop
并发，这把锁也会继续把推理串行化。实现需要把幂等表改成小型状态机：

- 第一个新 key 在锁内登记 `PENDING`，随后释放锁并执行 mutation。
- 相同 key、相同 digest 的并发请求挂接到同一个完成事件，不再次调用 mutation。
- 相同 key、不同 digest 立即返回 `IDEMPOTENCY_CONFLICT`。
- mutation 完成后在锁内发布 `DONE` 或规范化的 `FAILED`，唤醒等待者。
- 原连接超时或断开不取消已经获得执行权的 mutation；后续同 key 请求继续等待或回放终态。

不同 key 之间不得因为幂等表的全局锁而互相等待。所有状态发布仍须满足“先写终态，再唤醒”这一
线性化顺序。

## 6. 推理执行池

`PerceptionService` 负责 executor 生命周期，不再让连接 handler 直接调用一次 `run_next()`：

- Broker READY 前构造所有模型实例并完成既有 warm-up/self-test。
- 默认创建 2 个 YOLO executor，每个 executor 独占一个 detector/runtime 实例。
- Grounded-SAM 默认保持 1 个 executor。它只处理符合既有 fallback 条件的请求。
- executor 从现有公平队列领取请求，在模型调用前后继续执行 generation、authorization、健康状态、
  queue deadline 和 inference deadline 检查。
- 任一模型实例发生 CUDA/OOM 或 runtime infrastructure error 时，保持现有 fail-closed 语义：当前
  Broker generation 失去健康状态，由自适应 Runner 执行恢复或降级。不得偷偷减少 executor 后继续。
- shutdown 时先停止接收新 inference，fence generation，唤醒等待 handler，再有界等待 executor
  退出；清理回读必须确认线程和 Broker 容器均已结束。

W8 的 YOLO 队列容量设为 8，覆盖每个 Worker 的一个在途 YOLO 请求。`broker_inflight_per_worker_per_model`
继续为 1。容量不足属于配置错误或基础设施失败，不能触发 Grounded-SAM fallback。

第二阶段允许把 YOLO executor 数从 2 改为 4 做单变量 A/B。C4 只有同时降低端到端 P95、没有降低
20 点成功率、没有引发 Broker 健康丢失时才保留。C8 不在本次范围内。

## 7. `/cup_pose` 新鲜度

每个 attempt 按以下顺序建立感知接收边界：

1. reset 和 `point_initial_gate` 通过。
2. 等待该 Worker 的 ROS clock 大于 0。
3. 建立 `/cup_pose` subscription 并取得 subscription-ready receipt。
4. 冻结当前 attempt 的 ROS 起始时间、lease identity、reset epoch 和 frame watermark。
5. 只接受严格晚于这些边界且 identity 一致的 pose。

旧消息、未来时间戳、前一 attempt 的 retransmission 和时钟回退继续拒绝。实现不增加 future-skew
容差；如果 ROS clock 在已进入 READY 后归零或回退，本 attempt 记为基础设施中断并走现有恢复。

## 8. 配置与兼容性

配置新增或明确以下字段，名字在实施计划中根据现有 dataclass 命名约束最终核定：

| 配置 | 默认值 | 约束 |
| --- | ---: | --- |
| Broker connection handlers | 当前 pool Worker 数 | `1..8`，只影响 Broker endpoint |
| YOLO executor count | 2 | 本次只允许 `1`、`2`、`4` |
| Grounded-SAM executor count | 1 | 本次固定为 1 |
| Broker queue capacity per model | 8 | 不小于当前 pool Worker 数 |
| Broker inference RPC deadline | 由 queue、inference 和回包余量推导 | 不得复用 heartbeat timeout |

W1/W2/W4/W6/W8 共用同一套代码。connection handler 上限随实际 pool 档位收缩，YOLO executor
默认仍为 2；W1 时有效 executor 自动限制为 1。未启用 adaptive mode 的 v1 路径保持原默认值，
除通用的 accept-deadline 缺陷修复外不改变并发行为。

batch manifest 和最终报告必须记录实际 connection handler 数、模型 executor 数、队列容量和
deadline 派生值，避免把不同配置的性能样本混算。

## 9. 指标

每个 inference request 保留以下单调时钟点：

- client call start/end
- server accepted
- authentication start/end
- idempotency registration/replay
- Broker queued/started/completed
- response serialization/send complete
- consumer received/`POSE_ACCEPTED`

批次报告至少给出 READY 到 `POSE_ACCEPTED`、Broker round trip、queue wait、model execution 和
response delivery 的 P50/P95/max，并记录：

- 最大并发 client RPC 数；
- 最大 Broker queue depth；
- 每个模型的实际 executor 并发峰值；
- idempotent attach/replay 次数和逻辑 inference 次数；
- `TRUNCATED_FRAME`、结构化 deadline error 和 stale pose 拒绝计数；
- CPU、GPU、显存和 batch 总耗时。

这些指标只用于性能分析。点位是否通过仍由现有 perception admission、MoveIt、controller、MuJoCo
物理结果和 sealed evidence 决定。

## 10. 测试与实施顺序

实现按四轮单变量推进，每轮先 RED 后 GREEN：

### 10.1 IPC 修复

- 服务端空闲超过 request deadline 后再连接，快速 handler 必须正常回包。
- 连接后真正超时得到结构化错误，不得得到 `TRUNCATED_FRAME`。
- 对端断开不会终止 shared server loop。
- 同 key 重试只有一次 mutation。

这一轮保持 Broker 串行，单独证明 deadline 根因已修复。

### 10.2 并发连接和幂等状态机

- 8 个不同 key 能同时进入 handler；最大并发受配置上限约束。
- 同 key 并发请求共享一个 PENDING 结果。
- shutdown、异常和 generation fence 能唤醒所有等待者。
- 默认串行 endpoint 的调用顺序不变。

### 10.3 C2 推理池

- 8 个请求能全部进入服务，queue depth 大于 1，实际 YOLO 并发峰值精确为 2。
- 每个 executor 使用独立 detector 实例。
- 公平队列、per-worker inflight、deadline、fallback 和健康丢失测试继续通过。
- C1 与 C2 对同一固定输入的归一化输出一致。

### 10.4 ROS clock 与 W8 回归

- ROS clock 为 0 时不得发布 consumer READY。
- 前一 attempt 消息、未来时间戳和时钟回退被明确拒绝。
- 在 ai-station 上运行一次固定 W8、20 点、YOLO-only 性能回归；随后运行一次正常 YOLO-first、
  Grounded-SAM fallback-enabled 回归。
- 若 C2 仍未满足性能目标，再以相同 commit、输入和生命周期做 C2/C4 A/B。

## 11. 验收标准

自动化和 ai-station 现场证据同时满足以下条件，才能宣布优化完成：

- IPC accept-idle A/B 从稳定失败变为稳定通过，`TRUNCATED_FRAME=0`。
- 8-client 微基准观察到 8 个 pending RPC、queue depth 大于 1 和配置对应的模型并发峰值。
- 所有 idempotency key 的逻辑推理计数均不超过 1。
- 固定 W8 的 20 个点全部 `PASSED`，每个点都有新的初始状态、感知、MoveIt、controller、MuJoCo
  和 sealed result 证据。
- 固定 W8 运行不发生 fallback，最终精确清理通过，没有残留 ROS Domain、容器、socket 或进程。
- READY 到 `POSE_ACCEPTED` 的 P95 小于 5 秒；同时报告最大值和超过 5 秒的点，不能只报均值。
- 正常自适应运行仍可在 W8 基础设施故障后降到 W6，已完成点不重跑。
- 新的 GUI 截图和数值状态证明最终物理结果与 batch summary 一致。

如果 20/20 正确性通过但仍有少量 5 秒 SLO 超限，结果记为“功能通过、性能未通过”，继续分析
CPU 调度、frame 复制和证据写入，不能缩短 hard timeout 或弱化 pose admission 来制造通过。

## 12. 证据和清理

这项工作沿用 `docs/experiments/so101-parallel-adaptive-worker-pool-experiment-ledger.md`，由 ai-station
的单一执行者追加实验。高频时序和完整批次证据使用该任务已经登记的 durable evidence root；
pytest 的 `TMPDIR`、`TMP` 和 `TEMP` 必须位于其中新建且此前不存在的 NVMe scratch。

每轮记录 source commit、install overlay、runtime executable、ROS Domain、MuJoCo session、配置和
退出码。任务结束时分别列出 retained、archived 和删除候选；未经用户明确授权不删除日志、截图、
scratch 或旧实验。

本文只定义优化契约。完成自动化测试和 ai-station 现场回归之前，不能声称 IPC 缺陷或 W8 延迟
已经修复。
