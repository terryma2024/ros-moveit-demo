# Head Search 40 点验证执行计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 本文先交付计划；实现、构建、仿真实跑尚未授权。保持现有 worktree，不自动启动 dst、另一个执行器或新分支。

**Goal:** 用当前独立 Head、ROS/JTC、真实相机和 CUDA 检测链串行验证 40 个声明场景，运行到搜索终态，完成停车、owned 退出和逐次离线审核。

**Architecture:** 复用 `so101_head_search_calibration run --execution-inputs`，每个 attempt 是一个独立、有封存日志的开发运行。新增薄层场景准备与串行编排；场景真值、业务退出码、审核器结果和用例结论分开保存。搜索输出不会传给抓放状态机。

**Tech Stack:** Python 3.12、ROS 2 Jazzy、MuJoCo 3.12.0、现有 Head-only JTC/native Stop、CUDA YOLO、file-v1、`so101_head_search_audit`。

**Spec:** 本次用户明确要求“40 点验证的是 Head Search，到 search 结束为止，不执行 pick-place 动作”；固定用例来自 `src/so101_demo_py/config/act/head-search-scenario-partitions-v1.json`；执行安全合同沿用 `docs/superpowers/plans/2026-10-04-so101-head-file-protocol-stage-one-plan.md` 与实际 F022 输入；审核能力边界沿用 `docs/superpowers/specs/2026-10-06-so101-head-search-stage-two-offline-audit-design.md`。本文提出的是测试编排补充，不授予 Head/ACT qualification。

## 全局约束

- 本轮交付计划和审查，所有执行步骤保持未执行。计划获后续执行授权后，先完成下列准备任务及验收门，再启动任何仿真。
- 当前主机 `AI-STATION-001`（antzb），直接本机操作，不 self SSH。worktree `/data/work/ws_moveit/.worktrees/so101-head-file-protocol-1003`，branch `codex/so101-head-file-protocol-1003`，HEAD `fcee299deb6953e683f81176052edd97b003b2df`，submodule `495c3d6f512b5301405fc0955576bc231e344a7f`。
- 保留已存在的用户 dirty 工作、stage-two 审核程序和所有旧证据。不 reset/stash/clean/rebase，不 commit/push，不删除证据，不操作硬件或共享服务。
- 只有一个仿真 attempt 和一个执行器同时运行。pytest 的 8-worker 门禁与实跑串行无关；实跑不得用 pytest-xdist 或 campaign worker pool 并行。
- 搜索阶段允许的运动 goal 只有 `/neck_controller/follow_joint_trajectory` 且 joint set 恰为 `['neck_yaw_joint']`。准备阶段可用已声明的 native reset 设置手臂、夹爪和物体初始状态；进入搜索后只维持初始姿态。
- 不调用 arm/gripper action 或其 fire-and-forget command topic，不进入 `APPROACH`、`DESCEND`、`CLOSE_GRIPPER`、`LIFT`、`PLACE`、`OPEN_GRIPPER`、attach/detach 或 ACT episode collection。不通过完整 pick-place launch 再靠 `stop_after` 截断。
- `TARGET_LOCKED` 后保留最终目标报告，只执行本轮本地 Stop、资源 retirement、seal 和退出。失败/超时/中断也完成同样证据链；停车不是 pick-place 动作。
- `event_log_enabled=true`；CUDA 固定 `cuda:0`、无 CPU fallback。安全阈值、搜索预算、三帧锁定、目标容差与 native Stop 合同不变。仅日志关闭的历史 off017 不进入本次分母。
- 场景、输入、代码、policy 或安装改变必须新 freeze 和新 run；不同 freeze 的结果分别统计。正式 40 点批次中不在线调参、修改目标位置后重跑同一个 ID 或择优替换失败。
- 未证明停车、发现非 neck 动作、原件损坏或 owned 清理未证明时停止后续执行。只对记录了 ownership 的本轮资源做现有有界收敛，不用宽泛进程清理。

## 已核对的基线与尚缺能力

CP-HFP-789 已完成基本离线审核程序。最终 ordinary/package 各 8262 PASS、152 SKIP；五份原始实跑中 normal013/on016 LOCKED，三个故障样本 FAILED。五份原始日志的 `exit_cleanup=UNKNOWN`，因为 ps/graph 命令缺少原始 UTC 采样开始时间。它们是历史回归输入，不是本次 40 点结果。

正式单次入口见 `src/so101_demo_py/src/cli/head_execution_run.py`，由 calibration CLI 的 `run --execution-inputs` 转交。其业务 rc0 表示锁定成功，rc1 可包含双杯、无杯等预期非锁定终态，rc2 是准入拒绝。不能只凭 rc0/1 判用例。

旧 `measure-scenarios` 使用 `MujocoEpisodePlant` 直接推进进程内模型，不证明新 ROS/JTC/native 执行路径。`prepare_episode_scene` 按 seed 和杯子数量准备状态；`scenario` 标签本身不施加低照度或部分遮挡。不能把旧 38/40 报告或四十次同一场景当作新验证。

当前输入的 `development_pose` 只声明 `arm_rad`、`neck_rad`、`cup_xyz`。多杯、遮挡、光照及原始输入中断需要可封存的场景 fixture 和原始状态回读。当前审核器还未识别生产端 `TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL` 为 `NOT_FOUND`；双杯原始终态则属于其现有非锁定 `FAILED` 类别。本计划在 Task 3 约束这些映射，保留分项结果及原始终态。

基线输入：`E/head-file-protocol-1003/freezes/event-log-switch-20261006-022/inputs/execution-inputs.json`。模型 SHA256 `2afd550694abfbe6d1c37922c9ea0b4a0f8567bef94cf4c4ec85d4b50c0cc82a`；development config SHA256 `875f9aefc8d0153928e51e3b4f330b71565d9e47d34ba800c521939443643a36`。重取原件校验后才使用，不能复制其旧 run/session/socket/ROS 路径作为新运行身份。

固定控制值包括 search timeout 30 s、Stop confirmation 1 s、native close 0.05 s、fault reaction 0.25 s、watchdog 0.02 s、perception job 1 s、perception max age 0.15 s、每停稳重观察最多 3、总重观察最多 12、center deadband 3 px、lock 3 帧、goal tolerance 0.05 rad、stop velocity `0.04136050464213824` rad/s。完整 config/policy 整文件绑定，不仅比较这些摘录。

## 40 条用例及判据

`k=0,1,2,3`，每类 seed 为 `900000 + 10*k + class_index`。anchor 和 scene_group_id 必须原样读取清单，不能按类名猜 anchor；清单会轮换 default/left/forward。

| class_index / condition_class | 固定 seeds | 必须施加并证明的条件 | 预期终态 |
| --- | --- | --- | --- |
| 0 nominal | 900000, 900010, 900020, 900030 | 一个合法目标，默认光照，声明 anchor | 正确目标 LOCKED |
| 1 left_anchor | 900001, 900011, 900021, 900031 | 一个合法目标，清单中该条 anchor 的起始姿态 | 正确目标 LOCKED |
| 2 forward_anchor | 900002, 900012, 900022, 900032 | 一个合法目标，清单中该条 anchor 的起始姿态 | 正确目标 LOCKED |
| 3 distractor_present | 900003, 900013, 900023, 900033 | 一个目标与非杯干扰物同时可见，实例分开标注 | 只锁真实杯子 |
| 4 two_cups | 900004, 900014, 900024, 900034 | 两个合法杯子在搜索可见区域，存在两杯同时可见的原始帧 | TARGET_AMBIGUOUS；零锁定 |
| 5 no_cup | 900005, 900015, 900025, 900035 | 声明安全搜索域内无目标杯子，完整完成有界搜索覆盖 | TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL；零锁定 |
| 6 low_light | 900006, 900016, 900026, 900036 | 场景 light diffuse/specular 为基准的 0.35 倍，ambient/相机外参不变；同姿态成对原图证明变暗 | 正确目标 LOCKED |
| 7 partial_occlusion | 900007, 900017, 900027, 900037 | 用现有 PARTIALLY_OCCLUDED_CUP 几何构造遮挡，成对 segmentation 证明 `0 < occluded_fraction < 1` | 可见真实目标 LOCKED |
| 8 fast_interruption | 900008, 900018, 900028, 900038 | 第一 attempt 尚未锁定时实际切断 camera Image/Info 输入；其余 clock/joint/TF 继续 | 第一 attempt 本地故障停车；新 attempt 正确 LOCKED |
| 9 reacquire_after_stop | 900009, 900019, 900029, 900039 | 第一 attempt 首次实际观测交接后、三帧锁定前，由外层 SIGTERM 触发本计划新增的受控 signal Stop；旧状态不能进入新 attempt | 第一 attempt 受控停车；新 attempt 正确 LOCKED |

0.35 是本计划提出的测试场景光照条件，不是检测或控制阈值。必须在执行前冻结 fixture；不得为了让模型锁定而临时改亮度。遮挡比例只证明“部分”，不冒充已标定的鲁棒性区间。

正常类有 32 个 single-attempt 场景，中断类有 8 个 two-attempt 场景，正式批次因此是 **40 个场景、48 个预定 attempt**。中断未成功触发、第一 attempt 提前锁定或第二 attempt 未执行都不能缩成单次通过；不允许追加第三次来择优。

`nominal`、方向类和干扰物的物体/材质变化仅取冻结 profile 的合法范围，用原 seed 决定。camera mount、内参、分辨率、frame_id 不做随机抖动。无杯场景保留接口需要的 `plastic_cup` 语义，但把它封存在声明搜索域外的有支撑 fixture 停放区；不能让模型内的自由杯子悬空掉落或以全遮挡冒充“无杯”。新增杯子/遮挡物/停放支撑必须进入实际 scene closure、semantic model SHA、joint/free-body 映射和现有碰撞检查。

真值来自封存场景状态及与原始 RGB 同时间的实例 segmentation，不来自 detector 的输出。锁定的三帧分别用 bbox 与各真值实例 mask 的交集做归属：唯一非零最大交集且三帧同一真实杯子才能判正确；并列、零交集或缺 mask 是 UNKNOWN，不能根据 track_id 名字猜物体。真值只用于验收，不供给 controller 或 CUDA detector。

实例 mask 由 Task 2 的离线 truth builder 产生。现有相机只发布 RGB/Info，不假定已有 segmentation。collector 保存实际 RGB/Info、`SceneStateEvidence` 及 lossless `PhysicsStepEvidenceChunk` 原件；以 native simulation session/reset epoch 和相机 source ns 精确关联完整 qpos/qvel，physics time 使用相机同一 `llround(time*1e9)` 转换。scene-state trylock 缺帧时只能使用同时间、同身份的完整 physics 原件；无唯一匹配、流丢失或状态冲突均是 UNKNOWN，不取最新状态、邻近帧、插值或 reset pose。

离线重建在独立 MuJoCo data 中使用冻结 model、完整状态和相机渲染参数，先核验模型不存在未记录的 mocap、deformation 或运行时 model 修改，再生成 RGB 与实例 mask。原始图、状态、模型/config、重建图和 mask 全部引用 SHA；同姿态 RGB 重建及投影一致性在 pilot 中证明后才能用于三帧归属。当前两个原始流是否覆盖所需帧尚未实跑证明，Task 2/5/6 将其列为正式准入门。若该合同不足，先阻塞并交付最小修订，不默默增加 native publisher 或实时分割。

已确认一个具体渲染阶段风险：native `mujoco_simulation.cpp` 在 `mj_step` 后直接通知 observer；CameraPlugin 用 `mjv_copyData` 复制当时的派生渲染状态，未先 `mj_forward`。physics 原件则记录 post-integration qpos/qvel，其源码注明 xpos/xquat 可能仍属于 integration 前。故 exact timestamp 本身不能证明离线 `mj_forward` 重建的是实际相机几何。Task 2 必须证明冻结代码下的 render-phase 等价性，包含运动帧和停稳帧；不通过则此真值路线 BLOCKED，正式 40 点不启动。不得用前一帧、插值、近似 RGB 门限或调宽投影门掩盖。最小状态/渲染合同修订另行交付，未经授权不修改 native。该缺口不影响当前计划交付，但尚未被解决。

## 证据布局、生命周期与命令边界

唯一根 `E=/data/work/so101-evidence/act-data/20260930-antzb-head-search-krIv681m`。

- 本计划批次 `Q=E/head-file-protocol-1003/head-search-40-plan-20261006-001`：baseline、计划冻结副本、self review、计划审查和最终 SHA。
- 后续执行批次拟用 `C=E/head-file-protocol-1003/head-search-40-20261006-001`，必须尚不存在；若已存在，选择新单调编号并先登记。本文不创建 C。
- C 下分 `freeze/001/`、`fixtures/<seed>/`、`pilots/<id>/`、`cases/<seed>/attempt-01/`、`attempt-02/`、`reviews/`、`scratch/<unique>/tmp/`、`campaign-manifest.json`、`campaign-results.json` 和 `.md`。失败与拒绝也保留。
- 私有低速日志/socket 放新建 `/tmp/so101-debug-head-file-protocol-1003/hs40-<campaign-token>/`；每个 attempt 用唯一短 socket namespace，不能复用 on016。

正式尝试使用 **FULL_RESTART** 生命周期：现有 provider 每次 owns/starts/retires 一套 stack，不为本测试新增共享 stack 热复用能力。48 个 attempt 严格串行，同一已核验的 ROS domain 候选 223，每次唯一 partition/session；若 domain 有他人进程，准入拒绝，不抢占。next attempt 必须在前一轮 OS exit、本地 Stop 和 owned postflight 都已证明之后开始。场景内的 native reset 是该 attempt 的准备事务，不改变 FULL_RESTART 分类。

不能把 on016 的旧 env 字符串直接复制。新 freeze 的 dependency underlay、实际 executable、`PYTHONPATH`、`AMENT_PREFIX_PATH`、`LD_LIBRARY_PATH` 都重新生成并验证。现有 F021 是依赖闭包候选，F022 是 producer 基线，stage-two `freeze-008` 是审核基线；新代码改变后它们都不充当新正式执行产物。

单次仍调用实际现有接口，以下变量由冻结 campaign manifest 赋值，不是操作者手填的占位输入：

```zsh
test -x "$TEST_PYTHON" && test -x "$HEAD_CLI" && test -x "$AUDIT_CLI" || exit 1
"$TEST_PYTHON" "$HEAD_CLI" run --execution-inputs "$CASE_INPUTS"
head_rc=$?
# launcher 必须先写 actual_os_return_code / ended_ns，再完成 owned postflight 和 receipt。
"$TEST_PYTHON" "$AUDIT_CLI" \
  --run-root "$RUN_ROOT" \
  --execution-receipt "$EXECUTION_RECEIPT" \
  --execution-receipt-sha256 "$RECEIPT_SHA256" \
  --output-root "$NEW_AUDIT_OUTPUT"
audit_rc=$?
```

launcher 用结构化 `subprocess` argv 捕获结果，保存完整 stdout/stderr、开始/结束 UTC ns、elapsed、真实 OS rc、Python/executable 哈希和导入来源。不用 `set -e` 在预期业务 rc1 后提前退出；使用 tee 的命令必须开启 pipefail。正式 campaign CLI 在 Task 4 创建前不存在，不能声称现在已有一条全量入口。

## Review Focus

1. 条件标签与实际场景不一致：对应 Task 2 的原始状态、亮度和遮挡真值测试。
2. 搜索结束后意外调用 arm/gripper 或接入 pick-place：对应 Task 3 的所有 action/command 边界和终态后零新 dispatch 测试。
3. 预期非锁定业务 rc1 被当作失败，或 audit rc0 被当作全部通过：对应 Task 1/3/4 的正反例及独立退出码字段。
4. 中断未作用于真实运行或旧结果进入新 attempt：对应 Task 3 的实际 SDK/观测事件触发、迟到结果和唯一身份测试。
5. 准入/停车/退出/磁盘问题被重试覆盖：对应 Task 4 的碰撞、缺采样时间、空间预算、未停车中止和不可覆盖测试。

## Task 1：冻结矩阵、纯判据与协议

**Files:** Create `src/so101_demo_py/src/act/head_search_campaign.py`; Test `src/so101_demo_py/test/test_act_head_search_campaign.py`。只读取现有 partitions，不修改它。

**Interfaces:** `load_cases(partitions: dict) -> list[dict]` 返回原顺序 40 条；`classify_case(case: dict, attempts: list[dict]) -> dict` 返回 case_id、原始终态、两类 rc、分项审核、场景真值、PASS/FAIL/UNKNOWN/INVALID/NOT_RUN 和原因；`aggregate_cases(cases: list[dict]) -> dict` 返回五类计数、分条件/anchor 统计及覆盖。全部纯函数，无 ROS/model imports。

- [ ] 写 RED：恰好 40 seed、每类 4、三个 split 不重叠、anchor 原值保留、bool seed/duplicate 拒绝；中断必须有两条独立身份 attempt。
- [ ] 写 RED：双杯 actual terminal AMBIGUOUS + business rc1 + audit integrity/Stop/exit PASS 是场景 PASS；无杯缺完整覆盖不是 PASS；audit rc0 + execution FAIL、错误杯子锁定、缺第二 attempt、Stop UNKNOWN 均非 PASS。
- [ ] 实现上述 pure interfaces；分类先保留事实，禁止改变原始业务状态、seal 或审核结果来满足预期。
- [ ] GREEN 回读完整断言。正式总表固定 40 行，未运行也有 NOT_RUN；准入拒绝为 INVALID，不删除分母行。保存 qualified 标志为 false。

## Task 2：场景 fixture 与真实 reset 验证

**Files:** Create `src/so101_demo_py/src/act/head_search_campaign_scene.py`、`src/so101_demo_py/src/act/head_search_campaign_truth.py`、`src/so101_demo_py/src/adapters/act/head_campaign_truth_collector.py`; Modify `src/so101_demo_py/src/act/head_execution_inputs.py`、`src/so101_demo_py/src/adapters/act/head_execution_reset.py`; Test `src/so101_demo_py/test/test_act_head_search_campaign_scene.py`、`src/so101_demo_py/test/test_act_head_search_campaign_truth.py`、`src/so101_demo_py/test/test_act_head_execution_originals.py`。

**Interfaces:** `prepare_case_fixture(case: dict, baseline_inputs: dict, output_root: Path) -> dict` 产生每条冻结 scene、`scenario-fixture.json`、初始 free-body 状态、truth 声明及 SHA。为 `refs` 增加可选 `scenario_fixture` 引用；旧输入无该 ref 时保持原行为。fixture 顶层严格固定为 schema_version、case_id、seed、condition_class、anchor、scene_sha256、reset_free_bodies、lighting、truth_manifest、injection；不添加未封存 callable/provider 插件。

- [ ] RED：当前 primary-only reset 无法证明两个杯子/遮挡物的姿态；仅 condition label、不变 light、无遮挡、无杯仍在声明域内、camera mount 抖动、closure 缺新资产全部拒绝。
- [ ] 基于原 seed 制作真实 scene variants：light 条件按表固定；遮挡用已有 enum 的几何规则；额外 free joints 写入 fixture reset 声明。相机外参不变，不直接复用旧生成器中带 camera jitter 的 qpos/model 快照。
- [ ] 为每个 variant 重建 camera geometry/scene closure、semantic SHA、safety_inputs joint/free-body maps，调用现有 safety loader；fixed safety fields 原样保留。无法通过现有安全检查的 fixture 是 BLOCKED，不移除检查或扩大 allowed_pairs。
- [ ] 扩展 `HeadSceneServices.reset_pose` 的可选 `fixture=None`，通过同一个 native ResetWorld 设置所有已声明 free-body 位姿；`OwnedHeadScene._verify_pose` 检查全部对象与 reset_epoch、paused、step0、零初始速度。已有 arm/gripper/native reset 行为保持，搜索阶段无 arm/gripper goal。
- [ ] 实现 `collect_frame_state_originals()` 与 `build_frame_truth(frame_ref, state_refs, fixture_ref, output_root)`：collector 在进入搜索前绑定本轮实际 native session/epoch、原始相机源和既有 physics chunk topic，并保存精确原件及接收时间；后者只做离线 exact join、独立重建及实例分割。冻结 chunk 开关/容量/消息 schema、相机 ID/分辨率/内参/mjv 渲染选项、光照/material 和 geom→真实物体映射，不把初始化 mask 用到后续旋转视角。
- [ ] RED/GREEN：三帧视角变化的正确实例、两杯误锁、分割并列、缺/冲突 same-ns state、错 native session/epoch、重置时间重复、physics chunk gap/loss、错误模型、图像垂直翻转及投影偏移。完整 qpos/qvel 只有在冻结模型已证明包含全部渲染自由度时足够；未记录的模型自由度拒绝重建。保留原 RGB 不变，真值不进入控制输入。
- [ ] 明确 render-phase RED：`mj_step` 后 qpos 已更新而 xpos/cam_xpos 未重算的运动帧不能靠同时间戳通过。冻结实际 camera/physics 代码和渲染参数，在独立 data 中验证运动及停稳状态的派生几何阶段、RGB 原始字节和实例投影等价；证明不成立就 BLOCKED，不猜测上一积分状态或修改 live data。pilot 只接受已证明等价的逐帧重建。
- [ ] GREEN：三种 anchor、0/1/2 可见目标、light/occlusion 真值、真实状态拒绝和旧默认 reset 回归通过；实例 mask/RGB 身份、投影与空间支持证明作为 fixture-readiness 原件保存。

## Task 3：Head-only 终态、中断与审核映射

**Files:** Create `src/so101_demo_py/src/adapters/act/head_campaign_camera_relay.py`; Modify `src/so101_demo_py/src/adapters/act/head_execution_provider.py`、`src/so101_demo_py/src/cli/head_execution_run.py`、`src/so101_demo_py/src/cli/head_execution_runner.py`、`src/so101_demo_py/src/act/head_run_reader.py`、`src/so101_demo_py/src/act/head_run_audit.py`; Test `src/so101_demo_py/test/test_act_head_search_campaign_runtime.py`。利用 CameraPlugin 已有 `image_topic`/`info_topic` 配置，在每条冻结插件副本中把 head publisher 设为 `/hs40/raw/color`、`/hs40/raw/camera_info`，relay 原样转发至生产 topics `/head_camera/color`、`/head_camera/camera_info`。验证 owned stack 确实加载该封存 plugin config；不使用全局 remap。

**Interfaces:** `CameraRelay` 是 campaign 进程内的受 ownership 管理 ROS fixture；原始 publisher 的 Image/Info 转发至生产订阅 topic，消息内容、源 stamp/frame_id 原样保持。`close_delivery(trigger: dict) -> dict` 只切断生产端 camera 输入，joint/clock/TF 和原始源记录继续；不能 forged source、注入检测框或模拟 ACK。无 fixture 的默认 provider 不构造 relay。

- [ ] RED：任何 arm/gripper goal/command、锁定后新 neck goal、结果送入 pick-place 回调，都拒绝本次“Head-only”。用已安装入口与真实构造边界测试，不能只对假 controller 测一个 flag。记录本轮 action/command 构造及发送边界与实际 controller 原件；日志未记录或原件缺失不能仅凭没有 Head 事件推断零非 neck 动作，判 UNKNOWN 并阻塞后续。
- [ ] 复核现有 runner 的 LOCKED →本地 Stop→return；原始 AMBIGUOUS/有界 NOT_FOUND 仍按现有 business rc1 退休，不把它们改成 business rc0。所有路径都保留 Stop 后原始 joint/native/cancel/GetResult 和 seal。
- [ ] 为 fast_interruption 冻结触发条件：第一 attempt 搜索阶段第一次真实 `HEAD_ACTION_SDK_RETURNED`，且尚无 LOCKED；同步关闭 camera relay 并记录同 UUID、源 topic、生产 topic、实际 source/receipt 水位与触发时间。超时由原 policy 判定，不直接 `fault()` 伪造失帧。若当前 producer 没有可独立 remap 的 Image/Info publisher，Task 3 阻塞，不用暂停整个 simulator 替代；完整 clock/joint 仍须推进以证明 Stop。
- [ ] 现有正式入口没有 OS SIGTERM handler；runner 的 stop_handoff 只是普通 neck 回调，不能作为现有 signal 接线。明确新增 main-thread scoped signal guard：在创建 provider 前安装处理器，保存首个请求的真实 signal/UTC/monotonic 时间；尚未绑定 runtime 时保留 pending，绑定后由正常控制线程交给 `runtime.stop('signal', evidence)`。handler 内不做 ROS/native 调用、写盘或等待；首请求不可覆盖，退出后恢复原 handler。runner 必须显式处理 `stop_requested`，停止新搜索 dispatch 并走原有 retirement/seal，不用假 FAULT/目标终态补齐退出。测试覆盖绑定前/后、首次请求、恢复和所有退出路径，默认无 signal 行为不变。
- [ ] reacquire_after_stop 在第一条真实 `LIVE_STOPPED_OBSERVATION_HANDOFF` 且尚未 LOCKED 时，由本轮 launcher 向有 PID/started_ticks 证明的执行进程发送一次 SIGTERM，使用上述新增 guard。保存发送及执行端接收的原件、当时 job ID；不添加不存在的 operator origin、不直接 kill stack、不声称切断正在执行的 GPU kernel。若请求晚于 LOCKED，该 attempt 记 INVALID。第二 attempt 使用新进程/全新 run/session/epoch/generation、tracker、锁定状态、原始源水位，保留同一场景状态声明；不复用旧 inference owner。
- [ ] RED/GREEN：实际故障/操作员 Stop、首请求不可覆盖、迟到结果/旧 generation 拒绝、无故障照常转发原始字节、旧模式无 relay、关闭后退出证明、旧 logging-off 零日志开销路径不受新可选 fixture 影响。
- [ ] 审核 profile 只登记本次经审查的新 source/freeze SHA，保持旧 F015/F022 语义回归。无杯将原始 `TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL` 映射为 NOT_FOUND，必须有原 required domain、完整有界 plan、实际同 UUID/epoch 的逐停稳位姿及观察证据；覆盖不足或 deadline/budget fault 不映射为 NOT_FOUND。双杯保持审核 schema 的非锁定 FAILED，campaign 判据另读 AMBIGUOUS 原件，不隐藏 execution/Stop/exit 的 FAIL。
- [ ] 新 profile 对真实受控 signal Stop 使用单独的中断原件映射：仅当首请求、执行端受理、无后续 dispatch、Stop 和退出证据完整时，认定预期中断条件已满足。搜索结果保留非锁定及原始原因，不伪造 LOCKED/NOT_FOUND/FAULT；如需新增 `INTERRUPTED` outcome，明确 schema 小修订及旧 profile 兼容测试。campaign 的预期中断 PASS 不等于搜索锁定成功，缺接收/交接证据仍 UNKNOWN。
- [ ] 若现有 schema 不能容纳真实场景/中断原件，先写明确的小范围合同修订与 RED，不能顺手加入 CDR/完整轨迹/碰撞重证、准入资格或 episode 自动处置。

## Task 4：串行 launcher、postflight 与汇总

**Files:** Create `src/so101_demo_py/src/cli/head_search_campaign.py`; Modify `src/so101_demo_py/setup.py`; Test `src/so101_demo_py/test/test_cli_head_search_campaign.py`。

**Interfaces:** 新 console entry `so101_head_search_campaign = so101_demo.cli.head_search_campaign:main`；`main(argv=None) -> int` 的业务参数仅为 `--manifest ABS --output-root NEWABS --phase pilot|formal` 和可选 `--execute-simulation`（另有标准 `--help`）。manifest 包含固定矩阵 SHA、全部 fixture/input refs、freeze/provenance、阶段 seed 列表、允许的 Head-only 终态、实际 executable/Python 路径与空间预算。创建前校验完整 inputs 和 output collision。无执行开关仅只读 preflight，既不创建 output/run root，也不启动 ROS/仿真；通过返回 0、准入未满足返回 2、内部错误返回 3，不产出已执行 PASS 报告。

- [ ] RED：输出已存在、路径/sha 错、闭包缺失、未知终态、camera hook 不成立、日志开关 false、旧身份/固定 socket、资源不够和 arm/gripper action 启动全部 fail closed。
- [ ] 生成每轮严格 `HeadExecutionInputs.parse` 可接受的封存输入；可选 fixture ref 只在本次 unqualified campaign 可用。所有源码/模型/控制值保持冻结；run_root 不创建直到对应入口获准。
- [ ] launcher 保存 child PID/started_ticks、argv、UTC started_ns/ended_ns、actual_os_return_code、业务 completion、owned ROS node 名称和 domain/partition。OS ended_ns 记录完成后再开始 ps/graph 采样，每个 command 保存真实 started_ns/ended_ns/rc/stdout/stderr；时间来自执行该命令的外层进程，不填 phase 标签或文件 mtime。
- [ ] 调用正式安装审核器，每轮全新 output。回读 completion 标记及四份报告的 SHA/size、全部原件前后 SHA/size、实际 audit rc，才能记入 campaign 行。
- [ ] 执行 rc 按 phase 定义：formal 的完整分母是 40 case/48 attempt；pilot 是声明的 5 attempt。各自报告有 phase、expected_case_count/expected_attempt_count 和实际计数；pilot 两条中断仅验证首 attempt，不调用要求第二 attempt 的 formal classifier。0 是该 phase 报告完整且全部预期条件 PASS；1 是完整报告且有 VALID FAIL/UNKNOWN；2 是准入或安全证据门未满足、NOT_RUN/INVALID；3 是 launcher/发布内部错误。安全证据 UNKNOWN 的中止优先 rc2，纯搜索/真值 UNKNOWN 且安全链完整可 rc1；原 child/business/auditor rc 独立保存。
- [ ] 场景搜索终态不符合预期但 Stop/exit/integrity 全部已证明，保存 VALID FAIL 并继续剩余场景。Stop/exit UNKNOWN/FAIL、非法动作、input 原件变化或 owned 资源未退出时停止 campaign，余下 NOT_RUN，禁止自动重启接着计数。
- [ ] formal 汇总固定 40 行及 48 attempt 索引；pilot 单独固定 5 行，绝不补入正式表。分别给出 valid-pass、valid-fail、unknown、invalid、not-run、condition/anchor 分组、搜索终态、错误锁定、非 neck dispatch、真实 Stop/exit、frame freshness 与耗时。每条无日志/漏 seed 都可追溯。

## Task 5：回归、copy-install 与运行准入

**Files:** 复用已登记 pytest/colcon wrapper 规范，新增本批次冻结脚本放 C 的 evidence 区；测试仍在 `src/so101_demo_py/test/`，不跑 benchmark。

- [ ] 先用精确 `/data/work/venvs/so101-v5-t004-perception/bin/python3` 检查 executability、pytest/xdist/ROS/model imports。每轮新建 C/scratch 下从未存在的 NVMe TMPDIR/TMP/TEMP，验证两个实际 interpreter 的 `tempfile.gettempdir()` 及所有8worker proofs。
- [ ] 对 Task1–4 各自行为运行真正 RED/GREEN，保存 actual rc/elapsed/JUnit/输入原件/源快照。新增 camera relay/生产绑定必须有真实接口边界回归，不用绕过 native/ROS 的 mock 宣称全链路通过。
- [ ] 完整 demo 普通 `test/ -n 8`、必要 package `colcon test --packages-select so101_demo_py --pytest-args test -n 8` 及 `colcon test-result --verbose`。现场24CPU，8worker不降低；若修改 native support/launch 消息等其他模块，也完成其相应全量普通与 package/native gates。未改模块不重复其全量 gate。
- [ ] 使用 dependency-closed copy-install（不 symlink），固定新的 build/install root；核验现有 F021 依赖实文件和所有实际新 runtime/fixture/auditor 模块 origins、SHA，记录 dirty 源快照。旧 F022 与 stage-two freeze008 永远保留为历史基线。
- [ ] 在最终安装入口运行 campaign/preflight `--help` 与拒绝负例；回归审核既有5原件/23独立变造语料，旧真实退出 UNKNOWN 保持。不得回填历史 ps/graph 时间使旧报告 PASS。
- [ ] 计算磁盘预算：至少覆盖53个 attempt（5 pilot+48正式）的 lossless 上限、完整 build/install 闭包、两轮全量测试 scratch、报告和20%余量；按实际已保存原件速率及最大现有 scratch 计算，并登记 bytes/free。2026-10-06计划时 free约16.7GiB，尚未证明足够。资源不足停在准入，不删证据、关 fsync/采样、改 tmpfs、压缩丢帧或减worker。
- [ ] preflight只读检查 ps/tmux/ROS graph/native ownership 和 CUDA，确认候选domain223不被他人占用、无第二stack、没有共享服务将被本批次关闭。为本轮写PLANNED条目后才可执行；本计划不包含该实跑授权。

## Task 6：pilot、正式40点和交接

**Files:** C 下 runtime 原件与报告；继续单写入者更新 `docs/experiments/so101-head-file-protocol-1003-experiment-ledger.md`，不把高频日志放源码。

- [ ] pilot采用5个独立ID验证原始流程：nominal900000、two_cups900004、no_cup900005、fast_interruption900008的首次中断attempt、reacquire_after_stop900009的首次操作员Stop attempt。pilot不进入正式40分母，也不能充当正式第二attempt。
- [ ] pilot必须证明实际 scene 条件、仅 neck 动作、每种终态/故障语义的日志和报告映射，以及原始 Stop/退出采样时序。逐原图 exact state 匹配、lossless chunk 可用性及离线重建投影必须成立；不足则 UNKNOWN 并阻塞正式批次，不能拿初始化真值代替。两个中断 pilot 分别按真实失帧/受控 signal 请求、未提前锁定、Stop/退出及无迟到新 dispatch 判断首 attempt，不要求不存在的第二 attempt。纯搜索行为不达标但证据链完整可记录失败；不放宽阈值。
- [ ] 源码/fixture/阈值改动后新freeze，并重新完成受影响门禁与对应pilot；不会拼接不同版本。确认冻结source、fixtures、model、policy、安装SHA不变后，按清单原顺序串行正式48个attempt，得到40个case结果。
- [ ] 每轮状态 `PLANNED → RUNNING → VALID/INVALID`；另存其case PASS/FAIL/UNKNOWN，lifecycle FULL_RESTART。每轮完成后写真实来源和下一条实验ID；失败不改旧行、不追加免费重试。
- [ ] 场景RGB、实例真值和Stop前后原件作为每条视觉证据。再按项目gui-capture技能，对本次fresh界面/图像做有界抽查（每类至少1条及所有误锁/异常条），数值/原图仍覆盖全部40条。截图不替代完整原件，不操作共享codex-cua会话。
- [ ] 最终只在40条都PASS、48attempt完整、零误锁、零非neck dispatch、完整性/执行/Stop/owned退出均通过及所有冻结输入不变时报告“40点Head Search通过”。否则逐项报数量与缺口，不授予qualification，也不声称pick-place成功。
- [ ] 保留所有原件、输入、freeze、失败、pilot、正式报告和当前计划/审查；列retained、archived（默认NONE）、scratch/私有IPC删除候选。不得删除。完成后更新ledger及handoff，列source/install/domain/partition/实际入口/原始OS rc与未评估能力。

## 计划自审与实施边界

本文逐项覆盖40条清单，正式与pilot分开；中断是两attempt，搜索结束后没有抓放分支。default provider仍承担本轮全生命周期，测试不会偷换为旧进程内plant。字段/函数/CLI标为拟新增的接口，不能把它们当已安装能力。Task2/3/4完成和正式准入门通过前，40点入口不可运行。

现有stage-one normal014准入超时、Task6/Task8子进程启动超时初始原因、历史APPROACH和完整抓放缺口不由本计划自动关闭。停止在search之后不会证明approach、抓取、搬运、放置或episode质量。

计划审查将重点核对输入闭包、原始camera中断可实施性、无杯与双杯语义、全部48attempt的Stop，以及搜索后零pick-place。任何无法在现有合同内实现的部分要给出具体阻塞与最小修订，不能把UNKNOWN改成PASS。
