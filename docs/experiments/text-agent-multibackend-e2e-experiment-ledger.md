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
  - The Grounded SAM base v2 scipy-lock bundle can exercise the backend contract, but no currently registered Grounded SAM bundle has PickPlace qualification evidence.
latest_checkpoint: CP-006
next_experiment: EXP-008
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
