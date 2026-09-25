# 统一 Web Expert Validation 服务

在目标主机的仓库根目录运行启动脚本，它会启动已安装的统一 Web 服务并检查 Expert Validation 是否 ready，不会启动 Gazebo、MoveIt 或 Teleop 控制后端。此服务配置的 `/health` 显示 `domains.validation: "ready"`、`domains.teleop: "unavailable"`。

## 启动与清理

macOS 用 `scripts/so101-teleop-macos.zsh`，Linux 用 `scripts/so101-teleop-linux.sh`，两者子命令相同：

```sh
scripts/so101-teleop-macos.zsh doctor    # 只检查依赖路径和本机 Tailscale IPv4
scripts/so101-teleop-macos.zsh start     # 再运行安装版应用的 --check，然后等 /health ready
scripts/so101-teleop-macos.zsh status
scripts/so101-teleop-macos.zsh cleanup   # 只向身份仍匹配的已记录服务发停止信号
```

默认监听 `tailscale ip -4` 返回的地址和端口 `8000`，用 `curl -sS "http://$(tailscale ip -4):8000/health"` 检查。`/health` 顶层 `ok: false` 只表示 Teleop 控制域未就绪，不能用它代替 Validation 的状态判断。

`start` 输出 PID、日志和 evidence root；`status` 和 `cleanup` 读取同一主机的管理状态，macOS 默认在 `~/.local/state/so101-teleop-service-darwin/`，Linux 默认在 `~/.local/state/so101-teleop-service-linux/`。Campaign 仍在运行、正在清理或缺少完成清理回执时，`cleanup` 会拒绝停止。服务证据、模型和日志不会被删除。自定义 `--state-dir` 后，后续 `status` 和 `cleanup` 也要传入同一路径。

## 安装路径与模型

脚本使用以下已验证的主机默认值；现场移动后以只读检查确认新路径，再把相应参数传给 `doctor` 和 `start`。

| 项目 | macOS | Linux |
|---|---|---|
| Python | `/opt/ros/jazzy/.venv/bin/python` | `/data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python` |
| 项目 install | `/opt/data/so101/workspace/install` | 当前仓库的 `install/` |
| ROS setup | `/opt/ros/jazzy/install/setup.zsh`、`/opt/ros/jazzy/extra_ws/install/setup.zsh` | `/opt/ros/jazzy/setup.zsh` |
| 执行配置 | `parallel_batch_v4_macos_mps_w2.yaml` | `parallel_batch_v3.yaml` |
| YOLO 权重 | `/opt/data/work/so101-evidence/dual-teleop-tailscale/20260923-ff228e71/models/yolo/best.pt` | `/data/work/models/so101-perception/yolo11n-seg-plastic-cup/best.pt` |
| Grounded 模型目录 | `/opt/data/work/so101-evidence/dual-teleop-tailscale/20260923-ff228e71/models/grounded` | `/data/work/models/so101-perception/grounded-sam-cup-pickplace/bundle` |

macOS 还需要 `/opt/data/so101/runtime/fork/current/local_setup.zsh` 和 `/opt/ros/jazzy/dylib_farm/current`，完整环境检查见 [`macos-runtime-environment.md`](macos-runtime-environment.md)。缺少依赖时先修复 `doctor` 报出的路径，脚本不会安装 ROS、Python 包或模型。

可用 `--python`、`--install-prefix`、`--yolo-weights`、`--grounded-root` 覆盖对应默认值。测试另一个监听地址时，`start --host 127.0.0.1 --port 8014` 会在本机端口启动，不改变默认端口的服务。

## 端口、所有权与证据

2026-09-23 验收时，Mac 和 ai-station 的旧验收服务都在 Tailscale 地址的 8000 端口运行。管理脚本没有这些进程的状态记录，`start` 会报 `PORT_UNAVAILABLE`，`cleanup` 也不会接管它们。切换服务前先查询 campaign 和进程身份，确认旧任务已结束，再通过原启动器或所属 tmux 会话关闭旧服务；不得用 `pkill -f ros` 或按端口号直接杀进程。

默认 `start` 在 macOS 的 `/opt/data/work/so101-evidence/teleop-service/<run-id>/` 或 Linux 的 `/data/work/so101-evidence/teleop-service/<run-id>/` 创建私有 evidence root，重新启动同一管理状态时会复用它。SO-101 开发或专家验收任务不要依赖这个私有默认值，先用 `--evidence-root <registered-absolute-path>` 指定本 task 已登记的唯一 root，登记方式见 `SKILL.md` 的“证据根”一节。脚本只接受平台对应的 `so101-evidence/` 树，不接受源码目录、`/tmp` 或直接创建的平台 `so101-debug-*` 路径。
