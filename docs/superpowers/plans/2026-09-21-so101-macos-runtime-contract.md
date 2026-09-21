# SO-101 macOS 固定运行环境实施计划

**目标：** 让 `so101_demo_py` 在 Apple Silicon macOS 上通过同一个入口启动。入口先检查固定 ROS 环境；前提不成立时直接停止并给出可执行的修复提示，不再回退到用户目录或继承当前 shell 的偶然状态。

**固定契约：** ROS 根目录为 `/opt/ros2_jazzy`，Python 为 `/opt/ros2_jazzy/.venv/bin/python`，ROS 安装为 `/opt/ros2_jazzy/install`，dylib farm 为 `/opt/ros2_jazzy/dylib_farm/current`，临时目录为 `/opt/data/tmp`，运行数据根目录为 `/opt/data`。锁定 fork 通过 `/opt/data/so101/runtime/fork/current` 暴露，本仓运行包安装到 `/opt/data/so101/workspace/install`。源码 clone 路径可以不同，运行时前缀相同。

**实现方式：** 新增一个统一 zsh 入口和一个可独立测试的 Python 契约检查器。启动入口只接受 `doctor`、`prepare`、`launch`、`run`。`prepare` 先检查基础契约，再构建当前仓库的 `so101_demo_py` overlay、重建 dylib farm，最后执行真实加载检查；`launch/run` 通过完整 doctor 后，按固定顺序 source underlay、依赖 overlay 和当前仓库 overlay，最后用固定 Python 显式执行 ROS CLI。

## Task 1：固定并测试运行环境契约

- [x] 在 `src/so101_demo_py/test/` 中先写失败测试，覆盖固定路径、Darwin/arm64、目录权限、合法软链接、断链、Python 3.11 ABI、Python/ROS CLI、项目 overlay、必需 dylib，以及污染环境不改变契约。
- [x] 新增 `scripts/so101_macos_runtime_contract.py`。基础 doctor 检查平台、路径、权限与 Python；完整 doctor 增加 package prefix、farm manifest、`rclpy`/类型支持真实加载和 MuJoCo plugin 闭包。输出稳定 JSON，记录逻辑/真实路径、系统版本、Python ABI、依赖版本和包前缀。路径通过 Python 对象注入以便测试，但产品 CLI 固定使用 `/opt` 契约。
- [x] 修改 `scripts/setup-macos-ros-dylib-farm.zsh`，默认输出固定到 `/opt/ros2_jazzy/dylib_farm`。输入顺序固定为 ROS install、`extra_ws/install`、`/opt/data/so101/runtime/fork/current` 和 `/opt/data/so101/workspace/install`；固定前缀缺失时失败，不采用“存在就 source”。同名库按同一 overlay 顺序由后者覆盖，并记录 override manifest。farm 缺少 `libhardware_interface.dylib`、`librosidl_typesupport_c.dylib` 或 `libcontrol_toolbox.dylib` 时失败。

## Task 2：统一准备与启动入口

- [x] 新增 `scripts/so101-macos.zsh`，实现 `doctor`、`prepare`、`launch`、`run`，并校验参数与 `ROS_DOMAIN_ID`。`doctor --base` 可在首次准备前运行，完整 doctor 只在 overlay 与 farm 就绪后通过。
- [x] 入口从 allowlist 重建环境，清除继承的 `PYTHONHOME`、`PYTHONPATH`、`AMENT_PREFIX_PATH`、`CMAKE_PREFIX_PATH`、`COLCON_PREFIX_PATH` 与全部 `DYLD_*`；临时关闭 nounset 后按固定顺序 source setup，再恢复严格模式。脚本固定 `TMPDIR/TMP/TEMP=/opt/data/tmp`，把 `ROS_HOME/ROS_LOG_DIR` 放入 `/opt/data/so101`，`ROS_DOMAIN_ID` 默认 0 且只允许 0–232。
- [x] `prepare` 使用固定 Python/colcon。若固定 fork marker、公开头文件或锁定 commit 不匹配，在 `/opt/data/so101/runtime` 的全新 canonical workspace 重建并测试 fork，不改写旧的 `/opt/ros2_jazzy/ws_mujoco_ros2_control_fork`；随后构建 `so101_mujoco_support`、`so101_teleop`、`so101_demo_py` 到固定 workspace 并生成 farm。`launch/run` 使用固定 Python 显式执行 `/opt/ros2_jazzy/install/ros2cli/bin/ros2`。
- [x] 更新 `.envrc.example`，使交互式 shell 与统一脚本共享同一固定路径，不再默认 `$HOME/ros2_jazzy` 或 `/opt/ros/jazzy`。

## Task 3：指南与验证

- [x] 更新 `docs/guides/macos-apple-silicon-ros2-jazzy-so101-mujoco.md`，记录固定契约、首次准备、统一启动命令、最小环境变量和常见失败定位。
- [x] 运行 scoped pytest、普通 `so101_demo_py` 测试门、脚本语法检查和 `git diff --check`。最终的 macOS 普通非 ML 门禁使用 8 个 worker，结果为 3650 passed、9 skipped、0 failed，pytest 退出码为 0；12 个 `explicit_ml` 测试明确排除，且未收集 `benchmark_test/`。scoped pytest、脚本语法检查和 `git diff --check` 也已通过。
- [x] 在当前 Mac 上执行真实 `prepare` 与完整 doctor，再通过统一入口做有界 GUI task-station 启动，确认 Python 节点、`ros2_control_node`、ready 状态与清理结果。保存完整命令、退出码和日志。
- [x] 在两个隔离 HOME/PATH/ROS/DYLD 污染配置下运行真实 shell 入口，证明固定契约不依赖调用者环境。当前主机的两套污染环境回执逐字节一致。
- [x] 在第二台物理 Mac 上重复 `prepare`、完整 doctor 和一次真实 READY 验证；不能用本机污染环境矩阵代替。`matianyideMacBook-Air.local` 已在 `ROS_DOMAIN_ID=226` 上通过，详见实验账本 `RUN-007`。该项只确认第二台主机成功；由于 `RUN-002` 使用较早的 `/tmp` 契约，当前 `/opt/data/tmp` 补丁仍需在 Mac mini 上复验，之后才能宣称同一补丁的双机闭环。
- [x] scoped RED/GREEN 和普通 package gate 都先用固定 Python 验证 `rclpy`，记录非零收集、JUnit、退出码和摘要。
- [x] 登记证据、保留项和删除候选；不删除任何证据。
