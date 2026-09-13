# SO-101 MoveIt 专家 W8 并行准入设计

日期：2026-09-13

状态：设计已确认，等待实施与 ai-station 现场验收。

关联文档：

- `docs/superpowers/specs/2026-09-11-so101-parallel-multipoint-validation-design.md`
- `docs/superpowers/plans/2026-09-12-so101-parallel-multipoint-validation-implementation.md`
- `docs/experiments/so101-parallel-multipoint-validation-experiment-ledger.md`

本文扩展已经实现的 v1 多点并行验证。v1 仍只允许 1–3 个 Worker；v2 在当前 ai-station
硬件上增加 8 个完整 Worker 的安全准入路径。本文只覆盖 MuJoCo MoveIt 专家模式，不授权
实体机械臂并发运行，也不改变 YOLO-Seg 优先、Grounded-SAM 受限回退和 20 点首次有效执行
判定。

## 1. 已知基线

2026-09-13 的 ai-station 基线为 24 个逻辑 CPU、31 GiB 内存和 16,303 MiB RTX 5080
显存。已封存的单次完整 20 点结果如下：

| Worker | 结果 | 墙钟时间 | 平均 CPU | 说明 |
| --- | --- | ---: | ---: | --- |
| W1 | 20/20 | 1746.86 s | 127% | `qualification_passed=true` |
| W2 | 20/20 | 895.80 s | 242% | 相对 W1 加速 1.9501 倍 |
| W4 | 未执行 | 0.20 s | 不适用 | v1 以 `MAX_WORKER_COUNT` 拒绝 |
| W8 | 未执行 | 0.23 s | 不适用 | v1 以 `MAX_WORKER_COUNT` 拒绝 |

证据根为：

```text
/data/work/so101-evidence/parallel-worker-scaling/20260913-w1-w2-w4-w8-v1
```

W2 的平均 CPU 负载按比例扩到 W8 约为 9.7 个逻辑核，低于主机的 24 核。现有
`/usr/bin/time` 最大 RSS 只覆盖父进程，不能证明八套 Worker 的完整进程树内存峰值；现有
采样也没有覆盖 W2 运行全过程。因此，v2 不能靠降低 v1 的线性阈值直接放行 W8，必须补齐
进程树、GPU、Broker 和仿真实时率证据。

## 2. 目标与非目标

### 2.1 目标

- 在当前 ai-station 上请求、分配并启动八个完整 Worker。
- 八个 Worker 都拥有独立 ROS graph、MuJoCo、MoveIt/controller、日志、临时目录和 IPC
  namespace，并允许同时进入 `EXECUTING`。
- qualification 在同一批次中按 `1 → 2 → 4 → 6 → 8` 逐级追加 Worker。
- 八个 ROS Domain 在启动第一个 Worker 前一次性原子保留。
- 用 cgroup v2 对完整后代进程计量和限额，给主机与控制面保留硬余量。
- 用独立 Authority 审核封存指标。Coordinator 不能自行声明 W8 已准入。
- v1 保持原有冻结值和行为；v2 必须显式选择，不能成为旧命令的隐式默认值。
- 资源不足、Domain 冲突、Worker 丢失或证据不完整时 fail closed，不静默降级为 W7、W6
  或更少 Worker。

### 2.2 非目标

- 不在本轮实现 Gazebo 或实体机械臂的八 Worker 并发。
- 不把八个逻辑 slot 配成更低的活动并发上限。
- 不通过降低碰撞、抓取、放置、感知或物理验收阈值换取准入。
- 不要求 GPU 同时执行八个模型 kernel；PerceptionBroker 仍是单一共享 GPU 权威。
- 不保证 W8 线性加速。吞吐量由正式现场数据决定。
- 不按时间自动废弃已接受画像；画像只因身份漂移或已定义的运行故障失效。

## 3. 核心决策

| 边界 | 决策 |
| --- | --- |
| 版本 | 新增 v2；v1 不原地扩容 |
| W8 语义 | `requested_worker_count == allocated_worker_count == 8` |
| 活动并发 | 八个 Worker 都可同时 `EXECUTING` |
| qualification 扩容 | 同一批次累积启动 `1, 2, 4, 6, 8` |
| 阶段负载 | 每一级执行三轮同步 canary |
| 正式队列 | W8 canary 获得 provisional admission 后才开放 |
| Domain | 181–188 一次性全量保留，固定映射到 slot 1–8 |
| CPU | 为控制面保留 4 个逻辑 CPU，八 Worker 共享其余 20 个 |
| RAM | 批次最大 24 GiB，主机保留 6 GiB，批次禁用 swap |
| GPU | 单 Broker，共享 GPU；保留至少 2 GiB 显存 |
| 画像 | 绑定主机和运行 provenance；没有固定时间有效期 |
| Worker 丢失 | 暂停新 lease，恢复到八个 slot 后才继续 |
| 失败降级 | 禁止；无法恢复到 W8 时批次终止 |

## 4. v1/v2 冻结契约

### 4.1 版本边界

`parallel_batch_v1.yaml` 和现有 v1 Python 契约保持不变。v2 使用新文件：

```text
src/so101_demo_py/config/mujoco/parallel_batch_v2.yaml
```

CLI 根据 `schema_version` 选择严格解析器。未知字段、缺失字段、可强制转换类型和非有限数值
全部拒绝。旧命令没有显式 `--config ...parallel_batch_v2.yaml` 时仍走 v1。

v2 配置至少冻结：

```yaml
schema_version: 2
backend: mujoco
max_worker_count: 8
max_points_per_worker_upper_bound: 20
ros_domain_ids: [181, 182, 183, 184, 185, 186, 187, 188]
rmw_implementation: rmw_fastrtps_cpp
ros_discovery_scope: localhost
domain_allocation_policy: reserve_all_before_start
qualification_worker_stages: [1, 2, 4, 6, 8]
qualification_canary_rounds_per_stage: 3
exact_worker_count_required: true
resource_profile_required_from_worker_count: 4
w8_admission_profile_id: ai-station-w8-v1
broker_queue_capacity_per_model: 8
broker_inflight_per_worker_per_model: 1
requested_device: cuda
allow_cpu_fallback: false
host_min_logical_cpu_count: 24
host_reserved_logical_cpu_count: 4
host_reserved_ram_gib: 6
batch_memory_max_gib: 24
batch_memory_swap_max_gib: 0
hard_min_host_mem_available_gib: 4
host_reserved_gpu_gib: 2
required_measured_headroom_ratio: 0.20
resource_sample_interval_s: 0.5
stage_idle_stability_window_s: 10.0
```

已有模型、帧新鲜度、RGB-D/TF skew、lease、heartbeat、attempt ACK、result ACK 和各状态硬
期限继续使用 v1 的冻结值，除非 v2 配置明确给出替代值。任何替代值都要进入 v2 的完整
`runtime_config_sha256`；不能从环境变量或命令行悄悄覆盖。

### 4.2 三层冻结

1. 协议契约固定 lease、fencing、状态机、结果裁决、YOLO-first、恢复门和不降级语义。
2. 运行配置固定资源池、阈值、Broker 容量、模型身份和超时算法。
3. `ai-station-w8-v1` 画像固定已经验收的主机、软件、阶段指标和安全余量。

每个 batch manifest 都保存三层身份。正常 W8 必须同时匹配；qualification 可以在没有已接受
画像时创建候选，但只能走本文定义的逐级路径。

### 4.3 请求不变量

- v2 接受 `1 <= worker_count <= 8`，拒绝 W9。
- W4–W8 必须提供匹配的资源画像，或显式使用 `qualification` 模式。
- `requested_worker_count`、`allocated_worker_count`、`started_worker_count` 和最终
  `ready_worker_count` 分开记录。
- 正式队列开放时，四者都必须为 8。
- 启动器不能修改用户请求数，也不能用 `active_worker_limit` 隐藏并发降级。

## 5. qualification 状态机

```text
PREFLIGHT
  → RESERVE_8_DOMAINS
  → CREATE_CGROUPS
  → START_1  → QUALIFY_1
  → START_2  → QUALIFY_2
  → START_4  → QUALIFY_4
  → START_6  → QUALIFY_6
  → START_8  → QUALIFY_8
  → PROVISIONAL_ADMISSION
  → PRODUCTION_QUEUE_OPEN
  → PRODUCTION_COMPLETE
  → CLEANUP
  → PROFILE_ACCEPTED | PROFILE_REJECTED
```

同一 qualification 批次在 preflight 时声明最终 W8，并预留八套资源。每次扩容只启动新增
slot；已经通过的 Worker 不退出，不更换 `batch_id` 或 `coordinator_epoch`。

每个 `QUALIFY_N` 执行三轮同步 canary：

1. N 个 Worker 分别在自己的隔离世界中 reset 到同一个已知稳定 canary 点。
2. Coordinator 发出带统一 `canary_round_id` 的 barrier release。
3. N 个 Worker 必须有可计算的 `EXECUTING` 重叠窗口。
4. 每个 Worker 完成完整感知、pick-place、物理验收、恢复和 `worker_ready_gate`。
5. Authority 审核该级资源与隔离证据后，Coordinator 才能进入下一阶段。

canary attempt 使用 `qualification/canaries/` 命名空间和独立事件类型。它不进入正式点位
的 `coverage_complete`、首次有效成功率或 `qualification_passed` 分母。canary 行为失败仍会
令本级 qualification 失败，不能为了继续扩容而忽略。

W8 三轮通过后，Authority 签发只对当前 batch 和 epoch 有效的 provisional admission。
Coordinator 收到并复核后，才开放正式 20 点全局队列。八个 Worker 随后按既有动态 lease
抢点；`max_points_per_worker=3` 时理论容量为 24。

## 6. ROS Domain 池

### 6.1 原子保留

v2 固定 181–188，并在 `START_1` 前按数值顺序申请全部八个 lock。只有八个 lock 全部成功，
才写入 `DOMAINS_RESERVED`；任一失败会释放本次刚取得的 lock，并以
`DOMAIN_POOL_INCOMPLETE` 或 `DOMAIN_CLAIM_CONFLICT` 终止。

slot 映射固定：

| Slot | ROS_DOMAIN_ID |
| ---: | ---: |
| 1 | 181 |
| 2 | 182 |
| 3 | 183 |
| 4 | 184 |
| 5 | 185 |
| 6 | 186 |
| 7 | 187 |
| 8 | 188 |

Worker replacement 沿用该 slot 的 Domain，只增加 `worker_generation`。进入
`QUARANTINED` 的 slot 在批次结束前仍保留 Domain，不能让另一个 batch 抢走。

### 6.2 冲突检测

每个 Domain 依次经过：

- 0600、owner-controlled、`O_NOFOLLOW` 的 `flock` claim；
- `/proc` 进程身份和环境扫描；
- 不依赖共享 ROS CLI daemon 的短窗口 DDS graph 探测；
- `RMW_IMPLEMENTATION=rmw_fastrtps_cpp` 与 localhost discovery 配置回读。

同 UID 的候选进程环境不可读、跨 UID 的高召回 ROS 候选无法分类、进程身份在扫描期间变化，
都以 `DOMAIN_PROCESS_UNVERIFIABLE` 拒绝。发现现存 participant、node、service 或 topic 时返回
`DOMAIN_DISCOVERY_NOT_QUIET`。不能只凭 lock 文件时间戳判断 Domain 空闲。

claim receipt 至少记录 `domain_id`、`batch_id`、epoch、PID、进程 start ticks、boot ID、UID、
配置哈希、evidence root 和 claim path。

### 6.3 崩溃与释放

正常结束时先停止 Worker 和后代进程，再验证 DDS quiet window，最后关闭 claim FD。协调器崩溃
会释放自己的 FD，但新批次仍要经过进程扫描和 DDS 探测；旧 Worker 未退出时不能重新使用
Domain。stale claim 文件可以覆盖，活进程和未释放 lock 不能覆盖。

v1 和 v2 共享 181–183，因此两者不能同时运行。后启动的一方必须明确拒绝。这是隔离约束，
不是需要自动绕过的资源不足。

## 7. cgroup v2 与资源计量

### 7.1 层级

```text
so101-parallel-<batch>.slice
├── control.scope        # Coordinator、Authority client、监视器、Broker
└── workers.slice        # 总 CPU/RAM 边界
    ├── worker-01.scope
    ├── ...
    └── worker-08.scope
```

启动前必须确认 cgroup v2 的 `cpu`、`cpuset`、`memory`、`pids` 和必要的 IO 统计可用且已委派。
每个进程必须先进入对应 cgroup，再允许创建 ROS participant、MuJoCo 实例或模型 context。
Broker 容器必须通过容器运行时的 cgroup parent 接口进入 `control.scope`。发现后代进程逃逸时
返回 `PROCESS_ESCAPED_CGROUP`，暂停新动作并受控停止。

### 7.2 CPU

启动器按物理核/SMT 拓扑选择四个逻辑 CPU 给控制面，其余 20 个给 `workers.slice`。选择结果
写入 manifest，不硬编码 Linux CPU 编号。八个 worker scope 使用相同 CPU weight，共享这
20 个 CPU，不设置低于八的并发令牌。

资源监视器固定在控制面 CPU 上，不能与 MoveIt 规划线程争抢到无法发送 heartbeat。阶段验收
读取 cgroup CPU time、throttling 和 PSI；W8 实测峰值必须相对 20 CPU 预算保留 20% 余量。

### 7.3 RAM 与 swap

整个 batch 的 `memory.max` 为 24 GiB，`memory.swap.max` 为 0。主机至少保留 6 GiB 设计预算，
运行中 `MemAvailable` 的硬下限为 4 GiB。每个 Worker 使用独立 scope 记录 `memory.current`、
`memory.peak` 和 `memory.events`，但初版不设置会让负载不均 Worker 提前 OOM 的相同硬上限；
`workers.slice` 与 batch 上限负责总体保护。

任一 `oom`、`oom_kill`、活跃 swap-in/swap-out 或 4 GiB 主机硬下限触发熔断。W8 画像只在
完整进程树峰值相对 24 GiB 上限仍有至少 20% 余量时接受。

### 7.4 GPU、仿真和采样

资源监视器每 0.5 秒采集：

- cgroup CPU、memory、pids 和 pressure；
- 主机 `MemAvailable`、swap IO 和 load；
- NVML 按 PID 与整卡显存、利用率、Xid；
- Broker queue depth、queue wait、inference latency 和 generation；
- 每个 Worker 的 MuJoCo realtime factor、controller deadline miss 和渲染产帧率。

阶段开始前要求 10 秒稳定窗口，采样不能缺段。GPU 至少保留 2 GiB，且 accepted profile 的
峰值仍需满足 20% 余量。`nvidia-smi`/NVML 不可用、PID 归属不完整或指标时间轴无法和阶段事件
对齐时拒绝，不把缺测当成零负载。

## 8. PerceptionBroker 扩容

Broker 仍只有一个 GPU 模型服务。YOLO-Seg 始终优先；Grounded-SAM 只在 v1 已允许的感知
失败边界回退。八个 Worker 可同时各提交一个请求，两个模型队列容量都固定为 8，并继续按
Worker 轮转。

qualification 没有 accepted profile 时，排队 deadline 使用 v2 冻结上限；normal 模式按画像
的 p99 推理时间和当前活动 Worker 数计算 deadline，再受冻结上限约束。算法为：

```text
effective_queue_deadline = min(
  frozen_queue_deadline_ceiling,
  max(v1_queue_deadline_floor, 1.5 * accepted_inference_p99 * (active_workers - 1))
)
```

deadline、计算输入和结果写入请求证据。Broker queue 或 inference timeout 仍是
`INVALID` 基础设施尝试，不触发 Grounded-SAM 回退。Broker generation 改变时旧响应全部
fence；公共依赖不健康时暂停新 lease。

## 9. 独立 AdmissionAuthority 与画像

### 9.1 两级授权

```text
QUALIFY_8
  → seal W8 stage evidence
  → Authority verification
  → PROVISIONAL_W8_ADMISSION
  → formal 20-point queue
  → cleanup
  → final profile verification
  → W8_PROFILE_ACCEPTED
```

provisional record 只对当前 batch 和 epoch 有效。最终 `ai-station-w8-v1` 才能供 normal W8
复用。

Authority 使用固定 evidence registry 和 acceptance root。Coordinator 只传 `batch_id`，不能
传入阈值、任意路径或期望结果。Authority 从 registry 解析 batch root，以安全目录句柄读取
sealed 文件，复核 SHA256、inode、大小和修改时间，再从原始样本重新计算指标。

### 9.2 画像内容

画像绑定：

- CPU 型号/拓扑、逻辑核数、总内存、GPU 型号/UUID/显存；
- Linux 内核、NVIDIA driver、cgroup controller 和容器 runtime；
- ROS 发行版、RMW 名称/版本、Domain 池和 discovery 配置；
- source/install、容器、策略、场景、模型、配置和点位清单哈希；
- 五个阶段的窗口、样本数、缺样数、CPU/RAM/GPU/PSI、实时率、渲染和 Broker 分位数；
- provisional admission、正式点位结果、cleanup 和所有熔断事件。

画像无固定时间有效期。以下变化立即失效：

- 主机硬件、内核、driver、RMW、cgroup 或容器能力改变；
- source/install、容器、模型、策略、场景、v2 配置或点位清单哈希改变；
- clean-host normal W8 出现 OOM、GPU Xid、controller deadline miss、进程逃逸或资源硬门；
- sealed evidence 损坏、指标缺样或 acceptance 身份无法验证。

外部临时负载只拒绝当前运行。若当前主机满足 clean-host 前提却仍低于 accepted profile 的
余量，画像失效并要求重新 qualification。

资源与行为资格分开：

- `resource_profile_accepted=true` 表示 W8 资源和隔离证据有效。
- `qualification_passed=true` 仍要求正式 20 点全部首次有效执行通过并完成 cleanup。

行为失败不能冒充资源失败，20/20 也不能覆盖资源门失败。

## 10. Worker 丢失与熔断

正式队列开放后必须维持八个可用 slot。Worker 崩溃、退出或被隔离时：

1. Coordinator 立即停止发放新 lease。
2. 其他 Worker 可完成已经开始的点，避免主动制造 `INDETERMINATE`。
3. 故障 slot 的旧 generation 完成 fencing 和进程清理。
4. replacement 沿用原 Domain，增加 `worker_generation`，通过完整 ready gate。
5. 重新达到八个 `AVAILABLE` 后才恢复队列。

冻结期限内无法恢复时返回 `W8_CAPACITY_LOST`。已完成点保留原裁决，但整个批次不能声明 W8
资格。不得按七个或更少 Worker 继续派发新点。

软门事件暂停新 lease并等待恢复，例如 Broker queue 接近 deadline、CPU pressure 超过画像
余量或主机内存接近设计保留值。硬门事件执行受控停止，例如 OOM、GPU Xid、controller
deadline miss、cgroup 逃逸或 `MemAvailable < 4 GiB`。正式 attempt 已开始但结果无法证明时
仍按 v1 记为 `INDETERMINATE`，不能改成 `INVALID` 后重跑覆盖。

## 11. 错误码

| 边界 | 错误码 |
| --- | --- |
| 配置 | `CONTRACT_V2_MISMATCH`, `EXACT_WORKER_COUNT_REQUIRED` |
| Domain | `DOMAIN_POOL_INCOMPLETE`, `DOMAIN_CLAIM_CONFLICT`, `DOMAIN_PROCESS_UNVERIFIABLE`, `DOMAIN_DISCOVERY_NOT_QUIET` |
| cgroup | `CGROUP_V2_UNAVAILABLE`, `CGROUP_ENROLLMENT_FAILED`, `PROCESS_ESCAPED_CGROUP` |
| 静态资源 | `HOST_RESOURCE_BASELINE_FAILED` |
| 运行资源 | `MEMORY_HARD_LIMIT`, `GPU_HARD_HEADROOM`, `CPU_PRESSURE_LIMIT` |
| 公共依赖 | `BROKER_BACKPRESSURE_LIMIT`, `SIMULATION_REALTIME_LIMIT`, `CONTROLLER_DEADLINE_MISS` |
| Authority | `PROVISIONAL_ADMISSION_DENIED`, `PROFILE_PROVENANCE_DRIFT` |
| Worker 容量 | `W8_CAPACITY_LOST` |

错误码要同时进入事件账本、batch summary 和 CLI stderr。正式队列开放前失败时不创建正式
point attempt，也不把未执行点放进成功率分母。

## 12. 证据布局与写入权

现场 qualification 使用一个已登记的 durable evidence root：

```text
/data/work/so101-evidence/parallel-w8-admission/<run-id>/
├── registry/
├── authority/
├── coordinator/
├── qualification/
│   ├── stage-01/
│   ├── stage-02/
│   ├── stage-04/
│   ├── stage-06/
│   └── stage-08/
├── production/
├── workers/
├── broker/
├── metrics/
└── scratch/
```

Coordinator 写 batch 事件和正式点位投影；Worker 只写自己的 canary/attempt/recovery 目录；
资源监视器只写原始时间序列；Authority 只写 acceptance 和 profile。所有 sealed 目录继续使用
临时目录、文件与目录 fsync、原子 rename 和只读回读。

ai-station 上 pytest 或 benchmark 的 `TMPDIR`、`TMP`、`TEMP` 必须指向本 evidence root 下从未
存在的 `scratch/<test-run-id>/tmp`，并由实际测试 Python 回读 `tempfile.gettempdir()`。scratch
在完成后只列为删除候选，未经授权不得删除。

## 13. CLI

qualification 示例：

```bash
so101_parallel_batch \
  --points <absolute-point-catalog> \
  --config <absolute-parallel_batch_v2.yaml> \
  --batch-id <unique-batch-id> \
  --worker-count 8 \
  --max-points-per-worker 3 \
  --admission-mode qualification \
  --evidence-root <registered-durable-evidence-root> \
  --run-mode execute
```

normal W8 额外提供 accepted profile；CLI 读取 repo-tracked acceptance registry，不能由调用者
直接传任意 profile SHA：

```bash
so101_parallel_batch \
  --points <absolute-point-catalog> \
  --config <absolute-parallel_batch_v2.yaml> \
  --batch-id <unique-batch-id> \
  --worker-count 8 \
  --max-points-per-worker 3 \
  --admission-mode normal \
  --admission-profile-id ai-station-w8-v1 \
  --evidence-root <registered-durable-evidence-root> \
  --run-mode execute
```

W1–W3 旧命令和 v1 配置不变。

## 14. 测试与现场验收

### 14.1 自动化测试

- v1 全部 frozen-value 和行为测试保持通过。
- v2 接受 W8、拒绝 W9，拒绝配置漂移和任何实际 Worker 数降级。
- 八 Domain 全量原子 claim；部分冲突不留下半套 claim。
- 协调器崩溃且旧 Worker 存活时，新批次不能抢走 Domain。
- 所有 Worker、Broker 和后代进程都属于预期 cgroup；逃逸会触发硬门。
- canary 必须有三轮和 N Worker 的执行重叠，不能混入正式点位统计。
- 阶段不能跳过、倒退或在失败后继续扩容。
- Authority 拒绝自签记录、任意路径、文件替换、缺样、损坏和 provenance 漂移。
- W8 丢失 slot 后暂停发新 lease；恢复到八个后继续，超时则 `W8_CAPACITY_LOST`。
- Broker 对八 Worker 保持有界公平，YOLO-first 和既有失败矩阵不变。

### 14.2 ai-station qualification

同一批次依次完成 W1、W2、W4、W6、W8，每级三轮同步 canary。每级都要求：

- 当前级全部 Worker 有真实 `EXECUTING` 重叠窗口；
- canary pick-place 和 recovery 全部通过；
- 没有 OOM、swap IO、GPU Xid、controller deadline miss 或 cgroup 逃逸；
- Broker generation 稳定，无 queue/inference timeout；
- MuJoCo、渲染和控制器指标满足冻结硬门；
- CPU、RAM 和 GPU 峰值相对各自预算保留至少 20% 余量；
- Authority 对 sealed stage evidence 返回 accepted。

W8 provisional admission 后运行正式 20 点，`worker_count=8`、
`max_points_per_worker=3`，保留动态抢点。完成判据：

- 20 个点全部首次有效执行为 `PASSED`；
- `coverage_complete=true`、`batch_cleanup_complete=true`、
  `qualification_passed=true`；
- 八 Worker 并发重叠证据成立；
- `resource_profile_accepted=true`；
- 八个 Domain、所有 cgroup 和本轮拥有的进程都完成释放回读；
- 终态渲染图与各点数值证据可映射到唯一 Worker、attempt 和时间戳。

通过 qualification 后还要用 accepted profile 启动一次 normal W8。normal 运行按
`1 → 2 → 4 → 6 → 8` 做快速空载稳定检查，不重复 canary；八个 Worker 全部 ready 后才开放
队列。该次运行至少完成一组小规模点位，证明画像复用、provenance 复核和释放路径有效。

## 15. 未采用方案

| 方案 | 不采用原因 |
| --- | --- |
| 直接把 v1 常量从 3 改成 8 | 破坏已审查契约，且没有 W8 资源证明 |
| 八个 slot、四个活动 Worker | 不满足八 Worker 同时执行的用户要求 |
| 资源不足时自动退回 W6/W4 | 会把不同并发结果混成 W8，证据失真 |
| 八个独立 GPU Broker | RTX 5080 16 GiB 无法在未证明的情况下承诺模型副本资源 |
| 合并多个 Worker 的 ROS/MoveIt/MuJoCo | 削弱故障与 Domain 隔离，改动范围远大于当前目标 |
| 画像固定 30 天过期 | 用户不需要按时间重做；身份漂移和运行硬故障已提供明确失效边界 |

## 16. 完成边界

本文落盘只表示设计完成。只有实现通过自动化测试、ai-station 同批次五级 qualification、
正式 W8 20 点、normal profile 复用和完整清理回读后，才能声明 W8 已安全准入。任何缺失层
必须明确报告为未验证，不能由文档、静态测试或 W2 的历史结果替代。
