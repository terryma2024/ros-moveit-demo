# SO-101 固定并行共享队列与逐档资源预算设计

日期：2026-09-18。状态：按独立审查 F1..F4、C1..C3 修订，待 GPT-6 Astra / High 复审；未授权执行。

首审记录保留在 [design-review](../reviews/2026-09-18-so101-parallel-unbounded-queue-resource-budget-design-review.md)。
首审结论 CHANGES_REQUIRED，不代表任何档位通过运行资格；所有 N 的预算仍为 NOT_MEASURED。

本设计按已批准范围编写。讨论、设计、实施计划和 guide 由 GPT-5.6 Sol / High
(`gpt-5.6-sol`, `high`) 完成；方案、设计、计划和 guide 由独立 GPT-6 Astra / High
(`gpt-6-astra`, `high`) 审查。后续执行只使用 ai-station 上 tmux 持有的 DeepSeek
Harness TUI，命令 `dst`；执行监控和结果审查使用 Sol / High。模型或工具不可用时明确报告，
不得静默替换。本轮只写文档，不启动 TUI、编码、测试、仿真、停止服务、部署或推送。

## 1. 目标与范围

固定批次只配置执行模式和 worker 数 N。移除 `max_points_per_worker`（下文简称 K），
包括 Web 输入、capacity 展示、capability、API、schema、CLI、配置、请求、contracts、
coordinator 配额检查和因 K 耗尽而触发的 `CAPACITY_EXHAUSTED`。不使用大整数、点位数、
`null` 或无限大去模拟 K。`lease_count` 继续作为累计统计，不参与准入、任务分配或终止。

| 场景 | 不变约束 | 新行为 |
| --- | --- | --- |
| SEQUENTIAL 首轮 | N=1 | 一个 worker 从共享队列逐点领取 |
| PARALLEL 首轮 | N 为 2..8，批内固定 | 全部 N 个 worker 启动；空闲者抢下一项；一个 worker 同时最多一项 |
| 首轮点位 | 最终点位数 4..20，包含 4 个固定点位 | 点位选择、catalog 和 manifest 生成规则不改 |
| 人工失败 retry | 单点、FULL_RESTART、N=1 | 独立 batch、独立统计和 cleanup，不含 K |
| ADAPTIVE | 原 affinity、fallback tiers、infra attempt 限额 | 仅兼容共享请求契约变更，不改其调度策略 |

“无上限”仅指 worker 累计领取次数没有业务配额。业务/基础设施 retry、timeout、隔离、
epoch、cleanup、控制 lease、broker queue 和 inference 限额均保持。批次硬超时仍为 5400s。
选择 N8 不保证 N8 已通过资格；未知或未达标档必须拒绝，并显示原因，不自动降成 N2 或 ADAPTIVE。

这是一个原子契约迁移，分为可审查的实现任务；它不是独立的模型选型或性能优化项目。
不改模型、仿真物理、抓取 policy、资源扫描冻结策略、真实硬件控制或全局模型配置。

## 2. 当前事实与证据边界

2026-09-18 从 Mac orchestrator 通过只读 SSH 核对 ai-station：canonical checkout
`/data/work/ws_moveit`，分支 `main`，HEAD
`147d64a199bdf9c9b360555e15ad6ae85804ac39`。tracked source 干净；只有旧 fixed-eight
proposal 和 operator-recovery guide 两份 untracked 文档。MuJoCo 子模块为
`e4c0241aee52a40727681bd5872c09bf814e941a`。本地 checkout 仅作为文档编辑场所，不能据此推断远端接口。

现场硬件观测为 24 个逻辑 CPU、`MemTotal=32583596 KiB`、RTX 5080
`memory.total=16303 MiB`、driver `595.84`。本次读到 `MemAvailable=28355832 KiB`、
GPU free `15335 MiB`。空闲值随负载变化，只是观察，不是任何档位的预算或资格。

现有门控有三处重复实现：

| 消费者 | 真实源码边界 | 当前问题 |
| --- | --- | --- |
| Web production | `src/so101_teleop/so101_teleop/expert_validation/production.py::_HostResourceProbe.probe` | 硬编码 N>3 拒绝和 CPU/RAM/GPU 公式 |
| CLI prepare | `src/so101_demo_py/src/cli/mujoco_parallel_batch.py::_prepare_live_headroom` | N>3 拒绝；N=3 强制历史 Task14 特殊证据 |
| allocator | `src/so101_demo_py/src/parallel_batch/resources.py::WorkerResourceAllocator._live_headroom` | 同样 N>3 拒绝和 N=3 特例；allocate 另有资源公式 |

历史 `parallel_batch_v1.yaml` 使用 CPU=4N、RAM=6+4N GiB、GPU free>=8 GiB、
`required_live_headroom_ratio=0.20`。`Task14LiveHeadroomVerifier` 校验的是历史
`task14_two_worker_live_headroom`，不能把它当成新 exact-N 资格。三处必须迁移到同一 parser、
同一版本/内容哈希、同一实时 probe 和同一 exact-N qualification provider，不能只删除 `>3`。

当前旧服务 PID `1264438` 仍运行原安装版本；两个旧 campaign 的恢复 receipt 已保留，
但在线 supervisor 仍阻断原 fences。落盘 receipt 不等于在线恢复完成。历史新恢复代码的
509 pytest/508 colcon PASS 是交接事实，不能代替新干净源码、安装和线上读回。

`dst` 入口为 `/usr/local/bin/dst`，安装 metadata 版本 `0.10.2`，入口解析到
`/usr/local/lib/node_modules/@deepseek-harness-tui/dsh-tui/bin/dsh-tui.js`。
这里只核对安装身份，没有启动 TUI，未证明交互提交机制。

## 3. 契约 v2 与历史 v1

新增 `parallel_batch_v2.yaml` 和 v2 请求/manifest/resource/admission/preflight 契约。
v2 的 fixed execution config 只有 `execution_mode`、`worker_count` 和 `schema_version=2`。
新增批次写 v2；所有影响请求哈希、配置哈希和统计解释的顶层产物都标明版本。
内部与 K 无关的 inference/IPC 子协议不盲目升版，必须在顶层绑定其已有子协议版本。

v1 YAML、manifest、journal、receipt、evidence 与原哈希保留，只读解析用于历史展示、
审计及旧恢复验证。v1 不得从新 coordinator、spawn、resume、retry 或 allocator 入口启动新执行，
返回 `LEGACY_CONTRACT_EXECUTION_FORBIDDEN`。恢复旧服务状态可以读 v1，但不能据此重执行旧任务。
旧 journal 的事件、terminal reason 和统计解释继续走 v1 reader，不追加 v2 事件到 v1 journal。

新请求显式传 K，包括 `max_points_per_worker: null`，返回 HTTP 422 和稳定错误
`LEGACY_MAX_POINTS_PER_WORKER_UNSUPPORTED`；CLI 传 `--max-points-per-worker` 返回同名错误，
不启动任何资源。K 不出现在新 schema、capabilities、请求哈希和 responses 中。
历史响应使用明确 `contract_version=1` 的只读 view；不能把旧 capacity 字段塞回 v2 response。
version 缺失的既有记录归 v1 只读，新执行请求必须明确 v2。存储迁移只追加版本元数据，
不更新旧原始 document、receipt、fence 或结果文件。新请求遇到未知版本失败关闭。

建议接口（新类型均在实施任务中定义）：

```python
@dataclass(frozen=True)
class FixedExecutionConfigV2:
    schema_version: int  # 必须为 2
    execution_mode: str  # SEQUENTIAL | PARALLEL
    worker_count: int

def load_parallel_runtime_config_v2(path: Path) -> ParallelRuntimeConfigV2: ...
def read_historical_contract(path: Path) -> HistoricalContractView: ...
def require_v2_execution(request_version: int, config_version: int) -> None: ...
```

v2 config 不含 K、K upper bound 或旧资源公式。其 heartbeat/lease/ack/phase/batch/recovery、
broker 和 freshness 字段沿用原值。封闭 `execution` 区保存全部有效执行、安全和测量规则；
`deployment` 区仅保存 `approved_profile_path`、`approved_profile_sha256`、`promotion_record_path`。
候选配置的三项为 null，fixed生产配置必须完整；fixed production不能接受null或候选authority。
ADAPTIVE使用其独立context，不读取fixed deployment引用，不因这三项为null而要求fixed资格。
deployment 不保存 promotion hash、deployment receipt hash 或自己所属文件的 hash，避免反向引用。
配置完整原 bytes 仍进入部署审计；资格等价性的语义归一化见第8节，不能沿用 v1 的全量asdict哈希替代它。
ADAPTIVE 的 `PoolRequest`、内部 factory 和固定兼容 adapter 去掉 K，不新增代用配额；
`initial_points_per_worker` 仍是 affinity 初始分配语义，不变成累计领取限制。

## 4. 共享队列与统计

`BatchCoordinator.grant_lease` / `_grant_lease_outcome_locked` 保留锁、幂等 request key、worker generation、epoch、
broker-health pause、active attempt、blocked point 和 point-selector 校验，删去累计 lease 配额条件。
正常 fixed path 选择共享 ordered pending 集合中的第一项；READY/AVAILABLE worker 必须没有 active lease。
`lease_count` 每个新 grant 加一，重放/重复 request 不加；释放后可再次领取，无需与点位数比较。

`_evaluate` 保留 `POINTS_COMPLETE`、`SHARED_DEPENDENCY_UNAVAILABLE` 与全部 frozen deadlines。
没有 active lease 但仍有可恢复 worker/待注册 slot 时继续等待其原 deadline；若所有 slot 均已
终止且存在未完成点，则 v2 终止为 `NO_RECOVERABLE_WORKERS`，不是 K capacity exhausted。
单个 worker 恢复只替换相同 slot 并提升 generation，不降低所选 N、不新增第 N+1 个同时运行 slot。
若 N 个 slot 不能完整建立，批次不得宣称 exact-N 完成，按 infra failure 收敛和保留证据。

业务统计保留首轮与 FULL_RESTART_RETRY 的独立分母；资源测量和人工 retry 不污染首轮成功率。
历史 `CAPACITY_EXHAUSTED` 仍可读，v2 不产生此事件。新 lease_count 展示为累计次数，
不再出现 `/ K`。Web 以 “共享队列 · 每 worker 一次一任务” 和精确 N 的资格原因取代 Capacity。

## 5. 统一资源门

新增 `src/so101_demo_py/src/parallel_batch/resource_budget.py`，负责封闭 schema、
安全读取、fingerprint、exact-N profile、qualification 和实时准入；不承担仿真启动。
现有三消费者只作 adapter，不能各自重算公式或各自信任不同 evidence。

```python
class ResourceBudgetProvider:
    def load(self, path: Path, *, expected_sha256: str) -> ApprovedBudgetProfile: ...
    def admit_production(self, *, context: FixedProductionContext,
                         current: RuntimeFingerprint,
                         live: LiveResourceObservation) -> ResourceBudgetAdmission: ...
    def admit_measurement(self, *, context: MeasurementContext,
                          current: RuntimeFingerprint,
                          live: LiveResourceObservation) -> ResourceBudgetAdmission: ...

class ExactNQualificationProvider:
    def verify(self, *, record: ExactNQualification, worker_count: int,
               execution_identity_sha256: str,
               coverage_policy_sha256: str) -> QualificationDecision: ...
```

三种 allocation context 是互斥封闭类型，不是 `purpose` 字符串或 `enforce_resource_thresholds=False`：

| context | 封闭构造 authority | 拥有的约束 |
| --- | --- | --- |
| `FixedProductionContext` | 由三adapter共同调用provider验证promotion authority、approved profile、exact-N记录和当前控制身份后签发 | exact N、完整profile与qualification；Web只可获得此类型 |
| `MeasurementContext` | 独立measurement授权读取器验证private授权原文件、UID、expiry、batch/N/tree/policy并签发一次性scope handle | 不需要approved profile；只认可独立safety包络与measurement owner/control绑定 |
| `AdaptiveAllocationContext` | 现有 `ProductionAdaptivePoolFactory` 对当前pool token、pool generation和冻结adaptive options核验后签发 | 原domain、affinity、fallback和infra budget；不使用fixed-N qualification |

构造器不公开通用可伪造dict/string入口；签发结果绑定私有factory token和不可变context hash，
allocator验证其来源、请求kind、N、batch、epoch、effective config和拥有权一致。factory token本身
不是外部审批证明，外部 authority 仍逐次安全读取并核验。混合context、旧false flag、生产 caller
伪装 measurement、adaptive token进入fixed path均拒绝 `ALLOCATION_CONTEXT_MISMATCH`。
ADAPTIVE 继续原观测/allocator权限边界，其原 `enforce_resource_thresholds=False` 调用只迁成
typed AdaptiveAllocationContext，不扩展成 fixed bypass，也不强加 fixed-N profile。

普通 production Web 永远不签发 MeasurementContext；不得提供 `skip_resource_gate`、
通用 environment bypass 或 fallback。仅 production 的 Web preflight、CLI prepare、allocator
allocate/reconstruct 在资源副作用前校验相同 approved profile 和 exact-N record；在真正 spawn 前
重新probe。候选的同一allocator独立走measurement safety authority，不调用production profile读取。
preflight receipt绑定profile hash、qualification hash、fingerprint hash、requested N、
live observation monotonic timestamp和当前控制lease。
过期、变更或 TOCTOU 不一致使 receipt 失效。运行 watchdog 使用同一规则和原 owner cancellation 通道。

生产不只检查“空闲 RAM/GPU”。live probe 同时检查当前 background 包络、effective CPU
affinity/quota/thread policy、swap/PSI、GPU device、资格状态、完整运行版本与 cleanup/lease authority。
profile 无精确 N、UNKNOWN、REJECTED、尚未批准、fingerprint 漂移或不可读时一律拒绝。
reason codes 至少有 `BUDGET_PROFILE_UNAVAILABLE`、`EXACT_N_UNQUALIFIED`、
`RUNTIME_FINGERPRINT_MISMATCH`、`BACKGROUND_ENVELOPE_EXCEEDED`、`RESOURCE_PROBE_FAILED`、
`CPU_HEADROOM`、`RAM_HEADROOM`、`GPU_HEADROOM`、`SWAP_PRESSURE`、`QUALIFICATION_EVIDENCE_INVALID`。
每个 code 附 N、观测、所需值、证据引用，不暴露 token 或完整进程环境。

## 6. 逐档实测、采样与安全中止

N=2、3、4、5、6、7、8 分别测量、分别决策，不用公式外推，不把 N8 结果下发为 N4..7
资格，也不把 ADAPTIVE 或旧 N2/Task14 当固定 v2 资格。SEQ/retry 的 N1 用同一 provider，
有独立实测/既有可验证等价证据；不能因 N1 省略安全门。本设计不预填任何每档资源值。

每档候选测量前先冻结独立 measurement authorization：操作员 UID、dispatch/task ID、
候选 clean source commit 和 execution tree digest、有效配置、精确 N、20 点 catalog/seed、
FULL_RESTART、最大实验数量、单次5400s硬超时、abort policy hash、拥有的进程/容器/domain、
新独立 batch 路径及过期时间。授权只能启动候选测量入口，不认可生产资格，不允许循环授权。
measurement CLI 与普通 Web 分离，双重核对授权和 worker allocator context；缺失或重放到
不同 N/batch/hash 立即拒绝。候选入口依赖主机物理包络和授权 safety policy，不依赖尚未生成的
approved production budget，因此没有 bootstrap 循环；它也不能写 promotion 状态。

### 6.1 候选 owner、控制和独立监控

裸 CLI 当前没有 `_fixed_web_control` 时不创建控制server、不向wait注入stop_requested。
新measurement入口必须在首个claim/spawn前建立 `MeasurementOwnerBinding`：authorization hash、
task/campaign/batch ID、coordinator epoch、owner PID/starttime/UID、私有control socket/token
及其哈希、独立authorization绑定的owned-process scope、sampler identity、abort policy和事件文件。token随机生成，
只通过私有FD/0600文件传递，不记录明文到日志，不需要production Web lease。
scope只涵盖本次新measurement的controller/coordinator、worker slots、broker generation/container；
既有Web/ROS/其他campaign绝不纳入。socket使用短路径并逐项验证107字节预算、owner、mode和fd身份。

候选owner复用 `FixedCoordinatorControlServer` 的闭合schema1 `STATUS`/`CANCEL_BATCH` wire和
campaign/batch/epoch/token/request-hash校验，通过typed measurement binding提供其需要的身份；
将server只接受旧BatchRequest的类型检查明确扩展到合法v2 fixed request，不能接受adaptive请求。
wire的CANCEL_BATCH仍先fsync `BATCH_STOPPING`，ACK只证明停止转换，绝不是cleanup。
measurement context在本地owner绑定此endpoint，不复用production store/控制lease。

owner的20ms health loop与采样进程分离，直接核验sampler PID/starttime、最后成功sample sequence、
monotonic采样时间、独立host/GPU safety读数和controlserver健康。采样完成才推进heartbeat，
空echo/进程存活不推进。100ms内无成功sample、sampler退出、不可读、sequence回退或abort breach
先永久锁存abort，再冻结spawn/grant/recovery、发送认证取消。正常检测到发送应不超过50ms；
健康loop超调或无法给出该上界的运行记INVALID，不虚报及时取消。

composition以统一 `control.stop_requested()` 取代Web-only谓词，并无条件接入candidate的
broker-start/warmup readiness loop、每次worker spawn前、child wait、broker retire/reload/warmup、
worker recovery/readmission、finalization。每次外部阻塞调用使用原deadline的更短bounded poll，
不延长原timeout；abort latch后不得启动replacement或重新开启lease，即使迟到health ACK到达。
独立owner monitor同时核对owner和control endpoint；owner死亡/失去响应时先通过同一认证通道停止，
不能联系到owner则保留fence并只调用本次measurement已登记且fresh验证的ProcessSupervisor
owned-group containment，验证PID/starttime/PGID/descendants/容器label，绝不向foreign identity发信号。
controller目标取消不能证明、ownership未知或containment失败时，不生成正常cleanup receipt，
保持operator-recovery-required并阻断下一候选。owner monitor不是宽泛清理或操作者恢复授权。

记录 t_breach、t_detect、t_abort_latch、t_send、t_durable_stop_ack、t_last_goal_cancelled、
t_owned_groups_gone、t_domains_clear、t_cleanup_receipt；分别计算采样延迟、发送延迟和真实停止延迟。
取消ACK应在现有control transport的2s内到达，否则进入fenced containment；shutdown保留
ProcessSupervisor原interrupt5s/term5s/kill2s和worker控制5s、broker recovery90s、worker
recovery120s/finalizing120s等原deadline，不把“一个采样周期发送”说成“50ms物理停止”。
整个候选stop/cleanup不得超出既有phase/batch deadline；到期失败保留全部状态与证据。

baseline 至少 60s，记录完整 host/cgroup/process/container/GPU 负载。background 必须逐项归属：
现有broker/models若属本测量，必须先在独立批准的窗口验证拥有权并完成其FULL_RESTART，
使本轮baseline时owned workload尚未启动；若不属于本测量则记background，不能借其warmup省去cold-start。
不把同一 broker/PID 同时记入两边。以 PID+starttime/cgroup/container ID 建立不重复的 inventory，
包含全部 MuJoCo、MoveIt、controller、ROS、TF/RGB-D/rendering、broker/model/inference 和后代。
未知 same-UID 候选进程、不可读 environ/identity、未知 GPU consumer 或 baseline 漂移均失败关闭。
停止其他服务/背景负载只能在单独拥有权及部署窗口批准后进行，测量授权不允许宽泛清理。

### 6.2 计量、归属和20%方程

单位固定为 bytes 和 core-seconds/second（core-equivalent）。RAM容量 M 为 `/proc/meminfo`
MemTotal转换bytes；whole-host不可用量 U(t)=M-MemAvailable(t)，它包含内核/cache压力，不能
用PSS替代。GPU容量 G 为所绑定device NVML total bytes，V(t)=G-free(t)，包括所有consumer。
CPU的 E 是本任务允许cpuset与在线逻辑CPU集合、全部ancestor `cpuset.cpus.effective` 的交集大小，
再取全部ancestor quota/period的最小core-equivalent上限；不把24logical全数视为始终可用。
CPU时间统计去重的host全机与cpuset集合两种视图，以100ms非重叠窗累积delta core-seconds，
保留1s窗复核；cgroup CPU period固定100000us，quota只限制周期平均，不宣称限制瞬时每核峰值。
若没有同UID可验证的delegated cgroup v2、cpuset或足够计量能力，measurement不开启，不使用sudo
创建系统delegation、不用tmpfs，也不把缺少cgroup当作generic falseflag许可。

每轮只创建一棵measurement专属cgroup层级：owner/sampler/monitor与workload均记入本任务计量，
workload包含shared broker以及N worker的全部后代；相同页面/进程不能跨两个统计类别相加。
PSS是进程诊断分摊，cgroup memory.current/peak是本树实际charge，U是whole-host安全值，
三者分别保存和比较，不求它们的和。容器必须证明实际同一delegated树；无法归属的GPU/host
consumer或shared page charge均保守列unattributed/background，不从全机使用量中扣掉。
baseline在owned workload启动前观测至少60s：B_ram=max U(t)，B_gpu=max V(t)，B_cpu为E集合
中background100ms峰值。baseline包含OS/cache和既有服务；measurement工具的常驻开销单列H，
但若它已在baseline中则按inventory明确标记，不能再次加H。

每个exact-N profile保存startup/steady/recovery/finalization的增量上界D及误差上界J，
background包络B与采样工具开销H。RAM/GPU的D来自同阶段 whole-host/device量相对已核验background
的增量和cgroup/device交叉证据，取保守较大上界；不从负delta得到负需求。无法界定背景漂移或
峰值差上界则UNKNOWN。CPU的D来自本树delta CPU time，不把cgroup quota当测量需求。

pre-spawn准入方程分别为 `B_ram+H_ram+D_ram+J_ram <= 0.8*M`、
`B_gpu+H_gpu+D_gpu+J_gpu <= 0.8*G`、`B_cpu+H_cpu+D_cpu+J_cpu <= 0.8*E`。
当前raw MemAvailable还须满足相应增量需求后至少20%M空闲；GPU free同理。
in-flight时live观测已经含owned已启动部分：`observed_total + remaining_stage_increment_upper_bound
+ error_upper_bound <= 0.8*capacity`，不再追加全部D。remaining来自covered阶段转换（例如resident N
加broker reload）的独立实测上界；未知转换不得新spawn/recover并进入既有安全失败收敛。
已经运行的current whole-host/device量仍必须<=80%，background不能把owned负载重新当背景。
CPU同时核对E集合与whole-host负载约束，restricted cpuset内满载不能被其他闲核掩盖。

以下只作为算术table-test fixtures，不是ai-station预算：

| 合成输入 | 期望断言 |
| --- | --- |
| M=1000，B+H=200，D+J=600 | 总800，余量20%，相等通过；D+J=601拒绝 |
| E=4（host24但cpuset4），B+H=0.4，D+J=2.8 | 合计3.2相等通过；需求2.9拒绝；不能用24作分母 |
| 全机U=700，PSS=400，cgroup charge=500 | RAM安全值700而非1600，分别保留诊断视图 |
| in-flight GPU observed=600，remaining reload=150，J=50，G=1000 | 总800通过；不能再加含resident600的完整startup需求 |
| host内核/cache使U=810，PSS仍400 | whole-host拒绝，不能因进程PSS低而通过 |

采样器从 spawn 前开始，到 cleanup 及 finalization 后至少5s安静期结束：

- 每 50ms 收集 /proc/cgroup CPU time、RSS、host MemAvailable、swap counters、PSI 和
  整个 GPU device 使用量；startup、模型加载、warmup、inference、render 和 teardown 以事件边界标记。
  PSS 使用可承受的 100ms 子采样并记录实际耗时，不按全部 RSS 相加估算 RAM。
- CPU 使用 `delta(user+system)/delta(monotonic)` 得到 core-equivalent，并同时保存 100ms/1s
  window peaks、affinity、quota、线程数和 throttling。逻辑核数不能代替可用 core-equivalent。
  RAM 同时保存去重 PSS 合计、cgroup `memory.peak`、host MemAvailable 最低值；GPU 使用 NVML
  整设备值，包含模型、rendering 和外部 consumer，不能只看 PyTorch allocated。
- startup/steady/recovery/finalization各保留峰值、时间、PID/device、采样间隔和丢样率。
  GPU burst 和短命子进程另用 spawn/allocator/render 事件与 cgroup 高水位核对。
  重复一轮以 25ms fast channel 交叉检查峰值别名；若无法给出短脉冲未观测误差上界，或峰值差
  超过预先批准的误差包络，不可 promotion。不得声称轮询捕获了所有瞬时峰值。
- broker queue/inference 的 enqueue/start/end 时间、每模型 queue depth 和 p95/max 延迟，
  每 worker RGB-D 时间差、frame age、TF freshness、render frame latency、模拟时钟/墙钟 RTF
  都使用 monotonic 对齐。raw samples 保留，不只保留均值、p95 或摘要图。

安全 policy 的数值属于事前保守边界，不是假测量结果：CPU、RAM、GPU 全机容量至少保留20%。
候选 workload cgroup 的RAM charge上限为 `floor(0.8*M)-B_ram-H_ram`（保守限额非PSS预算），
CPU quota最多 `0.8*E-B_cpu-H_cpu`，对应100000us period；affinity由E的cpuset交集固定，
GPU 整设备 usage 上限 `0.8*device_total_bytes`；上限非正则不启动。memory OOM/high/max event、
任何新增 swap-in/out、PSI full stall、不可读/丢样 gap>100ms、MemAvailable<20% MemTotal、
GPU free<20% total 或E集合/whole-host CPU100ms窗超过其80%容量均触发owner-authenticated abort。
“立即”定义为发现后一个50ms采样周期内发送既有取消；实际 stop 延迟另记录并必须在原 cleanup
deadline 收敛。quota throttling 本身使该轮不能通过资格，不能靠限速后报告资源足够。
GPU 无安全强制硬配额时，启动逐阶段 guard 和 watchdog；不能界定峰值超调风险的 N 只记
UNKNOWN/REJECTED，不冒险一次性放行。达到 safety envelope 后不继续升 N。

准入余量至少20%，用各阶段实测上界加采样误差/重复性上界后比较全机包络。旧 queue/inference
timeout10s/YOLO20s/Grounded60s、frame age5s、RGB-D/TF skew0原值不放宽。
具体每档测量值、误差和 background 允许包络来自 raw evidence，经审查后写入 profile。

### 6.3 RTF、clock epoch与真实backlog

RTF是每worker的观察指标，不能直接要求所有1s样本>=1.0，也不能先填一个低target让高N通过。
期望pace q只取当前冻结launch/physics有效设置：正 `sim_speed_factor` 使用其值；否则使用已冻结的
MuJoCo real_time_index对应percent/100并在runtime再次读回。当前常见1x只能在现场参数证明后
记q=1.0；配置不明、UI speed变化或paused flag不明均拒绝资格，不修改simulator速度/物理来达标。
q、physics timestep、clock发布规则、时钟估计器和误差规则进入semantic execution identity。

clock identity包含worker slot/generation、simulation_session_id、reset_epoch、publisher
PID/starttime及ROS domain；收到新reset/restart事件、clock倒退、publisher更换都开启新epoch。
只在已完成readiness、physics运行未暂停、worker AVAILABLE/INITIALIZING/EXECUTING/FINALIZING
的active阶段使用完整window；两点间静止但physics在跑仍eligible，不能只测motion最轻部分。
首次clock前startup、合法reset、teardown和batch完成后的idle分开记录，使用原initializing180s、
worker-recovery120s、finalizing120s等deadline；after-readiness无clock/stale clock不能标idle绕过。
pause/reset exclusion须有owner事件和原deadline，未解释pause不能产生通过样本。

receiver使用CLOCK_MONOTONIC原时间戳，50ms资源样本与每条clock消息共同保存；跨线程对齐误差
单列。window长度1s，stride1s，严格非重叠，边界clock值使用最近合法样本并保存时间差；
epoch切换/边界样本过旧则该window INELIGIBLE，不能跨epoch拼接。coverage每个steady阶段至少
5个连续完整eligible窗；短阶段只提供峰值而不能替代steady clock资格。

测量前独立baseline校准并冻结epsilon_t（两端timestamp/接收/对齐不确定性总界）和epsilon_s
（两端clock量化/physics step不确定性总界），连同最大消息间隔/采样gap界和推导证据一起签入
measurement authorization。不能用本轮失败样本放大误差再通过；误差太大不能区分sustained lag
就UNKNOWN。对 Δwall、Δsim 的合法窗保存点估计 `RTF=Δsim/Δwall` 与保守区间
`[(Δsim-epsilon_s)/(Δwall+epsilon_t), (Δsim+epsilon_s)/(Δwall-epsilon_t)]`；
分母非正、epoch不匹配、gap超界或time-source不可靠都INVALID。正常量化1x窗只要区间覆盖q，
不按小于1.0的点估计机械失败；upper<q才是一次可证明deficit。

若冻结epsilon需要实际clock观察，先进行单独操作员授权的 `CALIBRATION_ONLY` bounded候选批次，
使用同一MeasurementContext/owner/control和20%whole-host安全guard，不依赖approved profile或
尚未产生的epsilon。该批次只产生时钟校准原证据，不判RTF通过、不计normal qualification；
结束并审查校准证据后，在下一独立normal batch授权中冻结epsilon与其证据hash。
校准算法/最大允许不确定性规则属于R，校准所得epsilon与clock interval上界属于B/Q/P，
production逐项读取其冻结值；改变误差规则invalid R，改变校准值必须新校准、新qualification和promotion，
不能回填旧失败样本或在原批次中动态抬高epsilon。没有可验证的校准界则不启动正常资格批次。

连续两个独立完整窗upper<q或相同active epoch的累积lag
`L=q*(wall-wall_anchor)-(sim-sim_anchor)`增长超过事前冻结的传播/量化误差界，且跨两个完整
非重叠窗仍增长，判 sustained lag 并认证取消；单次短扰动不从重叠rolling样本重复计数。
另保存起止clock lag、broker待处理年龄/queue depth、TF/RGB-D freshness、render延迟及原timeout
越界。持续队列增长/最老request超原queue deadline、after-ready时clock age超原heartbeat/frame
age中较小的5s、无clock/不明停步都会失败，即使某窗RTF通过。freshness和execution deadline
独立生效，不由RTF误差豁免。不得把旧Task14 realtime_headroom_ratio解释成新RTF。

估计器table tests使用合成值：Δwall=1.000s、Δsim=0.998s、epsilon_s=0.002s、epsilon_t=0
时区间含q=1，量化healthy通过；Δsim=0.900s且同误差时upper=0.902，两独立窗判deficit。
这些值只证明算法，不是生产误差界。真实epsilon尚未校准，状态NOT_MEASURED，不能获得资格。

## 7. exact-N 资格与业务结果

每档至少连续5次 VALID FULL_RESTART 的20点完整批次，固定 code tree、有效配置、模型、
container、thread policy、seed分布和验收契约；每次完整重启本轮拥有的 worker/broker stack，
全部 N 个 runtime slot 有独立 identity/启动/heartbeat/控制器/渲染证据，完整20点形成足够共享队列负载。
至少记录一次 N 个 worker 同时活跃窗口；缺少实际 N 并发不能用该轮为档位资格。
五次normal run是稳定运行证据，不单独证明所有允许phase的资源上界；还必须满足下述coverage。
额外点位少于 N 的 Web 验收保持 N runtime、允许部分 idle，不计为饱和资格。

| 分类 | 资格处理 | 业务统计 |
| --- | --- | --- |
| VALID + PASSED | 资源、实时性、cleanup及物理证据全部通过可延长资格序列 | 计业务成功 |
| VALID + 真实业务 FAILED | 20点均有最终确定结果、独立有效物理失败证据且资源契约通过，可延长资源资格序列 | 计业务失败，不延长抓取连续成功序列 |
| VALID + infra failure | startup/timeout/RTF/freshness/broker/cleanup失败；资格序列终止 | 单列 infra，不伪装业务失败或PASS |
| INVALID / UNKNOWN / INDETERMINATE | provenance、采样或物理证据污染；不进有效分母，终止该统计批次 | 保留原结果；不算成功 |

每点证据包含 policy 状态及原资格标志、MoveIt plan/execute result、controller/joint/TF反馈、
MuJoCo cup world pose/support contact/重力与 release epoch、MoveIt shadow detach/world sync、
fresh RGB-D/渲染图和最终截图。失败未到达阶段明确 NOT_REACHED，不能编造其后物理成功。
状态机 DONE、旧截图、旧结果、旧恢复 receipt 均不能替代独立物理证据。
若宣称抓取全流程连续成功，另满足同一冻结契约5次 VALID 业务成功；resource_qualified 和
product_qualification_passed 分开存储、展示，真实失败不因“资源qualified”被改成PASSED。

### 7.1 有限phase coverage与恢复峰值

每个exact N冻结以下coverage矩阵。正常业务失败可以支持有效资源观测，但若失败发生在所需phase
之前，那个cell仍NOT_COVERED。通过five-normal-run但coverage缺失不能promotion。
同一cell至少两个独立FULL_RESTART/合法恢复实验覆盖并进行50ms/25ms峰值交叉检查，记录所有
N runtime identities、模型请求路径和渲染事件；禁止用mock/synthetic物理成功补cell。

| cell | 固定支持路径与并发/驻留条件 | 资源上界所含范围 |
| --- | --- | --- |
| COLD_START | 独占owner启动shared broker、YOLO+Grounded/SAM模型加载warmup，再启动全部N worker/render/controller/MoveIt | 实际cold-start顺序全峰值，不能将加载次序假改成轻负载 |
| STEADY_YOLO | N个真实slot驻留、N路RGB-D/TF与render active，真实YOLO请求按原bounded queue/inflight处理 | coordinator/broker/全部runtime/renderer和并发请求峰值、queue延迟 |
| STEADY_GROUNDED_SAM | 通过真实模型失败/合法fallback路径触发Grounded+SAM，N runtime/render仍active，保存真实请求相关性 | Grounded和SAM模型常驻及计算峰值；不扩大queuecapacity/inflight |
| STEADY_MIXED | 至少两模型路径重叠，N路render与计划/控制反馈同时驻留；按原queue允许上界发请求 | 共享模型executor/队列、render、MoveIt/controller overlap，不把N理解为N个GPU executor |
| MOTION_RELEASE | 真实经过grasp/lift/transport/release的点，达到N-slot代表性motion/render/TF重叠，失败未到达的phase明确缺失 | 独立物理/scene/controller证据与对应资源峰值；无成功路径覆盖不能以早失败代替 |
| BROKER_RELOAD_WITH_N_RESIDENT | 故障后已停旧broker/container并证明，无N runtime卸载，原generation+1模型重载/warmup | resident N+模型reload/render压力的完整峰值，比cold-start大则提升envelope |
| WORKER_RECOVERY_WITH_N_RESIDENT | 原worker fenced/目标停止/旧进程消失后同slot新generation，其他N-1 runtime与shared broker仍驻留 | 不重叠两个同slot存活worker；启动/重新render/controller/model请求峰值 |
| FINALIZATION_CLEANUP | N slots的实际完成/取消及受控cleanup，shared模型和renderer释放 | finalization/teardown峰值、实际停止时间与ownership/domain读回 |

每cell使用现有支持路径，不新增自动retry或修改物理以促成覆盖。若当前队列上界使某个N无法
稳定提供该路径，记REJECTED/UNKNOWN，不调大queue或减少N。禁止只跑4点N8或全早失败20点
作为saturated steady/motion资格。允许的warmup/readiness/recovery bounded path均计入covered
phase包络，不把startup broker先于worker的峰值冒充broker reload与residentN重叠峰值。

每个 N 的 fault campaign 与正常资格序列分开：broker退出/queue超时、worker heartbeat失联、
startup失败、stale TF/RGB-D、render压力、RAM/GPU headroom侵蚀、sampling gap、cleanup unknown、
profile漂移、取消/restart/lease过期。合法bounded recovery的有效峰值和采样误差进入该N相同
resource envelope，failure/cancellation路径的有效压力峰值也不能漏掉；预期中止可支持门控测试，
不能算业务成功或five-normal-run资格通过。UNKNOWN/unbounded异常不能支持上界，阻断promotion。
不提升 infra attempts，不自动重测直到过关；每个新 batch 先冻结实验数量和失败决策。

## 8. fingerprint、promotion 与无自指身份

profile schema2 的每档 entry 为 UNKNOWN、CANDIDATE、REJECTED 或 APPROVED，含 exact N、
raw batch manifest hashes、五次qualification记录、完整coverage矩阵及startup/steady/recovery/finalization
峰值/误差/可用余量、baseline背景包络、
sampler身份/覆盖、有效timeout/freshness/RTF规则及审查批准引用。不允许 NaN、缺失测量或零填充。

`RuntimeFingerprint` 绑定 CPU/hardware/memory/GPU UUID和容量、OS/kernel、driver/CUDA/ROS/RMW、
MuJoCo子模块、模型weights/grounded manifest、broker image ID、container runtime、有效配置、
scene/policy/catalog、execution-code-tree、runtime installed files、console wrapper、build flags、
CPU affinity/quota及OMP/BLAS/render/model线程设置。source commit 作为审计标签仍要求 clean。

### 8.1 单向digest graph

资格身份与部署原字节审计是两层。v1的 `asdict(config)`、external binding原bytes及历史
hash解释保持原样；v2不能把它们合并成一个会自指的hash。所有digest使用canonical UTF-8 JSON，
sorted keys、无NaN、明确units和schema，不把本体self-digest或未来parent digest写入内容。

```text
normalization rule/code digest L
  -> normalized semantic config S + normalized execution-code/install inventories E/I
  -> execution identity R (hardware/model/container/runtime/thread + L/S/E/I)
  -> raw sealed measurement manifests B -> exact-N qualification/coverage index Q
  -> measured demands/covered peaks + R/Q -> profile P
  -> independent approval + P + measurement source/full-byte audit A0 -> promotion M
  -> installed deployment full-byte audit A1 + location binding + M/P -> deployment receipt D
```

R不含B/Q/P/M/D；B只绑定R、exactN、candidate authorization、safety/coverage policy和raw
artifact hashes，绝不引用未来approved profile hash。Q只引用已sealed B及其结果/coverage；
profile P引用Q，Q不反向引用P。`ExactNQualificationProvider.verify` 的参数是R和coverage
policy hash，不是enclosing profile hash；production adapter另校验P引用的Q与M/D一致。
M绑定独立operator/Astra/Sol审查引用、P和A0；A1可以包含安装配置内的P hash，D引用A1/M/P。
配置只保存P path/hash及M path，绝不保存M hash或D hash，M也不引用A1/D，故无环。
M path读取到的内容经独立promotion authority安全验证并核对P；只有路径不能构成approval。

### 8.2 精确归一化与部署审计

source与installed v2 YAML先按同一closed schema解析，拒绝重复key、unknown、nonfinite、
类型漂移。S为完整 `execution` 内容加相同 `deployment` key集合；仅将三个deployment值替换
为固定字面 `DEPLOYMENT_REFERENCE_V2`。L绑定这一算法、字段列表和schema版本；path/sha的值
变化不改变S，但未知deployment key、执行阈值变化、算法变化均invalid。
heartbeat/timeout/freshness/RTF estimator/error policy、abort thresholds、catalog/scene/model、
thread/affinity/quota和coverage policy全部保留在execution语义中，不以metadata名排除。
实测epsilon/需求数值在B/Q/P，不用修改measurement后的execution规则来容纳失败。

E和I按预先审核的logical package path清单构建：仅配置carrier
`src/so101_demo_py/config/mujoco/parallel_batch_v2.yaml`及其已证明的installed share对应副本
使用S作为内容digest。其余console wrapper/shebang、module、sampler/control/watchdog、launch、
policy/scene/model绑定、Web执行contract和运行依赖使用原bytes hash。预算/qualification/promotion
载体放注册evidence root内，根本不进入代码/安装inventory；docs和账本非执行文件不进E/I，
清单规则L固定，不能临时增加exclude。整个配置不是被排除，installed文件也不是全量被忽略。
runtime-file drift只要影响非carrier任一原字节就改变I，要求重新资格。

A0/A1分别保存clean source commit/status、所有source/install文件原bytes hash、config原sha、
实际prefix、可执行文件路径、wrapper/shebang、dependency origins、private authority身份和HTTP
assets绑定。A0是测量时审计，A1是部署时审计，不强求两者所有bytes相同；必须证明只变上述
允许carrier引用/metadata，且L/S/E/I/R相等，所有未允许文件bytes完全一致，生产P/M有效。
完整字节绑定验证在各自A中仍严格执行，不拿S替代原部署文件的真实性校验。

prefix搬移仅在实际executable/module/dependency bytes保持一致、环境origin/库闭包被验证、
路径映射已登记且R中的有效环境不变时是location binding变更，生成新A1/D即可；
任何wrapper/shebang因prefix重生成、absolute import/build path或依赖bytes改变均改变I/R，
不能归一化掉可执行内容，需重新测量。source HEAD变化只作审计标签不进R，但仍要求当前clean。
先clean commit冻结所有代码/规则，candidate引用为null；完成B/Q，再生成P、独立M，最后只发布
引用/metadata并产生A1/D。首个approved profile可加载而不用递归重测；安全配置/thread/model/
executable/normalization rule变化则invalid。三个消费者共享这份等价性与原bytes双层规则。

promotion 顺序固定：候选实测 -> Sol / High 审查执行结果和原始证据 -> Astra / High
独立审查 proposal/profile/parser规则 -> 操作员明确批准 exact N/profile hash -> 追加不可变promotion
M与部署审计A1/receipt D -> 三生产消费者实时检查+qualification -> 才允许新生产batch。
候选/批准文件安全读取沿用 fd/O_NOFOLLOW/owner/mode/size/hash稳定性与独立acceptance authority，
候选树不能自己提供 approval。换环境/profile/thread/driver/model/code即invalid，选项仍展示但禁用。

## 9. 恢复前置、部署和证据保存

先审查并在隔离 worktree 整合恢复源码快照六个源文件（不计 pycache）：
`src/so101_teleop/CMakeLists.txt`、`scripts/so101_expert_validation_recover.py`（package内）、
`so101_teleop/expert_validation/store.py`、`operator_recovery.py`、
`test/test_expert_validation_package_layout.py`、`test/teleop/test_expert_validation_operator_recovery.py`。
原快照位于唯一证据根的 `operator-recovery-implementation/recovery-source-snapshot/data/work/ws_moveit/`。
保留原 receipt、original fences、历史行/哈希、失败尝试。新 clean commit、install、独占离线
幂等核验及拥有的 Web refresh 全部完成后，才标 ONLINE_RECOVERY_VERIFIED。
重复核验已有成功 command ID 只返回原 receipt，不重写旧报告；原恢复script/module尚未部署。

canonical 旧 Web 保持到操作员批准的独占部署窗口。部署前 fresh核对 PID/starttime/parent/pane、
URL `100.82.102.56:8000`、ROS domain179、服务store/executable/hash和当前 lease/campaign。
历史 PID/parent461503/pane%63只是参考，不能作为停止授权。源身份只允许clean commit。
未知same-UID进程检查失败关闭；SSH sshd environ不可读时不改 skip/probe策略，改由 task-owned
tmux delayed command 执行，让dispatch SSH退出后再进行扫描。只停止本轮拥有的服务/进程。
离线operator恢复支持旧v1冻结配置，与新v2执行禁止分层处理。部署失败保留原服务回滚路径，
不得删除failedattempt或重新伪造receipt。

本任务唯一 raw evidence root 沿用
`/data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main`。
其下新增 `unbounded-queue-resource-budget/` task目录、独立measure/qualify/fault/browser/test batch，
不建立第二个root。恢复交接先读取当前serving continuation
`docs/experiments/so101-teleop-serving-worker-eight-continuation-ledger.md`，其header绑定本root和
CP-L02，正文还有后续CP-M01及PENDING refresh；header不是最终状态，必须结合本root/task-ledger
和fresh runtime恢复最后可信checkpoint。较早
`docs/experiments/so101-moveit-expert-validation-web-experiment-ledger.md` 保留为历史development
context，其不同root不能替换本任务root/ownership链，不回写旧历史。新增任务账本
`docs/experiments/so101-parallel-unbounded-queue-resource-budget-experiment-ledger.md`，单写入者，
在执行前登记root、checkpoint、原历史引用、owned/preserved进程、next experiment和明确未执行状态。

ai-station所有fsync-heavy pytest/colcon fixtures使用root下唯一此前不存在的
`unbounded-queue-resource-budget/scratch/<test-run-id>/tmp`。先同时设置 TMPDIR/TMP/TEMP，
使用实际test Python校验 `tempfile.gettempdir()` 在该目录内，失败不开始。记录scratch绝对路径、
命令、实际exit code、elapsed和junit；scratch仅列deletion candidates，未经明确授权不删。
普通demo gate只运行 `src/so101_demo_py/test/`，不收集benchmark_test。Web使用Bun和既有lock。

## 10. 实现映射与验收

| 实现边界 | 真实文件/测试 |
| --- | --- |
| v2 request/config和历史reader | `src/so101_demo_py/src/parallel_batch/contracts.py`，新增`historical_contracts.py`、`config/mujoco/parallel_batch_v2.yaml`；`test/test_parallel_batch_contracts.py`、`test/test_parallel_batch_journal.py`、`test/test_parallel_batch_crash_recovery.py` |
| shared queue/terminal | `src/so101_demo_py/src/parallel_batch/coordinator.py`；`test/test_parallel_batch_coordinator.py`、`test/test_parallel_batch_fault_injection.py` |
| unified budget/qualification/sampler/control | 新增`src/parallel_batch/resource_budget.py`、`resource_measurement.py`、`measurement_control.py`、`src/cli/measure_parallel_resources.py`；`resources.py`、`web_control.py`、`src/cli/mujoco_parallel_batch.py`、`src/runtime/parallel_processes.py`、`setup.py`；现有`test_parallel_batch_resources.py`、`test_parallel_resource_probe_races.py`、`test_parallel_batch_cli.py`、`test_parallel_batch_web_control.py`、`test_parallel_processes.py`及新定向测试 |
| ADAPTIVE兼容 | `adaptive_contracts.py`、`adaptive_runner.py`、`adaptive_pool.py`；`test_parallel_adaptive_contracts.py`、`test_parallel_adaptive_pool.py`、`test_parallel_adaptive_runner.py`、`test_parallel_adaptive_integration.py` |
| Web backend/store/projection | `src/so101_teleop/so101_teleop/expert_validation/{api,models,preflight,coordinator,supervisor,production,adaptive,statistics,store}.py`；`src/so101_teleop/test/teleop/test_expert_validation_{api,preflight,supervisor,store,statistics,production_projection,e2e_installed_port,process_owner_integration}.py`，新增budget adapter测试并在CMake注册 |
| OpenAPI/types | `src/so101_teleop/so101_teleop/openapi_export.py`、`expert_validation_openapi.json`；`src/so101_teleop/web/src/api/{expert-validation-schema.d.ts,expert-validation-types.ts,expert-validation-client.ts}`；`test_openapi_export.py`及client test |
| Web setup/progress | `web/src/expert-validation-app.tsx`、`web/src/components/expert-validation/{campaign-setup,campaign-progress}.tsx`、app/components/state tests |
| contract/installed/live browser | `web/e2e/expert-validation/pages/expert-validation-page.ts`、`contract/setup.spec.ts`、`contract/live-preflight.spec.ts`、`installed/support.ts`、`installed/{retry-queue,api-contract,entry-and-campaign,lease-recovery}.spec.ts`、`live-sim/{02-parallel,preflight}.spec.ts`、`fixtures/live-sim.ts`、`assertions/live-evidence.ts`、三个现有playwright配置 |
| fixture与process helper | `src/so101_teleop/test/e2e/{execution_port,scripted_service}.py`、`process_helpers/fixed_helper.py`、`test/fixtures/expert_validation_e2e/scenario.schema.json`与scenarios |

新测量/测试文件由实施计划定义接口，路径中的`src/parallel_batch`等相对demo package；未创建代码。
OpenAPI由现有 `python -m so101_teleop.openapi_export --validation ...` 导出，再在web目录
`bun run generate:api:validation`，不能手改生成types形成漂移。

验收必须覆盖：单worker领取次数超过历史K仍完成；重复grant不增统计；并发独占/恢复/fence/timeout
不变；v1字节/哈希不变且禁止新执行；新K明确失败；三消费者同profile同reason；精确N的缺失/漂移/未知
拒绝；candidate无生产bypass和无bootstrap循环；N2..8逐档raw/peak/qualification/promotion；
浏览器选择N、4/20点、刷新/续租/expiry、失败单点retry及独立统计、拒绝原因、原opaque evidence显示。
浏览器live门不得因当前共享services冲突而改成忽略；先批准独占窗口并fresh核对所有权，再运行。
guide作为实施计划末任务放在 `docs/guides/so101-parallel-unbounded-queue-resource-budget.md`。

## 11. 自查与未决风险

本设计没有填实测预算，没有宣称N4..8可用，没有把旧恢复凭据当在线恢复。
scope supersedes旧fixed-eight proposal及旧规范中K/count/resource-contract相关部分，其他历史规则
继续有效。旧proposal只可追加superseded链接，不删历史正文；不可覆写旧规范。

实施前须解决的可检验风险：GPU瞬时峰值覆盖和abort超调上界、PSS采样开销、RTF测量的每worker
时钟一致性、共享broker生命周期归属、N1证据等价性、clean source与profile metadata的分层身份、
旧恢复模块快照的真实安装依赖、当前live-sim fixture要求独占且canonical有既有services。
任何一项unknown则对应候选/档位拒绝，不能靠静默放宽阈值完成资格。最终报告分列retained、archived、
deletion candidates；本轮不产生新runtime artifact，不删除或归档旧证据。

本次复审必须具体核对以下design regression requirements，实施计划再给RED/GREEN可执行步骤：
首次profile从null candidate引用发布不形成identity循环；安全/timeout/thread/model/executable/rule
变化仍invalid；无Web的candidate在broker warmup/执行/reload中因RAM/GPU/sampler death/gap取消；
abort锁存后无replacement；无ACK/cleanup failure不伪造完成；量化healthy clock、sustained lag、
no-clock、epoch切换、同短扰动非重叠计数；five早失败不能补coverage；reload峰值提升envelope；
fault取消不计normal qualification/业务成功；互斥context不能伪造/混入adaptive；第6.2节数字table
tests保持去重和exact20%等式。文档审查PASS只闭合这些设计，不代表任何运行test/预算/上线PASS。
