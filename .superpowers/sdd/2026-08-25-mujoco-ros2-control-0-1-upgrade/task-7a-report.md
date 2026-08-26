# Task 7A Report: phase-separated macOS runtime qualification

## Result

- Status: `BREAKER / NOT QUALIFIED`.
- The strict phase-separated camera probe, one exact dynamic execute run, and a placed-cup screenshot all succeeded together in retained Runtime Round 4.
- Round 4 nevertheless failed the clean-shutdown contract because shutdown produced two PAL invalid-context errors and required SIGTERM escalation.
- The final permitted Runtime Round 5 failed during fresh MuJoCo GUI startup: `ros2_control_node` received SIGSEGV in `_glfwSetWindowSizeCocoa` and exited `-11`. Camera, dynamic execution, and screenshot acceptance were therefore not run in Round 5.
- The five-round runtime ceiling is exhausted. No sixth runtime, weakened camera formula, alternate evidence, source workaround, push, tag, or evidence deletion was performed.

## Registered boundary

- Upgrade worktree: `/Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/mujoco-ros2-control-0-1-upgrade`.
- Registered evidence root: `/tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/runtime-task7a/`.
- Final parent candidate: `22a98d740219abda9459ea3c9cc67eb9fb07fc12`.
- Final fork candidate and gitlink: `f0f09abfe1498e1c6aa84a37a78cea87d2198b1d`.
- Fork branch: `codex/upstream-0.1.0-so101-r1`.
- Runtime RMW: `rmw_cyclonedds_cpp` for the complete stack, truth bridge, probe, and dynamic process.
- Runtime domain: `72`; `ROS_LOCALHOST_ONLY=1`.
- Final partition: `mrc010-macos-task7a-r5-72`.
- Simulation session id: `mrc010-macos-a`.
- Final tmux session: `mrc010-macos-task7a-r5`.
- The main checkout and user-owned processes were not modified or signalled.

The short parent hash previously reported as `22a98d74eb...` was erroneous. All final bundle, project, runtime, and report provenance uses the actual full hash `22a98d740219abda9459ea3c9cc67eb9fb07fc12`.

## Strict camera qualification implementation

The accepted probe uses one invocation against one stack and one candidate provenance:

1. Phase 1 creates a color-only subscriber, collects at least 30 unique real header timestamps, and checks the original end-to-end formula `(n-1)/((last-first)/1e9)` against the inclusive 8-12 Hz contract.
2. Phase 1 fully tears down its node, executor, and context. Executor shutdown returning false or any teardown exception fails the phase after best-effort cleanup.
3. Phase 2 creates camera-info, color, and depth subscribers. Each stream must provide at least three samples and the three streams must share an exact header timestamp.
4. The messages at that common timestamp must be 640x480, frame `task_camera_frame`, color `rgb8`, depth `32FC1`, and have non-empty color/depth payloads. Every value in the complete depth payload is scanned and must be finite and positive.
5. A single final `camera-topics.json` is written atomically only when both phases pass. Any failure exits nonzero and removes a stale output.

Behavior tests cover 7.99/8/12/12.01 Hz boundaries, dropped-frame reduction of the end-to-end average, fewer than three samples, no common timestamp, wrong resolution/frame/encoding/payload, non-finite or non-positive values anywhere in the full depth payload, phase timeout, executor shutdown false/exception, complete Phase 1 teardown before Phase 2 creation, stale-output removal, and atomic final JSON.

The probe implementation and FixRound1 parent commit are `3d2aaebd7bdef5d53c2ba18aec68b02532356008`. Its independent source review passed with no findings.

## PAL shutdown fixes and review history

- A first registry-clear design was rejected because clearing a global registry while the ControllerManager thread could still read or publish introduced a data-race/UAF risk. It was not retained in the final source.
- The accepted production design registers a FIFO pre-shutdown callback after ControllerManager construction. After controller/resource teardown, it stops and joins only the two known PAL publisher threads, does not erase the registry map, then allows context shutdown and worker joins. ControllerManager destruction performs the existing final registry clear only after those threads have joined.
- Production fix fork commit: `41a67efee2f2fe2394e327e5b4cae541806f7772`; parent pin commit: `276e989f57c6c6510cc74c5baf29310a0771b628`.
- Clean real-launch PID evidence proved controller shutdown before resource shutdown before `PUBLISHERS_STOPPED`, followed by clean node exit; both `publish_async_failures_` counters were zero and no PAL invalid-context error occurred. Independent FixRound3 review passed with zero findings.
- The launch gate initially rejected `publish_async_failures_ 1`, although that counter also represents normal nonblocking mutex contention. FixRound4 is test-only: value 1 alone is allowed, while generic `Exception in publisher thread` and `context cannot be slept` still fail. Marker/order, process exit assertions, and forced-signal rejection remain.
- Final test-only fork commit: `f0f09abfe1498e1c6aa84a37a78cea87d2198b1d`; final parent pin commit: `22a98d740219abda9459ea3c9cc67eb9fb07fc12`.
- The production node source blob is identical between `41a67ef` and `f0f09ab`: Git blob `e31f68d003550f28eabe88ae09f79658a1566e0d`, SHA-256 `f3ccef3ed3bddc88121977fb89160df1412a2fdd79c95088c0bfd3350002d8a3`.
- FixRound4 behavior RED was exactly two failures and one pass; GREEN was 3/3. Independent review passed with `C=0, I=0, M=0`.

## Final candidate build and regression gates

The final candidate was rebuilt source-backed from clean hashes into `fix-round-4/final-candidate-f0f09ab` with copy-install semantics:

- Six packages built successfully.
- CTest discovery was exactly 23 wrappers: plugin 7, core 9, launch 7, and zero in the other three packages.
- Plugin 7/7, core 9/9, and real launch 7/7 passed.
- Final XML aggregate: 23 files, 334 cases, 0 failures, 0 errors, 19 intentional skips.
- The first launch attempt without the complete macOS dylib activation failed to load `libmujoco.3.4.0.dylib`; it is retained as a harness diagnostic. No test process remained. The authoritative rerun used `eval "$(direnv export bash)"`, proved the selected install prefixes, and passed all 7 launch wrappers.
- A fresh source-less build used the fake prebuilt vendor, generated no `simulate.cc.o`, and passed 9/9 core wrappers / 182 cases with no failure, error, or skip.
- Source-backed object audit found `simulate.cc.o`, `macos_gui.mm.o`, and `glfw_corevideo.mm.o`.
- Production source contains exactly one `mj_step`, at `mujoco_simulation.cpp:2152`.
- Upstream `57fc6744844902d4532160b403fa95840c1d6f96` and local r11 `f19a8cc...` ancestry passed. Plugin base, camera interfaces, capability header, and installed message/service interfaces matched their expected bytes.
- Linkage and exported-symbol gates passed for node, main-thread UI dispatcher, core, plugin boundaries, camera lifecycle, and dispatcher API.
- Relocation copied with `cp -RL`, reduced symlinks from 12 to 0, and audited 18 Mach-O files. The only `LC_RPATH` was `@loader_path`; no forbidden absolute candidate path remained. `ctypes` loaded the relocated core and dispatcher with zero original-prefix images.
- A canonical `/private/tmp` fresh project copy-install built `so101_teleop`, `so101_mujoco_support`, and `so101_demo_py`. Strict camera behavior/contracts passed 34/34 and the complete project suite passed 293/293.
- Parent, fork, and gitlink were read back exactly and both worktrees were clean before final runtime.

The authoritative combined readback is `fix-round-4/final-all-gates-readback.txt`; independent static gate evidence is under `fix-round-4/static-gates/`.

## Bundle

The final fork branch was bundled to `fix-round-4/bundle/mujoco_ros2_control-0.1.0-so101-r1-fix-round-4-f0f09ab.bundle`.

- `git bundle verify` passed and reported complete history.
- A fresh `--no-checkout` clone resolved `refs/remotes/origin/codex/upstream-0.1.0-so101-r1` exactly to `f0f09abfe1498e1c6aa84a37a78cea87d2198b1d`.
- `git fsck --full` passed.
- Tag count was zero.
- No bundle or source was pushed.

## Runtime Round 4: functional success, shutdown failure

Round 4 used the approved CycloneDDS single-variable experiment and one fresh stack/probe/dynamic provenance.

The formal camera JSON at `run-4/camera-topics.json` passed:

- Phase 1: 30 samples, 30 unique real header timestamps, first `98407999999`, last `101361999999`, end-to-end frequency `9.81719702098849 Hz`.
- Phase 2: camera-info 4, color 4, depth 3; common timestamp `101975999999`.
- Common-timestamp contract: 640x480, `task_camera_frame`, `rgb8` color with 921600 bytes, `32FC1` depth with 1228800 bytes.
- Complete depth payload: 307200 values, all 307200 finite and positive.

The exact dynamic command exited zero. `run-4/dynamic-summary.json` records `DONE`, 19 transitions, and the full state trace through grasp verification, lift, transport, place, detach/release, placement validation, and retreat. Final validation recorded table contact, zero finger contacts, final XY error `0.002110053805709703 m`, and upright tilt `0.0045375342204319515 rad`.

The placed-cup screenshot is `run-4/final-placed-cup.png`, SHA-256 `0d1f875ba9b23c813e0ae90573d2f5eb44960a8d7878dad247476c44b87997ce`.

Round 4 is not qualified because normal owner-scoped shutdown reproduced exactly two PAL invalid-context messages and required SIGTERM escalation. Those errors cannot be ignored or replaced with the earlier functional evidence.

## Runtime Round 5: final breaker

Round 5 preflight proved:

- domain 72 had no nodes;
- tmux name `mrc010-macos-task7a-r5` was unused;
- RMW was exactly `rmw_cyclonedds_cpp`;
- final package prefixes resolved to the f0f09ab fork install and canonical 22a98d7 project install;
- `ros2_control_node` SHA-256 was `d58598aeff3d3dfd0bf751a2fd3e6d39dabe72c6e9e460015d591f92745cd400`.

One nested protected-shell provenance command demonstrated macOS SIP stripping `DYLD_LIBRARY_PATH`; it is explicitly marked invalid and superseded by direct venv-Python readback in `preflight-provenance-corrected.txt`.

The fresh GUI stack then failed before readiness:

- MuJoCo initialized from the exact canonical project scene and submitted its UI task to the process main thread.
- During the main-thread UI task, the stack trace reached `_glfwSetWindowSizeCocoa`, AppKit window frame notification, and `mujoco::PlatformUIAdapter::OnWindowResize`.
- `ros2_control_node` died with exit code `-11` at `run-5/launch.log:74`.
- Because that process was required, launch sent SIGINT to the remaining stack. `scene_setup` reported a secondary `rcl_shutdown already called` error during this cascade.
- MoveGroup emitted its ordered-shutdown marker but exceeded launch's five-second SIGINT grace period and was escalated to SIGTERM.
- There were no remaining Task7A ROS, bridge, probe, or dynamic processes after the failure. The tmux pane is retained idle for evidence only.

Round 5 did not produce `camera-topics.json`, `dynamic-summary.json`, or `final-placed-cup.png`; `run-5/acceptance-artifact-readback.txt` proves all three are absent. The launch wrapper's final zero is not a qualification pass because its required child crashed and the hard no-SIGTERM/no-context-thread-error contract failed.

No Round 6 is permitted. Task 7A remains `NOT QUALIFIED`.

## Evidence retention

- Retained: the complete registered evidence root, including Task7A RED/GREEN tests, rejected-patch evidence, all review packages, FixRounds 1-4, fresh source-backed/source-less builds, 23-wrapper results, relocation/ABI/linkage audits, bundle/readback, canonical project copy-install, Runtime Rounds 2-5, Round 4 camera/dynamic/screenshot, and Round 5 breaker logs.
- Archived: none.
- Deletion candidates, retained and not deleted: the rejected Task 7 patch; superseded source designs; failed build/configure attempts; the first noncanonical `/tmp` project copy-install; the missing-ROS-setup pytest collection failure; the first launch run lacking complete dylib activation; superseded static audit scripts/readbacks; and the protected-shell SIP provenance failure.
- Deleted evidence: none.
- Ledger/progress edits: none.
- Pushes/tags: none.
