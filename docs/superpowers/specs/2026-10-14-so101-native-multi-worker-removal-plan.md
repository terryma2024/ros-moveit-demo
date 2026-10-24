# SO-101 native multi-worker removal: inventory and implementation plan

> Note, 2026-10-23: native collection (the single-worker native instance launcher) was retired as well (migration P3, M4); `act_rollout_native` remains as the single-stack rollout reference.

Date: 2026-10-14. Follows `2026-10-13-so101-act-fixed-instance-identity-amendment.md` (item 3: non-container runs no longer support
multiple workers).

## Human ruling

- 2026-10-13: non-container runs no longer support multiple workers; asked about scope, the user chose to remove the non-ACT native
  multi-worker as well.
- 2026-10-14: the user stated that the non-ACT native multi-worker was only a preliminary scheme built on the way to ACT data
  collection and is to be aligned with the current scheme.
- 2026-10-14, answers to the questions of section E below: Option 1 is confirmed - every entry refuses native multi-worker; the
  adaptive pool, its scripts and the macOS two-worker route are removed; Web Expert Validation stays as a single-worker tool; the
  runtime YAML files and their contract stay byte-identical. The macOS change may land from ai-station with the macOS real run
  recorded as an outstanding gate. Historical parallel and adaptive campaigns are re-readable only at the pre-removal commit
  (question 3), taken with the recommendation.

The text below is the investigation and plan as drafted before those answers; where it recommends, the answers above decide.


Read-only investigation; nothing was modified, built or run. PROVEN = read at the cited line; INFERRED = reasoned, not executed. Line numbers in files the Task 7 agent is editing (`worker_process.py`, `composition.py`, `worker.py`, `admission.py`) may shift. Line counts come from a static import-graph pass and are approximate.

Prefixes: `W` = `/home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a`, `D` = `W/src/so101_demo_py/src`, `T` = `W/src/so101_teleop/so101_teleop`, `X` = `W/src/so101_demo_py/test`.

## 0. Findings that shape the plan

1. **"The non-ACT native multi-worker" is three things.**
   - The Linux fixed batch at N of 2..8.
   - The Linux adaptive pool (W8, falling back to 6/4/2/1).
   - The macOS two-worker profile.
   
   All three have one product consumer: Web Expert Validation.
2. **Expert Validation is a documented, user-facing feature.** It is a page of the unified Web app with a mode selector, and `W/README.md:421-461` documents it for Linux and macOS.
3. **The design record only partly supports "it was only a pre-scheme for ACT".** See B.
4. **Most of the batch family is still the runtime library of the ACT instance program.** About 13.4k lines stay whatever option is chosen.
5. **The runtime YAML and its contract should not change.** ACT still reads `max_worker_count`, and any byte change cascades into the collection identity.
6. **`docker/parallel-perception/Dockerfile` is the base of the ACT Teacher inference image.** It cannot be deleted with the Broker.

## A. Inventory

| Piece | What it is | Callers | Size |
|---|---|---|---|
| `D/parallel_batch/` | Coordinator, Broker, leases, journal, artifacts, contracts, allocator, start guard, adaptive pool, macOS campaign core | batch CLI, Expert Validation, macOS campaign, ACT (subset) | 19,714 lines |
| `D/cli/mujoco_batch/` | `ProductionBatchComposition`, request parsing, worker process, RPC proxies, Broker lifecycle | `D/cli/mujoco_parallel_batch.py:12-17`; ACT borrows three symbols (C) | about 4,490 lines |
| `so101_parallel_batch` | Fixed and adaptive entry; `--worker-count` defaults to 2 (`request.py:375`) | Expert Validation, operators | `mujoco_parallel_batch.py`, 119 lines |
| `so101_parallel_batch_cleanup` | Exact cleanup of a batch's processes and domain claims | Expert Validation, adaptive wrapper | 393 lines |
| `so101_parallel_perception_broker` | Broker container entry, image build and `verify_source` | batch, Dockerfile build step | 551 lines |
| `so101_measure_parallel_resources` | Retired stub that prints a retirement error | none | small |
| Adaptive pool | `adaptive_contracts/pool/queue/runner.py`, `mujoco_batch/adaptive_results.py`, `config/mujoco/adaptive_worker_pool.yaml` | batch CLI, Expert Validation | about 1,590 lines |
| Scripts | `run_so101_adaptive_batch.zsh` (installed via `setup.py:90`), `run_so101_adaptive_worker_scaling.zsh`, `generate_so101_parallel_worker_scaling_chart.py`, `inject_so101_parallel_fault.py`, `parallel-perception-container.sh` | Expert Validation (wrapper), benchmarks | about 950 lines |
| Runtime configs | `parallel_batch_linux_cuda.yaml` (sha 991b5c1b…), `parallel_batch_act_offline.yaml` (5775cb3b…), three macOS YAMLs | Expert Validation, ACT, macOS | 5 files |
| Worker runtime | `D/runtime/parallel_worker_runtime.py`, `parallel_worker_parts/`, `parallel_ros_ports/`, `parallel_ros_runtime.py`, `parallel_perception_runtime.py`, `parallel_ipc/`, `parallel_processes.py` | batch and ACT instance | about 8,000 lines |
| `ParallelWorker` | `D/parallel_batch/worker.py` plus `worker_parts/commit`, `revocation`, `watchdog` | only `mujoco_batch/worker_process.py` | about 1,220 lines |
| Native domain allocation | `parallel_batch/resources.py`, `resource_allocation/*` (flock claims, slots from `ros_domain_ids[slot-1]`, `allocator_layout.py:190,212`) | batch only | about 1,800 lines |
| Broker image | `W/src/so101_demo_py/docker/parallel-perception/Dockerfile` | batch; base of `docker/campaign-inference/Dockerfile:7` | 51 lines |
| macOS campaign | `D/cli/macos_*`, `macos_campaign/`, `macos_station/`, `campaign_supervisor`, `point_drain`, `queue`, `selection`, `single_/two_worker_composition`, `contracts/macos_*`, `runtime/macos_*`, `mps_broker_bootstrap`, `parallel_ipc_darwin` | `so101_macos_service_campaign`, launched by Expert Validation on macOS | about 12,500 macOS-only lines |
| Expert Validation | `T/expert_validation/**` plus the Web page and e2e specs | unified Web service (`T/unified/app.py:756-902`, `compose.py:53`) | 14,565 lines Python; about 15,800 lines web and e2e |
| Tests | 199 files reference the batch family, e.g. `X/parallel_batch` (44), `W/src/so101_teleop/test/expert_validation` (38) | — | about 77,000 lines |
| Guides | `docs/guides/so101-parallel-adaptive-worker-pool-source-guide.md`, `so101-macos-service-campaign-closure.md`, `so101-unified-webapp-operation.md:73-79`, scaling chart assets | — | — |

- PROVEN dead today: `D/parallel_batch/history.py` (112 lines) has no importer.
- PROVEN unrelated: `so101_mujoco_rgbd_batch` is a sequential single-stack runner.

## B. Consumers

| Consumer | What it runs | Workers | Needs multi-worker? |
|---|---|---|---|
| Expert Validation, Linux, SEQUENTIAL | `so101_parallel_batch --worker-count 1` (`T/expert_validation/supervisor.py:183-199`) | 1 | No |
| Expert Validation, Linux, PARALLEL | Same argv with N of 2..8 (`preflight.py:19,481`) | 2..8 | Only for speed |
| Expert Validation, Linux, ADAPTIVE | `zsh run_so101_adaptive_batch.zsh --adaptive-workers` (`supervisor.py:376-400`); UI default 8 with fallback 6,4,2,1 (`web/src/expert-validation-app.tsx:347-349`) | 8 down to 1 | Only for speed |
| Expert Validation retry | `--batch-kind FULL_RESTART_RETRY`, one point per command (`production_service/retry.py:109-112`) | 1 (`execution_context.py:36`) | No |
| Expert Validation, macOS | `so101_macos_service_campaign`; three closed profiles (`D/parallel_batch/contracts/routes.py:22-27`) | 1 or 2 (`macos_service_campaign.py:225`) | W2 only for speed |
| Pick-place validation | One `ActChildLaunch` per case (`T/unified/pick_place_case_owner.py:107,112`; `pick_place_full_restart_campaign.py:42`) | 1 | No |
| Benchmarks | Scaling script and chart generator | 1..16 | They exist to measure scaling |

- PROVEN: Expert Validation has a UI. The nav entry is at `web/src/components/unified/app-shell.tsx:26`, and the mode and worker-count controls are in `web/src/components/expert-validation/campaign-setup.tsx:283-306`.
- PROVEN: pick-place validation does not import the batch core. `ActChildRegistry` (`T/unified/bridge.py:122-145`) can hold several native children on distinct domains, but no caller passes more than one.
- INFERRED: container shards cannot serve Expert Validation today. The instance program runs only the ACT collection workload in `formal` mode. Its Teacher service selects YOLO or Grounded-SAM per campaign, whereas point validation needs YOLO first with a bounded Grounded-SAM fallback.

**Evidence on the "pre-scheme" statement**

Supports it:
- The 20-point MoveIt expert baseline that the parallel design was written to speed up is ledgered under the ACT family. Its task id is `so101-act-head-wrist-moveit-expert-baseline-20260911`, with root `/data/work/so101-evidence/act-head-wrist-moveit-baseline/…` (`docs/experiments/so101-act-head-wrist-moveit-expert-baseline-experiment-ledger.md:2,8`).
- The ACT design reuses the batch as its collection substrate (`docs/superpowers/specs/2026-09-10-so101-act-head-wrist-rgb-design.md:42,208`).
- The MoveIt expert is the ACT Teacher.

Contradicts "only":
- The parallel design states its purpose as the 20-point MoveIt expert regression and says it does not modify ACT; a later ACT use "需要单独定义 profile 和验收" (`2026-09-11-so101-parallel-multipoint-validation-design.md`, §1).
- The adaptive design says the same (`2026-09-14-so101-adaptive-worker-pool-design.md`, intro).
- The Web design defines Expert Validation as a product page with three modes (`2026-09-11-so101-moveit-expert-validation-web-design.md`, §1).
- The ACT design says the adaptive pool "不再承担新的 ACT 正式采集" (line 208).

Conclusion: the fixed batch did become the ACT pre-scheme. The adaptive pool, the Web page and the macOS campaign were built as their own features.

## C. Shared code and the cut line

**Kept as the single-worker runtime library** (reached from the ACT instance program, the container campaign or the unified service):

| Module | Why it stays |
|---|---|
| `parallel_batch/contracts/common.py`, `identity.py`, `linux_cuda.py` | `LeaseIdentity`, `RunMode`, `teacher_execution_bound_s`, `ParallelRuntimeConfigLinuxCuda` (`D/runtime/container_campaign/task_builder.py:26-31`, `coordinator.py:22,275`) |
| `parallel_batch/act_attempt.py`, `act_inference.py`, `act_perception.py`, `perception.py` | `D/runtime/act_ros_runtime.py:8-14`, `act_teacher_client.py:8` |
| `parallel_batch/artifacts.py`, `dynamic_manifest.py` | `D/act/result_store.py:23,277` |
| `parallel_batch/journal.py` | `result_store.py:616-993`; the read-only `verify-commit`, `check-export`, `readback` commands that Task 7 keeps |
| `parallel_batch/worker_parts/protocol.py`, `contracts.py` | `WorkerProtocol._gate_summary` (`task_builder.py:531`) |
| `parallel_batch/resource_allocation/models.py` | `WorkerResources` (`task_builder.py:216`, `parallel_worker_runtime.py:13`) |
| `parallel_batch/start_guard.py`, `start_guard_probe.py`, `accelerator_probe.py` | `T/unified/compose.py:63,86`; `read_process_identity` in `D/runtime/owner_records.py:40` and `parallel_ros_ports/execution.py:16` |
| `parallel_batch/broker.py`, `frozen_models.py`, `canonical_json.py` | `BrokerResponse` type (`parallel_ros_ports/observations.py:17`); `runtime_closure/*` |
| `D/runtime/parallel_worker_runtime.py`, `parallel_worker_parts/*`, `parallel_ros_ports/*`, `parallel_ros_runtime.py` | `ActWorkerRuntime`, `ActRosRuntimePorts` |
| `D/runtime/parallel_perception_runtime.py`, `parallel_ipc/frames.py`, `parallel_processes.py` | `normalize_batch` (`D/runtime/inference/executor.py:26`); `canonical_json` (`D/cli/campaign_inference.py:23`) |
| `docker/parallel-perception/Dockerfile`, `parallel_perception_broker.verify_source` | Base image of the Teacher image; its build step imports `verify_source` |

**Three symbols ACT borrows from the batch CLI package.** They must move to a neutral module before that package can ever be deleted:
- `_load_runtime_config` (`D/cli/mujoco_batch/request.py:295`), which calls `two_worker_composition.load_execution_config`. Imported at `shard_launcher.py:9`, `task_builder.py:25`, `act_instance/spec.py:26`, `act_fixed_collection_composition.py:33,157`.
- `_lease_wire` (`mujoco_batch/common.py:126`), imported at `task_builder.py:24`.
- `_ArtifactResults` (`mujoco_batch/worker_process.py:41`), imported at `container_campaign/case_artifacts.py:9`.

**Dead once native multi-worker is gone (Option 1):**
- The adaptive pool and its results capture.
- `adaptive_worker_pool.yaml`, the wrapper script and the two scaling scripts.
- The Expert Validation adaptive and parallel paths: `adaptive.py`, `adaptive_events.py`, `supervisor.py:376-400`.
- The macOS two-worker route.

Three adaptive symbols are used outside the pool and must be relocated or proven adaptive-only first:
- `WorkerStartGate` and `WorkerReadinessReceipt` (`worker_process.py:418,446`; `rpc_proxies.py:361`).
- `adaptive_socket_paths` (`parallel_batch_cleanup.py:17`).

**Dead only if the whole native batch goes (Option 2):**
- About 10,200 lines reached only from the batch CLI and Expert Validation: `coordinator.py`, `worker.py`, `resources.py`, the allocator, `commit`, `revocation`, `watchdog`, and the rest of `cli/mujoco_batch`.
- About 2,850 lines shared with macOS: `web_control.py`, `parallel_ipc/authority.py`, `broker_transport.py`, the macOS contracts, `routes.py`.

## D. Options

| | Option 1: native is one worker | Option 2: delete the batch, move consumers to the instance program | Option 3: keep code, refuse N > 1 |
|---|---|---|---|
| User loses | PARALLEL and ADAPTIVE modes, macOS W2, scaling benchmarks. A 20-point run goes back to about 29 minutes (W1 1746.86 s versus W2 895.80 s, `2026-09-13-so101-parallel-w8-admission-design.md`, §1). | Nothing in principle, but only after a new point-validation workload exists. macOS has no containers, so it becomes native single-worker. | Same as Option 1 |
| Code removed | About 3–5k source lines and 8–12k test lines (INFERRED) | About 13k Linux lines, plus up to 12.5k macOS lines if macOS Expert Validation is also dropped; most of the 77k test lines | None |
| New code | Small: refusals and symbol moves | Large: validation workload, YOLO-then-Grounded-SAM fallback in the Teacher service, evidence schema, Web projection, retry, cancel | About 100 lines |
| Risk | Medium. Touches the Expert Validation API, store and UI. | High. It rebuilds a working feature, and the ACT design said not to reuse the point-validation evidence schema (line 42). | Low. Leaves the pool, wrapper and multi-slot allocator as dead weight. |
| Re-verify | Web Expert Validation SEQUENTIAL and retry end to end; ACT smoke after image rebuild; macOS W1 | Everything | Refusal paths only |
| Host | Linux on ai-station; the macOS profile removal needs the macOS host for the real run | Both | ai-station |

## E. Recommendation and plan

**Recommendation: Option 1, with Option 3 as its first task.** It matches the ACT ruling exactly: native runs one worker, multi-worker exists only in containers. It keeps Expert Validation usable and does not rebuild anything. Do not collapse the Coordinator and Broker for the single worker now; that is Option 2 under another name. Whether Expert Validation later gets container multi-worker, or is deleted, is question 1.

**Frozen identities**
- Keep `parallel_batch_act_offline.yaml` and `parallel_batch_linux_cuda.yaml` byte-identical, and keep `ros_domain_ids` and `max_worker_count` in the contract.
- PROVEN: ACT reads `max_worker_count` as the shard cap (`D/runtime/act_fixed_collection_composition.py:88`).
- PROVEN: `ros_domain_ids` is read only by the native allocator (`parallel_batch/resources.py:89,152`). At one worker only 181 is used.
- PROVEN consequence of dropping either field:
  - The schema is closed (`linux_cuda.py:80-92,326`) and the values are pinned (`:247-254,268-269`), so the YAML would have to change.
  - The pin at `config/act/parallel_collection.yaml:5` then changes, and with it `collection_config_sha256`.
  - That changes `_collection_identity` (`T/unified/admission.py:239-246`), and the qualification runs on the current identity would have to be redone.
- Any source edit already changes the source hash and both image digests. Batch all tasks before one image rebuild.
- Leave the Broker Dockerfile untouched. The inference image pins its base by image ID 010dca70… (`docker/campaign-inference/Dockerfile:4`).
- Migration: Expert Validation stores hold rows with `execution_mode` PARALLEL or ADAPTIVE, and `production_service/restore.py:86-111` rebuilds launch requests from them. After removal a restored non-terminal multi-worker campaign must be fenced to operator recovery, never relaunched.

**Tasks** (one writer, RED then GREEN each)

Entry gate: Task 7 committed, no live campaign, this plan committed and confirmed.

1. **Refuse native multi-worker at every entry.**
   - `BatchRequest` refuses `worker_count != 1` (`linux_cuda.py:64`).
   - `prepare_batch` refuses `--adaptive-workers` and N > 1 before any resource work; the default becomes 1 (`request.py:356-375`).
   - `_DEFAULT_WORKER_COUNT` becomes 1 (`resource_allocation/models.py:14`).
   - Expert Validation: `FIXED_WORKER_COUNTS` becomes `(1,)` (`preflight.py:19`); PARALLEL and ADAPTIVE are rejected (`preflight.py:479-520`, `api.py:77-79`); capabilities advertise SEQUENTIAL only.
   - Admission refuses a second native child for the pick-place kinds (`admission.py:556`).
   - RED cases: N = 2 refused by CLI, API and contract; N = 1 argv byte-identical to today.
2. **Restore fence.** A stored non-terminal PARALLEL or ADAPTIVE campaign projects as needing operator recovery. Test on a copied store fixture.
3. **Web UI.**
   - Remove the mode selector, worker-count control and adaptive panels.
   - Regenerate `expert_validation_openapi.json`, `unified_openapi.json` and `web/src/api/expert-validation-schema.d.ts`.
   - Update the vitest suites and the Playwright contract specs, including `console-worker-count.spec.ts`.
4. **Checkpoint C: real Web Expert Validation run on ai-station**, SEQUENTIAL, with one FULL_RESTART retry and one cancel.
5. **Delete the adaptive pool.**
   - First relocate the three adaptive symbols named in C.
   - Delete: the four `adaptive_*.py`, `mujoco_batch/adaptive_results.py`, `adaptive_worker_pool.yaml`, the wrapper and its `setup.py:90` entry, both scaling scripts, `history.py`, and Expert Validation's `adaptive.py` and `adaptive_events.py`.
   - Remove the adaptive branches and hash fields in Expert Validation: `supervisor.py`, `process_owner.py`, `statistics.py`, `production_service/layout.py:176-195`, `restore.py:120-130`, `campaigns.py:144-147`, `candidates.py:204-207`.
   - Delete tests: `X/parallel_batch/test_parallel_adaptive_{contracts,pool,queue,runner}.py`, `X/cli/test_parallel_adaptive_integration.py`, `X/cli/test_parallel_batch_cli_adaptive.py`, `X/scripts/test_generate_so101_parallel_worker_scaling_chart.py`, `W/scripts/tests/test_adaptive_worker_scaling_defaults.py`.
   - Rewrite tests: `test_parallel_batch_contracts.py`, `test_parallel_batch_cli_requests.py`, `test_parallel_batch_resources_*.py`, and the Expert Validation preflight, API, supervisor, statistics and projection suites.
   - Keep every Coordinator, worker, journal, artifacts, start-guard and runtime-port test.
6. **macOS.**
   - Drop the two-worker route from `APPROVED_EXECUTION_ROUTES` and `ROUTE_MODULES`; keep the two single-worker profiles.
   - Keep `contracts/macos_two_worker.py` as the constants the single-worker profiles derive from (`routes.py:44-56`) until a later rename.
   - Delete `cli/macos_two_worker_campaign.py`, `macos_two_worker_process.py` and their tests only after grep proves the single-worker path does not use them.
   - Unit tests can land from ai-station. The real W1 first-pass and retry run needs the macOS host.
7. **Guard, docs, ledger.**
   - New `X/repo/test_native_multi_worker_removed.py`, on the pattern of `test_old_native_act_path_removed.py`. It asserts removed files and names are absent, and that the kept library modules and both runtime YAML hashes are present.
   - Update `docs/guides/so101-unified-webapp-operation.md:73-79` and `so101-macos-service-campaign-closure.md`; retire the adaptive source guide with a short historical note. Use the humanizer skills.
   - Update `.agents/skills/so101-dev/references/unified-teleop-service.md` and add a note to the 2026-10-13 amendment.
8. **Freeze and verify.**
   - Fresh colcon build.
   - `so101_demo_py` ordinary gate and `so101_teleop` gate, with `/data` scratch per `AGENTS.md`.
   - Web unit tests and e2e.
   - Rebuild both images, then one container W1 run and one native W1 run of the ACT campaign as regression.

**Open questions for the human**

1. **Fate of Expert Validation.** Choices: (a) keep it as a single-worker native tool; (b) also port multi-worker to container shards later; (c) delete it as the pre-scheme. Recommendation: (a) now and decide (b) separately. I cannot tell from the record whether the page is still wanted.
2. **macOS.** Remove W2 and keep W1? Recommendation: yes. May the code land before the macOS real run, with that run recorded as an outstanding gate?
3. **Historical multi-worker evidence.** Is it acceptable that PARALLEL and ADAPTIVE campaigns are no longer projected in the Web page and are re-readable only at the pre-removal commit? Recommendation: yes, matching the Q5 precedent for old bags.
4. **Wording.** "也已经对齐现在的方案" reads literally as "has already been aligned". I assumed "is to be aligned". Please confirm.

To verify during Task 1 (INFERRED gap): native ACT exclusivity reads only the ACT tables and pick-place children (`T/unified/worker_slots.py:62-76`). A directly launched `so101_parallel_batch` worker also uses domain 181 and bypasses that check.

### Critical Files for Implementation
- `/home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a/src/so101_demo_py/src/cli/mujoco_batch/request.py`
- `/home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a/src/so101_demo_py/src/parallel_batch/contracts/linux_cuda.py`
- `/home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a/src/so101_teleop/so101_teleop/expert_validation/preflight.py`
- `/home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a/src/so101_teleop/so101_teleop/expert_validation/supervisor.py`
- `/home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a/src/so101_demo_py/src/parallel_batch/contracts/routes.py`
