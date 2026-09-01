# SO-101 Grounded SAM RGB-D 多实例感知 PickPlace 教学与源码导读

**范围：** Grounding DINO Tiny 文本引导检测、SAM 2.1 Hiera Tiny 实例分割、不可变本地模型包、逐帧无状态推理、RGB-D 深度定位、tf2、`/cup_pose`、MoveIt 与 MuJoCo 抓放验证

**对象：** 已了解 Python 和 ROS 2 基础，希望看懂“用开放词汇模型在多个物体中找到唯一杯子，再完成抓放”的开发者

**目标：** 理解并复现下面这条链路。生产路径只读取 RGB-D，不允许用 MuJoCo object ID、truth pose、颜色阈值或预先写好的杯子坐标替代模型判断

```text
MuJoCo RGB
  -> Grounding DINO Tiny + 受控文本 "plastic cup."
  -> 多个候选框
  -> 去重
  -> SAM 2.1 Hiera Tiny + box prompt
  -> 多个实例 mask
  -> DetectionCandidate
  -> 唯一 plastic_cup 选择
  -> mask + Depth + CameraInfo
  -> exact-stamp tf2
  -> /cup_pose
  -> dynamic_cup_pick_place
  -> MoveIt -> controller -> MuJoCo
```

本文沿用 [`so101-rgbd-perception-pick-place-source-guide.md`](so101-rgbd-perception-pick-place-source-guide.md) 的讲解方式。原导读从颜色和点云聚类讲起；[`so101-yolo-seg-rgbd-perception-pick-place-source-guide.md`](so101-yolo-seg-rgbd-perception-pick-place-source-guide.md) 进一步介绍了合成数据、YOLO-Seg 微调和本地权重部署。这里换一条路线：不先训练项目专用分类器，而是让 Grounding DINO 理解受控文本，再用 SAM 2.1 从框中切出实例。

`/cup_pose` 之后的动态目标、5-DoF IK、MoveIt 规划和抓放状态机，可配合 [`so101-dynamic-cup-pick-place-source-guide.md`](so101-dynamic-cup-pick-place-source-guide.md) 阅读。

## 1. 这条路线解决什么问题

YOLO-Seg 适合类别固定、数据可控的任务。它的代价也很明确：先生成或采集数据，再标注、训练、检查指标和分发 `best.pt`。当你想快速试一个新类别时，数据准备往往比写推理代码更费时间。

Grounding DINO 接受图像和文字。输入 `plastic cup.` 后，它返回与这段文字匹配的候选框。SAM 2.1 再把每个框当成提示，输出框内物体的 mask。这样可以先做零样本验证，看看预训练模型是否已经认识目标。

不过，开放词汇不等于可以让用户随意输入 prompt。当前应用只允许：

```text
plastic_cup -> "plastic cup."
```

映射写在 [`grounded_sam.yaml`](../../src/so101_demo_py/config/perception/grounded_sam.yaml) 和 [`grounded_sam_postprocess.py`](../../src/so101_demo_py/src/adapters/perception/grounded_sam_postprocess.py) 中。CLI 传的是规范类别 `plastic_cup`，不是任意自然语言。这样做能把模型能力限制在机器人任务已经验证过的范围内。

## 2. 先看完整运行图

### 2.1 公开入口

单独运行感知节点：

```bash
ros2 run so101_demo_py rgbd_object_pose ...
```

启动 MuJoCo、感知和抓放整条链路：

```bash
ros2 run so101_demo_py so101_mujoco_perception_pick_place ...
ros2 launch so101_demo_py so101_mujoco_perception_pick_place.launch.py ...
```

console script 注册在 [`setup.py`](../../src/so101_demo_py/setup.py)。一体化入口和公开 launch 最后都调用 [`build_perception_pick_place_launch_description()`](../../src/so101_demo_py/src/runtime/launch_composition.py)，因此参数门禁、组件顺序和退出策略只有一份实现。

### 2.2 实际启动的组件

当 `perception_backend:=grounded_sam` 且执行参数通过检查后，launch 会启动这些组件：

| 组件 | 进程或节点 | 生命周期 | 责任 |
|---|---|---|---|
| MuJoCo 与 controller manager | `mujoco_ros2_control/ros2_control_node` | 长驻 | 推进物理、发布 `/clock`，承载相机和物理证据插件 |
| Robot State Publisher | `robot_state_publisher` | 长驻 | 读取 URDF 与 `/joint_states`，发布机器人 `/tf` |
| Controller spawner × 3 | `controller_manager/spawner` | 激活后退出 | 启动 joint state、手臂和夹爪 controller |
| MoveIt | `so101_mujoco_support/graceful_shutdown_move_group` | 长驻 | 提供规划、轨迹执行与 Planning Scene 接口 |
| Planning Scene 初始化 | `so101_demo_py/scene_setup` | 一次性 | 写入并回读桌子、底座和杯子碰撞对象 |
| 静态相机 TF × 2 | `tf2_ros/static_transform_publisher` | 长驻 | 发布 `base -> camera_link -> task_camera_frame` |
| Grounded SAM 感知 | `so101_demo_py/rgbd_object_pose` | 发布后等待统一关停 | 加载本地双模型包，处理 RGB-D，发布候选、overlay 和 `/cup_pose` |
| 动态抓放 | `so101_demo_py/dynamic_cup_pick_place` | 一次任务 | 消费 `/cup_pose`，调用 MoveIt/controller，并验证物理结果 |

Grounding DINO 和 SAM 2.1 没有各自启动一个 ROS 节点，也没有 HTTP 服务。它们都在 `rgbd_object_pose` 进程内运行，共用一个 device。

### 2.3 组件如何通信

```mermaid
flowchart LR
  MJ[MuJoCo + ros2_control_node]
  CAM[CameraPlugin]
  JSB[joint_state_broadcaster]
  RSP[robot_state_publisher]
  STF[static TF x 2]
  RGBD[rgbd_object_pose]
  DINO[Grounding DINO Tiny]
  SAM[SAM 2.1 Hiera Tiny]
  SEL[TargetSelector]
  LOC[RgbdLocalizer]
  DYN[dynamic_cup_pick_place]
  MG[MoveIt move_group]
  CTRL[arm + gripper controllers]

  MJ --> CAM
  MJ --> JSB
  CAM -- RGB + Depth + CameraInfo --> RGBD
  RGBD -- RGB + plastic cup. --> DINO
  DINO -- boxes + scores --> SAM
  RGBD -- RGB + box prompts --> SAM
  SAM -- masks + predicted IoU --> RGBD
  RGBD --> SEL
  SEL -- exactly one candidate --> LOC
  LOC -- exact-stamp TF query --> STF
  LOC -- exact-stamp TF query --> RSP
  RGBD -- /perception/detections --> OBS1[检测观察者]
  RGBD -- /perception/overlay --> OBS2[图像观察者]
  RGBD -- /cup_pose --> DYN
  JSB -- /joint_states --> RSP
  JSB -- /joint_states --> MG
  DYN --> MG
  MG --> CTRL
  CTRL --> MJ
```

### 2.4 ROS 接口表

| 接口 | 类型 | 发布或提供方 | 消费方 | 用途 |
|---|---|---|---|---|
| `/clock` | `rosgraph_msgs/msg/Clock` | MuJoCo | 所有 `use_sim_time` 节点 | 统一图像、TF、Pose 和执行的时间基准 |
| `/task_camera/camera_info` | `sensor_msgs/msg/CameraInfo` | CameraPlugin | `rgbd_object_pose` | 图像尺寸和针孔内参 |
| `/task_camera/color` | `sensor_msgs/msg/Image`，`rgb8` | CameraPlugin | `rgbd_object_pose` | 两个模型使用的 RGB 输入 |
| `/task_camera/depth` | `sensor_msgs/msg/Image`，`32FC1` | CameraPlugin | `rgbd_object_pose` | 选中 mask 内的米制深度 |
| `/tf_static` | `tf2_msgs/msg/TFMessage` | 静态 TF 节点 | 感知、MoveIt | 固定相机外参 |
| `/tf` | `tf2_msgs/msg/TFMessage` | Robot State Publisher | 感知、MoveIt | 机器人 link 的动态变换 |
| `/perception/detections` | `vision_msgs/msg/Detection2DArray` | `rgbd_object_pose` | 观察者 | 候选 ID、类别、置信度和 bbox |
| `/perception/overlay` | `sensor_msgs/msg/Image`，`rgb8` | `rgbd_object_pose` | 观察者 | 带 mask、bbox、DINO 分数和 SAM 质量的图像 |
| `/cup_pose` | `geometry_msgs/msg/PoseStamped` | `rgbd_object_pose` | `dynamic_cup_pick_place` | `world` frame 下的杯子中心 |
| `/joint_states` | `sensor_msgs/msg/JointState` | joint state broadcaster | RSP、MoveIt、抓放节点 | 关节反馈 |
| `/plan_kinematic_path` | `moveit_msgs/srv/GetMotionPlan` | MoveIt | 抓放节点 | 生成碰撞约束轨迹 |
| `/execute_trajectory` | `moveit_msgs/action/ExecuteTrajectory` | MoveIt | 抓放节点 | 执行手臂轨迹 |

完整实例 mask 不塞进 `Detection2DArray`。它保留在进程内的 `DetectionCandidate.mask` 中，同时写入证据目录。三维定位读取的是布尔 mask，不是 overlay 图片。

## 3. 源码分成了哪些层

| 层 | 主要文件 | 只负责什么 |
|---|---|---|
| 核心数据契约 | [`detection.py`](../../src/so101_demo_py/src/core/detection.py) | frame、candidate、batch 和质量字段 |
| 检测端口 | [`object_detector.py`](../../src/so101_demo_py/src/ports/object_detector.py) | 定义 `detect(frame, query)`，不依赖具体模型 |
| 模型包校验 | [`model_bundle.py`](../../src/so101_demo_py/src/adapters/perception/model_bundle.py) | manifest、文件集合、大小和 SHA-256 |
| 纯后处理 | [`grounded_sam_postprocess.py`](../../src/so101_demo_py/src/adapters/perception/grounded_sam_postprocess.py) | prompt、框去重、mask 门禁和 candidate 转换 |
| 模型 adapter | [`grounded_sam.py`](../../src/so101_demo_py/src/adapters/perception/grounded_sam.py) | 本地加载、warm-up、DINO 推理和 SAM 推理 |
| detector 工厂 | [`detector_factory.py`](../../src/so101_demo_py/src/adapters/perception/detector_factory.py) | 验证后端参数，构造 YOLO 或 Grounded SAM |
| 应用规则 | [`object_pose.py`](../../src/so101_demo_py/src/application/object_pose.py) | 唯一目标选择、深度定位和请求编排 |
| ROS adapter | [`rgbd_object_pose_node.py`](../../src/so101_demo_py/src/ros/rgbd_object_pose_node.py) | 订阅、tf2、消息转换、publish 和生命周期 |
| 证据写入 | [`perception_evidence.py`](../../src/so101_demo_py/src/runtime/perception_evidence.py) | 原子写 RGB、mask、overlay、点云和 JSON |
| 启动编排 | [`launch_composition.py`](../../src/so101_demo_py/src/runtime/launch_composition.py) | 参数门禁、组件顺序、退出与清理 |

`TargetSelector` 和 `RgbdLocalizer` 没有 Grounding DINO 或 SAM 分支。更换模型只发生在 `DetectorPort` 的 adapter 一侧。

## 4. Grounding DINO Tiny 怎样把文字变成候选框

传统固定类别检测器的输出类别由训练配置决定。Grounding DINO 同时编码图片和文字，把文字 token 与图像区域做匹配。当前输入是：

```text
image: 当前 RGB 帧
text:  "plastic cup."
```

processor 把图片和文字转换为 tensor。模型输出后，`post_process_grounded_object_detection()` 使用两道阈值：

```text
grounding_box = 0.35
grounding_text = 0.25
```

`grounding_box` 控制框的检测分数，`grounding_text` 控制文字与区域的匹配。通过门槛的结果还要满足：label 必须精确归一为 `plastic cup`，bbox 必须有正面积并位于图像内，候选总数不能超过 `16`。

模型输出的 DINO score 保存到 `DetectionCandidate.confidence`。后面的 `TargetSelector` 继续用它和应用层 `confidence_threshold` 判断候选是否有资格执行。

## 5. 为什么候选框还要去重

同一个杯子可能产生两个高度重叠的框。如果直接把两个框送入 SAM，最终会得到两个候选，`TargetSelector` 就会返回 `TARGET_AMBIGUOUS`。

[`convert_grounding_results()`](../../src/so101_demo_py/src/adapters/perception/grounded_sam_postprocess.py) 先按分数降序，再比较 bbox IoU：

```text
duplicate_iou = 0.85
```

与已保留框的 IoU 达到或超过 `0.85` 时，较后的框被视为重复。这个步骤只合并同一物体的重复预测，不负责在两个真实杯子之间做选择。

## 6. SAM 2.1 怎样从 box prompt 得到实例 mask

Grounding DINO 只给矩形框。框中往往还有桌面和相邻物体，直接拿整个 bbox 做深度反投影会污染点云。

[`GroundedSamDetector._sam_results()`](../../src/so101_demo_py/src/adapters/perception/grounded_sam.py) 把所有候选框组成一次 batch：

```text
input_boxes.shape == (1, object_count, 4)
```

SAM 2.1 Hiera Tiny 对每个框返回多个 mask 方案，以及每个方案的 predicted IoU。后处理选择 predicted IoU 最高的那个 mask，再检查：

| 门禁 | 默认值 | 目的 |
|---|---:|---|
| `sam_quality` | `0.75` | predicted IoU 太低时拒绝该 mask |
| `min_mask_pixels` | `64` | 去掉过小碎片 |
| `max_mask_area_ratio` | `0.50` | 防止 mask 吞掉大半张图 |
| mask inside bbox ratio | `0.80` | 大部分 mask 必须位于提示框内 |

通过后，mask 被转成与原图同尺寸的布尔数组。被拒绝的框会记录 `MASK_REJECTED`，日志带 DINO score、最高 SAM quality 和当前门槛，便于判断是哪一道门限挡住了候选。

## 7. DINO confidence 与 SAM predicted IoU 不是一回事

一个 candidate 同时有两个质量值：

```text
confidence            = Grounding DINO score
segmentation_quality  = SAM predicted IoU
```

DINO score 表示图像区域与 `plastic cup.` 的匹配强度。SAM predicted IoU 是模型对 mask 质量的内部估计，不是拿 truth mask 现场算出的 IoU。

当前规则是：SAM 质量只负责 mask 门禁和证据记录，`TargetSelector` 不按它排序，也不会用它在两个杯子之间“挑更好的一个”。这能避免模型质量分偷偷改变任务语义。

## 8. 为什么必须逐帧无状态

SAM 2.1 有视频跟踪能力，但本版本没有启用。每次 `detect()` 都重新执行：

```text
current RGB
  -> Grounding DINO
  -> current boxes
  -> one batched SAM call
  -> current masks
```

adapter 不保存上一帧的 memory、object token 或 track ID。这样做有三个现实原因：

1. 一次请求的结果只属于当前 source stamp，证据容易复核；
2. 仿真 reset 或物体跳变后，不会把旧目标延续到新场景；
3. Mac MPS 和 Linux CUDA 共用同一套简单生命周期，先把跨平台基线跑稳。

代价是每帧都要运行两个模型，延迟高于视频跟踪。正式门槛要求 warm 后单次请求不超过 `2000 ms`，这个数值必须在真实模型 smoke 中测，不能从单元测试推断。

## 9. `DetectionCandidate` 如何承接两个模型

每个实例至少包含：

```text
instance_id
class_id = plastic_cup
confidence = DINO score
segmentation_quality = SAM predicted IoU
bbox_xyxy
mask
source_stamp_ns
source_frame_id
image_width
image_height
```

mask 必须非空，尺寸必须与当前 RGB 一致；candidate 的 stamp、frame 和尺寸不能与 batch 冲突。模型输出形状错误、NaN、越界分数或候选数量不一致时，后处理返回 `RESULT_CONTRACT_INVALID`，不会猜测缺失字段。

## 10. 为什么目标选择仍然是 0、1、2+

[`TargetSelector`](../../src/so101_demo_py/src/application/object_pose.py) 只看规范类别和 DINO confidence：

| 合格 `plastic_cup` 数量 | 结果 | 是否继续定位 |
|---:|---|---:|
| 0 | `TARGET_NOT_FOUND` | 否 |
| 1 | 选择该 candidate | 是 |
| 2 或更多 | `TARGET_AMBIGUOUS` | 否 |

两个杯子都满足条件时，程序没有“左边”“离机械臂近”或“分数最高”这样的任务约束。此时继续执行等于替用户猜目标，所以必须 fail closed。

## 11. RGB-D 为什么仍要 exact-stamp 对齐

两个模型只读取 RGB，三维位置仍依赖 Depth 和 CameraInfo。`AlignedRgbdBuffer` 只接收：

```text
camera_info.stamp == color.stamp == depth.stamp
```

节点还检查 frame、宽高和编码。RGB 必须是 `rgb8`，Depth 必须是 `32FC1`。第 N 帧的 mask 如果配上第 N+1 帧的 Depth，物体一动，边界点就会落到错误的三维位置。

## 12. mask、Depth 和 tf2 如何得到世界坐标

`RgbdLocalizer` 只遍历选中 mask 的像素。针孔相机反投影为：

```text
x = (u - cx) * z / fx
y = (v - cy) * z / fy
z = depth[v, u]
```

无效、非正或超过 `depth_trunc_m` 的深度被丢弃。点数不足时返回 `DEPTH_INVALID`。

得到相机坐标点云后，代码在原始 RGB-D source stamp 查询：

```text
world <- task_camera_frame
```

查询失败返回 `TF_UNAVAILABLE`。这里不能改用 latest transform，因为 latest TF 可能对应机械臂或相机的另一个时刻。

点云转换到 `world` 后，还要通过桌高、杯高、预期半径和半径容差。只有这些门禁都通过，才生成杯子 body center。

## 13. `/cup_pose` 何时发布

应用层顺序是：

```text
detect
  -> 写 source RGB、overlay、detections 和 candidate masks
  -> publish detections/overlay
  -> select
  -> 写 selected mask
  -> localize
  -> 写 selected cloud 和 staged result
  -> publish /cup_pose
  -> 标记 published_cup_pose=true
```

发布的消息保持原始 source stamp：

```yaml
header:
  stamp: <RGB-D source stamp>
  frame_id: world
pose:
  position: <localized cup body center>
  orientation: {x: 0.0, y: 0.0, z: 0.0, w: 1.0}
```

任何失败都不会发布默认 Pose，也不会复用上一轮 `/cup_pose`。

## 14. “本地推理服务”在这里是什么

当前实现没有 Triton、TorchServe 或 HTTP endpoint。`rgbd_object_pose` 是 ROS graph 中的本地感知进程：

```text
ROS executable
  -> verify immutable bundle
  -> force HF_HUB_OFFLINE=1 and TRANSFORMERS_OFFLINE=1
  -> import torch + transformers
  -> select mps/cuda
  -> load both snapshots with local_files_only=True
  -> warm up both models
  -> subscribe aligned RGB-D
  -> publish ROS topics
```

称它为服务，是因为其他 ROS 节点可以通过 topic 发现和消费它，不表示模型部署在远端服务器。

## 15. 不可变双模型包解决什么问题

模型来源固定为：

| 角色 | model ID | revision |
|---|---|---|
| detector | `IDEA-Research/grounding-dino-tiny` | `a2bb814dd30d776dcf7e30523b00659f4f141c71` |
| segmenter | `facebook/sam2.1-hiera-tiny` | `de431c4043854a71d8101e17995dfe596bf101a5` |

prepare CLI 下载这两个 revision，把普通文件复制到一个新目录，并生成 canonical `manifest.json`。manifest 记录：

- pipeline ID 和受控 prompt；
- 两个模型的 ID、revision 和目录；
- 每个普通文件的相对路径、大小和 SHA-256；
- 从同目录 `requirements.lock` 解析出的完整 `name==version` 映射。

prepare CLI 不会调用 `pip freeze`，也不读取当前 venv 来猜版本。它先逐行解析 [`requirements.lock`](../../src/so101_demo_py/config/perception/requirements.lock)：缺 pin、重复 pin、`>=` 一类非精确写法都会在下载模型前失败。运行时要同时提供 bundle 根目录和 manifest SHA-256。`verify_model_bundle()` 除了检查 symlink、路径逃逸、文件集合、大小和逐文件 SHA，还会把 manifest 的依赖映射与固定预期逐项比较；即使有人改过版本并重新计算 manifest SHA，也不能通过这层校验。

校验完成后，Transformers 仍使用 `local_files_only=True`。进程还会在任何 Hugging Face loader 调用前，把 `HF_HUB_OFFLINE` 和 `TRANSFORMERS_OFFLINE` 强制设为 `1` 并回读确认。调用方原先传入 `0` 时，以本进程的离线策略为准，不会带着冲突值继续加载。

bundle 输出目录必须不存在。prepare 不会覆盖同名目录，也不会把一次失败下载混进已经验收的模型包。

## 16. 依赖锁和 ROS Python 要分别确认

[`requirements.lock`](../../src/so101_demo_py/config/perception/requirements.lock) 固定了 PyTorch、Transformers、Hugging Face Hub、tokenizers 和图像依赖。模型依赖应放进隔离 venv，不要直接污染系统 Python。

部署时要确认两层：

```text
ROS interpreter
  -> rclpy、launch、vision_msgs、tf2_ros

perception site-packages
  -> torch、transformers、huggingface_hub、safetensors、Pillow
```

只激活 perception venv 可能找不到 ROS；只 source ROS overlay 又可能找不到模型库。先检查文件路径，再启动节点。

## 17. 如何构建本地模型包

这一步需要联网，只在准备机执行一次。输出目录必须是绝对路径且尚不存在：

```bash
source /opt/ros/jazzy/setup.zsh
source /absolute/path/to/candidate/install/setup.zsh

CONFIG="$(ros2 pkg prefix so101_demo_py)/share/so101_demo_py/config/perception/grounded_sam.yaml"
MODEL_ROOT=/absolute/path/to/grounded-sam-bundle
RESULT=/absolute/path/to/grounded-sam-bundle-result.json

ros2 run so101_demo_py prepare_grounded_sam_bundle \
  --config "$CONFIG" \
  --output "$MODEL_ROOT" | tee "$RESULT"
```

成功输出形如：

```json
{"manifest_sha256": "<64 lowercase hex characters>", "status": "OK"}
```

把 digest 单独取出：

```bash
MODEL_MANIFEST_SHA256="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["manifest_sha256"])' "$RESULT")"
printf '%s\n' "$MODEL_MANIFEST_SHA256"
```

本任务的 Task 10 才会执行真实下载、构建和双平台 smoke。代码和包级测试通过，不代表模型包已经构建。

## 18. 如何离线复制并复核 bundle

把整个 bundle 当作一个不可拆分的部署件。可以先打包复制，再在目标机解包到新目录；传输工具不限，但不要只拷贝两个 `model.safetensors`。

目标机在启动 ROS 前执行一次只读复核：

```bash
export MODEL_ROOT=/absolute/path/to/grounded-sam-bundle
export MODEL_MANIFEST_SHA256=<manifest_sha256_from_prepare_output>

python3 -c '
import os
from pathlib import Path
from so101_demo.adapters.perception.model_bundle import verify_model_bundle
b = verify_model_bundle(Path(os.environ["MODEL_ROOT"]), os.environ["MODEL_MANIFEST_SHA256"])
print(b.root)
print(b.manifest_sha256)
print(b.detector_dir)
print(b.segmenter_dir)
'
```

Mac 和 Linux 应使用同一 bundle、同一 manifest SHA 和同一阈值。device 不同不需要复制两份模型权重。

## 19. macOS MPS 本地部署

下面用临时 venv 演示。安装依赖属于环境变更，实际操作前先确认目标目录和授权范围。

```zsh
python3.11 -m venv /tmp/so101-grounded-sam-macos
source /tmp/so101-grounded-sam-macos/bin/activate
python -m pip install -r src/so101_demo_py/config/perception/requirements.lock
```

确认 MPS 和模型库：

```zsh
python -c 'import torch, transformers; print(torch.__version__); print(transformers.__version__); print(torch.backends.mps.is_built()); print(torch.backends.mps.is_available())'
```

运行 ROS 入口前，加载 ROS 与候选包 overlay，再注入 venv 的模型依赖：

```zsh
source /opt/ros/jazzy/setup.zsh
source /absolute/path/to/candidate/install/setup.zsh
export PYTHONPATH=/tmp/so101-grounded-sam-macos/lib/python3.11/site-packages${PYTHONPATH:+:$PYTHONPATH}
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

ros2 pkg prefix so101_demo_py
python -c 'import rclpy, torch, transformers; print(rclpy.__file__); print(torch.__file__); print(transformers.__file__)'
```

正式参数使用 `perception_device:=mps` 和 `perception_allow_cpu_fallback:=false`。MPS 不可用时返回 `DEVICE_UNAVAILABLE`，不会静默转 CPU。

## 20. Linux CUDA 本地部署

ai-station 使用 zsh。先确认主机和 overlay：

```zsh
hostname
pwd
source /opt/ros/jazzy/setup.zsh
source /absolute/path/to/candidate/install/setup.zsh
```

创建隔离 venv：

```zsh
python3.12 -m venv /data/work/venvs/so101-grounded-sam
source /data/work/venvs/so101-grounded-sam/bin/activate
python -m pip install -r src/so101_demo_py/config/perception/requirements.lock
```

CUDA 预检：

```zsh
nvidia-smi
python -c 'import torch, transformers; print(torch.__version__); print(transformers.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))'
```

把模型依赖接到 ROS entrypoint：

```zsh
export PYTHONPATH=/data/work/venvs/so101-grounded-sam/lib/python3.12/site-packages${PYTHONPATH:+:$PYTHONPATH}
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
python -c 'import rclpy, torch, transformers; print(rclpy.__file__); print(torch.__file__); print(transformers.__file__)'
```

正式参数使用 `perception_device:=cuda` 和 `perception_allow_cpu_fallback:=false`。`nvidia-smi` 只证明驱动可见，还要确认 `torch.cuda.is_available()` 和真实模型 smoke。

## 21. 单独启动 Grounded SAM 感知节点

先启动 MuJoCo 相机、相机 TF 和必要 ROS stack，再运行一次请求：

```bash
ros2 run so101_demo_py rgbd_object_pose \
  --backend grounded_sam \
  --model-root /absolute/path/to/grounded-sam-bundle \
  --model-manifest-sha256 <manifest_sha256_from_prepare_output> \
  --device mps \
  --grounding-box-threshold 0.35 \
  --grounding-text-threshold 0.25 \
  --duplicate-iou 0.85 \
  --max-candidates 16 \
  --sam-quality-threshold 0.75 \
  --min-mask-pixels 64 \
  --max-mask-area-ratio 0.50 \
  --request-id grounded-sam-smoke-001 \
  --evidence-root /absolute/path/to/new-evidence-directory \
  --once
```

Linux 把 `--device mps` 改为 `--device cuda`。`--once` 适合 smoke；一体化 launch 不传它，感知节点会等抓放 workflow 完成后统一关停。

## 22. 一体化启动感知与抓放

先准备一个不存在的 evidence file。launch 会创建独占 session 目录：

```bash
mkdir -p /tmp/so101-debug-grounded-sam-tutorial

ros2 run so101_demo_py so101_mujoco_perception_pick_place \
  run_mode:=execute \
  execute:=true \
  headless:=false \
  sensor_rendering:=true \
  session_id:=grounded-sam-tutorial-001 \
  evidence_file:=/tmp/so101-debug-grounded-sam-tutorial/run-001.json \
  mujoco_scene:="$(ros2 pkg prefix so101_demo_py)/share/so101_demo_py/assets/mujoco/v5_multi_object_scene.xml" \
  mujoco_initial_keyframe:=task_start \
  perception_backend:=grounded_sam \
  perception_model_root:=/absolute/path/to/grounded-sam-bundle \
  perception_model_manifest_sha256:=<manifest_sha256_from_prepare_output> \
  perception_device:=mps \
  perception_allow_cpu_fallback:=false \
  grounding_box_threshold:=0.35 \
  grounding_text_threshold:=0.25 \
  grounding_duplicate_iou:=0.85 \
  grounding_max_candidates:=16 \
  sam_mask_quality_threshold:=0.75 \
  sam_min_mask_pixels:=64 \
  sam_max_mask_area_ratio:=0.50
```

Linux 使用 `perception_device:=cuda`。注意 launch 参数是 `sam_mask_quality_threshold`，传给 `rgbd_object_pose` 时会转换为 CLI 参数 `--sam-quality-threshold`。

`sensor_rendering:=true` 不能省略。topic 名存在不代表相机真的在产生新 RGB-D。

## 23. launch 的启动顺序和失败策略

```text
注册退出处理器
  -> 启动静态 TF、MuJoCo、RSP、MoveIt、controllers、scene_setup
  -> scene_setup exit 0
      -> 同时启动 rgbd_object_pose 与 dynamic_cup_pick_place
  -> 感知发布 /cup_pose
  -> workflow 执行
  -> workflow 返回终态
  -> 统一关停本轮拥有的进程
```

模型包路径必须是已有的绝对非 symlink 目录，manifest digest 必须是 64 位小写十六进制。Grounded SAM 参数不能与 YOLO 权重参数混用。参数检查在节点 materialize 前完成，错误配置不会先启动半套机器人栈。

MuJoCo、RSP、MoveIt、静态 TF 或感知节点在 workflow 完成前退出，launch 都按失败处理。感知失败不会回退到固定杯位。

## 24. 常见错误码怎样定位

| 错误或症状 | 首先检查 | 不要先做什么 |
|---|---|---|
| `MODEL_BUNDLE_INVALID` | manifest schema、文件集合、symlink、路径逃逸 | 不要跳过 verifier |
| `MODEL_HASH_MISMATCH` | manifest SHA、文件大小和逐文件 SHA-256 | 不要重新下载单个缺失文件混入旧 bundle |
| `MODEL_LOAD_FAILED` | Transformers pin、snapshot 完整性、Python 路径 | 不要自动转在线 `from_pretrained()` |
| `DEVICE_UNAVAILABLE` | MPS/CUDA probe、wheel 和驱动 | 不要静默启用 CPU fallback |
| `WARMUP_FAILED` | 两个模型能否在同一 device 完成一次调用 | 不要只 warm DINO 或只 warm SAM |
| `UNSUPPORTED_DETECTION_QUERY` | query 是否为 `plastic_cup` | 不要把任意自然语言直接传入模型 |
| `CANDIDATE_LIMIT_EXCEEDED` | DINO 原始 proposal 数是否超过 `grounding_max_candidates` | 不要在 score/label 过滤后偷偷截断原始输出 |
| `RESULT_CONTRACT_INVALID` | boxes、scores、labels、masks 和 quality shape | 不要猜测或截断不一致数组 |
| `MASK_REJECTED` | predicted IoU、像素数、面积占比、框内占比 | 不要先放宽全部阈值 |
| `TARGET_NOT_FOUND` | overlay、DINO label/score、SAM rejection 日志 | 不要发布默认 Pose |
| `TARGET_AMBIGUOUS` | 是否确有两个合格杯子 | 不要暗中选最高分 |
| `DEPTH_INVALID` | selected mask 内 Depth、编码、点数 | 不要用 bbox 中心当三维位置 |
| `TF_UNAVAILABLE` | source stamp 的 `world <- task_camera_frame` | 不要换成 latest TF |
| `/cup_pose` 已有但抓放失败 | MoveIt、controller、Gazebo pose/contact 和 Planning Scene | 不要把 Pose 发布当成物理成功 |

## 25. 证据目录里有什么

一次感知请求会写出：

```text
source-rgb.png
prediction-overlay.png
candidate-mask-000.png
candidate-mask-001.png
...
detections.json
selected-mask.png
selected-cloud.ply
model-provenance.json
result.json
```

`detections.json` 同时记录 `confidence` 和 `segmentation_quality`。`model-provenance.json` 记录 backend、pipeline ID、manifest SHA 和 manifest 内容。`TARGET_NOT_FOUND`、`TARGET_AMBIGUOUS` 与 mask 拒绝也要保留证据，因为“不发布 `/cup_pose`”本身无法说明失败发生在哪一层。

## 26. 四场景如何验收

正式质量矩阵固定四类场景：

| 场景 | 期望感知结果 | `/cup_pose` |
|---|---|---:|
| 无杯，只有干扰物 | `TARGET_NOT_FOUND` | 否 |
| 一个杯子加干扰物 | 唯一 candidate，继续定位 | 是 |
| 两个合格杯子 | `TARGET_AMBIGUOUS` | 否 |
| 杯子贴近瓶子 | mask 不粘连，唯一 candidate | 是 |

两个平台都要检查：

```text
warmed latency <= 2000 ms
truth mask IoU >= 0.80
unique-cup world position error < 0.01 m
```

truth mask、MuJoCo object ID 和 truth pose 只用于验收计算，不能送进 detector 或 `TargetSelector`。

## 27. 连续 5/5 抓放怎样计数

Mac 和 Linux 分开统计，每次使用 `FULL_RESTART`。五次必须固定：

- source commit；
- bundle manifest SHA；
- 阈值；
- device；
- 场景和成功契约。

一次有效失败会中断连续序列。环境污染导致的 `INVALID` 运行不算产品失败，但当前批次也要停止，修复后换新 experiment ID 重开五次。

每次成功不能只看 `DONE`。还要有 controller/joint/TF 变化、Gazebo 杯子 pose/contact、MoveIt attached/world scene 收敛，以及动作后的新截图。

截至本文对应的 Task 9，真实模型下载、MPS/CUDA 推理、四场景质量矩阵和两个平台的连续 5/5 仍未执行。它们属于后续 Task 10/11，不能由 fake-backed 单元测试代替。

## 28. 为什么 V1 不需要 YOLO 式微调和合成数据

Grounded SAM V1 是开放词汇零样本基线。代码直接使用固定 revision 的预训练 Grounding DINO Tiny 和 SAM 2.1 Hiera Tiny，没有训练 loop、dataset YAML 或项目专用 checkpoint。因此，运行本版本不需要先生成 MuJoCo 合成训练集。

这不表示数据永远没用。四场景 RGB、truth mask、候选和误差证据仍要保存，用来回答两个问题：

1. 零样本模型在当前相机、材质和遮挡下是否够用；
2. 若不够用，失败集中在检测、文字匹配还是 mask 边界。

如果零样本质量或延迟达不到门槛，再决定走哪条路：调整受控 prompt/阈值、换模型，或回到 YOLO-Seg 微调。合成数据、object-ID 标签、数据集打包和 YOLO 微调流程见 [`SO-101 YOLO-Seg RGB-D 多实例感知 PickPlace 教学与源码导读`](so101-yolo-seg-rgbd-perception-pick-place-source-guide.md)。不要在没有失败分布的情况下先做一轮大规模微调。

## 29. Grounded SAM 与 YOLO-Seg 怎么选

| 维度 | Grounded SAM V1 | YOLO-Seg |
|---|---|---|
| 类别来源 | 受控文本 + 预训练开放词汇 | 项目训练数据中的固定类别 |
| 首次准备 | 下载两个固定 snapshot | 合成/采集、标注、训练和权重验收 |
| 推理链 | DINO 框 + SAM mask | 单模型直接给 bbox/class/mask |
| 延迟与显存 | 通常更高 | 通常更低 |
| 新类别试验 | 改受控映射后重新验收 | 通常需要补数据并训练 |
| 项目内 V1 状态 | 零样本，真实验收待完成 | 已有合成数据与微调教学链 |

工程上常见做法是先用开放词汇模型验证任务可行性、积累失败样本，再决定是否训练更轻的专用模型。

## 30. 建议的源码阅读顺序

1. [`grounded_sam.yaml`](../../src/so101_demo_py/config/perception/grounded_sam.yaml)：固定模型、revision、prompt 和阈值；
2. [`model_bundle.py`](../../src/so101_demo_py/src/adapters/perception/model_bundle.py)：不可变 bundle；
3. [`grounded_sam_postprocess.py`](../../src/so101_demo_py/src/adapters/perception/grounded_sam_postprocess.py)：框去重和 mask 门禁；
4. [`grounded_sam.py`](../../src/so101_demo_py/src/adapters/perception/grounded_sam.py)：两个模型的加载、warm-up 和逐帧推理；
5. [`detector_factory.py`](../../src/so101_demo_py/src/adapters/perception/detector_factory.py)：后端互斥和 provenance；
6. [`detection.py`](../../src/so101_demo_py/src/core/detection.py)：candidate 契约；
7. [`object_pose.py`](../../src/so101_demo_py/src/application/object_pose.py)：0/1/2+ 选择和深度定位；
8. [`rgbd_object_pose_node.py`](../../src/so101_demo_py/src/ros/rgbd_object_pose_node.py)：ROS 与 tf2；
9. [`perception_evidence.py`](../../src/so101_demo_py/src/runtime/perception_evidence.py)：证据文件；
10. [`launch_composition.py`](../../src/so101_demo_py/src/runtime/launch_composition.py)：组件和生命周期；
11. [`so101-dynamic-cup-pick-place-source-guide.md`](so101-dynamic-cup-pick-place-source-guide.md)：Pose 之后的执行闭环。

## 31. 初学者最小观察练习

先不运行完整抓放。用 `rgbd_object_pose --once` 处理一个场景，然后打开：

```text
source-rgb.png
prediction-overlay.png
candidate-mask-000.png
detections.json
result.json
```

按顺序回答：

1. Grounding DINO 返回了几个框，DINO score 分别是多少？
2. 去重前后是否有变化？变化由哪个 IoU 门槛造成？
3. 每个框的最高 SAM predicted IoU 是多少？
4. 被拒绝的 mask 卡在哪一道门禁？
5. `confidence` 和 `segmentation_quality` 为什么不能混为一个分数？
6. 两个杯子都通过时，为什么没有 `selected-mask.png` 和 `/cup_pose`？
7. 唯一杯子的点云只来自哪些像素？
8. `/cup_pose.header.stamp` 为什么要保留 RGB-D source stamp？

观察清楚再启动 pick&place。这样一旦失败，你能判断它停在模型包、DINO、SAM、选择、Depth、TF 还是执行层。

## 32. 自检问题

读完后，应能不看文档回答：

1. Grounding DINO 和 SAM 2.1 各自负责哪一步？
2. 为什么 prompt 固定为 `plastic_cup -> "plastic cup."`？
3. DINO confidence 与 SAM predicted IoU 分别表示什么？
4. 为什么 mask quality 不参与两个杯子之间的排序？
5. `duplicate_iou=0.85` 解决的是重复预测还是目标歧义？
6. 为什么当前实现不启用 SAM 2.1 视频跟踪？
7. bundle 为什么既要逐文件 SHA，又要 manifest SHA？
8. `local_files_only=True` 防止了什么？
9. Mac MPS 与 Linux CUDA 为什么能用同一个 bundle？
10. 0、1、2 个合格杯子分别产生什么结果？
11. mask 为什么比 bbox 更适合深度反投影？
12. exact-stamp tf2 失败时为什么不能用 latest transform？
13. `/perception/detections`、`/perception/overlay` 和 `/cup_pose` 分别服务谁？
14. 为什么 V1 不需要 YOLO 式合成训练集？
15. 哪些证据才能证明一次 pick&place 真正成功？

如果答案还停留在“DINO 找框，SAM 分割，最后发布 Pose”，建议回到组件图，对着一次真实证据目录把 source stamp、candidate、mask、点云、TF 和物理结果串起来。
