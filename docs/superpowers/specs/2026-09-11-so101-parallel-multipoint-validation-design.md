# SO-101 MoveIt 专家多点并行验证设计

日期：2026-09-11

更新：2026-09-12，根据 Astra/high 审查补齐容量耗尽、感知故障矩阵、恢复门控、lease 看门狗、协调器崩溃恢复和 Broker 背压。

状态：方案已确认，等待实施计划。本文只定义并行验证的行为、隔离和证据要求，不代表调度器、Worker 或共享感知服务已经实现，也不改变当前在 ai-station 上运行的顺序批次。

## 1. 背景

现有 MoveIt 专家模式需要在 20 个固定杯子点位上完成回归。顺序执行便于排查，但单轮耗时较长；简单地同时启动多个完整 ROS 2 栈，又容易出现 topic 串线、控制器互相干扰、GPU 抢占和结果账本并发写坏等问题。

本设计把一次多点验证拆成一个协调器、若干隔离 Worker 和一个共享感知服务。启动时动态指定 Worker 数量和每个 Worker 最多处理的点数。Worker 不绑定固定分片，而是从全局队列逐点领取任务；某个点失败后，只要该 Worker 完成恢复并重新通过初始状态检查，它仍可继续领取剩余点，其他 Worker 也不受影响。

本设计不要求多个点共享同一个进程栈，也不要求复现单进程 `RESET_WORLD` 的内部步骤。唯一必须保持的语义是：每个点开始执行前，都有可审计证据证明它处于规定的初始状态。

本文只编排 MoveIt 专家多点回归，不修改 `2026-09-11-so101-act-head-wrist-rgb-implementation.md` 中的 ACT observation、动作执行或控制权设计。以后若让 ACT 使用同一批调度器，需要单独定义 profile 和验收，不能让 batch lease 取代 ACT 的单 Worker 控制权仲裁。

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
| 首版后端 | 仅 MuJoCo；Gazebo 并行适配不在首版范围 |
| 初始状态 | 每个点执行前独立恢复并通过初始状态门控 |
| 感知顺序 | YOLO-Seg 优先；只有未接受有效 `/cup_pose` 前的感知失败才允许 Grounded-SAM 回退 |
| 单点失败 | 封存失败证据，点位记为 `FAILED`，本轮不自动重试 |
| 后续调度 | Worker 恢复成功后回到池中，可继续领取其他剩余点 |
| Worker 恢复失败 | Worker 进入 `QUARANTINED`，不再领取任务；其他 Worker 继续 |
| 整批停止条件 | 所有点进入终态；或队列仍有点，但没有在途任务，也没有可恢复且尚有容量的 Worker |
| 合格条件 | 20 个点在同一代码、模型、配置与策略哈希下全部首次有效执行成功，且批次安全收尾完成 |

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

协调器是任务状态和汇总结果的唯一权威。Worker 负责单点的场景恢复、初始状态验证、MoveIt 专家执行、结果判定和本地证据封存。共享感知服务只负责模型推理，不直接发布跨 Worker 共用的 ROS topic，也不持有调度权。Worker 内部现有或后续的 controller ownership broker 仍负责动作控制权；它与负责点位分配的 batch lease 是两个边界，不能互相替代。

首版只运行 MuJoCo。manifest 固定 `backend=mujoco`，provenance 中记录 `GZ_PARTITION=not_applicable`。如果以后支持 Gazebo，需要另加独立 `GZ_PARTITION`、Gazebo transport 端口和相应物理证据适配器，不能把 MuJoCo 的隔离声明直接套用到 Gazebo。

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
5. 共享 GPU 服务完成 YOLO-Seg 和 Grounded-SAM 的模型预热及最小推理自检。
6. 汇总账本不存在同名活动批次，证据根目录已注册且对本次批次唯一。
7. manifest 明确冻结 `backend=mujoco`、资源阈值、初始状态容差、各阶段硬期限、heartbeat/ACK 超时、Broker 队列上限、排队/推理 deadline 和公共依赖恢复期限。

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

协调器把启动时创建的 N 个 Worker 视为稳定 slot。进程重启会增加该 slot 的 `worker_generation`，但不会重置它已经消耗的领取次数。协调器只向 `AVAILABLE` 且领取次数小于 `K` 的 slot 发放任务。每次发放都创建 lease，至少包含 `batch_id`、`coordinator_epoch`、`worker_id`、`worker_generation`、`point_id`、`attempt_id`、`lease_generation`、领取时间和单调时钟截止时间。Worker 同时只能持有一个有效 lease；领取即消耗一次容量，无论最终结果是成功、有效失败还是基础设施无效尝试。

lease 使用协调器所在主机的单调时钟。Worker 通过独立看门狗发送 heartbeat；看门狗不能被 MoveIt 规划或 GPU 推理线程阻塞。协调器只允许 `INITIALIZING`、`EXECUTING`、`FINALIZING` 和 `RECOVERING` 状态在各自硬期限内续期，阶段硬期限由冻结 manifest 给出，续期不能越过批次总期限。Worker 在 heartbeat ACK 超时或发现 `coordinator_epoch` 改变后，必须停止提交新动作和新感知请求，取消并确认已有 controller goal，随后进入隔离等待；不能假定 lease 仍有效而继续运动。

lease 过期不是本地计时器的隐式副作用，而是协调器串行写入账本的 `LEASE_EXPIRED` 事件。完成提交和过期检查由同一把协调器状态锁线性化：先持久化的事件决定归属。过期后，旧 `lease_generation` 被 fenced；迟到事件只能进入审计记录。只有旧进程已停止、控制器停止已确认、资源已清理，而且本次 attempt 的结果归属已经按第 12 节裁决后，点位才可能重新入队。

`point_initial_gate` 通过后，Worker 先提交门控摘要和 `START_ATTEMPT` 请求。协调器核对当前 lease，写入并 fsync `ATTEMPT_STARTED`，再返回带当前 epoch 的 ACK。Worker 收到 ACK 后才能发送第一条模型请求或机械臂命令。这样，协调器账本中的 `ATTEMPT_STARTED` 是正式执行是否获准开始的权威边界。

调度器必须保持以下不变量：

- 一个点最多有一个当前有效 lease。
- 一个 Worker 最多有一个当前有效 lease。
- Worker 的领取总数不超过 `K`。
- 一个点的有效测试失败不会导致全局队列停止。
- 恢复并通过 `worker_ready_gate` 的同一个 Worker 可以继续领取其他点。
- 不得把一个有效失败点在同一轮中自动放回队列。
- 所有选定点均提交为 `PASSED` 或 `FAILED` 后才可声明 `coverage_complete=true`。
- 公共依赖不健康时暂停新 lease，不能靠连续制造 `INVALID` attempt 消耗容量。

## 7. 单点生命周期与初始状态门控

每个点按以下流程运行：

```text
LEASED
  → reset isolated world for leased point
  → point initial gate
  → acquire fresh perception
  → plan and execute pick-place
  → validate physical result
  → seal immutable attempt result
  → commit point result
  → recover worker to canonical ready state
  → append recovery receipt
  → worker ready gate
  → AVAILABLE or QUARANTINED
```

这里有两个不同的门控，不能合并：

- `worker_ready_gate` 不依赖下一点。它验证 Worker 进程健康、机械臂回到 canonical joints、控制器无活跃 goal、物理世界和 Planning Scene 均无 attachment、没有残留接触或约束、ROS graph 没有旧进程。杯子可以位于恢复区或上一点的稳定终态；这一门不要求下一点坐标、attempt ID 或新感知帧。
- `point_initial_gate` 在领取下一点并完成该点 reset 后运行。它验证下面列出的点位初始状态，并绑定新 `attempt_id` 和 reset epoch。只有该门通过，正式 attempt 才能开始。

`point_initial_gate` 至少验证：

- 机械臂处于规定的 canonical joints，关节速度已稳定在容差内。
- 杯子位于本点要求的精确初始位姿，并在规定观察窗内保持稳定。
- 杯子没有残留约束、焊接、吸附或夹指接触。
- MoveIt Planning Scene 中没有 attached object，世界碰撞物与仿真同步。
- 所需控制器均为 active，且没有上一次执行遗留的活跃 goal。
- reset epoch 和 attempt 均为本次新值；仿真 session 绑定当前 MuJoCo 实例，只有实例重建时才更换。
- 相机已有晚于本次 reset 完成事件的新鲜源帧；后续送入推理的每一帧都携带相同 attempt、reset epoch 和 session 身份。
- ROS graph 中不存在同 Worker 的旧节点或跨 Worker 的控制 topic。

任一条件不满足时，禁止开始机械臂动作。门控输入、判定值和失败原因全部写入证据。只调用 reset 服务而不读回状态，不足以证明点位从初始状态开始。

点位执行与物理结论先写入不可变的 `attempt_result_sealed`，由协调器按第 12 节提交为点位结果。恢复证据不回写该目录；Worker 完成 canonical 恢复后另行追加 `worker_recovery_receipt`。最后一个点也必须完成停止和恢复收尾，但恢复失败不会改写已经提交的 `PASSED` 或 `FAILED`。它会令 `batch_cleanup_complete=false`，Worker 进入 `QUARANTINED`，整批不能通过运行资格验收，直到受控停止完成并留下独立证据。

## 8. 感知优先级与共享服务边界

每个点先向感知服务发送 YOLO-Seg 请求。只有在 MoveIt 尚未接受有效 `/cup_pose`，并且出现下列感知类原因时，才允许在同一 point attempt 内回退到 Grounded-SAM：

- YOLO 没有合格检测；
- 分割掩码或深度投影不满足既定质量门控；
- YOLO 服务返回明确的模型或推理错误。

IK、规划、控制器、碰撞、抓取、释放或放置失败不触发 Grounded-SAM。已经接受有效 `/cup_pose` 后也不通过切换模型重新解释同一失败。

每个推理请求至少携带 `request_id`、`batch_id`、`coordinator_epoch`、`worker_id`、`worker_generation`、`point_id`、`attempt_id`、`lease_generation`、reset epoch、图像时间戳和输入哈希。响应必须原路返回请求 Worker，并经过身份、新鲜度和 fencing 检查。共享服务不向所有 ROS domain 广播一个 `/cup_pose`，从而避免结果串线。

Broker 只返回候选结果。Worker 内的 pose admission adapter 负责校验 TF 时间、点位边界、质量门控和 attempt 身份；通过后写入不可逆的 `POSE_ACCEPTED` 事件。该事件绑定产生它的 request、图像、TF、reset epoch 和 lease generation。“发布 `/cup_pose`”不等于 MoveIt 已接受，是否允许回退只由 Worker 本地状态机根据 `POSE_ACCEPTED` latch 判断。

模型阶段统一使用以下结果分类：

| 当前模型结果 | YOLO 阶段 | Grounded-SAM 阶段 |
| --- | --- | --- |
| `QUALIFIED` | 进入 pose admission；接受后不再回退 | 进入 pose admission |
| `NORMAL_REJECTION` | 未产生合格候选时允许回退 | 不再回退 |
| `MODEL_ERROR` | 返回结构完整、可归属到本 request 的模型错误时允许回退 | 不再回退 |
| `INFRA_ERROR` | 不回退 | 不回退 |
| `QUEUE_TIMEOUT` / `INFERENCE_TIMEOUT` | 不回退 | 不回退 |

两个模型阶段结束后按以下顺序裁决，前一条命中后不再继续：

1. 已有 `POSE_ACCEPTED`：继续 MoveIt。
2. 任一阶段为 `INFRA_ERROR`、`QUEUE_TIMEOUT` 或 `INFERENCE_TIMEOUT`：记为 `INVALID`。
3. 没有 accepted pose，且至少一个阶段为确定的请求级 `MODEL_ERROR`：记为有效 `FAILED/PERCEPTION_MODEL_ERROR`。
4. YOLO 和 Grounded-SAM 均为 `NORMAL_REJECTION`：记为有效 `FAILED/PERCEPTION_NO_POSE`。

pose admission 拒绝按当前模型的 `NORMAL_REJECTION` 处理。上述顺序覆盖 `MODEL_ERROR + NORMAL_REJECTION` 的两种排列，不允许留下无终态的感知组合。

`MODEL_ERROR` 只表示模型对一个已验证输入完成处理并返回确定的请求级错误。Broker 进程退出、CUDA context 丢失、OOM 导致服务重启、RPC 断开、队列或推理超时都属于基础设施错误，不能计入点位成功率。先前模型是否正常响应，不改变后续基础设施错误的 `INVALID` 分类。

Broker 为 YOLO 和 Grounded-SAM 分别维护有界队列，按 Worker 轮转调度；单 Worker 对每个模型最多有一个在途请求。排队 deadline 和推理 deadline 分开记录。请求出队前和结果返回前都要重新检查 lease；已取消、过期或 fenced 的请求直接进入审计记录，不占用 pose admission。Broker generation 改变后，旧 generation 的响应全部失效。

Broker 健康检查失败时，协调器暂停发放新 lease。已经接受 pose 的 Worker 可以按冻结策略完成本点；尚未接受 pose 的在途 attempt 以 `INVALID` 收尾。Broker 只有在重启、模型预热和自检通过后才能恢复调度；如果在批次公共依赖恢复期限内仍不可用，批次停止发新任务，等待已经接受 pose 的 Worker 到达终态或阶段硬期限，再以 `SHARED_DEPENDENCY_UNAVAILABLE` 结束。这样不会用连续 `INVALID` attempt 耗光所有 Worker 容量。

证据中分别记录 YOLO 和 Grounded-SAM 的排队、推理、输出、admission、拒绝原因、权重哈希与最终选用结果。共享 GPU 服务的故障单独写入 batch 事件，不能伪装成“未检测到杯子”。

## 9. 失败处理与继续执行

attempt 结束时分为以下三类：

### 9.1 有效测试失败

点位已经通过 `point_initial_gate` 并进入正式 attempt，随后在感知、IK、规划、控制、抓取、释放、放置或最终物理验收中失败。感知结果按第 8 节矩阵分类；基础设施错误不属于有效失败。协调器将该点记为 `FAILED`，封存完整证据，本轮不自动重试。该失败计入首次执行成功率。

Worker 随后进入 `RECOVERING`。恢复需要停止动作提交、取消并确认控制器 goal 已停止、清除 attached object、恢复机械臂到 canonical joints、等待物理稳定，并通过 `worker_ready_gate`。成功后 Worker 回到 `AVAILABLE`，可领取任意尚未执行的点；它不需要等待其他 Worker，也不要求换 Worker。恢复失败则进入 `QUARANTINED`。下一点的杯子位姿、reset epoch、attempt 和新鲜感知只在领取后由 `point_initial_gate` 验证。

### 9.2 基础设施无效尝试

Worker 启动失败、资源冲突、reset 无法验证、感知 `INFRA_ERROR`、队列/推理超时，或正式 attempt 开始前失去有效 lease，记为 `INVALID`，不计入点位成功率。先前是否有某个模型正常响应不改变这一分类。只有旧 lease 已 fenced、相关进程和 controller goal 已确认停止、证据已封存并重新通过准入后，协调器才可用新的 attempt 将该点重新入队。所有无效尝试仍保留在审计账本中。

### 9.3 结果不确定

正式 attempt 已经开始，但 Worker 或协调器崩溃后既没有完整、可验证的结果 manifest，也无法证明动作未发生，点位记为 `INDETERMINATE`。它不计为成功或有效失败，也不在同一轮重试。这样可以避免把一次可能已经发生的抓放动作改写成无效基础设施尝试，再以第二次结果覆盖首次行为。

剩余总容量不足以覆盖所有排队点，只设置 `full_coverage_no_longer_possible=true`，不立即停止调度。健康 Worker 继续领取，直到用完各自剩余容量；已经持有 lease 的点继续等待结果，不计入排队点。只有队列仍非空、没有有效在途任务、没有处于可恢复状态且尚有容量的 Worker 时，批次才以 `CAPACITY_EXHAUSTED` 结束。启动时的 `N × K` 检查只能保证理论容量；Worker 隔离和基础设施无效尝试仍可能使运行中容量不足。

## 10. 结果状态与整批判定

结果状态包括：

| 状态 | 含义 |
| --- | --- |
| `PASSED` | 初始状态有效，完整 pick-place 与最终物理验收通过 |
| `FAILED` | 初始状态有效，但正式执行或验收失败 |
| `INDETERMINATE` | 正式 attempt 可能已经执行，但结果证据无法完整裁决；本轮不重试 |
| `UNRUN` | 批次结束时没有获得有效执行机会 |
| `INVALID` | 仅用于 attempt 记录；点位仍需重新执行，不能作为批次终态成功 |

其中 `PASSED`、`FAILED`、`INDETERMINATE` 和批次结束时的 `UNRUN` 是点位终态；`INVALID` 只是一次 attempt 的状态。

四层状态的写入权和重试边界如下：

| 层 | 权威所有者 | 关键持久事件 | 同轮可重试性 |
| --- | --- | --- | --- |
| Batch | Coordinator | `BATCH_STARTED`、公共依赖状态、批次终态 | 不适用；配置变化必须新建 batch |
| Worker slot | Coordinator | lease 计数、`worker_generation`、ready/quarantine | 进程可换代，K 不重置 |
| Point | Coordinator | `RESULT_COMMITTED` 或点位终态 | `FAILED`、`INDETERMINATE` 不重试；`INVALID` 尚未产生点位终态 |
| Attempt | 当前 Worker，Coordinator 提交 | `ATTEMPT_STARTED`、sealed manifest、recovery receipt | 只在 `INVALID` 且完成 fencing 后新建 attempt |

整批汇总至少公开以下字段：

- `coverage_complete`：所有选定点均为 `PASSED` 或 `FAILED`。
- `execution_complete`：所有点已经进入点位终态，包括 `INDETERMINATE` 或 `UNRUN`。
- `batch_cleanup_complete`：所有 Worker 已通过恢复门或完成受控停止，没有未确认的 controller goal 和物理副作用。
- `qualification_passed`：`coverage_complete=true`、所有点均为 `PASSED`，且 `batch_cleanup_complete=true`。
- 首次有效执行成功数、失败数、不确定数、未执行数和无效 attempt 数。
- 各失败阶段、感知模型使用情况、Worker 领取量和隔离情况。
- 代码、工作区差异、安装、策略、场景、模型和点位清单哈希。

“20 个点都回归通过”只对应 `qualification_passed=true`。`coverage_complete=true` 只能说明全部点都得到有效行为结果；`execution_complete=true` 甚至可能包含不确定或未执行点，二者都不能写成 20/20 成功。

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
  coordinator.lock
  coordinator_epoch.json
  events/
    <coordinator-epoch>.jsonl
  aggregate_results.json
  workers/
    worker-01/
      worker_manifest.json
      attempts/<point-id>/<attempt-id>/
        working/
        sealed/
          initial_state/
          perception/
          planning/
          execution/
          final_state/
          attempt_result_manifest.json
      recoveries/<recovery-id>/
        worker_recovery_receipt.json
    worker-02/
      ...
  scratch/
  reports/
```

协调器启动时获取证据根目录的独占锁，并持久化新的 `coordinator_epoch`。同一证据根只能有一个持锁协调器。所有状态变更都有唯一 `event_id` 和幂等键；重复请求返回第一次的结果，不重复扣减 K，也不重复承认点位结果。事件记录带长度和校验和，写入后 fsync。重启时若最后一条记录不完整，保留损坏尾部作为证据，从新 epoch 的事件段继续，不能把半条记录解释成已提交状态。

lease 发放遵守“先持久化，后授权”：协调器先写入并 fsync `LEASE_GRANTED`，其中同时记录 slot 的 K 消耗，再向 Worker 返回 lease。Worker 未收到带当前 epoch 的 ACK，不得 reset 场景或提交动作。协调器重启后从事件段重放 lease、容量和 generation；`aggregate_results.json` 只是可重建投影，不作为恢复权威。

Worker 结束 attempt 时，先停止新动作，在 `working/` 内写完全部结果文件和 `attempt_result_manifest.json`，再 fsync 每个文件及 `working/` 目录。随后把 `working/` 原子改名为 `sealed/`，并 fsync attempt 父目录；从这一刻起不得再写 sealed 内容。协调器验证当前 lease、manifest 哈希、必备证据和终态后，写入并 fsync `RESULT_COMMITTED`，再返回 ACK。ACK 丢失时，同一幂等键只返回已经提交的结果。

协调器重启时先完整重放所有历史事件。已有 `RESULT_COMMITTED`、`LEASE_EXPIRED` 或点位终态不可被后来的文件改写。只对尚未提交、尚未过期且尚未 fenced 的 lease 检查 sealed 目录，然后按以下顺序裁决：

- 有完整 sealed manifest，且 lease 身份和证据校验通过：补写幂等的 `RESULT_COMMITTED`，不重派该点。
- 有可信账本证明 `ATTEMPT_STARTED` 尚未授权：记为 `INVALID`，完成 fencing 和资源清理后可以新 attempt 重排。
- 能证明正式 attempt 已开始，但结果缺失或不完整：点位记为 `INDETERMINATE`，本轮不重试。

完成提交与 lease 过期在协调器状态锁下串行处理。协调器准备写 `LEASE_EXPIRED` 前，必须先检查当前 lease 的待处理提交和已注册 sealed 目录；完整且身份有效的结果先写为 `RESULT_COMMITTED`。`LEASE_EXPIRED` 已落盘后出现的 sealed 或提交只进入审计记录，即使协调器随后重启也不能重新承认：已有 `ATTEMPT_STARTED` 时点位进入 `INDETERMINATE`；有可信账本证明它从未被授权时才可记为 `INVALID`。如果账本损坏或其他原因导致“是否开始”无法证明，默认 `INDETERMINATE`，不得重派。任何点位重新入队前，都要先完成上述裁决以及旧 Worker 的停止确认，不能把协调器崩溃一律转换成 `INVALID`。

Worker 只写自己的 attempt 和 recovery 目录。`worker_recovery_receipt` 通过独立事件追加到已提交点位，不修改 sealed manifest。协调器是 batch 事件和 `aggregate_results.json` 的唯一写入者；投影写入采用临时文件、fsync 和原子替换。原始事件不因最终结果变化而覆盖。

每个有效点至少保留初始状态读回、感知输入与叠加图、控制器状态、关键阶段截图或渲染帧、杯子最终位姿、接触/约束状态和失败原因。已经接受 pose 的点还必须保留 `POSE_ACCEPTED`、`/cup_pose` 及 TF 证据；进入规划或执行的点保存对应结果。恢复结果由关联的 recovery receipt 保存。并行运行可使用各自的离屏渲染，不要求共享 GUI，但视觉证据必须能映射到唯一的 Worker、点位、attempt、仿真进程和时间戳。

批次结束时报告保留批次、归档批次和删除候选；未经用户授权，不删除证据或 scratch。

## 13. 测试与验收

### 13.1 调度器单元测试

- `N × K` 不足时拒绝启动，等于或大于点数时正常启动。
- 并发领取不会产生重复有效 lease。
- Worker 领取次数不会超过 `K`，同时只持有一个 lease。
- 点位失败后不会自动重试，其他点继续调度。
- 同一 Worker 恢复成功后能够领取下一个点。
- 恢复失败的 Worker 被隔离，其他 Worker 继续。
- 剩余容量不足以全覆盖时仍处理所有可执行点；只有没有在途任务和可用容量时才结束。
- heartbeat、续期、协调器 epoch 变化、lease 超时和迟到结果均受 generation fencing 约束。
- Worker 进程换代不会重置 K；理论容量尚有但实际可用容量耗尽时返回明确批次状态。
- 在 `LEASE_GRANTED`、K 扣减、`ATTEMPT_STARTED`、结果 seal、`RESULT_COMMITTED` 和 ACK 前后逐点注入协调器崩溃，恢复后不重复领取、不漏计容量、不覆盖首次结果。
- 验证“`LEASE_EXPIRED` 落盘 → 旧 Worker 迟到 seal → 协调器重启”不会重新承认旧结果；无法证明 attempt 未开始时进入 `INDETERMINATE`。

### 13.2 感知与证据测试

- 每个点都先调用 YOLO；只有允许的感知失败原因触发 Grounded-SAM。
- 已接受 `/cup_pose` 后的规划或执行失败不触发模型切换。
- YOLO 正常拒绝后 Grounded-SAM 基础设施失败，attempt 仍为 `INVALID`；两模型正常拒绝才是有效 `FAILED`。
- `MODEL_ERROR + NORMAL_REJECTION` 的两种排列都收敛到 `FAILED/PERCEPTION_MODEL_ERROR`。
- `POSE_ACCEPTED` 与 request、lease、reset epoch、图像和 TF 身份一致，发布 topic 本身不触发 latch。
- 不同 Worker 的并发请求不会交换图像、pose 或证据目录。
- 有界 Broker 队列保持 Worker 公平性；取消或 fenced 请求不会进入 pose admission。
- Broker 不健康时暂停新 lease，恢复失败时返回 `SHARED_DEPENDENCY_UNAVAILABLE`，不会连续消耗 K。
- 协调器崩溃重启后能够从追加事件和已封存 attempt 恢复；不完整的正式 attempt 进入 `INDETERMINATE`，不能自动重跑。
- 汇总账本能检测缺失文件、哈希不一致和重复点位。

### 13.3 集成与现场验收

1. 用两个 Worker 和少量点位验证资源隔离、动态抢任务和失败后继续执行。
2. 注入单 Worker 崩溃、感知服务超时、协调器各提交窗口崩溃和恢复失败，验证 fencing、结果裁决、重新入队与隔离行为。
3. 在不改代码和配置的前提下运行完整 20 点批次。
4. 对每个点审查初始状态、感知、规划、执行、最终物理状态和关键视觉证据。
5. 验证最后一点结果先提交、恢复收尾后追加；恢复失败不会改写点位结果，但会阻止运行资格通过。
6. 只有 20 个点均为 `PASSED`、全部哈希一致且 `batch_cleanup_complete=true`，才通过并行回归验收。

仿真验收不能替代实体机械臂验收。任何实机并行方案都需要重新设计控制权、急停、工作空间和人员安全边界。

## 14. 分阶段实施顺序

1. 实现纯调度器、持久事件协议、lease、generation fencing 和崩溃窗口测试，不启动 ROS 2。
2. 封装单 Worker 生命周期，拆开 worker ready、point initial、sealed result 和 recovery receipt。
3. 增加 PerceptionBroker、`POSE_ACCEPTED` 和请求身份校验，验证 YOLO 优先、受限回退与公共依赖暂停。
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
