---
name: gui-capture
description: Use when capturing or inspecting a GUI window or desktop on macOS or GNOME Linux, including multi-monitor desktops, remote Linux sessions, debugging, or fresh visual evidence.
---

# GUI Capture

Capture fresh visual evidence from the intended window, with an explicit platform and window identity. Prefer a healthy, currently loaded semantic GUI driver when the task also requires mouse, keyboard, or UI-state inspection.

**REQUIRED BACKGROUND:** For SO-101 work, use `so101-dev` and obey its provenance, process-ownership, experiment-ledger, and fresh-evidence gates.

## Route the request

1. Prove whether execution is local or remote from live hostname and workspace evidence. A process already on the target host must not SSH to itself.
2. Inspect current tools for a loaded semantic GUI capability. When healthy, use `snapshot -> action -> fresh snapshot`; resolve elements again after every snapshot.
3. For deterministic capture, read the matching platform section in [references/platform-sop.md](references/platform-sop.md). On macOS, if capture is invoked through SSH, TCC denies the capture, or no permission prompt appears, also read [references/macos-tcc-troubleshooting.md](references/macos-tcc-troubleshooting.md).
4. Prefer window-level capture. List visible windows first, then select one unambiguous title/owner match or use its exact window ID. Never guess among duplicates.
5. Use explicit desktop capture when debugging requires cross-window relationships, occlusion, focus, menus, notifications, or other desktop context. Do not silently widen a window request into a desktop capture.
6. Capture into a task-owned directory outside the source tree, read [references/capture-contract.md](references/capture-contract.md), then visually inspect the fresh image at original resolution.

The script captures pixels only. A screenshot does not prove semantic control, application ownership, or functional success.

## Commands

```bash
.agents/skills/gui-capture/scripts/capture-gui.sh --local --list-windows
.agents/skills/gui-capture/scripts/capture-gui.sh --local \
  --window-id WINDOW_ID --output-root "$capture_evidence_dir"
```

Use `--remote` only from an orchestrator and set `GUI_CAPTURE_SSH_TARGET` explicitly. Both macOS and GNOME X11 support explicit `--desktop` for debugging; window-level capture remains the default choice.

## Safety boundaries

- On macOS, the target must be raised through Accessibility before `screencapture -l`. Grant Accessibility and Screen Recording to the live responsibility process; an SSH session is not covered by the local terminal application's permission.
- Multi-monitor macOS capture is keyed by CoreGraphics window ID, not display index or crop coordinates.
- A macOS desktop capture uses `screencapture -x`; use it only when the requested evidence needs desktop context.
- GNOME Wayland must use a loaded semantic driver or portal-aware tool; do not silently fall back to X11 injection or a whole-screen image.
- Do not create placeholders, reuse stale images, or close/rearrange unrelated windows to manufacture evidence.
