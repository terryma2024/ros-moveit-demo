# SO-101 Linux Expert Validation controller instance mismatch, 2026-09-24

```yaml
task_id: so101-linux-controller-instance-20260924
goal: Reproduce and repair Generate Points CONTROLLER_INSTANCE_MISMATCH on ai-station through the live Expert Validation page.
success_contract: One current browser document can acquire its lease and generate points without a controller identity mismatch; no active campaign is interrupted.
worktree: /Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp
linux_worktree: /home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp
branch: codex/so101-unified-webapp
base_commit: fd7348aa27361750f7e2e7954df53ef75e96545c
current_commit: e04c4ff1c8c85c7eba566d6b1960c75b57234099
evidence_root_mac: /tmp/so101-debug-linux-controller-instance-20260924
evidence_root_linux: /data/work/so101-evidence/controller-instance-mismatch/20260924-e04c4ff1
low_rate_root_linux: /tmp/so101-debug-linux-controller-instance-20260924
confirmed_conclusions:
  - The ai-station feature worktree is clean at e04c4ff1, but PID 2227775 serves the main checkout install at fd7348aa.
  - The Linux service reports Validation ready, global IDLE, and zero campaigns before reproduction.
  - EXP-001 reproduced Acquire Lease CONTROLLER_ALREADY_BOUND followed by Generate Points CONTROLLER_INSTANCE_MISMATCH; all three recorded leases are EXPIRED and the supervisor has zero campaigns.
  - EXP-002: after managed restart, Acquire Lease succeeds and Generate Points reaches a different failure, VALIDATION_MANIFEST_INPUT_INVALID; the installed demo resources are symlinks to source files and the manifest reader rejects them.
  - EXP-003: a non-symlink so101_demo_py install makes Generate Points succeed and persists a 20-point manifest with P01 through P20.
  - EXP-004: a full copied e04c4ff1 overlay passed build, doctor, targeted Linux tests, and a fresh Computer Use 20-point generation; final PID 2260420 has no controller lease or campaign.
disproven_routes: []
open_hypotheses:
  - A previous browser document remains bound as controller while a new document tries to generate points.
  - The browser loses or replaces its instance authority after lease acquisition.
  - The stale installed backend differs from the feature branch in a relevant boundary.
latest_checkpoint: CP-005
next_experiment: NONE
```

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: The browser document and server controller binding diverge between Acquire Lease and Generate Points.
working_tree_status: Mac feature worktree clean before this task-owned ledger; Linux feature worktree clean; ai-station main has unrelated untracked plan.
owned_processes: NONE
preserved_processes: Linux manager PID 2227775 on 100.104.202.119:8000 and all unrelated ROS/tmux processes; Mac campaign remains out of scope.
confirmed_conclusions:
  - Linux service Validation ready, IDLE, zero campaigns.
disproven_routes: []
open_risks:
  - A lease may exist without a campaign; no service restart until ownership is established.
next_command: Inspect the live page through Computer Use and record the authority/error transition.
```

```yaml
experiment_id: EXP-001
status: VALID
prior_experiment: NONE
hypothesis: Generate Points sends an instance ID different from the controller instance bound by Acquire Lease.
prediction: A fresh UI snapshot and server response identify two distinct instance IDs, with the first held by an earlier document or replaced in the current document.
single_variable: Reproduce the user's Acquire Lease to Generate Points sequence in one inspected browser document.
lifecycle: REUSE_STACK
preconditions:
  - Linux service PID 2227775, Validation ready, global IDLE, zero campaigns.
success_criteria:
  - Generate Points succeeds with a manifest and point chips.
failure_criteria:
  - Generate Points returns CONTROLLER_INSTANCE_MISMATCH and records the first divergent identity boundary.
invalid_criteria:
  - A campaign starts, the server PID changes, or another operator takes the lease during the reproduction.
provenance:
  source_commit: e04c4ff1c8c85c7eba566d6b1960c75b57234099
  install_overlay: /home/matianyi/Projects/ros-moveit-demo/install
  runtime_executable: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python
  ros_domain_id: 226
  gz_partition: so101-teleop-tailscale-ai-226
commands:
  - command: Computer Use visit http://100.104.202.119:8000/expert-validation; inspect state; Acquire Lease; Generate Points.
    exit_code: 0; both server mutations returned HTTP 409
observed:
  - Chrome displayed CONTROLLER_ALREADY_BOUND after Acquire Lease and CONTROLLER_INSTANCE_MISMATCH after Generate Points.
  - PID 2227775 log recorded the two HTTP 409 requests from 100.74.192.81.
  - Supervisor SQLite shows three EXPIRED leases, zero campaigns; /health reports global IDLE and Validation ready.
  - Multiple WebSocket clients remain connected; no active domain lease remains.
inferred:
  - An older document remains bound in InstanceRegistry memory after its lease expires. The registry intentionally refuses another instance until explicit handoff, operator recovery, or service restart.
conclusion: The reported UI error is reproduced at the controller binding boundary. Its prior owner has no active lease or campaign.
evidence:
  - /tmp/so101-debug-linux-controller-instance-20260924/generate-points-mismatch.png
decision: KEEP
next_experiment: EXP-002
```

```yaml
checkpoint_id: CP-002
last_valid_experiment: EXP-001
current_hypothesis: Replacing only the idle manager-owned service process will clear the obsolete in-memory controller binding, allowing a fresh document to acquire and generate points.
working_tree_status: Mac feature worktree has only this task-owned ledger; Linux feature worktree clean; ai-station main unrelated untracked plan preserved.
owned_processes: NONE
preserved_processes: Linux manager PID 2227775 until managed campaign guard and cleanup; all unrelated processes.
confirmed_conclusions:
  - EXP-001 reproduced the reported two-step 409 sequence with no active campaign and only expired leases.
disproven_routes:
  - Generate Points is the first rejected boundary; Acquire Lease is rejected earlier.
open_risks:
  - Restart disconnects read-only browser clients and requires a fresh document; their active lease has expired.
next_command: Run manager cleanup/start after a fresh campaign, lease, and PID ownership check; reload the page through Computer Use.
```

```yaml
experiment_id: EXP-002
status: VALID
prior_experiment: EXP-001
hypothesis: An idle service restart clears the stale in-memory controller binding without discarding supervisor history.
prediction: Manager cleanup stops only PID 2227775; a new manager PID serves the same endpoint; a fresh document acquires a lease and Generate Points succeeds.
single_variable: Replace the manager-owned Linux Web process while keeping the same installed code, configuration, evidence root, ROS domain, and Gazebo partition.
lifecycle: FULL_RESTART
preconditions:
  - PID 2227775 remains manager-owned, Validation ready, global IDLE, zero campaigns, and all leases expired.
success_criteria:
  - Fresh Acquire Lease and Generate Points succeed without controller mismatch; health stays Validation ready and no campaign starts.
failure_criteria:
  - Manager cleanup/start fails or the fresh page repeats either controller error.
invalid_criteria:
  - A campaign or live lease appears before cleanup, or another process takes port 8000.
provenance:
  source_commit: fd7348aa27361750f7e2e7954df53ef75e96545c
  install_overlay: /home/matianyi/Projects/ros-moveit-demo/install
  runtime_executable: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python
  ros_domain_id: 226
  gz_partition: so101-teleop-tailscale-ai-226
commands:
  - command: scripts/so101-teleop-linux.sh cleanup; scripts/so101-teleop-linux.sh start --install-prefix /home/matianyi/Projects/ros-moveit-demo/install --evidence-root /data/work/so101-evidence/teleop-service-restart/20260923-70919020
    exit_code: 0 cleanup; 2 first start from TIME_WAIT; 0 later start after TIME_WAIT cleared
  - command: Computer Use reload page, Acquire Lease, Generate Points.
    exit_code: 0 navigation; Acquire HTTP 200; Generate HTTP 409
observed:
  - Manager stopped PID 2227775 and started PID 2246459 on the same endpoint after transient TIME_WAIT port probe failures.
  - Fresh browser acquired lease HTTP 200; Generate Points no longer returned a controller identity error.
  - Generate Points returned VALIDATION_MANIFEST_INPUT_INVALID, with zero manifests persisted.
  - All seven installed demo resources required by the manifest reader are symlinks into the main source tree; manifest_geometry._read_inputs rejects symlinks by contract.
inferred:
  - Controller binding was in-memory stale state from prior document(s); restart removed that binding.
conclusion: Original controller mismatch cleared, but point generation remains blocked by a distinct installed-input provenance failure.
evidence:
  - /tmp/so101-debug-linux-controller-instance-20260924/cleanup.json
  - /tmp/so101-debug-linux-controller-instance-20260924/state-before.json
  - /data/work/so101-evidence/teleop-service-restart/20260923-70919020/service-20260923T164041Z.log
decision: KEEP
next_experiment: EXP-003
```

```yaml
checkpoint_id: CP-003
last_valid_experiment: EXP-002
current_hypothesis: Installing so101_demo_py as real files in an isolated overlay will satisfy the manifest input contract without changing product code or the existing main install.
working_tree_status: Mac feature worktree has only this task-owned ledger; Linux feature worktree clean; ai-station main unrelated untracked plan preserved.
owned_processes: Linux manager PID 2246459; the task browser currently owns a lease, so it must close and expire before another managed restart.
preserved_processes: All unrelated ROS/tmux processes and Mac service/campaign.
confirmed_conclusions:
  - EXP-001 confirmed the reported controller mismatch.
  - EXP-002 removed that mismatch with a managed restart; the next boundary is installed manifest inputs.
disproven_routes:
  - A restart alone makes Generate Points succeed.
open_risks:
  - The demo package has a dependency closure that must resolve under a fresh build base; the manager also expects a teleop package path under its chosen install prefix.
next_command: Verify the underlay and build an isolated non-symlink so101_demo_py install; link the unchanged teleop package into the overlay prefix only after inspecting its layout.
```

```yaml
experiment_id: EXP-003
status: VALID
prior_experiment: EXP-002
hypothesis: A copy-installed demo package provides immutable installed files accepted by manifest generation.
prediction: An isolated colcon install has no symlink in required manifest paths; manager doctor passes; after safe restart, a fresh browser Acquire Lease and Generate Points succeed and show P01 through P20.
single_variable: Change only the demo package install layout from symlinked main source resources to copied files from the current branch; keep the service code, config, models, domain, partition, and endpoint.
lifecycle: FULL_RESTART
preconditions:
  - PID 2246459 remains manager-owned; no campaign runs; task-owned lease is released or expired before cleanup.
success_criteria:
  - All required installed inputs are regular files; fresh Generate Points persists a 20-point manifest and shows P01 through P20 without controller or manifest-input errors.
failure_criteria:
  - Build/dependency closure, doctor, restart, or manifest generation fails.
invalid_criteria:
  - Another operator starts a campaign or changes the service installation during the attempt.
provenance:
  source_commit: e04c4ff1c8c85c7eba566d6b1960c75b57234099
  install_overlay: /data/work/so101-evidence/controller-instance-mismatch/20260924-e04c4ff1/install
  runtime_executable: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python
  ros_domain_id: 226
  gz_partition: so101-teleop-tailscale-ai-226
commands:
  - command: Build so101_demo_py without --symlink-install from the feature worktree into the task-owned overlay, then use manager doctor and a guarded restart.
    exit_code: 0 build, 0 doctor, 0 managed restart after TIME_WAIT cleared
  - command: Computer Use Acquire Lease and Generate Points on PID 2251037.
    exit_code: 0; both HTTP mutations succeeded
observed:
  - Copy install built so101_demo_py in 1.82 s; all ten checked manifest and execution configuration files are regular files with no symlink ancestor.
  - Manager doctor passed with task-owned overlay; manager stopped PID 2246459 and started PID 2251037 on the same endpoint.
  - Browser Generate Points enabled Check Resources and rendered the top-view map.
  - Supervisor SQLite contains manifest-6e5cac1019654cb7a3100f2426d4b158 with 20 points labeled P01 through P20; no campaign was created.
inferred:
  - The symlink install violated the intentional manifest input provenance contract; copy installation fixes that boundary.
conclusion: Generate Points works for the reported 20-point flow on Linux, with no controller mismatch or manifest-input error.
evidence:
  - /tmp/so101-debug-linux-controller-instance-20260924/colcon-demo-build.log
  - /tmp/so101-debug-linux-controller-instance-20260924/generate-points-success.png
  - /data/work/so101-evidence/teleop-service-restart/20260923-70919020/service-20260923T164715Z.log
decision: KEEP
next_experiment: EXP-004
```

```yaml
checkpoint_id: CP-004
last_valid_experiment: EXP-003
current_hypothesis: Building the feature-branch so101_teleop and so101_demo_py packages as copied files in a separate overlay can remove the still-stale main backend without regressing the now-working point generation.
working_tree_status: Mac feature worktree has only this task-owned ledger; Linux feature worktree clean; ai-station main unrelated untracked plan preserved.
owned_processes: Linux manager PID 2251037 on port 8000; task Chrome page has a live lease and must navigate away before restart.
preserved_processes: All unrelated ROS/tmux processes and Mac service/campaign.
confirmed_conclusions:
  - EXP-003 generated all 20 points from a copy-installed demo package.
  - The current teleop package path still resolves to main install, not feature source.
disproven_routes:
  - The symlink-installed demo files can satisfy manifest generation.
open_risks:
  - Linux has no Bun binary; a pinned, checksum-verified tool copy is needed for the teleop Web build.
next_command: Obtain Bun 1.3.14 from its official release into the task-owned durable root, build both packages into a separate copy install, and verify provenance before switching the service.
```

```yaml
experiment_id: EXP-004
status: VALID
prior_experiment: EXP-003
hypothesis: A full copy install from e04c4ff1 can serve the latest validation backend and retain successful point generation.
prediction: Official Bun 1.3.14 verifies its release SHA; both packages build into a separate prefix; three changed backend files match feature source; browser Acquire Lease and Generate Points still succeed after switch.
single_variable: Replace the mixed main teleop plus feature demo overlay with a fully copied e04c4ff1 overlay; keep endpoint, models, ROS domain, Gazebo partition, and service evidence root.
lifecycle: FULL_RESTART
preconditions:
  - PID 2251037 has no campaign and the task lease is expired before cleanup.
success_criteria:
  - Managed service uses copy-installed e04c4ff1 backend and demo resources; fresh browser generates 20 points; Validation stays ready.
failure_criteria:
  - Tool checksum, build, doctor, service start, backend provenance, or manifest generation fails.
invalid_criteria:
  - Another operator starts a campaign or changes the installation during the experiment.
provenance:
  source_commit: e04c4ff1c8c85c7eba566d6b1960c75b57234099
  install_overlay: /data/work/so101-evidence/controller-instance-mismatch/20260924-e04c4ff1/install-current
  runtime_executable: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python
  ros_domain_id: 226
  gz_partition: so101-teleop-tailscale-ai-226
commands:
  - command: Download pinned official Bun 1.3.14; verify SHA256 951ee2aee855f08595aeec6225226a298d3fea83a3dcd6465c09cbccdf7e848f; colcon build so101_teleop and so101_demo_py without symlink install.
    exit_code: 0 checksum, 0 build; remote direct download aborted after low throughput, verified Mac download copied to ai-station
  - command: Python -m pytest -q -n 8 for campaign layout, reducer, and production projection tests with isolated NVMe TMPDIR.
    exit_code: 0; 55 passed, 12 skipped in 6 seconds
  - command: Manager cleanup/start with install-current, Computer Use Acquire Lease and Generate Points, then close task document, let lease expire, and manager restart to clear its controller binding.
    exit_code: 0 for each manager action and both browser mutations
observed:
  - Bun 1.3.14 official Linux archive passed published SHA256; both packages built from an e04c4ff1-matched staged source in 31.3 seconds.
  - Installed campaign_layout.py, production.py, and reducer.py match e04c4ff1 source byte for byte; both Python packages import from install-current, and all seven manifest inputs are regular files.
  - Targeted pytest used 8 workers and /data/work/so101-evidence/controller-instance-mismatch/20260924-e04c4ff1/scratch/targeted-backend-e04c4ff1/tmp; 55 passed, 12 skipped.
  - Computer Use on the updated service returned HTTP 200 for Acquire Lease and Generate Points; manifest-d3ddfbe7f1244fc7905829fd549f50d0 contains exactly P01 through P20; the top-view map visibly shows the points.
  - After the test lease expired, manager restarted the same overlay to clear task controller state. Final PID 2260420 serves 100.104.202.119:8000 with Validation ready, global IDLE, zero campaigns, and zero active leases; the page is open read-only with Acquire Lease enabled.
inferred:
  - The final service is available for a different browser document to acquire; no task controller binding remains after the final restart.
conclusion: Latest branch code is deployed, and the reported Generate Points path works on Linux. The final service is healthy and unbound for the operator.
evidence:
  - /tmp/so101-debug-linux-controller-instance-20260924/colcon-current-build.log
  - /tmp/so101-debug-linux-controller-instance-20260924/targeted-backend-pytest.log
  - /tmp/so101-debug-linux-controller-instance-20260924/latest-generate-points-success.png
  - /tmp/so101-debug-linux-controller-instance-20260924/final-unbound-page.png
  - /data/work/so101-evidence/controller-instance-mismatch/20260924-e04c4ff1/targeted-backend-junit.xml
  - /data/work/so101-evidence/teleop-service-restart/20260923-70919020/service-20260923T170051Z.log
decision: KEEP
next_experiment: NONE
```

```yaml
checkpoint_id: CP-005
last_valid_experiment: EXP-004
current_hypothesis: NONE
working_tree_status: Mac feature worktree has this task-owned ledger only; Linux feature worktree clean; ai-station main unrelated untracked plan preserved.
owned_processes: Linux manager PID 2260420 on 100.104.202.119:8000 using install-current.
preserved_processes: Mac service/campaign and all unrelated ROS/tmux processes.
confirmed_conclusions:
  - EXP-001 identified the stale controller binding and reproduced the reported mismatch.
  - EXP-002 cleared that binding, exposing a separate symlink-installed manifest input failure.
  - EXP-003 proved a copied demo install generates 20 points.
  - EXP-004 deployed the full e04c4ff1 overlay and repeated a successful 20-point browser generation; final service is unbound and healthy.
disproven_routes:
  - A process restart alone can make a symlink-installed demo package generate points.
open_risks:
  - Refreshing or replacing the controller browser document after acquiring may require a managed service restart under the intentional exclusive-instance contract; do not restart an active campaign.
  - The page currently reports EXACT_N_UNQUALIFIED and BUDGET_PROFILE_UNAVAILABLE; Check Resources/Start Validation were outside this Generate Points repair.
  - Full-module eight-worker pytest and full package CTest gates were not run in this deployment task; targeted 8-worker tests passed.
retained_runs:
  - /data/work/so101-evidence/controller-instance-mismatch/20260924-e04c4ff1
  - /data/work/so101-evidence/teleop-service-restart/20260923-70919020
archived_runs: NONE
deletion_candidates:
  - /data/work/so101-evidence/controller-instance-mismatch/20260924-e04c4ff1/scratch/targeted-backend-e04c4ff1/tmp after readback.
  - /data/work/so101-evidence/controller-instance-mismatch/20260924-e04c4ff1/tools/bun-linux-x64-incomplete.zip after readback.
  - The superseded install/ and build/ directories within the task-owned durable root after readback; install-current remains in use and is retained.
  - /tmp/so101-debug-linux-controller-instance-20260924 on both hosts after readback.
next_command: Operator may open http://100.104.202.119:8000/expert-validation, acquire a lease, and generate points in one browser document.
```
