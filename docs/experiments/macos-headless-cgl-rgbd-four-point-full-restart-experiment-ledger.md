# macOS Headless CGL RGB-D Four-Point Full-Restart Experiment Ledger

## Task identity

- Date: 2026-08-27 through 2026-08-28
- Branch: `main`
- Initial moveit-demo commit: `4691d233a2a5095bc0ad93c092d20995b5e218a5`
- Initial `third_party/mujoco_ros2_control` commit: `5e9d67ce9fde39d35bf94cc498721abf203a0ddd`
- Registered evidence root: `/tmp/so101-debug-macos-headless-cgl-four-point-20260827/`
- Lifecycle contract: four independent `FULL_RESTART` runs
- Required launch mode: `headless=true`, `sensor_rendering=true`
- Frozen keyframes: `task_start`, `cup_test_forward_5cm`,
  `cup_test_left_5cm`, `cup_test_right_5cm`

## Experiment matrix

| ID | State | Purpose | Evidence |
| --- | --- | --- | --- |
| E00 | VALID | Inspect current source, branch, submodule, and rendering lifecycle before edits | This ledger and design record |
| E01 | VALID | RED macOS CGL worker lifecycle test | `red/camera-cgl.txt` |
| E02 | VALID | RED simulation rendering-policy test | `red/simulation-render-policy.txt` |
| E03 | VALID | RED launch sensor-rendering contract test | `red/launch-sensor-rendering.txt` |
| E04 | VALID | GREEN focused, package, and clean candidate-install tests | `green/`, `candidate/` |
| E05 | VALID | Installed-overlay headless RGB-D probe | `runtime-probe/` |
| E06 | VALID | FULL_RESTART: `task_start` | `full-restart/01-task_start/` |
| E07 | VALID | FULL_RESTART: `cup_test_forward_5cm` | `full-restart/02-cup_test_forward_5cm/` |
| E08 | VALID | FULL_RESTART: `cup_test_left_5cm` | `full-restart/03-cup_test_left_5cm/` |
| E09 | VALID | FULL_RESTART: `cup_test_right_5cm` | `full-restart/04-cup_test_right_5cm/` |

## E00 - baseline inspection

- State transition: `PLANNED -> RUNNING -> VALID`
- Source checkout: `/Users/matianyi/Projects/robot_demo_001/moveit-demo`
- Parent branch: `main`
- Parent status at inspection: clean, tracking `origin/main`
- MuJoCo fork state: detached at the recorded gitlink; local `main` contains
  the same commit; working tree clean
- Diagnosis: macOS currently enables camera rendering only when
  `macos_camera_window_` exists. Headless mode deliberately skips that
  main-thread GLFW window, so the plugin registers topics but is disabled by
  `MujocoSimulation::prepare_rendering_plugin` and cannot publish samples.
- Decision: implement worker-owned CGL for the null-window/rendering-enabled
  case and propagate `disable_rendering` independently of `headless`.

## E01-E03 - RED evidence

- State transitions: `PLANNED -> RUNNING -> VALID`
- E01: the new owned-CGL lifecycle test compiled, then failed because the
  current plugin rejected a null macOS GLFW context with
  `CameraPlugin did not receive a main-thread macOS GLFW context`.
- E02: the new simulation policy test failed to compile because
  `MujocoSimulation::initialize` accepted five arguments and could not receive
  the independent `disable_rendering` flag.
- E03: both focused Python tests failed: the renderer rejected the
  `sensor_rendering` keyword and the perception launch had no declaration with
  that name.
- Precondition note: the first direct E01 binary invocation lacked the sourced
  dylib environment and was invalid. It was rerun with
  `eval "$(direnv export zsh)"` plus `source install/setup.zsh`; only the rerun
  is the valid RED result in `red/camera-cgl.txt`.

## E04 - GREEN and candidate install

- State transition: `PLANNED -> RUNNING -> VALID`
- MuJoCo fork candidate commit:
  `71bc9346cf93d6227a6678fcacf63f3e18acfcba`.
- Focused launch contract: 2 passed; complete launch-composition file: 14
  passed.
- Camera lifecycle direct suite: 6 passed; simulation direct suite: 45
  passed.
- Full `mujoco_ros2_control_plugins` CTest from the graphical macOS session:
  7/7 passed, including a real no-window CGL context test.
- Clean candidate install prefix:
  `/tmp/so101-debug-macos-headless-cgl-four-point-20260827/candidate/install`.
- Candidate plugin suite: 7/7 passed; candidate core suite: 10/10 passed,
  including relocation smoke.
- Candidate `so101_demo_py` suite: 553 passed after installing
  `so101_mujoco_support` into the same candidate prefix.
- Final post-runtime repeat: plugin CTest 7/7, core CTest 10/10, and
  `so101_demo_py` pytest 553/553 passed.
- Environment corrections retained as diagnostic evidence: a sandboxed real
  CGL attempt could not connect to CoreGraphics, an unsourced `colcon test`
  loaded stale dylibs, and one Python run attempted to write `~/.ros/log`.
  Valid GREEN runs use the graphical session, the explicit candidate overlay,
  and registered `ROS_HOME`/`ROS_LOG_DIR` paths.

## Runtime provenance

- Candidate moveit-demo commit: `e5b9b9131fb70bf38f1da1c54c4826e6e99f3780`
- Candidate MuJoCo fork commit: `71bc9346cf93d6227a6678fcacf63f3e18acfcba`
- Install prefix: `/tmp/so101-debug-macos-headless-cgl-four-point-20260827/candidate/install`
- `ros2 pkg prefix mujoco_ros2_control`: candidate install prefix
- `ros2 pkg prefix mujoco_ros2_control_plugins`: candidate install prefix
- `ros2 pkg prefix so101_mujoco_support`: candidate install prefix
- `ros2 pkg prefix so101_demo_py`: candidate install prefix
- Loaded camera plugin library:
  `candidate/install/lib/libmujoco_ros2_control_plugins_impl.dylib`, SHA-256
  `02c0096ce18861480d7c718167c8fd40a98c77b276e5c8be4120a18c96605388`
- Python executable / ROS distribution:
  `/Users/matianyi/ros2_jazzy/.venv/bin/python3` / Jazzy
- `ROS_HOME` / `ROS_LOG_DIR`: unique child directories under each registered
  run root

## E05 - installed runtime and no-window probe

- State transition: `PLANNED -> RUNNING -> VALID`.
- All four changed runtime packages resolved to the clean candidate prefix;
  the installed manifest reported source commit `e5b9b913...` and the
  installed MuJoCo executable SHA-256
  `26a5fed8e3bd7ea1d52f590b8eca568ab0d5d378f9b5d569084507350fe6e332`.
- The loaded plugin links both GLFW for the unchanged interactive path and
  `/System/Library/Frameworks/OpenGL.framework` for the new CGL path.
- A real `headless=true`, `sensor_rendering=true` process logged
  `CGL: Successfully initialized headless OpenGL context`, allocated a
  640x480 offscreen buffer, and started the camera loop at 10 Hz.
- The standalone capture advanced past synchronized RGB-D acquisition and
  failed only at the intentionally absent static TF in the generic stack.
  E06 then validated the same installed renderer with the production static
  TF chain and a complete perception artifact.

## E06-E09 - four independent full restarts

- Each run started only after a read-only process check proved the prior
  MuJoCo, MoveIt, TF, perception, and dynamic workflow processes were gone.
- Every run used a unique `ROS_DOMAIN_ID`, `GZ_PARTITION`, session ID,
  `ROS_HOME`, `ROS_LOG_DIR`, and evidence directory.
- Each runtime logged exactly one successful CGL initialization, processed a
  synchronized 640x480 RGB/depth/camera-info set into positive point counts,
  published `/cup_pose`, completed the 19-transition dynamic pick/place state
  machine at `DONE`, exited zero, and logged 11 clean process exits.
- E06's runtime and all 11 child processes completed cleanly, but its temporary
  outer zsh helper then used the reserved variable name `status` while trying
  to record `$?`; the helper itself therefore returned 1 after the validated
  runtime had ended. The helper was corrected to `run_status` before E07-E09,
  whose outer exit statuses were recorded directly as zero.
- A final process check after E09 found no remaining task runtime processes.

## Four-point results

| ID | Keyframe | ROS domain | Session | RGB | Depth | Camera info | `/cup_pose` | Pick/place | Clean exit | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E06 | `task_start` | 181 | `macos-cgl-e06-task-start-20260828` | OK 640x480 | OK, 98,078 points | OK | `(0.01950, -0.28040, 0.16500)` | DONE, 19 transitions | Runtime clean; helper post-hook 1 | VALID |
| E07 | `cup_test_forward_5cm` | 182 | `macos-cgl-e07-forward-20260828` | OK 640x480 | OK, 98,078 points | OK | `(0.01962, -0.33046, 0.16500)` | DONE, 19 transitions | 0; 11 clean exits | VALID |
| E08 | `cup_test_left_5cm` | 183 | `macos-cgl-e08-left-20260828` | OK 640x480 | OK, 98,135 points | OK | `(-0.03036, -0.28059, 0.16500)` | DONE, 19 transitions | 0; 11 clean exits | VALID |
| E09 | `cup_test_right_5cm` | 184 | `macos-cgl-e09-right-20260828` | OK 640x480 | OK, 98,078 points | OK | `(0.06963, -0.28051, 0.16500)` | DONE, 19 transitions | 0; 11 clean exits | VALID |

## Evidence disposition

- Retained runs: E06-E09 and all supporting RED, GREEN, candidate-install,
  provenance, and runtime-probe evidence under the registered root
- Archived runs: none
- Deletion candidates: invalid-precondition probe artifacts (`capture/`, the
  first `provenance.txt`, and early probe logs), the unsourced
  `green/colcon-test.txt`, and stale-workspace relocation diagnostics. They
  remain retained; do not delete without explicit user authorization.
