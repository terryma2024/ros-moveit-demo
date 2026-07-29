# SO-101 Gazebo Camera and Work-Area Maximize Design

## Approved scope

Set MinimalScene's default `camera_pose` to exactly `0.4281 0.2175 0.4608 0 0.4 -2.3`. The GUI remains `fullscreen=0`. No horizontal-FOV field is added: the existing/default value is `1.570796`, and this change has no local Gazebo evidence for a supported replacement syntax.

Add `--maximize gazebo|rviz` to `tile_ai_station_guis.py`. It finds the requested X11 client using the existing EWMH backend, waits using the existing timeout behavior, and sends only `_NET_MOVERESIZE_WINDOW` for that client with the current `_NET_WORKAREA` rectangle. It must not send `_NET_WM_STATE_FULLSCREEN`, so GNOME's top bar remains outside the target work area.

The no-argument command retains two-pane behavior: it clears maximize for both discovered clients and resizes RViz left/Gazebo right. Therefore it restores either app from the new work-area maximize layout.

## Verification

Python contract tests cover the exact camera pose, fullscreen/FOV constraints, CLI parsing, selected-only work-area resize, idempotence, missing selected-window timeout, and return to the two-pane geometry. A fresh tmux-held GUI run verifies the installed world, Gazebo maximize, restore, and final Gazebo maximize using a new capture.
