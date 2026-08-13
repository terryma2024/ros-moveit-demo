# 长程实验账本

## 何时必须启用

出现任一条件，必须在运行下一条实验前启用持久账本：

- 预计需要两轮以上参数、几何、控制或物理实验；
- 需要比较环境生命周期、统计失败率或连续成功；
- 任务可能跨上下文压缩、goal 暂停或 agent 交接；
- 已有多轮 `/tmp` 证据，或用户要求避免重复已验证路线。

单轮、不会交接的普通低速最小复现继续只用唯一的 `/tmp/so101-debug-<task-id>/` 证据目录。

## 恢复任务时的硬门槛

恢复长程任务后，必须先读取账本和本次操作适用的其他 reference，并在开始实验前写明：

1. 最后一个可信 checkpoint；
2. 已确认结论和已证伪路线；
3. 当前 worktree、dirty diff、进程和证据归属；
4. 下一条实验引用哪个历史 `experiment_id`，以及它提供什么新增信息。

这四项未恢复前，不得启动 stack、改参数、操作 GUI、清理进程或重复旧实验。账本不会授权 `codex-cua`、扩大进程清理范围、运行真实机械臂、push 或 merge；这些动作仍遵守各自规则。

## 文件位置与证据边界

- 账本：当前实现 worktree 的 `docs/experiments/<task-slug>-experiment-ledger.md`。
- 每个 task 只能登记一个原始证据根：
  - 普通低速日志、截图、检查和临时构建证据：`/tmp/so101-debug-<task-id>/`；
  - 高频无损或明确要求持久保留的证据：`/data/work/so101-evidence/<task-family>/<run-id>/`；
  - 已被替代但仍需审计的批次：`/data/work/so101-evidence/archived/<task-family>/<run-id>/`。
- 禁止直接创建 `/data/work/so101-debug-*`，也不得把一个 task 分散到多个 evidence root。
- 账本只保存关键数值、退出码、摘要、证据路径和必要哈希；日志、截图、视频、rosbag 和构建产物不得复制进账本或源码目录。
- `/tmp` 不是长期结论的唯一保存位置。证据已丢失时必须标记 `evidence_unavailable`，不得假装仍可复核。
- 完成 checkpoint 必须分类报告 retained、archived 和可删除候选。未获用户明确授权不得删除；
  “可删除候选”不等于删除许可。
- 迁移或归档证据时，先记录 source-to-target 清单和相对文件 SHA256/大小/数量；移动后逐项复核，
  更新 tracked ledger/provenance/docs 绝对路径，但不回写或改变历史实验结论。
- 工程调试账本不默认写入学习者 session，也不改变个人学习进度。

同一任务只允许一个账本写入者。其他 agent 返回只读分析，由主执行者落账，避免并发改写历史。

## 账本头部

账本开头必须维护以下当前快照：

```yaml
task_id: so101-<stable-task-id>
goal: <端到端目标>
success_contract: <可计数的成功条件>
worktree: <absolute-path>
branch: <branch-name>
base_commit: <commit>
current_commit: <commit>
evidence_root: <the-one-approved-/tmp-or-/data/work/so101-evidence-root>
confirmed_conclusions:
  - <结论及其 experiment_id>
disproven_routes:
  - <路线及其 experiment_id>
open_hypotheses:
  - <未决假设>
latest_checkpoint: <checkpoint-id>
next_experiment: <experiment-id-or-NONE>
```

尖括号表示每个任务必须填写的值，不是允许保留的占位文字。每次 commit、分支、worktree 或目标变化后更新头部，但不得回写篡改历史实验条目。

## 单次实验状态机

合法状态转换只有：

```text
PLANNED -> RUNNING -> VALID
                   -> INVALID
```

- `PLANNED`：实验尚未启动，假设、唯一变量、生命周期和判据已经冻结。
- `RUNNING`：环境与 provenance 已核验，命令已经开始执行。
- `VALID`：前置条件和取证契约满足；结果可以支持成功、失败或参数比较。
- `INVALID`：环境、provenance、初始状态、命令或证据污染；保留记录但不用于行为结论。

不得从结果倒推并重写 `PLANNED` 内容。需要更正时追加 `correction`、时间和理由。

`ISOLATED_STACK` 只表示为单轮诊断新建了独立 ROS domain、Gazebo partition 和进程树；
它不能计入 `RESET_WORLD` 或 `FULL_RESTART` 的稳定性批次。用户指定重复实验生命周期时，
不得用 `ISOLATED_STACK` 绕过该约束。

## 实验记录模板

每轮复制下面完整模板；`experiment_id` 一经使用不得复用：

```yaml
experiment_id: EXP-<monotonic-id>
status: PLANNED
prior_experiment: <experiment-id-or-NONE>
hypothesis: <本轮准备证伪的解释>
prediction: <若假设成立会观察到什么>
single_variable: <唯一主动变化；NONE 表示固定配置复验>
lifecycle: REUSE_STACK | RESET_WORLD | FULL_RESTART | ISOLATED_STACK
preconditions:
  - <初始机器人、物体、scene 和进程条件>
success_criteria:
  - <端到端或本轮边界的成功事实>
failure_criteria:
  - <有效失败事实>
invalid_criteria:
  - <使本轮不能计数的污染条件>
provenance:
  source_commit: <commit>
  install_overlay: <absolute-path>
  runtime_executable: <absolute-path-or-package-prefix>
  ros_domain_id: <integer>
  gz_partition: <unique-partition>
commands:
  - command: <exact-command>
    exit_code: <integer-or-PENDING>
observed:
  - <OBSERVED 事实、时间和关键数值>
inferred:
  - <INFERRED 解释或 NONE>
conclusion: <本轮结论或 PENDING>
evidence:
  - <absolute-path-and-optional-hash>
decision: KEEP | REVERT | REPEAT | ABANDON | PENDING
next_experiment: <experiment-id-or-NONE>
```

创建条目时状态为 `PLANNED`；核验 provenance 后更新为 `RUNNING`；结束时必须落为 `VALID` 或 `INVALID`，并补齐命令退出码、观察、结论、证据和决策。

## 连续成功与无效运行

连续成功声明必须同时固定：commit、参数集合、成功契约和 lifecycle。例如：

```text
同一 commit、同一 motion policy、每次 FULL_RESTART 的连续 5 次端到端 pick-place 成功。
```

- `VALID` 成功：进入分母并延长当前成功序列。
- `VALID` 失败：进入分母并终止当前成功序列。
- `INVALID`：不进入分母、不算产品失败，但终止当前统计批次；修复污染后创建新的实验 ID 和批次。
- `REUSE_STACK`、`RESET_WORLD`、`FULL_RESTART` 和 `ISOLATED_STACK` 分开统计，不得混算为一个稳定性结论。

## 交接 checkpoint

上下文压缩、agent 交接、goal 暂停或停止工作前，必须在账本头部更新 checkpoint，并追加：

```yaml
checkpoint_id: CP-<monotonic-id>
last_valid_experiment: <experiment-id-or-NONE>
current_hypothesis: <hypothesis-or-NONE>
working_tree_status: <clean-or-exact-dirty-paths>
owned_processes: <pid-command-session-summary-or-NONE>
preserved_processes: <processes-that-must-not-be-touched-or-NONE>
confirmed_conclusions:
  - <conclusion-and-experiment-id>
disproven_routes:
  - <route-and-experiment-id>
open_risks:
  - <risk-or-NONE>
next_command: <one-exact-command-or-NONE>
```

聊天总结、tmux 输出或 goal 文本不能替代这个 checkpoint。

## 允许重复实验的条件

只有以下情况允许重复历史路线：

- 固定配置的重复性或连续成功验证；
- lifecycle、commit、初始条件或测量方法发生明确变化；
- 旧实验为 `INVALID`，本轮消除了具体污染项；
- 新证据与旧结论冲突，需要同条件复验。

新条目必须通过 `prior_experiment` 引用旧 ID，并在 `prediction` 中写明新增信息。仅因为“忘了结果”“想再试一次”或没有读取旧证据，不得重复。

## 示例：完整重启的连续成功验证

任务目标是验证 SO-101 pick-place 在完整环境重启下连续成功。先为五次运行分别建立 `EXP-021` 至 `EXP-025`，每条都使用 `lifecycle: FULL_RESTART`、`single_variable: NONE`，固定 commit、motion policy 和成功契约。每次都记录独立 ROS domain、Gazebo partition、overlay、最终 Gazebo/MoveIt attachment 状态和截图。

若 `EXP-023` 因 ROS domain 非法而无法启动，它必须记为 `INVALID`，原批次停止；修复环境后从新 ID 建立新的五次批次。若它正常启动但 pick-place 失败，则记为 `VALID` 失败、进入分母并终止连续成功序列。

## 常见错误

- 只在聊天或 tmux 中总结。改为先更新账本和 checkpoint，再发送摘要。
- 只保存 `/tmp` 路径。必须同时保存决定结论的关键数值和状态。
- 实验结束后才补写假设。`PLANNED` 必须先于命令执行。
- 把规划失败、环境无效和产品行为失败混成一个失败率。按状态和 lifecycle 分开。
- 复用实验 ID 或静默改写旧结论。新建 ID，并用 `prior_experiment` 和 `correction` 追踪。
- 为填写账本扩大操作权限。账本只记录授权范围，不创造新授权。
