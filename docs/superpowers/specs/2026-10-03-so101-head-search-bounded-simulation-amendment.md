# Head Search 有界仿真搜索修订

授权：`18307FF0-5891-462D-A26B-580868C007D2`。适用范围是 antzb 上现有 worktree 的 MuJoCo Head Search；执行方式是 GPT-6.1 Sol / High、inline self_review。设计和计划编写后按本次授权实施，不另等同范围批准。数值 bundle 的精确人工批准仍保留。

## 目标与依据

完成合法区间内的有界搜索、正确杯子的可靠锁定和异常后的实际停止。Head 允许感知丢帧、慢推理及有限重观察，全部事件留存。监督失效、身份错误、未知 action acceptance、无法证明停车仍是失败。

HS394 使用 Source `87b88febd0781baa779bfce42b88d468ec4f1bc3`，实际完成 86 次 exposure，随后 Root gen2 GC 停顿约 95.07 ms。CPU 在最早旧 fault 后约 1.48 ms 获得 native close ACK，约 24.88 ms 确认停车；Root 的旧 10 ms 门仍失败。该运行保持 REFUSED。HS395 的 offstack 四组默认 GC 测量表明 Torch 常驻对象和完整历史 cohort 都增加停顿；这些合成分配测量不能证明 live 停止性能。

继续为每帧建立 2/10 ms 上层硬门会偏离本仿真目标。单纯放大所有 `.010` 无法解决旧结果使用和运动期间推理。采用已有停点搜索并调整明确的 policy，是本次选择。保持原流水线再隔离所有 Python 堆需要更多资源和接口；连续实时感知控制器则改变已批准搜索方法，两者均不纳入此次实施。

## 替代关系

本文件在以下列明范围内优先于旧设计。旧文档、批准和失败结果保持原字节/结论。

| 旧来源与条款 | 本次替代 | 保留部分 |
| --- | --- | --- |
| 2026-09-30 设计 §7.1 `search_timeout_s` 的停点 p99 推导 | 搜索采用事先配置的有限 wall budget，默认 30 s；记录原测量分布和耗时，不从 held-out 结果调参 | 17 个名称和单位、有限停点和精调上限 |
| 同节 `max_age_s = p99.9 + 10 ms` 且超限必须修零超时流水线 | 有效结果年龄为事先冻结的有限预算，默认 0.15 s、仍不超过 0.15 s；迟到结果丢弃，可有限重观察。所有完成/丢弃年龄分布分别报告，不借过滤样本重算旧公式 | 原始 receipt、图像身份、frame/TF/joint 因果配对 |
| 同节 `stop_latency_s` 的 p99.9 + period 推导与旧约 70 ms seed | 故障确认至完整停止证明的事先冻结 wall budget，默认 1 s；每次故障都必须满足，无分位数豁免 | actual stop predicate、全部 UUID terminal/rejected、三个 distinct post-request quiet originals |
| 2026-10-02 freshness 的固定 2 ms poll、每个 gap/RPC 10 ms、native close 2 ms、joint/camera 两 period 的默认硬门 | 下表逐项配置；监督新鲜度不等于 RPC 等待。native 协议仍有独立有界 deadline，具体 transport consumer/readback 必须同步 | 原始时钟、鉴权/sequence/peer、epoch、native gate、不可复活和安全 lane |
| freshness/source-margin 的无 provisional fallback、17+8 审批和完整 population | 新增 `simulation_policy` 有版本及 hash，明确采用新的配置规则；8 项旧 feedback 名称继续回读，新监督/搜索项独立回读 | fresh run、全部原始 cohort、declared owners、无 clamp/删除异常 |
| primary-fault 的 10 ms common reaction / 2 ms socket timing | 配置的 reaction/native/stop 三段分别验证，最早确认故障开始 stop deadline | 三个独立 native endpoint、capability/peer、latch、并行 cancel/strict-close、完整 terminal reconciliation |
| 原设计 §10.3、smoke/scenarios/aggregate 的连续 10 Hz 无 gap 与每次 inference 完成门 | producer 仍配置 10 Hz；消费端 gaps/expired/miss 是记录并分类的事件，正常 run 在次数和总时限内允许重观察 | sealed 数据集无损、真实 producer 原始身份、正确 lock、40 seed 和三个 anchor |
| runtime plan revision 4 的 phase-7 zero-timeout 硬门 | timing phase 记录所有尝试及事件，验证本策略、轨迹和停止；发生不可恢复故障整个 run FAILED | 正式八阶段顺序、入口绑定一次、无 resume、人工批准/单次 promotion |

frame-identity、reservation-binding、undeclared-fields 的身份/鉴权/闭合 schema 条款不替代。ACT Recorder 的无损、10 Hz 连续性和独立 QC 均不修改。后续 W2 -> 独立 exact-W8/40 顺序保留，不执行 W4/W6。

## 配置、clock 与 owner

新增 `HeadSimulationPolicy`，只能由正式入口从显式、封闭字段配置绑定一次。`schema_version=1`、`mode=mujoco_bounded_stop_search`。旧配置走旧规则；无法把新字段混入旧 policy 自动放宽旧门。bool、非有限、非正数、未知字段和不成立的关系拒绝。所有预算以原始 nanosecond 比较，边界到达即不再开始新操作。

| 字段 | 默认值 / 可配置上限 | 含义、起点、clock、owner 和判据 |
| --- | --- | --- |
| `heartbeat_rpc_timeout_s` | 0.25 / 1 s | 本次 authenticated RPC 开始至完整验证 reply；monotonic，IPC worker。超时进入失去准入的等待态，不能重发同 sequence；在监督 stale 到达前只允许恢复同连接的完整正确 reply |
| `supervision_stale_s` | 0.5 / 2 s | 最新原始 executor progress、实际 peer progress 和成功 heartbeat 所携带 progress 的最早 expiry；monotonic，两侧 supervisor。到界 irreversibly REVOKED；旧/负 ACK 不续期 |
| `watchdog_period_s` | 0.02 / 0.1 s | 各 supervisor nominal scheduled loop；monotonic。记录真实 intervals；单个 gap 不直接失败，超过 supervision predicate 才 fault |
| `fault_reaction_limit_s` | 0.25 / 0.5 s | 最早确认 fault 至本地准入关闭、native fault-close 请求及 scoped cancel 发起；monotonic，实际可运行的安全 owner。原始两个流分别报告，不伪造被暂停/死亡 owner 的反应 |
| `native_close_timeout_s` | 0.05 / 0.25 s | close 请求的 connect/frame/validated ACK deadline；monotonic，各 native endpoint/客户端。迟到/错 ACK 不算 closure，仍取消并在总 stop budget 内对账 |
| `stop_confirmation_timeout_s` | 1 / 3 s | 最早确认 fault 至 native closure、完整 UUID terminal reconciliation、actual predicate、三条 post-request quiet originals 全部成立；monotonic，Root 或 CPU 的独立缓存。缺一即 FAILED_STOP_UNCONFIRMED |
| `perception_max_age_s` | 0.15 / 0.15 s | 原始 image/CameraInfo receipt 至准入、结果返回、实际使用；monotonic，capture/inference/search。每次使用均验证；过期只丢弃，绝不重写时间或增 lock |
| `perception_job_timeout_s` | 1 / 3 s | 从 Root 首次选定原始 image/Info pair 到正确 completion 解除租约；monotonic，唯一 inference owner。预算包含 CPU 准入等待，实际 CUDA 开始和返回时间另行记录；同一候选 pair 的期限不续期。年龄先到期则丢弃结果，已准入 job 仍被占有，不能并发另起 detector。job 超时结束 run，安全 owner证明停止、精确资源退休 |
| `camera_loss_timeout_s` | 0.5 / 2 s | 最新有效 advancing camera 原始 receipt 至现在；monotonic，两 reader 独立。短 gap 等待，持续 loss fault |
| `feedback_receipt_timeout_s` | 0.25 / 1 s | 当前原始 joint/clock receipt 至 decision；monotonic，两个独立 reader。超界 fault，不用缓冲旧样本刷新 |
| `joint_source_age_s` | 0.05 / 0.1 sim s | decision node sim time 减原 joint source；各 reader。未来、倒退、过界拒绝；不与 wall budget 相加 |
| `camera_source_age_s` | 0.2 / 0.3 sim s | decision node sim time 减原 image source；各 reader。用于 admission/use，过界丢弃，持续 stream failure 由 wall predicate 判定 |
| `search_timeout_s` | 30 / 120 s | 搜索入口第一个 decision 至业务终态，涵盖运动/停稳/等待/推理/重观察；monotonic，search owner。停止证明可另占明确 stop budget，终态须报告两者 |
| `max_reobservations_per_stop` | 3 / 10 | 单个停点允许额外获取新图的次数；严格整数，search owner。初次观察不计，miss/expired/drop 各占一次 retry；预算耗尽移到下一停点 |
| `max_reobservations_total` | 12 / 40 | 全搜索额外观察总数；严格整数。用尽后得到明确业务耗尽终态并证明停止，不重新创建 run/epoch |

关系：period < RPC < stale；reaction + native < stop；feedback receipt 和 camera loss <= stale；perception age <= job timeout；search > stop；per-stop retries <= total retries。`FeedbackPolicy` 的八个 consumer 在新模式分别从 receipt/source/camera-loss/source/receipt/period/reaction/native 字段映射，并在两个进程读回。`max_age_s`、`search_timeout_s`、`stop_latency_s` 与对应 simulation 字段必须完全相等，不存在双重有效值。

上述默认值是仿真工程预算，不是已批准 bundle 或硬实时保证。95 ms 的实际 GC 是选取 250/500 ms 监督预算的依据之一；停车 1 s 留出独立 cancel/terminal/三样本处理窗口。最终 moving/fault 实测仍必须验证这些预算和整个运动区间。若实际停车或合法轨迹无法满足，保留精确 blocker，不靠重观察掩盖。

## 停点状态机

`BOUND_ENTRY -> MOVE_BOUNDED -> WAIT_TERMINAL_AND_SETTLED -> ACQUIRE_NEW -> INFER_STOPPED -> VALIDATE -> LOCK / REOBSERVE / NEXT_STOP -> BUSINESS_TERMINAL -> STOP_PROVED`。

每个 native/SDK 目标发送前验证完整轨迹、合法区间、generation、inventory、fresh supervision 和当前 feedback。安全区间使用已有 MuJoCo 几何，不新造硬件认证。轨迹插值、中间位置和实际角度/速度均留证；只有 target 点合法不够。每次 coarse/fine 运动更新 motion epoch；所有已开始 action 都获得 terminal/rejected 和至少三条 advancing settled samples 后才启动 YOLO。初始停点也要实际确认 settled。

新图必须严格晚于当前 motion epoch 的 settled source floor 和获取请求的原始 wall floor。同一 image 只准入一次。capacity-one pending image 可以被最新图替代，替代事件完整记录。推理期间没有未完成 neck action；唯一模型/追踪器和 inference owner 不重绑定。返回后验证 session、attempt、native generation、motion epoch、frame、payload、source/receipt、TF/CameraInfo/joint 因果关系和 age。错误身份属于安全故障；正确身份的过期结果属于丢弃事件。两者都不能发目标或增加 lock。

可靠锁定保留同一合法 track、deadband、vertical bounds、置信度/面积门和三个 distinct、advancing、新鲜 settled frame。miss、expired 或换 track 清零连续有效锁定计数；重复 frame 不增加计数。fine correction 也必须走 MOVE -> SETTLED -> NEW_IMAGE，受原精调次数/累计角上限约束。正常重观察不更改 search 起点，也不恢复 FAILED run 或 REVOKED generation。

未找到或观察预算耗尽产生明确 `TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL` / `SEARCH_TIMEOUT` 等业务终态，记录完整停点覆盖和停止证明。qualifier 按事前冻结的场景类别判断，不把 nominal 超时算成功。任何未知 acceptance、通道协议损坏、peer death、身份错误、持续 feedback/clock/camera loss 都关闭准入并走 safety lane；fault generation 在新 controller incarnation 前不可复活。

## 慢 RPC 与 fail-closed

RPC 超时不是 process death。原 codec/MAC/sequence 和 peer 验证保留。旧 channel 的 partial frame 不能复用成下一次调用，也不能在 timeout 后创建第二 channel 来恢复 authority。IPC worker只继续有界完成同一在途 frame，owner 在无完整 fresh reply 时禁止 reserve/send。stale 到界或协议/连接真实失效即 fault。恢复的 reply 携带的原 progress仍必须新鲜，REVOKED 不能转回 READY。

故障后本地关闭准入先于排队操作；每个 worker 在 reserve 和实际 send 前再验证。独立 native fault-close 与 cancel 同时发起，cancel ACK/exit/瞬时 quiet 都不代表停车。native closure ACK 必须对应精确 peer、generation、incarnation 和状态。late acceptance 必须有权威拒绝或 terminal 对账。最早 fault crossing、request wall/sim、原始 quiet samples、各 decision clock、actual predicate observed time 都进入证据。

正常资格运行要求两个 sealed original streams。故障注入导致 peer 被杀时，保留原始不完整流、死亡证明和仍存活 owner 的独立停证；该 run 明确 EXPECTED_FAULT 或 FAILED_STOP_UNCONFIRMED，不伪造死进程 ACK/seal，也不作为正常成功。fault-control aggregator 从 raw evidence 判断故障是否按预期被 containment，并与正常资格 aggregator 的成功分开。

## 正式程序与证据

保留安装入口 `so101_head_search_calibration run`、`verify-promoted-config`、`qualify`。八阶段固定顺序；正式入口构造一次 native/ROS/camera/TF/detector/recorder-refusal/measurement admission，先检查全轨迹 precondition，再进入允许运动的阶段。普通 diagnostic 不代替正式入口。受控 source/config/policy 变化使旧 bundle/live/QUALIFIED 失效；新 attempt 在同 evidence root 下使用从未存在的新 run ID，无 resume。

policy schema、config digest 和实际 consumer readback 链接 bundle、每个 run 和 journal。新事件至少包含 scope/identities、motion epoch、frame identity、original clocks、事件原因、retry counts、deadline、reservation/UUID/terminal chain。producer 不自报合格；独立磁盘 aggregator 重建所有观察、命令、lock、fault 和 stop。缺失事件、未知 schema、过期动作/lock、未申报配置或丢失原始证据都拒绝。

记录正常/异常成功率分母、总 wall/sim 耗时、RTF 观察、丢帧/过期/miss/重观察数量、旧结果误用数量（必须为零）、实际位置/速度范围和停止状态。seed、配置和故障注入在运行前封存，不删 outlier、不按结果改阈值。

新 bundle 呈现 17+8、全部新增 policy 字段、单位、默认预算与实测分布/公式、源和运行 owner、所有依赖 SHA。精确人工批准 bundle digest 后一次 promotion、verify、freeze。sealed 数据/权重只读复用；held-out/40 seed 不参与校准调参。

## 真实验收

定向 RED/GREEN 后，冻结代码并使用实际 installed formal/default composition、producer -> sealed journal -> actual aggregator：正常有界运动/停稳/锁定；延迟/过期/短 gap 后有限重观察且旧结果误用为零；持续 feedback 失效；监督 process death/真实 channel loss；unknown acceptance/cancel/stop ACK 异常；同 fault generation 复活拒绝。每项保存实际 argv/rc/状态/原始流和 owned teardown。

完整普通 xdist/package/native gates 在计划指定集成边界运行，缺失 ACT baseline 文件仍报告，不缩范围、不反复全量。benchmark 只在模型选择或 benchmark 实现改动时按原规则运行。40 个 held-out qualification 场景和 default/left/forward 各一次 FULL_RESTART 保留。Teleop 使用实际原始/overlay 配对、新鲜且实际查看的桌面/窄屏截图、Bun/Playwright、ownership/conflict/stale/stop 控制；浏览器 latest-frame 不产生训练或生产反压。

只有所有修订功能门、当前 package/native、精确批准/配置回读、40/三 anchor/Teleop 和独立 evidence recomputation 成立才标记 HEAD_SEARCH_QUALIFIED head-only。独立证据计算不等于已被用户取消的独立 agent review。不得宣称 ACT/Task8/硬件 readiness，不 push，不删除 evidence，不创建第二 executor/worktree/stack。
