# macOS Text Agent RGB-D 端到端摘取 Launch 设计

**日期：** 2026-08-31

**状态：** 2026-08-31 在对话中批准

**运行目标：** 本机 macOS MuJoCo 仿真，`headless=false`

**代码范围：** `src/so101_demo_py`

**设计基线：** `03887b424797a2f644156725742077b970100a0f`

**实现与验收证据根：**
`/tmp/so101-debug-text-agent-e2e-launch-20260831/`

## 1. 目标

新增一个公开 launch，让操作者用一条 `ros2 launch` 命令启动自然语言摘取所需的整套 ROS
运行环境。链路固定为：

```text
自然语言 instruction
  -> DeepSeek Planner，失败时回退到本机 Ollama/qwen3.5:4b
  -> TaskCommand 校验
  -> RGB-D + tf2 生成新鲜 world /cup_pose
  -> DynamicCupPickPlaceExecutor
  -> MoveIt 规划与 controller 执行
  -> MuJoCo 物理摘取、搬运和放置
```

这个 launch 面向 MuJoCo，不扩展到 Gazebo 或真实机械臂。它只接受已有能力：
`plastic_cup + pick + {}`。

## 2. 现有基础

`so101_mujoco_perception_pick_place.launch.py` 已经能启动 MuJoCo、控制器、MoveIt、相机
TF 和 `rgbd_cup_pose`，但最后直接运行 `dynamic_cup_pick_place`。`text_pick_agent` 目前需要
操作者先单独启动运行栈和感知节点，再手工填写 session、reset epoch、source commit、installed
prefix 和 evidence root。

新入口复用现有感知 launch 的运行图和退出策略，只替换工作流节点。旧入口的参数、进程拓扑
和行为保持不变。

## 3. 方案

新增 `so101_mujoco_text_pick_agent.launch.py`，由新的
`build_text_pick_agent_launch_description()` 构建运行图。

不在旧 perception launch 上增加 `workflow:=dynamic|text_agent`。两个入口虽然共用底层 helper，
但公共契约保持分开：旧入口适合直接验证 RGB-D 动态摘取，新入口用于验证自然语言到物理动作
的完整链路。

也不使用 shell 脚本串联 task station 和 text agent。shell 无法可靠拥有所有子进程，也会把
退出码、证据目录和失败边界拆开。

## 4. 公开接口

入口名称：

```bash
ros2 launch so101_demo_py so101_mujoco_text_pick_agent.launch.py
```

launch 参数如下：

| 参数 | 默认值 | 约束 |
|---|---|---|
| `instruction` | 无 | 必填，交给现有 instruction validator |
| `run_mode` | `dry_run` | 执行时必须显式传 `execute` |
| `execute` | `false` | 执行时必须显式传 `true` |
| `skip_confirmation` | `false` | 一次性端到端运行必须显式传 `true` |
| `headless` | `false` | Mac 可见验收使用 `false`，自动测试可用 `true` |
| `sensor_rendering` | `true` | 固定为 `true`，否则没有 RGB-D 数据 |
| `mujoco_initial_keyframe` | `task_start` | 只接受四个已登记杯子点位 |
| `session_id` | 自动生成 | 必须满足现有安全字符规则 |
| `evidence_file` | `/tmp` 下唯一文件名 | 必须是尚不存在的绝对路径 |
| `readiness_timeout_s` | `90.0` | 正有限数 |
| `perception_startup_timeout_s` | `30.0` | 正有限数 |
| `cup_pose_timeout_s` | `45.0` | 正有限数，并传给 text agent executor |

该入口只支持显式跳过确认的一次性执行。需要人工 Preview/digest 确认时，继续使用现有
`text_pick_agent` 两步 CLI，不在 launch 中复制确认协议。

## 5. 组件和进程所有权

launch 拥有以下进程：

- `robot_state_publisher`；
- `mujoco_ros2_control/ros2_control_node`；
- `joint_state_broadcaster`、`arm_controller`、`gripper_controller` 的 spawner；
- `so101_mujoco_support/graceful_shutdown_move_group`；
- `scene_setup`；
- 两个相机 static TF publisher；
- `rgbd_cup_pose`；
- `text_pick_agent`。

DeepSeek 是外部 HTTPS 服务。Ollama 是本机常驻模型服务。launch 继承
`DEEPSEEK_API_KEY` 和 Ollama endpoint，但不启动、重启或停止 Ollama。这样退出 launch 不会
影响用户的其他模型任务。

实现和验收阶段若发现已有 MuJoCo、MoveIt、RGB-D 或 text-agent 进程，先确认所有权。新入口
不 attach 到未知运行栈，也不为了获得干净环境而停止它。

## 6. 启动顺序与数据流

1. OpaqueFunction 先验证执行授权、点位、超时、session、scene 和 evidence path。
2. 创建本次 session 独占的 `perception/` 与 `dynamic/` 目录。
3. 用 canonical execution-provenance resolver 从已导入模块路径解析 source commit，并从
   ament index 解析 `so101_demo_py` package prefix，供 `text_pick_agent` 再次校验。解析过程不依赖
   启动命令所在的当前目录。
4. 启动 MuJoCo、robot state publisher、controller spawner、MoveIt 和 `scene_setup`。
5. `scene_setup` 只有在 controller、MoveIt service/action 和 Planning Scene 都就绪后才退出 0。
6. scene setup 成功后，同时启动 `rgbd_cup_pose` 和 `text_pick_agent`。
7. text agent 完成模型规划与命令校验后，`DynamicCupPickPlaceExecutor` 等待同一 session 的新鲜
   `/cup_pose`，再进入现有动态摘取状态机。
8. text agent 返回后，launch 记录其退出码并关闭自己拥有的其余进程。

模型规划可能先于感知完成，这是允许的。executor 使用 `cup_pose_timeout_s` 等待新鲜 pose，
不会读取上一次运行留下的值。

## 7. Text Agent 调用契约

launch 构造的节点等价于：

```bash
ros2 run so101_demo_py text_pick_agent \
  --instruction '<instruction>' \
  --mode execute \
  --execute \
  --skip-confirmation \
  --backend mujoco \
  --cup-pose-timeout-s <cup_pose_timeout_s> \
  --session-id <session_id> \
  --expected-reset-epoch 0 \
  --evidence-root <dynamic_evidence_root> \
  --source-commit <execution_provenance.source_commit> \
  --installed-prefix <execution_provenance.package_prefix>
```

`expected-reset-epoch` 固定为 `0`，因为每次运行都启动新的 MuJoCo 环境。该 launch 不支持
attach existing stack 或 RESET_WORLD 复用。

## 8. 失败处理与退出

以下情况必须在任何物理执行前失败：

- 缺少 `run_mode:=execute`、`execute:=true` 或 `skip_confirmation:=true`；
- instruction、session、超时、scene 或 evidence path 非法；
- source/install/runtime provenance 不一致；
- controller、MoveIt 或 Planning Scene 未就绪；
- DeepSeek 和 Ollama 都失败，或模型命令未通过校验。

运行期失败包括 RGB-D 超时、`/cup_pose` 过期、不可达、规划/执行失败，以及物理结果验证失败。
这些错误沿用现有 reason code 和 runtime 退出码，不在 launch 中重新解释。

任一 required long-lived 进程在 text agent 完成前退出，都使 launch 失败。spawner 退出 0 是正常
的一次性行为；非零退出会关闭整条链路。text agent 不论成功或失败都只运行一次，不自动重试
物理请求。

清理只覆盖本 launch 启动的进程。DeepSeek、Ollama、其他 tmux 和未知所有权 ROS 进程不在
清理范围内。

## 9. 证据布局

每次运行使用新的 `evidence_file`。实际证据位于同名 `.d/<session_id>/`：

```text
<run>.d/<session_id>/
  perception/
    cup.ply
    summary.json
  dynamic/
    text-agent-provenance/
    ...现有 dynamic runtime artifacts...
```

终端输出保留 text agent 的 request ID、provider/model、fallback 标志、TaskCommand、状态轨迹、
runtime session ID 和 execution provenance。日志不得记录 API key、完整环境变量或原始模型响应。

## 10. 自动化测试

先补 launch contract 测试并观察 RED，再实现生产代码。测试至少覆盖：

- 新公开 launch 文件存在且保持 thin；
- 参数默认值和四个 keyframe choices；
- 缺少三重执行授权时不物化任何节点；
- scene setup 成功后只启动一个 `rgbd_cup_pose` 和一个 `text_pick_agent`；
- text agent 收到精确的 instruction、timeout、session、epoch、evidence 和 provenance 参数；
- 自动 provenance 解析不依赖 launch 的当前工作目录；
- required process、spawner、scene setup 和 text agent 的失败都传播到 launch；
- text agent 成功后退出 0，并允许其余 owned process 正常 teardown；
- 旧 perception launch 的节点和参数不变；
- installed launch 集合包含新文件。

随后执行 macOS `so101_demo_py` 定向测试、完整 package test、fresh build、installed
`--show-args` 和 fail-closed smoke test。

## 11. 本机四点验收

以下四个点位各跑一次独立 `FULL_RESTART`，不能用 RESET_WORLD 或同一常驻 stack 混算：

1. `task_start`
2. `cup_test_forward_5cm`
3. `cup_test_left_5cm`
4. `cup_test_right_5cm`

每次运行固定：

- `headless=false`；
- `sensor_rendering=true`；
- 同一自然语言 instruction；
- 新 session ID、request ID、evidence file 和 ROS log 目录；
- 当前 candidate source commit 和 installed overlay。

单点只有同时满足下列事实才记为成功：

- text agent 输出受支持的 `plastic_cup + pick + {}`，并记录实际 provider/model；
- RGB、Depth、CameraInfo 尺寸和编码正确，深度中有有限正值；
- 新鲜 `world` `/cup_pose` 与该点位对应，并被 dynamic runtime 消费；
- 动态状态机完成 19 个 transition，controller action、关节反馈和 TCP/FK 发生预期变化；
- MuJoCo 中杯子完成抬升、搬运、释放并在目标区域稳定；
- 最终 `table_contact=true`，无 fingertip contact；
- MoveIt `attached_object_ids=[]`，`plastic_cup` 回到 world collision objects；
- post-DONE 新截图显示同一 MuJoCo Viewer 中的最终状态；
- launch 退出 0，且本轮 owned process 没有残留。

topic 存在、`DONE`、模型 JSON 或截图中的任意单项都不能代替这组联合证据。无效 preflight
不计入四点结果，修复污染后必须使用新的 session 重跑该点。

## 12. 不在本次范围内

- 启动或管理 Ollama daemon；
- Gazebo backend；
- 真实机械臂执行；
- 多轮对话或复合任务；
- 自动重试自然语言请求或物理动作；
- 复用常驻 task station；
- 修改现有 dynamic pick policy、感知算法或 MuJoCo 四个预制点位。
