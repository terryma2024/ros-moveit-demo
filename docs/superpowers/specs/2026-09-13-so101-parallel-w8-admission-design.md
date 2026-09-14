# SO-101 MoveIt 专家 W8 并行准入设计

日期：2026-09-13

状态：已废弃。2026-09-14 起由
`docs/superpowers/specs/2026-09-14-so101-adaptive-worker-pool-design.md` 取代。本文保留为历史设计记录，
不得继续据此实现 AdmissionAuthority、资源画像、Ed25519、cgroup 硬准入、分级 canary 或 W8
原数恢复语义。

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

实现边界以这些上游文档为准：ROS 2 的 Linux Domain/端口选择规则、Linux cgroup v2 的
no-internal-process 约束、Docker systemd driver 的 cgroup parent 规则，以及 Fast DDS 的 SHM
传输行为。

- `https://docs.ros.org/en/lyrical/Concepts/Intermediate/About-Domain-ID.html`
- `https://kernel.org/doc/html/v5.16/admin-guide/cgroup-v2.html`
- `https://docs.docker.com/reference/cli/dockerd/`
- `https://fast-dds.docs.eprosima.com/en/2.x/fastdds/transport/shared_memory/shared_memory.html`

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
| 请求语义 | 对任意 v2 请求 N，`requested == allocated == started == ready == N`；W8 时 N 必须为 8 |
| 活动并发 | 八个 Worker 都可同时 `EXECUTING` |
| qualification 扩容 | 同一批次累积启动 `1, 2, 4, 6, 8` |
| 阶段负载 | 每一级执行三轮同步 canary |
| 正式队列 | W8 canary 获得 provisional admission 后才开放 |
| Domain | 215–222 一次性全量保留，固定映射到 slot 1–8 |
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
ros_domain_ids: [215, 216, 217, 218, 219, 220, 221, 222]
rmw_implementation: rmw_fastrtps_cpp
ros_discovery_scope: localhost
fastdds_transport: udp_v4_loopback_only
fastdds_data_sharing: false
max_dds_participants_per_worker: 32
max_unix_socket_path_bytes: 107
domain_allocation_policy: reserve_final_request_before_start
qualification_worker_stages: [1, 2, 4, 6, 8]
qualification_canary_rounds_per_stage: 3
exact_worker_count_required: true
resource_profile_required_from_worker_count: 4
w8_admission_profile_id: ai-station-w8-v1
broker_queue_capacity_per_model: 8
broker_inflight_per_worker_per_model: 1
v2_yolo_ticket_queue_timeout_s: 10.0
v2_grounded_sam_ticket_queue_timeout_s: 30.0
broker_capture_submit_timeout_s: 0.5
pose_admission_max_frame_age_s: 5.0
yolo_qualified_inference_p99_ceiling_s: 2.0
grounded_sam_qualified_inference_p99_ceiling_s: 4.0
freshness_commit_reserve_s: 0.25
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
resource_max_sample_gap_s: 1.0
resource_soft_stop_recovery_window_s: 10.0
resource_soft_stop_hard_timeout_s: 30.0
mujoco_realtime_factor_p05_floor: 0.50
render_fps_p05_floor: 5.0
controller_state_expected_hz: 100.0
controller_state_max_gap_s: 0.05
controller_deadline_miss_limit: 0
runtime_metrics_smoke_duration_s: 31.0
metrics_reset_transition_timeout_s: 20.0
metrics_recovery_transition_timeout_s: 120.0
metrics_rebaseline_timeout_s: 5.0
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

- v2 normal 接受 `1 <= worker_count <= 8`，拒绝 W9；qualification 只接受最终目标 W8。
- W4–W8 normal 必须提供已接受的 W8 资源画像：N=4 使用 stage-4 envelope，N=5/6 使用
  stage-6 envelope，N=7/8 使用 stage-8 envelope；W1–W3 可保持 v1 的现有资源门。
- `requested_worker_count`、`allocated_worker_count`、`started_worker_count` 和最终
  `ready_worker_count` 分开记录。
- normal 正式队列开放时，四者必须都等于请求 N；qualification 正式队列开放时四者必须都为 8。
- 启动器不能修改用户请求数，也不能用 `active_worker_limit` 隐藏并发降级。

normal N 的累计启动序列为 `startup_stages(N) = [s ∈ (1,2,4,6) where s < N] + [N]`，去重并
保持升序。例如 N=3 是 `1,2,3`，N=5 是 `1,2,4,5`，N=7 是 `1,2,4,6,7`，N=8 才是
`1,2,4,6,8`。每一级只做 10 秒空载稳定检查，不运行 qualification canary。

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

v2 固定 215–222。qualification 的 final request 是 W8，因此在 `START_1` 前按数值顺序申请
全部八个 lock；normal N 在启动前原子申请映射表前 N 个，不能边运行边追加。215–222 位于 Linux 推荐的
非临时端口 Domain 范围，避开 v1 的 181–183；每个 Worker 的 DDS participant 数硬上限为 32。
只有本次最终请求的全部 lock 成功，
才写入 `DOMAINS_RESERVED`；任一失败会释放本次刚取得的 lock，并以
`DOMAIN_POOL_INCOMPLETE` 或 `DOMAIN_CLAIM_CONFLICT` 终止。

slot 映射固定：

| Slot | ROS_DOMAIN_ID |
| ---: | ---: |
| 1 | 215 |
| 2 | 216 |
| 3 | 217 |
| 4 | 218 |
| 5 | 219 |
| 6 | 220 |
| 7 | 221 |
| 8 | 222 |

Worker replacement 沿用该 slot 的 Domain，只增加 `worker_generation`。进入
`QUARANTINED` 的 slot 在批次结束前仍保留 Domain，不能让另一个 batch 抢走。

### 6.2 冲突检测

每个 Domain 依次经过：

- 与 v1 共用 `/run/user/<uid>/so101-parallel-domain-claims/domain-<id>.lock`，使用 0700
  owner-controlled 目录、0600 regular file、`O_NOFOLLOW` 和 `flock` claim；
- `/proc` 进程身份和环境扫描；
- 不依赖共享 ROS CLI daemon 的短窗口 DDS graph 探测；
- `RMW_IMPLEMENTATION=rmw_fastrtps_cpp` 与 localhost discovery 配置回读；
- 哈希固定的 Fast DDS XML 只启用 UDPv4 loopback，关闭 SHM 与 Data Sharing，并限制每个
  Worker 最多 32 个 participant。

同 UID 的候选进程环境不可读、跨 UID 的高召回 ROS 候选无法分类、进程身份在扫描期间变化，
都以 `DOMAIN_PROCESS_UNVERIFIABLE` 拒绝。发现现存 participant、node、service 或 topic 时返回
`DOMAIN_DISCOVERY_NOT_QUIET`。不能只凭 lock 文件时间戳判断 Domain 空闲。

claim receipt 至少记录 `domain_id`、`batch_id`、epoch、PID、进程 start ticks、boot ID、UID、
配置哈希、evidence root 和 claim path。

### 6.3 崩溃与释放

正常结束时先停止 Worker 和后代进程，再验证 DDS quiet window，最后关闭 claim FD。协调器崩溃
会释放自己的 FD，但新批次仍要经过进程扫描和 DDS 探测；旧 Worker 未退出时不能重新使用
Domain。stale claim 文件可以覆盖，活进程和未释放 lock 不能覆盖。

v1 和 v2 虽不再共享 Domain，仍必须共用同一 claim root 和 lock inode 规则。现场 smoke 要用
真实 participant 证明不同 Domain 不串图、215–222 端口无冲突、SHM/Data Sharing 已关闭；任何
XML 未生效、participant 超限或跨 Domain 可见都拒绝准入。

## 7. cgroup v2 与资源计量

### 7.1 层级

```text
so101-w8-<batch>.slice                         # 空的 systemd slice，MemoryMax=24G
├── so101-w8-<batch>-control.slice             # 空 slice，MemoryLow=1G
│   ├── so101-w8-<batch>-coordinator.scope     # leaf
│   └── so101-w8-<batch>-monitor.scope         # leaf
├── so101-w8-<batch>-broker.slice              # 空 slice，Docker cgroup parent
└── so101-w8-<batch>-workers.slice             # 空 slice，20 CPU 边界
    ├── so101-w8-<batch>-worker01.scope        # leaf
    ├── ...
    └── so101-w8-<batch>-worker08.scope        # leaf
```

当前 ai-station 的 Docker 使用 systemd cgroup driver，且用户 manager 没有 Delegate。实现因此
只能使用 system manager 创建空 slice，再把进程放入独立 leaf scope；不得让有进程的 scope
承担 Docker `--cgroup-parent`，也不得在含进程的 cgroup 上开启子 controller。启动前用一次
无模型、无 ROS 的 capability smoke 证明 system manager 授权、unit 命名、controller、Docker
parent 和清理均有效。权限不足时返回 `CGROUP_DELEGATION_UNAVAILABLE`，不能退回无隔离模式。
每个进程必须先进入对应 leaf scope，再允许创建 ROS participant、MuJoCo 实例或模型 context。
Broker 容器以空的 broker slice 作为 cgroup parent，容器 init PID 和所有后代必须回读属于该
slice。发现后代逃逸时返回 `PROCESS_ESCAPED_CGROUP`，暂停新动作并受控停止。

### 7.2 CPU

启动器按物理核/SMT 拓扑选择四个逻辑 CPU 给控制面，其余 20 个给 `workers.slice`。选择结果
写入 manifest，不硬编码 Linux CPU 编号。八个 worker scope 使用相同 CPU weight，共享这
20 个 CPU，不设置低于八的并发令牌。

资源监视器固定在独立 monitor scope 和控制面 CPU 上，以 `MemoryLow=1G` 获得保护，不能与
MoveIt 规划线程或 Broker 同处可能被整体 OOM 的 leaf。阶段验收
读取 cgroup CPU time、throttling 和 PSI；W8 实测峰值必须相对 20 CPU 预算保留 20% 余量。

### 7.3 RAM 与 swap

整个 batch 的 `memory.max` 为 24 GiB，`memory.swap.max` 为 0。主机至少保留 6 GiB 设计预算，
运行中 `MemAvailable` 的硬下限为 4 GiB。每个 Worker 使用独立 scope 记录 `memory.current`、
`memory.peak` 和 `memory.events`，但初版不设置会让负载不均 Worker 提前 OOM 的相同硬上限；
`workers.slice` 与 batch 上限负责总体保护。

任一 `oom`、`oom_kill`、活跃 swap-in/swap-out 或 4 GiB 主机硬下限触发熔断。W8 画像只在
完整进程树峰值相对 24 GiB 上限仍有至少 20% 余量时接受。

### 7.4 冻结指标、采样与动作

资源监视器每 0.5 秒采集：

- cgroup CPU、memory、pids 和 pressure；
- 主机 `MemAvailable`、swap IO 和 load；
- NVML 按 PID 与整卡显存、利用率、Xid；
- Broker queue depth、queue wait、inference latency 和 generation；
- 每个 Worker 的 MuJoCo realtime factor、controller deadline miss 和渲染产帧率。

阶段开始前要求 10 秒稳定窗口。下表是 qualification 的硬契约，不由调用者或画像放宽：

| 指标 | 来源与窗口 | 接受阈值 | 动作 |
| --- | --- | --- | --- |
| 样本完整性 | 0.5 s monotonic 序列 | 缺样 0，最大间隔 `<=1.0 s` | 超出立即 HARD_STOP |
| Worker CPU | workers slice，任意 10 s rolling | p99 `<=16.0 CPU`，throttled/usage `<=1%` | p99 `>14 CPU` 或 throttled `>0.5%` 持续 10 s 时 SOFT_STOP；接受阈值超限 HARD_STOP |
| CPU PSI | workers slice `cpu.pressure`，任意 10 s | `some avg10 <=10%`，`full avg10 <=1%` | some `>8%` 或 full `>0.5%` 时 SOFT_STOP；接受阈值超限 HARD_STOP |
| Batch RAM | batch slice，全阶段 | peak `<=19.2 GiB`，`oom=oom_kill=0` | 18 GiB SOFT_STOP；超限 HARD_STOP |
| Host RAM/swap | `/proc/meminfo`、`/proc/vmstat` | `MemAvailable>=4 GiB`，swap-in/out 增量 0 | `<6 GiB` SOFT_STOP；硬门 HARD_STOP |
| GPU | NVML 整卡与 owned PID，全阶段 | free `>=max(2 GiB, 20% total)`，Xid 0 | free `<max(3 GiB, 25% total)` 时 SOFT_STOP；接受阈值或 Xid 超限 HARD_STOP |
| MuJoCo | Worker 每 0.5 s 发布 simulated/wall delta | 每 Worker p05 realtime factor `>=0.50` | 连续 10 s `<0.60` SOFT_STOP；阶段失败 HARD_STOP |
| Render | camera producer 的 fresh-frame 计数 | 每 Worker p05 `>=5.0 FPS`，无 `>1.0 s` 断帧 | 断帧先 SOFT_STOP；超过 1 s HARD_STOP |
| Controller | controller manager deadline counter | miss 增量 `==0` | 任一 miss HARD_STOP |
| Broker | Broker 原始事件，全阶段 | queue/inference timeout 0，p99 见 §8 | 接近新鲜度预算 SOFT_STOP；超限 HARD_STOP |

每个 Worker 的 `ParallelRuntimeMetricsProbe` 使用该 Worker 自己的 ROS Domain：

- 订阅 `so101_mujoco_support/msg/PhysicsStepEvidenceChunk` 的
  `/so101/simulation/physics_step_chunks`，用连续 chunk 的 simulation-time delta / 本地 monotonic
  receive delta 计算 realtime factor；`evidence_loss=true` 或未经授权的 reset/session 不连续即缺测。
- 订阅 `sensor_msgs/msg/Image` 的 `/task_camera/color`，用 source stamp 和本地 monotonic receive
  序列计算 0.5 秒窗口 FPS 与最大断帧。
- 订阅 `sensor_msgs/msg/JointState` 的 `/joint_states`。冻结的 broadcaster rate 为 100 Hz；非
  paused、非 reset 窗口内 source stamp 或 receive monotonic gap `>0.05 s` 就增加
  `controller_state_deadline_miss_count`。这项明确衡量 controller state 发布链，不宣称是内核
  scheduler 的控制环 deadline。

Probe 每 0.5 秒通过已有 worker control socket 发送带 batch/epoch/worker/generation/session/reset
身份的 `WorkerRuntimeMetricsSample`。`parallel_worker_runtime.py` 负责轮询和发送，
`parallel_ipc.py` 固定 wire schema，ResourceMonitor 只接收身份匹配且 sequence 连续的样本。
这些是生产接口，不是只在测试中注入的 fake。

正常 point/canary reset 通过有界 measurement epoch 转换处理。Worker 在调用 reset 前，先用已
fsync 的 point/canary identity、当前 lease 和 20 秒固定 deadline 发送
`MeasurementResetBegin`；Monitor 只接受当前 generation/session 的 begin。转换期间 cgroup、
host RAM/swap、GPU/Xid、进程逃逸和 watchdog 继续按 0.5 秒监控，只有 physics chunk、color 和
joint-state 的断流记为 `EXPECTED_RESET_GAP`，不计普通 missing。reset 成功后，现有
`ResetReceipt` 必须证明同一 simulation session、`reset_epoch=previous+1`；Worker 发送
`MeasurementResetCommit`，而 Worker metrics wire sequence 本身不能重置。Monitor 在 5 秒内
重新收到三类 topic，并建立新 source/receive baseline 后才结束转换；此前不得进入 canary
barrier、`EXECUTING` 或捕帧。begin/commit 超时、reset receipt 不匹配、topic 未恢复、session
意外改变或同一 epoch 重放都立即 HARD_STOP。新 Worker generation 的 session 变化只在完整
ready gate 中建立新 measurement epoch，不能借 reset 豁免。

正常 point/canary 结束仍保留 v1 的 FULL_RESTART recovery，不改成轻量 reset。Coordinator 在
现有 recovery registration 与 120 秒 immutable recovery deadline fsync 后，签发
`MeasurementRecoveryBegin(old_generation, old_session, target_generation=old+1,
deadline_monotonic_s)`。外层 Worker 进程在 shutdown/start owned ROS stack 期间继续发送带
transition ID 的 slot heartbeat；该 slot 暂不计 `slot_healthy`，所以停止发新 lease，但其他已
开始 attempt 可完成。cgroup/host/GPU/watchdog 监控始终不中断，physics/color/joint-state 停流
单独记为 `EXPECTED_RECOVERY_GAP`。

新 stack 必须在同一 recovery deadline 内完成 generation/session fencing、ROS graph、paused
initial gate、resume 回读和完整 `worker_ready_gate`，随后发送
`MeasurementRecoveryCommit(new_generation, new_session, reset_epoch, transition_id)`。Monitor 在
5 秒内从三类 production topic 建立新 baseline并返回 `MeasurementBaselineAck` 后，Coordinator
才把 slot 重新计为 healthy/available 并恢复派发。deadline 到期、外层 slot heartbeat 丢失、
旧 stack 残留、新 identity 不匹配、topic 未恢复或基线 ACK 缺失均按既有 recovery failure
fence，并触发容量丢失/受控清理；不能把 recovery gap 当普通缺样，也不能无限延长豁免。

reset 的生产顺序固定为：journal/reset authorization → `MeasurementResetBegin` → reset 与 paused
initial gate → `resume_physics()` 回读 unpaused → `MeasurementResetCommit` → 5 秒内三 topic
rebaseline → `MeasurementBaselineAck` → capture/canary barrier。等待基线不能发生在 resume 前，
也不能在 ACK 前捕帧。

`nvidia-smi`/NVML、MuJoCo realtime factor、controller state deadline counter 或 camera producer FPS
任一生产接口缺失，PID 归属不完整，或者指标时间轴无法对齐时都拒绝，不把缺测当成零负载。
任一 SOFT_STOP 先停止新 lease；只有所有指标连续 10 秒低于软门才恢复。30 秒内不能恢复时升级
为 HARD_STOP。这两个窗口由 v2 配置冻结，不能由画像或调用者延长。

## 8. PerceptionBroker 扩容

Broker 仍只有一个 GPU 模型服务。YOLO-Seg 始终优先；Grounded-SAM 只在 v1 已允许的感知
失败边界回退。八个 Worker 可同时各提交一个请求，两个模型队列容量都固定为 8，并继续按
Worker 轮转。

v2 使用两阶段 Broker 协议，避免 GPU 排队直接耗尽帧龄。Worker 先提交不含图像的
`BrokerTicket`；Broker 轮到该 ticket 时返回绑定 lease、worker generation、broker generation
和 ticket nonce 的 `CAPTURE_NOW`。Worker 必须在 0.5 秒内采集并提交新 RGB-D/TF。YOLO ticket
queue timeout 为 10 秒，Grounded-SAM 为 30 秒；这只延长未捕帧等待，不延长任何已有帧的
新鲜度。fallback 创建新的 ticket 并重新捕帧，不能复用 YOLO 阶段留下的帧。

收到 frame 后，inference deadline 受模型原始 v1 timeout 和 5 秒 pose admission 新鲜度预算限制：

```text
freshness_deadline = capture_monotonic + 5.0
qualified_inference_ceiling = 2.0  # YOLO; Grounded-SAM 为 4.0
inference_deadline = min(dispatch_monotonic + v1_inference_timeout,
                         freshness_deadline - 0.25)
```

过期、重复或错 generation 的 `CAPTURE_NOW`/frame 一律 fence，ticket 不能授权机器人动作或延长
lease。pose admission 前再次验证帧龄 `<5.0 s`。
qualification 在 `START_8` 后、三轮 pick-place canary 前增加独立 Broker 子阶段，分别产生八路
同时 YOLO、八路同时 Grounded-SAM 和混合队列的负载证据；Grounded-SAM 负载由专用 Broker
canary 触发，不改变正式 pick-place 的 YOLO-first
失败矩阵。各模型至少 24 个完成样本，缺失 p99 时拒绝；YOLO inference p99 必须 `<=2.0 s`，
Grounded-SAM 必须 `<=4.0 s`。deadline、计算输入和结果写入请求证据。Broker queue 或 inference timeout 仍是
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

Authority 是由 system manager 管理的 `so101-admission` 专用用户服务，不是 Coordinator 的
子进程。权威 registry、revocation journal 与 acceptance root 位于 root/Authority-only 可写的
`/var/lib/so101-admission/`；候选 batch、Coordinator 和 Worker 均无写权限。操作员通过 0660
Unix socket 请求登记，Authority 用 `SO_PEERCRED` 校验允许组，生成 batch nonce，并把固定
evidence root 的目录 FD 身份写入权威 registry。后续 RPC 只接受 `batch_id`、nonce 和请求类型；
当前 stage 由 Authority 从 sealed journal 推导，调用者不能传 stage、阈值、任意路径或期望结果。
响应由 Authority-only Ed25519 私钥签名，Coordinator 使用安装时固定的公钥验证，只接受当前
batch/epoch/nonce 的响应；Coordinator 永远拿不到可签发 acceptance 的密钥。
首次安装在 ai-station 上生成私钥到 root/Authority-only 路径，只把公钥导出到仓库。必须先
审查并提交公钥，再重装/重启服务并回读运行公钥 fingerprint 与 repo 公钥完全一致，之后才能
开始 qualification；密钥轮换会令既有 profile 失效并要求重新 qualification。

Authority 与 watchdog 不能从操作员可写 worktree、editable install 或 `--symlink-install` 加载。
部署脚本从已审查 commit 构建 wheel，并安装到
`/opt/so101-w8-admission/releases/<runtime_content_sha256>/venv`；整个 release、解释器、依赖、
unit 和配置由 root 拥有，目录 0755、不可变文件 0444/可执行文件 0555，且 import tree 无
symlink。systemd 使用该 release 的绝对 Python 路径与 `-I -s`，`WorkingDirectory=/`，清空
`PYTHONPATH` 并禁用 user site；启动时输出所有受信模块 `__file__` 与 release manifest hash，
任何路径越界或 hash 漂移都拒绝。Worker/开发 overlay 可以继续 symlink install，但不能进入
Authority/watchdog 的 `sys.path`。候选 UID 必须无法修改 release、unit、私钥、registry 和
pending records。

`verify_stage(batch_id, nonce) -> StageAcceptance` 可为 1/2/4/6/8 阶段出具 acceptance；只有
Authority 推导出 stage=8 且三轮全通过时，才返回 W8-only `ProvisionalAdmission`。
`verify_profile(batch_id, nonce) -> W8AdmissionProfile` 在正式结果和 cleanup 后运行。
`revoke(profile_id, reason, evidence_sha256)` 先 fsync append-only revocation journal，再使 profile
失效；进程重启后仍必须拒绝 revoked profile。Authority 以安全目录句柄读取 sealed 文件，复核
SHA256、inode、大小和修改时间，再从原始样本重新计算指标。候选写者关闭文件后，Authority
从已登记目录 FD 读取并复制到 Authority-owned staging，fsync 后原子 seal；chmod 只读或候选
目录内的 ownership 标记本身都不构成封存。

evidence root 和普通子目录继续保持操作员 0700。对每个待封存目录只增加
`u:so101-admission:--x` ACL，对已经关闭的固定 regular file 增加
`u:so101-admission:r--` ACL；不授予目录列举或写权限。Authority 只通过已登记 root FD 和固定
相对路径打开文件，复制完成后即可移除该文件 ACL。Authority 通过 socket 返回签名 bytes，
Coordinator 负责把不具权威性的副本写入 `authority-receipts/`；Authority 不需要写 candidate
evidence root。以两个真实 UID 的无 ROS smoke 验证读取桥、候选不能写权威目录、symlink 与
inode 替换仍被拒绝。

### 9.2 画像内容

画像绑定：

- CPU 型号/拓扑、逻辑核数、总内存、GPU 型号/UUID/显存；
- Linux 内核、NVIDIA driver、cgroup controller 和容器 runtime；
- ROS 发行版、RMW 名称/版本、Domain 池和 discovery 配置；
- runtime content、install、容器、策略、场景、模型、配置和完整点位清单哈希；
- 五个阶段的窗口、样本数、缺样数、CPU/RAM/GPU/PSI、实时率、渲染和 Broker 分位数；
- provisional admission、正式点位结果、cleanup 和所有熔断事件。

`runtime_content_sha256` 使用固定 allowlist，只覆盖实际影响执行的 Python/C++、launch、package
metadata、Docker 构建输入、运行配置、策略、场景和模型身份文件；明确排除 `docs/**`、evidence、
实验账本、Authority registry、accepted profile JSON/YAML 和 Git commit 对象。完整清单及每个
文件哈希写入画像。`installed_runtime_content_sha256` 对 install space 中同一逻辑 allowlist 的
产物计算，不对整个 install tree 做递归哈希，并采用相同排除项。`implementation_commit` 仅供审计，不参与匹配；这样把 accepted profile
提交到仓库不会自我失效，而任何 allowlist 内运行文件变化都会拒绝。normal 的点位子集仍用
qualification 时冻结的完整 catalog identity，并用既有 `--point-id` 表示 selection，不能另建
一个 catalog 冒充 provenance 一致。

画像无固定时间有效期。以下变化立即失效：

- 主机硬件、内核、driver、RMW、cgroup 或容器能力改变；
- runtime content/install、容器、模型、策略、场景、v2 配置或完整点位清单哈希改变；
- clean-host normal W8 出现 OOM、GPU Xid、controller deadline miss、进程逃逸或资源硬门；
- sealed evidence 损坏、指标缺样或 acceptance 身份无法验证。

外部临时负载只拒绝当前运行。若当前主机满足 clean-host 前提却仍低于 accepted profile 的
余量，画像失效并要求重新 qualification。

normal 启动时，Authority 根据 watchdog 从 preflight 到故障时刻的 0.5 秒 foreign-process、
GPU process 和系统负载序列签发 `CleanHostWindowReceipt`。使用 accepted profile 的 normal batch
若触发 OOM、GPU Xid、controller deadline miss、cgroup 逃逸或冻结资源硬门，ResourceMonitor
把原始 `HardStopEvidence` 交给 watchdog。watchdog 在杀进程前持久化包含 profile ID、batch、
reason、clean-host receipt SHA256 的 pending failure；Authority 可用时立即裁决，不可用时写入
root-owned `/var/lib/so101-admission/pending-revocation/`。Authority 每次启动以及处理任何
register/normal admission 前，必须先消费全部 pending failure。只有 Authority 验证
`clean_host=true` 且 reason 属于上述 profile-invalidating 集合时，才 fsync `revoke()`；存在未
处理 pending record 时 fail closed。foreign workload 出现过的运行只拒绝当前 batch，不撤销
画像。

资源与行为资格分开：

- `resource_profile_accepted=true` 表示 W8 资源和隔离证据有效。
- `qualification_passed=true` 仍要求正式 20 点全部首次有效执行通过并完成 cleanup。

行为失败不能冒充资源失败，20/20 也不能覆盖资源门失败。

## 10. Worker 丢失与熔断

正式队列开放后必须维持 `required_healthy_slots=requested_worker_count`；qualification 的正式
阶段请求固定为 8，因此必须维持八个，normal N 只维持 N，绝不额外启动到 8。
`slot_healthy` 独立于能否领取新 lease：只要 generation
身份正确、heartbeat 新鲜、资源/cgroup/Domain gate 有效，slot 处于 `AVAILABLE`、`LEASED`、
`INITIALIZING`、`EXECUTING` 或 `FINALIZING` 都计入健康容量。dispatcher 只从 `AVAILABLE` 且
未达到 K 的 Worker 发 lease。暂时无点、队列尾部不足 N 点或达到 K 的 Worker 必须继续 slot
heartbeat 并等待明确 `BATCH_TERMINAL`，不得自行退出；replacement 继承该 slot 持久化的
`lease_count`，它在 `LEASE_GRANTED` 时增加 1、使剩余配额减少 1；已授予计数包含未完成、`INVALID` 和 `INDETERMINATE`，不能
退款或通过换代重置配额。

slot heartbeat 是与 active lease 无关的独立 RPC：

```text
SlotHeartbeat(batch_id, coordinator_epoch, worker_id, worker_generation,
              worker_session_id, sequence)
SlotHeartbeatAck(accepted, coordinator_epoch, next_deadline_monotonic_s)
```

Worker 从首次 ready 到 `BATCH_TERMINAL` 每 1 秒发送；Coordinator 按自身 monotonic clock 固定
5 秒 deadline。它只能证明 slot 存活，不能创建/续租 lease、授权动作或改变 K。epoch、generation、
session、sequence 任一旧值都 fence；active Worker 同时发送既有 lease heartbeat 和 slot heartbeat。

Worker 崩溃、退出或被隔离时：

1. Coordinator 立即停止发放新 lease。
2. 其他 Worker 可完成已经开始的点，避免主动制造 `INDETERMINATE`。
3. 故障 slot 的旧 generation 完成 fencing 和进程清理。
4. replacement 沿用原 Domain，增加 `worker_generation`，通过完整 ready gate。
5. 重新达到 `required_healthy_slots` 个 `slot_healthy=true`，且至少一个 Worker 可领取时才恢复队列。

冻结期限内无法恢复时返回 `W8_CAPACITY_LOST`。已完成点保留原裁决，但整个批次不能声明 W8
资格。不得按七个或更少 Worker 继续派发新点。

软门事件暂停新 lease并等待恢复，例如 Broker queue 接近 deadline、CPU pressure 超过画像
余量或主机内存接近设计保留值。硬门事件执行受控停止，例如 OOM、GPU Xid、controller
deadline miss、cgroup 逃逸或 `MemAvailable < 4 GiB`。正式 attempt 已开始但结果无法证明时
仍按 v1 记为 `INDETERMINATE`，不能改成 `INVALID` 后重跑覆盖。

## 11. 错误码

| 边界 | 错误码 |
| --- | --- |
| 配置 | `CONTRACT_V2_MISMATCH`, `EXACT_WORKER_COUNT_REQUIRED`, `UNIX_SOCKET_PATH_TOO_LONG` |
| Domain | `DOMAIN_POOL_INCOMPLETE`, `DOMAIN_CLAIM_CONFLICT`, `DOMAIN_PROCESS_UNVERIFIABLE`, `DOMAIN_DISCOVERY_NOT_QUIET` |
| cgroup | `CGROUP_V2_UNAVAILABLE`, `CGROUP_DELEGATION_UNAVAILABLE`, `CGROUP_ENROLLMENT_FAILED`, `PROCESS_ESCAPED_CGROUP` |
| 静态资源 | `HOST_RESOURCE_BASELINE_FAILED` |
| 运行资源 | `MEMORY_HARD_LIMIT`, `GPU_HARD_HEADROOM`, `CPU_PRESSURE_LIMIT`, `METRICS_TRANSITION_TIMEOUT`, `METRICS_IDENTITY_DRIFT` |
| 公共依赖 | `BROKER_BACKPRESSURE_LIMIT`, `SIMULATION_REALTIME_LIMIT`, `CONTROLLER_DEADLINE_MISS` |
| Authority | `AUTHORITY_UNAVAILABLE`, `AUTHORITY_AUTHENTICATION_FAILED`, `AUTHORITY_EVIDENCE_ACCESS_FAILED`, `PENDING_REVOCATION_UNPROCESSED`, `PROVISIONAL_ADMISSION_DENIED`, `PROFILE_PROVENANCE_DRIFT`, `PROFILE_REVOKED` |
| Watchdog | `WATCHDOG_UNAVAILABLE`, `QUALIFICATION_CRASHED` |
| Worker 容量 | `SLOT_HEARTBEAT_TIMEOUT`, `W8_CAPACITY_LOST` |

错误码要同时进入事件账本、batch summary 和 CLI stderr。正式队列开放前失败时不创建正式
point attempt，也不把未执行点放进成功率分母。

## 12. 崩溃边界、证据布局与写入权

v2 qualification 不支持 resume。每个 batch 由 system manager 启动独立
`so101-parallel-watchdog@<batch>.service`。watchdog 在启动 Coordinator 前原子持有全部 Domain
claim FD、创建并拥有 batch slices，使用 pidfd/systemd unit 状态监视 Coordinator 与 monitor，
并监视长期 Authority service。Coordinator、Authority 或资源监视器在 `PREFLIGHT` 到
`PROFILE_ACCEPTED` 之间异常退出时，watchdog 先把 root-owned terminal record fsync 到
`/var/lib/so101-admission/pending-terminal/`（root 写、Authority 只读），再冻结 batch slice、TERM/KILL 全部 owned leaf、
验证 DDS quiet、关闭 claim FD并移除 slice/socket。Authority 可用时立即吸收该记录；Authority
自身宕机时必须在重启后先吸收 pending record，之后才接受任何 register/verify RPC。

该流程 fence 当前 epoch、完成清理并写 `QUALIFICATION_CRASHED`；该 batch 永久 terminal invalid。再次
尝试必须使用新 batch ID，并从 `START_1` 重新完成五级三轮。normal/formal 点位仍沿用 v1 的
attempt 终态与恢复语义，不能用 qualification 重启覆盖已开始 attempt。

AF_UNIX 地址在任何副作用前统一做完整模板预算。冻结上限为 107 bytes，必须枚举 allocator
占位 `ipc/<slot>/s`、`worker-NN.sock`、`worker-NN-control.sock`、Broker perception/authority、
Authority、watchdog 以及 replacement 复用路径；任一路径超限就返回
`UNIX_SOCKET_PATH_TOO_LONG`。现场 task root 与 batch 目录固定使用短路径，不能把长的人类描述
拼进 socket namespace。

现场 qualification 使用一个已登记的 durable evidence root：

```text
/data/work/so101-evidence/parallel-w8/<short-run-id>/
├── dispatch/
├── authority-requests/
├── authority-receipts/       # 只保存已签名响应副本，不是权威 registry
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
├── b/
│   ├── s/                 # cgroup smoke batch
│   ├── m/                 # one-Worker runtime metrics smoke
│   ├── q/                 # qualification batch
│   └── n/                 # normal reuse batch
└── scratch/
```

Coordinator 写 batch 事件和正式点位投影；Worker 只写自己的 canary/attempt/recovery 目录；
资源监视器只写原始时间序列；Coordinator 把 Authority socket 返回的签名响应副本写入 receipts，权威 acceptance/profile
只写 Authority-owned 路径。所有 sealed 目录继续使用临时目录、文件与目录 fsync、原子 rename、
候选 writer close、Authority 复制到自有 staging 和只读回读。Authority registry、revocation、
私钥与权威 acceptance 不放在候选可写 evidence root 内。

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
  --broker-image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1 \
  --yolo-weights <absolute-yolo-best.pt> \
  --yolo-weights-sha256 <sha256> \
  --grounded-root <absolute-grounded-root> \
  --grounded-manifest-sha256 <sha256> \
  --run-mode execute
```

normal W8 额外提供 accepted profile ID。repo-tracked profile 只是签名审计副本；CLI 必须向
Authority-owned live registry 查询签名、revocation 和当前 provenance，不能由调用者直接传
任意 profile SHA：

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
  --broker-image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1 \
  --yolo-weights <absolute-yolo-best.pt> \
  --yolo-weights-sha256 <sha256> \
  --grounded-root <absolute-grounded-root> \
  --grounded-manifest-sha256 <sha256> \
  --run-mode execute
```

W1–W3 旧命令和 v1 配置不变。

## 14. 测试与现场验收

### 14.1 自动化测试

- v1 全部 frozen-value 和行为测试保持通过。
- v2 normal 对请求 N 验证四种计数都等于 N；qualification 只接受 W8，拒绝 W9、配置漂移和任何实际 Worker 数降级。
- 八 Domain 全量原子 claim；部分冲突不留下半套 claim。
- qualification 在 barrier release、seal、provisional 和 queue-open 边界崩溃时都整批失效、清理且不能 resume。
- 20 点首波八个 lease、尾部不足八点、四点 normal 和 K 用尽时，八个健康 Worker 都保持存活；replacement 不重置 K。
- 所有 Worker、Broker 和后代进程都属于预期 cgroup；逃逸会触发硬门。
- canary 必须有三轮和 N Worker 的执行重叠，不能混入正式点位统计。
- 阶段不能跳过、倒退或在失败后继续扩容。
- Authority 拒绝自签记录、伪造 accepted 文件、registry 篡改、revoked profile、任意路径、文件替换、缺样、损坏和 provenance 漂移。
- clean-host normal 硬故障即使碰上 Authority 宕机，也会由 watchdog 持久 pending revocation；服务重启后同 profile 被拒绝。foreign workload 只拒绝当前 batch。
- W8 丢失 slot 后暂停发新 lease；恢复到八个后继续，超时则 `W8_CAPACITY_LOST`。
- Broker 对八 Worker 保持有界公平；真实 Worker/proxy/transport/runtime 链上的八路 YOLO、八路 fallback、混合请求、逐模型重新捕帧和最终帧新鲜度均通过，YOLO-first 和既有失败矩阵不变。

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
