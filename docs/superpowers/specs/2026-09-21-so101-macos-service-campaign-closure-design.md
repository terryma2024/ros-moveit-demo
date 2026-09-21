# SO-101 macOS service campaign 闭环设计

日期：2026-09-21
状态：根据首轮独立审查修订，待复审
实现基线：`codex/so101-unified-webapp`，`c6c91b8ac4d3f5e5f3fa138183679c36c80711eb`

## 1. 背景

统一 Web 服务已经可以在 macOS 上启动和控制 MPS W2 campaign。服务持有执行进程，control
protocol、lease 续约、取消和进程组清理均已接通。最后一次服务驱动运行完成了 16 次 lease
续约，没有拒绝，退出时两个 Worker 均被回收，registry 和 IPC 目录也已清空。

这条链路仍不能作为端到端验收结果，原因有四项：

1. `ros2_control_node` 停在加载 `RobotSystem` 期间，`/controller_manager/list_controllers`
   没有稳定出现。三个 spawner 无法激活 controller，Worker 因 `STATION_NOT_READY` 拒绝执行。
2. 现行 schema v4 只声明 exact W2，而人工失败重试必须是单点、`SEQUENTIAL`、N=1、
   `FULL_RESTART_RETRY`。同一份配置不可能同时满足两个合同。
3. macOS campaign 写入自己的 worker、broker 和终态证据，但没有现有服务投影依赖的
   coordinator journal。服务能控制执行，却无法把点位进度投影给 Web，页面一直显示 `UNRUN`。
4. 当前分支已退役 9 月 18 日的 measurement/provider/promotion 链；而旧设计又依赖
   Linux `/proc`/cgroup/NVML，不能直接支撑 macOS Stage C/D。

这些问题共同决定了一个边界：不能再用兼容分支、超时调整或终态文件轮询收口。系统需要
一套明确的 macOS runtime 闭包、一个独立的 N1 retry 合同，以及跨平台一致的投影事件协议。

## 2. 目标和非目标

### 2.1 目标

- 在 mac-mini 上稳定启动 task station，并证明 controller、MoveIt service/action、ROS graph
  和运行产物来自同一套冻结安装闭包。
- 保留 schema v4 exact-W2 语义；新增 macOS 单点完整重启重试合同，以及供
  Stage C 与 sequential Web 使用的普通 W1 first-pass 合同。
- first pass 和 retry 都由同一个统一服务 API 发起，并由同一个进程所有权模型管理。
- macOS campaign 产生可恢复、可校验的点位事件，Web 只消费服务权威投影。
- first pass、retry、资源资格和业务成功率继续使用独立批次与独立统计。
- 重建封闭的 measurement/provider/promotion 链，为 macOS N1/N2 建立独立的 MPS 统一内存预算。
- 任何 runtime byte、配置语义或执行依赖变化都生成新的执行身份 R；旧资格不得静默复用。

### 2.2 非目标

- 不改变 Linux/CUDA schema v2/v3 的执行语义。
- 不把 schema v4 从 exact W2 改成任意 worker count。
- 不通过放宽 readiness、跳过 controller 检查或使用 dry-run 伪造 live 成功。
- 不让 React 读取原始日志、worker 文件或 `campaign-result.json` 来重建状态。
- 不自动操作真实机械臂。本文的 live 验收范围是 macOS MuJoCo 仿真。
- 不授权删除历史证据、停止 foreign 进程、promotion、push 或 merge。

## 3. 总体决策

| 问题 | 决策 |
| --- | --- |
| station 无法 READY | 建立 task-owned runtime closure，用直连 service client、server 进程/加载状态、DDS 可见性和 `RobotSystem` A/B 逐层定位；在证据闭合前不预设根因 |
| N1 retry 与 exact W2 冲突 | 保留 v4，新增 schema v5 `MPS_W1_FULL_RESTART_RETRY`；不放宽 v4 |
| Stage C 普通 N1 无 macOS profile | 新增 schema v6 `MPS_W1_FIRST_PASS`，保留 20 点 ordinary N1 资格合同 |
| Web 投影缺失 | 复用现有 `CoordinatorJournal` 写标准事件，唯一 canonical reducer 验证并事务化投影 |
| Web 选点未真正驱动执行 | 新增 selection/catalog 绑定和共享点位队列；Worker 每次只执行当前 lease 绑定的一个点 |
| Stage C/D 资源链已退役且限定 Linux | 重建 typed measurement/provider/promotion 链，新增 `DARWIN_MPS_UNIFIED_MEMORY_V1`；macOS 只资格化 N1/N2 |
| 多平台差异 | 服务通过 typed execution profile 选择 runner 和 projection source；Web API 不出现平台分支 |
| 旧资格 | 新执行身份冻结后重新测量；旧 P/Q/M 只读保留 |

执行关系如下：

```text
Unified Web API
  -> ExpertValidationSupervisor
      -> execution profile
          -> v4 MPS W2 first-pass adapter
          -> v5 MPS W1 retry adapter
          -> v6 MPS W1 first-pass adapter
      -> ExecutionProcessOwner
      -> ProjectionSource
          -> CoordinatorJournalReader
      -> canonical reducer + durable store projection
  -> WebSocket / REST projection
  -> React UI
```

## 4. Runtime closure 与 station readiness

### 4.1 稳定闭包与单次运行绑定

原有 `RuntimeClosureManifest` 拆成三层，避免把 fresh 字段混入稳定身份：

- `RuntimeClosureIdentity` 只包含可跨重启保持的 bytes 和语义：source commit、
  `third_party/mujoco_ros2_control` commit、copied install prefix 的相对文件 SHA256
  inventory、执行文件与 dylib/plugin XML 来源、Python/ROS 2/MuJoCo/MoveIt 版本、
  净化后环境约束，以及 robot description、controller YAML、model 和 launch hash。
- `RunBinding` 绑定单次运行的 campaign/batch id、fresh `ROS_DOMAIN_ID`、station session、
  evidence root、owner generation 和启动时间。
- `RuntimeAttestation` 在进程启动后记录实际 PID/birth identity、已加载 image/dylib 路径、
  运行时查询结果，并同时引用前两者的 hash。

启动前验证预期 `RuntimeClosureIdentity`；启动后、宣布 READY 前再用进程 image 与
加载库读回生成 `RuntimeAttestation`。缺项、hash 漂移、canonical workspace 污染或动态库
来源无法确认时，station 不得 READY。五次重启要求闭包身份相同，但每轮
`RunBinding` 和 `RuntimeAttestation` 必须不同。

### 4.2 分层诊断，不预设根因

controller-manager 问题按以下顺序留证：

1. 用与 Worker 相同的 domain 启动 `MINIMAL_CONTROLLER_MANAGER`，不加载 `RobotSystem`。
2. 记录 server PID/birth、进程生存状态、实际加载库和 node/service graph。
3. 跳过 `motion_stack_ready` 聚合等待，使用一个受控的直连 client 调用
   `/controller_manager/list_controllers`，同时记录 DDS discovery 可见性。
4. 换为 `ROBOT_SYSTEM_CONTROLLER_MANAGER`，只增加当前 MuJoCo hardware plugin 和同一套
   robot description/config，重复相同观测。

A/B 只缩小怀疑边界，不单独证明根因。例如最小进程存活但直连 client 不可见时，
需要继续区分 server 注册、DDS 发现、domain 污染和 dylib/ABI；只有加载 `RobotSystem` 后进程停在
某个可观测初始化阶段，才能把问题定位到 hardware 路径。根因字段在证据闭合前保持
`UNCONFIRMED`。

hardware 路径必须写出 `PLUGIN_RESOLVED`、`SIMULATION_ENDPOINT_READY`、
`HARDWARE_INITIALIZING`、`HARDWARE_READY`、`CONTROLLER_MANAGER_SERVICES_READY` 和
`CONTROLLERS_ACTIVE` 结构化状态。每阶段有独立 deadline 和错误码；hardware plugin 不得
无限阻塞 controller-manager 构造。

### 4.3 Readiness 判据

`motion_stack_ready` 继续 fail closed。通过条件是：

- `/controller_manager/list_controllers` 可由直连 client 调用；
- `joint_state_broadcaster`、`arm_controller`、`gripper_controller` 均为 `active`；
- MoveIt 三个 service 与三个 action 均可用；
- controller query、service/action 观察来自同一 `ROS_DOMAIN_ID`；
- 当前 `RuntimeClosureIdentity` 与 campaign 绑定值一致，且启动后 attestation 读回一致。

ROS daemon 只是发现缓存，不是事实源。live gate 前后都用直接 node/service 查询；出现
daemon stale 时保留本轮证据并标记环境污染，不把这一轮当作产品通过或产品失败。

## 5. Web 选点到真实执行的闭环

### 5.1 SelectionBinding

Web 生成点位后，服务在启动 campaign 前写入不可变 `SelectionBinding`。它有两个互斥变体：

- `FirstPassSelectionBinding`：用于 v4/v6，要求 4–20 个点并包含四个固定 anchor；
- `RetrySelectionBinding`：用于 v5，只包含一个点，必须引用原 first-pass catalog hash、
  selection hash、result hash 和 point id，且原 result 是已提交的业务 `FAILED`。

两个变体共享以下字段：

- catalog schema/version、catalog SHA256 和坐标系；
- 按稳定顺序排列的 selected point id、坐标、姿态与每点 hash；
- selection SHA256 与 requested count；
- campaign/batch id、execution identity R 和 `RuntimeClosureIdentity` hash。

adapter 只接受该绑定，不得在本地重新生成点、默认取 catalog 前两点，也不得把
完整安装版 `rgbd_task_points.yaml` 交给 Worker 自行遍历。catalog 或 selection hash 不一致时
fail closed。

### 5.2 共享队列和单点执行合同

W2 的两个 slot 只代表并发容量，不再静态绑定 selection 的前两点。所有被选的 4–20 个
点进入同一个 durable queue。每次调度的唯一身份为：

```text
(campaign_id, batch_id, point_id, attempt_id, generation, worker_id)
```

Worker 在一个 lease 中只运行一个点。实现可生成经 hash 绑定的单点输入文件，或向 batch
runner 传入显式 point id 与 selection manifest；两种方式都必须由 runner 读回 point id/hash。MPS
broker inference attempt 与同一 `attempt_id` 绑定，不能成为与物理点位执行脱节的独立成功计数。

一个 result 只能在以下事实都已持久化后提交：对应点的 station READY、MoveIt 执行记录、
pick-place 业务判定、broker attempt（若需要）、证据 manifest 与 cleanup ownership。这个 result 才是
canonical reducer 得出 point terminal 的事实来源。

N1 retry 的 queue 只能包含 `RetrySelectionBinding` 中的 point id；不得回退到 catalog 第一点、
重跑整份点位文件，也不得对 retry binding 强加“包含四个 anchor”的 first-pass 检查。

## 6. schema v5/v6：macOS W1 闭合合同

### 6.1 保留 v4

schema v4 的 bytes 和含义保持不变，包括现有两个闭合平台组合：Linux/CUDA/EGL 和
Darwin/MPS/CGL。Darwin 组合继续要求 private-path Unix IPC、exact W2 与
`allow_cpu_fallback=false`。现有 v4 first-pass 证据可继续审计，但执行 bytes 变化后不得继续
授予生产资格。

### 6.2 v5 重试 profile

新增 schema v5，只声明一个平台组合：

```yaml
schema_version: 5
execution_profile: MPS_W1_FULL_RESTART_RETRY
platform: darwin
backend: mujoco
accelerator:
  kind: mps
  selector: default
requested_device: mps
ipc_transport: darwin_private_path_unix
execution_mode: SEQUENTIAL
worker_count: 1
allowed_batch_kind: FULL_RESTART_RETRY
allow_cpu_fallback: false
```

v5 不是通用 worker-count 配置。它必须拒绝：

- `FIRST_PASS`、`ADAPTIVE_POOL`；
- 点位数不是 1；
- worker count 不是 1；
- 非 `FULL_RESTART` lifecycle；
- CPU fallback、Linux transport、CUDA selector；
- 复用 first-pass batch id、evidence subtree 或统计记录。

### 6.3 v6 普通 W1 first-pass profile

Stage C 普通 N1 和 sequential Web 不借用 v5 retry 语义。新增独立 schema v6：

```yaml
schema_version: 6
execution_profile: MPS_W1_FIRST_PASS
platform: darwin
backend: mujoco
accelerator:
  kind: mps
  selector: default
requested_device: mps
ipc_transport: darwin_private_path_unix
execution_mode: SEQUENTIAL
worker_count: 1
allowed_batch_kind: FIRST_PASS
allow_cpu_fallback: false
```

v6 必须使用 `FirstPassSelectionBinding`。普通 N1 资格沿用已批准的 20 点、同 R、
`FULL_RESTART`、独立物理证据、资源合同和 cleanup 合同；v6 拒绝 `FULL_RESTART_RETRY`、
单点 retry binding、W2 和 adaptive 请求。v6 的 exact-N qualification 由现有
第 10 节重建后的 `ExactNQualificationProvider` 管理，不与 `RetryQualification` 混用。

### 6.4 RetryStartRequest 与互斥准入

服务增加独立 `RetryStartRequest`，不再用 first-pass `CampaignStartRequest` 加临时
`FixedExecutionConfig` 拼出重试。请求绑定：

- original campaign id、failed point id 和原始 terminal result hash；
- 新 retry batch id、schema-v5 config path/hash；
- `SEQUENTIAL`、N=1、`FULL_RESTART_RETRY`、`FULL_RESTART`；
- fresh station session、ROS domain、evidence subtree；
- runtime closure、模型和 execution identity R；
- lease generation、service session 和 command id。

只有业务 `FAILED` 点可以进入 retry。原 batch 已 terminal-clean、没有 recovery fence 或
active owner、当前 control lease 有效等公共检查无条件适用。`INFRA_FAILED`、
`INDETERMINATE`、attempt-level `INVALID` 或 point `UNRUN` 必须拒绝。

retry admission 使用两个封闭且互斥的 context，不接受 `mode` 字符串或 skip flag：

- `ProductionRetryContext` 由 production authority factory 签发，必须验证已批准
  `RetryQualification`、v5 profile/config hash、execution identity R、promotion/deployment receipt 和
  当前 control lease。普通 Web API 只能获得这一类 context。
- `MeasurementRetryContext` 由独立 measurement authority reader 对 sealed authorization 原文件安全读取后
  签发。授权精确绑定 operator UID、task/dispatch id、candidate R、v5 profile/config hash、
  original campaign/result/point id、new batch/evidence root、owner generation、一次可用 command id、
  expiry、max-runs 和 abort policy。它不要求尚未生成的 `RetryQualification`，不能写
  promotion，也不能调用 production endpoint。

context factory token 不是外部授权。adapter 要同时校验 context 类型、factory 来源、原授权 hash
和请求绑定。无资格且无有效 measurement authorization 时拒绝；candidate context 进入
production endpoint 或 production context 进入 measurement endpoint 也拒绝。

消费 command id、创建 retry binding、写入 owner spawn intent 必须在一个数据库事务中完成。事务后
启动失败则保留可恢复的 spawn intent 和 fence，不得重复消费命令。retry 成功不覆盖
first-pass 结果，只追加 retry outcome。

### 6.5 W1 composition

新增共用的 `macos_w1` composition primitive。它复用 MPS broker、snapshot、station owner、
control endpoint 和 cleanup primitive，只创建一个 slot、一个 Worker 和一个 ROS domain。对外保留
`macos_n1_first_pass` 与 `macos_n1_retry` 两个 typed entry，分别只接受 v6 与 v5，不开放
可任意组合 batch kind/profile 的通用 CLI。

服务端 adapter 增加 batch-kind 和 profile identity 校验，根据 typed request 选择 W2 first-pass、
W1 first-pass 或 W1 retry entry。adapter 不从点位数量猜 profile，也不在三个入口间 fallback。

## 7. 标准 projection journal

### 7.1 复用 CoordinatorJournal

campaign 是执行事实的生产者，服务是投影和权限的所有者。服务不轮询终态文件推测
运行过程；Worker 也不直接写服务数据库。

macOS W2 和 W1 composition 复用现有 `parallel_batch.journal.CoordinatorJournal`，不新建一套
相似存储。现有 owner lock、writer epoch、idempotency key、hash chain、fsync 和模糊 I/O 后 poison
语义保持权威。campaign/coordinator 是正常运行期唯一 writer，从取得 owner lock 到释放前不允许
Worker、service reader 或 reaper 直接 append。事件 envelope 在原有字段基础上扩展，至少显式包含：

```json
{
  "schema_version": 1,
  "writer_epoch": 3,
  "sequence": 17,
  "idempotency_key": "campaign-.../point-.../attempt-.../RESULT_COMMITTED",
  "previous_event_sha256": "...",
  "campaign_id": "campaign-...",
  "batch_id": "batch-...",
  "runtime_identity_sha256": "...",
  "config_sha256": "...",
  "event_type": "RESULT_COMMITTED",
  "observed_monotonic_ns": 0,
  "payload": {},
  "event_sha256": "..."
}
```

事件类型至少包含：

- `CAMPAIGN_STARTED`
- `WORKER_REGISTERED`
- `POINT_LEASED`
- `ATTEMPT_STARTED`
- `RESULT_COMMITTED`
- `POINT_TERMINAL`
- `BATCH_TERMINAL`
- `CLEANUP_COMMITTED`

`RESULT_COMMITTED` 引用 evidence root 内的 immutable manifest，并携带相对路径、SHA256、
point id、attempt id、worker id 和 generation。Worker 先用原子 rename 提交 result/manifest 并 fsync 文件
与父目录，然后通过私有 IPC 向 coordinator 提交带上述身份与 hash 的 commit proposal。
coordinator 验证 lease/generation、路径边界、symlink、hash 和 idempotency key，以唯一 writer 追加并
flush/fsync journal。随后它写入包含 `(writer_epoch, sequence, event_sha256)` 的
`CommittedWatermark`：先写同目录临时文件并 fsync，再原子 rename 并 fsync 父目录。只有两次
durability barrier 都成功后，coordinator 才通过已认证 IPC 发布 committed watermark，并对
Worker ACK。Worker 不能把 result 文件或尚未 watermark 确认的完整 journal frame 当成已提交事件。

recovery reaper 只能在以下条件全部成立后接管 writer：旧 coordinator PID/birth 已证明退出，
旧 owner generation 不再有活动子进程，独占 lock 成功，严格 replay 通过，且 journal 最后完整
frame 与 durable watermark 完全一致。随后 owner authority 签发新 writer epoch。reaper 先原子
提交并 fsync cleanup receipt，再按同样的 journal + watermark 顺序提交 `CLEANUP_COMMITTED`，
最后才释放 fence。旧 writer 尚在、lock 未取得、replay 失败或 watermark 落后时不自动接管。

### 7.2 ProjectionSource 和唯一 reducer

服务增加 typed `ProjectionSource`：

- Linux fixed coordinator 使用现有 coordinator journal source；
- macOS W2/W1 使用 coordinator journal source；
- adaptive 保持自己的 projection source。

三类 source 只做格式适配、identity/hash 验证和事件读取，不自己计算 projection delta。
`ProductionExpertValidationService` 按 durable execution binding 选择 source，然后把所有已验证事件交给
唯一 canonical reducer。React 和 OpenAPI 只看该 reducer 的持久化状态。

对每个事件，服务在一个数据库事务内完成：校验/record idempotency key、运行 reducer、更新
点位/尝试/批次全量状态，以及推进 accepted cursor。任何一步失败都回滚，不能出现
状态已变而 cursor 未变、或 cursor 越过状态的情况。服务重启后从持久化 cursor 继续；
重复事件幂等，epoch 退化、sequence 跳跃、hash 链断裂、identity 漂移或终态后非法追加都进入
`NEEDS_OPERATOR_RECOVERY`。

现有严格 `read_only_replay()` 语义保持不变，incomplete tail 仍拒绝；它用于恢复接管、
审计和资格。live projector 新增只读 `read_committed_prefix()`。它只接受两种 watermark 来源：
活跃 writer 在完成上述 durability barriers 后通过已认证 IPC 发布，或 writer 已证明退出后由
recovery owner 取得 lock、fsync watermark 目录并完成严格校验后发布。

reader 最多返回 sequence 不超过 watermark、且 `(epoch, sequence, hash)` 与 watermark 一致的
committed events。即使更后面的 frame 已 flush、换行完整且 hash 正确，也不投影、不推进
cursor。对尾部 fragment 返回 `TAIL_INCOMPLETE`；它不忽略中间损坏、完整记录 hash 错误、
sequence/epoch 断裂或 watermark 回退。

当旧 writer 仍活跃时，projector 只等待新 watermark。当 writer 已退出且存在 watermark 之后的
完整 frame 或 fragment 时，这些 bytes 标记为 `UNCONFIRMED_DURABILITY`，reaper 不得截断、投影或在
同一 journal 继续 append。批次保留 fence 并进入 operator recovery；如果需要记录后续 cleanup，只能
由经审核的新 journal segment 绑定最后 committed hash 和 orphan bytes digest。这一边界不改变
现有 poison 语义。

### 7.3 正交状态轴与合法转换

页面状态只来自已接受事件。reducer 分别维护，不混用以下状态轴：

- point status 只能是 `UNRUN/PASSED/FAILED/INDETERMINATE`；
- execution phase 可以是 `QUEUED/LEASED/RUNNING/TERMINAL`；
- attempt 另行保存 lifecycle、validity（包括 `INVALID`）和基础设施 outcome；
- batch 另行保存 business terminal、infrastructure terminal、cleanup complete 和 recovery fence。

`POINT_LEASED` 只把 execution phase 改为 `LEASED`，`ATTEMPT_STARTED` 只改为 `RUNNING`。
`RESULT_COMMITTED` 通过已验证的业务 result 推导 point terminal；`POINT_TERMINAL` 只能确认同一
result hash 的派生结果，不能单独创造终态。尝试 `INVALID` 或基础设施失败不得映射为
业务 `FAILED`。`BATCH_TERMINAL` 不代表 cleanup 完成；收到并验证 `CLEANUP_COMMITTED`
后才设置 `batch_cleanup_complete=true`。不符合合法转换表的事件不被接受，并置 recovery
fence。

`campaign-result.json` 继续作为终态摘要和审计索引，但不再承担 live projection。

## 8. 端到端流程

### 8.1 W2 first pass

1. Web 生成 4–20 点 selection，服务完成 lease、instance 和 preflight，并持久化
   `SelectionBinding`。
2. 服务选择 v4 W2 profile，绑定 `RuntimeClosureIdentity`、fresh `RunBinding` 与 evidence root。
3. adapter 启动 campaign；campaign 验证 selection 并写 `CAMPAIGN_STARTED`。
4. 两个 Worker 分别启动 station，通过 readiness 后注册，从共享队列每次领取一个点。
5. Worker 只执行 lease 绑定的 point/attempt，完成 result manifest 原子提交后向 coordinator
   发 commit proposal；coordinator 作为唯一 writer 写事件并 ACK。
6. 服务消费 journal，持久化 projection，并通过 REST/WebSocket 展示。
7. campaign 写业务终态，完成进程、station、broker、IPC 清理后写 cleanup 事件。

### 8.2 W1 first pass

1. Stage C measurement 或 sequential Web 创建 4–20 点 `FirstPassSelectionBinding`。
2. adapter 只接受 v6 `MPS_W1_FIRST_PASS`，一个 Worker 顺序消费共享队列。
3. 资格测量必须是 20 点、fresh `FULL_RESTART`、同 candidate R，并由已封存的
   `MeasurementContext` 授权；production 则要求 exact-N=1 的 `FixedProductionContext`。
4. result/journal/projection/cleanup 流程与 W2 相同，但实际 Worker 数必须始终为 1。

### 8.3 N1 retry

1. Web 只能选择一个 first-pass `FAILED` 点。
2. 服务先执行公共 eligibility 检查，再互斥验证 `ProductionRetryContext` 或
   `MeasurementRetryContext`；在单一事务中消费 command 并创建 retry binding/spawn intent。
3. 服务选择 v5 W1 profile，强制 fresh station session、ROS domain 和 evidence subtree。
4. W1 retry composition 执行一次完整重启生命周期，coordinator 写同一种 journal。
5. 服务把 retry outcome 追加到点位历史；first-pass 统计不变。
6. cleanup 验证通过后，retry batch 才进入 terminal-clean 状态。

### 8.4 Cancel、crash 与恢复

- 每层启动时都立即持久化 owner record：adapter/campaign/worker/station 的 PID、birth identity、
  PGID、parent owner、generation 和 spawn intent/confirmed 状态。station 即使位于独立 session，也必须挂在
  同一所有权树上。
- cancel 通过 control endpoint 到达 adapter，按叶子到根的顺序回收 station、worker、broker/campaign
  和 adapter；不以单个 PGID 清理替代所有权校验。
- adapter 被 `SIGKILL` 或服务崩溃后，recovery reaper 先核对每个 PID/birth、generation 和父子绑定，
  再按叶子到根回收。身份无法证明的进程不盲杀，进入 operator recovery。
- 只有完成回收且持有匹配 owner generation 的 reaper 才能写 cleanup receipt 和
  `CLEANUP_COMMITTED`。adapter 停止、`finally` 执行或未验证的零进程扫描都不足以解除 fence。
- 服务重启后先恢复 owner tree 和 recovery fence，再恢复 projection cursor，最后才决定是否重启或
  终止已记录的 spawn intent。
- journal 尾部只能按第 7.2 节处理；损坏 bytes 和所有 recovery 决策都保留证据。

## 9. 代码边界

预计修改或新增的责任边界如下，实施计划应在现场检查后确定精确文件清单：

| 组件 | 责任 |
| --- | --- |
| `parallel_batch/contracts.py` | schema v5/v6、closed platform profile 和拒绝规则 |
| `parallel_batch/w2_composition.py` | 保留 v4 exact W2；改为两 slot 消费共享点位队列 |
| 新 `parallel_batch/w1_composition.py` | W1 primitive 及 v5 retry/v6 first-pass 两个 typed entry |
| `parallel_batch/journal.py` | 扩展标准 payload 和 committed-prefix reader；保留 strict replay |
| `parallel_batch/queue.py` 及 Worker runner | `SelectionBinding`、durable queue、单点 lease 与 result 绑定 |
| `cli/macos_w2_campaign.py` | 验证 selection，调度全部被选点，写标准 W2 事件 |
| 新 `cli/macos_n1_first_pass.py` | v6 普通 W1 first-pass public entry |
| 新 `cli/macos_n1_retry.py` | 单点 N1 retry public entry |
| `cli/macos_service_campaign.py` | typed profile dispatch、batch-kind 校验和 control ownership |
| `runtime/task_stack.py`、launch composition | closure identity、run binding、attestation 和 bounded hardware bring-up |
| `expert_validation/supervisor.py` | `RetryStartRequest`、profile selection、互斥 retry context 与独立 config |
| `expert_validation/production.py` | `ProjectionSource` selection 与唯一 canonical reducer |
| `expert_validation/store.py` | reducer/cursor/idempotency 事务、retry/spawn binding、owner tree 和 fence |
| 新 `parallel_batch/resource_measurement.py`、`resource_budget.py` | 重建 raw B、exact-N Q、candidate P、promotion/deployment 验证 |
| `parallel_batch/accelerator_probe.py`、新 `darwin_resource_sampler.py`、`measurement_control.py` | 复用 unified-memory guard 语义，新增 Darwin 时序归属采样、sealed authority 和 owner/control binding |
| 新 Darwin pressure helper | 封装 `DispatchSourceMemoryPressure` 事件、50 ms heartbeat 和 monotonic timestamp，不伪造初始 NORMAL |
| 新 `cli/measure_macos_resources.py` | 只接受 typed Darwin measurement context 的候选入口；旧退役 CLI 仍拒绝 |
| Web/OpenAPI | 只扩展必要的 profile/retry reason，不实现平台特判 |

## 10. macOS 版本化资源预算与资格链

### 10.1 现状与暂停边界

当前分支不存在可用的“现有 provider”。`e62c86f5` 已主动退役 measurement runtime、
authority/context 和 promotion 链；`measure_parallel_resources.py` 固定返回
`MEASUREMENT_ENTRY_RETIRED`，`resources.py` 也拒绝 measurement authorization。旧 9 月 18 日预算设计
又把 `/proc`、NVML、cpuset/quota 和 delegated cgroup v2 当成强制前置，不能直接用于
macOS。

因此，Stage C/D 不是在 v6 runner 后可直接执行的步骤。必须先重建下述资格子系统，并完成
离线合同测试与 macOS 受限采样。这个前置未通过时，v4/v5/v6 只能做候选功能验证，
不能进入 Stage C、生成 candidate profile、进入 Stage D 或打开 production Web。

### 10.2 重建范围和封闭接口

本设计把已删除子系统的重建纳入同一实施范围，但不使旧代码复活为无审核 bypass。
重建后的边界是：

```text
sealed MeasurementAuthorization
  -> platform MeasurementContext factory
  -> ResourceProbe (Linux | Darwin)
  -> owned sampler + immutable raw manifest B
  -> ExactNQualificationProvider -> Q
  -> candidate budget profile P
  -> independent reviews + operator approval -> M
  -> deployment audit/receipt D
  -> FixedProductionContext
```

`MeasurementContext`、`FixedProductionContext` 与 `AdaptiveAllocationContext` 仍是无通用
dict/string 构造器的互斥封闭类型。独立 authority reader 每轮安全读取授权原文件，校验
UID、platform profile、candidate R、exact N、catalog/seed、batch/evidence root、时间窗、最大次数、
abort policy 和 owner scope。候选入口不要求尚未生成的 P/Q/M/D，但必须有平台安全包络和
一次性 measurement owner/control binding。生产入口不接受 measurement context。

Darwin measurement safety envelope 不从待测数据生成。它由已实现的 MPS start guard、操作员授权
内的 N 上限（本轮最大 2）、最长时间/批次数、现有 headroom floor、memory-pressure/swap 立即中止
规则和可验证 owner scope 共同构成。任何一项缺失都不启动采样，因此不需要用尚未生成的
candidate P 来授权首轮测量。

### 10.3 Darwin 计量与归属合同

Linux probe 保留旧 `/proc`/cgroup/NVML 合同，但它的 Q/P 不能用于 Darwin。Darwin 使用单独
`DARWIN_MPS_UNIFIED_MEMORY_V1` profile，并冻结 probe 代码和以下数据源：

- 主机内存与压力：Mach `host_statistics64` 与 `host_page_size`，总内存用 `sysctlbyname("hw.memsize")`，
  swap 用 `sysctlbyname("vm.swapusage")`。原始 counter、page size、换算值和 monotonic timestamp 同时保存。
- owned 进程 CPU/内存：对 owner tree 中每个已核验 PID/birth 调用
  `proc_pid_rusage(RUSAGE_INFO_V4)`，采集 user/system time、resident/physical footprint 与 I/O；主机 CPU
  用 `host_processor_info` 取同一窗口的 active/idle ticks。
- MPS 内存：由唯一 MPS broker 在已认证 telemetry channel 上自报
  `torch.mps.current_allocated_memory()`、`driver_allocated_memory()` 和
  `recommended_max_memory()`。每个样本绑定 broker PID/birth、generation、model hash、device 与时钟序号。
- 所有权：任何样本只聚合已登记 owner tree 和当前 broker generation。PID 复用、样本丢失、
  未授权 broker 自报断流或 generation 漂移使本轮 `INVALID`。

broker reload coverage 使用显式恢复状态机。coordinator 先提交
`BROKER_RELOAD_INTENT(from_generation, expected_generation=from+1, deadline, model/config hash)`，停止新 lease
并排空 in-flight request；验证旧 PID/birth 退出后，新 broker 必须在 deadline 内以精确 `+1`
generation、相同 device/model/config 完成注册和 warm-up。host CPU/内存/swap/pressure sampler 全程
不停；broker channel 在窗口内只能写 `NOT_RUNNING` 或 `RELOADING`，不产生伪 MPS 样本。旧新
broker 重叠、generation 跳变/回退、身份不匹配或 deadline 超时才是安全中止。

macOS 没有 cgroup v2/NVML 等价强隔离，也没有本设计可依赖的公开 whole-device Metal
占用/容量计数器。Darwin profile 不伪造这类保证：它设置
`device_gpu_capacity_claim=false`，只对 owner-bound broker metrics 做进程级归属；全机安全由统一内存
主视图、CPU 主视图、RTF/latency coverage 和已授权 background envelope 决定。已知未授权
Metal/MPS consumer 或 background 漂移超过 `E` 使本轮无效。任何 caller 尝试用 broker 数字
生成全设备 GPU 容量结论时返回 `GPU_ATTRIBUTION_UNKNOWN`，不进 Q。

MPS 的 current/driver 值只表示 broker 进程，不是全机 free VRAM。它们只用于实测峰值、
归属和回归对比，不得写入 NVML 字段或单独用作生产准入。启动 headroom 仍沿用已实现且
明确标记的 unified-memory proxy：`min(host_available, recommended_max_memory)`，再与 Darwin
profile 的实测包络和误差同时检查。

### 10.4 采样、误差和 coverage

Darwin sampler 使用同一 monotonic clock 合并主机、owner PID 和 broker 序列。每个 exact N 先做
50 ms/25 ms 交叉校准，冻结间隔、抖动、缺口、误差上界和峰值外推规则；已有 Linux 的
误差或数值不得复用。预算至少分开：主机 available/swap/pressure、任务 owned physical footprint、
CPU 窗口、MPS allocated/driver/recommended 比例、startup/steady/recovery/finalization 峰值。

qualification coverage 保留 cold start、真实 YOLO、fallback、render/motion overlap、release、broker reload、
Worker recovery 和 final cleanup 这些独立 cell。normal 至少五个连续有效的 20 点
`FULL_RESTART`；fault 只进安全包络，不进 normal/product 成功分母。超过误差上界、归属不明、
测量断流或资源上界未知时，对应 cell 保持 `UNKNOWN/NOT_COVERED`。

本轮 macOS 只允许 exact N=1（v6）和 exact N=2（v4）进入 Stage C。两者分别采样、分别生成
Q/P，不用 N2 外推 N1，也不为 N>2 生成候选 profile。N>2 在 macOS 保持 unavailable。

### 10.5 Darwin 准入与中止判定表

安全策略继承“全机 CPU 和统一内存至少保留 20%”，边界相等时通过，低于余量或
高于使用上限时拒绝。表中 `H=0.20`是事前固定 policy；`D` 是当前 exact N 在同 R 下
实测的需求上界，`E` 是采样别名、重复性和校准误差上界。P 保存 `D+E`，不保存
未加误差的观测峰值当作准入值。

判定分为两层。candidate gate 不读 P/Q：它只验证 sealed measurement authorization、固定 `H`、
现有 start guard、N/timeout 上限和本表的 watchdog 中止条件，同时采集 `D/E`。production gate
在相同固定规则之上再加已批准 P 中的 `D+E` 不等式和回归包络。下表用“C”和“P”分别
标出 candidate 与 production；未标注的中止条件对两者都生效。

数据类型也固定分开：CPU 累计 ticks、swapins/swapouts、sample sequence 是 monotonic
counters，回退为错误；available/used bytes、page buckets、physical footprint、MPS allocation 是 gauges，
允许正常增减，只做值域、identity 和本表明确列出的阈值检查。

| 资源/状态 | 数据源与单位 | 安全主视图和组合规则 | 启动准入 | 运行中止与时限 | 缺失/异常 |
| --- | --- | --- | --- | --- | --- |
| 统一内存 | `M=sysctl(hw.memsize)` bytes；`A` 来自冻结 Mach/vm-stat 页集合，bytes | 唯一安全算术是全机已用 proxy `U=M-A`。候选需求 `D_mem` 是每轮相对 pre-spawn `U0` 的最大正增量，再取五轮/coverage 上界。owned footprint、MPS current/driver 都是诊断视图，不与 `U`、`D_mem` 相加 | C：`U_now <= (1-H)*M` 且 start guard 通过。P：再要求 `U_now + (D_mem+E_mem) <= (1-H)*M` | 任一 50 ms sample 满足 `U_t > (1-H)*M` 或 `A_t < H*M`，在发现后 50 ms 内发 authenticated cancel；从实际越界到发送最坏 100 ms | page-size/total 变化，gauge 缺失、非整数、负数或 `A>M` 即拒绝/中止；页数正常增减允许 |
| MPS 诊断包络 | broker 自报 current/driver/recommended bytes | 只做归属和回归包络，不表示全机 free VRAM，不与统一内存相加 | C：`min(A_now,recommended_now)` 满足 start-guard floor，记录 gauge 但不读 P。P：再要求 device/model/generation 与 P 匹配 | C：只记录 D/E，安全由统一内存主视图中止。P：driver/current 超过 P 中 `D_mps+E_mps` 时在发现后 50 ms 内取消并记 regression | 非 reload 状态的 telemetry gap、非整数、未授权 generation 变更或 recommended 缺失即拒绝/中止；gauge 增减允许 |
| CPU | `host_processor_info` ticks 和 monotonic time；容量 `K_cpu=online logical CPUs` core-equivalent | 全机 active core-equivalent 是安全主视图；分别保留 100 ms/1 s 窗口。pre-spawn 全机活跃值为 `B_cpu`，profile 保存候选 owned CPU 的 `D_cpu+E_cpu`，不再加全机增量 | C：两窗口 `B_cpu <= (1-H)*K_cpu`。P：再要求 `B_cpu + (D_cpu+E_cpu) <= (1-H)*K_cpu` | 任一完整窗口的 whole-host active `> (1-H)*K_cpu` 时，下一个 50 ms 周期内发送取消 | cumulative tick 回退、online CPU 变化、窗口不完整或 owned PID 无法归属即拒绝/中止 |
| swap | `vm.swapusage` 的 used bytes；Mach/vm-stat 累计 swapins/swapouts pages | `swap_used_0`、`swapins_0`、`swapouts_0` 在 preflight 冻结；used 是当前占用，counter delta 是新活动 | preflight 1 s 内两个 counter 无增量，且 `swap_used_0` 不超过授权的 background 上界 | 任何 `delta(swapins)>0`、`delta(swapouts)>0` 或 `swap_used_t>swap_used_0` 立即触发取消；发现后 50 ms 内发送 | sysctl/counter 不可读或回退即拒绝/中止 |
| OS memory-pressure 事件 | 专用 native helper 的 `DispatchSourceMemoryPressure` WARN/CRITICAL 事件与 monotonic timestamp | 只是独立 tripwire，不从 VM counters 伪造“OS pressure”。初始状态记为 `NO_EVENT_YET`，不写成 NORMAL；启动安全仍由 20% 统一内存主视图决定 | helper/source 创建成功且 heartbeat 正常；不要求伪造的初始 NORMAL 事件 | WARN 或 CRITICAL callback 后 50 ms 内发送取消 | helper/source 创建失败或两个 heartbeat（100 ms）未到即拒绝/中止 |
| sampler 与时钟 | 50 ms 主通道、25 ms 校准通道，同 monotonic clock | 任何判定只用完整窗口；25 ms 仅用于得出 `E` 和峰值别名上界 | 校准通过且没有 >100 ms gap | 运行期 gap >100 ms、时钟回退或原始样本无法 fsync 时立即取消 | 不做插值，该轮 `INVALID` |
| GPU/MPS 归属 | owner tree、broker claim/generation、授权窗口的已知进程快照 | 只承认已证明归属的 broker metrics，冻结 `device_gpu_capacity_claim=false`；不从主机空闲推断 whole-device 归属 | broker 所有权闭合，已知未授权 Metal/MPS consumer 为零，background 在授权包络内 | 发现已知 foreign consumer、background 越界、claim 丢失，或出现未授权/跳代/重叠 generation 时取消；符合 reload intent 的精确 `+1` 不取消 | broker 归属无法证明，或 caller 请求 whole-device GPU 结论时 `GPU_ATTRIBUTION_UNKNOWN`，不进 Q |

authenticated cancel 发送后，实际 stop 必须在既有 cleanup deadline 内收敛，发现延迟、发送延迟和
stop 延迟分别记录。任何安全中止都不进 normal/product 分母，也不继续升 N。

### 10.6 promotion 和 retry 资源关系

重建的 `ExactNQualificationProvider` 和 `ResourceBudgetProvider` 是跨平台公共接口，但 Q/P 必须绑定
platform measurement profile/hash、原始样本 B、candidate R、exact N 和 coverage policy。Linux 与
Darwin 的 Q/P 不能互换。独立审查和 operator approval 生成 M，安装后读回生成 D；
`FixedProductionContext` 仍要求 P/Q/R/M/D 全部一致。

v5 retry 的业务 `RetryQualification` 不能替代 exact-N=1 资源 Q。生产 retry 同时要求已批准
Darwin N1 resource P/Q/M/D 和已批准 `RetryQualification`。候选 retry 只能在一次性
`MeasurementRetryContext` 与 Darwin measurement safety envelope 中运行，不得用它生成 production context。

### 10.7 资源子系统验收

- 先用测试证明退役入口仍 fail closed，新 measurement factory 只接受 sealed authority；
- 使用 fake Darwin APIs 覆盖 counter 换算、PID 复用、broker generation 漂移、telemetry gap、swap/pressure、
  foreign GPU 不可归属和平台 profile 交叉拒绝；
- 算术合同覆盖：20% 相等边界通过、差 1 byte/tick 拒绝；统一内存 `U` 不与 owned/MPS
  指标重复相加；100 ms/1 s CPU 窗口分判；swap used 不变但 counter 增长仍中止；
  pressure 初始 `NO_EVENT_YET` 不冒充 NORMAL；>100 ms 丢样不插值。
- 准入合同覆盖：无 P/Q 但有 sealed authorization 的首轮 candidate 可启动，production 在同一条件下
  因 P/Q 缺失拒绝；gauge 正常分配/释放的增减可接受，monotonic counter 回退拒绝。
- reload 合同覆盖：已提交 intent、旧 owner 退出、精确 generation+1、同模型/device 在 deadline 内恢复；
  无 intent、跳代、旧新重叠、配置漂移或超时均中止。reload 窗口没有伪造的 broker sample。
- live 前做 50/25 ms 校准，不通过时不启动 20 点；
- N1/N2 各自完成授权数量内的有限样本、coverage 和 fault，生成带 Darwin profile hash 的 B/Q/P；
- 资源数字、误差和包络只从当前 mac-mini 实测得出，设计文档不预填阈值；
- Stage D 依次审查 raw manifests、Q/P、parser/provider 和 deployment readback，未批准的 N/profile
  不能获得 `FixedProductionContext`。

## 11. 测试与验收

### 11.1 自动化合同测试

- v4 bytes/解析和 exact-W2 拒绝行为不变。
- v5 只接受单点、N=1、`SEQUENTIAL`、`FULL_RESTART_RETRY`、Darwin/MPS。
- v6 只接受 W1、`SEQUENTIAL`、`FIRST_PASS`、Darwin/MPS；资格运行要求 20 点。
- first-pass 请求不能选择 v5；retry 不能选择 v4/v6；W2 不能选择 v6。
- `FirstPassSelectionBinding` 强制 4–20 点与四 anchor；`RetrySelectionBinding` 强制单点来源链，
  且不执行 anchor 包含检查；两类 binding 交叉使用必须拒绝。
- 非默认、非前两个点的 selection 能驱动对应执行；所有 selected 点各执行一次，
  unselected 点为零次，没有重复 lease/result；N1 只执行指定失败点。
- runtime closure 对 ABI、library origin、config hash、canonical prefix 污染 fail closed。
- journal/reducer 覆盖单 writer 拒绝、epoch 接管、幂等重放、proposal/ACK、journal/watermark
  fsync failure、result 原子提交中断、partial tail 的 live/strict 差异、
  hash tamper、sequence gap、终态后非法追加、result 越界/symlink，以及 reducer+cursor 事务回滚。
- 在 journal `flush` 后、`fsync` 前阻塞 writer 时，live reader 看不到新 sequence；fsync 失败时
  不产生 terminal、不推进 cursor、不解除 fence。watermark 落后的完整 frame 也不投影。
- 服务重启从 accepted cursor 恢复全量 reducer state，不重复统计 attempt。
- retry 覆盖重复 command、原 batch cleanup 未完成、非业务失败、lease 失效、active/unknown
  owner、spawn 未知结果和事务后启动失败。
- 无 `RetryQualification` 但有有效 `MeasurementRetryContext` 时可执行；两者都没有时拒绝；
  measurement/production context 混用、重放、过期或绑定漂移均拒绝。
- cancel、exception、timeout、adapter/worker/station `SIGKILL` 后不遗留已证明归属的 descendant；
  无法证明的 PID 不会被误杀，fence 不会误解除。

所有修复先有能稳定失败的 RED，再进入 GREEN。依赖、动态库或测试 runner 启动失败不算 RED。

### 11.2 Station live gate

在五个连续 `FULL_RESTART` 中，每轮都要求：

- `RuntimeClosureIdentity` hash 不变，每轮 `RunBinding`/`RuntimeAttestation` 唯一且验证通过；
- `list_controllers` 可调用，三个 controller 为 `active`；
- MoveIt service/action ready；
- fresh ROS domain 和 station session；
- 退出后 service、station、worker、IPC residue 均为零。

### 11.3 Candidate service-driven W2 gate

- 在明确标注的 candidate/measurement context 中，统一服务 API 启动 v4 W2 first pass；
- 两个 Worker 与两套 station 同时存在，实际 N=2；
- 使用包含非前两点的 selection，selected 点均有且只有一个真实 pick-place attempt，
  unselected 点没有 lease、MoveIt 执行或 result；
- point status 与 execution phase 分轴投影，terminal 与已验证物理 result 一致；
- 服务 projection 与 raw journal/result manifest 一致；
- fresh Chrome 看到进度、终态和证据；
- cleanup event、进程扫描和 registry 一致。

### 11.4 Candidate service-driven W1 first-pass gate

- 在 `MeasurementContext` 中使用 v6 运行一个 20 点普通 N1 first-pass；
- manifest 显示 actual worker count 始终为 1、`FIRST_PASS`、`FULL_RESTART`、同 candidate R；
- 20 个 selected 点各有且只有一个真实 pick-place attempt，资源、物理与 cleanup 证据闭合；
- 运行可作为 Stage C 普通 N1 样本，但在聚合器、覆盖和连续样本门禁通过前不构成资格。

### 11.5 Candidate N1 retry gate

- 先通过受控 fault injection 验证失败分类和拒绝路径；这只是功能测试，不计入
  正常业务成功率或资格样本。
- retry live gate 使用一个已完成 terminal-clean 且具备真实业务 `FAILED` result 的 first-pass 点；
- 受限 measurement service entry 携 `MeasurementRetryContext` 发起一次单点 retry；
- manifest 显示 `SEQUENTIAL`、N=1、`FULL_RESTART_RETRY`、fresh FULL_RESTART；
- 只有指定 point id 发生一次真实 pick-place attempt，其他点为零次；
- retry 使用独立 batch、journal、证据和统计；
- Web 显示 first-pass 与 retry 两层结果；
- cleanup 后无进程和 IPC residue。

### 11.6 资格顺序与独立 retry 资格

资格不得形成“先用生产资格跑验收，再用验收生产资格”的循环。顺序固定为：

1. 代码、config 和 copied install 冻结后生成 candidate execution identity R。
2. operator 只授权受限的 `MEASUREMENT` context；该 context 使用与生产相同的 parser、owner、
   runner 和 reducer，但 API 与证据都明确标记为 candidate，不冒充 `FixedProductionContext`。
3. station/W2/W1 功能 gate 通过后，Stage C 按新 R 建立 P/Q/R 和可支持 exact N 的
   版本化预算。普通 N1 使用 v6，先完成现行 20 点合同；之后再测 W2。
4. v5 retry 不借用普通 N1 的 20 点资格，而是建立独立 `RetryQualification`：固定 v5 config/profile
   hash，覆盖 parser 拒绝、单点 selection、owner/crash cleanup、projection 恢复，并完成五轮
   连续有效的 W1 `FULL_RESTART_RETRY` live run。这五轮分别由精确绑定的一次性
   `MeasurementRetryContext` 授权；每轮使用独立 batch/run binding，且只能重试真实业务失败点。
5. Sol/high 审查测量结果，Astra/high 独立审查 profile/proposal/parser；操作员明确批准
   exact N、profile SHA、M/D 和 retry qualification 后，才生成 `FixedProductionContext`。
6. 只有上一步完成后，才使用 production Web API 运行最终 live gate。

任何 runtime byte、selection/queue/reducer 语义、profile 或 parser 变化都产生新 R，并使相关 P/Q/M/D
失效。未测量、coverage 不全或资源归属不明的 N 保持 disabled。

实施计划需要同步修订旧预算文档的明确边界：

- `docs/superpowers/specs/2026-09-18-so101-parallel-unbounded-queue-resource-budget-design.md`
  第 5–6 节：把已退役链记为历史，增加第 10 节的 Darwin profile；普通 N1 使用 v6，
  `RetryQualification` 使用 v5 专用 provider，Linux 强制前置不套用到 macOS。
- `docs/superpowers/plans/2026-09-18-so101-parallel-unbounded-queue-resource-budget-implementation.md`
  Task 13：把“先 N1”绑定到 v6/20 点；Task 15 的 R01 producer 只接受已批准 v6 N1，
  不再使用 v5 retry 或等价假设代替。

## 12. 迁移顺序

1. 冻结当前 19 个本地提交与 CP-175 证据，不改写历史结论。
2. 完成 controller-manager 分层 A/B 和直连/DDS 观测，给出有证据的根因；实现 closure
   identity、run binding 和 attestation，先让 station 稳定 READY。
3. 实现 `SelectionBinding`、共享点位队列和 Worker 单点合同，先用非默认点位证明
   Web selection 真正驱动执行。
4. 扩展现有 `CoordinatorJournal`、source adapter 和唯一 reducer，验证原子 projection/cursor 恢复。
5. 新增 schema v5/v6、W1 composition、typed retry admission 和所有权树恢复。
6. 重建 sealed measurement、Darwin probe/sampler、exact-N provider、candidate P、promotion/deployment 链；
   先通过全部离线合同测试，旧退役 CLI 仍 fail closed。
7. 冻结代码、config 与 copied install，生成 candidate R；之后不再把旧资格带入本轮。
8. 在受限 `MEASUREMENT` context 中完成 Darwin 50/25 ms 校准和 station、W2/W1 first-pass、
   N1 retry candidate gates。
9. 按第 11.6 节重跑 Stage C，完成独立 `RetryQualification`，再进入 Stage D 审查与
   操作员批准。
10. 只有 `FixedProductionContext` 生成后，才运行 production Web live gate。

步骤 2 未通过时可完成后续离线测试，但不能声明 live 闭环。步骤 3–6 任何一项改变
执行 bytes 或语义后，都必须返回步骤 7 生成新 R。

## 13. 未采用的方案

### 13.1 直接放宽 v4 为 N=1 或 N=2

拒绝。v4 是已经冻结的 exact-W2 平台声明。原地放宽会让旧配置看似兼容，却改变其执行集合，
并模糊 N1 与 N2 的独立资格。

### 13.2 在 Linux/CUDA 上单独完成 N1 retry

可作为临时验证，但不作为本设计的最终验收。跨主机会扩大 lease、运行身份、证据位置和恢复
边界，无法证明 macOS Web 服务的本地完整流程。

### 13.3 服务轮询 `campaign-result.json`

拒绝。终态文件没有可靠的 live sequence、attempt 边界和 crash-recovery cursor。轮询只能得到
最终摘要，无法成为权威 projection。

### 13.4 为 macOS 写一套无事件协议的专用页面 reader

拒绝。这样会把平台差异带进 Web，并形成第二套状态机。平台差异应止于 execution profile 和
projection source，canonical projection 之后保持一致。

## 14. 完成定义

只有以下条件全部满足，这组阻塞链路才算关闭：

- station 在五次连续 FULL_RESTART 中稳定 READY，闭包身份一致、run/attestation 独立，
  controller 和 MoveIt 证据完整；
- 服务驱动的 W2 first pass 把全部 selected 点各执行一次真实 pick-place，unselected 点为零次，
  并在 Web 中正确投影；
- v6 W1 first-pass 完成普通 N1/20 点 Stage C 门禁，不借用 retry 证据；
- 同一服务只对指定业务失败点完成 N1 `FULL_RESTART_RETRY`；最终 Web 调用使用
  `ProductionRetryContext`，候选采样使用 `MeasurementRetryContext`；
- first-pass、retry、projection、cleanup 和 raw evidence 的身份与 hash 一致；
- journal terminal/cursor 只到 durable committed watermark；flush 后、fsync 前的 frame 不会投影；
- 重建的 Darwin measurement/qualification 链已产生 N1/N2 的 B/Q/P/M/D，不依赖
  Linux `/proc`/cgroup/NVML 假设；
- 所有相关测试 GREEN，fresh Chrome/GUI 证据属于本轮；
- service、station、Worker、broker 和 IPC 无残留；
- ledger 写入新 checkpoint，retained、archived 和 deletion candidates 已分类；
- candidate R 已完成对应 Stage C 与 `RetryQualification`，并经 Stage D 审查/批准生成
  `FixedProductionContext`；未获 promotion 的 N/profile 继续禁用；
- 最终 production Web live gate 只在上述生产上下文中运行，不用 candidate 结果冒充生产验收。
