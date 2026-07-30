# Gazebo 视频排障报告

> 按本模板的固定 headings 填写 `report.md`。每一项都要有证据路径支撑;无法确认的写“未确认”,不得省略 heading。

## 1. Provenance

- 实验目标:
- 本地 commit / branch / `git status --short`:
- ai-station commit / branch / `git status --short`:
- 安装前缀与工具版本:
- 证据目录:`/tmp/so101-video-debug-<UTC>/`

## 2. Camera

- preset:`left-front | right-front | left-rear | right-rear`
- 关注点(杯子与夹爪交互区域中心):
- 覆盖 AABB(机械臂、杯子、桌面操作区、放置目标区):
- 计算距离(含安全边距):
- 最终 SDF pose 与 `camera-pose.json` 路径:

## 3. 单栈证据

- 清理前清单:`process-inventory-before.json`
- 清理后清单:`process-inventory-after.json`
- 被停止的 PID 及依据:
- 单栈结论(无重复 Gazebo / MoveIt / controller / robot_state_publisher / 抓取进程):

## 4. 录屏与任务

- 录屏参数(encoder、fps、geometry、window ID,来自 `recorder.json`):
- ready probe:`ready-probe.mkv` + `ready-last-frame.png`,视觉验收结论:
- 任务完整命令:
- 开始/结束 wall-clock 时间:
- 任务退出码与 `pick-place.log` 路径:
- ffprobe 验证(duration、resolution、frame rate、可解码性):

## 5. 低密度马赛克

- `mosaic-low.jpg` 路径、区间、间隔、帧数:
- 最后正常帧与第一异常帧(时间):

## 6. 加密采样记录

每次加密一行,格式:`frames-dense-<NN>/` + `mosaic-dense-<NN>.jpg`:

| 轮次 | 区间 (s) | 间隔 (s) | 选择理由(视觉证据) |
|---|---|---|---|
| 01 | | | |

## 7. 关键帧时间线

| 时间 (s) | 事件 | 原图路径(`keyframes/`) |
|---|---|---|
| | | |

## 8. 可见几何关系

- TCP、固定 TPU 贴片、活动 TPU 贴片、目标物(杯子)之间的可见关系逐帧描述:
- 首次接触/脱离/滑动的可见时刻:

## 9. 运行证据对齐

- 状态机 state 与任务退出边界:
- controller goal/result 与 joint error:
- Gazebo contact、attachment 与杯 world pose:
- TCP pose 与贴片实际表面几何:
- MoveIt planning/execution 证据:
- 时间无法对齐的项(标记“未确认”):

## 10. 分层结论

- `OBSERVED`(视频或日志直接可见的事实):
- `INFERRED`(由多层证据共同支持的推断):
- `HYPOTHESIS`(尚缺区分性证据的假设):

## 11. 置信度与下一步

- 根因置信度及依据:
- 竞争假设:
- 下一次单变量实验(能区分竞争假设的最小 A/B 修改):

## 12. 未通过项与剩余风险

- 未通过的 gate 或证据层:
- 证据缺口:
- 剩余风险与建议:
