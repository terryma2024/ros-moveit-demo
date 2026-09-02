# Grounded DINO + SAM 2.1 与 YOLO-Seg 双平台 Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在冻结的 200 张 val 与 200 张 test 数据上，以同一真值、匹配、安全决策和证据口径，对 YOLO-Seg 与逐帧无状态 Grounding DINO Tiny + SAM 2.1 Hiera Tiny 完成 Linux CUDA / macOS MPS A/B benchmark。

**Architecture:** 新增独立的 `so101_demo.perception_benchmark` 包，将不可变 schema、数据装载、几何匹配、指标、标定、模型诊断适配、运行编排和报告拆成单一职责模块。val 低门槛候选先在双平台采集，再合并生成不可变 threshold-lock；threshold-lock 冻结后才运行 test，production 正式路径仍经过现有 `DetectorPort`，benchmark-only raw 诊断出口不改变生产 detector 语义。

**Tech Stack:** Python 3.11、NumPy、Pillow 12.3.0、PyYAML 6.0.2、PyTorch 2.13.0、Ultralytics 8.4.115、Transformers 4.56.2、ROS 2 Jazzy/ament_python、pytest；不新增 SciPy 或 pycocotools。

**Spec:** `docs/superpowers/specs/2026-09-02-grounded-sam-yolo-seg-benchmark-design.md`

## Global Constraints

- 正式数据归档固定为 `datasets/so101-v5-t004-yolo-seg-synthetic/so101-v5-t004-yolo-seg-synthetic-20260831-f09cf88.tar.gz`，SHA-256 固定为 `c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1`。
- val 与 test 各 200 张；每个 split 的 `no_cup`、`one_cup_distractors`、`two_cups`、`cup_near_bottle` 各 50 张。任何逐图 `ERROR` 都保留在 full denominator，禁止跳样本、重复样本或隐式补跑。
- YOLO `best.pt` SHA-256 固定为 `f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781`；FP32，`imgsz=640`，Linux 用 CUDA，Mac 用 MPS，CPU fallback 禁止。
- Grounded-SAM manifest SHA-256 固定为 `838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3`；Grounding DINO revision 固定为 `a2bb814dd30d776dcf7e30523b00659f4f141c71`，SAM revision 固定为 `de431c4043854a71d8101e17995dfe596bf101a5`，prompt 固定为 `plastic cup.`，逐帧无状态，FP32，`offline=true`，`fallback_used=false`。
- 依赖继续使用 `src/so101_demo_py/config/perception/requirements.lock`；不新增 SciPy、pycocotools 或联网运行依赖。Hungarian、101 点 AP、bootstrap、RLE 均用 Python + NumPy 实现；polygon 栅格化固定为 Pillow 12.3.0 的精确规则。
- val-only 标定；两个平台的 val 记录合并选择一套共同 threshold-lock。threshold-lock 生成前禁止读取 test truth 或运行正式 test；test 结果不得反向改变 grid、阈值、prompt、模型、依赖或摘要结论。
- raw 低门槛采集与正式运行分离：val 仅采集 low-floor raw；threshold-lock 后，test 运行一次 low-floor `ORACLE_DIAGNOSTIC` 以计算 raw/AP 和固定两套 decision replay，另分别运行 production 与 calibrated/characterization 性能/契约路径。`ORACLE_DIAGNOSTIC` 不参与阈值选择、模型排名或 production 配置回填。
- production test 的正式调用必须通过现有 `so101_demo.adapters.perception.detector_factory.DetectorPort` 和 `TargetSelector`；benchmark-only adapters 只能暴露不可变 raw candidates、阶段时间和运行来源，不能改变生产 detector 语义。
- 由于当前 YOLO production 代码固定传入 `conf=0.25`、未在仓库配置文件显式写 NMS IoU，implementation 必须从 Ultralytics 8.4.115 warm-up 后的 resolved predictor args 读取 production NMS IoU 并写入配置快照；字段缺失时该 run 为 `INVALID`，禁止猜测历史默认值。此 ruling 的成本是 production 配置快照依赖锁定 Ultralytics 的可读 resolved args。
- 低门槛 test 诊断比 spec 第 9.1 节最小矩阵多一次模型运行。其收益是 AP/raw 候选与 production/calibrated 性能、生产边界证据互不混淆；成本是每平台每模型多处理 200 张，但它仍在 threshold-lock 后运行，且不解封任何新的选择自由度。
- run 状态只使用 `PLANNED`、`RUNNING`、`VALID`、`INVALID`；逐图状态只使用 `OK`、`ERROR`。run `INVALID` 与 record `ERROR` 是不同层级，不得把合法逐图错误自动升级为无效运行。
- 注册 durable evidence root 固定为 `/data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1`；Mac 临时 staging/debug 固定为 `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1`。Mac 工件传输到 durable root 后按 immutable inventory 做 SHA readback；未经明确授权不删除任何 evidence。
- 新账本固定为 `docs/experiments/grounded-sam-yolo-seg-benchmark-experiment-ledger.md`，外部运行前先写 `PLANNED`；每个实验记录 exact source commit、工作树状态、install overlay、runtime executable/package prefix、平台、device、dtype、依赖锁 SHA、配置 SHA、inventory SHA、开始/结束时间和证据路径。
- Mac 与 ai-station 都从 exact source commit 构建。ai-station 的 canonical `/data/work/ws_moveit` dirty checkout 保持不动，使用新的 isolated exact checkout；不得 reset、stash、clean 或覆盖用户文件。
- warmed latency：模型加载一次，正式 shape warm-up 至少 5 次，计时边界 device synchronize；cold latency：至少 3 个全新进程。保存逐图 p50/p95/p99、各 phase、throughput、peak RSS、CUDA/MPS memory 和平台可获得的资源采样；准确率运行不挑样本、不挑最好重复。
- 全部代码任务先 RED、再最小 GREEN、再定向测试、再 package gate；Mac 测试使用正确 ROS overlay 与 ROS Python direct pytest，不设置错误的 `PYTHONPATH=src/so101_demo_py/src`。Linux 使用 ROS-only zsh 和 isolated checkout。
- 本计划不修改 V5-T005 现有 ledger。Task 11 整改只产出 benchmark evidence、append-only remediation proposal 与回流建议；是否修改旧 ledger、重新运行 Task 11 或发布结论，另行取得授权。
- 不 push、不 merge，不启动真实机械臂、相机、MoveIt 或 Pick & Place；不运行 `ament_uncrustify --reformat`；不 stage 已有 `build-task10-watermark-v2/`、`build-task11-tf-discovery/`、`install-task10-watermark-v2/`、`install-task11-tf-discovery/`、`log-task10-watermark-v2/`。

## File Responsibility Map

| Path | Single responsibility |
| --- | --- |
| `src/so101_demo_py/src/perception_benchmark/contracts.py` | 冻结 enum、不可变 records、字段/数值校验 |
| `src/so101_demo_py/src/perception_benchmark/codec.py` | canonical JSON、mask RLE、SHA、原子读写 |
| `src/so101_demo_py/src/perception_benchmark/dataset.py` | 归档校验、只读解包、inventory、truth/polygon 栅格化 |
| `src/so101_demo_py/src/perception_benchmark/matching.py` | mask IoU/Dice、确定性 Hungarian assignment |
| `src/so101_demo_py/src/perception_benchmark/metrics.py` | AP、实例/count 指标、paired bootstrap |
| `src/so101_demo_py/src/perception_benchmark/decisions.py` | 0/1/2+ replay、confusion、安全与场景指标 |
| `src/so101_demo_py/src/perception_benchmark/calibration.py` | grid 枚举、共同 val 目标、tie-break、threshold-lock/seal |
| `src/so101_demo_py/src/perception_benchmark/adapters/base.py` | benchmark raw adapter protocol 与阶段计时 contract |
| `src/so101_demo_py/src/perception_benchmark/adapters/yolo.py` | YOLO low-floor/resolved production/raw candidate adapter |
| `src/so101_demo_py/src/perception_benchmark/adapters/grounded_sam.py` | DINO+SAM low-floor/raw scores/stateless adapter |
| `src/so101_demo_py/src/perception_benchmark/timing.py` | CUDA/MPS synchronize、cold/warm/resource samplers |
| `src/so101_demo_py/src/perception_benchmark/runner.py` | inventory 顺序、error record、checkpoint/resume、run manifest |
| `src/so101_demo_py/src/perception_benchmark/reporting.py` | 聚合 JSON/CSV/Markdown/evidence index |
| `src/so101_demo_py/src/perception_benchmark/comparison.py` | 双平台候选、confidence、box/mask、decision 差异 |
| `src/so101_demo_py/src/cli/perception_benchmark.py` | CLI 参数解析与 subcommand 编排 |
| `src/so101_demo_py/config/perception_benchmark/benchmark.yaml` | 资产、grid、生产参数来源、run protocol 固定配置 |
| `src/so101_demo_py/test/fixtures/perception_benchmark/dry-run-adapters.json` | 8 图 non-formal dry-run 的冻结 fake-adapter 输出 |
| `src/so101_demo_py/test/test_perception_benchmark_*.py` | 按上述边界拆分的 contract/组件/CLI 回归测试 |
| `docs/experiments/grounded-sam-yolo-seg-benchmark-experiment-ledger.md` | append-only 状态、provenance、checkpoint |
| `docs/reports/grounded-sam-yolo-seg-benchmark-report.md` | 最终人工报告，不替代机器证据 |

---

### Task 1: 不可变 benchmark contracts、schema version 与 JSON codec

**Files:**
- Create: `src/so101_demo_py/src/perception_benchmark/__init__.py`
- Create: `src/so101_demo_py/src/perception_benchmark/contracts.py`
- Create: `src/so101_demo_py/src/perception_benchmark/codec.py`
- Test: `src/so101_demo_py/test/test_perception_benchmark_contracts.py`
- Test: `src/so101_demo_py/test/test_perception_benchmark_codec.py`

**Interfaces:**
- Consumes: `numpy.ndarray` boolean masks；`so101_demo.core.detection.RuntimeDevice`。
- Produces: `SCHEMA_VERSION = "so101-perception-benchmark/v1"`；`RunStatus`、`RecordStatus`、`RunKind`、`DecisionOutput`；`MaskRef`、`TruthInstance`、`TruthSample`、`RawCandidate`、`PhaseTimings`、`RuntimeProvenance`、`PredictionRecord`；`encode_mask_rle(mask: np.ndarray) -> dict[str, object]`、`decode_mask_rle(document: Mapping[str, object]) -> np.ndarray`、`read_mask(mask_ref: MaskRef, evidence_root: Path) -> np.ndarray`、`canonical_json_bytes(document: object) -> bytes`、`sha256_bytes(payload: bytes) -> str`、`atomic_write_json(path: Path, document: object) -> str`。

- [ ] **Step 1: Write failing immutable-record and null-vs-zero tests**

```python
def test_prediction_record_preserves_null_phase_and_rejects_nonfinite_score() -> None:
    record = prediction_record(sam_ms=None, selector_ms=0.0)
    assert record.phase_timings.sam_ms is None
    assert record.phase_timings.selector_ms == 0.0
    with pytest.raises(ValueError, match="ranking_score"):
        raw_candidate(ranking_score=float("nan"))


def test_error_record_is_in_denominator_and_has_no_selected_candidate() -> None:
    record = prediction_record(
        record_status=RecordStatus.ERROR,
        decision=DecisionOutput.ERROR,
        error_type="INFERENCE_FAILED",
        selected_candidate_id=None,
    )
    assert record.formal_sample_index == 17
    assert record.error_type == "INFERENCE_FAILED"
```

- [ ] **Step 2: Run the focused tests and confirm RED**

Run:

```zsh
cd /Users/matianyi/.codex/worktrees/5b15/moveit-demo
eval "$(direnv export zsh)"
source /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/setup.zsh
source install/setup.zsh
/Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider \
  src/so101_demo_py/test/test_perception_benchmark_contracts.py \
  src/so101_demo_py/test/test_perception_benchmark_codec.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'so101_demo.perception_benchmark'`.

- [ ] **Step 3: Implement frozen enums and dataclasses with explicit validation**

```python
SCHEMA_VERSION = "so101-perception-benchmark/v1"


class RunStatus(str, Enum):
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    VALID = "VALID"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class MaskRef:
    relative_path: str
    sha256: str
    pixel_count: int
    image_width: int
    image_height: int


@dataclass(frozen=True, slots=True)
class RawCandidate:
    candidate_id: str
    label: str
    bbox_xyxy: tuple[float, float, float, float]
    mask: MaskRef
    ranking_score: float
    ranking_score_source: str
    class_confidence: float | None
    grounding_box_score: float | None
    grounding_text_score: float | None
    sam_quality: float | None

    def __post_init__(self) -> None:
        _require_probability("ranking_score", self.ranking_score)
        if not self.candidate_id or self.label != "plastic_cup":
            raise ValueError("candidate identity is invalid")
```

Implement `PredictionRecord.__post_init__` so an `ERROR` requires `DecisionOutput.ERROR` and non-empty `error_type`, while `OK` forbids error fields. Copy tuple/dict inputs into immutable owned values; reject duplicate candidate IDs, mask/image dimension mismatch, CPU device, fallback, nonfinite latency/confidence/box, missing provenance and unknown schema version.

- [ ] **Step 4: Add canonical JSON and lossless row-major RLE**

```python
def encode_mask_rle(mask: np.ndarray) -> dict[str, object]:
    value = np.asarray(mask, dtype=bool)
    if value.ndim != 2:
        raise ValueError("mask must be two-dimensional")
    flat = value.astype(np.uint8, copy=False).ravel(order="C")
    counts: list[int] = []
    current = 0
    run = 0
    for pixel in flat:
        if int(pixel) == current:
            run += 1
        else:
            counts.append(run)
            current = int(pixel)
            run = 1
    counts.append(run)
    return {"encoding": "binary-rle-c-v1", "height": value.shape[0], "width": value.shape[1], "counts": counts}


def canonical_json_bytes(document: object) -> bytes:
    return (json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
```

`MaskRef.sha256` 固定为解码后 `uint8` C-order bytes 的 SHA，而非 JSON 文本 SHA。`atomic_write_json` 用同目录临时文件、`flush`、`os.fsync`、`os.replace`，返回最终 canonical bytes SHA。

- [ ] **Step 5: Run focused tests and package-neighbor regressions**

Run the Step 2 command, then:

```zsh
/Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider \
  src/so101_demo_py/test/test_detection_contracts.py \
  src/so101_demo_py/test/test_target_selector.py -q
```

Expected: benchmark tests pass；existing detection/selector tests pass with no changed production API.

- [ ] **Step 6: Commit Task 1**

```zsh
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo add -- \
  src/so101_demo_py/src/perception_benchmark/__init__.py \
  src/so101_demo_py/src/perception_benchmark/contracts.py \
  src/so101_demo_py/src/perception_benchmark/codec.py \
  src/so101_demo_py/test/test_perception_benchmark_contracts.py \
  src/so101_demo_py/test/test_perception_benchmark_codec.py
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo commit -m "feat: add perception benchmark contracts"
```

### Task 2: Dataset archive verifier、truth loader 与确定性 polygon rasterization

**Files:**
- Create: `src/so101_demo_py/src/perception_benchmark/dataset.py`
- Test: `src/so101_demo_py/test/test_perception_benchmark_dataset.py`

**Interfaces:**
- Consumes: Task 1 `TruthInstance`、`TruthSample`、`MaskRef`、`atomic_write_json`。
- Produces: `DatasetInventory`；`DatasetArchiveVerifier.verify_and_extract(archive: Path, expected_sha256: str, output_root: Path) -> DatasetInventory`；`rasterize_polygon(polygon_xy, width, height) -> np.ndarray`；`load_truth_samples(dataset_root, split, inventory) -> tuple[TruthSample, ...]`。

- [ ] **Step 1: Write failing archive, traversal, count and rasterization tests**

```python
def test_polygon_rule_is_round_half_up_and_includes_pillow_boundary() -> None:
    polygon = ((0.0, 0.0), (1.0, 0.0), (0.5, 1.0))
    mask = rasterize_polygon(polygon, width=5, height=5)
    assert mask.dtype == np.bool_
    assert mask.tolist() == [
        [True, True, True, True, True],
        [False, True, True, True, False],
        [False, True, True, True, False],
        [False, False, True, False, False],
        [False, False, True, False, False],
    ]


def test_inventory_requires_200_and_50_per_scenario(tmp_path: Path) -> None:
    archive = build_fixture_archive(tmp_path, split_count=199)
    with pytest.raises(DatasetVerificationError, match="split count"):
        DatasetArchiveVerifier().verify_and_extract(archive, sha256_file(archive), tmp_path / "out")
```

Also create a tar member named `dataset/../../escape` and assert `ARCHIVE_PATH_UNSAFE`; corrupt one image/label pair and assert no partial inventory is returned.

- [ ] **Step 2: Run the dataset test and confirm RED**

Run:

```zsh
/Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider \
  src/so101_demo_py/test/test_perception_benchmark_dataset.py -q
```

Expected: import fails because `so101_demo.perception_benchmark.dataset` does not exist.

- [ ] **Step 3: Implement SHA-first safe extraction and immutable inventory**

```python
class DatasetArchiveVerifier:
    def verify_and_extract(self, archive: Path, expected_sha256: str, output_root: Path) -> DatasetInventory:
        if sha256_file(archive) != expected_sha256:
            raise DatasetVerificationError("DATASET_ARCHIVE_HASH_MISMATCH")
        if output_root.exists():
            raise DatasetVerificationError("OUTPUT_ROOT_ALREADY_EXISTS")
        with tarfile.open(archive, "r:gz") as tar:
            for member in tar.getmembers():
                target = (output_root / member.name).resolve()
                if not target.is_relative_to(output_root.resolve()) or member.issym() or member.islnk():
                    raise DatasetVerificationError("ARCHIVE_PATH_UNSAFE")
            tar.extractall(output_root, filter="data")
        return self._build_inventory(output_root / "dataset", expected_sha256)
```

Inventory order is `sorted(samples, key=lambda item: item.image_sha256)` within each split, then assign `formal_sample_index=0..199`. Verify PNG dimensions `640x480`, truth/label/image one-to-one mapping, unique SHA, visible truth count, and exact scenario histogram. After validation, chmod extracted files read-only and write canonical `inventory.json` plus SHA.

- [ ] **Step 4: Implement the exact Pillow 12.3.0 rasterization rule**

```python
def _round_half_up(value: float) -> int:
    return int(math.floor(value + 0.5))


def rasterize_polygon(polygon_xy: tuple[tuple[float, float], ...], width: int, height: int) -> np.ndarray:
    pixels = [
        (
            min(width - 1, max(0, _round_half_up(x * (width - 1)))),
            min(height - 1, max(0, _round_half_up(y * (height - 1)))),
        )
        for x, y in polygon_xy
    ]
    image = Image.new("1", (width, height), 0)
    ImageDraw.Draw(image).polygon(pixels, fill=1)
    return np.asarray(image, dtype=bool)
```

Store `rasterizer={"library":"Pillow","version":"12.3.0","coordinate_scale":"dimension_minus_one","rounding":"floor(x+0.5)","boundary":"ImageDraw.polygon fill=1"}` in inventory and reject another Pillow version during formal runs. For example, build val sample `000200001` from `truth/val/000200001.json`, not from predictions or RGB colors; verify label polygon equals truth polygon within exact parsed decimal values.

- [ ] **Step 5: Run focused tests plus existing dataset tests**

Run:

```zsh
/Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider \
  src/so101_demo_py/test/test_perception_benchmark_dataset.py \
  src/so101_demo_py/test/test_yolo_seg_dataset.py -q
```

Expected: all pass; fixture proves no inference output is consulted.

- [ ] **Step 6: Commit Task 2**

```zsh
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo add -- \
  src/so101_demo_py/src/perception_benchmark/dataset.py \
  src/so101_demo_py/test/test_perception_benchmark_dataset.py
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo commit -m "feat: verify benchmark dataset truth"
```

### Task 3: Mask IoU/Dice、确定性 Hungarian、AP 与 paired bootstrap

**Files:**
- Create: `src/so101_demo_py/src/perception_benchmark/matching.py`
- Create: `src/so101_demo_py/src/perception_benchmark/metrics.py`
- Test: `src/so101_demo_py/test/test_perception_benchmark_matching.py`
- Test: `src/so101_demo_py/test/test_perception_benchmark_metrics.py`

**Interfaces:**
- Consumes: Task 1 records/RLE；Task 2 truth samples。
- Produces: `MaskMatch`；`mask_iou(first: np.ndarray, second: np.ndarray) -> float`、`mask_dice(first: np.ndarray, second: np.ndarray) -> float`、`maximize_mask_iou_assignment(truth: Sequence[TruthInstance], candidates: Sequence[RawCandidate], evidence_root: Path) -> tuple[MaskMatch, ...]`；`compute_ap(records: Sequence[PredictionRecord], truths: Sequence[TruthSample], evidence_root: Path, iou_thresholds: Sequence[float]) -> ApSummary`；`bootstrap_image_metrics(samples: Sequence[ImageMetricInput], metric: Callable[[Sequence[ImageMetricInput]], float], seed: int = 20260902, repetitions: int = 10000) -> ConfidenceInterval`。

- [ ] **Step 1: Write failing geometry, tie, empty-truth and AP tests**

```python
def test_hungarian_maximizes_total_iou_and_breaks_tie_by_confidence_then_id() -> None:
    truth = (truth_mask("t0", [[1, 0], [0, 0]]),)
    candidates = (
        candidate("b", 0.9, [[1, 0], [0, 0]]),
        candidate("a", 0.9, [[1, 0], [0, 0]]),
        candidate("c", 0.8, [[1, 0], [0, 0]]),
    )
    assert maximize_mask_iou_assignment(truth, candidates)[0].candidate_id == "a"


def test_empty_truth_empty_prediction_has_no_synthetic_iou() -> None:
    summary = compute_image_metrics(truth=(), candidates=(), iou_threshold=0.50)
    assert summary.tp == summary.fp == summary.fn == 0
    assert summary.mean_iou is None


def test_ap_uses_101_point_interpolation() -> None:
    summary = compute_ap(fixture_records(), fixture_truth(), (0.50,))
    assert summary.mask_ap50 == pytest.approx(0.8349834983)
```

- [ ] **Step 2: Run matching/metrics tests and confirm RED**

Run:

```zsh
/Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider \
  src/so101_demo_py/test/test_perception_benchmark_matching.py \
  src/so101_demo_py/test/test_perception_benchmark_metrics.py -q
```

Expected: import failure for `matching` and `metrics`.

- [ ] **Step 3: Implement pure NumPy deterministic Hungarian assignment**

```python
def maximize_mask_iou_assignment(
    truth: Sequence[TruthInstance], candidates: Sequence[RawCandidate]
) -> tuple[MaskMatch, ...]:
    ordered_truth = tuple(sorted(truth, key=lambda item: item.instance_id))
    ordered_candidates = tuple(sorted(candidates, key=lambda item: (-item.ranking_score, item.candidate_id)))
    ious = np.asarray(
        [[mask_iou(read_mask(t.mask, evidence_root), read_mask(c.mask, evidence_root)) for c in ordered_candidates] for t in ordered_truth],
        dtype=np.float64,
    )
    row_to_column = _hungarian_minimize(1.0 - ious)
    return tuple(
        MaskMatch(ordered_truth[row].instance_id, ordered_candidates[column].candidate_id, float(ious[row, column]))
        for row, column in enumerate(row_to_column)
        if column is not None
    )
```

Implement `_hungarian_minimize(cost: np.ndarray) -> tuple[int | None, ...]` with the O(n^3) potential/augmenting-path algorithm. Iterate rows in truth ID order and columns in `(-ranking_score, candidate_id)` order; use strict `<` updates and lower column index on exact equality. This makes equal-total-IoU assignments deterministic without floating epsilon or SciPy.

- [ ] **Step 4: Implement thresholded counts, 101-point AP and image bootstrap**

```python
def interpolated_ap(recall: np.ndarray, precision: np.ndarray) -> float | None:
    if precision.size == 0:
        return None
    levels = np.linspace(0.0, 1.0, 101)
    return float(np.mean([np.max(precision[recall >= level], initial=0.0) for level in levels]))


def bootstrap_image_metrics(samples, metric, *, seed: int = 20260902, repetitions: int = 10_000):
    rng = np.random.default_rng(seed)
    values = np.empty(repetitions, dtype=np.float64)
    for index in range(repetitions):
        selected = rng.integers(0, len(samples), size=len(samples))
        values[index] = metric(tuple(samples[item] for item in selected))
    return ConfidenceInterval(float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975)))
```

At each global ranking prefix, recompute per-image Hungarian matching at the active IoU threshold and use the change in total matched truth as the TP increment. A record with `ERROR` contributes all truth as FN and no candidates. Precision with denominator zero is `None`; IoU/Dice aggregates include matched TP only. Paired model/platform bootstrap generates one shared index vector per repetition.

- [ ] **Step 5: Run focused tests and deterministic repeat test**

Run Step 2 twice and compare canonical JSON output SHA from the bootstrap fixture.

Expected: both runs pass and produce identical SHA; no `scipy` or `pycocotools` import appears in `rg -n "scipy|pycocotools" src/so101_demo_py/src/perception_benchmark`.

- [ ] **Step 6: Commit Task 3**

```zsh
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo add -- \
  src/so101_demo_py/src/perception_benchmark/matching.py \
  src/so101_demo_py/src/perception_benchmark/metrics.py \
  src/so101_demo_py/test/test_perception_benchmark_matching.py \
  src/so101_demo_py/test/test_perception_benchmark_metrics.py
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo commit -m "feat: compute benchmark instance metrics"
```

### Task 4: 0/1/2+ decision replay、安全与场景指标

**Files:**
- Create: `src/so101_demo_py/src/perception_benchmark/decisions.py`
- Test: `src/so101_demo_py/test/test_perception_benchmark_decisions.py`

**Interfaces:**
- Consumes: `PredictionRecord`、`TruthSample`、Task 3 matching。
- Produces: `DecisionThresholds` protocol、`DecisionReplay`、`DecisionMetrics`、`ScenarioMetrics`；`replay_decision(record: PredictionRecord, config: DecisionThresholds) -> DecisionReplay`；`aggregate_decisions(records: Sequence[PredictionRecord], truths: Sequence[TruthSample]) -> DecisionMetrics`；`aggregate_scenarios(records: Sequence[PredictionRecord], truths: Sequence[TruthSample], matches: Sequence[MaskMatch]) -> Mapping[str, ScenarioMetrics]`。

- [ ] **Step 1: Write failing confusion, unsafe, no-cup and leakage tests**

```python
def test_error_is_its_own_output_column_and_keeps_denominator() -> None:
    metrics = aggregate_decisions(
        records=(record(DecisionOutput.ERROR),),
        truths=(truth(decision_class="1"),),
    )
    assert metrics.confusion["1"]["ERROR"] == 1
    assert metrics.sample_count == 1


def test_unique_on_zero_or_two_is_unsafe() -> None:
    metrics = aggregate_decisions(
        records=(record(DecisionOutput.UNIQUE), record(DecisionOutput.UNIQUE)),
        truths=(truth(decision_class="0"), truth(decision_class="2+")),
    )
    assert metrics.unsafe_unique_count == 2
    assert metrics.unsafe_unique_rate == 1.0


def test_cup_near_bottle_leakage_uses_outside_cup_hull_pixels() -> None:
    assert non_cup_leakage_ratio(pred_mask(), cup_truth_union()) == pytest.approx(3 / 7)
```

- [ ] **Step 2: Run decision tests and confirm RED**

Run:

```zsh
/Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider \
  src/so101_demo_py/test/test_perception_benchmark_decisions.py -q
```

Expected: missing decisions module.

- [ ] **Step 3: Implement immutable replay without mutating raw candidates**

```python
class DecisionThresholds(Protocol):
    def filter_candidates(self, candidates: tuple[RawCandidate, ...]) -> tuple[RawCandidate, ...]:
        raise NotImplementedError


def replay_decision(record: PredictionRecord, config: DecisionThresholds) -> DecisionReplay:
    if record.record_status is RecordStatus.ERROR:
        return DecisionReplay(DecisionOutput.ERROR, None, record.error_type)
    accepted = config.filter_candidates(record.raw_candidates)
    if not accepted:
        return DecisionReplay(DecisionOutput.NOT_FOUND, None, "TARGET_NOT_FOUND")
    if len(accepted) > 1:
        return DecisionReplay(DecisionOutput.AMBIGUOUS, None, "TARGET_AMBIGUOUS")
    return DecisionReplay(DecisionOutput.UNIQUE, accepted[0].candidate_id, None)
```

For YOLO, `YoloThresholds.filter_candidates` applies deterministic score filter, fixed NMS replay and selector threshold. For Grounded-SAM, `GroundedSamBenchmarkThresholds.filter_candidates` applies box/text/SAM quality, fixed duplicate IoU, mask area/pixels and selector threshold. Return new IDs/decisions only; compare pre/post raw record SHA in tests.

- [ ] **Step 4: Implement full 3x4 confusion and required safety/scenario metrics**

```python
OUTPUTS = ("NOT_FOUND", "UNIQUE", "AMBIGUOUS", "ERROR")
TRUTHS = ("0", "1", "2+")


def decision_confusion(pairs: Iterable[tuple[str, DecisionOutput]]) -> dict[str, dict[str, int]]:
    matrix = {truth: {output: 0 for output in OUTPUTS} for truth in TRUTHS}
    for truth, output in pairs:
        matrix[truth][output.value] += 1
    return matrix
```

Compute macro-F1 with truth mapping `0->NOT_FOUND`, `1->UNIQUE`, `2+->AMBIGUOUS`, while retaining `ERROR` as an explicit wrong column. `no_cup` FPR counts images with any accepted cup candidate. `two_cups` both-instance recall requires two IoU>=0.50 matches. Leakage is `predicted_union & ~truth_cup_union` divided by predicted union pixels, and is named `non_cup_leakage_ratio` only.

- [ ] **Step 5: Run focused tests and Task 3 regression**

Expected: decision tests and matching/metrics tests pass; raw canonical SHA before and after replay is equal.

- [ ] **Step 6: Commit Task 4**

```zsh
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo add -- \
  src/so101_demo_py/src/perception_benchmark/decisions.py \
  src/so101_demo_py/test/test_perception_benchmark_decisions.py
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo commit -m "feat: score benchmark safety decisions"
```

### Task 5: val-only grid calibration、deterministic tie-break、threshold-lock 与 test seal

**Files:**
- Create: `src/so101_demo_py/src/perception_benchmark/calibration.py`
- Test: `src/so101_demo_py/test/test_perception_benchmark_calibration.py`

**Interfaces:**
- Consumes: Task 1 records/codec；Task 3/4 metrics；val inventory SHA and prediction inventories。
- Produces: `YoloThresholds`、`GroundedSamBenchmarkThresholds`、`CalibrationResult`、`ThresholdLock`；`enumerate_yolo_grid() -> Iterator[YoloThresholds]`、`enumerate_grounded_sam_grid() -> Iterator[GroundedSamBenchmarkThresholds]`；`calibrate_joint_platform_val(model: str, mac_records: Sequence[PredictionRecord], linux_records: Sequence[PredictionRecord], truths: Sequence[TruthSample], inventory_sha: str) -> ThresholdLock`；`verify_test_seal(lock: ThresholdLock, test_access_log: Path) -> None`。

- [ ] **Step 1: Write failing exact-grid, tie-break, unsafe and seal tests**

```python
def test_grids_have_exact_decimal_endpoints_without_float_drift() -> None:
    yolo = tuple(enumerate_yolo_grid())
    grounded = tuple(enumerate_grounded_sam_grid())
    assert yolo[0].conf == Decimal("0.05")
    assert yolo[-1].target_confidence_threshold == Decimal("0.95")
    assert grounded[-1].sam_quality == Decimal("0.95")


def test_joint_calibration_requires_zero_unsafe_on_both_platforms() -> None:
    lock = calibrate_joint_platform_val(mac_records(), linux_records(), inventory_sha="a" * 64)
    assert lock.selected.safe is True
    assert lock.platform_metrics["macos"].unsafe_unique_rate == 0.0
    assert lock.platform_metrics["linux"].unsafe_unique_rate == 0.0


def test_test_truth_access_before_lock_is_rejected() -> None:
    with pytest.raises(CalibrationError, match="TEST_SEALED"):
        TestSeal(lock_path=None).open_truth("test")
```

- [ ] **Step 2: Run calibration tests and confirm RED**

Run:

```zsh
/Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider \
  src/so101_demo_py/test/test_perception_benchmark_calibration.py -q
```

Expected: missing calibration module.

- [ ] **Step 3: Implement exact Decimal grids and normalized config JSON**

```python
def decimal_range(start: str, stop: str, step: str) -> tuple[Decimal, ...]:
    current, end, increment = Decimal(start), Decimal(stop), Decimal(step)
    values: list[Decimal] = []
    while current <= end:
        values.append(current)
        current += increment
    return tuple(values)


def enumerate_yolo_grid() -> Iterator[YoloThresholds]:
    for conf, nms_iou, selector in product(
        decimal_range("0.05", "0.95", "0.05"),
        decimal_range("0.30", "0.90", "0.10"),
        decimal_range("0.05", "0.95", "0.05"),
    ):
        yield YoloThresholds(conf, nms_iou, selector, imgsz=640)
```

Grounded grid follows spec endpoints/steps and fixed `duplicate_iou=0.85`、`min_mask_pixels=64`、`max_mask_area_ratio=0.50`. Serialize Decimal as fixed two-decimal strings in normalized JSON, then hash canonical bytes.

- [ ] **Step 4: Implement the seven-level joint-platform comparator and immutable lock**

```python
def calibration_key(point: EvaluatedPoint) -> tuple[object, ...]:
    return (
        point.mac_unsafe != 0.0 or point.linux_unsafe != 0.0,
        -min(point.mac_macro_f1, point.linux_macro_f1),
        -point.merged_macro_f1,
        -point.merged_mask_ap50_95,
        -min(point.mac_two_cup_recall, point.linux_two_cup_recall),
        point.safety_preference_key,
        point.normalized_json,
    )
```

If every point is unsafe, set `outcome="UNSAFE_CALIBRATION_NO_FEASIBLE_POINT"`, `deployable=false`, and still freeze the characterization winner selected by levels 2–7. `ThresholdLock` includes both platform val inventory SHAs, both prediction-record inventory SHAs, grid/target/tie-break version, selected values, code commit and its own SHA. `TestSeal` requires a verified threshold-lock file and appends a read-only access event before allowing test truth loading.

- [ ] **Step 5: Run focused tests and canonical lock reproducibility test**

Run Step 2 twice; Expected: identical lock SHA, exact same selected config, and test access is impossible when lock verification fails.

- [ ] **Step 6: Commit Task 5**

```zsh
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo add -- \
  src/so101_demo_py/src/perception_benchmark/calibration.py \
  src/so101_demo_py/test/test_perception_benchmark_calibration.py
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo commit -m "feat: calibrate joint platform thresholds"
```

### Task 6: YOLO 与 Grounded-SAM raw adapters、phase timing、offline/device/provenance boundary

**Files:**
- Create: `src/so101_demo_py/src/perception_benchmark/adapters/__init__.py`
- Create: `src/so101_demo_py/src/perception_benchmark/adapters/base.py`
- Create: `src/so101_demo_py/src/perception_benchmark/adapters/yolo.py`
- Create: `src/so101_demo_py/src/perception_benchmark/adapters/grounded_sam.py`
- Create: `src/so101_demo_py/src/perception_benchmark/timing.py`
- Test: `src/so101_demo_py/test/test_perception_benchmark_adapters.py`
- Test: `src/so101_demo_py/test/test_perception_benchmark_timing.py`

**Interfaces:**
- Consumes: existing `YoloSegDetector`、`GroundedSamDetector`、`DetectorPort`、`GroundedSamThresholds`、`DetectionFrame`、`DetectionQuery`；Task 1 records。
- Produces: `CollectionMode`、`RawDetectionResult`、`ProductionObservation`、`ResourceSample`；`RawDetectorAdapter.collect(frame: DetectionFrame, mode: CollectionMode) -> RawDetectionResult`；`YoloRawAdapter`、`GroundedSamRawAdapter`；`run_production_detector_port(detector: DetectorPort, frame: DetectionFrame, selector_threshold: float) -> ProductionObservation`；`DeviceSynchronizer.synchronize() -> None`；`ResourceSampler.sample() -> ResourceSample`。

- [ ] **Step 1: Write failing common-schema and production-boundary tests**

```python
@pytest.mark.parametrize("adapter_factory", (fake_yolo_adapter, fake_grounded_adapter))
def test_both_adapters_emit_same_raw_contract(adapter_factory) -> None:
    result = adapter_factory().collect(frame(), CollectionMode.LOW_FLOOR)
    assert result.raw_candidates
    assert result.phase_timings.total_ms >= 0.0
    assert all(candidate.mask.sha256 for candidate in result.raw_candidates)
    assert result.fallback_used is False


def test_production_observation_calls_detector_port_and_real_target_selector() -> None:
    detector = RecordingDetectorPort(batch=one_candidate_batch())
    observed = run_production_detector_port(detector, frame(), selector_threshold=0.50)
    assert detector.detect_calls == [(frame(), DetectionQuery("plastic_cup"))]
    assert observed.decision is DecisionOutput.UNIQUE


def test_offline_missing_bundle_never_calls_network_loader(tmp_path: Path) -> None:
    with pytest.raises(ModelSetupError, match="MODEL_UNAVAILABLE"):
        GroundedSamRawAdapter.from_bundle(tmp_path / "missing", network_loader=pytest.fail)
```

- [ ] **Step 2: Write failing timing synchronization and nullable resource tests**

```python
def test_cuda_and_mps_are_synchronized_at_each_timing_boundary() -> None:
    api = RecordingTorchApi()
    with PhaseTimer(DeviceSynchronizer(api, "cuda")) as timer:
        timer.mark("preprocess")
        timer.mark("model")
    assert api.cuda.synchronize_calls == 3


def test_unavailable_gpu_measurements_are_none_not_zero() -> None:
    sample = ResourceSampler(process=FakeProcess(), torch_api=FakeTorch(), device="mps").sample()
    assert sample.gpu_utilization_percent is None
    assert sample.gpu_power_watts is None
```

- [ ] **Step 3: Run adapter/timing tests and confirm RED**

Run:

```zsh
/Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider \
  src/so101_demo_py/test/test_perception_benchmark_adapters.py \
  src/so101_demo_py/test/test_perception_benchmark_timing.py -q
```

Expected: missing benchmark adapters/timing modules.

- [ ] **Step 4: Implement adapter protocol and production observation boundary**

```python
class RawDetectorAdapter(Protocol):
    model_id: str
    runtime_device: RuntimeDevice

    def collect(self, frame: DetectionFrame, mode: CollectionMode) -> RawDetectionResult:
        raise NotImplementedError


def run_production_detector_port(
    detector: DetectorPort,
    frame: DetectionFrame,
    selector_threshold: float,
) -> ProductionObservation:
    batch = detector.detect(frame, DetectionQuery("plastic_cup"))
    try:
        selected = TargetSelector().select(batch, DetectionQuery("plastic_cup"), selector_threshold)
    except TargetSelectionError as error:
        return ProductionObservation.from_selector_error(batch, error.code)
    return ProductionObservation.unique(batch, selected.instance_id)
```

The helper snapshots candidates before selector invocation and verifies their mask/confidence/ID canonical SHA afterward. `DetectorPort` production runs do not use raw adapter replay as a substitute.

- [ ] **Step 5: Implement YOLO low-floor and resolved production snapshot**

```python
class YoloRawAdapter:
    def collect(self, frame: DetectionFrame, mode: CollectionMode) -> RawDetectionResult:
        result = self._model.predict(
            source=frame.rgb8,
            imgsz=640,
            device=self.runtime_device,
            conf=0.01,
            iou=0.90,
            max_det=300,
            verbose=False,
        )[0]
        return self._convert_after_nms(result, frame, irreversible_limits={"nms_iou": 0.90, "max_det": 300})

    def resolved_production_config(self) -> YoloProductionSnapshot:
        args = self._model.predictor.args
        return YoloProductionSnapshot(conf=require_probability(args.conf), nms_iou=require_probability(args.iou), imgsz=640)
```

Use class confidence as `ranking_score`; class confidence is non-null while DINO/text/SAM fields are null. Low-floor `iou=0.90` equals grid maximum, so offline NMS can replay every lower grid IoU; report `max_det=300` as an irreversible collection limit. Refuse formal execution if resolved production `conf` is not `0.25`, `imgsz` is not `640`, or NMS IoU cannot be read.

- [ ] **Step 6: Implement Grounded-SAM low-floor stateless collection**

```python
class GroundedSamRawAdapter:
    def collect(self, frame: DetectionFrame, mode: CollectionMode) -> RawDetectionResult:
        prompt = "plastic cup."
        grounding = self._run_grounding(frame, prompt, box_threshold=0.01, text_threshold=0.01)
        masks, sam_quality = self._run_sam_once(frame, grounding.boxes)
        return self._build_candidates(
            grounding,
            masks,
            sam_quality,
            fixed_min_mask_pixels=64,
            fixed_max_mask_area_ratio=0.50,
        )
```

`_run_grounding` records post-processor grounding score as `grounding_box_score`/`ranking_score` and separately derives `grounding_text_score` from sigmoid token logits for the decoded `plastic cup` phrase. SAM quality is quality-gate evidence only and is never multiplied into ranking. Every `collect` call starts from RGB and fresh processor state; no video memory/tracking object exists. Force `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`, pass `local_files_only=True`, verify bundle/revisions/manifest before model load, and reject CPU/fallback.

- [ ] **Step 7: Implement synchronized phase and resource sampling**

```python
class DeviceSynchronizer:
    def synchronize(self) -> None:
        if self.device == "cuda":
            self.torch.cuda.synchronize()
        elif self.device == "mps":
            self.torch.mps.synchronize()
        else:
            raise RuntimeError("formal benchmark forbids CPU")
```

Time `preprocess_ms`、`dino_or_yolo_ms`、`sam_ms`、`postprocess_ms`、`selector_ms` and `total_ms`; non-applicable values are `None`. Sample process RSS/CPU and available CUDA/MPS memory/utilization/temperature/power with tool/version metadata; unavailable fields remain `None` plus a reason.

- [ ] **Step 8: Run focused and production adapter regressions**

Run:

```zsh
/Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider \
  src/so101_demo_py/test/test_perception_benchmark_adapters.py \
  src/so101_demo_py/test/test_perception_benchmark_timing.py \
  src/so101_demo_py/test/test_yolo_seg_adapter.py \
  src/so101_demo_py/test/test_grounded_sam_adapter.py \
  src/so101_demo_py/test/test_detector_factory.py \
  src/so101_demo_py/test/test_target_selector.py -q
```

Expected: all pass; production adapter source files are unchanged.

- [ ] **Step 9: Commit Task 6**

```zsh
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo add -- \
  src/so101_demo_py/src/perception_benchmark/adapters \
  src/so101_demo_py/src/perception_benchmark/timing.py \
  src/so101_demo_py/test/test_perception_benchmark_adapters.py \
  src/so101_demo_py/test/test_perception_benchmark_timing.py
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo commit -m "feat: collect benchmark detector candidates"
```

### Task 7: Runner、lossless records、fail-closed errors、resource stream 与 resume integrity

**Files:**
- Create: `src/so101_demo_py/src/perception_benchmark/runner.py`
- Test: `src/so101_demo_py/test/test_perception_benchmark_runner.py`

**Interfaces:**
- Consumes: Task 1/2 contracts/inventory；Task 6 adapters/timing。
- Produces: `RunSpec`、`RunManifest`、`RunCheckpoint`；`DetectorBenchmarkRunner.run(spec: RunSpec) -> RunManifest`；`verify_resume(checkpoint: RunCheckpoint, inventory: DatasetInventory, config_sha: str, source_commit: str) -> int`。

- [ ] **Step 1: Write failing per-image ERROR and resume-gap tests**

```python
def test_inference_exception_writes_error_record_and_continues_full_inventory(tmp_path: Path) -> None:
    runner = DetectorBenchmarkRunner(adapter=FailsOnIndex(3), output_root=tmp_path)
    manifest = runner.run(run_spec(sample_count=8))
    assert manifest.record_count == 8
    assert manifest.error_count == 1
    assert read_record(tmp_path, 3).decision is DecisionOutput.ERROR


def test_resume_rejects_gap_duplicate_or_changed_config(tmp_path: Path) -> None:
    write_records(tmp_path, formal_indices=(0, 1, 3))
    with pytest.raises(RunIntegrityError, match="NON_CONTIGUOUS_RECORDS"):
        verify_resume(read_checkpoint(tmp_path), inventory(), config_sha="a" * 64, source_commit="deadbeef")
```

- [ ] **Step 2: Run runner tests and confirm RED**

Run:

```zsh
/Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider \
  src/so101_demo_py/test/test_perception_benchmark_runner.py -q
```

Expected: missing runner module.

- [ ] **Step 3: Implement one-record-per-inventory-item execution**

```python
class DetectorBenchmarkRunner:
    def run(self, spec: RunSpec) -> RunManifest:
        start_index = verify_resume_or_start(spec)
        for item in spec.inventory.samples[start_index:]:
            try:
                result = self.adapter.collect(load_frame(item), spec.collection_mode)
                record = self._ok_record(spec, item, result)
            except Exception as error:
                record = self._error_record(spec, item, classify_error(error))
            atomic_write_json(spec.records_dir / f"{item.formal_sample_index:06d}.json", record.to_document())
            self._append_checkpoint(item.formal_sample_index, record.document_sha256)
        return self._finalize_manifest(spec)
```

Catch OOM/timeout/sync/schema/model errors into typed record error fields; do not retry another device/model. Before every record, verify input SHA. For formal sample 17 and candidate `grounded-sam-000`, persist the mask at `masks/000017/grounded-sam-000.rle.json`; use the same zero-padded/indexed rule for every record, fsync mask before record, then fsync checkpoint. A hardware overheat/resource sampler failure makes the whole run `INVALID` and stops; already-written evidence remains.

- [ ] **Step 4: Implement strict resume and run validity checks**

Resume only if existing indices are exactly `0..n-1`, every record/mask SHA verifies, source commit/config/model/inventory/device/dtype/run_kind match, and checkpoint points to record `n-1`. Any gap, duplicate, changed file or formal sample mismatch sets run manifest `INVALID`; never skip to the next unseen filename.

```python
def verify_resume(checkpoint, inventory, config_sha, source_commit) -> int:
    if checkpoint.config_sha != config_sha or checkpoint.source_commit != source_commit:
        raise RunIntegrityError("RESUME_PROVENANCE_CHANGED")
    indices = tuple(record.formal_sample_index for record in read_records(checkpoint.records_dir))
    if indices != tuple(range(len(indices))):
        raise RunIntegrityError("NON_CONTIGUOUS_RECORDS")
    return len(indices)
```

- [ ] **Step 5: Run runner, codec and contracts regressions**

Expected: all pass; fixture output contains 8 records even with one inference error, while a corrupted resume becomes run `INVALID`.

- [ ] **Step 6: Commit Task 7**

```zsh
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo add -- \
  src/so101_demo_py/src/perception_benchmark/runner.py \
  src/so101_demo_py/test/test_perception_benchmark_runner.py
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo commit -m "feat: run resumable perception benchmark"
```

### Task 8: Aggregator、reports 与 cross-platform comparison

**Files:**
- Create: `src/so101_demo_py/src/perception_benchmark/reporting.py`
- Create: `src/so101_demo_py/src/perception_benchmark/comparison.py`
- Test: `src/so101_demo_py/test/test_perception_benchmark_reporting.py`
- Test: `src/so101_demo_py/test/test_perception_benchmark_comparison.py`

**Interfaces:**
- Consumes: Tasks 1–7 records, matches, decisions, metrics, resources, threshold-lock。
- Produces: `MetricsAggregator.aggregate(input: AggregationInput) -> BenchmarkSummary`；`ReportWriter.write(summary, output_root) -> EvidenceIndex`；`compare_platforms(mac_records, linux_records) -> CrossPlatformSummary`。

- [ ] **Step 1: Write failing full-denominator and mismatch-list tests**

```python
def test_report_keeps_error_record_in_all_denominators(tmp_path: Path) -> None:
    summary = MetricsAggregator().aggregate(fixture_with_one_error_of_four())
    assert summary.sample_count == 4
    assert summary.error_count == 1
    assert summary.error_rate == 0.25
    assert summary.scenarios["no_cup"].sample_count == 1


def test_cross_platform_report_lists_candidate_and_decision_mismatches() -> None:
    result = compare_platforms(mac_records(), linux_records())
    assert result.mismatch_image_shas == ("1" * 64,)
    assert result.items[0].candidate_count_equal is False
    assert result.items[0].decision_equal is False
```

- [ ] **Step 2: Run report/comparison tests and confirm RED**

Run:

```zsh
/Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider \
  src/so101_demo_py/test/test_perception_benchmark_reporting.py \
  src/so101_demo_py/test/test_perception_benchmark_comparison.py -q
```

Expected: missing modules.

- [ ] **Step 3: Implement exact aggregation matrix and confidence intervals**

`BenchmarkSummary` keys are `platform -> model -> configuration -> overall/scenarios/performance/resources`. Validate exactly 200 unique image SHAs for formal split and 50 each scenario before aggregation. Emit `mask_AP50`、`mask_AP50_95`、precision/recall/F1 at 0.50、mean/median IoU/Dice、count accuracy、FP/image、FN/image、error/timeout/OOM、decision macro-F1、unique success、unsafe unique、no-cup FPR、two-cup both recall、leakage and 95% image bootstrap CI.

```python
def percentile(values: Sequence[float], quantile: float) -> float | None:
    finite = np.asarray([value for value in values if math.isfinite(value)], dtype=np.float64)
    return None if finite.size == 0 else float(np.quantile(finite, quantile, method="linear"))
```

Compute p50/p95/p99 from per-image values, never batch means. Count errored images in throughput wall time while leaving missing phases null.

- [ ] **Step 4: Implement stable cross-platform matching and reports**

For same model/config/image, order candidates by `candidate_id`, compare candidate count, confidence absolute/relative delta, Hungarian paired mask IoU and box IoU, decision and error type. Emit every mismatch image to `cross-platform-mismatches.csv`; no blanket “floating point” suppression.

`ReportWriter` creates:

```text
metrics/summary.json
metrics/per-scenario.csv
metrics/per-image.csv
metrics/cross-platform-mismatches.csv
performance/latency.json
performance/resources.json
report/benchmark.md
evidence-index.json
```

Every index entry has relative path, size and SHA. The report visibly separates `production`、`calibrated`/`characterization`、`ORACLE_DIAGNOSTIC`; oracle values never enter winner/safety summary.

- [ ] **Step 5: Run focused tests and output-tree SHA repeat**

Run Step 2 twice in separate `tmp_path` roots. Expected: all machine-readable files have identical SHA except explicitly excluded wall-clock timestamps; mismatch CSV lists exact image SHAs.

- [ ] **Step 6: Commit Task 8**

```zsh
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo add -- \
  src/so101_demo_py/src/perception_benchmark/reporting.py \
  src/so101_demo_py/src/perception_benchmark/comparison.py \
  src/so101_demo_py/test/test_perception_benchmark_reporting.py \
  src/so101_demo_py/test/test_perception_benchmark_comparison.py
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo commit -m "feat: report perception benchmark metrics"
```

### Task 9: CLI、setup/config、新实验账本与 8-image non-formal dry run

**Files:**
- Create: `src/so101_demo_py/src/cli/perception_benchmark.py`
- Create: `src/so101_demo_py/config/perception_benchmark/benchmark.yaml`
- Create: `src/so101_demo_py/test/fixtures/perception_benchmark/dry-run-adapters.json`
- Modify: `src/so101_demo_py/setup.py`
- Create: `src/so101_demo_py/test/test_perception_benchmark_cli.py`
- Create: `docs/experiments/grounded-sam-yolo-seg-benchmark-experiment-ledger.md`

**Interfaces:**
- Consumes: Tasks 1–8 public APIs；fixed assets and evidence roots。
- Produces: console entry point `perception_benchmark` with `verify-assets`、`prepare-dataset`、`dry-run`、`collect`、`calibrate`、`aggregate`、`verify-evidence` subcommands；prewritten benchmark ledger。

- [ ] **Step 1: Write failing CLI/config/install tests**

```python
def test_cli_rejects_test_collect_without_verified_threshold_lock(tmp_path: Path) -> None:
    result = invoke_cli(["collect", "--split", "test", "--threshold-lock", str(tmp_path / "missing.json")])
    assert result.exit_code == 2
    assert "TEST_SEALED" in result.stderr


def test_dry_run_selects_exactly_two_per_scenario_and_is_non_formal() -> None:
    plan = build_dry_run_plan(inventory())
    assert len(plan.samples) == 8
    assert Counter(item.scenario for item in plan.samples) == {scenario: 2 for scenario in DatasetScenario}
    assert plan.formal is False
```

Also inspect `setup.py` and assert exactly one `perception_benchmark = so101_demo.cli.perception_benchmark:main` entry and that installed resources include `config/perception_benchmark/benchmark.yaml`.

- [ ] **Step 2: Run CLI tests and confirm RED**

Run:

```zsh
/Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider \
  src/so101_demo_py/test/test_perception_benchmark_cli.py -q
```

Expected: missing CLI module/entrypoint.

- [ ] **Step 3: Add exact config and CLI argument gates**

Config must contain the exact dataset/model SHA/revisions, both grids, production Grounded-SAM values, low-floor values, FP32/device/fallback/offline requirements, warm-up `5`, cold process count `3`, bootstrap seed `20260902`, repetitions `10000`, durable/debug roots, and run order. YOLO production NMS remains `source: resolved_ultralytics_predictor_args`; no guessed numeric value is committed.

```python
def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        return arguments.handler(arguments)
    except BenchmarkError as error:
        print(f"{error.code}: {error.detail}", file=sys.stderr)
        return 2
```

The collect command requires explicit `--run-id`、`--platform`、`--model`、`--device`、`--split`、`--run-kind`、`--dataset-inventory`、model asset path/SHA, `--output-root` and exact source commit. `--split test` requires a verified `--threshold-lock`; `ORACLE_DIAGNOSTIC` is always labeled and cannot write threshold-lock.

Create the exact dry-run fixture as:

```json
{
  "schema_version": "so101-perception-benchmark/dry-run-fixture-v1",
  "candidate_counts_by_scenario": {
    "no_cup": 0,
    "one_cup_distractors": 1,
    "two_cups": 2,
    "cup_near_bottle": 1
  },
  "models": ["yolo_seg", "grounded_sam"],
  "ranking_scores": [0.91, 0.82],
  "sam_quality": 0.88
}
```

The fixture adapter creates deterministic rectangular masks from the scenario and formal sample index; it is accepted only with `dry-run`, never with `collect`.

- [ ] **Step 4: Prewrite the new ledger before any external execution**

Create the ledger header with:

```yaml
task_id: so101-grounded-sam-yolo-seg-benchmark-20260902-ab-v1
goal: 同数据同指标完成 YOLO-Seg 与 Grounded-SAM 双平台 RGB 实例分割 A/B benchmark
success_contract: 两平台两模型完整 val 200 与 test 200；无跳样本；threshold-lock 只读 val；全部证据 SHA 可回读
worktree: /Users/matianyi/.codex/worktrees/5b15/moveit-demo
branch: codex/v5-t004-yolo-seg-rgbd
evidence_root: /data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1
latest_checkpoint: CP-BENCH-001
next_experiment: EXP-BENCH-001
```

At implementation time insert actual `base_commit` and `current_commit` from explicit linked-worktree Git. Prewrite distinct `PLANNED` entries for asset verification/dry run, Mac val, Linux val, calibration/lock, Mac test, Linux test, performance/cross-platform/report, and Task 11 remediation proposal. Each entry uses only the legal four states and includes exact commands/evidence paths before the command runs.

- [ ] **Step 5: Build/install and run the 8-image non-formal dry run**

Use `--dry-run` fakes first in unit tests, then actual installed CLI on 2 fixed image-SHA samples per scenario. It may validate both actual model adapters only after asset staging is verified; until Task 11, use recorded fake adapters and label output `NON_FORMAL_DRY_RUN`. Command:

```zsh
/Users/matianyi/ros2_jazzy/.venv/bin/colcon build \
  --packages-select so101_demo_py --symlink-install \
  --build-base build-benchmark --install-base install-benchmark --log-base log-benchmark
source install-benchmark/setup.zsh
perception_benchmark dry-run \
  --config install-benchmark/so101_demo_py/share/so101_demo_py/config/perception_benchmark/benchmark.yaml \
  --dataset-inventory /tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/dataset/inventory.json \
  --output-root /tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/dry-run \
  --adapter-fixture src/so101_demo_py/test/fixtures/perception_benchmark/dry-run-adapters.json
```

Expected: exit 0; exactly 8 records, two per scenario, `formal=false`, evidence index verifies. Do not include dry-run records in val/test inventories.

- [ ] **Step 6: Run focused CLI plus all benchmark tests**

Run:

```zsh
/Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider \
  src/so101_demo_py/test/test_perception_benchmark_*.py -q \
  --junitxml=/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests/benchmark-focused.xml
```

Expected: non-zero test collection, zero failures/errors, JUnit under the registered debug root.

- [ ] **Step 7: Commit Task 9**

```zsh
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo add -- \
  src/so101_demo_py/src/cli/perception_benchmark.py \
  src/so101_demo_py/config/perception_benchmark/benchmark.yaml \
  src/so101_demo_py/test/fixtures/perception_benchmark/dry-run-adapters.json \
  src/so101_demo_py/setup.py \
  src/so101_demo_py/test/test_perception_benchmark_cli.py \
  docs/experiments/grounded-sam-yolo-seg-benchmark-experiment-ledger.md
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo commit -m "feat: add perception benchmark CLI"
```

### Task 10: Mac/Linux package gates 与 isolated exact-source deployment

**Files:**
- Modify: `docs/experiments/grounded-sam-yolo-seg-benchmark-experiment-ledger.md`
- Evidence only: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests/`
- Evidence only: `/data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/tests/`

**Interfaces:**
- Consumes: Tasks 1–9 committed source and tests。
- Produces: Mac and Linux package JUnit/test-result evidence；exact-source isolated Linux checkout and install provenance。

- [ ] **Step 1: Record local/remote provenance and process ownership read-only**

Mac exact linked-worktree commands:

```zsh
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo rev-parse HEAD
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo status --short
pgrep -af "perception_benchmark|move_group|rviz2|gz sim" || true
ssh -o BatchMode=yes ai-station 'hostname; zsh -lc "cd /data/work/ws_moveit && git rev-parse HEAD && git status --short"; pgrep -af "perception_benchmark|move_group|rviz2|gz sim" || true'
```

Expected: preserve all existing dirty paths/processes; do not start a second stack. Append observed commit/status/process facts to `EXP-BENCH-001` before changing it to `RUNNING`.

- [ ] **Step 2: Run Mac focused then package-level gate with correct overlays**

```zsh
cd /Users/matianyi/.codex/worktrees/5b15/moveit-demo
eval "$(direnv export zsh)"
source /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/setup.zsh
source install-benchmark/setup.zsh
export ROS_HOME=/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests/mac-ros-home
export ROS_LOG_DIR=$ROS_HOME/log
mkdir -p "$ROS_LOG_DIR"
PYTHONNOUSERSITE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -c 'import rclpy; print(rclpy.__file__)'
PYTHONNOUSERSITE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest \
  -p no:cacheprovider src/so101_demo_py/test -q \
  --junitxml=/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests/mac-so101_demo_py.xml
/Users/matianyi/ros2_jazzy/.venv/bin/colcon test-result \
  --test-result-base /tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests --verbose
```

Expected: `rclpy` imports from ROS Jazzy, non-zero tests collected, pytest exit 0, errors/failures 0.

- [ ] **Step 3: Create and verify an exact-source bundle without touching canonical checkout**

```zsh
source_sha=$(git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo rev-parse HEAD)
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo bundle create \
  /tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/source.bundle "$source_sha"
sha256sum /tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/source.bundle
scp /tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/source.bundle ai-station:/data/work/so101-grounded-sam-yolo-benchmark-source.bundle
```

On ai-station, clone the bundle into `/data/work/so101-grounded-sam-yolo-benchmark-ab-v1`, checkout the exact SHA printed above, verify clean status, and read back bundle/source SHA. If that path exists, stop and register a new explicit path instead of overwriting it. Retain the isolated checkout; do not delete it.

- [ ] **Step 4: Build and run Linux package gate in ROS-only zsh**

```zsh
ssh ai-station 'zsh -lc "source /opt/ros/jazzy/setup.zsh; cd /data/work/so101-grounded-sam-yolo-benchmark-ab-v1; colcon build --packages-select so101_demo_py --symlink-install --build-base build-benchmark --install-base install-benchmark --log-base log-benchmark; source install-benchmark/setup.zsh; ros2 pkg prefix so101_demo_py; PYTHONNOUSERSITE=1 colcon test --packages-select so101_demo_py --build-base build-benchmark --install-base install-benchmark --log-base log-benchmark --event-handlers console_direct+; colcon test-result --test-result-base build-benchmark --verbose"'
```

Expected: installed prefix belongs to isolated checkout, non-zero tests, zero errors/failures. Copy Linux JUnit/test-result summaries into durable `tests/linux/` and build an immutable evidence index.

- [ ] **Step 5: Update the ledger checkpoint and commit only the ledger**

Mark package-gate experiment `VALID` only when both platform gates and source/install/runtime provenance pass; otherwise `INVALID` with exact first bad boundary. Record retained isolated checkout, no archived runs, and deletion candidates without deleting them.

```zsh
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo add -- \
  docs/experiments/grounded-sam-yolo-seg-benchmark-experiment-ledger.md
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo commit -m "test: verify benchmark package gates"
```

### Task 11: Fixed asset staging、SHA readback 与正式实验预注册

**Files:**
- Modify: `docs/experiments/grounded-sam-yolo-seg-benchmark-experiment-ledger.md`
- Evidence only: `/data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/assets/`
- Evidence only: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/assets/`

**Interfaces:**
- Consumes: package-gated exact source；fixed dataset/YOLO/bundle SHA values。
- Produces: immutable asset inventories on both platforms；prewritten formal experiments `EXP-BENCH-VAL-MAC`、`EXP-BENCH-VAL-LINUX`、`EXP-BENCH-CALIBRATE`、`EXP-BENCH-TEST-MAC`、`EXP-BENCH-TEST-LINUX`、`EXP-BENCH-PERFORMANCE`、`EXP-BENCH-REPORT`。

- [ ] **Step 1: Set all formal experiment entries to PLANNED before asset/runtime commands**

For each entry freeze: hypothesis, prediction, single variable, lifecycle `ISOLATED_STACK`, exact 200-image inventory SHA, platform/model/run kind, source commit, install overlay, runtime executable, device/dtype, asset/config SHA, output path, success/failure/invalid criteria, exact command, retained classification and next experiment. Keep `ROS_DOMAIN_ID` and `GZ_PARTITION` as `NONE` because this offline RGB benchmark launches no ROS graph or Gazebo; write those literal values rather than omitting provenance fields.

- [ ] **Step 2: Verify repository dataset archive and build read-only extraction**

```zsh
cd /Users/matianyi/.codex/worktrees/5b15/moveit-demo
shasum -a 256 datasets/so101-v5-t004-yolo-seg-synthetic/so101-v5-t004-yolo-seg-synthetic-20260831-f09cf88.tar.gz
source install-benchmark/setup.zsh
perception_benchmark prepare-dataset \
  --archive datasets/so101-v5-t004-yolo-seg-synthetic/so101-v5-t004-yolo-seg-synthetic-20260831-f09cf88.tar.gz \
  --expected-sha256 c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1 \
  --output-root /tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/dataset
```

Expected: val/test inventories each 200 with 50/50/50/50 scenarios; all extracted regular files read-only; inventory SHA recorded before test truth remains sealed from calibration commands.

- [ ] **Step 3: Verify and stage YOLO weight without overwriting**

Find the existing ai-station evidence path from the V5-T004 ledger, read-only verify it, and copy only when destination does not exist:

```zsh
ssh ai-station 'zsh -lc "sha256sum /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/training/full-exp-012/best.pt; test ! -e /data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/assets/best.pt"'
scp ai-station:/data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/training/full-exp-012/best.pt \
  /tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/assets/best.pt
shasum -a 256 /tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/assets/best.pt
```

Expected SHA is `f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781` on source, Mac staging and Linux durable destination. A pre-existing destination is verified and reused only when SHA matches; mismatch stops the experiment as `INVALID`.

- [ ] **Step 4: Verify Grounded-SAM bundle on both platforms offline**

Mac bundle is `/Users/matianyi/Models/so101/grounded-sam-v1`; Linux bundle is `/data/work/so101-models/grounded-sam-v1`. Run the installed verifier with `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` and expected manifest SHA `838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3`. Verify manifest declares exact DINO/SAM revisions and every bundle file SHA; reject symlinks and network access.

- [ ] **Step 5: Verify lock/source/environment provenance and write asset indexes**

Record SHA of `src/so101_demo_py/config/perception/requirements.lock`, `torch/ultralytics/transformers/Pillow/PyYAML` versions, OS/CPU/GPU/driver/CUDA/MPS, actual `cuda`/`mps`, FP32, `fallback_used=false`, exact source and installed CLI path. Copy the verified dataset archive, dataset inventory, Mac asset inventory and Linux asset inventory into the durable `assets/` tree only when their destinations are absent; write one canonical durable inventory and read every file back by SHA.

- [ ] **Step 6: Update ledger and commit asset-registration checkpoint**

Asset experiment is `VALID` only if every fixed SHA/revision/device/offline check succeeds. Record retained asset indexes and source assets; classify stale Mac staging/isolated checkout as deletion candidates without deletion.

```zsh
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo add -- \
  docs/experiments/grounded-sam-yolo-seg-benchmark-experiment-ledger.md
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo commit -m "docs: register benchmark assets"
```

### Task 12: 双平台 val 低门槛完整采集

**Files:**
- Modify: `docs/experiments/grounded-sam-yolo-seg-benchmark-experiment-ledger.md`
- Evidence only: `/data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/val/`
- Evidence only: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/val/`

**Interfaces:**
- Consumes: verified assets, exact val inventory, installed CLI/adapters。
- Produces: four immutable 200-record val raw runs: Mac YOLO/MPS, Mac Grounded-SAM/MPS, Linux YOLO/CUDA, Linux Grounded-SAM/CUDA；record inventories and SHA readback。

- [ ] **Step 1: Transition only Mac val experiments from PLANNED to RUNNING after provenance recheck**

Re-read source/install/runtime, empty output destination, asset/config/inventory SHA, no owned benchmark process, MPS availability, FP32 and fallback false. Record start time and model execution order. First performance-order block runs YOLO then Grounded-SAM; the paired later platform begins Grounded-SAM then YOLO to expose order bias.

- [ ] **Step 2: Run Mac YOLO val low-floor once**

```zsh
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 perception_benchmark collect \
  --run-id mac-yolo-val-raw-ab-v1 --platform macos --model yolo_seg --device mps \
  --dtype float32 --split val --run-kind VAL_RAW \
  --dataset-inventory /tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/dataset/inventory.json \
  --weights /tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/assets/best.pt \
  --weights-sha256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781 \
  --config install-benchmark/so101_demo_py/share/so101_demo_py/config/perception_benchmark/benchmark.yaml \
  --source-commit "$(git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo rev-parse HEAD)" \
  --output-root /tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/val/mac-yolo
```

Expected: 200 unique `OK|ERROR` records in fixed image-SHA order; every record preserves low-floor raw candidates; device `mps`, fallback false. Individual model errors do not change the 200 denominator.

- [ ] **Step 3: Run Mac Grounded-SAM val low-floor once**

Run the Step 2 command again with `--run-id mac-grounded-sam-val-raw-ab-v1 --model grounded_sam --model-root /Users/matianyi/Models/so101/grounded-sam-v1 --manifest-sha256 838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3` and output `--output-root /tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/val/mac-grounded-sam`; remove the three YOLO weight arguments. Expected: 200 records; raw candidates include DINO grounding score, text score and SAM quality; stateless frame count equals 200; no video tracking state.

- [ ] **Step 4: Upload Mac val evidence to durable root and SHA read back**

Generate an immutable per-file inventory, transfer into `val/macos/` only when destination is absent, then remote-run `perception_benchmark verify-evidence` against that inventory. Local staging is not used as final report source after readback.

- [ ] **Step 5: Transition Linux val experiments to RUNNING and collect in opposite model order**

From isolated exact checkout, run Grounded-SAM then YOLO with identical inventory order/low-floor/config, `--device cuda --dtype float32`, Linux asset paths, output directly to `val/linux/`. Before each run, verify no concurrent benchmark process uses the GPU and capture background load/resource sampler metadata.

- [ ] **Step 6: Validate all four val runs without calibrating yet**

For each model/platform assert exactly 200 distinct image SHAs, four scenarios 50 each, record/mask SHA valid, no CPU/fallback, same dataset/config/source SHA, errors retained. Mark each experiment `VALID` or `INVALID`; any invalid run blocks Task 13 and is never silently resumed under the same run ID.

- [ ] **Step 7: Update checkpoint and commit ledger only**

Record run counts/errors/order/resource gaps, durable indexes, retained/archived/deletion candidates and exact next command. Commit message: `docs: record benchmark val collection`.

### Task 13: 合并双平台 val 标定并冻结 threshold-lock

**Files:**
- Modify: `docs/experiments/grounded-sam-yolo-seg-benchmark-experiment-ledger.md`
- Evidence only: `/data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/calibration/`

**Interfaces:**
- Consumes: four `VALID` val record inventories only；no test truth/predictions。
- Produces: YOLO and Grounded-SAM threshold-locks, calibration surfaces, access log proving test remained sealed。

- [ ] **Step 1: Verify val inputs and precondition the calibration experiment**

Require all four val manifests `VALID`, exact 200 records each, verified SHA, matching val inventory, test access log empty, output directory absent, no model process. Transition `EXP-BENCH-CALIBRATE` to `RUNNING` only after recording these facts.

- [ ] **Step 2: Run joint-platform calibration for YOLO**

```zsh
perception_benchmark calibrate \
  --model yolo_seg \
  --mac-record-inventory /data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/val/macos/yolo/evidence-index.json \
  --linux-record-inventory /data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/val/linux/yolo/evidence-index.json \
  --val-inventory-sha256 "$(perception_benchmark verify-evidence --print-inventory-sha /data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/dataset/val-inventory.json)" \
  --bootstrap-seed 20260902 --bootstrap-repetitions 10000 \
  --output-root /data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/calibration/yolo
```

Expected: all exact grid points evaluated with shared objective/tie-break; one lock plus its SHA; outcome is either safe calibrated or explicitly unsafe characterization.

- [ ] **Step 3: Run joint-platform calibration for Grounded-SAM**

Run the same command with Grounded-SAM val inventories and output `calibration/grounded-sam`. Expected: one common cross-platform lock, no platform-specific threshold.

- [ ] **Step 4: Seal and verify locks before test access**

Run `perception_benchmark verify-evidence` on both calibration directories, independently recompute lock SHA, compare embedded grid/input inventories/code commit, and append `threshold-lock-created` to access log. Then chmod lock/config/inventory files read-only. Only now can `TestSeal.open_truth("test")` succeed.

- [ ] **Step 5: Mark calibration VALID/INVALID and commit ledger checkpoint**

An unsafe but correctly characterized lock is a `VALID` run with `outcome=UNSAFE_CALIBRATION_NO_FEASIBLE_POINT`, not `INVALID`. A test access before lock, changed val input or lock SHA mismatch is `INVALID`. Commit message: `docs: freeze benchmark threshold locks`.

### Task 14: Threshold-lock 后的双平台 test raw、production 与 calibrated runs

**Files:**
- Modify: `docs/experiments/grounded-sam-yolo-seg-benchmark-experiment-ledger.md`
- Evidence only: `/data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/test/`
- Evidence only: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/test/`

**Interfaces:**
- Consumes: verified threshold-locks, exact test inventory, fixed assets/source/config。
- Produces per platform/model: one low-floor `ORACLE_DIAGNOSTIC` 200-image run; one production `DetectorPort` 200-image contract/performance run; one calibrated/characterization 200-image performance/contract run；fixed production/calibrated decision replay from the diagnostic raw records。

- [ ] **Step 1: Verify threshold-lock and open test exactly once per experiment**

Record lock SHA/access event before loading test truth or image paths. Recheck all assets/source/install/device and output absence. If any test artifact timestamp predates the lock event, mark the run `INVALID`.

- [ ] **Step 2: Run Mac test in preregistered interleaved order**

For YOLO and Grounded-SAM, execute in the preregistered order; every production/calibrated model process performs at least five excluded warm-up images, synchronizes its device boundaries, and saves the formal 200-image timing/resource stream:

1. `TEST_RAW_ORACLE` low-floor diagnostic on all 200 images, labeled `ORACLE_DIAGNOSTIC`;
2. `TEST_PRODUCTION` on all 200 images through `build_detector(factory_options).detector.detect(frame, DetectionQuery("plastic_cup"))` and actual `TargetSelector`;
3. `TEST_CALIBRATED` or `TEST_CHARACTERIZATION` on all 200 images with the frozen lock, without changing the lock.

The diagnostic record is the source for raw AP and immutable production/calibrated replay. Production `DetectorPort` decisions must equal production replay for the same image or the run is `INVALID`. Calibrated performance run decisions must equal calibrated replay. Each run has 200 records; they are separate run IDs and are never combined into a 600-image denominator.

- [ ] **Step 3: Validate Mac test and upload/read back durable evidence**

Verify six run manifests (2 models x 3 run kinds), their record/mask inventories and performance/resource streams, exact sample order, no fallback and full denominator. Transfer immutable Mac evidence into `test/macos/`, verify remote SHA, then use durable copies for aggregation.

- [ ] **Step 4: Run Linux test in the opposite model order**

Use the same three run kinds, locks, image SHA order and source/config/assets on CUDA. Do not run YOLO and Grounded-SAM concurrently. Record device synchronization and model order. Production again must pass actual `DetectorPort`/`TargetSelector`, not benchmark replay alone.

- [ ] **Step 5: Validate formal-vs-oracle separation and no test tuning**

Assert threshold-lock SHAs unchanged; no command wrote calibration output; `ORACLE_DIAGNOSTIC` is excluded from ranking/safety conclusions; production and calibrated results remain separate. A formal run with missing sample, changed threshold, fallback or replay/DetectorPort disagreement becomes `INVALID`.

- [ ] **Step 6: Update ledger and commit test checkpoint**

Record each run state/outcome/error counts and exact evidence index. Commit message: `docs: record frozen benchmark test runs`.

### Task 15: Cold/warmed/per-phase/resources 与 cross-platform evidence

**Files:**
- Modify: `docs/experiments/grounded-sam-yolo-seg-benchmark-experiment-ledger.md`
- Evidence only: `/data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/performance/`

**Interfaces:**
- Consumes: Task 14 valid formal configurations and exact inventories。
- Produces: cold/warmed/per-phase/resource raw streams and platform consistency input; no accuracy sample selection。

- [ ] **Step 1: Verify the preregistered Task 14 paired order and thermal/load/sampler state**

Read the Task 14 start/end resource samples and confirm the paired order: half of the formal blocks ran YOLO then Grounded-SAM, half ran the reverse. Verify that available CPU/GPU utilization, temperature, power, background load and sampler tool versions were recorded and that no two models shared one GPU concurrently. Resource values unavailable on a platform remain `null` with reason.

- [ ] **Step 2: Run at least three fresh-process cold measurements per model/config/platform**

Each process verifies assets/offline/device/fallback, loads model and processes the first preregistered shape/image. Record process start to first result, model load, first compile/optimization separately. Cold images are not inserted into the 200-image accuracy denominator.

- [ ] **Step 3: Validate Task 14 warmed measurements without rerunning the 200-image accuracy matrix**

For every Task 14 formal production/calibrated run, require one model load, at least five formal-shape warm-up images excluded from metrics, CUDA/MPS synchronization at every boundary and exactly 200 timed images in fixed order. Preserve each image's `preprocess_ms`、`dino_or_yolo_ms`、`sam_ms`、`postprocess_ms`、`selector_ms`、`total_ms` and wall throughput. Errors retain completed phase times and null later phases. If any gate is missing, mark the formal run `INVALID`; do not rerun it under the same run ID or select a better repetition.

- [ ] **Step 4: Capture peak and sampled resources**

Sample from load through warm-up and inference: RSS, CPU, available CUDA allocated/reserved/utilization/temp/power or MPS allocated/RSS. Save interval and gaps. Use process-owned samplers and stop only their recorded PIDs.

- [ ] **Step 5: Produce and verify cross-platform per-image comparison input**

For every same model/config/image pair, verify stable IDs/order, compare candidate count, confidence delta, box IoU, mask IoU, decision and error type. Preserve full mismatch list. Do not remove mismatches as “floating point noise.”

- [ ] **Step 6: Update ledger and commit performance checkpoint**

Mark performance experiment `VALID` only with >=3 cold processes, >=5 warm-ups, 200 warmed samples per model/config/platform, synchronization evidence and traceable samplers. Commit message: `docs: record benchmark performance evidence`.

### Task 16: Final metrics/report、humanizer-zh、durable readback 与 ledger checkpoint

**Files:**
- Create: `docs/reports/grounded-sam-yolo-seg-benchmark-report.md`
- Modify: `docs/experiments/grounded-sam-yolo-seg-benchmark-experiment-ledger.md`
- Evidence only: `/data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/final/`

**Interfaces:**
- Consumes: all verified VAL/TEST/performance/calibration evidence；Tasks 3/4/8 aggregation APIs。
- Produces: machine JSON/CSV, human report, evidence index, complete durable readback, final benchmark status and Task 11 remediation proposal。

- [ ] **Step 1: Aggregate only valid preregistered runs**

```zsh
perception_benchmark aggregate \
  --evidence-root /data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1 \
  --yolo-threshold-lock /data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/calibration/yolo/threshold-lock.json \
  --grounded-sam-threshold-lock /data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/calibration/grounded-sam/threshold-lock.json \
  --bootstrap-seed 20260902 --bootstrap-repetitions 10000 \
  --output-root /data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/final
```

Expected: main test table has Linux/Mac x YOLO/Grounded-SAM x production/calibrated-or-characterization, each sample count 200; all four scenarios count 50. Val stays in calibration appendix; oracle stays in diagnostics appendix.

- [ ] **Step 2: Generate complete machine and human report**

The report must explicitly include every spec §7 metric, 95% CI, error counts, full 3x4 decision confusion, exact count/safety metrics, cold/warm/per-phase/resource values, cross-platform mismatch list, production vs calibrated separation, oracle exclusion, fixed assets/provenance, dataset convex-hull limitation, absence of bottle mask, and the RGB-only non-goals for Depth/TF/`/cup_pose`/Pick & Place.

- [ ] **Step 3: Apply project-local humanizer-zh to Chinese report prose**

Read `.agents/skills/humanizer-zh/SKILL.md` completely, revise only Chinese explanatory prose, and preserve all commands, identifiers, paths, SHA values, model IDs/revisions, metrics, citations, links, JSON field names and conclusions exactly. Compare extracted code blocks/inline literals/link targets before and after; any difference blocks commit.

- [ ] **Step 4: Verify durable readback and evidence inventory**

Run `perception_benchmark verify-evidence` against final `evidence-index.json`; independently SHA every indexed file and confirm Mac-uploaded files match their local immutable inventory. Record files/count/bytes, retained runs, archived runs, deletion candidates, Mac durable status and any unavailable evidence reason. Do not delete anything.

- [ ] **Step 5: Decide overall benchmark validity without preselecting a winner**

Overall is `VALID` only if both platforms/two models complete val/test/full metrics, all fixed assets and evidence read back, no fallback/leakage and all required sample counts hold. A valid characterization may still conclude neither model has a deployable safe threshold. Unsafe unique rate >0 on frozen test prohibits a Pick & Place safe claim even if AP is high.

- [ ] **Step 6: Write Task 11 append-only remediation proposal, not ledger mutation**

Create a report section that maps old composite states to `PLANNED/RUNNING/VALID/INVALID`, lists the r8/r9 known scores, specifies low-floor replay fields and states whether Task 11 probe image SHA belongs to the formal inventory. Provide a separate proposed append-only patch and exact next experiment, but do not edit `docs/experiments/v5-t005-grounded-sam-rgbd-experiment-ledger.md`. State that applying the proposal or rerunning Task 11 needs new authorization.

- [ ] **Step 7: Update final checkpoint and commit report/ledger**

```zsh
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo add -- \
  docs/reports/grounded-sam-yolo-seg-benchmark-report.md \
  docs/experiments/grounded-sam-yolo-seg-benchmark-experiment-ledger.md
git --git-dir=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 \
  --work-tree=/Users/matianyi/.codex/worktrees/5b15/moveit-demo commit -m "docs: report Grounded SAM YOLO benchmark"
```

### Task 17: Independent final review、full verification 与 Task 11 return decision

**Files:**
- Review: all files committed by Tasks 1–16
- Review: `docs/superpowers/specs/2026-09-02-grounded-sam-yolo-seg-benchmark-design.md`
- Review: `/data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/final/evidence-index.json`
- Modify only if findings require scoped fixes: owning source/test/report/ledger files

**Interfaces:**
- Consumes: complete implementation, tests, reports and immutable evidence。
- Produces: independent Critical/Important/Minor review; verified final status; a recommendation to return/not return to Task 11, without automatically editing the old ledger。

- [ ] **Step 1: Dispatch a fresh independent reviewer with spec and evidence gates**

Reviewer checks: schema immutability/null semantics, archive/traversal, Pillow rasterization, RLE SHA, Hungarian/ties/AP/bootstrap, full denominator/errors, decision safety, val/test seal, joint tie-break, DetectorPort production proof, raw/formal/oracle separation, source/install/runtime provenance, offline/fallback/device, sample counts, performance synchronization/order/resource gaps, cross-platform mismatch list, evidence SHA/readback, report claims and old-ledger non-modification.

- [ ] **Step 2: Fix each accepted finding with a new RED/GREEN cycle**

For a code finding, add the smallest named regression test in the owning `test_perception_benchmark_*.py`, observe failure, patch the owning single-responsibility module, run focused tests, and use a concrete commit message such as `fix: preserve benchmark full denominator`. For a report/ledger finding, patch only the wrong statement/record and rerun link/literal/evidence checks. Do not rewrite experimental history.

- [ ] **Step 3: Run final Mac package gate**

Repeat Task 10 Mac direct package pytest with a new JUnit path under `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests/final/`, verify non-zero tests and zero failures/errors, then verify installed CLI prefix and exact source commit.

- [ ] **Step 4: Run final Linux package gate at the same exact commit**

Transfer only the reviewed source delta to a new isolated exact checkout or rebuild the existing isolated checkout only if its status is clean and commit matches. Run standard Linux `colcon test`, collect JUnit/test-result into durable `tests/final/linux/`, and verify source/install/runtime provenance. Never touch `/data/work/ws_moveit` dirty files.

- [ ] **Step 5: Re-run evidence and report consistency checks without rerunning accuracy**

Verify all immutable record/lock/report indexes and denominators. Do not rerun or cherry-pick a better 200-image accuracy result during review. If a code fix changes metric semantics or prediction records, invalidate the affected formal run and request authorization for a new run ID; do not silently regenerate.

- [ ] **Step 6: Make the Task 11 return recommendation**

Recommend full Task 11 return only if val on both platforms has unsafe unique rate 0, frozen test on both platforms has unsafe unique rate 0, Task 11 no/one/two-cup probe has a non-conflicting threshold interval, and complete raw/mask provenance reads back. Otherwise recommend “当前模型/提示词/阈值组合没有可接受安全区间” and require a new design for prompt/model/fine-tune changes. This is a proposal only; old ledger modification and Task 11 execution remain separately authorized.

- [ ] **Step 7: Commit final review corrections and report workspace state**

Run explicit linked-worktree `status --short`, `diff --check`, and `log -1 --oneline`; ensure existing untracked build/install/log paths remain untouched. Report final tests, evidence retained/archived/deletion candidates, review finding counts, current commit, and no push/merge.

## Spec Coverage Matrix

| Spec section | Implemented/verified by |
| --- | --- |
| §1–2 purpose/non-goals | Global Constraints, Tasks 8, 16 |
| §3 fixed assets/provenance | Tasks 9, 11, 12, 14 |
| §4 responsibilities/DetectorPort | File Map, Tasks 6, 7, 14 |
| §5 immutable truth/prediction schema | Tasks 1, 2, 7 |
| §6 Hungarian/AP/empty truth | Task 3 |
| §7 accuracy/decision/performance/cross-platform | Tasks 3, 4, 8, 15, 16 |
| §8 production/calibrated/low-floor/grid/tie-break | Tasks 5, 6, 12–14 |
| §9 full matrix/warm/cold/order/resources | Tasks 12, 14, 15 |
| §10 evidence roots/new ledger/readback | Tasks 9–16 |
| §11 Task 11 remediation/return gates | Tasks 16, 17 |
| §12 record ERROR/run INVALID rules | Tasks 1, 7, 12–15 |
| §13 unit/component/8-image dry run | Tasks 1–9 |
| §14 ten acceptance gates | Tasks 10–17 |
| §15 implementation file scope | File Map, Tasks 1–9 |
| §16 publication/runtime boundaries | Global Constraints, Tasks 10–17 |
| §17 related-document link integrity | final self-review and Task 17 |

## Plan Self-Review Before Execution

- [ ] Spec coverage: re-read all 17 spec sections and verify every row above points to an executable task with exact evidence.
- [ ] Placeholder scan: build the forbidden-pattern expression outside the plan from the writing-plans skill's “No Placeholders” list, then run `rg -n "$forbidden_plan_patterns" docs/superpowers/plans/2026-09-02-grounded-sam-yolo-seg-benchmark.md`; expected: no matches.
- [ ] Type/signature consistency: verify every `Consumes` symbol is produced by an earlier task and names match exactly: `PredictionRecord`、`RawCandidate`、`DatasetInventory`、`ThresholdLock`、`RawDetectionResult`、`RunManifest`、`BenchmarkSummary`。
- [ ] Literal/config consistency: verify all three fixed asset SHAs, two model revisions, four scenarios, sample counts, devices, FP32, warm-up/cold counts, bootstrap seed/repetitions and evidence roots match the approved spec exactly.
- [ ] Link scan: run `python3 -c 'from pathlib import Path; import re; files=(Path("docs/superpowers/plans/2026-09-02-grounded-sam-yolo-seg-benchmark.md"),Path("docs/superpowers/specs/2026-09-02-grounded-sam-yolo-seg-benchmark-design.md")); missing=[str((path.parent/target).resolve()) for path in files for target in re.findall(r"\[[^]]+\]\(([^)#]+)(?:#[^)]+)?\)",path.read_text()) if "://" not in target and not (path.parent/target).resolve().exists()]; assert not missing, missing'`; expected: every relative repository link resolves and no file is modified.
- [ ] Git diff check: run explicit linked-worktree `git diff --check` and `git status --short`; expected: no whitespace errors, no staged/untracked runtime artifacts added, and only intended plan/implementation scope appears per task.

## Execution Handoff

Plan execution defaults to **Subagent-Driven Development**. The orchestrator must use `superpowers:subagent-driven-development`, dispatch one fresh implementer per task, and perform spec-compliance then code-quality/evidence review before advancing. Tasks 12–17 are sequential evidence gates; no agent may run test before the shared threshold-lock is frozen, and no reviewer may rewrite or replace formal run evidence.

Plan complete and saved to `docs/superpowers/plans/2026-09-02-grounded-sam-yolo-seg-benchmark.md`. Recommended execution: Subagent-Driven, task-by-task with review checkpoints.
