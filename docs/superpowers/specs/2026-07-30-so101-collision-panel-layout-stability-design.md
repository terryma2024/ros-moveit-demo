# SO-101 Collision Panel 布局稳定性设计

## 背景

当前 `CollisionPanel` 接收一段由 `App` 拼接的 summary 字符串，其中包含杯子位姿、controller map 和 source-age map 的原始 JSON。遥测刷新时，浮点数字符长度和 contact/collision 行数持续变化，导致：

- summary 形成超长不可控文本，横向撑大页面；
- 浮点位数变化触发频繁换行；
- 证据表行数变化使卡片高度和后续页面位置跳动；
- 深度以 `-7.2349e-9` 等原始值出现，操作员难以快速判断量级。

## 目标

1. 遥测内容长度和证据行数变化时，Collision Panel 外框高度保持稳定。
2. 页面不产生横向溢出。
3. Gazebo contact 与 MoveIt collision 同时可见，保留跨层对照能力。
4. 高频值以适合操作员阅读的格式显示，同时能查看未舍入原值。
5. 不降低遥测刷新频率，不丢失原始 API 数据，也不改变后端接口。
6. `so101_teleop.launch.py` 提供单命令启动体验：Web production bundle 缺失或比输入源码旧时先自动构建，成功后再启动 FastAPI。
7. 用顶层功能 Tabs 降低单页认知负担，并把 TCP frame 选择呈现为连续的 segmented control；切换视图不重置控制状态或遥测连接。

## 非目标

- 不修改碰撞、接触或抓取验证算法。
- 不引入图表、历史趋势或遥测持久化。
- 不替换 ai-station 的系统 Node，也不启动常驻 Node/Vite 开发服务器。
- 不在 launch 内递归调用 `colcon build`。
- 不改变现有功能面板内部的业务行为。

## 方案比较

### A. 固定摘要 + 双证据窗格（采用）

杯子位姿、controller 和 source age 使用固定结构；MoveIt/Gazebo 两个固定高度窗格并排显示，内部独立滚动。

优点：布局稳定，两个事实源同时可见，符合物理/规划场景独立验收要求。缺点：小屏幕上需要纵向堆叠。

### B. Collision 层内 Tabs

两个证据表共享一个固定区域，用 Tab 切换。更紧凑，但隐藏其中一层，容易漏看 Gazebo/MoveIt 不一致，因此不采用。

### C. 折叠原始 JSON

实现最少，但只能缓解默认展开问题，不能提供操作员可扫描的状态，也不能稳定表格高度，因此不采用。

## 组件结构

`CollisionPanel` 不再接收预先格式化的 `summary: string`，而是接收结构化 props：

```ts
type CollisionPanelProps = {
  objectPose?: Pose6D;
  controllers: Record<string, string>;
  sourceAges: Record<string, number>;
  moveit: Evidence[];
  gazebo: Evidence[];
};
```

内部拆为三个单一职责单元：

1. `TelemetrySummary`：杯子 XYZ、controller 状态和固定顺序的 source ages。
2. `EvidencePane`：固定高度、可滚动的单个证据表。
3. 纯格式函数：`formatAge`、`formatDepth`、`formatPoseCoordinate`。

项目 Web 工具链统一使用 Bun，并以 `bun.lock` 作为唯一依赖锁文件；安装、scripts 和一次性 CLI 均通过 Bun 运行，不使用系统 Node/npm/npx 或 `package-lock.json`。

先通过 Bun 运行官方 `shadcn@latest` 的 `info`/`docs`，并对已有 Card 执行 dry-run/diff；然后引入或合并官方 `Card`、`Badge`、`Tooltip`、`ScrollArea`、`Empty` 和 `Table` 组件。必须保留现有 AlertDialog/Button 行为，不能无审查覆盖已有组件。`CollisionPanel` 使用完整的 `CardHeader`、`CardDescription` 和 `CardContent` 结构，Controller 状态使用 Badge，精确值使用 Tooltip，证据区使用 ScrollArea 与 Table，空状态使用 Empty。视觉样式继续遵循有效的 `components.json` new-york/Radix 配置和项目现有深色 theme token；当前 shadcn CLI 不接受旧版顶层 `preset` 字段，因此不保留该无效字段。

页面同时引入官方 `Tabs` 与 `ButtonGroup`。顶层 Tabs 固定包含 `Joints`、`TCP`、`Collision`、`Target`、`Gazebo`、`Workflow`、`Events` 七项，默认 `Joints`，每次只挂载选中面板；`ConnectionHeader`、全局 notice、`Current to Target`、诊断下载和 RTF 保持在 Tabs 外。Tabs 仅控制视图，target/plan/workflow 与 telemetry state 继续由 `App` 持有，因此切换不丢状态且 WebSocket 不重连。小屏 `TabsList` 在自身内部横向滚动并限制为页面宽度。

`ConnectionHeader` 的视觉/DOM 顺序固定为标题 → READY/mode Badge → lease 按钮 → 动态 metadata。前三项组成 `shrink-0` action cluster，按钮不位于 revision、RTT 或可选 TTL 等变长文本之后。metadata 使用独立 `min-w-0` 区域，可截断或换行；短长 session/revision/RTT/TTL 更新时 lease 按钮横坐标变化不得超过 2 px，窄屏不得引起页面横向 overflow。

TCP 的 `World frame` / `Tool frame` 使用官方 `ButtonGroup` 包裹现有 Button，按钮间无 gap、共享相邻边界，形成 segmented control。两个按钮保留完整文字和原生键盘激活能力，以 `aria-pressed` 与清晰 variant 同时表达 active 状态。

## 布局

### 状态摘要

- 使用响应式 grid，而不是一行字符串。
- Cup Pose 固定显示 X/Y/Z 三个值，单位 `m`，保留三位小数。
- Arm 与 Gripper controller 各占固定状态项，以 Badge 显示 `active` 或实际状态。
- source ages 按 `joints, tcp, object, gazebo_contacts, moveit_collisions, scene` 的固定顺序显示。
- 年龄显示为固定三位小数的秒，例如 `0.016 s`；超过显示范围时写 `>99.999 s`。容器使用 `tabular-nums` 和固定最小宽度。
- 每个舍入值通过 Tooltip 暴露完整 key 与原始值，并保留 `title` 作为无需脚本的回退。
- 未提供的数据使用 `—`，但占据相同位置。

### 证据窗格

- Desktop 使用 `lg:grid-cols-2`，左侧 MoveIt、右侧 Gazebo；小屏幕纵向堆叠。
- 每个窗格使用固定高度 `h-56`，表格内容在内部滚动。
- Header 固定，数据行通过 ScrollArea 滚动；无数据时在相同高度内渲染 Empty。
- 表格采用 fixed layout；Object A/B 截断显示，Tooltip 与 `title` 提供完整名称。
- Depth 转为 mm，显示三位小数；Tooltip 与 `title` 保存原始米值。非常小的负零显示为 `0.000 mm`。
- Source 列截断，避免撑宽页面。

## 数据流

WebSocket/HTTP snapshot 仍按当前频率进入 store。`App` 将 snapshot 中的结构化字段直接传入 `CollisionPanel`。Panel 只做展示格式化，不缓存、不节流、不改变事实数据。

证据数组变化只影响固定高度滚动区内部；summary 数值变化只替换固定宽度文本，因此不会移动下方卡片。

## 可访问性

- 两张表保留明确的 `aria-label` 和 caption。
- 截断文本用 Tooltip 暴露完整值，并保留原生 `title` 回退。
- 状态不能只依赖颜色，Badge 始终显示状态文字。
- 滚动区可通过键盘聚焦，并提供描述性 `aria-label`。

## 测试与验收

### Component tests

1. 传入超长 controller/source JSON 值时，不再渲染 `{...}` 原始 JSON。
2. 固定顺序展示 cup/controller/source ages，并验证单位与舍入。
3. 深度按 mm 显示，原始值保存在 `title`。
4. 空证据与多行证据都保留固定窗格结构。
5. Object/Source 单元格具有 truncate 和完整 `title`。

### Launch 一键构建与启动

新增一个独立、可单测的 Python Web bundle preflight helper，并由 `so101_teleop.launch.py` 在创建 server Node 前同步执行：

1. 解析 `web_source_dir`（launch 参数优先，其次 `SO101_TELEOP_WEB_SOURCE`，开发环境再回退到 symlink-install 可解析的源码目录）。
2. 检查 `dist/index.html` 以及其引用的本地静态资产均存在且非空。
3. 对比 bundle 与构建输入的新鲜度；输入包括 `package.json`、lockfile、Vite/Tailwind/PostCSS/TypeScript 配置和 `src/**`，不把测试输出或 `node_modules` 计入。
4. bundle 新鲜时快速跳过；缺失或过期时，使用 Bun 运行 `bun install --frozen-lockfile`（仅在依赖缺失或 `bun.lock` 指纹变化时）和 `bun run build`。
5. 构建后再次验证入口及引用资产。任何一步失败均让 launch 明确失败，FastAPI server 不得启动。
6. 通过 `SO101_TELEOP_WEB_ROOT=<source>/dist` 把已经验证的 bundle 显式传给 server；`main.installed_web_assets()` 支持该环境变量，并验证路径是目录。

launch 新增 `build_web_if_needed`（默认 `true`）和 `web_source_dir` 参数。显式关闭自动构建时仍必须验证可服务 bundle；无有效 bundle 直接失败。release 安装继续由 CMake 安装预构建 `dist`，launch preflight 不调用 `colcon`、不修改 ROS overlay，也不启动 Vite dev server。

Bun 解析顺序为：显式 `SO101_TELEOP_BUN`，ai-station 固定 Bun，最后是 PATH 中的 Bun。不可用系统 Node/npm 作为回退。

对应测试覆盖：fresh bundle 跳过构建、bundle 缺失触发构建、源码较新触发构建、`bun.lock` 变化触发 `bun install --frozen-lockfile`、构建失败阻止 server、非法 `SO101_TELEOP_WEB_ROOT` 被拒绝，以及 launch 参数和环境变量传递契约。

### Playwright

Mock telemetry 在以下状态间交替：

- source age 从短小数切换为长小数；
- contact/collision 从 0 行切换为 20 行；
- object 名称切换为超长字符串。

断言：

- Collision Panel bounding-box 高度变化不超过 2 px；
- `document.documentElement.scrollWidth <= clientWidth`；
- 两个证据窗格同时可见；
- 窗格内容溢出时内部可滚动；
- 页面 console/pageerror 为空。

在布局测量前先激活 `Collision` tab。另覆盖顶层 Tabs 点击和方向键切换、每次只显示所选 panel、切换后 Joint/TCP target 值保持、窄屏 TabsList 内滚动但页面无横向 overflow，以及 TCP ButtonGroup 的 active 状态与键盘操作。

### 构建与启动验收

- 在已有新鲜 bundle 时运行 launch，日志明确显示 `web bundle fresh`，且不执行 Bun build。
- 临时移走验证副本中的 `dist` 后运行 preflight，确认自动构建并通过静态资产完整性检查。
- 构造失败 Bun 命令，确认 launch 非零退出且没有新增 `so101_teleop_server_process`。
- 从干净 ROS 环境执行同一个 launch 命令，确认 8000 端口仅一个 listener，Web UI 可加载且 API/WebSocket 正常。

### 视觉验收

重新构建并部署到 ai-station 后，在真实 Teleop 页面观察至少 10 秒：

- 卡片和下方页面不随 ages/contact 刷新跳动；
- 页面无横向滚动条；
- MoveIt/Gazebo 两层能同时对照；
- 保存新鲜 Web UI 截图并实际查看。
- 截图同时确认顶层 Tabs 与 TCP frame ButtonGroup 具有清晰的选中态和 shadcn segmented 样式。

## 失败处理

- 若高度仍变化，先记录 bounding box 和变化来源，不盲目增加更多固定高度。
- 若小屏内容不可读，保持双层同时可见，允许纵向堆叠，不改为隐藏证据的 Tabs。
- 若 shadcn CLI 的变更会覆盖现有本地行为，先查看 `--dry-run`/`--diff`，手工合并所需官方结构并重新执行既有测试；不得静默覆盖。
- 若 Bun 不可用或版本探测失败，preflight 必须 fail fast，不得回退到系统 Node/npm 继续构建。
- 若 launch 找不到源码目录但 installed bundle 完整，可直接服务 installed bundle；若两者都无效，明确失败并给出 `web_source_dir` 修复提示。
