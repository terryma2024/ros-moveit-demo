# Capture Contract

The helper prints exactly one JSON object to stdout. Diagnostics go to stderr. A valid manifest has this shape:

```json
{
  "captured_at": "2026-08-11T12-00-00",
  "desktop": "/tmp/evidence/desktop.png",
  "rviz": null,
  "ghostty": null,
  "captured_windows": [],
  "missing_windows": ["rviz", "ghostty"],
  "capture_mode": "desktop_only",
  "ghostty_tab_test": "not_requested"
}
```

`desktop` is the only required image. It must name a fresh, nonempty PNG in the current capture directory. `rviz` and `ghostty` are either fresh, nonempty paths or JSON null. Never create a placeholder for a missing optional window.

`captured_windows` and `missing_windows` partition the optional names `rviz` and `ghostty`. `capture_mode` is `desktop_only` when neither exists, otherwise `desktop_and_windows`. `ghostty_tab_test` is `not_requested`, `completed`, or `skipped_no_window`; the skipped result sends no key.

Exit `0` after every valid desktop capture, including when one or both optional windows are absent. Exit nonzero only when desktop capture fails, the manifest is invalid, or transfer fails for an artifact declared by a non-null manifest path.
