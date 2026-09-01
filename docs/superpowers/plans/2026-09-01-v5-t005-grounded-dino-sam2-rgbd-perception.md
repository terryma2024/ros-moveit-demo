# V5-T005 Grounding DINO Tiny + SAM 2.1 RGB-D 多实例感知实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 macOS Apple Silicon 与 ai-station Linux 上，用同一份本地双模型包完成 Grounding DINO Tiny 候选检测、SAM 2.1 Hiera Tiny 实例分割、唯一 `plastic_cup` 选择、RGB-D 定位和 `/cup_pose` 发布，并让两个平台分别连续完成 5 次 MuJoCo pick&place。

**Architecture:** 新的 `GroundedSamDetector` 继续实现 `DetectorPort`，只读取 RGB。`DetectorFactory` 在 YOLO 与 Grounded SAM 之间选择 adapter；现有 `TargetSelector`、`RgbdLocalizer` 和 `/cup_pose` 发布路径不增加模型专用分支。两个 Hugging Face snapshot 由一个 SHA 校验的本地 bundle 管理，运行时使用 `local_files_only=True`，SAM 质量分只进入 mask 门禁和证据。

**Tech Stack:** Python、ROS 2 Jazzy、NumPy、PyTorch、Hugging Face Transformers、Grounding DINO Tiny、SAM 2.1 Hiera Tiny、MPS、CUDA、pytest、MuJoCo、MoveIt、vision_msgs。

**Spec:** `docs/superpowers/specs/2026-09-01-v5-t005-grounded-dino-sam2-rgbd-perception-design.md`

## Global Constraints

- 固定模型为 `IDEA-Research/grounding-dino-tiny` revision `a2bb814dd30d776dcf7e30523b00659f4f141c71` 与 `facebook/sam2.1-hiera-tiny` revision `de431c4043854a71d8101e17995dfe596bf101a5`。
- 首版使用 Transformers 进程内、逐帧无状态推理；不启用 SAM 2.1 视频跟踪。
- 两个模型必须运行在同一设备上。macOS 正式验收使用 `mps`，ai-station 使用 `cuda`；`perception_allow_cpu_fallback` 默认是 `false`。
- 首版固定 FP32，关闭 `torch.compile`、BF16、FP16、量化和模型拆分。
- 生产 detector 只读取 RGB。MuJoCo object ID、truth pose、颜色阈值和最大点云簇只能用于数据或验收，不能进入候选生成与目标选择。
- 受控映射固定为 `plastic_cup -> "plastic cup."`。CLI 与自然语言不能直接提供任意 prompt。
- `DetectionCandidate.confidence` 保存 Grounding DINO score；可选 `segmentation_quality` 保存 SAM predicted IoU。`TargetSelector` 只按规范类别和 confidence 工作。
- 0 个匹配候选返回 `TARGET_NOT_FOUND`，1 个进入定位，2 个及以上返回 `TARGET_AMBIGUOUS`；不能用最高分、面积或距离打破歧义。
- `/cup_pose` 只在唯一目标、mask、Depth、几何门禁和 exact-stamp tf2 全部通过后发布。失败时不发布默认 pose，也不复用旧 pose。
- 初始阈值为 `box=0.35`、`text=0.25`、`duplicate_iou=0.85`、`max_candidates=16`、`sam_quality=0.75`、`min_mask_pixels=64`、`max_mask_area_ratio=0.50`。
- 两平台正式门槛为 warmed request latency `<= 2000 ms`、truth mask IoU `>= 0.80`、唯一杯子 world position error `< 0.01 m`。
- 正式证据只写入 `/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869`。普通开发日志使用 `/tmp/so101-debug-v5-t005-grounded-sam-20260901`；不得创建第二个原始证据根。
- 不删除既有 V5-T004 证据、失败批次或其他用户文件。完成时分别报告 retained、archived 和 deletion candidates。
- 当前 linked worktree 的共享 `core.worktree` 会误导普通 Git 命令。Mac 上的 Git 写操作必须显式使用 `--git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo`，不得修改共享 Git 配置。

---

## 文件边界

- `src/so101_demo_py/src/adapters/perception/model_runtime.py`：模型 setup 错误和跨 adapter 设备选择。
- `src/so101_demo_py/src/adapters/perception/model_bundle.py`：双模型 manifest 解析、文件集合与 SHA 校验。
- `src/so101_demo_py/src/adapters/perception/grounded_sam_postprocess.py`：纯 NumPy prompt、候选框去重、SAM mask 选择和候选转换。
- `src/so101_demo_py/src/adapters/perception/grounded_sam.py`：Transformers 模型加载、warm-up 与逐帧推理。
- `src/so101_demo_py/src/adapters/perception/detector_factory.py`：后端专用参数校验和 detector 构造。
- `src/so101_demo_py/src/adapters/perception/yolo_seg.py`：继续提供 YOLO adapter，改用共享 model runtime。
- `src/so101_demo_py/src/core/detection.py`：给 `DetectionCandidate` 增加可选的模型无关 `segmentation_quality`。
- `src/so101_demo_py/src/runtime/perception_evidence.py`：记录 SAM 质量与双模型 provenance。
- `src/so101_demo_py/src/ros/rgbd_object_pose_node.py`：backend-neutral options、factory 接线和现有 ROS 生命周期。
- `src/so101_demo_py/src/cli/rgbd_object_pose.py`：后端互斥 CLI 参数。
- `src/so101_demo_py/src/runtime/launch_composition.py`：`grounded_sam` launch 参数和进程参数接线。
- `src/so101_demo_py/src/cli/prepare_grounded_sam_bundle.py`：按固定 revision 生成不可覆盖的本地模型包。
- `src/so101_demo_py/config/perception/grounded_sam.yaml`：固定模型、prompt profile 和初始阈值。
- `src/so101_demo_py/config/perception/requirements.lock`：精确依赖锁。
- `src/so101_demo_py/setup.py`：模型包 preparation CLI entry point。
- `src/so101_demo_py/test/test_model_runtime.py`：共享 setup/device 契约。
- `src/so101_demo_py/test/test_grounded_sam_config.py`：模型 revision、prompt 与依赖锁契约。
- `src/so101_demo_py/test/test_grounded_sam_bundle.py`：bundle builder/verifier 契约。
- `src/so101_demo_py/test/test_grounded_sam_postprocess.py`：纯候选和 mask 转换测试。
- `src/so101_demo_py/test/test_grounded_sam_adapter.py`：fake Transformers adapter 测试。
- `src/so101_demo_py/test/test_detector_factory.py`：后端构造与互斥配置。
- `src/so101_demo_py/test/test_detection_contracts.py`、`test_rgbd_object_pose.py`、`test_perception_pick_place_launch.py`：核心、CLI/ROS 和 launch 回归。
- `docs/guides/so101-grounded-sam-rgbd-perception-pick-place-source-guide.md`：本地部署、数据流、运行和故障说明。
- `docs/experiments/v5-t005-grounded-sam-rgbd-experiment-ledger.md`：实验状态、provenance 与连续成功记录。

### Task 1: 抽出共享模型运行时

**Files:**
- Create: `src/so101_demo_py/src/adapters/perception/model_runtime.py`
- Create: `src/so101_demo_py/test/test_model_runtime.py`
- Modify: `src/so101_demo_py/src/adapters/perception/yolo_seg.py:23-75`
- Modify: `src/so101_demo_py/test/test_yolo_seg_adapter.py:1-330`

**Interfaces:**
- Produces: `RequestedDevice = Literal["auto", "cuda", "mps", "cpu"]`。
- Produces: `ModelSetupError(code: str, detail: str)`，公开只读 `code` 和 `detail`。
- Produces: `select_runtime_device(requested: str, allow_cpu_fallback: bool, torch_api: Any) -> RuntimeDevice`。
- Preserves: `from so101_demo.adapters.perception.yolo_seg import ModelSetupError, select_runtime_device` 继续可用。

- [ ] **Step 1: 写共享 runtime 的 RED 测试**

```python
def test_auto_prefers_cuda_then_mps_and_requires_cpu_authorization() -> None:
    assert select_runtime_device("auto", False, fake_torch(cuda=True, mps=True)) == "cuda"
    assert select_runtime_device("auto", False, fake_torch(cuda=False, mps=True)) == "mps"
    with pytest.raises(ModelSetupError, match="DEVICE_UNAVAILABLE"):
        select_runtime_device("auto", False, fake_torch(cuda=False, mps=False))
    assert select_runtime_device("auto", True, fake_torch(cuda=False, mps=False)) == "cpu"

def test_explicit_accelerator_never_falls_back() -> None:
    with pytest.raises(ModelSetupError, match="requested MPS is unavailable"):
        select_runtime_device("mps", True, fake_torch(cuda=False, mps=False))
```

- [ ] **Step 2: 运行 RED**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_model_runtime.py -q
```

Expected: collection fails because `so101_demo.adapters.perception.model_runtime` does not exist.

- [ ] **Step 3: 移动公共类型和设备逻辑**

```python
RequestedDevice = Literal["auto", "cuda", "mps", "cpu"]

class ModelSetupError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail

def select_runtime_device(requested: str, allow_cpu_fallback: bool, torch_api: Any) -> RuntimeDevice:
    if requested == "cpu":
        return "cpu"
    if requested == "cuda":
        if bool(torch_api.cuda.is_available()):
            return "cuda"
        raise ModelSetupError("DEVICE_UNAVAILABLE", "requested CUDA is unavailable")
    if requested == "mps":
        if bool(torch_api.backends.mps.is_available()):
            return "mps"
        raise ModelSetupError("DEVICE_UNAVAILABLE", "requested MPS is unavailable")
    if requested != "auto":
        raise ModelSetupError("DEVICE_UNAVAILABLE", f"unknown device request: {requested}")
    if bool(torch_api.cuda.is_available()):
        return "cuda"
    if bool(torch_api.backends.mps.is_available()):
        return "mps"
    if allow_cpu_fallback:
        return "cpu"
    raise ModelSetupError(
        "DEVICE_UNAVAILABLE",
        "auto found no accelerator and CPU fallback was not authorized",
    )
```

`yolo_seg.py` 从新模块导入并重新暴露这些名字，不改 YOLO 行为。

- [ ] **Step 4: 跑共享 runtime 和 YOLO 回归**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_model_runtime.py src/so101_demo_py/test/test_yolo_seg_adapter.py -q
```

Expected: both files pass; existing YOLO imports remain valid.

- [ ] **Step 5: 提交**

```bash
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo add -- src/so101_demo_py/src/adapters/perception/model_runtime.py src/so101_demo_py/src/adapters/perception/yolo_seg.py src/so101_demo_py/test/test_model_runtime.py src/so101_demo_py/test/test_yolo_seg_adapter.py
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo commit -m "refactor(perception): share model runtime gates"
```

### Task 2: 增加分割质量证据

**Files:**
- Modify: `src/so101_demo_py/src/core/detection.py:64-104`
- Modify: `src/so101_demo_py/src/runtime/perception_evidence.py:130-205`
- Modify: `src/so101_demo_py/test/test_detection_contracts.py`
- Modify: `src/so101_demo_py/test/test_rgbd_object_pose.py`

**Interfaces:**
- Produces: `DetectionCandidate.segmentation_quality: float | None = None`。
- Produces: candidate JSON field `segmentation_quality`，值为 `float` 或 `null`。
- Preserves: `TargetSelector` 仍只读取 `class_id` 和 `confidence`。

- [ ] **Step 1: 写质量字段 RED 测试**

```python
def test_candidate_accepts_optional_segmentation_quality() -> None:
    candidate = make_candidate(segmentation_quality=0.82)
    assert candidate.segmentation_quality == 0.82
    with pytest.raises(ValueError, match="segmentation_quality"):
        make_candidate(segmentation_quality=float("nan"))
    with pytest.raises(ValueError, match="segmentation_quality"):
        make_candidate(segmentation_quality=1.01)

def test_detection_evidence_records_segmentation_quality(tmp_path: Path) -> None:
    writer = PerceptionEvidenceWriter()
    artifacts = writer.write_detection(request(tmp_path), batch(segmentation_quality=0.82))
    document = json.loads((tmp_path / "detections.json").read_text())
    assert document["candidates"][0]["segmentation_quality"] == 0.82
    assert artifacts
```

- [ ] **Step 2: 运行 RED**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_detection_contracts.py src/so101_demo_py/test/test_rgbd_object_pose.py -q
```

Expected: constructor or JSON assertions fail because the field is absent.

- [ ] **Step 3: 实现可选质量字段和证据输出**

在 dataclass 的默认字段区加入：

```python
segmentation_quality: float | None = None
```

在 `__post_init__` 中执行：

```python
if self.segmentation_quality is not None and (
    not math.isfinite(self.segmentation_quality)
    or not 0.0 <= self.segmentation_quality <= 1.0
):
    raise ValueError("segmentation_quality must be finite and in [0, 1]")
```

`_candidate_document` 始终输出这个字段。overlay 文本在非 `None` 时追加 `sam=<quality:.3f>`，YOLO 保持原显示。

- [ ] **Step 4: 运行 GREEN 和 selector 回归**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_detection_contracts.py src/so101_demo_py/test/test_rgbd_object_pose.py src/so101_demo_py/test/test_target_selector.py src/so101_demo_py/test/test_yolo_seg_adapter.py -q
```

Expected: all pass; YOLO candidate quality serializes as `null` and selection outcome is unchanged.

- [ ] **Step 5: 提交**

```bash
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo add -- src/so101_demo_py/src/core/detection.py src/so101_demo_py/src/runtime/perception_evidence.py src/so101_demo_py/test/test_detection_contracts.py src/so101_demo_py/test/test_rgbd_object_pose.py
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo commit -m "feat(perception): record segmentation quality"
```

### Task 3: 冻结模型来源、提示词和依赖

**Files:**
- Create: `src/so101_demo_py/config/perception/grounded_sam.yaml`
- Create: `src/so101_demo_py/test/test_grounded_sam_config.py`
- Modify: `src/so101_demo_py/config/perception/requirements.lock`
- Modify: `src/so101_demo_py/test/test_perception_dependency_lock.py`

**Interfaces:**
- Produces: schema version 1 model-source document consumed by the bundle preparation CLI。
- Produces: exact prompt profile and inference thresholds used by launch defaults and tests。

- [ ] **Step 1: 写配置 RED 测试**

```python
def test_grounded_sam_config_freezes_models_prompt_and_thresholds() -> None:
    document = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    assert document["schema_version"] == 1
    assert document["pipeline_id"] == "grounding-dino-tiny+sam2.1-hiera-tiny"
    assert document["models"]["detector"] == {
        "model_id": "IDEA-Research/grounding-dino-tiny",
        "revision": "a2bb814dd30d776dcf7e30523b00659f4f141c71",
        "directory": "grounding-dino-tiny",
    }
    assert document["models"]["segmenter"] == {
        "model_id": "facebook/sam2.1-hiera-tiny",
        "revision": "de431c4043854a71d8101e17995dfe596bf101a5",
        "directory": "sam2.1-hiera-tiny",
    }
    assert document["prompts"] == {"plastic_cup": "plastic cup."}
    assert document["thresholds"]["grounding_box"] == 0.35
    assert document["thresholds"]["sam_quality"] == 0.75
```

- [ ] **Step 2: 运行 RED**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_grounded_sam_config.py src/so101_demo_py/test/test_perception_dependency_lock.py -q
```

Expected: config file and new dependency assertions are missing.

- [ ] **Step 3: 写固定配置和依赖锁**

`grounded_sam.yaml` 使用以下完整业务值：

```yaml
schema_version: 1
pipeline_id: grounding-dino-tiny+sam2.1-hiera-tiny
models:
  detector:
    model_id: IDEA-Research/grounding-dino-tiny
    revision: a2bb814dd30d776dcf7e30523b00659f4f141c71
    directory: grounding-dino-tiny
  segmenter:
    model_id: facebook/sam2.1-hiera-tiny
    revision: de431c4043854a71d8101e17995dfe596bf101a5
    directory: sam2.1-hiera-tiny
prompts:
  plastic_cup: "plastic cup."
thresholds:
  grounding_box: 0.35
  grounding_text: 0.25
  duplicate_iou: 0.85
  max_candidates: 16
  sam_quality: 0.75
  min_mask_pixels: 64
  max_mask_area_ratio: 0.50
```

在现有 lock 中保留原包，并加入：

```text
transformers==4.56.2
huggingface-hub==0.34.4
safetensors==0.6.2
tokenizers==0.22.0
```

- [ ] **Step 4: 运行 GREEN**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_grounded_sam_config.py src/so101_demo_py/test/test_perception_dependency_lock.py -q
```

Expected: exact revision, prompt, thresholds and package pins all pass.

- [ ] **Step 5: 提交**

```bash
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo add -- src/so101_demo_py/config/perception/grounded_sam.yaml src/so101_demo_py/config/perception/requirements.lock src/so101_demo_py/test/test_grounded_sam_config.py src/so101_demo_py/test/test_perception_dependency_lock.py
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo commit -m "build(perception): pin Grounded SAM models and dependencies"
```

### Task 4: 构建并校验不可变双模型包

**Files:**
- Create: `src/so101_demo_py/src/adapters/perception/model_bundle.py`
- Create: `src/so101_demo_py/src/cli/prepare_grounded_sam_bundle.py`
- Create: `src/so101_demo_py/test/test_grounded_sam_bundle.py`
- Modify: `src/so101_demo_py/setup.py:47-71`

**Interfaces:**
- Produces: `VerifiedModelBundle(root: Path, manifest_sha256: str, detector_dir: Path, segmenter_dir: Path, manifest: Mapping[str, Any])`。
- Produces: `verify_model_bundle(root: Path, expected_manifest_sha256: str) -> VerifiedModelBundle`。
- Produces: `build_model_bundle(config_path: Path, destination: Path, snapshot_download: Callable[..., str]) -> str`，返回 manifest SHA。
- Produces CLI: `prepare_grounded_sam_bundle --config ABSOLUTE --output ABSOLUTE`。

- [ ] **Step 1: 写 verifier RED 测试**

```python
def test_verify_bundle_checks_manifest_and_every_regular_file(tmp_path: Path) -> None:
    root, digest = fake_bundle(tmp_path)
    bundle = verify_model_bundle(root, digest)
    assert bundle.detector_dir == root / "grounding-dino-tiny"
    assert bundle.segmenter_dir == root / "sam2.1-hiera-tiny"

    (root / "sam2.1-hiera-tiny/model.safetensors").write_bytes(b"changed")
    with pytest.raises(ModelSetupError) as error:
        verify_model_bundle(root, digest)
    assert error.value.code == "MODEL_HASH_MISMATCH"

def test_verify_bundle_rejects_symlink_unlisted_file_and_path_escape(tmp_path: Path) -> None:
    root, digest = fake_bundle(tmp_path)
    (root / "extra.bin").write_bytes(b"extra")
    with pytest.raises(ModelSetupError, match="MODEL_BUNDLE_INVALID"):
        verify_model_bundle(root, digest)
```

- [ ] **Step 2: 运行 verifier RED**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_grounded_sam_bundle.py -q
```

Expected: missing module.

- [ ] **Step 3: 实现 canonical manifest 与 verifier**

清单格式固定为：

```json
{
  "schema_version": 1,
  "pipeline_id": "grounding-dino-tiny+sam2.1-hiera-tiny",
  "prompt_profile": {"plastic_cup": "plastic cup."},
  "models": {
    "detector": {"model_id": "IDEA-Research/grounding-dino-tiny", "revision": "a2bb814dd30d776dcf7e30523b00659f4f141c71", "directory": "grounding-dino-tiny"},
    "segmenter": {"model_id": "facebook/sam2.1-hiera-tiny", "revision": "de431c4043854a71d8101e17995dfe596bf101a5", "directory": "sam2.1-hiera-tiny"}
  },
  "files": [{"path": "grounding-dino-tiny/config.json", "size": 1, "sha256": "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb"}],
  "dependencies": {}
}
```

`manifest.json` 使用 `json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"`。verifier 必须检查绝对 root、普通文件、无路径逃逸、无符号链接、严格文件集合、字节数和 SHA；清单 SHA 不符返回 `MODEL_HASH_MISMATCH`，结构问题返回 `MODEL_BUNDLE_INVALID`。

- [ ] **Step 4: 写 builder CLI RED 测试**

```python
def test_builder_copies_fixed_snapshots_without_symlinks(tmp_path: Path) -> None:
    calls: list[tuple[str, str]] = []
    digest = build_model_bundle(
        config_path=CONFIG_PATH,
        destination=tmp_path / "bundle",
        snapshot_download=fake_snapshot_download(calls),
    )
    assert calls == [
        ("IDEA-Research/grounding-dino-tiny", "a2bb814dd30d776dcf7e30523b00659f4f141c71"),
        ("facebook/sam2.1-hiera-tiny", "de431c4043854a71d8101e17995dfe596bf101a5"),
    ]
    assert verify_model_bundle(tmp_path / "bundle", digest).manifest_sha256 == digest
    assert not any(path.is_symlink() for path in (tmp_path / "bundle").rglob("*"))
```

- [ ] **Step 5: 实现无覆盖 builder 和 entry point**

builder 要求 output 的父目录已存在、output 本身不存在。它在 output 同一文件系统创建 staging，跟随 Hugging Face cache symlink 复制实际文件，跳过 `.cache` 元数据，生成清单，调用自身 verifier，最后用原子 rename 安装。任何失败都删除本轮 staging，但不删除已有 output。

`setup.py` 增加：

```python
"prepare_grounded_sam_bundle = so101_demo.cli.prepare_grounded_sam_bundle:main",
```

- [ ] **Step 6: 运行 bundle GREEN 和 setup 回归**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_grounded_sam_bundle.py src/so101_demo_py/test/test_src_layout.py src/so101_demo_py/test/test_installed_provenance.py -q
```

Expected: verifier, builder, refusal-to-overwrite and entry point tests pass.

- [ ] **Step 7: 提交**

```bash
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo add -- src/so101_demo_py/src/adapters/perception/model_bundle.py src/so101_demo_py/src/cli/prepare_grounded_sam_bundle.py src/so101_demo_py/test/test_grounded_sam_bundle.py src/so101_demo_py/setup.py
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo commit -m "feat(perception): build verified Grounded SAM bundles"
```

### Task 5: 实现纯候选和 mask 后处理

**Files:**
- Create: `src/so101_demo_py/src/adapters/perception/grounded_sam_postprocess.py`
- Create: `src/so101_demo_py/test/test_grounded_sam_postprocess.py`

**Interfaces:**
- Produces: `GroundedSamThresholds(box_threshold, text_threshold, duplicate_iou, max_candidates, sam_quality, min_mask_pixels, max_mask_area_ratio)` 及 `GroundedSamThresholds.defaults()`。
- Produces: `GroundingProposal(bbox_xyxy, confidence)`。
- Produces: `prompt_for_query(query: DetectionQuery) -> str`。
- Produces: `convert_grounding_results(boxes, scores, labels, frame, query, thresholds) -> tuple[GroundingProposal, ...]`。
- Produces: `convert_sam_results(proposals, masks, quality_scores, frame, thresholds) -> tuple[DetectionCandidate, ...]`。
- Produces: `GroundedSamResultError(code: str, detail: str)`。

- [ ] **Step 1: 写 prompt、框和去重 RED 测试**

```python
def test_prompt_is_fixed_and_unknown_query_never_reaches_model() -> None:
    assert prompt_for_query(DetectionQuery("plastic_cup")) == "plastic cup."

def test_grounding_conversion_clips_sorts_and_deduplicates() -> None:
    proposals = convert_grounding_results(
        boxes=np.array([[-1, 10, 31, 50], [0, 10, 30, 50], [80, 10, 120, 50]], dtype=float),
        scores=np.array([0.80, 0.90, 0.70]),
        labels=["plastic cup", "plastic cup", "plastic cup"],
        frame=frame(width=160, height=120),
        query=DetectionQuery("plastic_cup"),
        thresholds=thresholds(duplicate_iou=0.85),
    )
    assert [(proposal.confidence, proposal.bbox_xyxy) for proposal in proposals] == [
        (0.90, (0.0, 10.0, 30.0, 50.0)),
        (0.70, (80.0, 10.0, 120.0, 50.0)),
    ]
```

- [ ] **Step 2: 写 SAM mask RED 测试**

```python
def test_sam_conversion_selects_best_mask_and_preserves_grounding_score() -> None:
    candidates = convert_sam_results(
        proposals=(GroundingProposal((10.0, 10.0, 50.0, 70.0), 0.61),),
        masks=three_masks_for_one_object(),
        quality_scores=np.array([[0.40, 0.91, 0.75]], dtype=float),
        frame=frame(width=160, height=120),
        thresholds=thresholds(sam_quality=0.75),
    )
    assert len(candidates) == 1
    assert candidates[0].confidence == 0.61
    assert candidates[0].segmentation_quality == 0.91
    assert candidates[0].mask.shape == (120, 160)
```

还要覆盖：NaN、框数量超 16、label 不匹配、`masks`/quality 对象数不一致、低质量 mask 被拒绝、少于 64 像素、面积比例超过 0.50、mask 与框交集比例低于 0.80、两个真实杯子不被去重。

- [ ] **Step 3: 运行 RED**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_grounded_sam_postprocess.py -q
```

Expected: missing module.

- [ ] **Step 4: 实现纯 NumPy 后处理**

阈值 dataclass 在 `__post_init__` 校验概率范围、正整数和 `max_mask_area_ratio > 0`。框转换先校验原始候选数量，再裁剪、过滤 label、按固定排序键排序，最后做确定性 IoU 去重。SAM 转换要求输入形状 `(object_count, mask_count, height, width)` 和 `(object_count, mask_count)`；每个对象选最高质量 mask，低质量对象不生成 candidate，结构错误抛 `RESULT_CONTRACT_INVALID`。adapter 以 `MASK_REJECTED` 日志记录被过滤对象的索引、DINO score、SAM quality 和拒绝门槛，该日志进入本轮 ROS evidence。

默认值由一个明确的 classmethod 返回：

```python
@classmethod
def defaults(cls) -> "GroundedSamThresholds":
    return cls(
        box_threshold=0.35,
        text_threshold=0.25,
        duplicate_iou=0.85,
        max_candidates=16,
        sam_quality=0.75,
        min_mask_pixels=64,
        max_mask_area_ratio=0.50,
    )
```

instance ID 在最终列表生成：

```python
instance_id = f"grounded-sam-{index:03d}"
```

- [ ] **Step 5: 运行 GREEN 和核心契约回归**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_grounded_sam_postprocess.py src/so101_demo_py/test/test_detection_contracts.py src/so101_demo_py/test/test_target_selector.py -q
```

Expected: all pass; two-cup input remains two candidates.

- [ ] **Step 6: 提交**

```bash
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo add -- src/so101_demo_py/src/adapters/perception/grounded_sam_postprocess.py src/so101_demo_py/test/test_grounded_sam_postprocess.py
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo commit -m "feat(perception): convert Grounded SAM instances"
```

### Task 6: 实现 Transformers GroundedSamDetector

**Files:**
- Create: `src/so101_demo_py/src/adapters/perception/grounded_sam.py`
- Create: `src/so101_demo_py/test/test_grounded_sam_adapter.py`
- Modify: `src/so101_demo_py/test/test_core_import_boundaries.py`

**Interfaces:**
- Consumes: `VerifiedModelBundle`、`GroundedSamThresholds`、`DetectionFrame`、`DetectionQuery`。
- Produces: `GroundedSamDetector.detect(frame, query) -> DetectionBatch`。
- Produces attributes: `runtime_device: RuntimeDevice`、`cold_start_latency_ms: float`、`model_id = "grounding-dino-tiny+sam2.1-hiera-tiny"`。
- Constructor accepts optional fake loaders and `torch_api` so unit tests never load real weights。

- [ ] **Step 1: 写本地加载和 warm-up RED 测试**

```python
def test_detector_loads_both_local_models_offline_and_warms_them(tmp_path: Path) -> None:
    calls: list[tuple[str, Path, bool]] = []
    detector = GroundedSamDetector(
        bundle=verified_bundle(tmp_path),
        thresholds=GroundedSamThresholds.defaults(),
        requested_device="mps",
        allow_cpu_fallback=False,
        torch_api=fake_torch(mps=True),
        grounding_processor_loader=recording_loader(calls, "grounding-processor"),
        grounding_model_loader=recording_loader(calls, "grounding-model"),
        sam_processor_loader=recording_loader(calls, "sam-processor"),
        sam_model_loader=recording_loader(calls, "sam-model"),
        monotonic_ns=fake_clock(),
    )
    assert all(local_files_only for _kind, _path, local_files_only in calls)
    assert detector.runtime_device == "mps"
    assert detector.cold_start_latency_ms >= 0.0
```

- [ ] **Step 2: 写逐帧检测 RED 测试**

```python
def test_detect_runs_grounding_then_one_batched_sam_call() -> None:
    detector, grounding_model, sam_model = fake_detector(two_boxes=True)
    batch = detector.detect(frame(), DetectionQuery("plastic_cup"))
    assert grounding_model.call_count == 1
    assert sam_model.call_count == 1
    assert sam_model.last_input_boxes.shape == (1, 2, 4)
    assert len(batch.candidates) == 2
    assert batch.model_id == "grounding-dino-tiny+sam2.1-hiera-tiny"
    assert batch.weights_sha256 == "a" * 64

def test_empty_grounding_result_skips_sam_and_returns_empty_batch() -> None:
    detector, _grounding_model, sam_model = fake_detector(two_boxes=False)
    batch = detector.detect(frame(), DetectionQuery("plastic_cup"))
    assert batch.candidates == ()
    assert sam_model.call_count == 0
```

还要断言每次请求都重新执行 Grounding DINO 和 SAM，不保留视频 state；模型输出异常统一带 `INFERENCE_FAILED` 或 `RESULT_CONTRACT_INVALID`。

- [ ] **Step 3: 运行 RED**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_grounded_sam_adapter.py src/so101_demo_py/test/test_core_import_boundaries.py -q
```

Expected: missing adapter module.

- [ ] **Step 4: 实现延迟导入和 FP32 推理**

真实 loader 固定为：

```python
AutoProcessor.from_pretrained(bundle.detector_dir, local_files_only=True)
AutoModelForZeroShotObjectDetection.from_pretrained(
    bundle.detector_dir,
    local_files_only=True,
).to(runtime_device).eval()
Sam2Processor.from_pretrained(bundle.segmenter_dir, local_files_only=True)
Sam2Model.from_pretrained(
    bundle.segmenter_dir,
    local_files_only=True,
).to(runtime_device).eval()
```

推理只使用 `torch_api.inference_mode()`，不使用 autocast 或 compile。Grounding DINO processor 接收 `text="plastic cup."`，后处理传原始图像尺寸、`thresholds.box_threshold` 和 `thresholds.text_threshold`，并读取 `result["boxes"]`、`result["scores"]` 与 `result["text_labels"]`；SAM processor 的 `input_boxes` 是 `[object_count, 4]` 的单图 batch，`multimask_output=True`，随后调用 `post_process_masks` 恢复原分辨率。

warm-up 用一张固定全零 RGB 图和中心框分别走过两个模型。任一模型加载失败包装为 `MODEL_LOAD_FAILED`，warm-up 失败包装为 `WARMUP_FAILED`。

- [ ] **Step 5: 运行 GREEN 和 no-heavy-import 回归**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_grounded_sam_adapter.py src/so101_demo_py/test/test_core_import_boundaries.py -q
```

Expected: fake models pass; importing `core`、`ports` 或 ordinary CLI does not import Torch/Transformers.

- [ ] **Step 6: 提交**

```bash
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo add -- src/so101_demo_py/src/adapters/perception/grounded_sam.py src/so101_demo_py/test/test_grounded_sam_adapter.py src/so101_demo_py/test/test_core_import_boundaries.py
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo commit -m "feat(perception): add Grounded SAM detector"
```

### Task 7: 接入 detector factory、CLI 和 ROS node

**Files:**
- Create: `src/so101_demo_py/src/adapters/perception/detector_factory.py`
- Create: `src/so101_demo_py/test/test_detector_factory.py`
- Modify: `src/so101_demo_py/src/ros/rgbd_object_pose_node.py:1-123,248-273,420-450`
- Modify: `src/so101_demo_py/src/cli/rgbd_object_pose.py:57-138`
- Modify: `src/so101_demo_py/src/runtime/perception_evidence.py`
- Modify: `src/so101_demo_py/test/test_rgbd_object_pose.py:386-470`

**Interfaces:**
- Produces: `DetectorBackend = Literal["yolo_seg", "grounded_sam"]`。
- Produces: `DetectorFactoryOptions(backend, requested_device, allow_cpu_fallback, yolo_weights_path, yolo_weights_sha256, yolo_model_id, yolo_imgsz, grounded_model_root, grounded_manifest_sha256, grounded_thresholds)`；YOLO 字段和 Grounded SAM 字段必须互斥。
- Produces: `BuiltDetector(detector: DetectorPort, cold_start_latency_ms: float, provenance_document: Mapping[str, Any])`。
- Produces: `build_detector(options: DetectorFactoryOptions, *, yolo_detector_factory: Callable[..., DetectorPort] = YoloSegDetector, grounded_detector_factory: Callable[..., DetectorPort] = GroundedSamDetector) -> BuiltDetector`。
- Produces: `RgbdObjectPoseOptions.to_detector_factory_options() -> DetectorFactoryOptions`。
- Extends CLI: `--backend`、`--model-root`、`--model-manifest-sha256` 和七个 Grounded SAM 阈值参数。

- [ ] **Step 1: 写 factory 互斥配置 RED 测试**

```python
def test_factory_builds_grounded_sam_from_verified_bundle(tmp_path: Path) -> None:
    built = build_detector(
        grounded_factory_options(tmp_path),
        grounded_detector_factory=fake_grounded_detector_factory,
    )
    assert isinstance(built.detector, FakeGroundedSamDetector)
    assert built.provenance_document["pipeline_id"] == "grounding-dino-tiny+sam2.1-hiera-tiny"

@pytest.mark.parametrize("backend", ["yolo_seg", "grounded_sam"])
def test_factory_rejects_missing_or_cross_backend_artifacts(backend: str) -> None:
    with pytest.raises(ValueError, match="backend configuration"):
        build_detector(mixed_or_missing_options(backend))
```

- [ ] **Step 2: 运行 factory RED**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_detector_factory.py -q
```

Expected: missing factory module.

- [ ] **Step 3: 实现 factory 和 provenance writer**

`build_detector` 对 `yolo_seg` 调用现有 `verify_weights`/`YoloSegDetector`；对 `grounded_sam` 先调用 `verify_model_bundle`，再构造 `GroundedSamDetector`。`BuiltDetector.provenance_document` 对 Grounded SAM 包含完整 manifest 和 manifest SHA，对 YOLO 保持 model ID 与 weight SHA。

在 `PerceptionEvidenceWriter` 增加：

```python
def write_model_provenance(self, root: Path, document: Mapping[str, object]) -> str:
    path = root / "model-provenance.json"
    if path.exists():
        raise FileExistsError("model provenance path already exists")
    atomic_json(path, document)
    return str(path)
```

- [ ] **Step 4: 写 CLI/options RED 测试**

```python
def test_grounded_sam_cli_constructs_backend_specific_options(tmp_path: Path, monkeypatch) -> None:
    result = rgbd_object_pose.main([
        "--backend", "grounded_sam",
        "--model-root", str(tmp_path / "bundle"),
        "--model-manifest-sha256", "a" * 64,
        "--device", "mps",
        "--request-id", "req-001",
        "--evidence-root", str(tmp_path / "evidence"),
        "--once",
    ])
    assert result == 17
    assert calls[0].backend == "grounded_sam"
    assert calls[0].model_root == tmp_path / "bundle"
    assert calls[0].weights_path is None
```

补充反例：Grounded SAM 缺 model root、YOLO 缺 weights、两类参数同时出现、非法 SHA、阈值越界、相对模型路径。

- [ ] **Step 5: 改造 RgbdObjectPoseOptions 与 run 函数**

`RgbdObjectPoseOptions` 增加 `backend`，将 `weights_path`、`weights_sha256`、`model_root`、`model_manifest_sha256` 设为可选，并在 `__post_init__` 进行 backend-specific 校验。`run_rgbd_object_pose` 不再导入或直接构造 `YoloSegDetector`：

```python
built = build_detector(options.to_detector_factory_options())
detector = built.detector
model_provenance_artifact = PerceptionEvidenceWriter().write_model_provenance(
    options.evidence_root,
    built.provenance_document,
)
```

冷启动证据使用 `built.cold_start_latency_ms + localization_warm_up_ms`。现有帧门禁、publisher、tf2 和 cleanup 不改。

- [ ] **Step 6: 运行 GREEN 与 YOLO CLI 回归**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_detector_factory.py src/so101_demo_py/test/test_rgbd_object_pose.py src/so101_demo_py/test/test_yolo_seg_adapter.py -q
```

Expected: both backends construct correctly; existing YOLO `--weights` path remains accepted.

- [ ] **Step 7: 提交**

```bash
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo add -- src/so101_demo_py/src/adapters/perception/detector_factory.py src/so101_demo_py/src/ros/rgbd_object_pose_node.py src/so101_demo_py/src/cli/rgbd_object_pose.py src/so101_demo_py/src/runtime/perception_evidence.py src/so101_demo_py/test/test_detector_factory.py src/so101_demo_py/test/test_rgbd_object_pose.py
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo commit -m "feat(perception): select detector backends"
```

### Task 8: 接入 MuJoCo perception launch

**Files:**
- Modify: `src/so101_demo_py/src/runtime/launch_composition.py:412-490,930-1017,1143-1191`
- Modify: `src/so101_demo_py/test/test_perception_pick_place_launch.py:119-328`
- Modify: `src/so101_demo_py/test/test_launch_composition.py`

**Interfaces:**
- Extends `perception_backend` choices to `("color_geometry", "yolo_seg", "grounded_sam")`。
- Adds launch arguments: `perception_model_root`、`perception_model_manifest_sha256`、`grounding_box_threshold`、`grounding_text_threshold`、`grounding_duplicate_iou`、`grounding_max_candidates`、`sam_mask_quality_threshold`、`sam_min_mask_pixels`、`sam_max_mask_area_ratio`。
- Preserves the color-geometry and YOLO process graphs。

- [ ] **Step 1: 写 launch RED 测试**

```python
def test_grounded_sam_backend_starts_object_pose_with_bundle_and_thresholds(tmp_path: Path) -> None:
    bundle = fake_verified_bundle(tmp_path)
    context, actions, _status = _materialize(
        evidence_file=tmp_path / "launch.json",
        perception_backend="grounded_sam",
        perception_model_root=bundle,
        perception_model_manifest_sha256=manifest_sha(bundle),
        perception_device="mps",
    )
    started = _dispatch_process_exit(actions, _node(actions, "scene_setup"), 0, context)
    perception = _node(started, "rgbd_object_pose")
    assert "--backend" in perception._Node__arguments
    assert "grounded_sam" in perception._Node__arguments
    assert "--model-root" in perception._Node__arguments
    assert str(bundle) in perception._Node__arguments
    assert "--sam-mask-quality-threshold" in perception._Node__arguments
```

反例测试覆盖缺目录、相对目录、非法 manifest SHA、Grounded SAM 混入 YOLO weights、YOLO 混入 model root 和全部阈值越界。

- [ ] **Step 2: 运行 RED**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_perception_pick_place_launch.py src/so101_demo_py/test/test_launch_composition.py -q
```

Expected: backend choice and launch arguments are absent.

- [ ] **Step 3: 实现 launch 校验和参数接线**

`_configured_perception_pick_place_actions` 先校验 backend，再只解析对应模型参数。Grounded SAM root 必须是绝对现有目录，manifest SHA 必须是小写 64 hex；逐文件校验仍由 runtime adapter 完成。`_mujoco_perception_execute_actions` 对 Grounded SAM 创建同一个 `rgbd_object_pose` executable，参数顺序固定为共享参数、backend、model root/SHA、device、阈值、request ID 和 evidence root。

保持 `sim_speed_factor=1.0`，不伪造源时间戳，也不缩短 `/cup_pose` 交付确认。

- [ ] **Step 4: 运行 GREEN 和旧后端回归**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest src/so101_demo_py/test/test_perception_pick_place_launch.py src/so101_demo_py/test/test_launch_composition.py -q
```

Expected: color geometry, YOLO and Grounded SAM process-graph tests all pass.

- [ ] **Step 5: 提交**

```bash
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo add -- src/so101_demo_py/src/runtime/launch_composition.py src/so101_demo_py/test/test_perception_pick_place_launch.py src/so101_demo_py/test/test_launch_composition.py
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo commit -m "feat(perception): launch Grounded SAM pick-place"
```

### Task 9: 包级测试和初学者文档

**Files:**
- Create: `docs/guides/so101-grounded-sam-rgbd-perception-pick-place-source-guide.md`
- Modify: `docs/experiments/v5-t005-grounded-sam-rgbd-experiment-ledger.md`
- Modify: source/test files only if package tests expose a scoped regression from Tasks 1-8

**Interfaces:**
- Produces: one persistent guide under `docs/guides/`。
- Produces: a ledger checkpoint recording exact commit, test counts, evidence root and no owned processes。

- [ ] **Step 1: 运行全部定向测试**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest \
  src/so101_demo_py/test/test_model_runtime.py \
  src/so101_demo_py/test/test_grounded_sam_config.py \
  src/so101_demo_py/test/test_grounded_sam_bundle.py \
  src/so101_demo_py/test/test_grounded_sam_postprocess.py \
  src/so101_demo_py/test/test_grounded_sam_adapter.py \
  src/so101_demo_py/test/test_detector_factory.py \
  src/so101_demo_py/test/test_detection_contracts.py \
  src/so101_demo_py/test/test_rgbd_object_pose.py \
  src/so101_demo_py/test/test_perception_pick_place_launch.py -q
```

Expected: all collected tests pass.

- [ ] **Step 2: 运行 Mac package-level gate**

Run in the current zsh with the current ROS environment:

```zsh
cd /Users/matianyi/.codex/worktrees/5b15/moveit-demo
eval "$(direnv export zsh)"
source install/setup.zsh
export ROS_HOME=/tmp/so101-debug-v5-t005-grounded-sam-20260901/mac-package/ros-home
export ROS_LOG_DIR="$ROS_HOME/log"
mkdir -p "$ROS_LOG_DIR"
PYTHONNOUSERSITE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -c 'import rclpy; print(rclpy.__file__)'
PYTHONNOUSERSITE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest \
  -p no:cacheprovider src/so101_demo_py/test -q \
  --junitxml=/tmp/so101-debug-v5-t005-grounded-sam-20260901/mac-package/so101_demo_py-pytest.xml
/Users/matianyi/ros2_jazzy/.venv/bin/colcon test-result \
  --test-result-base /tmp/so101-debug-v5-t005-grounded-sam-20260901/mac-package --verbose
```

Expected: nonzero test collection, pytest exit 0, test-result errors/failures 0.

- [ ] **Step 3: 运行 ai-station package gate**

First verify host and dirty state. From the Mac orchestrator:

```bash
ssh -o BatchMode=yes ai-station 'hostname; zsh -lc "cd /data/work/ws_moveit && git status --short"'
```

After synchronizing the exact implementation commit into the ai-station checkout, run in ai-station zsh:

```zsh
cd /data/work/ws_moveit
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_demo_py --symlink-install
source install/setup.zsh
export ROS_HOME=/tmp/so101-debug-v5-t005-grounded-sam-20260901/linux-package/ros-home
export ROS_LOG_DIR="$ROS_HOME/log"
mkdir -p "$ROS_LOG_DIR"
PYTHONNOUSERSITE=1 colcon test --packages-select so101_demo_py --event-handlers console_direct+
colcon test-result --verbose
```

Expected: build exit 0, nonzero tests, errors/failures 0, and `ros2 pkg prefix so101_demo_py` points to `/data/work/ws_moveit/install/so101_demo_py`.

- [ ] **Step 4: 编写并 humanize 教学文档**

文档标题沿用现有源码导读格式，面向初学者解释：

1. Grounding DINO 的文本引导候选框原理；
2. SAM 2.1 框提示分割与 predicted IoU；
3. 为什么逐帧无状态；
4. `DetectorPort -> TargetSelector -> RgbdLocalizer -> /cup_pose` 通信关系；
5. 双模型包、revision、manifest 和离线部署；
6. macOS MPS 与 Linux CUDA 安装及启动命令；
7. 0/1/2+ 候选、Depth、TF 与错误码；
8. 四场景和连续 5/5 验收；
9. 常见故障和学员练习。

使用 `.agents/skills/humanizer-zh/SKILL.md` 审阅中文，只改叙述，不改命令、错误码、模型 ID、SHA、路径和链接。

- [ ] **Step 5: 更新 ledger checkpoint 并提交**

账本记录实际测试数、commit、Mac/Linux package evidence 路径、owned processes `NONE`，并将下一实验设为真实模型包构建。

```bash
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo add -- docs/guides/so101-grounded-sam-rgbd-perception-pick-place-source-guide.md docs/experiments/v5-t005-grounded-sam-rgbd-experiment-ledger.md
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo commit -m "docs: teach Grounded SAM RGB-D perception"
```

### Task 10: 构建同一模型包并完成双平台离线 smoke

**Files:**
- Modify: `docs/experiments/v5-t005-grounded-sam-rgbd-experiment-ledger.md`
- Evidence only: `/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/model-bundle/`
- Runtime model location on ai-station: `/data/work/so101-models/grounded-sam-v1`
- Runtime model location on Mac: `/Users/matianyi/Models/so101/grounded-sam-v1`

**Interfaces:**
- Consumes: installed `prepare_grounded_sam_bundle` and `rgbd_object_pose` entry points。
- Produces: one bundle manifest SHA shared by CUDA and MPS。
- Produces: actual-model smoke JSON with model revisions, runtime device, candidate count, mask pixels and phase latency。

- [ ] **Step 1: 在 ledger 预写 EXP-001 bundle 实验**

状态先写 `PLANNED`，固定两个 revision、输出路径、无覆盖规则和成功判据：bundle verifier 通过，模型文件无 symlink，manifest SHA 有效。核对 ai-station host、workspace、GPU 和现有模型目录后再改为 `RUNNING`。

- [ ] **Step 2: 在两平台准备锁定依赖**

使用任务专用 venv，不改系统 Python：

```zsh
cd /data/work/ws_moveit
python3 -m venv /data/work/venvs/so101-grounded-sam
source /data/work/venvs/so101-grounded-sam/bin/activate
NO_PROXY=pypi.tuna.tsinghua.edu.cn no_proxy=pypi.tuna.tsinghua.edu.cn \
  uv pip install --default-index https://pypi.tuna.tsinghua.edu.cn/simple \
  -r src/so101_demo_py/config/perception/requirements.lock
python -c 'import torch, transformers; print(torch.__version__, transformers.__version__, torch.cuda.is_available())'
```

Expected: pinned imports succeed and CUDA is `True`. If the candidate Transformers pins cannot load both fixed revisions, mark the experiment `VALID` failure, change only the dependency pins through a new RED/GREEN config test and rerun under a new experiment ID.

Mac 先检查现有 ROS Python，不做无条件重装：

```zsh
/Users/matianyi/ros2_jazzy/.venv/bin/python3 -c \
  'import rclpy, torch, transformers, safetensors; print(rclpy.__file__, torch.__version__, transformers.__version__, torch.backends.mps.is_available())'
```

若 import 或锁定版本不符，先保存 `uv pip freeze --python /Users/matianyi/ros2_jazzy/.venv/bin/python3`，取得依赖安装授权后执行：

```zsh
NO_PROXY=pypi.tuna.tsinghua.edu.cn no_proxy=pypi.tuna.tsinghua.edu.cn \
uv pip install \
  --python /Users/matianyi/ros2_jazzy/.venv/bin/python3 \
  --default-index https://pypi.tuna.tsinghua.edu.cn/simple \
  -r /Users/matianyi/.codex/worktrees/5b15/moveit-demo/src/so101_demo_py/config/perception/requirements.lock
```

安装后重跑 import probe，要求 `rclpy` 仍来自当前 ROS Jazzy 环境、锁定版本一致且 MPS 可用。不得用另一个 Python 的成功替代 installed `rgbd_object_pose` 所用解释器。

- [ ] **Step 3: 构建并验证 bundle**

```zsh
cd /data/work/ws_moveit
source /opt/ros/jazzy/setup.zsh
source install/setup.zsh
source /data/work/venvs/so101-grounded-sam/bin/activate
mkdir -p /data/work/so101-models
prepare_grounded_sam_bundle \
  --config /data/work/ws_moveit/src/so101_demo_py/config/perception/grounded_sam.yaml \
  --output /data/work/so101-models/grounded-sam-v1
sha256sum /data/work/so101-models/grounded-sam-v1/manifest.json
find /data/work/so101-models/grounded-sam-v1 -type l -print
```

Expected: CLI exits 0, SHA is lowercase 64 hex, `find` prints nothing.

- [ ] **Step 4: 归档并复制完全相同的 bundle 到 Mac**

在 ai-station：

```zsh
mkdir -p /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/model-bundle
tar -C /data/work/so101-models -czf \
  /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/model-bundle/grounded-sam-v1.tar.gz \
  grounded-sam-v1
sha256sum \
  /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/model-bundle/grounded-sam-v1.tar.gz \
  > /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/model-bundle/grounded-sam-v1.tar.gz.sha256
```

从 Mac 复制到 `/tmp/so101-debug-v5-t005-grounded-sam-20260901/model-transfer/`，核对 tar SHA，再解压到不存在的 `/Users/matianyi/Models/so101/grounded-sam-v1`。不得覆盖已有目录；若目标存在，先验证并复用，或停下请求用户决定。

- [ ] **Step 5: 两平台断网加载并运行 one-cup smoke**

Linux 先计算 manifest SHA 和 scene 路径，再启动一个新 ROS domain：

```zsh
bundle_sha=$(sha256sum /data/work/so101-models/grounded-sam-v1/manifest.json | awk '{print $1}')
scene_path=$(ros2 pkg prefix so101_demo_py)/share/so101_demo_py/assets/mujoco/v5_multi_object_scene.xml
run_id=linux-grounded-sam-smoke-001
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ROS_DOMAIN_ID=141 \
ros2 launch so101_demo_py so101_mujoco_perception_pick_place.launch.py \
  run_mode:=execute execute:=true headless:=true sensor_rendering:=true \
  session_id:=$run_id \
  evidence_file:=/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/model-smoke/linux-$run_id.json \
  mujoco_scene:=$scene_path mujoco_initial_keyframe:=task_start \
  perception_startup_timeout_s:=120.0 cup_pose_timeout_s:=45.0 \
  perception_backend:=grounded_sam \
  perception_model_root:=/data/work/so101-models/grounded-sam-v1 \
  perception_model_manifest_sha256:=$bundle_sha \
  perception_device:=cuda perception_allow_cpu_fallback:=false
```

Mac 使用同一个 manifest SHA：

```zsh
bundle_sha=$(shasum -a 256 /Users/matianyi/Models/so101/grounded-sam-v1/manifest.json | awk '{print $1}')
scene_path=$(ros2 pkg prefix so101_demo_py)/share/so101_demo_py/assets/mujoco/v5_multi_object_scene.xml
run_id=mac-grounded-sam-smoke-001
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ROS_DOMAIN_ID=142 \
ros2 launch so101_demo_py so101_mujoco_perception_pick_place.launch.py \
  run_mode:=execute execute:=true headless:=false sensor_rendering:=true \
  session_id:=$run_id \
  evidence_file:=/tmp/so101-debug-v5-t005-grounded-sam-20260901/model-smoke/mac-$run_id.json \
  mujoco_scene:=$scene_path mujoco_initial_keyframe:=task_start \
  perception_startup_timeout_s:=120.0 cup_pose_timeout_s:=45.0 \
  perception_backend:=grounded_sam \
  perception_model_root:=/Users/matianyi/Models/so101/grounded-sam-v1 \
  perception_model_manifest_sha256:=$bundle_sha \
  perception_device:=mps perception_allow_cpu_fallback:=false
```

Mac 结果核验后按相对路径、大小和 SHA 清单复制到 durable evidence root 的 `model-smoke/macos/`，再做远端 read-back。两次 smoke 不计入最终 5/5。

Expected: 两个平台都唯一选择 `plastic_cup`，生成非空 full-resolution mask，发布源时间戳 `/cup_pose`；网络关闭时没有 Hub 请求。

- [ ] **Step 6: 关闭进程并结算 EXP-001/EXP-002/EXP-003**

只停止本轮 PID/session，复查 ROS nodes、MuJoCo、MoveIt 和模型进程。账本记录 bundle/tar/manifest SHA、两个设备、冷启动和 warmed latency、候选/mask 指标、退出码与 cleanup。失败批次保留。

- [ ] **Step 7: 提交 ledger checkpoint**

```bash
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo add -- docs/experiments/v5-t005-grounded-sam-rgbd-experiment-ledger.md
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo commit -m "docs: record Grounded SAM offline smoke"
```

### Task 11: 双平台四场景与连续 5/5 Pick&Place

**Files:**
- Modify: `docs/experiments/v5-t005-grounded-sam-rgbd-experiment-ledger.md`
- Modify: production/config/test files only when a new experiment proves a scoped defect and a RED test reproduces it
- Evidence: `/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/`
- Evidence: `/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/pick-place/`

**Interfaces:**
- Produces: macOS MPS and Linux CUDA four-scene acceptance matrix。
- Produces: two independent `FULL_RESTART` consecutive-success series, each `5/5`。
- Produces: final evidence disposition and simulation-only acceptance decision。

- [ ] **Step 1: 预写四场景实验矩阵**

每个平台为以下 keyframe 分别创建 `PLANNED` experiment ID：

```text
task_start         -> one plastic_cup + distractors -> unique /cup_pose
v5_no_cup          -> TARGET_NOT_FOUND              -> no new /cup_pose
v5_two_cups        -> TARGET_AMBIGUOUS               -> no new /cup_pose
v5_cup_near_bottle -> unique cup mask                -> no bottle pixels
```

固定 commit、bundle SHA、全部阈值、`sim_speed_factor=1.0`、FULL_RESTART、新 request ID 和平台 device。每轮写清 invalid criteria：旧 topic、重复 node、错误 overlay、未对齐 payload、缺 truth、evidence 写失败或 cleanup 失败。

- [ ] **Step 2: 先跑 Linux CUDA 四场景**

逐场景执行，不并行启动多个 stack。每轮保存：

- RGB、Depth、CameraInfo 宽高、stamp、frame ID；
- `detections.json`、全部 candidate masks、selected mask 和 overlay；
- DINO score、SAM quality、candidate count 和 latency；
- truth mask IoU、world pose error；
- `/cup_pose` observer 结果；
- process/node cleanup read-back。

Linux zsh 逐轮执行：

```zsh
bundle_sha=$(sha256sum /data/work/so101-models/grounded-sam-v1/manifest.json | awk '{print $1}')
scene_path=$(ros2 pkg prefix so101_demo_py)/share/so101_demo_py/assets/mujoco/v5_multi_object_scene.xml
matrix_root=/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix/linux
mkdir -p "$matrix_root"
keyframes=(task_start v5_no_cup v5_two_cups v5_cup_near_bottle)
for index in {1..4}; do
  keyframe=${keyframes[$index]}
  run_id=linux-matrix-${index}-${keyframe}
  HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ROS_DOMAIN_ID=$((150 + index)) \
  ros2 launch so101_demo_py so101_mujoco_perception_pick_place.launch.py \
    run_mode:=execute execute:=true headless:=true sensor_rendering:=true \
    session_id:=$run_id evidence_file:=$matrix_root/$run_id.json \
    mujoco_scene:=$scene_path mujoco_initial_keyframe:=$keyframe \
    perception_startup_timeout_s:=120.0 cup_pose_timeout_s:=45.0 \
    perception_backend:=grounded_sam \
    perception_model_root:=/data/work/so101-models/grounded-sam-v1 \
    perception_model_manifest_sha256:=$bundle_sha \
    perception_device:=cuda perception_allow_cpu_fallback:=false
  printf '%s\n' $? > "$matrix_root/$run_id-exit-code.txt"
done
```

Expected: 4/4 满足 spec；warmed latency `<= 2000 ms`、IoU `>= 0.80`、唯一场景 error `< 0.01 m`。

- [ ] **Step 3: 再跑 macOS MPS 四场景**

沿用完全相同的 commit、bundle SHA 和阈值。需要 visible MuJoCo 或视觉证据时使用 `$gui-capture` 路由；截图之外仍要保存同一套数值证据。

Mac zsh 逐轮执行：

```zsh
bundle_sha=$(shasum -a 256 /Users/matianyi/Models/so101/grounded-sam-v1/manifest.json | awk '{print $1}')
scene_path=$(ros2 pkg prefix so101_demo_py)/share/so101_demo_py/assets/mujoco/v5_multi_object_scene.xml
matrix_root=/tmp/so101-debug-v5-t005-grounded-sam-20260901/perception-matrix/macos
mkdir -p "$matrix_root"
keyframes=(task_start v5_no_cup v5_two_cups v5_cup_near_bottle)
for index in {1..4}; do
  keyframe=${keyframes[$index]}
  run_id=mac-matrix-${index}-${keyframe}
  HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ROS_DOMAIN_ID=$((160 + index)) \
  ros2 launch so101_demo_py so101_mujoco_perception_pick_place.launch.py \
    run_mode:=execute execute:=true headless:=false sensor_rendering:=true \
    session_id:=$run_id evidence_file:=$matrix_root/$run_id.json \
    mujoco_scene:=$scene_path mujoco_initial_keyframe:=$keyframe \
    perception_startup_timeout_s:=120.0 cup_pose_timeout_s:=45.0 \
    perception_backend:=grounded_sam \
    perception_model_root:=/Users/matianyi/Models/so101/grounded-sam-v1 \
    perception_model_manifest_sha256:=$bundle_sha \
    perception_device:=mps perception_allow_cpu_fallback:=false
  printf '%s\n' $? > "$matrix_root/$run_id-exit-code.txt"
done
```

核验后将 Mac 四轮输出按相对路径、大小和 SHA 清单复制到 durable root 的 `perception-matrix/macos/`，并逐项回读。

Expected: 4/4 语义结论与 Linux 一致。Mask 不要求逐像素相同，但必须分别通过 IoU 和 pose 门槛。

- [ ] **Step 4: 若阈值失败，只做单变量标定**

先在 ledger 写新的 `PLANNED` 实验，只改一个阈值。不得同时改 prompt、阈值和场景。每次有效改动都补自动化边界测试、跑包级回归、提交新 commit，然后从四场景矩阵第一轮重新计数。

若受控阈值无法达到门槛，结论写 `MODEL_CAPABILITY_NOT_MET` 并停止；不加入 truth、颜色或最高分强选。

- [ ] **Step 5: 预写 Linux 五次 FULL_RESTART Pick&Place**

创建五个连续 experiment ID，固定最终 commit、bundle、阈值、`task_start`、motion policy 和成功契约。每轮要证明抓取、微抬升、放置、夹爪脱离、桌面支撑和 cleanup。`VALID` 失败终止序列；`INVALID` 不进分母但也终止当前批次。

- [ ] **Step 6: 执行 Linux CUDA 5/5**

使用 public perception pick-place launch，`perception_backend:=grounded_sam`、`perception_device:=cuda`、CPU fallback false。每轮全新进程图和 request ID。

```zsh
bundle_sha=$(sha256sum /data/work/so101-models/grounded-sam-v1/manifest.json | awk '{print $1}')
scene_path=$(ros2 pkg prefix so101_demo_py)/share/so101_demo_py/assets/mujoco/v5_multi_object_scene.xml
pick_root=/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/pick-place/linux
mkdir -p "$pick_root"
for run_number in {1..5}; do
  run_id=linux-pick-final-$run_number
  HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ROS_DOMAIN_ID=$((170 + run_number)) \
  ros2 launch so101_demo_py so101_mujoco_perception_pick_place.launch.py \
    run_mode:=execute execute:=true headless:=true sensor_rendering:=true \
    session_id:=$run_id evidence_file:=$pick_root/$run_id.json \
    mujoco_scene:=$scene_path mujoco_initial_keyframe:=task_start \
    perception_startup_timeout_s:=120.0 cup_pose_timeout_s:=45.0 \
    perception_backend:=grounded_sam \
    perception_model_root:=/data/work/so101-models/grounded-sam-v1 \
    perception_model_manifest_sha256:=$bundle_sha \
    perception_device:=cuda perception_allow_cpu_fallback:=false
  printf '%s\n' $? > "$pick_root/$run_id-exit-code.txt"
done
```

Expected: 连续五个 `VALID` success；`/cup_pose` 源时间戳与执行器消费证据一致。

- [ ] **Step 7: 预写并执行 macOS MPS 5/5**

规则与 Linux 相同，只把 device 设为 MPS。GUI 截图必须来自本轮动作之后并实际查看；视觉成功不能替代物理和 ROS/MoveIt 证据。

```zsh
bundle_sha=$(shasum -a 256 /Users/matianyi/Models/so101/grounded-sam-v1/manifest.json | awk '{print $1}')
scene_path=$(ros2 pkg prefix so101_demo_py)/share/so101_demo_py/assets/mujoco/v5_multi_object_scene.xml
pick_root=/tmp/so101-debug-v5-t005-grounded-sam-20260901/pick-place/macos
mkdir -p "$pick_root"
for run_number in {1..5}; do
  run_id=mac-pick-final-$run_number
  HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ROS_DOMAIN_ID=$((180 + run_number)) \
  ros2 launch so101_demo_py so101_mujoco_perception_pick_place.launch.py \
    run_mode:=execute execute:=true headless:=false sensor_rendering:=true \
    session_id:=$run_id evidence_file:=$pick_root/$run_id.json \
    mujoco_scene:=$scene_path mujoco_initial_keyframe:=task_start \
    perception_startup_timeout_s:=120.0 cup_pose_timeout_s:=45.0 \
    perception_backend:=grounded_sam \
    perception_model_root:=/Users/matianyi/Models/so101/grounded-sam-v1 \
    perception_model_manifest_sha256:=$bundle_sha \
    perception_device:=mps perception_allow_cpu_fallback:=false
  printf '%s\n' $? > "$pick_root/$run_id-exit-code.txt"
done
```

五轮核验后，按文件清单把 Mac 结果复制到 durable root 的 `pick-place/macos/` 并远端 read-back。

Expected: 连续五个 `VALID` success。

- [ ] **Step 8: 跑最终回归并锁定 provenance**

Mac 运行 Task 9 的完整 package gate；ai-station 运行 `colcon build/test/test-result`。回读 installed package prefix、runtime entry point、commit、bundle manifest SHA 和 launch 参数。任何最终代码或配置改动都使既有运行失效，必须重跑对应平台矩阵和 5/5。

- [ ] **Step 9: 更新最终 ledger 与证据处置**

账本头部写入最终 commit 和 `next_experiment: NONE`。checkpoint 至少列出：

```yaml
retained:
  - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/model-bundle
  - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/perception-matrix
  - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/pick-place/linux
  - /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/pick-place/macos
archived: []
deletion_candidates: []
remaining_boundary:
  - 本任务证明 MuJoCo 仿真，不证明真实 SO-101 硬件
```

- [ ] **Step 10: 提交最终验收记录**

```bash
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo add -- docs/experiments/v5-t005-grounded-sam-rgbd-experiment-ledger.md
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo commit -m "docs: record V5-T005 final simulation acceptance"
```

## 最终自检

- [ ] 对照设计的 17 个章节逐项确认有对应 Task。
- [ ] 搜索 writing-plans 禁止的占位词和空尖括号占位，结果必须为空。
- [ ] 核对 `GroundedSamThresholds`、`VerifiedModelBundle`、`BuiltDetector` 和 CLI/launch 参数在所有 Task 中拼写一致。
- [ ] 核对所有 Git 暂存命令只包含本任务路径。
- [ ] 核对 Mac/Linux 正式运行使用同一 commit、bundle SHA、prompt 和阈值。
- [ ] 核对每次成功声明同时有 payload、语义、mask、Depth、TF、pose、物理、视觉、provenance 与 cleanup 证据。
