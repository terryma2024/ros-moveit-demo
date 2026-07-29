# SO-101 Gazebo Camera and Work-Area Maximize Implementation Plan

> **For agentic workers:** Execute with TDD; do not commit this dirty workspace.

**Goal:** Load the requested default Gazebo camera and maximize one GUI client to EWMH work area without fullscreen.

**Architecture:** Reuse `tile_windows` discovery and EWMH geometry readback. Add a narrow selected-window function and route `--maximize` to it; retain the existing no-argument tile route.

**Constraints:** Camera pose is exact; `fullscreen=0`; no FOV field; no `_NET_WM_STATE_FULLSCREEN`; only the selected window changes in maximize mode; use tmux plus `~/gui-env.zsh` for visual acceptance.

### Task 1: World contract

- [ ] Add a failing world test for exact `camera_pose`, `fullscreen=0`, and no horizontal-FOV element.
- [ ] Run it RED against the currently dirty world.
- [ ] Change only the camera pose text.
- [ ] Re-run it GREEN.

### Task 2: EWMH maximize contract

- [ ] Add failing unit tests for parser/CLI, selected-only exact work-area resize, repeatability, timeout, and default tile restoration.
- [ ] Run the focused tests RED.
- [ ] Add the minimal selected-window layout path and CLI route, without fullscreen state messages.
- [ ] Re-run focused tests GREEN.

### Task 3: Installed-artifact and GUI acceptance

- [ ] Build `so101_gazebo_demo`, source `install/setup.zsh`, and run relevant package tests.
- [ ] Restart only the tracked `so101-moveit` experiment for fresh world loading in tmux with `~/gui-env.zsh`.
- [ ] Capture a fresh Gazebo-maximized view, capture restored tiling, then leave Gazebo maximized and inspect the final capture.
