# SO-101 Teleop Workflow Run/Resume 语义设计

**日期：** 2026-08-03
**范围：** `so101_gazebo_demo` Teleop Web UI 与 workflow HTTP 服务边界

## 目标

让 `Start`、`Run`、`Resume` 表达三个互不重叠的操作，并由前端与服务端共同执行同一契约：

- `Start`：创建新 workflow，只执行第一个 checkpoint step。
- `Run`：创建新 workflow，从头连续执行到 `DONE` 或失败边界。
- `Resume`：继续一个已经存在的 workflow，从当前 checkpoint 连续执行到 `DONE` 或失败边界。

浏览器仍不选择具体状态；状态转移继续由 C++ `pick_place_state_machine` 独占。

## UI 状态矩阵

| 状态 | Start | Run | Next Step | Stop | Resume | Reset workflow |
|---|---:|---:|---:|---:|---:|---:|
| 无租约 | 禁用 | 禁用 | 禁用 | 禁用 | 禁用 | 禁用 |
| 有租约、workflow 未开始 | 可用 | 可用 | 禁用 | 禁用 | 禁用 | 禁用 |
| 请求执行中 | 禁用 | 禁用 | 禁用 | 禁用 | 禁用 | 禁用 |
| workflow 已开始且未到终态 | 禁用 | 禁用 | 可用 | 可用 | 可用 | 可用 |
| workflow 已到 `DONE` | 禁用 | 禁用 | 禁用 | 禁用 | 禁用 | 可用 |
| Reset 成功后 | 可用 | 可用 | 禁用 | 禁用 | 禁用 | 禁用 |

`VALIDATION_FAILED` 保留现有 `Force Continue` 的独立门控，不用普通 `Resume` 绕过物理抓取验证。

## 服务端契约

### Start

1. 当前 simulation session 不得已有有效 workflow。
2. 服务端生成新的 `run_id` 和独立 checkpoint 文件。
3. 调用 C++ owner 时使用 `--mode execute --step`，不使用 `--resume`。

### Run

1. 当前 simulation session 不得已有有效 workflow。
2. 服务端生成新的 `run_id` 和独立 checkpoint 文件。
3. 调用 C++ owner 时使用 `--mode execute`，不使用 `--step` 或 `--resume`。
4. 因此 `Run` 永远表示从头连续执行，不承担续跑语义。

### Resume

1. 请求必须携带当前 simulation session 中已登记的 `run_id`。
2. checkpoint 必须仍有效；既有 session/checkpoint/readiness 安全校验保持不变。
3. 调用 C++ owner 时使用 `--mode execute --resume true`，不使用 `--step`。
4. 若不存在 workflow，不自动创建新 run，返回明确的 workflow mismatch/rejection。

### Reset workflow

Reset 继续要求二次确认。成功后删除服务端登记并使旧 `run_id` 失效，UI 清除 workflow snapshot，回到“有租约、workflow 未开始”状态。它不重置整个 Gazebo world。

## 状态所有权与错误处理

- 服务端以当前 simulation session 中登记的 workflow 作为“是否已经开始”的权威来源，不能仅相信浏览器传入的按钮状态。
- `Start` 或 `Run` 在已有有效 workflow 时必须 fail closed，不能静默覆盖 checkpoint。
- `Resume` 在没有有效 workflow、session 已变化或 checkpoint 已失效时必须 fail closed。
- 页面只根据租约、pending 状态与服务器返回的 workflow snapshot 决定按钮可用性，不在浏览器推导或选择下一个机器人状态。
- 现有 lease、readiness、session、stale-checkpoint、action、controller 和 Force Continue 安全门控保持不变。

## 最小实现边界

- Web：调整 `WorkflowPanel` 的按钮状态矩阵；Reset 成功后清除浏览器 workflow snapshot。
- Teleop service：将 `workflow_run` 纳入“创建新 workflow”路径，将 `workflow_resume` 保持为“既有 workflow + `--resume true`”路径，并拒绝语义不合法的调用。
- 文档：更新 Teleop 操作说明中的 Start/Run/Resume 定义。
- 不修改 C++ transition table、机器人动作序列、MoveIt/Gazebo 执行逻辑或 Force Continue 策略。

## 验证设计

### RED/GREEN 自动化测试

- UI：获得租约且无 workflow 时，`Start`、`Run` 可用，`Resume` 禁用。
- UI：Start 返回 run 后，`Start`、`Run` 禁用，`Resume` 可用。
- UI：`DONE` 时只保留 Reset workflow 可用。
- UI：Reset 成功后清除 snapshot 并恢复初始按钮矩阵。
- 服务端：初始 `workflow_run` 创建 run，C++ 参数不含 `--step` 和 `--resume`。
- 服务端：已有 workflow 时 `workflow_run` 被拒绝，旧 checkpoint 不被替换。
- 服务端：`workflow_resume` 对既有 run 追加 `--resume true`。
- 服务端：初始 `workflow_resume` 被拒绝且不创建 checkpoint。
- 回归：`workflow_start` 仍只执行一步；`workflow_step` 仍为 `--resume true --step`。

### 运行时与视觉验收

在 ai-station 的既有 Teleop stack 上受控切换到本轮构建产物后：

1. 获得租约，截图确认初始 `Start`、`Run` 可用而 `Resume` 禁用。
2. Reset 后点击 Start，查询响应与 checkpoint，截图确认 `Run` 禁用、`Resume` 可用。
3. Reset 后点击 Run，确认新 `run_id` 从头执行，且执行参数没有 `--resume`。
4. Start 后点击 Resume，确认同一 `run_id` 使用 checkpoint 继续并带 `--resume true`。
5. 对受影响的状态机、MoveIt、controller/joint/TF、Gazebo 与 Planning Scene 证据分别验收，并使用本轮新截图确认按钮及可见结果。

ai-station 当前运行的 Teleop 来自独立 dirty worktree；部署与验收不得覆盖该 worktree 的用户改动，也不得启动第二套 Gazebo/MoveIt stack。
