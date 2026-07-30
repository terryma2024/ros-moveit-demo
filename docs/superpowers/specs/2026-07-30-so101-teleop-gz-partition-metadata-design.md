# SO-101 Teleop ROS/Gazebo Environment Metadata Design

## Goal

在 Teleop Web UI 顶部动态 metadata 区显示当前 Teleop 运行进程实际使用的 `ROS_DOMAIN_ID` 与 `GZ_PARTITION`，并通过独立 `Environment` Tab 提供一组受控的 ROS/Gazebo 环境诊断信息，避免操作者依赖 shell 默认值、历史启动命令或静态文档判断当前运行边界。

## Architecture and data flow

Teleop server 在进程启动时从自身环境读取固定 allowlist，并将结果写入 `TelemetrySnapshot.environment`。该结构通过现有 `/snapshot` 与 WebSocket telemetry 通道传播；不增加独立 endpoint，也不让浏览器推断、读取 `/proc` 或写死运行值。

前端 `TelemetrySnapshot` 类型接受环境 map。环境信息只在独立 Environment Tab 显示；页眉不重复显示 `ROS_DOMAIN_ID` 与 `GZ_PARTITION`，避免动态 metadata 过长。缺失值显示 `—`。

顶层 Tabs 增加第八项 `Environment`。对应 panel 使用结构化表格按固定顺序展示：

1. `ROS_DOMAIN_ID`
2. `ROS_DISTRO`
3. `ROS_VERSION`
4. `ROS_PYTHON_VERSION`
5. `ROS_AUTOMATIC_DISCOVERY_RANGE`
6. `AMENT_PREFIX_PATH`
7. `COLCON_PREFIX_PATH`
8. `GZ_PARTITION`
9. `GZ_CONFIG_PATH`
10. `GZ_SIM_RESOURCE_PATH`
11. `GZ_SIM_SYSTEM_PLUGIN_PATH`
12. `PYTHONPATH`
13. `LD_LIBRARY_PATH`

长值在单元格内截断或换行，完整内容通过 tooltip 查看，并提供逐项 Copy 按钮。表格可在自身容器内滚动，但不得造成页面横向 overflow。缺失变量显示 `—`。

## Safety and compatibility

- 字段只读，不允许 Web UI 修改 ROS domain、Gazebo partition 或其他环境变量。
- 继续由 launch/tmux 环境决定实际运行环境。
- 后端只暴露上述固定 allowlist；不得序列化完整 `os.environ`，即使其中出现 token、proxy、credential 或其他未知变量也不得下发。
- 缺失字段具有安全的展示回退，兼容短暂连接到旧 snapshot 的情况。
- 不改变 ROS domain、Gazebo、MoveIt、lease 或 command 执行行为。

## Verification

1. Python RED/GREEN：snapshot 返回 allowlist 中设置的精确值、缺失项为空，并证明非允许变量不会出现在响应中。
2. Vitest RED/GREEN：`ConnectionHeader` 不重复显示 ROS domain 与 GZ partition，同时保持标题、READY badge、lease 按钮顺序不变；Environment panel 固定顺序显示全部 13 项并可复制完整值。
3. Playwright：mock telemetry 的两个关键值仅在 Environment Tab 可见；长值不造成页面水平 overflow，复制按钮工作且无 console error。
4. Bun frontend test、Playwright、production build 与 Teleop Python 定向测试全部通过。
5. 重新 colcon build/source，仅重启现有 Teleop tmux session；从 live `/snapshot` 验证 `ROS_DOMAIN_ID=55`、`GZ_PARTITION=so101_teleop_live_final` 及完整 allowlist 边界，并用新鲜截图实际确认 Environment Tab。

## Non-goals

- 不增加环境变量编辑器或切换按钮。
- 不重启或复制 Gazebo/MoveIt stack。
- 不执行 Attach、Execute 或其他机器人动作。
