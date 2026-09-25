---
name: so101-dev
description: Use when diagnosing, modifying, testing, or visually validating SO-101 pick-place in robot_demo_001, on ai-station or Apple Silicon macOS, covering ROS 2 Jazzy, Gazebo Harmonic, the MuJoCo task station, MoveIt 2, ros2_control, teleop and Web Expert Validation services, runtime logs, tmux, CUA and screenshots. Also use for SIP, DYLD or @rpath test-collection failures, stale installed binaries, controller or TF failures, and Planning Scene versus Gazebo attachment divergence.
---

# SO-101 开发调试闭环

## 核心原则

一次只验证一个最小假设。日志里的 `DONE`、MoveIt 的 `SUCCESS`、action 返回成功和 GUI 里“看起来动了”是四种独立证据，任何一个都不能替代其余层。

默认范围是仿真：ai-station 上的 Gazebo/MoveIt，或 macOS 上的 MuJoCo task station。目标包含真实机械臂动作时，在用户明确授权并建立急停、限速、限位和净空门控之前停在 plan-only。

先判定 coding agent 实际运行在哪台主机。已在 ai-station 上的 agent 直接在本机取证，不得再次 `ssh ai-station`；别名解析失败不能反推主机身份。

## 开始前必须做

1. 读取仓库根 `AGENTS.md`。
2. 判定执行主机，按 [`ai-station-access.md`](references/ai-station-access.md) 的交接模板声明执行位置。
3. 按路由表读取 reference，只跳过与本次任务明确无关的文件。
4. 记录 `pwd`、commit、branch、submodule 和 `git status --short`；orchestrator 与 ai-station 分别记录，已在远端的 agent 本机取证。已有改动都算用户工作。
5. 检查现有进程、ROS graph 和 `codex-cua` tmux 状态，不得在不知情时启动第二套 `/move_group`、RViz、Gazebo 或 MuJoCo stack。
6. 建立并登记本 task 唯一的 evidence root，见下节。日志、截图和构建产物不写进源码目录。

## Reference 路由

| 任务涉及 | 读取 |
|---|---|
| 远程命令、tmux/Codex 投递、GUI、截图、CUA | [`ai-station-access.md`](references/ai-station-access.md) |
| 源码归属、launch、安装产物、仓库与子模块边界 | [`so101-system-map.md`](references/so101-system-map.md) |
| 根因定位、证据分层、竞争假设、症状分流 | [`debug-evidence.md`](references/debug-evidence.md) |
| 改代码、构建、测试、验收、声明完成 | [`test-and-acceptance.md`](references/test-and-acceptance.md) |
| 在 macOS 上运行或测试 SO-101，含正常 package test | [`macos-runtime-environment.md`](references/macos-runtime-environment.md) |
| 多轮实验、生命周期比较、上下文压缩、agent 交接 | [`experiment-ledger.md`](references/experiment-ledger.md) |
| 安装 Python 依赖、uv 索引、镜像绕过代理 | [`python-dependency-install.md`](references/python-dependency-install.md) |
| 统一 Web Expert Validation 服务的启动、检查、清理 | [`unified-teleop-service.md`](references/unified-teleop-service.md) |

`src/so101_gazebo_demo_cpp/web` 统一用 Bun 装依赖、跑 scripts 和一次性 CLI，锁文件是 `bun.lock`，不用 npm/npx，也不引入 `package-lock.json`。每个新 shell 先记录 `command -v bun` 和 `bun --version`；项目预构建、本地测试和 shadcn CLI 也走 Bun，不要回退系统 Node 18。

## 证据根

每个 task 只有一个 evidence root：

| 证据类型 | 唯一路径 |
|---|---|
| 普通低速日志、截图、检查、临时构建证据 | `/tmp/so101-debug-<task-id>/` |
| 高频无损或必须持久保留 | ai-station `/data/work/so101-evidence/<task-family>/<run-id>/`；macOS `/opt/data/work/so101-evidence/<task-family>/<run-id>/` |
| 已被替代但仍需审计 | ai-station `/data/work/so101-evidence/archived/<task-family>/<run-id>/`；macOS `/opt/data/work/so101-evidence/archived/<task-family>/<run-id>/` |

禁止直接创建 `/data/work/so101-debug-*` 或 `/opt/data/work/so101-debug-*`，也不得把一个 task 分散到多个根目录。

登记方式看任务长度。**短任务**（单轮复现、不跨上下文压缩、不比较生命周期）在 root 内写一份 `manifest.md`，记下 `task_id`、`evidence_root`、scope、owner 和 retention，不需要 `docs/experiments/` 账本。**长程任务**另外在实现 worktree 建 `docs/experiments/<task-slug>-experiment-ledger.md`，并在账本头部登记同一个 root。

完成时分别报告 retained、archived 和可删除候选。“可删除候选”只是分类，未获用户明确授权不得删除任何证据。迁移或归档前后核验相对路径、SHA256、大小和数量，更新 tracked 绝对路径，但不改写历史结论。ai-station 的持久布局说明在 `/data/work/so101-evidence/README.md`。

## 闭环

每一轮只走下面六步，走完再开始下一轮。

1. **定义症状**：操作、期望、实际结果、首次失败边界，以及运行模式 `dry_run | plan_only | execute`。
2. **最小复现**：复用一套已知进程，必要时用 `stop_after`、单状态 CLI 或单测缩短路径。保存命令、退出码、时间戳和拥有该日志的进程。
3. **分层取证**：检查源码/安装产物、ROS/MoveIt、控制器与反馈、Gazebo 或 MuJoCo 物理、Planning Scene、视觉六层中相关的层。结论标为 `OBSERVED`、`INFERRED` 或 `HYPOTHESIS`。
4. **A/B 隔离**：只改一个变量。长程任务先写 `PLANNED` 条目，冻结历史引用、唯一变量、`REUSE_STACK | RESET_WORLD | FULL_RESTART` 生命周期和判据，结束后落为 `VALID` 或 `INVALID`。优先修第一个出现分叉的边界，不在下游用补偿逻辑掩盖上游错误。
5. **最小修改**：先建立会失败的自动化回归测试。缺陷只能 live 重现时，保留失败命令和前后状态断言，再补最接近所属边界的测试。只改根因所在的层。
6. **重新验证**：重新构建、重新 source，确认跑的是新安装产物；先定向测试，再包级测试，最后跑一次真实复现。只有当本轮改动有可见结果时才再取新的 GUI 截图。

一轮结束时输出：

| 字段 | 必填内容 |
|---|---|
| 症状边界 | 首个错误状态、topic、action、scene 或画面 |
| 当前判断 | `OBSERVED / INFERRED / HYPOTHESIS` |
| 唯一变量 | 本轮改变了什么 |
| 修改 | 文件和目的，或“未修改” |
| 自动验证 | 命令、退出码、关键断言 |
| 运行时验证 | Gazebo/MuJoCo、MoveIt、controller、joint/TF 的相关前后事实 |
| 视觉验证 | 有可见结果时的新截图路径，以及画面里实际确认的变化；只有纯 headless 或 Web 后端的改动才写 N/A 和原因，Web 前端等有可见输出的改动仍要新截图 |
| 下一步 | 一个最小假设，或明确完成 |

## 不可省略的证据规则

- code provenance 从运行中的进程、安装产物和 source tree 三处确认；README 和 IDE 索引不证明运行版本。
- ROS 2 嵌套 YAML 参数按 dotted leaf 查询，顶层 `Parameter not set` 不足以证明配置缺失。
- 以实际产生日志的进程为准，不能只凭 logger 名称判断是 `/move_group` 还是客户端。
- `plan()` 只产生候选轨迹，不证明执行、关节变化、TCP 变化或物理变化。
- Gazebo 是物体 pose 和物理 attachment 的事实源，MoveIt 是 world/attached collision object 的事实源，两者独立通过。
- 高频 topic 只取带时间边界的一次性前后样本。零运动是现象，不自动等于 controller 根因。
- GUI 操作遵守 `snapshot -> action -> fresh snapshot`，不复用旧 `element_index`。
- 证据不足就写“未确认”，不写“已定位”；根因必须能区分竞争假设。

## 强制门禁

- **Python 全量测试并行门禁**：每个模块的完整普通 pytest 范围都必须用 `pytest-xdist`，worker 数为 `min(8, 逻辑 CPU 数)`，并记录 CPU 数、worker 数、实际范围、退出码、JUnit 和跳过数。定向或串行运行只用于定位，不算全量通过；改用单进程、串行分组或缩小收集范围同样不算通过。ai-station 上还要把 `TMPDIR`/`TMP`/`TEMP` 指向 `/data` NVMe 下新建的 scratch 目录。
- **测试范围**：`so101_demo_py` 的普通门禁只收集 `src/so101_demo_py/test/`，不得收集 `src/so101_demo_py/benchmark_test/`。这条路径只属于 `so101_demo_py`，其他模块按各自 package 声明的测试范围收集，不要用它代表全部模块。`benchmark_test/` 只在改动 benchmark 实现、配置、adapter、报告或测试，或选择、比较感知模型时显式运行。

两条门禁的完整契约、命令和参数见 [`test-and-acceptance.md`](references/test-and-acceptance.md)。

## 完成条件

只有同时满足以下条件才宣布修复完成：

- 原始复现先失败、修改后通过，命令和退出码已保存。
- 新增或更新的回归测试经历过 RED -> GREEN，包级测试无新增失败。
- 跑过的平台已重新构建并 source 正确 overlay，运行产物 provenance 已确认。
- 状态机、MoveIt、controller/joint/TF、Gazebo 或 MuJoCo、Planning Scene 中与缺陷相关的层彼此一致。
- 有可见结果时用本轮新截图确认；截图不能只证明窗口存在。
- 没有覆盖用户既有改动，没有遗留重复 stack 或失控后台进程。
- 未通过的层、剩余风险和下一条验证命令已明确列出。
- 长程任务的实验结论和最新 checkpoint 已写入账本，不同生命周期没有混算，无效运行没有计入成功率或连续成功。

## 常见错误

- 收敛不了就继续扩大 `rg` 范围。改为写出一个竞争假设，跑能区分它们的命令。
- 看到成功日志就直接改物理或视觉层。先定位这个成功只覆盖了哪一层。
- 用 GUI 截图代替状态查询，或用状态查询代替 GUI 验收。两者都要有。
- 为了“干净环境”清理用户 worktree。用本 task 登记的单一 evidence root 和最小补丁隔离。
- 只在聊天、tmux 或 `/tmp` 里留长程实验结论。先更新持久账本和 checkpoint，再交接。

## Physical-outcome 边界

normal forward workflow 以 Gazebo physics 作为 cup 运动的唯一事实源。MoveIt attachment 只是从最新 Gazebo pose 派生的 collision-planning shadow，normal forward path 从不调用 `ATTACH_GAZEBO` 或 `DETACH_GAZEBO`；`reset` 为建立 canonical state 做的防御性 detach 属于独立事务。

当前释放顺序是 `DESCEND_TO_PLACE -> OPEN_GRIPPER -> RETREAT -> DETACH_MOVEIT -> WAIT_RELEASE_SETTLE -> VALIDATE_FINAL_PLACEMENT -> SYNC_WORLD_OBJECT -> DONE`。`WAIT_RELEASE_SETTLE` 和 `VALIDATE_FINAL_PLACEMENT` 只消费当前 non-resumable release epoch，不复用 pre-release 样本。

注意顺序差异。目标安全要求是：物理 `OPEN_GRIPPER` 之前必须 `DETACH_MOVEIT`。当前实现尚未满足这条要求，源码中的顺序把 shadow detach 排在 `OPEN_GRIPPER` 和 `RETREAT` 之后。在独立验证通过或用户明确修改契约之前，不得宣称“开夹爪前已完成 detach”这一安全属性成立。要修改 release 顺序或验证这条属性时，单独取证并如实报告结论。

无支撑但被物理持有的杯子必须停住等人工介入，不得自动开夹爪；stop/hold 后先保存证据。Live acceptance 需要独立的 Gazebo/MoveIt/controller/pose/contact 证据、fresh screenshot 和连续五次有效运行，细则见 [`test-and-acceptance.md`](references/test-and-acceptance.md)。
