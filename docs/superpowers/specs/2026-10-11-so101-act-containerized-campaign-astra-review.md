# 审查：SO-101 ACT 容器化采集 campaign 修订设计

日期：2026-10-11。

审查对象：[容器化采集 campaign 设计](2026-09-30-so101-act-containerized-campaign-design.md)。用户明确要求本次使用 GPT-6 Astra 独立审查；此要求仅适用于本次设计，不修改仓库默认模型规则。

源码基线：Gitee `codex/so101-act-data-0917a` 的 `6baf54e6313daca287fa86e7cc248c4c2f1b1dc3`，包含 GitHub 同名分支的 `9386860dfed9bdfa840b7b51f061c299459bd390`。两端分支均通过 `git ls-remote` 读回。本次在本地 `main` 上修改文档，源码对照使用该提交的独立只读 snapshot。

审查方式：GPT-6 Astra / High，对冻结文档做静态只读审查；未启动服务、容器、ROS、MuJoCo、SSH 或测试。证据根为 `/tmp/so101-debug-container-current-design-20261011-bSgZKkzb`。本记录与[上一轮设计审查](../reviews/2026-10-11-containerized-campaign-design-review.md) 分开保留。

## 首轮结论

`CHANGES_REQUIRED`：无 P0；一项 P1、两组 P2。冻结文件为 `design-review-round1.md`，SHA256：

`c9853ed981abd8b3ce1f05ee49518d4215f1e29f675c1cf6ac83d03cbaa7d9e3`。

| 级别 | 发现与源码依据 | 修订处理 |
| --- | --- | --- |
| P1 | 当前 `src/so101_teleop/so101_teleop/unified/admission.py:473–499` 要求资格状态为 `PASSED`，`src/so101_demo_py/src/act/parallel_qualification_verifier.py:48–51` 要求同一文件为 `QUALIFIED`；admission 的当前 root 限制还会影响新 campaign 对独立资格的引用。只补 verifier 无法打通正式启动。 | 设计差异表及 §8 同步规定报告 writer/schema、admission、verifier 和调用方迁移；八 Worker 报告只采用 `ACT_PARALLEL_COLLECTION_QUALIFICATION`、`schema_version=1` 和通过终态 `QUALIFIED`。资格和正式 campaign 保留独立 subroot；在同一登记 durable root 内只读引用原证据，核对路径、完整 hash 链与受控身份。新增真实正式启动正例与旧 14 项报告、终态冲突、篡改、路径逃逸和身份不符负例。运营参数不作隐含模型资格门禁。 |
| P2 | 首轮只规定 RGB8/shape，未固定 staging 的文件字节格式。当前 `runtime/parallel_perception_runtime.py:289–330` 使用完整 `.npy` 文件 hash 和同 bytes 解码。 | §3.3 固定唯一无 pickle、C-contiguous、`uint8 H×W×3 .npy`，完整文件大小/hash、同 bytes 解码、`0400`、输入/header/shape 限制；不做多格式探测或兼容 reader。 |
| P2 | 首轮尚未闭合 CUDA 子进程初始化、staging 计时起点、重复连接拒绝、查询与接纳计数等 IPC 边界。 | §3.1–3.4 明确 `spawn`、父进程不初始化 CUDA；deadline 从 staging 写入前开始；重复连接返回 `INPUT_INVALID/DUPLICATE_REQUEST`，不改原请求；只读查询不增加 `accepted_total`，同一服务 generation 内该计数单调。 |

审查确认以下设计边界与源码相符：mask/RLE 输出和 Worker 本地去重/追踪/R6 定位；原始 bag → Teacher 结束 → 离线 episode → 独立 QC；Teacher 与 ACT 数据状态分离；业务命名与当前各业务唯一 schema。历史文件名保留不等于引入旧接口。

## 复审对象

冻结文件：`design-review-round2.md`，SHA256：

`9f1d1fea41e738822e4acd0f0a2e8c0ce0d98a45714741be023c1d4ea519df4e`。

除上表修订外，§8 补齐了独立 40 场景与功能/正式数据划分不重叠、资格过程零基础设施失败/重试/crash-resume，以及资格开始前冻结实测单位、窗口和阈值的要求。这不是容量预测，也不要求按实例数逐档测试。

复审结论：`PASS`（设计静态审查）。Astra 完整反读 250 行冻结稿，首尾 hash 均一致；首轮 P1/P2 已闭合，未发现新的 P0、P1 或必须继续修改的 P2，可以据此编写实施计划。

| 复审项 | Astra 反读结论 |
| --- | --- |
| 报告与正式 admission 的状态冲突 | 第 43、246 行已要求完整调用链迁移和唯一 `QUALIFIED` 终态，不保留双状态兼容。 |
| 独立资格证据引用 | 第 248 行已规定受限只读引用、完整证据 hash、原资格 run 身份及正式 admission 正负例，未放宽其他 receipt/case 边界。 |
| 9+5 与独立 W8 分离 | 第 239、244–246 行已分别要求抓放 live 与 40 场景两波资格，不把当前 verifier 当成完成证据。 |
| staging 与 IPC 边界 | 第 127、133、141、162、166、176 行已闭合单一序列化、CUDA 启动、完整计时、重复响应和恢复计数。 |
| W8 实测合同 | 第 241 行符合独立场景、零基础设施失败/重试/crash-resume、资格前冻结测量门槛和不预估容量的用户边界。 |

复审后设计文档只更新了第 9 行的审查状态及链接，业务合同与冻结稿相同。没有把 `PASS` 改写成用户实施批准或 runtime qualification。

## 范围与证据保留

本次只修改设计和审查记录，不执行实施计划，不启动 `dst`，不做 runtime qualification，不 commit/push。设计审查通过不代表校准、抓放 live、八 Worker 资格或训练已经完成。后续须先形成实施计划并取得用户批准。

保留本证据根的 manifest 和两轮冻结审查文件；源码 snapshot 经反读后列为删除候选，未删除。没有新增归档，也没有移动或删除 ai-station 上的真实证据。
