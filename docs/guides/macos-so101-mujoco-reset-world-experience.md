# macOS SO-101 MuJoCo RESET_WORLD 适配经验

适用环境：Apple Silicon、源码 ROS 2 Jazzy 位于 `~/ros2_jazzy`、Python 3.11。所有 ROS 三方包和项目 overlay 都放在该目录；系统工具仅通过 Homebrew 安装，Python 包和 ROS 包均从源码构建。

## 依赖缺失与解法

| 现象 | 原因 | 解法 |
| --- | --- | --- |
| `colcon-common-extensions` 报 `colcon-core` 无匹配发行版 | VSCode/终端使用了错误的 Python，或索引没有对应 wheel | 使用 `~/ros2_jazzy/.venv` 的 Python 3.11；`colcon-core 0.21.0`、`colcon-common-extensions 0.3.0` 从源码安装。不要把系统 Python 与 ROS Python 混用。 |
| `pytest` 插件约束冲突 | `pytest 9` 超出 Jazzy 测试插件兼容范围 | 源码安装 `pytest 8.4.2`。 |
| `mujoco_vendor` 在 Darwin 配置失败 | 官方 Jazzy vendor 只覆盖 Linux 预编译布局 | 从 MuJoCo `3.4.0` 源码构建；用 `tools/mujoco_vendor_macos` 导出标准 CMake target，安装到 `extra_ws/install`。 |
| 缺少 `transmission_interface` | 源码 ROS underlay 未包含运行依赖 | 使用 ros2_control `4.46.0` 源码构建到 `extra_ws/install`。Apple Clang 21 与 Jazzy 旧 gtest 的 `char8_t` 测试告警冲突，因此该依赖只构建运行目标，最终由 fork 的 135 个测试验证 ABI。 |
| Python 服务缺包 | ai-station 依赖未进入 Mac venv | 按远端版本从源码安装 `fastapi 0.101.0`、`pydantic 1.10.14`、`uvicorn 0.27.1`、`pillow 10.2.0`、`httpx 0.26.0` 及其依赖。 |

## 代码不兼容与补丁

- `mujoco_ros2_control` 固定 fork 在提交 `738e304...`，安装器只在独立 build source 上重放 `scripts/patches/`，不修改 submodule。macOS 补丁处理 C++17、Apple Clang 转换告警、Mach-O install name/rpath、Cocoa/IOKit/CoreFoundation/CoreVideo framework、主线程 GLFW viewer，以及 CTest 的反向 dylib 查找。
- 源码 ROS underlay 有大量分散的 dylib 目录。`scripts/setup-macos-ros-dylib-farm.zsh` 将同名且内容一致的库合并为原子 symlink farm；发现同名异内容时直接失败。当前 `current` 包含 877 个 dylib。
- macOS SIP 会在 `#!/usr/bin/env` 和间接脚本边界过滤 `DYLD_LIBRARY_PATH`。资格栈在 Darwin 上用当前 Python 显式执行 `ros2`，资格 supervisor 也使用 `sys.executable`，保证 `.venv` 和 dylib 环境不漂移。
- 正常关停只能向两个 `ros2 launch` owner 各发送一次 SIGINT；不能 `killpg(SIGINT)`，否则 launch 再转发一次，`ros2_control_node` 会以 `-2` 退出并出现 `process has died`。超时兜底仍可终止整个进程组。
- 多轮 `RESET_WORLD` 不能在控制器激活后的第一帧 joint state 到达时立即 pause；该帧可能仍是瞬态。现在先等待新反馈进入关节容差，再 pause 并复核最终状态。Teleop 的失败 layer 也会省略空的 `owner_failure_code`，避免响应模型掩盖真实 owner 错误。

## 环境与验证

复制 `.envrc.example` 为 `.envrc` 后执行 `direnv allow`。加载顺序是 ROS underlay、当前目录 `install/setup.bash`、三方 overlay、fork、已验证的隔离 overlay；最后加入 dylib farm。当前目录仍被 source，但经过验证的依赖和项目 overlay 放在它之后，避免旧 build 遮蔽新安装。

重建 dylib farm：

```zsh
SO101_ROS_ROOT=~/ros2_jazzy ./scripts/setup-macos-ros-dylib-farm.zsh
```

重建固定 fork：

```zsh
SO101_WORKSPACE_DIR=~/ros2_jazzy \
SO101_ROS_UNDERLAY=~/ros2_jazzy/install \
SO101_ROS_DEPENDENCY_OVERLAY=~/ros2_jazzy/extra_ws/install \
./scripts/install-mujoco-ros2-control.zsh
```

正式资格运行必须使用同一个共享仿真 session、`RESET_WORLD` 生命周期、连续 5 次、固定 bundle；完成后另起进程执行 `verify-batch`。不要用单次 smoke、runner 退出码或日志中的 `DONE` 代替 manifest 验证。OMPL 的 `No default projection is set` 在 RRTConnect 随后规划和控制器执行成功时是非致命提示。

本次迁移不创建或更新 experiment ledger；所有运行证据保留在 `~/ros2_jazzy/so101-evidence/macos-mujoco-reset-world/`。
