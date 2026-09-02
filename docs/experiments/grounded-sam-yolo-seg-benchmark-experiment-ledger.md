---
task_id: so101-grounded-sam-yolo-seg-benchmark-20260902-ab-v1
goal: 同数据同指标完成 YOLO-Seg 与 Grounded-SAM 双平台 RGB 实例分割 A/B benchmark
success_contract: 两平台两模型完整 val 200 与 test 200；无跳样本；threshold-lock 只读 val；全部证据 SHA 可回读
worktree: /Users/matianyi/.codex/worktrees/5b15/moveit-demo
branch: codex/v5-t004-yolo-seg-rgbd
base_commit: 08c9fc0f0998f4df60c123b9affe8ea1be62b32f
current_commit: 608fc83c9a4ec6d42c8acca945f80881a163329b
evidence_root: /data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1
debug_evidence_root: /tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1
latest_checkpoint: CP-BENCH-001
next_experiment: EXP-BENCH-001
confirmed_conclusions: []
disproven_routes: []
open_hypotheses:
  - Both frozen model configurations can complete the formal macOS and Linux benchmark without skipped samples.
---

# Grounded-SAM / YOLO-Seg Benchmark Experiment Ledger

This is an audit record. Only `PLANNED`, `RUNNING`, `VALID`, and `INVALID` are legal experiment states. No formal archive, model inference, remote, or hardware execution is part of Task 9.

## Task 9 pre-execution provenance

- Source base commit: `08c9fc0f0998f4df60c123b9affe8ea1be62b32f`
- Source current commit: `608fc83c9a4ec6d42c8acca945f80881a163329b`
- Planned installed overlay: `/Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-benchmark/`
- Planned installed executable: `/Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-benchmark/so101_demo_py/lib/so101_demo_py/perception_benchmark`
- ROS domain ID: `NOT_APPLICABLE_NO_ROS`
- Gazebo partition: `NOT_APPLICABLE_NO_GAZEBO`
- Formal test access: `SEALED`; Task 9 does not unlock or inspect the formal test split.
- Runtime processes: none; Task 9 performs only CLI fixture and evidence-format verification.
- Task 9 fixture result: `NON_FORMAL_DRY_RUN`; it is implementation evidence only, does not transition an experiment state, and is excluded from validation and test inventories.

## EXP-BENCH-001 — Asset verification and non-formal fixture dry run

- Status: PLANNED
- Command: `perception_benchmark verify-assets --model yolo_seg --weights <absolute-best.pt> --weights-sha256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781`
- Command: `perception_benchmark dry-run --config install-benchmark/so101_demo_py/share/so101_demo_py/config/perception_benchmark/benchmark.yaml --output-root /tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/dry-run/task9-608fc83 --adapter-fixture src/so101_demo_py/test/fixtures/perception_benchmark/dry-run-adapters.json`
- Evidence: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/dry-run/task9-608fc83/`
- Lifecycle: retain Task 9 dry-run and tests; archive superseded formal batches only under `/data/work/so101-evidence/archived/grounded-sam-yolo-seg-benchmark/`; no current deletion candidates.

## EXP-BENCH-002 — macOS validation collection

- Status: PLANNED
- Command: `perception_benchmark collect --run-id 20260902-ab-v1-macos-yolo-val --platform macos --model yolo_seg --device mps --dtype float32 --split val --run-kind VAL_RAW --dataset-inventory <val>/inventory.json --dataset-archive-sha256 c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1 --inventory-sha256 <external-val-inventory-sha256> --weights <absolute-best.pt> --weights-sha256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781 --config <installed-benchmark.yaml> --source-commit <40-hex-commit> --output-root /data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/val/macos/yolo_seg/raw`
- Evidence: `/data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/val/macos/{yolo_seg,grounded_sam}/raw/`
- Lifecycle: retain valid terminal runs; archive superseded attempts; incomplete runs are deletion candidates only after explicit authorization.

## EXP-BENCH-003 — Linux validation collection

- Status: PLANNED
- Command: `perception_benchmark collect --run-id 20260902-ab-v1-linux-yolo-val --platform linux --model yolo_seg --device cuda --dtype float32 --split val --run-kind VAL_RAW --dataset-inventory <val>/inventory.json --dataset-archive-sha256 c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1 --inventory-sha256 <external-val-inventory-sha256> --weights <absolute-best.pt> --weights-sha256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781 --config <installed-benchmark.yaml> --source-commit <40-hex-commit> --output-root /data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/val/linux/yolo_seg/raw`
- Evidence: `/data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/val/linux/{yolo_seg,grounded_sam}/raw/`
- Lifecycle: retain valid terminal runs; archive superseded attempts; incomplete runs are deletion candidates only after explicit authorization.

## EXP-BENCH-004 — Joint validation calibration and threshold locks

- Status: PLANNED
- Command: `perception_benchmark calibrate --model yolo_seg --dataset-inventory <val>/inventory.json --dataset-archive-sha256 c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1 --inventory-sha256 <external-val-inventory-sha256> --mac-run-root <mac-val-run> --mac-run-expectation <externally-anchored-mac-expectation.json> --mac-run-expectation-sha256 <external-mac-expectation-sha256> --linux-run-root <linux-val-run> --linux-run-expectation <externally-anchored-linux-expectation.json> --linux-run-expectation-sha256 <external-linux-expectation-sha256> --source-commit <40-hex-commit> --output-root <locks>/yolo_seg`
- Evidence: `/data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/locks/{yolo_seg,grounded_sam}.json`
- Lifecycle: retain both verified formal locks permanently with their validation run roots; never rank or calibrate from test.

## EXP-BENCH-005 — macOS frozen test

- Status: PLANNED
- Command: `perception_benchmark unlock-test --archive <archive> --expected-sha256 c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1 --sealed-member-inventory <sealed.json> --yolo-threshold-lock <yolo-lock.json> --grounded-sam-threshold-lock <grounded-lock.json> --access-log <access.ndjson> --output-root <test-root>`
- Command: `perception_benchmark collect --run-id 20260902-ab-v1-macos-yolo-test-raw --platform macos --model yolo_seg --device mps --dtype float32 --split test --run-kind TEST_RAW_FROZEN --dataset-inventory <test>/inventory.json --dataset-archive-sha256 c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1 --inventory-sha256 <external-test-inventory-sha256> --test-access-event-sha256 <external-event-sha256> --sealed-member-inventory-sha256 <external-sealed-sha256> --yolo-lock-sha256 <external-yolo-lock-sha256> --grounded-sam-lock-sha256 <external-grounded-lock-sha256> --threshold-lock <yolo-lock.json> --output-root /data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/test/macos/yolo_seg/raw_frozen <asset-and-source-arguments>`
- Evidence: `/data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/test/macos/`
- Lifecycle: retain the one frozen formal test; archive invalid attempts without overwriting; delete nothing without authorization.

## EXP-BENCH-006 — Linux frozen test

- Status: PLANNED
- Command: `perception_benchmark collect --run-id 20260902-ab-v1-linux-yolo-test-raw --platform linux --model yolo_seg --device cuda --dtype float32 --split test --run-kind TEST_RAW_FROZEN --dataset-inventory <test>/inventory.json --dataset-archive-sha256 c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1 --inventory-sha256 <external-test-inventory-sha256> --test-access-event-sha256 <external-event-sha256> --sealed-member-inventory-sha256 <external-sealed-sha256> --yolo-lock-sha256 <external-yolo-lock-sha256> --grounded-sam-lock-sha256 <external-grounded-lock-sha256> --threshold-lock <yolo-lock.json> --output-root /data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/test/linux/yolo_seg/raw_frozen <asset-and-source-arguments>`
- Evidence: `/data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/test/linux/`
- Lifecycle: retain the one frozen formal test; archive invalid attempts without overwriting; delete nothing without authorization.

## EXP-BENCH-007 — Performance, cross-platform comparison, and report

- Status: PLANNED
- Command: `perception_benchmark aggregate --aggregation-plan <externally-anchored-aggregation-plan.json> --aggregation-plan-sha256 <external-plan-sha256> --output-root /data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/report`
- Command: `perception_benchmark verify-evidence --output-root /data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/report`
- Evidence: `/data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/report/`
- Lifecycle: retain report plus every indexed dependency; archive superseded reports; unindexed staging directories become deletion candidates after explicit authorization.

## EXP-BENCH-008 — Task 11 remediation proposal

- Status: PLANNED
- Command: `perception_benchmark dry-run --config <installed-benchmark.yaml> --output-root /tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/task11-remediation/<run-id> --adapter-fixture <recorded-fixture.json>`
- Evidence: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/task11-remediation/` followed, after asset qualification, by `/data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/task11-remediation/`.
- Lifecycle: retain the accepted remediation proof; archive superseded trials; rejected trial directories remain deletion candidates pending explicit authorization.
