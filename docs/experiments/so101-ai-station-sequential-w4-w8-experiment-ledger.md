# ai-station Expert Validation: SEQUENTIAL, W4, W8

```yaml
task_id: so101-ai-station-sequential-w4-w8-20260924
goal: Use Computer Use to complete one full simulated Expert Validation campaign each in SEQUENTIAL, PARALLEL W4, and PARALLEL W8 on ai-station, fixing encountered defects at their first failing boundary.
success_contract: Three separate 20-point campaigns, each terminal with all P01-P20 executed exactly once, qualification and cleanup true, independent outcome evidence, fresh UI readback, and no owned process residue.
worktree: /Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp
branch: codex/so101-unified-webapp
base_commit: dad92c8859b8c83135fbc8c8698e29df4e863d65
current_commit: dad92c8859b8c83135fbc8c8698e29df4e863d65
evidence_root: /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88
confirmed_conclusions:
  - Computer Use SEQUENTIAL campaign-7073fffd432d402d8bc641927095543b, W4 campaign-08ff66872bdd41deb7e5325b9a98c56f, and W8 campaign-4578dccaadb14d1e84f3552ac0fd62ef each completed 20/20 first pass with qualification and cleanup true.
  - All 60 point attempts are uniquely sealed PASSED with initial/terminal RGB, physical numeric and dynamic manifests present. Fresh terminal browser screenshots are retained for all three modes.
  - Installed Linux v5 service PID 2869092 remains available on 100.104.202.119:8000; no batch owner, ROS or Broker container remains.
disproven_routes:
  - An obsolete browser exact-N budget qualification check cannot govern Linux configured W4/W8 admission; fresh StartGuard does.
  - Repeating an uninstrumented failed W4 cannot identify the first physical monitor trigger because later recovery samples overwrite terminal evidence.
open_hypotheses:
  - Intermittent force/table-contact monitor aborts seen in failed W4 attempts did not recur after primary-trigger capture was added; their physical cause remains unconfirmed and the safety thresholds were not changed.
latest_checkpoint: CP-009
next_experiment: NONE
```

## EXP-000 — Read-only recovery

```yaml
experiment_id: EXP-000
status: VALID
prior_experiment: NONE
hypothesis: The installed ai-station service is idle and the browser can safely begin a fresh validation task after provenance and budget checks.
prediction: Health reports IDLE, campaigns empty, no active lease or stack, and the served install matches the inspected source.
single_variable: NONE
lifecycle: REUSE_STACK
preconditions:
  - Read-only process, status, worktree, and installed-artifact inspection.
success_criteria:
  - Unowned stack absent; service and code provenance identified.
failure_criteria:
  - Active campaign or unowned stack present.
invalid_criteria:
  - Incomplete process or service readback.
provenance:
  source_commit: e04c4ff1
  install_overlay: /data/work/so101-evidence/controller-instance-mismatch/20260924-e04c4ff1/install-current
  runtime_executable: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python
  ros_domain_id: 226
  gz_partition: so101-teleop-tailscale-ai-226
commands:
  - command: read-only health, campaign, process and worktree inspection from prior checkpoint
    exit_code: 0
observed:
  - Existing manager PID 2260420 serves port 8000 on 100.104.202.119; health IDLE, campaigns empty; no Gazebo, MoveIt, RViz or stack process observed.
  - Capability response showed exact-N budget provider unknown, reason BUDGET_PROVIDER_NOT_READY.
inferred:
  - A fresh campaign can be attempted after confirming no active browser lease and resolving qualification guards.
conclusion: VALID for idle/provenance preflight; no campaign success is inferred.
evidence:
  - /data/work/so101-evidence/teleop-service-restart/20260923-70919020
decision: KEEP
next_experiment: EXP-001
```

## EXP-001 — Production admission preflight

```yaml
experiment_id: EXP-001
status: VALID
prior_experiment: EXP-000
hypothesis: Fresh UI and API readback will identify the first actual admission blocker before any campaign is launched.
prediction: The budget provider or a separate resource probe reports a precise guard reason for each mode; no motion starts.
single_variable: Fresh browser authority and resource admission readback.
lifecycle: REUSE_STACK
preconditions:
  - Current service remains idle, no campaign or lease, source and install provenance verified.
success_criteria:
  - UI and API agree on mode-specific availability and the first failing boundary is identified.
failure_criteria:
  - Resource or budget admission fails with a reproducible reason.
invalid_criteria:
  - Stale browser lease, mismatched controller instance, or unowned stack makes readback uninterpretable.
provenance:
  source_commit: e04c4ff1
  install_overlay: /data/work/so101-evidence/controller-instance-mismatch/20260924-e04c4ff1/install-current
  runtime_executable: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python
  ros_domain_id: 226
  gz_partition: so101-teleop-tailscale-ai-226
commands:
  - command: scripts/so101-teleop-linux.sh cleanup (old managed service) then start --install-prefix /data/work/so101-evidence/controller-instance-mismatch/20260924-e04c4ff1/install-current --python /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python --evidence-root /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88 --state-dir /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88/service-state
    exit_code: 0
  - command: Computer Use Chrome snapshot, Acquire Lease, Generate Points, Check Resources for SEQUENTIAL and parallel exact N
    exit_code: 0
observed:
  - Old idle managed PID 2260420 stopped with STOPPED receipt; initial start met a transient TIME_WAIT bind conflict, then new managed PID 2465582 started successfully at this task's root.
  - Linux v3 capabilities report W2-W8 CONFIGURED/selectable but obsolete worker_qualifications remain UNKNOWN; source start path does not consult that legacy budget adapter.
  - Computer Use acquired the fresh lease, generated 20 catalog points, and SEQUENTIAL Check resources reported Preflight passed with StartGuard PASS: GPU free 15.2 GiB, RAM free 27.8 GiB, CPU busy 1.6%.
inferred:
  - Sequential campaign can proceed through the guarded start; W4/W8 browser selection needs the demonstrated UI fix and a fresh preflight.
conclusion: VALID preflight; no execution or physical outcome claimed.
evidence:
  - /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88
decision: KEEP
next_experiment: EXP-002
```

## EXP-002 — Full 20-point SEQUENTIAL campaign

```yaml
experiment_id: EXP-002
status: VALID
prior_experiment: EXP-001
hypothesis: The guarded CUDA v3 sequential execution can complete the full catalog on one isolated simulated worker.
prediction: P01-P20 each terminate PASSED once, the coordinator records coverage/execution/qualification/cleanup true, and no worker/container/GPU residue remains.
single_variable: Start one full SEQUENTIAL 20-point campaign from the passed preflight.
lifecycle: REUSE_STACK
preconditions:
  - Service PID 2465582 on 100.104.202.119:8000 is managed in the registered root; no active campaign or unowned stack.
  - Fresh lease, 20-point manifest, StartGuard PASS, CUDA v3 installed configuration, simulation only.
success_criteria:
  - All 20 point IDs exactly once PASSED with independent physical and visual evidence, full coverage, qualification and cleanup receipts, no residue.
failure_criteria:
  - Any valid point failure, stuck task, incomplete cleanup, or inconsistent physical outcome.
invalid_criteria:
  - Browser authority mismatch, stale preflight receipt, source/install mismatch, or unowned process collision.
provenance:
  source_commit: e04c4ff1
  install_overlay: /data/work/so101-evidence/controller-instance-mismatch/20260924-e04c4ff1/install-current
  runtime_executable: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python
  ros_domain_id: 226
  gz_partition: so101-teleop-tailscale-ai-226
commands:
  - command: Computer Use click Start validation for SEQUENTIAL, worker_count 1, P01-P20
    exit_code: 0
observed:
  - Computer Use started campaign-50e9808dcad14518ae87c933b49790e7 with manifest-b47007e8b27c49d98b65799cd183ef44 and batch b7522. Initial API status STARTED, 20 points UNRUN while coordinator starts.
  - Coordinator log returned PROVENANCE_BROKER_IMAGE_READBACK, caused by Docker reporting no such image for so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1. No coordinator, Worker or Broker process remains and no point attempt or journal was created; UI/API projection remains STARTED.
inferred:
  - Docker image absence is the first failing execution boundary; StartGuard was not a substitute for immutable image provenance.
conclusion: VALID failed execution admission. Zero points ran and this campaign does not satisfy the user request; recovery and a new campaign are required.
evidence:
  - /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88
decision: REPEAT
next_experiment: EXP-003
```

## EXP-003 — Restore immutable CUDA Broker image

```yaml
experiment_id: EXP-003
status: VALID
prior_experiment: EXP-002
hypothesis: Building the frozen combined Broker image from the exact installed demo package source will satisfy image readback without changing model or execution config.
prediction: The image build writes a verified immutable image ID, labels and in-image provenance matching the source, Dockerfile and pinned dependency hashes.
single_variable: Presence of the provenance-verified Broker image on ai-station.
lifecycle: REUSE_STACK
preconditions:
  - Docker daemon reachable, no active campaign Worker/Coordinator/Broker process or container, source package clean, at least 1.7 TB free storage.
success_criteria:
  - Build command exits zero; image_record succeeds; image ID and source/lock/Dockerfile hashes match independent readback.
failure_criteria:
  - Build, dependency, image provenance, or readback fails.
invalid_criteria:
  - A stale image/output path or source diff changes the frozen input during build.
provenance:
  source_commit: dad92c8859b8c83135fbc8c8698e29df4e863d65
  install_overlay: /data/work/so101-evidence/controller-instance-mismatch/20260924-e04c4ff1/install-current
  runtime_executable: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python
  ros_domain_id: 226
  gz_partition: so101-teleop-tailscale-ai-226
commands:
  - command: scripts/parallel-perception-container.sh build --image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1 --output /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88/broker-image-build.json
    exit_code: 0
observed:
  - Build from clean demo source exited zero. Docker image ID sha256:ab421f0393409ec956fc7f017b6f4f2a53cbb170d311cb45aef13b75840ae629; source c631badcd1a6d49f71f71285db6cc0bb3ab7c35499882cc7d0b24f03f91f251d; Dockerfile 54f385874d8ace0bce7b31832f0345ce3f8f32cfb91e6506775572bc40582ec5; lock 90f7f5983d806e4f78f50eb45c411b0a1a0e62201aca6b1f3afade962604fa5f. Docker inspect labels match receipt.
  - New browser bundle passed 302 Web tests and production build, then was staged in this root and hot loaded at port 8000; Computer Use selected PARALLEL W4 and showed CONFIGURED with resource check required.
  - Targeted operator recovery regression was RED for schema-v3 nested execution.ros_domain_ids, then GREEN with 65 tests at -n 8 after source fix; scratch roots are retained.
inferred:
  - The image absence blocker is removed. A new campaign must still pass fresh preflight and runtime execution.
conclusion: VALID image provenance repair and UI/recovery-code checks; no campaign success claimed.
evidence:
  - /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88/broker-image-build.log
  - /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88/broker-image-build.json sha256=3177acc0610c503200120a61fff646b4602885b8aa1d208a1586e9c61e300ceb
  - /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88/operator-recovery-green.xml
decision: KEEP
next_experiment: EXP-004
```

## EXP-004 — Audited recovery of the pre-journal failed campaign

```yaml
experiment_id: EXP-004
status: VALID
prior_experiment: EXP-002
hypothesis: The first coordinator exited before journal creation with no owned descendants, container or GPU workload, so an offline aborted recovery can preserve the failure and release the stale service authority.
prediction: Strict process/container/domain inspection finds no owned execution; a target-identity SIGTERM stops only the managed Web service; the offline recovery preview and apply prove absence and retain an OPERATOR_RECOVERED_ABORTED receipt without claiming execution or upstream cleanup.
single_variable: Recover the failed pre-journal campaign's owner state after immutable image restoration.
lifecycle: FULL_RESTART
preconditions:
  - Docker image build receipt valid; campaign-50e9808dcad14518ae87c933b49790e7 has zero point attempts, coordinator PID 2466672 absent, no batch container or GPU process, and manager cleanup refuses only because the Web projection remains STARTED.
success_criteria:
  - Exact managed service PID verified before signal, offline fence and recovery receipt valid, no historical execution success/cleanup claim, fresh service can acquire authority and preflight.
failure_criteria:
  - Any owned runtime remains, recovery preview refuses, service identity differs, or receipt cannot be verified.
invalid_criteria:
  - Unrelated process killed, service DB modified while live, or stale config hash supplied to recovery.
provenance:
  source_commit: e04c4ff1
  install_overlay: /data/work/so101-evidence/controller-instance-mismatch/20260924-e04c4ff1/install-current
  runtime_executable: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python
  ros_domain_id: 226
  gz_partition: so101-teleop-tailscale-ai-226
commands:
  - command: Verify exact managed PID and batch absence, send SIGTERM only to verified service PID, then run manager cleanup to mark ALREADY_EXITED.
    exit_code: 0
  - command: Offline SupervisorStore.record_recovery_fence followed by operator_recovery preview and apply for campaign-50e9808dcad14518ae87c933b49790e7 with exact v3 config.
    exit_code: 0
observed:
  - Audited managed PID 2465582 identity, coordinator PID 2466672 absence, empty batch container list, no NVIDIA compute process, and no owned execution descendants. Sent SIGTERM only to verified managed service; manager cleanup reported ALREADY_EXITED.
  - Offline recovery fence recorded reason COORDINATOR_EXITED_BEFORE_JOURNAL_PROVENANCE_BROKER_IMAGE_READBACK for batch b7522. Recovery preview verified ROS domains 181-188 clear and no process/group/container; apply returned OPERATOR_RECOVERED_ABORTED with execution_success=false and upstream_cleanup_claimed=false.
  - A fresh colcon build attempt stopped at CLI parsing because --log-base was placed after the build verb; no package boundary ran. Corrected invocation puts the global argument before build.
inferred:
  - Historical failure remains auditable, and its stale owner fence is released for a new service.
conclusion: VALID recovery with no execution or upstream cleanup claim; the original campaign remains failed.
evidence:
  - /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88/validation-service/operator-recovery
decision: KEEP
next_experiment: EXP-005
```

## EXP-005 — Fresh installed overlay and complete SEQUENTIAL campaign

```yaml
experiment_id: EXP-005
status: VALID
prior_experiment: EXP-004
hypothesis: A fresh overlay carrying the UI and recovery fixes plus the rebuilt Broker image permits a full 20-point SEQUENTIAL simulated campaign.
prediction: Computer Use generates P01-P20, fresh StartGuard passes, all points terminate exactly once with success evidence and complete cleanup.
single_variable: New installed source overlay after the audited aborted campaign.
lifecycle: FULL_RESTART
preconditions:
  - Service stopped and old owner recovered; fresh overlay build and doctor checks pass; immutable image readback valid.
success_criteria:
  - P01-P20 each PASSED exactly once, qualification/coverage/execution/cleanup true, independent outcome evidence, fresh UI terminal readback, no owned process residue.
failure_criteria:
  - Any valid point failure, stuck execution, or incomplete cleanup.
invalid_criteria:
  - Unowned stack, stale lease, or source/install mismatch.
provenance:
  source_commit: dad92c8859b8c83135fbc8c8698e29df4e863d65 plus task-local fixes
  install_overlay: /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88/install-v2
  runtime_executable: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python
  ros_domain_id: 226
  gz_partition: so101-teleop-tailscale-ai-226
commands:
  - command: colcon --log-base <root>/colcon-v2 build --base-paths src --packages-select so101_teleop so101_demo_py --allow-overriding so101_teleop so101_demo_py --build-base <root>/build-v2 --install-base <root>/install-v2
    exit_code: 0
  - command: scripts/so101-teleop-linux.sh doctor then start from install-v2
    exit_code: 0
  - command: Computer Use Chrome Acquire lease, Generate points count 20, Check resources SEQUENTIAL, Start validation
    exit_code: 0
observed:
  - New install contains Web bundle index-DVHlV5HV.js; doctor READY; managed service PID 2490331 on 100.104.202.119:8000.
  - Computer Use fresh StartGuard PASS: CPU 0.0%, 32 cores, GPU free 15.2 GiB, RAM free 27.7 GiB. Started campaign-7073fffd432d402d8bc641927095543b, manifest-4538606903b84e6b8b11c47b62eee4e2, batch be9ab. API now RUNNING with one available worker and 20 requested points.
  - Final API and aggregate report both show COMPLETED, requested/evaluated/execution_started/valid_succeeded 20/20/20/20, 0 failed, 0 indeterminate, coverage_complete/execution_complete/batch_cleanup_complete/qualification_passed true. Twenty sealed attempt manifests have 20 unique point IDs and status PASSED; all aggregate point attempts equal 1.
  - ai-station process, Docker and NVIDIA readback shows no batch be9ab worker, coordinator, Broker, container or compute process. Computer Use had shown RUNNING 2/20 with matching backend; at terminal its local native pipe stopped working, so terminal UI screenshot is unavailable while terminal API/aggregate readback is complete.
inferred:
  - This is a complete first-pass SEQUENTIAL campaign with independently sealed per-point evidence and cleanup.
conclusion: VALID complete SEQUENTIAL campaign; terminal UI readback limitation is recorded separately.
evidence:
  - /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88
decision: KEEP
next_experiment: EXP-006
```

## EXP-006 — Complete PARALLEL W4 campaign

```yaml
experiment_id: EXP-006
status: VALID
prior_experiment: EXP-005
hypothesis: Four independent simulated workers can complete the same 20-point catalog with unique leases and full cleanup after a fresh guarded start.
prediction: Computer Use selects PARALLEL W4, fresh StartGuard passes, P01-P20 each terminate PASSED exactly once with independent physical and visual evidence.
single_variable: Worker count 4 and PARALLEL execution mode.
lifecycle: FULL_RESTART
preconditions:
  - EXP-005 terminal and cleanup complete; no owned process/container/domain residue; new browser lease and manifest.
success_criteria:
  - 20 unique points PASSED, four worker identities observed, coverage/execution/qualification/cleanup true, browser terminal readback and no residue.
failure_criteria:
  - Valid point failure, duplicate lease, missing evidence, resource exhaustion, stuck execution, or incomplete cleanup.
invalid_criteria:
  - Unowned stack or stale authority/source prevents meaningful W4 readback.
provenance:
  source_commit: dad92c8859b8c83135fbc8c8698e29df4e863d65 plus task-local fixes
  install_overlay: /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88/install-v2
  runtime_executable: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python
  ros_domain_ids: [181, 182, 183, 184]
commands:
  - command: Audited exact old managed service PID 2490331 and batch absence, SIGTERM, manager cleanup ALREADY_EXITED, doctor READY, new managed start PID 2533810.
    exit_code: 0
  - command: Browser Computer Use retry and Chrome plugin discovery; both unavailable due Sky native pipe startup failure and no browser surface.
    exit_code: 1
  - command: Equivalent live instance WebSocket authority, lease, 20-point manifest, W4 preflight and campaign start over production API; control channel and renewal held open.
    exit_code: 0
observed:
  - Initial unauthenticated API lease was correctly refused CONTROLLER_INSTANCE_REQUIRED; the live instance channel and four authority headers resolved it without bypassing admission.
  - Fresh W4 StartGuard/admission passed, started campaign-23fa930b12d840ed9b0fc8ee050e47e3, batch b7184. All four distinct workers reached EXECUTING on four distinct points. GPU used 4.1 GiB and RAM available 20 GiB during initial execution.
  - Nineteen points PASSED and P18 sample_14_far_right became INDETERMINATE. MoveIt rejected MOVE_ABOVE_PLACE from joint 4 observed at 1.65808 rad while the URDF upper limit is 1.65806 rad; the preceding LIFT IK target was exactly 1.65806 rad. The controller overshoot was about 0.00002 rad. The point has a working evidence tree, not a sealed PASSED result.
  - Coordinator ended with batch_cleanup_complete=false after worker-04 ros2_control_node aborted during recovery. API projection remains CLEANING_UP, and no batch Coordinator/Broker/container is still running. Cleanup gates report process and container cleanup succeeded, coordinator completion unattempted.
  - Regression test for exact-limit IK was RED (2 failed, 2 passed) under pytest -n 8. A 0.002 rad interior IK solve margin built into install-v3 and the adjacent horizon test gate are GREEN (8 passed under -n 8). Source revision requires a new frozen Broker image build and a fresh W4 campaign.
  - Rebuilt frozen Broker image for the changed demo source: image sha256:f20ad426df954f7813eefa6037214065a5da64de52cb869ed62254f6097d6a65, source hash f52f12de2bfa0abbd6653bd8eb47f5c72c2e355bcd63a628bacd1950132aabce. Build receipt sha256 d49a06b322cd42ccb01f4580c96a073015e22ac868cb8a31312234f98acf3f20.
  - Audited coordinator PID 2536434, batch descendants, Broker/container and ROS domains absent; stopped exact managed Web service PID 2533810. Offline recovery preview verified domains 181-188 clear and no owner process/group/container, then apply returned OPERATOR_RECOVERED_ABORTED with execution_success=false, upstream_cleanup_claimed=false and no signals sent.
inferred:
  - The exact joint-limit target leaves no controller tracking margin and caused the P18 planning refusal. No claim of W4 success or cleanup is valid for this batch.
conclusion: VALID failed W4 run with first boundary MOVEIT_PLAN_FAILED at the joint-4 limit; preserve and recover offline before repeat.
evidence:
  - /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88
decision: REPEAT
next_experiment: EXP-008
```

## EXP-008 — Repeat complete PARALLEL W4 with joint margin

```yaml
experiment_id: EXP-008
status: VALID
prior_experiment: EXP-006
hypothesis: The 0.002 rad interior IK margin prevents a controller from reporting a start state just outside the URDF bound during a later MoveIt segment, allowing all 20 W4 points to finish first pass.
prediction: Fresh install-v3 plus matching Broker image, audited recovery, and guarded W4 admission yield 20 distinct PASSED points and full cleanup.
single_variable: IK target margin in the fresh installed demo source.
lifecycle: FULL_RESTART
preconditions:
  - EXP-006 coordinator and all owners absent; offline aborted recovery receipt; install-v3 and matching image provenance; fresh service/controller authority.
success_criteria:
  - Twenty unique sealed PASSED results, 4 worker identities, coverage/execution/qualification/cleanup true and no owned residue.
failure_criteria:
  - Any valid point failure, indeterminate result, stuck cleanup, or residue.
invalid_criteria:
  - Stale controller authority, installed source/image mismatch, or unowned stack.
provenance:
  source_commit: dad92c8859b8c83135fbc8c8698e29df4e863d65 plus task-local fixes
  install_overlay: /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88/install-v3
  runtime_executable: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python
  ros_domain_ids: [181, 182, 183, 184]
commands:
  - command: scripts/so101-teleop-linux.sh doctor then start with install-v3 and matching Broker image
    exit_code: 0
  - command: Fresh live instance WebSocket authority, 20-point manifest, guarded W4 preflight and campaign start through production API because Computer Use bridge remains unavailable
    exit_code: 0
observed:
  - Managed service PID 2583296; installed IK module readback CONTROL_JOINT_MARGIN_RAD=0.002 from install-v3, image sha256:f20ad426df954f7813eefa6037214065a5da64de52cb869ed62254f6097d6a65 with matching source label.
  - Fresh W4 preflight admitted and started campaign-3622c548fd584b5099fd1166a9f4bb4c, batch b9eea.
  - Terminal API and aggregate report show COMPLETED with requested/evaluated/execution_started/valid_succeeded 20/20/20/20, 0 failed, 0 indeterminate, and coverage_complete/execution_complete/batch_cleanup_complete/qualification_passed true.
  - All 20 sealed attempt manifests have unique point IDs and PASSED status. P18 sample_14_far_right has exactly one PASSED attempt. Worker-01 through worker-04 all STOPPED; batch Coordinator, Broker, container and GPU compute process absent on readback.
inferred:
  - The interior IK margin removed the observed exact-limit planning refusal in this full W4 run.
conclusion: VALID complete W4 first-pass campaign with full cleanup.
evidence:
  - /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88
decision: KEEP
next_experiment: EXP-007
```

## EXP-007 — Complete PARALLEL W8 campaign

```yaml
experiment_id: EXP-007
status: VALID
prior_experiment: EXP-008
hypothesis: Eight independent simulated workers can complete the same 20-point catalog with unique leases and full cleanup after a fresh guarded start.
prediction: Computer Use selects PARALLEL W8, fresh StartGuard passes, P01-P20 each terminate PASSED exactly once with independent physical and visual evidence.
single_variable: Worker count 8.
lifecycle: FULL_RESTART
preconditions:
  - EXP-006 terminal and cleanup complete; no owned process/container/domain residue; new browser lease and manifest.
success_criteria:
  - 20 unique points PASSED, eight worker identities observed, coverage/execution/qualification/cleanup true, browser terminal readback and no residue.
failure_criteria:
  - Valid point failure, duplicate lease, missing evidence, resource exhaustion, stuck execution, or incomplete cleanup.
invalid_criteria:
  - Unowned stack or stale authority/source prevents meaningful W8 readback.
provenance:
  source_commit: dad92c8859b8c83135fbc8c8698e29df4e863d65 plus task-local fixes
  install_overlay: /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88/install-v3
  runtime_executable: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python
  ros_domain_ids: [181, 182, 183, 184, 185, 186, 187, 188]
commands:
  - command: Audited exact managed service PID 2583296 and prior terminal W4, stopped only that PID, manager cleanup ALREADY_EXITED, doctor READY for install-v3.
    exit_code: 0
  - command: Fresh live instance W8 preflight and start through production API, followed by terminal aggregate and 20 sealed-attempt readback.
    exit_code: 0
  - command: Computer Use browser refresh and terminal campaign readback after its native pipe recovered.
    exit_code: 0
observed:
  - Initial new start reached transient TIME_WAIT PORT_UNAVAILABLE on 100.104.202.119:8000; no process owns the port. Waiting for kernel socket expiry before retry.
  - Managed install-v3 service restarted as PID 2619374 after TIME_WAIT expiry. Fresh W8 production preflight admitted; started campaign-0d9f0c890af0460a877c2cc23180afab, batch ba697, through live instance WebSocket authority with continued lease renewal.
  - Terminal aggregate reports COMPLETED, requested/evaluated/execution_started/valid_succeeded 20/20/20/20, zero failed or indeterminate; coverage, execution, batch cleanup and qualification are true.
  - All 20 sealed attempt manifests are unique PASSED with one attempt each, including P18. Eight workers STOPPED; no owned batch process, container or GPU compute process remained.
  - Restored Computer Use Chrome readback shows PARALLEL COMPLETED, 20 first-pass valid, zero failed/indeterminate/unrun and eight STOPPED workers. Screenshot w8-terminal-ui.png was copied into the task evidence root.
  - P18 initial and terminal RGB frames differ; final dynamic Gazebo sample records cup position [-0.0789186752, -0.2473311945, 0.1649215639], stable table contact and zero fingertip contacts after release.
inferred:
  - The repaired IK and worker isolation held under eight concurrent simulated workers in this campaign.
conclusion: VALID complete W8 first-pass campaign with full cleanup and fresh Computer Use terminal readback; campaign start used the production API during the Computer Use outage.
evidence:
  - /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88
decision: KEEP
next_experiment: EXP-009
```

## EXP-009 — Computer Use launch of a fresh W4 campaign

```yaml
experiment_id: EXP-009
status: VALID
prior_experiment: EXP-007
hypothesis: With the Computer Use bridge restored, a fresh browser authority can launch and observe a complete W4 campaign through the actual UI.
prediction: After an audited service restart clears the old controller binding, UI lease, 20-point generation, W4 resource check and start succeed; 20 points pass once and all owners stop.
single_variable: Browser-driven W4 campaign instead of the prior production API start.
lifecycle: FULL_RESTART
preconditions:
  - EXP-007 terminal and cleanup true; no batch owner residue; exact service PID and install provenance verified.
success_criteria:
  - UI start and terminal readback, 20 unique sealed PASSED attempts, qualification and cleanup true, no owned residue.
failure_criteria:
  - UI admission error, failed point, duplicate lease, incomplete cleanup, or unowned residue.
invalid_criteria:
  - Stale authority or unrelated stack makes the run uninterpretable.
provenance:
  source_commit: dad92c8859b8c83135fbc8c8698e29df4e863d65 plus task-local fixes
  install_overlay: /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88/install-v3
  runtime_executable: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python
  ros_domain_ids: [181, 182, 183, 184]
  gz_partition: so101-teleop-tailscale-ai-226
commands:
  - command: Audited manager status and exact PID 2619374; manager cleanup refused CAMPAIGN_STATUS_UNKNOWN after the large campaign-list response timed out. Independently read all five campaign summaries and audited no live batch owner; sent SIGTERM only to PID 2619374, then manager cleanup returned ALREADY_EXITED and install-v3 doctor READY.
    exit_code: 0
  - command: Managed start from install-v3 with this task's evidence root and state directory.
    exit_code: 2
  - command: Managed start retried after TIME_WAIT expired; Computer Use chose PARALLEL / 4, acquired lease, generated 20 points, ran Check resources and clicked Start validation.
    exit_code: 0
observed:
  - Previous failed campaigns remain NEEDS_OPERATOR_RECOVERY with incomplete aggregate cleanup but offline operator recovery receipts and no live owner; they are not counted as successes.
  - First restart attempt hit TIME_WAIT PORT_UNAVAILABLE on Tailscale 8000; ss showed only TIME-WAIT sockets, no listener. Browser navigated to about:blank through Computer Use to stop old projection polling while the socket expires.
  - Managed install-v3 service restarted as PID 2678292. Fresh Computer Use W4 StartGuard PASS: CPU busy 4.4%, 32 cores, GPU free 14.8 GiB, RAM free 26.7 GiB. UI started campaign-4fcfc0cd27044de5a855f9017b4e2db6; it reached RUNNING with four workers and 20 requested points.
  - In batch b65ce P03 cup_test_left_5cm became INDETERMINATE. Its working dynamic manifest reports MOVEIT_EXECUTION_MONITOR_ABORTED / DYNAMIC_FORCE_LIMIT_EXCEEDED at MOVE_ABOVE_PLACE, with physical action not proven absent; controller cancellation and revocation were recorded. Computer Use shows P03 INDETERMINATE and no committed evidence.
  - A/B with prior complete W4 batch b9eea: P03 input pose and resolved target are identical; post-LIFT contact force is 0.535 N versus 0.536 N. The new run diverged during MOVE_ABOVE_PLACE, so the browser request itself has no demonstrated causal link. The 11.60 N force guard remains unchanged pending stronger contact evidence.
  - Browser projection reached CLEANING_UP after all 20 points started: 19 PASSED, P03 INDETERMINATE, no unrun point. Worker-02 was QUARANTINED; aggregate has execution_complete=true, coverage_complete=false, batch_cleanup_complete=false, qualification_passed=false and terminal_reason POINTS_COMPLETE. Coordinator and batch processes are absent on readback.
inferred:
  - The force-monitor trip is isolated to P03 in this run; full W4 qualification cannot be claimed. No evidence yet distinguishes transient physics contact from a reproducible trajectory issue.
conclusion: VALID failed browser-driven W4 experiment with safe motion cancellation and incomplete upstream cleanup; preserve evidence and use offline operator recovery before a fresh A/B run.
evidence:
  - /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88
decision: REPEAT
next_experiment: EXP-010
```

## EXP-010 — Offline recovery after the W4 force trip

```yaml
experiment_id: EXP-010
status: VALID
prior_experiment: EXP-009
hypothesis: The failed W4 coordinator and every batch owner have exited; an offline audited abort can release the stale owner fence without claiming cleanup or success.
prediction: The recovery preview proves recorded owner PID/group/container and ROS domains absent; apply records OPERATOR_RECOVERED_ABORTED with no signals and no upstream cleanup claim.
single_variable: Offline operator recovery of campaign-4fcfc0cd27044de5a855f9017b4e2db6 / batch b65ce.
lifecycle: FULL_RESTART
preconditions:
  - Preserve failed UI and batch evidence; verify exact managed service PID, no batch owner/container/GPU process and correct config bytes; stop only the managed Web PID.
success_criteria:
  - Recovery preview and apply pass; receipt is durable, execution_success=false and upstream_cleanup_claimed=false.
failure_criteria:
  - Any owner remains, config mismatch, or recovery receipt cannot be verified.
invalid_criteria:
  - Service still online or unrelated process ownership ambiguous.
provenance:
  source_commit: dad92c8859b8c83135fbc8c8698e29df4e863d65 plus task-local fixes
  install_overlay: /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88/install-v3
  runtime_executable: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python
  ros_domain_ids: [181, 182, 183, 184]
  gz_partition: so101-teleop-tailscale-ai-226
commands:
  - command: Computer Use preserved failed W4 projection and navigated to about:blank; audited exact managed PID 2678292, no batch process/container/GPU owner; sent SIGTERM to that PID only and manager cleanup returned ALREADY_EXITED.
    exit_code: 0
  - command: Offline SupervisorStore.record_recovery_fence for campaign-4fcfc0cd27044de5a855f9017b4e2db6 / b65ce, followed by installed operator recovery preview and apply with byte-matched v3 config.
    exit_code: 0
observed:
  - Recovery preview proved batch container absent, leader and process group 2681753 absent, ROS domains 181-188 clear. Exact config SHA256 991b5c1b4fbd0cc1f0a97bd20a5b5a4e02028634f3f4ef288ad87554b383ab70 matched preflight.
  - Apply recorded OPERATOR_RECOVERED_ABORTED for the failed W4 with execution_success=false, upstream_cleanup_claimed=false and signals_sent=[]. Backup, probe and config copies remain under validation-service/operator-recovery/operator-recovery-4fcfc0cd-20260924.
inferred:
  - The stale owner fence is released; the physical safety failure and absent upstream cleanup remain historical facts.
conclusion: VALID audited abort recovery; no W4 success or cleanup is inferred.
evidence:
  - /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88
decision: KEEP
next_experiment: EXP-011
```

## EXP-011 — Reproduce the P03 force trip with a fresh browser W4 run

```yaml
experiment_id: EXP-011
status: VALID
prior_experiment: EXP-010
hypothesis: The P03 transfer force trip was an isolated simulation contact transient rather than a deterministic trajectory or browser-start defect.
prediction: With unchanged source, install, image and 20-point catalog after a full restart, browser-driven W4 completes P01-P20 first-pass with all four workers stopped and cleanup true.
single_variable: Fresh lifecycle and simulation instances; source, execution profile, catalog and worker count unchanged.
lifecycle: FULL_RESTART
preconditions:
  - EXP-010 recovery receipt verified, no owner/container/domain residue, exact install-v3 executable and matching Broker image readback.
success_criteria:
  - Browser StartGuard and start; P03 passes once; 20 unique sealed PASSED attempts and coverage/execution/qualification/cleanup true; fresh UI screenshot.
failure_criteria:
  - Another force trip, point failure/indeterminate, cleanup refusal or process residue.
invalid_criteria:
  - Source/image mismatch or stale browser authority.
provenance:
  source_commit: dad92c8859b8c83135fbc8c8698e29df4e863d65 plus task-local fixes
  install_overlay: /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88/install-v3
  runtime_executable: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python
  ros_domain_ids: [181, 182, 183, 184]
  gz_partition: so101-teleop-tailscale-ai-226
commands:
  - command: Managed doctor/start unchanged install-v3 and registered task root, then Computer Use chose PARALLEL / 4, acquired fresh lease, generated 20 points, checked resources and clicked Start validation.
    exit_code: 0
observed:
  - Managed service PID 2744285. UI StartGuard PASS: CPU busy 3.1%, 32 cores, GPU free 14.8 GiB and RAM free 25.9 GiB. Browser launched campaign-32c748ce51944b1bb3a1a2f7a8e12d16, which reached RUNNING with 20 requested points.
  - P03 cup_test_left_5cm PASSED on first attempt in the UI, unlike EXP-009, so that exact point failure is not deterministic with the unchanged source/config/catalog.
  - P08 sample_04_near_left became INDETERMINATE in batch b7da0. Its dynamic manifest records MOVEIT_EXECUTION_MONITOR_ABORTED / DYNAMIC_EARLY_TABLE_CONTACT at MOVE_ABOVE_PLACE; controller cancellation and worker quarantine preserved the working attempt.
  - At end of execution the UI shows 20 execution starts, 19 first-pass PASSED, one INDETERMINATE, zero unrun and CLEANING_UP. Aggregate qualification and batch cleanup are false. The failed P08 and successful prior W4 P08 have identical input cup pose and MOVE_ABOVE_PLACE target. Both lift cup center to about 0.225 m; the new run diverged during horizontal transfer.
  - The failure manifest captures a later recovery sample, not the exact contact event. It cannot distinguish a brief real collision from an incorrect contact report; no safety threshold or table-contact gate has been weakened.
inferred:
  - At least two distinct physical monitor stops can arise during the same transport phase across complete W4 campaigns; a wider replay must preserve the trigger sample before changing motion policy.
conclusion: VALID failed browser-driven W4 repeat; P03 was nonreproducible, while P08 exposed a new first failing boundary. Preserve this batch separately and recover offline before the next diagnostic run.
evidence:
  - /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88
decision: REPEAT
next_experiment: EXP-012
```

## EXP-012 — Offline recovery after the P08 table-contact stop

```yaml
experiment_id: EXP-012
status: VALID
prior_experiment: EXP-011
hypothesis: All owners of failed W4 batch b7da0 have exited and its stale fence can be resolved without declaring success.
prediction: Preview proves leader, process group, container and domains absent; apply records an aborted receipt with no signals.
single_variable: Offline operator recovery for campaign-32c748ce51944b1bb3a1a2f7a8e12d16 / b7da0.
lifecycle: FULL_RESTART
preconditions:
  - Failed UI screenshot and working P08 attempt preserved; managed service identity and owner absence audited.
success_criteria:
  - RECOVERY_ELIGIBLE_PREVIEW and OPERATOR_RECOVERED_ABORTED receipt, execution_success=false and upstream_cleanup_claimed=false.
failure_criteria:
  - Live owner, config mismatch or invalid receipt.
invalid_criteria:
  - Unrelated owner ambiguity.
provenance:
  source_commit: dad92c8859b8c83135fbc8c8698e29df4e863d65 plus task-local fixes
  install_overlay: /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88/install-v3
  runtime_executable: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python
  ros_domain_ids: [181, 182, 183, 184]
  gz_partition: so101-teleop-tailscale-ai-226
commands:
  - command: Computer Use saved CLEANING_UP UI and navigated to about:blank. Audited no batch process/container/GPU owner, stopped only managed PID 2744285, then manager cleanup returned ALREADY_EXITED.
    exit_code: 0
  - command: Recorded campaign/batch recovery fence, ran installed operator recovery preview and apply with exact v3 config.
    exit_code: 0
observed:
  - Preview proved batch container b7da0 absent, leader and process group 2748884 absent, domains 181-188 clear and config SHA256 991b5c1b4fbd0cc1f0a97bd20a5b5a4e02028634f3f4ef288ad87554b383ab70 matched.
  - Apply returned OPERATOR_RECOVERED_ABORTED, execution_success=false, upstream_cleanup_claimed=false and signals_sent=[]. Report, config copy and supervisor backup are retained.
inferred:
  - The stale fence is resolved without altering P08 or batch qualification history.
conclusion: VALID audited abort recovery.
evidence:
  - /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88
decision: KEEP
next_experiment: EXP-013
```

## EXP-013 — Capture the exact physical monitor violation

```yaml
experiment_id: EXP-013
status: VALID
prior_experiment: EXP-012
hypothesis: The post-recovery terminal sample is insufficient to classify the P03/P08 failures; persisting the atomic snapshot that triggered the monitor will identify actual cup pose, contact pair and force at the first failing boundary.
prediction: A targeted diagnostic run records the violating publisher sequence, simulation step, cup pose, contact geometries/positions and joint state before cancellation; existing safety behavior remains intact.
single_variable: Add failure-only atomic monitor evidence to the dynamic execution manifest.
lifecycle: FULL_RESTART
preconditions:
  - EXP-012 receipt durable, no owner residue; regression test RED before source patch.
success_criteria:
  - Targeted test RED then GREEN at min(8, CPU) workers, rebuilt install/image provenance, live diagnostic evidence adequate to separate physical collision from bad contact report.
failure_criteria:
  - Monitor behavior changes, missing failure snapshot or target diagnostic cannot reproduce.
invalid_criteria:
  - Instrumented source not present in both install and frozen Broker image.
provenance:
  source_commit: dad92c8859b8c83135fbc8c8698e29df4e863d65 plus task-local fixes
  install_overlay: /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88/install-v5 (v4 diagnostic predecessor retained)
  runtime_executable: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python
  ros_domain_ids: [181, 182, 183, 184]
  gz_partition: so101-teleop-tailscale-ai-226
commands:
  - command: Exact-source failure-snapshot pytest RED, implementation, then source-mapped GREEN and adjacent file gate with -n 8 and unique verified NVMe scratch paths.
    exit_code: 0
  - command: colcon fresh install-v4 of so101_teleop and so101_demo_py, and rebuilt frozen Broker image from the changed source.
    exit_code: 0
  - command: Managed service doctor READY and start from install-v4 on 100.104.202.119:8000.
    exit_code: 0
observed:
  - Failure-snapshot test RED at the intended boundary before patch; source-mapped GREEN afterward, adjacent test_dynamic_execute.py 18/18 under -n 8. Scratch and XML/log/exit receipts are retained under this task root.
  - Initial fresh build missed Bun in the remote shell; verified existing Bun executable and the corrected build finished 2/2 packages. Installed dynamic module contains _record_monitor_violation.
  - Frozen Broker image sha256:20c2d6a814c0d0f66b4bd3b0c1a58f66eef8e2d1221a1f36a3cad5fea6f8b517; source SHA256 4f0434f926b76ddd0842eb96949d616baac97a23558a736ec79d3b5b8756542f; receipt SHA256 f2d2633ced334a9fa273cad45a2790c9e7959da33475279b617ba029e0476ede.
  - Managed installed v4 service PID 2831822 started with registered evidence root.
  - Computer Use started full W4 campaign-467842d2c9a34272884d8af2063abfd7, batch b8080. P03 tripped the force monitor; an atomic recovery-state sample captured 11.6069 N of fingertip-to-cup force and no table contact, but the recovery event overwrote the first MOVE_ABOVE_PLACE trigger. Diagnostic run was cancelled through the UI after the disqualifying result.
  - Browser showed CANCELLING, 6 evaluated PASSED and 1 INDETERMINATE at cancellation. Audit showed no live batch owner, container or ROS process; exact managed service PID 2831822 stopped. Offline recovery preview checked all eight domains clear, batch container and leader/group absent; apply recorded OPERATOR_RECOVERED_ABORTED with no signal, no success/cleanup claim.
  - Extended the regression to require that subsequent recovery violations cannot overwrite the first trigger. It failed at the intended boundary under -n 8, then the full adjacent file passed 18/18 under -n 8 with distinct verified NVMe scratch paths.
  - Rebuilt install-v5 and frozen Broker image sha256:010dca70ce3ce995367793642c2e5515718986253cecacc032e9f7f7ec6c5457, matching source SHA256 3624dac7c70603039f9337f9f5175f9bf8b427656bf4bf09ed6cd490308d84a2. Managed service PID 2869092 started; Computer Use admitted and started eight-point W4 diagnostic campaign-1356e71b4aa14072bb2c79d7c39aafaf.
  - Eight-point W4 diagnostic campaign-1356e71b4aa14072bb2c79d7c39aafaf COMPLETED with P01-P08 first-pass 8/8, qualification and batch cleanup true; browser terminal screenshot retained. Neither P03 nor P08 reproduced a monitor abort.
  - With the same installed source/image, Computer Use generated a fresh 20-point catalog, StartGuard PASS and started full W4 campaign-08ff66872bdd41deb7e5325b9a98c56f; its terminal outcome is recorded in EXP-014.
inferred:
  - The first failure's physical cause cannot be classified from the v4 run because that first sample was overwritten; no v5 monitor abort occurred to provide a fresh trigger sample.
conclusion: VALID evidence-capture repair and eight-point diagnostic; intermittent physical abort root cause remains unconfirmed.
evidence:
  - /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88
decision: KEEP
next_experiment: EXP-014
```

## EXP-014 — Complete browser W4 validation

```yaml
experiment_id: EXP-014
status: VALID
prior_experiment: EXP-013
hypothesis: The installed v5 runtime can complete the full 20-point W4 catalog after the eight-point diagnostic passed with unchanged physical safety thresholds.
prediction: Computer Use starts W4 after a fresh guarded check; twenty distinct point attempts finish PASSED, qualification and batch cleanup complete, and no batch owner remains.
single_variable: Point count 8 to 20 with W4, catalog seed and installed runtime unchanged.
lifecycle: REUSE_STACK
preconditions:
  - Eight-point diagnostic completed with qualification and cleanup true; managed v5 service healthy, no batch residue.
success_criteria:
  - Browser terminal COMPLETED, P01-P20 first pass 20/20, unique sealed evidence, aggregate qualification and cleanup true, no batch process/container.
failure_criteria:
  - Any failed, indeterminate, unrun or repeated point, missing evidence, or incomplete cleanup.
invalid_criteria:
  - Wrong source/image provenance, stale browser authority or missing StartGuard admission.
provenance:
  source_commit: dad92c8859b8c83135fbc8c8698e29df4e863d65 plus task-local fixes
  install_overlay: /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88/install-v5
  broker_image_id: sha256:010dca70ce3ce995367793642c2e5515718986253cecacc032e9f7f7ec6c5457
  runtime_executable: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python
  ros_domain_ids: [181, 182, 183, 184]
  gz_partition: so101-teleop-tailscale-ai-226
commands:
  - command: Computer Use choose PARALLEL W4, generate fresh 20 points, Check resources StartGuard PASS, Start validation.
    exit_code: 0
  - command: Fresh terminal UI screenshot, production API, aggregate report, sealed attempt and process/container readback.
    exit_code: 0
observed:
  - Campaign campaign-08ff66872bdd41deb7e5325b9a98c56f, batch b706a, reached COMPLETED; requested/evaluated/execution_started/valid_succeeded 20/20/20/20, zero failed/indeterminate/unrun, coverage/execution/qualification/cleanup true.
  - Twenty distinct point IDs have one sealed PASSED attempt each across four workers; all initial/terminal RGB, physical numeric and dynamic manifests exist. Fresh browser terminal screenshot and API JSON retained.
  - Sampled P03 terminal RGB shows the cup upright on the table and the gripper withdrawn; no batch process or Broker container remains.
inferred:
  - The full browser W4 success contract is met for this campaign; previous failed batches remain separate and auditable.
conclusion: VALID complete W4 validation.
evidence:
  - /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88
decision: KEEP
next_experiment: EXP-015
```

## EXP-015 — Complete browser W8 validation

```yaml
experiment_id: EXP-015
status: VALID
prior_experiment: EXP-014
hypothesis: The installed v5 runtime can also complete the same 20-point catalog with eight concurrent independent workers.
prediction: Computer Use W8 admission and execution finish all points first pass, with qualification and full cleanup.
single_variable: Worker count 4 to 8 with the 20-point catalog and runtime unchanged.
lifecycle: REUSE_STACK
preconditions:
  - EXP-014 terminal/cleanup true; managed v5 service healthy, no batch residue.
success_criteria:
  - Browser terminal COMPLETED, twenty unique sealed PASSED attempts, eight worker identities, qualification and cleanup true, no batch process/container.
failure_criteria:
  - Any failed, indeterminate, unrun or repeated point, missing evidence, or incomplete cleanup.
invalid_criteria:
  - Wrong source/image provenance, stale browser authority or missing StartGuard admission.
provenance:
  source_commit: dad92c8859b8c83135fbc8c8698e29df4e863d65 plus task-local fixes
  install_overlay: /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88/install-v5
  broker_image_id: sha256:010dca70ce3ce995367793642c2e5515718986253cecacc032e9f7f7ec6c5457
  runtime_executable: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python
  ros_domain_ids: [181, 182, 183, 184, 185, 186, 187, 188]
  gz_partition: so101-teleop-tailscale-ai-226
commands:
  - command: Computer Use choose PARALLEL W8, generate fresh 20 points, Check resources StartGuard PASS, Start validation.
    exit_code: 0
  - command: Fresh terminal UI screenshot, production API, aggregate report, sealed attempt and process/container readback.
    exit_code: 0
observed:
  - Campaign campaign-4578dccaadb14d1e84f3552ac0fd62ef, batch bd96e, reached COMPLETED; requested/evaluated/execution_started/valid_succeeded 20/20/20/20, zero failed/indeterminate/unrun, coverage/execution/qualification/cleanup true.
  - Twenty distinct point IDs have one sealed PASSED attempt each across worker-01 through worker-08; all initial/terminal RGB, physical numeric and dynamic manifests exist. Fresh browser terminal screenshot and API JSON retained.
  - Sampled P18 terminal RGB shows the cup upright on the table and the gripper withdrawn; no batch process or Broker container remains.
inferred:
  - The full browser W8 success contract is met for this campaign; previous API-started W8 remains a separate earlier successful run.
conclusion: VALID complete W8 validation.
evidence:
  - /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88
decision: KEEP
next_experiment: NONE
```

## CP-009

```yaml
checkpoint_id: CP-009
last_valid_experiment: EXP-015
current_hypothesis: The three required browser campaigns are complete; intermittent earlier force/table-contact aborts were not reproduced after the evidence-capture repair, so their physical root remains unconfirmed.
working_tree_status: Mac and Linux worktrees on codex/so101-unified-webapp HEAD dad92c88 with task-local Web, recovery, IK and monitor source/tests dirty; Mac experiment ledger untracked. Installed v5 and matching frozen Broker image serve the final W4/W8 runs.
owned_processes: Managed installed v5 Web service PID 2869092 on 100.104.202.119:8000; no campaign coordinator, worker, ROS, Broker container or batch GPU owner after W8.
preserved_processes: ai-station Codex sessions, Docker daemon and unrelated RustDesk GPU process.
confirmed_conclusions:
  - Browser SEQUENTIAL campaign-7073fffd432d402d8bc641927095543b, W4 campaign-08ff66872bdd41deb7e5325b9a98c56f and W8 campaign-4578dccaadb14d1e84f3552ac0fd62ef each completed 20/20 first-pass with independent sealed physical/visual evidence, qualification and cleanup true.
  - Exact trigger-capture and primary-history regression tests passed 18/18 in the adjacent demo test file under -n 8; Web 302/302 and operator recovery 65/65 passed earlier in this task. Fresh installed v5 source and image provenance match.
  - Failed browser W4 batches remain auditable and were recovered as ABORTED without success or cleanup claims.
disproven_routes:
  - A recovery-state terminal sample reliably describes the first failing monitor boundary.
open_risks:
  - The intermittent physical force/table-contact abort root cause remains unconfirmed because no v5 monitor violation occurred; safety limits were not relaxed.
  - Full Linux package pytest gates remain failing for separately recorded platform/fixture issues; no package-wide pass claim.
next_command: No further validation action required for this task; retain evidence and report the remaining risks.
```

## Evidence disposition

```yaml
retained_runs:
  - /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88 (about 1.4 GiB; all successful and failed campaign evidence, service/build/test logs, receipts, screenshots and installed overlays)
archived_runs: []
deletion_candidates:
  - /data/work/so101-evidence/sequential-w4-w8-validation/20260924-dad92c88/scratch/* (14 test scratch trees after result readback)
deletions_performed: []
```

## CP-008

```yaml
checkpoint_id: CP-008
last_valid_experiment: EXP-012
current_hypothesis: The exact atomic contact snapshot at the dynamic transfer monitor is needed before changing the force or table-contact policy.
working_tree_status: Mac and Linux HEAD dad92c88 with task-local Web/recovery/IK source and tests; Mac ledger dirty. install-v3 and matching image unchanged.
owned_processes: Managed service stopped; second failed W4 batch coordinator and owners absent; recovery receipt resolved its fence.
preserved_processes: ai-station codex tmux, Docker daemon, unrelated RustDesk GPU process.
confirmed_conclusions:
  - Three earlier separate SEQUENTIAL, API W4 and API W8 campaigns completed 20/20 first-pass; fresh Computer Use terminal screenshots exist for SEQUENTIAL and W8.
  - Browser W4 EXP-009 had P03 force-limit stop; browser W4 EXP-011 passed P03 but had P08 early table-contact stop. Each ended 19 PASSED, one INDETERMINATE with incomplete upstream cleanup; both are preserved and audibly recovered as ABORTED.
disproven_routes:
  - Repeating the same unmodified full W4 is sufficient to distinguish the physical root cause.
open_risks:
  - The contact trigger instant was not persisted; successful and failed P08 paths share input and target, and post-recovery terminal pose cannot prove trigger geometry.
  - Full Linux package pytest gates remain failing for separately recorded test/environment issues; no package-wide pass claim.
next_command: Add and run a RED failure-snapshot regression, then add minimal monitor evidence capture without relaxing safety gates.
```

## CP-007

```yaml
checkpoint_id: CP-007
last_valid_experiment: EXP-010
current_hypothesis: The P03 force-monitor trip may be transient; a fresh browser W4 run at identical source/config/catalog will test reproducibility without weakening the safety guard.
working_tree_status: Mac and Linux HEAD dad92c88; task-local Web/recovery/IK source and tests dirty, Mac ledger dirty. install-v3 and matching Broker image unchanged.
owned_processes: Managed service stopped; failed W4 coordinator and all batch owners absent; offline recovery fence resolved.
preserved_processes: ai-station codex tmux, Docker daemon, unrelated RustDesk GPU process.
confirmed_conclusions:
  - Earlier SEQUENTIAL, API W4 and API W8 completed 20/20; Computer Use now has fresh terminal screenshots for SEQUENTIAL and W8.
  - Browser W4 campaign-4fcfc0cd27044de5a855f9017b4e2db6 ended 19 PASSED, P03 INDETERMINATE after DYNAMIC_FORCE_LIMIT_EXCEEDED in MOVE_ABOVE_PLACE; cleanup incomplete. EXP-010 recorded an auditable aborted recovery with no success claim.
disproven_routes:
  - The browser W4 launch itself is not sufficient to guarantee a perfect run; the physics safety monitor can trip despite an admitted StartGuard.
open_risks:
  - P03 transient versus reproducible contact cause is unconfirmed; no basis to change the force limit.
  - Full Linux package pytest gates remain failing for separately recorded test/environment issues; no package-wide pass claim.
next_command: Doctor/start unchanged install-v3 after TIME_WAIT, then Computer Use W4 admission and full run.
```

## CP-006

```yaml
checkpoint_id: CP-006
last_valid_experiment: EXP-007
current_hypothesis: A fresh controller instance will allow a genuinely browser-launched W4 repeat, and then W8, now that Computer Use is restored.
working_tree_status: Mac and Linux branch HEAD dad92c88 with task-local Web, recovery, IK and test changes; Mac task ledger dirty. install-v3 and matching Broker image are available on ai-station.
owned_processes: Managed install-v3 service PID 2619374 on 100.104.202.119:8000; no batch coordinator, worker, Gazebo, MoveIt or ros2_control owner after W8.
preserved_processes: ai-station codex tmux, Docker daemon, unrelated RustDesk GPU process.
confirmed_conclusions:
  - EXP-005 SEQUENTIAL, EXP-008 W4 repeat and EXP-007 W8 each completed 20/20 first-pass with cleanup and qualification true. W8 has fresh Computer Use terminal readback and screenshot.
  - Earlier EXP-006 W4 had P18 start-state limit refusal; install-v3 interior IK margin removed that refusal in the completed W4/W8 runs.
disproven_routes:
  - Curling 127.0.0.1:8000 does not check this service: it binds only the Tailscale address.
open_risks:
  - W4/W8 successful campaign starts used production API while Computer Use was unavailable; browser-driven admission/start still needs direct exercise.
  - Full Linux package pytest gates have unrelated/environment and parallel fixture failures recorded in task evidence; do not claim package-wide pass.
next_command: Audit exact service status and stop only managed PID, then restart install-v3 and use Computer Use for a fresh W4 campaign.
```

## CP-005

```yaml
checkpoint_id: CP-005
last_valid_experiment: EXP-006
current_hypothesis: The 0.002 rad interior IK margin in install-v3 and matching rebuilt Broker image permit a complete W4 first pass.
working_tree_status: Mac and Linux branch HEAD dad92c88 with task-local UI, recovery, IK source and tests dirty; fresh install-v3 and Docker image available on ai-station.
owned_processes: Managed service stopped; W4 coordinator and all batch owners absent after offline recovery; no batch Broker/container/GPU process.
preserved_processes: ai-station codex tmux, Docker daemon, unrelated RustDesk GPU process.
confirmed_conclusions:
  - EXP-005 SEQUENTIAL 20/20 qualified and cleaned up; EXP-006 W4 P18 exceeded joint-4 start bound by 0.00002 rad and ended 19 PASSED, 1 INDETERMINATE with incomplete cleanup.
  - IK exact-limit regression RED before fix and GREEN under -n 8 after fix; v3 install and image provenance built.
disproven_routes:
  - Targeting the exact URDF joint limit is unsafe for a subsequent MoveIt start-state check.
open_risks:
  - W4 repeat and W8 remain unobserved; Computer Use native pipe remains unavailable.
next_command: Doctor/start install-v3, acquire fresh live instance authority, run new guarded W4 campaign.
```

## CP-004

```yaml
checkpoint_id: CP-004
last_valid_experiment: EXP-004
current_hypothesis: A fresh overlay and the rebuilt Broker image permit a full sequential campaign.
working_tree_status: Mac ledger and Web UI/recovery source/tests dirty; Linux same targeted source, Web dist and node_modules dirty; both branch HEAD dad92c88.
owned_processes: No managed service, coordinator, Worker, Broker, batch container, or GPU process.
preserved_processes: ai-station codex tmux, Docker daemon and unrelated processes.
confirmed_conclusions:
  - EXP-004 recovered the pre-journal failed campaign as ABORTED without claiming execution.
disproven_routes:
  - colcon --log-base is a global option and cannot follow the build verb.
open_risks:
  - Actual twenty-point SEQUENTIAL, W4 and W8 physical/visual execution and cleanup remain unobserved.
next_command: Inspect fresh colcon build completion, start managed service from install-v2, then use Computer Use for fresh SEQUENTIAL campaign.
```

## CP-003

```yaml
checkpoint_id: CP-003
last_valid_experiment: EXP-003
current_hypothesis: The failed pre-journal campaign can be audited and recovered offline, then a fresh service can run with the rebuilt Broker image.
working_tree_status: Mac ledger and Web UI/recovery source/tests dirty; Linux only targeted operator recovery source/test dirty; both branch HEAD dad92c88.
owned_processes: Managed service PID 2465582; coordinator PID 2466672 exited; no batch worker, container or GPU process observed.
preserved_processes: ai-station codex tmux, Docker daemon and unrelated processes.
confirmed_conclusions:
  - EXP-002 coordinator failed before first point on missing image; EXP-003 image rebuilt with immutable provenance.
disproven_routes:
  - The service manager cannot clean this stale STARTED projection directly: CAMPAIGN_ACTIVE refusal despite no live owner.
open_risks:
  - Offline recovery may find an unobserved descendant or domain; fail closed if so.
next_command: Repeat exact owner/container/domain audit, then stop only verified managed service PID for offline recovery.
```

## CP-002

```yaml
checkpoint_id: CP-002
last_valid_experiment: EXP-001
current_hypothesis: The sequential campaign can execute all 20 points with the current guarded Linux v3 runtime.
working_tree_status: Ledger and UI fix/test dirty on Mac; Linux product source clean at dad92c88.
owned_processes: Managed ai-station service PID 2465582; active browser lease; no campaign/stack yet.
preserved_processes: ai-station codex tmux and unrelated processes.
confirmed_conclusions:
  - EXP-001 SEQUENTIAL preflight passed with GPU/RAM/CPU guard checks; W4/W8 are configured at backend but blocked by stale UI budget view.
disproven_routes:
  - Treating legacy UNKNOWN budget view as a Linux v3 execution refusal is inconsistent with the production start path.
open_risks:
  - Actual twenty-point physical/visual execution and cleanup have not yet been observed.
next_command: Computer Use click Start validation on the current SEQUENTIAL page
```

## CP-001

```yaml
checkpoint_id: CP-001
last_valid_experiment: EXP-000
current_hypothesis: Production budget admission is unknown; the first resource guard must be measured before campaigns.
working_tree_status: Only this new ledger is dirty; Mac and Linux product source clean at dad92c88.
owned_processes: New ai-station managed service PID 2465582 on 8000 in this task's root; no campaign/stack yet.
preserved_processes: ai-station codex tmux session and unrelated processes.
confirmed_conclusions:
  - EXP-000 existing service IDLE with no campaign; installed source provenance identified.
disproven_routes:
  - EXP-000 restart alone does not qualify exact N.
open_risks:
  - W4 and W8 may require an independently approved budget provider and profile.
next_command: Computer Use Chrome snapshot at http://100.104.202.119:8000/expert-validation
```
