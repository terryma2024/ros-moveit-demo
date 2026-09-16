---
name: so101-video-debug
description: Use when recording or analyzing SO-101 pick-place video in Gazebo or MuJoCo, checking a ready frame before execute, narrowing a failure with hierarchical frame extraction, or comparing visible gripper/object contact with simulator and robot evidence.
---

# 仿真器视频排障（Gazebo / MuJoCo）

本 skill 用于 ai-station 上 SO-101 Gazebo 或 MuJoCo 抓取实验的视频取证：固定仿真后端与视角，确认唯一窗口，录制 ready probe 和正式运行，再把关键帧与机器人及仿真器证据对齐。工具只做确定性的原子操作；区间选择、证据判断和报告由 Codex 完成。

**必须同时使用 `$so101-dev` 和 `$gui-capture`。** 本 skill 继承 `$so101-dev` 的 provenance、单栈、A/B 单变量隔离、构建后重新 source、唯一 evidence root 和新鲜视觉证据规则。截图及 GUI 控制按 `$gui-capture` 路由。结论继续分为 `OBSERVED / INFERRED / HYPOTHESIS`。

## 后端选择

开始时在 `manifest.json` 写入 `backend: gazebo | mujoco`。后续相机、窗口、录屏和物理证据必须使用同一个值，不得在同一轮实验中切换 backend。需要比较两个仿真器时，分别建立实验记录和视频，不把两个生命周期拼成一次运行。

| 项目 | Gazebo | MuJoCo |
|---|---|---|
| 可见窗口 | 唯一 Gazebo client | `headless:=false` 的唯一 MuJoCo Viewer |
| 视角设置 | SDF GUI camera pose | viewer camera preset 服务 |
| 物理事实 | contact、attachment、杯 world pose | `SimulationEvidence`、杯 pose/velocity、support/fingertip contact |
| 身份边界 | world / process / `GZ_PARTITION` | `simulation_session_id` / `reset_epoch` / MuJoCo owner PID |

MuJoCo Viewer 只用于操作员视角，它不是 `task_camera` RGB-D 传感器。Viewer 视频不能证明感知节点实际收到的 RGB、depth、segmentation 或 `CameraInfo`。

## 工具和证据目录

所有运行工具必须来自已确认的安装产物：

- 窗口布局：`ros2 run so101_teleop tile_ai_station_guis.py --maximize <gazebo|mujoco>`。无参数调用仍使用 RViz / Gazebo 默认分屏；MuJoCo 分屏用 `--right mujoco`。
- 只读清单：`ros2 run so101_teleop so101_stack_inventory.py [--json <path>]`。
- 仿真器录屏：Gazebo 使用 `ros2 run so101_teleop simulator_window_recorder.py start --simulator gazebo --output <mkv> --state <json>`；MuJoCo 还必须传入本轮 runtime PID：`start --simulator mujoco --owner-pid <pid> --output <mkv> --state <json>`。检查和停止分别使用 `status --state <json>`、`stop --state <json>`。`gazebo_window_recorder.py` 是保留的兼容入口，新命令使用 simulator-neutral 入口。
- Gazebo 视角：`gazebo_camera_pose.py compute --config <yaml> --preset <left-front|right-front|left-rear|right-rear> --json <path>`，确认数值与 SDF diff 后再运行 `apply --world <sdf> --pose-json <path>`。
- MuJoCo 视角：`ros2 run so101_demo_py camera_preset --backend mujoco <preset>`。preset 以已安装的 `config/mujoco/camera_views.yaml` 为准；当前标准项包括 `table_corner_nw`、`table_corner_ne`、`table_corner_se`、`table_corner_sw` 和 `top_down`。命令必须成功并完成服务 readback。
- 后处理：`video_extract_frame.py`、`video_sample_frames.py` 和 `video_mosaic.py` 仍由 `so101_gazebo_demo_cpp` 安装；它们处理普通视频文件，不依赖仿真后端。

`simulator_window_recorder.py` 当前支持 ai-station 的 GNOME X11 窗口录制。GNOME Wayland、macOS 或 headless MuJoCo 没有满足该契约的窗口时，按 `$gui-capture` 保存可用截图并把视频 gate 标记为未通过；不得改录全屏或把截图序列描述成完整录屏。

整个任务只登记一个 `/tmp/so101-debug-<task-id>/` evidence root。每轮实验在其中使用不重复的子目录，例如 `<run-id>/`，包含：

```text
manifest.json
process-inventory-before.json
process-inventory-after.json
camera-command.json
ready-probe.mkv
ready-last-frame.png
run.mkv
recorder.json
recorder.ffmpeg.log
pick-place.log
frames-low/
mosaic-low.jpg
frames-dense-<NN>/
mosaic-dense-<NN>.jpg
keyframes/
report.md
```

## 工作流程与判断门

按顺序经过以下 gate。每一步都由 Codex 查看证据后决定是否继续。

1. **Provenance 和 backend 冻结**：记录本地与 ai-station 的 commit、branch、`git status --short`、安装前缀、工具版本和 `backend`。从运行进程、安装产物和 source tree 三层确认版本。MuJoCo 还要记录 `mujoco_ros2_control`、`so101_mujoco_support`、owner PID、`simulation_session_id` 和 `reset_epoch`；尚未生成的运行身份写 `PENDING`，启动后补齐。
2. **相机设置与 readback**：Gazebo 先 compute，人工核对数值和 SDF diff 后 apply。MuJoCo 只用已安装 preset，通过服务设置并读回相机状态。数学覆盖或服务成功都只是候选，最终视角由 ready 末帧验收。
3. **Inventory 与精确清理**：保存清理前清单，把资源分为“本轮停止”“必须保留”“不确定”。只向确认属于本轮旧 stack 的 PID 发送正常终止信号，超时后才对同一 PID 升级。保存清理后清单，证明选定 backend、MoveIt、controller、`robot_state_publisher` 和任务进程没有重复。同一任务域同时出现 Gazebo 与 MuJoCo 时停止，先消除后端歧义。
4. **GUI 与唯一窗口**：在明确的 tmux session 中 source `~/gui-env.zsh`、ROS Jazzy 和本轮 overlay，不硬编码 `DISPLAY` 或 `XAUTHORITY`。MuJoCo 必须以 `headless:=false` 启动。运行 `tile_ai_station_guis.py --maximize <backend>`，要求 `LAYOUT_OK`。窗口为零或多于一个都不能录屏；截图和内部 GUI 控制交给 `$gui-capture`。
5. **1 秒 ready probe**：用 simulator-neutral recorder 录制约 1 秒；MuJoCo 的 `--owner-pid` 必须来自本轮 inventory，不得从窗口标题猜测。正常 stop 后提取 `ready-last-frame.png`。实际查看原图，确认机械臂、目标物、桌面和放置区完整可见，没有加载空白、错误对话框或严重遮挡。ready 未通过，不得启动抓取任务。
6. **正式录屏与 pre-roll**：启动 `run.mkv`，用 `status` 确认 `phase=recording`、仿真器字段正确且文件增长。抓取程序启动前保留 2–3 秒稳定画面。
7. **独立启动任务**：用另一条命令启动抓取程序，记录完整命令、wall-clock 开始时间、日志路径和退出码。录屏与任务不得封装成同一条命令。
8. **立即停止录屏**：任务返回后，无论退出码如何都立即 stop。用 ffprobe 验证 duration、resolution、frame rate 和可解码性，并确认 `recorder.json` 中的 `simulator` 与 manifest 一致。
9. **低密度马赛克**：首轮取约 12–16 帧，通常从 2 秒间隔开始。查看 `mosaic-low.jpg`，标出最后正常帧和第一异常帧，写明选择该边界的可见依据。
10. **选定加密区间**：只对夹住异常边界的区间以 0.5 秒采样；仍夹不住时改为 0.1 秒或逐帧。相邻帧已经夹住关键事件，或达到原视频帧率极限时停止。连续两轮没有新增区分性证据时，改用新视角或状态边界取证，不继续机械加密。
11. **关键帧**：将关键帧的原分辨率版本保存到 `keyframes/`，形成带视频时间的帧时间线，不只保留缩略图。
12. **运行证据对齐**：视频只证明可见现象。共同证据包括状态机边界、任务退出、controller goal/result、joint error、TCP/TF 和 MoveIt planning/execution。Gazebo 对齐 contact、attachment 和杯 world pose；MuJoCo 对齐 `SimulationEvidence` 的 session/epoch、仿真时间、paused、杯 pose/velocity、table contact 和左右 fingertip contact。`/clock` 或 MuJoCo simulation time 可能暂停或在 reset 时跳变，不能直接用视频秒数相减；必须用 recorder wall-clock、接收端 monotonic 时间和同一 session/epoch 的事件建立对应关系。无法对齐的项写“未确认”。
13. **分层报告**：按 [`references/report-template.md`](references/report-template.md) 的固定 headings 写 `report.md`，给出置信度、竞争假设和下一次单变量实验。

## 明确禁止

- ready probe 未通过就启动抓取任务。
- 窗口为零、窗口重复或 backend 不明确时继续最大化或录屏。
- 用 MuJoCo Viewer 视频证明 `task_camera` 传感器数据，或用 Gazebo/MuJoCo 视频单独宣称根因。
- 混用 Gazebo contact 与 MuJoCo `SimulationEvidence`，或跨 `simulation_session_id` / `reset_epoch` 拼接证据。
- 未说明区间和理由就加密采样。密度与区间由 Codex 决定并记录，工具不得自选。
- 使用宽泛的 `pkill -f ros`、`killall gz`、`killall mujoco`。只能根据 inventory 精确选择本轮 PID。
- 录全屏或音频。只录唯一的选定仿真器 client region。
- 覆盖已有证据文件，或把录屏、抓取、抽帧和报告串成一个端到端命令。

## 错误处理

- 安装产物没有 `simulator_window_recorder.py`、`--simulator mujoco` 或 MuJoCo 窗口分类：停止并按 `$so101-dev` 重新 build、source 和验证 package prefix，不能退回源码直跑后宣称 installed workflow 已通过。
- MuJoCo camera service 不可用或 readback 不一致：不录 ready probe；检查 `headless:=false`、owner PID、服务与 overlay provenance。
- ready probe 不可解码：不启动任务，检查 `recorder.ffmpeg.log` 和 ffmpeg 输出。
- recorder state 已存在：先运行 status，不覆盖 state，也不猜测旧 PID。
- ffmpeg 异常退出：保留 MKV 与日志，独立 remux/salvage，不伪造成功 metadata。
- 抓取程序失败：仍立即停止录屏并进入分析；失败样本不得删除或覆盖。
- 画面缺对象、仍在加载或 Viewer 属于错误 PID：修复 stack 后重做 ready probe。进程存在不等于 ready。
