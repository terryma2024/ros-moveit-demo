# Sim-synchronous camera rendering

Date: 2026-10-08

Trigger: the pilot bag `031b82c6` (attempt `task_start-lease-1`, `$R/experiments/nonhead-first-episode-031b82c6-6382-40a4-aae2-8f5721f4b248/run/workers/worker-01/attempts/task_start/task_start-lease-1/sealed/raw/bag`) has head and wrist frames at a nominal 100 ms cadence with these deviations: 12 of 1129 intervals are not 100 ms (102, 98 and 99 ms steps from 7.306 s on, one 200 ms interval ending at 21.206 s where a frame is missing). Head and wrist stamps are identical. Every stamp is also truncated by one nanosecond (`4.703999999`). The ACT capture mints one row per grid instant from a new frame whose stamp is at or before the instant (`continuous_capture._mint_rows`), so one +2 ms frame or one missing frame ends the episode with `NO_NEW_ACQUISITION`. The offline processor stopped at 7.3 s for exactly that.

Root cause (read from `third_party/mujoco_ros2_control/mujoco_ros2_control_plugins/src/camera_plugin.cpp`):

- `CameraPlugin::update()` runs on the controller-manager thread. It fired when `node->get_clock()->now() - last_publish_time_ >= 0.1`. That node clock follows `/clock`, which the simulation publishes with `tryPublish` (a realtime publisher that drops when busy). It lags the physics by several steps, so the frame instant was decided from a delayed clock, `last_publish_time_` was set to that delayed `now` (drift) and the snapshot taken in `update()` was the control thread's, which can be a step late.
- The stamp was `Duration::from_seconds(time)` (truncating): 4.804 s became `4.803999999`.
- The snapshot in `mj_camera_data_` was overwritten if a new one was due before the renderer had read the previous one (the renderer drops the data mutex between taking `new_data_` and rendering), so a frame could be coalesced away.

Options considered:

- A. Build the capture grid from the actual frame stamps (tolerate jitter). Changes the 10 Hz grid contract and cannot recover a missing frame.
- B. Make rendering sim-synchronous in the plugin: schedule on the snapshot's simulation time, snapshot on the physics thread at the exact step, stamp in whole rounded nanoseconds, and make the physics step wait while the renderer is busy.

Recommended option taken under CP-3394 and the CP-3439 decision: B. The contract (a 10 Hz grid of camera stamps, causal and unique per row) is unchanged.

Change (`mujoco_ros2_control_plugins`, vendored as the `third_party/mujoco_ros2_control` submodule pinned at `54463fc` with this tree's uncommitted changes; the frozen source copy and `submodule.patch` of each freeze carry it):

- `CameraPlugin` also implements `MuJoCoROS2ControlSimulationObserver` (the existing physics-thread hook the evidence plugin uses). `on_physics_step()` calls the same scheduler as `update()`; whichever sees an instant first takes it and moves the schedule on. In production the physics thread always sees the instant first, so the snapshot is of exactly the step that reaches `k * period`.
- Schedule in nanoseconds on `mjData::time`: due at the next integer multiple of the publish period, advanced by the grid (not by "now + period"); re-armed only when the clock moves more than a period behind the last frame (a reset).
- Stamp = `llround(time * 1e9)`.
- `render_busy_` / `consumed_cv_`: a snapshot is never overwritten before it was rendered. The scheduler waits (60 s bound, then logs an error), so the physics step waits when the renderer is busy. Only simulation speed is affected; the Teacher works in simulation time. The controller manager's overrun handling is not reached because its loop is paced by sim time (`use_sim_time`), not wall time.

Contract impact: none on the data contract. The producer now meets the exact-grid, no-drop behaviour the contract assumed. A bag with a frame off the grid or missing is named by the offline scan (`OFFLINE_CAMERA_GRID`) before it is processed.

Tests:

- C++, `test_camera_plugin.cpp`: `StreamingFramesLandOnExactSimMultiplesAndNoneIsDropped` (1000 physics steps driven far faster than the renderer, irregular wall pacing, a controller-thread snapshot one step behind: exactly 21 frames at exactly `k * 100 ms`) and `AFrameAfterASimulationResetIsStillOnTheGrid`. RED against the previous plugin source: 1 frame instead of 21 and a missing reset frame (`writer-artifacts/p2-camera-red.out`). GREEN: 11 tests of the suite, including the 9 existing ones. The GL tests need an EGL-capable environment and the build tree's library first on `LD_LIBRARY_PATH` (`writer-artifacts/p2-cpp.zsh`, scratch build bases).
- Python: the offline scan test for a missing/off-grid camera frame (`test_p2_offline_processor.py`).

Rollback: restore `camera_plugin.cpp/.hpp` and `test_camera_plugin.cpp` from `writer-artifacts/p2-camera-base.tar.gz` (sha256 beside it). The data contract is untouched, so nothing else depends on the change.

Ledger CP: CP-3439.
