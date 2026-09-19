# SO-101 macOS MPS 与私有 IPC 兼容设计

## 1. 背景

当前 `codex/so101-unbounded-queue-resource-budget` 分支以提交
`bf1b609157826bbcc18985959239c718c724d09e` 为设计基线。现有轻量 start guard、共享
Broker 和 exact Worker 数量管理已经去掉 per-N 认证预算，但运行时仍有两处 Linux/NVIDIA
假设：

- 加速器准入依赖 NVML，`requested_device` 只接受 `cuda`；
- IPC 地址依赖 `/proc/self/fd/<dirfd>/<basename>`，Darwin 无法使用同样的 bind 方式。

因此，现有实现可以通过便携性单元测试，却不能在 Apple Silicon 上启动真实的 MPS W2
流程。本设计新增闭合的 schema v4，同时冻结 schema v3 的 CUDA/NVML 语义。首期只声明
macOS exact `worker_count=2` 的功能和稳定性，不从 W2 外推 W4、W6、W8 或其他 N 值。

## 2. 已确认的产品决策

本设计采用以下已确认约束：

1. macOS IPC 使用私有短路径 AF_UNIX socket，不改为 TCP，也不重构为继承
   `socketpair`。
2. macOS IPC 验证保持轻量。访问控制只依赖文件系统权限：私有目录 `0700`、socket
   `0600`。
3. Client 不校验 endpoint receipt、inode、peer credential、token、generation 或 lease；
   获得 socket 路径且能 `connect()` 即可发起请求。
4. Server 不校验 token、generation 或 lease，这些字段不进入 v4 IPC 请求协议。Server
   只校验帧大小、消息结构、操作类型、deadline 和有界队列容量。
5. Broker 是不可信的本地推理计算服务，只负责模型加载、排队和推理，不拥有机器人动作、
   controller、lease、journal 或最终结果判定权。
6. Coordinator 继续保留运动授权、安全取消、当前请求映射、迟到结果拒绝、精确 owned
   Broker 停止与回收、资源清理和证据登记。
7. 没有真实硬件授权。本设计只覆盖受控的单用户 macOS 仿真环境，不把同 UID 的恶意进程
   作为防护目标。

第 3、4 项是有意放宽的信任边界：任何能访问私有 socket 的同 UID 进程，都可能提交合法
格式的推理请求、占满队列，或调用 Coordinator 当时状态机允许的控制操作。状态机仍拒绝
顺序错误、非 active point、重复 consume 和不满足 controller 安全条件的操作，但不区分同
UID 调用方身份。该风险只在单用户、task-owned 仿真环境中接受；多租户主机、不可信本地
用户或真实硬件环境必须另行设计认证机制，不能直接复用本方案。

## 3. 范围

### 3.1 本期范围

- Apple Silicon 上的真实 PyTorch MPS 模型加载、warm-up 和推理；
- exact W2：两个 Worker 共享一个 Broker 和一组模型实例；
- MPS 单执行 lane，允许两个 Worker 并发排队，不并发执行 Metal 推理；
- 私有短路径 AF_UNIX IPC；
- lightweight start guard、campaign 级 MPS 互斥、安全取消和 owned process cleanup；
- W2 功能正确性、失败恢复和五次连续 `FULL_RESTART` 仿真稳定性；
- 保持 schema v3 CUDA/NVML 行为不变。

### 3.2 明确不做

- 不运行或声明 W4、W6、W8；
- 不恢复 N1–N8 certified budget、provider 或 promotion；
- 不把 swap、PSI、源码 commit 或 ament prefix 加回运行时准入；
- 不允许 CPU fallback；
- 不使用任意 TCP 端口、外部 socket root 或用户提供的任意 endpoint；
- 不授权真实硬件、sudo、全局驱动修改、foreign process stop 或证据删除；
- 不在本轮执行 Linux 回归。当前没有可用 Linux 环境，相关任务在后续实施计划中必须标为
  `DEFERRED_ENVIRONMENT`，待 Linux 环境 ready 后再执行。

## 4. 总体架构

### 4.1 平台接口

新增两个小型平台接口，避免在 Coordinator、Broker 和 Worker 中散布平台判断：

```text
AcceleratorProbe
  probe(config) -> AcceleratorSnapshot

UnixAddressStrategy
  create_campaign_root() -> CampaignIpcRoot
  endpoint_path(root, role) -> Path
  validate_encoded_length(path) -> None
  cleanup_registered_endpoint(endpoint) -> CleanupReceipt
```

平台映射如下：

| 平台 | 加速器 | IPC 地址策略 | MuJoCo GL |
| --- | --- | --- | --- |
| Linux | CUDA/NVML | `ProcFdUnixAddress` | `egl` |
| macOS | MPS | `DarwinPrivatePathUnixAddress` | `cgl` |

schema v3 只保留原有 Linux CUDA/NVML 组合，不改变含义。schema v4 支持上述两个闭合组合；
任何交叉组合、未知字段或 CPU fallback 都 fail closed。

### 4.2 责任边界

```text
Coordinator
  ├─ start guard 与 MPS campaign claim
  ├─ Worker/请求生命周期与一次性结果准入
  ├─ controller 动作与安全取消
  ├─ 当前 request_id 映射和迟到结果拒绝
  └─ Broker/IPC/claim 精确清理

Worker 1 ─┐
          ├─ AF_UNIX ─> Broker ─> 单一 MPS execution lane
Worker 2 ─┘              └─ 一组共享模型实例
```

Broker 的响应只能是推理数据，不能直接触发机器人动作。每次推理前，Worker 通过既有
Coordinator 控制通道申请一个不复用的 opaque `request_id`。Coordinator 把它原子绑定到
`slot_id`、point、attempt、model、输入快照 SHA、deadline 和当前 owned Broker 的
PID/出生身份；这些绑定只存在于 Coordinator，不发送给 Broker。

Broker 仍把响应直接返回 Worker。Worker 必须把 `request_id`、响应摘要和模型输出契约提交给
Coordinator 执行一次性 consume；只有 consume 成功，结果才可进入 Worker 本地的 RGB-D
时间、TF、geometry、pose admission 和动作门。consume 与 cancel/timeout 在同一个锁边界内
互斥，成功后立即移除记录。未知、重复、已取消、已超时、输入快照不匹配或属于旧 Broker
PID/出生身份的结果一律丢弃并记录。Broker 替换时，Coordinator 先失效绑定到旧 Broker 的全部
请求，`request_id` 在整个 campaign 内永不复用。

这里的 Coordinator 控制通道同样采用 v4 的 OS 权限型 transport：消息不携带 token、
generation 或 lease，Server 也不校验这些字段。Coordinator 仍校验本地状态机的操作顺序、
active point 和一次性 consume；这些是机器人动作安全条件，不是调用方认证。

## 5. schema v4 配置

macOS 首期配置为：

```yaml
schema_version: 4
accelerator:
  kind: mps
  selector: default
requested_device: mps
allow_cpu_fallback: false
worker_count: 2
ipc_transport: darwin_private_path_unix
mps_process_memory_fraction: 0.8
start_guard:
  mps_minimum_headroom_bytes: 1073741824
```

约束如下：

- `worker_count` 必须精确为 `2`；其他值返回
  `PLATFORM_WORKER_COUNT_UNSUPPORTED`。
- `mps_process_memory_fraction` 必须位于 `(0, 1]`，在任何 MPS allocation 前设置。它是单个
  Broker 的 allocator 上限，不是按 Worker 数推导的资源预算，也不能用来宣称跨 N 资格。
- `mps_minimum_headroom_bytes` 必须是正整数，首期固定默认值为 `1 << 30`。它只拦截明显不足
  的启动状态，不随 Worker 数量、模型数量或 N 值缩放，也不是容量认证。
- `ipc_transport: auto` 只能解析为当前平台的闭合默认值：Linux 解析为
  `proc_fd_unix`，macOS 解析为 `darwin_private_path_unix`。
- manifest 必须记录解析后的 accelerator、IPC transport、GL backend 和 exact
  Worker 数量，不能只记录 `auto`。

## 6. MPS start guard 与 Broker 生命周期

### 6.1 轻量准入

Coordinator 在每个 campaign 启动前只运行一次 start guard。计时从尝试取得 claim 开始，到
snapshot 评估和 helper cleanup 完成结束，总耗时不超过 2 秒：

1. 启动轻量 `CampaignSupervisor`，非阻塞取得 campaign 独占的 `MPS:DEFAULT` flock，并检查
   上一 campaign 的 durable ownership receipt 没有未闭合的 owned process、controller goal
   或 IPC endpoint；
2. 确认 `torch.backends.mps.is_built()` 和
   `torch.backends.mps.is_available()` 均为真；
3. 读取 `torch.mps.recommended_max_memory()`；
4. 从 `vm_stat` 读取 host 可用统一内存；
5. 以 `min(host_available_memory, mps_recommended_max_memory)` 作为启动 headroom；
6. 要求 headroom 不小于 `mps_minimum_headroom_bytes`；
7. claim、残留检查、probe 和阈值比较全部通过后，才允许 spawn Broker 与 Worker。

所有 helper 调用只得到剩余 deadline；超时、输出缺失、单位非法、helper 无法 terminate/reap 或
ownership receipt 无法证明旧资源已清理，都返回 fail-closed 结果，不启动模型、Worker 或仿真
stack。RAM 的既有 host 下限继续独立检查，不能把 unified-memory proxy 填入 v3 的
`gpu_free_bytes` 评价路径。

`torch.mps.current_allocated_memory()` 和
`torch.mps.driver_allocated_memory()` 只作为诊断指标记录。它们不表示全机 free VRAM，也不参与
启动阈值计算。MPS 的准入结论必须标注为 unified-memory proxy，不能包装成 NVML 式设备级
显存证明。

`CampaignSupervisor` 在 start guard 期间取得 claim，PASS 后继续持锁。它不是 Coordinator
创建子进程后的旁路 helper，而是 Broker 和两个 Worker 的实际 parent、spawner 与 reaper。
每次 spawn 前，Supervisor 先把包含 role、预期启动参数和 receipt nonce 的 `SPAWNING` intent
原子写入 durable ownership receipt；child 必须在执行模型、连接 controller 或进入任务循环前
回报 PID/出生身份/进程组并取得 registered ACK，Supervisor 才把 intent 改为 `ACTIVE`。未取得
ACK 的 child 不得运行；超时后由 Supervisor 精确停止并 `waitpid`。任何未决 `SPAWNING` intent
都阻止下一 campaign。

Coordinator 只向 Supervisor 提交闭合的 spawn/stop 请求并发送心跳，不直接成为这些 child 的
parent。正常结束时，Supervisor 执行并核对 cancel、reap 和 live readback 后再清空 receipt、
释放 claim。Coordinator 异常退出时，Supervisor 进入有界恢复：先请求 Worker 安全停止，再
精确停止、reap 自己创建的 owned child；不能证明 controller goal absence 或清理完整时，保留
durable ownership receipt 并拒绝新 campaign。若 Supervisor 自身异常退出，残留 receipt 和
其中每个已登记或未决 intent 同样阻止新 campaign，不能据此停止 foreign process。第二个
campaign 必须在任何模型、Worker 或仿真 stack spawn 前失败。

### 6.2 Broker 启动

- 使用 multiprocessing `spawn`，禁止在父进程初始化 MPS 后再 `fork`。
- 一个 Broker 只加载一组真实模型，由 W2 两个 Worker 共享。
- Coordinator 构造 Broker 环境时拒绝继承
  `PYTORCH_ENABLE_MPS_FALLBACK=1`，并在导入 PyTorch 前固定
  `PYTORCH_ENABLE_MPS_FALLBACK=0`。Broker bootstrap 在 import 前再次读回；值不是 `0` 就
  fail closed。
- 设置 `mps_process_memory_fraction` 后加载模型，执行真实 warm-up 输入，再调用
  `torch.mps.synchronize()`。
- warm-up 和同步都成功后，Broker 才发布 ready receipt；仅进程存活或 socket bind 成功不算
  ready。
- 所有模型共用一个有界 MPS execution lane，不能沿用“每模型一个 executor thread”来形成
  并发 Metal 调用。两个 Worker 可以同时排队，但不能由本设计宣称并行 Metal kernel 带来
  性能提升。

ready receipt 至少记录：

- Broker PID 与进程出生身份；
- `runtime_device=mps`；
- 模型、配置和权重 SHA；
- `recommended_max_memory`、`current_allocated_memory`、
  `driver_allocated_memory`；
- `mps_process_memory_fraction`；
- `PYTORCH_ENABLE_MPS_FALLBACK=0`、PyTorch 版本和 bootstrap 检查结果；
- 每个模型的 warm-up latency、输出 shape/dtype 和同步结果。

允许 RGB 解码、shape 整理等明确列出的 CPU 预处理，但模型算子不得回退到 CPU。任何模型参数
或预期张量未在 MPS、fallback 环境不合规、设备字符串不一致、warm-up 异常或同步异常，都
必须阻止 ready。关闭 PyTorch fallback 后出现 unsupported MPS operator，按真实兼容性失败
处理，不能偷偷改用 CPU。

### 6.3 超时、OOM 与恢复

Broker 不提供没有认证的远程 cancel RPC。发生 request timeout、Broker OOM 或 Broker crash
时，Coordinator 按以下顺序处理：

1. 从本地 active request table 移除受影响的 `request_id`，停止接受其结果；
2. 将 in-flight point 标记为基础设施失败，不伪装成业务失败；
3. 对两个 Worker 执行安全停止；对已经进入运动阶段的 Worker 执行 controller cancel，并确认
   controller goal 已消失；
4. 按 PID、进程出生身份和进程组精确终止、reap 当前两个 Worker 与 owned Broker；
5. 创建新的随机 campaign IPC 路径并重新 spawn、warm-up Broker；
6. Broker 新 ready receipt 生效后，使用新路径重新 spawn 两个 Worker；
7. 两个新 Worker 都 ready 后，由 Coordinator 决定是否按既有 `FULL_RESTART` 策略重新排队。

Broker 故障采用整个 W2 pool 重建，不让存活 Worker 动态发现或校验新 endpoint。这样 Client
仍只从启动参数取得路径，也没有 endpoint receipt/inode/peer 校验。不在线程内部尝试强杀
阻塞的 Metal 调用，也不根据进程名、端口、镜像或启动时间模糊清理。

## 7. macOS 私有 IPC

### 7.1 路径布局

固定使用 canonical 路径，不使用 `$TMPDIR`、长 evidence root 或 `/tmp` alias：

```text
/private/tmp/so101-ipc-<uid>/
  b-<random-short-id>/
    coordinator.sock
    broker.sock
    w1.sock
    w2.sock
```

约束如下：

- `/private/tmp` 必须是 root-owned sticky directory；
- `so101-ipc-<uid>` 和 campaign 目录必须由当前 UID 拥有、mode 为 `0700`，且不是 symlink；
- socket 创建后设置为 `0600`；
- path 编码后的字节数连同终止 NUL 必须小于运行平台
  `sockaddr_un.sun_path` 的实际容量；不依赖字符数估算；
- campaign 目录使用随机短 ID，每次 restart 都创建新目录；存在冲突时 fail closed，不复用旧目录，
  也不自动删除冲突对象。

Coordinator 在本地 registry 中记录 endpoint path、role、创建时间、owned process PID/出生
身份和用于 cleanup 的文件身份。该 registry 用于精确清理和审计，不向 Client 提供认证语义。

### 7.2 请求协议

v4 transport 适用于 Coordinator、Broker 和 Worker 的 task-local AF_UNIX endpoint。请求的
公共 envelope 只保留路由、时限和 payload：

```text
request_id
operation
deadline_monotonic_ns
payload
```

v4 response 至少包含：

```text
request_id
status
output_descriptor | error
timing
```

协议中不包含 token、Broker generation 或 lease。Client 不读取 endpoint receipt，不做
`stat()`、inode、peer UID/PID 或 socket replacement 校验；它从 Coordinator 启动参数获得
路径，直接 `connect()` 并发送请求。Server 不查 token、generation 或 lease，只做以下有限
验证：

- frame 不超过固定上限；
- schema 完整且字段类型正确；
- `operation` 在闭合 allowlist 中；
- deadline 尚未过期；
- bounded queue 尚有容量。

Coordinator/Worker 控制操作仍要通过本地状态机的顺序、active point、一次性
`request_id` consume、controller 状态和结果完整性条件，但不根据调用方提供的 token、
generation 或 lease 授权。无法访问私有目录的进程不能连接；拥有同 UID 和 IPC 路径的进程
视为已获访问权限。

### 7.3 推理输入快照

推理 payload 使用 task-owned、不可变的 snapshot 文件，不把 RGB-D 原始数组塞进控制帧，也
不引入跨平台共享内存。`input_descriptor` 至少包含：

```text
relative_path
size_bytes
sha256
shape
dtype
encoding
frame_timestamp
```

Broker 启动时只获得一个 campaign-owned input root。`relative_path` 必须位于该 root 下；
descriptor 不能使用绝对路径、`..`、symlink 或超出配置上限的文件。Worker 先把 snapshot
完整写入临时名，fsync 后原子改名并封存，再向 Coordinator 登记 SHA；Broker 打开文件后核对
regular file、size、SHA、shape 和 dtype，读取完成后关闭。snapshot 至少保留到请求完成、取消
或失效并取得 readback，之后才列入 deletion candidate，未经授权不删除 evidence。

“正常 request path 不做文件系统访问”仅指不为 endpoint 认证执行 `stat()`、receipt、inode
或 peer 检查；读取并验证 `input_descriptor` 指向的 task-owned snapshot 是数据平面的一部分。
`broker_max_frame_bytes` 限制控制帧，另用 `max_input_snapshot_bytes` 限制 descriptor 指向的
数据，二者都必须在读取或排队前检查。

### 7.4 重启与清理

- Broker restart 必须使用新的随机 campaign 目录，不能在原 socket path 上重新 bind；两个
  Worker 也必须停止并使用新路径重建，不支持存活 Worker 动态切换 endpoint；
- 旧连接随 owned process 退出而断开；Coordinator 通过本地 active request table 拒绝旧请求
  的迟到结果；
- cleanup 只处理 registry 中的精确 endpoint 和空 campaign 目录；
- 禁止 glob、扫描其他 campaign、按名称匹配进程或删除未知对象；
- 证据文件保留，base 目录可以留存供后续 campaign 使用；
- cleanup receipt 必须记录逐个 endpoint 的结果和最终 live readback。

## 8. 轻量 macOS IPC 验证

macOS IPC 验证聚焦功能和资源边界，不引入重型多租户安全测试：

1. 在 canonical 私有短路径创建 Broker socket；
2. 两个 Client 同时连接并完成最小 round-trip；
3. 验证 malformed frame、oversized frame、未知 operation、过期 deadline 和 queue full 均被
   拒绝；
4. 断开并精确清理 owned socket；
5. 用新随机路径重启 Broker，确认旧路径不可用；
6. 重建两个 Worker，确认二者都只能通过新路径产生结果；
7. 让旧 `request_id` 产生迟到或重复结果，确认 Coordinator 的一次性 consume 拒绝；
8. 验证 snapshot path、size、SHA、shape/dtype 和上限，确认 path traversal、symlink、篡改或
   超大输入 fail closed；
9. 确认正常 RPC 路径没有 endpoint `stat()`、receipt、peer credential、token、generation 或
   lease 校验。

不要求 symlink race fuzz、peer credential matrix、token replay、generation replay 或 lease
replay，因为这些不再属于 v4 IPC 信任模型。目录权限、socket 权限和精确 cleanup 仍需单元测试。

## 9. 验收矩阵

### 9.1 macOS 本轮必须完成

- schema v3 冻结测试通过，证明本次修改没有重写旧配置语义；
- schema v4 MPS 配置、非法组合和 CPU fallback 的 RED/GREEN 测试通过；
- `PYTORCH_ENABLE_MPS_FALLBACK=1` 的继承环境在 import 前 fail closed，并保存 child env
  readback；
- MPS start guard、固定 headroom 阈值、2 秒 deadline、claim conflict、pre-spawn rejection
  和指标 provenance 测试通过；
- Coordinator 异常退出后，`CampaignSupervisor` 保持 claim，并完成 owned cleanup 或通过
  durable receipt 阻止新 campaign；
- Supervisor 在每个 child spawn 前持久写入 `SPAWNING` intent，child registered ACK 后才进入
  `ACTIVE`；未决 intent、ACK 超时和 Supervisor crash 都 fail closed；
- 私有短路径、权限、长度检查、两 Client round-trip、协议负面路径、restart 和 cleanup 测试
  通过；
- task-owned snapshot descriptor 的 path、size、SHA、shape/dtype、生命周期和数据上限测试
  通过；
- 真实模型在 MPS 加载、warm-up、`torch.mps.synchronize()`，ready receipt 与实际 device
  一致；
- exact W2 两个 slot 均产生进度、结果和独立 evidence，且共享一个 Broker/模型集合；
- request register/一次性 consume、queue full、inference timeout、Worker cancel、Broker
  crash 后整个 W2 pool 重建、迟到/重复结果拒绝和 controller goal absence 均有原始证据；
- fresh build/package/OpenAPI/copied-install/served-byte gate 在有效 macOS ROS 环境中完成；
- MoveIt shadow、controller/joints、MuJoCo pose/contact/detach/release/final placement 使用新
  epoch 证据；
- fresh GUI 证据按 snapshot/action/snapshot 取得；
- 冻结相同 commit、W2、点集、参数、成功契约和 lifecycle，完成五次连续有效
  `FULL_RESTART` 仿真成功批次；任何 INVALID 或提前终止都使该批次不计入 5/5，并在账本中
  单独记录。

只有以上 macOS 项全部满足，才可报告 `MACOS_MPS_W2_PASS`。它只证明 macOS exact W2，不证明
其他 Worker 数量、Linux 回归或真实硬件。

### 9.2 Linux 回归延后

当前没有可用 Linux 环境，因此本轮不执行 CUDA/NVML、`proc_fd_unix`、EGL、Linux package
或 Linux W2 回归。后续实施计划必须把这些任务写为独立 gate，并明确：

```text
status: DEFERRED_ENVIRONMENT
reason: no Linux environment available
resume_when: Linux CUDA/NVML environment is ready
```

延后期间：

- 不得把未运行写成 PASS、SKIP 或 N/A；
- 不得用 macOS MPS 结果替代 Linux CUDA 结果；
- 不得宣称 cross-platform、Linux regression 或发布资格完成；
- macOS W2 可以单独完成并形成 checkpoint，但总体状态必须保留
  `LINUX_REGRESSION_DEFERRED`；
- Linux 环境 ready 后，从该 checkpoint 执行 schema v3 CUDA/NVML、v4
  `cuda + proc_fd_unix`、真实 Broker device、package/CTest 和 exact W2 回归。

在 Linux 回归完成前，不基于本设计发布 main。若用户之后明确缩小发布范围，需要新的发布
决策，不能由执行器自行推断。

## 10. 证据与完成条件

实施阶段沿用一个已登记 evidence root，并保存：

- 配置、resolved manifest 和代码 commit；
- start-guard 原始快照、命令、时间、exit code 和 metric source；
- MPS claim、Broker ready、模型 provenance 和 warm-up receipt；
- IPC 路径、权限、长度、输入 snapshot、request register/consume、请求/响应和 cleanup
  receipt；
- exact W2 每个 slot 的进度、结果、取消和证据引用；
- controller goal absence、owned Broker reap 与 live process readback；
- 五次 `FULL_RESTART` 每次独立的物理、控制、视觉和最终 placement 证据；
- retained、archived 和 deletion candidates 清单，未经授权不删除。

以下情况都不能作为完成证明：仅有 tmux/进程存活、socket bind、单元测试截图、一个 20 点批次、
一个 Broker ready receipt、旧 epoch 证据，或没有实际执行的 Linux gate。

## 11. 后续实施计划要求

设计批准后再单独编写实施计划。计划必须：

1. 采用 RED→GREEN，小步修改 schema、platform probe、Broker、IPC 和 Coordinator；
2. 先保护 schema v3，再增加 schema v4，不在一次提交中混改全部边界；
3. 把 macOS 轻量 IPC、不可变输入 snapshot、一次性结果准入、campaign supervisor 和真实
   MPS W2 放在当前可执行阶段；
4. 把全部 Linux gate 独立列出并标记 `DEFERRED_ENVIRONMENT`，不在没有 Linux 环境时调度；
5. 规定每次代码变化使相关旧验收失效，必须重跑受影响的 macOS gate；
6. 在 Linux 环境 ready 后恢复延后任务，并在跨平台结论或发布前完成；
7. 不扩大到 W4/W6/W8、真实硬件、旧认证预算或 main 发布。

## 12. 参考资料

- [PyTorch MPS backend notes](https://docs.pytorch.org/docs/main/notes/mps.html)
- [PyTorch MPS environment variables](https://docs.pytorch.org/docs/2.14/mps_environment_variables.html)
- [torch.mps.set_per_process_memory_fraction](https://docs.pytorch.org/docs/main/generated/torch.mps.set_per_process_memory_fraction.html)
- [torch.mps.driver_allocated_memory](https://docs.pytorch.org/docs/stable/generated/torch.mps.driver_allocated_memory.html)
