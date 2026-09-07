# Text Agent 多后端 MuJoCo E2E Launch 设计

**日期：** 2026-09-07

**状态：** 已确认设计，等待评审

**代码范围：** `src/so101_demo_py`

**目标平台：** macOS Apple Silicon 与 ai-station NVIDIA GPU

**关联设计：**

- `2026-08-31-text-agent-rgbd-e2e-launch-design.md`
- `2026-08-31-v5-t004-yolo-seg-rgbd-perception-design.md`

## 1. 决策摘要

本设计保留现有两个公开入口，另建自然语言多后端闭环专用入口：

| 入口 | 保留用途 | 本次是否改变行为 |
|---|---|---|
| `so101_mujoco_text_pick_agent.launch.py` | 对应此前 Text Agent 课程，继续使用现有颜色几何感知链路 | 否 |
| `so101_mujoco_perception_pick_place.launch.py` | 不经过自然语言 Planner，直接验证多后端感知到动态抓取 | 否；允许内部改为调用等价的共享构造函数 |
| `so101_mujoco_text_pick_agent_e2e.launch.py` | 自然语言、多后端感知、MoveIt 与 MuJoCo 完整闭环 | 新增 |

新入口不是旧入口的别名，也不替换它们。旧命令、默认值、参数集合、进程顺序和退出语义都要通过回归测试锁定。

2026-08-31 的 Text Agent RGB-D E2E 设计仍是旧 `so101_mujoco_text_pick_agent.launch.py` 的历史依据。本设计把新 E2E launch 定义为完整闭环的规范入口。

## 2. 目标和范围

新入口用一条 `ros2 launch` 命令完成以下链路：

```text
instruction
  -> PlannerPort 生成候选结构
  -> 固定代码验证 plastic_cup + pick
  -> dynamic runtime 建立 /cup_pose 订阅
  -> 选择 color_geometry / yolo_seg / grounded_sam
  -> 唯一实例的 mask + Depth 反投影 + tf2
  -> 新鲜 world /cup_pose
  -> dynamic pick-place state machine
  -> MoveIt 规划与执行
  -> MuJoCo 物理抓取、搬运与放置
  -> Planning Scene 与 MuJoCo 双事实源验收
```

设计要解决四个问题：

1. Planner 拒绝时，不启动动态 runtime，不触发感知，也不发布本次请求的 `/cup_pose`。
2. dynamic runtime 的 subscriber ready 后才触发一次性感知，避免丢失 `/cup_pose`。
3. 顶层 launch 统一拥有进程、传播首个失败，并记录清理阶段的二次错误。
4. `RUNTIME_COMPLETED` 不能单独代表完整闭环成功；机器证据和视觉证据分别验收。

本次不修改检测模型、点云定位算法、动态抓取策略或 Planner provider 的 fallback 规则，也不扩展到 Gazebo、真实机械臂、多轮对话、复合任务和自动物理重试。

## 3. 方案比较

### 3.1 修改旧 Text Agent launch

直接把 `perception_backend` 加进 `so101_mujoco_text_pick_agent.launch.py`，文件最少，但会改变此前课程入口的参数和时序。历史实验难以复现，也容易把旧颜色几何链路与新入口的模型感知验收混在一起，因此不采用。

### 3.2 给 perception launch 增加 workflow 开关

可以增加 `workflow:=dynamic|text_agent`，但一个公开入口将同时承担感知直连和自然语言授权两种语义。使用者无法只看入口名判断是否存在 LLM 和执行授权，不利于安全审计，因此不采用。

### 3.3 新增专用 E2E launch

新增 `so101_mujoco_text_pick_agent_e2e.launch.py`，旧入口保持稳定，新入口显式承担自然语言驱动的完整闭环。它复用感知进程的构造逻辑，不 include 或嵌套另一个业务 launch。顶层直接拥有 MuJoCo、MoveIt、controllers、TF、TextAgent、感知和终态验证进程。

这是本次采用的方案。

## 4. 组件和所有权

### 4.1 顶层 launch

顶层 launch 负责：

- 校验所有 launch 参数；
- 创建唯一 `workflow_id`、simulation `session_id` 和证据目录；
- 启动并监控 MuJoCo、MoveIt、controllers、robot state publisher 和相机 TF；
- 在 `scene_setup` 成功后启动 TextAgent；
- 校验结构化事件并推进阶段；
- 在 `RUNTIME_READY` 后启动唯一的感知进程；
- 保存首个失败和清理失败；
- 在机器证据通过后返回成功，否则返回非零；
- 只清理本次 launch 创建的进程与容器。

顶层 launch 不解析自然语言，不选择目标实例，也不执行 MoveIt 动作。

### 4.2 PlannerPort 和 TextAgent

`PlannerPort` 只把 instruction 转成候选结构，不拥有执行权限。DeepSeek 可以在认证、网络、超时、HTTP 或不可解析输出等 provider 失败时回退到 Ollama。可解析但不能映射为合法 `TaskCommand` 的结果不得 fallback。

`TextAgent` 使用固定代码完成 schema、allowlist、backend、确认方式和执行授权检查。只有合法的：

```text
target_object = plastic_cup
action = pick
constraints = {}
```

才能产生 `DISPATCH_PREVIEW`，随后调用现有 dynamic runtime。LLM 输出不得携带 Pose、关节角、轨迹、速度、ROS topic、shell 命令或执行授权。

### 4.3 dynamic runtime

dynamic runtime 仍在 TextAgent 的 executor 边界内运行。它创建 `/cup_pose` subscriber 并通过结构化事件报告 `RUNTIME_READY`。收到新鲜 pose 后，继续执行 scene identity、Planning Scene、pose 一致性和 reachability preflight。所有预检通过后才创建 runner，并从 `IDLE` 进入 `PREPARE_OPEN_GRIPPER`。

进程启动不等于状态机启动，`RUNTIME_READY` 也不等于运动授权完成。

### 4.4 感知进程

感知 action 由共享构造函数生成：

- `color_geometry` 使用 `rgbd_cup_pose`；
- `yolo_seg` 使用 `rgbd_object_pose --backend yolo_seg`；
- `grounded_sam` 使用 `rgbd_object_pose --backend grounded_sam`。

新入口不 include `so101_mujoco_perception_pick_place.launch.py`。两个 launch 都调用同一组参数解析和 action 构造函数，以免复制 backend、device、模型工件、Docker 和 Grounded SAM 阈值逻辑。

`yolo_seg` 和 `grounded_sam` 必须携带 `--require-output-subscriber`。节点只处理 subscriber ready 和 TF ready 之后的新鲜 RGB-D。0 个杯子返回 `TARGET_NOT_FOUND`，2 个及以上返回 `TARGET_AMBIGUOUS`；这两种情况都不能发布 `/cup_pose`。

### 4.5 终态证据验证器

`RUNTIME_COMPLETED` 只说明 `run_dynamic_execute()` 返回 0。新入口随后运行一次只读的 E2E 证据验证器，并保持 MuJoCo 与 MoveIt 存活。验证器检查：

- workflow、request、simulation session 和 reset epoch 一致；
- dynamic manifest 的终态为 `DONE`，状态轨迹完整；
- controller result、关节反馈和 TCP 变化满足现有动态执行契约；
- MuJoCo 中杯子完成抬升、搬运、释放并在目标区域稳定；
- 最终有桌面支撑接触，无 fingertip contact；
- Planning Scene 的 attached 集合为空；
- `plastic_cup` 已回到 world collision objects，pose 与最终 MuJoCo pose 一致。

验证器通过后发出 `E2E_ACCEPTED`。任一事实缺失或矛盾都发出 `E2E_REJECTED`，顶层返回失败。视觉检查和 1 至 2 分钟视频仍是人工验收，不伪装成 launch 内部的自动判断。

## 5. 公开接口

入口名称：

```bash
ros2 launch so101_demo_py so101_mujoco_text_pick_agent_e2e.launch.py
```

### 5.1 Agent 与执行参数

| 参数 | 默认值 | 规则 |
|---|---|---|
| `instruction` | 无 | 必填，先经过现有 instruction validator |
| `run_mode` | `dry_run` | 完整闭环执行必须显式传 `run_mode:=execute` |
| `execute` | `false` | 必须显式传 `true` |
| `skip_confirmation` | `false` | 一次性 E2E 必须显式传 `true` |
| `headless` | `false` | 自动测试可传 `true`；视频验收使用 `false` |
| `sensor_rendering` | `true` | 只接受 `true` |
| `session_id` | 自动生成 | 使用现有安全字符规则 |
| `evidence_file` | `/tmp` 下唯一文件 | 必须是尚不存在的绝对路径 |
| `readiness_timeout_s` | `90.0` | 正有限数 |
| `perception_startup_timeout_s` | `30.0` | 正有限数 |
| `cup_pose_timeout_s` | `45.0` | 正有限数 |
| `mujoco_scene` | 安装包内 `scene.xml` | 必须是存在的绝对普通文件 |
| `mujoco_initial_keyframe` | `task_start` | 只接受已登记 keyframe |

`--mode execute` 选择完整执行路径，`--execute` 授予执行权限，`--skip-confirmation` 只跳过人工 digest 确认。后者不能绕过 Planner、TaskCommand、backend、provenance、感知、pose 或状态机门禁。

### 5.2 感知参数

新入口声明 perception launch 的完整 backend 参数集：

| 参数组 | 参数 |
|---|---|
| 后端 | `perception_backend` |
| YOLO-Seg | `perception_weights`、`perception_weights_sha256` |
| Grounded SAM | `perception_model_root`、`perception_model_manifest_sha256` |
| 设备 | `perception_device`、`perception_allow_cpu_fallback` |
| Linux 容器 | `perception_runtime`、`perception_container_image`、`perception_source_root` |
| Grounding DINO | `grounding_box_threshold`、`grounding_text_threshold`、`grounding_duplicate_iou`、`grounding_max_candidates` |
| SAM | `sam_mask_quality_threshold`、`sam_min_mask_pixels`、`sam_max_mask_area_ratio` |

`perception_backend` 默认使用 `yolo_seg`，因为新入口承担模型感知闭环。`color_geometry` 只用于诊断和与旧课程结果对照，不能作为该入口的正式感知验收。`grounded_sam` 是同一入口下的可替换模型后端。

backend 专属参数继续 fail-closed：YOLO-Seg 必须给出绝对权重路径和小写 SHA256；Grounded SAM 必须给出绝对 bundle 目录和 manifest SHA256；为错误 backend 提供专属参数时直接拒绝。

### 5.3 平台选择

`perception_runtime=auto` 沿用当前策略：

- macOS 在 host 运行，`perception_device=auto` 解析为 `mps`；
- ai-station Linux 使用已登记 Docker image 和 CUDA；
- CPU 只有显式 `perception_device=cpu` 或同时允许 CPU fallback 时可用；
- CPU 结果不能替代 macOS MPS 或 ai-station CUDA 的正式验收。

YOLO-Seg 在两个平台使用同一个 `.pt` 文件和同一个 SHA256。

## 6. 启动顺序

```text
validate launch arguments
  -> start MuJoCo / controllers / MoveIt / robot_state_publisher / static TF
  -> scene_setup exits 0
  -> start TextAgent only
  -> DISPATCH_PREVIEW
  -> TextAgent calls dynamic runtime
  -> RUNTIME_READY: /cup_pose subscriber exists
  -> start exactly one perception action
  -> PERCEPTION_READY
  -> optional TARGET_SELECTED
  -> CUP_POSE_PUBLISHED
  -> dynamic preflight
  -> IDLE -> PREPARE_OPEN_GRIPPER -> ... -> DONE
  -> RUNTIME_COMPLETED
  -> run E2E evidence validator while stack remains alive
  -> E2E_ACCEPTED
  -> graceful shutdown -> exit 0
```

MuJoCo、MoveIt 和 TF 可以在 Planner 前启动，因为它们只是基础设施，不构成动作授权。dynamic runtime 和感知不能越过 Planner 静态门。感知不能越过 `RUNTIME_READY`，否则一次性 `/cup_pose` 可能在订阅建立前丢失。

`DISPATCH_PREVIEW` 只说明自然语言结果已通过静态门禁，不能触发感知。`RUNTIME_READY` 是启动感知的唯一阶段事件。

## 7. 结构化事件协议

### 7.1 传输

新 E2E 入口使用 stdout 上的 NDJSON 事件，每个事件占一行并立即 flush。事件行固定使用 `SO101_EVENT ` 前缀。launch 的 `OnProcessIO` handler 按目标 process 分别缓冲字节，直到完整换行后再解析；不能假设一次回调正好收到一整行。

新参数 `--emit-workflow-events --workflow-id <id>` 只由 E2E launch 传入 TextAgent、dynamic runtime 和感知 CLI。未启用时，现有 CLI stdout 和退出码保持不变。项目自身的普通诊断写 stderr；第三方库产生的非事件 stdout 只记录，不驱动阶段迁移。

带 `SO101_EVENT ` 前缀但 JSON 或 schema 非法的行属于 `EVENT_PROTOCOL_INVALID`，必须失败。事件只能由固定代码构造；Planner 原始文本和模型输出不能直接成为事件类型、状态或 failure code。

### 7.2 事件字段

每个事件包含：

```json
{
  "schema_version": 1,
  "workflow_id": "text-e2e-7d3a9f",
  "sequence": 1,
  "component": "text_agent",
  "event": "DISPATCH_PREVIEW",
  "status": "OK",
  "timestamp_ns": 1788796800000000000,
  "failure_code": null,
  "payload": {}
}
```

约束如下：

- `schema_version` 必须等于顶层支持的版本；
- `workflow_id` 由本次 launch 内部生成，不作为公共覆盖参数；
- `component` 必须与 `OnProcessIO` 的目标 child 相符；dynamic runtime 在 TextAgent 进程内运行时允许声明 `dynamic_runtime`；
- `sequence` 在同一 `(workflow_id, component)` 内从 1 开始严格递增；
- 顶层另用全局阶段表校验跨组件顺序；
- `timestamp_ns` 使用宿主机时钟，事件到达时不得超过 5 秒；它不能替代 sequence；
- `failure_code` 成功时为 `null`，失败时必须是固定枚举；
- `payload` 只接受该 event 定义的字段，普通 message 不参与控制流。

### 7.3 事件与合法转移

成功路径允许：

```text
STACK_READY
  -> DISPATCH_PREVIEW
  -> RUNTIME_STARTED
  -> RUNTIME_READY
  -> PERCEPTION_READY
  -> [TARGET_SELECTED]
  -> CUP_POSE_PUBLISHED
  -> RUNTIME_COMPLETED
  -> E2E_ACCEPTED
```

方括号表示 `color_geometry` 可以不产生实例选择事件；`yolo_seg` 和 `grounded_sam` 必须产生 `TARGET_SELECTED`。
颜色几何节点即使继续发布诊断帧，也只为当前 workflow 发出第一次 `CUP_POSE_PUBLISHED` 事件；后续 topic 消息不再推进 E2E 阶段。

以下事件可以从所属阶段终止工作流：

- TextAgent：`PLANNER_FAILED`、`COMMAND_INVALID`、`DISPATCH_REJECTED`；
- dynamic runtime：`RUNTIME_FAILED`；
- perception：`PERCEPTION_FAILED`，其 failure code 可以是 `TARGET_NOT_FOUND`、`TARGET_AMBIGUOUS`、Depth、TF、模型或证据错误；
- E2E validator：`E2E_REJECTED`。

缺少前置事件、重复 sequence、乱序、未知 component、旧 workflow、超龄事件或非法跳转都返回 `EVENT_PROTOCOL_INVALID`。例如从 `DISPATCH_PREVIEW` 直接收到 `CUP_POSE_PUBLISHED` 必须失败，不能猜测 subscriber 已经 ready。

## 8. 失败传播

顶层维护：

```text
primary_failure
secondary_failures[]
current_phase
shutting_down
```

首个有效终态失败写入 `primary_failure`，后续失败不会覆盖它。每个 failure 记录 component、failure code、phase、message、process exit code 和 timestamp。

示例：感知先返回 `TARGET_AMBIGUOUS`，随后 MoveIt shutdown timeout。最终主错误仍是 `TARGET_AMBIGUOUS`；MoveIt 超时进入 `secondary_failures`。顶层返回非零，并同时保留两条结构化记录。

如果 child 非零退出但没有先发送合法失败事件，顶层使用 `CHILD_EXITED_WITHOUT_TERMINAL_EVENT`。required long-lived process 在 `E2E_ACCEPTED` 前退出时也是终态失败，即使退出码为 0。controller spawner 仍按一次性进程处理：0 为成功，非零为失败。

## 9. recovery 和资源清理

状态机 recovery 与进程 teardown 是两层工作：

- 状态机根据已经发生的副作用恢复夹爪、物理约束、Planning Scene attachment、world object 和安全 retreat；
- 顶层 launch 负责关闭仍存活的 owned processes 和 owned containers。

当前 MuJoCo execute 路径不创建显式 MuJoCo attachment。杯子依靠双侧接触、摩擦和物理仿真随夹爪移动，`ATTACH_MOVEIT` 只更新 Planning Scene。当前 `RECOVER_DETACH_GAZEBO` 不应被解释成解除一个真实 MuJoCo constraint。以后若引入显式物理 attachment，只有实际 attach 成功后才执行对应 detach。

顶层在业务失败后先给 dynamic runtime 留出 recovery 窗口，再发起全局 shutdown。进程信号按 `SIGINT -> SIGTERM -> SIGKILL` 升级，每一级都有有限超时。信号升级、容器残留或资源销毁异常写入 `secondary_failures`。顶层不能用重置世界来掩盖 recovery 失败。

清理范围包括本次 launch 创建的 TextAgent/dynamic runtime、感知进程或 Docker container、MuJoCo、MoveIt、controllers、robot state publisher、static TF publisher 和终态验证器。DeepSeek、Ollama daemon、其他 tmux 和未知所有权进程不在清理范围内。

## 10. 证据布局

每次运行使用唯一目录：

```text
<run-root>/
  workflow-events.ndjson
  e2e-result.json
  perception/
    result.json
    source-rgb.png
    prediction-overlay.png
    detections.json
    selected-mask.png
    selected-cloud.ply
  dynamic/
    text-agent-provenance/
    dynamic-execute-manifest.json
    ...现有状态机和物理证据...
  acceptance/
    mujoco-final.json
    planning-scene-final.json
    result.json
```

`e2e-result.json` 至少包含：

```text
schema_version
workflow_id
request_id
simulation_session_id
source_commit
installed_prefix
perception_backend
model provenance
event_trace
primary_failure
secondary_failures
runtime_exit_code
physical_outcome
planning_scene_outcome
owned_process_cleanup
artifact_paths
```

写入失败不能留下成功终态。事件文件和结果文件使用原子替换，任何临时文件都留在当前 run root，不写入源码目录。

ai-station 的正式高频证据放在 `/data/work/so101-evidence/text-agent-e2e/<run-id>/`。macOS 的普通调试日志使用唯一 `/tmp/so101-debug-text-agent-e2e-<run-id>/`；需要长期保留的视频和最终证据另行登记，不能只依赖 `/tmp`。

## 11. 自动化测试

实现按 RED -> GREEN 推进，日常测试只运行 `src/so101_demo_py/test/`，不触发 benchmark suite。

### 11.1 兼容性测试

- 两个旧 launch 文件内容仍是 thin wrapper；
- 旧 Text Agent launch 的参数集合、默认值、颜色感知进程和启动顺序不变；
- perception launch 的三个 backend、参数转发、host/Docker 行为和退出语义不变；
- installed launch 集合新增且只新增 E2E launch；
- 新增公共 CLI 参数未启用时，TextAgent 和 perception 的既有 stdout/exit contract 不变。

### 11.2 事件协议测试

- stdout chunk 被任意切分时仍能重组一行事件；
- schema、workflow、component、sequence、timestamp、status 和 payload 严格校验；
- 普通日志不能触发阶段迁移；
- 非法前缀事件、重复、乱序、旧 workflow 和阶段跳转都 fail-closed；
- `RUNTIME_READY` 只能触发一次感知 action；
- 第一次失败保留为 primary，清理错误进入 secondary。

### 11.3 launch contract 测试

- 缺少 `run_mode:=execute`、`execute:=true` 或 `skip_confirmation:=true` 时，不物化任何运行进程；
- scene setup 成功后只启动 TextAgent，不启动感知；
- Planner 拒绝后不出现 dynamic runtime、感知或 `/cup_pose`；
- `DISPATCH_PREVIEW` 不启动感知；
- `RUNTIME_READY` 启动且只启动一个选定 backend；
- backend 参数与证据路径完整传递；
- perception 非零退出会中止等待中的 runtime；
- MoveIt 等 required process 提前退出会立即使顶层失败；
- `RUNTIME_COMPLETED` 后运行证据验证器，只有 `E2E_ACCEPTED` 才返回 0；
- teardown 期间的预期 signal exit 不会覆盖 primary failure。

### 11.4 失败场景

至少覆盖：

| 场景 | 首个失败 | `/cup_pose` | runner |
|---|---|---|---|
| Planner 拒绝 | Planner/TextAgent | 不发布 | 不创建 |
| 两只杯子 | `TargetSelector / TARGET_AMBIGUOUS` | 不发布 | 不创建 |
| 唯一 pose，MoveIt 执行失败 | MoveIt/controller | 已发布 | 启动并进入 recovery |
| runtime 0，但物理证据不合格 | E2E validator | 已发布 | 已结束，顶层仍失败 |
| MuJoCo 成功但 Planning Scene 仍 attached | E2E validator | 已发布 | 已结束，顶层仍失败 |

## 12. 双平台运行验收

新入口在两个平台分别使用 fresh process graph、fresh workflow ID、fresh session 和 fresh evidence root。执行前确认 source、installed prefix、运行 binary、`ROS_DOMAIN_ID` 和 MuJoCo session provenance。

模型后端矩阵：

| 平台 | YOLO-Seg | Grounded SAM |
|---|---|---|
| macOS | 同一 `.pt`，`runtime_device=mps` | 已登记 bundle，实际 MPS/受支持 device |
| ai-station | 同一 `.pt`，`runtime_device=cuda` | 已登记 bundle，实际 CUDA |

每个模型后端在两个平台各完成一次 headless 唯一杯 E2E。正式 1 至 2 分钟视频使用 `yolo_seg`、`headless=false` 和一个 fresh run；视频可在任一已完成运行时 provenance 验证的平台录制。`color_geometry` 的成功只算回归基线。

单次成功必须同时满足：

- TextAgent 记录实际 provider/model/fallback，并产生合法 `plastic_cup + pick + {}`；
- 事件顺序完整，没有协议容错或跳步；
- RGB、Depth、CameraInfo 与 tf2 来自本次运行；
- `/cup_pose` 的 source stamp、frame、workflow/request 关联正确；
- 状态机到 `DONE`，MoveIt/controller/joint/TF 证据一致；
- MuJoCo 中杯子完成抬升、运输、释放和稳定放置；
- Planning Scene 最终 attached 集合为空，world object pose 与 MuJoCo 一致；
- E2E validator 返回 0，顶层 launch 返回 0；
- owned processes 和 container 无残留；
- 可见验收使用本轮完成后的新截图和视频。

另外完成三条负向运行：Planner 拒绝、`v5_two_cups` 歧义、MoveIt 执行失败注入。它们必须返回非零，且物理副作用和清理结果符合第 11.4 节。

## 13. 预计文件边界

实现计划围绕以下文件组织：

```text
src/so101_demo_py/launch/so101_mujoco_text_pick_agent_e2e.launch.py
src/so101_demo_py/src/runtime/launch_composition.py
src/so101_demo_py/src/runtime/perception_launch.py
src/so101_demo_py/src/runtime/workflow_events.py
src/so101_demo_py/src/application/text_agent.py
src/so101_demo_py/src/adapters/pick_place_executor.py
src/so101_demo_py/src/ros/dynamic_runtime.py
src/so101_demo_py/src/cli/text_pick_agent.py
src/so101_demo_py/src/cli/rgbd_cup_pose.py
src/so101_demo_py/src/ros/rgbd_cup_pose_node.py
src/so101_demo_py/src/cli/rgbd_object_pose.py
src/so101_demo_py/src/ros/rgbd_object_pose_node.py
src/so101_demo_py/src/application/e2e_acceptance.py
src/so101_demo_py/src/cli/e2e_acceptance.py
src/so101_demo_py/setup.py
src/so101_demo_py/test/test_workflow_events.py
src/so101_demo_py/test/test_text_pick_agent_e2e_launch.py
src/so101_demo_py/test/test_e2e_acceptance.py
src/so101_demo_py/test/test_rgbd_cup_pose.py
src/so101_demo_py/test/test_text_pick_agent_launch.py
src/so101_demo_py/test/test_perception_pick_place_launch.py
src/so101_demo_py/test/test_package_identity.py
src/so101_demo_py/test/test_installed_provenance.py
```

`perception_launch.py` 只承载 backend 参数解析与感知 action 构造。`workflow_events.py` 只承载事件 schema、编码、流式解码和阶段校验。E2E supervisor 仍由 `launch_composition.py` 组装，不能把自然语言或机器人控制逻辑塞进 launch 文件。

## 14. 完成条件

设计实现完成不等于学习任务已掌握。只有同时具备以下结果，才能进入课程验收：

1. 新 E2E launch 已安装，两个旧 launch 行为不变；
2. 结构化事件、阶段门、失败传播和 cleanup 测试通过；
3. macOS MPS 与 ai-station CUDA 的模型后端 E2E 运行符合第 12 节；
4. Planner 拒绝、两杯歧义和 MoveIt 执行失败三条负向路径 fail-closed；
5. MuJoCo 与 Planning Scene 双事实源均通过；
6. 保存显式启动命令、运行 provenance、结构化证据和 1 至 2 分钟 demo 视频；
7. 学习者能沿事件和机器人状态解释一次成功路径及三种失败路径。

本设计完成后先进行文档评审。评审通过后再单独编写实现计划，不在设计阶段直接修改生产代码。
