# macOS TCC troubleshooting

Use this reference when exact-window capture fails through SSH, Accessibility
mapping fails, `screencapture` exits nonzero, or macOS shows no permission
prompt. Screen Recording is named **Screen & System Audio Recording** on recent
macOS versions.

## Identify the permission owner

TCC permission follows the live responsibility chain, not the terminal window
that originated an SSH connection. Do not assume that `Ghostty`, `Terminal`,
`sshd-keygen-wrapper`, `sshd`, or `screencapture` is the correct principal.
Inspect the current remote shell and walk its parents:

```zsh
pid=$$
while (( pid > 1 )); do
  ps -p "$pid" -o pid=,ppid=,user=,comm=,args=
  pid=$(ps -p "$pid" -o ppid= | tr -d ' ')
done
```

On current macOS releases, Remote Login commonly produces a chain like:

```text
zsh
sshd-session: USER@notty
sshd-session: USER [priv]
launchd
```

In that case, add `/usr/libexec/sshd-session` with the `+` button in **System
Settings -> Privacy & Security -> Screen & System Audio Recording** and enable
it. `/usr/libexec/sshd-keygen-wrapper` may exist without participating in the
live session; its presence is not evidence that it owns the capture request.

Confirm the selected binary and its stable code identity when needed:

```zsh
ls -l /usr/libexec/sshd-session
codesign -dv --verbose=4 /usr/libexec/sshd-session 2>&1 \
  | grep -E 'Identifier|TeamIdentifier|Authority'
```

After changing TCC, close the test SSH connection and establish a fresh one.
Permission normally persists for later sessions with the same code identity,
but an OS update, code-identity change, or TCC reset can require reauthorization.
Do not run a broad `tccutil reset` as routine troubleshooting because it removes
existing grants.

## Separate Accessibility from Screen Recording

Use the failure boundary to choose the next check:

| Observation | Likely boundary | Action |
| --- | --- | --- |
| Window inventory is absent or ambiguous | Selection, visibility, or stale window ID | Relist windows and require one exact current ID. |
| JXA/`osascript` cannot map or raise one AX window | Accessibility or CG-to-AX matching | Check Accessibility for the live responsibility process and inspect PID/title/geometry matching. |
| AX mapping and `AXRaise` succeed, then `screencapture -l` exits 1 | Screen Recording TCC | Authorize the live responsibility binary found from the parent chain. |
| Local terminal capture succeeds but the same command over SSH fails | Responsibility mismatch | Do not add more permission to the local terminal; inspect the SSH chain. |
| No permission dialog appears | Inconclusive and common over SSH | Inspect TCC state/process identity; absence of a prompt is not approval. |
| Direct exact-ID capture succeeds but the helper fails | Helper selection/focus path | Diagnose the helper; do not widen to desktop capture. |

CoreGraphics can report an empty title while Accessibility reports a nonempty
title. In that case, match one window by the same owner PID and bounded geometry;
keep nonempty titles strict and reject zero or multiple matches. Never guess a
window from size alone.

To observe denials while reproducing from a fresh SSH connection, use a second
local or remote session:

```zsh
/usr/bin/log stream --style compact \
  --predicate 'subsystem == "com.apple.TCC" OR process == "tccd"'
```

## Verify with an exact window

First obtain a fresh inventory and freeze the intended window ID:

```zsh
cd "$HOME/Projects/robot_demo_001/moveit-demo"
.agents/skills/gui-capture/scripts/capture-gui.sh \
  --local --list-windows --platform macos
```

Then run the normal helper into a task-owned evidence directory:

```zsh
window_id=533  # replace with the fresh inventory result
capture_evidence_dir="/tmp/gui-capture-tcc-check-$(date +%Y%m%d-%H%M%S)"
.agents/skills/gui-capture/scripts/capture-gui.sh \
  --local --platform macos --window-id "$window_id" \
  --output-root "$capture_evidence_dir"
rc=$?
printf 'capture exit code: %s\n' "$rc"
find "$capture_evidence_dir" -type f -print
```

For a narrow TCC probe after freezing the ID, the underlying command is:

```zsh
window_id=533  # replace with the fresh inventory result
output="/tmp/window-${window_id}-$(date +%Y%m%d-%H%M%S).png"
/usr/sbin/screencapture -x -l "$window_id" "$output"
rc=$?
printf 'capture exit code: %s\n' "$rc"
test "$rc" -eq 0 && test -s "$output" && file "$output"
```

Acceptance requires all of the following:

- exit code zero and a nonempty PNG;
- a manifest naming the same current window ID, owner, title, and bounds;
- original-resolution visual inspection showing the complete intended window;
- no substitution with `screencapture -x`, desktop capture, or coordinate crop.

A desktop screenshot may be an explicitly labeled TCC diagnostic, but it cannot
qualify exact-window evidence. If the exact ID cannot be captured, report the
visual gate as unavailable or failed.
