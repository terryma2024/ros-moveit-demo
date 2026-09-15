# SO-101 Stateless Perception Broker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the shared perception Broker a stateless, bounded concurrent request/response service with no Coordinator lease, start-event, or journal authorization on its inference path, then prove W10 with real YOLO and a fixed 20-point run.

**Architecture:** The Broker owns request correlation, queues, executors, deadlines, model health, and results. The Coordinator continues to own point leases, Worker lifecycle, motion authority, final result admission, and journals, but is absent from inference request handling. Late or duplicated semantic inference is acceptable wasted compute; stale motion and final result acceptance remain rejected outside the Broker.

**Tech Stack:** Python 3.12, Unix domain sockets, threading/conditions, ROS 2 Jazzy, MuJoCo, MoveIt 2, Docker GPU Broker, pytest, colcon.

**Spec:** `docs/superpowers/specs/2026-09-15-so101-stateless-perception-broker-design.md`

## Global Constraints

- Run directly on ai-station; do not SSH from the ai-station Codex task.
- Use the existing registered evidence root `/data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01` and update the experiment ledger before new experiments.
- Preserve user-owned `MUJOCO_LOG.TXT` and the pre-existing changes in `src/so101_demo_py/test/test_parallel_batch_resources.py`; separate task edits before committing.
- Do not use broad `git restore`, `git reset`, `pkill`, or `killall` commands.
- Stop only exact task-owned obsolete units/process groups after identity readback and retain their logs.
- Keep default W8, fallback `W8 -> W6 -> W4 -> W2 -> W1`, optional W16 ceiling, and YOLO-first model policy unchanged.
- Broker/CUDA/RPC infrastructure failure must not trigger Grounded-SAM fallback.
- ai-station pytest must use a fresh, previously nonexistent `/data` NVMe scratch directory with `TMPDIR`, `TMP`, and `TEMP` preflight readback.
- Ordinary package tests must not collect `benchmark_test/` unless benchmark code/configuration changes.
- Do not push or merge without a new explicit authorization.

---

### Task 1: Record the design pivot and retire obsolete execution safely

**Files:**
- Modify: `docs/experiments/so101-parallel-adaptive-worker-pool-experiment-ledger.md`
- Create: `docs/superpowers/specs/2026-09-15-so101-stateless-perception-broker-design.md`
- Create: `docs/superpowers/plans/2026-09-15-so101-stateless-perception-broker-implementation.md`

**Interfaces:**
- Consumes: checkpoint `CP-042`, EXP-033/EXP-034 evidence, current dirty worktree and owned-process inventory.
- Produces: an append-only checkpoint marking strict inference authorization as superseded by the user-approved stateless boundary.

- [ ] Read repository rules, `so101-dev`, this spec and plan, the complete ledger, current diff, running units, processes, ROS graph, containers, and GPU processes.
- [ ] If `so101-exp034-full-gate-r7.service` is still active, verify its exact identity, stop only that unit, retain its log, and mark the run invalid/superseded because it tests the abandoned design.
- [ ] Append a new ledger checkpoint and planned experiment IDs; do not rewrite EXP-033/EXP-034 history or count old strict-authority tests as acceptance of this design.
- [ ] Copy this approved spec and plan into the implementation worktree unchanged before implementation.

### Task 2: Establish the stateless Broker contract with RED tests

**Files:**
- Modify or replace: `src/so101_demo_py/test/test_parallel_broker_hot_path.py`
- Modify: `src/so101_demo_py/test/test_parallel_ipc.py`
- Modify: `src/so101_demo_py/test/test_parallel_perception_runtime.py`
- Modify only if required: `src/so101_demo_py/test/test_parallel_batch_broker.py`

**Interfaces:**
- Consumes: current `BrokerTransport`, `PerceptionService`, `PerceptionBroker`, `UnixRpcClient`, and model result types.
- Produces: executable tests for a Coordinator-free inference endpoint and exact concurrent correlation.

- [ ] Write a failing test that starts the Broker without a Coordinator inference-authority server or journal and completes one request.
- [ ] Write a failing W10/C2 test with ten concurrent clients, deliberately reordered completions, and assertions that every response returns the originating `request_id` and input marker.
- [ ] Write a failing test that submits the same semantic point/image twice with distinct request IDs and asserts both are executed and returned.
- [ ] Write failing queue-full and per-request deadline tests proving prompt backpressure and that one timeout cannot cancel or misroute another request.
- [ ] Add a spy/forbidden callback assertion proving the entire inference lifecycle performs zero Coordinator authorization calls and zero journal replays.
- [ ] Run only these tests under a fresh registered `/data` scratch path and retain the expected RED output.

### Task 3: Remove scheduling authority from the inference path

**Files:**
- Modify: `src/so101_demo_py/src/runtime/parallel_ipc.py`
- Modify: `src/so101_demo_py/src/runtime/parallel_perception_runtime.py`
- Modify: `src/so101_demo_py/src/parallel_batch/broker.py`
- Modify: `src/so101_demo_py/src/cli/mujoco_parallel_batch.py`
- Modify only to remove now-dead inference API: `src/so101_demo_py/src/parallel_batch/coordinator.py`
- Modify only if wiring changes: `src/so101_demo_py/src/cli/parallel_perception_broker.py`

**Interfaces:**
- Consumes: request ID, model ID, immutable input reference/digest, inference options, and request deadline.
- Produces: terminal response carrying the exact request ID, model identity/version, outcome/result, and timings.

- [ ] Remove the Broker's `authorize_inference` calls to Coordinator at admission, dispatch, completion, polling, copying, and watchdog/deadline boundaries.
- [ ] Remove lease, generation, start-event, reset-epoch, and journal lookup as Broker admission requirements. If compatibility fields remain temporarily, treat them as opaque metadata and prove omission works.
- [ ] Do not weaken Coordinator/Worker control sockets used for scheduling, action ownership, cleanup, or final result commits.
- [ ] Keep one-request/one-response connection ownership or an explicit request-to-future map so out-of-order completion cannot cross-wire replies.
- [ ] Keep configured connection bounds, per-model queue capacities, C2 executor bounds, local deadlines, health, framing limits, socket permissions, and model provenance.
- [ ] Remove dead authority clients, tokens, metrics, and tests only when no non-inference control path uses them.
- [ ] Run the Task 2 tests to GREEN and record zero Coordinator inference calls and zero journal replays.

### Task 4: Protect motion and result boundaries outside the Broker

**Files:**
- Inspect and minimally modify only if regression coverage is missing: `src/so101_demo_py/src/parallel_batch/coordinator.py`
- Inspect and minimally modify only if regression coverage is missing: Worker/runtime execution adapter files discovered from the current source.
- Test: the nearest existing coordinator, Worker lifecycle, and stale-result tests.

**Interfaces:**
- Consumes: current Worker lease/action authority and Coordinator result-commit contracts.
- Produces: proof that simplifying inference does not authorize stale motion or stale final result admission.

- [ ] Reuse existing tests where they already prove that a stale Worker cannot start/continue physical action and cannot commit a final point result.
- [ ] Add only the smallest missing regression test; do not reintroduce inference authorization through another name.
- [ ] Run the focused scheduling/action/result tests to GREEN in fresh `/data` scratch.

### Task 5: Run adjacent and package-level gates

**Files:**
- Test: `src/so101_demo_py/test/`
- Evidence only: registered evidence root and fresh scratch trees.

**Interfaces:**
- Consumes: stateless Broker implementation and focused GREEN tests.
- Produces: clean package-level regression result and immutable candidate inputs.

- [ ] Run `git diff --check` and Python compile/import checks.
- [ ] Run Broker, IPC, runtime, coordinator, adaptive, fault-injection, cleanup, and CLI adjacent suites.
- [ ] Run the complete ordinary `src/so101_demo_py/test/` collection in a clean systemd unit with the ROS process-cleanup test before any library that makes pytest multithreaded; do not rewrite test constants or semantics in the runner.
- [ ] Require zero unexpected failures. Isolate any environment collision with a fresh scratch reproduction and record it; do not silently waive it.
- [ ] Separate task-owned changes from preserved user changes, then create reviewable commits. Do not push.

### Task 6: Build and prove real-YOLO perception-only W10

**Files:**
- Build/install outputs and Broker image derived from the committed candidate.
- Evidence: a new planned experiment under the registered evidence root.

**Interfaces:**
- Consumes: committed candidate, exact sourced overlay, frozen YOLO weights/image/configuration, ten concurrent request inputs, C2.
- Produces: real-YOLO W10 response-correlation, concurrency, timing, and cleanup evidence.

- [ ] Build and source an immutable candidate-equivalent overlay; verify source commit, installed module/console/config paths, hashes, Broker image identity, model hashes, and socket lengths.
- [ ] Plan and run a perception-only W10/C2 experiment with ten simultaneous requests and no simulation motion.
- [ ] Require ten correlated terminal responses, YOLO-first behavior, bounded queue depth, active model peak no greater than two, zero Coordinator inference calls, no journal access by Broker, and no transport errors.
- [ ] Perform exact cleanup and read back no task-owned processes, sockets, containers, or GPU clients.

### Task 7: Run one fixed-W10 20-point qualification

**Files:**
- Evidence and ledger only unless a newly observed failure justifies a new RED test and minimal source change.

**Interfaces:**
- Consumes: the exact candidate proven by Task 6 and the existing 20-point catalog/configuration.
- Produces: one valid fixed-W10 result without worker fallback.

- [ ] Freeze one experiment before launch: fixed W10, C2, YOLO-first, no Worker reduction/fallback, existing point catalog, initial-state gate, and current timeout policy.
- [ ] Run all 20 points from their required initial state. Do not mask a failure by increasing deadlines, retrying, falling back to fewer Workers, or switching models outside the existing perception-failure policy.
- [ ] Accept success only with 20/20 terminal point evidence, exact request/response correlation, model and timing metrics, Gazebo/MoveIt/controller/pose/contact evidence, and fresh visual evidence.
- [ ] If it fails, stop at the first new boundary, preserve evidence, clean exactly, and report it without claiming W10 qualification.
- [ ] Update the ledger checkpoint with retained runs, archived runs, deletion candidates, commits, process cleanup, confirmed conclusions, and the next exact command or `NONE`.

