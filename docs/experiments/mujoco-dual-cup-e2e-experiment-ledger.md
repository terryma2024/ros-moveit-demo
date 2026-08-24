# MuJoCo dual-cup end-to-end experiment ledger

```yaml
task_id: so101-mujoco-dual-cup-e2e
goal: Demonstrate one physical MuJoCo pick-place with fixed_cup_pick_place and one with dynamic_cup_pick_place on the local Apple Silicon host, retaining numeric and visual evidence.
success_contract: Each executable must consume its declared strategy input, execute the complete physical workflow, exit zero, prove controller motion and MuJoCo cup transport/release/final placement, prove MoveIt attachment lifecycle convergence, and retain fresh visual evidence. A single success is a demonstration, not a five-run stability qualification.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo
branch: main
base_commit: 5407592100823bcfa43138611f8de6b0de0c93f8
current_commit: 5407592100823bcfa43138611f8de6b0de0c93f8
evidence_root: /Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z
evidence_root_exception: The repository-preferred /data/work path cannot exist because the local macOS root volume is read-only; the user explicitly approved the equivalent persistent ~/work root.
confirmed_conclusions:
  - Direct package pytest reached 248 passing tests after the dynamic execute implementation, and package build/install discovery passes.
  - The dylib farm supports the interactive direnv shell but does not repair DYLD stripping in colcon test children; LOCAL-ENV-001.
  - fixed_cup_pick_place completed one physical MuJoCo pick-place with all nine phases, physical final-state gates, Planning Scene detach/world-object gates, and three visually inspected screenshots; EXP-004.
  - dynamic_cup_pick_place completed one headless physical MuJoCo pick-place from a fresh topic-derived cup pose, reached DONE, and passed physical, Planning Scene, and controller gates; EXP-006.
  - dynamic_cup_pick_place completed a second physical MuJoCo pick-place in the native viewer, reached DONE after the release-retreat ACM repair, and passed numeric, Planning Scene, controller, and three-screenshot visual gates; EXP-008.
disproven_routes:
  - Rebuilding the dylib farm does not fix colcon test because the required dylib is already present and the failing boundary is child-process environment propagation; LOCAL-ENV-001.
  - Treating dynamic plan-only as an end-to-end success is invalid because it sends no trajectory, gripper, or physical-world command; source inspection before EXP-001.
open_hypotheses:
  - NONE for the requested one-run-per-executable demonstration; repeated-run stability remains a separate qualification scope.
latest_checkpoint: CP-008
next_experiment: NONE_REQUIRED_FOR_SINGLE_RUN_ACCEPTANCE
```

## LOCAL-ENV-001

```yaml
experiment_id: LOCAL-ENV-001
status: VALID
lifecycle: ISOLATED_STACK
scope: Local macOS environment audit only; no pick-place execute.
evidence_root: /tmp/so101-debug-local-mujoco-env-M6lzDQ
commands:
  - command: eval "$(direnv export zsh)"; colcon build --packages-select so101_demo_py --symlink-install --event-handlers console_direct+
    exit_code: 0
  - command: ROS_LOG_DIR=<audit-root>/ros-log python3 -m pytest src/so101_demo_py/test -q
    exit_code: 0
observed:
  - Build completed for one package and the installed prefix exposes fixed_cup_pick_place and dynamic_cup_pick_place.
  - Direct pytest passed 236 tests.
  - colcon test collection is invalid on this host because its child loses DYLD_LIBRARY_PATH and cannot load librosidl_typesupport_c.dylib.
  - No physical workflow was started or counted.
conclusion: The Python package and installed overlay are build-ready. Live MuJoCo/MoveIt/controller readiness remains unproven until EXP-001.
decision: KEEP
next_experiment: EXP-001
```

## EXP-001

```yaml
experiment_id: EXP-001
status: VALID
prior_experiment: LOCAL-ENV-001
hypothesis: The installed local MuJoCo stack can start in an isolated ROS domain and expose healthy controllers, joint feedback, simulation evidence, MoveIt planning services, and an execute action without starting a workflow.
prediction: All required nodes/services/actions/topics appear, the three controllers are active, simulation evidence carries the requested session ID and reset epoch 0, and no duplicate pre-existing stack is present.
single_variable: Start the installed stack without a pick-place workflow.
lifecycle: ISOLATED_STACK
preconditions:
  - No existing move_group, MuJoCo ros2_control_node, fixed_cup_pick_place, or dynamic_cup_pick_place process is active.
  - Source commit and installed package prefix match this ledger.
  - ROS_DOMAIN_ID is 173 and GZ_PARTITION is not applicable to MuJoCo.
success_criteria:
  - MuJoCo ros2_control_node and MoveIt stay alive for the complete probe.
  - joint_state_broadcaster, arm_controller, and gripper_controller are active.
  - /joint_states and /so101/simulation/evidence each produce a fresh sample.
  - /plan_kinematic_path and /execute_trajectory are available.
failure_criteria:
  - A required process exits or any required controller/service/action/topic is absent.
invalid_criteria:
  - A pre-existing process shares ROS_DOMAIN_ID 173 or provenance does not match the installed overlay.
provenance:
  source_commit: 5407592100823bcfa43138611f8de6b0de0c93f8
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install
  runtime_executable: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/so101_demo_py
  ros_domain_id: 173
  gz_partition: NOT_APPLICABLE
commands:
  - command: ROS_DOMAIN_ID=173 ros2 launch so101_demo_py so101_mujoco.launch.py run_mode:=execute execute:=true headless:=true session_id:=dual-cup-smoke-20260824 readiness_timeout_s:=90
    exit_code: 0
observed:
  - No pre-existing MuJoCo, MoveIt, RViz, fixed_cup_pick_place, or dynamic_cup_pick_place process was found; pgrep matched only the probe shell.
  - Installed prefixes for so101_demo_py, mujoco_ros2_control, and so101_mujoco_support all resolve under /Users/matianyi/Projects/robot_demo_001/moveit-demo/install.
  - arm_controller, gripper_controller, and joint_state_broadcaster were active.
  - /plan_kinematic_path and /execute_trajectory were present.
  - Fresh /joint_states contained joints 1 through 6.
  - Fresh /so101/simulation/evidence reported session dual-cup-smoke-20260824, reset_epoch 0, publisher_sequence 4282, simulation_step 23259, and a stationary supported cup at [0.020000000000000018, -0.28, 0.16480156647042168].
inferred:
  - The existing installed fixed workflow may proceed to a fresh full-restart run; this probe did not execute any motion.
conclusion: The local MuJoCo, MoveIt, controller, joint-feedback, and atomic-evidence stack is runtime-ready for the fixed executable.
evidence:
  - /Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z/exp-001/launch.log sha256=78bcf39ffc791cf7af62057b837793f932b752b51dbbdb4119eb7bdb6729109f size=32148
  - /Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z/exp-001/probe.log sha256=826a29f76db41c42351afec8a2f6afc4d4128663336ac25b06c31b7eb3bbe9f4 size=15504
decision: KEEP
next_experiment: EXP-002
```

## EXP-002

```yaml
experiment_id: EXP-002
status: INVALID
prior_experiment: EXP-001
hypothesis: On a fresh local MuJoCo stack, the installed fixed_cup_pick_place executable can complete the qualified physical workflow and leave the plastic cup released, supported, stable, inside the target region, with MoveIt detached and controllers healthy.
prediction: The CLI exits zero with status DONE, all nine qualified phases pass, numeric physical outcome and Planning Scene gates pass, and fresh baseline/motion/final screenshots visibly show the cup moved from pick to place.
single_variable: Start fixed_cup_pick_place with the committed light_cup_wall_pick/v1 MuJoCo policy.
lifecycle: FULL_RESTART
preconditions:
  - EXP-001 stack is fully stopped and no competing MuJoCo/MoveIt process exists.
  - A fresh GUI-enabled stack starts with session fixed-cup-e2e-20260824, reset epoch 0, ROS_DOMAIN_ID 174, and the current installed overlay.
  - Scene setup succeeds and the initial cup is supported at the canonical pick pose.
success_criteria:
  - fixed_cup_pick_place exits 0 and its live-runtime manifest status is DONE with all nine expected phases.
  - Final MuJoCo samples prove release epoch consistency, table support, no gripper contact, stable pose, and target-region membership.
  - MoveIt attached-object IDs are empty and plastic_cup is restored to the world scene.
  - Controllers remain active and joint/TCP evidence changes consistently with the workflow.
  - Fresh baseline, in-motion, and final screenshots are retained and visually inspected.
failure_criteria:
  - Any qualified phase exits nonzero, evidence validation fails, final physical/scene state fails, or the visible cup is not at the place region.
invalid_criteria:
  - Duplicate stack, wrong session/reset epoch/overlay, missing screenshot, or evidence capture failure.
provenance:
  source_commit: 5407592100823bcfa43138611f8de6b0de0c93f8
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install
  runtime_executable: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/so101_demo_py/lib/so101_demo_py/fixed_cup_pick_place
  ros_domain_id: 174
  gz_partition: NOT_APPLICABLE
commands:
  - command: ROS_DOMAIN_ID=174 ros2 launch so101_demo_py so101_mujoco.launch.py run_mode:=execute execute:=true headless:=false session_id:=fixed-cup-e2e-20260824
    exit_code: 0
  - command: ROS_DOMAIN_ID=174 ros2 run so101_demo_py fixed_cup_pick_place --backend mujoco --run-mode execute --execute --session-id fixed-cup-e2e-20260824 --expected-reset-epoch 0 --evidence-root <evidence-root>/exp-002/fixed-run --motion-policy <installed-share>/config/policies/light_cup_wall_pick/v1/mujoco.yaml --contact-policy <installed-share>/config/contact_calibration.yaml
    exit_code: PENDING
observed:
  - Before workflow start, ros2_control_node reported Timed out waiting to start simulation rendering and failed hardware initialization.
  - The resolved runtime was /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/mujoco_ros2_control/lib/mujoco_ros2_control/ros2_control_node with SHA256 271fde4fad04d1cd1ae39c4f3309dee3979ed23e2738bf9f1f71d615bc98608c.
  - The pinned fork executable at /Users/matianyi/ros2_jazzy/ws_mujoco_ros2_control_fork/install/lib/mujoco_ros2_control/ros2_control_node has SHA256 c4eed0c172ef4cd831e1f3115aa427c43269095c5d9f680da00fd74393f51217 and contains the Apple main-thread UI path.
  - No robot motion or fixed_cup_pick_place process started.
inferred:
  - The GUI failure is attributable to stale package shadowing, not the fixed workflow.
conclusion: Invalid environment provenance. The current repo overlay shadowed the pinned fork binary required for native macOS viewer startup.
evidence:
  - /Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z/exp-002
decision: REPEAT
next_experiment: EXP-003
```

## EXP-003

```yaml
experiment_id: EXP-003
status: VALID
prior_experiment: EXP-002
hypothesis: Prepending the pinned fork merge-install to AMENT_PREFIX_PATH selects the Apple-main-thread ros2_control_node and permits native MuJoCo viewer startup without changing the demo package overlay.
prediction: ros2 pkg prefix mujoco_ros2_control resolves to /Users/matianyi/ros2_jazzy/ws_mujoco_ros2_control_fork/install, the viewer opens, hardware initializes once, controllers become active, and a fresh baseline screenshot can be retained before any motion.
single_variable: Prepend /Users/matianyi/ros2_jazzy/ws_mujoco_ros2_control_fork/install to AMENT_PREFIX_PATH.
lifecycle: FULL_RESTART
preconditions:
  - EXP-002 stack is stopped and no competing process exists.
  - so101_demo_py remains resolved from /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/so101_demo_py.
  - ROS_DOMAIN_ID is 175 and session ID is fixed-cup-e2e-20260824-r2.
success_criteria:
  - Native MuJoCo viewer starts and is visible through fresh Computer Use state.
  - All three controllers become active and the stack remains alive.
  - Baseline screenshot is saved before motion.
failure_criteria:
  - Viewer startup timeout, hardware initialization failure, missing controllers, or absent GUI.
invalid_criteria:
  - Wrong mujoco_ros2_control prefix, duplicate process, or screenshot capture failure.
provenance:
  source_commit: 5407592100823bcfa43138611f8de6b0de0c93f8
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install plus pinned fork first in AMENT_PREFIX_PATH
  runtime_executable: /Users/matianyi/ros2_jazzy/ws_mujoco_ros2_control_fork/install/lib/mujoco_ros2_control/ros2_control_node
  ros_domain_id: 175
  gz_partition: NOT_APPLICABLE
commands:
  - command: AMENT_PREFIX_PATH=<pinned-fork-first> ROS_DOMAIN_ID=175 ros2 launch so101_demo_py so101_mujoco.launch.py run_mode:=execute execute:=true headless:=false session_id:=fixed-cup-e2e-20260824-r2
    exit_code: RUNNING_STACK_OWNER
observed:
  - mujoco_ros2_control resolved to /Users/matianyi/ros2_jazzy/ws_mujoco_ros2_control_fork/install while so101_demo_py remained in the current repo install.
  - MuJoCo logged Starting the MuJoCo rendering thread and Sim ready without the EXP-002 timeout.
  - arm_controller, gripper_controller, and joint_state_broadcaster were active.
  - A fresh desktop screenshot visibly showed the native MuJoCo so101_task_scene viewer, the home robot, orange cup at the pick region, and red place marker before motion.
inferred:
  - The sole A/B variable, pinned-fork prefix precedence, is sufficient to restore the macOS native viewer path.
conclusion: The GUI startup blocker is confirmed as stale overlay shadowing; the pinned fork runtime passes the viewer/controller baseline gate.
evidence:
  - /Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z/exp-003/mujoco-prefix.txt
  - /Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z/exp-003/stack.log
  - /Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z/exp-003/screenshots/baseline-desktop.png
decision: KEEP
next_experiment: EXP-004
```

## EXP-004

```yaml
experiment_id: EXP-004
status: VALID
prior_experiment: EXP-003
hypothesis: The installed fixed_cup_pick_place executable can complete one full physical pick-place on the clean GUI stack validated by EXP-003.
prediction: All nine qualified phases pass, the CLI exits zero with status DONE, the cup moves from [0.02, -0.28] to the configured place region near [-0.08, -0.25], and final physical/MoveIt/controller/visual gates agree.
single_variable: Start fixed_cup_pick_place; stack configuration remains unchanged from EXP-003.
lifecycle: REUSE_STACK
preconditions:
  - EXP-003 stack remains healthy with no prior motion, session fixed-cup-e2e-20260824-r2, reset epoch 0, and all controllers active.
  - Baseline visual evidence is retained before workflow start.
success_criteria:
  - fixed_cup_pick_place exits 0 with status DONE and all nine expected phase artifacts validate.
  - Final MuJoCo evidence proves stable supported placement in target region with no gripper contact.
  - MoveIt reports no attached plastic_cup and restores it as a world object.
  - Controller/joint/TCP evidence and fresh motion/final screenshots agree with pick, transport, release, and retreat.
failure_criteria:
  - Any phase or final cross-layer gate fails.
invalid_criteria:
  - Stack provenance/session/reset changes unexpectedly or visual evidence cannot be captured.
provenance:
  source_commit: 5407592100823bcfa43138611f8de6b0de0c93f8
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install plus pinned fork first in AMENT_PREFIX_PATH
  runtime_executable: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/so101_demo_py/lib/so101_demo_py/fixed_cup_pick_place
  ros_domain_id: 175
  gz_partition: NOT_APPLICABLE
commands:
  - command: ROS_DOMAIN_ID=175 ros2 run so101_demo_py fixed_cup_pick_place --backend mujoco --run-mode execute --execute --session-id fixed-cup-e2e-20260824-r2 --expected-reset-epoch 0 --evidence-root <evidence-root>/exp-004/fixed-run --motion-policy <installed-share>/config/policies/light_cup_wall_pick/v1/mujoco.yaml --contact-policy <installed-share>/config/contact_calibration.yaml
    exit_code: 0
  - command: ROS_DOMAIN_ID=175 ros2 run so101_demo_py scene_setup --backend mujoco observe
    exit_code: 124
observed:
  - The executable reported status DONE, current_state DONE, transition_count 9, and the exact expected phase trace.
  - live-runtime-manifest.json reported status DONE, failed_phase null, failure null, correct session fixed-cup-e2e-20260824-r2, reset epoch 0, and exit code 0 for every phase artifact.
  - release-retreat.json reported RELEASE_RETREAT_FINAL_PLACEMENT_PROVED with 21 final samples, no attached object IDs, and world primitive counts table=1, pedestal=1, plastic_cup=13.
  - Fresh final atomic evidence reported publisher sequence 26219, simulation step 138393, a stable table-supported cup at [-0.0805566665, -0.247669460, 0.165322549], near-zero linear/angular velocity, no fingertip contact, and positive table normal force 0.23713.
  - arm_controller, gripper_controller, and joint_state_broadcaster remained active after completion.
  - Fresh screenshots were visually inspected: descent showed gripper/cup contact approach, transport showed the cup carried above the red place marker, and final showed the upright cup released on the red marker with the open gripper retreated.
  - The standalone scene_setup observe auxiliary command timed out and its forced shutdown hit the known double-shutdown exception; it is not counted as a success gate because the in-workflow release-retreat atomic artifact already proves the required final Planning Scene state.
inferred:
  - Numeric MuJoCo, controller, workflow, Planning Scene, and independent visual evidence converge on the same successful fixed-position pick-place outcome.
conclusion: fixed_cup_pick_place completed one valid local MuJoCo end-to-end demonstration.
evidence:
  - /Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z/exp-004/workflow.log sha256=20f92ced20a94cf733070ca70ebbdcb15ab83a41183a95ef1dd1e8f23863b726 size=551
  - /Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z/exp-004/final-readback.log sha256=cc03d2578fe1039fc02d0ec252c243f73284b48b1b6695a49ec4b83a828ca914 size=2926
  - /Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z/exp-004/fixed-run/live-runtime-manifest.json sha256=bdf22d4396140008df106777716f56643a264e95087f96076a0c92c449209c6c size=2037
  - /Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z/exp-004/fixed-run/release-retreat.json sha256=26556fac202d26f197eab8ae244a3ea8599faf3bf3267a26297160c444509a60 size=22417
  - /Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z/exp-004/screenshots/in-motion-descent.png sha256=abcf00f7335c4c00b023d414ef8c21833cb4831b045790f7be90691eb5119fbd size=1356471
  - /Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z/exp-004/screenshots/transport.png sha256=353455a467e5f1e9adaec94578d38436bfdc4e1b1b8d98eb99f6e1138e55bd3f size=1361219
  - /Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z/exp-004/screenshots/final.png sha256=d731594a96fe2ae6c1ac82ca901b62be45e513af47fc0e0a8a89674cefe29849 size=1360497
decision: KEEP
next_experiment: EXP-005
```

## EXP-005

```yaml
experiment_id: EXP-005
status: VALID
prior_experiment: EXP-004
hypothesis: Explicitly prepending the pinned MuJoCo fork after all direnv source operations will preserve the current demo overlay while making the Apple-main-thread fork authoritative.
prediction: A fresh direnv export resolves mujoco_ros2_control from the pinned fork, resolves so101_demo_py from the current repository install, and the complete package test suite remains green.
single_variable: Add the pinned fork prefix explicitly at the front of AMENT_PREFIX_PATH after the source loop.
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-003/004 stack is stopped with one SIGINT and no owned ROS process remains.
  - .envrc.example is changed under a RED environment-contract test; the local ignored .envrc receives the same repair.
success_criteria:
  - ros2 pkg prefix mujoco_ros2_control equals /Users/matianyi/ros2_jazzy/ws_mujoco_ros2_control_fork/install.
  - ros2 pkg prefix so101_demo_py remains under the current repository install.
  - AMENT_PREFIX_PATH begins with the pinned fork prefix.
  - Full direct package pytest passes.
failure_criteria:
  - Any prefix resolves to the wrong overlay or a package test regresses.
invalid_criteria:
  - Readback occurs without a fresh direnv export.
commands:
  - command: python3 -m pytest src/so101_demo_py/test/test_macos_install_contract.py -q -k pinned_mujoco_fork_first
    red_exit_code: 1
    green_exit_code: 0
  - command: direnv allow .; eval "$(direnv export zsh)"; ros2 pkg prefix mujoco_ros2_control; ros2 pkg prefix so101_demo_py
    exit_code: 0
  - command: eval "$(direnv export zsh)"; python3 -m pytest src/so101_demo_py/test -q
    exit_code: 0
observed:
  - The new contract test failed before the environment block existed and passed after the targeted patch.
  - mujoco_ros2_control resolved to the pinned fork, so101_demo_py remained in the repository install, and AMENT_PREFIX_PATH began with the pinned fork.
  - Full direct package pytest passed 237 tests in 8.15 seconds.
conclusion: The native macOS MuJoCo fork now resolves automatically in a fresh direnv shell without sacrificing the current demo package overlay.
evidence:
  - /Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z/exp-005/prefix-readback.log sha256=0ac8796e19cac69b65a270ca7761ee5a80a11bba9b2f2f43d395cc0f47d8cd9b size=246
  - /Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z/exp-005/pytest.log sha256=0e1ea64babf847ddff8b31d5c4ee7695cd9ab18b1043d02dc3551858ba00e46e size=340
decision: KEEP
next_experiment: EXP-006
```

## Checkpoint CP-001

```yaml
checkpoint_id: CP-001
last_valid_experiment: LOCAL-ENV-001
current_hypothesis: The installed local stack is ready for a workflow-free runtime smoke probe.
working_tree_status: Existing uncommitted V1/V2 implementation and documentation changes are preserved; this ledger is the only new task-owned source file.
owned_processes: NONE
preserved_processes: NONE observed; process check must be repeated outside the sandbox immediately before launch.
confirmed_conclusions:
  - Build, installed discovery, and direct package tests pass.
  - Dynamic execute is not implemented in the current V2.1 source.
disproven_routes:
  - Dynamic plan-only cannot count as physical end-to-end success.
open_risks:
  - Live MuJoCo/MoveIt/controller readiness is unknown.
  - Dynamic physical execution and calibration are not yet implemented.
next_command: Start EXP-001 only after an escalated duplicate-process check.
```

## Checkpoint CP-002

```yaml
checkpoint_id: CP-002
last_valid_experiment: EXP-001
current_hypothesis: The installed fixed executable can complete one fresh GUI-enabled physical run on the verified local stack.
working_tree_status: Existing uncommitted V1/V2 implementation and documentation changes are preserved; this ledger is task-owned.
owned_processes: NONE; EXP-001 stack exited cleanly with code 0.
preserved_processes: NONE
confirmed_conclusions:
  - Local MuJoCo, MoveIt, all three controllers, joint feedback, plan/execute interfaces, and lossless simulation evidence passed the stack-only probe.
  - Dynamic execute remains absent and cannot be tested as a physical workflow yet.
disproven_routes:
  - Local runtime dependency absence is not blocking the fixed workflow.
open_risks:
  - Native macOS viewer visibility and screenshot capture are not yet verified.
  - The fixed workflow has not yet run on this local checkout.
  - Dynamic physical execution and calibration remain unimplemented.
next_command: Start the EXP-002 GUI-enabled stack only after confirming no duplicate process.
```

## Checkpoint CP-003

```yaml
checkpoint_id: CP-003
last_valid_experiment: EXP-001
current_hypothesis: The pinned fork binary will make the native macOS viewer start when it is placed first in AMENT_PREFIX_PATH.
working_tree_status: Existing uncommitted V1/V2 implementation and documentation changes are preserved; this ledger is task-owned.
owned_processes: NONE; EXP-002 stack was stopped before any workflow or motion.
preserved_processes: NONE
confirmed_conclusions:
  - Headless runtime readiness passed in EXP-001.
  - EXP-002 selected a stale repo-local mujoco_ros2_control executable instead of the pinned fork.
disproven_routes:
  - GUI validation through the stale repo-local ros2_control_node cannot start native rendering on this host.
open_risks:
  - Pinned-fork viewer startup and screenshot capture remain unverified.
  - The fixed physical workflow has not run locally.
  - Dynamic physical execution remains unimplemented.
next_command: Start EXP-003 with only AMENT_PREFIX_PATH ordering changed.
```

## Checkpoint CP-004

```yaml
checkpoint_id: CP-004
last_valid_experiment: EXP-003
current_hypothesis: fixed_cup_pick_place will complete on the clean pinned-fork GUI stack.
working_tree_status: Existing uncommitted V1/V2 implementation and documentation changes are preserved; this ledger is task-owned.
owned_processes: EXP-003 stack owner remains active with ros2_control_node PID 19092 and move_group PID 19096 in ROS_DOMAIN_ID 175.
preserved_processes: NONE
confirmed_conclusions:
  - Pinned-fork AMENT precedence repairs native macOS viewer startup.
  - Baseline robot/cup/place-marker visual state is retained before motion.
disproven_routes:
  - Repo-local stale mujoco_ros2_control package cannot be used for GUI validation.
open_risks:
  - Fixed workflow has not yet passed locally.
  - Dynamic physical execution remains unimplemented.
next_command: Run EXP-004 fixed_cup_pick_place against the still-clean EXP-003 stack.
```

## Checkpoint CP-005

```yaml
checkpoint_id: CP-005
last_valid_experiment: EXP-004
current_hypothesis: A minimal environment precedence fix can make the pinned Apple-main-thread MuJoCo fork resolve automatically without shadowing the current so101_demo_py package.
working_tree_status: Existing uncommitted V1/V2 implementation and documentation changes are preserved; this ledger is task-owned.
owned_processes: EXP-003 stack owner remains active only until one clean SIGINT shutdown after fixed evidence sealing.
preserved_processes: NONE
confirmed_conclusions:
  - fixed_cup_pick_place completed one valid local MuJoCo demonstration with convergent workflow, physical, Planning Scene, controller, and visual evidence.
  - Pinned-fork AMENT precedence is required for the native macOS viewer.
  - Dynamic physical execution is still absent from the current V2.1 implementation.
disproven_routes:
  - A standalone scene_setup observe after the workflow is not a reliable auxiliary gate on this host because timeout termination triggers rclpy double shutdown; the workflow's atomic release-retreat artifact remains authoritative.
open_risks:
  - The direnv configuration still selects the stale repo-local MuJoCo package unless precedence is fixed.
  - Dynamic physical execution and calibration remain unimplemented and unvalidated.
next_command: Stop the EXP-003 stack with one SIGINT, verify owned processes exit, then begin test-first environment precedence repair as EXP-005.
```

## EXP-006

```yaml
experiment_id: EXP-006
status: VALID_HEADLESS
prior_experiment: EXP-005
hypothesis: The implemented dynamic MuJoCo execute path can consume a fresh topic-derived cup pose, complete the shared state-machine workflow, and satisfy the same physical and Planning Scene outcome gates as the fixed workflow.
prediction: dynamic_cup_pick_place exits zero at DONE, records the topic input and derived targets, completes every dynamic action, and leaves the cup stable and released in the place region with all controllers active.
single_variable: Execute the new dynamic strategy against the same qualified MuJoCo/MoveIt/controller stack; visual qualification is intentionally deferred.
lifecycle: FULL_RESTART_HEADLESS
preconditions:
  - The dynamic implementation and its unit/contract tests are installed from the current dirty working tree.
  - A unique headless stack uses session dynamic-headless-dev-8, reset epoch 0, and no competing ROS process.
  - The test-only observation bridge publishes the current MuJoCo cup state as /cup_pose without commanding the world or robot.
success_criteria:
  - The executable exits 0 at DONE with no failure and the complete dynamic action trace.
  - The manifest records a fresh world-frame /cup_pose and dynamically resolved action targets.
  - Final physical evidence proves target-region placement, table support, stability, upright orientation, and no fingertip contact.
  - Planning Scene ends detached with plastic_cup restored as a world object.
  - arm_controller, gripper_controller, and joint_state_broadcaster remain active.
failure_criteria:
  - Topic timeout/invalid input, fallback use, action failure, physical-outcome failure, scene mismatch, or inactive controller.
invalid_criteria:
  - Duplicate stack, session/reset mismatch, stale evidence, or presenting the headless run as final visual qualification.
provenance:
  source_commit: 5407592100823bcfa43138611f8de6b0de0c93f8 plus recorded uncommitted dynamic implementation
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install with pinned MuJoCo fork first
  runtime_executable: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/so101_demo_py/lib/so101_demo_py/dynamic_cup_pick_place
  simulation_session_id: dynamic-headless-dev-8
  expected_reset_epoch: 0
commands:
  - command: python3 -m so101_demo.ros.mujoco_cup_pose_bridge --session-id dynamic-headless-dev-8
    exit_code: CLEAN_SIGINT_AFTER_WORKFLOW
  - command: ros2 run so101_demo_py dynamic_cup_pick_place --backend mujoco --mode execute --execute --cup-pose-timeout-s 30 --scene-source observe_only --session-id dynamic-headless-dev-8 --expected-reset-epoch 0 --evidence-root <evidence-root>/exp-006/headless-dynamic
    exit_code: 0
observed:
  - The manifest schema is so101-dynamic-mujoco-execute-v1, current_state is DONE, failure is null, and the session/reset identifiers match.
  - The accepted input is a finite world-frame cup pose at [0.020000000000000018, -0.28, 0.16480156647042168] with an identity quaternion; the manifest records the dynamic policy hash and all resolved action targets.
  - The 18 executed state events, bounded by IDLE and DONE, are PREPARE_OPEN_GRIPPER, MOVE_ABOVE_OBJECT, DESCEND, CLOSE_GRIPPER, WAIT_GRASP_STABLE, MICRO_LIFT, WAIT_MICRO_LIFT_STABLE, VERIFY_PHYSICAL_GRASP, ATTACH_MOVEIT, LIFT, MOVE_ABOVE_PLACE, DESCEND_TO_PLACE, DETACH_MOVEIT, OPEN_GRIPPER, WAIT_RELEASE_SETTLE, VALIDATE_FINAL_PLACEMENT, SYNC_WORLD_OBJECT, and RETREAT.
  - Final cup position is [-0.078265637, -0.247422589, 0.164828462], approximately 0.002135 m from the configured XY target; upright tilt is approximately 0.004581 rad.
  - Final linear and angular velocities are near zero, fingertip contact counts are zero, table_contact is true, and maximum normal force is 0.232977 N.
  - Planning Scene attached object IDs are empty and world primitive counts are table=1, pedestal=1, plastic_cup=13.
  - arm_controller, gripper_controller, and joint_state_broadcaster are active.
conclusion: dynamic_cup_pick_place completed one valid headless local MuJoCo physical demonstration from a topic-derived pose. Independent native-viewer visual evidence remains required for the user's final end-to-end success contract.
evidence:
  - /Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z/exp-006/headless-dynamic/dynamic-execute-manifest.json sha256=1455783551f0841d599c80423ea051ee5f02efd8e232f7d637430d8963529688 size=48179
  - /Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z/exp-006/headless-dynamic/controllers.log sha256=323137275a8d9347a5c66ece85935e5c29cd8abc4bc440910ee3ad7f1f313889 size=258
decision: KEEP_NUMERIC_EVIDENCE
next_experiment: EXP-007
```

## EXP-007

```yaml
experiment_id: EXP-007
status: FAILED
prior_experiment: EXP-006
hypothesis: Repeating the qualified dynamic workflow on a visible native MuJoCo viewer will produce fresh descent, transport, and final screenshots that agree with the already-proven numeric outcome.
prediction: The GUI stack remains healthy, the dynamic run reaches DONE, and three non-black screenshots visibly prove grasp approach, cup transport, and final release.
single_variable: Enable native viewer capture while keeping dynamic policy and outcome gates unchanged.
lifecycle: FULL_RESTART_GUI
preconditions:
  - Pinned mujoco_ros2_control fork and current so101_demo_py overlay resolve correctly.
  - Native MuJoCo/GLFW includes the monitor-null, DPI, fullscreen, and no-monitor VSync guards required on this host.
  - The macOS desktop is unlocked and visible to Computer Use before the workflow starts.
success_criteria:
  - All EXP-006 numeric/workflow/scene/controller gates pass again.
  - Fresh in-motion-descent.png, transport.png, and final.png are non-black and visually inspected.
failure_criteria:
  - Dynamic workflow or any cross-layer outcome gate fails.
invalid_criteria:
  - Locked desktop, black/hidden/stale screenshot, viewer capture failure, session/reset mismatch, or duplicate stack.
provenance:
  final_attempt_ros_domain_id: 191
  final_attempt_simulation_session_id: dynamic-gui-e2e-20260824-r7
  expected_reset_epoch: 0
  runtime_stack_status: STOPPED_AFTER_FAILED_WORKFLOW
observed:
  - Earlier GUI diagnostics first crashed at _glfwGetVideoModeCocoa with no primary monitor, then deadlocked in CoreVideo display-refresh waiting while the render loop held the simulation mutex.
  - Targeted external MuJoCo/GLFW guards were rebuilt, after which the r5 stack loaded the model, initialized physics and MoveIt, completed scene setup, and activated all three controllers.
  - The locked-desktop r5 baseline was black and explicitly rejected. After unlock, its viewer was still not visible, so r5 was stopped without a workflow.
  - A sandboxed r6 launch could not write the controller-spawner lock and was invalidated before motion.
  - The unsandboxed r7 stack initialized successfully; its off-screen viewer was moved onto the primary display and a valid baseline was retained.
  - r7 consumed the topic pose and physically completed grasp, lift, transport, release, final placement validation, and world-object sync.
  - RETREAT and RECOVER_RETREAT both failed MoveIt validation because the restored world plastic_cup collision proxy intersected the gripper. The state trace ended at ERROR with MOVEIT_PLAN_FAILED.
  - MoveIt logs identify only the plastic_cup/gripper pair in the invalid retreat paths. The same contact pair was already handled narrowly for grasp descent but not for post-release retreat.
conclusion: EXP-007 exposed a real release-retreat ACM lifecycle defect. Although the cup reached the correct physical final placement, the executable did not reach DONE and this run is not accepted.
evidence:
  - /Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z/exp-007/screenshots/baseline.png classification=INVALID_BLACK_DIAGNOSTIC
  - /Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z/exp-007/dynamic-run/dynamic-execute-manifest.json classification=FAILED_WORKFLOW
decision: REPAIR_THEN_FULL_RESTART
next_experiment: EXP-008
```

## Checkpoint CP-006

```yaml
checkpoint_id: CP-006
last_valid_experiment: EXP-006
current_hypothesis: The proven dynamic run needs only an independent native-viewer repetition to satisfy the final user-visible evidence gate.
working_tree_status: Uncommitted fixed/dynamic implementation, environment, tests, and documentation changes are preserved; unrelated changes are not modified.
owned_processes: NONE after the EXP-006 headless stack and bridge were stopped cleanly.
confirmed_conclusions:
  - Dynamic topic consumption, strategy resolution, shared state-machine execution, controller motion, physical outcome, and Planning Scene convergence passed once headlessly.
  - Headless numeric success cannot substitute for visual evidence.
open_risks:
  - Native GUI initialization is unreliable when macOS reports no primary monitor.
next_command: Start an isolated GUI diagnostic before launching another dynamic workflow.
```

## Checkpoint CP-007

```yaml
checkpoint_id: CP-007
last_valid_experiment: EXP-006
current_hypothesis: A narrowly bounded cup/gripper ACM allowance during RETREAT and RECOVER_RETREAT will permit physical separation after release while restoring normal collision checks immediately afterward.
working_tree_status: Main repository changes remain uncommitted. External MuJoCo and mujoco_ros2_control sources contain targeted uncommitted macOS GUI guards with originals backed up under /tmp.
owned_processes: NONE; the r7 bridge and GUI stack were stopped after evidence capture.
confirmed_conclusions:
  - The GLFW primary-monitor crash and no-monitor VSync deadlock are repaired sufficiently for model, physics, MoveIt, scene, and controller initialization.
  - r7 proved every dynamic physical and scene gate through SYNC_WORLD_OBJECT, but RETREAT planning collided plastic_cup with gripper and the executable ended ERROR.
  - The new parameterized regression test failed for RETREAT and RECOVER_RETREAT before the code change and passed after the narrow enable-motion-disable ACM sequence was added.
open_risks:
  - The regression test does not replace a fresh full physical run.
next_command: Start EXP-008 from a fresh GUI stack and repeat the complete workflow and visual protocol.
```

## EXP-008

```yaml
experiment_id: EXP-008
status: VALID
prior_experiment: EXP-007
hypothesis: The narrow release-retreat ACM lifecycle repair permits the dynamic workflow to reach DONE without weakening any grasp, transport, release, physical, scene, or visual gate.
prediction: A fresh GUI run completes the same 18 action states plus DONE, the ACM exception is removed after retreat, the cup remains stable at the place target, and three screenshots visibly prove the motion.
single_variable: Allow only gripper/plastic_cup and jaw/plastic_cup collisions during RETREAT or RECOVER_RETREAT planning/execution, then immediately restore them to disallowed.
lifecycle: FULL_RESTART_GUI
preconditions:
  - The parameterized retreat ACM regression test is green after proving RED on the prior implementation.
  - A fresh native-viewer stack uses ROS_DOMAIN_ID 192, session dynamic-gui-e2e-20260824-r8, reset epoch 0, the pinned MuJoCo fork, and the current so101_demo_py overlay.
  - The viewer is visible on the unlocked primary desktop and a valid baseline is retained.
success_criteria:
  - dynamic_cup_pick_place exits 0 with status DONE and transition_count 19.
  - Input, resolved strategy, physical, Planning Scene, controller, and visual gates match the original contract.
  - RETREAT succeeds and the final manifest has no failure.
failure_criteria:
  - Any workflow or cross-layer gate fails, or retreat succeeds only by leaving the ACM exception enabled.
invalid_criteria:
  - Duplicate stack, session/reset mismatch, stale topic sample, or missing/black visual evidence.
provenance:
  source_commit: 5407592100823bcfa43138611f8de6b0de0c93f8 plus recorded uncommitted dynamic and release-retreat repair
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install with pinned MuJoCo fork first
  runtime_executable: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/so101_demo_py/lib/so101_demo_py/dynamic_cup_pick_place
  ros_domain_id: 192
  simulation_session_id: dynamic-gui-e2e-20260824-r8
  expected_reset_epoch: 0
commands:
  - command: python3 -m so101_demo.ros.mujoco_cup_pose_bridge --session-id dynamic-gui-e2e-20260824-r8
    exit_code: CLEAN_SIGINT_AFTER_READBACK
  - command: ros2 run so101_demo_py dynamic_cup_pick_place --backend mujoco --mode execute --execute --cup-pose-timeout-s 30 --scene-source observe_only --session-id dynamic-gui-e2e-20260824-r8 --expected-reset-epoch 0 --evidence-root <evidence-root>/exp-008/dynamic-run
    exit_code: 0
observed:
  - The executable reported status DONE, transition_count 19, current_state DONE, failure null, and the exact IDLE-to-DONE dynamic state trace.
  - It accepted a fresh finite world-frame /cup_pose at [0.020000000000000018, -0.28, 0.16480156647042168] and retained the dynamic policy SHA-256 1685caef958580c206c63acb1569cecca2a485535355f46c938cd8d6d027fb79 plus all resolved targets.
  - RETREAT completed with 34 trajectory points. Its final cup readback remained stable and table-supported with no fingertip contacts.
  - The manifest final sample was [-0.078272689, -0.247384500, 0.164825747], XY error 0.002117 m, upright tilt 0.004507 rad, near-zero velocities, zero left/right fingertip contacts, table_contact true, and maximum normal force 0.232848 N.
  - Independent post-run atomic readback reported the same session/reset and a stable cup at [-0.078749288, -0.248436898, 0.164981366], with only table contact.
  - Planning Scene attached object IDs were empty and world primitive counts were table=1, pedestal=1, plastic_cup=13.
  - arm_controller, joint_state_broadcaster, and gripper_controller remained active after DONE.
  - Fresh screenshots were visually inspected: descent showed the gripper inside the cup grasp region, transport showed the cup suspended above the table while moving toward the red marker, and final showed the upright cup released on the marker with the gripper open and retreated.
conclusion: dynamic_cup_pick_place completed one valid local MuJoCo native-viewer end-to-end demonstration from a topic-derived pose. Together with EXP-004, the requested fixed and dynamic single-run acceptance is satisfied.
evidence:
  - /Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z/exp-008/dynamic-run/dynamic-execute-manifest.json sha256=b8ea44b9b1425924bdd25f9ac41a8a1ea3ee015f3524ae65206fdc1e53f33496 size=48301
  - /Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z/exp-008/controllers.log sha256=ffb97138b19ea06a4a856c713c3987ef61218efd82b6cbda47eef9837da177cc size=258
  - /Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z/exp-008/final-evidence.log sha256=84cb5db2b827e7e4007504ddaa7841a19a5c363eb904159049faed1b86bdec63 size=1353
  - /Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z/exp-008/screenshots/in-motion-descent.png sha256=e91e3d1f82d99d0591053779a811a952287218ce88c9598b12c9d91fe99b932d size=1959886
  - /Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z/exp-008/screenshots/transport.png sha256=105e2ca4b949d935852c849f06463c4a6d0f5c74bea892923a6dde7d8367dec1 size=1962729
  - /Users/matianyi/work/so101-evidence/mujoco-dual-cup-e2e/20260824T035713Z/exp-008/screenshots/final.png sha256=1753ee06b703f35ddd1cfea7dc01b486501527f5b66cb513d3a7ffcefcc73e66 size=1963989
decision: KEEP
next_experiment: FINAL_REGRESSION_AND_SEALING
```

## Checkpoint CP-008

```yaml
checkpoint_id: CP-008
last_valid_experiment: EXP-008
current_hypothesis: NONE; the requested fixed and dynamic one-run MuJoCo acceptance contract is satisfied.
working_tree_status: Task changes remain uncommitted and unrelated user-owned changes are preserved. External MuJoCo/mujoco_ros2_control GUI guards also remain uncommitted with /tmp backups.
owned_processes: NONE; EXP-008 bridge and GUI stack were stopped with one SIGINT each after final readback.
confirmed_conclusions:
  - EXP-004 proves the fixed executable with convergent numeric, scene, controller, and visual evidence.
  - EXP-008 proves the dynamic executable consumes /cup_pose, reaches DONE, and passes the same cross-layer gates with fresh visual evidence.
  - The release-retreat ACM defect is covered by RED/GREEN regression tests and by a fresh physical success.
  - Final full package pytest passes 250 tests and colcon rebuild completes one package.
open_risks:
  - This is a single successful run per executable, not repeated-run stability qualification.
  - Native viewer startup on a locked/no-monitor macOS session still requires the external guards and a visible desktop for screenshot evidence.
next_command: Seal executable discovery, diff checks, hashes, and the retained/archived/deletion-candidate report.
```
