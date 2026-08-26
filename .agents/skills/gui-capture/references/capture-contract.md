# Capture Contract

The helper prints exactly one JSON object to stdout; diagnostics go to stderr. A target-window capture has this shape:

```json
{
  "captured_at": "20260826T120000",
  "platform": "macos",
  "session_type": "aqua",
  "capture_mode": "window",
  "selector": {"query": null, "window_id": 4107},
  "window": {
    "id": 4107,
    "owner": "Codex",
    "title": "moveit-demo",
    "x": -1512,
    "y": 80,
    "width": 1400,
    "height": 900
  },
  "image": "/tmp/evidence/20260826T120000-abcd1234/window.png"
}
```

`image` is the only artifact and must be a fresh, nonempty PNG inside the current capture directory. `window` is required for `capture_mode=window`. Negative global coordinates are valid on multi-monitor desktops and must not be normalized to the primary display.

macOS and GNOME X11 desktop capture use `capture_mode=desktop`, `window=null`, and `desktop.png`. On macOS this mode runs `screencapture -x`; it is an explicit debugging option, while ordinary target evidence should use window-level `screencapture -l`.

Selection is fail-closed. An exact ID must resolve once. A query must produce one best title/owner match; ambiguity exits nonzero and reports candidate IDs. Capture also exits nonzero when focus/raise fails, the image is empty, the manifest is invalid, or a declared remote image cannot be transferred.

`--local` never calls SSH or SCP. `--remote` uses `GUI_CAPTURE_SSH_TARGET`, transfers only the declared image, and preserves the exact remote manifest; remote provenance is not rewritten into local-looking paths.
