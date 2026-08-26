# RGB-D Pick-Place on mujoco_ros2_control 0.1.0 Main Integration Ledger

```yaml
task_id: so101-rgbd-pick-place-mrc010-main
goal: Prove RGB-D-driven physical pick-place from all four MJCF cup keyframes on macOS and ai-station using child main@5e9d67c.
success_contract: Four independent FULL_RESTART successes on macOS, four independent FULL_RESTART successes on ai-station, plus one ai-station task_start repeat so the final fixed candidate has five consecutive valid live runs.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-pick-place-mujoco-0-1-main
branch: codex/rgbd-pick-place-mujoco-0-1-main
base_commit: b73748f86acc891711aa455fc911a9ebde52686d
current_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_commit: 1a0c532cb4ff012bc1cef95a47594ca8a1a65fa5
commit_semantics: current_commit and implementation_commit identify the immutable installed runtime; record_commit identifies the ledger-only commit that first contains CP-002 and is resolved additively after that commit exists.
target_child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
evidence_root: /tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/
confirmed_conclusions:
  - OBS-001: child main@5e9d67c contains aeff7e5 and both commits have identical trees.
  - OBS-002: parent main@b73748f clean isolated-install baseline passed 303 of 303 so101_demo_py tests from /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-baseline-canonical.
  - OBS-003: origin/codex/rgbd-perception-pick-place@0649f3b retains prior four-position qualification, but those runs do not count for this new child-main candidate.
  - OBS-006: implementation 208dd216 with child main@5e9d67c built into isolated Mac fork/project installs; 17 registered child CTests (230 JUnit cases), 442 project tests, and the 153-test directed integration set pass.
disproven_routes:
  - OBS-004: sourcing the parent checkout .envrc in a nested worktree selects the parent install and is not valid candidate provenance.
  - OBS-005: using non-canonical /tmp build paths on macOS makes installed manifest and ament prefix strings diverge.
  - OBS-007: enabling zsh nounset before generated colcon setup scripts aborts source at unset COLCON_TRACE and removes required CMake prefixes.
  - OBS-008: colcon's macOS child environment omits DYLD_LIBRARY_PATH; accepted child tests use direct Homebrew CTest after same-process setup, with the candidate fork ahead of the dylib farm.
  - OBS-009: putting the dylib farm ahead of the task fork selects the old fork library and is invalid candidate provenance.
  - OBS-010: Mac EXP-015 is a VALID product failure: candidate project-install omitted ABI-dependent so101_mujoco_support, so the new 0.1.0 pre_step caller loaded the old isolated-workspace SimulationEvidencePlugin vtable and crashed with SIGSEGV before perception.
  - OBS-011: The RED support-plugin prefix contract is GREEN after building so101_mujoco_support against the candidate fork into the candidate project overlay; support CTest 1/1 and project pytest 443/443 pass.
  - OBS-012: Non-qualifying SMOKE-001 loaded only the ABI-aligned candidate SimulationEvidencePlugin, advanced authoritative simulation evidence from step 90989 to 90994, crossed the EXP-015 crash boundary for 221.44 s, and shut down cleanly after one owned SIGINT with no -11 or owned residue.
  - OBS-013: EXP-016 is a VALID product failure after the ABI fix: exact installed provenance and cwd passed, but rgbd_cup_pose exhausted its startup deadline during ROS runtime construction before producing any RGB-D/point-cloud/cup-pose evidence.
  - OBS-014: SMOKE-002 measures material live-stack contention: the same runtime probe grows from 6.69 s empty-graph to 17.14 s with MuJoCo/MoveIt live, principally Open3D 3.32 to 9.01 s and create_node 2.85 to 6.82 s, but a single probe still remains below 30 s.
open_hypotheses:
  - The tree-identical child-main merge commit preserves all qualified 0.1.0 runtime behavior after RGB-D integration.
  - The merged camera contract retains both 0.1.0 lifecycle and perception task-camera requirements.
  - A clean so101_mujoco_support rebuild against the frozen 0.1.0 child removes the confirmed ABI mismatch without source behavior changes.
latest_checkpoint: CP-022
next_experiment: SMOKE-003
```

## Shared live acceptance contract

`AC-001` requires every countable run to prove all of the following from the same session:

- exact parent commit, child gitlink/checkout `5e9d67c`, isolated installed package prefix, executable,
  ROS domain, partition, session, keyframe, and owned PID set;
- real aligned `640x480` CameraInfo/RGB/depth samples in `task_camera_frame`, encodings `rgb8` and
  `32FC1`, with finite positive depth;
- accepted segmented point cloud, radius fit, retained summary and nonempty PLY;
- fresh `world` `/cup_pose` from `rgbd_cup_pose`, no truth publisher, and error within the existing
  `0.01 m` tolerance of MuJoCo truth;
- installed exact-status runner exits zero, `dynamic_cup_pick_place` reaches `DONE` with 19 expected
  transitions, and motion states contain trajectory/joint/TF evidence;
- bilateral unsupported lift and transport, detach before open, stable table-supported final pose in
  the red target, zero final fingertip contacts, and no final physical attachment;
- MoveIt cup shadow attaches, detaches, and ends as a world object at the final MuJoCo pose;
- fresh baseline, transport, and final images are captured and inspected for the same Viewer/session;
- only run-owned processes exit, with no owned node, Viewer, tmux pane, or domain process remaining.

Any missing provenance, duplicate stack, old screenshot, wrong session, unavailable camera sample,
or mixed evidence makes the run `INVALID`. A countable behavioral failure is `VALID` failure and
ends the fixed-candidate consecutive batch.

## Planned macOS runs

```yaml
experiment_id: EXP-010
status: INVALID
prior_experiment: NONE
hypothesis: The final installed candidate completes AC-001 from task_start on macOS.
prediction: The perceived start pose is near [0.02, -0.28, 0.165] and the cup is released stably in the red target.
single_variable: initial_keyframe=task_start
lifecycle: FULL_RESTART
preconditions:
  - Candidate commit is frozen, clean, and installed from the isolated worktree.
  - Domain 220, session mac-mrc010-task-start-exp010, and the run evidence path are empty.
success_criteria:
  - AC-001 passes every clause.
failure_criteria:
  - The clean candidate starts correctly but any AC-001 product clause fails.
invalid_criteria:
  - Provenance, process isolation, GUI freshness, or evidence ownership is missing.
provenance:
  source_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
  install_overlay: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install
  runtime_executable: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 220
  gz_partition: mac-mrc010-task-start-exp010
commands:
  - command: ROS_DOMAIN_ID=220 GZ_PARTITION=mac-mrc010-task-start-exp010 ros2 run so101_demo_py so101_mujoco_perception_pick_place run_mode:=execute execute:=true headless:=false session_id:=mac-mrc010-task-start-exp010 mujoco_initial_keyframe:=task_start evidence_file:=/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-010/task-start.json
    exit_code: 1
observed:
  - INVALID_ENVIRONMENT: tmux inherited a deleted historical worktree as cwd; eleven getcwd-failed XML parser diagnostics preceded RGBD_CUP_POSE_TIMEOUT.
  - The exact Viewer baseline was captured and inspected, but transport and final boundaries never existed.
inferred:
  - The stale cwd is a launch-environment contaminant; this run cannot support product behavior conclusions.
conclusion: Strict INVALID; excluded from the Mac success set.
evidence:
  - /tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-010
decision: REPEAT
next_experiment: EXP-014
```

```yaml
experiment_id: EXP-014
status: INVALID
prior_experiment: EXP-010
hypothesis: Binding the task-owned tmux pane to the current live worktree removes only the stale-cwd contamination and permits the unchanged task_start candidate to complete AC-001.
prediction: No getcwd-failed diagnostic occurs; the perceived start pose is near [0.02, -0.28, 0.165], and the unchanged workflow releases the cup stably in the red target.
single_variable: tmux startup adds -c /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-pick-place-mujoco-0-1-main; product command, overlays, keyframe, policy, geometry, thresholds, and capture boundaries are unchanged.
lifecycle: FULL_RESTART
preconditions:
  - EXP-010 exact-owned product, capture helper, Viewer, tmux, and domain processes are absent; its invalid evidence remains immutable.
  - The candidate is unchanged, the task worktree exists, and the new tmux pane cwd readback equals that task worktree before the product command starts.
  - Domain 229, session mac-mrc010-task-start-retry-exp014, and the new run evidence path are empty.
success_criteria:
  - AC-001 passes every clause.
failure_criteria:
  - The clean unchanged candidate starts correctly but any AC-001 product clause fails.
invalid_criteria:
  - Provenance, cwd/process isolation, GUI freshness, or evidence ownership is missing.
provenance:
  source_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
  install_overlay: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install
  runtime_executable: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 229
  gz_partition: mac-mrc010-task-start-retry-exp014
commands:
  - command: ROS_DOMAIN_ID=229 GZ_PARTITION=mac-mrc010-task-start-retry-exp014 ros2 run so101_demo_py so101_mujoco_perception_pick_place run_mode:=execute execute:=true headless:=false session_id:=mac-mrc010-task-start-retry-exp014 mujoco_initial_keyframe:=task_start evidence_file:=/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-014/task-start-retry.json
    exit_code: 245
observed:
  - INVALID_ENVIRONMENT: the explicit tmux -c precondition failed before product startup; pane readback still selected the deleted historical worktree and child getcwd returned dot.
  - Seven getcwd-failed diagnostics preceded the required MuJoCo runtime SIGSEGV; launch then shut down the remaining owned graph.
inferred:
  - No causal claim between stale cwd and the SIGSEGV is required or made; the pre-registered cwd isolation precondition independently makes the run non-counting.
conclusion: Strict INVALID; excluded from product behavior conclusions.
evidence:
  - /tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-014
decision: REPEAT_AFTER_NON_PRODUCT_TMUX_CWD_AB
next_experiment: NONE
```

## CP-082 — Production input-release GREEN and installed freeze

```yaml
checkpoint_id: CP-082
recorded_at: 2026-08-27T03:14:30+08:00
cause: SMOKE-016 established that post-first-valid reliable RGB-D input traffic starved MoveIt action-result delivery on Mac.
tdd:
  red_commit: 4f260d2
  red_command: test_rgbd_cup_pose.py::test_first_valid_publish_releases_exact_rgbd_inputs_once_and_cleanup_is_safe
  red_result: Failed because zero of the three owned subscriptions were destroyed.
  green_commit: fff7ba3b1c7efb4472f51d0842d8bcba87d64621
  implementation: After the first successful world-pose publish, validate ownership count3, destroy inputs in reverse order, remove only successfully destroyed handles, mark release idempotently, and emit stable status INPUT_RELEASED_AFTER_FIRST_VALID; publisher/node/TF remain long-lived and cleanup sees an empty input list.
tests:
  focused: 1 passed
  rgbd_file: 44 passed
  full_project: 445 passed in 12.33s
  installed_provenance: 4 passed
installed:
  demo_prefix: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_demo_py
  support_prefix: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_mujoco_support
  fork_prefix: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-install/mujoco_ros2_control
  child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
  bundle_sha256: 5c84da5a6bed093be023336da815fc2d1c7cb169aefa72cb13d6999346f25a2a
  support_sha256: f4487cc3e2467e2ffec5b2ca2fa407d8c372b63cfe07cc1e71e777185d1a7ab7
  support_uuid: 74A169FE-F055-3D0D-A333-9F7F7BAEF574
qualification_helpers:
  runner_sha256: 8f0cbdce963608c21cc414972208ca439365e8fc90d9fba5574f0ac29353747b
  capture_sha256: ee291e99b2c600c7142c704139da561c8b5d13d280cd1a5ccb4496ec3c40eed8
decision: RESUME_FOUR_POSITION_FORMAL_BATCH_WITH_FRESH_EXP021
```

## CP-083 — Plan post-fix task_start Mac qualification

```yaml
checkpoint_id: CP-083
recorded_at: 2026-08-27T03:15:00+08:00
experiment_id: EXP-021
status: PLANNED
qualification: true
position: task_start
lifecycle: FULL_RESTART
implementation_commit: fff7ba3b1c7efb4472f51d0842d8bcba87d64621
record_head: cdc57ba
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
installed_bundle_sha256: 5c84da5a6bed093be023336da815fc2d1c7cb169aefa72cb13d6999346f25a2a
identity: {domain: 206, session: mac-mrc010-task-start-exp021, tmux: mac-mrc010-task-start-exp021, evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-021, evidence_file: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-021/task-start.json}
runner_gate:
  - Fresh domain/session/evidence/process/Viewer, exact installed bundle/prefix/fork/support, explicit in-pane task-worktree cwd.
  - Start fail-closed direct Codex capture coordinator first; require capture.owner before product. Freeze one exact Viewer window ID/PID and require nonempty validated manifest+PNG at baseline, LIFT/MOVE_ABOVE_PLACE transport, and WAIT_RELEASE_SETTLE/VALIDATE_FINAL_PLACEMENT final boundaries.
acceptance: Full CP-061 / AC-001 including RGB-D/PLY/radius/world pose/TF/no truth bridge, INPUT_RELEASED_AFTER_FIRST_VALID count3, DONE/19, trajectory/FK, bilateral unsupported grasp/lift/transport, detach-before-open, final table/XY/tilt/contact/Planning Scene, eleven exits, screenshots, and exact cleanup.
decision: COMMIT_PLAN_THEN_FRESH_PREFLIGHT_CAPTURE_OWNER_PRODUCT_NATURAL_EXIT
next_experiment: EXP-021
```

## CP-084 — Correct pre-product capture coordinator clock

```yaml
checkpoint_id: CP-084
recorded_at: 2026-08-27T03:17:20+08:00
experiment_id: EXP-021
status: PLANNED
pre_product_observation: The first direct coordinator invocation exited at line16 before creating evidence or ownership because noninteractive zsh with nounset did not define EPOCHSECONDS; no product/session/domain/Viewer started.
correction: Replace all EPOCHSECONDS reads with date +%s while preserving the 900-second boundaries and every capture/identity/validation gate.
corrected_capture_sha256: d2f714b34ad61eac861422d2242bdd99d374c968594fb13543baf837f23a82e4
decision: KEEP_EXP021_PLANNED_AND_REPEAT_FRESH_CAPTURE_OWNER_GATE
```

## CP-085 / CLOSE-EXP-021-001 — Reject capture inventory parser before product

```yaml
checkpoint_id: CP-085
transition_id: CLOSE-EXP-021-001
recorded_at: 2026-08-27T03:18:20+08:00
experiment_id: EXP-021
from: PLANNED
to: INVALID_CAPTURE_RUNNER
qualification: false
reason: The direct coordinator created only capture.owner, then its Python inventory expression failed syntax validation because escaped quotes were used inside an f-string expression. No Viewer/product/ROS/tmux was started.
cleanup: Coordinator exited nonzero naturally; exact session/domain206/processes remain empty.
correction: Use str.format with normal dictionary quoting in both inventory parsers; corrected helper SHA256 4821cb4b3be078b09a786ac637ed3c3cad40340f0763d8cd1aadfaabbf8a7eba.
evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-021
decision: RETAIN_INVALID_AND_REPEAT_FRESH_TASK_START
next_experiment: EXP-022
```

## CP-087 / TRANS-EXP-022-RUNNING-001 — Start post-fix task_start qualification

```yaml
checkpoint_id: CP-087
transition_id: TRANS-EXP-022-RUNNING-001
recorded_at: 2026-08-27T03:20:15+08:00
experiment_id: EXP-022
from: PLANNED
to: RUNNING
qualification: true
position: task_start
implementation_commit: fff7ba3b1c7efb4472f51d0842d8bcba87d64621
pre_running_observed:
  - Fresh domain207/session/processes/Viewer/evidence and exact installed bundle/helper gates passed.
  - Direct fail-closed capture coordinator PID48818 is alive with exact EXP-022 argv and capture.owner; no product has started.
decision: START_EXPLICIT_CWD_PRODUCT_AND_WAIT_FOR_NATURAL_EXIT_AND_THREE_CAPTURES
```

## CP-086 — Plan parser-validated task_start Mac qualification

```yaml
checkpoint_id: CP-086
recorded_at: 2026-08-27T03:18:50+08:00
experiment_id: EXP-022
status: PLANNED
qualification: true
position: task_start
lifecycle: FULL_RESTART
implementation_commit: fff7ba3b1c7efb4472f51d0842d8bcba87d64621
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
installed_bundle_sha256: 5c84da5a6bed093be023336da815fc2d1c7cb169aefa72cb13d6999346f25a2a
identity: {domain: 207, session: mac-mrc010-task-start-exp022, tmux: mac-mrc010-task-start-exp022, evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-022, evidence_file: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-022/task-start.json}
runner_gate: CP-083 unchanged except corrected capture helper SHA256 4821cb4b3be078b09a786ac637ed3c3cad40340f0763d8cd1aadfaabbf8a7eba; the exact live inventory parser was separately executed and returned NONE without syntax/runtime error before this plan.
acceptance: Full CP-061 / AC-001 and three validated exact-window original-resolution captures.
decision: COMMIT_PLAN_THEN_FRESH_PREFLIGHT_CAPTURE_OWNER_PRODUCT_NATURAL_EXIT
next_experiment: EXP-022
```

```yaml
experiment_id: EXP-011
status: PLANNED
prior_experiment: EXP-010
hypothesis: Changing only the keyframe to cup_test_forward_5cm preserves AC-001 on macOS.
prediction: The perceived start pose is near [0.02, -0.33, 0.165] and the same physical workflow succeeds.
single_variable: initial_keyframe=cup_test_forward_5cm
lifecycle: FULL_RESTART
preconditions:
  - EXP-010 owned processes are absent and the candidate is unchanged.
  - Domain 221, session mac-mrc010-forward-exp011, and the run evidence path are empty.
success_criteria:
  - AC-001 passes every clause.
failure_criteria:
  - The clean candidate starts correctly but any AC-001 product clause fails.
invalid_criteria:
  - Provenance, process isolation, GUI freshness, or evidence ownership is missing.
provenance:
  source_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
  install_overlay: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install
  runtime_executable: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 221
  gz_partition: mac-mrc010-forward-exp011
commands:
  - command: ROS_DOMAIN_ID=221 GZ_PARTITION=mac-mrc010-forward-exp011 ros2 run so101_demo_py so101_mujoco_perception_pick_place run_mode:=execute execute:=true headless:=false session_id:=mac-mrc010-forward-exp011 mujoco_initial_keyframe:=cup_test_forward_5cm evidence_file:=/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-011/forward.json
    exit_code: PENDING
observed:
  - NOT_RUN
inferred:
  - NONE
conclusion: PENDING
evidence:
  - /tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-011
decision: PENDING
next_experiment: EXP-012
```

```yaml
experiment_id: EXP-012
status: PLANNED
prior_experiment: EXP-011
hypothesis: Changing only the keyframe to cup_test_left_5cm preserves AC-001 on macOS.
prediction: The perceived start pose is near [-0.03, -0.28, 0.165] and the same physical workflow succeeds.
single_variable: initial_keyframe=cup_test_left_5cm
lifecycle: FULL_RESTART
preconditions:
  - EXP-011 owned processes are absent and the candidate is unchanged.
  - Domain 222, session mac-mrc010-left-exp012, and the run evidence path are empty.
success_criteria:
  - AC-001 passes every clause.
failure_criteria:
  - The clean candidate starts correctly but any AC-001 product clause fails.
invalid_criteria:
  - Provenance, process isolation, GUI freshness, or evidence ownership is missing.
provenance:
  source_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
  install_overlay: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install
  runtime_executable: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 222
  gz_partition: mac-mrc010-left-exp012
commands:
  - command: ROS_DOMAIN_ID=222 GZ_PARTITION=mac-mrc010-left-exp012 ros2 run so101_demo_py so101_mujoco_perception_pick_place run_mode:=execute execute:=true headless:=false session_id:=mac-mrc010-left-exp012 mujoco_initial_keyframe:=cup_test_left_5cm evidence_file:=/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-012/left.json
    exit_code: PENDING
observed:
  - NOT_RUN
inferred:
  - NONE
conclusion: PENDING
evidence:
  - /tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-012
decision: PENDING
next_experiment: EXP-013
```

```yaml
experiment_id: EXP-013
status: PLANNED
prior_experiment: EXP-012
hypothesis: Changing only the keyframe to cup_test_right_5cm preserves AC-001 on macOS.
prediction: The perceived start pose is near [0.07, -0.28, 0.165] and the same physical workflow succeeds.
single_variable: initial_keyframe=cup_test_right_5cm
lifecycle: FULL_RESTART
preconditions:
  - EXP-012 owned processes are absent and the candidate is unchanged.
  - Domain 223, session mac-mrc010-right-exp013, and the run evidence path are empty.
success_criteria:
  - AC-001 passes every clause.
failure_criteria:
  - The clean candidate starts correctly but any AC-001 product clause fails.
invalid_criteria:
  - Provenance, process isolation, GUI freshness, or evidence ownership is missing.
provenance:
  source_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
  install_overlay: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install
  runtime_executable: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 223
  gz_partition: mac-mrc010-right-exp013
commands:
  - command: ROS_DOMAIN_ID=223 GZ_PARTITION=mac-mrc010-right-exp013 ros2 run so101_demo_py so101_mujoco_perception_pick_place run_mode:=execute execute:=true headless:=false session_id:=mac-mrc010-right-exp013 mujoco_initial_keyframe:=cup_test_right_5cm evidence_file:=/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-013/right.json
    exit_code: PENDING
observed:
  - NOT_RUN
inferred:
  - NONE
conclusion: PENDING
evidence:
  - /tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-013
decision: PENDING
next_experiment: EXP-020
```

## Planned ai-station runs

The ai-station entries use the same full `AC-001` criteria. The command is identical to the Mac
runner command after sourcing `/opt/ros/jazzy/setup.zsh`, the isolated fork install, and the isolated
project install. Only the frozen keyframe, domain, session, partition, and evidence file change.

| Experiment | Domain | Keyframe | Session and partition | Evidence file |
|---|---:|---|---|---|
| EXP-020 | 224 | `task_start` | `linux-mrc010-task-start-exp020` | `/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/linux-runs/exp-020/task-start.json` |
| EXP-021 | 225 | `cup_test_forward_5cm` | `linux-mrc010-forward-exp021` | `/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/linux-runs/exp-021/forward.json` |
| EXP-022 | 226 | `cup_test_left_5cm` | `linux-mrc010-left-exp022` | `/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/linux-runs/exp-022/left.json` |
| EXP-023 | 227 | `cup_test_right_5cm` | `linux-mrc010-right-exp023` | `/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/linux-runs/exp-023/right.json` |
| EXP-024 | 228 | `task_start` | `linux-mrc010-task-start-repeat-exp024` | `/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/linux-runs/exp-024/task-start-repeat.json` |

For each `EXP-020` through `EXP-024`:

```yaml
status: PLANNED
lifecycle: FULL_RESTART
preconditions:
  - The exact pushed candidate is checked out cleanly in a new ai-station isolation root.
  - The previous experiment's owned graph is absent; the listed domain, session, and evidence path are empty.
success_criteria:
  - AC-001 passes every clause.
failure_criteria:
  - The clean candidate starts correctly but any AC-001 product clause fails.
invalid_criteria:
  - Provenance, process isolation, GUI freshness, or evidence ownership is missing.
provenance:
  source_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
  install_overlay: /tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/linux-candidate/project-install
  runtime_executable: /tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/linux-candidate/project-install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
observed:
  - NOT_RUN
inferred:
  - NONE
conclusion: PENDING
decision: PENDING
```

The table row supplies each experiment's single variable, exact domain, partition/session, command
argument, and evidence path. EXP-024 repeats EXP-020 with an otherwise unchanged fixed candidate to
complete the five-run ai-station stability batch.

## Checkpoints

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: The approved main integration can be implemented without changing qualified perception or motion behavior.
working_tree_status: Design amendment and this ledger are uncommitted; production source and submodule remain at parent main baseline.
owned_processes: NONE
preserved_processes: Mac parent checkout user changes; all existing ai-station worktrees, tmux sessions, Codex processes, and user stacks.
confirmed_conclusions:
  - Child main ancestry/tree equality and the 303-test clean parent baseline are observed.
disproven_routes:
  - Parent .envrc and non-canonical macOS /tmp build paths are invalid provenance routes.
open_risks:
  - Merge compatibility, dual-platform builds, nine live runs, and visual gates remain unverified.
next_command: Commit the amended design, ledger, and implementation plan; then begin the version-lock RED test.
```

```yaml
checkpoint_id: CP-002
recorded_at: 2026-08-26T23:03:02+08:00
last_valid_experiment: NONE
current_hypothesis: The exact installed 0.1.0-main candidate is statically qualified; EXP-010 must be the first fresh Mac live acceptance run.
implementation_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
record_commit: 1a0c532cb4ff012bc1cef95a47594ca8a1a65fa5
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
working_tree_status: Only this ledger is modified for CP-002; implementation commit 208dd216 and child checkout are clean.
owned_processes: NONE
preserved_processes: Mac parent checkout user changes; all unrelated local and ai-station worktrees, processes, tmux sessions, and evidence.
installed_provenance:
  fork_overlay: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-install
  project_overlay: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install
  package_prefixes:
    mujoco_3d_lidar: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-install/mujoco_3d_lidar
    mujoco_ros2_control_msgs: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-install/mujoco_ros2_control_msgs
    mujoco_ros2_control_plugins: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-install/mujoco_ros2_control_plugins
    mujoco_ros2_control: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-install/mujoco_ros2_control
    so101_demo_py: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_demo_py
  runtime_executable: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  launch_file: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_demo_py/share/so101_demo_py/launch/so101_mujoco_perception_pick_place.launch.py
  python_runtime_module: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-build/so101_demo_py/so101_demo/runtime/launch_composition.py
  bundle_sha256: 0caa56a10cc6d13d808aa8b57f5fbfae8c7fca808b53edccbbb47d03de7bc30e
commands:
  - command: colcon build four selected child packages into mac-candidate/fork-build and fork-install
    exit_code: 0
  - command: direct Homebrew CTest for all four selected child package build directories after same-process overlay setup
    exit_code: 0
  - command: colcon test-result over accepted direct-CTest JUnit scope
    exit_code: 0
  - command: colcon build --packages-select so101_demo_py into mac-candidate/project-build and project-install
    exit_code: 0
  - command: python -m pytest src/so101_demo_py/test -q
    exit_code: 0
  - command: python -m pytest nine directed version/camera/keyframe/TF/RGB-D/scene-sync/runner files -q
    exit_code: 0
automated_results:
  child_build: Four of four selected packages built; zero-package discovery did not occur.
  child_tests: 17 of 17 registered CTests pass; 230 JUnit cases, 0 errors, 0 failures. The lidar and msgs packages register no standalone tests; core and plugins provide the nonzero package gate.
  project_build: so101_demo_py built into the independent project overlay.
  project_full_tests: 442 passed in 21.03 s; collect-only independently found 442 tests.
  project_directed_tests: 153 passed in 17.45 s.
  backend_integration: PASS
  lock_gitlink_child_parity: Both installed locks, source locks, gitlink, and child HEAD select main@5e9d67c; child contains upstream 0.1.0 and f19a8cc lineage, and its tree equals aeff7e5.
invalid_non_counting_attempts:
  - Initial child build failed before compilation because nounset interrupted generated setup scripts; it is retained under fork-build-invalid-nounset and fork-log-invalid-nounset.
  - Initial colcon test child environment dropped DYLD_LIBRARY_PATH and produced loader errors; its dashboard and complete log are retained under fork-test-invalid-colcon-child-env and fork-test-command.log.
  - The first direct CTest A/B put the dylib farm before the task fork and selected an old library; direct-ctest-ab-core.log is retained.
  - A provenance readback reused zsh special variable path and lost PATH; installed-provenance-readback-invalid-zsh-path.txt is retained.
  - An unsourced collect-only probe produced collection errors; project-pytest-collect-only-invalid-unsourced.log is retained.
confirmed_conclusions:
  - OBSERVED: Natural ament prefixes resolve all four child packages to fork-install and so101_demo_py to project-install; the installed runner, launch, locks, runtime library, and immutable bundle are readable there.
  - OBSERVED: The accepted same-process Mac loader order puts the task fork before the existing farm and old fork, so candidate symbols and ROS dylibs both resolve.
  - OBSERVED: Static qualification is complete without changing grasp geometry, motion policy, camera extrinsics, target, controller, or recovery behavior.
disproven_routes:
  - nounset-before-source, colcon child-env test execution, farm-before-candidate, zsh special path reuse, and unsourced pytest collection are invalid environment routes, not product regressions.
open_risks:
  - EXP-010 through EXP-013 have not run; camera, point cloud, TF, physical workflow, Planning Scene, fresh visuals, and clean shutdown remain live acceptance gates.
evidence:
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-build-command-r2.log
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-direct-ctest.log
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-direct-test-result-verbose-clean-scope.txt
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-build-command.log
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-pytest-full.log
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-pytest-collect-only.log
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-directed-pytest.log
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/installed-provenance-readback.txt
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/installed-provenance-manifest.json
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/final-static-verification.txt
decision: PROCEED_TO_EXP_010_MAC_FULL_RESTART
next_experiment: EXP-010
next_command: Read the project-local gui-capture skill, prove domain 220/session/evidence/Viewer isolation, and transition only EXP-010 to RUNNING before starting the GUI stack.
```

## CP-002-AUDIT-CORRECTION — Task 3 review round 1

This is additive; it does not rewrite CP-002 or change installed implementation commit
`208dd216f9ef52e2792830a19c1e070b8aef1778`.

```yaml
correction_id: CP-002-AUDIT-CORRECTION
record_head_before_correction: ae4d20af0645bbf26459e4132e4287407cba8800
acceptance_ruling:
  - Upstream mujoco_3d_lidar and mujoco_ros2_control_msgs intentionally register no standalone CTest. Their literal "No tests were found!!!" output is preserved and is not counted as a test.
  - A selected leaf with no standalone CTest passes only through nonzero installed-artifact or installed-interface consumer tests against the exact candidate overlay; a raw no-tests output never passes alone.
  - mujoco_3d_lidar substitute gate is the 3-case test_3d_lidar_plugin ament-resource/plugin consumer; 3/3 passed.
  - mujoco_ros2_control_msgs substitute gate is test_mujoco_simulation (44 cases) plus test_viewer_camera (7 cases); 51/51 generated-interface consumer cases passed.
  - Project contract nodeids test_macos_install_contract.py::test_installer_builds_exact_upgrade_package_set_and_checks_new_artifacts and test_macos_install_contract.py::test_integration_guide_reads_back_all_four_fork_package_prefixes passed inside the 442-case full suite. They assert the exact four-package set, required message interfaces/artifacts, and all four candidate prefix readbacks.
accepted_environment_preamble_before_child_build: |-
  source /Users/matianyi/ros2_jazzy/.venv/bin/activate
  source /opt/ros/jazzy/setup.zsh
  source /Users/matianyi/ros2_jazzy/extra_ws/install/setup.zsh
  source /Users/matianyi/ros2_jazzy/so101_isolated_ws/install/setup.zsh
  export VIRTUAL_ENV=/Users/matianyi/ros2_jazzy/.venv
  export PATH="/Users/matianyi/ros2_jazzy/.venv/bin:${PATH}"
  export PYTHONNOUSERSITE=1
  export DYLD_LIBRARY_PATH="/Users/matianyi/ros2_jazzy/macos_dylib_farm/current${DYLD_LIBRARY_PATH:+:${DYLD_LIBRARY_PATH}}"
  export ROS_LOG_DIR=/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/ros-log
accepted_environment_preamble_before_child_test: |-
  source /Users/matianyi/ros2_jazzy/.venv/bin/activate
  source /opt/ros/jazzy/setup.zsh
  source /Users/matianyi/ros2_jazzy/extra_ws/install/setup.zsh
  source /Users/matianyi/ros2_jazzy/so101_isolated_ws/install/setup.zsh
  export DYLD_LIBRARY_PATH="/Users/matianyi/ros2_jazzy/macos_dylib_farm/current${DYLD_LIBRARY_PATH:+:${DYLD_LIBRARY_PATH}}"
  source /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-install/setup.zsh
  export VIRTUAL_ENV=/Users/matianyi/ros2_jazzy/.venv
  export PATH="/Users/matianyi/ros2_jazzy/.venv/bin:${PATH}"
  export PYTHONNOUSERSITE=1
  export ROS_LOG_DIR=/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/ros-log
accepted_environment_preamble_before_project_test: |-
  source /Users/matianyi/ros2_jazzy/.venv/bin/activate
  source /opt/ros/jazzy/setup.zsh
  source /Users/matianyi/ros2_jazzy/extra_ws/install/setup.zsh
  source /Users/matianyi/ros2_jazzy/so101_isolated_ws/install/setup.zsh
  export DYLD_LIBRARY_PATH="/Users/matianyi/ros2_jazzy/macos_dylib_farm/current${DYLD_LIBRARY_PATH:+:${DYLD_LIBRARY_PATH}}"
  source /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-install/setup.zsh
  source /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/setup.zsh
  export VIRTUAL_ENV=/Users/matianyi/ros2_jazzy/.venv
  export PATH="/Users/matianyi/ros2_jazzy/.venv/bin:${PATH}"
  export PYTHONNOUSERSITE=1
  export SO101_SOURCE_COMMIT=208dd216f9ef52e2792830a19c1e070b8aef1778
  export ROS_LOG_DIR=/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-ros-log
accepted_commands:
  - command: |-
      colcon --log-base /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-log build --base-paths third_party/mujoco_ros2_control --build-base /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-build --install-base /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-install --packages-select mujoco_3d_lidar mujoco_ros2_control_msgs mujoco_ros2_control_plugins mujoco_ros2_control --symlink-install --event-handlers console_direct+ > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-build-command-r2.log 2>&1
      task_rc=$?; printf '%s\n' "${task_rc}" > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-build-exit-code.txt; exit "${task_rc}"
    preamble: accepted_environment_preamble_before_child_build
    exit_code: 0
    exit_code_evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-build-exit-code.txt
  - command: |-
      : > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-direct-ctest.log; task_rc=0
      for package in mujoco_3d_lidar mujoco_ros2_control_msgs mujoco_ros2_control_plugins mujoco_ros2_control; do printf 'PACKAGE=%s\n' "${package}" >> /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-direct-ctest.log; ctest --test-dir "/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-build/${package}" --output-on-failure >> /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-direct-ctest.log 2>&1; package_rc=$?; printf 'PACKAGE_EXIT=%s\n' "${package_rc}" >> /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-direct-ctest.log; if test "${package_rc}" -ne 0; then task_rc=${package_rc}; fi; done
      printf '%s\n' "${task_rc}" > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-direct-ctest-exit-code.txt; test "${task_rc}" -eq 0 || exit "${task_rc}"
      colcon test-result --test-result-base /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-build --all --verbose > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-direct-test-result-verbose-clean-scope.txt 2>&1
      task_rc=$?; printf '%s\n' "${task_rc}" > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-direct-test-result-clean-scope-exit-code.txt; exit "${task_rc}"
    preamble: accepted_environment_preamble_before_child_test
    exit_code: 0
    exit_code_evidence: [/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-direct-ctest-exit-code.txt, /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-direct-test-result-clean-scope-exit-code.txt]
  - command: |-
      colcon --log-base /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-log build --base-paths src --build-base /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-build --install-base /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install --packages-select so101_demo_py --symlink-install --event-handlers console_direct+ > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-build-command.log 2>&1
      task_rc=$?; printf '%s\n' "${task_rc}" > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-build-exit-code.txt; exit "${task_rc}"
    preamble: accepted_environment_preamble_before_child_test
    exit_code: 0
    exit_code_evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-build-exit-code.txt
  - command: |-
      python -m pytest src/so101_demo_py/test -q -o cache_dir=/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-pytest-cache > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-pytest-full.log 2>&1
      task_rc=$?; printf '%s\n' "${task_rc}" > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-pytest-full-exit-code.txt; exit "${task_rc}"
    preamble: accepted_environment_preamble_before_project_test
    result: 442 passed in 21.03 s
    exit_code: 0
    exit_code_evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-pytest-full-exit-code.txt
  - command: |-
      python -m pytest src/so101_demo_py/test/test_macos_install_contract.py src/so101_demo_py/test/test_mujoco_camera_plugin_contract.py src/so101_demo_py/test/test_mujoco_cup_test_keyframes.py src/so101_demo_py/test/test_camera_tf_contract.py src/so101_demo_py/test/test_rgbd_point_cloud.py src/so101_demo_py/test/test_rgbd_cup_pose.py src/so101_demo_py/test/test_dynamic_scene_sync.py src/so101_demo_py/test/test_perception_pick_place_launch.py src/so101_demo_py/test/test_perception_launch_runner.py -q -o cache_dir=/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-directed-pytest-cache > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-directed-pytest.log 2>&1
      task_rc=$?; printf '%s\n' "${task_rc}" > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-directed-pytest-exit-code.txt; exit "${task_rc}"
    preamble: accepted_environment_preamble_before_project_test
    result: 153 passed in 17.45 s
    exit_code: 0
    exit_code_evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-directed-pytest-exit-code.txt
  - command: |-
      python -m pytest src/so101_demo_py/test --collect-only -q -o cache_dir=/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-pytest-cache-collect > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-pytest-collect-only.log 2>&1
      task_rc=$?; printf '%s\n' "${task_rc}" > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-pytest-collect-only-exit-code.txt; exit "${task_rc}"
    preamble: accepted_environment_preamble_before_project_test
    result: 442 tests collected
    exit_code: 0
    exit_code_evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-pytest-collect-only-exit-code.txt
non_counting_out_of_root_evidence:
  path: /tmp/so101-debug-mrc010-task1/
  status: Retained, not used for CP-002 acceptance, and not part of the registered evidence root.
  disposition: Deletion candidate only; no deletion performed and explicit user authorization remains required.
retained_runs: [/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/]
archived_runs: []
deletion_candidates: [/tmp/so101-debug-mrc010-task1/, registered-root invalid environment attempts listed in CP-002]
decision: CP-002_STATIC_QUALIFICATION_REMAINS_ACCEPTED_WITH_EXPLICIT_LEAF_PACKAGE_SUBSTITUTE_GATES
```

## CP-003 / TRANS-EXP-010-RUNNING-001 — Mac live recovery and first run

```yaml
checkpoint_id: CP-003
transition_id: TRANS-EXP-010-RUNNING-001
recorded_at: 2026-08-26T23:28:16+08:00
experiment_id: EXP-010
from: PLANNED
to: RUNNING
last_valid_experiment: NONE
current_hypothesis: The frozen installed candidate completes AC-001 from task_start on macOS.
implementation_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
record_head_before_transition: 0a6be4799f017e9b088a9698457279754d7dee38
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
working_tree_status: Clean before this ledger-only transition; the immutable implementation and child checkout are unchanged.
owned_processes: NONE
preserved_processes: Four unrelated historical tmux sessions were left untouched; no live conflicting MuJoCo, MoveIt, RGB-D, workflow, or Viewer process was observed.
pre_running_observed:
  - OBSERVED: The current host is matianyideMacBook-Air.local and the task worktree, branch, implementation commit, child gitlink/checkout, and frozen candidate overlay match CP-002.
  - OBSERVED: Natural ament prefix readback resolves so101_demo_py and all four child packages to the frozen project/fork installs; the installed exact-status runner exists and has SHA256 9ade27dcc334b8cf26d203e3e6dc8b5b26e0fe46487ca4dd7539a52286f9bfd1.
  - OBSERVED: Domain 220 returned no nodes; session/partition mac-mrc010-task-start-exp010, task-owned tmux mrc010-mac-exp010, exact MuJoCo Viewer title, and the nominal evidence path were empty.
  - OBSERVED: The node-list probe itself created ros2-daemon processes for domains 220 through 223 despite the attempted no-daemon environment flag. Those exact probe-owned daemons were stopped by domain before this transition; no product process or evidence identity was created.
confirmed_conclusions:
  - CP-002 remains the last trusted static checkpoint; none of its disproven environment routes is being reused.
disproven_routes:
  - A ros2 node-list emptiness probe is not process-neutral on this Mac and must be followed by exact domain daemon cleanup before a FULL_RESTART run.
single_variable: Exercise task_start in domain 220/session mac-mrc010-task-start-exp010; implementation, overlays, policy, geometry, extrinsics, target, controller, recovery, and capture protocol remain frozen.
evidence:
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-live-preflight/host-worktree-process-window-preflight.txt
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-live-preflight/escalated-process-tmux-window-preflight.txt
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-live-preflight/exp010-exact-provenance-isolation.txt
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-live-preflight/ros-daemon-probe-cleanup.txt
decision: START_EXACT_INSTALLED_EXP_010
next_command: Commit this transition, then start only mrc010-mac-exp010 and concurrently capture baseline, transport, and final from the exact MuJoCo Viewer window ID.
```

## CLOSE-EXP-010-001 / CP-004 — Invalid stale-cwd environment run

```yaml
closure_id: CLOSE-EXP-010-001
checkpoint_id: CP-004
recorded_at: 2026-08-26T23:35:48+08:00
experiment_id: EXP-010
status: INVALID
classification: stale_tmux_server_cwd_invalid_environment
implementation_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
record_head_before_closure: 6088dc2
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
first_bad_boundary: The new tmux pane inherited the removed .worktrees/mujoco-ros2-control-0-1-upgrade cwd; getcwd failed before production perception runtime construction.
observed:
  - OBSERVED: Frozen prefixes, installed runner ownership, domain 220, session, keyframe, and child commit were exact, but lsof proved shell PID 52920 held a deleted cwd and the old pathname no longer existed.
  - OBSERVED: The log contains 11 getcwd-failed diagnostics. RGB-D perception then returned RGBD_CUP_POSE_TIMEOUT before constructing its ROS runtime; the wrapper naturally returned 1 after 11 starts, 9 clean exits, and 2 required-process deaths.
  - OBSERVED: Exact Viewer window 45233 owned by ros2_control_node was captured once at baseline. Original-resolution inspection shows the table-supported orange cup at task_start, empty red target, open gripper, and Running status. The 2504x1770 PNG SHA256 is 6ac20e8f58e3e5dd20a61740bbd75ebdb515ffd3be9e7279431fafdb2cdfd2a7.
  - OBSERVED: No accepted perception summary, point cloud, dynamic manifest, transport boundary, or final boundary exists; no product behavior conclusion is drawn.
  - OBSERVED: After product terminal, the exact capture helper was interrupted with observed status 130 because its transport boundary could no longer occur. The dead exact-owned tmux was removed; target session/process/domain-daemon/Viewer identities are absent.
inferred:
  - INFERRED: The deleted cwd contaminated middleware runtime construction. A new tmux pane created with an explicit current worktree cwd distinguishes that environment cause without modifying the product.
evidence:
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-010/run/child.owner
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-010/run/full-restart.log
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-010/run/capture-terminal-note.txt
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-010/gui/baseline-helper/20260826T233239-0b7a5ef12109/manifest.json
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-010/gui/baseline-helper/20260826T233239-0b7a5ef12109/window.png
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-010/post-cleanup.log
decision: REPEAT_AS_EXP_014_WITH_EXPLICIT_TMUX_CWD
last_valid_experiment: NONE
owned_processes: NONE
preserved_processes: All unrelated historical tmux sessions and desktop windows remain untouched.
open_risks:
  - All four Mac positions remain unqualified under the current candidate.
next_experiment: EXP-014
next_command: Commit this INVALID closure, prove EXP-014 domain/session/evidence/Viewer isolation, transition EXP-014 to RUNNING, and start its tmux pane with -c set to the current worktree.
```

## CP-005 / TRANS-EXP-014-RUNNING-001 — Clean task_start retry

```yaml
checkpoint_id: CP-005
transition_id: TRANS-EXP-014-RUNNING-001
recorded_at: 2026-08-26T23:37:34+08:00
experiment_id: EXP-014
from: PLANNED
to: RUNNING
last_valid_experiment: NONE
implementation_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
record_head_before_transition: ef62dd6d62a1d06e9290db14fc9670559eacffa6
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
working_tree_status: Clean before this ledger-only transition; immutable implementation and installed overlays are unchanged.
owned_processes: NONE
pre_running_observed:
  - OBSERVED: Current task worktree exists at /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-pick-place-mujoco-0-1-main and is the explicit tmux startup cwd for this retry.
  - OBSERVED: Domain 229 session/partition process identity, mrc010-mac-exp014 tmux, exact Viewer title, and /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-014 were empty.
  - OBSERVED: EXP-010 is terminal INVALID, its evidence remains retained, and no exact-owned product/capture process from it remains.
single_variable: Add the explicit existing task worktree as the tmux pane cwd; all product inputs and the capture protocol are unchanged from EXP-010.
evidence:
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-live-preflight/exp014-provenance-isolation.txt
decision: START_EXACT_INSTALLED_EXP_014
next_command: Commit this transition, create mrc010-mac-exp014 with tmux -c set to the task worktree, verify the pane cwd readback, and run the unchanged installed command with concurrent exact-window capture.
```

## CLOSE-EXP-014-001 / CP-006 — Explicit tmux `-c` did not satisfy cwd precondition

```yaml
closure_id: CLOSE-EXP-014-001
checkpoint_id: CP-006
recorded_at: 2026-08-26T23:41:01+08:00
experiment_id: EXP-014
status: INVALID
classification: explicit_tmux_cwd_precondition_failed
implementation_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
record_head_before_closure: 7a99fce
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
first_bad_boundary: Before product startup, tmux-start-readback recorded pane_current_path as the deleted .worktrees/mujoco-ros2-control-0-1-upgrade path instead of the pre-registered live task worktree; child pwd -P consequently produced dot.
competing_hypotheses:
  - H1: The existing shared tmux server cannot honor new-session -c while its inherited base cwd has been unlinked.
  - H2: An explicit absolute cd in the new pane command repairs cwd without restarting or disturbing the shared tmux server.
  - H3: The current task worktree itself cannot be entered from a tmux pane.
observed:
  - OBSERVED: The current task worktree existed and was clean before launch. The exact start command did include tmux new-session -c with that path, but the immediate pane readback selected the deleted historical path and the child owner recorded working_directory=dot.
  - OBSERVED: The first runtime diagnostics at 23:38:57 were getcwd failures in the MuJoCo runtime, robot_state_publisher, and both camera TF publishers; seven total processes reported the same boundary before any controller became active or scene setup completed.
  - OBSERVED: The required MuJoCo runtime later raised SIGSEGV in the physics/plugin callback and exited -11. That first terminal child caused launch-owned SIGINT; scene_setup's wait_for_service interruption and move_group SIGKILL are downstream teardown, not external interrupts.
  - OBSERVED: The exact wrapper naturally returned 245 with 9 starts, 6 clean exits, and 3 died processes. No perception process, point cloud, dynamic manifest, workflow state, transport, or final placement existed.
  - OBSERVED: Capture helper started before launch, selected exact Viewer window 45252/PID 56131, and preserved one inspected 2504x1770 baseline. It performed no signal action and was interrupted with observed status 130 only after product terminal.
  - OBSERVED: Original-resolution inspection shows task_start cup on table, red target empty, gripper open, and Viewer Running. PNG SHA256 is 7658774a607b0ee35e1c3499eb6727b7a0c5a9edfeddd1182ebf4ca09ecbfc04.
  - OBSERVED: Exact-owned tmux was removed after terminal; target session/process/domain-daemon/Viewer identities are absent. Unrelated tmux sessions/windows remain preserved.
classification_rationale:
  - The pre-registered EXP-014 invalid criterion includes cwd/process isolation, and that precondition failed before any product boundary. Therefore this is INVALID even though the later MuJoCo SIGSEGV is observed; no claim that cwd caused SIGSEGV is necessary or made.
evidence:
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-014/run/tmux-start-readback.txt
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-014/run/child.owner
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-014/run/full-restart.log
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-014/run/capture.owner
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-014/run/capture-terminal-note.txt
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-014/gui/baseline-helper/20260826T233909-4f14a62519c6/manifest.json
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-014/gui/baseline-helper/20260826T233909-4f14a62519c6/window.png
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-014/post-cleanup.log
decision: RUN_NON_PRODUCT_TMUX_CWD_AB_BEFORE_NEW_EXPERIMENT
last_valid_experiment: NONE
owned_processes: NONE
open_risks:
  - Whether explicit in-pane cd repairs the stale shared tmux server cwd is not yet observed.
  - No current-candidate Mac position is qualified.
next_experiment: NONE
next_command: Commit this INVALID closure, then run a task-owned empty tmux A/B that records pwd for -c alone versus explicit absolute cd; do not start ROS or MuJoCo.
```

## CP-007 — tmux cwd A/B root cause and repaired retry plan

```yaml
checkpoint_id: CP-007
recorded_at: 2026-08-26T23:42:32+08:00
last_valid_experiment: NONE
current_hypothesis: Explicit absolute cd inside the new pane command repairs only the shared tmux server cwd contamination and permits a clean unchanged task_start run.
implementation_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
record_head_before_checkpoint: c71a099
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
working_tree_status: Clean before this ledger-only checkpoint; no production or installed artifact changed.
owned_processes: NONE
ab_result:
  - OBSERVED: Probe A used tmux new-session -c with the live task worktree but no in-pane cd. The pane still reported the deleted historical worktree and pwd -P produced dot.
  - OBSERVED: Probe B used the same tmux server and -c option but added an explicit absolute cd in the pane command. Both pane_current_path and pwd -P reported the live task worktree exactly.
  - OBSERVED: Neither probe sourced ROS nor started MuJoCo. Both task-owned sessions were removed and are absent.
root_cause:
  - CONFIRMED: The existing shared tmux server does not honor new-session -c while its inherited base cwd is unlinked; explicit in-pane cd repairs cwd without restarting or disturbing that shared server.
  - H1 confirmed; H2 confirmed; H3 disproved.
evidence:
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-live-preflight/cwd-probe-a.txt
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-live-preflight/cwd-probe-b.txt
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-live-preflight/cwd-ab-readback.txt
decision: PLAN_EXP_015_WITH_EXPLICIT_IN_PANE_CD
next_experiment: EXP-015
```

```yaml
experiment_id: EXP-015
status: VALID_FAILURE
prior_experiment: EXP-014
hypothesis: The unchanged frozen candidate completes task_start AC-001 when the exact-owned pane performs an observed explicit cd to the live worktree before sourcing or starting ROS.
prediction: Pane and child cwd readbacks are exact, getcwd failures are zero, RGB-D perception succeeds, and the full physical workflow releases the cup stably in the red target.
single_variable: Replace ineffective tmux -c-only cwd binding with explicit in-pane absolute cd; product command, overlays, keyframe, policy, geometry, thresholds, and capture protocol remain unchanged.
lifecycle: FULL_RESTART
preconditions:
  - EXP-014 is terminal INVALID and all its exact-owned identities are absent; A/B probe sessions are absent.
  - The immutable candidate and child are unchanged and clean.
  - Domain 230, session mac-mrc010-task-start-retry-exp015, mrc010-mac-exp015, exact Viewer title, and the evidence path are empty.
  - tmux pane_current_path and child pwd readback must equal /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-pick-place-mujoco-0-1-main.
success_criteria:
  - AC-001 passes every clause and getcwd-failed count is zero.
failure_criteria:
  - All preconditions pass but any AC-001 product clause fails.
invalid_criteria:
  - Provenance, cwd/process isolation, GUI freshness, or evidence ownership is missing.
provenance:
  source_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
  install_overlay: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install
  runtime_executable: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 230
  gz_partition: mac-mrc010-task-start-retry-exp015
commands:
  - command: ROS_DOMAIN_ID=230 GZ_PARTITION=mac-mrc010-task-start-retry-exp015 ros2 run so101_demo_py so101_mujoco_perception_pick_place run_mode:=execute execute:=true headless:=false session_id:=mac-mrc010-task-start-retry-exp015 mujoco_initial_keyframe:=task_start evidence_file:=/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-015/task-start-retry.json
    exit_code: 245
observed:
  - Pane and child cwd readbacks equal the live task worktree, exact installed source/fork/project provenance is recorded, and getcwd-failed count is zero.
  - The candidate loaded and initialized mujoco_camera_plugin and simulation_evidence, then ros2_control_node died with SIGSEGV -11 on the first physics pre-step callback; wrapper exit is 245.
  - Nine ROS processes started; six exited cleanly, scene_setup exited 1 after launch shutdown, ros2_control_node exited -11, and move_group exited -9 after bounded teardown.
  - GUI helper resolved exact Viewer window 45272 but AXRaise failed after the early product crash, so EXP-015 has no countable capture and no PNG is claimed.
  - Exact-owned tmux, domain/session processes, and Viewer are absent after cleanup; four unrelated tmux sessions remain untouched.
inferred:
  - Candidate project-build/project-install contain no so101_mujoco_support package. Pluginlib resolved the 2026-08-14 isolated-workspace SimulationEvidencePlugin, whose CMakeCache points to the old mujoco_ros2_control_plugins install.
  - Child 738e304's base vtable uses the slot after update for on_physics_step(model,data), while 5e9d67c uses that slot for pre_step(data). The crash report contains both the candidate runtime UUID and the stale plugin UUID and faults precisely at plugin->pre_step(data).
conclusion: VALID behavioral failure. The installed candidate is incomplete across an ABI boundary; all four Mac positions remain unqualified and the consecutive batch stops.
evidence:
  - /tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-015
  - /Users/matianyi/Library/Logs/DiagnosticReports/ros2_control_node-2026-08-26-234448.ips
decision: STOP_BATCH_REBUILD_ABI_DEPENDENT_SUPPORT_BEFORE_NEW_QUALIFICATION
next_experiment: NONE
```

## CP-008 / TRANS-EXP-015-RUNNING-001 — A/B-proven cwd repair

```yaml
checkpoint_id: CP-008
transition_id: TRANS-EXP-015-RUNNING-001
recorded_at: 2026-08-26T23:43:28+08:00
experiment_id: EXP-015
from: PLANNED
to: RUNNING
last_valid_experiment: NONE
implementation_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
record_head_before_transition: 33ba47d37bd924bbc96795eeba0f6fff897e1b98
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
working_tree_status: Clean before this ledger-only transition; implementation, installed overlays, and child are unchanged.
owned_processes: NONE
pre_running_observed:
  - OBSERVED: Current task worktree and child are exact; domain 230/session process identity, mrc010-mac-exp015, exact Viewer title, and the EXP-015 evidence path are empty.
  - OBSERVED: CP-007 non-product A/B proves the explicit in-pane absolute cd produces the exact live worktree on this preserved shared tmux server.
single_variable: Apply only the A/B-proven in-pane cd before the unchanged installed product command.
evidence:
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-live-preflight/exp015-provenance-isolation.txt
decision: START_EXACT_INSTALLED_EXP_015
next_command: Commit this transition, start exact-owned mrc010-mac-exp015 with explicit in-pane cd, verify pane and child cwd readbacks, and concurrently capture the three exact-window boundaries.
```

## CP-009 / CLOSE-EXP-015-001 — Valid runtime crash stops Mac batch

```yaml
checkpoint_id: CP-009
transition_id: CLOSE-EXP-015-001
recorded_at: 2026-08-26T23:52:18+08:00
experiment_id: EXP-015
from: RUNNING
to: VALID_FAILURE
last_valid_experiment: NONE
implementation_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
record_head_before_transition: f1d2744fbf5a44c179bb6c8bd66d6bd723ebcf98
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
working_tree_status: Implementation and frozen installs were unchanged during EXP-015; this closure changes only the ledger.
first_bad_boundary:
  - All registered environment, cwd, ownership, and frozen executable checks passed.
  - Both configured plugins initialized; the first authoritative physics pre-step fanout called plugin->pre_step(data) and ros2_control_node died SIGSEGV -11.
root_cause:
  status: CONFIRMED
  hypothesis: Task 3 omitted ABI-dependent so101_mujoco_support from candidate project-build/install, allowing the new 0.1.0 runtime to load the old plugin vtable.
  evidence:
    - Candidate project-build/project-install have no so101_mujoco_support prefix, plugin XML, or dylib.
    - Runtime pluginlib resource and plugin UUID 909C9671-8ACF-3018-8014-5516D2A54918 resolve to the 2026-08-14 isolated-workspace package; its CMakeCache targets the old fork prefix.
    - Candidate runtime UUID CC34CCF1-ACC8-39A9-A7A1-543C105E0015 appears in the crash report and contains the failing pre_step callback.
    - The base virtual slot changed from old on_physics_step(model,data) to new pre_step(data); the stale dylib is therefore ABI-incompatible at the exact faulting call.
  alternatives:
    - Camera rendering failure is disproved as the immediate boundary: the camera plugin initialized, has a current-ABI default pre_step, and its update thread remained waiting in the crash report.
    - External signal is disproved: capture failed only after the product crash, performed no signal, and the crash is EXC_BAD_ACCESS on the physics thread.
    - Stale cwd is disproved for EXP-015 by exact tmux/child readbacks and zero getcwd diagnostics.
cleanup:
  - mrc010-mac-exp015 removed; no domain 230/session process or exact Viewer remains.
  - Unrelated tmux sessions mrc010-exp013-final-stack, mrc010-exp013-smoke-r3, mrc010-macos-task7a-r4, and mrc010-macos-task7a-r5 were preserved.
  - Evidence was retained; nothing was deleted.
evidence:
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-015/run/full-restart.log
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-015/run/child.owner
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-015/run/cleanup.txt
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-015/diagnosis/root-cause-boundary.md
  - /Users/matianyi/Library/Logs/DiagnosticReports/ros2_control_node-2026-08-26-234448.ips
decision: STOP_MAC_BATCH_AND_REQUIRE_RED_RUNTIME_CONTRACT_PLUS_CLEAN_SUPPORT_REBUILD
next_experiment: NONE
```

## CP-010 — RED candidate support-plugin provenance contract

```yaml
checkpoint_id: CP-010
recorded_at: 2026-08-26T23:56:16+08:00
phase: RED
implementation_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
record_head_before_change: f2fed42
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
contract:
  - When so101_demo_py is selected from the isolated candidate project overlay, so101_mujoco_support must resolve from the same project-install base.
  - That support prefix must contain the pluginlib XML and libso101_simulation_evidence_plugin with the host platform suffix.
red_command: zsh /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/support-abi-red.zsh
red_nodeid: src/so101_demo_py/test/test_installed_provenance.py::test_mujoco_support_plugin_comes_from_the_candidate_project_overlay
red_exit_code: 1
observed:
  - Expected support prefix is /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_mujoco_support.
  - Actual support prefix is /Users/matianyi/ros2_jazzy/so101_isolated_ws/install/so101_mujoco_support.
  - The assertion fails before artifact checks, exactly detecting Task 3's omitted ABI-dependent package.
planned_single_fix:
  - Build so101_mujoco_support and so101_demo_py into the candidate project build/install against the frozen fork overlay; do not change product source behavior.
evidence:
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/support-abi-red.zsh
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-015/diagnosis/root-cause-boundary.md
decision: COMMIT_RED_THEN_CLEAN_BUILD_SUPPORT
next_experiment: NONE
```

## CP-011 — GREEN ABI-aligned support install

```yaml
checkpoint_id: CP-011
recorded_at: 2026-08-27T00:01:32+08:00
phase: GREEN
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_change: 74a65234551527fb5483366aa06a79a8f5efacfe
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
single_fix:
  - Built source package so101_mujoco_support, followed by so101_demo_py, into the existing isolated candidate project build/install after the candidate fork overlay.
  - No grasp, policy, geometry, extrinsics, controller, camera, recovery, or runtime orchestration source changed.
installed_provenance:
  support_prefix: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_mujoco_support
  support_cmake_dependency: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-install/mujoco_ros2_control_plugins
  plugin_sha256: f4487cc3e2467e2ffec5b2ca2fa407d8c372b63cfe07cc1e71e777185d1a7ab7
  plugin_uuid: 74A169FE-F055-3D0D-A333-9F7F7BAEF574
  plugin_symbols:
    - MuJoCoROS2ControlPluginBase::pre_step(mjData_*)
    - SimulationEvidencePlugin::update(mjModel_ const*, mjData_*)
    - SimulationEvidencePlugin::on_physics_step(mjModel_ const*, mjData_ const*) through the separate observer interface
tests:
  - focused installed prefix/XML/dylib contract: 1 passed in 0.40 s
  - support direct CTest: 1/1 passed; test_simulation_evidence_plugin, 4.48 s
  - full project pytest: 443/443 passed in 20.36 s
  - ros2 package readback selects candidate project-install for both so101_demo_py and so101_mujoco_support
evidence:
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/build-support-green.zsh
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/test-support-green.zsh
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/test-project-green.zsh
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-log-support-r1
decision: COMMIT_GREEN_THEN_RUN_NON_QUALIFICATION_CRASH_BOUNDARY_SMOKE
next_experiment: NONE
```

## CP-012 — Plan non-qualification ABI crash-boundary smoke

```yaml
checkpoint_id: CP-012
recorded_at: 2026-08-27T00:03:21+08:00
smoke_id: SMOKE-001
status: RUNNING
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_change: 05200680b07487abed9419003e91d65fa51a0246
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
hypothesis: The ABI-aligned candidate support plugin crosses the first authoritative physics pre_step boundary without the EXP-015 SIGSEGV.
single_variable: Replace only the stale isolated-workspace support plugin with the candidate project-overlay support plugin built at CP-011.
command_scope:
  - Launch the installed base MuJoCo stack, not the perception or dynamic pick-place workflow.
  - Use headless=false only to exercise the same camera/rendering/plugin combination.
  - Observe active controllers, advancing simulation evidence, and process survival for at least ten seconds past the prior crash boundary; then send one owned SIGINT for controlled shutdown.
preconditions:
  - Domain 231, session mac-mrc010-abi-smoke-r1, task tmux mrc010-mac-abi-smoke-r1, exact Viewer title, and evidence path are empty.
  - Candidate demo, support, and fork prefixes are the CP-011 overlays.
  - Unrelated historical tmux sessions and windows remain untouched.
success_criteria:
  - Both plugins initialize, physics advances for at least ten seconds beyond initialization, ros2_control_node remains alive, and no SIGSEGV/pre_step crash occurs.
  - Owned SIGINT produces bounded clean shutdown with no domain/session/tmux/Viewer residue.
failure_criteria:
  - Any product process dies before the owned stop, physics evidence does not advance, or the old pre_step SIGSEGV recurs.
evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-smoke/abi-r1
decision: COMMIT_PLAN_THEN_TRANSITION_RUNNING
next_experiment: SMOKE-001
```

## CP-013 / TRANS-SMOKE-001-RUNNING-001 — Start ABI smoke

```yaml
checkpoint_id: CP-013
transition_id: TRANS-SMOKE-001-RUNNING-001
recorded_at: 2026-08-27T00:03:50+08:00
smoke_id: SMOKE-001
from: PLANNED
to: RUNNING
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: a8b913424374f5c2c1932aa646af714860240cd8
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
pre_running_observed:
  - Candidate worktree is clean; installed prefix contract, support CTest, and 443-case project suite are GREEN.
  - Domain 231/session process identity, task tmux, exact Viewer title, and evidence path are empty.
owned_processes: NONE
decision: START_BASE_STACK_SMOKE
next_command: Start exact-owned tmux with explicit live-worktree cd, observe the old crash boundary plus five seconds, then send SIGINT only to the owned pane.
```

## CP-014 / CLOSE-SMOKE-001-001 — ABI-aligned support crosses crash boundary

```yaml
checkpoint_id: CP-014
transition_id: CLOSE-SMOKE-001-001
recorded_at: 2026-08-27T00:10:09+08:00
smoke_id: SMOKE-001
from: RUNNING
to: PASS_NON_QUALIFYING
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: 7d0cf1d
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
runtime_identity:
  domain: 231
  session: mac-mrc010-abi-smoke-r1
  tmux: mrc010-mac-abi-smoke-r1
  ros2_control_pid: 64876
  support_prefix: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_mujoco_support
  loaded_plugin: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_mujoco_support/lib/libso101_simulation_evidence_plugin.dylib
  loaded_plugin_sha256: f4487cc3e2467e2ffec5b2ca2fa407d8c372b63cfe07cc1e71e777185d1a7ab7
  loaded_plugin_uuid: 74A169FE-F055-3D0D-A333-9F7F7BAEF574
  old_isolated_plugin_loaded: false
observations:
  - MuJoCo physics thread started at 1787760321.650565; camera plugin initialized at 1787760324.136948; simulation_evidence initialized at 1787760324.247731; hardware activated at 1787760324.251299.
  - Direct same-domain rclpy observer exited zero after samples 16571 and 16572 advanced simulation_step 90989 to 90994 for exact session mac-mrc010-abi-smoke-r1.
  - gripper_controller, joint_state_broadcaster, and arm_controller all configured and activated; scene_setup READ_BACK succeeded.
  - One Ctrl-C was sent only to the exact owned tmux pane at 1787760545.692; the candidate plugin therefore survived 221.44 s beyond its initialization and 224.04 s beyond physics-thread start.
  - Log contains no SIGSEGV, segmentation fault, process died, exit code -11, or unexpected child exit before the owned stop.
shutdown:
  - controller manager deactivated and shut down all three controllers and RobotSystem.
  - so101_move_group emitted SO101_MOVE_GROUP_ORDERED_SHUTDOWN_OK; move_group, robot_state_publisher, and ros2_control_node all reported clean process exit.
  - Post-cleanup process-environment scan found no ROS_DOMAIN_ID=231, session, or smoke-tmux process; exact tmux is absent and GUI inventory contains no Viewer window.
  - Historical unrelated tmux sessions mrc010-exp013-final-stack, mrc010-exp013-smoke-r3, mrc010-macos-task7a-r4, and mrc010-macos-task7a-r5 remain untouched.
known_observation_gap:
  - Ctrl-C reached the foreground launch and pane shell, so the wrapper did not write exit-code.txt or finished-at.txt. Component-level ordered clean-exit records and exact absence readback establish bounded cleanup; no wrapper exit code is claimed.
evidence:
  owner: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-smoke/abi-r1/owner.txt
  owner_sha256: 34d836ee13a4524a3444d791e2fd815877ca96bccace418ed41b6f987269635f
  log: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-smoke/abi-r1/full.log
  log_sha256: 151c45de34bd1844ae978705ba83474fb564f765b686f4936d2700ac7899e417
  observer: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-smoke/abi-r1/observer-result.json
  observer_sha256: 6aa71fdb317c795adea142568980092430c66226ab093f1f79efa034331cb0b3
  loaded_plugin: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-smoke/abi-r1/loaded-plugin.txt
  loaded_plugin_sha256: 030cec1caa40138f0f7f1dc9232778dc4ec807869f73b3353c342de16e7bf9cf
decision: PASS_NON_QUALIFYING_ABI_SMOKE
next_experiment: EXP-016
```

## CP-015 — Plan rebuilt-candidate task_start qualification

```yaml
checkpoint_id: CP-015
recorded_at: 2026-08-27T00:12:16+08:00
experiment_id: EXP-016
status: PLANNED
qualification: true
position: task_start
lifecycle: FULL_RESTART
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
production_source_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
record_head_before_checkpoint: 1f5a12d20a17f24a7304a55bf4b79b67afcd7c14
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
hypothesis: The ABI-aligned installed candidate completes every AC-001 clause from task_start on macOS.
single_variable_from_smoke: Replace the non-qualifying base-stack smoke with the exact installed perception pick-place workflow; installed overlays, product policy, geometry, camera extrinsics, target, controller, and recovery remain frozen.
identity:
  domain: 232
  session: mac-mrc010-task-start-exp016
  partition: mac-mrc010-task-start-exp016
  tmux: mrc010-mac-exp016
  evidence_file: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-016/task-start.json
  evidence_root: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-016
command: ros2 run so101_demo_py so101_mujoco_perception_pick_place run_mode:=execute execute:=true headless:=false session_id:=mac-mrc010-task-start-exp016 mujoco_initial_keyframe:=task_start evidence_file:=/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-016/task-start.json
preconditions:
  - SMOKE-001 is terminal PASS_NON_QUALIFYING; its exact owned domain/session/tmux/Viewer identities are absent.
  - Worktree and child checkout are exact and clean; installed demo/support/fork prefixes and bundle hashes are freshly read back before RUNNING.
  - Domain 232, session identity, mrc010-mac-exp016, exact Viewer title, and the entire EXP-016 evidence path are empty.
  - Product tmux command starts with an explicit absolute in-pane cd and both pane and child cwd read back as the live worktree.
capture_protocol:
  - Resolve one exact MuJoCo : so101_task_scene Viewer window ID and retain the same ID for all captures.
  - Capture and preserve helper manifest plus PNG at baseline, transport, and released-final live-manifest boundaries.
  - Inspect all three PNGs at original resolution before classification.
success_criteria:
  - Every AC-001 perception, TF, no-truth-bridge, workflow, motion, physical-contact, Planning Scene, capture, exit, and cleanup clause passes from same-session evidence.
failure_criteria:
  - Preconditions and provenance are valid but any AC-001 product clause fails; stop the four-position batch for systematic debugging.
invalid_criteria:
  - Provenance, source order, cwd/process isolation, exact-window capture freshness, or evidence ownership is concretely invalid; retain evidence and use a fresh experiment ID.
sequence_gate: EXP-017 forward is forbidden until EXP-016 has a committed countable-success closure.
decision: COMMIT_PLAN_THEN_PREFLIGHT
next_experiment: EXP-016
```

## CP-016 / TRANS-EXP-016-RUNNING-001 — Start rebuilt-candidate task_start qualification

```yaml
checkpoint_id: CP-016
transition_id: TRANS-EXP-016-RUNNING-001
recorded_at: 2026-08-27T00:15:39+08:00
experiment_id: EXP-016
from: PLANNED
to: RUNNING
qualification: true
position: task_start
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
production_source_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
record_head_before_transition: 9f9670626b2e1e630106c9c7d33c7d7c9018d5a2
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
working_tree_status: Clean before this ledger-only transition; no production source or installed artifact changed after CP-011.
pre_running_observed:
  - Domain 232 and exact session process identity, mrc010-mac-exp016, exact Viewer title, and the entire EXP-016 evidence path are empty; preflight created no ROS daemon.
  - Candidate demo/support/fork prefixes resolve to the registered frozen overlays; exact installed runner SHA256 is 9ade27dcc334b8cf26d203e3e6dc8b5b26e0fe46487ca4dd7539a52286f9bfd1.
  - Installed support plugin SHA256 f4487cc3e2467e2ffec5b2ca2fa407d8c372b63cfe07cc1e71e777185d1a7ab7 and UUID 74A169FE-F055-3D0D-A333-9F7F7BAEF574 match the passing ABI smoke.
  - Installed bundle SHA256 is e2d777dfa2d925998583b8c1b376f063ec47f476d98402297701b541da455175 under SO101_SOURCE_COMMIT 74a6523.
  - Frozen task-owned runner and capture helpers pass zsh syntax checks; capture uses the same exact Viewer window ID at all three live-manifest boundaries.
evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-live-preflight/exp016-provenance-isolation.txt
owned_processes: NONE
decision: START_EXACT_INSTALLED_EXP_016
next_command: Commit this transition; create only mrc010-mac-exp016 with explicit in-pane absolute cd; verify pane and child cwd; run the exact installed command and same-ID three-boundary GUI capture.
```

## CP-017 / CLOSE-EXP-016-001 — Valid RGB-D runtime-construction timeout

```yaml
checkpoint_id: CP-017
transition_id: CLOSE-EXP-016-001
recorded_at: 2026-08-27T00:20:46+08:00
experiment_id: EXP-016
from: RUNNING
to: VALID_FAILURE
qualification: true
position: task_start
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
production_source_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
record_head_before_transition: 3dc08029a00311c2bb1f7b96d50a8097e17f8c0c
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
classification: VALID_BEHAVIORAL_FAILURE
first_bad_boundary: rgbd_cup_pose exited 1 with RGBD_CUP_POSE_TIMEOUT and message startup deadline expired during ROS runtime construction before creating summary.json or cup.ply.
validity_basis:
  - Explicit in-pane cd repaired the shared tmux cwd; pane and child readbacks equal the live task worktree and the log contains zero getcwd failures.
  - Domain 232, session, evidence path, task tmux, and exact Viewer were fresh; owner readback records the exact demo/support/fork prefixes, installed bundle e2d777dfa2d925998583b8c1b376f063ec47f476d98402297701b541da455175, runner SHA 9ade27dc, and ABI-aligned support SHA f4487cc3/UUID 74A169FE.
  - Candidate camera and simulation_evidence plugins initialized without SIGSEGV; all three controllers activated and Planning Scene READ_BACK succeeded before perception started.
observed:
  - Eleven ROS processes started. The wrapper naturally exited 1; nine processes exited cleanly, rgbd_cup_pose exited 1, and dynamic_cup_pick_place exited -2 only after launch-owned SIGINT teardown.
  - Perception and dynamic evidence directories were exclusively created, but no summary, PLY, dynamic manifest, point-cloud, cup-pose, state-machine, trajectory, contact, or final-placement evidence exists.
  - No truth bridge was introduced; no product motion began. Dynamic exit -2 and KeyboardInterrupt are downstream of the required perception exit and are not separate root causes.
capture:
  - GUI helper selected exact Viewer window 45303/PID 66158 and preserved one fresh 2504x1770 baseline manifest/PNG.
  - Original-resolution inspection shows the task_start cup table-supported, red target empty, gripper open, and Viewer Running.
  - Transport/final boundaries never existed. After product terminal the exact capture PID was stopped with SIGINT and returned 130; no transport or final image is claimed.
  - baseline_png_sha256: 82e1e84573635879cc59e54e16d43e6a635d6f85b691afd7dc9ecccf291c4439
  - baseline_manifest_sha256: adf4acc65089bb4d75cf169640a2484786ec1083368982ffd1b68048af7dcdad
cleanup:
  - Exact owned product tmux, capture PID, domain/session processes, all eleven owned PIDs, and exact Viewer are absent.
  - Historical unrelated tmux sessions remain untouched; no evidence was deleted.
evidence:
  owner: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-016/run/child.owner
  owner_sha256: 888bf908218a22b9f19d9409e83116277c33a030861f1a790b7c209979f37f9c
  log: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-016/run/full-restart.log
  log_sha256: 8a6a06e77f82ea563e736a37e9f3b3b82b791116b89b4b6190290579acf100d6
  baseline_manifest: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-016/gui/baseline-helper/20260827T001704-01ac7fe6b42d/manifest.json
  baseline_png: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-016/gui/baseline-helper/20260827T001704-01ac7fe6b42d/window.png
  cleanup: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-016/post-cleanup.txt
decision: STOP_BATCH_AND_DEBUG_RGBD_RUNTIME_CONSTRUCTION
next_experiment: NONE
```

## CP-018 — Plan non-qualification runtime-contention A/B

```yaml
checkpoint_id: CP-018
recorded_at: 2026-08-27T00:27:16+08:00
smoke_id: SMOKE-002
status: PLANNED
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_checkpoint: 17dd8fd15bdf6d8f0bf37445a7b5c0af729b0b23
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
problem: EXP-016 exceeded the 30 s startup budget after Open3D preflight but before ROS runtime construction returned.
empty_graph_control:
  - Fresh-process probes in legal domains 224, 225, and 226 all exited zero with total construction 6.686 to 6.782 s.
  - Open3D import used 3.303 to 3.384 s and rclpy create_node used 2.847 to 2.872 s; no other segment exceeded 0.25 s.
  - Fast DDS rejects domains above 232, so 233 through 235 are invalid diagnostic attempts and may not be reused for qualification.
hypothesis: A live MuJoCo camera/physics plus MoveIt/controller stack causes CPU or thread contention that stretches one measured Open3D/ROS construction segment past 30 s.
single_variable: Run the same staged timing probe in the same ROS domain while the exact installed base stack is live; do not start rgbd_cup_pose, dynamic_cup_pick_place, or any pick-place workflow.
identity:
  domain: 227
  session: mac-mrc010-runtime-contention-r1
  tmux: mrc010-mac-runtime-contention-r1
  evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/runtime-contention-r1
method:
  - Start exact installed base MuJoCo stack with headless=false and explicit in-pane cwd.
  - Wait for ABI-aligned plugins, all three controllers, and Planning Scene READ_BACK.
  - Run the frozen timing probe in the same domain with a 120 s external bound; record segment JSON and rc.
  - Send one SIGINT only to the exact owned base-stack tmux and prove bounded cleanup.
success_criteria: The A/B identifies whether Open3D import, ROS API load, rclpy init, create_node, TF listener, publisher, or subscriptions accounts for the EXP-016 overrun.
failure_criteria: No segment reproduces the overrun; retain the result and reject the contention hypothesis rather than changing timeout.
decision: COMMIT_PLAN_THEN_RUN_NON_QUALIFYING_AB
next_experiment: SMOKE-002
```

## CP-019 / TRANS-SMOKE-002-RUNNING-001 — Start runtime-contention A/B

```yaml
checkpoint_id: CP-019
transition_id: TRANS-SMOKE-002-RUNNING-001
recorded_at: 2026-08-27T00:28:28+08:00
smoke_id: SMOKE-002
from: PLANNED
to: RUNNING
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: 6892c87bcfff4e38fc184b5a90c59f0ad020d5fa
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
pre_running_observed:
  - Domain 227/session process identity, mrc010-mac-runtime-contention-r1, exact Viewer title, and diagnosis evidence path are empty.
  - Worktree is clean; installed candidate prefixes remain frozen and SMOKE-001's ABI-aligned plugin is unchanged.
  - Base runner and timing probe pass syntax/readback; SHA256 values are 41d02e347ff3982d35afc8707e4119e1f3888e2f61b0b67d335bc9360425727e and a0e6083edc8953a73562e80ad7da5871579e01aaf584c9ec2160ee50f6566d91.
owned_processes: NONE
decision: START_NON_QUALIFYING_BASE_STACK_AB
next_command: Commit transition, start exact-owned base stack with explicit cwd, wait for all readiness markers, run same-domain timing probe under 120 s bound, then exact SIGINT cleanup.
```

## CP-020 / CLOSE-SMOKE-002-001 — Live stack amplifies but does not alone exhaust startup budget

```yaml
checkpoint_id: CP-020
transition_id: CLOSE-SMOKE-002-001
recorded_at: 2026-08-27T00:33:24+08:00
smoke_id: SMOKE-002
from: RUNNING
to: PASS_DIAGNOSTIC
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: cad4f4f84c8e43de3b7eae5ee9797f7a7a8c61e4
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
control_result:
  - Three fresh-process empty-graph probes in domains 224 through 226 exited zero at 6.686, 6.691, and 6.782 s total.
  - Domains 233 through 235 are invalid because Fast DDS rejects domain IDs above 232; no product conclusion uses them.
live_stack_result:
  - Exact candidate camera/support plugins, all three controllers, MoveIt, and Planning Scene reached steady-state READ_BACK in domain 227.
  - The same-domain probe exited zero under its 120 s bound at 17.142 s, a 2.56x slowdown but still below the 30 s product startup deadline.
  - Open3D import grew from 3.318 to 9.010 s (2.72x) and rclpy create_node from 2.847 to 6.821 s (2.40x); other individual resource segments remained below 0.50 s.
  - During the probe ros2_control_node used about 146 to 149% CPU, move_group about 24 to 25%, WindowServer about 35%, and an unrelated preserved VS Code helper about 99 to 100%.
inference:
  - Live stack CPU/thread contention is real and explains much of EXP-016's reduced margin, but a steady-state stack plus one probe does not reproduce the >30 s failure.
  - The remaining product-only variable is simultaneous scene-success startup of rgbd_cup_pose and dynamic_cup_pick_place; launch sequencing/concurrent startup must be tested before changing timeout.
shutdown:
  - One SIGINT was sent only to the exact owned base tmux. Controller/RobotSystem teardown, move_group ordered shutdown, robot_state_publisher, and ros2_control_node all completed cleanly.
  - Domain 227/session/tmux/Viewer residue is absent; unrelated sessions/processes were preserved.
  - Ctrl-C ended the pane before wrapper exit files were written; component clean exits and absence readback are claimed, not a wrapper rc.
evidence:
  owner: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/runtime-contention-r1/owner.txt
  owner_sha256: 1f231c3dd77ef5d8dd69802a9b6787ed8024a293b07846f0bde2eba20b4ea87a
  base_log: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/runtime-contention-r1/base-stack.log
  base_log_sha256: 23b4e9d2b172da9533d131580363de6af687a7b2726c32e9e0ad59523f86c567
  timing: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/runtime-contention-r1/timing-result.txt
  timing_sha256: caa1fc2412c49633ed8149366f1a58ede2c0f303ed75854e775863e057600126
decision: RETAIN_RESULT_AND_PLAN_CONCURRENT_STARTUP_AB
next_experiment: NONE
```

## CP-021 — Plan scene-success concurrent-startup A/B

```yaml
checkpoint_id: CP-021
recorded_at: 2026-08-27T00:34:41+08:00
smoke_id: SMOKE-003
status: PLANNED
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_checkpoint: 49a0e3a8f01bc16a045951cd166f46bdcd2d7bf2
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
hypothesis: With the live stack already reducing runtime-construction margin to 17.14 s, simultaneous startup of dynamic_cup_pick_place at scene success supplies the remaining contention that can push rgbd_cup_pose construction past 30 s.
single_variable: At steady-state Scene READ_BACK, start the frozen timing probe and exact installed dynamic_cup_pick_place on one barrier; retain the same low-rate GUI polling coordinator shape that was active in EXP-016.
identity:
  domain: 228
  session: mac-mrc010-concurrent-startup-r1
  tmux: mrc010-mac-concurrent-startup-r1
  evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/concurrent-startup-r1
dynamic_scope:
  - backend mujoco, mode execute, execute flag, scene_source observe_only, expected reset epoch zero.
  - No /cup_pose publisher is started, so dynamic can only construct its source and wait; it cannot plan or move.
  - Dynamic timeout/exit due absent /cup_pose is expected diagnostic behavior, not a product result.
method:
  - Start exact installed base stack headless=false; wait for both plugins, all controllers, and Planning Scene READ_BACK.
  - Barrier-start timing probe plus installed dynamic wait, capture their separate stdout/stderr/rc/wall time, CPU snapshots, and impose a 120 s observer bound.
  - Stop polling coordinator and base stack by exact owned identity, then prove domain/session/tmux/Viewer cleanup.
decision_rule:
  - If timing construction exceeds 30 s, concurrent scene-success startup reproduces the EXP-016 boundary and launch sequencing needs a TDD fix: start perception earlier while leaving dynamic scene-gated.
  - If it stays below 30 s, reject this reproduction and do not change timeout or launch sequencing without a new discriminating RED.
decision: COMMIT_PLAN_THEN_RUN_CONCURRENT_AB
next_experiment: SMOKE-003
```

## CP-022 / TRANS-SMOKE-003-RUNNING-001 — Start concurrent-startup A/B

```yaml
checkpoint_id: CP-022
transition_id: TRANS-SMOKE-003-RUNNING-001
recorded_at: 2026-08-27T00:36:21+08:00
smoke_id: SMOKE-003
from: PLANNED
to: RUNNING
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: cf0b45fe36ab6c578a90fd110d254c028ace9a19
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
pre_running_observed:
  - Domain 228/session process identity, task tmux, exact Viewer, and diagnosis evidence path are empty.
  - Worktree is clean; base, barrier-orchestrator, and GUI polling helpers pass syntax checks with SHA256 7f9b74a7, c63e948a, and bf207075.
  - A shell-level python command was unavailable before activating the frozen venv; the venv interpreter syntax check is GREEN and no diagnostic state was created by that observer error.
owned_processes: NONE
decision: START_NON_QUALIFYING_CONCURRENT_AB
next_command: Commit transition; start base/capture; wait Scene READ_BACK; barrier-start timing plus installed dynamic wait; exact cleanup.
```

## CP-023 / CLOSE-SMOKE-003-001 — Concurrent dynamic startup does not reproduce the deadline overrun

```yaml
checkpoint_id: CP-023
transition_id: CLOSE-SMOKE-003-001
recorded_at: 2026-08-27T00:43:32+08:00
smoke_id: SMOKE-003
from: RUNNING
to: PASS_DIAGNOSTIC_HYPOTHESIS_REJECTED
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: 235608efdab55f02369aa53e1f44cd07afd048fd
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
readiness:
  - Exact candidate camera/support plugins, all three controllers, MoveIt, and Planning Scene reached READ_BACK success in legal domain 228.
  - The low-rate exact-Viewer GUI coordinator captured its baseline and remained active across the barrier, matching EXP-016's observer shape.
barrier_result:
  - The frozen timing probe and exact installed dynamic_cup_pick_place process started 0.004321 s apart.
  - Timing probe exited zero: 18.331570 s internal and 20.710140 s wall; Open3D import used 9.617970 s and create_node used 7.309310 s.
  - The installed dynamic process constructed successfully and exited one only at the expected CUP_POSE_TIMEOUT because this diagnostic intentionally provided no /cup_pose; it ran 52.719200 s and never planned or moved.
  - No observer timeout occurred. CPU load remained high: ros2_control about 134 to 137%, preserved unrelated Code helper about 96 to 97%, move_group about 23 to 24%, and WindowServer about 35% before the barrier.
inference:
  - Same-barrier dynamic startup did not push runtime construction beyond the 30 s deadline, so this hypothesis does not reproduce EXP-016.
  - This result does not authorize changing launch sequencing or the timeout. The next diagnostic must exercise the real installed rgbd_cup_pose entrypoint and split the actual deadline-covered phases.
shutdown:
  - SIGINT was sent only to exact task-owned GUI helper PID 69883 and exact tmux mrc010-mac-concurrent-startup-r1.
  - Controller/RobotSystem teardown, move_group ordered shutdown, robot_state_publisher, and ros2_control_node completed cleanly.
  - Exact PIDs 69883, 69874, 69878, 69873, 71764, and 71765 are absent; task tmux is absent; unrelated tmux sessions remain preserved.
  - The base wrapper pane ended before wrapper exit files were written; component clean exits and absence readback are claimed, not a wrapper rc.
evidence:
  owner: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/concurrent-startup-r1/owner.txt
  owner_sha256: 17d4231a6cc1f35e30fd6f017216c000cf067b84f923dffdbd36ad4d283f9e72
  base_log: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/concurrent-startup-r1/base-stack.log
  base_log_sha256: c659cd0291164f490c0d15c876d1cd63fcfcdfe8ed65c801dae5ff93d1bc975b
  barrier_result: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/concurrent-startup-r1/barrier-result.txt
  barrier_result_sha256: 65629c7feedc52487d028af2b810a0609572c0d411aea1414154f009b89e7cd8
  baseline_manifest: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/concurrent-startup-r1/gui/baseline-helper/20260827T003740-a00000095a6d/manifest.json
  baseline_png: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/concurrent-startup-r1/gui/baseline-helper/20260827T003740-a00000095a6d/window.png
decision: RETAIN_RESULT_AND_PLAN_REAL_INSTALLED_RGBD_ENTRYPOINT_AB
next_experiment: NONE
```

## CP-024 — Plan real installed rgbd_cup_pose entrypoint A/B

```yaml
checkpoint_id: CP-024
recorded_at: 2026-08-27T00:45:23+08:00
smoke_id: SMOKE-004
status: PLANNED
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_checkpoint: 0ef545585ef417985911c62a4cd11a9d13125d41
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
problem: Staged probes reproduce the heavy Open3D/import/create-node path in 17 to 18 s, but they do not execute the actual installed CLI, RosRuntime class construction, callbacks, TF lookup, point-cloud path, or the shared 30 s first-valid deadline that failed in EXP-016.
hypothesis: One omitted real-entrypoint phase, rather than dynamic startup alone, exhausts the remaining deadline margin on the live MuJoCo stack.
frozen_scope:
  - Use only the installed candidate at implementation commit 74a6523; do not rebuild, source-import, or change production code.
  - Invoke ros2 run so101_demo_py rgbd_cup_pose with the exact formal-launch parameters: 30.0 s startup timeout, /cup_pose, run-owned cup.ply and summary.json, and use_sim_time true.
  - Do not start dynamic_cup_pick_place; this diagnostic cannot plan or move the robot.
identity:
  empty_domain: 219
  empty_session: mac-mrc010-real-rgbd-empty-r1
  live_domain: 218
  live_session: mac-mrc010-real-rgbd-live-r1
  live_tmux: mrc010-mac-real-rgbd-live-r1
  evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/real-rgbd-entrypoint-r1
method:
  - Empty control first: run the exact installed entrypoint in an otherwise empty legal domain. Expected result is runtime construction below 30 s followed by the explicit no-valid-RGB-D timeout, not a construction timeout.
  - Stop on any valid empty-control construction failure and retain stdout/stderr/ROS logs.
  - Live A/B only after the control passes: start exact candidate MuJoCo base stack, both formal static TF publishers, GUI baseline polling, all controllers, MoveIt, and Planning Scene READ_BACK; then start the same exact installed entrypoint.
  - A live PASS requires first summary.json/cup.ply and a valid /cup_pose publication before 30 s. A construction timeout or first-valid timeout is the first valid failure and ends the A/B.
  - Retain a separate read-only staged timing record for Buffer/TransformListener/QoS/publisher/three subscriptions comparison; it does not replace the real entrypoint result.
cleanup: Send signals only to exact recorded observer/static-TF/base tmux identities; preserve unrelated processes, windows, and tmux sessions.
decision: COMMIT_PLAN_THEN_RUN_EMPTY_CONTROL
next_experiment: SMOKE-004
```

## CP-025 / TRANS-SMOKE-004-RUNNING-001 — Start real installed RGB-D empty control

```yaml
checkpoint_id: CP-025
transition_id: TRANS-SMOKE-004-RUNNING-001
recorded_at: 2026-08-27T00:50:16+08:00
smoke_id: SMOKE-004
from: PLANNED
to: RUNNING
phase: EMPTY_CONTROL
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: a806e15c49c23b3d3aa15cd2060192686b49dacd
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
pre_running_observed:
  - Legal domains 219 and 218 contain no ROS nodes with daemon use disabled; session/process identities, task tmux, exact Viewer, and the registered diagnosis path are empty.
  - Candidate prefixes resolve to project-install so101_demo_py/support and fork-install mujoco_ros2_control; installed bundle SHA256 is e2d777dfa2d925998583b8c1b376f063ec47f476d98402297701b541da455175.
  - Empty/base/static-TF/perception helpers have task-owned paths and syntax/readback; their SHA256 values are cb79439d, 42a53e25, c30bf0bf, and c2dd5fde.
  - A read-only syntax observer printed macOS nice permission warnings for background static-TF lines; exact process readback proved it started no process and created no diagnosis state.
owned_processes: NONE
decision: RUN_EMPTY_CONTROL_AND_STOP_ON_CONSTRUCTION_FAILURE
next_command: Start exact installed rgbd_cup_pose in domain 219 with formal 30 s parameters; retain natural result before considering live A/B.
```

## CP-026 / CLOSE-SMOKE-004-001 — Reject helper-expanded ROS parameter token

```yaml
checkpoint_id: CP-026
transition_id: CLOSE-SMOKE-004-001
recorded_at: 2026-08-27T00:52:00+08:00
smoke_id: SMOKE-004
from: RUNNING
to: INVALID_RUNNER
phase: EMPTY_CONTROL
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: 85cecb547d1310916aa48d2c4d49eb9e2bf4044f
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
observed:
  - The generated owner command proves zsh expanded the unquoted token use_sim_time:=true to use_sim_time:/usr/bin/true.
  - rclpy rejected that malformed parameter override before rgbd_cup_pose entered product setup; wrapper rc was one after 2.107121459 s.
  - No construction, callback, TF, point-cloud, or deadline inference is valid from this run.
classification_basis: This is a deterministic task-helper quoting defect outside the frozen installed implementation and formal launch token semantics.
cleanup:
  - The malformed process exited naturally; domain 219 readback contains no nodes and no task tmux/Viewer was created.
  - The invalid evidence remains retained and will not be overwritten or reused.
evidence:
  root: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/real-rgbd-entrypoint-r1/empty
  owner_sha256: b9e2de234f10ce58dd2fafe8a850464fa4c781443d59d464a8b18dbfe0524964
  stdout_sha256: 61a0fdb70abd07ba5f495131693f8f612162ee16b27dfdc490a9281e28fad719
  stderr_sha256: 98c4e3ce09db4e5180bafa1e47debc179d5e5b0b5c301d1d25a76829be73be70
decision: RETAIN_INVALID_AND_REPEAT_WITH_QUOTED_TOKEN_FRESH_IDENTITY
next_experiment: NONE
```

## CP-027 — Plan corrected-token real installed RGB-D A/B

```yaml
checkpoint_id: CP-027
recorded_at: 2026-08-27T00:54:11+08:00
smoke_id: SMOKE-005
status: PLANNED
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_checkpoint: 87e7f710139559480d01e6c65bc3dd889bc0df62
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
prior_invalid: SMOKE-004
single_variable: Quote the zsh array token as use_sim_time:=true so it reaches rclpy unchanged; formal launch semantics, installed executable, 30 s timeout, and all product parameters remain identical.
identity:
  empty_domain: 217
  empty_session: mac-mrc010-real-rgbd-empty-r2
  live_domain: 216
  live_session: mac-mrc010-real-rgbd-live-r2
  live_tmux: mrc010-mac-real-rgbd-live-r2
  evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/real-rgbd-entrypoint-r2
helpers:
  empty_sha256: 8129326df523fc5791031bc5049758240f815db0926899f3bbde86d0afe24d09
  base_sha256: 5ca739935378b905b4a9e4415df8094b540887d7bf5f6b66d415d5d8a17d33f9
  static_tf_sha256: fe3098a8836f95737cbab90ca44fa8460940cc9bebe07848cf53ca3a0e1fac8d
  perception_sha256: 99311773950a7c3a9b1eee1cf8b232349c13451cc45a022c1edff5b45e9da652
decision_rule:
  - Empty control must enter the real installed node and end only with the expected no-valid-RGB-D timeout; a construction timeout is a valid failure and stops the A/B.
  - Only after that control passes may the fresh live identity run. Live first-valid summary/cup.ply before 30 s is PASS_DIAGNOSTIC; either real deadline timeout is the first valid failure.
decision: COMMIT_PLAN_THEN_PREFLIGHT_FRESH_IDENTITY
next_experiment: SMOKE-005
```

## CP-028 / TRANS-SMOKE-005-RUNNING-001 — Start corrected real RGB-D control

```yaml
checkpoint_id: CP-028
transition_id: TRANS-SMOKE-005-RUNNING-001
recorded_at: 2026-08-27T00:55:25+08:00
smoke_id: SMOKE-005
from: PLANNED
to: RUNNING
phase: EMPTY_CONTROL
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: a873cbd0ddd19be4ef026374c4dd4edc9d252455
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
pre_running_observed:
  - Domains 217 and 216 are graph-empty with daemon use disabled; fresh process/session/tmux/evidence identities are empty.
  - All four r2 helpers pass zsh syntax checks outside the restricted observer; exact process readback remains empty afterward.
  - The corrected empty/perception command arrays preserve the literal quoted ROS parameter token use_sim_time:=true.
owned_processes: NONE
decision: START_CORRECTED_EMPTY_CONTROL
next_command: Run exact installed rgbd_cup_pose in domain 217; retain natural deadline classification before any live stack is started.
```

## CP-029 / TRANS-SMOKE-005-LIVE-001 — Empty control passes; authorize live phase

```yaml
checkpoint_id: CP-029
transition_id: TRANS-SMOKE-005-LIVE-001
recorded_at: 2026-08-27T00:57:23+08:00
smoke_id: SMOKE-005
from: RUNNING_EMPTY_CONTROL
to: RUNNING_LIVE_AB
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: 64f65a8799ab85f0168961372e67ef2c9f95620c
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
empty_control:
  - Exact installed entrypoint received the literal formal ROS parameter token and entered product setup.
  - It naturally exited one after 32.474651833 s wall with the expected product boundary: no valid RGB-D cup pose was published within 30.000 seconds.
  - It did not emit startup deadline expired during ROS runtime construction; stderr is empty. The absent graph intentionally supplied no camera topics or TF.
  - A unified-exec observer returned late and briefly made the still-running status appear longer than the evidence timestamps; the finished-at, monotonic files, stdout, and final rc are the authoritative result.
evidence:
  owner_sha256: b35952654877f076afadcfd43b3968af967f7c4026da9c7e679e3f87dd041819
  stdout_sha256: 108b952cf4a9675662f621abf42d7d0e99dfbbadf3d4c3fe6585c5c291ee3f37
  stderr_sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
decision: EMPTY_CONTROL_PASS_START_FRESH_LIVE_AB
next_command: Start domain 216 base/static-TF/GUI baseline; after Planning Scene READ_BACK start only exact installed rgbd_cup_pose and stop on its first deadline classification.
```

## CP-030 / CLOSE-SMOKE-005-001 — Reject live tmux cwd precondition

```yaml
checkpoint_id: CP-030
transition_id: CLOSE-SMOKE-005-001
recorded_at: 2026-08-27T01:00:24+08:00
smoke_id: SMOKE-005
from: RUNNING_LIVE_AB
to: INVALID_LIVE_PREFLIGHT
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: ba73b5d624d5d837f9651d3cdb44e706e9aa3b72
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
valid_control_retained:
  - The empty-domain real installed control remains a valid PASS and is not invalidated by this later live precondition failure.
invalid_observation:
  - Immediate tmux pane readback after new-session -c selected /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/mujoco-ros2-control-0-1-upgrade rather than the exact task worktree.
  - Ctrl-C was sent before the base helper created its owner/log or established a product result; no GUI capture or real live perception process started.
  - Static-TF wrappers had started in domain 216, but this environment precondition failure makes the live phase non-counting.
cleanup:
  - The exact base tmux received Ctrl-C and is absent. Static-TF wrapper 75143 and exact child PIDs 75241/75242 ignored bounded SIGINT, then exited after exact SIGTERM; no broad signal was used.
  - Domain 216 is graph-empty; exact PIDs and Viewer are absent; unrelated tmux/processes remain preserved.
evidence:
  live_root: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/real-rgbd-entrypoint-r2/live
  tf_owner_sha256: dd6061cfa46ff549bf5d65845977d9c0a51ba061997e7a368b136af889da278b
  base_owner: ABSENT_STOPPED_BEFORE_HELPER_ENTRY
  base_log: ABSENT_STOPPED_BEFORE_HELPER_ENTRY
decision: RETAIN_INVALID_LIVE_AND_REPEAT_LIVE_ONLY_WITH_IN_PANE_CD_READBACK
next_experiment: NONE
```

## CP-031 — Plan fresh live-only real RGB-D A/B with in-pane cwd gate

```yaml
checkpoint_id: CP-031
recorded_at: 2026-08-27T01:02:22+08:00
smoke_id: SMOKE-006
status: PLANNED
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_checkpoint: 094b6649f79a35fb8cb61be0f452c65f85cccc9b
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
valid_control_basis: SMOKE-005 empty control constructed the real installed node inside its 30 s budget and reached only the expected no-camera first-valid timeout.
single_variable: Replace unreliable tmux -c behavior with an initially idle task tmux, explicit in-pane cd to the exact worktree, and exact pane_current_path/pwd readback before starting any product helper.
identity:
  domain: 215
  session: mac-mrc010-real-rgbd-live-r3
  tmux: mrc010-mac-real-rgbd-live-r3
  evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/real-rgbd-entrypoint-r3/live
helpers:
  base_sha256: 7b4a8c5c715579a3c43dc01d2beb026aa269f9b03d76e6ebc3b00d4a5d63b33c
  static_tf_sha256: 411aee6274109f841f4125a79ebdee536fb2d76afbef7d3a5a6edaa17ef38c36
  perception_sha256: c50541dbf1129e96ce635d24695facf36d8145487d3b322d4741d5f7f524cbf3
method:
  - Preflight legal domain/session/evidence/Viewer empty and helper syntax, then create only an idle task tmux shell.
  - Send explicit cd to the exact task worktree and require both pane_current_path and captured pwd to match before committing RUNNING.
  - Start static TF plus base; keep exact-Viewer baseline polling active; wait candidate plugin/controllers/MoveIt/Scene READ_BACK.
  - Start only exact installed rgbd_cup_pose with formal 30 s args. PASS requires summary.json/cup.ply and /cup_pose; either construction or first-valid timeout is the first valid failure and stops diagnosis.
cleanup: Use only exact recorded helper PIDs and task tmux; the r3 static-TF helper uses exact TERM for its child wrappers because r2 proved background ros2 wrappers ignore inherited SIGINT.
decision: COMMIT_PLAN_THEN_CREATE_IDLE_TMUX_CWD_GATE
next_experiment: SMOKE-006
```

## CP-032 / TRANS-SMOKE-006-RUNNING-001 — Start cwd-gated live real RGB-D A/B

```yaml
checkpoint_id: CP-032
transition_id: TRANS-SMOKE-006-RUNNING-001
recorded_at: 2026-08-27T01:04:02+08:00
smoke_id: SMOKE-006
from: PLANNED
to: RUNNING
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: adb09be283ee3ab8dcfa2ca51b221321a7748087
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
pre_running_observed:
  - Domain 215, fresh session/process identity, diagnosis evidence path, and exact Viewer are empty; all r3 helper syntax checks pass and no helper process exists.
  - An idle task tmux shell only was created. Explicit in-pane cd plus both pane_current_path and captured pwd resolve exactly to the current task worktree.
  - No product helper has started and the diagnosis evidence path remains empty at this transition.
owned_processes:
  - tmux_session: mrc010-mac-real-rgbd-live-r3
    idle_pane_pid: 75744
cwd_gate_evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-live-preflight/smoke006-pane-readback.txt
cwd_gate_sha256: 9b385e02891b19a4e9ad7285190d84c3b512d8c2890ba3403ac209f1eb4c4eef
decision: START_STATIC_TF_BASE_GUI_THEN_REAL_PERCEPTION
next_command: Start r3 static TF; send exact r3 base helper to the cwd-gated pane; start exact-Viewer polling; after Scene READ_BACK start exact installed rgbd_cup_pose.
```

## CP-033 / CLOSE-SMOKE-006-001 — Real live entrypoint reproduces ROS runtime construction overrun

```yaml
checkpoint_id: CP-033
transition_id: CLOSE-SMOKE-006-001
recorded_at: 2026-08-27T01:10:22+08:00
smoke_id: SMOKE-006
from: RUNNING
to: VALID_FAILURE
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: 03f4197019a788a5068f1d79cca2c3df2ed57ab8
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
valid_preconditions:
  - In-pane cwd gate, candidate project/fork/support prefixes, ABI-aligned support plugin, legal domain 215, fresh session/evidence, and exact task ownership all passed.
  - MuJoCo camera/simulation stack remained live; joint_state_broadcaster, gripper_controller, and arm_controller activated; MoveIt announced ready; Planning Scene READ_BACK succeeded.
  - Exact Viewer window 45356 owned by ros2_control_node PID 76011 was captured at 1140x773 before perception startup. Both formal static TF publishers remained live.
failure:
  - Exact installed rgbd_cup_pose started at 01:07:19 with the formal 30.0 s parameters, literal use_sim_time true, and no dynamic/motion process.
  - It produced no summary.json or cup.ply, then naturally exited one after 51.686113917 s wall with RGBD_CUP_POSE_TIMEOUT: startup deadline expired during ROS runtime construction.
  - Stderr contains only ros2run's failure wrapper. The process naturally exited between the decision to sample and exact PID resolution, so no stack sample was taken and no unrelated PID was sampled.
comparison:
  - SMOKE-005 empty control reached only the ordinary no-camera first-valid timeout after 32.474651833 s wall, proving the real installed constructor can finish inside the deadline without a live stack.
  - SMOKE-002/003 staged probes finished live construction in 17.142 to 18.332 s; therefore their instrumentation omitted or failed to isolate the real blocking call reproduced here.
shutdown:
  - Perception exited naturally. Exact GUI helper PID 75967 received SIGINT and exited 130; exact static-TF wrapper 75804 used its task-owned TERM cleanup and exited zero; base tmux received Ctrl-C.
  - RobotSystem/controllers, move_group ordered shutdown, robot_state_publisher, and ros2_control_node all completed cleanly. The returned idle task tmux was then removed by exact session name.
  - Domain 215 graph, exact PIDs, task tmux, and exact Viewer are absent; unrelated windows/processes/tmux sessions remain preserved.
evidence:
  root: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/real-rgbd-entrypoint-r3/live
  perception_owner_sha256: f2626d88c08e08e741feee53ec6467a46c8774814ec4338823727e4b73029961
  perception_stdout_sha256: 2e7a1127621a702581e453ca74b9d989279c892d09c2cacf4b421e780833a390
  perception_stderr_sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
  base_owner_sha256: fc22f656fe3d1f37588d21b352f67e51cf6331281dfb956634c1e5accb24b99b
  base_log_sha256: a3fd49afd4a518d3d0a114dca2d39b573302c82211e59b24d3d1e15cca29cb3c
  tf_owner_sha256: 66bc7329c7eeb8fe79af34b046d2cb8a19eb9f3a886d5079d5b5539fd4b9c878
  baseline_manifest_sha256: a2ec36fe0dc532bd8d5909f5834e51cd56df3edb835f5f878d62d2d3fc3061d6
  baseline_png_sha256: ee04cb674d2c4364d5f6d4b700cef2c6577ed3d4f19f5d8fcec1aa5d11a8be02
decision: STOP_QUALIFICATION_AND_STAGE_PER_CALL_CONSTRUCTION_TIMING
next_experiment: NONE
```

## CP-034 — Plan transparent per-call ROS runtime construction timing

```yaml
checkpoint_id: CP-034
recorded_at: 2026-08-27T01:13:55+08:00
smoke_id: SMOKE-007
status: PLANNED
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_checkpoint: cd647c808b038be2b81e533ac847b961060b5c92
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
problem: The real installed live entrypoint takes 51.686 s and reports a construction timeout, while the prior manual staged probe reports only 17 to 18 s and therefore lacks a discriminating resource boundary.
hypothesis: One synchronous call inside the real candidate installed _create_ros_runtime becomes disproportionately slow only with the live stack; a transparent ROS API proxy can identify it without changing frozen production code.
identity:
  empty_domain: 214
  empty_session: mac-mrc010-per-call-empty-r1
  live_domain: 213
  live_session: mac-mrc010-per-call-live-r1
  live_tmux: mrc010-mac-per-call-live-r1
  evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/per-call-construction-r1
probe_contract:
  - Import candidate installed rgbd_cup_pose_node, begin the same 30 s budget, preflight Open3D, call installed _load_ros_api, then invoke installed _create_ros_runtime with a transparent proxy.
  - Emit flush-safe monotonic START/END events for rclpy.ok/init/create_node, Parameter, Buffer, TransformListener, QoSProfile, publisher, each of three subscriptions, reverse cleanup, and total construction/close.
  - Use the formal /cup_pose publisher and camera topics but never spin callbacks. No pose can be published and no dynamic/MoveIt workflow or motion process is started.
  - Impose a 120 s observer bound. If a call remains open, sample only its exact-owned PID for two seconds, then stop that observer and retain the last START event.
method:
  - Run empty-domain control first in domain 214 and stop on any valid probe failure.
  - Only after empty completes, start the exact candidate base/static-TF/GUI stack in fresh domain 213 behind an explicit in-pane cwd gate; wait all controllers, MoveIt, and Scene READ_BACK; run the identical probe.
  - Compare per-call durations and identify the first call responsible for the live overrun before any TDD product fix.
helpers:
  probe_sha256: 1203a40abb2cb92c930ad9d222d04693cfcfc4a79828c68338a7fac5e24a3d21
  empty_sha256: ed922430b987ffc29f14489550b0b4b0d2fdd641faa0ff6840e5b2b2bb598092
  live_base_sha256: f502288e8cfc3ec58876f6d12ddc55bf30157064bdcd972606a5b717a51e9902
  live_tf_sha256: f7b8eac025bf977cd91409d617859c534c83d5a67cca305cf710d2e38b044298
  live_probe_sha256: 2bba21382024a73913dae6cd8acd47a1638f7297c837fe1aed1dd756098a081c
decision: COMMIT_PLAN_THEN_RUN_EMPTY_PER_CALL_CONTROL
next_experiment: SMOKE-007
```

## CP-035 / TRANS-SMOKE-007-RUNNING-001 — Start empty per-call construction control

```yaml
checkpoint_id: CP-035
transition_id: TRANS-SMOKE-007-RUNNING-001
recorded_at: 2026-08-27T01:15:12+08:00
smoke_id: SMOKE-007
from: PLANNED
to: RUNNING_EMPTY_CONTROL
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: 165535af729af58b0e5e8275f9fd460fb5398084
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
pre_running_observed:
  - Legal domains 214/213 are graph-empty; fresh sessions/processes/tmux/evidence identities are empty.
  - Python probe compiles; four zsh helpers pass syntax outside the restricted observer; exact process readback remains empty.
  - Candidate bundle/prefixes remain frozen and no production source/build/install change occurred after SMOKE-006.
owned_processes: NONE
decision: START_EMPTY_PER_CALL_PROBE_WITH_120_SECOND_BOUND
next_command: Run the task-owned proxy around candidate installed _create_ros_runtime in domain 214; retain flush-safe events and stop on its first valid failure.
```

## CP-036 / TRANS-SMOKE-007-LIVE-001 — Empty per-call control passes; authorize live phase

```yaml
checkpoint_id: CP-036
transition_id: TRANS-SMOKE-007-LIVE-001
recorded_at: 2026-08-27T01:17:57+08:00
smoke_id: SMOKE-007
from: RUNNING_EMPTY_CONTROL
to: RUNNING_LIVE_AB
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: a10ed9ef4b227ecfd3873080ab0808eb57a47937
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
empty_control:
  - Probe exited zero; product-equivalent deadline elapsed 6.766301 s and _create_ros_runtime total was 3.276062 s.
  - Dominant empty phases were Open3D 3.335847 s, create_node 2.884717 s, publisher 0.236124 s, load_ros_api 0.154065 s, TransformListener 0.064793 s, and camera_info subscription 0.034787 s.
  - All other construction calls were below 0.004 s; cleanup total was 0.012145 s. The proxy produced no publication/evidence/motion artifact and stderr was empty.
live_preflight:
  - Domain 213 and live evidence/session identity are empty.
  - Idle tmux pane 79519 passed explicit cd, pane_current_path, and captured pwd against the exact task worktree; no product helper has started.
empty_evidence:
  owner_sha256: 4864a7bd249cfbf72c58e3904d7a5c984f2ac6b0885b5fc622cd0f8829551437
  events_sha256: c710e105b0031d11f3d5dfb2822dc21f3b86bc1894e380ebffa421ee81eb31ec
  stderr_sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
decision: START_LIVE_BASE_THEN_IDENTICAL_PER_CALL_PROBE
next_command: Start domain 213 static TF/base/GUI in cwd-gated pane; wait full readiness; run identical probe with 120 s bound.
```

## CP-037 / CLOSE-SMOKE-007-001 — Per-call proxy measures slowdown but no crossing call

```yaml
checkpoint_id: CP-037
transition_id: CLOSE-SMOKE-007-001
recorded_at: 2026-08-27T01:23:40+08:00
smoke_id: SMOKE-007
from: RUNNING_LIVE_AB
to: PASS_DIAGNOSTIC_HYPOTHESIS_REJECTED
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: 19ad00507f20f4a8e40a592052883dfb48e16408
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
empty_result:
  deadline_elapsed_s: 6.766301
  open3d_s: 3.335847
  load_ros_api_s: 0.154065
  create_node_s: 2.884717
  transform_listener_s: 0.064793
  publisher_s: 0.236124
  camera_info_subscription_s: 0.034787
  color_subscription_s: 0.003880
  depth_subscription_s: 0.000221
  construction_total_s: 3.276062
  cleanup_total_s: 0.012145
live_result:
  deadline_elapsed_s: 15.972863
  open3d_s: 7.872870
  load_ros_api_s: 0.333781
  create_node_s: 6.952925
  transform_listener_s: 0.129293
  publisher_s: 0.488720
  camera_info_subscription_s: 0.077224
  color_subscription_s: 0.009468
  depth_subscription_s: 0.000789
  construction_total_s: 7.765819
  cleanup_total_s: 0.013359
inference:
  - Live stack causes a consistent roughly two-times slowdown, dominated by Open3D and create_node, but every proxied call completed and the complete product-equivalent budget remained 14.027 s below the deadline.
  - No single synchronous boundary crossed 30 s, so the per-call proxy does not reproduce SMOKE-006's 51.686 s real installed failure and cannot authorize a source fix.
  - The proxy's NodeProxy object or ordinary run-to-run scheduling variance may alter the real path. A fresh real installed run must sample its exact child at about 25 s and again after 30 s if still alive.
observer_notes:
  - Both probes exited zero and stderr was empty. TF listener finalizers emitted two additional destroy-subscription events after SUMMARY; these are retained but do not affect construction timings.
  - Neither probe spun callbacks, published a pose, created cup evidence, started dynamic workflow, or moved the robot.
shutdown:
  - Exact GUI helper PID 79703 exited 130 after SIGINT; static-TF wrapper 79586 exited zero via exact TERM cleanup; base tmux received Ctrl-C and component teardown was clean.
  - Domain 213, exact PIDs, task tmux, and Viewer are absent; unrelated windows/processes/tmux remain preserved.
evidence:
  empty_events_sha256: c710e105b0031d11f3d5dfb2822dc21f3b86bc1894e380ebffa421ee81eb31ec
  live_events: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/per-call-construction-r1/live/probe-events.ndjson
  live_events_sha256: 318bc8ac71f12daaa89baf819262e583ddb65476aca9b1725a216bd5f9bcbe76
  live_probe_owner_sha256: 55fa466034753339e7f22fb5a706df0db79e1fedfa58a42cf78dcccd19798a7a
  live_probe_stderr_sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
  live_base_log_sha256: d4d940b66e9bd2a8a3d97828518f7851788611142a8a0bc31055d6c12ac7e5f5
  baseline_manifest_sha256: 36db1f66d60e2b46bfb1f5fd0a8932e3ca247c0107b74babc9e35b26020dc6a2
  baseline_png_sha256: d850bdecf9e44f3f30b509f8fa774f0bec9f7b0ad091631432e3c3b15c6917ce
decision: RETAIN_RESULT_AND_PLAN_REAL_INSTALLED_TWO_SAMPLE_STACK_CAPTURE
next_experiment: NONE
```

## CP-038 — Plan real installed child stack sampling at deadline boundaries

```yaml
checkpoint_id: CP-038
recorded_at: 2026-08-27T01:26:38+08:00
smoke_id: SMOKE-008
status: PLANNED
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_checkpoint: a444ef78427df100896af086b589f9c40802897a
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
problem: Transparent proxy timing changes the node object/path or catches a fast scheduling sample; it does not reproduce the exact installed entrypoint's real 51.686 s construction timeout.
hypothesis: Sampling the unmodified installed console-script child while it crosses the 30 s deadline will reveal whether it is blocked in Python import, rclpy/rcl/rmw construction, a TF/pub/sub call, or system scheduling.
identity:
  domain: 212
  session: mac-mrc010-real-sample-r1
  tmux: mrc010-mac-real-sample-r1
  evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/real-rgbd-sampling-r1/live
exact_child_contract:
  - Execute the immutable installed console script /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_demo_py/lib/so101_demo_py/rgbd_cup_pose directly with the exact formal arguments and venv shebang used by ros2 run.
  - Run it as the only background child of a recorded task wrapper; record actual PID, exact parent PID, launch argv, executable path, start/end monotonic, stdout/stderr, rc, and command readback before sampling.
  - Start no dynamic workflow and no motion. Base/static TF/GUI/controller/MoveIt/Scene readiness must match the prior live failures behind an explicit in-pane cwd gate.
sampling:
  - At 25 s and 31 s from the child's monotonic start, first skip if summary.json already proves construction complete or if the child exited.
  - Otherwise require exact parent and executable-prefix readback, then run macOS sample on only that PID for 2 s with 1 ms interval and retain identity/status/output for each boundary.
  - Sampling may perturb timing and is diagnostic only. After the second boundary, allow natural failure up to a 120 s observer bound; if construction already completed, exact SIGINT the owned child rather than leaving it spinning.
helpers:
  base_sha256: 206772203c2747fa4fb789715000133a0e9414cfa7b7bd0ff088e7edec3291b0
  static_tf_sha256: 77f2edeb18169e2e7edf85b9e8eb059f2e09cce9652c89962bf1520884b7961a
  perception_sha256: 0a0ec61a455f42c625bacd368548f094a4f2484c6b873b924bb1ff3e97378ca3
  sampler_sha256: 4a60765304ffec491b7f69607f90c34c96e3dc1d8c61781ccc57fb95f63f8cee
decision: COMMIT_PLAN_THEN_PREFLIGHT_FRESH_REAL_CHILD
next_experiment: SMOKE-008
```

## CP-039 / TRANS-SMOKE-008-RUNNING-001 — Start real installed child sampling run

```yaml
checkpoint_id: CP-039
transition_id: TRANS-SMOKE-008-RUNNING-001
recorded_at: 2026-08-27T01:28:04+08:00
smoke_id: SMOKE-008
from: PLANNED
to: RUNNING
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: 5d3ae49899a4a07591320e1172e9e101c444c3e5
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
pre_running_observed:
  - Domain 212, session/process/tmux/evidence/Viewer identity are fresh and empty; all four helpers pass syntax and exact process readback is empty.
  - Installed console script shebang is the frozen ROS venv Python and the immutable executable exists at the pre-registered path.
  - Idle tmux pane 82924 passed explicit cd, pane_current_path, and captured pwd against the exact task worktree; no product helper has started.
owned_processes:
  - tmux_session: mrc010-mac-real-sample-r1
    idle_pane_pid: 82924
decision: START_BASE_STATIC_TF_GUI_THEN_EXACT_CHILD_AND_SAMPLER
next_command: Start domain 212 base/static-TF/GUI; after full readiness start recorded installed child and boundary sampler.
```

## CP-040 / CLOSE-SMOKE-008-001 — Reject sampler environment before first sample

```yaml
checkpoint_id: CP-040
transition_id: CLOSE-SMOKE-008-001
recorded_at: 2026-08-27T01:33:39+08:00
smoke_id: SMOKE-008
from: RUNNING
to: INVALID_SAMPLER
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: 1fe6a6bfd8dcff9f1a3916fa26c6fb3ba31e8e44
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
valid_preconditions:
  - Exact cwd/provenance/installed child identity, domain 212, base/static TF/controllers/MoveIt/Scene READ_BACK, and exact Viewer baseline all passed.
invalid_observer:
  - sample-real-perception-r1.zsh did not source the venv and invoked an unavailable unqualified python token while calculating the 25 s remaining delay.
  - The empty remaining value made sleep fail; the sampler exited 66 before invoking macOS sample. No process was sampled or signaled by the invalid sampler.
  - Therefore the stack-sampling objective is invalid and no root-call inference is made from this run.
retained_behavior_observation:
  - The exact immutable installed child was independently recorded as PID 85092, PPID 84538, with exact executable and argv readback.
  - It naturally reproduced RGBD_CUP_POSE_TIMEOUT: startup deadline expired during ROS runtime construction after 51.306446333 s wall, rc one, with no summary.json/cup.ply.
  - This repeats SMOKE-006's product failure but supplies no new stack evidence and remains non-qualifying.
cleanup:
  - The child had already exited when exact SIGINT was attempted; exact GUI helper/static-TF/base identities were then stopped, component teardown was clean, and the returned idle tmux was removed by exact name.
  - Domain 212, exact PIDs, task tmux, and Viewer are absent; unrelated windows/processes/tmux remain preserved.
evidence:
  root: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/real-rgbd-sampling-r1/live
  perception_owner_sha256: fef7d97231db31a13fa31fb2c658bf273b0c08d2b9ce5465ed24519aedefb422
  child_owner_sha256: aa2bdce4882212e0dd70efb7fa20ea300005410e2166441402cb56407452f2e2
  stdout_sha256: 95b969fca349efacfe7a6111fc5ace0f49ac6171511174a16f0f7213be6ade0a
  stderr_sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
decision: RETAIN_INVALID_AND_REPEAT_WITH_ABSOLUTE_VENV_PYTHON_PLUS_IDENTITY_PARSER_PREFLIGHT
next_experiment: NONE
```

## CP-041 — Plan corrected real installed child stack sampling

```yaml
checkpoint_id: CP-041
recorded_at: 2026-08-27T01:38:07+08:00
smoke_id: SMOKE-009
status: PLANNED
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_checkpoint: 9e569ce344180c1e40b9610e2289d62aabfe773b
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
problem: SMOKE-008 reproduced the real constructor timeout, but its sampler exited before the first boundary because it used an unavailable unqualified python token.
hypothesis: With the observer corrected to the frozen absolute venv Python and its identity parser proven before product startup, two short samples of the exact immutable installed child at 25 s and 31 s will expose the blocking runtime call.
identity:
  domain: 211
  session: mac-mrc010-real-sample-r2
  tmux: mrc010-mac-real-sample-r2
  evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/real-rgbd-sampling-r2/live
observer_changes_only:
  - Use /Users/matianyi/ros2_jazzy/.venv/bin/python for monotonic-delay arithmetic; do not change the installed product, product arguments, base stack, or deadline.
  - Match the recorded exact parent and require that the child command contains the immutable installed console-script path, because the macOS process command begins with the resolved shebang interpreter.
  - At 25 s and 31 s, skip when summary.json exists or the child exited; otherwise sample only the exact-owned child for two seconds and retain identity, argv, timing, status, and stack output.
parser_preflight:
  result: PASS
  actual_pid: 86432
  expected_parent: 86431
  observed_parent: 86431
  observed_command: /opt/homebrew/opt/python@3.12/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-live-preflight/identity-parser-preflight-child.py
  absolute_python: /Users/matianyi/ros2_jazzy/.venv/bin/python
  threshold_math_result: 0.10000025
  evidence_sha256: c0cde871ba694da3e77e1ece83b2991cbb8542ccd3b6e7e10a32b328123d88cd
helpers:
  base_sha256: 82d9ed0be5c818a2f634296c6106ceb23e96c78e718e432bbf2ceb268a67fcc7
  static_tf_sha256: 5aa187e4107c51664329f9ad43400f05846ff379c02c8072d621c3fdebd7d5c9
  perception_sha256: d2a9d45ad6493fb20a110976e50e9d899af332e18f80b99a6c98fc661fd5a224
  sampler_sha256: bc0fe14549085ca8ea044cab1546cf1ee74ecd47c330e80e33f76a393cd6b208
  parser_preflight_sha256: a894694e475ddd258430499bb5fef8745008ed7453fcecf61175130baf557c60
decision: COMMIT_PLAN_THEN_PREFLIGHT_FRESH_DOMAIN_AND_EXACT_IDENTITIES
next_experiment: SMOKE-009
```

## CP-042 / TRANS-SMOKE-009-RUNNING-001 — Start corrected real installed child sampling

```yaml
checkpoint_id: CP-042
transition_id: TRANS-SMOKE-009-RUNNING-001
recorded_at: 2026-08-27T01:41:13+08:00
smoke_id: SMOKE-009
from: PLANNED
to: RUNNING
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: 9194a6a87b6c817717aea4e2d90a12354e806497
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
pre_running_observed:
  - Domain 211 ROS graph is empty with ROS2CLI_USE_DAEMON zero; the registered evidence path, exact task tmux, exact task process identities, and MuJoCo Viewer are absent.
  - Candidate package prefixes resolve to project-installed so101_demo_py and so101_mujoco_support plus fork-installed mujoco_ros2_control.
  - The absolute-Python identity parser preflight passed on a short-lived exact-owned child before product startup.
  - Idle tmux pane 86961 passed explicit in-pane cd, pane_current_path, and captured pwd against the exact task worktree.
owned_processes:
  - tmux_session: mrc010-mac-real-sample-r2
    idle_pane_pid: 86961
evidence:
  pane_readback_sha256: 881ffbb54a4407e1bba835906fe164d88b107d124c67d5059906aa59bfe2a1b1
decision: START_BASE_STATIC_TF_GUI_THEN_EXACT_CHILD_AND_CORRECTED_SAMPLER
next_command: Start domain 211 base/static-TF/GUI; after full readiness start recorded installed child and exact-owned 25 s/31 s sampler.
```

## CP-043 / CLOSE-SMOKE-009-001 — Localize constructor timeout to default ROS service typesupport loading

```yaml
checkpoint_id: CP-043
transition_id: CLOSE-SMOKE-009-001
recorded_at: 2026-08-27T01:47:12+08:00
smoke_id: SMOKE-009
from: RUNNING
to: VALID_DIAGNOSTIC_FAILURE
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: d5b5e04deb912833bc3c0923c292575b3d4b76db
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
valid_preconditions:
  - Exact worktree/provenance/domain/session/installed-child identity passed; base/static TF/controllers/MoveIt/Scene READ_BACK and unique Viewer baseline all passed before child start.
  - The corrected absolute-Python observer matched exact PID 90419, parent 88997, and immutable installed executable at both boundaries; macOS sample returned zero twice.
observed_product_failure:
  - The unchanged child naturally exited one with RGBD_CUP_POSE_TIMEOUT during ROS runtime construction, no summary.json/cup.ply, and measured wall 35.235684875 s.
  - Sampling is intentionally perturbing, so this wall value is diagnostic only and is not compared directly with the unsampled 51 s failures.
root_call_evidence:
  - At 25 s, all 1343 main-thread samples were inside rcl_service_init -> rmw_create_service -> FastRTPS service typesupport lookup -> rcpputils SharedLibrary -> rcutils_load_shared_library -> dyld dlopen/path-image scanning.
  - At 31 s, all 1519 main-thread samples were specifically inside rcl_node_type_description_service_init and then the same service-typesupport/dlopen chain.
  - This places the first bad boundary inside rclpy Node construction's automatically created ROS services, before TF, publisher, or RGB-D subscriptions. It rejects Open3D, subscription creation, and generic CPU scheduling as the active blocked call in this reproduction.
next_tdd_boundary:
  - The perception node does not consume ROS parameter services or rosout. Add a RED contract requiring Node construction to pass start_parameter_services false and enable_rosout false while preserving automatic parameter declaration and use_sim_time behavior.
  - Local Jazzy exposes both switches but no type-description-service switch; the type-description service remains and must be validated in a real live GREEN smoke after removing the avoidable default services.
cleanup:
  - Exact child exited naturally; exact capture/static-TF helpers received only their owned interrupt, base tmux received one Ctrl-C, and controller manager, Move Group, RSP, MuJoCo UI, and hardware teardown were clean in base log.
  - The base helper shell returned to its task pane before writing a wrapper exit-code file; this observer gap is retained and does not alter component-level clean teardown.
  - Domain 211, exact PIDs, task tmux, and Viewer are absent; unrelated windows/processes/tmux remain preserved.
evidence:
  root: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/real-rgbd-sampling-r2/live
  perception_owner_sha256: e088e5bb23b0c6f9c5bca4cb1348433b846b4d47ae755457e13547a3cb65848b
  perception_child_owner_sha256: 5940b469e67ca37357f13c509b02ed8de6a6cc171aca652e314e3bdc91381a64
  stdout_sha256: 95b969fca349efacfe7a6111fc5ace0f49ac6171511174a16f0f7213be6ade0a
  sample_25s_sha256: d966aab67090877bd09c33ee28737621659554fd1d4acbbf9413903b57f0885d
  sample_31s_sha256: 79281a40d2a444fd7a6144f0c1622d2216bf6d7e688e949e0a31fa21774cba86
  baseline_manifest_sha256: bc65c3a311725e9b1c9ea2431a256ca0588233230ed8cab5fab60b46873668ea
  baseline_png_sha256: b70b934fa57e079efabfaed81ef1af5a9d13d7472163753d5eb229efaba6576d
  base_log_sha256: d1e408ed0b3cb6297ca7ca5d3f62f5d25a2971b1712146ea3d5a26a0286882e5
decision: RETAIN_ROOT_CALL_EVIDENCE_AND_BEGIN_TDD_DEFAULT_SERVICE_REDUCTION
next_experiment: NONE
```

## CP-044 — RED contract for lean RGB-D perception node construction

```yaml
checkpoint_id: CP-044
recorded_at: 2026-08-27T01:49:42+08:00
status: RED
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_checkpoint: 306edcc70ac2c9b11656dffc1e10a3daf9dc596a
root_cause_evidence: SMOKE-009 sampled the constructor in ROS service typesupport dlopen at both 25 s and 31 s; the perception node does not use parameter services or rosout.
contract:
  - rclpy.create_node must receive start_parameter_services false and enable_rosout false.
  - automatically_declare_parameters_from_overrides must remain true and the use_sim_time true Parameter override must remain present.
red_command: python -m pytest -q -o cache_dir=/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/tdd-red-cache src/so101_demo_py/test/test_rgbd_cup_pose.py::test_ros_runtime_disables_unused_default_services_without_dropping_sim_time
red_result: one failed in 0.32 s
red_failure: KeyError start_parameter_services
scope: Add only the two supported rclpy Node construction keyword arguments; do not alter timeout, launch sequencing, perception policy, topics, TF, or motion.
decision: COMMIT_RED_THEN_ADD_MINIMAL_NODE_KEYWORDS
next_experiment: NONE
```

## CP-045 — GREEN lean RGB-D perception node construction

```yaml
checkpoint_id: CP-045
recorded_at: 2026-08-27T01:52:06+08:00
status: GREEN
qualification: false
record_head_before_checkpoint: 3adb8df828878dbd21a80559e849a9942eb52916
change:
  - Pass start_parameter_services false and enable_rosout false to the existing rgbd_cup_pose rclpy.create_node call.
  - Preserve use_sim_time true, automatic parameter override declaration, startup deadline, launch sequencing, perception policy, topics, TF, and motion behavior.
tests:
  - command: focused new contract
    result: one passed in 0.22 s
  - command: complete test_rgbd_cup_pose.py
    result: 43 passed in 0.25 s
  - command: complete src/so101_demo_py/test with ROS_LOG_DIR under the registered evidence root
    result: 444 passed in 12.73 s
invalid_test_observation:
  - An earlier full-suite invocation omitted ROS_LOG_DIR and produced 59 PermissionError failures while launch tried to write restricted ~/.ros/log; it is environmental, retained in terminal output, and was repeated with the required registered-root ROS_LOG_DIR.
decision: COMMIT_MINIMAL_GREEN_THEN_REBUILD_CANDIDATE_AND_RUN_REAL_LIVE_GREEN_SMOKE
next_experiment: NONE
```

## CP-046 — Rebuild fixed candidate and plan real live perception GREEN smoke

```yaml
checkpoint_id: CP-046
recorded_at: 2026-08-27T01:56:11+08:00
smoke_id: SMOKE-010
status: PLANNED
qualification: false
implementation_commit: dea3dfa41ba875a3114ed153f2bfcd8aca62dfba
record_head_before_checkpoint: dea3dfa41ba875a3114ed153f2bfcd8aca62dfba
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
candidate_rebuild:
  - Clean-cache rebuilt so101_mujoco_support and symlink-installed so101_demo_py against the frozen 0.1.0 child; build exited zero.
  - Candidate prefixes resolve to project-installed so101_demo_py and so101_mujoco_support plus fork-installed mujoco_ros2_control.
  - Installed provenance plus the new node contract passed five tests in 1.66 s; support CTest ran one test and passed.
  - installed_bundle_sha256: 971b1257a90ba5940c5fa9053f32674b3aeba1305af999ce9b2cb3b75808934a
  - simulation_evidence_plugin_sha256: f4487cc3e2467e2ffec5b2ca2fa407d8c372b63cfe07cc1e71e777185d1a7ab7
  - build_log_sha256: 27f8f9f26243238e45d7c111b37afd524a1298ee3005d60f05f213f6090e3a9a
identity:
  domain: 210
  session: mac-mrc010-real-green-r3
  tmux: mrc010-mac-real-green-r3
  evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/real-rgbd-green-r3/live
hypothesis: Removing the unused default parameter services and rosout leaves only the unavoidable type-description service and lets the exact installed perception node finish ROS construction, consume real RGB-D, and publish /cup_pose within its unchanged 30 s deadline on a fully ready live stack.
success_criteria:
  - Exact cwd/provenance, full base/static TF/controllers/MoveIt/Scene readiness, and unique Viewer baseline pass.
  - A pre-start observer receives one world-frame /cup_pose; the exact installed node creates nonempty summary.json and cup.ply without RGBD_CUP_POSE_TIMEOUT.
  - The summary/pose/PLY must appear before 30 s from exact child monotonic start; then only exact-owned child/base/TF/capture/observer identities are stopped and cleanup is clean.
failure_criteria: Valid preconditions followed by constructor timeout, missing pose/PLY, invalid TF/frame, or 30 s budget violation.
helpers:
  base_sha256: d5256d272066e2afa45006c172ea6f11ae679ccbfd86c50f5c17961e0b920469
  static_tf_sha256: cc610b52e7509c829e4894ea0c0733e8c63dd5c0d0262944b31eddbc08c5cc74
  perception_sha256: 2abc96759e874903ed707b7b4718114842c4d58a4c7592616845d7aa0fe6093e
  observer_sha256: 7355c39b1517384a544f2bf92a2d4588f9c508638754517757a2a29575586eb4
decision: COMMIT_PLAN_THEN_PREFLIGHT_FRESH_REAL_LIVE_GREEN_SMOKE
next_experiment: SMOKE-010
```

## CP-047 / TRANS-SMOKE-010-RUNNING-001 — Start fixed real live perception smoke

```yaml
checkpoint_id: CP-047
transition_id: TRANS-SMOKE-010-RUNNING-001
recorded_at: 2026-08-27T01:57:16+08:00
smoke_id: SMOKE-010
from: PLANNED
to: RUNNING
qualification: false
implementation_commit: dea3dfa41ba875a3114ed153f2bfcd8aca62dfba
record_head_before_transition: f98d56b756cccb383aca24ba1f67ea889c51a0b7
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
pre_running_observed:
  - Domain 210 graph, evidence path, exact task tmux/process identities, and Viewer were fresh and empty.
  - Candidate package prefixes and installed bundle 971b1257a90ba5940c5fa9053f32674b3aeba1305af999ce9b2cb3b75808934a were read back after the zero-exit rebuild.
  - Idle tmux pane 27435 passed explicit in-pane cd, pane_current_path, and captured pwd against the exact task worktree.
owned_processes:
  - tmux_session: mrc010-mac-real-green-r3
    idle_pane_pid: 27435
evidence:
  pane_readback_sha256: 881ffbb54a4407e1bba835906fe164d88b107d124c67d5059906aa59bfe2a1b1
decision: START_BASE_STATIC_TF_GUI_OBSERVER_THEN_EXACT_INSTALLED_PERCEPTION
next_command: Start domain 210 base/static-TF/GUI; after Scene READ_BACK start observer to readiness, then exact installed rgbd_cup_pose.
```

## CP-048 / CLOSE-SMOKE-010-001 — Constructor fix passes boundary but no valid RGB-D pose appears

```yaml
checkpoint_id: CP-048
transition_id: CLOSE-SMOKE-010-001
recorded_at: 2026-08-27T02:01:22+08:00
smoke_id: SMOKE-010
from: RUNNING
to: VALID_BEHAVIORAL_FAILURE
qualification: false
implementation_commit: dea3dfa41ba875a3114ed153f2bfcd8aca62dfba
record_head_before_transition: 0cbc4abdde665172d65367b29cbe5317b5acdc99
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
valid_preconditions:
  - Exact cwd/provenance/bundle/domain/session/installed-child identity passed; base/static TF/controllers/MoveIt/Scene READ_BACK and unique Viewer baseline passed.
  - The lean pre-start /cup_pose observer completed construction and subscribed before the perception child began.
observed:
  - The exact fixed node no longer emitted startup deadline expired during ROS runtime construction.
  - It naturally exited one after 32.290501875 s wrapper wall with no valid RGB-D cup pose was published within 30.000 seconds.
  - summary.json, cup.ply, and the pre-ready observer's /cup_pose document are absent.
conclusion:
  - dea3dfa crosses the constructor-timeout boundary but does not yet satisfy the unchanged end-to-end 30 s startup contract.
  - First bad boundary moves to the live frame pipeline after construction. No timeout or sequencing change is authorized until actual CameraInfo/color/depth samples, timestamps, and callback/TF/estimation boundaries are measured.
next_diagnosis:
  - Read candidate camera publisher QoS and lifetime behavior, especially whether CameraInfo is one-shot volatile before the scene-gated late subscription.
  - Run a non-qualifying live topic/callback observer with fresh exact identities; if late CameraInfo loss is proven, TDD launch perception early while preserving dynamic workflow's Scene gate.
cleanup:
  - Exact perception exited naturally; exact observer/capture/static-TF/base identities were stopped, component teardown was clean, and domain 210/task tmux/Viewer are absent.
  - Unrelated windows/processes/tmux remain preserved.
evidence:
  root: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/real-rgbd-green-r3/live
  perception_owner_sha256: ec0e77049cc01122b208181b4edef7d8dd1467ac226f30b35945b22cfc85b95a
  perception_child_owner_sha256: eecd3fa3e17f41044baf0f9930fac53ef132e9f08eb2d3b3d9d6c4bbea504dd4
  stdout_sha256: 67bdfb14f0529fd68c340378004e61eb098a39e19a67ded1f2a363f1d27e6202
  baseline_manifest_sha256: 3816efcb770036b00621d31402d891f4eea7c4d3985b5daa0944239c87441c94
  baseline_png_sha256: 84f2f08347c2d09e2f3dee484f057a13d9a6f1a7e763beab2f8d36dcf7657cd4
  base_log_sha256: 6ae0be2df197da737e3f29f5f6dabf57d608ba5f6cf781b60de06a691147e5de
decision: RETAIN_VALID_FAILURE_AND_MEASURE_LATE_SUBSCRIBER_TOPIC_BOUNDARY
next_experiment: NONE
```

## CP-049 — Plan live RGB-D input gate and diagnostic 60 s perception continuation

```yaml
checkpoint_id: CP-049
recorded_at: 2026-08-27T02:04:09+08:00
smoke_id: SMOKE-011
status: PLANNED
qualification: false
implementation_commit: dea3dfa41ba875a3114ed153f2bfcd8aca62dfba
record_head_before_checkpoint: adf552f98d3ded517995fa87a73c29872010dd6c
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
source_evidence: CameraPlugin streaming mode stamps and publishes color, depth, and CameraInfo together on every render; late loss of a one-shot CameraInfo is rejected by source.
identity:
  domain: 209
  session: mac-mrc010-rgbd-input-r4
  tmux: mrc010-mac-rgbd-input-r4
  evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/real-rgbd-input-r4/live
phase_one_gate:
  - After exact full Scene readiness, start a lean observer for all three camera topics.
  - Require at least three samples each, at least three common exact stamps, task_camera_frame on all, rgb8 color, 32FC1 depth, and positive finite depth. Stop if this gate fails.
phase_two_diagnostic:
  - Only after the input gate passes, run the same installed perception implementation with startup-timeout-s 60.0 as a diagnostic single-variable extension.
  - Record first frame-invalid or OK output, summary/PLY/pose timing, and whether success occurs in 30-60 s. This does not authorize a production timeout change and is non-qualifying.
helpers:
  base_sha256: 0dd5f0cb3d91abf79d276fadfb294c402a5f98a725248dcf1c98a74820d518c5
  static_tf_sha256: 8db57a9c75a53937bd3c5405fda29e806a745bb68a96ec25dd103d9738a0ea97
  observer_sha256: bf1776f7d41806f4e38e9af01b4eab84f30681dca1545b65b96ae3eb88cb3e83
  perception60_sha256: a3c71218a769e98b104893b0f3cab85b32e35fb6e31870f547429b33a7ea9ef0
decision: COMMIT_PLAN_THEN_PREFLIGHT_FRESH_DOMAIN_AND_INPUT_GATE
next_experiment: SMOKE-011
```

## CP-050 / TRANS-SMOKE-011-RUNNING-001 — Start live RGB-D input gate

```yaml
checkpoint_id: CP-050
transition_id: TRANS-SMOKE-011-RUNNING-001
recorded_at: 2026-08-27T02:05:10+08:00
smoke_id: SMOKE-011
from: PLANNED
to: RUNNING
qualification: false
implementation_commit: dea3dfa41ba875a3114ed153f2bfcd8aca62dfba
record_head_before_transition: 77a617514136514ad716762504cbc23e1d6f468e
pre_running_observed:
  - Domain 209 graph, evidence, exact task tmux/process identities, and Viewer were fresh and empty.
  - Idle tmux pane 48630 passed explicit in-pane cd, pane_current_path, and captured pwd against the exact worktree.
decision: START_BASE_STATIC_TF_GUI_THEN_POST_SCENE_RGBD_INPUT_OBSERVER
next_command: Do not start perception unless the three-topic input observer gate exits zero.
```

## CP-051 / CLOSE-SMOKE-011-001 — Stop at failed RGB-D input gate

```yaml
checkpoint_id: CP-051
transition_id: CLOSE-SMOKE-011-001
recorded_at: 2026-08-27T02:09:01+08:00
smoke_id: SMOKE-011
from: RUNNING
to: VALID_INPUT_GATE_FAILURE
qualification: false
implementation_commit: dea3dfa41ba875a3114ed153f2bfcd8aca62dfba
record_head_before_transition: b7b33e9f680a537f59174fd04a2869c76b93c12e
valid_preconditions:
  - Exact fixed candidate, domain/session/cwd, full base/static TF/controllers/MoveIt/Scene READ_BACK, and unique Viewer baseline passed.
input_observer:
  elapsed_s: 45.095307333162054
  camera_info_count: 10
  color_count: 0
  depth_count: 4
  common_stamp_count: 0
  frames: task_camera_frame for received CameraInfo and depth
  depth_encoding: 32FC1
  depth_finite_positive: 307200 of 307200
  depth_range_m: [0.5510081052780151, 41.51203536987305]
conclusion:
  - The product cannot form any aligned RGB-D triplet because the post-Scene best-effort observer receives no color and only sparse depth while small CameraInfo continues arriving.
  - Phase-two 60 s perception was correctly not started. This rules out a perception timeout extension as the next action.
next_diagnosis:
  - CameraPlugin publishers use reliable volatile depth-one QoS for all three topics, while perception and the lean observer use sensor-data best-effort QoS under FastDDS.
  - Run a fresh reliable subscriber A/B for exact counts/stamps before changing production. Do not switch RMW transport unless the QoS A/B also fails.
cleanup:
  - Exact observer exited two; exact capture/static-TF/base identities were stopped, component teardown was clean, and domain 209/task tmux/Viewer are absent.
evidence:
  root: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/real-rgbd-input-r4/live
  observer_sha256: 67887c898fe464e0b48b83c6db132c274023a25a6278dd2cf0c185ca96e9f993
  baseline_manifest_sha256: 9d6094d0bd9ed581fd022af0dfdfc3f362494479c00008dfabdbaaa8c688bb5a
  baseline_png_sha256: 261fa8d8baf52806e089be125871ea93215b29e73a56c041f29b335cfc1c7cd4
  base_log_sha256: 4cc98ba04f2957b1614a9a80842f7429824ba68562bffbbccbc45efe7fd6a719
decision: RETAIN_INPUT_FAILURE_AND_PLAN_FRESH_RELIABLE_QOS_AB
next_experiment: NONE
```

## CP-052 — Plan reliable RGB-D subscriber comparison

```yaml
checkpoint_id: CP-052
recorded_at: 2026-08-27T02:10:05+08:00
smoke_id: SMOKE-012
status: PLANNED
qualification: false
implementation_commit: dea3dfa41ba875a3114ed153f2bfcd8aca62dfba
record_head_before_checkpoint: 5cc9b63c280d86705d75f6ed41331206eb75a38a
identity:
  domain: 208
  session: mac-mrc010-rgbd-reliable-r5
  tmux: mrc010-mac-rgbd-reliable-r5
  evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/real-rgbd-reliable-r5/live
hypothesis: Matching CameraPlugin's reliable volatile depth-one QoS prevents FastDDS from silently dropping the fragmented color/depth samples seen by the best-effort SMOKE-011 observer.
single_variable: Observer QoS changes from sensor-data best-effort to depth-one reliable volatile; base, camera plugin, scene timing, RMW, and topics remain unchanged.
success_criteria: At least three samples and three common exact stamps across CameraInfo/color/depth, exact frame/encodings, and positive finite depth within 45 s.
helpers:
  base_sha256: 48c4881d0d66dbcb350b62e9ae2b1f45ff72e78910abf8d9917706df6e55522a
  static_tf_sha256: 18dc64029217fb5e249ffc07223b0b2cd23ca13baedf9e4d05c0f0bdaa749e87
  observer_sha256: 606923259de209371287f9cbdfe42ea2accda163331ca8d6b313082bd556f77e
decision: COMMIT_PLAN_THEN_FRESH_PREFLIGHT_AND_RUN_RELIABLE_OBSERVER
next_experiment: SMOKE-012
```

## CP-056 — RED contract for camera-compatible perception subscription QoS

```yaml
checkpoint_id: CP-056
recorded_at: 2026-08-27T02:20:28+08:00
status: RED
qualification: false
record_head_before_checkpoint: 40ab02e1400176ab290ed60fc3cc78cb38a3a87d
root_cause_evidence:
  - SMOKE-011 best-effort received CameraInfo ten, color zero, depth four, and zero aligned stamps in 45.095 s.
  - SMOKE-012 reliable volatile depth-one rolling observer received CameraInfo sixteen, color three, depth sixteen, and three aligned stamps in 1.549 s on the otherwise unchanged FastDDS stack.
contract:
  - All three perception camera subscriptions must use depth one, RELIABLE, VOLATILE QoS matching CameraPlugin publishers.
red_command: python -m pytest -q -o cache_dir=/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/tdd-qos-red-cache src/so101_demo_py/test/test_rgbd_cup_pose.py::test_ros_runtime_matches_reliable_depth_one_camera_qos
red_result: one failed in 0.37 s
red_failure: AttributeError object has no attribute depth because production still passes qos_profile_sensor_data.
invalid_test_observation: The first invocation omitted sourced overlays and failed import; it is an environment-only observation and was rerun with the frozen candidate overlays to obtain the product RED above.
scope: Change only the three camera subscription QoS profiles; do not alter publisher QoS, timeout, launch sequencing, perception policy, topics, TF, or motion.
decision: COMMIT_RED_THEN_APPLY_MINIMAL_CAMERA_QOS_CHANGE
next_experiment: NONE
```

## CP-055 / CLOSE-SMOKE-012-001 — Reliable QoS restores aligned RGB-D delivery

```yaml
checkpoint_id: CP-055
transition_id: CLOSE-SMOKE-012-001
recorded_at: 2026-08-27T02:17:39+08:00
smoke_id: SMOKE-012
from: RUNNING
to: VALID_DIAGNOSTIC_SUCCESS
qualification: false
implementation_commit: dea3dfa41ba875a3114ed153f2bfcd8aca62dfba
record_head_before_transition: 9125f0d2af2b1a52b22191367e3470f351fee948
observer_attempts:
  - r1 was invalid because it stopped on per-topic counts before three common stamps; it nevertheless showed reliable delivery within 0.917 s.
  - r2 was invalid because its first-ten frozen windows were not equivalent to production's rolling buffer; it showed ten messages for every topic.
  - r3 used rolling last-twenty storage and is the countable causal gate.
reliable_gate:
  elapsed_s: 1.5492615830153227
  camera_info_count: 16
  color_count: 3
  depth_count: 16
  common_stamp_count: 3
  common_stamps_ns: [258300000000, 258600000000, 258700000000]
  frames: task_camera_frame for all three topics
  encodings: [rgb8, 32FC1]
  depth_finite_positive: 307200 of 307200
  depth_range_m: [0.5510081052780151, 41.51203536987305]
conclusion:
  - Matching the reliable volatile depth-one CameraPlugin publisher QoS restores large color/depth delivery and aligned triplets under the unchanged FastDDS live stack.
  - This is a causal contrast with SMOKE-011 sensor-data best-effort color zero and common stamp zero in 45.095 s.
next_tdd:
  - Add a RED contract requiring the perception camera subscriptions to use reliable volatile depth-one QoS, then make the minimal production change and retain sensor-data behavior nowhere in this perception node.
cleanup:
  - No perception or motion started. Exact observers/capture/static-TF/base/tmux were stopped; component teardown was clean.
evidence:
  root: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/real-rgbd-reliable-r5/live
  reliable_r3_sha256: b55fe2cf35722754be839a826aa505c823fa757316e0f916b17b88732ac67367
  baseline_manifest_sha256: 5b2967ec6d98ccea793b4f3e89ac64c90e29f04a6ab11a7a7fdcb8446e5750ac
  baseline_png_sha256: b7b91ae34f3f37be76390df8a9a0ac12c93cc7efdf981c4940262561e7a56b95
  base_log_sha256: 0f8617e62bf329135ec81fdf1b7671c4d4d669884a8a368cf5d4928e8b001b2a
decision: COMMIT_CAUSAL_GATE_AND_BEGIN_TDD_RELIABLE_PERCEPTION_SUBSCRIPTIONS
next_experiment: NONE
```

## CP-053 / TRANS-SMOKE-012-RUNNING-001 — Start reliable RGB-D comparison

```yaml
checkpoint_id: CP-053
transition_id: TRANS-SMOKE-012-RUNNING-001
recorded_at: 2026-08-27T02:12:20+08:00
smoke_id: SMOKE-012
from: PLANNED
to: RUNNING
qualification: false
implementation_commit: dea3dfa41ba875a3114ed153f2bfcd8aca62dfba
record_head_before_transition: 96b583e
pre_running_observed:
  - Domain 208 graph, evidence, exact task tmux/process identities, and Viewer were fresh and empty.
  - Idle tmux pane 66040 completed explicit in-pane cd and captured pwd against the exact worktree after shell initialization.
decision: START_BASE_STATIC_TF_GUI_THEN_RELIABLE_POST_SCENE_OBSERVER
next_command: Run no perception or motion; close on the reliable three-topic gate result.
```

## CP-054 — Reject early-exit reliable observer and continue same unchanged stack

```yaml
checkpoint_id: CP-054
recorded_at: 2026-08-27T02:14:09+08:00
smoke_id: SMOKE-012
status: RUNNING_INVALID_OBSERVER_ATTEMPT
qualification: false
record_head_before_checkpoint: d9754fabec1172f031fb4667b3592c8a96148697
invalid_observer:
  - The first reliable observer stopped when every topic count reached three instead of waiting for three common exact stamps.
  - It exited two after 0.917108 s with CameraInfo nine, color three, depth nine, and two common stamps. This cannot close the registered three-common-stamp gate.
retained_signal:
  - All received frames are task_camera_frame, encodings are rgb8 and 32FC1, and all 307200 sampled depth values are finite positive.
  - Reliable QoS already materially improves over SMOKE-011 best-effort, but production change remains gated on the corrected observer.
correction:
  - Same unchanged live base remains running. The observer now loops until common exact stamp count reaches three or its deadline.
  - corrected_observer_sha256: ffeca740c9b78bad3de28fcdcccc62dd7c83c7b9d8921d69037aa41cc86b3f54
  - invalid_observer_evidence_sha256: e0521ceaea1c5e37aefbeda98a63b2aadbf9b0c905f543a98081b8ba74a7784c
decision: RERUN_ONLY_CORRECTED_OBSERVER_ON_UNCHANGED_LIVE_STACK
next_experiment: SMOKE-012
```

## CP-057 — GREEN camera-compatible perception subscription QoS

```yaml
checkpoint_id: CP-057
recorded_at: 2026-08-27T02:22:08+08:00
status: GREEN
qualification: false
record_head_before_checkpoint: da1265513b65fbc30f7be77f492743be16f6956c
change:
  - Construct a depth-one RELIABLE VOLATILE camera QoS profile and use it for CameraInfo, color, and depth subscriptions.
  - Remove the unused sensor-data QoS import from the perception node.
  - Preserve output publisher QoS, startup deadline, launch sequencing, perception policy, topics, TF, and motion behavior.
tests:
  - focused camera QoS contract: one passed in 0.28 s
  - complete test_rgbd_cup_pose.py: 43 passed in 0.31 s
  - complete src/so101_demo_py/test with registered-root ROS_LOG_DIR: 444 passed in 13.56 s
decision: COMMIT_MINIMAL_GREEN_THEN_REBUILD_CANDIDATE_AND_RUN_REAL_LIVE_PERCEPTION_SMOKE
next_experiment: SMOKE-013
```

## CP-058 — Plan installed reliable-QoS live perception smoke

```yaml
checkpoint_id: CP-058
recorded_at: 2026-08-27T02:27:04+08:00
smoke_id: SMOKE-013
status: PLANNED
qualification: false
implementation_commit: 7f767f818a3e97533b9d0b359d5c1e3ddc464bc7
record_head_before_checkpoint: 7f767f818a3e97533b9d0b359d5c1e3ddc464bc7
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
candidate:
  demo_prefix: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_demo_py
  support_prefix: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_mujoco_support
  installed_bundle_sha256: e1dae424668fe418e64f05cda6976308670ade43639df7b0fbc97d74fb8e4f93
  support_plugin_sha256: f4487cc3e2467e2ffec5b2ca2fa407d8c372b63cfe07cc1e71e777185d1a7ab7
  installed_contracts: 5 passed in 1.78 s
  support_ctest_correct_source_order: 1 of 1 test target passed, 19 gtests, in 3.61 s
environment:
  domain_id: 207
  session_id: mac-mrc010-real-qos-green-r6
  evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/real-rgbd-qos-green-r6/live
  keyframe: task_start
procedure:
  - Fresh-read domain graph, exact tmux/process identities, evidence directory, and Viewer; require all empty.
  - Start the installed base stack and the two registered static transforms, then wait for Scene READ_BACK and capture the exact Viewer baseline.
  - Start the independent cup-pose observer before the exact installed rgbd_cup_pose executable with its unchanged 30.0 s startup timeout.
  - Do not start dynamic_cup_pick_place or any motion.
success_gate:
  - Perception writes summary.json and nonempty cup.ply, publishes a world-frame /cup_pose observed by the independent subscriber, and exits or is exact-stopped only after those artifacts appear.
  - First valid evidence must occur within 30.0 s measured from the perception child monotonic start; no construction timeout, no no-valid timeout, no segfault, and no truth bridge.
  - Exact-owned cleanup leaves domain 207, session, processes, and Viewer empty.
helpers:
  base_sha256: 0bb34918850c2da898658d0a7d539b7fe2248c74e6171952908c18aa0affbd99
  tf_sha256: fc1d33d0a7c684a8ee1cbff108ce8b7d2d8324eca10a2c6a6b469eb15f0ecb2a
  perception_sha256: f1dced33a58eecd9c6ee0904da5539bc1b0d37c78f756337ffeca3c867562f38
  observer_sha256: 86fcfbd247d6a2ea9c5f532528b5f649718018543fcca8848026affdd3070184
decision: COMMIT_PLAN_THEN_FRESH_PREFLIGHT_AND_RUN
next_experiment: SMOKE-013
```

## CP-059 / TRANS-SMOKE-013-RUNNING-001 — Start installed reliable-QoS live perception smoke

```yaml
checkpoint_id: CP-059
transition_id: TRANS-SMOKE-013-RUNNING-001
recorded_at: 2026-08-27T02:28:10+08:00
smoke_id: SMOKE-013
from: PLANNED
to: RUNNING
qualification: false
implementation_commit: 7f767f818a3e97533b9d0b359d5c1e3ddc464bc7
record_head_before_transition: 27f0b31998bb60400abdacd17f412a16d21d8e17
pre_running_observed:
  - Domain 207 graph, evidence path, exact task tmux/process identities, and Viewer were fresh and empty.
  - Task-owned tmux pane completed explicit in-pane cd after shell initialization and read back the exact worktree path.
  - Candidate prefixes, installed bundle, installed runtime source, support plugin SHA, focused installed contracts, and correct-source-order support CTest match CP-058.
decision: START_BASE_STATIC_TF_GUI_THEN_OBSERVER_AND_INSTALLED_PERCEPTION
next_command: No dynamic node or motion; close on the first valid installed perception result.
```

## CP-060 / CLOSE-SMOKE-013-001 — Installed reliable-QoS perception succeeds on live MuJoCo RGB-D

```yaml
checkpoint_id: CP-060
transition_id: CLOSE-SMOKE-013-001
recorded_at: 2026-08-27T02:33:42+08:00
smoke_id: SMOKE-013
from: RUNNING
to: VALID_DIAGNOSTIC_SUCCESS
qualification: false
implementation_commit: 7f767f818a3e97533b9d0b359d5c1e3ddc464bc7
record_head_before_transition: 2432b91b0eb96893c8d53d45ca6cc75341ad5f9f
provenance:
  demo_prefix: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_demo_py
  support_prefix: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_mujoco_support
  installed_bundle_sha256: e1dae424668fe418e64f05cda6976308670ade43639df7b0fbc97d74fb8e4f93
  support_plugin_sha256: f4487cc3e2467e2ffec5b2ca2fa407d8c372b63cfe07cc1e71e777185d1a7ab7
timing:
  observer_ready_epoch_s: 1787769103.0150871
  perception_owner_start_epoch_s: 1787769112.0
  first_ok_epoch_s: 1787769133.503602
  first_ok_from_owner_s: 21.503602
  summary_mtime_from_monotonic_start_file_mtime_s: 17.961806
  startup_deadline_s: 30.0
perception:
  status: OK
  input_frame_id: task_camera_frame
  output_frame_id: world
  output_topic: /cup_pose
  position_xyz: [0.01949905513971856, -0.28040477913291795, 0.16499999999999998]
  fitted_radius_m: 0.03938055155330842
  expected_radius_m: 0.04
  full_point_count: 98080
  color_candidate_point_count: 260
  cup_point_count: 141
  ply_bytes: 4013
independent_observer:
  frame_id: world
  position_xyz: [0.01949905513971856, -0.28040477913291795, 0.16499999999999998]
  orientation_xyzw: [0.0, 0.0, 0.0, 1.0]
gui:
  exact_window_id: 45489
  exact_owner_pid: 17308
  original_capture_resolution: [2504, 1770]
shutdown:
  - After success artifacts appeared, one Ctrl-C was sent only to the exact perception pane; child PID 24361 disappeared, but its wrapper pane exited before writing exit-code and finished-at files. This bounded observer gap is not a product failure.
  - Exact Ctrl-C then stopped only this run's base and TF panes; robot_state_publisher, move_group, ros2_control, controllers, UI, and plugin teardown were clean.
  - Post-cleanup domain 207 had no nodes, task tmux/process identities and Viewer were absent, with only builtin /parameter_events and /rosout topic names reported.
evidence:
  root: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/real-rgbd-qos-green-r6/live
  summary_sha256: a13551970de14650c5ef7607f987ea4c560ebfc7c915cb4a16b1802ba47bc0bc
  ply_sha256: be6dc51ee934f0f8fb73a6744ebfa59235600a97c1143056f5d501b18fa3acb5
  observer_sha256: 950a1a6e8cbade56ce329475b2366b44b9a154a70c53aadd5aca3d6fd8db7180
  perception_log_sha256: eccc728e9f87f7f5e0a6dc23107e73848396c3f66fc4571c08d5f8afc5323fc0
  baseline_manifest_sha256: 23da5a26dda26853f1e3eb66d1f3726bc07485e70ef2ffb268c10ac23c31c7b4
  baseline_png_sha256: 5e95b4e5f296d1751d82bab1872a476a619ac8b4390a1fad73976ecc8937485c
  base_log_sha256: 61d2295f46272f8550765ffb0780bc7ab16357b0a30f6a42b98058a19217744a
decision: RESUME_FOUR_POSITION_FULL_RESTART_QUALIFICATION_WITH_THIS_INSTALLED_BUNDLE
next_experiment: EXP-017
```

## CP-061 — Plan fixed-candidate task_start qualification

```yaml
checkpoint_id: CP-061
recorded_at: 2026-08-27T02:35:25+08:00
experiment_id: EXP-017
status: PLANNED
qualification: true
position: task_start
lifecycle: FULL_RESTART
implementation_commit: 7f767f818a3e97533b9d0b359d5c1e3ddc464bc7
record_head_before_checkpoint: a6becb0d0bfb805f2e8d7bbfc44391fe18911b13
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
installed_bundle_sha256: e1dae424668fe418e64f05cda6976308670ade43639df7b0fbc97d74fb8e4f93
identity:
  domain: 233
  session: mac-mrc010-task-start-exp017
  tmux: mrc010-mac-exp017
  evidence_file: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-017/task-start.json
  evidence_root: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-017
command: ros2 run so101_demo_py so101_mujoco_perception_pick_place run_mode:=execute execute:=true headless:=false session_id:=mac-mrc010-task-start-exp017 mujoco_initial_keyframe:=task_start evidence_file:=/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-017/task-start.json
capture_protocol:
  - Concurrent exact-title coordinator captures one exact MuJoCo Viewer window ID at baseline, transport, and released-final manifest boundaries; retain manifest and PNG and inspect original resolution.
success_criteria: Every AC-001 camera, point-cloud, TF, no-truth-bridge, DONE/19, motion/FK, physical, Planning Scene, three-capture, eleven-exit, and exact-cleanup clause passes.
failure_criteria: With valid preconditions/provenance, any product clause failure stops the four-position batch for systematic debugging.
helpers:
  runner_sha256: 0ffe25a624c31aeccb300cd9947111ee5141059d579bf894ab255caaa96237e8
  capture_sha256: bf207075ec216c60e74493ad6fc6872fa2d85d7b833348da744d58f944d1b054
sequence_gate: No forward run until EXP-017 has a committed countable-success closure.
decision: COMMIT_PLAN_THEN_FRESH_PREFLIGHT
next_experiment: EXP-017
```

## CP-062 / CLOSE-EXP-017-001 — Reject unsupported FastDDS domain before product launch

```yaml
checkpoint_id: CP-062
transition_id: CLOSE-EXP-017-001
recorded_at: 2026-08-27T02:36:05+08:00
experiment_id: EXP-017
from: PLANNED
to: INVALID_PREFLIGHT
qualification: false
reason: FastDDS rejected domain 233 because its calculated port exceeds the supported range; the empty-graph probe failed before any ROS entity or product process was created.
preserved_empty_state: EXP-017 evidence root, tmux, exact session processes, and MuJoCo Viewer remained absent.
decision: RETAIN_INVALID_PLAN_AND_USE_FRESH_SUPPORTED_DOMAIN
next_experiment: EXP-018
```

## CP-063 — Replan task_start qualification on supported domain

```yaml
checkpoint_id: CP-063
recorded_at: 2026-08-27T02:36:30+08:00
experiment_id: EXP-018
status: PLANNED
qualification: true
position: task_start
lifecycle: FULL_RESTART
implementation_commit: 7f767f818a3e97533b9d0b359d5c1e3ddc464bc7
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
installed_bundle_sha256: e1dae424668fe418e64f05cda6976308670ade43639df7b0fbc97d74fb8e4f93
identity:
  domain: 200
  session: mac-mrc010-task-start-exp018
  tmux: mrc010-mac-exp018
  evidence_file: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-018/task-start.json
single_change_from_exp017: Replace unsupported domain 233 with supported fresh domain 200 and fresh experiment/session/evidence identities; all product, helper, capture, and AC-001 criteria remain exactly CP-061.
decision: COMMIT_PLAN_THEN_FRESH_PREFLIGHT
next_experiment: EXP-018
```

## CP-064 / TRANS-EXP-018-RUNNING-001 — Start fixed-candidate task_start qualification

```yaml
checkpoint_id: CP-064
transition_id: TRANS-EXP-018-RUNNING-001
recorded_at: 2026-08-27T02:37:20+08:00
experiment_id: EXP-018
from: PLANNED
to: RUNNING
qualification: true
position: task_start
implementation_commit: 7f767f818a3e97533b9d0b359d5c1e3ddc464bc7
pre_running_observed: Domain 200 graph, fresh evidence/session/tmux/process identities, and exact Viewer title are all empty; installed prefixes/bundle/helper hashes remain CP-061/063.
decision: START_EXACT_INSTALLED_FULL_RESTART_AND_CONCURRENT_CAPTURE
```

## CP-065 / CLOSE-EXP-018-001 — Reject capture-directory race before baseline

```yaml
checkpoint_id: CP-065
transition_id: CLOSE-EXP-018-001
recorded_at: 2026-08-27T02:38:30+08:00
experiment_id: EXP-018
from: RUNNING
to: INVALID_CAPTURE_RUNNER
qualification: false
reason: The capture helper started before runner-created run/ existed, failed writing run/capture.owner, and exited before Viewer discovery or baseline. Product was exact-stopped during startup and is not behavior-classified.
cleanup: Exact session/process/Viewer/domain identities are empty; early shutdown diagnostics are secondary to intentional stop.
correction: Pre-create only the fresh evidence run and gui directories before starting the unchanged capture and product helpers.
decision: RETAIN_INVALID_AND_REPEAT_FRESH_TASK_START
next_experiment: EXP-019
```

## CP-066 — Plan capture-safe task_start qualification retry

```yaml
checkpoint_id: CP-066
recorded_at: 2026-08-27T02:39:00+08:00
experiment_id: EXP-019
status: PLANNED
qualification: true
position: task_start
lifecycle: FULL_RESTART
implementation_commit: 7f767f818a3e97533b9d0b359d5c1e3ddc464bc7
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
installed_bundle_sha256: e1dae424668fe418e64f05cda6976308670ade43639df7b0fbc97d74fb8e4f93
identity: {domain: 201, session: mac-mrc010-task-start-exp019, tmux: mrc010-mac-exp019, evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-019, evidence_file: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-019/task-start.json}
single_runner_correction: After fresh preflight and RUNNING commit, pre-create empty run/ and gui/ directories so the unchanged concurrent capture helper can write ownership before product launch; all product/helper/AC-001 gates remain CP-061.
decision: COMMIT_PLAN_THEN_FRESH_PREFLIGHT
next_experiment: EXP-019
```

## CP-067 / TRANS-EXP-019-RUNNING-001 — Start capture-safe task_start qualification

```yaml
checkpoint_id: CP-067
transition_id: TRANS-EXP-019-RUNNING-001
recorded_at: 2026-08-27T02:39:40+08:00
experiment_id: EXP-019
from: PLANNED
to: RUNNING
qualification: true
position: task_start
implementation_commit: 7f767f818a3e97533b9d0b359d5c1e3ddc464bc7
pre_running_observed: Domain 201, evidence, exact session/tmux/processes, and Viewer are fresh and empty; frozen installed provenance/helper hashes unchanged.
decision: PRECREATE_EMPTY_RUN_GUI_THEN_START_CAPTURE_AND_FULL_RESTART
```

## CP-068 / CLOSE-EXP-019-001 — Reject non-executable capture invocation before product launch

```yaml
checkpoint_id: CP-068
transition_id: CLOSE-EXP-019-001
recorded_at: 2026-08-27T02:41:00+08:00
experiment_id: EXP-019
from: RUNNING
to: INVALID_CAPTURE_RUNNER
qualification: false
reason: The capture helper is intentionally non-executable and the tmux command used exec path instead of explicit zsh; capture exited before owner/readiness and product never started.
diagnostic_cleanup: An explicit-zsh observer-only check created ownership and was exact-stopped by PID; idle tmux was removed. No product, ROS graph, or Viewer existed.
correction: Invoke the unchanged helper as exec zsh helper and require the live capture pane plus owner file before product launch.
decision: RETAIN_INVALID_AND_REPEAT_FRESH_TASK_START
next_experiment: EXP-020
```

## CP-069 — Plan explicit-zsh capture-safe task_start qualification

```yaml
checkpoint_id: CP-069
recorded_at: 2026-08-27T02:41:20+08:00
experiment_id: EXP-020
status: PLANNED
qualification: true
position: task_start
lifecycle: FULL_RESTART
implementation_commit: 7f767f818a3e97533b9d0b359d5c1e3ddc464bc7
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
installed_bundle_sha256: e1dae424668fe418e64f05cda6976308670ade43639df7b0fbc97d74fb8e4f93
identity: {domain: 202, session: mac-mrc010-task-start-exp020, tmux: mrc010-mac-exp020, evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-020, evidence_file: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-020/task-start.json}
runner_gate: After fresh preflight/RUNNING commit, create empty run/gui, invoke capture as exec zsh helper, and require capture pane plus owner file before launching the unchanged product. All CP-061 product/helper/AC-001 gates remain frozen.
decision: COMMIT_PLAN_THEN_FRESH_PREFLIGHT
next_experiment: EXP-020
```

## CP-070 / TRANS-EXP-020-RUNNING-001 — Start explicit-zsh task_start qualification

```yaml
checkpoint_id: CP-070
transition_id: TRANS-EXP-020-RUNNING-001
recorded_at: 2026-08-27T02:42:00+08:00
experiment_id: EXP-020
from: PLANNED
to: RUNNING
qualification: true
position: task_start
implementation_commit: 7f767f818a3e97533b9d0b359d5c1e3ddc464bc7
pre_running_observed: Domain 202, evidence, exact session/tmux/process identities, and Viewer are fresh and empty; frozen provenance unchanged.
decision: PROVE_EXPLICIT_ZSH_CAPTURE_OWNER_THEN_START_PRODUCT
```

## CP-071 / CLOSE-EXP-020-001 — Valid MoveIt action-result delivery timeout

```yaml
checkpoint_id: CP-071
transition_id: CLOSE-EXP-020-001
recorded_at: 2026-08-27T02:46:30+08:00
experiment_id: EXP-020
from: RUNNING
to: VALID_BEHAVIORAL_FAILURE
qualification: false
position: task_start
implementation_commit: 7f767f818a3e97533b9d0b359d5c1e3ddc464bc7
valid_preconditions:
  - Fresh domain/session/evidence, exact installed prefixes/executable/child/support plugin/bundle, explicit cwd, Scene READ_BACK, camera, static TF, controllers, MoveIt, perception, and dynamic ownership all passed.
  - Reliable perception produced task_camera_frame RGB-D, 98080 full points, 141 cup points, 4013-byte PLY, radius 0.0393805516 m, and world pose [0.0194990551, -0.2804047791, 0.165].
failure:
  code: MOVEIT_EXECUTION_FAILED
  moveit_error: -6
  state_trace: [IDLE, PREPARE_OPEN_GRIPPER, MOVE_ABOVE_OBJECT, DESCEND, RECOVER_OPEN_GRIPPER, RECOVER_DETACH_GAZEBO, RECOVER_DETACH_MOVEIT, RECOVER_SYNC_WORLD_OBJECT, RECOVER_RETREAT, ERROR]
first_bad_boundary:
  - DESCEND arm_controller accepted at 1787769891.171543 and physically reported Goal reached at 1787769892.420400.
  - MoveIt timed out at 1787769894.095596 despite the physical success, then observed Controller successfully finished only at 1787769894.568601, about 2.148 s after controller completion.
  - This is action-result delivery latency, not a joint/controller physical miss. Reliable 640x480 RGB-D at 10 Hz plus ongoing Open3D processing and frame-error logging remained active over this interval.
recovery: Cup never left table support; recovery detach/sync/retreat completed and final cup remained at [0.02, -0.28, 0.1648015665] with no gripper contacts.
capture_concern: Exact Viewer window 45531/PID57668 and baseline boundary time were recorded, but the nested capture command returned no PNG/manifest and an empty baseline-capture.json; no transport/final boundary existed after the product failure.
cleanup: Product naturally exited one; only lingering exact capture pane was stopped; domain202, task tmux/processes, and Viewer are empty.
evidence:
  root: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-020
  log_sha256: 7981afffaf09e3bc9d973be8201788cfafa0c8cb9cf9569aed84726f59deac63
  manifest_sha256: fb91758f88509f959a0e1c7284b936cb0988a38923411002e99f884f56d10618
  perception_summary_sha256: 222b1b6bbd15aa83c17573f729897eda5eea3b7879623143d4a664d1c85aec29
  ply_sha256: be6dc51ee934f0f8fb73a6744ebfa59235600a97c1143056f5d501b18fa3acb5
decision: STOP_FOUR_POSITION_BATCH_AND_DIAGNOSE_DDS_PERCEPTION_LOAD_BEFORE_ANY_POLICY_CHANGE
next_experiment: NONE
```

## CP-072 — Plan 2 Hz camera-load causal A/B

```yaml
checkpoint_id: CP-072
recorded_at: 2026-08-27T02:48:00+08:00
smoke_id: SMOKE-014
status: PLANNED
qualification: false
base_failure: EXP-020
hypothesis: Continuous reliable 640x480 RGB-D at 10 Hz plus perception processing delays the arm action result beyond MoveIt's execution bound; reducing only CameraPlugin publish rate to 2 Hz will cross DESCEND without action-result timeout.
method:
  - Copy so101_demo_py at commit 7f767f8 into a registered-root diagnostic source and change only mujoco_plugins.yaml camera_publish_rate from 10.0 to 2.0.
  - Build a separate diagnostic install against the unchanged candidate fork/support; never modify the frozen qualification source/install.
  - Fresh domain203/session mac-mrc010-dds-2hz-smoke014/evidence mac-diagnosis/dds-2hz-smoke014; run the exact full workflow without qualification or motion-policy changes.
success_boundary: Dynamic state trace crosses DESCEND into grasp/lift/transport without MOVEIT_EXECUTION_FAILED -6; record arm accepted/goal-reached/result-observed timestamps and camera rate.
failure_boundary: Same action-result timeout remains, disproving camera rate as the primary causal variable.
decision: COMMIT_PLAN_BUILD_DIAGNOSTIC_OVERLAY_THEN_FRESH_RUN
next_experiment: SMOKE-014
```

## CP-073 / TRANS-SMOKE-014-RUNNING-001 — Start isolated 2 Hz camera-load causal probe

```yaml
checkpoint_id: CP-073
transition_id: TRANS-SMOKE-014-RUNNING-001
recorded_at: 2026-08-27T02:53:00+08:00
smoke_id: SMOKE-014
from: PLANNED
to: RUNNING
qualification: false
identity: {domain: 203, session: mac-mrc010-dds-2hz-smoke014, tmux: mac-mrc010-dds-2hz-smoke014, evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/dds-2hz-smoke014/live}
pre_running_observed:
  - Domain 203, exact session/process identities, Viewer, and live evidence path were fresh and empty.
  - Production prefix remained mac-candidate/project-install/so101_demo_py with camera_publish_rate 10.0 and YAML SHA256 57e4810c139bd19d9a1fba2b3618c3ce183cf87338869736c5a961b03591ca96.
  - Diagnostic prefix resolved to mac-diagnosis/dds-2hz-smoke014/diag-install/so101_demo_py with only camera_publish_rate 2.0, YAML SHA256 fff3182aa99c100a3deeb27903bb246715a0f73f4bee7d0ee1c5cc7c87bd2681, and diagnostic bundle 2f6dee9ae868bc350b019b5ac2eb577a5c57a8e23f77a434ed1a650b10f301ed.
runner_sha256: 351c22403c75e84c834d90c28af93f60c425d598ddba2ddd6a3d21e83ea20c6b
decision: START_NON_QUALIFYING_FULL_CHAIN_AND_WAIT_FOR_NATURAL_EXIT
```

## CP-074 / CLOSE-SMOKE-014-001 — Reject deleted-cwd diagnostic runner

```yaml
checkpoint_id: CP-074
transition_id: CLOSE-SMOKE-014-001
recorded_at: 2026-08-27T02:54:45+08:00
smoke_id: SMOKE-014
from: RUNNING
to: INVALID_RUNNER
qualification: false
reason: The tmux pane ignored the requested working directory, inherited a deleted mujoco-ros2-control worktree, recorded working_directory=., and emitted getcwd failed / Python path errors before and during stack construction; the product environment was not equivalent to EXP-020.
product_disposition: No DDS/action-latency conclusion is drawn even though launch began.
cleanup: One Ctrl-C was sent only to exact tmux mac-mrc010-dds-2hz-smoke014; domain203, exact processes, Viewer, and session are empty.
correction: Use a fresh identity and an explicit in-pane cd plus absolute pwd readback gate before starting the unchanged diagnostic helper.
evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/dds-2hz-smoke014
decision: RETAIN_INVALID_AND_REPEAT_WITH_EXPLICIT_CWD
next_experiment: SMOKE-015
```

## CP-076 / TRANS-SMOKE-015-RUNNING-001 — Release explicit-cwd 2 Hz probe

```yaml
checkpoint_id: CP-076
transition_id: TRANS-SMOKE-015-RUNNING-001
recorded_at: 2026-08-27T02:56:40+08:00
smoke_id: SMOKE-015
from: PLANNED
to: RUNNING
qualification: false
pre_running_observed:
  - Fresh domain204, exact session/processes, Viewer, and live evidence were empty.
  - Gate-only tmux mac-mrc010-dds-2hz-smoke015 is owned by PID 89321 and has not started ROS/product.
  - pane_current_path and /bin/pwd -P both read /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-pick-place-mujoco-0-1-main.
decision: CREATE_START_SIGNAL_AND_WAIT_FOR_UNCHANGED_2HZ_HELPER_NATURAL_EXIT
```

## CP-077 / CLOSE-SMOKE-015-001 — 2 Hz shifts but does not eliminate action-result lag

```yaml
checkpoint_id: CP-077
transition_id: CLOSE-SMOKE-015-001
recorded_at: 2026-08-27T03:00:30+08:00
smoke_id: SMOKE-015
from: RUNNING
to: CAUSAL_PARTIAL_PASS
qualification: false
valid_preconditions: Explicit task-worktree cwd, fresh domain204/session/evidence, diagnostic camera_publish_rate 2.0, exact candidate fork/support, perception world pose, and natural lifecycle all passed.
original_boundary_result:
  - State trace crossed DESCEND, CLOSE_GRIPPER, MICRO_LIFT, VERIFY_PHYSICAL_GRASP, ATTACH_MOVEIT, LIFT, and entered MOVE_ABOVE_PLACE.
  - All six segmented DESCEND trajectories delivered controller success to MoveIt 0.0048 to 0.0539 seconds after physical Goal reached, versus about 2.148 seconds at the first DESCEND segment in EXP-020.
later_failure:
  - MOVE_ABOVE_PLACE arm goal accepted at 1787770704.058625 and physically reached at 1787770705.377898.
  - MoveIt received no result before waitForExecution timeout at 1787770707.084773, a greater-than-1.706-second post-physical-completion lag.
  - Manifest ended MOVEIT_EXECUTION_FAILED with last_error MOVEIT_EXECUTION_MONITOR_ABORTED:DYNAMIC_EARLY_TABLE_CONTACT and recovery state trace, so the full workflow did not succeed.
conclusion: Lowering RGB-D from 10 to 2 Hz materially reduces result-delivery latency and moves the first failure later, supporting DDS/perception load causality, but 2 Hz alone is not a sufficient production fix.
cleanup: Natural rc1; domain204, exact processes, Viewer, and session are empty.
evidence:
  root: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/dds-2hz-smoke015
  log_sha256: 959ee12613e60b369e5bd256b09922fded6fe4ed3edc47b304083d501bc72ae0
  manifest_sha256: 57c2289a3ac29a3c33858bef25e451e9fb3961f93fe6d7ca3a592596110b2fc2
decision: DO_NOT_TDD_2HZ_ALONE; TEST_LONG_LIVED_PERCEPTION_WITH_INPUT_SUBSCRIPTIONS_RELEASED_AFTER_FIRST_VALID_POSE
next_experiment: SMOKE-016
```

## CP-079 — Correct SMOKE-015 primary-versus-recovery failure attribution

```yaml
checkpoint_id: CP-079
recorded_at: 2026-08-27T03:02:30+08:00
amends_checkpoint: CP-077
primary_failure: MOVE_ABOVE_PLACE waitForExecution action-result timeout after physical Goal reached, as established by the wall-clock controller/MoveIt log boundary.
secondary_recovery_failure: Manifest last_error DYNAMIC_EARLY_TABLE_CONTACT arose only after RECOVER_LIFT_TO_SAFE_HEIGHT and RECOVER_MOVE_ABOVE_PICK, when carried recovery RECOVER_DESCEND_TO_PICK approached the table-supported pick pose and rejected table contact.
evidence_interpretation: Recovery samples through RECOVER_MOVE_ABOVE_PICK remain table_contact=false; DYNAMIC_EARLY_TABLE_CONTACT is not evidence that transport physically dropped the cup and must not replace the primary DDS/action-result diagnosis.
decision: KEEP_SMOKE_016_FOCUSED_ON_POST_FIRST_VALID_RGBD_TRAFFIC
```

## CP-080 / TRANS-SMOKE-016-RUNNING-001 — Start perception input-release causal probe

```yaml
checkpoint_id: CP-080
transition_id: TRANS-SMOKE-016-RUNNING-001
recorded_at: 2026-08-27T03:05:20+08:00
smoke_id: SMOKE-016
from: PLANNED
to: RUNNING
qualification: false
identity: {domain: 205, session: mac-mrc010-perception-release-smoke016, tmux: mac-mrc010-perception-release-smoke016, evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/perception-release-smoke016}
pre_running_observed:
  - Fresh domain205/session/processes/Viewer/live evidence all empty; task worktree clean.
  - Diagnostic installed prefix and module resolve inside the registered root, camera remains 10.0 Hz, input-release marker is present, diagnostic bundle is c1d832e18968387670beae12ef87e1daf0450413c98acb11f7bc5cd87484f80d.
  - Gate-only pane PID10781 has not started ROS; pane_current_path and /bin/pwd -P both equal the exact task worktree.
diagnostic_source_sha256: de40cd14af074459f9ac016fae3b09a121309e1e0d0fa209e7e61c82fb3fc842
diagnostic_patch_sha256: 7ebf7d3c18dc06b923d0229e5da12ba65ca2bbd095ecae8ad908d04870e8de95
decision: CREATE_START_SIGNAL_AND_WAIT_FOR_NATURAL_FULL_CHAIN_EXIT
```

## CP-081 / CLOSE-SMOKE-016-001 — Post-first-valid input release removes action starvation

```yaml
checkpoint_id: CP-081
transition_id: CLOSE-SMOKE-016-001
recorded_at: 2026-08-27T03:08:30+08:00
smoke_id: SMOKE-016
from: RUNNING
to: CAUSAL_PASS
qualification: false
valid_preconditions: Fresh domain205/session/evidence, exact cwd/prefix/fork/support, unchanged camera_publish_rate 10.0 and motion policy, valid world pose/PLY/JSON, and INPUT_RELEASED_AFTER_FIRST_VALID count3 all passed.
provenance_note: Runtime bundle c995f5ebedfea8a0f0bccaf19e05c839277a54f16a449df4da0795d4c5f3a95b is the deterministic diagnostic bundle with SO101_SOURCE_COMMIT=7f767f8; CP-080's c1d832e value omitted that required environment variable during readback and is superseded.
result:
  - Natural rc0, status DONE, transition_count 19, full state trace through detach-before-open, placement validation, sync, and retreat.
  - 22 arm trajectories paired physical Goal reached to MoveIt Controller successfully finished with maximum delivery latency 0.053310 seconds; no waitForExecution timeout occurred.
  - Final cup [-0.07777456, -0.24757163, 0.16483053], table_contact true, zero fingertip contacts, and settled velocities; release marker sequence 6324.
causal_conclusion: Retaining the reliable RGB-D subscriptions after the one required perception result caused the Mac action-result starvation. Releasing exactly those three inputs after first valid pose while retaining node/publisher/TF is sufficient for the complete task_start chain at camera 10 Hz.
cleanup: Natural shutdown; domain205, exact processes, Viewer, and session are empty.
evidence:
  root: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/perception-release-smoke016
  log_sha256: 8a7ef0805408fa0f3a69282b3ef8a0f6d60fcc5fd5f18fac33d601f526e0c304
  manifest_sha256: ea016d164edc7ad755d5cc2166658be38e2b8184dc77973c58d25f1b90fc43ed
  perception_summary_sha256: f962f882186116d299a41836974b0fc43d1e5fc1eb2c6f4d9a0371df2fe85842
  ply_sha256: be6dc51ee934f0f8fb73a6744ebfa59235600a97c1143056f5d501b18fa3acb5
decision: TDD_PRODUCTIONIZE_IDEMPOTENT_EXACT_THREE_INPUT_RELEASE_WITH_STABLE_STATUS
next_experiment: NONE
```

## CP-078 — Plan post-first-valid perception input-release causal probe

```yaml
checkpoint_id: CP-078
recorded_at: 2026-08-27T03:01:15+08:00
smoke_id: SMOKE-016
status: PLANNED
qualification: false
base_failures: [EXP-020, SMOKE-015]
hypothesis: The dynamic workflow needs only the first valid /cup_pose; retaining three reliable 640x480 RGB-D subscriptions during motion causes intermittent DDS/action result starvation. Keeping rgbd_cup_pose alive while releasing only its input subscriptions immediately after the first valid publish will remove that traffic and allow all motion states to finish.
method:
  - Copy production so101_demo_py at commit 7f767f8 into a registered-root diagnostic source; retain camera_publish_rate 10.0 and every motion/config policy unchanged.
  - Change only diagnostic rgbd_cup_pose runtime ownership so the three camera subscriptions are destroyed and removed after the first successful world-pose publication; keep node, TF listener, /cup_pose publisher, and launch lifetime alive.
  - Build a separate diagnostic install, preserve diff/source/install hashes, then use fresh domain205/session mac-mrc010-perception-release-smoke016/evidence mac-diagnosis/perception-release-smoke016 with explicit cwd barrier.
success_boundary: Full task_start workflow exits zero/DONE and action results remain promptly observed after each physical Goal reached; diagnostic log proves INPUT_RELEASED_AFTER_FIRST_VALID.
failure_boundary: Any valid full-chain failure stops the experiment and disproves sufficiency; no timeout/policy/extrinsics change is allowed.
decision: COMMIT_PLAN_BUILD_ISOLATED_DIAGNOSTIC_THEN_FRESH_RUN
next_experiment: SMOKE-016
```

## CP-075 — Plan explicit-cwd 2 Hz camera-load causal probe

```yaml
checkpoint_id: CP-075
recorded_at: 2026-08-27T02:55:30+08:00
smoke_id: SMOKE-015
status: PLANNED
qualification: false
base_failure: EXP-020
identity: {domain: 204, session: mac-mrc010-dds-2hz-smoke015, tmux: mac-mrc010-dds-2hz-smoke015, evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/dds-2hz-smoke015}
controlled_variable: Reuse the immutable SMOKE-014 diagnostic overlay and helper with camera_publish_rate 2.0; use a fresh domain/session/run/evidence only.
runner_gate:
  - The task-owned gate runner explicitly cds to the exact task worktree and records /bin/pwd -P before waiting.
  - Require pane_current_path and recorded pane-pwd to both equal the task worktree before creating start.signal.
  - Then exec the unchanged 2 Hz full-chain helper SHA256 351c22403c75e84c834d90c28af93f60c425d598ddba2ddd6a3d21e83ea20c6b.
gate_runner_sha256: a81a7e81681209d6e21674776a68992f838aeeef93ca3209de566b5b79e7c9fd
success_boundary: Same as SMOKE-014; cross DESCEND without -6 and record action timing.
decision: COMMIT_PLAN_THEN_FRESH_PREFLIGHT_AND_CWD_BARRIER
next_experiment: SMOKE-015
```
