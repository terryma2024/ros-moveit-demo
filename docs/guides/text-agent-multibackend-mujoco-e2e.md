# Text Agent 多后端 MuJoCo E2E 使用与验收指南

本指南记录 `so101_mujoco_text_pick_agent_e2e.launch.py` 的当前用法和 2026-09-08 的现场结果。当前提交 `1614eb84ef73ad36f050368a65ef40ddae3ea78f` 已在 macOS/MPS 和 ai-station/CUDA 上通过 YOLO-Seg 四点位验收，两个平台的普通测试也全部通过。Grounded SAM、连续五次、其余现场负例、GUI 视频和学习者验收仍未完成，因此不能把 YOLO 两格通过写成整个双模型矩阵已经验收。

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
export E2E_IMAGE=so101-yolo11n-seg-inference:text-agent-e2e-1614eb84
export E2E_DEVICE=cuda
export E2E_RUNTIME=docker
```

镜像 ID 和本地 repo digest 都是 `sha256:56f88257d1124cd02121d99f422c4f98aec198ea7873fa4ccf9a5407dd4093e0`。旧镜像继续保留审计，不用于当前提交的资格运行。

先从当前 overlay 读出参数，避免凭记忆拼命令：

```bash
ros2 launch so101_demo_py so101_mujoco_text_pick_agent_e2e.launch.py --show-args
```

## ai-station YOLO headless 命令

下面是唯一杯执行模板。`E2E_ROOT` 每次都要换成新目录；不要在已有 `e2e-result.json` 的目录重跑。

```bash
export ROS_DOMAIN_ID=<fresh-valid-domain>
export E2E_SESSION=text-e2e-linux-yolo-$(uuidgen)
export E2E_ROOT=/data/work/so101-evidence/text-agent-e2e/<run-id>/live/<fresh-run-id>

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

macOS 的 YOLO 格使用同一个 `.pt` 和 SHA256、host runtime 与实际 `mps`，并关闭 CPU fallback。当前提交的四次有效运行是 EXP-025、EXP-026、EXP-027b 和 EXP-028；EXP-027 因 `ROS_DOMAIN_ID=233` 超出 Fast DDS 合法端口范围而记为 INVALID，没有计入四点结果。

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
| ai-station + YOLO-Seg + CUDA 四点位 | 通过 | EXP-037 至 EXP-040；位姿误差为 1.157、1.161、1.130、1.177 mm |
| macOS + YOLO-Seg + MPS 四点位 | 通过 | EXP-025、EXP-026、EXP-027b、EXP-028；位姿误差为 1.175、1.146、1.120、1.172 mm |
| ai-station + Grounded SAM | 未运行 | 没有已登记的 PickPlace-qualified bundle |
| macOS + Grounded SAM | 未运行 | 同上 |
| Planner 拒绝负例 | 通过 | EXP-015 实际 `qwen3.5:4b` 返回 unsupported；没有感知或运动副作用 |
| 双杯歧义负例 | 无效 | EXP-016 卡在 robot_description/正仿真时钟启动边界，没有进入推理 |
| MoveIt action abort 负例 | 未运行 | 没有现场注入证据 |
| 连续五次成功 | 未完成 | 当前四点位按位置验收，不能替代每配置连续五次门禁 |
| GUI 视频与新截图 | 未录制 | 不能用视频代替尚未通过的自动验收 |
| 学习者解释与掌握度 | 未记录 | 没有已确认身份的学习者现场回答 |

当前证据明确区分两个坐标系：感知输入来源仍是 `task_camera_frame`，`CUP_POSE_PUBLISHED.frame_id` 和 dynamic 输入都是 `world`。终态文件也分别标记 `mujoco_sim` 与 `system_wall`，不再直接相减这两个来源时间；采集先后只比较同一宿主机的 `readback_monotonic_ns`。这次修改没有放宽几何、稳定性或接触阈值。

八次有效 YOLO 四点运行都满足相同条件：launch 返回 0、`machine_accepted=true`、实际设备为 MPS 或 CUDA、杯体稳定且受支撑、无 fingertip contact、Planning Scene 的 attached 集合为空、最终位姿匹配，owned process/container 清理完整。当前矩阵的主要工件阻塞是两平台都没有登记可用于 PickPlace 资格运行的 Grounded SAM bundle。

## 已保留证据

主证据根：

```text
/data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad
```

ai-station 当前提交的四点运行位于 `live/exp-037-*` 到 `live/exp-040-*`；macOS 四点运行位于本地登记根的 `live/exp-025-*`、`exp-026-*`、`exp-027b-*` 和 `exp-028-*`。账本记录了固定 commit、模型、镜像、domain、session、命令、退出码和结论：

```text
docs/experiments/text-agent-multibackend-e2e-experiment-ledger.md
```

本轮没有删除证据。无效候选、无效运行和测试 scratch 只列为 deletion candidates，删除前必须另行取得授权。
