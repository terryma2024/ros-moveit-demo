# SO-101 Actual Clock Interleaving Probe Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans. The existing user override authorizes inline execution; an independent Astra reviewer checks the design and results.

**Goal:** Test whether a real ROS clock advance between READ and UPDATE can produce the observed native 4 ms / 0 ms pair.

**Architecture:** Add one optional scheduling wait in the traced control loop. Physics and clock delivery continue through their existing code. The probe records actual clock samples and never replaces controller timestamps or periods.

**Tech Stack:** C++17, rclcpp, existing ClockTrace DSO, gtest, colcon.

**Spec:** The registered evidence root contains `clock-diagnostic-yrcfff3b/actual-boundary-probe-proposal001.json` and independent `review/probe-design001/astra-review.json`.

## Global Constraints

- Keep the injection disabled unless `SO101_DIAGNOSTIC_CLOCK_ADVANCE_LOOP` is explicitly set to a decimal loop ID in `[1,50000]`; require tracing, simulated time and 500 Hz.
- Inject once at loop 5000 after the original READ and before the original UPDATE argument is sampled.
- Keep physics timestep, model, publication, QoS, READ/UPDATE/WRITE arguments, measured periods, sleep anchor and all native predicates unchanged.
- Use a 250 ms steady deadline. Check context, reset epoch, backwards clock and deadline before accepting success.
- Retain every run. Injected runs cannot qualify nominal stability. Do not repeat a failed or inconclusive experiment until it passes.
- Keep evidence under the existing registered root. Use fresh NVMe scratch with exact Python tempfile proofs for every test command.
- Preserve existing worktree changes and commits. No commit, push or global configuration changes are part of this plan.

## Review Focus

- A clock already past the target must be reported separately from a wait that observes a new clock advance.
- Shutdown or reset concurrent with reaching the target must fail the probe.
- Missing clock delivery must stop the wait within its wall deadline and cause a nonzero process exit.
- The injected sample must follow a clean active prefix from all three native controllers before it supports a shared-period claim.
- Every trace reader must recognize kind 17 and retain its raw before, after, target, epoch and monotonic bracket.

## Task 1: Bounded clock wait and node integration

**Files:** Create `include/mujoco_ros2_control/clock_advance_probe.hpp` and `tests/test_clock_advance_probe.cpp` in the MuJoCo package. Modify its node source, trace enum and `tests/CMakeLists.txt`.

**Interfaces:** `ClockAdvanceProbe::parse(const char *, bool)` constructs the disabled or configured probe; `validate(bool, uint32_t)` checks simulated time and rate. `run(uint64_t, const rclcpp::Time &, std::chrono::nanoseconds, uint64_t, rclcpp::Clock &, const rclcpp::Context &)` returns a result with invoked, flags, before/after/target timestamps and monotonic start/end. The control thread owns the probe and its once-only state.

- [x] Write gtests for absent/invalid configuration, incompatible runtime, selected loop, once-only behavior, real rclcpp clock advancement, already-reached target, cancelled context, reset, backwards clock and missing delivery timeout. Use actual rclcpp clock objects, not a period calculator.
- [x] Run the tests against a disabled implementation scaffold and record behavioral RED; compilation/setup errors do not count as RED.
- [x] Implement bounded polling of the actual ROS clock with thread yield, catching clock read failures. Store loop-start epoch before READ. Do not allocate or log inside the probe.
- [x] Add kind 17: `sim_ns=after`, `auxiliary=target`, `actor=before`. Flags: 1 advanced, 2 timeout, 4 cancelled, 8 clock/reset discontinuity, 16 clock error, 32 already reached. Preserve existing record fields and kinds.
- [x] On failure, set a shared diagnostic-failure flag and exit the control thread, publishing quiescence through RAII on every exit. A probe-only nonRT relay thread waits for failure and quiescence, then shuts down the original ROS context while CM and registries are alive. Context shutdown wakes executor spin persistently. Join the relay before destroying CM; preserve the original shutdown callbacks, macOS UI cleanup and trace finish; return nonzero. Test actual executor spin both before and after shutdown, and verify callbacks run after quiescence and before owner destruction.
- [x] Verify all directed gtests GREEN, then independently review the immutable source snapshot before a real run.

## Task 2: Copied install and one bounded diagnostic

**Files:** Create a new task-owned probe source/build/install and test wrappers inside `clock-diagnostic-yrcfff3b/probe001/`. Update task-owned analysis and launcher copies; preserve previous installs and run outputs.

- [x] Build a complete dependency-closed optimized copied install. Record source hashes, install inventory, exact executables and dependency provenance.
- [x] Run the complete MuJoCo package gate, test-result readback and complete Python test module with eight workers. Preserve all baseline failures and distinguish them from new regressions.
- [x] Bind the probe configuration into immutable manifest/input hashes. Add kind-17 readback and enforce exactly one marked invocation plus a clean active three-controller prefix for a sufficient-mechanism claim.
- [x] Freeze and independently review the launcher/runtime package. Run one 120 s FULL_RESTART holding capture with loop 5000 injection and the original teardown budgets.
- [x] Check raw stream finality/counts, real clock/physics/native correspondence, original sealed protocol/report, Stop/close and independent OS/graph absence. A wrapper failure invalidates the whole attempt.
- [x] Classify exact shared 4 ms / 0 ms as a sufficient schedule mechanism, partial reproduction as inconclusive, or no reproduction as a revised hypothesis. None proves historical cause or nominal qualification.

The valid run is `exit-probe001/checkpoints/holding001` under the registered clock diagnostic root. Its guardian returned 0, the original sealed startup/Stop/close and process-map checks passed, and all owned processes retired normally. The analyzer classified the observed loop-5000 pair as `CONFIRMED_SUFFICIENT_ACTUAL_SCHEDULE`. Earlier invalid attempts remain invalid. This completes the diagnostic plan, not the stability repair.

## Subsequent Work

Select the smallest repair after this experiment. The proposed global step coordinator still requires a complete lifecycle design and separate review. Stability acceptance remains three nominal 120 s checks, the frozen 20-repetition scope and fresh 40 cases / 48 attempts with perception and visual evidence.
