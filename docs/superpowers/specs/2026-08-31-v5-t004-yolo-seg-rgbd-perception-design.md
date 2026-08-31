# V5-T004 YOLO-Seg RGB-D 多实例感知设计

**日期：** 2026-08-31

**任务：** `V5-T004`

**代码范围：** `src/so101_demo_py`

**运行平台：** macOS Apple Silicon 与 ai-station NVIDIA GPU

## 1. 目标

当前 `rgbd_cup_pose` 使用橙色阈值和最大 DBSCAN 聚类定位杯子。它能处理受控的单杯场景，但不能区分同色杯子和瓶子，也不能在多个实例之间按 `TaskCommand.target_object` 选择目标。

本任务新增一条 YOLO-Seg RGB-D 感知路径：

```text
task_camera RGB
  -> YOLO-Seg 实例分割
  -> DetectionCandidate[]
  -> 按 plastic_cup 选择实例
  -> selected mask + aligned Depth + CameraInfo
  -> 实例点云与几何验证
  -> exact-stamp tf2
  -> /cup_pose
```

V5-T004 的验收终点是：在 MuJoCo 多物体场景中，从真实 `/task_camera` 输出识别目标杯子，并留下检测结果、分割画面和 3D 定位证据。

## 2. 不在本任务内的内容

以下工作留给 `V5-T005`：

- TextAgent 触发感知请求；
- 文本指令到抓取状态机的完整编排；
- MoveIt 规划与 controller 执行；
- MuJoCo 抓取、搬运和放置；
- 1 至 2 分钟完整演示视频。

本任务不修改 TextAgent 的执行授权，也不把检测成功解释为抓取成功。现有 `TaskDispatcher` 仍拒绝未被消费的 constraints。出现两个 `plastic_cup` 时必须返回歧义错误，不能擅自选择最近、最大或置信度最高的实例。

## 3. 方案选择

### 3.1 检测模型

第一版使用微调后的 YOLO-Seg。基础模型选用 `yolo11n-seg.pt`，原因是模型较小，适合 macOS MPS 的单帧推理，也能在 ai-station 上使用 CUDA 训练和推理。

训练产物是单一 `best.pt`。两个平台必须使用相同文件并核对 SHA256：

```text
best.pt
├── ai-station -> CUDA
└── macOS     -> MPS
```

只有 macOS 实测无法满足请求延迟时，才增加 ONNX 或 Core ML adapter。首版不同时维护 `.pt`、TensorRT engine 和 Core ML 三套产物。

### 3.2 实例分割而不是 3D 最大聚类

DBSCAN 根据点间距离聚类。杯子和瓶子靠得太近时，它们可能成为同一个点云簇。YOLO-Seg 先在 RGB 图像中产生实例 mask，再用每个 mask 提取 Depth，因此相邻物体仍可分别进入 3D 定位。

DBSCAN 可以保留在选中 mask 内做离群点清理，但不能再负责跨物体选择，也不能以最大聚类代替类别判断。

### 3.3 模拟器真值的使用范围

MuJoCo object-ID segmentation 只用于生成训练标签和验收对照。生产 `YoloSegDetector` 只能读取 RGB 图像；`RgbdLocalizer` 只能读取被选中 mask、Depth 和 CameraInfo。任何生产路径都不能读取 MuJoCo object ID、物体名称或 truth pose 来生成检测结果。

## 4. 组件边界

### 4.1 数据流

```text
AlignedRgbdBuffer
        │
        ├── RGB ─────────────────────────────┐
        │                                    ▼
        │                         DetectorPort.detect()
        │                                    │
        │                         DetectionCandidate[]
        │                                    │
        │                         TargetSelector.select()
        │                                    │
        └── Depth + CameraInfo ───────────────┤
                                             ▼
                                      RgbdLocalizer
                                             │
                                      LocalizedObject
                                             │
                                      exact-stamp tf2
                                             │
                                          /cup_pose
```

现有 `AlignedRgbdBuffer`、RGB/Depth 解码、Depth 反投影、杯子半径拟合和 exact-stamp tf2 继续复用。需要替换的是 `orange_cup_mask -> largest_cluster_indices` 这一段。

### 4.2 `DetectorPort`

端口定义保持模型无关：

```python
class DetectorPort(Protocol):
    def detect(
        self,
        frame: DetectionFrame,
        query: DetectionQuery,
    ) -> DetectionBatch: ...
```

`DetectorPort` 只负责 RGB 实例分割：

- 不读取 Depth；
- 不计算 3D pose；
- 不发布 `/cup_pose`；
- 不决定是否允许抓取；
- 不接收 TextAgent 原始文本。

`DetectionQuery` 只包含白名单中的规范类别，例如 `plastic_cup`。未来 `GroundedSamDetector` 通过受控配置把规范类别映射为模型 prompt，不能直接使用未校验的自然语言。

### 4.3 `DetectionCandidate`

候选结构至少包含：

```text
instance_id
class_id
confidence
bbox_xyxy
mask
source_stamp_ns
source_frame_id
```

约束如下：

- `instance_id` 在同一 `DetectionBatch` 内唯一；
- `class_id` 使用规范名称 `plastic_cup`，不向下游泄漏 YOLO 数字索引；
- `confidence` 是有限的 `[0, 1]` 浮点数；
- `bbox_xyxy` 位于原图边界内，且面积大于零；
- `mask` 是与原始 RGB 相同宽高的布尔数组；
- 时间戳非零，frame ID 非空。

### 4.4 `DetectionBatch`

批次保存运行和模型 provenance：

```text
model_id
weights_sha256
runtime_device
inference_latency_ms
image_width
image_height
candidates
```

`runtime_device` 只能是实际使用的 `cuda`、`mps` 或 `cpu`，不能记录请求值后忽略真实回退。

### 4.5 `YoloSegDetector`

`YoloSegDetector` 是第一版 adapter。它负责：

1. 延迟导入 `torch` 和 `ultralytics`；
2. 加载并 warm-up `best.pt`；
3. 选择已授权 device；
4. 执行单帧实例分割；
5. 将 Ultralytics boxes、classes、confidence 和 masks 转成 `DetectionBatch`。

普通单元测试通过 fake detector 运行，不要求 Torch、GPU 或模型文件。真实 adapter 测试使用单独的 runtime marker。

未来 adapter 保持同一端口：

```text
DetectorPort
├── YoloSegDetector
├── MaskRcnnDetector
└── GroundedSamDetector
```

本任务只实现 `YoloSegDetector`。

### 4.6 `TargetSelector`

选择器按 `TaskCommand.target_object` 过滤 `confidence >= 0.50` 的候选：

```text
0 个 plastic_cup  -> TARGET_NOT_FOUND
1 个 plastic_cup  -> 返回该 candidate
2 个及以上        -> TARGET_AMBIGUOUS
```

选择器不使用图像面积、距离或置信度打破同类实例歧义。空间约束的消费留给后续任务，并需要单独设计。

### 4.7 `RgbdLocalizer`

`RgbdLocalizer` 接收唯一候选和同一时间戳的 Depth/CameraInfo：

1. 检查 mask、Depth 和 CameraInfo 尺寸一致；
2. 丢弃 mask 内非有限、非正或超过截断距离的 Depth；
3. 按内参反投影为相机光学坐标系点云；
4. 在实例点云内部清理离群点；
5. 查询 `world <- source_frame` 的 exact-stamp transform；
6. 在 world 坐标系拟合直立杯子半径和中心；
7. 验证已知杯子半径、点数和工作区边界；
8. 生成 `LocalizedObject`。

YOLO confidence 不能绕过几何门禁。误检的圆柱尺寸不符合已知杯子时，结果是 `GEOMETRY_REJECTED`。

首版冻结以下感知参数：

```text
imgsz=640
confidence_threshold=0.50
depth_trunc_m=3.0
minimum_cup_points=50
expected_radius_m=0.04
radius_tolerance_m=0.01
```

参数变更必须生成新的版本化配置，并重新执行数据集 test split 和双平台四场景验收。

## 5. 合成数据生成

### 5.1 标签来源

数据生成器加载与生产相同的 MJCF 和 `task_camera`。每个样本从同一 camera pose 渲染两次：

```text
普通渲染      -> RGB PNG
object-ID 渲染 -> instance mask
```

生成器根据 MuJoCo geom/body ID 找到 `plastic_cup` 的可见像素，转换成 YOLO-Seg polygon 标签。标签不能根据颜色生成，否则模型仍可能只学到橙色。

### 5.2 场景覆盖

初始数据集包含 1200 张图：

```text
train: 800
val:   200
test:  200
```

每个 split 都包含：

- 没有杯子的负样本；
- 一个杯子和多个干扰物；
- 两个杯子；
- 杯子紧邻瓶子；
- 不同位置、旋转和遮挡程度；
- 不同颜色的杯子和同色瓶子；
- 相机小范围位置与朝向扰动；
- 光照、背景和材质扰动。

随机种子组和场景配置在 train、val、test 之间完全分离。同一轨迹的相邻帧不能跨 split。

### 5.3 数据与模型工件

仓库保存：

- 数据生成器；
- MJCF 多物体 fixture；
- 训练配置；
- 固定随机种子；
- dataset manifest schema；
- 小型测试 fixture。

大规模图片、训练中间产物和权重放入已登记的 V5-T004 evidence root，不进入普通 Git 历史。训练完成后保留：

```text
dataset-manifest.json
dataset.yaml
training-config.yaml
best.pt
metrics.json
weights.sha256
```

`dataset-manifest.json` 记录生成器 commit、MJCF SHA256、样本数量、split 种子和每个类别的实例数。

### 5.4 训练环境

训练在 ai-station CUDA 环境执行。macOS 不要求训练，但必须加载同一 `best.pt` 完成 MPS 推理。

训练与运行依赖使用锁定版本。实现阶段需要在两个平台完成安装 smoke test 后提交同一份受约束依赖清单；运行时不允许自动安装或升级包。

离线 `mAP`、precision、recall 和 mask IoU 全部记录，但不单独作为 V5-T004 完成证据。最终判断看真实 ROS RGB-D 场景矩阵。

## 6. ROS 节点与生命周期

### 6.1 新入口

新增：

```text
rgbd_object_pose
```

现有 `rgbd_cup_pose` 保留，作为颜色/几何基线。launch 通过显式参数选择：

```text
perception_backend=color_geometry
perception_backend=yolo_seg
```

同一进程图中只能有一个 `/cup_pose` publisher。

### 6.2 启动顺序

```text
验证参数与权重
  -> 加载 best.pt
  -> 选择 cuda / mps / explicit cpu
  -> warm-up
  -> status=READY
  -> 接收或生成一次检测请求
  -> 丢弃请求前缓存帧
  -> 消费请求后的第一组新鲜 aligned RGB-D
  -> detect -> select -> localize -> publish/result
```

V5-T004 提供 standalone `--once` 模式。节点 `READY` 后创建一次内部请求，处理一帧并退出。应用层保留 `detect_once()` 边界，V5-T005 再决定 TextAgent 到该边界的 ROS transport。

### 6.3 延迟口径

结果分别记录：

- `cold_start_latency_ms`：权重加载与 warm-up；
- `request_latency_ms`：请求被接受到结果完成。

V5-T004 的性能门槛是 `request_latency_ms <= 2000`。冷启动不计入这 2 秒，但必须记录，不能隐藏。

### 6.4 模型参数

CLI 要求：

```text
--weights /absolute/path/best.pt
--weights-sha256 <expected-sha256>
--device auto|cuda|mps|cpu
```

规则如下：

- 不允许运行时从网络下载权重；
- 权重路径必须是普通文件；
- SHA256 不一致时停止；
- 指定 `cuda` 或 `mps` 不可用时停止；
- `auto` 优先选择当前平台加速器；
- `auto` 找不到加速器时停止，除非同时提供显式 `--allow-cpu-fallback`；
- `--device cpu` 本身就是明确授权，不需要额外 fallback 标志。

macOS 正式验收必须记录 `runtime_device=mps`，ai-station 必须记录 `runtime_device=cuda`。CPU 结果不能替代两个平台的正式验收。

### 6.5 ROS 输入输出

输入沿用：

```text
/task_camera/camera_info
/task_camera/color
/task_camera/depth
```

输出：

```text
/perception/detections -> vision_msgs/msg/Detection2DArray
/perception/overlay    -> sensor_msgs/msg/Image
/cup_pose              -> geometry_msgs/msg/PoseStamped
```

`/perception/detections` 发布所有候选，即使最终是 `TARGET_AMBIGUOUS`。mask 在进程内用于定位，并写入证据文件；首版不增加自定义 mask message。

`/cup_pose` 只有在唯一目标、mask、Depth、几何验证和 exact-stamp tf2 全部通过后发布。任何失败都不能发布默认 pose，也不能重发上一帧旧 pose。

## 7. 结果记录

每次请求写入同一 run 目录：

```text
source-rgb.png
prediction-overlay.png
detections.json
selected-mask.png
selected-cloud.ply
result.json
```

`selected-mask.png` 和 `selected-cloud.ply` 只在唯一候选进入对应阶段后生成。没有目标或目标歧义不是证据文件缺失；`result.json` 必须明确记录终止边界。

`result.json` 至少包含：

```text
status
failure
request_id
source_stamp_ns
source_frame_id
model_id
weights_sha256
runtime_device
cold_start_latency_ms
inference_latency_ms
request_latency_ms
candidate_count
matching_candidate_count
published_cup_pose
artifact_paths
```

## 8. 错误处理

错误码固定为：

```text
MODEL_UNAVAILABLE
WEIGHTS_HASH_MISMATCH
DEVICE_UNAVAILABLE
RGBD_TIMEOUT
RGBD_INVALID
INFERENCE_FAILED
TARGET_NOT_FOUND
TARGET_AMBIGUOUS
MASK_INVALID
DEPTH_INVALID
GEOMETRY_REJECTED
TF_UNAVAILABLE
EVIDENCE_WRITE_FAILED
CLEANUP_FAILED
```

边界规则：

- 模型、device 或权重失败发生在订阅相机前；
- 请求只接受请求后的新鲜 frame；
- 推理失败不进入选择器；
- 0/2+ 匹配实例不进入 Depth 定位；
- mask 或 Depth 失败不查询 tf2；
- tf2 或几何失败不发布 `/cup_pose`；
- 证据写入失败时不把本次请求报告为成功；
- cleanup 失败覆盖原成功状态并返回非零。

唯一目标完成 3D 定位时进程返回 `0`。以上任一错误返回 `1`；`TARGET_NOT_FOUND` 和 `TARGET_AMBIGUOUS` 虽然是可预期的感知结果，仍属于不能向执行链提供 pose 的非零终止。

状态含义保持分离：

```text
DETECTION_COMPLETED    != 3D 定位完成
LOCALIZATION_COMPLETED != /cup_pose 已被下游消费
/cup_pose 已发布        != MuJoCo 抓取成功
```

## 9. 测试策略

### 9.1 不加载模型的单元测试

覆盖：

- `DetectionCandidate` 和 `DetectionBatch` 验证；
- 0/1/2+ `plastic_cup` 的选择结果；
- device 选择和 CPU fallback 门禁；
- 权重 SHA256；
- mask/Depth/CameraInfo 尺寸和 stamp；
- mask 内 Depth 反投影；
- 无效 Depth、点数不足、错误半径和 TF 失败；
- 每个错误路径都没有 publisher 调用；
- evidence JSON 字段和原子写入；
- fake detector 驱动完整 application flow。

### 9.2 YOLO adapter contract 测试

用伪造 Ultralytics 结果验证：

- boxes、classes、confidence 和 masks 一一对应；
- 保留所有实例；
- mask 恢复到原 RGB 尺寸；
- 数字 class index 通过固定映射变成 `plastic_cup`；
- 空 masks、非有限 confidence 和越界 bbox 被拒绝。

### 9.3 数据生成器测试

验证：

- 相同 seed 生成相同 manifest 和标签；
- object-ID mask 与 RGB 尺寸一致；
- 0/1/2 杯子样本数量符合配置；
- split seed 不重叠；
- 标签不读取材质颜色；
- polygon 坐标位于图像范围内。

### 9.4 真实模型 smoke test

两个平台都要：

1. 加载实际 `best.pt`；
2. 核对相同 SHA256；
3. 对固定测试图片推理；
4. 验证候选类别、数量和非空 mask；
5. 记录真实 `cuda` 或 `mps` device。

## 10. 双平台运行验收

macOS 和 ai-station 分别执行相同的四个 MuJoCo 场景。每个平台使用新进程图和新请求 ID，不能复用旧 topic 或上一次 pose。

| 场景 | 预期结果 |
|---|---|
| 只有橙色瓶子 | `TARGET_NOT_FOUND`，不发布新 `/cup_pose` |
| 一个杯子加多个干扰物 | 唯一 `plastic_cup`，发布新鲜 `/cup_pose` |
| 两个塑料杯 | 两个匹配 candidate，`TARGET_AMBIGUOUS`，不发布 pose |
| 杯子紧邻瓶子 | cup mask 不包含瓶子像素，唯一选择杯子 |

每次运行必须满足：

- RGB、Depth、CameraInfo 为真实 payload；
- 三者宽高、非零 stamp 和 frame ID 一致；
- 两个平台的 `weights_sha256` 相同；
- macOS 使用 `mps`，ai-station 使用 `cuda`；
- `request_latency_ms <= 2000`；
- cup mask 相对 MuJoCo truth 的 IoU 不低于 `0.80`；
- 唯一杯子的 world position 相对 MuJoCo truth 误差小于 `0.01 m`；
- 0/2 杯子场景没有新 `/cup_pose`；
- prediction overlay 清楚标出每个实例的类别、置信度和边界；
- 退出后没有重复 `/cup_pose` publisher 或残留推理进程。

GUI 截图只证明视觉结果。候选 JSON、mask IoU、truth pose error、topic payload 和进程清理仍需分别通过。

## 11. 完成条件

只有以下条件全部满足，V5-T004 才能进入学习验收：

1. `DetectorPort`、`YoloSegDetector`、`TargetSelector` 和 `RgbdLocalizer` 已实现；
2. MuJoCo object-ID 数据生成器可以复现数据集；
3. `best.pt`、训练配置、metrics 和 SHA256 已保存；
4. 定向测试和 `so101_demo_py` 包级测试通过；
5. macOS MPS 与 ai-station CUDA 完成四场景验收；
6. 同一权重、真实 RGB-D、mask、3D pose、视觉证据和 cleanup 均有记录；
7. 学习者能解释实例 mask、Depth 反投影、目标选择和 tf2 的责任边界。

代码或模型文件存在不能单独把任务标记为 `mastered`。抓取与放置也不属于本任务完成条件。

## 12. 预计文件边界

实现计划可以在以下位置落地，具体拆分以测试驱动后的最小职责为准：

```text
src/so101_demo_py/src/core/detection.py
src/so101_demo_py/src/ports/object_detector.py
src/so101_demo_py/src/application/object_pose.py
src/so101_demo_py/src/adapters/perception/yolo_seg.py
src/so101_demo_py/src/ros/rgbd_object_pose_node.py
src/so101_demo_py/src/cli/rgbd_object_pose.py
src/so101_demo_py/src/cli/generate_yolo_seg_dataset.py
src/so101_demo_py/assets/mujoco/v5_multi_object_scene.xml
src/so101_demo_py/config/perception/plastic_cup_yolo_seg.yaml
src/so101_demo_py/test/test_detection_contracts.py
src/so101_demo_py/test/test_target_selector.py
src/so101_demo_py/test/test_rgbd_localizer.py
src/so101_demo_py/test/test_yolo_seg_adapter.py
src/so101_demo_py/test/test_rgbd_object_pose.py
src/so101_demo_py/test/test_yolo_seg_dataset.py
```

新增 `vision_msgs` ROS 依赖。Torch、Ultralytics 和 MuJoCo Python binding 作为明确的感知/训练依赖管理，不在模块 import 时无条件加载。

## 13. 后续扩展

`GroundedSamDetector` 通过同一 `DetectorPort` 接入：

```text
plastic_cup
  -> 受控 prompt map
  -> Grounding DINO boxes
  -> SAM instance masks
  -> DetectionCandidate[]
  -> 同一个 TargetSelector 与 RgbdLocalizer
```

升级时不改变 Depth 反投影、tf2、几何门禁、`/cup_pose` 发布条件和错误语义。需要重新验证的是模型依赖、prompt map、推理延迟、候选置信度和双平台运行结果。
