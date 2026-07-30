# ai-station 远程、GUI 与 CUA

## 导航

- [事实与可变项](#事实与可变项)
- [shell 与 overlay](#shell-与-overlay)
- [GUI 进程](#gui-进程)
- [RViz 与 Gazebo 左右 50% 分屏](#rviz-与-gazebo-左右-50-分屏)
- [`codex-cua` 会话](#codex-cua-会话)
- [视觉证据](#视觉证据)
- [进程所有权与清理](#进程所有权与清理)

## 事实与可变项

仓库约定的 SSH 别名是 `ai-station`，ROS 工作区通常是 `/data/work/ws_moveit`，ROS 发行版通常是 Jazzy。它们是需要现场复核的环境约定，不是永久常量。

先做只读探测：

```bash
ssh -o BatchMode=yes ai-station 'hostname; pwd; zsh -lc "cd /data/work/ws_moveit && git rev-parse --show-toplevel && git status --short"'
ssh ai-station 'tmux list-sessions 2>/dev/null || true'
ssh ai-station 'pgrep -af "gz sim|move_group|rviz2|pick_place_state_machine" || true'
```

不要在输出中暴露 SSH 配置、token、proxy 凭据或完整私有环境变量。

## shell 与 overlay

ai-station 使用 zsh。ROS 命令按以下顺序加载：

```bash
source /opt/ros/jazzy/setup.zsh
cd /data/work/ws_moveit
source install/setup.zsh
```

不要在 zsh 里改用 `setup.bash`。每次 build 后重新 source。使用 `ros2 pkg prefix so101_gazebo_demo` 验证当前 overlay。

## GUI 进程

任何需要显示到已登录 GNOME 会话的 GUI 程序都必须由 tmux 持有，并在该 tmux shell 内先执行：

```bash
source ~/gui-env.zsh
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_moveit/install/setup.zsh
```

不得硬编码 `DISPLAY`、`XAUTHORITY` 或旧 session bus。长时间 GUI 任务要有明确 tmux session；不要用一次性 SSH shell 承载。

## RViz 与 Gazebo 左右 50% 分屏

先确认目标 RViz 和 Gazebo 已在各自的 tmux-held GUI session 中启动，并且没有第二套同类窗口造成识别歧义。分屏命令必须在已加载当前 GNOME 显示环境的 tmux shell 中运行。

检查 X11 依赖：

```bash
command -v xprop
command -v xwininfo
ldconfig -p | rg 'libX11\.so'
```

缺少依赖时，报告缺项；获得安装授权后使用 Ubuntu 包 `libx11-6` 和 `x11-utils`。不要以硬编码坐标或旧 `DISPLAY` 绕过依赖检查。

执行分屏：

```bash
source ~/gui-env.zsh
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_moveit/install/setup.zsh
ros2 run so101_gazebo_demo tile_ai_station_guis.py
```

该工具读取当前 EWMH work area，取消两个窗口的最大化状态，将 RViz 放在左侧 50%、Gazebo 放在右侧 50%；屏幕宽度为奇数时多出的 1 px 分给右侧。它等待目标窗口最多 30 秒，并在移动后回读两侧窗口几何。

成功必须同时满足：

- 命令退出码为 `0`，输出 `LAYOUT_OK RVIZ=... GAZEBO=...`；
- 回读位置和尺寸与目标几何的差值不超过默认 `12 px` 装饰边框容差；
- 分屏后重新运行本机 `<repo-root>/scripts/capture-ai-station.sh`；
- 实际打开新的 `desktop.png`，确认 RViz 左、Gazebo 右，各约占可用工作区 50%，两侧关键场景均可见且没有互相遮挡。

`LAYOUT_ERROR` 或退出码 `2` 表示失败。根据错误检查缺少的窗口、X11 依赖、`DISPLAY` 或窗口几何；不要把命令已发送当成分屏成功。若窗口尺寸正确但内部场景不可辨认，再用 CUA 按 `snapshot -> action -> fresh snapshot` 调整相机或面板，并保存新截图。

## `codex-cua` 会话

`codex-cua` 是标准 CUA 入口：

1. 先用 `tmux list-sessions` 和 `tmux capture-pane -pt codex-cua -S -200` 检查当前窗格与任务。
2. 会话存在且正在工作时，不发送按键、不重启、不抢占；先报告冲突。
3. 只有会话不存在且任务确需 GUI 操作时，才创建同名会话。不要为同一用途新建其他 session。
4. CUA 每次动作前获取 snapshot，动作后获取 fresh snapshot；element 索引只属于产生它的那次 snapshot。
5. 工具回报 `verified=false`、`degraded=true` 或效果不确定时，以新截图/read-back 验证，不把发送动作当成动作生效。

需要 CUA 驱动细节时再读取仓库 `skills/remote/cua-driver/SKILL.md` 与 `LINUX.md`；它们是参考快照，现场工具 schema 优先。

## 视觉证据

本机仓库已有抓取入口：

```bash
./scripts/capture-ai-station.sh
```

它会把 desktop、RViz 和 Ghostty 截图拉到忽略版本控制的 `assets/captures/ai-station/<timestamp>/`。先直接运行；只有远端 helper 缺失且任务允许部署 helper 时才运行 `--install`。

验收截图必须：

- 来自本轮动作之后；
- 能看到相关窗口和目标对象；
- 与本轮 log 时间、session 和运行模式对应；
- 由 agent 实际查看图像内容，而不是只检查文件存在或尺寸。

GUI 成功至少要写出“画面中哪一项发生了何种变化”。窗口出现、进程存活或截图生成本身都不是 pick-place 成功。

## 进程所有权与清理

只停止本轮明确启动且 PID/session 可追踪的进程。不要用宽泛 `pkill -f ros`、`killall gz` 或删除共享 tmux 会话。结束后再次列出相关进程和 ROS nodes，说明哪些是保留的既有进程。
