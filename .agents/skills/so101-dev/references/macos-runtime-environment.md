# macOS SO-101 运行环境排查

## 读取条件

只在以下条件同时成立时读取本文件：

- 当前主机是 Apple Silicon macOS；
- SO-101 启动或测试失败指向 Python、ROS overlay、package prefix、SIP、`DYLD_*` 或
  `@rpath/*.dylib`。

Linux/ai-station 不使用这里的命令。macOS 上的控制器行为、MoveIt 规划、MuJoCo 物理或视觉
问题，如果环境 doctor 已通过，也回到 `so101-dev` 的普通分层取证流程。

## 权威文档和入口

| 内容 | 文件 |
|---|---|
| 完整安装、启动、故障说明和跨 Mac 核对项 | [`docs/guides/macos-apple-silicon-ros2-jazzy-so101-mujoco.md`](../../../../docs/guides/macos-apple-silicon-ros2-jazzy-so101-mujoco.md) |
| 统一命令入口 | [`scripts/so101-macos.zsh`](../../../../scripts/so101-macos.zsh) |
| 固定环境 doctor 实现 | [`scripts/so101_macos_runtime_contract.py`](../../../../scripts/so101_macos_runtime_contract.py) |
| dylib farm 生成器 | [`scripts/setup-macos-ros-dylib-farm.zsh`](../../../../scripts/setup-macos-ros-dylib-farm.zsh) |
| 实施边界和未完成门禁 | [`docs/superpowers/plans/2026-09-21-so101-macos-runtime-contract.md`](../../../../docs/superpowers/plans/2026-09-21-so101-macos-runtime-contract.md) |
| 当前主机实验与证据结论 | [`docs/experiments/so101-macos-runtime-contract-experiment-ledger.md`](../../../../docs/experiments/so101-macos-runtime-contract-experiment-ledger.md) |

指南是操作说明，实验账本是证据记录。不要把账本中的一次成功当成另一台 Mac 已通过验收。

## 固定契约

所有目标 Mac 使用相同逻辑路径：

| 用途 | 路径 |
|---|---|
| ROS 根目录 | `/opt/ros2_jazzy` |
| ROS install | `/opt/ros2_jazzy/install` |
| ROS Python | `/opt/ros2_jazzy/.venv/bin/python` |
| 临时目录 | `/tmp` |
| 工作数据根目录 | `/opt/data` |
| 锁定 fork overlay | `/opt/data/so101/runtime/fork/current` |
| 项目 overlay | `/opt/data/so101/workspace/install` |
| dylib farm | `/opt/ros2_jazzy/dylib_farm/current` |

物理 ROS 目录可以位于不同用户的 home 下，但 `/opt/ros2_jazzy` 这个逻辑入口必须一致。
不要把 `/Users/<name>` 写进代码或测试。

## 使用方法

先做只读基础检查：

```zsh
uname -s
uname -m
ls -ld /opt/ros2_jazzy /opt/data /tmp
readlink /opt/ros2_jazzy
scripts/so101-macos.zsh doctor --base
```

`doctor --base` 失败时先对齐固定路径、CPython 3.11 和写权限，不要启动 ROS stack。需要创建
或修改 `/opt` 下的链接时，把准确命令交给用户执行；不要自行假设 sudo 权限。

基础契约通过后，准备固定 overlay 和 dylib farm：

```zsh
scripts/so101-macos.zsh prepare
scripts/so101-macos.zsh doctor --json
```

完整 doctor 必须真实导入 `rclpy`、加载关键 dylib，并核对 package prefix。不要用“文件存在”
代替加载成功。

启动 task station：

```zsh
scripts/so101-macos.zsh launch \
  so101_demo_py so101_mujoco_task_station.launch.py \
  headless:=false sensor_rendering:=true include_teleop:=false
```

检查控制器、MoveIt service 和 action：

```zsh
scripts/so101-macos.zsh run \
  so101_demo_py motion_stack_ready --timeout-s 90
```

外部必需环境变量是 0 个。唯一接受的可选变量是 `ROS_DOMAIN_ID`，范围为 0 到 232，默认值
为 0：

```zsh
ROS_DOMAIN_ID=225 scripts/so101-macos.zsh doctor --json
```

不要把裸 `ros2 launch`、direnv 或手工拼接的 `DYLD_LIBRARY_PATH` 当作生产启动前提。

## 两个常见 dylib 边界

- `@rpath/librosidl_typesupport_c.dylib` 通常由 ROS Python、消息或 service 类型支持加载，可能
  在 launch 文件解析或节点创建前失败。
- `@rpath/libhardware_interface.dylib` 属于 `ros2_control_node` 的依赖链，controller manager
  加载 `mujoco_ros2_control/MujocoSystemInterface` 时需要它。

macOS SIP 可能在受保护脚本边界移除 `DYLD_*`。如果日志出现上述错误，先运行完整 doctor；
不要根据下游的 controller timeout 直接修改控制器代码。

## Python package test

macOS 上的 package test 必须使用固定 Python，并在当前 zsh 内按固定顺序加载 overlay：

```zsh
source /opt/ros2_jazzy/install/setup.zsh
source /opt/ros2_jazzy/extra_ws/install/setup.zsh
source /opt/data/so101/runtime/fork/current/setup.zsh
source /opt/data/so101/workspace/install/setup.zsh
export DYLD_LIBRARY_PATH=/opt/ros2_jazzy/dylib_farm/current

/opt/ros2_jazzy/.venv/bin/python -c 'import rclpy; print(rclpy.__file__)'
/opt/ros2_jazzy/.venv/bin/python -m pytest \
  src/so101_demo_py/test \
  --junitxml="$TASK_EVIDENCE/tests/so101_demo_py.xml"
```

`TASK_EVIDENCE` 必须位于本 task 已登记的唯一 evidence root。测试必须实际收集非零用例。
pytest 收集前就因 `@rpath` 或模块导入失败时，记为 runner/environment failure，不记成代码
RED；导入成功后出现 assertion failure 才按测试失败处理。只运行定向契约测试时，如果 ROS 的
pytest plugin 干扰无关文件收集，可以为该次定向测试设置 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`；
普通整包 package gate 不使用这个选项隐藏已登记的插件或测试。

## 跨 Mac 验证

每台目标 Mac 都保存一次 `prepare`、`doctor --json` 和真实 task-station `READY` 证据。比较
doctor JSON 时核对 Darwin/arm64、CPython 3.11、逻辑路径、farm manifest、必需 dylib 和 package
prefix。`resolved` 路径可以因用户名不同而变化。

同一台 Mac 上运行两套污染 HOME/PATH/ROS/DYLD 环境，只能验证环境清理逻辑；不能代替第二台
物理 Mac。未执行的主机明确写 `NOT_RUN`。
