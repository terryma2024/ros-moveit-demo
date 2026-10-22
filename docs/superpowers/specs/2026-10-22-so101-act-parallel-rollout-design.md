# SO-101 ACT: parallel closed-loop rollout — design

Status: draft for human confirmation (2026-10-22). Nothing here is implemented yet.

## Human request (2026-10-22)

"后面要rollout验证的次数比较多，我需要rollout能并行做。类似采集的方案。提升验证迭代速度。"

This replaces the executor decision of 2026-10-18 ("执行器方案：容器外执行，不并发",
`2026-10-18-so101-act-native-rollout-design.md`). The native tool stays as the single-stack reference.

## Why

- One closed-loop trial of the four standard points takes about 15 min of wall time on one native stack. A 5-trial
  verdict for one execution setting takes about 75 min, plus INVALID re-runs.
- The TRAIN-006 work needs many settings and, later, several bundles. Serial runs are now the bottleneck of the
  iteration loop.
- The collection already runs N MuJoCo stacks in containers with proofs. Rollout should use the same machinery.

## Facts the design rests on (read-only map, 2026-10-22)

- **Shard isolation.** Collection shards run as one container per shard. Each has `--network none --ipc private`, the same fixed
  ROS identity (domain 181), and a per-shard session id (`SO101_MUJOCO_SESSION_ID`, `GZ_PARTITION`).
  - Container launch: `runtime/container_campaign/launch.py:105-192`.
  - Fixed identity: `runtime/act_instance/identity.py:21-38`.
- **Mount mode.** The image is the dependency-only base. The install and source trees are mounted read-only at their host
  paths (`mount_build.py`).
- **Host scheduling.** The Host coordinator runs waves with a barrier on READY, then assigns one task at a time. A
  `RecordingGate` caps the tasks in flight and enforces a minimum gap between assignments (`coordinator.py:110-153`,
  `:537-553`). Stage receipts are sha-chained and save the logs before `docker rm` (`container_receipts.py`).
- **Teacher perception.** One inference service serves every shard over a Unix socket. It carries framed JSON plus an RGB
  payload and has a queue limit and timeouts (`runtime/inference/service.py`, `codec.py`, `client.py`).
- **The native rollout is mostly shard-portable.** These already run inside the shard image: stack launch,
  `ActRosRuntimePorts` (reset, initial gate, resume), `rollout_ros` (observation assembler, `ActExecutionAdapter`, world
  observer), `PilotRecording` and the endpoint validator. Only the policy needs lerobot 0.6.1 and torch, which live in the
  train venv: torch 2.11.0+cu128 there, against 2.13 in the images.
- **Only two workload kinds exist.** No container-mode ACT rollout instance exists. `runtime/act_instance/spec.py`
  accepts only `no_motion_readiness` and `act_collection`.
- **The loop is free-running and sim-time anchored (D2).**
  - Inference limits: `request_timeout_s` 0.5, `max_reply_age_s` 0.3.
  - Observation sync: `rgb_sync` age/skew 0.1.
  - Goal submission: submitted 0.03 s ahead; acceptance must arrive within **0.02 s wall time** (`act/execution.py:201-213`).
  - Under CPU load, a late reply holds the previous goal. A late goal acceptance makes the attempt INVALID
    (`goal response timeout`), which already hits 19 of 78 attempts on ONE native stack, in the per-step modes.

## Decisions (recommended defaults; the human confirms or changes them)

| # | Decision | Recommendation | Alternative |
|---|---|---|---|
| P1 | Executor | **Container shards, as in collection.** New workload kind `act_rollout` in the shard program, mount mode, same isolation, receipts and stop proofs. | Several native instances on the host with distinct domains and ports. Quicker to build, but weaker isolation, no receipts, and it does not extend to antzb in the same form. |
| P2 | Where the policy runs | **One policy service per host, a host process in the train venv** (lerobot 0.6.1, torch 2.11, the same interpreter as training and the native rollout, so the numerics match). Every shard connects to it over a Unix socket mounted into the shard, with the inference codec's framing. The policy is loaded once. Requests are served FIFO, one at a time, with no batching. | Per-shard in-process policy. That needs lerobot in the shard image, torch 2.11 vs 2.13, and N CUDA contexts contending for the GPU. |
| P3 | Shard-side boundary | `ActInferenceProcess` keeps its rules: one request in flight, `request_timeout_s`, stale-reply refusal. Only its transport changes, from `ThreadInferenceTransport` to a socket transport. Execution modes (prefix, ensembling) stay in the shard, unchanged. | — |
| P4 | Task unit | **One task = one (scene, trial) attempt.** The Host keeps a queue of (point × trial). An INVALID attempt is re-queued up to `--max-invalid-retries`, as now. The trial number is a label only, because there are no episode seeds. | One task = one trial of 4 points (keeps today's grouping, but parallelism is then limited to trials). |
| P5 | Concurrency | **Cap and gap come from a measurement, not a guess.** Run N = 1, 2, 4, 6 and take the largest N that passes the timing gate below. The cap is a runtime parameter; its value and its evidence are recorded in each run. | A fixed 6/20, copied from collection. Collection has no 20 ms wall-clock window, so its envelope does not transfer. |
| P6 | Evidence | Same per-episode layout as the native tool (`episode.json`, `steps.jsonl`, `world.jsonl`, `endpoint.json`, `raw/`). Plus per-shard stage receipts and one `table.md` / `summary.json` per run (point × trial × verdict). | — |
| P7 | Hosts | ai-station first. antzb second, with the same tool and its own measured cap. Results from the two hosts are reported per host and merged only after the cross-host check below. | — |

## Timing gate (what "parallel is equivalent" means)

Rollouts are not bit-reproducible: the loop is free-running, so a verdict-by-verdict comparison (as for the reach light
stacks) cannot work. Equivalence is therefore shown on the **timing distributions that decide behaviour**, plus an
outcome sanity check. Every step already logs these, or will:

1. **Inference round trip.** Observation stamp to reply, p50/p99. p99 must stay below 0.1 s (one control period), well
   inside `max_reply_age_s` 0.3.
2. **Late steps.** The rate of late replies and `PREFIX_LATE` per episode must not exceed the native reference.
3. **Observation age and skew.** Observations rejected by `rgb_sync` must not exceed the native reference.
4. **Goal acceptance latency (wall).** The p99 and the `goal response timeout` rate must be no worse than native.
5. **Real-time factor of the sim.** Recorded only. A slower sim is not a failure, because the loop is sim-time anchored.
6. **Outcome sanity.** With one bundle and setting (TRAIN-006, ensembling M 0.01), 4 points × 5 trials at the chosen N.
   The per-point DONE counts must lie inside the 95 % binomial interval of the native result. Native has forward_5cm 4/4
   and the others 0/4, so this check is weak and only catches gross breakage.

The native reference for 1–4 is computed from the existing TRAIN-006 native runs (no new runs needed).

## Prerequisite: the goal-response-timeout INVALID (phase 0)

At 25 % INVALID on one stack, parallel load will make it worse. Before the parallel tool:

- Instrument the acceptance latency in the native tool: send time, accept time, sim time, load, and which controller.
- Find the cause. Candidates are executor scheduling in the rollout process, controller_manager callback latency, and DDS
  discovery or first-goal effects.
- Fix the cause.
- `accept_timeout_s` 0.02 is a frozen rollout setting. Raising it would change which attempts count, so it is **not**
  touched without a separate human decision, with the evidence.

## Implementation phases (after confirmation; Sonnet writer, Opus review, fixture-only tests written first)

0. Measure the goal-response-timeout latency and fix it (native tool). Gate.
1. **Policy service.** `act_policy_service` (train venv) loads one bundle and serves `infer(observation) → chunk` over a
   Unix socket, reusing `runtime/inference/codec.py` framing. It has a process record and a stop proof, and records the
   bundle sha and execution mode. Fixture tests use a fake policy.
2. **Shard workload `act_rollout`:**
   - spec kind and `shard_builder` entry;
   - a task builder that runs one rollout episode with `ActRosRuntimePorts` / `rollout_ros`, the socket transport behind
     `ActInferenceProcess`, `PilotRecording` and the endpoint;
   - output under `/act/output`.
3. **Host CLI `act_rollout_parallel`:**
   - reuses the coordinator waves, gate, barrier, receipts and cleanup;
   - owns the policy service lifecycle;
   - INVALID re-queue;
   - aggregates `table.md` / `summary.json`;
   - preconditions as in collection, plus the GPU check, which now allows only its own policy service.
4. **Timing gate and capacity.** N = 1, 2, 4, 6 on the four points, then the gate above at the chosen N. The result is
   ledgered.
5. **antzb.** The same steps, with its own cap. Cross-host check: the same setting on both hosts, timing gate per host,
   outcome sanity across the hosts.

## Expected speed

At N = 6 on ai-station, 4 points × 5 trials (20 attempts plus re-runs) takes about 4 waves of 15 min or less, so
**15–25 min instead of about 75–90 min**. With antzb as well, about half that again. The real N depends on phase 4.

## Risks

- **Load-dependent behaviour.** The timing gate is the guard. If no N > 1 passes, fall back to
  P1-alternative scheduling of fewer, lighter stacks. A sim-waits-for-inference (lockstep) mode would remove load
  sensitivity, but it changes D2 and is a separate decision.
- **Socket hop latency.** One RGB pair is about 1.8 MB. The local Unix socket copy is a few ms. Measured in phase 4.
- **Disk.** About 0.6 GB per episode of raw bags. The evidence partition is at 43 GiB free, so cleanup comes before the
  first parallel run.
- **Collision with collection and gates.** Use the HOST-BUSY flag protocol. The policy service and collection must not
  share a GPU window unless measured.
