# SO-101 MoveIt Expert Validation Web Experiment Ledger

```yaml
task_id: so101-moveit-expert-validation-web-20260916-e1701375-a01
goal: Implement and validate the approved 17-task Teleop MoveIt expert validation Web plan in MuJoCo simulation only.
success_contract: Source and package gates pass; fresh fixed four-point and adaptive twenty-point campaigns satisfy their authoritative upstream terminal and cleanup contracts; eligible business failure receives an independent FULL_RESTART retry or is explicitly not applicable because all points passed.
worktree: /data/work/ws_moveit/.worktrees/teleop-expert-validation-web
branch: codex/teleop-expert-validation-web
base_commit: e1701375690321bc83b5f30ec044da1847d373aa
current_commit: 12aeeb43ad68bc004fde9a3355388f7707e958ec
evidence_root: /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01
confirmed_conclusions:
  - origin/main exactly matched the required documentation commit e1701375690321bc83b5f30ec044da1847d373aa at CP-001.
  - The canonical checkout and new implementation worktree were clean at CP-001.
  - No pre-existing SO-101 application stack or ROS nodes were observed at CP-001.
  - The production server and coordinator accept the final bound copied overlay without symlinks or source fallback.
  - The manifest point source is an explicit closed API enum, and the final so101_teleop source gate passes 388 tests under -W error with no warning summary.
disproven_routes:
  - At commit 654756ba32cfc0697aff1444c79752ff1e61c4ee, a four-point manifest could not be returned because its source field violated the closed response model.
open_hypotheses:
  - The repaired installed API can now cross manifest creation and authorize a fresh sequential simulation campaign.
latest_checkpoint: CP-003
next_experiment: EXP-025
```

## Registered evidence and ownership

- Durable evidence root: `/data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01`
- Dispatch ID: `58403c0d-21cf-49b1-a2d3-1ab92a5f7b2a`
- Runtime-fix dispatch ID: `23EAC586-3035-444F-96F9-54B85A7E427D`
- Host: `ai-station`
- Python: `/usr/bin/python3` (`Python 3.12.3`)
- Bun: `/home/lenovo/.bun/bin/bun` (`1.3.14`)
- Existing tmux: session `codex`, pane `%0`, owned by this dispatch.
- Existing relevant processes: this Codex process tree only; no Gazebo, MuJoCo, MoveIt, validation server, coordinator, or adaptive wrapper process was observed.
- ROS graph: empty.
- Preserved worktrees: every pre-existing worktree reported by `git worktree list --porcelain` at CP-001; none is owned by this task and none may be modified or cleaned.
- Dirty files at CP-001: none in canonical checkout or implementation worktree.
- Archived runs: none.
- Deletion candidates: none yet; future scratch trees are candidates only and must not be deleted without explicit authorization.

## EXP-001 — Source and package gates

```yaml
experiment_id: EXP-001
status: PASS
prior_experiment: NONE
hypothesis: The implementation can satisfy all Python, Web, browser, real-process, build, and installed-package contracts from one clean task-owned commit.
prediction: Every required gate collects non-zero tests and exits zero, generated contracts are stable, and installed provenance resolves inside the task-owned overlay.
single_variable: The Web validation implementation introduced by Tasks 1 through 15.
lifecycle: ISOLATED_STACK
preconditions:
  - Worktree is on codex/teleop-expert-validation-web from e1701375690321bc83b5f30ec044da1847d373aa.
  - No SO-101 runtime stack is active.
  - Every pytest or colcon test uses a fresh scratch/<test-run-id>/tmp directory below the registered evidence root.
success_criteria:
  - Required source, Web, Playwright, real-process, package, and installed-layout gates exit zero with non-zero test counts.
  - The ordinary so101_demo_py gate does not collect benchmark_test.
failure_criteria:
  - Any assertion, build, schema, browser, package-layout, or installed-provenance failure.
invalid_criteria:
  - Wrong Python, stale install overlay, TMPDIR outside the registered evidence root, zero tests, or unrelated runtime/process contamination.
provenance:
  source_commit: 2128c536bd102925f46e82aaeb4faaabdb42f55e
  install_overlay: /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/install
  runtime_executable: SOURCE_TESTS_THEN_TASK_OWNED_INSTALL
  ros_domain_id: NONE_FOR_SOURCE_GATES
  gz_partition: NONE_FOR_SOURCE_GATES
commands:
  - command: Task-specific RED/GREEN commands followed by the Task 15 and Task 16 package gates.
    exit_code: 0
observed:
  - CP-001 provenance and ownership preflight completed before source edits.
  - The final source commit is 2128c536bd102925f46e82aaeb4faaabdb42f55e.
  - The strict so101_teleop source gate passed 383 tests under -W error with only two exact third-party FastAPI/Pydantic compatibility warnings narrowly allowed and no warning summary.
  - The final installed colcon readback reported 3115 tests, 0 errors, 0 failures, and 1 skipped: so101_demo_py contributed 3069 cases and so101_teleop contributed 382 cases across 46 CTest XML files.
  - The dedicated Linux process-owner integration JUnit collected three non-skipped passing cases.
  - The ordinary so101_demo_py gate did not collect benchmark_test.
inferred:
  - The implementation and installed package contracts are green independently of the later live-runtime startup boundary.
conclusion: PASS
evidence:
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/dispatch-initial-probe.txt
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/task-ledger.md
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/task15-teleop-pytest-007.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/task16-colcon-test-003.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/task16-colcon-test-004.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/process-owner-integration-linux.xml
decision: ADVANCE_TO_RUNTIME_PREFLIGHT
next_experiment: EXP-002
```

## Planned runtime experiments

The following entries were frozen before the final build or any simulation process was started.

### EXP-002 — Four-point sequential smoke

```yaml
experiment_id: EXP-002
status: INVALID
prior_experiment: EXP-001
hypothesis: The dedicated Web service can launch one fixed coordinator and complete the frozen four-point subset serially with authoritative point and cleanup evidence.
prediction: SEQUENTIAL N=1 K=4 reaches a safe terminal state; every point has fresh camera, MoveIt, controller, physics, Planning Scene, and cleanup evidence.
single_variable: execution_mode=SEQUENTIAL with worker_count=1 and max_points_per_worker=4
lifecycle: FRESH_ISOLATED_STACK
source_commit: 2128c536bd102925f46e82aaeb4faaabdb42f55e
install_overlay: /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/install
catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
parallel_config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
coordinator_module_sha256: ec18441cc5281dcb844d4bb279c74200bf53cffb81e176029c10440cbf2f7cce
selection: [task_start, cup_test_forward_5cm, sample_05_near_center, sample_14_far_right]
fixed_config: {worker_count: 1, max_points_per_worker: 4}
model_provenance:
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_sam_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
  broker_image_id: sha256:4fb57abe1109e7cc1c7fbf1780a7dd10b4167f12abfa59ba34b1903a60c4c972
success_criteria: Four authoritative PASSED point results, complete fixed qualification flags, and verified batch cleanup.
failure_criteria: Any authoritative FAILED or INDETERMINATE point, incomplete cleanup, or cross-attempt ownership leak.
invalid_criteria: Provenance mismatch, stale input, reset/session contamination, missing camera/MoveIt/controller/physics/Planning Scene evidence, or unknown process ownership.
observed:
  - The installed dedicated server exited before binding its socket with SO101_VALIDATION_SERVICE_FACTORY_REQUIRED. Its installed launcher calls main() without the factory that main() requires.
  - A simulation-free fixed-coordinator dry run using the exact frozen selection, task-owned installed overlay, catalog, configs, models, and Broker tag exited with PROVENANCE_MIXED_OVERLAY.
  - The coordinator provenance verifier requires the console and build products under <repository_root>/install and <repository_root>/build, while this plan requires the installed runtime under the registered durable evidence root. No MuJoCo, MoveIt, Worker, or Broker process was started.
  - Post-failure process readback found no task-owned SO-101 runtime stack to clean up.
conclusion: INVALID_BEFORE_SIMULATION_START
first_bad_boundary: DEDICATED_SERVER_PRODUCTION_COMPOSITION_MISSING
secondary_boundary: TASK_OWNED_EXTERNAL_OVERLAY_REJECTED_BY_COORDINATOR_PROVENANCE
evidence:
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/task16-server-start-001.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/task16-fixed-dry-run-001.log
decision: STOP_RUNTIME_SEQUENCE_FAIL_CLOSED
```

### EXP-003 — Same-selection two-Worker smoke

```yaml
experiment_id: EXP-003
status: NOT_RUN
prior_experiment: EXP-002
hypothesis: The same immutable four-point selection can execute with two isolated fixed Workers without ownership, pose, artifact, Broker, ROS-domain, or simulation-session leakage.
prediction: PARALLEL N=2 K=2 reaches a safe terminal state with two distinct Worker identities and complete cleanup.
single_variable: execution_mode=PARALLEL with worker_count=2 and max_points_per_worker=2; selection and all provenance remain identical to EXP-002
lifecycle: FRESH_ISOLATED_STACK
source_commit: 2128c536bd102925f46e82aaeb4faaabdb42f55e
install_overlay: /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/install
catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
parallel_config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
coordinator_module_sha256: ec18441cc5281dcb844d4bb279c74200bf53cffb81e176029c10440cbf2f7cce
selection: [task_start, cup_test_forward_5cm, sample_05_near_center, sample_14_far_right]
fixed_config: {worker_count: 2, max_points_per_worker: 2}
resource_observation_policy: admission is fixed-mode only; no silent downgrade to sequential is allowed
success_criteria: Two isolated Workers complete the four authoritative points with correct dynamic leases/K debits, shared-Broker identity/fairness, and complete cleanup.
failure_criteria: Any terminal point failure, resource admission failure, cross-Worker leak, or incomplete cleanup.
invalid_criteria: Any provenance/reset/session mismatch, duplicate coordinator, stale artifact, or missing per-Worker evidence.
observed:
  - Not started because EXP-002 failed before the shared Web/runtime authority could be established.
decision: BLOCKED_BY_EXP_002_INVALID
```

### EXP-004 — Twenty-point adaptive first pass

```yaml
experiment_id: EXP-004
status: NOT_RUN
prior_experiment: EXP-003
hypothesis: The production adaptive wrapper can execute the exact baseline catalog through Runner-owned generations and fallback semantics without Teleop recreating scheduling truth.
prediction: The first pass reaches COMPLETED_ALL_SUCCEEDED or COMPLETED_WITH_FAILURES with all twenty final point states, attempt histories, generations, resource observations, and cleanup receipts sealed.
single_variable: execution_mode=ADAPTIVE with preferred W8 and frozen W6/W4/W2/W1 fallback ladder
lifecycle: FRESH_ISOLATED_STACK
source_commit: 2128c536bd102925f46e82aaeb4faaabdb42f55e
install_overlay: /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/install
catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
parallel_config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
adaptive_config_sha256: 876ebf364076cb179e190266b42384b16a54eaf5a1b2c54113965d5e71127621
adaptive_runner_module_sha256: 64fb30186fabcb2c0988abe655f0dddbd909b1958853668307cc8a39238257ea
adaptive_pool_module_sha256: dbe220834233ed98b50fb8ad3369537e0ebc020ad4c263d8707e7d91ae90686e
adaptive_wrapper_sha256: 3667d8c0d27aa8b6a0d2638db1c186d1abffc52fe06aa4a207b3c2df91636fc7
adaptive_cleanup_module_sha256: 25eba952c9f3a3266aa311b5fcffc18c1a54f2407f5c2ccb4241a6e81d89f57f
adaptive_config:
  preferred_worker_count: 8
  fallback_worker_counts: [6, 4, 2, 1]
  initial_points_per_worker: 3
  worker_start_timeout_s: 120
  max_infra_attempts_per_point: 5
  yolo_executor_count: 2
model_provenance:
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_sam_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
  broker_image_id: sha256:4fb57abe1109e7cc1c7fbf1780a7dd10b4167f12abfa59ba34b1903a60c4c972
resource_observation_policy: observations are recorded but never select or reject an adaptive tier; only real infrastructure failure advances the Runner ladder
success_criteria: Safe Runner terminal status with twenty authoritative final states, sealed histories/artifacts, and complete batch cleanup.
failure_criteria: INFRA_FAILED, unsafe cleanup, unknown descendants, or a missing authoritative final point state.
invalid_criteria: Fixed K/live-headroom fields, non-production wrapper, provenance mismatch, stale evidence, or Teleop-derived adaptive terminal/fallback state.
observed:
  - Not started because the production Web service composition is absent and the required installed overlay is rejected by upstream provenance.
  - The adaptive process-owner path also expects an r/<batch_id>/handshake.json binding, while the installed production wrapper does not emit that handshake; this was identified by source readback only and was not bypassed.
decision: BLOCKED_BY_SHARED_RUNTIME_BOUNDARY
```

`EXP-005` was not created. EXP-004 did not reach a safe adaptive terminal state, so neither a business-failure retry nor `LIVE_RETRY_NOT_APPLICABLE_ALL_SUCCEEDED` is applicable.

## Runtime-fix continuation — dispatch 23EAC586-3035-444F-96F9-54B85A7E427D

The continuation preserves EXP-002 through EXP-004 exactly as recorded and does not reinterpret the
previously uncreated EXP-005. New work begins at EXP-006 so every repaired-boundary and simulation
run has a fresh monotonic identity.

### EXP-006 — Repaired installed runtime boundaries

```yaml
experiment_id: EXP-006
status: PASS
prior_experiment: EXP-004
hypothesis: The installed dedicated server now composes the durable production service and the coordinator accepts only an explicitly content-bound external overlay.
prediction: The installed server binds, serves health, and shuts down cleanly; the exact installed coordinator dry run crosses both original CP-002 boundaries while stale, mixed, mismatched, and unbound overlays remain rejected.
single_variable: Production service composition plus explicit external-overlay provenance binding.
lifecycle: ISOLATED_NO_SIMULATION_BOUNDARY_PROBES
source_commit: 654756ba32cfc0697aff1444c79752ff1e61c4ee
build_overlay: /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/runtime-fix-build-release
install_overlay: /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/runtime-fix-install-release
success_criteria:
  - Focused RED evidence reproduces both original boundaries and focused GREEN gates pass.
  - Installed server returns health from the production factory and releases its singleton lock on clean shutdown.
  - Coordinator dry run accepts the explicit binding and records exact source commit, package prefixes, entry points, config, catalog, and executable identities.
failure_criteria: Either original boundary remains after the fresh install, or a negative identity case is accepted.
invalid_criteria: Stale install, dirty source, wrong test Python/TMPDIR, source-tree fallback, symlink bypass, or any simulation process started by these probes.
observed:
  - The release copy overlay contains ordinary installed files and is bound by runtime-fix-release-overlay-binding.json to exact source, build, install, package-prefix, console, module, config, catalog, and entry-point identities.
  - The installed coordinator dry run crossed PROVENANCE_MIXED_OVERLAY and TRUSTED_FINAL_TARGET_INVALID, recorded VALIDATION_PASSED, and completed cleanup.
  - The installed production server returned health, advertised only SEQUENTIAL without manufacturing parallel/adaptive acceptance, served the installed SPA, shut down cleanly, and released its durable-store lock.
  - Negative provenance-binding tests, 117 coordinator/adaptive tests, and all 387 strict-warning Teleop source tests passed.
evidence:
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/runtime-fix-release-overlay-binding.json
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/runtime-fix-coordinator-release.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/runtime-fix-server-release.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/runtime-fix-server-health.json
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/runtime-fix-server-capabilities.json
decision: ADVANCE_TO_EXP_007
next_experiment: EXP-007
```

### EXP-007 — Fresh four-point sequential simulation

```yaml
experiment_id: EXP-007
status: INVALID
prior_experiment: EXP-006
hypothesis: The repaired Web authority can start the fixed coordinator for the frozen four-point selection with N1/K4 and retain authoritative point and cleanup evidence.
prediction: All four points reach an authoritative terminal state and the owned stack completes cleanup without identity or evidence leakage.
single_variable: execution_mode=SEQUENTIAL, worker_count=1, max_points_per_worker=4
lifecycle: FRESH_ISOLATED_STACK
source_commit: 654756ba32cfc0697aff1444c79752ff1e61c4ee
selection: [task_start, cup_test_forward_5cm, sample_05_near_center, sample_14_far_right]
success_criteria: Four authoritative PASSED results, all fixed qualification flags true, complete cleanup, and independently inspected visual evidence.
failure_criteria: Any authoritative business failure, indeterminate result, or incomplete cleanup.
invalid_criteria: Provenance, reset/session, ownership, camera, MoveIt/controller, physics, Planning Scene, artifact, or visual evidence mismatch.
observed:
  - Lease acquisition succeeded and persisted generation 1.
  - Four-point manifest creation persisted manifest-d38e32943c674b76856e6688144ea9cb, but FastAPI returned HTTP 500 before preflight.
  - Each internal manifest point includes source=anchor while the closed ManifestPointResponse omits source; response validation reported four extra_forbidden errors.
  - No campaign directory, coordinator, Worker, Broker, MoveIt, controller, MuJoCo, or robot action was started. Post-failure inventory was clean and the durable-store lock was released.
first_bad_boundary: MANIFEST_RESPONSE_VALIDATION_ERROR
evidence:
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/runtime-fix-live-sequential-lease.json
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/runtime-fix-live-first-invalid-boundary.txt
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/runtime-fix-server-live.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/runtime-fix-live-postinventory.txt
decision: STOP_RUNTIME_SEQUENCE_FAIL_CLOSED
next_experiment: STOP_FAIL_CLOSED
```

### EXP-008 — Fresh same-selection parallel simulation

```yaml
experiment_id: EXP-008
status: NOT_RUN
prior_experiment: EXP-007
hypothesis: The identical four-point selection runs through two isolated fixed Workers with dynamic leases and no cross-Worker leakage.
prediction: N2/K2 reaches a safe terminal state with distinct Worker, ROS domain, simulation session, artifact, and cleanup identities.
single_variable: execution_mode=PARALLEL, worker_count=2, max_points_per_worker=2
lifecycle: FRESH_ISOLATED_STACK
source_commit: 3442b18c15201450a4f6b2c134f1ee974d8ce3f2
selection: [task_start, cup_test_forward_5cm, sample_05_near_center, sample_14_far_right]
success_criteria: Four authoritative PASSED results with correct N2/K2 ownership, Broker routing, evidence isolation, and complete cleanup.
failure_criteria: Any business failure, admission failure, cross-Worker leak, or incomplete cleanup.
invalid_criteria: Any provenance/reset/session/owner mismatch, stale artifact, duplicate lease, or missing per-Worker evidence.
observed:
  - Not started because EXP-007 failed at the production manifest response boundary before simulation start.
decision: BLOCKED_BY_EXP_007_INVALID
next_experiment: EXP-009
```

### EXP-009 — Fresh twenty-point adaptive simulation

```yaml
experiment_id: EXP-009
status: NOT_RUN
prior_experiment: EXP-008
hypothesis: The installed production wrapper and Runner own the full W8/W6/W4/W2/W1 adaptive lifecycle and preserve authoritative results across any real infrastructure fallback.
prediction: The exact twenty-point catalog reaches COMPLETED or COMPLETED_WITH_FAILURES with top-level Runner journal authority, sealed generations, and complete cleanup.
single_variable: execution_mode=ADAPTIVE with preferred W8 and fallback [6, 4, 2, 1]
lifecycle: FRESH_ISOLATED_STACK
source_commit: 3442b18c15201450a4f6b2c134f1ee974d8ce3f2
success_criteria: Twenty authoritative final states, exact wrapper/Runner handshake and ownership, truthful fallback history, complete cleanup, and independently inspected visual evidence.
failure_criteria: INFRA_FAILED, unsafe cleanup, unknown descendants, or missing authoritative final point state.
invalid_criteria: Fixed-K semantics, non-production wrapper, provenance mismatch, stale evidence, Teleop-derived Runner truth, or missing generation evidence.
observed:
  - Not started because EXP-007 failed closed before a valid sequential campaign existed.
decision: BLOCKED_BY_EXP_007_INVALID
next_experiment: EXP-010
```

### EXP-010 — Conditional FULL_RESTART retry

```yaml
experiment_id: EXP-010
status: NOT_APPLICABLE
prior_experiment: EXP-009
hypothesis: An eligible authoritative FAILED point, if one exists, can be retried only as a new serial N1/K1 FULL_RESTART batch after prior cleanup is committed.
prediction: Each eligible selected point receives a new batch, attempt, simulation session, domain, owner, evidence child, and cleanup receipt; otherwise the ledger records LIVE_RETRY_NOT_APPLICABLE_ALL_SUCCEEDED.
single_variable: FULL_RESTART retry of eligible FAILED points only
lifecycle: FRESH_ISOLATED_STACK_PER_POINT
source_commit: 3442b18c15201450a4f6b2c134f1ee974d8ce3f2
success_criteria: Eligible retries satisfy the independent restart contract, or no eligible failure exists and non-applicability is recorded without manufacturing one.
failure_criteria: Reuse of a first-pass Worker/session, retry before cleanup, or unsafe terminal cleanup.
invalid_criteria: Retrying PASSED, INDETERMINATE, UNRUN, unresolved INVALID, or adaptive infrastructure interruption as a product failure.
observed:
  - No authoritative adaptive terminal campaign or eligible FAILED point exists; no retry was manufactured.
decision: LIVE_RETRY_NOT_APPLICABLE_NO_VALID_FIRST_PASS
```

### EXP-011 — Repaired manifest contract and fresh sequential simulation

```yaml
experiment_id: EXP-011
status: INVALID
prior_experiment: EXP-007
hypothesis: Declaring the stable point source enum in the closed public response model removes the first EXP-007 boundary without weakening response validation, allowing the same four-point sequential campaign to reach a safe authoritative terminal state.
prediction: Manifest creation returns HTTP 200 with four source=anchor points, preflight admits N1/K4, and the fresh sequential campaign retains complete coordinator, Worker, MoveIt/controller, MuJoCo physics, Planning Scene, artifact, cleanup, Web, and visual evidence.
single_variable: ManifestPointResponse now declares source as the closed enum anchor or generated.
lifecycle: FRESH_ISOLATED_STACK
preconditions:
  - Source commit 12aeeb43ad68bc004fde9a3355388f7707e958ec is clean.
  - The copied overlay and binding below match the source commit and contain no symlink install artifacts.
  - No validation server, coordinator, Worker, Broker, MoveIt, controller, Gazebo, or MuJoCo process is active.
success_criteria:
  - POST and GET manifest return the exact four selected points including source=anchor.
  - Preflight admits SEQUENTIAL worker_count=1 and max_points_per_worker=4.
  - All four points reach authoritative PASSED with complete cleanup and independently inspected visual evidence.
failure_criteria:
  - A valid campaign reaches an authoritative business failure or safe non-passing terminal state.
invalid_criteria:
  - Any provenance, reset/session, owner, camera, MoveIt/controller, physics, Planning Scene, artifact, cleanup, Web, or visual evidence mismatch.
provenance:
  source_commit: 12aeeb43ad68bc004fde9a3355388f7707e958ec
  install_overlay: /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/manifest-source-install-release2
  runtime_executable: /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/manifest-source-install-release2/so101_teleop/lib/so101_teleop/so101_expert_validation_server
  provenance_binding: /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/manifest-source-release2-overlay-binding.json
  ros_domain_id: 91
  gz_partition: so101-exp011-12aeeb43
  simulation_session_id: exp011-seq-12aeeb43
selection: [task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm]
fixed_config: {worker_count: 1, max_points_per_worker: 4}
commands:
  - command: Start the installed dedicated server, create the four-point manifest, preflight, and start the Web-authorized sequential campaign.
    exit_code: 127
observed:
  - The frozen four-point selector returns the four anchor points above; the prior generated-point selection text was stale and contradicted both the selector and EXP-007 response-validation evidence.
  - The YOLO weights and Grounded-SAM manifest independently hash to the frozen values before server start.
  - The declared runtime path omitted the installed `.py` suffix and the shell exited 127 before importing product code.
  - No listener, validation server, coordinator, Worker, Broker, MoveIt, controller, Gazebo, or MuJoCo process survived the invalid probe.
inferred:
  - This run can test the repaired public source contract without changing point-selection behavior.
conclusion: Invalid operator path; no product or simulation boundary was exercised.
evidence:
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp011/server.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp011/preinventory.txt
decision: STOP_FAIL_CLOSED_AND_USE_FRESH_ID
next_experiment: EXP-012
```

### EXP-012 — Corrected installed entry point and fresh sequential simulation

```yaml
experiment_id: EXP-012
status: INVALID
prior_experiment: EXP-011
hypothesis: The installed `.py` entry point exposes the repaired four-anchor manifest contract and permits the fresh N1/K4 sequential campaign to reach an authoritative terminal state.
prediction: POST and GET manifest return HTTP 200 with four source=anchor points, preflight admits N1/K4, and the campaign retains complete runtime and cleanup evidence.
single_variable: Correct the operator command to the installed executable filename; source, overlay, models, manifest count, and fixed execution configuration are unchanged.
lifecycle: FRESH_ISOLATED_STACK
source_commit: 12aeeb43ad68bc004fde9a3355388f7707e958ec
runtime_executable: /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/manifest-source-install-release2/so101_teleop/lib/so101_teleop/so101_expert_validation_server.py
provenance_binding: /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/manifest-source-release2-overlay-binding.json
selection: [task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm]
fixed_config: {worker_count: 1, max_points_per_worker: 4}
observed:
  - The corrected installed `.py` entry point imported the installed production composition root.
  - Source identity then rejected the registered but uncommitted ledger update with SO101_VALIDATION_SOURCE_IDENTITY before binding admission, socket bind, or campaign state creation.
  - No listener, validation server, coordinator, Worker, Broker, MoveIt, controller, Gazebo, or MuJoCo process survived.
conclusion: Invalid protocol ordering: runtime registration made the otherwise bound source tree dirty before production startup.
evidence:
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp012/preinventory.txt
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp012/server.log
decision: STOP_FAIL_CLOSED_COMMIT_REGISTRATION_AND_REBUILD
next_experiment: EXP-013
```

### EXP-013 — Clean committed source and fresh sequential simulation

```yaml
experiment_id: EXP-013
status: INVALID
prior_experiment: EXP-012
hypothesis: A fresh copy-install overlay bound to the clean registration commit starts the installed service and permits the repaired four-anchor N1/K4 campaign.
single_variable: Build and bind from the clean post-registration commit; product code, model identities, selection, and fixed execution configuration remain unchanged.
lifecycle: FRESH_ISOLATED_STACK
selection: [task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm]
fixed_config: {worker_count: 1, max_points_per_worker: 4}
success_criteria: Four authoritative PASSED results, complete cleanup, Web projection, and independently inspected runtime evidence.
invalid_criteria: Any provenance, reset/session, ownership, camera, MoveIt/controller, physics, Planning Scene, artifact, cleanup, Web, or visual mismatch.
observed:
  - The release3 installed service started from a clean bound source tree.
  - Manifest POST and GET returned the exact four anchor points with source=anchor, and N1/K4 preflight admitted with no reason codes.
  - The coordinator process exited immediately after the API returned STARTED; no Worker, Broker, MoveIt, controller, MuJoCo, or robot action started.
  - A captured safe dry-run reproduced BROKER_IMAGE_MISMATCH: the Teleop production default was a digest while the fixed coordinator contract accepts the frozen image tag.
  - The server stopped cleanly, no owned runtime survived, and the durable-store lock was released.
first_bad_boundary: BROKER_IMAGE_MISMATCH
evidence:
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp013/manifest-post.json
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp013/preflight-response.json
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp013/start-response.json
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp013/postinventory.txt
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp013/store-lock-readback.txt
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp013-diagnostic/coordinator-dryrun.log
decision: STOP_FAIL_CLOSED_AND_FIX_DEFAULT_CONTRACT
next_experiment: EXP-014
```

### EXP-014 — Fresh same-selection parallel simulation

```yaml
experiment_id: EXP-014
status: NOT_RUN
prior_experiment: EXP-013
hypothesis: The same four anchors run through two isolated fixed Workers with N2/K2 and no cross-Worker leakage.
single_variable: execution_mode=PARALLEL, worker_count=2, max_points_per_worker=2
lifecycle: FRESH_ISOLATED_STACK
selection: [task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm]
success_criteria: Four authoritative PASSED results with distinct Worker/runtime identities and complete cleanup.
observed:
  - Not started because EXP-013 failed before Worker or simulation startup.
decision: BLOCKED_BY_EXP_013_INVALID
next_experiment: EXP-015
```

### EXP-015 — Fresh twenty-point adaptive simulation

```yaml
experiment_id: EXP-015
status: NOT_RUN
prior_experiment: EXP-014
hypothesis: The production adaptive wrapper owns the W8/W6/W4/W2/W1 lifecycle and preserves authoritative results across any real fallback.
single_variable: execution_mode=ADAPTIVE with preferred W8 and fallback [6, 4, 2, 1]
lifecycle: FRESH_ISOLATED_STACK
success_criteria: Twenty authoritative terminal point states, truthful generation/fallback history, and complete cleanup.
observed:
  - Not started because no valid repaired sequential campaign exists yet.
decision: BLOCKED_BY_EXP_013_INVALID
next_experiment: EXP-016
```

### EXP-016 — Conditional FULL_RESTART retry

```yaml
experiment_id: EXP-016
status: NOT_APPLICABLE
prior_experiment: EXP-015
hypothesis: Any eligible authoritative FAILED point can be retried only as a new serial N1/K1 FULL_RESTART batch after cleanup; otherwise retry is not applicable.
single_variable: FULL_RESTART retry of eligible FAILED points only
lifecycle: FRESH_ISOLATED_STACK_PER_POINT
success_criteria: Eligible retries satisfy independent restart identity and cleanup, or non-applicability is recorded without manufacturing a failure.
observed:
  - No valid first-pass terminal result or eligible FAILED point exists; no retry was manufactured.
decision: LIVE_RETRY_NOT_APPLICABLE_NO_VALID_FIRST_PASS
```

### EXP-017 — Broker-contract repair and fresh sequential simulation

```yaml
experiment_id: EXP-017
status: INVALID
prior_experiment: EXP-013
hypothesis: Matching the production default broker image to the fixed coordinator tag removes the early-exit boundary and permits the four-anchor N1/K4 campaign.
single_variable: Teleop production broker-image default now equals the fixed upstream coordinator contract.
lifecycle: FRESH_ISOLATED_STACK
selection: [task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm]
fixed_config: {worker_count: 1, max_points_per_worker: 4}
success_criteria: Four authoritative PASSED results with complete runtime, artifact, cleanup, Web, and independently inspected visual evidence.
observed:
  - Release4 safe coordinator dry-run crossed the repaired broker-image comparison, then stopped at PROVENANCE_CONSOLE_MISSING before simulation.
  - The installed console is a regular file and matches the bound hash, but the child PATH did not contain its package lib directory, so the upstream coordinator could not discover its own installed console with shutil.which.
  - Focused RED reproduced the missing child-PATH prefix; focused GREEN passes after the supervisor prepends the exact installed console directory.
  - The complete strict Teleop gate passes 390 tests under -W error with no warning summary.
first_bad_boundary: PROVENANCE_CONSOLE_MISSING
evidence:
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/broker-contract-green-dryrun.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/t19-path-red.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/t19-path-green.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/t19-teleop-strict.log
decision: STOP_FAIL_CLOSED_AND_FIX_CHILD_PATH
next_experiment: EXP-018
```

### EXP-018 — Fresh same-selection parallel simulation after broker repair

```yaml
experiment_id: EXP-018
status: NOT_RUN
prior_experiment: EXP-017
hypothesis: The same four anchors run through two isolated fixed Workers with N2/K2 and no cross-Worker leakage.
single_variable: execution_mode=PARALLEL, worker_count=2, max_points_per_worker=2
lifecycle: FRESH_ISOLATED_STACK
selection: [task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm]
observed:
  - Not started because EXP-017 stopped before server or simulation startup.
decision: BLOCKED_BY_EXP_017_INVALID
next_experiment: EXP-019
```

### EXP-019 — Fresh twenty-point adaptive simulation after broker repair

```yaml
experiment_id: EXP-019
status: NOT_RUN
prior_experiment: EXP-018
hypothesis: The production adaptive wrapper owns the W8/W6/W4/W2/W1 lifecycle and preserves authoritative results across any real fallback.
single_variable: execution_mode=ADAPTIVE with preferred W8 and fallback [6, 4, 2, 1]
lifecycle: FRESH_ISOLATED_STACK
observed:
  - Not started because no valid sequential campaign exists after the new provenance boundary.
decision: BLOCKED_BY_EXP_017_INVALID
next_experiment: EXP-020
```

### EXP-020 — Conditional FULL_RESTART retry after broker repair

```yaml
experiment_id: EXP-020
status: NOT_APPLICABLE
prior_experiment: EXP-019
hypothesis: Any eligible authoritative FAILED point can be retried only as a new serial N1/K1 FULL_RESTART batch after cleanup; otherwise retry is not applicable.
single_variable: FULL_RESTART retry of eligible FAILED points only
lifecycle: FRESH_ISOLATED_STACK_PER_POINT
observed:
  - No valid first-pass terminal result or eligible FAILED point exists; no retry was manufactured.
decision: LIVE_RETRY_NOT_APPLICABLE_NO_VALID_FIRST_PASS
```

### EXP-021 — Child-PATH repair and fresh sequential simulation

```yaml
experiment_id: EXP-021
status: INVALID
prior_experiment: EXP-017
hypothesis: Supplying the installed coordinator directory on the owned child PATH closes provenance console discovery and permits the four-anchor N1/K4 campaign.
single_variable: Owned coordinator and adaptive-wrapper child PATH begins with the exact installed coordinator directory.
lifecycle: FRESH_ISOLATED_STACK
selection: [task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm]
fixed_config: {worker_count: 1, max_points_per_worker: 4}
observed:
  - Release5 safe dry-run crossed broker-image and console provenance, then stopped at UNIX_SOCKET_PATH_TOO_LONG before simulation.
  - The registered durable evidence root makes the shortest broker and Worker Unix endpoints exceed Linux's 107-byte pathname limit once batch IPC suffixes are appended.
  - The repair keeps all durable evidence under the registered root and moves only ephemeral Unix sockets/tokens into the closed same-UID 0700 runtime directory /run/user/1000.
  - Five focused fixed/adaptive/resource/IPC/Teleop contracts pass; the broad legacy diagnostic was invalid because its mandated long TMPDIR caused 56 pre-existing default-path tests to hit the same length guard before their intended assertions.
first_bad_boundary: UNIX_SOCKET_PATH_TOO_LONG
evidence:
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/child-path-green-dryrun.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/t20-demo-green2.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/t20-teleop-green.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/t20-demo-regression.log
decision: STOP_FAIL_CLOSED_AND_SEPARATE_EPHEMERAL_IPC_ROOT
next_experiment: EXP-022
```

### EXP-022 — Fresh same-selection parallel simulation after PATH repair

```yaml
experiment_id: EXP-022
status: NOT_RUN
prior_experiment: EXP-021
single_variable: execution_mode=PARALLEL, worker_count=2, max_points_per_worker=2
lifecycle: FRESH_ISOLATED_STACK
selection: [task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm]
observed:
  - Not started because EXP-021 stopped before server or simulation startup.
decision: BLOCKED_BY_EXP_021_INVALID
next_experiment: EXP-023
```

### EXP-023 — Fresh twenty-point adaptive simulation after PATH repair

```yaml
experiment_id: EXP-023
status: NOT_RUN
prior_experiment: EXP-022
single_variable: execution_mode=ADAPTIVE with preferred W8 and fallback [6, 4, 2, 1]
lifecycle: FRESH_ISOLATED_STACK
observed:
  - Not started because no valid sequential campaign exists after the socket-path boundary.
decision: BLOCKED_BY_EXP_021_INVALID
next_experiment: EXP-024
```

### EXP-024 — Conditional FULL_RESTART retry after PATH repair

```yaml
experiment_id: EXP-024
status: NOT_APPLICABLE
prior_experiment: EXP-023
single_variable: FULL_RESTART retry of eligible FAILED points only
lifecycle: FRESH_ISOLATED_STACK_PER_POINT
observed:
  - No valid first-pass terminal result or eligible FAILED point exists; no retry was manufactured.
decision: LIVE_RETRY_NOT_APPLICABLE_NO_VALID_FIRST_PASS
```

### EXP-025 — Short runtime IPC and fresh sequential simulation

```yaml
experiment_id: EXP-025
status: PLANNED
prior_experiment: EXP-021
hypothesis: Separating ephemeral same-user Unix IPC from durable evidence closes the pathname boundary without weakening evidence or runtime ownership.
single_variable: Unix sockets and tokens use the validated same-UID runtime directory; durable evidence layout and all execution semantics are unchanged.
lifecycle: FRESH_ISOLATED_STACK
selection: [task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm]
fixed_config: {worker_count: 1, max_points_per_worker: 4}
decision: RUN_AFTER_CLEAN_COMMIT_BUILD_AND_DRY_RUN
next_experiment: EXP-026
```

### EXP-026 — Fresh same-selection parallel simulation with short IPC

```yaml
experiment_id: EXP-026
status: PLANNED
prior_experiment: EXP-025
single_variable: execution_mode=PARALLEL, worker_count=2, max_points_per_worker=2
lifecycle: FRESH_ISOLATED_STACK
selection: [task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm]
decision: RUN_AFTER_EXP_025_VALID
next_experiment: EXP-027
```

### EXP-027 — Fresh twenty-point adaptive simulation with short IPC

```yaml
experiment_id: EXP-027
status: PLANNED
prior_experiment: EXP-026
single_variable: execution_mode=ADAPTIVE with preferred W8 and fallback [6, 4, 2, 1]
lifecycle: FRESH_ISOLATED_STACK
decision: RUN_AFTER_EXP_026_VALID
next_experiment: EXP-028
```

### EXP-028 — Conditional FULL_RESTART retry with short IPC

```yaml
experiment_id: EXP-028
status: PLANNED
prior_experiment: EXP-027
single_variable: FULL_RESTART retry of eligible FAILED points only
lifecycle: FRESH_ISOLATED_STACK_PER_POINT
decision: CONDITIONAL_AFTER_EXP_027
```

## Task 1 checkpoint

- RED attempt `task01-red-001` was invalid because `/usr/bin/python3` exposed Pydantic 1.10.14 and collection stopped before the feature boundary. Evidence: `/data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/task01-red.log`.
- A task-local `--system-site-packages` virtual environment was created at `/data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/python-venv`; Pydantic 2.13.4 and the current worktree's editable `so101_demo_py` were installed there without changing system Python.
- Valid RED `task01-red-002`: missing `so101_teleop.expert_validation`, exit 2, 0.57 s. Evidence: `/data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/task01-red-002.log`.
- GREEN `task01-green-003`: 11 tests passed, exit 0, 0.90 s. Evidence: `/data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/task01-green-003.log`.
- Existing generator regression `task01-regression-001`: 3 tests passed, exit 0, 0.57 s. Evidence: `/data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/task01-regression-001.log`.
- Top-view readback produced the exact 20-point baseline and minimum spacing `0.015116191120781703` m under `/data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/top-view-fixture`.
- Scratch deletion candidates retained: `scratch/task01-red-001`, `scratch/task01-red-002`, `scratch/task01-green-001`, `scratch/task01-green-002`, `scratch/task01-green-003`, and `scratch/task01-regression-001`.

## Task 2 checkpoint

- RED `task02-red-001`: projection module missing, exit 2, 0.55 s.
- GREEN `task02-green-001`: 24 projection and catalog tests passed, exit 0, 0.87 s.
- Existing generator regression `task02-regression-001`: 3 tests passed, exit 0, 0.55 s.
- The shared fixture freezes equal X/Y scale, full 20-point projection, cup/target radii, constant marker radius, palette, and non-colour terminal icons.
- Evidence: `/data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/task02-red-001.log`, `task02-green-001.log`, and `task02-regression-001.log`.
- Scratch deletion candidates retained: `scratch/task02-red-001`, `scratch/task02-green-001`, and `scratch/task02-regression-001`.

## Task 3 checkpoint

- RED `task03-red-001`: coordinator event adapter missing, exit 2, 0.56 s.
- GREEN `task03-green-001`: 140 Web-adapter and upstream journal/artifact tests passed, exit 0, 2.34 s.
- Fixed projection accepts point state only after a verified `RESULT_COMMITTED`/`VALIDATION_COMMITTED` reference. Adaptive projection consumes only Runner top-level pool/result/fallback/terminal events and never reads a nested generation journal as independent truth.
- Evidence: `/data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/task03-red-001.log` and `task03-green-001.log`.
- Scratch deletion candidates retained: `scratch/task03-red-001` and `scratch/task03-green-001`.

## Task 4 checkpoint

- RED attempt `task04-red-001` was invalid because the source overlay omitted `src/so101_demo_py/src`; collection stopped before the new module boundary.
- Valid RED `task04-red-002`: statistics module missing, exit 2, 0.57 s.
- First GREEN attempt `task04-green-001` correctly rejected an inconsistent test fixture that assigned active leases to a terminal batch: 149 passed and 1 failed.
- Corrected GREEN `task04-green-002`: 151 tests passed, exit 0, 4.63 s.
- Fixed-mode counters preserve the four authoritative upstream flags and fail closed on point-set/status disagreement. Adaptive-mode projections preserve Runner terminal status and attempt history without inventing fixed-mode qualification flags.
- Evidence: `/data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/task04-red-001.log`, `task04-red-002.log`, `task04-green-001.log`, and `task04-green-002.log`.
- Scratch deletion candidates retained: `scratch/task04-red-001`, `scratch/task04-red-002`, `scratch/task04-green-001`, and `scratch/task04-green-002`.

## Task 5 checkpoint

- RED `task05-red-001`: typed coordinator bridge was missing, exit 2.
- GREEN `task05-green-001`: 12 fixed/adaptive ownership tests passed, exit 0, 1.23 s.
- Dedicated real-process gate `task05-integration-001`: 2 tests passed, exit 0, 0.73 s; readback found no surviving `process_tree_helper.py` process.
- Ownership is bound to PID, PGID, `/proc` start ticks, and argv hash. Fixed shutdown is gated on cleanup and targets only the owned coordinator group; adaptive cancellation revalidates and signals only the wrapper PID.
- Evidence: `/data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/task05-red-001.log`, `task05-green-001.log`, and `task05-integration-001.log`.
- Scratch deletion candidates retained: `scratch/task05-red-001`, `scratch/task05-green-001`, and `scratch/task05-integration-001`.

## Task 6 checkpoint

- RED `task06-red-001`: mode-specific control module missing, exit 2.
- GREEN `task06-green-001`: 18 control and process-owner tests passed, exit 0, 0.79 s.
- Fixed control uses a closed, length-prefixed schema with command/request hashes and exact campaign, batch, epoch, socket-mode, and token binding. Coordinator-group stop authorization requires terminal state plus cleanup receipt, descendant inventory, and cleared ROS domains.
- Adaptive control validates the wrapper/Runner binding, signals only the wrapper, and blocks tier advancement or terminal authorization until the corresponding cleanup fact is present.
- Evidence: `/data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/task06-red-001.log` and `task06-green-001.log`.
- Scratch deletion candidates retained: `scratch/task06-red-001` and `scratch/task06-green-001`.

## Task 7 checkpoint

- RED `task07-red-001`: durable models/store modules missing, exit 2.
- Initial GREEN `task07-green-001`: store and existing process integration tests passed before durable owner wiring was added.
- Final GREEN `task07-green-002`: 11 store and real-process integration tests passed, exit 0, 1.01 s; no helper process remained after readback.
- SQLite runs in WAL/FULL/foreign-key mode behind a nonblocking OS writer lock. All mutations use `BEGIN IMMEDIATE`; owner intent precedes spawn acknowledgement, accepted upstream cursors are durable/idempotent, and retry cleanup plus dequeue is one transaction.
- The schema intentionally contains no Worker lease, point-result, or Broker-health truth tables; those remain derived from the bound top-level upstream journal.
- Evidence: `/data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/task07-red-001.log`, `task07-green-001.log`, and `task07-green-002.log`.
- Scratch deletion candidates retained: `scratch/task07-red-001`, `scratch/task07-green-001`, and `scratch/task07-green-002`.

## Task 8 checkpoint

- RED `task08-red-001`: preflight/supervisor modules missing, exit 2.
- GREEN attempts `task08-green-001` and `task08-green-002` were invalid for the upstream CLI gate: the first produced overlong Unix socket paths, while the `/proc/self/fd` alias in the second was correctly rejected by upstream anti-symlink traversal. Both attempts are retained.
- Web-only GREEN `task08-web-green-001`: 25 tests passed, exit 0, 0.99 s.
- Full GREEN `task08-green-003`: 121 Web, store, owner, and upstream CLI tests passed, exit 0, 4.99 s. It used the short, unique scratch directory `t08g3/tmp` directly under the registered evidence root so Unix socket paths remained within the kernel limit.
- Fixed admission never silently changes N/K; adaptive resource pressure remains an observation and cannot choose a tier. Sequential and parallel share the typed coordinator path, adaptive uses one wrapper request, and retry batches are N=1/K=1 with cleanup committed before queue advancement.
- Evidence: `/data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/task08-red-001.log`, `task08-green-001.log`, `task08-green-002.log`, `task08-web-green-001.log`, and `task08-green-003.log`.
- Scratch deletion candidates retained: `scratch/task08-red-001`, `scratch/task08-green-001`, `scratch/task08-green-002`, `scratch/task08-web-green-001`, and `t08g3`.

## Task 9 checkpoint

- RED `task09-red-001`: lease module missing, exit 2.
- GREEN `task09-green-001`: 19 lease, executor-registry, service, and store tests passed, exit 0, 0.72 s.
- Browser disconnect does not release authority; renewal advances the fencing generation; restart invalidates old leases; expiry requests cooperative cancellation and keeps new holders read/cancel-only until recovery.
- The V1 registry exposes only `moveit_expert/validate_pick_place`; fixed parallel and adaptive qualification are independent and fail closed on missing live acceptance. Manifests remain readable after source drift but cannot start new work, and start commands are durably idempotent by canonical payload hash.
- Evidence: `/data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/task09-red-001.log` and `task09-green-001.log`.
- Scratch deletion candidates retained: `scratch/task09-red-001` and `scratch/task09-green-001`.

## Task 10 checkpoint

- RED `task10-red-001`: validation artifact bridge missing, exit 2.
- GREEN `task10-green-001`: 120 validation, Teleop task-artifact, and upstream parallel-artifact tests passed, exit 0, 1.90 s.
- Registration requires a committed manifest hash already accepted by the bound top-level journal. It revalidates relative paths, regular-file and symlink boundaries, media type, size, and SHA256 before creating a server-owned opaque ID.
- Artifact identity remains scoped to campaign, batch, pool generation, Worker generation, and attempt. Shared Broker evidence retains no Worker identity, while Worker recovery retains its original role.
- Evidence: `/data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/task10-red-001.log` and `task10-green-001.log`.
- Scratch deletion candidates retained: `scratch/task10-red-001` and `scratch/task10-green-001`.

## Task 11 checkpoint

- RED `task11-red-001`: dedicated validation API module missing, exit 2.
- First GREEN `task11-green-001`: 23 passed and one route-count assertion failed because OpenAPI collapses PUT/DELETE on one path; the endpoint contract itself was intact.
- Corrected GREEN `task11-green-002`: 24 API, server-safety, regular-server, and OpenAPI tests passed, exit 0, 1.05 s.
- The dedicated service exposes 13 HTTP operations plus one WebSocket route, redirects `/` to `/expert-validation`, disables `/tasks`, and permits only loopback/Tailscale binds. The regular Teleop service exposes only an unavailable validation capability.
- Validation OpenAPI readback is byte-identical to the checked-in contract. Regenerating `expert-validation-schema.d.ts` produced stable SHA256 `22eacb67a494a9b538ff900b34bfc1cd87974170f127f630a7b9d8a52a1c36d9`.
- Evidence: `/data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/task11-red-001.log`, `task11-green-001.log`, `task11-green-002.log`, and `expert-validation-openapi.json`.
- Scratch deletion candidates retained: `scratch/task11-red-001`, `scratch/task11-green-001`, and `scratch/task11-green-002`.

## Task 12 checkpoint

- RED `task12-red-001`: typed validation client module missing, exit 1.
- Initial GREEN `task12-green-001`: 7 client/store tests passed before the typed response contract and full TypeScript gate were added.
- First build `task12-build-001` exposed incomplete campaign fixtures against the generated response model; the fixtures were corrected without weakening the production type.
- Final GREEN `task12-green-002`: 7 tests passed, exit 0, 1.04 s. Final build `task12-build-002` completed TypeScript and Vite production output, exit 0, 5.98 s.
- API/OpenAPI regression `task12-api-regression-002`: 11 tests passed, exit 0, 0.93 s; the preceding regression attempt retained a response-fixture mismatch.
- Web wire types are aliases and transformations of the generated OpenAPI schema. Reconnect performs HTTP GET before opening events, stale hints are discarded, and a sequence gap triggers authoritative HTTP refresh instead of deriving terminal state from WebSocket data.
- Evidence: `/data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/task12-red-001.log`, `task12-green-001.log`, `task12-green-002.log`, `task12-build-001.log`, `task12-build-002.log`, `task12-api-regression-001.log`, and `task12-api-regression-002.log`.
- Scratch deletion candidates retained: `scratch/task12-api-regression-001` and `scratch/task12-api-regression-002`.

## Task 13 checkpoint

- RED `task13-red-001`: Web projection fixture/module missing, exit 1.
- First GREEN `task13-green-001` exposed one JavaScript floating-point tail against the Python-serialized golden coordinate; projection output was normalized to the fixture's eight-decimal precision.
- Final GREEN `task13-green-002`: 15 projection and SVG accessibility/style tests passed, exit 0, 1.48 s.
- Python and Web projection fixtures compare byte-for-byte with `diff -u`. TypeScript/Vite build `task13-build-002` passed, exit 0, 6.05 s; `task13-build-001` was an invalid invocation from the repository root.
- The SVG uses one equal-scale transform, renders stable table/base/target/cup geometry and 20 equal-radius markers, and distinguishes selection focus from active-Worker stroke while preserving keyboard selection and non-colour status icons.
- Evidence: `/data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/task13-red-001.log`, `task13-green-001.log`, `task13-green-002.log`, `task13-build-001.log`, and `task13-build-002.log`.

## Task 14 checkpoint

- RED `task14-red-001`: expert-validation application and component modules were missing, exit 1.
- First GREEN attempt could not retain its log because the registered evidence root requires an approved write; it nevertheless isolated one duplicate live-status rendering after 18 of 19 tests passed.
- Final GREEN `task14-green-002`: 19 application, component, and top-view tests passed, exit 0, 1.38 s.
- TypeScript/Vite build `task14-build-001` passed, exit 0, 6.00 s.
- Changing point count invalidates the generated manifest and preflight receipt. Fixed parallel setup exposes exact capacity, while adaptive setup exposes the fixed fallback ladder. Campaign progress renders Worker generations, Broker health, fallback history, evidence, and retry controls limited to eligible failed points behind exact confirmation.
- Evidence: `/data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/task14-red-001.log`, `task14-green-002.log`, and `task14-build-001.log`.

## Task 15 checkpoint

- Browser RED `task15-red-e2e-001` failed at the intended missing reconnect/restore boundary. Final Playwright GREEN `task15-e2e-green-001` and package E2E gate `task15-web-e2e-001` each passed 1 test.
- Package-layout RED `task15-package-red-001` proved the new expert-validation tests were not registered. Final package-layout GREEN `task15-package-green-001` passed 8 tests after registering all expert-validation source gates and the real-process gate in CMake.
- Full Web gate `task15-web-all-001` passed 89 tests; production build `task15-web-build-001` completed successfully. The browser scenario exercised W8-to-W6 fallback, two Worker generations, Broker recovery, an `INDETERMINATE` requeue, a WebSocket sequence gap with HTTP resynchronization, restart restoration, a terminal failed point, and an independent retry attempt that passed.
- Linux process gate `task15-process-integration-001` passed 3 real-process tests. The task-owned development overlay was extended with the pinned `mujoco_ros2_control` fork and support packages after installed-provenance tests correctly rejected the incomplete first overlay.
- The first valid full `so101_teleop` baseline passed 383 tests with 25 warnings: 23 first-party Pydantic V1 deprecations and two upstream FastAPI/Pydantic compatibility deprecations. First-party calls now use `model_dump`, `model_copy`, and `model_validate`; the two external `general_plain_validator_function` warnings are narrowly filtered in package-local pytest configuration.
- Strict focused warning gate `task15-teleop-warnings-focused-006` passed 14 process/ownership tests. Strict full gate `task15-teleop-pytest-007` passed all 383 tests under `-W error`, with only the exact external compatibility warning allowed. Task-gateway parent log descriptors now close immediately after spawn, and real-process tests explicitly reap owned children.
- The final full `so101_demo_py` attempt `task15-demo-pytest-009` collected only the ordinary suite: 3,065 passed, 1 skipped, and two pre-existing timing/isolation races failed after 309.24 s. Both exact failures passed immediately in fresh isolated scratch (`task15-demo-flakes-focused-010`, 2 passed); an earlier focused set covering all environment-related failures also passed 29 tests (`task15-demo-focused-006`). No benchmark test was collected.
- Invalid or superseded demo attempts are retained: missing task-local Torch (`001`), incomplete ROS support overlay (`002`/`003`), uninitialized pinned submodule and one race (`004`), invalid tempdir probe (`005`), one launch cleanup race in an otherwise 3,066-pass run (`007`), and its passing focused replay (`008`).
- Evidence: `/data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/task15-red-e2e-001.log`, `task15-e2e-green-001.log`, `task15-package-red-001.log`, `task15-package-green-001.log`, `task15-web-all-001.log`, `task15-web-build-001.log`, `task15-web-e2e-001.log`, `task15-process-integration-001.log`, `task15-teleop-pytest-001.log`, `task15-teleop-warnings-focused-006.log`, `task15-teleop-pytest-007.log`, `task15-demo-pytest-009.log`, and `task15-demo-flakes-focused-010.log`.
- Scratch and build deletion candidates retained without deletion: `task15-build`, `task15-install`, `task15-colcon-log`, `t15t5`, `t15t6`, `t15t7`, `t15d9`, `t15d10`, and all Task 15 `scratch/` attempts.

## Checkpoint CP-001

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: The merged upstream coordinator and adaptive interfaces can be consumed directly by the Web implementation.
working_tree_status: clean before this ledger file was created
owned_processes: Codex dispatch process tree in tmux session codex; no SO-101 runtime processes
preserved_processes: all processes not explicitly spawned and recorded by this task
confirmed_conclusions:
  - Required published base commit fetched and verified.
  - Target branch and worktree were absent, then created from the verified base.
  - Registered evidence root is the only evidence root for this task.
disproven_routes:
  - NONE
open_risks:
  - Upstream qualification artifacts and exact installed runtime provenance remain to be checked before live execution.
next_command: Write and run the Task 1 catalog RED tests using a fresh registered scratch directory.
```

## Task 16 and Task 17 checkpoint

- The task-owned installed overlay is `/data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/install`. `ros2 pkg prefix` and executable/config readbacks passed for `so101_demo_py` and `so101_teleop`.
- Final package testing passed. `colcon test-result --verbose` reported 3,115 tests, zero errors, zero failures, and one skip. The dedicated Linux real-process integration gate collected and passed three tests.
- The final `so101_demo_py` package gate passed 3,068 tests with one skip. Four multiprocessing/fork warnings remain in the demo detector-factory suite; they are outside the requested `so101_teleop` warning scope.
- The `so101_teleop` warning cleanup is complete: first-party Pydantic V1 calls were migrated, parent subprocess log descriptors close immediately after spawn, real children are reaped, and fresh final gate `final-teleop-warning-verify-008` passed all 383 tests under `-W error`. The command exempted only the two verified external emitters `fastapi.openapi.models` and `pydantic_core.core_schema`; it produced no warning summary.
- The installed dedicated server startup attempt exited with `SO101_VALIDATION_SERVICE_FACTORY_REQUIRED`; it never bound port 8010 and never started an execution owner.
- A no-simulation coordinator dry run then exited with `PROVENANCE_MIXED_OVERLAY`: upstream provenance requires worktree-local `build/` and `install/`, contradicting this task's required durable external overlay. No symlink, source-tree fallback, alternate coordinator, or direct execution bypass was used.
- EXP-002 is therefore `INVALID` before simulation start. EXP-003 and EXP-004 are `NOT_RUN`; EXP-005 is not applicable because there is no safe adaptive terminal campaign to classify or retry.
- Runtime evidence is separate from source/package evidence: implementation and tests are green, but fixed/adaptive MuJoCo runtime, live artifact visual acceptance, retry, and page-backed campaign execution remain unverified.
- Retained run: `/data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01`.
- Archived runs: none.
- Deletion candidates retained without deletion: all `scratch/` (including superseded final warning attempts 001 through 007 and passing attempt 008), `t08g3`, `t15*` scratch/build/install trees, `build`, `final-build`, `final-install`, colcon log/result trees, and the empty or partial runtime/diagnostic directories created by failed startup probes.
- Final warning evidence: `/data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/final-teleop-warning-verify-008.log` and `.xml`. Attempts 001 through 007 are retained as invalid/superseded command-environment diagnostics.

## Checkpoint CP-002

```yaml
checkpoint_id: CP-002
last_valid_experiment: EXP-001
current_hypothesis: Runtime acceptance requires a production service factory/API composition and provenance support for the task-owned external install overlay before any simulation campaign can be validly started.
working_tree_status: only the task-owned experiment ledger is untracked before its final commit
owned_processes: no validation server, coordinator, adaptive wrapper, Worker, Broker, MoveIt, or MuJoCo process survives
preserved_processes: all processes not explicitly spawned and recorded by this task
confirmed_conclusions:
  - Source, Web, browser, process-owner, build, and installed package gates pass.
  - so101_teleop passes its strict warning gate.
  - The documented ros2 server command cannot start because no production service factory is supplied.
  - The required external installed overlay is rejected by coordinator provenance before simulation starts.
disproven_routes:
  - The checked-in dedicated server launcher is not independently runnable as documented.
  - A direct installed-overlay coordinator invocation cannot serve as a valid fallback under the frozen provenance contract.
open_risks:
  - No fresh task-camera, MoveIt/controller, physics, Planning Scene, fixed-parallel, adaptive, cleanup, visual, or live-retry evidence exists for this implementation.
next_command: Add and test a production ExpertValidationService composition, add an adaptive wrapper handshake compatible with exact ownership, and make installed provenance accept the explicitly bound task-owned overlay without weakening source/install identity checks; then create fresh experiment IDs instead of reusing EXP-002 through EXP-004.
```

## Runtime-fix checkpoint

- Runtime repair commits from CP-002 are `8a59deaa2`, `3442b18c1`, `6e9be24e2`, `40590e94c`, `458224107`, `382beb92f`, and `654756ba3`.
- The final non-symlink overlay is `runtime-fix-install-release`; its source commit is `654756ba32cfc0697aff1444c79752ff1e61c4ee` and its closed binding is `runtime-fix-release-overlay-binding.json`.
- Final source warning gate `runtime-fix-teleop-strict-release` passed 387 tests under `-W error`. Only the two exact external FastAPI/Pydantic emitters were exempted, and the run produced no warning summary.
- Release colcon gates passed: all 46 Teleop CTest commands and 386 underlying pytest cases were green; the proportionate installed coordinator/adaptive gate passed 117 tests. The ordinary suite did not collect `benchmark_test`.
- Web unit, TypeScript build, and Playwright gates remained green at 89 tests, successful production build, and 11 browser tests respectively.
- EXP-006 passed both repaired runtime boundaries. The final coordinator dry run returned `VALIDATION_PASSED` with cleanup complete; the dedicated server returned health and installed SPA content, advertised only `SEQUENTIAL`, exited zero, and released its lock.
- EXP-007 stopped before preflight or simulation: the production manifest response failed closed with four `extra_forbidden` errors on the internal `source` field. EXP-008 and EXP-009 were not run; EXP-010 is not applicable because no valid first pass or eligible failed point exists.
- Pre- and post-live inventories found no owned Gazebo, MuJoCo, MoveIt, coordinator, Worker, Broker, or validation-server process. No campaign directory was created.
- Retained run: `/data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01`.
- Archived runs: none.
- Deletion candidates retained without deletion: every `scratch/` attempt; superseded `runtime-fix-build*`, `runtime-fix-install*`, and `runtime-fix-log*` trees except the release set; failed and superseded test-result/log trees; `e6d`, `e6v`, `e6a`, and final dry-run `e6r`; and all earlier build/install/test candidates already listed at CP-002.

## Checkpoint CP-003

```yaml
checkpoint_id: CP-003
last_valid_experiment: EXP-006
current_hypothesis: The copied-overlay runtime composition is valid, but the production manifest response projection must exclude or model its internal source field before any Web-authorized simulation can start.
working_tree_status: only the task-owned experiment ledger is modified before its final commit
owned_processes: no validation server, coordinator, adaptive wrapper, Worker, Broker, MoveIt, controller, Gazebo, or MuJoCo process survives
preserved_processes: all processes not explicitly spawned and recorded by this task
confirmed_conclusions:
  - Both original CP-002 runtime boundaries are repaired without symlinks or source fallback.
  - Final source, Web, browser, installed Teleop, and proportionate coordinator/adaptive gates pass.
  - so101_teleop emits no first-party pytest warnings under the strict final gate.
  - Production manifest creation mutates durable state before its response fails closed on an undeclared source field.
disproven_routes:
  - The current closed ManifestPointResponse can serialize the canonical internal manifest point document.
open_risks:
  - No fresh task-camera, MoveIt/controller, physics, Planning Scene, artifact, visual, parallel, adaptive, or retry acceptance exists because EXP-007 never reached preflight.
next_command: Add a RED API test for the production manifest point projection, fix the closed response contract without exposing unintended internal fields, rebuild a fresh bound copy overlay, and create new experiment IDs rather than reusing EXP-007 through EXP-010.
```
