# SO-101 MoveIt Expert Validation Web Experiment Ledger

## CP-009 — Exited owner is not cancellation authority

- Source preceding this fix: `1faf89fe8af24805e0cbb0ea605afc51956e3d0a`. No new physical campaign; EXP-052 remains pending. Last actual runtime EXP-051 used source79a/copy release16, server domain231 and Worker domains181/182/183, GZ_PARTITION=not_applicable (MuJoCo).
- RED t80 recreated lease-expiry failure with a real short-lived non-ROS child owned by ExecutionProcessOwner. After natural exit0 and no live descendants, its retained binding still triggered FIXED_CANCEL_REQUIRES_CONTROL_SOCKET.1fail,exit1,elapsed1.05s. Child reaped; scratch/cx/tmp exact venv tempfile verified.
- Minimal fix: cancel_for_reason polls the recorded execution and skips only when both leader and descendants are no longer live. It does not clear the binding, alter retry/statistics, grant authority or equate leader exit with cleanup. Existing expiry recovery fence remains conservative.
- GREEN t81:complete strict Teleop411passed,elapsed9.95s,exit0. Additional real toy adaptive-wrapper cancellation proves the live branch delegates to exact wrapper PID; wrapper stops its own child and writes cleanup.json. Final t82 strict gate412passed,elapsed10.23s,exit0,no warning summary. Scratch/cy/cz exact tempfile verified; all tests and toy processes terminal.
- Remaining control gap: fixed cancel_for_reason still reaches ExecutionProcessOwner.request_cancel, which intentionally rejects fixed owners. CoordinatorControlClient exists but is not wired to production Supervisor; no matching authenticated Web-control server exists in upstream CLI. Do not claim active fixed cancellation or durable reconciliation complete. Implement the approved authenticated channel; do not weaken the reject gate or signal Worker/Runner/Broker groups.
- Other incomplete original gates: actual immutable-manifest map cardinality/geometry and reload restoration, verified Runner adaptive projection and qualified capabilities, corruption/restart recovery fencing and start idempotency, full producer RGB-D/cloud previews and all-layer artifact/visual acceptance, fixed N2/K2 and exact20adaptive, conditional retry, fresh installed gates and publication. Source tests/readback do not qualify these live gates.
- Evidence: registered root t80/t81/t82 logs, JUnit and metadata. Retained:unchanged root and all historical artifacts. Archived:none. Deletion candidates:cx/cy/cz and earlier scratch/superseded overlays; none deleted.

```yaml
checkpoint_id: CP-009
last_valid_experiment: EXP-006
current_hypothesis: Fixed production control must consume the authenticated client and upstream Coordinator request-stop/cleanup authority; the map must consume its bound immutable manifest instead of20fixture points.
working_tree_status: task-owned supervisor.py, test_expert_validation_supervisor.py and ledger changes
owned_processes: no task simulation/server/browser; handles terminal and toy leaders/descendants reaped
preserved_processes: all unrelated user sessions/processes
next_command: Commit the verified exited-owner guard, audit control transport and manifest/projection contracts, then build production integration RED tests without launching another simulation.
```

## CP-008 — Commit-authorized artifact metadata reaches the point panel

- Boundary confirmed: production projection hard-coded empty attempts/artifact_ids and App hard-coded an empty evidence list. The earlier registry-only tests never exercised this composition.
- `committed_artifacts.py` now imports only RESULT_COMMITTED references from the verified bound Coordinator journal. It checks full AttemptIdentity, exact Worker/point/attempt sealed path, journal reference hash and result status, then invokes the public upstream verify_attempt for complete inventory and mode-specific semantics. No directory scan, alternate verifier, scheduler or result writer was introduced.
- Registered records carry opaque IDs, allow-listed media types, semantic roles and campaign/batch/Worker generation/attempt identity. The original sealed manifest is offered as a separate sealed-result artifact. All validation occurs before advancing the accepted cursor. Duplicate committed identities fail closed. Production points now expose typed artifacts, existing artifact_ids and real first-pass attempts; the closed API and generated OpenAPI/TypeScript contracts are synchronized.
- App consumes the real typed artifact list. PointEvidence distinguishes FIRST_PASS from FULL_RESTART_RETRY and reports empty committed evidence explicitly. Geometry/manifest point cardinality and durable campaign restart restoration remain separate open gaps; this patch does not claim they are repaired.
- RED t74:8 expected failures and3 passes, exit1, elapsed1.09s. Identity mismatch across point, Worker, Worker generation, attempt, batch and lease generation was previously accepted; file drift was ignored and accepted attempts stayed empty. The old synthetic schema-only shared PASSED manifest was replaced by two distinct public-producer-shaped valid seals without weakening statistics assertions. Scratch/cu/tmp and exact venv tempfile verified.
- GREEN t75:11/11 projection tests, exit0, elapsed1.09s. They prove no cursor advancement on corruption, no uncommitted seal discovery, opaque route byte/hash readback, roles and cross-point artifact disjointness.
- Web RED t76:2 expected failures,9 passes; missing selected-point images/downloads and false FULL_RESTART first-pass label. Its transient log was retained at /tmp/so101-validation-t76-red.log and copied into the registered root as t76-web-red.log; no second evidence directory or deletion was performed.
- GREEN t77:96 Web tests passed; TS/Vite production build exit0, existing large-chunk advisory retained. GREEN t79:12 browser regressions passed in18.9s, including real browser image decoding and opaque numeric link. The fake Runner is regression only, not live/adaptive qualification.
- Complete source gate t78:410 Teleop tests passed under -W error except the two documented exact external compatibility emitters; no warning summary, elapsed9.70s, exit0. New scratch/cw/tmp; exact test venv tempfile verified.
- Real retained EXP-051 source-adapter readback: all4 accepted PASSED attempts projected13 artifacts each (12 inventory files plus original sealed manifest); all52 real ASGI opaque-route responses were checked for byte size and SHA256. No absolute evidence path appears in the campaign projection. Existing durable cursor update was idempotent; store closed. Evidence exp051/source-committed-artifacts-readback.json explicitly labels this source-only diagnostic NOT_INSTALLED_LIVE_QUALIFICATION. Original runtime was clean79a/release16, server domain231/Worker domains181,182,183, GZ_PARTITION=not_applicable. No new simulation or campaign started and EXP-051 is not retroactively qualified.
- Next EXP-052 remains pending: fix terminal owner expiry cancellation, actual immutable manifest/map restoration, corruption recovery fencing and fresh copied installed gates before actual-page sequential acceptance. Parallel/adaptive/conditional retry and complete RGB-D/cloud/controller/physics/scene/cleanup acceptance remain required by the original plan.
- Retained: single registered root, all historical seals/releases/gates and new readbacks. Archived:none. Deletion candidates: cu/cv/cw scratch and historical superseded candidates; none deleted. Publication remains unpushed pending plain trusted confirmation after prior auto-review rejection.

```yaml
checkpoint_id: CP-008
last_valid_experiment: EXP-006
current_hypothesis: Correct accepted artifacts now reach the page; actual manifest cardinality/restoration and exact terminal owner reconciliation are the next independent gates before installed live acceptance.
working_tree_status: only task-owned evidence bridge/API/generated contracts/tests/Web/ledger changes
owned_processes: no task motion/server/browser processes; t74/t75/t77/t78/t79 and diagnostic readback handles terminal
preserved_processes: all unrelated user sessions and processes
next_command: Commit the verified sealed-evidence bridge, then write RED tests for terminal-owner cancellation and immutable manifest map/reload binding.
```

## CP-007 — EXP-051 terminal readback and idle WebSocket disconnect repair

- EXP-051 final status: INVALID for full Web acceptance; its four physical outcomes are independently observed successes, not a completed Task16/17 gate. This supersedes the historical PLANNED/RUNNING entries without rewriting their frozen criteria.
- Clean runtime source: `79a51c1e2c7e680af681f81460d66e9342ab6851`; copied overlay `manifest-source-install-release16`, closed binding `manifest-source-release16-overlay-binding.json`. Server domain231, configured worker domains181/182/183, GZ_PARTITION=not_applicable (MuJoCo).
- Actual page campaign `campaign-02fbb834c64a45a2b9bdc19dce8e2995`, batch `b2bb8`, four anchors, SEQUENTIAL N1/K4. Final API sequence390: COMPLETED, requested4, evaluated4, execution_started4, valid_succeeded4, valid_failed0, qualification_passed=true, batch_cleanup_complete=true. Verified Coordinator state: POINTS_COMPLETE, qualification_passed=true, batch_cleanup_complete=true. The separate upstream dry-run `validation_passed=false` field is not relabelled as true or used as execute qualification.
- Actual page terminal DOM confirms COMPLETED and first pass4/4. Page-owned renewal responses001..025 advanced lease generation1..26; the observation driver did not renew authority. Browser exit metadata0.
- Independent installed upstream `verify_attempt` accepted all four sealed attempt manifests, each containing12 files, with exact AttemptIdentity and inventory/content hashes. First-point initial/terminal images were inspected previously; all-four visual and complete controller/physics semantic audit remain incomplete.
- First unpassed evidence-display boundary: every final API point still has empty attempts/artifact_ids despite accepted sealed evidence. Do not count this run as full artifact/page acceptance or start parallel/adaptive based on it.
- Shutdown observation: exact owned Web PID3547922 hung after first SIGINT at Waiting for background tasks; events route awaited queue.get without receiving disconnect. Second SIGINT cancelled only that server's tasks; server metadata exit0. Host readback found no listener18117 or running Docker containers. User codex/kimi sessions preserved; no broad signals or evidence deletion.
- Additional lifecycle risk observed after browser closure: lease expiry cancellation referenced stale fixed owner without a control socket, causing FIXED_CANCEL_REQUIRES_CONTROL_SOCKET and maintenance failure. Terminal owner reconciliation requires its own regression/fix; not concealed by socket repair.
- RED t72: real ASGI idle socket connect/disconnect timed out while route remained subscribed, 1 failed in2.52s. New NVMe scratch/cs/tmp, exact task venv tempfile verified; exit1, elapsed2.84s.
- GREEN t73: receive-disconnect and send-event tasks now race, owned tasks are cancelled/awaited and subscription removed in finally. Complete source Teleop strict gate402 passed in8.91s, elapsed9.27s, exit0, no warning summary; only the two documented exact external emitters exempted. New scratch/ct/tmp, exact task venv tempfile verified. Installed/live post-fix qualification is not yet run.
- Evidence: registered root `exp051/browser-driver.log`, `campaign-final-api.json`, `ui-13-terminal.txt`, `browser-exit.metadata`, `server.log`, `server-exit.metadata`, all four sealed manifests; `t72.log/.xml/.metadata`, `t73.log/.xml/.metadata`.
- Retained: single existing root and all historical releases/runs. Archived:none. Deletion candidates: used scratch/cs and scratch/ct plus earlier scratch and superseded build/install/log batches; none deleted.
- Publication: still unpublished after recorded auto-review rejection; no retry or alternate transport. Plain renewed trusted publication confirmation required.

```yaml
checkpoint_id: CP-007
last_valid_experiment: EXP-006
current_hypothesis: Accepted upstream sealed manifests must be registered and projected to typed opaque Web artifact metadata; terminal owner reconciliation must prevent expiry cancellation of already-cleaned batches.
working_tree_status: task-owned api.py, test_expert_validation_api.py and this ledger modified
owned_processes: no surviving task Web server, browser, Coordinator, Worker, MuJoCo, MoveIt or running Broker container observed after exact server shutdown
preserved_processes: unrelated codex/kimi tasks and all other user processes
next_command: Commit the verified idle-socket repair; add production sealed-evidence bridge RED tests and terminal-owner reconciliation RED tests before fresh copied release and EXP-052 page acceptance.
```

```yaml
task_id: so101-moveit-expert-validation-web-20260916-e1701375-a01
goal: Implement and validate the approved 17-task Teleop MoveIt expert validation Web plan in MuJoCo simulation only.
success_contract: Source and package gates pass; fresh fixed four-point and adaptive twenty-point campaigns satisfy their authoritative upstream terminal and cleanup contracts; eligible business failure receives an independent FULL_RESTART retry or is explicitly not applicable because all points passed.
worktree: /data/work/ws_moveit/.worktrees/teleop-expert-validation-web
branch: codex/teleop-expert-validation-web
base_commit: e1701375690321bc83b5f30ec044da1847d373aa
current_commit: 1faf89fe8af24805e0cbb0ea605afc51956e3d0a
evidence_root: /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01
confirmed_conclusions:
  - origin/main exactly matched the required documentation commit e1701375690321bc83b5f30ec044da1847d373aa at CP-001.
  - The canonical checkout and new implementation worktree were clean at CP-001.
  - No pre-existing SO-101 application stack or ROS nodes were observed at CP-001.
  - The production server and coordinator accept the final bound copied overlay without symlinks or source fallback.
  - The manifest point source is an explicit closed API enum; t38-final-source passes all 395 Teleop and 35 journal tests under -W error with only the documented system FastAPI/Pydantic compatibility warning excluded and no warning summary.
  - EXP-045 completed all four simulation points as PASSED with authoritative qualification and cleanup, but its production Web API remained at the initial STARTED/UNRUN projection.
  - EXP-045 used the worktree-derived release12 installed MuJoCo fork version 0.1.0 at e4c0241aee52a40727681bd5872c09bf814e941a, not a system 0.0.3 patch overlay.
disproven_routes:
  - At commit 654756ba32cfc0697aff1444c79752ff1e61c4ee, a four-point manifest could not be returned because its source field violated the closed response model.
open_hypotheses:
  - A read-only verified journal projection and authoritative HTTP watcher can synchronize fresh Web progress and terminal state without acquiring upstream coordinator authority.
latest_checkpoint: CP-009
next_experiment: EXP-052
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
status: INVALID
prior_experiment: EXP-021
hypothesis: Separating ephemeral same-user Unix IPC from durable evidence closes the pathname boundary without weakening evidence or runtime ownership.
single_variable: Unix sockets and tokens use the validated same-UID runtime directory; durable evidence layout and all execution semantics are unchanged.
lifecycle: FRESH_ISOLATED_STACK
selection: [task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm]
fixed_config: {worker_count: 1, max_points_per_worker: 4}
prestart_diagnostics:
  - The first release6 dry-run was invalid because its copied binding retained the pre-change coordinator-module hash; provenance rejected it before runtime composition.
  - A fresh binding with all artifact hashes recomputed crossed provenance and short-path allocation, then the Worker rejected its external control token because Worker-side authority reconstruction still assumed evidence_root/ipc.
  - Worker-side authority now binds to the authenticated control socket parent explicitly; no server, simulation, or robot action occurred in either diagnostic.
observed:
  - Release7 safe dry-run completed all four validations with cleanup complete, proving the broker, child-PATH, short-IPC, and Worker-token repairs before the live attempt.
  - The installed service returned health; manifest POST/GET preserved the exact four anchors and source=anchor; N1/K4 preflight admitted; start returned a durable campaign and batch identity.
  - The owned coordinator then exited before writing any batch evidence or starting a Worker, Broker, MoveIt, controller, MuJoCo, or robot action.
  - ExecutionProcessOwner had created the final batch_root before exec, while the upstream coordinator requires its evidence root to be absent so it can claim the batch atomically. The empty pre-created batch directory is the first bad boundary.
  - Shutdown left no validation server, coordinator, simulation, or container process; the durable-store lock was reacquired and released. Its RUNNING owner record is retained as truthful evidence of the lost child rather than rewritten.
first_bad_boundary: DUPLICATE_BATCH_EVIDENCE_ROOT
evidence:
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/short-ipc-green-dryrun.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/short-ipc-green-dryrun2.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/short-ipc-green-dryrun3.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp025/manifest-post.json
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp025/preflight-response.json
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp025/start-response.json
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp025/postinventory.txt
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp025/store-lock-readback.txt
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/t21-owner-red.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/t21-owner-green.log
decision: STOP_FAIL_CLOSED_AND_FIX_BATCH_ROOT_OWNERSHIP
next_experiment: EXP-029
```

### EXP-026 — Fresh same-selection parallel simulation with short IPC

```yaml
experiment_id: EXP-026
status: NOT_RUN
prior_experiment: EXP-025
single_variable: execution_mode=PARALLEL, worker_count=2, max_points_per_worker=2
lifecycle: FRESH_ISOLATED_STACK
selection: [task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm]
observed:
  - Not started because EXP-025 stopped at the coordinator evidence-root ownership boundary before any Worker or simulation startup.
decision: BLOCKED_BY_EXP_025_INVALID
next_experiment: EXP-027
```

### EXP-027 — Fresh twenty-point adaptive simulation with short IPC

```yaml
experiment_id: EXP-027
status: NOT_RUN
prior_experiment: EXP-026
single_variable: execution_mode=ADAPTIVE with preferred W8 and fallback [6, 4, 2, 1]
lifecycle: FRESH_ISOLATED_STACK
observed:
  - Not started because the repaired sequential campaign did not reach a valid runtime result.
decision: BLOCKED_BY_EXP_025_INVALID
next_experiment: EXP-028
```

### EXP-028 — Conditional FULL_RESTART retry with short IPC

```yaml
experiment_id: EXP-028
status: NOT_APPLICABLE
prior_experiment: EXP-027
single_variable: FULL_RESTART retry of eligible FAILED points only
lifecycle: FRESH_ISOLATED_STACK_PER_POINT
observed:
  - No valid first-pass terminal result or eligible FAILED point exists; no retry was manufactured.
decision: LIVE_RETRY_NOT_APPLICABLE_NO_VALID_FIRST_PASS
```

### EXP-029 — Coordinator-owned batch root and fresh sequential simulation

```yaml
experiment_id: EXP-029
status: INVALID
prior_experiment: EXP-025
hypothesis: Leaving the final fixed batch evidence root absent until coordinator exec restores atomic evidence ownership and permits the exact four-anchor N1/K4 campaign.
single_variable: ExecutionProcessOwner creates only batch_root.parent for fixed starts; the coordinator creates batch_root itself.
lifecycle: FRESH_ISOLATED_STACK
selection: [task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm]
fixed_config: {worker_count: 1, max_points_per_worker: 4}
success_criteria: Four authoritative PASSED results with complete runtime, artifact, cleanup, Web, and independently inspected visual evidence.
observed:
  - Release8 passed the five-package copy-install build, all 46 installed Teleop CTest commands, and 436 underlying tests with no failures.
  - Health, capabilities, lease, exact four-anchor manifest POST/GET, and N1/K4 preflight all succeeded; start returned campaign-ae2346f120344a128717165a529d89c2 and batch bc3f0.
  - The coordinator atomically created its previously absent batch root, verified the bound release8 provenance, allocated Worker resources and short IPC, started a healthy Broker, and wrote a Worker spec.
  - The Worker exited before registering or writing a result. The coordinator entered SUPERVISOR_SHUTDOWN with all four points UNRUN; cleanup removed owned processes and runtime IPC but could not prove Broker-container cleanup because no hardened container ID had been retained.
  - Existing ExecutionProcessOwner routing sent coordinator stdout and stderr to /dev/null, so the exact Worker exception was not auditable. A no-run construction probe passed, narrowing the failure to the Worker run/control phase.
  - The validation server stopped; no coordinator, Worker, Broker container, MoveIt, controller, or MuJoCo process survived, and the durable-store lock was reacquired and released.
first_bad_boundary: WORKER_RUNTIME_EARLY_EXIT_WITHOUT_DURABLE_PROCESS_LOG
evidence:
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp029/manifest-post.json
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp029/preflight-response.json
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp029/start-response.json
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp029/campaigns/campaign-ae2346f120344a128717165a529d89c2/bc3f0/coordinator/aggregate_results.json
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp029/campaigns/campaign-ae2346f120344a128717165a529d89c2/bc3f0/cleanup-gates.json
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp029/worker-construction-probe.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp029/postinventory.txt
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp029/store-lock-readback.txt
decision: STOP_FAIL_CLOSED_AND_RETAIN_COORDINATOR_PROCESS_LOG
next_experiment: EXP-033
```

### EXP-030 — Fresh same-selection parallel simulation after batch-root repair

```yaml
experiment_id: EXP-030
status: NOT_RUN
prior_experiment: EXP-029
single_variable: execution_mode=PARALLEL, worker_count=2, max_points_per_worker=2
lifecycle: FRESH_ISOLATED_STACK
selection: [task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm]
observed:
  - Not started because EXP-029 stopped at an unobservable Worker runtime early exit.
decision: BLOCKED_BY_EXP_029_INVALID
next_experiment: EXP-031
```

### EXP-031 — Fresh twenty-point adaptive simulation after batch-root repair

```yaml
experiment_id: EXP-031
status: NOT_RUN
prior_experiment: EXP-030
single_variable: execution_mode=ADAPTIVE with preferred W8 and fallback [6, 4, 2, 1]
lifecycle: FRESH_ISOLATED_STACK
observed:
  - Not started because no valid sequential runtime result exists after EXP-029.
decision: BLOCKED_BY_EXP_029_INVALID
next_experiment: EXP-032
```

### EXP-032 — Conditional FULL_RESTART retry after batch-root repair

```yaml
experiment_id: EXP-032
status: NOT_APPLICABLE
prior_experiment: EXP-031
single_variable: FULL_RESTART retry of eligible FAILED points only
lifecycle: FRESH_ISOLATED_STACK_PER_POINT
observed:
  - No authoritative first-pass business result or eligible FAILED point exists; no retry was manufactured.
decision: LIVE_RETRY_NOT_APPLICABLE_NO_VALID_FIRST_PASS
```

### EXP-033 — Durable coordinator diagnostics and fresh sequential simulation

```yaml
experiment_id: EXP-033
status: INVALID
prior_experiment: EXP-029
hypothesis: A private exclusive coordinator process log will expose the exact Worker failure while preserving coordinator-owned batch-root creation and bounded file-descriptor ownership.
single_variable: ExecutionProcessOwner routes merged coordinator stdout/stderr to a 0600 O_EXCL campaign log instead of /dev/null.
lifecycle: FRESH_ISOLATED_STACK
selection: [task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm]
fixed_config: {worker_count: 1, max_points_per_worker: 4}
success_criteria: Four authoritative PASSED results, or a precise first bad boundary retained in the coordinator log, with complete owned-process readback.
observed:
  - Release9 started the dedicated service from a clean bound source and repeated successful health, capability, lease, exact four-anchor manifest, and admitted N1/K4 preflight boundaries.
  - The private 0600 coordinator log retained the exact first error: RUNTIME_ROOT_OUTSIDE_BATCH_IPC.
  - The short-IPC composition supplied /run/user/1000/so101-ba11a/broker, but the Broker container argument validator still accepted only durable <batch>/ipc paths. The two valid security contracts were not yet connected.
  - No Worker, MoveIt, controller, or MuJoCo process started. Post-failure inventory found no owned process, runtime IPC directory, or Broker container; the durable-store lock was reacquired and released.
first_bad_boundary: RUNTIME_ROOT_OUTSIDE_BATCH_IPC
evidence:
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp033/manifest-post.json
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp033/preflight-response.json
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp033/start-response.json
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp033/campaigns/campaign-86c96e6a711842ad9d119fdc5321ee3d/ba11a.coordinator.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp033/postinventory.txt
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp033/store-lock-readback.txt
decision: STOP_FAIL_CLOSED_AND_BIND_BROKER_TO_VALIDATED_EXTERNAL_IPC_ROOT
next_experiment: EXP-037
```

### EXP-034 — Fresh same-selection parallel simulation after diagnostic repair

```yaml
experiment_id: EXP-034
status: NOT_RUN
prior_experiment: EXP-033
single_variable: execution_mode=PARALLEL, worker_count=2, max_points_per_worker=2
lifecycle: FRESH_ISOLATED_STACK
selection: [task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm]
observed:
  - Not started because EXP-033 failed before Worker or simulation startup.
decision: BLOCKED_BY_EXP_033_INVALID
next_experiment: EXP-035
```

### EXP-035 — Fresh twenty-point adaptive simulation after diagnostic repair

```yaml
experiment_id: EXP-035
status: NOT_RUN
prior_experiment: EXP-034
single_variable: execution_mode=ADAPTIVE with preferred W8 and fallback [6, 4, 2, 1]
lifecycle: FRESH_ISOLATED_STACK
observed:
  - Not started because no valid sequential runtime result exists after EXP-033.
decision: BLOCKED_BY_EXP_033_INVALID
next_experiment: EXP-036
```

### EXP-036 — Conditional FULL_RESTART retry after diagnostic repair

```yaml
experiment_id: EXP-036
status: NOT_APPLICABLE
prior_experiment: EXP-035
single_variable: FULL_RESTART retry of eligible FAILED points only
lifecycle: FRESH_ISOLATED_STACK_PER_POINT
observed:
  - No authoritative first-pass business result or eligible FAILED point exists; no retry was manufactured.
decision: LIVE_RETRY_NOT_APPLICABLE_NO_VALID_FIRST_PASS
```

### EXP-037 — Validated external Broker IPC and fresh sequential simulation

```yaml
experiment_id: EXP-037
status: INVALID
prior_experiment: EXP-033
hypothesis: Explicitly binding the Broker runtime mount to the validated same-UID, 0700, batch-specific external IPC root closes the container argument boundary without exposing Worker tokens or accepting arbitrary external paths.
single_variable: container_run_argv accepts an explicit runtime_ipc_root only when it equals /run/user/<uid>/so101-<batch_id> and the Broker child name matches its generation.
lifecycle: FRESH_ISOLATED_STACK
selection: [task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm]
fixed_config: {worker_count: 1, max_points_per_worker: 4}
success_criteria: Four authoritative PASSED results with complete runtime, artifact, cleanup, Web, and independently inspected visual evidence.
prestart_tests:
  - Broker container argument and composition isolation: 26 passed.
  - Focused external-root allow/reject and mount-isolation set: 13 passed.
  - Production composition forwards the exact validated external IPC root and removes its ephemeral directory: 1 passed.
  - Full parallel CLI diagnostic: 99 passed and four unrelated retained failures, led by the existing resume authority-order boundary and subsequent strict ResourceWarnings.
evidence:
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/t23-broker-ipc-red.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/t23-broker-ipc-green4.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/t23-broker-composition-green.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/t23-parallel-cli-green.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp037/manifest-post.json
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp037/preflight-response.json
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp037/start-response.json
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp037/campaigns/campaign-4a5dfa57289649708421cc566b080af8/bc800.coordinator.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp037/campaigns/campaign-4a5dfa57289649708421cc566b080af8/bc800/workers/worker-01/worker-run-results.json
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp037/postinventory.txt
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp037/store-lock-readback.txt
observed:
  - Release10 passed health, capability, lease, exact four-anchor manifest, admitted N1/K4 preflight, and campaign-start boundaries.
  - The Broker accepted the validated short IPC root, published readiness, and connected worker-01; MoveIt and the MuJoCo task station started.
  - ros2_control_node then exited with SIGSEGV in mj_contactForce called by SimulationEvidencePlugin::EvidenceBuilder::build from the controller write-path plugin update.
  - The update path receives an mj_copyData control snapshot; current unit tests cover authoritative mjData after mj_forward but do not cover contact-force extraction from a copied snapshot.
  - No point execution started. Cleanup removed the Broker container, Worker/coordinator processes, and /run/user/1000/so101-bc800; the service port was released and the durable-store lock was reacquired.
first_bad_boundary: COPIED_MJDATA_CONTACT_FORCE_SEGFAULT
decision: STOP_FAIL_CLOSED_AND_FIX_COPIED_SNAPSHOT_CONTACT_FORCE_EXTRACTION
next_experiment: EXP-038
```

### EXP-038 — Fresh same-selection parallel simulation after Broker IPC repair

```yaml
experiment_id: EXP-038
status: NOT_RUN
prior_experiment: EXP-037
single_variable: execution_mode=PARALLEL, worker_count=2, max_points_per_worker=2
lifecycle: FRESH_ISOLATED_STACK
selection: [task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm]
observed:
  - Not started because EXP-037 failed before controller readiness and point execution.
decision: BLOCKED_BY_EXP_037_INVALID
next_experiment: EXP-039
```

### EXP-039 — Fresh twenty-point adaptive simulation after Broker IPC repair

```yaml
experiment_id: EXP-039
status: NOT_RUN
prior_experiment: EXP-038
single_variable: execution_mode=ADAPTIVE with preferred W8 and fallback [6, 4, 2, 1]
lifecycle: FRESH_ISOLATED_STACK
observed:
  - Not started because no valid sequential runtime result exists after EXP-037.
decision: BLOCKED_BY_EXP_037_INVALID
next_experiment: EXP-040
```

### EXP-040 — Conditional FULL_RESTART retry after Broker IPC repair

```yaml
experiment_id: EXP-040
status: NOT_APPLICABLE
prior_experiment: EXP-039
single_variable: FULL_RESTART retry of eligible FAILED points only
lifecycle: FRESH_ISOLATED_STACK_PER_POINT
observed:
  - No authoritative first-pass business result or eligible FAILED point exists; no retry was manufactured.
decision: LIVE_RETRY_NOT_APPLICABLE_NO_VALID_FIRST_PASS
```

### EXP-041 — Copied-contact snapshot safety and fresh sequential simulation

```yaml
experiment_id: EXP-041
status: INVALID
prior_experiment: EXP-037
hypothesis: Contact-force evidence can be extracted safely from the controller write-path copy without dereferencing absent copied solver storage, while authoritative physics-step evidence retains exact forces.
single_variable: Contact-force extraction rejects a copied snapshot whose active constraint has no solver-force storage, proven by a copied-contact regression before rebuilding a fresh bound overlay.
lifecycle: FRESH_ISOLATED_STACK
selection: [task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm]
fixed_config: {worker_count: 1, max_points_per_worker: 4}
prestart_tests:
  - Valid RED copied-contact snapshot regression exited 139 in mj_contactForce.
  - GREEN copied-contact snapshot regression passed under gdb readback after the guard.
  - Full simulation-evidence binary passed 21 tests; package CTest passed 1 of 1.
evidence:
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/t24-copied-contact-red3.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/t24-copied-contact-green-gdb.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/t24-simulation-evidence-full-green2.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/t24-support-ctest-green2.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/manifest-source-test-release11-support2.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/manifest-source-test-result-release11-support2.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp041/manifest-post.json
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp041/start-response.json
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp041/campaigns/campaign-1a0eecd6709d4b05a542988ea0d0f0eb/b2017.coordinator.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp041/campaigns/campaign-1a0eecd6709d4b05a542988ea0d0f0eb/b2017/workers/worker-01/worker-run-results.json
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp041/postinventory.txt
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/exp041/store-lock-readback.txt
observed:
  - Release11 passed health, capability, lease, exact four-anchor source assertions, admitted N1/K4 preflight, and campaign-start boundaries.
  - The controller manager and all three controllers became active, MoveIt became ready, and the copied-contact SIGSEGV did not recur.
  - worker-01 then failed the initial evidence gate at reset_point with `initial evidence unavailable`; no point execution started.
  - The initial-snapshot retry calls pause(true), but MujocoSimulation returned early when already paused without dispatching a new authoritative state snapshot, so a missed or contended first snapshot could not be recovered idempotently.
  - Cleanup stopped the owned stack, released the service port, removed the short runtime IPC tree, and allowed the durable-store lock to be reacquired.
first_bad_boundary: PAUSED_NOOP_RETRY_DID_NOT_REPUBLISH_STATE_SNAPSHOT
decision: STOP_FAIL_CLOSED_AND_FIX_IDEMPOTENT_PAUSED_SNAPSHOT_RETRY
next_experiment: EXP-042
```

### EXP-042 — Fresh same-selection parallel simulation after paused-snapshot repair

```yaml
experiment_id: EXP-042
status: NOT_RUN
prior_experiment: EXP-041
single_variable: execution_mode=PARALLEL, worker_count=2, max_points_per_worker=2
lifecycle: FRESH_ISOLATED_STACK
selection: [task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm]
observed:
  - Not started because EXP-041 failed before initial evidence acceptance and point execution.
decision: BLOCKED_BY_EXP_041_INVALID
next_experiment: EXP-043
```

### EXP-043 — Fresh twenty-point adaptive simulation after paused-snapshot repair

```yaml
experiment_id: EXP-043
status: NOT_RUN
prior_experiment: EXP-042
single_variable: execution_mode=ADAPTIVE with preferred W8 and fallback [6, 4, 2, 1]
lifecycle: FRESH_ISOLATED_STACK
observed:
  - Not started because no valid sequential runtime result exists after EXP-041.
decision: BLOCKED_BY_EXP_041_INVALID
next_experiment: EXP-044
```

### EXP-044 — Conditional FULL_RESTART retry after paused-snapshot repair

```yaml
experiment_id: EXP-044
status: NOT_APPLICABLE
prior_experiment: EXP-043
single_variable: FULL_RESTART retry of eligible FAILED points only
lifecycle: FRESH_ISOLATED_STACK_PER_POINT
observed:
  - No authoritative first-pass business result or eligible FAILED point exists; no retry was manufactured.
decision: LIVE_RETRY_NOT_APPLICABLE_NO_VALID_FIRST_PASS
```

### EXP-045 — Idempotent paused-snapshot retry and fresh sequential simulation

```yaml
experiment_id: EXP-045
status: INVALID
prior_experiment: EXP-041
hypothesis: A repeated pause(true) request can recover a missed initial evidence snapshot by refreshing the control snapshot and dispatching one authoritative paused state snapshot without duplicating the pause lifecycle transition.
single_variable: An already-paused set_pause request republishes control and authoritative state snapshots while preserving the existing no-duplicate-pause-notification contract.
lifecycle: FRESH_ISOLATED_STACK
selection: [task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm]
fixed_config: {worker_count: 1, max_points_per_worker: 4}
prestart_tests:
  - Valid RED focused regression observed no state_snapshot on the repeated pause request.
  - GREEN focused regression passed 1 of 1 and the full MujocoSimulation binary passed 42 of 42.
evidence:
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/t25-pause-retry-red2.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/t25-pause-retry-green2-build.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/t25-pause-retry-green2.log
  - /data/work/so101-evidence/moveit-expert-validation-web/20260916-e1701375-a01/t25-mujoco-simulation-full-green2.log
observed:
  - Campaign campaign-d54278fee68f42e59c9c0ca8242d0bd7 and batch b2b97 ran through the release12 installed coordinator/core plugin path.
  - All four selected points were PASSED; the coordinator terminal reason was POINTS_COMPLETE, qualification_passed and batch_cleanup_complete were true, and Worker worker-01 was STOPPED.
  - Independent initial/terminal RGB inspection showed the distinct anchor positions and the cup in the red target circle after each completed attempt.
  - No owned runtime process, port, container, short IPC root, or store lock survived cleanup.
  - campaign-final-api.json still reported STARTED with all four points UNRUN and cleanup false because ProductionExpertValidationService cached only its initial projection.
  - Readback of the actual executable/package.xml proved the worktree-derived MuJoCo fork version 0.1.0. The old so101-0.0.3-r8 git-describe prefix was only the nearest ancestor tag.
new_boundary: PRODUCTION_WEB_PROJECTION_STALE
decision: INVALID_WEB_ACCEPTANCE_DESPITE_VALID_FOUR_POINT_SIMULATION
next_experiment: EXP-046
```

### EXP-046 — Verified journal/Web terminal synchronization

```yaml
experiment_id: EXP-046
status: PLANNED
prior_experiment: EXP-045
hypothesis: Read-only verified journal replay plus authoritative HTTP watching makes new Web campaigns progress to their actual upstream terminal state.
single_variable: Fixed-mode Web projection and watcher synchronization; the release12 MuJoCo 0.1.0 core behavior remains unchanged.
lifecycle: FRESH_ISOLATED_STACK
selection: [task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm]
fixed_config: {worker_count: 1, max_points_per_worker: 4}
success_criteria:
  - Installed Web API reaches COMPLETED with four PASSED points, evaluated/execution counts of four, qualification_passed true, and batch_cleanup_complete true.
  - New-campaign page watching reads authoritative HTTP projections and renders terminal point/Worker progress.
  - Independent sealed image, MoveIt/controller, physics, Planning Scene, artifact-manifest and cleanup readbacks agree.
invalid_criteria:
  - Mixed/unbound install, wrong source commit, stale Web state, missing independent evidence, or surviving owned runtime processes.
prestart_tests:
  - t26-web-projection-red reproduced missing read-only replay and rejection of the real sealed-directory reference.
  - t26-web-projection-green6 passed 2 of 2; t28-related-full passed 38 of 38.
  - t27-production-projection-red reproduced STARTED after a terminal journal; GREEN passed 1 of 1.
  - EXP-045's real 389-event journal now projects COMPLETED, four PASSED points, qualification and cleanup true, with its verified final frame cursor.
  - t34-web-watch-red reproduced absent new-campaign watching and absent no-hint HTTP polling; GREEN passed 9 of 9.
  - t35-web-full passed 91 tests and t35-web-build completed TypeScript/Vite output.
decision: RUN_AFTER_FINAL_REGRESSION_SCOPED_COMMITS_FRESH_COPY_BUILD_AND_BINDING
next_experiment: EXP-047
```

### EXP-047 — Same-selection fixed parallel Web smoke

```yaml
experiment_id: EXP-047
status: PLANNED
prior_experiment: EXP-046
single_variable: Change the same immutable four-point selection from N1/K4 to N2/K2.
lifecycle: FRESH_ISOLATED_STACK
success_criteria:
  - Two isolated Workers execute the exact same selection without sequential fallback, with authoritative qualification and cleanup.
  - Web progress, opaque artifacts, per-Worker domain/session/generation/lease evidence, shared Broker identities and sealed physical evidence agree.
invalid_criteria: Unqualified mode, mixed provenance, cross-Worker evidence or pose leak, missing independent evidence, or surviving owned processes.
decision: RUN_ONLY_AFTER_EXP_046_VALID_AND_VERIFIED_UPSTREAM_PARALLEL_QUALIFICATION
next_experiment: EXP-048
```

### EXP-048 — Exact twenty-point adaptive first pass

```yaml
experiment_id: EXP-048
status: PLANNED
prior_experiment: EXP-047
single_variable: Use the production adaptive wrapper and exact twenty-point ai_station_baseline_v1 selection.
lifecycle: FRESH_ISOLATED_STACK
config: {preferred_worker_count: 8, fallback_worker_counts: [6, 4, 2, 1], initial_points_per_worker: 3, worker_start_timeout_s: 120, max_infra_attempts_per_point: 5, yolo_executor_count: 2}
success_criteria:
  - Runner-authoritative twenty-point terminal results, attempts, levels, fallbacks and generations reach the Web with complete cleanup and independent sealed visual/numeric evidence.
  - Fixed K and fixed-mode resource admission are absent; observations do not select tiers.
invalid_criteria: Missing verified upstream fault/performance/twenty-point qualification, alternate execution path, mixed provenance, or missing independent evidence.
decision: RUN_ONLY_AFTER_FIXED_SMOKES_VALID_AND_VERIFIED_UPSTREAM_ADAPTIVE_QUALIFICATION
next_experiment: EXP-049
```

### EXP-049 — Conditional business-failure FULL_RESTART retry

```yaml
experiment_id: EXP-049
status: PLANNED
prior_experiment: EXP-048
single_variable: Independently retry the earliest eligible business FAILED point through confirmed fixed N1/K1 FULL_RESTART.
lifecycle: FULL_RESTART
success_criteria:
  - New batch/attempt/epoch/session/domain/process identities and cleanup-before-next-start; first-pass statistics remain immutable.
  - All-success first pass records LIVE_RETRY_NOT_APPLICABLE_ALL_SUCCEEDED without manufacturing a failure.
invalid_criteria: Retry of unsafe cleanup, INFRA_FAILED, INFRA_INTERRUPTED, INDETERMINATE, UNRUN or PASSED.
decision: WAIT_FOR_AUTHORITATIVE_ADAPTIVE_TERMINAL_CLASSIFICATION
next_experiment: NONE
```

## Journal/Web synchronization repair checkpoint (in progress)

- The production Web service did not consume its existing coordinator event reader. Fixed campaign GET/list now verify read-only journal frames and committed result references, merge point/Worker deltas, preserve upstream qualification policy, and persist the final accepted cursor without taking a coordinator lock or rotating its epoch.
- The real runtime result reference names a sealed directory whose SHA256 covers `attempt_result_manifest.json`. The reader now supports that contract while retaining regular-file and hash checks.
- New campaign pages previously never started a watcher, and a watcher with no hints never refreshed. The app now watches both new and restored campaigns; the client polls HTTP every two seconds and refreshes on every newer hint without treating hints as terminal truth.
- The new production projection test is explicitly registered in CMake after t33-layout-red proved its omission.
- Invalid/superseded command attempts retained: t26 GREEN 1/2 lacked ROS imports; GREEN 3 loaded the copied old demo package; GREEN 4/5 stopped at source-binding preflight; t29 strict 1/2 failed to exempt the exact external compatibility warning; t30 combined collection collided on duplicate module names; t30-demo-full2 was terminated as source-path binding was invalid (166 seconds, exit 143).
- t32-demo-full completed 3,083 passes and one skip with four failures in 339.70 seconds: stale dependency-lock pin, a child loading copied rather than source modules, a genuine resume initialization-order bug, and an existing launch cleanup timing failure. The first three have targeted fixes pending focused readback; the launch case will be replayed without changing its acceptance semantics.
- Ordinary demo fork warnings remain outside the requested Teleop warning scope. No benchmark suite was collected.
- All t26 through t36 scratch trees are retained deletion candidates after readback. No evidence was deleted or archived; the registered durable root is unchanged.
- t36-focused passed all 66 focused cases, including all four prior demo failures under their original acceptance assertions. The only two warnings were the documented external FastAPI/Pydantic emitters from collecting two package trees without package-local filters.
- t37-active-red reproduced the actual active_attempt string/Worker lease contract mismatch. Fixed projections now match active attempt IDs through authoritative Worker leases and count physical execution only from ATTEMPT_STARTED, never from a lease/attempt allocation counter.
- t38-final-source passed 430 tests (395 complete Teleop plus 35 journal), exit zero, 8.64 seconds, with the exact external compatibility warning excluded and no warning summary. The new active-owner and torn-tail tests prove that projection readers do not acquire, rotate, or repair coordinator authority.
- t39-browser passed all 11 browser tests in 24.7 seconds. The full Web unit gate passed 91 tests and the TypeScript/Vite build passed; its existing large-chunk advisory is unrelated to pytest warnings.
- Commit 2d85d53594df1b5b7292aba6d959f4a51bad398f synchronizes both dependency locks and the backend contract to the actual 0.1.0 gitlink, uses the allocator IPC root before authority construction during resume, and explicitly binds the no-rendering child test to its asserted source root.
- t37/t38 scratch trees and t39 browser output are retained; scratch remains a deletion candidate only. No push, merge, evidence deletion, or real-robot action occurred.

## Release13 installed verification continuation

- The user now requests publication before continuing to the original plan endpoint. Gitee readback found no existing Teleop task branch; the MuJoCo remote retains c16b5a5 on its earlier parallel-validation branch. Auto-review rejected the scoped publication command using the old handoff's prohibition; no push occurred, and renewed explicit publication confirmation was requested. Local verification continues without remote mutations.
- Clean implementation HEAD 97a789311c220f554d4958ba8fdee9e668331868 contains the journal/Web synchronization repair. Release13 copied installation built all seven selected packages in 55.7 seconds; the 0.1.0 MuJoCo gitlink remains e4c0241aee52a40727681bd5872c09bf814e941a.
- The release13 binding was generated from new installed artifact SHA256 values. ProductionRuntimeLayout resolves the clean worktree commit and release13 coordinator, and all five checked package prefixes are exact non-symlink release13 prefixes.
- t40 exited before testing because ROS setup is incompatible with shell nounset. t41 passed all 47 Teleop CTest entries, but Demo collection failed before execution because the clean shell omitted the existing ML venv's torch dependency. This is not a passing Demo gate.
- t42 repeats only the ordinary Demo package gate with the existing Grounded-SAM dependency site-packages appended after release13/ROS imports. Its unique NVMe scratch is scratch/t42-release13-demo-colcon-001/tmp; the exact test Python must verify tempfile before collection. No benchmark or evidence deletion is authorized.
- EXP-046 remains PLANNED until the installed package gates and runtime ownership preflight are complete. The previous simulation processes were stopped; this continuation has started no simulation stack.

## CP-004 — Installed readback and cleanup test budget correction

- Installed release13 Teleop JUnit readback: 47 XML files, 394 test cases, zero failures/errors/skips. Installed core colcon t44: one CTest, 42 gtest cases, zero failures, 4.11 seconds; the optional lidar dependency hook now resolves.
- t43 completed 3,090 installed Demo cases with 68 failures in 412 seconds. Its shell bootstrap did not preflight colcon's actual /usr/bin/python3 and omitted venv Pydantic 2; long scratch paths caused UDS failures. Text Agent's separate provenance tests require a module-side Git checkout and reject a copied external install. This probe is retained and is not a passing package gate; colcon's default exit zero does not override JUnit failures.
- Short scratch t45 passes all 285 allocator/CLI/IPC cases without implementation or assertion changes (6.53 seconds). Related installed t46 produced 1,272 passes and two failures in cleanup/concurrent claims; t48 observers preserved the original calls/results and reproduced both original assertions as passing, with the expected loser rejected ROS_DOMAIN_CLAIMED:181. The historical t46 triggers remain unconfirmed, not silently reclassified as successful.
- After the full ML gate stopped, the same unmodified 1,274 related installed cases passed under colcon t51 (66.50 seconds). /usr/bin/python3 preflight and Pydantic 2.13.4 were verified, return-code-on-test-failure was enabled, and ROS logs used scratch/c9/ros-home/log.
- Full source t47: 3,089 passes, one failure, four existing Demo fork warnings, 365.93 seconds. Its failing receipt has machine_accepted=true and no remaining process, but records cleanup timeout after every 50ms test-only signal budget. Production budgets are SIGINT 10s, TERM 5s and KILL 5s.
- t49 RED deterministically reproduces rejection of a controlled 150ms SIGINT recovery under the 50ms fixture (one failure). The normal real-process fixture now leaves production budgets intact; only the dedicated escalation fault case requests the original fast budgets. t50 GREEN and adjacent launch gate: 49/49, eight seconds, no warnings. No production timeout or physical acceptance threshold changed.
- Earlier t43/t47 LaunchService default logs also referenced /home/lenovo/.ros/log; their console evidence is retained here. All subsequent test/runtime shells explicitly bind ROS_HOME and ROS_LOG_DIR to the registered root. No default-log tree was deleted.
- Auto-review rejected publication again after the submodule increment was checked (only 10 added and two removed source/test lines). No external code publication occurred; a plain renewed user confirmation remains required by auto-review.

```yaml
checkpoint_id: CP-004
last_valid_experiment: EXP-001
current_hypothesis: The unchanged production cleanup budgets remove the normal real-process fixture's false deadline failure; a fresh full source gate must still prove this.
working_tree_status: Only the task-owned cleanup test and this ledger pending scoped commit.
owned_processes: NONE; all launched test children have completed their scoped cleanup.
preserved_processes: codex/kimi tmux and Software Updater desktop windows are unrelated and untouched.
next_command: Commit the verified fixture/ledger changes, run a fresh full source gate, and build a new copied release14 overlay from that clean commit before EXP-046.
```

Retained: the registered 20260916-e1701375-a01 root, release13 and all t40-t51 evidence. Archived: none. Deletion candidates after readback: all used scratch trees, including c2-c9; no deletion authorized. EXP-046/047/048/049 remain PLANNED, not runtime successes.

## EXP-046 boundary update — Installed SPA asset URLs

- EXP-046 is INVALID before campaign creation: the real release14 page returned index.html, but its absolute /assets JS/CSS URLs received 404. The heading never rendered; the browser driver exited 1. No Worker, Broker or simulation started.
- Source is clean 7fd1ef6ea61f652793c2ef05b9dfcb254fb960fe; all five package prefixes resolve to manifest-source-install-release14, both MuJoCo packages declare 0.1.0. Server PID 3506067 used the release14 installed launcher, ROS_DOMAIN_ID=231, GZ_PARTITION=not_applicable. Native window inventory identified owned Chrome ID 50331652; capture after driver shutdown correctly failed instead of reusing pixels. The fresh page-failure.png was inspected and is blank.
- Final source ordinary Demo t52 passed 3,091/3,091 in 342.98s, with four known Demo detector fork warnings; installed Teleop t53 passed 47/47 CTest, core t54 passed its simulation CTest, and installed related Demo t55 passed 1,274/1,274 in 60.58s. All scratch ca/cc/cd/ce trees are retained deletion candidates. No benchmark collected.
- Retained command diagnostics are not source regressions: initial browser launcher searched an absent bundled browser instead of the project's /usr/bin/google-chrome; dry-run 001 mistyped a model hash, dry-run r selected 20 points with capacity four, and dry-run s omitted the coordinator console directory from PATH. Production supervisor explicitly prepends that directory. All probes are retained under exp046.
- Confirmed first-bad boundary: shared Vite build emits /assets URLs, regular Teleop mounts /assets, but dedicated validation API mounted only /expert-validation/assets. Add a RED route regression, serve the build's real URLs, preserve /tasks disablement and Web execution authority, then rebuild a fresh copied overlay.

```yaml
experiment_id: EXP-050
status: PLANNED
prior_experiment: EXP-046
hypothesis: Serving the shared Vite build's absolute asset URLs lets the actual installed validation page render and reach the verified fixed journal projection.
single_variable: Dedicated SPA static asset route repair; no coordinator, Worker, model, physics or authority change.
lifecycle: FULL_RESTART
selection: [task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm]
fixed_config: {worker_count: 1, max_points_per_worker: 4}
success_criteria:
  - Real page loads all production JS/CSS, creates the frozen four-point manifest, and starts only after lease and preflight.
  - Actual API and page reach the authoritative terminal state, with independent sealed visual/numeric/cleanup evidence.
invalid_criteria:
  - Wrong source/install identity, blank/stale page, missing sealed evidence, or surviving owned descendants.
decision: RUN_AFTER_RED_GREEN_AND_FRESH_COPY_BUILD
next_experiment: EXP-047
```

## CP-005 — SPA assets RED/GREEN and clean shutdown

- t56 RED: the real FastAPI regression failed with 404 instead of 200 for the shared Vite build's /assets URL. Production now mounts /assets from the explicitly configured static assets directory, while preserving the validation-prefixed route and disabled /tasks surface. No coordinator, lease or simulator behavior changed.
- t57 GREEN: dedicated plus regular API tests passed 19/19, including actual JS/CSS content and missing-file 404. t59 complete source warning gate passed 396/396 in 8.16s, no warning summary. Only the established external fastapi.openapi.models and pydantic_core.core_schema emitters were exempted. t58 is an invalid collection bootstrap: -W message handling treated the attempted wildcard filter literally; the external warning was not suppressed.
- Idle owned server PID 3506067 received SIGINT after GET campaigns returned an empty list; server exit code zero and port 18115 was released. The owned browser launcher exited 1 after the heading timeout, and its tmux session disappeared. No campaign or MuJoCo/MoveIt/Worker/Broker started. Unrelated Software Updater and codex/kimi remain untouched.

```yaml
checkpoint_id: CP-005
last_valid_experiment: EXP-001
current_hypothesis: The new absolute Vite asset mount repairs the real blank page; fresh installed/browser acceptance must still prove it and the journal terminal sync.
working_tree_status: Only the task-owned API, API test and experiment ledger pending scoped commit.
owned_processes: NONE
preserved_processes: codex/kimi tmux and Software Updater windows.
next_command: Commit the route/test/ledger changes; build a fresh copied release15 overlay, bind its clean source commit, run installed Teleop gates, then execute EXP-050 through the actual page.
```

Retained: the registered root, exp046 invalid page evidence and all t52-t59 gates/diagnostics. Archived: none. Deletion candidates: scratch ca-cj as used, and superseded copied build/install/log directories; no evidence deleted. Push remains unpublished after auto-review rejection and requires plain renewed publication confirmation.

## EXP-050 update and EXP-051 pre-registration

- EXP-050 is INVALID before campaign creation: the owned driver timed out its 120s visual-approval wait while host screenshot review was pending. No Start request exists and GET campaigns returned []. Correct the temporary driver by checking the rendered setup before acquiring lease/preflight, not by extending server authority.
- The installed static-route repair is OBSERVED: actual release15 JS/CSS load, four-point manifest and lease POSTs and fixed preflight return 200. Native window 50331652 (Chrome's Unjvu6 profile, not the previous exp046 window despite reused X11 ID) was freshly captured under exp050/gui-prestart/20260916T161713-4d632d786038 and inspected: SEQUENTIAL N1/K4, capacity4/4, seed20260911, rendered setup and preflight status.
- Independent read-only SQLite at monotonic1366743888400364 found lease generation1 still ACTIVE, expiry1366560524918368, despite more than30s without browser traffic. The production API has no maintenance lifespan; expire_due is never invoked. The actual Web app has no renewal path. renew currently accepts a matching ACTIVE lease after expiry, so it can resurrect stale authority. These contradict the approved design's renewable, server-expiring lease contract; add RED tests before fixes.
- Owned idle server PID3522832 received SIGINT after confirming [] campaigns. No Worker/Broker/MoveIt/MuJoCo started. Retain browser timeout, native pixels, complete DOM snapshots, model/provenance/dry-run and release15 gate artifacts under the registered root.

```yaml
experiment_id: EXP-051
status: PLANNED
prior_experiment: EXP-050
hypothesis: Server-managed expiry and actual-page renewal preserve the approved lease contract and let fresh four-point page acceptance reach authoritative terminal state.
single_variable: Web lease lifecycle integration and expiry enforcement; physics and upstream 0.1.0 core unchanged.
lifecycle: FULL_RESTART
selection: [task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm]
fixed_config: {worker_count: 1, max_points_per_worker: 4}
success_criteria:
  - Actual page renews before the server-defined expiry; every renewal replaces fencing generation and invalidates old preflight.
  - Server expires without HTTP/browser traffic and requests only owner-authenticated cooperative cancellation.
  - New installed page/API agree with independent sealed four-point physical, visual and cleanup results.
invalid_criteria:
  - Wrong source/install, stale authority, missing evidence, driver observation pollution, or surviving owned runtime.
decision: RUN_AFTER_RED_GREEN_FRESH_COPY_BUILD_AND_PRELEASE_VISUAL_GATE
next_experiment: EXP-047
```

## CP-006 — Renewable and independently expiring Web authority

- Backend RED t61: no autonomous expiry/cancel without traffic, and a matching expired ACTIVE lease could renew (two intended failures). t64 RED: broken maintenance did not fence new campaign mutation (409 instead of dedicated503). t67 RED: replacement holder preflight bypassed recovery authority, and the normal service actually submitted replacement work to its test supervisor (two intended failures). No real execution was involved in these regression tests.
- API lifespan now runs a task that calls the existing lease expiry boundary every250ms and cancels/awaits that task before service/store shutdown. Expiry requests only the existing supervisor-to-owner cancellation channel. An unexpected maintenance failure fences HTTP mutations, makes health unhealthy, and requests owner-authenticated cancellation; it never signals Worker, Broker, Runner or simulator groups. Renew now authorizes current identity/generation and monotonic expiry before advancing generation. Preflight/start honor can_start_campaign, so an expired campaign's replacement holder remains read/cancel-only until recovery.
- Actual Web client now sends renewal PUT with current service session, lease ID and fencing generation. App schedules renewal using server capabilities, replaces authority on success, discards old-generation preflight, disables controls while pending, and clears authority/displays the error on failure. A preflight response arriving after authority replacement is rejected rather than cached. Unmount stops scheduling; it does not release server authority or cancel the campaign.
- t65 backend related GREEN25/25; t66 Web client/app/setup GREEN15/15. Final t68 complete Teleop strict gate401/401 in8.91s, no warning summary, with only the established two exact external compatibility emitters exempted. t69 full Web94/94 and TypeScript/Vite build passed; the pre-existing large-bundle advisory remains, outside pytest warning scope. t70 real browser regression11/11 in20.4s, including ordinary Teleop/task isolation; fake backend data is not live simulation qualification.
- t62 Web attempt is INVALID for app timer assertions: user-event/RTL async-wrapper timers deadlocked under Vitest fake timers and contaminated later tests. t63 uses synchronous real DOM clicks inside act for timer tests and reaches the intended three missing-renewal/fencing failures in1.47s. All test-only diagnostics are retained; none changed server lease duration or physical gates.
- EXP-050 server exit0, no listener18116, no surviving task-owned browser/server or simulation. The temporary live driver now freezes its visual gate before acquiring authority, with bounded300s observation; it never extends server lease/preflight. EXP-051 is still PLANNED pending clean commit and release16 installed gates. EXP-047/048/049 remain not run; their new start reference follows the next valid sequential campaign, not invalid EXP-046.
- Completion remains unproven for production opaque artifact registration/display, adaptive real journal projection, durable server restart restoration and live retry. These must be checked against the original plan; source/mock gates alone cannot close them.

```yaml
checkpoint_id: CP-006
last_valid_experiment: EXP-001
current_hypothesis: Actual-page renewal and server expiry integration satisfy authority safety; a fresh installed four-point campaign must still prove progress/evidence/cleanup.
working_tree_status: Only the scoped lease API/service/UI/tests and this ledger pending commit.
owned_processes: NONE
preserved_processes: codex/kimi tmux, Software Updater and all unrelated worktrees/processes.
next_command: Commit the verified lease integration; build/bind release16 from clean source; run installed gates; start EXP-051 through the actual page after prelease native visual inspection.
```

Retained: the registered root, exp050 visual/boundary evidence, release15 and t60-t70 results. Archived: none. Deletion candidates: all used scratch ck-cp and superseded copied overlays/build/logs; no evidence deleted. Publication remains rejected/unpublished; no protocol or permission bypass attempted.

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
