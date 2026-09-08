# Text Agent Multibackend E2E Experiment Ledger

```yaml
task_id: so101-text-agent-multibackend-e2e-impl-20260907-01a07c7f
goal: Implement and qualify the approved natural-language multibackend MuJoCo E2E launch.
success_contract: The new launch exits zero only after a valid workflow event trace, dynamic DONE evidence, MuJoCo physical acceptance, Planning Scene acceptance, and owned-resource cleanup; legacy launches remain compatible.
worktree: /private/tmp/so101-text-agent-multibackend-e2e-01a07c7f
branch: codex/text-agent-multibackend-e2e
base_commit: ef9466c602da710ec89d4ca5c36dd0d7596a83c4
current_commit: 8a1cbdeda25f94ed5eef7af999d892536b2e28fa
evidence_root: /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f
confirmed_conclusions:
  - The macOS source worktree is clean when inspected with its explicit git-dir and work-tree; ordinary Git status is invalid because repository core.worktree points at the shared checkout. OBSERVED before EXP-001.
  - The ai-station checkout is at e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4 with an unrelated untracked experiment ledger that must be preserved. OBSERVED before EXP-001.
disproven_routes:
  - Treating unqualified git status in the linked worktree as a trustworthy source-state check; it reports the shared Git directory as the work tree.
open_hypotheses:
  - The ai-station installed so101_demo_py overlay is stale and must not be used as implementation acceptance evidence.
  - The previously PickPlace-qualified Grounded SAM production bundle must be replayed through the new Text-Agent E2E entry before its two current matrix cells can pass.
latest_checkpoint: CP-014
next_experiment: Register fresh current-host paths for the pinned Grounded SAM production bundle, then run the new E2E four-point batches.
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
grounded_sam_pickplace_qualified:
  model_id: grounded-sam-dino-nonpenetrating-epoch1-sam-decoder-epoch4-r1
  manifest_sha256: b55bb601d311407df8f9f25d9da18649f6bd78ac1299148bde0d07f7cfdfed05
  threshold_lock_sha256: b02e3be2814d03b954bdcb73b2f79f8b91d1227c6476fcc82695cabb91f50278
  dino_weight_sha256: bfa141974163338b7333c9d9174609e1b29b4f3fd43eaaf5b1017d14abe7da4b
  sam_weight_sha256: 0d252822a8c62636467368fc39d2239d5303de482f04e8bda801e71aff9c6893
  private_hugging_face_repository: zjumty/so101-grounded-sam-cup-pickplace
  pinned_revision: 52b8334358e5ff11f94f10f7c14b1697ef44d964
  linux_source_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/models/grounded-sam-dino-nonpenetrating-epoch1-sam-decoder-epoch4-r1
  prior_qualification: Linux CUDA, current Mac MPS, and mac-mini MPS each passed four preset MuJoCo PickPlace points 4/4 through the existing perception entry.
  current_e2e_boundary: The new Text-Agent E2E entry has not run this bundle; fresh current-host roots and manifest readback are still required before those matrix cells can pass.
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

```yaml
experiment_id: EXP-003
status: VALID
prior_experiment: EXP-002
hypothesis: Shared perception declarations, validation, and action construction can be extracted without changing either legacy launch contract.
prediction: Each new helper test first fails for the missing interface, then both legacy launch test files pass after the extraction.
single_variable: Move perception-only launch behavior from launch_composition.py into runtime/perception_launch.py while retaining the legacy caller's backend default and process order.
lifecycle: ISOLATED_STACK
preconditions:
  - No ROS or MuJoCo stack is started for this test-only experiment.
  - PYTHONPATH resolves so101_demo through the isolated worktree package mapping established by EXP-002.
  - The Task 1 legacy contract baseline is 170 passing selected tests.
success_criteria:
  - New tests cover caller-owned defaults, full parsing, and color, YOLO host, and Grounded SAM action construction.
  - test_perception_pick_place_launch.py and test_text_pick_agent_launch.py collect nonzero tests and exit zero.
  - Legacy argument defaults, action arguments, and process order remain unchanged.
failure_criteria:
  - Any legacy launch test fails after successful collection from the correct source tree.
invalid_criteria:
  - rclpy cannot import, no tests collect, or so101_demo resolves outside the isolated worktree mapping.
provenance:
  source_commit: 79eeb7922ebf86c2162a333930e5639506e2a45d
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python3
  ros_domain_id: 0
  gz_partition: not-used-test-only
commands:
  - command: PYTHONPATH=/tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/pythonpath PYTHONNOUSERSITE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_perception_pick_place_launch.py src/so101_demo_py/test/test_text_pick_agent_launch.py -q
    exit_code: 0
observed:
  - OBSERVED 2026-09-08: the declaration-helper test first failed because so101_demo.runtime.perception_launch did not exist.
  - OBSERVED 2026-09-08: parser and builder tests then failed in sequence for the missing parser, missing color builder, unsupported YOLO builder, and unsupported Grounded SAM builder.
  - OBSERVED 2026-09-08: the first full legacy regression had seven failures because existing tests patch launch_composition.platform.system as a compatibility seam.
  - OBSERVED 2026-09-08: retaining the platform module import in launch_composition.py restored that seam without duplicating parsing logic.
  - OBSERVED 2026-09-08: 172 selected tests passed in 3.19 seconds after the extraction.
inferred:
  - The shared module preserves the legacy launch surface while making backend construction reusable by the new E2E launch.
conclusion: VALID; shared perception construction is ready for the workflow runner and the legacy launch contracts remain green.
evidence:
  - /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-003
decision: KEEP
next_experiment: EXP-004
```

```yaml
checkpoint_id: CP-002
last_valid_experiment: EXP-003
current_hypothesis: A strict workflow event protocol can reject malformed, duplicate, out-of-order, and cross-workflow evidence before orchestration is added.
working_tree_status: Task 2 changes are limited to the shared perception module, launch composition refactor, focused tests, plan progress, and this ledger.
owned_processes: NONE
preserved_processes: ai-station tmux sessions codex, microduck-policy-queue, and so101-exp079-linux-r3; all unknown or unrelated processes.
confirmed_conclusions:
  - Shared perception declarations retain caller-owned backend defaults.
  - Shared parsing and action construction preserve legacy color, YOLO host, YOLO Docker, and Grounded SAM behavior.
  - EXP-003 established a 172-test regression pass from the isolated worktree source.
disproven_routes:
  - Removing the launch_composition.platform import; existing compatibility tests require that patch seam.
open_risks:
  - The linked worktree has an uninitialized mujoco_ros2_control submodule and must rely on the verified underlay until initialized.
  - Grounded SAM has no currently registered PickPlace-qualified bundle; Task 9 formal success remains blocked by model qualification.
next_command: Run Task 2 static and diff checks, commit the extraction, then write the Task 3 workflow-event protocol test to RED.
```

```yaml
experiment_id: EXP-004
status: VALID
prior_experiment: EXP-003
hypothesis: A strict per-child decoder and global phase state can reject malformed or unauthorised workflow output without accepting ordinary logs as control evidence.
prediction: Focused tests first fail at each missing protocol boundary, then pass for byte-split UTF-8, exact schema, component sequence, payload, failure-code, timestamp, identity, and phase validation.
single_variable: Add runtime/workflow_events.py and its focused unit tests without connecting it to production processes yet.
lifecycle: ISOLATED_STACK
preconditions:
  - No ROS or MuJoCo stack is started for this protocol-only experiment.
  - PYTHONPATH resolves so101_demo through the isolated worktree package mapping established by EXP-002.
  - Task 2 is committed at 8f191ad0be933ea877fc59f2936cf4bf6754f32b.
success_criteria:
  - Arbitrarily split UTF-8 event lines decode exactly once and ordinary log lines never create events.
  - Exact fields, types, workflow, component, per-component sequence, five-second wall-clock window, status/failure pairing, payload allowlists, and fixed failure codes fail closed.
  - Model backends require TARGET_SELECTED, color_geometry may skip it, and only active-stage failures return FAIL.
  - Cross-stage request, session, and reset identity mismatches are rejected.
failure_criteria:
  - Any malformed record, duplicate, jump, stale record, unknown failure code, or identity mismatch is accepted.
invalid_criteria:
  - No tests collect or so101_demo resolves outside the isolated worktree mapping.
provenance:
  source_commit: 8f191ad0be933ea877fc59f2936cf4bf6754f32b
  install_overlay: not-used-protocol-only
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python3
  ros_domain_id: not-used
  gz_partition: not-used-test-only
commands:
  - command: PYTHONPATH=/tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/pythonpath PYTHONNOUSERSITE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_workflow_events.py -q --junitxml=/tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-004/pytest-workflow-events.xml
    exit_code: 0
observed:
  - OBSERVED 2026-09-08: the first split-line test failed at collection because workflow_events.py did not exist.
  - OBSERVED 2026-09-08: later RED runs separately exposed the missing EOF finalizer, strict schema checks, EventEmitter, failure transitions, and identity correlation.
  - OBSERVED 2026-09-08: an unrelated verification command without the ROS underlay failed to import launch; it was excluded from protocol evidence and rerun correctly for the Task 2 gate.
  - OBSERVED 2026-09-08: the final protocol run collected and passed 66 tests in 0.03 seconds and wrote JUnit evidence.
  - OBSERVED 2026-09-08: Python byte compilation and git diff --check passed.
inferred:
  - The protocol module now supplies a fail-closed boundary suitable for Task 7 process supervision while remaining independent of ROS actions.
conclusion: VALID; event transport, schema, fixed failure vocabulary, phase transitions, and identity correlation are ready to connect to TextAgent and dynamic runtime.
evidence:
  - /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-004
decision: KEEP
next_experiment: EXP-005
```

```yaml
checkpoint_id: CP-003
last_valid_experiment: EXP-004
current_hypothesis: TextAgent and dynamic runtime can emit protocol milestones at their existing authorization, subscription-ready, terminal-success, and terminal-failure boundaries without changing disabled-mode output.
working_tree_status: Task 3 changes are limited to workflow_events.py, test_workflow_events.py, plan progress, and this ledger.
owned_processes: NONE
preserved_processes: ai-station tmux sessions codex, microduck-policy-queue, and so101-exp079-linux-r3; all unknown or unrelated processes.
confirmed_conclusions:
  - EventDecoder handles arbitrary byte chunks and keeps an independent sequence per allowed component.
  - EventEmitter owns status and sequence and flushes every emitted record.
  - WorkflowState enforces the backend-specific success path and active-stage failure boundaries.
  - EXP-004 established a 66-test protocol pass from the isolated worktree source.
disproven_routes:
  - Accepting planner or model text as an arbitrary failure code.
  - Treating ordinary status text or an event-like malformed prefix as a workflow transition.
open_risks:
  - The linked worktree has an uninitialized mujoco_ros2_control submodule and must rely on the verified underlay until initialized.
  - Grounded SAM has no currently registered PickPlace-qualified bundle; Task 9 formal success remains blocked by model qualification.
next_command: Commit Task 3, then add the Task 4 TextAgent pre-dispatch event ordering test and run it to RED.
```

```yaml
experiment_id: EXP-005
status: VALID
prior_experiment: EXP-004
hypothesis: TextAgent and the dynamic runtime can emit correlated workflow milestones at their existing authorization and execution boundaries without changing disabled-mode behavior.
prediction: Focused tests first fail at missing event interfaces and boundaries, then all selected agent, executor, runtime, CLI, provenance, and protocol tests pass with exact legacy output preserved.
single_variable: Connect the Task 3 event protocol to TextAgent, DynamicCupPickPlaceExecutor, run_dynamic_execute, the text CLI, and final provenance.
lifecycle: ISOLATED_STACK
preconditions:
  - No ROS graph, MuJoCo process, or perception process is started; all execution dependencies are injected fakes.
  - PYTHONPATH resolves so101_demo through the isolated worktree package mapping established by EXP-002.
  - Task 3 is committed at ea850f48c13fea0d32b2c44ec1b755c55038386d.
success_criteria:
  - DISPATCH_PREVIEW occurs only after every static authorization and request-identity gate and immediately before executor dispatch.
  - RUNTIME_STARTED and RUNTIME_READY preserve workflow/request identity, and exactly one runtime terminal event is emitted.
  - Runtime manifests and text-agent provenance contain correlated identity and actual planner provider/model/fallback fields only when enabled.
  - Disabled-mode stdout, runtime options, manifest shape, and exit behavior remain unchanged.
failure_criteria:
  - A rejected request creates a runtime side effect or emits DISPATCH_PREVIEW.
  - Enabled status output contaminates command stdout, a runtime terminal is duplicated, or legacy exact-shape assertions fail.
invalid_criteria:
  - No tests collect or so101_demo resolves outside the isolated worktree mapping.
provenance:
  source_commit: ea850f48c13fea0d32b2c44ec1b755c55038386d
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python3
  ros_domain_id: not-used-injected-tests
  gz_partition: not-used-injected-tests
commands:
  - command: PYTHONPATH=/tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/pythonpath PYTHONNOUSERSITE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_text_agent.py src/so101_demo_py/test/test_text_agent_final_review.py src/so101_demo_py/test/test_planner_chain.py src/so101_demo_py/test/test_pick_place_executor_adapter.py src/so101_demo_py/test/test_dynamic_scene_sync.py src/so101_demo_py/test/test_dynamic_execute.py src/so101_demo_py/test/test_text_pick_agent_cli.py src/so101_demo_py/test/test_text_agent_execution_provenance.py src/so101_demo_py/test/test_workflow_events.py -q --junitxml=/tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-005/pytest-agent-runtime-events.xml
    exit_code: 0
observed:
  - OBSERVED 2026-09-08: the first TextAgent RED rejected event_emitter at construction; later RED runs exposed missing failure events, DynamicRuntimeContext fields, runtime emitter support, runtime identity propagation, and paired CLI arguments.
  - OBSERVED 2026-09-08: the first full CLI run exposed a missing sys import; the next run exposed three legacy monkeypatched TextAgent constructor signatures, which were preserved by omitting the optional keyword when disabled.
  - OBSERVED 2026-09-08: later RED tests exposed missing RosDynamicMujocoExecution identity fields, cross-bound emitter acceptance, and an executor path without a fallback terminal event.
  - OBSERVED 2026-09-08: the final selected run collected and passed 277 tests in 1.903 seconds with zero failures, errors, or skips and wrote JUnit evidence.
  - OBSERVED 2026-09-08: Python byte compilation and git diff --check passed after the final run.
inferred:
  - The agent and dynamic runtime now expose strict orchestration milestones while their disabled public contracts remain compatible.
conclusion: VALID; Task 4 identity, ordering, terminal ownership, output routing, and provenance requirements are ready for perception integration.
evidence:
  - /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-005
decision: KEEP
next_experiment: EXP-006
```

```yaml
checkpoint_id: CP-004
last_valid_experiment: EXP-005
current_hypothesis: Color and model perception can emit readiness, selection, publication, and fixed failures at their real gate boundaries without changing legacy output or publication behavior.
working_tree_status: Task 4 changes are limited to agent, executor, dynamic runtime, CLI, provenance, focused tests, plan progress, and this ledger.
owned_processes: NONE
preserved_processes: ai-station tmux sessions codex, microduck-policy-queue, and so101-exp079-linux-r3; all unknown or unrelated processes.
confirmed_conclusions:
  - Rejected requests do not emit DISPATCH_PREVIEW and do not reach the executor or runtime.
  - Runtime event identity is paired and cross-bound emitters fail closed.
  - Enabled event mode separates status from command output; disabled mode preserves exact legacy output and option shapes.
  - EXP-005 established a 277-test selected regression pass from the isolated worktree source.
disproven_routes:
  - Always passing optional constructor keywords to legacy test doubles.
  - Allowing the executor and runtime layers to emit duplicate terminal events.
open_risks:
  - The linked worktree has an uninitialized mujoco_ros2_control submodule and must rely on the verified underlay until initialized.
  - Grounded SAM has no currently registered PickPlace-qualified bundle; Task 9 formal success remains blocked by model qualification.
next_command: Commit Task 4, then add the Task 5 perception workflow event tests and run them to RED.
```

```yaml
experiment_id: EXP-006
status: VALID
prior_experiment: EXP-005
hypothesis: Color and model perception can emit milestones at real readiness, selection, evidence, and publication boundaries without changing disabled-mode behavior.
prediction: New tests first fail for missing emitter interfaces, paired CLI arguments, and Docker buffering, then the selected perception and legacy launch suites pass.
single_variable: Add the perception component's workflow-event integration to the existing color and model-backed processes.
lifecycle: ISOLATED_STACK
preconditions:
  - No ROS graph, MuJoCo process, Docker container, or model is started; detection, localization, publishers, and ROS boundaries use injected fakes.
  - PYTHONPATH resolves so101_demo through the isolated worktree package mapping established by EXP-002.
  - Task 4 is committed at 65ae695bef22d18144065dc4bc81c70b3683544b.
success_criteria:
  - Color emits READY only after a fresh aligned frame passes its gate and emits PUBLISHED exactly once after evidence and the first successful pose publication.
  - Model perception emits READY after output discovery and TF gates, SELECTED after unique TargetSelector success, and PUBLISHED after confirmed pose publication and final evidence.
  - Zero or multiple targets, TF, depth, model, evidence, output, and cleanup failures use the fixed PERCEPTION_FAILED vocabulary and never falsely publish.
  - Event arguments are paired and safe, enabled status goes to stderr, and Docker uses the same workflow with unbuffered Python output.
failure_criteria:
  - Any event precedes its real gate, a failed request publishes a pose, a second color frame advances the workflow, or legacy launch/CLI contracts regress.
invalid_criteria:
  - No tests collect, so101_demo resolves outside the isolated worktree mapping, or ROS logging writes outside the registered evidence root.
provenance:
  source_commit: 65ae695bef22d18144065dc4bc81c70b3683544b
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python3
  ros_domain_id: not-used-injected-tests
  gz_partition: not-used-injected-tests
commands:
  - command: PYTHONPATH=/tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/pythonpath PYTHONNOUSERSITE=1 ROS_HOME=/tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/ros-home ROS_LOG_DIR=/tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/ros-logs /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_perception_workflow_events.py src/so101_demo_py/test/test_rgbd_cup_pose.py src/so101_demo_py/test/test_rgbd_object_pose.py src/so101_demo_py/test/test_perception_pick_place_launch.py src/so101_demo_py/test/test_text_pick_agent_launch.py src/so101_demo_py/test/test_workflow_events.py -q --junitxml=/tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-006/pytest-perception-events.xml
    exit_code: 0
observed:
  - OBSERVED 2026-09-08: initial RED tests failed because FirstValidEvidencePublisher and detect_once rejected event_emitter, both CLIs rejected the new arguments as unknown, and Docker omitted PYTHONUNBUFFERED.
  - OBSERVED 2026-09-08: the first combined RED also attempted ROS logging without the registered ROS_HOME and was INVALID for that one launch assertion; all later runs set both ROS_HOME and ROS_LOG_DIR inside the task root.
  - OBSERVED 2026-09-08: a GREEN test was initially inserted before the prior profiling test's remaining assertions; moving those assertions back to their original test removed the test-only failure.
  - OBSERVED 2026-09-08: the final selected run collected and passed 344 tests in 3.47 seconds and wrote JUnit evidence with zero failures, errors, or skips.
  - OBSERVED 2026-09-08: Python byte compilation and git diff --check passed.
inferred:
  - Both perception families now expose the strict event stream while retaining the old process outputs and launch composition when workflow events are disabled.
conclusion: VALID; Task 5 perception readiness, selection, publication, fixed failure, CLI routing, and Docker forwarding are ready for the independent acceptance validator.
evidence:
  - /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-006
decision: KEEP
next_experiment: EXP-007
```

```yaml
checkpoint_id: CP-005
last_valid_experiment: EXP-006
current_hypothesis: A pure acceptance policy plus a read-only ROS adapter can reject incomplete, stale, cross-identity, physically invalid, or Planning Scene-invalid evidence before orchestration is added.
working_tree_status: Task 5 changes are limited to perception application callbacks, two CLIs, two ROS nodes, Docker environment construction, focused tests, plan progress, and this ledger.
owned_processes: NONE
preserved_processes: ai-station tmux sessions codex, microduck-policy-queue, and so101-exp079-linux-r3; all unknown or unrelated processes.
confirmed_conclusions:
  - Color emits one workflow publication milestone while retaining later diagnostic topic publication.
  - Model selection and evidence failures cannot produce a CUP_POSE_PUBLISHED event.
  - Enabled event transport uses stdout with wall-clock timestamps while ordinary process status moves to stderr.
  - EXP-006 established a 344-test perception and legacy launch regression pass from the isolated worktree source.
disproven_routes:
  - Emitting model readiness before subscriber and TF discovery complete.
  - Treating a successful topic publish as sufficient before the final result evidence is rewritten.
open_risks:
  - The linked worktree has an uninitialized mujoco_ros2_control submodule and must rely on the verified underlay until initialized.
  - Grounded SAM has no currently registered PickPlace-qualified bundle; Task 9 formal success remains blocked by model qualification.
next_command: Commit Task 5, then add the Task 6 missing-evidence acceptance test and run it to RED.
```

```yaml
experiment_id: EXP-007
status: VALID
prior_experiment: EXP-006
hypothesis: A ROS-free acceptance policy and a read-only ROS adapter can reject incomplete, cross-identity, physically invalid, or Planning Scene-invalid evidence after runtime completion.
prediction: The missing-evidence test first fails because the acceptance module is absent, then complete correlated evidence passes while each individually damaged fact is rejected without an unhandled exception.
single_variable: Add final E2E validation and readback without changing runtime control flow or publishing synthetic truth.
lifecycle: ISOLATED_STACK
preconditions:
  - No ROS graph or MuJoCo process is started; readback conversion and client boundaries use injected immutable fakes.
  - PYTHONPATH resolves so101_demo through the isolated worktree package mapping established by EXP-002.
  - Task 5 is committed at 8a1cbdeda25f94ed5eef7af999d892536b2e28fa.
success_criteria:
  - Empty and malformed documents return serializable rejection reports.
  - Workflow/request/session/reset, DONE and exact state trace, controller feedback, lift/transport, release sequence, physical stability, contact, world membership, and pose/time correlation are all required.
  - CALIBRATION_REQUIRED policies fail, and policy hashes and tolerances are sourced from the same dynamic policy used by execution.
  - Readback uses only the MuJoCo evidence observer and GetPlanningScene, with finite timeouts and no mutating control interfaces.
  - Acceptance artifacts are atomically written before E2E_ACCEPTED; invalid readback emits E2E_REJECTED and returns one.
failure_criteria:
  - Missing facts raise instead of rejecting, a single final pose can pass without the state trace, or MuJoCo truth is injected into runtime inputs.
invalid_criteria:
  - No tests collect or so101_demo resolves outside the isolated worktree mapping.
provenance:
  source_commit: 8a1cbdeda25f94ed5eef7af999d892536b2e28fa
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python3
  ros_domain_id: not-used-injected-tests
  gz_partition: not-used-injected-tests
commands:
  - command: PYTHONPATH=/tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/pythonpath PYTHONNOUSERSITE=1 ROS_HOME=/tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/ros-home ROS_LOG_DIR=/tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/ros-logs /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_e2e_acceptance.py src/so101_demo_py/test/test_dynamic_execute.py src/so101_demo_py/test/test_dynamic_scene_sync.py src/so101_demo_py/test/test_package_identity.py -q --junitxml=/tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-007/pytest-e2e-acceptance.xml
    exit_code: 0
observed:
  - OBSERVED 2026-09-08: all 14 initial acceptance tests failed at RED because application/e2e_acceptance.py did not exist.
  - OBSERVED 2026-09-08: the first GREEN run exposed a shared-list alias in the test fixture, not validator behavior; copying the Planning Scene pose made the single-variable pose mismatch test valid.
  - OBSERVED 2026-09-08: a test run without the final repository install overlay collected an incompatible stale mujoco_ros2_control message package and was INVALID; the recorded final command restored the verified overlay order.
  - OBSERVED 2026-09-08: the final selected run collected and passed 69 tests in 1.17 seconds and wrote JUnit evidence with zero failures, errors, or skips.
  - OBSERVED 2026-09-08: Python byte compilation, line-length inspection of changed files, and git diff --check passed.
inferred:
  - The validator can now be launched after RUNTIME_COMPLETED while the stack remains alive, and its result depends on both independent truth sources plus the complete dynamic trace.
conclusion: VALID; Task 6 pure validation, read-only collection, atomic artifacts, event terminal, and console entry point are ready for supervisor integration.
evidence:
  - /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-007
decision: KEEP
next_experiment: EXP-008
```

```yaml
checkpoint_id: CP-006
last_valid_experiment: EXP-007
current_hypothesis: A new launch supervisor can enforce the event phase machine, start perception only on RUNTIME_READY, run acceptance only after RUNTIME_COMPLETED, preserve the primary failure, and clean only owned resources.
working_tree_status: Task 6 changes are limited to the pure validator, readback adapter, validator CLI, shared terminal constants, setup entry point, focused tests, plan progress, and this ledger.
owned_processes: NONE
preserved_processes: ai-station tmux sessions codex, microduck-policy-queue, and so101-exp079-linux-r3; all unknown or unrelated processes.
confirmed_conclusions:
  - Acceptance rejects malformed evidence without KeyError and serializes every result.
  - Exact success trace and physical facts are required in addition to DONE.
  - Planning Scene cup pose is reconstructed from the canonical thirteenth bottom primitive and compared with fresh MuJoCo evidence.
  - EXP-007 established a 69-test acceptance and dynamic regression pass from the isolated worktree source.
disproven_routes:
  - Trusting dynamic runtime success or one final pose as complete E2E acceptance.
  - Calling mutation services or action clients from the final readback process.
open_risks:
  - The linked worktree has an uninitialized mujoco_ros2_control submodule and must rely on the verified underlay until initialized.
  - Grounded SAM has no currently registered PickPlace-qualified bundle; Task 9 formal success remains blocked by model qualification.
next_command: Commit Task 6, then add the Task 7 launch supervisor contract test and run it to RED.
```

```yaml
experiment_id: EXP-008
status: VALID
prior_experiment: EXP-007
hypothesis: A supervisor built around the strict event state machine can compose the new launch without changing either legacy launch contract.
prediction: Invalid authorization, instruction, sensor, model, or evidence inputs create no stack; valid events start each business child once, preserve the first failure, and write the final result only after owned cleanup.
single_variable: Add the supervised E2E launch graph and owned-resource policy on top of the previously validated producers and acceptance reader.
lifecycle: ISOLATED_STACK
preconditions:
  - No ROS graph, simulator, Docker container, or model inference is started; launch actions and child event streams are inspected with deterministic fakes.
  - PYTHONPATH resolves so101_demo through the isolated worktree package mapping established by EXP-002.
  - Task 6 is committed at 17a8da72c20935bf5d9b4f1dea2f5e5e7799de75.
success_criteria:
  - The E2E wrapper remains thin and exposes the exact agent and perception parameter contract with yolo_seg as its backend default.
  - All preflight gates run before evidence directories or MuJoCo actions are created.
  - STACK_READY starts only Text Agent; RUNTIME_READY starts one perception child; RUNTIME_COMPLETED starts one validator; only E2E_ACCEPTED begins successful cleanup.
  - Each child has its own strict decoder, stale timer generations are inert, required processes fail even on early zero exit, and nonterminal nonzero exits use CHILD_EXITED_WITHOUT_TERMINAL_EVENT.
  - Event and result writes use fsync plus atomic replacement, and the final success record is absent until every registered owned process has exited.
  - Docker runs created for this workflow carry a unique name, workflow label, and CID file; cleanup targets only that registered name.
failure_criteria:
  - Ordinary stack stdout drives workflow state, an invalid launch creates resources, a second error replaces the primary failure, or machine acceptance is written before cleanup completes.
invalid_criteria:
  - No tests collect or so101_demo resolves outside the isolated worktree mapping.
provenance:
  source_commit: 17a8da72c20935bf5d9b4f1dea2f5e5e7799de75
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python3
  ros_domain_id: not-used-launch-action-tests
  gz_partition: not-used-launch-action-tests
commands:
  - command: PYTHONPATH=/tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/pythonpath PYTHONNOUSERSITE=1 ROS_HOME=/tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/ros-home ROS_LOG_DIR=/tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/ros-logs /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_text_pick_agent_e2e_launch.py src/so101_demo_py/test/test_workflow_events.py src/so101_demo_py/test/test_text_pick_agent_launch.py src/so101_demo_py/test/test_perception_pick_place_launch.py -q --junitxml=/tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/task7-contract.xml
    exit_code: 0
observed:
  - OBSERVED 2026-09-08: the dedicated contract test collected 12 RED failures because the E2E builder and supervisor did not exist.
  - OBSERVED 2026-09-08: the first GREEN iteration exposed that stack processes must have exit handlers without event-stream handlers; business children now exclusively own event decoders.
  - OBSERVED 2026-09-08: the installed development scene is a symlink, so the E2E default is resolved to its ordinary source file while explicit symlink scene inputs remain rejected.
  - OBSERVED 2026-09-08: the selected combined run collected and passed 255 protocol, E2E launch, and legacy launch tests in 3.35 seconds with zero failures, errors, or skips.
  - OBSERVED 2026-09-08: Python byte compilation and git diff --check passed.
inferred:
  - The new launch graph is structurally isolated from both legacy business launches and can proceed to real LaunchService process-boundary tests.
conclusion: VALID; Task 7 launch composition, state-driven scheduling, primary-failure retention, atomic evidence, timeout generation, and scoped ownership are ready for installed and process-boundary verification.
evidence:
  - /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/task7-contract.xml
decision: KEEP
next_experiment: EXP-009
```

```yaml
checkpoint_id: CP-007
last_valid_experiment: EXP-008
current_hypothesis: The installed package and a real LaunchService can preserve event bytes through ProcessIO/ProcessExited races and expose reliable zero/nonzero top-level exit semantics.
working_tree_status: Task 7 changes are limited to the new thin launch, E2E supervisor composition, workflow-scoped Docker ownership metadata, focused tests, plan progress, and this ledger.
owned_processes: NONE
preserved_processes: ai-station tmux sessions codex, microduck-policy-queue, and so101-exp079-linux-r3; all unknown or unrelated processes.
confirmed_conclusions:
  - Business actions are not part of the initial action set and can only start from validated state-machine effects.
  - Stack stdout cannot masquerade as a workflow event because only the three business children have OnProcessIO handlers.
  - Successful top-level evidence separates machine acceptance from owned-process cleanup completion.
  - EXP-008 established a 255-test protocol, E2E launch, and legacy launch regression pass from the isolated worktree source.
disproven_routes:
  - Registering an event decoder for every stack process.
  - Treating a shutdown request as proof that owned processes and containers have exited.
open_risks:
  - The linked worktree has an uninitialized mujoco_ros2_control submodule and must rely on the verified underlay until initialized.
  - Grounded SAM has no currently registered PickPlace-qualified bundle; Task 9 formal success remains blocked by model qualification.
next_command: Commit Task 7, then add Task 8 installed-launch and real LaunchService process-boundary tests.
```

```yaml
experiment_id: EXP-009
status: VALID
prior_experiment: EXP-008
hypothesis: Real LaunchService children and a fresh isolated install can preserve the supervisor contract across stdout chunks, EOF, process exit, shutdown signals, and package discovery.
prediction: Accepted plus complete cleanup returns zero; child failure, required early exit, truncated event, out-of-order events, evidence failure, or cleanup escalation returns nonzero with the first failure retained.
single_variable: Replace in-memory launch events with real subprocess and installed-package boundaries without starting the robot stack.
lifecycle: ISOLATED_STACK
preconditions:
  - Fake Python children are owned by each test LaunchService and no ROS graph, MuJoCo process, model inference, or Docker container is started.
  - The candidate overlay is rooted at /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-009/install.
  - so101_mujoco_support is built into the same isolated install base; mujoco_vendor remains the previously verified underlay dependency.
success_criteria:
  - Seven real LaunchService cases prove zero/nonzero exit behavior, byte-split event delivery, EOF rejection, first-error retention, strict global ordering, and bounded signal escalation.
  - The installed launcher set adds only so101_mujoco_text_pick_agent_e2e.launch.py and the installed executable set includes text_pick_agent and e2e_acceptance.
  - ros2 pkg, ros2 launch --show-args, rclpy, and so101_demo resolve through the selected candidate overlay.
  - The full ordinary test directory passes after the pinned submodule is initialized; benchmark_test is not collected.
failure_criteria:
  - LaunchService returns zero on any rejected path, source imports replace installed inspection, or package tests run against an uninitialized submodule and are reported as passing.
invalid_criteria:
  - A fake child from another test remains alive or the installed package prefix does not resolve to EXP-009.
provenance:
  source_commit: f3ea8023128eb35b1e88c567bb4437bb9ee9128d
  install_overlay: /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-009/install
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python3
  so101_demo_module: /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-009/build/so101_demo_py/so101_demo/__init__.py
  rclpy_module: /opt/ros/jazzy/rclpy/lib/python3.11/site-packages/rclpy/__init__.py
  ros_domain_id: not-used-fake-process-tests
  gz_partition: not-used-fake-process-tests
commands:
  - command: python -m pytest -p no:cacheprovider src/so101_demo_py/test/test_text_pick_agent_e2e_process.py -q --junitxml=/tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-009/process.xml
    exit_code: 0
  - command: colcon --log-base /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-009/colcon-log build --build-base /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-009/build --install-base /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-009/install --packages-select so101_demo_py --symlink-install
    exit_code: 0
  - command: colcon --log-base /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-009/colcon-log-support build --build-base /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-009/build --install-base /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-009/install --packages-select so101_mujoco_support --symlink-install
    exit_code: 0
  - command: ros2 launch so101_demo_py so101_mujoco_text_pick_agent_e2e.launch.py --show-args
    exit_code: 0
  - command: python -m pytest -p no:cacheprovider src/so101_demo_py/test/test_package_identity.py src/so101_demo_py/test/test_installed_provenance.py -q --junitxml=/tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-009/installed-contract.xml
    exit_code: 0
  - command: python -m pytest -p no:cacheprovider src/so101_demo_py/test -q --junitxml=/tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-009/so101-demo-py.xml
    exit_code: 0
observed:
  - OBSERVED 2026-09-08: all seven real LaunchService tests passed in 8.47 seconds, including immediate valid failure plus exit, truncated EOF, required zero exit, accepted cleanup, signal escalation, evidence failure, and cross-child disorder.
  - OBSERVED 2026-09-08: the first installed contract run had six passes and one provenance failure because so101_mujoco_support still resolved to the old project overlay; building that dependency into EXP-009 made all seven installed tests pass in 3.39 seconds.
  - OBSERVED 2026-09-08: ros2 pkg prefix resolved to the EXP-009 install, ros2 pkg executables included text_pick_agent and e2e_acceptance, and the new launch --show-args exposed the expected contract.
  - OBSERVED 2026-09-08: the first package run had 1657 passes and four INVALID environment failures because the isolated worktree submodule was uninitialized. Initializing the pinned local-cache commit 71bc9346cf93d6227a6678fcacf63f3e18acfcba made the rerun pass all 1661 tests in 37.09 seconds.
  - OBSERVED 2026-09-08: colcon test-result read all recorded XML as 1675 tests, zero errors, zero failures, and zero skips.
inferred:
  - The top-level exit code is reliable at the LaunchService boundary, and candidate-package provenance is closed for so101_demo_py plus so101_mujoco_support on macOS.
conclusion: VALID for macOS Task 8; the ai-station NVMe scratch and installed-package gate remains to be run before the cross-platform acceptance claim.
evidence:
  - /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-009
decision: KEEP
next_experiment: EXP-010
```

```yaml
checkpoint_id: CP-008
last_valid_experiment: EXP-009
current_hypothesis: The same commit can pass ai-station installation and NVMe-backed package gates before live YOLO-Seg E2E runs begin.
working_tree_status: Task 8 changes are limited to installed launcher/executable assertions, real LaunchService process tests, plan progress, and this ledger.
owned_processes: NONE
preserved_processes: ai-station tmux sessions codex, microduck-policy-queue, and so101-exp079-linux-r3; all unknown or unrelated processes.
confirmed_conclusions:
  - LaunchService drains complete valid failure lines before classifying process exit in the tested immediate-exit case.
  - A truncated SO101_EVENT prefix is rejected at EOF and cross-child events remain strictly ordered.
  - Accepted workflow plus cleanup returns zero; cleanup escalation remains a nonzero outcome even after machine acceptance.
  - EXP-009 established a 1661-test ordinary package pass from the fresh macOS candidate overlay.
disproven_routes:
  - Claiming installed provenance while so101_mujoco_support resolves from the previous overlay.
  - Running source-tree contract tests with an uninitialized pinned submodule.
open_risks:
  - ai-station has not yet built or tested this candidate commit in its registered durable evidence root.
  - Grounded SAM has no currently registered PickPlace-qualified bundle; Task 9 formal success remains blocked by model qualification.
retained_runs:
  - /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-009
archived_runs: []
deletion_candidates:
  - /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-009/build
  - /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-009/install
  - /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-009/colcon-log
next_command: Commit the macOS Task 8 tests, then transfer the exact commit to a fresh ai-station worktree and run its NVMe scratch gate.
```

```yaml
experiment_id: EXP-010
status: VALID
prior_experiment: EXP-009
hypothesis: The exact candidate commit can be rebuilt in an isolated ai-station overlay and pass the ordinary package gate with every temporary file rooted on the registered NVMe evidence volume.
prediction: Candidate package prefixes and Python source provenance resolve to the transferred worktree, the ordinary suite collects 1661 tests, and JUnit reports zero errors or failures.
single_variable: Move the Task 8 installed-package gate from macOS to ai-station while keeping commit e6057016a0b42644349c3d381d6252261f4566d7 fixed.
lifecycle: ISOLATED_STACK
preconditions:
  - The transferred worktree is /data/work/ws_moveit/.worktrees/text-agent-e2e-e6057016 at exact commit e6057016a0b42644349c3d381d6252261f4566d7 with submodule commit 71bc9346cf93d6227a6678fcacf63f3e18acfcba.
  - The registered durable evidence root is /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad.
  - No ROS graph, MuJoCo process, model inference, or Docker container is started by the package gate.
success_criteria:
  - so101_demo_py, so101_mujoco_support, mujoco_ros2_control, its messages and plugins, mujoco_3d_lidar, and so101_teleop resolve from the candidate overlay where applicable.
  - The installed text_pick_agent and e2e_acceptance entry points resolve candidate source and the E2E launch exposes its installed argument contract.
  - TMPDIR, TMP, and TEMP resolve to a previously nonexistent scratch directory under the registered durable root using the exact test interpreter.
  - colcon test-result reports 1661 tests, zero errors, zero failures, and zero skips.
failure_criteria:
  - A required workspace dependency resolves to /opt/ros/jazzy, source provenance cannot reach the exact Git commit, test collection is zero, or JUnit contains any failure.
invalid_criteria:
  - The selected Python cannot import the locked test dependencies, the build reuses an incompatible setuptools installation mode, or the scratch path is outside the registered root.
provenance:
  source_commit: e6057016a0b42644349c3d381d6252261f4566d7
  transfer_bundle_sha256: 23bf79cca3434eded157c49778a8fe350882f32ab30d7d4f9a51e946577f17fc
  worktree: /data/work/ws_moveit/.worktrees/text-agent-e2e-e6057016
  install_overlay: /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/install
  runtime_executable: /usr/bin/python3
  dependency_pythonpath: /usr/lib/python3/dist-packages:/data/work/venvs/so101-grounded-sam/lib/python3.12/site-packages:/opt/ros/jazzy/lib/python3.12/site-packages
  torch: 2.13.0+cu130
  pillow: 10.2.0
  rclpy: /opt/ros/jazzy/lib/python3.12/site-packages/rclpy/__init__.py
  gpu: NVIDIA GeForce RTX 5080
  driver: 595.84
  inference_image_digest: sha256:fafdb147fab33758b45f8edb39d6ddb231b38ebe59b99dce17f01a0bf35d3a3e
  ros_domain_id: not-used-package-tests
  gz_partition: not-used-package-tests
commands:
  - command: GIT_LFS_SKIP_SMUDGE=1 git worktree add --detach /data/work/ws_moveit/.worktrees/text-agent-e2e-e6057016 refs/codex-transfer/text-agent-e2e-e6057016
    exit_code: 0
  - command: colcon build --packages-select mujoco_3d_lidar mujoco_ros2_control_msgs mujoco_ros2_control_plugins so101_mujoco_support so101_teleop so101_demo_py --symlink-install
    exit_code: 0_AFTER_DEPENDENCY_RETRY
  - command: colcon build --packages-select mujoco_ros2_control --symlink-install
    exit_code: 0
  - command: PYTHONNOUSERSITE=1 PYTHONPATH=<system-dist:locked-venv:ros:candidate-overlay> /usr/bin/colcon test --packages-select so101_demo_py --pytest-args test
    exit_code: 0
  - command: PYTHONNOUSERSITE=1 PYTHONPATH=<system-dist:locked-venv:ros:candidate-overlay> /usr/bin/colcon test-result --test-result-base <registered-root>/build --verbose
    exit_code: 0
invalid_attempts:
  - attempt: dependency-incomplete-build
    result: so101_demo_py was not started because mujoco_3d_lidar was absent from the fresh install base.
  - attempt: teleop-incomplete-build
    result: so101_demo_py was not started because so101_teleop was absent from the fresh install base.
  - attempt: system-python-without-locked-dependencies
    scratch: /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/scratch/20260908T032450Z-6a0a7e72/tmp
    result: zero tests executed; collection stopped because torch was unavailable.
  - attempt: locked-venv-copy-install
    scratch: /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/scratch/20260908T033050Z-9163c7af/tmp
    result: 1650 passed and 11 failed because setuptools 84 produced a copied install with unavailable Git source provenance and mujoco_ros2_control still resolved from /opt/ros/jazzy.
observed:
  - OBSERVED 2026-09-08: the first worktree checkout failed while Gitee LFS tried to fetch an unrelated dataset without permission; GIT_LFS_SKIP_SMUDGE=1 created the exact detached worktree without changing the candidate files used by this task.
  - OBSERVED 2026-09-08: system setuptools 68.1.2 preserved editable source identity, while locked-venv setuptools 84.0.0 produced a copied install that correctly failed the execution-source gate.
  - OBSERVED 2026-09-08: after building mujoco_ros2_control in the same overlay, its package prefix moved from /opt/ros/jazzy to the registered candidate install.
  - OBSERVED 2026-09-08: the final scratch was /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/scratch/20260908T033920Z-39d0f6c1/tmp, and /usr/bin/python3 resolved tempfile.gettempdir() to that exact path before pytest started.
  - OBSERVED 2026-09-08: the ordinary suite passed all 1661 tests in 30.97 seconds; the recorded end-to-end test command elapsed 33 seconds and colcon test-result reported zero errors, failures, and skips.
inferred:
  - The exact candidate is qualified for Task 8 installed-package behavior on both macOS and ai-station; live perception and MuJoCo acceptance remain separate Task 9 gates.
conclusion: VALID; Task 8 cross-platform installation, process-boundary, ordinary regression, and ai-station NVMe scratch gates are complete.
evidence:
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad
decision: KEEP
next_experiment: EXP-011
```

```yaml
checkpoint_id: CP-009
last_valid_experiment: EXP-010
current_hypothesis: The candidate can now enter Task 9 live YOLO-Seg acceptance without changing source, model, policy, provider, or failure semantics.
working_tree_status: Task 8 code and tests are committed; only the plan checkbox and this ai-station evidence checkpoint are pending commit.
owned_processes: NONE
preserved_processes: ai-station tmux sessions codex, microduck-policy-queue, and so101-exp079-linux-r3; all unknown or unrelated processes.
confirmed_conclusions:
  - The exact candidate commit passes 1661 ordinary package tests on both macOS and ai-station.
  - ai-station package provenance includes candidate mujoco_ros2_control rather than the ROS underlay copy.
  - The final ai-station test used a verified NVMe scratch and preserved all attempts for audit.
disproven_routes:
  - Running the ai-station package gate with /usr/bin/python3 and no locked dependency path.
  - Using the locked venv setuptools 84 copy install for a runtime that must prove its source Git commit.
open_risks:
  - Task 9 live YOLO-Seg has not yet run against this top-level supervisor.
  - Grounded SAM has no registered PickPlace-qualified bundle, so both formal Grounded SAM matrix cells remain blocked.
retained_runs:
  - /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-009
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad
archived_runs: []
deletion_candidates:
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/build
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/install
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/candidate-venv-r1
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/scratch/20260908T032450Z-6a0a7e72
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/scratch/20260908T033050Z-9163c7af
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/scratch/20260908T033920Z-39d0f6c1
next_command: Commit the Task 8 ai-station checkpoint, then preregister EXP-011 and run one fresh headless Linux YOLO-Seg E2E.
```

```yaml
experiment_id: EXP-011
status: VALID
prior_experiment: EXP-010
hypothesis: The supervised E2E launch can use the frozen YOLO-Seg model on ai-station CUDA and the existing Ollama planner to complete one unique-cup headless MuJoCo pick-place, independently validate physics and Planning Scene state, clean every owned process and container, and exit zero.
prediction: The strict workflow trace reaches E2E_ACCEPTED in order, e2e-result.json records machine_accepted and cleanup_complete, and the launch exits zero with no owned process or container remaining.
single_variable: Start the first real Linux YOLO-Seg E2E run; keep source, model, policy, provider model, scene, and authorization fixed.
lifecycle: FULL_RESTART
preconditions:
  - Source commit is fixed at 09b8bc0c and will be transferred without changing production code.
  - Candidate prefixes and the 1661-test package gate from EXP-010 remain valid.
  - The unique-cup task_start keyframe, plastic-cup-yolo11s-seg-v2 weights, and Docker image digest are fixed to the registered model inputs.
  - The local Ollama qwen3.5:4b preview returned plastic_cup plus pick plus empty constraints; a task-owned reverse tunnel will expose that unchanged localhost endpoint during this run and will be closed during cleanup.
  - ROS_DOMAIN_ID 218, session text-e2e-linux-yolo-011, and run root /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-011-linux-yolo-run-01 are fresh.
  - The unrelated GPU process /data/work/microduck_rl/.venv/bin/python3 is preserved; no ROS nodes or Docker containers were present at preregistration.
success_criteria:
  - Actual planner provider and model are ollama and qwen3.5:4b with a supported fixed command.
  - Actual perception device is CUDA with fallback_used false and weights SHA f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781.
  - RGB, depth, CameraInfo, tf2, selected cup pose, request/session/reset identities, dynamic DONE trace, controller feedback, lift/transport/release stability, contact, world membership, and Planning Scene readback all satisfy the validator.
  - e2e-result.json is atomically present only after all owned processes and the workflow-scoped Docker container have exited; launch exit code is zero.
failure_criteria:
  - Any strict event, model, provider, perception, motion, physical, Planning Scene, evidence-write, or cleanup gate fails, or launch exit is nonzero.
invalid_criteria:
  - Source/prefix/model/image identity drifts, provider tunnel fails before launch, a previous run root exists, the requested ROS domain is occupied, or an unrelated process is altered.
provenance:
  source_commit: 09b8bc0c2ec480230fb9b1e636216b3f30f0ff01
  install_overlay: /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/install
  yolo_weights: /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/training/full-exp-012/best.pt
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  perception_runtime: docker
  perception_device: cuda
  perception_allow_cpu_fallback: false
  container_image: so101-yolo11n-seg-inference:ros-jazzy-torch2.13.0-cu130-ultralytics8.4.115
  container_image_digest: sha256:fafdb147fab33758b45f8edb39d6ddb231b38ebe59b99dce17f01a0bf35d3a3e
  planner_provider: ollama-fallback
  planner_model: qwen3.5:4b
  ros_domain_id: 218
  session_id: text-e2e-linux-yolo-011
  run_root: /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-011-linux-yolo-run-01
commands:
  - command: ros2 launch so101_demo_py so101_mujoco_text_pick_agent_e2e.launch.py instruction:='Pick the plastic cup. Apply no constraints.' run_mode:=execute execute:=true skip_confirmation:=true headless:=true sensor_rendering:=true session_id:=text-e2e-linux-yolo-011 evidence_file:=<run-root>/e2e-result.json perception_backend:=yolo_seg perception_runtime:=docker perception_device:=cuda perception_allow_cpu_fallback:=false perception_weights:=<registered-best.pt> perception_weights_sha256:=f281d252... perception_container_image:=<registered-image>
    exit_code: 1
observed:
  - OBSERVED 2026-09-08: the stack reached STACK_READY, the Ollama fallback produced a supported fixed command, and dynamic runtime emitted RUNTIME_STARTED then RUNTIME_READY.
  - OBSERVED 2026-09-08: the frozen image exited with code 2 because its installed rgbd_object_pose did not recognize --require-output-subscriber, --emit-workflow-events, or --workflow-id.
  - OBSERVED 2026-09-08: the primary failure was CHILD_EXITED_WITHOUT_TERMINAL_EVENT for perception; machine_accepted was false and physical and Planning Scene outcomes remained empty.
  - OBSERVED 2026-09-08: owned cleanup completed with an empty remainder; no workflow-scoped container or ROS_DOMAIN_ID 218 node remained.
  - OBSERVED 2026-09-08: a new image was built under the distinct tag so101-yolo11n-seg-inference:text-agent-e2e-09b8bc0c from the exact candidate source. Its digest is sha256:bed9bda05f455d3732d3c5b854744b3097b92e7e84375ff0c3305cb1b17f77c7 and its installed help exposes all three required flags.
inferred:
  - The first live supervised boundary and cleanup semantics work for an early perception failure, but the frozen pre-candidate image cannot satisfy the new child event protocol.
conclusion: VALID failure reproduction; the success hypothesis is disproven because the registered image predates the required perception CLI contract.
evidence:
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-011-linux-yolo-run-01
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-011-linux-yolo-run-01.console.log
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-011-image-build.console.log
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-011-image-cli-help.txt
decision: REPEAT
next_experiment: EXP-012
```

```yaml
experiment_id: EXP-012
status: VALID
prior_experiment: EXP-011
hypothesis: Rebuilding only the YOLO-Seg inference image from the exact candidate source removes the perception CLI mismatch and lets the fixed Linux E2E workflow advance through the strict event protocol.
prediction: The new image accepts the supervisor flags, emits PERCEPTION_READY and POSE_PUBLISHED, and the workflow either reaches E2E_ACCEPTED or produces a later evidence-backed failure without leaking owned resources.
single_variable: Replace the pre-candidate inference image with so101-yolo11n-seg-inference:text-agent-e2e-09b8bc0c; keep source, weights, scene, policy, provider, device, and authorization fixed.
lifecycle: FULL_RESTART
preconditions:
  - Source commit remains 09b8bc0c2ec480230fb9b1e636216b3f30f0ff01 in the isolated candidate worktree and overlay.
  - The new image digest is sha256:bed9bda05f455d3732d3c5b854744b3097b92e7e84375ff0c3305cb1b17f77c7, and its installed help exposes --require-output-subscriber, --emit-workflow-events, and --workflow-id.
  - The same frozen weights and SHA256 from EXP-011 are used with CUDA and CPU fallback disabled.
  - The Ollama qwen3.5:4b endpoint remains reachable only through the task-owned reverse tunnel.
  - ROS_DOMAIN_ID 219, session text-e2e-linux-yolo-012, and run root /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-012-linux-yolo-run-01 are fresh.
success_criteria:
  - Planner, perception, runtime, physical outcome, Planning Scene readback, evidence finalization, and cleanup satisfy the same strict criteria as EXP-011.
  - The workflow reaches E2E_ACCEPTED and exits zero.
failure_criteria:
  - Any strict event, perception, motion, physical, Planning Scene, evidence-write, or cleanup gate fails with a valid result and nonzero launch exit.
invalid_criteria:
  - Image/source/weights identity drifts, the new run identity is not fresh, the provider tunnel fails before launch, or an unrelated process is altered.
provenance:
  source_commit: 09b8bc0c2ec480230fb9b1e636216b3f30f0ff01
  install_overlay: /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/install
  yolo_weights: /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/training/full-exp-012/best.pt
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  perception_runtime: docker
  perception_device: cuda
  perception_allow_cpu_fallback: false
  container_image: so101-yolo11n-seg-inference:text-agent-e2e-09b8bc0c
  container_image_digest: sha256:bed9bda05f455d3732d3c5b854744b3097b92e7e84375ff0c3305cb1b17f77c7
  planner_provider: ollama-fallback
  planner_model: qwen3.5:4b
  ros_domain_id: 219
  session_id: text-e2e-linux-yolo-012
  run_root: /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-012-linux-yolo-run-01
commands:
  - command: ros2 launch so101_demo_py so101_mujoco_text_pick_agent_e2e.launch.py instruction:='Pick the plastic cup. Apply no constraints.' run_mode:=execute execute:=true skip_confirmation:=true headless:=true sensor_rendering:=true session_id:=text-e2e-linux-yolo-012 evidence_file:=<run-root>/e2e-result.json perception_backend:=yolo_seg perception_runtime:=docker perception_device:=cuda perception_allow_cpu_fallback:=false perception_weights:=<registered-best.pt> perception_weights_sha256:=f281d252... perception_container_image:=so101-yolo11n-seg-inference:text-agent-e2e-09b8bc0c
    exit_code: 1
observed:
  - OBSERVED 2026-09-08: the candidate image emitted PERCEPTION_READY, selected exactly one plastic_cup, published a world-transformed cup pose, and recorded runtime_device cuda with the fixed weights SHA and no failure.
  - OBSERVED 2026-09-08: dynamic execution reached DONE with all 19 transitions, bilateral grasp contact, physical lift, transport, release settling, table contact, zero final fingertip contacts, world plastic_cup membership, and no attached Planning Scene object.
  - OBSERVED 2026-09-08: after RUNTIME_COMPLETED, launch_ros appended --ros-args to the Node-based e2e_acceptance invocation; its argparse parser rejected that token and exited 2 before readback.
  - OBSERVED 2026-09-08: the final result preserved CHILD_EXITED_WITHOUT_TERMINAL_EVENT for the E2E validator at phase RUNTIME_COMPLETED; machine_accepted was false and cleanup completed with no owned remainder.
  - OBSERVED 2026-09-08: a red test reproduced the exact SystemExit 2, and the minimal parser-boundary change used the same rclpy.utilities.remove_ros_args pattern as the repository's other ROS CLIs. The focused acceptance, launch, and real-process suites then passed 44 tests.
inferred:
  - Rebuilding the perception image fixed the EXP-011 boundary, and the runtime evidence is a complete successful pick-place, but formal E2E acceptance cannot be claimed until the independent validator runs and records fresh readback.
conclusion: VALID failure reproduction; the new image hypothesis advanced through perception and motion, then exposed a separate validator argument-boundary defect.
evidence:
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-012-linux-yolo-run-01
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-012-linux-yolo-run-01.console.log
  - /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-012-acceptance-cli-fix-expanded.xml
decision: FIX_AND_REPEAT
next_experiment: EXP-013
```

```yaml
checkpoint_id: CP-010
last_valid_experiment: EXP-012
current_hypothesis: Removing ROS launch arguments before parsing application arguments will let the independent validator read final MuJoCo and Planning Scene state after an otherwise successful fixed workflow.
working_tree_status: The validator argument-boundary fix, its red-then-green test, and EXP-011/EXP-012 evidence records are uncommitted pending the full ordinary package gate.
owned_processes:
  - local reverse SSH tunnel session 62665 exposing task-owned Ollama localhost to ai-station
preserved_processes:
  - ai-station /data/work/microduck_rl/.venv/bin/python3 GPU process
confirmed_conclusions:
  - The candidate YOLO image closes the strict perception event protocol and runs on CUDA with the fixed weights.
  - The dynamic runtime completed all 19 transitions with physical grasp, release, final table stability, and synchronized Planning Scene world membership.
  - The validator failure is isolated to application argument parsing before any final readback occurs.
disproven_routes:
  - Reusing the pre-candidate inference image for a workflow-events-qualified run.
  - Treating a ROS Node console executable as if launch_ros would pass only its explicit application arguments.
open_risks:
  - The fixed validator has not yet run on ai-station or produced an E2E_ACCEPTED result.
  - Five consecutive YOLO successes, both Mac matrix cells, and both Grounded SAM cells remain incomplete.
retained_runs:
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-011-linux-yolo-run-01
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-012-linux-yolo-run-01
archived_runs: []
deletion_candidates: []
next_command: Run the full ordinary macOS package gate, commit the one-boundary fix, transfer the exact commit, run its ai-station NVMe package gate, then preregister and execute EXP-013.
```

```yaml
experiment_id: EXP-013
status: VALID
prior_experiment: EXP-012
hypothesis: The exact validator argument fix lets the independent readback process consume ROS launch arguments and decide the already-qualified Linux YOLO-Seg workflow from fresh MuJoCo and Planning Scene state.
prediction: The workflow reaches E2E_ACCEPTED after RUNTIME_COMPLETED, writes physical and Planning Scene outcomes, completes cleanup, and exits zero.
single_variable: Add only commit 1b78c45ce0eb71fb10812343255cdf24da3cf5dd, which strips ROS arguments before e2e_acceptance application parsing; all runtime inputs remain fixed from EXP-012.
lifecycle: FULL_RESTART
preconditions:
  - The exact commit passed 1661 ordinary tests on macOS in 38.70 seconds.
  - The exact commit passed 1661 ordinary tests on ai-station in 33.39 seconds using /usr/bin/python3 and fresh verified scratch /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/scratch/20260908T035100Z-b62451d9/tmp.
  - The preceding scratch /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/scratch/20260908T034900Z-ff561f4a/tmp is retained as INVALID because colcon ran outside the candidate workspace, selected zero packages, and read stale results.
  - The fixed YOLO weights, candidate image digest, Ollama provider/model, task scene, execution policy, and explicit authorization are unchanged from EXP-012.
  - ROS_DOMAIN_ID 220, session text-e2e-linux-yolo-013, and run root /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-013-linux-yolo-run-01 are fresh.
success_criteria:
  - The strict event trace reaches E2E_ACCEPTED in order after the complete planner, perception, and runtime sequence.
  - Independent readback proves a stable final cup in MuJoCo, zero attached plastic_cup, a world plastic_cup, and a Planning Scene pose matching MuJoCo within policy tolerances.
  - e2e-result.json records machine_accepted true, runtime exit code zero, cleanup complete with no remainder, and the launch exits zero.
failure_criteria:
  - Any workflow, final physics, Planning Scene, evidence, cleanup, or launch exit gate fails.
invalid_criteria:
  - The exact source, image, model, provider, run identity, or input policy drifts; a prior root is reused; or an unrelated process is altered.
provenance:
  source_commit: 1b78c45ce0eb71fb10812343255cdf24da3cf5dd
  transfer_bundle_sha256: fbad0bccba05d5c51b460fa062fd9902e27dd3d3145b3b836a395bc46661f377
  install_overlay: /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/install
  yolo_weights: /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/training/full-exp-012/best.pt
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  perception_runtime: docker
  perception_device: cuda
  perception_allow_cpu_fallback: false
  container_image: so101-yolo11n-seg-inference:text-agent-e2e-09b8bc0c
  container_image_digest: sha256:bed9bda05f455d3732d3c5b854744b3097b92e7e84375ff0c3305cb1b17f77c7
  planner_provider: ollama-fallback
  planner_model: qwen3.5:4b
  ros_domain_id: 220
  session_id: text-e2e-linux-yolo-013
  run_root: /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-013-linux-yolo-run-01
commands:
  - command: ros2 launch so101_demo_py so101_mujoco_text_pick_agent_e2e.launch.py instruction:='Pick the plastic cup. Apply no constraints.' run_mode:=execute execute:=true skip_confirmation:=true headless:=true sensor_rendering:=true session_id:=text-e2e-linux-yolo-013 evidence_file:=<run-root>/e2e-result.json perception_backend:=yolo_seg perception_runtime:=docker perception_device:=cuda perception_allow_cpu_fallback:=false perception_weights:=<registered-best.pt> perception_weights_sha256:=f281d252... perception_container_image:=so101-yolo11n-seg-inference:text-agent-e2e-09b8bc0c
    exit_code: 1
observed:
  - OBSERVED 2026-09-08: exact source, image digest, empty ROS domain, empty workflow-container set, and Ollama model availability passed the scripted preflight before the run root was created.
  - OBSERVED 2026-09-08: the planner, candidate YOLO CUDA perception, and 19-state dynamic runtime completed again; the validator accepted --ros-args and emitted a schema-valid E2E_REJECTED event instead of exiting in argparse.
  - OBSERVED 2026-09-08: the validator rejected before creating fresh readback files. Layered offline diagnosis loaded dynamic and perception documents successfully and failed only at _policy_document with `dynamic policy path is invalid`.
  - OBSERVED 2026-09-08: the recorded policy is a colcon --symlink-install link whose readlink -f target is the exact candidate source policy; the file SHA is dc17d704ea9a333a387896bf36293a876bedc0be7868bc8b1ea800f4ce19d66d.
  - OBSERVED 2026-09-08: machine_accepted remained false, runtime_exit_code was zero, the final failure was E2E_EVIDENCE_REJECTED, and owned cleanup completed without a remainder.
  - OBSERVED 2026-09-08: a dedicated red test reproduced the policy-link rejection. Strictly resolving the absolute path to its real regular file before the existing digest and manifest checks made the focused acceptance/launch/process suite pass 45 tests and the full macOS ordinary suite pass 1662 tests in 38.69 seconds.
inferred:
  - The validator's no-symlink rule conflicts with the implementation plan's explicit --symlink-install overlay; resolving first retains content and manifest validation while admitting the planned install topology.
conclusion: VALID failure reproduction; the argument fix worked, and the remaining failure is the validator's incompatible treatment of a hash-bound colcon policy link.
evidence:
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-013-linux-yolo-run-01
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-013-linux-yolo-run-01.console.log
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-013-preflight.txt
  - /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-013-policy-symlink-fix.xml
  - /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-013-full-macos.xml
decision: FIX_AND_REPEAT
next_experiment: EXP-014
```

```yaml
checkpoint_id: CP-011
last_valid_experiment: EXP-013
current_hypothesis: A validator that resolves the planned colcon policy link before the existing digest and manifest checks can complete independent final readback and acceptance.
working_tree_status: The policy-link fix, its red-then-green test, EXP-013 outcome, and this checkpoint are uncommitted after a 1662-test macOS pass.
owned_processes:
  - local reverse SSH tunnel session 62665 exposing task-owned Ollama localhost to ai-station
preserved_processes:
  - ai-station /data/work/microduck_rl/.venv/bin/python3 GPU process
confirmed_conclusions:
  - The argv fix is proven live: the validator now parses and emits a terminal workflow event.
  - Both candidate-image live repetitions completed planner, perception, and all 19 runtime transitions with zero runtime error.
  - The second validator failure is reproducible from retained evidence without restarting ROS.
disproven_routes:
  - Rejecting every policy symlink while also qualifying a --symlink-install deployment.
open_risks:
  - Fresh final MuJoCo and Planning Scene readback has still not been recorded by a live accepted run.
  - Consecutive-run, Mac, Grounded SAM, negative-path, GUI, and learner-evidence gates remain incomplete.
retained_runs:
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-013-linux-yolo-run-01
archived_runs: []
deletion_candidates:
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/scratch/20260908T034900Z-ff561f4a
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/scratch/20260908T035100Z-b62451d9
next_command: Commit the policy-link fix and EXP-013 record, transfer the exact commit, pass a fresh ai-station NVMe package gate, preregister EXP-014, and run one fresh Linux YOLO E2E.
```

```yaml
experiment_id: EXP-014
status: VALID
prior_experiment: EXP-013
hypothesis: Resolving the hash-bound colcon policy link to its real regular file will let the independent validator collect final MuJoCo and Planning Scene state and accept the otherwise fixed workflow.
prediction: The exact workflow reaches E2E_ACCEPTED, writes both final readback files and accepted outcomes, cleans every owned resource, and exits zero.
single_variable: Add only commit 4d3d7ce7898b4641beb487d7a0b38107ab556deb, which resolves the planned symlink-installed policy path before existing digest and manifest validation.
lifecycle: FULL_RESTART
preconditions:
  - The exact commit passed 1662 ordinary tests on macOS in 38.69 seconds and on ai-station in 32.80 seconds.
  - The ai-station gate used /usr/bin/python3 with verified fresh scratch /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/scratch/20260908T041000Z-44aa651c/tmp.
  - The fixed YOLO weights, image digest, Ollama provider/model, task scene, execution policy, and authorization are unchanged.
  - ROS_DOMAIN_ID 221, session text-e2e-linux-yolo-014, and run root /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-014-linux-yolo-run-01 are fresh.
success_criteria:
  - The strict trace reaches E2E_ACCEPTED after all planner, perception, and runtime events.
  - Independent final readback proves stable MuJoCo placement and matching Planning Scene world state with no attachment.
  - The authoritative result records machine_accepted true, runtime_exit_code zero, cleanup complete with no remainder, and launch exit zero.
failure_criteria:
  - Any strict event, readback, physical, Planning Scene, evidence, cleanup, or exit gate fails.
invalid_criteria:
  - Source, image, model, provider, input, or run identity drifts; a previous root is reused; or an unrelated process is altered.
provenance:
  source_commit: 4d3d7ce7898b4641beb487d7a0b38107ab556deb
  transfer_bundle_sha256: 732f2499683cce6d15b5380661aa56f148bc29ae692c6ae70403ea2016cb1557
  install_overlay: /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/install
  yolo_weights: /data/work/so101-evidence/v5-t004-yolo-seg-rgbd/20260831-f09cf88/training/full-exp-012/best.pt
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  perception_runtime: docker
  perception_device: cuda
  perception_allow_cpu_fallback: false
  container_image: so101-yolo11n-seg-inference:text-agent-e2e-09b8bc0c
  container_image_digest: sha256:bed9bda05f455d3732d3c5b854744b3097b92e7e84375ff0c3305cb1b17f77c7
  planner_provider: ollama-fallback
  planner_model: qwen3.5:4b
  ros_domain_id: 221
  session_id: text-e2e-linux-yolo-014
  run_root: /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-014-linux-yolo-run-01
commands:
  - command: ros2 launch so101_demo_py so101_mujoco_text_pick_agent_e2e.launch.py instruction:='Pick the plastic cup. Apply no constraints.' run_mode:=execute execute:=true skip_confirmation:=true headless:=true sensor_rendering:=true session_id:=text-e2e-linux-yolo-014 evidence_file:=<run-root>/e2e-result.json perception_backend:=yolo_seg perception_runtime:=docker perception_device:=cuda perception_allow_cpu_fallback:=false perception_weights:=<registered-best.pt> perception_weights_sha256:=f281d252... perception_container_image:=so101-yolo11n-seg-inference:text-agent-e2e-09b8bc0c
    exit_code: 1
observed:
  - OBSERVED 2026-09-08: scripted preflight passed exact commit, image digest, provider model, fresh domain/root, and empty workflow-container checks.
  - OBSERVED 2026-09-08: planner, CUDA perception, 19-state runtime, and independent final readback all completed. MuJoCo final state was stable, supported by the table, free of fingertip contact, and nearly stationary.
  - OBSERVED 2026-09-08: the validator rejected with E2E_DYNAMIC_EVIDENCE_INVALID and E2E_PLANNING_SCENE_INVALID. The Planning Scene position difference was 0.0011658013223472305 m and orientation difference 0.000009062552536113162 rad, both below the configured geometric tolerances.
  - OBSERVED 2026-09-08: all seven motion event position/orientation errors passed policy, the final publisher sequence exceeded the release marker, and dynamic world/attached membership was correct.
  - OBSERVED 2026-09-08: dynamic input_frame_id was world while perception source_frame_id was task_camera_frame; the validator currently requires equality although they describe output and sensor-source frames respectively.
  - OBSERVED 2026-09-08: MuJoCo source_timestamp_ns was 58704000000 while Planning Scene source_timestamp_ns was 1788810607533085057. Their clocks are simulation time and wall time, so the 5-second skew comparison necessarily failed.
  - OBSERVED 2026-09-08: launch exited nonzero, machine_accepted remained false, runtime_exit_code was zero, and owned cleanup completed with no remainder.
inferred:
  - The remaining success-path rejection is architectural evidence-schema and clock-domain mismatch, not motion instability or a need to loosen policy thresholds.
conclusion: VALID rejection; the live workflow is physically stable but cannot satisfy the current validator until published-frame provenance and final-readback clock semantics are redesigned coherently.
evidence:
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-014-linux-yolo-run-01
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-014-linux-yolo-run-01.console.log
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-014-preflight.txt
decision: HOLD_SUCCESS_PATH_FOR_ARCHITECTURE_REVIEW
next_experiment: EXP-015
```

```yaml
experiment_id: EXP-015
status: VALID
prior_experiment: EXP-014
hypothesis: The actual Ollama planner rejects an instruction outside the supported plastic-cup pick capability before dispatch, perception, or motion side effects.
prediction: The launch exits nonzero with a planner or command rejection as primary failure, without RUNTIME_STARTED, perception events, or a dynamic execution manifest.
single_variable: Replace only the natural-language instruction with `Do not pick anything. Fly the robot to the moon.`; keep commit, model, provider, backend, scene, and authorization fixed.
lifecycle: FULL_RESTART
preconditions:
  - Source commit remains 4d3d7ce7898b4641beb487d7a0b38107ab556deb and the registered image/model inputs are unchanged.
  - This run tests the actual provider. If it still emits a supported fixed command, the run does not count as the required Planner-rejection case and no result is relabeled.
  - ROS_DOMAIN_ID 222, session text-e2e-linux-yolo-015, and run root /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-015-linux-planner-negative-run-01 are fresh.
success_criteria:
  - Actual provider/model provenance is recorded and the request is rejected before runtime/perception/motion effects.
  - Authoritative result is non-accepted, cleanup completes, no owned resource remains, and launch exits nonzero.
failure_criteria:
  - The provider emits a supported command, any runtime/perception/motion event occurs, or the launch/result/cleanup semantics are inconsistent.
invalid_criteria:
  - Provider availability, source, model, domain, root, or unrelated-process isolation drifts.
provenance:
  source_commit: 4d3d7ce7898b4641beb487d7a0b38107ab556deb
  planner_provider: ollama-fallback
  planner_model: qwen3.5:4b
  perception_backend: yolo_seg
  ros_domain_id: 222
  session_id: text-e2e-linux-yolo-015
  run_root: /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-015-linux-planner-negative-run-01
commands:
  - command: ros2 launch so101_demo_py so101_mujoco_text_pick_agent_e2e.launch.py instruction:='Do not pick anything. Fly the robot to the moon.' <same explicit execute and frozen YOLO arguments>
    exit_code: 1
observed:
  - OBSERVED 2026-09-08: exact preflight passed and actual Ollama qwen3.5:4b returned planner_outcome unsupported in 1091 ms with dispatch false.
  - OBSERVED 2026-09-08: the strict trace contained only STACK_READY then DISPATCH_REJECTED with primary PLANNER_OUTCOME_UNSUPPORTED.
  - OBSERVED 2026-09-08: no RUNTIME_STARTED, perception event, dynamic execution manifest, controller motion, or acceptance readback occurred.
  - OBSERVED 2026-09-08: launch exited 1, machine_accepted was false, cleanup completed with no remainder, and no workflow container was created.
inferred:
  - The actual provider respects the unsupported request and the supervisor stops before any business-side physical effect.
conclusion: VALID; the required live Planner rejection path is demonstrated with real provider output and fail-closed cleanup.
evidence:
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-015-linux-planner-negative-run-01
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-015-linux-planner-negative-run-01.console.log
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-015-preflight.txt
decision: KEEP
next_experiment: EXP-016
```

```yaml
experiment_id: EXP-016
status: INVALID
prior_experiment: EXP-015
hypothesis: With the two-cup MuJoCo keyframe, YOLO-Seg detects multiple matching plastic_cup instances and the selector fails closed before publishing /cup_pose or starting motion.
prediction: Perception emits PERCEPTION_READY then PERCEPTION_FAILED with TARGET_AMBIGUOUS, no CUP_POSE_PUBLISHED or RUNTIME_COMPLETED occurs, and cleanup returns a nonzero authoritative result with no owned remainder.
single_variable: Replace only mujoco_initial_keyframe task_start with v5_two_cups; restore the supported pick instruction and keep all other inputs fixed.
lifecycle: FULL_RESTART
preconditions:
  - Source commit, image, weights, provider/model, device, policy, and authorization remain fixed from EXP-014.
  - ROS_DOMAIN_ID 223, session text-e2e-linux-yolo-016, and run root /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-016-linux-two-cup-negative-run-01 are fresh.
success_criteria:
  - Perception evidence records at least two matching plastic_cup candidates and no published cup pose.
  - Primary failure is TARGET_AMBIGUOUS, dynamic runner does not begin motion, cleanup completes, and launch exits nonzero.
failure_criteria:
  - A pose is published, motion begins, the wrong primary failure is recorded, or any owned resource remains.
invalid_criteria:
  - Source/model/provider/run identity drifts or the two-cup keyframe does not actually contain two visible matching cups.
provenance:
  source_commit: 4d3d7ce7898b4641beb487d7a0b38107ab556deb
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  container_image_digest: sha256:bed9bda05f455d3732d3c5b854744b3097b92e7e84375ff0c3305cb1b17f77c7
  planner_provider: ollama-fallback
  planner_model: qwen3.5:4b
  mujoco_initial_keyframe: v5_two_cups
  ros_domain_id: 223
  session_id: text-e2e-linux-yolo-016
  run_root: /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-016-linux-two-cup-negative-run-01
commands:
  - command: ros2 launch so101_demo_py so101_mujoco_text_pick_agent_e2e.launch.py instruction:='Pick the plastic cup. Apply no constraints.' mujoco_initial_keyframe:=v5_two_cups <same explicit execute and frozen YOLO arguments>
    exit_code: 1
observed:
  - OBSERVED 2026-09-08: exact source, provider, image, weights, fresh root, domain, and workflow identity passed preflight; Ollama returned a supported pick command and dynamic runtime emitted RUNTIME_READY.
  - OBSERVED 2026-09-08: ros2_control then waited for robot_description, while the perception process waited for a positive simulation clock. No PERCEPTION_READY or candidate evidence was produced before the 30-second perception-startup deadline.
  - OBSERVED 2026-09-08: the authoritative primary failure was WORKFLOW_TIMEOUT at PERCEPTION_STARTUP, followed by CHILD_EXITED_WITHOUT_TERMINAL_EVENT during recovery. The run did not test whether the two visible cups produce TARGET_AMBIGUOUS.
  - OBSERVED 2026-09-08: launch exited 1, machine_accepted was false, runtime_exit_code was -2, cleanup completed with no remainder, and no workflow container or ROS_DOMAIN_ID 223 node remained.
inferred:
  - This run exposed a startup-order or robot-description publication failure distinct from the planned target-selection variable.
conclusion: INVALID; the two-cup negative acceptance case remains unproven because the stack never reached perception inference.
evidence:
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-016-linux-two-cup-negative-run-01
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-016-linux-two-cup-negative-run-01.console.log
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-016-preflight.txt
decision: RETAIN_INVALID
next_experiment: HOLD_FOR_ARCHITECTURE_AND_STARTUP_REVIEW
```

```yaml
checkpoint_id: CP-012
last_valid_experiment: EXP-015
current_hypothesis: Success-path qualification should resume only after the frame-provenance and clock-domain contract is redesigned and the two-cup startup failure is isolated.
working_tree_status: Production code is committed at 4d3d7ce7898b4641beb487d7a0b38107ab556deb; the remaining scoped files are the guide, plan progress, and EXP-015/016 ledger closeout for one documentation checkpoint.
owned_processes: NONE
preserved_processes:
  - ai-station /data/work/microduck_rl/.venv/bin/python3 GPU process
confirmed_conclusions:
  - The candidate passes 1662 ordinary tests on macOS and ai-station from qualified source/install roots.
  - Linux CUDA YOLO inference, the actual Ollama planner, all 19 runtime transitions, stable MuJoCo placement, and Planning Scene geometric agreement have each been observed in EXP-014.
  - The actual Planner rejects an unsupported instruction before perception or motion side effects in EXP-015.
  - The success-path validator compares an output world frame with a sensor input frame and compares MuJoCo simulation time with Planning Scene wall time; those facts cannot meet the current equality/skew contract.
  - EXP-016 cannot support the TARGET_AMBIGUOUS claim because perception never crossed its startup boundary.
  - The task-owned reverse SSH tunnel was closed after the final remote checks; ROS domains 218 through 223 and the workflow-container set were empty.
  - Final macOS verification loaded the ROS underlay and EXP-009 dependency overlay, resolved so101_demo from the isolated source mapping, and passed all 1662 ordinary tests in 38.77 seconds.
  - Two preceding final-verification attempts are INVALID environment records: the first omitted the ROS underlay, and the second omitted the candidate so101_mujoco_support overlay; both stopped during collection before tests ran.
disproven_routes:
  - Loosening geometry tolerances to address EXP-014; both position and orientation already passed their configured limits.
  - Counting EXP-016 as a two-cup negative acceptance result.
open_risks:
  - Linux and macOS YOLO acceptance, both Grounded SAM cells, five consecutive successes, MoveIt live abort, valid two-cup ambiguity, GUI video, and learner evidence remain incomplete.
  - No PickPlace-qualified Grounded SAM bundle is registered for either platform.
  - The EXP-016 robot_description/simulation-clock startup failure needs an isolated reproduction after the evidence-protocol redesign is settled.
retained_runs:
  - /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f
  - /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/final-verification-20260908-r3/so101_demo_py-pytest.xml
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-011-linux-yolo-run-01
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-012-linux-yolo-run-01
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-013-linux-yolo-run-01
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-014-linux-yolo-run-01
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-015-linux-planner-negative-run-01
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-016-linux-two-cup-negative-run-01
archived_runs: []
deletion_candidates:
  - /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/final-verification-20260908
  - /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/final-verification-20260908-r2
  - /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/final-verification-20260908-r3
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/build
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/install
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/candidate-venv-r1
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/scratch/20260908T032450Z-6a0a7e72
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/scratch/20260908T033050Z-9163c7af
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/scratch/20260908T033920Z-39d0f6c1
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/scratch/20260908T034900Z-ff561f4a
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/scratch/20260908T035100Z-b62451d9
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/scratch/20260908T041000Z-44aa651c
deletion_performed: false
next_command: Redesign the published-frame and timestamp-domain schema, add a focused startup-order reproduction for EXP-016, then rerun the required fresh acceptance matrix.
```

```yaml
experiment_id: EXP-017
status: VALID_LOCAL
prior_experiment: EXP-016
hypothesis: Explicit published-frame evidence plus source-specific clock domains remove EXP-014's two false rejections without changing either legacy launch contract.
prediction: New tests first reproduce camera/world and simulation/wall mismatches, then pass when publication events report world and final readbacks compare only host-monotonic collection times; both legacy launch contract suites remain byte-for-byte equivalent at their materialized interfaces.
single_variable: Revise only E2E evidence semantics approved by the user; retain motion policy thresholds, model inputs, launch authorization, and legacy entry surfaces.
lifecycle: ISOLATED_STACK
preconditions:
  - Source starts at ae62b686474b845dbaefc87415941f06183a396e with a clean worktree.
  - EXP-014 retained evidence proves geometry, motion, physical stability, and cleanup; only frame and clock comparisons are targeted.
  - The registered local evidence root remains /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f.
  - No ROS graph, MuJoCo process, Docker inference container, or provider tunnel is started during RED/GREEN unit work.
success_criteria:
  - Model and color perception emit the actual published world frame while retaining the sensor-source timestamp.
  - Dynamic input frame validates against world publication semantics; camera source frame remains separately present.
  - Both final documents carry fixed source clock domains and same-domain host-monotonic readback timestamps; cross-domain source timestamps are never subtracted.
  - Existing legacy Text Agent and perception launch argument, default, action, process-order, stdout, and exit contracts pass unchanged.
failure_criteria:
  - A test passes before the intended production change, any old entry contract changes, source timestamp correlation is weakened, or geometric thresholds change.
invalid_criteria:
  - Tests do not collect, resolve outside the isolated worktree mapping, or run without the required ROS/dependency overlay.
provenance:
  source_commit: ae62b686474b845dbaefc87415941f06183a396e
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python3
  ros_domain_id: not-used-test-only
  evidence: /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-017
commands:
  - command: PYTHONNOUSERSITE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider test_perception_workflow_events.py test_workflow_events.py test_e2e_acceptance.py -q
    exit_code: 1
    result: 8 failed, 103 passed
    evidence: /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-017/red/pytest.xml
  - command: same focused command after production changes
    exit_code: 0
    result: 111 passed in 1.05 seconds
    evidence: /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-017/green/pytest.xml
  - command: focused legacy launch, protocol, CLI, perception, and acceptance regression
    exit_code: 0
    result: 381 passed in 3.44 seconds
    evidence: /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-017/green-r2/pytest.xml
  - command: PYTHONNOUSERSITE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_text_pick_agent_e2e_process.py -q
    exit_code: 0
    result: 9 passed in 12.16 seconds
    evidence: /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-017/top-level-rejection/pytest-r2.xml
  - command: PYTHONNOUSERSITE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test -q
    exit_code: 0
    result: 1675 passed in 43.204 seconds
    evidence: /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-017/full-local/pytest.xml
observed:
  - OBSERVED 2026-09-08: user approved the frame/clock-domain redesign and required the four registered cup keyframes to pass acceptance while preserving legacy entry behavior.
  - OBSERVED 2026-09-08: the RED run produced exactly eight expected failures across color/model publication frame, protocol payload, dynamic frame correlation, cross-domain source time, and readback API behavior; 103 neighboring tests remained green.
  - OBSERVED 2026-09-08: after the scoped changes, the 111 focused tests passed. Publication events now carry world while perception evidence retains the sensor source frame and timestamp.
  - OBSERVED 2026-09-08: final readback documents now identify mujoco_sim and system_wall source clock domains and record same-host monotonic readback timestamps; the validator compares only those monotonic timestamps for collection skew.
  - OBSERVED 2026-09-08: both top-level physical rejection paths returned nonzero even though runtime_exit_code was zero, and preserved their physical and Planning Scene facts in the authoritative result.
  - OBSERVED 2026-09-08: 381 focused legacy/interface tests and all 1675 ordinary package tests passed from the isolated worktree mapping; the benchmark suite was not collected.
inferred:
  - Four-point qualification must be added to each platform/model configuration rather than replacing the existing matrix.
conclusion: VALID_LOCAL; the approved evidence semantics and legacy-entry regression gates pass locally. Exact-commit Linux build, container rebuild, and live four-point qualification remain separate runtime gates.
decision: COMMIT_AND_PROMOTE_EXACT_SOURCE
next_experiment: EXP-018
```

```yaml
checkpoint_id: CP-013
status: VALID_YOLO_TWO_PLATFORM_FOUR_POINT
prior_checkpoint: CP-012
scope: Complete the user-approved frame/clock repair, preserve both legacy entry contracts, and qualify the four registered cup positions on macOS/MPS and ai-station/CUDA with exact source commit 1614eb84ef73ad36f050368a65ef40ddae3ea78f.
source_provenance:
  branch: codex/text-agent-multibackend-e2e
  source_commit: 1614eb84ef73ad36f050368a65ef40ddae3ea78f
  source_bundle: /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-029-1614eb84.bundle
  source_bundle_sha256: 3d02e154070f3f687bc0f4c7f30d8fb2d24c0484f2b52c78cd54ee767567546e
  macos_candidate: /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/candidate-1614eb84-macos
  linux_candidate: /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/candidate-1614eb84-r4
model_provenance:
  backend: yolo_seg
  weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  macos_runtime: host
  macos_device: mps
  linux_runtime: docker
  linux_device: cuda
  allow_cpu_fallback: false
  linux_image: so101-yolo11n-seg-inference:text-agent-e2e-1614eb84
  linux_image_id: sha256:56f88257d1124cd02121d99f422c4f98aec198ea7873fa4ccf9a5407dd4093e0
verification:
  - gate: focused pose-delivery regression after keeping the E2E perception publisher alive
    result: 159 passed in 13.99 seconds
    evidence: /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-024-macos-pose-delivery-green.xml
  - gate: macOS complete ordinary suite from fresh current overlay
    result: 1676 passed in 43.74 seconds
    evidence: /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/exp-024-full-macos.xml
  - gate: ai-station complete ordinary suite with candidate source and support prefixes
    result: 1676 passed in 29.67 seconds
    scratch: /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/scratch/exp-035-pytest-current/tmp
    evidence: /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/tests/exp-035-current
legacy_contract:
  result: PASS
  evidence:
    - 381 focused legacy, interface, protocol, CLI, perception, and acceptance tests passed before the final publisher-lifetime fix.
    - The final macOS and ai-station ordinary suites each passed all 1676 tests, including legacy launch defaults, exact arguments, process ordering, stdout, exit behavior, installed launch inventory, and package provenance.
    - The final change is confined to the new E2E launch perception child lifetime; the two existing launch wrappers and their defaults were not changed.
macos_four_point:
  lifecycle: FULL_RESTART
  results:
    - experiment: EXP-025
      keyframe: task_start
      ros_domain_id: 231
      accepted: true
      position_error_mm: 1.175
      monotonic_readback_skew_ms: 4.265
      evidence: /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/live/exp-025-macos-yolo-task-start-run-01
    - experiment: EXP-026
      keyframe: cup_test_forward_5cm
      ros_domain_id: 232
      accepted: true
      position_error_mm: 1.146
      monotonic_readback_skew_ms: 5.941
      evidence: /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/live/exp-026-macos-yolo-cup-test-forward-5cm-run-01
    - experiment: EXP-027b
      keyframe: cup_test_left_5cm
      ros_domain_id: 180
      accepted: true
      position_error_mm: 1.120
      monotonic_readback_skew_ms: 6.462
      evidence: /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/live/exp-027b-macos-yolo-cup-test-left-5cm-run-01
    - experiment: EXP-028
      keyframe: cup_test_right_5cm
      ros_domain_id: 181
      accepted: true
      position_error_mm: 1.172
      monotonic_readback_skew_ms: 11.077
      evidence: /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/live/exp-028-macos-yolo-cup-test-right-5cm-run-01
linux_four_point:
  lifecycle: FULL_RESTART
  results:
    - experiment: EXP-037
      keyframe: task_start
      ros_domain_id: 182
      accepted: true
      position_error_mm: 1.157
      monotonic_readback_skew_ms: 1501.980
      evidence: /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-037-linux-yolo-task-start-run-01
    - experiment: EXP-038
      keyframe: cup_test_forward_5cm
      ros_domain_id: 183
      accepted: true
      position_error_mm: 1.161
      monotonic_readback_skew_ms: 0.978
      evidence: /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-038-linux-yolo-cup-test-forward-5cm-run-01
    - experiment: EXP-039
      keyframe: cup_test_left_5cm
      ros_domain_id: 184
      accepted: true
      position_error_mm: 1.130
      monotonic_readback_skew_ms: 0.956
      evidence: /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-039-linux-yolo-cup-test-left-5cm-run-01
    - experiment: EXP-040
      keyframe: cup_test_right_5cm
      ros_domain_id: 185
      accepted: true
      position_error_mm: 1.177
      monotonic_readback_skew_ms: 2002.239
      evidence: /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-040-linux-yolo-cup-test-right-5cm-run-01
common_four_point_outcome:
  - All eight valid runs recorded machine_accepted true and runtime_exit_code zero.
  - Actual devices were MPS on macOS and CUDA in Docker on ai-station; CPU fallback remained disabled.
  - Perception retained source_frame_id task_camera_frame while CUP_POSE_PUBLISHED and dynamic input used world.
  - MuJoCo readback used clock_domain mujoco_sim and Planning Scene used system_wall; collection skew used only host-monotonic timestamps.
  - Every final cup state was stable, supported by the table, free of fingertip contact, and matched the Planning Scene with an empty attached-object set.
  - Owned cleanup completed with no remaining process, ROS node, or workflow-labelled container.
invalid_and_diagnostic_records:
  - Parent commit d7d155b7 passed the ai-station YOLO four-point batch in EXP-018 through EXP-021 with 1.125 to 1.173 mm final position error. Those results remain historical and were rerun as EXP-037 through EXP-040 after the final publisher-lifetime fix.
  - EXP-022 is INVALID because the macOS dynamic loader environment omitted libmujoco; it did not enter qualification.
  - EXP-023 passed macOS task_start on parent commit d7d155b7. EXP-024 is a VALID macOS/MPS failure on that commit: perception published once and exited before the dynamic best-effort subscriber received the pose. The final commit removes --once only from the new E2E launch and keeps the publisher alive until supervisor teardown.
  - EXP-027 is INVALID because ROS_DOMAIN_ID 233 exceeds the Fast DDS port range. EXP-027b used a fresh root and legal domain 180.
  - candidate-1614eb84-r1 and r2 are retained invalid build attempts; candidate r3 built but its test environment exposed old support-package provenance, yielding 1675 passed and one provenance failure. Candidate r4 rebuilt both source and support packages and passed.
  - ai-station scratch exp-032 stopped at collection because the script replaced overlay PYTHONPATH; exp-033 ran 1676 tests with one provenance failure. Neither is counted as a passing gate.
open_gates:
  - No PickPlace-qualified Grounded SAM bundle is registered for macOS or ai-station, so the two Grounded SAM four-point cells remain blocked.
  - The two-cup TARGET_AMBIGUOUS and live MoveIt abort cases remain unproven; the actual Planner rejection case remains valid from EXP-015.
  - Per-configuration five-consecutive-success, GUI video, and learner explanation gates remain incomplete.
retained_runs:
  - /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad
archived_runs: []
deletion_candidates:
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/candidate-1614eb84-r1
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/candidate-1614eb84-r2
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/candidate-1614eb84-r3
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/scratch/exp-030-pytest-current
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/scratch/exp-031-pytest-current
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/scratch/exp-032-pytest-current
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/scratch/exp-033-pytest-current
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/scratch/exp-035-pytest-current
deletion_performed: false
conclusion: The exact current commit qualifies YOLO-Seg on both required platforms at all four registered points and preserves the legacy entry behavior. The full dual-model release matrix is still incomplete because the Grounded SAM artifact and the remaining stability, negative, video, and learner gates are not qualified.
next_experiment: Register a PickPlace-qualified Grounded SAM bundle before opening either Grounded SAM four-point batch.
```

## Checkpoint CP-014 — Correct Grounded SAM qualification inventory

```yaml
checkpoint_id: CP-014
status: DOCUMENTATION_CORRECTION_VALID
prior_checkpoint: CP-013
source_commit_under_review: 1c7ff19116d7ffe056938513d61b803c4db615c0
trigger: User reported that Grounded SAM had already completed PickPlace testing.
observed:
  - docs/reports/grounded-sam-yolo-seg-benchmark-report.md records the frozen DINO epoch 1 plus SAM decoder epoch 4 bundle with manifest SHA256 b55bb601d311407df8f9f25d9da18649f6bd78ac1299148bde0d07f7cfdfed05 and threshold-lock SHA256 b02e3be2814d03b954bdcb73b2f79f8b91d1227c6476fcc82695cabb91f50278.
  - The V5-T005 ledger records Linux CUDA, current Mac MPS, and mac-mini MPS four-point MuJoCo PickPlace acceptance at 4/4 for that common bundle identity.
  - The bundle is pinned in private Hugging Face repository zjumty/so101-grounded-sam-cup-pickplace at revision 52b8334358e5ff11f94f10f7c14b1697ef44d964 and passed fresh remote payload readback.
root_cause:
  - This task inventoried the base v2 scipy-lock bundle and an earlier epoch5 candidate that retained a historical COCO100 NO_GO result.
  - It omitted the later selected epoch1 plus epoch4 production bundle and the decision that COCO100 remained a disclosed generalization risk rather than this near-workspace promotion gate.
correction:
  - Grounded SAM has a registered PickPlace-qualified production bundle.
  - The open requirement is to stage and verify the pinned bundle on each current host, then run it through so101_mujoco_text_pick_agent_e2e.launch.py at the current source commit.
  - Prior Grounded SAM four-point results qualify the model and existing perception entry; they do not by themselves qualify the new Text-Agent event, acceptance, and cleanup path.
supersedes:
  - CP-013 open_gates statement that no PickPlace-qualified Grounded SAM bundle is registered.
  - CP-013 conclusion that the Grounded SAM artifact is not qualified.
  - CP-013 next_experiment instruction to create or register a new qualified bundle.
disproven_routes:
  - Treating the epoch5 COCO100-NO_GO candidate as the latest selected production bundle.
  - Treating absence from this task's initial model inventory as absence from the repository's existing qualification ledger.
current_open_gates:
  - Grounded SAM macOS/MPS and ai-station/CUDA runs through the new Text-Agent E2E entry remain NOT_RUN.
  - Five-consecutive-success, valid two-cup ambiguity, live MoveIt abort, GUI video, and learner explanation gates remain incomplete.
retained_runs:
  - /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad
archived_runs: []
deletion_performed: false
next_experiment: Verify fresh local and ai-station checkouts of Hugging Face revision 52b8334358e5ff11f94f10f7c14b1697ef44d964, register absolute model roots, and run the two current Grounded SAM E2E four-point batches.
```

## Checkpoint CP-015 — Grounded SAM E2E preflight complete

```yaml
checkpoint_id: CP-015
status: GO_GROUNDED_SAM_E2E
prior_checkpoint: CP-014
source:
  worktree: /private/tmp/so101-text-agent-multibackend-e2e-01a07c7f
  branch: codex/text-agent-multibackend-e2e
  head: 7cfc5f7b39637147647c385705f34b16a75c0918
  runtime_code_commit: 1614eb84ef73ad36f050368a65ef40ddae3ea78f
  submodule: 71bc9346cf93d6227a6678fcacf63f3e18acfcba
model:
  manifest_sha256: b55bb601d311407df8f9f25d9da18649f6bd78ac1299148bde0d07f7cfdfed05
  threshold_lock_sha256: b02e3be2814d03b954bdcb73b2f79f8b91d1227c6476fcc82695cabb91f50278
  local_root: /private/tmp/so101-debug-v5-t005-local-mac-r782-TwxaqX/model/bundle
  linux_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/models/grounded-sam-dino-nonpenetrating-epoch1-sam-decoder-epoch4-r1
  payload_readback: PASS_11_OF_11_BOTH_HOSTS
platforms:
  macos: {runtime: host, device: mps, fallback: false, locked_dependencies: PASS}
  linux: {runtime: host, device: cuda, fallback: false, locked_dependencies: PASS}
observed:
  - The local Ollama endpoint lists qwen3.5:4b.
  - Sandboxed MPS discovery is false, while the required unsandboxed probe reports torch 2.13.0, MPS built true and MPS available true.
  - The existing Linux candidate rgbd_object_pose shebang is /usr/bin/python3, which lacks torch and transformers.
  - The locked Linux Grounded SAM Python has torch 2.13.0+cu130, transformers 4.56.2, CUDA true, and NVIDIA GeForce RTX 5080; it requires ROS Python paths from the sourced Jazzy environment.
  - No pre-existing Grounded SAM E2E result roots selected below exist.
preserved_processes:
  - ai-station tmux sessions codex, microduck-policy-queue, and so101-exp079-linux-r3
  - unrelated ai-station Microduck GPU process if still present at each run preflight
local_process_probe: unavailable in the managed sandbox; each unsandboxed run must perform a scoped preflight and postflight.
next_experiment: EXP-041
```

## Experiment EXP-041 — Linux locked-Python E2E overlay

```yaml
experiment_id: EXP-041
status: PLANNED
prior_experiment: EXP-040
hypothesis: Rebuilding only so101_demo_py from exact runtime commit 1614eb84 with the existing locked Grounded SAM Python produces an isolated E2E prefix that can import both ROS Jazzy and the frozen ML dependency set without changing product source.
prediction: The installed rgbd_object_pose shebang names /data/work/venvs/so101-grounded-sam/bin/python, source and support provenance remain exact, and host CUDA/model preflight passes.
single_variable: Python interpreter used to install so101_demo_py; product source, support underlay, model and policy remain unchanged.
lifecycle: ISOLATED_STACK
preconditions:
  - /data/work/ws_moveit/.worktrees/text-agent-e2e-e6057016 is exact 1614eb84 and clean.
  - Existing candidate-1614eb84-r4 provides the already tested exact so101_mujoco_support underlay.
success_criteria:
  - Build exits zero into a previously nonexistent candidate-1614eb84-grounded-sam prefix.
  - Installed entrypoint uses the locked Python and imports rclpy, torch and transformers with CUDA available.
failure_criteria:
  - Build or import fails, source provenance drifts, or the installed entrypoint uses system Python.
invalid_criteria:
  - Existing install directories are overwritten or an unrelated process is changed.
provenance:
  source_commit: 1614eb84ef73ad36f050368a65ef40ddae3ea78f
  install_overlay: /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/candidate-1614eb84-grounded-sam/install
  runtime_executable: /data/work/venvs/so101-grounded-sam/bin/python /usr/bin/colcon
  ros_domain_id: NOT_USED_BUILD_ONLY
  gz_partition: NOT_USED_BUILD_ONLY
commands:
  - command: Source ROS Jazzy and candidate-1614eb84-r4, then drive /usr/bin/colcon with /data/work/venvs/so101-grounded-sam/bin/python to build only so101_demo_py into candidate-1614eb84-grounded-sam.
    exit_code: PENDING
observed: []
inferred: []
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/candidate-1614eb84-grounded-sam
decision: PENDING
next_experiment: EXP-042
```

## Experiments EXP-042 through EXP-045 — Linux Grounded SAM E2E four-point batch

```yaml
batch_status: PLANNED
prior_experiment: EXP-041
common:
  lifecycle: FULL_RESTART
  source_commit: 1614eb84ef73ad36f050368a65ef40ddae3ea78f
  install_overlay: /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/candidate-1614eb84-grounded-sam/install
  runtime_executable: installed so101_mujoco_text_pick_agent_e2e plus locked-Python rgbd_object_pose
  model_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/models/grounded-sam-dino-nonpenetrating-epoch1-sam-decoder-epoch4-r1
  manifest_sha256: b55bb601d311407df8f9f25d9da18649f6bd78ac1299148bde0d07f7cfdfed05
  thresholds: {box: 0.5, text: 0.5, duplicate_iou: 0.85, max_candidates: 16, sam_quality: 0.5, min_mask_pixels: 64, max_mask_area_ratio: 0.50}
  device: cuda
  allow_cpu_fallback: false
  perception_runtime: host
  planner: {provider: ollama, model: qwen3.5:4b, transport: task-owned reverse tunnel}
  success_criteria:
    - Strict workflow reaches E2E_ACCEPTED, machine_accepted is true, runtime and launch exit zero, and owned cleanup is complete.
    - One Grounded SAM target, fresh world cup pose, DONE/19, physical lift/transport/release, stable table support, no final fingertip contact, empty attached set, matching Planning Scene world pose, actual CUDA, and no fallback.
  failure_criteria: Any model, event, runtime, physical, Planning Scene, evidence, cleanup, or exit-code gate fails.
  invalid_criteria: Source/model/interpreter/provider identity drifts, run root or domain is not fresh, or unrelated state contaminates the run.
  command: Run the registered Linux Grounded SAM evidence wrapper with experiment id, keyframe and ROS domain shown below.
runs:
  - {experiment_id: EXP-042, keyframe: task_start, ros_domain_id: 186, gz_partition: text-e2e-linux-gsam-042, run_root: /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-042-linux-grounded-sam-task-start-run-01, status: PLANNED}
  - {experiment_id: EXP-043, keyframe: cup_test_forward_5cm, ros_domain_id: 187, gz_partition: text-e2e-linux-gsam-043, run_root: /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-043-linux-grounded-sam-forward-run-01, status: PLANNED}
  - {experiment_id: EXP-044, keyframe: cup_test_left_5cm, ros_domain_id: 188, gz_partition: text-e2e-linux-gsam-044, run_root: /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-044-linux-grounded-sam-left-run-01, status: PLANNED}
  - {experiment_id: EXP-045, keyframe: cup_test_right_5cm, ros_domain_id: 189, gz_partition: text-e2e-linux-gsam-045, run_root: /data/work/so101-evidence/text-agent-e2e/20260907T185218Z-197fa789-046f-4bd6-b029-641673ac17ad/live/exp-045-linux-grounded-sam-right-run-01, status: PLANNED}
```

## Experiments EXP-046 through EXP-049 — macOS Grounded SAM E2E four-point batch

```yaml
batch_status: PLANNED
prior_experiment: EXP-045
common:
  lifecycle: FULL_RESTART
  source_commit: 1614eb84ef73ad36f050368a65ef40ddae3ea78f
  install_overlay: /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/candidate-1614eb84-macos/install
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python
  model_root: /private/tmp/so101-debug-v5-t005-local-mac-r782-TwxaqX/model/bundle
  manifest_sha256: b55bb601d311407df8f9f25d9da18649f6bd78ac1299148bde0d07f7cfdfed05
  thresholds: {box: 0.5, text: 0.5, duplicate_iou: 0.85, max_candidates: 16, sam_quality: 0.5, min_mask_pixels: 64, max_mask_area_ratio: 0.50}
  device: mps
  allow_cpu_fallback: false
  perception_runtime: host
  planner: {provider: ollama, model: qwen3.5:4b, transport: localhost}
  success_criteria:
    - Strict workflow reaches E2E_ACCEPTED, machine_accepted is true, runtime and launch exit zero, and owned cleanup is complete.
    - One Grounded SAM target, fresh world cup pose, DONE/19, physical lift/transport/release, stable table support, no final fingertip contact, empty attached set, matching Planning Scene world pose, actual MPS, and no fallback.
  failure_criteria: Any model, event, runtime, physical, Planning Scene, evidence, cleanup, or exit-code gate fails.
  invalid_criteria: Source/model/interpreter/provider identity drifts, run root or domain is not fresh, MPS is unavailable outside the sandbox, or unrelated state contaminates the run.
  command: Run the registered macOS Grounded SAM evidence wrapper with experiment id, keyframe and ROS domain shown below.
runs:
  - {experiment_id: EXP-046, keyframe: task_start, ros_domain_id: 190, gz_partition: text-e2e-macos-gsam-046, run_root: /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/live/exp-046-macos-grounded-sam-task-start-run-01, status: PLANNED}
  - {experiment_id: EXP-047, keyframe: cup_test_forward_5cm, ros_domain_id: 191, gz_partition: text-e2e-macos-gsam-047, run_root: /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/live/exp-047-macos-grounded-sam-forward-run-01, status: PLANNED}
  - {experiment_id: EXP-048, keyframe: cup_test_left_5cm, ros_domain_id: 192, gz_partition: text-e2e-macos-gsam-048, run_root: /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/live/exp-048-macos-grounded-sam-left-run-01, status: PLANNED}
  - {experiment_id: EXP-049, keyframe: cup_test_right_5cm, ros_domain_id: 193, gz_partition: text-e2e-macos-gsam-049, run_root: /tmp/so101-debug-text-agent-e2e-impl-20260907-01a07c7f/live/exp-049-macos-grounded-sam-right-run-01, status: PLANNED}
```
