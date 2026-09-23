---
task_id: dual-teleop-tailscale-20260923-ff228e71
goal: Start the installed unified SO-101 Teleop app on this Mac and ai-station, bound to each host's Tailscale IPv4, for remote expert-validation acceptance.
worktree: /Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp
branch: codex/so101-unified-webapp
mac_source_commit: ff228e71b30add6cdc39f816d4f08d4f063b5262
ai_station_source_commit_at_baseline: 0bce9179ebe87fe8146815a56510eec3040edc43
evidence_root: /tmp/so101-debug-dual-teleop-tailscale-20260923-ff228e71
evidence_root_hosts: Each host has its own instance of the same absolute path; the host name disambiguates files.
mac_durable_evidence_root: /opt/data/work/so101-evidence/dual-teleop-tailscale/20260923-ff228e71
ai_station_durable_evidence_root: /data/work/so101-evidence/dual-teleop-tailscale/20260923-ff228e71
latest_checkpoint: CP-003
next_experiment: NONE
---

## CP-001: read-only baseline

The orchestrator runs on `Terry-Mac-mini.local` in the named worktree at
`ff228e71`; its worktree is clean. The installed unified console entry and Web
bundle exist under `/opt/data/so101/workspace/install/so101_teleop`.
Tailscale reports `100.74.192.81`. No Teleop Web listener or Gazebo/MoveIt
stack was found on the candidate ports. Two unrelated static transform
publishers remain outside this task's ownership.

The SSH target identifies itself as `ai-station`, with Tailscale address
`100.104.202.119`. Its clean repository is
`/home/matianyi/Projects/ros-moveit-demo` at `0bce9179`; the documented
`/data/work/ws_moveit` path is absent. Its installed Teleop package has only
the two legacy server entries, so it must be updated and rebuilt before a
unified app can be started. No candidate Web listener or simulation stack was
found. Neither host-local task evidence root existed before this task; both
were created mode `0700` at the registered absolute path above.

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: The Mac install can launch directly, while ai-station needs a source fast-forward, package build, and verified Python Web dependencies first.
working_tree_status: This ledger is the only new local worktree file; the ai-station repository was clean at baseline.
owned_processes: NONE
preserved_processes: Mac static_transform_publisher PIDs 1541 and 1542; all other pre-existing tmux/processes remain untouched.
confirmed_conclusions:
  - Mac installed unified entry and bundle exist at the current project overlay.
  - ai-station is a different checkout location from the older skill reference and lacks the unified installed entry.
disproven_routes:
  - /data/work/ws_moveit is the active ai-station checkout.
open_risks:
  - The Mac has no /data/work durable evidence mount and passwordless sudo is unavailable; an operational evidence layout for remote acceptance remains to be resolved.
  - ai-station package and Python dependency closure must be verified after updating.
next_command: Fast-forward ai-station main and rebuild the installed unified service packages.
```

## CP-002: runtime preparation

The user selected `/opt/data` for macOS durable evidence, and `AGENTS.md` now
names `/opt/data/work/so101-evidence` for macOS. Both host-specific durable run
roots exist with mode `0700`. On ai-station, `main` was fast-forwarded from
`0bce9179` to published `ff228e71`; its submodule was updated to the locked
commit. The clean checkout rebuilt only `so101_demo_py` and `so101_teleop`
into its existing install prefix with colcon. The build passed in 7.45 seconds;
the installed unified console entry and Web bundle now exist. The remote Web
Python and Bun executable were resolved under the earlier full-UT evidence
root. The Mac installed entry, bundle, MPS v4 config, and Web Python imports
were also checked. No service has started yet.

```yaml
checkpoint_id: CP-002
last_valid_experiment: NONE
current_hypothesis: Both installed entry points can compose their Validation domain with platform-specific runtime profiles.
working_tree_status: Local AGENTS.md modified and this ledger untracked; remote checkout clean at ff228e71.
owned_processes: NONE
preserved_processes: Mac static_transform_publisher PIDs 1541 and 1542; all pre-existing tmux/processes remain untouched.
confirmed_conclusions:
  - ai-station installed unified app now matches published main ff228e71.
  - macOS durable run root is under /opt/data/work/so101-evidence, as directed by the user.
open_risks:
  - Mac production model bundle paths from an older experiment are absent; a valid bundle must be found or staged before model-backed acceptance.
next_command: Validate composition without binding ports, then launch each installed service in an owned tmux session.
```

## CP-003: both services available for expert validation

At `2026-09-23T12:58:42Z`, both hosts retain one task-owned Web process in a
dedicated tmux session. The final launch scripts are in each host's registered
`/tmp` root. Neither script starts a ROS bridge because no verified Teleop
worker or simulation stack is provisioned for this acceptance window. A prior
bridge startup attempt exposed that the child receives neither
`SO101_CHILD_SERVICE_TOKEN` nor `SO101_CHILD_SERVICE_EPOCH`; the final service
configuration does not launch that unprovisioned child. Teleop and Tasks report
`unavailable`, while Expert Validation reports `ready` on both hosts.

The Mac production YOLO weights and Grounded SAM bundle were copied from
ai-station into the registered Mac durable root. The YOLO SHA256 is
`f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781`.
The Grounded SAM manifest SHA256 is
`b55bb601d311407df8f9f25d9da18649f6bd78ac1299148bde0d07f7cfdfed05`.
All 11 manifest files passed size and SHA256 readback (`816115806` bytes).
The Mac runtime dependency versions match the manifest for torch, torchvision,
ultralytics, transformers, safetensors, mujoco, Pillow, and huggingface-hub.

ai-station's colcon symlink install required real paths for the validation
catalog, parallel and adaptive configs, and adaptive wrapper. Its installed
Web asset auto-discovery followed the symlink back into source, so the final
launch names the installed `web` directory with `--static-dir`. The final
Linux service uses `parallel_batch_v3.yaml`, not the macOS MPS profile.

```yaml
checkpoint_id: CP-003
last_valid_experiment: EXP-001
current_hypothesis: Both Tailscale-bound Validation services remain available until the operator completes acceptance.
working_tree_status: Documentation and this ledger changed in the Mac worktree; ai-station checkout clean at ff228e71.
owned_processes:
  mac: tmux so101-teleop-tailscale-mac; PID 4563; /opt/ros/jazzy/.venv/bin/python; 100.74.192.81:8000
  ai_station: tmux so101-teleop-tailscale-ai; PID 2118905; /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python; 100.104.202.119:8000
preserved_processes: Mac static_transform_publisher PIDs 1541 and 1542; all other pre-existing tmux/processes remain untouched.
confirmed_conclusions:
  - Both /expert-validation pages, JS/CSS assets, capabilities, and campaign-list endpoints return HTTP 200 from the Mac; ai-station also reaches the Mac page and capabilities through Tailscale with HTTP 200.
  - Both /health responses show validation ready; Teleop and Tasks unavailable because no backend was provisioned.
  - No task-owned Gazebo or MoveIt process was started.
disproven_routes:
  - A colcon symlink-install config path can be passed unchanged to ProductionRuntimeLayout._required_file.
  - The unified Web asset auto-discovery finds the ai-station symlink-install bundle without --static-dir.
retained_runs:
  mac: /opt/data/work/so101-evidence/dual-teleop-tailscale/20260923-ff228e71
  ai_station: /data/work/so101-evidence/dual-teleop-tailscale/20260923-ff228e71
archived_runs: []
deletion_candidates:
  - Both host-local /tmp/so101-debug-dual-teleop-tailscale-20260923-ff228e71 roots after acceptance and readback; no deletion authorized.
  - ai-station diagnostic-composition and diagnostic-composition-2 under its durable run root; no deletion authorized.
next_command: Operator conducts expert-validation acceptance using the two URLs; preserve both service sessions and all evidence.
```

## EXP-001: launch preparation

```yaml
experiment_id: EXP-001
status: COMPLETE
prior_experiment: NONE
hypothesis: The published main commit and installed dependency closure can provide one unified Web app per host without launching a duplicate ROS simulation stack.
prediction: Each host starts exactly one owned listener bound to its own Tailscale IPv4; the installed Web assets load and /health exposes the Validation domain.
single_variable: Bring the app service online on each host against its verified install prefix.
lifecycle: REUSE_STACK
preconditions:
  - No existing Teleop Web listener on the selected host port.
  - No task-owned Gazebo or MoveIt process.
success_criteria:
  - Both Tailscale URLs respond from the Mac with an installed page and readable health endpoints.
  - Each listener PID, executable, commit, install prefix, bind address, and evidence root are recorded.
failure_criteria:
  - A host cannot serve its installed page or Validation domain from the Tailscale address.
invalid_criteria:
  - A prior unrelated listener owns the selected port or the source/install identity changes during startup.
provenance:
  mac_source_commit: ff228e71b30add6cdc39f816d4f08d4f063b5262
  mac_install_overlay: /opt/data/so101/workspace/install
  mac_runtime_executable: /opt/ros/jazzy/.venv/bin/python
  mac_ros_domain_id: 225
  mac_gz_partition: so101-teleop-tailscale-mac-225
  ai_station_source_commit: ff228e71b30add6cdc39f816d4f08d4f063b5262
  ai_station_install_overlay: /home/matianyi/Projects/ros-moveit-demo/install
  ai_station_runtime_executable: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python
  ai_station_ros_domain_id: 226
  ai_station_gz_partition: so101-teleop-tailscale-ai-226
commands:
  - Mac /tmp/so101-debug-dual-teleop-tailscale-20260923-ff228e71/run-mac.zsh --check exited 0 with SO101_UNIFIED_APP_OK.
  - ai-station /tmp/so101-debug-dual-teleop-tailscale-20260923-ff228e71/run-ai.zsh --check exited 0 with SO101_UNIFIED_APP_OK.
  - Each host started its final run script in its own so101-teleop-tailscale-* tmux session.
observed:
  - Mac listener PID 4563 bound only to 100.74.192.81:8000; ai-station listener PID 2118905 bound only to 100.104.202.119:8000.
  - Both /expert-validation pages, bundled assets, capabilities, and campaign-list endpoints returned HTTP 200.
  - Cross-host Tailscale requests in both directions returned HTTP 200 for the expert-validation page and capabilities.
  - Both /health responses reported validation ready and teleop/tasks unavailable.
inferred:
  - The expert-validation UI and API are reachable for operator acceptance; no execution campaign was started by this task.
conclusion: The two installed unified Web services are running and reachable over their Tailscale IPv4 addresses for expert-validation acceptance.
evidence:
  - /tmp/so101-debug-dual-teleop-tailscale-20260923-ff228e71
decision: Keep both owned tmux sessions running for operator acceptance.
next_experiment: NONE
```
