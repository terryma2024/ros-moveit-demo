# SO-101 Teleop 独立模块与多后端适配设计

- 日期：2026-08-11
- 状态：设计已通过对话分段确认，等待书面规格复核
- 目标仓库：`moveit-demo`
- 实现分支：`codex/so101-teleop-extraction`
- 实现 worktree：`/data/work/ws_moveit/.worktrees/so101-teleop-extraction`

## 背景

当前 Teleop 的 Python 后端、React 前端、launch、配置、测试和 Web 构建规则都位于
`src/so101_gazebo_demo_cpp`。虽然 Teleop 内部已有 gateway 和 port 抽象，运行实现仍通过
ament prefix 硬编码定位 `so101_gazebo_demo_cpp`，并调用该包的
`pick_place_state_machine`、`reset_so101_world` 和 `so101_moveit_scene`。

这种所有权使 Teleop 难以复用到以下后端：

- `so101_gazebo_demo_cpp`
- `so101_gazebo_demo_py`
- `so101_mujoco_demo_py`

同时，`tile_ai_station_guis.py` 仍由 C++ Gazebo 包安装；ai-station 截图脚本由上层
`robot_demo_001` 根仓维护，并假定 RViz 和 Ghostty 窗口存在。这些边界会增加多后端调试
成本，并让通用 GUI 工具依赖某一个机器人运行包。

## 设计目标

1. 在 `src/so101_teleop` 建立独立 ROS 2 package，完整拥有 Teleop 前端和后端。
2. 使用显式 `backend:=gazebo_cpp|gazebo_py|mujoco_py` 选择运行后端。
3. 保持机器人工作流、reset、scene 和物理结果判定由对应 ROS module 唯一拥有。
4. 使用配置化 CLI adapter 连接已安装的后端 executable。
5. 通过 capability 驱动前端和 API，不伪造未实现能力。
6. 将 `tile_ai_station_guis.py` 及其 X11/EWMH 支撑代码迁入 `so101_teleop`。
7. 在 moveit-demo 中建立独立 `ai-station-gui` Skill，长期维护截图和屏幕控制流程。
8. 优先使用本地 AI agent 与 `cua-driver` Skill；无该能力时才使用脚本截图回退。
9. 允许 RViz、Ghostty 等窗口全部不存在，并以全屏桌面截图作为兜底证据。
10. 删除旧 C++ Teleop launch，不提供兼容 wrapper。

## 非目标

- 不把 pick-place 状态机迁入 `so101_teleop`。
- 不让浏览器选择或复制机器人状态转移。
- 不让 Teleop 启动 Gazebo、MuJoCo、MoveIt 或 controller stack。
- 不把三个后端强制改造成同一套内部类结构。
- 不在本次迁移中补齐 MuJoCo 尚未实现的 live execute、reset 或 observer 能力。
- 不引入可由 Web 请求指定的任意 package、executable、shell 或 profile 路径。
- 不改写历史实验账本、历史设计、历史计划或既有证据中的旧命令。

## 方案选择

采用配置化 CLI Adapter。

未采用统一 ROS Service/Action 协议，是因为它要求三个后端同步新增接口节点，迁移面过大。
未采用直接导入各后端 Python 模块，是因为 C++ 后端仍需特殊路径，而且会让 Teleop 依赖后端
内部源码布局。CLI adapter 复用当前已安装 executable 边界，允许以后在不改变 Web API 的
前提下替换为 ROS Action adapter。

## 总体架构

```text
Web UI
  |
  v
so101_teleop API / session / lease / idempotency
  |
  +-- common ROS telemetry and direct joint/TCP controls
  |
  v
BackendProtocol + immutable installed profile
  |
  +-- gazebo_cpp --> so101_gazebo_demo_cpp installed executables
  +-- gazebo_py  --> so101_gazebo_demo_py installed console scripts
  +-- mujoco_py  --> so101_mujoco_demo_py actual supported owners

The selected ROS module remains the workflow and physics owner.
```

依赖方向保持单向：

- `so101_teleop` 不在 `package.xml` 中声明任何具体后端为构建依赖或强制运行依赖。
- 启动时才通过 ament index 解析被显式选择的后端。
- `so101_gazebo_demo_cpp`、`so101_gazebo_demo_py` 和
  `so101_mujoco_demo_py` 都不依赖 `so101_teleop`。

## 新 package 结构

`so101_teleop` 使用 `ament_cmake + ament_cmake_python`。Python 承载 FastAPI、
adapter 和 ROS worker；CMake 负责 Bun 前端构建、资源安装、launch 和测试注册。

```text
src/so101_teleop/
├── CMakeLists.txt
├── package.xml
├── launch/
│   └── so101_teleop.launch.py
├── config/backends/
│   ├── gazebo_cpp.yaml
│   ├── gazebo_py.yaml
│   └── mujoco_py.yaml
├── so101_teleop/
│   ├── api.py
│   ├── server.py
│   ├── service.py
│   ├── models.py
│   ├── control.py
│   ├── telemetry.py
│   ├── workflow_gateway.py
│   ├── backends/
│   │   ├── protocol.py
│   │   ├── profile.py
│   │   ├── registry.py
│   │   └── cli_adapter.py
│   └── gui/
│       └── x11.py
├── scripts/
│   ├── so101_teleop_server.py
│   └── tile_ai_station_guis.py
├── web/
├── test/
└── docs/
```

原 `so101_gazebo_demo_cpp/so101_teleop`、`web`、Teleop launch/config/docs/tests、
Web CMake 构建规则和 Teleop Python 运行依赖全部迁出。C++ 包不保留旧 launch wrapper。

## 执行所有权

系统区分“操作台控制面”和“机器人工作流”：

| 所有者 | 职责 |
|---|---|
| `so101_teleop` | Web API、前端、lease、session、command id、幂等、防并发、能力检查、请求转换、结果解析 |
| 后端 adapter | 定位已安装 owner、构造固定参数、执行、解析并包装结果 |
| 对应 ROS module | 状态机、状态转移、MoveIt 执行、夹爪、仿真物理、checkpoint/resume、reset/recovery、最终结果 |

`WorkflowGateway` 可以继续位于 Teleop，但不能定义
`MOVE_ABOVE_OBJECT -> DESCEND -> CLOSE_GRIPPER` 等状态序列。浏览器和 Teleop 不能跳过、
插入或重排机器人状态。

## 启动与预检

统一入口：

```bash
ros2 launch so101_teleop so101_teleop.launch.py \
  backend:=gazebo_py \
  simulation_session_id:=teleop-session-001
```

Teleop 连接已存在的仿真、MoveIt 和 controller stack，不负责启动它们。启动顺序为：

1. 校验 `backend` 为固定枚举。
2. 加载 package 内安装的不可变 profile。
3. 通过 ament index 查找 profile 指定的 package。
4. 检查该 profile 当前声明能力所需的 executable。
5. 验证 backend session、ROS graph 和公共 telemetry 前置条件。
6. 验证或构建 Web bundle。
7. 冻结本进程 capability snapshot。
8. 全部通过后启动 FastAPI server。

缺少所选后端时直接失败，不自动探测或切换到另一个已安装后端。

## BackendProtocol

```text
probe()
capabilities()
observe()
run_workflow(request)
reset_world(request)
scene_operation(request)
```

每次 adapter 调用返回统一 envelope：

```json
{
  "ok": true,
  "backend": "gazebo_py",
  "operation": "workflow_run",
  "session_id": "example-session",
  "owner_package": "so101_gazebo_demo_py",
  "owner_executable": "pick_place_state_machine",
  "exit_code": 0,
  "result": {},
  "error": null
}
```

Profile 是 package 安装内容，只能通过固定 backend ID 选择。Web 请求不能覆盖 package、
executable、参数模板、环境变量白名单或 profile 文件路径。adapter 使用参数数组调用
subprocess，不使用 shell 拼接。

## Backend profiles

| ID | Workflow owner | Reset/scene owner | 仿真事实源 |
|---|---|---|---|
| `gazebo_cpp` | `so101_gazebo_demo_cpp/pick_place_state_machine` | C++ `reset_so101_world`、`so101_moveit_scene` | Gazebo transport/contact |
| `gazebo_py` | `so101_gazebo_demo_py/pick_place_state_machine` | Python 同名 console scripts | Gazebo transport/contact |
| `mujoco_py` | `so101_mujoco_demo_py/pick_place_state_machine`，仅用于已验证的非 live CLI | 当前无可供 Teleop 使用的 reset/scene owner | 当前不向 Teleop 暴露物理 observer |

当前 MuJoCo worktree 的普通 `pick_place_state_machine` CLI 对 execute 返回
`LIVE_RUNTIME_NOT_IMPLEMENTED`，且未提供与 Gazebo profile 等价的完整 reset/scene CLI。
因此首版 `mujoco_py` profile 固定为：`backend_probe=true`，
`workflow_execute=false`，`workflow_start=false`，`workflow_run=false`，
`workflow_resume=false`，`reset_world=false`，`scene_operations=false`，
`physical_observation=false`，`manual_joint_execute=false`，
`manual_tcp_execute=false`，`camera_presets=false`。所有 live 操作按
`BACKEND_CAPABILITY_UNAVAILABLE` 处理。后续 MuJoCo owner 补齐后，通过 profile 和契约
测试逐项启用，不修改前端协议。

## Workflow 请求语义

以下语义只适用于对应 capability 已启用的 profile；未启用时在创建 run 或 subprocess 之前
失败：

- Start：创建新 run，调用后端 `--mode execute --step`。
- Run：创建新 run，调用后端 `--mode execute`。
- Resume：要求 Teleop 已知 run、session 和 checkpoint，再调用后端 `--resume true`。
- Reset：调用后端 reset owner；只有后端证明 reset 收敛后，才清理 Teleop run、lease、
  plan 和 idempotency 状态。
- Stop：只执行后端明确支持的停止语义；不能由 Teleop 虚构状态转移。

checkpoint 路径和内容由后端状态机拥有。Teleop 只保存 run 到 checkpoint/session 的控制面
映射。

## Capability 驱动

`/capabilities` 返回 backend ID、owner provenance 和逐项能力。前端据此禁用或隐藏不可用
操作。直接调用未支持 API 时返回 `BACKEND_CAPABILITY_UNAVAILABLE`。

禁止以下行为：

- 因某操作不支持而调用另一 backend；
- 把 dry-run 或 headless executable 存在解释为 live execute 可用；
- 返回成功但不执行 owner；
- 用 MoveIt Planning Scene pose 代替 Gazebo 或 MuJoCo 物理 pose。

## GUI tiling 迁移

`tile_ai_station_guis.py` 和底层 X11/EWMH 实现一起迁入 `so101_teleop`，并保留：

- 无参数时 RViz 左、Gazebo 右；
- `--maximize gazebo|rviz`；
- 唯一窗口、超时、work area 和几何容差语义；
- `LAYOUT_OK`、`LAYOUT_ERROR` 和退出码契约。

新入口：

```bash
ros2 run so101_teleop tile_ai_station_guis.py
```

旧入口 `ros2 run so101_gazebo_demo_cpp tile_ai_station_guis.py` 删除，不提供 wrapper。

## 独立 ai-station-gui Skill

moveit-demo 新增长期维护的 Skill：

```text
.agents/skills/ai-station-gui/
├── SKILL.md
├── scripts/
│   ├── capture-ai-station.sh
│   └── ai-station-capture.py
└── references/
    └── capture-contract.md
```

`so101-dev`、`gazebo-video-debug` 和 Teleop 当前操作文档引用该 Skill，不复制脚本或流程。

### Skill 能力路由

`SKILL.md` 首先要求 agent：

1. 判断当前是否直接运行在 ai-station，禁止远端 agent 自我 SSH。
2. 确认当前会话是否为具有屏幕工具能力的 Codex、Claude 或 Kimi，而不是只检查同名二进制。
3. 检查该 agent 是否已加载可用的 `cua-driver` Skill/工具。
4. 使用现场工具 schema 检查 driver、桌面会话和权限是否健康。
5. 若健康，优先使用 `agent + cua-driver` 完成截图和屏幕控制。
6. CUA 操作严格使用 `snapshot -> action -> fresh snapshot`，索引不跨 snapshot 复用。
7. 只有该路径不可用时，才使用 Skill 自带脚本做确定性截图回退。

脚本回退只提供截图，不假装具备鼠标、键盘或 UI 语义控制能力。

### 本机与远程回退

`capture-ai-station.sh` 支持两种明确路径：

- 当前直接位于 ai-station：直接执行同 Skill 内的 Python helper，不 SSH 自身。
- 当前位于 Mac/orchestrator：通过 `AI_STATION_SSH_TARGET` 部署 helper、远程执行并拉回结果。

输出目录必须位于调用者提供或脚本创建的证据目录，不把运行截图写入源码目录。

## 截图契约

全屏桌面截图是唯一必需工件；RViz、Ghostty 和其他窗口截图全部可选。

```json
{
  "captured_at": "2026-08-11T12-00-00",
  "desktop": "/tmp/example/desktop.png",
  "rviz": null,
  "ghostty": null,
  "captured_windows": [],
  "missing_windows": ["rviz", "ghostty"],
  "capture_mode": "desktop_only",
  "ghostty_tab_test": "not_requested"
}
```

行为矩阵：

| RViz | Ghostty | 结果 |
|---|---|---|
| 有 | 有 | desktop + rviz + ghostty |
| 有 | 无 | desktop + rviz |
| 无 | 有 | desktop + ghostty |
| 无 | 无 | 仅 desktop；退出 0 |

本地 wrapper 只对非空路径执行复制，不创建空文件，也不复用旧截图。缺失窗口输出
`RViz: not present` 或 `Ghostty: not present`。只有全屏截图失败、manifest 非法或已声明
工件传输失败时返回非零。

`--test-ghostty-tabs` 在 Ghostty 缺失时不发送按键，退出 0，并记录
`ghostty_tab_test: skipped_no_window`。

## 根仓迁移

`robot_demo_001` 不再长期维护截图实现：

- 删除根仓 `scripts/capture-ai-station.sh`；
- 删除根仓 `scripts/ai-station-capture.py`；
- 根仓 AGENTS、README、环境文档和当前 Skill 引用改为
  `moveit-demo/.agents/skills/ai-station-gui/`；
- 根仓不保留第二份 capture 实现；
- moveit-demo 变更可用后，根仓更新 submodule pointer。

根仓中通用的 `cua-driver` 参考资料不属于 capture 实现，不因本次迁移自动删除；新的
`ai-station-gui` Skill 只要求优先使用现场已加载的 driver Skill/工具。

## 错误模型

Teleop 统一包装基础设施错误，并保留后端原始 failure code：

- `BACKEND_PACKAGE_NOT_FOUND`
- `BACKEND_EXECUTABLE_NOT_FOUND`
- `BACKEND_CAPABILITY_UNAVAILABLE`
- `BACKEND_SESSION_MISMATCH`
- `BACKEND_TIMEOUT`
- `BACKEND_OUTPUT_INVALID`
- `BACKEND_OPERATION_FAILED`
- `TELEMETRY_STALE`

任何错误都不触发 backend 自动切换。adapter 诊断写入
`/tmp/so101-teleop/{sanitized_session_id}/`，不写源码目录。API 不返回完整环境变量、凭据或不受限的
subprocess 输出。

## 迁移顺序

1. 建立独立 worktree、设计规格和 RED 所有权测试。
2. 新建 `so101_teleop` package。
3. 迁移 Python、Web、config、launch、docs 和 tests，先保持 `gazebo_cpp` 行为等价。
4. 引入 BackendProtocol、profile registry 和 capability gate。
5. 接入 `gazebo_py` profile。
6. 接入只声明真实能力的 `mujoco_py` profile。
7. 迁移 GUI tiling 工具和测试。
8. 新建 `ai-station-gui` Skill，迁入并修复 capture 脚本。
9. 更新 moveit-demo 当前 README、AGENTS、Skills 和操作文档。
10. 从 C++ 包删除 Teleop 和 tile 的旧所有权及入口。
11. 在根仓独立变更中删除旧 capture 实现、更新引用和 submodule pointer。
12. 完成 build、package、Web、profile、截图、runtime 和视觉验收。

## 文档迁移原则

更新当前有效的：

- package README；
- 仓库 AGENTS；
- `so101-dev`；
- `gazebo-video-debug`；
- Teleop operator 文档；
- ai-station 当前环境和截图说明。

历史 specs、plans、handoffs 和 experiment ledgers 保留旧路径与旧命令。若需要帮助读者理解，
可以在当前索引或新设计中声明迁移，但不得批量改写历史证据。

## 测试与验收

### 结构与依赖

- C++ 包不再包含 Teleop Python、Web、launch、tile 源码或安装规则。
- `so101_teleop` clean build 可生成 Web bundle 并安装 server、launch、profiles 和 tile CLI。
- 三个后端 package 不依赖 `so101_teleop`。
- profile 不能由 Web 请求覆盖 package、executable 或参数模板。

### 后端契约

- `gazebo_cpp` 保持当前 API、Start/Run/Resume/Reset 和安全门语义。
- `gazebo_py` 调用 Python 包自己的 workflow/reset/scene owner，不误用 C++ executable。
- `mujoco_py` 可探测 package，并对当前未实现 live 能力明确返回 unavailable。
- package 缺失、executable 缺失、超时、非零退出和畸形输出均有定向测试。

### Web

- capability snapshot 决定按钮状态。
- 切换 profile fixture 时，Vitest 覆盖支持和不支持的操作。
- Playwright 覆盖启动页、能力显示、禁用态、API 错误和静态资源安装路径。
- OpenAPI schema 从新 package 生成并保持客户端类型一致。

### GUI 与截图

- 新 tile 命令保持 parser、X11 payload、超时、幂等和几何容差测试。
- 新安装入口输出 `LAYOUT_OK`，旧 C++ 安装入口不存在。
- 截图单测覆盖 RViz/Ghostty 的四种组合。
- 无任何目标窗口时，helper 仍生成全屏 desktop、manifest 合法且退出 0。
- wrapper 不复制 null 路径、不生成空文件、不复用旧文件。
- 在实际无 Ghostty 的 ai-station 会话中，capture 路径生成 fresh desktop 并成功退出。
- 若现场 agent 和 `cua-driver` 健康，验收记录优先路径及 fresh snapshot；脚本只作为回退验证。

### ROS 与运行时

- 在独立 overlay 中构建并 source 新安装产物。
- 回读 `ros2 pkg prefix so101_teleop`、installed launch、profiles、Web 和 executables。
- 分别验证 C++ 与 Gazebo Python profile 的 owner package、owner executable、session 和退出码。
- 不把 MuJoCo dry-run 或 headless 存在当作 live execute 通过。
- 不启动第二套与现有物理实验冲突的 stack；runtime 使用独立 domain/partition 或经核验复用。
- fresh GUI 证据必须与同一次运行的 ROS、MoveIt 和仿真数值证据对应。

## 完成条件

只有以下条件全部满足，才能声明迁移完成：

1. 独立 `so101_teleop` 是 Teleop 与 tile 工具的唯一源码和安装所有者。
2. 旧 C++ launch 和 runtime entry 不存在，文档不再把它们作为当前入口。
3. C++ 与 Gazebo Python profile 的可用能力通过自动化和至少一次真实连接验证。
4. MuJoCo profile 只暴露当前真实能力，没有假成功。
5. `ai-station-gui` Skill 先路由 agent+cua-driver，再安全回退到脚本。
6. 所有窗口缺失时仍能取得 fresh 全屏截图并退出 0。
7. 根仓不再维护 capture 实现，只引用 moveit-demo Skill。
8. package、Web 和文档检查无新增失败，运行 provenance 可回读。
9. 没有覆盖用户改动，没有扰动其他 worktree 或现有仿真进程。
