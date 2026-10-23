# Raw pilot readiness and process ownership

Date: 2026-10-08

Trigger: the inherited round-13 prototype reports RECORDING for a silent publisher. The regression is retained at `/data/work/so101-evidence/act-data/20260924-fbc25063-resume/scratch/offline-p1-readiness-red-iqLyLGHY/`. Parallel related tests also stopped the recording child before it opened the bag: `scratch/offline-p1-related-ZHxi17QL/` under the same evidence root.

Options considered:

- Complete the inherited in-process `rosbag2_py.Recorder` wrapper and its C++/Python context lifecycle.
- Use the plan's `ros2 bag record -s mcap` subprocess, owned by the raw sidecar, and a small read-only readiness subscriber.

Recommended option taken under CP-3394: use the CLI recorder in its own process group. The readiness subscriber observes a message after the bag subscription appears. Closed-bag counts and offline continuity checks still decide whether recording was complete. The sidecar polls the planning scene and publishes the original read with CDR and timestamps on `/so101/raw/planning_scene_reads`; it also retains the JSONL copy.

Contract impact: readiness now requires received data, not merely a publisher/subscription graph match. Teacher events are checked after recording because their publisher does not exist before Teacher startup. Any bounded readiness failure marks data invalid and the Teacher still runs. An early termination waits at most five seconds for the recording child to open its output before sending SIGINT, then waits at most fifteen seconds for close. This is a data-process shutdown rule; it does not delay or cancel a running Teacher.

Tests: `test_act_raw_readiness.py` covers the silent publisher, recorded scene reads and real CLI signal shutdown. `test_act_raw_pilot.py` checks owned-process start/stop and failure isolation. The inherited count test now stops publishing before bag shutdown so its count requirement describes the recording window. It still requires every published message in that window.

Rollback: verified baseline tarball `handoffs/codex-act-offline-20261007/backups/p0-source-baseline.tar.gz` under the registered evidence root. Pilot activation is confined to the new immutable tooling revisions; previous revisions remain available. No Teacher source changed.

Ledger CP: CP-3431; follow-on package and live evidence will be recorded separately.
