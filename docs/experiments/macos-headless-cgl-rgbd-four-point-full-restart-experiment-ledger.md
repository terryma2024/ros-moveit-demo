# macOS Headless CGL RGB-D Four-Point Full-Restart Experiment Ledger

## Task identity

- Date: 2026-08-27
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
| E05 | PLANNED | Installed-overlay headless RGB-D probe | `runtime-probe/` |
| E06 | PLANNED | FULL_RESTART: `task_start` | `full-restart/01-task_start/` |
| E07 | PLANNED | FULL_RESTART: `cup_test_forward_5cm` | `full-restart/02-cup_test_forward_5cm/` |
| E08 | PLANNED | FULL_RESTART: `cup_test_left_5cm` | `full-restart/03-cup_test_left_5cm/` |
| E09 | PLANNED | FULL_RESTART: `cup_test_right_5cm` | `full-restart/04-cup_test_right_5cm/` |

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
- Environment corrections retained as diagnostic evidence: a sandboxed real
  CGL attempt could not connect to CoreGraphics, an unsourced `colcon test`
  loaded stale dylibs, and one Python run attempted to write `~/.ros/log`.
  Valid GREEN runs use the graphical session, the explicit candidate overlay,
  and registered `ROS_HOME`/`ROS_LOG_DIR` paths.

## Runtime provenance template

Complete before E05:

- Candidate moveit-demo commit:
- Candidate MuJoCo fork commit: `71bc9346cf93d6227a6678fcacf63f3e18acfcba`
- Install prefix: `/tmp/so101-debug-macos-headless-cgl-four-point-20260827/candidate/install`
- `ros2 pkg prefix mujoco_ros2_control`:
- `ros2 pkg prefix mujoco_ros2_control_plugins`:
- `ros2 pkg prefix so101_demo_py`:
- Loaded camera plugin library:
- Python executable / ROS distribution:
- `ROS_HOME` / `ROS_LOG_DIR`:

## Four-point result template

| ID | Keyframe | ROS domain | Session | RGB | Depth | Camera info | `/cup_pose` | Pick/place | Clean exit | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E06 | `task_start` | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | PLANNED |
| E07 | `cup_test_forward_5cm` | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | PLANNED |
| E08 | `cup_test_left_5cm` | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | PLANNED |
| E09 | `cup_test_right_5cm` | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | PLANNED |

## Evidence disposition

- Retained runs: none yet
- Archived runs: none
- Deletion candidates: none; do not delete without explicit user authorization
