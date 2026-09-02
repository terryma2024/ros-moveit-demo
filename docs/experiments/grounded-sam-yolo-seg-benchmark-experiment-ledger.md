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

## CP-BENCH-002 — CORRECTION after independent review of `8985c56`

This checkpoint is append-only. It supersedes conflicting lifecycle wording above without rewriting the original audit record.

- Review state: `8985c56` had two critical and five important findings. Formal commands were not yet fully bound to the frozen config/provenance; calibration cross-run provenance and output isolation were incomplete; expected model/setup and malformed-plan errors were not all converted into stable CLI failures; test unlock output preflight occurred too late; and the config omitted registered Task 6 low-floor limits.
- Fix RED command: `PYTHONPATH=/Users/matianyi/.codex/worktrees/5b15/moveit-demo/build-benchmark/so101_demo_py /Users/matianyi/ros2_jazzy/.venv/bin/python -m pytest -q src/so101_demo_py/test/test_perception_benchmark_cli.py --junitxml=/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests/task9/fix1-red.xml`
- Fix RED evidence: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests/task9/fix1-red.xml`; result `13 passed, 9 failed`, with all failures caused by missing reviewed behavior rather than an import/install boundary.
- Current fix command: `PYTHONPATH=/Users/matianyi/.codex/worktrees/5b15/moveit-demo/build-benchmark/so101_demo_py /Users/matianyi/ros2_jazzy/.venv/bin/python -m pytest -q src/so101_demo_py/test/test_perception_benchmark_cli.py --junitxml=/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests/task9/fix1-cli-green.xml`
- Current fix evidence: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests/task9/fix1-cli-green.xml`; result `22 passed`.
- Authoritative retained dry-run at this checkpoint: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/dry-run-task9-final/`; its public evidence-index readback returned `VERIFIED 41`, with `8` samples and `16` model records.
- Superseded deletion candidate: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/dry-run/`. It has not been deleted.
- Retained fix evidence: all Task 9 RED/GREEN JUnit files under `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests/task9/`.
- Archived runs: none.
- Formal execution: none. No formal archive/model/test, ROS, remote, or hardware command ran.

## CP-BENCH-003 — FixRound1 installed verification

This checkpoint supersedes CP-BENCH-002 only for the authoritative non-formal dry-run lifecycle. Earlier records remain unchanged for auditability.

- Full regression command: `PYTHONPATH=/Users/matianyi/.codex/worktrees/5b15/moveit-demo/build-benchmark/so101_demo_py /Users/matianyi/ros2_jazzy/.venv/bin/python -m pytest -q src/so101_demo_py/test/test_perception_benchmark_*.py --junitxml=/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests/task9/fix1-benchmark-full.xml`
- Full regression evidence: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests/task9/fix1-benchmark-full.xml`; result `526 passed, 1 pre-existing pyparsing deprecation warning`.
- Installed build command: `source install/setup.zsh && /Users/matianyi/ros2_jazzy/.venv/bin/colcon --log-base log-benchmark build --packages-select so101_demo_py --packages-ignore mujoco_ros2_control_msgs mujoco_vendor so101_teleop mujoco_3d_lidar mujoco_ros2_control_plugins mujoco_ros2_control so101_mujoco_support --symlink-install --build-base build-benchmark --install-base install-benchmark`
- Installed build result: one package finished successfully. The later macOS LaunchServices `kLSNoExecutableErr` diagnostic did not change the successful colcon exit status and no GUI was required.
- Installed dry-run command: `source install-benchmark/setup.zsh && /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-benchmark/so101_demo_py/lib/so101_demo_py/perception_benchmark dry-run --config /Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-benchmark/so101_demo_py/share/so101_demo_py/config/perception_benchmark/benchmark.yaml --output-root /tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/dry-run-task9-fix1 --adapter-fixture /Users/matianyi/.codex/worktrees/5b15/moveit-demo/src/so101_demo_py/test/fixtures/perception_benchmark/dry-run-adapters.json`
- Authoritative retained dry-run: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/dry-run-task9-fix1/`; public evidence-index readback returned `VERIFIED 41`.
- Authoritative dry-run counts: `formal=false`, `run_kind=NON_FORMAL_DRY_RUN`, `8` samples, `16` model records, `8` records per model, and `2` samples for each registered scenario. No `inventory.json` exists.
- Superseded deletion candidates, not deleted: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/dry-run/` and `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/dry-run-task9-final/`.
- Retained implementation evidence: FixRound1 RED/GREEN/full JUnit, `build-benchmark/`, `install-benchmark/`, and `log-benchmark/`.
- Archived runs: none.
- Formal execution: none. No formal archive/model/test, ROS, remote, or hardware command ran.

## CP-BENCH-004 — FixRound1 final regression correction

This append-only checkpoint records the final regression after adding the sealed-inventory pre-event test. It supersedes the CP-BENCH-003 test count, but not its installed dry-run lifecycle decision.

- Final CLI evidence: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests/task9/fix1-cli-final2.xml`; result `34 passed`.
- Final full regression command: `PYTHONPATH=/Users/matianyi/.codex/worktrees/5b15/moveit-demo/build-benchmark/so101_demo_py /Users/matianyi/ros2_jazzy/.venv/bin/python -m pytest -q src/so101_demo_py/test/test_perception_benchmark_*.py --junitxml=/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests/task9/fix1-benchmark-full-final.xml`
- Final full regression evidence: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests/task9/fix1-benchmark-full-final.xml`; result `527 passed, 1 pre-existing pyparsing deprecation warning`.
- Authoritative retained dry-run remains `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/dry-run-task9-fix1/`; its evidence index remains `VERIFIED 41`.
- Archived runs: none. No evidence was deleted.

## CP-BENCH-005 — CORRECTION for frozen-config command contracts

Status: `PLANNED`. Reason: the formal archive, verified model assets, cross-platform runs, and threshold locks have not been staged or executed. Every conflicting command in EXP-BENCH-001 through EXP-BENCH-007 is superseded by the commands below. The old text remains above only as immutable audit history.

The replacement commands use these exact planned paths:

```zsh
BENCHMARK_CONFIG=/Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-benchmark/so101_demo_py/share/so101_demo_py/config/perception_benchmark/benchmark.yaml
BENCHMARK_ROOT=/data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1
ARCHIVE_ROOT=$BENCHMARK_ROOT/inputs/datasets/so101-v5-t004-yolo-seg-synthetic
ARCHIVE=$ARCHIVE_ROOT/so101-v5-t004-yolo-seg-synthetic-20260831-f09cf88.tar.gz
YOLO_WEIGHTS=$BENCHMARK_ROOT/inputs/models/yolo_seg/best.pt
GROUNDED_BUNDLE=$BENCHMARK_ROOT/inputs/models/grounded_sam
SOURCE_COMMIT=$(GIT_DIR=/Users/matianyi/Projects/robot_demo_001/.git/modules/moveit-demo/worktrees/moveit-demo1 GIT_WORK_TREE=/Users/matianyi/.codex/worktrees/5b15/moveit-demo git rev-parse HEAD)
VAL_INVENTORY_SHA256=$(tr -d '[:space:]' < $BENCHMARK_ROOT/anchors/val-inventory.sha256)
MAC_VAL_EXPECTATION_SHA256=$(tr -d '[:space:]' < $BENCHMARK_ROOT/anchors/macos-yolo-val-expectation.sha256)
LINUX_VAL_EXPECTATION_SHA256=$(tr -d '[:space:]' < $BENCHMARK_ROOT/anchors/linux-yolo-val-expectation.sha256)
AGGREGATION_PLAN_SHA256=$(tr -d '[:space:]' < $BENCHMARK_ROOT/anchors/aggregation-plan.sha256)
```

- `verify-assets` replacement, YOLO-Seg: `perception_benchmark verify-assets --config $BENCHMARK_CONFIG --model yolo_seg --weights $YOLO_WEIGHTS --weights-sha256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781`
- `verify-assets` replacement, Grounded-SAM: `perception_benchmark verify-assets --config $BENCHMARK_CONFIG --model grounded_sam --model-root $GROUNDED_BUNDLE --manifest-sha256 838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3`
- `inspect-archive` replacement: `perception_benchmark inspect-archive --config $BENCHMARK_CONFIG --archive $ARCHIVE --expected-sha256 c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1 --sealed-member-inventory $BENCHMARK_ROOT/dataset/sealed-test-members.json`
- `prepare-dataset` replacement: `perception_benchmark prepare-dataset --config $BENCHMARK_CONFIG --archive $ARCHIVE --expected-sha256 c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1 --split val --output-root $BENCHMARK_ROOT/dataset/val`
- `collect` replacement, macOS YOLO validation: `perception_benchmark collect --config $BENCHMARK_CONFIG --run-id 20260902-ab-v1-macos-yolo-val --platform macos --model yolo_seg --device mps --dtype float32 --split val --run-kind VAL_RAW --dataset-inventory $BENCHMARK_ROOT/dataset/val/inventory.json --dataset-archive-sha256 c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1 --inventory-sha256 $VAL_INVENTORY_SHA256 --weights $YOLO_WEIGHTS --weights-sha256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781 --source-commit $SOURCE_COMMIT --output-root $BENCHMARK_ROOT/val/macos/yolo_seg/raw`
- `calibrate` replacement: `perception_benchmark calibrate --config $BENCHMARK_CONFIG --model yolo_seg --dataset-inventory $BENCHMARK_ROOT/dataset/val/inventory.json --dataset-archive-sha256 c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1 --inventory-sha256 $VAL_INVENTORY_SHA256 --mac-run-root $BENCHMARK_ROOT/val/macos/yolo_seg/raw --mac-run-expectation $BENCHMARK_ROOT/anchors/macos-yolo-val-expectation.json --mac-run-expectation-sha256 $MAC_VAL_EXPECTATION_SHA256 --linux-run-root $BENCHMARK_ROOT/val/linux/yolo_seg/raw --linux-run-expectation $BENCHMARK_ROOT/anchors/linux-yolo-val-expectation.json --linux-run-expectation-sha256 $LINUX_VAL_EXPECTATION_SHA256 --source-commit $SOURCE_COMMIT --output-root $BENCHMARK_ROOT/locks/yolo_seg`
- `unlock-test` replacement: `perception_benchmark unlock-test --config $BENCHMARK_CONFIG --archive $ARCHIVE --expected-sha256 c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1 --sealed-member-inventory $BENCHMARK_ROOT/dataset/sealed-test-members.json --yolo-threshold-lock $BENCHMARK_ROOT/locks/yolo_seg/threshold-lock.json --grounded-sam-threshold-lock $BENCHMARK_ROOT/locks/grounded_sam/threshold-lock.json --access-log $BENCHMARK_ROOT/dataset/test-access.ndjson --output-root $BENCHMARK_ROOT/dataset/test`
- `aggregate` replacement: `perception_benchmark aggregate --config $BENCHMARK_CONFIG --aggregation-plan $BENCHMARK_ROOT/anchors/aggregation-plan.json --aggregation-plan-sha256 $AGGREGATION_PLAN_SHA256 --bootstrap-seed 20260902 --bootstrap-repetitions 10000 --output-root $BENCHMARK_ROOT/report`

Exact planned evidence paths are `$BENCHMARK_ROOT/dataset/sealed-test-members.json`, `$BENCHMARK_ROOT/dataset/{val,test}/inventory.json`, `$BENCHMARK_ROOT/{val,test}/{macos,linux}/{yolo_seg,grounded_sam}/`, `$BENCHMARK_ROOT/locks/{yolo_seg,grounded_sam}/threshold-lock.json`, `$BENCHMARK_ROOT/anchors/{val-inventory,macos-yolo-val-expectation,linux-yolo-val-expectation,aggregation-plan}.sha256`, and `$BENCHMARK_ROOT/report/evidence-index.json`. Each SHA sidecar must be created and registered as an independent external anchor before the corresponding command transitions from `PLANNED` to `RUNNING`; it must never be replaced by a self-reported digest from the command being verified.

## CP-BENCH-006 — FixRound2 output and plan preflight correction

- Review state: four important findings required a narrow macOS system-alias exception, shared output preflight for every mutating command, an immediate second unlock output check after archive verification, recursive aggregation-plan input validation, and executable replacement commands containing the frozen `--config` argument.
- RED evidence: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests/task9/fix2-red.xml`; result `35 passed, 9 failed` before implementation.
- CLI GREEN evidence: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests/task9/fix2-cli-green.xml`; result `44 passed`.
- Full regression evidence: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests/task9/fix2-benchmark-full.xml`; result `537 passed, 1 pre-existing pyparsing deprecation warning`.
- Installed build: the isolated `build-benchmark` / `install-benchmark` / `log-benchmark` build completed one package successfully. The later macOS LaunchServices `kLSNoExecutableErr` diagnostic did not change the successful colcon exit status.
- Authoritative retained dry-run: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/dry-run-task9-fix2/`; public evidence-index readback returned `VERIFIED 41`.
- Authoritative dry-run counts: `formal=false`, `run_kind=NON_FORMAL_DRY_RUN`, `8` samples, `16` model records, `8` records per model, `2` samples per registered scenario, and no `inventory.json`.
- Unlock boundary: the CLI performs an immediate output absence/safe-parent recheck after the potentially expensive archive verification and before invoking `unlock_test_seal`. This closes the reproduced window. A portable userspace preflight cannot make a future append to the access log and later archive extraction one atomic filesystem transaction; this checkpoint does not claim otherwise.
- Superseded deletion candidates, not deleted: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/dry-run/`, `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/dry-run-task9-final/`, and `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/dry-run-task9-fix1/`.
- Retained implementation evidence: every Task 9 RED/GREEN/full JUnit file plus `build-benchmark/`, `install-benchmark/`, and `log-benchmark/`.
- Archived runs: none. No evidence was deleted.
- Formal execution: none. No formal archive/model/test, ROS, remote, or hardware command ran.

## CP-BENCH-007 — FixRound3 resource-mapping validation

- Review state: one important finding remained after FixRound2. Raw JSON list-of-pairs values for `ResourceSample.unavailable_reasons` and `ResourceSample.tool_versions` could be normalized by `dict()` inside the constructor and reach external threshold-lock loading.
- Functional RED command: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=/Users/matianyi/.codex/worktrees/5b15/moveit-demo/build-benchmark/so101_demo_py /Users/matianyi/ros2_jazzy/.venv/bin/python -m pytest -q src/so101_demo_py/test/test_perception_benchmark_cli.py --junitxml=/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests/task9/fix3-red-functional-v2.xml`
- Functional RED evidence: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests/task9/fix3-red-functional-v2.xml`; result `46 passed, 3 failed`. The three failures prove that each mapping field separately and both fields together reached the mocked external threshold-lock loader before the fix. Earlier import and ROS pytest-plugin collection failures are environment-boundary records, not functional RED evidence.
- CLI GREEN evidence: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests/task9/fix3-cli-green.xml`; result `49 passed` after raw-document exact-key and `Mapping` validation. A raw valid mapping remains accepted, while list-valued scalar drift remains a typed `AGGREGATION_PLAN_INVALID` failure.
- Post-format CLI evidence: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests/task9/fix3-cli-final.xml`; result `49 passed`.
- Full regression evidence: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests/task9/fix3-full-green.xml`; result `542 passed, 1 pre-existing pyparsing deprecation warning`.
- Installed readback: `/Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-benchmark/so101_demo_py/lib/so101_demo_py/perception_benchmark verify-evidence --output-root /tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/dry-run-task9-fix2` returned `VERIFIED 41`.
- Authoritative retained dry-run remains `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/dry-run-task9-fix2/`. No new dry-run was generated. Readback remains `16` records, `formal=false`, `run_kind=NON_FORMAL_DRY_RUN`, `8` records per model, and `4` records per scenario (`2` per model per scenario).
- Superseded deletion candidates remain, without deletion: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/dry-run/`, `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/dry-run-task9-final/`, and `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/dry-run-task9-fix1/`.
- Retained implementation evidence: every Task 9 RED/GREEN/full JUnit file plus `build-benchmark/`, `install-benchmark/`, and `log-benchmark/`.
- Archived runs: none. No evidence was deleted.
- Formal execution: none. No formal archive/model/test, ROS, remote, or hardware command ran.

## CP-BENCH-008 — Task 10 package-gate provenance and RUNNING transition

This checkpoint is append-only. It starts the Task 10 package-gate experiment without rewriting the earlier `EXP-BENCH-001` audit entry.

- Experiment state: `EXP-BENCH-001` is `RUNNING` for Mac/Linux exact-source package gates only.
- Observation time: `2026-09-02T22:15:20Z` through `2026-09-02T22:15:41Z`.
- Lifecycle: `ISOLATED_STACK`; this task does not start a ROS graph, Gazebo, MoveIt, RViz, model inference, or hardware execution.
- Source commit: `1da1286ccd59cfa1deaa6da55c8dbd9b7f62fea4`.
- Mac worktree: `/Users/matianyi/.codex/worktrees/5b15/moveit-demo`; branch `codex/v5-t004-yolo-seg-rgbd`; preserved untracked paths are `build-benchmark/`, `build-task10-watermark-v2/`, `build-task11-tf-discovery/`, `install-benchmark/`, `install-task10-watermark-v2/`, `install-task11-tf-discovery/`, `log-benchmark/`, and `log-task10-watermark-v2/`.
- Mac canonical checkout: `/Users/matianyi/Projects/robot_demo_001/moveit-demo`; commit `b5f183353466264e0601d4946a8f3922691af575`; branch `main`; clean status. The parent checkout reported `-e7e0299cf8115214a0daf483cc40da6b09309091 moveit-demo`; no synchronization or mutation is authorized.
- ai-station canonical checkout: `/data/work/ws_moveit`; commit `e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4`; branch `main`; preserved untracked path `docs/experiments/ai-station-linux-headless-rgbd-four-point-upgrade-experiment-ledger.md`.
- Process ownership: no existing `perception_benchmark`, `move_group`, `rviz2`, or `gz sim` stack was observed on Mac. No such remote stack was observed; the only remote process match was the bounded read-only SSH wrapper that performed this query. No existing process will be stopped or replaced.
- Planned Mac install overlay: `/Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-benchmark/`.
- Planned Mac runtime executable/package prefix: `/Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-benchmark/so101_demo_py`.
- Planned isolated Linux checkout: `/data/work/so101-grounded-sam-yolo-benchmark-ab-v1` if absent; otherwise a new explicit suffix will be selected without overwriting the existing path.
- Planned isolated Linux install overlay: `<isolated-checkout>/install-benchmark/`.
- ROS domain ID: `NONE`.
- Gazebo partition: `NONE`.
- Success criteria: both Mac and Linux collect non-zero `so101_demo_py` tests with zero errors/failures; Linux source checkout is clean at the exact source commit; Mac `rclpy` resolves to ROS Jazzy; Linux `ros2 pkg prefix so101_demo_py` resolves inside the isolated checkout; all retained evidence is under the registered roots.
- Invalid criteria: any source/install/runtime provenance mismatch, zero tests, non-zero test command, any JUnit error/failure, unsafe pre-existing output path, or inability to preserve canonical checkout/process state.
- Command status: Mac package gate `PENDING`; exact-source bundle `PENDING`; Linux isolated build/package gate `PENDING`; evidence index `PENDING`.
- Evidence roots: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1` and `/data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1`.

## CP-BENCH-009 — Task 10 package-gate terminal result

This checkpoint is append-only and supersedes CP-BENCH-008 only for the terminal Task 10 state.

- Experiment state: `EXP-BENCH-001` is `INVALID`.
- Terminal observation time: `2026-09-02T22:57:06Z`.
- Conclusion: the Mac package gate passed after completing the candidate overlay, but the standard Linux `colcon test` package gate did not pass. This experiment is excluded from benchmark execution and cannot authorize Task 11 formal asset staging.
- First unsatisfied boundary: Linux package-test execution context. `colcon test` ran pytest from `build-benchmark/so101_demo_py`; the first failing test was `test_cup_pose_subscriber.py::test_setup_registers_the_cup_pose_subscriber_executable`, whose repository-root-relative read of `src/so101_demo_py/setup.py` raised `FileNotFoundError`.
- Additional observed Linux boundaries: the exact-source Git bundle contains the parent repository but not initialized `third_party/mujoco_ros2_control` submodule content; `torch` is unavailable in the ROS-only Python; and the Linux Pillow rasterizer identity does not match the frozen rasterizer identity used by the dataset tests. These are observations from the same invalid package run, not benchmark/model results.
- Mac focused command result: exit `0`; `49 passed`; JUnit `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests/mac-focused-cli.xml`.
- Mac first package command result: exit `1`; `1594 passed, 1 failed`; the failed provenance test found `so101_mujoco_support` in the ordinary `install/` underlay while `so101_demo_py` was in `install-benchmark/`. The failed JUnit remains `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests/mac-so101_demo_py.xml`.
- Mac candidate-overlay remediation: the first `so101_mujoco_support` build failed because CMake selected Homebrew Python 3.14 without `em`; the second build explicitly selected `/Users/matianyi/ros2_jazzy/.venv/bin/python3` and completed. No source file changed. The focused provenance regression then passed `1/1`.
- Mac final package command result: exit `0`; `1595 tests, 0 errors, 0 failures, 0 skipped`; final JUnit SHA-256 `691aab773daea7b2be74d676d45603301a4cebbee95b7a6ce3e554c69131b8fc`.
- Mac runtime provenance: `rclpy=/opt/ros/jazzy/rclpy/lib/python3.11/site-packages/rclpy/__init__.py`; `so101_demo_py` prefix `/Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-benchmark/so101_demo_py`; `so101_mujoco_support` prefix `/Users/matianyi/.codex/worktrees/5b15/moveit-demo/install-benchmark/so101_mujoco_support`; source commit `1da1286ccd59cfa1deaa6da55c8dbd9b7f62fea4`.
- Mac immutable gate evidence: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/tests/mac-package-gate/`; public verifier result `VERIFIED 4`; evidence-index SHA-256 `5a33f57a7acd8de4673ce155e5d5dd91caefd24ef731f463400eb30eba8720a5`.
- Exact-source bundle: `/tmp/so101-debug-grounded-sam-yolo-benchmark-20260902-ab-v1/source.bundle` and ai-station `/data/work/so101-grounded-sam-yolo-benchmark-source.bundle`; bundle head `1da1286ccd59cfa1deaa6da55c8dbd9b7f62fea4`; bundle SHA-256 on both hosts `086318bd4fc6210d0a1d48f3a9b41899a6e5dd290aca0f900ed84e632e6c8a4d`.
- Bundle command correction: `git bundle create <path> <raw-sha>` was rejected as an empty bundle; `git bundle create <path> HEAD` produced a complete bundle whose listed `HEAD` was the required exact SHA.
- First Linux clone: `/data/work/so101-grounded-sam-yolo-benchmark-ab-v1`; checkout failed when Git LFS smudge attempted to resolve the formal dataset through a file bundle. No formal dataset bytes were opened or accepted. The directory is retained as an invalid-attempt deletion candidate and was not reused, overwritten, or deleted.
- Authoritative Linux checkout: `/data/work/so101-grounded-sam-yolo-benchmark-ab-v1-task10-v2`; cloned with `GIT_LFS_SKIP_SMUDGE=1`; clean immediately after detached checkout at `1da1286ccd59cfa1deaa6da55c8dbd9b7f62fea4`. Post-build status contains only the owned untracked `build-benchmark/`, `install-benchmark/`, and `log-benchmark/` directories.
- Linux build: the first command was rejected before build because `--log-base` was placed after the `build` verb. After correcting it to the top-level colcon position, exact-source `so101_mujoco_support` and `so101_demo_py` both built successfully. Their prefixes are `/data/work/so101-grounded-sam-yolo-benchmark-ab-v1-task10-v2/install-benchmark/{so101_mujoco_support,so101_demo_py}`. The canonical `/data/work/ws_moveit/install` was consumed read-only for lower-level dependencies.
- Linux focused command result: exit `0`; `49 passed`; JUnit `/data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/tests/linux/junit/focused-cli.xml`.
- Linux package command result: pytest collected `1595` tests. By the time the owned process remained in `D/jbd2_log_wait_commit` beyond 15 minutes, it had emitted multiple failures and completed `882` test records. The owned pytest PID was interrupted only after the gate was already invalid. Partial JUnit/test-result: `882 tests, 0 errors, 74 failures, 2 skipped`; `colcon test-result` exit `1`.
- Linux immutable gate evidence: `/data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/tests/linux/package-gate/`; public verifier result `VERIFIED 4`; evidence-index SHA-256 `84e941691fcd2827c08b4a4cccb34ac8a42523d4f866b28ca5dd9baceef4f1e9`.
- ROS domain ID: `NONE`. Gazebo partition: `NONE`. No ROS graph, Gazebo, MoveIt, RViz, model inference, formal archive inspection, or hardware command ran.
- Preserved state: Mac canonical checkout remained at `b5f183353466264e0601d4946a8f3922691af575` with clean status. ai-station canonical checkout remained at `e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4` with its pre-existing untracked `docs/experiments/ai-station-linux-headless-rgbd-four-point-upgrade-experiment-ledger.md`. No benchmark/test process remained after the bounded interrupt; final process matches were only the read-only query itself.
- Retained: both immutable package-gate evidence trees, the exact-source bundle on both hosts, the authoritative isolated Linux checkout and its build/install/log directories, every failed and successful Mac JUnit/build log, the Linux focused JUnit, partial package JUnit, and test-result.
- Archived: none.
- Deletion candidates, not deleted: failed first Linux checkout `/data/work/so101-grounded-sam-yolo-benchmark-ab-v1`; unindexed duplicate Linux paths `/data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/tests/linux/{junit,ros-home}`; superseded Mac package-gate duplicates outside `tests/mac-package-gate/`; existing Task 9 deletion candidates remain unchanged.
- Decision: `ABANDON` this package-gate attempt. The next inline task must resolve the Linux package-test working-directory, dependency/submodule, Python capability, and frozen rasterizer identities before creating a new experiment ID. Task 10 does not enter Task 11.
