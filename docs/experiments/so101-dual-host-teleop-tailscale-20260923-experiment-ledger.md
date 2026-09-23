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
current_commit: b7f1f50692b8561420c797184a98ab2b56e6816e
latest_checkpoint: CP-007
next_experiment: EXP-005
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

## CP-004: Mac resource preflight refusal

During remote expert validation, the operator selected `PARALLEL` with two
workers, acquired a lease, generated points, and saw `RESOURCE_PROBE_FAILED`
at Check Resources. The Mac service log records several successful HTTP 200
preflight responses to the operator's Tailscale client; the response body can
still carry a refused receipt. The service remains PID 4563 on
`100.74.192.81:8000`; the operator's lease and points remain untouched.

A standalone call to the installed `_HostResourceProbe` under the same sourced
Mac launch environment returned `accepted=false`, reason
`RESOURCE_PROBE_FAILED`, and `probe_error=CoordinatorError`. The launch script
does not export `SO101_TASK_ROOT`. `ProbeCoordinator.default_state_root()`
requires that variable and raises `PROBE_STATE_ROOT_UNSET` when absent. The
existing macOS live-window launcher explicitly exports it before starting the
service. No task-owned Gazebo, MoveIt, or campaign process was started by this
diagnosis.

```yaml
checkpoint_id: CP-004
last_valid_experiment: EXP-001
current_hypothesis: The missing SO101_TASK_ROOT in the Mac service process causes every W2 resource probe to return RESOURCE_PROBE_FAILED.
working_tree_status: Clean at 4a00ff05 before this checkpoint; the ledger becomes the only local edit.
owned_processes:
  mac: tmux so101-teleop-tailscale-mac; PID 4563; 100.74.192.81:8000
  ai_station: tmux so101-teleop-tailscale-ai; PID 2118905; 100.104.202.119:8000
confirmed_conclusions:
  - The installed Mac resource probe reproduces the reported refusal without using the operator's lease.
  - SO101_TASK_ROOT is absent from the Mac task launch script and process environment.
open_risks:
  - A service restart may require the operator to acquire a fresh lease and regenerate points.
next_command: Add SO101_TASK_ROOT to the Mac launch environment only; run the same standalone probe, then restart the owned Mac service.
```

## EXP-002: bind Mac resource probe state to registered evidence

```yaml
experiment_id: EXP-002
status: VALID
prior_experiment: EXP-001
hypothesis: Setting SO101_TASK_ROOT to the registered Mac durable root resolves the CoordinatorError in W2 resource preflight.
prediction: The same installed _HostResourceProbe call no longer returns RESOURCE_PROBE_FAILED or probe_error CoordinatorError, and the remote Check Resources receipt is admitted or reports a concrete resource limit.
single_variable: SO101_TASK_ROOT in the Mac service launch environment.
lifecycle: REUSE_STACK
preconditions:
  - The current Mac service is the recorded PID 4563 in tmux so101-teleop-tailscale-mac.
  - No task-owned simulation or campaign is running.
success_criteria:
  - A fresh W2 probe returns an admitted result or a specific resource check outcome instead of RESOURCE_PROBE_FAILED.
  - The Mac service is rebound to 100.74.192.81:8000 with Validation ready.
failure_criteria:
  - The probe still returns RESOURCE_PROBE_FAILED after SO101_TASK_ROOT is set.
invalid_criteria:
  - An unowned process replaces the listener or the install/config identity changes during the experiment.
provenance:
  source_commit: 4a00ff0536fb77c5513113817ca7620d23ab4a5d
  install_overlay: /opt/data/so101/workspace/install
  runtime_executable: /opt/ros/jazzy/.venv/bin/python
  ros_domain_id: 225
  gz_partition: so101-teleop-tailscale-mac-225
commands:
  - Added export SO101_TASK_ROOT="$durable" to the Mac task launch script, where durable is /opt/data/work/so101-evidence/dual-teleop-tailscale/20260923-ff228e71.
  - Ran the identical installed _HostResourceProbe diagnostic with only SO101_TASK_ROOT changed; exit code 0.
  - Verified no campaign or simulation owner existed, stopped only Mac service PID 4563 through its tmux session, and restarted the corrected script; exit code 0.
  - Ran an isolated installed Expert Validation ASGI API flow: acquired a diagnostic lease, generated 20 points, submitted PARALLEL/W2 MPS_W2_FIRST_PASS preflight, and released the diagnostic lease; exit code 0.
observed:
  - Baseline diagnostic at /tmp/so101-debug-dual-teleop-tailscale-20260923-ff228e71/mac-resource-red.json returned RESOURCE_PROBE_FAILED with probe_error CoordinatorError.
  - Corrected diagnostic at /tmp/so101-debug-dual-teleop-tailscale-20260923-ff228e71/mac-resource-green.json returned accepted=true, reasons=[], start_guard_status=PASS, cleanup_state=CLEAR, CPU_CAPACITY_OK, RAM_OK, and MPS_HEADROOM_OK.
  - Restarted Mac service PID 6557 is bound to 100.74.192.81:8000; its process environment contains SO101_TASK_ROOT at the registered Mac durable root.
  - The expert-validation page and capabilities return HTTP 200; /health reports validation ready.
  - The isolated API preflight returned HTTP 200, admitted=true, reason_codes=[], start_guard PASS, and cleanup_state CLEAR; the diagnostic lease release returned released=true.
  - An earlier unified TestClient harness was invalid because its worker thread crossed the SQLite connection and it omitted instance authority headers; it did not exercise the intended preflight boundary.
inferred:
  - The missing task root was the cause of the reproduced RESOURCE_PROBE_FAILED result; the operator's browser flow still needs a fresh lease after the restart.
conclusion: The installed W2 resource probe succeeds with the registered SO101_TASK_ROOT, and the corrected Mac service is online.
evidence:
  - /tmp/so101-debug-dual-teleop-tailscale-20260923-ff228e71
  - /tmp/so101-debug-dual-teleop-tailscale-20260923-ff228e71/mac-preflight-api-v2.json
  - /opt/data/work/so101-evidence/dual-teleop-tailscale/20260923-ff228e71/launch/run-mac.zsh (SHA256 493826a2e97da6cddc3b434905f35c095c5dcc202dda22d48eabbce270ab62d6)
decision: KEEP
next_experiment: EXP-003
```

## CP-005: corrected Mac service online

The corrected Mac service is PID 6557 in the same task-owned tmux session.
`SO101_TASK_ROOT` points to the registered Mac durable root; the source and
retained launch-script copies share SHA256
`493826a2e97da6cddc3b434905f35c095c5dcc202dda22d48eabbce270ab62d6`.
The W2 probe passed with 10 logical CPUs, 14,793,031,680 available RAM bytes,
and 14,644,183,040 MPS headroom bytes. The service is reachable at the same
Tailscale URL and Validation is ready. The operator's lease may require renewal
after this restart. A separate installed API diagnostic with 20 points admitted
the W2 preflight and released its own lease. No campaign was started by the
diagnosis.

```yaml
checkpoint_id: CP-005
last_valid_experiment: EXP-002
current_hypothesis: A fresh browser lease and point selection should now pass Check Resources through the corrected Mac service.
working_tree_status: This ledger is modified; no application source or installed package changed.
owned_processes:
  mac: tmux so101-teleop-tailscale-mac; PID 6557; 100.74.192.81:8000
  ai_station: tmux so101-teleop-tailscale-ai; PID 2118905; 100.104.202.119:8000
confirmed_conclusions:
  - The same installed resource probe changed from RESOURCE_PROBE_FAILED to accepted with only SO101_TASK_ROOT added.
  - The corrected Mac process has the registered SO101_TASK_ROOT and Validation ready.
  - Isolated installed Expert Validation API preflight admitted PARALLEL/W2 with an empty reason_codes list.
open_risks:
  - Browser-level Check Resources after a new lease has not yet been observed.
retained_runs:
  mac: /opt/data/work/so101-evidence/dual-teleop-tailscale/20260923-ff228e71
  ai_station: /data/work/so101-evidence/dual-teleop-tailscale/20260923-ff228e71
archived_runs: []
deletion_candidates:
  - Both host-local /tmp/so101-debug-dual-teleop-tailscale-20260923-ff228e71 roots after acceptance; no deletion authorized.
  - ai-station diagnostic-composition and diagnostic-composition-2 under its durable run root; no deletion authorized.
  - Mac diagnostic-preflight-20260923 and diagnostic-preflight-api-20260923 under its durable run root after readback; no deletion authorized.
next_command: Observe a fresh operator Check Resources receipt without starting a campaign.
```

## EXP-003: operator browser preflight recheck

```yaml
experiment_id: EXP-003
status: VALID
prior_experiment: EXP-002
hypothesis: A fresh lease and points in the operator browser will yield a resource preflight receipt with no RESOURCE_PROBE_FAILED reason.
prediction: Check Resources shows W2 start guard PASS and permits the next acceptance step, or a specific current resource limit replaces the prior setup error.
single_variable: Fresh operator lease after the Mac service restart.
lifecycle: REUSE_STACK
preconditions:
  - Mac service PID 6557 remains bound to 100.74.192.81:8000 with Validation ready.
success_criteria:
  - The operator's next Check Resources receipt has no RESOURCE_PROBE_FAILED reason.
failure_criteria:
  - The browser still shows RESOURCE_PROBE_FAILED on a fresh lease and manifest.
invalid_criteria:
  - The browser reuses an expired lease or an unrelated service replaces PID 6557.
provenance:
  source_commit: 4a00ff0536fb77c5513113817ca7620d23ab4a5d
  install_overlay: /opt/data/so101/workspace/install
  runtime_executable: /opt/ros/jazzy/.venv/bin/python
  ros_domain_id: 225
  gz_partition: so101-teleop-tailscale-mac-225
commands:
  - Operator browser acquired a fresh lease, generated P01-P20, passed Check Resources, and started campaign campaign-2f433c80a9f546b381ec0e950eb9ec36.
observed:
  - The server admitted and launched W2 batch b6517, proving the resource preflight no longer returned RESOURCE_PROBE_FAILED.
  - The batch subsequently ended W2_CAMPAIGN_INCOMPLETE for a station runtime failure; that later boundary is recorded in CP-006 and EXP-004.
inferred: []
conclusion: The operator's Check Resources gate passed and admitted W2; no point-execution success follows from this result.
evidence:
  - /tmp/so101-debug-dual-teleop-tailscale-20260923-ff228e71
decision: KEEP
next_experiment: EXP-004
```

## CP-006: first operator W2 campaign stopped at station readiness

The operator's resource check admitted a 20-point W2 first pass. Its batch
`b6517` in campaign `campaign-2f433c80a9f546b381ec0e950eb9ec36`
terminated `W2_CAMPAIGN_INCOMPLETE` with exit code 7 and complete cleanup.
The two workers produced no point results. Both readiness records say
`MOTION_STACK_CONTROLLER_SERVICE_INVISIBLE`; the campaign log shows that
`libsdformat_urdf_plugin.dylib` could not load `@rpath/libsdformat14.14.dylib`.
The library and dylib farm link exist, but the task-owned Mac launch script did
not export `DYLD_LIBRARY_PATH`. The journal also contains `ATTEMPT_FAILED`,
which the Web campaign reader currently refuses, so the browser polls a 404
`UPSTREAM_PROJECTION_INVALID` and retains its cached `EXECUTING` view. The
campaign and station PIDs are gone; their owner cleanup receipt is clear.

```yaml
checkpoint_id: CP-006
last_valid_experiment: EXP-003
current_hypothesis: Exporting the fixed dylib farm in the Mac service and projecting verified infrastructure failures will make station readiness and the Web terminal status converge.
working_tree_status: docs/experiments/so101-dual-host-teleop-tailscale-20260923-experiment-ledger.md modified; application source clean.
owned_processes:
  mac: tmux so101-teleop-tailscale-mac; Web PID 6557; no campaign or station descendants
  ai_station: tmux so101-teleop-tailscale-ai; Web PID 2118905
confirmed_conclusions:
  - EXP-003 resource preflight was admitted because the W2 campaign started.
  - The batch terminated incomplete with cleanup complete and no executed points.
  - The first station failure is a missing dylib search path, before controller readiness.
  - The Web projection rejects ATTEMPT_FAILED and returns UPSTREAM_PROJECTION_INVALID.
open_risks:
  - A corrected Mac station has not yet reached ready under W2 concurrency.
  - The terminal projection must preserve UNRUN business results and refuse tampered failure evidence.
next_command: Add a failing campaign-layout regression for the observed ATTEMPT_FAILED journal.
```

## EXP-004: repair Mac W2 station startup and infrastructure projection

```yaml
experiment_id: EXP-004
status: VALID
prior_experiment: EXP-003
hypothesis: The absent fixed dylib search path causes the Mac station startup failure, and the unsupported ATTEMPT_FAILED event causes the stale Web view.
prediction: With only those boundaries corrected, the station readiness gate can see active controllers and the existing incomplete batch projects INFRA_FAILED with zero evaluated points.
single_variable: Mac launch environment DYLD_LIBRARY_PATH and campaign failure-event projection at their separate owning boundaries.
correction: The original planned entry combined two independent boundaries. The projection RED/GREEN and the dylib loader plus W2 readiness A/B were evaluated sequentially; no point-business success is inferred from either.
lifecycle: REUSE_STACK
preconditions:
  - Existing campaign batch b6517 is terminal and its owner cleanup receipt is clear.
  - Mac Web PID 6557 is the sole validation service for the registered root.
success_criteria:
  - The existing failure batch projects as INFRA_FAILED, with 20 requested and zero evaluated.
  - A fresh isolated Mac W2 readiness check no longer fails at the sdformat dylib boundary.
failure_criteria:
  - The identical failure journal still yields UPSTREAM_PROJECTION_INVALID, or the corrected station still cannot load sdformat.
invalid_criteria:
  - A different Web process or unowned ROS stack supplies the observed readiness.
provenance:
  source_commit: 3a750cfac91f2bcb88e5b6d8882d24ac8fa3f1ec
  install_overlay: /opt/data/so101/workspace/install
  runtime_executable: /opt/ros/jazzy/.venv/bin/python
  ros_domain_id: 181,182 (failed campaign); 225 (Web)
  gz_partition: so101-teleop-tailscale-mac-225
commands:
  - Added and ran the ATTEMPT_FAILED projection regression against source; RED exit code 1, then GREEN exit code 0.
  - Replayed the original b6517 journal through the source CampaignLayoutReader; exit code 0, ten verified events.
  - Exported DYLD_LIBRARY_PATH=/opt/ros/jazzy/dylib_farm/current in the task-owned Mac launch script; loaded libsdformat_urdf_plugin.dylib with ctypes; exit code 0.
  - Built so101_teleop into /opt/data/so101/workspace/install; exit code 0 in 69 seconds; source and installed Python file SHA256 values matched.
  - Restarted the task-owned Mac Web service at 100.74.192.81:8000 and queried the original campaign; HTTP 200.
  - Ran complete src/so101_teleop/test with pytest-xdist -n 8 on a ten-logical-CPU Mac; final exit code 0, 1056 passed and 19 skipped in 83.13 seconds.
  - Started two installed Mac task stations in ROS domains 181 and 182 and ran motion_stack_ready concurrently; both exit codes 0 and both stations cleaned up.
observed:
  - The original batch now reports INFRA_FAILED, requested=20, evaluated=0, not_executed=20, both workers STOPPED, and batch_cleanup_complete=true.
  - The two station readiness documents report three active controllers, three MoveIt services, and three actions each; both reached READY in 13.73 seconds.
  - The Mac service PID 13297 has the fixed dylib farm and SO101_TASK_ROOT in its environment; health reports Validation ready.
  - A first full 8-worker gate passed 1056 tests, then a repeat exposed a macOS process-argv race in an owner-tree test; waiting for stable child argv made the targeted test and final full 8-worker gate pass.
  - CoreGraphics listed both new MuJoCo windows; gui-capture window capture failed at the Accessibility raise step, so no fresh PNG was obtained.
inferred:
  - The fixed dylib path removed the observed station startup blocker. Point motion and all 20 business outcomes remain untested in this repair run.
conclusion: The stale EXECUTING projection and the observed W2 station readiness failure are repaired; full expert validation still requires a new operator campaign.
evidence:
  - /opt/data/work/so101-evidence/dual-teleop-tailscale/20260923-ff228e71/campaigns/campaign-2f433c80a9f546b381ec0e950eb9ec36/b6517
  - /opt/data/work/so101-evidence/dual-teleop-tailscale/20260923-ff228e71/station-w2.Wla4lIZ9/ready.json (SHA256 a46f74e699568564fb0db3b2f44bef98add3a65d0084ce2b8fd7401b5d9f3221)
  - /tmp/so101-debug-dual-teleop-tailscale-20260923-ff228e71/so101-teleop-pytest8-repeat.xml
  - /tmp/so101-debug-dual-teleop-tailscale-20260923-ff228e71/so101-teleop-build.log
decision: KEEP
next_experiment: NONE
```

## CP-007: Mac W2 station readiness and Web terminal projection restored

The task-owned Mac Web process is PID 13297 in the restarted tmux session at
`100.74.192.81:8000`. The fixed launch script SHA256 is
`570cba3d470256c6f16067e1816787c16ba9771027c9b5234d0c35ebb63e8fe9`.
The original batch now returns HTTP 200 with `INFRA_FAILED`, 20 requested,
0 evaluated, 20 unrun, two stopped workers, and complete cleanup. Both new
diagnostic stations reached `READY` concurrently on ROS domains 181 and 182;
their three controllers were active and the relevant MoveIt services/actions
were visible. The probe-owned station PIDs and controller PIDs are gone. The
Mac package build and final eight-worker full pytest gate passed. The failed
batch remains retained as an infrastructure run, not a business result.

```yaml
checkpoint_id: CP-007
last_valid_experiment: EXP-004
current_hypothesis: A new operator W2 first pass can now advance beyond station readiness; point motion and physical outcomes remain unverified.
working_tree_status: docs/experiments/so101-dual-host-teleop-tailscale-20260923-experiment-ledger.md, src/so101_teleop/so101_teleop/expert_validation/campaign_layout.py, production.py, reducer.py, and two so101_teleop tests modified.
owned_processes:
  mac: tmux so101-teleop-tailscale-mac; Web PID 13297; no diagnostic station descendants
  ai_station: tmux so101-teleop-tailscale-ai; Web PID 2118905, unchanged
preserved_processes: Mac static_transform_publisher PIDs 1541 and 1542 and unrelated existing sessions.
confirmed_conclusions:
  - EXP-004 original failure batch projects INFRA_FAILED without fabricating business results.
  - EXP-004 two concurrent Mac stations reached READY on separate ROS domains with active controllers and visible MoveIt dependencies.
  - EXP-004 full so101_teleop pytest gate passed at 8 workers on ten logical CPUs.
open_risks:
  - No new 20-point business run or physical outcome was executed after the repair.
  - gui-capture could list the two MuJoCo windows but Accessibility blocked window raise and fresh PNG capture.
retained_runs:
  mac: /opt/data/work/so101-evidence/dual-teleop-tailscale/20260923-ff228e71
  ai_station: /data/work/so101-evidence/dual-teleop-tailscale/20260923-ff228e71
archived_runs: []
deletion_candidates:
  - Mac /opt/data/tmp/so101-projection-NobuDn6Y, /opt/data/tmp/so101-projection-final-iyUQ8TL9, and /opt/data/tmp/so101-projection-repeat-ZprFAoOG after readback; no deletion authorized.
  - Host-local /tmp/so101-debug-dual-teleop-tailscale-20260923-ff228e71 roots after acceptance; no deletion authorized.
next_command: Operator refreshes the Mac page, reacquires a lease if expired, generates P01-P20, checks resources, and starts a new PARALLEL/W2 campaign.
```

## EXP-005: operator rerun of 20-point W2 first pass

```yaml
experiment_id: EXP-005
status: PLANNED
prior_experiment: EXP-004
hypothesis: The repaired Mac service can execute the operator's selected P01-P20 campaign beyond station readiness.
prediction: Both stations become READY, the journal advances past the two first ATTEMPT_STARTED events into committed point results or a specific later failure, and the browser reaches a terminal status after cleanup.
single_variable: Fresh operator campaign under the repaired installed service.
lifecycle: REUSE_STACK
preconditions:
  - Mac service PID 13297 reports Validation ready and no campaign owner is active.
  - Operator has a valid lease and uses PARALLEL with WorkerCount=2.
success_criteria:
  - The browser and API agree on terminal status, per-point outcomes, and cleanup; physical success is assessed only from the new campaign evidence.
failure_criteria:
  - Any station fails readiness, any point execution fails, or the browser diverges from a terminal backend batch.
invalid_criteria:
  - A stale lease or unrelated service/ROS stack owns the request.
provenance:
  source_commit: b7f1f50692b8561420c797184a98ab2b56e6816e
  install_overlay: /opt/data/so101/workspace/install
  runtime_executable: /opt/ros/jazzy/.venv/bin/python
  ros_domain_id: 181,182 (W2 slots); 225 (Web)
  gz_partition: so101-teleop-tailscale-mac-225
commands: []
observed: []
inferred: []
conclusion: PENDING
evidence:
  - /opt/data/work/so101-evidence/dual-teleop-tailscale/20260923-ff228e71
decision: PENDING
next_experiment: NONE
```
