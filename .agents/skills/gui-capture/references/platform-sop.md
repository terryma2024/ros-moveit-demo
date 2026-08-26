# Platform SOP

## macOS: exact window capture

1. Run `capture-gui.sh --local --list-windows`. The inventory comes from CoreGraphics and includes window ID, owner, title, and global bounds. Bounds may have negative `x` or `y` on displays left of or above the primary display; this is valid multi-monitor geometry.
2. Choose the exact visible, layer-zero window. If a title or owner query is ambiguous, rerun with `--window-id`; never select the largest match as a guess.
3. Capture with `--window-id`. The helper maps the CoreGraphics entry to one Accessibility window using process ID, title, position, and size; makes its process frontmost; performs `AXRaise`; then runs:

   ```bash
   screencapture -x -l WINDOW_ID OUTPUT.png
   ```

4. Confirm the manifest identifies that window and inspect the PNG. Because `-l` addresses the window itself, the result is independent of which monitor contains it and is not a crop of the combined desktop.

If Accessibility cannot resolve or raise exactly one window, stop. If Screen Recording permission is absent, `screencapture` must fail rather than substituting a desktop capture.

### macOS desktop debug capture

Window-level capture is preferred. Use desktop capture explicitly when debugging needs multiple windows, occlusion, focus state, menus, notifications, or other context outside one application window:

```bash
.agents/skills/gui-capture/scripts/capture-gui.sh --local --desktop \
  --output-root "$capture_evidence_dir"
```

The helper runs `screencapture -x OUTPUT.png`. Record `capture_mode=desktop` and inspect the fresh result; do not present a desktop capture as if it were an isolated target window or an all-monitor composite.

## GNOME Linux

The deterministic helper supports GNOME X11. It recovers the live graphical environment from `gnome-shell`, so an SSH shell reporting `XDG_SESSION_TYPE=tty` is not by itself evidence that no GUI exists.

For one window, list windows and select a query or exact X11 window ID. The helper activates and raises it through `_NET_ACTIVE_WINDOW`, captures its global bounds, then restores the previously active window.

For evidence involving several windows, use:

```bash
.agents/skills/gui-capture/scripts/capture-gui.sh --local --desktop \
  --output-root "$capture_evidence_dir"
```

GNOME Wayland blocks the X11 inventory/focus path. Use a currently loaded semantic driver or an approved screenshot-portal workflow. If neither exists, report capture unavailable; do not inject X11 keys or claim a whole-screen fallback is equivalent.

## Remote GNOME capture

From an orchestrator only:

```bash
GUI_CAPTURE_SSH_TARGET=ai-station \
  .agents/skills/gui-capture/scripts/capture-gui.sh --remote \
  --window 'Gazebo' --output-root "$capture_evidence_dir"
```

Remote mode stages only the colocated helper, runs it under `/tmp/gui-captures`, transfers the declared image, and stores the exact remote manifest beside the local copy.
