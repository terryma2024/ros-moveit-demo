# ai-station 远程、GUI 与 CUA

## 事实与可变项

仓库约定的 SSH 别名是 `ai-station`，ROS 工作区通常是 `/data/work/ws_moveit`，ROS 发行版通常是 Jazzy。这些是需要现场复核的环境约定，不是永久常量。

## 先判定当前执行主机

运行任何 `ssh ai-station` 之前，先确认 coding agent 是否已经直接跑在 ai-station 上。不要用“能否解析 `ai-station` 别名”反推主机身份：远端 agent 的受限环境可能没有该别名或 DNS 解析，但它仍然已经在目标主机上。

从 Mac/orchestrator 投递给 ai-station 上 tmux/Codex 的任务，交接开头必须写明：

```text
你当前直接运行在 ai-station 上。不要 ssh 到 ai-station；仓库、tmux、进程、CloudCompare、CUA 和截图命令都在当前主机直接执行。
```

执行边界：

- coding agent 已在 ai-station：直接运行本机命令，禁止再次 `ssh ai-station`；SSH 别名解析失败不是远端不可达证据。
- orchestrator 在 Mac：用 `ssh ai-station '...'` 进入目标主机，并在交接给远端 agent 时声明执行位置。
- 无法确认：报告 `hostname`、`pwd` 和工作区探测结果，不猜 endpoint，也不把自我 SSH 失败声明为任务阻塞。

只读探测。下面是在 Mac 上执行的写法；已经在 ai-station 上就直接跑引号内的同名命令：

```bash
ssh -o BatchMode=yes ai-station 'hostname; pwd; zsh -lc "cd /data/work/ws_moveit && git rev-parse --show-toplevel && git status --short"'
ssh ai-station 'tmux list-sessions 2>/dev/null || true'
ssh ai-station 'pgrep -af "gz sim|move_group|rviz2|pick_place_state_machine" || true'
```

不要在输出中暴露 SSH 配置、token、proxy 凭据或完整私有环境变量。

## 向 tmux 中的 Codex 投递任务

先区分 tmux pane 是普通 shell，还是已经运行 Codex TUI。长任务先保存到该 task 已登记的 evidence root，回读绝对路径、大小和 SHA256，投递时只发送一条让 Codex 完整读取该文件的短指令。tmux session 名与 Codex session UUID/任务名是两套标识，不得混用。

### 共享 preflight

两条传输路径共用这段检查，先跑完再选路径。以下命令都在 ai-station 本机 zsh 中执行，Mac/orchestrator 先经 SSH 进入目标主机。

```bash
task_id='<stable-task-id>'
dispatch_id=$(cat /proc/sys/kernel/random/uuid)
codex_bin=/home/lenovo/.local/bin/codex
evidence_root=/tmp/so101-debug-${task_id}
handoff_path=${evidence_root}/handoff.md
receipt_path=${evidence_root}/dispatch-${dispatch_id}.receipt
dispatch_message="Dispatch $dispatch_id. Read $handoff_path completely and execute that task autonomously. Before other task actions, use a shell command to write exactly $dispatch_id to $receipt_path."
dispatch_ready=false
dispatch_sent=false

if [[ -z "$dispatch_id" || ! -x "$codex_bin" || ! -d "$evidence_root" \
      || ! -r "$handoff_path" || -e "$receipt_path" ]]; then
  printf 'STOP: dispatch preflight failed\n' >&2
elif ! codex_version=$("$codex_bin" --version) \
    || ! handoff_bytes=$(wc -c < "$handoff_path") \
    || ! handoff_sha=$(sha256sum "$handoff_path"); then
  printf 'STOP: version or handoff read-back failed\n' >&2
else
  printf 'CODEX_VERSION=%s\nHANDOFF_BYTES=%s\nHANDOFF_SHA256=%s\n' \
    "$codex_version" "$handoff_bytes" "$handoff_sha"
  dispatch_ready=true
fi
```

`dispatch_ready` 是 fail-closed 开关：两条传输都在第一行检查它，只有 preflight 全部通过才可能投递。`receipt_path` 已存在说明这个 `dispatch_id` 用过，preflight 会停住而不会重放。`/home/lenovo/.local/bin/codex` 是当前 ai-station 的用户级安装约定，使用前必须现场验证，非交互 zsh 的 PATH 可能找不到裸 `codex`；模型、sandbox 和 approval 参数按任务授权显式添加，不能从示例推断权限。

### 传输 A：从普通 shell pane 启动新 Codex

pane 是普通 shell 时，`tmux send-keys ... Enter` 的接收者是 shell，首条指令作为启动参数传入：

```bash
tmux_session=codex-task-${task_id}
target_worktree=/data/work/ws_moveit

if [[ "$dispatch_ready" != true ]]; then
  printf 'STOP: preflight not passed, nothing sent\n' >&2
elif tmux has-session -t "$tmux_session" 2>/dev/null; then
  printf 'STOP: tmux session already exists: %s\n' "$tmux_session" >&2
elif pane_id=$(tmux new-session -d -P -F '#{pane_id}' -s "$tmux_session" -c "$target_worktree") \
    && [[ "$pane_id" =~ ^%[0-9]+$ ]] \
    && tmux capture-pane -p -J -t "$pane_id" -S -120 > "$evidence_root/dispatch-before.txt"; then
  if tmux send-keys -t "$pane_id" \
      "$codex_bin -C $target_worktree '$dispatch_message; start now.'" Enter; then
    dispatch_sent=true
  else
    printf 'STOP: failed to send Codex startup command to %s\n' "$pane_id" >&2
  fi
else
  printf 'STOP: failed to create and identify a new tmux pane\n' >&2
fi
```

### 传输 B：向已确认的 Codex 任务追加指令

从另一个 shell 使用 CLI 队列，不向运行中的 TUI composer 注入按键。`--thread` 必须用启动时记录或从 Codex 元数据回读的 session UUID；无法确认它对应目标 worktree/任务时停止，不凭 tmux 名或相似标题猜。现场 CLI 没有 `queue` 时改为新建 tmux shell 走传输 A。

```bash
codex_thread=REPLACE_WITH_VERIFIED_CODEX_SESSION_UUID
pane_id=REPLACE_WITH_VERIFIED_TMUX_PANE_ID

if [[ "$dispatch_ready" != true ]]; then
  printf 'STOP: preflight not passed, nothing queued\n' >&2
elif ! tmux capture-pane -p -J -t "$pane_id" -S -120 > "$evidence_root/dispatch-before.txt" \
    || ! "$codex_bin" queue --help >/dev/null; then
  printf 'STOP: pane read-back or queue probe failed\n' >&2
elif "$codex_bin" queue --thread "$codex_thread" --message "$dispatch_message"; then
  dispatch_sent=true
else
  printf 'STOP: codex queue failed for %s\n' "$codex_thread" >&2
fi
```

旧任务仍在运行或所有权不明确时，不自动创建第二个执行者，停下报告冲突。上面的 `codex-task-*` 只是普通 coding session 示例；任务需要 GUI/CUA 时改用下面的 `codex-cua`，不为同一用途另建 CUA session。

**Codex 投递不是执行授权。** AGENTS.md 的 Task model selection 要求“执行 implementation plan”用 tmux 里的 `dst` 启动 DeepSeek Harness TUI；把计划投给 Codex 只适用于该表允许的任务，两者不能互相替代。

### 不要向运行中的 TUI 盲发回车

用 `tmux load-buffer/paste-buffer` 粘贴正文，再用 `tmux send-keys Enter` 或 `C-m` 提交 Codex TUI 是无效做法。已在 ai-station Codex CLI 0.154.0 验证：合成 `Enter` 以 LF (`0x0a`) 到达 PTY，被 composer 当成 `Ctrl-J`/换行，`C-m` 也属于 editor newline 绑定；长粘贴显示成 `[Pasted Content N chars]`，突发保护期间紧随的 Enter 可能继续被吸收。tmux 退出码 `0` 只证明字节已发送，正文停在输入区不算投递成功，也不要连续盲发回车。

### bounded read-back

投递后在限定时间内取少量 fresh capture。只有本次随机 `dispatch_id` 的 receipt 原先不存在、投递后由 Codex 工具执行创建且内容精确匹配，并看到 handoff 要求的首个探测结果，才记录 `HANDOFF_SUBMITTED`；提示词回显或普通 `Working` 可能属于输入区或上一轮，不能证明接收。

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

## shell 与 overlay

ai-station 使用 zsh，ROS 命令按顺序加载，不要在 zsh 里改用 `setup.bash`：

```bash
source /opt/ros/jazzy/setup.zsh
cd /data/work/ws_moveit
source install/setup.zsh
```

每次 build 后重新 source，再用 `ros2 pkg prefix so101_gazebo_demo_cpp` 验证当前 overlay。

## Git push 与 LFS 例外

`GIT_LFS_SKIP_PUSH=1` 只跳过 Git LFS 的 pre-push hook，不上传 LFS 对象，也不从历史或服务端删除对象。默认禁止使用，不得写入 shell profile、Git config 或其他持久环境；只有用户在当前任务中明确授权了具体 remote/ref，才可对该次 push 临时设置。

使用前必须完成三项检查：fetch 并回读远端 ref，记录本地提交、远端旧 SHA 和预期更新方式；用 `git lfs status` 和可达历史检查待推送的 LFS pointer，若待推历史仍引用远端缺失对象就停止，修复 LFS 服务或另行取得重写历史和 force-push 授权，不得用 skip 发布残缺历史；若用户授权删除历史路径，在独立克隆中改写，先保存可恢复 bundle，再校验改写前后 `HEAD^{tree}` 一致，并确认 `git rev-list --objects --all` 不再包含目标路径。

```bash
GIT_LFS_SKIP_PUSH=1 git push origin main
GIT_LFS_SKIP_PUSH=1 git push \
  --force-with-lease='refs/heads/main:<verified-old-sha>' origin main
```

push 后用 `git ls-remote <remote> refs/heads/main` 回读并精确匹配本地 SHA；两个远端映射同一条主线时分别验证，一个远端成功不能代替另一个。服务端可能继续保留已不可达的 LFS 对象，删除可达引用不等于物理清除，彻底清除要走托管平台的 GC 或支持流程。

## GUI 进程与分屏

GUI 截图、桌面检查和语义控制必须使用项目内 `$gui-capture`；读取 `.agents/skills/gui-capture/SKILL.md` 后按其当前平台和 agent capability 路由执行。SO-101 的 provenance、进程所有权和视觉证据门仍由 `$so101-dev` 约束。

任何显示到已登录 GNOME 会话的 GUI 程序都必须由 tmux 持有，并在该 tmux shell 内先加载显示环境、ROS 和本轮 overlay：

```bash
source ~/gui-env.zsh
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_moveit/install/setup.zsh
```

不得硬编码 `DISPLAY`、`XAUTHORITY` 或旧 session bus。长时间 GUI 任务要有明确 tmux session，不要用一次性 SSH shell 承载。

要对 RViz 和 Gazebo 做左右 50% 分屏时，先确认两者已在各自的 tmux-held GUI session 中启动，且没有第二套同类窗口造成识别歧义。检查 X11 依赖：

```bash
command -v xprop && command -v xwininfo && ldconfig -p | rg 'libX11\.so'
```

缺依赖时报告缺项，获得安装授权后使用 Ubuntu 包 `libx11-6` 和 `x11-utils`，不要用硬编码坐标或旧 `DISPLAY` 绕过检查。然后在同一个已加载显示环境的 tmux shell 中执行分屏：

```bash
ros2 run so101_teleop tile_ai_station_guis.py
```

该工具读取当前 EWMH work area，取消窗口最大化，把 RViz 放左侧 50%、Gazebo 放右侧 50%（屏幕宽度为奇数时多出的 1 px 给右侧），等待目标窗口最多 30 秒，并在移动后回读两侧几何。

成功必须同时满足：退出码为 `0` 且输出 `LAYOUT_OK RVIZ=... GAZEBO=...`；回读位置和尺寸与目标几何的差值不超过默认 `12 px` 装饰边框容差；用 `$gui-capture` 的 GNOME desktop 模式生成本轮新鲜桌面截图，并实际打开新的 `desktop.png` 确认 RViz 左、Gazebo 右各约占可用工作区 50%、两侧场景可见且不互相遮挡。`LAYOUT_ERROR` 或退出码 `2` 表示失败，按缺少的窗口、X11 依赖、`DISPLAY` 或窗口几何排查，不要把“命令已发送”当成分屏成功。

## `codex-cua` 会话

`codex-cua` 是标准 CUA 入口。先用 `tmux list-sessions` 和 `tmux capture-pane -pt codex-cua -S -200` 检查窗格与任务；会话存在且正在工作时不发按键、不重启、不抢占，先报告冲突。只有会话不存在且任务确需 GUI 操作时才创建同名会话。

CUA 每次动作前取 snapshot，动作后取 fresh snapshot；element 索引只属于产生它的那次 snapshot。工具回报 `verified=false`、`degraded=true` 或效果不确定时，用新截图或 read-back 验证，不把发送动作当成动作生效。驱动细节按 `$gui-capture` 检查当前 agent 已加载的能力与现场 schema，不得把另一个 agent 的会话当作本 agent 的控制能力。

## 视觉证据

先按 `$gui-capture` 判断当前 agent 是否有健康的 CUA 能力；脚本 fallback 只抓取截图。输出必须落在本 task 已登记的唯一 evidence root 下，不要用裸 `mktemp -d` 另开目录：

```bash
: "${SO101_EVIDENCE_ROOT:?先 export 本 task 已登记的唯一 evidence root}"
test -d "$SO101_EVIDENCE_ROOT" || { printf 'STOP: evidence root missing\n' >&2; exit 1; }
capture_dir="$SO101_EVIDENCE_ROOT/captures/<run-id>"
mkdir -p "$capture_dir" || exit 1
.agents/skills/gui-capture/scripts/capture-gui.sh --local --desktop \
  --output-root "$capture_dir"
```

`SO101_EVIDENCE_ROOT` 是本 task 已登记的唯一 root；manifest 声明的 `desktop.png` 必须存在且新鲜。直接运行在 ai-station 时不得 SSH 自身，仅 Mac/orchestrator 使用显式 remote 模式。

验收截图必须来自本轮动作之后，能看到相关窗口和目标对象，与本轮 log 时间、session 和运行模式对应，并由 agent 实际查看图像内容，而不是只检查文件存在或尺寸。GUI 成功至少要写出“画面中哪一项发生了何种变化”；窗口出现、进程存活或截图生成本身都不是 pick-place 成功。

## 进程所有权与清理

只停止本轮明确启动且 PID/session 可追踪的进程。不要用宽泛 `pkill -f ros`、`killall gz` 或删除共享 tmux 会话。结束后再次列出相关进程和 ROS nodes，说明哪些是保留的既有进程。
