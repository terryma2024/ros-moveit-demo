# SO-101 Head Search YOLO Calibration and Teleop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task in the existing ai-station worktree. Do not create another worktree or a second writer. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用一套正式、可审计、不可续跑的程序完成 head-camera YOLO 数据生成、A/B/C 模型选择、17 项 Head Search 参数校准、生产绑定和 Teleop 可视化，并通过串行 MuJoCo 资格验证。

**Architecture:** 所有代码先实现并通过定向门禁，再串行生成数据、训练和评测模型。模型选择冻结后，正式校准程序在 calibration-only admission 下测量并生成 head-only 资格产物；批准值写入生产配置后冻结唯一 runtime identity，最后运行 40 个串行场景和三个 anchor 各一次独立 `FULL_RESTART`。Teleop 只复用这一套生产 detector、head controller、lease 和 arbiter，不启动第二套感知或控制栈。

**Tech Stack:** Python 3、ROS 2 Jazzy、MuJoCo、ros2_control、Ultralytics YOLO11n-Seg、CUDA、NumPy、FastAPI/WebSocket、React 18、TypeScript、Bun/Vitest/Playwright、colcon/pytest。

**Spec:** `docs/superpowers/specs/2026-09-30-so101-head-search-yolo-calibration-teleop-design.md`

## Global Constraints

- 执行工作树固定为 `/home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a`，分支固定为 `codex/so101-act-data-0917a`；唯一代码写入者是 ai-station 上 `tmux` session `dst` 内的 DeepSeek Harness TUI。
- `dst` 收到整个计划后，在执行任何命令前先把本文 Task 1–14、当前边界和完成条件写入可见 task list。此后每个 turn 结束只更新既有条目的 status，不改写、重命名、合并、拆分、删除或补充条目内容。
- 执行器直接运行在 ai-station，不得从 ai-station 自我 SSH；Mac orchestrator 只做监视、审查和必要的只读检查。
- 唯一 durable evidence root 是 `/data/work/so101-evidence/act-data/20260924-fbc25063-resume`。普通低频日志放唯一 `/tmp/so101-debug-head-search-calibration/`；高频、模型、数据、测试 scratch 和资格证据全部进入登记 root。不得移动或删除既有 evidence。
- Head Search 不使用 Grounded-SAM。Grounded-SAM 不参与标签、筛选、复核、fallback、模型投票或运行时决策。
- 只允许 MuJoCo；全程 CUDA，`allow_cpu_fallback=false`。不得触及真实 SO-101。
- 当前任务不实现产品级并行执行。数据生成、训练、A/B/C 评测、正式校准、40 场景和三个 restart 全部串行；只允许一套 ROS/MuJoCo/YOLO stack 和一个 detector instance。
- 普通包测试按仓库门禁使用 pytest-xdist；这是测试运行器行为，不是产品并行支持。Task 1 和 Task 4 只运行正在修改的具名 benchmark 测试文件，完整 `benchmark_test` suite 只在 Task 4 和 Task 11 的明确集成边界运行；Task 12 运行的是冻结模型的真实数据比较入口。
- head-camera 数据固定为 train 800、val 200、test 200；四个场景各占 1/4。B 使用 800 张 head train；C 每个 epoch 使用 head 800 + task 800，batch 内 1:1 domain balance。
- A/B/C 都在冻结的 head test 与 task test 上评测。若 C 与最佳 head 候选等效且保留 task 能力，则选择 C；所有候选等效时也选择 C。
- 校准程序没有 resume、checkpoint replay 或阶段继续入口。失败 run 保持不可变；修复后使用新 run ID 从输入验证重新开始。sealed dataset 和未变化权重可以作为新 run 的只读输入。
- 资格验证固定为 40 个串行场景；之后 `default`、`left`、`forward` 各一次独立 `FULL_RESTART`，共三次，不要求连续五次。
- Task 13 完成最终配置提交和 runtime freeze 后，任何受控 source/config/policy、模型、camera、tracker 或依赖变化都会使旧 bundle、live evidence 和资格结论失效，必须用新 run root 重做 Task 13–14。
- README 使用英文并通过项目 `$humanizer`；本中文计划和设计使用 `$humanizer-zh`。账本和 evidence 不做文风改写。
- 每个代码 Task 都执行定向 RED、最小 GREEN、定向回归、精确 diff 审查和独立 commit。没有真实运行证据的 UT GREEN 不能关闭运行类 finding。
- 不 push，不使用 `gh`，不 force-push，不运行 `ament_uncrustify --reformat`，不清理用户 dirty work。

---

## Baseline, evidence, and test shell

执行 Task 1 前记录实际 `HEAD`、branch、dirty paths、submodule 状态、`dst` pane、goal 和账本 checkpoint。本文编写基线是设计终审提交 `06c26a7e646c2ebc13e3ae14b0ec8cc85b2677f9`；执行时以现场只读结果为准，不能用该哈希覆盖后续已有工作。

所有 ai-station pytest/colcon 命令使用同一 shell 中的以下辅助函数。每次测试都创建此前不存在的 NVMe scratch，并记录路径、elapsed、退出码、测试数和日志；scratch 只标记为 deletion candidate，不删除。

```zsh
set -o errexit -o pipefail
source /opt/ros/jazzy/setup.zsh
HEAD_EVIDENCE=/data/work/so101-evidence/act-data/20260924-fbc25063-resume
HEAD_PYTHON=$(python3 -c 'import sys; print(sys.executable)')
HEAD_COLCON=$(command -v colcon)
test -d "$HEAD_EVIDENCE" || exit 1
test -x "$HEAD_PYTHON" || exit 1
test -f "$HEAD_COLCON" || exit 1
"$HEAD_PYTHON" "$HEAD_COLCON" --help >/dev/null || exit 1
export HEAD_EVIDENCE HEAD_PYTHON HEAD_COLCON

head_colcon() {
  "$HEAD_PYTHON" "$HEAD_COLCON" "$@"
}

new_head_scratch() {
  mkdir -p "$HEAD_EVIDENCE/scratch"
  HEAD_SCRATCH=$(mktemp -d "$HEAD_EVIDENCE/scratch/head-test-XXXXXXXX") || return 1
  mkdir "$HEAD_SCRATCH/tmp" || return 1
  export TMPDIR="$HEAD_SCRATCH/tmp" TMP="$HEAD_SCRATCH/tmp" TEMP="$HEAD_SCRATCH/tmp"
  "$HEAD_PYTHON" -c 'import os,tempfile; from pathlib import Path; assert Path(tempfile.gettempdir()).resolve() == Path(os.environ["TMPDIR"]).resolve()' || return 1
  "$HEAD_PYTHON" -c 'import json,os,platform,sys,tempfile; print(json.dumps({"python":sys.executable,"tempdir":tempfile.gettempdir(),"cpu_count":os.cpu_count(),"platform":platform.platform()},sort_keys=True))' \
    >"$HEAD_SCRATCH/interpreter-and-cpu.json" || return 1
}

head_test() {
  new_head_scratch || return 1
  set -o pipefail
  set +o errexit
  /usr/bin/time -p "$HEAD_PYTHON" -m pytest -p no:cacheprovider \
    --junitxml="$HEAD_SCRATCH/pytest.junit.xml" "$@" \
    2>&1 | tee "$HEAD_SCRATCH/pytest.console.log"
  test_rc=$?
  set -o errexit
  print -r -- "$test_rc" >"$HEAD_SCRATCH/pytest.rc"
  print -r -- "scratch=$HEAD_SCRATCH rc=$test_rc"
  return $test_rc
}

run_logged() {
  log_path=$1
  shift
  set +o errexit
  "$@" 2>&1 | tee "$log_path"
  command_rc=$?
  set -o errexit
  print -r -- "$command_rc" >"$log_path.rc"
  return $command_rc
}

expect_head_red() {
  red_pattern=$1
  shift
  if head_test "$@"; then
    print -u2 -- "RED gate unexpectedly passed: $red_pattern"
    return 1
  fi
  rg -n "$red_pattern" "$HEAD_SCRATCH/pytest.console.log" >/dev/null || return 1
}
```

代码冻结前的正式 build/install 使用登记 root 下独立且完整的 build、install、log 三元组，先验证依赖 closure；不能把 underlay 缺失或包选择错误记为 source RED。

## File map

| Area | Files | Responsibility |
| --- | --- | --- |
| Camera geometry | `act/head_camera_geometry.py`, `cli/validate_head_camera_geometry.py`, `assets/mujoco/act/so101.xml` | 解决 `in_frame=0`，证明三个 anchor、required domain 和安全 neck 区间 |
| Dataset identity | `adapters/perception/mujoco_dataset.py`, `config/perception/head_camera_yolo_seg.yaml` | 消费 camera geometry seal，生成跨 domain `scene_group_id` 和 800/200/200 manifest |
| Training identity | `adapters/perception/yolo_training.py`, `cli/train_yolo_seg.py`, `act/head_search_training.py` | B/C 数据组合、1:1 domain balance、不可变 candidate manifest |
| Model evaluation | `perception_benchmark/head_search_models.py`, `cli/evaluate_head_search_yolo_candidates.py` | operating point 冻结、scene bootstrap、A/B/C 双 domain 比较和 verdict |
| Search geometry | `act/head_search_domain.py`, `act/search.py`, `act/head_search_binding.py` | required domain、双向有界停点、覆盖证明和终止状态 |
| Calibration | `act/head_search_calibration.py`, `cli/head_search_calibration.py` | 17 项算法、no-resume runner、bundle、config verification 和 qualify |
| Qualification bridge | `act/head_search_qualification.py`, `act/head_search_binding.py` | `HEAD_SEARCH_QUALIFIED` 闭合 report/sample 与既有 Task 8 隔离 |
| Teleop backend | `so101_teleop/head_camera.py`, `unified/ports.py`, `unified/compose.py`, `unified/app.py` | 单 detector frame envelope、受控位置命令、stop 和原子 capture |
| Teleop frontend | `web/src/api/head-camera-client.ts`, `components/teleop/head-camera-panel.tsx`, `app.tsx` | Raw/Overlay、状态、控制和 capture UI |
| Persistent docs | `src/so101_demo_py/README.md`, `docs/experiments/so101-act-data-experiment-ledger.md` | 权重来源、命令、决策、证据和删除候选 |

## Phase A — Implement and freeze the software

### Task 1: Freeze data, episode, and candidate contracts

**Files:**

- Create: `src/so101_demo_py/src/act/head_search_training.py`
- Create: `src/so101_demo_py/test/test_act_head_search_training.py`
- Modify: `src/so101_demo_py/src/perception_benchmark/contracts.py`
- Modify: `src/so101_demo_py/benchmark_test/test_perception_benchmark_contracts.py`

**Interfaces:** Consumes the existing YOLO dataset manifests. Produces `HeadSearchSplitSeal`, `CandidateIdentity`, `validate_scene_group_partition(...)`, and canonical JSON digests used by Tasks 2–4.

- [ ] **Step 1: Write RED tests for cross-domain leakage and candidate closure.**

```python
def test_scene_group_cannot_cross_camera_splits():
    head = {"scene-7": "train"}
    task = {"scene-7": "test"}
    with pytest.raises(ValueError, match="SCENE_GROUP_SPLIT_LEAK"):
        validate_scene_group_partition(head=head, task=task)

def test_candidate_identity_binds_operating_point_and_tracker():
    identity = CandidateIdentity.from_document(CANDIDATE)
    assert identity.weights_sha256 == "a" * 64
    assert identity.operating_point.min_confidence == 0.51
    assert identity.sha256 == canonical_sha256(identity.to_document())
```

- [ ] **Step 2: Run RED.**

```zsh
expect_head_red 'scene_group_cannot_cross|CandidateIdentity|candidate_identity_binds' \
  src/so101_demo_py/test/test_act_head_search_training.py \
  src/so101_demo_py/benchmark_test/test_perception_benchmark_contracts.py -q || exit 1
```

Expected: new symbols or new closed fields are missing; environment/import failures do not count as RED.

- [ ] **Step 3: Implement strict immutable contracts.**

```python
@dataclass(frozen=True, slots=True)
class CandidateIdentity:
    candidate_id: Literal["A", "B", "C"]
    weights_sha256: str
    head_operating_point: OperatingPoint
    task_operating_point: OperatingPoint
    postprocess_sha256: str
    tracker_sha256: str
    runtime_sha256: str
```

Require exact keys, finite values, lowercase SHA256, unique `scene_group_id`, mutually disjoint image splits, and mutually disjoint `calibration`, `held_out`, and `qualification` episode seed lists. Do not add Grounded-SAM fields.

- [ ] **Step 4: Run GREEN and commit.**

```zsh
head_test src/so101_demo_py/test/test_act_head_search_training.py \
  src/so101_demo_py/benchmark_test/test_perception_benchmark_contracts.py -q || exit 1
git add src/so101_demo_py/src/act/head_search_training.py \
  src/so101_demo_py/src/perception_benchmark/contracts.py \
  src/so101_demo_py/test/test_act_head_search_training.py \
  src/so101_demo_py/benchmark_test/test_perception_benchmark_contracts.py
git diff --cached --check
git commit -m "feat: define head search model identities"
```

### Task 2: Extend formal MuJoCo dataset generation for head camera

**Files:**

- Create: `src/so101_demo_py/src/act/head_camera_geometry.py`
- Create: `src/so101_demo_py/src/cli/validate_head_camera_geometry.py`
- Create: `src/so101_demo_py/config/act/head-camera-geometry-contract-v1.json`
- Create: `src/so101_demo_py/config/perception/head_camera_yolo_seg.yaml`
- Create: `src/so101_demo_py/src/cli/verify_head_search_dataset.py`
- Modify: `src/so101_demo_py/assets/mujoco/act/so101.xml`
- Modify: `src/so101_demo_py/config/mujoco/camera_views.yaml`
- Modify: `src/so101_demo_py/src/adapters/perception/mujoco_dataset.py`
- Modify: `src/so101_demo_py/src/cli/generate_yolo_seg_dataset.py`
- Modify: `src/so101_demo_py/setup.py`
- Modify: `src/so101_demo_py/test/test_act_task8_bottom_io_geometry.py`
- Modify: `src/so101_demo_py/test/test_yolo_seg_dataset.py`
- Modify: `src/so101_demo_py/test/test_yolo_seg_dataset_augmented.py`

**Interfaces:** `validate_head_camera_geometry` consumes the production MJCF/camera, three anchors and the frozen geometry matrix. It emits `head-camera-geometry.json` with the resolved `in_frame` matrix, `horizontal_fov_rad`, `lock_valid_neck_rad`, required search domain, safe neck interval and all source digests. Dataset generation refuses to run without that seal and produces the sealed 800/200/200 head-camera manifest with RGB, YOLO-Seg labels, raw masks, CameraInfo, camera pose, neck yaw and `scene_group_id`.

- [ ] **Step 1: Add RED tests for the production view, safe geometry, exact count and camera identity.**

```python
def test_production_head_camera_covers_geometry_matrix_at_all_anchors():
    result = validate_head_camera_geometry(PRODUCTION_SCENE, GEOMETRY_CONTRACT)
    assert result.in_frame_failures == []
    assert tuple(result.anchors) == ("default", "left", "forward")
    assert result.safe_interval_contains_required_domain

def test_head_camera_plan_has_four_balanced_scenarios():
    plan = split_scene_plan(camera_name="head_camera", counts={"train": 800, "val": 200, "test": 200})
    assert plan.counts("train") == {
        "no_cup": 200, "one_cup_distractors": 200,
        "two_cups": 200, "cup_near_bottle": 200,
    }
    assert all(item.camera_name == "head_camera" for item in plan.samples)
```

- [ ] **Step 2: Run RED and prove the intended camera/count assertions failed.**

```zsh
expect_head_red 'in_frame|geometry|head_camera|balanced_scenarios' \
  src/so101_demo_py/test/test_act_task8_bottom_io_geometry.py \
  src/so101_demo_py/test/test_yolo_seg_dataset.py \
  src/so101_demo_py/test/test_yolo_seg_dataset_augmented.py -q || exit 1
```

- [ ] **Step 3: Repair and freeze the production camera, then implement the fail-closed dataset profile.**

Make the minimal production-camera correction in `assets/mujoco/act/so101.xml` and its owned camera view so the real `head_camera` sees the target-support geometry; do not add a dataset-only camera. The validator renders the production scene headlessly over `default`, `left`, `forward`, both required-domain endpoints, the legal neck grid, target-support positions and occluder extrema. It rejects any `in_frame=0`, an unsafe swept segment, insufficient FOV-union coverage, camera/MJCF drift or a required domain outside the safe interval. The YAML freezes `camera_name: head_camera`, `640x480`, exact split counts, four scenario names, seed ranges, neck-yaw sampling and the accepted geometry-seal digest. `generate_dataset()` requires `--geometry-seal`, writes each sample's `scene_group_id`, camera intrinsics/extrinsics and raw instance-mask digest, and rejects missing CameraInfo, duplicate groups, split leakage, image/label count drift, non-head camera renders, a changed production-camera digest or an existing output root.

- [ ] **Step 4: Run GREEN and commit the formal programs.**

```zsh
head_test src/so101_demo_py/test/test_act_task8_bottom_io_geometry.py \
  src/so101_demo_py/test/test_yolo_seg_dataset.py \
  src/so101_demo_py/test/test_yolo_seg_dataset_augmented.py -q || exit 1
git add src/so101_demo_py/src/act/head_camera_geometry.py \
  src/so101_demo_py/src/cli/validate_head_camera_geometry.py \
  src/so101_demo_py/config/act/head-camera-geometry-contract-v1.json \
  src/so101_demo_py/config/perception/head_camera_yolo_seg.yaml \
  src/so101_demo_py/src/cli/verify_head_search_dataset.py \
  src/so101_demo_py/assets/mujoco/act/so101.xml \
  src/so101_demo_py/config/mujoco/camera_views.yaml \
  src/so101_demo_py/src/adapters/perception/mujoco_dataset.py \
  src/so101_demo_py/src/cli/generate_yolo_seg_dataset.py \
  src/so101_demo_py/setup.py \
  src/so101_demo_py/test/test_act_task8_bottom_io_geometry.py \
  src/so101_demo_py/test/test_yolo_seg_dataset.py \
  src/so101_demo_py/test/test_yolo_seg_dataset_augmented.py
git diff --cached --check
git commit -m "feat: generate sealed head camera datasets"
```

The installed camera-validation and 12-image dataset smokes run once at Task 11's integration boundary. Task 2 is not accepted as runtime-complete until those retained artifacts are read back there.

### Task 3: Make B/C training reproducible and domain-balanced

**Files:**

- Create: `src/so101_demo_py/config/perception/head_search_yolo_training.yaml`
- Modify: `src/so101_demo_py/src/act/head_search_training.py`
- Modify: `src/so101_demo_py/src/adapters/perception/yolo_training.py`
- Modify: `src/so101_demo_py/src/cli/train_yolo_seg.py`
- Modify: `src/so101_demo_py/test/test_yolo_training.py`
- Modify: `src/so101_demo_py/test/test_yolo_training_container.py`

**Interfaces:** Consumes sealed head/task dataset manifests and A's immutable `best.pt`. Produces B and C runtime YAML plus `candidate-manifest.json`; C's epoch sampler emits 800 head + 800 task samples at 1:1 batch balance.

- [ ] **Step 1: Add RED tests for B/C exposure parity and offline CUDA.**

```python
def test_mixed_candidate_uses_full_union_and_balanced_batches():
    plan = build_candidate_plan("C", head=HEAD_MANIFEST, task=TASK_MANIFEST)
    assert plan.train_count == 1600
    assert plan.val_count == 400
    assert plan.domain_counts == {"head": 800, "task": 800}
    assert all(batch.head_count == batch.task_count for batch in plan.batches)
    assert plan.device == "cuda" and not plan.allow_cpu_fallback

def test_b_and_c_use_the_same_two_domain_checkpoint_score():
    for candidate in (build_candidate_plan("B", head=HEAD_MANIFEST, task=TASK_MANIFEST),
                      build_candidate_plan("C", head=HEAD_MANIFEST, task=TASK_MANIFEST)):
        assert candidate.checkpoint_score == "0.5*head_val_mask_map50_95+0.5*task_val_mask_map50_95"
        assert candidate.validation_domains == ("head", "task")
```

- [ ] **Step 2: Run RED.**

```zsh
expect_head_red 'mixed_candidate|two_domain_checkpoint_score|checkpoint_score' \
  src/so101_demo_py/test/test_yolo_training.py \
  src/so101_demo_py/test/test_yolo_training_container.py -q || exit 1
```

- [ ] **Step 3: Implement exact candidate plans.**

`train_yolo_seg --candidate B` trains only on head train, but receives both head val and task val. `--candidate C` trains on the full head/task union and writes a deterministic balanced sampling manifest. For both, checkpoint score is exactly `0.5 * head_val_mask_mAP50_95 + 0.5 * task_val_mask_mAP50_95`; non-finite/missing cells invalidate the epoch, and an exact score tie selects the earlier epoch. Both inherit A, share optimizer/augmentation/imgsz/batch/seed/max-epoch/early-stop settings, set `YOLO_OFFLINE=true`, require a CUDA device, and atomically write weight/config/dataset/runtime digests after a successful child exit. Existing output roots remain an error.

- [ ] **Step 4: Run GREEN and commit the reproducible training entry.**

```zsh
head_test src/so101_demo_py/test/test_yolo_training.py \
  src/so101_demo_py/test/test_yolo_training_container.py -q || exit 1
git add src/so101_demo_py/config/perception/head_search_yolo_training.yaml \
  src/so101_demo_py/src/act/head_search_training.py \
  src/so101_demo_py/src/adapters/perception/yolo_training.py \
  src/so101_demo_py/src/cli/train_yolo_seg.py \
  src/so101_demo_py/test/test_yolo_training.py \
  src/so101_demo_py/test/test_yolo_training_container.py
git diff --cached --check
git commit -m "feat: prepare head search YOLO candidates"
```

The installed one-epoch B/C smokes run at Task 11 after the package is rebuilt. They must actually enter Ultralytics, consume both validation domains, detect CUDA and exit 0. A CLI/config-only success is insufficient.

### Task 4: Implement the two benchmark gates and A/B/C verdict

**Files:**

- Create: `src/so101_demo_py/src/perception_benchmark/head_search_models.py`
- Create: `src/so101_demo_py/src/cli/evaluate_head_search_yolo_candidates.py`
- Create: `src/so101_demo_py/benchmark_test/test_head_search_model_evaluation.py`
- Modify: `src/so101_demo_py/src/perception_benchmark/reporting.py`
- Modify: `src/so101_demo_py/src/perception_benchmark/calibration.py`
- Modify: `src/so101_demo_py/src/cli/perception_benchmark.py`
- Modify: `src/so101_demo_py/setup.py`

**Interfaces:** Consumes A/B/C `CandidateIdentity`, frozen head/task test manifests and held-out detector/tracker episodes. Produces `model-comparison.json` and `model-selection-verdict.json` with scene-level paired bootstrap.

- [ ] **Step 1: Add RED tests for statistical unit, sealing, and C preference.**

```python
def test_bootstrap_resamples_scene_groups_not_frames():
    result = paired_scene_bootstrap(FRAMES_FROM_TWO_SCENES, repetitions=10_000, seed=17)
    assert result.independent_unit == "scene_group_id"
    assert result.unit_count == 2

def test_all_equivalent_candidates_prefer_retained_mixed_model():
    assert choose_candidate(A_EQUIVALENT, B_EQUIVALENT, C_EQUIVALENT_RETAINED).candidate_id == "C"
```

- [ ] **Step 2: Run RED, then implement.**

```zsh
expect_head_red 'bootstrap_resamples|equivalent_candidates_prefer' \
  src/so101_demo_py/benchmark_test/test_head_search_model_evaluation.py -q || exit 1
```

Freeze each candidate's weight, domain-specific confidence/area/aspect, tracker IoU, postprocess and runtime before test access. Static image metrics and held-out detector/tracker episode metrics remain separate. Require 10,000 paired scene bootstrap repetitions, AP/F1/recall margin 0.01, bbox-center p95 margin 2 px, zero `no_cup` false candidates, C task retention margin 0.01, and the latency budget from the spec. Do not compute controller-dependent wrong-lock/reacquisition metrics here.

- [ ] **Step 3: Build a fresh Task 4 package boundary, run the explicit implementation gate, and commit.**

```zsh
TASK4_GATE="$HEAD_EVIDENCE/head-benchmark-code-gate-$(date -u +%Y%m%dT%H%M%SZ)"
test ! -e "$TASK4_GATE" || exit 1
mkdir "$TASK4_GATE" || exit 1
source /opt/ros/jazzy/setup.zsh
set -o pipefail
new_head_scratch || exit 1
run_logged "$TASK4_GATE/build.console.log" /usr/bin/time -p \
  "$HEAD_PYTHON" "$HEAD_COLCON" --log-base "$TASK4_GATE/build-log" build \
  --build-base "$TASK4_GATE/build" \
  --install-base "$TASK4_GATE/install" \
  --packages-up-to so101_demo_py --symlink-install --executor sequential \
  --cmake-args -DPython3_EXECUTABLE="$HEAD_PYTHON" || exit 1
test -f "$TASK4_GATE/install/setup.zsh" || exit 1
source "$TASK4_GATE/install/setup.zsh"
new_head_scratch || exit 1
run_logged "$TASK4_GATE/test.console.log" /usr/bin/time -p \
  "$HEAD_PYTHON" "$HEAD_COLCON" --log-base "$TASK4_GATE/test-log" test \
  --build-base "$TASK4_GATE/build" \
  --install-base "$TASK4_GATE/install" \
  --packages-select so101_demo_py --return-code-on-test-failure --executor sequential \
  --pytest-args benchmark_test || exit 1
head_colcon test-result --test-result-base "$TASK4_GATE/build" --verbose \
  >"$TASK4_GATE/test-result.txt" || exit 1
git add src/so101_demo_py/src/perception_benchmark/head_search_models.py \
  src/so101_demo_py/src/cli/evaluate_head_search_yolo_candidates.py \
  src/so101_demo_py/benchmark_test/test_head_search_model_evaluation.py \
  src/so101_demo_py/src/perception_benchmark/reporting.py \
  src/so101_demo_py/src/perception_benchmark/calibration.py \
  src/so101_demo_py/src/cli/perception_benchmark.py src/so101_demo_py/setup.py
git diff --cached --check
git commit -m "feat: compare frozen head search YOLO candidates"
```

Record the actual pytest argv to prove `benchmark_test` ran; ordinary `src/so101_demo_py/test/` collection does not substitute for this gate.

### Task 5: Replace positive-circle search with bounded domain coverage

**Files:**

- Create: `src/so101_demo_py/src/act/head_search_domain.py`
- Create: `src/so101_demo_py/src/cli/head_search_smoke.py`
- Create: `src/so101_demo_py/test/test_act_head_search_domain.py`
- Modify: `src/so101_demo_py/src/act/search.py`
- Modify: `src/so101_demo_py/src/act/head_search_binding.py`
- Modify: `src/so101_demo_py/src/adapters/act/task8_calibration_search_binding.py`
- Modify: `src/so101_demo_py/test/test_act_search.py`
- Modify: `src/so101_demo_py/test/test_act_task8_search_binding.py`
- Modify: `src/so101_demo_py/test/test_act_head_search_binding.py`
- Modify: `src/so101_demo_py/setup.py`

**Interfaces:** Consumes camera FOV, anchor, `required_search_domain_rad`, `lock_valid_neck_rad`, step and independent `sweep_checker`. Produces `SearchStopPlan` and exact statuses `TARGET_LOCKED`, `TARGET_NOT_FOUND`, or `TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL`.

- [ ] **Step 1: Reproduce the current overflow as RED.**

```python
def test_default_anchor_never_commands_past_safe_upper_bound():
    plan = bounded_search_stops(
        anchor_rad=0.1,
        required_domain_rad=(-2.5, 2.5),
        safe_interval_rad=(-2 * math.pi + 1e-5, 2 * math.pi - 1e-5),
        horizontal_fov_rad=1.0,
        coarse_step_rad=0.5,
    )
    assert max(plan.targets_rad) <= 2 * math.pi - 1e-5
    assert plan.coverage_complete
```

- [ ] **Step 2: Run RED.**

```zsh
expect_head_red 'never_commands_past_safe|coverage_complete|bounded_search_stops' \
  src/so101_demo_py/test/test_act_head_search_domain.py \
  src/so101_demo_py/test/test_act_search.py \
  src/so101_demo_py/test/test_act_task8_search_binding.py -q || exit 1
```

- [ ] **Step 3: Implement deterministic bounded stops.**

```python
def bounded_search_stops(*, anchor_rad: float,
                         required_domain_rad: tuple[float, float],
                         safe_interval_rad: tuple[float, float],
                         horizontal_fov_rad: float,
                         coarse_step_rad: float) -> SearchStopPlan:
    """Visit the nearer coverage endpoint first, reverse once, and prove FOV union coverage."""
```

Every target and swept segment must pass the existing calibration binding and independent sweep checker. Stable FOV intervals, not accumulated angle, establish coverage. If the safe interval cannot cover the required domain, reject before motion. A no-cup result is `TARGET_NOT_FOUND` only after complete coverage; reaching a bound first is `TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL` and fails qualification.

- [ ] **Step 4: Run GREEN and commit the bounded-search entry.**

```zsh
head_test src/so101_demo_py/test/test_act_head_search_domain.py \
  src/so101_demo_py/test/test_act_search.py \
  src/so101_demo_py/test/test_act_task8_search_binding.py \
  src/so101_demo_py/test/test_act_head_search_binding.py -q || exit 1
git add src/so101_demo_py/src/act/head_search_domain.py \
  src/so101_demo_py/src/act/search.py \
  src/so101_demo_py/src/cli/head_search_smoke.py \
  src/so101_demo_py/src/act/head_search_binding.py \
  src/so101_demo_py/src/adapters/act/task8_calibration_search_binding.py \
  src/so101_demo_py/test/test_act_head_search_domain.py \
  src/so101_demo_py/test/test_act_search.py \
  src/so101_demo_py/test/test_act_task8_search_binding.py \
  src/so101_demo_py/test/test_act_head_search_binding.py src/so101_demo_py/setup.py
git diff --cached --check
git commit -m "fix: bound head search to the calibrated domain"
```

Task 11 runs the installed smoke after Task 7's restricted admission exists. The smoke must start the real MuJoCo/controller composition, exit 0, show complete coverage and never command outside the safe interval. This task registers `so101_head_search_smoke = so101_demo.cli.head_search_smoke:main`; the entry calls the production composition and does not carry a fixture-only backend.

### Task 6: Implement the 17-parameter calibration library

**Files:**

- Create: `src/so101_demo_py/src/act/head_search_calibration.py`
- Create: `src/so101_demo_py/config/act/head-search-calibration-contract-v1.json`
- Create: `src/so101_demo_py/config/act/head-search-calibration-contract-schema.json`
- Create: `src/so101_demo_py/config/act/head-search-scenario-partitions-v1.json`
- Create: `src/so101_demo_py/test/test_act_head_search_calibration.py`
- Modify: `src/so101_demo_py/config/act/task8-calibration-measurement-contract-v2.json`

**Interfaces:** Consumes raw geometry, CameraInfo, frozen candidate operating point, calibration episodes, timing/stop records and exact source/config identities. Produces `HeadSearchCalibrationBundle` containing all 17 values and controlled dependencies.

- [ ] **Step 1: Write RED tests for all fields and hard bounds.**

```python
EXPECTED = {
    "horizontal_fov_rad", "lock_valid_neck_rad", "coarse_step_rad",
    "search_timeout_s", "min_confidence", "tracking_iou",
    "min_bbox_aspect", "min_area_px2", "center_deadband_px",
    "vertical_bounds_px", "max_fine_corrections", "max_fine_total_rad",
    "max_age_s", "max_skew_s", "submit_lead_s",
    "stop_velocity_rad_s", "stop_latency_s",
}

def test_bundle_has_exactly_seventeen_measured_values():
    bundle = calibrate_head_search(FIXTURE_INPUTS)
    assert set(bundle.measurements) == EXPECTED
    assert bundle.measurements["max_age_s"].value <= 0.15
    assert bundle.measurements["max_skew_s"].value <= 0.05
```

- [ ] **Step 2: Run RED.**

```zsh
expect_head_red 'exactly_seventeen|EXPECTED|max_age_s|max_skew_s' \
  src/so101_demo_py/test/test_act_head_search_calibration.py -q || exit 1
```

- [ ] **Step 3: Implement pure calibration functions.**

Each result stores `value`, `unit`, formula ID, ordered input SHA256 list, observed distribution, margin, production owner and consumer field. Reject an uncovered required domain, nonzero val false candidates, missing two-cup detections, tracker identity switches, non-finite samples, stale frames, time regression, unsafe fine motion or any hard-bound violation. The four perception values must exactly equal the selected candidate identity; this library verifies but does not retune them after test.

`head-search-scenario-partitions-v1.json` is the single tracked source of seed partitions. It contains exact, disjoint `calibration`, `held_out_evaluation`, and 40-item `qualification` arrays; every qualification item carries one of the ten approved condition classes and one of `default`, `left`, or `forward`. Its schema rejects a repeated seed or scene group across any partition.

- [ ] **Step 4: Run GREEN and commit.**

```zsh
head_test src/so101_demo_py/test/test_act_head_search_calibration.py \
  src/so101_demo_py/test/test_act_calibration.py -q || exit 1
git add src/so101_demo_py/src/act/head_search_calibration.py \
  src/so101_demo_py/config/act/head-search-calibration-contract-v1.json \
  src/so101_demo_py/config/act/head-search-calibration-contract-schema.json \
  src/so101_demo_py/config/act/head-search-scenario-partitions-v1.json \
  src/so101_demo_py/config/act/task8-calibration-measurement-contract-v2.json \
  src/so101_demo_py/test/test_act_head_search_calibration.py
git diff --cached --check
git commit -m "feat: calibrate head search parameters"
```

### Task 7: Build the no-resume formal CLI and head-only qualification bridge

**Files:**

- Create: `src/so101_demo_py/src/act/head_search_qualification.py`
- Create: `src/so101_demo_py/src/cli/head_search_calibration.py`
- Create: `src/so101_demo_py/test/test_act_head_search_qualification.py`
- Create: `src/so101_demo_py/test/test_head_search_calibration_cli.py`
- Modify: `src/so101_demo_py/src/act/head_search_binding.py`
- Modify: `src/so101_demo_py/src/act/task8_calibration_admission.py`
- Modify: `src/so101_demo_py/src/adapters/act/task8_calibration_search_binding.py`
- Modify: `src/so101_demo_py/setup.py`

**Interfaces:** Produces `so101_head_search_calibration run`, `verify-promoted-config`, `qualify`, and `serve-teleop`. `run` emits the calibration bundle. `qualify` consumes a complete real-runtime evidence set and only then emits closed `head-search-qualification.json` and `head-search-qualified-report.json` with `HEAD_SEARCH_QUALIFIED`. `serve-teleop` is a blocking process owner used only after qualification: it starts one fresh production stack from the frozen runtime and head-only report, publishes a readiness receipt, and performs owned teardown on signal. It is not a resume path and is not one of the three qualification `FULL_RESTART` gates.

- [ ] **Step 1: Write RED tests for no-resume and Task 8 isolation.**

```python
def test_cli_has_no_resume_or_stage_continuation(parser):
    with pytest.raises(SystemExit):
        parser.parse_args(["run", "--resume", "old-run"])

def test_head_only_report_does_not_grant_task8_ready(tmp_path):
    report = qualify_head_search(QUALIFIED_INPUTS, tmp_path)
    assert report["status"] == "HEAD_SEARCH_QUALIFIED"
    with pytest.raises(ValueError, match="TASK8"):
        require_gate(report, "task8_live")

def test_serve_teleop_requires_closed_head_only_report(tmp_path):
    with pytest.raises(ValueError, match="HEAD_SEARCH_QUALIFIED_REQUIRED"):
        serve_teleop(unqualified_report(), tmp_path / "fresh-run")

def test_serve_teleop_owns_teardown_and_cannot_resume(tmp_path):
    receipt = serve_then_signal(qualified_report(), tmp_path / "fresh-run")
    assert receipt["controller_stopped"] is True
    assert receipt["graph_clear"] is True
    with pytest.raises(ValueError, match="RUN_ROOT_ALREADY_EXISTS"):
        serve_teleop(qualified_report(), tmp_path / "fresh-run")
```

- [ ] **Step 2: Run RED.**

```zsh
expect_head_red 'no_resume|head_only_report|TASK8' \
  src/so101_demo_py/test/test_act_head_search_qualification.py \
  src/so101_demo_py/test/test_head_search_calibration_cli.py \
  src/so101_demo_py/test/test_act_task8_calibration_admission.py -q || exit 1
```

- [ ] **Step 3: Implement the runner and closed bridge.**

`run` accepts only a new, nonexistent run root. It writes `RUNNING` once, executes the fixed phase list, then atomically writes `SUCCEEDED` or `FAILED`; a pre-existing root is always refused. A single issuer creates operation-bound head-only admission for exactly `GEOMETRY_SMOKE`, `CALIBRATION_RUN`, `QUALIFICATION_RUN`, or `TELEOP_ACCEPTANCE`. The first three bind generation, production camera, safe interval, independent sweep checker, one stack and one detector; `TELEOP_ACCEPTANCE` additionally requires the already closed `HEAD_SEARCH_QUALIFIED` report and may expose only the Teleop Head Camera consumer. Release, recorder, retreat, pick and Task 8 readiness remain refused in every mode. `run` and the initial `qualify` construction both consume this restricted admission. Task 5's smoke can run only after this issuer exists and only with `GEOMETRY_SMOKE`. `verify-promoted-config` requires the exact user-approved bundle SHA256, writes an immutable `approval-receipt.json`, and compares all values and identities byte-for-byte. `qualify` uses the same restricted owner to run one production smoke, 40 serial scenes, and one independent `FULL_RESTART` per anchor; it has no resume path and publishes nothing qualified until every required evidence digest passes. `serve-teleop` accepts a new nonexistent run root plus the exact qualification report, promoted config and approval receipt, owns one process group, writes a readiness receipt only after graph/detector/CUDA/identity probes pass, blocks until SIGINT/SIGTERM, then records controller stop, graph clear and teardown status. The final aggregator reuses `_MEASURED`, `_CAMERA_MEASURED`, `validate_head_search_shape()` and sample digest checks. `validate_head_search_binding()` accepts the strict head-only report for later Head Search consumers but `task8_live`, release, retreat and dynamic pick continue to reject it.

- [ ] **Step 4: Run GREEN and commit the formal CLI.**

```zsh
head_test src/so101_demo_py/test/test_act_head_search_qualification.py \
  src/so101_demo_py/test/test_head_search_calibration_cli.py \
  src/so101_demo_py/test/test_act_task8_calibration_admission.py \
  src/so101_demo_py/test/test_act_head_search_binding.py -q || exit 1
git add src/so101_demo_py/src/act/head_search_qualification.py \
  src/so101_demo_py/src/cli/head_search_calibration.py \
  src/so101_demo_py/src/act/head_search_binding.py \
  src/so101_demo_py/src/act/task8_calibration_admission.py \
  src/so101_demo_py/src/adapters/act/task8_calibration_search_binding.py \
  src/so101_demo_py/test/test_act_head_search_qualification.py \
  src/so101_demo_py/test/test_head_search_calibration_cli.py src/so101_demo_py/setup.py
git diff --cached --check
git commit -m "feat: add formal head search calibration entry"
```

### Task 8: Wire the selected bundle into production startup

**Files:**

- Create: `src/so101_demo_py/config/mujoco/act/head_search_v2.json`
- Modify: `src/so101_demo_py/src/act/head_search_binding.py`
- Modify: `src/so101_demo_py/src/runtime/launch_composition.py`
- Modify: `src/so101_demo_py/src/cli/act_stack_ready.py`
- Modify: `src/so101_demo_py/test/test_act_head_search_binding.py`
- Modify: `src/so101_demo_py/test/test_act_stack_ready.py`
- Modify: `src/so101_demo_py/test/test_launch_composition.py`

**Interfaces:** Consumes either an operation-bound head-only context (`GEOMETRY_SMOKE`, `CALIBRATION_RUN`, `QUALIFICATION_RUN`, or `TELEOP_ACCEPTANCE`) or an approved `HEAD_SEARCH_QUALIFIED` report plus promoted config. `TELEOP_ACCEPTANCE` additionally requires that exact closed report and grants only the Teleop Head Camera consumer. Produces one immutable `HeadSearchBinding` used by the only detector/controller instance. Restricted contexts never grant Task 8, release, recorder, retreat or pick authority.

- [ ] **Step 1: Add RED tests for exact readback and fail-closed drift.**

```python
def test_startup_rejects_one_field_of_bundle_drift():
    config = promoted_config(min_confidence=0.52)
    report = qualified_report(min_confidence=0.51)
    with pytest.raises(ValueError, match="HEAD_SEARCH_SAMPLE_MISMATCH"):
        validate_head_search_binding(config, report)
```

- [ ] **Step 2: Run RED, implement, and run GREEN.**

```zsh
expect_head_red 'bundle_drift|HEAD_SEARCH_SAMPLE_MISMATCH' \
  src/so101_demo_py/test/test_act_head_search_binding.py \
  src/so101_demo_py/test/test_act_stack_ready.py \
  src/so101_demo_py/test/test_launch_composition.py -q || exit 1
```

Startup verifies regular no-follow weight file, weight SHA, candidate identity, camera, tracker, all 17 values, controlled dependencies, CUDA device and `allow_cpu_fallback=false` before ROS/model construction. The effective-config readback lists every consumed value and consumer; any unused value rejects startup.

- [ ] **Step 3: Run the same tests GREEN, then commit.**

```zsh
head_test src/so101_demo_py/test/test_act_head_search_binding.py \
  src/so101_demo_py/test/test_act_stack_ready.py \
  src/so101_demo_py/test/test_launch_composition.py -q || exit 1
git add src/so101_demo_py/config/mujoco/act/head_search_v2.json \
  src/so101_demo_py/src/act/head_search_binding.py \
  src/so101_demo_py/src/runtime/launch_composition.py \
  src/so101_demo_py/src/cli/act_stack_ready.py \
  src/so101_demo_py/test/test_act_head_search_binding.py \
  src/so101_demo_py/test/test_act_stack_ready.py \
  src/so101_demo_py/test/test_launch_composition.py
git diff --cached --check
git commit -m "feat: bind qualified head search at startup"
```

### Task 9: Add the Teleop head-camera backend without a second detector

**Files:**

- Create: `src/so101_teleop/so101_teleop/head_camera.py`
- Create: `src/so101_teleop/test/teleop/test_head_camera_api.py`
- Modify: `src/so101_teleop/so101_teleop/unified/ports.py`
- Modify: `src/so101_teleop/so101_teleop/unified/compose.py`
- Modify: `src/so101_teleop/so101_teleop/unified/app.py`
- Modify: `src/so101_teleop/so101_teleop/unified/arbiter.py`
- Modify: `src/so101_teleop/so101_teleop/openapi_export.py`
- Modify: `src/so101_teleop/CMakeLists.txt`

**Interfaces:** Produces `GET /teleop/head-camera/status`, `WS /teleop/head-camera/stream`, `POST /teleop/head-camera/target`, `POST /teleop/head-camera/stop`, and `POST /teleop/head-camera/capture`. Consumes the existing detector stream and controller ownership; it does not instantiate either.

- [ ] **Step 1: Add RED API/ownership tests.**

```python
def test_head_camera_stream_uses_composed_detector_identity(client, services):
    envelope = services.head_camera.publish_once()
    assert envelope.model_id == services.head_search.model_id
    assert services.detector_factory_calls == 1

def test_out_of_range_target_is_refused_before_submit(client):
    response = client.post("/teleop/head-camera/target", json={"target_rad": 99.0}, headers=AUTH)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "HEAD_TARGET_OUT_OF_RANGE"
```

- [ ] **Step 2: Run RED.**

```zsh
expect_head_red 'composed_detector_identity|HEAD_TARGET_OUT_OF_RANGE|head_camera' \
  src/so101_teleop/test/teleop/test_head_camera_api.py \
  src/so101_teleop/test/teleop/test_unified_arbiter.py -q || exit 1
```

- [ ] **Step 3: Implement typed status/frame/control/capture contracts.**

The WebSocket envelope binds JPEG and detections to one `frame_sequence`, image SHA, camera stamp/frame, CameraInfo, model/bundle SHA, inference latency and search projection. Latest-frame display dropping never backpressures the production stream. Target commands are bounded absolute positions with instance authority, lease, global mutation reservation, safe interval and sweep checks. Stop remains `STOPPING` until three consecutive raw velocity samples meet the calibrated threshold. Capture atomically writes raw image, overlay inputs, detections, runtime state and manifest for the exact requested frame; stale or mismatched frames are refused.

- [ ] **Step 4: Run GREEN, export the exact OpenAPI files, and commit.**

```zsh
head_test src/so101_teleop/test/teleop/test_head_camera_api.py \
  src/so101_teleop/test/teleop/test_unified_arbiter.py \
  src/so101_teleop/test/teleop/test_unified_api.py -q || exit 1
PYTHONPATH="$PWD/src/so101_teleop${PYTHONPATH:+:$PYTHONPATH}" \
  "$HEAD_PYTHON" -m so101_teleop.openapi_export \
  src/so101_teleop/so101_teleop/openapi.json || exit 1
PYTHONPATH="$PWD/src/so101_teleop${PYTHONPATH:+:$PYTHONPATH}" \
  "$HEAD_PYTHON" -m so101_teleop.openapi_export --unified \
  src/so101_teleop/so101_teleop/unified_openapi.json || exit 1
git add src/so101_teleop/so101_teleop/head_camera.py \
  src/so101_teleop/so101_teleop/unified/ports.py \
  src/so101_teleop/so101_teleop/unified/compose.py \
  src/so101_teleop/so101_teleop/unified/app.py \
  src/so101_teleop/so101_teleop/unified/arbiter.py \
  src/so101_teleop/so101_teleop/openapi_export.py \
  src/so101_teleop/so101_teleop/openapi.json \
  src/so101_teleop/so101_teleop/unified_openapi.json \
  src/so101_teleop/test/teleop/test_head_camera_api.py src/so101_teleop/CMakeLists.txt
git diff --cached --check
git commit -m "feat: expose qualified head camera controls"
```

Task 11 runs the installed `/teleop/head-camera/status` composed-service smoke after the backend is rebuilt; Task 14 runs the real production-stack API/control/capture acceptance.

### Task 10: Add the Teleop Head Camera page and visual evidence

**Files:**

- Create: `src/so101_teleop/web/src/api/head-camera-client.ts`
- Create: `src/so101_teleop/web/src/api/head-camera-client.test.ts`
- Create: `src/so101_teleop/web/src/components/teleop/head-camera-panel.tsx`
- Create: `src/so101_teleop/web/src/components/teleop/head-camera-panel.test.tsx`
- Create: `src/so101_teleop/web/e2e/head-camera.spec.ts`
- Modify: `src/so101_teleop/web/src/app.tsx`
- Modify: `src/so101_teleop/web/src/styles/unified-layout.css`
- Modify: `src/so101_teleop/web/src/api/schema.d.ts`

**Interfaces:** Consumes Task 9's APIs. Produces a `Head Camera` tab with Raw/YOLO overlay, bounded absolute/step controls, stop, capture and runtime identities.

- [ ] **Step 1: Add RED component tests.**

```tsx
it("keeps control disabled until authority and qualification are present", () => {
  render(<HeadCameraPanel status={unqualifiedStatus} />)
  expect(screen.getByRole("button", { name: "Execute" })).toBeDisabled()
  expect(screen.getByText("View only")).toBeVisible()
})
```

- [ ] **Step 2: Run RED.**

```zsh
TASK10_RED="$HEAD_EVIDENCE/head-teleop-web-red-$(date -u +%Y%m%dT%H%M%SZ)"
test ! -e "$TASK10_RED" || exit 1
mkdir -p "$TASK10_RED" || exit 1
(
  cd "$PWD/src/so101_teleop/web" || exit 1
  set -o pipefail
  bun run test -- src/api/head-camera-client.test.ts \
    src/components/teleop/head-camera-panel.test.tsx \
    2>&1 | tee "$TASK10_RED/vitest-red.log"
  web_red_rc=$pipestatus[1]
  print -r -- "$web_red_rc" >"$TASK10_RED/vitest-red.rc"
  test "$web_red_rc" -ne 0 || exit 1
  rg -n 'head-camera-client|head-camera-panel|keeps control disabled until authority and qualification are present' \
    "$TASK10_RED/vitest-red.log" >/dev/null || exit 1
) || exit 1
```

Read back the nonzero exit code and the named failing test from the retained log. A missing `bun`, collection error, wrong working directory or unrelated failure is not RED.

- [ ] **Step 3: Implement the page.**

Render the fixed 4:3 frame, mask, bbox, class, confidence, track ID, optical axis, horizontal deadband, vertical bounds, candidate center and three-frame lock progress. Show angle, velocity, target, interval, owner, lease, operation, model/weight/bundle SHA, CUDA, FPS, latency, frame age, skew and display drops. Expose absolute angle plus `-5°`, `-1°`, `+1°`, `+5°`, Execute and Stop; do not expose threshold editing or model hot switching.

- [ ] **Step 4: Run GREEN and build the web bundle.**

```zsh
(cd "$PWD/src/so101_teleop/web" && \
  bun run test -- src/api/head-camera-client.test.ts \
    src/components/teleop/head-camera-panel.test.tsx && \
  bun run build) || exit 1
```

Do not claim installed-app or visual acceptance here. Task 14 sets `SO101_TELEOP_BASE_URL` to the installed unified service, runs Playwright without Vite's development server, and captures the fresh runtime screenshots.

- [ ] **Step 5: Commit.**

```zsh
git add src/so101_teleop/web/src/api/head-camera-client.ts \
  src/so101_teleop/web/src/api/head-camera-client.test.ts \
  src/so101_teleop/web/src/components/teleop/head-camera-panel.tsx \
  src/so101_teleop/web/src/components/teleop/head-camera-panel.test.tsx \
  src/so101_teleop/web/e2e/head-camera.spec.ts \
  src/so101_teleop/web/src/app.tsx \
  src/so101_teleop/web/src/styles/unified-layout.css \
  src/so101_teleop/web/src/api/schema.d.ts
git diff --cached --check
git commit -m "feat: visualize head search in Teleop"
```

## Phase B — Generate data, train, and select the model

### Task 11: Complete source gates and freeze the data/model toolchain

**Files:**

- Modify: `src/so101_demo_py/README.md`
- Modify: `docs/experiments/so101-act-data-experiment-ledger.md`

**Interfaces:** Consumes all Task 1–10 commits. Produces an installed, test-green code identity and documents the Hugging Face A-model source plus the head-search exclusion of Grounded-SAM.

- [ ] **Step 1: Update persistent documentation before runtime freeze.**

Keep the README in English. Preserve the existing pinned repositories and hashes:

```text
zjumty/so101-yolo11n-seg-plastic-cup
revision b55430fb75c0207b35bd20f4e328e042bff06f3f
best.pt SHA256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781

zjumty/so101-grounded-sam-cup-pickplace
revision 52b8334358e5ff11f94f10f7c14b1697ef44d964
```

State explicitly that Head Search uses YOLO11n-Seg only and does not load Grounded-SAM. Add the formal head calibration commands, no-resume behavior and evidence layout. Run the project `$humanizer` skill on README prose without changing commands, paths, identifiers, hashes or links.

- [ ] **Step 2: Build a fresh dependency-closed installed toolchain and prove entry-point provenance.**

```zsh
TOOLCHAIN_RUN="$HEAD_EVIDENCE/head-toolchain-$(date -u +%Y%m%dT%H%M%SZ)"
test ! -e "$TOOLCHAIN_RUN" || exit 1
mkdir "$TOOLCHAIN_RUN" || exit 1
git rev-parse HEAD >"$TOOLCHAIN_RUN/source-commit.txt" || exit 1
source /opt/ros/jazzy/setup.zsh
set -o pipefail
new_head_scratch || exit 1
run_logged "$TOOLCHAIN_RUN/build.console.log" /usr/bin/time -p \
  "$HEAD_PYTHON" "$HEAD_COLCON" --log-base "$TOOLCHAIN_RUN/build-log" build \
  --build-base "$TOOLCHAIN_RUN/build" \
  --install-base "$TOOLCHAIN_RUN/install" \
  --packages-up-to so101_demo_py so101_teleop --symlink-install --executor sequential \
  --cmake-args -DPython3_EXECUTABLE="$HEAD_PYTHON" || exit 1
test -f "$TOOLCHAIN_RUN/install/setup.zsh" || exit 1
source "$TOOLCHAIN_RUN/install/setup.zsh"
test "$(ros2 pkg prefix so101_demo_py)" = "$TOOLCHAIN_RUN/install/so101_demo_py" || exit 1
test "$(ros2 pkg prefix so101_teleop)" = "$TOOLCHAIN_RUN/install/so101_teleop" || exit 1
ros2 pkg executables so101_demo_py >"$TOOLCHAIN_RUN/so101_demo_py.executables" || exit 1
for executable in validate_head_camera_geometry generate_yolo_seg_dataset train_yolo_seg \
  verify_head_search_dataset evaluate_head_search_yolo_candidates \
  so101_head_search_smoke so101_head_search_calibration; do
  rg -n "so101_demo_py[[:space:]]+$executable$" "$TOOLCHAIN_RUN/so101_demo_py.executables" \
    >/dev/null || exit 1
done
test -x "$TOOLCHAIN_RUN/install/so101_teleop/lib/so101_teleop/so101_unified_web_server.py" || exit 1
test -f "$TOOLCHAIN_RUN/install/so101_teleop/share/so101_teleop/web/index.html" || exit 1
```

If dependency closure, underlay setup, package selection, or override validation fails before compilation, classify it as an environment failure and do not count it as a source RED.

- [ ] **Step 3: Run source and installed ordinary package gates with explicit CPU/worker evidence.**

```zsh
nproc >"$TOOLCHAIN_RUN/nproc.txt" || exit 1
lscpu >"$TOOLCHAIN_RUN/lscpu.txt" || exit 1
head_test -n 8 src/so101_demo_py/test -q || exit 1
head_test -n 8 src/so101_teleop/test -q || exit 1

new_head_scratch || exit 1
run_logged "$TOOLCHAIN_RUN/test-demo-ordinary.console.log" /usr/bin/time -p \
  "$HEAD_PYTHON" "$HEAD_COLCON" \
  --log-base "$TOOLCHAIN_RUN/test-log-demo-ordinary" test \
  --build-base "$TOOLCHAIN_RUN/build" --install-base "$TOOLCHAIN_RUN/install" \
  --packages-select so101_demo_py --return-code-on-test-failure --executor sequential \
  --pytest-args test || exit 1

new_head_scratch || exit 1
run_logged "$TOOLCHAIN_RUN/test-teleop.console.log" /usr/bin/time -p \
  "$HEAD_PYTHON" "$HEAD_COLCON" \
  --log-base "$TOOLCHAIN_RUN/test-log-teleop" test \
  --build-base "$TOOLCHAIN_RUN/build" --install-base "$TOOLCHAIN_RUN/install" \
  --packages-select so101_teleop --return-code-on-test-failure --executor sequential || exit 1
head_colcon test-result --test-result-base "$TOOLCHAIN_RUN/build" --verbose \
  >"$TOOLCHAIN_RUN/test-result-ordinary.txt" || exit 1
```

Confirm neither ordinary command collected `src/so101_demo_py/benchmark_test/`. Retain pytest JUnit XML, colcon xUnit files, both `interpreter-and-cpu.json` files, `nproc.txt`, `lscpu.txt`, exact `-n 8` argv and elapsed times.

- [ ] **Step 4: Run every installed formal-entry smoke serially.**

```zsh
GEOMETRY_RUN="$HEAD_EVIDENCE/head-camera-geometry-$(date -u +%Y%m%dT%H%M%SZ)"
DATASET_SMOKE_ROOT="$HEAD_EVIDENCE/head-dataset-smoke-$(date -u +%Y%m%dT%H%M%SZ)"
TRAIN_SMOKE_CAMPAIGN="$HEAD_EVIDENCE/head-training-smokes-$(date -u +%Y%m%dT%H%M%SZ)"
SEARCH_SMOKE_ROOT="$HEAD_EVIDENCE/head-search-smoke-$(date -u +%Y%m%dT%H%M%SZ)"
BACKEND_SMOKE_ROOT="$HEAD_EVIDENCE/teleop-head-backend-smoke-$(date -u +%Y%m%dT%H%M%SZ)"
for root in "$GEOMETRY_RUN" "$DATASET_SMOKE_ROOT" "$TRAIN_SMOKE_CAMPAIGN" \
  "$SEARCH_SMOKE_ROOT" "$BACKEND_SMOKE_ROOT"; do
  test ! -e "$root" || exit 1
done
mkdir "$TRAIN_SMOKE_CAMPAIGN" "$BACKEND_SMOKE_ROOT" || exit 1

run_logged "$TOOLCHAIN_RUN/head-camera-geometry.console.log" \
  ros2 run so101_demo_py validate_head_camera_geometry \
  --scene "$PWD/src/so101_demo_py/assets/mujoco/act/so101.xml" \
  --camera-config "$PWD/src/so101_demo_py/config/mujoco/camera_views.yaml" \
  --contract "$PWD/src/so101_demo_py/config/act/head-camera-geometry-contract-v1.json" \
  --anchors default,left,forward --output-root "$GEOMETRY_RUN" || exit 1
test -f "$GEOMETRY_RUN/head-camera-geometry.json" || exit 1

run_logged "$TOOLCHAIN_RUN/head-dataset-smoke.console.log" \
  ros2 run so101_demo_py generate_yolo_seg_dataset \
  --config "$PWD/src/so101_demo_py/config/perception/head_camera_yolo_seg.yaml" \
  --geometry-seal "$GEOMETRY_RUN/head-camera-geometry.json" \
  --output-root "$DATASET_SMOKE_ROOT" --generator-commit "$(git rev-parse HEAD)" \
  --sample-limit 12 || exit 1
run_logged "$TOOLCHAIN_RUN/head-dataset-verify.console.log" \
  ros2 run so101_demo_py verify_head_search_dataset \
  --head "$DATASET_SMOKE_ROOT/dataset-manifest.json" \
  --expected-total 12 --geometry-seal "$GEOMETRY_RUN/head-camera-geometry.json" || exit 1

HF_ROOT="$HEAD_EVIDENCE/models/huggingface"
YOLO_REV=b55430fb75c0207b35bd20f4e328e042bff06f3f
A_ROOT="$HF_ROOT/so101-yolo11n-seg-plastic-cup/$YOLO_REV"
A_WEIGHTS="$A_ROOT/best.pt"
run_logged "$TOOLCHAIN_RUN/hf-download.console.log" \
  hf download zjumty/so101-yolo11n-seg-plastic-cup --revision "$YOLO_REV" \
  --include best.pt --include SHA256SUMS --include 'dataset/**' --local-dir "$A_ROOT" || exit 1
TASK_DATASET_MANIFEST="$A_ROOT/dataset/dataset-manifest.json"
test -f "$TASK_DATASET_MANIFEST" || exit 1
printf '%s  %s\n' "f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781" "$A_WEIGHTS" \
  | sha256sum --check --strict || exit 1

run_logged "$TOOLCHAIN_RUN/train-smoke-b.console.log" \
  ros2 run so101_demo_py train_yolo_seg --candidate B --epochs 1 --fraction 0.05 \
  --contract "$PWD/src/so101_demo_py/config/perception/head_search_yolo_training.yaml" \
  --head-dataset "$DATASET_SMOKE_ROOT/dataset-manifest.json" \
  --task-dataset "$TASK_DATASET_MANIFEST" --base-model "$A_WEIGHTS" \
  --output "$TRAIN_SMOKE_CAMPAIGN/candidate-b" --run-name smoke-b || exit 1
run_logged "$TOOLCHAIN_RUN/train-smoke-c.console.log" \
  ros2 run so101_demo_py train_yolo_seg --candidate C --epochs 1 --fraction 0.05 \
  --contract "$PWD/src/so101_demo_py/config/perception/head_search_yolo_training.yaml" \
  --head-dataset "$DATASET_SMOKE_ROOT/dataset-manifest.json" \
  --task-dataset "$TASK_DATASET_MANIFEST" --base-model "$A_WEIGHTS" \
  --output "$TRAIN_SMOKE_CAMPAIGN/candidate-c" --run-name smoke-c || exit 1

run_logged "$TOOLCHAIN_RUN/head-search-smoke.console.log" \
  ros2 run so101_demo_py so101_head_search_smoke --scenario no_cup --anchor default \
  --geometry-seal "$GEOMETRY_RUN/head-camera-geometry.json" \
  --evidence-root "$SEARCH_SMOKE_ROOT" || exit 1
test -f "$SEARCH_SMOKE_ROOT/coverage-proof.json" || exit 1
ros2 run so101_demo_py evaluate_head_search_yolo_candidates --help >/dev/null || exit 1
ros2 run so101_demo_py so101_head_search_calibration --help >/dev/null || exit 1
CLI_REFUSAL_ROOT="$HEAD_EVIDENCE/cli-refusal-existing-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir "$CLI_REFUSAL_ROOT" || exit 1
if run_logged "$TOOLCHAIN_RUN/cli-existing-root-refusal.console.log" \
    ros2 run so101_demo_py so101_head_search_calibration run \
    --run-root "$CLI_REFUSAL_ROOT" \
    --evidence-root "$HEAD_EVIDENCE" \
    --candidate "$TRAIN_SMOKE_CAMPAIGN/candidate-b/candidate-manifest.json" \
    --dataset "$DATASET_SMOKE_ROOT/dataset-manifest.json" \
    --geometry-seal "$GEOMETRY_RUN/head-camera-geometry.json" \
    --production-config "$PWD/src/so101_demo_py/config/mujoco/act/head_search_v2.json" \
    --camera-config "$PWD/src/so101_demo_py/config/mujoco/camera_views.yaml" \
    --episode-partitions "$PWD/src/so101_demo_py/config/act/head-search-scenario-partitions-v1.json" \
    --episode-split calibration; then
  exit 1
fi
rg -n 'RUN_ROOT_ALREADY_EXISTS|existing.*run.root' \
  "$TOOLCHAIN_RUN/cli-existing-root-refusal.console.log" >/dev/null || exit 1

SO101_UNIFIED_BACKEND=mujoco_py \
SO101_UNIFIED_INSTALL_PREFIX="$TOOLCHAIN_RUN/install" \
SO101_UNIFIED_EVIDENCE_ROOT="$BACKEND_SMOKE_ROOT" \
SO101_UNIFIED_ROS_PYTHON="$HEAD_PYTHON" \
  "$TOOLCHAIN_RUN/install/so101_teleop/lib/so101_teleop/so101_unified_web_server.py" \
  --host 127.0.0.1 --port 18081 --capture-dir "$BACKEND_SMOKE_ROOT/captures" \
  >"$BACKEND_SMOKE_ROOT/server.log" 2>&1 &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null; wait "$server_pid" 2>/dev/null' EXIT
for attempt in {1..60}; do
  curl --silent --fail http://127.0.0.1:18081/teleop/head-camera/status \
    >"$BACKEND_SMOKE_ROOT/status.json" && break
  kill -0 "$server_pid" 2>/dev/null || exit 1
  sleep 1
done
curl --fail http://127.0.0.1:18081/teleop/head-camera/status \
  >"$BACKEND_SMOKE_ROOT/status.json" || exit 1
kill "$server_pid"
set +o errexit
wait "$server_pid"
server_rc=$?
set -o errexit
case $server_rc in 0|130|143) ;; *) exit 1 ;; esac
print -r -- "$server_rc" >"$BACKEND_SMOKE_ROOT/server.rc"
trap - EXIT
```

Read back zero `in_frame` failures, all three anchors, safe-domain containment, exactly 12 smoke images, CUDA entry in both one-epoch training logs, two-domain validation scoring for B and C, bounded no-cup coverage, expected existing-root refusal, zero detector construction by the standalone Teleop backend, and the view-only `/teleop/head-camera/status` identity. The Head Search smoke separately proves exactly one production detector. Task 14 proves the installed backend consuming that detector in the final production composition. These artifacts close the runtime portions deferred by Tasks 2, 3, 5, 7 and 9 without claiming premature Teleop control acceptance.

- [ ] **Step 5: Run the explicit perception benchmark implementation gate.**

```zsh
new_head_scratch || exit 1
run_logged "$TOOLCHAIN_RUN/test-benchmark.console.log" /usr/bin/time -p \
  "$HEAD_PYTHON" "$HEAD_COLCON" --log-base "$TOOLCHAIN_RUN/test-log-benchmark" test \
  --build-base "$TOOLCHAIN_RUN/build" \
  --install-base "$TOOLCHAIN_RUN/install" \
  --packages-select so101_demo_py --return-code-on-test-failure --executor sequential \
  --pytest-args benchmark_test || exit 1
head_colcon test-result --test-result-base "$TOOLCHAIN_RUN/build" --verbose \
  >"$TOOLCHAIN_RUN/test-result-with-benchmark.txt" || exit 1
```

Read back exact console scripts, Python module paths, web bundle and OpenAPI from `$TOOLCHAIN_RUN/install`; do not accept a matching source-tree path as installed evidence.

- [ ] **Step 6: Commit documentation and ledger checkpoint.**

```zsh
git add src/so101_demo_py/README.md docs/experiments/so101-act-data-experiment-ledger.md
git diff --cached --check
git commit -m "docs: record head search model and calibration workflow"
```

The ledger checkpoint names each retained smoke, test scratch deletion candidate, installed prefix, commit, elapsed time and exit code.

### Task 12: Generate 1200 head images, train B/C, and run the real A/B/C gate

**Files:**

- Modify: `docs/experiments/so101-act-data-experiment-ledger.md`

All generated datasets, weights, reports and logs are immutable evidence artifacts under the registered root; the only repository edit is the model-decision ledger checkpoint.

**Interfaces:** Consumes Task 11's installed toolchain and pinned A weights. Produces sealed head dataset, B/C weights, three frozen candidate identities, `model-comparison.json`, and `model-selection-verdict.json`.

- [ ] **Step 1: Create a new model-campaign root and verify inputs.**

```zsh
: "${TOOLCHAIN_RUN:?set to the exact retained Task 11 toolchain root named in the ledger}"
: "${GEOMETRY_RUN:?set to the exact retained Task 11 production-camera geometry root}"
case "$TOOLCHAIN_RUN" in "$HEAD_EVIDENCE"/*) ;; *) exit 1 ;; esac
case "$GEOMETRY_RUN" in "$HEAD_EVIDENCE"/*) ;; *) exit 1 ;; esac
test -f "$TOOLCHAIN_RUN/install/setup.zsh" || exit 1
test -f "$GEOMETRY_RUN/head-camera-geometry.json" || exit 1
TOOLCHAIN_COMMIT=$(<"$TOOLCHAIN_RUN/source-commit.txt")
git cat-file -e "$TOOLCHAIN_COMMIT^{commit}" || exit 1
source "$TOOLCHAIN_RUN/install/setup.zsh"
test "$(ros2 pkg prefix so101_demo_py)" = "$TOOLCHAIN_RUN/install/so101_demo_py" || exit 1
MODEL_RUN="$HEAD_EVIDENCE/head-yolo-models-$(date -u +%Y%m%dT%H%M%SZ)"
test ! -e "$MODEL_RUN" || exit 1
mkdir "$MODEL_RUN" || exit 1
HF_ROOT="$HEAD_EVIDENCE/models/huggingface"
YOLO_REV=b55430fb75c0207b35bd20f4e328e042bff06f3f
A_ROOT="$HF_ROOT/so101-yolo11n-seg-plastic-cup/$YOLO_REV"
A_WEIGHTS="$A_ROOT/best.pt"
export no_proxy=localhost,127.0.0.1 NO_PROXY=localhost,127.0.0.1
hf auth whoami || exit 1
run_logged "$MODEL_RUN/hf-download.console.log" \
  hf download zjumty/so101-yolo11n-seg-plastic-cup --revision "$YOLO_REV" \
  --include README.md --include SHA256SUMS --include best.pt --include 'model/**' \
  --include 'dataset/**' --local-dir "$A_ROOT" || exit 1
TASK_DATASET_MANIFEST="$A_ROOT/dataset/dataset-manifest.json"
SCENARIO_PARTITIONS="$PWD/src/so101_demo_py/config/act/head-search-scenario-partitions-v1.json"
test -f "$A_WEIGHTS" || exit 1
test -f "$TASK_DATASET_MANIFEST" || exit 1
test -f "$SCENARIO_PARTITIONS" || exit 1
set -o pipefail
printf '%s  %s\n' "f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781" "$A_WEIGHTS" \
  | sha256sum --check --strict || exit 1
nvidia-smi --query-gpu=uuid,name,memory.total --format=csv,noheader \
  >"$MODEL_RUN/gpu.txt" || exit 1
```

Record `hf auth status` and the pinned repository/revision without printing credentials. Do not download `main` without `--revision`.

- [ ] **Step 2: Generate and seal the exact head dataset.**

```zsh
run_logged "$MODEL_RUN/generate-head-dataset.console.log" \
  ros2 run so101_demo_py generate_yolo_seg_dataset \
  --config "$PWD/src/so101_demo_py/config/perception/head_camera_yolo_seg.yaml" \
  --geometry-seal "$GEOMETRY_RUN/head-camera-geometry.json" \
  --output-root "$MODEL_RUN/head-dataset" --generator-commit "$TOOLCHAIN_COMMIT" || exit 1
run_logged "$MODEL_RUN/verify-head-dataset.console.log" \
  ros2 run so101_demo_py verify_head_search_dataset \
  --head "$MODEL_RUN/head-dataset/dataset-manifest.json" \
  --task "$TASK_DATASET_MANIFEST" \
  --geometry-seal "$GEOMETRY_RUN/head-camera-geometry.json" \
  --expected-train 800 --expected-val 200 --expected-test 200 || exit 1
```

Expected: exit 0, four scenarios at 200/50/50, no cross-domain split leakage, no Grounded-SAM provenance, all files and camera identities digest-clean.

- [ ] **Step 3: Train B then C, never concurrently.**

```zsh
run_logged "$MODEL_RUN/train-b.console.log" \
  ros2 run so101_demo_py train_yolo_seg --candidate B \
  --contract src/so101_demo_py/config/perception/head_search_yolo_training.yaml \
  --head-dataset "$MODEL_RUN/head-dataset/dataset-manifest.json" \
  --task-dataset "$TASK_DATASET_MANIFEST" \
  --base-model "$A_WEIGHTS" \
  --output "$MODEL_RUN/candidate-b" --run-name head-only || exit 1

run_logged "$MODEL_RUN/train-c.console.log" \
  ros2 run so101_demo_py train_yolo_seg --candidate C \
  --contract src/so101_demo_py/config/perception/head_search_yolo_training.yaml \
  --head-dataset "$MODEL_RUN/head-dataset/dataset-manifest.json" \
  --task-dataset "$TASK_DATASET_MANIFEST" --base-model "$A_WEIGHTS" \
  --output "$MODEL_RUN/candidate-c" --run-name head-task-mixed || exit 1
```

Read back the C sampling manifest: each epoch must use 800 head and 800 task images with 1:1 batches. Confirm both jobs used CUDA and the same frozen hyperparameters. Seal `best.pt`, configs, logs and candidate manifests.

- [ ] **Step 4: Calibrate and freeze each candidate operating point on val/calibration episodes.**

```zsh
run_logged "$MODEL_RUN/register-a.console.log" \
  ros2 run so101_demo_py evaluate_head_search_yolo_candidates register \
  --candidate-id A --weights "$A_WEIGHTS" \
  --head-dataset "$MODEL_RUN/head-dataset/dataset-manifest.json" \
  --task-dataset "$TASK_DATASET_MANIFEST" \
  --output "$MODEL_RUN/candidate-a" || exit 1
for candidate in A B C; do
  candidate_name=$(print -r -- "$candidate" | tr '[:upper:]' '[:lower:]')
  run_logged "$MODEL_RUN/calibrate-$candidate_name.console.log" \
    ros2 run so101_demo_py evaluate_head_search_yolo_candidates calibrate \
    --candidate "$MODEL_RUN/candidate-$candidate_name/candidate-manifest.json" \
    --head-dataset "$MODEL_RUN/head-dataset/dataset-manifest.json" --head-split val \
    --task-dataset "$TASK_DATASET_MANIFEST" --task-split val \
    --episode-partitions "$SCENARIO_PARTITIONS" --episode-split calibration \
    --output "$MODEL_RUN/frozen-$candidate_name.json" || exit 1
done
```

Expected: three frozen identities containing weight, both domain operating points, tracker, postprocess and runtime digests. Test manifests remain unopened through this step.

- [ ] **Step 5: Run the actual frozen-model evaluation gate.**

```zsh
run_logged "$MODEL_RUN/compare.console.log" \
  ros2 run so101_demo_py evaluate_head_search_yolo_candidates compare \
  --candidate "$MODEL_RUN/frozen-a.json" \
  --candidate "$MODEL_RUN/frozen-b.json" \
  --candidate "$MODEL_RUN/frozen-c.json" \
  --head-dataset "$MODEL_RUN/head-dataset/dataset-manifest.json" --head-split test \
  --task-dataset "$TASK_DATASET_MANIFEST" --task-split test \
  --episode-partitions "$SCENARIO_PARTITIONS" --episode-split held_out_evaluation \
  --bootstrap-repetitions 10000 --device cuda \
  --output "$MODEL_RUN/evaluation" || exit 1
```

Read back all six candidate/domain cells, scene-level confidence intervals, zero false candidates, latency, retention verdict and final choice. If the gate requests parameter changes after test access, invalidate the verdict and create new test/held-out seeds; do not retune against the opened test.

- [ ] **Step 6: Append and commit the model decision checkpoint.**

Record the selected A/B/C identity, why the deterministic rule chose it, all relevant SHA256 values, retained run root and any deletion candidates in the ledger. Do not alter source or production config in this task.

```zsh
git add docs/experiments/so101-act-data-experiment-ledger.md
git diff --cached --check
git commit -m "docs: record head search model decision"
```

## Phase C — Run formal calibration, promote, and qualify

### Task 13: Run the formal calibration, approve values, promote, and freeze runtime

**Files:**

- Modify: `src/so101_demo_py/config/mujoco/act/head_search_v2.json`
- Modify: `docs/experiments/so101-act-data-experiment-ledger.md`

**Interfaces:** Consumes Task 12's selected candidate. Produces an approved promoted config, exact code/config/runtime identity, and a successful `verify-promoted-config` result. It does not yet claim live qualification.

- [ ] **Step 1: Start a brand-new no-resume run.**

```zsh
CAL_RUN="$HEAD_EVIDENCE/head-calibration-$(date -u +%Y%m%dT%H%M%SZ)"
: "${MODEL_RUN:?set to the exact retained Task 12 run root named in the reviewed ledger checkpoint}"
: "${TOOLCHAIN_RUN:?set to the exact retained Task 11 toolchain root}"
: "${GEOMETRY_RUN:?set to the exact retained Task 11 production-camera geometry root}"
HEAD_CAMERA_CONFIG="$PWD/src/so101_demo_py/config/mujoco/camera_views.yaml"
SCENARIO_PARTITIONS="$PWD/src/so101_demo_py/config/act/head-search-scenario-partitions-v1.json"
test ! -e "$CAL_RUN" || exit 1
case "$MODEL_RUN" in "$HEAD_EVIDENCE"/*) ;; *) exit 1 ;; esac
case "$TOOLCHAIN_RUN" in "$HEAD_EVIDENCE"/*) ;; *) exit 1 ;; esac
case "$GEOMETRY_RUN" in "$HEAD_EVIDENCE"/*) ;; *) exit 1 ;; esac
test -f "$MODEL_RUN/evaluation/model-selection-verdict.json" || exit 1
test -f "$MODEL_RUN/head-dataset/dataset-manifest.json" || exit 1
test -f "$TOOLCHAIN_RUN/install/setup.zsh" || exit 1
test -f "$GEOMETRY_RUN/head-camera-geometry.json" || exit 1
test -f "$HEAD_CAMERA_CONFIG" || exit 1
test -f "$SCENARIO_PARTITIONS" || exit 1
source "$TOOLCHAIN_RUN/install/setup.zsh"
test "$(ros2 pkg prefix so101_demo_py)" = "$TOOLCHAIN_RUN/install/so101_demo_py" || exit 1
CAL_LAUNCH_LOG="$HEAD_EVIDENCE/head-calibration-launch-$(date -u +%Y%m%dT%H%M%SZ).log"
run_logged "$CAL_LAUNCH_LOG" \
  ros2 run so101_demo_py so101_head_search_calibration run \
  --run-root "$CAL_RUN" \
  --evidence-root "$HEAD_EVIDENCE" \
  --candidate "$MODEL_RUN/evaluation/model-selection-verdict.json" \
  --dataset "$MODEL_RUN/head-dataset/dataset-manifest.json" \
  --geometry-seal "$GEOMETRY_RUN/head-camera-geometry.json" \
  --production-config src/so101_demo_py/config/mujoco/act/head_search_v2.json \
  --camera-config "$HEAD_CAMERA_CONFIG" \
  --episode-partitions "$SCENARIO_PARTITIONS" --episode-split calibration || exit 1
```

Expected: fixed phases run in order, one calibration-only generation, safe bounded motion, no release/recorder, `SUCCEEDED`, all declared outputs and exactly 17 measurements. If interrupted or failed, inspect process/log/output state, retain the run unchanged, and restart from input validation under a new run ID; never reuse `run-status.json` as a checkpoint.

- [ ] **Step 2: Stop for exact parameter approval.**

Present the 17 values, units, formulas, distributions, margins, selected model/camera/tracker identities and first failure if any. Do not modify tracked production config until the user explicitly approves this exact bundle digest.

- [ ] **Step 3: Promote the approved values and verify byte-for-byte.**

Use `apply_patch` once to copy the approved bundle's exact model identity, 17 values and controlled dependencies into `head_search_v2.json`. Do not use a formatter or a script that rewrites unrelated fields. Then run:

```zsh
: "${APPROVED_BUNDLE_SHA256:?set this only from the user's exact approval message}"
test "$APPROVED_BUNDLE_SHA256" = "$(sha256sum "$CAL_RUN/head-search-calibration-bundle.json" | cut -d' ' -f1)" || exit 1
run_logged "$CAL_RUN/verify-promoted-config.console.log" \
  ros2 run so101_demo_py so101_head_search_calibration verify-promoted-config \
  --bundle "$CAL_RUN/head-search-calibration-bundle.json" \
  --production-config src/so101_demo_py/config/mujoco/act/head_search_v2.json \
  --approved-bundle-sha256 "$APPROVED_BUNDLE_SHA256" \
  --approval-output "$CAL_RUN/approval-receipt.json" || exit 1
```

The config edit copies approved values and identities only. It must not recompute, round, clamp or silently substitute a threshold.

- [ ] **Step 4: Commit promotion and rerun source-level affected gates.**

```zsh
git add src/so101_demo_py/config/mujoco/act/head_search_v2.json \
  docs/experiments/so101-act-data-experiment-ledger.md
git diff --cached --check
git commit -m "config: promote calibrated head search bundle"

head_test -n 8 src/so101_demo_py/test -q || exit 1
head_test -n 8 src/so101_teleop/test -q || exit 1
```

- [ ] **Step 5: Build the final frozen runtime and run installed gates.**

```zsh
FINAL_RUN="$HEAD_EVIDENCE/head-final-runtime-$(date -u +%Y%m%dT%H%M%SZ)"
test ! -e "$FINAL_RUN" || exit 1
mkdir "$FINAL_RUN" || exit 1
git rev-parse HEAD >"$FINAL_RUN/source-commit.txt" || exit 1
source /opt/ros/jazzy/setup.zsh
set -o pipefail
new_head_scratch || exit 1
run_logged "$FINAL_RUN/build.console.log" /usr/bin/time -p \
  "$HEAD_PYTHON" "$HEAD_COLCON" --log-base "$FINAL_RUN/build-log" build \
  --build-base "$FINAL_RUN/build" \
  --install-base "$FINAL_RUN/install" \
  --packages-up-to so101_demo_py so101_teleop --symlink-install --executor sequential \
  --cmake-args -DPython3_EXECUTABLE="$HEAD_PYTHON" || exit 1
test -f "$FINAL_RUN/install/setup.zsh" || exit 1
source "$FINAL_RUN/install/setup.zsh"
test "$(ros2 pkg prefix so101_demo_py)" = "$FINAL_RUN/install/so101_demo_py" || exit 1
test "$(ros2 pkg prefix so101_teleop)" = "$FINAL_RUN/install/so101_teleop" || exit 1
new_head_scratch || exit 1
run_logged "$FINAL_RUN/test-demo-ordinary.console.log" /usr/bin/time -p \
  "$HEAD_PYTHON" "$HEAD_COLCON" --log-base "$FINAL_RUN/test-log-demo-ordinary" test \
  --build-base "$FINAL_RUN/build" \
  --install-base "$FINAL_RUN/install" \
  --packages-select so101_demo_py --return-code-on-test-failure --executor sequential \
  --pytest-args test || exit 1
new_head_scratch || exit 1
run_logged "$FINAL_RUN/test-teleop.console.log" /usr/bin/time -p \
  "$HEAD_PYTHON" "$HEAD_COLCON" --log-base "$FINAL_RUN/test-log-teleop" test \
  --build-base "$FINAL_RUN/build" \
  --install-base "$FINAL_RUN/install" \
  --packages-select so101_teleop --return-code-on-test-failure --executor sequential || exit 1
head_colcon test-result --test-result-base "$FINAL_RUN/build" --verbose \
  >"$FINAL_RUN/test-result.txt" || exit 1
test -x "$FINAL_RUN/install/so101_teleop/lib/so101_teleop/so101_unified_web_server.py" || exit 1
test -f "$FINAL_RUN/install/so101_teleop/share/so101_teleop/web/index.html" || exit 1
```

Record `$FINAL_RUN` in the ledger together with package, console script, model, CUDA, config, camera, tracker and web bundle identities. Task 14 must source exactly `$FINAL_RUN/install/setup.zsh`; this is the final controlled runtime freeze.

### Task 14: Run production smoke, 40 serial scenarios, three restarts, and Teleop acceptance

**Files:** No controlled source/config edits are allowed. Only ledger/evidence appends may occur. Any source/config change invalidates Task 13 and returns to its first step with a new run root.

**Interfaces:** Consumes the frozen installed runtime and approved calibration bundle. Produces the final production, 40-scenario, restart, head-only qualification, Teleop and evidence-readback verdicts.

- [ ] **Step 1: Verify exclusive ownership before the formal qualifier starts its owned stack.**

Read the fresh process table, ROS graph, GPU processes, tmux ownership and evidence root. Refuse to proceed if another detector, MuJoCo instance, controller owner or campaign holds the resources. Do not pre-start a stack: the qualifier owns every start and teardown. During qualification confirm one YOLO instance, CUDA, correct weights/bundle SHA and effective 17-value readback.

- [ ] **Step 2: Run the complete no-resume qualification command.**

```zsh
QUAL_RUN="$HEAD_EVIDENCE/head-qualification-$(date -u +%Y%m%dT%H%M%SZ)"
: "${CAL_RUN:?set to the exact approved Task 13 calibration run root}"
: "${FINAL_RUN:?set to the exact frozen Task 13 runtime root}"
SCENARIO_PARTITIONS="$PWD/src/so101_demo_py/config/act/head-search-scenario-partitions-v1.json"
test ! -e "$QUAL_RUN" || exit 1
case "$CAL_RUN" in "$HEAD_EVIDENCE"/*) ;; *) exit 1 ;; esac
case "$FINAL_RUN" in "$HEAD_EVIDENCE"/*) ;; *) exit 1 ;; esac
test -f "$CAL_RUN/head-search-calibration-bundle.json" || exit 1
test -f "$CAL_RUN/approval-receipt.json" || exit 1
test -f "$FINAL_RUN/install/setup.zsh" || exit 1
test -f "$SCENARIO_PARTITIONS" || exit 1
source "$FINAL_RUN/install/setup.zsh"
test "$(ros2 pkg prefix so101_demo_py)" = "$FINAL_RUN/install/so101_demo_py" || exit 1
QUAL_LAUNCH_LOG="$HEAD_EVIDENCE/head-qualification-launch-$(date -u +%Y%m%dT%H%M%SZ).log"
run_logged "$QUAL_LAUNCH_LOG" \
  ros2 run so101_demo_py so101_head_search_calibration qualify \
  --run-root "$QUAL_RUN" \
  --bundle "$CAL_RUN/head-search-calibration-bundle.json" \
  --approval-receipt "$CAL_RUN/approval-receipt.json" \
  --production-config src/so101_demo_py/config/mujoco/act/head_search_v2.json \
  --episode-partitions "$SCENARIO_PARTITIONS" \
  --profile mujoco --serial \
  --anchors default,left,forward || exit 1
```

The command's fixed phases are `production-smoke -> qualification-40 -> FULL_RESTART(default) -> FULL_RESTART(left) -> FULL_RESTART(forward) -> aggregate`. It has no phase-select, skip, resume or existing-root mode. If any phase fails or is interrupted, inspect and retain the run, then repeat the entire command under a new `QUAL_RUN`.

- [ ] **Step 3: Read back production smoke and 40-scene evidence.**

The smoke must prove producer → sealed journal → actual aggregator, correct `TARGET_LOCKED`, 10 Hz continuity, bounded commands, three-sample stop proof and exact runtime identity. A mock/fixture-only result does not pass.

Expected: ten condition classes × four unseen seeds, one at a time. Legal single cup ends `TARGET_LOCKED`; two cups end `TARGET_AMBIGUOUS`; no cup ends `TARGET_NOT_FOUND` only with complete coverage; interrupted input ends the old attempt fail-closed, proves stop, clears tracker/lock state and reacquires under a new attempt. Every scenario has zero wrong locks, zero unsafe commands, valid timing and CUDA-only evidence.

- [ ] **Step 4: Read back exactly one independent FULL_RESTART per anchor.**

Each phase tears down and reconstructs the one stack, then passes graph, detector, search, lock, timing and stop gates. The manifest must contain exactly `default`, `left`, and `forward`, once each. Do not add a five-consecutive loop.

- [ ] **Step 5: Verify the head-only qualification documents.**

Read back `head-search-qualification.json` and `head-search-qualified-report.json`. Confirm the former holds one PASS sample with all 17 + four camera measurements and cites the smoke, 40 scenes and three restart roots. Confirm the latter says only `HEAD_SEARCH_QUALIFIED`, then prove `task8_live` still refuses it.

- [ ] **Step 6: Start one separately owned Teleop-acceptance stack, run the installed acceptance, and inspect fresh screenshots.**

The qualifier tears down its final `forward` restart before returning; do not depend on a leaked child process. Start one new `TELEOP_ACCEPTANCE` stack from the same frozen install, selected model, promoted config, approval receipt and closed head-only report. This startup is a separate functional-acceptance fixture, not a fourth qualification `FULL_RESTART`, and it cannot mutate the qualification report. Run the installed unified app against that one stack and detector. Verify Raw/Overlay correlation, bounded absolute and step movement, conflicting owner refusal, stale-frame refusal, stop proof and atomic capture.

```zsh
TELEOP_ACCEPT_ROOT="$HEAD_EVIDENCE/teleop-head-camera-acceptance-$(date -u +%Y%m%dT%H%M%SZ)"
test ! -e "$TELEOP_ACCEPT_ROOT" || exit 1
mkdir "$TELEOP_ACCEPT_ROOT" || exit 1
ros2 run so101_demo_py so101_head_search_calibration serve-teleop \
  --run-root "$TELEOP_ACCEPT_ROOT/runtime" \
  --qualification-report "$QUAL_RUN/head-search-qualified-report.json" \
  --bundle "$CAL_RUN/head-search-calibration-bundle.json" \
  --approval-receipt "$CAL_RUN/approval-receipt.json" \
  --production-config src/so101_demo_py/config/mujoco/act/head_search_v2.json \
  --profile mujoco --ready-file "$TELEOP_ACCEPT_ROOT/runtime-ready.json" \
  >"$TELEOP_ACCEPT_ROOT/runtime.log" 2>&1 &
runtime_pid=$!
server_pid=""
cleanup_head_acceptance() {
  test -z "$server_pid" || { kill "$server_pid" 2>/dev/null; wait "$server_pid" 2>/dev/null; }
  test -z "$runtime_pid" || { kill "$runtime_pid" 2>/dev/null; wait "$runtime_pid" 2>/dev/null; }
}
trap cleanup_head_acceptance EXIT
for attempt in {1..180}; do
  test -f "$TELEOP_ACCEPT_ROOT/runtime-ready.json" && break
  kill -0 "$runtime_pid" 2>/dev/null || exit 1
  sleep 1
done
test -f "$TELEOP_ACCEPT_ROOT/runtime-ready.json" || exit 1
SO101_UNIFIED_BACKEND=mujoco_py \
SO101_UNIFIED_INSTALL_PREFIX="$FINAL_RUN/install" \
SO101_UNIFIED_EVIDENCE_ROOT="$TELEOP_ACCEPT_ROOT" \
SO101_UNIFIED_RUNTIME_ID="$(<"$FINAL_RUN/source-commit.txt")" \
SO101_UNIFIED_ROS_PYTHON="$HEAD_PYTHON" \
  "$FINAL_RUN/install/so101_teleop/lib/so101_teleop/so101_unified_web_server.py" \
  --host 127.0.0.1 --port 18082 --capture-dir "$TELEOP_ACCEPT_ROOT/captures" \
  >"$TELEOP_ACCEPT_ROOT/server.log" 2>&1 &
server_pid=$!
for attempt in {1..60}; do
  curl --silent --fail http://127.0.0.1:18082/teleop/head-camera/status \
    >"$TELEOP_ACCEPT_ROOT/status-before.json" && break
  kill -0 "$server_pid" 2>/dev/null || exit 1
  sleep 1
done
curl --fail http://127.0.0.1:18082/teleop/head-camera/status \
  >"$TELEOP_ACCEPT_ROOT/status-before.json" || exit 1
(cd "$PWD/src/so101_teleop/web" && \
  SO101_TELEOP_BASE_URL=http://127.0.0.1:18082 \
  SO101_E2E_EVIDENCE_ROOT="$TELEOP_ACCEPT_ROOT" \
  bun run test:e2e -- e2e/head-camera.spec.ts) || exit 1
kill "$server_pid"
set +o errexit
wait "$server_pid"
server_rc=$?
set -o errexit
case $server_rc in 0|130|143) ;; *) exit 1 ;; esac
print -r -- "$server_rc" >"$TELEOP_ACCEPT_ROOT/server.rc"
server_pid=""
kill "$runtime_pid"
set +o errexit
wait "$runtime_pid"
runtime_rc=$?
set -o errexit
test $runtime_rc -eq 0 || exit 1
print -r -- "$runtime_rc" >"$TELEOP_ACCEPT_ROOT/runtime.rc"
runtime_pid=""
test -f "$TELEOP_ACCEPT_ROOT/runtime/teardown-receipt.json" || exit 1
trap - EXIT
unfunction cleanup_head_acceptance
```

Because `SO101_TELEOP_BASE_URL` is set, Playwright must not start Vite. The case captures fresh light/dark desktop/narrow screenshots for Raw, Overlay, conflict, stale, stopping and stopped states plus exact raw/overlay frame pairs. Inspect those files and their browser URL. The page must show the same model and bundle SHA as the production process and the process/GPU readback must show one detector. The teardown receipt must prove controller stop, process-group exit and graph clear.

- [ ] **Step 7: Read back all evidence and close the ledger.**

Verify every manifest digest, exit code, producer/journal/aggregator chain, scenario count, anchor restart, screenshot and runtime identity from disk. Append retained runs, archived runs and deletion candidates to the ledger. Do not delete anything. Report the final result as `HEAD_SEARCH_QUALIFIED` or an exact blocker; no threshold, worker, camera, sample-rate or device downgrade is allowed.

```zsh
git add docs/experiments/so101-act-data-experiment-ledger.md
git diff --cached --check
git commit -m "docs: record head search qualification"
```

This final commit may contain only the ledger closeout. Any controlled source/config/policy change invalidates Task 13 and requires a new run root.

## Review checkpoints

- After each Task 1–10 commit: independent code review before the next task boundary.
- After Task 4 and Task 11: confirm the explicit benchmark implementation gate actually collected `benchmark_test`.
- After Task 12: review the exact A/B/C report and deterministic choice before calibration.
- After Task 13 Step 1: user approves the exact 17-value bundle before tracked config changes.
- After Task 14 Step 5: independently verify the head-only report cannot grant Task 8 readiness.
- After Task 14: independently review exact diff, test logs, production runtime evidence and ledger before declaring the Head Search work complete.

## Completion definition

This plan is complete only when Tasks 1–14 are all complete, the production head camera passes the three-anchor geometry seal with zero `in_frame=0` failures, the selected model passes both camera-domain gates, all 17 parameters are consumed by production and bound to one approved sample, the 40 serial scenarios and three independent anchor restarts pass, Teleop is visually and functionally accepted, and evidence readback closes without an identity or digest mismatch. A green unit test suite, a successful training process, a generated bundle, or an unreviewed screenshot is not completion on its own.
