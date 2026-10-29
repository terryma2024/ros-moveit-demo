# 统一 Web 服务（Expert Validation 已退役）

Expert Validation 生产服务、它的网页、Linux broker 批处理（`so101_parallel_batch`）和感知 broker 容器已于 2026-10-24 退役（挂载树迁移 M5，提交 P3b）。启动器 `scripts/so101-teleop-macos.zsh` / `scripts/so101-teleop-linux.sh` 按人工决定恢复成只启动 Teleop 服务的精简版（命令名和子命令不变），不再带 Validation、模型或 broker 参数。

## 启动与清理

在目标主机的仓库根目录运行，启动已安装的统一 Web 服务（Teleop、Tasks、Archives）。它不启动 Gazebo、MoveIt 或 Teleop 控制后端：

```sh
scripts/so101-teleop-macos.zsh doctor    # 只检查 python、install 前缀、ROS setup 和 Tailscale IPv4
scripts/so101-teleop-macos.zsh start     # 先运行安装版应用的 --check，再等 /health/live 和首页就绪
scripts/so101-teleop-macos.zsh status
scripts/so101-teleop-macos.zsh cleanup   # 只向身份仍匹配的已记录服务发停止信号
```

Linux 用 `scripts/so101-teleop-linux.sh`，子命令相同。默认监听 `tailscale ip -4` 的地址和端口 `8000`；`--host`、`--port`、`--python`、`--install-prefix`、`--evidence-root`、`--state-dir`、`--domain-id`、`--partition` 可覆盖默认值。

`status` 和 `cleanup` 读取同一主机的管理状态（`~/.local/state/so101-teleop-service-<platform>/`）。`/health` 显示的全局状态不是 `IDLE` 时（有进行中的任务或被阻塞），`cleanup` 拒绝停止（`SERVICE_BUSY`）；读不到状态时也拒绝（`SERVICE_STATE_UNKNOWN`）。日志和 evidence 不会被删除，不是本脚本启动的服务不会被接管。

默认 evidence root 是 `<durable_base>/<run-id>/`（macOS `/opt/data/work/so101-evidence/teleop-service/`，Linux `/data/work/so101-evidence/teleop-service/`）；开发和验收任务用 `--evidence-root <已登记的绝对路径>` 指定本 task 的唯一 root。macOS 还需要 `/opt/data/so101/runtime/fork/current/local_setup.zsh` 和 `/opt/ros/jazzy/dylib_farm/current`，见 [`macos-runtime-environment.md`](macos-runtime-environment.md)。

macOS 服务 campaign（`so101_macos_service_campaign`）和它的进程内 MPS broker 保留，不使用 `so101-parallel-perception` 镜像。
