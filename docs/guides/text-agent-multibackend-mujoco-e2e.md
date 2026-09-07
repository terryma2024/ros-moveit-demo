# Text Agent 多后端 MuJoCo E2E 使用与验收指南

本指南记录 `so101_mujoco_text_pick_agent_e2e.launch.py` 的当前用法和 2026-09-08 的现场结果。代码路径已经通过 macOS 与 ai-station 的普通测试门，但完整现场验收尚未通过。不要把下面的失败运行当成可发布的成功证据。

## 三个入口分别做什么

| 入口 | 用途 | 是否属于本轮新接口 |
|---|---|---|
| `so101_mujoco_text_pick_agent.launch.py` | 复现既有 Text Agent 课程，继续使用颜色几何感知 | 否，接口保持原样 |
| `so101_mujoco_perception_pick_place.launch.py` | 跳过自然语言 Planner，直接检查多后端感知与动态抓取 | 否，内部复用共享感知构造 |
| `so101_mujoco_text_pick_agent_e2e.launch.py` | 运行自然语言 Planner、多后端感知、MoveIt、MuJoCo 和独立终态验证 | 是 |

新入口只有在 `E2E_ACCEPTED`、所有 owned process/container 清理完成、`e2e-result.json` 原子写入后才返回 0。看到杯子移动不代表验收通过。

## 运行前固定输入

每轮都要使用新的 `ROS_DOMAIN_ID`、`session_id` 和 run root。`evidence_file` 必须是尚不存在的绝对路径。Planner 凭据通过现有安全配置提供，不能写进命令或日志。

本轮 ai-station YOLO 输入如下：

```bash
export E2E_WEIGHTS=/data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/training/full-exp-012/best.pt
export E2E_WEIGHTS_SHA256=f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
export E2E_IMAGE=so101-yolo11n-seg-inference:text-agent-e2e-09b8bc0c
export E2E_DEVICE=cuda
export E2E_RUNTIME=docker
```

镜像 digest 是 `sha256:bed9bda05f455d3732d3c5b854744b3097b92e7e84375ff0c3305cb1b17f77c7`。旧镜像 `sha256:fafdb147fab33758b45f8edb39d6ddb231b38ebe59b99dce17f01a0bf35d3a3e` 没有 `--require-output-subscriber`、`--emit-workflow-events` 和 `--workflow-id`，不能用于这个入口。

先从当前 overlay 读出参数，避免凭记忆拼命令：

```bash
ros2 launch so101_demo_py so101_mujoco_text_pick_agent_e2e.launch.py --show-args
```

## ai-station YOLO headless 命令

下面是唯一杯执行模板。`E2E_ROOT` 每次都要换成新目录；不要在已有 `e2e-result.json` 的目录重跑。

```bash
export ROS_DOMAIN_ID=224
export E2E_SESSION=text-e2e-linux-yolo-017
export E2E_ROOT=/data/work/so101-evidence/text-agent-e2e/<run-id>/live/exp-017-linux-yolo-run-01

ros2 launch so101_demo_py so101_mujoco_text_pick_agent_e2e.launch.py \
  instruction:='Pick the plastic cup. Apply no constraints.' \
  run_mode:=execute execute:=true skip_confirmation:=true \
  headless:=true sensor_rendering:=true \
  session_id:="$E2E_SESSION" evidence_file:="$E2E_ROOT/e2e-result.json" \
  perception_backend:=yolo_seg \
  perception_runtime:="$E2E_RUNTIME" perception_device:="$E2E_DEVICE" \
  perception_allow_cpu_fallback:=false \
  perception_weights:="$E2E_WEIGHTS" \
  perception_weights_sha256:="$E2E_WEIGHTS_SHA256" \
  perception_container_image:="$E2E_IMAGE"
print -r -- "$?" > "$E2E_ROOT/launch-exit-code.txt"
```

macOS 的正式 YOLO 格应使用同一个 `.pt` 和 SHA256，host runtime 与实际 `mps`，同时保持 CPU fallback 关闭。当前没有 macOS 现场运行证据，所以不能照此指南宣称 MPS 已验收。

Grounded SAM 需要已登记且支持目标设备的 PickPlace-qualified bundle：

```bash
perception_backend:=grounded_sam \
perception_runtime:="$E2E_RUNTIME" \
perception_device:="$E2E_DEVICE" \
perception_allow_cpu_fallback:=false \
perception_model_root:="$E2E_MODEL_ROOT" \
perception_model_manifest_sha256:="$E2E_MODEL_MANIFEST_SHA256"
```

这段参数要替换 YOLO 参数并追加到完整 `ros2 launch` 命令。当前没有合格 bundle，macOS 和 ai-station 两格均未运行。

## 怎样读事件和最终结果

`workflow-events.ndjson` 是严格控制协议。正常顺序是：

```text
STACK_READY
  -> DISPATCH_PREVIEW
  -> RUNTIME_STARTED
  -> RUNTIME_READY
  -> PERCEPTION_READY
  -> TARGET_SELECTED
  -> CUP_POSE_PUBLISHED
  -> RUNTIME_COMPLETED
  -> E2E_ACCEPTED
```

用 `jq` 先看阶段，再看首错和清理：

```bash
jq -r '[.component,.event,.status,(.failure_code // "-")] | @tsv' \
  "$E2E_ROOT/workflow-events.ndjson"

jq '{machine_accepted,primary_failure,secondary_failures,runtime_exit_code,
     physical_outcome,planning_scene_outcome,owned_process_cleanup,artifact_paths}' \
  "$E2E_ROOT/e2e-result.json"
```

顶层只认第一个有效终态失败为 `primary_failure`。清理或退出期间的新问题进入 `secondary_failures`。`runtime_exit_code: 0` 只表示动态执行程序完成，物理结果、Planning Scene 或清理失败仍会让 launch 返回非零。

每轮目录应包含：

```text
<run-root>/
  workflow-events.ndjson
  e2e-result.json
  perception/
  dynamic/
  acceptance/
    mujoco-final.json
    planning-scene-final.json
    result.json
```

如果某阶段提前失败，后面的目录或文件可能不存在。缺失本身是失败证据，不能补写或从另一轮复制。

## 当前现场结论

| 验收项 | 结果 | 证据或原因 |
|---|---|---|
| ai-station + YOLO-Seg + CUDA 唯一杯 | 未验收 | EXP-014 完成 Planner、感知、19 个 runtime 状态和稳定放置，但 validator 拒绝 |
| macOS + YOLO-Seg + MPS 唯一杯 | 未运行 | 成功路径协议先行阻塞 |
| ai-station + Grounded SAM | 未运行 | 没有已登记的 PickPlace-qualified bundle |
| macOS + Grounded SAM | 未运行 | 同上 |
| Planner 拒绝负例 | 通过 | EXP-015 实际 `qwen3.5:4b` 返回 unsupported；没有感知或运动副作用 |
| 双杯歧义负例 | 无效 | EXP-016 卡在 robot_description/正仿真时钟启动边界，没有进入推理 |
| MoveIt action abort 负例 | 未运行 | 没有现场注入证据 |
| 连续五次成功 | 未开始 | 没有任何 machine-accepted 首次运行 |
| GUI 视频与新截图 | 未录制 | 不能用视频代替尚未通过的自动验收 |
| 学习者解释与掌握度 | 未记录 | 没有已确认身份的学习者现场回答 |

EXP-014 的物理结果不是失败根因。杯子在 MuJoCo 中稳定、受桌面支撑、没有 fingertip contact；Planning Scene 与 MuJoCo 的位置差为 `0.0011658013223472305 m`，姿态差为 `0.000009062552536113162 rad`，都在策略阈值内。

当前阻塞来自证据语义：dynamic 的 `input_frame_id` 是发布后的 `world`，perception 的 `source_frame_id` 是传感器输入 `task_camera_frame`，validator 却要求二者相等。MuJoCo 终态时间戳使用仿真时钟 `58704000000`，Planning Scene 读回使用墙上时钟 `1788810607533085057`，现有 5 秒 skew 检查无法成立。下一轮代码变更应先明确 published frame provenance 和 timestamp domain，再重跑 fresh matrix；不要放宽几何阈值来掩盖这个问题。

## 已保留证据

主证据根：

```text
/data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad
```

现场运行位于 `live/exp-011-*` 到 `live/exp-016-*`。账本记录了每轮的固定 commit、模型、镜像、domain、session、命令、退出码和结论：

```text
docs/experiments/text-agent-multibackend-e2e-experiment-ledger.md
```

本轮没有删除证据。`build/`、`install/`、候选 venv 和所有测试 scratch 仅列为 deletion candidates，删除前必须另行取得授权。
