---
name: ai-station-gui
description: Use when capturing screenshots, inspecting desktop state, or controlling GUI windows on ai-station from Codex, Claude, or Kimi.
---

# AI Station GUI

Prefer a healthy, currently loaded `cua-driver` capability for semantic screen work. Use the deterministic script only as a screenshot fallback.

**REQUIRED BACKGROUND:** For SO-101 work, use `so101-dev` and obey its provenance, process-ownership, experiment-ledger, and fresh-evidence gates.

## Route the request

1. Prove whether the current process is 直接运行在 ai-station from live hostname and workspace evidence. Do not infer locality from an SSH alias. An agent on ai-station 不得 SSH 自身.
2. Identify the live agent context as Codex, Claude, or Kimi.
3. Inspect the current tool and Skill inventory for a loaded `cua-driver` screen-control capability and its live schema. A binary, directory, tmux session, or another agent's driver is not current-agent capability.
4. Probe the driver, desktop, and session permissions with that schema. Treat absent, busy, degraded, or unowned capability as unavailable; never restart or take over another agent session.
5. When healthy, perform every interaction as `snapshot -> action -> fresh snapshot`. Resolve element identifiers anew after each snapshot.
6. When unavailable, run `scripts/capture-ai-station.sh`. State that this fallback captures screenshots only.

If semantic mouse, keyboard, focus, or UI control is required but only script capture is available, capture evidence and report control unavailable. Do not inject X11 keys as a substitute.

## Capture fallback

Run locally when already on ai-station:

```bash
capture_evidence_dir=$(mktemp -d)
.agents/skills/ai-station-gui/scripts/capture-ai-station.sh --local \
  --output-root "$capture_evidence_dir"
```

Use `--remote` only from a Mac/orchestrator and set `AI_STATION_SSH_TARGET` explicitly when needed. Never write captures into the source tree.

Read [references/capture-contract.md](references/capture-contract.md) before interpreting or transferring a manifest. Inspect the fresh `desktop.png`; file existence alone is not visual evidence.

## Safety boundaries

- Treat `desktop.png` as required and RViz/Ghostty windows as optional.
- Do not close windows to manufacture an absent-window test.
- Do not copy null paths, create placeholders, reuse stale files, or claim control from a screenshot.
- Run `--test-ghostty-tabs` only when the window is absent or ownership is explicit. Absence must produce `skipped_no_window` without a key event.
