# ai-station 远程、GUI 与 CUA

## 导航

- [事实与可变项](#事实与可变项)
- [先判定当前执行主机](#先判定当前执行主机)
- [向 tmux 中的 Codex 投递任务](#向-tmux-中的-codex-投递任务)
- [shell 与 overlay](#shell-与-overlay)
- [GUI 进程](#gui-进程)
- [RViz 与 Gazebo 左右 50% 分屏](#rviz-与-gazebo-左右-50-分屏)
- [`codex-cua` 会话](#codex-cua-会话)
- [视觉证据](#视觉证据)
- [进程所有权与清理](#进程所有权与清理)

## 事实与可变项

仓库约定的 SSH 别名是 `ai-station`，ROS 工作区通常是 `/data/work/ws_moveit`，ROS 发行版通常是 Jazzy。它们是需要现场复核的环境约定，不是永久常量。

## 先判定当前执行主机

在运行任何 `ssh ai-station` 前，先确认 coding agent 当前是否已经直接运行在 ai-station。不要用“能否解析 `ai-station` 别名”反推主机身份：远端 agent 的受限环境可能没有该 SSH 别名或 DNS 解析，但它仍然已经位于目标主机。

从 Mac/orchestrator 投递给 ai-station 上 tmux/Codex 的任务，交接开头必须明确写出：

```text
你当前直接运行在 ai-station 上。不要 ssh 到 ai-station；仓库、tmux、进程、CloudCompare、CUA 和截图命令都在当前主机直接执行。
```

远端 coding agent 先在本机只读确认：

```bash
hostname
pwd
test -d /data/work/ws_moveit && printf 'AI_STATION_WORKSPACE_PRESENT\n'
tmux list-sessions 2>/dev/null || true
```

执行边界：

- coding agent 已在 ai-station：直接运行本机命令，禁止再次 `ssh ai-station`；SSH 别名解析失败不是远端不可达证据。
- orchestrator 在 Mac：使用 `ssh ai-station '...'` 进入目标主机，并在交接给远端 agent 时声明上述执行位置。
- 无法确认：先报告 `hostname`、`pwd` 和工作区探测结果，不猜测 endpoint，也不把自我 SSH 失败声明为任务阻塞。

先做只读探测：

```bash
ssh -o BatchMode=yes ai-station 'hostname; pwd; zsh -lc "cd /data/work/ws_moveit && git rev-parse --show-toplevel && git status --short"'
ssh ai-station 'tmux list-sessions 2>/dev/null || true'
ssh ai-station 'pgrep -af "gz sim|move_group|rviz2|pick_place_state_machine" || true'
```

不要在输出中暴露 SSH 配置、token、proxy 凭据或完整私有环境变量。

## 向 tmux 中的 Codex 投递任务

先区分 tmux pane 当前是普通 shell，还是已经运行 Codex TUI。长任务先保存到该任务已登记
的 evidence root，回读绝对路径、大小和 SHA256；投递时只发送一条让 Codex 完整读取该
文件的短指令。tmux session 名与 Codex session UUID/任务名是两套标识，不得混用。下面
的命令在 ai-station 本机 zsh 中执行；Mac/orchestrator 需先通过 SSH 进入目标主机。

新任务从普通 shell pane 启动 Codex，并把首条指令作为启动参数传入；此时
`tmux send-keys ... Enter` 的接收者是 shell：

```bash
task_id=moveit-expert-baseline
read -r dispatch_id < /proc/sys/kernel/random/uuid
tmux_session=codex-task-${task_id}
target_worktree=/data/work/ws_moveit
evidence_root=/tmp/so101-debug-${task_id}
handoff_path=${evidence_root}/handoff.md
receipt_path=${evidence_root}/dispatch-${dispatch_id}.receipt
codex_bin=/home/lenovo/.local/bin/codex
dispatch_sent=false

if [[ -z "$dispatch_id" || ! -x "$codex_bin" || ! -d "$target_worktree" || ! -d "$evidence_root" \
      || ! -r "$handoff_path" || -e "$receipt_path" ]]; then
  printf 'STOP: dispatch preflight failed\n' >&2
elif ! codex_version=$("$codex_bin" --version) \
    || ! handoff_bytes=$(wc -c < "$handoff_path") \
    || ! handoff_sha=$(sha256sum "$handoff_path"); then
  printf 'STOP: version or handoff read-back failed\n' >&2
elif tmux has-session -t "$tmux_session" 2>/dev/null; then
  printf 'STOP: tmux session already exists: %s\n' "$tmux_session" >&2
elif pane_id=$(tmux new-session -d -P -F '#{pane_id}' -s "$tmux_session" -c "$target_worktree") \
    && [[ "$pane_id" =~ '^%[0-9]+$' ]] \
    && tmux capture-pane -p -J -t "$pane_id" -S -120 > "$evidence_root/dispatch-before.txt"; then
  printf 'CODEX_VERSION=%s\nHANDOFF_BYTES=%s\nHANDOFF_SHA256=%s\n' \
    "$codex_version" "$handoff_bytes" "$handoff_sha"
  if ! tmux send-keys -t "$pane_id" \
      "$codex_bin -C $target_worktree 'Dispatch $dispatch_id. Read $handoff_path completely and execute that task autonomously. The file is the authoritative handoff. Before other task actions, use a shell command to write exactly $dispatch_id to $receipt_path; start now.'" Enter; then
    printf 'STOP: failed to send Codex startup command to %s\n' "$pane_id" >&2
  else
    dispatch_sent=true
  fi
else
  printf 'STOP: failed to create and identify a new tmux pane\n' >&2
fi
```

`/home/lenovo/.local/bin/codex` 是当前 ai-station 的用户级安装约定，使用前必须现场验证；
非交互 zsh 的 PATH 可能找不到裸 `codex`。模型、sandbox 和 approval 参数按任务授权显式
添加，不能从示例中推断权限。

向已有 Codex 任务追加指令时，从另一个 shell 使用 CLI 队列，不向其 TUI composer 注入
按键。优先使用启动时记录或从 Codex 元数据回读的 session UUID；无法确认 UUID 与目标
worktree/任务一致时停止，不凭 tmux 名或相似标题猜测：

```bash
task_id=moveit-expert-baseline
read -r dispatch_id < /proc/sys/kernel/random/uuid
codex_thread=REPLACE_WITH_VERIFIED_CODEX_SESSION_UUID
pane_id=REPLACE_WITH_VERIFIED_TMUX_PANE_ID
evidence_root=/tmp/so101-debug-${task_id}
handoff_path=${evidence_root}/handoff.md
receipt_path=${evidence_root}/dispatch-${dispatch_id}.receipt
codex_bin=/home/lenovo/.local/bin/codex
dispatch_sent=false

if [[ -z "$dispatch_id" || ! -x "$codex_bin" || ! -d "$evidence_root" || ! -r "$handoff_path" \
      || -e "$receipt_path" ]]; then
  printf 'STOP: dispatch preflight failed\n' >&2
elif ! codex_version=$("$codex_bin" --version) \
    || ! handoff_bytes=$(wc -c < "$handoff_path") \
    || ! handoff_sha=$(sha256sum "$handoff_path") \
    || ! "$codex_bin" queue --help >/dev/null \
    || ! tmux capture-pane -p -J -t "$pane_id" -S -120 > "$evidence_root/dispatch-before.txt"; then
  printf 'STOP: version, handoff, queue, or pane read-back failed\n' >&2
else
  printf 'CODEX_VERSION=%s\nHANDOFF_BYTES=%s\nHANDOFF_SHA256=%s\n' \
    "$codex_version" "$handoff_bytes" "$handoff_sha"
  if ! "$codex_bin" queue --thread "$codex_thread" \
      --message "Dispatch $dispatch_id. Read $handoff_path completely and execute that task autonomously. Before other task actions, use a shell command to write exactly $dispatch_id to $receipt_path."; then
    printf 'STOP: codex queue failed for %s\n' "$codex_thread" >&2
  else
    dispatch_sent=true
  fi
fi
```

只有已确认目标 Codex 任务与本次工作一致时才可 queue；不要把 tmux session 名直接当作
`--thread`。若现场 CLI 没有 `queue`，创建新 tmux shell 并使用启动参数，不退回 TUI
按键模拟。若旧任务仍在运行或所有权不明确，不自动创建第二个执行者；停止并报告冲突。

不要用 `tmux load-buffer/paste-buffer` 粘贴正文后再以 `tmux send-keys Enter` 或 `C-m`
提交 Codex TUI。已在 ai-station Codex CLI 0.154.0 验证：tmux 的合成 `Enter` 可作为
LF (`0x0a`) 到达 PTY，被 composer 识别为 `Ctrl-J`/换行；`C-m` 也属于 editor newline
绑定，不是修复。长粘贴还会显示为 `[Pasted Content N chars]`，粘贴突发保护期间紧随的
Enter 可能继续被吸收为换行。tmux 命令退出码为 `0` 只证明字节已发送，不证明任务已提交。

投递后必须 bounded read-back：

```bash
if [[ "$dispatch_sent" != true ]]; then
  printf 'STOP: dispatch command was not accepted by its transport\n' >&2
else
  tmux capture-pane -p -J -t "$pane_id" -S -120 > "$evidence_root/dispatch-after.txt"
  for attempt in {1..10}; do
    test -r "$receipt_path" && break
    sleep 1
  done
  if [[ ! -r "$receipt_path" ]]; then
    printf 'STOP: dispatch receipt was not created\n' >&2
  elif ! receipt_value=$(tr -d '\r\n' < "$receipt_path"); then
    printf 'STOP: dispatch receipt could not be read\n' >&2
  elif [[ "$receipt_value" != "$dispatch_id" ]]; then
    printf 'STOP: dispatch receipt does not match\n' >&2
  else
    printf 'DISPATCH_RECEIPT_OK=%s\n' "$dispatch_id"
  fi
fi
```

在限定时间内取少量 fresh capture；只有本次随机 `dispatch_id` 对应的 receipt 原先不存在、
投递后由 Codex 工具执行创建且内容精确匹配，并看到 handoff 要求的首个探测结果，才记录
`HANDOFF_SUBMITTED`。提示词回显或普通 `Working` 可能属于输入区/上一轮，不能证明接收。
仅看到正文或
`[Pasted Content N chars]` 仍停在输入区不算投递成功；不要连续盲发回车。

上面的 `codex-task-*` 仅是普通 coding session 示例。任务需要 GUI/CUA 时，按下文
`codex-cua` 会话规则复用或创建唯一标准会话，不为同一用途另建第二个 CUA session。

## shell 与 overlay

ai-station 使用 zsh。ROS 命令按以下顺序加载：

```bash
source /opt/ros/jazzy/setup.zsh
cd /data/work/ws_moveit
source install/setup.zsh
```

不要在 zsh 里改用 `setup.bash`。每次 build 后重新 source。使用 `ros2 pkg prefix so101_gazebo_demo_cpp` 验证当前 overlay。

## GUI 进程

GUI screenshot、桌面检查和语义控制必须使用项目内 `$gui-capture`；读取
`.agents/skills/gui-capture/SKILL.md` 后按其当前平台和 agent capability 路由执行。
SO-101 的 provenance、进程所有权和视觉证据门仍由 `$so101-dev` 约束。

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
ros2 run so101_teleop tile_ai_station_guis.py
```

该工具读取当前 EWMH work area，取消两个窗口的最大化状态，将 RViz 放在左侧 50%、Gazebo 放在右侧 50%；屏幕宽度为奇数时多出的 1 px 分给右侧。它等待目标窗口最多 30 秒，并在移动后回读两侧窗口几何。

成功必须同时满足：

- 命令退出码为 `0`，输出 `LAYOUT_OK RVIZ=... GAZEBO=...`；
- 回读位置和尺寸与目标几何的差值不超过默认 `12 px` 装饰边框容差；
- 分屏后用 `$gui-capture` 的 GNOME desktop 模式生成本轮新鲜桌面截图；
- 实际打开新的 `desktop.png`，确认 RViz 左、Gazebo 右，各约占可用工作区 50%，两侧关键场景均可见且没有互相遮挡。

`LAYOUT_ERROR` 或退出码 `2` 表示失败。根据错误检查缺少的窗口、X11 依赖、`DISPLAY` 或窗口几何；不要把命令已发送当成分屏成功。若窗口尺寸正确但内部场景不可辨认，再用 CUA 按 `snapshot -> action -> fresh snapshot` 调整相机或面板，并保存新截图。

## `codex-cua` 会话

`codex-cua` 是标准 CUA 入口：

1. 先用 `tmux list-sessions` 和 `tmux capture-pane -pt codex-cua -S -200` 检查当前窗格与任务。
2. 会话存在且正在工作时，不发送按键、不重启、不抢占；先报告冲突。
3. 只有会话不存在且任务确需 GUI 操作时，才创建同名会话。不要为同一用途新建其他 session。
4. CUA 每次动作前获取 snapshot，动作后获取 fresh snapshot；element 索引只属于产生它的那次 snapshot。
5. 工具回报 `verified=false`、`degraded=true` 或效果不确定时，以新截图/read-back 验证，不把发送动作当成动作生效。

需要 CUA 驱动细节时按 `$gui-capture` 检查当前 agent 已加载的能力与现场 schema；不得把另一个 agent 的会话当作本 agent 的控制能力。

## 视觉证据

先按 `$gui-capture` 判断当前 agent 是否有健康的 CUA 能力。脚本 fallback 只抓取截图；GNOME X11 本机入口为：

```bash
capture_evidence_dir=$(mktemp -d)
.agents/skills/gui-capture/scripts/capture-gui.sh --local --desktop \
  --output-root "$capture_evidence_dir/captures"
```

manifest 声明的 `desktop.png` 必须存在且新鲜。直接运行在 ai-station 时不得 SSH 自身；仅 Mac/orchestrator 使用显式 remote 模式。

验收截图必须：

- 来自本轮动作之后；
- 能看到相关窗口和目标对象；
- 与本轮 log 时间、session 和运行模式对应；
- 由 agent 实际查看图像内容，而不是只检查文件存在或尺寸。

GUI 成功至少要写出“画面中哪一项发生了何种变化”。窗口出现、进程存活或截图生成本身都不是 pick-place 成功。

## 进程所有权与清理

只停止本轮明确启动且 PID/session 可追踪的进程。不要用宽泛 `pkill -f ros`、`killall gz` 或删除共享 tmux 会话。结束后再次列出相关进程和 ROS nodes，说明哪些是保留的既有进程。
