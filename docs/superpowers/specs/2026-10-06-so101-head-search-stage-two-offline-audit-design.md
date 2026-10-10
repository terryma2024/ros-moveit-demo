# Head Search 第二阶段：执行后日志审核程序

日期：2026-10-06。状态：用户已确认简化方向，本稿按该方向修订，待核对书面细节；尚未编写实施计划、修改程序或下发任务。

本设计承接 [文件协议与两阶段修订](2026-10-03-so101-head-search-optional-supervision-amendment.md) 的第二阶段。目标是把第一阶段的人工日志分析做成正式、可安装的事后诊断程序。主进程结束后，程序核对日志完整性，关联动作、帧和结果，检查搜索闭环及实际停车，输出可定位的问题。它不重新证明整套控制系统，也不决定 ACT 训练数据是否接纳。

## 1. 范围与取证基线

Astra 修复后复审已接受 ASTRA-01～04 的代码修复，以及本轮新发现的 ASTRA-R05 推理结果交接竞态修复。第二阶段以最终接受的 F015 冻结源码、安装产物和四个真实新 run 为输入基线，不再沿用“修复尚在进行”的假设。

这不等于第一阶段全部验收通过。复审时仍保留历史失败归因和原件缺口，F 为 `PARTIAL/OPEN`，G 的完成声明为 `PARTIAL`；普通/package 门禁为 `FAIL/OPEN`，资格为 `NOT_QUALIFIED`。这些是原复审记录，不因用户暂缓历史归因而改写。审核器可以复核某个有完整原件的 run，不能据此关闭其他运行的历史问题或宣布整个 Head Search 完成。

以下是 2026-10-06 设计取证时在 antzb 读取的 F015 复审快照，不是后续 UT 修复完成后的实时状态：

| 项目 | F015 复审取证依据 |
| --- | --- |
| 主机 | `antzb`，hostname `AI-STATION-001`；本设计由 Mac orchestrator 编写 |
| 执行 worktree | `/data/work/ws_moveit/.worktrees/so101-head-file-protocol-1003` |
| 分支 / HEAD | `codex/so101-head-file-protocol-1003` / `536ee1f53e40f97020190fcd7d3bdda4d7f8d87d`，另有大量未提交实现，HEAD 不能代表完整运行源码 |
| 子模块 | `495c3d6f512b5301405fc0955576bc231e344a7f` |
| 账本快照 | `docs/experiments/so101-head-file-protocol-1003-experiment-ledger.md`，当时读到 `CP-HFP-765` |
| 唯一 evidence root，以下记为 E | `/data/work/so101-evidence/act-data/20260930-antzb-head-search-krIv681m` |
| 阶段一证据子树，以下记为 N | `E/head-file-protocol-1003` |
| F015 Astra 复审报告 | `N/reviews/astra-stage1-remediation-20261006-002/review.md`；SHA256 `19da648c6f1f80055cd98e8bb984e803df09334b8b148459efe480d79d99c9f2` |
| 机器判定与独立读回 | 同目录 `review.json` / `readback.json`；SHA256 分别为 `a23c645fedf6a56c4d77258f4a8576d22d5886c763ec71df27471d5ca2cd6c3e` / `bd286300f63fb9d2337b7c34cd8f93f39206db7f2aa22d3f1dbd207654d4c53e` |
| F015，以下记为 F | `N/freezes/stage1-astra-fixes-20261006-015`；`freeze.json` SHA256 `a5fb3450da59e2bfff452de5823efdf0bb070f71f7ff59a129b541e163a7fecc` |
| 正常运行 execution inputs | `F/inputs/execution-inputs.json`；SHA256 `0356ae634b6314d200a25d0372b0bc98d0616a533d6c8e041cb5ed3ae0bca818`；异常探针各有独立绑定的 inputs |
| 修复交接，以下目录记为 M | `N/astra-fixes-20261006-001/final-remediation-handoff.json`；M 为其父目录 |

子模块 pin 以现场完整字符串为准，实施时须重新读取；本文件不授权 checkout、更新子模块或覆盖 dirty work。

`CP-HFP-756` 撤回此前 A–G 全部完成的整体结论；`CP-HFP-757` 登记修复授权，`CP-HFP-765` 登记 F015 修复后的独立复审与剩余限制。F013/F014 是保留的未接受候选，不能作为已接受的生产 profile。原始首轮报告与 F012 继续保留，不能用 F015 的通过结果覆盖旧结论。

复审剩余三类问题不转写成新的已确认源码缺陷：

| 剩余项 | 已知事实与第二阶段处理 |
| --- | --- |
| GAP-01，P2，OPEN | F012 原九个 Head 失败的调度、失败读数和退出转换时间线不足。F015 Head 全绿不能反推旧失败与实现无关；不把 I/O/TraceRoost 假设写成根因 |
| GAP-02，P2，OPEN_CAUSE | Teleop 原空 cmdline 失败读数缺失；retry-owner 的安全拒绝码差异已在精确 F012 诊断复现，但原失败归因仍有限。不能称本轮新增 Head 回归，也不能称原因已关闭 |
| GAP-03，P2，历史原件缺失 | F001/005/009/010/011 旧 build/XML 不可重读。用户已确认部分缺失来自磁盘空间耗尽后的手动数据清理；原件覆盖缺口仍保留，不补造文件，不据此改变旧测试判定 |

用户于 2026-10-06 补充：部分历史 build/XML 因磁盘空间满而被手动清理。这是用户确认的清理背景，补充在本设计中，不回写 Astra 原报告。当前没有逐文件清理清单，不能将该原因外推到所有缺失文件。被清理的原件继续标记 `evidence_unavailable`；保留的分类记录可以引用，但不能当作原件已经恢复或可重新核验。

清理原因与测试失败原因分开记录。磁盘空间满解释了这部分证据为何被清理，不证明当时 build 或测试失败也由磁盘问题造成。GAP-01/02 的原复审判定、普通/package 门禁记录和 F015 的验收范围不变；现有证据仍不删除、不覆盖。

用户于 2026-10-06 决定：历史失败归因暂不追查，不作为第二阶段的前置阻塞。GAP-01/02 中的历史归因，以及 GAP-03 中已缺失原件的追溯工作，处置记为 `DEFERRED_BY_USER`；这与原复审的 `OPEN/OPEN_CAUSE`、`evidence_unavailable` 分开保留，不表示原因已查明或原件已恢复。不为这些旧问题单独重跑历史环境，也不补造已清理的 build/XML。

若后续再次出现相同边界的失败或类似症状，按新的运行登记并详细归因，不能先假定与历史失败同因。保留当次源码和安装产物、配置与输入绑定、完整日志与测试 XML、失败读数和时间线，以及相关 PID、实际退出码和停车/退休证据；区分调度、资源、数据缺口与代码问题，给出可验证的根因和修复证据。若需修复，先定向 RED/GREEN，再按影响范围执行真实运行或集成门禁。当前可复现的失败、已证实的合同违规，以及当前 run 缺必需原件，不属于这次暂缓范围。

F015 复审基线中，demo 普通 xdist/package 分别有 304/322 个 fail/error，Teleop 普通 xdist/package inner 分别有 17/18 个；两包 Head/neck 失败均为零。native support/JTC/plugins 内层 168/821/48 例与 wrapper 16/5/6 例均零 fail/error/skip。这些计数不是后续修复的实时状态。Head 子集和 native 通过不能替代普通整包通过；本设计不豁免当前仍失败的测试，也不承担补齐全部历史归因的任务。

第二阶段只审核单次 Head Search 执行，不包含模型重训、17 项参数重新校准、40 场景资格测试、三 anchor、Teleop 视觉验收、非 Head 抓放、ACT Recorder/QC 或并行 campaign。既有合同保留，但不把它们混入本程序的单次审核判据。

用户确认的简化范围如下：不实现完整 CDR 消息解析器；不重算 quintic 极值、碰撞/clearance 或完整指向控制算法；内部计数与 PID/thread 信息主要用于诊断；退出检查只关联本次 owned 资源；冻结依赖按实际检查需要读取。文件完整性、跨运行身份、停稳取新帧、结果有效性、不同帧锁定、有界结束和实际停车仍需检查。移出的独立验证能力标记为首版不评估，不伪装成通过；执行端现有安全检查和预算不变。

## 2. 职责边界

审核程序没有运动权限。它不启动 ROS、MuJoCo、MoveIt 或 CUDA，不加载 YOLO 做推理，不调用 action/service，不发送 cancel、revoke 或 stop，不读取在线共享状态，也不等待主进程提供额外消息。

主进程不启动审核子进程、不等待审核 ACK、不读取审核结果来决定动作。审核未运行、崩溃、没有读权限或报告失败，都不影响已经发生的执行结果。未来上层可以在执行完成后据报告决定是否接纳一次运行，不能把审核重新接入逐动作准入路径。

本程序分别回答“记录是否完整、搜索结果是什么、可观察的执行是否有问题、是否实际停车、还缺哪些证据”。它不宣称独立防卡死，也不能证明日志之外从未发生任何动作。SHA256 用于发现字节变化和绑定版本，不是可信签名；自报日志不能抵御恶意生产者整套伪造并重封存。原始回调、原始 joint、外层退出记录应交叉核对，证据强度与缺口明确写入报告。日志不完整不等于动作失败，搜索失败不等于日志损坏；任何报告都不自动废弃 ACT episode 或干预 Teacher。

## 3. 方案选择与代码归属

考虑三个方向：

| 方案 | 取舍 |
| --- | --- |
| 单次离线审核入口，复用磁盘校验和纯计算组件 | 推荐。输入和报告简单，能独立验证，不带运行时依赖 |
| 直接扩展现有 qualification aggregator | 其 40 场景、10 Hz cadence、anchor 和 Teleop 门禁会污染单次搜索审核；不采用 |
| 新建监督服务、数据库或 LLM 审核框架 | 当前无需在线服务或交互判断；不采用 |

现有 `src/so101_demo_py/src/act/head_run_evidence.py` 是生产 writer 和 sealer；读取方不实例化它。`head_search_aggregate.py::aggregate_qualification` 是整体资格聚合器，不是本次单 run 审核器。`head_policy_audit.py` 是校准测量审核及旧子进程协议，也不能直接当成本次入口。

拟新增正式入口 `so101_head_search_audit`，归属 `so101_demo_py`，并通过 `setup.py` 安装。建议分为以下模块，名称属于本设计提案，尚未实现：

- `cli/head_search_audit.py`：参数、退出码和报告发布。
- `act/head_run_reader.py`：只读文件验证、版本适配、流式事件读取。
- `act/head_run_audit.py`：按 goal、observation、motion epoch 建立状态并审核。
- `act/head_run_audit_report.py`：稳定机器报告和可读报告。

从现有 aggregator 复用哈希、引用验证、问题定位等适合的纯磁盘能力；不为复用引入全套 qualification gate、ROS adapter 或 producer 的通过结论。若抽取公共工具会影响旧 reader，保留原格式和行为并增加回归。审核只重算本稿列出的时间、关节范围、中心误差和事件关联，不调用 producer 的 `validate()` 后照抄返回值，也不新增轨迹安全或控制算法实现。

## 4. 输入与版本合同

### 4.1 单次运行原件

输入继续使用第一阶段目录，不另造第二份运行数据：

```text
run/
├── manifest.json
├── events.jsonl
├── artifacts/
├── completion.json
└── seal.json
```

已观察到 `file_protocol_version=1`；manifest 的 `run` 包含 `run_id/session_id/epoch/generation`，还包含 `execution_inputs`、`freeze_receipt`、`refs`、policy digest、scope 和资源声明。completion 记录 `execution/business_return_code/complete_composition`，可能含 failure。seal 保存 `files` 的 path/size/SHA、event/artifact 数量和 writer counters，不含自身 hash。

F015 实际事件外层字段为 `schema_version/record_schema_version/run/source_sha256/config_sha256/model_sha256/owner/sequence/kind/record/source_stamp_ns/observed_mono_ns/occurrence_mono_ns/artifact_refs`。`run` 是四项身份；`owner` 记录实际生产者 `pid/thread_name/thread_native_id`。`record_schema_version` 取自内层 record，内层没有 schema 时合法为 null；不能要求所有内层都虚构版本 1。全局 `sequence` 是文件顺序，与 `record` 中 joint、observation、exposure 的序号不同。

ASTRA-02 的逐事件身份和普通生产 action 原件已交付。reader 的第一版 profile 使用 F015 的协议映射，以 run 的 execution inputs 和冻结记录识别当时版本；`source_sha256` 不等于 Git HEAD，也不等于 `freeze.json` SHA。逐事件 source/config/model digest 与 manifest 声明匹配，controller boot/incarnation 按动作关联需要读取。PID/thread 保留为诊断来源，不要求每次审核证明所有线程的实现正确性；缺该信息不自动判搜索失败。

以下是已从 F015 原件和源码核对的映射；实施计划要将条件必需字段、单位和嵌套路径落实为完整 schema 测试，不改变这些事件的现有含义：

| 事件 | 实际原件与关联方式 |
| --- | --- |
| `HEAD_ACTION_SDK_RETURNED/HEAD_ACTION_SDK_ACCEPTANCE/HEAD_ACTION_SDK_RESULT/HEAD_ACTION_SDK_CANCEL` | record 为 `schema_version/goal_uuid/callback_wall_ns/callback_sim_ns/original`；original 是实际 SDK 返回或回复，分别检查 future/accepted、UUID/stamp、status/result、cancel reply |
| `HEAD_ACTION_STATUS` | 同一 action record 格式；original 的 `goal_info.goal_id.uuid` 与 `status` 用于独立对账，不能只信本地 accepted cache |
| `HEAD_ACTION_SERVICE_REQUEST/HEAD_ACTION_CANCEL/HEAD_ACTION_GET_RESULT` | 实际独立观察者请求与回复，仍按 UUID 和 occurrence 关联；请求原件含 CancelGoal 的 `goal_info` 或 GetResult 的 `goal_id`，按冻结布局区分，不预造 service 字段 |
| `SEARCH_OBSERVATION_REQUESTED` | `record.request` 含 observation sequence、motion epoch、settled floor、原 search deadline 与 policy 身份；`record.budget` 保存当时重观察预算 |
| `LIVE_STOPPED_OBSERVATION_FINISHED/LIVE_STOPPED_OBSERVATION_HANDOFF` | `record.record` 含 request/SHA、observation sequence、可为 null 的 admitted exposure `sequence`、outcome、原始 Image/Info/TF/joint 身份、推理/验龄/handoff 时钟和检测输出 |
| `SEARCH_EXPOSURE_DECISION` | `record.observation` 含 exposure sequence/source、core tick、实际 current joint、decision、track 与 lock count；与前述原始观测关联后重算，不把结果自报当结论 |

原始 acceptance、result、Cancel/GetResult 的必需性由实际路径决定。normal013 没有调用独立 GetResult/Cancel，不要求生成这些不存在的请求；unknown006 故意扣留 acceptance 回调，不要求它出现在普通生产日志中，但必须由独立 status、请求/回复、故障及停车记录完成对账。确有调用而原件缺失时才报告覆盖缺口。外部探针 instrumentation 只解释注入和扣留事实，不替代普通生产回复。

物理文件协议版本和事件 schema/producer profile 分开。新审核器报告自身 `audit_schema_version=1` 与 `ruleset_id=head-file-postrun-basic-v1`；producer profile 由明确的版本/冻结引用识别，不凭字段猜版本。首版只实现已核对的协议映射，旧输入能否按该映射解释由覆盖报告说明，不为历史日志单独开发全面兼容层。缺失原始回调不得从派生 `settled` 记录补造。未知版本不妨碍字节完整性检查，但受影响的语义检查为 UNKNOWN；纯诊断扩展可忽略其语义，仍验证已封存字节。

### 4.2 冻结依赖与外层证据

必须读取 run 内 seal 列出的全部文件和 artifact，校验大小与 SHA。外部依赖按规则需要读取：execution inputs、相关 policy 阈值及版本绑定记录是基本来源；camera geometry、controller config 只读取本次计算使用的字段。首版不遍历完整 source/install 闭包，不读取 scene/URDF 做碰撞重算，也不要求每次重新哈希完整 YOLO 权重。报告区分“记录中的 model digest 一致”和“实际模型字节已独立验证”，不能将前者写成后者。若某份文件本身属于 run 的 seal 清单，仍必须验证，不因用途缩减跳过完整性检查。

被读取的外部引用必须位于 E 内，大小和 SHA 可验证。不下载缺失文件，不访问网络，不用当前工作区的新配置代替当时原件。某项计算缺其必要配置时，仅该项为 UNKNOWN；未纳入首版的依赖没有原件，不阻止其他检查。

还要有一份独立外层执行证据，绑定同一 run、实际启动命令及可执行文件身份、真实 OS 退出码、退出后 owned 资源检查的原始引用。已有 launcher 记录通过只读 adapter 映射到该合同，无需重写历史文件。外层证据不能只是把 completion 的拟返回码再抄一次；它必须来自等待该进程结束的外层执行者。

F015 正常路径已有 `M/production-astra-normal013/launcher-result.json`，字段包括 `argv/python/formal_sha256/freeze_sha256/inputs_sha256/owner/started_ns/ended_ns/actual_os_return_code/run_root/ros_domain_id/partition`；探针对应 `M/serial-probes/<run-id>/outer/launcher-result.json`。`started_ns/ended_ns` 是外层 wall 时间，不能与事件 monotonic 直接相减。`M/normal013-G-acceptance.json` 及探针 acceptance 提供 launcher、inputs、seal、postflight 的 path/SHA 索引；F015 adapter 以该索引作为 `--execution-receipt` 的输入，实际退出证据仍必须追溯到外层 launcher。审核只使用索引和原件，忽略 acceptance 的通过布尔值及人工结论。缺 postflight 使清理覆盖为 UNKNOWN，不自动否定文件完整性、搜索或停车结果。

正常 postflight 在 `F/inputs/postflight/result.json`，探针在各自目录 `postflight/result.json`。只核对本次 owned PID、child、domain/partition 等声明资源及退出后采样顺序；按这些资源实际需要读取对应 ps 或 graph 原件。tmux/GPU/Docker 不要求全机为空，与本 run 无关的服务不算失败。`ready=true` 不是 owned 清理证明；不足时报告清理覆盖 UNKNOWN，不把人工已接受直接变成程序 PASS。

外层证据路径和 SHA 由调用者显式传入。实施前冻结其已有格式映射；缺 run 绑定、实际 OS rc 或 owned 清理原件时，分别报告受影响项 UNKNOWN，不能从当前 `/proc`、GPU 或 ROS graph 推测历史。退出前 child retirement 与退出后检查分别报告，不复刻所有内部 worker 退休状态机。

内部 artifact 使用 run-relative 路径，拒绝绝对路径和 `..`。外部冻结引用使用 E 内绝对路径；已存在的 acceptance 索引中有 `M/../freezes/...`，只读 adapter 可对这类已声明外部引用做规范化，保留原字符串与规范路径，逐段检查无符号链接、无越出 E，随后验证 regular file、大小和 SHA。不得把这种兼容用于 run 内 artifact 或任意目录遍历。拒绝 FIFO/device、符号链接跳转、越界引用和目录枚举逃逸。仅追踪声明的必要引用，不扫描整个 E，不读取旧 native capability/provision 密钥内容；通道身份和 ACK 需要可审计记录，不能依赖仍可连接的在线通道。

引用内容按实际需要的固定格式读取：JSON 使用严格、有界解析；必要的 YAML 配置仅用 safe loader。首版不开发历史 build/JUnit XML 读取功能。配置里的 plugin、module 或 executable 名称只是数据，不动态 import 或执行。正常 marker 缺失、未知格式或格式超出已支持范围均明确报告，不能拿生产运行库来“帮忙打开”。

### 4.3 只读性与不完整输入

用只读句柄验证 regular file、大小、SHA；读取时记录文件身份，结束时重检已读取原件的身份/大小/哈希和 run 清单。发现输入变化，记完整性缺口，按第 6.1 节合并结果；受影响文件不再支持语义结论，不继续把混合版本当同一运行分析。输出不得位于 run、冻结依赖、输入原件或其子目录中。

审核输入应为已结束的执行。无 seal、无退出记录或 JSONL 尾行截断时，可以只读分析完整前缀，并分别标记完整性和退出证据缺口。已有可信违规仍单独报告，不能用缺口遮掉它，也不能把其余未记录部分猜成成功或失败。不等文件继续增长，不补造尾行、不续跑搜索、不生成新 seal。不完整行只记录位置和错误类别，不输出任意损坏内容。

## 5. 审核顺序和规则

处理顺序为：输入边界检查 → 字节与版本验证 → 原始事件关联 → 数值和状态重算 → 终态/退出核对 → 报告发布。完整性失效的文件不能支持语义通过；仍可记录可信文件上的已证实问题，明确各结论依赖的字节范围。

每项必需规则输出 `HOLDS/VIOLATED/UNKNOWN/NOT_APPLICABLE`。`NOT_APPLICABLE` 必须有触发条件依据，例如没有发出 goal 的 entry refusal 不要求 goal result；缺日志不是不适用。

| 规则 ID | 首版检查 | 结果归属与边界 |
| --- | --- | --- |
| HFA-001 | 文件清单、大小/SHA、UTF-8/严格 JSON、连续全局序号、引用、writer 丢失/故障计数；拒绝重复 JSON key、NaN/Infinity、布尔值伪装整数 | 完整性；必须检查 |
| HFA-002 | run/session/epoch/generation、必要 controller 身份；事件声明的 source/config/model/policy 与 manifest 一致，禁止跨运行拼接 | 身份矛盾为执行问题；PID/thread 和整套冻结闭包是来源信息，不做全系统证明 |
| HFA-003 | 同 UUID 的结构化目标、实际 send、acceptance/result/status 关联；检测同 UUID 重复派发；对实际出现的 UNKNOWN、Cancel/GetResult 回复对账；原始 CDR artifact 校验字节哈希 | 执行问题；不解析完整 CDR，不宣称全部线上字段等于 typed payload |
| HFA-004 | 结构化目标的 joint scope、有限值、时间递增、必要向量形状和关节范围；关联目标与实际 joint/terminal，报告执行偏差和故障 | 执行问题；不重算 quintic 极值、速度/加速度极值、collision/clearance 或完整轨迹安全性 |
| HFA-005 | 原始 advancing joint 和匹配 terminal 支持停稳；capture 的 sim source 和 receipt 晚于本次 settled floor；Image/CameraInfo 及使用到的 TF/joint 身份一致 | 执行问题；保留停稳后取新帧检查 |
| HFA-006 | 请求、推理结果和实际 consume 的 job/frame/motion epoch/generation、source/receipt/age 一致；过期或错身份结果没有提交 target/track/lock | 执行问题；不从普通日志证明 owner 锁内原子性 |
| HFA-007 | 原总搜索期限、可观察的请求生命周期、重复请求、有限重观察和结果丢弃；不允许无界继续或重置整体期限 | 总期限和可证实的重复派发/非法消费属于执行问题；request/exposure/retry 内部计数差异只作诊断，不逐项复刻预算状态机 |
| HFA-008 | 锁定使用三个 distinct advancing VALID frame、同 track、正确 motion epoch；用检测中心与已记录图像尺寸/阈值核对中心误差，检查 lock count 和终态 | 搜索结果及执行问题；不重算完整指向、精调几何或重新运行 YOLO |
| HFA-009 | 成功或异常后的 Stop 起点、实际 close/cancel/terminal 及连续 quiet joint；UNKNOWN 按实际路径对账；核对已批准 Stop/native close 预算 | 停车；Cancel ACK 或 raw_stop_confirmed 布尔值不能单独证明停住 |
| HFA-010 | seal、实际 OS rc、业务返回码、owned child 退出与本 run postflight；forced kill、未退出资源和缺口分别记录 | 退出/清理；不要求全机 ps/tmux/GPU/Docker/ROS graph 为空，不复刻全部 worker 退休过程 |
| HFA-011 | LOCKED、有限未找到、entry refusal、fault 等与实际事件及 completion 一致 | 搜索结果与声明一致性；不以自报 SUCCEEDED/FAILED 代替证据 |

typed trajectory 与实际动作通过 UUID、原始回调和日志中的绑定关联。CDR 只校验保留字节和声明 SHA，首版不实现消息二进制解析器。报告明确 `wire_payload_equivalence=NOT_ASSESSED`；结构化目标与全部线上派发字段等价性不属于首版必需规则，不因这一移出范围使正常 run 的所有结果 UNKNOWN。UUID、目标或回复之间出现可观察矛盾，仍报告执行问题。

轨迹安全和完整控制算法继续由执行端及其代码/运行测试负责。首版报告 `trajectory_safety_reproof=NOT_ASSESSED`、`pointing_algorithm_reproof=NOT_ASSESSED`；不能把 producer 自报的 collision safe 变成独立安全结论，也不能为减少审核工作删除生产检查、修改阈值或清理原始轨迹证据。

三帧连续性的 reset/保留行为按修复后冻结 profile 逐项定义，包括 miss、expired、track 改变和新 motion epoch，不能自行选择更严或更宽的算法。原始 YOLO 输出可以支持“执行按检测结果正确决策”的判断，不证明识别的物体确实是杯子；模型效果另行评测。

ASTRA-R05 的已接受实现合同是：owner 在同一锁中清空 pending request 并推进 `_completed_observation_sequence`；读取端只暴露不超过该完成 watermark 的观测。producer 先追加 FINISHED/HANDOFF，而 infer 尚未返回，是合法内部交错；不得仅凭这两个事件就认为消费者可重提请求，也不要求消费者等 CUDA 或重设预算。

F015 普通日志没有独立的 owner watermark/release 事件，不能从日志声称观察到了锁内原子性。HFA-006/007 只检查可见请求、消费、discard、后续请求和总期限；锁内交错由已有源码与 producer→owner→consumer barrier 回归负责，不列为审核器的新验收任务。内部状态未记录属于方法覆盖边界，不预造日志或误判为搜索失败。可见事件证实重复派发、非法消费或无界重观察时，执行检查为 FAIL；某项必要因果关系确实无法判断时，仅该项为 UNKNOWN。

### 时钟与超时

monotonic wall 和 sim source 分开计算，不相减；跨 owner/boot 的 monotonic 不能直接比较。全局 append 顺序只用于完整性，因果关系使用 occurrence、关联 ID 和显式阶段。回调晚到或记录交错本身不算违规。

审核原始整数 ns；历史 float wall_s 按 profile 声明的转换和精度处理，报告转换来源。不能凭最后一位浮点差异新增硬失败，也不能悄悄放宽现有 policy。精度不足以确定边界时记 UNKNOWN，并给出数值区间。

延迟、丢帧、gap、miss、expired、retry 和 outlier 作为诊断统计。允许的丢弃与有限重观察是正常路径，不要求上层流水线零超时。job/准入超时后合法丢弃、失败退出或停车，记录该异常，不因此认定日志损坏或控制违规；消费过期结果、无界继续、重置总期限或违反已批准 Stop/native close 预算仍是执行/停车问题。精确内部 budget 计数不是首版硬门。没有新增 10 ms、精确 2 ms 或固定 10 Hz 的单次审核硬门；ACT Recorder 的 10 Hz 门和整体资格旧门不由本设计改写。

## 6. 结论、报告和退出码

### 6.1 各类结果分开，不输出总通过判定

报告不再使用一个 `audit.status` 汇总所有问题，分别保存：

| 字段 | 状态与含义 |
| --- | --- |
| `integrity.status` | PASS/FAIL/INCOMPLETE：run 文件和已读取必要引用是否可读、完整、未被改动 |
| `search.outcome` | LOCKED/NOT_FOUND/REFUSED/FAILED/UNKNOWN：日志支持的搜索结果，另保留 completion 原声明、业务 rc、实际 OS rc |
| `execution_checks.status` | PASS/FAIL/UNKNOWN：本稿范围内的可观察执行检查，明确每项覆盖；PASS 不代表整套控制系统已证明安全 |
| `stop.status` | PASS/FAIL/UNKNOWN/NOT_APPLICABLE：实际停车与适用预算；无任何动作且无停车义务才可不适用 |
| `exit_cleanup.status` | PASS/FAIL/UNKNOWN：本次退出、owned 资源清理与返回码/声明一致性 |
| `coverage` | 逐规则的 HOLDS/VIOLATED/UNKNOWN/NOT_APPLICABLE、证据缺口及明确移出的 NOT_ASSESSED 能力 |
| `report.status` | COMPLETE：报告已完整发布；发布中断没有有效完成标记，外层记 AUDIT_NOT_COMPLETED |

历史复审和整包 UT 状态不作为单 run 结果必需字段；可保留参考 path/SHA，不要求每次重述 F/G、GAP 或追查历史。用户暂缓历史归因的处置仍保留在本设计及原复审记录中，不改写旧判定。报告不授予 qualification，不输出阶段一完成或 ACT episode 接纳结论。

各类结果只按自己的证据判定。execution_checks、stop 和 exit_cleanup 内，任何适用规则 VIOLATED 则该类 FAIL；没有 VIOLATED 但有必要规则 UNKNOWN，则该类 UNKNOWN；所有适用的必需规则 HOLDS 才能 PASS。NOT_APPLICABLE 不补成 HOLDS，也不掩盖缺口；没有停车义务时 stop 才能整体 NOT_APPLICABLE。完整性先保留已证实的 FAIL，再判断必要文件缺失或输入变化的 INCOMPLETE，其余为 PASS。缺原件不等于控制故障已证实。某一类有缺口不能遮掉其他类已经证实的问题，也不能使其他已有证据的结果统一失效。

例如搜索超时后正确停止且日志完整，应报告 integrity=PASS、search=FAILED、stop=PASS，并记录超时异常；其余适用执行规则全部 HOLDS 时，execution_checks 可为 PASS，不能仅因“未发现违规”就判通过。过期结果实际参与锁定，则 execution_checks=FAIL；停车缺原始证据，则 stop=UNKNOWN。这两种情况即使文件哈希全部一致也不能隐藏。搜索效果 benchmark 与 ACT QC 另行判断。

完整性分类为：seal 清单文件或必要引用缺失、无 seal、未封存尾行截断 → INCOMPLETE；已存在文件的 SHA/size 不符、封存 JSON/schema 无效、全局序号重复/跳号/倒序 → FAIL。动作/帧身份冲突和违规结果消费归 execution_checks；缺回调只影响依赖该回调的检查，不能仅凭缺记录判断动作失败。INPUT_CHANGED 记完整性缺口，若没有已证实的完整性 FAIL，则 integrity INCOMPLETE；受影响语义为 UNKNOWN。参数非法、输出冲突或内部异常属于工具失败，不伪装成完整报告。

### 6.2 报告位置与内容

输出到 E 下此前不存在的 `reviews/<run-id>/<audit-id>/`，不覆盖旧报告。至少包含：

```text
audit/
├── review.json
├── review.md
├── metrics.json
├── input-readback.json
└── audit-completion.json
```

`review.json` 是机器接口，字段包括 schema/ruleset、producer profile、auditor 版本/digest、已读取 run/seal/外层证据 SHA、第 6.1 节各类结果、逐规则结果、coverage 和 findings。每个 finding 有稳定 code、类别 `INTEGRITY/CONTRACT/EVIDENCE_GAP/DIAGNOSTIC`、受影响的结果字段、严重程度、原始文件 SHA 与行号或 event sequence、相关 UUID/frame/job/motion epoch、expected/observed 和计算依据。byte offset 等额外定位可选。不复制大图、完整模型、密钥或任意环境变量到报告。

严重程度固定为 `ERROR/WARNING/INFO`：已证实完整性或执行/停车违规为 ERROR；影响判断的证据缺口为 WARNING，仅使依赖它的规则 UNKNOWN；允许丢弃、有限重观察与一般统计为 INFO。一般超时异常可为 WARNING，不能只因其存在将文件完整性或停车改成 FAIL。finding 没有事件位置时写 null 和缺失的文件/字段名，不造 event sequence=0。

metrics 保留逐 observation/goal 的 timing 和耗用预算，再给 count/min/max/median/p95 汇总；样本不足也报告数量，不伪称稳定分布。Markdown 使用同一机器结果渲染，说明首个问题、缺什么原件以及能支持什么结论，不另行作一套判断。

同输入/profile/ruleset 的各类结果、规则和计数应一致；audit ID、UTC、耗时、输出路径不参与结果等价比较。首版不新增跨存储位置的 `semantic_digest` 合同。机器报告和 Markdown 使用同一结果；所有报告写临时文件、fsync、原子发布并同步目录，最后发布 `audit-completion.json`，列出报告 hash/size。发布中断留下不完整报告，不得被下游当完整审核。

审核前后 input-readback 核对原件清单及 SHA 不变；审核输出里的临时索引归本审核所有，不进入原 run，也不作为下一次 resume 输入。保留原始 run 的全部字节，原 seal 永远不重写。

### 6.3 拟定 CLI

以下是待实现接口示例，不是当前已有命令或运行证据：

```bash
so101_head_search_audit \
  --run-root /absolute/sealed-run \
  --execution-receipt /absolute/external-execution-index.json \
  --execution-receipt-sha256 <sha256> \
  --output-root /absolute/new-audit-directory
```

CLI 只做单 run 串行审核，无 resume、watch、daemon、自动重跑、在线探测或批量并行功能。不提供跳过 Stop/身份/哈希、强制通过或覆盖 policy 的 flag。规则 profile 从冻结输入识别，报告其版本，不能通过选一个宽松 profile 给同一运行改判。

| 审核进程退出码 | 含义 |
| --- | --- |
| 0 | 完整报告已发布，integrity PASS；搜索、执行、停车、清理结果须分别读取，不能把 rc0 当全部通过 |
| 1 | 完整报告已发布，integrity FAIL |
| 2 | 完整报告已发布，integrity INCOMPLETE |
| 3 | CLI 输入/输出冲突、资源限额或内部工具失败，报告未完成 |

`--help` 返回 0 不代表审核完成。外层同时记录审核进程实际 rc/stdout/stderr；报告 hashes、完成标记、integrity 与实际 rc 一致时，才确认报告完整发布，不据此接纳训练数据。execution_checks/stop 的 FAIL 必须保留在报告和 Markdown 摘要中，不能被 rc0 遮掉。没有报告或进程被信号终止时，外层记 `AUDIT_NOT_COMPLETED`，不沿用旧报告。

## 7. 资源、稳定性和兼容

审核单进程、CPU-only，不引入运行时主进程通信。大型文件以固定块流式哈希，事件至少两遍流式读取，不一次载入所有 RGB 或整条 JSONL。输入顺序不是因果顺序，关联索引记录定位和必要状态；跨线程晚到关联在第二遍处理。

第一版读取限额建议为：单事件 1 MiB、JSON 深度 64、单份结构化文档 16 MiB、一个 run 最多 2,000,000 事件/100,000 artifacts、关联 goal 和 observation 各最多 100,000。原始图像等二进制 artifact 按块读取，不受结构化文档限制。超限明确作为工具资源限制退出 3，保留精确边界，不记搜索或执行失败、不悄悄截断为完整结果；这些是审核器内存/解析防护，不是运动或感知阈值。

索引和逐样本报告可流式落在独立输出目录，内存按块处理。容量不能通过无限读入或移除校验规避；更大任务需要显式调整审核资源设计，本次不做通用 campaign 审核服务。日志错误处理非递归，内部异常只产生一次有界失败说明。

不修改共享 ACT、旧资格 reader 或生产控制合同以适配审核器。若正式 producer 必需字段仍缺，先提出精确协议缺口，由阶段一修复任务处理并新 freeze/new run；审核器不生成“补齐后的”原件。生产 source/config/policy 变化仍使旧 live/bundle/QUALIFIED 失效；旧运行可继续审计，只能说明旧版本。仅审核规则升级重新审核旧 run，不代表已经验证新 producer。

## 8. 回归语料与验收

### 8.1 从真实原件建立语料

冻结语料索引，保存每个 run/seal、外层证据、producer freeze 与人工预期的 SHA/路径及理由：

| 语料 | 用途 |
| --- | --- |
| `N/runs/hfp1006-normal011` | 已实际完成五次观测、三帧锁定和 Stop；原始 action 缺口报告在对应规则 coverage 中，不强求所有结果都有结论 |
| `hfp1006-probe-camera004` / `hfp1006-probe-feedback003` / `hfp1006-probe-unknown004` | 已发生的故障、真实 SDK UNKNOWN/回调丢失、停车和退休；按原件覆盖判断，不把外部 instrumentation 冒充普通生产日志 |
| `hfp1006-probe-unknown001` 等未封存运行 | 缺原件、缺 terminal/退出证据的分类，不伪造完整性或故障原因 |
| `hfp1006-astra-normal013`，F015 | 正式正常语料：7759 连续事件、106 artifacts、105 Image/Info pair，三次非零 goal、五次停点 CUDA 观测和三帧锁定；OS/business rc0，预期 integrity PASS、search LOCKED、execution_checks/stop/exit_cleanup PASS |
| `hfp1006-astra-camera006` / `hfp1006-astra-feedback005` / `hfp1006-astra-unknown006`，F015 | 串行实际异常语料：真实非零运动/SDK 请求，独立 Cancel/GetResult、原始 Stop/native ACK 与退休；OS/business rc1、complete FAILED，预期 integrity PASS、search FAILED、stop/exit_cleanup PASS；适用执行规则全部 HOLDS 时 execution_checks PASS，注入故障另报异常 |
| 不可变交接 RED/GREEN，参考材料 | `M/immutable-handoff-red-001` / `M/immutable-handoff-green-001` 是既有 owner 接口回归，不作为首版审核器必须重跑的验收任务，也不伪装成新的 MuJoCo run |

四个 F015 run 的 `seal.json` SHA256 已只读核对，分别为：

| run | seal SHA256 |
| --- | --- |
| `hfp1006-astra-normal013` | `24b8964dc5c6a8a4d04e1d9f957ff3a71149592d8f61e6aa380c4541817612cc` |
| `hfp1006-astra-camera006` | `6d72d7333160efc0ecabdecb15fbecbd4fc91e9990c9a0f9f4212c8ccc053f24` |
| `hfp1006-astra-feedback005` | `e442018ca9360f138c56109877f27bea0d2238e948e1070e496652273d5471e9` |
| `hfp1006-astra-unknown006` | `0dad81b43b4e56704e8d21ee5d739f934a4f4e068700276b625854aebd9a77db` |

normal013 的验收索引为 `M/normal013-G-acceptance.json`，SHA256 `4850cb2e666b11896aafa7c228802166ecd0383e3a30fbf55383802fdbb70d30`；三个探针索引为 `M/serial-probes/<run-id>/acceptance.json`。按本稿检查范围冻结各自 inputs/launcher 和 owned postflight 引用，不能只使用 seal 或人工结论。表中各类结果是待实现程序的预期，不是已执行结果；发现必要字段缺口时，对应项为 UNKNOWN，不强制判绿。F015 是已保留的历史运行语料，不代表 UT 修复后当前源码仍为 F015；新 profile 必须单独核对映射。

新 unknown006 的实际 SDK UNKNOWN 区间是 1,209,723 ns，只证明短暂 UNKNOWN 与 acceptance callback 扣留，不能称持续 400 ms 超时已验证。它的故障先于 admission resume，后续 `HEAD_ADMISSION_REVOKED` 是撤销保持生效，不能改写成正常成功。三个探针实际 GetResult 为 terminal6/error-1，normal013 为 terminal4/error0；不能混称为成功终态。

camera006/feedback005 在真实非零运动后分别扣留 4 条/10 条 primary 记录；原始证据仍留存，不能记为 writer 数据丢失。normal013 的 66 次未准入帧替换与 writer drop0 同样是不同计数。原件分别支持 fault→native ACK 8.18/13.45/16.97 ms、fault→raw Stop 48.30/55.94/57.59 ms，报告重算这些数值及原预算，不新增更紧阈值。

旧 UNKNOWN004 也不证明持续 400 ms UNKNOWN；normal011 与 normal013 均不能证明真实 EXPIRED→reobserve 路径已在仿真执行。normal013 的五次结果是 VALID，真实 discard→下一 VALID 和 owner 原子交接已有定向接口回归，验收须准确标注层级，不据此额外重启仿真。缺某个未来批准边界所需实际路径时另报缺口。全部测试/回放原件继续保留，旧 helper 缺调用时 dirty source SHA 的限制不补写、不由新不可变 receipt 追认。

变造负例放 E 的独立审核测试语料目录，逐例记录 derived-from、改动和预期，使用独立副本；不得对原件使用可写硬链接。单独测试未更新 seal 的字节篡改，以及重新计算副本 seal 后仍应被语义审核抓住的违规。后者是审核器测试，不是真实运动失败。

### 8.2 必需测试

定向 RED/GREEN 覆盖文件边界、缺失/篡改/截断、版本和单位、身份错配、实际动作/回复关联、关节范围和非法结构化目标、错误 settled floor、过期结果实际消费、重复帧锁定、总期限续期、取消 ACK 假冒 Stop、缺 owned 退出/OS rc，以及合法丢弃与重观察。搜索失败但日志完整且正确停车必须准确分开报告。缺 PID/thread、未遍历完整模型/安装闭包、没有全机清空证明，以及内部计数的纯诊断差异，均有不误判搜索失败的正例；某项必要原件缺失仅影响依赖它的结论。

已关闭的五项代码问题对应不同回归，不再当作待修复问题重复下发：

| 复审项 | 首版审核回归与既有生产回归的边界 |
| --- | --- |
| ASTRA-01 | 审核可见 discard→新观测、过期结果未被消费和有界重观察；详细 request/exposure/retry 计数回归继续由生产测试负责，不要求审核器复刻 |
| ASTRA-02 | 审核 run/schema/身份一致和实际 SDK/status/服务回复关联；正常无 Cancel/GetResult、合法 UNKNOWN 回调缺失均有正例；PID/thread 仅保留来源信息 |
| ASTRA-03 | writer 故障或证据不足应影响相应完整性/覆盖，不能伪造搜索失败或 Stop。writer 坏 sink 时终态对账的生产回归不转成审核器新任务 |
| ASTRA-04 | 旧入口拒绝和 production 路由由既有入口测试负责；本审核器不修复或重验旧资格执行路径 |
| ASTRA-R05 | 不从 FINISHED/HANDOFF 推断 owner 锁内已释放，也不因没有 watermark 事件误报；锁内 barrier 回归由生产测试负责 |

静态代码递归、锁内原子性和未执行的旧分支无法仅从一份日志证明，仍由冻结源码/接口/路由测试确认；报告不得宣称日志审核已替代代码审查。旧资格入口拒绝是当前正确行为，不应成为“为审核器修复旧资格路径”的隐含任务。

独立性测试阻止导入 `rclpy/torch/ultralytics/mujoco` 和运行 resource provider，禁止网络/socket/action/subprocess 启动，验证审核仍可运行。机器报告和 Markdown 一致；相同输入重复审核各类结果一致。只读输入目录、输出路径冲突、输入并发变更、超限、写报告失败/中断都要有明确结果且不改原件。文件完整但执行或停车违规的负例必须在对应字段及摘要中暴露，即使审核进程因 integrity PASS 返回 0。

### 8.3 正式安装入口验收

代码冻结后，使用实际非 symlink 安装入口 `--help` 和上述四类输入完整执行。记录精确 executable/Python/import origins、auditor digest、完整 argv、输入 SHA、预期/实际 status 和 rc、stdout/stderr、elapsed、报告与原件前后 readback。这一层是“真实磁盘原件 → 实际安装审核器 → 完整报告”，不能只凭 mock、fixture 或 UT GREEN 宣称完成。

第二阶段默认不重启仿真。优先消费阶段一修复后的真实日志；缺所需真实路径时，报告缺口，另行获得对应生产验证授权。实施中若确实修改 producer 或其依赖，按已批准边界重新 freeze/install、以新 run 从头验证，不能用旧运行冒充新版本。

完整普通 pytest 使用 `xdist`、worker=`min(8, logical CPUs)`，按受影响模块实际普通目录分别执行；必要 package gate 和 `colcon test-result` 在计划集成边界执行。缺 underlay/依赖闭包不算代码 RED。历史 ordinary/package FAIL/OPEN 保留在原记录中，当前门禁以当次完整运行结果为准，不能沿用历史失败冒充当前失败，也不能只用绿子集冒充全量通过。此任务不改模型或 benchmark，不运行 benchmark suite。

ai-station 的 fsync-heavy pytest/colcon 使用登记 E 下此前不存在的 NVMe scratch，精确测试 Python 验证 `TMPDIR/TMP/TEMP` 和 `tempfile.gettempdir()`。antzb 不套用 ai-station 专用路径规则，沿用该任务已登记 NVMe scratch 合同并记录实际路径；不关闭 fsync、journal 或哈希。当前只设计，不运行这些门禁。

完成条件是：正式程序可安装；真实语料得到正确的分项结果；负例和允许路径不误判；问题可追溯；原件未改；离线权限隔离成立；实际安装入口、报告与退出码一致。还须跑完受影响模块的完整普通/package 门禁，本次新增失败或当前可复现的相关测试失败未关闭时不能宣布程序完成。既有独立运行时问题另行取证和修复，可作为诊断语料，不要求审核程序修复控制系统后才完成；不能宣称它们已关闭。历史归因、完整 CDR/轨迹安全/控制算法重证、整机清空和整体 qualification 均不作为本程序的完成条件。程序完成与 Head Search 运行可靠性、实际抓放和 ACT 数据 QC 分开。

## 9. 阶段衔接与审批

用户已确认简化方向，本次只修订设计。F015 四个保留 run 继续作为首版真实语料；UT 修复后的当前版本、相关新运行和新超时需在实施计划前另行核对，不把本文历史快照当当前状态。下一步核对书面范围、分项报告、输入映射及验收边界，再编写实施计划，呈现精确命令、语料、预期结果与 gate，获得执行确认后才开始第二阶段；本次更新不授权实现。

阶段一 F/G 的历史缺口仍另行保留。用户已决定暂缓历史失败归因，这部分追溯工作不再阻塞第二阶段；当前测试修复、安全合同和本次输入完整性要求不变。第二阶段仍须经过设计、实施计划及执行审批，暂缓历史归因不是实施授权。获授权后，可在已接受 F015 的单 run 合同上开发离线 reader，不接管或掩盖 GAP-01～03。后续 source/input 变化须重新核对 freeze 与复审结论，不能默认本表始终有效。没有完整抓放证据，不把 Head pointing/lock 描述成 pick-place 完成。

计划/复杂问题/Review 使用 GPT-6.1 Sol / High，Sol 工作做 inline self review；若执行者为 dst 或 Luna，按仓库规则由 GPT-6.1 Sol / High 独立复审。不能自动派新 Astra、启动第二写入者或沿用旧 goal 扩大实施权限。

后续给执行者下发时，要求任务开始前更新可见 task list，列出整个授权边界和完成条件；每个 turn 结束只更新既有项目 status，不更改项目内容。执行位置直接为 antzb，不自我 SSH。复用已确认 worktree/branch 是否合适在实施计划前重新检查，本草案不创建新的 worktree、进程或 stack。

本次只读核对保留全部原始证据，归档、删除均为零，也没有新增删除候选。之后的报告与变造语料全部纳入 E 的 retained inventory；scratch 可在回读后列为删除候选，未获用户授权不删除。没有 commit/push 授权，不发布文档或代码到远端。
