---
name: gazebo-video-debug
description: Use when recording a Gazebo window as pick-place evidence, diagnosing a pick-place failure from recorded video, running ready-frame (ready probe) checks before execute, doing hierarchical frame extraction (low-density mosaic to dense interval to keyframes), or analyzing visual/TCP/fixed-pad/moving-pad contact relations. 必须与 $so101-dev 同时使用;遵循其 provenance、单栈、A/B 隔离、构建-source 和新鲜视觉证据规则。
---

# Gazebo 视频排障

本 skill 用于 ai-station 上 SO101 Gazebo 抓取实验的可复现视频取证:相机就位、单栈就绪、精确录屏、分层抽帧和证据对齐报告。判断与排序在 Codex;工具只做确定性的原子操作,不提供端到端脚本。

**必须同时使用 `$so101-dev`**。本 skill 继承其全部证据规则:provenance 三层确认、单栈前提、A/B 单变量隔离、构建后重新 source 验证安装产物、结论按 `OBSERVED / INFERRED / HYPOTHESIS` 分层、用本轮新鲜截图验收。

## 工具与证据目录

所有工具以安装产物调用,一律使用 `ros2 run so101_gazebo_demo <tool>`:

- `tile_ai_station_guis.py --maximize gazebo`(无参数调用仍保持左右分屏)
- `gazebo_camera_pose.py compute --config <yaml> --preset <left-front|right-front|left-rear|right-rear> --json <path>` 与 `apply --world <sdf> --pose-json <path>`
- `so101_stack_inventory.py [--json <path>]`(只读)
- `gazebo_window_recorder.py start --output <mkv> --state <json>` / `status --state <json>` / `stop --state <json>`
- `video_extract_frame.py --input <video> --at <last|seconds> --output <png>`
- `video_sample_frames.py --input <video> --start <s> --end <s> --interval <s> --max-width <px> --output-dir <dir>`
- `video_mosaic.py --frames <dir> --columns <n> --output <jpg> --max-width <px>`

每次实验建立独立证据目录 `/tmp/so101-video-debug-<UTC>/`,布局:`manifest.json`、`process-inventory-before.json`、`process-inventory-after.json`、`camera-pose.json`、`ready-probe.mkv`、`ready-last-frame.png`、`run.mkv`、`recorder.json`、`recorder.log`、`pick-place.log`、`frames-low/`、`mosaic-low.jpg`、`frames-dense-<NN>/`、`mosaic-dense-<NN>.jpg`、`keyframes/`、`report.md`。

## 工作流程与判断门

按顺序经过以下 gate;每个 gate 由 Codex 实际查看证据后决定是否继续,不得跳步。

1. **Provenance**:记录本地和 ai-station 的 commit、branch、`git status --short`、安装前缀和工具版本,写入 `manifest.json`。按 `$so101-dev` 规则从运行进程、安装产物和 source tree 三者确认版本。
2. **Camera compute/apply**:从四个 preset 选一个 compute;人工核对数值和 SDF diff 后才 apply。数学覆盖只是候选,最终视角由 ready 末帧验收。
3. **Inventory/精确清理**:运行 `so101_stack_inventory.py` 存为 `process-inventory-before.json`。把资源分为“本轮停止”“必须保留”“不确定”;只向确认属于本轮旧 stack 的 PID 发正常终止信号,超时后对同一 PID 升级。再次 inventory 存 `process-inventory-after.json`,证明无重复 Gazebo、MoveIt、controller、robot_state_publisher 或抓取进程。
4. **GUI/maximize**:在明确 tmux session 中 source `~/gui-env.zsh`、ROS Jazzy 和最新 workspace overlay(不得硬编码 `DISPLAY`/`XAUTHORITY`)。启动必要服务和唯一 Gazebo GUI,然后 `tile_ai_station_guis.py --maximize gazebo`,必须输出 `LAYOUT_OK`。
5. **1 秒 probe 与视觉判断**:录制约 1 秒 `ready-probe.mkv`,正常 stop 后提取 `ready-last-frame.png`。**实际查看图片**:确认完整机械臂、杯子、桌面和放置区可见,无加载空白、错误对话框或严重遮挡。ready 未通过不得进入下一步。
6. **正式录屏与 pre-roll**:`gazebo_window_recorder.py start` 录 `run.mkv`,`status` 确认在录且文件增长。保留 2–3 秒 pre-roll(抓取程序启动前的稳定场景)。
7. **独立启动任务**:单独命令启动抓取程序,记录完整命令、wall-clock 开始时间、日志路径(`pick-place.log`)和退出码。录屏与任务不得封装成同一条命令。
8. **立即停止录屏**:任务返回后(无论退出码)立即 `stop`;用 ffprobe 验证 duration、resolution、frame rate 和可解码性。
9. **低密度马赛克**:首轮采样最多约 12–16 帧,初始间隔通常 2 秒,存入 `frames-low/` 并拼 `mosaic-low.jpg`。查看马赛克,标出最后正常帧和第一异常帧,**写下选择该区间的视觉证据**。
10. **选定加密区间**:只对夹住异常边界的区间以 0.5 秒间隔采样(`frames-dense-01/` 等);仍夹不住则改 0.1 秒或逐帧。相邻帧已夹住关键事件或达到原视频帧率极限即停止。连续两轮加密无新增区分性证据时,停止机械抽帧,改提新相机角度或状态边界取证方案。
11. **关键帧**:把关键帧原分辨率版本存入 `keyframes/`(不只留缩略图),形成带时间的帧时间线。
12. **运行证据对齐**:视频只证明可见现象。把关键帧与状态机 state/任务退出边界、controller goal/result 与 joint error、Gazebo contact/attachment/杯 world pose、TCP 与固定/活动 TPU 贴片的实际表面几何、MoveIt planning/execution 证据对齐。时间无法对齐时在报告中标记“未确认”。
13. **分层报告**:按 [`references/report-template.md`](references/report-template.md) 的固定 headings 写 `report.md`,结论分 `OBSERVED / INFERRED / HYPOTHESIS`,并给出置信度、竞争假设和下一次单变量实验。

## 明确禁止

- ready probe 未通过就启动抓取任务。
- 存在多个 Gazebo 窗口时继续录屏或最大化;先清理歧义再重试。
- 只凭视频宣称根因;必须有至少一层机器人运行证据对齐。
- 未说明所选区间和理由就加密采样;密度与区间由 Codex 决定并记录,工具不得自选。
- 宽泛 `pkill -f ros`、`killall gz` 等;只能按 inventory 结果精确选择 PID。
- 录全屏或音频;只录唯一 Gazebo client region。
- 覆盖已有证据文件;输出已存在时换显式新路径。
- 把录屏、抓取、抽帧、报告串成端到端命令。

## 错误处理

- ready probe 不可解码:不启动抓取,查 `recorder.log` 与 ffmpeg 输出。
- recorder state 已存在:先 `status`,不覆盖 state,不猜测旧 PID。
- ffmpeg 异常退出:保留 MKV 和日志,独立 remux/salvage;不得伪造成功 metadata。
- 抓取程序失败:仍立即停止录屏并进入分析;失败样本不得删除或覆盖。
- 画面缺对象或仍在加载:等待或修复 stack;进程存在不等于 ready。
