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

The wrapper accepts one execution mode. `--local` runs the colocated helper directly and never calls SSH or SCP. `--remote` installs and executes that helper through `AI_STATION_SSH_TARGET`. Automatic mode selection is allowed only from live hostname plus workspace evidence; an ai-station process never SSHes to itself.

Remote mode transfers the required desktop and only optional artifacts named by non-null paths. It stores the exact remote manifest beside the transferred files so remote provenance is not rewritten into local-looking paths. Local mode requires every declared path to be a fresh, nonempty artifact under the current output root.
