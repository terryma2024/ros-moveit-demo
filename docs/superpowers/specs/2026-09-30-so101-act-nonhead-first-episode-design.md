# SO-101 ACT 首条非 Head Search 采集闭环设计

日期：2026-09-30
状态：讨论边界已获用户确认，独立 Astra/High 复审通过，等待用户审阅本文。本文不授权实现或启动采集。

## 1. 目标

在 ai-station 上完成一次真实 MuJoCo 抓放，将执行期间的数据交给正式 Recorder 无损落盘，再由独立进程回读、计算 QC，并取得实际 Coordinator 提交记录。

这次只回答一个问题：隔离 Head Search 后，正式 ACT 数据采集的首条闭环能否跑通。完成条件是一条从桌面杯子开始、完整抓放并提交的 episode，不要求多场景、多个 anchor 或连续五次成功。这个单次里程碑是用户指定的范围，不改变正式采集与稳定性资格的验收次数。

复用正式 Worker 的采集合同。固定目标输入是隔离点，其余动作授权、物理监督、同步、Recorder、seal、结果验证与提交走共同路径。诊断数据可以获得真实提交，但不能进入正式训练集或计入资格数量。

## 2. 范围与已有事实

执行位置是 ai-station，worktree 为 `/home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a`，分支为 `codex/so101-act-data-0917a`。dst 是唯一实现执行器；它直接在 ai-station 上运行，不得自我 SSH。antzb 上的 Head Search 校准继续独立进行，本任务不改其校准、数据和模型比较方案。

设计调查读取的 ai-station HEAD 为 `9386860dfed9bdfa840b7b51f061c299459bd390`。当时还有未提交的物理执行修改，账本最新记录为 CP-1920；HEAD 不能代表这些修改的内容。实现前必须重新记录 HEAD、submodule、dirty diff 和安装产物身份，保留已有工作。

当前代码提供了可复用边界，但还不能据此宣称 live 闭环已完成：

| 当前边界 | 已有能力或缺口 | 本任务的处理 |
| --- | --- | --- |
| `act/contracts.py`、`act/synchronizer.py` | 双 RGB、8D state、6D action 及因果采样合同 | 保留输入语义、顺序和单位 |
| `act/expert.py` | 从 controller reference 取得 `t+0.1s` 标签 | 接入实际执行中的采集，不用 phase 结束后的汇总冒充时序数据 |
| `act/recorder.py` | PNG/JSONL、hash、fsync、不可覆盖的 seal | 复用；补足共同的独立图像和物理 QC |
| `act/result_store.py` | 工作目录到 sealed 结果的发布及 lease 身份验证 | 复用注册目录、完整 lease 和实际验证 |
| `parallel_batch/coordinator.py` | 验证结果后写 `RESULT_COMMITTED` | 必须实际调用并回放 journal，不由 Worker 自报提交 |
| `act/collection.py` | `collect_authorized_scenario()` 的汇总直接写 `coordinator_committed=True` | 消除该字段作为提交依据的用法；由真实 receipt 派生交付状态 |

本任务不实现容器化 campaign、共享推理服务、并行扩容、ACT 训练或模型效果比较。未来容器架构可复用本文的数据边界，但不成为首条闭环的新增前置条件。

## 3. 正式路径与诊断路径

新增显式的“预选目标诊断”模式。这里是设计名称，不表示仓库已存在对应 CLI。入口必须要求用户主动选择，默认仍是正式模式；不存在自动回退。

正式模式继续要求合法 Head Search 校准和 qualification。诊断模式不扫描、不居中、不运行 head YOLO，也不生成 `TARGET_LOCKED`、Head `QUALIFIED` 或 `TASK8_READY` 假证书。neck 保持冻结的初始角，使用实际关节反馈确认静止。

拆分启动 prerequisite 的适用范围：仅 Head Search、Head 视野效果及其校准配对不适用于本诊断。机器人、接触、控制器、reset、碰撞、持物、释放、采样与身份门禁仍适用。包含 `CALIBRATION_REQUIRED` 的非 Head 安全策略不能被诊断模式清除；缺少必要的非 Head 参数或批准证据时停在具体 blocker。

启动时创建不可变的模式/场景记录，并绑定到该 batch、lease、episode seal 和 QC 报告的 hash 链。诊断身份必须保留到 Coordinator index 与训练导出边界；不能只放在不参与验证的 README 或命令行日志里。导出器仅接收明确的正式身份，未知模式、缺少模式证据、诊断模式均拒绝。不能通过复制目录或改一个布尔值把诊断结果改为正式数据。

### 3.1 固定目标输入

冻结一个 scene ID、seed、杯子桌面初始 pose、机器人初始关节、neck 初始角、放置区及目标 mask。目标 provider 输出唯一杯子的身份、mask 来源和教师所需目标几何；几何必须与本次 reset 后的场景一致，坐标变换和可达性检查照常执行。若直接使用仿真真值取得目标几何，明确标记诊断教师来源，不能声称相机教师已验证。

固定 mask 只替代目标选择，不能充当物理抓取、支撑或释放证据。它不向 ACT observation 添加信息，不按杯子实时真值替机器人补动作，也不被当作每帧新鲜检测。head/wrist 图像仍来自本次 MuJoCo 的实际相机。

## 4. 共同运行链

~~~text
统一入口：显式模式 + 冻结场景/策略 + 单 Worker admission
  -> Coordinator 发实际 lease
  -> FULL_RESTART / 一次 reset / 初始状态确认
  -> 预选目标 provider / 稳定状态
  -> MoveIt 专家真实抓放 + 执行期间持续采样
  -> Recorder drain / fsync / episode seal
  -> 新进程独立回读及共同 QC
  -> ResultStore 发布 sealed result
  -> Coordinator verifier / RESULT_COMMITTED / index receipt
~~~

使用正式 Coordinator、Worker 与结果接口的单 Worker 配置，不搭建简化的第二套 scheduler 或 Recorder。若现有 production composition 尚未连接某一边界，补齐连接及相关回归测试；mock composition 不算运行验收。

campaign 资源绑定只在统一启动入口发生。内部组件验证当前 lease、generation、session、reset epoch 和消息新鲜度，不重复申请 campaign 资源。即使不跑模型推理，保留 MuJoCo GPU/EGL 与 GPU 所有权要求；需要推理的组件仍是 CUDA/no CPU fallback。

### 4.1 物理动作

杯子从桌面开始。必须经历接近、闭合夹爪、抓稳验证、抬升、搬运、到达有支撑的放置位置、释放、稳定放置、撤离和最终检查。不能以已经持杯的轨迹、瞬移杯子或人为 physics attachment 替代抓取过程。

完整机器人碰撞检查和 controller admission 保持生效。MoveIt attachment 仅是规划 shadow；MuJoCo pose/contact 是独立物理事实源。释放顺序必须满足现有安全契约，包括开夹爪前的必要 shadow detach；不能从成功 action 返回值推定该顺序已经实现。该顺序若需要修复，保存真实前后证据并单独测试。

持有无支撑杯子时出现错误，只允许 stop/hold 和保存证据，不自动开夹爪或 reset。放置验收须使用当前 release epoch 的 pose、support contact、gripper/controller 和 Planning Scene 证据，不能复用释放前样本。

数值阈值、采样新鲜度、碰撞接触白名单和稳定窗口来自冻结的共同策略。实现计划必须列出实际配置键、数值、来源文件与 hash，并给出可执行的逐项断言；缺失项是启动失败，不能为首条成功临时选取宽松数值。

## 5. Observation、action 与时序

| 数据 | 与正式 ACT 相同的合同 |
| --- | --- |
| head/wrist RGB | 各为 `640×480×3`、`uint8`，实际源帧，保存为无损 PNG |
| state | 关节 `1` 至 `6` 的实测位置，再接 `sin(neck_yaw)`、`cos(neck_yaw)`；共 8D，关节按共同映射使用 radians |
| action | 关节 `1` 至 `6` 的 controller reference position；共 6D，五个 arm 加一个 gripper，不含 neck |
| 时间 | 10 Hz sim-time 网格，action 的 reference time 为 observation time `t+0.1s` |
| audit | session/attempt/reset/release 身份、源时间戳、实际 controller reference、物理 truth/contact、Planning Scene 与事件证据 |

`task_camera`、mask、目标坐标、Depth、truth、contact、phase 和教师内部状态均不进入 ACT observation。教师可以使用诊断目标几何；其来源只留在 audit 和运行溯源。

采集从 reset 已确认、目标已指定且输入稳定的初始状态开始，早于第一条抓取命令；覆盖整个执行及撤离、最终放置稳定检查。不能只在每个 phase 返回后记录一行或补造中间帧。

每个 observation 只使用 `stamp <= t` 且满足共同 age/skew 约束的输入。已有 Recorder 的 `dt_s=0.1`、`max_source_age_s=0.1` 约束保持不变，跨流 skew 使用冻结配置。head 即使没看到杯子，仍要有新鲜、连续、身份正确的 RGB；本次不评价它的检测或搜索效果。

每路相机在采集边界提供 session/reset-scoped acquisition ID、源序号及 sim-time stamp；ID 在生产新帧时产生，不能在选择旧帧或写 PNG 时重建。相邻训练行的每路 acquisition 必须不同，源序号与 stamp 严格递增，禁止拿同一 acquisition 补齐下一行。在线采集和离线 QC 都验证这一点，并按冻结的 10 Hz 源帧 schedule、起止边界及 acquisition 计数检查完整覆盖；不能只检查 JSONL 行数。源序号出现无法解释的缺口、缺少新 acquisition 或实际源帧 cadence 不满足合同，均失败。静止画面中不同 acquisition 的像素 digest 可以相同，不能据像素相同判重。

`t+0.1s` reference 是实际 controller 接受的轨迹在该时刻的参考位置。采集器用有界缓冲等待相应 reference 的可验证证据，再封存 observation/action pair。停止或撤销后的未生效轨迹不提供标签；不能改用下一帧实测关节、未执行的规划结果或固定 action。

命令 dispatch、接触变化、release 和最终检查在实际发生边界记录源时间、序号及关联身份，保留足以回算标签的 controller reference 历史。结束时没有合法未来 reference 的尾帧仅留在审计数据，不伪造训练 action；释放和最终稳定性证据仍须完整保留。队列溢出、缺帧、过期或跨 epoch 数据使运行失败，不丢帧后继续报 PASS。

单次 attempt 保留共同的 120 s 单调墙钟上限。在第一条执行命令前开始计时，包含等待、完整抓放、撤离和最终检查；若有更早的实际推理则从其开始计时。进入 finalizing 后不再发新物理动作。Recorder/QC/提交另受现有 finalization、lease 和 batch deadline 约束，不能反向延长运动期限。

## 6. 落盘、独立 QC 与提交

### 6.1 同一 Recorder 与 schema

复用 `EpisodeRecorder` 的 rows、双 PNG、provenance、fsync 与不可覆盖 seal，以及 `ActCollectionResultStore` 的 registered workspace、`working` 到 `sealed` 发布。完整 lease identity 包括 batch/coordinator epoch、worker/generation、point、attempt、lease generation；session 和 reset epoch 也要绑定。成功前要确认 controller 已停止、队列排空、文件及父目录持久化。

现有 observation/audit/provenance/result 都是 closed schema，不能偷偷增加诊断字段而仍称原 schema。新模式、原始像素 digest、事件/reference 历史及独立 QC 报告若需要新增数据，采用共同的 versioned audit/manifest 扩展：显式版本、closed fields、逐文件 hash 与 receipt 绑定，由正式和诊断路径共用验证器。原有 observation/action 语义不变；旧版本缺少所需证据时不能取得这次验收 PASS。

原始像素 digest 在 acquisition 边界按固定 RGB shape/dtype/字节顺序计算，不从落盘 PNG 反向生成。每个训练行关联其 head/wrist acquisition ID、源 stamp 和 digest。完整 reference/event audit 也纳入同一 hash 链，不能由可随意改写的旁路日志补齐。

### 6.2 独立回读

新进程只接收只读的已封印 episode、绑定的运行配置与原始 audit，不共享 Worker 内存、不连接 live topic、不请求 Worker 再解释结果。它使用共同规则重新计算：

1. 文件集合、数量、大小、SHA256、每个 PNG 的完整解码及 RGB shape/dtype；解码像素与 acquisition digest 一致。
2. rows 与双帧的一一对应、完整 10 Hz 网格、每路 acquisition ID 的唯一性、源序号/stamp 严格递增、源帧 schedule 的连续覆盖、源 age/skew、关节顺序、有限值及 session/attempt/reset/release 身份。
3. 每个 action 与实际 controller reference 在 `t+0.1s` 的匹配、命令接受/撤销时序，拒绝未来反馈和未生效参考。
4. 桌面初态、抓稳和实际抬升、持物搬运、当前 release epoch 的释放及支撑、稳定最终 pose、撤离和安全终态；阈值用绑定的共同策略。

seal 中的 `status` 或 `qc_passed` 只是一项待核对声明，不能代替计算。QC 报告保存规则版本、配置 hash、episode/audit hash、完整身份、计数、逐项结果和失败原因，并由结果验证器核对。正式与诊断共享这套 QC，不增加一套降低阈值的“测试 QC”。

### 6.3 真正提交

episode seal 保持不可变，`committed:false` 不改写。Coordinator 经结果 verifier 确认 sealed result、QC 和当前有效 lease 后，持久写入 `RESULT_COMMITTED` 并生成 index/receipt。完成报告须回放这个 journal 事件，核对 episode、result、QC、模式及 identity hash 一致。

因此有三种不同状态：只有文件；已有合法 seal/QC；已由 Coordinator 提交。只有第三种同时具备真实物理成功及独立 QC PASS 才满足本任务。诊断提交仍禁止进入正式训练 manifest、资格计数和正式成功率分母。

## 7. 失败处理与安全停点

本任务不实现 resume、并行运行或自动业务重试。失败后先保存第一失败边界、实际退出码、部分文件和物理状态；修复后另建 run/attempt，从 FULL_RESTART 重跑。不得在旧 root 中覆盖输出、删失败行或拼接前后两次的数据。

CPU/GPU/RAM、磁盘、MuJoCo RTF、Recorder 队列或 10 Hz 连续性达到共同停点时，停止并报告资源证据。不能改画质、采样率、阈值或以 CPU fallback 换取通过。未知进程所有权、不能证明旧 goal 已停止、必要策略未批准或将触及硬件时，同样停下请求最小决策。

## 8. 实现与验收边界

后续实现计划须给出可安装、可重复调用的正式程序入口，保留在仓库；不得以 agent 临时脚本完成核心采集或 QC。列明 exact executable/environment、输入文件、模式、预期产物、成功 `rc=0` 与失败非零退出码、日志和 readback 命令。若现有入口尚不存在，由计划明确新增，不能把设计名称写成已经可执行的命令。

执行分段如下：

1. 针对 admission 模式隔离、运行中采样、reference 因果性、共同 QC、实际提交与诊断导出拒绝，完成定向 RED/GREEN；先证明预期代码边界确实运行。
2. 代码及配置冻结后，重新构建/source 并确认源码、安装产物、实际进程三处 provenance；在计划定义的集成边界执行受影响包的普通 gate。
3. 用一套 MuJoCo headless stack、一个 Worker、一个固定场景做一次 FULL_RESTART，真实执行第 4 节全链。保存完整命令、stdout/stderr、实际 rc、controller/physics/reference/event、队列与资源状态。
4. 新进程独立回读全部数据，生成 QC PASS；实际 Coordinator 提交后回放 receipt，并证明导出器拒绝这条诊断 episode。
5. 对成功证据的隔离副本做缺帧、PNG 损坏、错误 reference、旧 generation、未提交与模式证据缺失的负向检查。另构造“没有新 acquisition，却复制旧帧补齐行、PNG 数量和合法 hash”的副本，必须因 acquisition 重用或连续性失败而拒绝；不同 acquisition 但像素相同的正常静止帧应通过。原成功证据只读保留；拒绝原因须对应真正失败边界。

代码 checkpoint 按根 `AGENTS.md`：dst 在执行主机的 Codex tmux 中使用 GPT-6.1 Sol/High 审查；环境不可用则暂停，等 coordinator 给审查结果。设计与实施计划的独立审查使用 GPT-6 Astra/High。UT GREEN、静态 wiring 或 fixture seal 不足以关闭 runtime finding。

完整普通 Python gate 使用 `pytest-xdist`，worker 数为 `min(8, 逻辑 CPU 数)`；记录实际收集范围、JUnit、跳过数、耗时及退出码。`so101_demo_py` 普通范围仅为 `test/`，本任务不运行 `benchmark_test/`。ai-station 的 fsync-heavy pytest/colcon 使用登记 evidence root 下全新 NVMe scratch，验证 `TMPDIR`、`TMP`、`TEMP` 和每个实际测试 Python 的 `tempfile.gettempdir()`；不满足则不启动。

只有以下结果齐全才报告首条闭环通过：真实完整抓放证据、持续采样及无损 readback、独立 QC PASS、当前身份的持久提交、诊断导出拒绝、相关回归和集成 gate。报告明确“非 Head Search 诊断闭环”，不宣称 Head 校准完成、正式训练数据已合格或并行采集已通过。

## 9. 证据与后续合并

执行沿用唯一 durable evidence root `/data/work/so101-evidence/act-data/20260924-fbc25063-resume`，每次冻结身份创建此前不存在的 run 子目录。账本为 `docs/experiments/so101-act-data-experiment-ledger.md`，登记 scope、模式、source/config/policy hash、初始条件、命令、退出码、读回结论及提交 receipt。正式数据、诊断数据和负向副本的用途通过受验证身份区分，不能只靠目录名。

全部成功和失败 run 保留；本任务不移动或删除既有 evidence。scratch 与负向检查副本经读回后可列为删除候选，未经用户授权不删除。结束报告分别列出 retained、archived 和 deletion candidates。

任何受控 source/config/policy 变化都使旧 bundle/live/QUALIFIED 对新身份失效；旧证据保持原结论，但不能拿来批准修改后的正式运行。单次诊断 PASS 也不会生成完整系统 qualification。

待 antzb 的 Head 校准与模型选择完成，另开合并任务：用正式 Head Search target provider 替换本次诊断 provider，冻结合并后的 source/config/policy，重新跑完整链并取得新证据。合并涉及的资格与 W2 后独立 exact-W8/40 场景顺序仍遵守正式计划，不跑 W4/W6；不能把本次诊断提交升级成正式提交。两台机器的共享分支发布要串行交接，不覆盖对方未提交工作。

## 10. 参考边界

- [双 RGB ACT 总体设计](2026-09-10-so101-act-head-wrist-rgb-design.md)
- [Task 8 live 与正式采集设计](2026-09-24-so101-act-task8-live-formal-collection-design.md)
- [容器化 campaign 设计](2026-09-30-so101-act-containerized-campaign-design.md)，仅用于后续接口兼容，不增加本任务容器化范围。
- ai-station 上的批准设计 `docs/superpowers/specs/2026-09-28-so101-act-task8-artifact-preparation-design.md` 与已审计划 `docs/superpowers/plans/2026-09-11-so101-act-head-wrist-rgb-implementation.md`。
- ai-station 上的 `act/contracts.py`、`act/joints.py`、`act/synchronizer.py`、`act/expert.py`、`act/recorder.py`、`act/result_store.py`、`act/collection.py`、`adapters/act/parallel_collection_runtime.py` 与 `parallel_batch/coordinator.py`，路径均相对 `src/so101_demo_py/src/`。

本文仅针对预选目标的单 episode 诊断，明确替代“必须先完成 Head qualification 才能做这项诊断”以及一般五次稳定性验收对本里程碑的要求。正式模式、非 Head 安全门、正式数据资格和并行计划不因此放宽。
