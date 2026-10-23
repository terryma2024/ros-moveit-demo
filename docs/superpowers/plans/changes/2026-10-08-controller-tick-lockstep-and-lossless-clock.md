# Controller manager lock-step with the physics loop, lossless `/clock`, no catch-up burst after a render wait

Date: 2026-10-08

Trigger: pilot bag 8d9ed9d3 (CP-3444). `/clock` and the three `controller_state` topics lack the same 2 ms ticks (586 ticks in all four topics, 805 in the union, none where only `/clock` is missing), always 4 to 12 ms after a camera instant; the physics-step chunks have no hole. Four arm ticks at +2 ms touch a label instant (45.502, 57.402, 60.402, 111.002 s). Six controller frames are published twice with one stamp (57.404, 58.106, 65.706, 77.210 s), which latches `CONTROLLER_REFERENCE_ORDER_INVALID` in the reference observer. Bag 031b, recorded before the camera plugin waited for its render, had 4 arm gaps in the whole run.

## 1. Cause (code reading and a test)

- The camera plugin is a simulation observer: `step_authoritative_physics()` calls `observer_dispatcher_.on_physics_step()` (the render wait) inside the physics step, with the simulation mutex held.
- `physics_loop()` then finds the simulation behind wall time (`kSyncMisalign` is 0.1 s) and takes the catch-up branch: it steps back to back until it has caught up, each step calling `publish_clock()`.
- `publish_clock()` used `RealtimePublisher::try_publish`, which refuses while the publisher thread still sends the previous message: the tick is dropped.
- The controller manager loop (`mujoco_ros2_control_node.cpp`) sleeps on `/clock` (`sleep_until(current_time + period)` on the ROS clock). A dropped tick makes it wake one tick late (a skipped update, a missing `controller_state` stamp); two ticks arriving together make it read the same node clock twice (a repeated stamp: the controllers stamp their state with the node clock).
- RED test (before the change): `TickLockstepTest.EveryPhysicsStepPublishesItsClockTickAcrossARenderWait` fails at tick 81 (`tick 81 at 166000000 ns`), the first tick after a 40 ms wait in step 80.

## 2. Changes (`third_party/mujoco_ros2_control/mujoco_ros2_control`)

- `ControlTickGate` (`control_tick_gate.hpp/.cpp`, in the library): the physics loop publishes a tick after every authoritative step; once a consumer has attached (by waiting for a tick) the physics loop does not take the next step before the consumer acknowledged the tick it is due for. The consumer is due for the tick at or after `last tick + its period`. An unacknowledged tick disarms the gate after 250 ms (the consumer is gone) and the physics loop runs free until it attaches again.
- `ros2_control_node`: on simulation time the loop is `run_control_tick_loop`: one `read/update/write` per due tick, in order, period = the measured step (nominal after a reset). Each update first waits (at most 20 ms) until the node clock, which the controllers use for their stamps, shows the tick's time. The wall-clock branch and the startup waits are unchanged. The executable now links `mujoco_ros2_control`.
- `physics_loop()`: waits for the acknowledgement before taking the lock (services and the viewer keep running); with a consumer attached it takes one step per iteration (no catch-up burst) and a step slower than 5 ms re-anchors the real-time pacing (`speed_changed`): the simulation runs slower until it is back in sync. Without a consumer nothing changes (the existing catch-up tests are untouched).
- `publish_clock()`: retries `try_publish` for up to 20 ms (the physics thread is not a realtime thread) and reports a drop.
- Simulation speed: ACT runs at `sim_speed_factor` 1, so the lock-step costs no throughput. At higher speed factors the simulation is paced by the controller update (about 0.1 to 0.3 ms per tick).

## 3. Tests

`tests/test_control_tick_lockstep.cpp`: the clock test above (RED, then GREEN); the controller loop across a render wait (250 updates, each stamp exactly 2 ms after the previous, equal to the published clock ticks, no skipped tick, no timeout); the gate rules (not armed, due and not due, timeout and re-attach). 15 repeated runs green. Existing C++ tests: `mujoco_ros2_control` 12 of 12, `mujoco_ros2_control_plugins` 6 of 6 (camera plugin included).

Not covered by a unit test: the real controller manager with the real joint trajectory controllers. The first live bag is that test; `p2c_missing.py` (missing and duplicate stamps per topic) is the check to run on it before the processor.

Contract impact: none for the data contract. Control timing: one update per physics step is now guaranteed instead of usual. The Teacher's motion definitions are unchanged.

Rollback: `writer-artifacts/p2c-tick-base.tar.gz` (the whole `mujoco_ros2_control` and `mujoco_ros2_control_plugins` source trees as they were), sha256 beside it.

Ledger CP: CP-3445.
