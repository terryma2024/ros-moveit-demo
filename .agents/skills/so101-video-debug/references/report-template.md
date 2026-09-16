# Gazebo / MuJoCo 视频排障报告

> 按本模板的固定 headings 填写 `report.md`。每项都要有证据路径；无法确认时写“未确认”，不要省略 heading。

## 1. Provenance 与后端身份

- 实验目标：
- backend: `gazebo | mujoco`
- 本地 commit / branch / `git status --short`：
- ai-station commit / branch / `git status --short`：
- 安装前缀与工具版本：
- evidence root 与本轮子目录：`/tmp/so101-debug-<task-id>/<run-id>/`
- Gazebo 专属：world、`GZ_PARTITION`、进程 PID；不适用时写 `N/A`。
- MuJoCo 专属：`mujoco_ros2_control` / `so101_mujoco_support` 版本、owner PID、`simulation_session_id`、`reset_epoch`；不适用时写 `N/A`。

## 2. Camera

- 相机类型：`Gazebo GUI camera | MuJoCo Viewer camera`
- preset 与已安装配置路径：
- Gazebo compute/apply receipt 与最终 SDF pose；不适用时写 `N/A`。
- MuJoCo set/get service receipt 与 readback；不适用时写 `N/A`。
- 关注点和覆盖区：机械臂、目标物、桌面操作区、放置区。
- `camera-command.json` 路径：

## 3. 单栈与窗口证据

- 清理前清单：`process-inventory-before.json`
- 清理后清单：`process-inventory-after.json`
- 被停止的 PID 及依据：
- 必须保留和不确定的进程：
- 唯一 backend 窗口 ID、title、class、owner PID：
- 无重复 simulator / MoveIt / controller / `robot_state_publisher` / 任务进程的结论：

## 4. 录屏与任务

- 录屏参数：simulator、encoder、fps、geometry、window ID，来自 `recorder.json`。
- ready probe：`ready-probe.mkv`、`ready-last-frame.png` 和视觉验收结论。
- 任务完整命令：
- 开始/结束 wall-clock 时间：
- 任务退出码与 `pick-place.log`：
- ffprobe：duration、resolution、frame rate、可解码性。

## 5. 低密度马赛克

- `mosaic-low.jpg` 路径、区间、间隔、帧数：
- 最后正常帧与第一异常帧的视频时间：
- 选择该异常边界的可见依据：

## 6. 加密采样记录

每次加密一行，关联 `frames-dense-<NN>/` 和 `mosaic-dense-<NN>.jpg`：

| 轮次 | 区间 (s) | 间隔 (s) | 选择理由和新增视觉证据 |
|---|---|---|---|
| 01 | | | |

## 7. 关键帧时间线

| 视频时间 (s) | wall-clock / monotonic 对齐点 | 事件 | 原图路径 (`keyframes/`) |
|---|---|---|---|
| | | | |

## 8. 可见几何关系

- TCP、固定 TPU 贴片、活动 TPU 贴片和目标物之间的逐帧可见关系：
- 首次接触、脱离或滑动的可见时刻：
- 遮挡或视角造成的不可判断项：

## 9. 共同运行证据对齐

- 状态机 state 与任务退出边界：
- controller goal/result 与 joint error：
- TCP / TF 前后状态：
- MoveIt planning/execution 与 Planning Scene：
- recorder wall-clock、接收端 monotonic 时间和仿真时钟的映射：
- 仿真时钟暂停、reset 跳变或无法对齐的项：

## 10. Gazebo 专属证据

- contact 与 attachment：
- 目标物 world pose、速度与支撑状态：
- world / `GZ_PARTITION` 身份：
- 若 backend 为 MuJoCo：`N/A`。

## 11. MuJoCo 专属证据

- `SimulationEvidence` 的 `simulation_session_id` / `reset_epoch` / source timestamp：
- paused 与仿真时间：
- 目标物 pose、linear/angular velocity：
- table contact、左右 fingertip contact 与力证据：
- Viewer owner PID 与本轮 runtime 的对应关系：
- `task_camera` RGB-D/segmentation 证据（Viewer 视频不能替代）：
- 若 backend 为 Gazebo：`N/A`。

## 12. 分层结论

- `OBSERVED`：视频或日志直接可见的事实。
- `INFERRED`：由多层、同身份和同时间边界证据共同支持的推断。
- `HYPOTHESIS`：尚缺区分性证据的假设。

## 13. 置信度与下一步

- 根因置信度及依据：
- 竞争假设：
- 下一次单变量实验：能区分竞争假设的最小 A/B 修改。

## 14. 未通过项与剩余风险

- 未通过的 gate 或证据层：
- 证据缺口：
- 剩余风险与下一条验证命令：
