# SO-101 Head Search YOLO 校准与 Teleop 诊断设计

**日期：** 2026-09-30
**状态：** 设计讨论已确认，等待独立 GPT-6 Astra/High 复审
**适用范围：** MuJoCo-only；不涉及真实 SO-101 运动

## 1. 背景

当前 Task 8 的 Head Search 还不能进入资格运行。`task8-calibration-search-candidate-v1.json` 中的 17 项搜索参数仍为空，生产路径也缺少合法的 `head_search_qualification` 产物。现有动态相机取证还发现，按已准入轨迹渲染时，杯子在 head camera 中持续 `in_frame=0`。在这个问题解决之前，继续推进后续 Task 8 只会把错误带到下游。

已有 YOLO11n-Seg 权重来自 [zjumty/so101-yolo11n-seg-plastic-cup](https://huggingface.co/zjumty/so101-yolo11n-seg-plastic-cup)，训练数据使用 `task_camera`。这组权重可以作为基线，但它在 task-camera test 上的结果不能证明 head camera 可用。Head Search 需要自己的数据、模型比较、参数校准和闭环证据。

本设计把 Head Search 作为独立门禁。模型、17 项参数、Teleop 诊断和运行验收全部完成后，才恢复其他 Task 8 工作。

## 2. 已确定的边界

本任务遵守以下决定：

- Head Search 不使用 Grounded-SAM。数据标签直接来自 MuJoCo 实例真值，运行时只使用 YOLO-Seg。
- 新建 head-camera 数据集，数量与现有 task-camera 数据一致：800 train、200 val、200 test。
- 比较三个模型：现有 task-camera 模型 A、head-only 微调模型 B、head/task 混合微调模型 C。
- C 使用两套完整数据的并集，不下采样：1600 train、400 val，batch 内按 camera domain 1:1 采样。
- 如果 C 与 head-camera 最佳模型在预先声明的等效区间内，并且 task-camera 能力没有越过退化门槛，选择 C，让一个权重服务两个 camera domain。
- 先冻结模型，再发布完整的 17 项参数 bundle。
- 校准必须由仓库内正式安装的程序完成。禁止用 agent 临时脚本生成最终参数。
- 校准程序不支持 resume。失败 run 永远不能续跑，修复后必须用新 run ID 从头运行。
- 数据生成、模型评测、校准、40 场景和资格验证均为单 stack 串行执行。本任务不实现 W2/W4/W6/W8 或其他多 worker 支持。
- Teleop 增加 Head Camera 页面，用于受控转头、查看画面、检查 YOLO-Seg overlay 和保存证据。
- Teleop 只旁路读取生产感知链，不能启动第二个 detector，也不能绕过 broker 直接控制 neck。

## 3. 总体流程

流程按以下顺序执行：

```text
生产相机契约冻结
  -> 安全 neck 区间测量
  -> head-camera 数据生成与封存
  -> A/B/C 训练和离线评测
  -> 最终权重冻结
  -> 17 项参数校准
  -> 参数 bundle 晋级与核对
  -> 单 stack 串行闭环资格验证
  -> Head Search QUALIFIED
```

前一阶段没有形成可回读的成功产物时，下一阶段必须拒绝启动。任何受控输入发生变化，所有下游结果随之失效。

生产数据流只有一条：

```text
MuJoCo head camera
  -> frame envelope
  -> CUDA YOLO-Seg
  -> mask / bbox / confidence
  -> tracker
  -> HeadSearchController
  -> broker-owned neck command
  -> controller feedback
```

Teleop 订阅同一个 frame envelope 和检测结果。它不是第二套 Head Search 实现。

## 4. 生产相机契约

采集数据前先冻结以下内容：

- MuJoCo camera 名称和 MJCF 来源；
- 640×480 分辨率；
- CameraInfo、畸变参数和 optical-to-base 变换；
- ROS frame ID、sim time 和 receive monotonic time；
- 10 Hz 生产帧率；
- cup、target 和 occluder 的生产几何；
- head camera 与 neck joint 的实际绑定关系。

当前 `in_frame=0` 必须在这一阶段解决。修复后的视图需要覆盖合法 neck 区间、三个 anchor 和后续 40 场景。为生成数据而单独设置一个更容易看到杯子的相机不算通过。

`horizontal_fov_rad` 和 `lock_valid_neck_rad` 是模型无关的几何事实，可以在模型选择前测量。它们会作为数据生成的安全输入，但 17 项参数仍然在模型冻结后一起发布。

## 5. Head-camera 数据集

### 5.1 数量和场景

| Split | 图片数 | 每个场景的数量 |
| --- | ---: | ---: |
| train | 800 | 200 |
| val | 200 | 50 |
| test | 200 | 50 |

四类场景与现有 task-camera 数据保持一致：

- `no_cup`
- `one_cup_distractors`
- `two_cups`
- `cup_near_bottle`

每个 split 还要覆盖 cup 相对光轴的水平位置、合法 neck yaw、垂直位置、距离、投影面积、部分遮挡、画面边缘、材质、光照和背景变化。

### 5.2 划分和真值

数据生成使用生产 head camera 和 MuJoCo 实例真值。Grounded-SAM 不参与生成标签、补标、筛选或复核。

划分单位是跨 camera domain 统一的 `scene_group_id`，不能只看单张图片或局部 seed。属于同一 MuJoCo 世界状态的 head-camera、task-camera 和相邻帧必须进入同一个 split，以免同一场景从一个 camera domain 泄漏到另一个 domain 的 val/test。train、val、test 的 `scene_group_id` 和 seed 清单在采集前冻结，并写入 dataset manifest；校验器发现任一 group 跨 split 时直接拒绝数据集。

1200 张图片用于模型训练与离线评测。tracker、frame freshness 和闭环搜索另设互不重叠的 `calibration episodes`、`held-out evaluation episodes` 和最终 40 个 `qualification scenarios`。三组的 seed 清单在任何参数搜索前冻结；qualification seed 不参与参数选择。连续 episode 不计入 1200 张图片，也不混入静态图像指标。

### 5.3 数据产物

现有 `generate_yolo_seg_dataset` 扩展 head-camera 正式配置。产物至少包含：

- RGB 图片；
- YOLO-Seg label；
- 原始实例 mask；
- CameraInfo 和相机位姿；
- scene seed、场景类型和 neck yaw；
- split manifest、文件 SHA256 和生成程序身份。

## 6. 模型训练与比较

### 6.1 候选模型

| 模型 | 初始化 | 训练数据 | 用途 |
| --- | --- | --- | --- |
| A | 当前 task-camera 权重 | 不训练 | 基线 |
| B | A | head train 800 | head 专用候选 |
| C | A | head 800 + task 800 | 两个 camera domain 的共享候选 |

B 和 C 使用相同的 YOLO11n-Seg 架构、输入尺寸、optimizer、augmentation、batch size、随机种子、最大 epoch、checkpoint 策略和 early-stop 规则。C 每个 epoch 都完整看到 800 张 head 和 800 张 task 图片，batch 内保持 1:1 domain 比例。两者的 head 数据暴露次数相同；C 多出的计算用于保留 task-camera 能力。

B 和 C 都使用 head val 与 task val 的组合评分选择 checkpoint。随后，每个候选分别在 val 图片和 `calibration episodes` 上确定 head/task domain 的感知 operating point，形成不可拆分的候选身份：权重 SHA256、confidence、area、aspect、tracking 参数、后处理版本和 tracker 版本。test 与 `held-out evaluation episodes` 在候选身份冻结前保持 sealed。

### 6.2 两道离线门禁

“Benchmark gate”在本文中拆成两个明确名称。

`perception benchmark implementation gate` 验证评测程序本身，包括 mask/bbox 匹配、AP、precision、recall、F1、paired bootstrap、dataset seal、报告和 CLI。它不能证明模型质量。

`A/B/C frozen-model evaluation gate` 才运行真实权重和数据：

```text
A / B / C x head-camera test
A / B / C x task-camera test
```

两道门禁都串行运行。模型推理必须使用 CUDA，不允许 CPU fallback。

### 6.3 指标

Head-camera 的静态图像主指标包括：

- cup-present recall；
- `no_cup` false-positive rate；
- `two_cups` 两个实例同时检出的比例；
- bbox center error 的 median 和 p95；
- box/mask AP50、AP50-95；
- CUDA inference latency p50、p95、p99。

连续指标在 `held-out evaluation episodes` 上单独计算，包括 tracking continuity、identity switch、fragmentation、错误候选、错误锁定、重新获取和端到端时延。静态图像和连续 episode 的统计单位不能混用。

Task-camera 保留指标包括 box/mask AP50-95、precision、recall、F1、`no_cup` false-positive rate 和 `two_cups` both-cup recall。

### 6.4 等效判定和模型选择

差异不显著不能简化为 `p > 0.05`。评测使用固定 seed、至少 10,000 次按独立 `scene_group_id` 分层的 paired bootstrap，检查 95% CI 是否落在预先声明的等效区间内。只有 dataset manifest 能证明每个 scene 仅有一张测试图时，才允许退化为 image-level bootstrap；连续指标以 episode 为统计单位：

- recall、F1、AP 的绝对差不超过 0.01；
- bbox center p95 不比最佳候选差超过 2 px；
- C 相对 A 的 task-camera mask AP50-95 和 recall 下降不超过 0.01；
- `no_cup` 错误候选和最终错误锁定必须为零；
- 推理延迟满足 `p95_inference <= 100 ms - p95_non_inference - 10 ms guard`。

选择顺序如下：

1. 出现错误锁定、CPU fallback、身份不完整或时延超限的候选直接淘汰。
2. 在剩余候选中确定与 head-camera 最佳候选等效的集合。
3. 如果 C 位于该等效集合内，同时通过 task-camera 保留门禁，选择 C；A、B、C 全部等效时也适用这一条。
4. 如果 C 不满足共享模型条件，而 B 明显优于 A/C，Head Search 使用 B，task-camera 继续使用 A。
5. 如果 C 不满足共享模型条件且 A 与 head-camera 最佳候选等效，两个入口保留 A。

共享的是权重，不强制两个 camera domain 使用同一个 confidence threshold。每个 domain 可以保留各自在 val 上锁定的 operating point。

`A/B/C frozen-model evaluation gate` 评测的是上面冻结的“权重 + operating point + tracker”整体，而不是裸权重。打开 test 后不得重新优化任何感知参数。最终正式校准只能逐字段纳入并验证获选候选的已冻结感知值；如果验证失败或任何值需要改变，旧 verdict 立即失效，必须用 val 重新形成候选身份，并用一套此前从未打开的新 test/held-out episode seeds 重新完成比较。

## 7. 17 项参数校准

### 7.1 参数及算法

| 参数 | 校准方法和失败条件 |
| --- | --- |
| `horizontal_fov_rad` | 从生产 CameraInfo 计算左右视场角，取有效帧的保守最小值；必须与 MuJoCo camera 定义在容差内一致。 |
| `lock_valid_neck_rad` | 在 `[-2*pi, 2*pi]` 上以 0.002 rad 闭网格检查三个 anchor 的碰撞和净空，状态边界二分至 1e-5 rad；取唯一一个同时包含零位和三个起始角的安全连通区间，端点向内缩 1e-5 rad。另行把合法拾取工作区投影成 `required_search_domain_rad`；该受控依赖不是第 18 个调参项。若安全区间与相机视场不能覆盖整个 required domain，校准直接失败。 |
| `coarse_step_rad` | 在 `<= horizontal_fov_rad / 2` 的候选中，选择通过有界双向扫描覆盖整个 `required_search_domain_rad`、val 中零漏扫且锁定时间最短的最大步长。禁止用固定正向累计 `2*pi` 代替覆盖证明。 |
| `search_timeout_s` | 按有界扫描轨迹的最大稳定停点数、每步 p99 settle/frame 时间、最大精调次数和一个完整控制周期 guard 计算。 |
| `min_confidence` | 与面积、aspect、tracking 条件在 head val 上联合搜索；要求 `no_cup` 零候选、双杯都被检出，并在约束下最大化 recall/F1。 |
| `tracking_iou` | 用连续 episode 中同一杯子的正样本对和不同杯子的负样本对选择分界；要求零 identity switch，并限制 fragmentation。找不到安全分界时淘汰 tracker/model。 |
| `min_bbox_aspect` | 用 cup 真值 bbox 与干扰物/误检分布选择；保留所有 required-visible val cup，同时拒绝对应假候选。 |
| `min_area_px2` | 根据生产分辨率下 required-visible cup 的最小投影面积确定。小目标误检不能靠继续放宽阈值解决。 |
| `center_deadband_px` | 从中心抖动和相机角分辨率计算起始值，选择能连续三帧稳定锁定且不左右振荡的最小值。 |
| `vertical_bounds_px` | 将合法拾取工作区投影到 head camera，再与图像安全边缘相交；禁止从检测结果极值回填。 |
| `max_fine_corrections` | 取 val 成功 episode 所需最大次数，再增加一次恢复余量；增加后仍需保持在合法 neck 区间。 |
| `max_fine_total_rad` | 取成功 episode 的最大累计精调量，加一个已观测最大单次精调余量；不能越过安全区间。 |
| `max_age_s` | 取端到端 frame age 的 p99.9 加 10 ms；上限是 1.5 个 10 Hz frame period。超限时修流水线，不提高阈值。 |
| `max_skew_s` | 取 image、CameraInfo、joint/TF 的 p99.9 skew 加一个时钟分辨率；上限是半个 frame period。 |
| `submit_lead_s` | controller goal-admission 的最小 lead 加一个 MuJoCo simulation timestep；全部提交使用 sim time 验证。 |
| `stop_velocity_rad_s` | 由静止状态 p99.9 速度噪声、反馈量化分辨率和 controller stopped tolerance 得到保守包络。 |
| `stop_latency_s` | 测量 stop/revoke 到第三个连续合格反馈的延迟，取 p99.9 加一个 feedback period；test 中任一次超限都失败。 |

### 7.2 依赖顺序

```text
相机和安全几何
  -> 每个候选的感知 operating point 校准与冻结
  -> 冻结候选评测与模型选择
  -> 获选感知参数原样纳入并验证
  -> 搜索和精调参数
  -> freshness、提交和停车参数
  -> 完整 bundle
```

`min_confidence`、`tracking_iou`、`min_bbox_aspect`、`min_area_px2` 在每个候选的 val 和 `calibration episodes` 上联合搜索，避免参数顺序影响结果。候选评测后不得再次优化这四项。`center_deadband_px`、精调次数和累计精调角使用连续 calibration episode 校准，并用互斥的 held-out episode 验证。

粗扫轨迹是按 anchor 生成的确定性、有界停点序列。它从 anchor 先到较近的 required-domain 端点，再反向扫描至另一端；每个相邻目标都必须位于 `lock_valid_neck_rad` 内，并由独立 sweep checker 证明整段安全。覆盖完成以稳定停点的相机水平视场并集完整覆盖 `required_search_domain_rad` 为准，不以累计角度等于 `2*pi` 为准。只有覆盖完成且仍无合法候选时才返回 `TARGET_NOT_FOUND`；到达安全边界但覆盖不完整时返回 `TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL`，资格验证判失败。

每项参数必须记录数值、单位、选择公式、输入证据和 SHA256、observed distribution、安全余量、production owner、启动 readback 以及运行时有效值。如果一个参数只出现在配置文件里，没有被 production component 实际读取并影响决策，整个 bundle 失败。

`settle_velocity_rad_s`、`goal_tolerance_rad`、连续三帧锁定规则、tracker 算法和 10 Hz frame contract 虽不属于这 17 项，也要作为受控依赖写入 manifest。

## 8. 正式校准程序

### 8.1 安装入口

新增正式入口：

```text
so101_head_search_calibration run
so101_head_search_calibration verify-promoted-config
so101_head_search_calibration qualify
```

现有 `generate_yolo_seg_dataset` 负责数据生成，`train_yolo_seg` 负责 B/C 训练。新程序消费 sealed dataset、冻结的候选 operating point 和不可变候选权重，完成真实评测、模型选择、17 项参数校准和 bundle 生成。

数学与策略代码放在可独立测试的库模块中。CLI 只解析参数、验证输入和编排阶段。

### 8.2 一次性运行

`run` 的阶段固定：

```text
输入验证
  -> 几何测量与 required search domain 覆盖证明
  -> 各候选感知 operating point 的 val 校准与冻结
  -> 冻结候选评测与选择
  -> 获选感知参数原样验证
  -> 搜索参数校准
  -> 时序和停车参数校准
  -> bundle 生成
```

程序没有 `--resume`，也不提供中间阶段继续执行的入口。`run-status.json` 只用于审计，不是 checkpoint。

结果只能是 `SUCCEEDED` 或 `FAILED`。失败时记录首次失败阶段、失败码、命令、退出码和已经生成的证据，并立即停止。失败 run 不得被修改、续跑或晋级。修复后使用同一登记 evidence root 下的新 run ID，从输入验证开始重跑。

数据集和权重如果已经 sealed 且 digest 没变，可以继续作为新 run 的只读输入；没有必要重新生成相同数据或重新训练相同权重。

首次校准不能调用要求既有 `TASK8_READY/QUALIFIED` 的生产 Head Search 入口，否则会形成先有资格才能校准的死锁。`run` 和首次 `qualify` 必须复用现有 `CalibrationMeasurementAdmission` 与 `CalibrationSearchBinding`：只允许 `role=calibration` 的单次 measurement flight，release 和 recorder 永远拒绝；所有 neck target 绑定同一 generation、measurement plan、safe interval 和独立 sweep-check receipt。资源只在 CLI 入口绑定一次，内部阶段不得重绑。当前正向累计 `2*pi` 的生产 controller 不满足本文轨迹契约，必须在 RED/GREEN 中改成前述有界停点序列后才能用于正式资格验证。

### 8.3 输出和晋级

运行必须显式提供 evidence root、生产配置、相机配置、dataset manifest、model manifest 和 runtime identity。输出包括：

```text
manifest.json
run-status.json
geometry-measurements.json
dataset-provenance.json
model-comparison.json
model-selection-verdict.json
perception-calibration.json
search-calibration.json
timing-calibration.json
head-search-calibration-bundle.json
logs/
artifacts/
scratch/
```

`run` 只在 evidence root 内生成候选 bundle，不直接修改 tracked config。批准后的值写入仓库配置后，`verify-promoted-config` 逐字段核对 17 项值、单位、模型 SHA、camera、dataset、tracker、runtime identity 和批准记录。存在任何差异时拒绝 `qualify`。

`qualify` 输出两份不可混淆的 head-only 产物：

- `head-search-qualification.json` 复用现有闭合 sample schema，必须包含同一个 PASS sample 中的 17 项 `_MEASURED`、四项 `_CAMERA_MEASURED`、`observed_lock_frames`、完整 runtime descriptor、source commit、config SHA256 和 provenance SHA256；
- `head-search-qualified-report.json` 只声明 `status=HEAD_SEARCH_QUALIFIED`，逐字段引用上面的 sample，并绑定获选模型、camera、motion 和 bundle identity。

`validate_head_search_binding()` 扩展为接受这一种严格闭合的 head-only report，同时继续接受现有 `TASK8_READY/QUALIFIED` report；两条路径都调用同一个 shape、sample digest 和数值校验。`HEAD_SEARCH_QUALIFIED` 只允许 Head Search 和 Teleop Head Camera consumer 使用，不能被 `task8_live`、release、retreat、动态拾取或整个 Task 8 的 readiness gate 接受。后续 Task 8 聚合器可以引用同一不可变 sample，但必须独立补齐 support 字段并重新形成 `TASK8_READY/QUALIFIED`，不得由本程序自动晋级。

## 9. Teleop Head Camera

### 9.1 页面

Teleop 新增 `Head Camera` 页签。左侧显示固定 4:3 画面，支持 Raw 和 YOLO-Seg Overlay 切换。Overlay 包含 mask、bbox、类别、confidence、track ID、相机光轴、horizontal deadband、vertical bounds、当前候选中心和三帧 lock 进度。

右侧显示当前 neck angle、velocity、target、安全区间、控制 owner、lease、operation 状态、model ID、weights SHA256、parameter bundle SHA256、CUDA device、FPS、推理延迟、frame age、source skew 和显示丢帧数。

转头采用有界位置目标，不提供 velocity jog。控件包括绝对角度输入、滑杆、`-5°`、`-1°`、`+1°`、`+5°`、Execute 和 Stop。页面不允许在线修改 calibration threshold。

### 9.2 视频协议

WebSocket 发送原子 frame envelope：

```text
frame_sequence
image/jpeg
image_sha256
camera frame/stamp
receive monotonic time
CameraInfo identity
model identity
detections[]
inference latency
search projection
```

JPEG 和检测结果属于同一条消息，前端按结构化结果绘制 overlay。显示端使用 latest-frame 语义；浏览器处理不过来时丢弃旧显示帧，不能让 Teleop 对生产 detector 或 10 Hz Head Search 形成 backpressure。

候选模型不能在页面热切换。A/B/C 比较时，每次 `FULL_RESTART` 只启动一个模型，页面显示实际模型身份。

### 9.3 API 和控制所有权

正式接口为：

```text
GET  /teleop/head-camera/status
WS   /teleop/head-camera/stream
POST /teleop/head-camera/target
POST /teleop/head-camera/stop
POST /teleop/head-camera/capture
```

`target` 请求包含绝对 target、command ID、simulation session、execution generation 和 bundle SHA。执行前检查 MuJoCo-only、有效 Teleop lease、instance authority、global mutation arbiter、自动 Head Search/ACT owner、feedback freshness、bundle 身份和 neck 安全区间。

浏览器请求通过 unified Teleop admission 进入受控 child，再交给 broker-owned neck trajectory。浏览器不能直接发布 ROS topic 或 action。

控制状态为：

```text
VIEW_ONLY
  -> LEASED_IDLE
  -> MANUAL_HEAD_ACTIVE
  -> STOPPING
  -> LEASED_IDLE
```

自动 Head Search、ACT、session 变化、lease 失效、stale input 或参数身份变化都会禁用运动控件。`lock_valid_neck_rad` 未获批时，页面只能看画面。

Stop 走 safety lane。UI 要区分 stop request accepted、controller goal revoked、原始反馈确认停车三个状态；第三个连续合格反馈出现之前不能显示 `Stopped`。

### 9.4 证据捕获

`capture` 按 frame sequence 从服务端短期 ring buffer 取同一帧，并原子保存：

```text
head-camera-raw.jpg
head-camera-overlay.png
head-camera-detections.json
head-camera-runtime.json
capture-manifest.json
```

frame 已过期或身份不一致时直接拒绝，不能换成更新的一帧。manifest 记录图像、模型、参数、相机和运行身份的 SHA256。

## 10. 测试与资格验证

### 10.1 测试阶梯

执行顺序如下：

```text
定向 RED/GREEN
  -> perception benchmark implementation gate
  -> A/B/C frozen-model evaluation gate
  -> 包级测试
  -> 单 stack production smoke
  -> 单 stack 串行 40 场景
  -> 三个 anchor 各一次独立 FULL_RESTART
```

普通 package gate 仍按仓库规则使用 `pytest-xdist`。这是测试运行器要求，不表示校准程序支持并行执行。ai-station 上所有 fsync-heavy pytest/colcon 都使用登记 evidence root 下全新的 NVMe scratch，并在启动前验证 `TMPDIR`、`TMP`、`TEMP` 和 `tempfile.gettempdir()`。

### 10.2 40 场景

40 个场景使用十类条件，每类四个独立 seed，并在三个 anchor 间均衡分布。这些 qualification seed 在校准前封存，与图像 train/val/test、连续 calibration episodes 和 held-out evaluation episodes 都不重叠：

1. cup 位于左侧搜索边缘；
2. cup 接近相机中心；
3. cup 位于右侧搜索边缘；
4. cup 接近 vertical upper bound；
5. cup 接近 vertical lower bound；
6. 部分遮挡；
7. cup 靠近 bottle；
8. 两个 cup；
9. 无 cup；
10. 临时 frame/detection 中断后重新获取。

场景逐个运行。前一场景完成停车、证据落盘和状态清理后，下一场景才能启动。单杯合法场景必须锁定正确杯子；双杯返回 `TARGET_AMBIGUOUS`；无杯只有在视场覆盖证明完成后才返回 `TARGET_NOT_FOUND`；安全边界先到、stale、时间倒退或身份变化必须停车并 fail-closed。中断场景收到故障后终止旧 attempt，清空旧 track 和 lock count，再以新的 attempt ID 启动重新获取。

40 场景之后，`default`、`left`、`forward` 各运行一次独立 `FULL_RESTART`。三次都要通过构图、检测、搜索、锁定、时序和停车门禁，不设置连续成功计数。

### 10.3 闭环门禁

所有场景共同满足：

- 零错误锁定、零越界 neck command；
- inference、frame age 和 source skew 均在冻结阈值内；
- 生产 10 Hz 帧序列无重复、倒退或未声明缺口；
- coarse/fine 次数和累计角度不超限；
- stop/revoke 后有三个连续原始反馈证明停车；
- 全程 CUDA，无 CPU fallback；
- runtime effective config 与批准 bundle 完全一致；
- producer、journal、aggregator 和最终报告可以从证据中回读。

结果类别门禁分别是：

- 合法单杯：正确 cup 的中心连续三帧位于 deadband 和 vertical bounds 内，最终状态为 `LOCKED`；
- 双杯：最终状态为 `TARGET_AMBIGUOUS`，全程零错误锁定，并有停车证据；
- 无杯：完整覆盖 required search domain 后返回 `TARGET_NOT_FOUND`，全程零错误候选/错误锁定，并有停车证据；
- frame/detection 中断：旧 attempt fail-closed 并停车，新 attempt 使用空 tracker/lock state 重新获取，不能把旧帧计入三帧锁定。

### 10.4 Teleop 验收

自动测试覆盖 frame correlation、overlay 坐标、display backpressure、lease/session 失效、越界 target、owner 冲突、停车状态和 capture manifest。

可视验收使用真实浏览器和本轮新截图，检查 Raw/Overlay、mask/bbox/中心线、light/dark theme、桌面与窄屏布局，以及 active、conflict、stale、stopping、stopped 状态。截图不能代替 API 和原始运行证据。

## 11. 失败、失效与证据

以下任一变化都会使旧 bundle、live evidence 和 `QUALIFIED` 状态失效：

- 模型权重或 model ID；
- camera、MJCF、target/occluder 几何；
- tracker 或 detector 后处理；
- 17 项参数；
- `settle_velocity_rad_s`、`goal_tolerance_rad`、三帧规则或 10 Hz contract；
- broker/controller、source/config/policy；
- CUDA、PyTorch 或 Ultralytics runtime identity。

失效后使用同一登记 evidence root 下的新 run ID 从头执行。旧 run 保留为 auditable evidence，分类为 retained、invalid/archived 或 deletion candidate；没有用户明确授权不得删除。

本任务沿用已经登记的唯一 evidence root：

```text
/data/work/so101-evidence/act-data/20260924-fbc25063-resume
```

普通低速诊断日志可以写入唯一的 `/tmp/so101-debug-<task-id>/`，但最终数据、模型、校准、截图和 qualification evidence 都留在登记 root 内。

## 12. 完成条件

满足以下条件后，Head Search 才能标记为完成：

- A/B/C verdict 已冻结；
- 最终权重、来源、revision 和 SHA256 写入英文 README；
- 17 项参数都有测量来源、production consumption 和 runtime readback；
- `so101_head_search_calibration` 作为正式安装产物通过测试；
- Teleop Head Camera 的控制、画面、YOLO-Seg overlay 和证据捕获通过；
- 串行 40 场景和三个 anchor 的独立 `FULL_RESTART` 全部通过；
- 独立 GPT-6 Astra/High 复审设计、执行计划和最终结果；
- 账本记录 retained runs、failed/invalid runs 和 deletion candidates；
- 没有删除证据、push、触及真实 SO-101 或遗留第二套 stack。

上述条件没有全部满足时，其他 Task 8 工作继续保持暂停。
