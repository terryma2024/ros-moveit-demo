# Independent design review audit

review_date: 2026-09-18
reviewer: GPT-6 Astra / High, independent reviewer
decision: CHANGES_REQUIRED
reviewed_document: docs/superpowers/specs/2026-09-18-so101-parallel-unbounded-queue-resource-budget-design.md
reviewed_document_sha256: 9af29770f084f0c6d2287fd5ffbc78604e1c9e54151d6ce688c15142936d8b6a
source_of_truth: ai-station:/data/work/ws_moveit
source_commit: 147d64a199bdf9c9b360555e15ad6ae85804ac39
mujoco_submodule_commit: e4c0241aee52a40727681bd5872c09bf814e941a
local_document_checkout: 303c2cb9e2b1faea55a6d82dac2197da7512be96
registered_evidence_root: /data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main

## Scope and observed evidence

Only the design and existing implementation were reviewed. No implementation, dst session, ROS/Web process, simulation, pytest, deployment, commit, or push was started. The author document was not modified. AGENTS.md, so101-dev, and its access, system-map, evidence, acceptance, and ledger references were read. The earlier memory note about linked-worktree metadata was used only to choose explicit Git directory/work-tree arguments; current state was verified directly.

Read-only SSH confirmed the source commit above and main branch. Tracked remote source was clean; the existing fixed-eight proposal and operator-recovery guide were untracked. Local AGENTS.md and existing untracked documents were preserved. The existing service was still PID 1264438, parent 461503, pane %63. Its command pointed to the installed expert-validation server. This process observation does not claim new recovery code is installed or that ROS/physical outcomes were verified. The six-source-file recovery snapshot exists at the design's stated path; pending-commit is a separate directory, not a replacement for the complete snapshot.

Source citations below are paths and line numbers in the remote checkout above, not the older local source. Design line numbers refer to the exact SHA256 above.

## Blocking findings

### F1 [P1] Define an acyclic qualification identity graph, including configuration references

Design locations: lines 99-100, 134-136, 238-255. Primary anchor: lines 247-255.

The v2 YAML binds the approved profile path/hash, while effective configuration and installed files enter RuntimeFingerprint. Excluding the profile carrier from the execution inventory does not exclude the reference to that carrier inside the YAML or its installed copy. Publishing the measured profile then changes the configuration/file identity against which it was measured. There is a second unresolved edge: an entry contains the five qualification records, while qualification verification accepts the profile SHA256. If a qualification record itself binds that enclosing profile digest, those content hashes also form a cycle. The design says the cycle is avoided, but does not define the digest inputs that make that statement true.

Current implementation makes this consequential: `src/so101_demo_py/src/parallel_batch/resources.py:1833-1834` hashes the complete `asdict(config)`; `src/so101_demo_py/src/cli/mujoco_parallel_batch.py:780-805` verifies the installed config's raw bytes; Web `src/so101_teleop/so101_teleop/expert_validation/production.py:425-426` hashes the config file. Carrying these existing identity rules forward recreates the cycle even if the profile file itself is excluded.

Minimum correction: specify a one-directional digest graph. Freeze execution/configuration identity without deployment-reference fields, preserving every effective safety/execution value. Qualification evidence binds that identity and exact N. A profile can reference those immutable evidence digests. A separate promotion record binds profile digest and approval. Define the exact normalization of source and installed configuration references, and keep byte-level artifact/provenance checks separate from the qualification equivalence digest. State whether moving a prefix changes executable identity (including wrapper/shebang) or only a verified location binding. Do not exclude the whole config or all installed-file hashes.

Required regression evidence: the same measured execution tree can publish and load its first approved profile without remeasurement; changing a timeout, thread policy, model, executable, or normalization rule invalidates it; changing only an approved reference/location does not create a recursive hash requirement or silently accept changed executable bytes.

### F2 [P1] Give standalone measurement a functioning abort authority before its first spawn

Design locations: lines 139-144, 160-166, 196-200. Primary anchor: lines 196-199.

The candidate CLI is deliberately separate from production Web, but its safety argument requires an owner-authenticated cancellation within one 50 ms cycle through the existing channel. That channel is not unconditional in the current composition. `mujoco_parallel_batch.py:2583-2592` creates it only when `_fixed_web_control` is present; `3516-3521` returns false when it is absent; `3770-3771` adds `stop_requested` to the child wait only when that server exists. Broker startup and recovery also call this Web-specific predicate (`3081-3093`, `3177-3209`). A standalone measurement authorization does not currently provide such a binding. The design has not specified which owner receives an abort before/through model loading and after a sampler failure.

This is not a request to implement the missing feature during review. It is a missing design dependency for the claimed safety bound: merely adding a measurement CLI and sampler leaves a compliant-looking implementation that can detect a limit breach but remain in broker startup or the child wait until an ordinary deadline.

Minimum correction: define a typed measurement owner/control binding and cancellation path, authenticated by the measurement authorization and available before any resource spawn. It may adapt the existing control primitives, but must not require a live production Web lease. Define the supervisor's independent sampler-health deadline, how loss of sampling stops new spawns/grants, and how the abort is observed during startup, broker reload, execution, and teardown. Preserve the existing owned cleanup/fence rules and record actual stop latency separately from send latency.

Required regression evidence: a CLI-only candidate with no Web service aborts on RAM/GPU pressure, sampler death, and sampling gap during both broker warmup and execution; no replacement worker/broker is launched after the abort latch; cleanup failure is preserved as a failure. A production caller cannot acquire this authority using a purpose string alone.

### F3 [P1] Make the RTF pass/fail rule measurable for the existing 1x simulator

Design locations: lines 203-206.

The literal gate requires every worker's minimum 1 s rolling RTF to be at least 1.0 and aborts after two lower windows, without specifying active phases, clock-generation boundaries, window overlap, or observation uncertainty. The current MuJoCo implementation sleeps for 1 ms in its ordinary loop and advances until slightly ahead of wall time: `third_party/mujoco_ros2_control/mujoco_ros2_control/src/mujoco_simulation.cpp:2193-2201,2260-2304`. Even healthy 1x simulation therefore has quantization and scheduling error on either side of 1.0; overlapping windows can turn one timing perturbation into many consecutive failures. Startup before the first clock, legitimate reset/restart epochs, and completed/idle slots also lack a defined RTF denominator. As written, normal behavior can fail every N without demonstrating insufficient compute capacity.

Minimum correction: define which per-worker runtime/clock epoch is observed, when a full active window becomes eligible, and how startup/reset/teardown are bounded separately. Freeze the estimator, window stride, time-source synchronization, and an explicit error bound before measurement. Judge genuine sustained lag against that bound and retain the raw RTF and lag values. Do not silently lower the target, speed up physics, or hide actual backlog; a proposed policy change still needs the normal design approval.

Required regression evidence: a healthy quantized 1x clock passes; sustained below-target progress fails; no-clock/stale-clock and epoch changes cannot manufacture a pass; two overlapping samples of the same short perturbation are not mistaken for two independent full-window deficits.

### F4 [P1] Bind resource admission to covered workload phases, including allowed recovery

Design locations: lines 211-214, 219-220, 231-240. Primary anchor: lines 231-240.

Five 20-point batches and one simultaneous N-worker window do not establish an upper envelope for every permitted workload path. The design correctly allows genuine business failures in resource qualification, but a batch can then finish with much less inference/render/motion work than a successful batch. It also separates fault campaigns from qualification without saying that measured resource peaks from successful bounded recovery must enter the approved envelope. This matters in the actual composition: initial startup warms the broker before starting workers (`mujoco_parallel_batch.py:3747-3756`), whereas broker recovery reloads/warms it while the N existing worker runtimes remain resident (`3177-3198`). The latter overlap is not covered by a normal cold-start maximum. Existing warmup of both models also does not, by itself, demonstrate the maximum concurrent inference/render load.

Minimum correction: define a finite phase/coverage matrix for each exact N covering the supported inference paths, representative N-way steady load, and allowed broker/worker recovery overlap. Resource evidence used for the envelope may come from separate bounded campaigns; those outcomes must remain outside the five-run business/normal qualification denominator. A candidate missing a required phase cannot be promoted merely because all its points reached a valid terminal failure. Fold all required covered peaks and their uncertainty into the same profile or explicitly disallow the uncovered path without expanding the current scope.

Required regression evidence: a five-run set whose points all fail before the relevant workload phase cannot alone satisfy coverage; a broker reload peak larger than normal startup raises the required budget; fault-triggered expected cancellation is never counted as a business success or a normal qualification pass.

## Non-blocking clarifications for the implementation plan

### C1 [P2] Make measurement and adaptive allocation contexts explicit types

Design locations: lines 128-144, 160-166; compatibility scope at lines 24, 101-102.

`ResourceBudgetProvider.admit(profile: ApprovedBudgetProfile, purpose: str)` does not express a candidate context without an approved profile, although section 6 intends exactly that. The unconditional sentence about all adapters checking an approved profile also needs an explicit production-only qualifier. Separately, ADAPTIVE currently shares `ProductionBatchComposition` and uses `AllocationPolicy(enforce_resource_thresholds=False)` at `mujoco_parallel_batch.py:2523-2533`; its pool uses the same allocator. A string-purpose branch or a generic false flag would make it easy either to gate ADAPTIVE on fixed-N evidence unintentionally or to expose a fixed-mode bypass.

In the plan, define distinct production/measurement/adaptive contexts with closed constructors and the correct authority for each. Add negative tests for forged/mixed contexts and an ADAPTIVE regression showing its existing authority/fallback semantics survive removal of K. The intended separation is already in the design; this comment asks that interfaces express it.

### C2 [P2] Freeze the headroom accounting equations and phase ownership

Design locations: lines 168-183, 192-207.

The 20% rule is a clear target, but `baseline_background_peak_bytes` and `effective_host_cores` have no exact definitions. PSS, cgroup memory charges, and `MemTotal-MemAvailable` are different quantities; summing them double-counts some pages, while PSS alone omits kernel/cache charges. A cgroup quota caps average CPU over its configured period and is not interchangeable with physical/logical capacity or a 100 ms peak. The production recheck/watchdog must also distinguish already-started owned workload from background so the same load is not added twice during staged startup or restart.

The plan should freeze units (bytes and core-seconds per second), cgroup hierarchy/delegation, CPU period and cpuset intersections, baseline/owned/unattributed categories, and the pre-spawn versus in-flight equations. Include numeric table tests proving exactly what 20% means at equality, under a restricted cpuset, and with shared pages/cache and broker reload. Retain whole-device GPU and whole-host safety guards; do not replace them with process allocations.

### C3 [P2] Point recovery handoff at the ledger for the registered serving root

Design locations: lines 282-288.

The named `so101-moveit-expert-validation-web-experiment-ledger.md` is a historical development ledger; its snapshot references a different evidence root. The current serving continuation ledger is `docs/experiments/so101-teleop-serving-worker-eight-continuation-ledger.md`, whose lines 8-9 bind this design's registered root and checkpoint CP-L02. Add that serving ledger as the recovery handoff reference while retaining the older ledger as historical context, so the executor resumes the intended process/evidence ownership chain.

## Accepted boundaries and disposition

The design correctly removes K rather than replacing it with a large value, preserves lease counting as statistics, preserves exact N with no downgrade, separates fixed and adaptive authority, treats v1 artifacts as immutable historical evidence, and keeps resource qualification separate from business success. It explicitly avoids promoting old N2/Task14 or recovery receipts into new qualification and includes the necessary recovery deployment prerequisite. Those directions are accepted.

The decision is CHANGES_REQUIRED for F1-F4. No N is approved by this review. Re-review the amended design against a new immutable hash before writing the final execution plan; the plan can then resolve C1-C2 into concrete interfaces and checks, and the design should correct C3's ledger reference. The review does not authorize runtime work or deployment.

retained: this review, the reviewed design, and all pre-existing evidence under the registered root.
archived: none.
deletion_candidates_created_by_review: none.
