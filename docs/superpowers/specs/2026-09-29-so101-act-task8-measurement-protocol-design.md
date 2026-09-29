# SO-101 ACT Task 8 MuJoCo measurement protocol 补充设计

**日期：** 2026-09-29  
**状态：** 独立 GPT-6 Astra / High 三轮审查通过  
**适用范围：** ai-station、MuJoCo-only、Task 8L 首轮校准与 `TASK8_READY` 生成  
**不在范围内：** Gazebo、真实 SO-101、正式采集、ACT 训练、W4/W6

## 1. 问题与决定

当前代码已经有 measurement contract、测量 CLI、batch 封存和离线 aggregator，但没有生产
MuJoCo measurement driver。现有 aggregator 还会读取原始文件中的 `target_in_view`、`qualified`、
`contact_ok` 和 execution `*_ok` 等布尔结论，不能证明结果是从原始证据重新计算得到的。

本补充设计采用以下方案：

1. driver 只采集原始事实，不产生 PASS、FAIL 或 `TASK8_READY`。
2. 一个测量 batch 覆盖 default、left、forward 三个 anchor。每个 anchor 使用独立
   `FULL_RESTART`、session、reset epoch 和 attempt；任一 anchor 无效会使整个 batch `INVALID`。
3. 离线 aggregator 只能读取 `batch.json.files` 列出的普通文件，并从 raw evidence 重算所有字段和检查。
4. 现有 head-search closed sample 继续承载 17 个 search 字段和 4 个 head camera 字段，共 21 项。
5. `TASK8_READY` 还需要 7 个 live 前字段。它们进入单独的 `task8-ready-support.json`：
   `wrist_translation_m`、`wrist_rpy_rad`、`wrist_intrinsics_px`、`velocity_limit_rad_s`、
   `acceleration_limit_rad_s2`、`path_step_s`、`path_clearance_m`。
6. release/retreat 的 5 个字段仍在 Task 8 live 后从五次 FULL 的原始 evidence 生成，首轮校准不得填写。
7. 首轮校准走专用 admission 和 owner，不借用伪造的 `TASK8_READY`，也不启动 production Task 8 child。

`runtime-task8l-gen3` 保留为审计证据，但不得继续测量。实现完成后从一个全新、此前不存在的
`runtime-task8l-gen4/` 重做 provenance、五项 identity、contract binding 和整个 Task 8L。若该目录在实施前
已经存在，则必须分配下一代目录，不能复用或覆盖。

## 2. 方案边界

### 2.1 选择的方案

measurement protocol 分成四个互不替代的组件：

```text
bound contract + calibration admission
                 |
                 v
      MuJoCo measurement driver
      只写 raw evidence，不写 verdict
                 |
                 v
           sealed batch.json
                 |
                 v
       deterministic aggregator
                 |
        +--------+-------------------+
        |                            |
        v                            v
head-search-qualification.json  task8-ready-support.json
        |                            |
        +-------------+--------------+
                      v
          task8-ready-calibration.json
```

measurement driver 复用现有 MuJoCo backend、camera topics、TF、broker、controller readback、PathProof 和
cleanup state machine。它不复制这些组件的判断逻辑，也不调用 Task 8 production admission。

### 2.2 不采用的方案

- 不让 driver 写 `target_in_view=true`、`velocity_ok=true` 之类的结果，再由 aggregator 汇总。
- 不给 production Task 8 child 增加“忽略校准”开关。
- 不用单元测试 fixture 生成的 `TASK8_READY` 启动 live。
- 不从 gen3 复用 provenance、identity、bound contract 或 bundle。
- 不在资源不足时降低 camera cadence、CUDA 要求、路径网格、碰撞预算或 worker 档位。

## 3. 冻结身份与 batch 结构

### 3.1 Contract v2

实现将 measurement contract 升级为 v2。bound contract 必须绑定以下原始文件的规范路径和 SHA256：

- source provenance；
- runtime descriptor 与 head-search config；
- anchor config；
- approved contact policy 与 activation receipt；
- installed ACT profile；
- MuJoCo XML、URDF、controller config、joint limit 和 camera plugin config；
- phase plan、phase-camera coverage matrix、PathProof profile；
- calibration-search candidate config 与 calibration-search policy；
- detector weights、模型 ID、Torch/Ultralytics 版本和 CUDA device policy。

合同为每个 measurement 固定 `unit`、`source_kind`、`comparator`、`formula_id`、窗口、阈值来源和失败码。
CLI 不提供阈值覆盖参数。

`task8-calibration-search-candidate-v1.json` 是新增的受控输入，逐项保存 17 个 search 配置值、detector/runtime
身份、三个 anchor 的 `neck_start_rad` 和候选 safe interval。它不是校准结果，也不能由本次观测反向拟合。
`task8-calibration-search-policy-v1.json` 固定搜索状态机源码 hash、coarse/fine 算法、超时起点、候选目标生成、
越界处理、controller generation 绑定和 stop/cleanup 规则。Contract v2 分别保存两者 SHA256。

### 3.2 Batch identity

`batch.json.identity` 使用闭合字段集：

```text
source_commit
config_sha256
source_provenance_sha256
runtime_config_sha256
anchors_sha256
contact_policy_fingerprint
act_profile_sha256
measurement_contract_sha256
phase_camera_matrix_sha256
driver_source_sha256
```

`source_commit` 与 `config_sha256` 不再由 aggregator 从一个不保证存在的附加字段中读取。CLI 在启动 driver
之前构造完整 identity，driver、batch seal 和 aggregator 使用同一对象。

### 3.3 Raw batch 布局

一个有效 batch 至少包含：

```text
batch.json
campaign.json
sources/index.json
anchors/default/run.json
anchors/default/phase-events.jsonl
anchors/default/cameras/{head,wrist,task}/camera-info.jsonl
anchors/default/cameras/{head,wrist,task}/frames.jsonl
anchors/default/cameras/{head,wrist}/segmentation.jsonl
anchors/default/detector/head-detections.jsonl
anchors/default/search/state-events.jsonl
anchors/default/joints.jsonl
anchors/default/tf.jsonl
anchors/default/controller/{commands,references,feedback,goal-events}.jsonl
anchors/default/mujoco/{poses,contacts,render-projection}.jsonl
anchors/default/path-proof.jsonl
anchors/default/broker-events.jsonl
anchors/default/cleanup-receipt.json
anchors/left/...
anchors/forward/...
```

大体积 RGB 与 segmentation 数据可以使用逐帧二进制文件加 JSONL index，但 index 必须记录相对路径、
SHA256、编码、shape、source stamp、receive monotonic time、session、reset epoch、attempt 和 physics step。

封存规则：

- `batch.json.files` 精确列出 batch 内除自身以外的全部普通文件；不允许 symlink、hardlink 到 root 外、
  `..`、绝对相对项或未登记文件。
- aggregator 先验证目录实际文件集与 index 完全相等，再打开 raw evidence。它不能通过猜路径读取文件。
- batch 只允许 `CLOSED` 或 `INVALID`。driver 抛错、cleanup 不完整、session 混用、资源瓶颈、缺帧或
  身份漂移都封存为 `INVALID`，不能聚合。
- 同一个 output root 不重开。重试使用新的 batch ID。

## 4. 21 个 head-search 字段

每项审计记录都包含以下结构：

```text
configured_limit: 值、比较方向、来源路径和来源 SHA256
observed_summary: count、min/max、必要的分位数、逐 anchor 摘要和 raw_refs
reported_value: 最终写入 calibration report 的值
formula_id: 本节冻结的公式标识
```

这组结构只写入 `aggregation-receipt.json.field_audit`，不塞进 closed sample。closed sample 保持生产
validator 当前要求的精确形状，见第 5 节。

对配置型字段，`reported_value` 等于冻结配置，观测只用于证明运行没有越界。观测结果不能自动放宽配置。
对几何型字段，`reported_value` 由 raw CameraInfo/TF 按固定公式得到，并与冻结 MuJoCo/URDF 来源交叉核对。

### 4.1 Camera 几何字段

| 字段 | 原始来源 | 固定公式与 reported value | 失败条件 |
| --- | --- | --- | --- |
| `head_intrinsics_px` | 每个 anchor reset 后的 `/head_camera/camera_info` 原始 `K`、宽高；MuJoCo camera `fovy` | 每帧取 `[K00,K11,K02,K12]`；reported value 为全部有效帧逐分量中位数。另算 `fy=(H/2)/tan(fovy/2)`、`fx=fy`、`cx=W/2`、`cy=H/2` 交叉核对 | 非 640×480、K 非有限/变化、三个 anchor 不一致、与模型公式差值超过 contract tolerance |
| `head_translation_m` | neck=0 且 arm 在 canonical reset pose 时 `base -> head_camera_frame` TF；URDF fixed/neck joint 链 | reported value 为三个 anchor reset 后稳定窗口逐分量中位数 | TF 缺失、时间不因果、anchor 间超 tolerance、与 URDF forward transform 不一致 |
| `head_rpy_rad` | 与上一项同一 TF 的归一化 quaternion | 固定使用 ZYX 分解，先 unwrap 再逐分量中位数，范围规范到 `(-pi,pi]` | quaternion 非单位、奇异/非有限、与 URDF 结果不一致 |
| `yaw_zero_bearing_rad` | neck=0 时 `base -> head_camera_frame` rotation | ROS optical frame 前向轴为 `+Z`；`a=R*[0,0,1]`，reported value=`wrap_pi(atan2(a_y,a_x))` 的 circular median | 前向轴退化、三个 anchor 不一致、与模型/URDF 计算不一致 |

每个 anchor 必须提供至少 10 个连续的 post-reset CameraInfo/TF 样本。样本属于同一 reset epoch，且相邻 source
stamp 严格递增。不能从 XML 常量直接抄值后声称完成测量。

几何交叉核对的容差是协议常量，而不是 CLI 参数：CameraInfo `K` 每元素绝对误差 `<=1e-6 px`，translation
每轴绝对误差 `<=1e-6 m`，unwrap 后 rotation 每轴绝对误差 `<=1e-6 rad`，FOV 绝对误差
`<=1e-6 rad`，输入 quaternion norm 与 1 的绝对误差 `<=1e-9`。三个 anchor 的同名几何值使用同一容差；
任一维越界就失败，不用平均值掩盖单次漂移。

### 4.2 Search、detector 与 timing 字段

| 字段 | 原始来源 | 固定公式与 reported value | 比较方向与失败条件 |
| --- | --- | --- | --- |
| `horizontal_fov_rad` | raw head CameraInfo | 每帧 `atan(cx/fx)+atan((W-cx)/fx)`；reported value 取所有有效帧最小值 | `EXACT_WITH_TOLERANCE` 对模型 FOV；非有限或漂移即 FAIL |
| `coarse_step_rad` | bound calibration-search config、search state event、broker neck target event | state event 记录 `coarse_accumulator_before/after`；step=`after-before`。除最后一个覆盖剩余角度的 step 外都等于配置，最后一步 `0<step<=配置`；reported value=配置值 | 重发同一个 target 不生成新 state event，也不增加 accumulator；fine event 单独分类；step 越界、事件缺失或命令与 event target 不同为 FAIL/INVALID |
| `search_timeout_s` | config、`SEARCH_STARTED` state event、terminal event | 起点是第一次 `advance_deadline()` 设置 `started_wall_s` 的 monotonic 时刻，不是首个有效图像；elapsed=`terminal_monotonic-started_monotonic`；reported value=配置值 | 等待有效输入也计时；每个 anchor elapsed `<= configured_limit`；无 terminal 为 INVALID |
| `max_fine_corrections` | config、逐次 fine target event | 每个 anchor 统计 fine correction 次数；reported value=配置值 | count `<= configured_limit` |
| `max_fine_total_rad` | config、逐次 fine target delta | 每个 anchor `sum(abs(delta_rad))`；reported value=配置值 | sum `<= configured_limit` |
| `min_confidence` | config、原始 detector candidate confidence | 对进入 lock 判定的帧取 confidence 最小值；reported value=配置值 | 每个 accepted frame `>= configured_limit`；缺原始 candidate 为 INVALID |
| `tracking_iou` | config、连续 bbox、track assignment event | 同一继承 track 的相邻 bbox 用标准 intersection-over-union；observed=min IoU；reported value=配置值 | 继承时 IoU `>= configured_limit`；新 track 不计为继承，且会重置连续 lock |
| `min_bbox_aspect` | config、原始 bbox | `(y2-y1)/(x2-x1)`；observed=min；reported value=配置值 | accepted bbox aspect `>= configured_limit` |
| `center_deadband_px` | config、bbox 与 CameraInfo | `abs((x1+x2)/2-K02)`；observed=max；reported value=配置值 | lock frame error `<= configured_limit` |
| `vertical_bounds_px` | config、bbox center | `cy=(y1+y2)/2`；observed `[min(cy),max(cy)]`；reported value=配置区间 | 每个 lock frame center 必须位于配置闭区间 |
| `min_area_px2` | config、原始 bbox | `(x2-x1)*(y2-y1)`；observed=min；reported value=配置值 | accepted bbox area `>= configured_limit` |
| `max_age_s` | config、每个 source 的 receive monotonic time、decision monotonic time | 对 head image、CameraInfo、joint/TF 以及 phase coverage 所需来源计算 `decision_monotonic-received_monotonic`；observed=max | 每项 age `0<=age<=configured_limit`；负值、缺 receipt 或时钟倒退为 INVALID |
| `max_skew_s` | config、同一 causal sample 的 source stamps | `max(required_source_stamp)-min(required_source_stamp)`；search 集合为 head image/CameraInfo/joint/TF，phase 集合再含 wrist/reference/physics；observed=max | 每个 causal tuple `<= configured_limit`；跨未来取样或缺源为 INVALID |
| `lock_valid_neck_rad` | broker calibration-search command bound `[-2*pi,2*pi]`、三个 anchor canonical qpos、全路径 MuJoCo neck sweep、raw command/feedback | URDF continuous joint 不提供有限 limit。对 `[-2*pi,2*pi]` 按 0.002 rad 闭网格逐点检查三个 anchor 的 protected contact/clearance；状态变化的相邻网格用二分细化到 1e-5 rad。选择唯一一个同时包含 0 和三个 `neck_start_rad` 的安全连通分量，端点向安全侧收缩 1e-5 rad 后作为 reported interval | 没有这样的分量、出现多个无法由包含规则唯一选择的分量、区间不能容纳观测 current/target，或任一动态 segment 的独立 sweep 失败即 FAIL |
| `submit_lead_s` | config、raw controller submission event、首个 target sim time | 每个提交 `first_target_sim_s-submit_snapshot_sim_s`；observed=min；reported value=配置值 | 每次 lead `>= configured_limit`；使用 wall time 代替 sim time为 INVALID |
| `stop_velocity_rad_s` | config、raw joint/controller feedback | stop/revoke 后寻找 3 个连续、严格递增的 feedback；每个样本算六臂关节与 neck 的 `max(abs(v))`，observed 为证明窗口最大值；reported value=配置值 | 三个样本均 `<= configured_limit`；只信 broker `stop_confirmed` 为 INVALID |
| `stop_latency_s` | config、stop/revoke request monotonic time、上述第 3 个合格 feedback 的 receive monotonic time | `third_confirming_receive_monotonic-stop_request_monotonic`；observed=max；reported value=配置值 | 每个 stop proof `<= configured_limit`；只算首个样本或 worker 内部耗时为 INVALID |

三个 anchor 各自必须产生至少 3 个连续 lock frame。连续性要求同一 target track、严格递增 source stamp、
零缺帧，并且 confidence、area、aspect、center、vertical bound、age、skew 全部在合同内。最终
`observed_lock_frames` 是三个 anchor 最长合格连续段的最小值，类型为整数。

## 5. `TASK8_READY` 的 7 个 support 字段

21 字段 sample 不能单独满足现有 `require_gate()`。aggregator 还要生成一个 closed
`task8-ready-support.json`，字段如下：

| 字段 | 原始来源与公式 | PASS 规则 |
| --- | --- | --- |
| `wrist_intrinsics_px` | `/wrist_camera/camera_info`，公式与 head intrinsics 相同，三个 anchor、完整 phase coverage 中逐分量中位数 | frame size、K、模型 FOV 和跨 anchor 一致 |
| `wrist_translation_m` | URDF fixed parent `gripper -> wrist_camera_frame` 的 raw TF；逐分量中位数 | 全 phase 相对变换不漂移，并与 URDF/MuJoCo 固定变换一致 |
| `wrist_rpy_rad` | 同一 TF quaternion 的 ZYX unwrap/中位数 | 非有限、非单位或漂移即 FAIL |
| `velocity_limit_rad_s` | installed controller/policy limit 六维向量；全路径计划与 bounded live probe 的逐关节 `max(abs(dq/dt))` | observed 每维不超过配置，reported value 保持配置向量 |
| `acceleration_limit_rad_s2` | installed limit；按 raw reference/feedback 相邻时间戳计算逐关节速度，再对速度做相邻差分 | observed 每维不超过配置；时间间隔非正为 INVALID |
| `path_step_s` | approved PathProof profile 和每条 replay grid 时间戳 | reported value=配置值；所有相邻 grid `dt>0` 且 `dt<=configured_limit` |
| `path_clearance_m` | approved PathProof profile、MuJoCo 每个 grid 行的 protected geom signed distance 和 contact pair | observed=min signed distance；必须 `>= configured_limit`，合同 allowlist 内的显式接触按 phase 单独裁决 |

`head-search-qualification.json` 保持当前 `validate_head_search_binding()` 要求的精确字段集，不增加字段：

```text
schema_version
kind
status
head_search
observed_lock_frames
measurements
camera_measurements
source_commit
config_sha256
source_provenance_sha256
```

其中 `measurements` 是 17 个字段到裸 `reported_value` 的映射，`camera_measurements` 是 4 个字段到裸
`reported_value` 的映射，`observed_lock_frames` 是整数。`head_search` 与 production runtime descriptor
逐项相等。合同 hash、raw refs、configured limit 和 observed summary 只进入 aggregation receipt。

`task8-ready-support.json` 使用闭合字段集
`schema_version/kind/status/source_commit/config_sha256/source_provenance_sha256/measurements`，其中
`measurements` 是 7 个字段到裸值的映射。完整 identity 和逐字段审计同样留在 aggregation receipt。

calibration report 中每个 measurement 继续使用现有四字段形状
`value/unit/sample_path/sample_sha256`。21 个 measurement 全部指向同一个
`head-search-qualification.json`；7 个 support measurement 全部指向同一个
`task8-ready-support.json`。单位严格使用 `calibration.py` 的现有值：无量纲是 `1`，面积是 `px^2`，
不再使用 v1 template 的 `ratio` 或 `px2`。

`TASK8_READY` 报告共有 28 个 measurement。release/retreat 的以下 5 项不在报告中，相关 checks 固定为
`UNMEASURED`：

- `grasp_occlusion_window_s`
- `support_distance_m`
- `release_stable_s`
- `retreat_distance_m`
- `placement_stable_s`

它们只能由 Task 8P4 从五次 FULL 的原始 live evidence 生成新的 `QUALIFIED` report。

## 6. Phase-camera 覆盖规则

### 6.1 三种时间轴

覆盖分成三类，不能相互冒充：

1. **calibration replay coverage**：private MuJoCo 以绑定的 expert path、phase、anchor 和 2 ms grid 产生
   几何投影、segmentation、depth、pose/contact。下面九阶段矩阵在此时间轴验收 `TASK8_READY` 的 FOV/path
   可行性。每个 row 带 `replay_id/anchor/phase/path_row/physics_model_sha256`，不得声明为 live source。
2. **calibration live continuity**：首轮校准真实执行的 `CALIBRATION_STATIC`、`SEARCH`、
   `CONTROL_PROBE` 三个窗口中，head/wrist RGB 都必须按 10 Hz 连续，并与同一 live session/reset/attempt 的
   joint/TF/reference/physics receipt 因果配对。它只验证 source/sync/controller 链路，不伪造九阶段时间线。
3. **Task 8 live continuity**：真正的 SEARCH 到 FINAL_CHECK 九阶段 10 Hz 时间线由 Task 8 live evidence
   recorder 产生，并在 Task 8P4 生成 `QUALIFIED` 时按同一矩阵再次验收。没有这层 evidence 不能 QUALIFIED。

task camera 在 replay 和实际执行窗口都是 required audit source，但永远不是 ACT observation，也不参与
head-search lock。2 ms replay row、校准 10 Hz live sample 和 Task 8 live 10 Hz sample 使用不同 kind/schema；
aggregator 禁止跨 kind 拼接 source stamps 或 phase。

### 6.2 覆盖矩阵

| Phase | Head target coverage | Wrist target coverage | 说明 |
| --- | --- | --- | --- |
| `SEARCH` | `LOCK_WINDOW_REQUIRED` | `NOT_REQUIRED` | head 扫描过程中允许尚未发现目标；终止前必须有合格 lock 窗口。wrist 仍要求连续有效帧 |
| `APPROACH` | `VISIBLE_REQUIRED` | `VISIBLE_REQUIRED` | 两个相机都要看到杯体，作为 ACT 进入接近段的视觉条件 |
| `CLOSE` | `VISIBLE_REQUIRED` | `BOUNDED_GRIPPER_OCCLUSION` | wrist 可被夹爪/指尖局部遮挡；出画和非允许物体遮挡不算合法 occlusion |
| `MICRO_LIFT` | `VISIBLE_REQUIRED` | `BOUNDED_GRIPPER_OCCLUSION` | 与 CLOSE 相同 |
| `TRANSPORT` | `VISIBLE_REQUIRED` | `BOUNDED_GRIPPER_OCCLUSION` | wrist 可近距离局部遮挡，但杯体投影必须仍在画内 |
| `ALIGN` | `VISIBLE_REQUIRED` | `BOUNDED_GRIPPER_OCCLUSION` | 与 TRANSPORT 相同 |
| `RELEASE` | `VISIBLE_REQUIRED` | `BOUNDED_GRIPPER_OCCLUSION` | calibration 只做 plan/replay coverage；真实 occlusion 时长留到 Task 8P4 |
| `RADIAL_RETREAT` | `VISIBLE_REQUIRED` | `VISIBLE_REQUIRED` | 夹爪离开后恢复双视角可见 |
| `FINAL_CHECK` | `VISIBLE_REQUIRED` | `VISIBLE_REQUIRED` | 最终放置位置必须在两个 observation camera 的有效区域内 |

### 6.3 可见面积和遮挡公式

对每个 2 ms expert path grid row，MuJoCo 使用 640×480、相同 camera pose、near/far plane 和 projection
matrix 产生两份无抗锯齿审计图：

- normal-scene segmentation/depth；
- 保留杯体、相机和几何姿态但关闭其他可见 geom 的 isolated-cup segmentation。

聚合器从 raw mask 重算：

```text
projected_pixels      = isolated-cup viewport mask 的杯体像素数
visible_pixels        = normal-scene mask 中杯体像素数
full_projected_pixels = 杯体三角网格经 near-plane clipping 后，在不裁 viewport 的整数栅格中覆盖的像素数
in_frame_fraction     = projected_pixels / full_projected_pixels
visible_fraction      = visible_pixels / projected_pixels
bbox                  = visible mask 的最小轴对齐矩形
```

另用未裁剪的相机投影计算杯体投影包围多边形，并记录 `in_frame_fraction`。规则如下：

- 三角形先在 camera space 对 near plane 做 Sutherland-Hodgman clipping；完全在 far plane 外或 behind-camera
  的三角形不计，跨 near plane 的三角形使用裁剪后多边形。投影使用固定 top-left fill rule；分母为裁剪后、
  未裁 viewport 的像素并集，分子为同一栅格裁到 `[0,639]x[0,479]` 后的像素数。
- `full_projected_pixels==0`、`projected_pixels==0`、投影非有限或 `in_frame_fraction<0.98` 是 out-of-FOV，
  不能记作 occlusion。
- `VISIBLE_REQUIRED` 固定要求 `visible_fraction>=0.80`、`visible_pixels>=min_area_px2`、
  bbox aspect `>=min_bbox_aspect`，且 bbox center 位于闭矩形 `x=[4,635], y=[4,475]`。
- `BOUNDED_GRIPPER_OCCLUSION` 仍要求 `in_frame_fraction>=0.98`，visible fraction 允许降到 0。对 isolated
  mask 中每个在 normal scene 不再属于 cup 的像素，读取 normal geom segmentation 和 depth；只有当 normal
  depth 比 isolated cup depth 近至少 `1e-6 m`，且 owner geom 属于合同绑定的 `gripper`、moving/fixed finger
  或 fingertip-pad 集合时才算合法遮挡。背景、深度缺失、未知 geom、桌面或其他机器人 geom 一律 FAIL。
- calibration 阶段只验证允许发生 occlusion 的 phase 和遮挡来源，不提前生成
  `grasp_occlusion_window_s`。真实连续时长在 live 的 10 Hz 时间线中计算。
- 2 ms grid 用于路径几何覆盖；10 Hz RGB source stamps 用于 frame continuity 和训练观察频率。不能把 2 ms
  渲染行冒充 10 Hz 相机帧。

上述 `0.98/0.80/[4,635]x[4,475]/1e-6 m`、`min_area_px2`、`min_bbox_aspect` 和允许 occluder geom 集合
逐字写入 phase-camera matrix v1。bound contract 保存该文件 SHA256；实现不得从本次观测重新拟合这些值。
aggregator 不接受 raw 文件里的 `visible=true` 或 `occluded=true`。

允许 occluder 集合不使用运行时模糊字符串匹配。audit RGB/segmentation render 固定只启用 MuJoCo `group=0`
visual geom；collision geom 不参与像素 owner 判定。matrix 的生成器从受控 MuJoCo XML 中解析 `gripper` body
及其 `jaw` 后代，冻结当前参与渲染的完整名单：`gripper_visual_00`、`gripper_visual_01`、
`fixed_fingertip_pad_visual`、`jaw_visual_00`、`moving_fingertip_pad_visual`。生成时把按字节排序的完整 geom
名称数组写进 matrix；空集合、未命名 visual geom、名单项不在 `gripper` 后代、模型新增 `group=0` 的
gripper/jaw visual geom 而 matrix 未重生成，或 segmentation owner 落到 collision geom，都使 contract binding
或该 sample 失败。contact 判定另用 collision geom，不得把 collision 名称当成合法视觉遮挡 owner。

## 7. 首轮校准 admission 与 owner

### 7.1 Bootstrap deadlock 的处理

production Task 8 child 继续要求 `TASK8_READY`。首轮 measurement 不进入该入口，改走
`CalibrationMeasurementAdmission`：

```text
CALIBRATION_REQUIRED / 无 ready report
              |
              v
验证 source provenance + 五项 identity + bound contract
              |
              v
一次性 CalibrationMeasurementContext
purpose=task8_measurement, owner=calibration, generation=N
              |
              v
静态采集 -> plan/replay -> live search -> bounded control probe -> cleanup
              |
              v
sealed raw batch -> offline aggregate -> TASK8_READY
```

准入只接受 `CALIBRATION_REQUIRED` 或没有 ready report 的首轮状态；如果已经存在同 identity 的
`TASK8_READY/QUALIFIED`，必须显式选择新 measurement generation，不能覆盖旧结果。

### 7.2 权限边界

`owner=calibration` 是 broker 的独立 owner 类型，权限小于 `owner=act`：

- 可以执行 canonical reset、bounded neck search、hash-bound plan-only replay、固定的 non-contact controller probe、
  stop、revoke 和 cleanup。
- 不能创建 production Task 8 child，不能运行 `RELEASE`/`RADIAL_RETREAT` 的真实动作，不能打开夹爪释放杯子，
  不能启动 Recorder，也不能产出训练 episode。
- arm probe 使用合同内固定、无接触、可回到 canonical pose 的 trajectory。它只验证 controller
  submission/reference/feedback/stop 链路。完整 phase path 的 FOV、collision、velocity 和 acceleration
  覆盖由 private MuJoCo/PathProof replay 计算。
- `measurement_plan_sha256` 只绑定 canonical reset、private replay 和 non-contact arm probe。arm 命令必须与
  计划逐字一致；calibration owner 不接受其他 arm trajectory。
- neck search 不是固定 target 列表，而由 `calibration_search_policy_sha256` 绑定的状态机动态生成。
  `CalibrationSearchBinding` 从 admission context、candidate config、safe interval、detector identity 和当前
  controller generation 构造；它不读取未来的 calibration report，也不调用要求 `TASK8_READY` 的
  `validate_head_search_binding()`。
- broker 对每个 neck target 要求：由已绑定状态机在当前 event 序列唯一导出；current/target 均在候选 safe
  interval；`MujocoNeckSweepChecker` 对该 segment 独立通过；coarse/fine accumulator 和 target event 原子落盘。
  下一个候选 target 越过 safe interval 时，不提交命令，状态机以 `TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL` 终止。
- calibration owner acquire 时返回不可复用的 controller generation。每个 state、command、feedback、stop、
  cleanup event 都携带该 generation；漂移、旧 generation 迟到或第二个 flight 立即 revoke 并使 batch INVALID。
- 现有 production search binding 只接受 `owner=act`。实现必须新增 composition/adapter 处理
  `owner=calibration`，不能伪造 act owner，也不能放宽 production binding。
- 未知 phase、未知 operation、identity/generation 不匹配、或无法从两个受控 hash 推导的命令立即 revoke。

资源绑定只在 calibration 启动入口执行一次。driver 内部 camera、PathProof、broker、TF 和 evidence writer
消费已准入 context，不重新申请 campaign lease。若 GPU、CPU、RAM、磁盘、MuJoCo RTF、10 Hz continuity 或
CUDA 出现瓶颈，measurement 停止并封存 INVALID，等待人工决定；不降档。

### 7.3 固定执行顺序

每个 anchor 使用独立 `FULL_RESTART`，顺序固定为 default、left、forward：

1. 启动唯一 MuJoCo/ROS stack，验证 overlay、runtime role、CUDA/no CPU fallback 和冲突进程。
2. canonical reset，取得 paused/epoch/physics-step receipt。
3. 采集 camera geometry、CameraInfo、TF 和 source timing。
4. private MuJoCo 重放完整九 phase expert path，写 2 ms projection、contact、clearance 和 reference grid。
5. 在 live stack 中运行 head search，保存原始 RGB、detector candidate、neck command 和 feedback。
6. 运行固定 non-contact controller probe，保存 command/reference/feedback/submit/stop 证据。
7. generation-scoped、single-flight cleanup；确认 goal、owner、socket、process 和 controller group 清空。
8. 完全退出该 stack 后才进入下一个 anchor。

任何步骤失败都不继续下一个 anchor，也不尝试拼接旧 anchor 结果。

## 8. Aggregator 规则

aggregator 是纯离线函数。它不导入 rclpy、MuJoCo runtime、Torch 或 YOLO，也不启动进程。

固定处理顺序：

1. 验证 bound contract、identity 和 batch seal。
2. 比较实际文件集与 `batch.json.files`，拒绝未索引文件、少文件、hash 漂移和 symlink。
3. 验证三个 anchor 恰好各一个有效 run；session/reset/attempt 不得跨 anchor 混写。
4. 从 raw CameraInfo/TF/RGB/detection/command/reference/feedback/pose/contact/mask 重新计算摘要。
5. 按第 4、5、6 节公式生成两个 closed sample。
6. 调用 production `require_gate(report, "task8_live")` 和
   `validate_head_search_binding(runtime, report)` 做同进程 readback。
7. 同一 sealed batch 聚合两次，三个输出必须逐字节相同。

五项 pre-live check 的判据：

- `fov`：calibration replay matrix 所有 required row 通过；校准真实执行的三个窗口分别通过 head/wrist
  10 Hz continuity；camera 几何 7 项齐全。它不声称已获得九阶段 live continuity。
- `search`：21 字段完整，三个 anchor 各自至少 3 个连续合格 lock frame。
- `synchronization`：零缺样、零时间倒退、所有 age/skew 单点不越界。分位数只用于审计。
- `collision`：完整九 phase、三个 anchor、2 ms grid 的 PathProof、clearance、contact allowlist 全部通过；
  首次完整调用和随后 3 次完整调用都不超过冻结预算。
- `execution`：计划和 bounded live probe 的 reference、feedback、速度、加速度、submit lead、stop proof 与 cleanup 全部通过。

任一输入缺失为 `UNMEASURED`，任一有效越界为 `FAIL`，身份/时钟/封存/cleanup 污染为整个 batch
`INVALID`。只有五项全部 PASS，且 release/retreat 都是 `UNMEASURED`，才输出 `TASK8_READY`。

### 8.1 Task 8P4 的 5 个 live-only 字段

当前 `task8_live_qualification.py` 只复制 ready report并更新 status/checks，尚未产生以下五项 measurement；
因此即使 measurement driver 完成，也不能把现状声明为 `QUALIFIED`。Task 8P4 必须从五次互相独立的 FULL
run raw evidence 重算并生成新的 33-field report：

| 字段 | 单次 FULL 的固定公式 | 五次 FULL 的聚合与准入 |
| --- | --- | --- |
| `grasp_occlusion_window_s` | CLOSE 到 RELEASE 的 10 Hz live 时间线中，合法 gripper occlusion 的最长连续 source-stamp 区间；断帧、非允许 owner 或 phase 越界使该 run FAIL | 取五次最大值，必须 `<=` 配置上限 |
| `support_distance_m` | 同一 release epoch 中，首个 gripper-open command 前紧邻的 3 个连续 10 Hz live sample；每帧从 MuJoCo exact collision pair `bottom_collision`/`table_collision` 读取有符号最短距离 `d_signed`，reported sample=`max(0,d_signed)`，单次取三帧最大值；三帧还必须都有该 exact pair 的 active contact，且 cup linear/angular velocity 与 pose 稳定谓词通过 | 取五次最大值，必须 `<=` 配置上限；任一帧无真实 `bottom_collision`/`table_collision` contact 即 FAIL，距离通过不能替代支撑接触 |
| `release_stable_s` | RELEASE 后首次满足 cup pose/velocity/contact 稳定谓词起，到首次破坏或 phase 结束的最长连续 source-stamp 时长 | 取五次最小值，必须 `>=` 配置下限 |
| `retreat_distance_m` | RADIAL_RETREAT 中 gripper 相对已放置 cup 的径向位移，首次同时满足 clearance/contact/pose 稳定时的 readback 值 | 每次必须出现 qualifying readback；取五次最小值，必须 `>=` 配置下限 |
| `placement_stable_s` | FINAL_CHECK 中 pose、linear/angular velocity、table support 和 forbidden-contact 全部满足的最长连续 source-stamp 时长 | 取五次最小值，必须 `>=` 配置下限 |

稳定、支撑、速度、距离、occlusion owner 和缺帧阈值全部来自 bound live qualification contract，不提供 CLI
override。五项都写成现有 `value/unit/sample_path/sample_sha256` 形状；sample path 指向 sealed、indexed 的 live
qualification sample，不能指向摘要日志。Task 8P4 先生成 immutable 33-field report，再调用
`require_qualified(report)` 和 production readback；只有两者通过才可发布 `QUALIFIED`。五次 run 的 identity、
policy、source/config hash 或 phase-camera matrix 任一不同，不允许聚合。

## 9. 错误处理和状态恢复

- driver 不捕获并改写原始异常为 PASS/FAIL。CLI 记录失败码，执行 stop/cleanup，封存 `INVALID`。
- cleanup 必须沿用 generation-scoped、single-flight 状态机。旧 generation 的迟到回调不能清理新 generation。
- measurement 中断后先检查进程、日志、batch 文件集和 cleanup receipt，再决定是否重跑。poll 中断不算失败。
- `INVALID` batch、gen3 及失败 bundle 全部保留。未经用户授权不删除、不移动唯一 evidence root。
- controlled source、contract、runtime config、phase-camera matrix 或 policy 任一变化，都使旧
  measurement、bundle、LIVE 和 QUALIFIED 对新 identity 失效。

## 10. 实施和验证门

实施按以下最小边界推进：

1. schema/contract RED：21 字段公式、7 个 support 字段、phase-camera matrix、完整 identity 和文件闭包。
2. aggregator RED/GREEN：拒绝 label-only、`roots[0]` 偏差、未索引文件、混 identity、错 sample shape 和假 lock。
3. admission RED/GREEN：`CALIBRATION_REQUIRED` 可以创建 calibration context；production Task 8 child 仍拒绝；
   calibration owner 只接受 hash-bound arm plan 和 policy-bound bounded neck target，拒绝 release、Recorder、
   非计划 arm trajectory、safe-interval 外 target、generation 漂移和第二个 flight。
4. driver unit/component RED/GREEN：raw writer、三个 anchor、source stamps、projection、detector raw output、
   controller raw readback、INVALID seal 和 cleanup。
5. fixed raw fixture 两次聚合逐字节一致，并同时通过 `require_gate()` 与
   `validate_head_search_binding()`。
6. Task 8P4 producer RED/GREEN：五次 FULL raw evidence 生成 5 个 live-only measurement，输出 immutable
   33-field report，并通过 `require_qualified()`；缺一字段、混 identity 或伪造 summary 都拒绝。
7. 定向测试通过后，按计划的集成边界运行一次 ai-station full xdist/package gate。测试使用 evidence root
   下全新 NVMe scratch，并验证 `TMPDIR/TMP/TEMP`。
8. 代码、schema、合同和计划审查通过后，建立新 run subroot，从零生成 provenance、五项 identities 和
   bound contract；不得复制 gen3 输出。
9. 运行真实 MuJoCo measurement。资源瓶颈立即停止等待人工决定。
10. offline aggregate 得到新的 `TASK8_READY`，完成 readback 后继续 artifact preparation、九个 phase-prefix、
   五次 FULL_RESTART 和 live 后 `QUALIFIED`。

full test 只在上述明确集成边界运行，不在每个小修改后重复执行。

## 11. 完成条件

本补充设计的实现完成需要同时满足：

- 仓库中存在生产 driver，不再由测试临时创建 `driver.py`；
- 21 个字段和 7 个 support 字段都能追溯到 indexed raw evidence、公式和冻结来源；
- phase-camera matrix 对九个 phase、head/wrist 两个 observation camera 没有缺项；
- raw label 被篡改不会改变聚合结论，raw 数值或 mask 被篡改会被 hash/重算发现；
- 首轮 calibration 不需要伪造 `TASK8_READY`，且权限小于 production Task 8；
- 新 `TASK8_READY` 同时通过 production gate 和 head-search binding；
- Task 8L 从新 run subroot 重做，gen3 保留但不被消费；
- 没有 Gazebo、CPU fallback、W4/W6、阈值降档、真实硬件动作、证据删除或 push。

设计审查通过只授权实施和重新运行 Task 8L，不表示 Task 8 live、正式采集或训练已经完成。
