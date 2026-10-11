# SO-101 Teacher 执行与 ACT 数据验证分离修订

日期：2026-10-05
状态：用户已确认两个原则，并授权 ai-station 的现有 Claude 修订执行计划、清理旧实现和测试、按新计划执行。本文经过编写者 inline self review；未宣称代码、集成或运行验收通过。

## 1. 适用范围与优先级

本修订适用于完整 ACT 方案中的 MoveIt Teacher 示教执行与数据采集，也适用于当前非 Head 首条采集闭环。它不是诊断模式专用的宽松规则。发生冲突时，本文优先于下列文档及其执行计划中的 Teacher/Recorder/QC 耦合、过程质量成功条件和数据故障停机条款：

- `2026-09-10-so101-act-head-wrist-rgb-design.md`
- `2026-09-24-so101-act-task8-live-formal-collection-design.md`
- `2026-09-28-so101-act-task8-artifact-preparation-design.md`
- `2026-09-29-so101-act-task8-measurement-protocol-design.md`
- `2026-09-30-so101-act-containerized-campaign-design.md`
- `2026-09-30-so101-act-nonhead-first-episode-design.md`
- `2026-10-01-so101-act-endpoint-pose-acceptance-design.md`

Head Search、ACT 模型闭环控制策略和算法不在本次实施范围。ACT rollout 的停止规则不从 Teacher 的旁路采集规则自动推导。W2 后直接独立 40 场景 exact-W8、不跑 W4/W6、正式/诊断用途隔离、CUDA/no CPU fallback 和 MuJoCo-only 保持不变；本次不启动并行资格、训练、第二套 stack 或真实硬件。

## 2. 两个原则

Teacher 独立负责执行、运动安全和任务结果。Recorder、ACT 同步器、数据 QC 和导出筛选是旁路消费者，不是运动许可的签发者。关闭、缺失或故障的采集侧不能改变 Teacher 的规划、轨迹、动作顺序、重试策略或执行结果。

Teacher 的任务成功以同一杯子的起点和最终 Pose 为主要判据：杯子实际从配置的 start 区域转移到 end 区域，最终位置和高度满足容差，杯轴保持竖直、没有倾倒。过程物理检查尽量减少；抓稳、抬升高度、持续双侧接触、阶段间的物理质量窗口不再独立决定任务成功。

## 3. 组件权限和数据流

Teacher 使用自己执行所需的 MuJoCo/ROS 状态、MoveIt 规划、controller action 和必要安全输入。其控制通道、控制租约和停止确认独立于采集结果租约、Recorder 状态、数据 seal 和 Coordinator 提交。复用已有控制器和必要的控制所有权机制，不因分离而绕过关节限制或允许多个运动所有者。

Teacher/仿真只向采集侧提供观测、已接受的 controller reference 和执行事件。采集侧没有 Teacher command、cancel、revoke、pause、reset 或自动业务重试权限。独立 QC 只读取已保留的文件，不连接运动控制入口。数据 finalization 超时、提交失败或采集 lease 过期不能取消仍在其独立执行期限内的 Teacher。

CPU/GPU/RAM/磁盘资源在启动入口按现有规则绑定一次；不能在内部组件重新申请资源。Teacher 的输入校验不再以 RGB 齐备、Recorder READY、首行成功、数据 hash/seal 或采集队列排空为运动 prerequisite。真正的执行安全配置缺失仍拒绝运动；不能把旧质量报告改名为安全报告以保留耦合。

## 4. Teacher 的最小检查和结果判定

### 4.1 必须保留的执行保护

保留有效机器人/场景身份、合法控制所有权、关节位置/速度/加速度限制、必要的规划碰撞约束、明确危险碰撞/接触力保护、controller 失效和必要状态长期不可用的停止机制。保留用户停止、独立执行 deadline、停止后的反馈确认；控制消息不得跨 session/reset 使用。

Planning Scene attachment 仍只是规划 shadow，不得通过 MuJoCo 物体瞬移、人工 physics attachment 或隐藏 reset 制造成功。释放与错误处理保留真正的安全要求；无支撑且被持有的杯子出错时，不通过自动开爪来清理。必要的执行保护可以停止 Teacher，但必须记录明确的安全/控制原因，而不是数据 QC 原因。

逐项审查双侧接触丢失、提前碰桌、夹取前杯子移动、微抬升验证、释放接触和阶段稳定窗口：一般过程质量项改为 audit-only，不再取消轨迹或阻止 `DONE`。只有能够说明具体危险、独立于采集也需要的条件才归入执行保护。不能把所有旧过程断言都标为“安全”保留下来，也不能把所有接触保护一并删除。计划须列出每项的去留、消费者和测试。

### 4.2 起点与终点

Teacher 在 reset 完成后、本次首条 arm/gripper 运动前独立读取起点 Pose，不等待采集启动、相机齐备、首行或 phase-channel 的数据绑定。终点在获准动作序列结束、释放动作完成并确认 controller 停止后读取；可使用配置的短暂落稳等待，默认取 `0.5 s` 经验值，允许非负有限值覆盖。它不是速度、接触或精确连续采样门禁；可选的多帧终态观察只留诊断，不新增过程质量成功条件。

起点和终点均来自实际执行世界、同一个 `object_id/body_name`、`world` frame 和本次 session/reset。目标在运行前冻结，不从实际终点反推目标。不择优选择历史帧；缺少有效终态给出 `UNCONFIRMED`，不能因证据缺失报成功。Teacher 的必要状态新鲜度按执行策略定义，不能直接继承 ACT 的 10 Hz/100 ms 数据合同，也不能要求两个不同时间的快照数值完全相同。

沿用五个可配置经验容差：初始位置 `0.010 m`、初始轴 `0.15 rad`、最终 XY `0.020 m`、最终 Z `0.010 m`、最终轴 `0.15 rad`。最终杯轴是 body 局部 `+Z` 旋转到 world 后与 world `+Z` 的夹角；终点目标姿态也必须符合直立要求，不能通过冻结倾倒目标取得 PASS。不限制绕杯轴的 yaw，四元数须有效。

使用版本化的新结果规则和配置，不能在旧 closed schema 偷加字段并继续声称 `endpoint_pose_v1`。现有位置/角度字段可复用，新增落稳参数由计划定义显式版本。配置在 episode/attempt 开始前冻结，记录完整生效值和 hash，不在运行后调阈值重判同一次结果。

start/end recipe 必须定义实际搬运任务，不能把起终目标配置为重合，然后宣称杯子被转移；不要求另一个经测量批准的最小位移阈值。端点口径不证明全程夹持或标准抓取方式，报告如实写明“杯子转移与最终直立结果通过”。

## 5. ACT 采集故障只影响数据

缺帧、acquisition 重用、同步/因果标签失败、raw chunk 缺口、截断、队列溢出、落盘错误、seal/QC/提交失败，只能影响本次数据状态。可继续保留诊断或关闭失败的采集侧；不得请求 Teacher stop/revoke/pause/reset，不能拖住 Teacher 退出。损坏或不完整的数据不得进入训练集。

Teacher 自身需要的状态源故障另走执行错误路径。相同消息可以被两个组件读取，但采集侧的缓冲、raw history 完整性或 QC 状态不能作为 Teacher 状态健康的代理。明确的物理危险由 Teacher 自己判断；采集侧保留记录，不以“QC 发现 hazard”取得运动控制权。

训练数据合同保持不变：实际 head/wrist RGB、8D state、6D accepted controller reference、10 Hz sim-time 网格和 `t+0.1s` 标签、身份与来源绑定、无损 PNG/JSONL、hash/fsync/seal、独立回读 QC、实际 Coordinator journal/index 和用途门禁。不能以分离为理由降低数据标准、复制旧帧、编造 reference 或把诊断数据升级为正式数据。

分别报告 `teacher_execution_status`、`teacher_task_result` 和 `act_data_status`，新 schema 及与旧记录的兼容策略由计划显式定义。Teacher 成功而数据无效时，任务仍成功，数据拒绝导出；Teacher 失败但数据完整时保留失败记录，不自动进入成功示教集。未知版本拒绝，不隐式沿用旧耦合结果。

Teacher 成功率的分母是已开始的合法 Teacher attempts，不能只统计 QC PASS 的子集；另报 ACT 数据合格率和可提交数量。不混算历史过程门禁口径与新端点口径。

## 6. 旁路的资源与时延隔离

建议使用独立 Recorder 进程，执行结束后独立进程 QC。Teacher 的 ROS 回调只承担执行必需处理和有界轻量事件交接，不做 PNG 编码、重型 history join/hash、fsync 或 QC。旁路使用有界非阻塞入口和独立锁；Teacher 不等待 Recorder ACK，采集队列不反压控制线程。无法保留全部数据就标记数据无效，不无限扩容，不悄悄降采样。

磁盘空间、水位、RGB continuity 和纯数据 RTF 指标不得作为运行中 Teacher 停止原因。采集资源不足可拒绝/停止采集及后续采集调度，已运行的 Teacher 按自身执行契约收尾。若共享宿主资源确实导致控制失效，Teacher 自身的健康保护仍生效；不能许诺共享机器上绝对零资源影响。

计划在测试前冻结可验收的延迟、负载和成功率比较口径，比较相同 Teacher/config/scene 下采集关闭、正常采集和故障采集。启动 admission 的资源规则不变，不能降低阈值或绕过 GPU 所有权。资源隔离应在现有单 stack 内完成，本任务不新增容器体系。

## 7. 清理旧实现与测试

先列旧条件→新归属→代码消费者→测试→删除/替代理由的清单。重点审查 `PHYSICS_COMMIT_VERSION_CHANGED`、`TEACHER_PHYSICS_SOURCE_REFUSED`、`ENDPOINT_INITIAL_CAPTURE_INVALID`、phase/Recorder bind、data hazard dispatcher、数据 lease/finalization 触发控制撤销以及采集队列 hold/resume。

正常追加 chunk 改变全局 version 不再独立构成 Teacher 停机理由。必要的 Teacher 提交检查应针对具体控制权限、身份、选中状态的执行有效性和真实安全条件。数据一致性与完整性在旁路处理。不能用增加重试次数、阻塞 ROS 接收或扩大时窗来维持旧耦合方案。

删除不再有消费者的适配层、RPC、配置项、分支和状态机依赖；保留仍供真正执行保护或严格数据 QC 使用的共享功能。不保留默认启用的“兼容旧耦合”开关。修改/删除测试须说明它验证的旧合同为何被替代，并新增相应新合同测试；不能批量 skip/xfail、删失败用例来制造 GREEN。原有脏工作、失败日志、冻结产物与历史账本保持可追溯，不回滚覆盖、不删除证据。

## 8. 实施顺序与验收

Claude 先修改当前执行计划及相关设计链接，列出旧 gate 迁移、清理范围、命令入口、输入、预期产物/退出码和证据。用户已授权该范围内的计划修订和执行；计划完成并 self review 后继续，不再把已批准的两个原则当作待决问题。遇到范围外的安全授权或资源缺口才请求最小决策。

执行分段：

1. 定向 RED/GREEN 验证 Teacher 无采集独立执行、采集故障无反向控制、端点判据及保留的执行保护，完成旧代码和旧测试清理。
2. 代码/config/policy 冻结后在明确集成边界跑相关完整普通 xdist/package gate，重建/source，核验实际安装产物和进程 provenance；不频繁全量跑测试，不收集 benchmark suite。
3. 用现有正式程序入口、一套 MuJoCo headless stack 和固定场景串行实际运行：Teacher 关闭采集的真实抓放；正常采集的真实抓放→Recorder→seal→独立回读 QC→Coordinator commit/index；隔离的采集故障注入。不能只用 mock/fixture 宣称分离完成。
4. 实际故障注入至少覆盖 Recorder 不可用/迟到、队列积压/溢出、采集来源缺口或过期，以及隔离输出目录中的写入失败。记录 Teacher 轨迹/结果、控制事件、实际 start/end Pose、数据错误、退出码和 owned process cleanup；证明故障不产生数据来源的 cancel/revoke/pause，数据仍拒绝导出。不能填满真实 evidence 磁盘、污染原成功文件或人为制造物理危险。
5. 用正反例验证终点偏移、倾倒、终态不可用、yaw 不敏感和坏配置。证实过程诊断失败但最终结果合法的任务不会被旧质量 gate 阻断；真正的执行安全失败仍保持正确停止。

实际命令由执行者在更新后的计划中从当前 CLI/launch 发现，写出精确 executable、输入、预期输出、rc 和日志位置；新入口必须成为仓库内正式程序。Teacher 成功且数据故障的组合允许整体采集命令返回非零，但报告必须保留 Teacher 成功，不能把非零解释为机械臂任务失败。

当前单 episode 里程碑仍要求一条真实抓放、端点结果通过、完整无损采集、新进程 QC PASS、实际提交和诊断用途拒绝导出；故障隔离验证不替代这条成功链，也不自动证明正式并行资格。头部功能与正式配额另按原计划完成。

## 9. 执行位置、证据和交接

执行者沿用 ai-station 的 tmux `claude`，worktree `/home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a`，branch `codex/so101-act-data-0917a`。Claude 直接在 ai-station 操作，不自我 SSH。不新建第二执行器/worktree/stack，不改 antzb 的当前任务。

唯一 durable evidence root 继续为 `/data/work/so101-evidence/act-data/20260924-fbc25063-resume`，账本继续为 `docs/experiments/so101-act-data-experiment-ledger.md`。所有 source/config/policy/schema 变化使旧 bundle/live/QUALIFIED 对新身份失效，需新冻结和新 run 子目录；旧证据不重新贴标签、不移动、不删除。Claude 是远端账本与实现的唯一协调写入者。

ai-station pytest/colcon 的 fsync-heavy fixtures 使用该 root 下全新 NVMe scratch，核验精确 Python 的 TMPDIR/TMP/TEMP 与 `tempfile.gettempdir()`；保留 fsync，记录 elapsed、JUnit、skip 和实际 rc。pipelines 使用 pipefail。scratch 只列删除候选，未获授权不删除。

收到交接后，Claude 在新增任务执行前更新可见 task list，固定任务项内容、当前边界和完成条件；此后每个 turn 结束只更新 status，不改写/重命名/合并/拆分/删除任务项。先保存现有工作并协调已在运行的旧子任务安全收尾，再转入新计划，不与旧子任务并行修改相同文件。保留原 goal；若处于非用户主动暂停，在工具支持的用户侧入口按本次授权继续，不反复调用被禁止的自恢复工具。

本次只交付设计修订和执行交接，未获 commit/push、merge、硬件动作或删除证据的授权。完成交付列出 retained、archived 和 deletion candidates，并分开报告 Teacher 结果、数据 QC、集成测试和运行验收。
