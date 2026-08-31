# V5-T004 YOLO-Seg RGB-D 多实例感知实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 macOS Apple Silicon 与 ai-station Linux 上，用同一份 YOLO-Seg 权重从真实 MuJoCo RGB-D 识别 `plastic_cup`，完成唯一实例选择、深度定位和 `/cup_pose` 发布，并复用现有动态执行链完成两平台 MuJoCo pick&place。

**Architecture:** 生产链按 `DetectorPort -> TargetSelector -> RgbdLocalizer -> ROS publisher` 拆分。YOLO adapter 只消费 RGB；选择器只按规范类别和置信度判定 0/1/2+ 候选；定位器只消费唯一 mask 与同时间戳 Depth/CameraInfo，执行几何门禁和 exact-stamp tf2。感知验收与 pick&place 验收分别计数，后者只复用现有动态执行链，不扩展 TextAgent 权限。

**Tech Stack:** Python 3.11/3.12、ROS 2 Jazzy、NumPy、Open3D、MuJoCo、Ultralytics YOLO11-Seg、PyTorch MPS/CUDA、pytest、vision_msgs。

**Spec:** `docs/superpowers/specs/2026-08-31-v5-t004-yolo-seg-rgbd-perception-design.md`

## Global Constraints

- 首版基础模型固定为 `yolo11n-seg.pt`，训练产物固定为一份 `best.pt`；macOS 与 Linux 必须核对相同 SHA256。
- 生产 `YoloSegDetector` 只读取 RGB；MuJoCo object-ID segmentation 只用于数据标签和验收 truth。
- 感知参数固定为 `imgsz=640`、`confidence_threshold=0.50`、`depth_trunc_m=3.0`、`minimum_cup_points=50`、`expected_radius_m=0.04`、`radius_tolerance_m=0.01`。
- 0 个匹配候选返回 `TARGET_NOT_FOUND`；1 个返回该实例；2 个及以上返回 `TARGET_AMBIGUOUS`。选择器不得用距离、面积或置信度打破同类歧义。
- `/cup_pose` 只在唯一目标、mask、Depth、几何验证和 exact-stamp tf2 全部通过后发布；失败时不发布默认 pose，也不重发旧 pose。
- 正式验收要求 macOS `runtime_device=mps`、ai-station `runtime_device=cuda`、`request_latency_ms <= 2000`、mask truth IoU `>= 0.80`、唯一杯子 world position 误差 `< 0.01 m`。
- 每个平台四个感知场景使用独立进程图和新 request ID；最终 pick&place 使用 MuJoCo 仿真，不代表真实机械臂验收。
- 开发阶段登记唯一证据根 `/tmp/so101-debug-v5-t004-yolo-seg-20260831/`。Task 7 生成大规模数据前，先按相对路径核对 SHA256、大小和文件数，再迁移到 `/data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/` 并更新账本；迁移完成前不得创建第二套正式证据目录。
- ai-station 当前 `nvidia-smi` 因用户态 `595.84` 与已加载内核模块 `595.71.05` 不一致而失败。CUDA 训练和正式 Linux 验收必须等 `nvidia-smi` 与 `torch.cuda.is_available()` 都通过；不得用 CPU 结果替代。
- 不修改用户已有 `/Users/matianyi/Projects/robot_demo_001` dirty 文件，也不覆盖 ai-station 的未跟踪实验账本。

---

## 文件边界

- `src/so101_demo_py/src/core/detection.py`：不可变 detection/localization 数据契约和错误码。
- `src/so101_demo_py/src/ports/object_detector.py`：模型无关 `DetectorPort`。
- `src/so101_demo_py/src/application/object_pose.py`：目标选择、mask RGB-D 定位、一次请求的 fail-closed 编排。
- `src/so101_demo_py/src/adapters/perception/yolo_seg.py`：权重校验、device 选择、YOLO 结果转换和真实 adapter。
- `src/so101_demo_py/src/runtime/perception_evidence.py`：原子写入 PNG/JSON/PLY 与 result manifest。
- `src/so101_demo_py/src/ros/rgbd_object_pose_node.py`：新鲜帧门禁、tf2、ROS detections/overlay/pose publisher 和 cleanup。
- `src/so101_demo_py/src/cli/rgbd_object_pose.py`：standalone `--once` CLI。
- `src/so101_demo_py/src/adapters/perception/mujoco_dataset.py`：同 camera pose 的 RGB/object-ID 渲染和 YOLO polygon 标签。
- `src/so101_demo_py/src/cli/generate_yolo_seg_dataset.py`：1200 样本数据集入口和 manifest。
- `src/so101_demo_py/assets/mujoco/v5_multi_object_scene.xml`：瓶子、一个杯子、两个杯子和相邻物体 fixture。
- `src/so101_demo_py/config/perception/plastic_cup_yolo_seg.yaml`：冻结的类别、推理、几何和训练参数。
- `src/so101_demo_py/config/perception/requirements.lock`：双平台 smoke test 后确定的 Python 依赖版本。
- `src/so101_demo_py/launch/so101_mujoco_perception_pick_place.launch.py` 与 `src/so101_demo_py/src/runtime/launch_composition.py`：显式 `perception_backend` 和 YOLO 参数接线。
- `src/so101_demo_py/setup.py`、`src/so101_demo_py/package.xml`：CLI、资源和 `vision_msgs` 依赖。
- `src/so101_demo_py/test/test_detection_contracts.py`、`test_target_selector.py`、`test_rgbd_localizer.py`、`test_yolo_seg_adapter.py`、`test_rgbd_object_pose.py`、`test_yolo_seg_dataset.py`：RED -> GREEN 自动回归。
- `docs/experiments/v5-t004-yolo-seg-rgbd-experiment-ledger.md`：跨平台实验状态、provenance、连续成功和证据索引。

### Task 1: Detection 契约与目标选择

**Files:**
- Create: `src/so101_demo_py/src/core/detection.py`
- Create: `src/so101_demo_py/src/ports/object_detector.py`
- Create: `src/so101_demo_py/test/test_detection_contracts.py`
- Create: `src/so101_demo_py/test/test_target_selector.py`
- Modify: `src/so101_demo_py/src/core/__init__.py`
- Modify: `src/so101_demo_py/src/ports/__init__.py`

**Interfaces:**
- Produces: `DetectionFrame(rgb8, source_stamp_ns, source_frame_id)`、`DetectionQuery(class_id)`、`DetectionCandidate(instance_id, class_id, confidence, bbox_xyxy, mask, source_stamp_ns, source_frame_id)`、`DetectionBatch(model_id, weights_sha256, runtime_device, inference_latency_ms, image_width, image_height, candidates)`、`DetectorPort.detect(frame, query)`、`TargetSelector.select(batch, query, confidence_threshold)`。

- [x] **Step 1: 写 candidate/batch 的失败测试**

```python
def test_candidate_rejects_mask_with_wrong_image_shape() -> None:
    with pytest.raises(ValueError, match="mask shape"):
        DetectionCandidate(
            instance_id="cup-0",
            class_id="plastic_cup",
            confidence=0.9,
            bbox_xyxy=(10.0, 20.0, 30.0, 40.0),
            mask=np.ones((20, 20), dtype=bool),
            source_stamp_ns=7,
            source_frame_id="task_camera_frame",
            image_width=640,
            image_height=480,
        )
```

- [x] **Step 2: 运行 RED 测试**

Run: `PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_detection_contracts.py -q`

Expected: collection fails because `so101_demo.core.detection` does not exist.

- [x] **Step 3: 实现不可变契约和 `DetectorPort`**

Implement dataclasses with array copies marked read-only. Validate finite confidence in `[0, 1]`, non-empty identifiers, nonzero stamp, positive image size, in-bounds positive-area bbox, boolean full-resolution mask, unique `instance_id`, 64-character lowercase SHA256, actual device in `{"cuda", "mps", "cpu"}`, and finite nonnegative latency.

- [x] **Step 4: 运行 contracts GREEN**

Run: same command as Step 2.

Expected: all collected tests pass.

- [x] **Step 5: 写 0/1/2+ 选择器 RED 测试**

```python
@pytest.mark.parametrize(
    ("matching", "failure"),
    [(0, "TARGET_NOT_FOUND"), (2, "TARGET_AMBIGUOUS")],
)
def test_selector_fails_closed_for_zero_or_multiple_matching_candidates(
    matching: int, failure: str
) -> None:
    batch = detection_batch(plastic_cup_count=matching)
    with pytest.raises(TargetSelectionError, match=failure):
        TargetSelector().select(batch, DetectionQuery("plastic_cup"), 0.50)
```

- [x] **Step 6: 运行 selector RED，随后实现最小选择器并跑 GREEN**

Run: `PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_target_selector.py -q`

Expected RED: import or missing selector failure. Expected GREEN: 0/1/2+、低置信度过滤和非目标类别测试全部通过。

- [x] **Step 7: 提交本任务**

```bash
git add src/so101_demo_py/src/core/detection.py src/so101_demo_py/src/core/__init__.py src/so101_demo_py/src/ports/object_detector.py src/so101_demo_py/src/ports/__init__.py src/so101_demo_py/test/test_detection_contracts.py src/so101_demo_py/test/test_target_selector.py
git commit -m "feat(perception): add detection contracts and target selector"
```

### Task 2: 权重、device 门禁与 YOLO adapter

**Files:**
- Create: `src/so101_demo_py/src/adapters/perception/__init__.py`
- Create: `src/so101_demo_py/src/adapters/perception/yolo_seg.py`
- Create: `src/so101_demo_py/test/test_yolo_seg_adapter.py`

**Interfaces:**
- Consumes: `DetectionFrame`、`DetectionQuery`、`DetectionCandidate`、`DetectionBatch`。
- Produces: `verify_weights(path, expected_sha256) -> str`、`select_runtime_device(requested, allow_cpu_fallback, torch_api) -> str`、`convert_yolo_result(...) -> DetectionBatch`、`YoloSegDetector.detect(...)`。

- [x] **Step 1: 写 hash/device/转换 RED 测试**

```python
def test_explicit_mps_does_not_fall_back_to_cpu() -> None:
    torch_api = fake_torch(mps_available=False, cuda_available=False)
    with pytest.raises(ModelSetupError, match="DEVICE_UNAVAILABLE"):
        select_runtime_device("mps", False, torch_api)

def test_converter_preserves_two_instance_masks() -> None:
    batch = convert_yolo_result(fake_two_cup_result(), frame(), provenance())
    assert [candidate.instance_id for candidate in batch.candidates] == ["0", "1"]
    assert all(candidate.mask.shape == (480, 640) for candidate in batch.candidates)
```

- [x] **Step 2: 运行 RED 测试**

Run: `PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_yolo_seg_adapter.py -q`

Expected: missing adapter module.

- [x] **Step 3: 实现 setup 与纯转换边界**

`verify_weights` must reject non-regular files and mismatched SHA256. `select_runtime_device` must implement exact `auto|cuda|mps|cpu` semantics from the spec. `convert_yolo_result` must reject mismatched box/class/confidence/mask counts, empty masks, non-finite confidence, unknown class indices, and out-of-bounds boxes; mask resize uses nearest-neighbor semantics.

- [x] **Step 4: 实现延迟导入的 `YoloSegDetector`**

Import `torch` and `ultralytics` only in construction. Load local weights with downloads disabled by requiring the file to exist before `YOLO(path)`. Warm up one zero RGB frame at `imgsz=640`. Record the device returned by the adapter, measured warm-up/cold-start time, per-call inference time, model ID, and weight hash.

- [x] **Step 5: 运行 GREEN 与 import-boundary 回归**

Run: `PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_yolo_seg_adapter.py src/so101_demo_py/test/test_core_import_boundaries.py -q`

Expected: all tests pass without importing Torch in the ordinary unit-test process.

- [x] **Step 6: 提交本任务**

```bash
git add src/so101_demo_py/src/adapters/perception src/so101_demo_py/test/test_yolo_seg_adapter.py
git commit -m "feat(perception): add fail-closed YOLO-Seg adapter"
```

### Task 3: mask 驱动的 RGB-D 定位

**Files:**
- Create: `src/so101_demo_py/src/application/object_pose.py`
- Create: `src/so101_demo_py/test/test_rgbd_localizer.py`
- Modify: `src/so101_demo_py/src/cli/rgbd_point_cloud.py`
- Modify: `src/so101_demo_py/src/cli/rgbd_cup_pose.py`

**Interfaces:**
- Consumes: unique `DetectionCandidate`、aligned CameraInfo/RGB/Depth、exact-stamp transform lookup。
- Produces: `MaskPointCloud`、`LocalizedObject`、`RgbdLocalizer.localize(candidate, camera_info, depth_message, lookup_transform)`。

- [x] **Step 1: 写 mask 反投影、尺寸/stamp、几何 RED 测试**

```python
def test_localizer_back_projects_only_valid_depth_inside_selected_mask() -> None:
    localized = localizer().localize(
        candidate=single_pixel_mask(rows=[100, 100], columns=[200, 201]),
        camera_info=camera_info(fx=500.0, fy=500.0, cx=320.0, cy=240.0),
        depth_message=depth(values={(100, 200): 0.5, (100, 201): float("nan")}),
        lookup_transform=identity_transform,
    )
    assert localized.valid_depth_point_count == 1
```

- [x] **Step 2: 运行 RED**

Run: `PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_rgbd_localizer.py -q`

Expected: missing `RgbdLocalizer`.

- [x] **Step 3: 抽取 mask point-cloud helper**

Add a pure `build_mask_point_cloud` path that reuses `_decode_depth`, camera intrinsics and `back_project_depth`, but never calls `orange_cup_mask` or cross-object `largest_cluster_indices`. Keep the legacy color path unchanged.

- [x] **Step 4: 实现 instance 内离群点清理和 world 几何门禁**

Run DBSCAN only inside the selected mask, retain the cluster whose median is nearest the full mask-cloud median, transform at `source_stamp_ns`, fit the upright radius in world coordinates, validate point count/radius/workspace, and return `LocalizedObject`. Map failures to `MASK_INVALID`、`DEPTH_INVALID`、`GEOMETRY_REJECTED`、`TF_UNAVAILABLE`.

- [x] **Step 5: 运行 GREEN 和 legacy 回归**

Run: `PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_rgbd_localizer.py src/so101_demo_py/test/test_rgbd_point_cloud.py src/so101_demo_py/test/test_rgbd_cup_pose.py -q`

Expected: new and legacy paths pass; color baseline remains available.

- [x] **Step 6: 提交本任务**

```bash
git add src/so101_demo_py/src/application/object_pose.py src/so101_demo_py/src/cli/rgbd_point_cloud.py src/so101_demo_py/src/cli/rgbd_cup_pose.py src/so101_demo_py/test/test_rgbd_localizer.py
git commit -m "feat(perception): localize selected masks in aligned RGB-D"
```

### Task 4: 一次请求、证据工件与 fail-closed 编排

**Files:**
- Create: `src/so101_demo_py/src/runtime/perception_evidence.py`
- Create: `src/so101_demo_py/test/test_rgbd_object_pose.py`
- Modify: `src/so101_demo_py/src/application/object_pose.py`

**Interfaces:**
- Produces: `ObjectPoseRequest`、`ObjectPoseResult`、`detect_once(request, detector, selector, localizer, evidence_writer, publisher)`、`PerceptionEvidenceWriter.write(...)`。

- [x] **Step 1: 写 fake detector 全流 RED 测试**

```python
def test_ambiguous_result_writes_candidates_but_never_localizes_or_publishes(tmp_path) -> None:
    calls = call_log()
    result = detect_once(
        request=request(tmp_path),
        detector=fake_detector(two_cups()),
        selector=TargetSelector(),
        localizer=fake_localizer(calls),
        evidence_writer=real_writer(tmp_path),
        publisher=fake_publisher(calls),
    )
    assert result.failure == "TARGET_AMBIGUOUS"
    assert calls == []
    assert (tmp_path / "source-rgb.png").is_file()
    assert (tmp_path / "detections.json").is_file()
    assert not (tmp_path / "selected-mask.png").exists()
```

- [x] **Step 2: 运行 RED，随后实现状态机**

Run: `PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_rgbd_object_pose.py -q`

`detect_once` must stop at the first failed boundary, never call downstream dependencies after a failure, and only invoke the pose publisher after evidence files have been fsynced and atomically renamed.

- [x] **Step 3: 实现证据 writer**

Write `source-rgb.png`、`prediction-overlay.png`、`detections.json`、conditional `selected-mask.png`、conditional `selected-cloud.ply` and `result.json`. Temporary files use `.<name>.<request_id>.tmp` in the same directory and `os.replace`. `EVIDENCE_WRITE_FAILED` prevents publishing; cleanup failure replaces success with `CLEANUP_FAILED`.

- [x] **Step 4: 跑错误矩阵 GREEN**

Run: same command as Step 2.

Expected: every spec error code has a test asserting no stale/default pose publication.

- [x] **Step 5: 提交本任务**

```bash
git add src/so101_demo_py/src/application/object_pose.py src/so101_demo_py/src/runtime/perception_evidence.py src/so101_demo_py/test/test_rgbd_object_pose.py
git commit -m "feat(perception): add one-shot evidence-gated application flow"
```

### Task 5: ROS 节点、CLI 与 launch/package 集成

**Files:**
- Create: `src/so101_demo_py/src/ros/rgbd_object_pose_node.py`
- Create: `src/so101_demo_py/src/cli/rgbd_object_pose.py`
- Modify: `src/so101_demo_py/src/runtime/launch_composition.py`
- Modify: `src/so101_demo_py/launch/so101_mujoco_perception_pick_place.launch.py`
- Modify: `src/so101_demo_py/setup.py`
- Modify: `src/so101_demo_py/package.xml`
- Modify: `src/so101_demo_py/test/test_perception_pick_place_launch.py`
- Modify: `src/so101_demo_py/test/test_src_layout.py`

**Interfaces:**
- Produces: console script `rgbd_object_pose` and launch parameter `perception_backend:=color_geometry|yolo_seg`。

- [x] **Step 1: 写 CLI/ROS/launch RED tests**

Assert absolute `--weights` and `--evidence-root`; exact SHA; `--once`; `--device`; CPU fallback semantics; detection/overlay/cup topics; request-fresh frame gate; one `/cup_pose` publisher; yolo node receives the weight/device/evidence parameters.

- [x] **Step 2: 运行 RED**

Run: `PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_rgbd_object_pose.py src/so101_demo_py/test/test_perception_pick_place_launch.py src/so101_demo_py/test/test_src_layout.py -q`

Expected: entry point and launch backend tests fail.

- [x] **Step 3: 实现 ROS lifecycle**

Validate model/device/hash before creating subscriptions. After `READY`, freeze `request_started_monotonic_ns` and `minimum_source_stamp_ns`, discard cached frames, consume the first aligned triplet newer than the request, run one request, publish `vision_msgs/msg/Detection2DArray` and overlay even for ambiguity, publish PoseStamped only for success, destroy subscriptions/publishers/listener/node, and return 0 only for localized success.

- [x] **Step 4: 接入 launch 与 package**

Keep `rgbd_cup_pose` for `color_geometry`. For `yolo_seg`, start exactly one `rgbd_object_pose`. Add `vision_msgs` to `package.xml`, add the console script in `setup.py`, and keep Torch/Ultralytics lazy so package import works without model dependencies.

- [x] **Step 5: 运行 GREEN**

Run: same command as Step 2.

Expected: launch selects one backend and creates one `/cup_pose` publisher.

- [x] **Step 6: 提交本任务**

```bash
git add src/so101_demo_py/src/ros/rgbd_object_pose_node.py src/so101_demo_py/src/cli/rgbd_object_pose.py src/so101_demo_py/src/runtime/launch_composition.py src/so101_demo_py/launch/so101_mujoco_perception_pick_place.launch.py src/so101_demo_py/setup.py src/so101_demo_py/package.xml src/so101_demo_py/test/test_rgbd_object_pose.py src/so101_demo_py/test/test_perception_pick_place_launch.py src/so101_demo_py/test/test_src_layout.py
git commit -m "feat(perception): expose YOLO RGB-D object pose node"
```

### Task 6: MuJoCo 多物体 fixture 与可复现数据集

**Files:**
- Create: `src/so101_demo_py/src/adapters/perception/mujoco_dataset.py`
- Create: `src/so101_demo_py/src/cli/generate_yolo_seg_dataset.py`
- Create: `src/so101_demo_py/assets/mujoco/v5_multi_object_scene.xml`
- Create: `src/so101_demo_py/config/perception/plastic_cup_yolo_seg.yaml`
- Create: `src/so101_demo_py/test/test_yolo_seg_dataset.py`
- Modify: `src/so101_demo_py/setup.py`

**Interfaces:**
- Produces: `DatasetScenario`、`render_labeled_sample(model, camera, seed, scenario)`、`generate_dataset(config, output_root)`、console script `generate_yolo_seg_dataset`。

- [x] **Step 1: 写 seed/split/object-ID RED 测试**

```python
def test_material_color_is_not_used_to_build_labels() -> None:
    sample_a = render_with_truth_ids(cup_rgba=(1, 0.4, 0, 1))
    sample_b = render_with_truth_ids(cup_rgba=(0, 0, 1, 1))
    assert polygons(sample_a) == polygons(sample_b)
```

Also assert deterministic manifests, disjoint seed sets, 0/1/2 cup counts, image/mask dimensions, and normalized polygon coordinates.

- [x] **Step 2: 运行 RED**

Run: `PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_yolo_seg_dataset.py -q`

Expected: missing dataset module.

- [x] **Step 3: 实现 fixture 与 Python MuJoCo renderer**

The fixture names truth bodies `plastic_cup_a` and `plastic_cup_b`, plus non-target `orange_bottle` and neutral distractors. Render RGB and object-ID segmentation from the same `task_camera` pose without stepping between renders. Map geom IDs through `model.geom_bodyid` to target body IDs and convert each visible connected instance mask to a clipped polygon.

- [x] **Step 4: 实现 800/200/200 数据集和 manifest**

Use fixed disjoint seed ranges `train=100000..100799`、`val=200000..200199`、`test=300000..300199`. Write `dataset.yaml`、`dataset-manifest.json`、YOLO images/labels and per-sample truth JSON. Manifest records generator commit, MJCF SHA256, counts, seed ranges and class instance totals.

- [x] **Step 5: 运行 GREEN 与 12 样本 smoke generation**

Run: `PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_yolo_seg_dataset.py -q`

Run after MuJoCo install: `ros2 run so101_demo_py generate_yolo_seg_dataset --config <share>/config/perception/plastic_cup_yolo_seg.yaml --output-root <evidence-root>/dataset-smoke --sample-limit 12`

Expected: 12 RGB files, 12 label files, manifest count 12, no overlapping seeds.

- [x] **Step 6: 提交本任务**

```bash
git add src/so101_demo_py/src/adapters/perception/mujoco_dataset.py src/so101_demo_py/src/cli/generate_yolo_seg_dataset.py src/so101_demo_py/assets/mujoco/v5_multi_object_scene.xml src/so101_demo_py/config/perception/plastic_cup_yolo_seg.yaml src/so101_demo_py/test/test_yolo_seg_dataset.py src/so101_demo_py/setup.py
git commit -m "feat(perception): generate object-ID YOLO-Seg training data"
```

### Task 7: 依赖锁、训练与真实模型 smoke

**Files:**
- Create: `src/so101_demo_py/config/perception/requirements.lock`
- Create: `src/so101_demo_py/config/perception/training.yaml`
- Create: `src/so101_demo_py/test/test_perception_dependency_lock.py`
- Evidence only: `dataset-manifest.json`、`dataset.yaml`、`training-config.yaml`、`best.pt`、`metrics.json`、`weights.sha256`。

**Interfaces:**
- Produces: identical `best.pt` and SHA256 for both platforms.

- [x] **Step 1: 写依赖锁 contract RED 测试**

Assert exact pins for `torch`、`torchvision`、`ultralytics`、`mujoco`; reject ranges and duplicate packages; assert config references `yolo11n-seg.pt`, `imgsz=640`, one class `plastic_cup`, and recorded seed.

- [x] **Step 2: 迁移证据根到持久存储**

Freeze the local development root, write a relative-path manifest containing SHA256 and byte size, copy it to `/data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/`, compare file count/hash/size, then update the ledger header and every tracked absolute path. Do not delete the source root.

- [x] **Step 3: 在隔离环境安装并做双平台 smoke**

Install the same pinned application versions in platform-specific virtual environments. Record `python --version`, package versions, `torch.backends.mps.is_available()` on Mac and `torch.cuda.is_available()` plus GPU name on Linux. No runtime command may install packages.

- [x] **Step 4: 修复 Linux CUDA 前置条件**

After coordinating the shared host, make the loaded NVIDIA kernel module and user-space library versions match. Gate command: `nvidia-smi` exits 0 and the chosen Linux Python prints `torch.cuda.is_available() == True`. Do not train before this gate.

- [x] **Step 5: 生成 1200 张数据并训练**

Generate exactly 800/200/200 samples under the registered evidence root, validate the manifest, and train on ai-station CUDA from local `yolo11n-seg.pt`. Save the full training config, metrics, `best.pt`, and `sha256sum best.pt`.

- [x] **Step 6: 两平台真实权重 smoke**

Run one fixed test image on Linux `cuda` and Mac `mps`, asserting the expected candidate count, class `plastic_cup`, non-empty mask, same weights SHA256, and actual runtime device. Copy Mac result artifacts to `<evidence-root>/platform-smoke/macos/` with hash manifest.

- [x] **Step 7: 运行 package tests 并提交可提交配置**

Mac direct pytest gate:

```zsh
PYTHONNOUSERSITE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test -q --junitxml=<mac-staging>/so101_demo_py-pytest.xml
```

Linux gate:

```zsh
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_moveit/install/setup.zsh
PYTHONNOUSERSITE=1 colcon test --packages-select so101_demo_py --event-handlers console_direct+
colcon test-result --verbose
```

Commit only dependency/config/tests; model and large dataset remain in evidence storage.

### Task 8: 双平台四场景感知验收

**Files:**
- Modify: `docs/experiments/v5-t004-yolo-seg-rgbd-experiment-ledger.md`
- Evidence only: per-platform/per-scenario run directories.

**Interfaces:**
- Consumes: installed package, `best.pt`, four fixture keyframes, real ROS topics.
- Produces: 8 valid perception experiments and cleanup reports.

- [x] **Step 1: 为 8 次运行预登记实验**

Create separate `PLANNED` entries for `macos|linux x bottle_only|one_cup_distractors|two_cups|cup_adjacent_bottle`. Freeze commit, weight hash, parameters, `FULL_RESTART`, ROS_DOMAIN_ID, GZ_PARTITION and pass/fail/invalid criteria before launching.

- [x] **Step 2: 每次验证 RGB-D payload 与 installed provenance**

Record package prefix/executable, installed file timestamp, 640x480 `rgb8`/`32FC1` payload, nonzero equal stamp, frame IDs, finite positive depth, weight hash and actual device.

- [x] **Step 3: 执行四场景并核对 truth**

For each platform, assert expected not-found/unique/ambiguous/adjacent behavior, no pose in 0/2 scenarios, IoU `>= 0.80`, unique-cup position error `< 0.01 m`, and request latency `<= 2000 ms`. Save all six request artifacts where applicable.

- [x] **Step 4: 视觉与 cleanup 验收**

Use project `gui-capture` routing for fresh exact-window/desktop evidence. Inspect the overlay itself, name the detected instances and visible mask separation, then prove zero owned inference processes and exactly zero or one `/cup_pose` publisher according to process state.

- [x] **Step 5: 落账并冻结结论**

Each run transitions `PLANNED -> RUNNING -> VALID|INVALID` with command exit code and evidence paths. Do not count invalid environment runs.

### Task 9: 双平台 MuJoCo pick&place 闭环

**Files:**
- Modify: `docs/experiments/v5-t004-yolo-seg-rgbd-experiment-ledger.md`
- Modify only if contract test proves necessary: `src/so101_demo_py/src/runtime/launch_composition.py`
- Modify only if contract test proves necessary: `src/so101_demo_py/test/test_perception_pick_place_launch.py`

**Interfaces:**
- Consumes: unique `plastic_cup` scene result and fresh `/cup_pose` from `yolo_seg` backend.
- Produces: one valid macOS and one valid Linux physical-simulation pick&place result, then a five-run stability batch per platform if the first run passes.

- [x] **Step 1: 先做 launch contract RED/GREEN**

Prove the existing integrated launch starts the yolo perception node before dynamic execution, waits for a fresh pose with source stamp/request provenance, keeps a single pose publisher, and propagates perception nonzero exit without moving the arm. Add the smallest launch patch only if this test is RED.

- [x] **Step 2: 为 macOS 与 Linux 首次 execute 预登记实验**

Use the one-cup-with-distractors scene, `run_mode:=execute`, explicit execution authorization, unique ROS/Gazebo isolation and `FULL_RESTART`. The failure boundary is the first differing layer among perception, MoveIt, controller/joint/TF, MuJoCo attachment, Planning Scene, release and final placement.

- [x] **Step 3: 执行首次双平台 pick&place**

Require fresh YOLO `/cup_pose`; MoveIt planning and execute success; joint/TCP motion; MuJoCo cup attach, transport, release and stable final pose; MoveIt attached/world synchronization; no support-free auto-open; clean owned-process shutdown; and a fresh GUI frame showing the final cup in the target region.

- [x] **Step 4: 执行每平台连续五次稳定性批次**

After the first valid run, pre-register five `FULL_RESTART` experiments per platform at fixed commit, weight hash and parameters. A valid failure breaks the sequence; an invalid run ends the batch and starts new experiment IDs after contamination is removed.

- [x] **Step 5: 完成账本 checkpoint**

Record retained evidence, archived evidence, deletion candidates, preserved user processes/files, exact source/install/runtime provenance and next command. No evidence is deleted.

### Task 10: 完成前总验证与学习边界

**Files:**
- Modify: `docs/experiments/v5-t004-yolo-seg-rgbd-experiment-ledger.md`
- Optional after user exercise: `learners/zjumty/sessions/<new-session-file>.md`
- Optional after user acceptance: `learners/zjumty/progress.yaml`

- [x] **Step 1: fresh package verification**

Run focused tests, full `so101_demo_py` package tests, build/install checks, `ros2 pkg prefix`, `ros2 pkg executables`, installed entry-point/hash checks and `git diff --check`. Record actual counts and exit codes.

- [x] **Step 2: requirements trace**

Map every design completion condition to a test, model artifact, platform experiment or explicit user-learning gate. Missing evidence remains open; tests do not substitute for runtime.

- [ ] **Step 3: 用户最小学习验收**

Ask the user to explain four boundaries: instance mask versus bbox/color; mask depth back-projection; 0/1/2+ target selection; exact-stamp tf2. Do not mark `V5-T004=mastered` until the user passes this check, even if software and runtime are complete.

- [x] **Step 4: final report**

Report first bad boundary if any, RED/GREEN evidence, macOS/Linux model device and hash, four-scene results, pick&place physical-simulation layers, fresh screenshots, cleanup, preserved user changes, retained/archived/deletion-candidate evidence and the next exact command for every unpassed gate.
