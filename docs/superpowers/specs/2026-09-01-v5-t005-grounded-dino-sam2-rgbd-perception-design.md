# V5-T005 Grounding DINO Tiny + SAM 2.1 RGB-D 多实例感知设计

**日期：** 2026-09-01

**任务：** `V5-T005`

**代码范围：** `src/so101_demo_py`

**运行平台：** macOS Apple Silicon 与 ai-station NVIDIA GPU

## 1. 目标

V5-T004 已经用 `YoloSegDetector` 跑通多物体候选、`plastic_cup` 选择、深度定位和 `/cup_pose`。本任务增加第二个实例分割后端：Grounding DINO Tiny 先根据受控类别提示生成候选框，SAM 2.1 Hiera Tiny 再按框生成实例 mask。

新后端沿用现有 RGB-D 定位和执行链：

```text
task_camera RGB
  -> Grounding DINO Tiny
  -> plastic_cup 候选框
  -> SAM 2.1 Hiera Tiny 批量框提示分割
  -> DetectionCandidate[]
  -> TargetSelector
  -> selected mask + aligned Depth + CameraInfo
  -> RgbdLocalizer + exact-stamp tf2
  -> /cup_pose
  -> MoveIt pick&place
```

最终要在 macOS MPS 和 Linux CUDA 上完成同一套多物体场景验收。每个平台还要经过完整重启，连续完成 5 次 MuJoCo pick&place。

## 2. 已确定的范围

首版固定为：

- `IDEA-Research/grounding-dino-tiny`；
- `facebook/sam2.1-hiera-tiny`；
- Hugging Face Transformers 进程内推理；
- 每帧无状态检测；
- SAM 2.1 只使用静态图像框提示，不启用视频跟踪；
- Grounding DINO 与 SAM 2.1 在同一设备上运行；
- macOS 使用 MPS，ai-station 使用 CUDA；
- 只有明确授权时才允许 CPU fallback。

本任务不允许用 MuJoCo object ID、物体名称、truth pose、颜色阈值或最大点云簇生成生产检测结果。模拟器真值只用于验收。

## 3. 为什么选择进程内 Transformers

实现有三条路：Transformers 统一加载、分别接入两个上游仓库，或把模型部署成独立本地服务。首版选择第一条。

Grounding DINO 和 SAM 2.1 共用一套 PyTorch 设备管理，ROS 节点也不用增加图像序列化、IPC 和服务健康检查。相比直接安装两个上游仓库，这条路更容易控制 macOS 与 Linux 的依赖差异，也避开 Grounding DINO 自定义扩展带来的安装分支。

如果后续实测表明进程内方案无法满足 MPS 延迟，再单独设计本地服务或平台专用推理 adapter。首版不同时维护多条推理路径。

## 4. 组件边界

### 4.1 组件关系

```text
RgbdObjectPoseNode
  |
  +-- DetectorFactory
        |
        +-- YoloSegDetector
        |
        +-- GroundedSamDetector
              |
              +-- PromptRegistry
              +-- GroundingDinoStage
              +-- Sam2SegmentationStage
              +-- CandidateConverter
```

### 4.2 DetectorFactory

`RgbdObjectPoseNode` 当前直接构造 `YoloSegDetector`。本任务增加 `DetectorFactory`，根据 `perception_backend` 选择实现：

```text
color_geometry
yolo_seg
grounded_sam
```

factory 只负责校验后端配置并创建 adapter。它不处理 RGB-D、目标选择或 pose 发布。

### 4.3 GroundedSamDetector

`GroundedSamDetector` 实现现有接口：

```python
DetectorPort.detect(frame: DetectionFrame, query: DetectionQuery) -> DetectionBatch
```

它只读取 `frame.rgb8`、源时间戳和 frame ID。Depth、CameraInfo、tf2 与 MuJoCo truth 都不进入 detector。

这个 adapter 负责：

- 加载并预热两个模型；
- 将受控 query 映射成提示词；
- 调用 Grounding DINO；
- 校验和去重候选框；
- 把所有候选框一次送入 SAM 2.1；
- 选择并校验实例 mask；
- 生成 `DetectionBatch`。

### 4.4 PromptRegistry

首版只注册一个映射：

```text
plastic_cup -> "plastic cup."
```

调用方不能从命令行或自然语言直接传入 prompt。遇到未知 `DetectionQuery.class_id` 时返回 `UNSUPPORTED_DETECTION_QUERY`，不执行模型。

模型返回的文本 label 也不能直接成为领域类别。只有通过当前 query 和固定映射得到的结果，才能写成规范类名 `plastic_cup`。

### 4.5 GroundingDinoStage

这一阶段输入 RGB 和固定提示词，输出框与 grounding score。后处理使用 Transformers 的 `post_process_grounded_object_detection`，目标尺寸必须是原图尺寸。

候选框依次经过以下检查：

1. 坐标与 confidence 都是有限值；
2. 坐标顺序是 `x1 < x2`、`y1 < y2`；
3. 裁剪后仍有正面积；
4. label 与当前受控 query 一致；
5. 候选数量没有超过上限。

超过候选上限时整帧返回 `CANDIDATE_LIMIT_EXCEEDED`，不能只保留分数最高的若干个。

### 4.6 Sam2SegmentationStage

SAM 2.1 对当前帧只计算一次图像特征。全部合格候选框作为一个 batch 输入 `Sam2Processor`，不逐框重复编码图像。

首版使用 `multimask_output=True`。每个候选框选择 predicted IoU 最高的 mask，然后恢复到原始 RGB 分辨率。SAM 分数只用于分割质量门禁，不和 Grounding DINO confidence 相乘。

### 4.7 CandidateConverter

转换后的 `DetectionCandidate` 保持现有语义：

- `class_id` 是 `plastic_cup`；
- `confidence` 是 Grounding DINO 的 grounding score；
- `segmentation_quality` 是可选的模型无关分割质量，Grounded SAM 写入 SAM predicted IoU，YOLO 保持 `None`；
- `bbox_xyxy` 是原图像素坐标；
- `mask` 是与原 RGB 同尺寸的 bool 数组；
- source stamp 和 frame ID 原样保留。

实例编号在所有过滤和去重完成后生成。排序键固定为：

```text
confidence desc, x1, y1, x2, y2
```

这能让 MPS 和 CUDA 在候选结论相同时得到稳定的实例顺序，但不要求两个平台的浮点输出逐位相同。

## 5. 目标选择与 RGB-D 定位

`TargetSelector` 和 `RgbdLocalizer` 不增加模型专用分支。

选择规则不变：

```text
0 个合格 plastic_cup -> TARGET_NOT_FOUND
1 个合格 plastic_cup -> 进入深度定位
2 个及以上           -> TARGET_AMBIGUOUS
```

不能按最高分、面积、深度或离机器人最近来消除歧义。调用方需要唯一目标时，场景本身必须满足唯一性。

唯一 mask 通过后，`RgbdLocalizer` 才能读取对齐 Depth 和 CameraInfo，完成 mask 内深度过滤、3D 反投影、几何验证和精确源时间戳 tf2。任何失败都不能复用上一帧 `/cup_pose`。

## 6. 双模型本地包

### 6.1 目录格式

模型不在运行时下载。两个 Hugging Face snapshot 组成一个不可变本地包：

```text
<absolute-model-root>/
├── manifest.json
├── grounding-dino-tiny/
│   ├── config.json
│   ├── model.safetensors
│   ├── preprocessor_config.json
│   └── tokenizer files...
└── sam2.1-hiera-tiny/
    ├── config.json
    ├── model.safetensors
    └── preprocessor_config.json
```

仓库提交下载脚本、清单格式和依赖锁，不提交预训练模型文件。

### 6.2 manifest.json

清单至少记录：

- bundle schema version；
- 两个官方 model ID；
- 固定 Hugging Face revision；
- 每个文件的相对路径、字节数和 SHA-256；
- 提示词映射版本；
- 已验证的 Transformers、PyTorch、TorchVision 与 safetensors 版本。

打包脚本先下载到 staging，再复制成普通文件并生成清单。正式模型包内不允许符号链接。运行时还要拒绝清单之外的文件，避免同一路径被悄悄替换成另一份 snapshot。

### 6.3 启动校验

启动顺序固定为：

1. `perception_model_root` 必须是绝对目录；
2. `manifest.json` SHA 必须匹配启动参数；
3. 清单中的每个文件必须是普通文件；
4. 字节数和 SHA 必须匹配；
5. 目录中不能有未登记文件；
6. 两个模型都用 `local_files_only=True` 加载；
7. 联合 warm-up 成功后节点才进入 ready。

加载进程设置 `HF_HUB_OFFLINE=1` 和 `TRANSFORMERS_OFFLINE=1`。代码本身也必须传 `local_files_only=True`，不能只依赖环境变量。

### 6.4 DetectionBatch provenance

现有 `DetectionBatch.weights_sha256` 是单个 SHA 字段。本任务不扩大核心契约；对于 `grounded_sam`，该字段保存 `manifest.json` 的 SHA。这个 digest 指向清单内的两套模型文件和各自 SHA。

```text
model_id: grounding-dino-tiny+sam2.1-hiera-tiny
weights_sha256: sha256(manifest.json bytes)
```

运行证据同时展开记录两个模型 revision 和文件 SHA，不能只写 bundle digest。`detections.json` 和 overlay 还要记录每个 Grounded SAM 候选的 `segmentation_quality`，便于回查 mask 选择；`TargetSelector` 不读取这个字段。

## 7. 设备与精度

两个模型必须在同一 runtime device 上：

```text
auto -> cuda -> mps -> cpu
```

`cpu` 只有在 `perception_allow_cpu_fallback=true` 时可用。显式请求 `cuda` 或 `mps` 但设备不可用时，返回 `DEVICE_UNAVAILABLE`，不自动换设备。

首版固定 FP32，关闭 `torch.compile`、BF16、FP16、量化和模型拆分。这样先把 MPS/CUDA 的行为与证据边界稳定下来。完成两平台基线后，再用独立设计评估精度优化。

模型加载时间和 warmed inference latency 分开记录。不能把下载、首次编译或 warm-up 时间混进稳定推理指标。

## 8. 候选框与 mask 规则

### 8.1 初始参数

以下值用于第一轮标定：

```text
grounding_box_threshold: 0.35
grounding_text_threshold: 0.25
grounding_duplicate_iou: 0.85
grounding_max_candidates: 16
sam_mask_quality_threshold: 0.75
sam_min_mask_pixels: 64
sam_max_mask_area_ratio: 0.50
```

它们不是免测的生产常量。正式阈值要用同一套固定验证图在 macOS MPS 和 Linux CUDA 上标定，然后冻结到实验记录。

### 8.2 去重

Grounding DINO 可能为同一实例返回多个近似框。转换器在 CPU 上执行确定性 IoU 去重，保留更高分结果。`0.85` 只合并高度重合的重复框，不用于合并相邻杯子。

两个真实杯子即使互相遮挡，也必须作为两个候选交给 `TargetSelector`。如果去重会改变双杯场景结论，阈值不得进入正式配置。

### 8.3 mask 门禁

每个选中 mask 都要满足：

- predicted IoU 不低于质量阈值；
- 输出能恢复为原始图像尺寸；
- mask 是有限、非空的二维结果；
- 像素数不少于下限；
- mask 面积比例不超过上限；
- mask 与提示框有足够空间重叠。

单个低质量 mask 会被丢弃并写入 rejection diagnostics。若输出数量、维度或对象对应关系错误，整帧返回 `RESULT_CONTRACT_INVALID`。

## 9. ROS 参数

新增启动参数：

```text
perception_backend:=grounded_sam
perception_model_root:=/absolute/path/to/grounded-sam-v1
perception_model_manifest_sha256:=<64-char-sha256>
perception_device:=auto
perception_allow_cpu_fallback:=false
grounding_box_threshold:=0.35
grounding_text_threshold:=0.25
grounding_duplicate_iou:=0.85
grounding_max_candidates:=16
sam_mask_quality_threshold:=0.75
sam_min_mask_pixels:=64
sam_max_mask_area_ratio:=0.50
```

现有 `target_confidence_threshold`、Depth 门槛、TF timeout、topic 和 evidence 参数继续使用。数值参数在订阅相机前完成范围检查。

`yolo_seg` 继续使用原有 `perception_weights` 和 `perception_weights_sha256`。factory 必须按 backend 校验互斥配置：Grounded SAM 不能误用 YOLO 权重参数，YOLO 也不能忽略 Grounded SAM 模型目录。

## 10. 错误处理

### 10.1 启动错误

```text
MODEL_BUNDLE_INVALID
MODEL_HASH_MISMATCH
DEVICE_UNAVAILABLE
MODEL_LOAD_FAILED
WARMUP_FAILED
```

这些错误都发生在节点 ready 之前。失败后不订阅相机，也不创建可被误认为可用的 `/cup_pose` 路径。

### 10.2 请求错误

```text
UNSUPPORTED_DETECTION_QUERY
CANDIDATE_LIMIT_EXCEEDED
RESULT_CONTRACT_INVALID
INFERENCE_FAILED
TARGET_NOT_FOUND
TARGET_AMBIGUOUS
DEPTH_INVALID
TF_UNAVAILABLE
EVIDENCE_WRITE_FAILED
CLEANUP_FAILED
```

边界规则：

- 推理失败不进入选择器；
- 0 个或 2 个以上目标不读取 Depth；
- mask 或 Depth 失败不查询 tf2；
- tf2 失败不发布 `/cup_pose`；
- evidence 写入失败不能报告请求成功；
- cleanup 失败覆盖原来的成功状态；
- 任何失败都不能发布或复用旧 pose。

## 11. 测试策略

### 11.1 不加载模型的单元测试

fake processor 和 fake model 覆盖：

- 提示词白名单和未知类别；
- 模型包路径、manifest 与逐文件 SHA；
- 禁止符号链接和未登记文件；
- `local_files_only=True`；
- CUDA、MPS 与 CPU fallback；
- Grounding DINO 后处理、排序和去重；
- 多候选框批量送入 SAM 2.1；
- 多 mask 质量排序和原尺寸恢复；
- `segmentation_quality` 进入候选 JSON 与 overlay，但不改变目标选择；
- NaN、空 mask、维度错误与候选超限；
- 错误路径没有 publisher 调用；
- fake detector 驱动完整 application flow；
- `YoloSegDetector` 和现有 RGB-D 流程回归。

### 11.2 真实模型离线 smoke

两个平台都要：

1. 使用相同 bundle 和 manifest SHA；
2. 断网加载实际模型；
3. 完成联合 warm-up；
4. 对固定图片执行 Grounding DINO + SAM 2.1；
5. 记录真实 `mps` 或 `cuda` device；
6. 保存候选框、分数、mask 和分阶段 latency；
7. 确认退出后没有残留进程。

## 12. 双平台 MuJoCo 感知矩阵

macOS 与 ai-station 分别运行四个新进程场景：

| 场景 | 预期结果 |
|---|---|
| 只有瓶子等干扰物 | `TARGET_NOT_FOUND`，没有新 `/cup_pose` |
| 一个杯子加多个干扰物 | 唯一 `plastic_cup`，发布新鲜 `/cup_pose` |
| 两个塑料杯 | `TARGET_AMBIGUOUS`，没有新 `/cup_pose` |
| 杯子紧邻或部分遮挡干扰物 | 杯子 mask 不吞并干扰物，唯一选择 |

每轮必须满足：

- RGB、Depth、CameraInfo 是真实 payload，尺寸、stamp 和 frame ID 一致；
- macOS 实际使用 MPS，ai-station 实际使用 CUDA；
- 两个平台使用相同 commit、bundle SHA、提示词和阈值；
- warmed request latency 不超过 `2000 ms`；
- cup mask 相对 MuJoCo truth 的 IoU 不低于 `0.80`；
- 唯一杯子的 world position 误差小于 `0.01 m`；
- 0 杯和 2 杯场景没有新 pose；
- overlay 标出全部候选框、类别、DINO 分数和 SAM 质量；
- cleanup 后没有重复 publisher 或残留推理进程。

两平台不要求 mask 逐像素相同，但目标数量、选择结果和几何门槛必须一致。

如果零样本模型达不到门槛，可以调受控阈值并重跑完整矩阵。不能引入 MuJoCo truth、颜色规则、最大 mask 或最高分强选来补结果。若阈值仍无法解决，任务应停在模型能力不满足，而不是放宽安全边界。

## 13. 完整 Pick&Place 验收

四场景感知矩阵通过后，每个平台从干净进程图执行连续 5 次完整重启：

```text
Grounded SAM 感知
  -> /cup_pose
  -> MoveIt 规划
  -> 双指抓取
  -> 物理微抬升
  -> 搬运和放置
  -> 松爪脱离
  -> 杯子稳定支撑
```

每次成功都要证明：

- 目标来自本轮模型输出；
- `/cup_pose` 保留 RGB-D 源时间戳；
- MoveIt 消费的是本轮 pose；
- 杯子被双指夹持并离开桌面；
- 杯子进入放置区域；
- 松爪后杯子与夹爪分离；
- 杯子得到桌面稳定支撑；
- 所有本任务进程完成清理。

macOS 与 Linux 都必须达到 `5/5`。这组证据只证明 MuJoCo 仿真闭环，不证明真实 SO-101 硬件 pick&place。

## 14. 证据与实验账本

正式证据根登记为：

```text
/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869
```

普通开发日志放在：

```text
/tmp/so101-debug-v5-t005-grounded-sam-20260901
```

账本位于：

```text
docs/experiments/v5-t005-grounded-sam-rgbd-experiment-ledger.md
```

正式矩阵、mask、overlay、pose、truth 对照和 pick&place 连续运行证据进入 durable root。失败批次也保留；未经用户明确授权，不删除或覆盖。

## 15. 预计代码边界

实现计划预计涉及：

```text
src/so101_demo_py/src/adapters/perception/grounded_sam.py
src/so101_demo_py/src/adapters/perception/detector_factory.py
src/so101_demo_py/src/ros/rgbd_object_pose_node.py
src/so101_demo_py/src/cli/rgbd_object_pose.py
src/so101_demo_py/src/runtime/launch_composition.py
src/so101_demo_py/config/perception/
src/so101_demo_py/scripts/
src/so101_demo_py/test/
docs/experiments/v5-t005-grounded-sam-rgbd-experiment-ledger.md
docs/guides/
```

具体拆分以测试驱动后的最小职责为准。实现不能把 Transformers 类型带进 `core` 或 `ports`，也不能改变 `TargetSelector` 的 0/1/2+ 语义。

## 16. 完成条件

以下条件全部满足后，V5-T005 才完成：

1. `GroundedSamDetector` 与 detector factory 已实现；
2. 双模型本地包可以复现、校验并断网加载；
3. 定向测试和 `so101_demo_py` 包级测试通过，YOLO 路径无回归；
4. macOS MPS 与 Linux CUDA 完成四场景感知矩阵；
5. 两个平台固定同一 commit、bundle SHA 和阈值；
6. 两个平台分别连续完成 5 次完整重启 Pick&Place；
7. payload、语义选择、mask、Depth、TF、pose、物理结果、cleanup 和 provenance 都有独立证据；
8. 教学文档说明模型原理、本地部署、组件通信、运行命令和常见故障。

模型成功输出、`/cup_pose` 出现或单次抓取成功，都不能单独关闭任务。

## 17. 参考资料

- [Grounding DINO Transformers 文档](https://huggingface.co/docs/transformers/model_doc/grounding-dino)
- [Grounding DINO 官方仓库](https://github.com/IDEA-Research/GroundingDINO)
- [SAM 2 Transformers 文档](https://huggingface.co/docs/transformers/model_doc/sam2)
- [`facebook/sam2.1-hiera-tiny` 模型页](https://huggingface.co/facebook/sam2.1-hiera-tiny)
- [Meta SAM 2 官方仓库](https://github.com/facebookresearch/sam2)
