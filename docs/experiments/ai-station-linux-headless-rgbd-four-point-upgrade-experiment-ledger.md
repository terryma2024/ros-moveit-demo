---
task_id: so101-ai-station-linux-headless-rgbd-four-point-upgrade-20260828
goal: Upgrade ai-station main and third_party/mujoco_ros2_control, then qualify the four MuJoCo cup keyframes in both Linux headless and visible rendering modes.
success_contract: Eight VALID FULL_RESTART runs, covering four frozen MuJoCo cup keyframes with headless=true and headless=false; each run must prove installed provenance, real synchronized RGB/depth/camera-info processing, /cup_pose, dynamic pick/place DONE, physical final-placement evidence, clean exit, and no runtime residue. Visible mode additionally requires fresh exact-window visual evidence.
worktree: /data/work/ws_moveit
branch: main
base_commit: b3770360b26fe8f6fac0e19338d250b6f5cab0e7
current_commit: e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4
evidence_root: /data/work/so101-evidence/fusion/ai-station-linux-headless-rgbd-four-point-20260828
confirmed_conclusions:
  - Local and Gitee parent main are e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4; Gitee third_party main is 71bc9346cf93d6227a6678fcacf63f3e18acfcba (EXP-201 preflight).
  - ai-station /data/work/ws_moveit main is clean at b3770360b26fe8f6fac0e19338d250b6f5cab0e7, behind origin/main by 23 commits, with clean detached third_party at 738e304551b4ea6db020b466086a13db71b65607 (EXP-201 preflight).
  - No MuJoCo, MoveIt, RGB-D perception, or dynamic workflow process was running during preflight; existing worktrees and tmux sessions are preserved (EXP-201 preflight).
  - ai-station main fast-forwarded to e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4 and third_party/mujoco_ros2_control materialized 71bc9346cf93d6227a6678fcacf63f3e18acfcba without modifying preserved worktrees or sessions (EXP-201).
  - The installed third_party candidate passed 240 tests with zero errors/failures; isolated project support passed 20 tests, and the demo suite passed 551 tests with two stale CLI mock assertions deselected (EXP-202).
  - EXP-203 proved Linux EGL and 640x480 offscreen-buffer initialization but was INVALID_PREFLIGHT because the declared python3-open3d runtime dependency was absent; no perception result or grasp action was counted.
disproven_routes:
  - NONE
open_hypotheses:
  - The fast-forwarded Linux candidate builds and its installed runtime completes all four frozen keyframes in both headless and visible modes under independent FULL_RESTART lifecycle.
latest_checkpoint: CP-203
next_experiment: EXP-211
---

# ai-station Linux headless RGB-D four-point upgrade ledger

## Frozen matrix

| Experiment | Lifecycle | Headless | Keyframe | Expected cup XYZ | ROS domain | GZ partition | Session |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EXP-211 | `FULL_RESTART` | `true` | `task_start` | `(0.02, -0.28, 0.165)` | 211 | `so101_linux_rgbd_exp211` | `linux-rgbd-exp211-task-start` |
| EXP-212 | `FULL_RESTART` | `true` | `cup_test_forward_5cm` | `(0.02, -0.33, 0.165)` | 212 | `so101_linux_rgbd_exp212` | `linux-rgbd-exp212-forward` |
| EXP-213 | `FULL_RESTART` | `true` | `cup_test_left_5cm` | `(-0.03, -0.28, 0.165)` | 213 | `so101_linux_rgbd_exp213` | `linux-rgbd-exp213-left` |
| EXP-214 | `FULL_RESTART` | `true` | `cup_test_right_5cm` | `(0.07, -0.28, 0.165)` | 214 | `so101_linux_rgbd_exp214` | `linux-rgbd-exp214-right` |
| EXP-215 | `FULL_RESTART` | `false` | `task_start` | `(0.02, -0.28, 0.165)` | 215 | `so101_linux_rgbd_exp215` | `linux-visible-exp215-task-start` |
| EXP-216 | `FULL_RESTART` | `false` | `cup_test_forward_5cm` | `(0.02, -0.33, 0.165)` | 216 | `so101_linux_rgbd_exp216` | `linux-visible-exp216-forward` |
| EXP-217 | `FULL_RESTART` | `false` | `cup_test_left_5cm` | `(-0.03, -0.28, 0.165)` | 217 | `so101_linux_rgbd_exp217` | `linux-visible-exp217-left` |
| EXP-218 | `FULL_RESTART` | `false` | `cup_test_right_5cm` | `(0.07, -0.28, 0.165)` | 218 | `so101_linux_rgbd_exp218` | `linux-visible-exp218-right` |

## CP-200 - preflight

```yaml
checkpoint_id: CP-200
last_valid_experiment: NONE
current_hypothesis: The published macOS CGL change preserves the Linux EGL path and four-point RGB-D physical workflow.
working_tree_status: ai-station main clean; local orchestrator main clean
owned_processes: NONE
preserved_processes: existing codex and codex-cua tmux sessions; three pre-existing linked worktrees
confirmed_conclusions:
  - ai-station main and third_party are clean and behind the published candidates.
  - No relevant runtime stack is active.
disproven_routes:
  - NONE
open_risks:
  - Linux build and installed runtime are not yet verified at the new commits.
  - Four-point physical and visual outcomes are not yet verified.
next_command: git pull --ff-only origin main followed by git submodule sync/update
```

## EXP-201 - parent and third_party upgrade

```yaml
experiment_id: EXP-201
status: VALID
prior_experiment: NONE
hypothesis: The clean ai-station main can fast-forward to the published parent commit and materialize the locked third_party commit without overwriting user work.
prediction: Parent HEAD becomes the ledger-bearing origin/main commit, third_party becomes 71bc9346cf93d6227a6678fcacf63f3e18acfcba, and both worktrees remain clean.
single_variable: Published parent and submodule revisions
lifecycle: ISOLATED_STACK
preconditions:
  - /data/work/ws_moveit main and third_party are clean.
  - No task runtime stack is active.
success_criteria:
  - git pull --ff-only succeeds.
  - git submodule sync/update succeeds.
  - Parent and third_party commits and statuses match the published candidates.
failure_criteria:
  - A non-fast-forward, dirty conflict, missing object, or submodule update failure occurs.
invalid_criteria:
  - Any pre-existing user change is overwritten or an unrelated worktree is modified.
provenance:
  source_commit: e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4
  install_overlay: NOT_BUILT
  runtime_executable: NOT_BUILT
  ros_domain_id: 200
  gz_partition: so101_linux_rgbd_exp201
commands:
  - command: git pull --ff-only origin main; git submodule sync --recursive; git submodule update --init --recursive
    exit_code: 0
observed:
  - Parent fast-forwarded from b3770360b26fe8f6fac0e19338d250b6f5cab0e7 to e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4.
  - third_party/mujoco_ros2_control updated from 738e304551b4ea6db020b466086a13db71b65607 to 71bc9346cf93d6227a6678fcacf63f3e18acfcba.
  - Parent status contains only this task-owned untracked ledger; the submodule is detached and clean.
inferred:
  - Published parent/submodule revisions are now materialized on ai-station and ready for isolated qualification.
conclusion: The fast-forward and recursive submodule upgrade succeeded without overwriting user work.
evidence:
  - /data/work/so101-evidence/fusion/ai-station-linux-headless-rgbd-four-point-20260828/upgrade
decision: VALID
next_experiment: EXP-202
```

## CP-201 - upgraded source

```yaml
checkpoint_id: CP-201
last_valid_experiment: EXP-201
current_hypothesis: The upgraded Linux sources build and test from an isolated candidate overlay.
working_tree_status: ai-station main has only the task-owned untracked ledger; third_party detached clean
owned_processes: NONE
preserved_processes: existing codex and codex-cua tmux sessions; three pre-existing linked worktrees
confirmed_conclusions:
  - Parent source is e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4.
  - third_party/mujoco_ros2_control source is 71bc9346cf93d6227a6678fcacf63f3e18acfcba.
disproven_routes:
  - NONE
open_risks:
  - Candidate build, test collection, and installed provenance are not yet verified.
  - Four independent RGB-D physical workflows are not yet verified.
next_command: Inspect package graph and build the isolated candidate overlay under the registered evidence root.
```

## EXP-202 - clean candidate build and tests

```yaml
experiment_id: EXP-202
status: QUALIFIED_FOR_RUNTIME_WITH_RECORDED_GAPS
prior_experiment: EXP-201
hypothesis: The upgraded Linux sources build into isolated fork and project overlays, pass the rendering/support/runtime tests, and resolve every changed runtime package to the candidate prefixes.
prediction: All changed packages resolve to the candidate prefixes and the runtime-relevant non-zero tests pass; unrelated current-main test/environment gaps are preserved explicitly.
single_variable: Installed candidate built from EXP-201 source
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-201 is VALID.
  - Candidate build/install/log paths are new and inside the registered evidence root.
success_criteria:
  - Candidate build exits zero.
  - Directed and package tests collect non-zero tests and pass.
  - ros2 package prefixes and runtime executable resolve to the candidate overlay.
failure_criteria:
  - Compile, link, test assertion, or installed provenance fails.
invalid_criteria:
  - Tests load the previous workspace plugin/core/demo instead of the candidate.
provenance:
  source_commit: e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4
  install_overlay: /data/work/so101-evidence/fusion/ai-station-linux-headless-rgbd-four-point-20260828/candidate/project-isolated/install
  runtime_executable: /data/work/so101-evidence/fusion/ai-station-linux-headless-rgbd-four-point-20260828/candidate/project-isolated/install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 200
  gz_partition: so101_linux_rgbd_exp202
commands:
  - command: scripts/install-mujoco-ros2-control.zsh in the registered candidate workspace
    exit_code: 0
  - command: isolated project colcon build; support colcon test; repository-root demo pytest; backend integration and installed provenance checks
    exit_code: 0 for the qualified runtime gates
observed:
  - Four fork packages built; 240 tests passed, 0 errors, 0 failures, 3 platform skips.
  - so101_mujoco_support passed 20 tests; so101_demo_py passed 551 tests with two current-main CLI mock assertions deselected; backend integration passed.
  - The two deselected tests slice the generated `ros2 run ...` argv at index 2 but still expect the removed `run` token; live command generation itself is correct.
  - so101_teleop test collection is blocked by ai-station system pydantic 1.10.14 while current code imports the pydantic-v2 `field_validator`; teleop is outside this RGB-D runtime path.
  - The static fusion script is stale against current executable names and stops after `gazebo_ready`; this failure is retained and is not reported as a pass.
  - Fork packages resolve to the fork candidate, project packages resolve to isolated per-package prefixes, and mujoco_vendor resolves to /opt/ros/jazzy.
inferred:
conclusion: The exact upgraded RGB-D runtime is installed and qualified for live headless/visible testing, with current-main teleop/static-test gaps explicitly outside the runtime success claim.
evidence:
  - /data/work/so101-evidence/fusion/ai-station-linux-headless-rgbd-four-point-20260828/candidate
decision: PROCEED_TO_LIVE_RUNTIME_WITH_RECORDED_GAPS
next_experiment: EXP-211
```

## CP-202 - installed candidate ready for live qualification

```yaml
checkpoint_id: CP-202
last_completed_experiment: EXP-202
source_commit: e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4
fork_commit: 71bc9346cf93d6227a6678fcacf63f3e18acfcba
fork_tests: 240 tests, 0 errors, 0 failures, 3 skipped
support_tests: 20 tests, 0 errors, 0 failures
demo_qualified_tests: 551 passed, 2 stale mock assertions deselected
backend_integration: PASS
owned_processes: NONE
preserved_processes: existing codex and codex-cua tmux sessions; three pre-existing linked worktrees
open_test_gaps:
  - Two current-main mujoco_rgbd_batch mock assertions have an impossible argv slice/expectation pairing.
  - so101_teleop requires pydantic v2 but ai-station system Python provides 1.10.14.
  - check_fusion_contract.sh still expects removed executable names.
next_command: Run EXP-211 headless=true task_start as an independent FULL_RESTART.
```

## EXP-203 - invalid Open3D preflight

```yaml
experiment_id: EXP-203
status: INVALID_PREFLIGHT
prior_experiment: EXP-202
lifecycle: FULL_RESTART
headless: true
mujoco_initial_keyframe: task_start
ros_domain_id: 201
gz_partition: so101_linux_rgbd_exp203
observed:
  - Linux headless mode selected sensor rendering and created a Mesa EGL 1.5 OpenGL context with a 640x480 offscreen buffer.
  - rgbd_cup_pose failed closed before perception or motion because Open3D was missing from /usr/bin/python3.
  - Launch performed ordered shutdown and the wrapper recorded no postflight node/process residue.
conclusion: Renderer startup is useful diagnostic evidence, but this run cannot count because the perception dependency precondition was false.
decision: Preserve the run; materialize the previously validated Open3D 0.19 task-local dependency set inside this task evidence root, freeze a new eight-run matrix, and start at EXP-211.
evidence:
  - /data/work/so101-evidence/fusion/ai-station-linux-headless-rgbd-four-point-20260828/runs/exp-203-headless-task-start
```

## CP-203 - Python runtime dependency restored

```yaml
checkpoint_id: CP-203
last_valid_experiment: EXP-202
invalid_experiment: EXP-203
python_dependency_root: /data/work/so101-evidence/fusion/ai-station-linux-headless-rgbd-four-point-20260828/python-deps
open3d: 0.19.0
numpy: 1.26.4
pydantic: 2.13.4
dependency_source: Previously validated ai-station task-local dependency set copied into the registered current evidence root; no system Python mutation.
owned_processes: NONE
next_command: Execute the newly frozen EXP-211 through EXP-218 matrix without reusing EXP-203 evidence.
```

## EXP-211 through EXP-218 - four-point, two-render-mode FULL_RESTART qualification

For each row in the frozen matrix, create a new process tree only after the
prior run has completely exited. The planned variables are the frozen
`mujoco_initial_keyframe` and the one render-mode switch between the two
four-run blocks; source commit, candidate overlay, remaining launch parameters,
policy, perception thresholds, and success contract remain fixed.

```yaml
status: PLANNED
prior_experiment: CP-203 for EXP-211; immediately preceding FULL_RESTART thereafter
hypothesis: The upgraded installed Linux runtime performs RGB-D perception-driven pick/place at the selected frozen cup keyframe.
prediction: The selected EGL headless or GLFW visible renderer produces synchronized rgb8/32FC1/camera-info data; perception emits a bounded /cup_pose; the dynamic workflow reaches DONE with physical final-placement evidence and exits cleanly.
single_variable: mujoco_initial_keyframe within each render-mode block; headless changes once between EXP-214 and EXP-215
lifecycle: FULL_RESTART
preconditions:
  - EXP-202 installed provenance and runtime-relevant tests are qualified with its unrelated current-main gaps recorded.
  - No prior task runtime process remains.
  - Unique ROS_DOMAIN_ID, GZ_PARTITION, session, ROS_HOME, ROS_LOG_DIR, and evidence child are active.
success_criteria:
  - Perception status is OK with 640x480 input and positive point counts.
  - Perceived XYZ is within 2 mm planar tolerance of the frozen keyframe position.
  - Dynamic manifest is DONE with 19 transitions and final-placement validation.
  - Runtime exits zero and no owned process remains.
  - Every visible-mode run has a fresh exact-window screenshot paired with runtime data.
failure_criteria:
  - Valid startup reaches a perception, planning, execution, physical, placement, or shutdown failure.
invalid_criteria:
  - Wrong source/overlay, duplicate stack, stale evidence path, or lifecycle contamination.
provenance:
  source_commit: e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4
  install_overlay: /data/work/so101-evidence/fusion/ai-station-linux-headless-rgbd-four-point-20260828/candidate/project-isolated/install
  runtime_executable: /data/work/so101-evidence/fusion/ai-station-linux-headless-rgbd-four-point-20260828/candidate/project-isolated/install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: FROM_FROZEN_MATRIX
  gz_partition: FROM_FROZEN_MATRIX
commands:
  - command: ros2 run so101_demo_py so101_mujoco_perception_pick_place run_mode:=execute execute:=true headless:=<true-or-false> sensor_rendering:=true mujoco_initial_keyframe:=<keyframe> ...
    exit_code: PENDING
observed:
  - PENDING
inferred:
  - NONE
conclusion: PENDING
evidence:
  - Child directory below the registered evidence root for the experiment ID
decision: PENDING
next_experiment: NEXT_ROW_OR_NONE
```

## Evidence disposition

- Retained: none yet
- Archived: none
- Deletion candidates: none; no evidence may be deleted without explicit user authorization
