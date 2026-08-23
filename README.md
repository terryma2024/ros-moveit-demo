# SO-101 MoveIt 仿真工作区

本仓库是面向 SO-101 机械臂的 ROS 2 Jazzy / MoveIt 2 仿真工作区，提供 Gazebo Harmonic、MuJoCo、可视化 Teleop 和 pick-place 示例。当前推荐入口是统一 Python 包 `so101_demo_py`；仓库同时保留基于共享状态机的 C++ Gazebo 实现，以及 Panda 和固定目标 Pose 示例。

## 主要能力

- 使用同一套 Python 应用层在 MuJoCo 与 Gazebo 中运行 SO-101 pick-place。
- 通过 MoveIt 2 和 `ros2_control` 完成规划、轨迹执行与场景管理。
- 提供统一的 Planning Scene、相机预设和仿真世界重置命令。
- 提供后端无关的 SO-101 Teleop Web UI。
- 通过 `pick_place_common` 复用 C++ 工作流基础设施，并保留 SO-101、Panda 示例。

## 项目架构

```text
操作员 / Teleop Web UI
          |
          v
so101_demo_py 或机器人专用 C++ 包
          |
          v
      MoveIt 2 + ros2_control
          |
          v
   Gazebo Harmonic 或 MuJoCo
```

- `so101_demo_py` 是 SO-101 Python 仿真的统一入口，拥有 MuJoCo/Gazebo launcher、公共 CLI、配置和资源。
- `so101_teleop` 提供仿真后端选择、ROS 2 服务端和 Web UI。
- `pick_place_common` 提供机器人无关的 C++ pick-place 核心；机器人资源和策略留在各自的 C++ 包中。
- `so101_mujoco_support` 提供 SO-101 MuJoCo 支持资源；固定版本的 `mujoco_ros2_control` fork 作为独立 overlay 构建。

更完整的边界说明见 [Python 架构](docs/pick-place-python-architecture.md) 和 [C++ pick-place 架构](docs/pick-place-architecture.md)。

## 目录结构

```text
ws_moveit/
├── src/
│   ├── so101_demo_py/             # 统一 SO-101 Python 仿真应用
│   ├── so101_teleop/              # Teleop 服务端、Web UI 与后端配置
│   ├── so101_mujoco_support/      # SO-101 MuJoCo 支持资源
│   ├── pick_place_common/         # 机器人无关的 C++ 工作流核心
│   ├── so101_gazebo_demo_cpp/     # SO-101 Gazebo / MoveIt C++ 示例
│   ├── panda_gazebo_demo_cpp/     # Panda Gazebo / MoveIt C++ 示例
│   └── fixed_pose_goal/           # Panda 固定目标 Pose 示例
├── docs/                          # 架构、集成、运行与实验文档
├── scripts/                       # 依赖安装和维护脚本
└── third_party/
    └── mujoco_ros2_control/       # 固定版本的 fork submodule
```

`build/`、`install/` 和 `log/` 是 colcon 生成目录，不属于源码结构。

## 环境要求

- Ubuntu 24.04 与 ROS 2 Jazzy；Apple Silicon macOS 将源码安装前缀软链为 `/opt/ros/jazzy`
- MoveIt 2
- Gazebo Harmonic 及 ROS 2 bridge/control 组件
- `colcon`、`rosdep` 和 Zsh
- MuJoCo 路径所需的依赖由仓库脚本安装并验证
- Teleop Web UI 需要 Bun；详见 Teleop 使用文档

## 构建

先安装工作区声明的 ROS 依赖：

```bash
cd /data/work/ws_moveit
source /opt/ros/jazzy/setup.zsh
rosdep install --from-paths src --ignore-src -r -y
```

完整构建（包括 MuJoCo overlay）使用固定依赖安装器：

```bash
zsh scripts/install-mujoco-ros2-control.zsh --init-submodule
source /data/work/ws_mujoco_ros2_control_fork/install/setup.zsh
colcon build --base-paths src --symlink-install
source install/setup.zsh
```

安装器会按 `src/so101_demo_py/config/mujoco/dependency-lock.yaml` 初始化、构建并验证 fork。若只使用某个 Gazebo/C++ 示例，可按包构建，例如：

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --symlink-install --packages-up-to so101_gazebo_demo_cpp so101_teleop
source install/setup.zsh
```

每次打开新终端后，都需要按所用后端重新 source ROS underlay、依赖 overlay 和本工作区 overlay。

## 运行

以下命令均假定已完成构建并 source 对应 overlay。

### 统一 SO-101 Python 示例

两个 pick-place launcher 默认使用 `run_mode:=dry_run execute:=false`，适合先检查启动图和配置：

```bash
ros2 launch so101_demo_py so101_mujoco_pick_place.launch.py
ros2 launch so101_demo_py so101_gazebo_pick_place.launch.py
```

确认只连接仿真环境后，可显式启用执行：

```bash
ros2 launch so101_demo_py so101_mujoco_pick_place.launch.py \
  run_mode:=execute execute:=true

ros2 launch so101_demo_py so101_gazebo_pick_place.launch.py \
  run_mode:=execute execute:=true
```

若只需要启动仿真栈而不运行 pick-place，可使用：

```bash
ros2 launch so101_demo_py so101_mujoco.launch.py
ros2 launch so101_demo_py so101_gazebo.launch.py
```

### 公共仿真命令

在对应仿真栈运行后，通过 `--backend mujoco|gazebo` 选择后端：

```bash
ros2 run so101_demo_py scene_setup --backend gazebo setup
ros2 run so101_demo_py camera_preset --backend gazebo overview
ros2 run so101_demo_py teleop_reset --backend gazebo --session-id operator-reset-001
```

### Teleop Web UI

先启动兼容的仿真栈，再以相同 session 启动 Teleop：

```bash
ros2 launch so101_teleop so101_teleop.launch.py \
  backend:=gazebo_py \
  bind_address:=127.0.0.1 \
  simulation_session_id:=<session-id>
```

Teleop 也支持 `mujoco_py` 和 `gazebo_cpp` profile。网络访问、安全边界和 Web bundle 构建方式见 [Teleop Web UI 指南](src/so101_teleop/docs/so101-teleop-web-ui.md)。

### C++ 与示例包

```bash
# SO-101 Gazebo / MoveIt C++ 仿真
ros2 launch so101_gazebo_demo_cpp so101_gazebo.launch.py

# Panda Gazebo / MoveIt 示例
ros2 launch panda_gazebo_demo_cpp panda_gazebo.launch.py

# Panda 固定目标 Pose 示例
ros2 launch fixed_pose_goal fixed_pose_goal.launch.py
```

## 文档索引

- [统一 SO-101 Python 包](src/so101_demo_py/README.md)
- [Apple Silicon ROS 2 Jazzy 与 SO-101 MuJoCo](docs/guides/macos-apple-silicon-ros2-jazzy-so101-mujoco.md)
- [Python pick-place 架构](docs/pick-place-python-architecture.md)
- [SO-101 MuJoCo ROS 2 集成指南](docs/guides/so101-mujoco-ros2-integration-guide.md)
- [C++ pick-place 架构](docs/pick-place-architecture.md)
- [C++ launch 参数与安全合同](docs/pick-place-launch-parameters.md)
- [SO-101 Gazebo C++ 包](src/so101_gazebo_demo_cpp/README.md)
- [Teleop Web UI 指南](src/so101_teleop/docs/so101-teleop-web-ui.md)
- [Panda Gazebo C++ 包](src/panda_gazebo_demo_cpp/README.md)

## 安全边界

本仓库当前的 SO-101 操作入口仅面向仿真。Python real-arm adapter 保持 fail-closed，仓库没有可直接驱动真实 SO-101 的 launcher。不要把上述仿真执行命令用于真实机械臂；真实硬件接入需要独立的安全设计、限位、急停和验收流程。
