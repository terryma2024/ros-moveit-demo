# SO-101 MoveIt 专家多点并行验证设计

日期：2026-09-11

状态：方案已确认，等待实施计划。本文只定义并行验证的行为、隔离和证据要求，不代表调度器、Worker 或共享感知服务已经实现，也不改变当前在 ai-station 上运行的顺序批次。

## 1. 背景

现有 MoveIt 专家模式需要在 20 个固定杯子点位上完成回归。顺序执行便于排查，但单轮耗时较长；简单地同时启动多个完整 ROS 2 栈，又容易出现 topic 串线、控制器互相干扰、GPU 抢占和结果账本并发写坏等问题。

本设计把一次多点验证拆成一个协调器、若干隔离 Worker 和一个可选的共享感知服务。启动时动态指定 Worker 数量和每个 Worker 最多处理的点数。Worker 不绑定固定分片，而是从全局队列逐点领取任务；某个点失败后，只要该 Worker 完成恢复并重新通过初始状态检查，它仍可继续领取剩余点，其他 Worker 也不受影响。

本设计不要求多个点共享同一个进程栈，也不要求复现单进程 `RESET_WORLD` 的内部步骤。唯一必须保持的语义是：每个点开始执行前，都有可审计证据证明它处于规定的初始状态。

## 2. 目标与非目标

### 2.1 目标

- 用一个启动命令动态配置 Worker 数量和单 Worker 的最大领取量。
- 允许 Worker 从全局队列动态抢任务，减少固定分片造成的空闲。
- 保证同一点不会被两个有效 Worker 同时执行。
- 保证每个点从经过验证的初始状态开始。
- 感知始终优先使用 YOLO-Seg，仅在规定的感知失败边界内回退到 Grounded-SAM。
- 单点失败不终止整批验证；恢复成功的 Worker 可以继续处理其他点。
- 用同一份不可并发篡改的汇总账本判断 20 个点是否全部覆盖、是否全部通过。
- 保存足以复核感知、规划、执行、物理结果和 Worker 恢复过程的证据。

### 2.2 非目标

- 不在首版中并行控制实体机械臂。
- 不用自动重试覆盖首轮有效失败，也不把重试成功改写成首轮成功。
- 不通过放宽碰撞、抓取、放置或视觉验收阈值提高成功率。
- 不允许多个 Worker 共享同一个 ROS graph、控制器、MuJoCo 实例或可写结果文件。
- 不把不同代码、模型或运行配置产生的结果拼成一轮 20/20。

## 3. 已确认决策

| 项目 | 决策 |
| --- | --- |
| 并行单位 | 一个 Worker 同时只执行一个点 |
| Worker 数量 | 启动时通过 `--worker-count N` 指定 |
| 单 Worker 处理量 | 启动时通过 `--max-points-per-worker K` 指定最大领取次数 |
| 分配方式 | 全局队列、原子 lease、动态抢任务，不做固定分片 |
| 容量检查 | `N × K` 小于待测点数时拒绝启动；容量大于点数允许 |
| 初始状态 | 每个点执行前独立恢复并通过初始状态门控 |
| 感知顺序 | YOLO-Seg 优先；只有未接受有效 `/cup_pose` 前的感知失败才允许 Grounded-SAM 回退 |
| 单点失败 | 封存失败证据，点位记为 `FAILED`，本轮不自动重试 |
| 后续调度 | Worker 恢复成功后回到池中，可继续领取其他剩余点 |
| Worker 恢复失败 | Worker 进入 `QUARANTINED`，不再领取任务；其他 Worker 继续 |
| 整批停止条件 | 所有点进入终态，或剩余可用容量不足且没有 Worker 可以继续 |
| 合格条件 | 20 个点在同一代码、模型、配置与策略哈希下全部首次有效执行成功 |

## 4. 总体架构

```text
                         ┌─────────────────────────────┐
                         │ ParallelBatchCoordinator    │
                         │ queue / lease / admission   │
                         │ aggregate ledger / summary  │
                         └──────────────┬──────────────┘
                                        │ atomic lease
              ┌─────────────────────────┼─────────────────────────┐
              ▼                         ▼                         ▼
       ┌─────────────┐           ┌─────────────┐           ┌─────────────┐
       │ Worker 01   │           │ Worker 02   │    ...    │ Worker NN   │
       │ isolated    │           │ isolated    │           │ isolated    │
       │ ROS/MuJoCo  │           │ ROS/MuJoCo  │           │ ROS/MuJoCo  │
       └──────┬──────┘           └──────┬──────┘           └──────┬──────┘
              │ perception request      │                         │
              └─────────────────────────┼─────────────────────────┘
                                        ▼
                         ┌─────────────────────────────┐
                         │ PerceptionBroker            │
                         │ YOLO-Seg → Grounded-SAM     │
                         └─────────────────────────────┘
```

协调器是任务状态和汇总结果的唯一权威。Worker 负责单点的场景恢复、初始状态验证、MoveIt 专家执行、结果判定和本地证据封存。共享感知服务只负责模型推理，不直接发布跨 Worker 共用的 ROS topic，也不持有调度权。

首版在 ai-station 上默认使用 2 个 Worker。只有在双 Worker 运行期间 CPU、内存、GPU 显存、仿真实时率和渲染稳定性均通过准入门控后，才允许把启动参数提高到 3；启动器不得在资源不足时静默减少 Worker 数量。

## 5. 启动契约与准入检查

计划中的命令接口如下，名称和参数将在实施计划中映射到具体脚本：

```bash
so101_parallel_batch \
  --points <point-manifest> \
  --worker-count 2 \
  --max-points-per-worker 10 \
  --evidence-root <registered-evidence-root>
```

启动前必须完成以下检查：

1. `N` 和 `K` 均为正整数，且 `N × K` 不小于清单中的唯一点数。
2. 点位 ID 唯一，点位坐标、目标位置和预期场景配置可解析。
3. 代码提交、工作区差异、安装产物、运行策略、YOLO 权重和 Grounded-SAM 权重均生成哈希。
4. 每个 Worker 已分配唯一资源：`ROS_DOMAIN_ID`、仿真及桥接端口、进程会话、`ROS_HOME`、日志目录和临时目录。
5. 共享 GPU 服务完成模型预热和最小推理自检；若不使用共享服务，则每个 Worker 的独立模型实例也必须通过资源准入。
6. 汇总账本不存在同名活动批次，证据根目录已注册且对本次批次唯一。

在 ai-station 上执行会创建大量临时文件的 pytest 或 benchmark 时，`TMPDIR`、`TMP` 和 `TEMP` 必须指向本批次证据根目录下新建的 NVMe scratch 子目录，并用实际测试 Python 验证 `tempfile.gettempdir()`。运行产生的 scratch 作为删除候选记录，但未经授权不删除。

## 6. 调度、lease 与 Worker 状态

Worker 状态如下：

```text
STARTING → AVAILABLE → LEASED → INITIALIZING → EXECUTING → FINALIZING
               ▲                                            │
               └────────────── RECOVERING ◀─────────────────┘
                                      │
                                      └────────→ QUARANTINED

任意可停止状态 → STOPPED
```

协调器只向 `AVAILABLE` 且领取次数小于 `K` 的 Worker 发放任务。每次发放都创建带 generation 的 lease，至少包含 `batch_id`、`worker_id`、`point_id`、`attempt_id`、领取时间和过期时间。Worker 同时只能持有一个有效 lease；领取即消耗一次容量，无论最终结果是成功、有效失败还是基础设施无效尝试。

对同一点，协调器只能承认当前 generation 的事件和结果。Worker 崩溃、lease 超时或进程被替换后，旧 generation 被 fenced；迟到的状态、感知结果和最终写入只能进入审计记录，不能改变当前点位状态。只有旧进程已停止、资源已清理且新 generation 已建立后，基础设施无效的点才可重新入队。

调度器必须保持以下不变量：

- 一个点最多有一个当前有效 lease。
- 一个 Worker 最多有一个当前有效 lease。
- Worker 的领取总数不超过 `K`。
- 一个点的有效测试失败不会导致全局队列停止。
- 恢复并重新通过初始状态门控的同一个 Worker 可以继续领取其他点。
- 不得把一个有效失败点在同一轮中自动放回队列。
- 所有点进入终态后才可声明 `coverage_complete=true`。

## 7. 单点生命周期与初始状态门控

每个点按以下流程运行：

```text
LEASED
  → reset isolated world
  → verify initial state
  → acquire fresh perception
  → plan and execute pick-place
  → validate physical result
  → seal evidence and result
  → recover worker
  → AVAILABLE or QUARANTINED
```

初始状态门控至少验证：

- 机械臂处于规定的 canonical joints，关节速度已稳定在容差内。
- 杯子位于本点要求的精确初始位姿，并在规定观察窗内保持稳定。
- 杯子没有残留约束、焊接、吸附或夹指接触。
- MoveIt Planning Scene 中没有 attached object，世界碰撞物与仿真同步。
- 所需控制器均为 active，且没有上一次执行遗留的活跃 goal。
- reset epoch、session、attempt 和感知输入时间戳均为本次新值。
- ROS graph 中不存在同 Worker 的旧节点或跨 Worker 的控制 topic。

任一条件不满足时，禁止开始机械臂动作。门控输入、判定值和失败原因全部写入证据。只调用 reset 服务而不读回状态，不足以证明点位从初始状态开始。

## 8. 感知优先级与共享服务边界

每个点先向感知服务发送 YOLO-Seg 请求。只有在 MoveIt 尚未接受有效 `/cup_pose`，并且出现下列感知类原因时，才允许在同一 point attempt 内回退到 Grounded-SAM：

- YOLO 没有合格检测；
- 分割掩码或深度投影不满足既定质量门控；
- YOLO 服务返回明确的模型或推理错误。

IK、规划、控制器、碰撞、抓取、释放或放置失败不触发 Grounded-SAM。已经接受有效 `/cup_pose` 后也不通过切换模型重新解释同一失败。

每个推理请求至少携带 `batch_id`、`worker_id`、`point_id`、`attempt_id`、reset epoch、图像时间戳和输入哈希。响应必须原路返回请求 Worker，并经过身份、新鲜度和 generation 检查。共享服务不向所有 ROS domain 广播一个 `/cup_pose`，从而避免结果串线。

证据中分别记录 YOLO 和 Grounded-SAM 的请求、耗时、输出、拒绝原因、权重哈希与最终选用结果。共享 GPU 队列属于共同依赖；队列超时或服务崩溃需要显式报告，不能伪装成“未检测到杯子”。

## 9. 失败处理与继续执行

失败分为两类：

### 9.1 有效测试失败

点位已经通过初始状态门控并进入正式 attempt，随后在感知、IK、规划、控制、抓取、释放、放置或最终物理验收中失败。这里的感知失败是指请求已经由模型正常处理，但 YOLO 和允许的 Grounded-SAM 回退都没有产生合格 pose；它不同于共享服务宕机或通信中断。协调器将该点记为 `FAILED`，封存完整证据，本轮不自动重试。该失败计入首次执行成功率。

Worker 随后进入 `RECOVERING`。恢复需要停止动作提交、取消并确认控制器 goal 已停止、清除 attached object、恢复机械臂和杯子、等待物理稳定，并再次通过完整初始状态门控。恢复成功后，Worker 回到 `AVAILABLE`，可领取任意尚未执行的点；它不需要等待其他 Worker，也不要求换 Worker。恢复失败则进入 `QUARANTINED`。

### 9.2 基础设施无效尝试

Worker 启动失败、资源冲突、过期 lease、reset 无法验证，或在任何模型正常处理请求前出现感知服务宕机或通信中断，记为 `INVALID`，不计入点位成功率。只有在旧 lease 已 fenced、相关进程已停止、证据已封存并重新通过准入后，协调器才可用新的 attempt 将该点重新入队。所有无效尝试仍保留在审计账本中。

如果可用 Worker 的剩余领取容量不足以覆盖未完成点，批次以 `CAPACITY_EXHAUSTED` 结束。启动时的 `N × K` 检查只能保证理论容量；Worker 隔离或基础设施无效尝试消耗的容量仍可能使运行中出现不足，汇总报告必须明确列出。

## 10. 结果状态与整批判定

结果状态包括：

| 状态 | 含义 |
| --- | --- |
| `PASSED` | 初始状态有效，完整 pick-place 与最终物理验收通过 |
| `FAILED` | 初始状态有效，但正式执行或验收失败 |
| `UNRUN` | 批次结束时没有获得有效执行机会 |
| `INVALID` | 仅用于 attempt 记录；点位仍需重新执行，不能作为批次终态成功 |

其中 `PASSED`、`FAILED` 和批次结束时的 `UNRUN` 是点位终态；`INVALID` 只是一次 attempt 的状态。

整批汇总至少公开以下字段：

- `coverage_complete`：所有选定点均为 `PASSED` 或 `FAILED`。
- `qualification_passed`：`coverage_complete=true` 且所有点均为 `PASSED`。
- 首次有效执行成功数、失败数、未执行数和无效 attempt 数。
- 各失败阶段、感知模型使用情况、Worker 领取量和隔离情况。
- 代码、工作区差异、安装、策略、场景、模型和点位清单哈希。

“20 个点都回归通过”只对应 `qualification_passed=true`。`coverage_complete=true` 只能说明全部点都得到有效结果，不能写成 20/20 成功。

如果运行过程中修改代码、点位、场景、模型权重、阈值或控制策略，旧结果不能与新结果合并成同一轮 20/20。变更后需要用新的批次 ID 在同一组新哈希下重跑全部 20 点。

## 11. 进程与资源隔离

每个 Worker 至少独占：

- `ROS_DOMAIN_ID`；
- MuJoCo、MoveIt、controller manager 和桥接进程树；
- 仿真端口、渲染设备上下文或虚拟显示编号；
- `ROS_HOME`、日志、参数快照和临时目录；
- 证据根目录下的 `workers/<worker-id>/` 子目录。

共享内容仅限只读代码、只读安装产物、冻结配置、模型权重和显式的 PerceptionBroker。不得通过相同 ROS domain、相同 controller namespace 或相同可写 SQLite/JSON 文件共享状态。停止一个 Worker 时，只能按已登记的 PID、进程组和资源 ID 清理，不能使用影响其他 Worker 或其他任务的宽泛进程匹配。

建议的资源准入指标包括 CPU 饱和度、可用内存、GPU 显存余量、GPU 推理排队时延、仿真实时率、controller deadline miss 和渲染丢帧。首版先用两个 Worker 跑小规模集合并记录这些指标，再决定是否允许三个 Worker。

## 12. 证据目录与写入权

整批运行只注册一个证据根目录。建议结构如下：

```text
<evidence-root>/
  batch_manifest.json
  source_manifest.json
  lease_events.jsonl
  aggregate_results.json
  workers/
    worker-01/
      worker_manifest.json
      attempts/<point-id>/<attempt-id>/
        initial_state/
        perception/
        planning/
        execution/
        final_state/
        recovery/
    worker-02/
      ...
  scratch/
  reports/
```

协调器是 `lease_events.jsonl` 和 `aggregate_results.json` 的唯一写入者。Worker 只写自己的 attempt 目录，再通过带哈希的完成消息请求协调器归档结果。汇总写入采用临时文件、fsync 和原子替换，避免进程中断留下半份 JSON。原始事件采用追加式记录，不能因为最终结果变化而覆盖历史。

每个有效点至少保留：初始状态读回、感知输入与叠加图、`/cup_pose` 及 TF 证据、规划结果、控制器状态、关键阶段截图或渲染帧、杯子最终位姿、接触/约束状态、失败原因和恢复结果。并行运行可使用各自的离屏渲染，不要求共享 GUI，但视觉证据必须能映射到唯一的 Worker、点位、attempt、仿真进程和时间戳。

批次结束时报告保留批次、归档批次和删除候选；未经用户授权，不删除证据或 scratch。

## 13. 测试与验收

### 13.1 调度器单元测试

- `N × K` 不足时拒绝启动，等于或大于点数时正常启动。
- 并发领取不会产生重复有效 lease。
- Worker 领取次数不会超过 `K`，同时只持有一个 lease。
- 点位失败后不会自动重试，其他点继续调度。
- 同一 Worker 恢复成功后能够领取下一个点。
- 恢复失败的 Worker 被隔离，其他 Worker 继续。
- lease 超时、Worker 崩溃和迟到结果均受 generation fencing 约束。
- 理论容量尚有但实际可用容量耗尽时返回明确批次状态。

### 13.2 感知与证据测试

- 每个点都先调用 YOLO；只有允许的感知失败原因触发 Grounded-SAM。
- 已接受 `/cup_pose` 后的规划或执行失败不触发模型切换。
- 不同 Worker 的并发请求不会交换图像、pose 或证据目录。
- 协调器崩溃重启后能够从追加事件和已封存 attempt 恢复，不重复承认结果。
- 汇总账本能检测缺失文件、哈希不一致和重复点位。

### 13.3 集成与现场验收

1. 用两个 Worker 和少量点位验证资源隔离、动态抢任务和失败后继续执行。
2. 注入单 Worker 崩溃、感知服务超时和恢复失败，验证 fencing、重新入队与隔离行为。
3. 在不改代码和配置的前提下运行完整 20 点批次。
4. 对每个点审查初始状态、感知、规划、执行、最终物理状态和关键视觉证据。
5. 只有 20 个点均为 `PASSED` 且全部哈希一致，才通过并行回归验收。

仿真验收不能替代实体机械臂验收。任何实机并行方案都需要重新设计控制权、急停、工作空间和人员安全边界。

## 14. 分阶段实施顺序

1. 实现纯调度器、lease、generation fencing 和账本测试，不启动 ROS 2。
2. 封装单 Worker 生命周期，使顺序执行也走同一初始状态和证据接口。
3. 增加 PerceptionBroker 和请求身份校验，验证 YOLO 优先与受限回退。
4. 运行两个隔离 Worker 的小规模集成测试，完成资源准入。
5. 运行 20 点并行批次并审查全部证据。

当前 ai-station 上的顺序批次继续按原流程运行，不作为本并行实现的替代验证，也不会被本设计打断。

## 15. 未采用的方案

| 方案 | 未采用原因 |
| --- | --- |
| 固定把点位切成 N 份 | 慢点或故障会让部分 Worker 空闲，无法利用剩余容量 |
| 任一点失败就终止全批次 | 无法收集完整失败分布，也不符合继续执行剩余点的要求 |
| 失败点在同一轮自动重试 | 会掩盖首次有效执行成功率，使 20/20 含义不清 |
| 多 Worker 共用一个 ROS 2/MoveIt 栈 | 控制权、topic 和状态容易串线，难以证明点位隔离 |
| 每个 Worker 各自写总账 | 会产生覆盖、乱序和重复承认，审计困难 |
| 一开始启动 20 个完整 Worker | ai-station 的 CPU、内存、GPU 和渲染资源不足以支持可验证的稳定运行 |
