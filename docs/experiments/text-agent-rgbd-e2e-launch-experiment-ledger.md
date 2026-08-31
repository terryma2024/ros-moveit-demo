# Text Agent RGB-D end-to-end launch experiment ledger

```yaml
task_id: so101-text-agent-rgbd-e2e-launch
goal: Add one MuJoCo launch for natural-language planning, RGB-D perception, dynamic pick-place, and owned cleanup, then validate all four preset positions on the local Mac.
success_contract: Four independent FULL_RESTART runs at task_start, cup_test_forward_5cm, cup_test_left_5cm, and cup_test_right_5cm satisfy text-agent, RGB-D, controller, MoveIt, MuJoCo physical, visual, exit, and cleanup gates.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo
branch: main
base_commit: 03887b424797a2f644156725742077b970100a0f
current_commit: 15ab84162083c591b0e531222434a4c85243d0ec
evidence_root: /tmp/so101-debug-text-agent-e2e-launch-20260831
confirmed_conclusions:
  - DESIGN-001: The existing perception launch already owns MuJoCo, controllers, MoveIt, camera TF, RGB-D perception, and dynamic pick-place; the approved design adds a separate public launch that substitutes text_pick_agent for the direct dynamic workflow.
  - DESIGN-001: DeepSeek and Ollama remain external services; the launch inherits provider configuration but does not own either service.
  - PROV-001: Local main is 03887b424797a2f644156725742077b970100a0f with pinned mujoco_ros2_control 71bc9346cf93d6227a6678fcacf63f3e18acfcba.
  - PROV-001: A pre-existing local MuJoCo stack and rgbd_cup_pose process tree is present and must not be stopped or reused without ownership confirmation.
  - PROV-001: ai-station remains at e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4 with its untracked RGB-D ledger and codex/codex-cua sessions preserved.
  - CP-STATIC-GREEN: Focused source tests passed 90/90, the full package suite passed 792/792, and the installed overlay exposes the new launch with all 13 arguments.
  - CP-STATIC-GREEN: Missing skip_confirmation fails before evidence creation, leaves domain 221 empty, and returns launch status 1.
  - CP-MAC-VISIBLE-BLOCKED: The current macOS login context reports CGMainDisplayID=0 and zero active CoreGraphics displays; every visible launch reaches the MuJoCo main-thread UI boundary and then exits -11 in glfwGetVideoMode before Text Agent or motion starts.
disproven_routes:
  - DESIGN-001: A shell wrapper is rejected because it splits process ownership, exit status, and evidence provenance.
  - DESIGN-001: Adding workflow selection to the existing perception launch is rejected to preserve its public contract.
  - CP-STATIC-GREEN: ROS_DOMAIN_ID values 240 through 244 are invalid on the local Fast DDS configuration because domain IDs above 232 overflow its port calculation; static and live domains were changed to 221 through 225.
open_hypotheses:
  - Each of the four FULL_RESTART runs can complete the full natural-language-to-physical chain on the local Mac with headless=true and sensor_rendering=true while the visible-only gate remains environment-blocked.
latest_checkpoint: CP-MAC-VISIBLE-BLOCKED
next_experiment: Run a fresh task_start FULL_RESTART functional acceptance in ROS domain 222 with headless=true and sensor_rendering=true.
```

## DESIGN-001

```yaml
design_id: DESIGN-001
status: APPROVED_IN_WRITING
date: 2026-08-31
design: docs/superpowers/specs/2026-08-31-text-agent-rgbd-e2e-launch-design.md
single_variable: Add one dedicated text-agent RGB-D launch while leaving the existing perception launch unchanged.
evidence:
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/design/local-provenance.log
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/design/local-domain-231-nodes-final.log
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/design/local-processes.log
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/design/local-ollama-ps.log
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/design/ai-station-provenance.log
decision: KEEP
```

## CP-001

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: The dedicated launch can compose the existing proven components without changing their internal contracts.
working_tree_status: Design spec and this ledger are new; no pre-existing local source changes were observed at task start.
owned_processes: NONE
preserved_processes:
  - Local ros2 launch PID 79408 and descendant MuJoCo/MoveIt/RGB-D processes 79419, 79423, 80039, and 80040.
  - ai-station codex and codex-cua tmux sessions and its untracked RGB-D experiment ledger.
confirmed_conclusions:
  - Approved architecture is recorded in DESIGN-001.
disproven_routes:
  - Shell wrapper and modification of the existing perception launch public contract.
open_risks:
  - Local pre-existing runtime ownership must be resolved before any FULL_RESTART acceptance run.
  - Ollama currently reports no loaded model in ollama ps; provider health must be rechecked before acceptance.
next_command: User reviews the written spec; after approval, create the implementation plan before editing production code.
evidence_disposition:
  retained:
    - /tmp/so101-debug-text-agent-e2e-launch-20260831/design
  archived: NONE
  deletion_candidates: NONE
```

## CP-002

```yaml
checkpoint_id: CP-002
date: 2026-08-31
last_valid_experiment: DESIGN-001
current_hypothesis: The approved design can be implemented as six TDD tasks without changing the existing perception launch contract.
written_design_approval: CONFIRMED_BY_USER
implementation_plan: docs/superpowers/plans/2026-08-31-text-agent-rgbd-e2e-launch.md
source_commit: 5396e2e7e1a07330a3872712e25bbdb8931fc5a7
owned_processes: NONE
preserved_processes:
  - Local pre-existing MuJoCo and RGB-D process tree recorded in CP-001.
  - ai-station sessions and untracked ledger recorded in CP-001.
next_command: Select subagent-driven or inline plan execution, then begin the canonical installed execution identity RED test.
evidence_disposition:
  retained:
    - /tmp/so101-debug-text-agent-e2e-launch-20260831/design
  archived: NONE
  deletion_candidates: NONE
```

## CP-STATIC-GREEN

```yaml
checkpoint_id: CP-STATIC-GREEN
date: 2026-08-31
source_commit: b7518e6f99a11269a6e4b3f9b83ee95a1426520b
installed_prefix: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/so101_demo_py
focused_tests: 90 passed
full_package_tests: 792 passed
installed_launch_count: 7
installed_launch: so101_mujoco_text_pick_agent.launch.py
launch_argument_count: 13
fail_closed_smoke:
  ros_domain_id: 221
  launch_status: 1
  reason: text-agent launch requires skip_confirmation:=true
  evidence_directory_created: false
  remaining_nodes: 0
disproven_preflight:
  ros_domain_id: 240
  status: INVALID_ENVIRONMENT
  reason: Fast DDS reports that domain IDs above 232 produce a port number that is too high.
evidence:
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/static/focused-pytest.log
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/static/colcon-build.log
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/static/package-prefix.log
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/static/installed-launches.log
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/static/show-args.log
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/static/full-pytest.log
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/static/rejected-domain-221-launch.log
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/static/rejected-domain-221-status.log
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/static/domain-221-nodes.log
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/static/domain-240-repro.log
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/static/domain-221-control.log
owned_processes: NONE
next_command: Run provider and process-ownership preflight, then start task_start in domain 222.
evidence_disposition:
  retained:
    - /tmp/so101-debug-text-agent-e2e-launch-20260831/design
    - /tmp/so101-debug-text-agent-e2e-launch-20260831/static
  archived: NONE
  deletion_candidates: NONE
```

## EXP-MAC-VISIBLE-PREFLIGHT and CP-MAC-VISIBLE-BLOCKED

```yaml
checkpoint_id: CP-MAC-VISIBLE-BLOCKED
date: 2026-08-31
source_commit: 15ab84162083c591b0e531222434a4c85243d0ec
installed_prefix: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/so101_demo_py
ros_domain_id: 222
lifecycle: FULL_RESTART_PREFLIGHT
status: INVALID_ENVIRONMENT
attempts:
  - id: task_start
    result: INVALID_ENVIRONMENT
    first_bad_boundary: libmujoco.3.4.0.dylib was unavailable because the first runner did not load the repository direnv environment.
  - id: task_start_run2
    result: INVALID_ENVIRONMENT
    first_bad_boundary: visible MuJoCo exited -11 in glfwGetVideoMode before hardware initialization completed.
  - id: task_start_run3
    result: INVALID_RUNNER
    first_bad_boundary: the new Ghostty app instance restored windows but did not execute the supplied runner; no ROS process started.
  - id: task_start_run4
    result: INVALID_RUNNER
    first_bad_boundary: Terminal opened the runner in /tmp, so direnv did not load the repository environment and ros2 was unavailable; no ROS process started.
  - id: task_start_run5
    result: INVALID_ENVIRONMENT
    first_bad_boundary: after explicit checkout cd and complete environment loading, visible MuJoCo again exited -11 in glfwGetVideoMode before Text Agent, RGB-D perception, or motion started.
observed:
  - Both a Codex PTY and a task-owned Terminal GUI process reached the same glfwGetVideoMode failure.
  - system_profiler reports the Apple M5 GPU but no display entry.
  - CoreGraphics reports CGMainDisplayID=0 and CGActiveDisplayCount=0.
  - Domain 222 is empty after every failed preflight; no task-owned ROS process remains.
inferred:
  - The visible-only gate is blocked by the current no-active-display macOS environment rather than by the launch responsibility chain.
  - A headless functional matrix can still exercise Text Agent, rendered RGB-D, MoveIt, controllers, and MuJoCo physical outcome, but cannot satisfy the pre-registered exact-window gate.
evidence:
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/task_start
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/task_start_run2
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/task_start_run3
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/task_start_run4
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/task_start_run5
preserved_processes:
  - Pre-existing PIDs 79408, 79419, 79423, 80039, and 80040 remain untouched.
decision: KEEP_INVALID_AND_RUN_HEADLESS_FUNCTIONAL_MATRIX
next_experiment: Fresh task_start session in domain 222 with headless=true and sensor_rendering=true.
evidence_disposition:
  retained:
    - /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/task_start
    - /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/task_start_run2
    - /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/task_start_run3
    - /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/task_start_run4
    - /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/task_start_run5
  archived: NONE
  deletion_candidates: NONE
```
