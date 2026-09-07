# Text Agent Multibackend MuJoCo E2E Launch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增自然语言多后端 MuJoCo 闭环入口，在明确授权、唯一目标、动态执行与双事实源验证全部通过后返回成功，并保留两个旧入口的行为。

**Architecture:** 在 `launch_composition.py` 组装 E2E supervisor，复用抽出的感知参数解析与 action 构造函数。TextAgent、dynamic runtime 和感知通过严格校验的结构化事件连接；终态验证器独立读取 MuJoCo 与 Planning Scene，顶层负责失败记录及 owned resources 清理。

**Tech Stack:** Python、ROS 2 Jazzy launch/rclpy、MoveIt 2、MuJoCo、PyTorch MPS/CUDA、YOLO-Seg、Grounded SAM、pytest、NDJSON。

**Spec:** [2026-09-07-text-agent-multibackend-mujoco-e2e-launch-design.md](../specs/2026-09-07-text-agent-multibackend-mujoco-e2e-launch-design.md)。执行者必须一起阅读设计与本计划。

## Global Constraints

- 新入口：`so101_mujoco_text_pick_agent_e2e.launch.py`。旧 `so101_mujoco_text_pick_agent.launch.py` 与 `so101_mujoco_perception_pick_place.launch.py` 的参数集合、默认值、进程顺序、stdout/exit contract 保持兼容。
- 必填 `instruction`；`run_mode=dry_run`、`execute=false`、`skip_confirmation=false`。完整执行须显式 `run_mode:=execute execute:=true skip_confirmation:=true`，任一缺失在创建运行进程之前拒绝。
- `headless=false`、`sensor_rendering=true` 且只接受 `true`；`session_id` 自动生成，沿用安全字符规则。`mujoco_scene` 默认安装包的 `scene.xml`，须为存在的绝对普通文件；`mujoco_initial_keyframe=task_start`，只允许 `MUJOCO_CUP_KEYFRAMES`。
- `evidence_file` 默认 `/tmp` 内唯一文件，须是尚不存在的绝对路径。`readiness_timeout_s=90.0`、`perception_startup_timeout_s=30.0`、`cup_pose_timeout_s=45.0`，全部正有限。
- `perception_backend=yolo_seg`；`color_geometry` 只作诊断；`grounded_sam` 是正式可替换后端。YOLO-Seg 必须提供绝对权重路径和小写 SHA256；Grounded SAM 必须提供绝对 bundle 目录和 manifest SHA256；错配的后端专属参数直接拒绝。
- `perception_runtime=auto`：macOS host/MPS，ai-station 登记的 Docker/CUDA。CPU 须显式选择或显式允许 fallback，不能替代正式 MPS/CUDA 验收；两平台 YOLO-Seg 使用相同 `.pt` 与 SHA256。
- Planner 只产生候选。固定代码仅接受 `plastic_cup + pick + {}`；禁止模型输出 Pose、关节角、轨迹、速度、topic、shell 和执行授权。保留当前 provider fallback 边界。
- dynamic runtime 在 executor 内运行，subscriber 建立后才发 `RUNTIME_READY`；pose、scene identity、Planning Scene、reachability 全部通过后才创建 runner。
- `SO101_EVENT ` + NDJSON，schema version `1`，每行 flush。内部生成 `workflow_id`，不得增加公共覆盖参数。component 内 sequence 从 `1` 严格递增，事件到达时年龄不超过 `5` 秒。
- 未启用 `--emit-workflow-events --workflow-id` 时保持旧 CLI 行为；启用时项目诊断走 stderr，第三方普通 stdout 不推进阶段。
- 不改变模型、定位算法、抓取策略、provider fallback；不扩展到 Gazebo、实机、多轮对话、复合任务、自动物理重试。
- 日常测试仅 `src/so101_demo_py/test/`；本计划不运行 `benchmark_test`。不改 learner 进度，不把工程验收记为掌握。
- 先读取本地 `so101-dev`；持久中文说明使用 `humanizer-zh`，README 使用英语及 `humanizer`；教学指南只能写入 `docs/guides/`。
- 保留用户改动；不使用 `gh`、force-push、全局进程清理或 `ament_uncrustify --reformat`。任务内提交只包含该任务文件；本计划不授权 push/merge。

## 当前代码与本次计划边界

2026-09-07 本地核对：工作区 `/Users/matianyi/Projects/robot_demo_001/moveit-demo`，主机 `matianyideMacBook-Air.local`，分支 `main`，commit `ef9466c602da710ec89d4ca5c36dd0d7596a83c4`；开始时工作区干净。子模块 `third_party/mujoco_ros2_control` 为 `71bc9346cf93d6227a6678fcacf63f3e18acfcba`。这些是计划基线，执行时重新确认。

已核对的实现位置：

| 当前文件/符号 | 现状与计划用途 |
|---|---|
| `src/so101_demo_py/src/runtime/launch_composition.py` | 已有 `_mujoco_stack_actions`、两个旧 builder；感知参数解析和 host/Docker action 目前在同一大文件，按职责抽取 |
| `src/so101_demo_py/src/application/text_agent.py:TextAgent._handle` | 已有 Planner、TaskCommand、确认与授权校验；事件插在实际 dispatch 前，不能借用 preview 分支绕过 execute 校验 |
| `src/so101_demo_py/src/adapters/pick_place_executor.py:DynamicRuntimeContext` | 已有 session、reset epoch、来源与 profiler；加入可选事件上下文 |
| `src/so101_demo_py/src/ros/dynamic_runtime.py:run_dynamic_execute` | `runtime.cup_pose_source(...)` 后目前打印 `status=READY subscription=/cup_pose`；此处是新事件位置 |
| `src/so101_demo_py/src/ros/rgbd_cup_pose_node.py` | 已有 `FreshFrameGate`、`FirstValidEvidencePublisher`，连续发布，不能改成旧入口只发一次 |
| `src/so101_demo_py/src/ros/rgbd_object_pose_node.py` | 已有 subscriber 门禁和 `_publish_and_confirm`，保留一次性感知及失败语义 |
| `src/so101_demo_py/src/ros/dynamic_mujoco_execution.py:RosDynamicMujocoExecution.finish` | 现有 manifest 含 `state_trace`、`state_events`、`final_samples`、`release_marker_sequence`、`planning_scene_readback`；尚不能假定含 workflow/request，需补关联证据 |
| `src/so101_demo_py/setup.py:installed_resources` | 已递归安装 launch；只需添加入口文件及 validator console script，不另造安装机制 |

本次只编写计划和校验文档，不启动 ROS/仿真、远程实验或测试。远程 checkout、进程图、依赖和模型工件留给 Task 1 取证，不能从旧记录断言其可用。

### 本次计划任务账本

- task_id：`text-agent-e2e-plan-20260907-01a07c7f`。
- 唯一 evidence root：`/tmp/so101-debug-text-agent-e2e-plan-20260907-01a07c7f/`。
- checkpoint：计划已生成，生产代码未修改；下一步是执行阶段 Task 1。
- retained：本计划及该 root 下的文档检查结果；archived：无；删除候选：文档检查临时结果，未经授权不删除。

## 文件分工与依赖

以下路径均相对仓库根。表中“新增”是本计划拟建文件，不表示当前存在。

| Task | 文件 | 职责 |
|---|---|---|
| 1 | 新增 `docs/experiments/text-agent-multibackend-e2e-experiment-ledger.md`；修改 `src/so101_demo_py/test/test_text_pick_agent_launch.py`、`test_perception_pick_place_launch.py`、`test_package_identity.py` | 环境与模型登记、旧入口兼容性基线 |
| 2 | 新增 `src/so101_demo_py/src/runtime/perception_launch.py`；修改 `src/so101_demo_py/src/runtime/launch_composition.py` | 共享后端解析和感知 action，不搬迁业务时序 |
| 3 | 新增 `src/so101_demo_py/src/runtime/workflow_events.py`、`src/so101_demo_py/test/test_workflow_events.py` | schema、编码、按进程流式解码、阶段机 |
| 4 | 修改 `src/so101_demo_py/src/application/text_agent.py`、`src/adapters/pick_place_executor.py`、`src/ros/dynamic_runtime.py`、`src/cli/text_pick_agent.py`、`src/ros/dynamic_mujoco_execution.py`（后四项均位于 `src/so101_demo_py/`） | 静态门和 runtime 事件、证据关联 |
| 4 tests | `src/so101_demo_py/test/test_text_agent.py`、`test_text_agent_provider_boundaries.py`、`test_text_agent_execution_provenance.py`、`test_dynamic_execute.py` | 拒绝不产生副作用，旧调用仍兼容 |
| 5 | 修改 `src/so101_demo_py/src/cli/rgbd_cup_pose.py`、`src/ros/rgbd_cup_pose_node.py`、`src/cli/rgbd_object_pose.py`、`src/ros/rgbd_object_pose_node.py`（后三项同包） | 感知 readiness、选择、发布、失败事件 |
| 5 tests | `src/so101_demo_py/test/test_rgbd_cup_pose.py`；新增 `src/so101_demo_py/test/test_perception_workflow_events.py` | 两类感知节点事件与旧 stdout contract |
| 6 | 新增 `src/so101_demo_py/src/application/e2e_acceptance.py`、`src/cli/e2e_acceptance.py`、`src/ros/e2e_acceptance_readback.py`（后两项同包）；新增 `src/so101_demo_py/test/test_e2e_acceptance.py`；修改 `src/so101_demo_py/setup.py` | 纯判据、只读 ROS 采集、CLI。ROS 适配器是为遵守现有分层而增加的文件 |
| 7 | 修改 `src/so101_demo_py/src/runtime/launch_composition.py`；新增 `src/so101_demo_py/launch/so101_mujoco_text_pick_agent_e2e.launch.py`、`src/so101_demo_py/test/test_text_pick_agent_e2e_launch.py` | supervisor、资源所有权、退出码与证据写入 |
| 8 | 修改 `src/so101_demo_py/test/test_package_identity.py`、`test_installed_provenance.py`；新增 `src/so101_demo_py/test/test_text_pick_agent_e2e_process.py` | 安装与真实 LaunchService/进程边界测试 |
| 9 | 更新实验账本；新增 `docs/guides/text-agent-multibackend-mujoco-e2e.md` | 平台运行、视频、使用命令和学习者验收入口 |

依赖：`1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9`。每个代码任务遵循 RED、最小实现、GREEN、局部审查、定向提交；只有获得执行请求后才实施。

## Task 1：冻结兼容性基线与执行环境

**Interfaces:** 产出账本内的 source/install/runtime/model provenance，以及旧入口声明集合和行为断言。后续任务使用该基线，不从历史测试数字推断当前通过。

- [x] 读取 `AGENTS.md`、父目录 `AGENTS.md`、`so101-dev` 的 access、test-and-acceptance、debug-evidence 和 experiment-ledger references。创建隔离 worktree 时使用 using-git-worktrees；复核 `.git` 指向，若 `core.worktree` 错配，使用显式 `--git-dir` 与 `--work-tree`。
- [x] 在 orchestrator 与 ai-station 分别记录以下命令结果；已在 ai-station 上执行的 agent 不再 SSH 自身。

```bash
pwd
hostname
git rev-parse HEAD
git branch --show-current
git status --short
git submodule status
ros2 pkg prefix so101_demo_py
ros2 pkg executables so101_demo_py
ros2 node list
tmux list-sessions
```

- [x] 检查已有进程和 ROS domain，记录需保留的 PID、命令与容器。建立 `docs/experiments/text-agent-multibackend-e2e-experiment-ledger.md`。每个平台运行作为单独 task/run 登记唯一 root；一次 task 的日志、build/install/test scratch 都在同一 root 内。
- [x] 正式 ai-station task 根使用 `/data/work/so101-evidence/text-agent-e2e/<run-id>/`；macOS 普通调试用 `/tmp/so101-debug-text-agent-e2e-<run-id>/`。每个 `<run-id>` 实际由 UTC 时间和 UUID 生成。长期视频在录制前登记耐久存储；macOS 没有可用耐久根时，在 ai-station 录制。迁移需清单与逐文件 SHA256/大小/数量核验，不制造同一 task 的两个活动根。
- [x] 在已正确 source 的 ROS shell 里设 `E2E_ROOT` 为该账本记录的绝对根，`E2E_PYTHON` 为实际 ROS Python；验证 `import rclpy` 与 `so101_demo.__file__`。模型清单记录两平台 `.pt` 路径、同一 SHA256、Grounded SAM bundle/manifest hash、实际设备与 Docker image digest。不要自动换权重或降级 CPU。
- [x] 加强旧入口参数默认值与序列测试，复用现有 `_builder`、`_declared`、`_default` 测试 helper。例如在 `test_text_pick_agent_launch.py` 加：

```python
def test_legacy_text_entry_stays_color_only():
    declared = _declared(_builder()())
    assert 'perception_backend' not in declared
    assert _default(declared['run_mode']) == 'dry_run'
    assert _default(declared['execute']) == 'false'
    assert _default(declared['skip_confirmation']) == 'false'
```

另外锁定旧 TextAgent 颜色感知与 agent 的现有启动顺序、三个 perception backend 的 argv/env/mount/exit 行为。基线测试此时应为 GREEN；这一步不人为制造失败。

- [x] 执行定向基线并保存退出码、耗时、非零收集数：

```bash
"$E2E_PYTHON" -m pytest -p no:cacheprovider \
  src/so101_demo_py/test/test_text_pick_agent_launch.py \
  src/so101_demo_py/test/test_perception_pick_place_launch.py \
  src/so101_demo_py/test/test_package_identity.py -q
```

ai-station 每次 pytest 前必须执行下文的 NVMe scratch gate。环境失败先记录为 INVALID，不计代码回归。

- [x] 提交本任务明确列出的测试和账本，message：`test: freeze legacy text and perception launch contracts`；先检查 staged diff，不夹带环境产物。

## Task 2：抽取共享感知构造，保留旧时序

**Interfaces:** 在 `runtime/perception_launch.py` 定义 `PerceptionLaunchOptions`（frozen dataclass），字段为设计 §5.2 的后端参数去掉 `perception_` 前缀，另含保留 launch 参数文本的 `startup_timeout_s: str`；parser 在构造前验证其为正有限数。Grounded SAM 七个阈值保留原名及类型。

定义 `declare_perception_arguments(*, default_backend: str) -> list[DeclareLaunchArgument]`、`parse_perception_options(context: LaunchContext) -> PerceptionLaunchOptions`、`build_perception_action(options: PerceptionLaunchOptions, *, evidence_root: Path, request_id: str, workflow_id: str | None = None, child_arguments: tuple[str, ...] = (), profiling_root: Path | None = None) -> ExecuteProcess`。`request_id` 是现有感知 CLI 与 owned container name 的必要输入；`Node` 是可返回的 ExecuteProcess 子类，profiling 通过 `child_arguments` 与可选挂载根保留原转发。

- [x] 在 `test_perception_pick_place_launch.py` 加 RED：完整 backend 参数声明一次；将旧 builder 的 backend 默认值设为 `color_geometry`，新调用可以传 `yolo_seg`，二者互不改默认。

```python
def test_backend_argument_default_is_caller_owned():
    from so101_demo.runtime.perception_launch import declare_perception_arguments
    old = {a.name: a for a in declare_perception_arguments(default_backend='color_geometry')}
    new = {a.name: a for a in declare_perception_arguments(default_backend='yolo_seg')}
    assert old.keys() == new.keys()
    assert _default(old['perception_backend']) == 'color_geometry'
    assert _default(new['perception_backend']) == 'yolo_seg'
```

- [x] 运行该测试，预期新模块不存在而失败；不能把 ROS import 错误当 RED。
- [x] 移动当前 backend 校验、阈值常量与 host/Docker 构造代码，保留原值：`0.35/0.25/0.85/16/0.75/64/0.50`。复用已登记默认 image，不新加依赖。调用方式：

```python
options = parse_perception_options(context)
perception = build_perception_action(
    options, evidence_root=evidence_paths.perception,
    child_arguments=tuple(profiling_arguments),
)
```

旧调用 `workflow_id=None`，argv、文件名和事件顺序必须与基线相同；新调用启用事件时再用设计 §10 的规范文件名。不得顺手修改旧 artifact contract。

- [x] 覆盖绝对路径/哈希错误、错误 backend 专属参数、非默认错配阈值、NaN/Inf、CPU fallback、macOS MPS、Linux Docker CUDA、Docker 挂载路径和 image，模型后端必须带 `--require-output-subscriber`。
- [x] 运行 Task 1 两个旧 launch 测试文件到 GREEN。审查 diff 仅抽取构造逻辑，提交 `refactor: share perception action construction`。

## Task 3：实现严格事件协议与阶段机

**Interfaces:** `workflow_events.py` 定义 `WorkflowEvent`（设计 §7.2 九个字段的 frozen dataclass）；`WorkflowProtocolError(ValueError)`；`EventEmitter(workflow_id: str, component: str, write: Callable[[str], None], clock_ns: Callable[[], int])`，其 `emit(event: str, *, payload: dict[str, object], failure_code: str | None = None) -> WorkflowEvent` 负责 sequence、固定 status 和 flush writer。

`EventDecoder(workflow_id: str, allowed_components: frozenset[str])` 提供 `feed(chunk: bytes, *, now_ns: int) -> list[WorkflowEvent]` 与 `finish(*, now_ns: int) -> list[WorkflowEvent]`。每个 child 独立实例，内部跟踪该 child 每个 component 的 sequence。`WorkflowState(backend: str)` 提供 `accept(event: WorkflowEvent) -> str | None`，仅返回固定 effect `START_PERCEPTION`、`START_ACCEPTANCE`、`FAIL`、`ACCEPT` 或 `None`；它不创建 ROS action。

- [x] 写拆包 RED，覆盖 UTF-8 字节中间切分、连续多行、普通日志、末尾半行。测试直接构造九字段 JSON，不依赖未实现测试 fixture：

```python
import json
from so101_demo.runtime.workflow_events import EventDecoder

def test_event_can_be_split_at_every_byte():
    record = dict(schema_version=1, workflow_id='w1', sequence=1,
                  component='text_agent', event='DISPATCH_PREVIEW', status='OK',
                  timestamp_ns=100, failure_code=None, payload={})
    line = ('SO101_EVENT ' + json.dumps(record) + '\n').encode()
    for cut in range(len(line)):
        decoder = EventDecoder('w1', frozenset({'text_agent', 'dynamic_runtime'}))
        events = decoder.feed(line[:cut], now_ns=100)
        events += decoder.feed(line[cut:], now_ns=100)
        assert len(events) == 1
        assert events[0].event == 'DISPATCH_PREVIEW'
```

- [x] 运行 `test_workflow_events.py` 到预期 RED，之后实现严格 schema 和逐行 parser：

```python
if line.startswith(b'SO101_EVENT '):
    event = decode_and_validate(line[len(b'SO101_EVENT '):], now_ns=now_ns)
    events.append(event)
```

`decode_and_validate(raw: bytes, *, now_ns: int) -> WorkflowEvent` 是 decoder 私有方法，检查字段精确集合、bool 不能冒充 int、schema=1、workflow/component 绑定、sequence、有限值、status/failure 配对。时间要求 `0 <= now_ns - timestamp_ns <= 5_000_000_000`；future timestamp 同样拒绝。EOF 遗留前缀半行必须协议失败；普通尾部日志只记日志。为每条事件固定 payload 字段白名单，未知字段不得透传。

- [x] payload v1 定义：阶段事件允许 `{}`，关联字段按事件选择：`DISPATCH_PREVIEW` 可含 `request_id/provider/model/fallback`，`RUNTIME_STARTED/READY` 可含 `request_id/session_id/reset_epoch`，`TARGET_SELECTED` 可含 `target_id/class_name`，`CUP_POSE_PUBLISHED` 可含 `source_stamp_ns/frame_id`，`RUNTIME_COMPLETED` 必含 `manifest_path/runtime_exit_code`；验证事件必含 `result_path`。其余字段全部拒绝。标识值与账本/provenance 交叉核对；provider/model 仅作数据，不作状态或 failure code。
- [x] 按设计 §7.3 编码完整有向转移：`STACK_READY -> DISPATCH_PREVIEW -> RUNTIME_STARTED -> RUNTIME_READY -> PERCEPTION_READY -> TARGET_SELECTED -> CUP_POSE_PUBLISHED -> RUNTIME_COMPLETED -> E2E_ACCEPTED`。仅颜色后端可跳过 `TARGET_SELECTED`。失败 event 仅在所属活动阶段接受。
- [x] 参数化测试每种非法 schema/workflow/component/sequence/timestamp/status/payload、旧 workflow、普通日志伪装状态、跳步和重复 ready。固定 failure code 表合并当前组件已有枚举；未知错误映射固定内部错误，禁止 `str(error)` 直接充当 code。
- [x] 运行文件到 GREEN；提交 `feat: add strict workflow event protocol`。

## Task 4：连接 TextAgent、executor 和 dynamic runtime 的事件

**Interfaces:** `TextAgent.__init__` 新增可选 `event_emitter: EventEmitter | None = None`；`DynamicRuntimeContext` 新增 `workflow_id: str | None = None`、`event_emitter: EventEmitter | None = None`；`run_dynamic_execute` 新增可选 keyword `event_emitter: EventEmitter | None = None`。TextAgent 与 dynamic runtime 各有独立 sequence，虽同进程也不能混用 emitter。

- [ ] 在现有 TextAgent fake planner/executor 测试中加记录列表断言：合法 execute 的 `DISPATCH_PREVIEW` 发生在 `executor.dispatch` 前；unsupported、ambiguous、schema 错、backend 错、未授权、digest 错均不 dispatch、不创建 runtime、不发 preview。provider 失败才 fallback，可解析非法命令不得 fallback。
- [ ] 在 `test_dynamic_execute.py` 的注入 `_runtime` 测试记录 `cup_pose_source/get_one/execution/runner` 顺序，RED 断言订阅创建后、`get_one` 前产生 READY；scene/pose/reachability 拒绝时 runner 创建次数为零。
- [ ] 给 CLI 加成对参数，workflow ID 使用现有安全字符规则，只有一项时立即拒绝。TextAgent 授权和 request claim 完成后插入：

```python
if self._event_emitter is not None:
    self._event_emitter.emit('DISPATCH_PREVIEW', payload={})
result = self._executor.dispatch(dispatch_request)
```

executor 在真实调用 runtime 前发 `RUNTIME_STARTED`；runtime 在 `cup_pose_source` 成功返回后发 `RUNTIME_READY`。return 0 且 finish/cleanup 成功后才发 `RUNTIME_COMPLETED`；异常、非零、证据写入失败发 `RUNTIME_FAILED`。发终态只允许一个层负责，外层错误只能补 secondary，防止双发。

- [ ] 在 `RosDynamicMujocoExecution` 加可选 `workflow_id/request_id`，从已经校验的 request/context 传入并保存；旧调用默认 None，旧 manifest 读者兼容。新 E2E 验证时缺少关联字段必须拒绝。不要只凭相邻目录推定证据同源。
- [ ] 保存实际 provider/model/fallback、source commit、installed prefix、request/session/reset、input source stamp/frame 的关联文件；补在原 provenance 写入边界，禁止保存 provider 密钥和原始敏感响应。
- [ ] enabled 模式普通状态行定向 stderr；disabled 模式 golden stdout 与退出码完全不变。运行上述四个测试文件及现有相关 CLI 测试到 GREEN；提交 `feat: emit agent and dynamic runtime workflow milestones`。

## Task 5：让感知按真实就绪、选择和发布发事件

**Interfaces:** 两个 perception CLI 支持成对 `--emit-workflow-events/--workflow-id`；两个 ROS run 函数增加可选 `event_emitter: EventEmitter | None = None`。节点内部使用同一个 `perception` emitter，CLI 不再次生成终态。

- [ ] 在新增 `test_perception_workflow_events.py` 用 fake publisher、TF、subscriber gate 记录调用：subscriber 或 TF 未 ready 时既无 `PERCEPTION_READY` 也不处理旧帧；ready 后仅消费新 RGB/Depth/CameraInfo。各 gate 保留当前超时。
- [ ] RED 断言唯一实例时顺序为 READY、SELECTED、PUBLISHED；0/2+ 杯子各发失败，publisher 调用为零；证据写入失败也不得发布。模型测试使用 fake detector，不装载真实模型，不改变测试 suite 分区。
- [ ] 在已通过 ready gate 处发 `PERCEPTION_READY`，`TargetSelector` 成功之后发 `TARGET_SELECTED`，现有证据写入和 `_publish_and_confirm` 成功之后发 `CUP_POSE_PUBLISHED`。Depth、TF、模型和证据异常映射现有固定 code。
- [ ] 颜色节点在 `FirstValidEvidencePublisher` 的首次成功发布边界加一次事件标记，保留后续 topic 发布：

```python
self._publish(frame)
self.published_count += 1
if self.published_count == 1 and self._event_emitter is not None:
    self._event_emitter.emit('CUP_POSE_PUBLISHED', payload={})
```

构造函数增加可选 emitter 并存入 `_event_emitter`；颜色节点在首帧 gate 开放时发一次 `PERCEPTION_READY`，无需伪造 `TARGET_SELECTED`。测试连续两帧 publisher=2、PUBLISHED event=1。

- [ ] Docker 环境转发事件参数、同一 workflow、证据挂载路径并保持 unbuffered stdout；容器里的 `timestamp_ns` 使用宿主共享 wall clock，不能改成仿真时间。
- [ ] 运行 `test_rgbd_cup_pose.py`、`test_perception_workflow_events.py` 和两个旧 launch 文件的测试到 GREEN，提交 `feat: emit perception readiness and publication events`。

## Task 6：实现独立只读 E2E 验证器

**Interfaces:** `application/e2e_acceptance.py` 定义 `AcceptanceReport(accepted: bool, failures: tuple[str, ...], physical_outcome: dict[str, object], planning_scene_outcome: dict[str, object])`；`validate_e2e_evidence(document: dict[str, object]) -> AcceptanceReport`。输入 document 必含 `expected_identity/dynamic/perception/mujoco_final/planning_scene_final/policy`；使用原 manifest 语义，不另造布尔 passed 值替代原始事实。

`ros/e2e_acceptance_readback.py` 定义 `collect_final_readback(*, session_id: str, reset_epoch: int, timeout_s: float) -> dict[str, object]`，只读 MuJoCo observer 和 `/get_planning_scene`，返回 `mujoco_final/planning_scene_final`。CLI `main(arguments: list[str] | None = None) -> int` 接收 `--run-root --workflow-id --request-id --session-id --expected-reset-epoch --emit-workflow-events`，从 run root 内校验过的清单读取其他路径。

- [ ] RED：空文档不能成功，不得抛出未经处理的 KeyError；缺证据结果可序列化：

```python
from so101_demo.application.e2e_acceptance import validate_e2e_evidence

def test_missing_evidence_is_rejected():
    report = validate_e2e_evidence({})
    assert report.accepted is False
    assert report.failures
```

- [ ] 从 `test_dynamic_execute.py` 当前有效 manifest fixture 构造完整成功文档，并在 `test_e2e_acceptance.py` 定义本文件自己的 `accepted_document` fixture。逐项损坏 identity、DONE/state_trace、controller feedback、lift/transport、release sequence、support contact、fingertip contact、world/attached、pose/timestamp；每次只改一项，必须拒绝。
- [ ] 复用当前 dynamic policy 和 `dynamic_mujoco_execution.py` 的判据读取字段：`resolved_targets`、`state_events`、`final_samples`、`release_marker_sequence`、`planning_scene_readback`；位置/姿态/稳定窗口阈值来自同一 policy/hash，不重新猜阈值。controller-level reconciliation 只有满足现有反馈契约才接受。
- [ ] 验证完整状态轨迹符合当前 runner transition table，包含抬升、搬运、先 `DETACH_MOVEIT` 后开夹爪、当前 release epoch 的 settle/final validation。仅 DONE 或单个 final pose 不足以接受。policy 仍为 `CALIBRATION_REQUIRED` 时拒绝正式 live success。
- [ ] 采集器在 runtime 已完成且 stack 仍存活时读取新的 MuJoCo session/reset/sequence/pose/contact 和 Planning Scene；最终 attached 集合为空，`plastic_cup` 在 world，位置与四元数角误差符合既有 policy。MuJoCo truth 仅供验证，禁止写 `/cup_pose` 或注入 runtime localization。
- [ ] mock ROS clients 验证仅调用读取 service/subscription，没有 action 执行、`apply_planning_scene`、reset、attach 或开夹爪。每次读取有限 timeout；缺字段、失联、跨 session、跨 reset、陈旧快照返回 rejected。
- [ ] 原子写 `acceptance/mujoco-final.json`、`planning-scene-final.json`、`result.json`，成功落盘之后发 `E2E_ACCEPTED`；失败发 `E2E_REJECTED`，CLI 返回 1。失败写盘不能保留旧成功结果。
- [ ] `setup.py` 新增 `e2e_acceptance = so101_demo.cli.e2e_acceptance:main`。测试到 GREEN，提交 `feat: verify final MuJoCo and planning scene evidence`。

## Task 7：组装新 launch、失败传播与清理

**Interfaces:** `launch_composition.py` 新增 `build_text_pick_agent_e2e_launch_description() -> LaunchDescription`、`E2ESupervisor`。supervisor 提供 `on_stdout(child: ExecuteProcess, chunk: bytes) -> list[Action]`、`on_exit(child: ExecuteProcess, returncode: int) -> list[Action]`；内部保存 `primary_failure/secondary_failures/current_phase/shutting_down`、per-child decoder、owned process/container registry 和 timer generation。`Action` 使用 `launch.Action`。

- [ ] 在 `test_text_pick_agent_e2e_launch.py` 建立当前两个 launch 测试相同风格的 materialize helper，RED 覆盖全部公共参数与三重授权。无授权、坏 instruction、坏 sensor flag、坏模型参数、既有 evidence 文件时，断言 `_mujoco_stack_actions` 调用为零。
- [ ] 写 thin wrapper：

```python
from so101_demo.runtime.launch_composition import build_text_pick_agent_e2e_launch_description

def generate_launch_description():
    return build_text_pick_agent_e2e_launch_description()
```

所有参数校验在创建 Node/ExecuteProcess 前完成，资源目录拒绝 symlink/穿越/已有结果。新 `evidence_file` 就是本轮顶层 result 文件；默认生成唯一 root 下的 `e2e-result.json`。显式自定义文件名时，该文件是唯一权威 summary，run root 由它所在的独占目录确定，其他设计 §10 子路径相对该 root；不再生成第二个同义成功文件。

- [ ] 复用 `_mujoco_stack_actions` 和 camera TF；不 include 旧业务 launch。注册所有 handler 后才启动 child；scene_setup 退出 0 且 stack readiness 完成后，由 supervisor 发内部 `STACK_READY` 并只启动 TextAgent。
- [ ] 为 TextAgent child 允许 `{text_agent, dynamic_runtime}`，感知仅 `{perception}`，validator 仅 `{e2e_validator}`；`STACK_READY` 属于 supervisor，不能由 child 冒充。`OnProcessIO` 每个目标独立累积字节。调度 effect 示例：

```python
effect = self.workflow_state.accept(event)
if effect == 'START_PERCEPTION':
    if self.perception_started:
        raise WorkflowProtocolError('EVENT_PROTOCOL_INVALID')
    self.perception_started = True
    return [self.perception_action]
```

`self.perception_action` 由 Task 2 builder 生成，`workflow_state` 来自 Task 3。`DISPATCH_PREVIEW` 永远返回空 action。对重复、丢失和跨阶段事件必须拒绝，不能通过普通日志补齐。

- [ ] readiness、perception startup 和 cup pose timeout 分别从 stack 启动、感知启动、runtime subscriber ready 计时。timer 绑定 workflow/phase generation，旧 timer 不得杀新阶段。runtime/validator/recovery/teardown 再设内部有限 deadline（不新增公共参数）：runtime 600 秒、validator 30 秒、recovery 30 秒，SIGINT 10 秒、SIGTERM 5 秒，SIGKILL 后 5 秒确认退出；测试用 fake clock。
- [ ] 首次有效失败写 primary（component/code/phase/message/exit code/timestamp），之后只追加 secondary。perception 失败时停止等待 pose 的 runtime：已进入动作则走现有取消/recovery 路径，等待 recovery 窗口后才 teardown。无支撑且仍物理持杯时保持，不自动开夹爪。若现有 runtime 取消接口不足，先在 Task 4 补 stop/recovery 边界测试，再连接；不得用世界 reset 代替恢复。
- [ ] required long-lived child 在 accepted 前即使 exit 0 也失败；spawner/scene_setup 为一次性角色，0 可成功；TextAgent 只有合法 runtime terminal 后的 0 才正常；一次性感知只有合法发布事件后的 0 才正常；颜色节点持续存活。无合法 terminal 的非零退出使用 `CHILD_EXITED_WITHOUT_TERMINAL_EVENT`。
- [ ] Docker 用本轮唯一 name/label/CID 记录 ownership，只清理 registry 内的容器；清理只作用本轮 child。保留 Ollama daemon、DeepSeek 服务、其他 tmux 和未知 PID。信号升级、destroy 异常、容器残留记录 secondary，已有 primary 不被 signal exit 覆盖。
- [ ] `RUNTIME_COMPLETED` 只启动一次 validator，保持 stack。`E2E_ACCEPTED` 后完成 owned cleanup，再原子写最终结果；cleanup 有未解决错误时顶层仍非零。机器验收通过与资源清理成功分开记录。
- [ ] 事件 trace 每次更新通过同 root 临时文件、flush/fsync、`os.replace` 原子替换完整 NDJSON；最终 JSON 同样处理。若 trace/result 写入失败，以证据错误失败并进入 cleanup，不保留 success 字段。原子 writer 放 supervisor 私有 helper，避免给协议模块加文件所有权职责。
- [ ] 完整保存设计 §10 summary 字段与所有 artifact paths；外部模型路径只作 provenance，不算本轮可清理文件。将 failure 状态连接 `_terminal_launch_actions` 的失败传播机制并做真实进程测试，不能只测内存 returncode。
- [ ] 运行 Task 7 contract 与 Task 3 协议测试到 GREEN；提交 `feat: compose supervised text agent multibackend e2e launch`。

## Task 8：验证安装、并发边界与包级回归

**Interfaces:** 安装集合只新增 E2E launch 和 validator CLI；真实 `ros2 launch` 退出码是用户可依赖的 contract。

- [ ] `test_package_identity.py` 比较安装 launch 集合为基线加单个新文件；`test_installed_provenance.py` 验证新 launch/CLI 和 source hash/prefix 对应。不能用 source import 代替安装验证。
- [ ] 新增 `test_text_pick_agent_e2e_process.py`，使用 Python fake children 与真实 LaunchService：child 通过 stdout 写协议，控制 exit code 和分块延迟，不启动机器人。覆盖业务失败后退出非零、required process exit 0 失败、accepted+cleanup 全通过才 exit 0、错误证据写入非零、首错保持、信号升级与 owned cleanup。
- [ ] 用可控 fake child 验证 EOF 与 ProcessExited 竞态：在处理 exit 前 drain 该 child 已接收完整行；prefix 半行失败，不能把有效失败误报成无 terminal。对跨 child 的 `CUP_POSE_PUBLISHED/RUNTIME_COMPLETED` 做不同 I/O 调度测试；按设计严格全局阶段接收，乱序明确失败，不重排、不猜测、不静默放宽。真实平台若出现此竞态，记录为阻塞缺陷；先提出与设计一致的生产者同步修正，再跑该复现，不能把它当成偶发成功。
- [ ] 重新构建到 task 独立 overlay，先 source 正确 underlay，再 source 本 overlay；保留构建命令、退出码、实际 module path：

```bash
colcon --log-base "$E2E_ROOT/colcon-log" build \
  --build-base "$E2E_ROOT/build" --install-base "$E2E_ROOT/install" \
  --packages-select so101_demo_py --symlink-install
source "$E2E_ROOT/install/setup.zsh"
ros2 pkg prefix so101_demo_py
ros2 pkg executables so101_demo_py
ros2 launch so101_demo_py so101_mujoco_text_pick_agent_e2e.launch.py --show-args
"$E2E_PYTHON" -c 'import rclpy, so101_demo; print(rclpy.__file__); print(so101_demo.__file__)'
```

依赖必须已在核验过的 underlay；缺少本次变更依赖时先独立构建所需依赖，不复用来源不明 install。

- [ ] ai-station 每次测试创建全新 NVMe scratch，并用实际测试 Python 验证，随后记录耗时：

```bash
E2E_SCRATCH="$E2E_ROOT/scratch/$(date -u +%Y%m%dT%H%M%S)-$(uuidgen)/tmp"
mkdir -p "$(dirname "$E2E_SCRATCH")"
mkdir "$E2E_SCRATCH"
export TMPDIR="$E2E_SCRATCH" TMP="$E2E_SCRATCH" TEMP="$E2E_SCRATCH"
"$E2E_PYTHON" -c 'import os,pathlib,tempfile; p=pathlib.Path(tempfile.gettempdir()).resolve(); expected=pathlib.Path(os.environ["TMPDIR"]).resolve(); assert p==expected and str(p).startswith("/data/work/so101-evidence/"); print(p)'
time colcon --log-base "$E2E_ROOT/colcon-test-log" test \
  --build-base "$E2E_ROOT/build" --install-base "$E2E_ROOT/install" \
  --packages-select so101_demo_py --pytest-args test \
  --event-handlers console_direct+
colcon test-result --test-result-base "$E2E_ROOT/build" --verbose
```

实际 colcon runner interpreter 必须与 `E2E_PYTHON` 相同，通过 command.log 核验；不一致先停。scratch 读回后列为删除候选，不删除、不关闭 fsync、不换 tmpfs。macOS 不套用 `/data` 规则。

- [ ] macOS 在当前 zsh 保留 ROS/DYLD 环境，运行包级 pytest：

```bash
export ROS_HOME="$E2E_ROOT/ros-home" ROS_LOG_DIR="$E2E_ROOT/ros-home/log"
mkdir -p "$ROS_LOG_DIR"
PYTHONNOUSERSITE=1 "$E2E_PYTHON" -m pytest -p no:cacheprovider \
  src/so101_demo_py/test -q --junitxml="$E2E_ROOT/so101_demo_py-pytest.xml"
colcon test-result --test-result-base "$E2E_ROOT" --verbose
```

若 rclpy collection 因 dylib 失败，按 so101-dev reference 检查 runner bootstrap，不能报通过；收集数必须大于零。定向测试已通过后只跑一次包级 gate，新增修改或失败才重跑。

- [ ] 运行 `git diff --check` 并检查 staged scope，提交 `test: verify e2e launch process and installed contracts`。

## Task 9：双平台现场验收、视频与交接

**Interfaces:** 产出每轮 `workflow-events.ndjson/e2e-result.json/perception/dynamic/acceptance`、数值证据、命令与退出码、fresh screenshot、1 至 2 分钟 demo；工程结果与学习者结果分别记录。

- [ ] 每轮先写 PLANNED 条目：prior experiment、唯一变量、`FULL_RESTART`、固定 commit/policy/model、fresh domain/session/workflow/root、成功/失败/INVALID 判据。取证后才 RUNNING，结束记 VALID 或 INVALID。不同 host/backend 使用独立 task 记录；同一 task 的各次实验在其唯一 root 的子目录。
- [ ] 以账本验证的绝对路径设置 `E2E_WEIGHTS`、`E2E_WEIGHTS_SHA256`、`E2E_MODEL_ROOT`、`E2E_MODEL_MANIFEST_SHA256` 和 `E2E_RUNTIME`、`E2E_DEVICE`；Linux image 使用账本已验证的固定值。这些是实际工件输入，不给不存在的示例权重路径。provider 使用现有安全配置，不把 secret 写入命令日志。
- [ ] 在每个平台执行 YOLO-Seg 唯一杯 headless：

```bash
E2E_SESSION="text-e2e-$(uuidgen)"
ros2 launch so101_demo_py so101_mujoco_text_pick_agent_e2e.launch.py \
  instruction:='Pick the plastic cup. Apply no constraints.' \
  run_mode:=execute execute:=true skip_confirmation:=true \
  headless:=true sensor_rendering:=true session_id:="$E2E_SESSION" \
  evidence_file:="$E2E_ROOT/e2e-result.json" \
  perception_backend:=yolo_seg perception_runtime:="$E2E_RUNTIME" \
  perception_device:="$E2E_DEVICE" perception_allow_cpu_fallback:=false \
  perception_weights:="$E2E_WEIGHTS" perception_weights_sha256:="$E2E_WEIGHTS_SHA256"
E2E_RC=$?
print -r -- "$E2E_RC" > "$E2E_ROOT/launch-exit-code.txt"
```

Linux 若登记 image 与默认不同，显式加 `perception_container_image`；macOS 要读回实际 MPS，Linux 要读回实际 CUDA，不只看传入参数。每个示例命令只运行在尚无 result 的 fresh run root，不能原地重复覆盖。

- [ ] 两平台各另开 fresh task/run 执行 Grounded SAM。命令沿用上面的公共参数，完整替换 backend 部分为：

```bash
perception_backend:=grounded_sam \
perception_runtime:="$E2E_RUNTIME" perception_device:="$E2E_DEVICE" \
perception_allow_cpu_fallback:=false \
perception_model_root:="$E2E_MODEL_ROOT" \
perception_model_manifest_sha256:="$E2E_MODEL_MANIFEST_SHA256"
```

该参数片段追加到 `ros2 launch` 命令，不能单独执行；同时移除两个 YOLO 专属参数。确认 bundle 与实际 supported device 兼容，失败不切颜色后端抵数。正式矩阵共四格，每格至少一次 headless 唯一杯完整 E2E。

- [ ] 验证每次 actual provider/model/fallback、request/session/reset、RGB/Depth/CameraInfo 与 tf2、本次 `/cup_pose` stamp/frame、完整事件和 state_trace、controller/joint/TCP、MuJoCo 抬升搬运释放稳定支撑、无 fingertip、Planning Scene world/attached、validator 和 launch 双退出码、owned cleanup。
- [ ] 执行三条 fresh 负向 live run。Planner 拒绝使用 `instruction:='Do not pick anything. Fly the robot to the moon.'`，必须读回真实拒绝；若 provider 仍产生合法命令，则该轮不能算拒绝用例，记录失败并在测试注入的确定性 Planner 边界复现。两杯使用 `mujoco_initial_keyframe:=v5_two_cups`，要求 primary `TARGET_AMBIGUOUS`、无 pose、无 runner。MoveIt 故障在独立 domain 的测试执行服务中返回 action abort，或只中止本轮 owned controller；冻结注入的时点与 PID，确保失败落在 execute 而非 startup，要求 runner recovery、非零退出和可解释副作用。
- [ ] Task 6/8 自动化还必须证明 runtime 0 但物理不合格、MuJoCo 合格但 Planning Scene attached 两条路径顶层失败，不能用成功视频覆盖这些断言。
- [ ] 设计要求四格最小运行；so101-dev 的正式物理完成门还要求连续五次有效成功。对完成声明覆盖的每个模型/平台配置，使用固定 commit/参数和 `FULL_RESTART` 单独计数五次，四格首轮可算各自第一次。VALID 失败中断序列；INVALID 中断批次并保留记录。该稳定性 gate 是仿真验证，不运行 perception benchmark suite。
- [ ] 在已完成 provenance 验证的平台使用 YOLO-Seg、`headless:=false` 和 fresh run 录制 1 至 2 分钟视频，录制前读 `gui-capture` 技能。录制覆盖指令、运动、放置和自动退出，结束后取新的截图并实际打开检查；launch 不为录像暂停成功退出，镜头内容不足则另开 fresh run，不修改超时伪造成功。
- [ ] 新建 `docs/guides/text-agent-multibackend-mujoco-e2e.md`，写实际可复现命令、三入口用途、事件与失败读法、证据路径和视频链接，使用 humanizer-zh。只写已验证结果，未通过矩阵格明确标为未验收。
- [ ] 学习者验收单独安排：沿事件解释成功路径，以及 Planner 拒绝、歧义、MoveIt 执行失败各在哪一层终止、是否已有物理副作用。只有确认学习者身份并取得实际解释后，才按课程流程更新其个人记录；本计划不代填进度。
- [ ] 最终账本列 retained runs、archived runs、scratch/临时结果删除候选；不得删除证据。提交指南与账本，message：`docs: record multibackend text agent e2e acceptance`。未完成现场 gate 时只提交真实 checkpoint，不写 acceptance passed。

## 逐项覆盖与完成检查

| 设计要求 | 实现/验证位置 |
|---|---|
| §1–3 三入口定位、旧行为稳定 | Task 1、2、7、8 |
| §4.1/4.4 共享感知与顶层所有权 | Task 2、5、7 |
| §4.2 Planner 与固定授权边界 | Task 4，Task 9 负向运行 |
| §4.3 subscriber、预检与 runner 边界 | Task 4、5、7 |
| §4.5 双事实源终态验证 | Task 6、8、9 |
| §5 全部参数、平台和模型 provenance | Global Constraints、Task 1、2、7、9 |
| §6–7 顺序、协议与失败事件 | Task 3–5、7–8 |
| §8–9 首错、recovery、owned teardown | Task 4、7–9 |
| §10 路径、原子写与结果字段 | Task 1、4–7、9 |
| §11 兼容、协议、launch、五条失败边界 | Task 1–8 |
| §12 双平台四格、三负向、视频 | Task 9 |
| §13 文件边界 | 文件分工表；额外 ROS readback 适配器保持应用层纯逻辑 |
| §14 工程与学习者验收分离 | Task 9 |

- [ ] 所有代码任务 RED/GREEN 有命令、退出码和非零测试数；两个旧入口回归通过。
- [ ] 新入口真实 `ros2 launch` 失败非零，成功须 acceptance、原子证据和 cleanup 全通过。
- [ ] 平台矩阵、连续有效运行、三条负向和视频均有当前来源证据；未满足的项不得勾选。
- [ ] learner 掌握度独立记录，未因代码或计划完成自动更新。

执行可使用 executing-plans 在当前会话逐项推进；选择子代理执行时再使用 subagent-driven-development。计划编写阶段不创建子代理或实现分支。
