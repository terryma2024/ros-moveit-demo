# macOS Four-Preset Post-Reconcile Pick-Place Ledger

```yaml
task_id: so101-mac-four-preset-post-reconcile-20260827
goal: Requalify RGB-D perception-driven pick-place at all four MJCF cup presets after reconciling the five local files to main@b6adf1b.
success_contract: Four independent FULL_RESTART runs, one per preset, each passing perception, controller, MoveIt shadow, MuJoCo physical outcome, final placement, ordered shutdown, and cleanup gates.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo
branch: main
base_commit: b6adf1b85c575f726da4e40662f6bb53842fc6dd
current_commit: b6adf1b85c575f726da4e40662f6bb53842fc6dd
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
child_version: 0.1.0
evidence_root: /tmp/so101-debug-mac-four-preset-post-reconcile-20260827
confirmed_conclusions:
  - CP-148 in rgbd-pick-place-mujoco-0-1-main-integration-experiment-ledger.md qualified the same four presets on macOS before the five-file reconciliation.
  - The five reconciled files are byte-identical to b6adf1b and the post-reconcile Python suite passed 448 tests.
disproven_routes:
  - The prior run-repair-full-restart.zsh is not reusable because it hard-codes superseded fork-install and project-install overlays.
open_hypotheses:
  - The reconciled main tree preserves the four-preset live behavior when executed from freshly rebuilt reconcile-five overlays.
latest_checkpoint: CP-004
next_experiment: COMPLETE
```

## CP-001 — batch preregistered after clean live preflight

```yaml
checkpoint_id: CP-001
recorded_at: 2026-08-27T14:00:00+08:00
status: READY
last_valid_experiment: CP-148 from the prior integration ledger
working_tree_status: clean at preflight; this ledger is the only planned repository write
installed_fork_overlay: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/reconcile-five-fork-install
installed_project_overlay: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/reconcile-five-project-r2-install
runtime_bundle_sha256: 8570eccd5410a7b76f2e34229b4185491813d2b215d13522f9ab6b51ba15fdf5
preflight: No active MuJoCo, MoveIt, controller, perception, or dynamic pick-place process; ROS domain 125 is empty.
preserved_processes: Four pre-existing mrc010 tmux sessions; three dead panes and one idle shell, none owns a live stack.
next_command: Run EXP-001 task_start as an independent FULL_RESTART.
```

## EXP-001 through EXP-004 — four-preset fixed-configuration batch

Common frozen contract:

```yaml
status: PLANNED
prior_experiment: CP-148
hypothesis: main@b6adf1b with child@5e9d67c and the reconcile-five overlays preserves the previously qualified four-preset behavior.
prediction: Each preset reaches DONE with source-stamped RGB-D perception, physical unsupported lift and transport, detach-before-open, stable final placement, synchronized MoveIt world state, and clean shutdown.
single_variable: mujoco_initial_keyframe only
lifecycle: FULL_RESTART
preconditions:
  - No active task stack in the experiment ROS domain or GZ partition.
  - Robot and cup start from the named MJCF keyframe.
success_criteria:
  - Runner exits zero and dynamic manifest reaches DONE with transition_count 19.
  - Perception publishes a source-stamped world /cup_pose within 5 mm of the preset and writes nonempty point-cloud evidence.
  - Every motion phase has nonzero trajectory points and fresh terminal joint/FK evidence with <=5 mm TCP position error.
  - Physical micro-lift is 1-10 mm with bilateral contact and no table support; lift and transport remain bilaterally held and unsupported.
  - MoveIt detaches before gripper open; final cup is upright, supported by the table, within 10 mm XY, stationary, and absent from attached objects.
  - Ordered MoveIt/controller shutdown markers are present and the experiment owns no remaining process.
failure_criteria: Any product gate above fails with valid provenance and observation.
invalid_criteria: Wrong overlay, wrong commit/version, duplicate stack, missing evidence, GUI/capture contamination, or incomplete cleanup.
```

| Experiment | Domain | Keyframe | Session | Evidence stem |
|---|---:|---|---|---|
| EXP-001 | 125 | `task_start` | `mac-post-reconcile-task-start-exp001` | `task-start` |
| EXP-002 | 126 | `cup_test_forward_5cm` | `mac-post-reconcile-forward-exp002` | `forward` |
| EXP-003 | 127 | `cup_test_left_5cm` | `mac-post-reconcile-left-exp003` | `left` |
| EXP-004 | 128 | `cup_test_right_5cm` | `mac-post-reconcile-right-exp004` | `right` |

## EXP-001 — task_start

```yaml
experiment_id: EXP-001
status: VALID
prior_experiment: CP-148
single_variable: mujoco_initial_keyframe=task_start
lifecycle: FULL_RESTART
provenance:
  source_commit: b6adf1b85c575f726da4e40662f6bb53842fc6dd
  install_overlay: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/reconcile-five-project-r2-install
  runtime_executable: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/reconcile-five-project-r2-install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 125
  gz_partition: mac-post-reconcile-task-start-exp001
commands:
  - command: /tmp/so101-debug-mac-four-preset-post-reconcile-20260827/tools/run-full-restart.zsh /tmp/so101-debug-mac-four-preset-post-reconcile-20260827/runs/exp-001 125 mac-post-reconcile-task-start-exp001 task_start /tmp/so101-debug-mac-four-preset-post-reconcile-20260827/runs/exp-001/task-start.json
    exit_code: 0
observed:
  - Perception error 0.000644043399 m; physical micro-lift 0.003981548419 m.
  - Maximum terminal TCP position error 0.000691654266 m; final XY error 0.002611016680 m.
  - All validator gates pass, the direct postflight graph is empty, and the task identity owns no remaining process.
  - The macOS window inventory exposes no MuJoCo/GLFW window; the desktop debug capture does not show the Viewer, so exact-window visual success remains unavailable and is not claimed.
conclusion: task_start passes the complete functional and physical contract on main@b6adf1b.
evidence:
  - /tmp/so101-debug-mac-four-preset-post-reconcile-20260827/runs/exp-001/task-start.d/mac-post-reconcile-task-start-exp001/perception/summary.json sha256=64e7a19432715b43bda82a0b2c5896d543d970d3e752d91046983283034788c9
  - /tmp/so101-debug-mac-four-preset-post-reconcile-20260827/runs/exp-001/task-start.d/mac-post-reconcile-task-start-exp001/dynamic/dynamic-execute-manifest.json sha256=3458981d5ab9e79d9b6bb5d0191f6d8d342c0241e46e65107dd5b64e325ef820
decision: KEEP
next_experiment: EXP-002
```

## EXP-002 — cup_test_forward_5cm

```yaml
experiment_id: EXP-002
status: VALID
prior_experiment: EXP-001
single_variable: mujoco_initial_keyframe=cup_test_forward_5cm
lifecycle: FULL_RESTART
provenance:
  source_commit: b6adf1b85c575f726da4e40662f6bb53842fc6dd
  install_overlay: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/reconcile-five-project-r2-install
  runtime_executable: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/reconcile-five-project-r2-install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 126
  gz_partition: mac-post-reconcile-forward-exp002
commands:
  - command: /tmp/so101-debug-mac-four-preset-post-reconcile-20260827/tools/run-full-restart.zsh /tmp/so101-debug-mac-four-preset-post-reconcile-20260827/runs/exp-002 126 mac-post-reconcile-forward-exp002 cup_test_forward_5cm /tmp/so101-debug-mac-four-preset-post-reconcile-20260827/runs/exp-002/forward.json
    exit_code: 0
observed:
  - Perception error 0.000594433664 m; physical micro-lift 0.003979802915 m.
  - Maximum terminal TCP position error 0.001179072930 m; final XY error 0.002473540387 m.
  - All validator gates pass, the direct postflight graph is empty, and the task identity owns no remaining process.
conclusion: cup_test_forward_5cm passes the complete functional and physical contract.
evidence:
  - /tmp/so101-debug-mac-four-preset-post-reconcile-20260827/runs/exp-002/forward.d/mac-post-reconcile-forward-exp002/perception/summary.json sha256=977b08a3d0608a656d1c51c00fe9005c2debbf0798fddd7310fe55a106d27f78
  - /tmp/so101-debug-mac-four-preset-post-reconcile-20260827/runs/exp-002/forward.d/mac-post-reconcile-forward-exp002/dynamic/dynamic-execute-manifest.json sha256=4baa7619cecc874fc16a63ff2d4e8c4b0741ad5ab18ace7ba4b40651a71dfe13
decision: KEEP
next_experiment: EXP-003
```

## EXP-003 — cup_test_left_5cm

```yaml
experiment_id: EXP-003
status: VALID
prior_experiment: EXP-002
single_variable: mujoco_initial_keyframe=cup_test_left_5cm
lifecycle: FULL_RESTART
provenance:
  source_commit: b6adf1b85c575f726da4e40662f6bb53842fc6dd
  install_overlay: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/reconcile-five-project-r2-install
  runtime_executable: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/reconcile-five-project-r2-install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 127
  gz_partition: mac-post-reconcile-left-exp003
commands:
  - command: /tmp/so101-debug-mac-four-preset-post-reconcile-20260827/tools/run-full-restart.zsh /tmp/so101-debug-mac-four-preset-post-reconcile-20260827/runs/exp-003 127 mac-post-reconcile-left-exp003 cup_test_left_5cm /tmp/so101-debug-mac-four-preset-post-reconcile-20260827/runs/exp-003/left.json
    exit_code: 0
observed:
  - Perception error 0.000690029746 m; physical micro-lift 0.003968494856 m.
  - Maximum terminal TCP position error 0.000832295709 m; final XY error 0.002480510202 m.
  - All validator gates pass, the direct postflight graph is empty, and the task identity owns no remaining process.
conclusion: cup_test_left_5cm passes the complete functional and physical contract.
evidence:
  - /tmp/so101-debug-mac-four-preset-post-reconcile-20260827/runs/exp-003/left.d/mac-post-reconcile-left-exp003/perception/summary.json sha256=3d43a80fe3652deb0a558734a73070ca1149a3f8c61b678325b088807d02768b
  - /tmp/so101-debug-mac-four-preset-post-reconcile-20260827/runs/exp-003/left.d/mac-post-reconcile-left-exp003/dynamic/dynamic-execute-manifest.json sha256=079a855dcd4ad362634c8d0aa3b2c8afd380b6b2f209a2f4f653ffded61b4aa3
decision: KEEP
next_experiment: EXP-004
```

## EXP-004 — cup_test_right_5cm

```yaml
experiment_id: EXP-004
status: VALID
prior_experiment: EXP-003
single_variable: mujoco_initial_keyframe=cup_test_right_5cm
lifecycle: FULL_RESTART
provenance:
  source_commit: b6adf1b85c575f726da4e40662f6bb53842fc6dd
  install_overlay: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/reconcile-five-project-r2-install
  runtime_executable: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/reconcile-five-project-r2-install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 128
  gz_partition: mac-post-reconcile-right-exp004
commands:
  - command: /tmp/so101-debug-mac-four-preset-post-reconcile-20260827/tools/run-full-restart.zsh /tmp/so101-debug-mac-four-preset-post-reconcile-20260827/runs/exp-004 128 mac-post-reconcile-right-exp004 cup_test_right_5cm /tmp/so101-debug-mac-four-preset-post-reconcile-20260827/runs/exp-004/right.json
    exit_code: 0
observed:
  - Perception error 0.000631097398 m; physical micro-lift 0.003973254288 m.
  - Maximum terminal TCP position error 0.001570441281 m; final XY error 0.002501671881 m.
  - All validator gates pass, the direct postflight graph is empty, and the task identity owns no remaining process.
conclusion: cup_test_right_5cm passes the complete functional and physical contract.
evidence:
  - /tmp/so101-debug-mac-four-preset-post-reconcile-20260827/runs/exp-004/right.d/mac-post-reconcile-right-exp004/perception/summary.json sha256=d362ee96857a641e6d951b5cf6eff419a69de7d5efdd5fdbbdb9a9ba19dc775a
  - /tmp/so101-debug-mac-four-preset-post-reconcile-20260827/runs/exp-004/right.d/mac-post-reconcile-right-exp004/dynamic/dynamic-execute-manifest.json sha256=17dafed300be0789d8aebec0e34e75ee949aecb3dd9d76b1fe773469d329b864
decision: KEEP
next_experiment: NONE
```

## CP-002 — four runtime runs valid; post-run verification pending

```yaml
checkpoint_id: CP-002
status: RUNTIME_4_OF_4_VALID
last_valid_experiment: EXP-004
working_tree_status: Only this task ledger is untracked; no runtime source file differs from b6adf1b.
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions remain untouched.
confirmed_conclusions:
  - EXP-001 task_start, EXP-002 forward, EXP-003 left, and EXP-004 right are four independent valid FULL_RESTART successes.
  - All four runs use main@b6adf1b, child@5e9d67c version 0.1.0, and the reconcile-five fork/project overlays.
  - Four-run joint validator passes every perception, workflow, motion, physical, MoveIt, placement, provenance, and ordered-shutdown gate.
open_risks:
  - macOS does not expose the non-bundled GLFW Viewer as an Accessibility window; exact-window visual success remains unavailable and is not claimed.
next_command: Run the 448-test post-runtime suite, then repeat provenance, worktree, process, domain, and retained-evidence checks.
```

## CP-003 — post-reconcile Mac four-preset qualification complete

```yaml
checkpoint_id: CP-003
status: COMPLETE
last_valid_experiment: EXP-004
source_commit: b6adf1b85c575f726da4e40662f6bb53842fc6dd
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
child_version: 0.1.0
valid_full_restart_batch: [EXP-001, EXP-002, EXP-003, EXP-004]
positions: [task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm]
perception_error_range_m: [0.0005944336636481587, 0.0006900297461242743]
physical_micro_lift_range_m: [0.003968494856396831, 0.0039815484186450645]
maximum_terminal_tcp_position_error_m: 0.0015704412809286782
final_xy_error_range_m: [0.0024735403870756074, 0.002611016680229501]
common_result: Every run exits zero, reaches DONE/19, uses source-stamped world /cup_pose from nonempty RGB-D point-cloud evidence, records fresh terminal joint/FK evidence and nonzero trajectories, proves bilateral unsupported lift/transport, detaches MoveIt before opening, reaches stable table-supported final placement with zero fingertip contacts, syncs the world object, retreats, and shuts down cleanly.
post_run_tests: 448 passed in 12.62 s.
owned_processes: NONE
task_domains: 125-128 all empty by direct no-daemon readback
preserved_processes: Pre-existing mrc010 tmux sessions remain untouched.
visual_boundary: Exact-window MuJoCo Viewer capture remains unavailable on macOS because the GLFW window is absent from the Accessibility/CoreGraphics inventory; visual success is not claimed.
retained: /tmp/so101-debug-mac-four-preset-post-reconcile-20260827 including all four run logs, point clouds, manifests, provenance, validator, and postflight logs.
archived: NONE
deletion_candidates:
  - EXP-001 desktop debug capture because it did not contain the Viewer and includes unrelated desktop context; retained pending explicit user authorization.
next_command: NONE
```

## CP-004 — RGB-D perception PickPlace teaching guide verified

```yaml
checkpoint_id: CP-004
status: DOCUMENTATION_COMPLETE
last_valid_experiment: EXP-004
source_commit: b6adf1b85c575f726da4e40662f6bb53842fc6dd
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
child_version: 0.1.0
working_tree_status: Three untracked documentation files: this ledger, the RGB-D guide, and its Superpowers implementation plan; no runtime source differs from b6adf1b.
documentation:
  - docs/so101-rgbd-perception-pick-place-source-guide.md
  - docs/superpowers/plans/2026-08-27-rgbd-perception-pick-place-guide.md
installed_runtime_prefix: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/reconcile-five-project-r2-install/so101_demo_py
verification:
  - New guide has 35 relative Markdown links and every target exists.
  - Perception, launch-composition, and dynamic-input targeted suite passed 117 tests.
  - Full so101_demo_py suite passed 448 tests in 12.34 s from the same reconcile-five candidate overlay used by the four-preset qualification.
  - The first full-suite attempt against the stale workspace install was not a product failure: 447 tests passed and installed provenance alone rejected the missing console script; the exact candidate overlay then passed 448/448.
evidence:
  - /tmp/so101-debug-mac-four-preset-post-reconcile-20260827/doc-verification/pytest-so101-demo.xml sha256=bcb49c4d5dba749c9c26efef988f6aaded600e16894b521f261e9bc8ba813e51 size=75K
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions remain untouched.
visual_boundary: No new runtime or GUI claim was made for the documentation-only follow-up; CP-003 remains the visual evidence boundary.
retained: /tmp/so101-debug-mac-four-preset-post-reconcile-20260827 including the original four runs and doc-verification/pytest-so101-demo.xml.
archived: NONE
deletion_candidates:
  - EXP-001 desktop debug capture previously identified by CP-003; retained pending explicit user authorization.
  - doc-verification/pytest-cache and doc-verification/ros-log are reproducible test scratch outputs; retained pending explicit user authorization.
next_command: NONE
```
