# 审查：SO-101 ACT 容器化采集执行计划

审查对象：[执行计划](2026-10-11-so101-act-containerized-campaign-implementation.md)。设计依据：[已审设计](../specs/2026-09-30-so101-act-containerized-campaign-design.md)。源码基线为 Gitee `origin/codex/so101-act-data-0917a` 的 `6baf54e6313daca287fa86e7cc248c4c2f1b1dc3`，不以本地旧 main 代替。

用户本次明确要求 GPT-6 Astra / High 独立审查，因此作为仓库 Sol 自审规则的本次例外执行。后续 `dst` 实施 checkpoint 仍按仓库规则由执行机上的 GPT-6.1 Sol / High 审查。本记录不授权实施，也不表示运行验收通过。

最新状态见文末“用户批准的简化修订（2026-10-12）”；下面的 Astra PASS 仅适用于其历史冻结稿。

本次文档任务登记的证据根：`/tmp/so101-debug-container-plan-20261011-zmN9PDXR`。只保存源码只读快照、审查冻结稿和任务 manifest；未运行测试、Docker、ROS/MuJoCo、SSH 或真实硬件，未 commit/push。

## 首轮：CHANGES_REQUIRED

冻结稿：`plan-review-round1.md`，357 行，SHA256 `4e694eb859629b98744a821693a4588b68fc079165772e285f152758104179c4`。Astra 首尾复核 hash 相同，结论为无 P0、4 项 P1、1 项 P2。

| 级别 | 必须修订项 | 核验依据与修订 |
| --- | --- | --- |
| P1 | 正式 CLI 没有接通真实准入与执行 owner | `act_collect_parallel` 读取不存在的 context，普通字典和第二位置参数不符合 `UnifiedWorkloadService.start(OperationSpec, *, allow_existing)`。计划补完整生产链、单 composition、真实 CLI 集成测试和 cleanup 后 finish；不把 admitted 当采集完成。 |
| P1 | 校准/Head Search/live 接线晚于镜像冻结，首轮校准存在报告依赖 | `calibration_production_composition` 仍构造本地 detector/MuJoCo，live case factory 仍构造宿主 stack。计划把实际 provider 和 container port 迁移移到冻结之前；首轮明确受限测量准入与正式绑定的不同条件、Head Search 来源和 promotion 审批，不借旧 READY 绕过。 |
| P1 | 外层路径翻译不能解决嵌入绝对引用 | calibration sample、Head Search reader、bundle_root、offline result 和结果 entry 含本地绝对路径。计划补完整 writer/schema/reader 迁移、各 root 的受限解析以及同 bytes/hash 的 Host/容器双视角测试。 |
| P1 | 私有 PID namespace 破坏 watchdog/ready/stop 身份 | bridge 注入 Host PID，child 用 kill 检查，ready 又比较 Host Popen.pid。计划区分容器与内层进程 owner，补控制 heartbeat、namespace 内 readback、generation-scoped stop 和 PID 碰撞测试；禁止 host PID namespace 绕过。 |
| P2 | 资源指标只有消费者，没有完整 producer/固定集合 | 既有 telemetry period、bag stats 和空 stall telemetry 不能提供全部观测。计划补 collector/raw sample/metric registry/reducer/coverage 与 stop_dispatch，磁盘资格重算消费同一原始流；数值门槛仍需来自批准配置。 |

额外自检补充：admission 冻结的逻辑 Worker slot 与累计实际容器 launch 分开登记；wave/case 更换 session 不得修改原 context hash，也不能导致 `finish` 误把所有容器数当 Worker 数。

## 第二轮：PASS

冻结稿：`plan-review-round2.md`，465 行，SHA256 `0c2512dda53d265467b76352f8b4b205483528865b0f1c1c8a918136075046ab`。同一 Astra / High reviewer 首尾核对 hash 一致，复审结论为 **PASS，无剩余 P0/P1/P2 必须修订项**。

| 首轮问题 | 第二轮冻结稿中的处置 |
| --- | --- |
| 生产调用链 | 238–241 行：真实 composition、正确 OperationSpec/start、owner→close→finish、无 factory 替代测试、slot 与 launch registry 分离。 |
| 校准与 live 接线、首轮循环 | 322–359 行：实际 provider/入口在冻结前迁移；首轮受限测量→Head Search 来源/审批/反读→完整 21 项→READY→activation/live。 |
| 跨视角引用 | 120–135 行：嵌入引用及全部业务 reader 迁移、明确根边界、同 bytes/hash 双视角测试。 |
| namespace ownership | 211–219 行：两类 owner、heartbeat、内层 ready、stop/exit/cleanup 及 PID 碰撞/陈旧身份拒绝。 |
| 资源观测 | 252–284 行：真实 producer、固定 metric 合同、coverage、在线 guard 与独立磁盘重算；缺批准门槛仍停下。 |

审查另外核对了 `head_search_aggregate/aggregate.py:179–189`：九项 qualification gates 成立后可发布 Head Search 资格；Teleop acceptance 属于另一个最终 verdict 门。不能仅因最终 verdict 尚未通过，就断定首轮一定存在循环。实施仍需从“没有本轮 READY”的真实起点执行计划要求的依赖链测试，不以这次静态判断代替测试。

最终持久计划只更新第 13 行的审查状态和链接；实现步骤与第二轮冻结稿完全相同。本轮最后核验包括两个新文档的 whitespace 检查、全部相对链接、所有 zsh 命令块语法；没有执行这些命令块中的测试或服务。

## 范围与证据保留

静态 PASS 只能证明计划的实现步骤与验收边界可供执行。真实 CUDA/EGL、容器权限、测量/Head Search promotion、9+5 live、W1/W2、独立 40 场景 exact-W8、正式采集及训练输入，均需后续各自的执行证据。

保留本次 manifest 和全部审查冻结稿；没有 archived run。源码只读快照在反读后列为删除候选，未经用户明确授权不删除。旧 ACT durable evidence root 和所有旧实验不移动、不改写。

## 后续执行计划审查的修订处置（2026-10-11）

本节回应[后续审查](../reviews/2026-10-11-containerized-campaign-plan-review.md)的5项P1、7项P2。上文Astra第二轮PASS只对其记录的冻结hash有效；“步骤与第二轮冻结稿相同”也是当时状态，不适用于本次修订。此次按仓库规则由执行文档修订的Sol会话内自检，没有重新派发Astra，也不把静态修订记为代码或运行PASS。

| 意见 | 本次处置及执行时所需验证 |
| --- | --- |
| P1-1 教师模型写死 | 推理合同步骤明确首份model ID、完整权重hash及0.25来源，新增detector/factory显式注入；其他业务默认值保留。后续合法权重/阈值配置变更不改source/runtime受控hash，head不串配置；镜像依赖变化仍受控。 |
| P1-2 macOS共享代码 | Worker接入列出实际policy、request/outcome/provenance/rpc_proxies及旧Broker/transport/Snapshot/image/macOS端口。ACT走新YOLO-only接口，旧接口仅供另一业务，保留Grounded/MPS；以调用链扫描及定向回归证明隔离。 |
| P1-3 outcome归类 | 闭合8项wire映射加本地R6拒绝；INPUT_INVALID/QUEUE_FULL归INFRA_ERROR，其余沿用既有infra INVALID、模型失败FAILED。QUALIFIED只是候选，经R6/latch才继续；逐项参数化测试，不删infra分母。 |
| P1-4 用户选择只卡数据质量 | 同步设计及计划：仅Recorder丢失、10Hz间隔、QC合格率、Teacher物理成功率为指标硬门槛，沿用已有规则。其余资源/吞吐只观测、limit等为null；磁盘见底/真实数据损坏/服务故障停派。身份、exact40/两wave、零infra、cleanup仍必需，不创设容量预算。 |
| P1-5 测量/live服务所有权 | 新共用ContainerServiceOwner。measurement入口单次受限准入、仅head、独立flight；live外层一次准入并启动两服务，14个局部case不再全局start/finish。明确非wave前缀、退役顺序、roles及payload拆分，诊断不继承W8；测试全局lease跨case保持且只finish一次。 |
| P2-1 schema与旧writer | 最终报告parallel-qualification-schema.json与预运行parallel-qualification-contract-schema.json是两类业务文件；点名替换旧create_qualification_contract/require_collection_mode/QUALIFICATION_KINDS，W1/W2另用闭合功能合同，拒绝冒充W8。 |
| P2-2 Worker预留 | 每wave前16scene按manifest相邻两项各预留给八Worker，完成自己的两项后可拉取余下4项。极快/极慢调度测试及独立receipt重算，失败不抢预留项补资格。 |
| P2-3 head绑定 | head模型/阈值/线程/interop及torch/ultralytics版本从绑定派生并校验，运行证明移入模型子进程；不是教师运营参数。首次受限measurement候选例外单列，不扩大正式准入。 |
| P2-4 head超时 | staging前起算端到端等待，计入本campaign批准perception_job_timeout_s；1.0s仅候选。保留max_age ≤ job_timeout ≤ stop_confirmation_timeout。 |
| P2-5 Snapshot字段 | ACT新合同禁止start_event_id/start_event_type/start_identity及旧compat字段；macOS仍用的公共Snapshot/transport不全仓删除。 |
| P2-6 类别映射 | HeadIpcDetector按受控class map转回plastic_cup/cup，未知类拒绝，教师与head映射分别冻结并测试。 |
| P2-7 文档与测试布局 | guide注明基线分支缺失，在集成交付步骤创建/核对导入；不让执行者等待不存在的链接。新增测试镜像runtime/inference与runtime/container_campaign目录，不新建test/integration旁路。 |

自检额外消除两处跨段矛盾：资源/吞吐旧“全部达标”措辞已从W8与故障条款移除；case级owner不得释放外层campaign的GPU lease/fence。配置中的qualification_contract在非W8业务为null，首轮measurement不要求未运行Teacher的ready或W8 receipt。

本次文档证据根：`/tmp/so101-debug-container-plan-revision-20261011-vs46oqKc`，登记manifest及修订前后快照。静态核验范围为12项映射、设计/计划一致性、链接、空白和zsh命令块语法；未执行命令块中的测试或服务，未实施、dispatch、SSH、commit或push。保留该根及历史审查根，未新增archived run或删除候选，未删除任何证据。实施仍须用户明确批准。

## 用户批准的简化修订（2026-10-12）

本节是当前设计与计划的最新处置，取代上文涉及路径格式迁移、staging、Host 接管、完整资源指标框架和三个镜像的实施要求；其他仍适用的审查意见保留。历史审查输入、冻结 hash 和 PASS/CHANGES_REQUIRED 原文不改写。本次 Sol 按仓库规则在当前会话内自检，没有重新派发 Astra；文档批准不授权实施。

用户要求保留一个可配置证据 ROOT，方便不同机器使用不同存储位置；其余按简化方案修改。当前[设计](../specs/2026-09-30-so101-act-containerized-campaign-design.md)与[执行计划](2026-10-11-so101-act-containerized-campaign-implementation.md)已作如下调整：

| 决定 | 当前合同与替代步骤 | 保留的边界 |
| --- | --- | --- |
| 可配置 ROOT、同路径挂载 | campaign 配置新增 evidence_root，与启动入口登记值一致。Host 派生新 run/shard/measurement/live 目录，私有证据以同一绝对路径 rw 挂载，所需批准输入同路径 ro。取消约 25 个 artifact writer/schema/reader 的批量相对引用迁移及通用 resolver。 | 不挂宽 ROOT、不暴露其他 shard/Host journal；既有绝对及相对引用、hash/QC/seal 原合同不变。ROOT 只影响新运行，旧证据跨机需原路径只读映射或另获批准迁移，不能自动改写。 |
| RGB 直接走 Unix socket | 唯一有界 binary envelope 包含 JSON header 与 RGB8 payload；不再用 request-ID 文件、0400、文件 no-follow、运输用 SHA 或只增不删 staging。取消 staging.py 及对应 mount，新增 codec.py。 | 先验证帧长/shape/byte_length，有界接收/队列/执行/回复，RLE mask 不截断；measurement/Recorder 原始 RGB/hash 仍留证。head deadline 从序列化前起算，source stamp 不改成发送时刻。 |
| Host 崩溃结束旧 campaign | 移除 service_state、accepted_total、双次零在途及全历史 seen-ID。只清理已确认 owned 的旧 generation；新 campaign 必须有旧资源终止证明、用户许可和新 run/ID。 | heartbeat/controller stop、namespace ownership、generation-scoped/single-flight cleanup 和未知 owner fence 保留；Host 活着时单 shard 故障仍按既有合同处理，已 commit 不自动重采。 |
| 资源只记日志、磁盘停派 | 复用已有读数写低频日志；取消通用 14-metric registry、闭合 raw schema、reducer 和 coverage。发 lease 前检查真实 ROOT 文件系统的空间，沿用批准下限；无下限时按无可用块/ENOSPC 停派。 | 四项质量/业务判定直接读取 bag、逐帧时间、QC 与物理结果，规则不降；日志缺测不作资格门禁。OOM/服务退出/采集损坏仍是实际故障，不删除证据腾空间。 |
| 两类镜像 | 一个 campaign-inference 镜像分别启动 head/Teacher 两个容器，一个 campaign-shard 镜像启动各 shard；只保留两个 Dockerfile 和两个 digest。 | 两服务配置/权重/hash、实例池与队列分开；同一推理镜像依赖须满足 head 绑定。source/install、CUDA UUID、EGL 与挂载权限仍真实反读。 |

上文后续审查的 P1-1/2/3、P2-1/2/3/5/6/7 仍保留；P1-4 的四项质量门槛不变，但撤销其完整指标生产/汇总框架。P1-5 的服务 owner、角色与退役顺序不变，非 wave staging 前缀改为 ROOT 下私有证据目录。P2-4 的端到端超时仍成立，计时起点改为 RGB 序列化前。首轮 P1“嵌入绝对引用”不再通过修改产物格式解决，而通过同路径挂载保留同一 bytes；首轮 P2“资源 producer”不再要求生成全量指标。

会话内自检覆盖 ROOT/挂载与旧证据边界、两类镜像/三个运行角色、binary codec 与完整 deadline、Host 崩溃终止、资源日志与四项质量分离，以及 measurement/live→W1/W2→独立 exact-W8→正式数据交付的依赖顺序。没有新增多版本 reader，也没有更改 21 项测量公式、十成员 identity、MuJoCo-only、CUDA/no CPU fallback 或 W2 后直接 40 场景 exact-W8。

本次文档证据根：`/tmp/so101-debug-container-simplification-20261012-hOJKruyD`。保留修订前后快照、manifest 与静态校验记录；未运行文档中的 pytest、Docker、ROS/MuJoCo 或真实硬件，未 SSH、dispatch、commit 或 push。未新增 archived run/删除候选，未删除任何证据。实际容器挂载、GPU、多实例、校准/live/W8/正式采集都仍待用户批准后由 dst 执行验收。
