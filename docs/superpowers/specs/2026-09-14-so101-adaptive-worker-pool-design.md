# SO-101 MoveIt 专家自适应 Worker 池设计

日期：2026-09-14

状态：设计决策已确认，等待文档复核和实施计划。

关联文档：

- `docs/superpowers/specs/2026-09-11-so101-parallel-multipoint-validation-design.md`
- `docs/superpowers/plans/2026-09-12-so101-parallel-multipoint-validation-implementation.md`
- `docs/superpowers/specs/2026-09-13-so101-parallel-w8-admission-design.md`（已废弃）
- `docs/superpowers/plans/2026-09-13-so101-parallel-w8-admission-implementation.md`（不再执行）
- `docs/experiments/so101-parallel-multipoint-validation-experiment-ledger.md`

本文把 W8 从严格准入目标改为批量点位验证的加速档。系统优先尝试 W8；如果当前 ai-station
无法稳定运行八个完整 Worker，就缩到 W6，必要时继续按 `W8 → W6 → W4 → W2 → W1`
降级。已经完成的点位结果不会重跑，剩余点继续执行。

本文只覆盖 MuJoCo MoveIt 专家模式。它不授权实体机械臂并发运行，也不修改 ACT 的 observation、
动作执行或控制权设计。与 2026-09-11 基础设计冲突时，自适应模式以本文为准；未启用自适应
模式时，原有行为保持不变。

## 1. 为什么改成轻量方案

W8 的目的很具体：缩短 20 个测试点的总执行时间。它不是长期在线服务，也不需要为一次离线
回归建立独立授权服务、签名画像和严格资源担保。W8 能跑就用；跑不起来时，W6 或更小的池仍然
能完成同一批点位。

因此，本设计保留对结果可信度有直接作用的边界：独立 ROS Domain、独立仿真世界、点位初始
状态检查、lease、结果持久化和精确进程清理。下列机制不再实现：

- `AdmissionAuthority` 和 systemd Authority/watchdog；
- Ed25519 密钥生成、签名画像和不可变 `/opt/.../releases/<hash>` 安装；
- cgroup 硬配额、固定 CPU/GPU/RAM 余量和 PSI/RTF 准入阈值；
- `1 → 2 → 4 → 6 → 8` 分级 qualification、同步 canary 和 provisional admission；
- 画像撤销、clean-host 判定和运行身份漂移审批；
- W8 Worker 丢失后必须恢复到八个 slot 才能继续的限制。

CPU、内存、显存和仿真实时率可以继续采样，但只用于解释性能和故障，不作为启动许可。
OOM、进程退出或通信中断仍是实际的基础设施故障，会触发降级。

## 2. 目标与非目标

### 2.1 目标

- 启动时动态指定 Worker 数量和初始点位分配量。
- 默认从 W8 开始，基础设施故障时自动按配置缩容。
- N 个 Worker 必须全部达到 `READY` 后才开放真实点位队列。
- Worker 从共享队列领取任务；初始分配完成后可以动态抢剩余点。
- 同一个健康 Worker 完成恢复后可以继续执行其他点，不绑定固定分片。
- 每个点在实际动作开始前都通过可读回的初始状态门控，不要求复刻 `RESET_WORLD` 的内部步骤。
- YOLO-Seg 优先；只在允许的感知失败边界内回退到 Grounded-SAM。
- 保留已经提交的 `PASSED` 和 `FAILED`；降级只重新排队未运行和被基础设施中断的点。
- 报告实际使用的 Worker 档位、降级原因、点位结果、各 Worker 负载和总耗时。

### 2.2 非目标

- 不保证 W8 一定能启动或完成。
- 不要求八个 Worker 同时处于 `EXECUTING`；只要求它们在队列开放时全部 `READY`，且每个都具备
  执行完整 pick-place 的能力。
- 不为临时回归环境提供生产级资源隔离或加密授权。
- 不用自动重试覆盖点位的感知、规划、抓取或放置失败。
- 不把降级后的完成时间记作原 Worker 档位的性能结果。
- 不允许多个 Worker 共享同一个 ROS graph、仿真世界、控制器 namespace 或可写结果目录。

## 3. 总体架构

```text
┌───────────────────────────────────────────────────────────────┐
│ AdaptiveBatchRunner                                           │
│ remaining points / terminal results / fallback journal        │
└──────────────────────────────┬────────────────────────────────┘
                               │ owns one active pool generation
                               ▼
┌───────────────────────────────────────────────────────────────┐
│ AdaptiveWorkerPool: W8 → W6 → W4 → W2 → W1                   │
│ start / READY barrier / health / exact cleanup / restart       │
└───────────────┬──────────────────────┬────────────────────────┘
                │                      │
       ┌────────▼────────┐    ┌────────▼────────┐
       │ complete Worker │ …  │ complete Worker │
       │ ROS + MuJoCo    │    │ ROS + MuJoCo    │
       │ MoveIt/controller│   │ MoveIt/controller│
       └────────┬────────┘    └────────┬────────┘
                └──────────┬───────────┘
                           ▼
                ┌──────────────────────┐
                │ PerceptionBroker     │
                │ YOLO → Grounded-SAM  │
                └──────────────────────┘
```

`AdaptiveBatchRunner` 是跨 pool generation 的点位终态和降级历史唯一写入者。每个
`AdaptiveWorkerPool` 在当前档位内复用一个现有 `ParallelBatchCoordinator`，负责本代 lease、attempt
ACK 和结果提交；Runner 只导入已 fsync 的终态。降级时整代停止并重新创建，Runner 则保留剩余点
和既有终态。Worker 负责一个点的初始化、感知、MoveIt 专家执行、物理验收和本地证据封存。

每个 Worker 是完整执行栈，至少拥有：

- 唯一 `ROS_DOMAIN_ID`；
- 唯一 MuJoCo session、进程组、`ROS_HOME`、日志和临时目录；
- 自己的 MoveIt/controller namespace 和点位证据目录；
- 独立 heartbeat、lease identity 和 worker generation；
- 到共享 PerceptionBroker 的具名连接，响应只能返回原 Worker。

## 4. 启动接口与兼容性

自适应行为必须显式开启：

```bash
so101_parallel_batch \
  --adaptive-workers \
  --config src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml \
  --adaptive-config src/so101_demo_py/config/mujoco/parallel_adaptive_workers_v1.yaml \
  --batch-id e2001 \
  --worker-count 8 \
  --fallback-worker-counts 6,4,2,1 \
  --initial-points-per-worker 3 \
  --worker-start-timeout-s 120 \
  --max-infra-attempts-per-point 5 \
  --points <absolute-point-catalog> \
  --evidence-root <registered-evidence-root>
```

现场和性能运行由仓库中的轻量监督脚本包装这条命令；直接调用 CLI 只用于自动化测试。监督脚本
不改变参数语义，只在 Runner 子进程异常退出后调用精确 owned-process cleanup。

参数约束如下：

- 自适应模式复用既有 `batch_id` 作为短 run ID，限制为 1–5 个 ASCII ID 字符；runtime root 固定
  为 `<evidence-root>/r/<batch-id>`，描述性标题写入 manifest，不进入 socket 路径。
- `worker_count` 是首选启动档位，必须为正整数。
- `fallback_worker_counts` 必须是严格递减、去重且小于首选档位的正整数列表。默认值为
  `6,4,2,1`；从 W6 启动时实际序列是 `W6 → W4 → W2 → W1`。
- `initial_points_per_worker` 是初始分配提示，不是容量上限。默认值为 3。
- `worker_start_timeout_s` 限制当前档位全部 Worker 达到 `READY` 的时间。
- `max_infra_attempts_per_point` 防止同一点随多次降级无限重试；默认值 5 对应五个档位。

未启用 `--adaptive-workers` 时，现有顺序和并行模式保持原语义，
`--max-points-per-worker` 仍是硬领取上限。自适应模式不接受
`--max-points-per-worker`，调用者必须改用 `--initial-points-per-worker`。两者同时出现时在创建
任何进程前报配置错误。

`--config` 继续提供已冻结的 MoveIt、lease、感知与模型运行契约；`--adaptive-config` 只提供
Worker 池配置。自适应配置使用独立的小型 schema，不复用已废弃设计中的
`parallel_batch_v2.yaml`。它只保存
默认档位、降级序列、启动超时、Domain 池和现有执行策略引用；Worker 数量与初始分配量允许在
命令行动态指定，并写入 batch manifest。

## 5. 当前档位的启动门

Runner 按降级序列逐档尝试。一个档位只有在全部 N 个 Worker 同时满足以下条件后才能从
`STARTING` 进入 `RUNNING`：

1. N 个进程组均存活，worker identity、generation 和 session 唯一。
2. 从配置的 Domain 池原子取得 N 个互不重复的 claim；每个 Domain 的必要 ROS graph 可读，
   没有发现本批次外的冲突节点。
3. 每个 Worker 的 MuJoCo、MoveIt 和 controller 进程完成最小健康回读。
4. 每个 Worker 可以向 Coordinator 发送 heartbeat，并完成一次不含真实点位动作的 Broker
   通信自检。
5. 日志、证据目录、socket 和临时目录互不重用。

这里没有 canary，也不运行测试点。自适应 Worker 启动后先在本地 start gate 等待，不调用 lease
RPC。Runner 收齐并最终复核全部 Worker 的新鲜 `READY` receipt 后，先把 `POOL_RUNNING` 作为启动
成功线性化点写入并 fsync，再向这一代全部 Worker 释放 start gate。线性化点之前的故障属于启动
失败，必须保持零 lease；线性化点之后的 release 或 Worker 故障属于运行中基础设施失败，裁决
可能已经领取的在途点后降级。启动等待不复用 Broker recovery 的 lease-pause 协议。

Domain allocator 每次只申请当前档位需要的 N 个 Domain。取得不足时释放本次全部 claim，然后
把该档位记为启动失败。它不预留未来档位，也不绑定固定的 215–222 slot 映射；manifest 记录
本次实际分配结果。

## 6. 初始分配与动态抢任务

20 个点只有一份跨档位权威剩余集。Runner 启动每一代时把剩余点交给本代 Coordinator；后者按
稳定点位顺序轮转填充 Worker 的 preferred deque，每个 Worker 最多填入
`initial_points_per_worker` 个点，其余点留在本代全局队列。初始分配只是亲和提示，不提前创建
lease。

Worker 空闲时按以下顺序取点：

1. 自己 preferred deque 中尚未 lease 的点；
2. 全局队列中的点；
3. 其他 Worker preferred deque 尾部尚未 lease 的点。

Coordinator 在同一把状态锁下原子创建 lease，所以一个点不会同时交给两个 Worker。完成初始
分配后没有每 Worker 领取上限；只要还有可执行点，任何 `AVAILABLE` Worker 都可以继续领取。

业务失败不会让 Worker 自动退出。它完成 canonical recovery 并再次通过 `worker_ready_gate` 后，
可以继续取其他点。恢复失败属于基础设施故障，触发当前 pool generation 降级。

## 7. 单点初始状态与执行

本设计不要求每个点执行与历史 `RESET_WORLD` 完全相同的内部流程。实现可以重建仿真实例、调用
确定性 reset，或恢复必要对象；验收只看实际读回的状态。

每个新 lease 都按下面的顺序运行：

```text
LEASED
  → restore point-specific initial state
  → point_initial_gate
  → START_ATTEMPT commit and ACK
  → fresh YOLO perception
  → optional Grounded-SAM fallback
  → MoveIt pick-place
  → physical result validation
  → seal and commit PASSED or FAILED
  → canonical recovery
  → worker_ready_gate
  → AVAILABLE
```

`point_initial_gate` 至少读回并验证：

- 机械臂处于 canonical joints，关节速度已经稳定；
- 夹爪处于规定初始状态，没有活跃 controller goal；
- 杯子位于点位清单规定的初始 6D pose 和容差内，并在观察窗中保持稳定；
- MuJoCo 物理状态与 MoveIt Planning Scene 均无残留 attachment；
- 当前 reset epoch、simulation session、point ID 和 lease identity 一致；
- 相机产生晚于本次恢复完成事件的新帧；
- ROS graph 中没有同 Worker 的旧进程或跨 Worker 控制 topic。

只收到 reset 命令成功响应不能通过此门。初始状态恢复或读回失败发生在正式 attempt 前，按基础
设施故障处理；点位清单本身非法则属于启动配置错误，整批在创建 Worker 前拒绝。

感知仍使用 2026-09-11 基础设计的边界：YOLO-Seg 始终先运行。只有在尚未写入
`POSE_ACCEPTED`，并且 YOLO 没有合格检测、掩码/深度投影未通过质量门，或返回确定的请求级
模型错误时，才允许用新鲜输入调用 Grounded-SAM。IK、规划、控制、抓取、释放和放置失败不触发
感知回退。Broker 退出、CUDA/OOM、RPC 断开和排队/推理基础设施超时也不触发模型回退。

## 8. 状态与结果

批次状态：

```text
CREATED
  → STARTING(W8)
  → RUNNING(W8)
  → DEGRADING(W8→W6)
  → RUNNING(W6)
  → ...
  → COMPLETED | COMPLETED_WITH_FAILURES | INFRA_FAILED
```

点位状态：

| 状态 | 含义 | 是否可重新入队 |
| --- | --- | --- |
| `UNRUN` | 尚未获得正式执行机会 | 是 |
| `LEASED` / `RUNNING` | 当前 generation 的在途状态 | 仅在故障裁决后 |
| `INFRA_INTERRUPTED` | 基础设施故障中断，尚无有效业务终态 | 是 |
| `PASSED` | pick-place 和物理验收通过 | 否 |
| `FAILED` | 有效初始状态下产生业务失败 | 否 |

`PASSED` 和 `FAILED` 是不可覆盖的点位终态。基础设施中断的 attempt 必须单独保留，记录动作是否
已经开始、最后可信状态和现场证据。如果动作可能已经发生，该 attempt 标记为
`INDETERMINATE`，但点位仍可在旧进程停止、世界重新恢复且新 `point_initial_gate` 通过后，以新
attempt 重新执行。后一次结果不能删除或改写前一次的不确定记录。

最终批次状态：

- `COMPLETED`：所有点位均为 `PASSED`，清理回读成功。
- `COMPLETED_WITH_FAILURES`：所有点位均已获得业务终态，至少一个为 `FAILED`，清理回读成功。
- `INFRA_FAILED`：降到 W1 后仍发生基础设施故障、降级清理无法完成、Coordinator 自身崩溃，或
  有点超过基础设施尝试上限。

## 9. 业务失败与基础设施故障

只有基础设施故障触发降级。

| 分类 | 例子 | 处理 |
| --- | --- | --- |
| 业务失败 | 没有合格 pose、IK/规划失败、碰撞拒绝、抓取失败、放置超差 | 提交 `FAILED`，当前档位继续 |
| 启动故障 | Worker 未按时 READY、Domain 不足、必要进程启动失败 | 清理当前档位，尝试下一档 |
| 运行故障 | Worker/仿真/Broker 进程退出、heartbeat 丢失、ROS/Broker 断连、OOM | 保留终态，裁决在途点，随后降级 |
| 恢复故障 | canonical recovery、初始状态恢复或清理回读失败 | 降级；未产生业务终态的点重新排队 |

MoveIt 或 controller 在健康通信链上返回明确的规划/执行失败，属于业务失败。进程失联、transport
超时或无法取得可归属的返回值，属于基础设施故障。共享 Broker 故障会让整个 pool generation
失效，不能伪装成 YOLO 未检测到杯子。

资源采样不设置预警阈值。只有已经发生的 OOM、GPU Xid 导致服务失效、进程被杀或通信不可用
才进入基础设施故障路径。CPU 高、显存占用高或 RTF 下降本身只进入性能报告。

## 10. 降级事务

当前档位发生基础设施故障时，Runner 协调本代 Coordinator 执行一次串行降级事务：

1. 停止发放新 lease，冻结当前 pool generation。
2. fsync 已提交的 `PASSED` 和 `FAILED`，这些结果之后不再运行。
3. 裁决在途点；没有业务终态的点记为 `INFRA_INTERRUPTED`。
4. 根据登记的进程组、Domain claim、session 和 socket 停止当前 pool，包含该 generation 的
   Worker 与 Broker。
5. 验证旧进程退出、controller goal 停止、Domain 静默、session 和 socket 已释放。
6. 把 `UNRUN` 和 `INFRA_INTERRUPTED` 放回共享队列；保留其历史 attempt。
7. 启动下一档，并等待该档全部 Worker `READY`。
8. 对重新领取的每个点执行新的初始状态恢复和 `point_initial_gate`，然后继续批次。

降级清理失败时不得叠加启动下一套 ROS/MoveIt/MuJoCo 栈，批次直接进入 `INFRA_FAILED`。W1 运行
中再发生基础设施故障时也进入 `INFRA_FAILED`。每个点在每个 fallback level 最多产生一次基础
设施 attempt，且总数不超过 `max_infra_attempts_per_point`。

如果全部点位已经提交终态，只执行最终清理，不再为了维持 Worker 数而启动下一档。最终清理
失败仍使批次成为 `INFRA_FAILED`，点位结果则原样保留。

## 11. 持久化与崩溃边界

Runner 的顶层追加式 JSONL journal 记录跨档位权威事件；每代 Coordinator journal 保留本代
lease、attempt ACK 和 sealed result。顶层 journal 至少记录：

- batch manifest 和 pool generation；
- Worker READY、lease 创建和 attempt 开始 ACK；
- sealed 结果的身份、哈希与 `RESULT_COMMITTED`；
- 基础设施故障、在途点裁决和 fallback transition；
- cleanup receipt 和最终 batch summary。

点位终态和降级事件在复用内存状态前先 fsync。Worker 只写自己的 attempt 目录，不能直接修改
汇总状态。Web 页面或其他 UI 只读取投影，不能把失败或未完成结果升级为成功。

轻量版本不实现 Runner 崩溃后的自动续跑。正常入口由一层轻量监督 shell 持有 Runner 子进程；
Runner 发生 Python 异常、收到 SIGINT/SIGTERM 或被 SIGKILL 后，监督层调用精确 cleanup 入口，只
根据 journal 与 owned-process manifest 停止已登记进程，并把批次记为 `INFRA_FAILED`。监督 shell
自身被 SIGKILL 不承诺自动恢复；既有 runtime root 和持久 `ACTIVE` Domain claim record 会让新
批次失败关闭，操作者
必须先显式运行相同的精确 cleanup。重新运行必须使用新 batch ID，不能静默把两个批次拼成一轮
性能数据。

## 12. 清理与隔离

启动器必须登记每个 pool generation 拥有的 PGID、进程 start ticks、Domain claim、仿真 session、
socket、容器和证据目录。停止时只处理这些登记对象，禁止使用宽泛的 `pkill -f`、模糊容器名或
扫描后批量终止其他任务。

durable evidence root 可以使用长描述名，但自适应 batch ID 最长为 5 个 ASCII ID 字符，运行时
目录采用短名，例如 `<evidence-root>/r/mr01/p/g01w08`，并在创建进程前逐个验证最终 Unix socket
路径不超过 107 bytes。
长标题、报告和截图放在运行时目录之外的 ledger/report 路径中。

自适应 Domain claim 除 flock 外还保存 `ACTIVE|RELEASED` 状态、batch 和 generation identity。
Runner 被杀导致 flock 自动关闭时，`ACTIVE` record 仍阻止其他自适应批次复用 Domain；只有精确
cleanup 完成进程、controller、session 和 socket 回读后，才能持锁把 record 改为 `RELEASED` 并
fsync。v1 继续使用原 claim 语义，不受该持久标记扩展影响。

清理完成至少要读回：

- 已登记进程和后代均退出；
- controller 没有本批次遗留 goal；
- Domain claim 已释放，短窗口内没有旧 generation 节点；
- MuJoCo session、IPC socket 和 Broker generation 不再响应；
- 不存在本批次留下的物理或 Planning Scene attachment。

清理只删除运行时可重建的 socket 和空临时目录。日志、截图、attempt evidence、scratch 和账本
均按证据规则保留；未经用户明确授权不得删除。

## 13. 报告与性能口径

batch summary 至少包含：

- 首选 Worker 数、最终 Worker 数和实际使用过的档位；
- 每次 fallback 的时间、原因、故障 generation 和当时剩余点数；
- 每个 Worker 完成、失败和中断的点数；
- 每个点的最终结果、业务失败原因、基础设施 attempt 次数和证据路径；
- YOLO 与 Grounded-SAM 的调用和最终选用情况；
- 总墙钟时间、各档位耗时和清理结果；
- 观察到的 CPU、内存、显存和 RTF 指标摘要。

W1/W2/W4/W6/W8 性能比较必须使用相同 commit、模型、配置、点位清单和初始状态契约。只有从头
到尾保持目标档位、没有发生 fallback 的批次，才能计为该档位的性能样本。W8 降到 W6 后完成，
说明自适应批次可用，但它不是 W8 性能数据。加速比统一相对有效 W1 批次计算。

## 14. 自动化测试

实现至少覆盖：

1. 自适应参数解析、严格递减 fallback 列表，以及旧参数的兼容边界。
2. `initial_points_per_worker` 只影响初始亲和，N×K 小于点数时仍能靠动态抢任务完成。
3. W8 全部 READY 后直接开放真实队列，不运行 canary。
4. W8 启动失败后清理并用 W6 完成剩余点。
5. W8 运行中基础设施故障后保留终态结果，W6 只接管 `UNRUN` 和
   `INFRA_INTERRUPTED`。
6. 单点业务失败提交 `FAILED`，不会触发 fallback；原 Worker 恢复后可以继续取点。
7. `W8 → W6 → W4 → W2 → W1` 连续降级；W1 故障得到 `INFRA_FAILED`。
8. 在途 attempt 已开始但结果不确定时，历史记录不会被后续点位结果覆盖。
9. 精确清理只停止本批次登记的 PGID、Domain、session 和 Broker，不影响旁路哨兵进程。
10. journal 重放能还原点位终态和 fallback 历史；不能凭 UI 投影修改结果。

## 15. ai-station 现场验收

现场工作使用一个已登记的 durable evidence root，并在实验账本中先冻结 commit、install overlay、
运行入口、点位清单、模型哈希、ROS Domain 和成功判据。ai-station 上创建 fsync-heavy fixture 的
pytest 或 benchmark 必须把 `TMPDIR`、`TMP` 和 `TEMP` 指向该 evidence root 下新建的 NVMe scratch，
并用实际测试 Python 回读 `tempfile.gettempdir()`。

现场验收分两类：

### 15.1 故障注入

- W8 启动时令一个 Worker 无法 READY，观察 W6 接管。
- 运行中终止一个登记的 Worker，确认终态点不重跑、在途点重新初始化后再执行。
- 放置一个非本批次哨兵进程和独立 ROS Domain，确认降级清理不影响它们。

业务失败不降级和完整 `W8 → W6 → W4 → W2 → W1` 收敛使用确定性的自动化 fake-port 测试，
不为了现场验收增加生产路径中的测试故障开关。现场注入只有上面两个基础设施实验；如果信号发出
前目标 attempt 已自然完成，则该轮无效，必须换新 run ID 重做。

### 15.2 20 点回归与性能

- 首先尝试 W8；如果基础设施无法稳定运行，允许自动缩到 W6 或更低档继续。
- 每个点都要有新的初始状态读回、感知、MoveIt、controller、仿真物理和结果证据。
- 20 个点全部为 `PASSED` 且最终清理通过时，批次为 `COMPLETED`。
- 有业务失败时批次为 `COMPLETED_WITH_FAILURES`，失败点不得由同批自动重试成功覆盖。
- 分别运行 W1/W2/W4/W6/W8 性能样本；发生 fallback 的样本只用于验证恢复，不进入原档位
  加速比。

## 16. 实施边界

后续实施应优先复用现有 `ParallelBatchCoordinator` 作为单代执行器，并新增轻量
`AdaptiveBatchRunner` 管理跨代状态；同时复用 Worker 生命周期、Domain claim、
PerceptionBroker 和动态队列代码。已经为旧 W8 设计写入的 Authority、签名、画像、cgroup 硬门、
五阶段 qualification 和 canary 代码应删除、旁路或停止接线，不能留在默认自适应路径中制造
隐式失败条件。

实施计划必须先核对 ai-station 当前分支和未提交文件。旧 worktree 中已经完成的提交和 RED
证据要保留，不得 reset、clean 或改写历史；只在新的轻量实现任务中做可审查的最小改动。

本文落盘只表示轻量方案的设计完成。只有自动化测试通过，并在 ai-station 上完成故障注入、
20 点回归、性能采样和精确清理回读后，才能声明自适应 Worker 池已经实现。W8 未通过不阻塞
整批完成；报告必须如实写出最终使用的档位。
