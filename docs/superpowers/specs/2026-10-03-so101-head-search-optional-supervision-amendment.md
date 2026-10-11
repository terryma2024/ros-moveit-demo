# Head Search 执行后日志审核设计修订

日期：2026-10-03。用户最新决定：分两阶段推进。第一阶段先由主进程独立执行、留存日志、实际跑通端到端，再分析日志中的问题；第二阶段才开发正式监督审核程序并验证它。本次不运行在线监督进程，不保留逐帧、逐动作的监督审批。

用户已选择文件协议，并要求本次转换到新任务：先由 antzb 当前 Codex 保存状态汇总并结束旧任务，再以冻结的当前代码和明确迁移的未提交源码为基线，创建新 branch/worktree。新任务由 GPT-6.1 Sol / High 编写实施计划、Review 和复杂问题根因分析，由 GPT-6 Luna 执行具体开发与验证。新的计划先呈现并取得明确实施确认；第二阶段以第一阶段真实日志和分析结果为输入，另行明确边界并获准后开始。不创建第二套仿真 stack，不允许旧任务与新任务并行写代码。

## 1. 范围和现场基线

执行主机为 antzb（hostname AI-STATION-001）。旧任务 worktree 为 `/data/work/ws_moveit/.worktrees/so101-act-data-0917a`、branch 为 `codex/so101-act-data-0917a`；旧执行器完成汇总并冻结后，以其最终 HEAD 和经校验的未提交源码创建新 worktree/branch，实际路径、基线与迁移哈希由新任务登记。唯一证据根仍为 `/data/work/so101-evidence/act-data/20260930-antzb-head-search-krIv681m`。旧账本 `docs/experiments/so101-act-data-experiment-ledger.md` 作为历史输入保留，新任务维护独立当前账本并引用旧 checkpoint，不改写旧结论。

编制本修订时取证的 HEAD 为 `de10f34e2528a2f5bde23dafbd0bd3dd3a6f107f`，当时 HS409 已完成定向验证，HS410 正在修改 stopped live exposure。该快照不代替后续 fresh readback。保留 dirty 文件、已完成本地校验和所有运行证据，不 reset、不删除、不覆盖。

本次任务切换前后须再次确认最终 HEAD、dirty/staged/untracked、submodule pin、真实进程和最新测试退出码，以上旧快照不是新 worktree 的固定起点。旧代码与运行证据仍可审计；新 worktree 不复制 runtime 目录或无归属的临时产物。

范围仅为 MuJoCo Head Search。保持 CUDA/no CPU fallback、无 Grounded-SAM、单模型、单 stack、串行、有限搜索、停稳后取新帧、有限重观察和三帧锁定。17 项搜索参数、trajectory/native/controller 安全检查不因本修订取消。ACT Recorder 的无损、10 Hz 连续性和独立 QC、非 Head 抓放与模型训练/评测合同不变。

本文件替代上一轮“可选在线旁路监督”的方向，当前只做执行后审核。文件名保留 optional-supervision-amendment 便于引用，标题和合同以本文件为准；未来在线旁路监督属于另行设计，不在本次计划中实现。

## 2. 对旧合同的替代

本文件在以下明确范围内优先于 `2026-10-03-so101-head-search-bounded-simulation-amendment.md` 及其 plan；历史失败和测试结论保留，不追溯改判。

| 原要求 | 当前合同 |
| --- | --- |
| 初始化必须有健康 MonitorProcess、POLICY_READY 和 CONFIGURED ACK | 主进程独立初始化及 native readback，不启动在线监督或等待其 ACK |
| REGISTER/DISPATCH 经监督批准 | 主进程独立管理完整 goal inventory 和 native reservation/send 条件 |
| EXPOSURE_INPUTS/ADMIT/FINISH ACK 是推理和结果使用前提 | 主进程执行必需的 frame/job/epoch/freshness 校验 |
| 监督 heartbeat/channel/death 影响正常动作权限 | 执行期间不存在监督通信和监督权限依赖 |
| pending 监督 reply 阻塞正常执行 | 正常路径无监督 RPC、共享控制锁或监督等待 |
| 正常资格要求两个完整 sealed original streams | 主线原始日志必需；第一阶段人工/协调者分析，第二阶段正式程序独立重算 |
| kill monitor 是必跑的运行时故障组 | 在线监督故障组取消；改验执行时确实无监督，以及日志审核失败/缺失的报告行为 |

监督程序不等于控制器的本地安全机制或 ACT 物理监督器。不得把其他系统中同名 supervisor 一并删除，也不能跳过限位、完整轨迹、碰撞、controller 状态、native 许可和本地异常停止。

## 3. 主进程独立执行

完整流程仍为：

`ENTRY -> MOVE_BOUNDED -> WAIT_TERMINAL_AND_SETTLED -> ACQUIRE_NEW -> INFER_STOPPED -> VALIDATE -> LOCK / REOBSERVE / NEXT_STOP -> BUSINESS_TERMINAL -> STOP_PROVED`。

搜索控制线程、唯一 CUDA 推理线程和 ROS executor 可以并存。主进程独立拥有 canonical search state、motion epoch、完整 goal inventory、frame/job identity、原始 deadline、retry 和 lock counter，不把必要校验变成总是成功的 null ACK 或 mock。

运动前由主进程检查完整轨迹和合法区间、fresh feedback、controller incarnation/generation、UUID/typed goal、reservation，以及实际 send 前条件。未知 acceptance 仍必须对账；不能因为没有监督就算成功。故障后由本地 fault latch、cancel、native close 和 terminal/quiet 原始证据完成停止确认，撤销的主线 generation 不复活。

推理前确认真实停稳，图像严格晚于本次 settled source/wall floor，并配对原始 CameraInfo/TF/joint。返回后重新验证身份、motion epoch、source/receipt 和 age。正确身份过期结果丢弃并有限重观察；错身份、持续必需 feedback 丢失、controller 故障、整体期限耗尽仍按本地规则处理。

执行期间不创建监督进程、监督 socket 或 heartbeat worker；正式入口、default composition 和 Teleop 路径必须一致。资源在入口绑定一次，不建立另一模型、CUDA context 或仿真 stack。

## 4. 主进程日志合同

日志是结构化、版本化的原始证据，而非只有自然语言描述或最终 PASS。每条事件至少带 run/session/attempt、严格递增 event sequence、owner/thread、source/config/model digest、原始 monotonic wall time，以及涉及的数据 source sim stamp。不同 clock 保持分离，不以接收时间改写原始 source 时间。

必须记录以下可重算信息：

- 状态转移、停点/精调目标、完整轨迹或只读引用及 SHA、实测 joint/angle/velocity、motion epoch。
- goal UUID、reservation/send、acceptance/UNKNOWN、feedback/result/terminal、cancel/native close 请求和实际 ACK。
- 停稳条件、原始连续样本、判定时间、image/CameraInfo/TF/joint 配对和完整 frame/job identity。
- 获取请求、推理开始/结束、检测摘要、原始年龄/期限、结果消费、miss/drop/expired、重观察理由和预算。
- 同一 track 的三个 distinct advancing valid frame、lock counter 每次变化、使用该结果发出的动作。
- 本地 fault、停止确认、业务终态、异常、进程退出、资源退休和 owned teardown。

配对图像、overlay、原始样本和轨迹的大文件引用必须可回读并校验 SHA。执行记录保留实际采用的 detector 输出，审核不用另一次推理结果冒充当时结果。本次审核关注执行合同，不替代模型效果评测；YOLO 离线指标和人工图像检查仍按原计划单独验收。

日志写入只能使用主进程自己的有界资源，不等待审核进程。高频证据放登记 NVMe root；缓冲、队列容量、实际写入耗时和丢失计数均可检查。不能通过删除事件、关闭 fsync 或篡改 timestamp 降低开销。日志系统出错应明确记录本地证据故障；未完整落盘的运行不能宣称可审计或 QUALIFIED。

正常终态及 owned teardown 完成后 flush/seal，保存文件清单、hash、数量、模式、argv、输入和 rc。异常退出可能没有 seal，应保留原始 bytes 和缺失事实，不能生成伪造的“完整 seal”。

### 文件交接协议

主进程和监督审核程序通过运行目录交接，没有运行时双向消息、socket、数据库、消息队列或共享内存依赖。第一阶段只实现写入、完成标记和回读分析；第二阶段再实现正式读取和审核。

新运行目录位于已登记 evidence root 内，使用此前不存在的 run ID。目录合同如下，文件名是本设计选择，不能称为当前代码已有能力：

```text
run/
├── manifest.json       # 协议版本、运行身份、代码/配置/权重及命令输入
├── events.jsonl        # 逐行追加的结构化原始事件
├── artifacts/          # 图像、轨迹和原始样本等实际引用
├── completion.json     # 业务终态、退出原因和主进程可确认的完成事实
└── seal.json           # 已完成文件的清单、大小、SHA256及事件数量
```

`manifest.json` 声明 `file_protocol_version=1`；这是文件交接协议版本，不重定义现有事件 schema。事件行保留各自 schema version 和 run 身份，采用 UTF-8 JSONL、整数纳秒原始时钟及全局连续 event sequence。主进程内多个线程通过同一有界日志写入者确定 append 顺序；事件的实际发生时间另行记录，不能把文件顺序解释为跨线程因果关系。原始 sim/wall clock 分开，UTC 仅用于可读标签。无效或缺失值明确表示，不能输出非标准 JSON 的 NaN/Infinity，也不能以零伪装缺失时间。

复用现有原始 journal、样本和图像存储，避免为文件协议重复保存同一份大数据。新增事件可指向已有只读 artifact；其路径、身份和 SHA 必须在 manifest/seal 中可追溯。实现计划列明与现有 journal 格式的映射，不能为了新文件名丢弃原始字段。

主进程关闭所有日志生产者并完成 owned teardown 后，flush/fsync 已写文件，生成 `completion.json` 和 seal。最终 seal 采用同一文件系统内临时文件完成写入和同步，再原子发布为 `seal.json`，并同步所属目录；seal 不包含自身哈希。`seal.json` 出现只是完成标记，读取方仍须验证清单、事件数量、sequence 和引用哈希。日志容量和写盘错误按本地证据故障处理，不等待审核程序解决。

`completion.json` 不伪称捕获 SIGKILL 或主进程已经发生的 OS 退出码：程序记录自身业务结果和拟返回码；外层既有命令执行记录保存实际进程退出码，两者独立核对。任何情况下都不能仅凭 completion 文件或退出码零判定证据完整。

审核输入是一个明确的 run 目录路径。正常完整输入应具备可验证 seal；异常退出无 seal 或 JSONL 尾行截断时，可以只读分析已有完整事件，但完整性标记为 INCOMPLETE，不补造尾行、不修改原文件。已存在的明确违规可以单独报告，不能把其余缺失部分猜成成功或失败。

审核输出放在 evidence root 的独立 `reviews/<run-id>/<audit-id>/` 中，与 sealed run 分离。记录所读 run/seal 哈希、审核程序和规则版本，再写 `review.json` 与 `review.md`；第一阶段的人工分析也使用独立目录。不能把报告加进原 run 后使原 seal 失效。

第一阶段交接不需要接收者确认，主进程不等 ACK、不轮询审核结果。第二阶段审核程序未启动、失败或无权限读取，只影响 audit 状态，不能改变已经发生的 execution 结果。审核所需最终 CLI、状态和退出码映射在第二阶段计划确定。

## 5. 第一阶段：主线日志与端到端闭环

第一阶段不编写、安装或等待正式监督审核程序。实施范围仅为主进程独立执行、去除在线监督准入依赖、保留必要本地校验和日志。最短验收路径是实际 MuJoCo + CUDA 运行完整搜索、停稳、新帧、推理、精调、三帧锁定和停车，落盘完整原始日志，完成可追溯的人工/协调者日志分析。

先完成端到端运行，再依据日志定位真实问题；避免先把未来审核器的 schema、报告框架、故障样本生成器或全面审计矩阵做完，才允许主线运行。基本版本、事件身份、顺序、时钟、完整性和引用哈希仍需具备，防止日志无法分析。

日志分析直接回读原始事件，按 motion -> settled -> capture -> infer -> validate -> lock -> stop 顺序检查；列出发现的问题、证据位置、影响和下一步。命令或小型只读查询仅用于分析，不发展成临时版本的正式审核器。无依据的问题标记待验证，不能由最终 DONE 反推每个环节正确。

阶段一里程碑称为“主进程独立端到端闭环及日志分析完成”。没有正式审核程序不影响这一里程碑。若日志发现本地合同违规或无法确认停车，保留运行失败并修复后从新 run 重做；不能因尚无自动审核而放行明显问题。此里程碑不等于全部 Head Search/Teleop/40 场景 QUALIFIED，也不声称已具备独立防卡死。

## 6. 第二阶段：正式执行后监督审核

监督程序仅在主进程结束后启动，以只读方式读取该 run 的 frozen manifest、原始日志和引用。它不启动 ROS/MuJoCo、不占用 CUDA、不重新执行搜索，不发送 cancel/revoke/运动，也不改日志、配置或历史结果。

审核必须独立于 producer 的最终 PASS，基于日志重算：

- 全部停点/精调轨迹是否在合法区间，实际动作是否有匹配的 reservation/UUID/terminal。
- 停稳后是否才取新图、开始推理，旧 frame、错 epoch 或过期结果是否曾被使用。
- 重观察是否有界，总 search/job deadline 是否被续期或绕过，三帧锁定是否真实成立。
- 本地异常是否按声明处理，停车证据是否完整，是否出现 unknown acceptance、丢失事件、资源残留或不完整退出。
- motion/settle/capture/inference/use 的 wall/sim 耗时，以及 gap、miss、expired、drop、retry 和 timing outlier；保留全部样本。

第二阶段以第一阶段保留的真实正常、失败和异常日志为回归输入，使用现有独立磁盘 aggregator 的能力，补成正式安装的日志审核入口；不再新增一套同功能临时 agent 脚本。由 antzb 在计划中选定精确入口/模块和 schema，记录与现有 aggregator 的复用关系。审核默认确定性地输出问题、原始 event sequence/文件位置、判断依据和严重程度；不依赖 LLM 对话才可运行。

审核结论分为 PASS、FAIL、INCOMPLETE。仅有主线 DONE、rc=0 或缺少报错不能算 PASS。输入无 seal、sequence gap、hash 不符、缺失引用或信息不足时给出 INCOMPLETE 或明确完整性 FAIL，不能猜测缺失事件，也不能把“无法审核”当作“执行有问题已证实”。

审核报告按文件协议输出到 evidence root 的独立 `reviews/<run-id>/<audit-id>/`，不改 sealed run 原始数据；包含 `review.json` 和便于阅读的 `review.md`。最终退出码与状态的映射在第二阶段实施计划中明确，正式入口先经 --help 验证。当前不虚构已经存在的新命令或已通过的审核证据。

审核程序未启动、崩溃或无法读取输入，不改变主进程已经发生的执行结果；报告“审核未完成”。总报告分别显示 execution status、audit status 和 qualification status。第二阶段的监督审核程序必须独立验收其正确性；未来需要自动审核的整体资格，才要求功能合同和正式审核同时成立。不得追溯要求阶段一先具备审核程序，也不得把第二阶段尚未完成写成阶段一运行失败。

## 7. 防卡死边界

本阶段没有在线独立监督，因此事后日志审核不能防止正在发生的卡死，也不能在主进程完全挂起后立即停车。不能宣称拥有这层独立防卡死保障。

主进程仍保留本地期限、有限轨迹和 controller 层停止机制。实际 controller 是否具备 owner loss stop、watchdog 或有限目标结束后的保持行为，需要核对并报告，不假定已实现。发现真实卡死时保留最早失败边界和可用日志，由用户决定后续独立保护设计；不能借本修订触碰真实硬件。

## 8. 两阶段实施和实际验收

### 第一阶段计划与验收

先映射 bootstrap.start_monitor/CONFIGURE/POLICY、HeadPrimarySupervisor、REGISTER/DISPATCH、HeadLiveExposures EXPOSURE_INPUTS/ADMIT/FINISH、inference owner、native owner/lease/lifecycle 和日志依赖。列出必须迁回主进程的校验；schema 只做到日志可完整回读，不先实施正式审核程序。

同时清理与本设计冲突的遗留代码：在线监督启动/heartbeat/RPC/ACK 准入、监督生命周期连带撤销主权限、必须双流 seal 的 Head-only 判断、无消费者的旧配置、安装入口及只验证过时合同的测试。逐项记录调用者和清理理由，消除 production/default/Teleop 路径的隐藏依赖。共享 ACT/native/安全能力有其他调用者时，只拆开 Head 在线监督耦合，不能删除其仍需功能；历史日志 reader 如需保留则明确为只读兼容模块，不允许悄悄回退旧运行方式。代码删除通过 Git 可恢复，运行证据不删。清理与迁回校验一起经历 RED/GREEN、包级门和真实闭环，不扩成无关重构。

定向 RED/GREEN 必须证明真实 primary/default composition 在不创建监督进程时可运行，必要 trajectory/frame/epoch/freshness/goal/stop 负例仍拒绝，日志保存原始事件且可 flush/readback。现有 journal 可复用，不为了新报告框架改全部历史格式。定向 GREEN 不替代实际闭环。

代码冻结后读取实际 installed `so101_head_search_calibration run --help`、`verify-promoted-config --help`、`qualify --help`，核验绝对 executable、Python/overlay、真实输入和一次资源绑定。计划必须给出完整 argv、输入 path/SHA、预期业务终态/日志文件和实际 rc/stdout/stderr/teardown，不虚构尚不存在的 flag。

既有定向 runner 为 `/data/work/venvs/so101-v5-t004-perception/bin/python3 /tmp/so101-debug-head-codex-oXpMWjlc/prepare-dispatch-test.py LABEL TEST_FILE...`，随后执行输出新 RUN_DIR 的 `run.sh`。先验证两个路径；fixture/bootstrap 错误不算行为 RED。

使用事前冻结的开发场景、实际 installed formal/default composition、单个真实 MuJoCo stack 和唯一 CUDA detector，运行完整正常搜索。预期 execution rc=0，完整运动/停稳/新帧/推理/精调/三帧锁定/停车；进程树确认无在线监督，主线原始 journal flush/seal 和引用可回读。先完成该闭环，再分析全部日志，包括耗时、gap/expired/reobserve、错误结果使用、目标/terminal 和停车。正常过期丢弃不自动算失败，旧结果实际被用来发目标或增加 lock 则必须修复。

若日志暴露问题，做对应的定向复现和最小修复，代码再次冻结后新 run 从头执行。不先把全部未来审核器负例矩阵跑完再开始首条闭环。与当前改动直接相关的真实本地异常停止控制仍需验证，不能因优先跑通而去掉安全前提。

阶段一输出：实际命令及 rc、输入/源/安装/权重 SHA、全部原始日志和 seal/缺失事实、native/UUID/quiet stop proof、资源 teardown、可读日志分析和问题清单。预期日志位置由执行计划列明。人工分析不是正式审核程序，也不冒称自动审核资格。

### 第二阶段计划与验收

以阶段一真实日志和问题清单为输入，精确确定安装审核入口、schema、规则、问题级别、报告与退出码。复用实际 disk aggregator，但不启动第二 ROS/MuJoCo stack，不新建模型或重跑推理。方案和实施边界先呈现确认，再开始代码。

先定向 RED/GREEN，再执行实际安装审核入口读取阶段一原始 seal/log。验证正常日志 PASS、实际违规 FAIL、信息不足 INCOMPLETE，以及程序启动失败/崩溃时 audit 未完成且 execution 历史不变。完整命令、输入文件 SHA、预期和实际两进程 rc、stdout/stderr、review.json/review.md 和只读性证据都保留。

负例使用独立副本，保留真实原始日志不变：删 event、改变 sequence/hash、缺引用、错 identity、过期结果消费、非法 lock、缺 stop proof，必须逐项定位。受控改写样本只是审核器测试，不能冒称真实运动故障；至少包含阶段一已经实际观察到的问题作为回归。审核还要正确区分允许的 miss/expired/有限重观察，不能只证明会报错。

证明审核执行前后原始 run 的文件内容/哈希不变。程序不导入 producer 的 PASS 作为判断，也不启动 CUDA/ROS/仿真，不发送 motion/cancel/revoke。审核失败不能重写 execution outcome；整体资格按明确合同单独判断。

### 共同门禁

完整普通 xdist/package/native gates 仅在计划集成边界运行，worker=min(8, logical CPUs)，保存真实 rc/elapsed/JUnit 和 baseline 缺失。不因日志审核重构额外跑 benchmark。fsync-heavy tests 使用登记 root 下新 NVMe scratch，并用精确 Python 验证 TMPDIR/TMP/TEMP 和 tempfile.gettempdir()。

受控 source/config/policy 变化使旧 bundle/live/QUALIFIED 失效；新 run ID 从头执行，无 resume。正式校准、40 held-out、default/left/forward 三 anchor 各一次 FULL_RESTART、Teleop 原始/overlay、封存模型数据和 exact digest 人工批准保留，它们属于整体目标后续门禁，不能把阶段一首条闭环说成已全部通过。不使用 held-out 调预算。ACT campaign W2 -> 独立 exact-W8/40、禁止 W4/W6、资源入口绑定一次均不改。

## 9. 当前交接和任务状态

用户已要求停止旧任务并开启新任务。当前旧任务只接收状态汇总、保存和冻结指令，不承担本设计的代码实施。新任务在交接确认和新 worktree 建立后接收设计及计划任务。

用户进一步明确，切换必须按进程完成：先由旧 Codex 保存状态摘要和冻结凭据，再退出旧 CLI 进程并确认原 PID 已消失，最后启动全新的 Codex CLI 进程。新进程不使用 resume 或 fork 接续旧会话；通过持久交接文件恢复工作背景。不停止其他任务共享的后台服务，也不以关闭一个 UI 会话冒充旧进程已退出。

先在安全命令边界完成已启动测试并保存 rc/证据、HS410 dirty diff 和 checkpoint。不为新指令重跑旧 gate，不继续扩展监督 ACK 必需的实现。导入本修订并更新两阶段计划，优先呈现阶段一最小实施范围、实际运行命令、日志字段和分析方式，等待用户实施确认；阶段二暂不开发。

新任务开始前更新可见 task list，明确交接恢复、设计导入、依赖迁移与遗留清理、阶段一日志与端到端计划、阶段二后置及审批等待。每个 turn 结束只更新既有任务项 status，不改写、重命名、合并、拆分、删除或补充内容。新 session 不恢复旧 goal，不继承旧任务无限推进授权；不调用禁止的自恢复工具。

GPT-6.1 Sol / High 负责计划、Luna 结果的独立 Review、复杂问题根因分析及整体协调；GPT-6 Luna 只执行已批准的明确 task boundary。两者可以共享新 worktree，但同一时刻只有一个源码/文档写入者；Review 冻结精确 diff、source 和测试/运行证据，不与 Luna 写入并行。Luna 遇到复杂或反复问题停在证据边界交给 Sol 分析，不自行扩大权限或降低门槛。模型不可用时报告限制，不替换模型；不改变 global defaults。

旧任务摘要、原工作区 dirty 和任务相关未提交源码均保留，未完成 RED 不冒称已修复，新任务记录 baseline 失败。不得 push、删除运行证据或操作真实 SO-101；新 branch/worktree 与上述模型分工是本次明确授权，不授予第二套 stack 或无关并行开发。
