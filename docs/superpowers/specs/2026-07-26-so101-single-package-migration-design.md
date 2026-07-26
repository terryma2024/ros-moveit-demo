# SO-101 单 Package 迁移设计

## 1. 背景与目标

当前 SO-101 仿真资产位于 `/data/work/so101_lerobot_ws`，分散在以下三个 ROS 2 package：

- `lerobot_description`
- `lerobot_controller`
- `lerobot_moveit`

后续需要把 `panda_gazebo_demo` 的 pick-place 状态机迁移到 SO-101。为避免继续依赖独立工作区，也避免修改已经稳定运行的 Panda 实现，本设计在 `/data/work/ws_moveit/src` 新建一个自包含 package：

```text
so101_gazebo_demo
```

迁移分为两个阶段：

1. 将现有 SO-101 description、controller、MoveIt、Gazebo world、工具和测试扁平合并为单一 package，并独立构建和运行。
2. 在该 package 内复制 `panda_gazebo_demo` 的 pick-place 代码结构，再逐项替换 SO-101 的 adapter、配置和策略。两个实现分别跑通后，才允许抽取公共逻辑和重构。

本文完整定义第一阶段，并约束第二阶段的边界。

## 2. 设计原则

### 2.1 自包含

完成第一阶段后，仅 source `/data/work/ws_moveit/install/setup.zsh` 即可构建和运行 SO-101 仿真及 MoveIt。运行时和测试不得依赖：

- `/data/work/so101_lerobot_ws` 的 source/install 空间；
- `lerobot_description`、`lerobot_controller`、`lerobot_moveit` package；
- 指向旧工作区的绝对路径。

### 2.2 与 Panda 隔离

- 不修改 `src/panda_gazebo_demo` 的源码、配置和测试。
- 不把 SO-101 条件分支加入 Panda package。
- 第一阶段不复制或链接 Panda pick-place 状态机。
- 第二阶段采用代码复制，以便 SO-101 可以独立演化；公共逻辑抽取推迟到两个实现都通过各自验收之后。

### 2.3 保持已验证行为

迁移不得改变以下 SO-101 行为：

- table、pedestal、Coke 和 SO-101 的世界几何关系；
- `base_height=0.1899186`，使底座 mesh 最低面位于 pedestal 顶面 `z=0.22`；
- `so101_tcp` 定义和夹爪预开/接触几何计算；
- arm controller 与 gripper controller 的关节集合；
- MoveIt planning group、SRDF、joint limits、kinematics 和 controller mapping；
- Gazebo/RViz 默认视角与 GUI 分屏外观；
- Coke contact sensor 到 ROS `/coke/contacts` 的桥接。

## 3. 选择的方案

采用单 package 扁平合并，不保留嵌套 ROS package，也不建立 meta package。

```text
/data/work/ws_moveit/src/so101_gazebo_demo/
├── CMakeLists.txt
├── package.xml
├── LICENSE
├── README.md
├── config/
│   ├── initial_positions.yaml
│   ├── joint_limits.yaml
│   ├── kinematics.yaml
│   ├── moveit_controllers.yaml
│   ├── moveit.rviz
│   ├── pilz_cartesian_limits.yaml
│   ├── so101.srdf
│   └── so101_controllers.yaml
├── launch/
│   ├── so101_controller.launch.py
│   ├── so101_display.launch.py
│   ├── so101_gazebo.launch.py
│   └── so101_moveit.launch.py
├── meshes/so101/
├── rviz/
│   └── display.rviz
├── scripts/
│   ├── gripper_preopen_calc.py
│   └── tile_ai_station_guis.py
├── test/
│   ├── test_gripper_preopen_calc.py
│   ├── test_so101_launch_contract.py
│   ├── test_so101_pick_place_world.py
│   ├── test_so101_srdf.py
│   └── test_tile_ai_station_guis.py
├── urdf/
└── worlds/
    └── so101_pick_place.sdf
```

复制时明确排除：

- `.git/`
- `build/`
- `install/`
- `log/`
- `.pytest_cache/`
- `__pycache__/`
- `*.pyc`

## 4. Package 资源与依赖

### 4.1 Package 名称替换

所有内部资源引用统一到 `so101_gazebo_demo`：

- `package://lerobot_description/...` → `package://so101_gazebo_demo/...`
- `$(find lerobot_controller)/config/so101_controllers.yaml` → `$(find so101_gazebo_demo)/config/so101_controllers.yaml`
- `get_package_share_directory("lerobot_description")`、`get_package_share_directory("lerobot_controller")`、`get_package_share_directory("lerobot_moveit")` → `get_package_share_directory("so101_gazebo_demo")`
- `MoveItConfigsBuilder("so101", package_name="lerobot_moveit")` → `MoveItConfigsBuilder("so101", package_name="so101_gazebo_demo")`
- 夹爪几何计算器中的旧工作区默认绝对路径改为基于新 package share 或脚本相对路径解析。

迁移后使用静态扫描和安装后运行测试共同证明旧 package 名和旧工作区路径不再构成运行依赖。

### 4.2 CMake 安装边界

`CMakeLists.txt` 负责安装：

- `config/`
- `launch/`
- `meshes/`
- `rviz/`
- `urdf/`
- `worlds/`
- `scripts/gripper_preopen_calc.py`
- `scripts/tile_ai_station_guis.py`

第一阶段不添加 C++ target。第二阶段复制状态机时，才参照 `panda_gazebo_demo` 增加 `include/`、`src/`、可执行程序和 C++ 测试 target。

### 4.3 package.xml

新 `package.xml` 使用三个源 package 依赖的并集，并删除对三个 `lerobot_*` package 的依赖。至少覆盖：

- Xacro、URDF、robot_state_publisher；
- ros_gz_sim、ros_gz_bridge、gz_ros2_control；
- controller_manager 和 joint trajectory controller；
- RViz；
- MoveIt configs、move_group 和 controller manager；
- launch/launch_ros；
- ament CMake pytest 和 lint 测试依赖。

依赖以 `rosdep check` 和干净 overlay 构建结果为准，不保留仅由旧 package 拆分方式产生的内部依赖。

## 5. Launch 与数据流

### 5.1 Gazebo 启动链

```text
so101_gazebo.launch.py
  → package 内 so101.urdf.xacro
  → package 内 so101_controllers.yaml
  → package 内 so101_pick_place.sdf
  → robot_state_publisher
  → Gazebo create
  → controller spawners
  → /clock 与 /coke/contacts bridge
```

### 5.2 MoveIt 启动链

```text
so101_moveit.launch.py
  → package 内 URDF/Xacro
  → package 内 SRDF/kinematics/joint_limits/controller config
  → move_group
  → RViz
```

Gazebo 与 MoveIt 必须使用同一个 `base_height` 默认值和同一份 Xacro，防止 Planning Scene 中的机器人模型与物理模型产生高度偏差。

### 5.3 Controller 与 display 启动链

`so101_controller.launch.py` 和 `so101_display.launch.py` 继续保留，以保证原有的控制器启动和纯模型观察入口没有因 package 合并而丢失。两者的所有资源查找都改为新 package。

## 6. 测试策略

迁移遵循测试先行。先复制和改写测试，使其针对 `so101_gazebo_demo` 的期望目录及 package 名失败，再复制生产资源使其转绿。

### 6.1 静态与单元测试

- Xacro 可展开，mesh URI 全部指向 `so101_gazebo_demo`。
- base frame、mesh bottom 和 pedestal top 的几何关系保持一致。
- TCP、gripper named states 和 SRDF planning groups 保持一致。
- Gazebo/MoveIt launch 的公共参数和默认 `base_height` 一致。
- controller spawner、Coke contact bridge 和 world GUI 契约保持一致。
- 夹爪计算器对 `q_preopen`、`q_contact` 的现有结果保持一致。
- GUI 分屏脚本的窗口识别、EWMH payload、几何验证与幂等测试保持一致。
- 源码静态扫描不存在旧 package 名或旧工作区绝对路径。

### 6.2 Package 构建与测试

```bash
cd /data/work/ws_moveit
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_gazebo_demo --symlink-install
source install/setup.zsh
colcon test --packages-select so101_gazebo_demo
colcon test-result --verbose
```

由于工作区中已有 Panda 未提交测试修改，验证和提交必须限定到新 package；不得用清理、reset 或 checkout 处理这些已有修改。

### 6.3 自包含验证

在不 source `/data/work/so101_lerobot_ws/install/setup.zsh` 的新 shell 中验证：

- `ros2 pkg prefix so101_gazebo_demo` 指向 `/data/work/ws_moveit/install`；
- `xacro` 可以展开安装后的 URDF；
- Gazebo launch 能加载 mesh、controller config 和 world；
- MoveIt launch 能进入 ready 状态；
- `ros2 pkg prefix lerobot_description` 是否存在不影响上述结果；新 package 不引用它。

### 6.4 真实运行验收

按 ai-station GUI SOP 在 tmux 中 source `~/gui-env.zsh`，仅 source ROS Jazzy 与 `/data/work/ws_moveit/install/setup.zsh`，启动 Gazebo 与 MoveIt，然后验证：

- controller manager、arm controller、gripper controller 和 joint state broadcaster active；
- TF `world → base` 为 `z=0.1899186`；
- Gazebo 中 base mesh 与 pedestal 贴合；
- table、pedestal、SO-101、Coke 的场景关系和最终视角不变；
- RViz 与 Gazebo 左右分屏，无窗口遮挡；
- 截图作为实际 UI 证据归档。

## 7. 错误处理与回滚

- 构建、测试或运行验收失败时，不删除源 package，也不修改 Panda package。
- 新 package 的问题仅在 `src/so101_gazebo_demo` 内修复。
- 若旧 package 名扫描仍有命中，逐条区分运行依赖、测试说明和许可证归属；运行依赖必须清零。
- 若源工作区与复制结果行为不一致，以现有 `/data/work/so101_lerobot_ws` 的已验证运行结果为基线进行 A/B 对比。
- 本阶段不删除 `/data/work/so101_lerobot_ws`，它继续作为可回退参考。

## 8. 第二阶段边界

第一阶段全部验收通过后，第二阶段才开始复制 Panda pick-place 结构：

```text
include/pick_place/
src/pick_place/
src/nodes/
test/pick_place/
test/headless/
```

第二阶段的首要目标是结构一致和行为隔离，而不是立即抽象：

- 复制后使用 SO-101 自己的 namespace、target、link、joint、planning group、controller 和 gripper adapter；
- Panda 与 SO-101 分别构建、分别测试、分别运行；
- 不让 Panda target policy、Panda finger 语义或 attachment link 泄漏到 SO-101；
- 等固定位置 SO-101 pick-place 全流程及 recovery 场景通过后，再比较两个 package，识别可抽取的纯状态机、策略接口和通用 ROS adapter。

第二阶段需要独立设计与实施计划，不在第一阶段迁移中顺带执行。

## 9. 完成标准

第一阶段仅在以下条件全部满足时完成：

- `/data/work/ws_moveit/src/so101_gazebo_demo` 是一个可被 `colcon list` 识别的单一 ROS 2 package；
- package 自包含，不依赖旧 SO-101 工作区或三个 `lerobot_*` package；
- package 构建和全部 package 测试通过；
- Gazebo、MoveIt、controller 和 display 入口可从新 package 启动；
- 真实 TF、控制器、Gazebo 场景和 GUI 截图验收通过；
- `panda_gazebo_demo` 及其已有未提交修改保持不变；
- 第一阶段没有复制 Panda pick-place 状态机，也没有提前抽取公共逻辑。
