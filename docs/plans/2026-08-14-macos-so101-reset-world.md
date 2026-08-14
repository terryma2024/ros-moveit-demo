# macOS SO-101 MuJoCo RESET_WORLD 实施计划

目标是在 Apple Silicon macOS 上，仅使用 `~/ros2_jazzy` 内的源码 ROS/三方
overlay 和 Homebrew 系统库，完成 `so101_demo_py` 的 `RESET_WORLD` 连续五次
有效成功。当前冲突 checkout 保持不动，所有改动位于独立 worktree。

1. 固定 Python 测试环境为 ROS Jazzy 可兼容的 pytest 8.4.2，并保留环境修复证据。
2. 在 `~/ros2_jazzy/extra_ws` 单独构建 `transmission_interface`、MuJoCo 3.4.0
   源码和 macOS `mujoco_vendor` 包；所有源码提交与安装前缀可回查。
3. 运行锁定 fork 安装器，把补丁后的 `mujoco_ros2_control` 构建到
   `~/ros2_jazzy/ws_mujoco_ros2_control_fork`。
4. 将仓库包构建到 `~/ros2_jazzy/so101_isolated_ws`，运行安装态测试和来源检查。
5. 用一个 headless 栈执行 `RESET_WORLD` 五次，要求同一 session、递增 reset epoch、
   固定 bundle、每次完整物理与工作流证据，最后通过批次验证器。
6. 另跑一次不计数 GUI 观察，补充 macOS 画面证据；经验文档只记录依赖、错误、
   补丁和复现命令，不创建 experiment ledger。
