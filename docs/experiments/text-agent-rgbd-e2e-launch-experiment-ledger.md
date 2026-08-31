# Text Agent RGB-D end-to-end launch experiment ledger

```yaml
task_id: so101-text-agent-rgbd-e2e-launch
goal: Add one MuJoCo launch for natural-language planning, RGB-D perception, dynamic pick-place, and owned cleanup, then validate all four preset positions on the local Mac.
success_contract: Four independent FULL_RESTART runs at task_start, cup_test_forward_5cm, cup_test_left_5cm, and cup_test_right_5cm satisfy text-agent, RGB-D, controller, MoveIt, MuJoCo physical, visual, exit, and cleanup gates.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo
branch: main
base_commit: 03887b424797a2f644156725742077b970100a0f
current_commit: 2cf66ed5fbcfed3da8bef917b4c9b7e6d5113a01
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
  - CP-LIVE-PROCESS-GREEN: text_pick_agent is a plain installed CLI and must be launched with ExecuteProcess so ROS launch does not append --ros-args.
  - CP-MAC-HEADLESS-FUNCTIONAL: Four independent DeepSeek FULL_RESTART runs completed the natural-language, rendered RGB-D, MoveIt, controller, MuJoCo physical, exit, and cleanup gates at all four preset positions.
  - CP-MAC-QWEN-FUNCTIONAL: With DEEPSEEK_API_KEY absent from the launch child and qwen3.5:4b warm in Ollama, an additional task_start run completed the same functional chain through the Ollama fallback.
disproven_routes:
  - DESIGN-001: A shell wrapper is rejected because it splits process ownership, exit status, and evidence provenance.
  - DESIGN-001: Adding workflow selection to the existing perception launch is rejected to preserve its public contract.
  - CP-STATIC-GREEN: ROS_DOMAIN_ID values 240 through 244 are invalid on the local Fast DDS configuration because domain IDs above 232 overflow its port calculation; static and live domains were changed to 221 through 225.
open_hypotheses:
  - The four visible FULL_RESTART qualification runs can be repeated when the macOS login context has an active CoreGraphics display.
latest_checkpoint: CP-FINAL-AUDIT
next_experiment: Restore an active macOS display and repeat all four runs with headless=false for exact-window visual qualification.
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

## CP-LIVE-PROCESS-GREEN

```yaml
checkpoint_id: CP-LIVE-PROCESS-GREEN
date: 2026-08-31
source_commit: 2cf66ed5fbcfed3da8bef917b4c9b7e6d5113a01
status: FIXED_AND_REGRESSION_TESTED
first_live_failure:
  run: /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/headless_task_start
  result: INVALID_PRODUCT
  first_bad_boundary: ROS Node appended --ros-args to the plain text_pick_agent CLI, so argparse rejected the command before planning, perception, or motion.
root_cause: text_pick_agent is an installed command-line workflow, not a ROS node; launch_ros.actions.Node always applies ROS CLI semantics.
change: Resolve the exact installed entrypoint and start it with launch.actions.ExecuteProcess while retaining launch-owned exit and teardown handlers.
red_green_evidence:
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/static/text-agent-plain-process-red.log
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/static/text-agent-plain-process-green.log
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/static/text-agent-launch-process-green.log
decision: KEEP
evidence_disposition:
  retained:
    - /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/headless_task_start
    - /tmp/so101-debug-text-agent-e2e-launch-20260831/static
  archived: NONE
  deletion_candidates: NONE
```

## CP-MAC-HEADLESS-FUNCTIONAL

```yaml
checkpoint_id: CP-MAC-HEADLESS-FUNCTIONAL
date: 2026-08-31
source_commit: 2cf66ed5fbcfed3da8bef917b4c9b7e6d5113a01
installed_prefix: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/so101_demo_py
lifecycle: FOUR_INDEPENDENT_FULL_RESTARTS
mode:
  headless: true
  sensor_rendering: true
  visual_qualification: NOT_SATISFIED
instruction: Pick the plastic cup. Apply no constraints.
planner:
  provider: deepseek
  model: deepseek-v4-flash
  fallback_used: false
  validated_command: {target_object: plastic_cup, action: pick, constraints: {}}
  confirmation_mode: skipped
runs:
  - keyframe: task_start
    ros_domain_id: 222
    evidence: /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/headless_task_start_run2
    session_id: text-e2e-headless-task-start-run2-20260831
    request_id: 49d9b9c6-c2ed-450c-bfde-54758dbb4fc4
    perceived_xyz_m: [0.01949905513971856, -0.28040477913291795, 0.165]
    rgbd: {width: 640, height: 480, full_points: 98078, cup_points: 141}
    dynamic: {status: DONE, transitions: 19, state_events: 18, motion_events: 7}
    final_xyz_m: [-0.07776387624460847, -0.2475368764937461, 0.16482891330851807]
    final_physics: {table_contact: true, left_contacts: 0, right_contacts: 0}
    planning_scene: {attached_ids: [], plastic_cup_primitives: 13}
    launch_status: 0
    post_cleanup_nodes: 0
  - keyframe: cup_test_forward_5cm
    ros_domain_id: 223
    evidence: /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/headless_forward
    session_id: text-e2e-headless-forward-20260831
    request_id: af61d6f4-f6ec-4ac1-924f-7a2719556fcf
    perceived_xyz_m: [0.01962362709282407, -0.33046010304848167, 0.165]
    rgbd: {width: 640, height: 480, full_points: 98078, cup_points: 168}
    dynamic: {status: DONE, transitions: 19, state_events: 18, motion_events: 7}
    final_xyz_m: [-0.07792698856416416, -0.24752272639551834, 0.16482335453386052]
    final_physics: {table_contact: true, left_contacts: 0, right_contacts: 0}
    planning_scene: {attached_ids: [], plastic_cup_primitives: 13}
    launch_status: 0
    post_cleanup_nodes: 0
  - keyframe: cup_test_left_5cm
    ros_domain_id: 224
    evidence: /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/headless_left
    session_id: text-e2e-headless-left-20260831
    request_id: 85fad7c1-c19b-4f96-acce-a62f170cd9d4
    perceived_xyz_m: [-0.030362306397919193, -0.28058726069557155, 0.165]
    rgbd: {width: 640, height: 480, full_points: 98135, cup_points: 378}
    dynamic: {status: DONE, transitions: 19, state_events: 18, motion_events: 7}
    final_xyz_m: [-0.07792410367976381, -0.2474694846362872, 0.16492354528282097]
    final_physics: {table_contact: true, left_contacts: 0, right_contacts: 0}
    planning_scene: {attached_ids: [], plastic_cup_primitives: 13}
    launch_status: 0
    post_cleanup_nodes: 0
  - keyframe: cup_test_right_5cm
    ros_domain_id: 225
    evidence: /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/headless_right
    session_id: text-e2e-headless-right-20260831
    request_id: ab51bba5-a26e-4834-b2f7-5b328ab77261
    perceived_xyz_m: [0.06963311309305363, -0.28051349578752416, 0.165]
    rgbd: {width: 640, height: 480, full_points: 98078, cup_points: 126}
    dynamic: {status: DONE, transitions: 19, state_events: 18, motion_events: 7}
    final_xyz_m: [-0.07792465204104866, -0.24755749935594762, 0.16477649409806938]
    final_physics: {table_contact: true, left_contacts: 0, right_contacts: 0}
    planning_scene: {attached_ids: [], plastic_cup_primitives: 13}
    launch_status: 0
    post_cleanup_nodes: 0
aggregate_result: 4/4 VALID_FUNCTIONAL
qualification_result: BLOCKED_VISUAL_ONLY
preserved_processes:
  - Pre-existing PIDs 79408, 79419, 79423, 80039, and 80040 were not used or signaled.
owned_processes: All task-owned launch and GUI-wrapper processes exited or were terminated by exact PID after invalid preflights.
evidence_disposition:
  retained:
    - /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/headless_task_start_run2
    - /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/headless_forward
    - /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/headless_left
    - /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/headless_right
    - /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/post-cleanup-domain-222
    - /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/post-cleanup-domain-223
    - /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/post-cleanup-domain-224
    - /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/post-cleanup-domain-225
  archived: NONE
  deletion_candidates: NONE
```

## CP-MAC-QWEN-FUNCTIONAL

```yaml
checkpoint_id: CP-MAC-QWEN-FUNCTIONAL
date: 2026-08-31
source_commit: 2cf66ed5fbcfed3da8bef917b4c9b7e6d5113a01
model: qwen3.5:4b
provider: ollama
deepseek_api_key_in_child: UNSET
first_attempt:
  evidence: /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/headless_qwen_task_start
  status: INVALID_PROVIDER_PREFLIGHT
  launch_status: 1
  reason: The cold Ollama model load exceeded the Text Agent default 12-second provider timeout, so the planner chain failed before RGB-D publication or motion.
provider_recovery: A direct qwen3.5:4b adapter call loaded the model; a second call completed inside the production timeout without changing source or provider configuration.
valid_attempt:
  ros_domain_id: 226
  evidence: /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/headless_qwen_task_start_run2
  session_id: text-e2e-headless-qwen-task-start-run2-20260831
  request_id: a8357713-f98b-41a0-b872-0ac84ffb06bb
  planner: {provider: ollama, model: qwen3.5:4b, fallback_used: true, latency_ms: 1627}
  perceived_xyz_m: [0.01949905513971856, -0.28040477913291795, 0.165]
  rgbd: {width: 640, height: 480, full_points: 98078, cup_points: 141}
  dynamic: {status: DONE, transitions: 19, state_events: 18, motion_events: 7}
  final_xyz_m: [-0.07777704634524335, -0.24756158640804266, 0.16482869648227444]
  final_physics: {table_contact: true, left_contacts: 0, right_contacts: 0}
  planning_scene: {attached_ids: [], plastic_cup_primitives: 13}
  launch_status: 0
result: VALID_FUNCTIONAL_EXTRA_PROVIDER_CHECK
evidence_disposition:
  retained:
    - /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/headless_qwen_task_start
    - /tmp/so101-debug-text-agent-e2e-launch-20260831/macos/headless_qwen_task_start_run2
  archived: NONE
  deletion_candidates: NONE
```

## CP-FINAL-AUDIT

```yaml
checkpoint_id: CP-FINAL-AUDIT
date: 2026-08-31
verified_source_commit: 2cf66ed5fbcfed3da8bef917b4c9b7e6d5113a01
full_package_tests:
  command: python3 -m pytest -q -p no:cacheprovider src/so101_demo_py/test
  environment: Repository direnv plus macOS dylib farm, source PYTHONPATH, and evidence-root ROS_HOME/ROS_LOG_DIR.
  result: 793 passed in 9.41s
build:
  command: colcon build --packages-select so101_demo_py --symlink-install
  result: 1 package finished; exit status 0
installed_readback:
  package_prefix: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/so101_demo_py
  launch: so101_mujoco_text_pick_agent.launch.py
  public_argument_count: 13
  preset_keyframes: [task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm]
cleanup_readback:
  task_owned_text_agent_or_launch_processes: 0
  preserved_preexisting_pids: [79408, 79419, 79423, 80039, 80040]
  deepseek_domains_222_to_225_nodes_after_exit: 0
  qwen_domain_226_nodes_after_exit: 0
result:
  implementation: PASS
  four_point_headless_functional: PASS_4_OF_4
  qwen_extra_functional: PASS
  visible_exact_window_qualification: BLOCKED_NO_ACTIVE_DISPLAY
evidence_disposition:
  retained:
    - /tmp/so101-debug-text-agent-e2e-launch-20260831
  archived: NONE
  deletion_candidates: NONE
```
