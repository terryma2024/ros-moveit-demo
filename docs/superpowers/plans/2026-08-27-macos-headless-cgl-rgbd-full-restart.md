# macOS Headless CGL RGB-D Full-Restart Implementation Plan

> Execute on the current `main` branch. Preserve unrelated parent-workspace
> changes and do not publish remotely unless separately requested.

## 1. Freeze provenance and experiment contract

- Record the moveit-demo and MuJoCo fork commits, installed overlay, toolchain,
  evidence root, and four keyframes in the task ledger.
- Keep every experiment state explicit: `PLANNED`, `RUNNING`, then `VALID` or
  `INVALID`.

## 2. RED: encode missing behavior

- Extend the macOS camera lifecycle test with fake CGL entry points and assert
  that a rendering-enabled plugin with no injected GLFW context starts an owned
  CGL worker, renders, and tears down in worker-thread order.
- Extend MuJoCo simulation tests so a headless simulation can enable a rendering
  plugin without a Viewer context, while a rendering-disabled simulation keeps
  the plugin disabled.
- Extend launch tests so `sensor_rendering=true` renders
  `disable_rendering=false` independently of `headless=true`, and the perception
  launch defaults sensor rendering on.
- Run the focused tests before production changes and retain the expected
  failures under the registered evidence root.

## 3. GREEN: implement CGL and policy propagation

- Add worker-owned CGL context lifecycle to `CameraPlugin` on Apple platforms.
- Link the production camera plugin to `OpenGL.framework`; keep lifecycle tests
  hermetic through fake CGL functions.
- Parse `disable_rendering` in `MujocoSystemInterface`, pass the policy through
  `MujocoSimulation`, and decouple plugin enablement from Viewer availability.
- Add launch-level `sensor_rendering` resolution with generic `auto` behavior
  and perception default `true`.
- Make the smallest targeted changes needed for a four-keyframe full-restart
  runner if the existing launch/runner cannot enforce the frozen contract.

## 4. Package and installed-runtime verification

- Run focused GREEN tests, full affected package tests, and inspect CTest/JUnit
  counts so zero discovered tests cannot be reported as a pass.
- Build the affected packages in the exact macOS ROS environment, source the
  installed overlay, and record executable/library provenance.
- Run one short headless RGB-D probe and verify actual RGB/depth/camera-info
  samples, encodings, finite positive depth, timestamps, and clean shutdown.

## 5. Four-point full-restart qualification

- Commit the candidate so every run uses one immutable source identity.
- For each frozen keyframe, allocate a fresh ROS domain, session ID, log path,
  and perception evidence path.
- Start the installed perception pick-place launch with `headless=true`, wait
  for terminal success/failure, inspect payload and manipulation evidence, then
  verify the entire stack has stopped before the next run.
- Produce a four-row acceptance matrix and retain every run's evidence.

## 6. Handoff

- Run `git diff --check`, final tests, and inspect both repositories' status.
- Update the ledger with exact commands, commit IDs, outcomes, retained runs,
  archived runs, and deletion candidates.
- Report functional validation separately from any local commit/publication
  status.
