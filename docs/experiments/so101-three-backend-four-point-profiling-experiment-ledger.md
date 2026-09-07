# SO-101 three-backend four-point profiling experiment ledger

```yaml
task_id: so101-three-backend-four-point-profiling-20260907
status: PASS
goal: Extend semantic profiling to color-geometry RGB-D, YOLO-Seg RGB-D, and Grounded SAM RGB-D perception pick-place, then qualify four successful MuJoCo points for every backend.
worktree: /Users/matianyi/.codex/worktrees/e25f6316-2ce5-4d0c-8e8f-c526f066e2f7/moveit-demo
base_commit: d8fd978fcab431099b761d7e184a79f12edba351
evidence_root: /data/work/so101-evidence/so101-three-backend-four-point-profiling/20260907T080303Z-880a7aeb
latest_checkpoint: CP-004
retained_runs:
  - candidate
  - candidate-r2
  - runs/color_geometry
  - runs/yolo_seg
  - runs/grounded_sam
  - run-evidence
archived_runs: []
deletion_candidates:
  - scratch/package-test-001 through scratch/package-test-006
  - scratch/focused-red-keyframes-001 through scratch/focused-final-009
  - every scratch/live-* directory
  - run-evidence/invalid-sync-001
  - run-evidence/invalid-sync-002
deletions_performed: []
```

## EXP-001 - profiling contract extension

```yaml
experiment_id: EXP-001
status: PASS
hypothesis: The two model-backed RGB-D paths and the dynamic runtime can join the existing correlated profiling session without changing profiling-off behavior.
single_variable: profiling propagation and semantic spans in the public perception pick-place launch
lifecycle: TEST_ONLY
provenance:
  source_commit: d8fd978fcab431099b761d7e184a79f12edba351 plus the candidate patch
  candidate: /data/work/so101-evidence/so101-three-backend-four-point-profiling/20260907T080303Z-880a7aeb/candidate-r2
  install_overlay: /data/work/so101-evidence/so101-three-backend-four-point-profiling/20260907T080303Z-880a7aeb/install
  runtime_python: /data/work/venvs/so101-grounded-sam/bin/python
results:
  profiling_modes: [off, summary, trace]
  process_roles: [launch, perception, runtime]
  required_spans:
    - launch.total
    - runtime.total
    - perception.total
    - perception.wait_all_subscriptions_matched
    - perception.wait_all_first_callbacks
    - perception.wait_common_stamp
    - perception.wait_synchronized_frame
    - perception.transform_world
    - perception.estimate_cup_pose
  yolo_container_profiling_mount: /profiling
  model_backend_start_order: dynamic subscriber, one-second timer, model perception
  required_pose_output_discovery: enabled by the perception pick-place launch
  direct_cli_optional_output_discovery: preserved
  focused_final_gate: 172 passed in 2.69 seconds
  ordinary_gate: 1507 passed with 4 existing fork warnings in 23.99 seconds
  benchmark_test_collected: false
  diff_check: PASS
  compileall: PASS
```

The implementation adds profiling arguments to `rgbd_object_pose` and
`dynamic_cup_pick_place`, records the shared RGB-D subscription milestones and
perception spans in `rgbd_object_pose_node`, and propagates one session through
all three public launch backends. The launch mounts the profiling root into the
YOLO container and starts model perception only after the dynamic consumer.
The model node then requires discovery of the `/cup_pose` subscriber before it
freezes and publishes the fresh RGB-D request.

## EXP-002 - ai-station three-by-four live qualification

```yaml
experiment_id: EXP-002
status: PASS
hypothesis: Every backend can complete the same four MuJoCo keyframes while producing complete correlated profiling and physical outcome evidence.
single_variable: perception backend across three separately validated four-point matrices
lifecycle: FULL_RESTART_PER_RUN
fixed_inputs:
  points:
    - task_start
    - cup_test_forward_5cm
    - cup_test_left_5cm
    - cup_test_right_5cm
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_sam_bundle_manifest_sha256: b55bb601d311407df8f9f25d9da18649f6bd78ac1299148bde0d07f7cfdfed05
  runtime_device_for_model_backends: cuda
  qualified_mujoco_binary_root: /data/work/so101-evidence/fusion/ai-station-linux-headless-rgbd-four-point-20260828/candidate/ws_mujoco_ros2_control_fork/install
acceptance:
  validated_runs: 12
  status_done: 12
  transition_count_19: 12
  perception_status_ok: 12
  perception_total_published: 12
  complete_profiling_manifest: 12
  final_table_contact: 12
  final_zero_gripper_contacts: 12
  final_speed_below_1e-3: 12
  empty_moveit_attached_objects: 12
  exact_window_gui_sequences: 12
  result: PASS
aggregate_evidence:
  json: run-evidence/selected-runs-validation.json
  tsv: run-evidence/selected-runs-validation.tsv
```

| Backend | Keyframe | Selected run | Profiling | Input XY error (m) | GUI frames | Result |
|---|---|---|---|---:|---:|---|
| color_geometry | task_start | color-task-start-r3 | trace | 0.000642 | 12 | PASS |
| color_geometry | cup_test_forward_5cm | color-forward | summary | 0.000594 | 14 | PASS |
| color_geometry | cup_test_left_5cm | color-left | summary | 0.000693 | 12 | PASS |
| color_geometry | cup_test_right_5cm | color-right | summary | 0.000631 | 13 | PASS |
| yolo_seg | task_start | yolo-task-start-r4 | trace | 0.000457 | 13 | PASS |
| yolo_seg | cup_test_forward_5cm | yolo-forward-r2 | summary | 0.000506 | 14 | PASS |
| yolo_seg | cup_test_left_5cm | yolo-left-r3 | summary | 0.000435 | 12 | PASS |
| yolo_seg | cup_test_right_5cm | yolo-right-r2 | summary | 0.000489 | 13 | PASS |
| grounded_sam | task_start | grounded-task-start-r3 | trace | 0.000485 | 15 | PASS |
| grounded_sam | cup_test_forward_5cm | grounded-forward-r4 | summary | 0.000455 | 16 | PASS |
| grounded_sam | cup_test_left_5cm | grounded-left-r3 | summary | 0.000444 | 15 | PASS |
| grounded_sam | cup_test_right_5cm | grounded-right-r4 | summary | 0.000499 | 15 | PASS |

The selected task-start run for each backend used trace mode. `babeltrace2`
read back 3,586,096 color-geometry events, 3,859,002 YOLO-Seg events, and
4,457,081 Grounded SAM events. Postflight checks found no owned LTTng session,
no owned perception container, and no retained GPU compute process.

Every selected GUI sequence uses exactly one `MuJoCo/MuJoCo` window. The
expected title is `MuJoCo : so101_task_scene` for color geometry and YOLO-Seg,
and `MuJoCo : so101_v5_multi_object_scene` for Grounded SAM. The last capture
of `grounded-left-r3` occurred as the MuJoCo window closed and contained the
desktop despite its capture manifest. Visual review therefore uses frame 014;
the invalid last frame remains retained. The structured final placement for
that run remains valid and independent of the GUI frame.

## Invalid and superseded attempts

All attempts below remain under the registered evidence root and are excluded
from the 12 selected runs.

| Attempt | Classification | Reason |
|---|---|---|
| candidate | invalid setup | Git LFS smudge timed out before worktree creation |
| package-test-001 | invalid test | system Python lacked the model runtime |
| package-test-002 | invalid overlay | support package resolved from the shared overlay |
| package-test-005 | invalid test environment | an extra prefix variable imposed the wrong support-package expectation; 1506 tests passed |
| color-task-start | invalid wrapper | unquoted zsh launch assignments |
| color-task-start-r2 | invalid scene | color geometry used the small-cup multi-object scene |
| yolo-task-start | superseded | business success, but an interrupted total span left the first profiling manifest incomplete |
| yolo-task-start-r2 | invalid handoff | first `/cup_pose` message was lost during process discovery |
| yolo-left-r2 | invalid handoff | reproduced the cross-container `/cup_pose` discovery race before the required handshake |
| grounded-task-start | invalid GUI contract | wrapper expected the single-object MuJoCo title |
| grounded-forward | invalid scene | the multi-object scene lacked the common 5 cm keyframes |
| grounded-forward-r3 | valid recovery, failed task | stochastic MoveIt execution failure at placement |
| grounded-left-r2 | valid recovery, failed task | stochastic MoveIt execution failure during descent |
| grounded-right-r2 | valid recovery, failed task | stochastic MoveIt execution failure during descent |
| grounded-right-r3 | valid recovery, failed task | stochastic MoveIt execution failure after placement descent |
| run-evidence/invalid-sync-001 and invalid-sync-002 | invalid file transfer | flat rsync destinations were moved out of the candidate without deletion |

Other successful runs superseded by a later lifecycle fix remain retained and
auditable but are not part of the selected 12-run matrix.

## CP-004 - completion checkpoint

```yaml
checkpoint_id: CP-004
status: COMPLETE
last_valid_experiment: EXP-002
candidate_base: d8fd978fcab431099b761d7e184a79f12edba351
installed_demo_prefix: /data/work/so101-evidence/so101-three-backend-four-point-profiling/20260907T080303Z-880a7aeb/install/so101_demo_py
installed_support_prefix: /data/work/so101-evidence/so101-three-backend-four-point-profiling/20260907T080303Z-880a7aeb/install/so101_mujoco_support
ordinary_test_gate: 1507 passed
focused_test_gate: 172 passed
selected_live_matrix: 12 of 12 passed
owned_processes: NONE
preserved_processes: all pre-existing tmux sessions and the shared /data/work/ws_moveit checkout
retained_runs: all candidate, live, trace, GUI, and test evidence under the registered evidence root
archived_runs: none
deletion_candidates: scratch trees and invalid-sync copies listed at the top of this ledger
deletions_performed: none
```
