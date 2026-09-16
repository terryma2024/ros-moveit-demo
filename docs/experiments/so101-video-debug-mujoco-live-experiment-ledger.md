---
task_id: so101-video-debug-mujoco-live
goal: Record and visually validate a real SO-101 MuJoCo GUI video sample on ai-station.
success_contract: The installed recorder runs against the owned MuJoCo window, produces a non-empty decodable video, yields a fresh final frame, and the frame visibly contains the expected SO-101 simulation scene.
worktree: /data/work/worktrees/so101-video-debug-forward-test-20260916
branch: detached
base_commit: 80e02810102190135c505a768bd5f6ebbfd71dae
current_commit: d4a0b1fe9f7e1fa8d86e0bb764c2d453fd66eddf
evidence_root: /data/work/so101-evidence/so101-video-debug-forward-test/20260916-a01
confirmed_conclusions:
  - EXP-001 did not start MuJoCo or produce video because GUI-only tools imported Pydantic-v2 server models under the ai-station Pydantic-v1 runtime.
  - The lazy package export fixes the Pydantic-v1 GUI-tool import boundary; 89 focused ai-station tests and all three installed tool probes passed (EXP-002).
  - Visible MuJoCo video-only sampling passes with sensor_rendering=false; the retained H.264 recording and fresh screenshots show the robot, cup, table, and placement ring (EXP-003).
disproven_routes:
  - A local-only test pass is sufficient evidence for MuJoCo video sampling (EXP-001).
  - The sensor-rendering task station is a valid video-only probe on the current ai-station runtime; concurrent GLFW initialization aborts before a window is recordable (EXP-002).
open_hypotheses:
  - NONE
latest_checkpoint: CP-002
next_experiment: NONE
---

## EXP-001

```yaml
experiment_id: EXP-001
status: INVALID
prior_experiment: NONE
hypothesis: The published simulator-neutral recorder can sample a MuJoCo GUI on ai-station.
prediction: Inventory, layout, and recorder commands start and a decodable video is produced.
single_variable: Published simulator-neutral video workflow at commit 80e02810102190135c505a768bd5f6ebbfd71dae.
lifecycle: ISOLATED_STACK
preconditions:
  - The task worktree is clean at the published commit.
success_criteria:
  - MuJoCo starts and a decodable video plus fresh frame are retained.
failure_criteria:
  - The owned MuJoCo window is not recordable or the resulting media is invalid.
invalid_criteria:
  - A prerequisite tool fails before MuJoCo sampling starts.
provenance:
  source_commit: 80e02810102190135c505a768bd5f6ebbfd71dae
  install_overlay: /data/work/worktrees/so101-video-debug-forward-test-20260916/install
  runtime_executable: so101_teleop installed scripts
  ros_domain_id: NOT_STARTED
  gz_partition: NOT_APPLICABLE
commands:
  - command: installed inventory, tiler, and recorder probes
    exit_code: 1
observed:
  - Python 3 imported Pydantic 1.10.14 and failed on models.field_validator before argument parsing.
  - MuJoCo was not launched; no video or screenshot was created.
inferred:
  - Importing so101_teleop.gui.x11 executes so101_teleop.__init__, which eagerly imports server models.
conclusion: The run is invalid as a video-sampling validation because prerequisite import failed before sampling.
evidence:
  - /data/work/so101-evidence/so101-video-debug-forward-test/20260916-a01/result.md
  - /data/work/so101-evidence/so101-video-debug-forward-test/20260916-a01/report.md
decision: REPEAT
next_experiment: EXP-002
```

## EXP-002

```yaml
experiment_id: EXP-002
status: VALID
prior_experiment: EXP-001
hypothesis: Deferring package-level server model imports lets GUI-only tools run under ai-station's Pydantic-v1 environment, enabling real MuJoCo video sampling.
prediction: The installed inventory, layout, and recorder tools parse and run; the owned MuJoCo window produces a non-empty decodable video and a visibly valid final frame.
single_variable: Replace the eager so101_teleop.models package import with a lazy compatibility boundary.
lifecycle: ISOLATED_STACK
preconditions:
  - The task worktree and install overlay resolve to the follow-up commit.
  - No unrelated MuJoCo window or task-owned runtime remains.
  - GUI environment comes from ~/gui-env.zsh.
success_criteria:
  - Installed GUI-only commands no longer import so101_teleop.models during startup.
  - A unique task-owned MuJoCo window is discovered by owner PID.
  - Recorder stop succeeds and ffprobe decodes a non-empty video.
  - A fresh extracted frame visibly contains the SO-101 robot and expected task scene.
failure_criteria:
  - The valid owned window cannot be recorded, media cannot be decoded, or visual content is blank/error/loading/incorrect.
invalid_criteria:
  - Commit or overlay provenance differs, window ownership is ambiguous, or evidence is stale.
provenance:
  source_commit: d4a0b1fe9f7e1fa8d86e0bb764c2d453fd66eddf
  install_overlay: /data/work/worktrees/so101-video-debug-forward-test-20260916/install
  runtime_executable: /data/work/ws_mujoco_ros2_control_fork/install/lib/mujoco_ros2_control/ros2_control_node
  ros_domain_id: 78
  gz_partition: NOT_APPLICABLE
commands:
  - command: targeted RED/GREEN regression and package tests
    exit_code: 0
  - command: installed GUI-tool probes
    exit_code: 0
  - command: ros2 launch so101_demo_py so101_mujoco_task_station.launch.py headless:=false sensor_rendering:=true include_teleop:=false session_id:=video-debug-exp002
    exit_code: -6
observed:
  - 89 focused tests passed with TMPDIR resolved to the registered evidence root scratch tree.
  - Installed inventory, tiler, and recorder help probes passed under Pydantic 1.10.14.
  - The task-station ros2_control_node aborted in GLFW before a MuJoCo window became recordable.
inferred:
  - Viewer and camera plugin initialized GLFW concurrently; _glfwGrabErrorHandlerX11 asserted because its X11 error handler was already held.
conclusion: The import fix is confirmed and kept, but this task-station configuration fails the video-sampling contract at the rendering lifecycle boundary.
evidence:
  - /data/work/so101-evidence/so101-video-debug-forward-test/20260916-a01/exp002/focused-pytest.xml
  - /data/work/so101-evidence/so101-video-debug-forward-test/20260916-a01/exp002/task-station.log
decision: KEEP
next_experiment: EXP-003
```

## EXP-003

```yaml
experiment_id: EXP-003
status: VALID
prior_experiment: EXP-002
hypothesis: The supported visible MuJoCo stack with sensor_rendering=false avoids the camera-plugin GLFW race and provides a valid video-only sampling target.
prediction: One owned MuJoCo window remains healthy, the recorder creates decodable media, and fresh frames visibly contain the expected SO-101 scene.
single_variable: Use so101_mujoco.launch.py with sensor_rendering=false instead of the task-station sensor-rendering configuration.
lifecycle: ISOLATED_STACK
preconditions:
  - Task worktree and so101_demo_py/so101_teleop install prefixes resolve to commit d4a0b1fe9f7e1fa8d86e0bb764c2d453fd66eddf.
  - No previous task-owned MuJoCo process or window remains.
  - GUI environment is loaded from ~/gui-env.zsh.
success_criteria:
  - One MuJoCo Viewer is bound to the exact runtime PID.
  - Camera preset readback and LAYOUT_OK succeed.
  - Recorder metadata is finalized and ffprobe decodes non-empty H.264 media.
  - The final frame and fresh desktop screenshot visibly show the robot, cup, table, and placement ring without error or loading overlays.
failure_criteria:
  - The runtime crashes, window ownership is ambiguous, media cannot be decoded, or visual content is invalid.
invalid_criteria:
  - Commit/overlay identity differs, evidence is stale, or another MuJoCo window contaminates capture.
provenance:
  source_commit: d4a0b1fe9f7e1fa8d86e0bb764c2d453fd66eddf
  install_overlay: /data/work/worktrees/so101-video-debug-forward-test-20260916/install
  runtime_executable: /data/work/ws_mujoco_ros2_control_fork/install/lib/mujoco_ros2_control/ros2_control_node
  ros_domain_id: 78
  gz_partition: NOT_APPLICABLE
commands:
  - command: ros2 launch so101_demo_py so101_mujoco.launch.py run_mode:=execute execute:=true headless:=false sensor_rendering:=false session_id:=video-debug-exp003
    exit_code: 0
  - command: camera_preset --backend mujoco table_corner_nw and tile_ai_station_guis.py --maximize mujoco
    exit_code: 0
  - command: simulator_window_recorder.py start/status/stop --simulator mujoco --owner-pid 3055665
    exit_code: 0
  - command: ffprobe, final-frame extraction, five-frame sampling, mosaic, and fresh desktop capture
    exit_code: 0
observed:
  - Inventory found exactly one MuJoCo window 0x3000007 owned by PID 3055665; arm, gripper, and joint-state controllers were active.
  - Camera preset readback matched table_corner_nw and layout returned LAYOUT_OK.
  - ready-probe.mkv is H.264, 4988x2742, 30 fps, 20.266 seconds, and 512432 bytes.
  - Five exact PTS samples at 0, 5, 10, 15, and 20 seconds decoded successfully.
  - Original final frame and fresh desktop capture visibly contain the SO-101 robot, cup, table, and red placement ring; the Viewer reports Running.
  - SimulationEvidence reports simulation_session_id video-debug-exp003, reset_epoch 0, paused false, and object_body plastic_cup.
  - The task tmux session closed cleanly; no owned MuJoCo/MoveIt runtime PID or MuJoCo window remained.
inferred:
  - sensor_rendering=false removes the unnecessary camera-plugin GLFW initializer while preserving the visible Viewer needed for video evidence.
conclusion: MuJoCo video sampling is validated for the video-only workflow. This result does not validate task_camera RGB-D or a pick-place execution.
evidence:
  - /data/work/so101-evidence/so101-video-debug-forward-test/20260916-a01/exp003/ready-probe.mkv
  - /data/work/so101-evidence/so101-video-debug-forward-test/20260916-a01/exp003/ready-recorder.json
  - /data/work/so101-evidence/so101-video-debug-forward-test/20260916-a01/exp003/ready-ffprobe.json
  - /data/work/so101-evidence/so101-video-debug-forward-test/20260916-a01/exp003/ready-last-frame.png
  - /data/work/so101-evidence/so101-video-debug-forward-test/20260916-a01/exp003/mosaic-low.jpg
  - /data/work/so101-evidence/so101-video-debug-forward-test/20260916-a01/exp003/captures/20260916T093214-6cbef55883e6/manifest.json
  - /data/work/so101-evidence/so101-video-debug-forward-test/20260916-a01/exp003/simulation-evidence.txt
  - /data/work/so101-evidence/so101-video-debug-forward-test/20260916-a01/exp003/process-inventory-before.json
  - /data/work/so101-evidence/so101-video-debug-forward-test/20260916-a01/exp003/process-inventory-after.json
decision: KEEP
next_experiment: NONE
```

## Checkpoint CP-001

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: Package-level eager server model imports are the first bad boundary for GUI-only tools.
working_tree_status: Clean published worktree before the new test and ledger files.
owned_processes: NONE
preserved_processes: Existing unrelated tmux sessions and processes on ai-station.
confirmed_conclusions:
  - EXP-001 is invalid and cannot support a video-sampling success claim.
disproven_routes:
  - Re-running the same published commit without removing the import failure adds no evidence.
open_risks:
  - MuJoCo launch or scene visibility may expose a later independent failure after the import boundary is fixed.
next_command: Run test_package_import_isolation.py and confirm the expected RED failure.
```

## Checkpoint CP-002

```yaml
checkpoint_id: CP-002
last_valid_experiment: EXP-003
current_hypothesis: NONE
working_tree_status: Release worktree contains only the reviewed skill/test/ledger follow-up before final commit.
owned_processes: NONE
preserved_processes: Existing codex and codex-task-so101-video-debug-forward-test tmux sessions were not modified.
confirmed_conclusions:
  - The Pydantic-v1 import boundary is fixed at d4a0b1fe9f7e1fa8d86e0bb764c2d453fd66eddf (EXP-002).
  - The video-only visible MuJoCo workflow passes with sensor_rendering=false (EXP-003).
disproven_routes:
  - Current task-station sensor rendering can be used as a video-only probe without hitting the GLFW concurrency failure (EXP-002).
open_risks:
  - The sensor_rendering=true task-station GLFW lifecycle remains a separate unvalidated path.
next_command: NONE
```
