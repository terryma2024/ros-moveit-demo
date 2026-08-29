# Text Pick Agent：从一句话到一次受控 MuJoCo 调度

## 先理解它解决什么问题

`text_pick_agent` 不是“让大模型直接控制机械臂”。它把模型限制在一个很窄的职责里：
判断一句自然语言是 `supported`、`unsupported` 还是 `ambiguous`；只有 `supported` 才能附带
当前唯一的 `plastic_cup / pick / constraints` 命令。固定的 Python 代码随后独立完成命令校验、
能力解析、人工确认绑定、执行 provenance 核验和一次性调度。

最重要的直觉是：**预览看到什么，执行就只能确认什么**。预览结果里的
`confirmation_digest` 是一个带版本的 SHA-256，绑定了去除首尾空白后的 instruction、不可变
`TaskCommand`、解析出的 capability、provider 和 model。token 数、延迟和 cache 信息不会改变
digest。执行时模型会再规划一次；任何 instruction、command、provider 或 model 漂移都会使
digest 不匹配，并且发生在 request_id claim 和 Executor 调用之前。

## 数据流和每一层的责任

```text
CLI
  -> PlannerChain
       -> DeepSeekPlanner --HTTPS JSON--> DeepSeek
       -> OllamaPlanner   --HTTP JSON---> loopback Ollama（仅 provider failure 时一次 fallback）
  -> Planner outcome validator (supported | unsupported | ambiguous)
  -> TaskCommand validator
  -> confirmation digest
  -> TextAgent
  -> TaskDispatcher
  -> DynamicCupPickPlaceExecutor（typed in-process Python port）
  -> run_dynamic_execute（现有 dynamic runtime）
  -> /cup_pose + MoveIt + controllers + Planning Scene + MuJoCo
```

各组件的边界如下：

- CLI 只处理参数、provider 生产配置、执行上下文、provenance 持久化和单个 JSON 输出。preview
  不构造 live Executor，也不导入 `rclpy` 或 `so101_demo.ros`。
- `PlannerChain` 先调 DeepSeek；只有 `PlannerProviderError` 才调一次 Ollama。语义上不支持或含糊
  的 primary 结果不会被 fallback “修好”。
- DeepSeek adapter 固定为官方 HTTPS `https://api.deepseek.com/chat/completions` 和
  `deepseek-v4-flash`。Ollama adapter 固定为 `qwen3.5:4b`，只接受 `127.0.0.1`、`::1` 或
  `localhost` 的 `/api/chat`，允许端口覆盖以支持 localhost reverse tunnel；它显式发送
  `think=false`，避免 reasoning text 占满结构化响应 deadline。
- Planner outcome 只有三种闭合形状：`unsupported` 和 `ambiguous` 不能携带 command；
  `supported` 必须携带当前闭合 TaskCommand。共享 prompt 禁止臆造 instruction 未明确给出的
  constraints；没有明确 constraint 时必须返回 `{}`。前两种 outcome 在 Dispatcher 之前终止。
- `TaskCommand` validator 把 mapping 归一化为 frozen value；V5-T003 虽认识 `speed` 和
  `spatial_relation`，但 Dispatcher 没有它们的 consumer，所以任何非空 constraints 都拒绝。
- `TextAgent` 负责 double authorization、confirmation digest、backend gate 和 resident
  request_id claim。membership check 与 claim 共用一把锁；claim 在成功、受控失败和意外异常后
  都保留，避免同一 resident agent 重复调度。
- `TaskDispatcher` 只把无 constraints 的 `plastic_cup/pick` 映射为
  `dynamic_cup_pick_place`、`backend=mujoco`、`scene_source=observe_only`。
- `DynamicCupPickPlaceExecutor` 不拼 shell 命令。它通过 typed Python request 在同一进程里调用
  现有 `run_dynamic_execute(options)`，ROS import 仍是 lazy 的。
- dynamic runtime 创建 `so101_dynamic_cup_pick_place` ROS node，从 `/cup_pose` 取一次有 deadline
  的 `PoseStamped`，校验 session/reset epoch 和 MuJoCo truth，建立/读回 Planning Scene，做
  reachability，然后交给已有 state machine。

## Preview 和 live execution 分别启动什么

preview 只启动一个短生命周期的 `text_pick_agent` 进程。它通过 HTTP JSON 调 provider，然后在
同一 Python 进程内经过 PlannerChain、outcome/command validator、digest、TextAgent 和 Dispatcher；
Executor 不会运行，也不需要 MuJoCo、MoveIt、controllers 或 `/cup_pose`。

live execution 需要另一个、已经 readiness-qualified 且由操作者明确拥有的 MuJoCo stack。当前
`so101_mujoco.launch.py` 的 MuJoCo composition 启动：

- `robot_state_publisher`；
- `mujoco_ros2_control/ros2_control_node`；
- `joint_state_broadcaster`、`arm_controller`、`gripper_controller` 三个 spawner；
- `so101_mujoco_support/graceful_shutdown_move_group`；
- 一次性的 `scene_setup`，负责 Planning Scene setup/read-back。

V5-T003 仿真资格运行还需要一个拥有者明确的 `/cup_pose` producer。当前 test-only truth bridge 是
`python3 -m so101_demo.ros.mujoco_cup_pose_bridge --session-id <session>`；感知工作流则可以由
`rgbd_cup_pose` 发布 `/cup_pose`。不要同时启动两个 producer。

execute 的 `text_pick_agent` 仍是单独进程，但 Executor 在该进程内调用 dynamic runtime。主要
ROS 2 连接包括 `/cup_pose` 和 `/joint_states` topics、`/plan_kinematic_path`、
`/get_planning_scene`、`/apply_planning_scene` services、`/execute_trajectory` action，以及
`/gripper_controller/follow_joint_trajectory` action。MoveIt 拥有规划与 Planning Scene shadow；
controllers 执行 trajectory；MuJoCo 是仿真物理和杯子运动的 truth source。

## 隔离、相关性和 cleanup ownership

同一轮 stack、bridge、preview 和 execute 必须使用同一个 `ROS_DOMAIN_ID` 和 `GZ_PARTITION`。
不同实验必须使用不同 domain/partition，避免 ROS discovery 或 MuJoCo transport 串线。

`request_id` 关联 Text Agent 的 preview/execute 和 resident claim；`session_id` 关联 stack、
dynamic runtime、MuJoCo evidence 和 reset epoch。它们可以取同一个可读值，但语义不同。执行前，
CLI 还会核验：

- source commit 是完整 40-hex，并等于当前 imported runtime 所在 Git checkout 的 HEAD；
- `--installed-prefix` canonicalize 后等于 ament 实际解析到的 `so101_demo_py` prefix；
- entrypoint wrapper、imported module 和 Python executable 在可用时都有 SHA-256；
- session、reset epoch 和 evidence root 一并投影。

verified document 会先原子写入
`<evidence-root>/text-agent-provenance/<sha256(request-id)>.json`，也会出现在 execute 的 JSON
结果里。cleanup 只向本轮记录过的 launch/bridge PIDs 或 task-owned tmux panes 发送 SIGINT；禁止
用 broad `pkill`、`killall` 或删除共享 session。

## 安全加载 `~/.env`

下面的 zsh 片段用 export semantics 加载文件，抑制 `source` 输出，并且只报告 SET/UNSET，绝不
显示 key 值：

```zsh
set -a
source "$HOME/.env" >/dev/null 2>&1
env_load_exit=$?
set +a
if (( env_load_exit != 0 )); then
  print -u2 -- "failed to load ~/.env"
  exit 1
fi
if [[ -n ${DEEPSEEK_API_KEY:-} ]]; then
  print -r -- 'DEEPSEEK_API_KEY=SET'
else
  print -r -- 'DEEPSEEK_API_KEY=UNSET'
fi
```

不要运行 `env`、`set`、`printenv DEEPSEEK_API_KEY`，也不要把 key 放进参数、日志、账本或
evidence。

## DeepSeek：preview → confirm → execute

先 source 精确 candidate overlay，并为本轮设置唯一值：

```zsh
export ROS_DOMAIN_ID=221
export GZ_PARTITION=v5-t003-learning-deepseek-001
export REQUEST_ID=v5-t003-learning-deepseek-001
export SESSION_ID=v5-t003-learning-deepseek-001
export RESET_EPOCH=0  # 只能填 readiness evidence 刚刚观测到的 epoch
export EVIDENCE_ROOT=/tmp/so101-debug-v5-t003-learning
mkdir -p "$EVIDENCE_ROOT"
```

加载 key 后运行 preview，并从唯一 JSON 文档读回 provider/model/digest：

```zsh
PREVIEW_JSON="$EVIDENCE_ROOT/deepseek-preview.json"
ros2 run so101_demo_py text_pick_agent \
  --instruction 'Pick the plastic cup. Apply no constraints.' \
  --request-id "$REQUEST_ID" \
  --backend mujoco >"$PREVIEW_JSON"

python3 - "$PREVIEW_JSON" <<'PY'
import json, sys
document = json.load(open(sys.argv[1], encoding="utf-8"))
assert document["status"] == "DISPATCH_PREVIEW"
assert document["planner"]["provider"] == "deepseek"
assert document["planner"]["model"] == "deepseek-v4-flash"
assert document["planner_outcome"] == "supported"
print(document["confirmation_digest"])
PY

export CONFIRMATION_DIGEST="$(python3 -c \
  'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["confirmation_digest"])' \
  "$PREVIEW_JSON")"
```

人工检查 preview 的 instruction 语义、command、provider/model 后，使用**完全相同的 instruction**
执行一次：

```zsh
ros2 run so101_demo_py text_pick_agent \
  --instruction 'Pick the plastic cup. Apply no constraints.' \
  --request-id "$REQUEST_ID" \
  --backend mujoco \
  --mode execute \
  --execute \
  --confirmation-digest "$CONFIRMATION_DIGEST" \
  --session-id "$SESSION_ID" \
  --expected-reset-epoch "$RESET_EPOCH" \
  --evidence-root "$EVIDENCE_ROOT" \
  --source-commit "$(git rev-parse HEAD)" \
  --installed-prefix "$(ros2 pkg prefix so101_demo_py)"
```

若第二次 provider 结果漂移，执行应返回 `CONFIRMATION_DIGEST_MISMATCH`；这不是重试 execute 的
理由。重新 preview 属于新的 fail-closed provider observation，真正 execute 仍必须保持一次。

## qwen3.5:4b fallback：显式取消 cloud key

qwen workflow 先按上面的方式安全加载 `~/.env`，随后只对当前 shell/session 取消 cloud key：

```zsh
unset DEEPSEEK_API_KEY
print -r -- 'DEEPSEEK_API_KEY=UNSET'
```

其余 preview-confirm-execute 命令相同。默认 endpoint 是
`http://127.0.0.1:11434/api/chat`；localhost reverse tunnel 可以显式传入例如：

```zsh
--ollama-endpoint http://127.0.0.1:21434/api/chat
```

preview 必须读回 `planner.provider=ollama`、`planner.model=qwen3.5:4b` 和
`planner_outcome=supported`，再把该次 digest 原样交给 execute。不要用空 key 字符串参数模拟
fallback；provider 选择只读取环境中的 `DEEPSEEK_API_KEY`。

## 正确理解状态和证据层

- `DISPATCH_PREVIEW`：静态 outcome/command/capability 通过，`dispatch=false`；没有 ROS runtime。
- `RUNTIME_STARTED`：只出现在 `state_trace`，表示 typed Executor 已被调用。
- `RUNTIME_COMPLETED`：dynamic runtime 返回 exit 0；它不是物理成功的别名。
- state-machine dispatch：还要用同一个 request/session 在 runtime log 中证明 state machine 确实
  启动，而不只是 Agent 生成了状态字段。
- downstream `DONE`：说明当前 dynamic state machine 走到终点，可作为下游诊断证据。
- V5-T005 physical proof：另一个验收任务，必须独立证明 cup pose/contact、MoveIt attached/world
  scene、controller/joint/TF、fresh visual evidence 和规定的连续有效运行。V5-T003 的 `DONE` 不能
  升格为 V5-T005 结论。
