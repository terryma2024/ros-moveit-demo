# Apple Silicon macOS：ROS 2 Jazzy 与 SO-101 MuJoCo

本指南适用于 Apple Silicon、源码构建的 ROS 2 Jazzy、SO-101 MuJoCo 仿真和
`RESET_WORLD` 连续资格运行。ROS 源码工作区、ROS 三方包、MuJoCo fork、项目隔离构建和
Python 虚拟环境统一放在 `~/ros2_jazzy`，其中源码安装前缀通过
`/opt/ros/jazzy -> ~/ros2_jazzy/install` 暴露为 Ubuntu 默认路径。系统工具和基础库只通过 Homebrew 安装；
Python 包和 ROS 包均从源码构建，不执行网络安装脚本。

## 目录与环境

```text
~/ros2_jazzy/
├── .venv/                         # Python 3.11 ROS/测试环境
├── install/                       # ROS 2 Jazzy 源码 underlay
├── extra_ws/install/              # MoveIt、ros2_control、MuJoCo vendor、OMPL 等
├── ws_mujoco_ros2_control_fork/   # 锁定 fork 的独立源码、build、install
├── so101_isolated_ws/             # 本工程经过验证的隔离 build/install
├── macos_dylib_farm/current       # 源码 overlay 的聚合 dylib 软链接
└── so101-evidence/                # 资格运行证据

/opt/ros/jazzy -> ~/ros2_jazzy/install
/opt/ros/lyrical -> ~/ros2_lyrical/install
```

手动打开新 zsh 时按下列顺序加载：

```zsh
source ~/ros2_jazzy/.venv/bin/activate
source /opt/ros/jazzy/setup.zsh
source ./install/setup.zsh                    # 当前项目本地构建，可不存在
source ~/ros2_jazzy/extra_ws/install/setup.zsh
source ~/ros2_jazzy/ws_mujoco_ros2_control_fork/install/setup.zsh
source ~/ros2_jazzy/so101_isolated_ws/install/setup.zsh
export DYLD_LIBRARY_PATH="$HOME/ros2_jazzy/macos_dylib_farm/current${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
```

推荐用 direnv 自动配置。仓库根目录执行：

```zsh
cp .envrc.example .envrc
direnv allow
```

`.envrc.example` 会依次 source ROS underlay、当前目录的 `install/setup.bash`、三方
overlay、fork 和隔离项目 overlay，最后加入 dylib farm。当前目录仍会被加载，但经过
验证的 overlay 位于它之后，可避免旧 build 抢占 package prefix。VSCode 必须从已进入
该目录并完成 direnv 加载的 shell 启动，Python 解释器选择
`~/ros2_jazzy/.venv/bin/python`。

脚本将 `SO101_ROS_UNDERLAY` 默认设为 `/opt/ros/jazzy`，将
`SO101_ROS_WORKSPACE` 默认设为 `~/ros2_jazzy`；旧的 `SO101_ROS_ROOT` 仍可作为工作区
根目录兼容变量。不要把 `/opt/ros/jazzy` 当成整个源码工作区：它只代表 `install`
前缀，因此 `.venv`、三方 overlay、fork、dylib farm 和证据仍在 `~/ros2_jazzy`。

## 依赖缺失与解决办法

| 现象 | 原因 | 解决办法 |
| --- | --- | --- |
| `colcon-common-extensions` 报 `colcon-core` 无匹配发行版 | VSCode/终端使用了错误 Python，或索引没有对应 wheel | 使用 `~/ros2_jazzy/.venv` 的 Python 3.11；从源码安装 `colcon-core 0.21.0` 和 `colcon-common-extensions 0.3.0`。不要混用系统 Python。 |
| `pytest` 插件约束冲突 | `pytest 9` 超出 Jazzy 测试插件兼容范围 | 从源码安装并固定 `pytest 8.4.2`。 |
| `mujoco_vendor` 在 Darwin 配置失败 | Jazzy vendor 默认按 Linux 预编译布局处理 | 从 MuJoCo `3.4.0` 源码构建，通过 `tools/mujoco_vendor_macos` 导出标准 CMake target，安装到 `extra_ws/install`。 |
| 缺少 `transmission_interface` | 源码 ROS underlay 未包含 fork 的运行依赖 | 从 ros2_control `4.46.0` 源码构建到 `extra_ws/install`。Apple Clang 21 与 Jazzy 旧 gtest 的 `char8_t` 告警冲突，因此这里只构建运行目标，最终由 fork 测试验证 ABI。 |
| 缺少 `tl_expected`、`ros_gz_interfaces` 或 MoveIt/OMPL 组件 | ai-station 的二进制环境没有随源码工程迁移 | 将对应源码包统一构建到 `extra_ws/install`。不要把系统路径临时拼入工程。 |
| Python 服务缺包 | ai-station 依赖未进入 Mac venv | 按兼容版本从源码安装 `fastapi 0.101.0`、`pydantic 1.10.14`、`uvicorn 0.27.1`、`pillow 10.2.0`、`httpx 0.26.0` 及其依赖。 |

OMPL 2.0.1 需要 Homebrew `libomp`。配置源码构建时使用：

```text
-DCMAKE_CXX_FLAGS=-I/opt/homebrew/opt/libomp/include
-DOpenMP_CXX_FLAGS=-Xpreprocessor -fopenmp
-DOpenMP_CXX_LIB_NAMES=omp
-DOpenMP_omp_LIBRARY=/opt/homebrew/opt/libomp/lib/libomp.dylib
```

## 构建与 macOS 补丁

重建聚合 dylib 目录：

```zsh
./scripts/setup-macos-ros-dylib-farm.zsh
```

源码 ROS 的 `.dylib` 分散在大量 install 目录中，而 macOS SIP 会在
`#!/usr/bin/env` 和间接脚本边界过滤 `DYLD_LIBRARY_PATH`。dylib farm 将同名且内容一致
的库聚合成一个原子切换的软链接目录；若同名库内容不同则直接失败，避免静默加载错误
ABI。资格通过时的 farm 含 877 个 dylib。项目 C++ 目标仍需保留 install rpath；farm
不是 rpath 的替代品。

重建固定的 `mujoco_ros2_control` fork：

```zsh
SO101_WORKSPACE_DIR=~/ros2_jazzy \
SO101_ROS_UNDERLAY=/opt/ros/jazzy \
SO101_ROS_DEPENDENCY_OVERLAY=~/ros2_jazzy/extra_ws/install \
./scripts/install-mujoco-ros2-control.zsh
```

fork 固定在提交 `738e304...`。安装器在独立 build source 上重放
`scripts/patches/`、清缓存构建、运行包测试，并检查 package prefix 和 dylib。不要手工
修改 `third_party/mujoco_ros2_control` 或生成目录中的源码；补丁应保持可重放。

主要兼容修改如下：

- Apple Clang：补齐 C++17、`PRIu64` 和转换告警兼容。
- Mach-O：修正 install name、`@executable_path`、install rpath，并链接 GLFW 所需的
  Cocoa、IOKit、CoreFoundation、CoreVideo framework；CTest 补齐 RMW 和日志 dylib
  查找路径。
- AppKit 主线程：原生 MuJoCo viewer 由 `ros2_control_node` 主线程创建，ROS executor
  放到后台线程。GUI 模式禁用会在 worker thread 新建 GLFW window 的离屏 camera/lidar，
  但保留原生 viewer；headless 模式禁用全部渲染。
- SIP/Python：Darwin 上用当前 `sys.executable` 显式执行 `ros2` 和 Python 节点，避免
  shebang 跨进程后丢失 `.venv` 与 dylib 环境。
- 正常关停：只向两个 `ros2 launch` owner 各发送一次 SIGINT。不能对整个进程组发送
  SIGINT，否则 launch 会再次转发，导致 `ros2_control_node` 以 `-2` 退出；仅超时兜底
  终止进程组。
- reset：重新写入并读回 Planning Scene；等待 reset 后的新 joint feedback 收敛到关节
  容差，再 pause 并复核最终状态，不能把控制器激活后的第一帧瞬态当成稳定状态。
- 首次启动：源码栈 readiness budget 为 90 秒；Teleop 失败响应省略空的
  `owner_failure_code`，保留真实 owner 错误。

Finder 或浏览器来源文件可能带 `com.apple.provenance` xattr，使 `--symlink-install` 无法
替换旧 build 路径。保留旧目录用于审计，改用全新的 package build 目录；不要用管理员
权限覆盖源码。

## 运行与前缀检查

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

运行前先确认解析位置；基础 underlay 使用 `/opt/ros/jazzy`，额外包仍来自源码工作区：

```zsh
ros2 pkg prefix transmission_interface  # ~/ros2_jazzy/extra_ws/install
ros2 pkg prefix mujoco_vendor           # ~/ros2_jazzy/extra_ws/install
ros2 pkg prefix mujoco_ros2_control      # ~/ros2_jazzy/ws_mujoco_ros2_control_fork/install
ros2 pkg prefix so101_demo_py            # ~/ros2_jazzy/so101_isolated_ws/install/so101_demo_py
```

若终端可运行但 VSCode 仍标红，先检查 VSCode 状态栏的解释器是否为
`~/ros2_jazzy/.venv/bin/python`，再从已加载 direnv 的项目终端执行 `Developer: Reload
Window`。不要通过在源码中写死 `sys.path` 掩盖 overlay 错误。

## RESET_WORLD 连续 5 次资格运行

正式资格运行必须在同一个共享仿真 session 中使用 `RESET_WORLD` 生命周期、固定 bundle
并连续成功 5 次。推荐 headless；GUI smoke 只验证显示路径，不能替代资格 manifest。

```zsh
evidence_root="$HOME/ros2_jazzy/so101-evidence/macos-mujoco-reset-world/<run-id>"
bundle_sha256="<固定 bundle 的 SHA-256>"

ros2 run so101_demo_py run_qualification run \
  --batch-id <batch-id> \
  --lifecycle RESET_WORLD \
  --count 5 \
  --fingerprint "$bundle_sha256" \
  --evidence-root "$evidence_root" \
  --base-domain-id <未占用的 ROS_DOMAIN_ID> \
  --base-port <未占用的端口> \
  --headless
```

完成后必须在另一个进程中独立验证同一批次：

```zsh
ros2 run so101_demo_py run_qualification verify-batch \
  --evidence-root "$evidence_root" \
  --expected-lifecycle RESET_WORLD \
  --expected-count 5 \
  --expected-bundle "$bundle_sha256"
```

只有 `verify-batch` 输出 `QUALIFIED`，且 `qualification-manifest.json` 记录同一 session、
递增 reset epoch、固定 bundle 和 5 条合格记录，才算 5 连胜。单次 smoke、runner 退出码、
日志中的 `DONE` 或截图都不能代替 manifest 验证。

本次迁移不创建或更新 experiment ledger。证据统一保留在
`~/ros2_jazzy/so101-evidence/macos-mujoco-reset-world/`；不得未经授权删除或覆盖既有批次。

已知非致命提示：OMPL 可能记录 `No default projection is set`。只要 RRTConnect 随后的
规划、控制器执行和资格 manifest 均成功，该消息不构成失败；应按结果与证据判定，而非
只按日志级别判定。
