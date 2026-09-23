# macOS 上的 SO-101 C++ 依赖

这份清单记录 Apple Silicon Mac 上构建项目 C++ 包所需的 Gazebo Harmonic、MoveIt 和 ROS 桥接依赖。ROS 的逻辑根目录统一为 `/opt/ros/jazzy`；物理目录可以位于用户目录。先运行 `scripts/so101-macos.zsh doctor --base`，确认入口和 Python 环境可用。

## Homebrew 包

项目使用 Gazebo Harmonic。当前机器安装并验证过以下版本：

| 包 | 当前版本 | 用途 |
| --- | --- | --- |
| `osrf/simulation/gz-msgs10` | 10.4.0 | Gazebo 消息定义 |
| `osrf/simulation/gz-transport13` | 13.6.0 | Gazebo transport |
| `osrf/simulation/gz-sim8` | 8.15.0 | Gazebo 仿真；同时带入 `gz-plugin2` 等 Harmonic 库 |
| `ogre2.3-with-freeimage` | 2.3.1 | `gz_ogre_next_vendor` 使用的 OGRE-2.3 |
| `qt@5` | 5.15.19 | Gazebo ROS 控制插件编译 |
| `cli11` | 2.6.2 | `ros_gz_sim` 的命令行头文件 |
| `tinyxml2` | Homebrew 当前版 | `gz_ros2_control` 的 CMake 目标 |
| `llvm` | 22.1.8 | 项目 C++ 的 `run-clang-tidy`、`clang-tidy` 和 `clang-format` 门禁 |
| `uncrustify` | 0.83.0 | ROS `ament_uncrustify` 只读测试所需的可执行程序 |
| `coreutils` | Homebrew 当前版 | C++ 测试脚本使用的 GNU `timeout` |
| `bash` | 5.3.15 | Gazebo launch 的子进程保留 ROS 动态库搜索路径 |
| `gnu-sed` | Homebrew 当前版 | 测试脚本使用的 GNU `sed` 地址和 `-i` 语法 |
| `ripgrep` | 15.2.0 | C++ 测试脚本使用的 `rg` 命令 |
| `ffmpeg-full` | 9.0.2 | 视频帧取样需要 `drawtext`；普通 `ffmpeg` 9.0.2 未编入该 filter |
| `ninja` | 1.13.2 | 本次隔离构建使用的 CMake 生成器 |

安装缺失的 Gazebo 版本包：

```zsh
brew install osrf/simulation/gz-msgs10 osrf/simulation/gz-transport13 osrf/simulation/gz-sim8
```

这台机器原有的 `ogre2.3` 链接与 `ogre2.3-with-freeimage` 冲突。两套 formula 均已保留，只把激活的链接切换为 `ogre2.3-with-freeimage`。若 `brew install` 报相同冲突，先核实当前链接，再执行 `brew unlink ogre2.3` 和 `brew link ogre2.3-with-freeimage`。

## ROS 源码包

基础 `/opt/ros/jazzy/install` 和依赖 `/opt/ros/jazzy/extra_ws/install` 已有部分 MoveIt 包。以下缺口需补入依赖 overlay，才能让项目的 Gazebo 与 MoveIt C++ 包完整配置和链接：

| 来源 | 包 |
| --- | --- |
| 现有 `extra_ws/src/moveit2` 与 `warehouse_ros` | `warehouse_ros`、`moveit_ros_warehouse`、`moveit_ros_planning_interface` |
| ROS 2 配套源码 | `xacro`、`moveit_resources_panda_description`、`moveit_resources_panda_moveit_config`、`moveit_resources_fanuc_description`、`moveit_resources_fanuc_moveit_config`、`simulation_interfaces` |
| 桥接消息源码 | `actuator_msgs`、`gps_msgs`、`marine_acoustic_msgs`、`vision_msgs` |
| Jazzy `gazebo-release` | `gz_common_vendor`、`gz_dartsim_vendor`、`gz_fuel_tools_vendor`、`gz_gui_vendor`、`gz_msgs_vendor`、`gz_ogre_next_vendor`、`gz_physics_vendor`、`gz_plugin_vendor`、`gz_rendering_vendor`、`gz_sensors_vendor`、`gz_sim_vendor`、`gz_transport_vendor`、`sdformat_vendor` |
| Jazzy 集成源码 | `gz_ros2_control`、`ros_gz_bridge`、`ros_gz_sim` |

本次隔离构建的源码提交与命令、失败边界记录在 [实验账本](../experiments/so101-macos-jazzy-path-deps-20260923-experiment-ledger.md)。补包时固定源码提交，避免 Jazzy 分支后续变化混入已验证的依赖组合。
已验证的十组补包源码保留在 `/opt/ros/jazzy/extra_ws/so101_macos_source_pins/`，逐文件与隔离构建源码核对过路径、大小和 SHA256。它们位于 `src/` 之外，避免与现有 `ros_gz` 和 `sdformat_vendor` 源码重复发现。下面的命令明确指定源码目录、29 个包和构建参数。

## 重建依赖与项目

先在仓库根目录使用已经登记的证据根目录运行以下命令。`SO101_EVIDENCE_ROOT` 必须指向本次任务独有的目录；构建日志和中间文件都留在那里。重建前核对锁定源码及上述 Homebrew 包，确认补丁已应用到相应源码。

```zsh
: "${SO101_EVIDENCE_ROOT:?先登记并设置本次任务的证据根目录}"
test -d "$SO101_EVIDENCE_ROOT"
repo="$PWD"
ros_root=/opt/ros/jazzy
pins="$ros_root/extra_ws/so101_macos_source_pins"
test -x "$ros_root/.venv/bin/colcon"
test -x "$ros_root/.venv/bin/python"
test -f "$repo/tools/macos/homebrew-gazebo-cmake.cmake"
source "$ros_root/install/setup.zsh"
source "$ros_root/extra_ws/install/setup.zsh"
export PATH="$ros_root/.venv/bin:/opt/homebrew/opt/ffmpeg-full/bin:/opt/homebrew/opt/llvm/bin:/opt/homebrew/opt/coreutils/libexec/gnubin:/opt/homebrew/opt/gnu-sed/libexec/gnubin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PYTHONNOUSERSITE=1
export DYLD_LIBRARY_PATH="$ros_root/dylib_farm/current"
export GZ_RELAX_VERSION_MATCH=1
export GZ_CONFIG_PATH=/opt/homebrew/opt/gz-sim8/share/gz:/opt/homebrew/opt/gz-transport13/share/gz:/opt/homebrew/opt/gz-msgs10/share/gz:/opt/homebrew/opt/gz-plugin2/share/gz:/opt/homebrew/opt/sdformat14/share/gz

"$ros_root/.venv/bin/colcon" --log-base "$SO101_EVIDENCE_ROOT/build/promote-log" build \
  --base-paths \
    "$ros_root/extra_ws/src/moveit2/moveit_ros/planning_interface" \
    "$ros_root/extra_ws/src/moveit2/moveit_ros/warehouse" \
    "$ros_root/extra_ws/src/warehouse_ros" \
    "$pins/xacro-src" "$pins/moveit_resources-src" \
    "$pins/simulation_interfaces-src" "$pins/actuator_msgs-src" \
    "$pins/gps_umd-src" "$pins/marine_msgs-src" "$pins/vision_msgs-src" \
    "$pins/gz-vendors-src" "$pins/gz_ros2_control-src" "$pins/ros_gz-src" \
  --packages-select \
    warehouse_ros moveit_ros_warehouse moveit_ros_planning_interface \
    xacro moveit_resources_panda_description moveit_resources_panda_moveit_config \
    moveit_resources_fanuc_description moveit_resources_fanuc_moveit_config \
    simulation_interfaces actuator_msgs gps_msgs marine_acoustic_msgs vision_msgs \
    gz_common_vendor gz_dartsim_vendor gz_fuel_tools_vendor gz_gui_vendor \
    gz_msgs_vendor gz_ogre_next_vendor gz_physics_vendor gz_plugin_vendor \
    gz_rendering_vendor gz_sensors_vendor gz_sim_vendor gz_transport_vendor \
    sdformat_vendor gz_ros2_control ros_gz_bridge ros_gz_sim \
  --build-base "$SO101_EVIDENCE_ROOT/build/promote-build" \
  --install-base "$ros_root/extra_ws/install" --merge-install \
  --parallel-workers 2 \
  --cmake-args \
    -DBUILD_TESTING=OFF \
    -DPython3_EXECUTABLE="$ros_root/.venv/bin/python" \
    -DQt5_DIR=/opt/homebrew/opt/qt@5/lib/cmake/Qt5 \
    -DCLI11_INCLUDE_DIRS=/opt/homebrew/opt/cli11/include \
    -DSO101_MACOS_DYLIB_FARM="$ros_root/dylib_farm/current" \
    -DCMAKE_PROJECT_INCLUDE="$repo/tools/macos/homebrew-gazebo-cmake.cmake"
```

依赖安装后，先运行 `scripts/setup-macos-ros-dylib-farm.zsh`，再运行 `scripts/so101-macos.zsh prepare`。`prepare` 会重建锁定的 MuJoCo fork 和三个项目包。要迁移完整 C++ 项目，还需在同一仓库执行下面的八包构建；旧 `/opt/ros2_jazzy` 链接必须等这一步通过后才能移除。

```zsh
source /opt/data/so101/runtime/fork/current/local_setup.zsh
test -x /opt/homebrew/opt/llvm/bin/run-clang-tidy
test -x /opt/homebrew/opt/llvm/bin/clang-format
"$ros_root/.venv/bin/colcon" --log-base "$SO101_EVIDENCE_ROOT/build/project-stable-log" build \
  --base-paths "$repo/src" \
  --packages-select \
    fixed_pose_goal panda_gazebo_demo_cpp panda_mujoco_demo \
    pick_place_common so101_gazebo_demo_cpp so101_mujoco_support \
    so101_teleop so101_demo_py \
  --build-base /opt/data/so101/workspace/build \
  --install-base /opt/data/so101/workspace/install \
  --parallel-workers 2 --cmake-clean-cache \
  --cmake-args \
    -DBUILD_TESTING=ON \
    -DPython3_EXECUTABLE="$ros_root/.venv/bin/python" \
    -DQt5_DIR=/opt/homebrew/opt/qt@5/lib/cmake/Qt5 \
    -DCLI11_INCLUDE_DIRS=/opt/homebrew/opt/cli11/include \
    -DRUN_CLANG_TIDY_EXECUTABLE=/opt/homebrew/opt/llvm/bin/run-clang-tidy \
    -DCLANG_FORMAT_EXECUTABLE=/opt/homebrew/opt/llvm/bin/clang-format \
    -DCMAKE_PROJECT_INCLUDE="$repo/tools/macos/homebrew-gazebo-cmake.cmake"
scripts/setup-macos-ros-dylib-farm.zsh
scripts/so101-macos.zsh doctor --json
```

macOS 有几处需要显式处理的构建边界：`gz_ogre_next_vendor` 通过 [`gz-ogre-next-vendor-homebrew.patch`](../../tools/macos/gz-ogre-next-vendor-homebrew.patch) 使用 Homebrew OGRE；`gz_ros2_control` 通过 [`gz-ros2-control-entity-format.patch`](../../tools/macos/gz-ros2-control-entity-format.patch) 修正 Clang 的 `Entity` 格式检查，并通过 [`homebrew-gazebo-cmake.cmake`](../../tools/macos/homebrew-gazebo-cmake.cmake) 提供 TinyXML2 目标；`ros_gz_bridge` 通过 [`ros-gz-bridge-dyld-farm.patch`](../../tools/macos/ros-gz-bridge-dyld-farm.patch) 给两个代码生成子进程传入 dylib farm；`ros_gz_sim` 配置时需要 `-DCLI11_INCLUDE_DIRS=/opt/homebrew/opt/cli11/include`。`ros_gz_sim` 的 [`ros-gz-sim-dyld-shell.patch`](../../tools/macos/ros-gz-sim-dyld-shell.patch) 让 macOS 直接启动 Homebrew Ruby，避免 `/bin/sh` 清除 `DYLD_LIBRARY_PATH`。

项目 C++ 构建还需要显式传入 `-DPython3_EXECUTABLE=/opt/ros/jazzy/.venv/bin/python`、`-DQt5_DIR=/opt/homebrew/opt/qt@5/lib/cmake/Qt5`、`-DRUN_CLANG_TIDY_EXECUTABLE=/opt/homebrew/opt/llvm/bin/run-clang-tidy`、`-DCLANG_FORMAT_EXECUTABLE=/opt/homebrew/opt/llvm/bin/clang-format` 和 `-DCMAKE_PROJECT_INCLUDE=<仓库绝对路径>/tools/macos/homebrew-gazebo-cmake.cmake`。构建前还要执行 `export PATH="/opt/homebrew/opt/llvm/bin:$PATH"`，使 `run-clang-tidy` 的子进程找到同版本 `clang-tidy`。路径以本机 `test -x`、`test -f` 检查为准。Homebrew `llvm@18` 在当前 Xcode SDK 的 libc++ 头中出现编译诊断，已排除在本次可用工具链之外。

运行 shell 脚本和 CTest 前，再把 `/opt/homebrew/opt/coreutils/libexec/gnubin`、`/opt/homebrew/opt/gnu-sed/libexec/gnubin`、`/opt/homebrew/bin` 放入 `PATH`。这一步让脚本找到 GNU `timeout`、GNU `sed`、Homebrew Bash 和 `rg`。Gazebo launch 通过 PATH 选取 Homebrew Bash，避免 macOS 系统 `/bin/bash` 启动 ROS 子进程时清除 `DYLD_LIBRARY_PATH`。
视频取样还需让 `/opt/homebrew/opt/ffmpeg-full/bin` 排在 `/opt/homebrew/bin` 前面。统一入口已固定这个顺序，手工 CTest shell 也须遵守。

ROS 的旧 `sdformat_vendor` 环境 hook 会把 `GZ_CONFIG_PATH` 指向旧库。macOS 统一入口现固定选用 Homebrew Harmonic 的 `gz-sim8`、`gz-transport13`、`gz-msgs10`、`gz-plugin2` 和 `sdformat14` 命令配置。手工运行 CTest 时也需使用这组路径；否则 `gz sdf -p` 可能加载旧 vendor 库并以 255 退出。

构建后的终端按顺序加载 `/opt/ros/jazzy/install/setup.zsh`、`/opt/ros/jazzy/extra_ws/install/setup.zsh`、fork 的 `local_setup.zsh` 和项目的 `local_setup.zsh`。已有 fork 与项目 `setup.zsh` 可能记录旧入口，直接加载它们会把 `/opt/ros2_jazzy` 再放入环境。
旧 fork 的 CMake 导出文件也记录过 `/opt/ros2_jazzy`。迁移后运行 `scripts/so101-macos.zsh prepare` 会在新目录重建锁定 fork，并对其过时的 macOS RPATH 测试应用 [`mujoco-fork-rpath-test.patch`](../../tools/macos/mujoco-fork-rpath-test.patch)。这项测试现在检查两个相对搜索路径，与锁定源码中的安装设置一致。
