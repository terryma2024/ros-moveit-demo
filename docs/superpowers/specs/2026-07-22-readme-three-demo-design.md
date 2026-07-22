# README 三 Demo 重构设计

## 背景

仓库根目录的 `README.md` 目前只介绍 `fixed_pose_goal`，已经不能反映仓库同时承载多个 MoveIt 2 机械臂示例的定位。

仓库预期包含三个独立 Demo：

1. `src/fixed_pose_goal`：固定目标 Pose 规划与执行。
2. `src/panda_gazebo_demo`：Panda 机械臂、Gazebo 与 MoveIt 2 集成仿真。
3. `src/so_arm_gazebo_demo`：SO-ARM101 机械臂与 Gazebo 集成仿真，当前处于规划阶段。

## 目标

- 将根 README 从单一包说明改为整个仓库的入口文档。
- 让读者一眼看清三个 Demo 的用途和当前状态。
- 为两个已存在的 Demo 提供与源码一致的入口信息。
- 明确区分已实现、开发中和规划中的内容，避免把未来能力写成现状。
- 保留现有 `fixed_pose_goal` 中仍然准确的 Pose、运行方式、安全提醒和 IK 多解说明。

## 非目标

- 不创建 `so_arm_gazebo_demo` 包或任何实现代码。
- 不修改 ROS 2 节点、launch 文件、构建配置或运行行为。
- 不为规划中的 Demo 编造依赖、可执行程序或启动命令。
- 不把每个 ROS 2 executable 错称为独立 Demo。

## README 信息架构

### 1. 仓库概览

标题使用“ROS 2 MoveIt 机械臂 Demo”。简介说明本仓库通过多个渐进式示例展示 MoveIt 2 从固定目标规划到 Gazebo 机械臂仿真的使用方式。

紧接着使用状态表列出：

| Demo | 状态 | 定位 |
| --- | --- | --- |
| `fixed_pose_goal` | 已实现 | 固定目标 Pose、RViz Goal State 同步、规划与执行 |
| `panda_gazebo_demo` | 开发中 | Panda、Gazebo、MoveIt 2 与抓取状态机 |
| `so_arm_gazebo_demo` | 规划中 | SO-ARM101 与 Gazebo 仿真 |

### 2. 项目结构

目录树以三个 `src/` 子目录为核心。对尚未落盘的 `src/so_arm_gazebo_demo` 使用“规划中”注释，避免读者误以为检出仓库后该目录已经存在。

### 3. Demo 章节

每个 Demo 使用独立的二级章节。

`fixed_pose_goal` 章节保留：

- 两个现有 ROS 2 节点的职责。
- 固定目标 Pose 和 RViz Marker 名称。
- 包级构建与运行命令。
- 七自由度 Panda 机械臂可能出现多个 IK 解的说明。

`panda_gazebo_demo` 章节基于当前源码说明：

- `panda_gazebo.launch.py` 启动 Gazebo、Panda、控制器、MoveIt `move_group`、Planning Scene 与 RViz。
- `headless:=true` 可使用无界面模式。
- 包内现有 executable：`planning_scene_setup`、`pre_grasp_plan`、`attach_and_lift_demo`、`pick_place_state_machine`。
- 只提供源码能够支持的构建和启动入口，不宣称抓取流程已经完整实现。

`so_arm_gazebo_demo` 章节只说明：

- 目标机械臂为 SO-ARM101。
- 目标环境为 Gazebo 仿真并计划接入 MoveIt 2。
- 当前状态为规划中，目录、依赖和运行命令将在实现后补充。

### 4. 公共说明

- 环境要求以 ROS 2 Jazzy、MoveIt 2、Gazebo、`colcon` 和 C++17 为主，并注明不同 Demo 的依赖不同。
- 构建说明同时给出按包构建和构建整个工作区的方式。
- 安全提醒覆盖仿真和潜在实机使用；明确 `fixed_pose_goal` 会在规划成功后调用 `execute()`。

## 准确性约束

- Demo 名称、路径、launch 文件和 executable 必须与当前仓库内容一致。
- “状态”描述必须使用“已实现”“开发中”“规划中”，不使用容易误解为完成度承诺的措辞。
- SO-ARM101 只写方向和边界，不写未经实现验证的命令。
- README 变更后用文本搜索核对三个 Demo 都出现，并用 `git diff --check` 检查 Markdown 空白问题。

## 验收标准

1. README 的首屏能识别三个独立 Demo 及其状态。
2. `fixed_pose_goal` 的现有有效信息没有丢失。
3. `panda_gazebo_demo` 的入口与当前 CMake 和 launch 文件一致。
4. `so_arm_gazebo_demo` 明确标为规划中，且没有虚构运行方式。
5. README 不再把整个仓库描述为单一固定 Pose 示例。
