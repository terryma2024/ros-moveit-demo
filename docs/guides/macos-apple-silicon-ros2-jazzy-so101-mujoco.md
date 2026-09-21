# Apple Silicon macOS：ROS 2 Jazzy 与 SO-101 MuJoCo

本文记录 SO-101 在 Apple Silicon macOS 上的固定运行契约。目标很直接：新终端无需手工
`source` 多层 overlay，也不用临时拼接动态库路径，执行同一个脚本就能检查、构建和启动。

## 固定运行契约

所有 Mac 都使用下面这组逻辑路径：

| 用途 | 固定路径 |
| --- | --- |
| ROS 2 工作区根目录 | `/opt/ros2_jazzy` |
| ROS 2 安装前缀 | `/opt/ros2_jazzy/install` |
| ROS Python | `/opt/ros2_jazzy/.venv/bin/python` |
| 临时目录 | `/opt/data/tmp` |
| SO-101 数据与构建目录 | `/opt/data` |
| 动态库聚合目录 | `/opt/ros2_jazzy/dylib_farm/current` |
| 锁定 MuJoCo fork overlay | `/opt/data/so101/runtime/fork/current` |
| 项目 overlay | `/opt/data/so101/workspace/install` |

物理目录可以放在用户目录，但上述逻辑路径不能随机器变化。例如当前机器使用：

```zsh
sudo mkdir -p /opt
sudo ln -s "$HOME/ros2_jazzy" /opt/ros2_jazzy
```

若链接已经存在，先检查，不要直接覆盖：

```zsh
ls -ld /opt/ros2_jazzy
readlink /opt/ros2_jazzy
```

`/opt/data` 必须存在，并且当前用户可写。`prepare` 会创建权限为 `0700` 的
`/opt/data/tmp`；后续的启动和测试都使用这个固定临时目录。

## 统一入口

首次配置或依赖更新后，在仓库根目录运行：

```zsh
scripts/so101-macos.zsh prepare
```

`prepare` 会依次完成这些工作：

1. 检查 Darwin/arm64、固定软链接、CPython 3.11 和目录权限。
2. 按 dependency lock 构建并测试 `mujoco_ros2_control` fork。
3. 构建 `so101_mujoco_support`、`so101_teleop` 和 `so101_demo_py`。
4. 从 ROS underlay、依赖 overlay、fork overlay 和项目 overlay 生成 dylib farm。
5. 用真实 `dlopen` 加载关键动态库，并核对各 ROS package prefix。

只检查当前环境，不构建：

```zsh
scripts/so101-macos.zsh doctor --json
```

完整检查通过时，输出中的 `status` 为 `PASS`。回执同时记录逻辑路径、解析后的物理路径、
Python ABI、farm manifest、关键动态库和 package prefix，便于比较不同 Mac 的运行前提。

## 启动程序

启动 MuJoCo task station：

```zsh
scripts/so101-macos.zsh launch \
  so101_demo_py so101_mujoco_task_station.launch.py \
  headless:=false sensor_rendering:=true include_teleop:=false
```

检查控制器、MoveIt service 和 action 是否就绪：

```zsh
scripts/so101-macos.zsh run \
  so101_demo_py motion_stack_ready --timeout-s 90
```

普通 ROS 可执行程序也统一从该入口运行：

```zsh
scripts/so101-macos.zsh run so101_demo_py <executable> [arguments...]
```

不要把裸 `ros2 launch` 作为 macOS 的生产启动方式。统一脚本会清理继承环境、按固定顺序加载
overlay，并用下面的显式调用链跨过 macOS SIP 边界：

```text
/opt/ros2_jazzy/.venv/bin/python
  /opt/ros2_jazzy/install/ros2cli/bin/ros2
```

退出时向启动 owner 发送一次 `Ctrl-C`。不要向整个进程组重复发送 SIGINT；`ros2 launch`
会负责向子进程转发并完成清理。

## 最小环境变量

外部必需环境变量是 **0 个**。脚本会使用 `/usr/bin/env -i` 建立干净环境，并自行设置
`PATH`、`VIRTUAL_ENV`、`PYTHONNOUSERSITE`、`TMPDIR`、`TMP`、`TEMP`、`ROS_HOME`、
`ROS_LOG_DIR` 和动态库路径。

唯一允许由调用者传入的可选变量是：

```zsh
ROS_DOMAIN_ID=225 scripts/so101-macos.zsh doctor --json
```

`ROS_DOMAIN_ID` 必须是 0 到 232 的整数，默认值为 0。`PYTHONPATH`、`PYTHONHOME`、
`AMENT_PREFIX_PATH`、`CMAKE_PREFIX_PATH`、`COLCON_PREFIX_PATH` 和所有继承的 `DYLD_*`
都会被丢弃，避免不同终端或 IDE 污染启动结果。

`.envrc.example` 只用于交互式开发。程序启动和验收仍应使用 `scripts/so101-macos.zsh`，不能把
direnv 当成运行前提。

## 两个常见的 `@rpath` 报错

`@rpath/librosidl_typesupport_c.dylib` 通常在 ROS Python 启动阶段出现。`rclpy` 导入消息和
service 类型支持时就需要它，因此报错可能发生在 launch 文件刚开始解析、节点尚未创建的时候。

`@rpath/libhardware_interface.dylib` 由 `ros2_control_node` 需要。controller manager 加载
`mujoco_ros2_control/MujocoSystemInterface` 插件时会进入这条依赖链，所以它往往在仿真窗口出现
前后才暴露。

两者不是“某个 Python 文件缺包”，而是源码 ROS 的 Mach-O 动态库分散在多个 install prefix，
加上 SIP 会在受保护脚本边界移除 `DYLD_LIBRARY_PATH`。本项目采用两层处理：

- C++ 安装目标保留 loader-relative rpath。
- `scripts/setup-macos-ros-dylib-farm.zsh` 将各 overlay 的 `.dylib` 汇总到一个固定目录。

farm 对同名库采用明确的 overlay 顺序，后加载的 prefix 胜出，并把每次覆盖的来源路径和 SHA-256
写入 `.overrides.tsv`。`current` 只在新 run 完整生成后原子切换。

遇到类似报错时不要手工追加一长串目录，直接运行：

```zsh
scripts/so101-macos.zsh prepare
scripts/so101-macos.zsh doctor --json
```

`doctor` 会真实加载以下三项，而不只是检查文件是否存在：

```text
libcontrol_toolbox.dylib
libhardware_interface.dylib
librosidl_typesupport_c.dylib
```

## fork 构建与跨平台测试

macOS 安装器从 clean submodule 构建 dependency lock 指定的精确提交，并验证它同时包含官方
0.1.0 与本地 r11 lineage。构建产物放在提交号对应的独立目录中；只有完整测试通过后才写入
`so101-locked-commit.txt` 并发布 `fork/current`。

macOS 测试有一个额外限制：colcon 生成包级测试环境时会经过 `/bin/sh`，SIP 会再次移除
`DYLD_*`。因此安装器在提供 `SO101_TEST_DYLIB_FARM` 时直接调用 `ctest`，最后仍由
`colcon test-result` 汇总。Linux 没有该 farm 参数，继续使用标准 `colcon test`。测试代码通过
注入临时根目录和平台信息验证 Linux/macOS 分支，不依赖开发者的真实用户目录。

如需单独运行安装器，路径可以显式传入：

```zsh
SO101_WORKSPACE_DIR=/opt/data/so101/runtime/fork/runs/<commit> \
SO101_ROS_UNDERLAY=/opt/ros2_jazzy/install \
SO101_ROS_DEPENDENCY_OVERLAY=/opt/ros2_jazzy/extra_ws/install \
SO101_TEST_DYLIB_FARM=/opt/data/so101/runtime/bootstrap-dylib-farm/current \
SO101_PYTHON=/opt/ros2_jazzy/.venv/bin/python \
SO101_COLCON=/opt/ros2_jazzy/.venv/bin/colcon \
SO101_ROS2=/opt/ros2_jazzy/install/ros2cli/bin/ros2 \
scripts/install-mujoco-ros2-control.zsh
```

日常使用不需要执行这段命令，`prepare` 会自动完成同样的工作。

## 运行 `so101_demo_py` 全量测试

测试仍使用固定 Python、固定临时目录和同一组 overlay。八进程并行门禁还需要项目 `test`
extra 中锁定的 `pytest-xdist==3.8.0`：

```zsh
/opt/ros2_jazzy/.venv/bin/python -m pip install 'src/so101_demo_py[test]'

source /opt/ros2_jazzy/install/setup.zsh
source /opt/ros2_jazzy/extra_ws/install/setup.zsh
source /opt/data/so101/runtime/fork/current/setup.zsh
source /opt/data/so101/workspace/install/setup.zsh
export DYLD_LIBRARY_PATH=/opt/ros2_jazzy/dylib_farm/current
export TMPDIR=/opt/data/tmp TMP=/opt/data/tmp TEMP=/opt/data/tmp

/opt/ros2_jazzy/.venv/bin/python -m pytest -n 8 --dist loadscope \
  --basetemp=/opt/data/tmp/pytest-<unique-run-id> \
  src/so101_demo_py/test \
  --junitxml=/tmp/so101-demo-py-pytest.xml
```

每次运行都要为 `--basetemp` 换一个尚不存在的短路径，避免并行 worker 读到旧状态。普通
package gate 默认排除标记为 `explicit_ml` 的 Torch/SAM 集成用例，并且只收集
`src/so101_demo_py/test/`，不包含 `benchmark_test/`。需要单独检查 ML 用例时运行：

```zsh
/opt/ros2_jazzy/.venv/bin/python -m pytest -m explicit_ml \
  src/so101_demo_py/test/test_sam_decoder_runtime.py
```

如果 pytest 在收集测试前就因 ROS overlay 或 dylib 导入失败退出，应先修复环境，不要把它记成
代码回归。

## 在另一台 Mac 上验证

先对齐固定路径和权限，再执行：

```zsh
scripts/so101-macos.zsh prepare
scripts/so101-macos.zsh doctor --json > /tmp/so101-macos-runtime.json
```

比较两台机器的 JSON 时，至少核对：

- `platform.system` 为 `Darwin`，`platform.machine` 为 `arm64`。
- Python 为 CPython 3.11，入口来自固定 venv。
- ROS 逻辑路径相同；用户目录不同只应体现在 `resolved` 字段。
- farm manifest、required libraries 和 package prefix 集合一致。
- `required_external_environment` 为空。

本地用多套污染环境运行脚本只能证明环境清理逻辑稳定，不能冒充第二台物理 Mac。发布前仍需在
每台目标 Mac 上各自保存 `prepare`、`doctor --json` 和一次真实 task-station READY 记录。

## 常见检查

固定路径或 Python 不符合契约时，`doctor --base` 会在构建前失败：

```zsh
scripts/so101-macos.zsh doctor --base
```

查看当前发布的 overlay 和 farm：

```zsh
readlink /opt/data/so101/runtime/fork/current
readlink /opt/ros2_jazzy/dylib_farm/current
```

若 IDE 仍然标红，把解释器设为 `/opt/ros2_jazzy/.venv/bin/python`。不要在源码里写死
`sys.path`，也不要恢复旧的 `~/ros2_jazzy/so101_isolated_ws` 或
`~/ros2_jazzy/macos_dylib_farm` 路径。
