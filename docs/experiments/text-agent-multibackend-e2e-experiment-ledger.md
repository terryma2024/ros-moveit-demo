# Text Agent Multibackend E2E Experiment Ledger

```yaml
task_id: so101-text-agent-multibackend-e2e-impl-20260907-01a07c7f
goal: Implement and qualify the approved natural-language multibackend MuJoCo E2E launch.
success_contract: The new launch exits zero only after a valid workflow event trace, dynamic DONE evidence, MuJoCo physical acceptance, Planning Scene acceptance, and owned-resource cleanup; legacy launches remain compatible.
worktree: /private/tmp/so101-text-agent-multibackend-e2e-01a07c7f
branch: codex/text-agent-multibackend-e2e
base_commit: ef9466c602da710ec89d4ca5c36dd0d7596a83c4
current_commit: 870807e15fb60eadbfaa73cb7b6c1c3fd9c12622
evidence_root: /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f
confirmed_conclusions:
  - The macOS source worktree is clean when inspected with its explicit git-dir and work-tree; ordinary Git status is invalid because repository core.worktree points at the shared checkout. OBSERVED before EXP-001.
  - The ai-station checkout is at e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4 with an unrelated untracked experiment ledger that must be preserved. OBSERVED before EXP-001.
disproven_routes:
  - Treating unqualified git status in the linked worktree as a trustworthy source-state check; it reports the shared Git directory as the work tree.
open_hypotheses:
  - The ai-station installed so101_demo_py overlay is stale and must not be used as implementation acceptance evidence.
  - The Grounded SAM base v2 scipy-lock bundle can exercise the backend contract, but no currently registered Grounded SAM bundle has PickPlace qualification evidence.
latest_checkpoint: CP-001
next_experiment: EXP-003
```

## Registered model inputs

```yaml
yolo_seg:
  model_id: plastic-cup-yolo11s-seg-v2
  sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  bytes: 6001316
  macos_path: /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/models/yolo/best.pt
  linux_path: /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/training/full-exp-012/best.pt
  macos_expected_device: mps
  linux_expected_device: cuda
grounded_sam_base_v2:
  model_id: grounding-dino-tiny+sam2.1-hiera-tiny
  manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
  macos_root: /Users/matianyi/Models/so101/grounded-sam-v2-scipy-lock
  linux_root: /data/work/so101-models/grounded-sam-v2-scipy-lock
  qualification_boundary: Available on both hosts and hash-matched; not established as PickPlace-qualified by this task.
grounded_sam_latest_trained_candidate:
  manifest_sha256: 6e822c23d690fc7ededca64647eb1a3d111e2b9219484e541ae334478d4530ce
  linux_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/models/grounded-sam-dino-pinned-base-epoch5-sam-decoder-epoch4-r1
  macos_root: unavailable
  qualification_boundary: PickPlace NO_GO because the frozen COCO100 gate failed; it cannot count toward Task 9 success.
linux_container:
  reference: so101-yolo11n-seg-inference:ros-jazzy-torch2.13.0-cu130-ultralytics8.4.115
  image_id: sha256:fafdb147fab33758b45f8edb39d6ddb231b38ebe59b99dce17f01a0bf35d3a3e
  gpu: NVIDIA GeForce RTX 5080
  driver: 595.84
```

```yaml
experiment_id: EXP-001
status: INVALID
prior_experiment: NONE
hypothesis: The current branch preserves the legacy TextAgent and perception launch contracts before production changes.
prediction: The selected legacy contract tests collect nonzero tests and exit zero in the verified macOS ROS Python environment.
single_variable: Add assertions that freeze already-existing public argument defaults and legacy color-perception ownership.
lifecycle: ISOLATED_STACK
preconditions:
  - No ROS or MuJoCo stack is started for this test-only experiment.
  - The source checkout is clean under the explicit linked-worktree git-dir and work-tree.
  - The test interpreter imports rclpy and so101_demo from the recorded ROS environment and source checkout.
success_criteria:
  - test_text_pick_agent_launch.py, test_perception_pick_place_launch.py, and test_package_identity.py collect nonzero tests and exit zero.
  - New assertions observe existing behavior and do not require production changes.
failure_criteria:
  - A contract assertion fails after successful test collection.
invalid_criteria:
  - rclpy cannot import, no tests collect, or the test command uses an unrecorded interpreter or source tree.
provenance:
  source_commit: 870807e15fb60eadbfaa73cb7b6c1c3fd9c12622
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python3
  ros_domain_id: 0
  gz_partition: not-used-test-only
commands:
  - command: PYTHONNOUSERSITE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_text_pick_agent_launch.py src/so101_demo_py/test/test_perception_pick_place_launch.py src/so101_demo_py/test/test_package_identity.py -q
    exit_code: 0
observed:
  - OBSERVED 2026-09-08: pytest collected and passed 170 tests in 4.55 seconds.
  - OBSERVED 2026-09-08: rclpy imported from /opt/ros/jazzy/rclpy/lib/python3.11/site-packages.
  - OBSERVED 2026-09-08: so101_demo imported from /Users/matianyi/Projects/robot_demo_001/moveit-demo/build/so101_demo_py/so101_demo instead of this isolated worktree.
inferred:
  - The selected test result cannot establish the feature-worktree baseline because Python executed the shared checkout build.
conclusion: INVALID because source provenance did not satisfy the precondition.
evidence:
  - /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-001
decision: REPEAT
next_experiment: EXP-002
```

```yaml
experiment_id: EXP-002
status: VALID
prior_experiment: EXP-001
hypothesis: The current branch preserves the legacy TextAgent and perception launch contracts when Python resolves so101_demo through an explicit worktree package mapping.
prediction: The same 170 or more selected tests collect and exit zero, and so101_demo.__file__ resolves through the worktree package mapping.
single_variable: Replace the shared-checkout build import with an evidence-root Python package symlink that maps so101_demo to this worktree's src/so101_demo_py/src.
lifecycle: ISOLATED_STACK
preconditions:
  - No ROS or MuJoCo stack is started for this test-only experiment.
  - The source checkout is clean except for this task ledger.
  - PYTHONPATH starts with /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/pythonpath.
success_criteria:
  - so101_demo.__file__ resolves inside /private/tmp/so101-text-agent-multibackend-e2e-01a07c7f/src/so101_demo_py/src.
  - The three selected test files collect nonzero tests and exit zero.
failure_criteria:
  - A contract assertion fails after successful test collection from the correct source tree.
invalid_criteria:
  - rclpy cannot import, no tests collect, or either Python module resolves outside the recorded roots.
provenance:
  source_commit: 870807e15fb60eadbfaa73cb7b6c1c3fd9c12622
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python3
  ros_domain_id: 0
  gz_partition: not-used-test-only
commands:
  - command: PYTHONPATH=/tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/pythonpath PYTHONNOUSERSITE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_text_pick_agent_launch.py src/so101_demo_py/test/test_perception_pick_place_launch.py src/so101_demo_py/test/test_package_identity.py -q
    exit_code: 0
observed:
  - OBSERVED 2026-09-08: experiment planned before creating the package mapping and rerunning tests.
  - OBSERVED 2026-09-08: so101_demo resolved to /private/tmp/so101-text-agent-multibackend-e2e-01a07c7f/src/so101_demo_py/src/__init__.py.
  - OBSERVED 2026-09-08: rclpy resolved to /Users/matianyi/ros2_jazzy/src/ros2/rclpy/rclpy/rclpy/__init__.py.
  - OBSERVED 2026-09-08: 170 selected tests passed in 3.36 seconds with a JUnit record.
inferred:
  - The feature branch starts from a valid legacy launch contract baseline.
conclusion: VALID baseline; existing exact argument-set and process-order tests already catch addition of perception_backend or replacement of rgbd_cup_pose, so no redundant characterization assertion was added.
evidence:
  - /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-002
decision: KEEP
next_experiment: EXP-003
```

```yaml
checkpoint_id: CP-001
last_valid_experiment: EXP-002
current_hypothesis: Shared perception construction can be extracted without changing either legacy launch contract.
working_tree_status: docs/experiments/text-agent-multibackend-e2e-experiment-ledger.md is new; no production files changed.
owned_processes: NONE
preserved_processes: ai-station tmux sessions codex, microduck-policy-queue, and so101-exp079-linux-r3; all unknown or unrelated processes.
confirmed_conclusions:
  - Explicit linked-worktree Git inspection is required for every source-state judgment.
  - ai-station source and install provenance do not match this feature branch.
  - EXP-002 established a 170-test legacy contract baseline from the isolated worktree source.
disproven_routes:
  - Reusing the current ai-station installed prefix as evidence for this feature branch.
  - Using the shared-checkout Python build path for isolated-worktree tests; EXP-001 is INVALID.
open_risks:
  - The linked worktree has an uninitialized mujoco_ros2_control submodule and must rely on the verified underlay until initialized.
  - Grounded SAM has no currently registered PickPlace-qualified bundle; Task 9 formal success remains blocked by model qualification.
next_command: Write the Task 2 failing shared-perception-construction test and run it to RED.
```
