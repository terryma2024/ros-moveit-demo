# Apple Silicon macOS：ROS 2 Jazzy 与 SO-101

本工程在 Apple Silicon 上使用源码构建的 ROS 2 Jazzy。ROS 源码、ROS 三方包、MuJoCo fork、项目构建和 Python 虚拟环境统一位于 `~/ros2_jazzy`；Homebrew 只提供系统编译工具和基础库，不安装独立应用包，也不执行网络安装脚本。

## 目录与环境

```text
~/ros2_jazzy/
├── .venv/                         # ROS/测试 Python 环境
├── install/                       # ROS 2 Jazzy 源码 underlay
├── extra_ws/install/              # MoveIt、ros2_control、MuJoCo vendor、OMPL 等依赖
├── ws_mujoco_ros2_control_fork/   # 锁定 fork 的源码、build、install
└── so101_isolated_ws/             # 本工程隔离 build/install
```

每个新 shell 按下列顺序加载：

```zsh
source ~/ros2_jazzy/.venv/bin/activate
source ~/ros2_jazzy/install/setup.zsh
source ~/ros2_jazzy/extra_ws/install/setup.zsh
source ~/ros2_jazzy/ws_mujoco_ros2_control_fork/install/setup.zsh
source ~/ros2_jazzy/so101_isolated_ws/install/setup.zsh
```

重建锁定的 `mujoco_ros2_control` fork：

```zsh
SO101_WORKSPACE_DIR=~/ros2_jazzy \
SO101_ROS_UNDERLAY=~/ros2_jazzy/install \
SO101_ROS_DEPENDENCY_OVERLAY=~/ros2_jazzy/extra_ws/install \
./scripts/install-mujoco-ros2-control.zsh
```

安装器会还原并重新应用仓库内的 macOS 补丁、清缓存构建、运行包测试，并检查最终 package prefix 和 dylib。不要直接修改 `~/ros2_jazzy/ws_mujoco_ros2_control_fork/src`；应修改 `scripts/patches/` 中的可重放补丁。

## 缺失依赖与解决办法

- ROS 2/MoveIt 缺少的 `tl_expected`、`transmission_interface`、`ros_gz_interfaces`、`mujoco_vendor` 等从源码构建到 `extra_ws/install`。
- MuJoCo 使用 `mujoco_vendor` 提供的 3.4 版本；fork 运行库继续从该 overlay 解析。
- OMPL 2.0.1 需要 Homebrew `libomp`。配置源码构建时使用：

  ```text
  -DCMAKE_CXX_FLAGS=-I/opt/homebrew/opt/libomp/include
  -DOpenMP_CXX_FLAGS=-Xpreprocessor -fopenmp
  -DOpenMP_CXX_LIB_NAMES=omp
  -DOpenMP_omp_LIBRARY=/opt/homebrew/opt/libomp/lib/libomp.dylib
  ```

- Python 使用 `~/ros2_jazzy/.venv`；当前测试环境固定兼容的 `pytest 8.4.2`，避免系统 Python 与 ROS 生成包混用。
- macOS SIP 会过滤由脚本间接传递的 `DYLD_LIBRARY_PATH`。launch 文件在 Darwin 上显式用当前 Python 解释器启动 Python 节点，C++ 目标则通过 install rpath 解析 dylib。
- Finder/浏览器来源文件可能带 `com.apple.provenance` xattr，使 `--symlink-install` 无法替换旧 build 路径。保留旧目录后改用全新 package build 目录；不要用管理员权限覆盖源码。

## macOS 兼容补丁

fork 补丁覆盖 Apple Clang 的 `PRIu64`、Mach-O install name/rpath、`@executable_path`，以及 GLFW 所需 Cocoa、IOKit、CoreFoundation、CoreVideo framework。CTest 还显式补齐 RMW 与日志 dylib 路径。

MuJoCo 原实现会从 worker thread 创建 GLFW/AppKit 窗口，在 macOS 上触发 Cocoa 主线程异常。现在原生 viewer 由 `ros2_control_node` 主线程执行，ROS executor 在后台线程运行；退出时按顺序停止 viewer 和 ROS。SO-101 在 macOS GUI 模式下禁用会另开 worker GLFW window 的离屏 camera/lidar 渲染，但保留原生 MuJoCo viewer。headless 模式禁用全部渲染。

项目侧还有三项必要适配：reset 后重新写入并读回 Planning Scene；launch 子进程使用独立 process group 以保证 SIGINT 有序退出；源码栈首次启动的 readiness budget 为 90 秒，并传给会接收 launch 注入 ROS 参数的 `scene_setup`。

## 运行与验证

GUI：

```zsh
ros2 launch so101_demo_py so101_mujoco.launch.py \
  run_mode:=execute execute:=true headless:=false
```

Headless：

```zsh
ros2 launch so101_demo_py so101_mujoco.launch.py \
  run_mode:=execute execute:=true headless:=true
```

查看解析位置时，`ros2 pkg prefix` 应全部落入 `~/ros2_jazzy`：

```zsh
ros2 pkg prefix mujoco_vendor
ros2 pkg prefix mujoco_ros2_control
ros2 pkg prefix so101_demo_py
```

已知非致命提示：OMPL 可能记录 `No default projection is set`，但 RRTConnect 随后的计划与执行仍成功；应以 plan/controller result 和资格 manifest 判定，不能只按该日志级别判失败。
