# SO-101 单 Web 服务与 shadcn 界面设计

日期：2026-09-18。用户已逐节批准架构、全局互斥、交互草图及迁移验收方向；独立审查结论以绑定本文对象哈希的 GPT-6 Astra / High 审查记录为准，书面设计仍须用户审阅。本文不是实施计划，也不代表代码、部署或运行资格已经通过。

## 1. 范围与边界

Teleop 和 Expert Validation 合为一个 Web app：一个启动入口、一个 HTTP/WebSocket 服务进程、一个 Web 监听端口、一个前端构建。ROS worker 和采样 executor 可以是非 Web 子进程；不以一个 launcher 启动两个 Web 服务冒充合并。

采用用户指定的 `shadcn --preset b311momZs0` 设计系统，重构两页及共享外壳，保留原有业务功能、协议、安全门控与证据边界。`/tasks` 是已有工作流的兼容入口，不新增第三套业务体系。

本轮仅写设计。实施计划需另行批准；执行须遵守 `AGENTS.md`：DeepSeek Harness TUI 的 `dst` 在 `tmux` 中运行，监控和结果审查用 GPT-5.6 Sol / High，设计和计划由 GPT-6 Astra / High 独立审查。模型或工具不可用时明确报告，不替换、不修改全局模型配置。

以下事项不在此设计的授权范围内：停止或接管 foreign 进程、自动启动仿真、恢复旧 campaign 执行、批准资源 profile promotion、改动并行预算任务、删除证据、真实机械臂动作。真实机械臂仍需独立急停、限速、限位与净空授权。

## 2. 源码基线与已确认事实

源码事实来自已发布 `main` 的 `84620fc0529779a27c6985f8717d78f0386e0135`，读取位置为 `/private/tmp/so101-doc-publication.R3yXD0aj/repo`。原 `587b` 工作区是旧源码，不能作为当前 `main` 的事实源。下表行号均属于该发布基线；后续实施必须重新确认工作树、安装产物和实际运行 provenance。

| 基线位置 | 事实与设计影响 |
| --- | --- |
| `src/so101_teleop/so101_teleop/main.py:74`、`:122`、`:132` | Teleop 入口先创建并启动 ROS worker，再启动 uvicorn，最终停止 worker；需要把 ROS 生命周期移出 Web 进程。 |
| `src/so101_teleop/so101_teleop/api.py:43`、`:63`、`:149`、`:276` | Teleop factory 同时拥有 Teleop、Tasks、静态页；Validation capability 目前是不可用占位，全局 SPA fallback 在末尾。 |
| `src/so101_teleop/so101_teleop/server.py:146`、`:167`、`:187` | ROS worker 管理 rclpy、节点、executor 和线程；不是仿真启动器。 |
| `src/so101_teleop/so101_teleop/server.py:568`、`:599`、`:606`、`:692` | Teleop lease 和 command coordinator 在内存；现有任务阻塞谓词只连接 legacy TaskService。续约不能被长命令串行锁饿死。 |
| `src/so101_teleop/so101_teleop/task_service.py:63`、`:71` | Legacy Tasks 有自己的 active run 和命令缓存，当前不是跨 Validation 的互斥。 |
| `src/so101_teleop/so101_teleop/expert_validation/main.py:28`、`:39` | Validation 是另一个 ROS-free uvicorn 入口，默认端口与 Teleop 不同。 |
| `src/so101_teleop/so101_teleop/expert_validation/api.py:330`、`:351`、`:365`、`:523` | Validation lifespan 维护 lease；维护失败已有 mutation fence；单独服务的 `/tasks` deny 路由不能照搬到聚合服务。 |
| `src/so101_teleop/so101_teleop/expert_validation/store.py:124`、`:137` | Validation store 使用私有目录及排他 supervisor lock；合并不能打开第二个同域 supervisor。 |
| `src/so101_teleop/so101_teleop/expert_validation/lease.py:45` | 服务重启使旧 Validation leases 失效；未收敛 campaign 留下阻塞，而不是自动恢复执行。 |
| `src/so101_teleop/web/src/main.tsx:10` | 当前一个 bundle 按 pathname 选择三种根组件，但没有跨页面持久业务 provider。 |
| `src/so101_teleop/web/src/app.tsx:75`、`:124` | Telemetry 与 lease heartbeat 目前跟随 Teleop 页面 effect；组件卸载会关闭订阅或续约。 |
| `src/so101_teleop/web/src/state/expert-validation-store.ts:18`、`:26` | Validation 已以 HTTP projection 为权威，事件序列缺口触发补快照；应保留这个方向。 |
| `src/so101_teleop/web/src/components/teleop/joint-panel.tsx:33` | 轴 `1`–`5` 是臂关节，轴 `6` 是夹爪；草图的 J1–J5 加夹爪不增加第六个臂关节。 |
| `src/so101_teleop/web/src/api/client.ts:10`、`:25` | Execute All 当前是两个生成不同 command ID 的 POST；独立单步 reservation 不能覆盖中间空隙。 |
| `src/so101_teleop/so101_teleop/control.py:55`、`server.py:728`、`:858` | 当前 cancel 进入普通 coordinator，长命令持锁会返回 `SERVER_BUSY`；本设计必须替换这条调度路径。 |
| `src/so101_teleop/so101_teleop/server.py:411`、`:423`、`:537`、`:542` | 当前保存 arm goal，gripper handle 只是局部值，cancel 只请求 arm goal；home 本身包含 arm 和 gripper。 |

这些事实只描述发布树，不证明当前 ai-station 服务存活、进程归属或安装版本。并行预算任务有独立执行责任与 checkpoint；本任务不能借该任务的运行状态作自己的上线证据。

## 3. 单服务架构与生命周期

采用单 Web 进程加非 Web ROS 子进程。相较直接把 ROS 线程塞进 Web，此方案让 ROS 缺失、executor 卡死或 IPC 断裂不会阻止 HTTP 查看 Validation 历史，并能把 ROS 环境与 Web Python 依赖分开确认。

```text
浏览器：统一外壳 + Teleop / Expert Validation / 兼容 Tasks
                       │ 同源 HTTP / WebSocket
单 Web 进程
├─ 统一路由、静态资源、health、根级会话投影
├─ 全局 mutation arbiter 与持久 intent/ack 记录
├─ Teleop / Tasks 服务适配器 ── 受限 IPC ── 非 Web ROS worker
└─ Validation supervisor/store ── 既有 owned execution ports
                                      └─ 非 Web采样 executor / workers
```

Web app factory 不导入或初始化 rclpy。纯 schema、路由与服务接口可在无 ROS 环境加载；ROS imports、节点和 executor 只在 child 入口内发生。Teleop 的 camera/backend/Tasks 适配保留既有能力判定，不能从 UI 存在推断后端支持。

统一 lifespan 是唯一生命周期 owner：先确认配置和持久 store locks，建立 arbiter 与域状态，再启动 Validation lease maintenance、订阅和已配置的 ROS bridge。全局仲裁 store 有独立排他 service-instance lock，即使 Validation 未配置也不能启动第二个控制 owner；其版本化新记录不改写旧 Validation journal。只连接经批准的 runtime；创建 ROS client 节点不等于允许启动 MuJoCo、MoveIt 或控制器。没有 ROS、依赖不完整或 bridge 初始化失败时，Teleop 标记 unavailable，不自动另找 runtime。

| 域状态 | HTTP 与可用能力 |
| --- | --- |
| Web 正常，Teleop unavailable，Validation ready | 页面和历史可读；Validation 可在自己已授权、安全且资源合格的域内操作；Teleop mutation 拒绝。 |
| Web 正常，Validation blocked，Teleop ready | 历史可读；若阻塞涉及未知运行 owner、未完成 cleanup 或全局安全状态，Teleop mutation 也拒绝。单纯未配置 Validation 不伪造 active owner。 |
| 任一 lease maintenance、ownership 或 arbiter 状态无法证明 | 相应域与全局执行门控按影响范围 fail closed；不得用另一域 ready 覆盖阻塞。 |
| Web 正常，两域 ready | 操作还须通过独立域 authority、全局互斥及各自运行门控。 |

退出时先停止接收新的 mutation，保持续约/取消安全路径，按持久 owner 记录协调本服务拥有的任务，等待现有终止确认与 cleanup 判据，然后关闭维护任务、IPC 和 stores。超过既有终止或 cleanup deadline 时保留 blocked 记录并报告，不能将“服务退出”写成“物理已安全停止”。非 owned runtime 不发信号。

## 4. 路由、静态资源与健康检查

从两个 factory 抽取业务 routers 和可组合服务接口，由一个顶层 factory 注册。不能 mount 两个完整 app 后依靠注册先后来掩盖重复 `/health`、静态路径和 catch-all。

| 路由族 | 聚合契约 |
| --- | --- |
| `/`、`/expert-validation`、`/tasks` | 同一个 SPA 和共享 shell；`/` 保留 Teleop，`/tasks` 保留已有 TaskApp 能力。浏览器 direct refresh、back/forward 与导航使用同一入口。 |
| `/snapshot`、`/capabilities`、`/control/*`、`/plan/*`、`/plans/*`、`/telemetry` 及既有 Teleop 操作 | 保留原路径、DTO 和错误语义；unavailable 时返回结构化域错误，不落入 HTML fallback。 |
| `/tasks/*`、`/tasks/events` | 保留真实 TaskService routers；移除仅用于独立 Validation server 的 `VALIDATION_TASKS_DISABLED` blanket deny。门控仍由 capability、lease 与 arbiter 判定。 |
| `/expert-validation/*`、`/expert-validation/events` | 保留真实 Validation routers，替换 Teleop 的不可用 capability 占位；不改 campaign、lease 或 artifact identifiers。 |
| `/assets`、兼容 `/expert-validation/assets`、`/captures` 与两类 artifact 路径 | 一个已验证 bundle；保留既有 asset alias 和 capture/artifact authority。路径穿越、缺失资源、未知 API 返回原错误或 404，不能返回 SPA。 |

注册顺序是具体 API/WS、受限静态资源、明确页面路径、最后 SPA fallback。API 与 artifact namespace 显式排除 fallback。产物仍通过 `installed_web_assets` 的完整性检查，不依赖 Vite dev server 或第二个端口。

`/health` 聚合域 readiness、maintenance 与全局 blocked 原因，同时保留现有 Teleop health 字段的兼容投影；不得把 Validation ready 映射成 Teleop ROS ready。增加 `/health/live` 表达 Web 事件循环与生命周期存活，`/health/ready` 表达启用域是否满足其 readiness。ready 不满足返回 503；HTTP 仍可服务授权范围内的历史读取。停止条件不能只依赖一个绿色总灯。

一个 OpenAPI document 覆盖真实聚合 routers；现有 Teleop 和 Validation schema 导出可以保留为过滤视图，不能手工维护第二份不同路由。沿用 `src/so101_teleop/so101_teleop/openapi_export.py` 和 `src/so101_teleop/web/package.json` 的 `generate:api`、`generate:api:validation`，统一生成并验证客户端路径。兼容 entrypoint 只委托统一入口，不再分别启动 Web。

## 5. 根级状态、租约与重连

共享 shell 负责 theme、navigation、health 汇总与域订阅；它不是共享业务 lease。Teleop 仍使用自己的 lease、simulation session 和 command IDs；Validation 仍使用自己的 service session、lease ID、generation、campaign IDs。不能把一域 lease 填入另一域请求，也不能把 acquire lease 当作获得全局运行授权。

根级 Teleop provider、Validation provider 与兼容 Tasks provider 独立持有连接、快照和必要 heartbeat，页面只消费 projection。切页不取消任务、不释放 lease、不停止续约；退出控制必须是显式操作。provider 不因页面出现而自动 acquire lease。续约不进入耗时 mutation 串行锁，保留现有租期与维护安全规则。

多标签排他采用下面确定的服务器实例绑定契约。本地存储只恢复只读投影，不恢复执行许可。

订阅按域携带 epoch/generation 与 sequence。连接建立、断线重连、序列缺口或 epoch 变化时先获取权威快照，再衔接快照之后的事件；重复或旧事件忽略，缓冲有界，无法闭合顺序便再次取快照。Validation 继续以 HTTP projection 为权威。Teleop 的 simulation session 变化继续使旧 lease、plan 和 workflow 失效。

事件和重连只更新视图，不发运动命令。HTTP/IPC 超时或连接丢失时以原 command ID 查询记录；不知道结果就显示 unknown 并阻止依赖动作。不得生成新 command ID 自动重试，也不得回放离线 mutation 队列。

### 5.1 单 controller-instance 与显式交接

每个新 document 通过新增 `POST /control/instances` 登记域为 `teleop` 或 `validation` 的只读实例。服务器产生 instance ID 与至少256-bit的不透明随机 proof，proof 只保留于该 document 的内存，不写 session/local storage、URL或日志；两域分别登记，不共享 proof。其后连接新增 `/control/instances/{instance_id}/channel` WebSocket，以首个封闭握手消息提供 proof。服务器绑定实际活跃连接与 channel revision；浏览器自报的 ID、BroadcastChannel或持久 lease值都不能建立绑定。

实例登记不授予控制。用户显式 acquire 时，既有域 lease endpoint 在同一服务端事务中验证该实例的活跃通道，并绑定该域唯一 controller。若已有 controller，新 document即使持有相同有效 lease/session/generation，也只能读取，不能续约、mutation或以 acquire冒充恢复。普通命令和浏览器安全 cancel携带新增 `X-SO101-Instance-ID`、`X-SO101-Instance-Proof`、`X-SO101-Channel-Revision`、`X-SO101-Execution-Generation` authority headers；服务器逐请求检查域、proof、请求revision与实际活跃通道、controller绑定及原 lease/session权限。旧通道发出的迟到HTTP请求也因revision不匹配拒绝。legacy Tasks使用Teleop域绑定，不创建可绕过它的第三个controller。proof是实例绑定凭据，不代替现有运行安全或operator权限。

服务器维护独立单调 `execution_generation`：controller初次绑定和显式交接时推进；每个 parent/action在创建时冻结此值。Validation现有 lease renewal generation仍用于续约和当前lease请求校验，不改变运行中 action的execution generation，不能让正常renewal误取消action或授权旧controller。连接revision用于踢掉迟到连接，不替代execution generation；service epoch变更使全部instance proof与controller绑定失效，旧action仍按持久owner记录阻塞/恢复。

同一 document的切页和SPA back/forward复用根provider，不重新登记。硬刷新、重复标签、full navigation是新document，只恢复历史/快照并保持只读；BFCache恢复先验证原通道，不能假定仍有执行权。同一document断网可用内存proof重连，服务器原子更新channel revision、关闭旧连接；补权威快照前不接受新的业务mutation，旧连接迟到消息拒绝。重连不能自动继续已暂停或结果unknown的parent操作。

新增 `POST /control/instances/handoff` 只在全局无未收敛owner、无cleanup/recovery fence时执行。当前合法controller明确批准目标只读instance；若原controller已丢失，则先按现有lease失效及operator恢复路径证明无未收敛owner，不能凭复制的lease自行交接。事务验证目标活跃通道、原authority和预期execution generation，递增execution generation并使旧controller失效；交接竞争只能成功一次。断线本身不自动交接，也不释放运行reservation。

旧API路径与业务DTO保留，但所有控制acquire/renew及mutation增加实例authority要求；未升级客户端返回明确 `CONTROLLER_INSTANCE_REQUIRED`，不得存在legacy bypass。读取旧历史仍兼容。proof由服务器生成，不依赖当前`100.x` HTTP页面是否有secure-context WebCrypto；服务检查same-origin/Origin与握手来源。该proof不能保护不可信网络中的明文窃听，现有受限网络边界仍是前提，不能把实例绑定宣称为TLS或用户认证。

## 6. 双向原子 mutation 仲裁

默认全局互斥，不按 ROS domain 或 worker identity 放开跨页面并行。Validation 从 admission 到终止与 cleanup 完整收敛期间，Teleop 和 legacy Tasks 只读；其 motion、execute、reset 及其他 runtime mutation 均拒绝。反向同样成立：Teleop 或 Tasks 已取得 mutation reservation 时，Validation start/retry 拒绝，不能只实现 Validation 阻塞 Teleop 的单向谓词。

新 `GlobalMutationArbiter` 是服务端唯一 reservation authority。以下名称是拟实现契约，不声称基线已有：状态为 `IDLE`、`TELEOP_ACTIVE`、`TASK_ACTIVE`、`VALIDATION_ACTIVE`、`CLEANING`、`BLOCKED`；每个 reservation 绑定域、operation/command ID、payload fingerprint、service epoch、域 generation、runtime identity 和 owner。一个持久事务完成检查、intent 写入与 reservation，竞争请求只能有一个成功；检查后再 dispatch 之间没有可插入第二域执行的窗口。

| 操作类别 | 门控与 reservation 范围 |
| --- | --- |
| Teleop plan、execute、gripper、attachment、scene repair、home、reset、参数写入、workflow mutation、camera preset；Tasks start/recovery/shutdown 及写入运行现场的操作 | 先验证 capability、独立 lease/session、payload 和运行安全，再原子 reservation，之后才能 IPC/执行 dispatch。plan 也受默认只读策略约束。长 action 保留 reservation 到终态及所需清理，不在 HTTP 返回时提前释放。 |
| Validation start、FULL_RESTART retry 与其他改变执行现场的操作 | 独立 lease/generation、manifest、recovery/ownership/resource 门控与全局 reservation 同时成立才 dispatch；保持到 campaign 和 owned cleanup 收敛。 |
| manifest 创建、preflight、reachability、capture/render 等非运动写操作 | 使用短 reservation，验证身份后执行并记录终态；另一个运行域占用时拒绝。preflight 可返回只读的 blocked 原因，但不因此获得执行许可。纯历史/已冻结 manifest 的 GET 不抢 reservation；不能因“预览”标签默认豁免 POST。 |
| lease renew、读取快照/历史/证据 | 不抢运动 reservation；独立 authority 和现有未收敛状态规则仍生效。 |
| 安全 cancel/hold | 保留原安全路径，在对应 authority 下只作用于精确 owned 操作；不被另一域只读 banner 隐藏，也不成为任意 reset、open gripper 或 foreign kill 的 bypass。 |

所有入口，包括 legacy endpoints、workflow 内部执行、人工 retry、IPC handler 和后台 dispatch，都通过同一 arbiter；前端 disabled 仅解释服务端结果。参数或 camera 操作即使不直接运动，也不能在 Validation 期间悄悄改变其冻结 runtime。

命令 idempotency 绑定 command ID 和 canonical payload fingerprint；同 ID 不同 payload 拒绝，同 ID 重复请求返回持久记录，不再次执行。执行 intent 在 dispatch 前落盘，child 返回 accepted ACK 时记录实际 operation identity，再记录进度、终态和 cleanup 证明。进程存在检查或 in-memory active flag不能独立释放 reservation。

owner 未知、intent 没有可核验 ACK、进程身份漂移、旧恢复 fences、lease maintenance 失败或 cleanup 未收敛时进入 `BLOCKED`。即使页面报告 failed，仍不能 start 下一域。明确恢复操作必须走既有恢复授权及证据链，不以换页、重启服务或释放 lease清除 fences。

### 6.1 复合操作的父生命周期

Execute All改为一个服务端复合操作：新增 `POST /plans/{plan_id}/execute-all`，一次请求冻结plan ID、gripper target、canonical payload、runtime identity及execution generation，先持久建立parent ID与全局reservation，再由受控sequencer执行arm和gripper。响应可查询parent及每个child结果；前端不再以两次普通POST拼接Execute All。既有arm/gripper单步API继续存在，但不能借parent ID获取继承授权。

child身份由服务器产生并绑定parent、步骤和真实action identity。arm terminal至gripper dispatch之间仍是同一parent reservation，不经过`IDLE`；只有parent全部终态和cleanup证据收敛才能释放。arm失败不派发gripper，第二步失败保留部分完成记录；重复parent command ID返回原记录，不同payload拒绝。

在arm ACK、arm terminal、gripper dispatch之前分别重新验证owner通道、冻结generation/runtime及取消状态，但不重新争抢reservation。两步之间断线、取消、deadline超时或Web crash停止后续dispatch，保留partial/unknown状态；重连、旧客户端迟到gripper请求或重启都不能自动补完。安全收敛后如需进一步动作，必须由用户以当前现场重新确认/规划并创建新operation，不能恢复旧parent的未执行child。

home同样是包含planning、arm和gripper的parent，不在arm完成时释放。workflow的start/run、内部连续动作及后续step/resume绑定同一个run parent；HTTP返回或到达可续的pause checkpoint不算parent终态，reservation仍保留。pause后的resume必须显式由绑定controller以当前authority请求，且只能调用backend原有可续能力；force-continue保留原物理确认，不成为仲裁旁路。parent释放须完成真实终态和所需cleanup，或通过明确授权的abandon/reset事务证明owned action已停止、现场安全且checkpoint失效；单独删除checkpoint不足以释放。backend不支持的workflow stop仍不可用，不借新取消通道补造该能力。

## 7. 非 Web ROS bridge 与 crash 恢复

ROS child 由统一生命周期记录，但只拥有自己的 ROS client、线程和 IPC endpoint；不会因此获得已有 simulator、MoveIt 或 controller 的停止权限。启动使用固定 executable/模块与经验证的环境、安装前缀和配置，不接受请求提供 shell 命令、任意 executable、Python表达式或 ROS method 名。

IPC 使用私有 Unix domain socket、服务 epoch scoped token 和 peer UID 检查；目录/socket 权限限定当前服务 owner。协议显式版本化，封闭 schema、消息大小上限及有界队列在部署配置中冻结并校验，不支持 pickle 或任意对象反序列化。请求只包含 allowlisted operation、command ID、payload fingerprint、domain generation、runtime identity 和 deadline；大型相机/证据数据走既有受限 artifact 路径，不塞入控制消息。

每个 operation 有强类型 payload、范围校验和允许的 capability；IPC timeout 不放宽原 plan/action/cleanup deadline。child 必须在使用前检查 epoch/generation、剩余 deadline 和 reservation授权；过期排队命令不得稍后补执行。HTTP schema 校验不能替代 child 边界校验。

ROS child 的 owner-channel heartbeat/watchdog 独立于浏览器 lease 与页面订阅。Web 死亡、事件循环失联或 IPC 断裂时，child 停止接收新 mutation，并在既有安全 deadline 内请求取消/hold 自己拥有的 action；不能自动 reset 或打开夹爪。该内部安全通道验证服务 owner，而不依赖已失效的浏览器 lease。实际停止与 cleanup 仍须反馈证明，无法确认则保留持久 blocked intent，不能以 watchdog 超时当作停止 ACK。

ACK 区分 accepted、执行终态和 cleanup confirmed。accepted 不代表机械臂完成，也不代表安全停止。dispatch 与 ACK 之间断裂、执行中 child 死亡、未确认 cancel 或超时时，保留 intent 和 reservation，视图标 unknown/blocked；不能以 retry 同一 payload 开始第二次动作。

owner 记录采用已验证的精确进程 identity：PID、PGID、启动 ticks、argv/environment fingerprint、runtime generation/epoch，以及对应 control socket 和 campaign/operation ID；沿用 Validation `OwnedCoordinator`、`OwnedAdaptiveWrapper` 与 process-owner 的安全约束。PID 单独不足以证明归属。取消先走 owned control 协议，升级信号前重新匹配 identity；未知 same-UID 进程、复用 PID 或不可读身份 fail closed，不给宽泛进程组发信号。

Web 重启读取 durable journal、旧 intent/ACK 和 supervisor 状态，建立新的 service epoch，使旧 authority 失效。它只恢复可读 projection 与 blocked 原因，不自动接管存活 executor、不重发未确认命令、不启动 sim、不自动恢复 campaign。人工恢复须确认 fresh ownership、现有恢复 fences、installed provenance 和 cleanup，再按显式授权改变状态。旧 journal、receipts 与证据哈希保持不变，新增恢复记录追加。

Teleop IPC 断裂使 Teleop readiness 失效；HTTP 和可读 Validation 历史仍存活。如果断裂遗留可能运动的全局 intent，Validation start也被阻塞；只有能够证明 Teleop 无未收敛 owner 的“未配置/无 ROS”情形，才允许 Validation 在自己的安全域内操作。

### 7.1 独立安全调度与精确取消目标

浏览器安全cancel、lease-maintenance取消和owner-watchdog取消共享独立的有界安全lane，在Web和child两端都有专用处理能力及独立control IPC通道。它们不获取新的运动reservation，不等待普通`CommandCoordinator`锁、普通IPC backlog、执行线程池或action completion；不能沿用基线`cancel → _commands.run`路径。安全lane的持久状态更新只使用短临界事务，不把长action或远程等待放在该锁内。

浏览器cancel须验证该域当前绑定instance与有效authority，只能指向其owned parent/action；lease过期、maintenance故障或Web heartbeat丢失时，由内部owner安全authority处理持久记录中的action，不等待浏览器重新acquire。server/child保存独立arm、gripper及parent-child action registry，包含实际ROS goal UUID/handle、operation ID、冻结execution generation和runtime/process identity。不得用一个latest goal指针、只有PID或客户端任意action ID选择目标。

取消parent先原子标记后续child禁止dispatch，再按registry取消其活动child；重复cancel合并到同一记录，旧generation/action ID或foreign identity拒绝，不能误取消新action。Validation继续使用其精确owned control协议，但入口同样不等待普通业务reservation锁。workflow没有可证明的安全停止能力时显示明确blocked，不将一次HTTP取消响应包装为backend stop。

安全lane在配置中冻结正值的delivery与stop-confirmation deadlines及队列上限，均不得放宽原backend安全/执行/cleanup界限；运行能力启用前须证明在普通队列饱和和长arm/gripper action期间仍可按期送达。重复目标合并，队列满或处理故障立刻拒绝新运行能力、触发内部owned安全处理并保留blocked，而不是排到普通队尾。不能确认可靠取消能力的backend拒绝对应运行能力。

cancel accepted ACK只表示目标已登记并收到取消请求。原reservation持续保留，直到对应action terminal、实际停止反馈与所需cleanup成立；cancel delivery超时、stop超时或反馈缺失均记录unknown/blocked，不能以accepted ACK、timer触发或HTTP200释放。独立安全lane不授权open gripper、reset或foreign process信号。

## 8. preset 与组件迁移

只读 CLI 检查已得到以下 preset 元数据，未执行 `init`、`apply` 或 `add`。preset reference 为 `https://ui.shadcn.com/create?preset=b311momZs0`；这描述设计系统意向，不证明项目已安装或草图逐像素匹配官方组件。

| 项 | 已核验值 |
| --- | --- |
| preset / version / style | `b311momZs0` / `b` / `maia` |
| baseColor / theme / chartColor | `mist` / `blue` / `mist` |
| iconLibrary | `lucide` |
| font / fontHeading | `dm-sans` / `outfit` |
| radius | `large` |
| menuAccent / menuColor | `subtle` / `default` |

CLI 项目检查显示 base 为 `radix`，这是独立 primitive 配置，不是 preset 字符串编码的字段。本项目保留 Radix 方向；不能因 preset 切换而悄悄改成 Base UI。

实际源码在 `src/so101_teleop/web/`：`package.json` 和 `bun.lock` 使用 Tailwind `3.4.17`，`src/index.css` 是 `@tailwind base/components/utilities`，配套 `postcss.config` 与 `tailwind.config.ts`。CLI 自动检测曾显示 v4，不能以此覆盖实际 v3事实。已观察到 Bun `1.3.14`，实施仍需 fresh 工具链记录并遵守项目 Bun/锁文件规则。

采用完整 smart merge：先预览 registry 与 preset 对配置、主题、字体、依赖和现有组件的差异，再合入基础 tokens 和 primitives，保留业务 variants、ARIA、事件、disabled reason、测试选择器与安全门控。不能直接 force overwrite 全组件，不能只换几个按钮而留下旧硬编码 surface。既有组件需要逐项比对，新增 Sidebar、Sheet、Field 等仅在页面需要时引入，不使用 `add --all` 扩大范围。

设计系统迁移以真实 v3 为起点。若冻结后的 maia registry 需要 v4，则作为本重构内明确的兼容升级：一起迁移 compiler/PostCSS/CSS入口/tokens和组件依赖，固定经验证的版本与 `bun.lock`，完成构建和行为测试后才使用该产物。不得混用 v4 `@theme` 输出与未升级的 v3 编译器。本文不猜测尚未锁定的升级版本；实施计划应基于当时 registry manifest 固定精确版本，不用漂移的 latest构建生产产物。

统一 `background/card/foreground/muted/border/input/ring/primary/destructive`、Sidebar 与 chart tokens，连同字体、圆角、间距和 light/dark 成套更新。light 为默认，dark 可切换并持久保留用户选择。DM Sans/Outfit 配套中文系统 fallback；字体不可用不能阻塞控制，生产不依赖运行时外部字体请求。业务点位使用独立成功/待执行/失败 semantic tokens，不将蓝色 primary当成成功。

## 9. 稳定布局规格

用户批准 v2 草图的布局方向。临时文件 `/tmp/so101-debug-unified-webapp-design-20260918/unified-webapp-layout-v2.html` 的 SHA256 为 `c075978d6db51d4cd7e23ff94b28ab47370be562c2ee7cb09dec84a298727dbf`。它是本地交互示意，坐标、任务统计与证据占位不是实测；长期契约由本节定义，不依赖临时预览服务继续存在。

```text
┌──────────┬─────────────────────────────────────────────────────┐
│ Sidebar  │ 页面标题 / 两域健康 / 全局占用原因 / theme           │
│ Teleop   ├─────────────────────────────────────────────────────┤
│ Expert   │ Validation：模式 / 最终点位数 / exact N /资格/操作  │
│Validation├───────────────────────────────┬─────────────────────┤
│          │ 约 60%：真实等比例俯视图       │ 约40%：进度与统计   │
│ Tasks兼容│ 桌面/方底座/杯点/目标/坐标轴  │ 多列点位结果        │
│入口      │ 状态圈同半径，可选中点位     │ 点击 → 证据 Sheet   │
└──────────┴───────────────────────────────┴─────────────────────┘
```

Sidebar 只有 Teleop、Expert Validation 两个主要功能入口。Tasks 保持旧 `/tasks` direct route，并在 Teleop 现有 workflow/任务区提供兼容访问，不把它包装成新功能。共享 shell 不重复嵌套业务导航；窄屏 Sidebar 折叠成可关闭的导航 Sheet。

桌面 Validation 的配置条位于上方，图与结果约 `60/40` 分栏。地图容器占满左列有效宽度，不设小尺寸 `max-width`；按真实几何纵横比安排高度，必要的留白由几何比例决定，不靠裁剪/拉伸消除。右栏点位卡在宽屏三列、较窄两列，再窄时一列。页面整体可滚动，不把操作和20点结果压入不可达区域。

手机按配置、地图、进度、点位结果顺序堆叠；证据 Sheet 使用适合视口的宽度和内部滚动。`1400×900` 与 `390×844` 是必须检查的视口，页面无水平溢出。密集关节表可在自身受控滚动区域显示，不得使整个页面横向溢出。

### 9.1 Validation 数据与点位语义

最终点位数保持 `4..20`，包含四个固定点位。`PARALLEL` 的 worker selector 为 `2..8`，每批固定所选 exact N；`SEQUENTIAL` 为1，人工失败 retry 是独立 `FULL_RESTART` 单点、1-worker batch及统计记录。界面没有 K、max-points-per-worker或其变相容量输入。

资格来自预算 provider：逐 N 显示 available/unknown/rejected 和原因。未知或未达标禁用启动，不默认降为 N2、不替换为 ADAPTIVE。点数小于 N 时仍启动所选 N、允许部分 idle；不能把较低实际并发显示成 N。现有 ADAPTIVE affinity/fallback含义保持不变，不借 UI 重构修改其调度。

点位位置、固定点身份、桌面边界、底座和目标区取自 accepted manifest。沿用 `manifest_geometry.freeze_manifest_context(layout, selection)` 对 installed scene/policy/anchor/catalog 的校验和冻结，以及 `Projection.from_geometry(...)`、`project_xy(...)` 的单一 `pixels_per_m` 等比投影；前端对应 `components/expert-validation/projection.ts`。响应式缩放只能对整张图做同一比例变换，不能独立拉伸 X/Y、重新随机点位或复制草图坐标。source/geometry hash失配禁止新执行，旧 manifest仍可按历史读取。

机械臂底座以真实 `base_bounds` 方形轮廓显示；杯足迹和 target tolerance使用真实几何尺寸，不能与状态圈混为同一尺度。三类状态圈保持同半径：绿色成功、蓝色待执行/执行中、红色失败类；每个圈同时有编号、图标和可读状态。红色中的 `FAILED`、`INDETERMINATE`、`INVALID_BLOCKED`、`INFRA_FAILED_REMAINDER`必须按原状态明确区分，不能合并成抓取失败率；blue requeueable infra也有文字解释。状态 circle半径与业务状态、worker 或成功率无关，不修改冻结历史 marker尺寸；显示增强采用一致视图样式。

点位结果和图互相选择，展示 attempt、worker、业务结果与基础设施原因。证据 Sheet按真实 artifact registry读取图片、事件和物理证据；缺失/不可读时说明原因，不制造照片或用渲染图代替物理证据。旧 evidence/manifest/receipts保持原版本、路径与哈希，不能因主题变化重写历史。

### 9.2 Teleop 与旧 workflow

Teleop 保留关节实际值/速度/目标/限位和微调、TCP、夹爪、plan/execute/execute-all/cancel、collision与Planning Scene、attachment、home/reset、camera/screenshot、physics/backend 状态、参数和workflow/YAML工具、事件日志及 Tasks 的 sensor/point-cloud/evidence等已有功能。基线 capability决定哪些可用，不能为了图稿补造控制或参数。

臂区是五个关节，夹爪独立：基线 joint identifiers `1`–`5` 和 `6` 保留，不新增 J6臂轴，不把人体式名称写进后端协议。角度单位、TCP坐标系、safe limits、stale plan与simulation session检查保持原样。规划与执行分开，不把计划成功画成动作完成。

Validation 占用时顶部明确提示全局只读及 owner/campaign，相关控制 disabled并给出原因；仍可查看 telemetry、camera和已有证据。原安全 cancel在满足自己的 owned authority 时保持可达。低层 IPC断线、backend不支持或 lease失效各自解释，不能都显示为“请获取控制权”。

## 10. 与并行预算任务的接口

本设计只消费 [共享队列与资源预算设计](2026-09-18-so101-parallel-unbounded-queue-resource-budget-design.md)及其 [实施计划](../plans/2026-09-18-so101-parallel-unbounded-queue-resource-budget-implementation.md)，不另写资源公式、不制造资格数值、不修改 frozen profile或测量流程。该设计 SHA256为 `5e085f98e9926591fbefd3d6e16c16b33bfc9956df9221c46f383b310553657b`；计划 SHA256为 `cd1b606fd8a40d7bb6e576f6f59a6ef5abcb45a8bee7e2a669c7b7a40bfc8789`。

Web capability/preflight/start读取同一版本的 provider决策，包含 selected N、当前环境/runtime identity、qualification状态与拒绝原因；start仍做实时检查，不能信任页面缓存。未来 v2接口实施前不得声称当前基线已经有无K资格 provider；整合必须基于其最终独立审查通过的接口，不建立旁路。

统一 Web、ROS bridge、IPC线程、共享 subscriptions和新 background进程会改变有效 runtime footprint，必须按预算的 acyclic code/config/install身份契约重新计算 R。R变化后旧预算不能复用，即使 N或抓取算法没变；需要新候选测量、独立审查及 operator promotion。纯 metadata变化只按该契约的等价性规则处理，不能以“UI改动”擅自排除实际执行 bytes。

资源资格与业务成功率分开：完整有效证据下的业务 `FAILED`不自动证明资源档不可用；infra中断、freshness/deadline越界或 unknown不能记为稳定资格成功。界面与统计遵循原分类，不把文档审查 PASS、policy DONE或演示数据当运行验证。所有 N不必被强行启用；只启用当前已证明且批准的档位。

## 11. 迁移与分层验收

迁移在独立工作树进行，先完成接口、持久仲裁、非 Web bridge、路由与UI，再冻结代码/锁文件并验证安装来源。运行窗口、旧服务替换、owned进程停止和profile promotion分别取得授权，不能因设计批准而自动执行。既有服务若仍存在，先 fresh记录 owner与任务状态；不能凭历史 PID重启或停止。新入口之外不遗留旧 Web listener。

| 层 | 必须满足的验收 |
| --- | --- |
| 源码与安装 | 无 ROS环境可导入聚合 factory；一个 Web入口/监听端口/已验证 bundle；实际 executable、package prefix、code/config/install identity与冻结记录一致，Bun锁文件可复现。 |
| API与路由 | 原Teleop/Tasks/Validation客户端路径与DTO回归；单OpenAPI无重复operation；`/tasks`不被独立server deny覆盖；direct refresh/back/switch可用；API/artifact未知路径不返回HTML。 |
| authority与竞争 | 双向并发start/execute/retry/recovery竞争只有一个reservation成功；全部legacy/internal入口覆盖；idle lease不会代替运行许可；续约不被长动作饿死；stale generation、未知owner和cleanup未收敛拒绝。 |
| durability与IPC | dispatch前intent落盘；同ID不同payload拒绝；ACK各阶段清楚；timeout、丢ACK、worker crash和PID复用不重复执行或foreign signals；Web restart保持blocked/可读历史而不自动接管。 |
| 域故障 | ROS缺失/IPC crash仅降低Teleopreadiness，HTTP仍可查历史；未收敛运动intent仍阻塞Validation；lease maintenance失败保留原安全取消例外及mutation fence。 |
| 浏览器状态 | 切页不停止heartbeat/任务；多标签authority不混用；断网/重连序列缺口补快照；session/generation变化清除旧执行许可；无事件驱动命令回放。 |
| 复合操作断点 | 在Execute All的arm ACK、arm terminal、gripper dispatch前竞争Validation start均拒绝；覆盖arm/第二步失败、两步间断线/取消/Web重启、parent重复或payload变更，迟到gripper不执行。home与workflow child terminal、pause、显式resume、abandon/cleanup各切点均不提前释放parent。 |
| 安全lane断点 | 长arm和gripper action加普通队列饱和时，浏览器cancel按deadline到达精确goal；验证lease过期、maintenance故障、Web watchdog失联、重复cancel、旧goal与foreign identity。delivery/stop deadline、队列饱和和lane故障分别注入；accepted后未证实停止仍阻塞Validation，不能只测按钮或HTTP。 |
| controller实例断点 | 两个document复制同一有效lease/session/generation，同时及交替mutation/renew只有绑定实例成功；覆盖duplicate/refresh/BFCache、同document重连及旧channel迟到、handoff竞争与未收敛owner拒绝。SPA切页不新登记，renewal不改变action execution generation，旧客户端mutation无authority拒绝。 |
| 布局与无障碍 | 两个指定视口无页面水平溢出；地图占满左列且X/Y等比/不裁剪/真实坐标，全部状态圈同半径；light/dark对比、键盘、focus恢复、Sheet关闭与读屏状态有效，状态不只靠颜色。 |
| 兼容业务 | 原关节/TCP/夹爪/physics/scene/参数/YAML/workflow/Tasks能力回归，真实5+1；业务/infra/invalid分类与独立FULL_RESTART N1 retry不改变。 |
| exact N与资源 | Chrome逐一查看N2..8资格/禁用原因及4..20点配置，已批准档以实际N运行、不静默降档；新R完成适用资格后才生产admission，不要求未合格档伪造PASS。 |
| live物理与视觉 | 经批准的仿真窗口使用fresh Chrome截图及独立MuJoCo/MoveIt/controller/joint/TF/pose/contact证据验证原流程；页面状态、action成功与物理结果分别核对。若宣称全流程连续成功，仍需skill要求的五次有效成功，不以草图或provider资格代替。 |

实施验收先定向自动回归，再包级门控，最后授权live复现。普通 `so101_demo_py`只收集 `src/so101_demo_py/test/`，本重构不运行benchmark suite。ai-station的fsync-heavy pytest/colcon fixtures仍须每次唯一NVMe scratch及实际test Python的`tempfile`证明，保留elapsed与退出码；本轮不执行这些测试。

设计任务唯一证据根为 `/tmp/so101-debug-unified-webapp-design-20260918/`，持久账本为 `docs/experiments/so101-unified-webapp-design-experiment-ledger.md`，由主协作者单写。临时v1/v2草图与浏览器截图保留为设计证据，不是生产证据；不删除或归档本轮已有记录。后续实施、live资格与并行预算任务按各自已登记根和所有权管理，不能为同一任务临时复制出第二证据根。

## 12. 交付判定

本文固定已批准的设计范围。独立审查通过后仍需用户审阅书面设计，再编写实施计划；计划批准不等于部署、恢复、profile promotion或真实机械臂授权。

尚未产生新产品代码、ROS bridge、合并server、preset安装或新资源测量。因此不能声称单端口服务上线、所有N合格、旧campaign恢复完成或原功能已运行通过。后续审查应重点核对跨入口仲裁闭合、IPC未确认结果的fences、真实v3兼容迁移和新runtime的资格失效边界。
