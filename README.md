# ROS 2 MoveIt 固定目标 Pose 示例

这是一个基于 ROS 2 Jazzy 和 MoveIt 2 的 C++ 示例项目，用于：

- 将 Panda 机械臂的 `panda_link8` 设置到固定目标 Pose；
- 同步更新 RViz MotionPlanning Display 中的 Query Goal State；
- 监听 RViz 交互式目标 Marker 的 Pose 变化并打印；
- 使用一个 launch 文件同时启动上述两个节点。

## 环境要求

- ROS 2 Jazzy
- MoveIt 2
- Panda MoveIt 示例配置或等价的 Panda 机械臂配置
- `colcon`
- C++17 编译器

主要 ROS 2 依赖：

- `rclcpp`
- `geometry_msgs`
- `visualization_msgs`
- `moveit_ros_planning_interface`
- `launch_ros`

## 项目结构

```text
src/fixed_pose_goal/
├── CMakeLists.txt
├── package.xml
├── launch/
│   └── fixed_pose_goal.launch.py
└── src/
    ├── fixed_pose_goal.cpp
    └── interactive_marker_pose_feedback.cpp
```

## 节点说明

### fixed_pose_goal

该节点执行以下操作：

1. 创建 `MoveGroupInterface`，规划组为 `panda_arm`；
2. 为 `panda_link8` 设置固定目标 Pose；
3. 向 RViz Interactive Marker feedback topic 发布 `POSE_UPDATE`，同步 Query Goal State；
4. 规划并执行机械臂轨迹。

当前目标 Pose 位于 `world` 坐标系：

```yaml
position:
  x: 0.770
  y: 0.165
  z: 0.472
orientation:
  x: 0.466
  y: -0.379
  z: 0.798
  w: 0.053
```

RViz 目标 Marker 名称为：

```text
EE:goal_panda_link8
```

### interactive_marker_pose_feedback

该节点监听：

```text
/rviz_moveit_motion_planning_display/robot_interaction_interactive_marker_topic/feedback
```

当收到 `visualization_msgs/msg/InteractiveMarkerFeedback` 的 `POSE_UPDATE` 事件时，打印：

- Marker 名称；
- Control 名称；
- 坐标系；
- 位置 XYZ；
- 四元数 XYZW。

## 构建

在工作区根目录执行：

```bash
source /opt/ros/jazzy/setup.bash
colcon build --packages-select fixed_pose_goal
source install/setup.bash
```

如果使用 zsh：

```zsh
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select fixed_pose_goal
source install/setup.zsh
```

## 运行

确保 MoveIt、`move_group` 和带有 MotionPlanning Display 的 RViz 已经启动。

同时启动两个节点：

```bash
ros2 launch fixed_pose_goal fixed_pose_goal.launch.py
```

也可以分别启动：

```bash
ros2 run fixed_pose_goal interactive_marker_pose_feedback
ros2 run fixed_pose_goal fixed_pose_goal
```

## 安全提醒

`fixed_pose_goal` 在规划成功后会立即调用 `execute()` 执行轨迹。连接真实机械臂时，请在运行前确认：

- 目标 Pose 位于机械臂安全工作空间；
- 规划场景中的碰撞模型正确；
- 周围没有人员或障碍物；
- 急停设备可用；
- 速度和加速度缩放符合现场安全要求。

当前代码中的最大速度和加速度缩放系数均为 `0.1`，但这不能替代实际系统的安全措施。

## 关于 RViz Goal State 与执行结果

Panda 是七自由度机械臂。同一个六自由度末端 Pose 可能对应多组关节角，因此 RViz Query Goal State 和规划器最终选择的关节姿态可能不同。若末端位置与方向基本重合，仅肘部或其他关节姿态不同，这是冗余机械臂产生不同 IK 解的正常现象。
