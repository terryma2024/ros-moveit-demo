---
name: so101-dev
description: Use when diagnosing, modifying, testing, or visually validating SO-101 pick-place on ai-station in robot_demo_001, especially ROS 2 Jazzy, Gazebo Harmonic, MoveIt 2, stale installed binaries, controller or TF failures, Planning Scene and Gazebo attachment divergence, runtime logs, tmux, CUA, or screenshots.
---

# SO-101 开发调试闭环

## 核心原则

一次只验证一个最小假设。日志里的 `DONE`、MoveIt 的 `SUCCESS`、action 返回成功和 GUI 里“看起来动了”都是不同证据，任何一个都不能替代其余层。

默认范围是 ai-station 上的 SO-101 仿真。若目标包含真实机械臂动作，在得到用户明确授权并建立急停、限速、限位和净空门控前，停在 plan-only。

先判定 coding agent 实际运行在哪台主机。若任务已发送到 ai-station 的 tmux/Codex，交接指令必须明确写出“你当前直接运行在 ai-station 上”，后续命令在本机执行，不得再次 `ssh ai-station`。具体判定与交接模板见 [`references/ai-station-access.md`](references/ai-station-access.md)。

## 开始前必须做

1. 读取仓库根 `AGENTS.md` 和 `moveit-demo/AGENTS.md`。
2. 读取以下 reference；只跳过与本次任务明确无关的文件：
   - 远程命令、tmux、GUI、截图或 CUA：[`references/ai-station-access.md`](references/ai-station-access.md)
   - 查找源码、launch、安装产物或运行边界：[`references/so101-system-map.md`](references/so101-system-map.md)
   - 定位根因和区分证据层：[`references/debug-evidence.md`](references/debug-evidence.md)
   - 修改代码、运行测试或声明完成：[`references/test-and-acceptance.md`](references/test-and-acceptance.md)
   - 多轮实验、生命周期比较、上下文压缩或 agent 交接：[`references/experiment-ledger.md`](references/experiment-ledger.md)
3. 从当前 orchestrator 和 ai-station 分别记录 `pwd`、commit、branch、submodule 和 `git status --short`；已经位于 ai-station 的 coding agent 直接在本机取证，不再 SSH 自身。已有改动均视为用户工作，不能覆盖、清理或夹带。
4. 检查现有进程、ROS graph 和 `codex-cua` tmux 状态。不得在不知情时启动第二套 `/move_group`、RViz 或 Gazebo。
5. 给本轮建立一个 `/tmp/so101-debug-<时间或短ID>/` 证据目录；不要把日志、截图或构建产物写进源码目录。

## 长程任务实验账本

预计需要两轮以上实验、需要比较环境生命周期或连续成功、任务可能跨上下文压缩/goal 暂停/agent 交接，或用户要求避免重复路线时，必须在当前实现 worktree 建立并持续更新 `docs/experiments/<task-slug>-experiment-ledger.md`。详细状态机、字段和模板见 [`references/experiment-ledger.md`](references/experiment-ledger.md)。

恢复任务时必须先读账本，复述最后可信 checkpoint、已确认结论、已证伪路线和下一条实验引用；完成前不得启动 stack、调参、操作 GUI 或清理进程。原始日志和截图继续放在唯一的 `/tmp` 证据根目录，不能让 `/tmp` 或聊天成为长期结论的唯一载体。

每条实验记录必须显式写出 source commit、install overlay、runtime executable 或 package prefix、`ROS_DOMAIN_ID` 和 `GZ_PARTITION`；不得只写笼统的 “provenance 已确认”。每轮结束、上下文压缩、暂停或交接前，必须先更新账本 checkpoint，再发送聊天或 tmux 摘要。

## 闭环

每一轮只走下面六步，完成后才开始下一轮。

1. **定义症状**：写清操作、期望、实际结果、首次失败边界和运行模式 `dry_run | plan_only | execute`。
2. **最小复现**：复用一套已知进程；必要时用 `stop_after`、单状态 CLI 或单测缩短路径。保存命令、退出码、时间戳和拥有该日志的进程。
3. **分层取证**：至少检查源码/安装产物、ROS/MoveIt、控制器与反馈、Gazebo 物理、Planning Scene、视觉六层中的相关层。把结论标为 `OBSERVED`、`INFERRED` 或 `HYPOTHESIS`。
4. **A/B 隔离**：只改变一个变量。长程任务必须先写 `PLANNED` 实验条目，冻结历史引用、唯一变量、`REUSE_STACK | RESET_WORLD | FULL_RESTART` 生命周期和判据；结束后落为 `VALID` 或 `INVALID`。优先在第一个出现分叉的边界修复，不在下游用补偿逻辑掩盖上游错误。
5. **最小修改**：先建立会失败的自动化回归测试；如果缺陷只能在 live runtime 重现，保留失败命令和前后状态断言，再补最接近所属边界的测试。只修改根因所属层。
6. **重新验证**：重新构建、重新 source、确认执行的是新安装产物；先跑定向测试，再跑包级测试，最后跑一次真实复现并做新的 GUI 截图。

一轮结束时输出：

| 字段 | 必填内容 |
|---|---|
| 症状边界 | 首个错误状态、topic、action、scene 或画面 |
| 当前判断 | `OBSERVED / INFERRED / HYPOTHESIS` |
| 唯一变量 | 本轮改变了什么 |
| 修改 | 文件和目的，或“未修改” |
| 自动验证 | 命令、退出码、关键断言 |
| 运行时验证 | Gazebo、MoveIt、controller、joint/TF 的相关前后事实 |
| 视觉验证 | 新截图路径和画面中实际确认的变化 |
| 下一步 | 一个最小假设，或明确完成 |

## 快速分流

| 症状 | 第一检查点 |
|---|---|
| 修改 C++ 后行为不变 | `ros2 run` 使用的 install 前缀、构建时间、重新 source 的 overlay |
| `No kinematics plugins defined` | 警告所属进程，以及 `/move_group` 的 dotted leaf parameter |
| 状态机到 `DONE` 但物体未搬运 | Gazebo attach 状态与 Coke 6D pose；不要先改 transition table |
| MoveIt 规划成功但机械臂未动 | 是否调用 execute、action 结果、`/joint_states` 与 TF 前后差值 |
| Gazebo 已 attach、RViz 仍是 world object | MoveIt world/attached collision membership 与 attached link |
| 日志互相矛盾 | 是否同时存在重复 `/move_group`、RViz、Gazebo 或旧 tmux 进程 |
| GUI 与日志不一致 | 新截图、正确窗口/会话、画面时间与本轮日志时间是否一致 |

## 不可省略的证据规则

- 从运行中进程、安装产物和 source tree 三者确认代码 provenance；README 或 IDE 索引不证明运行版本。
- ROS 2 嵌套 YAML 参数按 dotted leaf 查询。顶层 `Parameter not set` 不足以证明配置缺失。
- 以实际产生日志的进程为准，不能只凭 logger 名称判断是 `/move_group` 还是客户端。
- `plan()` 只产生候选轨迹；不证明执行、关节变化、TCP 变化或 Gazebo 物理变化。
- Gazebo 是物体 pose/物理 attachment 的事实源；MoveIt 是 world/attached collision object 的事实源。两者必须独立通过。
- 高频 topic 只取带时间边界的一次性前后样本。零运动是现象，不自动等于 controller 根因。
- GUI 操作必须遵守 `snapshot -> action -> fresh snapshot`；不能复用旧 `element_index`。
- 根因必须有可区分竞争假设的 A/B 证据。证据不足时写“未确认”，不得写“已定位”。

## 完成条件

只有同时满足以下条件才可宣布修复完成：

- 原始复现先失败、修改后通过；命令和退出码已保存。
- 新增或更新的回归测试经历过 RED -> GREEN，包级测试无新增失败。
- ai-station 已重新构建并 source 正确 overlay，运行产物 provenance 已确认。
- 状态机、MoveIt、controller/joint/TF、Gazebo 和 Planning Scene 中所有与缺陷相关的层彼此一致。
- 使用本轮新截图确认可见结果；截图不能只证明窗口存在。
- 没有覆盖用户既有改动，没有遗留重复 stack 或失控后台进程。
- 未通过的层、剩余风险和下一条验证命令已明确列出。
- 长程任务的实验结论和最新 checkpoint 已写入账本；不同生命周期没有混算，无效运行没有计入成功率或连续成功。

## 常见错误

- 在无法收敛时继续扩大 `rg` 范围。改为写出一个竞争假设并运行能区分它们的命令。
- 看到成功日志就直接改物理或视觉层。先定位成功只覆盖了哪一层。
- 修改 source 后直接 `ros2 run`。必须 build、source，再验证 package prefix/产物。
- 用 GUI 截图代替状态查询，或用状态查询代替 GUI 验收。两者都要有。
- 为获得“干净环境”清理用户 worktree。用独立 `/tmp` 证据目录和最小补丁隔离。
- 只在聊天、tmux 或 `/tmp` 中保存长程实验结论。先更新持久账本和 checkpoint，再交接或继续下一轮。
