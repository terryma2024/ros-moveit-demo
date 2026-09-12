# SO-101 parallel multi-point validation experiment ledger

```yaml
task_id: so101-parallel-multipoint-validation-20260912-v1
goal: Implement and qualify isolated MuJoCo workers with dynamic point leasing across the frozen 20-point catalog.
success_contract: One immutable execute batch physically passes all 20 catalog points with qualification_passed=true and all evidence, isolation, recovery, and cleanup gates satisfied.
worktree: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1
branch: codex/so101-parallel-multipoint-validation
base_commit: 5bfc5dbe7a7a92448f6e89a9a262b82117dec0a5
current_commit: e94143e015370cfc2f53c70ec552bbede4fbf825
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1
confirmed_conclusions:
  - The dispatch receipt and frozen plan, design, and point catalog hashes were verified before implementation (CP-001).
  - The canonical checkout remains at the expected base with only its pre-existing .gitignore change (CP-001).
  - The implementation worktree uses the pinned clean mujoco_ros2_control gitlink 71bc9346cf93d6227a6678fcacf63f3e18acfcba (CP-001).
  - The shared detector runtime is review-clean; its content-verified immutable image executed both frozen models successfully on the frozen P01 RGB (CP-008, EXP-007, EXP-008).
  - Isolated Worker resource admission is review-clean; EXP-017 admitted exactly two process-free Worker resource sets and left no owned process, container, or GPU task (CP-009).
  - The Worker state machine is review-clean with deadline-bounded authorization RPCs, mode-specific durable start evidence, local sealing before commit, and atomic deadline-bound recovery/readmission (CP-010).
  - The isolated Worker runtime is review-clean with headless launch constraints, strict owned-process identity, mode-separated execution, attempt-bound fresh visual/numeric evidence, and replacement-backed process generations (CP-011).
  - The authenticated coordinator CLI is review-clean with exact Worker/Broker IPC, process-tree cleanup, source-clock pose admission, artifact composition, and stale-overlay rejection (CP-012).
  - Crash-window and Broker-recovery behavior is review-clean; abnormal terminal reasons cannot produce successful batch or validation outcomes (CP-013).
  - The fresh three-package overlay, complete ordinary package gate, installed provenance, and immutable dual-model Broker image are qualified for live validation (CP-014, EXP-022).
  - F35 preserves bounded Worker initialization diagnostics and closes the supervised-exit observation race without weakening absent-process or PID-reuse rejection; the complete ordinary gate and rebuilt immutable image passed (CP-015).
  - F36 retries idempotent paused snapshots for volatile subscribers, serializes Worker cleanup publication, and boundedly observes an exiting exact child; the complete ordinary gate and rebuilt immutable image passed (CP-016).
disproven_routes:
  - The canonical install overlay is not usable for this task because setup.zsh references stale external overlays (CP-001).
open_hypotheses:
  - The reviewed architecture can meet all contract, crash-recovery, isolation, live-small, and 20-point qualification gates on this host.
latest_checkpoint: CP-016
next_experiment: EXP-032
```

Frozen provenance:

- Plan SHA256: `9a1af647bd232e9ad614f5e9b032ccac2e9a2f47f6e8c6887fa38a0406cf67fe`
- Design SHA256: `51e7baee4dfbbfbbe779415e0e929e7a9e63dea308e15051727cc7fab462d3ca`
- Catalog SHA256: `c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5`
- YOLO-Seg weights SHA256: `f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781`
- Grounded-SAM bundle manifest SHA256: `0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775`
- Runtime overlay: `/data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install` (fresh build pending)
- `ROS_DOMAIN_ID`: per-worker allocation pending; allowed pool is 181–183.
- `GZ_PARTITION`: `not_applicable` for the MuJoCo-only implementation.

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: The reviewed architecture can satisfy the frozen parallel validation contract.
working_tree_status: docs/experiments/so101-parallel-multipoint-validation-experiment-ledger.md is the only uncommitted tracked path; SDD files are git-ignored.
owned_processes: NONE
preserved_processes: NONE; preflight found no relevant MuJoCo, MoveIt, RViz, Gazebo, pick-place, or parallel perception process.
confirmed_conclusions:
  - Dispatch receipt exact IDs and all three frozen input hashes were read back successfully.
  - Worktree and branch were created from canonical HEAD without carrying the canonical .gitignore change.
  - Pinned third_party/mujoco_ros2_control submodule checkout is initialized, clean, and matches the gitlink.
disproven_routes:
  - Sourcing /data/work/ws_moveit/install/setup.zsh is unsafe for this task because it references stale external installs.
open_risks:
  - No worktree-local build or test evidence exists yet.
  - Resource and model/container admission have not yet been run.
next_command: Generate the Task 1 SDD brief after completing the preflight consistency scan.
```

Evidence classification at CP-001:

- Retained: `/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/handoff/`, `source-before.json`, and `reports/submodule-status.txt`.
- Archived: none.
- Deletion candidates: none yet; scratch directories will be listed without deletion after each test run.

Preflight rulings adopted before Task 1:

- Ruling F1: Model candidates use `QUALIFIED`; only persisted Worker-local `POSE_ACCEPTED` authorizes MoveIt. Cost if wrong: shared enum and dependent tests require refactoring.
- Ruling F2: Shared validation/inference identities are owned by Task 1 contracts, mode-specific coordinator transitions by Task 3, and mode-specific sealing/runtime adapters remain explicit. Cost if wrong: early cross-task API rework.
- Ruling F3: Task 7 uses injected transport and authorization ports; Task 11 owns the only real IPC/auth protocol and socket integration. Cost if wrong: Task 11 integration rework.
- Ruling F4: MuJoCo v1 keeps simulation/bridge ports and `GZ_PARTITION` as `not_applicable`; actual allocatable resources remain unique. Cost if wrong: future backend work needs a new reviewed adapter.
- Ruling F5: heartbeat loss uses the frozen 5-second timeout; recovery uses the frozen 120-second timeout without resetting phase or batch start. Cost if wrong: conservative recovery or stuck cleanup.
- Ruling F6: result expiry consults an injected sealed-result verifier/discovery port under the coordinator lock; journal history remains authoritative. Cost if wrong: adapter ordering rework before live validation.
- Ruling F7: this ledger exists from setup, stays controller-owned, and allocates fresh monotonic experiment IDs before every run. Cost if wrong: example numbering differs while preserving audit chronology.
- Ruling F8: a `VALID` experiment only means evidence is usable; Task 15 admission additionally requires an actually accepted small execute result, fault gates, cleanup, and headroom. Cost if wrong: an extra small batch is required.
- Ruling F9: live Worker/Broker termination tests use plan-only; Task 12 covers crash windows, timeout, and recovery failure through injected integration boundaries, with simulated and real-process evidence separated. Cost if wrong: additional safe non-execute runs.
- Ruling F10: RED requires collected behavioral failures after all test helpers and imports are valid. Cost if wrong: extra test-authoring work.
- Ruling F11: Preserve the exact frozen catalog bytes and SHA256 despite the authoritative file's trailing blank line being reported by `git diff --check`. Cost if wrong: a formatting-only check remains exceptional for this immutable input.
- Ruling F12: Task 1 uses a package-selected contract build; before runtime validation, build `so101_mujoco_support`, `so101_teleop`, and `so101_demo_py` freshly into the worktree overlay over Jazzy, avoiding the Linux-incompatible local macOS vendor selected by `--packages-up-to`. Cost if wrong: a later runtime dependency may require another scoped build ruling.
- Ruling F13: Pure implementation unit-test RED/GREEN cycles retain scratch, command, and exit evidence but do not consume runtime experiment IDs; IDs begin with formally frozen package/runtime gates. Cost if wrong: test-only cycles are absent from the runtime experiment index but remain fully auditable in task reports.
- Ruling F14: Preserve the strict WorkerRoot artifact layout (`attempts/<point>/<attempt>` and `validations/<point>/<validation>`) and wire coordinator reservations plus `SealedResultAdapter` consistently in Task 11, allowing a narrowly scoped coordinator integration edit if necessary. Cost if wrong: cross-owner integration rework is required; weakening the layout would invalidate isolation and recovery discovery.
- Ruling F15: EXP-001 validly failed in the pre-existing `so101_teleop` web build under its pinned Three.js/TypeScript dependency set. Task 7 may build `so101_demo_py` alone from the clean Jazzy underlay for isolated, non-physical detector-image qualification, but Worker/live admission remains blocked until the fresh three-package overlay succeeds. Cost if wrong: a separately scoped teleop prerequisite fix and complete rebuild are required before Task 11/13.
- Ruling F16: Task 9 fix round 1 may narrowly edit the Task 3-owned coordinator implementation and test so ATTEMPT_STARTED/VALIDATION_STARTED durably bind the strict point-initial gate summary in their idempotency identity, as the frozen design requires. It may update only the direct legacy start-ACK calls in `test_parallel_batch_artifacts.py` with valid summaries; production artifact code remains out of scope. Other Task 9 fixes remain Worker-local. Cost if wrong: a small coordinator port/replay compatibility adjustment; retaining the old port would leave the authoritative start event without its authorization evidence.
- Ruling F17: Start evidence is an exact discriminated union. Execute and plan-only persist the strict post-reset point-initial gate summary; dry-run persists a strict scheduler-start summary bound to the current lease/epoch/Worker generation/point/validation identity with `point_gate_applicable=false`, `physical_runtime_started=false`, and `scheduler_only=true`. Dry-run must not fabricate reset/session/source-frame evidence. Cost if wrong: Task 11 needs a small transport union adapter; imposing a physical gate would violate the frozen dry-run contract.
- Ruling F18: Recovery/readmission must be deadline-aware under the coordinator lock. The next generation may be registered while the slot remains RECOVERING, but only `record_recovery` may atomically expose AVAILABLE, and only when the supplied absolute deadline exactly matches the immutable recovery-stage deadline and coordinator time remains strictly before it. Late or failed transactions remain RECOVERING or QUARANTINED and never expose an intermediate AVAILABLE old generation. Cost if wrong: a small coordinator recovery API/order update; allowing late remote mutation creates a transient authorization window.
- Ruling F19: Task 11 may narrowly extend the Task 7 CLI/transport seam, the Task 9 Worker Broker port, and the Task 10 source-stamped capture/runtime receipt, together with their direct tests, so a post-reset immutable canonical `.npy` RGB snapshot and exact durable ATTEMPT_STARTED/VALIDATION_STARTED idempotency identity cross the authenticated IPC boundary into one separately supervised Broker process. The Broker must verify the committed start event through coordinator authority, and production plan-only/execute may not retain an in-process Broker or fabricate source frame/hash/shape metadata. No detector, pose-admission, planning, execution, or result policy may change. Cost if wrong: focused cross-owner adapter rework; without this seam the reviewed Task 7, 9, and 10 contracts cannot be composed truthfully in Task 11.
- Ruling F20: Task 11 may add `runtime/parallel_ros_runtime.py` and its direct `test_parallel_ros_runtime.py`, and wire them only through its CLI, to provide the missing concrete production ports with fresh read-only ROS/MuJoCo observations. The adapter must reuse qualified reset/client, RGB-D, mask back-projection, planning-scene, planning, and dynamic-consumer primitives; it must prove canonical joints, zero active controller/MoveIt goals, no MoveIt attachment, no contact, and no stale or duplicate Worker node from actual observations, and localize only the authenticated Broker mask against exact-stamp depth/TF. It may not substitute color segmentation for the Broker mask, infer absent observations as true, or duplicate motion/perception policy. Cost if wrong: the adapter may need later separation into owning modules, but a test-only injection path cannot satisfy the reviewed production CLI.
- Ruling F21: Task 11 may narrowly extend the strict v1 runtime config/contract and direct contract tests with `max_frame_age_s=5.0`, `max_rgbd_skew_s=0.0`, and `max_tf_skew_s=0.0`, then compose the Task 5 `PoseAdmissionLatch` and `PerceptionPolicy` through the F20 production adapter. The age value comes from the already-frozen MuJoCo dynamic-pick policy; zero skew is required by the existing exact-stamp RGB-D and TF contracts. Reset completion must be a fresh same-session/same-epoch MuJoCo simulation-time watermark and latch time must come from the ROS simulation clock, never host monotonic. Geometry and quality gates reuse frozen policy/candidate evidence; no threshold or truth default may be invented. Cost if wrong: a small frozen-schema adjustment is required; refusing the seam would bypass durable `POSE_ACCEPTED` or mix clock domains.
- Ruling F22: Task 12 may narrowly extend the existing artifact, process-supervisor, and parallel CLI seams plus only their direct tests. The original seven-file boundary cannot expose real working-fsync, atomic-seal, and recovery-receipt crash windows, and the production composition currently treats an external Broker exit as an immediate batch failure instead of the frozen unhealthy-pause/recovery lifecycle. The extension may only add dependency-injected durability hooks, exact-owned-process retirement, Broker generation `g+1` restart with a fresh immutable endpoint/spec/token and authenticated warmup/readback, and authenticated Worker discovery of the current Broker endpoint/generation before later work. It may not add a production fault flag, weaken admission, adopt an unowned process, reset K, or duplicate the coordinator state machine. Cost if wrong: focused cross-owner adapter tests and another review round; refusing the seam would violate the design and make the Task 14 Broker fault gate impossible.
- Ruling F23: Task 12 may narrowly extend `parallel_batch/contracts.py` and its direct contract tests so aggregate qualification is bound to the authoritative batch terminal reason. A `SHARED_DEPENDENCY_UNAVAILABLE` or any other abnormal terminal reason preserves durable per-point results but can never yield `qualification_passed=true`; only the normal points-complete path may qualify after all existing gates pass. Direct already-authorized projections may be updated only as required by the strict constructor/schema. Cost if wrong: a small aggregate-contract migration; leaving the field independent of terminal cause could falsely qualify a batch whose shared dependency failed.
- Ruling F24: Apply the same terminal-reason binding to `validation_passed` and the non-execute CLI outcome. Dry-run or plan-only ending for any reason other than normal `POINTS_COMPLETE` preserves validation history but must report `validation_passed=false` and a nonzero outcome even after cleanup. Scope remains the F23 contract/CLI seams and direct tests. Cost if wrong: validation-only evidence could falsely pass after a shared-dependency failure.
- Ruling F25: Task 13 keeps `/usr/bin/python3` as the colcon and pytest interpreter but prepends the established locked `/data/work/venvs/so101-grounded-sam/lib/python3.12/site-packages` to the sourced worktree/ROS Python path. Readback proved this exact combination imports torch 2.13.0+cu130, mujoco 3.12.0, ROS Jazzy modules, and the worktree `FreeJointState`. No source test is skipped or changed. Cost if wrong: EXP-019 is INVALID and package admission remains closed; using the bare system path already made EXP-018 invalid at collection.
- Ruling F26: The locked ML site-packages are injected only after the package build and worktree overlay source, immediately before the test/import phase. Build retains the bare ROS/worktree interpreter environment because the venv setuptools does not support colcon's develop uninstall option. Cost if wrong: another fresh experiment is required; mixing the test-only dependency path into build already invalidated EXP-019 before test startup.
- Ruling F27: The Task 13 pytest scratch remains a unique previously nonexistent directory under the registered durable evidence root, but its leaf is deliberately short enough that test-owned Unix sockets remain at most 107 bytes. The exact interpreter must still resolve tempfile inside that directory. Cost if wrong: EXP-021 is INVALID; lengthening a security test's socket path already produced 48 expected fail-closed results in EXP-020.
- Ruling F28: Task 13 supplies the current reviewed container CLI's required exclusive `--output` receipt for build, then passes its read-back immutable image ID together with a fresh private batch root to smoke. This reconciles the frozen intent with the stricter Task 11 interface added after the plan example. Cost if wrong: image qualification fails closed without Docker mutation or a fresh experiment is required.
- Ruling F29: Every live/fault experiment must commit its PLANNED/RUNNING ledger state in a ledger-only pre-run commit, then append results in a later ledger-only commit. The reviewed production CLI rejects any dirty repository path, including its own controller ledger, before creating batch evidence. Executable source remains pinned to 30f18b7dc's code tree while the clean runtime HEAD may advance by ledger-only commits. Cost if wrong: admission fails before side effects as EXP-023 did; omitting pre-registration would violate the experiment state machine.
- Ruling F30: Live commands prepend the verified worktree package libexec directory `/data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install/so101_demo_py/lib/so101_demo_py` to PATH before invoking `ros2 run`. ROS 2 can locate a libexec without PATH, but the reviewed independent provenance verifier requires `shutil.which("so101_parallel_batch")` to bind the exact installed wrapper. Cost if wrong: admission fails before side effects as EXP-024 did; invoking an unverified wrapper would violate installed-byte admission.
- Ruling F31: Task 14 returns to the Task 11 provenance owner for a scoped TDD fix in `mujoco_parallel_batch.py` and its direct CLI test. The verifier must derive the actual repository package_dir layout `src/so101_demo_py/src/cli/...`; it may not weaken console/config/catalog checkout fencing. Cost if wrong: mixed overlays could be accepted; retaining the impossible extra `so101_demo` segment makes every real live run fail before side effects.
- Ruling F32: Task 14 may make the matching scoped TDD correction to the installed-editable-tree identity in `mujoco_parallel_batch.py` and its direct CLI test. The verifier must bind `build/so101_demo_py/so101_demo` to this repository's actual `package_dir={"so101_demo": "src"}` source root `src/so101_demo_py/src`, while retaining exact module, console, egg-link, entry-point, wrapper-byte, and tree-byte checks. Cost if wrong: a stale or foreign editable tree could be accepted; retaining the impossible nested source target makes every real live run fail before resource or process side effects.
- Ruling F33: Domain-pool preflight and cleanup must stop controller-created ROS 2 discovery daemons for domains 181-183 and verify those domains with `--no-daemon` or the production same-UID `/proc` probe before a live run. The three daemons found by EXP-027 were created at the Task 14 preflight timestamp and are task-owned diagnostic residue, not Worker processes or external users. Cost if wrong: stopping a foreign daemon would disturb unrelated discovery; retaining our own daemons makes every resource admission fail before batch-root creation.
- Ruling F34: Task 14 returns narrowly to the Task 11/12 Broker lifecycle seams and their direct tests. Initial model-backed Broker readiness must use the frozen 90-second Broker recovery/startup budget instead of the 5-second steady-state heartbeat-loss budget. The Docker launch must publish a private batch/generation-specific cidfile, and cleanup/recovery must verify that exact container's immutable image, labels, and batch-specific mounts before stopping it; aggregate cleanup cannot pass while that container remains. Cost if wrong: an unrelated container could be stopped, or a detached Broker/GPU process could survive while the batch falsely reports cleanup complete; retaining the current behavior guarantees cold-start timeout and already produced both defects in EXP-028.
- Ruling F35: Task 14 returns narrowly to the Task 9 Worker failure-reporting seam and Task 11 process supervisor, with direct tests only. A Worker that catches a reset or initial-gate exception must emit a bounded, structured local result identifying the failed boundary without changing its conservative `INITIAL_GATE_FAILED` outcome. If a supervised process exits between a first `poll()==None` observation and `/proc` identity readback, the supervisor must re-poll once: a now-terminal exact child follows the existing exit/group-survivor path, while a still-running absent identity remains `OWNED_PROCESS_ABSENT`; PID mismatch remains fatal. Cost if wrong: exception text could leak unbounded data or PID reuse could be accepted; retaining current behavior makes live failures unauditable and replaces the original Worker result with a supervisor traceback, as EXP-029 demonstrated.
- Ruling F36: Task 14 returns narrowly to the existing MuJoCo paused-evidence acquisition and Worker-owned process-tree seams, with direct tests. A newly joined volatile sensor-data subscriber must retry the already-authorized idempotent `pause(True)` snapshot request within the existing timeout until it receives a fresh authoritative paused frame; it may not unpause or advance physics. Worker child-list mutation and manifest publication must be serialized across the main and authenticated control threads so cleanup cannot collide on or reorder one PID-named temporary publication. The supervisor may boundedly yield and re-poll only while the exact owned child has become absent between observations; a still-nonterminal result remains fatal and PID mismatch remains fatal. Cost if wrong: retry could mask a failed pause or concurrent cleanup could republish stale ownership; retaining current behavior makes every post-reset watermark read fail and produced manifest/temp plus exit-observation races in EXP-030.

```yaml
checkpoint_id: CP-002
last_valid_experiment: NONE
current_hypothesis: Crash-safe journal semantics can be added on top of the reviewed contract layer without weakening exact-byte or validation/physical separation.
working_tree_status: docs/experiments/so101-parallel-multipoint-validation-experiment-ledger.md is the only uncommitted tracked path; SDD files are git-ignored.
owned_processes: NONE
preserved_processes: Existing unrelated Python/colcon processes outside this task were not touched.
confirmed_conclusions:
  - Task 1 is review-clean after two fix rounds and controller verification passed 29 contract tests in a fresh scratch.
  - Installed catalog SHA256 is c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5 from the worktree overlay.
  - Fresh zsh provenance requires ROS setup scripts to run without nounset; the controller test helper was corrected and reverified.
disproven_routes:
  - Module import success from a long-lived shell is insufficient provenance; a fresh zsh exposed the test-helper nounset defect.
  - `colcon build --packages-up-to so101_demo_py` is not a viable Linux command in this checkout because tools/mujoco_vendor_macos shadows the Jazzy vendor.
open_risks:
  - The complete runtime overlay including so101_teleop has not yet been built.
  - No runtime, Broker, resource, or physical experiment has started.
next_command: Generate and dispatch the Task 2 crash-safe journal brief.
```

```yaml
checkpoint_id: CP-003
last_valid_experiment: NONE
current_hypothesis: The coordinator can preserve queue, K, leases, validation, deadlines, and cleanup qualification as a deterministic replayable projection.
working_tree_status: docs/experiments/so101-parallel-multipoint-validation-experiment-ledger.md is the only uncommitted tracked path; SDD files are git-ignored.
owned_processes: NONE
preserved_processes: Existing unrelated Python/colcon processes outside this task were not touched.
confirmed_conclusions:
  - Task 2 is review-clean after one fix round and controller verification passed 61 journal plus contract tests.
  - Corrupted committed frames, impossible partial lengths, and recursive non-string JSON keys fail closed without epoch advancement.
  - Directory durability tests verify file fsync, publication, and exact-parent fsync ordering.
disproven_routes:
  - Treating every incomplete final payload as a torn tail is unsafe when existing checksum, payload, or newline bytes prove length-field corruption.
open_risks:
  - Journal behavior is not yet integrated with coordinator sealed-result discovery or runtime IPC.
  - Full runtime overlay and all live gates remain pending.
next_command: Generate and dispatch the Task 3 coordinator brief.
```

```yaml
checkpoint_id: CP-004
last_valid_experiment: NONE
current_hypothesis: Immutable attempt and validation sealing can provide the real verifier/discovery boundary required by the coordinator.
working_tree_status: docs/experiments/so101-parallel-multipoint-validation-experiment-ledger.md is the only uncommitted tracked path; SDD files are git-ignored.
owned_processes: NONE
preserved_processes: Existing unrelated processes outside this task were not touched.
confirmed_conclusions:
  - Task 3 is review-clean after one fix round and controller verification passed 135 coordinator plus journal tests.
  - Recovery and cleanup accept only real booleans, point completion is separate from cleanup, and frozen selection order survives replay.
  - Result commit and expiry are serialized around an injected sealed-result verification/discovery port.
disproven_routes:
  - Truthiness is not acceptable for safety confirmations.
  - Cleanup state cannot define whether all point outcomes have reached terminal status.
open_risks:
  - The injected result port has no real artifact implementation yet.
  - Runtime ACK timers, process ownership, Broker, and physical validation remain pending.
next_command: Generate and dispatch the Task 4 artifact-sealing brief.
```

```yaml
checkpoint_id: CP-005
last_valid_experiment: NONE
current_hypothesis: YOLO-first fallback and pose admission can enforce candidate provenance without letting a perception candidate authorize MoveIt directly.
working_tree_status: docs/experiments/so101-parallel-multipoint-validation-experiment-ledger.md is the only uncommitted tracked path; SDD files are git-ignored.
owned_processes: NONE
preserved_processes: Existing unrelated processes outside this task were not touched.
confirmed_conclusions:
  - Task 4 is review-clean after one fix round and controller verification passed 187 artifact, task-artifact, and coordinator tests.
  - A sealed result is accepted only after its publication parent fsync succeeds; discovery reuses the same verifier.
  - Final-manifest digest I/O failures are normalized to the coordinator port's ValueError-compatible ArtifactError boundary.
disproven_routes:
  - Visibility after rename is not sufficient durability evidence when the parent-directory fsync failed.
  - Raw filesystem exceptions must not leak through the sealed-result verification port.
open_risks:
  - Coordinator reservation paths and the concrete sealed-result adapter still require consistent Task 11 wiring under the strict WorkerRoot layout.
  - Runtime ACK timers, process ownership, Broker, and physical validation remain pending.
next_command: Dispatch Task 5 perception fallback and pose-admission implementation.
```

```yaml
checkpoint_id: CP-006
last_valid_experiment: NONE
current_hypothesis: A fair bounded Broker can preserve per-worker model isolation and generation fencing under backpressure and deadlines.
working_tree_status: docs/experiments/so101-parallel-multipoint-validation-experiment-ledger.md is the only uncommitted tracked path; SDD files are git-ignored.
owned_processes: NONE
preserved_processes: Existing unrelated processes outside this task were not touched.
confirmed_conclusions:
  - Task 5 is review-clean after one fix round and controller verification passed 349 perception, contract, artifact, and coordinator tests.
  - Model output remains a QUALIFIED candidate until a Worker-local, durable POSE_ACCEPTED event passes complete identity, generation, authorization, RGB-D, TF, session, and time checks.
  - Admission revalidates before and after persistence; a visible uncertain event permanently fences the current latch for recovery adjudication and cannot trigger model fallback.
disproven_routes:
  - Pre-write authorization and freshness checks are insufficient across blocking fsync/readback windows.
  - A static Broker-generation comparison is insufficient when injected validators can block and generation can change.
open_risks:
  - The Broker queue/deadline implementation and real detector transport remain pending.
  - Runtime ACK timers, process ownership, sealed-result wiring, and physical validation remain pending.
next_command: Dispatch Task 6 fair bounded Broker implementation.
```

```yaml
checkpoint_id: CP-007
last_valid_experiment: NONE
current_hypothesis: The real shared detector runtime can preserve the reviewed Broker and Worker-only pose-admission boundary inside the frozen isolated container contract.
working_tree_status: docs/experiments/so101-parallel-multipoint-validation-experiment-ledger.md is the only uncommitted tracked path; SDD files are git-ignored.
owned_processes: NONE
preserved_processes: Existing unrelated processes outside this task were not touched.
confirmed_conclusions:
  - Task 6 is review-clean after three fix rounds and controller verification passed 220 Broker and perception tests.
  - Queue and inference deadlines are independently enforced at every result boundary; cancellation, health loss, and clock faults permanently fence cached candidates.
  - Terminal publication preserves the first result under reentrant callbacks, and candidate ownership never exposes the Broker's internal cache.
  - Queued plus running work remains limited to one request per Worker/model, with per-model cap 3 and total cap 6.
disproven_routes:
  - A guard before a final copy is insufficient because copying and callbacks can cross deadlines or publish a new terminal result.
  - Outcome-specific commit paths are unsafe; all model outcomes require identical deadline, fencing, and health checks.
open_risks:
  - Cross-process generation persistence and transport rejection of old envelopes remain Task 7/11 integration work.
  - Combined CUDA image build, full-model smoke, runtime ACK ownership, and physical validation remain pending.
next_command: Dispatch Task 7 shared detector runtime, container, build, and smoke implementation.
```

```yaml
checkpoint_id: CP-008
last_valid_experiment: EXP-008
current_hypothesis: Two isolated Worker resource sets can be allocated without inherited ROS namespace, filesystem, socket, or capacity collisions.
working_tree_status: docs/experiments/so101-parallel-multipoint-validation-experiment-ledger.md is the only uncommitted tracked path; SDD files are git-ignored.
owned_processes: NONE
preserved_processes: Existing unrelated processes outside this task were not touched.
confirmed_conclusions:
  - Task 7 is review-clean after one fix round and controller verification passed 356 runtime, container, adapter, Broker, and perception tests in fresh scratch pytest-Ii3XxrMv.
  - Image f7ac5cbe5e67491aa0cbc71003c2e5c3fa6378025a585eb96e7c02a67c25e115 verifies the copied source content cd3b4b607881a090503be9c0e7d7ea7bb0327d090b8368f0b0e13be7c76c2427 independently of its labels.
  - EXP-008 executed both YOLO and Grounded-SAM on the frozen P01 RGB and returned one QUALIFIED candidate from each with finite non-negative latency; no container or GPU compute process remained.
  - Authorization, transport, timeout, model-stage, provenance, filesystem mode, and startup failures now fail closed at their reviewed boundaries.
disproven_routes:
  - Image labels alone are not source provenance; actual copied content must be recomputed during build, host readback, and runtime startup.
  - Authorization exceptions and scheduler-discovered timeouts cannot be represented as ordinary cancellation or a healthy empty poll.
open_risks:
  - Ruling F3 reserves one real authenticated socket and non-root transport integration for Task 11.
  - Ruling F15 still blocks Worker/live admission until the fresh three-package overlay succeeds; Task 8 resource dry admission is process-free and may proceed.
next_command: Dispatch Task 8 isolated Worker resource allocation and dry-admission implementation.
```

```yaml
checkpoint_id: CP-009
last_valid_experiment: EXP-017
current_hypothesis: The Worker state machine can preserve dual readiness gates, attempt authorization, generation fencing, watchdog deadlines, and mode-separated terminal evidence on top of the reviewed resource allocator.
working_tree_status: docs/experiments/so101-parallel-multipoint-validation-experiment-ledger.md is the only uncommitted tracked path; SDD files are git-ignored.
owned_processes: NONE
preserved_processes: Existing unrelated processes outside this task were not touched.
confirmed_conclusions:
  - Task 8 is review-clean after four fix rounds and controller verification passed 152 resource and contract tests in fresh scratch pytest-mgldGNMe.
  - EXP-017 admitted exactly two isolated Worker resource sets with 24 CPUs, 26.920 GiB MemAvailable, and 14.914 GiB free GPU against the frozen two-Worker thresholds.
  - Domain claims are acquired all-or-none before process scan and held through immutable manifest publication; every Worker/domain/session/path/socket/EGL identity was unique and no owned process, container, or GPU task remained.
  - Three-Worker admission fails closed until Task 11 supplies independent Task 14 acceptance and stable full-content current provenance for source, install, config, policy, scene, models, container, and catalog.
disproven_routes:
  - Shallow label, revision, or file-count JSON is not executable provenance; actual content or a canonical per-content inventory must be bound.
  - A single current-provenance sample is insufficient; pre/final stable epochs and a final independent acceptance reread are required before admission.
open_risks:
  - Task 9 Worker watchdog, readiness, authorization, recovery, and run-mode separation are not yet implemented.
  - Ruling F15 continues to block real Worker/live gates until a fresh three-package overlay succeeds.
next_command: Generate and dispatch the Task 9 Worker state-machine brief.
```

```yaml
checkpoint_id: CP-010
last_valid_experiment: EXP-017
current_hypothesis: Independent headless MuJoCo and MoveIt runtimes can consume the reviewed Worker resources and state machine without violating owned-process or run-mode boundaries.
working_tree_status: docs/experiments/so101-parallel-multipoint-validation-experiment-ledger.md is the only uncommitted tracked path; SDD files are git-ignored.
owned_processes: NONE
preserved_processes: Existing unrelated processes outside this task were not touched.
confirmed_conclusions:
  - Task 9 is review-clean after two fix rounds; reviewer gate pytest-26mG2Uo9 passed 287 tests and controller gate pytest-tBoyvRq6 passed 536 tests.
  - EXECUTE and PLAN_ONLY start evidence requires the strict POINT_INITIAL_GATE summary, while DRY_RUN uses the strict nonphysical SCHEDULER_START discriminator without fabricated reset facts.
  - Authorization RPCs are deadline-bounded and a conservative local terminal is sealed exactly once before coordinator finalization.
  - Recovery uses the coordinator-frozen immutable deadline and F18 permits no intermediate AVAILABLE or grant window before final atomic recovery recording.
disproven_routes:
  - A pre-heartbeat watchdog check alone cannot fence a fault that arrives while the current-token RPC is in flight.
  - A Worker-derived recovery deadline is not authoritative and may extend the coordinator's frozen recovery budget.
open_risks:
  - Task 10 isolated headless runtime composition and owned-process lifecycle are not yet implemented.
  - Ruling F15 continues to block real Worker and live gates until a fresh three-package overlay succeeds.
next_command: Generate and dispatch the Task 10 isolated headless runtime brief.
```

```yaml
checkpoint_id: CP-011
last_valid_experiment: EXP-017
current_hypothesis: Authenticated local IPC and an owned-process supervisor can expose the reviewed Coordinator, Broker, Worker, resource, artifact, and runtime components without weakening their fencing.
working_tree_status: docs/experiments/so101-parallel-multipoint-validation-experiment-ledger.md is the only uncommitted tracked-intent path; SDD files are git-ignored.
owned_processes: NONE
preserved_processes: Existing unrelated processes outside this task were not touched.
confirmed_conclusions:
  - Task 10 is review-clean after two fix rounds; reviewer process-free-expanded evidence had 92 passing tests plus exactly two inherited F15 overlay failures, and controller process-free gate pytest-5gvj0ve3 passed 92 tests with those two nodes deselected.
  - Linux headless launch retains sensor rendering, task camera, controllers and MoveIt while forbidding teleop; macOS headless and sensor-disabled headless configurations fail closed.
  - Execute waits for consumer subscription before volatile pose publication, while plan-only retains a connected seven-state prefix including MICRO_LIFT without an ActionClient goal.
  - RGB and depth/TF/physical receipts are source-fresh, canonical and point/attempt-bound; authoritative plan and execute completions capture terminal evidence.
  - Owned-process cleanup retains unresolved identities, and successful recovery consumes a deadline-checked generation g+1 resource replacement with a fresh session/environment before restart.
disproven_routes:
  - Publishing a one-shot volatile cup pose before consumer readiness is not reliable delivery.
  - Restarting generation g resources after Coordinator readmission as generation g+1 cannot process another lease and violates process/session fencing.
open_risks:
  - Task 11 authenticated IPC, supervisor and CLI wiring are not yet implemented.
  - Ruling F15 still blocks the three-package build, installed CLI readback, and all real Worker/live gates.
next_command: Generate and dispatch the Task 11 authenticated IPC, supervisor, and CLI brief.
```

```yaml
checkpoint_id: CP-012
last_valid_experiment: EXP-017
current_hypothesis: Deterministic fault injection can prove the review-clean coordinator, Broker, Worker, artifact, IPC, and process composition preserves conservative outcomes across every commit window.
working_tree_status: docs/experiments/so101-parallel-multipoint-validation-experiment-ledger.md is the only uncommitted tracked-intent path; SDD files are git-ignored.
owned_processes: NONE
preserved_processes: Existing unrelated processes outside this task were not touched.
confirmed_conclusions:
  - Task 11 is review-clean at faaa89b7189af09a82b713104be9d689c49043da after four fix rounds; final reviewer gate pytest-GDjxPlcG passed 139 tests with no Critical, Important, or Minor findings.
  - Authenticated exact-schema Unix IPC composes one external Broker with isolated Worker authorities, strict generation/lease/start-event identity, retry-safe idempotency, and an authenticated socket/inode-fenced ready handshake.
  - Production point reset applies the selected cup free-joint override, restores Planning Scene identity, resumes before source-fresh RGB-D, and admits only a durable Task 5 POSE_ACCEPTED using the ROS simulation clock.
  - SIGINT/SIGTERM cleanup publishes a lock-free stop fence before cancellation, confirmation and recovery, and exact process supervision proves no owned PGID survivors without name-based cleanup.
  - The installed console/module tree, source checkout, dirty state, config, policy, scene, models, container, catalog and selected-point hashes are bound and re-read before side effects.
  - Final process-free implementation gate pytest-PfQ9YFWE passed 995 tests with the two exact F15 nodes deselected; the nondeselected pytest-eutSZhL4 reproduced only those two inherited failures.
disproven_routes:
  - A stop flag published only after acquiring the execution lock cannot fence a blocking Broker or controller call.
  - A filesystem ready file and path existence are not a Broker identity proof; the gate requires an authenticated Unix-socket handshake and post-handshake inode fence.
  - Correct install paths alone do not prove current installed bytes.
open_risks:
  - Task 12 crash-window and fault-injection matrices have not yet run.
  - Ruling F15 still blocks the fresh three-package overlay, installed CLI readback, and all real Worker/live gates.
next_command: Generate and dispatch the Task 12 crash-recovery and fault-injection brief.
```

```yaml
checkpoint_id: CP-013
last_valid_experiment: EXP-017
current_hypothesis: The review-clean implementation can pass a fresh three-package overlay build, ordinary package gate, and final shared-detector image qualification before live validation.
working_tree_status: docs/experiments/so101-parallel-multipoint-validation-experiment-ledger.md is the only uncommitted tracked-intent path; SDD files are git-ignored.
owned_processes: NONE
preserved_processes: Existing unrelated processes outside this task were not touched.
confirmed_conclusions:
  - Task 12 is review-clean at e4d06020598eda8f22c54b3826802df84b84291f; the final independent review found no Critical, Important, or Minor findings.
  - Durable journal, seal, result, expiry, and recovery hooks preserve authority across every tested crash window without double K debit, double leasing, or committed-result overwrite.
  - Unexpected Broker exit pauses grants without spending K, retires only exact owned processes, and recovers as generation g+1 with fresh authenticated endpoint authority while fencing stale responses.
  - Only normal POINTS_COMPLETE termination can set qualification_passed or validation_passed; abnormal shared-dependency failure remains unsuccessful while preserving history.
  - Controller gate pytest-XajTn4rR passed 265 tests; the expanded implementation gate pytest-EpRMIZv3 passed 805 tests.
  - The inherited F15 build failure was diagnosed as an incomplete generated @types/three installation. A forced frozen-lock reinstall restored 950 files, after which tsc -b and the full teleop web build passed without tracked source changes.
disproven_routes:
  - The prior teleop TypeScript failure was not a pinned source/API incompatibility; it was an incomplete generated node_modules tree.
open_risks:
  - The repaired dependency tree has not yet been proven by a fresh three-package colcon build and ordinary so101_demo_py package gate.
  - Live small-batch, controlled Worker/Broker fault, and full 20-point execute evidence do not yet exist.
next_command: Allocate EXP-018 and run the fresh three-package overlay build plus ordinary package gate.
```

```yaml
checkpoint_id: CP-014
last_valid_experiment: EXP-022
current_hypothesis: The qualified installed runtime and immutable Broker image can pass the two-Worker four-point execute and controlled plan-only fault gates with complete visual and cleanup evidence.
working_tree_status: docs/experiments/so101-parallel-multipoint-validation-experiment-ledger.md is the only uncommitted tracked-intent path; SDD files are git-ignored.
owned_processes: NONE
preserved_processes: Existing unrelated processes outside this task were not touched.
confirmed_conclusions:
  - The repaired node_modules tree supports a fresh so101_mujoco_support, so101_teleop, and so101_demo_py worktree overlay without tracked source changes.
  - EXP-022 passed the complete ordinary so101_demo_py gate with 2754 tests, 0 errors, 0 failures, and 0 skipped under the established locked-ML plus ROS runner; benchmark_test was not collected.
  - Installed console, module, config, and catalog resolve through the worktree; source/install hashes, frozen catalog/model hashes, git diff check, and compileall all passed.
  - The final combined Broker image is immutable ID sha256:3ca6f7db5303c05c6a899889d73c0cf16b1fe91c4e5d7ef2ce69af2ddbd7e5d4 with source and verified-source SHA256 c5fcae2e99975d37030ce1827d50367d36db404077b272687fe8f13d63a5f426.
  - Both frozen models returned QUALIFIED with one candidate on the frozen P01 image; no container or GPU compute application remained.
disproven_routes:
  - Bare /usr/bin/python3 lacks the locked torch and MuJoCo dependencies required by the complete ordinary suite.
  - Injecting the locked venv site-packages during setup.py build selects an incompatible setuptools path.
  - Long randomized pytest scratch leaves violate the intentionally strict Unix-socket path limit in security tests.
  - The frozen example image command omits the current reviewed CLI's mandatory exclusive build receipt and immutable smoke admission arguments.
open_risks:
  - No live two-Worker execute, controlled Worker/Broker fault, or fresh visual acceptance has run against this image ID.
  - Full 20-point qualification remains prohibited until Task 14 is VALID.
next_command: Read the gui-capture and gazebo-video-debug skills, allocate EXP-023, and run the four-point two-Worker execute gate.
```

```yaml
checkpoint_id: CP-015
last_valid_experiment: EXP-022
current_hypothesis: The F35-corrected runtime will either cross the point-initial authorization boundary or preserve the exact rejected boundary without replacing it with a supervisor traceback.
working_tree_status: clean at source commit 52bf3ef7dee36db9c35df9eec1153df05b3b686b before the EXP-030 ledger-only pre-run commit
owned_processes: NONE; no task container or NVIDIA compute application remains
preserved_processes: Existing unrelated processes outside this task were not touched.
confirmed_conclusions:
  - Behavioral RED pytest-IRfB7Mnv collected six focused cases with five expected failures; final focused pytest-NaPCXjHH passed 6/6 and expanded pytest-DIc9cH3V passed 165/165.
  - The supervisor re-polls only after an exact nonterminal-poll/absent-identity pair; a terminal second poll uses existing exit/group-survivor handling, while a second nonterminal result and every PID mismatch remain fatal.
  - Reset and point-initial-gate exceptions retain bounded single-line boundary/type/message diagnostics in a private no-replace worker-run-results.json without changing INITIAL_GATE_FAILED semantics.
  - Fresh p37 rebuilt so101_demo_py in 1.51 s and passed the complete ordinary suite in 83.47 s: 2762 tests, 0 errors, 0 failures, 0 skipped; benchmark_test was not collected. p36 is a retained harness-preparation failure caused by a malformed chmod command and never started build or pytest.
  - Installed source/build module trees are equal at SHA256 4bb127e71b57f7e4d35889d9d9b763511a039c7d16af123ea397b9ae831c7016.
  - Rebuilt immutable image sha256:d549146f76df4c8e4d747fa2c6c3d8ffb11302ce2f3d43d2a1bac98efc74153c binds equal source/verified SHA256 49b7d63b1bb3ef048540571964551edfa912429dea1f07f858bc59a8d7cb2acf. Fresh smoke2 returned one QUALIFIED candidate from each frozen model and left no container/GPU process.
  - Fresh EXP-030 preflight found no related process, container, GPU task, or ROS domain 181-183 owner; 24 CPUs, 25.933 GiB MemAvailable, and 14.911 GiB free GPU exceed admission.
disproven_routes:
  - A smoke batch root is a pre-existing trusted 0700 input; omitting it fails before container creation. The failed f35 smoke reports are retained and not reused; corrected smoke2 passed.
open_risks:
  - The exact sub-gate that rejected EXP-029 is not recoverable from old evidence; EXP-030 must produce either valid start evidence or the new Worker diagnostic.
  - No four-point execute has yet reached ATTEMPT_STARTED, so controlled fault and 20-point admission remain closed.
next_command: Execute the clean pre-registered EXP-030 two-Worker four-point batch using image sha256:d549146f76df4c8e4d747fa2c6c3d8ffb11302ce2f3d43d2a1bac98efc74153c.
```

```yaml
checkpoint_id: CP-016
last_valid_experiment: EXP-022
current_hypothesis: The F36-corrected runtime can retain an authoritative paused reset watermark for each new volatile observer and shut down both Workers without manifest or supervisor races.
working_tree_status: clean at source commit e94143e015370cfc2f53c70ec552bbede4fbf825 before the EXP-031 ledger-only pre-run commit
owned_processes: NONE; no task container or NVIDIA compute application remains
preserved_processes: Existing unrelated processes outside this task were not touched.
confirmed_conclusions:
  - Formal RED pytest-gNauEfcM failed all three targeted behavior tests at the intended paused-frame-loss, concurrent-manifest, and absent-child waitability assertions. The earlier pytest-wRZSvPkx lacked the worktree message overlay and is retained as a harness failure.
  - Final focused pytest-pVdw808t passed 6/6, adjacent pytest-WEuadMcR passed 63/63, and expanded pytest-x1NNDLN1 passed 303/303.
  - Paused evidence acquisition repeats only pause(True) within the original timeout; it neither unpauses nor advances physics. Worker child mutation and publication use one re-entrant lock, and absent-child repolling is bounded to 50 ms while PID mismatch remains immediately fatal.
  - Fresh p39 symlink build completed in 1.52 s and the complete ordinary suite passed in 83.60 s: 2765 tests, 0 errors, 0 failures, 0 skipped; benchmark_test was not collected. p38 is retained as a harness failure caused by omitting --symlink-install and never counts as a product result.
  - Installed source/build module trees are equal at SHA256 e8fa535e3678d3fee239735e8b5379cd9a1e7072f7291c5b1bf2e7d70d244396.
  - Rebuilt immutable image sha256:9a436646a124d4164ed560882f0ec7c3776380733065b10fcb3ca84b13cac34c binds equal source/verified SHA256 0624e00ad3d6967e33eb6b805b40f6ad1f1e84cb21bb0abde4a7166264f4f7d5. Fresh smoke returned one QUALIFIED CUDA candidate from each frozen model and left no container/GPU process.
  - Fresh EXP-031 preflight found no related process, container, GPU task, or ROS domain 181-183 owner; 24 CPUs, 25.846 GiB MemAvailable, and 14.914 GiB free GPU exceed admission.
disproven_routes:
  - A non-symlink colcon build copies modules into install and fails the source-origin contract test; p38 is retained and not reused.
open_risks:
  - No four-point execute has yet reached ATTEMPT_STARTED, so controlled fault and 20-point admission remain closed.
next_command: Execute the clean pre-registered EXP-031 two-Worker four-point batch using image sha256:9a436646a124d4164ed560882f0ec7c3776380733065b10fcb3ca84b13cac34c.
```

## EXP-001 — Task 7 fresh runtime overlay build

```yaml
experiment_id: EXP-001
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T03:54:14+08:00
  - status: RUNNING
    at: 2026-09-12T03:54:14+08:00
  - status: INVALID
    at: 2026-09-12T03:56:00+08:00
hypothesis: The Task 7 source snapshot builds the three required Linux runtime packages into the isolated worktree overlay without selecting the repository's macOS-only mujoco vendor.
host: AI-STATION-001
worktree: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1
committed_head: c4155995d1a0558f4175ace8ec3a7fc5ffd3ebcb
source_snapshot_hash_manifest: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/task7-prebuild-source-hashes.txt
source_snapshot_hash_manifest_sha256: 93ebb9fa50f250f673e379aaba382ba11d4029c70fefc554d7f917a9aa13e4ff
dockerfile_sha256: ec8566ad07627da358b311b6fe2b4f64e32800eaa6d1182a756854a05a40fb1d
command: >-
  /usr/bin/zsh -f -c 'source .superpowers/sdd/2026-09-12-so101-parallel-multipoint-validation-implementation/test-env.zsh;
  /usr/bin/python3 -m colcon build --packages-select so101_mujoco_support so101_teleop so101_demo_py
  --symlink-install > "$PARALLEL_EVIDENCE/reports/task7-colcon-build-001.log" 2>&1;
  build_exit=$?; printf "%s\n" "$build_exit" > "$PARALLEL_EVIDENCE/reports/task7-colcon-build-001.exit"; exit "$build_exit"'
expected_outputs:
  - /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install/so101_mujoco_support
  - /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install/so101_teleop
  - /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install/so101_demo_py
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/task7-colcon-build-001.log
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/task7-colcon-build-001.exit
result: so101_mujoco_support built successfully; so101_teleop failed its existing TypeScript web build; so101_demo_py was not processed; exit 2.
failure_classification: valid build failure; no runtime stack or physical action started
log_sha256: c10a19db2a734c9770232c2169569f83ef2c043f57737681892d9c820a06a136
exit_file_sha256: 53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3
blocking_detail: src/so101_teleop/web/src/components/tasks/point-cloud-viewer.tsx cannot resolve Mesh, Scene, Color, AxesHelper, Points, and Vector3 from the pinned @types/three namespace; no CMake option exists to disable the ALL web target.
retained: all listed logs and the worktree build/install overlay
archived: none
deletion_candidates: none
```

## EXP-018 — Task 13 fresh overlay and ordinary package gate

```yaml
experiment_id: EXP-018
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T15:52:01+08:00
  - status: RUNNING
    at: 2026-09-12T15:52:24+08:00
  - status: INVALID
    at: 2026-09-12T15:54:13+08:00
hypothesis: The repaired frozen web dependency tree permits a fresh three-package worktree overlay, the ordinary so101_demo_py gate passes without collecting benchmark_test, and the final combined Broker image passes both-model smoke.
host: AI-STATION-001
worktree: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1
git_head_at_plan: e4d06020598eda8f22c54b3826802df84b84291f
mode: build, ordinary package test, provenance readback, combined-image rebuild, and detector smoke only; no live ROS/MuJoCo/MoveIt Worker batch or physical execution
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1
acceptance: Fresh so101_mujoco_support/so101_teleop/so101_demo_py build succeeds; ordinary so101_demo_py test and colcon test-result both exit zero from a verified fresh NVMe tempfile root; benchmark_test is not collected; installed console/module/config resolve only through the worktree overlay and match source bytes; frozen catalog/models remain unchanged; git diff and compileall checks pass; rebuilt immutable Broker image ID is recorded and both-model smoke succeeds.
result: The fresh three-package overlay build passed in 2.83 s, closing F15. The ordinary package build also passed, but pytest collection stopped with ModuleNotFoundError for torch at test_grounding_dino_domain_retention.py:6. The frozen /usr/bin/python3 intentionally has no torch; comparable optional training tests use pytest.importorskip. colcon test exited 2 and test-result reported 1 collection error, 0 failures, and 0 skipped, so this experiment is INVALID before image qualification or any live action.
three_package_build_scratch: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/task13-three-package-build-cyd6VDm8
three_package_build_log_sha256: b9dfaeea8f9df39494046cab8932c9de84d3d680acd606a7b4607bbe2e0a72d4
three_package_build_time_sha256: c05175da0059c45791d526d80c83479fccd8633314465bdc30287319116c1abf
package_gate_scratch: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/package-gate-R81lEN3o
package_test_exit: 2
package_test_result_exit: 1
package_test_result: 1 test, 1 collection error, 0 failures, 0 skipped
package_test_time_sha256: 8a1ccbaa3566275884dc89ad1a0b36400caf79facef1de822cbfee3d933bea35
package_test_result_sha256: 548ce91423cecc08d755f3a4efab0cc577a5b56928e5677b1740a7aba64e3dd2
retained: all build, test, provenance, image, and smoke logs plus scratch trees
archived: none
deletion_candidates: fresh build/test scratch trees after readback; nothing will be deleted without explicit authorization
```

EXP-018 postmortem: the first comparison with optional SAM tests was incomplete. A full ordinary-suite probe showed the same bare interpreter also lacked MuJoCo. Historical repository gate evidence identified the established locked-ML plus ROS path order, and a direct readback confirmed that environment supplies both dependencies without changing source. The temporary test edit was reverted before any commit.

## EXP-019 — Task 13 corrected locked-dependency package gate

```yaml
experiment_id: EXP-019
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T15:57:43+08:00
  - status: RUNNING
    at: 2026-09-12T15:58:27+08:00
  - status: INVALID
    at: 2026-09-12T15:59:19+08:00
hypothesis: The exact system interpreter with the established locked ML site-packages prepended to the fresh worktree and ROS overlay passes the complete ordinary package gate without collecting benchmark_test.
host: AI-STATION-001
worktree: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1
git_head_at_plan: e4d06020598eda8f22c54b3826802df84b84291f
source_changes_since_exp_018: none
runner_python: /usr/bin/python3
locked_site_packages: /data/work/venvs/so101-grounded-sam/lib/python3.12/site-packages
dependency_readback: torch 2.13.0+cu130; mujoco 3.12.0; ROS Jazzy rclpy/launch/ament; worktree FreeJointState
mode: ordinary package build/test plus provenance, image rebuild, and detector smoke only; no benchmark_test, live stack, planning, execution, or physical action
acceptance: Build, ordinary test, and test-result exit zero from a fresh verified NVMe scratch; no benchmark_test is collected; exact test count/errors/failures and provenance are read back; all remaining Task 13 provenance/image gates pass.
result: Dependency import readback passed, but the same PYTHONPATH was injected too early into the repeated build. The venv setuptools rejected colcon's setup.py develop --uninstall option; build exited 1 after 1.26 s and no pytest or JUnit ran. This is an INVALID harness-order experiment with no product-source change.
package_gate_scratch: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/package-gate-locked-bDxIFyCi
build_log_sha256: 44aae8f9c314442a141fabe1907103447a9aa95c130c55f9f6acf33a63a8306c
build_time_sha256: 8d322a7d7259884c909450fb56e64b9ca6c5b06659c00d1da998ac0429e1df7a
python_provenance_sha256: d01157bdca910c9d9ec42b3e08eeadcc404d100e8258b77a11c272bdcb7ca25d
retained: all logs, JUnit, provenance, image, smoke, and scratch evidence
archived: none
deletion_candidates: fresh package-gate scratch after readback; nothing will be deleted without explicit authorization
```

## EXP-020 — Task 13 phase-separated package gate

```yaml
experiment_id: EXP-020
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T15:59:19+08:00
  - status: RUNNING
    at: 2026-09-12T16:00:43+08:00
  - status: INVALID
    at: 2026-09-12T16:02:29+08:00
hypothesis: Building in the bare sourced ROS/worktree environment and adding the locked ML site-packages only for the subsequent test phase passes the complete ordinary package gate.
host: AI-STATION-001
worktree: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1
git_head_at_plan: e4d06020598eda8f22c54b3826802df84b84291f
source_changes_since_exp_019: none
runner_python: /usr/bin/python3
build_environment: sourced helper and worktree overlay without locked ML PYTHONPATH
test_environment: worktree overlay plus locked ML site-packages, ROS Jazzy, and system dist-packages
mode: ordinary package build/test plus provenance, image rebuild, and detector smoke only; no benchmark_test, live stack, planning, execution, or physical action
acceptance: Build, complete ordinary test, and test-result exit zero from a fresh verified NVMe scratch; no benchmark_test is collected; exact counts and provenance are read back; all remaining Task 13 gates pass.
result: Build passed in 1.51 s and all 2754 ordinary tests collected with the correct locked dependencies. Test-result found 48 failures, all caused by the long randomized scratch prefix making test-owned AF_UNIX paths exceed the production 107-byte limit. colcon test returned 0 but authoritative test-result returned 1; no benchmark tests ran. This is an INVALID harness-path experiment, not a product relaxation case.
package_gate_scratch: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/package-gate-phased-SAFX4z0z
package_test_result: 2754 tests, 0 errors, 48 failures, 0 skipped
package_test_result_sha256: a14f2bb315b15951947d885762bc2a805bf2191314168447dc4cc84ad831a3f4
junit_sha256: 19fd2f136d1adcda0c34ba56eb1d716a201061b7fde257b40b17ca10458e7a72
retained: all logs, JUnit, provenance, image, smoke, and scratch evidence
archived: none
deletion_candidates: fresh package-gate scratch after readback; nothing will be deleted without explicit user authorization
```

## EXP-021 — Task 13 short-root ordinary package gate

```yaml
experiment_id: EXP-021
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T16:02:29+08:00
  - status: RUNNING
    at: 2026-09-12T16:03:00+08:00
  - status: INVALID
    at: 2026-09-12T16:06:32+08:00
hypothesis: The phase-separated dependency environment passes the full ordinary suite when its unique evidence-root scratch leaf preserves the frozen Unix-socket length contract.
host: AI-STATION-001
worktree: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1
git_head_at_plan: e4d06020598eda8f22c54b3826802df84b84291f
source_changes_since_exp_020: none
scratch_candidate: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p21
runner_python: /usr/bin/python3
mode: ordinary package build/test plus provenance, image rebuild, and detector smoke only; no benchmark_test, live stack, planning, execution, or physical action
acceptance: Candidate scratch did not exist before creation; tempfile resolves exactly beneath it; build, complete ordinary test, and test-result exit zero; no benchmark_test is collected; exact counts and remaining Task 13 gates pass.
result: The fresh short-root package gate passed with 2754 tests, 0 errors, 0 failures, and 0 skipped. Provenance, catalog/model hashes, git diff check, and compileall passed. The frozen-plan image command then stopped at argparse because the reviewed CLI requires an exclusive --output receipt for build; exit 2 occurred before Docker mutation. Since the aggregate Task 13 acceptance was incomplete, EXP-021 is INVALID and all successful subgate evidence remains retained.
package_gate_scratch: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p21
package_test_result: 2754 tests, 0 errors, 0 failures, 0 skipped
junit_sha256: 9d34b408f5ff961c8009f786328c80acef72b142c783ac6c352a8ecf3f3a5350
provenance_report_sha256: 6301fcf44718cc89a37e416255ad104bfd4ebc8e0dba73e1d0bd0b89d52a1503
image_build_cli_log_sha256: d2056c3493a4c589ea74b4754e89845cc25519fd64d61ced9e877bed459e4544
retained: all logs, JUnit, provenance, image, smoke, and scratch evidence
archived: none
deletion_candidates: scratch/p21 after readback; nothing will be deleted without explicit user authorization
```

## EXP-022 — Task 13 final package and immutable-image gate

```yaml
experiment_id: EXP-022
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-12T16:06:32+08:00
  - status: RUNNING
    at: 2026-09-12T16:07:03+08:00
  - status: VALID
    at: 2026-09-12T16:10:40+08:00
hypothesis: The exact EXP-021 package environment remains green and the current receipt-bearing container CLI rebuilds and smoke-tests one immutable dual-model Broker image.
host: AI-STATION-001
worktree: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1
git_head_at_plan: e4d06020598eda8f22c54b3826802df84b84291f
source_changes_since_exp_021: none
scratch_candidate: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p22
image_tag: so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1
mode: ordinary package build/test, provenance, immutable image rebuild, and offline dual-model smoke; no benchmark_test, live Worker stack, planning, execution, or physical action
acceptance: Complete ordinary gate repeats with zero errors/failures; provenance remains exact; build receipt and image inspect agree on immutable ID and current source; both frozen models execute successfully in smoke; no owned container or GPU process remains.
result: The fresh package build passed in 1.53 s and the ordinary suite passed 2754 tests with 0 errors, 0 failures, and 0 skipped in 83.18 s; benchmark_test was not collected. Worktree console/module/config/catalog provenance and frozen model hashes matched, git diff check and compileall passed. The rebuilt receipt and docker inspect agreed on immutable image sha256:3ca6f7db5303c05c6a899889d73c0cf16b1fe91c4e5d7ef2ce69af2ddbd7e5d4 with equal source/verified hashes c5fcae2e99975d37030ce1827d50367d36db404077b272687fe8f13d63a5f426. Offline smoke returned QUALIFIED with one candidate from each frozen model and left no running container or GPU compute application.
package_gate_scratch: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p22
package_test_result: 2754 tests, 0 errors, 0 failures, 0 skipped
package_test_log_sha256: 91e6f6462c2a4179af25c499b0b2120039959dd2d83df7cc5c154c46f30367d8
package_test_result_sha256: 7ac0c183cfd6ffe15685fbb74bb91b8c4360453bfee3df107c53da08957f2e2e
junit_sha256: 8dce8a96a32a470fe0cb126c2f0045cce739ead83adcc0d082f37bc269fa4c03
image_id: sha256:3ca6f7db5303c05c6a899889d73c0cf16b1fe91c4e5d7ef2ce69af2ddbd7e5d4
image_source_sha256: c5fcae2e99975d37030ce1827d50367d36db404077b272687fe8f13d63a5f426
image_build_receipt_sha256: 1cf58fe0b7a66d028761f3267bbe13f9469d0799d41c86af9abe622a17f8a000
smoke_admission_sha256: 7856e678bf1942460f9e0f277cde568b23980726e8eb23b3b0188d0b9a67b4c5
smoke_result_sha256: 8f320e079347f3cae8b78115b4952241d2013028fb1f7ba299f12e925c092bf2
smoke_models: grounded-sam QUALIFIED one candidate 199.154 ms; plastic-cup-yolo11n-seg-v1 QUALIFIED one candidate 33.217 ms
retained: all logs, JUnit, provenance, image, smoke, and scratch evidence
archived: none
deletion_candidates: scratch/p22 after readback; nothing will be deleted without explicit user authorization
```

## EXP-023 — Task 14 two-Worker four-point execute

```yaml
experiment_id: EXP-023
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T16:14:08+08:00
  - status: RUNNING
    at: 2026-09-12T16:15:53+08:00
  - status: INVALID
    at: 2026-09-12T16:16:39+08:00
prior_experiment: EXP-022
hypothesis: Two isolated headless MuJoCo Workers dynamically lease and physically pass the four preregistered representative points through one immutable external Broker while preserving all per-point numeric, visual, isolation, and cleanup gates.
prediction: Exactly four unique points reach PASSED with qualification_passed=true; no slot exceeds K=2, no point has two valid leases, both Workers use disjoint domains/sessions/roots/sockets, and every point has fresh post-reset through post-retreat evidence.
single_variable: Move from offline package/image qualification to the frozen four-point two-Worker execute selection; source, install, runtime policy, models, image ID, and catalog remain fixed.
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-022 package and immutable-image gate is VALID.
  - No relevant MuJoCo, MoveIt, controller, ROS worker, Broker, container, or GPU compute process is active; domains 181-183 have no nodes.
  - CPU 24, MemAvailable 27.965 GB, and GPU free 15.272 GiB exceed two-Worker admission thresholds.
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small did not exist before planning.
success_criteria:
  - Command exits 0 and authoritative summary reports normal POINTS_COMPLETE plus qualification_passed=true.
  - task_start, cup_test_forward_5cm, sample_05_near_center, and sample_14_far_right each have exactly one valid lease and PASSED sealed result.
  - Each Worker completes at most two points; all identity and resource isolation fields are pairwise disjoint.
  - Per-point reset, canonical joints, fresh RGB-D, POSE_ACCEPTED, MoveIt/controller, final cup support/contact/detachment, retreat, and fresh offscreen RGB evidence pass readback.
  - Cleanup is true and no owned process, container, GPU compute task, active controller goal, MoveIt attachment, or stale Worker node remains.
failure_criteria:
  - A correctly initialized counted point fails a physical or evidence gate; preserve it as a VALID failed behavior run and stop Task 15.
invalid_criteria:
  - Provenance, initial state, command, stack uniqueness, recorder/capture identity, or evidence completeness is polluted; retain evidence but do not count the behavior result.
provenance:
  source_commit: 30f18b7dc24bc6aed7e5bdfdc446e92f37bf5f5f
  source_tree: 3e0eef3773e2f2be7930614403f5fe621a2d2727
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  runtime_executable: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install/so101_demo_py/lib/so101_demo_py/so101_parallel_batch
  ros_domain_ids: [181, 182]
  gz_partition: not_applicable
  image_id: sha256:3ca6f7db5303c05c6a899889d73c0cf16b1fe91c4e5d7ef2ce69af2ddbd7e5d4
  image_source_sha256: c5fcae2e99975d37030ce1827d50367d36db404077b272687fe8f13d63a5f426
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
visual_method: Workers are headless MuJoCo with no Gazebo client or window; GUI capture is therefore not a truthful route. Apply the gui-capture freshness/identity rule and gazebo-video-debug ready-frame/timeline principles to each immutable Worker offscreen RGB sequence, using original-resolution local image inspection and numeric runtime alignment.
commands:
  - command: ros2 run so101_teleop so101_stack_inventory.py --json /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/process-inventory-before-023.json
    exit_code: 0
    environment_note: The installed tool requires Pydantic v2; its read-only invocation prepended /data/work/microduck_rl/.venv/lib/python3.12/site-packages after the bare system attempt failed at import. The resulting inventory contains no stack process, ROS node, or GUI window.
  - command: ros2 run so101_demo_py so101_parallel_batch --points src/so101_demo_py/config/mujoco/moveit_expert_validation_points_v1.yaml --point-id task_start --point-id cup_test_forward_5cm --point-id sample_05_near_center --point-id sample_14_far_right --config src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml --batch-id parallel-small-20260912-v1 --worker-count 2 --max-points-per-worker 2 --evidence-root /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small --broker-image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1 --yolo-weights /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt --yolo-weights-sha256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781 --grounded-root /data/work/so101-models/grounded-sam-v2-scipy-lock --grounded-manifest-sha256 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775 --run-mode execute
    exit_code: 1
observed:
  - The inventory command exited 0 and found no stack process, ROS node, or GUI window.
  - The execute command exited 1 in 0.37 s with PROVENANCE_SOURCE_DIRTY before creating the batch root or starting any Worker, Broker, container, ROS node, simulation, plan, or motion.
inferred:
  - The controller-owned ledger update is the sole dirty path and conflicts with strict clean-repository admission unless its pre-run state is committed first.
conclusion: INVALID pre-admission harness ordering; no product behavior was exercised.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/task14-preflight-023.txt
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/process-inventory-before-023.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/live-small-command.log; sha256 82fc295a5ca0a20eba622efdf04f8a904196dd006c6048160c6b528ecd09eb26
decision: REPEAT after a ledger-only pre-run commit
next_experiment: EXP-024 repeats the same frozen execute run from a clean ledger-precommitted HEAD
```

## EXP-024 — Task 14 clean-head two-Worker four-point execute

```yaml
experiment_id: EXP-024
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T16:17:14+08:00
  - status: RUNNING
    at: 2026-09-12T16:17:14+08:00
  - status: INVALID
    at: 2026-09-12T16:18:23+08:00
prior_experiment: EXP-023
hypothesis: Committing the ledger-only pre-run state removes EXP-023's sole provenance dirtiness and permits the otherwise identical frozen two-Worker four-point execute to exercise product behavior.
prediction: Clean-source admission succeeds; exactly four unique points reach PASSED with qualification_passed=true; no slot exceeds K=2, no point has two valid leases, and all numeric, visual, isolation, and cleanup gates pass.
single_variable: Ledger state is committed before runtime; all executable source, install bytes, selection, policy, models, image ID, N=2, K=2, batch ID, and absent batch root are unchanged from EXP-023.
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-022 is VALID and EXP-023 stopped before side effects solely because its ledger was dirty.
  - The ledger-only pre-run commit containing this RUNNING record is the runtime HEAD; executable source tree remains 3e0eef3773e2f2be7930614403f5fe621a2d2727.
  - No relevant stack/process/container/GPU task or domain 181-183 node exists, and live-small remains absent.
success_criteria:
  - Command exits 0 with normal POINTS_COMPLETE and qualification_passed=true.
  - All four selected points have exactly one PASSED sealed result; both Workers remain within K=2 with disjoint identity/resources.
  - Reset, joints, RGB-D, POSE_ACCEPTED, MoveIt/controller, final support/contact/detachment, retreat, offscreen visual, and cleanup readback all pass.
failure_criteria:
  - A correctly initialized counted point fails a physical or evidence gate; preserve as a VALID failed behavior run and stop Task 15.
invalid_criteria:
  - Admission/provenance/initial-state/command/evidence pollution prevents a trustworthy behavior result.
provenance:
  executable_source_commit: 30f18b7dc24bc6aed7e5bdfdc446e92f37bf5f5f
  executable_source_tree: 3e0eef3773e2f2be7930614403f5fe621a2d2727
  runtime_head: clean ledger-only pre-run commit containing this record
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  runtime_executable: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install/so101_demo_py/lib/so101_demo_py/so101_parallel_batch
  ros_domain_ids: [181, 182]
  gz_partition: not_applicable
  image_id: sha256:3ca6f7db5303c05c6a899889d73c0cf16b1fe91c4e5d7ef2ce69af2ddbd7e5d4
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
visual_method: Headless MuJoCo offscreen per-point RGB at original resolution, checked for freshness and aligned to sealed runtime evidence; no Gazebo window exists, so window recording/capture would be false provenance.
commands:
  - command: ros2 run so101_demo_py so101_parallel_batch with the exact EXP-023 arguments and unique reports/live-small-command-024 log/exit/time evidence
    exit_code: 1
observed:
  - The clean HEAD passed the source-dirty boundary, then the execute command exited 1 in 0.37 s with PROVENANCE_CONSOLE_MISSING before batch-root creation or process startup.
inferred:
  - The overlay locates the libexec through ament for ros2 run, while the independent verifier needs the same installed wrapper explicitly discoverable through PATH.
conclusion: INVALID pre-admission environment omission; no product behavior was exercised.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/process-inventory-before-023.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/live-small-command-024.log; sha256 99c39672bf29d69af01c4f046a0639a05b3a0be6f0bd7a83577bd768858e1b8b
decision: REPEAT with only the verified libexec PATH added
next_experiment: EXP-025 repeats the frozen execute from a clean precommitted ledger and verified libexec PATH
```

## EXP-025 — Task 14 verified-libexec two-Worker execute

```yaml
experiment_id: EXP-025
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T16:18:23+08:00
  - status: RUNNING
    at: 2026-09-12T16:18:23+08:00
  - status: INVALID
    at: 2026-09-12T16:20:05+08:00
prior_experiment: EXP-024
hypothesis: Adding only the verified worktree libexec to PATH satisfies the final provenance boundary and permits the otherwise identical four-point execute run.
prediction: Provenance and resource admission succeed; exactly four unique points reach PASSED with qualification_passed=true; N=2/K=2 isolation and all numeric, visual, and cleanup gates pass.
single_variable: PATH gains only /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install/so101_demo_py/lib/so101_demo_py; all EXP-024 executable inputs and absent batch root remain fixed.
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-022 is VALID; EXP-024 stopped before any side effect at console discovery.
  - The pre-run ledger is committed and clean, live-small is absent, inventory has no stack, and the exact PATH-resolved wrapper hash is f04ec5fff42403737d1703e8dafe01e8a7d4454963e2d547e0e937db64914c53.
success_criteria:
  - Exit 0, normal POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, per-Worker K<=2, complete evidence, and clean shutdown.
failure_criteria:
  - Trustworthy initialized product behavior fails any physical/evidence gate; stop Task 15.
invalid_criteria:
  - A provenance, command, initial-state, or evidence defect prevents trustworthy behavior counting.
provenance:
  executable_source_commit: 30f18b7dc24bc6aed7e5bdfdc446e92f37bf5f5f
  executable_source_tree: 3e0eef3773e2f2be7930614403f5fe621a2d2727
  runtime_head: clean ledger-only pre-run commit containing this record
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  runtime_executable: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install/so101_demo_py/lib/so101_demo_py/so101_parallel_batch
  ros_domain_ids: [181, 182]
  gz_partition: not_applicable
  image_id: sha256:3ca6f7db5303c05c6a899889d73c0cf16b1fe91c4e5d7ef2ce69af2ddbd7e5d4
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
visual_method: Original-resolution immutable MuJoCo offscreen RGB per point with freshness, source-stamp, and runtime-evidence alignment; no Gazebo client/window exists.
commands:
  - command: prepend verified worktree libexec to PATH, then run the exact EXP-023 ros2 execute command with reports/live-small-command-025 log/exit/time evidence
    exit_code: 1
observed:
  - Console discovery passed, then execution exited 1 in 0.38 s with PROVENANCE_MIXED_OVERLAY before batch-root creation or any process side effect.
  - Imported module resolves to src/so101_demo_py/src/cli/mujoco_parallel_batch.py; verifier expects the nonexistent src/so101_demo_py/src/so101_demo/cli/mujoco_parallel_batch.py.
inferred:
  - The helper and its fake test encode a conventional nested package path that does not match this repository's setup.py package_dir mapping.
conclusion: INVALID before product execution, but it confirms a Task 11 provenance implementation defect requiring scoped TDD repair.
repair: TDD RED pytest-UF9TFOfi failed 1/1 on the real package_dir layout; focused GREEN pytest-ETvtcUlA passed 1/1; expanded pytest-6W1zTYoH passed 64 tests. Scoped fix commit f9984f074 changes only the verifier and its direct test. Fresh package gate p31 passed 2754 tests with no errors/failures, and rebuilt image sha256:3db5046e9eba7448ab03505f5a3240df7e70c922194d07316599a20ea2261018 passed both-model smoke.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/process-inventory-before-023.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/live-small-command-025.log; sha256 30462a747fb2fcfe642a9d0b2221a85ed020724f54613610b707be92fbacf6fa
decision: REPEAT only after scoped provenance RED/GREEN, overlay/image rebuild, and clean ledger precommit
next_experiment: EXP-026 is reserved for the corrected fresh execute batch after the scoped fix
```

## EXP-026 — Task 14 corrected-provenance two-Worker execute

```yaml
experiment_id: EXP-026
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T16:24:24+08:00
  - status: RUNNING
    at: 2026-09-12T16:25:26+08:00
  - status: INVALID
    at: 2026-09-12T16:28:00+08:00
prior_experiment: EXP-025
hypothesis: The scoped real-layout provenance fix permits the frozen four-point execute to start while preserving all mixed-overlay fences and physical/evidence acceptance gates.
prediction: Clean admission succeeds; exactly four unique points reach PASSED with qualification_passed=true; both Workers remain within K=2 and all identity, numeric, visual, and cleanup gates pass.
single_variable: Verifier expected-module path matches the repository's actual package_dir; source commit, installed overlay, and image are freshly rebuilt from f9984f074, while selection, config, models, N=2, K=2, batch ID, and absent live-small root remain frozen.
lifecycle: ISOLATED_STACK
preconditions:
  - Provenance TDD RED/GREEN and expanded 64-test gate passed; full p31 package gate passed 2754 tests with no errors/failures.
  - Rebuilt immutable image sha256:3db5046e9eba7448ab03505f5a3240df7e70c922194d07316599a20ea2261018 has source/verified SHA256 6a0db750d1a4c438a74ac23acfa82358328b692d79040be3b4fbd1ef8668a7bc and passed dual-model smoke.
  - The ledger-only pre-run commit containing RUNNING state is clean; no relevant stack/container/GPU task exists and live-small is absent.
success_criteria:
  - Exit 0, normal POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, per-Worker K<=2, complete per-point evidence, and clean shutdown.
  - Reset, canonical joints, fresh RGB-D, POSE_ACCEPTED, MoveIt trajectory/controller, final cup support/contact/detachment, retreat, and original-resolution offscreen visual evidence pass readback.
failure_criteria:
  - Trustworthy initialized product behavior fails any physical/evidence gate; retain as VALID failed behavior and stop Task 15.
invalid_criteria:
  - Provenance, initial state, command, stack uniqueness, or evidence pollution prevents trustworthy behavior counting.
provenance:
  executable_source_commit: f9984f07413c561f3bdedd8288df751b96d39565
  executable_source_tree: 53cf6d5e8b96dec73bf677d536c5da3fbe9d4f81
  runtime_head: clean ledger-only pre-run commit containing this record
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  runtime_executable: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install/so101_demo_py/lib/so101_demo_py/so101_parallel_batch
  ros_domain_ids: [181, 182]
  gz_partition: not_applicable
  image_id: sha256:3db5046e9eba7448ab03505f5a3240df7e70c922194d07316599a20ea2261018
  image_source_sha256: 6a0db750d1a4c438a74ac23acfa82358328b692d79040be3b4fbd1ef8668a7bc
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
visual_method: Original-resolution immutable MuJoCo offscreen RGB per point, inspected fresh and aligned to sealed runtime evidence; no Gazebo client/window is part of this headless backend.
commands:
  - command: inventory the pre-run stack to reports/process-inventory-before-026.json
    exit_code: 0
  - command: prepend the verified worktree libexec to PATH, then run the frozen four-point ros2 execute command with reports/live-small-command-026 log/exit/time evidence
    exit_code: 1
observed:
  - All module, console-wrapper, and egg-link identity checks matched the exact worktree, but the execute command exited 1 in 0.37 s with PROVENANCE_INSTALLED_OVERLAY.
  - The editable build symlink resolves to the real package_dir source root src/so101_demo_py/src; the verifier and its synthetic test incorrectly require the nonexistent nested src/so101_demo_py/src/so101_demo directory.
  - The batch root remained absent and no Worker, Broker, container, ROS stack, simulation, plan, motion, or GPU compute task was started.
inferred:
  - The first scoped path fix exposed the adjacent installed-tree check carrying the same conventional-layout assumption; this is a pre-admission Task 11 verifier defect, not product behavior.
conclusion: INVALID before resource or process side effects; no physical behavior can be counted.
repair: >-
  The real package_dir fixture produced RED in pytest-S0EQDPY8, and the one-line source-root
  correction produced focused GREEN plus 60/60 CLI tests in pytest-5yd1q2CH. Scoped commit
  d7919dca9 changes only the installed-tree verifier and its direct test. p34 then rebuilt the
  package and passed all 2754 ordinary tests with zero errors/failures/skips; benchmark_test was
  not collected. A preceding p33 full run had one transient CHILD_IDENTITY failure in a real
  short-lived process test, which passed immediately in isolated pytest-6lpHcTmc; the complete p34
  rerun was required and passed. Rebuilt immutable image sha256:5922d725fac1d64267ccfcdbbc45887775d87678da0397d3e6594e3469eefc9a
  has equal source/verified hash 1d06060e76044f2be69b13eaaaf68c52ac582cc2351f35d201f404148172e79d
  and both frozen models returned QUALIFIED in fresh task14-f32-smoke evidence.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p31
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/final-broker-image-build-f31.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/task14-f31-smoke
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/process-inventory-before-026.json; sha256 cfdbfdc8b7abc2bfde2ca7c07ddd67df79fd43ab08611d6a37969d7871a4707d
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/live-small-command-026.log; sha256 13e0220e61ee07524dc6a94108fca6961e50866c4459ed6b9573e0887b772524
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/live-small-command-026.time; sha256 1553b91e8c61e58b23d277e175d2af9e0c42615e565d68ce5f5425987269d286
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/live-small-command-026.exit; sha256 4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865
decision: REPEAT only after the F32 installed-tree RED/GREEN, full package gate, image rebuild, dual-model smoke, and clean ledger precommit
next_experiment: EXP-027 is reserved for the corrected fresh execute batch after the scoped fix
```

## EXP-027 — Task 14 installed-tree-corrected two-Worker execute

```yaml
experiment_id: EXP-027
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T16:37:19+08:00
  - status: RUNNING
    at: 2026-09-12T16:37:19+08:00
  - status: INVALID
    at: 2026-09-12T16:38:44+08:00
prior_experiment: EXP-026
hypothesis: The source-module and installed-editable-tree checks now bind the repository's real package_dir layout, permitting the frozen four-point execute while retaining every provenance, isolation, physical, visual, and cleanup fence.
prediction: Clean admission succeeds; exactly four unique points reach PASSED with qualification_passed=true; both Workers remain within K=2 and all identity, numeric, visual, and cleanup gates pass.
single_variable: The installed-tree expected source root changes from the nonexistent nested directory to the actual package_dir root; selection, config, models, N=2, K=2, batch ID, and still-absent live-small root remain frozen.
lifecycle: ISOLATED_STACK
preconditions:
  - F32 TDD and the complete p34 ordinary gate passed; installed provenance readback binds exact source and build trees to SHA256 757f3e9017d978ee5457f39d1528d9e4ba7b5a737510b49cea5961d1b43eae4e.
  - Rebuilt immutable image sha256:5922d725fac1d64267ccfcdbbc45887775d87678da0397d3e6594e3469eefc9a passed fresh dual-model smoke with equal source/verified SHA256 1d06060e76044f2be69b13eaaaf68c52ac582cc2351f35d201f404148172e79d.
  - Fresh inventory found no stack process, ROS node, or GUI window; no related container/GPU task exists; live-small remains absent.
success_criteria:
  - Exit 0, normal POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, per-Worker K<=2, complete per-point evidence, and clean shutdown.
  - Reset, canonical joints, fresh RGB-D, POSE_ACCEPTED, MoveIt trajectory/controller, final cup support/contact/detachment, retreat, and original-resolution offscreen visual evidence pass readback.
failure_criteria:
  - Trustworthy initialized product behavior fails any physical/evidence gate; retain as VALID failed behavior and stop Task 15.
invalid_criteria:
  - Provenance, initial state, command, stack uniqueness, or evidence pollution prevents trustworthy behavior counting.
provenance:
  executable_source_commit: d7919dca912f1ec3f97009e697f3724fb9610f11
  executable_source_tree: 757f3e9017d978ee5457f39d1528d9e4ba7b5a737510b49cea5961d1b43eae4e
  runtime_head: clean ledger-only pre-run commit containing this record
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  runtime_executable: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install/so101_demo_py/lib/so101_demo_py/so101_parallel_batch
  ros_domain_ids: [181, 182]
  gz_partition: not_applicable
  image_id: sha256:5922d725fac1d64267ccfcdbbc45887775d87678da0397d3e6594e3469eefc9a
  image_source_sha256: 1d06060e76044f2be69b13eaaaf68c52ac582cc2351f35d201f404148172e79d
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
visual_method: Original-resolution immutable MuJoCo offscreen RGB per point, inspected fresh and aligned to sealed runtime evidence; no Gazebo client/window is part of this headless backend.
commands:
  - command: inventory the pre-run stack to reports/process-inventory-before-027.json
    exit_code: 0
  - command: prepend the verified worktree libexec to PATH, then run the frozen four-point ros2 execute command with reports/live-small-command-027 log/exit/time evidence
    exit_code: 1
observed:
  - Both source and installed-tree provenance checks passed, then resource admission exited 1 in 0.66 s with ROS_DOMAIN_IN_USE for 181 and 182 before batch-root creation.
  - Readback found controller-created ros2cli discovery daemons for domains 181, 182, and 183, all launched at 16:13 during Task 14 preflight; there were no domain claim locks, Worker/Broker processes, containers, or GPU compute applications.
  - `ROS_DOMAIN_ID=<domain> ros2 daemon stop` cleanly stopped all three exact task-owned daemons; daemon status and `ros2 node list --no-daemon` then found no nodes, and the production same-UID probe reported all three domains unused.
inferred:
  - The earlier domain inventory polluted the live namespace by leaving discovery daemons behind; this is a pre-admission harness cleanup defect, not product behavior or an external domain owner.
conclusion: INVALID before directory, process, simulation, plan, or motion side effects; no physical behavior can be counted.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p34
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/installed-provenance-f32.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/final-broker-image-build-f32.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/task14-f32-smoke
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/process-inventory-before-027.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/live-small-command-027.log; sha256 b5493b490ba65da85229951e9839a4780b92fc220aabc3a208cd0b75d28d5753
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/live-small-command-027.time; sha256 ca2e23d01722694d675d0db5ca7bd2032015ff3b253f90d175d1e3684e364123
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/live-small-command-027.exit; sha256 4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/domain-preflight-before-028b.json; sha256 b9558cb18d3e833693da291aa92a305aa32bded6ee05650b4d9f6999d9311d4b
decision: REPEAT after stopping only the exact controller-created daemons and proving all three domains unused with the production probe
next_experiment: EXP-028 repeats the otherwise identical frozen execute from clean domain state
```

## EXP-028 — Task 14 clean-domain two-Worker execute

```yaml
experiment_id: EXP-028
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T16:39:46+08:00
  - status: RUNNING
    at: 2026-09-12T16:39:46+08:00
  - status: INVALID
    at: 2026-09-12T16:45:03+08:00
prior_experiment: EXP-027
hypothesis: Removing only task-owned ROS discovery daemons permits the fully provenance-qualified four-point execute to enter resource allocation and run with isolated domains 181 and 182.
prediction: Clean admission succeeds; exactly four unique points reach PASSED with qualification_passed=true; both Workers remain within K=2 and all identity, numeric, visual, and cleanup gates pass.
single_variable: Domains 181-183 no longer contain controller-created discovery daemons; source, install, image, selection, config, models, N=2, K=2, batch ID, and absent live-small root remain identical to EXP-027.
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-027 passed provenance and stopped before batch-root or process side effects only because task-owned ROS discovery daemons occupied the domain pool.
  - All three daemon APIs report stopped; no-daemon node discovery is empty; the production same-UID probe reports domains 181-183 unused with 24 CPUs, 26.022 GiB MemAvailable, and 14.914 GiB GPU free.
  - The ledger-only RUNNING record is committed and clean; live-small remains absent and no related container or GPU task exists.
success_criteria:
  - Exit 0, normal POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, per-Worker K<=2, complete per-point evidence, and clean shutdown.
  - Reset, canonical joints, fresh RGB-D, POSE_ACCEPTED, MoveIt trajectory/controller, final cup support/contact/detachment, retreat, and original-resolution offscreen visual evidence pass readback.
failure_criteria:
  - Trustworthy initialized product behavior fails any physical/evidence gate; retain as VALID failed behavior and stop Task 15.
invalid_criteria:
  - Provenance, initial state, command, stack uniqueness, or evidence pollution prevents trustworthy behavior counting.
provenance:
  executable_source_commit: d7919dca912f1ec3f97009e697f3724fb9610f11
  executable_source_tree: 757f3e9017d978ee5457f39d1528d9e4ba7b5a737510b49cea5961d1b43eae4e
  runtime_head: clean ledger-only pre-run commit containing this record
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  runtime_executable: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install/so101_demo_py/lib/so101_demo_py/so101_parallel_batch
  ros_domain_ids: [181, 182]
  gz_partition: not_applicable
  image_id: sha256:5922d725fac1d64267ccfcdbbc45887775d87678da0397d3e6594e3469eefc9a
  image_source_sha256: 1d06060e76044f2be69b13eaaaf68c52ac582cc2351f35d201f404148172e79d
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
visual_method: Original-resolution immutable MuJoCo offscreen RGB per point, inspected fresh and aligned to sealed runtime evidence; no Gazebo client/window is part of this headless backend.
commands:
  - command: stop exact task-owned domain 181-183 ROS discovery daemons, verify no-daemon node lists, and run production same-UID domain/resource probe to reports/domain-preflight-before-028b.json
    exit_code: 0
  - command: prepend the verified worktree libexec to PATH, then run the frozen four-point ros2 execute command with reports/live-small-command-028 log/exit/time evidence
    exit_code: 1
observed:
  - Provenance and two-Worker resource allocation succeeded. The immutable Broker container started, loaded both models, and published a valid ready receipt plus socket after about 7.69 seconds.
  - The coordinator used the 5-second heartbeat-loss interval as the initial cold-start deadline, emitted BROKER_READY_TIMEOUT, and never launched either Worker or granted any point lease; all four points remained UNRUN with zero attempts.
  - Host-process cleanup removed the attached docker client but left its exact container and 2636 MiB Broker GPU process running while aggregate_results.json incorrectly recorded batch_cleanup_complete=true.
  - Inspect readback bound orphan container 6679c21fea256732ab2f821733b7d5aeb7e3b224ecef78bffa12544af2d44977 to immutable image sha256:5922d725..., the exact live-small /runtime and /inputs mounts, and this start time. `docker stop --time 10` stopped that exact task-owned container; `--rm` removed it, and final process/container/GPU/domain readback is empty.
inferred:
  - Initial cold start and steady-state heartbeat loss are distinct frozen budgets. The current lifecycle also supervises only the attached Docker client PID, not the actual container identity, so process-group absence alone cannot prove cleanup.
conclusion: INVALID infrastructure bootstrap with zero counted point attempts; it exposed two concrete Broker lifecycle defects requiring F34 TDD repair before another execute run.
repair: >-
  Valid behavioral RED pytest-md7VkUVA proved the 5-second/90-second budget mismatch, absent
  container lifecycle injection, and missing cidfile/labels. Focused GREEN pytest-57Zjafzv passed
  4 tests, and expanded pytest-wlodUMVR passed 93 CLI/container/fault tests. Commit 53592aa0f adds
  a private generation-specific cidfile, exact image/label/mount inspect before Docker stop, cleanup
  truth binding, recovery retirement, and the frozen 90-second initial Broker budget. p35 rebuilt the
  package and passed 2756 ordinary tests with zero errors/failures/skips; benchmark_test was not
  collected. Rebuilt immutable image sha256:a340599a2f78b3f47424a151cc69ad61be869c0a2336a2933891ef4ac8a5631d
  has equal source/verified SHA256 fcc27fdad80ef6f894f381f5cf07efc4dd62cfecc1368f4e0974b71e655df679
  and fresh task14-f34-smoke qualified both models, left a private 0600 cidfile, and left no container
  or GPU process.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/domain-preflight-before-028.json (empty rejected diagnostic from an incorrect probe class name; retained, not authoritative)
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/domain-preflight-before-028b.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small; batch manifest sha256 07958e981e5b46e34ab46a1d598a74c47a85904e0829d0ec49319ce60bae3b9e; resource manifest sha256 3ebf24bd0c652b0db2bb3f6f68923f4d9da7230d463514a1039b356329582c4a
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small/ipc/broker/ready.json; sha256 e5b20960c303df0c6861bf7e9086d900f672868497f612f106b05243e9108536
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small/coordinator/aggregate_results.json; sha256 d5cc1e18292aad61b40089142a6836011b75ac3fa3a2a42a866cdc6ae7d7365d
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/live-small-command-028.log; sha256 7f1c70a59275f6994e8f298eb97efda2501867c05c0d457159f951ca0be7b2c4
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/live-small-command-028.time; sha256 edf8df73142e64a16fa41df1f8c766ca0bef454ebdb00b1bc3d9fc7c311a25fa
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/orphan-container-028-inspect.json; sha256 1e6ac7fa81a620107706d77f881263cac1830cf0e85a496eb91917ca624cadb2
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/orphan-container-028-stop.txt; sha256 84a5b7d46a7488cabb7ca7c24d31f9d4570a6251a7a3fc96f10213ec0afb731e
retained: complete live-small batch tree, outer reports, orphan ownership/cleanup readback, and all earlier package/image/smoke evidence
archived: none
deletion_candidates: empty rejected domain-preflight-before-028.json and scratch p32/p33/p34 plus direct pytest scratch; nothing will be deleted without explicit user authorization
decision: REPEAT only after F34 RED/GREEN, full ordinary gate, image rebuild, dual-model smoke, and a fresh immutable batch root
next_experiment: EXP-029 is reserved for the Broker-lifecycle-corrected execute run
```

## EXP-029 — Task 14 lifecycle-corrected two-Worker execute

```yaml
experiment_id: EXP-029
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T16:53:28+08:00
  - status: RUNNING
    at: 2026-09-12T16:53:28+08:00
  - status: INVALID
    at: 2026-09-12T16:59:33+08:00
prior_experiment: EXP-028
hypothesis: The verified 90-second startup budget and exact Docker-container cleanup identity permit the four-point execute to run without either premature cold-start timeout or detached Broker residue.
prediction: Clean admission succeeds; exactly four unique points reach PASSED with qualification_passed=true; both Workers remain within K=2 and all identity, numeric, visual, and cleanup gates pass.
single_variable: F34 corrects Broker startup/cleanup lifecycle; a fresh immutable batch ID/root is required because EXP-028 evidence is retained, while source, install, image, selection, config, models, N=2, and K=2 remain fixed.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f34
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f34
preconditions:
  - F34 RED/GREEN, expanded 93-test gate, and complete p35 ordinary gate passed; installed source/build trees bind to SHA256 4c46529f9a60c7cec3bae6df42e47cb54c38268b0859f1facd1cb9b8348df203.
  - Immutable image sha256:a340599a2f78b3f47424a151cc69ad61be869c0a2336a2933891ef4ac8a5631d passed fresh dual-model smoke with equal source/verified SHA256 fcc27fdad80ef6f894f381f5cf07efc4dd62cfecc1368f4e0974b71e655df679 and private cidfile evidence.
  - Fresh inventory and production probe found no stack process, ROS node, related container/GPU task, or domain 181-183 owner; 24 CPUs, 25.871 GiB MemAvailable, and 14.914 GiB GPU free exceed admission; live-small-f34 is absent.
success_criteria:
  - Exit 0, normal POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, per-Worker K<=2, complete per-point evidence, and clean shutdown.
  - Reset, canonical joints, fresh RGB-D, POSE_ACCEPTED, MoveIt trajectory/controller, final cup support/contact/detachment, retreat, and original-resolution offscreen visual evidence pass readback.
  - Exact labeled Broker cid is absent from Docker after shutdown and aggregate cleanup is true only with no process/container/GPU residue.
failure_criteria:
  - Trustworthy initialized product behavior fails any physical/evidence gate; retain as VALID failed behavior and stop Task 15.
invalid_criteria:
  - Provenance, initial state, command, stack uniqueness, or evidence pollution prevents trustworthy behavior counting.
provenance:
  executable_source_commit: 53592aa0f8bb8866db581572568f2f4179b1d826
  executable_source_tree: 4c46529f9a60c7cec3bae6df42e47cb54c38268b0859f1facd1cb9b8348df203
  runtime_head: clean ledger-only pre-run commit containing this record
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  runtime_executable: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install/so101_demo_py/lib/so101_demo_py/so101_parallel_batch
  ros_domain_ids: [181, 182]
  gz_partition: not_applicable
  image_id: sha256:a340599a2f78b3f47424a151cc69ad61be869c0a2336a2933891ef4ac8a5631d
  image_source_sha256: fcc27fdad80ef6f894f381f5cf07efc4dd62cfecc1368f4e0974b71e655df679
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
visual_method: Original-resolution immutable MuJoCo offscreen RGB per point, inspected fresh and aligned to sealed runtime evidence; no Gazebo client/window is part of this headless backend.
commands:
  - command: fresh stack inventory and production domain/resource probe to reports/process-inventory-before-029.json and reports/domain-preflight-before-029.json
    exit_code: 0
  - command: prepend verified worktree libexec, then run the frozen four-point ros2 execute with the fresh EXP-029 batch/root and reports/live-small-command-029 log/exit/time evidence
    exit_code: 1
observed:
  - Admission and immutable Broker startup passed. Both isolated headless MuJoCo/MoveIt stacks reached READY; worker-01 leased task_start and worker-02 leased cup_test_forward_5cm, so no point had more than one lease.
  - Both Workers remained in INITIALIZING. The journal contains no ATTEMPT_STARTED or terminal point event and aggregate projection leaves all four points UNRUN; therefore zero point outcomes are countable.
  - worker-01 reset task_start successfully, then its initial boundary failed and its owned launch tree shut down. The current Worker result collapses the caught exception to INITIAL_GATE_FAILED and writes no diagnostic, so the exact rejected sub-gate is not recoverable from immutable evidence. A MoveIt diagnostic reported that attached body plastic_cup was absent during canonical scene restoration, but that log alone does not prove it was the exception source.
  - While observing the exiting Worker, ProcessSupervisor saw poll()==None and then an absent /proc identity, raised OWNED_PROCESS_ABSENT, and replaced the original child exit with a controller traceback. The final controller aggregate has terminal_reason SUPERVISOR_SHUTDOWN and batch_cleanup_complete=false.
  - Finally cleanup emptied the exact owned-process manifests, removed the exact labeled Broker container/cid, released domains 181/182, and left no NVIDIA compute application. A post-run no-daemon probe found domains 181-183 empty. The task-created MuJoCo warning log was retained under reports instead of being discarded.
inferred:
  - The live stack progressed past every EXP-023 through EXP-028 bootstrap defect, but the first point authorization boundary was never reached. This is an infrastructure/observability failure before trustworthy behavior counting, not a physical point failure.
  - The supervisor failure is a deterministic exit-observation race: an absent identity after a nonterminal poll must be re-polled before classifying it as disappearance, without weakening PID-reuse fencing.
conclusion: INVALID; zero countable attempts. Repair the Worker boundary diagnostic and supervisor exit race under F35, then repeat the unchanged four-point execute from a fresh clean commit, batch ID, and evidence root before any fault or 20-point run.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p35
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/installed-provenance-f34.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/final-broker-image-build-f34.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/task14-f34-smoke
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/process-inventory-before-029.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/domain-preflight-before-029.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/live-small-command-029.log
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f34/coordinator/events/segment-00000000000000000001.journal
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f34/coordinator/aggregate_results.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/post-029-cleanup-audit.log
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/MUJOCO_LOG-EXP029.txt
hashes:
  live_command_log_sha256: d9cb351be4f5e61dec7cb8d2248276575e0d6f126d8fa4b2172e3a6c3b025354
  journal_sha256: d6d1c7f8cd6c18ec2436ab8aaf77b844372a7600894ad2c8d35742eb704766d9
  coordinator_aggregate_sha256: 05a5b26b78c26e6f380b6e827945b145b21356fab7ad7908c24f9b4f65bd4fe8
  final_owned_manifest_sha256: 84ddaa068e4bc361545ff1eae55756858d69626df2cf899f2404922e9f0c3d1c
  cleanup_audit_sha256: 8b6304d397d38186795b4fe1fedecf7d9b7bb5aaf9cade6a70271513ac85e9f8
  mujoco_warning_log_sha256: 03a7c77559e983df564943604fe6a2035756e1accbf34193ecfb401b7f969fc6
retained: complete live-small-f34 tree, command/preflight/cleanup reports, journal/projections, ROS logs, container cidfile, and relocated MuJoCo warning log
archived: none
deletion_candidates: scratch p32/p33/p34/p35 and prior direct-pytest scratch remain candidates; nothing was deleted
decision: REPEAT after F35 RED/GREEN, ordinary package gate, installed provenance, image rebuild, and dual-model smoke
next_experiment: EXP-030 is reserved for the fresh F35-corrected execute repeat; controlled plan-only fault remains blocked until execute acceptance
```

## EXP-030 — Task 14 diagnostic-preserving two-Worker execute

```yaml
experiment_id: EXP-030
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T17:12:52+08:00
  - status: RUNNING
    at: 2026-09-12T17:12:52+08:00
  - status: INVALID
    at: 2026-09-12T17:19:10+08:00
prior_experiment: EXP-029
hypothesis: F35 preserves the true initial-boundary outcome and closes the process-exit observation race, allowing the otherwise unchanged four-point execute either to reach authorization or to fail with an exact Worker-local diagnostic and normal cleanup.
prediction: Clean admission succeeds; exactly four unique points reach PASSED with qualification_passed=true; both Workers remain within K=2 and all identity, numeric, visual, and cleanup gates pass. If an initial boundary still rejects, worker-run-results.json identifies it without a controller traceback.
single_variable: F35 changes only Worker initial-boundary diagnostics and the nonterminal-poll/absent-identity exit race. Selection, configuration, models, N=2, K=2, and physical criteria remain frozen; source/install/image and batch/root identities advance because code changed and prior evidence is immutable.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f35
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f35
preconditions:
  - F35 RED/GREEN and expanded 165-test gate passed; p37 complete ordinary gate passed 2762 tests with no error/failure/skip and no benchmark collection.
  - Installed source/build module trees both hash SHA256 4bb127e71b57f7e4d35889d9d9b763511a039c7d16af123ea397b9ae831c7016.
  - Immutable image sha256:d549146f76df4c8e4d747fa2c6c3d8ffb11302ce2f3d43d2a1bac98efc74153c binds equal source/verified SHA256 49b7d63b1bb3ef048540571964551edfa912429dea1f07f858bc59a8d7cb2acf and passed fresh dual-model smoke2.
  - Fresh inventory and production probe found no related stack process, container, GPU task, or domain 181-183 owner; live-small-f35 is absent.
success_criteria:
  - Exit 0, normal POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, per-Worker K<=2, complete per-point evidence, and clean shutdown.
  - Reset, canonical joints, fresh RGB-D, POSE_ACCEPTED, MoveIt trajectory/controller, final cup support/contact/detachment, retreat, and original-resolution offscreen visual evidence pass readback.
  - Exact labeled Broker cid is absent after shutdown and aggregate cleanup is true only with no process/container/GPU residue.
failure_criteria:
  - Trustworthy initialized product behavior fails a physical/evidence gate; retain as VALID failed behavior and stop Task 15.
invalid_criteria:
  - Provenance, initial state, command, stack uniqueness, evidence pollution, or an initial boundary failure before ATTEMPT_STARTED prevents trustworthy behavior counting.
provenance:
  executable_source_commit: 52bf3ef7dee36db9c35df9eec1153df05b3b686b
  executable_source_tree: 49b7d63b1bb3ef048540571964551edfa912429dea1f07f858bc59a8d7cb2acf
  runtime_head: clean ledger-only pre-run commit containing this record
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  runtime_executable: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install/so101_demo_py/lib/so101_demo_py/so101_parallel_batch
  ros_domain_ids: [181, 182]
  gz_partition: not_applicable
  image_id: sha256:d549146f76df4c8e4d747fa2c6c3d8ffb11302ce2f3d43d2a1bac98efc74153c
  image_source_sha256: 49b7d63b1bb3ef048540571964551edfa912429dea1f07f858bc59a8d7cb2acf
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
visual_method: Original-resolution immutable MuJoCo offscreen RGB per point, inspected fresh and aligned to sealed runtime evidence; no Gazebo client/window is part of this headless backend.
commands:
  - command: fresh stack inventory and production domain/resource probe to reports/process-inventory-before-030.json and reports/domain-preflight-before-030.json
    exit_code: 0
  - command: prepend verified worktree libexec, then run the frozen four-point ros2 execute with fresh EXP-030 batch/root and reports/live-small-command-030 log/exit/time evidence
    exit_code: 1
observed:
  - Admission and immutable Broker startup passed. Both isolated stacks reached READY; worker-01 leased task_start and worker-02 leased cup_test_forward_5cm, with no duplicate lease and no ATTEMPT_STARTED event.
  - Both exact Worker result files retained failure_boundary=reset_point, failure_type=RuntimeError, and failure_message="fresh paused atomic MuJoCo evidence unavailable". All four points remain UNRUN and zero outcomes are countable.
  - Source inspection confirms the reset transaction leaves physics paused, then reset_point creates a new sensor-data/volatile observer and makes only one pause snapshot request. The publisher is likewise volatile and snapshot publication is one-shot; a matched subscriber can miss that frame and has no retained sample to read.
  - The authenticated stop request and main Worker finally block concurrently called shutdown_owned. Both publications used the same PID-derived temporary manifest name, producing FileExistsError. During the resulting exit window, the supervisor's immediate second poll still returned nonterminal after the exact /proc identity disappeared and raised OWNED_PROCESS_ABSENT.
  - Final external readback found empty coordinator and Worker ownership manifests, no temporary manifest, no exact Broker container, no GPU compute application, and no node in domains 181-183. The task-created MuJoCo warning file was retained as reports/MUJOCO_LOG-EXP030.txt.
inferred:
  - This is an initialization/evidence-delivery and concurrent-cleanup defect before physical authorization, not a trustworthy point outcome. The identical independent Worker failures and publication QoS/service behavior explain the common reset watermark failure.
  - Serializing Worker cleanup is required in addition to collision-free temporary names, because concurrent snapshots could otherwise replace a newer empty manifest with stale ownership. A bounded supervisor yield remains fail-closed but allows waitpid state to catch up after /proc disappearance.
conclusion: INVALID; zero countable attempts. Apply F36 with RED/GREEN evidence, complete ordinary package gate, installed provenance, rebuilt immutable image, fresh dual-model smoke, and then repeat the unchanged four-point execute under EXP-031.
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p37
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/installed-provenance-f35.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/final-broker-image-build-f35.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/task14-f35-smoke2
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/process-inventory-before-030.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/domain-preflight-before-030.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/live-small-command-030.log
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f35/coordinator/events/segment-00000000000000000001.journal
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f35/coordinator/aggregate_results.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f35/workers/worker-01/worker-run-results.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f35/workers/worker-02/worker-run-results.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/post-030-cleanup-audit.log
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/MUJOCO_LOG-EXP030.txt
hashes:
  live_command_log_sha256: 225fedc66549f129c90b8b8881ed87cbac113f2bbafc92fbb3eecd4ec5310c15
  journal_sha256: 3fce7c4f870a4c0f351781269a8d51300adf46bf4d8223ee90b807cd78c6ac84
  coordinator_aggregate_sha256: a38d9911655254fdbabd21aa20d155ea6af12e410b2c6cac32174811ca8b4947
  worker_01_result_sha256: c4d5bb7624b9a6e1748779c96a2c55d4bf80f755bce562da1ad2f2e7406684ee
  worker_02_result_sha256: e17a02f779c0133d7b833f4d16af17eb34dc1945c423563a490945836ba0de77
  cleanup_audit_sha256: 4ddb6bd1afe2595d2b9a3e40e4a58d5466f372372909c0c2c6cff651aa151a5e
  mujoco_warning_log_sha256: 7c2dc647f117c4e39a125bfd2c9a47993d8a50a173bd91282da28f0958811a38
retained: complete live-small-f35 tree, command/preflight/cleanup reports, journal/projections, Worker diagnostics, ROS logs, container cidfile, and relocated MuJoCo warning log
archived: none
deletion_candidates: scratch p32 through p37, prior direct-pytest scratch, and the failed f35 smoke report-only attempt remain candidates; nothing was deleted
decision: REPEAT after F36 RED/GREEN, ordinary package gate, installed provenance, image rebuild, and dual-model smoke
next_experiment: EXP-031 is reserved for the F36-corrected execute repeat; controlled plan-only fault advances to EXP-032 and remains blocked until execute acceptance
```

## EXP-031 — Task 14 paused-evidence and cleanup-corrected two-Worker execute

```yaml
experiment_id: EXP-031
status: RUNNING
status_history:
  - status: PLANNED
    at: 2026-09-12T17:31:22+08:00
  - status: RUNNING
    at: 2026-09-12T17:31:22+08:00
prior_experiment: EXP-030
hypothesis: F36 permits each new volatile observer to obtain the already-authorized paused snapshot and serializes cleanup, so the unchanged four-point execute reaches durable authorization without replacing child outcomes with cleanup races.
prediction: Clean admission succeeds; exactly four unique points reach PASSED with qualification_passed=true; both Workers remain within K=2 and all identity, numeric, visual, and cleanup gates pass.
single_variable: F36 changes paused-snapshot retry, Worker-owned cleanup serialization, and bounded exact-child exit observation only. Selection, configuration, models, N=2, K=2, and physical criteria remain frozen; source/install/image and batch/root identities advance because code changed and prior evidence is immutable.
lifecycle: ISOLATED_STACK
batch_id: parallel-small-20260912-v1-f36
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/live-small-f36
preconditions:
  - F36 formal RED, focused/adjacent/expanded GREEN, and p39 complete ordinary gate passed 2765 tests with no error/failure/skip and no benchmark collection.
  - Installed source/build module trees both hash SHA256 e8fa535e3678d3fee239735e8b5379cd9a1e7072f7291c5b1bf2e7d70d244396.
  - Immutable image sha256:9a436646a124d4164ed560882f0ec7c3776380733065b10fcb3ca84b13cac34c binds equal source/verified SHA256 0624e00ad3d6967e33eb6b805b40f6ad1f1e84cb21bb0abde4a7166264f4f7d5 and passed fresh dual-model smoke.
  - Fresh inventory and production probe found no related stack process, container, GPU task, or domain 181-183 owner; live-small-f36 is absent.
success_criteria:
  - Exit 0, normal POINTS_COMPLETE, qualification_passed=true, four unique PASSED points, per-Worker K<=2, complete per-point evidence, and clean shutdown.
  - Reset, canonical joints, fresh RGB-D, POSE_ACCEPTED, MoveIt trajectory/controller, final cup support/contact/detachment, retreat, and original-resolution offscreen visual evidence pass readback.
  - Exact labeled Broker cid is absent after shutdown and aggregate cleanup is true only with no process/container/GPU residue.
failure_criteria:
  - Trustworthy initialized product behavior fails a physical/evidence gate; retain as VALID failed behavior and stop Task 15.
invalid_criteria:
  - Provenance, initial state, command, stack uniqueness, evidence pollution, or an initial boundary failure before ATTEMPT_STARTED prevents trustworthy behavior counting.
provenance:
  executable_source_commit: e94143e015370cfc2f53c70ec552bbede4fbf825
  executable_source_tree: 0624e00ad3d6967e33eb6b805b40f6ad1f1e84cb21bb0abde4a7166264f4f7d5
  runtime_head: clean ledger-only pre-run commit containing this record
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install
  runtime_executable: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install/so101_demo_py/lib/so101_demo_py/so101_parallel_batch
  ros_domain_ids: [181, 182]
  gz_partition: not_applicable
  image_id: sha256:9a436646a124d4164ed560882f0ec7c3776380733065b10fcb3ca84b13cac34c
  image_source_sha256: 0624e00ad3d6967e33eb6b805b40f6ad1f1e84cb21bb0abde4a7166264f4f7d5
  config_sha256: 7baaac4e4113427a262bfef4a081ceb0351920b386d3daff2042338764177478
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  selection_sha256: a474137a29b5044ba0045628f090b0ff38b07058d2efbf1e2500f32393370ce8
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
visual_method: Original-resolution immutable MuJoCo offscreen RGB per point, inspected fresh and aligned to sealed runtime evidence; no Gazebo client/window is part of this headless backend.
commands:
  - command: fresh stack inventory and production domain/resource probe to reports/process-inventory-before-031.json and reports/domain-preflight-before-031.json
    exit_code: 0
  - command: prepend verified worktree libexec, then run the frozen four-point ros2 execute with fresh EXP-031 batch/root and reports/live-small-command-031 log/exit/time evidence
    exit_code: PENDING
observed:
  - PENDING
inferred:
  - PENDING
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/scratch/p39
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/installed-provenance-f36.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/final-broker-image-build-f36.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/task14-f36-smoke
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/process-inventory-before-031.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/domain-preflight-before-031.json
decision: PENDING
next_experiment: EXP-032 controlled plan-only fault only after this execute run is accepted
```

## EXP-002 — Task 7 isolated detector package build

```yaml
experiment_id: EXP-002
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-12T03:57:08+08:00
  - status: RUNNING
    at: 2026-09-12T03:57:08+08:00
  - status: VALID
    at: 2026-09-12T03:59:10+08:00
hypothesis: The Task 7 detector package builds independently from the clean Jazzy underlay, allowing isolated container qualification without claiming the blocked Worker/live overlay gate.
host: AI-STATION-001
worktree: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1
committed_head: c4155995d1a0558f4175ace8ec3a7fc5ffd3ebcb
source_snapshot_hash_manifest: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/task7-prebuild-source-hashes-002.txt
source_snapshot_hash_manifest_sha256: 864fb13057c8bde020ec4a8512a694d1c41edbc9657b57a0dd5ea2dc8b27d8d1
underlay: /opt/ros/jazzy only; intentionally does not source the partial worktree install from INVALID EXP-001
command: >-
  /usr/bin/zsh -f -c 'source /opt/ros/jazzy/setup.zsh;
  export PARALLEL_EVIDENCE=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1;
  /usr/bin/time -p -o "$PARALLEL_EVIDENCE/reports/task7-colcon-build-002.time"
  /usr/bin/python3 -m colcon build --packages-select so101_demo_py --symlink-install
  > "$PARALLEL_EVIDENCE/reports/task7-colcon-build-002.log" 2>&1;
  build_exit=$?; printf "%s\n" "$build_exit" > "$PARALLEL_EVIDENCE/reports/task7-colcon-build-002.exit"; exit "$build_exit"'
expected_outputs:
  - /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install/so101_demo_py
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/task7-colcon-build-002.log
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/task7-colcon-build-002.exit
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/task7-colcon-build-002.time
result: so101_demo_py built successfully in 1.49 seconds; exit 0; installed Broker console script exists with UID:GID 1000:1000 and mode 0775; fresh package.zsh readback resolves the package and Python module to this worktree.
log_sha256: 3e1901c7dca07953b015064e40c442d281a601d7aabb674e374e7395c704be09
exit_file_sha256: 9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa
time_file_sha256: 33803f707c9e4d53a17cefecd377c9d8648824c3cb8d33cd0d3aecb0566256ce
installed_entrypoint_sha256: cb44cb102d2bea4df5c306ef1839bd6bb700e8100e780dce7b519e6350430ce1
qualification_scope: isolated detector package build only; does not clear the three-package Worker/live overlay gate blocked by EXP-001
retained: all listed outputs and the worktree package overlay
archived: none
deletion_candidates: none
```

## EXP-003 — Task 7 immutable combined CUDA image build

```yaml
experiment_id: EXP-003
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-12T04:00:54+08:00
  - status: RUNNING
    at: 2026-09-12T04:00:54+08:00
  - status: VALID
    at: 2026-09-12T04:08:36+08:00
hypothesis: The pinned ROS Jazzy base and eleven exact Python/CUDA dependencies can produce the immutable combined YOLO/Grounded-SAM image with read-back provenance labels matching the frozen Task 7 source.
host: AI-STATION-001
worktree: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1
committed_head: c4155995d1a0558f4175ace8ec3a7fc5ffd3ebcb
image_tag: so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1
dockerfile_sha256: ec8566ad07627da358b311b6fe2b4f64e32800eaa6d1182a756854a05a40fb1d
inline_lock_sha256: 90f7f5983d806e4f78f50eb45c411b0a1a0e62201aca6b1f3afade962604fa5f
package_source_sha256: c1d4c9d59663dd30cb8d5102a7152d3c2d0dc8de30b3dd76a452f8d919cb7e03
command: >-
  /usr/bin/zsh -f -c 'source .superpowers/sdd/2026-09-12-so101-parallel-multipoint-validation-implementation/test-env.zsh;
  /usr/bin/time -p -o "$PARALLEL_EVIDENCE/reports/task7-docker-build-003.time"
  scripts/parallel-perception-container.sh build
  --image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1
  --output "$PARALLEL_EVIDENCE/reports/broker-image-003.json"
  > "$PARALLEL_EVIDENCE/reports/task7-docker-build-003.log" 2>&1;
  build_exit=$?; printf "%s\n" "$build_exit" > "$PARALLEL_EVIDENCE/reports/task7-docker-build-003.exit"; exit "$build_exit"'
expected_outputs:
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/broker-image-003.json
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/task7-docker-build-003.log
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/task7-docker-build-003.exit
  - /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/task7-docker-build-003.time
acceptance: exit 0; immutable image ID; all three image labels equal the pre-run hashes; runtime dependency version import assertion succeeds during image build.
result: immutable combined image built successfully in 355.40 seconds; exit 0; image ID and all three provenance labels matched independent Docker inspect readback.
image_id: sha256:da433e4a02d4d5d420f3d33b7a18debb1f5ed52cf142186b79924cb5e0d14077
provenance_json_sha256: 1843c3db14fbbedd5fbdbad03bbc21c7b2338885957f2afd706f9886e5555274
build_log_sha256: c2deb470b71e10dedd77c781896e162af48ffc5241c2ed7f59c511ebd0521c3a
exit_file_sha256: 9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa
time_file_sha256: c26502b8785e41e6a961c6a014c06ee3909fb520540cc514af8b1677b700151f
retained: image, provenance JSON, build log, exit, and time evidence
archived: none
deletion_candidates: BuildKit caches are retained and are not approved for deletion.
```

## EXP-004 — Task 7 frozen dual-model GPU smoke

```yaml
experiment_id: EXP-004
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T04:09:11+08:00
  - status: RUNNING
    at: 2026-09-12T04:09:11+08:00
  - status: INVALID
    at: 2026-09-12T04:10:10+08:00
hypothesis: The immutable combined image can load and warm both frozen CUDA models, run both against the frozen P01 RGB image without ROS or motion, and emit owner/mode/provenance-verified receipts under a unique batch root.
mode: offline detector smoke; no ROS, simulation, planning, execution, or physical action
host: AI-STATION-001
worktree: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1
committed_head: c4155995d1a0558f4175ace8ec3a7fc5ffd3ebcb
batch_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/task7-smoke-004
image_tag: so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1
image_id: sha256:da433e4a02d4d5d420f3d33b7a18debb1f5ed52cf142186b79924cb5e0d14077
dockerfile_sha256: ec8566ad07627da358b311b6fe2b4f64e32800eaa6d1182a756854a05a40fb1d
inline_lock_sha256: 90f7f5983d806e4f78f50eb45c411b0a1a0e62201aca6b1f3afade962604fa5f
package_source_sha256: c1d4c9d59663dd30cb8d5102a7152d3c2d0dc8de30b3dd76a452f8d919cb7e03
input_rgb_sha256: 48febb1647afe462099c11079013c573281f8a1eee88425a2bcd4a04bf35124a
yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
gpu: NVIDIA GeForce RTX 5080; UUID GPU-0b7689c1-877a-b915-12aa-c9b9f86aa190; driver 595.84; 16303 MiB total; 15269 MiB free before run
gpu_device_gids: [0]
command: >-
  /usr/bin/zsh -f -c 'source .superpowers/sdd/2026-09-12-so101-parallel-multipoint-validation-implementation/test-env.zsh;
  smoke_batch="$PARALLEL_EVIDENCE/task7-smoke-004"; test ! -e "$smoke_batch" || exit 2;
  mkdir -m 700 "$smoke_batch" "$smoke_batch/workers";
  /usr/bin/time -p -o "$PARALLEL_EVIDENCE/reports/task7-smoke-004.time"
  scripts/parallel-perception-container.sh smoke
  --image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1
  --image-id sha256:da433e4a02d4d5d420f3d33b7a18debb1f5ed52cf142186b79924cb5e0d14077
  --batch-root "$smoke_batch"
  --input /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/reset-world-20/8a87dc3e-9836-4feb-8f3c-3286b1efcaff/batches/formal-reset20-candidate-002/points/01-task_start/sensor-snapshot/rgb.png
  --yolo-weights /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt
  --grounded-root /data/work/so101-models/grounded-sam-v2-scipy-lock
  --output "$PARALLEL_EVIDENCE/reports/broker-smoke-004.json"
  > "$PARALLEL_EVIDENCE/reports/task7-smoke-004.log" 2>&1;
  smoke_exit=$?; printf "%s\n" "$smoke_exit" > "$PARALLEL_EVIDENCE/reports/task7-smoke-004.exit"; exit "$smoke_exit"'
acceptance: exit 0; both models warm and return normalized outcomes with provenance and latency; host/container mapping, UID:GID, ready/smoke receipt modes, GPU groups, immutable image and no-network/no-ROS/no-motion isolation read back exactly; real socket is deferred to Task 11 by Ruling F3.
result: pre-execution admission failed; controller source readback showed that the frozen image's smoke result omitted per-model latency required by Task 7 Step 4. The command was not authorized or launched, and no batch/output path was created.
failure_classification: valid pre-execution acceptance failure; source and image provenance must change together before retry
retained: unique batch root, copied read-only RGB, runtime receipts, admission JSON, log, exit, and time evidence
archived: none
deletion_candidates: none; batch evidence is retained
```

## EXP-005 — Task 7 latency-qualified immutable image rebuild

```yaml
experiment_id: EXP-005
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-12T04:13:15+08:00
  - status: RUNNING
    at: 2026-09-12T04:13:15+08:00
  - status: VALID
    at: 2026-09-12T04:14:44+08:00
hypothesis: Rebuilding the combined image with explicit outer service latency preserves all frozen dependencies while making dual-model smoke timing directly auditable.
host: AI-STATION-001
worktree: /data/work/ws_moveit/.worktrees/parallel-multipoint-v1
committed_head: c4155995d1a0558f4175ace8ec3a7fc5ffd3ebcb
image_tag: so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1
dockerfile_sha256: ec8566ad07627da358b311b6fe2b4f64e32800eaa6d1182a756854a05a40fb1d
inline_lock_sha256: 90f7f5983d806e4f78f50eb45c411b0a1a0e62201aca6b1f3afade962604fa5f
package_source_sha256: 07ad87cfc2a40fd33df1b3a9cd5aeb69b27ad442b502de144e7093c1fd3e2315
command: >-
  /usr/bin/zsh -f -c 'source .superpowers/sdd/2026-09-12-so101-parallel-multipoint-validation-implementation/test-env.zsh;
  /usr/bin/time -p -o "$PARALLEL_EVIDENCE/reports/task7-docker-build-005.time"
  scripts/parallel-perception-container.sh build
  --image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1
  --output "$PARALLEL_EVIDENCE/reports/broker-image-005.json"
  > "$PARALLEL_EVIDENCE/reports/task7-docker-build-005.log" 2>&1;
  build_exit=$?; printf "%s\n" "$build_exit" > "$PARALLEL_EVIDENCE/reports/task7-docker-build-005.exit"; exit "$build_exit"'
acceptance: exit 0; new immutable image ID; Dockerfile/lock/source labels exactly match this experiment; runtime version and model-class import gates pass.
result: latency-qualified image rebuilt successfully from cache in 9.35 seconds; exit 0; independent Docker inspect matched the new immutable image ID and all three frozen labels.
image_id: sha256:89100312949f9a24512f0bbbd2e119379a6f9dd46c89f4aa400252f9508579e4
provenance_json_sha256: f40ebdd57a10f5eddede715427f07dd2e98ec81ae6d01cc4428869d1ab678c60
build_log_sha256: 7c60b5801b7e806d6f4af4b4048318988017397d8321e4b6bd5b78f953aa604b
exit_file_sha256: 9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa
time_file_sha256: f3e5b74a20e8391e8e049467dc22d7e4dedfac71d441e4d3836a6b7a8bd4c522
retained: rebuilt image and all build provenance/log/exit/time evidence
archived: none; the EXP-003 image ID remains auditable through its provenance record even if the tag advances
deletion_candidates: none; no image or cache deletion is authorized
```

## EXP-006 — Task 7 latency-qualified dual-model GPU smoke

```yaml
experiment_id: EXP-006
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-12T04:15:04+08:00
  - status: RUNNING
    at: 2026-09-12T04:15:04+08:00
  - status: VALID
    at: 2026-09-12T04:18:06+08:00
hypothesis: The latency-qualified immutable image can warm and execute both frozen models against P01 while preserving the offline, non-root, no-network, read-only isolation contract.
mode: offline detector smoke; no ROS, simulation, planning, execution, or physical action
batch_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/task7-smoke-006
image_id: sha256:89100312949f9a24512f0bbbd2e119379a6f9dd46c89f4aa400252f9508579e4
dockerfile_sha256: ec8566ad07627da358b311b6fe2b4f64e32800eaa6d1182a756854a05a40fb1d
inline_lock_sha256: 90f7f5983d806e4f78f50eb45c411b0a1a0e62201aca6b1f3afade962604fa5f
package_source_sha256: 07ad87cfc2a40fd33df1b3a9cd5aeb69b27ad442b502de144e7093c1fd3e2315
input_rgb_sha256: 48febb1647afe462099c11079013c573281f8a1eee88425a2bcd4a04bf35124a
yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
command: >-
  /usr/bin/zsh -f -c 'source .superpowers/sdd/2026-09-12-so101-parallel-multipoint-validation-implementation/test-env.zsh;
  smoke_batch="$PARALLEL_EVIDENCE/task7-smoke-006"; test ! -e "$smoke_batch" || exit 2;
  mkdir -m 700 "$smoke_batch" "$smoke_batch/workers";
  /usr/bin/time -p -o "$PARALLEL_EVIDENCE/reports/task7-smoke-006.time"
  scripts/parallel-perception-container.sh smoke
  --image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1
  --image-id sha256:89100312949f9a24512f0bbbd2e119379a6f9dd46c89f4aa400252f9508579e4
  --batch-root "$smoke_batch"
  --input /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/reset-world-20/8a87dc3e-9836-4feb-8f3c-3286b1efcaff/batches/formal-reset20-candidate-002/points/01-task_start/sensor-snapshot/rgb.png
  --yolo-weights /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt
  --grounded-root /data/work/so101-models/grounded-sam-v2-scipy-lock
  --output "$PARALLEL_EVIDENCE/reports/broker-smoke-006.json"
  > "$PARALLEL_EVIDENCE/reports/task7-smoke-006.log" 2>&1;
  smoke_exit=$?; printf "%s\n" "$smoke_exit" > "$PARALLEL_EVIDENCE/reports/task7-smoke-006.exit"; exit "$smoke_exit"'
acceptance: exit 0; ready and smoke receipts are owner 1000:1000 mode 0600; both model records have executed=true, normalized outcomes, finite non-negative service latency, adapter timing, and immutable provenance; mounts, GPU groups, UID:GID, no-network/no-ROS/no-motion isolation read back exactly; real socket remains Task 11 by Ruling F3.
result: exit 0 in 8.65 seconds; both models executed on CUDA and returned one QUALIFIED candidate each; all outer and adapter latencies were finite and non-negative; immutable provenance, UID:GID, mount flags, modes, and copied input hash matched readback; owned container and compute process exited cleanly.
yolo_result: one candidate; service latency 32.551903 ms; adapter latency 29.818351 ms; cold start 2660.430105 ms
grounded_result: one candidate; service latency 244.052789 ms; adapter latency 243.817828 ms; cold start 2673.495751 ms
admission_json_sha256: f078106cc4064a9fff08be1696433924935ed7b5f75822619250509e3552da06
ready_receipt_sha256: f44d257557255715e332b626e6e5e949d738f3e635cf6099d4d4532cf5ea11d3
smoke_receipt_sha256: e743f91f15c7a4f3df57534b3c5c40f974063eea1e1317bd377462dfa26bc5cf
copied_rgb_sha256: 48febb1647afe462099c11079013c573281f8a1eee88425a2bcd4a04bf35124a
log_sha256: 8dbb7dbe99da8971bfb93ab15bb5ff15a14eb2985575ab72db541e888203ddc7
exit_file_sha256: 9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa
time_file_sha256: 8ad155da00197c70545becbd02308631affe6e5862f70262cc650faeb9c81963
retained: unique batch root, copied read-only RGB, ready/smoke receipts, admission JSON, log, exit, and time evidence
archived: none
deletion_candidates: none; batch evidence is retained
```

## EXP-007 — Task 7 verified-content image rebuild

```yaml
experiment_id: EXP-007
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-12T04:36:26+08:00
  - status: RUNNING
    at: 2026-09-12T04:36:26+08:00
  - status: VALID
    at: 2026-09-12T04:38:33+08:00
hypothesis: The image can independently hash the actual copied package tree and refuse host-claimed provenance drift while preserving every frozen runtime dependency.
image_tag: so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1
dockerfile_sha256: 5ea9558890ee781a722f8e23e17025845211440459c87215d25f7ffd3ba5a595
inline_lock_sha256: 90f7f5983d806e4f78f50eb45c411b0a1a0e62201aca6b1f3afade962604fa5f
host_package_source_sha256: cd3b4b607881a090503be9c0e7d7ea7bb0327d090b8368f0b0e13be7c76c2427
command: >-
  /usr/bin/zsh -f -c 'source .superpowers/sdd/2026-09-12-so101-parallel-multipoint-validation-implementation/test-env.zsh;
  /usr/bin/time -p -o "$PARALLEL_EVIDENCE/reports/task7-docker-build-007.time"
  scripts/parallel-perception-container.sh build
  --image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1
  --output "$PARALLEL_EVIDENCE/reports/broker-image-007.json"
  > "$PARALLEL_EVIDENCE/reports/task7-docker-build-007.log" 2>&1;
  build_exit=$?; printf "%s\n" "$build_exit" > "$PARALLEL_EVIDENCE/reports/task7-docker-build-007.exit"; exit "$build_exit"'
acceptance: exit 0; image-computed actual source hash equals the host pre-build hash; verified provenance file read from a never-started owned container matches immutable ID labels; exact versions/imports pass; owned readback container is removed.
result: exit 0 in 14.70 seconds; image-internal actual source hash equaled the host pre-build hash; the verified provenance read from a never-started owned container matched the immutable image labels; the owned readback container was removed.
image_id: sha256:f7ac5cbe5e67491aa0cbc71003c2e5c3fa6378025a585eb96e7c02a67c25e115
verified_source_sha256: cd3b4b607881a090503be9c0e7d7ea7bb0327d090b8368f0b0e13be7c76c2427
provenance_json_sha256: ea154eb011497faffe77fbfae14ca9ce6afe03085a25f27c4c43ba2afaa86dfa
build_log_sha256: d85c857d1c6552191d532a0a115c3d03d92238861eff0ef972dbb016ae940ebf
exit_file_sha256: 9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa
time_file_sha256: d09d455592b23aa621fbcae27b2b114f79d0bfa7d9b7ff37b3f0d03d513ef9bf
retained: image, provenance JSON, log, exit, and time evidence
archived: none; prior immutable image IDs remain recorded
deletion_candidates: none; no image or cache deletion is authorized
```

## EXP-008 — Task 7 verified-content dual-model GPU smoke

```yaml
experiment_id: EXP-008
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-12T04:39:07+08:00
  - status: RUNNING
    at: 2026-09-12T04:39:07+08:00
  - status: VALID
    at: 2026-09-12T04:42:43+08:00
hypothesis: The content-verified immutable image preserves the successful dual-model P01 result and all offline isolation, timing, and cleanup gates after the review fixes.
mode: offline detector smoke; no ROS, simulation, planning, execution, or physical action
batch_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/task7-smoke-008
image_id: sha256:f7ac5cbe5e67491aa0cbc71003c2e5c3fa6378025a585eb96e7c02a67c25e115
dockerfile_sha256: 5ea9558890ee781a722f8e23e17025845211440459c87215d25f7ffd3ba5a595
inline_lock_sha256: 90f7f5983d806e4f78f50eb45c411b0a1a0e62201aca6b1f3afade962604fa5f
source_sha256: cd3b4b607881a090503be9c0e7d7ea7bb0327d090b8368f0b0e13be7c76c2427
verified_source_sha256: cd3b4b607881a090503be9c0e7d7ea7bb0327d090b8368f0b0e13be7c76c2427
input_rgb_sha256: 48febb1647afe462099c11079013c573281f8a1eee88425a2bcd4a04bf35124a
command: >-
  /usr/bin/zsh -f -c 'source .superpowers/sdd/2026-09-12-so101-parallel-multipoint-validation-implementation/test-env.zsh;
  smoke_batch="$PARALLEL_EVIDENCE/task7-smoke-008"; test ! -e "$smoke_batch" || exit 2;
  mkdir -m 700 "$smoke_batch" "$smoke_batch/workers";
  /usr/bin/time -p -o "$PARALLEL_EVIDENCE/reports/task7-smoke-008.time"
  scripts/parallel-perception-container.sh smoke --image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1
  --image-id sha256:f7ac5cbe5e67491aa0cbc71003c2e5c3fa6378025a585eb96e7c02a67c25e115
  --batch-root "$smoke_batch"
  --input /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/reset-world-20/8a87dc3e-9836-4feb-8f3c-3286b1efcaff/batches/formal-reset20-candidate-002/points/01-task_start/sensor-snapshot/rgb.png
  --yolo-weights /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt
  --grounded-root /data/work/so101-models/grounded-sam-v2-scipy-lock
  --output "$PARALLEL_EVIDENCE/reports/broker-smoke-008.json"
  > "$PARALLEL_EVIDENCE/reports/task7-smoke-008.log" 2>&1;
  smoke_exit=$?; printf "%s\n" "$smoke_exit" > "$PARALLEL_EVIDENCE/reports/task7-smoke-008.exit"; exit "$smoke_exit"'
acceptance: exit 0; both models executed with normalized outcome and finite non-negative outer/adapter latency; source equals verified source; owner/mode/mount/GPU/no-network isolation and post-run container/GPU cleanup pass; real socket remains Task 11 by Ruling F3.
result: >-
  Exit 0 in 8.93 s (user 0.23 s, sys 0.09 s). grounded-sam returned QUALIFIED with one
  candidate in 190.99948299117386 ms outer / 190.76926 ms adapter latency; yolo returned
  QUALIFIED with one candidate in 32.44399907998741 ms outer / 29.158651 ms adapter latency.
  The runtime-recomputed source_sha256 and image verified_source_sha256 both equal
  cd3b4b607881a090503be9c0e7d7ea7bb0327d090b8368f0b0e13be7c76c2427. Batch and IPC
  directories were 0700; ready, smoke, and admission receipts were 0600; the copied input was
  0400; all were owned by uid/gid 1000:1000. No container derived from the image and no NVIDIA
  compute application remained after readback.
ready_sha256: 1e1fe452fb0e16feb340ca1d95993293a949255c16893d1ff100fc3d3cbe215f
smoke_sha256: 1f0fad7d0383d8868263b96a28d14b84f2b32429f823455a805bdb789b6b1ef6
admission_sha256: 73d1dc2d7203c076fef622c7665c61f44f51925353772b6e1b2986125716679f
log_sha256: cd73dff77392026a934341d93bf8db895aa23214fa6549428dfcdb6a414ae834
exit_sha256: 9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa
time_sha256: 5c6efea85aded95065e4ef8699a761c42928495dc9f42296bc693a2a103c67f7
retained: unique batch root, receipts, admission, input copy, log, exit, and time evidence
archived: none
deletion_candidates: none; the batch evidence is retained
```

## EXP-009 — Task 8 two-Worker resource dry admission

```yaml
experiment_id: EXP-009
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T05:06:51+08:00
  - status: RUNNING
    at: 2026-09-12T05:07:17+08:00
  - status: INVALID
    at: 2026-09-12T05:07:39+08:00
hypothesis: The current ai-station has enough CPU, RAM, and GPU memory to allocate exactly two isolated Worker resource sets with no live ROS-domain, socket, directory, or namespace collision.
mode: host resource dry admission; read-only system probes and private directory/manifest creation only; no ROS, MuJoCo, MoveIt, Broker, simulation, planning, execution, or physical action
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/resource-dry
committed_head: 42728127626af794c5f1c3f7543a134b5655667f
resources_source_sha256: 2b9ccd755fe0376498a46e78bc4c5caa43b550fc30902fd290ffc35f65ba1fcb
resources_test_sha256: c5f482fe96048ca1b2573ea5542d1dd901133e9a495cfc0f08c67727de11cff9
command: >-
  /usr/bin/zsh -f -c 'source .superpowers/sdd/2026-09-12-so101-parallel-multipoint-validation-implementation/test-env.zsh;
  umask 077; /usr/bin/time -p -o "$PARALLEL_EVIDENCE/reports/task8-resource-dry-009.time"
  "$PARALLEL_PYTHON" -m so101_demo.parallel_batch.resources
  --config src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml --worker-count 2
  --evidence-root "$PARALLEL_EVIDENCE/resource-dry" --dry-run
  > "$PARALLEL_EVIDENCE/reports/task8-resource-dry-009.log" 2>&1;
  run_exit=$?; printf "%s\n" "$run_exit" > "$PARALLEL_EVIDENCE/reports/task8-resource-dry-009.exit";
  exit "$run_exit"'
acceptance: >-
  Exit 0; exact requested and admitted worker count 2; observed finite CPU/RAM/GPU satisfy
  required 8 logical CPU, 14.0 GiB RAM, and 8.0 GiB GPU; domains 181 and 182 have no
  live collision; every real per-Worker identity/path is unique; Unix socket paths are absent
  and at most 107 bytes; all MuJoCo-only non-resources are literal not_applicable; manifest,
  allowlisted environment, owner, and private modes read back exactly; no relevant process starts.
result: >-
  Exit 2 in 0.08 s (user 0.06 s, sys 0.01 s) before directory creation. The probe
  reported 24 logical CPUs and 14.9111328125 GiB GPU free, but only 1.8330574035644531
  GiB RAM against the frozen 14.0 GiB threshold. Immediate host readback showed
  MemAvailable=28538252 kB (about 27.22 GiB) and only MemFree=1925136 kB (about 1.84
  GiB); the implementation had measured SC_AVPHYS_PAGES/MemFree rather than Linux
  MemAvailable, so this is an implementation-invalid admission result rather than a
  genuine resource shortage. No resource-dry directory or relevant process was created.
log_sha256: aeddfd0f25ad4fdd4da9380d7eda96b4dae384d39d0b3a3061d7095e27cbc450
exit_sha256: 53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3
time_sha256: 1f00c70a85b25c45237e698754bbdddf8fd5ead47ffa49dd985ec51b93d2688a
retained: log, exit, and time evidence; no resource root or manifest was created
archived: none
deletion_candidates: none
```

## EXP-010 — Task 8 corrected MemAvailable two-Worker dry admission

```yaml
experiment_id: EXP-010
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-12T05:10:38+08:00
  - status: RUNNING
    at: 2026-09-12T05:11:49+08:00
  - status: VALID
    at: 2026-09-12T05:12:22+08:00
hypothesis: Strict Linux MemAvailable probing will admit exactly two isolated Worker resource sets on the current ai-station while preserving all collision, namespace, mode, and no-process gates.
mode: host resource dry admission; read-only system probes and private directory/manifest creation only; no ROS, MuJoCo, MoveIt, Broker, simulation, planning, execution, or physical action
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/resource-dry
committed_head: 42728127626af794c5f1c3f7543a134b5655667f
resources_source_sha256: b3ce1aed6e27604161a54f2131dca821c26b2ea3db5fc3c5901761115738d343
resources_test_sha256: 4cf6662a89310f336cf3e58e2a7e7619971ee60f3aac6445ddb92d5ad285560f
pre_run_mem_available_kib: 28527972
command: >-
  /usr/bin/zsh -f -c 'source .superpowers/sdd/2026-09-12-so101-parallel-multipoint-validation-implementation/test-env.zsh;
  umask 077; /usr/bin/time -p -o "$PARALLEL_EVIDENCE/reports/task8-resource-dry-010.time"
  "$PARALLEL_PYTHON" -m so101_demo.parallel_batch.resources
  --config src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml --worker-count 2
  --evidence-root "$PARALLEL_EVIDENCE/resource-dry" --dry-run
  > "$PARALLEL_EVIDENCE/reports/task8-resource-dry-010.log" 2>&1;
  run_exit=$?; printf "%s\n" "$run_exit" > "$PARALLEL_EVIDENCE/reports/task8-resource-dry-010.exit";
  exit "$run_exit"'
acceptance: >-
  Exit 0; exact requested and admitted worker count 2; Linux MemAvailable-derived RAM and
  observed finite CPU/GPU satisfy required 14.0 GiB RAM, 8 logical CPU, and 8.0 GiB GPU;
  domains 181 and 182 have no live collision; every real per-Worker identity/path is unique;
  Unix socket paths are absent and at most 107 bytes; all MuJoCo-only non-resources are literal
  not_applicable; manifest, allowlisted environment, owner, and private modes read back exactly;
  no relevant process starts.
result: >-
  Exit 0 in 0.13 s (user 0.06 s, sys 0.02 s). Admission preserved requested_worker_count
  and worker_count at exactly 2. Observed resources were 24 logical CPUs, 27.201595306396484
  GiB Linux MemAvailable, and 14.9111328125 GiB GPU free against required 8, 14.0, and
  8.0 respectively. Domains were exactly 181 and 182. Worker, session, controller namespace,
  ROS directories, temp, socket namespace/path, and root identities were pairwise unique;
  both socket paths were 89 bytes and absent. Every directory was 0700 and manifest/log/exit/time
  files were 0600, all owner 1000:1000. Environment keys were limited to the approved base and
  generated Worker-specific allowlists. No relevant ROS, MuJoCo, MoveIt, or Broker process remained.
manifest_sha256: b038c7e8fc8526665c8934bfc9b1c4beb8e098844f0189bb60090329b06a64c3
log_sha256: 328bf438984281edb65cf2cd3057b2e00553d18a2f1d03a7495294511ae6ffbd
exit_sha256: 9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa
time_sha256: 7dc7cd0c5414a0287a97901254c2d0e8614aa4360c8d484e619a939141585be5
retained: log, exit, time, resource root, private namespaces, and manifest
archived: none
deletion_candidates: none; admitted resource evidence will be retained
```

## EXP-011 — Task 8 hardened atomic resource dry admission

```yaml
experiment_id: EXP-011
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T05:36:38+08:00
  - status: RUNNING
    at: 2026-09-12T05:37:11+08:00
  - status: INVALID
    at: 2026-09-12T05:37:41+08:00
hypothesis: The review-hardened allocator can admit exactly two Workers while atomically claiming same-UID ROS domains, securely publishing evidence through held directory descriptors, and allocating unique headless-EGL context identities.
mode: host resource dry admission; read-only system/process probes, host-wide same-UID flock claims, and private directory/manifest creation only; no ROS, MuJoCo, MoveIt, Broker, simulation, planning, execution, or physical action
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/resource-dry-fix1
claim_root: /run/user/1000/so101-parallel-domain-claims
claim_root_preflight: existing owner 1000:1000 mode 0700 non-symlink directory with unlocked 0600 claim records retained from pure Task 8 tests
committed_head: 6432942c68862bec8b382ae66bb89dd1a8d25b37
resources_source_sha256: 09827b8b596253d1895b19864b559fb7423d2750ec12f29398d36f9eb432ce88
resources_test_sha256: f4ac405f5bb2b85ded7ff8467e8ebb800995d91a45dc94f92a20fd7bd255091b
command: >-
  /usr/bin/zsh -f -c 'cd /data/work/ws_moveit/.worktrees/parallel-multipoint-v1;
  source .superpowers/sdd/2026-09-12-so101-parallel-multipoint-validation-implementation/test-env.zsh;
  test ! -e "$PARALLEL_EVIDENCE/resource-dry-fix1" || { print -u2 "resource-dry-fix1 already exists"; exit 97; };
  umask 077; /usr/bin/time -p -o "$PARALLEL_EVIDENCE/reports/task8-resource-dry-011.time"
  "$PARALLEL_PYTHON" -m so101_demo.parallel_batch.resources
  --config src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml --worker-count 2
  --evidence-root "$PARALLEL_EVIDENCE/resource-dry-fix1" --dry-run
  > "$PARALLEL_EVIDENCE/reports/task8-resource-dry-011.log"
  2> "$PARALLEL_EVIDENCE/reports/task8-resource-dry-011.stderr";
  test_exit=$?; printf "%s\n" "$test_exit" > "$PARALLEL_EVIDENCE/reports/task8-resource-dry-011.exit";
  exit "$test_exit"'
acceptance: >-
  Exit 0; exact worker count 2; CPU/Linux MemAvailable/GPU static gates pass; domains 181/182
  are acquired atomically in fixed order and released when the dry CLI exits; manifest limits
  the claim scope to cooperating same-UID processes and records uid_flock_v1 claims; unique
  Worker/session/controller/path/socket and headless-EGL context identities; all non-resources
  remain literal not_applicable; trusted-path owner/mode/symlink identities, 0700 directories,
  0600 records, durable manifest readback, environment allowlist, socket length/absence, empty
  stderr, and no persistent related process all pass.
result: >-
  Exit 2 in 0.07 s (user 0.05 s, sys 0.01 s) with PROC_ENV_UNVERIFIABLE for PID
  15163 before batch-directory creation. Readback identified PID 15163 as the long-lived same-UID
  `/usr/lib/systemd/systemd --user`; its cmdline and stat are readable but environ and exe are
  permanently permission-denied by the host policy. Thus the implementation applies the
  same-UID uncertainty rule too broadly to a known non-ROS service manager and cannot admit on
  this host. The three retained claim files were all independently lockable after CLI exit;
  no batch root, manifest, related process, or held claim remained.
stdout_sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
stderr_sha256: 0809d6a442d9906c35a8cc0770a13453335f130973b66dee8df99593c0c6f1ef
exit_sha256: 53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3
time_sha256: 36ed4b0c320f1c4b2f0e8057de2bb49214aba89c82c0a3b34fc99bf8b1f0073a
retained: stdout, stderr, exit, time, and unlocked host claim records; no resource tree or manifest was created
archived: none
deletion_candidates: none
```

## EXP-012 — Task 8 candidate-scoped atomic resource dry admission

```yaml
experiment_id: EXP-012
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-12T05:47:43+08:00
  - status: RUNNING
    at: 2026-09-12T05:48:17+08:00
  - status: VALID
    at: 2026-09-12T05:49:05+08:00
hypothesis: Candidate-scoped same-UID process inspection can skip the host's frozen non-ROS service managers while preserving fail-closed inspection of high-recall ROS/DDS-capable processes and every hardened atomic resource gate.
mode: host resource dry admission; read-only system/process probes, host-wide same-UID flock claims, and private directory/manifest creation only; no ROS, MuJoCo, MoveIt, Broker, simulation, planning, execution, or physical action
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/resource-dry-fix2
claim_root: /run/user/1000/so101-parallel-domain-claims
claim_preflight: domain-181.lock and domain-182.lock are regular owner 1000:1000 mode 0600 files and both were independently nonblocking-lockable before execution
known_host_skip: pid 15163, uid 1000, starttime_ticks 104116, comm systemd, argv /usr/lib/systemd/systemd --user
committed_head: 6432942c68862bec8b382ae66bb89dd1a8d25b37
resources_source_sha256: 3930ff5da544851b02d68993d35b6ce72a917cef8d9290642b7bcfcec8a46278
resources_test_sha256: 86eacd0254c53945eee6579c5759bb3433becbc8d5782eb9d429d40ba915973a
command: >-
  /usr/bin/zsh -f -c 'cd /data/work/ws_moveit/.worktrees/parallel-multipoint-v1;
  source .superpowers/sdd/2026-09-12-so101-parallel-multipoint-validation-implementation/test-env.zsh;
  test ! -e "$PARALLEL_EVIDENCE/resource-dry-fix2" || { print -u2 "resource-dry-fix2 already exists"; exit 97; };
  umask 077; /usr/bin/time -p -o "$PARALLEL_EVIDENCE/reports/task8-resource-dry-012.time"
  "$PARALLEL_PYTHON" -m so101_demo.parallel_batch.resources
  --config src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml --worker-count 2
  --evidence-root "$PARALLEL_EVIDENCE/resource-dry-fix2" --dry-run
  > "$PARALLEL_EVIDENCE/reports/task8-resource-dry-012.log"
  2> "$PARALLEL_EVIDENCE/reports/task8-resource-dry-012.stderr";
  test_exit=$?; printf "%s\n" "$test_exit" > "$PARALLEL_EVIDENCE/reports/task8-resource-dry-012.exit";
  exit "$test_exit"'
acceptance: >-
  Exit 0 with empty stderr and one JSON stdout document; exact count 2 and static gates pass;
  domains 181/182 are fully locked before process scan, all-or-none claim records are published,
  and locks release only at dry CLI close; the manifest records candidate, frozen-skip, unknown,
  cross-UID, and claim trust policies plus complete PID 15163 skip identity; unique headless-EGL,
  Worker, ROS, path, and socket identities; 0700 directories, 0600 records, held-dirfd path
  identity and durable readback; allowlisted environment; absent <=107-byte sockets; literal
  not_applicable non-resources; and no persistent related process.
result: >-
  Exit 0 in 0.15 s (user 0.08 s, sys 0.02 s) with empty stderr. Exact count 2
  was admitted with 24 logical CPUs, 27.078018188476562 GiB Linux MemAvailable, and
  14.9140625 GiB GPU free against required 8, 14.0, and 8.0. Domain claims 181/182
  record uid_flock_v1 and the exact resource-dry-fix2 identity; both locks were independently
  acquirable after CLI exit. Process-scan policy and five frozen-skip records read back, including
  exact PID 15163 uid/starttime/comm/cmdline/reason. Both Workers have unique domain, session,
  controller, directory, socket, and headless-EGL identities; sockets were absent and 94 bytes.
  All resource directories were owner 1000:1000 mode 0700; manifest and report files plus claim
  records were 0600. Manifest/path readback and environment/non-resource assertions passed.
  No actual ROS, MuJoCo, MoveIt, or Broker process persisted; the process-inventory regex matched
  only its own inspection command.
manifest_sha256: aac93afc4ae2e43281855c5d5fffceb0fcb3603c501d454f704c58688582b571
stdout_sha256: 36b95847d7b8471af1930fc7d527757d2b55ef3715f99c511bb20d1728ac50d5
stderr_sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
exit_sha256: 9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa
time_sha256: ac77a9d1f424f06ac2468fd4cba52d1cc9ee76a9e98c2dd0ff553250a9e8af24
domain_181_claim_sha256: ba3a79bb60bcb16eb19cd2282af03c094b40964860b9c615bdd7cf90553f7419
domain_182_claim_sha256: 654a83e524b07d3aa458e6f64c83e0fa42d15b795eff5aaab2ec32a51cfda663
external_claim_records_are_mutable: true
immutable_claim_evidence: the copies embedded in resource_manifest.json under its recorded manifest_sha256
post_validation_correction: >-
  At 2026-09-12T05:53:34+08:00 the independent review unit gate pytest-ayZnIGcE
  exposed a test-isolation defect by legitimately acquiring the unlocked production claim files
  and replacing their last-holder diagnostics with scratch batch r39. This did not alter the
  EXP-012 manifest or acquire a live-held claim, but proves the external files are mutable
  coordination state and cannot be retained as immutable hash evidence.
post_validation_domain_181_sha256: bbe64160cc2169da62030d34590ef47d24f1842f79a6e044fd2beff1ff024a46
post_validation_domain_182_sha256: 4ae312a2f899e8187c76febee3f92a1ff7409ed08d1011b9ef9c3b8c93835a9c
second_post_validation_correction: >-
  At 2026-09-12T06:11:08+08:00 the controller-side full unit gate pytest-Nb5pQJ74
  found three additional direct allocator constructions that omitted the scratch claim root.
  The test behavior itself passed 123 cases, but the production-claim autouse fixture correctly
  raised three teardown errors after records 181 and 182 changed from reviewer scratch r39 to
  controller scratch r46. No active flock was bypassed, the records were not restored, and this
  further confirms that the external files are mutable last-holder coordination diagnostics rather
  than immutable EXP-012 evidence. The implementation tests now inject a scratch claim root at
  every allocator and CLI call; the corrected full gate pytest-IzENHtLr passed 123 tests while
  preserving the production records byte-for-byte and mtime-for-mtime.
second_post_validation_domain_181_sha256: b85f1c8e55e9b56561c99a507e7468c23e640136b5acb1b83b87e036005e5fe6
second_post_validation_domain_182_sha256: 8599bf707233cd109015f7c0bad6b45026f63d8e046334c96f693756d51ad105
retained: stdout, stderr, exit, time, resource tree, manifest, and host claim records
archived: none
deletion_candidates: none; admitted resource evidence and coordination records will be retained
```

## EXP-013 — Task 8 atomically published and review-closed two-Worker dry admission

```yaml
experiment_id: EXP-013
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T06:15:08+08:00
  - status: RUNNING
    at: 2026-09-12T06:16:01+08:00
  - status: INVALID
    at: 2026-09-12T06:16:34+08:00
hypothesis: The review-corrected allocator can admit exactly two isolated Workers without consulting the three-Worker Task 14 verifier, while publishing only a complete no-replace manifest and preserving production claim isolation in its unit tests.
mode: host resource dry admission; read-only system/process probes, host-wide same-UID flock claims, and private directory/manifest creation only; no ROS, MuJoCo, MoveIt, Broker, simulation, planning, execution, or physical action
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/resource-dry-fix3
claim_root: /run/user/1000/so101-parallel-domain-claims
claim_preflight: domains 181, 182, and 183 are owner 1000:1000 mode 0600 regular files and independently nonblocking-lockable; 181/182 contain mutable last-holder r46 records and 183 contains r39
git_head_at_run: 516974d1bf1e9725f9cc8bc5722c0b4d1515bdcd
candidate_bytes_later_committed_as: e2a8e036c8f1fad0a6554de9d78858299b530dca
resources_source_sha256: 8bc83bb745b0b8db39a1e48d478905aa11b852f6536250d0548f03de6cbce199
resources_test_sha256: 5b24b7f674fab367d826b8acfa4eefe8feafa9bb1aaeb27d49bd91b36dfb14f6
authorized_diff_sha256: 7dd7ef037efe7c02f0dac62a91b13d09c9e693a5b17b8d7185cd5b242ffb6d3c
pre_run_domain_181_sha256: b85f1c8e55e9b56561c99a507e7468c23e640136b5acb1b83b87e036005e5fe6
pre_run_domain_182_sha256: 8599bf707233cd109015f7c0bad6b45026f63d8e046334c96f693756d51ad105
pre_run_domain_183_sha256: 4bae7bccf96b89b60a84a24fd9610fb41f1737c58539d70356953ee7fef0332d
command: >-
  /usr/bin/zsh -f -c 'set -eu; cd /data/work/ws_moveit/.worktrees/parallel-multipoint-v1;
  source .superpowers/sdd/2026-09-12-so101-parallel-multipoint-validation-implementation/test-env.zsh;
  root="$PARALLEL_EVIDENCE/resource-dry-fix3"; log="$PARALLEL_EVIDENCE/reports/task8-resource-dry-013.log";
  err="$PARALLEL_EVIDENCE/reports/task8-resource-dry-013.stderr"; timing="$PARALLEL_EVIDENCE/reports/task8-resource-dry-013.time";
  status="$PARALLEL_EVIDENCE/reports/task8-resource-dry-013.exit"; test ! -e "$root"; test ! -e "$log";
  test ! -e "$err"; test ! -e "$timing"; test ! -e "$status"; umask 077; set +e;
  /usr/bin/time -p -o "$timing" "$PARALLEL_PYTHON" -m so101_demo.parallel_batch.resources
  --config src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml --worker-count 2
  --evidence-root "$root" --dry-run >"$log" 2>"$err"; rc=$?; set -e;
  printf "%s\n" "$rc" >"$status"; exit "$rc"'
acceptance: >-
  Exit and status 0 with empty stderr and one complete JSON stdout document; exact requested and
  admitted count 2; finite CPU/Linux MemAvailable/GPU meet 8 CPU, 14.0 GiB RAM, and 8.0 GiB GPU;
  domains 181/182 are acquired all-or-none before the process scan and independently lockable after
  CLI exit; domain 183 content/hash/mtime is unchanged; manifest copies the exact claims and trust
  policy; every Worker/domain/session/controller/path/socket/headless-EGL identity is unique; socket
  paths are absent and at most 107 bytes; simulation_port, bridge_port, virtual_display, and
  GZ_PARTITION are literal not_applicable; all directories are owner 1000:1000 mode 0700 and all
  manifest/claim/report files are owner 1000:1000 mode 0600; final manifest is complete and has no
  temporary sibling; the two-Worker path neither requires nor invokes Task 14 live evidence; no
  related ROS, MuJoCo, MoveIt, Gazebo, Broker, container, or GPU process remains.
result: >-
  The shell exited 1 before the product module ran. Enabling nounset before sourcing the ROS and
  worktree setup emitted unset-variable errors, and the command then attempted to assign the zsh
  read-only special parameter status. No batch root, stdout/stderr/time/exit report, claim change,
  or related process was created. This is an invalid command-construction result, not a resource
  admission result; the ID and absent output path will not be reused.
retained: ledger record of the command-construction failure; no runtime artifacts were created
archived: none
deletion_candidates: none
```

## EXP-014 — Task 8 corrected atomically published two-Worker dry admission

```yaml
experiment_id: EXP-014
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-12T06:16:34+08:00
  - status: RUNNING
    at: 2026-09-12T06:17:17+08:00
  - status: VALID
    at: 2026-09-12T06:18:35+08:00
hypothesis: With the zsh setup order and exit-file variable corrected, the review-corrected allocator will admit exactly two isolated Workers, publish one complete no-replace manifest, and release its exact domain claims without consulting Task 14 evidence.
mode: host resource dry admission; read-only system/process probes, host-wide same-UID flock claims, and private directory/manifest creation only; no ROS, MuJoCo, MoveIt, Broker, simulation, planning, execution, or physical action
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/resource-dry-fix4
claim_root: /run/user/1000/so101-parallel-domain-claims
claim_preflight: domains 181, 182, and 183 remain byte-identical to EXP-013 preflight and independently nonblocking-lockable; EXP-013 created no artifact or claim change
git_head_at_run: 516974d1bf1e9725f9cc8bc5722c0b4d1515bdcd
candidate_bytes_later_committed_as: e2a8e036c8f1fad0a6554de9d78858299b530dca
resources_source_sha256: 8bc83bb745b0b8db39a1e48d478905aa11b852f6536250d0548f03de6cbce199
resources_test_sha256: 5b24b7f674fab367d826b8acfa4eefe8feafa9bb1aaeb27d49bd91b36dfb14f6
authorized_diff_sha256: 7dd7ef037efe7c02f0dac62a91b13d09c9e693a5b17b8d7185cd5b242ffb6d3c
pre_run_domain_181_sha256: b85f1c8e55e9b56561c99a507e7468c23e640136b5acb1b83b87e036005e5fe6
pre_run_domain_182_sha256: 8599bf707233cd109015f7c0bad6b45026f63d8e046334c96f693756d51ad105
pre_run_domain_183_sha256: 4bae7bccf96b89b60a84a24fd9610fb41f1737c58539d70356953ee7fef0332d
command: >-
  /usr/bin/zsh -f -c 'cd /data/work/ws_moveit/.worktrees/parallel-multipoint-v1;
  source .superpowers/sdd/2026-09-12-so101-parallel-multipoint-validation-implementation/test-env.zsh;
  set -eu; root="$PARALLEL_EVIDENCE/resource-dry-fix4";
  log="$PARALLEL_EVIDENCE/reports/task8-resource-dry-014.log";
  err="$PARALLEL_EVIDENCE/reports/task8-resource-dry-014.stderr";
  timing="$PARALLEL_EVIDENCE/reports/task8-resource-dry-014.time";
  exit_file="$PARALLEL_EVIDENCE/reports/task8-resource-dry-014.exit";
  test ! -e "$root"; test ! -e "$log"; test ! -e "$err"; test ! -e "$timing";
  test ! -e "$exit_file"; umask 077; set +e;
  /usr/bin/time -p -o "$timing" "$PARALLEL_PYTHON" -m so101_demo.parallel_batch.resources
  --config src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml --worker-count 2
  --evidence-root "$root" --dry-run >"$log" 2>"$err"; rc=$?; set -e;
  printf "%s\n" "$rc" >"$exit_file"; exit "$rc"'
acceptance: >-
  Exit and recorded status 0 with empty stderr and one complete JSON stdout document; exact requested
  and admitted count 2; finite CPU/Linux MemAvailable/GPU meet 8 CPU, 14.0 GiB RAM, and 8.0 GiB GPU;
  domains 181/182 are acquired all-or-none before the process scan and independently lockable after
  CLI exit; domain 183 content/hash/mtime is unchanged; manifest copies the exact claims and trust
  policy; every Worker/domain/session/controller/path/socket/headless-EGL identity is unique; socket
  paths are absent and at most 107 bytes; simulation_port, bridge_port, virtual_display, and
  GZ_PARTITION are literal not_applicable; all directories are owner 1000:1000 mode 0700 and all
  manifest/claim/report files are owner 1000:1000 mode 0600; final manifest is complete and has no
  temporary sibling; the two-Worker path neither requires nor invokes Task 14 live evidence; no
  related ROS, MuJoCo, MoveIt, Gazebo, Broker, container, or GPU process remains.
result: >-
  Exit and recorded status were 0 in 0.17 s (user 0.09 s, sys 0.02 s), stderr was
  empty, and stdout parsed as exactly the same JSON document as the atomically published
  resource_manifest.json. Admission observed 24 logical CPUs, 26.982009887695312 GiB Linux
  MemAvailable, and 14.84375 GiB GPU free against required 8, 14.0, and 8.0. The exact two
  Workers used domains 181/182, pairwise-unique Worker/session/controller/directory/socket/EGL
  identities, absent 94-byte sockets, isolated egl environments, and literal not_applicable
  non-resources. The manifest recorded no live_headroom_evidence, confirming the two-Worker path
  did not require Task 14. Every batch directory was owner 1000:1000 mode 0700, the manifest and
  reports were 0600, and no manifest temporary sibling remained. External claims 181/182 exactly
  matched the copies in the manifest and all three domain files were independently lockable after
  exit; domain 183 retained its pre-run hash and mtime. Five frozen non-candidate process skips were
  fully recorded. No process referenced this batch or resource module after readback, and no running
  container or NVIDIA compute application remained.
manifest_sha256: 1bc87274a3d3f08093800c274eb5a4e8655e5f5870c2f715da0ac1c96c8ef6a3
stdout_sha256: b86319a604acf4f616fddf60ad0d86008858597138079a7336be4ea3661ba086
stderr_sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
time_sha256: 71aca1a9dd3569018d28a37c266759ed4e2bed2f9355b99f3f30d61b03c05aa9
exit_sha256: 9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa
post_run_domain_181_sha256: e6f7597c67d450d66fb112ebb2787fbcabe465a49336da03503318f9bd4dfad3
post_run_domain_182_sha256: 596f0046a7c2f5f341c57915b2122b261b938a1834880f429f6598336d2720b0
post_run_domain_183_sha256: 4bae7bccf96b89b60a84a24fd9610fb41f1737c58539d70356953ee7fef0332d
retained: stdout, stderr, exit, time, resource tree, and immutable manifest; unlocked host claim records are mutable coordination state and only their time-scoped diagnostics are indexed here
archived: none
deletion_candidates: none
```

## EXP-015 — Task 8 independently anchored three-Worker gate and final two-Worker dry admission

```yaml
experiment_id: EXP-015
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-12T06:52:33+08:00
  - status: RUNNING
    at: 2026-09-12T06:55:43+08:00
  - status: INVALID
    at: 2026-09-12T06:56:46+08:00
hypothesis: The round-3 candidate preserves exact two-Worker host admission while making default three-Worker admission fail closed until Task 11 supplies independent Task 14 acceptance and current full-provenance authorities.
mode: host resource dry admission; read-only system/process probes, host-wide same-UID flock claims, and private directory/manifest creation only; no ROS, MuJoCo, MoveIt, Broker, simulation, planning, execution, or physical action
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/resource-dry-fix5
claim_root: /run/user/1000/so101-parallel-domain-claims
claim_preflight: domains 181, 182, and 183 are owner 1000:1000 mode 0600 regular files, independently nonblocking-lockable, and retain the exact EXP-014 post-run hashes
git_head_at_run: e2a8e036c8f1fad0a6554de9d78858299b530dca
dirty_candidate_scope: exactly resources.py and test_parallel_batch_resources.py; controller ledger is separately untracked
resources_source_sha256: 86bb3661b2e3f0515cd021ac2566a18d791733b43deccabc76877e87dbc21e3d
resources_test_sha256: 6f95ca6d341de9975dfaeb97169e66c8aae04beea73ce77c3e53d57780e10e9b
authorized_diff_sha256: 0ca7e401e9e0ad194d89653990bf290bc83a40535f3fc503551b2a71508e8ac1
pre_run_domain_181_sha256: e6f7597c67d450d66fb112ebb2787fbcabe465a49336da03503318f9bd4dfad3
pre_run_domain_182_sha256: 596f0046a7c2f5f341c57915b2122b261b938a1834880f429f6598336d2720b0
pre_run_domain_183_sha256: 4bae7bccf96b89b60a84a24fd9610fb41f1737c58539d70356953ee7fef0332d
round3_unit_gate: pytest-DmWNP0Uo; 138 passed in 0.80 s pytest and 1.06 s wall
command: >-
  /usr/bin/zsh -f -c 'set -e;
  cd /data/work/ws_moveit/.worktrees/parallel-multipoint-v1;
  source .superpowers/sdd/2026-09-12-so101-parallel-multipoint-validation-implementation/test-env.zsh;
  run_root="$PARALLEL_EVIDENCE/resource-dry-fix5";
  run_log="$PARALLEL_EVIDENCE/reports/task8-resource-dry-015.log";
  run_stderr="$PARALLEL_EVIDENCE/reports/task8-resource-dry-015.stderr";
  run_time="$PARALLEL_EVIDENCE/reports/task8-resource-dry-015.time";
  run_exit="$PARALLEL_EVIDENCE/reports/task8-resource-dry-015.exit";
  test ! -e "$run_root"; test ! -e "$run_log"; test ! -e "$run_stderr";
  test ! -e "$run_time"; test ! -e "$run_exit"; umask 077; set +e;
  /usr/bin/time -p -o "$run_time" "$PARALLEL_PYTHON" -m so101_demo.parallel_batch.resources
  --config src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml --worker-count 2
  --evidence-root "$run_root" --dry-run >"$run_log" 2>"$run_stderr";
  test_exit=$?; set -e; printf "%s\n" "$test_exit" >"$run_exit"; exit "$test_exit"'
acceptance: >-
  Exit and recorded status 0 with empty stderr and one complete JSON stdout document; exact count 2;
  finite CPU/Linux MemAvailable/GPU meet 8 CPU, 14.0 GiB RAM, and 8.0 GiB GPU; domains 181/182
  are acquired all-or-none before the process scan and independently lockable after exit; domain 183
  hash and mtime remain unchanged; manifest claims/trust policy match external time-scoped diagnostics;
  every Worker/domain/session/controller/path/socket/headless-EGL identity is unique; socket paths are
  absent and at most 107 bytes; simulation_port, bridge_port, virtual_display, and GZ_PARTITION are
  literal not_applicable; directories are owner 1000:1000 mode 0700 and manifest/reports/claims 0600;
  final manifest is complete with no temporary sibling; live_headroom_evidence is null because exact
  two-Worker admission never calls Task 14 authorities; no owned related process/container/GPU task
  remains. Unit evidence separately proves default three-Worker allocator/CLI rejects self-signed or
  unwired evidence, only an internal independent acceptance plus exact current provenance can pass,
  execute aggregate and cleanup hashes/semantics bind, drift fails, and same-inode mode/content changes
  are detected by complete snapshots and final re-read/hash.
result: >-
  The product parser exited 2 because the recorded multiline shell command omitted continuation
  characters after the Python module line and therefore supplied no arguments. The shell then
  interpreted the following argument lines as commands and recorded final exit 127. The allocator
  never entered resource admission: the batch root remained absent, stdout was empty, the captured
  stderr contained only the shell command-not-found diagnostic, and all three external claim records
  retained their exact preflight hashes and mtimes and were independently lockable. No related
  process, running container, or NVIDIA compute application remained. This is an invalid
  command-transcription result, not a resource-admission result; neither this experiment ID nor its
  report paths will be reused.
stdout_sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
stderr_sha256: b4abd0d1b816eb6453a06185f6388db840228d89ff3509c737b2bed9e268e0fc
time_sha256: de95956ad067620d171d72c64f7709e1afe956c2095eae8249f325b965fdfec1
exit_sha256: 743c7850cccfba5e53a9002663ec1ddd1079315a98bdbfdde10e6044f56abefe
post_run_domain_181_sha256: e6f7597c67d450d66fb112ebb2787fbcabe465a49336da03503318f9bd4dfad3
post_run_domain_182_sha256: 596f0046a7c2f5f341c57915b2122b261b938a1834880f429f6598336d2720b0
post_run_domain_183_sha256: 4bae7bccf96b89b60a84a24fd9610fb41f1737c58539d70356953ee7fef0332d
retained: empty stdout, captured stderr, exit, and time reports plus this ledger diagnosis
archived: none
deletion_candidates: none
```

## EXP-016 — Task 8 corrected independently anchored three-Worker gate and final two-Worker dry admission

```yaml
experiment_id: EXP-016
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-12T06:56:46+08:00
  - status: RUNNING
    at: 2026-09-12T06:57:45+08:00
  - status: VALID
    at: 2026-09-12T07:00:06+08:00
hypothesis: The round-3 candidate preserves exact two-Worker host admission while making default three-Worker admission fail closed until Task 11 supplies independent Task 14 acceptance and current full-provenance authorities.
mode: host resource dry admission; read-only system/process probes, host-wide same-UID flock claims, and private directory/manifest creation only; no ROS, MuJoCo, MoveIt, Broker, simulation, planning, execution, or physical action
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/resource-dry-fix6
claim_root: /run/user/1000/so101-parallel-domain-claims
claim_preflight: domains 181, 182, and 183 are owner 1000:1000 mode 0600 regular files, independently nonblocking-lockable, and retain the exact EXP-015 pre-run hashes and mtimes
git_head_at_run: e2a8e036c8f1fad0a6554de9d78858299b530dca
dirty_candidate_scope: exactly resources.py and test_parallel_batch_resources.py; controller ledger is separately untracked
resources_source_sha256: 86bb3661b2e3f0515cd021ac2566a18d791733b43deccabc76877e87dbc21e3d
resources_test_sha256: 6f95ca6d341de9975dfaeb97169e66c8aae04beea73ce77c3e53d57780e10e9b
authorized_diff_sha256: 0ca7e401e9e0ad194d89653990bf290bc83a40535f3fc503551b2a71508e8ac1
pre_run_domain_181_sha256: e6f7597c67d450d66fb112ebb2787fbcabe465a49336da03503318f9bd4dfad3
pre_run_domain_182_sha256: 596f0046a7c2f5f341c57915b2122b261b938a1834880f429f6598336d2720b0
pre_run_domain_183_sha256: 4bae7bccf96b89b60a84a24fd9610fb41f1737c58539d70356953ee7fef0332d
round3_unit_gate: pytest-DmWNP0Uo; 138 passed in 0.80 s pytest and 1.06 s wall
command: |-
  /usr/bin/zsh -f -c 'set -e;
  cd /data/work/ws_moveit/.worktrees/parallel-multipoint-v1;
  source .superpowers/sdd/2026-09-12-so101-parallel-multipoint-validation-implementation/test-env.zsh;
  run_root="$PARALLEL_EVIDENCE/resource-dry-fix6";
  run_log="$PARALLEL_EVIDENCE/reports/task8-resource-dry-016.log";
  run_stderr="$PARALLEL_EVIDENCE/reports/task8-resource-dry-016.stderr";
  run_time="$PARALLEL_EVIDENCE/reports/task8-resource-dry-016.time";
  run_exit="$PARALLEL_EVIDENCE/reports/task8-resource-dry-016.exit";
  test ! -e "$run_root"; test ! -e "$run_log"; test ! -e "$run_stderr";
  test ! -e "$run_time"; test ! -e "$run_exit"; umask 077; set +e;
  /usr/bin/time -p -o "$run_time" "$PARALLEL_PYTHON" -m so101_demo.parallel_batch.resources \
    --config src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml --worker-count 2 \
    --evidence-root "$run_root" --dry-run >"$run_log" 2>"$run_stderr";
  test_exit=$?; set -e; printf "%s\n" "$test_exit" >"$run_exit"; exit "$test_exit"'
acceptance: >-
  Exit and recorded status 0 with empty stderr and one complete JSON stdout document; exact count 2;
  finite CPU/Linux MemAvailable/GPU meet 8 CPU, 14.0 GiB RAM, and 8.0 GiB GPU; domains 181/182
  are acquired all-or-none before the process scan and independently lockable after exit; domain 183
  hash and mtime remain unchanged; manifest claims/trust policy match external time-scoped diagnostics;
  every Worker/domain/session/controller/path/socket/headless-EGL identity is unique; socket paths are
  absent and at most 107 bytes; simulation_port, bridge_port, virtual_display, and GZ_PARTITION are
  literal not_applicable; directories are owner 1000:1000 mode 0700 and manifest/reports/claims 0600;
  final manifest is complete with no temporary sibling; live_headroom_evidence is null because exact
  two-Worker admission never calls Task 14 authorities; no owned related process/container/GPU task
  remains. Unit evidence separately proves default three-Worker allocator/CLI rejects self-signed or
  unwired evidence, only an internal independent acceptance plus exact current provenance can pass,
  execute aggregate and cleanup hashes/semantics bind, drift fails, and same-inode mode/content changes
  are detected by complete snapshots and final re-read/hash.
result: >-
  Exit and recorded status were 0, stderr was empty, and stdout was semantically identical to the
  complete immutable manifest. Exactly two Workers were admitted with 24 logical CPUs, 26.931 GiB
  Linux MemAvailable, and 14.914 GiB free GPU memory against exact thresholds of 8, 14.0 GiB, and
  8.0 GiB. Worker, domain, session, controller, directory, socket, and EGL identities were unique;
  all inapplicable fields were literal not_applicable; every batch directory was 0700 and every
  manifest, report, and claim file was 0600. Both socket paths were absent and within the 107-byte
  limit, no manifest temporary sibling existed, live_headroom_evidence was null, and external
  domains 181/182 exactly matched the manifest claims and were independently lockable after exit.
  Domain 183 retained its pre-run hash and mtime. Five frozen non-candidate process skips were fully
  recorded. After excluding the readback checker and its ancestors, no process referenced this
  batch or resource module, and no running container or NVIDIA compute application remained.
manifest_sha256: b1c0e9fa9f866b9059f854106f7e19074621dd207b9589b5d1c426fd2803b1bd
stdout_sha256: eb6a6c8ee57fe3b2a2f922f120478da5d311bae53883605b9c57dbed59b9862d
stderr_sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
time_sha256: b71710e3b2319c07273e898dac7be643921dd2a367701b6526b3696767a3db79
exit_sha256: 9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa
post_run_domain_181_sha256: 93da1ec61b22650df2b68e25a5ca5a4b12cfadf98db8f3ea2fefd4495b20c3cc
post_run_domain_182_sha256: ff30afc38cbb8411c68bf47cca33d926948f8e7821d03f2138a953af25f99b01
post_run_domain_183_sha256: 4bae7bccf96b89b60a84a24fd9610fb41f1737c58539d70356953ee7fef0332d
retained: stdout, stderr, exit, time, resource tree, and immutable manifest; unlocked host claim records are mutable coordination state and only their time-scoped diagnostics are indexed here
archived: none
deletion_candidates: none
```

## EXP-017 — Task 8 content-bound stable-provenance two-Worker dry admission

```yaml
experiment_id: EXP-017
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-12T07:21:20+08:00
  - status: RUNNING
    at: 2026-09-12T07:23:13+08:00
  - status: VALID
    at: 2026-09-12T07:24:23+08:00
hypothesis: The round-4 candidate preserves exact two-Worker dry admission while three-Worker admission is bound to stable actual-content provenance for source, install, runtime config, policy, scene, models, container, and catalog.
mode: host resource dry admission; read-only system/process probes, host-wide same-UID flock claims, and private directory/manifest creation only; no ROS, MuJoCo, MoveIt, Broker, simulation, planning, execution, container, or physical action
evidence_root: /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/resource-dry-fix7
claim_root: /run/user/1000/so101-parallel-domain-claims
claim_preflight: domains 181, 182, and 183 are owner 1000:1000 mode 0600 regular files, independently nonblocking-lockable, and retain the exact EXP-016 post-run hashes and mtimes
git_head_at_run: 59e8b9323eb5ad61542e0a1b6d4e918568d7ca8d
dirty_candidate_scope: exactly resources.py and test_parallel_batch_resources.py; controller ledger is separately untracked
resources_source_sha256: b1ee3292cf28384153bc1a6a92e5108df4b4e636cf68e831e2960f84e1befb46
resources_test_sha256: 6bd25369af334f51e06873d2a2e04518145f39ed0a7a40604de6adba05a2faa4
authorized_diff_sha256: fe07de11054cebefcd11a2a0b881b619249f3c2e2f449a78d434a4cc662bf1bd
pre_run_domain_181_sha256: 93da1ec61b22650df2b68e25a5ca5a4b12cfadf98db8f3ea2fefd4495b20c3cc
pre_run_domain_182_sha256: ff30afc38cbb8411c68bf47cca33d926948f8e7821d03f2138a953af25f99b01
pre_run_domain_183_sha256: 4bae7bccf96b89b60a84a24fd9610fb41f1737c58539d70356953ee7fef0332d
round4_unit_gate: pytest-cAx7sTWL; 152 passed in 0.97 s pytest and 1.23 s wall
command: |-
  /usr/bin/zsh -f -c 'set -e;
  cd /data/work/ws_moveit/.worktrees/parallel-multipoint-v1;
  source .superpowers/sdd/2026-09-12-so101-parallel-multipoint-validation-implementation/test-env.zsh;
  run_root="$PARALLEL_EVIDENCE/resource-dry-fix7";
  run_log="$PARALLEL_EVIDENCE/reports/task8-resource-dry-017.log";
  run_stderr="$PARALLEL_EVIDENCE/reports/task8-resource-dry-017.stderr";
  run_time="$PARALLEL_EVIDENCE/reports/task8-resource-dry-017.time";
  run_exit="$PARALLEL_EVIDENCE/reports/task8-resource-dry-017.exit";
  test ! -e "$run_root"; test ! -e "$run_log"; test ! -e "$run_stderr";
  test ! -e "$run_time"; test ! -e "$run_exit"; umask 077; set +e;
  /usr/bin/time -p -o "$run_time" "$PARALLEL_PYTHON" -m so101_demo.parallel_batch.resources --config src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml --worker-count 2 --evidence-root "$run_root" --dry-run >"$run_log" 2>"$run_stderr";
  command_exit=$?; set -e; printf "%s\n" "$command_exit" >"$run_exit"; exit "$command_exit"'
acceptance: >-
  Exit and recorded status 0 with empty stderr and one complete JSON stdout document semantically
  equal to the immutable manifest; exact count 2; finite CPU/Linux MemAvailable/GPU meet 8 CPU,
  14.0 GiB RAM, and 8.0 GiB GPU; domains 181/182 are acquired all-or-none before process scan and
  independently lockable after exit; domain 183 hash and mtime unchanged; manifest claims match the
  external time-scoped diagnostics; all Worker/domain/session/controller/path/socket/headless-EGL
  identities unique; socket paths absent and at most 107 bytes; simulation_port, bridge_port,
  virtual_display, and GZ_PARTITION literal not_applicable; directories owner 1000:1000 mode 0700
  and manifest/reports/claims 0600; no temporary manifest; live_headroom_evidence null because the
  exact two-Worker path never calls Task14 authorities; no related owned process/container/GPU task
  remains. Unit evidence separately proves three-Worker candidate/acceptance/pre-current/final-current
  equality over stable actual-content identities, deep source inventories including scripts/gitlinks/
  dirty state, install/model/catalog/policy/scene content drift rejection, and late same-inode or
  cross-input mixed-epoch rejection.
result: >-
  Exit and recorded status were 0, stderr was empty, and stdout was semantically identical to the
  complete immutable manifest. Exactly two Workers were admitted with 24 logical CPUs, 26.920 GiB
  Linux MemAvailable, and 14.914 GiB free GPU memory against thresholds 8, 14.0 GiB, and 8.0 GiB.
  All Worker, domain, session, controller, directory, socket, and EGL identities were unique; all
  inapplicable fields were literal not_applicable; batch directories were 0700 and manifest, report,
  and claim files were 0600. Both 94-byte socket paths were absent, no manifest temporary sibling
  existed, and live_headroom_evidence was null. External domains 181/182 exactly matched manifest
  claims and all three domain records were independently lockable after exit. Domain 183 retained
  its pre-run hash and mtime. Five frozen non-candidate process skips were recorded. After excluding
  the readback checker and ancestors, no process referenced this batch or resource module, and no
  running container or NVIDIA compute application remained.
manifest_sha256: c0789db7a1b4a3af7bcf5c004224a1030ab47b8b405965fcd42586596a3adccd
stdout_sha256: f0fd635f920bab7575d1787b717bfde649a32d399848689d0e45c69f7ee3c293
stderr_sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
time_sha256: b2b892ce9a7c8ad29214199a33b154dab17a22613496aeb4905dbef44d49cb57
exit_sha256: 9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa
post_run_domain_181_sha256: 9ade9026b3652f9ade96d3e6e23a2a74686319574a4e7b5c465dc83811bef810
post_run_domain_182_sha256: 4acda3731cbedf5bde739a85d5c2473bb1a25ff07d4d3b25b8caa2d7edbbb698
post_run_domain_183_sha256: 4bae7bccf96b89b60a84a24fd9610fb41f1737c58539d70356953ee7fef0332d
retained: stdout, stderr, exit, time, resource tree, and immutable manifest; unlocked host claim records are mutable coordination state and only their time-scoped diagnostics are indexed here
archived: none
deletion_candidates: none
```
