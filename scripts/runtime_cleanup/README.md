# Runtime process cleanup

Each host has its own entry point. The first supported host is Linux `AI-STATION-001` (ai-station). Run the script as the account that owns the ROS and Teleop processes, using system Python 3.9 or later with Linux pidfd support. The host must provide `tmux`, `docker` and `systemctl`, and allow read-only access to their runtime state.

Preview targets and blockers:

```sh
/usr/bin/python3 scripts/runtime_cleanup/ai_station.py
```

Stop verified processes and close idle dedicated ROS/Teleop sessions:

```sh
/usr/bin/python3 scripts/runtime_cleanup/ai_station.py --apply \
  --evidence-dir /path/to/registered/task-evidence/cleanup-run-001
```

Use a new evidence directory for every run. Register its parent root in the task ledger before applying. The script saves process identity hashes, results and dedicated pane output there. It does not overwrite existing evidence or record full command arguments.

The script discovers executable paths, ROS/Teleop entry scripts and loaded ROS/simulator libraries. Prompt text, inherited ROS variables and an SO-101 training filename alone do not identify a target. Before each SIGINT, it opens a Linux pidfd and checks the PID, startup ticks, UID, executable and command hash against the discovery snapshot. The default exit timeout is 15 seconds per process; `--timeout` accepts up to 60 seconds. A timeout returns a blocker without escalating to SIGTERM or SIGKILL.

Running containers, active named ROS/Teleop user services, service-owned targets and targets belonging to another UID block application before any signal. Stop those launchers through their owning lifecycle, then preview again. The script does not stop containers or disable services. Failed historical services and stopped containers remain intact. Host-protected process metadata is reported; a failed Docker or tmux inspection is not treated as an empty environment.

Only `so101-expert-validation`, `so101-mujoco` and `so101-teleop` sessions can be closed. Their pane and shell identities must still match the initial snapshot, and their shells must have no remaining children. A changed session or a session containing Codex or any other child is retained and reported as a blocker. Other tmux sessions are preserved.

ROS installations, virtual environments, source, build/install trees, Docker images/containers/volumes, supervisor history, recovery fences and existing evidence remain on disk. Killing a process does not recover a campaign record or prove normal campaign cleanup. A PASS result means no identified ROS/Teleop process remains in the final snapshot. New processes started afterward require another preview.

Run the script's tests without starting ROS or a simulator:

```sh
/usr/bin/python3 -m unittest discover -s scripts/runtime_cleanup/tests -v
```
